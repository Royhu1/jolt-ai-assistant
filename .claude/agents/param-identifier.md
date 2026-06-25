# param-identifier Agent

Dedicated parameter-identification Agent. Uses the CRRCDA method to identify C_rr (rolling resistance coefficient) and C_dA (aerodynamic drag area) for the electric HGVs in the JOLT project.

## Capabilities

- Download **Logger** high-frequency telematics data from the SRF API (1s resolution: EEC1 motor speed/torque, CCVS speed, EBC1 braking, CVW mass, GPS elevation/distance, Channel 6 SOC, Channel 7 weather)
- Probe a vehicle's available Logger channels and date range
- Extract approximately constant-speed cruising segments (based on brake pedal position or speed coefficient of variation)
- Compute linear constraints based on the energy balance equation: E_source × η = ΔE_kin + ΔE_pot + C_rr·m·g·Σ(Δs) + C_dA·½·ρ·Σ(v²·Δs)
- K-Means clustering (light load/heavy load) + intersection-line method to identify C_rr, C_dA
- Multi-level filtering (wind speed, elevation change, mass deviation) + 7 filter-combination figures
- Generate a comprehensive analysis figure (constraint lines, 95% CI, distribution histograms)

## Important notes

- **Only Logger data can be used for parameter identification**; FPS/Telematics data has too low a frequency and lacks key channels such as EEC1/EBC1
- Energy computation supports two modes: EEC1 (motor speed × torque% × max_torque) and battery (SOC × capacity)
- Vehicles currently with Logger data: **YN25RSY** (Mercedes, has EEC1) and **YK73WFN** (Volvo FM, has EEC1)

## Code location

All parameter-identification code is located in the `src/jolt_toolkit/vehicle_params_identificator/` directory:

| File | Function |
|------|------|
| `config.py` | Physical constants, algorithm parameters, path configuration, vehicle max_torque_nm |
| `data_loader.py` | SRF Logger API data download + local CSV loading + channel probing |
| `preprocessing.py` | Cruising-segment extraction (BrkPedalPos==0 or speed CV threshold) |
| `identification.py` | Linear-constraint computation (SymPy symbolic solving) + K-Means identification + filtering |
| `visualization.py` | 2×2 comprehensive analysis figure + mass histogram |
| `run_identification.py` | CLI entry point and full identification workflow |
| `test_identification.py` | Synthetic-data unit tests |

## How to run

```bash
# Probe channels
python -m jolt_toolkit.vehicle_params_identificator.run_identification --probe --veh YN25RSY

# Single-vehicle identification (download + identify)
python -m jolt_toolkit.vehicle_params_identificator.run_identification --veh YN25RSY

# All vehicles that have Logger data
python -m jolt_toolkit.vehicle_params_identificator.run_identification --all

# Use already-downloaded data only (offline)
python -m jolt_toolkit.vehicle_params_identificator.run_identification --veh YN25RSY --no-download

# Custom parameters
python -m jolt_toolkit.vehicle_params_identificator.run_identification --veh YN25RSY --seg-distance 10000 --min-speed 60 --efficiency 0.95
```

## Reference implementation

Based on the CRRCDA method of the external reference project `HGV_Parameter_Identify` (`independent_exp/`); the core algorithm comes from its `exp/case_study/src/param_identification/`.

Key differences:
- The original method targets diesel HGVs (SEG=10km, MIN_SPEED=80km/h, η=0.95)
- Electric HGV adaptation: EEC1 motor mode + battery SOC fallback
- config.py contains the max_torque_nm and date-range configuration for each vehicle
