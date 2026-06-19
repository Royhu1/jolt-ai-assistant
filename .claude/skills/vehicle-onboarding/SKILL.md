---
name: vehicle-onboarding
description: |
  Onboard a new vehicle into the JOLT report generator. Use when the user
  provides a new vehicle registration that is not yet in vehicles.json.
  Triggers on:
  (1) "add vehicle <reg>", "onboard <reg>", "configure <reg>"
  (2) "new vehicle <reg>"
  (3) "/vehicle-onboarding <reg>"
  Queries SRF API for vehicle metadata, inspects raw telematics data columns,
  configures vehicles.json/pipelines.json/plot_config.json, generates an initial
  report (with inspect HTML), runs param-tuner to optimise segmentation, and then
  ORCHESTRATES the downstream artefacts — weather backfill, the data-availability
  dashboard, and data-collection-monitor registration — by INVOKING the existing
  skills rather than re-implementing them. Handles both EV and DIESEL vehicles.
---

# Vehicle Onboarding

Onboard a new vehicle into the JOLT report pipeline: from SRF API discovery
to validated segmentation parameters.

## Mode selection

At the start, present the user with two options:

1. **Guided mode** — step-by-step with user confirmation at each decision point
2. **Auto mode** — make best-guess decisions automatically, present results for review

Default: Guided mode.

---

## Workflow

### Phase 1 — Discovery

#### 1.1 Query SRF API for vehicle metadata

```python
import srf_client, requests, os, json
from dotenv import load_dotenv; load_dotenv()

srf = srf_client.SRFData(api_key=os.environ['SRF_API_KEY'],
                         root='https://data.csrf.ac.uk/api/')

# Search by registration (with space, e.g. "TA70 WTL")
vehicles = srf.vehicles.find_all(**{'registration': reg_with_space})
for v in srf_client.paging.paged_items(vehicles):
    print(v.registration, v.make, v.model, v.uri)
    # Key attributes available on Vehicle object:
    #   v.registration, v.make, v.model, v.vin, v.uri
    #   v.fuel_capacity  — nominal battery capacity (kWh), use as default nominal_kwh
    #   v.fuel, v.type, v.weight_class, v.country, v.description
    # NOTE: v.fleet does NOT exist — will raise AttributeError
```

#### 1.1b Read organisation name (for company assignment)

`organisation` is NOT exposed on the Python `Vehicle` object. Use the REST API directly:

```python
headers = {'Authorization': f'Bearer {os.environ["SRF_API_KEY"]}'}
# v.uri gives the vehicle URL, e.g. "https://data.csrf.ac.uk/api/vehicles/177"
resp = requests.get(v.uri, headers=headers)
veh_json = resp.json()
org_url = veh_json.get('organisation', {}).get('_location', '')
if org_url:
    org_resp = requests.get(org_url, headers=headers)
    org_name = org_resp.json().get('name', '')
    # org_name examples: "JOLT Knowles-Volvo", "JOLT Nestle-Volvo", "JOLT Welch-Volvo",
    #                    "JOLT JLP-Volvo", "JOLT Partners", "Welch Group"
```

#### 1.1c Auto-map organisation → company constant

Use the mapping below to convert SRF organisation names to plot_config company constants.
If no match found, present options to the user.

```python
ORG_TO_COMPANY = {
    'JOLT Knowles-Volvo': 'KNOWLES',
    'JOLT Nestle-Volvo': 'NESTLE',
    'JOLT Welch-Volvo': 'WELCH_TRANSPORT',
    'Welch Group': 'WELCH_TRANSPORT',
    'JOLT JLP-Volvo': 'JLP',
    'John Lewis Partnership': 'JLP',
    'JOLT Partners': None,  # Multi-operator — needs manual assignment
}
company = ORG_TO_COMPANY.get(org_name)
```

#### 1.1d Nominal capacity from SRF

`v.fuel_capacity` returns the SRF-registered battery capacity in kWh.
Use this as the default `nominal_kwh` value. Present to user for confirmation only when
it differs significantly from known datasheet values.

> **Note**: SRF `fuelCapacity` may differ from datasheet nominal capacity for some vehicles
> (e.g., SRF shows usable capacity while datasheet shows gross capacity). Cross-reference
> against known vehicles: AV24LXJ SRF=265 vs config=360, N88GNW SRF=417 vs config=540.
> When discrepancy exists, prefer the value the user provides or the existing convention.

Present findings to user for verification (cross-check make/model with user's expectation).

#### 1.2 Find available data date range

```python
import datetime, srf_client
params = {
    'start_time': srf_client.filter.between(
        datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
        datetime.datetime.now(datetime.timezone.utc)),
    'sort': srf_client.sort.asc('startTime'),
}
legs = srf.legs.find_all(**params, **{'trip.vehicle.registration': reg_with_space})
# Get first and last leg to determine data range
```

#### 1.3 Inspect raw telematics data columns

Download 3-5 legs from different dates and inspect:

```python
import io, pandas as pd
for leg in sample_legs:
    raw = list(leg.get_raw_data())
    csv_text = "\n".join(c for c in raw if c.strip())
    df = pd.read_csv(io.StringIO(csv_text), dtype=str)
    print(f"Leg {leg.start_time.date()}: {len(df)} rows, cols: {list(df.columns)}")
```

**Key columns to identify:**

| Purpose | Common names | Check |
|---------|-------------|-------|
| Speed | `wheel_based_speed`, `speed` | Non-null count, range |
| SOC | `electricBatteryLevelPercent`, `state_of_charge` | Precision (integer vs float) |
| Odometer | `odometer`, `high_resolution_total_vehicle_distance` | Non-null |
| Mass | `gross_combination_vehicle_weight` | Non-null, range |
| Total energy | `total_electric_energy_used_plugged_in_included`, `total_electric_energy_used` | Availability |
| Moving energy | `electric_energy_wheelbased_speed_over_zero` | Availability |
| AC energy | `battery_pack_ac_watthours` | Availability |
| DC energy | `battery_pack_dc_watthours` | Availability |
| Altitude | `gnss_altitude` | Availability |
| Latitude/Longitude | `latitude`, `longitude` | Availability |

Present a data availability summary table to the user.

### Phase 2 — Configuration

#### 2.1 Algorithm branch selection

> **DIESEL vehicles (SRF `fuel` = DIESEL) skip the EV speed/SOC branch entirely.**
> They have **no battery/SOC**; their data is **SRF Logger** (`leg.trip.source` starts
> with `SRFLOGGER`, channel set via `leg_source: SRFLOGGER_V1`), not FPS telematics
> (a diesel's FPS leg is usually IMU-only — speed/fuel live in the Logger J1939
> channels). Configure them like the existing diesel vehicle **WU70GLV** (template):
> `fuel_type: DIESEL`, `pipeline: daf_diesel_logger` (a routing label — the channel
> names live in `vehicles.json`, so the same pipeline serves any OEM whose Logger
> exposes the standard J1939 channels), `leg_source: SRFLOGGER_V1`, plus the channel
> mappings `speed_col`=`CCVS wheel based vehicle speed`, `fuel_energy_col`=`LFC engine
> total fuel used`, `fuel_rate_col`=`LFE fuel rate`, `distance_col`=`VDHR hr total
> vehicle distance`, `mass_col`=`CVW gross combination vehicle weight`,
> `altitude_col`=`2 altitude`, `ambient_temp_col`=`AMB ambient air temperature`,
> `speed_col_fallback`=`2 speed`, and `diesel_lhv_kwh_per_l: 10.0`. **Discover a new
> diesel's channels** by listing `leg.types` and `leg.get_data_frame(<channel>)`
> columns on a `SRFLOGGER` leg (channels CCVS/LFC/LFE/VDHR/CVW/AMB/2/7); these J1939
> names are OEM-independent, so a new diesel usually reuses `daf_diesel_logger`
> verbatim. See `references/YT21EFD.md` (Scania) + `references/WU70GLV` for worked
> examples. Then jump to §2.4 (no speed/SOC branch question for diesel).

For **EV** vehicles, present options to user (in English):

```
Which segmentation approach should be used for discharge trip detection?

1. **Speed-based** (recommended if speed column available) — Detects trips by
   vehicle speed. More accurate trip boundaries, compatible with --fast mode.
   Best for vehicles with reliable speed data at ≥1 reading/5min.

2. **SOC-based** — Detects trips by SOC decrease patterns. Works without speed
   data but sensitive to SOC precision. Best for vehicles with high-precision
   SOC (≥0.1%) or no speed data.

3. Something else — Describe your preferred approach.

Recommended: [1 or 2 based on data inspection]
```

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
2. Save param-tuner case study if tuning was done
3. Update the weekly `changelogs/changelog_<Mon>_<Sun>.md`
4. Commit changes (config + skill); do not bump the package version for a config-only
   onboarding that reuses an existing pipeline

---

## Decision points requiring user input

All decision points present numbered options in English with brief explanations.
The last option is always "Something else" for free-form input.

| Decision | When | Options |
|----------|------|---------|
| Branch selection | After data inspection | speed / soc / something else |
| Color | After pipeline config | suggest unused color / user picks |
| min_cluster_gap_kg | After mass data inspection | 1000 / 2000 / 3000 / something else |
| Date range | Before report generation | suggest range based on data / user picks |
| Pipeline params | If default doesn't work | adjust specific params / something else |

---

## Post-onboarding case study

After successful onboarding, save `references/{reg}.md` with:

1. Vehicle specs (make, model, capacity, data characteristics)
2. Telematics column mapping (which standard columns exist, any non-standard names)
3. Algorithm choices made and why
4. Initial parameter values and any tuning done
5. Data quirks discovered (SOC precision, missing channels, etc.)

These case studies help future onboarding of similar vehicles.

---

## Guidelines

- **ALL questions to the user MUST be formatted as numbered selectable options** with brief
  explanations for each option. The last option is always "Something else" for free-form input.
  Give a recommended option where applicable. Never use open-ended questions — always provide
  concrete choices. This applies to every decision point, including capacity, color, date range,
  parameters, and any other user-facing question.
- Always verify SRF API results with user before proceeding
- Never assume column names — always inspect raw data first
- Use existing pipeline parameters as starting point, not from scratch
- Check param-tuner `references/` for similar vehicles before tuning
- Ensure all configurations are --fast mode compatible (no Logger dependency for segmentation)
- One vehicle at a time; complete onboarding before starting the next
