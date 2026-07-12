# Mode: batch — quarter-split ranges / standard test fleet (`batch_generate.py`)

Use when the user asks for the standard test-vehicle set, multiple vehicles, or a
whole-range / longer-than-a-quarter span that must be auto-split into one report per
meteorological quarter (the span convention lives in `static/core/conventions.md`).

Single vehicle, long range → auto-split into one report per meteorological quarter (default):

```bash
# whole range for one vehicle, meteorological-quarter reports (the default span, inclusive end)
python .claude/skills/generate-excel-report/batch_generate.py --veh YK73WFN --ds 2024-06-01 --de 2026-06-09
# equal-length escape hatch (e.g. monthly) or a forced output dir
python .claude/skills/generate-excel-report/batch_generate.py --veh YK73WFN --ds 2024-06-01 --de 2025-12-01 --months 1 --out-dir ./excel_report_database/2.2.8
# raw-only (fast) batch regenerate; figures re-drawn later by the overlay regenerate step
python .claude/skills/generate-excel-report/batch_generate.py --raw-only
```

The split helper is `batch_generate.split_into_periods(date_start, date_end, months=None)`
— `months=None` (default) splits into meteorological quarters (DJF/MAM/JJA/SON) with
**inclusive-end, non-overlapping** periods (first clipped to `date_start`, last to
`date_end`); `months=N` is an equal-length N-month escape hatch (also inclusive-end).

Batch (standard test fleet + date ranges from `test_data_config.json`):

```bash
python .claude/skills/generate-excel-report/batch_generate.py            # whole fleet
python .claude/skills/generate-excel-report/batch_generate.py --veh YK73WFN  # one configured vehicle
```

Remember the ⚠️ from `static/core/conventions.md`: `test_data_config.json` end dates are
hand-maintained and can be stale — for "up to now" runs derive `--de` from today instead.
After the batch finishes, follow `references/after-generating.md` — a batch / full-fleet
regen is NOT complete without the weather backfill (every vehicle dir), the charger
backfill sweep and the dashboard refresh listed there.
