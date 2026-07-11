# Data contract — configuration, loading, filters

## Configuration

All vehicle metadata (make, effective capacity, tractor weight, company assignment, colours) is in:
`src/jolt_toolkit/configs/plot_config.json`

Key fields used:

- `vehicle_specs.{REG}.make` — OEM name
- `vehicle_specs.{REG}.effective_capacity_kwh` — for Max Range calculation
- `vehicle_specs.{REG}.tractor_weight_kg` — for Payload+Trailer
- `company_assignment.simple.{REG}` — company label
- `company_assignment.round_robin.{REG}` — time-based company assignment
- `trailer_weights_kg.{company}` — trailer weight per company
- `colors.vehicle_override.{REG}` — per-vehicle colour
- `colors.company.{company}` — per-company colour
- `colors.oem_by_make.{make}` — OEM colour by make
- `oem_anonymization.{make}` — anonymised OEM label (e.g. "OEM A")
- `driving_leg_types` — list of Leg Type values to include

Changes to `plot_config.json` itself are owned by the `jolt-toolkit-dev` agent — route
config edits there; this skill only reads it.

## Data loading

Read from `excel_report_database/{version}/{REG}/jolt_report_{REG}_{YYYYMMDD}_{YYYYMMDD}.xlsx`, sheet `Report`.

Required columns:

- `Vehicle Mass (kg)` — total vehicle mass
- `Energy Performance (kWh/km)` — energy per km (standard)
- `Battery Capacity (kWh)` — for reference
- `Distance (km)` — leg distance
- `Leg Type` — filter to `driving_leg_types` only
- `Start Time (UTC)` — for company round-robin assignment

Derived columns:

- `Max Range (km)` = `effective_capacity_kwh / Energy Performance (kWh/km)`
- `Payload+Trailer (kg)` = `Vehicle Mass - tractor_weight_kg + trailer_weight_kg`

## Data quality filters (apply before plotting)

- `Leg Type in driving_leg_types`
- `Energy Performance > 0.1` and `<= 3.0`
- `Vehicle Mass > 0` and `<= 42000`
