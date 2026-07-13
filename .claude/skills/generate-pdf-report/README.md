# generate-pdf-report — industrial-partner PDF/HTML briefing

> Reads xlsx pipeline artefacts → computes KPIs + load-point conclusions → renders figures +
> HERE route map → fills a Jinja2 template → prints a two-page A4 PDF briefing with headless
> Chrome. This README is the skill's human-facing single source of truth; `SKILL.md` is the
> agent-facing router over `manifest.yaml`.

**Invoke:** `/generate-pdf-report <REG> <period>` · **In:**
`excel_report_database/<ver>/<REG>/` (xlsx + `raw_telematics/`) · **Out:**
`pdf_report_workspace/output_by_TBD/<REG>_<OPERATOR>_<op_period>/` (working set; frozen as
`output_by_<YYYYMMDD>/` on finalisation) (HTML + PDF + figures + verification xlsx)

## What it is

Turn JOLT fleet-analysis results into a **one-page, dashboard-style briefing** (HTML + PDF)
delivered to industrial partners (fleet operators, OEMs). Kept strictly separate from
`publication_workspace/` (academic papers): this is a visual, easy-to-read results snapshot.
The layout derives from the EVITA Round Robin 1 Case Study under `references/`.

This skill owns both **generation** and **maintenance** (changing charts/layout/commentary,
applying review comments). It is the single authoritative source for how the briefing is
produced; `pdf_report_workspace/` only holds the artefacts.

## Directory map

```
generate-pdf-report/
├── SKILL.md                      # router: routing protocol only (agent entry point)
├── manifest.yaml                 # always_load + mode axis + gates + on-demand reference table
├── README.md                     # this file — human-facing map + pipeline
├── generate_pdf_report.py        # the generator CLI: xlsx → KPIs, figures, route map, context
├── build_pdf.py                  # Jinja2 render + headless-Chrome PDF printing
├── templates/
│   └── report_template.html.j2   # the two-page A4 HTML template
├── briefing_vehicle_specs.json   # per-vehicle unladen-band / mass overrides (AI-judged artic bands)
├── static/
│   ├── core/                     # layout-contract.md + discipline.md (always loaded)
│   └── fragments/mode/           # generate.md | revise.md (exactly one loaded per run)
├── references/                   # on-demand knowledge + LOCAL PDF style exemplars
│   ├── commentary-style.md       # Conclusions & Summary methodology (git-tracked)
│   ├── field-applicability.md    # do-not-fabricate-N/A rules (git-tracked)
│   ├── verification.md           # post-generation verification (git-tracked)
│   ├── EVITA Round Robin 1 Case Study PDF.pdf            (gitignored, local only)
│   └── style_baseline_YK73WFN_20250306_20250522.pdf      (gitignored, local only)
└── evaluations/                  # per-run experience log
```

> **Note on `references/`**: the markdown knowledge files are git-tracked and travel with
> the skill; only the two local PDFs (external copyrighted case study + regenerable
> style-baseline snapshot) are gitignored (`references/*.pdf` in the root `.gitignore`)
> and never pushed.

### Style references (`references/`)

- `EVITA Round Robin 1 Case Study PDF.pdf` — the source of the layout.
- `style_baseline_YK73WFN_20250306_20250522.pdf` — a finished snapshot of the current
  finalised style (the version after the 2026-06-16 changes to fonts / axes-box alignment /
  clustering / valid-trip filter / operating-period naming); new reports should match its
  style. Note: `references/` are gitignored local files, not shared via git (local reference
  only).

## Pipeline

1. **Locate source xlsx** — exact period if present, else the most compact report whose
   `[start,end]` covers the window, clipped to the window by Start Time (prefer `_finetuned`).
2. **Resolve metadata** — operator (data-driven: the dominant per-leg `Operator` column in
   the report's data; `plot_config.json` `company_assignment` is no longer used — see
   `static/fragments/mode/generate.md` §1), battery capacity + OEM + model (from
   `vehicles.json` / `plot_config.json`).
3. **Compute KPIs + load points** — valid-trip filter (distance ≥ 3 km, EP ∈ [0.3, 3]); regen
   from the `raw_telematics` cumulative counter (`build_interp`/`delta`), not the sparse xlsx
   column; OPERATING PERIOD = real span of valid trips. Resolve unladen / laden masses
   (`_compute_load_points`: band / single-group / legacy-tertile / KDE, see
   `references/commentary-style.md`) and the unladen/laden/42-t EP & range (±1σ) for
   the Conclusions.
4. **Render** — two A4-portrait pages. Page 1: ops dashboard (timeline, stat cards, route map —
   HERE basemap, CARTO no-labels for `--anon`) + plain-English **Summary**. Page 2: a **2×2 grid
   of square charts** (EP-vs-GVM, Range-vs-GVM, EP-vs-temp on the laden cluster, charge-start SoC)
   with shared aligned axes, no legend/±1σ band, Unladen/Laden/Full load markers + dashed fit to
   42 t; below them a plain-English **Conclusions** block.
5. **Template → PDF** — Jinja2 HTML at fixed A4 size, then headless Chrome prints it.
   `--anon` produces a registration-free, operator-masked variant alongside the named one.
   **Variants (auto, no flag)**: no usable mass channel → the *distribution* variant
   (EP/range histograms); vehicles.json `fuel_type == "DIESEL"` (e.g. YT21EFD/WJF) → the
   *diesel-comparator* variant — Fuel Consumption (L/100km) analysis, page-1 totals from the
   raw VDHR/LFC cumulative counters (trial end − trial start), a TANK-TO-WHEEL EMISSIONS
   card (CO₂e = fuel × 2.58354 kg/L), and trunk-haul (≥ 50 km/h) mass/temperature figures —
   see `static/core/layout-contract.md`.
6. **Verify** — emit `verification_*.xlsx` (every briefing number recomputed via native Excel
   formulas, mismatches flagged FAIL) + a field-applicability audit; AI-side screenshot/PDF
   checks against the style baseline.

## How to run

```bash
# Run from the repo root (PYTHONUTF8=1 avoids the Windows cp1252 encoding crash)
PYTHONUTF8=1 python .claude/skills/generate-pdf-report/generate_pdf_report.py \
    --reg YK73WFN --period 20250301_20250601 [--version 2.2.8] [--base]
```

Full option semantics (`--all-data`, the automatic per-operator split +
`--min-operator-trips`, `--anon`, `--page1-basis {raw,segment}`), output naming and the
preconditions (covering xlsx, Chrome, weather backfill) live in
`static/fragments/mode/generate.md`. Prereq: if no covering xlsx exists →
`/generate-excel-report` first.

## Ownership and neighbours

**Owner:** self-contained — layout, charts, commentary style and generator code all live in
this skill; only route to `jolt-toolkit-dev` if a *new xlsx field* is needed. Artefacts are
gitignored. **Prereq:** if no covering xlsx exists → `/generate-excel-report` first.

- Chart-style boundary: **partner-briefing charts** (square, no legend / no ±1σ band)
  belong to this skill; **analysis figures** (10×6, legend, ±1σ band) belong to the
  `plot-figure` skill — route style requests accordingly.
- Full discipline text (data-source read-only boundary, `jolt_toolkit.analysis` read-only
  calls, no version bumps, changelog duty): `static/core/discipline.md` (always loaded).
- The `pdf-report-auditor` agent independently re-derives the briefing numbers from raw
  telematics + xlsx (read-only); generator fixes route back to this skill.

## To-do (ported from the original workspace README)

1. Logos: the title bar no longer carries any logo (the 3 dashed placeholder boxes were
   removed). If real logos are ever wanted, re-add an `<img src="logos/<operator>.png">`
   (operator / JOLT / OEM) into the `.ops-header` flex container in the template and drop
   the files under `references/logos/`.
2. Commercial-field interface: if the operator provides Monta cost/scheduling, add
   `--ops-data <json>` to merge into the context.
3. Units: currently km / kWh/km; add a switch for an imperial miles version if needed.
