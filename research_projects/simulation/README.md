# Simulation — Electric Heavy-Truck Energy Consumption Simulation Experiments

> **Current version: `v2.2.3`** (see `pyproject.toml`)

## Directory overview

This directory contains physics-based energy consumption simulation experiments, used to quantitatively analyse the independent contribution of each influencing factor to the Energy Performance (kWh/km) of electric heavy trucks.

It is complementary to the measured-data analysis in the `data_analysis_workspace/` directory: measured analysis is constrained by the multi-factor coupling and measurement noise in real data, whereas simulation experiments can precisely isolate each factor under controlled conditions.

## Experiment design

→ [`results/EP_simulation_report.md`](results/EP_simulation_report.md) — full simulation report (physics derivation + formulae + baseline parameters + simulation results, including the §1.5 Case 1/2/3 driving-cycle correction framework, §2.2.3 two-dimensional heatmaps, §2.3 non-cruise analysis)
→ [`results/EP_simulation_report_en.md`](results/EP_simulation_report_en.md) — English-language report
→ [`results/exp9_distance_correction_report.md`](results/exp9_distance_correction_report.md) — Exp 9 distance-correction topical report

### Experiment list

| No. | Experiment | Key variable | Coefficient / main conclusion |
|------|------|---------|----------------|
| Exp 1 | Vehicle mass | GVW 10,000–44,000 kg | α₁ = 1.434×10⁻⁵ kWh/(km·kg), R² ≈ 1.000 |
| Exp 2 | Wind speed | 0–15 m/s, random wind direction | α₂ = 5.85×10⁻⁴ kWh/(km·(m/s)²) |
| Exp 3 | Ambient temperature | −5°C to 35°C (Arrhenius battery efficiency) | Non-linear, +7.1% at −5°C |
| Exp 4 | Road surface condition | Dry / wet / snowy ($C_{rr}$ 0.003–0.011) | α₃ = 127.8 kWh/(km per unit Crr) |
| Exp 5 | Elevation change | Net height difference ±200 m | α₄⁺ = 12.79×10⁻⁴, α₄⁻ = 10.36×10⁻⁴ kWh/(km·m) |
| Exp 6 | Number of stop-starts | 0–30 times, multi-mass comparison | α₅(m), negative at 18 t (turns positive above about 30 t) |
| Exp 7 | Vehicle configuration | CdA 3.9–8.5 m² | α₇ = 0.118 kWh/(km·m²) |
| Exp 8 | EP vs Mass multi-factor + sensitivity | All factors × GVW 10–44 t | Curve families + tornado chart (42 t baseline, road surface > CdA > elevation > temperature > wind > stop-start)|
| Exp 9 | Event-level distance correction | Any (v_entry → v_low → v_exit) event | $EP_{corr} = E/(d + \sum \Delta s_i)$, η_dt cancelled algebraically |

**Supplementary simulations** (not counted as numbered Exp, but included in the report):

| Module | Script | Corresponding report section |
|------|------|-------------|
| Two-dimensional coupling heatmaps | `exp_heatmaps.py` | §2.2.3 — (m, Crr) / (m, Δh) / (CdA, V_wind) / (m, T) |
| Non-cruise basics | `exp_non_cruise.py` | §2.3.2 $N_a$ sweep, §2.3.3 driving style, §2.3.4 $\eta_{regen}$ sweep, §2.3.5 $f_{cycle}$ zero-error validation |
| Non-cruise speed profile | `exp_noncruise_profile.py` | §2.3 opening illustration ($N_a=N_d=5$, 90/80 km/h mix)|
| Exp 6 speed profile | `exp6_speed_profile_n5.py` | Exp 6 illustration (n_stop = 5 speed-distance profile)|
| EP vs Mass triptych | `exp_ep_vs_mass_new.py` | §2.3 — DC event count / driving style / regen efficiency, three curve families |

## Baseline scenario

- **Distance**: 100 km, pure cruise (90 km/h throughout)
- **Baseline vehicle**: parameters from IEEE ITSC 2026 [1] (GVW 42 t, 90 km/h, CdA 6.16 m², Crr 0.00465)
- **Baseline EP₀ = 1.327 kWh/km** (42 t, no wind, dry road, 20°C, flat road, no stops)

## Directory structure

```
research_projects/simulation/
├── README.md                              ← this file
├── EP_simulation_report.pdf                ← report PDF export (auto-generated)
├── run_all.py                             ← run all experiments in one click, generate the report
├── models/
│   └── vehicle_physics.py                ← shared physics model (compute_ep + re-exported eta_bat + style constants)
├── experiments/
│   ├── exp1_mass.py                       ← EP vs mass
│   ├── exp2_wind.py                       ← EP vs wind speed
│   ├── exp3_temperature.py                ← EP vs temperature
│   ├── exp4_road_surface.py               ← EP vs road surface condition
│   ├── exp5_elevation.py                  ← EP vs elevation
│   ├── exp6_stop_start.py                 ← EP vs number of stop-starts
│   ├── exp6_speed_profile_n5.py           ← Exp 6 illustration: n_stop = 5 speed profile
│   ├── exp7_cda.py                        ← EP vs aerodynamic drag area
│   ├── exp8_ep_vs_mass_factors.py         ← EP vs Mass factor curve families + sensitivity tornado
│   ├── exp9_distance_correction.py        ← event-level distance correction (any v_entry→v_low→v_exit)
│   ├── exp_heatmaps.py                    ← two-dimensional coupling heatmaps (§2.2.3)
│   ├── exp_non_cruise.py                  ← non-cruise main experiment (§2.3.2–§2.3.5)
│   ├── exp_noncruise_profile.py           ← non-cruise speed profile illustration (§2.3)
│   └── exp_ep_vs_mass_new.py              ← EP vs Mass triptych (DC / driving style / η_regen)
└── results/
    ├── figures/                           ← PNG figures (300 DPI, publication grade)
    │   ├── exp1_mass.png ~ exp7_cda.png          ← single-factor experiment figures (Exp 1–7)
    │   ├── exp6_noregen_compare.png              ← Exp 6 auxiliary: no-regen comparison
    │   ├── exp6_speed_profile_n5.png             ← Exp 6 speed-distance profile
    │   ├── ep_vs_mass_wind.png                   ← Exp 8: EP-Mass wind-speed family
    │   ├── ep_vs_mass_temperature.png            ← Exp 8: EP-Mass temperature family
    │   ├── ep_vs_mass_road.png                   ← Exp 8: EP-Mass road-surface family
    │   ├── ep_vs_mass_elevation.png              ← Exp 8: EP-Mass elevation family
    │   ├── ep_vs_mass_stops_regen.png            ← Exp 8: EP-Mass stop-start (η_regen=0.90)
    │   ├── ep_vs_mass_stops_halfregen.png        ← Exp 8: EP-Mass stop-start (η_regen=0.50)
    │   ├── ep_vs_mass_stops_noregen.png          ← Exp 8: EP-Mass stop-start (η_regen=0)
    │   ├── ep_vs_mass_cda.png                    ← Exp 8: EP-Mass CdA family
    │   ├── sensitivity_tornado.png               ← Exp 8: tornado sensitivity chart
    │   ├── ep_vs_mass_dc.png                     ← triptych: different DC event counts
    │   ├── ep_vs_mass_driver.png                 ← triptych: different driving styles
    │   ├── ep_vs_mass_regen.png                  ← triptych: different regen efficiencies
    │   ├── heatmap_m_crr.png                     ← §2.2.3 heatmap: (m, Crr)
    │   ├── heatmap_m_dh.png                      ← §2.2.3 heatmap: (m, Δh)
    │   ├── heatmap_cda_wind.png                  ← §2.2.3 heatmap: (CdA, V_wind)
    │   ├── heatmap_m_temp.png                    ← §2.2.3 heatmap: (m, T)
    │   ├── baseline_speed_profile.png            ← baseline pure-cruise speed profile
    │   ├── exp_noncruise_profile_n5.png          ← §2.3 non-cruise profile (N_a=N_d=5)
    │   ├── exp_noncruise_a.png ~ exp_noncruise_d.png   ← §2.3 Exp A/B/C/D validation
    │   ├── exp_noncruise_232.png                 ← §2.3.2: $N_a$ sweep
    │   ├── exp_noncruise_233.png                 ← §2.3.3: driving style
    │   ├── exp_noncruise_234_regen.png           ← §2.3.4: $\eta_{regen}$ sweep
    │   ├── exp_noncruise_235.png                 ← §2.3.5: $f_{cycle}$ zero-error validation
    │   ├── exp9_distance_correction.png          ← Exp 9 main figure
    │   ├── exp9_mixed_trip.png                   ← Exp 9 mixed-trip example
    │   ├── exp9_asymmetric_events.png            ← Exp 9 asymmetric-event validation
    │   └── exp9_regen_sweep.png                  ← Exp 9 η_regen sweep
    ├── tables/                            ← CSV data files
    │   ├── exp1_mass.csv ~ exp7_cda.csv          ← Exp 1–7 data tables
    │   ├── exp9_distance_correction.csv          ← Exp 9 data table
    │   ├── exp_noncruise_232.csv                 ← §2.3.2 data
    │   ├── exp_noncruise_233.csv                 ← §2.3.3 data
    │   └── exp_noncruise_234_regen.csv           ← §2.3.4 data
    ├── notebook/                          ← reference Jupyter notebooks (nb1–nb4)
    ├── EP_simulation_report.md            ← auto-generated Chinese report
    ├── EP_simulation_report_en.md         ← auto-generated English report
    └── exp9_distance_correction_report.md ← Exp 9 topical report
```

> **Note (toolkit v2.2.4):** the canonical implementation of `eta_bat` (the Arrhenius
> battery-efficiency model) now lives in `jolt_toolkit.analysis.physics`;
> `models/vehicle_physics.py` re-exports it for backward compatibility (sub-project
> independence convention).

## How to run

```bash
cd <project_root>
python research_projects/simulation/run_all.py
```

Run a single experiment:

```bash
python research_projects/simulation/experiments/exp1_mass.py
```

## Results summary

The report draft is auto-generated to: [`results/EP_simulation_report.md`](results/EP_simulation_report.md)

**Final EP prediction formula** (superposition of factors, baseline T₀ = 20°C):

$$EP = c_0 + \alpha_1 \cdot m + \alpha_2 \cdot V_{wind}^2 + f_T(T) + \alpha_3 \cdot C_{rr} + f_h(\Delta h) + \alpha_5(m) \cdot n_{stop} + \alpha_7 \cdot C_dA$$

**Key findings**:
- All linear factors (mass, Crr, CdA) have R² = 1.000, strictly linear
- The ratio of the uphill/downhill coefficients |α₄⁺/α₄⁻| = 1.235 = 1/(η_drivetrain × η_regen), in exact agreement with theory
- The stop-start coefficient α₅ becomes positive above about 30 t; under light load, stopping actually saves energy (aerodynamic drag saving > KE loss)
- The two-dimensional heatmaps (§2.2.3) quantify the four second-order mixed partial derivatives (m, Crr) / (m, Δh) / (CdA, V_wind) / (m, T)
- The non-cruise simulation (§2.3) proves that the $f_{cycle}$ correction projects any cycle back to $EP_{c90}$ with zero error at $\eta_{regen}=0$

## Correspondence with measured analysis

The simulation results are used in the measured pipelines of `data_analysis_workspace/` in two ways:

**(A) Factor-isolation validation** (the analytical coefficients of Exp 1–7 serve as "reference lines" for the measured regression):

| Measured analysis step | Corresponding simulation experiment |
|-------------|-------------|
| `ep_cruise_correction.py` §3.1 Wind filter | Exp 2 (quantitative wind-speed analysis) |
| `ep_cruise_correction.py` §3.1 Temp filter | Exp 3 (temperature Arrhenius efficiency) |
| `ep_cruise_correction.py` §3.1 Dry weather | Exp 4 (road surface condition) |
| `ep_cruise_correction.py` §3.1 Elev corrected | Exp 5 (elevation validation) |
| `ep_cruise_correction.py` Case 3's $f_{no\_cruise}$ | Exp 6 (number of stop-starts) + Exp 9 (event distance correction) |
| Full-factor sensitivity ranking (measured tornado comparison) | Exp 8 (sensitivity tornado) |

**(B) Case 1 / 2 / 3 driving-cycle correction framework** (`EP_simulation_report.md` §1.5):

The three-tier case-by-case driving-cycle correction strategy derived in `§1.5` is strictly implemented on measured data by `data_analysis_workspace/driving_cycle_correction/scripts/ep_cruise_correction.py`:

| Simulation Eq. | Measured implementation location | Description |
|---------------|-------------|------|
| Eq.22 (standard-cycle EP) | inside `ep_c90_case3()` | $EP_{c90}^{theo,flat}$ for pure 90 km/h flat-road cruise |
| Eq.27 (Case 1 direct measurement) | `ep_c90_case1()` | zero model parameters, read $\sum E_k / \sum d_k$ directly from the ≈90 km/h CC segments in the trip |
| Eq.28 (Case 2 simulation ratio mapping) | `ep_c90_case2()` | $EP_{cruise@v}$ × segment-level simulation ratio ($\sum E_{sim@90}/\sum E_{sim@v}$). Depends on $C_dA$, $C_{rr}$, $m$ ($\eta$ cancels in the ratio) |
| Eq.29 (Case 3 model ratio) | `ep_c90_case3()` | model ratio method $EP_{total}^{telematics} \cdot (EP_{c90}^{theo}/EP_{total}^{theo})$, depends on all vehicle parameters |

**Difference between Exp 9 and §1.5 Case 1/2/3**: Exp 9 (`exp9_distance_correction_report.md`) is "event-level distance correction" —— it converts the KE loss of each stop-start/decelerate-accelerate event into an equivalent "extra distance", correcting the total distance to $d_{corr} = d + \sum\Delta s_i$, so that differences in driver style can be cancelled via $EP_{corr} = E / d_{corr}$, and η_drivetrain is cancelled algebraically in the formula. It and §1.5 are **two orthogonal routes**: §1.5 follows the "case-by-case segmented integration" route, while Exp 9 follows the "equivalent distance" route. In practice, `ep_cruise_correction.py` uses the §1.5 scheme; `exp9_distance_correction_report.md` is an optional implementation as an alternative method for Case 3 (not yet wired into measured data).

---

> [1] J. Hu, "A Traffic-Aware Driving Cycle Predictor for Heavy Goods Vehicles," IEEE ITSC 2026.
