# TA70WTL — Renault Trucks E-Tech T

## 车辆特征

- 品牌/型号: Renault Trucks E-Tech T (ARTIC)
- 标称容量: 417 kWh
- 有效容量: ~375 kWh (90%, 算法自动计算均值 379.2 kWh)
- 运营商: Welch's Transport
- 运营模式: 城际配送，低使用率期间以 tractor-only 停放为主
- SRF 注册号: "TA70 WTL"
- 数据范围: 2025-04-30 ~ 2026-03-20 (312 FPS legs, 0 Charger, 80 Logger legs limited to 2025-06~08)

## 遥测列映射

与 N88GNW (Renault D Wide Z.E.) 完全一致：

| 用途 | 列名 | 备注 |
|------|------|------|
| 速度 | `wheel_based_speed` | 与 Volvo/Scania/Renault 标准一致 |
| SOC | `electricBatteryLevelPercent` | 整数精度 (1%) |
| 里程 | `high_resolution_total_vehicle_distance` | 可用 |
| 质量 | `gross_combination_vehicle_weight` | 可用, tractor ~10000 kg |
| 总能量 | `total_electric_energy_used_plugged_in_included` | 可用 |
| 移动能量 | `electric_energy_wheelbased_speed_over_zero` | 可用 |
| AC 能量 | `battery_pack_ac_watthours` | 可用 |
| DC 能量 | `battery_pack_dc_watthours` | 可用 |
| 海拔 | `gnss_altitude` | 可用 |
| 经纬度 | `latitude`, `longitude` | 可用 |

## 算法选择

- **管线**: `renault_speed` (speed-based 放电分段)
- **速度列**: 默认 `wheel_based_speed`（无需 `speed_col` 覆盖）
- **原因**: 速度数据完整可靠；SOC 整数精度下 speed-based 更稳定

## 参数

使用 `renault_speed` 默认参数，无需调优：

| 参数 | 值 | 说明 |
|------|-----|------|
| speed_threshold_kmh | 1.0 | 默认 |
| min_stop_duration_min | 5.0 | 默认 |
| min_trip_duration_min | 2.0 | 默认 |
| min_soc_drop | 1.0 | 默认 |
| min_energy_kwh | 1.0 | 默认 |
| min_cluster_gap_kg | 2000.0 | 默认 |

## 数据特点

1. **2 月使用率低**: 29 天中仅 4 天有放电段（02-02, 02-09, 02-10, 02-17），其余为空闲/充电日
2. **全部 tractor-only**: 所有质量读数 ~10000 kg (< 13000 kg 阈值)，无挂车数据
3. **短暂 yard movement**: 02-11, 02-26 出现短暂速度尖峰 (~13 km/h) 但 SOC 不变，被 min_soc_drop 正确过滤
4. **充电模式**: 小功率夜间补电为主（+25~47 kWh），偶有大充电 (02-03: +210 kWh)
5. **Logger 数据有限**: 仅 2025-06 ~ 2025-08 共 80 legs，后续无 Logger

## 经验教训

1. **Renault 列结构高度一致**: TA70WTL 与 N88GNW 列名完全相同，新 Renault 车辆可直接复用列映射
2. **低使用率时期的默认参数验证**: 即使活动天数少，默认 `renault_speed` 参数也能正确工作，无过度分段
3. **Yard movement 过滤有效**: `min_soc_drop=1.0` 成功过滤短暂移动（速度尖峰但 SOC 不变）
