# KY24LHT — Parameter Tuning Reference

> Volvo FM Electric | Pipeline: volvo_speed_03 | Battery: 540 kWh | Last updated: **2026-05-17**

## ⚠️ 2026-05-17 update — historical Round 1/2 conclusion overturned

The earlier conclusion ("min_stop=60 is perfect, no parameter tuning needed") was a misjudgement. The real problem lies in
`merge_discharge_by_mass`: KY24LHT's telematics mass is locked at ~10 t (90-day std 0.12 t,
100% within ±200 kg), so all trips fall into the same mass cluster → merged into a single In Transit.
The long stop threshold (60 min) was only a secondary symptom.

**This round's (2026-05-17) changes**:
- `volvo_speed_03.speed_params.min_stop_duration_min`: 60.0 → **5.0** (aligned with the fleet)
- `vehicles.json::KY24LHT.min_cluster_gap_kg`: 1000.0 → **2000.0** (aligned with the fleet)
- `volvo_speed_03.merge_by_mass`: added → **false** (mass merging disabled, split retained)

**Effect**: 2024-06_2024-09 period 1 outbound → **184 driving legs**; 2024-12_2025-03 period 1 outbound → **52 driving legs**. Visual spot-check 2024-07-01 shows healthy multi-trip splitting.

The three sections below — "Pipeline parameters" / "Parameter rationale" / "Validation history" — are all old records from before v2.2.2, retained only for historical reference; the current parameters are as given in this section.

---


## Vehicle profile

- **Make/Model:** Volvo FM Electric
- **Application:** Long-distance trunk haulage (depot-based)
- **Battery capacity:** 540 kWh
- **Mass range:** 10-40t (typically 15-30t when loaded, ~10t unladen)
- **Data range:** 2024-06-11 to 2025-03-20

## Operational pattern

- **Depot-based:** Departs from depot, drives long trunk routes, returns for overnight charge
- **Multi-drop:** Some days feature multi-stop delivery patterns with short intermediate stops
- **Activity frequency:** Operates 2-4 days/week when active; many idle days (weekends, holidays)
- **Seasonal variation:** Most active Jun-Aug 2024; extended downtime Nov 2024 - Feb 2025 (3+ months idle); resuming Mar 2025
- **Typical active day:** 1-4 discharge trips separated by charging events; SOC drops 10-60% per trip
- **Energy per trip:** Ranges from ~5 kWh (short repo moves) to ~300 kWh (full-day long-haul)

## Pipeline parameters (volvo_speed_03)

```json
{
  "branch": "speed",
  "charge_params": {
    "plateau_window_min": 60,
    "min_soc_rise": 5.0,
    "min_energy_kwh": 5.0
  },
  "discharge_params": {
    "plateau_window_min": 15,
    "soc_rise_abort_pct": 3.0,
    "min_soc_drop": 5.0,
    "min_energy_kwh": 2.0
  },
  "speed_params": {
    "speed_threshold_kmh": 1.0,
    "min_stop_duration_min": 60.0,
    "min_trip_duration_min": 2.0,
    "min_soc_drop": 1.0,
    "min_energy_kwh": 1.0
  }
}
```

**min_cluster_gap_kg:** 1000 (from vehicles.json)

## Parameter rationale

### min_stop=60 min (key differentiator)
- This is 12x the default (5 min) and is the defining parameter for this pipeline
- Justified because the Volvo's operational pattern features natural long stops (>1 hr) between distinct trip legs (charge-drive-charge cycles)
- Short stops (<60 min) during multi-drop deliveries are intentionally merged into single trip segments
- This is the correct behaviour for energy analysis: a "trip" for this vehicle means the full driving period between depot/charging stops, not individual delivery stops

### min_soc_drop=1.0
- Low threshold appropriate for detecting short repo moves (~5-10 kWh)
- One edge case: 2024-10-25 showed potential over-segmentation at low SOC, but isolated

### min_cluster_gap_kg=1000
- Lower than default (2000) but works well; mass clusters are naturally well-separated for this vehicle

## Validation history

| Round | Date | Mode | Reviewed | OK | Issue | Issue rate |
|-------|------|------|----------|------|-------|-----------|
| 1 | 2026-03-24 | Quick | 60 | 57 | 3 | 5.0% |
| 2 | 2026-03-25 | Thorough | 220 | 220 | 0 | 0.0% |
| **Total** | — | — | **280** | **277** | **3** | **1.1%** |

## Known edge cases

1. **Under-segmentation at dense multi-stop days** (2024-07-25, 2024-08-07): When the vehicle makes many stops with <60 min gaps, trips get merged. This is by design but means payload changes mid-route are not captured as separate segments. Occurs ~2/280 days (0.7%).

2. **Over-segmentation at low SOC** (2024-10-25): When SOC is very low (<20%), small movements can create many micro-segments with marginal energy. min_soc_drop=1.0 is slightly too sensitive for these edge cases. Occurs ~1/280 days (0.4%).

3. **Extended idle periods:** The vehicle has multi-month idle periods where no segments are detected. This is correct behaviour but means the effective data yield (active days / total days) is low (~20%).

## Lessons learned

- **min_stop=60 is robust for depot-based long-haul operations.** The 1.1% issue rate across 280 figures confirms this parameter is well-tuned.
- **No parameter changes needed.** After comprehensive review, all parameters are validated.
- **High idle ratio is normal.** Do not treat the ~80% idle days as a data quality issue — this reflects the vehicle's actual operational pattern with seasonal variation.
