#!/usr/bin/env python3
"""Build 2024 California CoC population estimates from Census tracts."""

from __future__ import annotations

import csv
import json
import math
import sys
import urllib.request
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_CENSUS = ROOT / "data" / "raw" / "census"
TRACT_DIR = RAW_CENSUS / "tracts_2024"
PROCESSED = ROOT / "data" / "processed"
SHAPEFILES = PROCESSED / "shapefiles"

COC_GEOJSON = PROCESSED / "ca_coc_organizations_boundaries_pit_hic_2024.geojson"
BLIND_GUESSES = PROCESSED / "ca_coc_blind_guesses_2024.csv"
TRACT_ZIP = RAW_CENSUS / "tl_2024_06_tract.zip"
TRACT_SHP = TRACT_DIR / "tl_2024_06_tract.shp"
ACS_TABLE = RAW_CENSUS / "acsdt5y2024-b01003.dat"
COC_CATEGORY_JSON = ROOT / "data" / "raw" / "hud_ca_coc_geography_type_2024.json"

TRACT_URL = (
    "https://www2.census.gov/geo/tiger/TIGER2024/TRACT/"
    "tl_2024_06_tract.zip"
)
ACS_URL = (
    "https://www2.census.gov/programs-surveys/acs/summary_file/2024/"
    "table-based-SF/data/5YRData/acsdt5y2024-b01003.dat"
)
COC_CATEGORY_URL = (
    "https://services.arcgis.com/VTyQ9soqVukalItT/ArcGIS/rest/services/"
    "CoC_Geo_Type/FeatureServer/0/query?where=COCNUM%20LIKE%20%27CA-%25%27"
    "&outFields=COCNUM%2CCOCNAME%2CGeo_Type&returnGeometry=false"
    "&orderByFields=COCNUM&f=json"
)

CATEGORY_NAMES = {
    "Major Cities": "Major City",
    "Other Urban CoCs": "Urban",
    "Suburban CoCs": "Suburban",
    "Rural CoCs": "Rural",
}
CATEGORY_ORDER = [
    "Major City",
    "Urban",
    "Suburban",
    "Rural",
]

EQUAL_AREA_CRS = "EPSG:3310"  # California Albers; units are meters.
EXPECTED_COCS = 44
STATE_FIPS = "06"


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "ca-coc-data/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response:
        content = response.read()
    if not content:
        raise RuntimeError(f"Empty response from {url}")
    destination.write_bytes(content)


def ensure_sources() -> None:
    if not TRACT_ZIP.exists():
        download(TRACT_URL, TRACT_ZIP)
    if not ACS_TABLE.exists():
        download(ACS_URL, ACS_TABLE)
    if not COC_CATEGORY_JSON.exists():
        download(COC_CATEGORY_URL, COC_CATEGORY_JSON)
    TRACT_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(TRACT_ZIP) as archive:
        archive.extractall(TRACT_DIR)
    if not TRACT_SHP.exists():
        raise RuntimeError("The TIGER tract archive did not contain the expected shapefile")


def read_acs_population() -> pd.DataFrame:
    data = pd.read_csv(ACS_TABLE, sep="|", dtype={"GEO_ID": "string"})
    data = data[data["GEO_ID"].str.startswith(f"1400000US{STATE_FIPS}")].copy()
    data["GEOID"] = data["GEO_ID"].str[-11:]
    data = data.rename(
        columns={
            "B01003_E001": "total_population_2024",
            "B01003_M001": "total_population_moe_2024",
        }
    )
    data["total_population_2024"] = pd.to_numeric(
        data["total_population_2024"], errors="raise"
    )
    data["total_population_moe_2024"] = pd.to_numeric(
        data["total_population_moe_2024"], errors="raise"
    )
    if data["GEOID"].duplicated().any():
        raise RuntimeError("Duplicate California tract GEOIDs in ACS B01003")
    return data[["GEOID", "total_population_2024", "total_population_moe_2024"]]


def read_coc_categories() -> pd.DataFrame:
    payload = json.loads(COC_CATEGORY_JSON.read_text())
    records = [feature["attributes"] for feature in payload.get("features", [])]
    categories = pd.DataFrame(records).rename(
        columns={"COCNUM": "coc_number", "Geo_Type": "hud_category"}
    )
    if (
        len(categories) != EXPECTED_COCS
        or categories["coc_number"].duplicated().any()
        or set(categories["hud_category"]) != set(CATEGORY_NAMES)
    ):
        raise RuntimeError("HUD category source does not contain the expected CoCs/categories")
    categories["coc_category"] = categories["hud_category"].map(CATEGORY_NAMES)
    return categories[["coc_number", "coc_category"]]


def sum_fields(frame: pd.DataFrame, fields: list[str]) -> pd.Series:
    return frame[fields].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)


def largest_remainder(values: pd.Series, target: int) -> pd.Series:
    """Round allocations to integers while preserving their statewide sum."""
    floors = values.apply(math.floor).astype("int64")
    seats = target - int(floors.sum())
    if seats < 0 or seats > len(values):
        raise RuntimeError(f"Unexpected rounding remainder: {seats}")
    fractions = values - floors
    for index in fractions.sort_values(ascending=False).index[:seats]:
        floors.loc[index] += 1
    return floors


def zip_shapefile(stem: Path) -> Path:
    output = stem.with_name(f"{stem.name}_shapefile.zip")
    members = sorted(stem.parent.glob(f"{stem.name}.*"))
    members = [path for path in members if path != output]
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member in members:
            archive.write(member, arcname=member.name)
    return output


def main() -> int:
    if not COC_GEOJSON.exists():
        raise FileNotFoundError(
            f"Missing {COC_GEOJSON.relative_to(ROOT)}; run build_ca_coc_2024.py first"
        )

    RAW_CENSUS.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    SHAPEFILES.mkdir(parents=True, exist_ok=True)
    ensure_sources()

    acs = read_acs_population()
    tracts = gpd.read_file(TRACT_SHP)
    tracts = tracts.merge(acs, on="GEOID", how="left", validate="one_to_one")
    if len(tracts) != len(acs) or tracts["total_population_2024"].isna().any():
        raise RuntimeError("TIGER/ACS tract join was not one-to-one and complete")

    tract_csv = PROCESSED / "ca_census_tract_population_2024.csv"
    tract_table = tracts[
        [
            "GEOID",
            "NAMELSAD",
            "COUNTYFP",
            "total_population_2024",
            "total_population_moe_2024",
            "ALAND",
            "AWATER",
        ]
    ].rename(
        columns={
            "GEOID": "tract_geoid",
            "NAMELSAD": "tract_name",
            "COUNTYFP": "county_fips",
            "ALAND": "land_area_square_meters",
            "AWATER": "water_area_square_meters",
        }
    )
    tract_table.to_csv(tract_csv, index=False, quoting=csv.QUOTE_MINIMAL)

    tract_shape = tracts[
        [
            "GEOID",
            "NAMELSAD",
            "total_population_2024",
            "total_population_moe_2024",
            "ALAND",
            "AWATER",
            "geometry",
        ]
    ].rename(
        columns={
            "total_population_2024": "POP2024",
            "total_population_moe_2024": "POP_MOE24",
        }
    )
    tract_shape_path = SHAPEFILES / "ca_census_tract_population_2024.shp"
    tract_shape.to_file(tract_shape_path, driver="ESRI Shapefile", encoding="UTF-8")

    cocs = gpd.read_file(COC_GEOJSON)
    cocs = cocs.drop(
        columns=["total_population_2024", "homeless_per_10000"],
        errors="ignore",
    )
    if len(cocs) != EXPECTED_COCS or cocs["COCNUM"].duplicated().any():
        raise RuntimeError(f"Expected {EXPECTED_COCS} unique California CoCs")
    cocs["geometry"] = cocs.geometry.make_valid()

    projected_tracts = tracts.to_crs(EQUAL_AREA_CRS)
    projected_cocs = cocs[["COCNUM", "geometry"]].to_crs(EQUAL_AREA_CRS)
    projected_tracts["tract_area"] = projected_tracts.geometry.area

    intersections = gpd.overlay(
        projected_tracts[
            ["GEOID", "total_population_2024", "tract_area", "geometry"]
        ],
        projected_cocs,
        how="intersection",
        keep_geom_type=False,
    )
    intersections["intersection_area"] = intersections.geometry.area
    intersections = intersections[intersections["intersection_area"] > 0].copy()

    matched_area = intersections.groupby("GEOID")["intersection_area"].transform("sum")
    intersections["normalized_area_share"] = (
        intersections["intersection_area"] / matched_area
    )
    intersections["allocated_population"] = (
        intersections["total_population_2024"]
        * intersections["normalized_area_share"]
    )

    matched_geoids = set(intersections["GEOID"])
    unmatched = tracts[~tracts["GEOID"].isin(matched_geoids)]
    if (unmatched["total_population_2024"] != 0).any():
        raise RuntimeError("At least one populated tract does not intersect a CoC")

    population = intersections.groupby("COCNUM")["allocated_population"].sum()
    state_total = int(tracts["total_population_2024"].sum())
    population = largest_remainder(population, state_total).rename("total_population_2024")
    if int(population.sum()) != state_total:
        raise RuntimeError("Rounded CoC populations do not preserve the California total")

    cocs["sheltered_2024"] = sum_fields(
        cocs,
        ["pit_sheltered_persons_in_families", "pit_sheltered_individuals"],
    )
    cocs["unsheltered_2024"] = sum_fields(
        cocs,
        ["pit_unsheltered_persons_in_families", "pit_unsheltered_individuals"],
    )
    cocs["year_round_beds_2024"] = sum_fields(
        cocs,
        [
            "hic_emergency_shelter_beds",
            "hic_safe_haven_beds",
            "hic_transitional_housing_beds",
            "hic_permanent_supportive_housing_beds",
            "hic_rapid_rehousing_beds",
            "hic_other_permanent_housing_beds",
        ],
    )
    cocs = cocs.merge(population, on="COCNUM", how="left", validate="one_to_one")
    if cocs["total_population_2024"].isna().any():
        raise RuntimeError("At least one CoC did not receive a population estimate")

    summary = cocs[
        [
            "COCNUM",
            "COCNAME",
            "total_population_2024",
            "pit_total_homeless_persons",
        ]
    ].rename(
        columns={
            "COCNUM": "coc_number",
            "COCNAME": "coc_name",
            "pit_total_homeless_persons": "pit_total_2024",
        }
    )
    categories = read_coc_categories()
    summary = summary.merge(categories, on="coc_number", how="left", validate="one_to_one")
    category_column = summary.pop("coc_category")
    summary.insert(summary.columns.get_loc("coc_name") + 1, "coc_category", category_column)
    summary.insert(
        summary.columns.get_loc("pit_total_2024") + 1,
        "homeless_per_10000",
        (
            summary["pit_total_2024"]
            / summary["total_population_2024"]
            * 10_000
        ).round(1),
    )

    blind = pd.read_csv(BLIND_GUESSES, dtype={"coc_number": "string"})
    if (
        len(blind) != EXPECTED_COCS
        or blind["coc_number"].duplicated().any()
        or set(blind["coc_number"]) != set(summary["coc_number"])
    ):
        raise RuntimeError("Blind guess file must contain exactly one row per CoC")
    summary = summary.merge(blind, on="coc_number", how="left", validate="one_to_one")
    guess_column = summary.pop("blind_guessed_pit_total_2024")
    guess_position = summary.columns.get_loc("homeless_per_10000") + 1
    summary.insert(
        guess_position,
        "blind_guessed_pit_total_2024",
        guess_column,
    )
    summary.insert(
        guess_position + 1,
        "percent_error",
        (
            (summary["blind_guessed_pit_total_2024"] - summary["pit_total_2024"])
            / summary["pit_total_2024"]
            * 100
        ).round(1),
    )
    integer_columns = [
        column
        for column in summary.columns
        if column
        not in {
            "coc_number",
            "coc_name",
            "coc_category",
            "homeless_per_10000",
            "percent_error",
        }
    ]
    summary[integer_columns] = summary[integer_columns].round().astype("int64")
    summary = summary.sort_values("coc_number")
    summary_path = PROCESSED / "ca_coc_summary_2024.csv"
    summary.to_csv(summary_path, index=False, quoting=csv.QUOTE_MINIMAL)

    category_source = summary.assign(
        _absolute_percent_error=(
            (
                summary["blind_guessed_pit_total_2024"]
                - summary["pit_total_2024"]
            ).abs()
            / summary["pit_total_2024"]
            * 100
        )
    )
    category_summary = (
        category_source.groupby("coc_category", observed=True)
        .agg(
            count=("coc_number", "size"),
            total_homeless=("pit_total_2024", "sum"),
            total_population=("total_population_2024", "sum"),
            average_absolute_percent_error=("_absolute_percent_error", "mean"),
        )
        .reindex(CATEGORY_ORDER)
        .reset_index()
    )
    category_summary.insert(
        category_summary.columns.get_loc("total_population") + 1,
        "homeless_per_10000",
        (
            category_summary["total_homeless"]
            / category_summary["total_population"]
            * 10_000
        ).round(1),
    )
    category_summary["average_absolute_percent_error"] = category_summary[
        "average_absolute_percent_error"
    ].round(1)
    category_summary_path = PROCESSED / "ca_coc_category_summary_2024.csv"
    category_summary.to_csv(category_summary_path, index=False, quoting=csv.QUOTE_MINIMAL)

    # Persist the population fields in the GeoJSON consumed by index.html.
    map_attributes = summary.set_index("coc_number")[
        [
            "coc_category",
            "total_population_2024",
            "homeless_per_10000",
            "blind_guessed_pit_total_2024",
            "percent_error",
        ]
    ].copy()
    map_attributes["absolute_percent_error"] = map_attributes["percent_error"].abs()
    population_by_coc = map_attributes.to_dict(orient="index")
    geojson = json.loads(COC_GEOJSON.read_text())
    for feature in geojson["features"]:
        code = feature["properties"]["COCNUM"]
        feature["properties"].update(population_by_coc[code])
    COC_GEOJSON.write_text(json.dumps(geojson, separators=(",", ":")) + "\n")

    coc_shape = cocs[
        [
            "COCNUM",
            "COCNAME",
            "pit_total_homeless_persons",
            "sheltered_2024",
            "unsheltered_2024",
            "pit_total_veterans",
            "pit_total_unaccompanied_youth_under_25",
            "year_round_beds_2024",
            "total_population_2024",
            "geometry",
        ]
    ].rename(
        columns={
            "pit_total_homeless_persons": "PIT_TOTAL",
            "sheltered_2024": "SHELTERED",
            "unsheltered_2024": "UNSHELTER",
            "pit_total_veterans": "VETERANS",
            "pit_total_unaccompanied_youth_under_25": "YOUTH",
            "year_round_beds_2024": "YR_BEDS",
            "total_population_2024": "TOTPOP24",
        }
    )
    coc_shape_path = SHAPEFILES / "ca_coc_2024.shp"
    coc_shape.to_file(coc_shape_path, driver="ESRI Shapefile", encoding="UTF-8")

    tract_archive = zip_shapefile(tract_shape_path.with_suffix(""))
    coc_archive = zip_shapefile(coc_shape_path.with_suffix(""))

    metadata = {
        "year": 2024,
        "population_dataset": "2020-2024 ACS 5-year Detailed Table B01003",
        "population_variable": "B01003_E001",
        "tract_geography": "2024 TIGER/Line California census tracts",
        "allocation_method": (
            "Population is allocated in proportion to each tract's intersected area "
            "among CoCs in EPSG:3310. Shares are normalized across matched CoCs; "
            "largest-remainder rounding preserves the published California total."
        ),
        "california_total_population": state_total,
        "california_tract_count": len(tracts),
        "california_coc_count": len(cocs),
        "zero_population_unmatched_offshore_tracts": len(unmatched),
        "sources": {
            "tiger_tracts": TRACT_URL,
            "acs_b01003": ACS_URL,
            "hud_coc_categories": COC_CATEGORY_URL,
        },
    }
    (PROCESSED / "ca_coc_population_2024_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )

    print(f"Wrote {summary_path.relative_to(ROOT)} ({len(summary)} CoCs)")
    print(f"Wrote {category_summary_path.relative_to(ROOT)} ({len(category_summary)} categories)")
    print(f"Wrote {tract_csv.relative_to(ROOT)} ({len(tract_table)} tracts)")
    print(f"Wrote {coc_archive.relative_to(ROOT)}")
    print(f"Wrote {tract_archive.relative_to(ROOT)}")
    print(f"California population check: {population.sum():,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
