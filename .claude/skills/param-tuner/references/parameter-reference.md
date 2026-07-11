# Parameter reference

Every tunable segmentation parameter: where it lives, its default, and what it does.
The symptom → parameter mapping is in `evaluation-criteria.md`. Per the guidelines
(`static/core/principles.md`), each vehicle has its own pipeline in `pipelines.json`,
so changes to one vehicle's pipeline do not affect others.

| Parameter | Config location | Default | Effect |
|-----------|----------------|---------|--------|
| `min_stop_duration_min` | pipelines.json -> speed_params | 5.0 | Zero-speed duration (min) to end a trip |
| `min_trip_duration_min` | pipelines.json -> speed_params | 2.0 | Minimum trip duration (min); shorter trips discarded |
| `min_soc_drop` | pipelines.json -> speed_params | 1.0 | Minimum SOC decrease (%) for a valid trip |
| `min_energy_kwh` | pipelines.json -> speed_params | 1.0 | Minimum energy consumption (kWh) for a valid trip |
| `speed_threshold_kmh` | pipelines.json -> speed_params | 1.0 | Speed above this = moving (km/h) |
| `min_cluster_gap_kg` | vehicles.json -> vehicle config | 2000.0 | Minimum mass difference (kg) between clusters |
| `plateau_window_min` | pipelines.json -> charge_params | 60 | SOC plateau window for charge detection (min) |
| `min_soc_rise` | pipelines.json -> charge_params | 5.0 | Minimum SOC rise (%) for a valid charge event |
