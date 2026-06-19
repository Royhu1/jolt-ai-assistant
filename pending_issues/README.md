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
