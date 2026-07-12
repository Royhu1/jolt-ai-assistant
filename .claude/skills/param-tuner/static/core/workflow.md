# Tuning workflow (always load)

Systematically review validation figures for a vehicle, diagnose segmentation
issues, and adjust algorithm parameters to produce optimal trip/charging boundaries.
Follow steps 0–6 in order. Steps 2 and 5.4 are mode-specific and delegate their exact
scope to the loaded mode fragment (`static/fragments/mode/quick.md` or
`static/fragments/mode/thorough.md`).

## 0. Check prior experience

Before starting:

1. Read `references/` for case studies of previously tuned vehicles.
   If the target vehicle shares characteristics (same make, similar operation pattern,
   similar data availability), use the prior case study to inform initial expectations
   and parameter starting points.
2. Read `evaluations/{REG}_review_results.md` if it exists — it contains prior review
   results and known remaining issues from previous optimization sessions.

## 1. Locate data

- Identify the vehicle registration from user input
- Read `src/jolt_toolkit/configs/vehicles.json` to get the vehicle's pipeline and parameters
- Read `src/jolt_toolkit/configs/pipelines.json` to get the current pipeline parameters
- Find the report directory: `excel_report_database/{version}/{reg}/`
- Read the Excel report to extract dates that have discharge trip data
- Count total validation figures available

## 2. Select review set

Mode-specific — apply the loaded mode fragment's "Review-set selection":
**Thorough** reviews all validation figures; **Quick** builds a stratified sample
(≥ max(30% of trips, 30) figures — full algorithm in `static/fragments/mode/quick.md`).

## 3. Review validation figures

For each figure in the review set, evaluate across all four panels using the criteria
in `references/evaluation-criteria.md`. **Record results in
`evaluations/{REG}_review_results.md`** (create if not exists, append new round if
exists). See `references/record-format.md` for the evaluation record format.

**Efficiency tips**:

- After reviewing ~10 active days, check if a dominant pattern has emerged.
  If >70% of issues share the same root cause, note this early hypothesis
  but continue reviewing to confirm.
- For idle days, batch-review quickly: confirm 0 segments detected, flag
  any false positives immediately.

## 4. Diagnose and recommend

After reviewing, summarize findings and propose parameter changes.
Present changes as a table: parameter, current value, proposed value, reason.

## 5. Apply and verify

1. Edit the config file(s)
2. Reinstall: `pip install -e . -q`
3. **Fast validation** — first use `--fast --debug` to quickly check segmentation quality
   (telematics data only):
   ```bash
   python .claude/skills/generate-excel-report/batch_generate.py --debug --fast --veh {reg}
   ```
4. Re-check validation figures per the loaded mode fragment's "Re-check scope"
   (Quick: an ~10-figure spot-check; Thorough: a full re-check — exact scope in the
   fragment)
5. **Update `evaluations/{REG}_review_results.md`**: add a new round section recording
   each re-checked figure's status (resolved / still problematic / newly broken).
   Update the summary table at the top of the file.
6. **Backfill via patchers** — once segmentation is verified, backfill Logger/Charger data
   per the full statement (patcher snippet + never plain `--debug` warning) in
   `static/core/principles.md`, Phase 3 step 11.

## 6. Finalize

1. **Create or update case study**: save optimization summary to
   `references/{reg}.md` in this skill's directory (structure in
   `references/record-format.md`, "Case study reference files")
2. **Ensure `evaluations/{REG}_review_results.md` is up to date**: the summary table
   should reflect the final state — which figures are OK, which still have issues.
   This file persists across sessions for future re-optimization.
3. Update `changelogs/changelog_YYYYMMDD_YYYYMMDD.md` (the current week's file)
4. Commit changes
