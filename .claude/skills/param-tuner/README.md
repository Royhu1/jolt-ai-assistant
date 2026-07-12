# param-tuner — segmentation parameter tuning

> Reads a vehicle's report + validation figures → diagnoses segmentation issues →
> adjusts pipeline parameters → re-validates → logs experience for next time.
> This README is the skill's human-facing single source of truth; `SKILL.md` is the
> agent-facing router over `manifest.yaml`.

**Invoke:** `/param-tuner <REG>` · **In:** `excel_report_database/<version>/<REG>/` +
`vehicles.json` / `pipelines.json` · **Out:** edited configs + `evaluations/{REG}_review_results.md`
+ `references/{reg}.md`

## Directory map

```
param-tuner/
├── SKILL.md            # router: routing protocol only (agent entry point)
├── manifest.yaml       # always_load + mode axis + vehicle-data gate + on-demand reference table
├── README.md           # this file — human-facing map + pipeline
├── static/
│   ├── core/           # workflow.md (7-step tuning workflow) + principles.md
│   │                   #   (holistic optimization + evaluations-log key rules + guidelines) — always loaded
│   └── fragments/mode/ # quick.md | thorough.md (exactly one loaded per run)
├── references/         # evaluation-criteria / parameter-reference / record-format (skill docs)
│   └── <REG>.md        #   + optimisation case studies (per vehicle, written when done)
└── evaluations/        # validation-figure review log (per vehicle, updated each round)
    └── {REG}_review_results.md
```

- `references/<REG>.md` — post-optimisation lessons learned, for reference on future similar vehicles
- `evaluations/` — per-figure assessment log of each review, updated across iterations,
  recording which figures still have issues (13 vehicles logged so far; format in
  `references/record-format.md`, discipline in `static/core/principles.md`)

## Tuning modes

When starting, the skill presents both modes to the user — there is no silent default:

| Mode | Fragment | In one line |
|------|----------|-------------|
| **Quick** | [static/fragments/mode/quick.md](static/fragments/mode/quick.md) | Stratified sample (≥ max(30% of trips, 30) figures), one adjustment iteration, ~10-figure spot-check; for vehicles with known similar characteristics to a previously tuned vehicle. |
| **Thorough** | [static/fragments/mode/thorough.md](static/fragments/mode/thorough.md) | All valid figures, full day-by-day diagnosis table, multiple iterations until convergence, full re-checks; for first-time optimization or vehicles with unique data characteristics. |

## Pipeline

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
other vehicles). For outliers global parameters can't fix → `/report-finetuner`.

## How to run

- `/param-tuner <REG>` — or in natural language: "optimize parameters for <REG>",
  "tune segmentation for <REG>", "review validation figures for <REG>".
- Fast validation regeneration used inside the loop (telematics data only):

  ```bash
  python .claude/skills/generate-excel-report/batch_generate.py --debug --fast --veh <reg>
  ```

- After segmentation is verified, backfill Logger/Charger data via `ChargerPatcher` +
  `LoggerPatcher` (exact snippet in `static/core/principles.md`, Phase 3 step 11) — never
  plain `--debug`, which overwrites the backfilled data.

## Ownership and neighbours

- The tuning loop edits parameter **values** in `src/jolt_toolkit/configs/vehicles.json` /
  `pipelines.json` (workflow step 5.1). Algorithm / code changes under `src/jolt_toolkit/`
  (e.g. verifying `_recompute_anchors`, outlier filtering) belong to the `jolt-toolkit-dev`
  agent.
- New vehicles arrive via `/vehicle-onboarding`, which runs this skill after producing the
  first report.
- Individual outlier days that global parameters cannot fix route to `/report-finetuner`
  (post-processing `*_finetuned` artefacts) — never over-tune global parameters for them.
- Validation figures and reports come from the `generate-excel-report` batch CLI; reports
  live in `excel_report_database/<version>/<REG>/`.
