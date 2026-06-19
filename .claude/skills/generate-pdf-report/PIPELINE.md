# generate-pdf-report — Pipeline

> Reads xlsx pipeline artefacts → computes KPIs + load-point conclusions → renders figures +
> HERE route map → fills a Jinja2 template → prints a two-page A4 PDF briefing with headless Chrome.

**Invoke:** `/generate-pdf-report <REG> <period>` · **In:**
`excel_report_database/<ver>/<REG>/` (xlsx + `raw_telematics/`) · **Out:**
`pdf_report_workspace/output/<REG>_<op_period>/` (HTML + PDF + figures + verification xlsx)

## Flow

1. **Locate source xlsx** — exact period if present, else the most compact report whose
   `[start,end]` covers the window, clipped to the window by Start Time (prefer `_finetuned`).
2. **Resolve metadata** — operator (`_resolve_operator` via `plot_config.json` simple /
   round-robin), battery capacity + OEM + model (from `vehicles.json` / `plot_config.json`).
3. **Compute KPIs + load points** — valid-trip filter (distance ≥ 3 km, EP ∈ [0.3, 3]); regen
   from the `raw_telematics` cumulative counter (`build_interp`/`delta`), not the sparse xlsx
   column; OPERATING PERIOD = real span of valid trips. Resolve unladen / laden masses
   (`_compute_load_points`: band / single-group / legacy-tertile / KDE, see SKILL §5) and the
   unladen/laden/42-t EP & range (±1σ) for the Conclusions.
4. **Render** — two A4-portrait pages. Page 1: ops dashboard (timeline, stat cards, route map —
   HERE basemap, CARTO no-labels for `--anon`) + plain-English **Summary**. Page 2: a **2×2 grid
   of square charts** (EP-vs-GVM, Range-vs-GVM, EP-vs-temp on the laden cluster, charge-start SoC)
   with shared aligned axes, no legend/±1σ band, Unladen/Laden/Full load markers + dashed fit to
   42 t; below them a plain-English **Conclusions** block.
5. **Template → PDF** — Jinja2 HTML at fixed A4 size, then headless Chrome prints it.
   `--anon` produces a registration-free, operator-masked variant alongside the named one.
6. **Verify** — emit `verification_*.xlsx` (every briefing number recomputed via native Excel
   formulas, mismatches flagged FAIL) + a field-applicability audit; AI-side screenshot/PDF
   checks against the style baseline.

**Owner:** self-contained — layout, charts, commentary style and generator code all live in
this skill; only route to `jolt-toolkit-dev` if a *new xlsx field* is needed. Artefacts are
gitignored. **Prereq:** if no covering xlsx exists → `/generate-excel-report` first.
