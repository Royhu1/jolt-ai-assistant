# Discipline and ownership (always load)

- **This skill is the self-contained, sole owner of industrial PDF-briefing development**:
  layout, chart specs, commentary style, KPI/statistics computation basis, and the generator
  code `generate_pdf_report.py` / `build_pdf.py` / `templates/` / `briefing_vehicle_specs.json`
  (per-vehicle unladen-band / mass overrides) / style baseline `references/`
  are all maintained by this skill, with all knowledge recorded in this skill's files (the
  `SKILL.md` router, the `static/core/` contracts, the `static/fragments/` quick-starts and
  the `references/` deep material). **All
  briefing chart/layout/commentary/naming/statistics changes are made within this skill, not
  routed to the `jolt-toolkit-dev` agent.**
- Data-source boundary: only **read** `excel_report_database/<version>/<REG>/` (xlsx + the
  `raw_telematics/` in the same directory), and may make read-only calls to the **versioned**
  `jolt_toolkit.analysis` API (e.g. counter interpolation `build_interp`/`delta`, permitted by
  the sub-project independence convention). **Only when the briefing needs a new field / new
  data source not in the xlsx** do you raise a request to `jolt-toolkit-dev` (the sole owner
  of `src/jolt_toolkit/`); otherwise **do not change** any code/config in `src/jolt_toolkit/`.
- Do not bump the version number; artefacts are not committed to git (the skill itself is
  shared via git).
- Append a Q&A record to `changelogs/changelog_<Monday>_<Sunday>.md` at the end of the
  conversation.
