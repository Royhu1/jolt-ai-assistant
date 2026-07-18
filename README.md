# JOLT — Joint Operators Logistics Trial

> **This file is the project map** — overall design, repository layout, and how to use & develop this project (including skills and commands). For *how to install and run the toolkit itself*, see the package README below. At every level, that directory's own `README.md` is the single source of truth for that directory.

## Project architecture: a hierarchical design

**Design philosophy: enable efficient human–AI collaboration (human developers + AI agents).**

- The repository is a tree (root + sub-projects); at every level, that level's `README.md` is the single source of truth for its structure, conventions and how to run it.
- Human developers: simply read / edit each level's `README.md` to achieve sound project management.
- AI agents: navigate via each level's `README.md` through progressive disclosure.

## Repository layout

Only the top level is shown. Any folder that has its own `README.md` documents its internal structure there.

```
./
├── src/jolt_toolkit         # core toolkit package (src-layout; the only installable, versioned unit)
├── excel_report_database    # directory holding the generated Excel reports
├── publication_workspace    # workspace for technical reports or academic papers
├── pdf_report_workspace     # generated partner-briefing artefacts (output_by_*/ + HERE-tile cache/); produced by the generate-pdf-report skill
├── data_collection_reports  # weekly data-collection digests (PDF + MONITOR_STATUS.md); produced by the data-collection-monitor skill
├── monthly_presentation     # workspace for preparing the monthly JOLT meeting slides
├── data_analysis_workspace  # relatively standalone data-analysis workspace, mainly for quick idea validation
├── research_projects        # systematic academic research projects
├── chatbot                  # development directory for this project's chatbot
├── changelogs               # weekly project changelog (Q&A summaries of every change)
├── pending_issues           # register of known-but-deferred issues (one .md per issue + index)
├── tmp                      # temporary-file directory, keeps the main directory clean
├── unarchived               # holding area for items not yet slotted into the blueprint
├── archive                  # recycle bin
├── requirements.txt         # Python dependency list (pip install -r)
├── README.md                # project map (this file)
├── CLAUDE.md                # Claude / AI collaboration conventions
└── .claude                  # Claude Code configuration, skills / commands / agents, etc.
```

> The generated / runtime directory `cache/` and the packaging file `pyproject.toml` at the repo
> root are omitted from this conceptual map (`cache/` is a gitignored build artefact;
> `pyproject.toml` defines the `src/jolt_toolkit` package). The report-generation CLIs
> (`generate_report.py` / `batch_generate.py` / `test_data_config.json`) and the
> cached-recompute tool (`tools/recompute_from_cache.py`) now live inside the
> `generate-excel-report` skill, and old analysis figures have been moved to `archive/`.

## Environment setup

- Configure the relevant API keys in `.env`.
- Python version requirement: **Python ≥ 3.10**.
- It is recommended to create an isolated environment with conda and install the dependencies:

```bash
# Create and activate an environment named jolt
conda create -n jolt python=3.11 -y
conda activate jolt

# Install the project dependencies
pip install -r requirements.txt

# Install the core package jolt_toolkit in editable mode (for local development)
pip install -e .
```

## Quick usage / development guide

### 1. Generate an Excel report

Type a natural-language prompt in Claude Code:

```
Generate the Excel report for YK73WFN in 2025
```

or a slash command:

```
/generate-excel-report YK73WFN 2025
```

This triggers the `generate-excel-report` skill, which calls the relevant code in `jolt_toolkit` to generate the requested `.xlsx` file. Notes:

- The relevant code in `jolt_toolkit` may take different arguments; when these are not specified, the skill asks you about each option (including the final output directory, which defaults to a sub-directory of `excel_report_database`).
- When the target vehicle is not in an existing pipeline, the `vehicle-onboarding` skill is triggered first — an AI agent automatically selects / designs a reasonable data-processing pipeline for the new vehicle and updates the relevant code and configuration files in `jolt_toolkit`.

### 2. Generate analysis figures

Type a natural-language prompt in Claude Code:

```
Generate the EP vs GVM figure for all Excel reports of vehicle YK73WFN
```

or a slash command:

```
/plot-figure EP vs GVM figure for YK73WFN
```

This triggers the `plot-figure` skill, which generates a png based on the skill's built-in plotting-style Python code, figure-style configuration and template figures, saved to `tmp` by default. Notes:

- The skill persists a self-contained, editable plotting script in the target workspace's `code/`/`scripts/` folder (named `plot_<figure>.py`, never a throwaway `_tmp_*.py`) and runs it from there to write the PNG into your chosen figures directory; you can then tweak and re-run that script to refine the figure, leaving the master `shared/generate_figures.py` style source untouched.

### 3. Quick validation of any idea

For example, type the following in Claude Code:

```
Analyse the relationship between the ratio of a vehicle's regenerative braking energy to its propulsion energy and the ambient temperature
```

This generates an agent dedicated to this small topic, which creates a sub-directory under `data_analysis_workspace` to work in:

- It generates data-analysis code / figures, etc., and when necessary searches online for relevant references and downloads / saves them.
- Finally it produces an analysis report in that sub-directory for developers (human or other AI agents) to review, then iterates based on the review feedback.

> Note: for analysis carried out with the help of AI agents, the quality of the results depends on the agent's capability and the quality of the prompt.

## Commands / Skills / Agents

All of these live under `.claude/`. Type `/<name>` in Claude Code to invoke a command or skill;
agents are launched automatically for larger tasks in their area.

### Shared design principles

All skills / commands / agents follow the shared design principles in
[`.claude/rules/skill-design.md`](.claude/rules/skill-design.md) (adapted from the
[nature-skills](https://github.com/Yuan1z0825/nature-skills) design philosophy) — one line each;
the rules file carries the full statements *with their reasons*:

1. **Single source of truth, progressive disclosure** — each level's `README.md` owns its structure; `SKILL.md` stays a lean router over `manifest.yaml`-declared fragments and `references/`.
2. **Explicit beats implicit** — rules state their reason; artefact paths and trigger phrases are written out, never assumed.
3. **Output-first** — every skill run ends in a directly usable artefact at a documented path.
4. **Single ownership, explicit routing** — each artefact / code area has exactly one owner; everyone else routes changes to it.
5. **Self-contained and extensible** — adding a skill never requires editing existing skills; content needed by ≥ 2 skills is promoted to a `_shared/` layer.
6. **Canonical data is append-only** — never overwrite: `*_finetuned` siblings, forward-only report database, archive over delete.
7. **Accumulate experience** — per-run knowledge persists next to the skill/agent (`evaluations/`, `references/<REG>.md`, audits, health checks).

Each index table below carries a **Status** column:

| Status | Meaning |
|--------|---------|
| `Draft` | Rules/workflow written, but not yet exercised on real fleet data. |
| `Beta` | Has produced real artefacts on part of the fleet; edge cases may remain. |
| `Stable` | Validated in routine use; other skills rely on its outputs. |

To add a new skill / command / agent, follow the procedure in
[`.claude/rules/skill-design.md`](.claude/rules/skill-design.md), add a row to the matching
index table below, then run `python .claude/scripts/check_skill_registry.py` — it verifies
these tables stay in sync with what exists under `.claude/` (one row per item, resolvable
links, valid statuses, minimum files per skill).

### Commands (`.claude/commands/`)

| Command | Status | What it does |
|---------|--------|--------------|
| [`/translate-doc <file>`](.claude/commands/translate-doc.md) | Stable | Regenerate the other side of a bilingual doc pair (`<name>.md` ↔ `<name>.zh.md`) from the side you just edited. |
| [`/check-doc-sync <file\|all>`](.claude/commands/check-doc-sync.md) | Stable | Check whether bilingual doc pairs are content-consistent; list out-of-sync pairs and what differs (read-only). `all` = check every pair. |

### Skills (`.claude/skills/`)

> Each JOLT skill follows the **router / static-dynamic split** (anatomy v2, adapted from
> nature-figure — see `.claude/rules/skill-design.md`): a short `SKILL.md` router +
> declarative `manifest.yaml` (always-loaded `static/core/` contracts, per-mode
> `static/fragments/`, on-demand `references/`) + a human-facing `README.md` — the skill's
> single source of truth, whose **Pipeline** section gives the quick walk-through (data in
> → processing → artefacts out, ownership, neighbouring skills; it absorbed the former
> `PIPELINE.md`). The skill names below link to that `README.md`.

| Skill | Status | What it does |
|-------|--------|--------------|
| [`/generate-excel-report <REG> <period>`](.claude/skills/generate-excel-report/README.md) | Stable | Generate a formatted Excel report for a vehicle + date range (drives the report CLI → `excel_report_database/`). |
| [`/generate-pdf-report <REG> <period>`](.claude/skills/generate-pdf-report/README.md) | Stable | Generate the industrial-partner one-page PDF/HTML briefing from xlsx pipeline artefacts (→ `pdf_report_workspace/output_by_TBD/`, frozen as `output_by_<YYYYMMDD>/` on finalisation). **Self-contained owner of all PDF-briefing development** — its own generator code (`generate_pdf_report.py` / `build_pdf.py` / `templates/`), layout, chart specs, commentary style guide and KPI computation all live in the skill; reads `excel_report_database/*.xlsx` (and may read-only call `jolt_toolkit.analysis`), routing to `jolt-toolkit-dev` *only* for new xlsx fields. |
| [`/generate-data-dashboard <version>`](.claude/skills/generate-data-dashboard/README.md) | Stable | Generate/refresh the offline data-availability dashboard (`data_dashboard.html`) for a report-database version. **Self-contained owner of the dashboard code** (`code/`, moved out of `jolt_toolkit` in v3.1.0); reads the package read-only. |
| [`/data-collection-monitor [--cadence weekly]`](.claude/skills/data-collection-monitor/README.md) | Beta | Periodic (designed for `/loop`, default weekly) fleet data-intake check: append-only extends `excel_report_database/<version>/` with newly-collected SRF data (never overwrites), refreshes the dashboard, and emits a fixed-template PDF "data collection digest" (+ `MONITOR_STATUS.md`) → `data_collection_reports/`. |
| [`/plot-figure`](.claude/skills/plot-figure/README.md) | Stable | Generate energy-performance figures (EP-vs-mass scatter+fit, range, per-OEM…) from xlsx reports into a `--out-dir` you specify. |
| [`/report-visuals <REG\|dir>`](.claude/skills/report-visuals/README.md) | Draft | Repaint validation figures (one PNG per day + `.boxes.json` overlay sidecars) and (re)write `inspect_*.html` viewers for a vehicle report dir, from on-disk raw artefacts; the `repaint-finetuned` CLI mode renders `*_finetuned` sets for report-finetuner. **Self-contained owner of all validation-figure + inspect-HTML rendering code** (EV + diesel painters, finetuned overlays, viewer template — moved out of `jolt_toolkit` in v3.1.0); segmentation stays in the package (read-only call via its `figure_hook`). |
| [`/param-tuner <REG>`](.claude/skills/param-tuner/README.md) | Stable | Review and optimise a vehicle's trip/charging segmentation parameters from its validation figures. |
| [`/report-finetuner <REG> <period>`](.claude/skills/report-finetuner/README.md) | Beta | Vision-driven post-processing of a generated xlsx's segmentation (merge / split / delete legs → `*_finetuned` artefacts). |
| [`/vehicle-onboarding <REG>`](.claude/skills/vehicle-onboarding/README.md) | Beta | Onboard a new vehicle: query SRF, configure `vehicles.json` / `pipelines.json` / `plot_config.json`, produce the first report. |
| [`/project-qa`](.claude/skills/project-qa/README.md) | Stable | Read-only Q&A about project state (vehicles, data coverage, configs, results, changelog) — never edits anything. |
| [`/html-artifacts`](.claude/skills/html-artifacts/SKILL.md) | Stable | Produce a self-contained HTML artefact deliverable (instead of Markdown) for content that needs layout / diagrams / interactivity. (Vendored third-party skill — keeps its `UPSTREAM_README.md` instead of a `PIPELINE.md`.) |

### Agents (`.claude/agents/`)

| Agent | Status | Owns / handles |
|-------|--------|----------------|
| [`jolt-toolkit-dev`](.claude/agents/jolt-toolkit-dev.md) | Stable | Sole owner of **`src/jolt_toolkit/` development only** — since v3.1.0 the package is the platform report-generation surface (generation orchestration + CLIs, segmentation incl. the general fallback pipeline for un-onboarded regs and the `figure_hook` seam, capacity model, Excel writing, weather/charger/logger patchers, config schema, shared `analysis/`). **Not** the industrial PDF briefing (the `generate-pdf-report` skill's own code — route here only for a *new xlsx field / data source*), and **not** the v3.1.0 re-homed capabilities: rendering → `report-visuals`, finetune → `report-finetuner`, dashboards → `generate-data-dashboard`, params identification → `research_projects/parameter_identify/`. |
| [`param-identifier`](.claude/agents/param-identifier.md) | Beta | C_rr / C_dA parameter identification from high-rate Logger data (code home: `research_projects/parameter_identify/code/`, moved out of `jolt_toolkit` in v3.1.0). |
| [`simulation`](.claude/agents/simulation.md) | Stable | Physics-based EP simulation experiments (`research_projects/simulation/`). |
| [`regen-analysis`](.claude/agents/regen-analysis.md) | Stable | Single-vehicle regenerative-braking energy-recovery analysis (`research_projects/regen_analysis/`). |
| [`report-finetuner`](.claude/agents/report-finetuner.md) | Beta | Post-processing segmentation corrections to generated xlsx reports (produces `*_finetuned` artefacts). |
| [`academic-writer`](.claude/agents/academic-writer.md) | Stable | Writes and maintains the academic paper workspace `publication_workspace/`. |
| [`literature-reviewer`](.claude/agents/literature-reviewer.md) | Stable | Searches / reads / curates the literature (now under the statistics paper's `reference/` + `draft/`). |
| [`project-health-steward`](.claude/agents/project-health-steward.md) | Beta | Periodic project health checks: tidy/archive temp + stale files, version-consistency, doc & skill/agent hygiene, and local-storage (`D:\JOLT_local`) management; accumulates experience in `.claude/health_checks/`. |
| [`project-architect`](.claude/agents/project-architect.md) | Draft | Architecture governance ("chief steward for structure"): allocates/re-homes ownership of code / skills / agents, plans and orchestrates structural refactors (package slimming, functionality moves, new-skill extraction), adjudicates technical designs; records ADR-style decisions in `.claude/architecture/`. Tidiness stays with `project-health-steward`; all `src/jolt_toolkit/` edits route to `jolt-toolkit-dev`. |
| [`pdf-report-auditor`](.claude/agents/pdf-report-auditor.md) | Beta | Independent data audit of every partner-facing PDF briefing in `pdf_report_workspace/output_by_*/` — re-derives page-1/page-2 numbers straight from raw telematics + xlsx (a path independent of `generate_pdf_report.py`), checks physical plausibility and energy reconciliation; read-only, accumulates experience in `.claude/audits/pdf_reports/`. |

## Project maintenance notes (for human developers)

- Use git for sound branch management, and use worktrees for parallel development.
- Keep the project structure tidy: achieve sustainable project management mainly by maintaining `CLAUDE.md` and each level's `README.md`.
- Turn SOPs into skills in moderation to improve development efficiency; make sure each skill's description and positioning are clear, so that AI agents do not confuse the usage of different skills.
