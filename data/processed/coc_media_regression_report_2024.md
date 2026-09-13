# Media coverage regression — 2024 California CoCs

## Question

Is GDELT article count associated with the absolute percentage error of the blind AI estimate after accounting for CoC population and the actual PIT count?

This is an associational test, not a causal estimate.

## Test

- Observations: 44 California CoCs.
- Outcome: `log(1 + absolute percentage error)`.
- Controls: `log(population)` and `log(actual PIT total)`.
- Added variable: `log(1 + distinct GDELT article count)`.
- Method: incremental F-test comparing two nested linear regression models.

## Models shown on the website

Population and PIT only:

`log(1 + Absolute % Error) = 6.315 + 0.161 log(population) - 0.790 log(actual PIT count)`

Population, PIT, and articles:

`log(1 + Absolute % Error) = 6.625 + 0.128 log(population) - 0.817 log(actual PIT count) + 0.063 log(1 + article count)`

## Results shown on the website

- Population-and-PIT model R²: **0.4079**.
- Population-PIT-and-articles model R²: **0.4102**.
- Change in R²: **0.0023**.
- Incremental test: **F(1, 40) = 0.156, p = 0.695**.

Adding article count raised R² by only 0.0023. If article count had no additional linear association with error, an F-statistic at least as large as 0.156 would occur about 69.5% of the time under repeated sampling. The result does not provide convincing evidence that article count improves the model after population and PIT count are included. It does not prove that the association is exactly zero.

The GDELT measure counts assigned California location mentions, not necessarily the primary location of each article's homelessness discussion.
