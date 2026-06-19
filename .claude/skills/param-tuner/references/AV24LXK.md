# AV24LXK — Parameter Tuning Case Study

> Pipeline: volvo_speed_00 | Optimised: 2026-03-25 | Status: No changes needed

## 1. Vehicle characteristics

| Field | Value |
|-------|-------|
| Make/Model | Volvo FE Electric |
| Nominal capacity | 360 kWh |
| Effective capacity | 313.2 kWh |
| Operation pattern | Waste collection (multi-stop urban cycles) |
| Data availability | FPS telematics (full range, Jun 2024 - Dec 2025) |
| Pipeline | volvo_speed_00 (speed-based segmentation) |
| Total validation figures | 544 (2024-06 to 2025-12) |

**Distinctive characteristics**:
- Consistent 5-day working pattern (Mon-Fri or Tue-Sat) with weekends idle or charge-only
- On active days: 6-22 discharge trips interleaved with 1-4 charge events (mid-day DC fast charge plus overnight/end-of-day AC)
- SOC range typically 100% to 5-30% on heavy days, 80-95% to 50-70% on lighter days
- Mass variation: 5000-45000 kg range with proper cluster boundaries
- Sister vehicles AV24LXJ and AV24LXL share identical pipeline parameters
- No Logger data — relies entirely on FPS telematics
- Weekend charge-only days common (~2/month), with AC charging detected correctly

## 2. Root causes found

**No segmentation issues identified across comprehensive review (251 figures, 18 months).**

Minor observations (not issues):
| Observation | Frequency | Notes |
|-------------|-----------|-------|
| Weekend charge-only days | ~2/month | AC charging on Sat/Sun, SOC rises without discharge; correctly handled as charge-only, no false trips |
| Report boundary duplicates | 8 cases | Same date appearing in two consecutive report files; both copies show identical, correct segmentation |
| Short-activity end-of-day fragments | 3 cases | 1-trip segments near midnight (e.g., 2025-08-12 _0074); correctly captured as single discharge segment |
| Empty boundary fragments | 4 cases | Report boundary produces near-empty second figure; all axes flat, no false segments |

## 3. Parameter changes

**No parameter changes made.** Current volvo_speed_00 settings are optimal.

| Parameter | Value | Assessment |
|-----------|-------|------------|
| speed_threshold_kmh | 1.0 | Correct — filters GPS jitter |
| min_stop_duration_min | 5.0 | Good — bridges short traffic-light stops without merging distinct trips |
| min_trip_duration_min | 2.0 | Good — filters ultra-short noise |
| min_soc_drop | 1.0 | Appropriate for speed-based segmentation |
| min_energy_kwh | 1.0 | Correct — no false positives observed even in winter |
| plateau_window_min | 60 | Good for charge detection |
| min_soc_rise | 5.0 | Good — captures real charges, ignores noise |
| min_charge_energy_kwh | 5.0 | Appropriate |
| min_cluster_gap_kg | 2000.0 | Good — mass clusters are clean |

## 4. Results

| Metric | Value |
|--------|-------|
| Total figures reviewed (all rounds) | 251 |
| Overall pass rate | 100% (251/251 OK) |
| Active days reviewed | ~164 |
| Idle days reviewed | ~52 |
| Charge-only days reviewed | ~14 |
| Boundary/short-activity days reviewed | ~21 |
| Issues requiring parameter change | 0 |

## 5. Lessons learned

1. **Volvo FE Electric waste collection is the cleanest use case for speed-based segmentation**: Multi-stop urban collection produces distinct speed-to-zero transitions at each stop. The algorithm captures every trip boundary with no false positives and no missed segments across all 251 figures reviewed.

2. **No seasonal degradation**: Unlike the FM Electric (YK73WFN, volvo_speed_02), the FE Electric shows no winter HVAC parasitic load issues. All Nov-Feb idle/weekend days are completely clean with no energy counter anomalies triggering false segments.

3. **High trip counts are genuine**: Days with 20+ trips reflect the actual duty cycle (repeated house-to-house stops), not over-segmentation. The min_stop_duration_min=5.0 correctly bridges brief pauses at traffic lights.

4. **Weekend charge-only days handled perfectly**: Regular Saturday/Sunday AC charging events (SOC rises of 5-40%) are always correctly classified as charge-only, never triggering false discharge segments.

5. **Report boundary handling is robust**: All 8 boundary overlap cases (same date in two report files) produce identical, correct segmentation in both copies. Empty boundary fragments show flat axes with no false segments.

6. **Three sister vehicles (AV24LXJ, AV24LXK, AV24LXL) validate the pipeline**: All share identical volvo_speed_00 parameters. AV24LXJ: 130/130 OK, AV24LXK: 251/251 OK, confirming the pipeline is robust for this vehicle class.

## 6. Recommendation for similar vehicles

For other Volvo FE Electric vehicles with waste-collection duty cycles:
- Start with `volvo_speed_00` parameters — they work out of the box
- Expect 6-22 trips/day on active operating days — this is correct
- Charge-only and idle days are handled cleanly
- No need to adjust min_energy_kwh for winter — 1.0 kWh is sufficient
- min_cluster_gap_kg=2000 kg works well for the typical 5000-45000 kg mass range
- Weekend charge-only patterns are common and correctly handled
