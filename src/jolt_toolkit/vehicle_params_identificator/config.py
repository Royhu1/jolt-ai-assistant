"""
参数辨识配置模块。
物理常数、车辆配置、算法参数。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────────────────────────
from jolt_toolkit.configs import get_config_path as _get_config_path

# 项目根目录（src/jolt_toolkit/vehicle_params_identificator → 上溯 4 层到项目根）
JOLT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
VEHICLES_JSON = _get_config_path("vehicles.json")

# 参数辨识工作目录放在项目根的 research_projects/ 下，而非包内
DATA_DIR = JOLT_ROOT / "research_projects" / "parameter_identify" / "data"
RESULTS_DIR = JOLT_ROOT / "research_projects" / "parameter_identify" / "results"
LOGS_DIR = JOLT_ROOT / "research_projects" / "parameter_identify" / "logs"

# ── 物理常数 ──────────────────────────────────────────────────────────────
GRAVITY = 9.81  # m/s²
AIR_DENSITY = 1.225  # kg/m³
MOTOR_EFFICIENCY = 0.90  # 电机 + 逆变器 + 传动效率（EV 综合）

# ── 巡航段提取参数 ────────────────────────────────────────────────────────
SEG_DISTANCE_M = 5000  # 巡航段最小距离 (m)，比柴油 10 km 更短
MIN_AVG_SPEED_KMPH = 40  # 最小平均速度 (km/h)，比柴油 80 km/h 更低
WINDOW_STEP_M = 200  # 滑动窗口步长 (m)
MAX_SPEED_CV = 0.20  # 巡航段速度变异系数上限（替代 BrkPedalPos == 0 判定）
MIN_SPEED_FLOOR_KMPH = 5.0  # 段内最低速度底线 (km/h)

# ── 聚类 & 辨识参数 ──────────────────────────────────────────────────────
N_CLUSTERS = 2
RANDOM_STATE = 42

PARAMS_RANGE = {
    "crr_low": 0.002,
    "crr_high": 0.020,
    "delta_crr": 0.0001,
    "cda_low": 2.0,
    "cda_high": 15.0,
    "delta_cda": 0.1,
}

# ── 过滤参数 ──────────────────────────────────────────────────────────────
ELEVATION_CHANGE_THRESHOLD_M = 100.0  # 海拔变化阈值 (m)
MASS_DEVIATION_PCT = 0.10  # 质量偏差百分比（±10%）
WIND_MEAN_MAX_MPS = 4.0  # 平均风速阈值 (m/s)

# ── 车辆 Logger 参数辨识配置 ────────────────────────────────────────────
# 仅包含有 SRF Logger 数据的车辆
# max_torque_nm: EEC1 模式所需的电机最大扭矩
# date_range: Logger 数据可用日期范围
IDENTIFICATION_CONFIGS: dict[str, dict] = {
    "YN25RSY": {
        "max_torque_nm": 1000,
        "description": "Mercedes-Benz eActros 600 — 双电机系统，EEC1 报告系统级",
        "date_range": ("2025-08-26", "2026-01-15"),
        "has_eec1": True,
    },
    "YK73WFN": {
        "max_torque_nm": 2400,
        "description": "Volvo FM Electric — 电机额定扭矩 ~2400 Nm",
        "date_range": ("2025-03-20", "2025-08-31"),
        "has_eec1": True,
    },
}

# ── 绘图参数 ──────────────────────────────────────────────────────────────
LABEL_FONT_SIZE = 16
TITLE_FONT_SIZE = 14
TICK_FONT_SIZE = 14
LEGEND_FONT_SIZE = 14
LINE_COLOR_CLUSTER_0 = "blue"
LINE_COLOR_CLUSTER_1 = "green"
INTERSECTION_COLOR = "red"

# ── 日志 ──────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def load_vehicle_configs() -> dict:
    """加载 JOLT 车辆配置 (vehicles.json)。"""
    with open(VEHICLES_JSON, encoding="utf-8") as f:
        return json.load(f)
