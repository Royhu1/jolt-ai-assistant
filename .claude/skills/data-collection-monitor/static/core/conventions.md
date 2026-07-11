# Behaviour conventions + discipline (always load)

Contract-grade rules that apply to every run of this skill. The first convention —
**append-only, never overwrite** — is THE contract of this skill.

## Behaviour conventions (finalised)

- **Append-only, never overwrite**: generate only for the gap after `last_covered`; skip if the
  target period file already exists. Historical reports / raw data (incl. `raw_telematics/`)
  are never rewritten. This naturally produces "weekly incremental slice" files within the
  current quarter (e.g. `..._20260610_20260615.xlsx`) that do not overlap the historical
  quarter files, so the dashboard does not double-count.
- **Dynamic version**: defaults to `jolt_toolkit.__version__`; merged into the main database
  `excel_report_database/<version>/`, refreshing the main dashboard — new data is reflected
  directly in the main database and main dashboard you use daily.
- **No validation figures** (`save_figures=False`); by default writes raw CSV + inspect HTML
  (for human drill-down checks; `--no-raw` skips them for speed). Collection-volume stats
  (telematics / SRF logger leg counts) are taken from the xlsx `Telematics Link` / `SRF Logger
  Link` columns, not dependent on raw files.
- Failure isolation: a single vehicle's generation failure only records `ERROR` for that
  vehicle and does not interrupt the whole-fleet check.
- **Charger backfill sweep (v2.2.8+)**: SRF charge-point transactions can be uploaded
  days/weeks after the vehicle telematics, and report generation only fuses what exists at
  generation time — so each run first sweeps ALL existing reports of the watched version with
  `python -m jolt_toolkit.report_generator.charger_patcher <db_root> --persist-raw`
  (idempotent: only empty `Charger Link` cells are filled; `raw_charger/
  charger_transactions.csv` is merge-accumulated per vehicle — the very file the digest's
  Charger columns and the dashboard raw base read). Disable with `--no-charger-sweep`. This
  is the ONLY sanctioned in-place update to existing reports (it appends previously-missing
  charger facts; it never alters energies or segmentation).

## Discipline

- **Do not change any code / config in `src/jolt_toolkit/`** (jolt-toolkit-dev's territory);
  this skill only orchestrates the existing `JOLTReportGenerator` and dashboard CLI. To change
  report-generation logic → raise a request to jolt-toolkit-dev.
- **Do not bump the version number** (the check is a routine refresh); artefacts not committed
  to git (the skill itself is shared via git).
- Append a Q&A record to `changelogs/changelog_<Monday>_<Sunday>.md` at the end of the
  conversation.
- HTML→PDF uses this machine's headless Chrome/Edge (`build_digest_pdf.py`, vendored from
  generate-pdf-report's `build_pdf.py`, zero extra dependencies).
