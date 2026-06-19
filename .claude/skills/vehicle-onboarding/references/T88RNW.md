# T88RNW — Renault E-Tech D Wide

## 车辆特征

- 品牌/型号: Renault Trucks E-Tech D Wide (RIGID, 19t)
- VIN: VF620JEA7PB000178
- 标称容量: 211 kWh (SRF fuel_capacity)
- 有效容量: ~190 kWh (算法自动计算实测均值 ~233 kWh/%)
- 运营商: Welch's Transport (WELCH_TRANSPORT)
- 运营模式: 城市多点配送，每日 6-17 个配送段
- SRF 注册号: "T88 RNW"
- SRF Organisation: "JOLT Welch-Volvo"
- 数据范围: 2024-06-11 ~ 2026-03-21 (1209 legs)

## 遥测列映射

与 N88GNW (Renault D Wide Z.E.) 和 TA70WTL (Renault E-Tech T) 列结构一致：

| 用途 | 列名 | 备注 |
|------|------|------|
| 速度 | `wheel_based_speed` | 96% 填充率 |
| SOC | `electricBatteryLevelPercent` | 整数精度 (1%) |
| 里程 | `hr_total_vehicle_distance` | 可用 |
| 质量 | `gross_combination_vehicle_weight` | **全部为 null — 无质量数据** |
| 总能量 | `total_electric_energy_used_plugged_in_included` | ~20% 行有值 |
| 移动能量 | `electric_energy_wheelbased_speed_over_zero` | ~20% 行有值 |
| AC 能量 | `battery_pack_ac_watthours` | ~20% 行有值 |
| DC 能量 | `battery_pack_dc_watthours` | ~20% 行有值 |
| 海拔 | `gnss_altitude` | 96% 填充率 |
| 经纬度 | `latitude`, `longitude` | 可用 |

## 算法选择

- **管线**: `renault_speed` (speed-based 放电分段)
- **速度列**: 默认 `wheel_based_speed`
- **原因**: 速度数据完整可靠；SOC 整数精度下 speed-based 更稳定

## 参数

使用 `renault_speed` 默认参数，无需调优：

| 参数 | 值 | 说明 |
|------|-----|------|
| speed_threshold_kmh | 1.0 | 默认 |
| min_stop_duration_min | 5.0 | 默认，恰好区分"交通等待"和"配送停车" |
| min_trip_duration_min | 2.0 | 默认 |
| min_soc_drop | 1.0 | 默认，1% 是电池最小分辨率 |
| min_energy_kwh | 1.0 | 默认 |
| min_cluster_gap_kg | 2000.0 | 默认（无质量数据，不生效） |

## SRF API 自动发现

首次使用 SRF API 自动读取以下信息：
- `v.fuel_capacity` = 211 → 直接用作 `nominal_kwh`
- `organisation.name` = "JOLT Welch-Volvo" → 映射为 WELCH_TRANSPORT
- `v.description` = "2023 Renault E-Tech D Wide 19-t rigid electric (211 kWh)"
- `v.type` = RIGID, `v.weight_class` = 18.0

## 数据特点

1. **城市多点配送模式**: 每日 6-17 个 trip，平均 10.46 km/trip，日均约 112 km
2. **无质量数据**: `gross_combination_vehicle_weight` 全部 null
3. **SOC 分辨率受限**: 211 kWh 时 1% SOC ≈ 2.39 kWh，短程(<3 km)常出现 1% SOC 和偏高 EP
4. **22% 的 trip 仅 1% SOC 变化**: 城市配送短距离造成，是真实运营特征
5. **高 EP 离群值 (1.7%)**: EP > 3 kWh/km 的 trip 全部为极短距离(<1 km)，是 SOC 精度问题
6. **充电类型**: 主要 DC Home 充电，少数 "Charge Home"（AC/DC 列均为 0 但 SOC 上升）

## 经验教训

1. **Renault 列结构高度一致**: T88RNW 与 N88GNW、TA70WTL 列名完全相同，新 Renault 车辆可直接复用列映射
2. **小电池车辆的 SOC 精度更粗**: 211 kWh 时 1% ≈ 2.39 kWh，比大电池车（540 kWh → 5.4 kWh）更容易出现边界效应
3. **无质量数据不影响速度分段**: 速度分段只需 speed + SOC + energy 列
4. **SRF API 可自动获取容量和运营商**: fuel_capacity + organisation.name 大幅减少 onboarding 手动输入
