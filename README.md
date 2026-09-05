# AI Homelessness Bias

This repository contains all 44 California Continuums of Care (CoCs), their FY2024 administrative boundaries, and CoC-level 2024 homelessness data from the U.S. Department of Housing and Urban Development (HUD).

## Ready-to-use data

`data/processed/ca_coc_organizations_boundaries_pit_hic_2024.geojson` is the main dataset. Each polygon is one California CoC and includes:

- HUD CoC code and organization/area name;
- the FY2024 administrative boundary in WGS 84 (`EPSG:4326`);
- January 2024 Point-in-Time (PIT) counts, including sheltered/unsheltered people, families, chronic homelessness, veterans, and unaccompanied youth;
- 2024 Housing Inventory Count (HIC) beds by program type;
- FY2024 System Performance Measures (SPM);
- FY2024 CoC, ESG, and YHDP award amounts; and
- direct HUD source URLs for the boundary, performance profile, detailed PIT report, and detailed HIC report.

The unmodified response from HUD's boundary service is retained at `data/raw/ca_coc_boundaries_2024.geojson`. The per-CoC HUD performance profiles used for the join are retained under `data/raw/performance_profiles_2024/`.

## Census tracts and CoC population summary

`data/processed/ca_coc_summary_2024.csv` contains one row for each of the 44 CoCs with these columns:

- `coc_number`
- `coc_name`
- `coc_category`
- `total_population_2024`
- `pit_total_2024`
- `homeless_per_10000`
- `blind_guessed_pit_total_2024`
- `percent_error`

Additional Census and spatial outputs are:

- `data/processed/ca_census_tract_population_2024.csv` — all 9,129 California tracts with 2024 ACS total-population estimates and margins of error;
- `data/processed/ca_coc_blind_guesses_2024.csv` — fixed internal-knowledge guesses recorded before comparison with PIT data;
- `data/processed/ca_coc_category_summary_2024.csv` — category counts, aggregated homelessness and population, rate, and mean absolute percentage error;
- `data/raw/census/tracts_2024/` — the original 2024 Census TIGER/Line California tract shapefile;
- `data/processed/shapefiles/ca_census_tract_population_2024_shapefile.zip` — tract geometry joined to ACS population;
- `data/processed/shapefiles/ca_coc_2024_shapefile.zip` — CoC geometry with the requested summary fields; and
- `data/processed/ca_coc_population_2024_metadata.json` — sources, counts, and calculation method.

The population source is the 2020–2024 ACS 5-year estimate from Detailed Table B01003 (`B01003_E001`). Calculations intersect 2024 tract geometry with FY2024 CoC geometry in California Albers (`EPSG:3310`). A split tract's population is allocated in proportion to its intersected area among CoCs. Area shares are normalized over matched CoCs to absorb minor boundary-vintage and coastline discrepancies. Largest-remainder rounding makes the integer CoC values add exactly to the published California tract total of 39,287,377. `homeless_per_10000` is the 2024 PIT total divided by estimated CoC population, multiplied by 10,000 and rounded to one decimal. This is an area-weighted estimate, not a Census-published CoC statistic.

`blind_guessed_pit_total_2024` contains rough guesses made from internal general knowledge after viewing only CoC identifiers and names. `percent_error` is `(blind guess - PIT total) / PIT total * 100`, rounded to one decimal. Positive error means the guess was too high and negative error means it was too low. These guesses are an informal experiment and must not be treated as an alternative homelessness dataset.

`coc_category` comes from HUD's FY2024 `CoC_Geo_Type` layer and is normalized to four labels: `Major City`, `Urban`, `Suburban`, and `Rural`. In the category summary, `homeless_per_10000` is calculated from category totals. `average_absolute_percent_error` is the mean of `abs(blind guess - PIT total) / PIT total * 100` across the CoCs in each category, so overestimates and underestimates cannot cancel one another.

## Interactive map

`index.html` provides a fullscreen MapLibre map with the CoCs over OpenFreeMap's grayscale Positron vector-tile basemap. Its legend control can recolor the polygons by homelessness, population, beds, or blind-guess error metrics; hover highlights a boundary and click opens its PIT/HIC summary.

Browsers block local GeoJSON requests when an HTML file is opened directly. Start a local web server from the repository root instead:

```bash
python3 -m http.server
```

Then open <http://localhost:8000/>.

## GDELT homelessness-headline collector

`scripts/collect_gdelt_homeless_headlines.py` collects English-language article
metadata whose **headline** contains an editable homelessness term. It reads the
public minute-level [GDELT Article List (GAL)](https://blog.gdeltproject.org/announcing-the-gdelt-article-list-rss-feed/)
files and writes a deduplicated CSV under `data/raw/`. No GDELT account,
BigQuery project, or paid API is required.

The default range is January 2024. Start with a short, restartable test:

```bash
.venv/bin/python scripts/collect_gdelt_homeless_headlines.py --max-minutes 20
```

Rerun the same command without `--max-minutes` to resume and finish January:

```bash
.venv/bin/python scripts/collect_gdelt_homeless_headlines.py
```

Choose another inclusive range or search vocabulary with command-line options:

```bash
.venv/bin/python scripts/collect_gdelt_homeless_headlines.py \
  --start-date 2024-01-01 \
  --end-date 2024-12-31 \
  --terms homeless homelessness unhoused "people experiencing homelessness"
```

The collector records a checkpoint after every checked UTC minute and resumes
without discarding earlier matches. Use `--restart` only when you intentionally
want to replace the checkpoint and output for that date range. The temporary
checkpoint files are ignored by Git.

This output is only a discovery dataset of matching headlines captured by
GDELT. It is not all published news, does not search full article text, and does
not determine whether a location is in California or assign an article to a
CoC. Duplicate normalized URLs are removed, but separate publications sharing
the same headline are preserved. The selected date range is the GAL file's UTC
capture window. GDELT's `date` is sometimes a publisher-supplied publication
time and otherwise the time GDELT observed the page, so an old or republished
page can appear in a 2024 file and must not automatically be described as
published in 2024.

## Sources and year definition

- **Boundaries:** [HUD ArcGIS Continuum of Care Grantee Areas](https://www.arcgis.com/home/item.html?id=c930d736b1764c259371fc7111e02740). The service description identifies its coverage as FY2024.
- **PIT and HIC:** [HUD 2024 AHAR Part 1](https://www.huduser.gov/portal/datasets/ahar/2024-ahar-part-1-pit-estimates-of-homelessness-in-the-us.html). The counts were conducted in January 2024.
- **Joined summaries:** HUD Exchange's official `CoC Performance Profile` PDFs for reporting year 2024. Every feature contains its exact report URL.

“2024” therefore means the source's reporting/coverage year, even when HUD published or refreshed the file later. No 2023 or 2025 observations are substituted.

## Rebuild

Requires Python 3.9+ and internet access:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_ca_coc_2024.py
.venv/bin/python scripts/build_coc_population_2024.py
```

The builder validates that HUD returns exactly 44 `CA-###` features and stops on missing reports or unparseable metrics. HUD's downloadable AHAR spreadsheets are not committed because the site currently responds to non-browser downloads with an AWS WAF challenge and an empty file; the same 2024 CoC summaries are extracted from HUD's accessible official performance-profile reports instead.

## Important interpretation notes

- CoCs are HUD program geographies, not California counties or general-purpose local governments.
- PIT is a one-night estimate and has known undercount and methodology limitations; it is not an annual count of everyone who experienced homelessness.
- HIC values are year-round beds reported on the HIC date, not people served during the year.
- Null values mean HUD printed `--` or `N/A`; they are not converted to zero.
- The raw HUD boundary layer contains several blank legacy fields. Use the clear, lower-case joined fields in the processed file for analysis.
