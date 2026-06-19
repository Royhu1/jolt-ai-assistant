# YT21EFD — onboarding case study (Scania P410, DIESEL)

> First **Scania** diesel onboarded; second diesel overall (after WU70GLV / DAF).
> Worked example for the **diesel / SRF-Logger** onboarding path. Onboarded 2026-06-18.

## 1. Vehicle specs

| Field | Value |
|-------|-------|
| Registration | `YT21EFD` (SRF reg with space: `YT21 EFD`) |
| Make / model | Scania P410 (2021 artic, 12.7 L) |
| VIN | YS2P4X20005617908 |
| Fuel | **DIESEL** (no battery; `fuel_capacity` = None in SRF) |
| Weight class | 40.0 t (ARTIC) |
| SRF vehicle URI | https://data.csrf.ac.uk/api/vehicles/239 |
| Operator | **William Jackson Food → `WJF`** (see §2) |
| Data range | 2025-08-29 → 2026-06-17 (2,891 legs at discovery) |
| Leg source | **100 % `SRFLOGGER_V1`** (`leg.trip.source`) |

## 2. Operator (important gotcha)

SRF `organisation.name` for this dedicated vehicle = **"William Jackson Food"**. This is
**NOT a new operator** — the fleet already carries the code **`WJF`** (= **W**illiam
**J**ackson **F**ood), which appears as the *round-robin trial token* `"WJF"` on
EX74JXW / YN25RSY / EX74JXY legs (colour lime `#A7CC01`, trailer 7000). The same company
therefore reaches the operator system via **two** SRF signals — the dedicated `org.name`
("William Jackson Food") here, and the round-robin token ("WJF") on shared vehicles — and
both must resolve to the **one** code `WJF` so downstream figures/PDF/dashboard/stats
aggregate it as a single operator. Wiring: `operators.py::_SRF_ORG_TO_CODE` maps
`"William Jackson Food" → "WJF"`; `vehicles.json` YT21EFD `operators` pins `WJF`
(2025-08-29 → open). **Lesson for future onboarding:** before minting a new operator code
from a dedicated `org.name`, check whether its initials already exist as a round-robin
token in `_TRIAL_OP_TO_CODE` / `KNOWN_OPERATOR_CODES`.

## 3. Data source & column mapping (Logger J1939, not FPS)

A diesel's **FPS telematics** leg here is IMU-only (`get_raw_data()` returns `journey
info.` + rotation/accelerometer triplets — no speed/fuel). All useful signals live in the
**SRF Logger** (`SRFLOGGER_V1`) J1939 channels, pulled per leg via
`leg.get_data_frame(<channel>, resolution="1s")`. YT21EFD's channels were **byte-identical
to WU70GLV's** (J1939 names are OEM-independent):

| Purpose | Channel | Column (→ `vehicles.json` key) |
|---------|---------|-------------------------------|
| Speed | `CCVS` | `CCVS wheel based vehicle speed` → `speed_col` |
| Speed fallback | `2` (GPS) | `2 speed` → `speed_col_fallback` |
| Fuel (cumulative) | `LFC` | `LFC engine total fuel used` → `fuel_energy_col` (also `LFC trip fuel`) |
| Fuel rate | `LFE` | `LFE fuel rate` → `fuel_rate_col` |
| Distance | `VDHR` | `VDHR hr total vehicle distance` → `distance_col` |
| Mass | `CVW` | `CVW gross combination vehicle weight` → `mass_col` |
| Ambient temp | `AMB` | `AMB ambient air temperature` → `ambient_temp_col` |
| Altitude / GPS | `2` | `2 altitude` → `altitude_col`, `2 longitude/latitude` |
| Weather station | `7` | temperature/pressure/humidity/wind speed+dir/cloud cover |

Also available (unused by the current pipeline, but present): `VW` (trailer / cargo / axle
weight), `EEC1` (engine speed, % torque), `EEC2` (accelerator pedal).

## 4. Algorithm / config choices

- **Reused the `daf_diesel_logger` pipeline verbatim** — it is a routing label; all channel
  names live in `vehicles.json`, so no new pipeline was needed. `fuel_type: DIESEL`,
  `leg_source: SRFLOGGER_V1`, `diesel_lhv_kwh_per_l: 10.0`.
- Params copied from WU70GLV (diesel defaults, a starting point): `min_cluster_gap_kg 2000`,
  `min_trip_duration_min 2`, `min_trip_distance_km 1`, `min_stop_duration_min 5`,
  `speed_threshold_kmh 1.0`.

## 5. Data quirks

- **Weather may be pre-filled from Logger channel 7** (on-board weather station) → the
  diesel pipeline reads it before any OpenWeather patch. Check driving-leg
  `Average Temperature (C)` coverage first; only OpenWeather-backfill the gaps.
- `fuel_capacity` is None (diesel) — no `nominal_kwh` / SOC concepts apply.
- Discovery method (reusable): iterate `srf.legs.find_all(... 'trip.vehicle.registration')`,
  keep legs whose `leg.trip.source` starts with `SRFLOGGER`, then inspect `leg.types` +
  `leg.get_data_frame(ch)` columns.
