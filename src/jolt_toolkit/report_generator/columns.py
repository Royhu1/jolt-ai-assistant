"""
report_generator.columns
========================
Report column contracts: the EV ``HEADERS`` / diesel ``DIESEL_HEADERS`` tuples,
the row-tuple index helper, the leg-type predicates, the ``_is_nan`` guard, and
the telematics source-column name constants. Imports nothing package-internal so
every other report-builder module can depend on it without a cycle.

Split out of report_builder.py in v3.0.0 (pure move; report_builder re-exports
these names for backward compatibility).
"""

from __future__ import annotations

import re

import numpy as np


# ── Excel 报告列头（电动车；与老版 JOLT LegRecord 字段顺序完全一致）─────────
HEADERS = (
    "Leg Number",
    "Leg Type",
    "Telematics Link",
    "Charger Link",
    "SRF Logger Link",
    "Start Time (UTC)",
    "Origin (Lat, Lon)",
    "Origin Place",
    "End Time (UTC)",
    "Destination (Lat, Lon)",
    "Destination Place",
    "Duration (HH:MM:SS)",
    "Distance (km)",
    "Average Speed (km/h)",
    "Elevation Difference (m)",
    "Vehicle Mass (kg)",
    "Vehicle Mass CV (reliability)",
    "Recuperation Energy (kWh)",
    "Start SOC (%)",
    "End SOC (%)",
    "SOC Change (%)",
    "Energy Change (kWh)",
    "Energy Charged AC (kWh)",
    "Energy Charged DC (kWh)",
    "CO2 level (g/kWh)",
    "Cumulative Distance (km)",
    "CO2 for event (g)",
    "Cumulative CO2 (g)",
    "Battery Power (kW)",
    "Energy Performance (kWh/km)",
    "Energy Performance Corrected by Elevation Difference (kWh/km)",
    "Battery Capacity (kWh)",
    "Energy Output from Charger (kWh)",
    "Wire Energy Efficiency (kWh/kWh)",
    "Peak Charging (kW)",
    "Average Charging (kW)",
    "Energy based on motor power (kWh)",
    "Average Temperature (C)",
    "Average Pressure (hPa)",
    "Average Humidity (%)",
    "Average Wind Speed (m/s)",
    "Average Wind Direction",
    "Weather Type",
    "Histogram of Accelerator Pedal Position",
    "Histogram of Decelerator Pedal Position",
    # 新版额外列
    "Energy Source",
    "Energy Performance Kinetics Corrected (kWh/km)",
    # v2.2.3 新增：trip 时段内的电机驱动总能量（kWh），来自 telematics
    # `electric_energy_propulsion` 累计计数器（Wh）按时间窗插值差分。
    # 与 'Energy Change (kWh)' 区别：propulsion **不扣** 再生制动回收，只统计
    # 正向驱动；常用于反算 η_BM。仅 EV；柴油车走 DIESEL_HEADERS 不含此列。
    "Propulsion Energy (kWh)",
    # v2.2.4 新增：去掉辅助/驻车负载（HVAC、低压系统等）后的净牵引能耗效率
    # (kWh/km)。定义见 data_analysis_workspace/energy_balance_check/report.md：
    #   EP_exclude_aux = (propulsion − recuperation) / distance = EP − auxiliary/distance
    # 等价推导：SRF 恒等式 total = propulsion + auxiliary − recuperation，放电
    # trip 的 EP = |Energy Change| / dist ≈ total / dist，故
    #   EP − aux/dist = (total − aux)/dist = (propulsion − recuperation)/dist。
    # 直接用 propulsion 与 recuperation 两个 trip 级量，不依赖 aux 的解算。
    # 仅当三个计数器（propulsion / recuperation）该 trip 都非空时可算，否则 NaN
    # —— 这天然把 EX74JXW / EX74JXY / YN25RSY / YN75NMA（计数器 NaN/缺失）置空。
    # 加在 HEADERS **末尾**：LoggerPatcher / WeatherPatcher 的硬编码列索引
    # （temp=38 / wind=41 / link=5 / mass=16 / kin=47）均 ≤ 47，不受影响。
    # 柴油车走 DIESEL_HEADERS 不含此列。
    "EP_exclude_aux",
    # v2.2.5 新增：单车单 leg 的运营商代码（project operator CODE）。来源级联见
    # report_generator/operators.py（SRF 为主：round-robin 取 leg.trip.trial.
    # description，专属车取 vehicle.organisation.name；vehicles.json 为兜底）。
    # 加在 HEADERS **末尾**，不移动任何既有列索引（LoggerPatcher / WeatherPatcher
    # 的硬编码列索引、_generator 的 _IDX_* 均 ≤ 48，不受影响）。
    "Operator",
)

# ── 柴油车专用列头（v2.2.2 扩展：不再复用电车 HEADERS）────────────────────
# 只保留对柴油有物理意义的字段：不出现 SOC、AC/DC 充电能量、Battery Capacity、
# Energy Performance (kWh/km) 等与电量相关的列。燃油消耗用 L 和 L/100km 表达。
DIESEL_HEADERS = (
    "Leg Number",
    "Leg Type",
    "SRF Logger Link",
    "Start Time (UTC)",
    "Origin (Lat, Lon)",
    "Origin Place",
    "End Time (UTC)",
    "Destination (Lat, Lon)",
    "Destination Place",
    "Duration (HH:MM:SS)",
    "Distance (km)",
    "Average Speed (km/h)",
    "Elevation Difference (m)",
    "Vehicle Mass (kg)",
    "Vehicle Mass CV (reliability)",
    "Cumulative Distance (km)",
    "Fuel Used (L)",
    "Fuel Consumption (L/100km)",
    "Average Temperature (C)",
    "Average Pressure (hPa)",
    "Average Humidity (%)",
    "Average Wind Speed (m/s)",
    "Average Wind Direction",
    "Weather Type",
    "Energy Source",
    # v2.2.5 新增：运营商代码，柴油车与电车列集对齐。加在 **末尾**（diesel row
    # 末尾追加，长度断言 len(row) == len(DIESEL_HEADERS) - 1 自动跟随）。
    "Operator",
)


_CHARGE_LEG_RE = re.compile(r"^(AC|DC|Charge|Mix|estimated)", re.IGNORECASE)


def _leg_is_charge(leg_type) -> bool:
    """True if a Leg Type string denotes a charge segment (red row)."""
    return bool(
        leg_type and isinstance(leg_type, str) and _CHARGE_LEG_RE.match(leg_type)
    )


def _leg_is_stop(leg_type) -> bool:
    """True if a Leg Type string denotes a Stop segment (white row)."""
    return bool(
        leg_type and isinstance(leg_type, str) and leg_type.strip().lower() == "stop"
    )


def is_trip_leg(leg_type) -> bool:
    """True if a Leg Type denotes a driving / trip segment.

    The single shared definition of a "trip" (driving) row: a non-blank Leg Type
    that is neither a charge segment (:func:`_leg_is_charge`) nor a Stop
    (:func:`_leg_is_stop`) — i.e. one of "In House" / "Round Trip" / "Outbound" /
    "Return" / "In Transit" (see :func:`_get_leg_type`). Public because the
    weather patchers import it: weather is backfilled on trip rows ONLY (charge
    and Stop rows do not need weather and would only waste OpenWeather quota), so
    the patchers and the chart ``driving_only`` filter agree on what counts as a
    driving row.
    """
    if not leg_type or not isinstance(leg_type, str) or not leg_type.strip():
        return False
    return not _leg_is_charge(leg_type) and not _leg_is_stop(leg_type)


_WEIGHT_COL = "gross_combination_vehicle_weight"
# v2.2.4: 电车遥测速度列（km/h）。per-leg 质量均值/CV 优先只用行驶中样本，
# 排除静止时不可靠的 GCVW 广播；列缺失时退回旧的全部 (> 0) 样本行为。
_SPEED_COL = "wheel_based_speed"
_RECUP_COL = "electric_energy_recuperation_watthours"
# v2.2.3: 累计电机驱动能量计数器（Wh，since vehicle inception）。trip 起止时间通过
# 线性插值在最近的 RFMS 快照之间得到 Δ，再除以 1000 转 kWh，写入新的
# `Propulsion Energy (kWh)` 列。柴油车没有此列。
_PROPULSION_COL = "electric_energy_propulsion"


def _row_col_index(col_name: str, headers: tuple = HEADERS) -> int:
    """Return the 0-based index of a column inside the row tuple.

    ``headers[0]`` is 'Leg Number' which is written separately by the Excel
    writer and does **not** appear in the row tuple — so the row tuple index is
    ``headers.index(col_name) - 1``. Pass ``DIESEL_HEADERS`` to get the layout
    used by diesel rows.
    """
    return headers.index(col_name) - 1


def _is_nan(v) -> bool:
    """Safe NaN check."""
    if v is None:
        return False
    try:
        return bool(np.isnan(v))
    except (TypeError, ValueError):
        return False
