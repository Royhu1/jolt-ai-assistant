"""
segment_algorithms.py
=====================
充电分段（Volvo / Renault）和放电分段（Scania）的统一检测算法，
并可选生成逐腿验证图。

统一输出 schema（v2）
-------------------
两种模式均输出以下关键字段：

  delta_soc_pct      : 正值 = 充电（SOC 上升）；负值 = 放电（SOC 下降）。
  delta_energy_kwh   : 正值 = 充电（能量流入电池）；负值 = 放电（能量流出）。
                       充电来源：AC+DC 累计差值；
                       放电首选：total_electric_energy_used_plugged_in_included；
                       备选：electric_energy_wheelbased_speed_over_zero；
                       兜底：SOC × nominal_kwh 估算。
  energy_source      : 'ac_dc'         — 充电，来自 AC+DC 列
                       'total_energy'  — 放电，来自 total_electric_energy_used_* 列
                       'moving_energy' — 放电，来自 wheelbased_speed_over_zero 列
                       'soc_estimate'  — 无可用能量列，由 SOC × nominal_kwh 估算
  delta_moving_kwh   : electric_energy_wheelbased_speed_over_zero 累计差值（kWh，>= 0）；
                       数据不可用时为 None。

公开函数
--------
find_charge_segments_by_soc(df_raw, ...)
find_discharge_segments_by_soc(df_raw, ...)
find_speed_trips(df_raw, ...)
find_discharge_segments_by_speed(df_raw, ...)
cluster_mass_data(df_raw, ...)
split_discharge_by_mass(discharge_segs, df_raw, ...)
merge_discharge_by_mass(discharge_segs, df_raw, ...)
run_segment_detection(df_raw, reg, suffix, out_dir,
                      generate_validation_fig=True, ...)

常量
----
TIME_COL, SOC_COL, AC_COL, DC_COL, MOVING_COL, ODO_COL, TOTAL_ENERGY_COL

VEHICLE_CONFIG
    各车辆的 SRF 注册名、分段模式、标称容量、厂商型号及能量列名映射。

_ANCHOR_PRIVATE_KEYS
    segment dict 中仅供绘图使用的临时字段名集合，保存 CSV 前需过滤。
"""
# =============================================================================
# Backward-compatibility facade (v3.0.0)
# -----------------------------------------------------------------------------
# The implementation was split into the ``segmentation/`` sub-package (a pure,
# behaviour-preserving move — see ``segmentation/__init__.py`` for the module
# map). This module re-exports EVERY name that was importable from the former
# monolith so that all existing consumers
# (``_generator`` / ``report_builder`` / ``diesel_pipeline`` / ``finetune`` /
# ``validation_generator`` / ``data_dashboard_detail`` / the patchers / the
# recompute script / archived analysis scripts) keep working unchanged.
#
# Importing this module (or any name below) imports ``validation_figure``, which
# sets the matplotlib ``Agg`` backend — preserving the monolith's import-time
# side-effect.
#
# New code should import from ``jolt_toolkit.report_generator.segmentation``
# directly. Prefer explicit re-exports (below) over ``import *`` so the public
# surface stays documented.
# =============================================================================
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── constants ────────────────────────────────────────────────────────────────
from jolt_toolkit.report_generator.segmentation.constants import (  # noqa: F401
    AC_COL,
    DC_COL,
    MASS_COL,
    MIN_CLUSTER_GAP_KG,
    MOVING_COL,
    MOVING_SPEED_THRESHOLD_KMH,
    ODO_COL,
    PIPELINE_CONFIGS,
    RECUP_COL,
    SOC_COL,
    TIME_COL,
    TOTAL_ENERGY_COL,
    TRACTOR_ONLY_MAX_KG,
    VEHICLE_CONFIG,
    _ANCHOR_PRIVATE_KEYS,
    _load_json,
)

# ── timeutil ─────────────────────────────────────────────────────────────────
from jolt_toolkit.report_generator.segmentation.timeutil import (  # noqa: F401
    _to_utc,
)

# ── mass aggregation ─────────────────────────────────────────────────────────
from jolt_toolkit.report_generator.segmentation.mass_aggregation import (  # noqa: F401
    _MAD_K,
    _MASS_AGG_METHODS,
    _TRIM_FRAC,
    _agg_mass,
    _coerce_seconds,
    _iqr_inliers,
    _mad_inliers,
    _mad_tw_value,
    _time_weighted_mean,
    _trimmed_inliers,
    resolve_mass_agg,
)

# ── SOC-based detection ──────────────────────────────────────────────────────
from jolt_toolkit.report_generator.segmentation.soc_detection import (  # noqa: F401
    find_charge_segments_by_soc,
    find_discharge_segments_by_soc,
)

# ── speed-based detection ────────────────────────────────────────────────────
from jolt_toolkit.report_generator.segmentation.speed_detection import (  # noqa: F401
    _extend_trip_endpoint_to_zero,
    find_discharge_segments_by_speed,
    find_speed_trips,
)

# ── mass clustering / split / merge / anchors ────────────────────────────────
from jolt_toolkit.report_generator.segmentation.mass_clustering import (  # noqa: F401
    _detect_cluster_transitions,
    _enforce_anchor_ordering,
    _get_seg_dominant_cluster,
    _merge_two_discharge_segs,
    _recompute_anchors,
    _split_point_has_zero_speed,
    _split_seg_at_times,
    cluster_mass_data,
    merge_discharge_by_mass,
    split_discharge_by_mass,
)

# ── validation figure (sets matplotlib Agg backend on import) ────────────────
from jolt_toolkit.report_generator.segmentation.validation_figure import (  # noqa: F401
    _CHARGE_COLOR,
    _DATE_FMT,
    _DISCHARGE_COLOR,
    _DPI,
    _DSOC_FONT,
    _FIGURE_SIZE,
    _HAS_MPL,
    _LABEL_FONT,
    _LEGEND_FONT,
    _TEXT_BBOX,
    _TICK_FONT,
    _annotate_overlay_energy_delta,
    _build_energy_series,
    _export_overlay_boxes,
    _mark_anchors_stored,
    _overlay,
    _parse_box_gid,
    plot_leg_validation,
)

# ── top-level orchestrator ───────────────────────────────────────────────────
from jolt_toolkit.report_generator.segmentation.detection import (  # noqa: F401
    run_segment_detection,
)
