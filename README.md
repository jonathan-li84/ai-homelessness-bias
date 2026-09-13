# AI Homelessness Bias

[View the research dashboard](https://jonathan-li84.github.io/ai-homelessness-bias/)

This project examines whether local media coverage is associated with the
accuracy of blind AI estimates of homelessness across California's 44
Continuums of Care (CoCs), after accounting for population and the actual 2024
Point-in-Time (PIT) count. The analysis measures association, not causation.

## Research question

How much additional variation in the accuracy of AI homelessness estimates is
associated with local media coverage across California CoCs, after accounting
for population and actual homelessness levels?

The population-and-PIT regression explains 40.79% of the variation in the
log-transformed absolute percentage error. Adding GDELT article count raises
this to 41.02%, a change of 0.23 percentage points. The incremental test gives
`F(1, 40) = 0.156` and `p = 0.695`, so these data do not provide convincing
evidence that article count adds explanatory value after the controls are
included.

## Dashboard

`index.html` contains:

- an interactive MapLibre map of all 44 California CoCs;
- controls for coloring the map by AI error, article mentions, homelessness
  rate, PIT count, population, or blind estimate;
- observed-versus-predicted charts for the two regression models;
- both model equations, their R² values, and the incremental F-test; and
- data-source and limitation notes.

The page reads these files directly:

- `data/processed/ca_coc_organizations_boundaries_pit_hic_2024.geojson`
- `data/processed/gdelt_gkg_article_counts_by_coc_2024.csv`
- `data/processed/coc_media_regression_data_2024.csv`

Browsers block local data requests when an HTML file is opened directly. From
the repository root, run:

```bash
python3 -m http.server
```

Then open <http://localhost:8000/>.

## Data

### CoC boundaries and HUD homelessness data

`data/processed/ca_coc_organizations_boundaries_pit_hic_2024.geojson` is the
main geographic dataset. Each feature represents one FY2024 California CoC and
contains its boundary, January 2024 PIT counts, 2024 Housing Inventory Count
data, HUD performance measures, award amounts, source URLs, estimated
population, AI estimate, and error measures.

The unmodified HUD boundary response is retained at
`data/raw/ca_coc_boundaries_2024.geojson`. The 44 HUD performance-profile PDFs
used to construct the joined data are retained under
`data/raw/performance_profiles_2024/`.

### Population and AI estimates

`data/processed/ca_coc_summary_2024.csv` contains one row per CoC with:

- CoC number, name, and HUD geographic category;
- estimated 2024 population;
- actual January 2024 PIT total;
- homelessness per 10,000 residents;
- blind AI estimate; and
- signed percentage error.

Population comes from the 2020–2024 ACS five-year estimate, Detailed Table
B01003. Census tracts are intersected with CoC boundaries in California Albers
(`EPSG:3310`). When a tract intersects multiple CoCs, its population is
allocated in proportion to intersected area. These are project estimates, not
Census-published CoC population figures.

The blind estimates in `data/processed/ca_coc_blind_guesses_2024.csv` were
generated in one GPT-5.6 Sol run after providing only the CoC identifiers and
names and before comparing the estimates with HUD counts. They are an informal
model experiment, not an alternative homelessness dataset. The repository
does not currently preserve the complete original prompt or generation
settings, which limits exact replication of that run.

`percent_error` is calculated as:

```text
(blind estimate - actual PIT total) / actual PIT total * 100
```

Positive values are overestimates and negative values are underestimates.
Absolute percentage error is used as the regression outcome so overestimates
and underestimates cannot cancel each other.

Supporting outputs are:

- `data/processed/ca_census_tract_population_2024.csv` — tract-level ACS data;
- `data/processed/ca_coc_category_summary_2024.csv` — results summarized by
  Major City, Urban, Suburban, and Rural CoCs;
- `data/processed/ca_coc_population_2024_metadata.json` — population sources
  and allocation method; and
- `data/processed/shapefiles/*_shapefile.zip` — downloadable GIS exports.

### GDELT media coverage

`sql/gdelt_gal_gkg_usca_2024.sql` selects full-calendar-year 2024 English GDELT
Article List headlines containing the project's homelessness terms, joins them
to GDELT GKG `V2Locations`, and retains point-level California (`USCA`)
annotations. State-centroid records are excluded because they cannot be
meaningfully assigned to a CoC.

`scripts/build_gdelt_gkg_location_mentions.py` reads the saved BigQuery table
and maps its location annotations to CoCs. Points are spatially joined to CoC
polygons, while county mentions are mapped through county–CoC polygon
intersections. Repeated mentions of the same GKG feature do not inflate the
final distinct-article count.

The outputs are:

- `gdelt_gkg_usca_locations_raw_2024.csv` — saved California GKG location rows;
- `gdelt_gkg_location_mentions_2024.csv` — article-location-CoC relationships;
  and
- `gdelt_gkg_article_counts_by_coc_2024.csv` — final distinct article counts
  used by the regression and dashboard.

An article can count for multiple CoCs when it mentions multiple California
locations. A location mention does not necessarily identify the primary place
discussed by the article.

## Statistical analysis

`scripts/analyze_media_coverage_regression.py` compares two nested ordinary
least-squares models across all 44 CoCs:

```text
log(1 + Absolute % Error) = log(population) + log(actual PIT count)

log(1 + Absolute % Error) = log(population) + log(actual PIT count)
                          + log(1 + article count)
```

The incremental F-test evaluates whether adding article count improves the
full model relative to the population-and-PIT model. Its outputs are:

- `coc_media_regression_data_2024.csv` — merged data and transformations;
- `coc_media_regression_model_metrics_2024.csv` — model coefficients and R²
  values;
- `coc_media_regression_tests_2024.csv` — change in R², F-statistic, degrees of
  freedom, and p-value; and
- `coc_media_regression_report_2024.md` — readable method and result summary.

The test is associational. It cannot establish that media coverage caused AI
estimates to become more or less accurate. The sample contains only 44 CoCs,
uses one AI estimate per CoC, and relies on GDELT location mentions that can
include secondary or incorrectly resolved places.

## Rebuild

Using Python 3.10 or newer, create the environment and install dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Build the HUD, population, and GIS outputs:

```bash
.venv/bin/python scripts/build_ca_coc_2024.py
.venv/bin/python scripts/build_coc_population_2024.py
```

In Google BigQuery, run `sql/gdelt_gal_gkg_usca_2024.sql` and save the result as
`ai-homelessness-bias.gdelt_work.gal_gkg_usca_2024`. After configuring Google
Application Default Credentials, build the GDELT-to-CoC outputs:

```bash
.venv/bin/python scripts/build_gdelt_gkg_location_mentions.py \
  --project ai-homelessness-bias \
  --table ai-homelessness-bias.gdelt_work.gal_gkg_usca_2024
```

Run the regression:

```bash
.venv/bin/python scripts/analyze_media_coverage_regression.py
```

## Sources and interpretation

- **HUD boundaries:** FY2024 Continuum of Care Grantee Areas.
- **HUD PIT and HIC:** January 2024 PIT count and 2024 HIC data reported in the
  2024 AHAR and CoC Performance Profiles.
- **Population:** 2020–2024 ACS five-year B01003 estimates and 2024 TIGER/Line
  census-tract boundaries.
- **Media:** Full-year 2024 GDELT Article List metadata joined to GKG
  `V2Locations` annotations.

CoCs are HUD program geographies, not necessarily counties or cities. PIT is a
one-night estimate with known undercount and methodology limitations. HIC beds
are inventory reported for the HIC date, not the number of people served during
the year. Null HUD values remain null rather than being converted to zero.
