"""
Top-level orchestrator: run charge + discharge segmentation for one leg and
optionally render the validation figure.

Behaviour-preserving split of the former ``segment_algorithms.py`` (v3.0.0).
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .constants import (
    AC_COL,
    DC_COL,
    MASS_COL,
    MIN_CLUSTER_GAP_KG,
    MOVING_COL,
    MOVING_SPEED_THRESHOLD_KMH,
    PIPELINE_CONFIGS,
    TIME_COL,
    TOTAL_ENERGY_COL,
    VEHICLE_CONFIG,
)
from .mass_aggregation import resolve_mass_agg
from .mass_clustering import (
    _enforce_anchor_ordering,
    _recompute_anchors,
    cluster_mass_data,
    merge_discharge_by_mass,
    split_discharge_by_mass,
)
from .soc_detection import (
    find_charge_segments_by_soc,
    find_discharge_segments_by_soc,
)
from .speed_detection import (
    find_discharge_segments_by_speed,
    find_speed_trips,
)
from .validation_figure import _HAS_MPL, plot_leg_validation

logger = logging.getLogger(__name__)

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
