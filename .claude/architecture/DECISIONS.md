# Architecture Decision Records (ADR log)

> Owned by the `project-architect` agent. One dated entry per material structural
> decision: context → options considered → decision → consequences. Newest at the top.
> Plan documents for in-flight changes live beside this file.

## 2026-07-21 — ADR-003: v3.2.0 workspace form — de-packaging, comment cleanup, versions.md

**Context**: user decision 2026-07-21 — the SRF platform will **vendor the toolkit
folder**, not pip-install it. The installable-package form (build-system, wheel +
package-data metadata, `jolt-report` console script, `importlib.metadata` version
resolution) is now dead weight and a second dependency-declaration surface that can
drift from `requirements.txt`. Separately, the code carries accumulated version-history
narration in comments (survey 2026-07-21: 96 `vX.Y.Z` mentions across 26 package files
— "added in v2.2.3", "since v3.1.0", facade "Removed in v3.1.0" storytelling) that
duplicates changelog/README-migration content and rots in place; the user wants it
stripped and a standalone `versions.md` created instead.

**Options considered**:
1. *Form*: (a) keep the installable package (status quo); (b) plain code workspace,
   code staying at `src/jolt_toolkit/` — **chosen**; (c) workspace + relocate out of
   `src/` — rejected: form ≠ location, and dozens of `PYTHONPATH=src` references
   repo-wide make relocation pure churn.
2. *Version identity*: (a) 4.0.0 (formally breaking — console script + dist metadata
   disappear); (b) **3.2.0 minor — chosen** (user preference; every consumer is in-repo
   and rewired in the same change; ADR-002 precedent).
3. *Version-history knowledge*: (a) leave in code comments (rots, duplicates); (b)
   delete outright (loses facts); (c) **move condensed into `src/jolt_toolkit/versions.md`
   — chosen** (travels with the vendored folder; append-forward from now on, wired into
   the release procedure).
4. *Dependency source*: requirements.txt becomes the single source (pre-decision).
   Mechanical refinement adopted at plan level: runtime deps live in
   `src/jolt_toolkit/requirements.txt` (the vendorable folder is self-describing — same
   "travels with the workspace" logic as versions.md), and the root `requirements.txt`
   includes it via `-r` plus repo-level extras; each dep declared exactly once.
   Flat-single-file fallback documented in the plan if the user prefers.

**Decision**: proceed per `plan_v320_workspace_form.md` (beside this file). Shape:
`pyproject.toml` keeps only `[tool.black]`/`[tool.isort]`/`[tool.pytest.ini_options]`
(with `pythonpath=["src"]` — what keeps `pytest` working uninstalled); `__init__.py`
gets a plain `__version__ = "3.2.0"` constant; the CLI's documented entry points become
`python -m jolt_toolkit.report_generator.cli` + library import; DEPLOYMENT.md rewritten
for vendoring; comment cleanup per crisp DELETE/KEEP rules (delete the *when*, keep the
*why*: units, ordering warnings, cache-key/column-index/`=NA()` contracts, figure_hook
docstring, routing facts). Local env continuity post-merge via a `.pth` file pointing at
`<repo>/src` — zero call-site changes for skills/agents. Implementation: W1/W2 →
jolt-toolkit-dev (the two repo-root form files `pyproject.toml`/`requirements.txt`
explicitly in its brief), W3 → general agent, W4 → architect review + user merge call.

**Verification decision (reasoned)**: no fresh 7-vehicle golden regen. The `__version__`
constant was audited as outside the xlsx numeric surface (feeds only the wrapper default
out-dir + CLI display), W2 is AST-invariant by construction (AST-mask proof: strip
docstrings, mask strings, identical dumps), and the residual import/path risk is fully
exercised by the 249-test suite + fast EV (YK73WFN) and short diesel (WU70GLV) smokes vs
the standing goldens (0 diffs required) — a regen would re-test the same paths at ~100×
cost.

**Consequences**: `pip install .` intentionally stops working (the signal that
installing is no longer the supported form); the git-workflow rule "version belongs to
pyproject" moves to the `__version__` constant + versions.md; release-procedure step 3
gains "append the versions.md section"; the health-check LESSONS gotcha "re-`pip
install -e .` after a version bump" becomes obsolete under the `.pth` setup; the
dist-repo sync for James reduces to "vendor `src/jolt_toolkit` as-is".

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
