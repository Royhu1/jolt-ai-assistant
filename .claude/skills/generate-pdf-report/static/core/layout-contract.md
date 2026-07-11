# Layout and rendering conventions (always load — finalised, do not revert)

The briefing's two-page A4 layout is **contract-fixed**: every generated report must match
the finalised conventions below and the style baseline `references/style_baseline_*.pdf`.
Retired schemes are marked explicitly — do not restore them.

- **Two fixed A4-portrait pages** (210×297 mm). `@page { size:A4; margin:0 }`; each `.page` is
  `210mm × 297mm`, `overflow:hidden`, laid out with flexbox to fit one page — **no dynamic
  `@page` height injection** (the old 1280×720 16:9 / measure-and-inject scheme is retired, do
  not restore it). Both pages share the same **~11 mm side / ~7 mm bottom margins**; the navy
  headers are full-bleed.
- **Page 1 (operations dashboard) — UNFILTERED (all trips)**: full-bleed header → timeline →
  operating band → 4-cell summary strip → 3-card row (Vehicle Performance / Charging Sessions /
  route map, ~92 mm tall) → **Summary** card (plain-English bullets, see
  `references/commentary-style.md`). Page-1 footer is
  **empty** (the trip-filtering footnote lives on page 2, where the filtering applies). Every page-1
  count/total (Active Days, Driving Legs, Median GVM, timeline, distance/energy) is computed over
  **all** driving legs — see the Cleaning section in `references/commentary-style.md`.
- **Page 2 — four figures in a 2×2 grid (FILTERED)** + a **Conclusions** block + the
  **chart trip-filtering footnote** (`.analysis-footer`, italic muted, right-aligned: the valid-trip
  distance filter, see the Cleaning section in `references/commentary-style.md`; shown on
  both named and anon versions). The daily-traction-energy
  figure was removed. Grid cells, in order:
  1. Energy Performance vs Gross Vehicle Mass
  2. Projected Range vs Gross Vehicle Mass
  3. Energy Performance vs Ambient Temperature (**restricted to the laden cluster** to control
     for mass; the title states the laden mass range, e.g. "(laden, ≥ 20 t)")
  4. Charging Start State of Charge
- **No-mass distribution variant** (auto, see `static/fragments/mode/generate.md` §1): the page-2
  grid becomes (1) **Energy Performance
  Distribution** (histogram + KDE overlay + mean/median lines, EP axis 0–3), (2) **Projected Range
  Distribution** (per-trip capacity ÷ EP), (3) **Energy Performance vs
  Ambient Temperature** fitted over **all trips** (no laden cluster), (4) Charging Start SoC.
  Capacity for (2): `effective_capacity_kwh`, falling back to the **rated** capacity
  (`srf_capacity_kwh` / `nominal_kwh`, since 2026-07-10) when no effective value exists —
  e.g. LN25NKE, whose energies are all `soc_estimate` = ΔSOC × the SRF rated 462 kWh, so no
  independent effective estimate is possible; the capacity then cancels in range = cap/EP
  (≡ km-per-%SOC × 100) and the conclusions bullet says **"rated capacity"**, never
  "effective". Only with no capacity at all is the chart skipped (3-chart page). The GVM
  scatters, load markers and the 42 t projection are omitted.
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
