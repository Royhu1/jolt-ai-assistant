# v3.2.0 Workspace Form & Comment Cleanup — Architecture Plan

> Owner: `project-architect` (ADR-003). Implementation branch:
> `refactor/v3.2.0-workspace-form` in worktree `.claude/worktrees/v320-workspace`,
> based on `main` `b765afe` (= v3.1.0 merged, tagged, verified).
> **Behaviour-preserving change**: no numeric surface is touched. Verification =
> AST-mask proof (W2) + fast EV / short diesel smokes vs existing golden outputs
> (0 diffs) + the full test suite. A fresh 7-vehicle golden regen is **not**
> required — see §4 (reasoned verification decision).

## 0. Goals & user decisions (2026-07-21)

1. `jolt_toolkit` stops being shaped as an installable Python **package** and becomes a
   plain **code workspace**: James / the SRF platform vendors the folder (copy it, install
   deps, put `src` on the import path). No `pip install`, no wheel, no console script.
2. The code **stays at `src/jolt_toolkit/`** — workspace is a change of *form*, not
   *location* (dozens of `PYTHONPATH=src` references repo-wide make relocation pure churn).
3. Strip redundant comments from the toolkit code — especially **version-difference
   narration** ("added in v2.2.3", "since v3.1.0", facade "Removed in v3.1.0" storytelling,
   migration notes inside docstrings).
4. Create **`src/jolt_toolkit/versions.md`** recording the main differences between
   versions. It lives *inside* the toolkit folder so it travels with the vendored
   workspace; the version-history knowledge removed from code comments lands here
   (condensed) — nothing is lost.
5. Version: **3.2.0**, git tag `v3.2.0` after merge (user prefers minor bumps; ADR-002
   precedent — all consumers are in-repo and rewired in the same change).

## 1. Change map (surface → change → owner → phase)

| Surface | Change | Owner | Phase |
|---|---|---|---|
| `pyproject.toml` | Drop `[build-system]`, `[project]` (incl. `dependencies`, `optional-dependencies`, `scripts`) and both `[tool.setuptools.*]` tables. Keep ONLY `[tool.black]`, `[tool.isort]`, `[tool.pytest.ini_options]` — a tool-config-only pyproject is legitimate for a non-package repo. `pythonpath = ["src"]` **stays**: it is what keeps `pytest` working with no install. | jolt-toolkit-dev | W1 |
| Dependencies | NEW `src/jolt_toolkit/requirements.txt` = the toolkit's **runtime** deps (the 11 currently in `[project].dependencies`) so they travel with the vendored folder. Root `requirements.txt` becomes `-r src/jolt_toolkit/requirements.txt` + the repo-level extras (matplotlib, scikit-learn, dev toolchain) — **each dep declared exactly once**. Header comments rewritten (no more "declared in pyproject"). See §2b for the rationale and the flat-file fallback. | jolt-toolkit-dev | W1 |
| `src/jolt_toolkit/__init__.py` | Plain `__version__ = "3.2.0"` constant; drop the `importlib.metadata` + pyproject-walking resolution entirely. | jolt-toolkit-dev | W1 |
| `report_generator/cli.py` | `prog="jolt-report"` → `prog="python -m jolt_toolkit.report_generator.cli"`; module docstring's `jolt-report` example updated. The documented entry points become the module form + library import. | jolt-toolkit-dev | W1 |
| `tests/test_cli.py` | Update the `--help` assertion (`"jolt-report" in out` → the module-form prog string); docstring updated. These tests already run via `python -m` subprocess with `PYTHONPATH=src`, so nothing else changes. No other test asserts dist metadata (checked 2026-07-21: the only `pyproject` mention in `tests/` is a comment in `test_imports.py`). | jolt-toolkit-dev | W1 |
| `src/jolt_toolkit/DEPLOYMENT.md` | Install section rewritten for **vendoring**: copy the folder + `pip install -r requirements.txt` (the folder's own) + import-path setup (`PYTHONPATH`, a `.pth` file, or `sys.path` in the platform harness); "verify" block switches to the module form + `python -c "import jolt_toolkit; print(jolt_toolkit.__version__)"`; drop the wheel/package-data/`[dev]`-extra language (configs now always read from the folder itself — the `JOLT_CONFIG_DIR` copy-to-writable-dir advice stays, for the capacity ledger). | jolt-toolkit-dev | W1 |
| `src/jolt_toolkit/README.md` | Install/quickstart rewritten (module form + library import; no console script); the **v3.0.0 and v3.1.0 migration-notes sections are deleted** in favour of a pointer to `versions.md` (their content is absorbed there, condensed). | jolt-toolkit-dev | W1 |
| `src/jolt_toolkit/versions.md` | NEW — see content spec §2c. | jolt-toolkit-dev | W1 |
| Package code comments (96 `vX.Y.Z` mentions across 26 files, plus restating-the-code and stale cross-reference comments) | Cleanup per rules §2d; AST-mask proof. | jolt-toolkit-dev | W2 |
| `.claude/rules/git-workflow.md` | "Version belongs to pyproject" wording → the `__version__` constant in `src/jolt_toolkit/__init__.py` + history in `versions.md`; release-procedure step 3 becomes "bump `__version__` + append the `versions.md` section". Tagging discipline unchanged. | general agent (under this plan) | W3 |
| `.claude/rules/code-style.md` | Cosmetic: "tools configured under `[project.optional-dependencies].dev` in pyproject" → "the dev toolchain in `requirements.txt`" (black/isort/mypy config still lives in pyproject `[tool.*]`). The sub-project-independence wording ("the versioned `src/jolt_toolkit`") stays — still true via the `__version__` constant. | general agent | W3 |
| Root `README.md` | Environment-setup section: `pip install -e .` → workspace setup (`.pth` file or `PYTHONPATH=src`); layout-table line "the only installable, versioned unit" → "the core toolkit workspace (src-layout; the versioned unit)"; the note about `pyproject.toml` "defines the package" → "carries the formatting/test tool config". | general agent | W3 |
| `research_projects/README.md`, `.claude/skills/vehicle-onboarding/` (README + `static/core/workflow.md`), `.claude/skills/param-tuner/` (README + `static/core/workflow.md` + `static/core/principles.md`), `.claude/agents/jolt-toolkit-dev.md` | Sweep the remaining live `pip install -e` / `jolt-report` console-script references to the workspace form (module CLI / `.pth`). Skill file edits ⇒ **patch bump each touched skill's `manifest.yaml` version**. | general agent | W3 |
| Historical records — changelogs, `.claude/health_checks/*`, skill `evaluations/*` logs | **NOT touched** (frozen history; the `pip install -e` gotcha in `LESSONS.md` simply becomes obsolete — the `.pth` setup reads the version from source, never stale). | — | — |

**Out of scope**: any change to numeric processing; the dist-repo sync for James
(separate pending item — this change makes it trivial: vendor `src/jolt_toolkit` as-is);
renaming the `jolt` conda env setup beyond the post-merge `.pth` swap (§2e).

## 2. Design details

### 2a. De-packaging shape

Final `pyproject.toml` ≈ 15 lines: a header comment ("tool config only — jolt_toolkit is
a vendored code workspace since v3.2.0, not an installable package; deps in
`requirements.txt`, version in `src/jolt_toolkit/__init__.py`, history in
`src/jolt_toolkit/versions.md`") + `[tool.black]` + `[tool.isort]` +
`[tool.pytest.ini_options]` exactly as today. Nothing else. `pip install .` in the repo
must FAIL (no `[project]` table) — that is the intended signal that installing is no
longer the supported form.

`__version__` audit (done 2026-07-21): the constant feeds only (i) the wrapper default
out-dir `./excel_report_database/<version>` in `report_generator/__init__.py`, (ii) CLI
display, (iii) in-repo consumers (`generate_report.py` / `batch_generate.py` /
`data_dashboard.py` / `run_monitor.py` / `generate_figures.py` / `generate_pdf_report.py`
/ `recompute_from_cache.py`) — all read the attribute, none read dist metadata. It is
**not written into xlsx cells**, so the 3.1.0 → 3.2.0 bump cannot pollute the golden
smoke compares (which pass explicit `--out-dir`). Nit for the W1 brief: `_generator.py:21`
imports `__version__` but appears not to use it — jolt-toolkit-dev may drop the import
after confirming no consumer imports it via `_generator` (suite + smokes cover it);
optional, not required.

### 2b. Dependency single-source (refinement of pre-decision 3)

Pre-decision: "requirements.txt becomes the single dependency source". Refinement, by the
same "travels with the workspace" logic that puts `versions.md` inside the folder: the
**runtime** deps move to `src/jolt_toolkit/requirements.txt` (the vendorable unit is
self-describing — James copies one folder and has code + deps + version history), and the
root `requirements.txt` opens with `-r src/jolt_toolkit/requirements.txt` (pip resolves
the path relative to the including file) followed by the repo-level extras. Single-source
is preserved: every dep is declared in exactly one file. **Fallback if the user prefers
strictly one file**: keep the flat root `requirements.txt` and have DEPLOYMENT.md name the
runtime subset inline (accepting a second, driftable list — the reason this is not the
primary design).

### 2c. `versions.md` content spec

Location `src/jolt_toolkit/versions.md`. One concise section per notable version, a few
bullets each (facts mined from `changelogs/`, the package README's v3.0.0/v3.1.0 migration
notes — absorbed then deleted — and the git tags `v1.0.0`…`v3.1.0`):

- **1.0.0** — report scope baseline (initial Excel report generator).
- **2.0.0** — src-layout unification (`src/jolt_toolkit` package form, unified
  segmentation algorithm).
- **2.2.1 → 2.2.8** — the 2.2.x series highlights, one short block per tag (e.g. 2.2.3
  weather patching / canonical DB; 2.2.4 robust-mass + sub-project independence; 2.2.5
  per-leg operator resolution; 2.2.6 configurable robust mass + one-figure-per-day +
  weather-cache rekey + trip-only weather; 2.2.7/2.2.8 charger fusion + per-vehicle
  SOC-fallback energy rewrite). Verify each claim against the changelog week before
  writing — do not trust memory.
- **3.0.0** — behaviour-preserving architecture refactor (segmentation/ split,
  report_builder split, facades, English translation; golden-verified 7/7 vs 2.2.8).
- **3.1.0** — platform slimming (rendering/dashboard/finetune/params re-homed to skills;
  matplotlib dropped) + general fallback pipeline for un-onboarded regs.
- **3.2.0** — workspace form (de-packaging), comment cleanup, and this file.

Discipline going forward: `versions.md` is **append-forward** — every future version bump
appends a section here in the same change (this becomes part of release-procedure step 3,
synced in W3). Where a deleted code comment carried a version fact not yet in the list
(e.g. a "changed in v2.2.6" note on a specific threshold), W2 condenses it into the
matching section rather than dropping it.

### 2d. Comment-cleanup rules (W2)

**DELETE**:
- Version-history narration: any "vX.Y.Z:"-style added-in / changed-in / removed-in
  commentary; "since v…" / "as of v…" qualifiers; facade migration storytelling (the
  "Removed in v3.1.0 → …" narration blocks in `segment_algorithms.py` and
  `report_generator/__init__.py`); migration notes inside docstrings ("kept only for
  backward-compatible call sites since v…").
- Restating-the-code comments (comments that paraphrase the next line).
- Stale cross-references (paths/modules that no longer exist).

**KEEP** (constraint / rationale comments — the *why*, not the *when*):
- Physical units and unit conventions (`mass_kg`, `v_c` m/s …).
- Ordering / precedence warnings (e.g. the c_params merge-order note).
- Cache-key compatibility warnings; column-index guard explanations (`_COL_*` hardcoded
  1-based indices / append-only HEADERS contract).
- The `figure_hook` contract docstring; the `=NA()` cell contract; SOC==0-is-invalid.
- Ownership/routing facts with the version stamp removed: a facade must still say
  *"these names live in the report-visuals skill; this module re-exports the
  `segmentation/` names"* — it just stops saying *when* that became true (versions.md
  carries the when).

**Verification** (comments are invisible to the AST): new scratch script
`tmp/v320_ast_proof/ast_mask_check.py` — for every `src/jolt_toolkit/**/*.py`, parse
before/after, strip docstrings, mask string constants, compare `ast.dump()`; all files
must be identical. The string-mask is deliberately permissive (docstrings/log text may
change), so two guards close the loop: (i) non-docstring string literals may only change
where they are pure narration (log/help text), and every such change is enumerated in the
commit message; (ii) the smokes + full suite re-run green after W2.

### 2e. Local env continuity (post-merge, orchestrator — NOT a branch change)

The `jolt` conda env's editable install is replaced by a `.pth` file in its
`site-packages` containing the absolute path to `<repo>/src`. Every existing skill/agent
invocation (`python -m jolt_toolkit...`, plain `import jolt_toolkit`) keeps working with
zero call-site changes. Side benefit: the long-standing "re-`pip install -e .` after a
version bump or `__version__` goes stale" gotcha (health-check LESSONS) disappears — the
version is now read from source. Also post-merge: regenerate the gitignored `README.zh.md`
copies for the touched READMEs via `/translate-doc`.

## 3. Phases (each = independently verified commit(s) on the branch)

### W1 — De-packaging + versions.md + package docs (jolt-toolkit-dev)
Scope: rows 1–9 of §1. The two repo-root files (`pyproject.toml`, `requirements.txt`) are
explicitly in-scope for the jolt-toolkit-dev brief — they define the toolkit's form.
Constraints to carry in the brief: no behaviour change; `pythonpath=["src"]` must survive;
`__version__` = "3.2.0" plain constant; prog-string decision as §1; versions.md spec §2c.
**Verify**: full suite green from the worktree root (`pytest` — no install present);
fast EV + short diesel smokes vs goldens (0 diffs — commands §4); `--help` exit 0 via the
module form in an env where `jolt-toolkit` is NOT installed (PYTHONPATH-only);
`python -c "import jolt_toolkit; print(jolt_toolkit.__version__)"` → `3.2.0` the same way;
`pip install .` from the worktree fails (no `[project]`) — intended.

### W2 — Comment cleanup + AST proof (jolt-toolkit-dev)
Scope: §2d across the package (survey: 96 `vX.Y.Z` occurrences in 26 files; densest:
`capacity.py` 16, `_generator.py` 14, `columns.py` 8, `row_builder.py` 7,
`diesel_pipeline.py` 7, `mass_clustering.py` 7). Any version *fact* not already in
versions.md is condensed into it in the same commit.
**Verify**: `ast_mask_check.py` PASS on every file; enumerated string-literal changes in
the commit message; suite + both smokes re-run (0 diffs).

### W3 — Repo governance docs (general agent under this plan)
Scope: rows 10–13 of §1 (rules files, root README, research_projects README, the two
skills' docs + manifest patch bumps, jolt-toolkit-dev agent doc). Historical records
untouched.
**Verify**: `python .claude/scripts/check_skill_registry.py` green;
`python .claude/scripts/check_subproject_independence.py` green;
`grep -rn "pip install -e\|jolt-report" --include="*.md"` over the worktree returns only
historical records (changelogs / health_checks / evaluations) and `versions.md` itself.

### W4 — Verification wrap + merge decision (project-architect + user)
Review W1–W3 evidence against the acceptance criteria (§5); update this plan's §6 status
table and the ADR outcome line; hand the merge decision to the user. After merge (user
consent for any push, per git-workflow): `git tag v3.2.0`; then the post-merge steps of
§2e (orchestrator).

## 4. Verification protocol — commands and the no-regen decision

**Why no fresh 7-vehicle golden regen**: W1 removes packaging metadata and changes a
version constant that is provably outside the xlsx numeric surface (§2a audit); W2 is
AST-invariant by construction. The residual risk (import-time breakage, path handling) is
fully exercised by the suite + two smokes. A 7-vehicle regen would re-test the same code
paths at ~100× the cost. Decision: fast EV + short diesel smoke + suite are sufficient;
recorded here as the reasoned verification decision (ADR-003).

Run from the **main repo root** (so `./cache` and `.env` hit), with the worktree's `src`
first on the import path:

```powershell
$wt = "D:\OneDrive - University of Cambridge\Research\JOLT_Report\.claude\worktrees\v320-workspace"
$env:PYTHONPATH = "$wt\src"; $env:PYTHONUTF8 = "1"

# 1. Test suite (from the worktree root; pyproject pythonpath covers imports)
cd $wt; python -m pytest tests/ -q

# 2. Fast EV smoke — golden: tmp/v300_compare/smoke_baseline (YK73WFN, proven ≡ 2.2.8/3.0.0/3.1.0)
cd "D:\OneDrive - University of Cambridge\Research\JOLT_Report"
python -m jolt_toolkit.report_generator.cli -veh YK73WFN -ds 2025-04-01 -de 2025-04-15 --fast --out-dir tmp\v320_compare\smoke_w1
python tmp\v300_compare\compare_reports.py tmp\v300_compare\smoke_baseline tmp\v320_compare\smoke_w1   # exit 0 required

# 3. Short diesel smoke — golden: tmp/v300_compare/diesel_ref_p3c (WU70GLV; ≡ tmp/v310_compare/smoke_p2_diesel_ref)
python -m jolt_toolkit.report_generator.cli -veh WU70GLV -ds 2025-09-01 -de 2025-09-04 --out-dir tmp\v320_compare\smoke_w1_diesel
python tmp\v300_compare\compare_reports.py tmp\v300_compare\diesel_ref_p3c tmp\v320_compare\smoke_w1_diesel   # exit 0 required

# 4. Workspace-form checks (no dist installed — PYTHONPATH only)
python -m jolt_toolkit.report_generator.cli --help          # exit 0
python -c "import jolt_toolkit; print(jolt_toolkit.__version__)"   # → 3.2.0
```

W2 re-runs steps 1–3 plus `python tmp\v320_ast_proof\ast_mask_check.py` (compares the
worktree HEAD~1 vs HEAD trees, or a pre-cleanup copy).

## 5. Acceptance criteria (gate for W4 / merge)

1. Suite green; both smokes 0 diffs at every phase boundary that touched code.
2. `pyproject.toml` contains only the three `[tool.*]` tables; no `[project]`/`[build-system]`.
3. `import jolt_toolkit` + module CLI work with `PYTHONPATH=src` only (no installed dist).
4. `versions.md` exists, covers 1.0.0 → 3.2.0, and absorbs every version fact deleted
   from code comments and the README migration sections.
5. AST-mask proof PASS for all W2 files; string-literal changes enumerated.
6. No live doc still instructs `pip install -e .` / `pip install .` / `jolt-report`
   (historical records exempt); registry + independence checks green; touched skills'
   manifests patch-bumped.
7. Changelog entry + ADR-003 outcome line updated at wrap-up.

## 6. Execution status

| Phase | Status | Commits |
|-------|--------|---------|
| W1 — de-packaging + versions.md + package docs | pending | — |
| W2 — comment cleanup + AST proof | pending | — |
| W3 — repo governance docs | pending | — |
| W4 — verification wrap + merge decision | pending | — |
