# Persistent record formats

This file defines the two persistent artefacts every tuning run writes: the per-vehicle
review log in `evaluations/` and the post-run case study in `references/`. **This is the
format the existing `evaluations/*_review_results.md` files follow** — match it when
creating or appending.

## Evaluation record format

`evaluations/{REG}_review_results.md` is the persistent review log for a vehicle.
It tracks every figure's status across multiple optimization rounds.

> The create/append/update discipline (key rules: when to create, appending rounds,
> keeping the Summary table current, the allowed Status / Type values, conciseness) is
> always-loaded contract material in `static/core/principles.md`
> ("Evaluations-log key rules").

> **Figure naming**: since v2.2.6 validation figures are per-day
> `validation_<REG>_<YYYY-MM-DD>.png` (with a `.boxes.json` sidecar); legacy per-leg
> `validation_<REG>_<date>_<NNNN>.png` files still exist for some vehicles (e.g. AV24LXJ),
> so both schemes may appear in older logs.

### File structure

```markdown
# {REG} — Validation Figure Review Results

> Pipeline: {pipeline_name} | Last reviewed: {date}

## Summary

| Status | Count | Percentage |
|--------|-------|------------|
| OK | — | — |
| Issue | — | — |
| Not reviewed | — | — |
| **Total** | — | — |

### Known remaining issues

- {brief list of unresolved problems, grouped by root cause}

---

## Round 1 — Initial review ({date})

Parameters: {current parameter snapshot}

### Per-figure results

| Figure | Type | Status | Issue | Root cause |
|--------|------|--------|-------|------------|
| validation_{REG}_2025-06-01.png | Active | OK | — | — |
| validation_{REG}_2025-06-02.png | Active | Issue | Over-segmentation: 1 trip split into 3 | min_stop_duration_min too small |
| ... | ... | ... | ... | ... |

### Round 1 summary

- Reviewed: N figures
- OK: X, Issue: Y
- Dominant pattern: {description}
- Proposed changes: {brief}

---

## Round 2 — After parameter adjustment ({date})

Parameters changed: {what changed}

### Re-checked figures

| Figure | Previous | Current | Notes |
|--------|----------|---------|-------|
| validation_{REG}_2025-06-02.png | Issue | **Resolved** | Now correctly 1 trip |
| validation_{REG}_2025-06-05.png | OK | OK | No regression |
| validation_{REG}_2025-06-08.png | OK | **New issue** | ... |
| ... | ... | ... | ... |

### Round 2 summary

- Resolved: X issues
- New issues: Y
- Still problematic: Z
```

## Case study reference files

After each optimization, save a summary to `references/{reg}.md` containing:

1. **Vehicle characteristics**: make/model, capacity, operation pattern, data availability
2. **Root causes found**: what was wrong and why
3. **Parameter changes**: before/after table with reasoning
4. **Results**: improvement summary
5. **Lessons learned**: generalizable insights for similar vehicles

Read relevant case studies at the start of each new optimization to leverage
prior experience. For example, if tuning a new Mercedes vehicle, read `references/YN25RSY.md`
first to understand Mercedes-specific data quirks.

> The per-vehicle case studies sit alongside this file and the other reference docs in
> `references/` — uppercase `<REG>.md` = case study, kebab-case `*.md` = skill reference.
