# generate-excel-report — JOLT report-generation CLI wrapper

> Drives the report-generation CLI (a thin wrapper) → `jolt_toolkit` fetches SRF
> telematics, segments it into trips/charges, and writes one `.xlsx` per period.
> This README is the skill's human-facing single source of truth; `SKILL.md` is the
> agent-facing router over `manifest.yaml`.

**Invoke:** `/generate-excel-report <REG> <period>` · **In:** SRF telematics (live API) ·
**Out:** `excel_report_database/<version>/<REG>/jolt_report_<REG>_<start>_<end>.xlsx`

## When to use

Use this skill when the user asks to:

- Generate / regenerate an Excel report for one vehicle and date range
- Batch-generate the standard test fleet
- Run `/generate-excel-report <REG> <period>`

## Directory map

```
generate-excel-report/
├── SKILL.md              # router: routing protocol only (agent entry point)
├── manifest.yaml         # always_load + mode axis + gates + on-demand reference table
├── README.md             # this file — human-facing map + pipeline
├── generate_report.py    # CLI: one vehicle + one period → one .xlsx
├── batch_generate.py     # CLI: whole-range quarter-split / standard test fleet
├── test_data_config.json # standard test-fleet date ranges (⚠️ hand-maintained ends can be stale)
├── patch_graphs_2_2_3.py # in-place Graphs-sheet re-chart tool (maintenance pass, no pipeline re-run)
├── static/
│   ├── core/             # conventions.md — always-loaded contracts (inputs, preconditions,
│   │                     #   output artefacts, weather/elevation cache-first)
│   └── fragments/mode/   # single.md | batch.md (exactly one loaded per run)
├── references/           # after-generating.md — mandatory post-run checklist
└── evaluations/          # per-run experience log
```

## Pipeline

1. **Confirm inputs** — registration, date range (inclusive `-ds`/`-de`), the active
   `jolt_toolkit.__version__`, and the output dir (defaults to the version sub-dir).
2. **Preconditions** — `.env` has `SRF_API_KEY`; the vehicle is configured in
   `vehicles.json` / `pipelines.json` (if not → hand off to `/vehicle-onboarding` first).
3. **Span** — a single period ≤ ~1 quarter calls `generate_report.py`; a longer range calls
   `batch_generate.py`, which auto-splits into one report per meteorological quarter
   (DJF/MAM/JJA/SON, inclusive-end, non-overlapping).
4. **Fetch + segment** — the CLI pulls SRF legs (telematics) + optionally SRF Logger / Charger;
   `jolt_toolkit` segments per the vehicle's pipeline params and computes KPIs (EP, SoC, mass,
   distance, energy).
5. **Write** — the `.xlsx` Report sheet; `--debug` also writes validation figures + raw CSV +
   inspect HTML, `--raw-only` writes raw + HTML without baked figures, `--fast` skips
   Logger/Charger (non-final only).
6. **Weather (separate post-step)** — `weather_patch` backfills temperature columns
   cache-first from OpenWeather; elevation needs no API (read from the GPS-altitude channel).
7. **Charger backfill (separate post-step, v2.2.8+)** — SRF charge-point transactions can
   arrive weeks after the telematics, so after a regen (and weekly via the
   data-collection-monitor sweep) run
   `python -m jolt_toolkit.report_generator.charger_patcher <version-dir> --persist-raw`
   — idempotent (fills only empty Charger Link cells) and merge-accumulates each vehicle's
   `raw_charger/charger_transactions.csv`.

## How to run

Single vehicle + single period (mode `single`; full flag docs in
`static/core/conventions.md`, command block in `static/fragments/mode/single.md`):

```bash
python .claude/skills/generate-excel-report/generate_report.py -veh YK73WFN -ds 2025-03-01 -de 2025-05-31
```

Long range (auto quarter-split) or the standard test fleet (mode `batch`; command
blocks in `static/fragments/mode/batch.md`):

```bash
python .claude/skills/generate-excel-report/batch_generate.py --veh YK73WFN --ds 2024-06-01 --de 2026-06-09
python .claude/skills/generate-excel-report/batch_generate.py            # whole fleet, test_data_config.json ranges
```

Every run then needs the post-run checklist in `references/after-generating.md` —
weather backfill is **required** (generation leaves the weather columns empty), and a
batch / full-fleet regen is only complete with weather + charger backfill + dashboard
refresh.

## Ownership and neighbours

- **Owner:** algorithms live in `jolt_toolkit` (route code changes to `jolt-toolkit-dev`); this
  skill only drives the CLI. **Next:** `/param-tuner`, `/report-finetuner`, `/plot-figure`,
  `/generate-pdf-report`.
- Produce JOLT `.xlsx` reports from SRF telematics. This skill is a thin driver over the
  report-generation CLI; the actual algorithms live in the `jolt_toolkit` package
  (owned by the `jolt-toolkit-dev` agent — route code changes there, not here).
- If the target vehicle is not yet configured, hand off to `/vehicle-onboarding` first.
