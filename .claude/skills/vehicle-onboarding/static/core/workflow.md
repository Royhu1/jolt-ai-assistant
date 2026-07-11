# Workflow — the six onboarding phases (always load)

Onboard a new vehicle into the JOLT report pipeline: from SRF API discovery to validated
segmentation parameters. Work through the phases in order; every user-facing question
follows `interaction-contract.md` (numbered selectable options, "Something else" last).

### Phase 1 — Discovery

Open [../../references/srf-discovery.md](../../references/srf-discovery.md) for the SRF
API code snippets and the raw-telematics column checklist, and work through its steps:

- **1.1 Query SRF API for vehicle metadata** (make/model/VIN, `fuel_capacity`), plus
  **1.1b** read the organisation name via REST, **1.1c** auto-map organisation → company
  constant, and **1.1d** take `v.fuel_capacity` as the default `nominal_kwh`.
  Present findings to user for verification (cross-check make/model with user's
  expectation).
- **1.2 Find available data date range** (first and last leg).
- **1.3 Inspect raw telematics data columns** (download 3-5 legs from different dates).
  Present a data availability summary table to the user.

Phase 1 also resolves the `vehicle-type` axis: SRF `fuel` = DIESEL → `diesel`,
otherwise `ev` (see `manifest.yaml`).

### Phase 2 — Configuration

#### 2.1 Algorithm branch selection

Load exactly one vehicle-type fragment per the manifest's `vehicle-type` axis:

- **DIESEL** (SRF `fuel` = DIESEL) →
  [../fragments/vehicle-type/diesel.md](../fragments/vehicle-type/diesel.md) — no
  speed/SOC branch question; SRF-Logger J1939 channel mappings, reuse
  `daf_diesel_logger`, then jump to §2.4.
- **EV** → [../fragments/vehicle-type/ev.md](../fragments/vehicle-type/ev.md) — present
  the speed-based vs SOC-based segmentation branch question, then continue with §2.2.

#### 2.2 Pipeline configuration

Based on branch selection, create a new pipeline entry in `pipelines.json`.
Use naming convention: `{make_lower}_{branch}_{sequence}` (e.g., `renault_speed_01`).

Start with default parameters — param-tuner will optimize later.

#### 2.3 Company assignment and color

If the organisation was auto-mapped in Phase 1.1c:
- Check if the company already exists in `plot_config.json` → reuse existing color
- If new company → suggest an unused color

If the organisation could NOT be auto-mapped (e.g., "JOLT Partners" which hosts multiple operators):
- Present the user with existing company options + "Something else"

```
Company auto-detected from SRF: {org_name} → {company}
Color: {existing_color} (reusing existing company color)
```

#### 2.4 Write vehicle config

Add entry to `vehicles.json` with discovered column mappings.
Add pipeline entry to `pipelines.json`.
Update `plot_config.json` with company/color assignment.
Add entry to `.claude/skills/generate-excel-report/test_data_config.json`.

### Phase 3 — Initial report generation

This is just a thin call into the **`/generate-excel-report`** skill — do not re-derive
its CLI flags or date-range conventions here; follow that skill (it owns the quarter-split
and `--debug` behaviour). `--debug` already writes the **`inspect_*.html`** viewer + the
validation figures alongside the `.xlsx`, so **there is no separate "produce inspect.html"
step** — it is part of report generation.

```bash
pip install -e . -q
python .claude/skills/generate-excel-report/generate_report.py -veh {REG} -ds {start} -de {end} --debug
# long / full range → batch_generate.py --veh {REG} --ds {start} --de {end} --debug (auto-splits into meteorological quarters)
```

For the **first validation** pass choose a 1-month range with good coverage; for a full
onboarding, generate the whole available range (quarter-split per `/generate-excel-report`).
Diesel and EV vehicles use the **same** CLI (the pipeline is selected from `vehicles.json`).

### Phase 4 — Parameter tuning

Invoke param-tuner skill (quick mode) on the generated report to verify
segmentation quality and adjust parameters if needed.

### Phase 5 — Downstream artefacts (orchestration)

Onboarding is **not** finished at "first report" — bring the new vehicle into the same
artefacts the rest of the fleet has, by **invoking the owning skills** (never re-implement
their logic here):

1. **Weather backfill (driving legs)** — a freshly generated report has empty weather
   columns. Run the weather patch exactly as `/generate-excel-report` documents under
   "After generating":
   ```bash
   python -m jolt_toolkit.report_generator.weather_patch ./excel_report_database/<ver>/{REG}/
   ```
   (needs `OPENWEATHER_API_KEYS`; cache-first, **driving-legs-only**.) **DIESEL note:** the
   SRF Logger carries an on-board weather station (channel 7), so a diesel report may already
   be weather-filled from the Logger — check `Average Temperature (C)` coverage on driving
   legs first and only patch the gaps.
2. **Data-availability dashboard** — invoke **`/generate-data-dashboard <version>`** so the
   new vehicle's directory is picked up and appears in `data_dashboard.html`.
3. **Data-collection-monitor registration** — add `{REG}` to
   `.claude/skills/data-collection-monitor/watched_vehicles.json` so the periodic intake
   check covers it from now on. (Optionally run `/data-collection-monitor --veh {REG}` once
   to seed its digest; the essential step is registering the vehicle.)

> **Division of labour — orchestrate, don't duplicate.** This phase only *calls*
> `/generate-excel-report`'s weather step, `/generate-data-dashboard`, and
> `/data-collection-monitor`; it never copies their code, templates, or conventions. If a
> downstream artefact needs a behaviour change, change it in that skill (or route to
> `jolt-toolkit-dev`), not here. inspect HTML is already produced in Phase 3 (`--debug`).

### Phase 6 — Finalize

1. Save case study to `references/{reg}.md` in this skill's directory
   (template: [../../references/case-study-template.md](../../references/case-study-template.md))
2. Save param-tuner case study if tuning was done
3. Update the weekly `changelogs/changelog_<Mon>_<Sun>.md`
4. Commit changes (config + skill); do not bump the package version for a config-only
   onboarding that reuses an existing pipeline
