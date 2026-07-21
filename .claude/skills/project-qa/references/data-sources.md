# Data sources

All sources are **read-only**. Never write to or modify any of these files.

| Source | Path | Contains |
|--------|------|----------|
| Vehicle registry | `src/jolt_toolkit/configs/vehicles.json` | Vehicle make/model, pipeline, capacity, mass params |
| Pipeline configs | `src/jolt_toolkit/configs/pipelines.json` | Segmentation algorithm parameters per pipeline |
| Plot / operator config | `src/jolt_toolkit/configs/plot_config.json` | Operator → vehicle assignment, vehicle specs |
| Test date ranges | `.claude/skills/generate-excel-report/test_data_config.json` | Standard date ranges used for batch report generation |
| Reports directory | `excel_report_database/<version>/` | Generated Excel reports per vehicle |
| Data-availability dashboard | `excel_report_database/<version>/dashboard/data_dashboard.html` | ACTUAL per-vehicle data coverage (which days have telematics / logger / charger data). Use this for coverage questions — `test_data_config.json` is a configured snapshot, not live coverage |
| Simulation results | `research_projects/simulation/results/EP_simulation_report.md` | Physics simulation findings |
| Simulation tables | `research_projects/simulation/results/tables/*.csv` | Numerical experiment data |
| Changelog | `changelogs/changelog_*.md` | Weekly Q&A logs of completed tasks |
| Toolkit version | `src/jolt_toolkit/__init__.py` (`__version__`) | Current version number (history in `src/jolt_toolkit/versions.md`) |
| Architecture docs | `src/jolt_toolkit/README.md` | Module structure |
