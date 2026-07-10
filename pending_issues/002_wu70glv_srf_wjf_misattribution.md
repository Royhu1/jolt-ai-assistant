# 002 — WU70GLV legs mis-attributed to WJF in SRF (2025-09-01 → 2025-11-06)

- **Status**: OPEN
- **Date found**: 2026-07-10
- **Owner**: jolt-toolkit-dev (pipeline-side mitigation) / SRF platform (root fix)

## Summary

WU70GLV (DAF XF 450 diesel comparator) legs between 2025-09-01 and 2025-11-06 carry a
"WJF" round-robin trial token in SRF, so the reports database's per-leg `Operator` column
attributes ~342 legs to WJF. The user confirmed (2026-07-10) the vehicle is DP World's and
**was never lent to WJF** — the attribution is a platform data error. The true trial is one
continuous DP World stint, 2025-06-26 → 2025-12-11.

## Root cause

SRF `leg.trip.trial.description` for those legs names the wrong operator (exact upstream
cause unknown — likely a trial record mis-assignment on the platform). The report
generator's data-driven operator derivation faithfully copies it.

## Impact

- `excel_report_database/<ver>/WU70GLV/` `Operator` column shows WJF for 2025-09→11 legs
  (both 2.2.7 and 2.2.8).
- Any per-operator aggregation that trusts the column (data-collection digest, dashboards,
  potential future per-operator briefings for diesel vehicles) splits WU70GLV's trial into
  spurious DP World → WJF → DP World stints.
- Presentation artefacts corrected manually on 2026-07-10: `pdf_report_status.md` /
  `.xlsx` and the 0715 deck show one continuous DP World trial.

## Suggested fix

Ask SRF to correct the trial record; if not feasible, add a pipeline-side operator
override (e.g. a per-vehicle date-ranged correction map consulted by the operator
derivation in `jolt_toolkit`) — route to jolt-toolkit-dev. Re-check after the next SRF
sync whether the token is fixed before building overrides.

## References

- `pdf_report_workspace/pdf_report_status.md` (corrected table + note)
- changelog 2026-07-06_2026-07-12, status-table restructure entries
