# vehicle-onboarding — bring a new registration into the JOLT report pipeline

> Brings a new registration into the report generator: SRF discovery → config →
> first report → param-tuning → case study. Since jolt_toolkit v3.1.0 generation
> never *requires* onboarding (see the boundary note below) — onboarding is about
> report quality and fleet registration, not about making generation possible.
> This README is the skill's human-facing single source of truth; `SKILL.md` is the
> agent-facing router over `manifest.yaml`.

**Invoke:** `/vehicle-onboarding <REG>` · **In:** SRF API (metadata + sample raw legs) ·
**Out:** updated `vehicles.json` / `pipelines.json` / `plot_config.json` / `test_data_config.json`
+ report(s) with inspect HTML + **weather-backfilled** + **refreshed data dashboard** +
**registered in data-collection-monitor's `watched_vehicles.json`** + `references/{reg}.md`

## Directory map

```
vehicle-onboarding/
├── SKILL.md                     # router: routing protocol only (agent entry point)
├── manifest.yaml                # always_load + vehicle-type axis + gates + on-demand reference table
├── README.md                    # this file — human-facing map + pipeline
├── static/
│   ├── core/                    # workflow.md (the 6 phases) + interaction-contract.md
│   │                            #   (mode, decision points, guidelines) — always loaded
│   └── fragments/vehicle-type/  # ev.md | diesel.md (exactly one loaded per run)
└── references/                  # srf-discovery.md (Phase 1 API code + column checklist),
                                 # case-study-template.md, and per-vehicle case studies
                                 # (T88RNW.md, TA70WTL.md, YT21EFD.md, … one per onboarded vehicle)
```

## Pipeline

0. **Mode** — Guided (confirm at each decision, default) or Auto (best-guess, review after).
1. **Phase 1 — Discovery (SRF):** query vehicle metadata (make/model/VIN, `fuel_capacity` →
   default `nominal_kwh`); read the organisation name via REST and map it to a company
   constant; find the available data date range; download 3–5 sample legs and inspect raw
   telematics columns (speed, SoC, odometer, mass, energy, altitude, lat/lon).
2. **Phase 2 — Configuration:** **EV** → choose the segmentation branch (speed-based,
   recommended, vs SOC-based) + add a pipeline entry (`{make}_{branch}_{seq}`). **DIESEL**
   (SRF `fuel`=DIESEL) → no branch question: reuse the `daf_diesel_logger` pipeline with
   `leg_source: SRFLOGGER_V1` + the J1939 channel mappings (template = WU70GLV; channel names
   are OEM-independent). Assign company + colour; write all four config files.
3. **Phase 3 — Initial report:** thin call into `/generate-excel-report` (`--debug` →
   `.xlsx` + **inspect HTML** + validation figures in one step). EV/diesel use the same CLI
   (pipeline picked from `vehicles.json`).
4. **Phase 4 — Tuning:** invoke `/param-tuner` (quick mode) to verify segmentation and adjust
   parameters if needed.
5. **Phase 5 — Downstream artefacts (orchestration):** by *invoking* the owning skills, not
   duplicating them — (a) weather backfill (driving legs; diesel may be pre-filled from Logger
   channel 7), (b) `/generate-data-dashboard <version>`, (c) register `{REG}` in
   data-collection-monitor's `watched_vehicles.json`.
6. **Phase 6 — Finalise:** save the `references/{reg}.md` onboarding case study (+ param-tuner
   case study), update the changelog, commit (config-only onboarding reusing a pipeline → no
   version bump).

**Rules:** every user-facing question is presented as numbered selectable options (+ "Something
else"); always verify SRF results before proceeding; never assume column names; ensure the
config is `--fast`-compatible; one vehicle at a time.

## How to run

Invoke `/vehicle-onboarding <REG>` (or "onboard <REG>" / "add vehicle <REG>") — the router
`SKILL.md` loads `manifest.yaml`, always-loads the two core files, resolves the interaction
mode and the vehicle-type axis (from SRF `fuel`), and walks the six phases. The Phase 3
initial report is a thin call into `/generate-excel-report`:

```bash
pip install -e . -q
python .claude/skills/generate-excel-report/generate_report.py -veh {REG} -ds {start} -de {end} --debug
# long / full range → batch_generate.py --veh {REG} --ds {start} --de {end} --debug (auto-splits into meteorological quarters)
```

Needs `SRF_API_KEY` (Phase 1) and `OPENWEATHER_API_KEYS` (Phase 5 weather patch) in `.env`.

## Boundary with the general fallback pipeline (jolt_toolkit v3.1.0)

Since v3.1.0 the package generates a report for **any** registration — an un-onboarded
reg (EV or diesel) goes through the **general fallback pipeline** (runtime config from
SRF metadata + column auto-detection; never written to `vehicles.json`), so generation
never blocks on "onboard first". What onboarding adds — and why it still matters:

- **Tuned segmentation parameters** (a dedicated pipeline entry + param-tuner pass)
  instead of the generic `default_soc`/`default_speed` defaults;
- **Validation review** (validation figures + inspect HTML inspected by a human/agent
  before the vehicle's numbers are trusted);
- **Fleet registration**: the dashboard, data-collection-monitor watching, and the
  capacity ledger (`effective_capacity_*` write-back) all require a real
  `vehicles.json` entry — the fallback deliberately persists nothing.

Rule of thumb: a one-off exploratory report for an unknown reg → just run
`/generate-excel-report` (the fallback handles it); a vehicle joining the fleet → this
skill, as before.

## Ownership and neighbours

- **This skill owns** the onboarding workflow and its per-vehicle case studies. It **writes**
  the four config entries (`vehicles.json`, `pipelines.json`, `plot_config.json`,
  `.claude/skills/generate-excel-report/test_data_config.json`) as part of onboarding.
- **Orchestrate, don't duplicate:** Phases 3–5 only *invoke* the owning skills —
  `/generate-excel-report` (CLI flags, quarter-split, `--debug` = inspect HTML + validation
  figures, weather patch step), `/param-tuner`, `/generate-data-dashboard`,
  `/data-collection-monitor` (registration via its `watched_vehicles.json`). If a downstream
  artefact needs a behaviour change, change it in that skill (or route to `jolt-toolkit-dev`),
  not here.
- **Experience accumulation:** this skill has no `evaluations/` directory — per-vehicle
  onboarding experience accumulates in `references/<REG>.md` case studies instead
  (template: `references/case-study-template.md`); check them (and param-tuner's
  `references/`) before onboarding a similar vehicle.
