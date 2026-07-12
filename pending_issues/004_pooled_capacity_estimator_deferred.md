# 004 — Switch monthly capacity/SOH series to a ΔSOC-weighted estimator (pooled ratio / origin-OLS, deferred)

- **Status**: OPEN (deferred by decision 2026-07-08 — the hard |ΔSOC| ≥ 10 % threshold is
  good enough for now; this records the demonstrated-better estimator as the next step)
- **Date found**: 2026-07-08 (estimator precision study in
  `data_analysis_workspace/effective_capacity_trend/`)
- **Owner**: unassigned (analysis-side — `effective_capacity_trend` sub-project owns the
  change; no `src/jolt_toolkit/` code involved)
- **Priority**: low-medium (quality improvement to an internal analysis; no partner-facing
  number currently depends on the monthly capacity series)

## Summary

The effective-capacity trend analysis currently estimates monthly capacity/SOH as the
**mean of per-leg ratios** `|ΔE| / (|ΔSOC|/100)` over legs with `|ΔSOC| >= 10 %`. An
empirical study (`scripts/compare_capacity_estimators.py`,
`results/estimator_comparison.csv`) showed two ΔSOC-weighted estimators are more precise
on unthresholded data and would let the monthly series keep every measured leg instead of
discarding the shallow ones:

- **Pooled ratio** `Σ|ΔE| / Σ(|ΔSOC|/100)` per month — algebraically a ΔSOC-weighted mean
  of the per-leg capacities, identical to merging the month's legs into one long
  charge-to-charge window;
- **Through-origin OLS slope** of `|ΔE|` on `|ΔSOC|/100` — ΔSOC²-weighting, deep legs
  dominate further.

Measured on the ≥ 5 % extraction by month-to-month volatility (`std(diff)/√2`; true
capacity moves well under 1 %/month, so series jitter ≈ estimation noise): pooled ratio
−8 % median (−40 % best), origin-OLS −9 % median (−51 % best), versus only −3 % for the
hard ≥ 10 % threshold — and both weighted estimators keep 100 % of the measured legs
(the threshold discards 5 to 75 % of discharge legs per vehicle).

## Why deferred (decision context)

The ≥ 10 % hard threshold was adopted on 2026-07-08 because it also removes the
shallow-leg Jensen (upward) bias — discharge means dropped 2 to 24 kWh — and it keeps
every plotted scatter point individually meaningful. On the ≥ 10 % data the weighted
estimators add no further precision (−1 to +3 %): once shallow legs are gone, leg-to-leg
physical variation (temperature, power, duty) dominates over SOC quantisation noise. So
the weighted estimator matters when one wants the shallow legs' information back in the
monthly *series* without re-admitting their noise/bias into the *scatter figures*.

## Suggested fix (when picked up)

1. In `plot_effective_capacity_trend.py`, compute the binned/monthly SOH series (the
   `soh_binned_vs_*` figures) with the **pooled ratio** per bin instead of the per-leg
   mean, sourced from a lower-threshold extraction (≥ 5 %, or all measured legs).
2. Error bars: **bootstrap over legs** (resample the bin's legs with replacement,
   recompute the pooled ratio, take the std / 2.5–97.5 % interval). Prefer a day-block
   bootstrap — legs within a day are correlated. Note this changes the error-bar meaning
   from "leg spread (±1 std)" to "uncertainty of the bin value" — relabel the legend.
3. Keep the ≥ 10 % per-leg threshold for all scatter figures (individual points must be
   meaningful) and for `analyze_degradation.py` unless its regressions are also moved to
   the pooled monthly series.
4. Re-run `compare_capacity_estimators.py` afterwards as the regression check.

## References

- `data_analysis_workspace/effective_capacity_trend/report_degradation_analysis.md`
  §2.6 (threshold/estimator sensitivity) and §5 recommendation 2.
- `data_analysis_workspace/effective_capacity_trend/scripts/compare_capacity_estimators.py`
  + `results/estimator_comparison.csv`.
- Changelog 2026-07-08 entries in `changelogs/changelog_20260706_20260712.md`.
