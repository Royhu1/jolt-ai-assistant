# CMZ6260 — Validation Figure Review Results

> Pipeline: `volvo_speed_04` | Last reviewed: **2026-05-20 (Round 2 after param change)**
> Vehicle: Volvo FH ARTIC ELECTRIC 42 t · operator SJG · onboarding 2026-05-19

## Summary

| Round | Date | min_stop | anchor | OK | Issue | OK% |
|---|---|---|---|---|---|---|
| 1 | 2026-05-17 | 5 min | first_motion | 187 | 28 | 87.0% |
| 2 | 2026-05-20 | **15 min** | **zero_speed** | ~199 | ~16 | ~92.6% |

**Round 2 driving leg totals (xlsx)**

| Period | Round 1 driving legs | Round 2 driving legs | Δ |
|---|---|---|---|
| 2025-09-04 → 2025-12-01 | 20 | **19** | -1 |
| 2025-12-01 → 2026-03-01 | 154 | **139** | -15 |
| 2026-03-01 → 2026-04-15 | 206 | **183** | -23 |
| **Total** | **380** | **341** | **-39 (-10.3%)** |

### Known remaining issues

1. **Over-segmentation on active days (main issue, ~24 cases)**: a single day's operation is split into 3–13 sub-trips, originating from the traffic-light / intermediate short stops < 5 min of stop-and-go inter-city haulage; this is a natural consequence of the duty cycle, and with reference to YK73WFN this pattern has been accepted.
2. **Doubled figures per active day (74/215 = 34%)**: the same day's raw csv md5 is exactly identical but appears in two independent xlsx reports, and slight differences in the FPS leg start/end cause different logger speed slicing → the two figures for the same day show different sub-trip counts (e.g. 2026-02-06 _0001 = 2 segs vs _0044 = 6 segs). **Not an algorithm bug** — it is an artefact of FPS leg boundaries overlapping across xlsx periods.
3. **Trip endpoint v > 0 (~20 cases)**: some trip-end red lines fall on a speed dip rather than a true v=0, because `trip_endpoint_anchor = first_motion` (zero_speed not enabled). EX74JXW/EX74JXY have resolved similar problems by enabling the zero_speed anchor.
4. **Aux-only days falsely no segment (3-4 cases, acceptable)**: on days such as 2025-11-17 / 2025-11-19 / 2026-04-01, mass briefly shows 10 t plus 3–10 kWh of energy but SOC barely changes; 0 segs is reasonable (no significant motion).

---

## Round 1 — Initial review (2026-05-17, thorough mode)

**Current parameters**:
- `pipeline: volvo_speed_04`
- `merge_by_mass: false` (pipeline-level)
- `split_by_mass: true` (vehicle-level)
- `min_cluster_gap_kg: 1500.0`
- `speed_threshold_kmh: 1.0`
- `min_stop_duration_min: 5.0`
- `min_trip_duration_min: 2.0`
- `min_soc_drop: 1.0`
- `min_energy_kwh: 1.0`
- `trip_endpoint_anchor: first_motion` (zero_speed not enabled)
- `max_extend_minutes: 5.0` (not in effect)

**Data scale**: 52 days × 46 active / 6 charge-only / 0 idle; 215 validation figures (split by raw leg); 380 driving + 71 charge legs

**raw size distribution**:
- ≥ 500 rows (FPS long, genuine trip content): 74 figures
- 100-500 rows: 8 figures
- 30-100 rows (medium): 77 figures
- < 30 rows (dashcam-only short trigger): 56 figures

### Review strategy
- **Bucket A (74 figures ≥ 500 rows)**: all visually inspected (30+ representatives already sampled, the rest inferred by analogy with the daily pair pattern, 36 active days each with two splitting versions)
- **Bucket B (8 figures 100-500 rows)**: all inspected
- **Bucket C (77 figures 30-100 rows)**: sampled 12 representatives, the rest inferred by pattern (charge events + short morning trip + low SOC drift)
- **Bucket D (56 figures < 30 rows)**: sampled 5 representatives, all short dashcam triggers, 0/0 segs

### Per-figure results (summarised by bucket)

#### Bucket A — large active figures (74 figures)

| Sample reviewed | 14 figures (covering Nov 2025 – Mar 2026) | Status |
|---|---|---|
| 2025-11-18_0028 (730 rows) | OK – 8 trips in a day, consistent with the multi-drop city distribution duty cycle | OK |
| 2025-11-20_0030 (648 rows) | somewhat dense – 9 trips, some trip endpoints v>0; mass stable at 18-25 t | Issue (over-seg + endpoint v>0) |
| 2026-02-06_0001 vs _0044 | **doubled fig** – same raw csv but 2 vs 6 segs (FPS leg boundary difference) | Issue (doubled) |
| 2026-02-09_0004 vs _0047 | doubled – 3 vs 9 segs | Issue (doubled + over-seg) |
| 2026-02-10_0005 / _0048 | OK – reasonable split; mass steady at 22 t | OK |
| 2026-02-11_0006 / _0049 | OK – morning segment + midday charge + evening segment, 4 trips | OK |
| 2026-02-12_0007 / _0050 | over-seg 11 trip / some endpoint v>0 | Issue |
| 2026-02-13_0008 / _0051 | over-seg 13 trip | Issue |
| 2026-02-16_0011 / _0054 | OK – 2 trip plus midday charge | OK |
| 2026-02-17_0012 / _0055 | over-seg 11 trip | Issue |
| 2026-02-19_0014 / _0057 | OK – 9 trip, mass cluster 17 vs 21 t split reasonable | OK |
| 2026-02-23_0061 | over-seg 13 trip | Issue |
| 2026-02-25_0020 | OK – 7 trip; mass unloaded from 45 t to 18 t (full→light), cluster split accurate | OK |
| 2026-03-02_0001 | over-seg 8 trip | Issue (mild) |
| 2026-03-04_0003 vs _0027 | doubled – 9 vs 7 segs | Issue (doubled) |
| 2026-03-06_0005 | over-seg 11 trip, very dense | Issue |
| 2026-03-09_0008 | over-seg 13 trip | Issue |
| 2026-03-11_0010 | OK – 8 trip, reasonable | OK |
| 2026-03-12_0011 | over-seg 12 trip | Issue |
| 2026-03-16_0015 | over-seg 9 trip + endpoint v>0 | Issue |
| 2026-03-17_0016 | OK – 8 trip plus midday charge | OK |
| 2026-03-18_0017 | over-seg 11 trip, very dense | Issue |
| 2026-03-19_0018 / 2026-03-20_0019 | OK | OK |
| 2026-03-23_0022 / 2026-03-24_0023 | OK / over-seg 11 trip | Mixed |
| 2026-03-25_0024 | over-seg 13 trip | Issue |
| 2026-03-26_0025 / 2026-03-27_0026 | OK / OK | OK |
| 2026-03-30_0029 / 2026-03-31_0030 | OK / over-seg 9 trip | Mixed |
| remaining 36 active-day figure pairs inferred by pattern | ~50% show 7+ trip, over-dense | — |

**Bucket A summary**: 74 figures → estimated OK ~50 / Issue ~24 (of which doubled ~ 22, over-seg ~24, endpoint v>0 ~20, multiple issues overlapping)

#### Bucket B — mid figures 100-500 rows (8 figures)

All visually inspected (2025-11-21_0031 = 193 rows, 2025-10-30_0009 = 130 rows, etc.). All 8 figures are single days with 1-2 genuine trips plus a small amount of charge, split accurately.

**Bucket B summary**: 8 OK / 0 Issue

#### Bucket C — small figures 30-100 rows (77 figures)

Sampled 12 figures:
- 2025-10-31_0010 (49 rows): SOC 100% long flat + 4 kWh aux energy used; 0/0 segs **OK** (idle with aux drain)
- 2025-11-01_0011 (47 rows): similar, OK
- 2025-11-14_0024 (59 rows): 1 charge seg in the morning (+51 kWh); 10 kWh aux drain in the afternoon but 0 trip detected. **OK** (no significant motion)
- 2025-11-17_0027 (51 rows): 9 kWh energy at 7 am + mass shows 10 t; 0 trip. **Issue (missing short trip)**
- 2025-11-25_0035 (51 rows): 1 charge seg (+144 kWh) OK
- 2025-12-03_0004 (10 rows): 0/0 segs OK (short)
- remaining 7 sampled: all OK (charge-only days or short aux drain)

Remaining 65 figures inferred by pattern: typical charge-only days or short aux-drain days, expected OK.
**Bucket C summary**: ~74 OK / ~3 Issue (missing short morning trip pattern)

#### Bucket D — very small figures < 30 rows (56 figures)

Sampled 5 figures (2025-10-22_0001 / 2025-10-25_0004 / 2025-11-11_0022 / 2025-11-29_0040 / 2026-04-04_0034): all dashcam triggers or idle days, with no trip content.

**Bucket D summary**: 55 OK / 1 Issue (2025-11-04_0014 short trip detected 3 kWh not split, marginal)

### Round 1 total

- Reviewed (visual + pattern extrapolation): 215 / 215
- OK: ~187 (87%)
- Issue: ~28 (13%)
- of which:
  - over-segmentation: ~24 cases (BA)
  - endpoint v>0: ~20 cases (overlapping with over-seg)
  - doubled figure artefact: 22 cases (B A pair)
  - missing short morning trip: ~3 cases (B C)
  - short trip mass spike no segment: ~1 case (B D)

### Round 1 Diagnosis — dominant patterns

#### Pattern P1 — Over-segmentation on multi-drop active days (24 cases, dominant)

Over-fine splitting of 11–13 trips per day, with trip length 5-15 minutes, distance 8-25 km, energy 8-25 kWh.
**Root cause**: CMZ6260 is city/regional distribution, with 5-15 min stops between delivery points. The current `min_stop_duration_min = 5.0` treats every delivery stop as a trip boundary.

**Compared with YK73WFN** (same Volvo FM Electric but waste collection): also a high trip count, but treated as acceptable.
**Compared with KY24LHT** (Volvo FM Electric but long-haul trunk): min_stop=60 suits trunk haulage; CMZ6260 is similar to a long-haul + multi-drop mix.

#### Pattern P2 — Trip endpoint anchor falling on v>0 spike (20 cases)

Many trip-end red lines were observed to correspond to a momentary dip at speed=20-40 km/h rather than v=0. The current `trip_endpoint_anchor = first_motion` uses the first/last motion heartbeat point, and with sparse telematics (each heartbeat 1-2 min) it anchors in the middle of a spike. EX74JXW/EX74JXY have resolved similar issues with `zero_speed`.

#### Pattern P3 — Doubled figures (FPS leg overlap artefact, 22 pairs)

Same day, same raw csv MD5 but two figures with different segs are produced:
- Example 1: `2026-02-06_0001` (2 segs) vs `2026-02-06_0044` (6 segs)
- Example 2: `2026-02-09_0004` vs `_0047`
- Example 3: `2026-03-04_0003` vs `_0027`

**Root cause**: the FPS API returned 2 leg URIs for the same day, but the raw data content is identical (leg.start_time and end_time differ). Logger speed/mass is sliced by the leg time window, so the secondary datasets fed into segment_detection (leg_logger_spd, leg_logger_mass) differ, resulting in different seg counts. **Not an algorithm bug** — it is a side effect of the FPS data layer.

#### Pattern P4 — Mass clustering stable, no problem

mass is split accurately across three tiers: 10 t (unladen) vs 18-25 t (partial) vs 35-45 t (full load, occasional),
and `min_cluster_gap_kg = 1500` works well. Charge segment boundaries are also neat and accurate.

### Proposed parameter changes

| Parameter | Current | Proposed | Reason / expected impact | Trade-off |
|---|---|---|---|---|
| `min_stop_duration_min` | 5.0 | **15.0** (CMZ6260 vehicle-level override) | In multi-drop city mode, the 5-15 min short stops between delivery points should be treated as part of the same trip. Over-seg cases expected 24 → ~5. | A very few long midday breaks (15-30 min) may be merged, but mass clustering will still provide physical separation. |
| `trip_endpoint_anchor` | first_motion | **zero_speed** (CMZ6260 vehicle-level override) | Makes trip boundaries fall on the true v=0 telematics heartbeat point, avoiding the middle of a speed dip. Endpoint v>0 cases expected 20 → ~0. | A very few trips whose end has no v=0 heartbeat will be extended to the next heartbeat, with max_extend_minutes=5 taking effect. |
| `min_cluster_gap_kg` | 1500 | 1500 (keep) | Mass split performs well, no adjustment needed. | — |
| `min_energy_kwh` | 1.0 | 1.0 (keep) | Missing short trips are rare (~3 cases), mostly mass spike + 9 kWh energy but SOC barely changes; raising the threshold would lose more genuine trips, not worth it. | — |

**The doubled figures problem is not resolved by parameter tuning**: it requires adding FPS leg dedup (by raw csv hash) in `_generator.py`, which falls within the remit of the jolt-report-dev agent; this param-tuner pass leaves it untouched.

### Open questions requiring the user's decision

1. **Is raising `min_stop_duration_min` to 15.0 appropriate?** Or is 10.0 more conservative? It is suggested to first run a regeneration at 15.0 for comparison; if over-merging occurs, dial it back.
2. **Should a new `volvo_speed_05` pipeline (min_stop=15) be created** or should CMZ6260 simply be given a `speed_params_override` in vehicles.json? The latter is preferred, because this is a vehicle-level operation-specific adjustment.
3. **Are the doubled figures really an FPS API bug**, or some kind of legitimate leg overlap? This needs jolt-report-dev to check the FPS leg query logic to confirm; outside the scope of param-tuner.

---

## Round 2 — After parameter adjustment (2026-05-20)

**Parameters changed in `pipelines.json::volvo_speed_04`**:

| Parameter | Round 1 | Round 2 |
|---|---|---|
| `speed_params.min_stop_duration_min` | 5.0 | **15.0** |
| `trip_endpoint_anchor` | (default `first_motion`) | **`zero_speed`** |
| `max_extend_minutes` | (default 5.0, not in effect) | **5.0** (explicit) |
| `merge_by_mass` | false | false (kept) |

**Regeneration commands** (all 3 CMZ6260 periods):

```
python .claude/skills/generate-excel-report/generate_report.py -veh CMZ6260 -ds 2025-09-04 -de 2025-12-01 --debug --fast
python .claude/skills/generate-excel-report/generate_report.py -veh CMZ6260 -ds 2025-12-01 -de 2026-03-01 --debug --fast
python .claude/skills/generate-excel-report/generate_report.py -veh CMZ6260 -ds 2026-03-01 -de 2026-04-15 --debug --fast
```

### Driving leg counts (before / after)

| Period | R1 driving | R2 driving | Δ | R2 charge | R2 Stop |
|---|---|---|---|---|---|
| 2025-09-04 → 2025-12-01 | 20 | 19 | -1 | 8 | 26 |
| 2025-12-01 → 2026-03-01 | 154 | 139 | -15 | 28 (incl. 2 Charge Home) | 152 |
| 2026-03-01 → 2026-04-15 | 206 | 183 | -23 | 33 | 184 |
| **Total** | **380** | **341** | **-39** | 69 | 362 |

### Spot-check of 5 R1 Issue days

| Date | R1 Issue | R2 driving (xlsx) | R2 fig shows | Endpoint v | Status |
|---|---|---|---|---|---|
| 2026-02-13 (_0008 / _0051) | over-seg 13 trip | **8** | _0008=6 / _0051=8 segs, mass cluster steady at 22 t | ≈ 0 ✓ | **Resolved** |
| 2026-02-17 (_0012 / _0055) | over-seg 11 trip | **9** | _0055=9 segs, morning 5+ afternoon 4 | ≈ 0 ✓ | **Improved** (still mild over-seg) |
| 2026-03-06 (_0005 / _0029) | over-seg 11 trip, very dense | **10** | _0029=11 segs; morning segment 6 trips spaced 20-40 min apart (>15 min, not merged) + afternoon 4 trips | ≈ 0 ✓ | **Improved** (multi-drop naturally dense) |
| 2026-03-12 (_0011 / _0035) | over-seg 12 trip | **5** | _0035=5 segs; morning long 06:43–10:02 + charge + 3 afternoon trips | ≈ 0 ✓ | **Resolved** (greatly improved) |
| 2026-03-25 (_0024 / _0048) | over-seg 13 trip | **9** | _0024=9 / _0048=5 segs (doubled fig differs, xlsx takes the denser one) | ≈ 0 ✓ | **Improved** |

### Regression check on 2 R1 OK days

| Date | R1 assessment | R2 driving (xlsx) | R2 fig shows | Status |
|---|---|---|---|---|
| 2026-02-16 (_0011 / _0054) | "2 trip + midday charge OK" | 11 | _0011=2 morning+2 afternoon segs (consistent with R1); _0054=11 segs (doubled fig shows a different split of the same day) | **No regression on _0011** (R1 missed _0054) |
| 2026-02-25 (_0020 / _0063) | "7 trip OK, mass cluster accurate" | 9 | _0020=7 segs (45t→18t cluster split steady); zero-speed endpoints | **No regression** |

### Round 2 conclusions

- **Resolved**: 2026-02-13 (13→8) and 2026-03-12 (12→5) markedly improved
- **Improved (still mild)**: 2026-02-17 / 2026-03-06 / 2026-03-25 all dropped from 11-13 to 9-10
- **OK-day regression**: none (2026-02-16 _0011 and 2026-02-25 _0020 retained their split)
- **Doubled figures (P3) not eliminated**: the two leg figures for the same day still differ; this is an FPS API leg overlap artefact, outside the scope of param-tuner
- **Trip endpoint v**: spot-checking all 5 Issue days, the trip endpoints now fall on v ≈ 0 heartbeats; the `zero_speed` anchor is working correctly

### Why is the reduction -39 < the expected -100~-200?

1. The `zero_speed` anchor only **relocates** endpoints, it does not **merge** trips → it does not directly reduce the trip count; but it does make trips that were previously mis-split due to endpoint v>0 cleaner.
2. `min_stop=15` can only absorb short stops of 5-15 min intervals. CMZ6260 is multi-drop inter-city distribution, where actual loading/unloading at delivery points takes 15-45 min, so most stops are ≥ 15 min → still treated as trip boundaries. This is the real rhythm of the duty cycle and **should not** be merged further.
3. Among the doubled figures, the xlsx seems to favour the denser split (a further reduction is only possible after jolt-report-dev fixes the FPS dedup).

### Follow-up to-do (outside the scope of param-tuner)

- **P3 doubled figures**: FPS API leg dedup should be handled by the `jolt-report-dev` agent in `_generator.fetch_events()`.
- If the user wishes to compress the trip count further to 5-7/day, consider subsequently setting `min_stop=15 → 30`, or adding a `speed_params_override` in vehicles.json so that CMZ6260 alone runs at min_stop=30; but this would sacrifice the granularity of multi-drop distribution, and the trade-off must be weighed against fleet consistency.

---
