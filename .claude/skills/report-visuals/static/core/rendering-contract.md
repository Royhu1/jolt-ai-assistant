# Rendering contract (always load)

Applies to every run of the report-visuals skill. *Why each rule exists is
stated inline so the rule can be safely evolved later.*

## Invocation (single CLI, two modes)

Run from the **repo root** so `./cache`, `.env` (SRF_API_KEY) and relative DB
paths resolve; use the jolt env python with `PYTHONUTF8=1` (Windows cp1252
consoles crash on the pipeline's Unicode log text otherwise).

```bash
# Repaint figures + sidecars + inspect HTML for one vehicle report directory
python .claude/skills/report-visuals/code/render_visuals.py \
    repaint --dir excel_report_database/<ver>/<REG>

# Same, for every vehicle dir under a base directory (optional --reg filter)
python .claude/skills/report-visuals/code/render_visuals.py \
    repaint --dir excel_report_database/<ver> [--reg <REG>]

# Rewrite ONLY the inspect_*.html viewers from existing figures/sidecars
python .claude/skills/report-visuals/code/render_visuals.py \
    rerender-html --version <ver> --db-root excel_report_database [--reg <REG>]
```

`repaint` inputs: `raw_telematics/raw_*.csv` (EV) or `raw_logger_*/logger_*.csv`
(diesel) + at least one non-finetuned `jolt_report_*.xlsx` in the directory
(the REG and the periods are parsed from the xlsx filenames). No raw data ⇒
nothing to repaint — generate the report with `--debug`/`--raw-only` first
(generate-excel-report skill).

## Artefact naming (the contract downstream tools rely on)

- One figure per **UTC day**: `validation_figures/validation_<REG>_<YYYY-MM-DD>.png`
  (+ `.boxes.json` overlay sidecar; figure-fraction coords, origin top-left).
- Viewer: `inspect_jolt_report_<REG>_<start>_<end>.html` next to the xlsx —
  one per non-finetuned period xlsx in the directory.
- Repaint first sweeps stale non-finetuned `validation_<REG>_*` PNGs/sidecars
  (including legacy per-leg `_<NNNN>` files) so old and new naming never
  coexist in the viewer sidebar.

## Append-only / finetuned discipline

`*_finetuned.*` artefacts are NEVER touched: finetuned figures/sidecars survive
every sweep, and finetuned xlsx periods get no inspect HTML from this skill —
they belong to the report-finetuner flow (its corrections must not be silently
overwritten by a base repaint). Explicit `--finetuned` support is a later
phase (TODO in README).

## Delegation status (P1)

The EV path still calls the package's `run_segment_detection(out_dir=...)`,
which paints inline with the PACKAGE's `plot_leg_validation` — expected until
the P2 `figure_hook` seam lands; the skill-local `validation_figure.py` is
already the module the diesel painter and future hook use. Segmentation
always stays in `jolt_toolkit` (read-only from here); route segmentation /
xlsx changes to jolt-toolkit-dev.
