# AV24LXJ — Parameter Tuning Case Study

> Pipeline: volvo_speed_00 | Optimised: 2026-03-25 | Status: No changes needed

## 1. Vehicle characteristics

| Field | Value |
|-------|-------|
| Make/Model | Volvo FE Electric |
| Nominal capacity | 360 kWh |
| Effective capacity | 309.4 kWh |
| Operation pattern | Waste collection (multi-stop urban cycles) |
| Data availability | FPS telematics (full range, Jun 2024 - Dec 2025) |
| Pipeline | volvo_speed_00 (speed-based segmentation) |
| Total validation figures | 536 (2024-06 to 2025-12) |

**Distinctive characteristics**:
- Consistent 5-day (Mon-Fri or Tue-Sat) working pattern with weekends idle
- On active days: 6-23 discharge trips interleaved with 1-4 charge events (mid-day DC fast charge plus overnight/end-of-day AC)
- SOC range typically 100% to 5-35% on heavy days, 80-95% to 50-70% on lighter days
- Mass variation: 5000-50000 kg range with proper cluster boundaries
- Sister vehicles AV24LXK and AV24LXL share identical pipeline parameters
- No Logger data — relies entirely on FPS telematics

## 2. Root causes found

**No segmentation issues identified across comprehensive review (130 figures, 18 months).**

Minor observations (not issues):
| Observation | Frequency | Notes |
|-------------|-----------|-------|
| Energy counter increments on idle days | 2 cases (Jan/Feb 2025) | ~3-12 kWh energy accumulation without speed; no false trips triggered |
| AC-DC delta on charge-only days | 5 cases | Slow AC charge with SOC near full; correctly identified as charge, no false discharge |
| Nov 2024 idle day with ~1 kWh AC delta | 1 case (Nov 17) | Tiny metering increment, no segment created |

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
| Total figures reviewed (all rounds) | 130 |
| Overall pass rate | 100% (130/130 OK) |
| Active days reviewed | 78 |
| Idle days reviewed | 42 |
| Charge-only days reviewed | 5 |
| Boundary/low-activity days reviewed | 9 |
| Issues requiring parameter change | 0 |

## 5. Lessons learned

1. **Volvo FE Electric waste collection is the cleanest use case for speed-based segmentation**: Multi-stop urban collection produces distinct speed-to-zero transitions at each stop. The algorithm captures every trip boundary with no false positives and no missed segments.

2. **No seasonal degradation**: Unlike the FM Electric (YK73WFN, volvo_speed_02), the FE Electric shows no winter HVAC parasitic load issues. This may be due to the smaller cabin or different heating strategy. All Nov/Dec idle days are completely clean.

3. **High trip counts are genuine**: Days with 20+ trips reflect the actual duty cycle (repeated house-to-house stops), not over-segmentation. The min_stop_duration_min=5.0 correctly bridges brief pauses at traffic lights.

4. **Energy counter anomalies do not create false positives**: Small energy accumulations on otherwise idle days (observed Jan/Feb 2025) are handled correctly — no false discharge segments.

5. **Three sister vehicles (AV24LXJ, AV24LXK, AV24LXL) validate the pipeline**: All three share identical volvo_speed_00 parameters and show 100% pass rates in their respective reviews, confirming the pipeline is robust for this vehicle class.

## 6. Recommendation for similar vehicles

For other Volvo FE Electric vehicles with waste-collection duty cycles:
- Start with `volvo_speed_00` parameters — they work out of the box
- Expect 6-23 trips/day on active operating days — this is correct
- Charge-only and idle days are handled cleanly
- No need to adjust min_energy_kwh for winter — 1.0 kWh is sufficient
- min_cluster_gap_kg=2000 kg works well for the typical 5000-50000 kg mass range
