# Conclusions & Summary — core responsibility (commentary style guide)

Load this file whenever page-2 Conclusions / page-1 Summary text is produced or changed, or
a load-point decision is made — in both `generate` and `revise` mode.

The page-2 **Conclusions** block and the page-1 **Summary** block are the subjective deliverable.
Both are plain-English, partner-facing, **British English**, concise, with **every number inlined
from the pipeline (no manual entry)** and **no inference unsupported by the data**. **State the
headline numbers only — no parenthetical median / IQR / σ breakdowns and no subjective verdict tags
(e.g. "…temperature-sensitive", "widely spread"); this applies to BOTH the standard and the
distribution variant** (the per-load-point `±s` on the standard variant is kept — it is a concise,
expected spread, not a verbose breakdown). Use
**"energy performance"** (matching the figures), not "energy use". Glossary: gross vehicle mass
(GVM); EP = energy performance (kWh/km); Range = effective battery capacity ÷ EP (state capacity).

## Page-2 Conclusions (load points + load sensitivity + temperature)

Report at three load points, each with a **±1 standard deviation** in brackets:

- **Unladen (~M t)**, **Laden (~M t)**, **Fully laden (42 t, projected to rated GVW)** →
  `energy performance X (±s) kWh/km, range Y (±s) km`.
- **Range = capacity ÷ that point's EP** (state the capacity); ± propagated as `range·σ_EP/EP`.
  A cluster's range is `capacity ÷ cluster-mean EP`, **never** the mean of per-trip cap/EP (the
  latter is dominated by low-EP trips and inverts heavy>light); the per-trip scatter still plots
  cap/EP.
- One **load-sensitivity** line (`Each extra tonne of load adds ~m kWh/km`).
- One **temperature** line: `Temperature (laden trips, lo–hi t): energy performance changes
  ~X kWh/km per 10 °C colder/warmer` (**sign-aware**: "colder" when EP rises as temperature falls, i.e.
  `temp_slope < 0`; "warmer" when EP rises with temperature) — **numbers only: no R² and no qualitative "…temperature-sensitive"
  verdict tag** (see the style note above). Temperature is fitted on a **narrow mass window within
  the laden cluster** (`_narrow_temp_window`: adaptive width **2–5 t** — the densest such window
  holding ≥~15 points, widening from 2 t only as the data volume requires, capped at 5 t — so mass is
  genuinely held roughly constant, not merely "laden"); the bullet + chart title state that **narrow
  mass range** (e.g. "(laden, 24–27 t)"). The load points still use the FULL laden cluster.

## Load-point masses & EP basis (data + judgement) — `_compute_load_points`

Masses combine the GVM distribution with judgement. Priority **band > single-group >
legacy-tertile > KDE**.

**Use AI judgement, not a blind algorithm** (especially for artics): at generation time, INSPECT the
vehicle's GVM histogram / KDE and map the clusters to the **articulated-HGV mass tiers** —
(1) **tractor-only / bobtail ~10 t** = the lightest cluster, NOT a real operating mass → **EXCLUDE**;
(2) **tractor + empty trailer ~16–17 t** = **unladen**; (3) **loaded operations** = higher,
operation-dependent up to the rated GVW (~42 t) = **laden** — then record that decision as a
`briefing_vehicle_specs.json` band. The default KDE split is only a fallback: for a mostly-laden
vehicle it merges the ~17 t unladen shoulder into the dominant laden peak and reports a too-high
unladen (e.g. CMZ6260's KDE → ~19 t, whereas the true tractor+trailer unladen is ~17 t).

- **Band mode** (`briefing_vehicle_specs.json` `unladen_band_t`=[lo,hi], opt. `laden_min_t`): the
  AI-judged artic case above (**takes priority** over single-group / legacy-tertile / KDE). Unladen =
  data points in [lo,hi) (tractor + empty trailer); laden = GVM ≥ laden_min (default hi); bobtail
  (< lo) excluded; `unladen_mass_t` pins the marker when the band is sparse. Illustrative examples:
  **EX74JXW [13,19]/19** (unladen pinned ~17 t), **YK73WFN [13,24]/24** (bobtail ~11 t — 106 data
  points! — excluded, unladen ~19 t, laden ~35 t); all 12 current entries live in
  `briefing_vehicle_specs.json` (the single source, with per-vehicle histogram + judgement in each
  JSON `note`; do not enumerate them here).
- **Single-group** (`SINGLE_GROUP_REGS`): laden = GVM > threshold, no unladen point — for a vehicle
  that genuinely runs only laden. **None currently** (YN25RSY moved to a band once its ~19 t unladen
  cluster was identified); a configured band overrides single-group.
- **Legacy tertile** (`LEGACY_TERTILE_REGS`, e.g. **YK73WFN** historically): unladen = lightest
  tertile, laden = heaviest. **Superseded for YK73WFN by an AI-judged band** (band has priority) —
  the tertile let YK73's 106 bobtail points contaminate the lightest third / unladen.
- **Default** (fallback only): KDE density-valley split (`_gvm_cluster_split`) — laden = the
  **heavier** cluster by mass, unladen = the lighter. Prefer an AI-judged band for artics (the
  default cannot see the bobtail/unladen/laden tiers and will mislabel a mostly-laden vehicle).

**EP basis**: laden EP = mean of the laden data points (ample data; ± within-cluster std).
Unladen EP = mean of the unladen data points **except in band mode**, where the band is sparse
→ the **EP-vs-GVM trend evaluated at the unladen mass** (± fit σ). Fully-laden (42 t) has no data
→ always the **trend extrapolated** (± fit σ); drawn dashed + labelled "projected" when observed
GVM never reaches 42 t.

## Page-1 Summary (no duplication of page 2)

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

## No-mass distribution variant — conclusions & page-1

When the vehicle reports no usable mass, the page-2 Conclusions become a **distribution analysis**
(no load points): EP `averaged X kWh/km over N trips`; projected range `averaged X km —
effective capacity Z kWh ÷ per-trip EP` (headline means only — no median/IQR/σ parentheticals and no
"…spread" verdict, per the style note above); the temperature bullet is fitted over **all trips** (stated
as "all trips", not "laden"); plus one honest line that load dependence cannot be assessed without
mass. Page-1 "Median GVM" shows "—" (forced for the no-mass variant even if a few legs happen to carry a mass value) and the data-availability note lists "gross vehicle mass". The
verification workbook (a mass-based audit) is **not** emitted for this variant (follow-up: add a
distribution-stats audit).

## Diesel-comparator variant — conclusions & page-1

The metric is **"fuel consumption"** (L/100km, matching the figures), never "fuel economy"
or mpg. Load points follow the standard rules (band > KDE; ± as usual) but are computed on
the **trunk-haul subset** (average speed ≥ 50 km/h — over all trips the urban tail swamps
the mass signal); the load-sensitivity line states that basis once: `Each extra tonne of
load adds ~m L/100km (trunk-haul trips, average speed ≥ 50 km/h).` The fully-laden point
projects to the **vehicle's own rated gross weight** (`full_laden_t` override, e.g. 40 t),
worded "(N t, the rated gross weight)". One temperature line (same sign-aware pattern,
"laden trunk-haul trips"), one **speed** line (`Average trip speed: fitted fuel consumption
is ~X L/100km at 30 km/h and ~Y L/100km at 70 km/h.`).

Page-1 Summary: (1) fleet-overview line (active days, km, ~km/day, litres, mean L/100km);
(2) **CO₂ line** — state the arithmetic inline so the partner can reproduce it:
`Tank-to-wheel CO₂ emissions over the period were ~X t CO₂e (total fuel × 2.58354 kg CO₂e
per litre), i.e. ~Y kg CO₂e per km.` Never attribute the factor to a source unless
confirmed — it is the operator-agreed briefing basis; (3) a **counter-basis line** when the
raw basis is in use: totals are cumulative-counter differences (trial end minus trial
start), so they include idling and any telematics outages (state the outage count and
approximate km/L). No charging/regen lines — those channels do not exist; the
data-availability note is not used for them (they are not applicable rather than
unreported; see `references/field-applicability.md`).

## Cleaning — PAGE 2 ONLY (page 1 is unfiltered)

> `compute()` returns **two** trip sets. `tr_all` = **every** driving leg → the **PAGE-1** operations
> dashboard is UNFILTERED (Active Days, Driving Legs, Median GVM, timeline and the distance/energy
> totals count every leg the vehicle drove, incl. < 3 km legs; no EP nulling). `tr` =
> the **cleaned PAGE-2 analysis set** below (figures / fits / conclusions only). The **OPERATING PERIOD
> label and the output directory naming stay keyed to the valid-trip (`tr`) span** so naming is stable.

- **Valid-trip filter** (`MIN_TRIP_KM` = 3 km): for **page 2**, drop driving legs with distance
  < 3 km (or missing) — too-short/residual legs with unreliable EP.
- **EP cleaning** (`EP_CLEAN_MIN/MAX` = 0.3 / 3): EP outside [0.3, 3] kWh/km is dropped from
  scatter / fit / conclusion stats (0.3 lower bound kills the spurious thousand-km range from
  too-short residual legs); the EP y-axis stays fixed 0–3.
- **SOC-quantisation guard — REMOVED (2026-07-02).** A `|SOC Change| ≤ 1 %` EP-nulling guard used
  to sit here: short trips whose energy the (old) generator re-derived from the coarse integer SOC
  came out at a spurious low EP (~0.7), forming an isolated low band on EP-vs-GVM (e.g. AV24LXJ at
  28–33 t). That was a **downstream workaround**; the ROOT CAUSE is now fixed in **`jolt_toolkit`
  ≥ 2.2.7** — the `_correct_effective_capacity` ±1σ step no longer overwrites reliable counter energy
  (MODE A), and capacity uses a ΔSOC-weighted aggregation. Short-trip EP is therefore correct at
  source (the AV24 trucks' `|ΔSOC| ≤ 1 %` legs now sit at a realistic ~1.17 kWh/km median, not 0.7),
  so the guard would only wrongly discard now-valid short-trip points — hence removed. Only the
  distance filter remains.
- The remaining filter is stated in the **page-2 footer footnote** (built from `MIN_TRIP_KM`):
  *"Figures exclude driving legs shorter than 3 km."* — shown on named and anon versions.
