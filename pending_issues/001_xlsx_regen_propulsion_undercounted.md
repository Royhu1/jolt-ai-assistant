# 001 — regen energy in the Excel report / dashboard is severely underestimated (~5%, should be ~19%)

- **Status**: OPEN (analysed, fix deferred)
- **Date found**: 2026-06-17
- **Owner**: `jolt-toolkit-dev` (sole owner of `src/jolt_toolkit/`) — this is a source-data (xlsx column) problem
- **Priority**: medium (does not block the current delivery; the PDF briefing already works around it separately within the skill, see below)

## Summary

The **`Recuperation Energy (kWh)`** column in `excel_report_database/<ver>/<REG>/jolt_report_*.xlsx`
(very likely `Propulsion Energy` too) has **sparse coverage and low per-segment values**, causing all downstream consumers that read this column
(the Excel report itself, the data dashboard, the old PDF briefing) to display the regenerative-energy share as **~4.5–8%**, whereas the true
value is about **19%**.

Measured (YK73WFN, 2.2.3, `...finetuned.xlsx`):
- xlsx `Recuperation Energy`: 495 kWh, **only 55/115 segments have a value (48% coverage)**; 60 segments are blank, of which
  **39 segments clearly have SRF Logger data** yet still produced no recup (→ not merely a missing source, but an extraction bug), and another 21 segments have no Logger.
- recup / |Energy Change| = **4.5%** (whole fleet) / 8.0% (covered segments only).
- Compared with `data_analysis_workspace/energy_breakdown` (which uses the **raw_telematics cumulative counters** interpolated at the trip endpoints
  to compute `E_recup`, with **100% coverage**): YK73 **E_recup/E_total = 19.4%**, official summary `pct_recup_tot = 18.9%`.
  The basis is consistent (the denominator on both sides is net battery energy); the 19% vs 8% gap **comes purely from the data source / coverage of this one regen item**.

## Root cause

The xlsx `Recuperation Energy` (and `Propulsion Energy`) columns use a **sparse source** (Logger/event extraction,
with incomplete coverage and missed counts), rather than the **raw_telematics cumulative regeneration counters**. The `energy_breakdown` README already
explicitly points this out and deliberately switches to the counters: "*Energies come from raw_telematics cumulative counters … not the xlsx
Propulsion/Recuperation columns, which have poor coverage*".

## Scope of impact

- **Affected**: the regen column of the Excel report, the data dashboard, and any consumer that reads the xlsx recup/propulsion columns directly.
- **Already worked around (DONE 2026-06-17)**: the industrial **PDF briefing** has already switched to the counter basis within the `generate-pdf-report` skill
  (`_counter_recup`, reading only `raw_telematics` + `jolt_toolkit.analysis`) to compute regen, with full coverage and correct results —
  YK73 measured 495→**1,818 kWh (coverage 107/107, ~17%)**; vehicles without counters (Scania/Mercedes/diesel) fall back to displaying "—".
  So there is now **inconsistency between deliverables**: the PDF briefing ≈ correct, but the **Excel report / dashboard still read the sparse xlsx column ~5%** —
  this is precisely the remaining part of this issue that is yet to be resolved.

## Suggested fix

In `src/jolt_toolkit/` (implemented by `jolt-toolkit-dev`), change the xlsx `Recuperation Energy`
(and `Propulsion Energy`) columns to be **computed from the raw_telematics cumulative counters**:
- Reference implementation: `data_analysis_workspace/energy_breakdown/scripts/build_dataset.py`
  — using `build_interp / delta / to_utc` from `jolt_toolkit.analysis` and the counter-column constants
  `COL_TOTAL / COL_PROP / COL_RECUP`, taking the `[Start, End]` endpoint difference for each driving leg.
- Only for **EVs that have the full set of counters** (Volvo FM/FH, Renault, etc., 10 vehicles); vehicles without counters
  (Scania / Mercedes / DAF LN25NKE, diesel WU70GLV) keep a graceful N/A.
- This is **a change to canonical data** → it requires a fleet re-run + version bump (per convention, obtain the user's consent first).

## References

- This analysis conversation (2026-06-17).
- `data_analysis_workspace/energy_breakdown/` (README §"Conventions & gotchas", `scripts/build_dataset.py`).
- `.claude/skills/generate-pdf-report/SKILL.md` (the boundary note for if the PDF side switches to the counter basis).
