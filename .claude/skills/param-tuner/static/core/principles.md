# Core principle: holistic optimization (always load)

Parameter tuning must optimize **global** segmentation quality, not fix individual outliers at the
expense of overall accuracy. Follow this process strictly:

## Phase 1 — Audit (review set depends on mode)

1. Review validation figures per the selected mode's sampling strategy.
2. **Create `evaluations/{REG}_review_results.md`** (or append Round N if exists).
   Record per-figure results: figure name, type, status, issue description, root cause.
3. After reviewing, **summarize recurring patterns** — group issues by root cause rather
   than treating each individually. Update the Summary table and Known remaining issues.

## Phase 2 — Propose changes

4. Identify the **minimum set of parameter changes** that addresses the most common issues.
5. Present the proposal as a table (parameter, current, proposed, expected impact).
6. Explicitly note any trade-offs: "increasing X will fix A but may worsen B".

## Phase 3 — Apply and validate

7. Apply changes (no reinstall — the workspace runs from source, so config edits take
   effect on the next run).
8. **Fast validation**: `python .claude/skills/generate-excel-report/batch_generate.py --debug --fast --veh {reg}` — quickly check segmentation using telematics data only.
9. Re-check validation figures per the loaded mode fragment's "Re-check scope"
   (`static/fragments/mode/quick.md` / `thorough.md`).
10. **Append new Round to `evaluations/{REG}_review_results.md`**: record each re-checked
    figure's updated status (Resolved / still Issue / New issue). Update the Summary table.
11. **Backfill via patchers** — once segmentation is confirmed, backfill Logger/Charger data
    with the patchers (avoids `--fast` overwriting existing data):
    ```python
    from jolt_toolkit.report_generator.charger_patcher import ChargerPatcher
    from jolt_toolkit.report_generator.logger_patcher import LoggerPatcher
    ChargerPatcher().patch_folder("excel_report_database/{version}/{reg}/")
    LoggerPatcher().patch_folder("excel_report_database/{version}/{reg}/")
    ```
    > **Important**: do NOT regenerate with `batch_generate.py --debug` (without `--fast`)
    > directly — that overwrites the Logger/Charger data already backfilled by the patchers.
    > Correct flow: `--fast --debug` to validate → patcher backfill.
    This is the single full statement of the validation/backfill command discipline;
    workflow step 5.5 and the guideline below point here.

## Phase 4 — Finalize

10. If satisfactory, update documentation:
    - `evaluations/{REG}_review_results.md` — ensure Summary table reflects final state
    - `references/{reg}.md` — save case study for future reference
    - `changelogs/changelog_YYYYMMDD_YYYYMMDD.md` — record optimisation results (the current week's file)
11. Commit changes and present results for user review.

---

## Evaluations-log key rules

These rules govern the persistent review log `evaluations/{REG}_review_results.md` on
every run (its file-structure template lives in `references/record-format.md`):

1. **Create on first review**: create the file during Step 3 of the first round
2. **Append new rounds**: each subsequent review (Step 5) adds a new `## Round N` section
3. **Always update the Summary table**: after each round, recalculate the top-level summary
   to reflect current state across all figures
4. **Update "Known remaining issues"**: after each round, list issues that persist
5. **Status values**: `OK`, `Issue`, `Resolved`, `New issue`, `Not reviewed`
6. **Type values**: `Active` (has discharge trips), `Charge-only`, `Idle`
7. **Keep it concise**: one row per figure, issue description in ≤15 words

---

## Guidelines

- Adjust one parameter at a time; verify effect before changing another
- Review multiple days (not just one) to avoid overfitting to a single day
- Different vehicles may need different parameters due to different operation patterns
- Each vehicle has its own pipeline in pipelines.json; changes to one vehicle's pipeline do not affect others
- Validation/backfill command discipline (`--fast --debug` to validate → patcher backfill,
  never plain `--debug`): full statement in Phase 3 step 11 above
- Isolated wrongly-segmented days that a GLOBAL parameter change cannot fix (without
  regressing correct days) are NOT a tuning problem: stop and hand off to
  `/report-finetuner` (per-leg xlsx post-processing). Do not over-tune global parameters
  to chase single outlier days.
- Check `references/` for prior experience with similar vehicles before starting
