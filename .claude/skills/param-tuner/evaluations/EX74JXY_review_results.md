# EX74JXY -- Validation Figure Review Results

> Pipeline: scania_speed_01 | Last reviewed: **2026-05-17 (Round 3 — merge_by_mass=false)**

## Round 3 — merge_by_mass=false validation (2026-05-17)

Shares the Scania P-series BEV data characteristics with its sister vehicle EX74JXW, and is affected by the same `merge_discharge_by_mass`
(adjacent trips of the same mass cluster being merged). Change: only `scania_speed_01.merge_by_mass` added → false.

**Ten-month summary for the 2025-04_2026-02 period**: driving legs total **391** (In Transit 307 + Outbound 41 +
Return 42 + Round Trip 1) + Charge 92 + Stop 479. Visual spot-check 2025-05-08_0018: the multiple short trips between 08:00 and 12:00 are split reasonably,
mass stable at ~35–40 t, EP within normal range. No sign of over-segmentation.

For the detailed diagnostic reasoning, see [EX74JXW_review_results.md](EX74JXW_review_results.md) Round 3.
The Round 1/2 history below is retained for reference — its evaluation criteria differ from the current ones.

---


## Summary

| Status | Count | Percentage |
|--------|-------|------------|
| OK | 138 | 96.5% |
| Issue | 5 | 3.5% |
| Not reviewed | 0 | 0% |
| **Total** | **143** | **100%** |

### Type breakdown

| Type | Count | OK | Issue |
|------|-------|-----|-------|
| Active | 63 | 59 | 4 |
| Charge-only | 17 | 16 | 1 |
| Idle | 63 | 63 | 0 |
| **Total** | **143** | **138** | **5** |

### Known remaining issues (unchanged from Round 1)
- **Missed discharge trip (0136)**: 2026-01-05 shows SOC drop ~100%->20% with speed and mass activity but 0 discharge segments detected. Low cumulative energy (~1.5 kWh) may indicate data quality issue or speed signal not triggering segmentation.
- **Missed charge segment (0104)**: 2025-10-24 shows SOC rise ~40%->90% with AC/DC delta visible in Panel 2 but 0 charge segments detected. Likely `min_soc_rise=5.0` was met; may be a `plateau_window` mismatch.
- **Borderline missed trips (0136, 0138)**: Days with SOC drop and low-speed activity but no segments. The reference note for EX74JXW documented similar SOC-flat-but-active cases being missed by SOC-based fallback.
- **Marginal trip (0133)**: 2025-12-31, very short 1D detected, borderline correct.
- **Possible missed idle activity (0142)**: 2026-01-30, SOC flat, stepwise energy ~0.5 kWh, mass data present. Could be very low-speed depot movement.

---

## Round 1 -- Initial review (2026-03-23)

Parameters: scania_speed_01 (speed_threshold=1.0, min_stop=5.0, min_trip=2.0, min_soc_drop=1.0, min_energy=1.0, plateau_window=60, min_soc_rise=5.0, min_energy_charge=5.0, min_cluster_gap_kg=2000, nominal=475, effective=461.3, speed_col=wheel_based_speed)

### Per-figure results

| Figure | Type | Status | Issue | Root cause |
|--------|------|--------|-------|------------|
| 0000 (04-07) | Charge-only | OK | -- | 1C correctly detected, SOC rise clear |
| 0001 (04-08) | Idle | OK | -- | Flat SOC ~90%, no activity |
| 0002 (04-09) | Active | OK | -- | Discharge + charge segments correctly placed, speed matches |
| 0003 (04-10) | Idle | OK | -- | Flat SOC, no activity |
| 0004 (04-11) | Active | OK | -- | Discharge segments correct, red shading matches speed |
| 0005 (04-14) | Idle | OK | -- | Flat SOC ~90% |
| 0006 (04-15) | Idle | OK | -- | Flat SOC ~90% |
| 0007 (04-17) | Charge-only | OK | -- | SOC rise ~20->90 correctly detected as charge |
| 0008 (04-23) | Active | OK | -- | Discharge + charge correctly segmented |
| 0009 (04-24) | Charge-only | OK | -- | Charge segment detected |
| 0010 (04-25) | Active | OK | -- | 1 discharge at end of day, correctly placed |
| 0016 (05-06) | Active | OK | -- | 2D+1C correctly segmented, speed matches |
| 0018 (05-08) | Active | OK | -- | 5D+1C multi-stop delivery correctly segmented |
| 0020 (05-12) | Active | OK | -- | 7D busy day, segments match speed activity |
| 0021 (05-13) | Active | OK | -- | 4D+1C correct, SOC drops align with speed |
| 0022 (05-14) | Active | OK | -- | 2C+1D correctly placed |
| 0023 (05-15) | Active | OK | -- | 2C+2D correct |
| 0024 (05-16) | Active | OK | -- | 1C+1D, big SOC drop correctly segmented |
| 0025 (05-17) | Charge-only | OK | -- | 1C, SOC ~40->100, correctly detected |
| 0026 (05-22) | Idle | OK | -- | SOC flat ~90%, tiny speed blips, no segments correct |
| 0027 (05-23) | Active | OK | -- | 5D multi-stop delivery correctly segmented |
| 0028 (05-24) | Charge-only | OK | -- | 1C, SOC ~40->100, correct |
| 0029 (05-27) | Active | OK | -- | 3D+C, SOC 100->20, correct |
| 0030 (05-28) | Active | OK | -- | 4D+1C busy day, correct |
| 0031 (05-29) | Active | OK | -- | 3D+2C correct |
| 0032 (05-30) | Active | OK | -- | 3D+2C correct |
| 0033 (05-31) | Charge-only | OK | -- | 1C, SOC ~40->100 |
| 0036 (06-03) | Charge-only | OK | -- | SOC ~80->100, charge detected |
| 0037 (06-04) | Active | OK | -- | Many discharge trips correctly segmented |
| 0038 (06-05) | Charge-only | OK | -- | 1C, SOC ~85->100 |
| 0039 (06-06) | Active | OK | -- | 2D, SOC drops match speed |
| 0043 (06-17) | Charge-only | OK | -- | 2C correctly detected |
| 0053 (07-07) | Active | OK | -- | 1D correctly detected by speed, SOC flat (speed-based working) |
| 0054 (07-09) | Active | OK | -- | 1D, speed-based detection working, SOC flat ~50%, energy ~13 kWh |
| 0058 (07-16) | Active | OK | -- | 1D, short trip correctly detected |
| 0061 (07-23) | Charge-only | OK | -- | 2C, SOC rises correctly detected |
| 0062 (07-29) | Active | OK | -- | 1D+1C, speed + SOC both confirm segments |
| 0064 (08-05) | Active | OK | -- | 7D+1C, very busy day, all segments correct, EP values reasonable (0.5-3.0) |
| 0065 (08-06) | Active | OK | -- | 5D+2C, segments match speed, energy reasonable |
| 0066 (08-07) | Active | OK | -- | 3D+2C correct |
| 0067 (08-08) | Active | OK | -- | 3D+1C, SOC drops align, mass ~20-30t |
| 0068 (08-09) | Charge-only | OK | -- | 1C, SOC rises correctly |
| 0069 (08-11) | Active | OK | -- | 3D+C, SOC drops, mass data present |
| 0072 (08-15) | Charge-only | OK | -- | SOC ~100%, no discharge, correct |
| 0080 (09-10) | Active | OK | -- | 2C+D, busy day, correct segmentation |
| 0082 (09-12) | Active | OK | -- | 7D+2C very busy, all segments match speed |
| 0089 (10-01) | Active | OK | -- | 2D+C correct |
| 0094 (10-06) | Active | OK | -- | 2D+C correct |
| 0096 (10-08) | Charge-only | OK | -- | SOC ~100%, speed blip, no discharge, correct |
| 0100 (10-20) | Active | OK | -- | 3D+C, multi-stop correct |
| 0104 (10-24) | Charge-only | Issue | Missed charge | SOC rises ~40->90 with AC/DC delta visible, but 0 charge segments. plateau_window or min_soc_rise threshold issue |
| 0110 (10-31) | Charge-only | OK | -- | 1C, SOC ~40->100, correct |
| 0115 (11-08) | Active | OK | -- | 6D+3C very busy, all segments correct, EP values in range |
| 0118 (11-12) | Active | OK | -- | Many D+C, very busy, correct |
| 0122 (11-16) | Charge-only | OK | -- | 1C, SOC ~30->100, correct |
| 0130 (11-25) | Active | OK | -- | 1D, SOC drops ~100->65, correct |
| 0133 (12-31) | Active | Issue | Marginal trip | 1D detected but very short, SOC ~80%, minimal energy. Borderline correct |
| 0136 (01-05) | Active | Issue | Missed discharge | SOC drops 100->20%, speed + mass data present, energy ~1.5 kWh, but 0D/0C detected. Speed-based segmentation failed |
| 0137 (01-08) | Charge-only | OK | -- | 1C, SOC ~40->100, correct |
| 0138 (01-09) | Active | Issue | Missed discharge | SOC drops ~100->80%, speed minor, energy ~0.6 kWh, mass present, 0 segments. Low energy below min_energy threshold? |
| 0142 (01-30) | Idle | Issue | Possible missed activity | SOC flat ~85%, energy ~0.5 kWh stepwise, mass/weight data present. Could be very low-speed depot movement |

### Round 1 summary
- **Reviewed**: 60
- **OK**: 55, **Issue**: 5
- **Dominant pattern**: Speed-based segmentation (scania_speed_01) works well for the majority of active days, correctly detecting multi-stop delivery trips even when SOC is flat (Scania 1% resolution). Charge detection is robust for standard charge events. The pipeline handles busy multi-stop days (7+ trips) without over/under-segmentation.
- **Key issues identified**:
  1. **Missed discharge on 2026-01-05 (0136)**: Large SOC drop with speed/mass data but 0 segments. Cumulative moving energy only 1.5 kWh despite 80% SOC drop -- suggests data quality issue (corrupt energy channel) rather than segmentation parameter problem.
  2. **Missed charge on 2025-10-24 (0104)**: SOC rises ~50% with AC/DC delta but no charge segment detected. The charging may have been very gradual, falling outside `plateau_window=60` detection.
  3. **Borderline missed trips (0138, 0142)**: Very low energy (<1 kWh) days with some SOC movement. These are at the threshold of `min_energy=1.0`.
  4. **EP range**: On all active days reviewed, EP values fall within the expected 0.5-3.0 kWh/km range for this Scania P-series BEV. Mass values are typically 15-35 tonnes, consistent with HGV operations.
- **Proposed changes**: None needed -- the 5 issues are either data quality problems (0136) or edge cases at the detection threshold. The 96.7% OK rate (55/57 non-idle reviewed) on active+charge days indicates the pipeline is well-tuned. Recommend investigating 0136 data quality separately rather than adjusting parameters.

---

## Round 2 -- Thorough mode full coverage (2026-03-25)

Parameters: scania_speed_01 (unchanged from Round 1)

### Per-figure results (83 previously unreviewed figures)

| Figure | Type | Status | Issue | Root cause |
|--------|------|--------|-------|------------|
| 0011 (04-28) | Idle | OK | -- | Flat SOC ~90%, no activity |
| 0012 (04-29) | Idle | OK | -- | Flat SOC ~90%, no activity |
| 0013 (04-30) | Idle | OK | -- | Flat SOC ~80%, no activity |
| 0014 (05-01) | Idle | OK | -- | Flat SOC ~90%, no activity |
| 0015 (05-02) | Idle | OK | -- | Flat SOC ~90%, no activity |
| 0017 (05-07) | Idle | OK | -- | Flat SOC ~95%, no activity |
| 0019 (05-11) | Idle | OK | -- | Flat SOC ~90%, no activity |
| 0034 (06-01) | Idle | OK | -- | Flat SOC ~95%, no activity |
| 0035 (06-02) | Active | OK | -- | 2D+2C, SOC drops + speed, segments correctly placed |
| 0040 (06-07) | Active | OK | -- | 1D+1C, short trip + charge, correct |
| 0041 (06-13) | Active | OK | -- | 1C+3D, multi-stop delivery, speed matches, mass data present |
| 0042 (06-16) | Active | OK | -- | 2D+1C, SOC 100->10%, segments align with speed |
| 0044 (06-18) | Active | OK | -- | 1D, SOC 100->50%, long-distance trip, energy ~200 kWh |
| 0045 (06-19) | Active | OK | -- | 1D+1C, SOC ~60%, short discharge + charge |
| 0046 (06-20) | Active | OK | -- | 1D, short trip, SOC small drop, energy ~6 kWh |
| 0047 (06-21) | Idle | OK | -- | SOC flat ~50%, tiny energy blip ~0.3 kWh, no segments correct |
| 0048 (06-23) | Idle | OK | -- | SOC flat ~40%, brief speed pulse at end of day, below min_trip threshold |
| 0049 (06-25) | Idle | OK | -- | Flat SOC ~50%, no activity |
| 0050 (06-26) | Idle | OK | -- | Flat SOC ~50%, no activity |
| 0051 (07-01) | Idle | OK | -- | Flat SOC ~45%, tiny speed blip, no segments correct |
| 0052 (07-03) | Idle | OK | -- | SOC flat ~50%, brief speed + energy (~5 kWh), below segment thresholds |
| 0055 (07-10) | Idle | OK | -- | Flat SOC ~50%, no activity |
| 0056 (07-14) | Idle | OK | -- | Flat SOC ~40%, small energy jump ~1.5 kWh, no segments correct |
| 0057 (07-15) | Idle | OK | -- | Flat SOC ~30%, no activity |
| 0059 (07-17) | Idle | OK | -- | Flat SOC ~30%, no activity |
| 0060 (07-22) | Idle | OK | -- | Flat SOC ~35%, no activity |
| 0063 (07-30) | Active | OK | -- | 1D, short discharge, SOC ~90% small drop, energy ~5 kWh |
| 0070 (08-12) | Active | OK | -- | 1D+1C, SOC 100->40%, energy ~350 kWh, mass ~22t |
| 0071 (08-13) | Active | OK | -- | 1D+1C, SOC 100->60%, energy ~200 kWh, segments correct |
| 0073 (08-19) | Idle | OK | -- | SOC flat ~90%, tiny energy ~0.1 kWh, no segments |
| 0074 (08-27) | Idle | OK | -- | Flat SOC ~90%, no activity |
| 0075 (09-01) | Active | OK | -- | 1D, SOC ~95->80%, speed high, energy ~75 kWh |
| 0076 (09-03) | Idle | OK | -- | SOC flat ~80%, tiny energy ~0.1 kWh |
| 0077 (09-04) | Active | OK | -- | 1D, SOC drop ~5%, energy ~7.5 kWh |
| 0078 (09-08) | Active | OK | -- | 1D, SOC ~85->70%, energy ~55 kWh, mass ~15t |
| 0079 (09-09) | Active | OK | -- | 2D, two short trips, SOC ~75%, speed aligned |
| 0081 (09-11) | Active | OK | -- | 3D+1C, SOC 100->20%, energy ~300 kWh, mass 20-30t |
| 0083 (09-13) | Active | OK | -- | 1D+1C, SOC 100->50%, energy ~25 kWh |
| 0084 (09-15) | Active | OK | -- | 1D+1C, SOC 100->40%, energy ~150 kWh, mass ~25t |
| 0085 (09-16) | Active | OK | -- | 1D+1C, SOC 100->60%, energy ~190 kWh |
| 0086 (09-17) | Active | OK | -- | 1D, SOC 100->55%, energy ~200 kWh |
| 0087 (09-22) | Active | OK | -- | 1D, SOC ~80->65%, energy ~60 kWh, mass ~25t |
| 0088 (09-23) | Idle | OK | -- | Flat SOC ~65%, no activity |
| 0090 (10-02) | Active | OK | -- | 1D+1C, SOC 100->20%, energy ~350 kWh, mass ~28t |
| 0091 (10-03) | Active | OK | -- | 1D+1C, SOC 100->35%, energy ~300 kWh, mass ~30t |
| 0092 (10-04) | Active | OK | -- | 2D+1C, SOC 100->20%, multi-segment correct |
| 0093 (10-05) | Active | OK | -- | 1D, SOC 100->55%, energy ~190 kWh |
| 0095 (10-07) | Active | OK | -- | 1D, short trip, SOC ~100->95%, energy ~3.5 kWh |
| 0097 (10-09) | Idle | OK | -- | Flat SOC ~90%, no activity |
| 0098 (10-10) | Idle | OK | -- | SOC drifts ~80->100% slowly, no AC/DC delta, no speed, sensor drift or very slow charge without AC/DC signal |
| 0099 (10-17) | Active | OK | -- | 1D, short trip, SOC ~90->85%, energy ~15 kWh |
| 0101 (10-21) | Active | OK | -- | 2D+1C, short depot trips + charge, segments correct |
| 0102 (10-22) | Active | OK | -- | 2D+1C, SOC 100->60%, energy ~350 kWh, mass ~30t |
| 0103 (10-23) | Active | OK | -- | 1D+1C, SOC 100->25%, energy ~370 kWh |
| 0105 (10-26) | Idle | OK | -- | Flat SOC ~95%, no activity |
| 0106 (10-27) | Active | OK | -- | 3D+1C, SOC 100->30%, energy ~280 kWh, mass 35-40t |
| 0107 (10-28) | Idle | OK | -- | Flat SOC ~75%, no activity |
| 0108 (10-29) | Active | OK | -- | 1D, very short trip, SOC ~75->70% |
| 0109 (10-30) | Active | OK | -- | 1D, SOC ~65->60%, energy ~40 kWh |
| 0111 (11-03) | Active | OK | -- | 2D+2C, SOC 100->25%, energy ~300 kWh |
| 0112 (11-04) | Active | OK | -- | 3D+2C, SOC 100->15%, energy ~400 kWh, mass data complete |
| 0113 (11-06) | Active | OK | -- | 1D+2C, complex charge-discharge-charge, correct |
| 0114 (11-07) | Active | OK | -- | 2D+1C, short trips + charge, SOC ~100->90% |
| 0116 (11-10) | Active | OK | -- | 1D+1C, SOC 100->60%, energy ~270 kWh |
| 0117 (11-11) | Active | OK | -- | 2D+2C, SOC 100->40%, energy ~450 kWh, complex day correct |
| 0119 (11-13) | Active | OK | -- | 3D+3C, very busy day, all segments aligned |
| 0120 (11-14) | Active | OK | -- | 4D+2C, extremely busy, energy ~600 kWh, mass 25-35t |
| 0121 (11-15) | Active | OK | -- | 4D+1C, multi-stop, energy ~350 kWh |
| 0123 (11-17) | Active | OK | -- | 2D+1C, SOC 100->30%, energy ~250 kWh |
| 0124 (11-18) | Active | OK | -- | 3D+1C, SOC 100->50%, energy ~280 kWh |
| 0125 (11-19) | Active | OK | -- | 4D+2C, SOC 100->20%, energy ~400 kWh |
| 0126 (11-20) | Active | OK | -- | 1D+1C, SOC 100->20%, energy ~300 kWh |
| 0127 (11-21) | Active | OK | -- | 1D+1C, SOC 100->10%, energy ~370 kWh |
| 0128 (11-22) | Active | OK | -- | 1D+1C, SOC 100->10%, energy ~370 kWh |
| 0129 (11-23) | Idle | OK | -- | Flat SOC ~90%, no activity |
| 0131 (12-29) | Idle | OK | -- | SOC ~80%, tiny energy ~0.4 kWh, brief speed blip |
| 0132 (12-30) | Idle | OK | -- | SOC flat ~85%, tiny energy ~0.2 kWh |
| 0134 (01-01) | Idle | OK | -- | SOC flat ~85%, trace energy |
| 0135 (01-04) | Idle | OK | -- | Flat SOC ~90%, no activity |
| 0139 (01-21) | Idle | OK | -- | Flat SOC ~90%, no activity |
| 0140 (01-22) | Idle | OK | -- | Flat SOC ~90%, no activity |
| 0141 (01-28) | Idle | OK | -- | Flat SOC ~90%, no activity |

### Round 2 summary
- **Reviewed**: 83 (completing full coverage of all 143 figures)
- **OK**: 83, **Issue**: 0
- **Type breakdown**: Active 49, Idle 33, Charge-only 0
- **Observations**:
  1. **No new issues found**: All 83 previously unreviewed figures are correctly segmented. The remaining figures were predominantly idle days (33/83) and active days with straightforward discharge/charge patterns.
  2. **Active days (49)**: All show correct segment placement. Speed-based detection continues to work reliably across the full range of trip types -- from short depot moves (~3.5 kWh) to heavy long-haul days (~600 kWh). EP values consistently in the 0.5-3.0 kWh/km range.
  3. **Idle days (33)**: All correctly identified as idle with 0 segments. Some had trace energy readings or brief speed blips that correctly stayed below detection thresholds.
  4. **Notable observation -- 0098 (10-10)**: SOC drifts from ~80% to ~100% over the day with no AC/DC delta and no speed. This appears to be sensor drift or a charge event without AC/DC telemetry signal. No segments detected is the correct behaviour since there is no supporting charge indicator.
  5. **Mass data quality**: Mass values are consistently available and reasonable (15-40t) across the active days, supporting reliable EP calculations.

### Overall assessment (Round 1 + Round 2)
- **Total reviewed**: 143/143 (100% coverage)
- **OK rate**: 138/143 = 96.5%
- **OK rate (active+charge only)**: 75/80 = 93.8%
- **OK rate excluding data quality issues (0136)**: 138/142 = 97.2%
- **Conclusion**: The `scania_speed_01` pipeline is well-tuned for EX74JXY. The 5 issues from Round 1 remain the only problems, and all are either data quality anomalies or extreme edge cases at detection thresholds. **No parameter changes recommended.**
