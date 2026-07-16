"""
Segmentation shared constants and configuration loading.

Raw-telemetry column-name constants (overridable per vehicle via
``VEHICLE_CONFIG``), the mass-clustering default thresholds, the private
anchor-key set, and the SINGLE load site of ``VEHICLE_CONFIG`` /
``PIPELINE_CONFIGS`` (shared by reference across the package — every other
module imports these bindings; do not add a second load site).

Behaviour-preserving split of the former ``segment_algorithms.py`` (v3.0.0).
"""
from __future__ import annotations

from typing import Any

# ── 原始遥测列名常量（默认值；VEHICLE_CONFIG 可按车型覆盖）─────────────────────
TIME_COL         = 'eventDatetime'
SOC_COL          = 'electricBatteryLevelPercent'
AC_COL           = 'battery_pack_ac_watthours'
DC_COL           = 'battery_pack_dc_watthours'
ODO_COL          = 'odometer'
MOVING_COL       = 'electric_energy_wheelbased_speed_over_zero'
TOTAL_ENERGY_COL = 'total_electric_energy_used_plugged_in_included'
MASS_COL         = 'gross_combination_vehicle_weight'
RECUP_COL        = 'electric_energy_recuperation_watthours'

# ── 质量聚类参数默认值 ──────────────────────────────────────────────────────────
MIN_CLUSTER_GAP_KG   = 2000.0   # 聚类间最小质量差（kg）：两个聚类平均值差 < 此值则合并
TRACTOR_ONLY_MAX_KG  = 13000.0  # cluster 0 均值低于此值时判定为 tractor-only，忽略其质量
# v2.2.4: J1939 gross-combination-weight 在静止时（装卸货瞬态 / 默认广播）不可靠，
# 会污染质量聚类。聚类均值只用「行驶中」(speed > 此阈值, km/h) 的读数计算；与各
# pipeline 的 speed_threshold_kmh 约定（默认 1.0）对齐。NaN speed 视为非行驶。
MOVING_SPEED_THRESHOLD_KMH = 1.0

# segment dict 中的临时锚点字段（不写入 CSV）
_ANCHOR_PRIVATE_KEYS: frozenset = frozenset({
    '_anchor_start_time', '_anchor_end_time',
    '_anchor_start_rel_kwh', '_anchor_end_rel_kwh',
})

# ── 配置加载（从 JSON 文件）─────────────────────────────────────────────────
import json as _json
from jolt_toolkit.configs import get_config_path as _get_config_path

def _load_json(name: str) -> dict:
    """Load a JSON config file from the active config directory.

    Raises ``FileNotFoundError`` with an actionable message when the file is
    missing (previously returned ``{}`` silently, which surfaced much later as
    an empty ``VEHICLE_CONFIG`` and a cryptic 'vehicle not registered' error).
    """
    path = _get_config_path(name)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file '{name}' not found at {path}. If jolt_toolkit was "
            f"installed as a wheel, ensure the configs are packaged "
            f"(pyproject 'jolt_toolkit.configs' package-data), or set the "
            f"JOLT_CONFIG_DIR environment variable to a directory containing "
            f"vehicles.json / pipelines.json / plot_config.json."
        )
    with open(path, 'r', encoding='utf-8') as f:
        return _json.load(f)

VEHICLE_CONFIG: dict[str, dict[str, Any]] = _load_json('vehicles.json')
PIPELINE_CONFIGS: dict[str, dict] = _load_json('pipelines.json')
