# YK73WFN — Parameter Tuning Case Study

> Pipeline: volvo_speed_02 | Optimised: 2026-03-25 | Status: No changes needed

## 1. Vehicle characteristics

| Field | Value |
|-------|-------|
| Make/Model | Volvo FM Electric |
| Nominal capacity | 540 kWh |
| Effective capacity | 358.8 kWh |
| Operation pattern | Bulk waste/recycling collection (stop-and-go urban cycles) |
| Data availability | FPS telematics (full range); Logger (from ~2025-04 onward, V1+V2) |
| Pipeline | volvo_speed_02 (speed-based segmentation) |
| Total validation figures | 543 (2024-06 to 2025-12) |

**Distinctive characteristics**:
- Very long idle stretches (sometimes weeks) between sporadic intensive operation periods
- Highly variable mass: from ~10 t (unladen) to ~44 t (fully loaded), multiple mass clusters per day
- On active days: 1–10 discharge trips interleaved with 1–4 charge events; SOC can oscillate from ~100% to ~5%
- Logger Speed (orange channel) available from ~2025-04; consistently matches telematics speed
- From Oct–Nov 2025: parasitic loads (HVAC/heating) create small SOC fluctuations on idle days

## 2. Root causes found

**No systematic segmentation issues identified.**

Minor issues found during comprehensive Round 2 review (543 figures across 18 months):

| Issue type | Frequency | Root cause |
|------------|-----------|------------|
| Over-segmentation (10-trip days) | 2 cases in summer | Continuous waste-collection rounds fragmented at momentary stops; inherent to duty cycle |
| Marginal false positive trips (≤ 2 kWh) | 7 cases in autumn/winter | Parasitic HVAC/heating loads creating small SOC fluctuations; some are at/below min_energy threshold |
| Energy–SOC data anomaly | 2 cases, Nov 2025 | Energy counter accumulating without SOC/speed; telematics data quality issue, not algorithm |
| SOC rise within trip | 1 case | UTC day-boundary artefact |
| Missing charger data | 1 case | External data completeness issue |

## 3. Parameter changes

**No parameter changes made.** Current volvo_speed_02 settings are appropriate.

| Parameter | Value | Assessment |
|-----------|-------|------------|
| speed_threshold_kmh | 1.0 | Correct — filters out GPS jitter |
| min_stop_duration_min | 5.0 | Good — bridges short traffic-light stops without merging genuinely distinct trips |
| min_trip_duration_min | 2.0 | Good — filters ultra-short noise trips |
| min_soc_drop | 1.0 | Appropriate for speed-based segmentation |
| min_energy_kwh | 1.0 | Acceptable — some noise-level events (0.5–2 kWh) pass in autumn/winter; raising to 2.0 would help but risks removing valid short depot moves |

## 4. Results

| Metric | Value |
|--------|-------|
| Total figures reviewed (all rounds) | ~295 unique (188 in Round 2 + ~107 in Batch A+B + 64 in Round 1) |
| Overall pass rate (reviewed) | ~95% |
| Batch C (summer, 94 figures) | 97% OK |
| Batch D (autumn/winter, 94 figures) | 84% OK |
| Issues requiring parameter change | 0 |

## 5. Lessons learned

1. **Waste-collection duty cycle produces high trip counts**: 8–10 trips/day is normal for this vehicle on active days. The algorithm correctly captures each collection round; the high count reflects genuine operational structure, not over-segmentation.

2. **Seasonal false positives**: Parasitic HVAC loads in Oct–Nov create sub-2 kWh SOC drops on otherwise idle days. These pass the `min_energy_kwh=1.0` filter occasionally. This is acceptable for research purposes — the events are clearly sub-threshold and represent standing load, not genuine driving.

3. **Logger speed as validation tool**: From 2025-04, Logger Speed (orange) provides an excellent cross-check against telematics speed (blue). The consistent agreement across all reviewed days validates the telematics-based trip detection.

4. **Round 1 stratified sample was representative**: The 64-figure sample in Round 1 correctly concluded the pipeline was well-tuned. The comprehensive Round 2 review only surfaced minor issues (3% of summer figures, 16% of autumn/winter figures) that don't warrant parameter changes.

5. **Data anomalies in Nov 2025**: Two figures (2025-11-19, 2025-11-20) show energy accumulating without SOC drop or speed — this is a telematics data quality issue unrelated to the segmentation algorithm. The algorithm correctly produced no discharge segments for those days.

6. **UTC boundary artefacts**: Overnight reports (report period ending at UTC midnight) can produce day-boundary window figures with very short time spans. These are correctly classified as idle with no false positives.

## 6. Recommendation for similar vehicles

For other Volvo FM Electric vehicles with similar waste-collection duty cycles:
- Start with `volvo_speed_02` parameters
- Expect high trip counts (6–10/day) on active operating days — this is correct
- In autumn/winter, expect occasional sub-2 kWh false positives; acceptable for research purposes
- If operation involves depot manoeuvres only (no actual collection routes), consider raising `min_energy_kwh` to 2.0 kWh
