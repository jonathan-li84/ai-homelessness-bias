# AI Homelessness Estimation Across California

[View the dashboard](https://jonathan-li84.github.io/ai-homelessness-bias/)

How do the accuracy, direction, and consistency of AI homelessness estimates vary across California CoCs?

The primary analysis compares the first 50 successful Gemini API runs (2,200 estimates) with January 2024 HUD PIT counts for 44 CoCs. The model is identified as gemini-3.8-flash in the first batch quota log; consistent settings across batches are assumed. Retained runs comprise 17 from batch 1, 19 from batch 2 and requests 1–14 from batch 3. Four failed requests and the final six successful requests were excluded. Exact API prompt, settings and dates were not supplied.

## Current data

- `data/raw/ai_estimate_runs_2024.csv`: retained estimates with model ID, sequential run number, original source batch/request number and CoC.
- `data/processed/ca_coc_summary_2024.csv`: baseline names, categories, population, actual PIT and homelessness rate; no AI estimates.
- `ai_estimate_run_errors_2024.csv`: signed/absolute errors for every response.
- `ai_estimate_coc_summary_2024.csv`: mean estimates, observed range, sample SD, mean signed/absolute errors and over/underestimation rates.
- `ai_estimate_category_summary_2024.csv`: equal-CoC-weighted geographic summaries.
- `ai_estimate_runs_metadata.json` and `ai_estimate_runs_report_2024.md`: provenance, methods and results.
- `ca_coc_organizations_boundaries_pit_hic_2024.geojson`: HUD boundaries, PIT/HIC/performance data and population, without embedded AI estimates.

Files without a directory prefix above are in `data/processed`.
Signed error is estimate minus actual PIT. Percentage error divides by actual PIT and multiplies by 100. Absolute error removes the sign. Signed errors and absolute errors are averaged across runs separately, so overestimates and underestimates do not cancel in the absolute measure. SD uses n−1. Ranges are observed responses, not confidence intervals. Repeated runs are not additional independent geographic observations.

## Dashboard

The map joins repeated-run results to boundaries by CoC ID. Map selectors, legends, popups and the sortable table share metric names: mean signed/absolute error in people and percentages, sample standard deviation, standard deviation %, estimate range in people and %, over/underestimation rates, mean estimate, actual PIT, population, homelessness rate and GDELT counts. The table also shows minimum–maximum estimates. Standard deviation % is sample SD divided by actual PIT times 100; estimate range % is (maximum−minimum) divided by actual PIT times 100. Category summaries include the mean CoC SD in people and mean normalized SD; these are averages of within-CoC variability, not pooled standard deviations. The dashboard also shows all 44 estimate ranges.

The CoC table, map selector and popup order is counts/context, mean estimates, signed errors, absolute errors, over/underestimation rates, ranges, standard deviations, then media counts. A second sortable table shows all these metrics by category, plus CoC counts, defaulting to Major City → Urban → Suburban → Rural order. Every header sorts numerically or by category order; clicking again reverses the direction. Estimate range sorts by its width. Category metrics are equal-CoC-weighted means: population/PIT are average counts, not totals; SDs and ranges are averaged within-CoC measures. Range endpoints are average minima and maxima. The saved category CSV uses the same grouping.

There is also a histogram for every CoC, grouped in geographic category order. Each uses all 50 response estimates, 30 equal-width bins, a shared vertical scale of 0–50 responses, and a CoC-specific horizontal scale that includes actual PIT. Reference lines mark actual PIT and the mean estimate. Hovering bars shows interval counts. Different horizontal scales/bin widths should be considered when comparing histograms.

It loads the CoC GeoJSON, repeated-run CoC summary and per-run errors, GDELT count CSV, regression-test CSV and regression-model-metrics CSV. Run `python3 -m http.server` and open <http://localhost:8000/>; opening HTML directly blocks data requests.

## Exploratory media analysis

`scripts/analyze_media_coverage_regression.py` uses one observation per CoC. Its outcome is `log(1 + mean absolute percentage error across 50 runs)`. Controls are `log(population)` and `log(actual PIT)`; the added predictor is `log(1 + article count)`.

Control R² = 0.3250; full R² = 0.3304; ΔR² = 0.0054; F(1,40) = 0.320; p = 0.575. The indicator adds limited explanatory value and provides no convincing evidence of an additional linear association. This cannot establish causation or prove zero association.

The four current outputs under `data/processed` are `coc_media_regression_data_2024.csv`, `coc_media_regression_model_metrics_2024.csv`, `coc_media_regression_tests_2024.csv` and `coc_media_regression_report_2024.md`.

## Sources

HUD FY2024 boundaries and January 2024 PIT/HIC counts come from performance profiles. The raw boundary response and 44 profile PDFs remain in `data/raw`. PIT is a one-night estimate with measurement limitations; CoCs are program geographies, not necessarily counties.

Population uses 2020–2024 ACS five-year B01003 and 2024 TIGER/Line tracts, allocating tract population by intersected area in California Albers (EPSG:3310). These are project estimates, not Census-published CoC totals. Tract data, population metadata and zipped GIS exports remain as supporting data.

`sql/gdelt_gal_gkg_usca_2024.sql` selects full-year 2024 English homelessness headlines joined to GKG California locations. State-centroid records are excluded. `scripts/build_gdelt_gkg_location_mentions.py` maps points and counties to CoCs. Raw location rows, mapped relationships and distinct article counts remain as an audit trail. Secondary mentions, ambiguous places and syndicated URLs limit this indicator as a measure of local coverage. An article can count for multiple CoCs.

## Collect new Gemini responses

`scripts/collect_gemini_estimates.py` contains the fixed 44-CoC prompt and sends
each request without prior conversation history. It reads `GEMINI_API_KEY` from
the environment. After installing requirements and setting that variable locally:

```bash
.venv/bin/python scripts/collect_gemini_estimates.py --runs 50 --delay-seconds 12
```

The model defaults to `gemini-3.8-flash` and can be changed with `--model`.
Results and errors print to stdout; the script does not overwrite the analysis
dataset. Fifty attempts may yield fewer than fifty usable responses. The delay
does not guarantee compliance with API quotas; validate returned CSVs before
adding them to the experiment. Credentials belong outside the repository.

## Rebuild data

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_ca_coc_2024.py
.venv/bin/python scripts/build_coc_population_2024.py
.venv/bin/python scripts/analyze_ai_estimate_runs.py
.venv/bin/python scripts/analyze_media_coverage_regression.py
```

To recollect GDELT, run the SQL in BigQuery, saving `ai-homelessness-bias.gdelt_work.gal_gkg_usca_2024`. Configure Google Application Default Credentials, then run:

```bash
.venv/bin/python scripts/build_gdelt_gkg_location_mentions.py --project ai-homelessness-bias --table ai-homelessness-bias.gdelt_work.gal_gkg_usca_2024
```
