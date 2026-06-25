> Git workflow conventions — referenced from the root `CLAUDE.md` "## Git Workflow" section via `@import`.
> Editing here = editing the git / version / changelog conventions for the whole project (team-shared, committed with `.claude/`).

### Version number (refers only to the `src/jolt_toolkit` package)

The version number **belongs only to the `src/jolt_toolkit` package**, is maintained in the `version` field of `pyproject.toml`, and follows
SemVer; the project's other modules (`data_analysis_workspace/` / `research_projects/` / `publication_workspace/`, etc.) are not part of this scheme and are not tagged.

- `patch` (x.x.**N**): bug fixes / minor adjustments, no interface change
- `minor` (x.**N**.0): new features, backward compatible
- `major` (**N**.0.0): breaking interface changes
- Add a git tag alongside every version change: `git tag vX.Y.Z`

### Commit messages (Conventional Commits)

`feat:` new feature / `fix:` fix / `refactor:` refactor / `docs:` documentation / `chore:` version bump, dependencies and other maintenance.
Meaningless messages (such as "update", "checkpoint", "11") are forbidden.

### Pushing (push) requires user consent (mandatory)

- **Every `git push` (pushing to any remote / any branch, including `main`) must first obtain the user's explicit consent; you must not push on your own initiative.**
- commit / branch creation / local merge may proceed as usual per the workflow; but **always ask the user before a push**, stating what will be pushed and the target
  (branch, remote, whether tags are included). The user consenting to a push in one conversation is **not** treated as long-term authorisation for subsequent pushes — confirm each one separately.

### Branch strategy

- `main` is the stable mainline; **do not develop directly on main**. New changes go on feature branches: `feat/<description>` / `fix/<description>` /
  `refactor/<description>`.
- Merging: `git checkout main && git merge <branch>`; if a version change is involved, tag after merging.

### Standard version-release procedure

1. Complete the code change → 2. Update `src/jolt_toolkit/README.md` (architecture/field/module changes) →
3. Update the version number in `pyproject.toml` → 4. `git commit` → 5. `git tag vX.Y.Z`.

### Artefacts not committed to git

`cache/` / `excel_report_database/` / `figures/` / `publication_workspace/` and the generated charts and data are not committed (already in `.gitignore`).

### changelog (mandatory every conversation)

Before the end of every conversation, update `changelogs/changelog_YYYYMMDD_YYYYMMDD.md` (split into files by week Mon–Sun, with that week's Monday as
start and Sunday as end), recording this conversation's task prompt and a summary of the completed result in Q&A format; append if the current week's file exists,
otherwise create a new one. New changelog entries committed to the repository are written in **English** (existing historical Chinese entries are left as-is).
