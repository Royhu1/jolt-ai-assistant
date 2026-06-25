# EX74JXW — Scania P-series BEV

> Pipeline: scania_speed_00 | Last updated: **2026-05-17**

## ⚠️ 2026-05-17 update — historical Round 1/2 conclusion overturned

The previous two thorough reviews judged "0 genuine segmentation errors, no parameter tuning needed". But when the user re-reviewed 2025-07-14_0005, they
clearly pointed out that 06:30–15:00 should have 4 trips rather than 1 trip of 220 km In Transit. Diagnosis:

- the `find_speed_trips` probe proved the algorithm had in fact correctly split out 8 trips (4 in the morning + 4 in the afternoon)
- the real culprit is the downstream `merge_discharge_by_mass`: adjacent trips have the same dominant `mass_cluster` →
  merged into a single In Transit
- EX74JXW's real load fluctuation of 1–2 t falls within the same `min_cluster_gap_kg=2000` cluster bucket → merge is bound to trigger

**This round's (2026-05-17) changes**:
- `scania_speed_00.merge_by_mass`: added → **false** (mass merging disabled, split retained)
- the other speed_params / charge_params unchanged

**Effect** (2025-06_2025-09 period comparison):
| Leg Type | merge ON (old) | merge OFF (new) | Δ |
|---|---|---|---|
| In Transit | 43 | 101 | +135% |
| Outbound + Return | 16 | 21 | +31% |
| **total driving legs** | **59** | **122** | **+107%** |

07-14_0005 splits 4 trips in the morning (50.7 + 49.3 + 56.1 + 43.5 km) + 4 in the afternoon; visual verification passed.
Per-day driving leg max 11/day (07-31), median 5.5, no over-segmentation.

The old records below are retained only for historical reference — the current conclusion is as given in this section.

---


## Vehicle characteristics

- Make/Model: Scania P-series BEV
- Nominal capacity: 475 kWh
- Operation mode: mode=discharge, multi-drop distribution
- Data characteristics: telematics SOC (coarse 1% resolution), telematics speed (`wheel_based_speed`), Logger Speed (available after October)

## State before optimisation

- Pipeline: `scania_soc_00` (SOC-based discharge segmentation)
- Main problem: **~14% of days had trips missed** — when SOC is flat (100% or barely changing), there is clear speed activity but no discharge segment

## Root cause

Scania SOC precision is integer (1%). When a trip is short or energy efficiency is high, the SOC change < 5% (the `min_soc_drop` threshold),
so the trip is not detected at all. Typical scenario:
- genuine driving reaching 80 km/h
- Moving Energy consumption of 6-16 kWh
- but SOC remains at 97-100% unchanged

## Solution

Switch to `scania_speed_00` (speed-based discharge segmentation).

**Key point**: the speed branch in `run_segment_detection()` already has a fallback mechanism ——
when `find_discharge_segments_by_speed()` returns an empty list, it automatically falls back to SOC-based.
Therefore, for the case where telematics speed was unavailable during July, the algorithm automatically falls back to SOC-based, without losing data.

## Final parameters

Use the `scania_speed_00` default parameters, no extra tuning needed:

| Parameter | Value |
|------|-----|
| speed_threshold_kmh | 1.0 |
| min_stop_duration_min | 5.0 |
| min_trip_duration_min | 2.0 |
| min_soc_drop | 1.0 |
| min_energy_kwh | 1.0 |

## Lessons learned

1. **SOC-based is unsuitable for short-trip detection with coarse-resolution SOC** — at 1% resolution, min_soc_drop=5.0 will miss short trips
2. **Speed-based + fallback is the best strategy** — use speed when available, fall back to SOC when not
3. **Do not abandon speed-based just because some periods lack speed data** — the fallback mechanism already covers this case
4. **EX74JXW and EX74JXY are both Scania P-series, with the same problem and solution**

## Tuning history

| Round | Date | Action | Result |
|-------|------|--------|--------|
| 1 | 2026-03-23 | Initial review of 71 validation figures | 55 OK / 16 Issue / 0 genuine segmentation errors. No parameter tuning needed. |
| 2 | 2026-03-25 | Thorough-mode full detailed re-review | Confirmed all Round 1 judgements. 0 status changes. No parameter tuning needed. |

## Data coverage and quality summary (v2.1.0.dev0)

- **Reporting period**: 2025-06-01 to 2025-12-01 (two xlsx)
- **Validation figures**: 71 days (19 days in July + 13 in August + 22 in October + 17 in November)
- **Active driving days**: 42/71 (59.2%)
- **EP range**: 0.5-3.0 kWh/km (typically 0.8-2.2)
- **Mass range**: empty ~10-14t, full load ~20-40t
- **Data characteristics**: no telematics speed in July (SOC-fallback); telematics speed restored in mid-August; Logger Speed available from October
