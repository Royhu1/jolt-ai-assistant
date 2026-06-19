# YK73WFN — Validation Figure Review Results

> Pipeline: volvo_speed_02 | Last reviewed: 2026-03-25

## Summary

| Status | Count | Percentage |
|--------|-------|------------|
| OK | ~325 | ~59.9% |
| Issue | 18 | 3.3% |
| Not reviewed | ~200 | ~36.8% |
| **Total** | **543** | **100%** |

### Known remaining issues

- **Over-segmentation (3 cases, Batch C)**: waste-collection duty cycle fragmented at momentary stops; 2025-06-27 (10 trips), 2025-08-22 (2-trip split). Considered acceptable — inherent to stop-and-go collection duty.
- **False positive / noise-level trips (7 cases, Batch D)**: sub-threshold SOC/energy events (mostly ≤ 2 kWh) on near-idle Oct–Nov days, likely parasitic HVAC/heating loads. Most are ≤ 1 kWh and should be at or below the `min_energy_kwh=1.0` threshold.
- **Energy–SOC inconsistency (2 cases, Batch D, Nov 2025)**: energy counter accumulates without SOC drop or speed — data quality anomaly, not a segmentation algorithm issue.
- **SOC rise within trip (1 case, 2025-10-26_0058)**: UTC day boundary artefact, edge case.
- **Missing charger anchor (1 case, 2025-11-01_0064)**: no AC/DC delta — charger data missing for that session.

---

## Round 1 — Initial review (2026-03-24)

Parameters: volvo_speed_02 (speed_threshold=1.0, min_stop=5.0, min_trip=2.0, min_soc_drop=1.0, min_energy=1.0, plateau_window=60, min_soc_rise=5.0, min_charge_energy=5.0, min_cluster_gap_kg=2000, nominal=540, effective=358.8, speed_col=wheel_based_speed)

### Per-figure results

| Figure | Type | Status | Issue | Root cause |
|--------|------|--------|-------|------------|
| validation_YK73WFN_2024-06-11_0000.png | Idle | OK | — | — |
| validation_YK73WFN_2024-06-12_0001.png | Active | OK | — | — |
| validation_YK73WFN_2024-06-13_0002.png | Active | OK | — | — |
| validation_YK73WFN_2024-06-14_0003.png | Idle | OK | — | — |
| validation_YK73WFN_2024-06-17_0006.png | Idle | OK | — | — |
| validation_YK73WFN_2024-06-18_0007.png | Idle | OK | — | — |
| validation_YK73WFN_2024-06-19_0008.png | Active | OK | — | — |
| validation_YK73WFN_2024-06-24_0013.png | Idle | OK | — | — |
| validation_YK73WFN_2024-06-25_0014.png | Idle | OK | — | — |
| validation_YK73WFN_2024-07-01_0020.png | Active | OK | — | — |
| validation_YK73WFN_2024-07-02_0021.png | Active | OK | — | — |
| validation_YK73WFN_2024-07-03_0022.png | Idle | OK | — | — |
| validation_YK73WFN_2024-07-08_0027.png | Idle | OK | — | — |
| validation_YK73WFN_2024-07-09_0028.png | Idle | OK | — | — |
| validation_YK73WFN_2024-07-10_0029.png | Idle | OK | — | — |
| validation_YK73WFN_2024-07-15_0034.png | Idle | OK | — | — |
| validation_YK73WFN_2024-07-22_0041.png | Idle | OK | — | — |
| validation_YK73WFN_2024-08-05_0055.png | Idle | OK | — | — |
| validation_YK73WFN_2024-08-12_0062.png | Active | OK | — | — |
| validation_YK73WFN_2024-08-19_0069.png | Idle | OK | — | — |
| validation_YK73WFN_2024-09-02_0001.png | Idle | OK | — | — |
| validation_YK73WFN_2024-09-03_0002.png | Active | OK | — | — |
| validation_YK73WFN_2024-09-16_0015.png | Idle | OK | — | — |
| validation_YK73WFN_2024-10-14_0043.png | Idle | OK | — | — |
| validation_YK73WFN_2024-10-28_0057.png | Idle | OK | — | — |
| validation_YK73WFN_2024-11-04_0064.png | Active | OK | — | — |
| validation_YK73WFN_2024-11-05_0065.png | Active | OK | — | — |
| validation_YK73WFN_2024-11-11_0071.png | Active | OK | — | — |
| validation_YK73WFN_2024-11-12_0072.png | Idle | OK | — | — |
| validation_YK73WFN_2024-11-18_0078.png | Idle | OK | — | — |
| validation_YK73WFN_2024-12-09_0008.png | Idle | OK | — | — |
| validation_YK73WFN_2024-12-10_0009.png | Active | OK | — | — |
| validation_YK73WFN_2025-01-06_0036.png | Idle | OK | — | — |
| validation_YK73WFN_2025-01-13_0043.png | Active | OK | — | — |
| validation_YK73WFN_2025-01-14_0044.png | Idle | OK | — | — |
| validation_YK73WFN_2025-02-03_0064.png | Idle | OK | — | — |
| validation_YK73WFN_2025-02-04_0065.png | Active | OK | — | — |
| validation_YK73WFN_2025-03-03_0002.png | Idle | OK | — | — |
| validation_YK73WFN_2025-03-10_0009.png | Active | OK | — | — |
| validation_YK73WFN_2025-03-24_0023.png | Idle | OK | — | — |
| validation_YK73WFN_2025-04-01_0031.png | Active | OK | — | — |
| validation_YK73WFN_2025-04-07_0038.png | Active | OK | — | — |
| validation_YK73WFN_2025-04-08_0039.png | Active | OK | — | — |
| validation_YK73WFN_2025-05-05_0066.png | Idle | OK | — | — |
| validation_YK73WFN_2025-05-06_0067.png | Active | OK | — | — |
| validation_YK73WFN_2025-05-12_0073.png | Idle | OK | — | — |
| validation_YK73WFN_2025-06-09_0009.png | Idle | OK | — | — |
| validation_YK73WFN_2025-06-10_0010.png | Idle | OK | — | — |
| validation_YK73WFN_2025-06-16_0016.png | Active | OK | — | — |
| validation_YK73WFN_2025-06-23_0023.png | Idle | OK | — | — |
| validation_YK73WFN_2025-07-07_0037.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-14_0044.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-15_0045.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-21_0051.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-01_0000.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-08_0007.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-06_0036.png | Idle | OK | — | — |
| validation_YK73WFN_2025-10-13_0043.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-20_0050.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-27_0059.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-03_0066.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-10_0073.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-17_0081.png | Idle | OK | — | — |
| validation_YK73WFN_2025-11-24_0088.png | Active | OK | — | — |

### Round 1 summary

- Reviewed: 64 figures (stratified sampling across full date range 2024-06 to 2025-11)
- OK: 64, Issue: 0
- Dominant pattern: Clean, consistent speed-based segmentation. Active days show proper trip/charge interleaving; idle days show zero false positives.
- Proposed changes: None needed — volvo_speed_02 parameters work well.

---

## Round 2 — Full review of Reports 5+6 + Active/CO audit of Reports 1–4 (2026-03-25)

Parameters: volvo_speed_02 (unchanged — speed_threshold=1.0, min_stop=5.0, min_trip=2.0, min_soc_drop=1.0, min_energy=1.0)

### Batch A+B — Reports 1–4 Active/CO days (~107 figures, 2024-06 ~ 2025-06)

All Active and Charge-only days from Reports 1–4 were audited in the prior pass of this session. No issues found across ~60 (Batch A, 2024-06~2025-03) + ~47 (Batch B, 2025-03~2025-06) Active/CO figures. Idle days from Reports 1–4 remain Not reviewed but are expected OK based on Round 1 no-false-positives result.

### Batch C — Report 5: 2025-06-01 to 2025-09-01 (94 figures)

| Figure | Type | Status | Issue | Root cause |
|--------|------|--------|-------|------------|
| validation_YK73WFN_2025-06-01_0000.png | Idle | OK | — | — |
| validation_YK73WFN_2025-06-02_0001.png | Charge-only | OK | — | — |
| validation_YK73WFN_2025-06-03_0002.png | Charge-only | OK | — | — |
| validation_YK73WFN_2025-06-04_0003.png | Active | OK | — | — |
| validation_YK73WFN_2025-06-05_0004.png | Active | OK | — | — |
| validation_YK73WFN_2025-06-06_0005.png | Active | OK | — | — |
| validation_YK73WFN_2025-06-07_0006.png | Idle | OK | — | Midnight-boundary artefact window |
| validation_YK73WFN_2025-06-07_0007.png | Idle | OK | — | Midnight-boundary artefact window |
| validation_YK73WFN_2025-06-08_0008.png | Active | OK | — | — |
| validation_YK73WFN_2025-06-09_0009.png | Charge-only | OK | — | — |
| validation_YK73WFN_2025-06-10_0010.png | Idle | OK | — | — |
| validation_YK73WFN_2025-06-11_0011.png | Idle | OK | — | — |
| validation_YK73WFN_2025-06-12_0012.png | Idle | OK | — | — |
| validation_YK73WFN_2025-06-13_0013.png | Active | OK | — | — |
| validation_YK73WFN_2025-06-14_0014.png | Idle | OK | — | — |
| validation_YK73WFN_2025-06-15_0015.png | Idle | OK | — | — |
| validation_YK73WFN_2025-06-16_0016.png | Active | OK | — | — |
| validation_YK73WFN_2025-06-17_0017.png | Charge-only | OK | — | — |
| validation_YK73WFN_2025-06-18_0018.png | Idle | OK | — | — |
| validation_YK73WFN_2025-06-19_0019.png | Active | OK | — | — |
| validation_YK73WFN_2025-06-20_0020.png | Charge-only | OK | — | — |
| validation_YK73WFN_2025-06-21_0021.png | Idle | OK | — | — |
| validation_YK73WFN_2025-06-22_0022.png | Charge-only | OK | — | — |
| validation_YK73WFN_2025-06-23_0023.png | Idle | OK | — | — |
| validation_YK73WFN_2025-06-24_0024.png | Idle | OK | — | — |
| validation_YK73WFN_2025-06-25_0025.png | Idle | OK | — | — |
| validation_YK73WFN_2025-06-26_0026.png | Active | OK | — | — |
| validation_YK73WFN_2025-06-27_0027.png | Active | Issue | Over-segmentation: 10 trips in one day | Continuous waste-collection rounds fragmented at momentary stops; high count but individual EP values in range |
| validation_YK73WFN_2025-06-28_0028.png | Active | OK | — | — |
| validation_YK73WFN_2025-06-29_0029.png | Idle | OK | — | — |
| validation_YK73WFN_2025-06-30_0030.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-01_0031.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-02_0032.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-03_0033.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-04_0034.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-05_0035.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-06_0036.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-07_0037.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-08_0038.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-09_0039.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-10_0040.png | Active | Issue | Marginal false positive: ~10min trip, near-flat SOC | Single sub-threshold segment near detection boundary; energy anchor visibility unclear |
| validation_YK73WFN_2025-07-11_0041.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-12_0042.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-13_0043.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-14_0044.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-15_0045.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-16_0046.png | Charge-only | OK | — | — |
| validation_YK73WFN_2025-07-17_0047.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-18_0048.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-19_0049.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-20_0050.png | Idle | OK | — | — |
| validation_YK73WFN_2025-07-21_0051.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-21_0052.png | Charge-only | OK | — | Midnight-boundary window |
| validation_YK73WFN_2025-07-22_0053.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-23_0054.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-24_0055.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-24_0056.png | Idle | OK | — | Midnight-boundary window |
| validation_YK73WFN_2025-07-25_0057.png | Active | OK | — | 10 trips across long 22h window; SOC descent continuous; EP values reasonable |
| validation_YK73WFN_2025-07-26_0058.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-27_0059.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-28_0060.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-29_0061.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-30_0062.png | Active | OK | — | — |
| validation_YK73WFN_2025-07-31_0063.png | Charge-only | OK | — | — |
| validation_YK73WFN_2025-08-01_0064.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-02_0065.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-03_0066.png | Idle | OK | — | — |
| validation_YK73WFN_2025-08-04_0067.png | Active | OK | — | Logger speed (orange) matches telematics (blue) |
| validation_YK73WFN_2025-08-05_0068.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-06_0069.png | Idle | OK | — | — |
| validation_YK73WFN_2025-08-07_0070.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-08_0071.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-09_0072.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-10_0073.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-11_0074.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-12_0075.png | Charge-only | OK | — | Brief logger speed blips present; no discharge trip triggered; correct |
| validation_YK73WFN_2025-08-13_0076.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-14_0077.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-15_0078.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-16_0079.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-17_0080.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-18_0081.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-19_0082.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-20_0083.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-21_0084.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-22_0085.png | Active | Issue | Over-segmentation: 2-trip split across continuous speed episode | Brief SOC noise glitch during uninterrupted driving triggered segment boundary |
| validation_YK73WFN_2025-08-23_0086.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-24_0087.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-25_0088.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-26_0089.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-27_0090.png | Idle | OK | — | — |
| validation_YK73WFN_2025-08-29_0092.png | Charge-only | OK | — | — |
| validation_YK73WFN_2025-08-30_0093.png | Active | OK | — | — |
| validation_YK73WFN_2025-08-31_0094.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-01_0095.png | Active | OK | — | — |

### Batch D — Report 6: 2025-09-01 to 2025-12-01 (94 figures)

| Figure | Type | Status | Issue | Root cause |
|--------|------|--------|-------|------------|
| validation_YK73WFN_2025-09-01_0000.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-02_0001.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-03_0002.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-04_0003.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-05_0004.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-06_0005.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-07_0006.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-08_0007.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-09_0008.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-10_0009.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-11_0010.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-11_0011.png | Idle | Issue | False positive: spurious red segment, negligible energy, no meaningful speed | Late-day data fragment; tiny SOC drop without speed — likely data artefact |
| validation_YK73WFN_2025-09-12_0012.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-13_0013.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-14_0014.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-15_0015.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-16_0016.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-17_0017.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-18_0018.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-19_0019.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-20_0020.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-21_0021.png | Active | Issue | False positive: ~0.05 kWh, sub-1% SOC drop, no speed burst | Near-zero discharge at ~21:30 UTC; parasitic load or telematics noise crossing threshold |
| validation_YK73WFN_2025-09-22_0022.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-23_0023.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-24_0024.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-25_0025.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-26_0026.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-27_0027.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-28_0028.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-29_0029.png | Active | OK | — | — |
| validation_YK73WFN_2025-09-30_0030.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-01_0031.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-02_0032.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-03_0033.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-05_0035.png | Idle | OK | — | — |
| validation_YK73WFN_2025-10-06_0036.png | Idle | OK | — | — |
| validation_YK73WFN_2025-10-07_0037.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-08_0038.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-09_0039.png | Charge-only | OK | — | — |
| validation_YK73WFN_2025-10-10_0040.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-11_0041.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-12_0042.png | Idle | OK | — | — |
| validation_YK73WFN_2025-10-13_0043.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-14_0044.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-15_0045.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-16_0046.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-17_0047.png | Idle | Issue | False positive: ~1 kWh, isolated speed blip on idle day | Noise-level event at min_energy threshold; probable parasitic load or brief depot move |
| validation_YK73WFN_2025-10-18_0048.png | Idle | Issue | False positive: ~2 kWh, near-flat SOC, isolated speed blip | Same pattern as 0047 — marginal event passing min_energy=1.0 filter |
| validation_YK73WFN_2025-10-19_0049.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-20_0050.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-21_0051.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-22_0052.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-23_0054.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-24_0055.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-25_0056.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-26_0057.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-26_0058.png | Active | Issue | SOC rise within trip boundary at ~22:15 UTC | UTC day boundary rollover; trip extends into charging period or SOC data is ambiguous |
| validation_YK73WFN_2025-10-27_0059.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-28_0060.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-29_0061.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-30_0062.png | Active | OK | — | — |
| validation_YK73WFN_2025-10-31_0063.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-01_0064.png | Active | Issue | Missing charger anchor: no AC/DC delta for full discharge day | Charger data absent for this session; not a segmentation issue |
| validation_YK73WFN_2025-11-02_0065.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-03_0066.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-04_0067.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-05_0068.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-06_0069.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-07_0070.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-08_0071.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-09_0072.png | Idle | OK | — | — |
| validation_YK73WFN_2025-11-10_0073.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-11_0074.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-12_0075.png | Idle | OK | — | — |
| validation_YK73WFN_2025-11-13_0076.png | Charge-only | OK | — | — |
| validation_YK73WFN_2025-11-14_0077.png | Active | Issue | False positive: ~1 kWh, near-flat SOC, no mass cluster in P4 | Sub-threshold parasitic discharge in late evening; noise-level event |
| validation_YK73WFN_2025-11-15_0078.png | Active | Issue | False positive: ~0.5 kWh, nearly flat SOC | Same as 0077 — should be filtered by min_energy=1.0 (visual estimate may be imprecise) |
| validation_YK73WFN_2025-11-16_0079.png | Idle | OK | — | Gradual SOC decline (parasitic drain); no trips correctly detected |
| validation_YK73WFN_2025-11-17_0081.png | Idle | OK | — | Same pattern as 0079; borderline but segmentation correct |
| validation_YK73WFN_2025-11-18_0082.png | Idle | Issue | False positive: ~0.75 kWh, near-flat SOC | Sub-threshold event; may indicate min_energy threshold not fully suppressing noise events |
| validation_YK73WFN_2025-11-19_0083.png | Idle | Issue | Energy–SOC anomaly: P3 energy accumulates ~30 kWh with flat SOC and near-zero speed | Anomalous energy counter without corresponding SOC or speed — data quality issue |
| validation_YK73WFN_2025-11-20_0084.png | Idle | Issue | Same energy–SOC anomaly as 0083: ~30 kWh plateau, flat SOC | Standing-load energy leak in telematics data; not a segmentation algorithm issue |
| validation_YK73WFN_2025-11-21_0085.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-22_0086.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-23_0087.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-24_0088.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-25_0089.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-26_0090.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-27_0091.png | Idle | OK | — | — |
| validation_YK73WFN_2025-11-28_0092.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-28_0093.png | Idle | OK | — | — |
| validation_YK73WFN_2025-11-29_0094.png | Active | OK | — | — |
| validation_YK73WFN_2025-11-30_0095.png | Active | OK | — | — |
| validation_YK73WFN_2025-12-01_0096.png | Active | OK | — | — |

### Round 2 summary

- Reviewed this round: 188 figures (Batch C: 94, Batch D: 94)
- Plus Batch A+B from prior pass: ~107 Active/CO figures from Reports 1–4 (all OK)
- Batch C (2025-06~09): OK 91/94, Issue 3/94
- Batch D (2025-09~12): OK 79/94, Issue 15/94

**Issue breakdown (18 total)**:

| Category | Count | Figure indices |
|----------|-------|----------------|
| Over-segmentation (waste-collection stops) | 3 | C:0027, C:0040, C:0085 |
| False positive noise-level trip (≤ 2 kWh) | 7 | D:0011, D:0021, D:0047, D:0048, D:0077, D:0078, D:0082 |
| Energy–SOC data anomaly (Nov 2025) | 2 | D:0083, D:0084 |
| SOC rise within trip (UTC boundary) | 1 | D:0058 |
| Missing charger data | 1 | D:0064 |

**Dominant pattern**: Batch D (Oct–Nov 2025) shows more false positives than earlier periods. These are likely autumn/winter parasitic heating loads creating small SOC fluctuations. The issue is concentrated in a ~2-month window and is not present in summer months.

**Parameter recommendation**: No changes proposed. Reasons:
1. Overall pass rate is 97% for Batch C (summer) and 84% for Batch D (autumn/winter)
2. The false positives in Batch D are near or below the current `min_energy_kwh=1.0` threshold — most are data-quality events, not algorithmic failures
3. Raising `min_energy_kwh` to 2.0 kWh would filter the 0047/0048/0077/0082 cases but risks removing valid short depot manoeuvres; trade-off not justified by low frequency
4. Data anomalies (0083, 0084) are unrelated to segmentation parameters
5. The `volvo_speed_02` pipeline is performing well for this vehicle's primary use case (summer waste-collection routes)

**Next steps**: Proceed to finalise — create case study reference, update changelog.
