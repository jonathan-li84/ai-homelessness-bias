#!/usr/bin/env python3
"""Map saved GDELT GKG California location annotations to 2024 CoCs.

The expensive GAL-to-GKG query is intentionally kept in
sql/gdelt_gal_gkg_usca_2024.sql. This script reads its saved destination table,
exports the unmodified GKG rows, and performs the local spatial joins. It does
not download article pages and does not use an AI classifier.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import geopandas as gpd
import pandas as pd
import requests
from google.cloud import bigquery


ROOT = Path(__file__).resolve().parents[1]
COUNTY_SHAPEFILE_URL = (
    "https://www2.census.gov/geo/tiger/TIGER2024/COUNTY/"
    "tl_2024_us_county.zip"
)
TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src"}
COUNTY_NAME = re.compile(r"^\s*([^,]+ County)\s*(?:,|$)", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="ai-homelessness-bias")
    parser.add_argument(
        "--table",
        default="ai-homelessness-bias.gdelt_work.gal_gkg_usca_2024",
        help="Existing destination table created by the SQL query",
    )
    parser.add_argument(
        "--cocs",
        type=Path,
        default=ROOT
        / "data/processed/ca_coc_organizations_boundaries_pit_hic_2024.geojson",
    )
    parser.add_argument(
        "--county-shapefile",
        type=Path,
        default=Path("/tmp/tl_2024_us_county.zip"),
    )
    parser.add_argument(
        "--raw-output",
        type=Path,
        default=ROOT / "data/processed/gdelt_gkg_usca_locations_raw_2024.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data/processed/gdelt_gkg_location_mentions_2024.csv",
    )
    parser.add_argument(
        "--counts-output",
        type=Path,
        default=ROOT / "data/processed/gdelt_gkg_article_counts_by_coc_2024.csv",
    )
    parser.add_argument(
        "--nearest-limit-km",
        type=float,
        default=25.0,
        help="Maximum nearest-CoC fallback distance for points outside polygons",
    )
    return parser.parse_args()


def normalize_url(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    if parts.port and not (
        (parts.scheme.lower() == "http" and parts.port == 80)
        or (parts.scheme.lower() == "https" and parts.port == 443)
    ):
        host = f"{host}:{parts.port}"
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in TRACKING_PARAMETERS
    ]
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), host, path, urlencode(query), ""))


def make_article_id(normalized_url: str) -> str:
    digest = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:24]
    return f"gdelt_gal_{digest}"


def download_if_missing(path: Path, url: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url} to {path}")
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with path.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                output.write(chunk)


def fetch_saved_table(project: str, table_id: str) -> pd.DataFrame:
    """Read a saved table without running another BigQuery SQL scan."""
    client = bigquery.Client(project=project)
    table = client.get_table(table_id)
    # Building records from Row objects avoids requiring the optional
    # db-dtypes and BigQuery Storage packages for this modestly sized table.
    records = [dict(row.items()) for row in client.list_rows(table)]
    result = pd.DataFrame.from_records(records, columns=[field.name for field in table.schema])
    if len(result) != table.num_rows:
        raise RuntimeError(
            f"Downloaded {len(result):,} rows but table reports {table.num_rows:,}"
        )
    return result


def prepare_raw(data: pd.DataFrame) -> pd.DataFrame:
    data = data.copy()
    data["date"] = pd.to_datetime(data["date"], utc=True)
    data["normalized_url"] = data["url"].fillna("").map(normalize_url)
    data["article_id"] = data["normalized_url"].map(make_article_id)
    data["gkg_location_source"] = "GDELT GKG V2Locations"
    front = [
        "article_id",
        "date",
        "url",
        "normalized_url",
        "domain",
        "publisher",
        "title",
        "description",
        "language",
        "author",
    ]
    return data[front + [column for column in data.columns if column not in front]]


def county_coc_crosswalk(
    county_zip: Path, cocs: gpd.GeoDataFrame
) -> dict[str, list[tuple[str, str]]]:
    counties = gpd.read_file(f"zip://{county_zip.resolve()}")
    counties = counties.loc[
        counties["STATEFP"].eq("06"), ["GEOID", "NAMELSAD", "geometry"]
    ].to_crs(3310)
    coc_shapes = cocs[["COCNUM", "COCNAME", "geometry"]].to_crs(3310)
    overlaps = gpd.overlay(counties, coc_shapes, how="intersection")
    overlaps["overlap_sq_km"] = overlaps.geometry.area / 1_000_000
    # Ignore microscopic boundary/sliver intersections.
    overlaps = overlaps.loc[overlaps["overlap_sq_km"].gt(1.0)].copy()
    grouped = (
        overlaps.sort_values(["GEOID", "overlap_sq_km"], ascending=[True, False])
        .groupby("GEOID", sort=False)[["COCNUM", "COCNAME"]]
        .apply(lambda frame: list(frame.itertuples(index=False, name=None)), include_groups=False)
    )
    return grouped.to_dict()


def is_county_mention(location_name: object) -> bool:
    return bool(COUNTY_NAME.search(str(location_name or "")))


def map_counties(
    rows: pd.DataFrame, crosswalk: dict[str, list[tuple[str, str]]]
) -> pd.DataFrame:
    output: list[dict[str, object]] = []
    for row in rows.to_dict("records"):
        adm2 = str(row.get("adm2_code") or "")
        geoid = "06" + adm2[-3:] if re.fullmatch(r"CA\d{3}", adm2) else ""
        matches = crosswalk.get(geoid, [])
        if not matches:
            output.append(
                {**row, "coc_number": "", "coc_name": "", "coc_mapping_method": "unmapped_county"}
            )
            continue
        method = "county_polygon_multiple_cocs" if len(matches) > 1 else "county_polygon_single_coc"
        for coc_number, coc_name in matches:
            output.append(
                {
                    **row,
                    "coc_number": coc_number,
                    "coc_name": coc_name,
                    "coc_mapping_method": method,
                }
            )
    return pd.DataFrame(output)


def map_points(
    rows: pd.DataFrame, cocs: gpd.GeoDataFrame, nearest_limit_km: float
) -> pd.DataFrame:
    if rows.empty:
        return rows.assign(
            coc_number=pd.Series(dtype=str),
            coc_name=pd.Series(dtype=str),
            coc_mapping_method=pd.Series(dtype=str),
        )
    points = gpd.GeoDataFrame(
        rows.copy(),
        geometry=gpd.points_from_xy(rows["longitude"], rows["latitude"]),
        crs=4326,
    )
    coc_shapes = cocs[["COCNUM", "COCNAME", "geometry"]].to_crs(4326)
    mapped = gpd.sjoin(points, coc_shapes, how="left", predicate="intersects")
    mapped = mapped.rename(columns={"COCNUM": "coc_number", "COCNAME": "coc_name"})
    mapped["coc_mapping_method"] = mapped["coc_number"].notna().map(
        {True: "gkg_point_in_coc", False: "unmapped_point"}
    )

    missing_index = mapped.index[mapped["coc_number"].isna()].unique()
    if len(missing_index):
        missing_points = points.loc[missing_index].to_crs(3310)
        nearest = gpd.sjoin_nearest(
            missing_points,
            coc_shapes.to_crs(3310),
            how="left",
            distance_col="coc_distance_m",
        )
        nearest = nearest.sort_values("coc_distance_m").loc[~nearest.index.duplicated()]
        acceptable = nearest["coc_distance_m"].le(nearest_limit_km * 1000)
        nearest = nearest.loc[acceptable]
        mapped.loc[nearest.index, "coc_number"] = nearest["COCNUM"]
        mapped.loc[nearest.index, "coc_name"] = nearest["COCNAME"]
        mapped.loc[nearest.index, "coc_mapping_method"] = "nearest_coc_within_limit"

    return pd.DataFrame(mapped.drop(columns=["geometry", "index_right"], errors="ignore"))


def write_counts(mapped: pd.DataFrame, cocs: gpd.GeoDataFrame, path: Path) -> None:
    valid = mapped.loc[mapped["coc_number"].fillna("").ne("")]
    counts = valid.groupby("coc_number", as_index=False).agg(
        article_count=("article_id", "nunique"),
        article_location_relationship_count=("article_id", "size"),
    )
    all_cocs = (
        cocs[["COCNUM", "COCNAME"]]
        .drop_duplicates()
        .rename(columns={"COCNUM": "coc_number", "COCNAME": "coc_name"})
    )
    counts = all_cocs.merge(counts, on="coc_number", how="left")
    counts[["article_count", "article_location_relationship_count"]] = counts[
        ["article_count", "article_location_relationship_count"]
    ].fillna(0).astype(int)
    counts = counts.sort_values(["article_count", "coc_number"], ascending=[False, True])
    path.parent.mkdir(parents=True, exist_ok=True)
    counts.to_csv(path, index=False)


def main() -> None:
    args = parse_args()
    download_if_missing(args.county_shapefile, COUNTY_SHAPEFILE_URL)
    raw = prepare_raw(fetch_saved_table(args.project, args.table))
    if raw.empty:
        raise RuntimeError("The saved BigQuery table is empty")
    if raw["date"].min() < pd.Timestamp("2024-01-01", tz="UTC") or raw[
        "date"
    ].max() >= pd.Timestamp("2025-01-01", tz="UTC"):
        raise RuntimeError("The saved table contains records outside calendar year 2024")

    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    raw.sort_values(["date", "article_id", "character_offset"]).to_csv(
        args.raw_output, index=False
    )

    cocs = gpd.read_file(args.cocs)
    county_mask = raw["location_name"].map(is_county_mention)
    crosswalk = county_coc_crosswalk(args.county_shapefile, cocs)
    county_rows = map_counties(raw.loc[county_mask], crosswalk)
    point_rows = map_points(raw.loc[~county_mask], cocs, args.nearest_limit_km)
    mapped = pd.concat([point_rows, county_rows], ignore_index=True)

    # One article-location-CoC relationship per GKG feature. Character offsets
    # remain in the raw export but repeated mentions do not inflate CoC counts.
    dedupe_key = [
        "article_id",
        "feature_id",
        "location_name",
        "latitude",
        "longitude",
        "coc_number",
    ]
    mapped = mapped.sort_values(["date", "article_id", "character_offset"])
    mapped = mapped.drop_duplicates(dedupe_key, keep="first")
    mapped.insert(0, "relationship_id", range(1, len(mapped) + 1))
    mapped = mapped.drop(columns=["geometry"], errors="ignore")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    mapped.to_csv(args.output, index=False)
    write_counts(mapped, cocs, args.counts_output)

    mapped_articles = mapped.loc[mapped["coc_number"].fillna("").ne(""), "article_id"].nunique()
    print(f"Raw GKG rows: {len(raw):,} across {raw['article_id'].nunique():,} articles")
    print(f"Mapped relationships: {len(mapped):,} across {mapped_articles:,} articles")
    print(f"Full-year output: {args.output}")
    print(f"CoC counts: {args.counts_output}")


if __name__ == "__main__":
    main()
