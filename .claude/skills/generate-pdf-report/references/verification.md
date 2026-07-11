# Post-generation verification

**AI side (mandatory on every generation)**:

1. Render each PDF page to PNG with PyMuPDF (`doc[i].get_pixmap(dpi=150)`), confirm **two
   A4-portrait pages** (595×842 pt = 210×297 mm) and that no content is clipped (page-1 Summary +
   footer present; page-2 Conclusions + footer present with a bottom margin).
2. Inspect region by region: page-1 cards/summary fill the page without large empty bands; the
   page-2 2×2 chart **boxes are top/bottom aligned**, load markers don't overlap, titles aren't
   clipped.
3. Cross-check the Conclusions / Summary numbers against the figures (slope sign, the load-point
   values vs the markers, sanity of unladen < laden < full).
4. Compare against `references/style_baseline_*.pdf` (the authoritative style baseline).

**Manual verification (before external delivery, done by a human)**: each generation
automatically ships a `verification_<REG>_<period>.xlsx` verification workbook —

- The leg sheets copied from the canonical xlsx are the self-contained data basis, split to match
  the two-page filtering: **`Trips`** = the cleaned page-2 analysis legs (≥ 3 km, EP-cleaned; the
  old SOC-quantisation guard was removed 2026-07-02, see the Cleaning section in
  `references/commentary-style.md`) — page-2 EP/GVM formulas run over it; **`AllTrips`** + the all-legs **`Daily`** =
  every driving leg — the UNFILTERED page-1 counts/totals recompute over it. `Charges` = charge legs;
- The `Audit` sheet lists **every number that appears in the briefing**, one per row (~46
  items), and recomputes each from the raw legs on the fly using **native Excel formulas**
  (SUM/MEDIAN/AVERAGEIFS/SLOPE/RSQ/PERCENTILE…) — an independent computation path from the
  generator's pandas, so any mismatch is automatically flagged red **FAIL**;
- The verifier opens the workbook: review FAIL items → spot-check PASS items → complete CHECK
  MANUALLY items (timeline median, battery capacity vs vehicles.json, reciprocal-fit R² vs the
  legend) → fill in the Verified by / Date / Notes columns for the record.
- Note: openpyxl writing Excel 2010+ new functions needs the `_xlfn.` prefix; the workbook
  uses compatible forms throughout (e.g. `PERCENTILE` rather than `PERCENTILE.INC`, same
  interpolation).
