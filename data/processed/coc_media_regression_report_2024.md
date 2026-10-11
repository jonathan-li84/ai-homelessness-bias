# Media coverage regression — 2024 California CoCs

## Question

Is GDELT article count associated with the absolute percentage error of the 50-run AI estimates after accounting for CoC population and the actual PIT count?

This is an associational test, not a causal estimate.

## Test

- Observations: 44 California CoCs.
- Outcome: `log(1 + mean absolute percentage error across 50 runs)`.
- Controls: `log(population)` and `log(actual PIT total)`.
- Added variable: `log(1 + distinct GDELT article count)`.
- Method: incremental F-test comparing two nested linear regression models.

## Fitted models

Population and PIT only:

`log(1 + Mean Absolute % Error) = 6.278 - 0.007 log(population) - 0.586 log(actual PIT count)`

Population, PIT, and articles:

`log(1 + Mean Absolute % Error) = 5.797 + 0.045 log(population) - 0.545 log(actual PIT count) - 0.098 log(1 + article count)`

## Results shown on the website

- Population-and-PIT model R²: **0.3250**.
- Population-PIT-and-articles model R²: **0.3304**.
- Change in R²: **0.0054**.
- Incremental test: **F(1, 40) = 0.320, p = 0.575**.

Adding article count raised R² by only 0.0054. If article count had no additional linear association with error, an F-statistic at least as large as 0.320 would occur about 57.5% of the time under repeated sampling. The result does not provide convincing evidence that article count improves the model after population and PIT count are included. It does not prove that the association is exactly zero.

The GDELT measure counts assigned California location mentions, not necessarily the primary location of each article's homelessness discussion.
