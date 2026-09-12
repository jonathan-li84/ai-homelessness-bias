#!/usr/bin/env python3
"""Test the adjusted association between GDELT mentions and AI estimate error.

The analysis uses all 44 California CoCs. Because article counts and absolute
percentage errors are right-skewed, both are log transformed. Population and
the actual PIT count are also log transformed. A restricted cubic spline tests
whether the article-count association departs from linearity.

This is an associational analysis. It does not identify a causal effect.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / "data/processed/ca_coc_summary_2024.csv",
    )
    parser.add_argument(
        "--article-counts",
        type=Path,
        default=ROOT / "data/processed/gdelt_gkg_article_counts_by_coc_2024.csv",
    )
    parser.add_argument(
        "--analysis-data",
        type=Path,
        default=ROOT / "data/processed/coc_media_regression_data_2024.csv",
    )
    parser.add_argument(
        "--model-metrics",
        type=Path,
        default=ROOT / "data/processed/coc_media_regression_model_metrics_2024.csv",
    )
    parser.add_argument(
        "--tests",
        type=Path,
        default=ROOT / "data/processed/coc_media_regression_tests_2024.csv",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "data/processed/coc_media_regression_report_2024.md",
    )
    return parser.parse_args()


def restricted_cubic_spline(
    values: np.ndarray, probabilities: tuple[float, float, float] = (0.10, 0.50, 0.90)
) -> tuple[np.ndarray, np.ndarray]:
    """Return linear and nonlinear columns for a 3-knot natural cubic spline."""
    knots = np.quantile(values, probabilities)
    first, middle, last = knots
    if not first < middle < last:
        raise ValueError("Spline knots must be distinct")

    def positive_cube(value: np.ndarray, knot: float) -> np.ndarray:
        return np.maximum(value - knot, 0.0) ** 3

    nonlinear = (
        positive_cube(values, first)
        - positive_cube(values, middle) * (last - first) / (last - middle)
        + positive_cube(values, last) * (middle - first) / (last - middle)
    ) / (last - first) ** 2
    return np.column_stack([values, nonlinear]), knots


def fit_ols(matrix: np.ndarray, outcome: np.ndarray) -> dict[str, object]:
    coefficients = np.linalg.lstsq(matrix, outcome, rcond=None)[0]
    inverse = np.linalg.pinv(matrix.T @ matrix)
    residuals = outcome - matrix @ coefficients
    rss = float(residuals @ residuals)
    leverage = np.sum(matrix * (matrix @ inverse), axis=1)
    adjusted_residual_sq = (residuals / (1.0 - leverage)) ** 2
    hc3_covariance = inverse @ (
        matrix.T @ (adjusted_residual_sq[:, None] * matrix)
    ) @ inverse
    n, parameters = matrix.shape
    total_ss = float(np.sum((outcome - outcome.mean()) ** 2))
    r_squared = 1.0 - rss / total_ss
    loocv_rmse = float(np.sqrt(np.mean((residuals / (1.0 - leverage)) ** 2)))
    return {
        "coefficients": coefficients,
        "residuals": residuals,
        "rss": rss,
        "hc3_covariance": hc3_covariance,
        "leverage": leverage,
        "r_squared": r_squared,
        "loocv_rmse": loocv_rmse,
        "n": n,
        "parameters": parameters,
    }


def nested_f_test(
    reduced: dict[str, object], full: dict[str, object], added_df: int
) -> tuple[float, float]:
    denominator_df = int(full["n"]) - int(full["parameters"])
    statistic = (
        (float(reduced["rss"]) - float(full["rss"])) / added_df
    ) / (float(full["rss"]) / denominator_df)
    return statistic, float(stats.f.sf(statistic, added_df, denominator_df))


def hc3_wald_test(
    fit: dict[str, object], coefficient_indices: list[int]
) -> tuple[float, float]:
    indices = np.asarray(coefficient_indices)
    coefficients = np.asarray(fit["coefficients"])[indices]
    covariance = np.asarray(fit["hc3_covariance"])[np.ix_(indices, indices)]
    numerator_df = len(indices)
    denominator_df = int(fit["n"]) - int(fit["parameters"])
    statistic = float(
        coefficients @ np.linalg.pinv(covariance) @ coefficients / numerator_df
    )
    return statistic, float(stats.f.sf(statistic, numerator_df, denominator_df))


def variance_inflation_factor(target: np.ndarray, others: np.ndarray) -> float:
    matrix = np.column_stack([np.ones(len(target)), others])
    residuals = target - matrix @ np.linalg.lstsq(matrix, target, rcond=None)[0]
    r_squared = 1.0 - (residuals @ residuals) / np.sum((target - target.mean()) ** 2)
    return float(1.0 / (1.0 - r_squared))


def main() -> None:
    args = parse_args()
    summary = pd.read_csv(args.summary)
    counts = pd.read_csv(args.article_counts)
    data = summary.merge(
        counts[["coc_number", "article_count"]],
        on="coc_number",
        how="inner",
        validate="one_to_one",
    )
    if len(data) != 44:
        raise RuntimeError(f"Expected 44 matched CoCs, found {len(data)}")

    required_positive = ["total_population_2024", "pit_total_2024", "article_count"]
    if (data[required_positive] <= 0).any().any():
        raise RuntimeError("Population, PIT totals, and article counts must be positive")
    data["absolute_percent_error"] = data["percent_error"].abs()
    data["log1p_absolute_percent_error"] = np.log1p(data["absolute_percent_error"])
    data["log1p_article_count"] = np.log1p(data["article_count"])
    data["log_population"] = np.log(data["total_population_2024"])
    data["log_pit_total"] = np.log(data["pit_total_2024"])

    outcome = data["log1p_absolute_percent_error"].to_numpy()
    controls = np.column_stack(
        [
            np.ones(len(data)),
            data["log_population"],
            data["log_pit_total"],
        ]
    )
    spline_columns, knots = restricted_cubic_spline(
        data["log1p_article_count"].to_numpy()
    )
    data["article_spline_nonlinear"] = spline_columns[:, 1]
    matrices = {
        "controls_only": controls,
        "log_linear_article_count": np.column_stack([controls, spline_columns[:, 0]]),
        "article_count_spline": np.column_stack([controls, spline_columns]),
    }
    fits = {name: fit_ols(matrix, outcome) for name, matrix in matrices.items()}

    # Partial-regression values used by the website to show exactly what the
    # population/PIT adjustment removes (Frisch-Waugh-Lovell equivalence).
    article_log = data["log1p_article_count"].to_numpy()
    article_control_fit = fit_ols(controls, article_log)
    data["article_residual_after_population_pit"] = article_control_fit["residuals"]
    data["error_residual_after_population_pit"] = fits["controls_only"]["residuals"]
    unadjusted_matrix = np.column_stack([np.ones(len(data)), article_log])
    unadjusted_fit = fit_ols(unadjusted_matrix, outcome)
    data["unadjusted_fitted_log1p_absolute_error"] = (
        unadjusted_matrix @ np.asarray(unadjusted_fit["coefficients"])
    )

    model_rows = []
    control_r_squared = float(fits["controls_only"]["r_squared"])
    for name, fit in fits.items():
        model_rows.append(
            {
                "model": name,
                "n": fit["n"],
                "parameters": fit["parameters"],
                "r_squared": fit["r_squared"],
                "incremental_r_squared_vs_controls": float(fit["r_squared"])
                - control_r_squared,
                "loocv_rmse_log1p_absolute_error": fit["loocv_rmse"],
            }
        )

    comparisons = [
        (
            "linear_article_association",
            "controls_only",
            "log_linear_article_count",
            [3],
        ),
        (
            "overall_spline_article_association",
            "controls_only",
            "article_count_spline",
            [3, 4],
        ),
        (
            "article_association_nonlinearity",
            "log_linear_article_count",
            "article_count_spline",
            [4],
        ),
    ]
    test_rows = []
    for hypothesis, reduced_name, full_name, coefficient_indices in comparisons:
        reduced_fit = fits[reduced_name]
        full_fit = fits[full_name]
        added_df = matrices[full_name].shape[1] - matrices[reduced_name].shape[1]
        classical_f, classical_p = nested_f_test(reduced_fit, full_fit, added_df)
        robust_f, robust_p = hc3_wald_test(full_fit, coefficient_indices)
        test_rows.append(
            {
                "hypothesis": hypothesis,
                "reduced_model": reduced_name,
                "full_model": full_name,
                "numerator_df": added_df,
                "denominator_df": len(data) - matrices[full_name].shape[1],
                "classical_f": classical_f,
                "classical_p_value": classical_p,
                "hc3_robust_f": robust_f,
                "hc3_robust_p_value": robust_p,
            }
        )

    linear_fit = fits["log_linear_article_count"]
    linear_coefficient = float(np.asarray(linear_fit["coefficients"])[3])
    linear_se = float(np.sqrt(np.asarray(linear_fit["hc3_covariance"])[3, 3]))
    linear_df = int(linear_fit["n"]) - int(linear_fit["parameters"])
    critical_t = float(stats.t.ppf(0.975, linear_df))
    lower = linear_coefficient - critical_t * linear_se
    upper = linear_coefficient + critical_t * linear_se
    doubling_change = 100.0 * (np.exp(linear_coefficient * np.log(2.0)) - 1.0)
    doubling_lower = 100.0 * (np.exp(lower * np.log(2.0)) - 1.0)
    doubling_upper = 100.0 * (np.exp(upper * np.log(2.0)) - 1.0)

    article_vif = variance_inflation_factor(
        data["log1p_article_count"].to_numpy(),
        data[["log_population", "log_pit_total"]].to_numpy(),
    )
    population_vif = variance_inflation_factor(
        data["log_population"].to_numpy(),
        data[["log1p_article_count", "log_pit_total"]].to_numpy(),
    )
    pit_vif = variance_inflation_factor(
        data["log_pit_total"].to_numpy(),
        data[["log1p_article_count", "log_population"]].to_numpy(),
    )

    model_metrics = pd.DataFrame(model_rows)
    tests = pd.DataFrame(test_rows)
    for path in [args.analysis_data, args.model_metrics, args.tests, args.report]:
        path.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(args.analysis_data, index=False)
    model_metrics.to_csv(args.model_metrics, index=False)
    tests.to_csv(args.tests, index=False)

    spline_test = tests.loc[
        tests["hypothesis"].eq("overall_spline_article_association")
    ].iloc[0]
    nonlinear_test = tests.loc[
        tests["hypothesis"].eq("article_association_nonlinearity")
    ].iloc[0]
    linear_test = tests.loc[
        tests["hypothesis"].eq("linear_article_association")
    ].iloc[0]
    article_knots = np.expm1(knots)
    report = f"""# Media coverage regression — 2024 California CoCs

## Question

Is GDELT article count associated with the absolute percentage error of the blind AI estimate after accounting for CoC population and the actual PIT count?

This is an associational test, not a causal estimate.

## Specification

- Observations: {len(data)} California CoCs.
- Outcome: `log(1 + absolute percentage error)`.
- Exposure: `log(1 + distinct GDELT article count)`.
- Controls: `log(population)` and `log(actual PIT total)`.
- Nonlinearity: three-knot restricted cubic spline with article-count knots at {article_knots[0]:.1f}, {article_knots[1]:.1f}, and {article_knots[2]:.1f}.
- Inference: HC3 heteroskedasticity-robust Wald tests. The primary test evaluates whether the adjusted log-linear article-count coefficient equals zero.

## Results

- Primary log-linear article-count test: coefficient = {linear_coefficient:.3f}, HC3 95% CI [{lower:.3f}, {upper:.3f}], p = {linear_test['hc3_robust_p_value']:.3f}.
- Overall spline association: HC3 p = {spline_test['hc3_robust_p_value']:.3f}.
- Evidence of nonlinearity beyond a straight line: HC3 p = {nonlinear_test['hc3_robust_p_value']:.3f}.
- Interpreted approximately, doubling article count corresponds to a {doubling_change:.1f}% change in `(1 + absolute percentage error)`; HC3 95% CI [{doubling_lower:.1f}%, {doubling_upper:.1f}%].
- Incremental R² over population and PIT controls: linear = {model_metrics.loc[model_metrics['model'].eq('log_linear_article_count'), 'incremental_r_squared_vs_controls'].iloc[0]:.3f}; spline = {model_metrics.loc[model_metrics['model'].eq('article_count_spline'), 'incremental_r_squared_vs_controls'].iloc[0]:.3f}.
- Leave-one-out RMSE (lower is better): controls only = {model_metrics.loc[model_metrics['model'].eq('controls_only'), 'loocv_rmse_log1p_absolute_error'].iloc[0]:.3f}; linear = {model_metrics.loc[model_metrics['model'].eq('log_linear_article_count'), 'loocv_rmse_log1p_absolute_error'].iloc[0]:.3f}; spline = {model_metrics.loc[model_metrics['model'].eq('article_count_spline'), 'loocv_rmse_log1p_absolute_error'].iloc[0]:.3f}.

At the pre-specified 0.05 level, the article-count coefficient is not statistically significant (`p = {linear_test['hc3_robust_p_value']:.3f}`). These data therefore do not provide evidence of an adjusted article-count association. There is also no evidence that allowing a nonlinear relationship changes the conclusion. This does not prove that the association is zero; the sample contains only 44 CoCs and the article-count measure has known location-relevance errors.

## Collinearity diagnostics

- Article count VIF: {article_vif:.2f}
- Population VIF: {population_vif:.2f}
- PIT total VIF: {pit_vif:.2f}

Population and PIT total are strongly related, which widens uncertainty but does not invalidate the adjusted model. The GDELT measure counts any assigned California location mention, not necessarily the primary location of the homelessness discussion.
"""
    args.report.write_text(report)

    print(report)
    print(f"Analysis data: {args.analysis_data}")
    print(f"Model metrics: {args.model_metrics}")
    print(f"Tests: {args.tests}")
    print(f"Report: {args.report}")


if __name__ == "__main__":
    main()
