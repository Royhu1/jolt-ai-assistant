# Evaluation criteria

Apply these when reviewing each validation figure across all four panels (workflow
step 3 / Phase 1 audit): symptom → diagnosis → parameter to adjust. Each parameter's
config location, default and effect is in `parameter-reference.md`.

## A. Discharge trips (Panel 1 + Panel 3)

| Symptom | Diagnosis | Parameter to adjust |
|---------|-----------|-------------------|
| Continuous driving split into multiple trips (short stops like traffic lights cause splits) | `min_stop_duration_min` too small | Increase `min_stop_duration_min` in `pipelines.json` -> speed_params |
| Distinct trips with long stop between them merged into one | `min_stop_duration_min` too large | Decrease `min_stop_duration_min` |
| Very short noise trips (seconds of sensor jitter) appear | `min_trip_duration_min` too small | Increase `min_trip_duration_min` |
| Valid short delivery trips missing from report | `min_trip_duration_min` too large | Decrease `min_trip_duration_min` |
| Trip shows SOC rising (includes charging period) | Trip boundary incorrect | Check speed data quality; review `speed_threshold_kmh` |
| Effective Capacity (C) far from nominal (>50% deviation) | Energy/SOC filter too loose | Adjust `cap_lo`/`cap_hi` via `nominal_kwh` |
| Energy anchors (triangles) missing on Panel 3 | Split by mass cleared anchors | Verify `_recompute_anchors` runs after split/merge |
| EP value unreasonably high or low | Odometer or energy data issue | Check raw data quality for that leg |

## B. Mass clustering (Panel 4)

| Symptom | Diagnosis | Parameter to adjust |
|---------|-----------|-------------------|
| Clearly different load levels (e.g. 20t vs 28t) shown as same cluster | Gap too large | Decrease `min_cluster_gap_kg` in `vehicles.json` |
| Normal sensor noise (~500kg) causes unnecessary cluster splits and trip splits | Gap too small | Increase `min_cluster_gap_kg` |
| Mass annotation shows unreasonable values (e.g. 0 or >50t) | Sensor outlier | Check raw mass data; may need outlier filtering |

## C. Charging events (Panel 1 + Panel 2)

| Symptom | Diagnosis | Parameter to adjust |
|---------|-----------|-------------------|
| Charge segment includes driving period (speed > 0) | `plateau_window_min` too large | Decrease `plateau_window_min` in charge_params |
| Tiny charge events (dSOC 1-2%) cluttering report | `min_soc_rise` too small | Increase `min_soc_rise` in charge_params |
| Valid charge event missing | `min_soc_rise` or `min_energy_kwh` too large | Decrease thresholds |
| AC+DC delta and Charger Meter mismatch | Charger matching or time offset issue | Check charger_transactions data |
