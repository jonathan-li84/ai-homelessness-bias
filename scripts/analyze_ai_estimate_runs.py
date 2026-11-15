"""Summarize 50 Gemini API requests, one row per CoC."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.stats import pearsonr

ROOT = Path(__file__).resolve().parents[1]
CATEGORY_ORDER = ['Major City', 'Urban', 'Suburban', 'Rural']

def gini_mean_difference(values):
    """Average absolute difference over all distinct unordered response pairs."""
    samples = np.asarray(values, dtype=float)
    if samples.size < 2 or not np.isfinite(samples).all():
        raise ValueError('GMD requires at least two finite estimates')
    differences = np.abs(samples[:, None] - samples[None, :])
    return float(differences[np.triu_indices(samples.size, k=1)].mean())

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
        max_estimate=('estimated_pit_total_2024', 'max'), estimate_gmd=('estimated_pit_total_2024', gini_mean_difference),
        mean_signed_error_people=('signed_error_people', 'mean'), mean_signed_percent_error=('signed_percent_error', 'mean'),
        mean_absolute_error_people=('absolute_error_people', 'mean'), mean_absolute_percent_error=('absolute_percent_error', 'mean'),
        overestimate_rate=('signed_error_people', lambda x: 100 * (x > 0).mean()),
        underestimate_rate=('signed_error_people', lambda x: 100 * (x < 0).mean()),
    ).reset_index().merge(baseline[['coc_number','coc_name','coc_category','total_population_2024','pit_total_2024','homeless_per_10000']], on='coc_number', validate='one_to_one')
    summary['gmd_percent'] = 100 * summary.estimate_gmd / summary.pit_total_2024
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
        mean_gmd_percent=('gmd_percent','mean'),
        mean_estimate_gmd=('estimate_gmd','mean'),
        mean_signed_error_people=('mean_signed_error_people','mean'),
        mean_estimate_range_percent=('estimate_range_percent','mean'),
    ).reindex(CATEGORY_ORDER).reset_index()
    categories = categories[[
        'coc_category', 'coc_count', 'mean_population', 'mean_actual_pit',
        'mean_homeless_per_10000', 'mean_ai_estimate', 'mean_signed_error_people',
        'mean_signed_percent_error', 'mean_absolute_error_people', 'mean_absolute_percent_error',
        'mean_overestimation_rate', 'mean_underestimation_rate', 'mean_min_estimate',
        'mean_max_estimate', 'mean_estimate_range_people', 'mean_estimate_range_percent',
        'mean_estimate_gmd', 'mean_gmd_percent', 'mean_article_count',
    ]]
    categories.to_csv(ROOT / 'data/processed/ai_estimate_category_summary_2024.csv', index=False)
    correlation = pearsonr(np.log1p(summary.gmd_percent), np.log1p(summary.mean_absolute_percent_error))
    metadata = {
        'model_id': 'gemini-3.8-flash',
        'request_count': 50,
        'estimate_count': 2200,
        'coc_count': 44,
        'request_ids': 'run identifies each of the 50 requests, numbered 1 through 50.',
        'prompt': 'Full prompt and CoC list: PROMPT in scripts/collect_gemini_estimates.py.',
        'generation_date': '2026-10-10',
        'temperature': 1.0,
        'thinking_level': 'medium',
        'generation_settings_source': 'Documented model defaults; generation settings were not explicitly set in the collection script.',
        'independent_requests': 'Each request used the same fixed prompt without prior conversation history, a custom system instruction, or external tools.',
        'aggregation': 'Equal weight per CoC; estimates and signed/absolute errors use arithmetic means across runs. Absolute errors are calculated before averaging.',
    }
    metadata['units'] = 'Errors in people or percentage points. GMD is the mean absolute difference over all 1,225 distinct unordered pairs of 50 estimates. Relative GMD (%) = GMD/actual PIT*100. Relative estimate range (%) = (max-min)/actual PIT*100.'
    metadata['consistency_correlation'] = {
        'x': 'ln(1 + gmd_percent)', 'y': 'ln(1 + mean_absolute_percent_error)',
        'percentage_units': 'Percentage points (5 for 5%) before adding 1 and taking natural logarithms.',
        'n_cocs': len(summary), 'pearson_r': float(correlation.statistic),
        'p_value': float(correlation.pvalue), 'alternative': 'two-sided',
        'caution': 'Both percentages share the actual PIT denominator. Association is not causation.',
    }
    metadata['display_labels'] = {
        'estimate_gmd': 'GMD (people)', 'gmd_percent': 'Relative GMD (%)',
        'estimate_range_percent': 'Relative estimate range (%)',
        'mean_estimate_gmd': 'Mean GMD (people)', 'mean_gmd_percent': 'Mean relative GMD (%)',
        'mean_estimate_range_percent': 'Mean relative estimate range (%)',
    }
    (ROOT / 'data/processed/ai_estimate_runs_metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    report = '# Geographic AI estimation error — 50 API requests\n\n'
    report += 'How do the accuracy and consistency of AI homelessness estimates vary across California CoCs?\n\n'
    report += 'Gemini API (gemini-3.8-flash): 50 requests, 2,200 estimates, 44 CoCs. Estimates were generated on October 10, 2026. Each request used the same fixed prompt without prior conversation history, a custom system instruction, or external tools. The prompt and full CoC list are in scripts/collect_gemini_estimates.py. Temperature 1.0 and thinking level medium are the documented model defaults; generation settings were not explicitly set in the collection script.\n\n'
    report += f'Mean absolute percentage error, averaged equally across CoCs and runs: {summary.mean_absolute_percent_error.mean():.4f}%.\n\n'
    report += "Consistency is measured by Gini's mean difference (GMD): the average absolute difference over the 1,225 distinct unordered pairs among each CoC's 50 estimates. Relative GMD (%) is GMD divided by actual PIT and multiplied by 100. Category GMDs are equal-weighted means of within-CoC GMDs, not pooled variability.\n\n"
    report += f'Pearson correlation across 44 CoCs between ln(1 + relative GMD) and ln(1 + mean absolute percentage error): r = {correlation.statistic:.6f}, p-value = {correlation.pvalue:.6g} (two-sided). Percentages enter as percentage points (5 for 5%). All 44 CoCs are included. Both variables share the PIT denominator, which can contribute to the association; this is not evidence of causation.\n\n'
    report += categories.to_csv(index=False)
    report += '\nSigned errors describe direction; absolute errors describe inaccuracy. Numerical error describes people added or missed; percentage error describes error relative to actual PIT. Ranges summarize the observed 50 responses, not confidence intervals. Repeated responses are not additional independent geographic observations.\n\nThe media regression uses mean absolute percentage error across these 50 requests. See coc_media_regression_report_2024.md for current exploratory results; it does not identify causation.\n'
    (ROOT / 'data/processed/ai_estimate_runs_report_2024.md').write_text(report)
    print(categories.to_string(index=False))

if __name__ == '__main__':
    main()
