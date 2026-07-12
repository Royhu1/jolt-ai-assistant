# data_analysis_workspace/shared — cross-topic shared scripts

The only git-tracked part of `data_analysis_workspace/` (everything else in this
workspace is local-only scratch). Code only — no data, no figures.

| File | Role |
|------|------|
| `generate_figures.py` | **Executable source of truth for the JOLT figure style** — the standard batch figure set (per-operation / all-operations / per-OEM, named + anon). Driven by the `plot-figure` skill (its `static/core/style-contract.md` mirrors this script's constants; a deliberate style change edits this script first, then the mirror). Usage: `PYTHONPATH=src python data_analysis_workspace/shared/generate_figures.py --out-dir <dir> [--version <X.Y.Z>] [--anon]`. |
| `batch_weather_patch.py` | Batch weather backfill helper for report-database vehicle dirs (loops the `jolt_toolkit` weather patcher over every vehicle folder of a version). |

Sub-project independence rules (`.claude/rules/code-style.md`) still apply: topics under
`data_analysis_workspace/<topic>/` may NOT import from here via `sys.path` tricks — copy
(vendor) what you need, or promote stable 3+-consumer code to `jolt_toolkit.analysis`.
