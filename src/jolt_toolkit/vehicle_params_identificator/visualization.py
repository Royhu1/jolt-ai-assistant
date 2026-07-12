"""
综合可视化模块。
生成 2×2 子图的参数辨识分析图。
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

from jolt_toolkit.vehicle_params_identificator.config import (
    PARAMS_RANGE,
    LABEL_FONT_SIZE,
    TITLE_FONT_SIZE,
    TICK_FONT_SIZE,
    LEGEND_FONT_SIZE,
    LINE_COLOR_CLUSTER_0,
    LINE_COLOR_CLUSTER_1,
    INTERSECTION_COLOR,
)

logger = logging.getLogger(__name__)

plt.rcParams["font.sans-serif"] = ["SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def plot_comprehensive_analysis(
    result: dict,
    title: str,
    *,
    save_path: Optional[str] = None,
    params_range: dict | None = None,
    figsize: tuple = (18, 16),
    show_plot: bool = False,
) -> Optional[str]:
    """
    2×2 综合分析图：
    - 左上: 所有约束线
    - 右上: 平均线 + 95% CI + 交点
    - 左下: 斜率分布
    - 右下: 截距分布

    Returns:
        保存路径或 None。
    """
    if params_range is None:
        params_range = PARAMS_RANGE

    constraints = result.get("constraints", [])
    labels = result.get("cluster_labels")
    if labels is None or len(constraints) == 0:
        logger.warning("无有效约束，跳过绘图")
        return None

    slopes = np.array([c["slope"] for c in constraints])
    intercepts = np.array([c["intercept"] for c in constraints])
    idx_0 = np.where(labels == 0)[0]
    idx_1 = np.where(labels == 1)[0]

    if len(idx_0) == 0 or len(idx_1) == 0:
        logger.warning("聚类不均衡，跳过绘图")
        return None

    slopes_0, slopes_1 = slopes[idx_0], slopes[idx_1]
    intercepts_0, intercepts_1 = intercepts[idx_0], intercepts[idx_1]
    cda_range = np.linspace(params_range["cda_low"], params_range["cda_high"], 200)

    fig, axes = plt.subplots(2, 2, figsize=figsize)
    fig.suptitle(
        f"Comprehensive Parameter Identification — {title}",
        fontsize=TITLE_FONT_SIZE + 2, fontweight="bold", y=0.995,
    )

    c0 = LINE_COLOR_CLUSTER_0
    c1 = LINE_COLOR_CLUSTER_1

    # ── 1. 所有约束线 ────────────────────────────────────────────────────
    ax1 = axes[0, 0]
    for i, c in enumerate(constraints):
        crr = c["slope"] * cda_range + c["intercept"]
        color = c0 if labels[i] == 0 else c1
        ax1.plot(cda_range, crr, color=color, alpha=0.3, linewidth=0.8)

    ax1.set_xlim(params_range["cda_low"], params_range["cda_high"])
    ax1.set_ylim(params_range["crr_low"], params_range["crr_high"])
    ax1.set_xlabel("$C_dA$ (m²)", fontsize=LABEL_FONT_SIZE)
    ax1.set_ylabel("$C_{rr}$", fontsize=LABEL_FONT_SIZE)
    ax1.set_title("All Constraint Lines", fontsize=TITLE_FONT_SIZE, fontweight="bold")
    ax1.tick_params(labelsize=TICK_FONT_SIZE)
    ax1.grid(alpha=0.3)
    from matplotlib.lines import Line2D
    ax1.legend(handles=[
        Line2D([0], [0], color=c0, lw=2, alpha=0.6, label=f"Cluster 0 ({len(idx_0)} seg)"),
        Line2D([0], [0], color=c1, lw=2, alpha=0.6, label=f"Cluster 1 ({len(idx_1)} seg)"),
    ], fontsize=LEGEND_FONT_SIZE)

    # ── 2. 平均线 + CI + 交点 ────────────────────────────────────────────
    ax2 = axes[0, 1]
    ms0 = result["cluster_0_slope_mean"]
    mi0 = result["cluster_0_intercept_mean"]
    ms1 = result["cluster_1_slope_mean"]
    mi1 = result["cluster_1_intercept_mean"]

    line_0 = ms0 * cda_range + mi0
    line_1 = ms1 * cda_range + mi1

    # 95% CI bands
    se_s0 = stats.sem(slopes_0) if len(slopes_0) > 1 else 0
    se_i0 = stats.sem(intercepts_0) if len(intercepts_0) > 1 else 0
    t0 = stats.t.ppf(0.975, max(len(slopes_0) - 1, 1))
    ci_up0 = line_0 + t0 * np.sqrt((cda_range * se_s0)**2 + se_i0**2)
    ci_lo0 = line_0 - t0 * np.sqrt((cda_range * se_s0)**2 + se_i0**2)

    se_s1 = stats.sem(slopes_1) if len(slopes_1) > 1 else 0
    se_i1 = stats.sem(intercepts_1) if len(intercepts_1) > 1 else 0
    t1 = stats.t.ppf(0.975, max(len(slopes_1) - 1, 1))
    ci_up1 = line_1 + t1 * np.sqrt((cda_range * se_s1)**2 + se_i1**2)
    ci_lo1 = line_1 - t1 * np.sqrt((cda_range * se_s1)**2 + se_i1**2)

    ax2.fill_between(cda_range, ci_lo0, ci_up0, color=c0, alpha=0.2, label="95% CI Cluster 0")
    ax2.fill_between(cda_range, ci_lo1, ci_up1, color=c1, alpha=0.2, label="95% CI Cluster 1")

    # CI 交集区域
    ci_int_lo = np.maximum(ci_lo0, ci_lo1)
    ci_int_up = np.minimum(ci_up0, ci_up1)
    ci_mask = ci_int_lo <= ci_int_up
    if ci_mask.any():
        ax2.fill_between(
            cda_range[ci_mask], ci_int_lo[ci_mask], ci_int_up[ci_mask],
            color="orange", alpha=0.4, label="CI Intersection", zorder=3,
        )

    ax2.plot(cda_range, line_0, color=c0, lw=2.5, label=f"Mean Cluster 0 (slope={ms0:.6f})", zorder=4)
    ax2.plot(cda_range, line_1, color=c1, lw=2.5, label=f"Mean Cluster 1 (slope={ms1:.6f})", zorder=4)

    if result["c_da_identified"] is not None and result["c_rr_identified"] is not None:
        cda_id = result["c_da_identified"]
        crr_id = result["c_rr_identified"]
        if params_range["cda_low"] <= cda_id <= params_range["cda_high"]:
            ax2.plot(cda_id, crr_id, "o", color=INTERSECTION_COLOR, ms=10, zorder=5,
                     label=f"C_dA={cda_id:.2f}, C_rr={crr_id:.5f}")

    ax2.set_xlim(params_range["cda_low"], params_range["cda_high"])
    ax2.set_ylim(params_range["crr_low"], params_range["crr_high"])
    ax2.set_xlabel("$C_dA$ (m²)", fontsize=LABEL_FONT_SIZE)
    ax2.set_ylabel("$C_{rr}$", fontsize=LABEL_FONT_SIZE)
    ax2.set_title("Mean Lines + 95% CI", fontsize=TITLE_FONT_SIZE, fontweight="bold")
    ax2.tick_params(labelsize=TICK_FONT_SIZE)
    ax2.legend(fontsize=LEGEND_FONT_SIZE - 2, loc="best")
    ax2.grid(alpha=0.3)

    # ── 3. 斜率分布 ──────────────────────────────────────────────────────
    ax3 = axes[1, 0]
    ax3.hist(slopes_0, bins=20, color=c0, alpha=0.6, label=f"Cluster 0 (n={len(slopes_0)})", edgecolor="k", density=True)
    ax3.hist(slopes_1, bins=20, color=c1, alpha=0.6, label=f"Cluster 1 (n={len(slopes_1)})", edgecolor="k", density=True)
    ax3.axvline(ms0, color=c0, ls="--", lw=2, label=f"μ₀={ms0:.6f}")
    ax3.axvline(ms1, color=c1, ls="--", lw=2, label=f"μ₁={ms1:.6f}")
    ax3.set_xlabel("Slope", fontsize=LABEL_FONT_SIZE)
    ax3.set_ylabel("Density", fontsize=LABEL_FONT_SIZE)
    ax3.set_title("Slope Distribution", fontsize=TITLE_FONT_SIZE, fontweight="bold")
    ax3.tick_params(labelsize=TICK_FONT_SIZE)
    ax3.legend(fontsize=LEGEND_FONT_SIZE - 1)
    ax3.grid(alpha=0.3)

    # ── 4. 截距分布 ──────────────────────────────────────────────────────
    ax4 = axes[1, 1]
    ax4.hist(intercepts_0, bins=20, color=c0, alpha=0.6, label=f"Cluster 0 (n={len(intercepts_0)})", edgecolor="k", density=True)
    ax4.hist(intercepts_1, bins=20, color=c1, alpha=0.6, label=f"Cluster 1 (n={len(intercepts_1)})", edgecolor="k", density=True)
    ax4.axvline(mi0, color=c0, ls="--", lw=2, label=f"μ₀={mi0:.6f}")
    ax4.axvline(mi1, color=c1, ls="--", lw=2, label=f"μ₁={mi1:.6f}")
    ax4.set_xlabel("Intercept", fontsize=LABEL_FONT_SIZE)
    ax4.set_ylabel("Density", fontsize=LABEL_FONT_SIZE)
    ax4.set_title("Intercept Distribution", fontsize=TITLE_FONT_SIZE, fontweight="bold")
    ax4.tick_params(labelsize=TICK_FONT_SIZE)
    ax4.legend(fontsize=LEGEND_FONT_SIZE - 1)
    ax4.grid(alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.99])

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
        logger.info("图保存至: %s", save_path)

    if show_plot:
        plt.show()
    else:
        plt.close(fig)

    return save_path


def plot_mass_histogram(
    constraints: list[dict],
    title: str,
    *,
    save_path: Optional[str] = None,
) -> Optional[str]:
    """质量分布直方图 (按 cluster 着色)。"""
    if not constraints:
        return None

    masses = [c.get("avg_mass", np.nan) for c in constraints]
    clusters = [c.get("cluster", 0) for c in constraints]

    fig, ax = plt.subplots(figsize=(10, 5))
    for cl, color in [(0, LINE_COLOR_CLUSTER_0), (1, LINE_COLOR_CLUSTER_1)]:
        m = [masses[i] for i in range(len(masses)) if clusters[i] == cl and np.isfinite(masses[i])]
        if m:
            ax.hist(m, bins=30, range=(0, 50000), alpha=0.5, color=color,
                    label=f"Cluster {cl} (n={len(m)})")
            mean_m = np.mean(m)
            ax.axvline(mean_m, color=color, ls="--", lw=2)
            ax.text(mean_m, ax.get_ylim()[1] * 0.9, f"{mean_m:.0f} kg",
                    color=color, rotation=90, va="top", ha="right")

    ax.set_xlabel("avg_mass (kg)", fontsize=LABEL_FONT_SIZE)
    ax.set_ylabel("Count", fontsize=LABEL_FONT_SIZE)
    ax.set_title(f"{title}: Mass Distribution by Cluster", fontsize=TITLE_FONT_SIZE)
    ax.legend(fontsize=LEGEND_FONT_SIZE)
    ax.set_xlim(0, 50000)
    fig.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        fig.savefig(save_path, dpi=200)
        logger.info("质量直方图保存至: %s", save_path)

    plt.close(fig)
    return save_path
