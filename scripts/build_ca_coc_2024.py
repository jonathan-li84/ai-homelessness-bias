#!/usr/bin/env python3
"""Download and combine HUD FY2024 California CoC boundaries and profile data."""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
PROFILE_DIR = RAW / "performance_profiles_2024"

BOUNDARY_URL = (
    "https://services.arcgis.com/VTyQ9soqVukalItT/arcgis/rest/services/"
    "Continuum_of_Care_Grantee_Areas/FeatureServer/0/query"
    "?where=COCNUM%20LIKE%20%27CA-%25%27&outFields=*&returnGeometry=true"
    "&outSR=4326&f=geojson"
)
PROFILE_URL = (
    "https://files.hudexchange.info/reports/published/"
    "CoC_Perf_CoC_{code}-2024_CA_2024.pdf"
)

# Labels printed in HUD's "Data Summary" table. The PDF text layer puts the
# 2024 value three tokens from the right: [2024 value, change, percent change].
METRICS = {
    "pit_sheltered_persons_in_families": "Number of Sheltered Persons in Families",
    "pit_unsheltered_persons_in_families": "Number of Unsheltered Persons in Families",
    "pit_sheltered_individuals": "Number of Sheltered Individuals",
    "pit_unsheltered_individuals": "Number of Unsheltered Individuals",
    "pit_total_homeless_persons": "Total Homeless Persons",
    "pit_sheltered_families": "Number of Sheltered Families",
    "pit_unsheltered_families": "Number of Unsheltered Families",
    "pit_total_families": "Number of Total Families",
    "pit_sheltered_chronically_homeless_individuals": "Sheltered Chronically Homeless Individuals",
    "pit_unsheltered_chronically_homeless_individuals": "Unsheltered Chronically Homeless Individuals",
    "pit_total_chronically_homeless_individuals": "Total Chronically Homeless Individuals",
    "pit_sheltered_veterans": "Sheltered Veterans",
    "pit_unsheltered_veterans": "Unsheltered Veterans",
    "pit_total_veterans": "Total Veterans",
    "pit_sheltered_unaccompanied_youth_under_25": "Sheltered Unaccompanied Youth (up to 24)",
    "pit_unsheltered_unaccompanied_youth_under_25": "Unsheltered Unaccompanied Youth (up to 24)",
    "pit_total_unaccompanied_youth_under_25": "Total Unaccompanied Youth (up to 24)",
    "spm_average_length_homeless_days": "Average Length of Time Homeless (days)",
    "spm_return_to_homelessness_6_month_rate_pct": "Rate People Return to Homelessness in 6 Months",
    "spm_first_time_homeless_people": "Number of People who are Homeless for the First Time",
    "spm_exit_to_permanent_housing_rate_pct": "Rate People Exit from ES, SH, TH, and RRH to PH",
    "spm_retain_or_exit_to_permanent_housing_rate_pct": "Rate People in PSH and OPH Retain or Exit to PH",
    "hic_emergency_shelter_beds": "Emergency Shelter (ES)",
    "hic_safe_haven_beds": "Safe Haven (SH)",
    "hic_transitional_housing_beds": "Transitional Housing (TH)",
    "hic_permanent_supportive_housing_beds": "Permanent Supportive Housing (PSH)",
    "hic_rapid_rehousing_beds": "Rapid Re-Housing (RRH)",
    "hic_other_permanent_housing_beds": "Other Permanent Housing (OPH)",
    "award_emergency_solutions_grants_usd": "Emergency Solutions Grants (ESG)",
    "award_youth_homelessness_demonstration_program_usd": "Youth Homelessness Demonstration Program (YHDP)",
}

TOKEN_RE = re.compile(r"(?:\(\$[\d,]+\)|\$[\d,]+|[\d,]+(?:\.\d+)?%?|--|N/A)")


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "ca-coc-data/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        content = response.read()
    if not content:
        raise RuntimeError(f"Empty response from {url}")
    destination.write_bytes(content)


def value(token: str):
    if token in {"--", "N/A"}:
        return None
    negative = token.startswith("(") and token.endswith(")")
    cleaned = token.strip("()").replace("$", "").replace(",", "")
    if cleaned.endswith("%"):
        number = float(cleaned[:-1])
    else:
        number = float(cleaned) if "." in cleaned else int(cleaned)
    return -number if negative else number


def find_line(lines: list[str], label: str) -> str:
    matches = [line for line in lines if label in line]
    if len(matches) != 1:
        raise ValueError(f"Expected one line for {label!r}; found {len(matches)}")
    return matches[0]


def extract_2024_metrics(pdf_path: Path) -> dict:
    text = "\n".join(page.extract_text() or "" for page in PdfReader(pdf_path).pages)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    result = {}
    for key, label in METRICS.items():
        matching_lines = [line for line in lines if label in line]
        # HUD omits table rows that have no observations for a CoC (commonly
        # Safe Haven or YHDP). Preserve those omissions as null.
        if not matching_lines:
            result[key] = None
            continue
        if len(matching_lines) > 1:
            raise ValueError(f"Expected at most one line for {label!r}; found {len(matching_lines)}")
        line = matching_lines[0]
        tail = line.split(label, 1)[1]
        tokens = TOKEN_RE.findall(tail)
        if len(tokens) < 3:
            raise ValueError(f"Could not parse {label!r} in {pdf_path.name}: {line!r}")
        result[key] = value(tokens[-3])

    # This row is rendered with its label after the values in HUD's PDFs.
    coc_award_line = find_line(lines, "Continuum of Care (CoC)")
    tokens = TOKEN_RE.findall(coc_award_line.split("Continuum of Care (CoC)", 1)[0])
    if len(tokens) < 3:
        raise ValueError(f"Could not parse CoC award in {pdf_path.name}")
    result["award_continuum_of_care_usd"] = value(tokens[-3])
    return result


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    boundary_path = RAW / "ca_coc_boundaries_2024.geojson"
    download(BOUNDARY_URL, boundary_path)
    collection = json.loads(boundary_path.read_text())
    features = collection.get("features", [])
    if len(features) != 44:
        raise RuntimeError(f"Expected 44 California CoCs, received {len(features)}")

    for index, feature in enumerate(features, 1):
        props = feature["properties"]
        code = props["COCNUM"]
        if not re.fullmatch(r"CA-\d{3}", code):
            raise RuntimeError(f"Unexpected CoC code: {code!r}")
        report_url = PROFILE_URL.format(code=code)
        report_path = PROFILE_DIR / f"{code}.pdf"
        download(report_url, report_path)
        props.update(extract_2024_metrics(report_path))
        props.update(
            {
                "data_year": 2024,
                "state_abbreviation": "CA",
                "boundary_source_url": BOUNDARY_URL,
                "performance_profile_url": report_url,
                "pit_report_url": (
                    "https://files.hudexchange.info/reports/published/"
                    f"CoC_PopSub_CoC_{code}-2024_CA_2024.pdf"
                ),
                "hic_report_url": (
                    "https://files.hudexchange.info/reports/published/"
                    f"CoC_HIC_CoC_{code}-2024_CA_2024.pdf"
                ),
            }
        )
        print(f"[{index:02}/44] {code}")

    collection["name"] = "California Continuums of Care with 2024 HUD data"
    collection["year"] = 2024
    collection["sources"] = {
        "boundaries": BOUNDARY_URL,
        "performance_profiles": "HUD Exchange CoC Performance Profiles, 2024",
    }
    output = PROCESSED / "ca_coc_organizations_boundaries_pit_hic_2024.geojson"
    # Compact JSON keeps the full-resolution HUD geometry at a manageable size.
    output.write_text(json.dumps(collection, separators=(",", ":")) + "\n")
    print(f"Wrote {output.relative_to(ROOT)} ({len(features)} features)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
