"""
Speed-based trip / discharge segmentation.

Behaviour-preserving split of the former ``segment_algorithms.py`` (v3.0.0).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .constants import (
    MOVING_COL,
    ODO_COL,
    SOC_COL,
    TIME_COL,
    TOTAL_ENERGY_COL,
)

# =============================================================================
# 基于速度的放电行程分段
# =============================================================================
def _extend_trip_endpoint_to_zero(
    times_ns: np.ndarray,
    spd_arr: np.ndarray,
    idx0: int,
    direction: str,
    max_extend_ns: int,
) -> int:
    """
    将 trip 端点向外扩展到最近的 v == 0 样本（用于 zero_speed anchor 模式）。

    参数
    ----
    times_ns    : 全 leg 时间戳 (datetime64[ns] view as int64)
    spd_arr     : 全 leg 速度数组（NaN 已填 0；与 times_ns 同长）
    idx0        : 当前端点索引（first/last moving sample 在 df 中的位置）
    direction   : 'backward'（trip 起点向前扩）或 'forward'（trip 终点向后扩）
    max_extend_ns : 最大外扩窗口（纳秒）；超出则放弃外扩，回退到 idx0

    返回
    ----
    扩展后的端点索引；若窗口内未找到 v == 0 样本则返回 idx0（fallback 行为）。
    """
    n = len(times_ns)
    t0 = times_ns[idx0]
    if direction == 'backward':
        j = idx0
        while j > 0:
            j -= 1
            if (t0 - times_ns[j]) > max_extend_ns:
                return idx0  # 超出窗口，回退
            if spd_arr[j] == 0:
                return j
        return idx0  # 到 leg 起点仍未遇到 v==0
    else:  # 'forward'
        j = idx0
        while j < n - 1:
            j += 1
            if (times_ns[j] - t0) > max_extend_ns:
                return idx0  # 超出窗口，回退
            if spd_arr[j] == 0:
                return j
        return idx0  # 到 leg 终点仍未遇到 v==0


def find_speed_trips(
    df_raw: pd.DataFrame,
    speed_col: str = 'wheel_based_speed',
    speed_threshold_kmh: float = 1.0,
    min_stop_duration_min: float = 5.0,
    min_trip_duration_min: float = 2.0,
    trip_endpoint_anchor: str = 'zero_speed',
    max_extend_minutes: float = 5.0,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """
    基于车速检测行程起止时间。

    参数
    ----
    df_raw              : 原始遥测 DataFrame（需含 TIME_COL 和 speed_col 列）
    speed_col           : 速度列名（km/h）
    speed_threshold_kmh : 速度高于此值视为行驶中
    min_stop_duration_min : 连续零速超过此时长（分钟）才视为行程结束；
                            更短的零速间隔会被桥接（如红灯、短暂停车）
    min_trip_duration_min : 行程持续时间低于此值（分钟）则丢弃（噪声）
    trip_endpoint_anchor : trip 端点锚定策略：
        - 'zero_speed'（默认，v2.2.5 起）：split + merge + 过滤后，把端点外扩到
                                  最近的 v == 0 样本（不超过 max_extend_minutes 分钟）。
                                  目的：让 trip 窗口完整覆盖低频遥测心跳上的
                                  零速尾巴，避免起止时刻落在 76 km/h 等瞬态点。
                                  现为全车队标准。
        - 'first_motion'（opt-out / legacy）：端点 = trip 内首/末个
                                  v > speed_threshold_kmh 样本（v2.2.3 之前的唯一行为，
                                  保留作向后兼容 / per-pipeline override）。
    max_extend_minutes  : zero_speed 模式下端点外扩的最大窗口（分钟）；超出则
                          静默回退到 first_motion 端点。仅当 anchor==zero_speed 时生效。

    返回
    ----
    [(trip_start, trip_end), ...] — 按时间排序的行程时间窗口列表。
    若速度列不存在或全部无效，返回空列表。
    """
    if TIME_COL not in df_raw.columns:
        return []
    if speed_col not in df_raw.columns:
        return []

    df = df_raw[[TIME_COL, speed_col]].copy()
    df[TIME_COL] = pd.to_datetime(df[TIME_COL], errors='coerce', utc=True)
    df = df.dropna(subset=[TIME_COL]).sort_values(TIME_COL).reset_index(drop=True)
    if df.empty:
        return []

    # 速度：NaN → 0
    df['_spd'] = pd.to_numeric(df[speed_col], errors='coerce').fillna(0.0)

    # 若速度列全部为 0 则无行程
    if (df['_spd'] <= speed_threshold_kmh).all():
        return []

    # 标记行驶状态
    df['_moving'] = df['_spd'] > speed_threshold_kmh
    times = df[TIME_COL].values.astype('datetime64[ns]')
    moving = df['_moving'].values

    # 找到连续行驶块
    raw_trips: list[tuple[int, int]] = []  # (first_moving_idx, last_moving_idx)
    i = 0
    n = len(df)
    while i < n:
        if moving[i]:
            start = i
            while i < n and moving[i]:
                i += 1
            raw_trips.append((start, i - 1))
        else:
            i += 1

    if not raw_trips:
        return []

    # 桥接：若两个行驶块之间的零速间隔 < min_stop_duration_min，则合并
    min_stop_ns = int(min_stop_duration_min * 60 * 1_000_000_000)
    merged_trips: list[tuple[int, int]] = [raw_trips[0]]
    for trip_s, trip_e in raw_trips[1:]:
        prev_e = merged_trips[-1][1]
        gap_ns = int(times[trip_s] - times[prev_e])
        if gap_ns <= min_stop_ns:
            # 桥接：扩展前一行程到当前行程结束
            merged_trips[-1] = (merged_trips[-1][0], trip_e)
        else:
            merged_trips.append((trip_s, trip_e))

    # 过滤短行程
    min_trip_ns = int(min_trip_duration_min * 60 * 1_000_000_000)
    spd_arr = df['_spd'].values
    max_extend_ns = int(max_extend_minutes * 60 * 1_000_000_000)
    use_zero_anchor = (trip_endpoint_anchor == 'zero_speed')

    result: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for trip_s, trip_e in merged_trips:
        # 行程长度过滤基于原始 first_motion 端点（与 v2.2.2 行为一致）
        if int(times[trip_e] - times[trip_s]) < min_trip_ns:
            continue

        s_idx, e_idx = trip_s, trip_e
        if use_zero_anchor:
            # 端点向外扩到最近的 v==0 样本，超出 max_extend_ns 则回退
            times_ns_int = times.view('i8')
            s_idx = _extend_trip_endpoint_to_zero(
                times_ns_int, spd_arr, trip_s, 'backward', max_extend_ns,
            )
            e_idx = _extend_trip_endpoint_to_zero(
                times_ns_int, spd_arr, trip_e, 'forward', max_extend_ns,
            )

        result.append((pd.Timestamp(times[s_idx]), pd.Timestamp(times[e_idx])))

    return result


def find_discharge_segments_by_speed(
    df_raw: pd.DataFrame,
    speed_col: str = 'wheel_based_speed',
    speed_threshold_kmh: float = 1.0,
    min_stop_duration_min: float = 5.0,
    min_trip_duration_min: float = 2.0,
    min_soc_drop: float = 1.0,
    min_energy_kwh: float = 1.0,
    cap_lo: float | None = None,
    cap_hi: float | None = None,
    total_energy_col: str = TOTAL_ENERGY_COL,
    moving_energy_col: str = MOVING_COL,
    nominal_kwh: float | None = None,
    trips: list[tuple] | None = None,
    trip_endpoint_anchor: str = 'zero_speed',
    max_extend_minutes: float = 5.0,
) -> list[dict]:
    """
    基于车速的放电行程分段：用速度检测行程边界，SOC/能量用于计算指标。

    输出 schema 与 find_discharge_segments_by_soc() 完全一致（v2 统一 schema），
    保证下游 report_builder / merge_discharge_by_mass 等逻辑无需修改。

    与 SOC-based 放电分段的区别：
    - 行程边界由速度信号定义（更精确），而非 SOC 下降趋势
    - 使用更宽松的 min_soc_drop（默认 1.0 vs 5.0）和 min_energy_kwh（1.0 vs 2.0）
    - 能量源级联逻辑完全相同：total_energy → moving_energy → soc_estimate

    参数
    ----
    参见 find_speed_trips() 和 find_discharge_segments_by_soc() 的参数说明。

    返回
    ----
    list[dict] — 与 find_discharge_segments_by_soc() 相同的分段字典列表。
    若速度列缺失或全零（无行程），返回空列表（调用方可 fallback 到 SOC-based）。
    """
    # 1. 获取速度定义的行程时间窗口（可接受外部预计算的 trips）
    if trips is None:
        trips = find_speed_trips(
            df_raw,
            speed_col=speed_col,
            speed_threshold_kmh=speed_threshold_kmh,
            min_stop_duration_min=min_stop_duration_min,
            min_trip_duration_min=min_trip_duration_min,
            trip_endpoint_anchor=trip_endpoint_anchor,
            max_extend_minutes=max_extend_minutes,
        )
    if not trips:
        return []

    # 2. 准备数据列
    if SOC_COL not in df_raw.columns or TIME_COL not in df_raw.columns:
        return []

    df = df_raw.copy()
    df[TIME_COL] = pd.to_datetime(df[TIME_COL], errors='coerce', utc=True)
    df = df.dropna(subset=[TIME_COL]).sort_values(TIME_COL).reset_index(drop=True)
    if df.empty:
        return []

    df['_soc'] = pd.to_numeric(df[SOC_COL], errors='coerce')
    df.loc[df['_soc'] == 0, '_soc'] = np.nan

    has_total  = total_energy_col  in df.columns
    has_moving = moving_energy_col in df.columns

    if has_total:
        df['_tot'] = pd.to_numeric(df[total_energy_col], errors='coerce')
    if has_moving:
        df['_mov'] = pd.to_numeric(df[moving_energy_col], errors='coerce')

    if ODO_COL in df.columns:
        df['_odo'] = pd.to_numeric(df[ODO_COL], errors='coerce')
    else:
        df['_odo'] = np.nan

    for _c in ('latitude', 'longitude'):
        if _c in df.columns:
            df[_c] = pd.to_numeric(df[_c], errors='coerce')
            df.loc[df[_c] == 0, _c] = np.nan

    # 速度列（用于 zero_speed anchor 模式下计算 v>0 子区间累计时长）
    if speed_col in df.columns:
        df['_spd'] = pd.to_numeric(df[speed_col], errors='coerce').fillna(0.0)
    else:
        df['_spd'] = 0.0

    times_np = df[TIME_COL].values.astype('datetime64[ns]')

    # Total energy 基准（用于 anchor 相对值）
    tot_base_wh = 0.0
    if has_total:
        _tot_valid = df.loc[df['_tot'].notna(), '_tot']
        if len(_tot_valid):
            tot_base_wh = float(_tot_valid.iloc[0])

    mov_base_wh = 0.0
    if has_moving:
        _mov_valid = df.loc[df['_mov'].notna(), '_mov']
        if len(_mov_valid):
            mov_base_wh = float(_mov_valid.iloc[0])

    def _nearest_before(col_name: str, t_np):
        """在时间 t_np 之前（含）找到最近的有效值。"""
        mask = df[col_name].notna() & (times_np <= t_np)
        idx = df.index[mask]
        if len(idx) == 0:
            return np.nan, None
        i = idx[-1]
        return float(df.loc[i, col_name]), pd.Timestamp(times_np[i])

    def _nearest_after(col_name: str, t_np):
        """在时间 t_np 之后（含）找到最近的有效值。"""
        mask = df[col_name].notna() & (times_np >= t_np)
        idx = df.index[mask]
        if len(idx) == 0:
            return np.nan, None
        i = idx[0]
        return float(df.loc[i, col_name]), pd.Timestamp(times_np[i])

    # 3. 对每个行程计算分段指标
    segments: list[dict] = []
    for trip_start, trip_end in trips:
        t_s = trip_start.to_numpy().astype('datetime64[ns]')
        t_e = trip_end.to_numpy().astype('datetime64[ns]')

        # SOC：行程窗口内第一个和最后一个有效读数
        win_mask = (times_np >= t_s) & (times_np <= t_e)
        win_soc = df.loc[win_mask & df['_soc'].notna(), '_soc']
        if len(win_soc) < 1:
            # 窗口内无 SOC → 尝试窗口边界附近的 SOC
            soc_s, _ = _nearest_before('_soc', t_s)
            soc_e, _ = _nearest_after('_soc', t_e)
        else:
            soc_s = float(win_soc.iloc[0])
            soc_e = float(win_soc.iloc[-1])

        # SOC 变化量
        has_soc = not (np.isnan(soc_s) or np.isnan(soc_e))
        if has_soc:
            delta_soc_signed = soc_e - soc_s      # 负值 = 放电
            delta_soc_abs    = soc_s - soc_e       # 正值 = 下降幅度
        else:
            delta_soc_signed = 0.0
            delta_soc_abs    = 0.0

        # SOC 变化量过滤：剔除 SOC 下降不足的行程
        if has_soc and delta_soc_abs < min_soc_drop:
            continue

        # ── delta_energy_kwh：能量源级联 ──────────────────────────────
        # 速度分段中行程已由速度确认，优先用能量计数器（精度高于 SOC）。
        delta_energy_kwh = None
        energy_source    = None
        anchor_s_time = anchor_e_time = None
        anchor_s_rel = anchor_e_rel = float('nan')

        # 1. Total energy col（首选）
        if has_total:
            e_s, t_es = _nearest_before('_tot', t_s)
            e_e, t_ee = _nearest_after('_tot', t_e)
            if not np.isnan(e_s) and not np.isnan(e_e):
                _raw = (e_e - e_s) / 1000.0
                if _raw > 0:
                    delta_energy_kwh = -_raw
                    energy_source    = 'total_energy'
                    anchor_s_time    = t_es
                    anchor_e_time    = t_ee
                    anchor_s_rel     = round((e_s - tot_base_wh) / 1000.0, 4)
                    anchor_e_rel     = round((e_e - tot_base_wh) / 1000.0, 4)

        # 2. Moving energy col（备选）
        if delta_energy_kwh is None and has_moving:
            e_s, t_es = _nearest_before('_mov', t_s)
            e_e, t_ee = _nearest_after('_mov', t_e)
            if not np.isnan(e_s) and not np.isnan(e_e):
                _raw = (e_e - e_s) / 1000.0
                if _raw > 0:
                    delta_energy_kwh = -_raw
                    energy_source    = 'moving_energy'
                    anchor_s_time    = t_es
                    anchor_e_time    = t_ee
                    anchor_s_rel     = round((e_s - mov_base_wh) / 1000.0, 4)
                    anchor_e_rel     = round((e_e - mov_base_wh) / 1000.0, 4)

        # 3. SOC estimate（兜底）— 仅在 SOC 有实际下降时使用
        if delta_energy_kwh is None and nominal_kwh is not None and delta_soc_abs > 0:
            delta_energy_kwh = (delta_soc_signed / 100.0) * nominal_kwh
            energy_source    = 'soc_estimate'
            anchor_s_time    = trip_start
            anchor_e_time    = trip_end
            anchor_s_rel     = float('nan')
            anchor_e_rel     = float('nan')

        if delta_energy_kwh is None:
            continue
        if abs(delta_energy_kwh) < min_energy_kwh or delta_energy_kwh >= 0:
            continue

        # Effective capacity：仅在 SOC 有实际下降时可计算
        if delta_soc_abs > 0:
            eff_cap = abs(delta_energy_kwh) / (delta_soc_abs / 100.0)
            if cap_lo is not None and cap_hi is not None:
                if not (cap_lo <= eff_cap <= cap_hi):
                    continue
        else:
            eff_cap = None

        # delta_moving_kwh（独立于主能量源）
        delta_moving = None
        if has_moving:
            e_ms, _ = _nearest_before('_mov', t_s)
            e_me, _ = _nearest_after('_mov', t_e)
            if not np.isnan(e_ms) and not np.isnan(e_me):
                _dm = (e_me - e_ms) / 1000.0
                if _dm > 0:
                    delta_moving = round(_dm, 3)

        # 里程
        odo_s, _ = _nearest_before('_odo', t_s)
        odo_e, _ = _nearest_after('_odo', t_e)

        # GPS
        has_latlon = 'latitude' in df.columns and 'longitude' in df.columns
        if has_latlon:
            win = df.loc[win_mask]
            lat_v = win['latitude'].dropna()
            lon_v = win['longitude'].dropna()
            lat_s = round(float(lat_v.iloc[0]),  6) if len(lat_v) else None
            lon_s = round(float(lon_v.iloc[0]),  6) if len(lon_v) else None
            lat_e = round(float(lat_v.iloc[-1]), 6) if len(lat_v) else None
            lon_e = round(float(lon_v.iloc[-1]), 6) if len(lon_v) else None
        else:
            lat_s = lon_s = lat_e = lon_e = None

        # ── motion_duration_s（v>0 子区间累计时长，仅 zero_speed anchor 模式）
        # 仅当 trip_endpoint_anchor='zero_speed' 时写入；下游 _seg_to_row 用此值
        # 代替端点差作 avg_speed 分母，避免零速尾巴稀释速度。
        motion_duration_s = None
        if trip_endpoint_anchor == 'zero_speed':
            win_idx = np.where(win_mask)[0]
            if len(win_idx) >= 2:
                spd_win = df['_spd'].values[win_idx]
                tns_win = times_np[win_idx].view('i8')
                # 用前向差分：dt[i] = t[i+1] - t[i]，若 spd[i] > threshold 计入
                dt_ns = tns_win[1:] - tns_win[:-1]
                moving_mask = spd_win[:-1] > speed_threshold_kmh
                motion_duration_s = float(dt_ns[moving_mask].sum()) / 1e9

        segments.append({
            'start_time':             trip_start,
            'end_time':               trip_end,
            'start_soc':              round(soc_s,    2),
            'end_soc':                round(soc_e,    2),
            'delta_soc_pct':          round(delta_soc_signed, 2),
            'delta_energy_kwh':       round(delta_energy_kwh, 3),
            'energy_source':          energy_source,
            'delta_moving_kwh':       delta_moving,
            'effective_capacity_kwh': round(eff_cap, 1) if eff_cap is not None else None,
            'odo_start_km':           round(odo_s, 3) if np.isfinite(odo_s) else None,
            'odo_end_km':             round(odo_e, 3) if np.isfinite(odo_e) else None,
            'lat_start':              lat_s,
            'lon_start':              lon_s,
            'lat_end':                lat_e,
            'lon_end':                lon_e,
            'motion_duration_s':      motion_duration_s,
            '_anchor_start_time':     anchor_s_time,
            '_anchor_end_time':       anchor_e_time,
            '_anchor_start_rel_kwh':  anchor_s_rel,
            '_anchor_end_rel_kwh':    anchor_e_rel,
        })

    return segments
