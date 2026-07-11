# Mode: single — one vehicle, one period (`generate_report.py`)

Use when the run produces exactly **one** `.xlsx`: one vehicle and one explicit period
of ≤ ~3 months, or a deliberately single full-range report (see the span rules in
`static/core/conventions.md`).

Single vehicle, single period (≤ ~3 months):

```bash
python .claude/skills/generate-excel-report/generate_report.py -veh YK73WFN -ds 2025-03-01 -de 2025-05-31
# add --debug for validation figures + raw CSV; --raw-only for raw + HTML without baked figures
# --fast only for quick non-final runs
# --out-dir ./excel_report_database/2.2.7   # override the version-derived output dir
```

Flag semantics (`--debug` / `--raw-only` / `--fast`) and the output artefact paths are
in `static/core/conventions.md` ("Inputs to confirm" / "Output artefacts"). After the
command finishes, follow `references/after-generating.md` before declaring the run
complete (weather backfill is required).
