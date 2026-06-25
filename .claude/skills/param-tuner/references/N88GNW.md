# N88GNW — Renault Trucks D Wide Z.E.

## Vehicle characteristics

- Make/Model: Renault Trucks D Wide Z.E.
- Nominal capacity: 540 kWh
- Operation mode: multi-drop distribution (city/suburban), typically 10-14 stops per day
- Data characteristics: telematics SOC + telematics speed (`wheel_based_speed`) + Logger Mass; AC/DC charging power columns are unstable (often zero or cumulative values)
- Data range: 2024-10-11 to 2025-12-01 (421 days, 5 quarterly reports)

## Pipeline and parameters

- Pipeline: `renault_speed` (speed-based segmentation)
- All parameters are default values, no special adjustment needed

| Parameter | Value | Reason |
|------|-----|------|
| `speed_threshold_kmh` | 1.0 | default; correctly distinguishes stationary/moving |
| `min_stop_duration_min` | 5.0 | default; suits the multi-drop distribution stopping pattern |
| `min_trip_duration_min` | 2.0 | default; captures short-distance shunting |
| `min_soc_drop` | 1.0 | default; at 540 kWh, 1% = 5.4 kWh, reasonable |
| `min_energy_kwh` | 1.0 | default; filters out micro-movements |

## Review results

### Round 1 (2026-03-24): sampled review
- 50/421 figures reviewed (sampled every 7 days)
- OK: 37, Issue: 13

### Round 2 (2026-03-26): full detailed inspection (Thorough Mode)
- all 421/421 figures reviewed
- OK: 388 (92.2%), Issue: 33 (7.8%)
- all Issues are of the same type: cross-day boundary charge omission (architectural limitation)
- no parameter tuning needed

## Key findings

### 1. Renault AC/DC charging data is unreliable
The telematics AC/DC charging power columns of the Renault D Wide Z.E. behave inconsistently:
- on some days entirely zero (even when SOC clearly rises)
- on some days they show a cumulative energy-meter value (~100-400 kWh steps) rather than instantaneous power
- charge detection correctly falls back to the SOC-rise heuristic

### 2. High-quality speed segmentation
The speed-based pipeline performs excellently on this large-capacity 540 kWh vehicle:
- a typical working day produces 1-14 discharge segments, perfectly aligned with the speed trace
- in multi-drop distribution mode, `min_stop=5.0` minutes correctly distinguishes "stops" vs "deceleration while driving"
- EP values of 0.8-2.5 kWh/km are within a reasonable range (~26t GVW class)

### 3. Mass data is noisy but usable
- raw telematics mass range 10,000-35,000 kg (with noise/jumps)
- segment-mean mass is stable at 14-25 t (a reasonable laden/unladen range)
- loading events are occasionally visible (mass jumps from ~10 t to ~30 t)

### 4. Cross-day boundary charge omission (confirmed as an architectural limitation)
- this issue occurs on about 33/421 days (7.8%)
- overnight charging completes before 00:00 -> attributed to the previous day
- or charging starts after 00:00 -> only discharge on that day
- this is an inherent limitation of the per-day segmentation window, not resolvable by parameter tuning

## Lessons learned (applicable to similar Renault vehicles)

1. **The Renault defaults are sufficient** — no need to adjust `min_soc_drop` or switch the speed column as for Mercedes
2. **Do not rely on AC/DC charging data** — the Renault telematics AC/DC columns are unreliable, charge detection should rely primarily on SOC-rise
3. **`min_stop=5.0` is appropriate in multi-drop distribution mode** — better suited to frequent stops than long-haul transport (which may need a larger min_stop)
4. **Mass data noise must be considered during analysis** — use segment means rather than raw time-series values
5. **For large-capacity vehicles (540 kWh), `min_soc_drop=1.0` corresponds to ~5.4 kWh** — enough to filter noise without missing valid trips
