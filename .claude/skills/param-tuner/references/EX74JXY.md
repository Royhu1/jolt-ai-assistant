# EX74JXY — Scania P-series BEV

> Pipeline: scania_speed_01 | Last updated: **2026-05-17**

## ⚠️ 2026-05-17 update — 历史 Round 0/1/2 结论已被推翻

EX74JXY 与 EX74JXW 共享 Scania P-series BEV 数据特征，同样受 `merge_discharge_by_mass` 影响：
真实装载 1–2 t 波动落在同一个 `min_cluster_gap_kg=2000` cluster 桶内 → 相邻 trip 的
dominant cluster 相同 → 被合并成单条 In Transit。

**本轮（2026-05-17）改动**：
- `scania_speed_01.merge_by_mass`: 新增 → **false**（关闭质量合并，保留 split）
- 其它 speed_params / charge_params 未动

**效果**（2025-04_2026-02 一段 10 个月）：driving legs 共 **391**（In Transit 307 + Outbound 41 +
Return 42 + Round Trip 1）。视觉抽查 2025-05-08 多 trip 切分健康，质量 ~35–40 t 稳定，
EP 范围正常。

详细诊断逻辑参见姊妹车 [EX74JXW.md](EX74JXW.md) 的 2026-05-17 update 段。

下面的旧记录仅保留作历史参考——当前结论以本节为准。

---


## 车辆特征

- 品牌/型号: Scania P-series BEV
- 标称容量: 475 kWh
- 运营模式: mode=discharge
- 数据特征: 与 EX74JXW 一致，遥测 SOC 粗精度（1% resolution），遥测速度可用
- 典型质量范围: 15–40 tonnes
- 典型 EP 范围: 0.5–3.0 kWh/km

## 管线与参数

- 管线: `scania_speed_01`
- speed_threshold_kmh: 1.0
- min_stop_duration_min: 5.0
- min_trip_duration_min: 2.0
- min_soc_drop: 1.0
- min_energy_kwh: 1.0
- plateau_window_min: 60
- min_soc_rise: 5.0
- min_energy_charge: 5.0
- speed_col: wheel_based_speed

## 优化历史

### Round 0 — 管线切换（2026-03-22）
- 从 `scania_soc_01` 切换到 `scania_speed_01`
- 原因: SOC 粗精度导致 SOC-based 算法大量漏检（速度 80 km/h 但 SOC 平坦）
- 与 EX74JXW 完全相同的问题和方案，参见 `EX74JXW.md`

### Round 1 — 初始审查（2026-03-23）
- 审查 60/143 张验证图
- OK rate: 55/60 = 91.7%（含 idle）; 55/57 = 96.5%（active+charge only）
- 发现 5 个问题（1 missed discharge、1 missed charge、2 borderline、1 possible missed idle）
- 结论: 不需要参数调整

### Round 2 — Thorough mode 全量覆盖（2026-03-25）
- 审查全部剩余 83/143 张验证图，实现 100% 覆盖
- Round 2 新审查部分: 83 OK, 0 Issue
- 全量结果: 138 OK / 5 Issue = 96.5% OK rate
- **无新问题发现**，Round 1 的 5 个 issue 确认为唯一问题
- **不需要参数调整**

## 已知问题（不可通过参数调整修复）

| Figure | Date | Type | 描述 | 根因 |
|--------|------|------|------|------|
| 0136 | 2026-01-05 | Missed discharge | SOC 100→20% 但 0 段，移动能量仅 1.5 kWh | 数据质量问题（能量通道异常） |
| 0104 | 2025-10-24 | Missed charge | SOC 40→90% 有 AC/DC delta 但 0 段 | 充电过于缓慢，可能超出 plateau_window |
| 0138 | 2026-01-09 | Missed discharge | SOC 100→80%，能量 0.6 kWh，0 段 | 低于 min_energy 阈值边界 |
| 0133 | 2025-12-31 | Marginal trip | 1D 检出但极短，能量极少 | 边界情况，检出正确但可疑 |
| 0142 | 2026-01-30 | Possible missed idle | SOC 平坦，能量 0.5 kWh 阶梯式 | 可能极低速depot移动，低于阈值 |

## 关键经验

1. **速度基分段对 Scania 粗精度 SOC 至关重要**: SOC 1% 步进导致 SOC-based 算法漏检大量真实行程
2. **当前参数对多站配送场景表现优异**: 7+ 次停站的繁忙日全部正确分段
3. **数据质量问题不应通过降低阈值来补偿**: 0136 的能量通道异常（80% SOC drop 但仅 1.5 kWh 移动能量）是数据质量问题，不是参数问题
4. **缓慢充电检测是已知限制**: 0104 的充电非常缓慢，可能需要更大的 plateau_window，但这会影响其他正常充电检测
5. **Idle 天的微量能量（<1 kWh）和速度脉冲可正确忽略**: 当前阈值对 depot 微移动有良好的过滤效果
