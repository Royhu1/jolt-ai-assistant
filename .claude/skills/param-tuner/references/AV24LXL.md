# AV24LXL — Parameter Tuning Case Study

> Pipeline: volvo_speed_00 | Optimised: 2026-03-25 | Status: No changes needed

## 1. Vehicle characteristics

| Field | Value |
|-------|-------|
| Make/Model | Volvo FE Electric |
| Nominal capacity | 360 kWh |
| Effective capacity | 300.2 kWh |
| Operation pattern | Waste collection (multi-stop urban cycles) |
| Data availability | FPS telematics (full range, Jun 2024 - Dec 2025) |
| Pipeline | volvo_speed_00 (speed-based segmentation) |
| Total validation figures | 528 (2024-06 to 2025-12) |

**Distinctive characteristics**:
- Consistent 5-day (Mon-Fri or Tue-Sat) working pattern with weekends idle
- On active days: 3-22 discharge trips interleaved with 1-4 charge events (mid-day DC fast charge plus overnight/end-of-day AC)
- SOC range typically 100% to 5-35% on heavy days, 80-95% to 50-70% on lighter days
- Mass variation: 5000-50000 kg range with proper cluster boundaries
- Sister vehicles AV24LXJ and AV24LXK share identical pipeline parameters
- No Logger data -- relies entirely on FPS telematics
- Data-sparse period in Aug 2024 (08-15 to 08-23) with micro energy accumulations but no speed activity

## 2. Root causes found

**No segmentation issues identified across exhaustive 528-figure review (2 rounds).**

Minor observations (not issues):
| Observation | Frequency | Notes |
|-------------|-----------|-------|
| Micro energy accumulation on idle/low-activity days | 6 cases (Aug 2024, Oct 2024, Aug 2025) | 0.3-15 kWh energy step without speed; no false segments triggered |
| Report-period boundary duplicate dates | 5 dates | Both copies consistent, correctly handled |
| Charge-only days (AC only) | 8 cases | Correctly identified, no false discharge segments |

## 3. Parameter changes

**No parameter changes made.** Current volvo_speed_00 settings are optimal.

| Parameter | Value | Assessment |
|-----------|-------|------------|
| speed_threshold_kmh | 1.0 | Correct -- filters GPS jitter |
| min_stop_duration_min | 5.0 | Good -- bridges short traffic-light stops without merging distinct trips |
| min_trip_duration_min | 2.0 | Good -- filters ultra-short noise |
| min_soc_drop | 1.0 | Appropriate for speed-based segmentation |
| min_energy_kwh | 1.0 | Correct -- no false positives even with micro energy anomalies |
| plateau_window_min | 60 | Good for charge detection |
| min_soc_rise | 5.0 | Good -- captures real charges, ignores noise |
| min_charge_energy_kwh | 5.0 | Appropriate |
| min_cluster_gap_kg | 2000.0 | Good -- mass clusters are clean |

## 4. Results

| Metric | Value |
|--------|-------|
| Total figures reviewed (all rounds) | 528 |
| Overall pass rate | 100% (528/528 OK) |
| Active days reviewed | ~350 |
| Idle days reviewed | ~164 |
| Charge-only days reviewed | ~8 |
| Low-activity days reviewed | ~6 |
| Issues requiring parameter change | 0 |

## 5. Lessons learned

1. **Volvo FE Electric waste collection is the cleanest use case for speed-based segmentation**: Multi-stop urban collection produces distinct speed-to-zero transitions at each stop. The algorithm captures every trip boundary with no false positives and no missed segments across 528 figures spanning 18 months.

2. **Data-sparse periods do not create false positives**: The Aug 2024 data gap (08-15 to 08-23) shows micro energy accumulations (0.3-15 kWh) without speed activity. The speed-based branch correctly ignores these because there are no speed-to-zero transitions to trigger segmentation.

3. **No seasonal degradation**: Unlike the FM Electric (YK73WFN, volvo_speed_02), the FE Electric shows no winter HVAC parasitic load issues. All Nov/Dec/Jan/Feb idle days are completely clean.

4. **High trip counts are genuine**: Days with 20+ trips reflect the actual duty cycle (repeated house-to-house stops), not over-segmentation. The min_stop_duration_min=5.0 correctly bridges brief pauses at traffic lights.

5. **Three sister vehicles (AV24LXJ, AV24LXK, AV24LXL) validate the pipeline**: All three share identical volvo_speed_00 parameters and show 100% pass rates in their respective exhaustive reviews, confirming the pipeline is robust for this vehicle class.

6. **Report-period boundary handling is clean**: Duplicate dates from overlapping reporting windows produce consistent results in both copies.

## 6. Recommendation for similar vehicles

For other Volvo FE Electric vehicles with waste-collection duty cycles:
- Start with `volvo_speed_00` parameters -- they work out of the box
- Expect 3-22 trips/day on active operating days -- this is correct
- Charge-only and idle days are handled cleanly
- No need to adjust min_energy_kwh for winter -- 1.0 kWh is sufficient
- Data-sparse periods with micro energy accumulation are safe (no false segments)
- min_cluster_gap_kg=2000 kg works well for the typical 5000-50000 kg mass range
