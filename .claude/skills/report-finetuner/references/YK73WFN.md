# YK73WFN Finetune Case Study

## Vehicle characteristics

- **Make/model**: Volvo FM Electric
- **Nominal capacity**: ~540 kWh
- **Operation pattern**: depot-based regional distribution, mixed AC home / DC fast charge,
  daily loaded outbound + empty return pattern
- **Data availability**: Telematics + Logger (CCVS + EEC1 + CVW + Channel 7 weather)

## Recurring visual issues observed

On the 2024-06-01 ~ 2024-09-01 window (100 days), **no genuine segmentation errors**
were found — `param-tuner` had already converged. The demo used an illustrative
(not validated) `MergeOp` to showcase the overlay workflow.

### The 2024-06-20 ambiguity

- `row 18: DC Home 12:36-13:22` (+44% SOC)
- `row 19: Stop 13:22-14:01` (-8% SOC, suspicious — aux drain expected ~0.2-0.5%)
- `row 20: In Transit 14:01-16:52` (80km)

The -8% SOC drop during the post-DC-charge Stop is physically large. Possible
explanations:
1. DC fast charge SOC rebalance (battery thermal equilibration → measured SOC falls
   without actual energy use)
2. Pre-departure HVAC/cabin conditioning
3. Missed short trip (algorithm saw zero speed despite brief movement)

**Demo resolution used**: `MergeOp(rows=[19, 20], new_type="In Transit", reason="DEMO")`
— merged Stop into following Trip. NOT validated as the correct physical interpretation;
used only to showcase overlay visualisation.

## Operations applied (demo only)

| Op | Count | Reason |
|----|-------|--------|
| MergeOp | 1 | Demo: merge Stop + In Transit for overlay showcase |

## Lessons for similar vehicles

1. **Volvo FM telematics is clean**. Fine-grained event boundaries accurate after
   `param-tuner` runs. Don't expect to find many real finetune candidates.
2. **Post-DC-charge SOC drops are common on Volvo FM** (battery thermal rebalance).
   These are NOT real trips and should NOT be treated as segmentation errors.
   Leave them as Stop rows.
3. **Cargo loading events while parked** (mass 10t → 32t without speed) are
   correctly not segmented as Trip. Don't try to "fix" them.
4. **Idle days with tiny AC+DC delta noise** (~5-10 kWh cumulative increments
   when SOC stays at 100) are correctly rejected by `min_soc_rise` — don't
   manufacture charge segments there.

## Technical gotchas encountered

Both captured as permanent lessons in `.claude/agents/report-finetuner.md` §陷阱:

- **`MergeOp` `new_type` is mandatory** when merging rows of different leg types,
  otherwise the merged row silently inherits the first row's type (often `Stop`)
  and disappears from discharge/charge segs.
- **`Energy Change (kWh)` column is SOC-derived, not cumulative-integral-based**
  after merge. Don't trust post-merge EP values; re-integrate from raw CSV if
  accurate energy matters.

## Reference run

- Xlsx: `excel_report_database/2.2.2/YK73WFN/jolt_report_YK73WFN_20240601_20240901_finetuned.xlsx`
- Overlay demo PNG: `excel_report_database/2.2.2/YK73WFN/validation_figures/validation_YK73WFN_2024-06-20_0009_finetuned.png`
- Inspect HTML: `excel_report_database/2.2.2/YK73WFN/inspect_jolt_report_YK73WFN_20240601_20240901_finetuned.html`
- Evaluation log: `.claude/skills/report-finetuner/evaluations/YK73WFN_20240601_20240901_finetune_log.md`

## Additional period reviewed: 20241201_20250301 (winter)

- Evaluation log: `.claude/skills/report-finetuner/evaluations/YK73WFN_20241201_20250301_finetune_log.md`
- 92 figures reviewed, 27 active days
- **0 genuine segmentation errors**, no operations applied
- Confirms param-tuner convergence holds for winter period

### New knowledge: January 2025 telematics SOC corruption

On **2025-01-23 ~06:30 through 2025-01-24 ~14:00**, the Volvo FM SOC signal
briefly crashes to 9% and recovers to 80%+ multiple times while the vehicle is
stationary and `total_electric_energy_used` is unchanged. The algorithm
correctly produces alternating In House / Charge Home rows (rows 84-96 of the
20241201_20250301 report). This is a telematics signal quality issue, not a
segmentation error — do not attempt to fix via MergeOp/DeleteOp. If future
runs hit the same date range, skip investigation and record the same
conclusion.

## Additional period reviewed: 20250301_20250601 (spring/early summer)

- Evaluation log: `.claude/skills/report-finetuner/evaluations/YK73WFN_20250301_20250601_finetune_log.md`
- 93 figures reviewed, 46 active days + 47 idle days
- **1 genuine fix applied** (sensor glitch, not a segmentation-algorithm issue)

### The 2025-05-27 21:49 SOC outlier glitch

Telematics `electricBatteryLevelPercent` emitted **two 40-second-apart outlier
samples reading 44%** (21:49:22, 21:49:42) sandwiched between 87% readings
before and after. The segmentation algorithm dutifully produced a fake
`Charge Home` row (SOC 44 → 87 in 20 min) between two real multi-day idle
Stops. Confirmed via:

1. `battery_pack_ac_watthours` + `battery_pack_dc_watthours` flat (no metered
   energy flow)
2. `total_electric_energy_used` flat
3. Surrounding SOC values (87, 87) consistent with ongoing thermal rebalance
   from the 2025-05-22 full charge

Fix: `MergeOp(rows=[352, 353, 354], new_type="Stop")`
→ One long Stop 2025-05-22 21:00:41 → 2025-05-30 10:46:23, Start SOC 100 →
End SOC 69.

### New lesson for similar vehicles

5. **Telematics SOC can emit 1–2-sample outlier dips** (often ~40-50% below
   true SOC). If an apparent `Charge Home` row records >30% dSOC in <30 min
   and Panel 2 (AC+DC Delta) is flat at zero, suspect a sensor glitch rather
   than real charging. Classic signature: Stop-Charge-Stop pattern where SOC
   just before and just after the "Charge" are equal (ongoing thermal
   rebalance), and the dip occurs between two adjacent telematics samples
   without any intermediate readings.

### Known finetune library limitation discovered

`_apply_merge` carries over `End SOC (%)` from the last merged row but does
**not** recompute `SOC Change (%)`. On 2025-05-22 row 352 after merge, SOC
Change still reads `-56` instead of the correct `-31`. Start SOC and End SOC
columns themselves are correct. Downstream analyses should compute
`End SOC - Start SOC` directly on finetuned rows rather than trust the SOC
Change column. Potential `jolt-toolkit-dev` follow-up: extend
`_recompute_leg_derived` to recompute `SOC Change (%)` for Stop rows.

## Operations summary (running totals across all reviewed periods)

| Op type | Count | Typical reason |
|---------|-------|----------------|
| MergeOp (demo)   | 1 | Illustrative overlay workflow (20240601_20240901) |
| MergeOp (glitch) | 1 | Absorb fake Charge Home from sensor-outlier V-spike (20250301_20250601) |
| SplitOp          | 0 | — |
| DeleteOp         | 0 | — |
