# Field applicability (do not fabricate N/A fields)

Load this file before deciding whether any briefing field is real pipeline data, partially
available, or N/A.

| Category | Fields |
|------|------|
| ✅ Real pipeline data | active days, trip/charge segment counts, total distance, mean/max daily distance, total energy, average EP, regen recovered kWh, AC/DC charging, start/end SoC, average GVM, EP-vs-GVM, Range-vs-GVM, EP-vs-temperature (laden cluster), SoC distribution, route (lat/lon) |
| ⚠️ Partially available | regen recovery (**EVs with a counter (Volvo/Renault) now use the raw_telematics counter for full coverage**, ≈20%; vehicles with no counter, Scania/Mercedes/diesel, still N/A → "—"), net payload (only GVM, must subtract tare) |
| ✗ N/A (operator commercial data) | customer count, cargo type, charging cost/rebate, CO₂ and fuel saving (needs a diesel baseline), fixed shifts |

✗ fields must be requested from the operator / Monta, or clearly marked estimated/not
applicable — **never fabricated**.

- **No mass channel** (e.g. YN75NMA, T88RNW): the briefing auto-switches to the **distribution
  variant** — EP & projected-range histograms replace the GVM scatters; load points, the 42 t
  projection, "Median GVM" and the verification workbook are all N/A (shown as "—" / omitted), never
  fabricated.

- **Diesel comparator (YT21EFD)**: charging sessions / SoC / AC-DC split / regen are **not
  applicable** (no battery), not "unreported" — the diesel briefing simply has no such
  fields (no "—" placeholders, no data-availability note for them). Real pipeline data:
  distance + fuel (raw VDHR/LFC cumulative counters and the xlsx driving-leg sums),
  fuel consumption, GVM, temperature, speed, route, and **tank-to-wheel CO₂e** (fuel ×
  the agreed 2.58354 kg CO₂e/L factor — arithmetic, not measurement; state the factor
  inline). Well-to-tank / well-to-wheel CO₂e remains N/A unless a factor is agreed. The
  EV briefings' "CO₂ & fuel saved vs diesel" stays N/A *in the EV briefing itself*, but
  this diesel briefing now supplies the baseline numbers a partner needs to make that
  comparison offline.

- **Unavailable → show "—" not 0**: when a pipeline field is in the schema but this vehicle
  has no valid value for the whole column (e.g. some vehicles do not report charging AC/DC
  kWh, or regen recovery), pass NaN via `_sum_or_na`, and the render-side `f()` shows "—"
  rather than a misleading 0; the charging commentary then changes wording to "Charged-energy
  AC/DC breakdown not reported for this vehicle." A true 0 (data present and genuinely 0) is
  still shown as 0. The audit print likewise shows "—" for unavailable.
