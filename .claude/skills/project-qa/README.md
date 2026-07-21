# project-qa — read-only project Q&A

> A strictly read-only Q&A agent: reads configs / reports / simulation / changelog to
> answer questions about project state. Never edits any file.
> This README is the skill's human-facing single source of truth; `SKILL.md` is the
> agent-facing router over `manifest.yaml`.

**Invoke:** `/project-qa` (or "what vehicles / which operators / report status …") ·
**In:** read-only project sources · **Out:** a concise answer (tables + units), no file changes

## Directory map

```
project-qa/
├── SKILL.md          # router: routing protocol only (agent entry point)
├── manifest.yaml     # always_load + blocking language gate + on-demand reference table (no axes)
├── README.md         # this file — human-facing map + pipeline
├── static/
│   └── core/         # read-only-contract.md (always loaded: strict read-only
│                     #   constraint + mandatory Step-0 language preference
│                     #   + presentation guidelines)
└── references/       # data-sources.md (read-only map of where every fact lives)
                      # + question-categories.md (the 8 per-category answer recipes)
```

No `static/fragments/`: a read-only Q&A flow has no genuine mode branch, so the skill
omits `axes` per the proportionality rule in `.claude/rules/skill-design.md`. No
`evaluations/` either: this skill is stateless by design — strictly read-only Q&A that
produces no artefacts and therefore accumulates no per-run state.

## Pipeline

1. **Route** — `SKILL.md` loads `manifest.yaml`: always-load the core contract
   (`static/core/read-only-contract.md` — strict read-only constraint + Step-0
   language preference + presentation guidelines).
2. **Language (blocking gate)** — first present the response-language choice (Chinese
   default / English / other) and wait for the reply.
3. **Classify** the question into one of the known categories: fleet overview,
   data-collection date ranges, generated-report status, pipeline/algorithm parameters,
   vehicle specs, simulation results, recent changes (changelog), or package
   version/branch — then open `references/question-categories.md` for that category's
   answer recipe.
4. **Read the matching source(s)** (all read-only; full map in
   `references/data-sources.md`):
   - configs — `vehicles.json` / `pipelines.json` / `plot_config.json`
   - reports — `excel_report_database/<version>/` (via Glob)
   - test ranges — `generate-excel-report/test_data_config.json`
   - simulation — `research_projects/simulation/results/…`; changelog —
     `changelogs/changelog_*.md`; version — `src/jolt_toolkit/__init__.py` (`__version__`)
5. **Answer** — lead with the direct answer, then details; use tables for multiple
   vehicles/params; include units; say so clearly if data is missing.

**Hard constraint:** no Edit/Write, no state-changing commands (no `pip install`, `git
commit`, `batch_generate.py`). Permitted tools: Read / Glob / Grep / read-only Bash. Any
edit request is declined → "ask Claude directly".

## Ownership and neighbours

- This skill owns nothing writable: it never modifies configs, reports or code. Change
  requests are declined and routed to Claude directly — i.e. to the owning skill/agent
  (anything under `src/jolt_toolkit/` → `jolt-toolkit-dev`; report generation →
  `/generate-excel-report`; dashboards → `/generate-data-dashboard`).
- Everything it reads is owned elsewhere and consumed read-only — see
  `references/data-sources.md` for the full source map.
- Periodic inspection/cleanup and version-consistency ENFORCEMENT belong to the
  `project-health-steward` agent; this skill only answers questions (read-only).
