"""
diesel_pipeline.py
==================
柴油车 Logger 侧数据处理管线（v2.2.2 新增；v2.2.3 切换到独立 DIESEL_HEADERS）。

与电动车 pipeline 的主要区别：
  * 数据源是 SRFLOGGER_V1 legs（而非 FPS telematics legs）
  * 能量来自 LFC `engine total fuel used` 累积油耗（L），乘柴油 LHV 换算为 kWh
  * 距离来自 VDHR `hr total vehicle distance` 累积里程（km）
  * 车辆质量来自 Logger 侧 `CVW gross combination vehicle weight`
  * 没有 SOC、没有充电事件、没有 effective capacity 修正
  * Trip 分段沿用 segment_algorithms.find_speed_trips（完全共享逻辑）
  * **Excel 列集独立**：使用 ``DIESEL_HEADERS``（见 report_builder.py），
    不再混用电车 ``HEADERS`` 并把电量相关列（SOC、Battery Capacity、
    Energy Performance kWh/km 等）写 NaN。

面向外部的入口：
  * process_diesel_leg(leg, cfg, cumulative_km, srf_data, ...) -> (row_tuples, cumulative_km)

本模块额外承担柴油车的 validation figures 生成（4 面板：Speed / 累计油耗 /
累计里程 / GCVW），代替电车的 plot_leg_validation。
"""
from __future__ import annotations

import datetime
import json
import logging
import re
from math import nan
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from jolt_toolkit.report_generator.segment_algorithms import (
    find_speed_trips,
    TIME_COL,
    VEHICLE_CONFIG,
    # Shared validation-figure styling primitives (v2.2.4): the rounded white
    # data-label background and the post-draw collector that externalises every
    # such label to a sidecar JSON. Reused verbatim so diesel figures match the
    # EV figures' interactive-overlay behaviour (DRY — one source of truth).
    _TEXT_BBOX,
    _export_overlay_boxes,
)
from jolt_toolkit.report_generator.report_builder import (
    DIESEL_HEADERS,
    _build_logger_url,
    _point_str,
    _get_postcode,
    _write_html_viewer,
)

logger = logging.getLogger(__name__)


# ── Logger channel 名常量（与 vehicles.json 字段对应的默认值）─────────────
DEFAULT_SPEED_COL = "CCVS wheel based vehicle speed"
DEFAULT_SPEED_FALLBACK = "2 speed"           # GPS m/s
DEFAULT_FUEL_COL = "LFC engine total fuel used"   # 累积 L
DEFAULT_FUEL_RATE_COL = "LFE fuel rate"           # 瞬时 L/h
DEFAULT_DISTANCE_COL = "VDHR hr total vehicle distance"  # 累积 km
DEFAULT_MASS_COL = "CVW gross combination vehicle weight"
DEFAULT_ALTITUDE_COL = "2 altitude"
DEFAULT_AMBIENT_TEMP_COL = "AMB ambient air temperature"
DEFAULT_DIESEL_LHV_KWH_PER_L = 10.0   # 柴油低热值 ≈ 36 MJ/L / 3600 s/h = 10 kWh/L
DEFAULT_MIN_TRIP_DISTANCE_KM = 1.0    # 低于该距离的 "trip" 被视为 depot shuffling 噪声

# ── Logger Channel 7 天气通道（与 logger_patcher.py 保持一致）─────────────
_W_TEMP   = '7 temperature'
_W_PRESS  = '7 pressure'
_W_HUMID  = '7 humidity'
_W_WIND_S = '7 wind speed'
_W_WIND_D = '7 wind direction'
_CARDINALS = ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')


def _row_col_index(col_name: str) -> int:
    """返回 col_name 在 row tuple 中的 0-based 索引（不含 Leg Number 列）。"""
    return DIESEL_HEADERS.index(col_name) - 1


def _build_logger_df(leg, cfg: dict) -> pd.DataFrame | None:
    """
    从一个 SRFLOGGER leg 拉取柴油 pipeline 需要的所有通道，合并到单个 DataFrame。

    返回的 DataFrame:
      - 索引：UTC 时间戳
      - 列（存在即加）:
        {speed_col}, {fuel_col}, {fuel_rate_col}, {distance_col}, {mass_col},
        {altitude_col}, {ambient_temp_col}, "_lat", "_lon"
      - 额外列 TIME_COL：与索引同值，供 find_speed_trips 使用

    若 leg 不含 CCVS 和 GPS Channel 2 两种速度源，返回 None。
    """
    types_avail = set(leg.types)

    speed_col = cfg.get("speed_col", DEFAULT_SPEED_COL)
    speed_fb = cfg.get("speed_col_fallback", DEFAULT_SPEED_FALLBACK)
    fuel_col = cfg.get("fuel_energy_col", DEFAULT_FUEL_COL)
    fuel_rate_col = cfg.get("fuel_rate_col", DEFAULT_FUEL_RATE_COL)
    dist_col = cfg.get("distance_col", DEFAULT_DISTANCE_COL)
    mass_col = cfg.get("mass_col", DEFAULT_MASS_COL)
    alt_col = cfg.get("altitude_col", DEFAULT_ALTITUDE_COL)
    temp_col = cfg.get("ambient_temp_col", DEFAULT_AMBIENT_TEMP_COL)

    frames: list[pd.DataFrame] = []

    def _pull(channel: str, wanted_cols: list[str]) -> None:
        """抓一个 J1939 channel，筛出 wanted_cols 里真实存在的列，加入 frames。"""
        if channel not in types_avail:
            return
        try:
            df_ch = leg.get_data_frame(channel, resolution="1s")
        except Exception as exc:
            logger.debug("  leg %s channel %s 拉取失败: %s", leg.uri, channel, exc)
            return
        if df_ch is None or df_ch.empty:
            return
        keep = [c for c in wanted_cols if c in df_ch.columns]
        if keep:
            frames.append(df_ch[keep])

    # ── CCVS（主速度源）───────────────────────────────────────────────
    _pull("CCVS", [speed_col])

    # ── LFC（累积油耗）────────────────────────────────────────────────
    _pull("LFC", [fuel_col])

    # ── LFE（瞬时油耗）────────────────────────────────────────────────
    _pull("LFE", [fuel_rate_col])

    # ── VDHR（累积里程）───────────────────────────────────────────────
    _pull("VDHR", [dist_col])

    # ── CVW（实时车辆质量）────────────────────────────────────────────
    _pull("CVW", [mass_col])

    # ── AMB（环境温度）────────────────────────────────────────────────
    _pull("AMB", [temp_col])

    # ── Channel 7（Logger 气象站：温度/气压/湿度/风速/风向）──────────
    if "7" in types_avail:
        try:
            df_w = leg.get_data_frame("7", resolution="1s")
            if df_w is not None and not df_w.empty:
                keep = [c for c in (_W_TEMP, _W_PRESS, _W_HUMID, _W_WIND_S, _W_WIND_D)
                        if c in df_w.columns]
                if keep:
                    frames.append(df_w[keep])
        except Exception as exc:
            logger.debug("  leg %s channel 7 拉取失败: %s", leg.uri, exc)

    # ── Channel 2（GPS 定位 + fallback 速度 + 海拔）──────────────────
    if "2" in types_avail:
        try:
            df_gps = leg.get_data_frame("2", resolution="1s")
            if df_gps is not None and not df_gps.empty:
                gps_cols = {}
                if "2 longitude" in df_gps.columns:
                    gps_cols["_lon"] = df_gps["2 longitude"]
                if "2 latitude" in df_gps.columns:
                    gps_cols["_lat"] = df_gps["2 latitude"]
                if alt_col in df_gps.columns:
                    gps_cols[alt_col] = df_gps[alt_col]
                if speed_fb in df_gps.columns:
                    gps_cols[speed_fb] = df_gps[speed_fb]
                if gps_cols:
                    frames.append(pd.DataFrame(gps_cols, index=df_gps.index))
        except Exception as exc:
            logger.debug("  leg %s channel 2 拉取失败: %s", leg.uri, exc)

    if not frames:
        return None

    # 按时间戳 outer join（不同 channel 采样间隔可能不同）
    df = pd.concat(frames, axis=1)
    return _finalise_logger_df(df, cfg, source=getattr(leg, "uri", "?"))


def _finalise_logger_df(
    df: pd.DataFrame, cfg: dict, source: str = "?"
) -> pd.DataFrame | None:
    """
    收尾一个 Logger DataFrame：去重 + UTC 索引 + TIME_COL + 速度 fallback。

    抽取自 :func:`_build_logger_df` 的尾段，供两条数据源共享：
      * SRF leg（``_build_logger_df`` 拉取后的 concat 结果）
      * 本地 ``raw_logger_*/logger_*.csv``（:func:`_logger_df_from_csv` 读取后）

    ``source`` 仅用于 debug 日志标识来源。若处理后没有可用主速度列，返回 None。
    """
    speed_col = cfg.get("speed_col", DEFAULT_SPEED_COL)
    speed_fb = cfg.get("speed_col_fallback", DEFAULT_SPEED_FALLBACK)

    df = df[~df.index.duplicated(keep="first")].sort_index()

    # 确保索引带 UTC 时区
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    # 加 TIME_COL 列供 find_speed_trips 使用
    df[TIME_COL] = df.index

    # 主速度列处理：若 CCVS 速度空，用 GPS speed × 3.6 fallback
    if speed_col not in df.columns or pd.to_numeric(df[speed_col], errors="coerce").notna().sum() == 0:
        if speed_fb in df.columns:
            df[speed_col] = pd.to_numeric(df[speed_fb], errors="coerce") * 3.6
            logger.debug("  leg %s 使用 GPS speed fallback (m/s × 3.6)", source)
        else:
            return None  # 无速度源

    return df


def _logger_df_from_csv(csv_path: Path, cfg: dict) -> pd.DataFrame | None:
    """
    从本地 ``raw_logger_*/logger_*.csv`` 重建柴油 pipeline 的 Logger DataFrame。

    这些 CSV 由 :func:`_generator.JOLTReportGenerator._save_logger_data` 以
    ``get_data_frame(list(available), resolution='1s')`` 落盘，首列是时间戳索引，
    其余列为所有 J1939 通道的真实列名（CCVS / LFC / VDHR / CVW / Channel 7 等），
    与 :func:`_build_logger_df` 实时拉取并 concat 后的结果同形。读取后交给
    :func:`_finalise_logger_df` 做同样的索引 / 速度 fallback 收尾，因此无需 SRF。
    """
    try:
        df = pd.read_csv(csv_path, index_col=0)
    except Exception as exc:
        logger.debug("  读取 logger CSV 失败 %s: %s", csv_path.name, exc)
        return None
    if df is None or df.empty:
        return None
    idx = pd.to_datetime(df.index, errors="coerce", utc=True)
    df = df.loc[~idx.isna()]
    df.index = idx[~idx.isna()]
    if df.empty:
        return None
    return _finalise_logger_df(df, cfg, source=csv_path.name)


def _safe_stat(series: pd.Series, fn=np.nanmean, default=nan) -> float:
    """对可能有 NaN/空的 series 做聚合，空则返回 default。"""
    try:
        s = pd.to_numeric(series, errors="coerce").dropna()
        if len(s) == 0:
            return default
        val = fn(s.values)
        if pd.isna(val):
            return default
        return float(val)
    except Exception:
        return default


def _trip_metrics(
    df: pd.DataFrame,
    t_start: pd.Timestamp,
    t_end: pd.Timestamp,
    cfg: dict,
    mass_fallback_kg: float | None = None,
) -> dict[str, Any]:
    """
    计算一个 trip 时间窗口内的所有指标。

    ``mass_fallback_kg`` 是前一段有效 trip 的 CVW 读数（由 process_diesel_leg
    维护），在当前 trip 的 CVW 窗口没有任何有效采样时作为 carry-over 使用。
    若 carry-over 也不可用，再 fallback 到 ``cfg['weight_class_t'] * 1000``。
    """
    fuel_col = cfg.get("fuel_energy_col", DEFAULT_FUEL_COL)
    dist_col = cfg.get("distance_col", DEFAULT_DISTANCE_COL)
    mass_col = cfg.get("mass_col", DEFAULT_MASS_COL)
    alt_col = cfg.get("altitude_col", DEFAULT_ALTITUDE_COL)
    temp_col = cfg.get("ambient_temp_col", DEFAULT_AMBIENT_TEMP_COL)
    lhv = float(cfg.get("diesel_lhv_kwh_per_l", DEFAULT_DIESEL_LHV_KWH_PER_L))

    if t_start.tzinfo is None:
        t_start = t_start.tz_localize("UTC")
    if t_end.tzinfo is None:
        t_end = t_end.tz_localize("UTC")

    sl = df.loc[t_start:t_end]
    if sl.empty:
        return {}

    # ── 油耗：累积列差分 ─────────────────────────────────────────────
    # LFC 计数器按 0.5 L 步长更新；短 trip 窗口可能整段都没 tick，导致
    # delta=0 出现在一个正在移动的 trip 上。那种情况实际是 "unknown"，
    # 不是 "zero consumption" —— 在下游用 fuel_l IS NULL 做 dist-guard 修正。
    fuel_l = nan
    if fuel_col in sl.columns:
        fuel_series = pd.to_numeric(sl[fuel_col], errors="coerce").dropna()
        if len(fuel_series) >= 2:
            delta = float(fuel_series.iloc[-1] - fuel_series.iloc[0])
            if delta > 0:
                fuel_l = round(delta, 3)
            # delta == 0 on a moving trip → LFC counter did not tick; leave NaN
    energy_kwh = round(fuel_l * lhv, 3) if not np.isnan(fuel_l) else nan

    # ── 距离：累积里程差分 ───────────────────────────────────────────
    distance_km = nan
    if dist_col in sl.columns:
        d_series = pd.to_numeric(sl[dist_col], errors="coerce").dropna()
        if len(d_series) >= 2:
            delta = float(d_series.iloc[-1] - d_series.iloc[0])
            if delta >= 0:
                distance_km = round(delta, 3)

    # ── 速度积分兜底 ─────────────────────────────────────────────────
    speed_col = cfg.get("speed_col", DEFAULT_SPEED_COL)
    if (np.isnan(distance_km) or distance_km == 0) and speed_col in sl.columns:
        spd = pd.to_numeric(sl[speed_col], errors="coerce").fillna(0.0)
        if len(spd) >= 2:
            dt_s = np.diff(sl.index.values).astype("timedelta64[ms]").astype(float) / 1000.0
            v_ms = spd.values[:-1] / 3.6
            distance_km = round(float(np.sum(v_ms * dt_s) / 1000.0), 3)

    # ── 平均速度 ─────────────────────────────────────────────────────
    dur_s = (t_end - t_start).total_seconds()
    avg_speed = round(distance_km / (dur_s / 3600.0), 2) if (
        not np.isnan(distance_km) and dur_s > 0) else nan

    # ── 质量：trip 内 CVW 中位数；不可用时按 fallback 链取值 ────────
    veh_mass = nan
    veh_mass_cv = nan
    mass_source = 'cvw_trip'  # 'cvw_trip' | 'cvw_carryover' | 'weight_class'
    if mass_col in sl.columns:
        m_all = pd.to_numeric(sl[mass_col], errors="coerce")
        # 排除 CVW 计数器在静止时广播的 0
        valid_m = m_all.notna() & (m_all > 0)
        # v2.2.4: 优先只用行驶中 (speed > 阈值) 的 CVW 读数；trip 内停车瞬态
        # （红灯 / 装卸货）的 CVW 同样不可靠。窗口内行驶样本 < 1 时回退全部 > 0。
        thr = float(cfg.get("speed_threshold_kmh", 1.0))
        if speed_col in sl.columns:
            spd_m = pd.to_numeric(sl[speed_col], errors="coerce")
            moving_m = valid_m & spd_m.notna() & (spd_m > thr)
            if moving_m.sum() >= 1:
                valid_m = moving_m
        m = m_all[valid_m]
        if len(m) > 0:
            veh_mass = float(np.nanmedian(m.values))
            if len(m) > 2 and m.mean() > 0:
                veh_mass_cv = round(float(m.std() / m.mean()), 4)
    if np.isnan(veh_mass) and mass_fallback_kg is not None and mass_fallback_kg > 0:
        veh_mass = float(mass_fallback_kg)
        mass_source = 'cvw_carryover'
    if np.isnan(veh_mass):
        wc_t = cfg.get("weight_class_t")
        if wc_t is not None:
            veh_mass = float(wc_t) * 1000.0
            mass_source = 'weight_class'

    # ── 海拔差 ───────────────────────────────────────────────────────
    elev_diff = nan
    if alt_col in sl.columns:
        e = pd.to_numeric(sl[alt_col], errors="coerce").dropna()
        if len(e) >= 2:
            elev_diff = round(float(e.iloc[-1] - e.iloc[0]), 2)

    # ── 环境温度平均值 ────────────────────────────────────────────────
    # 优先用 Logger Channel 7 天气站 (`7 temperature`)，因为它是专门的气象传感器，
    # 比发动机舱 AMB 读数更贴近报告语义的 "ambient temperature"。
    # Channel 7 不可用时 fallback 到 AMB。
    temp_avg = nan
    if _W_TEMP in sl.columns:
        temp_avg = _safe_stat(sl[_W_TEMP])
    if np.isnan(temp_avg) and temp_col in sl.columns:
        temp_avg = _safe_stat(sl[temp_col])

    # ── Logger Channel 7 其余天气字段 (气压 / 湿度 / 风速 / 风向) ──
    pressure_avg = _safe_stat(sl[_W_PRESS]) if _W_PRESS in sl.columns else nan
    humidity_avg = _safe_stat(sl[_W_HUMID]) if _W_HUMID in sl.columns else nan
    wind_speed_avg = _safe_stat(sl[_W_WIND_S]) if _W_WIND_S in sl.columns else nan
    wind_dir_text = None
    if _W_WIND_D in sl.columns:
        wd_deg = _safe_stat(sl[_W_WIND_D])
        if not np.isnan(wd_deg):
            wind_dir_text = _CARDINALS[round(wd_deg / 45.0) % 8]

    # ── Origin / Destination ─────────────────────────────────────────
    lat_s = lon_s = lat_e = lon_e = None
    if "_lat" in sl.columns and "_lon" in sl.columns:
        lat_series = pd.to_numeric(sl["_lat"], errors="coerce").dropna()
        lon_series = pd.to_numeric(sl["_lon"], errors="coerce").dropna()
        if len(lat_series) >= 1 and len(lon_series) >= 1:
            lat_s = float(lat_series.iloc[0])
            lon_s = float(lon_series.iloc[0])
            lat_e = float(lat_series.iloc[-1])
            lon_e = float(lon_series.iloc[-1])

    # ── Fuel Consumption (L/100km) —— 柴油车主指标 ─────────────────
    fuel_consumption_l_per_100km = nan
    if (not np.isnan(distance_km) and distance_km > 0
            and not np.isnan(fuel_l)):
        fuel_consumption_l_per_100km = round(fuel_l / distance_km * 100.0, 3)

    return {
        "start_time": t_start,
        "end_time": t_end,
        "fuel_l": fuel_l,
        "energy_kwh": energy_kwh,
        "distance_km": distance_km,
        "avg_speed": avg_speed,
        "veh_mass": veh_mass,
        "veh_mass_cv": veh_mass_cv,
        "mass_source": mass_source,
        "elev_diff": elev_diff,
        "temp_avg": temp_avg,
        "pressure_avg": pressure_avg,
        "humidity_avg": humidity_avg,
        "wind_speed_avg": wind_speed_avg,
        "wind_dir_text": wind_dir_text,
        "lat_s": lat_s, "lon_s": lon_s,
        "lat_e": lat_e, "lon_e": lon_e,
        "fuel_consumption_l_per_100km": fuel_consumption_l_per_100km,
    }


def _diesel_seg_to_row(
    seg: dict,
    leg_uri: str,
    cumulative_km: float,
    srf_data=None,
) -> tuple[tuple, float]:
    """
    把一个 diesel trip dict 转换成一个 row tuple（顺序与 DIESEL_HEADERS 一致，去掉 Leg Number）。

    柴油车列集是独立于电车 HEADERS 的 DIESEL_HEADERS —— 不出现 SOC、AC/DC、
    Battery Capacity、Energy Performance (kWh/km) 等与电量相关的列。
    Stop / Charge 永不在此生成（柴油车无充电，Stop 由 _insert_stop_rows 后处理合成）。
    """
    t_s = seg["start_time"]
    t_e = seg["end_time"]

    distance = seg.get("distance_km", nan)
    if not np.isnan(distance):
        cumulative_km += distance

    # 只有 SRF Logger leg 链接；柴油车没有 FPS telematics、没有充电桩
    logger_url = _build_logger_url(leg_uri, t_s, t_e)

    # Origin / Destination
    origin = _point_str(seg.get("lat_s"), seg.get("lon_s"))
    destination = _point_str(seg.get("lat_e"), seg.get("lon_e"))
    origin_pc = _get_postcode(seg.get("lat_s"), seg.get("lon_s"), srf_data)
    dest_pc = _get_postcode(seg.get("lat_e"), seg.get("lon_e"), srf_data)

    # Duration (fractional days for Excel [hh]:mm:ss format)
    dur_days = (pd.Timestamp(t_e) - pd.Timestamp(t_s)).total_seconds() / 86400.0

    # Leg Type
    leg_type = "In Transit"  # 沿用 EV 放电 Trip 的命名，跨车对比时直接可比

    row = (
        leg_type,                                       # Leg Type
        logger_url,                                     # SRF Logger Link
        pd.Timestamp(t_s),                              # Start Time (UTC)
        origin,                                         # Origin (Lat, Lon)
        origin_pc,                                      # Origin Place
        pd.Timestamp(t_e),                              # End Time (UTC)
        destination,                                    # Destination (Lat, Lon)
        dest_pc,                                        # Destination Place
        dur_days,                                       # Duration (HH:MM:SS)
        distance,                                       # Distance (km)
        seg.get("avg_speed", nan),                      # Average Speed (km/h)
        seg.get("elev_diff", nan),                      # Elevation Difference (m)
        seg.get("veh_mass", nan),                       # Vehicle Mass (kg)
        seg.get("veh_mass_cv", nan),                    # Vehicle Mass CV (reliability)
        cumulative_km,                                  # Cumulative Distance (km)
        seg.get("fuel_l", nan),                         # Fuel Used (L)
        seg.get("fuel_consumption_l_per_100km", nan),   # Fuel Consumption (L/100km)
        seg.get("temp_avg", nan),                       # Average Temperature (C)  — Logger Channel 7
        seg.get("pressure_avg", nan),                   # Average Pressure (hPa)   — Logger Channel 7
        seg.get("humidity_avg", nan),                   # Average Humidity (%)     — Logger Channel 7
        seg.get("wind_speed_avg", nan),                 # Average Wind Speed (m/s) — Logger Channel 7
        seg.get("wind_dir_text") or nan,                # Average Wind Direction   — Logger Channel 7
        nan,                                            # Weather Type — text label, 仍需 OpenWeather WeatherPatcher
        "lfc_fuel",                                     # Energy Source
    )

    assert len(row) == len(DIESEL_HEADERS) - 1, (
        f"diesel row length {len(row)} != expected {len(DIESEL_HEADERS) - 1}"
    )
    return row, cumulative_km


def plot_diesel_leg_validation(
    df: pd.DataFrame,
    trips: list[tuple[pd.Timestamp, pd.Timestamp]],
    seg_metrics: list[dict],
    reg: str,
    suffix: str,
    out_path: Path,
    cfg: dict,
    export_overlay: bool = False,
) -> None:
    """
    柴油车 4 面板 leg validation 图（替代 plot_leg_validation，后者强依赖 SOC）。

    Panel 1 (Speed)                — CCVS wheel-based vehicle speed（或 GPS fallback）
    Panel 2 (Cumulative Fuel Used) — LFC engine total fuel used 归零化后的累计曲线
    Panel 3 (Cumulative Distance)  — VDHR hr total vehicle distance 归零化后的累计曲线
    Panel 4 (Vehicle Mass)         — CVW gross combination vehicle weight
    所有面板上叠加 trip 窗口阴影；Panel 4 每个 trip 上标注 per-trip 平均质量。

    字号 / 布局与电车 :func:`plot_leg_validation` 对齐（v2.2.4）：轴标题 / 轴标签
    用 ``_LABEL_FONT=20``、刻度用 ``_TICK_FONT=16``、四个子图 legend 统一用
    ``_LEGEND_FONT=18``。圆角数据标注（per-trip 油耗 / 质量）画成 ``bbox=_TEXT_BBOX``。

    ``export_overlay`` 镜像电车的 ``export_dsoc_overlay``：True 时在 ``fig.canvas.draw()``
    后用共享的 :func:`_export_overlay_boxes` 把所有圆角标注从 PNG 中剥离并写到
    ``<png-stem>.boxes.json`` sidecar（供 inspect HTML 渲染交互 overlay），保存时
    **不带** ``bbox_inches='tight'`` 以保持 figure-fraction 坐标映射；False 时维持旧
    行为，把标注烤进 PNG。就地重画入口 :func:`regenerate_diesel_validation` 传 True。
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
    except ImportError:
        logger.debug("matplotlib 不可用，跳过柴油 validation figure")
        return

    if df is None or df.empty:
        return

    speed_col = cfg.get("speed_col", DEFAULT_SPEED_COL)
    fuel_col = cfg.get("fuel_energy_col", DEFAULT_FUEL_COL)
    dist_col = cfg.get("distance_col", DEFAULT_DISTANCE_COL)
    mass_col = cfg.get("mass_col", DEFAULT_MASS_COL)

    _DISCHARGE_COLOR = '#C8E6C9'  # 浅绿，和电车 Trip 颜色保持一致
    # Two-line short format matching the EV plot_leg_validation. The previous
    # single-line '%Y-%m-%d %H:%M' was too wide and collided horizontally once
    # the tick font doubled to 16.
    _DATE_FMT = '%d %b\n%H:%M'
    # In-figure fonts aligned with the EV plot_leg_validation (v2.2.4, doubled).
    # The larger figure + DPI give the 2x two-line y-labels and the legends room
    # so nothing overlaps or clips at this scale.
    _LABEL_FONT = 20
    _TICK_FONT = 16
    _LEGEND_FONT = 18
    # Baked size for the rounded-bbox data labels — only visible when they are
    # NOT externalised (``export_overlay=False``); otherwise governed by viewer CSS.
    _DATA_FONT = 14
    _DPI = 150

    fig, (ax1, ax2, ax3, ax4) = plt.subplots(
        4, 1, figsize=(18, 10), sharex=True,
        gridspec_kw={'height_ratios': [1.6, 1.2, 1.2, 1.6]},
    )

    def _overlay(ax):
        for t_s, t_e in trips:
            ax.axvspan(pd.Timestamp(t_s), pd.Timestamp(t_e),
                       color=_DISCHARGE_COLOR, alpha=0.55, zorder=1)

    # ── Panel 1: Speed ─────────────────────────────────────────────────
    if speed_col in df.columns:
        spd = pd.to_numeric(df[speed_col], errors='coerce')
        ax1.plot(df.index, spd, color='#1565C0', lw=1.0, alpha=0.9,
                 label='CCVS speed (km/h)')
    _overlay(ax1)
    ax1.set_ylabel('Speed (km/h)', fontsize=_LABEL_FONT)
    # 固定 0–100 km/h：与电车 plot_leg_validation 的 Panel 1 Speed 轴保持一致
    ax1.set_ylim(0, 100)
    ax1.grid(True, alpha=0.3)
    legend_items1 = [
        Patch(color=_DISCHARGE_COLOR, alpha=0.6,
              label=f'Trip ({len(trips)} segs)'),
        Line2D([0], [0], color='#1565C0', lw=1.5, label='Speed'),
    ]
    ax1.legend(handles=legend_items1, fontsize=_LEGEND_FONT, loc='upper right')
    ax1.set_title(f'{reg}  {suffix}  [Diesel Segment Validation]',
                  fontsize=_LABEL_FONT)

    # ── Panel 2: Cumulative Fuel Used (L) ──────────────────────────────
    if fuel_col in df.columns:
        fuel = pd.to_numeric(df[fuel_col], errors='coerce')
        mask = fuel.notna()
        if mask.any():
            base = float(fuel[mask].iloc[0])
            ax2.plot(df.index[mask], fuel[mask] - base,
                     color='#8D6E63', lw=1.8, alpha=0.9,
                     label='LFC total fuel used (normalised)')
        # per-trip 油耗注记
        for seg in seg_metrics:
            if np.isnan(seg.get('fuel_l', nan)):
                continue
            t_s_seg = pd.Timestamp(seg['start_time'])
            t_e_seg = pd.Timestamp(seg['end_time'])
            mid = t_s_seg + (t_e_seg - t_s_seg) / 2
            # 注释：用 axvspan 外加一个位于中点的 text
            try:
                _fuel_mid = fuel.loc[:t_e_seg].dropna()
                if len(_fuel_mid) > 0:
                    y_lvl = float(_fuel_mid.iloc[-1]) - base
                    # Rounded-bbox data label so _export_overlay_boxes picks it up.
                    ax2.annotate(f"{seg['fuel_l']:.1f} L",
                                 xy=(mid, y_lvl),
                                 fontsize=_DATA_FONT, color='#4E342E', ha='center',
                                 va='bottom', fontweight='bold', bbox=_TEXT_BBOX)
            except Exception:
                pass
    _overlay(ax2)
    ax2.set_ylabel('Fuel Used\n(L, zeroed)', fontsize=_LABEL_FONT)
    # minimum ymax = 5.0 L：短 trip 强制显示 0–5 L，长 trip 保留数据驱动的更大范围
    ymax2 = max(5.0, ax2.get_ylim()[1])
    ax2.set_ylim(0, ymax2)
    ax2.grid(True, alpha=0.3)
    if ax2.get_legend_handles_labels()[1]:
        ax2.legend(fontsize=_LEGEND_FONT, loc='upper left')

    # ── Panel 3: Cumulative Distance (km) ──────────────────────────────
    if dist_col in df.columns:
        d = pd.to_numeric(df[dist_col], errors='coerce')
        mask = d.notna()
        if mask.any():
            base = float(d[mask].iloc[0])
            ax3.plot(df.index[mask], d[mask] - base,
                     color='#6A1B9A', lw=1.8, alpha=0.9,
                     label='VDHR distance (normalised)')
    _overlay(ax3)
    ax3.set_ylabel('Distance\n(km, zeroed)', fontsize=_LABEL_FONT)
    # minimum ymax = 10.0 km：短 trip 强制显示 0–10 km，长 trip 保留数据驱动的更大范围
    ymax3 = max(10.0, ax3.get_ylim()[1])
    ax3.set_ylim(0, ymax3)
    ax3.grid(True, alpha=0.3)
    if ax3.get_legend_handles_labels()[1]:
        ax3.legend(fontsize=_LEGEND_FONT, loc='upper left')

    # ── Panel 4: GCVW ──────────────────────────────────────────────────
    has_gcvw = False
    if mass_col in df.columns:
        m = pd.to_numeric(df[mass_col], errors='coerce')
        mask = m.notna() & (m > 0)
        if mask.any():
            has_gcvw = True
            ax4.plot(df.index[mask], m[mask],
                     color='#37474F', lw=1.4, alpha=0.8)
            ax4.scatter(df.index[mask], m[mask],
                        color='#37474F', s=5, alpha=0.8)
    # per-trip 平均质量注记
    has_trip_mass = False
    for seg in seg_metrics:
        if np.isnan(seg.get('veh_mass', nan)):
            continue
        has_trip_mass = True
        t_s_seg = pd.Timestamp(seg['start_time'])
        t_e_seg = pd.Timestamp(seg['end_time'])
        seg_mass = float(seg['veh_mass'])
        ax4.plot([t_s_seg, t_e_seg], [seg_mass, seg_mass],
                 color='#2E7D32', lw=3.5, linestyle='--', alpha=0.9, zorder=5)
        mid = t_s_seg + (t_e_seg - t_s_seg) / 2
        # Rounded-bbox data label so _export_overlay_boxes picks it up.
        ax4.text(mid, seg_mass, f' {seg_mass / 1000:.1f} t',
                 ha='center', va='bottom', fontsize=_DATA_FONT,
                 color='#2E7D32', fontweight='bold', zorder=8, bbox=_TEXT_BBOX)
    _overlay(ax4)
    ax4.set_ylabel('GCVW\n(kg)', fontsize=_LABEL_FONT)
    ax4.set_ylim(0, 50000)
    ax4.set_yticks(range(0, 50001, 10000))
    ax4.grid(True, alpha=0.3)
    mass_legend = []
    if has_gcvw:
        mass_legend.append(
            Line2D([0], [0], color='#37474F', lw=1.4, marker='o',
                   markersize=5, label='GCVW reading'))
    if has_trip_mass:
        mass_legend.append(
            Line2D([0], [0], color='#2E7D32', lw=3.5, linestyle='--',
                   label='Per-trip mean'))
    if mass_legend:
        ax4.legend(handles=mass_legend, fontsize=_LEGEND_FONT, loc='upper right')

    # Fix the time axis to the full UTC calendar day [00:00, next 00:00) so that
    # diesel figures from different days share an identical midnight-to-midnight
    # grid (directly comparable across days) instead of autoscaling to each day's
    # actual data span. Mirrors the EV plot_leg_validation. ``df.index`` is a
    # tz-aware UTC DatetimeIndex (forced in _build_logger_df); the middle row is
    # robust against a stray early/late point, and ``.normalize()`` floors it to
    # 00:00:00 keeping the UTC tz so the limits stay in the same date units.
    _t_mid = pd.Timestamp(df.index[len(df.index) // 2])
    day_start = _t_mid.normalize()
    day_end = day_start + pd.Timedelta(days=1)

    fmt = mdates.DateFormatter(_DATE_FMT)
    for ax in (ax1, ax2, ax3, ax4):
        # Fresh locator per axis (DateLocators hold an axis ref). 3-hourly major
        # ticks give an even 00:00 → 24:00 grid that reads both midnights without
        # crowding the two-line '%d %b\n%H:%M' labels.
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 3)))
        ax.xaxis.set_major_formatter(fmt)
        # Size both axes' tick labels to the 2x EV scale (was only ax4 x-major).
        ax.tick_params(axis='both', labelsize=_TICK_FONT)
    # sharex=True → setting the limit once propagates to all four panels.
    ax4.set_xlim(day_start, day_end)
    ax4.set_xlabel('Time (UTC)', fontsize=_LABEL_FONT)

    # h_pad mirrors the EV figure: gives the 2x two-line y-labels of adjacent
    # panels room so they do not crowd at the panel boundaries.
    plt.tight_layout(h_pad=1.4)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if export_overlay:
        # Exact figure-fraction export requires the saved PNG to span the full
        # figure extent, so we save WITHOUT bbox_inches='tight' (which would crop
        # the margins and break the mapping). Draw first so transforms reflect the
        # laid-out axes, then collect + strip every bbox data label before saving.
        fig.canvas.draw()
        boxes = _export_overlay_boxes(fig)
        plt.savefig(out_path, dpi=_DPI)
        sidecar = out_path.with_suffix('.boxes.json')
        if boxes:
            with open(sidecar, 'w', encoding='utf-8') as fh:
                json.dump(boxes, fh, ensure_ascii=False)
        elif sidecar.exists():
            # Stale sidecar from a previous run with labels → remove it so the
            # viewer does not overlay boxes onto a now-empty figure.
            sidecar.unlink()
    else:
        plt.savefig(out_path, dpi=_DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  fig: {out_path.name}')


def _segments_from_df(
    df: pd.DataFrame, cfg: dict, source: str = "?"
) -> tuple[list[tuple[pd.Timestamp, pd.Timestamp]], list[dict]]:
    """
    速度分段 + per-trip 指标 + 过滤链，返回 ``(trips, seg_metrics)``。

    抽取自 :func:`process_diesel_leg`，供两条入口共享同一套分段逻辑（DRY）：
      * ``process_diesel_leg`` —— 生成 xlsx 行（在外层把 seg_metrics 转 row）。
      * :func:`regenerate_diesel_validation` —— 仅重画 validation figure。

    返回的 ``trips`` 是 :func:`find_speed_trips` 的全部窗口（用于图上 trip 阴影），
    ``seg_metrics`` 仅含通过过滤链的 trip（短 trip / pathological 已剔除），
    顺序即 trip 时间顺序，质量 carry-over 已在内部按序应用。
    """
    speed_col = cfg.get("speed_col", DEFAULT_SPEED_COL)
    speed_thr = float(cfg.get("speed_threshold_kmh", 1.0))
    min_stop = float(cfg.get("min_stop_duration_min", 5.0))
    min_trip = float(cfg.get("min_trip_duration_min", 2.0))
    min_trip_km = float(cfg.get("min_trip_distance_km",
                                DEFAULT_MIN_TRIP_DISTANCE_KM))

    trips = find_speed_trips(
        df,
        speed_col=speed_col,
        speed_threshold_kmh=speed_thr,
        min_stop_duration_min=min_stop,
        min_trip_duration_min=min_trip,
    )
    if not trips:
        return [], []

    seg_metrics: list[dict] = []
    # Mass carry-over across trips in the same leg — previous trip's CVW
    # median is used as fallback for a trip whose window has no valid CVW.
    mass_carry: float | None = None
    n_dropped_short = 0
    n_dropped_pathological = 0
    for t_start, t_end in trips:
        seg = _trip_metrics(
            df, pd.Timestamp(t_start), pd.Timestamp(t_end), cfg,
            mass_fallback_kg=mass_carry,
        )
        if not seg:
            continue

        dist = seg.get("distance_km", nan)
        if np.isnan(dist) or dist <= 0:
            continue

        # (1) Drop ghost micro-trips (depot shuffling, GPS noise) below the
        # minimum trip distance. These corrupt fuel/100km because a 0.5 L
        # cold-start cost divided by 300 m gives a triple-digit value.
        if dist < min_trip_km:
            n_dropped_short += 1
            continue

        # (2) Drop pathological trips where Logger channels have no valid
        # data in the window (the 13 m "trip" row 22 case). A trip that
        # doesn't give us at least mass OR fuel OR temperature isn't usable
        # for anything downstream.
        all_nan = (
            np.isnan(seg.get("fuel_l", nan))
            and np.isnan(seg.get("veh_mass", nan))
            and np.isnan(seg.get("temp_avg", nan))
        )
        if all_nan:
            n_dropped_pathological += 1
            continue

        # Promote this trip's CVW median to the carry-over slot so the next
        # trip's fallback chain can use it. We only promote real CVW reads
        # (mass_source == 'cvw_trip'), never fallback values — otherwise a
        # single missing trip would propagate weight_class_t forever.
        if seg.get("mass_source") == "cvw_trip":
            mass_carry = seg["veh_mass"]

        seg_metrics.append(seg)

    if n_dropped_short or n_dropped_pathological:
        logger.debug(
            "  leg %s: dropped %d short (<%.1f km) + %d pathological trips",
            source, n_dropped_short, min_trip_km, n_dropped_pathological,
        )

    return trips, seg_metrics


def process_diesel_leg(
    leg,
    cfg: dict,
    cumulative_km: float,
    srf_data=None,
    out_dir: Path | str | None = None,
    reg: str | None = None,
    debug_mode: bool = False,
    generate_validation_fig: bool = True,
    leg_idx: int = 0,
) -> tuple[list, float]:
    """
    处理一条 SRFLOGGER_V1 leg：拉取 Logger channels、速度分段、per-trip 计算、生成行元组。

    当 ``debug_mode=True`` 且 ``generate_validation_fig=True`` 且 ``out_dir`` 非空时，
    额外生成 4 面板 diesel validation figure 到
    ``{out_dir}/validation_figures/validation_{reg}_{date}_{idx}.png``。
    ``generate_validation_fig=False`` 时跳过画图（与 EV 的 ``run_segment_detection``
    同名参数对齐）——用于 ``--raw-only`` 提速：raw logger CSV 由上游 ``_save_logger_data``
    独立落盘，图稍后由 overlay regenerate 统一重画，避免画两遍。

    Returns
    -------
    (row_list, cumulative_km)
        row_list: list of (start_time, row_tuple) 对 —— 外层保持与 EV 管线相同的格式，
                  方便后续 sort + stop 插入逻辑统一处理。
        cumulative_km: 更新后的累积里程。
    """
    df = _build_logger_df(leg, cfg)
    if df is None or df.empty:
        return [], cumulative_km

    trips, seg_metrics = _segments_from_df(df, cfg, source=getattr(leg, "uri", "?"))
    if not trips:
        return [], cumulative_km

    # Build the row tuples from the kept segments (sequential, so cumulative_km
    # advances trip by trip). ``_segments_from_df`` has already applied the
    # mass carry-over + distance / pathological filtering, so iterating its
    # ``seg_metrics`` here is equivalent to the previous single combined loop.
    rows: list = []
    for seg in seg_metrics:
        row, cumulative_km = _diesel_seg_to_row(
            seg, leg.uri, cumulative_km, srf_data=srf_data,
        )
        rows.append((seg["start_time"], list(row)))

    # ── Validation figure ────────────────────────────────────────────
    # Default export_overlay=False bakes the data labels into the PNG, mirroring
    # the EV initial-gen path (run_segment_detection with export_dsoc_overlay
    # defaulting False). They are externalised only when re-painted in place by
    # regenerate_diesel_validation below.
    if (
        debug_mode
        and generate_validation_fig
        and out_dir is not None
        and reg is not None
        and seg_metrics
    ):
        try:
            leg_date = str(pd.Timestamp(leg.start_time).date())
            suffix = f"{leg_date}_{leg_idx:04d}"
            out_path = Path(out_dir) / 'validation_figures' / \
                f'validation_{reg}_{suffix}.png'
            plot_diesel_leg_validation(
                df, trips, seg_metrics, reg, suffix, out_path, cfg,
            )
        except Exception as exc:
            logger.warning("柴油 validation figure 生成失败: %s", exc)

    return rows, cumulative_km


# 报告文件名解析：jolt_report_<REG>_<YYYYMMDD>_<YYYYMMDD>[_finetuned].xlsx
_XLSX_RE = re.compile(
    r"jolt_report_(?P<reg>\w+?)_(?P<ds>\d{8})_(?P<de>\d{8})"
    r"(?P<ft>_finetuned)?\.xlsx$"
)
# 本地 logger CSV 名解析：logger_<suffix>.csv（suffix == 初始生成时的图后缀）
_LOGGER_CSV_RE = re.compile(r"logger_(?P<suffix>.+)\.csv$")


def regenerate_diesel_validation(
    report_dir: str | Path,
    *,
    reg: str | None = None,
    cfg: dict | None = None,
) -> int:
    """
    就地重画柴油车 4 面板 validation figures + inspect HTML（**不重跑 xlsx**）。

    柴油版的 :meth:`ValidationGenerator.regenerate` —— 后者是电车专用（依赖 SOC +
    FPS ``raw_telematics`` + ``run_segment_detection``，对柴油会 early-return）。
    本函数改从本地 ``raw_logger_*/logger_*.csv`` 重建 Logger DataFrame（不需 SRF
    往返），按与初始生成相同的 idx 后缀 **同名覆盖** 原图，并以
    ``export_overlay=True`` 调用 :func:`plot_diesel_leg_validation`，把所有圆角数据
    标注外置到 ``<png-stem>.boxes.json`` sidecar（由 inspect HTML 渲染交互 overlay）。

    CSV 与图的 idx 一致性：``_save_logger_data`` 落盘 CSV 与柴油主循环出图都对同一
    个 ``SRFLOGGER_V1`` ``logger_legs`` 列表按相同顺序 enumerate，故
    ``logger_<date>_<idx>.csv`` ↔ ``validation_<reg>_<date>_<idx>.png`` 一一对应。

    Args:
        report_dir: 车辆报告目录，含 ``raw_logger_*/`` CSV 与 ``jolt_report_*.xlsx``。
        reg:        车牌；省略时从首个 xlsx 文件名解析。
        cfg:        车辆配置；省略时按 ``reg`` 从 VEHICLE_CONFIG 读取。

    Returns:
        重画的 validation figure 数量。
    """
    report_dir = Path(report_dir)
    xlsx_files = sorted(report_dir.glob("jolt_report_*.xlsx"))

    if reg is None:
        if not xlsx_files:
            logger.error("未找到报告文件，无法解析车辆: %s", report_dir)
            return 0
        m = _XLSX_RE.match(xlsx_files[0].name)
        if not m:
            logger.error("无法解析文件名: %s", xlsx_files[0].name)
            return 0
        reg = m.group("reg")

    if cfg is None:
        cfg = VEHICLE_CONFIG.get(reg)
    if cfg is None:
        logger.error("车辆 %s 未在 vehicles.json 中注册", reg)
        return 0

    # 收集本地 raw_logger CSV（一个目录下可能有 raw_logger_v1 等多个版本子目录）
    logger_dirs = [d for d in sorted(report_dir.glob("raw_logger*")) if d.is_dir()]
    csvs: list[Path] = []
    for d in logger_dirs:
        csvs.extend(sorted(d.glob("logger_*.csv")))
    if not csvs:
        logger.error("目录下无 raw_logger CSV: %s", report_dir)
        return 0

    fig_dir = report_dir / "validation_figures"
    fig_count = 0
    for csv_path in csvs:
        nm = _LOGGER_CSV_RE.match(csv_path.name)
        if not nm:
            continue
        suffix = nm.group("suffix")  # e.g. 2025-06-26_0001
        df = _logger_df_from_csv(csv_path, cfg)
        if df is None or df.empty:
            continue
        trips, seg_metrics = _segments_from_df(df, cfg, source=csv_path.name)
        # 与初始生成一致：无有效 trip（seg_metrics 空）则不出图
        if not seg_metrics:
            continue
        out_path = fig_dir / f"validation_{reg}_{suffix}.png"
        try:
            plot_diesel_leg_validation(
                df, trips, seg_metrics, reg, suffix, out_path, cfg,
                export_overlay=True,
            )
            fig_count += 1
        except Exception as exc:
            logger.warning(
                "柴油 validation figure 重画失败 %s: %s", csv_path.name, exc
            )

    # 为每个非 finetuned 周期 xlsx 各重写一份 inspect HTML（finetuned 周期由
    # report-finetuner 流程负责，跳过以免覆盖其 *_finetuned.png 引用）。
    html_count = 0
    for xlsx in xlsx_files:
        pm = _XLSX_RE.match(xlsx.name)
        if not pm or pm.group("ft"):
            continue
        p_start = datetime.datetime.strptime(pm.group("ds"), "%Y%m%d").date()
        p_end = datetime.datetime.strptime(pm.group("de"), "%Y%m%d").date()
        _write_html_viewer(report_dir, reg, p_start, p_end, xlsx.name)
        html_count += 1

    logger.info(
        "regenerate_diesel_validation: %s 完成 %d 张图, %d 份 inspect HTML",
        reg, fig_count, html_count,
    )
    return fig_count
