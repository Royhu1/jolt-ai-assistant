"""
Mass-cluster based trip splitting / merging and energy-anchor recomputation.

Behaviour-preserving split of the former ``segment_algorithms.py`` (v3.0.0).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .constants import (
    MASS_COL,
    MIN_CLUSTER_GAP_KG,
    MOVING_SPEED_THRESHOLD_KMH,
    ODO_COL,
    SOC_COL,
    TIME_COL,
    TRACTOR_ONLY_MAX_KG,
)
from .timeutil import _to_utc

logger = logging.getLogger(__name__)

def cluster_mass_data(
    df_raw: pd.DataFrame,
    mass_col: str = MASS_COL,
    min_cluster_gap_kg: float = MIN_CLUSTER_GAP_KG,
    speed_col: str | None = None,
    speed_threshold_kmh: float = MOVING_SPEED_THRESHOLD_KMH,
    keep_tractor_only_label: bool = False,
) -> pd.DataFrame:
    """
    对遥测数据中的质量列进行 1D 聚类，为 df_raw 新增 ``mass_cluster`` 列。

    算法
    ----
    1. 提取质量列中所有有效（非 NaN、>0）读数。
    2. **聚类均值只用「行驶中」(speed > ``speed_threshold_kmh``) 的有效读数计算**
       （v2.2.4；静止时的 GCVW 广播不可靠）。按值排序，相邻排序值之差
       ≥ ``min_cluster_gap_kg`` 处切分为独立聚类。
    3. 计算每个聚类的均值；若相邻聚类均值差 < ``min_cluster_gap_kg``，合并。
    4. 按聚类均值从小到大重新编号：0 = 最低质量（通常为 tractor 自重）。
    5. 每条**有效**读数（行驶 + 静止）都分配到距其最近的聚类均值。

    Moving 标注与回退（v2.2.4）
    --------------------------
    - 新增布尔列 ``mass_moving``：``True`` 表示该行质量有效且采样时在行驶
      (speed > 阈值)。下游 :func:`_get_seg_dominant_cluster` 据此优先用行驶行投票。
    - 若提供了 ``speed_col`` 但全表无行驶质量读数（稀疏质量车辆），退回旧行为：
      在所有有效读数上聚类，并打 info 日志。
    - 若未提供 ``speed_col``（或列缺失），``mass_moving`` 置为「质量有效」本身，
      行为与旧版完全一致。

    NaN / 无效质量值的行不参与聚类，``mass_cluster`` 保持 NaN，``mass_moving`` 为 False。

    ``keep_tractor_only_label`` (opt-in; default ``False``)
    -------------------------------------------------------
    When ``True`` the returned copy carries an extra boolean column
    ``mass_tractor_only`` marking exactly the readings that step 4 判定为
    tractor-only (cluster 0 均值 < ``TRACTOR_ONLY_MAX_KG``) and therefore blanked
    from ``mass_cluster``. This lets a caller RECOVER those report-excluded
    ~tractor-weight readings (e.g. the dashboard drill-down, which still wants to
    DISPLAY bare-tractor / bobtail events, just marked distinctly) without any
    effect on the shared segmentation contract. The default (``False``) adds no
    column and leaves the output byte-identical to every existing caller.

    返回
    ----
    带有 ``mass_cluster``（int 或 NaN）与 ``mass_moving``（bool）两列的 df_raw
    **副本**（``keep_tractor_only_label=True`` 时额外带 ``mass_tractor_only`` 布尔列）。
    """
    df = df_raw.copy()
    df['mass_cluster'] = np.nan
    df['mass_moving'] = False
    if keep_tractor_only_label:
        # Opt-in marker column: default False everywhere; set True only on the
        # rows step 4 drops as tractor-only. Initialised here so every early-return
        # path (missing / all-invalid mass) still exposes the column.
        df['mass_tractor_only'] = False

    if mass_col not in df.columns:
        return df

    mass_numeric = pd.to_numeric(df[mass_col], errors='coerce')
    valid_mask = mass_numeric.notna() & (mass_numeric > 0)
    if valid_mask.sum() == 0:
        return df

    # ── 行驶掩码：speed > 阈值（NaN speed 视为非行驶）────────────────────────
    if speed_col is not None and speed_col in df.columns:
        spd_numeric = pd.to_numeric(df[speed_col], errors='coerce')
        moving_mask = valid_mask & spd_numeric.notna() & (spd_numeric > speed_threshold_kmh)
    else:
        # 无速度信息：把所有有效读数当作「可用于聚类」，等价旧行为
        moving_mask = valid_mask.copy()

    # 聚类均值的来源读数：优先只用行驶中的；若全表没有行驶读数则回退到全部有效
    if moving_mask.any():
        cluster_source_vals = mass_numeric[moving_mask].values.astype(float)
    else:
        cluster_source_vals = mass_numeric[valid_mask].values.astype(float)
        if speed_col is not None and speed_col in df.columns:
            logger.info('  质量聚类: 全表无行驶中质量读数，回退用全部有效读数聚类 '
                        '(%d 条)', int(valid_mask.sum()))

    # mass_moving 列：质量有效 + 行驶中（无速度信息时即「质量有效」）
    df['mass_moving'] = moving_mask

    valid_vals = mass_numeric[valid_mask].values.astype(float)

    # ── 1. 排序并按间隔切分（仅基于 cluster_source_vals）──────────────────────
    sorted_vals = np.sort(cluster_source_vals)
    diffs = np.diff(sorted_vals)
    break_indices = np.where(diffs >= min_cluster_gap_kg)[0]

    # 构建各聚类在 sorted 数组上的 [start, end) 切片
    slices: list[tuple[int, int]] = []
    start = 0
    for b in break_indices:
        slices.append((start, b + 1))
        start = b + 1
    slices.append((start, len(sorted_vals)))

    # 每个聚类的均值
    means = [float(np.mean(sorted_vals[s:e])) for s, e in slices]

    # ── 2. 合并均值差 < min_cluster_gap_kg 的相邻聚类 ────────────────────────
    merged_means: list[float] = [means[0]]
    merged_slices: list[tuple[int, int]] = [slices[0]]
    for i in range(1, len(means)):
        if means[i] - merged_means[-1] < min_cluster_gap_kg:
            old_s, _ = merged_slices[-1]
            _, new_e = slices[i]
            merged_slices[-1] = (old_s, new_e)
            merged_means[-1] = float(np.mean(sorted_vals[old_s:new_e]))
        else:
            merged_means.append(means[i])
            merged_slices.append(slices[i])

    # ── 3. 每条读数分配到最近聚类均值 → 标签从 0（最低）开始 ────────────────
    means_arr = np.array(merged_means)  # 已按升序排列
    distances = np.abs(valid_vals[:, np.newaxis] - means_arr[np.newaxis, :])
    labels = np.argmin(distances, axis=1).astype(float)

    df.loc[valid_mask, 'mass_cluster'] = labels

    # ── 4. Tractor-only 检测：cluster 0 均值 < 阈值时视为仅牵引车 ─────────
    #    这些行的 mass_cluster 置 NaN，使后续合并/拆分算法忽略它们
    if merged_means[0] < TRACTOR_ONLY_MAX_KG:
        tractor_mask = valid_mask & (df['mass_cluster'] == 0)
        if keep_tractor_only_label:
            # Record which readings we are about to blank, so an opted-in caller
            # can recover them (the dashboard displays them, marked tractor-only).
            df.loc[tractor_mask, 'mass_tractor_only'] = True
        df.loc[tractor_mask, 'mass_cluster'] = np.nan
        logger.info('  质量聚类: cluster 0 均值 %.0f kg < %.0f kg，'
                     '判定为 tractor-only，%d 条读数已忽略',
                     merged_means[0], TRACTOR_ONLY_MAX_KG, tractor_mask.sum())

    return df


def _get_seg_dominant_cluster(
    df_raw: pd.DataFrame,
    t_start: pd.Timestamp,
    t_end: pd.Timestamp,
) -> float | None:
    """返回时间窗口 [t_start, t_end] 内出现次数最多的 mass_cluster 标签。

    v2.2.4: **优先用行驶中** (``mass_moving == True``) 的质量行投票（静止时的
    GCVW 广播不可靠）。若窗口内没有任何行驶中的质量行，则回退用静止行投票
    （用户要求的「当无可用行驶数据时仍用静止质量数据」）。``mass_moving`` 列缺失
    时（旧数据 / 旧调用路径）退回原行为：所有有效行一起投票。
    """
    if 'mass_cluster' not in df_raw.columns:
        return None
    t_s = _to_utc(t_start)
    t_e = _to_utc(t_end)
    times = pd.to_datetime(df_raw[TIME_COL], errors='coerce', utc=True)
    base_mask = (times >= t_s) & (times <= t_e) & df_raw['mass_cluster'].notna()
    # 优先行驶中的质量行
    if 'mass_moving' in df_raw.columns:
        moving_mask = base_mask & df_raw['mass_moving'].astype(bool)
        moving_vals = df_raw.loc[moving_mask, 'mass_cluster']
        if not moving_vals.empty:
            return float(moving_vals.mode().iloc[0])
        # 窗口内无行驶质量行 → 回退用静止质量行
    vals = df_raw.loc[base_mask, 'mass_cluster']
    if vals.empty:
        return None
    return float(vals.mode().iloc[0])

# =============================================================================
# 基于质量聚类的行程拆分（装卸货检测）
# =============================================================================

def _split_point_has_zero_speed(
    df_raw: pd.DataFrame,
    t_split: pd.Timestamp,
    speed_col: str,
    window_seconds: float,
) -> bool:
    """
    检查切点 t_split 的中心对称邻域 [t-W/2, t+W/2] 内是否存在 v==0 样本。

    物理含义：基于质量聚类的 trip 切分本质上是“装卸货事件”检测。装卸货
    必然伴随停车，所以一个合格的切点附近（±W/2 时间窗）必须存在严格
    零速读数。否则视为 CVW 噪声尖刺（如行驶途中质量读数瞬时跳变），
    应当放弃切分以避免把一条连续的高速 trip 切成两段。

    参数
    ----
    df_raw         : 原始遥测 DataFrame，需含 TIME_COL 与 speed_col
    t_split        : 候选切点时间戳
    speed_col      : 速度列名（默认 'wheel_based_speed'，单位 km/h）
    window_seconds : 中心对称窗口总宽度 W（秒）；通常等于
                     min_stop_duration_min × 60
    """
    if speed_col not in df_raw.columns:
        # 无速度信息时退回保守行为：保留切点（沿用旧逻辑）
        return True

    t = _to_utc(t_split)
    half = pd.Timedelta(seconds=window_seconds / 2.0)
    t_lo, t_hi = t - half, t + half

    times = pd.to_datetime(df_raw[TIME_COL], errors='coerce', utc=True)
    mask = (times >= t_lo) & (times <= t_hi)
    if not mask.any():
        return False
    spd = pd.to_numeric(df_raw.loc[mask, speed_col], errors='coerce')
    # 严格 v == 0（与 trip_endpoint_anchor=zero_speed 一致的零速判定）
    return bool((spd == 0).any())


def _detect_cluster_transitions(
    df_raw: pd.DataFrame,
    t_start: pd.Timestamp,
    t_end: pd.Timestamp,
    speed_col: str | None = None,
    zero_speed_window_seconds: float | None = None,
) -> list[pd.Timestamp]:
    """
    在 [t_start, t_end] 时间窗口内检测 mass_cluster 标签变化点。

    当相邻**行驶中**质量读数的 mass_cluster 不同时，视为装卸货事件，
    在该时间点处拆分放电段。

    行驶读数限定（v2.2.5）
    --------------------
    切换点检测只扫描 ``mass_moving == True`` 的行：静止时的 J1939 GCVW 广播
    不可靠，若纳入会在停车点制造假切点（碎段被 ``min_soc_drop`` 丢弃 → trip
    丢失一段），或模糊真实的行驶质量变化。与 ``cluster_mass_data`` 的均值只用
    行驶读数（v2.2.4）、``_get_seg_dominant_cluster`` 的行驶优先投票一致。
    ``mass_moving`` 列缺失时（旧数据 / 旧调用路径）退回全部有效读数。

    可选的零速窗口过滤
    ------------------
    若同时提供 ``speed_col`` 与 ``zero_speed_window_seconds``，则每个候选
    切点需通过 ``_split_point_has_zero_speed`` 检验：切点附近 ±W/2 窗口
    内必须存在 v=0 样本，否则丢弃该切点（视为 CVW 噪声）。

    返回：拆分时间点列表（UTC）。空列表表示无需拆分。
    """
    if 'mass_cluster' not in df_raw.columns:
        return []

    t_s = _to_utc(t_start)
    t_e = _to_utc(t_end)
    times = pd.to_datetime(df_raw[TIME_COL], errors='coerce', utc=True)
    mask = (times >= t_s) & (times <= t_e) & df_raw['mass_cluster'].notna()
    # Scan only the "moving" (mass_moving == True) mass readings when detecting
    # cluster-transition split points. A standstill J1939 GCVW broadcast is
    # unreliable (loading/unloading transients, default/last-held values), so a
    # stationary row assigned to a neighbouring cluster would otherwise either
    # (a) fabricate a spurious split at a stop — yielding a tiny sub-segment that
    # gets dropped by min_soc_drop, so a chunk of the trip goes missing — or
    # (b) blur a genuine moving-mass change. This mirrors cluster_mass_data's
    # moving-only cluster means (v2.2.4) and _get_seg_dominant_cluster's
    # moving-first voting. If mass_moving is absent (legacy data / call path),
    # fall back to the historical all-valid-readings behaviour.
    if 'mass_moving' in df_raw.columns:
        mask = mask & df_raw['mass_moving'].astype(bool)
    sub = df_raw.loc[mask, [TIME_COL, 'mass_cluster']].copy()
    sub[TIME_COL] = times[mask]
    sub = sub.sort_values(TIME_COL).reset_index(drop=True)

    if len(sub) < 2:
        return []

    clusters = sub['mass_cluster'].values
    splits: list[pd.Timestamp] = []
    for i in range(1, len(clusters)):
        if clusters[i] != clusters[i - 1]:
            splits.append(sub.iloc[i][TIME_COL])

    # 方案 B：要求切点附近存在 v=0 样本，否则视为 CVW 噪声尖刺，放弃切分
    if splits and speed_col is not None and zero_speed_window_seconds is not None:
        splits = [
            t for t in splits
            if _split_point_has_zero_speed(
                df_raw, t, speed_col, zero_speed_window_seconds,
            )
        ]

    return splits


def _split_seg_at_times(
    seg: dict,
    df_raw: pd.DataFrame,
    split_times: list[pd.Timestamp],
    min_soc_drop: float = 5.0,
    min_energy_kwh: float = 2.0,
) -> list[dict]:
    """
    将一个放电分段在给定时间点处拆分为多个子分段。

    子分段关键指标计算方式
    ----------------------
    - start_soc / end_soc : 从原始数据线性插值
    - delta_soc_pct       : end_soc - start_soc（负值）
    - delta_energy_kwh    : 按 SOC 比例从父分段按比例分配
    - effective_capacity_kwh : |delta_energy| / (|delta_soc| / 100)
    - odo / lat / lon     : 从原始数据最近值查找
    - _anchor_*           : 置 None（比例分配后锚点无意义）

    不满足 min_soc_drop 或 min_energy_kwh 的子分段将被丢弃。
    若最终无有效子分段，返回 [seg]（原始分段）。
    """
    t_seg_s = _to_utc(seg['start_time'])
    t_seg_e = _to_utc(seg['end_time'])

    splits_ok = sorted(_to_utc(t) for t in split_times if t_seg_s < _to_utc(t) < t_seg_e)
    if not splits_ok:
        return [seg]

    df_r = df_raw.copy()
    df_r[TIME_COL] = pd.to_datetime(df_r[TIME_COL], errors='coerce', utc=True)
    df_r = df_r.dropna(subset=[TIME_COL]).sort_values(TIME_COL).reset_index(drop=True)

    if SOC_COL in df_r.columns:
        df_r['_soc_n'] = pd.to_numeric(df_r[SOC_COL], errors='coerce')
        df_r.loc[df_r['_soc_n'] == 0, '_soc_n'] = np.nan
    else:
        df_r['_soc_n'] = np.nan
    soc_valid = df_r[df_r['_soc_n'].notna()].sort_values(TIME_COL)

    if ODO_COL in df_r.columns:
        df_r['_odo_n'] = pd.to_numeric(df_r[ODO_COL], errors='coerce')
        odo_valid = df_r[df_r['_odo_n'].notna()].sort_values(TIME_COL)
    else:
        odo_valid = pd.DataFrame()

    def _soc_at(t: pd.Timestamp) -> float:
        if soc_valid.empty:
            return float('nan')
        before = soc_valid[soc_valid[TIME_COL] <= t]
        after  = soc_valid[soc_valid[TIME_COL] >= t]
        if before.empty:
            return float(after.iloc[0]['_soc_n'])
        if after.empty:
            return float(before.iloc[-1]['_soc_n'])
        t0, v0 = before.iloc[-1][TIME_COL], float(before.iloc[-1]['_soc_n'])
        t1, v1 = after.iloc[0][TIME_COL],   float(after.iloc[0]['_soc_n'])
        if t0 == t1:
            return v0
        frac = max(0.0, min(1.0, (t - t0).total_seconds() / (t1 - t0).total_seconds()))
        return v0 + frac * (v1 - v0)

    def _odo_at(t: pd.Timestamp) -> float:
        if odo_valid.empty:
            return float('nan')
        before = odo_valid[odo_valid[TIME_COL] <= t]
        return float(before.iloc[-1]['_odo_n']) if not before.empty else float('nan')

    # 预计算有效 lat/lon 子集（避免在循环中反复复制 DataFrame）
    _ll_valid = pd.DataFrame()
    if 'latitude' in df_r.columns and 'longitude' in df_r.columns:
        _ll_tmp = df_r[[TIME_COL, 'latitude', 'longitude']].copy()
        _ll_tmp['_lat'] = pd.to_numeric(_ll_tmp['latitude'], errors='coerce')
        _ll_tmp['_lon'] = pd.to_numeric(_ll_tmp['longitude'], errors='coerce')
        _ll_valid = _ll_tmp[_ll_tmp['_lat'].notna() & (_ll_tmp['_lat'] != 0)
                            & _ll_tmp['_lon'].notna()].sort_values(TIME_COL)

    def _latlon_at(t: pd.Timestamp, side: str = 'start'):
        if _ll_valid.empty:
            return None, None
        subset = _ll_valid[_ll_valid[TIME_COL] >= t] if side == 'start' else _ll_valid[_ll_valid[TIME_COL] <= t]
        row = subset.iloc[0] if (side == 'start' and not subset.empty) else (
              subset.iloc[-1] if (side == 'end' and not subset.empty) else _ll_valid.iloc[-1 if side == 'end' else 0])
        return round(float(row['_lat']), 6), round(float(row['_lon']), 6)

    boundaries   = [t_seg_s] + splits_ok + [t_seg_e]
    orig_dsoc    = float(seg['delta_soc_pct'])    # negative
    orig_denergy = float(seg['delta_energy_kwh']) # negative

    result: list[dict] = []
    for k in range(len(boundaries) - 1):
        sub_t_s  = boundaries[k]
        sub_t_e  = boundaries[k + 1]
        is_first = (k == 0)
        is_last  = (k == len(boundaries) - 2)

        sub_soc_s = float(seg['start_soc']) if is_first else _soc_at(sub_t_s)
        sub_soc_e = float(seg['end_soc'])   if is_last  else _soc_at(sub_t_e)
        if np.isnan(sub_soc_s) or np.isnan(sub_soc_e):
            continue

        sub_dsoc = sub_soc_e - sub_soc_s    # should be negative
        if -sub_dsoc < min_soc_drop:
            continue

        # 能量按 SOC 比例分配
        if orig_dsoc != 0 and np.isfinite(orig_denergy):
            sub_denergy = orig_denergy * (sub_dsoc / orig_dsoc)
        else:
            sub_denergy = float('nan')
        if np.isnan(sub_denergy) or abs(sub_denergy) < min_energy_kwh:
            continue

        sub_effcap = (abs(sub_denergy) / (abs(sub_dsoc) / 100.0)
                      if abs(sub_dsoc) > 0 else float('nan'))

        sub_odo_s = float(seg.get('odo_start_km') or float('nan')) if is_first else _odo_at(sub_t_s)
        sub_odo_e = float(seg.get('odo_end_km')   or float('nan')) if is_last  else _odo_at(sub_t_e)

        lat_s, lon_s = ((seg.get('lat_start'), seg.get('lon_start')) if is_first
                        else _latlon_at(sub_t_s, 'start'))
        lat_e, lon_e = ((seg.get('lat_end'),   seg.get('lon_end'))   if is_last
                        else _latlon_at(sub_t_e, 'end'))

        result.append({
            'start_time':             sub_t_s,
            'end_time':               sub_t_e,
            'start_soc':              round(sub_soc_s, 2),
            'end_soc':                round(sub_soc_e, 2),
            'delta_soc_pct':          round(sub_dsoc, 2),
            'delta_energy_kwh':       round(sub_denergy, 3),
            'energy_source':          seg.get('energy_source'),
            'delta_moving_kwh':       None,
            'effective_capacity_kwh': (round(sub_effcap, 1)
                                       if np.isfinite(sub_effcap) else None),
            'odo_start_km':  round(sub_odo_s, 3) if np.isfinite(sub_odo_s) else None,
            'odo_end_km':    round(sub_odo_e, 3) if np.isfinite(sub_odo_e) else None,
            'lat_start':     lat_s,
            'lon_start':     lon_s,
            'lat_end':       lat_e,
            'lon_end':       lon_e,
            '_anchor_start_time':    None,
            '_anchor_end_time':      None,
            '_anchor_start_rel_kwh': float('nan'),
            '_anchor_end_rel_kwh':   float('nan'),
        })

    return result if result else [seg]


def split_discharge_by_mass(
    discharge_segs: list[dict],
    df_raw: pd.DataFrame,
    min_soc_drop: float = 5.0,
    min_energy_kwh: float = 2.0,
    speed_col: str | None = None,
    zero_speed_window_seconds: float | None = None,
) -> list[dict]:
    """
    基于质量聚类标签变化拆分放电分段。

    前置条件：df_raw 已通过 ``cluster_mass_data()`` 添加了 ``mass_cluster`` 列。

    对每个放电分段，检测其时间窗口内 mass_cluster 是否发生变化；
    若变化则在该时间点将分段拆分为多个子分段（每个子分段内质量聚类一致）。
    未检测到变化的分段保持原样不变。

    可选的零速切点过滤（方案 B）
    --------------------------
    若同时提供 ``speed_col`` 与 ``zero_speed_window_seconds``，则每个候选
    切点附近 ±W/2 时间窗内必须存在 v=0 样本才被采纳；否则视为 CVW 噪声
    尖刺，丢弃该切点。这避免了在连续高速行驶途中因质量读数瞬时跳变而
    把一条 trip 切成两段（如 EX74JXW 07-17_0008 案例）。

    参数
    ----
    discharge_segs            : 放电分段列表
    df_raw                    : 带有 mass_cluster 列的原始遥测 DataFrame
    min_soc_drop              : 子分段最小 SOC 下降量（%），低于此则丢弃
                                （默认 5.0）
    min_energy_kwh            : 子分段最小能量（kWh），低于此则丢弃（默认 2.0）
    speed_col                 : 速度列名，用于零速窗口检验（可选）
    zero_speed_window_seconds : 零速窗口总宽度 W（秒），通常 =
                                min_stop_duration_min × 60（可选）
    """
    result: list[dict] = []
    for seg in discharge_segs:
        splits = _detect_cluster_transitions(
            df_raw, seg['start_time'], seg['end_time'],
            speed_col=speed_col,
            zero_speed_window_seconds=zero_speed_window_seconds,
        )
        if not splits:
            result.append(seg)
        else:
            sub_segs = _split_seg_at_times(
                seg, df_raw, splits,
                min_soc_drop=min_soc_drop,
                min_energy_kwh=min_energy_kwh,
            )
            result.extend(sub_segs)
    return result


# =============================================================================
# 重新计算缺失的能量锚点
# =============================================================================

def _recompute_anchors(
    segments: list[dict],
    df_raw: pd.DataFrame,
    total_energy_col: str,
    moving_energy_col: str,
) -> None:
    """
    为 anchor 缺失的分段重新计算能量锚点（原地修改）。

    split_discharge_by_mass 拆分分段后，子段的 anchor 被清空（因为能量按 SOC
    比例分配，不再对应实际能量计数器读数）。此函数根据子段的 energy_source
    重新查找最近的能量计数器读数，恢复锚点以便验证图标注。
    """
    if not segments:
        return

    df = df_raw.copy()
    df[TIME_COL] = pd.to_datetime(df[TIME_COL], errors='coerce', utc=True)
    df = df.dropna(subset=[TIME_COL]).sort_values(TIME_COL).reset_index(drop=True)
    times_np = df[TIME_COL].values.astype('datetime64[ns]')

    has_total = total_energy_col in df.columns
    has_moving = moving_energy_col in df.columns

    tot_base = mov_base = 0.0
    if has_total:
        df['_tot'] = pd.to_numeric(df[total_energy_col], errors='coerce')
        _tv = df.loc[df['_tot'].notna(), '_tot']
        if len(_tv):
            tot_base = float(_tv.iloc[0])
    if has_moving:
        df['_mov'] = pd.to_numeric(df[moving_energy_col], errors='coerce')
        _mv = df.loc[df['_mov'].notna(), '_mov']
        if len(_mv):
            mov_base = float(_mv.iloc[0])

    def _nb(col: str, t_np):
        mask = df[col].notna() & (times_np <= t_np)
        idx = df.index[mask]
        if len(idx) == 0:
            return np.nan, None
        i = idx[-1]
        return float(df.loc[i, col]), pd.Timestamp(times_np[i])

    def _na(col: str, t_np):
        mask = df[col].notna() & (times_np >= t_np)
        idx = df.index[mask]
        if len(idx) == 0:
            return np.nan, None
        i = idx[0]
        return float(df.loc[i, col]), pd.Timestamp(times_np[i])

    for seg in segments:
        # 跳过已有有效锚点的分段
        a_st = seg.get('_anchor_start_time')
        a_et = seg.get('_anchor_end_time')
        a_sv = seg.get('_anchor_start_rel_kwh', float('nan'))
        a_ev = seg.get('_anchor_end_rel_kwh', float('nan'))
        if (a_st is not None and a_et is not None
                and not np.isnan(a_sv) and not np.isnan(a_ev)):
            continue

        t_s = pd.Timestamp(seg['start_time']).asm8.astype('datetime64[ns]')
        t_e = pd.Timestamp(seg['end_time']).asm8.astype('datetime64[ns]')
        src = seg.get('energy_source', '')

        if src == 'total_energy' and has_total:
            e_s, t_es = _nb('_tot', t_s)
            e_e, t_ee = _na('_tot', t_e)
            if not np.isnan(e_s) and not np.isnan(e_e):
                seg['_anchor_start_time'] = t_es
                seg['_anchor_end_time'] = t_ee
                seg['_anchor_start_rel_kwh'] = round((e_s - tot_base) / 1000.0, 4)
                seg['_anchor_end_rel_kwh'] = round((e_e - tot_base) / 1000.0, 4)
        elif src == 'moving_energy' and has_moving:
            e_s, t_es = _nb('_mov', t_s)
            e_e, t_ee = _na('_mov', t_e)
            if not np.isnan(e_s) and not np.isnan(e_e):
                seg['_anchor_start_time'] = t_es
                seg['_anchor_end_time'] = t_ee
                seg['_anchor_start_rel_kwh'] = round((e_s - mov_base) / 1000.0, 4)
                seg['_anchor_end_rel_kwh'] = round((e_e - mov_base) / 1000.0, 4)


# =============================================================================
# 基于质量相似性合并相邻放电分段
# =============================================================================

def _merge_two_discharge_segs(seg_a: dict, seg_b: dict) -> dict:
    """将两个相邻放电分段合并为一个，用于 merge_discharge_by_mass 内部调用。"""
    soc_s = float(seg_a['start_soc'])
    soc_e = float(seg_b['end_soc'])
    dsoc  = soc_e - soc_s  # negative

    # Sum energies (both negative for discharge)
    e_a = seg_a.get('delta_energy_kwh')
    e_b = seg_b.get('delta_energy_kwh')
    denergy = float('nan')
    if e_a is not None and e_b is not None:
        fa, fb = float(e_a), float(e_b)
        if np.isfinite(fa) and np.isfinite(fb):
            denergy = fa + fb

    effcap = float('nan')
    if np.isfinite(denergy) and abs(dsoc) > 0:
        effcap = abs(denergy) / (abs(dsoc) / 100.0)

    # Prefer higher-priority energy source
    _prio = {'total_energy': 0, 'moving_energy': 1, 'soc_estimate': 2}
    src_a = seg_a.get('energy_source', 'soc_estimate')
    src_b = seg_b.get('energy_source', 'soc_estimate')
    src   = src_a if _prio.get(src_a, 9) <= _prio.get(src_b, 9) else src_b

    return {
        'start_time':             seg_a['start_time'],
        'end_time':               seg_b['end_time'],
        'start_soc':              soc_s,
        'end_soc':                soc_e,
        'delta_soc_pct':          round(dsoc, 2),
        'delta_energy_kwh':       round(denergy, 3) if np.isfinite(denergy) else None,
        'energy_source':          src,
        'delta_moving_kwh':       None,
        'effective_capacity_kwh': round(effcap, 1) if np.isfinite(effcap) else None,
        'odo_start_km':           seg_a.get('odo_start_km'),
        'odo_end_km':             seg_b.get('odo_end_km'),
        'lat_start':              seg_a.get('lat_start'),
        'lon_start':              seg_a.get('lon_start'),
        'lat_end':                seg_b.get('lat_end'),
        'lon_end':                seg_b.get('lon_end'),
        '_anchor_start_time':     seg_a.get('_anchor_start_time'),
        '_anchor_end_time':       seg_b.get('_anchor_end_time'),
        '_anchor_start_rel_kwh':  seg_a.get('_anchor_start_rel_kwh', float('nan')),
        '_anchor_end_rel_kwh':    seg_b.get('_anchor_end_rel_kwh', float('nan')),
    }


def merge_discharge_by_mass(
    discharge_segs: list[dict],
    df_raw: pd.DataFrame,
    charge_segs: list[dict] | None = None,
    max_merge_gap_min: float | None = None,
) -> list[dict]:
    """
    基于质量聚类标签合并相邻放电分段。

    前置条件：df_raw 已通过 ``cluster_mass_data()`` 添加了 ``mass_cluster`` 列。

    合并条件（同时满足）：
    - 相邻段的主导 mass_cluster 相同（同一质量等级）
    - 间隔内无充电分段
    - 间隔（静止时长）< ``max_merge_gap_min``（若提供）

    不同 cluster → 视为装卸货事件，保持分离。

    长时间静止切分（可选，opt-in）
    ------------------------------
    速度分段（``find_speed_trips``）已把行驶期之间停车 >= ``min_stop_duration_min``
    的间隔切成相邻 trip；本函数随后会把同质量 cluster、间隔无充电的相邻 trip
    重新合并成一条长 trip。当 ``max_merge_gap_min`` 提供时，若两个相邻 trip 之间
    的静止间隔 >= 该阈值（分钟），则视为行程边界，拒绝合并——即使质量不变。
    用途：把「行驶 → 长时间停车 → 再行驶」切成两个 trip（如 Nestlé 车 YK73WFN
    白天中段长达数小时的停车）。``None``（默认）= 关闭，行为与历史完全一致。

    参数
    ----
    discharge_segs    : 放电分段列表
    df_raw            : 带有 mass_cluster 列的原始遥测 DataFrame
    charge_segs       : 充电分段列表；若间隔内存在充电则阻止合并（默认 None）
    max_merge_gap_min : 相邻 trip 之间允许合并的最大静止间隔（分钟）。间隔 >=
                        此值则拒绝合并（保持为两个 trip）。``None`` = 不应用
                        （默认，向后兼容；仅 Nestlé 车经 vehicles.json
                        ``split_long_stops_min`` 启用）。
    """
    if len(discharge_segs) <= 1 or 'mass_cluster' not in df_raw.columns:
        return discharge_segs

    # 预转换充电段时间
    charge_intervals: list[tuple] = []
    if charge_segs:
        for c in charge_segs:
            try:
                charge_intervals.append((_to_utc(c['start_time']), _to_utc(c['end_time'])))
            except Exception:
                pass

    def _has_charge_in_gap(gap_start: pd.Timestamp, gap_end: pd.Timestamp) -> bool:
        for c_s, c_e in charge_intervals:
            if c_s < gap_end and c_e > gap_start:
                return True
        return False

    # 每个分段的主导 mass_cluster
    seg_clusters = [
        _get_seg_dominant_cluster(df_raw, s['start_time'], s['end_time'])
        for s in discharge_segs
    ]

    result: list[dict] = []
    i = 0
    while i < len(discharge_segs):
        seg   = discharge_segs[i].copy()
        c_cur = seg_clusters[i]
        j     = i + 1

        while j < len(discharge_segs):
            c_next = seg_clusters[j]
            # 未知 cluster → 保守不合并
            if c_cur is None or c_next is None:
                break
            # 不同 cluster → 装卸货事件，保持分离
            if c_cur != c_next:
                break
            # 间隔内有充电 → 不合并
            gap_start = _to_utc(seg['end_time'])
            gap_end   = _to_utc(discharge_segs[j]['start_time'])
            if _has_charge_in_gap(gap_start, gap_end):
                break
            # 长时间静止 → 行程边界（opt-in，Nestlé 专用）：即使质量不变、
            # 间隔无充电，若静止间隔 >= max_merge_gap_min 也拒绝合并。
            if max_merge_gap_min is not None:
                _gap_min = (gap_end - gap_start).total_seconds() / 60.0
                if _gap_min >= max_merge_gap_min:
                    break
            # 相同 cluster，无充电，间隔不长 → 合并
            seg = _merge_two_discharge_segs(seg, discharge_segs[j])
            j  += 1

        result.append(seg)
        i = j

    return result


# =============================================================================
# 锚点非重叠强制（修正稀疏累计计数器导致的相邻段能量重复计入）
# =============================================================================

def _enforce_anchor_ordering(discharge_segs: list[dict], reg: str = '') -> int:
    """强制相邻放电段的能量锚点不重叠（前段 anchor_end <= 后段 anchor_start）。

    背景
    ----
    speed 分支中每个 trip 的能量用 ``_nearest_before(total_energy, trip_start)``
    → ``_nearest_after(total_energy, trip_end)`` 计算。``total_energy`` 是稀疏读数的
    累计计数器：若某 trip 结束后到下一个 trip 之间没有计数器读数，
    ``_nearest_after(trip_end)`` 会跳到「下一个 trip 期间/之后」的读数，使本段能量
    重复计入下一段的能量，并造成 ``anchor_end(i) > anchor_start(i+1)`` 的时间重叠
    → ``delta_energy_kwh`` / ``effective_capacity_kwh`` / EP 被高估。

    本后处理在 ``merge_discharge_by_mass`` + ``_recompute_anchors`` 之后、对**最终**
    放电段运行：把重叠的前段 ``_anchor_end_time`` 钳到后段 ``_anchor_start_time``，
    并据已是 kWh 的锚点相对值重算 ``delta_energy_kwh`` 与 ``effective_capacity_kwh``。
    仅修改实际存在重叠的段（稀疏计数器场景）；计数器在间隔内有读数时无重叠 →
    不改动。

    锚点相对值与能量的关系（见 find_discharge_segments_by_speed）：
        delta_energy_kwh = -(anchor_end_rel_kwh - anchor_start_rel_kwh)
    （二者皆相对腿起点归零、单位 kWh；放电为负）。

    原地修改 ``discharge_segs`` 内的段字典；返回被钳位的段数（供 regen 日志统计）。
    """
    if not discharge_segs or len(discharge_segs) < 2:
        return 0

    # 1. 防御性按 start_time 排序（仅用于确定相邻关系；段字典为共享引用，
    #    原地修改会传回 discharge_segs，不改变调用方列表的原有顺序）。
    segs = sorted(discharge_segs, key=lambda s: _to_utc(s['start_time']))

    def _usable_anchor(s: dict) -> bool:
        # soc_estimate 段没有真实计数器锚点（rel 为 NaN）→ 跳过
        if s.get('energy_source') == 'soc_estimate':
            return False
        if s.get('_anchor_start_time') is None or s.get('_anchor_end_time') is None:
            return False
        a_sv = s.get('_anchor_start_rel_kwh', float('nan'))
        a_ev = s.get('_anchor_end_rel_kwh', float('nan'))
        try:
            return bool(np.isfinite(a_sv) and np.isfinite(a_ev))
        except (TypeError, ValueError):
            return False

    n_clamped = 0
    for k in range(len(segs) - 1):
        cur = segs[k]
        nxt = segs[k + 1]
        if not (_usable_anchor(cur) and _usable_anchor(nxt)):
            continue

        cur_end   = _to_utc(cur['_anchor_end_time'])
        nxt_start = _to_utc(nxt['_anchor_start_time'])
        if cur_end <= nxt_start:
            continue  # 无重叠 → 不动（计数器在间隔内有读数的正常情形）

        # 重叠 → 把前段 anchor_end 钳到后段 anchor_start，并据锚点相对值重算能量
        new_end_rel = nxt['_anchor_start_rel_kwh']
        new_delta   = -(new_end_rel - cur['_anchor_start_rel_kwh'])
        if not (new_delta < 0):
            # 钳位后不再是有效放电（锚点塌缩 / 病态）→ 保持原段不变，仅告警
            logger.warning(
                '[%s] anchor overlap clamp skipped (would collapse to '
                'non-discharge): cur trip start=%s, anchor_end %s > next '
                'anchor_start %s, new_delta=%.3f',
                reg, cur.get('start_time'), cur_end, nxt_start, new_delta,
            )
            continue

        cur['_anchor_end_time']    = nxt['_anchor_start_time']
        cur['_anchor_end_rel_kwh'] = new_end_rel
        cur['delta_energy_kwh']    = round(new_delta, 3)
        dsoc_abs = abs(cur.get('delta_soc_pct') or 0.0)
        if dsoc_abs > 0:
            cur['effective_capacity_kwh'] = round(
                abs(new_delta) / (dsoc_abs / 100.0), 1
            )
        n_clamped += 1
        logger.info(
            '[%s] anchor overlap clamped: cur trip start=%s, anchor_end %s → %s '
            '(next anchor_start); delta_energy_kwh=%s, eff_cap=%s',
            reg, cur.get('start_time'), cur_end, nxt_start,
            cur['delta_energy_kwh'], cur.get('effective_capacity_kwh'),
        )

    return n_clamped
