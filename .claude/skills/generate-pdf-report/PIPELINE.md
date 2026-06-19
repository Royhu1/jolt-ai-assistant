# generate-pdf-report — Pipeline

> Reads xlsx pipeline artefacts → computes KPIs → renders figures + HERE route map →
> fills a Jinja2 template → prints a one-page PDF briefing with headless Chrome.

**Invoke:** `/generate-pdf-report <REG> <period>` · **In:**
`excel_report_database/<ver>/<REG>/` (xlsx + `raw_telematics/`) · **Out:**
`pdf_report_workspace/output/<REG>_<op_period>/` (HTML + PDF + figures + verification xlsx)

## Flow

1. **Locate source xlsx** — exact period if present, else the most compact report whose
   `[start,end]` covers the window, clipped to the window by Start Time (prefer `_finetuned`).
2. **Resolve metadata** — operator (`_resolve_operator` via `plot_config.json` simple /
   round-robin), battery capacity + OEM + model (from `vehicles.json` / `plot_config.json`).
3. **Compute KPIs** — apply the valid-trip filter (distance ≥ 3 km, EP ∈ [0.3, 3]); regen
   from the `raw_telematics` cumulative counter (`build_interp`/`delta`), not the sparse xlsx
   column. The OPERATING PERIOD = the real span of valid trips.
4. **Render** — 5 page-2 figures (EP-vs-GVM, Range-vs-GVM, EP-vs-temp, daily energy, charge
   start SoC) on parameterised/pinned axes, each with a fixed-structure commentary box; plus
   the route map (HERE basemap, or CARTO no-labels for `--anon`).
5. **Template → PDF** — Jinja2 HTML, then headless Chrome prints it (PDF = HTML preview).
   `--anon` produces a registration-free, operator-masked variant alongside the named one.
6. **Verify** — emit `verification_*.xlsx` (every briefing number recomputed via native Excel
   formulas, mismatches flagged FAIL) + a field-applicability audit; AI-side screenshot/PDF
   checks against the style baseline.

**Owner:** self-contained — layout, charts, commentary style and generator code all live in
this skill; only route to `jolt-toolkit-dev` if a *new xlsx field* is needed. Artefacts are
gitignored. **Prereq:** if no covering xlsx exists → `/generate-excel-report` first.
