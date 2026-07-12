# Mode: generate — produce a briefing for `<REG>` + `<period>` (DEFAULT)

Use for producing a new briefing (named and/or anonymised, raw and/or segment page-1 basis)
for a vehicle + period, including `--all-data` full-range runs and the automatic
per-operator split. The layout contract and discipline contract (`static/core/`) apply
throughout; consult `references/` per the manifest table — in particular
`references/commentary-style.md` governs every Conclusions / Summary sentence and
the load-point band judgement, and `references/verification.md` is **mandatory
after every generation**.

## 1. Inputs and data sources

- Arguments: `<REG>` (registration) + `<period>` (`yyyymmdd_yyyymmdd`); optional `--version`
  (default = installed jolt_toolkit version; 2.2.8 at the time of writing) and `--base` (use
  the non-finetuned base xlsx).
- **`--all-data`**: read & concatenate **every** period report for the vehicle (all collected data,
  deduped by Start Time + Leg Type) instead of one period; the operating period and output naming
  then span the full data range, and `--period` is ignored for xlsx selection. Combine with `--anon`
  as usual. Example: `--reg CMZ6260 --all-data` covers 2025-09 → 2026-04 across three quarterly reports.
- **Round-robin vehicles + `--all-data` → one briefing PER OPERATOR (auto, DATA-DRIVEN)**: the operator
  comes from the report's per-leg **`Operator`** column (the generator derives it from SRF
  `leg.trip.trial.description` / `vehicle.organisation.name`), **NOT** the manual plot_config. With
  `--all-data`, if the data shows **>1 distinct operator** (each with **≥20 valid trips**) the generator
  emits **one briefing per operator** — trips filtered by `Operator == op`, charges by that operator's
  trip date span, labelled with that operator — instead of one merged briefing. Output is
  `output_by_TBD/<REG>_<OPERATOR>_<op_period>/` (e.g. `CMZ6260_JLP_…` / `CMZ6260_SJG_…` / `CMZ6260_HTL_…`).
  A single distinct operator → one briefing; non-`--all-data` runs → one briefing. An operator with
  **< 20 valid trips** is **skipped** (too sparse, logged) — the threshold is `--min-operator-trips N`
  (default 20); lower it to FORCE a briefing for a sparse operator (e.g. `--min-operator-trips 10` for
  EX74JXW/WELCH_TRANSPORT ~11 trips), but note its load-points / temperature trend are then unreliable
  (the temperature analysis self-caveats to "inconclusive" when its laden window has < 15 points). The **mass-vs-distribution variant is decided
  at the vehicle level** (over all the vehicle's data, before the split) so a vehicle's per-operator
  briefings are all the same variant (a sparse operator subset can't flip to a mass briefing on its own).
- **Two report variants, auto-selected by data**: vehicles that report gross vehicle mass get the
  standard mass-based briefing; vehicles with **no usable mass channel** (mass present on < 5 % of
  trips — e.g. YN75NMA, T88RNW) automatically get the **distribution variant** (see
  `static/core/layout-contract.md` / `references/commentary-style.md`) — no flag
  needed.
- Data comes **only** from `excel_report_database/<version>/<REG>/jolt_report_*.xlsx`
  (prefer `_finetuned`). If there is **no exact-period** file, the generator automatically
  picks the most compact report whose `[start,end]` **covers the target period** and **clips
  trips/charges to the target window by Start Time** (numbers = the target window; footer
  Source is marked "subset to window"). Battery capacity is read from
  `src/jolt_toolkit/configs/vehicles.json` `effective_capacity_kwh` (needed for the Range
  figure); OEM is taken from `plot_config.json` `vehicle_specs`, and model from
  `vehicles.json` `model`.
- **Operator resolution (DATA-DRIVEN)**: the page-header operator is the **dominant operator** in the
  briefing's data (mode of the trips' `Operator` column), falling back to the registration only if the
  column is empty. `plot_config.json` `company_assignment` (simple / round_robin) is **no longer used**
  for the operator — the report's per-leg `Operator` column is the single source of truth, so an operator
  change shows up automatically (e.g. CMZ6260 JLP→SJG→HTL; YN75NMA PORT_EXPRESS_DAIMLER→HTL) with no
  config edit. The anonymised version always hides the operator as "JOLT MEMBER".
- **Regen energy is taken from the raw_telematics cumulative counter** (`_counter_recup`):
  read the regen counter under `excel_report_database/<ver>/<REG>/raw_telematics/` and use
  `jolt_toolkit.analysis` `build_interp`/`delta` to interpolate-and-difference at each
  segment's [Start,End] endpoints and sum — **full coverage, correct basis (≈20% of
  energy)** — replacing the xlsx's sparse `Recuperation Energy` column (coverage often <50%,
  underestimated to ≈5%). Vehicles with no raw / no such counter (Scania/Mercedes/diesel)
  fall back to the xlsx column (usually shows "—"). The page-1 "Energy Recuperated" only
  shows the value (kWh), no percentage.
- **Page-1 distance / energy-used / recuperation / CHARGED TOTALS can use a RAW-TELEMATICS basis
  (`_raw_kpi_totals`), decided PER FIELD** — these four page-1 totals (and the derived Mean EP, daily
  avg/max, regen %) can come from whole-period sums of the raw_telematics cumulative counters
  (`odometer`, `total_electric_energy_used`, `electric_energy_recuperation_watthours`,
  `battery_pack_dc_watthours` + `battery_pack_ac_watthours`) instead of the filtered driving-leg /
  charge-leg sums, so they **include non-driving consumption** (parked HVAC/thermal/aux), Total
  Distance is the odometer's true travelled km (incl. < 3 km / excluded legs), and Total Energy
  Charged is **all** charging (not just segmented sessions). The decision is **independent per field**:
  - **Total Distance** → raw odometer whenever it is populated;
  - **Total Energy Used** → raw used-energy counter whenever populated, else the driving-leg /
    SOC-derived segment sum;
  - **Energy Recuperated** → raw recup counter whenever populated, else `_counter_recup` / "—";
  - **Total Energy Charged (+ AC/DC split)** → raw `battery_pack_dc + ac` counter whenever populated,
    else the xlsx **event** charge-leg AC+DC sum. The event sum only counts SEGMENTED charge sessions
    and **under-captures by 5–36%** (partial / un-segmented / gap-period charging); the raw counter
    captures all of it. SoC stats (median start / mean end) always stay event-based (no raw equivalent).
  - **Charge legs = Home AND Away** (`CHARGE` covers all six leg types `AC/DC/Charge × Home/Away`,
    since 2026-07-08): Away legs are real charging sessions (public/en-route chargers). The old
    Home-only set under-counted sessions fleet-wide (EV73SAL ~83, LN25NKE ~58 Away legs excluded)
    and broke down when the 2.2.8 recompute reclassified CMZ6260's depot charges to Away (Home
    68→8: the briefing showed 0 sessions / "—" SoC against a 10.6 MWh charged total on the same
    page). Session count, SoC stats, the SoC histogram and the event AC/DC fallback sums all
    include Away legs.

  So e.g. **Scania (EX74JXW/JXY), DAF (LN25NKE), Mercedes (YN25RSY/YN75NMA) populate the odometer
  but NOT the energy/recup/charge counters** → they get a **raw (complete) Total Distance** yet keep
  the **segment Total Energy Used** ("—" recup, "—" charged). **Volvo/Renault** populate all of them →
  fully raw, and **Total Energy Used then reconciles with raw Total Energy Charged for every vehicle**
  (used is 91–98 % of charged — slightly less, as round-trip/standby losses require). The OLD event-
  charged made some vehicles look like Used ≫ Charged (e.g. CMZ6260 +52 %), which was purely the
  event under-capture, not a real imbalance — hence charged is now raw-based on page 1.
  Mean EP always divides Total Energy Used by distance **on the same basis as that energy** (raw
  odometer for raw energy, driving-leg km for segment energy) so it stays a valid per-driving-km
  efficiency, never (driving energy ÷ all-travel distance). Robust estimator = Σ per-sample
  increments keeping only `0 ≤ Δ ≤ max_rate × Δt` — drops counter **resets** (negative steps; e.g.
  AV24LXK's energy counter resets 15× over 2 yr) and physically-impossible **spikes** (e.g. the
  odometer's 2 garbage jumps); energy/recup are sparse (TIMER-row only) so are dropna'd per column
  before diffing. Daily average = Total Distance ÷ **active days**; daily max = busiest single day.
  **`PAGE 2` analysis (per-leg EP/GVM scatters, range, temperature, conclusions) ALWAYS keeps the
  xlsx driving-leg segment basis — it is never raw.** In the verification workbook each raw-basis
  number is flagged **CHECK MANUALLY** (the leg sheets cannot reproduce a raw-counter whole-period
  total; the driving-leg formula is kept in the row note), not FAIL; segment-basis rows stay PASS/FAIL.
- **Two output versions via `--page1-basis {raw,segment}`** (default `raw`): `raw` = the per-field
  raw basis above (the standard briefing); `segment` = page-1 totals forced to the **excel-report
  driving-leg basis** (exactly the pre-2026-06 behaviour — energy/distance/recup all from the legs).
  The `segment` version's artefacts get a **`_xlsxkpi`** suffix (`report_<REG>_<period>_xlsxkpi.pdf` /
  `_xlsxkpi.html` / `verification_..._xlsxkpi.xlsx`) and **coexist in the same output dir** with the
  raw version (unsuffixed = raw). Page 2 is identical in both. Run the generator twice (once per
  basis) to produce both for a vehicle.

## 2. Preconditions

- The xlsx for the target period already exists, **or** a wider xlsx whose `[start,end]`
  covers the target period exists (the generator auto-selects the closest covering report
  and clips the data to the target window); if neither exists, run `/generate-excel-report`
  first.
- This machine has Chrome / Edge (headless PDF rendering).
- The repo-root `.env` has `HERE_API_KEY` (optional; if missing / on network failure the
  route map falls back to a basemap-free schematic and the caption switches to "indicative").
- **The temperature column must hold real values** (the EP-vs-temp figure depends on it): a
  freshly generated report may have all weather columns such as `Average Temperature (C)`
  as placeholder **0** (LoggerPatcher default) — in that case EP-vs-temp degrades (it will
  not crash, but is meaningless). Backfill temperature first via the weather-patch flow:
  clear the weather columns (xlsx columns 38–43) then run
  `python -m jolt_toolkit.report_generator.weather_patch <xlsx>` (coarse; coarse does not
  overwrite a value of 0, so the columns must be cleared first). Check: driving-segment
  temperature `nunique > 1`.

## 3. How to run

```bash
# Run from the repo root (PYTHONUTF8=1 avoids the Windows cp1252 encoding crash)
PYTHONUTF8=1 python .claude/skills/generate-pdf-report/generate_pdf_report.py \
    --reg YK73WFN --period 20250301_20250601 [--version 2.2.8] [--base]
```

- Artefacts → `pdf_report_workspace/output_by_TBD/<REG>_<OPERATOR>_<op_period>/` (the working
  set — on finalisation the whole dir is renamed to `output_by_<YYYYMMDD>/` as a frozen snapshot
  and an empty `output_by_TBD/` is recreated; scheme of 2026-07-10): `report_*.html`,
  `report_*.pdf`, `figures/*_<token>.png` (figure names carry a run token to bust the Chrome
  cache), `verification_*.xlsx` (the manual-verification workbook, see
  `references/verification.md`). All gitignored.
  - **Naming ALWAYS carries the operator**: the dir + every filename is
    `<REG>_<OPERATOR>_<op_period>` for BOTH the per-operator split AND the single-operator case
    (the single case uses the dominant operator, e.g. `AV24LXK_KNOWLES_…`, `YK73WFN_NESTLE_…`,
    `YN25RSY_WJF_…`) — so every briefing carries its operator consistently. `<OPERATOR>` is the
    filesafe form (non-alphanumerics → `_`, e.g. `WELCH_TRANSPORT`); the page header still shows
    the spaced display name.
  - **Naming aligns to the OPERATING PERIOD**: `<op_period>` = **the real span of valid
    trips** (first departure → last arrival, `YYYYMMDD_YYYYMMDD`), matching the page-header
    OPERATING PERIOD, **not** the nominal `<period>` passed on the command line (the latter
    is only used to locate the source xlsx). Example: passing `YN25RSY 20251001_20260201` but
    valid trips only run to 11-18 → the artefact directory/filenames are
    `YN25RSY_WJF_20251021_20251118`. With no valid trip it falls back to the nominal `<period>`.
- **Directory hygiene**: each run automatically cleans up the generator's historical
  timestamped copies (pdf/xlsx with a `_<unix-timestamp>` suffix, written as a fallback when
  the canonical name was locked) — only one latest named version and one latest anonymised
  version of the PDF are ever kept; any other file the user named manually is left untouched.
  A timestamped copy **newer than its canonical** is a locked-canonical fallback from a
  previous run (the canonical is the stale one): since 2026-07-10 it is **promoted over the
  canonical** (os.replace) rather than deleted — deleting it once left T88RNW's raw PDF two
  days stale after a viewer lock + the follow-up `_xlsxkpi` run's cleanup.

### Anonymised presentation version (`--anon`)

> **Default = named version only.** No anonymised version is produced unless `--anon` is
> explicitly passed. Do NOT generate an anon version by default or offer it unprompted — only
> add `--anon` when the user (or an external-presentation context such as SteerCo) explicitly
> asks for anonymisation.

External presentation (e.g. SteerCo) requires operator consent; the 2026-06 Nestlé approval
was conditional on **anonymisation**. Add `--anon`:

- Page-header operator → "JOLT MEMBER", **registration hidden**; model retained (the real
  model from vehicles.json).
- **Data-source footers stay hidden**, but the **page-2 chart trip-filtering footnote is kept** (it is
  methodology, not an identifying source — same text as the named version).
- Basemap switched to **CARTO light_nolabels** (OSM data, no place names; tile stitching +
  the same Web Mercator georeferencing), keeping route lines and start/end points; copyright
  note "© OpenStreetMap © CARTO".
- Artefacts are `report_anon_<period>.html/pdf` + `figures_anon/` (filenames carry no
  registration, can be forwarded directly), coexisting with the named version without
  overwriting it; the numbers are identical to the named version, verify with the named
  version's verification workbook.
- HERE basemap cache → `pdf_report_workspace/cache/` (keyed by centre/zoom/size), re-runs can
  be offline.
- At the end of the run a **field-applicability audit** is printed (real pipeline data vs N/A).
- ⚠️ Do not open the output PDF in a reader and then re-run: when the canonical name is
  locked it gets rewritten to `report_*_<unixtime>.pdf` with a notice; close the reader and
  re-run to write back the canonical name.

## 4. After running — mandatory follow-ups

1. **Commentary check**: the Conclusions / Summary text and the load-point band judgement
   (inspect the GVM histogram, record artic bands in `briefing_vehicle_specs.json`) are
   governed by `references/commentary-style.md` — load it whenever commentary is
   produced or a load-point decision is made.
2. **Field applicability**: before accepting any "—" / N/A field, check
   `references/field-applicability.md` (never fabricate).
3. **Verification (MANDATORY)**: run the AI-side checks in
   `references/verification.md` on every generated PDF, and hand the shipped
   `verification_*.xlsx` workbook to the human verifier before external delivery.
4. Log reusable lessons (per-vehicle quirks, sparse operators, band judgements) in
   `evaluations/` per its README.
