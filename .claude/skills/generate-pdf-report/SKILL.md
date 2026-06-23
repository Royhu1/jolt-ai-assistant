---
name: generate-pdf-report
description: |
  Generate the industrial-partner one-page PDF/HTML briefing for a vehicle + period
  from the JOLT xlsx pipeline artefacts (excel_report_database/<ver>/<REG>/), by running
  generate_pdf_report.py (KPIs + matplotlib figures + HERE route map + Jinja2 template
  + headless-Chrome PDF). Output goes to pdf_report_workspace/output/<REG>_<period>/.
  This skill OWNS the briefing's layout and commentary style guide — also use it for
  chart/layout changes, commentary rewording, and applying partner review comments,
  so the subjective conclusions stay stylistically consistent across reports.
  Triggers on:
  (1) "generate the PDF briefing/report for <REG> in <period>"
  (2) "生成 <REG> 的 PDF 简报 / 工业伙伴报告"
  (3) "/generate-pdf-report <REG> <period>"
  (4) partner review comments on a briefing; briefing chart / layout / commentary changes
  If no xlsx for the requested period exists — neither an exact-period report nor a
  broader one whose [start,end] covers the window — hand off to /generate-excel-report first.
---

# generate-pdf-report — industrial-partner PDF/HTML briefing

Turn JOLT fleet-analysis results into a **one-page, dashboard-style briefing** (HTML + PDF)
delivered to industrial partners (fleet operators, OEMs). Kept strictly separate from
`publication_workspace/` (academic papers): this is a visual, easy-to-read results snapshot.
The layout derives from the EVITA Round Robin 1 Case Study under `references/`.

This skill owns both **generation** and **maintenance** (changing charts/layout/commentary,
applying review comments). It is the single authoritative source for how the briefing is
produced; `pdf_report_workspace/` only holds the artefacts.

## 1. Inputs and data sources

- Arguments: `<REG>` (registration) + `<period>` (`yyyymmdd_yyyymmdd`); optional `--version`
  (default 2.2.3) and `--base` (use the non-finetuned base xlsx).
- Data comes **only** from `excel_report_database/<version>/<REG>/jolt_report_*.xlsx`
  (prefer `_finetuned`). If there is **no exact-period** file, the generator automatically
  picks the most compact report whose `[start,end]` **covers the target period** and **clips
  trips/charges to the target window by Start Time** (numbers = the target window; footer
  Source is marked "subset to window"). Battery capacity is read from
  `src/jolt_toolkit/configs/vehicles.json` `effective_capacity_kwh` (needed for the Range
  figure); OEM is taken from `plot_config.json` `vehicle_specs`, and model from
  `vehicles.json` `model`.
- **Operator resolution** (`_resolve_operator`): first look up `plot_config.json`
  `company_assignment.simple`; for a dedicated vehicle not in `simple`, match the report
  period against the date ranges in `company_assignment.round_robin[REG]` (prefer the range
  containing the period-end day, otherwise the overlapping range); fall back to the
  registration if neither matches. Example: EX74JXW is in `round_robin`, the 2025-10/11
  period → `WJF`. The anonymised version always hides the operator as "JOLT MEMBER".
- **Regen energy is taken from the raw_telematics cumulative counter** (`_counter_recup`):
  read the regen counter under `excel_report_database/<ver>/<REG>/raw_telematics/` and use
  `jolt_toolkit.analysis` `build_interp`/`delta` to interpolate-and-difference at each
  segment's [Start,End] endpoints and sum — **full coverage, correct basis (≈20% of
  energy)** — replacing the xlsx's sparse `Recuperation Energy` column (coverage often <50%,
  underestimated to ≈5%). Vehicles with no raw / no such counter (Scania/Mercedes/diesel)
  fall back to the xlsx column (usually shows "—"). The page-1 "Energy Recuperated" only
  shows the value (kWh), no percentage.

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
    --reg YK73WFN --period 20250301_20250601 [--version 2.2.3] [--base]
```

- Artefacts → `pdf_report_workspace/output/<REG>_<op_period>/`: `report_*.html`,
  `report_*.pdf`, `figures/*_<token>.png` (figure names carry a run token to bust the Chrome
  cache), `verification_*.xlsx` (the manual-verification workbook, see §7). All gitignored.
  - **Naming aligns to the OPERATING PERIOD**: `<op_period>` = **the real span of valid
    trips** (first departure → last arrival, `YYYYMMDD_YYYYMMDD`), matching the page-header
    OPERATING PERIOD, **not** the nominal `<period>` passed on the command line (the latter
    is only used to locate the source xlsx). Example: passing `YN25RSY 20251001_20260201` but
    valid trips only run to 11-18 → the artefact directory/filenames are
    `YN25RSY_20251021_20251118`. With no valid trip it falls back to the nominal `<period>`.
- **Directory hygiene**: each run automatically cleans up the generator's historical
  timestamped copies (pdf/xlsx with a `_<unix-timestamp>` suffix, written as a fallback when
  the canonical name was locked) — only one latest named version and one latest anonymised
  version of the PDF are ever kept; any other file the user named manually is left untouched.

### Anonymised presentation version (`--anon`)

External presentation (e.g. SteerCo) requires operator consent; the 2026-06 Nestlé approval
was conditional on **anonymisation**. Add `--anon`:

- Page-header operator → "JOLT MEMBER", **registration hidden**; model retained (the real
  model from vehicles.json).
- **Both Source footers fully hidden** (including the xlsx filename and library path).
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

## 4. Layout and rendering conventions (finalised, do not revert)

- **Two fixed A4-portrait pages** (210×297 mm). `@page { size:A4; margin:0 }`; each `.page` is
  `210mm × 297mm`, `overflow:hidden`, laid out with flexbox to fit one page — **no dynamic
  `@page` height injection** (the old 1280×720 16:9 / measure-and-inject scheme is retired, do
  not restore it). Both pages share the same **~11 mm side / ~7 mm bottom margins**; the navy
  headers are full-bleed.
- **Page 1 (operations dashboard)**: full-bleed header → timeline → operating band → 4-cell
  summary strip → 3-card row (Vehicle Performance / Charging Sessions / route map, ~92 mm tall)
  → **Summary** card (plain-English bullets, see §5) → source footer.
- **Page 2 — four figures in a 2×2 grid** + a **Conclusions** block (the daily-traction-energy
  figure was removed). Grid cells, in order:
  1. Energy Performance vs Gross Vehicle Mass
  2. Projected Range vs Gross Vehicle Mass
  3. Energy Performance vs Ambient Temperature (**restricted to the laden cluster** to control
     for mass; the title states the laden mass range, e.g. "(laden, ≥ 20 t)")
  4. Charging Start State of Charge
- **Chart titles are HTML** (`.chart-cell__title`), **spelled out (no GVM/SoC abbreviations)**
  and **larger than the matplotlib axis labels**; a 2-line title height is reserved so every
  cell's plot box starts at the same y.
- **Charts are square (figsize 4.6×4.6 in)** with **no legend and no ±1σ shaded band** — the
  partner figures show only the scatter, the fit/trend line, the dashed extrapolation to 42 t,
  and the load markers. The slope / R² / σ are still computed for the Conclusions text, not drawn.
  Global rcParams: axis labels **16** / ticks **15** pt (kept smaller than the HTML titles).
- **All four charts share one fixed axes box** `SCATTER_AXBOX` (`_save(..., box=SCATTER_AXBOX)`)
  so their plot-box top/bottom edges align across the grid; `_finish_scatter` shrinks the y-tick
  font when it has ≥3 digits (e.g. Range's 200/400). `_scatter_fit` / the Range `curve_fit` keep
  the "≥3 points + variance" guard + try/except for degenerate data.
- **Parameterised axes** (top of `generate_pdf_report.py`, never hardcode per figure): EP
  `EP_MIN/EP_MAX` = 0–3 kWh/km; GVM `GVM_XLIM` = 0–45 t + `GVM_XTICKS`; temperature `TEMP_XLIM` =
  −5–30 °C + `TEMP_XTICKS`; full-laden reference `FULL_LADEN_T` = 42 t.
- **Load markers** (`_add_load_markers`): on the EP-vs-GVM and Range-vs-GVM charts, vertical
  dashed lines + labels mark **Unladen / Laden / Full (42 t)**, and the fit is **extended dashed
  from the observed-data max out to 42 t**. Labels auto-stagger (sorted by mass, alternating a
  high/low level) so adjacent labels never overlap; the lowest mass (Unladen) sits on the high
  level. The 42 t marker is labelled a projection when observed GVM never reaches it.
- **Range vs GVM uses a reciprocal-model fit** `recip_model(x,k,a,c)=c/(k·x+a)` (scipy
  `curve_fit`), **normalised to c = battery capacity** so k·x+a matches the EP linear slope; the
  other charts use a linear fit.
- **Route map**: named = HERE `lite.day`; anonymised = CARTO `light_nolabels` (no place names);
  start/end points Web Mercator pixel-georeferenced, uniform red dot #e74c3c, no legend;
  `MAP_PX_W/H` (740×1060 portrait) must match the map card aspect (object-fit:cover); copyright
  note bottom-right ("map © HERE" / "© OpenStreetMap © CARTO", "indicative" on schematic fallback).

## 5. Conclusions & Summary — core responsibility

The page-2 **Conclusions** block and the page-1 **Summary** block are the subjective deliverable.
Both are plain-English, partner-facing, **British English**, concise, with **every number inlined
from the pipeline (no manual entry)** and **no inference unsupported by the data**. Use
**"energy performance"** (matching the figures), not "energy use". Glossary: gross vehicle mass
(GVM); EP = energy performance (kWh/km); Range = effective battery capacity ÷ EP (state capacity).

### Page-2 Conclusions (load points + load sensitivity + temperature)
Report at three load points, each with a **±1 standard deviation** in brackets:

- **Unladen (~M t)**, **Laden (~M t)**, **Fully laden (42 t, projected to rated GVW)** →
  `energy performance X (±s) kWh/km, range Y (±s) km`.
- **Range = capacity ÷ that point's EP** (state the capacity); ± propagated as `range·σ_EP/EP`.
  A cluster's range is `capacity ÷ cluster-mean EP`, **never** the mean of per-trip cap/EP (the
  latter is dominated by low-EP trips and inverts heavy>light); the per-trip scatter still plots
  cap/EP.
- One **load-sensitivity** line (`Each extra tonne of load adds ~m kWh/km`).
- One **temperature** line: `Temperature (laden trips, lo–hi t): energy performance changes
  ~X kWh/km per 10 °C colder (R²=…) — <largely / moderately / noticeably temperature-sensitive>`.
  Temperature is fitted on the **laden cluster only** (mass held roughly constant); the bullet
  states the laden **mass range**.

### Load-point masses & EP basis (data + judgement) — `_compute_load_points`
Masses combine the GVM distribution with judgement. Priority **band > single-group >
legacy-tertile > KDE**:

- **Band mode** (`briefing_vehicle_specs.json` `unladen_band_t`=[lo,hi], opt. `laden_min_t`):
  for an **artic whose lightest GVM cluster is the bobtail tractor** (not a real unladen mass).
  Unladen = data points in [lo,hi) (tractor + empty trailer); laden = GVM ≥ laden_min (default
  hi); bobtail (< lo) excluded. e.g. **EX74JXW = [14,20], laden_min 20** (bobtail ~12 t).
- **Single-group** (`SINGLE_GROUP_REGS`, e.g. **YN25RSY = 17 t**): laden = GVM > threshold;
  **no unladen point** (runs mostly laden); laden EP = IQR(1.5×)-trimmed mean.
- **Legacy tertile** (`LEGACY_TERTILE_REGS`, e.g. **YK73WFN**): unladen = lightest tertile,
  laden = heaviest tertile (the partner style baseline).
- **Default**: KDE density-valley split (`_gvm_cluster_split`) — laden = denser cluster,
  unladen = lighter cluster.

**EP basis**: laden EP = mean of the laden data points (ample data; ± within-cluster std).
Unladen EP = mean of the unladen data points **except in band mode**, where the band is sparse
→ the **EP-vs-GVM trend evaluated at the unladen mass** (± fit σ). Fully-laden (42 t) has no data
→ always the **trend extrapolated** (± fit σ); drawn dashed + labelled "projected" when observed
GVM never reaches 42 t.

### Page-1 Summary (no duplication of page 2)
1. Fleet-overview line (active days, distance, ~km/day, total energy, mean EP).
2. Charging behaviour (sessions, median start SoC, mean end SoC).
3. **Regen-recovery line** (`recup_pct`, only when the vehicle reports recuperation — the
   Volvo/Renault raw-telematics counter): `Regenerative braking recovered ~X kWh over the period —
   about Y% of the energy used`, where **Y = energy recuperated ÷ total energy used × 100** (the
   project's "≈20% of energy" basis; tot_e is the net driving discharge). Omitted for vehicles with
   no regen channel (then the data-availability note flags it instead).
4. **Data-availability note** (adaptive): the channels this vehicle does **not** report — e.g.
   "Data channels: charged energy (AC/DC) and energy recuperated are not reported by this vehicle
   telematics (shown as '—')." Omitted when every channel is reported.
The load / range / temperature detail lives on page 2 and is **not** repeated in the Summary.

### Cleaning (unchanged)
- **Valid-trip filter** (`MIN_TRIP_KM` = 3 km): drop driving legs with distance < 3 km (or
  missing). The OPERATING PERIOD (page-header span), active days and all stats use only valid
  trips — the period is the real span of valid events, not the nominal `<period>` argument.
- **EP cleaning** (`EP_CLEAN_MIN/MAX` = 0.3 / 3): EP outside [0.3, 3] kWh/km is dropped from
  scatter / fit / conclusion stats (0.3 lower bound kills the spurious thousand-km range from
  too-short residual legs); the EP y-axis stays fixed 0–3.

## 6. Field applicability (do not fabricate N/A fields)

| Category | Fields |
|------|------|
| ✅ Real pipeline data | active days, trip/charge segment counts, total distance, mean/max daily distance, total energy, average EP, regen recovered kWh, AC/DC charging, start/end SoC, average GVM, EP-vs-GVM, Range-vs-GVM, EP-vs-temperature (laden cluster), SoC distribution, route (lat/lon) |
| ⚠️ Partially available | regen recovery (**EVs with a counter (Volvo/Renault) now use the raw_telematics counter for full coverage**, ≈20%; vehicles with no counter, Scania/Mercedes/diesel, still N/A → "—"), net payload (only GVM, must subtract tare) |
| ✗ N/A (operator commercial data) | customer count, cargo type, charging cost/rebate, CO₂ and fuel saving (needs a diesel baseline), fixed shifts |

✗ fields must be requested from the operator / Monta, or clearly marked estimated/not
applicable — **never fabricated**.

- **Unavailable → show "—" not 0**: when a pipeline field is in the schema but this vehicle
  has no valid value for the whole column (e.g. some vehicles do not report charging AC/DC
  kWh, or regen recovery), pass NaN via `_sum_or_na`, and the render-side `f()` shows "—"
  rather than a misleading 0; the charging commentary then changes wording to "Charged-energy
  AC/DC breakdown not reported for this vehicle." A true 0 (data present and genuinely 0) is
  still shown as 0. The audit print likewise shows "—" for unavailable.

## 7. Post-generation verification

**AI side (mandatory on every generation)**:

1. Render each PDF page to PNG with PyMuPDF (`doc[i].get_pixmap(dpi=150)`), confirm **two
   A4-portrait pages** (595×842 pt = 210×297 mm) and that no content is clipped (page-1 Summary +
   footer present; page-2 Conclusions + footer present with a bottom margin).
2. Inspect region by region: page-1 cards/summary fill the page without large empty bands; the
   page-2 2×2 chart **boxes are top/bottom aligned**, load markers don't overlap, titles aren't
   clipped.
3. Cross-check the Conclusions / Summary numbers against the figures (slope sign, the load-point
   values vs the markers, sanity of unladen < laden < full).
4. Compare against `references/style_baseline_*.pdf` (the authoritative style baseline).

**Manual verification (before external delivery, done by a human)**: each generation
automatically ships a `verification_<REG>_<period>.xlsx` verification workbook —

- The `Trips`/`Charges`/`Daily` sheets are the period's raw legs copied from the canonical
  xlsx (a self-contained data basis);
- The `Audit` sheet lists **every number that appears in the briefing**, one per row (~46
  items), and recomputes each from the raw legs on the fly using **native Excel formulas**
  (SUM/MEDIAN/AVERAGEIFS/SLOPE/RSQ/PERCENTILE…) — an independent computation path from the
  generator's pandas, so any mismatch is automatically flagged red **FAIL**;
- The verifier opens the workbook: review FAIL items → spot-check PASS items → complete CHECK
  MANUALLY items (timeline median, battery capacity vs vehicles.json, reciprocal-fit R² vs the
  legend) → fill in the Verified by / Date / Notes columns for the record.
- Note: openpyxl writing Excel 2010+ new functions needs the `_xlfn.` prefix; the workbook
  uses compatible forms throughout (e.g. `PERCENTILE` rather than `PERCENTILE.INC`, same
  interpolation).

## 8. Style references (`references/`)

- `EVITA Round Robin 1 Case Study PDF.pdf` — the source of the layout.
- `style_baseline_YK73WFN_20250306_20250522.pdf` — a finished snapshot of the current
  finalised style (the version after the 2026-06-16 changes to fonts / axes-box alignment /
  clustering / valid-trip filter / operating-period naming); new reports should match its
  style. Note: `references/` are gitignored local files, not shared via git (local reference
  only).

## 9. Discipline and ownership

- **This skill is the self-contained, sole owner of industrial PDF-briefing development**:
  layout, chart specs, commentary style, KPI/statistics computation basis, and the generator
  code `generate_pdf_report.py` / `build_pdf.py` / `templates/` / `briefing_vehicle_specs.json`
  (per-vehicle unladen-band / mass overrides) / style baseline `references/`
  are all maintained by this skill, with all knowledge recorded in this SKILL.md. **All
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

## To-do (ported from the original workspace README)

1. The 3 logo placeholder boxes in the title bar: once real logos arrive, put them in
   `references/logos/` and replace the template `.logo-ph` with
   `<img src="logos/<operator>.png">` (left = operator / centre = JOLT / right = OEM).
2. Commercial-field interface: if the operator provides Monta cost/scheduling, add
   `--ops-data <json>` to merge into the context.
3. Units: currently km / kWh/km; add a switch for an imperial miles version if needed.
