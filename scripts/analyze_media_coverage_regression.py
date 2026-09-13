#!/usr/bin/env python3
"""Run the incremental F-test presented on the research website.

The analysis compares a population-and-PIT control model with the same model
plus GDELT article count. All continuous variables are log transformed. This
is an associational analysis and does not identify a causal effect.
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
        "--summary", type=Path,
        default=ROOT / "data/processed/ca_coc_summary_2024.csv",
    )
    parser.add_argument(
        "--article-counts", type=Path,
        default=ROOT / "data/processed/gdelt_gkg_article_counts_by_coc_2024.csv",
    )
    parser.add_argument(
        "--analysis-data", type=Path,
        default=ROOT / "data/processed/coc_media_regression_data_2024.csv",
    )
    parser.add_argument(
        "--model-metrics", type=Path,
        default=ROOT / "data/processed/coc_media_regression_model_metrics_2024.csv",
    )
    parser.add_argument(
        "--tests", type=Path,
        default=ROOT / "data/processed/coc_media_regression_tests_2024.csv",
    )
    parser.add_argument(
        "--report", type=Path,
        default=ROOT / "data/processed/coc_media_regression_report_2024.md",
    )
    return parser.parse_args()


def fit_ols(matrix: np.ndarray, outcome: np.ndarray) -> dict[str, object]:
    coefficients = np.linalg.lstsq(matrix, outcome, rcond=None)[0]
    residuals = outcome - matrix @ coefficients
    rss = float(residuals @ residuals)
    total_ss = float(np.sum((outcome - outcome.mean()) ** 2))
    return {
        "coefficients": coefficients,
        "rss": rss,
        "r_squared": 1.0 - rss / total_ss,
        "n": len(outcome),
        "parameters": matrix.shape[1],
    }


def incremental_f_test(
    reduced: dict[str, object], full: dict[str, object]
) -> tuple[float, float, int, int]:
    numerator_df = int(full["parameters"]) - int(reduced["parameters"])
    denominator_df = int(full["n"]) - int(full["parameters"])
    statistic = (
        (float(reduced["rss"]) - float(full["rss"])) / numerator_df
    ) / (float(full["rss"]) / denominator_df)
    p_value = float(stats.f.sf(statistic, numerator_df, denominator_df))
    return statistic, p_value, numerator_df, denominator_df


def signed_term(coefficient: float, variable: str) -> str:
    operator = "+" if coefficient >= 0 else "-"
    return f" {operator} {abs(coefficient):.3f} {variable}"


def main() -> None:
    args = parse_args()
    summary = pd.read_csv(args.summary)
    counts = pd.read_csv(args.article_counts)
    data = summary.merge(
        counts[["coc_number", "article_count"]],
        on="coc_number", how="inner", validate="one_to_one",
    )
    if len(data) != 44:
        raise RuntimeError(f"Expected 44 matched CoCs, found {len(data)}")

    positive_columns = ["total_population_2024", "pit_total_2024", "article_count"]
    if (data[positive_columns] <= 0).any().any():
        raise RuntimeError("Population, PIT totals, and article counts must be positive")

    data["absolute_percent_error"] = data["percent_error"].abs()
    data["log1p_absolute_percent_error"] = np.log1p(data["absolute_percent_error"])
    data["log1p_article_count"] = np.log1p(data["article_count"])
    data["log_population"] = np.log(data["total_population_2024"])
    data["log_pit_total"] = np.log(data["pit_total_2024"])

    outcome = data["log1p_absolute_percent_error"].to_numpy()
    controls = np.column_stack([
        np.ones(len(data)), data["log_population"], data["log_pit_total"],
    ])
    full_matrix = np.column_stack([controls, data["log1p_article_count"]])
    fits = {
        "population_and_pit": fit_ols(controls, outcome),
        "population_pit_and_articles": fit_ols(full_matrix, outcome),
    }

    reduced = fits["population_and_pit"]
    full = fits["population_pit_and_articles"]
    reduced_r_squared = float(reduced["r_squared"])
    full_r_squared = float(full["r_squared"])
    r_squared_change = full_r_squared - reduced_r_squared
    f_statistic, p_value, numerator_df, denominator_df = incremental_f_test(
        reduced, full
    )

    model_rows = []
    for name, fit in fits.items():
        coefficients = np.asarray(fit["coefficients"])
        model_rows.append({
            "model": name,
            "n": fit["n"],
            "parameters": fit["parameters"],
            "r_squared": fit["r_squared"],
            "change_in_r_squared_vs_population_and_pit": (
                float(fit["r_squared"]) - reduced_r_squared
            ),
            "intercept": coefficients[0],
            "log_population_coefficient": coefficients[1],
            "log_pit_total_coefficient": coefficients[2],
            "log1p_article_count_coefficient": (
                coefficients[3] if len(coefficients) == 4 else 0.0
            ),
        })
    model_metrics = pd.DataFrame(model_rows)

    tests = pd.DataFrame([{
        "test": "incremental_f_test_for_adding_article_count",
        "reduced_model": "population_and_pit",
        "full_model": "population_pit_and_articles",
        "n": len(data),
        "reduced_r_squared": reduced_r_squared,
        "full_r_squared": full_r_squared,
        "change_in_r_squared": r_squared_change,
        "numerator_df": numerator_df,
        "denominator_df": denominator_df,
        "f_statistic": f_statistic,
        "p_value": p_value,
    }])

    for path in [args.analysis_data, args.model_metrics, args.tests, args.report]:
        path.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(args.analysis_data, index=False)
    model_metrics.to_csv(args.model_metrics, index=False)
    tests.to_csv(args.tests, index=False)

    control_coefficients = np.asarray(reduced["coefficients"])
    full_coefficients = np.asarray(full["coefficients"])
    control_equation = (
        f"log(1 + Absolute % Error) = {control_coefficients[0]:.3f}"
        + signed_term(control_coefficients[1], "log(population)")
        + signed_term(control_coefficients[2], "log(actual PIT count)")
    )
    full_equation = (
        f"log(1 + Absolute % Error) = {full_coefficients[0]:.3f}"
        + signed_term(full_coefficients[1], "log(population)")
        + signed_term(full_coefficients[2], "log(actual PIT count)")
        + signed_term(full_coefficients[3], "log(1 + article count)")
    )

    report = f"""# Media coverage regression — 2024 California CoCs

## Question

Is GDELT article count associated with the absolute percentage error of the blind AI estimate after accounting for CoC population and the actual PIT count?

This is an associational test, not a causal estimate.

## Test

- Observations: {len(data)} California CoCs.
- Outcome: `log(1 + absolute percentage error)`.
- Controls: `log(population)` and `log(actual PIT total)`.
- Added variable: `log(1 + distinct GDELT article count)`.
- Method: incremental F-test comparing two nested linear regression models.

## Models shown on the website

Population and PIT only:

`{control_equation}`

Population, PIT, and articles:

`{full_equation}`

## Results shown on the website

- Population-and-PIT model R²: **{reduced_r_squared:.4f}**.
- Population-PIT-and-articles model R²: **{full_r_squared:.4f}**.
- Change in R²: **{r_squared_change:.4f}**.
- Incremental test: **F({numerator_df}, {denominator_df}) = {f_statistic:.3f}, p = {p_value:.3f}**.

Adding article count raised R² by only {r_squared_change:.4f}. If article count had no additional linear association with error, an F-statistic at least as large as {f_statistic:.3f} would occur about {p_value * 100:.1f}% of the time under repeated sampling. The result does not provide convincing evidence that article count improves the model after population and PIT count are included. It does not prove that the association is exactly zero.

The GDELT measure counts assigned California location mentions, not necessarily the primary location of each article's homelessness discussion.
"""
    args.report.write_text(report)

    print(report)
    print(f"Analysis data: {args.analysis_data}")
    print(f"Model metrics: {args.model_metrics}")
    print(f"Tests: {args.tests}")
    print(f"Report: {args.report}")


if __name__ == "__main__":
    main()
