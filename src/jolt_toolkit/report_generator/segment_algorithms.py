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

from __future__ import annotations

import logging
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

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
    """从 configs/ 目录加载 JSON 配置文件。"""
    path = _get_config_path(name)
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return _json.load(f)
    return {}

VEHICLE_CONFIG: dict[str, dict[str, Any]] = _load_json('vehicles.json')
PIPELINE_CONFIGS: dict[str, dict] = _load_json('pipelines.json')

# =============================================================================
# 每段质量聚合（可配置、稳健）
# =============================================================================
# Single source of truth shared by the three plain-mean sites that estimate a
# segment's vehicle mass (Excel "Vehicle Mass (kg)" column, the validation-figure
# Panel-4 annotation, and the finetune recompute). The aggregation method is a
# configurable pipeline branch parameter (``mass_agg``), so a transient telematics
# weight spike (e.g. a ~49000 kg reading on a true ~30 t trip) no longer inflates
# the value. The default ``"mean"`` preserves the legacy behaviour bit-for-bit.

_MASS_AGG_METHODS = (
    'mean', 'median', 'iqr_median', 'mad_median',
    'iqr_mean', 'mad_mean', 'mad_tw_mean', 'trimmed_mean',
)

# ``mad_median`` / ``mad_mean`` fence width as a multiple of the MAD (median
# absolute deviation): inliers are kept within ``median ± _MAD_K * MAD``. Using
# the raw MAD (no 1.4826 normal-consistency scaling), k=3 gives a fence of
# ~2 robust-sigma — tight enough to shave a one-sided high-spike tail that an IQR
# fence leaves in (its q3 lands on the spikes), yet validated to never dip below
# the central body (see :func:`_agg_mass`).
_MAD_K = 3.0

# ``trimmed_mean`` per-tail trim fraction (symmetric). 0.20 drops the lowest and
# highest 20% of the samples and means the central 60% — the classic 20% trimmed
# mean (matching ``scipy.stats.trim_mean(proportiontocut=0.20)``).
_TRIM_FRAC = 0.20


def _iqr_inliers(sel: 'pd.Series') -> 'pd.Series':
    """Tukey 1.5·IQR inlier subset of ``sel`` (shared by ``iqr_median`` /
    ``iqr_mean`` so they fence identically).

    Returns the subset within ``[q1 - 1.5*iqr, q3 + 1.5*iqr]`` when the IQR is
    positive and >= 2 samples survive; otherwise returns ``sel`` unchanged (a
    zero IQR means a quantised GCW where the median already ignores a minority
    spike).
    """
    q1, q3 = sel.quantile([0.25, 0.75])
    iqr = q3 - q1
    if iqr > 0:
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        inliers = sel[(sel >= lo) & (sel <= hi)]
        if len(inliers) >= 2:
            return inliers
    return sel


def _mad_inliers(sel: 'pd.Series') -> 'pd.Series':
    """Median ± ``_MAD_K``·MAD inlier subset of ``sel`` (shared by ``mad_median`` /
    ``mad_mean`` so they fence identically).

    Returns the subset within ``median ± _MAD_K*MAD`` (raw median absolute
    deviation) when the MAD is positive and >= 2 samples survive; otherwise
    returns ``sel`` unchanged. Because the fence is centred on the robust median
    rather than on the quartiles, it shaves a dense body's one-sided HIGH-spike
    tail that the IQR fence leaves in (a cluster of spikes pins q3, so the IQR
    fence stays too wide).
    """
    med = sel.median()
    mad = float((sel - med).abs().median())
    if mad > 0:
        lo, hi = med - _MAD_K * mad, med + _MAD_K * mad
        inliers = sel[(sel >= lo) & (sel <= hi)]
        if len(inliers) >= 2:
            return inliers
    return sel


def _trimmed_inliers(sel: 'pd.Series', frac: float = _TRIM_FRAC) -> 'pd.Series':
    """Symmetric trimmed subset of ``sel``: drop the lowest & highest ``frac``.

    ``k = int(len * frac)`` samples are dropped from each tail (matching
    ``scipy.stats.trim_mean`` semantics) and the central subset is returned. When
    trimming would leave fewer than one sample (tiny windows) ``sel`` is returned
    unchanged so the caller still has a value.
    """
    n = len(sel)
    k = int(n * frac)
    if k <= 0 or n - 2 * k < 1:
        return sel
    ordered = sel.sort_values()
    return ordered.iloc[k:n - k]


def _coerce_seconds(ts: 'pd.Series') -> 'np.ndarray | None':
    """Coerce ``ts`` (a per-sample time axis aligned to a kept mass set) into a
    1-D float array of seconds, or ``None`` when it cannot be used.

    Accepts either a datetime-like Series (any unit / tz; e.g. the telematics
    ``eventDatetime``) or an already-numeric seconds Series (e.g. the dashboard's
    seconds-from-midnight). For datetimes the offset is taken from the first
    element, so only relative spacing matters (the time-weighted mean is invariant
    to a constant time offset / uniform scaling). Any NaN/NaT makes it unusable.
    """
    if ts is None or len(ts) == 0:
        return None
    s = ts if isinstance(ts, pd.Series) else pd.Series(list(ts))
    if pd.api.types.is_numeric_dtype(s):
        n = pd.to_numeric(s, errors='coerce')
        return n.to_numpy('float64') if bool(n.notna().all()) else None
    t = pd.to_datetime(s, errors='coerce', utc=True)
    if not bool(t.notna().all()):
        return None
    return (t - t.iloc[0]).dt.total_seconds().to_numpy('float64')


def _time_weighted_mean(values: 'np.ndarray', seconds: 'np.ndarray') -> float:
    """Trapezoidal time-weighted mean of ``values`` sampled at ``seconds``.

    Each sample's weight is the time interval it represents (trapezoidal rule:
    half the gap to each neighbour; the two endpoints get half of their single
    adjacent gap). A short dense burst of repeated readings therefore contributes
    only its (short) duration, not its (large) count — so a transient lag plateau
    that telematics happens to sample densely no longer biases the mean. Falls
    back to the plain arithmetic mean when the time axis is unusable (< 2 points,
    any non-finite second, or a zero span — e.g. all-duplicate timestamps), which
    makes ``mad_tw_mean`` degrade exactly to ``mad_mean``.
    """
    v = np.asarray(values, dtype='float64')
    s = np.asarray(seconds, dtype='float64')
    if v.size < 2 or s.size != v.size or not np.isfinite(s).all():
        return float(v.mean())
    order = np.argsort(s, kind='mergesort')
    s = s[order]
    v = v[order]
    if (s[-1] - s[0]) <= 0:
        return float(v.mean())
    w = np.empty_like(s)
    w[1:-1] = (s[2:] - s[:-2]) / 2.0
    w[0] = (s[1] - s[0]) / 2.0
    w[-1] = (s[-1] - s[-2]) / 2.0
    wsum = float(w.sum())
    if wsum <= 0:
        return float(v.mean())
    return float(np.dot(w, v) / wsum)


def _mad_tw_value(sel: 'pd.Series', kept: 'pd.Series',
                  timestamps: 'pd.Series | None') -> float:
    """Time-weighted mean of the MAD-fenced ``kept`` set, aligned to ``timestamps``.

    ``timestamps`` is expected to be index-aligned to ``sel`` (the pre-fence
    sample series), so it is reindexed onto ``kept.index`` to pick each survivor's
    time. Any failure (missing / mis-aligned / non-unique / unusable timestamps)
    falls back to ``kept.mean()`` — i.e. plain ``mad_mean`` — so the method is
    always safe to select even when a caller cannot supply a time axis.
    """
    if len(kept) >= 2 and isinstance(timestamps, pd.Series):
        try:
            secs = _coerce_seconds(timestamps.reindex(kept.index))
            if secs is not None and len(secs) == len(kept):
                return _time_weighted_mean(kept.to_numpy('float64'), secs)
        except Exception:  # pragma: no cover - defensive; degrade to mad_mean
            pass
    return float(kept.mean())


def _agg_mass(sel: 'pd.Series', method: str = 'mean',
              timestamps: 'pd.Series | None' = None) -> tuple[float, float]:
    """Aggregate an already-filtered mass-sample series into ``(mass_kg, cv)``.

    ``sel`` is expected to already be positive (> 0) and, where applicable,
    restricted to moving-only samples (the caller owns the filtering, so that the
    Excel column and the figure annotation share one definition).

    Each method is a two-step recipe — an outlier *fence* (which inliers to keep)
    followed by a central *estimator* (median or mean over the kept set):

        ``"mean"``         — no fence; arithmetic mean of all samples (legacy
                             default; identical to the pre-v2.2.6 behaviour, so
                             non-opted-in vehicles are unchanged).
        ``"median"``       — no fence; plain median (matches the diesel pipeline).
        ``"iqr_median"``   — Tukey 1.5·IQR fence (:func:`_iqr_inliers`) → median.
        ``"iqr_mean"``     — Tukey 1.5·IQR fence (:func:`_iqr_inliers`) → mean.
        ``"mad_median"``   — median ± _MAD_K·MAD fence (:func:`_mad_inliers`) →
                             median. The fence is centred on the robust median
                             rather than on the quartiles, so it shaves a dense
                             body's one-sided HIGH-spike tail that the IQR fence
                             leaves in (a cluster of spikes pins q3). Strengthens
                             high-outlier rejection over ``iqr_median`` without
                             dipping below the body.
        ``"mad_mean"``     — median ± _MAD_K·MAD fence (:func:`_mad_inliers`) →
                             mean of survivors. Same robust fence as ``mad_median``
                             but a mean estimator, so when the cleaned body still
                             carries a high-side lag/over-read tail (telematics
                             that lags the true load) the mean sits *below* the
                             body's median — useful where the median lands on
                             lag-high readings.
        ``"mad_tw_mean"``  — median ± _MAD_K·MAD fence (:func:`_mad_inliers`) → a
                             *time-weighted* mean of survivors (:func:`_mad_tw_value`
                             / :func:`_time_weighted_mean`), requiring per-sample
                             ``timestamps`` aligned to ``sel``. Each survivor is
                             weighted by the time interval it represents, so a
                             short dense burst of repeated lag/over-read values
                             (which count-weighting over-counts) contributes only
                             its brief duration. Where telematics samples are
                             bursty (dense transient clusters + sparse steady
                             cruise) this pulls the estimate toward the
                             duration-dominant settled body, matching how a 1 Hz
                             logger averages the same window. **Without usable
                             ``timestamps`` it degrades to ``mad_mean``** (identical
                             fence + plain mean), so it is always safe to select.
        ``"trimmed_mean"`` — symmetric 20% trimmed mean (:func:`_trimmed_inliers`
                             → mean): drop the lowest & highest 20% of samples and
                             mean the central 60% (a robust two-sided reference).

    ``timestamps`` is only consulted by ``mad_tw_mean``; every other method
    ignores it and is byte-identical to the pre-``timestamps`` behaviour.

    ``cv`` is ``std / mean`` of the kept set (sample std, ddof=1), matching the
    legacy reliability metric (``mad_tw_mean`` shares ``mad_mean``'s kept set, so
    its cv is identical). Unknown ``method`` falls back to ``"mean"`` with a
    warning. ``len(sel) < 2`` returns ``(nan, nan)``; ``mean <= 0`` yields a nan
    cv.
    """
    if sel is None or len(sel) < 2:
        return np.nan, np.nan
    m = (method or 'mean').lower()
    if m not in _MASS_AGG_METHODS:
        logger.warning("Unknown mass_agg method %r; falling back to 'mean'", method)
        m = 'mean'

    # Step 1 — outlier fence (the kept inlier set). ``mean`` / ``median`` use the
    # full window; each ``*_median`` and ``*_mean`` pair shares one fence helper,
    # so the median and mean variants of a fence keep BYTE-IDENTICAL inlier sets
    # (only the Step-2 estimator differs).
    if m in ('iqr_median', 'iqr_mean'):
        kept = _iqr_inliers(sel)
    elif m in ('mad_median', 'mad_mean', 'mad_tw_mean'):
        kept = _mad_inliers(sel)
    elif m == 'trimmed_mean':
        kept = _trimmed_inliers(sel)
    else:  # 'mean', 'median'
        kept = sel

    # Step 2 — central estimator over the kept set.
    if m in ('median', 'iqr_median', 'mad_median'):
        value = float(kept.median())
    elif m == 'mad_tw_mean':
        # Time-weighted mean of the (shared) MAD fence; falls back to the plain
        # mean of the kept set when no usable time axis is supplied (== mad_mean).
        value = _mad_tw_value(sel, kept, timestamps)
    else:  # 'mean', 'iqr_mean', 'mad_mean', 'trimmed_mean'
        value = float(kept.mean())

    # ``cv`` is std/mean of the kept set (legacy reliability metric); for a
    # singleton kept set fall back to the full window so cv stays meaningful.
    cv_set = kept if len(kept) >= 2 else sel
    mu = float(cv_set.mean())
    cv = float(cv_set.std() / mu) if mu > 0 else np.nan
    return round(value, 1), round(cv, 4)


def resolve_mass_agg(reg: str, pipeline_cfg: dict | None = None) -> str:
    """Resolve the ``mass_agg`` method for ``reg``.

    Precedence: vehicle-level (``vehicles.json``) > pipeline-level
    (``pipelines.json``) > default ``"mean"``. When ``pipeline_cfg`` is not
    supplied it is derived from the vehicle's configured pipeline, so a bare
    ``resolve_mass_agg(reg)`` still honours a pipeline-level setting.
    """
    veh = VEHICLE_CONFIG.get(reg, {})
    m = veh.get('mass_agg')
    if m:
        return str(m)
    if pipeline_cfg is None:
        pname = veh.get('pipeline', 'default_soc')
        pipeline_cfg = PIPELINE_CONFIGS.get(pname)
    if pipeline_cfg:
        m = pipeline_cfg.get('mass_agg')
        if m:
            return str(m)
    return 'mean'


# =============================================================================
# 充电分段检测
# =============================================================================
def find_charge_segments_by_soc(
    df_raw: pd.DataFrame,
    plateau_window_min: float = 60,
    min_soc_rise: float = 5.0,
    min_energy_kwh: float = 5.0,
    cap_lo: float | None = None,
    cap_hi: float | None = None,
    ac_col: str = AC_COL,
    dc_col: str = DC_COL,
    moving_energy_col: str = MOVING_COL,
    nominal_kwh: float | None = None,
) -> list[dict]:
    """
    从稀疏原始遥测数据中检测充电分段（SOC 持续上升段）。

    能量来源优先级
    --------------
    1. AC+DC 列（ac_col + dc_col）有效数据 → energy_source='ac_dc'
    2. SOC × nominal_kwh 估算            → energy_source='soc_estimate'

    返回字段（v2 统一 schema）
    -------------------------
    start_time, end_time, start_soc, end_soc,
    delta_soc_pct (正值),
    delta_energy_kwh (正值),
    energy_source,
    delta_moving_kwh (>= 0，或 None),
    effective_capacity_kwh,
    charge_type,
    ac_start_wh, ac_end_wh, dc_start_wh, dc_end_wh (None 若无 AC/DC 数据),
    odo_start_km, odo_end_km, latitude, longitude

    临时字段（_ANCHOR_PRIVATE_KEYS，保存 CSV 前需过滤）：
    _anchor_start_time, _anchor_end_time,
    _anchor_start_rel_kwh, _anchor_end_rel_kwh
    """
    if SOC_COL not in df_raw.columns or TIME_COL not in df_raw.columns:
        return []

    df = df_raw.copy()
    df[TIME_COL] = pd.to_datetime(df[TIME_COL], errors='coerce', utc=True)
    df = df.dropna(subset=[TIME_COL]).sort_values(TIME_COL).reset_index(drop=True)

    df[SOC_COL] = pd.to_numeric(df[SOC_COL], errors='coerce')
    df.loc[df[SOC_COL] == 0, SOC_COL] = np.nan

    has_acdc = ac_col in df.columns and dc_col in df.columns
    if has_acdc:
        df[ac_col] = pd.to_numeric(df[ac_col], errors='coerce')
        df[dc_col] = pd.to_numeric(df[dc_col], errors='coerce')

    has_moving = moving_energy_col in df.columns
    if has_moving:
        df[moving_energy_col] = pd.to_numeric(df[moving_energy_col], errors='coerce')

    if ODO_COL in df.columns:
        df[ODO_COL] = pd.to_numeric(df[ODO_COL], errors='coerce')
    for _c in ('latitude', 'longitude'):
        if _c in df.columns:
            df[_c] = pd.to_numeric(df[_c], errors='coerce')
            df.loc[df[_c] == 0, _c] = np.nan

    # ── SOC 上升块检测 ────────────────────────────────────────────────────────
    soc_mask = df[SOC_COL].notna()
    soc_pos  = np.array(df.index[soc_mask].tolist(), dtype=np.intp)
    if len(soc_pos) < 2:
        return []

    soc_vals  = df.loc[soc_pos, SOC_COL].values.astype(float)
    times_all = df[TIME_COL].values.astype('datetime64[ns]')
    n = len(soc_pos)

    rising = np.concatenate([[False], np.diff(soc_vals) > 0])
    blocks: list[list[int]] = []
    i = 1
    while i < n:
        if rising[i]:
            s = i
            while i < n and rising[i]:
                i += 1
            blocks.append([s, i - 1])
        else:
            i += 1

    if not blocks:
        return []

    # ── 合并相邻块 ────────────────────────────────────────────────────────────
    plateau_ns = int(plateau_window_min * 60 * 1_000_000_000)
    merged = [blocks[0][:]]
    for blk in blocks[1:]:
        prev_end = merged[-1][1]
        gap_ns   = int(times_all[soc_pos[blk[0]]] - times_all[soc_pos[prev_end]])
        has_drop = any(soc_vals[j] < soc_vals[j - 1]
                       for j in range(prev_end + 1, blk[0]))
        if gap_ns <= plateau_ns and not has_drop:
            merged[-1][1] = blk[1]
        else:
            merged.append(blk[:])

    # ── 准备能量序列 ──────────────────────────────────────────────────────────
    energy_pos  = np.array([], dtype=np.intp)
    base_wh     = 0.0
    if has_acdc:
        emask      = df[ac_col].notna() & df[dc_col].notna()
        energy_pos = np.array(df.index[emask].tolist(), dtype=np.intp)
        if len(energy_pos) > 0:
            base_wh = float(df.at[energy_pos[0], ac_col]) + float(df.at[energy_pos[0], dc_col])

    mov_pos     = np.array([], dtype=np.intp)
    if has_moving:
        mmask   = df[moving_energy_col].notna()
        mov_pos = np.array(df.index[mmask].tolist(), dtype=np.intp)

    # ── 生成分段 ──────────────────────────────────────────────────────────────
    segments: list[dict] = []
    for blk_start, blk_end in merged:
        soc_row_s = int(soc_pos[blk_start - 1])
        soc_row_e = int(soc_pos[blk_end])
        soc_s = float(soc_vals[blk_start - 1])
        soc_e = float(soc_vals[blk_end])
        delta_soc = soc_e - soc_s          # positive for charge

        if delta_soc < min_soc_rise or delta_soc <= 0:
            continue

        # ── delta_energy_kwh: AC+DC → SOC estimate ────────────────────────
        delta_energy = None
        energy_source = None
        ac_s = ac_e = dc_s = dc_e = None
        anchor_s_time = anchor_e_time = None
        anchor_s_rel = anchor_e_rel = float('nan')

        if len(energy_pos) > 0:
            idx_s = int(np.searchsorted(energy_pos, soc_row_s, side='right')) - 1
            idx_e = int(np.searchsorted(energy_pos, soc_row_e, side='left'))
            if idx_s < 0:
                idx_s = 0
            if idx_e >= len(energy_pos):
                idx_e = len(energy_pos) - 1
            ext_s = int(energy_pos[idx_s])
            ext_e = int(energy_pos[idx_e])
            if ext_s < ext_e:
                _ac_s = float(df.at[ext_s, ac_col]); _ac_e = float(df.at[ext_e, ac_col])
                _dc_s = float(df.at[ext_s, dc_col]); _dc_e = float(df.at[ext_e, dc_col])
                _delta = ((_ac_e - _ac_s) + (_dc_e - _dc_s)) / 1000.0
                if _delta > 0:
                    delta_energy  = _delta
                    energy_source = 'ac_dc'
                    ac_s, ac_e, dc_s, dc_e = _ac_s, _ac_e, _dc_s, _dc_e
                    anchor_s_time = pd.Timestamp(df.at[ext_s, TIME_COL])
                    anchor_e_time = pd.Timestamp(df.at[ext_e, TIME_COL])
                    anchor_s_rel  = round((_ac_s + _dc_s - base_wh) / 1000.0, 4)
                    anchor_e_rel  = round((_ac_e + _dc_e - base_wh) / 1000.0, 4)

        if delta_energy is None and nominal_kwh is not None:
            delta_energy  = (delta_soc / 100.0) * nominal_kwh
            energy_source = 'soc_estimate'
            anchor_s_time = pd.Timestamp(df.at[soc_row_s, TIME_COL])
            anchor_e_time = pd.Timestamp(df.at[soc_row_e, TIME_COL])
            anchor_s_rel  = float('nan')
            anchor_e_rel  = float('nan')

        if delta_energy is None or delta_energy < min_energy_kwh or delta_energy <= 0:
            continue

        eff_cap = delta_energy / (delta_soc / 100.0)
        if cap_lo is not None and cap_hi is not None:
            if not (cap_lo <= eff_cap <= cap_hi):
                continue

        # ── delta_moving_kwh (separate, always >= 0) ─────────────────────
        delta_moving = None
        if len(mov_pos) > 0:
            idx_ms = int(np.searchsorted(mov_pos, soc_row_s, side='right')) - 1
            idx_me = int(np.searchsorted(mov_pos, soc_row_e, side='left'))
            if idx_ms < 0:
                idx_ms = 0
            if idx_me >= len(mov_pos):
                idx_me = len(mov_pos) - 1
            ext_ms = int(mov_pos[idx_ms])
            ext_me = int(mov_pos[idx_me])
            if ext_ms < ext_me:
                _mov_s = float(df.at[ext_ms, moving_energy_col])
                _mov_e = float(df.at[ext_me, moving_energy_col])
                _dm = (_mov_e - _mov_s) / 1000.0
                if _dm >= 0:
                    delta_moving = round(_dm, 3)

        # 充电类型
        if energy_source == 'ac_dc':
            thr = 0.5
            d_ac = (ac_e - ac_s) / 1000.0
            d_dc = (dc_e - dc_s) / 1000.0
            if d_ac >= thr and d_dc >= thr:
                charge_type = 'Mix charge'
            elif d_ac >= thr:
                charge_type = 'AC charge'
            else:
                charge_type = 'DC charge'
        else:
            charge_type = 'estimated'

        seg: dict = {
            'start_time':             pd.Timestamp(df.at[soc_row_s, TIME_COL]),
            'end_time':               pd.Timestamp(df.at[soc_row_e, TIME_COL]),
            'start_soc':              round(soc_s, 1),
            'end_soc':                round(soc_e, 1),
            'delta_soc_pct':          round(delta_soc, 1),    # positive
            'delta_energy_kwh':       round(delta_energy, 3), # positive
            'energy_source':          energy_source,
            'delta_moving_kwh':       delta_moving,
            'effective_capacity_kwh': round(eff_cap, 1),
            'charge_type':            charge_type,
            'ac_start_wh':            round(ac_s, 0) if ac_s is not None else None,
            'ac_end_wh':              round(ac_e, 0) if ac_e is not None else None,
            'dc_start_wh':            round(dc_s, 0) if dc_s is not None else None,
            'dc_end_wh':              round(dc_e, 0) if dc_e is not None else None,
            '_anchor_start_time':     anchor_s_time,
            '_anchor_end_time':       anchor_e_time,
            '_anchor_start_rel_kwh':  anchor_s_rel,
            '_anchor_end_rel_kwh':    anchor_e_rel,
        }

        if ODO_COL in df.columns:
            ob = df.loc[:soc_row_s, ODO_COL].dropna()
            oa = df.loc[soc_row_e:, ODO_COL].dropna()
            seg['odo_start_km'] = round(float(ob.iloc[-1]), 1) if len(ob) else None
            seg['odo_end_km']   = round(float(oa.iloc[0]),  1) if len(oa) else None

        for _c in ('latitude', 'longitude'):
            if _c in df.columns:
                vals = df.loc[soc_row_s:soc_row_e, _c].dropna()
                seg[_c] = round(float(vals.mean()), 5) if len(vals) else None

        segments.append(seg)

    return segments

# =============================================================================
# 放电分段检测
# =============================================================================
def find_discharge_segments_by_soc(
    df_raw: pd.DataFrame,
    plateau_window_min: float = 60,
    soc_rise_abort_pct: float = 3.0,
    min_soc_drop: float = 10.0,
    min_energy_kwh: float = 2.0,
    cap_lo: float | None = None,
    cap_hi: float | None = None,
    total_energy_col: str = TOTAL_ENERGY_COL,
    moving_energy_col: str = MOVING_COL,
    nominal_kwh: float | None = None,
    min_trip_distance_km: float = 0.0,
) -> list[dict]:
    """
    从稀疏原始遥测数据中检测放电/行驶分段（SOC 持续下降段）。

    能量来源优先级
    --------------
    1. total_energy_col（total_electric_energy_used_plugged_in_included）→ energy_source='total_energy'
    2. moving_energy_col（electric_energy_wheelbased_speed_over_zero）   → energy_source='moving_energy'
    3. SOC × nominal_kwh 估算                                            → energy_source='soc_estimate'

    返回字段（v2 统一 schema）
    -------------------------
    start_time, end_time, start_soc, end_soc,
    delta_soc_pct (负值，如 -25.0),
    delta_energy_kwh (负值，如 -80.0),
    energy_source,
    delta_moving_kwh (>= 0，或 None),
    effective_capacity_kwh,
    odo_start_km, odo_end_km, lat_start, lon_start, lat_end, lon_end

    临时字段（_ANCHOR_PRIVATE_KEYS，保存 CSV 前需过滤）：
    _anchor_start_time, _anchor_end_time,
    _anchor_start_rel_kwh, _anchor_end_rel_kwh

    参数
    ----
    min_trip_distance_km : float, default 0.0
        放电段最短里程过滤阈值（km）。若 (odo_end_km - odo_start_km) < 该值，
        则剔除该 segment。默认 0.0 表示不过滤，向后兼容。
        典型用途：mercedes_soc 上设为 10.0 抑制 depot/short-haul SOC 抖动造成
        的 EP outlier（短段 EP 噪声极大）。
    """
    if SOC_COL not in df_raw.columns or TIME_COL not in df_raw.columns:
        return []
    if df_raw.empty:
        return []

    df = df_raw.copy()
    df[TIME_COL] = pd.to_datetime(df[TIME_COL], errors='coerce', utc=True)
    df = df.dropna(subset=[TIME_COL]).sort_values(TIME_COL).reset_index(drop=True)

    plateau_ns = int(plateau_window_min * 60 * 1_000_000_000)

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

    soc_rows  = df.index[df['_soc'].notna()].tolist()
    if len(soc_rows) < 2:
        return []
    soc_vals  = df.loc[soc_rows, '_soc'].values.astype(float)
    soc_times = df.loc[soc_rows, TIME_COL].values.astype('datetime64[ns]')

    # Total energy arrays
    tot_vals = tot_times = None
    tot_base_wh = 0.0
    if has_total:
        tr = df.index[df['_tot'].notna()].tolist()
        if tr:
            tot_vals  = df.loc[tr, '_tot'].values.astype(float)
            tot_times = df.loc[tr, TIME_COL].values.astype('datetime64[ns]')
            tot_base_wh = float(tot_vals[0])

    # Moving energy arrays
    mov_vals = mov_times = None
    mov_base_wh = 0.0
    if has_moving:
        mr = df.index[df['_mov'].notna()].tolist()
        if mr:
            mov_vals  = df.loc[mr, '_mov'].values.astype(float)
            mov_times = df.loc[mr, TIME_COL].values.astype('datetime64[ns]')
            mov_base_wh = float(mov_vals[0])

    # Odometer
    odo_rows  = df.index[df['_odo'].notna()].tolist()
    odo_vals  = df.loc[odo_rows, '_odo'].values.astype(float) if odo_rows else np.array([])
    odo_times = (df.loc[odo_rows, TIME_COL].values.astype('datetime64[ns]')
                 if odo_rows else np.array([], dtype='datetime64[ns]'))
    n_soc = len(soc_rows)

    def _at_or_before(tarr, varr, t):
        if tarr is None or not len(tarr):
            return -1, np.nan
        pos = int(np.searchsorted(tarr, t, side='right')) - 1
        return (pos, float(varr[pos])) if pos >= 0 else (-1, np.nan)

    def _at_or_after(tarr, varr, t):
        if tarr is None or not len(tarr):
            return -1, np.nan
        pos = int(np.searchsorted(tarr, t, side='left'))
        return (pos, float(varr[pos])) if pos < len(tarr) else (-1, np.nan)

    # ── SOC 下降块检测 ────────────────────────────────────────────────────────
    soc_diff  = np.diff(soc_vals)
    declining = np.concatenate([[False], soc_diff < 0])
    blocks: list[list[int]] = []
    i = 1
    while i < n_soc:
        if declining[i]:
            s = i
            while i < n_soc and declining[i]:
                i += 1
            blocks.append([s, i - 1])
        else:
            i += 1

    if not blocks:
        return []

    # ── 合并相邻块 ────────────────────────────────────────────────────────────
    merged = [blocks[0][:]]
    for blk in blocks[1:]:
        prev_end = merged[-1][1]
        gap_ns   = int(soc_times[blk[0]] - soc_times[prev_end])
        max_rise = max(
            (soc_vals[j] - soc_vals[j - 1] for j in range(prev_end + 1, blk[0])),
            default=0.0,
        )
        if gap_ns <= plateau_ns and max_rise < soc_rise_abort_pct:
            merged[-1][1] = blk[1]
        else:
            merged.append(blk[:])

    # ── 计算分段指标 ──────────────────────────────────────────────────────────
    segments: list[dict] = []
    for blk_start, blk_end in merged:
        i_s = blk_start - 1
        i_e = blk_end
        t_s          = soc_times[i_s]
        t_e          = soc_times[i_e]
        soc_s        = float(soc_vals[i_s])
        soc_e        = float(soc_vals[i_e])
        delta_soc_signed = soc_e - soc_s    # negative for discharge
        delta_soc_abs    = soc_s - soc_e    # positive (drop magnitude)

        if delta_soc_abs < min_soc_drop or delta_soc_abs <= 0:
            continue

        # ── delta_energy_kwh: total → moving → SOC estimate ──────────────
        delta_energy_kwh = None
        energy_source    = None
        anchor_s_time = anchor_e_time = None
        anchor_s_rel = anchor_e_rel = float('nan')

        # 1. Total energy col (preferred)
        if tot_vals is not None:
            pos_s, e_s = _at_or_before(tot_times, tot_vals, t_s)
            pos_e, e_e = _at_or_after(tot_times, tot_vals, t_e)
            if (pos_s >= 0 and pos_e >= 0
                    and not np.isnan(e_s) and not np.isnan(e_e)):
                _raw = (e_e - e_s) / 1000.0
                if _raw > 0:
                    delta_energy_kwh = -_raw
                    energy_source    = 'total_energy'
                    anchor_s_time    = pd.Timestamp(tot_times[pos_s])
                    anchor_e_time    = pd.Timestamp(tot_times[pos_e])
                    anchor_s_rel     = round((e_s - tot_base_wh) / 1000.0, 4)
                    anchor_e_rel     = round((e_e - tot_base_wh) / 1000.0, 4)

        # 2. Moving energy col (fallback)
        if delta_energy_kwh is None and mov_vals is not None:
            pos_s, e_s = _at_or_before(mov_times, mov_vals, t_s)
            pos_e, e_e = _at_or_after(mov_times, mov_vals, t_e)
            if (pos_s >= 0 and pos_e >= 0
                    and not np.isnan(e_s) and not np.isnan(e_e)):
                _raw = (e_e - e_s) / 1000.0
                if _raw > 0:
                    delta_energy_kwh = -_raw
                    energy_source    = 'moving_energy'
                    anchor_s_time    = pd.Timestamp(mov_times[pos_s])
                    anchor_e_time    = pd.Timestamp(mov_times[pos_e])
                    anchor_s_rel     = round((e_s - mov_base_wh) / 1000.0, 4)
                    anchor_e_rel     = round((e_e - mov_base_wh) / 1000.0, 4)

        # 3. SOC estimate (last resort)
        if delta_energy_kwh is None and nominal_kwh is not None:
            delta_energy_kwh = (delta_soc_signed / 100.0) * nominal_kwh  # negative
            energy_source    = 'soc_estimate'
            anchor_s_time    = pd.Timestamp(t_s)
            anchor_e_time    = pd.Timestamp(t_e)
            anchor_s_rel     = float('nan')
            anchor_e_rel     = float('nan')

        if delta_energy_kwh is None:
            continue
        if abs(delta_energy_kwh) < min_energy_kwh or delta_energy_kwh >= 0:
            continue

        eff_cap = abs(delta_energy_kwh) / (delta_soc_abs / 100.0)
        if cap_lo is not None and cap_hi is not None:
            if not (cap_lo <= eff_cap <= cap_hi):
                continue

        # ── delta_moving_kwh (always >= 0, separate from primary energy) ─
        delta_moving = None
        if mov_vals is not None:
            pos_ms, e_ms = _at_or_before(mov_times, mov_vals, t_s)
            pos_me, e_me = _at_or_after(mov_times, mov_vals, t_e)
            if pos_ms >= 0 and pos_me >= 0:
                _dm = (e_me - e_ms) / 1000.0
                if _dm > 0:
                    delta_moving = round(_dm, 3)

        _, odo_s = _at_or_before(odo_times, odo_vals, t_s)
        _, odo_e = _at_or_after(odo_times, odo_vals, t_e)

        has_latlon = 'latitude' in df.columns and 'longitude' in df.columns
        if has_latlon:
            srow_s = soc_rows[i_s]
            srow_e = soc_rows[i_e]
            win    = df.loc[srow_s:srow_e]
            lat_v  = win['latitude'].dropna()
            lon_v  = win['longitude'].dropna()
            lat_s = round(float(lat_v.iloc[0]),  6) if len(lat_v) else None
            lon_s = round(float(lon_v.iloc[0]),  6) if len(lon_v) else None
            lat_e = round(float(lat_v.iloc[-1]), 6) if len(lat_v) else None
            lon_e = round(float(lon_v.iloc[-1]), 6) if len(lon_v) else None
        else:
            lat_s = lon_s = lat_e = lon_e = None

        segments.append({
            'start_time':             pd.Timestamp(t_s),
            'end_time':               pd.Timestamp(t_e),
            'start_soc':              round(soc_s,    2),
            'end_soc':                round(soc_e,    2),
            'delta_soc_pct':          round(delta_soc_signed, 2),  # negative
            'delta_energy_kwh':       round(delta_energy_kwh, 3),  # negative
            'energy_source':          energy_source,
            'delta_moving_kwh':       delta_moving,
            'effective_capacity_kwh': round(eff_cap, 1),
            'odo_start_km':           round(odo_s, 3) if np.isfinite(odo_s) else None,
            'odo_end_km':             round(odo_e, 3) if np.isfinite(odo_e) else None,
            'lat_start':              lat_s,
            'lon_start':              lon_s,
            'lat_end':                lat_e,
            'lon_end':                lon_e,
            '_anchor_start_time':     anchor_s_time,
            '_anchor_end_time':       anchor_e_time,
            '_anchor_start_rel_kwh':  anchor_s_rel,
            '_anchor_end_rel_kwh':    anchor_e_rel,
        })

    # ── 最短里程过滤（per-pipeline 可选；默认 0.0 = 不过滤，向后兼容）─────────
    # 目的：抑制 depot/short-haul 抖动造成的 EP outlier（短段 EP 噪声极大）。
    # 在所有 segments 形成之后做后置 filter，能精确统计 drop 数。
    if min_trip_distance_km > 0.0 and segments:
        _kept: list[dict] = []
        _drops: list[float] = []
        for _seg in segments:
            _o_s = _seg.get('odo_start_km')
            _o_e = _seg.get('odo_end_km')
            if _o_s is None or _o_e is None:
                # 无 odo 信息时不应用 distance filter（避免误删）
                _kept.append(_seg)
                continue
            _dist = float(_o_e) - float(_o_s)
            if _dist < min_trip_distance_km:
                _drops.append(_dist)
                continue
            _kept.append(_seg)
        if _drops:
            logger.info(
                '  最短里程过滤: 剔除 %d 段 distance < %.2f km '
                '(被剔除距离 km: %s)',
                len(_drops), min_trip_distance_km,
                ', '.join(f'{d:.2f}' for d in _drops),
            )
        segments = _kept

    return segments


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


# =============================================================================
# 验证图绘制（需要 matplotlib）
# =============================================================================
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import matplotlib.colors as mcolors
    from matplotlib.patches import Patch
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

_CHARGE_COLOR    = '#2ca02c'
_DISCHARGE_COLOR = '#d62728'
# v2.2.4: figure enlarged from (13, 7) so the doubled fonts (see below) keep
# clear of one another and of the tick labels under ``tight_layout``.
_FIGURE_SIZE     = (18, 10)
_DPI             = 150
# In-figure font sizes were doubled in v2.2.4 so the static PNG reads at roughly
# 2x the previous scale. Only the *chrome* — axis titles / ticks / sub-titles /
# legends — is baked into the PNG at these sizes. Later within v2.2.4 every rounded-bbox
# *data label* (Panel-1 dSOC, Panel-2/3 energy + charger-meter deltas, Panel-3
# recuperation deltas, Panel-4 mass labels) is stripped from the PNG and exported
# to a sidecar JSON, then rendered as an interactive HTML overlay (see
# ``plot_leg_validation(export_dsoc_overlay=...)``); their size is then governed by
# the viewer CSS, not by these constants.
_LABEL_FONT      = 20
_TICK_FONT       = 16
# Unified legend font across all four subplots. v2.2.6: scaled to ~0.6x the
# previous 18 pt so the baked-in legends sit more discreetly over the data lines
# (axis titles ``_LABEL_FONT`` left unchanged — only the legends were requested).
_LEGEND_FONT     = 11
# Baked-text size for the rounded-bbox data labels — only used when they are NOT
# externalised (``export_dsoc_overlay=False`` — e.g. the finetune comparison path).
_DSOC_FONT       = 14
_DATE_FMT        = '%d %b\n%H:%M'


def _to_utc(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t if t.tzinfo is not None else t.tz_localize('UTC')


def _build_energy_series(df_raw: pd.DataFrame, *cols):
    """返回 (times_np, values_np)：相对腿起点归零，单位 kWh。"""
    sub = df_raw[[TIME_COL] + list(cols)].copy()
    for c in cols:
        sub[c] = pd.to_numeric(sub[c], errors='coerce')
    sub = sub.dropna(subset=list(cols)).sort_values(TIME_COL)
    if len(sub) < 2:
        return None, None
    combined = sub[list(cols)].sum(axis=1)
    base = combined.iloc[0]
    return sub[TIME_COL].values, ((combined - base) / 1000.0).values


_TEXT_BBOX = dict(boxstyle='round,pad=0.15', fc='white', ec='none', alpha=0.75)


def _overlay(ax, df_seg: pd.DataFrame, color: str, kwh_col: str | None = None,
             *, span_alpha: float = 0.12, line_alpha: float = 0.85,
             label_prefix: str = '', y_offset_frac: float = 0.0,
             z_base: int = 1, seg_prefix: str = '', panel: int | None = None):
    """在 ax 上叠加分段区间（阴影 + 竖线 + 可选 SOC 标注）。

    参数
    ----
    span_alpha : axvspan 透明度（base segs 默认 0.12；overlay 默认 0.40）
    line_alpha : axvline 透明度
    label_prefix : annotation 文本前缀（overlay 用 '[FT] ' 做区分）
    y_offset_frac : annotation 纵向位移比例（相对 y 轴范围，overlay 上移 ~10%）
    z_base : axvspan / axvline 的 zorder 基准（overlay 用更大值盖在上面）

    Note: the dSOC label (when ``kwh_col`` is set) is always drawn with a rounded
    ``_TEXT_BBOX`` background. In the interactive-overlay export path
    (``export_dsoc_overlay=True``) the generic post-draw collector
    :func:`_export_overlay_boxes` strips every such bbox label from the PNG and
    re-emits it as an HTML overlay; in the legacy path it stays baked in.
    """
    # 计算 y 轴范围以便 offset
    ylim = ax.get_ylim()
    y_span = ylim[1] - ylim[0] if ylim[1] > ylim[0] else 1.0
    y_shift = y_offset_frac * y_span

    for idx, (_, row) in enumerate(df_seg.iterrows()):
        t_s = _to_utc(row['start_time'])
        t_e = _to_utc(row['end_time'])
        ax.axvspan(t_s, t_e, alpha=span_alpha, color=color, zorder=z_base)
        ax.axvline(t_s, color=color, lw=2.0, linestyle='--', alpha=line_alpha,
                   zorder=z_base + 1)
        ax.axvline(t_e, color=color, lw=2.0, linestyle=':',  alpha=line_alpha,
                   zorder=z_base + 1)
        if kwh_col is not None:
            # ``row.get(..., nan)`` 在值为 ``None`` 时不会触发 default，
            # 因此需要显式把 None / 空字符串转 NaN（xlsx 反推的 overlay segs
            # 里部分字段可能为空，见 :func:`reconstruct_segs_from_xlsx`）。
            def _f(val, default=float('nan')):
                if val is None or val == '':
                    return default
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return default
            dsoc = _f(row.get('delta_soc_pct'))
            kwh = _f(row.get(kwh_col))
            eff = _f(row.get('effective_capacity_kwh'))
            mid_t = t_s + (t_e - t_s) / 2
            # 交替上下放置，避免相邻段文字重叠
            end_soc = _f(row.get('end_soc'), 50.0)
            start_soc = _f(row.get('start_soc'), end_soc)
            if idx % 2 == 0:
                y_pos = min(max(start_soc, end_soc) + 3, 105)
                va = 'bottom'
            else:
                y_pos = max(min(start_soc, end_soc) - 3, 5)
                va = 'top'
            # Overlay 纵向错开：y_shift 正值表示向上推（bottom 位置向上，top 位置
            # 也向上），clamp 到 [0, 110] 防止越界
            y_pos = max(0, min(y_pos + y_shift, 110))
            lines = [f'dSOC={dsoc:+.0f}%']
            if not np.isnan(kwh):
                lines.append(f'{kwh:+.1f} kWh')
            if not np.isnan(eff):
                lines.append(f'C={eff:.0f} kWh')
            # energy performance for discharge (delta_soc < 0)
            if not np.isnan(dsoc) and dsoc < 0:
                try:
                    odo_s = row.get('odo_start_km')
                    odo_e = row.get('odo_end_km')
                    if odo_s is not None and odo_e is not None:
                        dist = float(odo_e) - float(odo_s)
                        if dist > 0 and not np.isnan(kwh):
                            ep = abs(kwh) / dist
                            lines.append(f'EP={ep:.3f} kWh/km')
                except (TypeError, ValueError):
                    pass
            text_body = '\n'.join(lines)
            if label_prefix:
                text_body = f'{label_prefix} ' + text_body
            _t = ax.text(mid_t, y_pos, text_body,
                         ha='center', va=va, fontsize=_DSOC_FONT, color=color,
                         bbox=_TEXT_BBOX, zorder=8)
            # v2.2.6: tag the Panel-1 dSOC block as the segment's ``info`` label so
            # the interactive viewer can route it to the pinned info box on hover.
            if seg_prefix and panel is not None:
                _t.set_gid(f'{seg_prefix}{idx}|p{panel}|info')


def _mark_anchors_stored(
    ax,
    df_seg: pd.DataFrame,
    color: str,
    *,
    label_prefix: str = '',
    y_offset_frac: float = 0.0,
    z_base: int = 5,
    seg_prefix: str = '',
    panel: int | None = None,
):
    """
    在能量子图上标注算法记录的锚点（▼▲）及 delta 虚线。

    NaN 锚点（soc_estimate 情况或 finetune overlay 缺失原始累计数据时）自动跳过。

    参数
    ----
    label_prefix : 文字前缀（overlay 用 ``'[FT]'``），空字符串表示无前缀（原图风格）
    y_offset_frac : 文字纵向偏移比例（相对 y 轴范围），overlay 用正值向上错开避免
        压到原始标注。triangles 本身不偏移，只有文字位置偏移。
    z_base : 三角形和虚线的 zorder 基准（overlay 用更大值盖在原图之上）
    """
    if df_seg.empty or '_anchor_start_time' not in df_seg.columns:
        return
    ylim = ax.get_ylim()
    y_span = ylim[1] - ylim[0] if ylim[1] > ylim[0] else 1.0
    y_shift = y_offset_frac * y_span
    for idx, (_, row) in enumerate(df_seg.iterrows()):
        t_s_raw = row.get('_anchor_start_time')
        t_e_raw = row.get('_anchor_end_time')
        v_s = float(row.get('_anchor_start_rel_kwh', float('nan')))
        v_e = float(row.get('_anchor_end_rel_kwh',   float('nan')))
        if t_s_raw is None or t_e_raw is None or np.isnan(v_s) or np.isnan(v_e):
            continue
        t_s = _to_utc(t_s_raw)
        t_e = _to_utc(t_e_raw)
        delta_raw = row.get('delta_energy_kwh', v_e - v_s)
        try:
            delta = float(delta_raw) if delta_raw is not None \
                and delta_raw != '' else v_e - v_s
        except (TypeError, ValueError):
            delta = v_e - v_s
        ax.scatter(t_s, v_s, marker='v', s=60, color=color, zorder=z_base,
                   edgecolors='white', linewidths=1.0)
        ax.scatter(t_e, v_e, marker='^', s=60, color=color, zorder=z_base,
                   edgecolors='white', linewidths=1.0)
        ax.plot([t_s, t_e], [v_s, v_s],
                color=color, lw=2.0, linestyle='--', alpha=0.85,
                zorder=z_base - 1)
        ax.plot([t_e, t_e], [v_s, v_e],
                color=color, lw=1.6, linestyle=':', alpha=0.8,
                zorder=z_base - 1)
        mid_t = t_s + (t_e - t_s) / 2
        text_body = f'{delta:+.1f}kWh'
        if label_prefix:
            text_body = f'{label_prefix} ' + text_body
        _t = ax.text(mid_t, v_s + y_shift, text_body,
                     ha='center', va='bottom', fontsize=13, color=color,
                     fontweight='bold', bbox=_TEXT_BBOX, zorder=z_base + 3)
        if seg_prefix and panel is not None:
            _t.set_gid(f'{seg_prefix}{idx}|p{panel}|value')


def _annotate_overlay_energy_delta(
    ax, df_seg: pd.DataFrame, color: str,
    *,
    label_prefix: str = '[FT]',
    y_offset_frac: float = 0.10,
    fontsize: float = 12.0,
    seg_prefix: str = '',
    panel: int | None = None,
):
    """在能量子图（Panel 2 AC+DC delta / Panel 3 Total Energy Used）上
    为 overlay segments 标注 ``[FT] ±X.X kWh``。

    与 :func:`_mark_anchors_stored` 不同，overlay segs 由
    :func:`reconstruct_segs_from_xlsx` 从 xlsx 反推得到，没有内部锚点字段
    （``_anchor_*``），因此位置基于 ``start_time``/``end_time`` 的中点，
    并在 y 轴顶部附近以 ``y_offset_frac`` 比例错开避免压到原始标注。
    字体比原始小 0.5pt，颜色与 overlay shading 一致。
    """
    if df_seg is None or df_seg.empty:
        return
    ylim = ax.get_ylim()
    y_span = ylim[1] - ylim[0] if ylim[1] > ylim[0] else 1.0
    # overlay 标注放在段上方接近 y_max 的位置，向下偏移 y_offset_frac × span
    y_pos = ylim[1] - y_offset_frac * y_span
    for idx, (_, row) in enumerate(df_seg.iterrows()):
        t_s = _to_utc(row['start_time'])
        t_e = _to_utc(row['end_time'])
        _raw_kwh = row.get('delta_energy_kwh')
        if _raw_kwh is None or _raw_kwh == '':
            continue
        try:
            kwh = float(_raw_kwh)
        except (TypeError, ValueError):
            continue
        if np.isnan(kwh):
            continue
        mid_t = t_s + (t_e - t_s) / 2
        _t = ax.text(mid_t, y_pos, f'{label_prefix} {kwh:+.1f} kWh',
                     ha='center', va='top', fontsize=fontsize, color=color,
                     fontweight='bold', bbox=_TEXT_BBOX, zorder=9)
        if seg_prefix and panel is not None:
            _t.set_gid(f'{seg_prefix}{idx}|p{panel}|value')


def _parse_box_gid(gid):
    """Decode a label ``gid`` of the form ``"<seg>|p<panel>|<role>"`` into the
    ``(seg, panel, role)`` triple used by the interactive viewer.

    Returns ``(None, None, None)`` for any artist without a recognised gid
    (legacy / diesel labels, charger-meter session totals), which the viewer
    treats as always-visible, non-segment annotations.
    """
    if not gid or '|' not in gid:
        return None, None, None
    parts = gid.split('|')
    if len(parts) != 3:
        return None, None, None
    seg, panel_tok, role = parts
    try:
        panel = int(panel_tok.lstrip('p'))
    except (TypeError, ValueError):
        panel = None
    return (seg or None), panel, (role or None)


def _export_overlay_boxes(fig, soc_ax=None, seg_specs=None):
    """Collect **every** rounded-bbox data label across all panels and map each to
    figure-fraction coordinates (origin **top-left**, matching how an ``<img>`` is
    laid out in HTML). The collected text artists are **removed from the figure**
    so they are *not* baked into the saved PNG — they live only as the interactive
    HTML overlay.

    Detection is structural and future-proof: it walks ``fig.axes`` (primary axes
    *and* their twins) and picks out the text artists that carry a background patch
    (``t.get_bbox_patch() is not None`` — i.e. drawn with ``bbox=_TEXT_BBOX``).
    Chrome that is *not* a data label — axis titles, sub-titles, legends and tick
    labels — lives outside ``ax.texts`` (in ``ax.title`` / ``ax.{x,y}axis`` / the
    Legend), carries no bbox patch, and therefore stays baked in the PNG at 2x.

    Each output box carries ``x`` / ``y`` in [0, 1] (fraction of the saved PNG,
    from the left / top edge respectively), the alignment (``ha`` / ``va``) so the
    viewer can anchor the div, the multi-line ``text``, the CSS ``color`` and —
    when the artist was drawn with a ``set_gid`` tag (v2.2.6) — the owning
    ``seg`` / ``role`` / ``panel`` so the viewer can group a segment's labels.

    Return shape (v2.2.6):
      * ``soc_ax is None and seg_specs is None`` → a **flat list** of boxes
        (legacy behaviour; the diesel figure and any other caller stay
        byte-compatible and render via the viewer's back-compat path).
      * otherwise → a **dict** ``{"boxes": [...], "segments": [...],
        "soc_axis": {...}}`` driving the hover redesign, where:
          - ``segments`` is ``[{seg, x0, x1}]`` — each segment's figure-fraction
            x-range (full-height hover hotzones), mapped through the SAME
            transData→figure transform as the boxes;
          - ``soc_axis`` is the SOC panel's ``{x0, y0, x1, y1}`` in figure
            fraction, **top-left origin** — the anchor for the pinned info box.

    Must be called AFTER ``fig.canvas.draw()`` and with a layout that matches the
    saved-PNG extent (i.e. saved WITHOUT ``bbox_inches='tight'``), otherwise the
    fractions would not line up with the rendered image.
    """
    out: list[dict] = []
    inv = fig.transFigure.inverted()
    for ax in fig.axes:
        # Snapshot the list: ``t.remove()`` mutates ``ax.texts`` during iteration.
        for t in list(ax.texts):
            if t.get_bbox_patch() is None:
                continue
            try:
                # ``get_unitless_position()`` strips axis units (e.g. converts a
                # date x-coordinate to its date2num float), so ``get_transform()``
                # (transData of the owning axis, twins included) maps it straight
                # to display px. ``get_position()`` would return the raw Timestamp,
                # which ``transData`` cannot transform.
                disp = t.get_transform().transform(t.get_unitless_position())
                fx, fy = inv.transform(disp)
            except (TypeError, ValueError):
                continue
            if not (np.isfinite(fx) and np.isfinite(fy)):
                continue
            seg, panel, role = _parse_box_gid(t.get_gid())
            out.append({
                'x': round(float(fx), 5),
                # Flip vertically: matplotlib figure fraction is bottom-up, but an
                # HTML image positions from the top-down.
                'y': round(float(1.0 - fy), 5),
                'ha': t.get_ha(),
                'va': t.get_va(),
                'text': t.get_text(),
                'color': mcolors.to_hex(t.get_color()),
                'seg': seg,
                'role': role,
                'panel': panel,
            })
            # Strip from the PNG; the box now lives only as an HTML overlay div.
            t.remove()

    # Legacy / diesel callers (no extras) get the flat list unchanged.
    if soc_ax is None and seg_specs is None:
        return out

    # ── New schema: segment hotzone x-ranges + SOC-panel anchor box ──────────
    segments: list[dict] = []
    if seg_specs:
        for segid, t_s, t_e in seg_specs:
            try:
                x_s = soc_ax.transData.transform(
                    (mdates.date2num(t_s), 0.0))[0]
                x_e = soc_ax.transData.transform(
                    (mdates.date2num(t_e), 0.0))[0]
                fx0 = inv.transform((x_s, 0.0))[0]
                fx1 = inv.transform((x_e, 0.0))[0]
            except (TypeError, ValueError):
                continue
            if not (np.isfinite(fx0) and np.isfinite(fx1)):
                continue
            if fx1 < fx0:
                fx0, fx1 = fx1, fx0
            segments.append({
                'seg': segid,
                'x0': round(float(fx0), 5),
                'x1': round(float(fx1), 5),
            })

    soc_axis = None
    if soc_ax is not None:
        pos = soc_ax.get_position()  # figure-fraction Bbox, bottom-up origin
        soc_axis = {
            'x0': round(float(pos.x0), 5),
            'x1': round(float(pos.x1), 5),
            # Flip to top-left origin: top edge = 1 - y1, bottom edge = 1 - y0.
            'y0': round(float(1.0 - pos.y1), 5),
            'y1': round(float(1.0 - pos.y0), 5),
        }

    return {'boxes': out, 'segments': segments, 'soc_axis': soc_axis}


def cluster_mass_data(
    df_raw: pd.DataFrame,
    mass_col: str = MASS_COL,
    min_cluster_gap_kg: float = MIN_CLUSTER_GAP_KG,
    speed_col: str | None = None,
    speed_threshold_kmh: float = MOVING_SPEED_THRESHOLD_KMH,
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

    返回
    ----
    带有 ``mass_cluster``（int 或 NaN）与 ``mass_moving``（bool）两列的 df_raw **副本**。
    """
    df = df_raw.copy()
    df['mass_cluster'] = np.nan
    df['mass_moving'] = False

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


def plot_leg_validation(
    df_raw: pd.DataFrame,
    charge_segs: list[dict],
    discharge_segs: list[dict],
    reg: str,
    suffix: str,
    out_path,
    ac_col: str = AC_COL,
    dc_col: str = DC_COL,
    panel3_col: str = MOVING_COL,
    mass_col: str = MASS_COL,
    speed_col: str = 'wheel_based_speed',
    logger_speed_df: pd.DataFrame | None = None,
    logger_mass_df: pd.DataFrame | None = None,
    charger_meter_df: pd.DataFrame | None = None,
    mass_from_logger: bool = False,
    mass_agg: str = 'mean',
    *,
    overlay_charge_segs: list[dict] | None = None,
    overlay_discharge_segs: list[dict] | None = None,
    overlay_label_prefix: str = '[FT]',
    overlay_color_discharge: str = '#FF9933',
    overlay_color_charge: str = '#00CCCC',
    export_dsoc_overlay: bool = False,
) -> None:
    """
    为一条腿生成四面板验证图，保存为 PNG。

    Panel 1 (SOC + Speed)         — SOC 左轴，Speed 右轴（Telematics + 可选 Logger）
    Panel 2 (AC+DC Delta)         — 累计充电能量折线 + 充电锚点 ▼▲
    Panel 3 (Discharge Energy)    — panel3_col 累计 delta 折线 + 放电锚点 ▼▲
    Panel 4 (Vehicle Mass)        — mass_col 时序散点（kg） + 可选 Logger CVW，段阴影叠加

    Overlay（v2.2.4 新增）：
    当 ``overlay_charge_segs`` / ``overlay_discharge_segs`` 非空时，在 base
    segment shading（红 / 绿）之上叠加第二套 shading（默认橙 / 青），用于
    finetune 前后对比。overlay annotations 加 ``overlay_label_prefix``（默认
    ``[FT]``）前缀，纵向错开避免重叠。legend 扩展为 4 项（Original charge /
    Original discharge / Finetuned charge / Finetuned discharge）。
    当两个 overlay 参数都为 None 时，函数行为与 v2.2.3 完全一致（向后兼容）。

    Interactive overlay (``export_dsoc_overlay``, introduced and later generalised within v2.2.4):
    when ``True``, **every** rounded-bbox data label across all four panels — the
    Panel-1 ``dSOC=...`` boxes, the Panel-2/3 ``±X kWh`` energy deltas and
    charger-meter total, the Panel-3 recuperation deltas, and the Panel-4 mass
    labels — is **not** baked into the PNG. After the layout is finalised they are
    collected (:func:`_export_overlay_boxes`), converted to figure-fraction
    coordinates (0–1, origin top-left), removed from the figure, and written to a
    sidecar ``<png-stem>.boxes.json`` next to the PNG, so the HTML viewer can render
    them as hover-reactive overlay ``<div>``s. To keep the figure-fraction →
    saved-pixel mapping exact, this mode saves WITHOUT ``bbox_inches='tight'``
    (which would crop the whitespace and shift the mapping); ``tight_layout()``
    still prevents overlap. When ``False`` (default, e.g. the finetune comparison
    path) all labels stay baked into the PNG.
    """
    if not _HAS_MPL:
        warnings.warn('matplotlib not available; skipping validation figure')
        return

    df_c = pd.DataFrame(charge_segs)
    df_d = pd.DataFrame(discharge_segs)

    # Overlay (v2.2.4): 额外的 finetuned segs，用不同色相叠加在 base 之上
    _has_overlay = (overlay_charge_segs is not None or
                     overlay_discharge_segs is not None)
    df_oc = pd.DataFrame(overlay_charge_segs) if overlay_charge_segs else pd.DataFrame()
    df_od = pd.DataFrame(overlay_discharge_segs) if overlay_discharge_segs else pd.DataFrame()

    df_r = df_raw.copy()
    df_r[TIME_COL] = pd.to_datetime(df_r[TIME_COL], errors='coerce', utc=True)
    df_r = df_r.dropna(subset=[TIME_COL]).sort_values(TIME_COL)
    df_r[SOC_COL] = pd.to_numeric(df_r[SOC_COL], errors='coerce')
    df_r.loc[df_r[SOC_COL] == 0, SOC_COL] = np.nan
    soc_rows = df_r[df_r[SOC_COL].notna()].sort_values(TIME_COL)
    if len(soc_rows) < 2:
        return

    has_acdc = {ac_col, dc_col}.issubset(df_r.columns)
    t2, v2   = _build_energy_series(df_r, ac_col, dc_col) if has_acdc else (None, None)
    t3, v3   = (_build_energy_series(df_r, panel3_col)
                if panel3_col in df_r.columns else (None, None))

    if panel3_col == TOTAL_ENERGY_COL:
        ylabel3 = 'Total Energy\nUsed Delta (kWh)'
    elif panel3_col == MOVING_COL:
        ylabel3 = 'Moving Energy\nDelta (kWh)'
    else:
        ylabel3 = f'{panel3_col[:15]}\nDelta (kWh)'

    fig, (ax1, ax2, ax3, ax4) = plt.subplots(
        4, 1, figsize=(_FIGURE_SIZE[0], _FIGURE_SIZE[1] + 2), sharex=True,
        gridspec_kw={'height_ratios': [2.4, 1, 1, 1.6]},
    )

    # ── Panel 1: SOC ──────────────────────────────────────────────────────────
    ax1.plot(soc_rows[TIME_COL], soc_rows[SOC_COL],
             color='#555555', lw=1.6, alpha=0.8)
    ax1.scatter(soc_rows[TIME_COL], soc_rows[SOC_COL],
                color='#555555', s=6, alpha=0.6, zorder=2)
    if not df_d.empty:
        _overlay(ax1, df_d, _DISCHARGE_COLOR, kwh_col='delta_energy_kwh',
                 seg_prefix='d', panel=1)
    if not df_c.empty:
        _overlay(ax1, df_c, _CHARGE_COLOR,    kwh_col='delta_energy_kwh',
                 seg_prefix='c', panel=1)
    # Overlay (finetuned) — 用不同色相 + 更深 alpha + 纵向错开 annotations
    if _has_overlay:
        if not df_od.empty:
            _overlay(ax1, df_od, overlay_color_discharge,
                     kwh_col='delta_energy_kwh',
                     span_alpha=0.40, line_alpha=0.95,
                     label_prefix=overlay_label_prefix,
                     y_offset_frac=0.10, z_base=2,
                     seg_prefix='od', panel=1)
        if not df_oc.empty:
            _overlay(ax1, df_oc, overlay_color_charge,
                     kwh_col='delta_energy_kwh',
                     span_alpha=0.40, line_alpha=0.95,
                     label_prefix=overlay_label_prefix,
                     y_offset_frac=0.10, z_base=2,
                     seg_prefix='oc', panel=1)
    # ── Panel 1 右轴：Speed ──────────────────────────────────────────────
    ax1_speed = ax1.twinx()
    _tele_speed_plotted = False
    _logger_speed_plotted = False
    if speed_col in df_r.columns:
        spd = pd.to_numeric(df_r[speed_col], errors='coerce').fillna(0.0)
        ax1_speed.plot(df_r[TIME_COL], spd,
                       color='#1565C0', lw=1.0, alpha=0.7)
        _tele_speed_plotted = True
    if logger_speed_df is not None and not logger_speed_df.empty:
        ax1_speed.plot(logger_speed_df.index, logger_speed_df.iloc[:, 0],
                       color='#E65100', lw=1.0, alpha=0.8)
        _logger_speed_plotted = True
    if _tele_speed_plotted or _logger_speed_plotted:
        ax1_speed.set_ylabel('Speed (km/h)', fontsize=_LABEL_FONT, color='#1565C0')
        ax1_speed.tick_params(axis='y', labelcolor='#1565C0', labelsize=_TICK_FONT)
        # 固定 0–100 km/h：全项目 speed 轴一致标准，便于不同 leg 之间对比
        ax1_speed.set_ylim(0, 100)
    else:
        ax1_speed.set_yticks([])

    if _has_overlay:
        legend_items = [
            Patch(color=_CHARGE_COLOR, alpha=0.6,
                  label=f'Original charge ({len(df_c)} segs)'),
            Patch(color=_DISCHARGE_COLOR, alpha=0.6,
                  label=f'Original discharge ({len(df_d)} segs)'),
            Patch(color=overlay_color_charge, alpha=0.7,
                  label=f'Finetuned charge ({len(df_oc)} segs)'),
            Patch(color=overlay_color_discharge, alpha=0.7,
                  label=f'Finetuned discharge ({len(df_od)} segs)'),
        ]
    else:
        legend_items = [
            Patch(color=_CHARGE_COLOR,    alpha=0.6,
                  label=f'Charge ({len(df_c)} segs)'),
            Patch(color=_DISCHARGE_COLOR, alpha=0.6,
                  label=f'Discharge/Trip ({len(df_d)} segs)'),
        ]
    if _tele_speed_plotted or _logger_speed_plotted:
        from matplotlib.lines import Line2D
        legend_items.append(Line2D([0], [0], color='#1565C0', lw=2, alpha=0.8, label='Telematics Speed'))
        if _logger_speed_plotted:
            legend_items.append(Line2D([0], [0], color='#E65100', lw=2, alpha=0.8, label='Logger Speed'))
    ax1.legend(handles=legend_items, fontsize=_LEGEND_FONT, loc='upper right')
    ax1.set_ylabel('SOC (%)', fontsize=_LABEL_FONT)
    ax1.set_ylim(0, 110)
    ax1.grid(True, alpha=0.3)
    ax1.set_title(f'{reg}  {suffix}  [Segment Validation]', fontsize=_LABEL_FONT)

    # ── Panel 2: AC+DC 累计 delta + 充电锚点 ──────────────────────────────────
    if t2 is not None:
        ax2.plot(t2, v2, color=_CHARGE_COLOR, lw=1.8, alpha=0.9)
    if not df_d.empty:
        _overlay(ax2, df_d, _DISCHARGE_COLOR)
    if not df_c.empty:
        _overlay(ax2, df_c, _CHARGE_COLOR)
        _mark_anchors_stored(ax2, df_c, _CHARGE_COLOR, seg_prefix='c', panel=2)
    if _has_overlay:
        if not df_od.empty:
            _overlay(ax2, df_od, overlay_color_discharge,
                     span_alpha=0.40, line_alpha=0.95, z_base=2)
        if not df_oc.empty:
            _overlay(ax2, df_oc, overlay_color_charge,
                     span_alpha=0.40, line_alpha=0.95, z_base=2)
            # 充电段 overlay 的 ▼▲ 锚点（在 AC+DC 累计曲线上）+ `[FT] +XX.X kWh`。
            # 锚点由 reconstruct_segs_from_xlsx → attach_anchors_from_df 从 df_raw
            # 线性插值得出，风格与原 production 图（_mark_anchors_stored）完全一致。
            # 若 overlay segs 缺失 _anchor_* 字段（向后兼容），退化为顶部文字标注。
            if '_anchor_start_time' in df_oc.columns:
                _mark_anchors_stored(
                    ax2, df_oc, overlay_color_charge,
                    label_prefix=overlay_label_prefix,
                    y_offset_frac=0.05, z_base=6,
                    seg_prefix='oc', panel=2,
                )
            else:
                _annotate_overlay_energy_delta(
                    ax2, df_oc, overlay_color_charge,
                    label_prefix=overlay_label_prefix, y_offset_frac=0.10,
                    seg_prefix='oc', panel=2,
                )
    ax2.set_ylabel('AC+DC Delta\n(kWh)', fontsize=_LABEL_FONT)
    ax2.set_ylim(bottom=0)
    ax2.grid(True, alpha=0.3)
    # ── Panel 2 右轴：Charger Meter ─────────────────────────────────────
    if charger_meter_df is not None and not charger_meter_df.empty:
        from matplotlib.lines import Line2D
        ax2_r = ax2.twinx()
        meter_vals = charger_meter_df['meter_kwh'].values
        meter_times = charger_meter_df.index
        # 归一化：从 0 开始（减去首个读数）
        meter_base = meter_vals[0] if len(meter_vals) else 0.0
        meter_normed = meter_vals - meter_base
        ax2_r.plot(meter_times, meter_normed,
                   color='#6A1B9A', lw=2.4, alpha=0.9, marker='o', markersize=4)
        ax2_r.set_ylabel('Charger Meter\n(kWh)', fontsize=_LABEL_FONT, color='#6A1B9A')
        ax2_r.tick_params(axis='y', labelcolor='#6A1B9A', labelsize=_TICK_FONT)
        ax2_r.set_ylim(bottom=0)
        # 标注充电桩总能量变化量（首个读数 → 末个读数）。用 ``ax.text`` 而非
        # ``ax.annotate``，使其与其余数据标注框一致，能被 _export_overlay_boxes
        # 统一收集为 HTML overlay。
        if len(meter_vals) >= 2:
            total_delta = meter_vals[-1] - meter_vals[0]
            mid_time = meter_times[0] + (meter_times[-1] - meter_times[0]) / 2
            mid_val = (meter_normed[0] + meter_normed[-1]) / 2
            ax2_r.text(mid_time, mid_val, f'{total_delta:+.1f} kWh',
                       fontsize=12, color='#6A1B9A', ha='center', va='bottom',
                       fontweight='bold', bbox=_TEXT_BBOX, zorder=8)
        # 图例
        legend_p2 = [
            Line2D([0], [0], color=_CHARGE_COLOR, lw=2, alpha=0.9, label='AC+DC Delta'),
            Line2D([0], [0], color='#6A1B9A', lw=2.4, alpha=0.9,
                   marker='o', markersize=4, label='Charger Meter'),
        ]
        ax2.legend(handles=legend_p2, fontsize=_LEGEND_FONT, loc='upper left')

    # ── Panel 3: 放电能量 delta + 再生回收能量 delta + 放电锚点 ────────────────
    _RECUP_PLOT_COLOR = '#2E7D32'  # 深绿色区分再生回收
    if t3 is not None:
        ax3.plot(t3, v3, color=_DISCHARGE_COLOR, lw=1.8, alpha=0.9,
                 label='Total Energy Used')
    if not df_d.empty:
        _overlay(ax3, df_d, _DISCHARGE_COLOR)
        _mark_anchors_stored(ax3, df_d, _DISCHARGE_COLOR, seg_prefix='d', panel=3)
    if not df_c.empty:
        _overlay(ax3, df_c, _CHARGE_COLOR)
    if _has_overlay:
        if not df_od.empty:
            _overlay(ax3, df_od, overlay_color_discharge,
                     span_alpha=0.40, line_alpha=0.95, z_base=2)
            # 放电段 overlay 的 ▼▲ 锚点（在 Total Energy Used 累计曲线上）+
            # `[FT] -XX.X kWh`。同 Panel 2，风格与原 production 图一致。
            # 向后兼容：缺 _anchor_* 时退化为顶部文字。
            if '_anchor_start_time' in df_od.columns:
                _mark_anchors_stored(
                    ax3, df_od, overlay_color_discharge,
                    label_prefix=overlay_label_prefix,
                    y_offset_frac=0.05, z_base=6,
                    seg_prefix='od', panel=3,
                )
            else:
                _annotate_overlay_energy_delta(
                    ax3, df_od, overlay_color_discharge,
                    label_prefix=overlay_label_prefix, y_offset_frac=0.10,
                    seg_prefix='od', panel=3,
                )
        if not df_oc.empty:
            _overlay(ax3, df_oc, overlay_color_charge,
                     span_alpha=0.40, line_alpha=0.95, z_base=2)
    ax3.set_ylabel(ylabel3, fontsize=_LABEL_FONT)
    ax3.set_ylim(bottom=0)
    ax3.grid(True, alpha=0.3)

    # ── Panel 3 右 Y 轴：Recuperation Energy（归零化） ──────────────────────
    t_recup, v_recup = (_build_energy_series(df_r, RECUP_COL)
                        if RECUP_COL in df_r.columns else (None, None))
    if t_recup is not None and len(t_recup) > 1:
        ax3r = ax3.twinx()
        ax3r.plot(t_recup, v_recup, color=_RECUP_PLOT_COLOR, lw=1.8, alpha=0.9,
                  label='Recuperation Energy')
        ax3r.set_ylabel('Recuperation\nDelta (kWh)', fontsize=_LABEL_FONT,
                         color=_RECUP_PLOT_COLOR)
        ax3r.tick_params(axis='y', labelcolor=_RECUP_PLOT_COLOR, labelsize=_TICK_FONT)
        ax3r.set_ylim(bottom=0)
        # 在放电段锚点位置标注 recuperation 数据点
        if not df_d.empty and '_anchor_start_time' in df_d.columns:
            recup_idx = pd.DatetimeIndex(t_recup, tz='UTC')
            recup_s = pd.Series(v_recup, index=recup_idx)
            for _ridx, (_, row) in enumerate(df_d.iterrows()):
                t_s_raw = row.get('_anchor_start_time')
                t_e_raw = row.get('_anchor_end_time')
                if t_s_raw is None or t_e_raw is None:
                    continue
                t_s_a = _to_utc(t_s_raw)
                t_e_a = _to_utc(t_e_raw)
                # 找最近的 recup 数据点
                try:
                    idx_s = recup_s.index.searchsorted(t_s_a)
                    idx_e = recup_s.index.searchsorted(t_e_a)
                    if 0 < idx_s < len(recup_s) and 0 < idx_e < len(recup_s):
                        rs = recup_s.iloc[max(0, idx_s - 1):idx_s + 1].iloc[-1]
                        re = recup_s.iloc[max(0, idx_e - 1):idx_e + 1].iloc[-1]
                        delta_recup = re - rs
                        ax3r.scatter(t_s_a, rs, marker='v', s=40,
                                     color=_RECUP_PLOT_COLOR, zorder=5,
                                     edgecolors='white', linewidths=1.0)
                        ax3r.scatter(t_e_a, re, marker='^', s=40,
                                     color=_RECUP_PLOT_COLOR, zorder=5,
                                     edgecolors='white', linewidths=1.0)
                        mid_t = t_s_a + (t_e_a - t_s_a) / 2
                        _t = ax3r.text(mid_t, re, f'{delta_recup:+.1f}kWh',
                                       ha='center', va='bottom', fontsize=12,
                                       color=_RECUP_PLOT_COLOR, fontweight='bold',
                                       bbox=_TEXT_BBOX, zorder=8)
                        # recup delta belongs to the same discharge segment as the
                        # Panel-3 anchor (shares the ``d{idx}`` id across panels).
                        _t.set_gid(f'd{_ridx}|p3|value')
                except (IndexError, KeyError):
                    pass
        # 统一左右 Y 轴刻度：以 Total Energy Used（左轴）的范围为主，
        # Recuperation（右轴）使用相同范围，保证两条曲线直观可比。
        ymax_left  = ax3.get_ylim()[1]
        ymax_right = ax3r.get_ylim()[1]
        ymax_unified = max(ymax_left, ymax_right, 5.0)  # 至少 5 kWh
        ax3.set_ylim(0, ymax_unified)
        ax3r.set_ylim(0, ymax_unified)

        # 合并图例（左右轴）
        from matplotlib.lines import Line2D
        lines3_left = [Line2D([0], [0], color=_DISCHARGE_COLOR, lw=1.8, alpha=0.9,
                              label=ylabel3.replace('\n', ' '))]
        lines3_right = [Line2D([0], [0], color=_RECUP_PLOT_COLOR, lw=1.8, alpha=0.9,
                               label='Recuperation Delta')]
        ax3.legend(handles=lines3_left + lines3_right, fontsize=_LEGEND_FONT, loc='upper left')

    # ── Panel 4: Vehicle Mass ──────────────────────────────────────────────
    _tele_mass_plotted = False
    _logger_mass_plotted = False
    if mass_col in df_r.columns and not mass_from_logger:
        mass_s = pd.to_numeric(df_r[mass_col], errors='coerce')
        mask_m = mass_s.notna() & (mass_s > 0)
        if mask_m.any():
            ax4.scatter(df_r.loc[mask_m, TIME_COL], mass_s[mask_m],
                        s=6, color='#37474F', alpha=0.8, zorder=2)
            ax4.plot(df_r.loc[mask_m, TIME_COL], mass_s[mask_m],
                     color='#37474F', lw=1.4, alpha=0.7)
            _tele_mass_plotted = True
    if logger_mass_df is not None and not logger_mass_df.empty:
        ax4.plot(logger_mass_df.index, logger_mass_df.iloc[:, 0],
                 color='#E65100', lw=1.4, alpha=0.8, zorder=3)
        _logger_mass_plotted = True
    if not df_d.empty:
        _overlay(ax4, df_d, _DISCHARGE_COLOR)
    if not df_c.empty:
        _overlay(ax4, df_c, _CHARGE_COLOR)
    if _has_overlay:
        if not df_od.empty:
            _overlay(ax4, df_od, overlay_color_discharge,
                     span_alpha=0.40, line_alpha=0.95, z_base=2)
        if not df_oc.empty:
            _overlay(ax4, df_oc, overlay_color_charge,
                     span_alpha=0.40, line_alpha=0.95, z_base=2)
    # ── 每个分段的平均质量（虚线 + 标注）──────────────────────────────────────
    # v2.2.6: the Panel-4 segment mass now uses the SAME filter + aggregation as
    # the Excel "Vehicle Mass (kg)" column (report_builder._get_vehicle_mass):
    # window -> valid (>0) -> moving-only (speed > MOVING_SPEED_THRESHOLD_KMH,
    # falling back to all-valid when fewer than two moving samples), then `_agg_mass`
    # by the resolved `mass_agg` method. This keeps the figure annotation consistent
    # with the report value and, for vehicles configured with a robust method
    # (median / iqr_median), drops a transient GCW spike. The old `mass_cluster`
    # filter is no longer needed: the robust median already ignores a few
    # tractor-only low readings.
    def _telemetry_mass(t_s, t_e):
        """Return ``(sel, timestamps)`` — the filtered positive (moving-preferred)
        telemetry mass Series for a segment window and its index-aligned
        ``eventDatetime`` axis (for ``mad_tw_mean``) — or ``(None, None)`` when
        fewer than two samples remain."""
        if mass_col not in df_raw.columns:
            return None, None
        _times = pd.to_datetime(df_raw[TIME_COL], errors='coerce', utc=True)
        _win = (_times >= t_s) & (_times <= t_e)
        _vals = pd.to_numeric(df_raw.loc[_win, mass_col], errors='coerce')
        _valid = _vals.notna() & (_vals > 0)
        if speed_col in df_raw.columns:
            _spd = pd.to_numeric(df_raw.loc[_win, speed_col], errors='coerce')
            _moving = _valid & _spd.notna() & (_spd > MOVING_SPEED_THRESHOLD_KMH)
            if _moving.sum() >= 2:
                _valid = _moving
        _sel = _vals[_valid]
        if len(_sel) < 2:
            return None, None
        return _sel, _times.loc[_sel.index]

    _mean_mass_tele = False
    _mean_mass_logger = False
    for _df_seg, _col, _seg_pfx in ((df_d, _DISCHARGE_COLOR, 'd'),
                                    (df_c, _CHARGE_COLOR, 'c')):
        for _midx, (_, row) in enumerate(_df_seg.iterrows()):
            t_s = _to_utc(row['start_time'])
            t_e = _to_utc(row['end_time'])
            _seg_mass = None
            _from_logger = False
            # 优先使用遥测质量（与 Excel 列同口径过滤 + mass_agg 聚合）
            _sel, _sel_ts = _telemetry_mass(t_s, t_e)
            if _sel is not None:
                _mkg, _ = _agg_mass(_sel, mass_agg, timestamps=_sel_ts)
                if np.isfinite(_mkg):
                    _seg_mass = float(_mkg)
                    _from_logger = mass_from_logger
            # 回退：若遥测质量不可用，使用 Logger CVW（同样 mass_agg 聚合）
            if _seg_mass is None and logger_mass_df is not None and not logger_mass_df.empty:
                _log_slice = logger_mass_df.loc[t_s:t_e]
                if not _log_slice.empty:
                    _log_vals = pd.to_numeric(_log_slice.iloc[:, 0], errors='coerce').dropna()
                    _log_vals = _log_vals[_log_vals > 0]
                    if len(_log_vals) >= 2:
                        _mkg, _ = _agg_mass(_log_vals, mass_agg,
                                            timestamps=_log_vals.index.to_series())
                        if np.isfinite(_mkg):
                            _seg_mass = float(_mkg)
                            _from_logger = True
            if _seg_mass is not None:
                _ls = ':' if _from_logger else '--'
                ax4.plot([t_s, t_e], [_seg_mass, _seg_mass],
                         color=_col, lw=4.0, linestyle=_ls, alpha=0.9, zorder=5)
                _t = ax4.text(t_s + (t_e - t_s) / 2, _seg_mass,
                              f' {_seg_mass / 1000:.1f} t',
                              ha='center', va='bottom', fontsize=14,
                              color=_col, fontweight='bold',
                              bbox=_TEXT_BBOX, zorder=8)
                _t.set_gid(f'{_seg_pfx}{_midx}|p4|value')
                if _from_logger:
                    _mean_mass_logger = True
                else:
                    _mean_mass_tele = True
    # ── Overlay（v2.2.4+）：finetuned 段的 mean mass 横线 + `[FT] XX.X t` 标注 ──
    # 与 base 段同样的质量计算逻辑，但线 / 文字用 overlay color；线和文字都向上
    # 偏移 y_span 的 ~3% 避免遮挡 base 的同高度 dashed line（典型情况下 base 和
    # overlay 的 mean mass 非常接近，不偏移时橙 / 青线会完全盖住红 / 绿线）。
    # 文字额外再抬高一点与线错开。
    if _has_overlay:
        _y4_lim = ax4.get_ylim()
        _y4_span = _y4_lim[1] - _y4_lim[0] if _y4_lim[1] > _y4_lim[0] else 10000.0
        _y4_line_shift = 0.03 * _y4_span   # 线向上抬 ~3% 避免盖住 base
        _y4_text_shift = 0.08 * _y4_span   # 文字再抬 ~5% 避免压到原始 t 标注
        for _df_ov, _ov_col, _ov_pfx in ((df_od, overlay_color_discharge, 'od'),
                                         (df_oc, overlay_color_charge, 'oc')):
            if _df_ov is None or _df_ov.empty:
                continue
            for _midx, (_, row) in enumerate(_df_ov.iterrows()):
                t_s = _to_utc(row['start_time'])
                t_e = _to_utc(row['end_time'])
                _seg_mass = None
                _from_logger = False
                # 与 base 段同口径：window -> valid -> moving -> mass_agg 聚合
                _sel, _sel_ts = _telemetry_mass(t_s, t_e)
                if _sel is not None:
                    _mkg, _ = _agg_mass(_sel, mass_agg, timestamps=_sel_ts)
                    if np.isfinite(_mkg):
                        _seg_mass = float(_mkg)
                        _from_logger = mass_from_logger
                if (_seg_mass is None and logger_mass_df is not None
                        and not logger_mass_df.empty):
                    _log_slice = logger_mass_df.loc[t_s:t_e]
                    if not _log_slice.empty:
                        _log_vals = pd.to_numeric(
                            _log_slice.iloc[:, 0], errors='coerce').dropna()
                        _log_vals = _log_vals[_log_vals > 0]
                        if len(_log_vals) >= 2:
                            _mkg, _ = _agg_mass(_log_vals, mass_agg,
                                                timestamps=_log_vals.index.to_series())
                            if np.isfinite(_mkg):
                                _seg_mass = float(_mkg)
                                _from_logger = True
                if _seg_mass is None:
                    continue
                _ls = ':' if _from_logger else '--'
                # 线本身向上抬 _y4_line_shift，避免盖住 base 的同高度虚线
                _line_y = min(_seg_mass + _y4_line_shift, _y4_lim[1])
                ax4.plot([t_s, t_e], [_line_y, _line_y],
                         color=_ov_col, lw=4.0, linestyle=_ls,
                         alpha=0.9, zorder=6)
                # 文字位置比线再高一点，避免覆盖原始段的 t 标注
                _label_y = min(_seg_mass + _y4_text_shift, _y4_lim[1])
                _t = ax4.text(t_s + (t_e - t_s) / 2, _label_y,
                              f'{overlay_label_prefix} {_seg_mass / 1000:.1f} t',
                              ha='center', va='bottom', fontsize=12.0,
                              color=_ov_col, fontweight='bold',
                              bbox=_TEXT_BBOX, zorder=9)
                _t.set_gid(f'{_ov_pfx}{_midx}|p4|value')
    ax4.set_ylabel('Vehicle Mass\n(kg)', fontsize=_LABEL_FONT)
    ax4.set_ylim(0, 50000)
    ax4.set_yticks(range(0, 50001, 10000))
    ax4.grid(True, alpha=0.3)
    if _tele_mass_plotted or _logger_mass_plotted or _mean_mass_tele or _mean_mass_logger:
        from matplotlib.lines import Line2D
        mass_legend = []
        if _tele_mass_plotted:
            mass_legend.append(Line2D([0], [0], color='#37474F', lw=2, alpha=0.8, label='Telematics Weight'))
        if _logger_mass_plotted:
            mass_legend.append(Line2D([0], [0], color='#E65100', lw=2, alpha=0.8, label='SRF Logger Weight'))
        if _mean_mass_tele:
            mass_legend.append(Line2D([0], [0], color='#333333', lw=4, linestyle='--', alpha=0.9, label='Seg. Mean Mass'))
        if _mean_mass_logger:
            mass_legend.append(Line2D([0], [0], color='#333333', lw=4, linestyle=':', alpha=0.9, label='Seg. Mean Mass (Logger)'))
        ax4.legend(handles=mass_legend, fontsize=_LEGEND_FONT, loc='upper right')

    # Fix the time axis to the full UTC calendar day [00:00, next 00:00) so that
    # figures from different days share an identical midnight-to-midnight grid
    # (directly comparable across days) instead of matplotlib autoscaling the x
    # axis to each day's actual data start/end. The day is derived from the data
    # timestamps themselves (tz-aware UTC) — the middle row is robust against a
    # stray early/late point that brushes the previous/next midnight. ``.normalize()``
    # floors a tz-aware Timestamp to 00:00:00 while keeping its UTC tz, so the
    # limits stay in the same date units (date2num) the panels already plot in.
    _t_mid = df_r[TIME_COL].iloc[len(df_r) // 2]
    day_start = _t_mid.normalize()
    day_end = day_start + pd.Timedelta(days=1)

    fmt = mdates.DateFormatter(_DATE_FMT)
    for ax in (ax1, ax2, ax3, ax4):
        # Fresh locator per axis — DateLocators hold an axis reference, so a
        # single shared instance must not be attached to multiple shared axes.
        # 3-hourly major ticks give an even 00:00 → 24:00 grid (00,03,…,21 plus
        # the next-day 00:00 at the right edge) that reads both midnights without
        # crowding the two-line '%d %b\n%H:%M' labels at the 2x tick font.
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 3)))
        ax.xaxis.set_major_formatter(fmt)
    # sharex=True → setting the limit once propagates to all four panels.
    ax4.set_xlim(day_start, day_end)
    plt.setp(ax4.xaxis.get_majorticklabels(), fontsize=_TICK_FONT)
    ax3.set_xlabel('')  # move xlabel to bottom panel
    ax4.set_xlabel('Time (UTC)', fontsize=_LABEL_FONT)

    # h_pad gives the 2x two-line y-axis labels of adjacent panels room so they
    # do not crowd at the panel boundaries.
    plt.tight_layout(h_pad=1.4)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if export_dsoc_overlay:
        # Exact figure-fraction export requires that the saved PNG span the full
        # figure [0,1]×[0,1]. ``bbox_inches='tight'`` would crop the outer
        # whitespace and break the mapping, so we save without it (tight_layout
        # already keeps the margins snug). Draw first so the transforms reflect
        # the final, laid-out axes positions, then collect + strip all bbox data
        # labels before saving so they are externalised rather than baked in.
        fig.canvas.draw()
        # v2.2.6: build the per-segment hotzone specs (id + time range) so the
        # exporter can map each segment to a figure-fraction x-range. The ids match
        # the ``set_gid`` tags on every panel's labels (``d``/``c`` base, ``od``/``oc``
        # overlay), so one hover reveals a segment's labels across all panels.
        seg_specs = []
        for _sd, _spfx in ((df_d, 'd'), (df_c, 'c'), (df_od, 'od'), (df_oc, 'oc')):
            if _sd is None or _sd.empty:
                continue
            for _i, (_, _r) in enumerate(_sd.iterrows()):
                try:
                    seg_specs.append((f'{_spfx}{_i}',
                                      _to_utc(_r['start_time']),
                                      _to_utc(_r['end_time'])))
                except (KeyError, TypeError, ValueError):
                    continue
        result = _export_overlay_boxes(fig, soc_ax=ax1, seg_specs=seg_specs)
        plt.savefig(out_path, dpi=_DPI)
        sidecar = out_path.with_suffix('.boxes.json')
        if result['boxes']:
            with open(sidecar, 'w', encoding='utf-8') as fh:
                _json.dump(result, fh, ensure_ascii=False)
        elif sidecar.exists():
            # Stale sidecar from a previous run with labels → remove it so the
            # viewer does not overlay boxes onto a now-empty figure.
            sidecar.unlink()
        # Tidy the legacy sidecar name from earlier builds (pre overlay-rename,
        # before ``.boxes.json``) so a re-paint never leaves an
        # orphaned ``.dsoc.json`` next to the new ``.boxes.json``.
        legacy = out_path.with_suffix('.dsoc.json')
        if legacy.exists():
            legacy.unlink()
    else:
        plt.savefig(out_path, dpi=_DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  fig: {out_path.name}')

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


# =============================================================================
# 封装函数：同时运行充放电分段 + 可选生成验证图
# =============================================================================
def run_segment_detection(
    df_raw: pd.DataFrame,
    reg: str,
    suffix: str,
    out_dir=None,
    generate_validation_fig: bool = True,
    charge_params: dict | None = None,
    discharge_params: dict | None = None,
    cap_lo: float | None = None,
    cap_hi: float | None = None,
    logger_speed_df: pd.DataFrame | None = None,
    logger_mass_df: pd.DataFrame | None = None,
    charger_meter_df: pd.DataFrame | None = None,
    export_dsoc_overlay: bool = False,
) -> tuple[list[dict], list[dict]]:
    """
    对一条腿的原始数据同时运行充电和放电分段算法。

    从 VEHICLE_CONFIG[reg] 自动提取各能量列名和标称容量，
    注入到 find_charge_segments_by_soc / find_discharge_segments_by_soc，
    确保列名映射和 SOC 估算兜底均使用车辆正确配置。

    参数
    ----
    df_raw   : 原始遥测 DataFrame（单条腿）
    reg      : 车辆注册号（如 'AV24LXK'），用于查找 VEHICLE_CONFIG
    suffix   : 腿标识（如 '2024-10-01_0000'），用于图片文件名
    out_dir  : 输出目录（验证图保存至 out_dir/validation/）
    generate_validation_fig : 是否生成验证图（默认 True）
    charge_params    : 传给 find_charge_segments_by_soc 的额外参数 dict
    discharge_params : 传给 find_discharge_segments_by_soc 的额外参数 dict
    cap_lo, cap_hi   : 容量阈值，同时传给两个算法
    logger_speed_df  : 可选的 Logger 速度 DataFrame（用于验证图 Panel 1 右轴）
    logger_mass_df   : 可选的 Logger CVW 质量 DataFrame（用于验证图 Panel 4）
    export_dsoc_overlay : 透传给 plot_leg_validation。True 时所有面板的圆角数据
                       标注框（dSOC / 能量 delta / 充电桩 / 再生 / 质量）均不烤进
                       PNG，改写出 ``<png>.boxes.json`` sidecar 供 inspect HTML 做
                       交互式叠加（见 plot_leg_validation）。

    返回
    ----
    (charge_segs, discharge_segs)
    _anchor_* 字段已包含；调用方保存 CSV 前需过滤（见 _ANCHOR_PRIVATE_KEYS）。
    """
    cfg      = VEHICLE_CONFIG.get(reg, {})
    _ac_col  = cfg.get('ac_col',           AC_COL)
    _dc_col  = cfg.get('dc_col',           DC_COL)
    _tot_col = cfg.get('total_energy_col', TOTAL_ENERGY_COL)
    _mov_col = cfg.get('moving_energy_col', MOVING_COL)
    _nominal = cfg.get('nominal_kwh')
    _srf_cap = cfg.get('srf_capacity_kwh', _nominal)
    _eff_cap = cfg.get('effective_capacity_kwh')
    # SOC estimate 用的容量优先级：effective > srf > nominal
    _soc_est_cap = _eff_cap or _srf_cap or _nominal

    # Pipeline params as defaults; caller-passed overrides take precedence
    _pipeline_name = cfg.get('pipeline', 'default_soc')
    _pipeline_cfg  = PIPELINE_CONFIGS.get(_pipeline_name,
                                          PIPELINE_CONFIGS['default_soc'])
    c_params = dict(_pipeline_cfg.get('charge_params', {}))
    c_params.update(charge_params or {})
    d_params = dict(_pipeline_cfg.get('discharge_params', {}))
    d_params.update(discharge_params or {})

    if cap_lo is not None:
        c_params.setdefault('cap_lo', cap_lo)
        d_params.setdefault('cap_lo', cap_lo)
    if cap_hi is not None:
        c_params.setdefault('cap_hi', cap_hi)
        d_params.setdefault('cap_hi', cap_hi)

    # 列名映射注入（覆盖 params 中可能的旧值）
    c_params['ac_col']           = _ac_col
    c_params['dc_col']           = _dc_col
    c_params['moving_energy_col'] = _mov_col
    # SOC estimate 兜底容量：effective > srf > nominal
    if _soc_est_cap is not None:
        c_params.setdefault('nominal_kwh', _soc_est_cap)

    d_params['total_energy_col']  = _tot_col
    d_params['moving_energy_col'] = _mov_col
    if _soc_est_cap is not None:
        d_params.setdefault('nominal_kwh', _soc_est_cap)

    # Pipeline 顶层 min_trip_distance_km 注入（默认 0.0 = 不过滤，向后兼容）。
    # 仅 soc 分支用；speed 分支由 find_speed_trips 的 min_trip_duration_min 控制。
    _min_trip_km = float(_pipeline_cfg.get('min_trip_distance_km', 0.0))
    if _min_trip_km > 0.0:
        d_params.setdefault('min_trip_distance_km', _min_trip_km)

    # ── pipeline 分支 ─────────────────────────────────────────────────────
    # 算法分支由 PIPELINE_CONFIGS[pipeline_name]['branch'] 决定。
    # 新增算法分支：在此添加 elif branch == '...' 分支并实现对应函数。
    branch = _pipeline_cfg.get('branch', 'soc')

    if branch == 'soc':
        charge_segs    = find_charge_segments_by_soc(df_raw, **c_params)
        discharge_segs = find_discharge_segments_by_soc(df_raw, **d_params)

    elif branch == 'speed':
        charge_segs = find_charge_segments_by_soc(df_raw, **c_params)
        # 速度分段参数
        _speed_col = cfg.get('speed_col', 'wheel_based_speed')
        speed_p = dict(_pipeline_cfg.get('speed_params', {}))
        speed_p['speed_col'] = _speed_col
        # Per-vehicle min_stop_duration_min override (vehicles.json): defaults to
        # the pipeline speed_params value; a vehicle that needs a wider
        # stop-bridge gap (e.g. TA70WTL's ~7-min pickup/drop pauses that should
        # not split a single round) can raise it without touching the shared
        # pipeline value (renault_speed also serves N88GNW / T88RNW). Only
        # vehicles that set the key are affected.
        _min_stop_override = cfg.get('min_stop_duration_min')
        if _min_stop_override is not None:
            speed_p['min_stop_duration_min'] = float(_min_stop_override)
        # 从车辆配置传递能量列和容量参数
        speed_p['total_energy_col'] = _tot_col
        speed_p['moving_energy_col'] = _mov_col
        if _soc_est_cap:
            speed_p.setdefault('nominal_kwh', _soc_est_cap)
        if cap_lo:
            speed_p.setdefault('cap_lo', cap_lo)
        if cap_hi:
            speed_p.setdefault('cap_hi', cap_hi)
        # Trip 端点锚定策略（pipeline 顶层字段）。v2.2.5 起 zero_speed 成为
        # 全车队默认；pipeline 可显式设 trip_endpoint_anchor: "first_motion" 退回旧行为。
        # zero_speed 模式见 find_speed_trips() docstring。
        _anchor = _pipeline_cfg.get('trip_endpoint_anchor', 'zero_speed')
        _max_ext = float(_pipeline_cfg.get('max_extend_minutes', 5.0))
        speed_p['trip_endpoint_anchor'] = _anchor
        speed_p['max_extend_minutes']   = _max_ext
        # 遥测速度不可用、或车辆配置 prefer_logger_speed 时，用 Logger 速度检测行程窗口。
        # prefer_logger_speed: telematics speed 存在但不可靠（如 YN25RSY 几乎全零、仅零星
        # 噪声，.any() 会误判为可用）→ 显式强制走可靠的 Logger 速度（与 diesel logger 范式
        # 一致），避免落到 SOC 兜底切出跟随 SOC 下降的巨段。
        _prefer_logger = bool(cfg.get('prefer_logger_speed', False))
        _has_tele_speed = (_speed_col in df_raw.columns and
                           pd.to_numeric(df_raw[_speed_col], errors='coerce')
                           .pipe(lambda s: s.notna() & (s > 0)).any())
        if (_prefer_logger or not _has_tele_speed) and \
                logger_speed_df is not None and not logger_speed_df.empty:
            # 从 Logger 速度 DataFrame 构建行程检测用的 DataFrame
            _logger_spd_df = pd.DataFrame({
                TIME_COL: logger_speed_df.index,
                _speed_col: logger_speed_df.iloc[:, 0].values,
            })
            _logger_trips = find_speed_trips(
                _logger_spd_df,
                speed_col=_speed_col,
                speed_threshold_kmh=speed_p.get('speed_threshold_kmh', 1.0),
                min_stop_duration_min=speed_p.get('min_stop_duration_min', 5.0),
                min_trip_duration_min=speed_p.get('min_trip_duration_min', 2.0),
                trip_endpoint_anchor=_anchor,
                max_extend_minutes=_max_ext,
            )
            speed_p['trips'] = _logger_trips
            _logger_reason = ('使用 Logger Speed（prefer_logger_speed）'
                              if _prefer_logger else
                              '遥测速度不可用，回退使用 Logger Speed')
            logger.info(f'  速度数据: {_logger_reason}'
                        f' (检测到 {len(_logger_trips)} 个行程)')
        discharge_segs = find_discharge_segments_by_speed(df_raw, **speed_p)
        # Fallback：若速度分段无结果，回退到 SOC-based
        if not discharge_segs:
            discharge_segs = find_discharge_segments_by_soc(df_raw, **d_params)

    else:
        raise ValueError(
            f'Unknown algorithm branch {branch!r} for pipeline {_pipeline_name!r} '
            f'(vehicle {reg!r}). Supported: soc, speed'
        )

    # ── 质量聚类 + 基于聚类的拆分与合并 ──────────────────────────────────────
    _m_col = cfg.get('mass_col', MASS_COL)
    _mass_from_logger = False
    # 检查遥测质量数据是否有效；若无效且有 Logger 质量则回退
    _has_tele_mass = False
    if _m_col in df_raw.columns:
        _tele_mass = pd.to_numeric(df_raw[_m_col], errors='coerce')
        _has_tele_mass = bool((_tele_mass.notna() & (_tele_mass > 0)).any())
    if not _has_tele_mass and logger_mass_df is not None and not logger_mass_df.empty:
        # Logger 质量回退：将 Logger CVW 合并到 df_raw 的质量列中
        df_raw = df_raw.copy()
        if _m_col not in df_raw.columns:
            df_raw[_m_col] = np.nan
        _times_utc = pd.to_datetime(df_raw[TIME_COL], errors='coerce', utc=True)
        _df_times = pd.DataFrame({
            '_idx': df_raw.index,
            '_time': _times_utc,
        }).dropna(subset=['_time']).sort_values('_time')
        _log_df = pd.DataFrame({
            '_time': logger_mass_df.index,
            '_logger_mass': logger_mass_df.iloc[:, 0].values,
        }).sort_values('_time')
        _merged = pd.merge_asof(
            _df_times, _log_df, on='_time',
            tolerance=pd.Timedelta('5min'),
            direction='nearest',
        )
        # df_raw 以 dtype=str 读取，需将 float 转为 str 以避免 TypeError
        _mass_vals = _merged['_logger_mass'].values
        df_raw[_m_col] = df_raw[_m_col].astype(object)
        df_raw.loc[_merged['_idx'].values, _m_col] = _mass_vals
        _mass_from_logger = True
        logger.info('  质量数据: 遥测质量不可用，回退使用 Logger CVW')

    if cfg.get('split_by_mass', True) and _m_col in df_raw.columns:
        # 1. 对整条 leg 的质量数据聚类，新增 mass_cluster + mass_moving 列
        #    v2.2.4: 聚类均值只用「行驶中」质量读数（静止 GCVW 不可靠）；
        #    若 mass-from-logger 路径下遥测无速度列，cluster_mass_data 会自动回退
        #    到全部有效读数聚类（low-risk，无行为变化）。
        _gap_kg = cfg.get('min_cluster_gap_kg', MIN_CLUSTER_GAP_KG)
        _split_speed_col = cfg.get('speed_col', 'wheel_based_speed')
        _speed_p_top = _pipeline_cfg.get('speed_params', {}) if branch == 'speed' else {}
        _move_thr = float(_speed_p_top.get('speed_threshold_kmh',
                                           MOVING_SPEED_THRESHOLD_KMH))
        df_raw = cluster_mass_data(df_raw, mass_col=_m_col,
                                   min_cluster_gap_kg=_gap_kg,
                                   speed_col=_split_speed_col,
                                   speed_threshold_kmh=_move_thr)
        # 2. 在聚类标签变化处拆分放电段（装卸货事件）
        #    方案 B：切点附近 ±W/2 必须存在 v=0 样本，否则视为 CVW 噪声尖刺。
        #    W 沿用速度参数 min_stop_duration_min（与 zero_speed anchor 一致）。
        # Honour the per-vehicle min_stop_duration_min override here too, so the
        # zero-speed split window stays coherent with the trip-detection gap.
        _min_stop_min = float(cfg.get('min_stop_duration_min',
                                      _speed_p_top.get('min_stop_duration_min', 5.0)))
        _split_window_s = _min_stop_min * 60.0
        discharge_segs = split_discharge_by_mass(
            discharge_segs, df_raw,
            speed_col=_split_speed_col,
            zero_speed_window_seconds=_split_window_s,
        )
        # 3. 合并相邻且聚类相同的放电段（消除非装卸货事件的多余切分）
        #    pipeline 顶层 `merge_by_mass: false` 可关闭此合并（保留 split）。
        #    用例：scania_speed_00 / scania_speed_01 / volvo_speed_03 等同质量
        #    cluster 整日不变的车辆，merge 会把所有 trip 合并成单段长 In Transit。
        #    Per-vehicle override (vehicles.json `merge_by_mass`) wins over the
        #    pipeline flag; both default to True. This lets a single vehicle on a
        #    shared pipeline (e.g. TA70WTL on renault_speed) disable the merge
        #    without affecting its pipeline siblings (N88GNW / T88RNW stay merge-ON).
        _merge_by_mass = cfg.get(
            'merge_by_mass', _pipeline_cfg.get('merge_by_mass', True)
        )
        if _merge_by_mass:
            # 长时间静止切分（opt-in）：vehicles.json 的 split_long_stops_min
            # （分钟）启用。仅配置了该键的车辆（目前 Nestlé: EV73SAL / YK73WFN）
            # 受影响；其它车 cfg.get(...) 为 None → merge 行为逐字不变。
            _long_stop_min = cfg.get('split_long_stops_min')
            discharge_segs = merge_discharge_by_mass(
                discharge_segs, df_raw,
                charge_segs=charge_segs,
                max_merge_gap_min=_long_stop_min,
            )
        # 4. 重新计算拆分后缺失的能量锚点（用于验证图标注）
        _recompute_anchors(discharge_segs, df_raw, _tot_col, _mov_col)

    # ── 锚点非重叠强制 ────────────────────────────────────────────────────
    # 对最终放电段（已经过 split / merge / _recompute_anchors）运行：把因稀疏累计
    # 计数器导致的相邻段能量重复计入（anchor_end(i) > anchor_start(i+1)）钳正。
    # 置于 split_by_mass 块之外、验证图之前 → speed / soc 两分支的最终段都覆盖。
    _n_clamped = _enforce_anchor_ordering(discharge_segs, reg)
    if _n_clamped:
        logger.info('  锚点重叠修正: %d 段已钳位（%s %s）', _n_clamped, reg, suffix)

    if generate_validation_fig and out_dir is not None and _HAS_MPL:
        # Panel 3 列：优先使用 total_energy_col（若放电段实际使用了它）
        panel3_col = _mov_col  # default
        if discharge_segs:
            if discharge_segs[0].get('energy_source') == 'total_energy':
                panel3_col = _tot_col
        else:
            # 无放电段时检查 df 中 total_energy_col 是否有效数据
            if _tot_col in df_raw.columns:
                if pd.to_numeric(df_raw[_tot_col], errors='coerce').notna().sum() > 0:
                    panel3_col = _tot_col

        val_dir  = Path(out_dir) / 'validation_figures'
        out_path = val_dir / f'validation_{reg}_{suffix}.png'
        _mass_col = cfg.get('mass_col', MASS_COL)
        _speed_col = cfg.get('speed_col', 'wheel_based_speed')
        _mass_agg = resolve_mass_agg(reg, _pipeline_cfg)
        plot_leg_validation(
            df_raw, charge_segs, discharge_segs,
            reg, suffix, out_path,
            ac_col=_ac_col, dc_col=_dc_col, panel3_col=panel3_col,
            mass_col=_mass_col, speed_col=_speed_col,
            logger_speed_df=logger_speed_df,
            logger_mass_df=logger_mass_df,
            charger_meter_df=charger_meter_df,
            mass_from_logger=_mass_from_logger,
            mass_agg=_mass_agg,
            export_dsoc_overlay=export_dsoc_overlay,
        )

    return charge_segs, discharge_segs
