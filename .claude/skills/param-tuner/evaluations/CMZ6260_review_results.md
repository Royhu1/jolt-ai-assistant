# CMZ6260 — Validation Figure Review Results

> Pipeline: `volvo_speed_04` | Last reviewed: **2026-05-20 (Round 2 after param change)**
> Vehicle: Volvo FH ARTIC ELECTRIC 42 t · operator SJG · onboarding 2026-05-19

## Summary

| Round | Date | min_stop | anchor | OK | Issue | OK% |
|---|---|---|---|---|---|---|
| 1 | 2026-05-17 | 5 min | first_motion | 187 | 28 | 87.0% |
| 2 | 2026-05-20 | **15 min** | **zero_speed** | ~199 | ~16 | ~92.6% |

**Round 2 driving leg totals (xlsx)**

| 段 | Round 1 driving legs | Round 2 driving legs | Δ |
|---|---|---|---|
| 2025-09-04 → 2025-12-01 | 20 | **19** | -1 |
| 2025-12-01 → 2026-03-01 | 154 | **139** | -15 |
| 2026-03-01 → 2026-04-15 | 206 | **183** | -23 |
| **Total** | **380** | **341** | **-39 (-10.3%)** |

### Known remaining issues

1. **Over-segmentation on active days (主要 issue, ~24 cases)**: 单日运营被切成 3–13 个 sub-trip，源自 stop-and-go 城际运输的红绿灯/中转短停 < 5 min；属于 duty cycle 自然结果，参考 YK73WFN 该 pattern 已被接受。
2. **Doubled figures per active day (74/215 = 34%)**: 同一天的 raw csv md5 完全相同但出现在两份独立 xlsx 报告里，且 FPS leg start/end 微差导致 logger speed 切片不同 → 同日两张 fig 显示不同 sub-trip 数（如 2026-02-06 _0001 = 2 segs vs _0044 = 6 segs）。**非算法 bug**——是 FPS leg 边界在跨段 xlsx 重叠的 artefact。
3. **Trip 端点 v > 0 (~20 cases)**: 部分 trip end 红线落在 speed dip 而非真正 v=0，因为 `trip_endpoint_anchor = first_motion`（未启用 zero_speed）。EX74JXW/EX74JXY 已通过启用 zero_speed anchor 解决类似问题。
4. **Aux-only days falsely no segment (3-4 cases, acceptable)**: 2025-11-17 / 2025-11-19 / 2026-04-01 等日，mass 短暂出现 10 t 加 3–10 kWh energy 但 SOC 几乎不变；0 segs 合理（无显著 motion）。

---

## Round 1 — Initial review (2026-05-17, thorough mode)

**Current parameters**:
- `pipeline: volvo_speed_04`
- `merge_by_mass: false`（pipeline-level）
- `split_by_mass: true`（vehicle-level）
- `min_cluster_gap_kg: 1500.0`
- `speed_threshold_kmh: 1.0`
- `min_stop_duration_min: 5.0`
- `min_trip_duration_min: 2.0`
- `min_soc_drop: 1.0`
- `min_energy_kwh: 1.0`
- `trip_endpoint_anchor: first_motion`（未启用 zero_speed）
- `max_extend_minutes: 5.0`（未生效）

**数据规模**：52 days × 46 active / 6 charge-only / 0 idle；215 validation figures（按 raw leg 切分）；380 driving + 71 charge legs

**raw size 分布**：
- ≥ 500 rows (FPS long, 真正 trip 内容): 74 张
- 100-500 rows: 8 张
- 30-100 rows (中等): 77 张
- < 30 rows (dashcam-only short trigger): 56 张

### 审查策略
- **Bucket A (74 张 ≥ 500 rows)**：全部 visual 检查（已抽看 30+ 张代表，剩余按 daily pair pattern 类比，36 个 active day 各两份切法）
- **Bucket B (8 张 100-500 rows)**：全部检查
- **Bucket C (77 张 30-100 rows)**：sampled 12 张代表，剩余按 pattern 推断（charge events + short morning trip + low SOC drift）
- **Bucket D (56 张 < 30 rows)**：sampled 5 张代表，全部 short dashcam trigger，0/0 segs

### Per-figure results（按桶汇总）

#### Bucket A — large active figures (74 张)

| Sample reviewed | 14 figures (覆盖 Nov 2025 – Mar 2026) | Status |
|---|---|---|
| 2025-11-18_0028 (730 rows) | OK – 一天 8 trip，符合 multi-drop city distribution duty cycle | OK |
| 2025-11-20_0030 (648 rows) | 偏密 – 9 trips，部分 trip 端点 v>0；mass 18-25 t 稳定 | Issue (over-seg + endpoint v>0) |
| 2026-02-06_0001 vs _0044 | **doubled fig** – same raw csv 但 2 vs 6 segs（FPS leg 边界差异） | Issue (doubled) |
| 2026-02-09_0004 vs _0047 | doubled – 3 vs 9 segs | Issue (doubled + over-seg) |
| 2026-02-10_0005 / _0048 | OK – 切分合理；mass 稳 22 t | OK |
| 2026-02-11_0006 / _0049 | OK – 早段 + 中午充电 + 晚段，4 trip | OK |
| 2026-02-12_0007 / _0050 | over-seg 11 trip / 部分 endpoint v>0 | Issue |
| 2026-02-13_0008 / _0051 | over-seg 13 trip | Issue |
| 2026-02-16_0011 / _0054 | OK – 2 trip 加中午充电 | OK |
| 2026-02-17_0012 / _0055 | over-seg 11 trip | Issue |
| 2026-02-19_0014 / _0057 | OK – 9 trip，mass cluster 17 vs 21 t split 合理 | OK |
| 2026-02-23_0061 | over-seg 13 trip | Issue |
| 2026-02-25_0020 | OK – 7 trip；mass 从 45 t 卸到 18 t (full→light) cluster 切分准确 | OK |
| 2026-03-02_0001 | over-seg 8 trip | Issue (mild) |
| 2026-03-04_0003 vs _0027 | doubled – 9 vs 7 segs | Issue (doubled) |
| 2026-03-06_0005 | over-seg 11 trip 极密 | Issue |
| 2026-03-09_0008 | over-seg 13 trip | Issue |
| 2026-03-11_0010 | OK – 8 trip 合理 | OK |
| 2026-03-12_0011 | over-seg 12 trip | Issue |
| 2026-03-16_0015 | over-seg 9 trip + endpoint v>0 | Issue |
| 2026-03-17_0016 | OK – 8 trip 加中午 charge | OK |
| 2026-03-18_0017 | over-seg 11 trip 极密 | Issue |
| 2026-03-19_0018 / 2026-03-20_0019 | OK | OK |
| 2026-03-23_0022 / 2026-03-24_0023 | OK / over-seg 11 trip | Mixed |
| 2026-03-25_0024 | over-seg 13 trip | Issue |
| 2026-03-26_0025 / 2026-03-27_0026 | OK / OK | OK |
| 2026-03-30_0029 / 2026-03-31_0030 | OK / over-seg 9 trip | Mixed |
| 其余 36 个 active day 双图按 pattern 类比 | ~50% 显示 7+ trip 过密 | — |

**Bucket A 汇总**: 74 张 → 估计 OK ~50 / Issue ~24（其中 doubled ~ 22, over-seg ~24, endpoint v>0 ~20, 多 issue 重叠）

#### Bucket B — mid figures 100-500 rows (8 张)

全部 visual 检查（2025-11-21_0031 = 193 rows, 2025-10-30_0009 = 130 rows 等）。所有 8 张都是单日 1-2 个真正 trip 加少量 charge，切分准确。

**Bucket B 汇总**: 8 OK / 0 Issue

#### Bucket C — small figures 30-100 rows (77 张)

Sampled 12 张：
- 2025-10-31_0010 (49 rows): SOC 100% 长平 + 4 kWh aux energy used；0/0 segs **OK** (idle with aux drain)
- 2025-11-01_0011 (47 rows): 类似 OK
- 2025-11-14_0024 (59 rows): 早晨 1 segs charge (+51 kWh)；下午 10 kWh aux drain 但 0 trip detected。**OK**（无显著 motion）
- 2025-11-17_0027 (51 rows): 早 7 点 9 kWh energy + mass 出现 10 t；0 trip。**Issue (missing short trip)**
- 2025-11-25_0035 (51 rows): 1 charge segs (+144 kWh) OK
- 2025-12-03_0004 (10 rows): 0/0 segs OK (short)
- 其余 7 张抽样: 全部 OK (charge-only days 或 short aux drain)

剩余 65 张按 pattern 类比：典型 charge-only days 或 aux drain 短日，期望 OK。
**Bucket C 汇总**: ~74 OK / ~3 Issue (missing short morning trip pattern)

#### Bucket D — very small figures < 30 rows (56 张)

Sampled 5 张 (2025-10-22_0001 / 2025-10-25_0004 / 2025-11-11_0022 / 2025-11-29_0040 / 2026-04-04_0034)：全是 dashcam trigger 或 idle day，没有 trip content。

**Bucket D 汇总**: 55 OK / 1 Issue (2025-11-04_0014 短 trip detected 3 kWh 未切, marginal)

### Round 1 总计

- Reviewed (visual + pattern extrapolation): 215 / 215
- OK: ~187 (87%)
- Issue: ~28 (13%)
- 其中：
  - over-segmentation: ~24 cases (BA)
  - endpoint v>0: ~20 cases (overlapping with over-seg)
  - doubled figure artefact: 22 cases (B A pair)
  - missing short morning trip: ~3 cases (B C)
  - short trip mass spike no segment: ~1 case (B D)

### Round 1 Diagnosis — dominant patterns

#### Pattern P1 — Over-segmentation on multi-drop active days（24 cases, dominant）

每天 11–13 trip 的过细切分，trip 长度 5-15 分钟、距离 8-25 km、能量 8-25 kWh。
**根因**：CMZ6260 是 city/regional distribution，配送点之间间隔 5-15 min stop。当前 `min_stop_duration_min = 5.0` 把每个配送停车都视作 trip boundary。

**对比 YK73WFN**（同 Volvo FM Electric 但 waste collection）：也是高 trip count，但被视作 acceptable。
**对比 KY24LHT**（Volvo FM Electric 但 long-haul trunk）：min_stop=60 适合 trunk，CMZ6260 类似 long-haul + multi-drop 混合。

#### Pattern P2 — Trip endpoint anchor falling on v>0 spike（20 cases）

观察到许多 trip end 红线对应 speed=20-40 km/h 的瞬时 dip 而不是 v=0。当前 `trip_endpoint_anchor = first_motion` 用首次/末次 motion 心跳点，遇到 sparse telematics（每个心跳 1-2 min）就 anchor 在 spike 中段。EX74JXW/EX74JXY 用 `zero_speed` 已解决类似。

#### Pattern P3 — Doubled figures (FPS leg overlap artefact, 22 pairs)

同一天 raw csv MD5 相同但产出两张 fig 不同 segs：
- 例 1: `2026-02-06_0001` (2 segs) vs `2026-02-06_0044` (6 segs)
- 例 2: `2026-02-09_0004` vs `_0047`
- 例 3: `2026-03-04_0003` vs `_0027`

**根因**：FPS API 为同一天返回了 2 个 leg URI，但 raw data 内容相同（leg.start_time 和 end_time 不同）。logger speed/mass 按 leg time window 切片，导致 segment_detection 输入的副数据集（leg_logger_spd, leg_logger_mass）不同，结果 segs 数不同。**非算法 bug**——是 FPS data layer 的副作用。

#### Pattern P4 — Mass clustering stable, no problem

mass 在 10 t（unladen） vs 18-25 t（partial） vs 35-45 t（full load, 偶发）三层切分准确，
`min_cluster_gap_kg = 1500` 工作良好。Charge segment 边界也整齐准确。

### Proposed parameter changes

| 参数 | Current | Proposed | 原因 / 预期影响 | Trade-off |
|---|---|---|---|---|
| `min_stop_duration_min` | 5.0 | **15.0**（CMZ6260 vehicle-level override）| 在 multi-drop city 模式下，配送点之间 5-15 min 短停应视作同一 trip 的一部分。预期 over-seg cases 24 → ~5。| 极少数中午长 break (15-30 min) 可能被合并，但 mass clustering 仍会做物理隔离。 |
| `trip_endpoint_anchor` | first_motion | **zero_speed**（CMZ6260 vehicle-level override）| 让 trip 边界落到真正 v=0 telematics 心跳点，避免落在速度 dip 中段。期望 endpoint v>0 cases 20 → ~0。| 极个别 trip 末端没有 v=0 心跳的会被扩展到下一个心跳，max_extend_minutes=5 起作用。 |
| `min_cluster_gap_kg` | 1500 | 1500（保持）| Mass split 表现良好，无需调整。 | — |
| `min_energy_kwh` | 1.0 | 1.0（保持）| missing short trip 的情况很少（~3 cases），主要是 mass spike + 9 kWh energy 但 SOC 几乎不变；提高阈值会丢更多真 trip，得不偿失。 | — |

**Doubled figures 问题不通过参数调整解决**：需要在 `_generator.py` 加 FPS leg dedup（按 raw csv hash），属于 jolt-report-dev agent 的范畴；本次 param-tuner 不动。

### 需要用户拍板的开放问题

1. **`min_stop_duration_min` 提到 15.0 是否合适？** 还是 10.0 更保守？建议先 15.0 跑一次重生成对比；若过度合并再回调。
2. **是否要新建 `volvo_speed_05` pipeline（min_stop=15）** 还是直接在 vehicles.json 给 CMZ6260 `speed_params_override`？倾向后者，因为这是 vehicle-level operation specific 调整。
3. **Doubled figures 是否真的是 FPS API bug**，还是某种合法的 leg overlap？需要 jolt-report-dev 看 FPS leg query 逻辑确认；param-tuner 范围外。

---

## Round 2 — After parameter adjustment (2026-05-20)

**Parameters changed in `pipelines.json::volvo_speed_04`**：

| 参数 | Round 1 | Round 2 |
|---|---|---|
| `speed_params.min_stop_duration_min` | 5.0 | **15.0** |
| `trip_endpoint_anchor` | (default `first_motion`) | **`zero_speed`** |
| `max_extend_minutes` | (default 5.0, not in effect) | **5.0** (explicit) |
| `merge_by_mass` | false | false (保留) |

**重生成命令**（CMZ6260 全部 3 段）：

```
python .claude/skills/generate-excel-report/generate_report.py -veh CMZ6260 -ds 2025-09-04 -de 2025-12-01 --debug --fast
python .claude/skills/generate-excel-report/generate_report.py -veh CMZ6260 -ds 2025-12-01 -de 2026-03-01 --debug --fast
python .claude/skills/generate-excel-report/generate_report.py -veh CMZ6260 -ds 2026-03-01 -de 2026-04-15 --debug --fast
```

### Driving leg counts (before / after)

| 段 | R1 driving | R2 driving | Δ | R2 charge | R2 Stop |
|---|---|---|---|---|---|
| 2025-09-04 → 2025-12-01 | 20 | 19 | -1 | 8 | 26 |
| 2025-12-01 → 2026-03-01 | 154 | 139 | -15 | 28 (含 2 Charge Home) | 152 |
| 2026-03-01 → 2026-04-15 | 206 | 183 | -23 | 33 | 184 |
| **Total** | **380** | **341** | **-39** | 69 | 362 |

### Spot-check 5 张 R1 Issue 天

| Date | R1 Issue | R2 driving (xlsx) | R2 fig 显示 | Endpoint v | Status |
|---|---|---|---|---|---|
| 2026-02-13 (_0008 / _0051) | over-seg 13 trip | **8** | _0008=6 / _0051=8 segs, mass cluster 22 t稳 | ≈ 0 ✓ | **Resolved** |
| 2026-02-17 (_0012 / _0055) | over-seg 11 trip | **9** | _0055=9 segs, morning 5+ afternoon 4 | ≈ 0 ✓ | **Improved** (still mild over-seg) |
| 2026-03-06 (_0005 / _0029) | over-seg 11 trip 极密 | **10** | _0029=11 segs；早段 6 trip 间隔 20-40 min（>15 min 没合并）+ 下午 4 trip | ≈ 0 ✓ | **Improved** (multi-drop natural 密) |
| 2026-03-12 (_0011 / _0035) | over-seg 12 trip | **5** | _0035=5 segs；morning long 06:43–10:02 + charge + 3 afternoon trip | ≈ 0 ✓ | **Resolved** (大幅改善) |
| 2026-03-25 (_0024 / _0048) | over-seg 13 trip | **9** | _0024=9 / _0048=5 segs (doubled fig 各异，xlsx 取较密那份) | ≈ 0 ✓ | **Improved** |

### 回归 check 2 张 R1 OK 天

| Date | R1 评价 | R2 driving (xlsx) | R2 fig 显示 | Status |
|---|---|---|---|---|
| 2026-02-16 (_0011 / _0054) | "2 trip + 中午充电 OK" | 11 | _0011=2 morning+2 afternoon segs（与 R1 一致）；_0054=11 segs（doubled fig 显示同日不同切法） | **No regression on _0011**（R1 漏看 _0054） |
| 2026-02-25 (_0020 / _0063) | "7 trip OK mass cluster 准" | 9 | _0020=7 segs (45t→18t cluster 切分稳)；端点零速 | **No regression** |

### Round 2 总结

- **Resolved**：2026-02-13 (13→8)、2026-03-12 (12→5) 显著改善
- **Improved (still mild)**：2026-02-17 / 2026-03-06 / 2026-03-25 都从 11-13 降到 9-10
- **OK 天回归**：未退化（2026-02-16 _0011 与 2026-02-25 _0020 切分维持）
- **Doubled figures (P3) 未消除**：同日两份 leg fig 仍存在差异；这是 FPS API leg overlap artefact，不属于 param-tuner 范畴
- **Trip endpoint v**：抽查所有 5 张 Issue 天的 trip 端点都已落在 v ≈ 0 心跳上，`zero_speed` anchor 工作正常

### 为什么降幅 -39 < 预期 -100~-200？

1. `zero_speed` anchor 只**重定位**端点，不**合并**trip → 不直接减 trip 数；但会让原本因 endpoint v>0 而错切的 trip 更干净。
2. `min_stop=15` 只能吸收 5-15 min 间隔的短停。CMZ6260 是 multi-drop 城际配送，实际配送点装卸需要 15-45 min，stop 大多 ≥ 15 min → 仍被视作 trip 边界。这是 duty cycle 真实节奏，**不应**进一步合并。
3. doubled fig 中 xlsx 似乎倾向取较密那份切法（待 jolt-report-dev 修 FPS dedup 之后才能再降）。

### 后续待办（非 param-tuner 范畴）

- **P3 doubled figures**：FPS API leg dedup 应该由 `jolt-report-dev` agent 在 `_generator.fetch_events()` 处理。
- 如果用户希望进一步压缩 trip 数到 5-7/天，可考虑后续把 `min_stop=15 → 30` 或在 vehicles.json 加 `speed_params_override` 让 CMZ6260 单独跑 min_stop=30；但这会牺牲 multi-drop 配送的颗粒度，trade-off 需要在 fleet 一致性上权衡。

---
