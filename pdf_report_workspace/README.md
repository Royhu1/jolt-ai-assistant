# pdf_report_workspace — briefing artefact store

**This directory holds only generated artefacts.** The production method (code, Jinja2
template, style references, commentary style guide, run instructions) lives in the
**`generate-pdf-report` skill**: `.claude/skills/generate-pdf-report/SKILL.md`.

To (re)generate a briefing, type in Claude Code:

```
/generate-pdf-report <REG> <yyyymmdd_yyyymmdd>
```

## Two page-1 KPI versions: raw vs `_xlsxkpi`

Each briefing can be produced in **two versions that differ only on page 1** (the page-2
analysis — EP/GVM scatters, range, temperature, conclusions — is **identical** in both, always
on the driving-leg basis). Choose with `--page1-basis {raw,segment}`:

| File | Page-1 totals basis |
|------|---------------------|
| `report_<REG>_<period>.pdf` (no suffix) | **raw** — Total Distance, Energy Used, Energy Recuperated and **Energy Charged** come from the `raw_telematics/` cumulative counters (`odometer`, `total_electric_energy_used`, `electric_energy_recuperation_watthours`, `battery_pack_dc/ac_watthours`). Whole-period sums → include non-driving consumption + the true odometer distance, and energy used reconciles with energy charged. |
| `report_<REG>_<period>_xlsxkpi.pdf` | **segment** — the same page-1 totals computed the old way: summed from the **xlsx report** (`jolt_report_*.xlsx`) driving-leg / charge-leg rows (hence "**xlsx kpi**"). The reference / comparison version. |

So **`_xlsxkpi` = "page-1 KPIs taken from the xlsx report (driving-leg segment basis)"**, kept
alongside the raw version for comparison. The raw basis is decided **per field** — a vehicle
that reports an odometer but no energy/charge counter (Scania/DAF/Mercedes) gets a raw Total
Distance but keeps the segment energy/charged. Full detail: the skill's `SKILL.md` §1.

## Contents (artefacts gitignored; the status table is committed)

```
pdf_report_workspace/
├── pdf_report_status.md              # per-trial briefing coverage table (operator, vehicle,
│                                     # reg, BYO/round-robin, period, PDF generated?) —
│                                     # committed; update after each briefing batch
├── pdf_report_status.xlsx            # operator-grouped spreadsheet version (+ Diesel
│                                     # comparator column, merged cells) — gitignored;
├── build_pdf_report_status.py        # rebuilds the xlsx AND the 0715 deck's two table
│                                     # slides from its GROUPS data (committed)
├── output_by_<YYYYMMDD>/             # FROZEN SNAPSHOT: the briefing set finalised on that
│                                     # date (e.g. output_by_20260710 = the 2.2.8 Round-1 set,
│                                     # frozen 2026-07-10) — do not regenerate into it
├── output_by_TBD/<REG>_<period>/     # WORKING SET for the next reporting round — the
│                                     # generator writes here; to finalise a round, rename
│                                     # the whole dir to output_by_<YYYYMMDD> and recreate
│                                     # an empty output_by_TBD (scheme since 2026-07-10).
│                                     # Per-briefing contents (either dir kind):
│   ├── report_<REG>_<period>.html/pdf         # RAW page-1 version (browser-viewable + PDF)
│   ├── report_<REG>_<period>_xlsxkpi.html/pdf # SEGMENT page-1 version (xlsx-report basis)
│   ├── report_anon_<period>.html/pdf # anonymised version (--anon: no operator/reg/source,
│   │                                 # label-free CARTO basemap) — safe to forward
│   ├── verification_<REG>_<period>.xlsx           # human-verification workbook (raw version)
│   ├── verification_<REG>_<period>_xlsxkpi.xlsx   # ditto for the segment version
│   │                                 # (Excel formulas independently recompute every number)
│   └── figures/, figures_anon/       # chart PNGs (run-token names bust browser cache)
└── cache/here_*.png              # HERE basemap tiles (keyed by centre/zoom/size,
                                  # reused across runs so re-runs work offline)
```

- If the canonical `report_*.pdf` is locked by a PDF viewer at generation time, a
  timestamped `report_*_<unixtime>.pdf` is written instead — close the viewer and
  regenerate to write back the canonical name.
- Safe to delete anything here; every artefact is reproducible from the skill +
  `excel_report_database/`.
