# Mode: revise — layout / chart / commentary changes to the briefing product

Use when the request is about how briefings **look or read** rather than producing a fresh
briefing for a new REG/period: applying partner review comments, rewording Conclusions /
Summary text, chart or layout spec changes, naming / statistics-basis changes. This skill
OWNS the briefing's layout and commentary style guide — revisions are handled here so the
subjective conclusions stay stylistically consistent across reports (see the frontmatter
description, trigger 4).

## Workflow

1. **Locate the governing rule first.** Every partner-facing convention already has a home:
   - layout / rendering / charts / route map → `static/core/layout-contract.md`
     (**finalised, do not revert** — check its retired schemes before changing anything);
   - Conclusions / Summary wording, load points, cleaning →
     `references/commentary-style.md`;
   - what a field may show ("—" vs 0, N/A rules) →
     `references/field-applicability.md`;
   - verification workbook / AI-side checks → `references/verification.md`.
   Read the relevant file before editing — a review comment may be asking for something
   that was deliberately retired (e.g. legends, ±1σ bands, dynamic `@page` height,
   the SOC-quantisation guard) and should be answered from the contract, not re-implemented.
2. **Apply the change in skill-owned code only**: `generate_pdf_report.py` / `build_pdf.py` /
   `templates/report_template.html.j2` / `briefing_vehicle_specs.json`. Per the discipline
   contract (`static/core/discipline.md`), never edit `src/jolt_toolkit/` — only a *new xlsx
   field / data source* is routed to `jolt-toolkit-dev`.
3. **Keep the knowledge current**: update the governing contract / reference file in the
   same change (the discipline contract requires all briefing knowledge to be recorded in
   this skill's files) — a deliberate style change edits the doc and the code together,
   never one without the other. If the change supersedes the finalised style, say so
   explicitly in the layout contract rather than leaving a silent divergence from
   `references/style_baseline_*.pdf`.
4. **Re-render every affected briefing** so the working set in
   `pdf_report_workspace/output_by_TBD/` stays consistent: follow the run instructions in
   `static/fragments/mode/generate.md` §3 for each affected `<REG>`/`<period>` (this is the
   one point where revise mode consults the generate fragment). A commentary/style change
   applies to ALL briefings that carry the affected text, not just the one the comment came
   from.
5. **Verify** per `references/verification.md` (mandatory after every generation),
   comparing against `references/style_baseline_*.pdf` — the authoritative style baseline
   new reports should match.
6. **Log the revision** in `evaluations/` (partner comment → decision → what changed →
   which briefings were re-rendered), per its README.
