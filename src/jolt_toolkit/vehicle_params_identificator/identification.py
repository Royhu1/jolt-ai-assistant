"""
参数辨识核心算法模块。
基于能量平衡的线性约束法辨识 C_rr 和 C_dA。

支持两种能量源：
1. EEC1 模式: E_motor = Σ(EngSpd × EngTrq% × max_torque / 100 × 2π/60 × Δt)
   适用于有 EEC1 (J1939) 数据的电动重卡（电机通过 J1939 报告转速/扭矩）
2. 电池模式: E_battery = ΔE_counter × 3600000 (kWh → J)
   适用于有电池能量计数器的车辆（fallback）

能量方程: E_source = (ΔE_kinetic + ΔE_potential + C_rr·m·g·Σ(Δs) + C_dA·½·ρ·Σ(v²·Δs)) / η
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
import sympy as sp
from scipy import stats
from sklearn.cluster import KMeans

from jolt_toolkit.vehicle_params_identificator.config import (
    GRAVITY,
    AIR_DENSITY,
    MOTOR_EFFICIENCY,
    N_CLUSTERS,
    RANDOM_STATE,
)

logger = logging.getLogger(__name__)


def calculate_linear_constraint(
    segment_df: pd.DataFrame,
    *,
    max_torque_nm: float | None = None,
    drive_train_efficiency: float = MOTOR_EFFICIENCY,
    gravity: float = GRAVITY,
    air_density: float = AIR_DENSITY,
    elevation_col: str = "elevation",
    energy_mode: str = "auto",
) -> Optional[dict]:
    """
    为单个巡航段计算 C_rr = f(C_dA) 的线性约束。

    Args:
        max_torque_nm: 电机/发动机最大扭矩 (Nm)，EEC1 模式必需
        energy_mode: "eec1" / "battery" / "auto"
            auto: 有 EngSpd+EngTrq → eec1; 否则 → battery

    Returns:
        约束字典或 None。
    """
    # 自动列名兼容
    speed_col = "Spd_Kmph_x" if "Spd_Kmph_x" in segment_df.columns else "speed_kmph"
    dist_col = "distance_gps" if "distance_gps" in segment_df.columns else "distance_m"
    mass_col = "MassKg" if "MassKg" in segment_df.columns else "mass_kg"

    try:
        # ── 质量 ──
        mass_series = segment_df[mass_col].dropna()
        mass_series = mass_series[mass_series > 0]
        if len(mass_series) < 2:
            return None
        avg_mass = float(mass_series.mean())
        mass_cv = float(mass_series.std() / avg_mass) if avg_mass > 0 else 0.0

        # ── 海拔 ──
        if elevation_col not in segment_df.columns:
            return None
        elev = segment_df[elevation_col].dropna()
        if len(elev) < 2:
            return None
        h_start, h_end = float(elev.iloc[0]), float(elev.iloc[-1])

        # ── 速度 ──
        speed_mps = segment_df[speed_col].dropna() / 3.6
        if len(speed_mps) < 2:
            return None
        v_start, v_end = float(speed_mps.iloc[0]), float(speed_mps.iloc[-1])

        # ── 距离增量 ──
        dist_intervals = segment_df[dist_col].diff().fillna(0)
        total_distance = float(dist_intervals.sum())
        if total_distance <= 0:
            return None

        # ── 确定能量模式 ──
        has_eec1 = (
            "EngSpd" in segment_df.columns
            and "EngTrq" in segment_df.columns
            and segment_df["EngSpd"].notna().sum() > 5
        )
        if energy_mode == "auto":
            energy_mode = "eec1" if has_eec1 else "battery"

        # ── 计算实际能量 (J) ──
        if energy_mode == "eec1":
            if max_torque_nm is None:
                logger.warning("EEC1 模式需要 max_torque_nm")
                return None
            actual_energy_J = _calc_eec1_energy(segment_df, max_torque_nm)
        else:
            actual_energy_J = _calc_battery_energy(segment_df)

        if actual_energy_J is None or actual_energy_J <= 0:
            return None

        # ── 符号求解 ──
        crr = sp.symbols("crr")
        cda = sp.symbols("cda")

        delta_kinetic = 0.5 * avg_mass * (v_end**2 - v_start**2)
        delta_potential = avg_mass * gravity * (h_end - h_start)
        rolling = crr * avg_mass * gravity * total_distance

        v_series = segment_df[speed_col].fillna(0) / 3.6
        v2_ds = float((v_series**2 * dist_intervals).sum())
        aero = cda * 0.5 * air_density * v2_ds

        predicted = (delta_kinetic + delta_potential + rolling + aero) / drive_train_efficiency
        eq = sp.Eq(predicted, actual_energy_J)

        crr_sols = sp.solve(eq, crr)
        if not crr_sols:
            return None
        crr_expr = crr_sols[0]

        slope_val = float(crr_expr.coeff(cda, 1))
        intercept_val = float(crr_expr.coeff(cda, 0))

        return {
            "slope": slope_val,
            "intercept": intercept_val,
            "avg_mass": avg_mass,
            "mass_cv": mass_cv,
            "actual_energy_J": actual_energy_J,
            "energy_mode": energy_mode,
            "segment_period": None,
            "segment_df": segment_df,
        }

    except Exception as e:
        logger.debug("约束计算失败: %s", e)
        return None


def _calc_eec1_energy(df: pd.DataFrame, max_torque_nm: float) -> float | None:
    """从 EEC1 (EngSpd, EngTrq%) 计算能量 (J)。"""
    eng_spd = pd.to_numeric(df["EngSpd"], errors="coerce")
    eng_trq_pct = pd.to_numeric(df["EngTrq"], errors="coerce")
    if eng_spd.notna().sum() < 5:
        return None

    trq_nm = eng_trq_pct * max_torque_nm / 100.0
    power_w = eng_spd * trq_nm * 2 * np.pi / 60.0  # RPM → rad/s × Nm = W
    # 每行 1s（Logger 1s 分辨率）→ 功率之和 ≈ 能量 (J)
    total_energy = float(power_w.sum())
    return total_energy if total_energy > 0 else None


def _calc_battery_energy(df: pd.DataFrame) -> float | None:
    """从电池能量计数器或 SOC 计算能量 (J)。"""
    # 优先用累积能量计数器
    for col in ["energy_kwh"]:
        if col in df.columns:
            e = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(e) >= 2:
                delta_kwh = e.iloc[-1] - e.iloc[0]
                if delta_kwh > 0:
                    return delta_kwh * 3_600_000

    # fallback: SOC × nominal capacity
    if "soc_pct" in df.columns and "battery_capacity" in df.columns:
        soc = pd.to_numeric(df["soc_pct"], errors="coerce").dropna()
        cap = pd.to_numeric(df["battery_capacity"], errors="coerce").dropna()
        if len(soc) >= 2 and len(cap) >= 1:
            delta_soc = abs(soc.iloc[-1] - soc.iloc[0]) / 100.0
            avg_cap = float(cap.mean())
            if delta_soc > 0 and avg_cap > 0:
                return delta_soc * avg_cap * 3_600_000  # kWh → J

    return None


def calculate_all_constraints(
    segments: list[dict],
    *,
    max_torque_nm: float | None = None,
    drive_train_efficiency: float = MOTOR_EFFICIENCY,
    gravity: float = GRAVITY,
    air_density: float = AIR_DENSITY,
    elevation_col: str = "elevation",
    energy_mode: str = "auto",
    verbose: bool = True,
) -> list[dict]:
    """为所有巡航段计算线性约束。"""
    constraints = []
    failed = 0

    for idx, seg in enumerate(segments):
        c = calculate_linear_constraint(
            seg["segment_df"],
            max_torque_nm=max_torque_nm,
            drive_train_efficiency=drive_train_efficiency,
            gravity=gravity,
            air_density=air_density,
            elevation_col=elevation_col,
            energy_mode=energy_mode,
        )
        if c is not None:
            c["segment_period"] = seg["segment_period"]
            constraints.append(c)
        else:
            failed += 1

        if verbose and (idx + 1) % 50 == 0:
            logger.info("已处理 %d/%d 段", idx + 1, len(segments))

    logger.info("约束计算: 成功 %d, 失败 %d", len(constraints), failed)
    return constraints


def identify_parameters(
    constraints: list[dict],
    *,
    n_clusters: int = N_CLUSTERS,
    random_state: int = RANDOM_STATE,
) -> dict:
    """
    K-Means 聚类 + 交线法辨识 C_rr, C_dA。

    1. 对 avg_mass 做 K-Means（轻载/重载）
    2. 分别计算平均约束线
    3. 交点 = (C_dA, C_rr)
    """
    result = {
        "c_rr_identified": None,
        "c_da_identified": None,
        "cluster_0_slope_mean": None,
        "cluster_0_intercept_mean": None,
        "cluster_1_slope_mean": None,
        "cluster_1_intercept_mean": None,
        "cluster_labels": None,
        "constraints": constraints,
        "n_cluster_0": 0,
        "n_cluster_1": 0,
        "optimal_k": n_clusters,
    }

    if len(constraints) < n_clusters:
        logger.error("约束数量 (%d) 不足", len(constraints))
        return result

    avg_masses = np.array([c["avg_mass"] for c in constraints]).reshape(-1, 1)
    slopes = np.array([c["slope"] for c in constraints])
    intercepts = np.array([c["intercept"] for c in constraints])

    kmeans = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
    labels = kmeans.fit_predict(avg_masses)

    idx_0 = np.where(labels == 0)[0]
    idx_1 = np.where(labels == 1)[0]

    if len(idx_0) == 0 or len(idx_1) == 0:
        logger.error("聚类不均衡: %d / %d", len(idx_0), len(idx_1))
        result["cluster_labels"] = labels
        return result

    # Cluster 0 = 轻载
    if float(avg_masses[idx_0].mean()) > float(avg_masses[idx_1].mean()):
        labels = 1 - labels
        idx_0, idx_1 = idx_1, idx_0

    ms0 = float(slopes[idx_0].mean())
    mi0 = float(intercepts[idx_0].mean())
    ms1 = float(slopes[idx_1].mean())
    mi1 = float(intercepts[idx_1].mean())

    logger.info("Cluster 0 (轻载): n=%d, mass=%.0f kg", len(idx_0), float(avg_masses[idx_0].mean()))
    logger.info("Cluster 1 (重载): n=%d, mass=%.0f kg", len(idx_1), float(avg_masses[idx_1].mean()))

    result.update({
        "cluster_0_slope_mean": ms0, "cluster_0_intercept_mean": mi0,
        "cluster_1_slope_mean": ms1, "cluster_1_intercept_mean": mi1,
        "cluster_labels": labels,
        "n_cluster_0": int(len(idx_0)), "n_cluster_1": int(len(idx_1)),
    })

    if abs(ms0 - ms1) > 1e-10:
        c_da = float((mi1 - mi0) / (ms0 - ms1))
        c_rr = float(ms0 * c_da + mi0)
        result["c_da_identified"] = c_da
        result["c_rr_identified"] = c_rr
        logger.info("辨识结果: C_dA = %.3f m^2, C_rr = %.6f", c_da, c_rr)
    else:
        logger.warning("两条平均线平行，无法求交点")

    return result


def filter_by_wind_mean(
    constraints: list[dict], *, wind_max_mps: float, wind_col: str = "wind_speed_mps",
) -> list[dict]:
    """过滤平均风速过大的约束。"""
    kept = []
    for c in constraints:
        df = c.get("segment_df")
        if df is None or df.empty or wind_col not in df.columns:
            kept.append(c)  # 无风速数据则保留
            continue
        ws = df[wind_col].dropna()
        if len(ws) == 0 or float(ws.mean()) <= wind_max_mps:
            kept.append(c)
    logger.info("风速过滤 (≤%.1f m/s): %d → %d", wind_max_mps, len(constraints), len(kept))
    return kept


def filter_by_elevation_change(
    constraints: list[dict], *, threshold_m: float, elevation_col: str = "elevation",
) -> list[dict]:
    """过滤海拔变化过大的约束。"""
    kept = []
    for c in constraints:
        df = c.get("segment_df")
        if df is None or df.empty or elevation_col not in df.columns:
            continue
        elev = df[elevation_col].dropna()
        if len(elev) < 2:
            kept.append(c)
            continue
        if abs(float(elev.iloc[-1] - elev.iloc[0])) <= threshold_m:
            kept.append(c)
    logger.info("海拔过滤 (±%.0f m): %d → %d", threshold_m, len(constraints), len(kept))
    return kept


def filter_by_mass_deviation(constraints: list[dict], *, deviation_pct: float) -> list[dict]:
    """过滤质量偏离聚类中心的约束。"""
    if not constraints:
        return constraints
    labels = np.array([c.get("cluster", -1) for c in constraints])
    masses = np.array([c.get("avg_mass", np.nan) for c in constraints])
    keep = np.ones(len(constraints), dtype=bool)
    for cl in set(labels.tolist()):
        if cl < 0:
            continue
        cl_idx = np.where(labels == cl)[0]
        mean_m = float(np.nanmean(masses[cl_idx]))
        for i in cl_idx:
            if not (mean_m * (1 - deviation_pct) <= masses[i] <= mean_m * (1 + deviation_pct)):
                keep[i] = False
    kept = [c for i, c in enumerate(constraints) if keep[i]]
    logger.info("质量过滤 (±%.0f%%): %d → %d", deviation_pct * 100, len(constraints), len(kept))
    return kept
