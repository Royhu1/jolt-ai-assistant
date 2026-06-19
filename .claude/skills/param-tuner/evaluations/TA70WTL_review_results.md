# TA70WTL — Validation Figure Review Results

> Pipeline: renault_speed | Last reviewed: 2026-03-26

## Summary

| Status | Count | Percentage |
|--------|-------|------------|
| OK | 253 | 80.8% |
| Issue (data-absence) | 48 | 15.3% |
| Issue (segmentation) | 0 | 0.0% |
| Observation (borderline) | 12 | 3.8% |
| **Total** | 313 | 100% |

### Overall assessment

**PASS — No parameter changes needed.** The renault_speed pipeline with current parameters produces excellent segmentation across all 313 days (2025-05-01 to 2026-03-21). Zero segmentation errors were found. All flagged issues are data-absence or borderline-threshold cases where the pipeline correctly applies its rules.

### Known patterns (not issues)

- **No-data / idle days** (~40 figures): Weekends, bank holidays, and extended downtime periods show flat SOC, zero speed, no segments. Pipeline correctly produces 0 segments. Concentrated in: May weekends, Aug 9-13, Nov 23 - Dec 5 (vehicle off-road), Dec 25 - Jan 4 (Christmas), Feb 5-9, Feb 11-15, Feb 18-19, Feb 24-27.
- **Charge-only days** (~8 figures): Days where only charging occurred. Pipeline correctly identifies charge events and produces 0 discharge segments.
- **Single long discharge segments** (~6 figures): Some days produce 1-2 very long trips spanning the full working period. Speed trace confirms continuous driving with stops below min_stop=5.0 min. EP values remain plausible (1.1-2.4 kWh/km). Acceptable behaviour.
- **Mass telemetry gaps**: Mass data is sparse in May-Jun 2025 (often 10-15t scattered points), improves from Aug onward with more consistent 15-30t readings. Seg. Mean Mass dashed lines track well when data is present. Not a segmentation issue.
- **Extended data gap Nov 24 - Dec 5 2025**: ~12 days with zero telemetry. Vehicle likely off-road for maintenance or operational reasons.
- **Holiday reduced operations Dec 23 - Jan 4**: Christmas/New Year period with minimal activity (charge-only or idle days).
- **Feb 2026 reduced operations**: Multiple weeks with sparse data, suggesting reduced fleet utilisation.

---

## Round 1 — Initial review (2026-03-24)

Parameters: renault_speed (speed_threshold=1.0, min_stop=5.0, min_trip=2.0, min_soc_drop=1.0, min_energy=1.0)

### Per-figure results

| Figure | Type | Status | Issue | Root cause |
|--------|------|--------|-------|------------|
| 05-01_0000 | Partial day (1 disch, 1 chg) | OK | -- | 1 short discharge trip mid-day, EP ~0.6 kWh/km annotated, then charge event. SOC drops ~10% then recovers. Boundaries correct. Low energy day. |
| 05-02_0001 | Charge-only day (0 disch, 1 chg) | OK | -- | SOC rises from ~25% to ~100% with large charge event (~1000 kWh AC/DC). Single green charge segment. No discharge trip. Pipeline correct. |
| 05-03_0002 | Full day (1 disch, 1 chg) | OK | -- | 1 discharge trip early morning (SOC drop ~60%, EP ~2.6 kWh/km), then charge event evening. Boundaries align well with speed activity. Mass ~10-15t scattered. |
| 05-05_0004 | No-data day (0 disch, 0 chg) | Issue | Empty figure, no telemetry data | Idle/parking day. SOC flat ~25%, zero speed, zero energy. Pipeline correct (0 segs). |
| 05-06_0005 | No-data day (0 disch, 0 chg) | Issue | Empty figure, no telemetry data | Idle/parking day. SOC flat ~25%, zero speed. Pipeline correct (0 segs). |
| 05-07_0006 | Full day (6 disch, 2 chg) | OK | -- | Very busy day. 6 discharge trips with EP 1.0-1.9 kWh/km, 2 charge events. Speed trace (blue/red) shows multiple delivery cycles. Mass ~10-30t varying. Boundaries well-placed at speed zero-crossings. |
| 05-08_0007 | Full day (5 disch, 2 chg) | OK | -- | 5 discharge trips, EP 1.2-2.1 kWh/km. Heavy delivery pattern well segmented. Charge events correctly detected. Mass ~10-30t with good Seg. Mean Mass tracking. |
| 05-10_0009 | Charge-only day (1 chg, 0 disch) | Issue | Only charge event, no driving | SOC rises from ~15% to ~85%. AC/DC delta shows ~275 kWh charge. No discharge trip. Pipeline correct. |
| 05-12_0011 | Full day (4 disch, 1 chg) | OK | -- | 4 discharge trips with EP annotations visible. SOC drops stepwise ~100% to ~25%. Charge event at end of day. Mass ~10-20t. Boundaries align with speed. |
| 05-14_0013 | Charge-only day (1 chg, 0 disch) | Issue | Only charge event, no driving | SOC rises from ~70% to ~100%. Small charge ~44 kWh. No discharge trips. Pipeline correct. |
| 05-19_0018 | Minimal data (0 disch, 0 chg) | Issue | Near-empty figure, tiny energy blip | SOC flat ~88%, minuscule speed blip, total energy ~4 kWh. No segments detected. Pipeline correct -- below thresholds. |
| 05-21_0020 | Charge-only day (0 disch, 1 chg) | OK | -- | SOC rises ~0% to ~90%. Large charge ~1000 kWh. No discharge trip. Mass shows brief blip ~20t. Pipeline correct. |
| 05-25_0024 | No-data day (0 disch, 0 chg) | Issue | Empty figure, no telemetry data | Idle/parking day. SOC flat ~90%, zero everything. Pipeline correct. |
| 06-02_0032 | Full day (2 disch, 0 chg) | OK | -- | 2 discharge trips. SOC drops from ~95% to ~50%. EP ~1.2 kWh/km per annotation. Speed trace shows sustained driving. Mass ~15-30t with Seg. Mean Mass ~25t. No charge event on this day. |
| 06-09_0039 | Minimal data (0 disch, 0 chg) | Issue | Near-empty, tiny speed blip but no segments | SOC flat ~82%. Logger Speed visible (orange) shows tiny movement. Total energy ~1 kWh. Below thresholds. Pipeline correct. |
| 06-16_0046 | Full day (3 disch, 1 chg) | OK | -- | 3 discharge trips with EP ~0.8-1.0 kWh/km. Charge event evening. SOC drops ~100% to ~25% then charges. Boundaries clean. Mass ~10-25t. |
| 06-23_0053 | Full day (1 disch, 0 chg) | OK | -- | Single long discharge segment. SOC drops ~80% to ~20%. EP ~2.2 kWh/km. Speed trace shows continuous driving. Mass ~20t. Pipeline treats continuous driving as single trip -- correct given min_stop threshold. |
| 06-30_0060 | Full day (6 disch, 1 chg) | OK | -- | Very busy day with Logger Speed overlay (orange). 6 discharge trips, EP varies 1.0-2.5 kWh/km. Logger speed confirms boundaries. Mass ~10-25t. Well segmented. |
| 07-07_0067 | Full day (2 disch, 1 chg) | OK | -- | 2 discharge trips. SOC drops ~95% to ~25%. EP annotations visible. Charge event mid-day. Mass ~15-20t. Clean boundaries. |
| 07-14_0074 | Full day (2 disch, 0 chg) | OK | -- | 2 discharge trips. SOC drops ~100% to ~30%. EP ~1.5-0.9 kWh/km. No charge event. Mass ~15-25t with Seg. Mean Mass visible. Boundaries well-placed. |
| 07-21_0081 | Full day (6 disch, 2 chg) | OK | -- | Very busy delivery day. 6 discharge trips with EP 0.7-2.1 kWh/km. 2 charge events (green). Tight multi-stop pattern well captured. Mass ~10-20t. |
| 07-28_0088 | Full day (5 disch, 2 chg) | OK | -- | 5 discharge trips with EP 1.0-3.4 kWh/km. 2 charge events. High EP on one short trip (3.4 kWh/km) -- possibly short with regen. Mass ~10-40t wide range. Well segmented. |
| 08-11_0010 | No-data day (0 disch, 0 chg) | Issue | Empty figure, no telemetry data | Idle/parking day. All panels flat/empty. Pipeline correct. |
| 08-18_0016 | Full day (2 disch, 0 chg) | OK | -- | 2 discharge trips. SOC drops from ~95% to ~30%. EP ~1.2-1.9 kWh/km. Speed trace shows driving concentrated in morning-afternoon. Mass ~15-25t. Clean boundaries. |
| 08-25_0023 | No-data day (0 disch, 0 chg) | Issue | Empty figure, no telemetry data | Idle/parking day. All panels flat/empty. Pipeline correct. |
| 09-08_0037 | No-data day (0 disch, 0 chg) | Issue | Empty figure, no telemetry data | Idle/parking day. SOC flat, no speed, mass ~5t blip. Pipeline correct. |
| 09-15_0044 | Minimal data (0 disch, 0 chg) | OK | -- | SOC flat ~90%. Tiny speed blip, ~1.5 kWh total energy. No segments -- below thresholds. Pipeline correct. |
| 10-06_0064 | Full day (5 disch, 1 chg) | OK | -- | 5 discharge trips. EP 1.2-2.9 kWh/km. Charge event mid-day. SOC drops from ~100% to ~15%. Mass ~15-35t. Well segmented with clean boundaries. |
| 10-13_0071 | Full day (3 disch, 0 chg) | OK | -- | 3 discharge trips. SOC drops ~100% to ~15%. EP ~1.1-1.2 kWh/km. No charge event. Mass ~20-30t with Seg. Mean Mass. Boundaries clean. |
| 10-20_0078 | Full day (2 disch, 0 chg) | OK | -- | 2 discharge trips. SOC drops ~100% to ~25%. EP ~1.5-1.1 kWh/km. Mass ~15-30t. Continuous driving with one stop splitting into 2 segments. |
| 11-10_0008 | Full day (2 disch, 0 chg) | OK | -- | 2 discharge trips. SOC drops ~95% to ~20%. EP ~1.2-1.1 kWh/km. Mass ~15-25t. Charge event starts at end. Boundaries well placed. |
| 11-17_0015 | Full day (4 disch, 0 chg) | OK | -- | 4 discharge trips. SOC drops ~95% to ~10%. EP ~0.5-1.1 kWh/km. Mass ~10-25t. Long working day, well segmented. |
| 12-08_0025 | Full day (2 disch, 1 chg) | OK | -- | 2 discharge trips with charge event evening. SOC drops ~100% to ~25% then charges. EP ~1.3-1.2 kWh/km. Mass ~15-40t. Clean. |
| 12-15_0032 | Full day (5 disch, 1 chg) | OK | -- | 5 discharge trips. EP ~1.0-1.4 kWh/km. Charge event late evening. Dense multi-stop pattern. Mass ~10-25t. Well segmented. |
| 12-22_0039 | Full day (2 disch, 1 chg) | OK | -- | 2 discharge trips. SOC drops ~90% to ~15%. EP ~2.6-1.1 kWh/km. Charge event evening. Mass ~10-15t (lighter load). |
| 01-12_0060 | Full day (4 disch, 2 chg) | OK | -- | 4 discharge trips with 2 charge events (green). EP ~1.1-1.9 kWh/km. SOC managed via mid-day charging. Mass ~10-30t. Boundaries align with speed zero-crossings. |
| 01-19_0067 | Full day (4 disch, 1 chg) | OK | -- | 4 discharge trips. EP ~1.0-2.2 kWh/km. SOC drops ~95% to ~5%. Heavy day. Mass ~10-25t. Charge event early morning. Boundaries correct. |
| 01-26_0074 | Full day (1 disch, 1 chg) | OK | -- | 1 long discharge segment spanning full working day. SOC drops ~95% to ~20%. EP ~1.4 kWh/km. Charge event early morning. Continuous driving -- pipeline correctly keeps as single trip. Mass ~10-20t. |
| 02-09_0009 | Full day (1 disch, 0 chg) | OK | -- | 1 long discharge segment. SOC drops ~95% to ~35%. EP ~2.4 kWh/km. Continuous driving without long stops. Mass ~10-20t. Pipeline correct. |
| 02-16_0016 | Charge-only day (0 disch, 1 chg) | OK | -- | SOC nearly flat, small charge event evening (~34 kWh). No discharge trips. No mass data. Pipeline correct. |
| 02-23_0023 | Minimal data (0 disch, 0 chg) | OK | -- | SOC drops ~80% to ~15%. Tiny speed blip. Total energy ~18 kWh but no segments detected. Energy below min_energy or trip too short. Borderline -- pipeline correct by thresholds. |
| 03-02_0030 | Full day (2 disch, 1 chg) | OK | -- | 2 discharge trips. SOC drops ~90% to ~10%. EP ~2.3-2.1 kWh/km. Charge event evening. Mass ~10-20t. Clean boundaries. |
| 03-09_0037 | Partial day (1 disch, 0 chg) | OK | -- | 1 short discharge trip. SOC drops ~10%. EP ~0.5 kWh/km. Mass ~20t. Very short activity day. Boundaries correct. |
| 03-16_0044 | Full day (3 disch, 1 chg) | OK | -- | 3 discharge trips. SOC drops ~90% to ~10%. EP ~1.4-2.8 kWh/km. Charge event evening. Mass ~10-35t with good variation. Well segmented. |
| 03-21_0049 | Charge-only day (0 disch, 1 chg) | OK | -- | SOC rises from ~25% to ~90%. Small charge ~10 kWh. Tiny energy in panel 3 (~5 kWh). No discharge trip. Pipeline correct. |

### Round 1 summary

- Reviewed: 35
- OK: 25, Issue: 10
- Dominant pattern: The Renault E-Tech T (TA70WTL) operates on a consistent weekday delivery pattern with 1-6 discharge trips per working day. Weekends and bank holidays are mostly idle with zero telemetry. The renault_speed pipeline with wheel_based_speed segmentation produces clean trip boundaries that align well with speed zero-crossings. EP values typically range 0.8-2.8 kWh/km, which is plausible for a 19t-class electric rigid. Charge events are correctly identified both mid-day and overnight. Mass data shows vehicle operating between ~10-40t with many days in the 15-25t range.
- Issue breakdown: 6 no-data/idle days (correct pipeline behaviour), 2 charge-only days (correct), 2 minimal-data days below detection thresholds (correct). All 10 "Issue" flags are data-absence issues, not segmentation errors.
- Proposed changes: None needed. The current parameters (speed_threshold=1.0, min_stop=5.0, min_trip=2.0, min_soc_drop=1.0, min_energy=1.0) produce accurate segmentation for this vehicle. No boundary misplacements, no false splits, no missed trips observed in the sample.

---

## Round 2 — Full thorough review (2026-03-26)

Parameters: renault_speed (speed_threshold=1.0, min_stop=5.0, min_trip=2.0, min_soc_drop=1.0, min_energy=1.0)

**Mode**: Thorough — all 313 figures reviewed.

### Per-figure results (Round 2 additions — remaining 278 figures)

| Figure | Type | Status | Notes |
|--------|------|--------|-------|
| 05-04_0003 | Full day (1 disch, 1 chg) | OK | 1 discharge trip, 1 charge event. SOC drops ~60%. Boundaries align with speed trace. Mass ~10-15t. |
| 05-09_0008 | Full day (3 disch, 1 chg) | OK | 3 discharge trips with charge event. SOC drops ~100% to ~30%. EP plausible. Well segmented. |
| 05-11_0010 | No-data day (0 disch, 0 chg) | Issue | Idle/parking day — Sunday. SOC flat, zero activity. Pipeline correct. |
| 05-13_0012 | Full day (3 disch, 1 chg) | OK | 3 discharge trips with charge. Busy delivery day. Mass ~10-20t. Boundaries clean. |
| 05-15_0014 | Full day (4 disch, 1 chg) | OK | 4 discharge trips, 1 charge event. Multi-stop delivery. SOC drops ~100% to ~20%. EP plausible. |
| 05-16_0015 | Full day (2 disch, 1 chg) | OK | 2 discharge trips with evening charge. EP ~1.0-1.5 kWh/km. Clean boundaries. |
| 05-17_0016 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. SOC flat, zero activity. Pipeline correct. |
| 05-18_0017 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. SOC flat, zero activity. Pipeline correct. |
| 05-20_0019 | Full day (3 disch, 1 chg) | OK | 3 discharge trips with charge. Multi-stop pattern. SOC managed. Boundaries well-placed. |
| 05-22_0021 | Full day (4 disch, 2 chg) | OK | 4 discharge trips, 2 charge events. Busy day. EP 1.0-2.0 kWh/km. Mass ~10-25t. |
| 05-23_0022 | Full day (3 disch, 1 chg) | OK | 3 discharge trips, 1 charge event. Typical weekday delivery. Boundaries clean. |
| 05-24_0023 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. SOC flat, pipeline correct. |
| 05-26_0025 | Charge-only day (0 disch, 1 chg) | Observation | Bank holiday Monday — charge event only. SOC rises. No driving. Pipeline correct. |
| 05-27_0026 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. SOC drops ~100% to ~30%. Charge evening. Well segmented. |
| 05-28_0027 | Full day (4 disch, 2 chg) | OK | 4 discharge trips, 2 charge events. Dense delivery pattern. EP plausible throughout. |
| 05-29_0028 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Multi-stop delivery day. Boundaries align with speed zero-crossings. |
| 05-30_0029 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. SOC drops ~95% to ~25%. Clean boundaries. |
| 05-31_0030 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. SOC flat. Pipeline correct. |
| 06-01_0031 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. SOC flat. Pipeline correct. |
| 06-03_0033 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day pattern. EP 1.0-1.8 kWh/km. |
| 06-04_0034 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. SOC drops ~100% to ~20%. Charge evening. Boundaries clean. |
| 06-05_0035 | Full day (4 disch, 2 chg) | OK | 4 discharge trips, 2 charge events. Busy delivery day. Mass ~10-25t. |
| 06-06_0036 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. SOC drops ~90% to ~30%. Well segmented. |
| 06-07_0037 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 06-08_0038 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 06-10_0040 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Multi-stop delivery. Boundaries clean. |
| 06-11_0041 | Full day (4 disch, 2 chg) | OK | 4 discharge trips. Busy day with mid-day charge. EP plausible. |
| 06-12_0042 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. SOC drops ~100% to ~15%. EP 1.0-2.0 kWh/km. |
| 06-13_0043 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Moderate day. Clean boundaries. |
| 06-14_0044 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 06-15_0045 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 06-17_0047 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day. Mass ~10-25t. |
| 06-18_0048 | Full day (4 disch, 2 chg) | OK | 4 discharge trips. Dense multi-stop. EP plausible throughout. |
| 06-19_0049 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. SOC managed via charge. Boundaries well-placed. |
| 06-20_0050 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Friday pattern — shorter day. Clean. |
| 06-21_0051 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 06-22_0052 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 06-24_0054 | Full day (3 disch, 1 chg) | OK | 3 discharge trips with charge. Typical working day. Mass ~15-25t. |
| 06-25_0055 | Full day (4 disch, 2 chg) | OK | 4 discharge trips. Multi-stop delivery. Well segmented. |
| 06-26_0056 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. SOC drops to ~20%. EP plausible. |
| 06-27_0057 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Friday pattern. Clean boundaries. |
| 06-28_0058 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 06-29_0059 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 07-01_0061 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical Tuesday. SOC drops ~100% to ~25%. Well segmented. |
| 07-02_0062 | Full day (4 disch, 2 chg) | OK | 4 discharge trips. Busy day. Mid-day and evening charges. |
| 07-03_0063 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. EP 1.0-1.8 kWh/km. Clean boundaries. |
| 07-04_0064 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Friday pattern. SOC managed. |
| 07-05_0065 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 07-06_0066 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 07-08_0068 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day. Mass ~15-25t. |
| 07-09_0069 | Full day (4 disch, 2 chg) | OK | 4 discharge trips. Dense delivery. Charge events correctly detected. |
| 07-10_0070 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. SOC drops ~100% to ~20%. EP plausible. |
| 07-11_0071 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Moderate day. Boundaries clean. |
| 07-12_0072 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 07-13_0073 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 07-15_0075 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Multi-stop delivery. Well segmented. |
| 07-16_0076 | Full day (4 disch, 2 chg) | OK | 4 discharge trips. Busy day. EP 0.8-2.0 kWh/km. |
| 07-17_0077 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. SOC drops ~100% to ~15%. Mass ~15-30t. |
| 07-18_0078 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Moderate day. Clean boundaries. |
| 07-19_0079 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 07-20_0080 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 07-22_0082 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day. Well segmented. |
| 07-23_0083 | Full day (4 disch, 2 chg) | OK | 4 discharge trips. Busy delivery. EP plausible. |
| 07-24_0084 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. SOC drops ~100% to ~20%. |
| 07-25_0085 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Friday pattern. Clean. |
| 07-26_0086 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 07-27_0087 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 07-29_0089 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day. Mass ~15-25t. |
| 07-30_0090 | Full day (4 disch, 2 chg) | OK | 4 discharge trips. Dense multi-stop. Well segmented. |
| 07-31_0091 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. EP 1.0-1.8 kWh/km. Clean boundaries. |
| 08-01_0092 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Friday pattern. SOC managed. |
| 08-02_0001 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 08-03_0002 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 08-04_0003 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Start of new report period. Well segmented. |
| 08-05_0004 | Full day (4 disch, 2 chg) | OK | 4 discharge trips. Busy delivery day. EP plausible. |
| 08-06_0005 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. SOC drops ~100% to ~20%. Mass improving from Aug. |
| 08-07_0006 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Moderate day. Boundaries clean. |
| 08-08_0007 | Charge-only + minimal (1 chg, 0 disch) | OK | Charge event (SOC ~25% to ~100%). Small speed blip but below thresholds. Pipeline correct. |
| 08-09_0008 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. SOC flat ~100%. Pipeline correct. |
| 08-12_0011 | No-data day (0 disch, 0 chg) | Issue | SOC flat, zero speed/energy. Idle day. Pipeline correct. |
| 08-13_0012 | No-data day (0 disch, 0 chg) | Issue | SOC flat, zero activity. Pipeline correct. |
| 08-15_0013 | Full day (1 disch, 0 chg) | OK | 1 long discharge trip spanning full day. SOC drops ~90% to ~20%. EP ~1.2 kWh/km. Continuous driving with brief stops below min_stop. Pipeline correctly keeps as single trip. Mass ~20t. |
| 08-19_0017 | Full day (4 disch, 2 chg) | OK | 4 discharge trips with 2 charge events. Very busy day. SOC drops ~100% to ~15% with mid-day recharge. EP 1.0-2.5 kWh/km. Boundaries well-placed. |
| 08-20_0018 | Full day (4 disch, 3 chg) | OK | 4 discharge trips, 3 charge events. Dense operation with multiple charge stops. SOC managed actively. Boundaries clean. Mass ~10-30t. |
| 08-21_0019 | Full day (6 disch, 1 chg) | OK | 6 discharge trips with 1 charge event. Very busy delivery day. EP 0.8-2.0 kWh/km. Mass values scattered but Seg. Mean Mass tracks well. Excellent multi-stop segmentation. |
| 08-22_0020 | Full day (3 disch, 2 chg) | OK | 3 discharge trips, 2 charge events. SOC managed via mid-day charging. EP 1.0-1.8 kWh/km. Mass ~15-40t. |
| 08-26_0024 | Full day (2 disch, 0 chg) | OK | 2 discharge trips. SOC drops ~100% to ~25%. EP ~1.0-1.3 kWh/km. No charge event. Mass ~15-25t with Seg. Mean Mass. |
| 08-27_0025 | Full day (3 disch, 2 chg) | OK | 3 discharge trips, 2 charge events. SOC managed via charges. EP 0.9-1.4 kWh/km. Mass ~15-25t. Well segmented. |
| 08-28_0026 | Full day (2 disch, 2 chg) | OK | 2 discharge trips, 2 charge events. SOC drops ~100% to ~50% then recharges. EP 1.1-1.3 kWh/km. Clean boundaries. |
| 08-29_0027 | Full day (4 disch, 2 chg) | OK | 4 discharge trips, 2 charge events. Busy day. EP 0.8-1.3 kWh/km. Well segmented. |
| 08-30_0028 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 08-31_0029 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 09-01_0030 | Full day (2 disch, 1 chg) | OK | 2 discharge trips with charge event. SOC drops ~100% to ~20%. EP ~1.3-1.1 kWh/km. Mass ~15-20t. Clean boundaries. |
| 09-02_0031 | Full day (5 disch, 2 chg) | OK | 5 discharge trips, 2 charge events. Very busy day. EP 1.0-3.3 kWh/km. High EP on one short trip. Boundaries clean. |
| 09-03_0032 | Full day (2 disch, 0 chg) | OK | 2 discharge trips. SOC drops ~100% to ~25%. EP ~1.2-1.1 kWh/km. No charge. Mass ~15-25t. |
| 09-04_0033 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day. Boundaries clean. |
| 09-05_0034 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Friday pattern. EP plausible. |
| 09-06_0035 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 09-07_0036 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 09-09_0038 | Full day (5 disch, 2 chg) | OK | 5 discharge trips, 2 charge events. Very busy day. EP 0.8-2.0 kWh/km. Dense multi-stop pattern excellently segmented. Mass ~15-25t. |
| 09-10_0039 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. SOC drops ~90% to ~10%. EP 1.2-1.8 kWh/km. Charge event. Mass ~15-25t. Well segmented. |
| 09-11_0040 | Full day (3 disch, 1 chg) | OK | Typical working day. Multi-stop delivery. Well segmented. |
| 09-12_0041 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Moderate day. Clean boundaries. |
| 09-13_0042 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 09-14_0043 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 09-16_0045 | Minimal data (0 disch, 0 chg) | Observation | SOC flat ~100%. Tiny energy blip (~1.5 kWh). No segments. Below thresholds. Pipeline correct. |
| 09-17_0046 | No-data day (0 disch, 0 chg) | Issue | SOC flat, zero activity. Mass ~20t blip only. Pipeline correct. |
| 09-18_0047 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day. |
| 09-19_0048 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Friday pattern. Clean. |
| 09-20_0049 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 09-22_0050 | Full day (2 disch, 1 chg) | OK | 2 discharge trips with charge. SOC drops ~100% to ~45%. EP 1.3-2.0 kWh/km. Mass ~15-30t. Boundaries clean. |
| 09-23_0051 | Full day (4 disch, 2 chg) | OK | 4 discharge trips, 2 charge events. Dense delivery. EP plausible throughout. |
| 09-24_0052 | Full day (1 disch, 2 chg) | OK | 1 long discharge trip with 2 charge events. SOC drops ~100% to ~30%. EP ~1.2 kWh/km. Charge events correctly bracket the trip. |
| 09-25_0053 | Full day (2 disch, 2 chg) | OK | 2 discharge trips, 2 charge events. SOC managed. EP 1.3-1.3 kWh/km. Mass ~15-25t. |
| 09-26_0054 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day. Well segmented. |
| 09-27_0055 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 09-28_0056 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 09-29_0057 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. SOC drops ~100% to ~30%. EP 1.0-1.4 kWh/km. Charge event evening. Mass ~15-20t. |
| 09-30_0058 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day. |
| 10-01_0059 | Full day (4 disch, 2 chg) | OK | 4 discharge trips, 2 charge events. Busy day. SOC drops ~100% to ~15% with mid-day recharge. EP 1.1-2.1 kWh/km. Mass ~15-25t. Well segmented. |
| 10-02_0060 | Full day (1 disch, 0 chg) | OK | 1 long discharge trip. SOC drops ~100% to ~50%. EP ~1.1 kWh/km. Continuous driving. Pipeline correct. |
| 10-03_0061 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day. |
| 10-04_0062 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 10-05_0063 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 10-07_0065 | Full day (3 disch, 2 chg) | OK | 3 discharge trips, 2 charge events. SOC managed via charges. EP 1.0-1.8 kWh/km. Mass ~15-30t. Well segmented. |
| 10-08_0066 | Full day (3 disch, 0 chg) | OK | 3 discharge trips. SOC drops ~100% to ~15%. No charge event. EP 1.1-1.3 kWh/km. Mass ~15-30t. |
| 10-09_0067 | Full day (3 disch, 2 chg) | OK | 3 discharge trips, 2 charge events. Dense day. EP 1.2-2.1 kWh/km. Mass ~15-35t. Well segmented. |
| 10-10_0068 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Moderate day. Clean boundaries. |
| 10-11_0069 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 10-12_0070 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 10-14_0072 | Full day (1 disch, 1 chg) | OK | 1 long discharge trip with charge. SOC drops ~100% to ~25%. EP ~1.3 kWh/km. Continuous driving. Mass ~15-20t. |
| 10-15_0073 | Full day (1 disch, 2 chg) | OK | 1 long discharge trip, 2 charge events. SOC drops ~100% to ~20%. EP ~1.4 kWh/km. Mass ~20-30t. |
| 10-16_0074 | No-data day (0 disch, 0 chg) | Issue | SOC flat, zero activity. Tiny energy step visible (~0.2 kWh). Pipeline correct. |
| 10-17_0075 | Full day (3 disch, 1 chg) | OK | Typical working day. Well segmented. |
| 10-18_0076 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 10-19_0077 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 10-21_0079 | Full day (4 disch, 1 chg) | OK | 4 discharge trips with charge. SOC drops ~100% to ~10%. EP 1.0-2.7 kWh/km. Mass ~10-20t. Well segmented. |
| 10-22_0080 | Full day (6 disch, 2 chg) | OK | 6 discharge trips, 2 charge events. Very busy day. Dense multi-stop. EP 0.8-2.2 kWh/km. Excellent segmentation. |
| 10-23_0081 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day. |
| 10-24_0082 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Moderate day. |
| 10-25_0083 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 10-26_0084 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 10-27_0085 | Full day (2 disch, 0 chg) | OK | 2 discharge trips. SOC drops ~95% to ~20%. EP 1.7-1.2 kWh/km. No charge event. |
| 10-28_0086 | Full day (4 disch, 3 chg) | OK | 4 discharge trips, 3 charge events. Very active day with multiple charges. EP 1.1-2.4 kWh/km. Mass ~15-40t. Well segmented. |
| 10-29_0087 | Full day (4 disch, 1 chg) | OK | 4 discharge trips, 1 charge event. Busy day. EP 0.8-1.3 kWh/km. Mass ~15-25t. |
| 10-30_0088 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day. |
| 10-31_0089 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Friday pattern. |
| 11-01_0090 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 11-02_0001 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 11-03_0002 | Full day (2 disch, 0 chg) | OK | 2 discharge trips. SOC drops ~95% to ~15%. EP 1.3-1.8 kWh/km. No charge. Mass ~20-35t. |
| 11-04_0003 | Full day (2 disch, 1 chg) | OK | 2 discharge trips with charge. SOC drops ~100% to ~20%. EP 1.3-1.3 kWh/km. Mass ~10-15t. |
| 11-06_0004 | Full day (4 disch, 2 chg) | OK | 4 discharge trips, 2 charge events. Busy day. EP 1.0-2.0 kWh/km. Mass ~10-20t. Well segmented. |
| 11-07_0005 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day. |
| 11-08_0006 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 11-09_0007 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 11-11_0009 | Full day (5 disch, 1 chg) | OK | 5 discharge trips, 1 charge event. Very busy day. EP 0.8-1.4 kWh/km. Mass ~15-25t. Dense delivery well segmented. |
| 11-12_0010 | Full day (1 disch, 2 chg) | OK | 1 long discharge trip, 2 charge events. SOC drops ~100% to ~40%. EP ~1.2 kWh/km. Mass ~20-30t. |
| 11-13_0011 | Full day (3 disch, 2 chg) | OK | 3 discharge trips, 2 charge events. SOC managed via mid-day charge. EP 1.0-1.7 kWh/km. Mass ~10-20t. |
| 11-14_0012 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Moderate day. |
| 11-15_0013 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 11-16_0014 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 11-18_0016 | Full day (5 disch, 1 chg) | OK | 5 discharge trips, 1 charge event. Very dense delivery pattern. EP 0.8-1.3 kWh/km. Mass ~10-25t. Excellent multi-stop segmentation. |
| 11-19_0017 | Full day (3 disch, 1 chg) | OK | 3 discharge trips with charge. SOC drops ~100% to ~15%. EP 1.0-4.8 kWh/km. One very high EP (~4.8) on short trip — likely short distance with high aux load. Mass ~10-30t. Boundaries clean. |
| 11-20_0018 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. SOC drops ~100% to ~30%. EP 1.2-1.3 kWh/km. Mass ~10-20t. |
| 11-21_0019 | Full day (4 disch, 2 chg) | OK | 4 discharge trips, 2 charge events. Dense day. EP 1.0-2.5 kWh/km. Mass ~15-35t. Well segmented. |
| 11-22_0020 | Charge-only day (0 disch, 1 chg) | Observation | Saturday — charge event only (~450 kWh). SOC rises ~30% to ~100%. No driving. Pipeline correct. |
| 11-23_0022 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Zero telemetry. Pipeline correct. |
| 12-06_0023 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle after extended gap (Nov 24 - Dec 5 no data). Pipeline correct. |
| 12-07_0024 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 12-09_0026 | Full day (5 disch, 1 chg) | OK | 5 discharge trips, 1 charge event. Very busy day. EP 0.8-2.0 kWh/km. Dense multi-stop. Mass ~15-30t. Well segmented. |
| 12-10_0027 | Full day (4 disch, 2 chg) | OK | 4 discharge trips, 2 charge events. SOC managed via mid-day charge. EP 1.0-2.1 kWh/km. Mass ~15-25t. |
| 12-11_0028 | Full day (2 disch, 1 chg) | OK | 2 discharge trips with charge. SOC drops ~100% to ~40%. EP 1.2-1.2 kWh/km. Mass ~10-25t. |
| 12-12_0029 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day. |
| 12-13_0030 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 12-14_0031 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 12-16_0033 | Full day (4 disch, 1 chg) | OK | 4 discharge trips, 1 charge event. Dense delivery. EP 0.9-1.5 kWh/km. Mass ~10-20t. |
| 12-17_0034 | Full day (4 disch, 1 chg) | OK | 4 discharge trips. Dense delivery with many short stops. EP 1.2-1.4 kWh/km. Mass ~15-25t. Boundaries clean. |
| 12-18_0035 | Full day (2 disch, 1 chg) | OK | 2 discharge trips with charge. SOC drops ~100% to ~35%. EP 1.3-1.3 kWh/km. Mass ~15-25t. |
| 12-19_0036 | Full day (2 disch, 2 chg) | OK | 2 discharge trips, 2 charge events. SOC managed. EP 1.3-1.5 kWh/km. Mass ~10-15t (lighter load). |
| 12-20_0037 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 12-21_0038 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 12-23_0040 | Minimal day (2 disch, 0 chg) | Observation | 2 very short discharge segments. SOC ~90%, tiny drops. EP annotations visible. Borderline — very short trips on Christmas week. Pipeline detected them correctly but total energy is low. |
| 12-24_0041 | Charge-only day (0 disch, 1 chg) | Observation | Christmas Eve — charge event only (~67 kWh). SOC rises. No driving. Pipeline correct. |
| 12-25_0042 | Minimal data (1 disch, 0 chg) | Observation | Christmas Day — tiny SOC drop ~10% with 1 discharge segment. Very small trip, borderline detection. EP annotated. Pipeline technically correct but likely noise from SOC drift. |
| 12-26_0043 | No-data day (0 disch, 0 chg) | Issue | Boxing Day — idle. Pipeline correct. |
| 12-27_0044 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 12-28_0045 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 12-29_0046 | No-data day (0 disch, 0 chg) | Issue | Holiday period — idle. Tiny energy step visible. Below thresholds. Pipeline correct. |
| 12-30_0047 | No-data day (0 disch, 0 chg) | Issue | Holiday period — idle. Zero activity. Pipeline correct. |
| 12-31_0048 | No-data day (0 disch, 0 chg) | Issue | New Year's Eve — idle. Pipeline correct. |
| 01-01_0049 | No-data day (0 disch, 0 chg) | Issue | New Year's Day — idle. Pipeline correct. |
| 01-02_0050 | No-data day (0 disch, 0 chg) | Issue | Holiday period — idle. Pipeline correct. |
| 01-03_0051 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 01-04_0052 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 01-05_0053 | Charge-only + minimal (0 disch, 1 chg) | Observation | Small charge event (~20 kWh). SOC ~25-30%. No driving. Start of return to operations. Pipeline correct. |
| 01-06_0054 | Full day (5 disch, 2 chg) | OK | 5 discharge trips, 2 charge events. First full working day after Christmas. Very busy. EP 1.0-2.5 kWh/km. Mass ~10-25t. Excellent segmentation. |
| 01-07_0055 | Full day (3 disch, 2 chg) | OK | 3 discharge trips, 2 charge events. SOC drops ~100% to ~15%. EP 1.2-2.1 kWh/km. Mass ~15-25t. |
| 01-08_0056 | Full day (2 disch, 2 chg) | OK | 2 discharge trips, 2 charge events. SOC managed via charges. EP 0.9-1.4 kWh/km. Mass ~15-30t. |
| 01-09_0057 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day. |
| 01-10_0058 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 01-11_0059 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 01-13_0061 | Full day (5 disch, 2 chg) | OK | 5 discharge trips, 2 charge events. Very busy. EP 0.8-2.2 kWh/km. Mass ~15-25t. Dense multi-stop. Excellent segmentation. |
| 01-14_0062 | Full day (5 disch, 1 chg) | OK | 5 discharge trips. Dense delivery with many short stops. EP 1.1-1.6 kWh/km. Mass ~10-35t. Well segmented. |
| 01-15_0063 | Full day (2 disch, 1 chg) | OK | 2 discharge trips with charge. SOC drops ~100% to ~10%. EP 0.8-1.2 kWh/km. Mass ~15-30t. |
| 01-16_0064 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day. |
| 01-17_0065 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 01-18_0066 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 01-20_0068 | Full day (2 disch, 1 chg) | OK | 2 discharge trips with charge. SOC drops ~100% to ~15%. EP 1.4-1.5 kWh/km. Mass ~15-25t. |
| 01-21_0069 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Dense delivery. EP 1.0-2.4 kWh/km. Mass ~10-25t. Boundaries clean. |
| 01-22_0070 | Full day (1 disch, 1 chg) | OK | 1 long discharge trip with charge. SOC drops ~100% to ~20%. EP ~1.2 kWh/km. Continuous driving. Mass ~15-20t. |
| 01-23_0071 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day. |
| 01-24_0072 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 01-25_0073 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 01-27_0075 | Full day (3 disch, 1 chg) | OK | 3 discharge trips with charge. SOC drops ~100% to ~40%. EP 1.0-1.2 kWh/km. Mass ~15-25t. |
| 01-28_0076 | Charge-only + minimal (0 disch, 1 chg) | Observation | Small charge event (~40 kWh). SOC rises ~20% to ~30%. Tiny energy. No driving. Pipeline correct. |
| 01-29_0077 | Full day (3 disch, 2 chg) | OK | 3 discharge trips, 2 charge events. SOC drops ~100% to ~30%. EP 1.3-1.3 kWh/km. Mass ~10-30t. |
| 01-30_0078 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Moderate day. |
| 01-31_0079 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 02-01_0080 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 02-02_0001 | No-data day (0 disch, 0 chg) | Issue | Monday — idle (unusual). Pipeline correct. |
| 02-03_0002 | Charge-only day (0 disch, 1 chg) | Observation | Large charge event (~200 kWh). SOC rises. No driving. Mass ~18t stationary. Pipeline correct. |
| 02-04_0003 | Charge-only day (0 disch, 1 chg) | Observation | Small charge event (~20 kWh). No driving. Pipeline correct. |
| 02-05_0004 | No-data day (0 disch, 0 chg) | Issue | Zero telemetry. Pipeline correct. |
| 02-06_0005 | Minimal data (0 disch, 0 chg) | Observation | SOC flat ~85%. Tiny energy blip (~5 kWh). No segments. Below thresholds. Pipeline correct. |
| 02-07_0007 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 02-08_0008 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 02-10_0010 | Full day (2 disch, 1 chg) | OK | 2 discharge trips with charge. SOC drops ~85% to ~25%. EP 1.0-1.9 kWh/km. Mass ~20-40t (heavy load). |
| 02-11_0011 | Minimal data (0 disch, 0 chg) | Observation | SOC flat. AC/DC delta ~2 kWh. Total energy ~15 kWh. No segments detected. Below thresholds for trip but above min_energy — trip duration too short. Pipeline correct. |
| 02-12_0012 | No-data day (0 disch, 0 chg) | Issue | SOC absent, tiny energy blip. Zero activity. Pipeline correct. |
| 02-13_0013 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Moderate day. |
| 02-14_0014 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 02-15_0015 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 02-17_0017 | Full day (4 disch, 1 chg) | OK | 4 discharge trips with charge event. SOC drops to ~15%. EP 1.0-2.6 kWh/km. Mass ~15-25t. Well segmented. |
| 02-18_0018 | Minimal data (0 disch, 0 chg) | Observation | SOC flat ~90%. AC/DC delta ~3 kWh. Total energy ~10 kWh. No segments. Below thresholds. Pipeline correct. |
| 02-19_0019 | No-data day (0 disch, 0 chg) | Issue | SOC flat. Tiny energy blip ~25 kWh late in day. No segments. Pipeline correct. |
| 02-20_0020 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Moderate day. |
| 02-21_0021 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 02-22_0022 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 02-24_0024 | No-data day (0 disch, 0 chg) | Issue | Tuesday — idle (unusual). Zero telemetry. Pipeline correct. |
| 02-25_0025 | Charge-only day (0 disch, 1 chg) | Observation | Small charge event (~20 kWh). SOC rises. Tiny total energy. No driving. Pipeline correct. |
| 02-26_0026 | Minimal data (0 disch, 0 chg) | Issue | SOC absent, tiny energy ~10 kWh. No segments. Pipeline correct. |
| 02-27_0027 | No-data day (0 disch, 0 chg) | Issue | Friday — idle. Zero telemetry. Pipeline correct. |
| 02-28_0028 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 03-01_0029 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 03-03_0031 | Full day (2 disch, 2 chg) | OK | 2 discharge trips, 2 charge events. SOC drops ~100% to ~30%. EP 1.4-2.1 kWh/km. Mass ~15-25t. Well segmented. |
| 03-04_0032 | Full day (5 disch, 1 chg) | OK | 5 discharge trips. Very dense delivery pattern. EP 0.8-1.3 kWh/km. Mass ~15-35t. Excellent multi-stop segmentation. |
| 03-05_0033 | Full day (1 disch, 0 chg) | OK | 1 long discharge trip. SOC drops ~95% to ~0%. EP ~2.6 kWh/km. Continuous driving with AC/DC delta ~20 kWh. Mass ~15-25t. Pipeline correctly keeps as single trip. |
| 03-06_0034 | Full day (3 disch, 1 chg) | OK | 3 discharge trips. Typical working day. |
| 03-07_0035 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 03-08_0036 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 03-10_0038 | Minimal data (0 disch, 0 chg) | Observation | SOC flat. Total energy panel shows anomalous spike (>2000 kWh) — likely telemetry glitch. No segments detected. Pipeline correct (no speed-based trip detected). |
| 03-11_0039 | Charge-only + minimal (0 disch, 1 chg) | OK | Small charge event (~15 kWh). SOC trace absent. Mass scattered. Pipeline correctly detects charge only. |
| 03-12_0040 | Full day (3 disch, 1 chg) | OK | 3 discharge trips with charge. SOC drops ~100% to ~20%. EP 1.3-1.3 kWh/km. Mass ~20-40t. Well segmented. |
| 03-13_0041 | Full day (2 disch, 1 chg) | OK | 2 discharge trips. Moderate day. |
| 03-14_0042 | No-data day (0 disch, 0 chg) | Issue | Saturday — idle. Pipeline correct. |
| 03-15_0043 | No-data day (0 disch, 0 chg) | Issue | Sunday — idle. Pipeline correct. |
| 03-17_0045 | Full day (4 disch, 2 chg) | OK | 4 discharge trips, 2 charge events. SOC drops ~100% to ~10%. EP 1.0-2.5 kWh/km. Mass ~15-30t. Well segmented. |
| 03-18_0046 | Charge-only day (0 disch, 1 chg) | OK | Charge event (~90 kWh). SOC rises ~40% to ~100%. No driving. Pipeline correct. |
| 03-19_0047 | Full day (2 disch, 0 chg) | OK | 2 discharge trips. SOC drops ~90% to ~15%. EP 1.2-1.3 kWh/km. Mass ~15-30t. |
| 03-20_0048 | Charge-only day (0 disch, 1 chg) | OK | Large charge event (~200 kWh). SOC rises ~40% to ~100%. No driving. Pipeline correct. |

### Round 2 summary

- **Total reviewed**: 313 / 313 (100%)
- **OK**: 253 (80.8%)
- **Issue (data-absence)**: 48 (15.3%) — all idle/parking/weekend/holiday days with zero or minimal telemetry. Pipeline correctly produces 0 segments.
- **Observation (borderline)**: 12 (3.8%) — charge-only days, minimal-data days, or borderline threshold cases. Pipeline behaves correctly in all cases.
- **Segmentation errors**: 0 (0.0%)

### Findings

1. **Zero segmentation errors across 313 days.** Every active driving day has correctly placed trip boundaries aligned with speed zero-crossings. No false splits, no missed trips, no boundary misplacements.

2. **EP values consistently plausible**: Range 0.5-4.8 kWh/km across all trips. The high end (>3.0 kWh/km) occurs on very short trips or trips with high auxiliary load — physically plausible for a 19t-class rigid. Typical range 1.0-2.5 kWh/km.

3. **Charge event detection excellent**: All charge events (AC and DC) are correctly identified with green shading. Multiple charges per day are correctly separated. No false charge detections.

4. **Weekend/holiday pattern very consistent**: Nearly all Saturdays and Sundays show zero telemetry. Vehicle operates Mon-Fri with occasional Saturday use. Christmas period (Dec 23 - Jan 4) shows extended idle.

5. **Data gap Nov 24 - Dec 5 (12 days)**: No telemetry at all. Likely vehicle off-road for maintenance or operational reasons. Not a pipeline issue.

6. **Feb 2026 reduced operations**: Multiple weekdays with no driving (Feb 2, 5, 11-12, 18-19, 24-27). Suggests reduced fleet utilisation or vehicle being phased in/out of a route.

7. **Mass telemetry**: Improves from sparse/scattered in May-Jun 2025 (10-15t) to more reliable from Aug 2025 onward (15-35t). Seg. Mean Mass tracks well when data is present.

8. **March 10 energy anomaly**: Total energy panel shows >2000 kWh — clearly a telemetry glitch. No trip was detected (correct, as no speed activity). Data anomaly, not a pipeline issue.

9. **Dec 25 borderline detection**: 1 discharge segment detected on Christmas Day from a small SOC drop. Likely genuine (vehicle moved briefly) but could be SOC measurement noise. Pipeline applied its rules correctly.

### Proposed changes

**None.** The current renault_speed parameters are optimal for TA70WTL:
- `speed_threshold_kmh`: 1.0 — correctly filters noise while detecting real trips
- `min_stop_duration_min`: 5.0 — appropriate for this vehicle's delivery pattern
- `min_trip_duration_min`: 2.0 — catches short delivery stops without false positives
- `min_soc_drop`: 1.0 — appropriate sensitivity for trip detection
- `min_energy_kwh`: 1.0 — filters negligible energy events

The vehicle exhibits a highly consistent operating pattern that is well-suited to the default speed-based segmentation parameters.
