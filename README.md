# AI Homelessness Estimation Across California

[View the dashboard](https://jonathan-li84.github.io/ai-homelessness-bias/)

How do the accuracy and consistency of AI homelessness estimates vary across California CoCs?

The primary analysis compares 50 Gemini API requests (2,200 estimates) with January 2024 HUD PIT counts for 44 CoCs. The estimates were generated on October 10, 2026, using gemini-3.8-flash. Each request used the same fixed prompt without previous conversation history, a custom system instruction, or external tools. Temperature 1.0 and thinking level medium are the documented model defaults; generation settings were not explicitly set in the collection script. The full prompt and CoC list are saved in scripts/collect_gemini_estimates.py.

## Current data

- `data/raw/ai_estimate_runs_2024.csv`: estimates from 50 requests, with model ID, request number and CoC.
- `data/processed/ca_coc_summary_2024.csv`: baseline names, population, actual PIT and homelessness rate; no AI estimates.
- `ai_estimate_run_errors_2024.csv`: signed/absolute errors for every response.
- `ai_estimate_coc_summary_2024.csv`: mean estimates, observed range, GMD, mean signed/absolute errors and over/underestimation rates.
- `ai_estimate_runs_metadata.json` and `ai_estimate_runs_report_2024.md`: provenance, methods and results.
- `ca_coc_organizations_boundaries_pit_hic_2024.geojson`: HUD boundaries, PIT/HIC/performance data and population, without embedded AI estimates.

Files without a directory prefix above are in `data/processed`.
Signed error is estimate minus actual PIT. Percentage error divides by actual PIT and multiplies by 100. Absolute error removes the sign. Signed errors and absolute errors are averaged across runs separately, so overestimates and underestimates do not cancel in the absolute measure. Gini’s mean difference (GMD) averages absolute differences over the 1,225 distinct unordered pairs among each CoC’s 50 estimates. It is zero only when all estimates are identical. Relative GMD (%) divides GMD by actual PIT and multiplies by 100. Ranges are observed responses, not confidence intervals. Repeated runs are not additional independent geographic observations.

## Dashboard

The dashboard opens with an Overview that introduces the research question, summarizes population relationships, and compares population with accuracy and consistency in two log-transformed scatterplots. A persistent, grouped sidebar links to Geography, Consistency, CoC comparison, Distributions, Media analysis, and Methods & data. On mobile the sidebar becomes a compact horizontal navigation bar. URL hashes support direct links and browser back/forward navigation. The consistency view keeps the range chart immediately before the relative-GMD chart, followed by the correlation plot; the long 44-CoC charts have scrollable frames.

The overview explains the benchmark and interpretation limits, and uses El Dorado and the highest-relative-GMD CoC as contrasting examples of accuracy and consistency. Geography contains one interactive map with selectable measures, CoC lookup, and detailed results, over an OpenFreeMap Positron basemap. Fills at 100% opacity retain the yellow–green–cyan–blue palette, with a diverging palette for signed errors. Basemap text labels render above the CoC fills and outlines. California is fitted when the Geography panel first becomes visible, rather than while the map container is hidden. Chart footnotes link to their underlying data, and the consistency view includes local chart navigation. Navigation and filtering do not change the underlying observations or recalculate the analyses.

The CoC comparison table supports searching by name or ID. The distribution view has its own name/ID search for the 44 heatmap rows. The study view includes measure definitions, sources and limitations, CSV downloads, and all six paper figures. Hover details remain instant across charts and table controls.

Select a CoC name in the table, a range-chart point, a ranked-GMD row, or a scatterplot point to open its linked profile. The profile shows six key measures and links directly to that CoC’s map location, table row, and 50-response heatmap row. Chart selections also work with the keyboard. The map includes a CoC lookup and reset control, selected boundaries are outlined, and both searchable views have filter-reset buttons. Selecting or filtering a place does not recalculate the analysis.

The map joins repeated-run results to boundaries by CoC ID. Map selectors, legends, popups and the sortable table share metric names: mean signed/absolute error in people and percentages, GMD, Relative GMD (%), estimate range in people and %, over/underestimation rates, mean estimate, actual PIT, population, homelessness rate and GDELT counts. The table also shows minimum–maximum estimates. Relative GMD (%) is GMD divided by actual PIT times 100; relative estimate range (%) is (maximum−minimum) divided by actual PIT times 100. The dashboard also shows all 44 estimate ranges.

The CoC table, map selector and popup order is counts/context, mean estimates, signed errors, absolute errors, over/underestimation rates, ranges, GMDs, then media counts. Table headers sort numerically, clicking again reverses the direction. Estimate range sorts by its width. CoCs default to numeric CoC order.

The sorted error heatmap shows one row per CoC in CoC-number order, with 50 tiles sorted independently by signed percentage error from lowest to highest (ties use original run order). Tile positions indicate rank, not error magnitude or chronology. Blue marks underestimates, magenta overestimates, and pale yellow exact matches, using the same five-color palette as the signed-error map. The two color ramps use square-root scaling capped at −100% and +100%, so small errors remain visible and matching magnitudes receive matching intensity. Errors beyond these limits receive the darkest color, with exact values retained in tooltips. Legends label the color scale. Actual PIT, mean estimate, and under/exact/over rates appear beside each row. Instant hover and keyboard-focus tooltips show the original run, estimate, signed percentage error, and error in people. All 50 responses are included, including duplicates and outliers. The table scrolls within its frame, with sticky CoC labels and column headers. Searching and linked profile navigation filter the rows without changing colors or recalculating results.

The consistency–accuracy scatterplot uses ln(1 + relative GMD) and ln(1 + mean absolute percentage error), with percentages entered as percentage points (5 for 5%). It retains all 44 CoCs, uses blue points and shows an overall fitted line, Pearson r and p-value. Current r = 0.807816 and p = 3.41669 × 10⁻¹¹. Both percentages share the actual PIT denominator, which can contribute to the association. Results are also saved in the run metadata and report. The media regression remains a separate analysis with an unchanged outcome.

The Overview includes two population scatterplots: ln(population) versus ln(1 + mean absolute percentage error), and ln(population) versus ln(1 + relative GMD). They use the 50-run summaries for all 44 CoCs, blue points, linked CoC selections, instant tooltips, fitted lines, and Pearson r and p values calculated from the CSV. Current correlations are −0.515727 (p = 0.000339798) for accuracy and −0.573388 (p = 0.0000473407) for consistency. These are unadjusted associations, not causal effects. Both outcomes are normalized by actual PIT, which may contribute to their association with population. No outliers are removed.

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
dataset. The delay
does not guarantee compliance with API quotas; validate returned CSVs before
adding them to the experiment. Credentials belong outside the repository.

## Rebuild data

Paper figures are exported to `figures/` as editable SVG files and high-resolution PNGs:

```bash
.venv/bin/python scripts/export_paper_figures.py
```

PNG export requires `rsvg-convert` on PATH; without it, the script still exports SVGs. The six figures are (1) side-by-side signed- and absolute-percentage-error maps, (2) ranked relative GMD, (3) the sorted error heatmap, (4) population versus accuracy and consistency, (5) the ln-transformed consistency–accuracy scatterplot, and (6) the exploratory media-model comparison. Figure 1 compares mean signed percentage error with mean absolute percentage error using identical map geometry and separate labeled color scales. Figure 3 includes all 44 CoCs and 2,200 responses, plus actual PIT, mean estimate, and under/exact/over rates, with the dashboard’s square-root color scale capped at ±100%. Figure 4 combines two panels, using ln(population) and ln(1 + percentage outcome), with Pearson r, p values, and blue points. Figure 6 stacks the models without and with article count, with identical axis limits, fitted equations, R² values and the incremental F-test result. They use the current processed data and dashboard colors. The map uses projected CoC boundaries without external basemap tiles.

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
