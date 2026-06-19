# param-identifier Agent

参数辨识专用 Agent。使用 CRRCDA 方法对 JOLT 项目中的电动重卡辨识 C_rr（滚动阻力系数）和 C_dA（空气阻力面积）。

## 能力范围

- 从 SRF API 下载 **Logger** 高频遥测数据（1s 分辨率：EEC1 电机转速/扭矩、CCVS 速度、EBC1 制动、CVW 质量、GPS 海拔/距离、Channel 6 SOC、Channel 7 天气）
- 探测车辆的 Logger 可用通道和日期范围
- 提取近似恒速巡航段（基于制动踏板位置或速度变异系数）
- 基于能量平衡方程计算线性约束：E_source × η = ΔE_kin + ΔE_pot + C_rr·m·g·Σ(Δs) + C_dA·½·ρ·Σ(v²·Δs)
- K-Means 聚类（轻载/重载）+ 交线法辨识 C_rr, C_dA
- 多级过滤（风速、海拔变化、质量偏差）+ 7 种过滤组合图
- 生成综合分析图（约束线、95% CI、分布直方图）

## 重要说明

- **只有 Logger 数据可用于参数辨识**，FPS/Telematics 数据频率太低且缺少 EEC1/EBC1 等关键通道
- 能量计算支持两种模式：EEC1（电机转速×扭矩%×max_torque）和 battery（SOC×容量）
- 当前有 Logger 数据的车辆：**YN25RSY**（Mercedes，有 EEC1）和 **YK73WFN**（Volvo FM，有 EEC1）

## 代码位置

所有参数辨识代码位于 `src/jolt_toolkit/vehicle_params_identificator/` 目录：

| 文件 | 功能 |
|------|------|
| `config.py` | 物理常数、算法参数、路径配置、车辆 max_torque_nm |
| `data_loader.py` | SRF Logger API 数据下载 + 本地 CSV 加载 + 通道探测 |
| `preprocessing.py` | 巡航段提取（BrkPedalPos==0 或速度 CV 阈值） |
| `identification.py` | 线性约束计算（SymPy 符号求解）+ K-Means 辨识 + 过滤 |
| `visualization.py` | 2×2 综合分析图 + 质量直方图 |
| `run_identification.py` | CLI 入口和完整辨识流程 |
| `test_identification.py` | 合成数据单元测试 |

## 运行方式

```bash
# 探测通道
python -m jolt_toolkit.vehicle_params_identificator.run_identification --probe --veh YN25RSY

# 单辆车辨识（下载 + 辨识）
python -m jolt_toolkit.vehicle_params_identificator.run_identification --veh YN25RSY

# 全部有 Logger 的车辆
python -m jolt_toolkit.vehicle_params_identificator.run_identification --all

# 仅用已下载数据（不联网）
python -m jolt_toolkit.vehicle_params_identificator.run_identification --veh YN25RSY --no-download

# 自定义参数
python -m jolt_toolkit.vehicle_params_identificator.run_identification --veh YN25RSY --seg-distance 10000 --min-speed 60 --efficiency 0.95
```

## 参考实现

基于外部参考项目 `HGV_Parameter_Identify`（`independent_exp/`）的 CRRCDA 方法，核心算法来自其 `exp/case_study/src/param_identification/`。

关键差异：
- 原始方法面向柴油 HGV（SEG=10km, MIN_SPEED=80km/h, η=0.95）
- 电动重卡适配：EEC1 电机模式 + battery SOC fallback
- config.py 中有每辆车的 max_torque_nm 和日期范围配置
