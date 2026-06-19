# YN25RSY — Validation Figure Review Results

> Pipeline: mercedes_speed | Last reviewed: 2026-03-25 (Round 2 thorough)

## Summary

| Status | Count | Percentage |
|--------|-------|------------|
| OK | 46 | 95.8% |
| Issue | 2 | 4.2% |
| Not reviewed | 0 | 0% |
| **Total** | 48 | 100% |

### Known remaining issues

- 12-01 (0039): SOC flat at ~12%, speed spikes visible but no discharge trip detected — BMS protection / low-SOC plateau, known limitation (documented in reference)
- 11-18 (0027): Second discharge trip annotation shows EP=1.349 kWh/km at very low SOC (~2-5%), potentially unreliable energy performance at battery floor

---

## Round 1 — Initial review (2026-03-23)

Parameters: mercedes_speed (speed_threshold=1.0, min_stop=5.0, min_trip=2.0, min_soc_drop=2.0, min_energy=1.0)

### Per-figure results

| Figure | Type | Status | Issue | Root cause |
|--------|------|--------|-------|------------|
| validation_YN25RSY_2025-10-20_0000.png | Idle | OK | — | — |
| validation_YN25RSY_2025-10-21_0001.png | Active | OK | — | — |
| validation_YN25RSY_2025-10-22_0002.png | Active | OK | — | — |
| validation_YN25RSY_2025-10-23_0003.png | Active | OK | — | — |
| validation_YN25RSY_2025-10-24_0004.png | Idle | OK | — | — |
| validation_YN25RSY_2025-10-25_0005.png | Active | OK | — | — |
| validation_YN25RSY_2025-10-26_0006.png | Idle | OK | — | — |
| validation_YN25RSY_2025-10-27_0007.png | Active | OK | — | — |
| validation_YN25RSY_2025-10-28_0008.png | Active | OK | — | — |
| validation_YN25RSY_2025-10-29_0009.png | Idle | OK | — | — |
| validation_YN25RSY_2025-10-30_0010.png | Active | OK | — | — |
| validation_YN25RSY_2025-10-31_0011.png | Idle | OK | — | — |
| validation_YN25RSY_2025-11-01_0012.png | Active | OK | — | — |
| validation_YN25RSY_2025-11-02_0013.png | Idle | OK | — | — |
| validation_YN25RSY_2025-11-04_0015.png | Idle | OK | — | — |
| validation_YN25RSY_2025-11-06_0016.png | Idle | OK | — | — |
| validation_YN25RSY_2025-11-08_0018.png | Active | OK | — | — |
| validation_YN25RSY_2025-11-09_0019.png | Active | OK | — | — |
| validation_YN25RSY_2025-11-10_0020.png | Idle | OK | — | — |
| validation_YN25RSY_2025-11-11_0021.png | Active | OK | — | — |
| validation_YN25RSY_2025-11-12_0022.png | Active | OK | — | — |
| validation_YN25RSY_2025-11-13_0023.png | Active | OK | — | — |
| validation_YN25RSY_2025-11-14_0024.png | Idle | OK | — | — |
| validation_YN25RSY_2025-11-15_0025.png | Idle | OK | — | — |
| validation_YN25RSY_2025-11-18_0027.png | Active | Issue | Second trip EP=1.349 kWh/km at very low SOC (~2-5%); dSOC=3% near battery floor may yield unreliable EP | SOC floor artefact — energy metrics near 0% SOC are unreliable due to BMS non-linearity |
| validation_YN25RSY_2025-11-19_0028.png | Idle | OK | — | — |
| validation_YN25RSY_2025-11-20_0029.png | Idle | OK | — | — |
| validation_YN25RSY_2025-11-22_0031.png | Idle | OK | — | — |
| validation_YN25RSY_2025-11-26_0034.png | Idle | OK | — | — |
| validation_YN25RSY_2025-11-27_0035.png | Idle | OK | — | — |
| validation_YN25RSY_2025-11-28_0036.png | Idle | OK | — | — |
| validation_YN25RSY_2025-11-29_0037.png | Idle | OK | — | — |
| validation_YN25RSY_2025-11-30_0038.png | Idle | OK | — | — |
| validation_YN25RSY_2025-12-01_0039.png | Active | Issue | Speed spikes visible but SOC flat at ~12% — no discharge trip detected | BMS protection / SOC plateau at low state; known limitation documented in reference |
| validation_YN25RSY_2025-12-02_0040.png | Idle | OK | — | — |
| validation_YN25RSY_2025-12-03_0041.png | Idle | OK | — | — |
| validation_YN25RSY_2025-12-04_0042.png | Active | OK | — | — |
| validation_YN25RSY_2025-12-05_0043.png | Active | OK | — | — |
| validation_YN25RSY_2025-12-06_0044.png | Idle | OK | — | — |
| validation_YN25RSY_2025-12-08_0046.png | Charge-only | OK | — | — |
| validation_YN25RSY_2025-12-09_0047.png | Idle | OK | — | — |
| validation_YN25RSY_2025-12-10_0048.png | Idle | OK | — | — |
| validation_YN25RSY_2025-12-15_0050.png | Idle | OK | — | — |
| validation_YN25RSY_2025-12-20_0051.png | Idle | OK | — | — |
| validation_YN25RSY_2025-12-23_0052.png | Idle | OK | — | — |
| validation_YN25RSY_2026-01-04_0055.png | Idle | OK | — | — |
| validation_YN25RSY_2026-01-09_0056.png | Charge-only | OK | — | — |
| validation_YN25RSY_2026-01-10_0057.png | Idle | OK | — | — |

### Round 1 summary

- Reviewed: 48 figures
- OK: 46, Issue: 2
- Active days with discharge trips: 15 days (10-21, 10-22, 10-23, 10-25, 10-27, 10-28, 10-30, 11-01, 11-08, 11-09, 11-11, 11-12, 11-13, 11-18, 12-04, 12-05)
- Charge-only days: 2 (12-08, 01-09)
- Idle/no-activity days: 31

**Dominant pattern**: The vehicle has a high idle ratio (~65% of days). Active days show clean speed-based segmentation with correct trip boundaries. Logger CVW mass overlay appears correctly as purple dashed lines on active days. The mercedes_speed pipeline handles integer SOC precision well — no over-segmentation artefacts observed.

**Key observations on active days**:
1. Trip boundaries align well with speed traces (telematics speed in orange, Logger speed in yellow where available).
2. Charging segments (green bands) correctly identified between discharge trips.
3. EP values on annotated trips are in the expected 0.7-2.1 kWh/km range for a 40t class eActros 600.
4. Logger CVW mass values typically in 12,000-35,000 kg range, consistent with HGV operations.
5. Multi-stop days (e.g., 10-28 with 3 trips, 11-12 with 4 trips) are segmented correctly without over-splitting.

**Issue details**:
1. **11-18 (minor)**: The second discharge trip occurs at very low SOC (2-5%). The EP value of ~1.349 kWh/km is likely unreliable because BMS voltage-SOC mapping is highly non-linear near 0%. This is a data quality issue, not a segmentation issue — the trip boundaries themselves are correct.
2. **12-01 (known)**: The vehicle appears to move (speed spikes visible) but SOC remains flat at ~12%. This is a known BMS protection behaviour where the vehicle operates in limp mode and the BMS reports constant SOC. No segmentation algorithm can extract meaningful energy data from a flat SOC trace. Already documented in the reference file.

**Proposed changes**: None needed. Current parameters are well-tuned for this vehicle. Both identified issues are inherent data quality limitations, not parameter issues.

---

## Round 2 — Thorough review (2026-03-25)

Parameters: mercedes_speed (speed_threshold=1.0, min_stop=5.0, min_trip=2.0, min_soc_drop=2.0, min_energy=1.0) — **unchanged from Round 1**

### Review scope

Full re-examination of all 48 validation figures with particular attention to:
1. Trip boundary accuracy vs. speed traces (telematics speed overlay)
2. Charge segment detection correctness
3. Annotation consistency (dSOC, energy, EP values)
4. Previously flagged issues (11-18, 12-01) — re-evaluated
5. AC/DC delta, moving energy, and vehicle mass subplots for anomalies

### Per-figure results

| Figure | Type | Status | Issue | Notes |
|--------|------|--------|-------|-------|
| validation_YN25RSY_2025-10-20_0000.png | Idle | OK | — | SOC flat ~85%, no activity |
| validation_YN25RSY_2025-10-21_0001.png | Active | OK | — | 1 trip (dSOC~50%), 1 charge. Trip boundary aligns with speed trace |
| validation_YN25RSY_2025-10-22_0002.png | Active | OK | — | 3 trips, SOC 100%→25%. Annotation text overlap (cosmetic) but data correct |
| validation_YN25RSY_2025-10-23_0003.png | Active | OK | — | 1 trip + 1 charge, clean boundaries |
| validation_YN25RSY_2025-10-24_0004.png | Idle | OK | — | SOC flat ~85% |
| validation_YN25RSY_2025-10-25_0005.png | Active | OK | — | 5 trips, high-intensity multi-stop day. EP range 0.9–1.2 kWh/km, consistent |
| validation_YN25RSY_2025-10-26_0006.png | Idle | OK | — | SOC flat ~25% |
| validation_YN25RSY_2025-10-27_0007.png | Active | OK | — | 1 charge + 2 trips, boundaries align well with speed |
| validation_YN25RSY_2025-10-28_0008.png | Active | OK | — | 4 trips + 2 charges, complex multi-stop day. All segment boundaries correct |
| validation_YN25RSY_2025-10-29_0009.png | Idle | OK | — | SOC flat ~85%, minor speed spikes (below threshold) |
| validation_YN25RSY_2025-10-30_0010.png | Active | OK | — | 2 trips + 2 charges, correct segmentation |
| validation_YN25RSY_2025-10-31_0011.png | Idle | OK | — | SOC flat ~85% |
| validation_YN25RSY_2025-11-01_0012.png | Active | OK | — | 2 trips + 1 charge, SOC 95%→5%. Previously problematic with Logger-speed pipeline; now correctly handled by telematics speed |
| validation_YN25RSY_2025-11-02_0013.png | Idle | OK | — | SOC flat ~15% |
| validation_YN25RSY_2025-11-04_0015.png | Idle | OK | — | SOC flat ~85% |
| validation_YN25RSY_2025-11-06_0016.png | Idle | OK | — | SOC flat ~85%, very short time window |
| validation_YN25RSY_2025-11-08_0018.png | Active | OK | — | 4 trips + 1 charge, correct boundaries. Charge segment (green band) properly placed |
| validation_YN25RSY_2025-11-09_0019.png | Active | OK | — | 1 short trip + 1 charge, SOC 25%→10% then charge to 95% |
| validation_YN25RSY_2025-11-10_0020.png | Idle | OK | — | SOC flat ~25% |
| validation_YN25RSY_2025-11-11_0021.png | Active | OK | — | 3 trips + 1 charge, SOC 95%→15%. Multi-stop correctly segmented |
| validation_YN25RSY_2025-11-12_0022.png | Active | OK | — | 5 trips + 2–3 charges, full-day high-frequency ops. Segmentation excellent |
| validation_YN25RSY_2025-11-13_0023.png | Active | OK | — | 3 trips + 2 charges, multi-cycle day. EP values reasonable |
| validation_YN25RSY_2025-11-14_0024.png | Idle | OK | — | SOC flat ~85% |
| validation_YN25RSY_2025-11-15_0025.png | Idle | OK | — | SOC flat ~85% |
| validation_YN25RSY_2025-11-18_0027.png | Active | Issue | Last trip at SOC ~2–5%, EP=1.349 kWh/km unreliable | **Re-confirmed**: 5 discharge trips total; first 4 trips are clean with plausible EP. Only the final trip near SOC floor is questionable. Trip boundaries themselves are correct — this is a data quality limitation, not segmentation error |
| validation_YN25RSY_2025-11-19_0028.png | Idle | OK | — | SOC flat ~10% |
| validation_YN25RSY_2025-11-20_0029.png | Idle | OK | — | SOC flat ~5% |
| validation_YN25RSY_2025-11-22_0031.png | Idle | OK | — | SOC flat ~5%, short time window |
| validation_YN25RSY_2025-11-26_0034.png | Idle | OK | — | SOC flat ~10% |
| validation_YN25RSY_2025-11-27_0035.png | Idle | OK | — | SOC flat ~5% |
| validation_YN25RSY_2025-11-28_0036.png | Idle | OK | — | SOC flat ~5% |
| validation_YN25RSY_2025-11-29_0037.png | Idle | OK | — | SOC flat ~10% |
| validation_YN25RSY_2025-11-30_0038.png | Idle | OK | — | SOC flat ~10% |
| validation_YN25RSY_2025-12-01_0039.png | Active | Issue | SOC flat ~12%, speed spikes but no trip detected | **Re-confirmed**: BMS protection / limp mode. SOC trace completely flat despite apparent vehicle movement. No segmentation algorithm can extract energy from flat SOC. Known limitation |
| validation_YN25RSY_2025-12-02_0040.png | Idle | OK | — | SOC flat ~10% |
| validation_YN25RSY_2025-12-03_0041.png | Idle | OK | — | SOC flat ~10%, minor speed spikes |
| validation_YN25RSY_2025-12-04_0042.png | Active | OK | — | 2 charges + minor discharge trips. Small dSOC movements correctly identified |
| validation_YN25RSY_2025-12-05_0043.png | Charge-only | OK | — | SOC rising from ~15% to ~25%, 1 charge correctly annotated. Reclassified from Active to Charge-only (no meaningful discharge trip) |
| validation_YN25RSY_2025-12-06_0044.png | Idle | OK | — | SOC flat ~35% |
| validation_YN25RSY_2025-12-08_0046.png | Charge-only | OK | — | SOC 60%→95%, 1 charge correctly annotated |
| validation_YN25RSY_2025-12-09_0047.png | Idle | OK | — | SOC flat ~85% |
| validation_YN25RSY_2025-12-10_0048.png | Idle | OK | — | SOC flat ~85% |
| validation_YN25RSY_2025-12-15_0050.png | Idle | OK | — | SOC flat ~85% |
| validation_YN25RSY_2025-12-20_0051.png | Idle | OK | — | SOC flat ~85% |
| validation_YN25RSY_2025-12-23_0052.png | Idle | OK | — | SOC flat ~85%, very short time window |
| validation_YN25RSY_2026-01-04_0055.png | Idle | OK | — | SOC flat ~85% |
| validation_YN25RSY_2026-01-09_0056.png | Charge-only | OK | — | SOC 85%→95%, 1 charge segment correctly identified |
| validation_YN25RSY_2026-01-10_0057.png | Idle | OK | — | SOC flat ~95% |

### Round 2 summary

- **Reviewed**: 48 figures (full re-examination)
- **OK**: 46, **Issue**: 2 (unchanged from Round 1)
- **Active days**: 15 (10-21, 10-22, 10-23, 10-25, 10-27, 10-28, 10-30, 11-01, 11-08, 11-09, 11-11, 11-12, 11-13, 11-18, 12-04)
- **Charge-only days**: 3 (12-05 reclassified from Active, 12-08, 01-09)
- **Idle days**: 30

**Classification change from Round 1**: 12-05 (0043) reclassified from Active to Charge-only. On closer inspection, the SOC trace only shows a rising trend with 1 charge annotation. The original "Active" classification was borderline; the dominant activity is charging, not discharging. This is a cosmetic reclassification and does not affect data quality or segment accuracy.

**Consistency check**:
1. All 15 active days show trip boundaries correctly aligned with telematics speed traces — no over-segmentation or under-segmentation observed.
2. Charge segments (green bands) are consistently placed at correct time windows across all active days.
3. EP values remain in the expected 0.7–2.1 kWh/km range for eActros 600 (40t class) across all valid trips.
4. AC/DC Delta, Moving Energy Delta, and Vehicle Mass subplots show consistent patterns — no anomalous spikes or data gaps detected on active days.
5. The long idle period from late November through mid-January (11-19 to 01-04) is correctly represented with flat SOC traces and no false trip detections.

**Re-evaluation of known issues**:
1. **11-18 (0027)**: Re-confirmed as minor data quality issue. The trip at SOC floor (2–5%) produces an EP value (1.349 kWh/km) that is within the plausible range but should be treated with caution in analysis. No parameter change can address BMS non-linearity at SOC floor.
2. **12-01 (0039)**: Re-confirmed as known BMS protection limitation. The speed spikes visible in this Round 2 review are very small (just barely visible) and do not correspond to any SOC change. This is consistent with the BMS protecting the battery at ~12% SOC.

**Proposed changes**: None. The mercedes_speed pipeline with current parameters (speed_threshold=1.0, min_stop=5.0, min_trip=2.0, min_soc_drop=2.0, min_energy=1.0) produces excellent segmentation quality for YN25RSY. Both identified issues are inherent data/BMS limitations that cannot be addressed through parameter tuning.
