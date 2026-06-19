# EX74JXW — Scania P-series BEV

> Pipeline: scania_speed_00 | Last updated: **2026-05-17**

## ⚠️ 2026-05-17 update — 历史 Round 1/2 结论已被推翻

之前两轮 thorough review 判定 "0 真正分段错误、不需要调参"。但用户重审 2025-07-14_0005 时
明确指出 06:30–15:00 应有 4 条 trip 而非 1 条 220 km In Transit。诊断结果：

- `find_speed_trips` 探针证明算法本来就正确切出 8 条 trip（上午 4 + 下午 4）
- 真凶是下游 `merge_discharge_by_mass`：相邻 trip 的 dominant `mass_cluster` 相同 →
  被合并成单条 In Transit
- EX74JXW 真实装载 1–2 t 波动落在同一个 `min_cluster_gap_kg=2000` cluster 桶内 → merge 必然触发

**本轮（2026-05-17）改动**：
- `scania_speed_00.merge_by_mass`: 新增 → **false**（关闭质量合并，保留 split）
- 其它 speed_params / charge_params 未动

**效果**（2025-06_2025-09 段对比）：
| Leg Type | merge ON (旧) | merge OFF (新) | Δ |
|---|---|---|---|
| In Transit | 43 | 101 | +135% |
| Outbound + Return | 16 | 21 | +31% |
| **driving legs 总数** | **59** | **122** | **+107%** |

07-14_0005 上午切 4 条 trip（50.7 + 49.3 + 56.1 + 43.5 km）+ 下午 4 条；视觉验证通过。
Per-day driving leg max 11/天（07-31），中位数 5.5，无过切分。

下面的旧记录仅保留作历史参考——当前结论以本节为准。

---


## 车辆特征

- 品牌/型号: Scania P-series BEV
- 标称容量: 475 kWh
- 运营模式: mode=discharge，多点配送
- 数据特征: 遥测 SOC（粗精度 1%），遥测速度（`wheel_based_speed`），Logger Speed（10月后可用）

## 优化前状态

- 管线: `scania_soc_00` (SOC-based 放电分段)
- 主要问题: **~14% 天数行程漏检** — SOC 平坦时（100% 或几乎不变）明确有速度活动但无放电段

## 根因

Scania SOC 精度为整数（1%）。当行程较短或能效较高时，SOC 变化 < 5%（`min_soc_drop` 阈值），
导致行程完全未被检测。典型场景：
- 速度达 80 km/h 的真实行驶
- Moving Energy 消耗 6-16 kWh
- 但 SOC 保持在 97-100% 不变

## 解决方案

切换到 `scania_speed_00` (speed-based 放电分段)。

**关键**: `run_segment_detection()` 中 speed 分支已有 fallback 机制 ——
当 `find_discharge_segments_by_speed()` 返回空列表时自动回退到 SOC-based。
因此对于 7 月期间遥测速度不可用的情况，算法会自动回退到 SOC-based，不会丢失数据。

## 最终参数

使用 `scania_speed_00` 默认参数，无需额外调优：

| 参数 | 值 |
|------|-----|
| speed_threshold_kmh | 1.0 |
| min_stop_duration_min | 5.0 |
| min_trip_duration_min | 2.0 |
| min_soc_drop | 1.0 |
| min_energy_kwh | 1.0 |

## 经验教训

1. **SOC-based 对粗精度 SOC 不适用于短行程检测** — 1% 精度下 min_soc_drop=5.0 会漏掉短行程
2. **Speed-based + fallback 是最佳策略** — 有速度时用速度，无速度时回退到 SOC
3. **不要因部分时段缺少速度数据而放弃 speed-based** — fallback 机制已覆盖这种情况
4. **EX74JXW 和 EX74JXY 同为 Scania P-series，问题和方案一致**

## 调优历史

| Round | Date | Action | Result |
|-------|------|--------|--------|
| 1 | 2026-03-23 | 初始评审 71 张验证图 | 55 OK / 16 Issue / 0 真实分段错误。不需要调参。 |
| 2 | 2026-03-25 | Thorough mode 全量精细复审 | 确认 Round 1 所有判定。0 状态变更。不需要调参。 |

## 数据覆盖与质量摘要（v2.1.0.dev0）

- **报告期**: 2025-06-01 至 2025-12-01（两份 xlsx）
- **验证图**: 71 天（7月19天 + 8月13天 + 10月22天 + 11月17天）
- **活跃行驶天**: 42/71 (59.2%)
- **EP 范围**: 0.5-3.0 kWh/km（典型 0.8-2.2）
- **质量范围**: 空车 ~10-14t，满载 ~20-40t
- **数据特征**: 7月无遥测速度（SOC-fallback）；8月中旬遥测速度恢复；10月起 Logger Speed 可用
