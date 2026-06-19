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

- **Single large-font layout, PDF = HTML preview**: on-screen and print share one layout
  (font sizes are 2× the original 16:9 version; page/card content auto-fits its height). A
  script at the end of the template measures each `.page`'s actual height after load and
  injects named `@page ops/analysis` sizes (headless Chrome prints after load) — **never**
  restore the fixed 720px 16:9 page.
- **Parameterised axes** (constants at the top of `generate_pdf_report.py`, so all reports
  are comparable across vehicles/periods; never hardcode per figure): EP axis
  `EP_MIN/EP_MAX` = 0–3 kWh/km; GVM axis `GVM_XLIM` = 0–45 t + `GVM_XTICKS` (0..40 step 10);
  temperature axis `TEMP_XLIM` = −5–30 °C + `TEMP_XTICKS` (0..30 step 10).
- **Charts**: scatter + fit + ±1σ shaded band; figsize 5.6×3.2 in, font sizes (global
  rcParams) ticks **17** / axis labels **18** / legend **13** pt (reduced from 21/23/15 on
  2026-06-16, to stop axis labels being clipped by the figure edge under fixed axes); **axis
  titles in Title Case** (each word capitalised, e.g. "Gross Vehicle Mass (t)", "Ambient
  Temperature (°C)"; units and abbreviations such as kWh/km, SoC kept as-is); **chart titles
  are rendered by HTML** (template `.chart-panel__title`), not drawn into the PNG.
- **The three scatter plots' axes are pinned and aligned** (EP-vs-GVM / Range-vs-GVM /
  EP-vs-temp): use a fixed axes box `SCATTER_AXBOX` (`_save(..., box=SCATTER_AXBOX)`,
  replacing the old `tight_layout`+`top=0.88`) → the plot box is pixel-consistent across
  figures, edges aligned; `_finish_scatter` then adapts to the **number of significant digits
  in the y ticks** (≥3 digits like Range's 200/400 are scaled down one order, ≥4 digits are
  rotated vertical), so all figures share the same left margin without clipping. The two bar
  charts (daily energy / SoC) still use `tight_layout`. `_scatter_fit` and Range's
  `curve_fit` both have a "≥3 points and x/y have variance" guard + try/except to avoid
  crashing on degenerate data.
- **Range vs GVM uses a reciprocal-model fit**: `recip_model(x, k, a, c) = c / (k·x + a)`
  (scipy `curve_fit`). The model is invariant under common scaling of (k,a,c) (a scale
  degree of freedom) → after fitting it must be **normalised by pinning c = battery
  capacity**, so that k·x+a returns to the dimension of the EP linear formula (self-consistent
  with the linear slope of the EP-vs-GVM figure). The other scatter plots use a linear fit.
- **Page-2 figure order** (5 rows): EP vs GVM → Range vs GVM → EP vs ambient temperature →
  Daily traction energy → Charging start SoC.
- **Route map**: the named version uses the HERE Map Image v3 real basemap (`style=lite.day`),
  the anonymised version uses CARTO light_nolabels (no place names); start/end points are
  Web Mercator pixel-georeferenced. The basemap request size `MAP_PX_W/H` (740×1060 portrait)
  **must match the aspect ratio of the map card's display window** — the card uses
  object-fit:cover, so a mismatched ratio crops the sides; **start/end points are not
  distinguished** (uniform red dot #e74c3c, no legend); the copyright note is **bottom-right**,
  semi-transparent ("map © HERE" / "© OpenStreetMap © CARTO", "indicative" when falling back
  to a schematic).

## 5. Commentary style guide — core responsibility

Each page-2 figure has a dark commentary box, **3–4 bullets, fixed structure**:

1. **Coverage**: data span + sample size + median, e.g.
   "GVM spans 10–42 t over 109 trips (median 19.6 t)."
2. **Fit**: slope/equation + R², e.g. "Fit slope +0.029 kWh/km per tonne (R²=0.51)." or
   "Reciprocal fit: Range = 352 / (0.028·GVM + 0.68) (R²=0.53)."
3. (+4.) **Comparison groups**: a paired two lines, format strictly
   `<Label>: For <condition>, Average <metric> = <value> <unit>.`

> **2026-06-10 partner-review ruling** (the style baseline; every future comparison bullet
> must follow this two-line format):
> - "Lighter GVM cluster: For GVM < 19 t, Average EP = 1.16 kWh/km."
> - "Heavier GVM cluster: For GVM ≥ 19 t, Average EP = 1.79 kWh/km."
> - "Coldest trips: For T < 5 °C, Average EP = 1.63 kWh/km."
> - "Warmest trips: For T > 15 °C, Average EP = 1.27 kWh/km."
>
> Rationale: operator/OEM readers want conclusions readable at a glance — condition and value
> split onto explicit lines beats a prose sentence. Any future comparison (e.g. dry/wet)
> follows the same format.
>
> **2026-06-16 update**: the light/heavy grouping **defaults** from a fixed 1/3 quantile to an
> **adaptive split at the density valley of the actual GVM distribution** (`_gvm_cluster_split`:
> Gaussian KDE, take the valley between the two highest-density peaks as the threshold; ≤ is
> the light cluster, > is the heavy cluster; for a single peak / insufficient sample fall back
> to the median) — HGV gross mass is often multi-modal (empty/laden), and the density valley
> fits the visual cluster boundary better than a fixed quantile or 2-means (with a large
> sample-size imbalance, 2-means pulls the boundary toward the big cluster and wrongly merges
> edge points, so it is not used). The threshold is computed inline per vehicle and period;
> the two-line format is unchanged.
> **Exception (`LEGACY_TERTILE_REGS`, currently includes `YK73WFN`)**: keep the original
> **fixed 1/3 tertile** wording ("Lightest/Heaviest 1/3 of trips: For GVM </> X t", X = the
> 33%/67% quantile) — YK73WFN is the partner style baseline, so its analysis wording stays
> unchanged. To add a vehicle that should keep tertiles, just add the registration to that set.

General rules:

- **British English**; state facts concisely, draw no inference unsupported by data; **every
  number must come from the pipeline computation (inlined in an f-string), no manual entry**.
- **Glossary**: gross vehicle mass / **GVM** (not GVW, vehicle gross weight, total mass);
  EP = energy performance (kWh/km); ambient temperature; Range = effective battery capacity ÷
  EP (state the capacity value).
- **A cluster/comparison-group Average range = capacity ÷ that cluster's average EP** (**not**
  the mean of per-segment range cap/EP): the latter is dominated by low-EP segments, is
  self-inconsistent with the EP commentary, and produces the counter-intuitive reversal
  "heavy cluster range > light cluster"; the former is monotone with the cluster EP and is
  always consistent with the EP commentary direction (low EP → high range). The per-segment
  scatter plot is still drawn with per-segment cap/EP.
- Light/heavy comparison is one of three (per vehicle, priority SINGLE_GROUP > LEGACY_TERTILE
  > default clustering):
  - **Default**: an **adaptive density-valley split** of the actual GVM distribution
    (`_gvm_cluster_split`: the valley between the two highest Gaussian-KDE peaks) → light/heavy
    two-cluster comparison.
  - `LEGACY_TERTILE_REGS` (includes YK73WFN): fixed 1/3 tertiles (the partner style baseline).
  - `SINGLE_GROUP_REGS` (includes YN25RSY=17t): the vehicle runs mostly laden, clustering is
    meaningless → **no clustering**, just one line "Laden operation (GVM > threshold t):
    Average EP/range = … over N trips (outliers excluded)", where the mean is the
    **IQR(1.5×)-outlier-trimmed average** (`_outlier_trimmed_mean`), and range = capacity ÷
    that mean.
  - The cold/warm comparison uses <5 °C / >15 °C (unless the user specifies otherwise).
- **Valid-trip filter**: a driving segment with distance < **3 km** (or missing distance) is
  invalid (too short / a residual segment) and excluded from all analysis. **The OPERATING
  PERIOD (page-header span), active days, and all KPIs/scatter are based only on valid
  trips** — i.e. the operating period is the real span determined by valid events, not the
  nominal bounds of the report-period argument (constant `MIN_TRIP_KM`).
- EP cleaning: a valid trip with EP ∉ **[0.3, 3]** kWh/km is treated as implausible and
  excluded from scatter/fit/commentary statistics (the 0.3 lower bound excludes the very-low
  EP from too-short / residual segments — otherwise the full-charge range projection 600/EP
  is dragged to a spurious value of thousands of km; the figure y-axis is still fixed 0–3).

## 6. Field applicability (do not fabricate N/A fields)

| Category | Fields |
|------|------|
| ✅ Real pipeline data | active days, trip/charge segment counts, total distance, mean/max daily distance, total energy, average EP, regen recovered kWh, AC/DC charging, start/end SoC, average GVM, EP-vs-GVM/temperature, Range-vs-GVM, daily energy, SoC distribution, route (lat/lon) |
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

1. Screenshot the HTML with headless Chrome (`--screenshot --window-size=1280,<tall enough>`),
   inspect by eye at native resolution, region by region.
2. Render each PDF page to PNG with PyMuPDF (`doc[i].get_pixmap(dpi=120)`), confirm two pages,
   content auto-fits height, consistent with the HTML.
3. Cross-check commentary numbers against the figures (slope sign, legend n, sanity of
   comparison values).
4. Compare against `references/style_baseline_YK73WFN_20250306_20250522.pdf` (the authoritative
   style baseline).

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
  code `generate_pdf_report.py` / `build_pdf.py` / `templates/` / style baseline `references/`
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
