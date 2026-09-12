# Media coverage regression — 2024 California CoCs

## Question

Is GDELT article count associated with the absolute percentage error of the blind AI estimate after accounting for CoC population and the actual PIT count?

This is an associational test, not a causal estimate.

## Specification

- Observations: 44 California CoCs.
- Outcome: `log(1 + absolute percentage error)`.
- Exposure: `log(1 + distinct GDELT article count)`.
- Controls: `log(population)` and `log(actual PIT total)`.
- Nonlinearity: three-knot restricted cubic spline with article-count knots at 32.5, 126.0, and 1165.3.
- Inference: HC3 heteroskedasticity-robust Wald tests. The primary test evaluates whether the adjusted log-linear article-count coefficient equals zero.

## Results

- Primary log-linear article-count test: coefficient = 0.063, HC3 95% CI [-0.263, 0.390], p = 0.698.
- Overall spline association: HC3 p = 0.895.
- Evidence of nonlinearity beyond a straight line: HC3 p = 0.696.
- Interpreted approximately, doubling article count corresponds to a 4.5% change in `(1 + absolute percentage error)`; HC3 95% CI [-16.7%, 31.0%].
- Incremental R² over population and PIT controls: linear = 0.002; spline = 0.006.
- Leave-one-out RMSE (lower is better): controls only = 1.039; linear = 1.060; spline = 1.099.

At the pre-specified 0.05 level, the article-count coefficient is not statistically significant (`p = 0.698`). These data therefore do not provide evidence of an adjusted article-count association. There is also no evidence that allowing a nonlinear relationship changes the conclusion. This does not prove that the association is zero; the sample contains only 44 CoCs and the article-count measure has known location-relevance errors.

## Collinearity diagnostics

- Article count VIF: 2.37
- Population VIF: 5.83
- PIT total VIF: 5.68

Population and PIT total are strongly related, which widens uncertainty but does not invalidate the adjusted model. The GDELT measure counts any assigned California location mention, not necessarily the primary location of the homelessness discussion.
