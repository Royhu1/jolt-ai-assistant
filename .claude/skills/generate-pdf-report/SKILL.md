---
name: generate-pdf-report
description: |
  Generate the industrial-partner one-page PDF/HTML briefing for a vehicle + period
  from the JOLT xlsx pipeline artefacts (excel_report_database/<ver>/<REG>/), by running
  generate_pdf_report.py (KPIs + matplotlib figures + HERE route map + Jinja2 template
  + headless-Chrome PDF). Output goes to pdf_report_workspace/output_by_TBD/<REG>_<OPERATOR>_<period>/ (the working set; finalised sets are frozen as output_by_<YYYYMMDD>/).
  This skill OWNS the briefing's layout and commentary style guide — also use it for
  chart/layout changes, commentary rewording, and applying partner review comments,
  so the subjective conclusions stay stylistically consistent across reports.
  Triggers on:
  (1) "generate the PDF briefing/report for <REG> in <period>"
  (2) "generate the PDF briefing / industrial-partner report for <REG>"
  (3) "/generate-pdf-report <REG> <period>"
  (4) partner review comments on a briefing; briefing chart / layout / commentary changes
  If no xlsx for the requested period exists — neither an exact-period report nor a
  broader one whose [start,end] covers the window — hand off to /generate-excel-report first.
---

# generate-pdf-report — Router

This skill is split into two layers (pattern adapted from nature-skills/nature-figure):

- A **static layer** under `static/` holding versioned, reusable content fragments: the
  layout/rendering contract, the discipline & ownership contract, a per-mode quick-start,
  and the on-demand commentary / field-applicability / verification references.
- A **dynamic layer** (this file plus `manifest.yaml`) that resolves the run's mode and
  loads only the fragment needed for the current job.

Do not generate or revise a briefing from memory or from this router alone. Always load
the fragments from disk as described below. **The rendered output is contract-fixed**: two
A4-portrait pages matching `references/style_baseline_*.pdf` — this refactor changes how
the skill is organised, never what the briefing looks like.

## Routing protocol

Follow these five steps every time the skill is invoked.

### 1. Load the manifest and the core layer

Read [manifest.yaml](manifest.yaml). It declares the `mode` axis, the blocking gates and
the on-demand reference table.

Also read every file listed under `always_load`:
[static/core/layout-contract.md](static/core/layout-contract.md) (the finalised two-page
A4 layout and rendering conventions — do not revert) and
[static/core/discipline.md](static/core/discipline.md) (self-contained ownership, the
read-only data-source boundary, version/changelog duties). These apply to every run.

### 2. Check the blocking gates

Per the manifest: the source xlsx must exist (exact-period, or a wider report whose
`[start,end]` covers the window — else hand off to `/generate-excel-report` first);
Chrome/Edge must be available for headless PDF rendering; and the report's temperature
column must hold real values (not the LoggerPatcher placeholder 0), else backfill weather
first. Full precondition text (incl. the weather-patch commands and the optional
`HERE_API_KEY`): [static/fragments/mode/generate.md](static/fragments/mode/generate.md) §2.

### 3. Resolve the mode and load the matching fragment

- **`generate` (DEFAULT)** — produce a briefing for a `<REG>` + `<period>`, including
  `--all-data`, the automatic per-operator split, `--anon` and `--page1-basis` runs.
  → Read [static/fragments/mode/generate.md](static/fragments/mode/generate.md).
- **`revise`** — change how briefings look or read: chart/layout changes, commentary
  rewording, applying partner review comments to existing briefings.
  → Read [static/fragments/mode/revise.md](static/fragments/mode/revise.md).

Do not load the other mode's fragment (exception: revise mode ends by re-rendering the
affected briefings and at that point follows the generate fragment's §3 run instructions).

### 4. Build using the loaded material

Apply in this order: layout contract (fixed pages / parameterised axes / load markers,
exactly) → discipline contract (ownership + data-source boundary) → the mode fragment's
workflow. Commentary is never freestyled: whenever Conclusions / Summary text is produced
or changed, or a load-point band judgement is made, load
[references/commentary-style.md](references/commentary-style.md) first.

### 5. Reach for references on demand — verification is mandatory

Open files under `references/` per the manifest table:
[commentary-style.md](references/commentary-style.md) for the Conclusions/Summary
style + `_compute_load_points` judgement + the PAGE-2-ONLY cleaning rules,
[field-applicability.md](references/field-applicability.md) before deciding any
field is N/A ("—" not 0, never fabricate), and
[verification.md](references/verification.md) **after every generation run — its
AI-side checks are mandatory**, and each run ships a `verification_*.xlsx` workbook for
the human verifier.

Log reusable lessons (partner comments applied, layout decisions, per-vehicle quirks) in
`evaluations/` per its README.

## Why this split

- The layout contract ("finalised, do not revert") and the ownership discipline are the two
  rules that must never drift — they are the two that always load, no longer buried in the
  middle of a 475-line SKILL.md.
- Each invocation stays cheap: only the selected mode's quick-start enters context, and the
  commentary / applicability / verification depth loads only when that step needs it.
- The router itself is short on purpose. Update fragments and references, not this file,
  when adding scope.
- This structure mirrors nature-figure's static/dynamic split, adapted to the JOLT skill
  anatomy v2 (`README.md` + `manifest.yaml` + on-demand references + `evaluations/` per
  `.claude/rules/skill-design.md`); the human-facing map + pipeline live in
  [README.md](README.md). `references/` holds both the git-tracked markdown knowledge and
  the two gitignored local PDF style exemplars (`references/*.pdf` in the root
  `.gitignore`) — see the README's directory map.
