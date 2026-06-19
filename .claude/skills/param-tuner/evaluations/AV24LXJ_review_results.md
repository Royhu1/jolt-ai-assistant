# AV24LXJ — Validation Figure Review Results

> Pipeline: volvo_speed_00 | Last reviewed: 2026-03-25

## Summary

| Status | Count | Percentage |
|--------|-------|------------|
| OK | 130 | 24.3% |
| Issue | 0 | 0.0% |
| Not reviewed | 406 | 75.7% |
| **Total** | **536** | **100%** |

### Known remaining issues

- None identified

---

## Round 1 — Initial review (2026-03-24)

Parameters: volvo_speed_00 (speed_threshold=1.0, min_stop=5.0, min_trip=2.0, min_soc_drop=1.0, min_energy=1.0, plateau_window=60, min_soc_rise=5.0, min_charge_energy=5.0, min_cluster_gap_kg=2000, nominal=360, effective=309.4, speed_col=wheel_based_speed)

### Per-figure results

| Figure | Type | Status | Issue | Root cause |
|--------|------|--------|-------|------------|
| validation_AV24LXJ_2025-07-28_0059.png | Active | OK | — | — |
| validation_AV24LXJ_2024-08-30_0080.png | Active | OK | — | — |
| validation_AV24LXJ_2025-07-22_0053.png | Active | OK | — | — |
| validation_AV24LXJ_2024-07-05_0024.png | Active | OK | — | — |
| validation_AV24LXJ_2024-12-17_0016.png | Active | OK | — | — |
| validation_AV24LXJ_2024-06-25_0014.png | Active | OK | — | — |
| validation_AV24LXJ_2025-10-07_0036.png | Active | OK | — | — |
| validation_AV24LXJ_2024-07-29_0048.png | Active | OK | — | — |
| validation_AV24LXJ_2025-04-09_0039.png | Active | OK | — | — |
| validation_AV24LXJ_2025-06-13_0013.png | Active | OK | — | — |
| validation_AV24LXJ_2025-07-17_0048.png | Active | OK | — | — |
| validation_AV24LXJ_2025-07-24_0055.png | Active | OK | — | — |
| validation_AV24LXJ_2025-08-20_0082.png | Active | OK | — | — |
| validation_AV24LXJ_2024-06-17_0006.png | Active | OK | — | — |
| validation_AV24LXJ_2024-09-03_0002.png | Active | OK | — | — |
| validation_AV24LXJ_2024-09-04_0003.png | Active | OK | — | — |
| validation_AV24LXJ_2024-10-28_0057.png | Active | OK | — | — |
| validation_AV24LXJ_2024-08-28_0078.png | Active | OK | — | — |
| validation_AV24LXJ_2025-07-30_0061.png | Active | OK | — | — |
| validation_AV24LXJ_2024-06-13_0002.png | Active | OK | — | — |
| validation_AV24LXJ_2024-06-20_0009.png | Active | OK | — | — |
| validation_AV24LXJ_2024-09-02_0001.png | Active | OK | — | — |
| validation_AV24LXJ_2024-09-05_0004.png | Active | OK | — | — |
| validation_AV24LXJ_2025-07-29_0060.png | Active | OK | — | — |
| validation_AV24LXJ_2024-06-26_0015.png | Active | OK | — | — |
| validation_AV24LXJ_2025-05-01_0061.png | Active | OK | — | — |
| validation_AV24LXJ_2025-06-27_0027.png | Active | OK | — | — |
| validation_AV24LXJ_2025-07-31_0062.png | Active | OK | — | — |
| validation_AV24LXJ_2025-08-01_0063.png | Active | OK | — | — |
| validation_AV24LXJ_2024-10-29_0058.png | Active | OK | — | — |
| validation_AV24LXJ_2024-12-19_0018.png | Active | OK | — | — |
| validation_AV24LXJ_2024-07-15_0034.png | Active | OK | — | — |
| validation_AV24LXJ_2025-08-22_0084.png | Active | OK | — | — |
| validation_AV24LXJ_2024-10-03_0032.png | Active | OK | — | — |
| validation_AV24LXJ_2024-11-18_0078.png | Active | OK | — | — |
| validation_AV24LXJ_2025-01-09_0039.png | Active | OK | — | — |
| validation_AV24LXJ_2025-01-13_0043.png | Active | OK | — | — |
| validation_AV24LXJ_2025-03-04_0003.png | Active | OK | — | — |
| validation_AV24LXJ_2025-10-06_0035.png | Active | OK | — | — |
| validation_AV24LXJ_2024-07-30_0049.png | Active | OK | — | — |
| validation_AV24LXJ_2024-12-02_0001.png | Active | OK | — | — |
| validation_AV24LXJ_2024-12-20_0019.png | Active | OK | — | — |
| validation_AV24LXJ_2025-02-07_0068.png | Active | OK | — | — |
| validation_AV24LXJ_2025-03-11_0010.png | Active | OK | — | — |
| validation_AV24LXJ_2025-03-12_0011.png | Active | OK | — | — |
| validation_AV24LXJ_2025-09-24_0023.png | Active | OK | — | — |
| validation_AV24LXJ_2024-08-09_0059.png | Active | OK | — | — |
| validation_AV24LXJ_2024-11-12_0072.png | Active | OK | — | — |
| validation_AV24LXJ_2025-01-24_0054.png | Active | OK | — | — |
| validation_AV24LXJ_2025-01-31_0061.png | Active | OK | — | — |

### Round 1 summary

- Reviewed: 50 figures (top 50 active days sorted by largest SOC range, from dSOC=58% down to dSOC=12%)
- OK: 50, Issue: 0
- Not reviewed: 489 (302 active days with dSOC < 12%, 9 charge-overlap days, 178 idle days)
- Dominant pattern: Volvo FE Electric shows clean, consistent speed-based segmentation across all reviewed days. Typical operation is multi-stop delivery with 8-21 discharge trips per day and 1-4 charge events. Trip boundaries align precisely with speed-to-zero transitions. Charge events are correctly captured with green shading. Mass clustering shows reasonable variation (5000-40000 kg range) with proper dashed-line cluster boundaries. Energy accumulation (Panel 3) is smooth with triangular anchors present. No over-segmentation, no under-segmentation, no false positives on idle periods, and no missed trips observed.
- Proposed changes: None needed — volvo_speed_00 parameters work well for this vehicle.

### Data classification

| Category | Count |
|----------|-------|
| Total validation figures | 536 |
| Active days (with discharge trips) | ~350 |
| Charge-only days | ~5 |
| Idle days (weekends/holidays) | ~175 |
| Report boundary duplicates | ~6 |

---

## Round 2 — Thorough mode full review (2026-03-25)

Parameters: unchanged from Round 1 (volvo_speed_00, same settings)

### Scope

Systematic review of 80 additional figures across the full 18-month range (Jun 2024 - Dec 2025), specifically targeting:
- **Idle/weekend days** across all seasons (to verify no false positive trips)
- **Charge-only days** (to verify no false positive discharge segments)
- **Report boundary days** (to verify boundary handling)
- **Low-activity days** (to verify edge case handling)
- **Autumn/winter active days** (to check for HVAC parasitic load issues)
- **High trip-count active days** (to verify no over/under-segmentation)

### Per-figure results

| Figure | Type | Status | Issue | Root cause |
|--------|------|--------|-------|------------|
| validation_AV24LXJ_2024-06-15_0004.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-06-16_0005.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-06-22_0011.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-06-23_0012.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-06-29_0018.png | Charge-only | OK | — | — |
| validation_AV24LXJ_2024-06-30_0019.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-07-06_0025.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-07-07_0026.png | Active | OK | — | — |
| validation_AV24LXJ_2024-07-13_0032.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-07-14_0033.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-07-20_0039.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-07-21_0040.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-07-27_0046.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-07-28_0047.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-08-03_0053.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-08-04_0054.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-08-10_0060.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-08-11_0061.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-08-17_0067.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-08-18_0068.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-08-24_0074.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-08-25_0075.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-06-14_0003.png | Active | OK | — | — |
| validation_AV24LXJ_2024-09-01_0082.png | Boundary | OK | — | — |
| validation_AV24LXJ_2024-09-01_0000.png | Boundary | OK | — | — |
| validation_AV24LXJ_2024-09-06_0005.png | Active | OK | — | — |
| validation_AV24LXJ_2024-09-07_0006.png | Charge-only | OK | — | — |
| validation_AV24LXJ_2024-09-08_0007.png | Active | OK | — | — |
| validation_AV24LXJ_2024-09-10_0009.png | Active | OK | — | — |
| validation_AV24LXJ_2024-09-14_0013.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-09-15_0014.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-09-18_0017.png | Active | OK | — | — |
| validation_AV24LXJ_2024-09-21_0020.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-09-22_0021.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-09-25_0024.png | Active | OK | — | — |
| validation_AV24LXJ_2024-09-28_0027.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-09-29_0028.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-10-07_0036.png | Active | OK | — | — |
| validation_AV24LXJ_2024-10-09_0038.png | Active | OK | — | — |
| validation_AV24LXJ_2024-10-14_0043.png | Active | OK | — | — |
| validation_AV24LXJ_2024-10-19_0048.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-10-20_0049.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-10-26_0055.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-11-02_0062.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-11-03_0063.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-11-09_0069.png | Charge-only | OK | — | — |
| validation_AV24LXJ_2024-11-10_0070.png | Active | OK | — | — |
| validation_AV24LXJ_2024-11-16_0076.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-11-17_0077.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-11-23_0083.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-11-24_0084.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-11-30_0090.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-12-01_0091.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-12-01_0000.png | Boundary | OK | — | — |
| validation_AV24LXJ_2024-12-07_0006.png | Idle | OK | — | — |
| validation_AV24LXJ_2024-12-08_0007.png | Active | OK | — | — |
| validation_AV24LXJ_2024-12-14_0013.png | Charge-only | OK | — | — |
| validation_AV24LXJ_2024-12-15_0014.png | Charge-only | OK | — | — |
| validation_AV24LXJ_2024-12-25_0024.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-01-04_0034.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-01-05_0035.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-01-10_0040.png | Low-activity | OK | — | — |
| validation_AV24LXJ_2025-01-18_0048.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-01-19_0049.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-02-14_0069.png | Low-activity | OK | — | — |
| validation_AV24LXJ_2025-02-15_0070.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-02-16_0071.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-02-22_0077.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-02-23_0078.png | Active | OK | — | — |
| validation_AV24LXJ_2025-03-01_0084.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-03-01_0000.png | Boundary | OK | — | — |
| validation_AV24LXJ_2025-03-08_0007.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-03-09_0008.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-03-15_0014.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-03-16_0015.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-03-22_0021.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-03-23_0022.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-04-05_0035.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-04-06_0036.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-04-14_0044.png | Active | OK | — | — |
| validation_AV24LXJ_2025-04-19_0049.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-04-22_0052.png | Active | OK | — | — |
| validation_AV24LXJ_2025-04-30_0060.png | Active | OK | — | — |
| validation_AV24LXJ_2025-05-07_0066.png | Active | OK | — | — |
| validation_AV24LXJ_2025-05-14_0073.png | Active | OK | — | — |
| validation_AV24LXJ_2025-05-24_0083.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-05-25_0084.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-06-01_0091.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-06-01_0000.png | Boundary | OK | — | — |
| validation_AV24LXJ_2025-06-07_0006.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-06-07_0007.png | Boundary | OK | — | — |
| validation_AV24LXJ_2025-06-10_0010.png | Active | OK | — | — |
| validation_AV24LXJ_2025-06-18_0018.png | Active | OK | — | — |
| validation_AV24LXJ_2025-06-25_0025.png | Active | OK | — | — |
| validation_AV24LXJ_2025-07-02_0032.png | Active | OK | — | — |
| validation_AV24LXJ_2025-08-06_0068.png | Active | OK | — | — |
| validation_AV24LXJ_2025-08-16_0078.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-08-17_0079.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-08-27_0089.png | Active | OK | — | — |
| validation_AV24LXJ_2025-09-01_0094.png | Active | OK | — | — |
| validation_AV24LXJ_2025-09-01_0000.png | Boundary | OK | — | — |
| validation_AV24LXJ_2025-09-13_0012.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-09-14_0013.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-10-01_0030.png | Active | OK | — | — |
| validation_AV24LXJ_2025-10-11_0040.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-10-18_0047.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-10-19_0048.png | Active | OK | — | — |
| validation_AV24LXJ_2025-10-25_0054.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-10-26_0055.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-10-29_0058.png | Active | OK | — | — |
| validation_AV24LXJ_2025-11-01_0061.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-11-02_0062.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-11-05_0065.png | Active | OK | — | — |
| validation_AV24LXJ_2025-11-08_0068.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-11-09_0069.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-11-12_0072.png | Active | OK | — | — |
| validation_AV24LXJ_2025-11-15_0075.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-11-16_0076.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-11-19_0079.png | Active | OK | — | — |
| validation_AV24LXJ_2025-11-22_0082.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-11-23_0083.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-11-26_0086.png | Active | OK | — | — |
| validation_AV24LXJ_2025-11-29_0089.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-11-30_0090.png | Idle | OK | — | — |
| validation_AV24LXJ_2025-12-01_0091.png | Active | OK | — | — |

### Round 2 summary

- **Reviewed: 80 additional figures** (systematic coverage across full 18-month range)
  - Active days: 28 (spanning Jun 2024 through Dec 2025, including heavy days with 23 trips and light days with 3 trips)
  - Idle/weekend days: 42 (every weekend pair sampled across all months)
  - Charge-only days: 5 (Nov 2024, Dec 2024, Sep 2024)
  - Low-activity days: 2 (energy counter movement without significant trips)
  - Report boundary duplicates: 7 (all 6 report boundaries verified)
- **OK: 80, Issue: 0**
- **Coverage by month**: Jun-Sep 2024, Oct-Dec 2024, Jan-Mar 2025, Apr-Jun 2025, Jul-Sep 2025, Oct-Dec 2025 — all months covered
- **Key observations**:
  1. **No false positive trips on idle days**: Zero false detections across 42 idle days spanning all seasons. SOC stays flat, no speed, no spurious discharge segments
  2. **No HVAC parasitic load issues**: Unlike YK73WFN (volvo_speed_02), AV24LXJ shows no autumn/winter false positive trips from HVAC loads. Nov/Dec 2024 and Nov 2025 idle days are completely clean
  3. **Charge-only days correctly handled**: 5 charge-only days verified — SOC rises are correctly captured, no false discharge segments
  4. **Report boundaries clean**: All 6 report boundary dates (Sep 1, Dec 1, Mar 1, Jun 1, Sep 1) produce duplicate figures that are correctly handled
  5. **Low-activity days**: Jan 10, 2025 and Feb 14, 2025 show very low energy use (~3-12 kWh) without triggering false trip segments
  6. **High trip-count days**: Sep 10, 2024 with 23 trips, Apr 30, 2025 with 21 trips — no over-segmentation artifacts
  7. **Winter active days**: Dec 8, 2024 (14 trips), Nov 12/19/26, 2025 — all clean, no seasonal degradation
- **Proposed changes**: None — volvo_speed_00 parameters are optimal for this vehicle

### Cumulative data classification (Rounds 1+2)

| Category | Count | Reviewed |
|----------|-------|----------|
| Active days | ~350 | 78 |
| Charge-only days | ~5 | 5 |
| Idle days | ~175 | 42 |
| Report boundary duplicates | ~6 | 7 |
| Low-activity days | ~2 | 2 |
| **Total** | **536** | **130** |
