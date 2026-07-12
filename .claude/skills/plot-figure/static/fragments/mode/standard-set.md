# Mode: standard-set — the full standard batch, regenerated as-is

Use ONLY when the user wants the whole standard figure set (per-operation /
all-operations / per-OEM, named + anon) regenerated with no customisation.

The standalone script `data_analysis_workspace/shared/generate_figures.py` implements the
full standard set and is the authoritative source of style + data-loading + fit logic
(see the style contract).

```bash
cd <project_root>
PYTHONPATH=src python data_analysis_workspace/shared/generate_figures.py --out-dir <your/output/dir> [--version 2.2.8] [--anon]
```

- **Outputs**: `<out-dir>/named/` (real names) and `<out-dir>/anon/` (anonymised OEM
  labels, needs `--anon`).
- `--version` selects the report-database version under `excel_report_database/`.
- Do NOT copy-edit this script for a customised variant — that is `bespoke` mode, which
  persists its own `plot_<name>.py` in the target workspace instead.

## Checklist

1. Ensure reports exist for the chosen `--version` under `excel_report_database/<version>/`
   (regenerate via the `generate-excel-report` skill if missing; skip `--debug` to preserve
   patched weather data).
2. Run the command above with the user's `--out-dir`.
3. Review the output PNGs against the `templates/` gallery (style contract).
4. Report the output directory contents to the user.
