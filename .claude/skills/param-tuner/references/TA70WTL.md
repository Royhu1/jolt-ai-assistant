# TA70WTL — Renault E-Tech T Reference Case

> Pipeline: `renault_speed` | Battery: 417 kWh nominal | Class: 19t rigid | Use: long-distance trunk delivery
> Report period: 2025-05-01 to 2026-03-21 (313 days)
> Last reviewed: 2026-03-26 (Round 2 — Full thorough, 313/313 figures)

## Vehicle characteristics

- **Make/Model**: Renault E-Tech T (electric rigid HGV)
- **Nominal capacity**: 417 kWh
- **Typical mass**: 15-35t loaded (early months show sparse mass data at 10-15t)
- **Operating pattern**: Mon-Fri trunk delivery, mostly idle weekends
- **Typical trips/day**: 1-6 discharge trips (median ~3)
- **Typical EP range**: 0.8-2.8 kWh/km (occasional outliers 0.5-4.8 kWh/km on very short trips)
- **Charging**: Mix of overnight and mid-day DC charging; 1-3 charge events per working day

## Optimal parameters (confirmed)

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
    "min_stop_duration_min": 5.0,
    "min_trip_duration_min": 2.0,
    "min_soc_drop": 1.0,
    "min_energy_kwh": 1.0
  }
}
```

These are the `default_speed` parameters — no vehicle-specific tuning was needed.

## Key findings

1. **Segmentation quality**: Excellent. Zero errors across 313 figures. All trip boundaries align precisely with speed zero-crossings.
2. **No parameter changes needed**: The default speed-based parameters work optimally for this vehicle's consistent delivery pattern.
3. **Data quality**: Good overall. Mass telemetry sparse in early months (May-Jun 2025), improves from Aug 2025. SOC and speed traces are reliable.
4. **Notable data gaps**: Nov 24 - Dec 5 (12 days, vehicle off-road), Christmas period (Dec 23 - Jan 4), and Feb 2026 reduced operations.
5. **One telemetry anomaly**: Mar 10 — total energy spike >2000 kWh (telemetry glitch, not a pipeline issue).

## Lessons for same-pipeline vehicles

- The `renault_speed` pipeline with default parameters is well-suited for Renault E-Tech T vehicles in regular trunk delivery operations.
- No need to adjust `min_stop_duration_min` — 5.0 min correctly separates multi-stop delivery trips without over-merging.
- The vehicle's consistent weekday-only pattern means idle/no-data days are concentrated on weekends and holidays — no risk of false positive trip detection on rest days.
- Mass data scatter in early months does not affect segmentation quality.
