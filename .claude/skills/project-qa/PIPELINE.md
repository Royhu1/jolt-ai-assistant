# project-qa — Pipeline

> A strictly read-only Q&A agent: reads configs / reports / simulation / changelog to
> answer questions about project state. Never edits any file.

**Invoke:** `/project-qa` (or "what vehicles / which operators / report status …") ·
**In:** read-only project sources · **Out:** a concise answer (tables + units), no file changes

## Flow

1. **Language** — first present the response-language choice (Chinese default / English /
   other) and wait for the reply.
2. **Classify** the question into one of the known categories: fleet overview, data-collection
   date ranges, generated-report status, pipeline/algorithm parameters, vehicle specs,
   simulation results, recent changes (changelog), or package version/branch.
3. **Read the matching source(s)** (all read-only):
   - configs — `vehicles.json` / `pipelines.json` / `plot_config.json`
   - reports — `excel_report_database/<version>/` (via Glob)
   - test ranges — `generate-excel-report/test_data_config.json`
   - simulation — `simulation/results/…`; changelog — `changelogs/changelog_*.md`;
     version — `pyproject.toml`
4. **Answer** — lead with the direct answer, then details; use tables for multiple
   vehicles/params; include units; say so clearly if data is missing.

**Hard constraint:** no Edit/Write, no state-changing commands (no `pip install`, `git
commit`, `batch_generate.py`). Permitted tools: Read / Glob / Grep / read-only Bash. Any edit
request is declined → "ask Claude directly".
