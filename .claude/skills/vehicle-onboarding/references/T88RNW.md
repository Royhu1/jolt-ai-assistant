# T88RNW — Renault E-Tech D Wide

## Vehicle characteristics

- Make/Model: Renault Trucks E-Tech D Wide (RIGID, 19t)
- VIN: VF620JEA7PB000178
- Nominal capacity: 211 kWh (SRF fuel_capacity)
- Effective capacity: ~190 kWh (algorithm auto-computed measured mean ~233 kWh/%)
- Operator: Welch's Transport (WELCH_TRANSPORT)
- Operation mode: city multi-drop distribution, 6-17 delivery legs per day
- SRF registration: "T88 RNW"
- SRF Organisation: "JOLT Welch-Volvo"
- Data range: 2024-06-11 ~ 2026-03-21 (1209 legs)

## Telematics column mapping

Consistent with the column structure of N88GNW (Renault D Wide Z.E.) and TA70WTL (Renault E-Tech T):

| Purpose | Column name | Notes |
|------|------|------|
| Speed | `wheel_based_speed` | 96% fill rate |
| SOC | `electricBatteryLevelPercent` | integer precision (1%) |
| Distance | `hr_total_vehicle_distance` | available |
| Mass | `gross_combination_vehicle_weight` | **all null — no mass data** |
| Total energy | `total_electric_energy_used_plugged_in_included` | ~20% of rows have values |
| Moving energy | `electric_energy_wheelbased_speed_over_zero` | ~20% of rows have values |
| AC energy | `battery_pack_ac_watthours` | ~20% of rows have values |
| DC energy | `battery_pack_dc_watthours` | ~20% of rows have values |
| Altitude | `gnss_altitude` | 96% fill rate |
| Latitude/Longitude | `latitude`, `longitude` | available |

## Algorithm choice

- **Pipeline**: `renault_speed` (speed-based discharge segmentation)
- **Speed column**: default `wheel_based_speed`
- **Reason**: speed data is complete and reliable; with integer SOC precision, speed-based is more stable

## Parameters

Use the `renault_speed` default parameters, no tuning needed:

| Parameter | Value | Notes |
|------|-----|------|
| speed_threshold_kmh | 1.0 | default |
| min_stop_duration_min | 5.0 | default, neatly distinguishes "traffic waiting" from "delivery stops" |
| min_trip_duration_min | 2.0 | default |
| min_soc_drop | 1.0 | default, 1% is the battery's minimum resolution |
| min_energy_kwh | 1.0 | default |
| min_cluster_gap_kg | 2000.0 | default (no mass data, not in effect) |

## SRF API auto-discovery

On first use, the SRF API automatically reads the following information:
- `v.fuel_capacity` = 211 → used directly as `nominal_kwh`
- `organisation.name` = "JOLT Welch-Volvo" → mapped to WELCH_TRANSPORT
- `v.description` = "2023 Renault E-Tech D Wide 19-t rigid electric (211 kWh)"
- `v.type` = RIGID, `v.weight_class` = 18.0

## Data characteristics

1. **City multi-drop distribution mode**: 6-17 trips per day, average 10.46 km/trip, around 112 km per day
2. **No mass data**: `gross_combination_vehicle_weight` is all null
3. **Limited SOC resolution**: at 211 kWh, 1% SOC ≈ 2.39 kWh, so short trips (<3 km) often show 1% SOC and an elevated EP
4. **22% of trips have only a 1% SOC change**: caused by short city-distribution distances, a genuine operational characteristic
5. **High EP outliers (1.7%)**: trips with EP > 3 kWh/km are all extremely short distances (<1 km), an SOC precision issue
6. **Charging types**: mainly DC Home charging, with a few "Charge Home" (AC/DC columns both 0 but SOC rises)

## Lessons learned

1. **The Renault column structure is highly consistent**: T88RNW has exactly the same column names as N88GNW and TA70WTL, so new Renault vehicles can reuse the column mapping directly
2. **Smaller-battery vehicles have coarser SOC precision**: at 211 kWh, 1% ≈ 2.39 kWh, making boundary effects more likely than for large-battery vehicles (540 kWh → 5.4 kWh)
3. **No mass data does not affect speed segmentation**: speed segmentation needs only the speed + SOC + energy columns
4. **The SRF API can auto-fetch capacity and operator**: fuel_capacity + organisation.name greatly reduces manual onboarding input
