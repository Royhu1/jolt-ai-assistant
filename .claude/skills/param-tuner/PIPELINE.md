# param-tuner — Pipeline

> Reads a vehicle's report + validation figures → diagnoses segmentation issues →
> adjusts pipeline parameters → re-validates → logs experience for next time.

**Invoke:** `/param-tuner <REG>` · **In:** `excel_report_database/<version>/<REG>/` +
`vehicles.json` / `pipelines.json` · **Out:** edited configs + `evaluations/{REG}_review_results.md`
+ `references/{reg}.md`

## Flow

0. **Prior experience** — read `references/{reg}.md` (similar-vehicle case studies) and any
   existing `evaluations/{REG}_review_results.md` (known remaining issues).
1. **Locate + select** — read the vehicle's pipeline params and report dir; pick the review
   set by mode: **Quick** = stratified sample (≥ max(30% of trips, 30), all active +
   charge-only days), **Thorough** = all valid figures.
2. **Review** — inspect each validation figure across the 4 panels (discharge trips, mass
   clusters, charge events); record per-figure status in `evaluations/{REG}_review_results.md`,
   grouping issues by root cause.
3. **Propose** — the minimum set of parameter changes that fixes the most common issues, as a
   table (param, current, proposed, expected impact + trade-offs).
4. **Apply + revalidate** — edit configs → `pip install -e . -q` → regenerate with
   `--fast --debug` → re-check figures (Quick: ~10 key; Thorough: every flagged + correct day)
   → append a new Round to the evaluations log.
5. **Backfill** — once segmentation is confirmed, run `ChargerPatcher` + `LoggerPatcher`
   (never plain `--debug`, which would overwrite patched data).
6. **Finalise** — update the evaluations summary, save the `references/{reg}.md` case study,
   update the changelog, commit.

**Principle:** optimise *global* segmentation quality, not individual outliers; change one
parameter at a time. Parameters live per-vehicle in `pipelines.json` (changes don't affect
other vehicles). For outliers Quick can't fix → `/report-finetuner`.
