# PDF-briefing Audit — Experience Accumulation (LESSONS)

> `pdf-report-auditor` **reads this first** every audit, and at wrap-up appends new lessons here after
> de-duplicating. Seeded 2026-06-26 from the conversation that built the raw-counter page-1 basis.

## Data lineage & the two versions (the mental model)

- `raw_telematics/raw_*.csv` (cumulative counters, ~daily files) → `jolt_report_*.xlsx` (segment legs,
  deduped on Start Time+Leg Type for `--all-data`) → briefing PDF (page 1 + page 2).
- **Two PDFs per output dir** (`generate_pdf_report.py --page1-basis {raw,segment}`):
  `report_<REG>_<period>.pdf` = **raw** page-1 (counters); `..._xlsxkpi.pdf` = **segment** page-1 (xlsx
  legs). **Page 2 is segment-basis in BOTH.** Audit both.
- Page-1 raw basis is decided **per field** (`_raw_kpi_totals`): Total Distance ← `odometer`; Energy
  Used ← `total_electric_energy_used`; Recuperated ← `electric_energy_recuperation_watthours`; Energy
  Charged (+AC/DC) ← `battery_pack_dc + ac_watthours`. Each falls back to the segment/leg sum when its
  counter is absent. Mean EP divides Used by distance ON THE SAME basis as the energy.

## Robust-counter recipe (reproduce before trusting any raw KPI)

- Read all `raw_*.csv` in the window, sort by `eventDatetime` (UTC). **Drop NaN per column first** —
  energy/recup/charge counters are SPARSE (logged only on TIMER rows, NaN on dense GPS rows); diffing
  the raw column pairs a value against NaN and loses almost everything (the "290 kWh" bug).
- `Δ = diff()`, `Δt_h = time diff`. Valid increment = `0 ≤ Δ ≤ max_rate·Δt` (energy/recup/charge
  max_rate = 1e6 Wh/h = 1000 kW; distance = 130 km/h). This drops **resets** (Δ<0) and **spikes**
  (Δ above the physical ceiling). TOTAL = Σ valid increments × scale.
- **Per-day series** (for daily max) additionally drops increments with `Δt > 6 h` — a multi-hour/day
  data gap accumulates real distance/energy but, dumped into one day, gives an absurd daily max (the
  EX74JXY "5,117 km in a day" bug). TOTAL keeps gap increments (real travel); per-day excludes them.

## VERIFIED facts (2026-06-26, version 2.2.6 data) — re-check, but these were correct

- **Energy reconciliation (whole-vehicle, raw Used vs raw Charged = battery_pack DC+AC)**: every
  counter-vehicle had Used = **91–98 %** of Charged (Used slightly < Charged = round-trip/standby
  losses — physically correct). e.g. AV24LXK 183,430 / 193,759 (95 %), T88RNW 64,548 / 66,820 (97 %),
  CMZ6260 24,973 / 25,598 (98 %). If a future audit shows Used ≫ Charged whole-vehicle → red flag.
- **Counter-vehicle map** (have energy+charge counters → fully raw): Volvo (AV24LXJ/K/L, CMZ6260,
  EV73SAL, KY24LHT, YK73WFN) + Renault (N88GNW, T88RNW, TA70WTL).
- **No energy/charge counters** (raw DISTANCE only; energy=segment; recup/charged "—"): Scania
  (EX74JXW, EX74JXY), DAF (LN25NKE), Mercedes (YN25RSY, YN75NMA). They DO populate `odometer`.
- **WU70GLV (DAF XF 450), YT21EFD (Scania P410) are DIESEL** → no EV briefing (skip).

## KNOWN & ACCEPTED limitations — do NOT re-flag as bugs

- **Event charge-leg sum under-captures charging by 5–36 %** (partial/un-segmented/gap-period charges
  not counted). The `_xlsxkpi` (segment) version shows this lower event-charged ON PURPOSE; the raw
  version shows the canonical raw battery_pack counter. So the segment version's Used > Charged is
  expected, NOT a bug.
- **Per-operator (round-robin) briefings: Charged can be < Used** because the short operator window's
  start/end SoC differ (the battery ran on charge put in before the window). e.g. CMZ6260_JLP window
  SoC 86 %→28 %, so window Used 1,434 > Charged 1,265. Whole-vehicle still reconciles. EXPECTED.
- **Segmentation under-captures DISTANCE for some vehicles** — raw odometer ≫ leg-sum (EX74JXY +97 %,
  LN25NKE +31 %, T88RNW +20 % un-segmented). The raw odometer is the TRUE distance; this is a known
  data property, not a raw-side error. Flag only if odometer has no gap/short-trip explanation.
- **No GVM**: T88RNW & YN75NMA (and the no-mass variant vehicles) genuinely have no gross-mass signal
  → "Median GVM —" and the distribution page-2 variant. EXPECTED (a data gap, not a bug).
- The diesel `total_electric_energy_used` etc. are absent by design.

## Traps / pitfalls

- **Do NOT verify layout by eye on a PyMuPDF render** — line-wrapping is BAKED into the PDF by Chrome
  at generation; PyMuPDF's own font fallback can wrap differently from what's in the PDF, so the eye
  was fooled twice (3-line label read as 2). Verify via `page.get_text()` (the `\n` are the real
  wraps) + word bounding boxes: card height 92 mm; flag if the last card row's `y1` ≥ card bottom
  (= title `y0` − 11 pt + 92 mm·2.835). Fonts ARE embedded, so all readers render identically.
- **Round-robin vehicle-level vs briefing**: a whole-vehicle raw re-derivation differs from the
  per-operator briefing (the briefing windows each operator's trip span ±1 day, excluding
  between-operator gaps). Compare like-for-like (use the operator window) when checking a split.
- **"99,796 ≠ AV24LXK"**: registrations differ by one letter (AV24LX**J** vs AV24LX**K**); a value
  quoted by a human may be the sibling vehicle's. Always re-derive for the exact REG.
- Run from repo root with `PYTHONUTF8=1` (Windows cp1252 crash). Heavy raw reads (≈750 files/vehicle)
  → background or one script over all 15 vehicles.

## VERIFIED facts (2026-06-26 audit run, version 2.2.6) — confirmed independently, re-check next time

- **The whole fleet re-derives correctly.** Every page-1 (raw + segment basis) and page-2 number
  across all 21 briefings matched an independent pandas re-derivation within rounding. Raw AC/DC/Total
  charged split matched to the kWh for every counter vehicle (AV24LXJ AC 9 / DC 158,235, EV73SAL AC
  34,440 / DC 114,871, YK73WFN AC 21,628 / DC 125,712, …). Counter-vehicle reconciliation 91–98 %
  reconfirmed. Daily-max distances all plausible (25–85 km/h over realistic spans; gap-exclusion OK).
- **Page-1 SoC has TWO different (both correct) statistics**: the **"Mean Start SoC" tile = mean**
  (`ch["ssoc"].mean()`); the **Summary "median X% start SoC" = median** (`ch["ssoc"].median()`). They
  differ (skewed SoC), e.g. YN25RSY tile 30 (mean 29.9) vs summary 21 (median 21.0). A naive comparison
  that diffs the tile against your median will FALSE-flag — compare tile→mean and summary→median.
- **`trips/day` and `Median GVM` round to 1 dp** (14.9, 28.2 t) — keep comparison tolerance ≥0.05/0.05
  or you get phantom mismatches.
- **No-counter vehicles' RAW-version Energy Used == SEG-version Energy Used** (fallback): Scania
  (EX74JXW/JXY), Mercedes (YN25RSY/YN75NMA), DAF (LN25NKE) have energy/recup/charge counters that are
  **present-but-100%-NaN** in raw_telematics → raw basis falls back to segment for energy, "—" for
  recup/charged. Only distance differs between the two versions for these vehicles. EXPECTED.

## Post-fix re-audit 2026-06-26 — FLAG 1 & FLAG 2 fixes VERIFIED RESOLVED (re-confirm next regen)

- **FLAG 1 (EX74JXY charged `0`→`—`) is FIXED and correctly scoped.** Guard added in
  `_emit_briefing`: `if charge_basis == "segment" and len(ch) > 0 and not (notna(tot_ch) and
  tot_ch > 0): ac = dc = tot_ch = NaN`. → EX74JXY now shows `—` (both versions) and its data note
  discloses charged-missing. **Scoped to `charge_basis=="segment"` only**, so a counter vehicle's
  REAL raw zero is NOT suppressed — CMZ6260_JLP legitimately shows `— AC Charged 0 kWh` (raw AC
  counter genuinely 0, DC-only window). When auditing charged, distinguish: dist-only vehicle all-zero
  event legs → must be `—`; counter vehicle raw-0 → keep `0`. Fleet-wide invariant to re-check: every
  dist-only vehicle (EX74JXW×2, EX74JXY, LN25NKE×3, YN25RSY, YN75NMA×2) shows charged `—` + note
  "charged energy (AC/DC) … not reported"; every Volvo/Renault shows a real charged value + note
  silent on charged.
- **FLAG 2 (T88RNW Summary overflow) is FIXED.** `.ops-summary` tightened (padding `13px 22px 11px`,
  `li line-height:1.42; margin:3px 0`). Page-1 max word `y1` dropped **845 → 816.9 pt** (inside the
  841.92 pt page). Re-confirm with the max-y1 sweep below.
- **Card-overflow check — corrected recipe (the 2026-06-26 first pass had a false positive).** The
  SUMMARY block title sits at `y0≈630` BELOW the stat-card bottom (`≈606`); include only words whose
  TOP is strictly inside the card (`title_y0 < w.y1top < card_bottom`), else the SUMMARY title (in the
  perf-card x-band) false-flags as overflow. Verified-good geometry: page1 stat-card titles
  "VEHICLE PERFORMANCE"/"CHARGING SESSIONS" at `y0≈356`; `card_bottom = 356 − 11 + 92·2.835 ≈ 606`;
  real card content max `y1 ≈ 590` (perf "Energy Recuperated" row / charge "Mean End SoC" row) → ~16 pt
  slack. The day-rhythm strip ("DAY START/END", departure/arrival, "≈ N trips/day") is a TOP header
  band at `y0≈99–193`, above the cards — never inside the overflow window. Map caption "map © HERE"
  `y1≈600` lives in col-3, x≈508 — exclude from the charge band (xhi=422).
- **Layout baselines (2.2.6 post-fix, all 42 PDFs)**: page-1 max-y1 = **800 pt** for every briefing
  (the footer line) except T88RNW **817**; page-2 max-y1 = **773–785 pt**. Page-overflow threshold
  **828 pt** (page height − bottom margin) cleanly separates pass (≤817) from the old clip (845).
  Per-card text-rows: perf ≤ 9, charge ≤ 9, uniform fleet-wide — a 3-line label would bump one card
  to ≥10 rows AND push cmax past 606 (neither happened). Longest VALUE today = AV24LXK "193,759 kWh"
  / "193,662 kWh" — renders full-font (label wraps, value `flex:0 0 auto` never shrinks; `v-xs` guard
  only fires at ≥13 chars, never seen).
- **Operator display name underscores→spaces is display-only** (`operator_clean =
  operator.replace("_"," ")` for the header/sub-title; the per-leg filter `op_filter` + dir/file
  `_op_tag` keep underscores). So "WELCH TRANSPORT" / "PORT EXPRESS DAIMLER" / "DP WORLD" on the page,
  `WELCH_TRANSPORT` etc. in the path. Don't mistake the spaced header for a data/filter change — the
  numbers still reconcile (verified T88RNW "WELCH TRANSPORT").

## RE-VERIFIED facts (2026-06-26 post-fix re-derivation) — exact matches, re-check next time
- **Raw-counter page-1 totals re-derive EXACTLY** (robust Σ-valid-increment recipe): EX74JXY odometer
  31,380 km; T88RNW 59,080 km / used 64,548 / recup 21,134 / DC 64,788 / AC 2,032 / total 66,820
  (Used/Charged 96.6 %); AV24LXK 126,729 km / used 183,430 / recup 34,546 / DC 193,662 / AC 97 /
  total 193,759 (94.7 %). All identical to the regenerated PDFs → the display/layout regen shifted no
  value. EX74JXY energy/recup/charge counters are 100 % NaN (0 non-null) → segment fallback / "—".
- **Per-operator raw `used` differs from a calendar-window re-derivation by ~0.7 %** (CMZ6260_JLP PDF
  1,434 vs calendar-window 1,424): the briefing windows `used` by the operator's exact TRIP span, and
  raw `used` includes PARKED (non-driving) consumption, so a boundary parked-but-charging sample adds
  kWh with **0 extra odometer km** — distance/recup/charged match exactly while `used` shifts slightly.
  EXPECTED; compare like-for-like (operator trip span) or accept ≤1 % on `used` for round-robin splits.

## NEW flags found 2026-06-26 (fixes proposed, not yet applied — re-check if still present)

- **`_sum_or_na` shows a FALSE "0 kWh" when a charge channel is present-but-all-zero.** EX74JXY's
  xlsx event charge legs carry a genuine `0.0` (not NaN) in `Energy Charged AC/DC` on 20 of 146 legs,
  so `_sum_or_na` (returns the sum whenever `.notna().any()`) yields `0.0` → page-1 shows
  `Total Energy Charged 0 kWh / AC 0 / DC 0` next to "146 charging sessions, SoC 52→96 %"
  (self-contradiction; sibling EX74JXW correctly shows "—" because its charge cols are all-NaN). Same
  root cause makes EX74JXY's data-availability note omit "charged energy". Fix → `generate-pdf-report`
  skill: treat present-but-all-zero charge AC/DC (no positive value, no raw counter) as unavailable → "—".
  **Trap for the auditor**: a present-but-all-zero column is NOT the same as all-NaN — when probing
  "is this channel reported", count `notna()` AND check for any value > 0, not just `nonzero`.
- **No-mass + regen vehicle overflows the page-1 Summary.** T88RNW is the only distribution-variant
  vehicle that also reports regen → its Summary has 4 bullets (fleet+charging+regen+data-availability),
  and the last line sits at y1≈845 pt > the 841.92 pt A4 edge (clipped). Every other briefing maxes at
  y1≈798. Fix → skill: condense the 4-bullet summary. **Layout-check recipe that caught it**: PyMuPDF
  `page.get_text("words")`, take `max(w[3])` per page; flag if > ~828 pt (page height − bottom margin).
  This is the reliable coordinate check the LESSONS "do not judge by eye" trap calls for.

## Useful reusable scripts (rebuild as needed)

- Per-vehicle reset/spike/gap decomposition of any counter; raw-vs-segment reconciliation table
  (distance, energy, recup, charged event vs raw); layout overflow check (text-position based). The
  2026-06-26 run produced working versions in the session scratchpad: `rederive.py` (own robust-counter
  re-derivation over all 21 briefings → JSON), `compare.py` (parse PDF `get_text()` page-1 + diff),
  `summary.py` (reconciliation/odometer/page-2 monotonicity tables), `layout.py` (per-page max-y1
  overflow check). Re-author from the recipes above.
