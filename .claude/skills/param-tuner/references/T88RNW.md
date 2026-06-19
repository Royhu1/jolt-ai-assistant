# T88RNW — Parameter Tuning Case Study

> Pipeline: renault_speed | Optimised: 2026-03-26 | Status: No changes needed

## 1. Vehicle characteristics

| Field | Value |
|-------|-------|
| Make/Model | Renault E-Tech D Wide |
| Nominal capacity | 211 kWh |
| Effective capacity | (not separately configured; uses nominal) |
| Operation pattern | Urban city delivery (Mon-Fri, 8-17 discharge segments/day) |
| Data availability | FPS telematics (full range, 2024-06-11 to 2026-03-21); no Logger data |
| Pipeline | renault_speed (speed-based segmentation) |
| Total validation figures | 643 (636 unique dates + 7 report boundary duplicates) |
| Data gap | 2025-05-02 to 2025-05-14 (13 days, telematics outage) |

**Distinctive characteristics**:
- Highly consistent Mon-Fri urban delivery pattern with 8-17 discharge segments per active day
- Saturday = charge-only day (60-200 kWh); Sunday = idle (no activity)
- Overnight charging pattern: charge typically completes before midnight, creating day-boundary artefacts where the driving day shows discharge-only
- Deep discharge common: SOC regularly drops to 0-5% on heavy delivery days
- No vehicle mass data reported by telematics (`gross_combination_vehicle_weight` column empty)
- Mid-day rapid charges occur occasionally (30-64 kWh), correctly detected
- Auxiliary/hotel loads produce 1-5 kWh/day cumulative energy on idle days
- No BST clock-change artefacts (telematics reports in UTC)

## 2. Root causes found

**No systematic segmentation issues identified.**

Comprehensive findings from 3-round full-coverage review (643/643 figures):

| Issue type | Frequency | Root cause |
|------------|-----------|------------|
| Missing charge (day-boundary display) | ~95 days | Overnight charge before midnight on prev day; display artefact, not algorithm |
| Idle/auxiliary energy on weekends | ~15 days | Hotel/HVAC loads; 1-5 kWh/day; correctly no segments produced |
| Report boundary duplicates | 7 dates | Overlapping 3-month report windows; cosmetic duplication |
| Empty mass panel | All 643 figs | Vehicle telematics doesn't report mass; data availability issue |
| Sparse data fragment | 2 instances | Telematics logger restart; ~3 hrs of AC-DC data only; correctly no segments |
| Data gap (no figures) | 13 days | 2025-05-02 to 2025-05-14; telematics outage |

## 3. Parameter changes

**No parameter changes made.** Current renault_speed settings are optimal for this vehicle.

| Parameter | Value | Assessment |
|-----------|-------|------------|
| speed_threshold_kmh | 1.0 | Correct — filters GPS jitter for city delivery |
| min_stop_duration_min | 5.0 | Good — bridges short delivery stops without merging distinct trips |
| min_trip_duration_min | 2.0 | Good — correctly includes genuine short trips (e.g., 2024-08-30, 2025-07-01) |
| min_soc_drop | 1.0 | Appropriate for speed-based segmentation with 211 kWh battery |
| min_energy_kwh | 1.0 | Correct — captures short delivery runs while filtering noise |
| plateau_window_min | 60 | Charge detection working properly for overnight and mid-day charges |
| min_soc_rise | 5.0 | Correctly filters sub-threshold parasitic fluctuations |
| min_energy_kwh (charge) | 5.0 | Appropriate — all genuine charges are 30+ kWh |

## 4. Results

| Metric | Value |
|--------|-------|
| Total figures reviewed (all rounds) | 643/643 (100% coverage) |
| Overall OK rate | 79% (508 OK, 135 Issue) |
| Issues attributable to algorithm | 0 |
| Issues attributable to display/data | 135 (100% of issues) |
| Round 1 (stratified sample, 92 figures) | 78% OK |
| Round 2 (full-range thorough, 643 figures) | 79% OK |
| Round 3 (confirmation review, 41 figures inspected) | Confirmed all Round 2 findings |
| Issues requiring parameter change | 0 |

## 5. Lessons learned

1. **Day-boundary charge artefact is the dominant "issue"**: ~70% of all flagged issues are discharge-only days where the charge occurred on the previous calendar day (typically overnight before midnight). This is inherent to per-day validation figures and cannot be fixed by parameter tuning. A cross-day charge look-back in the validation figure generator would eliminate this as a concern.

2. **Renault E-Tech D Wide has clean telematics**: Unlike some Volvo vehicles, this Renault reports in UTC consistently with no BST clock-change artefacts. Speed data is reliable, and SOC reporting is smooth with no spurious jumps or self-discharge events.

3. **No mass data available**: The `gross_combination_vehicle_weight` field is empty across 21 months of data. Mass clustering validation is impossible for this vehicle. This is a telematics limitation specific to this make/model.

4. **211 kWh battery with deep discharge cycles**: The vehicle regularly discharges from ~95% to 0-5% SOC on heavy delivery days (up to 17 discharge segments). The algorithm handles these extreme cycles correctly.

5. **Mid-day rapid charges correctly detected**: Occasional mid-day charges (30-64 kWh) between morning and afternoon delivery rounds are correctly identified as separate charge events, with proper SOC rise visible in Panel 1 and energy step in Panel 2.

6. **Auxiliary loads on idle days are negligible**: 1-5 kWh/day from hotel/HVAC loads on weekends/holidays. These never trigger false segment detection due to the `min_energy_kwh=1.0` threshold in combination with zero speed.

7. **Short trip days handled correctly**: Days with only 1 discharge segment (e.g., 2024-08-30, 2025-07-01) are correctly captured. The `min_trip_duration_min=2.0` threshold is low enough to include genuine short depot runs.

8. **Round 1 sampling accurately predicted full-range results**: The initial 92-figure stratified sample (78% OK) closely matched the full 643-figure review (79% OK), suggesting future Renault vehicles can rely on smaller sample sizes with confidence.

## 6. Recommendation for similar vehicles

For other Renault E-Tech D Wide vehicles with urban delivery duty cycles:
- Start with `renault_speed` parameters — they are well-tuned out of the box
- Expect ~15-20% of validation figures to show "missing charge" day-boundary artefacts; this is normal and not an algorithm issue
- Expect empty mass panels — Renault telematics does not report vehicle mass
- No parameter changes needed; default renault_speed settings are robust for this duty cycle
- If the vehicle operates with fewer stops per day (long-haul rather than city delivery), consider raising `min_stop_duration_min` to reduce over-segmentation at traffic lights
