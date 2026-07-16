"""
report_generator.row_builder
============================
Converts a segment dict into one Excel report row (``_seg_to_row``): URL
builders, per-metric telematics helpers (mass / recuperation / propulsion /
elevation / elevation- and kinetics-corrected EP), postcode reverse geocoding
with an on-disk cache, home detection + leg-type classification, and Stop-row
synthesis (``_stop_row_from_neighbours`` / ``_insert_stop_rows``).

Split out of report_builder.py in v3.0.0 (pure move).
"""

from __future__ import annotations

import json
from math import nan

import numpy as np
import pandas as pd

from srf_client import paging
from srf_client import filter as srf_filter
from geopy import Point as GeoPoint
from geopy.distance import Distance, geodesic
from urllib.parse import urlencode, urljoin

from jolt_toolkit.report_generator.paths import get_cache_dir
from jolt_toolkit.report_generator.segment_algorithms import (
    TIME_COL,
    MOVING_SPEED_THRESHOLD_KMH,
    _agg_mass,
)
from jolt_toolkit.report_generator.pedal_histogram import (
    compute_pedal_histogram,
    MIN_DISTANCE_FOR_PEDAL_KM,
    EEC2_COL,
    EBC1_COL,
)
from jolt_toolkit.report_generator.columns import (
    HEADERS,
    _WEIGHT_COL,
    _SPEED_COL,
    _RECUP_COL,
    _PROPULSION_COL,
    _row_col_index,
)


# =============================================================================
# URL 构建工具
# =============================================================================


def _ts_iso(t) -> str:
    """将 pd.Timestamp 或 datetime 转换为 ISO 字符串（保留时区）。"""
    ts = pd.Timestamp(t)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return str(ts)


def _build_telematics_url(leg_uri: str, t_start, t_end) -> str | None:
    """构建遥测可视化 URL。"""
    if not leg_uri:
        return None
    query = urlencode(
        {
            "start": _ts_iso(t_start),
            "end": _ts_iso(t_end),
            "type": (96, "HSS2"),
            "resourceUri": leg_uri,
        },
        doseq=True,
    )
    return urljoin(leg_uri, "/explore/graphics/plots") + "?" + query


def _build_charger_url(charger_uri: str, t_start, t_end) -> str | None:
    """构建充电桩可视化 URL。"""
    if not charger_uri:
        return None
    query = urlencode(
        {
            "start": _ts_iso(t_start),
            "end": _ts_iso(t_end),
            "resourceUri": charger_uri,
        }
    )
    return urljoin(charger_uri, "/explore/graphics/usage") + "?" + query


def _build_logger_url(logger_uri: str, t_start, t_end) -> str | None:
    """构建 SRF Logger 可视化 URL。"""
    if not logger_uri:
        return None
    query = urlencode(
        {
            "start": _ts_iso(t_start),
            "end": _ts_iso(t_end),
            "resourceUri": logger_uri,
        }
    )
    return urljoin(logger_uri, "/explore/graphics/plots") + "?" + query


def _find_overlap(windows: list, t_start, t_end, tol_min: float = 5) -> str | None:
    """
    在时间窗口列表中查找与 [t_start, t_end] 重叠的第一个条目。

    windows: list of (start, end, uri)
    返回 URI 或 None。
    """
    tol = pd.Timedelta(minutes=tol_min)
    t_s = pd.Timestamp(t_start)
    t_e = pd.Timestamp(t_end)
    if t_s.tzinfo is None:
        t_s = t_s.tz_localize("UTC")
    if t_e.tzinfo is None:
        t_e = t_e.tz_localize("UTC")
    ext_s = t_s - tol
    ext_e = t_e + tol
    for entry in windows:
        try:
            ws, we, uri = entry[0], entry[1], entry[2]
            ws = pd.Timestamp(ws)
            we = pd.Timestamp(we)
            if ws.tzinfo is None:
                ws = ws.tz_localize("UTC")
            if we.tzinfo is None:
                we = we.tz_localize("UTC")
            if ws <= ext_e and we >= ext_s:
                return uri
        except Exception:
            continue
    return None


# =============================================================================
# 遥测数据辅助函数
# =============================================================================


def _to_utc_series(df: pd.DataFrame) -> pd.Series:
    """将 TIME_COL 列转为 UTC tz-aware datetime Series。"""
    return pd.to_datetime(df[TIME_COL], errors="coerce", utc=True)


def _seg_mask(df: pd.DataFrame, t_start, t_end) -> pd.Series:
    """返回落在 [t_start, t_end] 窗口内的行掩码。"""
    ts = _to_utc_series(df)
    t_s = pd.Timestamp(t_start)
    t_e = pd.Timestamp(t_end)
    if t_s.tzinfo is None:
        t_s = t_s.tz_localize("UTC")
    if t_e.tzinfo is None:
        t_e = t_e.tz_localize("UTC")
    return (ts >= t_s) & (ts <= t_e)


def _get_vehicle_mass(
    df: pd.DataFrame,
    t_start,
    t_end,
    speed_col: str = _SPEED_COL,
    speed_threshold_kmh: float = MOVING_SPEED_THRESHOLD_KMH,
    method: str = "mean",
) -> tuple[float, float]:
    """返回 (mass_kg, cv) 或 (nan, nan)。

    v2.2.4: 优先只用**行驶中** (speed > ``speed_threshold_kmh``) 的质量样本计算
    leg 均值/CV —— 静止时的 J1939 GCVW 广播（装卸货瞬态 / 默认值）不可靠。
    当窗口内有 ≥2 个行驶样本时用行驶样本；否则回退到旧行为（窗口内全部 > 0 样本）。
    若速度列缺失，行为与旧版完全一致。

    v2.2.6: 过滤口径不变，但末段聚合改由 ``_agg_mass`` 按 ``method`` 完成
    （``mean`` / ``median`` / ``iqr_median`` / ``mad_mean`` / ``mad_tw_mean`` …），
    供异常重量尖峰的稳健估计。默认 ``mean`` 与旧实现逐值一致（``sel.mean()`` /
    ``std/mean``）。``mad_tw_mean`` 额外需要与 ``sel`` 对齐的时间轴，故仅在该方法
    下从 ``TIME_COL`` 构造时间戳传入；其余方法路径逐值不变。
    """
    if _WEIGHT_COL not in df.columns:
        return nan, nan
    mask = _seg_mask(df, t_start, t_end)
    vals = pd.to_numeric(df.loc[mask, _WEIGHT_COL], errors="coerce")
    # 过滤 J1939 default 0 值（静止时 broadcast 默认值，非真实读数）
    # 参考 diesel_pipeline.py line ~549 对 CVW 同样使用 m > 0 过滤
    valid = vals.notna() & (vals > 0)

    # 优先行驶中样本（speed > 阈值，NaN speed 视为非行驶）
    if speed_col in df.columns:
        spd = pd.to_numeric(df.loc[mask, speed_col], errors="coerce")
        moving = valid & spd.notna() & (spd > speed_threshold_kmh)
        if moving.sum() >= 2:
            valid = moving

    sel = vals[valid]
    # ``mad_tw_mean`` needs a per-sample time axis aligned to ``sel``; build it
    # only for that method so every other method's path is byte-identical.
    timestamps = None
    if (method or "").lower() == "mad_tw_mean":
        timestamps = _to_utc_series(df).loc[sel.index]
    return _agg_mass(sel, method, timestamps=timestamps)


def _get_recuperation(df: pd.DataFrame, t_start, t_end) -> float:
    """返回区间内电制动回收能量（kWh）。累计计数器，取 max - min。"""
    if _RECUP_COL not in df.columns:
        return nan
    mask = _seg_mask(df, t_start, t_end)
    vals = pd.to_numeric(df.loc[mask, _RECUP_COL], errors="coerce").dropna()
    if len(vals) < 2:
        return nan
    return round(float(vals.max() - vals.min()) / 1000.0, 3)


def _propulsion_at(
    t_target: pd.Timestamp, times: np.ndarray, values: np.ndarray
) -> float:
    """在 `electric_energy_propulsion` 累计计数器序列上对 t_target 做线性插值。

    times: 1D ns 时间戳数组（已排序）
    values: 同长度的累计 propulsion 值 (Wh)
    返回 t_target 处的插值 propulsion (Wh)；t_target 落在样本范围之外时取最近端点。
    """
    t_ns = np.int64(pd.Timestamp(t_target).value)
    if t_ns <= times[0]:
        return float(values[0])
    if t_ns >= times[-1]:
        return float(values[-1])
    # np.interp 对单调递增 x 做线性插值
    return float(np.interp(t_ns, times, values))


def _get_propulsion_energy(df: pd.DataFrame, t_start, t_end) -> float:
    """计算一个 trip 时间窗 [t_start, t_end] 内的 propulsion 增量 (kWh)。

    数据源：raw telematics 的 `electric_energy_propulsion` 列（Wh，累计计数器，
    单调递增）。RFMS 快照稀疏（~15 分钟一条），所以一个 trip 内可能只有 2–20 个
    采样点，需要在窗口边界做线性插值。

    算法：
    1. 提取整 leg 的 (timestamp, propulsion) 序列，去重 + 排序。
    2. 优先：[t_start, t_end] 严格包含在样本范围内 → 在两端各做一次插值 → Δ
    3. fallback：t_start 在范围内但 t_end 在范围外（或反之）→ 取窗口内首/末
       样本的差，即 partial-coverage 估计。
    4. 都不可用（窗口在样本范围外或样本 < 2）→ NaN。

    返回 Δ propulsion (kWh)；列缺失或样本不足时返回 NaN。
    """
    if _PROPULSION_COL not in df.columns:
        return nan
    # 准备样本序列
    ts = _to_utc_series(df)
    vals = pd.to_numeric(df[_PROPULSION_COL], errors="coerce")
    keep = (~ts.isna()) & (~vals.isna())
    if keep.sum() < 1:
        return nan
    sub = pd.DataFrame({"t": ts[keep], "v": vals[keep]}).drop_duplicates("t")
    sub = sub.sort_values("t")
    if len(sub) < 1:
        return nan
    # Pandas 2.x 的 pd.to_datetime 会根据输入精度推断 dtype 单位（如 'datetime64[us, UTC]'），
    # 此时 .asi8 / .astype('int64') 返回 microseconds 而不是 nanoseconds，与
    # pd.Timestamp.value（恒为 ns）单位不匹配会导致比较全错。强制 .as_unit('ns')。
    times = pd.DatetimeIndex(sub["t"]).as_unit("ns").asi8
    values = sub["v"].values

    # 规范化窗口边界为 UTC tz-aware
    t_s = pd.Timestamp(t_start)
    t_e = pd.Timestamp(t_end)
    if t_s.tzinfo is None:
        t_s = t_s.tz_localize("UTC")
    if t_e.tzinfo is None:
        t_e = t_e.tz_localize("UTC")
    t_s_ns = np.int64(t_s.value)
    t_e_ns = np.int64(t_e.value)

    s_min, s_max = times[0], times[-1]

    # ── 优先：bracketed 插值（窗口完全在样本范围内）────────────
    if t_s_ns >= s_min and t_e_ns <= s_max:
        v_s = _propulsion_at(t_s, times, values)
        v_e = _propulsion_at(t_e, times, values)
        delta_wh = v_e - v_s
        if delta_wh < 0:  # 累计计数器理论上单调递增，负值视为噪声
            return nan
        return round(delta_wh / 1000.0, 3)

    # ── fallback：窗口内首/末样本的差（partial coverage）────────
    in_window = (times >= t_s_ns) & (times <= t_e_ns)
    if in_window.sum() >= 2:
        idx = np.where(in_window)[0]
        delta_wh = float(values[idx[-1]] - values[idx[0]])
        if delta_wh < 0:
            return nan
        return round(delta_wh / 1000.0, 3)

    # ── 完全没有可用样本 ─────────────────────────────────────
    return nan


def _ep_exclude_aux(
    propulsion_kwh: float, recuperation_kwh: float, distance_km: float
) -> float:
    """净牵引（去辅助负载）能耗效率 (kWh/km)。

    定义见 ``data_analysis_workspace/energy_balance_check/report.md``：

        EP_exclude_aux = (propulsion − recuperation) / distance

    即每公里的牵引能量扣除再生回收后、再剔除 HVAC/驻车等辅助负载的净值。
    propulsion / recuperation 任一为 NaN（计数器缺失或全空），或 distance ≤ 0
    时返回 NaN —— 因此只有同时报告 propulsion + recuperation 两个计数器的车
    才会得到有效值，与 report.md 的可算车队一致。
    """
    if any(
        v is None or np.isnan(v)
        for v in (propulsion_kwh, recuperation_kwh, distance_km)
    ):
        return nan
    if distance_km <= 0:
        return nan
    return round((propulsion_kwh - recuperation_kwh) / distance_km, 4)


def _get_elevation_diff(
    df: pd.DataFrame, t_start, t_end, altitude_col: str | None = None
) -> float:
    """返回区间内的海拔差（米）：末尾高度 - 起始高度。"""
    if altitude_col is None or altitude_col not in df.columns:
        return nan
    mask = _seg_mask(df, t_start, t_end)
    vals = pd.to_numeric(df.loc[mask, altitude_col], errors="coerce").dropna()
    if len(vals) < 2:
        return nan
    return round(float(vals.iloc[-1] - vals.iloc[0]), 1)


_G = 9.81  # m/s²


def _corrected_energy_perf(
    energy_kwh: float, distance_km: float, elevation_m: float, mass_kg: float
) -> float:
    """
    海拔修正后的能量效率 (kWh/km)。

    公式：E_gravity = m * g * Δh / 3,600,000 (kWh)
    上坡 (Δh > 0) 时扣除重力做功，下坡 (Δh < 0) 时加上回收。
    corrected = (|delta_energy| - E_gravity) / distance
    """
    if any(np.isnan(v) for v in (energy_kwh, distance_km, elevation_m, mass_kg)):
        return nan
    if distance_km <= 0:
        return nan
    e_gravity_kwh = mass_kg * _G * elevation_m / 3_600_000.0
    corrected = abs(energy_kwh) - e_gravity_kwh
    return round(corrected / distance_km, 4)


ETA_DT = 0.90  # 传动效率 η（电池→车轮，含电机 0.95 × 变速器 0.95）
ETA_REGEN = 0.90  # 再生制动效率 η（车轮→电池，与 η_dt 对称）
_V_MAX_KMH = 100.0  # GPS 速度上限截断（km/h），UK 重卡限速 56 mph ≈ 90 km/h


def _kinetics_corrected_energy_perf(
    energy_kwh: float,
    distance_km: float,
    elevation_m: float,
    mass_kg: float,
    speed_array_kmh,
) -> float:
    """
    海拔 + 动能修正后的能量效率 (kWh/km)。

    基于 Sherborne (2024) Vehicle Model C（PhD thesis, Section 2.2.4, Eq. 2.6–2.10）：
    使用 Logger 1Hz 速度数据逐秒计算再生调整动能变化 ke，
    再转换为电池级能量消耗以校正行驶工况差异。

    逐秒动能变化：
      Δ_i = ½(v²_{i+1} - v²_i)            [J/kg]
    再生调整权重：
      W_i = 1     if Δ_i > 0（加速）
      W_i = η²    if Δ_i ≤ 0（减速，η² 为往返效率）
    电池级净动能消耗：
      E_KE_bat = (1/η) × m × Σ(Δ_i × W_i)
              = Σ(ΔKE>0)/η_dt - η_regen × Σ(|ΔKE<0|)

    η² 的物理含义：减速时动能经电机→逆变器→电池存储（效率 η），
    下一次加速时再经电池→逆变器→电机转回动能（效率 η），
    往返效率 = η × η = η²。

    Args:
        speed_array_kmh: numpy array，Logger 1Hz 速度值 (km/h)
    """
    if any(np.isnan(v) for v in (energy_kwh, distance_km, mass_kg)):
        return nan
    if distance_km <= 0:
        return nan
    if speed_array_kmh is None or len(speed_array_kmh) < 2:
        return nan
    # 海拔修正
    e_gravity_kwh = 0.0
    if not np.isnan(elevation_m):
        e_gravity_kwh = mass_kg * _G * elevation_m / 3_600_000.0
    # GPS 速度预处理：截断异常值 + 3 点中位数滤波抑制尖刺
    v_kmh = np.asarray(speed_array_kmh, dtype=float)
    v_kmh = np.clip(v_kmh, 0.0, _V_MAX_KMH)
    if len(v_kmh) >= 3:
        v_kmh = pd.Series(v_kmh).rolling(3, center=True, min_periods=1).median().values
    # 逐秒动能变化（Sherborne Eq. 2.6–2.9）
    v_ms = v_kmh / 3.6  # km/h → m/s
    delta_ke_j = 0.5 * mass_kg * np.diff(v_ms**2)  # Joules
    accel_energy_j = delta_ke_j[delta_ke_j > 0].sum()
    braking_energy_j = np.abs(delta_ke_j[delta_ke_j < 0]).sum()
    # 电池级净动能消耗 = 加速耗能/η_dt - η_regen × 制动回收
    net_ke_kwh = (accel_energy_j / ETA_DT - ETA_REGEN * braking_energy_j) / 3_600_000.0
    # 安全检查：校正量不应超过实际电池能量的 80%
    if abs(net_ke_kwh) > 0.8 * abs(energy_kwh):
        return nan
    corrected = abs(energy_kwh) - e_gravity_kwh - net_ke_kwh
    return round(corrected / distance_km, 4)


def _get_trip_speed_array(logger_speed_df, t_start, t_end):
    """提取 Logger 1Hz 速度数组（用于动能修正计算）。

    Args:
        logger_speed_df: pd.DataFrame，索引为 UTC 时间戳，列 'logger_speed' (km/h)
        t_start, t_end: 行程时间窗口边界

    Returns:
        numpy array (km/h) 或 None（数据不足时）
    """
    if logger_speed_df is None or logger_speed_df.empty:
        return None
    try:
        sliced = logger_speed_df.loc[t_start:t_end, "logger_speed"].dropna()
    except Exception:
        return None
    if len(sliced) < 2:
        return None
    return sliced.values  # numpy array，单位 km/h


def _point_str(lat, lon) -> str | None:
    """格式化为 'Point(lat lon)'（与老版 JOLT 一致）。"""
    if lat is None or lon is None:
        return None
    try:
        return f"Point({float(lat):.6f} {float(lon):.6f})"
    except Exception:
        return None


# =============================================================================
# Postcode reverse geocoding
# =============================================================================

# Anchored on the cache root (``JOLT_CACHE_DIR`` or ``./cache``) instead of the
# module file: identical to ``<repo>/cache/postcode_cache.json`` when run from the
# repository root, but now honours the cache-dir override for a platform deploy.
_POSTCODE_CACHE_PATH = get_cache_dir() / "postcode_cache.json"


def _load_postcode_cache() -> dict:
    """从磁盘加载 postcode 缓存。"""
    if _POSTCODE_CACHE_PATH.exists():
        try:
            with open(_POSTCODE_CACHE_PATH, "r") as f:
                raw = json.load(f)
            # JSON 键为字符串如 "(52.0368, -0.6572)"，转回 tuple
            return {
                tuple(map(float, k.strip("()").split(", "))): v for k, v in raw.items()
            }
        except Exception:
            return {}
    return {}


def _save_postcode_cache():
    """保存 postcode 缓存到磁盘。"""
    try:
        _POSTCODE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        serializable = {str(k): v for k, v in _postcode_cache.items()}
        with open(_POSTCODE_CACHE_PATH, "w") as f:
            json.dump(serializable, f, indent=2)
    except Exception:
        pass


_postcode_cache: dict = _load_postcode_cache()


def _get_postcode(lat, lon, srf_data=None) -> str | None:
    """Reverse geocode (lat, lon) → UK postcode via SRF location API. Results cached."""
    if lat is None or lon is None:
        return None
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if lat_f == 0.0 and lon_f == 0.0:
        return None
    key = (round(lat_f, 4), round(lon_f, 4))
    if key in _postcode_cache:
        return _postcode_cache[key]
    if srf_data is None:
        return None
    postcode = None
    try:
        pt = GeoPoint(lat_f, lon_f)
        places = srf_data.locations.find_all(
            point=srf_filter.near(pt, Distance(meters=500))
        )
        if places.total == 1:
            postcode = getattr(places.items[0], "post_code", None)
        elif places.total > 1:
            dis = [(p, geodesic(pt, p.point)) for p in paging.paged_items(places)]
            closest, _ = min(dis, key=lambda pair: pair[1])
            postcode = getattr(closest, "post_code", None)
    except Exception:
        pass
    _postcode_cache[key] = postcode
    _save_postcode_cache()
    return postcode


# =============================================================================
# Home detection & leg-type classification
# =============================================================================

HOME_DETECTION_KM = 0.5
ROUND_TRIP_MIN_KM = (
    5.0  # trips starting AND ending at depot but longer than this → "Round Trip"
)


def _is_home(lat, lon, home_point) -> bool:
    """Return True if (lat, lon) is within HOME_DETECTION_KM of home_point."""
    if lat is None or lon is None or home_point is None:
        return False
    try:
        return (
            geodesic(home_point, GeoPoint(float(lat), float(lon))).km
            < HOME_DETECTION_KM
        )
    except Exception:
        return False


def _get_leg_type(mode: str, seg: dict, energy_ac, energy_dc, home_point) -> str:
    """
    Classify a segment into one of the old-JOLT leg types:
      Charge: "AC Home" / "DC Home" / "AC/DC Home" / "Charge Home"
              "AC Away" / "DC Away" / "AC/DC Away" / "Charge Away"
      Trip:   "In House" / "Round Trip" / "Outbound" / "Return" / "In Transit"
              (Round Trip = circular delivery starting AND ending at depot, dist > ROUND_TRIP_MIN_KM)
    """
    if mode == "charge":
        lat = seg.get("latitude")
        lon = seg.get("longitude")
        # 充电段：只要坐标接近 home 即判定为 Home
        place = "Home" if _is_home(lat, lon, home_point) else "Away"
        ac_ok = (
            abs(float(energy_ac)) > 1
            if (energy_ac is not None and not np.isnan(float(energy_ac)))
            else False
        )
        dc_ok = (
            abs(float(energy_dc)) > 1
            if (energy_dc is not None and not np.isnan(float(energy_dc)))
            else False
        )
        if ac_ok and dc_ok:
            return f"AC/DC {place}"
        elif ac_ok:
            return f"AC {place}"
        elif dc_ok:
            return f"DC {place}"
        else:
            return f"Charge {place}"
    else:  # discharge / trip
        is_home_s = _is_home(seg.get("lat_start"), seg.get("lon_start"), home_point)
        is_home_e = _is_home(seg.get("lat_end"), seg.get("lon_end"), home_point)
        if is_home_s and is_home_e:
            # Distinguish depot-to-depot circular delivery from a short local move
            try:
                odo_s = seg.get("odo_start_km")
                odo_e = seg.get("odo_end_km")
                if odo_s is not None and odo_e is not None:
                    dist = float(odo_e) - float(odo_s)
                    if dist > ROUND_TRIP_MIN_KM:
                        return "Round Trip"
            except (TypeError, ValueError):
                pass
            return "In House"
        elif is_home_s:
            return "Outbound"
        elif is_home_e:
            return "Return"
        else:
            return "In Transit"


# =============================================================================
# Stop leg type — gap-fill between consecutive trip/charging rows
# =============================================================================

# Minimum gap (seconds) between two segments that qualifies as a Stop.
# Anything shorter is assumed to be a segment-algorithm boundary artefact.
STOP_MIN_GAP_SECONDS = 60.0


def _stop_row_from_neighbours(
    prev_row: list, next_row: list, headers: tuple = HEADERS
) -> list:
    """Build a Stop row from the two surrounding (trip/charge) rows.

    The stop spans the gap between ``prev_row``'s End Time and ``next_row``'s
    Start Time. We pull the vehicle's location from the end of ``prev_row``
    (= start of ``next_row``, modulo noise), the mass from ``prev_row``'s
    end value, and the SOC endpoints from both neighbours to expose any
    auxiliary/standby drain during the stop.

    ``headers`` chooses the row layout: pass ``DIESEL_HEADERS`` for diesel rows;
    diesel Stop rows skip SOC bookkeeping since diesel rows have no SOC columns.
    """
    row = [nan] * (len(headers) - 1)

    def _i(h):
        return _row_col_index(h, headers)

    def _has(h):
        return h in headers

    def _get(r, h):
        if not _has(h):
            return nan
        try:
            return r[_i(h)]
        except (IndexError, KeyError):
            return nan

    # ── Core identity ────────────────────────────────────────────────────
    row[_i("Leg Type")] = "Stop"
    for link_col in ("Telematics Link", "Charger Link", "SRF Logger Link"):
        if _has(link_col):
            row[_i(link_col)] = None

    # ── Time window ──────────────────────────────────────────────────────
    t_start = _get(prev_row, "End Time (UTC)")
    t_end = _get(next_row, "Start Time (UTC)")
    row[_i("Start Time (UTC)")] = t_start
    row[_i("End Time (UTC)")] = t_end

    try:
        ts_start = pd.Timestamp(t_start)
        ts_end = pd.Timestamp(t_end)
        if ts_start.tzinfo is None:
            ts_start = ts_start.tz_localize("UTC")
        if ts_end.tzinfo is None:
            ts_end = ts_end.tz_localize("UTC")
        duration_days = max((ts_end - ts_start).total_seconds(), 0) / 86400.0
    except Exception:
        duration_days = nan
    row[_i("Duration (HH:MM:SS)")] = duration_days

    # ── Location ─────────────────────────────────────────────────────────
    # At a Stop, origin and destination are the same vehicle location —
    # take the previous row's destination as the canonical stop location.
    stop_location = _get(prev_row, "Destination (Lat, Lon)")
    stop_place = _get(prev_row, "Destination Place")
    # Fallback to next row's origin if previous destination is missing
    if not stop_location or (
        isinstance(stop_location, float) and np.isnan(stop_location)
    ):
        stop_location = _get(next_row, "Origin (Lat, Lon)")
        stop_place = _get(next_row, "Origin Place")
    row[_i("Origin (Lat, Lon)")] = stop_location
    row[_i("Origin Place")] = stop_place
    row[_i("Destination (Lat, Lon)")] = stop_location
    row[_i("Destination Place")] = stop_place

    # ── Motion fields ────────────────────────────────────────────────────
    # The vehicle doesn't move during a Stop
    row[_i("Distance (km)")] = 0.0
    row[_i("Average Speed (km/h)")] = 0.0
    if _has("Elevation Difference (m)"):
        row[_i("Elevation Difference (m)")] = 0.0

    # ── Mass (carry over from previous leg's value) ──────────────────────
    row[_i("Vehicle Mass (kg)")] = _get(prev_row, "Vehicle Mass (kg)")
    if _has("Vehicle Mass CV (reliability)"):
        row[_i("Vehicle Mass CV (reliability)")] = _get(
            prev_row, "Vehicle Mass CV (reliability)"
        )

    # ── Cumulative Distance (carry over so the xlsx shows running total) ─
    if _has("Cumulative Distance (km)"):
        row[_i("Cumulative Distance (km)")] = _get(prev_row, "Cumulative Distance (km)")

    # ── SOC endpoints — expose any auxiliary drain during the stop ───────
    # Diesel rows have no SOC columns, so this block is a no-op there.
    if _has("Start SOC (%)") and _has("End SOC (%)"):
        row[_i("Start SOC (%)")] = _get(prev_row, "End SOC (%)")
        row[_i("End SOC (%)")] = _get(next_row, "Start SOC (%)")
        if _has("SOC Change (%)"):
            try:
                start_soc = float(row[_i("Start SOC (%)")])
                end_soc = float(row[_i("End SOC (%)")])
                row[_i("SOC Change (%)")] = end_soc - start_soc
            except (TypeError, ValueError):
                pass  # leave as nan

    # ── Operator — carry from the neighbouring leg (same vehicle, same stop) ──
    if _has("Operator"):
        op = _get(prev_row, "Operator")
        if op is None or (isinstance(op, float) and np.isnan(op)):
            op = _get(next_row, "Operator")
        row[_i("Operator")] = op

    return row


def _insert_stop_rows(
    sorted_rows: list,
    min_gap_seconds: float = STOP_MIN_GAP_SECONDS,
    headers: tuple = HEADERS,
) -> list:
    """Walk sorted rows and insert Stop rows in every non-trivial gap.

    A Stop is added whenever ``next.start_time - prev.end_time > min_gap_seconds``.
    The input list is not mutated; a new list is returned.
    """
    if not sorted_rows:
        return sorted_rows

    result: list = []
    end_col = _row_col_index("End Time (UTC)", headers)
    start_col = _row_col_index("Start Time (UTC)", headers)

    for i, row in enumerate(sorted_rows):
        result.append(row)
        if i == len(sorted_rows) - 1:
            break
        prev_end = row[end_col]
        next_start = sorted_rows[i + 1][start_col]
        try:
            ts_prev = pd.Timestamp(prev_end)
            ts_next = pd.Timestamp(next_start)
            if ts_prev.tzinfo is None:
                ts_prev = ts_prev.tz_localize("UTC")
            if ts_next.tzinfo is None:
                ts_next = ts_next.tz_localize("UTC")
            gap_s = (ts_next - ts_prev).total_seconds()
        except Exception:
            continue
        if gap_s > min_gap_seconds:
            result.append(
                _stop_row_from_neighbours(row, sorted_rows[i + 1], headers=headers)
            )
    return result


# =============================================================================
# Segment → Excel 行构建
# =============================================================================


def _seg_to_row(
    seg: dict,
    mode: str,
    leg_uri: str,
    charger_windows: list,
    logger_windows: list,
    df_leg: pd.DataFrame,
    cumulative_km: float,
    home_point=None,
    srf_data=None,
    altitude_col: str | None = None,
    speed_col: str = "wheel_based_speed",
    has_logger: bool = False,
    logger_speed_all: pd.DataFrame | None = None,
    logger_acc_pedal_all: pd.DataFrame | None = None,
    logger_dec_pedal_all: pd.DataFrame | None = None,
    operator: str | None = None,
    mass_agg: str = "mean",
) -> tuple:
    """
    将一个 segment dict 转换为一行 Excel 数据（HEADERS 顺序）。

    mode: 'charge' | 'discharge'
    logger_speed_all:      Logger 1Hz 速度 DataFrame（索引为 UTC 时间戳，列 'logger_speed'），
                           用于逐秒动能修正计算。
    logger_acc_pedal_all:  Logger EEC2 油门踏板位置 DataFrame（索引为 UTC 时间戳）。
    logger_dec_pedal_all:  Logger EBC1 制动踏板位置 DataFrame（索引为 UTC 时间戳）。
    """
    t_s = pd.Timestamp(seg["start_time"])
    t_e = pd.Timestamp(seg["end_time"])
    # 统一时区：确保两者都是 UTC 或都是 tz-naive
    if t_s.tzinfo is not None and t_e.tzinfo is None:
        t_e = t_e.tz_localize("UTC")
    elif t_s.tzinfo is None and t_e.tzinfo is not None:
        t_s = t_s.tz_localize("UTC")
    duration = t_e - t_s

    # ── URLs ───────────────────────────────────────────────────────────────
    telem_url = _build_telematics_url(leg_uri, t_s, t_e)
    # Logger Link 仅用于放电/行程段；充电段不应有 Logger 链接
    logger_url = None
    if mode == "discharge":
        logger_uri = _find_overlap(logger_windows, t_s, t_e, tol_min=5)
        logger_url = _build_logger_url(logger_uri, t_s, t_e) if logger_uri else None
    charger_url = None
    charger_energy_kwh = nan
    if mode == "charge":
        charger_uri = _find_overlap(charger_windows, t_s, t_e, tol_min=4)
        charger_url = _build_charger_url(charger_uri, t_s, t_e) if charger_uri else None
        # 提取匹配的充电桩能量数据
        if charger_uri:
            for entry in charger_windows:
                if len(entry) >= 4 and entry[2] == charger_uri and entry[3] is not None:
                    charger_energy_kwh = round(entry[3], 3)
                    break

    # ── Leg type ─────────────────────────────────────────────────────────
    energy_ac_delta = (
        (float(seg.get("ac_end_wh", 0) or 0) - float(seg.get("ac_start_wh", 0) or 0))
        / 1000.0
        if (seg.get("ac_end_wh") is not None and seg.get("ac_start_wh") is not None)
        else float("nan")
    )
    energy_dc_delta = (
        (float(seg.get("dc_end_wh", 0) or 0) - float(seg.get("dc_start_wh", 0) or 0))
        / 1000.0
        if (seg.get("dc_end_wh") is not None and seg.get("dc_start_wh") is not None)
        else float("nan")
    )
    leg_type = _get_leg_type(mode, seg, energy_ac_delta, energy_dc_delta, home_point)

    # ── Location ──────────────────────────────────────────────────────────
    if mode == "charge":
        lat = seg.get("latitude")
        lon = seg.get("longitude")
        origin = _point_str(lat, lon)
        destination = origin
        origin_pc = _get_postcode(lat, lon, srf_data)
        dest_pc = origin_pc
    else:
        origin = _point_str(seg.get("lat_start"), seg.get("lon_start"))
        destination = _point_str(seg.get("lat_end"), seg.get("lon_end"))
        origin_pc = _get_postcode(seg.get("lat_start"), seg.get("lon_start"), srf_data)
        dest_pc = _get_postcode(seg.get("lat_end"), seg.get("lon_end"), srf_data)

    # ── Distance & speed ─────────────────────────────────────────────────
    odo_s = seg.get("odo_start_km")
    odo_e = seg.get("odo_end_km")
    distance = nan
    if odo_s is not None and odo_e is not None:
        d = float(odo_e) - float(odo_s)
        if d > 0:
            distance = round(d, 3)

    dur_h = duration.total_seconds() / 3600.0
    # ── Average Speed ────────────────────────────────────────────────────
    # 默认（first_motion anchor）：distance / 端点差
    # zero_speed anchor 模式下，端点已被外扩到零速样本，trip 窗口含零速尾巴 →
    # 分母改用 trip 内 v > speed_threshold 子区间的累计时长，保持速度物理意义。
    # 由 find_discharge_segments_by_speed() 在 zero_speed 模式写入 seg['motion_duration_s']；
    # first_motion 模式 / charge 段 该字段为 None 或不存在。
    _motion_s = seg.get("motion_duration_s") if mode == "discharge" else None
    if _motion_s is not None and _motion_s > 0 and not np.isnan(distance):
        avg_speed = round(distance / (_motion_s / 3600.0), 2)
    else:
        avg_speed = (
            round(distance / dur_h, 2)
            if (not np.isnan(distance) and dur_h > 0)
            else nan
        )

    # ── Vehicle mass ──────────────────────────────────────────────────────
    veh_mass, veh_mass_cv = _get_vehicle_mass(df_leg, t_s, t_e, method=mass_agg)
    recuperation = _get_recuperation(df_leg, t_s, t_e)
    elevation_diff = _get_elevation_diff(df_leg, t_s, t_e, altitude_col)

    # ── Propulsion energy (kWh) — 仅 trip 段（v2.2.3）─────────────────────
    # 充电段 / 静止段 propulsion 必为 0，写 NaN 与现有 EP 列在 charge/stop
    # 行的处理一致；只对 discharge 计算插值差分。
    propulsion_kwh = nan
    if mode == "discharge":
        propulsion_kwh = _get_propulsion_energy(df_leg, t_s, t_e)

    # ── SOC / energy ──────────────────────────────────────────────────────
    start_soc = seg.get("start_soc", nan)
    end_soc = seg.get("end_soc", nan)
    soc_change = seg.get("delta_soc_pct", nan)  # signed
    energy_change = seg.get("delta_energy_kwh", nan)  # signed
    battery_cap = seg.get("effective_capacity_kwh", nan)
    energy_source = seg.get("energy_source", None)

    # ── Charge-specific ───────────────────────────────────────────────────
    energy_ac = nan
    energy_dc = nan
    battery_power = nan
    if mode == "charge":
        energy_ac = round(energy_ac_delta, 3) if not np.isnan(energy_ac_delta) else nan
        energy_dc = round(energy_dc_delta, 3) if not np.isnan(energy_dc_delta) else nan
        if not np.isnan(energy_change) and dur_h > 0:
            battery_power = round(energy_change / dur_h, 3)

    # ── Trip-specific ─────────────────────────────────────────────────────
    energy_perf = nan
    energy_perf_corrected = nan
    energy_perf_kinetics = nan
    ep_exclude_aux = nan
    if mode == "discharge" and not np.isnan(distance) and distance > 0:
        energy_perf = round(abs(energy_change) / distance, 4)
        energy_perf_corrected = _corrected_energy_perf(
            energy_change, distance, elevation_diff, veh_mass
        )
        # 去辅助负载净牵引效率：(propulsion − recuperation) / distance。
        # propulsion / recuperation 任一 NaN（计数器缺失）→ NaN。
        ep_exclude_aux = _ep_exclude_aux(propulsion_kwh, recuperation, distance)
        if logger_speed_all is not None:
            speed_arr = _get_trip_speed_array(logger_speed_all, t_s, t_e)
            if speed_arr is not None:
                energy_perf_kinetics = _kinetics_corrected_energy_perf(
                    energy_change, distance, elevation_diff, veh_mass, speed_arr
                )

    # ── 踏板位置直方图（仅放电段，距离 > 10 km）──────────────────────
    acc_hist = None
    dec_hist = None
    if (
        mode == "discharge"
        and not np.isnan(distance)
        and distance > MIN_DISTANCE_FOR_PEDAL_KM
    ):
        if logger_acc_pedal_all is not None:
            try:
                acc_slice = logger_acc_pedal_all.loc[t_s:t_e].dropna()
                if len(acc_slice) > 0:
                    acc_hist = compute_pedal_histogram(acc_slice, value_col=EEC2_COL)
            except Exception:
                pass
        if logger_dec_pedal_all is not None:
            try:
                dec_slice = logger_dec_pedal_all.loc[t_s:t_e].dropna()
                if len(dec_slice) > 0:
                    dec_hist = compute_pedal_histogram(dec_slice, value_col=EBC1_COL)
            except Exception:
                pass

    # ── Cumulative distance ───────────────────────────────────────────────
    if mode == "discharge" and not np.isnan(distance):
        cumulative_km += distance
    cumulative_km_out = cumulative_km if mode == "discharge" else nan

    # ── Duration as fractional days (Excel format) ────────────────────────
    dur_days = duration.total_seconds() / 86400.0

    # Build row in HEADERS order (excluding 'Leg Number' which is added by writer)
    row = (
        leg_type,  # Leg Type
        telem_url,  # Telematics Link
        charger_url,  # Charger Link
        logger_url,  # SRF Logger Link
        pd.Timestamp(t_s),  # Start Time (UTC)
        origin,  # Origin (Lat, Lon)
        origin_pc,  # Origin Place (postcode)
        pd.Timestamp(t_e),  # End Time (UTC)
        destination,  # Destination (Lat, Lon)
        dest_pc,  # Destination Place (postcode)
        dur_days,  # Duration (HH:MM:SS) — stored as fractional days
        distance,  # Distance (km)
        avg_speed,  # Average Speed (km/h)
        elevation_diff,  # Elevation Difference (m)
        veh_mass,  # Vehicle Mass (kg)
        veh_mass_cv,  # Vehicle Mass CV
        recuperation,  # Recuperation Energy (kWh)
        start_soc,  # Start SOC (%)
        end_soc,  # End SOC (%)
        soc_change,  # SOC Change (%) — signed
        energy_change,  # Energy Change (kWh) — signed
        energy_ac,  # Energy Charged AC (kWh)
        energy_dc,  # Energy Charged DC (kWh)
        nan,  # CO2 level (g/kWh)
        cumulative_km_out,  # Cumulative Distance (km)
        nan,  # CO2 for event (g)
        nan,  # Cumulative CO2 (g)
        battery_power,  # Battery Power (kW)
        energy_perf,  # Energy Performance (kWh/km)
        energy_perf_corrected,  # Energy Performance Corrected
        battery_cap,  # Battery Capacity (kWh)
        charger_energy_kwh,  # Energy Output from Charger (kWh)
        nan,  # Wire Energy Efficiency
        nan,  # Peak Charging (kW)
        nan,  # Average Charging (kW)
        nan,  # Energy based on motor power
        nan,  # Average Temperature
        nan,  # Average Pressure
        nan,  # Average Humidity
        nan,  # Average Wind Speed
        nan,  # Average Wind Direction
        nan,  # Weather Type
        acc_hist,  # Histogram Acc Pedal
        dec_hist,  # Histogram Dec Pedal
        energy_source,  # Energy Source
        energy_perf_kinetics,  # Energy Performance Kinetics Corrected (kWh/km)
        propulsion_kwh,  # Propulsion Energy (kWh)  [v2.2.3]
        ep_exclude_aux,  # EP_exclude_aux (kWh/km)  [v2.2.4]
        operator,  # Operator (project code)  [v2.2.5]
    )
    return row, cumulative_km
