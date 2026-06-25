# EX74JXY — Scania P-series BEV

> Pipeline: scania_speed_01 | Last updated: **2026-05-17**

## ⚠️ 2026-05-17 update — historical Round 0/1/2 conclusion overturned

EX74JXY shares the Scania P-series BEV data characteristics with EX74JXW, and is likewise affected by `merge_discharge_by_mass`:
the real load fluctuation of 1–2 t falls within the same `min_cluster_gap_kg=2000` cluster bucket → adjacent trips have the
same dominant cluster → merged into a single In Transit.

**This round's (2026-05-17) changes**:
- `scania_speed_01.merge_by_mass`: added → **false** (mass merging disabled, split retained)
- the other speed_params / charge_params unchanged

**Effect** (the 10-month 2025-04_2026-02 period): driving legs total **391** (In Transit 307 + Outbound 41 +
Return 42 + Round Trip 1). Visual spot-check 2025-05-08 shows healthy multi-trip splitting, mass stable at ~35–40 t,
EP within normal range.

For the detailed diagnostic reasoning, see the 2026-05-17 update section of the sister vehicle [EX74JXW.md](EX74JXW.md).

The old records below are retained only for historical reference — the current conclusion is as given in this section.

---


## Vehicle characteristics

- Make/Model: Scania P-series BEV
- Nominal capacity: 475 kWh
- Operation mode: mode=discharge
- Data characteristics: consistent with EX74JXW, telematics SOC coarse precision (1% resolution), telematics speed available
- Typical mass range: 15–40 tonnes
- Typical EP range: 0.5–3.0 kWh/km

## Pipeline and parameters

- Pipeline: `scania_speed_01`
- speed_threshold_kmh: 1.0
- min_stop_duration_min: 5.0
- min_trip_duration_min: 2.0
- min_soc_drop: 1.0
- min_energy_kwh: 1.0
- plateau_window_min: 60
- min_soc_rise: 5.0
- min_energy_charge: 5.0
- speed_col: wheel_based_speed

## Optimisation history

### Round 0 — Pipeline switch (2026-03-22)
- Switched from `scania_soc_01` to `scania_speed_01`
- Reason: coarse SOC precision caused the SOC-based algorithm to miss many trips (speed 80 km/h but SOC flat)
- Exactly the same problem and solution as EX74JXW, see `EX74JXW.md`

### Round 1 — Initial review (2026-03-23)
- Reviewed 60/143 validation figures
- OK rate: 55/60 = 91.7% (incl. idle); 55/57 = 96.5% (active+charge only)
- Found 5 issues (1 missed discharge, 1 missed charge, 2 borderline, 1 possible missed idle)
- Conclusion: no parameter tuning needed

### Round 2 — Thorough mode full coverage (2026-03-25)
- Reviewed all remaining 83/143 validation figures, achieving 100% coverage
- Round 2 newly reviewed portion: 83 OK, 0 Issue
- Full results: 138 OK / 5 Issue = 96.5% OK rate
- **No new issues found**, the 5 issues from Round 1 confirmed as the only problems
- **No parameter tuning needed**

## Known issues (cannot be fixed by parameter tuning)

| Figure | Date | Type | Description | Root cause |
|--------|------|------|------|------|
| 0136 | 2026-01-05 | Missed discharge | SOC 100→20% but 0 segments, moving energy only 1.5 kWh | data quality issue (energy channel anomaly) |
| 0104 | 2025-10-24 | Missed charge | SOC 40→90% with AC/DC delta but 0 segments | charging too gradual, may exceed plateau_window |
| 0138 | 2026-01-09 | Missed discharge | SOC 100→80%, energy 0.6 kWh, 0 segments | below the min_energy threshold boundary |
| 0133 | 2025-12-31 | Marginal trip | 1D detected but extremely short, very little energy | edge case, detection correct but questionable |
| 0142 | 2026-01-30 | Possible missed idle | SOC flat, energy 0.5 kWh stepwise | possibly very low-speed depot movement, below threshold |

## Key lessons

1. **Speed-based segmentation is crucial for Scania's coarse-resolution SOC**: the 1% SOC step causes the SOC-based algorithm to miss many genuine trips
2. **The current parameters perform excellently for multi-drop distribution scenarios**: busy days with 7+ stops are all correctly segmented
3. **Data quality issues should not be compensated for by lowering thresholds**: the energy channel anomaly of 0136 (80% SOC drop but only 1.5 kWh moving energy) is a data quality issue, not a parameter issue
4. **Slow-charge detection is a known limitation**: the charging of 0104 is very gradual and may need a larger plateau_window, but this would affect other normal charge detection
5. **Trace energy (<1 kWh) and speed pulses on idle days can be correctly ignored**: the current thresholds filter depot micro-movements well
