> Naming conventions — referenced from the root `CLAUDE.md` "## Naming Convention" section via `@import`.
> Editing here = editing the file / directory / artefact naming conventions for the whole project (team-shared, committed with `.claude/`).

> This file governs only **project-level data / artefact / file / directory naming**. Python identifiers (`snake_case` /
> `PascalCase` / `UPPER_SNAKE` / private leading underscore), abbreviation consistency, physical-unit suffixes, and one-off script
> naming (`_tmp_*.py` / `_patch_*.py` / `tools_*.py`) are in `code-style.md`; branch / commit /
> version tag / changelog file names are in `git-workflow.md`.

### Vehicle / directory / skill

- **Vehicle registration**: uppercase, no spaces, exactly as on the plate (e.g. `YK73WFN`, `CMZ6260`);
  used as the `<REG>` token throughout directory names, report file names and config files.
- **Folders**: lowercase `snake_case` (e.g. `data_analysis_workspace`, `excel_report_database`);
  the only exception is the core package directory `src/jolt_toolkit`.
- **skill / agent / command**: kebab-case (e.g. `plot-figure`, `generate-excel-report`,
  `jolt-toolkit-dev`).

### Date / period

- Data fields and per-day timestamps: ISO `YYYY-MM-DD`.
- Date-bearing directories (e.g. `monthly_presentation/<YYYYMMDD>/`): compact `YYYYMMDD`.
- Report period: `YYYYMMDD_YYYYMMDD` (start_end).

### Report artefacts

- Report file: `excel_report_database/<version>/<REG>/jolt_report_<REG>_<start>_<end>.xlsx`.
- HTML viewer: `inspect_*.html`; raw telematics: `raw_telematics/raw_*.csv`;
  validation figures: `validation_<REG>_<YYYY-MM-DD>.png` (+ `.boxes.json` sidecar) —
  one figure per day since v2.2.6; legacy per-leg `validation_<REG>_<date>_<NNNN>.png`
  files (NNNN = leg index) persist for some vehicles and are kept as history.
- Post-processing (finetune) artefacts always take the `*_finetuned.*` suffix, and **never overwrite the original file**.

### Versioned output layout

- `excel_report_database/<version>/<REG>/` and `figures/<version>/{named,anon}/`
  (`named` = real OEM labels, `anon` = anonymised); `<version>` is the SemVer of `src/jolt_toolkit`.

### Bilingual documentation

- `README.md` is the committed authoritative English version; `README.zh.md` is the gitignored Chinese copy,
  kept in sync via `/translate-doc`.
