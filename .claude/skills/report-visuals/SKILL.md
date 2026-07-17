---
name: report-visuals
description: |
  Repaint validation figures and (re)write inspect-HTML viewers for generated
  JOLT reports, from the raw artefacts already on disk. Owns ALL
  validation-figure + inspect-HTML rendering code (EV painter — also the
  figure_hook the package's run_segment_detection calls, diesel painter,
  overlay-regenerate, finetuned overlay repaint, viewer template) —
  self-contained in code/, driven by a single CLI (code/render_visuals.py:
  repaint | rerender-html | repaint-finetuned). Artefacts land inside the
  target vehicle report directory: validation_figures/validation_<REG>_<date>.png
  + .boxes.json sidecars and inspect_jolt_report_*.html next to the xlsx
  (finetuned mode: *_finetuned.png + inspect_*_finetuned.html).
  Triggers on:
  (1) "repaint validation figures (for <REG> / a report dir)"
  (2) "regenerate inspect html / refresh the inspect viewers"
  (3) "/report-visuals <REG|dir>"
  (4) "repaint the finetuned figures/HTML" (normally driven by the
      report-finetuner skill through the repaint-finetuned CLI contract)
  Routing boundary: xlsx GENERATION (reports, segmentation, raw persistence)
  belongs to the generate-excel-report skill / jolt_toolkit package
  (jolt-toolkit-dev agent); reviewing figures to tune segmentation parameters
  belongs to param-tuner; per-leg xlsx corrections (merge/split/delete →
  *_finetuned.xlsx, incl. segment reconstruction) belong to report-finetuner —
  it hands THIS skill only the rendering, via CLI. This skill only renders.
---

# Report Visuals — Router

Code-owner skill (like `generate-pdf-report`): the rendering code lives in
`code/` and this router stays lean. No axes — the three CLI modes are listed
in the core contract and README.

## Routing protocol

1. Read [manifest.yaml](manifest.yaml) and the always-load core contract
   [static/core/rendering-contract.md](static/core/rendering-contract.md) —
   invocation modes, artefact naming, append-only/finetuned discipline, and
   the figure_hook seam note.
2. Resolve the target: a vehicle report directory (or DB base dir + `--reg`)
   for `repaint`; a `--version` + `--db-root` for `rerender-html`; an `--xlsx`
   (`*_finetuned.xlsx`) + `--segs-json` for `repaint-finetuned`. If the user
   gave only a REG, ask which report-database version / directory to operate
   on — never guess between versions.
3. Run `code/render_visuals.py` (see the core contract for the exact
   commands; run from the repo root so `./cache` and `.env` resolve).
4. Deep material on demand: [README.md](README.md) is the single source of
   truth (directory map, pipeline, ownership, neighbours, TODOs).

Update `code/`, the core contract or the README when adding scope — not this
router.
