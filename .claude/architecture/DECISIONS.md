# Architecture Decision Records (ADR log)

> Owned by the `project-architect` agent. One dated entry per material structural
> decision: context → options considered → decision → consequences. Newest at the top.
> Plan documents for in-flight changes live beside this file.

## 2026-07-17 — ADR-002: v3.1.0 platform slimming — package = report generation only

**Context**: jolt_toolkit v3.0.0 will be deployed on the SRF platform (James). The user
wants the package to contain ONLY the report-generator surface; AUX capabilities
(dashboards, finetune, validation-figure/inspect-HTML rendering, parameter
identification) must move to skill/agent-owned code providing the same functionality.
Additionally the generator must handle not-yet-onboarded registrations via a general
fallback pipeline: BOTH EV and diesel GUARANTEED to produce an xlsx — the platform must
never surface an 'onboard first' prompt (user decision 2026-07-17, superseding the
earlier EV-only-guarantee choice; ultimate fallback = a valid, possibly sparse report).

**Options for the shared `analysis/` sub-package**: (a) keep in package (sanctioned by
the sub-project-independence rule; consumed by generate-pdf-report skill + simulation);
(b) move out and vendor. **User decision: keep (a).**

**Decision**: proceed with the v3.1.0 allocation plan (see `plan_v310_platform_slim.md`
beside this file). Highlights: dashboards → `generate-data-dashboard` skill code;
finetune library → `report-finetuner` skill code; validation figures + inspect HTML +
overlay-regenerate + rerender → a NEW skill owning the rendering path;
`vehicle_params_identificator` → the `param-identifier` agent's research workspace;
package keeps xlsx generation + patchers + configs + `analysis/`; `--debug` in-package
behaviour becomes raw-CSV persistence (rendering happens post-hoc via the new skill,
matching the already-canonical overlay-regenerate path). Version: **3.1.0** (user decision — despite module removals being formally breaking, the user opts for a minor bump; the removed modules' consumers are all re-homed inside the same repo in the same change).

**Consequences**: package loses matplotlib-dependent code paths (dependency audit due);
jolt-toolkit-dev's ownership shrinks accordingly (agent doc updated in the same change);
every consumer of removed import paths is re-homed before removal (facade-before-break).

**Outcome (2026-07-18)**: executed as planned across P1/P2/P2b/P3/P4 on
`refactor/v3.1.0-platform-slim` (commit table in `plan_v310_platform_slim.md` §5).
The package dropped 23 files / ~12.3k lines and the matplotlib dependency; every
re-homed capability was verified working from its new home (report-visuals repaint
byte-identical, finetuned rendering CLI-delegated, dashboard skill runner, params
workspace); the general fallback pipeline exceeded the original EV-only guarantee
(both fuel types produce a report; un-onboarded diesel smoke came out cell-identical
to the onboarded report). Onboarded-vehicle output verified 0-diff on fast smokes;
the full 7-vehicle golden compare (P5) is the remaining gate before merge. One plan
deviation: SRF capacity resolution reads `fuel_capacity` directly off the `Vehicle`
object (the speculative `vehicle_classes` lookup was dropped as unreliable).

## 2026-07-16 — ADR-001 (retrospective): v3.0.0 behaviour-preserving refactor

Recorded retrospectively: v3.0.0 restructured the package (segmentation/ split,
report_builder split, capacity extraction, packaging fixes, English translation,
facades preserving every import path) with golden-compare verification
(7/7 vehicles cell-identical vs 2.2.8). Established the verification infrastructure
reused by later structural work: `tmp/v300_compare/` harness (baseline generation
script + cell-by-cell comparator + vehicles.json snapshot protocol) and
`tests/` contract suite. Full record: `tmp/v300_changes_log.md`,
`tmp/v300_handover_for_james.md`, changelog week 20260713.
