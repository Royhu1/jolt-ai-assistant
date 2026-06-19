# YN25RSY — Mercedes-Benz eActros 600

## 车辆特征

- 品牌/型号: Mercedes-Benz eActros 600
- 标称容量: 600 kWh
- 运营模式: 长途干线运输，偶尔多点配送
- 数据特征: 遥测 SOC（整数精度 1%）+ 遥测速度（`speed` 列，~2 min 间隔）+ Logger Speed + Logger Mass；遥测无质量数据

## 关键发现：遥测列名差异

Mercedes 遥测速度列名为 `speed`，而非 Volvo/Scania/Renault 使用的 `wheel_based_speed`。
需在 vehicles.json 中显式配置 `"speed_col": "speed"`。

## 优化前状态

- 管线: `mercedes_soc` (SOC-based 放电分段)
- 主要问题: **过度分段**（10+ 天受影响），个别天数 6 段放电
- 次要问题: 低 SOC 时行程遗漏（1 天）

## 根因与解决方案

### 根因 1: SOC 整数精度导致过度分段

Mercedes SOC 精度为 1%（整数），连续行驶中出现短暂 SOC 平台期或微小回升（1-3%），
`soc_rise_abort_pct=3.0%` 将一个连续行程切成多个片段。

**解决**: 切换到 speed-based 管线 (`mercedes_speed`)，配置 `speed_col: "speed"` 使用遥测速度。

### 根因 2: Logger 速度方案不适合

最初尝试使用 Logger Speed（高频 ~15s 间隔）进行行程检测。问题：
- 依赖 Logger 数据，`--fast` 模式不可用
- 高频数据检测到每个短停靠（5-15min），需要将 `min_stop_duration_min` 增大到 15
- 部分天数 Logger 速度不完整（11-01），导致行程遗漏

**最终方案**: 使用遥测速度（`speed` 列，~2min 间隔）。优势：
- 不依赖 Logger/Charger 数据，`--fast` 模式兼容
- 2min 间隔自然过滤极短停靠（<2min 的停靠不可见）
- 覆盖完整（遥测始终在线），不会因 Logger 不完整而遗漏行程

## 最终参数

| 参数 | 默认值 | 最终值 | 原因 |
|------|--------|--------|------|
| `pipeline` | `mercedes_soc` | `mercedes_speed` | SOC 精度不足，切换到速度分段 |
| `speed_col` | `wheel_based_speed` | `speed` | Mercedes 遥测速度列名不同 |
| `min_stop_duration_min` | 5.0 | **5.0** | 遥测 2min 间隔下 5min 即可，无需像 Logger 那样增大 |
| `min_soc_drop` | 1.0 | **2.0** | 过滤 dSOC≤1% 噪声段 |

## 优化结果

- 8/15 天改善或显著改善
- 3/3 正确天保持不变
- 11-01 修复（之前 Logger 方案遗漏的全天行驶现在被遥测速度覆盖）
- 12-01 仍无法检测（SOC 在 ~12% 完全平坦，BMS 保护）

## Round 2 验证 (2026-03-25, v2.1.0.dev0)

全量精细检视（48 张验证图逐一审查）确认：
- **46/48 OK、2/48 Issue** — 与 Round 1 结果完全一致
- 15 个活跃日的 trip boundary 均与遥测速度 trace 正确对齐
- EP 值在 0.7–2.1 kWh/km 范围内（eActros 600, 40t 级别）
- 充电段（绿色区域）在所有活跃日正确识别
- 2025-11-19 至 2026-01-04 的长待机期无误报
- 12-05 重新分类为 Charge-only（仅充电，无有效放电行程）
- **无需参数调整** — 当前参数已达到最优

## 经验教训（适用于类似车辆）

1. **优先使用遥测速度，而非 Logger 速度** — 遥测始终在线且与 `--fast` 模式兼容；
   Logger 速度作为补充验证，不作为分段依据
2. **不同品牌的遥测列名不同** — 配置 `speed_col` 而非硬编码列名：
   - Volvo/Scania/Renault: `wheel_based_speed`
   - Mercedes: `speed`
3. **SOC 整数精度的车辆应使用 speed-based 管线** — SOC-based 对 1% 精度过于敏感
4. **遥测速度的时间分辨率自然过滤短停靠** — 2min 间隔下 `min_stop_duration_min=5` 即可，
   无需像高频 Logger 速度那样增大到 15
5. **分段算法不应依赖 Logger/Charger 数据** — 确保 `--fast` 模式（仅遥测）
   和完整模式产生相同的 trip/charge 分段结果
6. **`min_soc_drop=2.0` 适用于大容量车辆** — 600kWh 下 1% SOC = 6kWh，
   dSOC=1% 的移动通常是调车/挪车，不是有效行程
