# TA70WTL — Renault Trucks E-Tech T

## Vehicle characteristics

- Make/Model: Renault Trucks E-Tech T (ARTIC)
- Nominal capacity: 417 kWh
- Effective capacity: ~375 kWh (90%, algorithm auto-computed mean 379.2 kWh)
- Operator: Welch's Transport
- Operation mode: inter-city distribution, predominantly tractor-only parking during low-usage periods
- SRF registration: "TA70 WTL"
- Data range: 2025-04-30 ~ 2026-03-20 (312 FPS legs, 0 Charger, 80 Logger legs limited to 2025-06~08)

## Telematics column mapping

Exactly consistent with N88GNW (Renault D Wide Z.E.):

| Purpose | Column name | Notes |
|------|------|------|
| Speed | `wheel_based_speed` | consistent with the Volvo/Scania/Renault standard |
| SOC | `electricBatteryLevelPercent` | integer precision (1%) |
| Distance | `high_resolution_total_vehicle_distance` | available |
| Mass | `gross_combination_vehicle_weight` | available, tractor ~10000 kg |
| Total energy | `total_electric_energy_used_plugged_in_included` | available |
| Moving energy | `electric_energy_wheelbased_speed_over_zero` | available |
| AC energy | `battery_pack_ac_watthours` | available |
| DC energy | `battery_pack_dc_watthours` | available |
| Altitude | `gnss_altitude` | available |
| Latitude/Longitude | `latitude`, `longitude` | available |

## Algorithm choice

- **Pipeline**: `renault_speed` (speed-based discharge segmentation)
- **Speed column**: default `wheel_based_speed` (no `speed_col` override needed)
- **Reason**: speed data is complete and reliable; with integer SOC precision, speed-based is more stable

## Parameters

Use the `renault_speed` default parameters, no tuning needed:

| Parameter | Value | Notes |
|------|-----|------|
| speed_threshold_kmh | 1.0 | default |
| min_stop_duration_min | 5.0 | default |
| min_trip_duration_min | 2.0 | default |
| min_soc_drop | 1.0 | default |
| min_energy_kwh | 1.0 | default |
| min_cluster_gap_kg | 2000.0 | default |

## Data characteristics

1. **Low usage in February**: only 4 of 29 days have discharge segments (02-02, 02-09, 02-10, 02-17), the rest being idle/charging days
2. **All tractor-only**: all mass readings ~10000 kg (< 13000 kg threshold), no trailer data
3. **Brief yard movement**: on 02-11, 02-26 brief speed spikes (~13 km/h) appear but SOC is unchanged, correctly filtered out by min_soc_drop
4. **Charging pattern**: predominantly low-power overnight top-ups (+25~47 kWh), with the occasional large charge (02-03: +210 kWh)
5. **Limited Logger data**: only 80 legs over 2025-06 ~ 2025-08, with no Logger thereafter

## Lessons learned

1. **The Renault column structure is highly consistent**: TA70WTL has exactly the same column names as N88GNW, so new Renault vehicles can reuse the column mapping directly
2. **Default parameter validation during low-usage periods**: even with few active days, the default `renault_speed` parameters still work correctly, with no over-segmentation
3. **Yard movement filtering is effective**: `min_soc_drop=1.0` successfully filters out brief movements (speed spikes but unchanged SOC)
