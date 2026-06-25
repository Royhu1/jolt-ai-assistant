# YN25RSY — Mercedes-Benz eActros 600

## Vehicle characteristics

- Make/Model: Mercedes-Benz eActros 600
- Nominal capacity: 600 kWh
- Operation mode: long-haul trunk transport, occasionally multi-drop distribution
- Data characteristics: telematics SOC (integer 1% precision) + telematics speed (`speed` column, ~2 min interval) + Logger Speed + Logger Mass; no telematics mass data

## Key finding: telematics column name difference

The Mercedes telematics speed column is named `speed`, not the `wheel_based_speed` used by Volvo/Scania/Renault.
It must be explicitly configured in vehicles.json as `"speed_col": "speed"`.

## State before optimisation

- Pipeline: `mercedes_soc` (SOC-based discharge segmentation)
- Main problem: **over-segmentation** (10+ days affected), with 6 discharge segments on individual days
- Secondary problem: trips missed at low SOC (1 day)

## Root causes and solutions

### Root cause 1: SOC integer precision causes over-segmentation

Mercedes SOC precision is 1% (integer); during continuous driving brief SOC plateaus or small rebounds (1-3%) appear,
and `soc_rise_abort_pct=3.0%` cuts a continuous trip into multiple fragments.

**Solution**: switch to the speed-based pipeline (`mercedes_speed`), configuring `speed_col: "speed"` to use telematics speed.

### Root cause 2: the Logger speed approach is unsuitable

The Logger Speed (high-frequency ~15s interval) was initially tried for trip detection. Problems:
- relies on Logger data, `--fast` mode unavailable
- high-frequency data detects every short stop (5-15min), requiring `min_stop_duration_min` to be raised to 15
- on some days the Logger speed is incomplete (11-01), causing trips to be missed

**Final approach**: use telematics speed (`speed` column, ~2min interval). Advantages:
- does not rely on Logger/Charger data, compatible with `--fast` mode
- the 2min interval naturally filters out very short stops (stops <2min are invisible)
- full coverage (telematics always online), so trips are not missed due to incomplete Logger

## Final parameters

| Parameter | Default | Final | Reason |
|------|--------|--------|------|
| `pipeline` | `mercedes_soc` | `mercedes_speed` | insufficient SOC precision, switched to speed segmentation |
| `speed_col` | `wheel_based_speed` | `speed` | the Mercedes telematics speed column name is different |
| `min_stop_duration_min` | 5.0 | **5.0** | with a 2min telematics interval, 5min suffices, no need to raise it as for Logger |
| `min_soc_drop` | 1.0 | **2.0** | filters out dSOC≤1% noise segments |

## Optimisation results

- 8/15 days improved or markedly improved
- 3/3 correct days unchanged
- 11-01 fixed (the full-day driving previously missed by the Logger approach is now covered by telematics speed)
- 12-01 still undetectable (SOC completely flat at ~12%, BMS protection)

## Round 2 verification (2026-03-25, v2.1.0.dev0)

Full detailed inspection (each of 48 validation figures reviewed) confirms:
- **46/48 OK, 2/48 Issue** — exactly consistent with the Round 1 results
- the trip boundaries on all 15 active days are correctly aligned with the telematics speed trace
- EP values within the 0.7–2.1 kWh/km range (eActros 600, 40t class)
- charge segments (green regions) correctly identified on all active days
- no false positives during the long standby period from 2025-11-19 to 2026-01-04
- 12-05 reclassified as Charge-only (charging only, no valid discharge trip)
- **no parameter tuning needed** — the current parameters are already optimal

## Lessons learned (applicable to similar vehicles)

1. **Prefer telematics speed over Logger speed** — telematics is always online and compatible with `--fast` mode;
   Logger speed serves as supplementary validation, not as the basis for segmentation
2. **Telematics column names differ between makes** — configure `speed_col` rather than hard-coding the column name:
   - Volvo/Scania/Renault: `wheel_based_speed`
   - Mercedes: `speed`
3. **Vehicles with integer SOC precision should use the speed-based pipeline** — SOC-based is too sensitive at 1% precision
4. **The time resolution of telematics speed naturally filters short stops** — with a 2min interval, `min_stop_duration_min=5` suffices,
   no need to raise it to 15 as for high-frequency Logger speed
5. **The segmentation algorithm should not rely on Logger/Charger data** — ensure `--fast` mode (telematics only)
   and full mode produce the same trip/charge segmentation results
6. **`min_soc_drop=2.0` is appropriate for large-capacity vehicles** — at 600kWh, 1% SOC = 6kWh,
   a dSOC=1% movement is usually shunting/repositioning, not a valid trip
