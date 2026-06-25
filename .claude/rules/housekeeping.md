> Tidiness and local-storage conventions — referenced from the root `CLAUDE.md` "## Housekeeping & Local Storage" section via `@import`.
> Editing here = editing the temp-file cleanup / archiving / local-storage conventions for the whole project (team-shared, committed with `.claude/`).

> This file governs **project tidiness and where files land**: where temporary / stale files are cleaned and archived to, and which files should stay on
> local disk rather than OneDrive. For Python identifiers / one-off script naming see `code-style.md`; for data / artefact /
> directory naming see `naming.md`; for branch / commit / changelog see `git-workflow.md`.

### Temporary files: zones and cleanup

| Zone | Purpose | In git | Cleanup policy |
|------|------|--------|---------|
| `tmp/` | one-off scratch (logs / intermediate CSVs / debug figures / `_tmp_*.py`) | No | clean after use; during a health check archive the whole directory to the local `scratch_archive/` (move, not delete) |
| `cache/` | API caches for SRF / weather, etc. | No | **Do not clean lightly** — rebuilding is expensive and subject to API quotas; at most clean stray test files in the root directory |
| `archive/` | recycle bin: superseded / retired artefacts | No | in only, never out; root-level scratch produced by a health check goes to `archive/root_scratch_<YYYYMMDD>/` |
| `unarchived/` | the "holding area" not yet slotted into place | No | triage periodically: either slot it back into a blueprint directory, or retire it into `archive/` |

- **Keep the repository root clean**: do not drop one-off scripts / logs directly in the root; they belong in `tmp/`,
  or are moved into `archive/root_scratch_<YYYYMMDD>/` during a health check. Root-level scratch that is already gitignored should also be physically moved away,
  not merely hidden behind gitignore.
- **Prefer archiving over deletion**: clean up by `Move-Item` to `archive/` or the local `scratch_archive/`, preserving traceability;
  only delete what is genuinely reproducible waste. (Note: the sandbox intercepts `Remove-Item` on top-level / protected paths, so move is safer.)
- **OneDrive note**: close Excel before cleaning / regenerating xlsx (lock files will make the move fail); archiving large-volume scratch
  to local disk can also help ease the OneDrive sync burden.

### Local storage: OneDrive vs local disk

The repository itself lives under OneDrive and syncs to the cloud. JOLT files that **need to stay local and should not go to the cloud** are consolidated under the local root
**`D:\JOLT_local\`** (machine-local, not in git, not on OneDrive):

| Sub-directory | What goes there |
|--------|--------|
| `git_backups/` | old repository / bare `.git` history backups (e.g. snapshots from a clean rebuild) |
| `scratch_archive/` | scratch archived from the repo's `tmp/` or from various places on the D drive (organised into sub-directories by source: `repo_tmp_<date>` / `D_temp` …) |
| `<service>/` | local services / large-volume data (e.g. a local routing engine, OSM extract), set up as needed |

- Criteria for choosing local disk: **large-volume, rebuildable, machine-local, or unsuitable for the cloud** (backups, cache snapshots, routing data, etc.).
  The actual project source / documentation still stays inside the repository, travelling with git and OneDrive.
- Do not scatter JOLT leftovers in casual places like `D:\temp` / `D:\tmp` / the `D:\` root — consolidate them under `D:\JOLT_local\`.

> Enforcement of this convention and periodic health checks are the responsibility of the `project-health-steward` agent (see `.claude/agents/`);
> each health-check record is kept in `.claude/health_checks/`, with experience accumulating run by run.
