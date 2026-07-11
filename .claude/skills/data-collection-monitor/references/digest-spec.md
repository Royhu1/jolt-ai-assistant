# Artefacts: digest PDF/HTML + MONITOR_STATUS.md (spec)

`data_collection_reports/` (gitignored, artefacts not committed):
- `data_collection_digest_<YYYYMMDD>_<YYYYMMDD>.pdf` + same-name `.html` (one whole-fleet
  digest per trigger).
- `MONITOR_STATUS.md` (loop cadence / last / next / per-vehicle summary — see
  `references/loop-usage.md`).

PDF content: **a single "whole-fleet data-collection overview table"** (no summary cards, no
per-vehicle detail sections; title bar centred, the time range in red). One row per vehicle,
14 columns: **Vehicle / Operator / Make-Model / Energy type (EV·Diesel) / Telematics data /
SRF logger / Charger data / Trips / Charges / Active days / Distance (km) / Latest telematics /
Latest SRF logger / Latest charger**.
- *Telematics data* / *SRF logger* = the number of legs **within the window** supported by SRF
  FPS telematics / SRF logger respectively (count of non-empty `Telematics Link` / `SRF Logger
  Link` in the Report sheet); *Charger data* = the number of charge-point transactions in the
  window (rows of `raw_charger/charger_transactions.csv` whose `start_time` falls in the window).
- *Latest telematics* / *Latest SRF logger* / *Latest charger* = the **most recent data time
  across the whole database** for that source (newest files scanned first): **green** = falls
  within this window, **amber** = the last time was before the window (possibly long ago),
  **grey "—"** = that source has never been collected.
- *Energy type* is taken from vehicles.json `fuel_type` (DIESEL → Diesel, otherwise EV);
  *Operator* is taken from `plot_config.json` `company_assignment` (incl. `round_robin` matched
  by date range against the window-end day).
- Layout: font sizes are **3×** the base version, so a large landscape canvas (≈720×450 mm,
  with left/right margins) is used so the 14 columns do not wrap and the whole fleet fits
  (a digital PDF, mainly for on-screen reading, header repeated per page, some columns centred).
