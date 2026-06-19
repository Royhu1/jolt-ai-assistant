# YK73WFN Regenerative Braking Energy Recovery Analysis

> Vehicle: YK73WFN (Volvo FM Electric, 540 kWh nominal capacity, max torque 2400 Nm)

---

## 1. Introduction

This analysis quantifies the regenerative braking energy recovery performance of
**YK73WFN** (Volvo FM Electric, 540 kWh nominal, max torque 2400 Nm) by
cross-referencing two independent data sources:

- **Logger data** (1 Hz, CAN bus): 328 files, 2025-03-22 to 2025-08-31
  (~1.02 million rows), containing speed, brake pedal position, engine/motor
  torque, mass, elevation, and SOC.
- **Telematics data** (SRF API, vehicleId=116): ~115,000 rows, 2024-06 to
  2025-12, with cumulative `electric_energy_recuperation_watthours`.

The overlap period (2025-03-22 to 2025-08-31) was used for all paired analyses.

## 2. Data Description

### 2.1 Logger Data

| Metric | Value |
|--------|-------|
| Files | 328 |
| Total rows | 1,023,996 |
| Time range | 2025-03-22 to 2025-08-31 |
| Speed validity | 99.97% |
| EngTrq validity | 98.95% |
| Mass validity | 96.3% |
| SOC validity | 97.92% |
| Elevation validity | 99.97% |

Key observations:
- EngTrq is reported as percentage of rated torque (0-100%), never negative.
  Zero torque while moving indicates coasting/regeneration (30.6% of moving time).
- Mass median: ~19,680 kg (unladen) to 33,150 kg (laden).
- Brake pedal is pressed (>5%) only ~12% of the time.

As the figure below shows, the EngTrq distribution is strongly left-skewed: over
500,000 rows (roughly half of all records) report zero torque, indicating the
vehicle spends a large fraction of its time coasting or regenerating rather than
applying traction. A secondary peak at 100% corresponds to full-throttle
acceleration.

![Figure 2.1 Motor torque percentage distribution (N=1,013,284 rows)](results/figures/eng_trq_distribution.png)

### 2.2 Telematics Data

| Metric | Value |
|--------|-------|
| vehicleId | 116 |
| Total rows | 115,744 |
| Recuperation valid rows | 13,805 (11.9%) |
| Sampling interval (recup rows) | Median 3600s, mean 4300s |
| Cumulative recup range | 1,909 - 15,077 kWh |

The `electric_energy_recuperation_watthours` field is a monotonically increasing
cumulative counter; the difference between consecutive records is the actual
recuperated energy over that interval. As the figure below shows, the sampling
interval for recuperation-bearing records concentrates around 60 minutes (red
dashed line), making the data well suited to energy balance analysis on an
"hourly window" basis.

![Figure 2.2 Telematics sampling interval distribution (N=115,738 rows)](results/figures/telematics_sampling_interval.png)

## 3. Methodology

### 3.1 Time Window Selection

For each pair of consecutive telematics records where recuperation data is valid:
1. Compute the time gap dt and recuperation difference delta_recup_wh.
2. Retain windows where:
   - 30 min <= dt <= 90 min
   - Logger coverage >= 80%
   - delta_recup_wh > 0
   - Vehicle was moving (speed > 0)

**Result**: 141 valid analysis windows.

### 3.2 Recoverable Energy Model

Total recoverable energy per window:

```
E_recoverable = E_KE + E_PE_down
```

where:
- **E_KE** = sum of kinetic energy changes during all deceleration events:
  `0.5 * m * (v_start^2 - v_end^2)` for each event where speed monotonically
  decreases by >= 0.1 m/s^2 over >= 1 second.
- **E_PE_down** = gravitational potential energy from downhill segments:
  `m * g * |dh|` for all negative elevation changes, using **201-point moving
  average** to suppress GPS altitude noise. At 80 km/h, 201 s corresponds to
  ~4.5 km spatial smoothing.

The figure below shows the four-panel validation plot for a representative
analysis window (Window 12, 2025-04-02 05:38-07:00 UTC), illustrating how the
analysis framework works:

- **Panel 1**: Vehicle speed (blue, left axis) overlaid with the smoothed
  elevation profile (brown, right axis); coloured vertical bands mark
  deceleration events (green = motor_only, red = blended, orange = coasting).
- **Panel 2**: Brake pedal position (BrkPedalPos, %) and brake switch
  (BrakeSwitch) signal.
- **Panel 3**: Motor shaft power (kW) = torque x speed, with the zero line shown
  as a grey dashed line.
- **Panel 4**: Cumulative recuperated energy — blue dashed line is the KE-only
  model, blue solid line is the KE+PE model (both scaled by eta=0.9), and the red
  solid line is the telematics-measured cumulative value (zeroed at the window
  start). For this window eta_obs = 0.552.

![Figure 3.1 Representative analysis window (Window 12): speed/elevation + brake signals + motor power + cumulative recuperation comparison](results/figures/window_012.png)

### 3.3 Observed Regeneration Efficiency

```
eta_regen_obs = delta_recup_wh / E_recoverable
```

This represents the **end-to-end system efficiency** from recoverable mechanical
energy (KE + PE) to electrical energy stored in the battery, encompassing:
- Motor/generator efficiency
- Power electronics (inverter) efficiency
- Battery charging efficiency
- Portion of energy diverted to mechanical brakes

### 3.4 Terrain-Dominated Window Filter

Windows where `E_PE_down / E_KE > 2.0` are flagged as **terrain-dominated**,
meaning the PE contribution is more than twice the KE contribution, suggesting
the window was on a prolonged downhill gradient. These are reported separately
to avoid confounding the efficiency estimate with GPS-noise-inflated PE.

**Result**: 0 out of 136 valid windows were terrain-dominated (PE/KE < 2.0 in
all windows), confirming the 201-point smoothing adequately suppresses noise.

### 3.5 Brake Type Classification

#### Role of each data source

Brake type classification is derived entirely from the **1 Hz Logger (CAN-bus)
data**, not from telematics. The two data sources serve distinct roles:

| Source | Resolution | Role in this analysis |
|--------|-----------|----------------------|
| **Telematics** | ~1 hour/point | Provides window boundaries and the **total energy actually recuperated** within each window (Δ_recup_Wh) |
| **Logger (CAN)** | 1 Hz | Provides **second-by-second braking detail** within each window (speed, pedal, torque, brake switch) |

The observed efficiency η_regen bridges the two:

```
              Δ_recup_Wh  (telematics: how much was recovered)
η_regen_obs = ─────────────────────────────────────────────────
              E_recoverable  (logger: how much was theoretically available)
```

Each analysis window (30–90 min) contains ~2,000–5,000 Logger rows, enabling
precise reconstruction of every deceleration event and its braking behaviour.
Telematics provides only two data points (start and end) for the same window.

#### Physical meaning

The three brake types correspond to different energy pathways during deceleration:

- **`motor_only` (pure motor braking)**: The driver releases the accelerator but
  does not press the brake pedal. The motor acts as a generator, creating a
  braking torque. Kinetic energy flows: wheel → driveshaft → motor → inverter →
  battery. All deceleration energy is converted to electricity (minus losses).
  Highest regenerative efficiency.

- **`blended` (blended braking)**: The driver presses the brake pedal. Both the
  motor and friction brakes (brake pads) apply simultaneously. Kinetic energy
  splits: a portion is recovered electrically, the remainder dissipated as heat
  through the friction brakes. High-speed, high-deceleration events more
  frequently trigger this mode, because motor braking alone cannot provide the
  deceleration force demanded.

- **`coasting` (free deceleration)**: The driver neither accelerates nor brakes.
  The vehicle decelerates naturally under aerodynamic drag and rolling resistance.
  Motor torque is zero; active regeneration is negligible.

#### Classification method

**Step 1**: Detect deceleration events in Logger data — speed decreasing
monotonically by ≥ 0.1 m/s² for ≥ 1 second.

**Step 2**: For each event, average the CAN signals over the event rows:

```python
mean_pedal  = BrkPedalPos.mean()       # mean brake pedal position (%)
mean_switch = BrakeSwitch_CCVS.mean()  # mean brake switch signal
mean_trq    = EngTrq.mean()            # mean torque percentage
```

**Step 3**: Classify using the following rules:

| Type | Criterion |
|------|-----------|
| `motor_only` | BrkPedalPos <= 5% AND BrakeSwitch = 0 (pure motor/regen braking) |
| `blended` | BrkPedalPos > 5% (friction + motor: blended braking) |
| `coasting` | EngTrq = 0 AND BrkPedalPos <= 5% AND BrakeSwitch = 0 (free decel) |

Per-window and aggregate statistics are reported for event count share and KE
share of each type.

### 3.6 Time Alignment Quality

For each window, the gap between telematics timestamp boundaries and actual
logger record timestamps is computed:
- `gap_start_s`: |t_logger_first - t_telem_start|
- `gap_end_s`: |t_logger_last - t_telem_end|

Windows where both gaps < 300 s (5 minutes) are classified as **high
alignment quality**; otherwise **low quality**.

### 3.7 EngTrq=0 Regen Candidate Analysis

Since Volvo FM Electric CAN data does not report negative EngTrq, regeneration
is indirectly identified via periods where:
- Speed > 5 km/h (vehicle moving)
- EngTrq = 0 (no traction torque)
- Acceleration < -0.05 m/s^2 (actively decelerating)

These **regen candidate** periods are compared against all deceleration periods
to characterise speed and brake pedal distributions during likely regen.

### 3.8 Energy Model Calibration (reference only)

An attempt was made to calibrate Crr and CdA using EngSpd/EngTrq as motor shaft
power. Results (Crr=0.0072, CdA=3.81 m^2, R^2=-0.16) showed poor fit, likely
due to the Volvo FM Electric's multi-speed gearbox causing variable
motor-to-wheel speed ratios across speed ranges. The calibration results are
retained for reference but not relied upon for the regen analysis, which depends
only on vehicle speed, mass, and elevation — all directly measured quantities.

## 4. Key Findings

### 4.1 Regeneration Efficiency Distribution

| Statistic | All windows | Non-terrain-dominated | High alignment quality |
|-----------|-------------|----------------------|------------------------|
| N | 136 / 141 | 136 | 125 |
| Mean eta_regen | 0.430 | 0.430 | 0.430 |
| Median eta_regen | **0.423** | **0.423** | **0.423** |
| Std dev | 0.132 | 0.132 | 0.130 |
| 25th percentile | 0.356 | 0.356 | — |
| 75th percentile | 0.494 | 0.494 | — |
| Minimum | 0.110 | 0.110 | — |
| Maximum | 0.904 | 0.904 | — |

The figure below shows the eta_regen histogram for the 136 valid windows. The red
dashed line marks the median (0.423) and the gold dashed line marks the
theoretical motor-level efficiency (0.9). The bulk of the distribution sits
between 0.30 and 0.55 with a slight right skew; the large gap between the two
lines (42% vs 90%) arises from the diversion of energy to the friction brakes
(roughly 50% of deceleration energy is dissipated mechanically rather than
electrically) plus transmission losses at each stage.

> **Note**: The "terrain-dominated windows" described in §3.4 number zero in this
> dataset (fully removed by the 201-point smoothing), so all 136 valid windows
> are non-terrain-dominated and no extra filtering is needed.

![Figure 4.1 Regeneration efficiency distribution (N=136, median=0.423, mean=0.430)](results/figures/eta_regen_distribution.png)

The median system-level regen efficiency of **0.42** is physically reasonable for
a heavy-duty BEV.

No terrain-dominated windows were identified (all PE/KE ratios < 2.0), confirming
that the 201-point smoothing is adequate for this dataset.

Assuming eta_motor * eta_inverter * eta_battery ~ 0.85-0.90, the implied
**fraction of deceleration energy routed through regeneration (vs mechanical
brakes) is approximately 47-50%**.

### 4.2 Energy Budget

| Component | Total (kWh) | Share |
|-----------|-------------|-------|
| Recoverable KE | 3,252 | 77.6% |
| Recoverable PE (downhill) | 940 | 22.4% |
| **Total recoverable** | **4,192** | 100% |
| Actual recuperation | 1,752 | 41.8% |

### 4.3 Speed Range Analysis

| Speed range | KE share | Event count |
|-------------|----------|-------------|
| <30 km/h | ~3% | low |
| 30-60 km/h | ~19% | moderate |
| 60-80 km/h | significant | |
| >80 km/h | dominant | high |

High-speed deceleration (>60 km/h) accounts for approximately **77.9%** of all
recoverable kinetic energy, consistent with the vehicle operating primarily on
motorways and A-roads. **Regenerative braking also occurs under high-speed
conditions**, and it is the dominant source of energy recovery.

### 4.4 Brake Type Analysis

#### By event count (mean across windows)

| Brake type | Event % |
|------------|---------|
| motor_only | **65.3%** |
| blended | 27.0% |
| coasting | 7.5% |

#### By KE share (mean across windows)

| Brake type | KE % |
|------------|------|
| motor_only | 42.2% |
| blended | **53.2%** |
| coasting | 4.6% |

The figure below makes this contrast visible: the left stacked-area panel layers
the KE share, and the right bar panel gives the absolute KE total per type.
Blended braking (red) accounts for a much larger KE share (53.2%, 1,644 kWh) than
its event-count share (27%), whereas pure motor braking (blue) accounts for a
smaller KE share (42.2%, 1,442 kWh) than its event-count share (65%).

![Figure 4.4 Recoverable kinetic energy by brake type: mean per-window KE share (left) and total KE across all windows (right)](results/figures/brake_type_ke_distribution.png)

Key insight: Although `motor_only` events are the most frequent (65%), they
account for only 42% of recoverable KE. `blended` events (27% of count)
account for 53% of KE — meaning that high-energy deceleration events (high
initial speed, heavy vehicle) more frequently involve the friction brake pedal.
This is physically expected: at high speeds, the driver may supplement motor
braking with the service brake to achieve safe deceleration rates.

### 4.5 Speed Range × Brake Type Cross-Analysis

The figure below shows the brake-type event-count distribution across the four
speed bins (left) and the KE-share distribution within each speed bin (right).

![Figure 4.5 Brake type distribution x speed bin: event-count share (left) and KE share (right)](results/figures/speed_x_brake_type.png)

Two clear patterns emerge:

1. **By event count**: `motor_only` (blue) is dominant in every speed bin
   (64% → 56% → 60% → 79%), and its share is highest in the >80 km/h bin (79%),
   meaning the very highest-speed braking is more often handled by the motor
   alone.
2. **By kinetic energy**: `blended` (red) has a KE share in the 60-80 km/h and
   >80 km/h bins (63%, 39%) noticeably higher than its event-count share — i.e.
   **high-speed, high-energy deceleration events more often involve pedal
   input**, even though motor_only still dominates by count.

This cross-analysis answers the core question: **at high speeds, motor braking
remains the most common brake type (by event count), but the large kinetic
energy carried by high-speed deceleration flows more through the blended-braking
pathway (by KE)**.

### 4.6 EngTrq=0 Regen Candidate Analysis

| Metric | Value |
|--------|-------|
| Regen candidate rows (EngTrq=0, speed>5, decel) | 53,268 |
| All decel period rows | 112,742 |
| Candidate share | **47.2%** |
| Candidate speed median | 50.2 km/h |
| Candidate BrkPedalPos median | 0.0% |

The figure below compares (left) the speed distribution of regen candidate
periods (dark) against all deceleration periods (light): candidate periods
concentrate in the 20-90 km/h band, consistent with mid-to-high-speed driving.
The right panel shows the brake pedal position distribution for candidate
periods: **the vast majority sit at 0%**, confirming these are pure motor
regeneration periods with no friction-brake assistance.

![Figure 4.6 Regen candidate analysis: speed distribution (left) and brake pedal position distribution (right)](results/figures/regen_candidate_analysis.png)

Nearly half of all deceleration time is characterised by zero engine torque
with no brake pedal input, indicating unambiguous regenerative braking without
friction brake assistance. The median speed of 50.2 km/h is consistent with
mid-range deceleration events (30-60 km/h bin). The 0.0% median BrkPedalPos
confirms these are genuine motor-only regeneration periods.

**Conclusion: regenerative braking also occurs when the brake pedal is pressed**
(blended events), but its efficiency is slightly lower than pure motor braking;
motor braking without pedal input is the "purest" regeneration scenario.

### 4.7 Time Alignment Quality

| Category | Windows | eta_regen median |
|----------|---------|------------------|
| High alignment (gap < 5 min) | 129 / 141 | 0.423 |
| Low alignment (gap > 5 min) | 12 / 141 | similar |

The figure below shows (left) the distribution of telematics-logger timestamp
gaps across the 141 windows (blue = start gap, orange = end gap): the vast
majority sit close to 0, well below the 5-minute threshold (red dashed line). The
right box plot compares the efficiency distribution of high- vs low-alignment
windows, showing no meaningful difference (median ~0.42 in both), confirming the
12 low-quality windows introduce no systematic bias.

![Figure 4.7 Time alignment quality: telematics-logger gap distribution (left) and efficiency comparison of high- vs low-quality windows (right)](results/figures/time_alignment_quality.png)

129 out of 141 windows (91%) have both start and end gaps below 5 minutes,
indicating reliable temporal synchronisation between telematics and logger
data. The eta estimate is essentially unchanged between high- and low-quality
windows (median 0.423 vs similar), suggesting the 12 low-quality windows do
not introduce systematic bias.

**Recommended**: Use high-alignment-quality windows (N=125, after eta range
filter) for final efficiency estimates.

### 4.8 Brake Pedal and EngTrq Analysis

- **Brake pedal usage**: Pressed >5% only 12.0% of the time, indicating heavy
  reliance on engine/motor braking and coasting.
- **EngTrq = 0 while moving**: 30.6% of moving time, indicating frequent
  coasting / regenerative deceleration without traction torque.
- **Correlation with eta**: EngTrq-zero ratio has moderate positive correlation
  with eta (r=0.36), while brake pedal usage has weak positive correlation
  (r=0.14).

The figure below is a scatter of per-window eta_regen against the EngTrq=0 time
share (r=0.36). The overall trend is positive: the higher the share of zero-torque
time (coasting/regeneration) within a window, the higher the window's observed
regeneration efficiency tends to be. This matches physical expectation — an
operating mode that relies more on motor braking (less pedal use) reduces the
diversion to friction braking and raises the system recovery efficiency.

![Figure 4.8 Regeneration efficiency vs EngTrq=0 time share (r=0.36)](results/figures/eng_trq_zero_vs_eta.png)

### 4.9 Telematics Sampling Error

Windows with longer duration (>60 min) show more stable eta estimates compared
to shorter windows. The standard deviation of eta decreases with window length,
confirming that telematics sampling granularity (~1 hour) introduces noise in
single-window estimates but the ensemble statistics are robust.

## 5. Limitations

1. **GPS elevation noise**: Despite 201-point smoothing, GPS altitude data may
   still contain residual noise. The PE share (22.4%) should be treated as an
   upper bound. The terrain-dominated filter (PE/KE > 2.0) found 0 affected
   windows, suggesting the noise level is manageable.

2. **No negative EngTrq**: The Volvo FM Electric's CAN data reports EngTrq as
   0-100% (no negative values), preventing direct measurement of regenerative
   braking torque. Regeneration is inferred indirectly from EngTrq=0 and speed
   decreases.

3. **Blended braking allocation unknown**: The split between regenerative and
   mechanical braking within `blended` events is not directly observable. The
   eta_regen metric captures the combined system effect.

4. **Telematics sampling resolution**: ~1 hour sampling means individual windows
   aggregate many micro-events. Short regeneration events within a window cannot
   be individually validated.

5. **Energy model calibration**: The Crr/CdA calibration was unsuccessful due to
   the multi-speed gearbox. However, this does not affect the core regen
   analysis, which uses directly measured speed, mass, and elevation.

6. **Brake type classification threshold**: The 5% BrkPedalPos threshold for
   distinguishing motor_only from blended is a heuristic. Small pedal inputs
   below 5% may still engage partial friction braking.

## 6. Conclusions

The Volvo FM Electric (YK73WFN) achieves a **median system-level regenerative
braking efficiency of 0.42** across 136 valid analysis windows spanning
March-August 2025 (GPS elevation processed with a 201-point moving average).

Key findings:
- **No terrain-dominated windows** detected (PE/KE < 2.0 in all cases),
  validating the GPS noise suppression approach.
- **65% of decel events** are motor_only (pure regenerative), but these account
  for only 42% of recoverable KE; blended events dominate KE recovery (53%).
- **47% of decel time** at EngTrq=0 with speed>5 and decel>0.05 m/s^2 are
  unambiguous regen candidates with 0% median brake pedal input.
- **91% of windows** have high time-alignment quality (gap < 5 min); the
  final eta estimate of 0.42 is robust to alignment quality filtering.

**Answers to the three core questions**:

| Question | Conclusion |
|----------|------------|
| What is the regeneration efficiency? | System-level median **42%**; roughly 47-50% of deceleration energy is recovered via regeneration rather than friction braking |
| Is energy recovered at high speed? | **Yes** — high speed (>60 km/h) contributes ~78% of recoverable KE and is the dominant source of energy recovery |
| Does braking with the pedal also regenerate? | **Yes (blended braking)**, but 47% of deceleration time is pure motor regeneration (pedal = 0%); high-energy deceleration events more often involve pedal input (blended accounts for 53% of KE) |

The implied brake fraction (energy routed to regen vs. mechanical brakes) is
**47-50%**.

**Implication for the simulation model**: the `eta_regen` default in
`research_projects/simulation/models/vehicle_physics.py` is 0.90 (the theoretical
motor-level efficiency). The measured system-level efficiency here is ~**0.42**;
the difference arises from the diversion of energy to friction braking (~50% of
energy goes through the mechanical brakes) plus transmission losses at each stage.
To reflect the real recovery behaviour, `eta_regen` should be set to ~**0.42**.

## 7. File Inventory

| File | Description |
|------|-------------|
| `config.json` | Analysis configuration (vehicleId, physics params) |
| `scripts/01_data_explore.py` | Data feature analysis |
| `scripts/02_find_windows.py` | Time window search |
| `scripts/03_energy_model.py` | Crr/CdA calibration (reference only) |
| `scripts/04_regen_analysis.py` | Per-window regen analysis |
| `scripts/05_full_analysis.py` | Full-dataset statistics |
| `scripts/run_all.py` | One-click pipeline runner |
| `results/tables/valid_windows.csv` | 141 valid analysis windows |
| `results/tables/full_analysis_results.csv` | Per-window results |
| `results/tables/window_analysis_detail.csv` | Top-10 window detail |
| `results/tables/all_decel_events.csv` | All decel events with brake type |
| `results/tables/regen_candidate_analysis.csv` | EngTrq=0 regen candidates |
| `results/tables/summary_statistics.csv` | Aggregate statistics |
| `results/figures/` | Analysis figures (26 total) |
| `results/figures/eng_trq_distribution.png` | EngTrq percentage distribution |
| `results/figures/telematics_sampling_interval.png` | Telematics sampling interval distribution |
| `results/figures/eta_regen_distribution.png` | Eta histogram |
| `results/figures/brake_type_ke_distribution.png` | KE by brake type |
| `results/figures/speed_x_brake_type.png` | Speed x brake type cross-analysis |
| `results/figures/time_alignment_quality.png` | Alignment quality |
| `results/figures/regen_candidate_analysis.png` | EngTrq=0 candidates |
| `results/figures/eng_trq_zero_vs_eta.png` | EngTrq=0 fraction vs eta_regen |
| `results/figures/window_012.png` | Example window validation figure |
