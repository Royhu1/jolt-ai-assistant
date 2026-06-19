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
├── pdf_report_workspace     # generated partner-briefing artefacts (output/ + HERE-tile cache/); produced by the generate-pdf-report skill
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
> (`generate_report.py` / `batch_generate.py` / `test_data_config.json`) now live inside the
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

### Commands (`.claude/commands/`)

| Command | What it does |
|---------|--------------|
| `/translate-doc <file>` | Regenerate the other side of a bilingual doc pair (`<name>.md` ↔ `<name>.zh.md`) from the side you just edited. |
| `/check-doc-sync <file\|all>` | Check whether bilingual doc pairs are content-consistent; list out-of-sync pairs and what differs (read-only). `all` = check every pair. |

### Skills (`.claude/skills/`)

> Each JOLT skill folder also contains a concise `PIPELINE.md` — a quick, human-readable
> walk-through of what happens when you invoke that skill (data in → processing → artefacts
> out, plus ownership and how it connects to neighbouring skills). Read it to grasp a skill's
> working principle without opening its full `SKILL.md`.

| Skill | What it does |
|-------|--------------|
| `/generate-excel-report <REG> <period>` | Generate a formatted Excel report for a vehicle + date range (drives the report CLI → `excel_report_database/`). |
| `/generate-pdf-report <REG> <period>` | Generate the industrial-partner one-page PDF/HTML briefing from xlsx pipeline artefacts (→ `pdf_report_workspace/output/`). **Self-contained owner of all PDF-briefing development** — its own generator code (`generate_pdf_report.py` / `build_pdf.py` / `templates/`), layout, chart specs, commentary style guide and KPI computation all live in the skill; reads `excel_report_database/*.xlsx` (and may read-only call `jolt_toolkit.analysis`), routing to `jolt-toolkit-dev` *only* for new xlsx fields. |
| `/generate-data-dashboard <version>` | Generate/refresh the offline data-availability dashboard (`data_dashboard.html`) for a report-database version (drives the `jolt_toolkit` dashboard CLI). |
| `/data-collection-monitor [--cadence weekly]` | Periodic (designed for `/loop`, default weekly) fleet data-intake check: append-only extends `excel_report_database/<version>/` with newly-collected SRF data (never overwrites), refreshes the dashboard, and emits a fixed-template PDF "data collection digest" (+ `MONITOR_STATUS.md`) → `data_collection_reports/`. |
| `/plot-figure` | Generate energy-performance figures (EP-vs-mass scatter+fit, range, per-OEM…) from xlsx reports into a `--out-dir` you specify. |
| `/param-tuner <REG>` | Review and optimise a vehicle's trip/charging segmentation parameters from its validation figures. |
| `/report-finetuner <REG> <period>` | Vision-driven post-processing of a generated xlsx's segmentation (merge / split / delete legs → `*_finetuned` artefacts). |
| `/vehicle-onboarding <REG>` | Onboard a new vehicle: query SRF, configure `vehicles.json` / `pipelines.json` / `plot_config.json`, produce the first report. |
| `/project-qa` | Read-only Q&A about project state (vehicles, data coverage, configs, results, changelog) — never edits anything. |
| `/html-artifacts` | Produce a self-contained HTML artefact deliverable (instead of Markdown) for content that needs layout / diagrams / interactivity. |

### Agents (`.claude/agents/`)

| Agent | Owns / handles |
|-------|----------------|
| `jolt-toolkit-dev` | Sole owner of **`src/jolt_toolkit/` development only** — the core package (Excel report generation, segmentation algorithms, vehicle/pipeline configs, Excel formatting, weather/charger/logger patchers, validation figures, report CLIs). **Not** the industrial PDF briefing: that is the `generate-pdf-report` skill's own self-contained code (`generate_pdf_report.py` etc.); only route a request here when the briefing needs a *new xlsx field / data source*. |
| `param-identifier` | C_rr / C_dA parameter identification from high-rate Logger data. |
| `simulation` | Physics-based EP simulation experiments (`research_projects/simulation/`). |
| `regen-analysis` | Single-vehicle regenerative-braking energy-recovery analysis (`research_projects/regen_analysis/`). |
| `report-finetuner` | Post-processing segmentation corrections to generated xlsx reports (produces `*_finetuned` artefacts). |
| `academic-writer` | Writes and maintains the academic paper workspace `publication_workspace/`. |
| `literature-reviewer` | Searches / reads / curates the literature (now under the statistics paper's `reference/` + `draft/`). |

## Project maintenance notes (for human developers)

- Use git for sound branch management, and use worktrees for parallel development.
- Keep the project structure tidy: achieve sustainable project management mainly by maintaining `CLAUDE.md` and each level's `README.md`.
- Turn SOPs into skills in moderation to improve development efficiency; make sure each skill's description and positioning are clear, so that AI agents do not confuse the usage of different skills.
