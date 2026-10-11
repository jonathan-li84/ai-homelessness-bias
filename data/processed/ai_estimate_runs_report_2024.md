# Geographic AI estimation error — 50 successful API runs

How do the accuracy, direction, and consistency of AI homelessness estimates vary across California CoCs?

Gemini API (gemini-3.8-flash as identified in batch 1): 50 successful runs, 2,200 estimates, 44 CoCs. Selected chronologically: 17 successful runs from batch 1, 19 from batch 2 and runs 1–14 from batch 3. Four failed requests and the final six successful requests were excluded. Original batch/request numbers are preserved.

Mean absolute percentage error, averaged equally across CoCs and runs: 12.1360%.

coc_category,coc_count,mean_population,mean_actual_pit,mean_homeless_per_10000,mean_ai_estimate,mean_signed_error_people,mean_signed_percent_error,mean_absolute_error_people,mean_absolute_percent_error,mean_overestimation_rate,mean_underestimation_rate,mean_min_estimate,mean_max_estimate,mean_estimate_range_people,mean_estimate_range_percent,mean_estimate_sd,mean_normalized_sd_percent,mean_article_count
Major City,9,2315194.3333333335,14104.222222222223,56.03333333333333,14052.977777777776,-51.24444444444444,-1.9592800612785115,224.25333333333333,3.269259970628121,32.0,27.555555555555557,13801.555555555555,14587.888888888889,786.3333333333334,5.439427009478798,199.6181329275722,1.0460757595856833,1779.3333333333333
Urban,5,357323.4,1205.0,32.04,1211.544,6.544000000000002,10.957549202737347,128.552,17.57211949516094,49.2,25.2,1015.0,1578.2,563.2,51.525130766859185,132.5734003563528,10.12718389835506,303.0
Suburban,19,785177.0,2232.3684210526317,37.5,2128.478947368421,-103.88947368421051,-0.5488864766457461,156.83263157894734,10.79530833471638,27.789473684210527,47.89473684210526,1957.0,2266.842105263158,309.8421052631579,14.723579923480692,106.0849778477167,4.250841976960338,152.47368421052633
Rural,11,158695.27272727274,1064.1818181818182,64.47272727272728,930.0527272727272,-134.1290909090909,-1.8083510399908733,163.22727272727272,19.235253364573797,24.727272727272727,74.72727272727273,773.1818181818181,1086.090909090909,312.90909090909093,37.37221036527837,76.65566447249951,9.081415164328783,66.27272727272727

Signed errors describe direction; absolute errors describe inaccuracy. Numerical error describes people added or missed; percentage error describes error relative to actual PIT. Ranges summarize the observed 50 responses, not confidence intervals. Repeated responses are not additional independent geographic observations. Exact API prompt, settings and generation dates were not supplied.

The media regression uses mean absolute percentage error across these 50 runs. See coc_media_regression_report_2024.md for current exploratory results; it does not identify causation.
