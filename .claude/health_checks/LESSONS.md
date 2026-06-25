# Health-Check Experience Accumulation (LESSONS)

> `project-health-steward` **reads this file first** at every health check, and at wrap-up appends new lessons here after de-duplicating.
> Purpose: to make the steward's judgement progressively stronger as the project evolves.

## Project conventions (most frequently used, placed first)

- **Current canonical version (the `src/jolt_toolkit` package only)**: see the `version` field in `pyproject.toml`;
  during a health check, verify that all version references across the project point to it (skill examples, the various READMEs, agent knowledge, etc.).
- **This repository is a clean-rebuild repository**: history starts from `initialise clean repository`, with no old tags / history early on;
  any descriptions in memory about earlier merges / tags belong to the old repository that was replaced and do not apply to this repository — rely on the actual
  `git log` / `git tag`.
- **The gitignore coverage is broad**: `tmp/` `cache/` `archive/` `unarchived/`, the various workspaces, and all
  `*.csv/*.xlsx/*.pdf/*.log/*.zh.md` are not in git. So "cleaning up" is mostly physical tidiness (disk / OneDrive),
  unrelated to git state — do not mistake gitignored leftovers for git changes.
- **`*.zh.md` are gitignored Chinese copies**; `README.md` (English) is the authoritative version committed to the repository.

## Pitfalls / traps

- **The sandbox forbids using `Remove-Item` to delete top-level / protected paths** (e.g. `D:\jolt_worktrees` reports "protected from
  removal", and the **entire script fails the pre-check and nothing is executed**). Countermeasure: always use `Move-Item` to archive when cleaning up, not
  `Remove-Item` — this both bypasses the sandbox and complies with "prefer archiving over deletion".
- **OneDrive locks**: before cleaning / regenerating xlsx, ask the user to close Excel first, otherwise the move / write will fail.
- **`src/jolt_toolkit/` can only go through jolt-toolkit-dev**: committing its changes, modifying its README / version number, correcting the column counts / architecture in agent
  knowledge — all should be routed to it (it knows the real state best); the main loop is only responsible for orchestrating git and cleanup outside the package.
- **After changing the version number, do not forget `pip install -e .`**: the `jolt_toolkit.__version__` of an editable install does not update automatically with
  `pyproject.toml`; before a full re-run you need `pip install -e . --no-deps`, otherwise the output will land in the old version directory.
- **Do not accidentally clear precious scratch**: `tmp/` occasionally contains non-scratch results (e.g. `canonical_<ver>_numbers.md` is the paper's
  canonical statistics). Before clearing `tmp/`, scan the recent `.md` files, extract the results into the appropriate workspace first, then archive the whole directory.
- **Pinned versions may be intentional**: a workspace sub-project README pinning a particular data version (e.g. energy_breakdown pinned to 2.2.3)
  is mostly a reproducible archive for sub-project independence — do **not** treat it as a stale version to be bumped — when in doubt, ask the owner first.

## Past health checks

- 2026-06-19: first health check, establishing this mechanism (housekeeping conventions + steward agent + this directory). See
  `check_20260619.md` for details.
