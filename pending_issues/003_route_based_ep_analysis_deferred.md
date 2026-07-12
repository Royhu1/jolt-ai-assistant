# 003 — Route-based energy-performance analysis for the WJF fleet (John Miles request, deferred)

- **Status**: OPEN (deferred by agreement — prioritising the first JOLT technical report and the first JOLT journal paper)
- **Date found**: 2026-07-12 (registered; the request comes from John Miles's email on the WJF Hull briefings, June 2026)
- **Owner**: unassigned (analysis-side — a `data_analysis_workspace/` or `research_projects/` sub-project when picked up); route any `src/jolt_toolkit/` change to `jolt-toolkit-dev`
- **Priority**: medium (partner-requested; explicitly queued behind the two publication deliverables, with the partner informed)

## Summary

John Miles asked (second point of his email on the WJF briefings) for a **comparison of
vehicle performance over different types of terrain / route**: the flat Hull–Worksop trips
versus the trans-Pennine crossings (presumed via the M62), i.e. can the data be separated
by route type and the energy performance compared per group?

Xiaoxiang's reply (cc Jianghan) committed to coming back to this **after** two
higher-priority deliverables — the first JOLT technical report (promised to the cohort
within about a month) and the first JOLT journal paper. This file is the register entry so
the promise is not lost.

## Root cause (why it is not simply done already)

A proper answer needs **route selection and grouping code that does not yet exist** in the
pipeline: legs must be clustered by origin–destination / route corridor from their GPS
traces, robustly across the fleet's differing GPS sources, before per-route energy
performance can be compared. A one-off internal look (see below) exists, but it is not the
partner-facing deliverable and has no reusable route-grouping capability.

## What already exists (starting point, not the answer)

`data_analysis_workspace/terrain_load_comparison/` (2026-06-19, pinned to
`excel_report_database/2.2.5`) is the weekend quick-validation study behind Xiaoxiang's
reply. It shows the split is feasible but partial:

- Terrain classification from GPS works: for the WJF diesel comparator **YT21EFD** it
  separates 848 flat Hull–Worksop legs from 114 trans-Pennine M62 crossings; terrain came
  out as only a ~4 % second-order driver of fuel use once load/speed/distance are
  controlled.
- The **EV pair lacks trans-Pennine coverage** in the studied window: EX74JXW has no
  Pennine crossings at all; YN25RSY has few, and its telematics GPS carries no altitude.
- Limitations: one-off script, WJF-only, binary flat-vs-Pennine terrain axis (not general
  route grouping), old data version, results never shared with John.

## Impact

- An open partner commitment: John was told the analysis would follow the technical
  report and the journal paper; if unregistered it would rely on memory alone.
- Until done, briefing/report energy-performance figures for the WJF vehicles remain
  aggregated across route types, which John flagged as masking a comparison he cares
  about.

## Suggested fix (when picked up)

1. Build proper **route selection/grouping** code — cluster legs by OD pair / route
   corridor from GPS traces (handling the three GPS source types documented in
   `terrain_load_comparison/README.md`) — as a new or extended analysis sub-project,
   re-pinned to the then-current `excel_report_database/<version>/`.
2. Produce the **partner-facing answer to John**: per-route energy performance for the
   WJF vehicles (YN25RSY, EX74JXW), using diesel YT21EFD as the trans-Pennine
   comparator where the EVs lack coverage; check first whether newer data has added EV
   Pennine crossings.
3. If the route-grouping code proves reusable by 3+ sub-projects, promote it into
   `jolt_toolkit.analysis` per the code rule-of-three (via `jolt-toolkit-dev`, SemVer
   minor bump).

## References

- John Miles ↔ Xiaoxiang Na email exchange on the WJF briefings (June 2026; second
  question = this request, first question = the load comparison already answered).
- `data_analysis_workspace/terrain_load_comparison/` (`README.md` + `report.md`) — the
  internal preliminary study (Q2 = terrain split).
