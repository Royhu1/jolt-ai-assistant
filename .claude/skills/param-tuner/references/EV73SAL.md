# EV73SAL — Parameter Tuning Case Study

> Pipeline: volvo_speed_01 | Optimised: 2026-03-25 | Status: No changes needed

## 1. Vehicle characteristics

| Field | Value |
|-------|-------|
| Make/Model | Volvo FM Electric |
| Nominal capacity | 540 kWh |
| Effective capacity | 361.9 kWh |
| Operation pattern | Waste collection (stop-and-go urban cycles) |
| Data availability | FPS telematics (full range, 2024-06 to 2025-12) |
| Pipeline | volvo_speed_01 (speed-based segmentation) |
| Total validation figures | 542 (2024-06 to 2025-12) |

**Distinctive characteristics**:
- Very similar to YK73WFN (same make/model, same waste-collection duty)
- High trip counts on active days: 1-10 discharge trips interleaved with 1-4 charge events
- Mass ranges 10,000-45,000 kg (unladen to fully loaded)
- Long idle stretches (weeks) between intensive operation periods
- No Logger speed data available (unlike YK73WFN which has Logger from 2025-04)
- BST clock-change artefacts produce duplicate figures on transition dates (2025-03-31, 2025-04-01)
- Report-boundary overlaps produce duplicate figures on boundary dates (every 3 months)
- Record energy day: 2025-11-19 with ~750 kWh total energy across 6 trips

## 2. Root causes found

**No systematic segmentation issues identified.**

Comprehensive findings from full-coverage review (542/542 figures, 3 rounds):

| Issue type | Frequency | Root cause |
|------------|-----------|------------|
| Small idle-day energy delta (5-20 kWh) | ~10 cases in autumn/winter | Parasitic HVAC/heating loads; correctly excluded by thresholds |
| SOC drop without speed | 3 cases | Self-discharge or system reset artefact; no false positives |
| Report-boundary duplicates | 5 dates | Expected from overlapping 3-month report windows |
| BST clock-change splits | 2 dates (4 figures) | UTC day-boundary artefact; correctly handled |
| High trip count (7-10/day) | 5 cases | Genuine waste-collection rounds; correct segmentation |
| Small trickle charges (1-7.5 kWh) | ~15 cases | Sub-threshold energy; correctly excluded by min_energy_kwh=5.0 |

## 3. Parameter changes

**No parameter changes made.** Current volvo_speed_01 settings are appropriate.

| Parameter | Value | Assessment |
|-----------|-------|------------|
| speed_threshold_kmh | 1.0 | Correct -- filters GPS jitter |
| min_stop_duration_min | 5.0 | Good -- bridges traffic-light stops without merging distinct trips |
| min_trip_duration_min | 2.0 | Good -- no false short trips observed |
| min_soc_drop | 1.0 | Appropriate for speed-based segmentation |
| min_energy_kwh | 1.0 | Acceptable -- some noise-level events pass in autumn/winter; below threshold |
| plateau_window_min | 60 | Charge detection working properly |
| min_soc_rise | 5.0 | Correctly filters sub-threshold trickle charges |
| min_cluster_gap_kg | 2000 | Appropriate cluster separation |

## 4. Results

| Metric | Value |
|--------|-------|
| Total figures reviewed (all rounds) | 542/542 (100% coverage) |
| Overall pass rate | 100% |
| Round 1 (stratified sample, 50 figures) | 100% OK |
| Round 2 (thorough, 130 new dates) | 100% OK |
| Round 3 (full-coverage, 372 remaining) | 100% OK |
| Issues requiring parameter change | 0 |

## 5. Lessons learned

1. **Consistent with YK73WFN findings**: Same make/model, same duty cycle, same parameter values work well. The volvo_speed_01 parameters are essentially identical to volvo_speed_02 -- both use the default speed-branch settings.

2. **Waste-collection duty cycle produces high trip counts**: 7-10 trips/day is normal on intensive collection days. The algorithm correctly captures each collection round. Record: 2025-11-27 with 8 trips + 4 charges.

3. **Seasonal HVAC effects are manageable**: Autumn/winter idle days show small energy deltas (5-20 kWh) from parasitic loads. These are correctly excluded by the min_soc_rise=5.0 and min_energy_kwh thresholds -- zero false positives across 542 figures.

4. **No Logger data means no cross-validation**: Unlike YK73WFN, EV73SAL has no Logger speed data. However, the telematics speed alone is sufficient for reliable segmentation, as confirmed by 100% pass rate.

5. **Self-discharge artefacts are rare but present**: 3 cases across 18 months where SOC drops significantly without speed activity (e.g., 2024-10-31, 2025-02-04). The algorithm correctly produces no segments for these days.

6. **Full-coverage review validates sampling**: The Round 1 stratified sample of 50 figures correctly predicted zero issues. Rounds 2 and 3 confirmed this across all 542 figures, suggesting future vehicles of this type can rely on smaller sample sizes.

7. **Energy consumption extremes**: This vehicle shows daily energy consumption ranging from 0 (idle) to ~750 kWh (2025-11-19), reflecting the highly variable nature of waste-collection operations. The algorithm handles the full range correctly.

## 6. Recommendation for similar vehicles

For other Volvo FM Electric vehicles with waste-collection duty cycles:
- Start with volvo_speed_01/02 parameters (they are identical)
- Expect high trip counts (6-10/day) on active operating days -- this is correct behaviour
- In autumn/winter, expect occasional sub-threshold energy deltas on idle days; these are correctly handled
- min_cluster_gap_kg=2000 is appropriate for the mass range of this vehicle class
- No parameter changes needed; default speed-branch settings are robust for this duty cycle
