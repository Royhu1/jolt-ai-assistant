# pending_issues/ — deferred-issue register

Holds issues that are **known, analysed, but not being fixed right now** (deferred issues):
one Markdown file per issue, with this README as the index. The point is to make sure
"log it now, fix it later" problems are never lost.

## Conventions

- One issue per file, named `NNN_<kebab-description>.md` (NNN = incrementing number).
- Each issue file records: **Status / Date found / Summary / Root cause / Impact / Suggested
  fix / Owner / References**.
- Status: `OPEN` / `IN PROGRESS` / `RESOLVED` (on resolution, note the date + outcome at the
  top of the file and remove or strike it from the index table below).
- When an issue is resolved: update its file's status and update the index table below.

## Index

| # | Issue | Status | Owner |
|---|-------|--------|-------|
| 001 | [Excel report / dashboard regen energy under-counted to ~5% (should be ~19%)](001_xlsx_regen_propulsion_undercounted.md) | OPEN | jolt-toolkit-dev |
| 002 | [WU70GLV legs mis-attributed to WJF in SRF (2025-09 to 2025-11)](002_wu70glv_srf_wjf_misattribution.md) | OPEN | jolt-toolkit-dev / SRF |
| 003 | [Route-based energy-performance analysis for the WJF fleet (John Miles request, deferred)](003_route_based_ep_analysis_deferred.md) | OPEN | unassigned (analysis-side) |
| 004 | [Switch monthly capacity/SOH series to a ΔSOC-weighted estimator (pooled ratio / origin-OLS)](004_pooled_capacity_estimator_deferred.md) | OPEN | unassigned (analysis-side) |
| 005 | [English-comment pass for the large generator scripts (pdf-report ×2, generate_figures, batch_generate runtime strings)](005_english_comment_pass_generator_scripts.md) | OPEN | owning skills (see issue) |
