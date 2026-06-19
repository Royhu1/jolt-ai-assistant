# vehicle-onboarding — Pipeline

> Brings a new registration into the report generator: SRF discovery → config →
> first report → param-tuning → case study. Runs before `/generate-excel-report` can.

**Invoke:** `/vehicle-onboarding <REG>` · **In:** SRF API (metadata + sample raw legs) ·
**Out:** updated `vehicles.json` / `pipelines.json` / `plot_config.json` / `test_data_config.json`
+ report(s) with inspect HTML + **weather-backfilled** + **refreshed data dashboard** +
**registered in data-collection-monitor's `watched_vehicles.json`** + `references/{reg}.md`

## Flow

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
