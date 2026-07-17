---
name: report-visuals
description: |
  Repaint validation figures and (re)write inspect-HTML viewers for generated
  JOLT reports, from the raw artefacts already on disk. Owns ALL
  validation-figure + inspect-HTML rendering code (EV painter, diesel painter,
  overlay-regenerate, viewer template) — self-contained in code/, driven by a
  single CLI (code/render_visuals.py). Artefacts land inside the target vehicle
  report directory: validation_figures/validation_<REG>_<date>.png +
  .boxes.json sidecars and inspect_jolt_report_*.html next to the xlsx.
  Triggers on:
  (1) "repaint validation figures (for <REG> / a report dir)"
  (2) "regenerate inspect html / refresh the inspect viewers"
  (3) "/report-visuals <REG|dir>"
  Routing boundary: xlsx GENERATION (reports, segmentation, raw persistence)
  belongs to the generate-excel-report skill / jolt_toolkit package
  (jolt-toolkit-dev agent); reviewing figures to tune segmentation parameters
  belongs to param-tuner; per-leg xlsx corrections (merge/split/delete →
  *_finetuned artefacts) belong to report-finetuner. This skill only renders.
---

# Report Visuals — Router

Code-owner skill (like `generate-pdf-report`): the rendering code lives in
`code/` and this router stays lean. No axes — both CLI modes are listed in the
core contract and README.

## Routing protocol

1. Read [manifest.yaml](manifest.yaml) and the always-load core contract
   [static/core/rendering-contract.md](static/core/rendering-contract.md) —
   invocation modes, artefact naming, append-only/finetuned discipline, and the
   P1/P2 delegation note.
2. Resolve the target: a vehicle report directory (or DB base dir + `--reg`)
   for `repaint`; a `--version` + `--db-root` for `rerender-html`. If the user
   gave only a REG, ask which report-database version / directory to operate
   on — never guess between versions.
3. Run `code/render_visuals.py` (see the core contract for the exact
   commands; run from the repo root so `./cache` and `.env` resolve).
4. Deep material on demand: [README.md](README.md) is the single source of
   truth (directory map, pipeline, ownership, neighbours, TODOs).

Update `code/`, the core contract or the README when adding scope — not this
router.
