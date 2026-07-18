# Rendering contract (always load)

Applies to every run of the report-visuals skill. *Why each rule exists is
stated inline so the rule can be safely evolved later.*

## Invocation (single CLI, three modes)

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

# Rendering half of the report-finetuner flow: paint *_finetuned overlay
# figures + the inspect_*_finetuned.html viewer for a finetuned xlsx
python .claude/skills/report-visuals/code/render_visuals.py \
    repaint-finetuned --xlsx <dir>/jolt_report_<REG>_<start>_<end>_finetuned.xlsx \
    --segs-json <segments.json> [--raw-dir <dir>/raw_telematics] \
    [--out-dir <dir>/validation_figures] [--fig-suffix _finetuned] \
    [--figures-only | --html-only] [--html-out <path>]
```

`repaint-finetuned` contract: the segments JSON (schema
`report-visuals.finetuned-segs/v1`) is produced by the report-finetuner
skill's `finetune.dump_segs_json` — xlsx reconstruction is finetune-owned,
painting is this skill's; the two halves meet ONLY at this CLI + JSON seam
(no cross-skill Python imports — v3.1.0 coupling rule). `--html-only` needs
no JSON (it enumerates figures already on disk). The CLI prints
machine-parsable `figures=<N>` / `html=<path>` summary lines that the
finetune library's wrappers parse — keep them stable.

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

The base modes (`repaint` / `rerender-html`) NEVER touch `*_finetuned.*`
artefacts: finetuned figures/sidecars survive every sweep, and finetuned xlsx
periods get no inspect HTML from those modes — a base repaint must not
silently overwrite the report-finetuner's corrections. Regenerating the
finetuned set is exclusively `repaint-finetuned`'s job (driven by the
report-finetuner skill), and IT in turn never overwrites non-finetuned
originals — its outputs always carry the `--fig-suffix`
(`validation_<REG>_<date>_<idx>_finetuned.png`,
`inspect_*_finetuned.html`); a date whose finetuned segs equal the originals
gets NO finetuned PNG (stale ones are removed) so the viewer falls back to
the original figure.

## figure_hook seam (P2b)

Since v3.1.0 P2 the package paints nothing and does not import matplotlib.
The EV repaint path passes the skill-local painter
(`validation_figure.plot_leg_validation`) to the package's
`run_segment_detection(..., figure_hook=...)` — the hook is invoked at
exactly the point, and with exactly the arguments, the former inline call
used (contract in `segmentation/detection.py`; an import-time assertion in
`validation_generator.py` guards signature drift), so figures are identical
in a single pass. Segmentation always stays in `jolt_toolkit` (read-only from
here); route segmentation / xlsx changes to jolt-toolkit-dev.
