> Python code style — referenced from the root `CLAUDE.md` "## Code Style" section via `@import`.
> Editing here = editing the code-style conventions for the whole project (team-shared, committed with `.claude/`).

Python code follows PEP 8, and uses the dev toolchain declared in the root
`requirements.txt` for a uniform style (the tool *configuration* — line width, isort
profile, pytest options — lives in the `[tool.*]` tables of `pyproject.toml`):

- **Formatting**: `black` (default line width 88).
- **import ordering**: `isort` (standard library / third-party / local — three separated groups).
- **Static typing**: `mypy`; public functions should provide type annotations for parameters and return values wherever possible.

### Naming rules

| Object | Style | Example |
|------|------|------|
| Package / module file | `snake_case` | `report_generator`, `segment_algorithms.py` |
| Function / method / variable | `snake_case` | `compute_ep`, `find_speed_trips` |
| Class | `PascalCase` | `JOLTReportGenerator`, `WeatherPatcher` |
| Constant / module-level config | `UPPER_SNAKE_CASE` | `HEADERS`, `BASELINE`, `ETA_DT` |
| Internal / private (module / function / attribute) | leading underscore | `_generator.py`, `_seg_to_row()`, `_safe_num()` |

- Identifiers must always be in English; keep abbreviations consistent across the project (`ep` = energy performance, `soc`, `crr`, `cda`, etc.).
- Quantities carrying physical units should state the unit in the name or a comment, e.g. `delta_energy_kwh`, `mass_kg`, `v_c` (m/s).

### Other conventions

- Prefer `pathlib.Path` for paths; use f-strings for string formatting.
- Name one-off / temporary scripts `_tmp_*.py` / `_patch_*.py` (already gitignored; delete after use, do not write them into the README).
- **Code comments and docstrings must always be written in English** — even when the working / communication language is Chinese. Code is shared via the repository, so keeping comments uniformly in English aids international collaboration. All content committed / pushed to the repository — code, comments, docstrings, documentation, changelogs, configs — is written in **English**; Chinese is used ONLY for (a) interactive chat replies and (b) the gitignored `*.zh.md` local reading copies.

### Sub-project independence (from 2026-06-11)

Sub-projects under each workspace (`data_analysis_workspace/`, `research_projects/`, `publication_workspace/`,
`monthly_presentation/`, etc.) must be **mutually independent** — a sub-project is a reproducible research archive,
and should be deletable / archivable on its own without breaking the other sub-projects:

- Only three kinds of code dependency are allowed: stdlib / pip packages, the versioned `src/jolt_toolkit`
  (including `jolt_toolkit.analysis`: counter interpolation, OLS/FE regression utilities, the `eta_bat` physics model),
  and the sub-project's own files. **`sys.path.insert` pointing at other sub-projects is forbidden** — if you need code from elsewhere, copy it (vendoring).
- A vendored copy must carry a provenance header: source repo relative path, copy date, symbol list,
  reason (sub-project independence); do not modify the function body unless you intend to keep it in sync with the source.
- **Rule of three**: machine code reused by 3+ sub-projects and already stable should be promoted into `jolt_toolkit.analysis`
  (route the change to the jolt-toolkit-dev agent, bump the version by a SemVer minor); do not copy it endlessly.
- Data dependencies may only read `excel_report_database/<version>/` (versioned, append-only),
  and **reading other sub-projects' `results/` is forbidden**. Cross-linking documents (README links) is unrestricted.
- Frozen snapshots older than this convention (`monthly_presentation/20260422/`, `data_analysis_workspace/deprecated/`)
  are exempt (grandfathered), are not guaranteed to be re-runnable, and must not be extended.
- Read-only check: `python .claude/scripts/check_subproject_independence.py [--verbose]`
  (AST-parses `sys.path.insert` targets, exit 1 on violation).

> The report-generation package's architecture conventions (src-layout, the unified segmentation algorithm, `HEADERS` column order, configs, deprecated, etc.)
> are in `src/jolt_toolkit/README.md`; the agent ownership of each major directory and the discipline of "to change its code, route to the corresponding agent"
> are defined in each `.claude/agents/*.md` (the owner is declared in the agent's description).
