# Canonical home since v3.1.0 (P1 copy, 2026-07-17): moved here from
# src/jolt_toolkit/vehicle_params_identificator/preprocessing.py — the param-identifier
# agent's workspace (research_projects/parameter_identify/) now owns the
# identification code (the package original is removed in P2). Standalone entry:
#   python research_projects/parameter_identify/code/run_identification.py --help
"""
巡航段提取模块。
从 Logger per-leg CSV 中提取满足条件的近似恒速段 (cruise segments)。

支持两种模式：
- 有 BrkPedalPos 时：使用原始 CRRCDA 方法（无制动 + 高速）
- 无 BrkPedalPos 时：使用速度 CV 判定（fallback）

列名约定（与原始 CRRCDA 兼容）：
- Spd_Kmph_x: CCVS 速度 (km/h)
- BrkPedalPos: 制动踏板位置
- distance_gps: 累积 GPS 距离 (m)
- MassKg: 质量 (kg)
- elevation: 海拔 (m)
- EngSpd / EngTrq: 电机转速/扭矩百分比（有 EEC1 时）
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from config import (
    MAX_SPEED_CV,
    MIN_AVG_SPEED_KMPH,
    MIN_SPEED_FLOOR_KMPH,
    SEG_DISTANCE_M,
    WINDOW_STEP_M,
)

logger = logging.getLogger(__name__)


def get_cruise_segments(
    leg_df: pd.DataFrame,
    *,
    seg_distance_m: float = SEG_DISTANCE_M,
    min_avg_speed_kmph: float = MIN_AVG_SPEED_KMPH,
    window_step_m: float = WINDOW_STEP_M,
    max_speed_cv: float = MAX_SPEED_CV,
    min_speed_floor_kmph: float = MIN_SPEED_FLOOR_KMPH,
    use_brake_filter: bool = True,
) -> list[dict]:
    """
    从单条 leg 中使用滑动窗口提取巡航段。

    筛选条件：
    1. 有 BrkPedalPos 时 → 段内无制动 (BrkPedalPos == 0)
       无 BrkPedalPos 时 → 速度 CV < max_speed_cv
    2. 段内最低速度 > min_speed_floor（无停车）
    3. 平均速度 ≥ min_avg_speed
    4. 有效质量数据（MassKg > 0）
    5. 有效海拔数据（≥ 2 个点）
    6. 有效能量数据（EngSpd/EngTrq 不全 NaN，或 soc_pct 有变化）

    Returns:
        [{"segment_period": (...), "segment_df": DataFrame}, ...]
    """
    # 确定列名
    speed_col = "Spd_Kmph_x" if "Spd_Kmph_x" in leg_df.columns else "speed_kmph"
    dist_col = "distance_gps" if "distance_gps" in leg_df.columns else "distance_m"
    mass_col = "MassKg" if "MassKg" in leg_df.columns else "mass_kg"
    elev_col = "elevation" if "elevation" in leg_df.columns else "altitude_m"
    brake_col = "BrkPedalPos"

    if dist_col not in leg_df.columns or speed_col not in leg_df.columns:
        return []

    has_brake = brake_col in leg_df.columns and use_brake_filter
    has_eec1 = "EngSpd" in leg_df.columns and "EngTrq" in leg_df.columns

    segments = []
    max_distance = leg_df[dist_col].max()
    if pd.isna(max_distance) or max_distance < seg_distance_m:
        return []

    start = 0.0
    while start < max_distance - seg_distance_m:
        end = start + seg_distance_m
        mask = (leg_df[dist_col] >= start) & (leg_df[dist_col] < end)
        seg_df = leg_df.loc[mask].copy()

        if len(seg_df) < 10:
            start += window_step_m
            continue

        speed = seg_df[speed_col].dropna()
        if len(speed) < 5:
            start += window_step_m
            continue

        # 条件 1: 无制动 / 低速度变异
        if has_brake:
            if (seg_df[brake_col] > 0).any():
                start += window_step_m
                continue
        else:
            avg_spd = speed.mean()
            cv = speed.std() / avg_spd if avg_spd > 0 else float("inf")
            if cv > max_speed_cv:
                start += window_step_m
                continue

        # 条件 2: 段内无停车
        if (speed < min_speed_floor_kmph).any():
            start += window_step_m
            continue

        # 条件 3: 最小平均速度
        avg_speed = speed.mean()
        if avg_speed < min_avg_speed_kmph:
            start += window_step_m
            continue

        # 条件 4: 有效质量
        if mass_col in seg_df.columns:
            mass_valid = seg_df[mass_col].dropna()
            mass_valid = mass_valid[mass_valid > 0]
            if len(mass_valid) < 2:
                start += window_step_m
                continue
        else:
            start += window_step_m
            continue

        # 条件 5: 有效海拔
        if elev_col in seg_df.columns:
            alt_valid = seg_df[elev_col].dropna()
            if len(alt_valid) < 2:
                start += window_step_m
                continue
        else:
            start += window_step_m
            continue

        # 条件 6: 有效能量数据
        if has_eec1:
            eng_spd = seg_df["EngSpd"].dropna()
            eng_trq = seg_df["EngTrq"].dropna()
            if len(eng_spd) < 5 or len(eng_trq) < 5:
                start += window_step_m
                continue
        elif "soc_pct" in seg_df.columns:
            soc = seg_df["soc_pct"].dropna()
            if len(soc) < 2 or abs(soc.iloc[-1] - soc.iloc[0]) < 0.5:
                start += window_step_m
                continue
        # 如果没有任何能量数据也跳过
        elif "energy_kwh" not in seg_df.columns:
            start += window_step_m
            continue

        # 所有条件通过
        if "UnixTime" in seg_df.columns:
            times = pd.to_datetime(seg_df["UnixTime"], unit="ms")
            period = (
                times.iloc[0].strftime("%y%m%d-%H%M%S"),
                times.iloc[-1].strftime("%y%m%d-%H%M%S"),
            )
        elif "timestamp" in seg_df.columns:
            ts = pd.to_datetime(seg_df["timestamp"])
            period = (
                ts.iloc[0].strftime("%y%m%d-%H%M%S"),
                ts.iloc[-1].strftime("%y%m%d-%H%M%S"),
            )
        else:
            period = (str(int(start)), str(int(end)))

        segments.append({"segment_period": period, "segment_df": seg_df})
        start = end  # 不重叠

    return segments


def extract_all_cruise_segments(
    dataframes: list[pd.DataFrame],
    *,
    seg_distance_m: float = SEG_DISTANCE_M,
    min_avg_speed_kmph: float = MIN_AVG_SPEED_KMPH,
    window_step_m: float = WINDOW_STEP_M,
    max_speed_cv: float = MAX_SPEED_CV,
    min_speed_floor_kmph: float = MIN_SPEED_FLOOR_KMPH,
    use_brake_filter: bool = True,
    verbose: bool = True,
) -> list[dict]:
    """从所有 leg 数据中提取巡航段。"""
    all_segments = []
    for idx, df in enumerate(dataframes):
        segs = get_cruise_segments(
            df,
            seg_distance_m=seg_distance_m,
            min_avg_speed_kmph=min_avg_speed_kmph,
            window_step_m=window_step_m,
            max_speed_cv=max_speed_cv,
            min_speed_floor_kmph=min_speed_floor_kmph,
            use_brake_filter=use_brake_filter,
        )
        if segs:
            all_segments.extend(segs)
            if verbose:
                logger.debug("Leg %d: %d 个巡航段", idx + 1, len(segs))

    logger.info(
        "总计提取 %d 个巡航段 (来自 %d 条 legs)", len(all_segments), len(dataframes)
    )
    return all_segments
