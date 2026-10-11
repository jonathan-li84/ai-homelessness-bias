"""Summarize the first 50 successful Gemini API runs, one row per CoC."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CATEGORY_ORDER = ['Major City', 'Urban', 'Suburban', 'Rural']

def main():
    runs = pd.read_csv(ROOT / 'data/raw/ai_estimate_runs_2024.csv')
    baseline = pd.read_csv(ROOT / 'data/processed/ca_coc_summary_2024.csv')
    assert len(runs) == 2200 and set(runs.run) == set(range(1, 51))
    assert set(runs.model) == {'gemini-3.8-flash'}
    assert (runs.estimated_pit_total_2024 >= 0).all()
    assert not runs.duplicated(['run', 'coc_number']).any()
    for _, group in runs.groupby('run'):
        assert set(group.coc_number) == set(baseline.coc_number)
    data = runs.merge(baseline[['coc_number', 'pit_total_2024']], on='coc_number', validate='many_to_one')
    data['signed_error_people'] = data.estimated_pit_total_2024 - data.pit_total_2024
    data['signed_percent_error'] = 100 * data.signed_error_people / data.pit_total_2024
    data['absolute_error_people'] = data.signed_error_people.abs()
    data['absolute_percent_error'] = data.signed_percent_error.abs()
    summary = data.groupby('coc_number').agg(
        run_count=('run', 'size'),
        mean_estimate=('estimated_pit_total_2024', 'mean'), min_estimate=('estimated_pit_total_2024', 'min'),
        max_estimate=('estimated_pit_total_2024', 'max'), estimate_sd=('estimated_pit_total_2024', 'std'),
        mean_signed_error_people=('signed_error_people', 'mean'), mean_signed_percent_error=('signed_percent_error', 'mean'),
        mean_absolute_error_people=('absolute_error_people', 'mean'), mean_absolute_percent_error=('absolute_percent_error', 'mean'),
        overestimate_rate=('signed_error_people', lambda x: 100 * (x > 0).mean()),
        underestimate_rate=('signed_error_people', lambda x: 100 * (x < 0).mean()),
    ).reset_index().merge(baseline[['coc_number','coc_name','coc_category','total_population_2024','pit_total_2024','homeless_per_10000']], on='coc_number', validate='one_to_one')
    summary['normalized_sd_percent'] = 100 * summary.estimate_sd / summary.pit_total_2024
    summary['estimate_range_percent'] = 100 * (summary.max_estimate - summary.min_estimate) / summary.pit_total_2024
    summary = summary.sort_values(['coc_category', 'coc_number'], key=lambda col: col.map({name: i for i, name in enumerate(CATEGORY_ORDER)}) if col.name == 'coc_category' else col)
    summary.to_csv(ROOT / 'data/processed/ai_estimate_coc_summary_2024.csv', index=False)
    data.to_csv(ROOT / 'data/processed/ai_estimate_run_errors_2024.csv', index=False)
    counts = pd.read_csv(ROOT / 'data/processed/gdelt_gkg_article_counts_by_coc_2024.csv')
    category_source = summary.merge(counts[['coc_number', 'article_count']], on='coc_number', validate='one_to_one')
    category_source['estimate_range_people'] = category_source.max_estimate - category_source.min_estimate
    categories = category_source.groupby('coc_category').agg(
        mean_population=('total_population_2024','mean'),
        mean_actual_pit=('pit_total_2024','mean'), mean_ai_estimate=('mean_estimate','mean'),
        mean_homeless_per_10000=('homeless_per_10000','mean'),
        mean_min_estimate=('min_estimate','mean'), mean_max_estimate=('max_estimate','mean'),
        mean_estimate_range_people=('estimate_range_people','mean'),
        mean_overestimation_rate=('overestimate_rate','mean'),
        mean_underestimation_rate=('underestimate_rate','mean'),
        mean_article_count=('article_count','mean'),
        coc_count=('coc_number','size'), mean_absolute_percent_error=('mean_absolute_percent_error','mean'),
        mean_signed_percent_error=('mean_signed_percent_error','mean'),
        mean_absolute_error_people=('mean_absolute_error_people','mean'),
        mean_normalized_sd_percent=('normalized_sd_percent','mean'),
        mean_estimate_sd=('estimate_sd','mean'),
        mean_signed_error_people=('mean_signed_error_people','mean'),
        mean_estimate_range_percent=('estimate_range_percent','mean'),
    ).reindex(CATEGORY_ORDER).reset_index()
    categories = categories[[
        'coc_category', 'coc_count', 'mean_population', 'mean_actual_pit',
        'mean_homeless_per_10000', 'mean_ai_estimate', 'mean_signed_error_people',
        'mean_signed_percent_error', 'mean_absolute_error_people', 'mean_absolute_percent_error',
        'mean_overestimation_rate', 'mean_underestimation_rate', 'mean_min_estimate',
        'mean_max_estimate', 'mean_estimate_range_people', 'mean_estimate_range_percent',
        'mean_estimate_sd', 'mean_normalized_sd_percent', 'mean_article_count',
    ]]
    categories.to_csv(ROOT / 'data/processed/ai_estimate_category_summary_2024.csv', index=False)
    metadata = {'model_id':'gemini-3.8-flash','model_id_evidence':'Model named in the first batch API quota error; same model for subsequent batches assumed from user submission.', 'runs_retained':50,'estimate_count':2200,'selection':'First 50 successful API requests in submission order: 17 from batch 1, 19 from batch 2, and runs 1–14 from batch 3.', 'failed_requests_excluded':{'batch_1':[5,9,20],'batch_2':[1],'batch_3':[]}, 'successful_requests_excluded':{'batch_3':[15,16,17,18,19,20]}, 'source_ids':'source_batch and source_run preserve original request identities; run is sequential successful-run ID.', 'prompt':'Exact API prompt not supplied with the logs.', 'generation_date':None,'temperature':None,'independent_requests':'User reports Gemini API requests without earlier conversation context; request payloads and exact settings were not supplied.', 'units':'Errors in people or percentage points; SD uses sample denominator n-1; estimate range % is (max-min)/actual PIT*100.', 'aggregation':'Equal weight per CoC; estimates and signed/absolute errors use arithmetic means across runs. Absolute errors are calculated before averaging.'}
    (ROOT / 'data/processed/ai_estimate_runs_metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    report = '# Geographic AI estimation error — 50 successful API runs\n\n'
    report += 'How do the accuracy, direction, and consistency of AI homelessness estimates vary across California CoCs?\n\n'
    report += 'Gemini API (gemini-3.8-flash as identified in batch 1): 50 successful runs, 2,200 estimates, 44 CoCs. Selected chronologically: 17 successful runs from batch 1, 19 from batch 2 and runs 1–14 from batch 3. Four failed requests and the final six successful requests were excluded. Original batch/request numbers are preserved.\n\n'
    report += f'Mean absolute percentage error, averaged equally across CoCs and runs: {summary.mean_absolute_percent_error.mean():.4f}%.\n\n'
    report += categories.to_csv(index=False)
    report += '\nSigned errors describe direction; absolute errors describe inaccuracy. Numerical error describes people added or missed; percentage error describes error relative to actual PIT. Ranges summarize the observed 50 responses, not confidence intervals. Repeated responses are not additional independent geographic observations. Exact API prompt, settings and generation dates were not supplied.\n\nThe media regression uses mean absolute percentage error across these 50 runs. See coc_media_regression_report_2024.md for current exploratory results; it does not identify causation.\n'
    (ROOT / 'data/processed/ai_estimate_runs_report_2024.md').write_text(report)
    print(categories.to_string(index=False))

if __name__ == '__main__':
    main()
