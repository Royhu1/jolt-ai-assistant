"""
01_data_explore.py — YK73WFN 再生制动分析：数据探索
统计 logger / telematics 数据的基本特征，输出探索性图表。
"""
from __future__ import annotations

import json
import glob
import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── 项目根目录 ──────────────────────────────────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CFG_PATH = os.path.join(ROOT, "research_projects", "regen_analysis", "config.json")
with open(CFG_PATH, encoding="utf-8") as f:
    CFG = json.load(f)

FIGURES_DIR = os.path.join(ROOT, CFG["paths"]["figures_dir"])
TABLES_DIR = os.path.join(ROOT, CFG["paths"]["tables_dir"])
os.makedirs(FIGURES_DIR, exist_ok=True)
os.makedirs(TABLES_DIR, exist_ok=True)

# ── 绘图样式（与 simulation/models/vehicle_physics.py 一致）──────────────────
FIG_W, FIG_H = 10, 6
DPI = 300
FS_LABEL = 14
FS_TITLE = 14
FS_TICK = 12
FS_LEGEND = 9
GRID_ALPHA = 0.3


def apply_style():
    """统一图表样式。"""
    matplotlib.rcParams.update({
        "axes.titlesize": FS_TITLE,
        "axes.labelsize": FS_LABEL,
        "xtick.labelsize": FS_TICK,
        "ytick.labelsize": FS_TICK,
        "legend.fontsize": FS_LEGEND,
        "figure.dpi": 120,
        "savefig.dpi": DPI,
        "savefig.bbox": "tight",
        "axes.grid": True,
        "grid.alpha": GRID_ALPHA,
    })


# ── Logger 数据加载 ──────────────────────────────────────────────────────────
def load_all_logger(max_files: int = 0) -> pd.DataFrame:
    """加载所有 logger CSV 文件并拼接。"""
    logger_dir = os.path.join(ROOT, CFG["paths"]["logger_dir"])
    files = sorted(glob.glob(os.path.join(logger_dir, "*.csv")))
    if max_files > 0:
        files = files[:max_files]
    print(f"[Logger] 发现 {len(files)} 个文件")

    dfs = []
    skipped = 0
    for f in files:
        try:
            df = pd.read_csv(f)
            # 跳过 EngTrq 全 NaN 的文件
            if df["EngTrq"].isna().all():
                skipped += 1
                continue
            df["_source_file"] = os.path.basename(f)
            dfs.append(df)
        except Exception as e:
            print(f"  跳过 {os.path.basename(f)}: {e}")
            skipped += 1

    print(f"  有效文件: {len(dfs)}, 跳过: {skipped}")
    if not dfs:
        return pd.DataFrame()
    all_df = pd.concat(dfs, ignore_index=True)
    # 转换 UnixTime（毫秒）为 UTC 时间戳
    all_df["timestamp"] = pd.to_datetime(all_df["UnixTime"], unit="ms", utc=True)
    return all_df


# ── Telematics 数据加载 ──────────────────────────────────────────────────────
def load_telematics(vehicle_id: int = 116) -> pd.DataFrame:
    """加载指定 vehicleId 的所有 telematics 数据。"""
    srf_dir = os.path.join(ROOT, CFG["paths"]["srf_raw_dir"])
    all_files = sorted(glob.glob(os.path.join(srf_dir, "*.csv")))
    print(f"[Telematics] 扫描 {len(all_files)} 个文件中 vehicleId={vehicle_id} ...")

    dfs = []
    for f in all_files:
        try:
            tmp = pd.read_csv(f, nrows=1, usecols=["vehicleId"])
            if int(tmp["vehicleId"].iloc[0]) == vehicle_id:
                df = pd.read_csv(f, low_memory=False)
                dfs.append(df)
        except Exception:
            pass

    if not dfs:
        print("  未找到任何匹配文件！")
        return pd.DataFrame()

    all_df = pd.concat(dfs, ignore_index=True)
    all_df["eventDatetime"] = pd.to_datetime(all_df["eventDatetime"])
    all_df = all_df.sort_values("eventDatetime").reset_index(drop=True)
    print(f"  总行数: {len(all_df)}, 文件数: {len(dfs)}")
    return all_df


# ── 统计输出 ────────────────────────────────────────────────────────────────
def summarise_logger(df: pd.DataFrame) -> dict:
    """Logger 数据统计摘要。"""
    cols = CFG["logger_cols"]
    summary = {
        "total_rows": len(df),
        "files": df["_source_file"].nunique(),
        "time_min": str(df["timestamp"].min()),
        "time_max": str(df["timestamp"].max()),
    }
    for label, col in cols.items():
        if col in df.columns:
            valid = df[col].notna().sum()
            summary[f"{label}_valid_pct"] = round(valid / len(df) * 100, 2)
    print("\n=== Logger 数据统计 ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return summary


def summarise_telematics(df: pd.DataFrame) -> dict:
    """Telematics 数据统计摘要。"""
    recup_col = CFG["telematics_cols"]["recup_wh"]
    recup_valid = df[recup_col].notna()
    summary = {
        "total_rows": len(df),
        "time_min": str(df["eventDatetime"].min()),
        "time_max": str(df["eventDatetime"].max()),
        "recup_valid_rows": int(recup_valid.sum()),
        "recup_valid_pct": round(recup_valid.sum() / len(df) * 100, 2),
    }
    if recup_valid.any():
        r = df.loc[recup_valid, recup_col]
        summary["recup_min_wh"] = float(r.min())
        summary["recup_max_wh"] = float(r.max())
        summary["recup_range_kwh"] = round((r.max() - r.min()) / 1000, 2)
    # 采样间隔分析
    dt = df["eventDatetime"].diff().dt.total_seconds()
    summary["sampling_interval_median_s"] = float(dt.median())
    summary["sampling_interval_mean_s"] = round(float(dt.mean()), 1)
    summary["sampling_interval_std_s"] = round(float(dt.std()), 1)

    print("\n=== Telematics 数据统计 ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return summary


# ── 图表 ────────────────────────────────────────────────────────────────────
def plot_brk_pedal_hist(df: pd.DataFrame):
    """BrkPedalPos 分布直方图。"""
    col = "BrkPedalPos"
    data = df[col].dropna()
    # 排除 0 值（静止/未制动时），单独统计
    nonzero = data[data > 0]
    zero_pct = (data == 0).sum() / len(data) * 100

    fig, axes = plt.subplots(1, 2, figsize=(FIG_W, FIG_H * 0.7))
    # 左：全数据
    axes[0].hist(data, bins=100, color="steelblue", edgecolor="none", alpha=0.8)
    axes[0].set_xlabel("BrkPedalPos (%)")
    axes[0].set_ylabel("Count")
    axes[0].set_title(f"Brake pedal position distribution (all, N={len(data):,})")
    axes[0].text(0.95, 0.95, f"Zero: {zero_pct:.1f}%",
                 transform=axes[0].transAxes, ha="right", va="top",
                 fontsize=FS_LEGEND + 1, bbox=dict(boxstyle="round", fc="wheat"))

    # Right: non-zero
    if len(nonzero) > 0:
        axes[1].hist(nonzero, bins=50, color="coral", edgecolor="none", alpha=0.8)
        axes[1].set_xlabel("BrkPedalPos (%)")
        axes[1].set_ylabel("Count")
        axes[1].set_title(f"Brake pedal position (non-zero, N={len(nonzero):,})")
        median_val = nonzero.median()
        axes[1].axvline(median_val, color="red", ls="--", lw=1.5,
                        label=f"Median = {median_val:.1f}%")
        axes[1].legend()

    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "brk_pedal_hist.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"  保存: {out}")


def plot_eng_trq_vs_speed(df: pd.DataFrame):
    """EngTrq vs Speed 散点图（色彩表示 BrkPedalPos）。"""
    mask = df["EngTrq"].notna() & df["Spd_Kmph_y"].notna()
    sub = df.loc[mask].copy()
    # 下采样到最多 50000 点
    if len(sub) > 50000:
        sub = sub.sample(50000, random_state=42)

    # 实际扭矩 Nm
    sub["TorqueNm"] = sub["EngTrq"] / 100.0 * CFG["vehicle"]["max_torque_nm"]

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    sc = ax.scatter(
        sub["Spd_Kmph_y"], sub["TorqueNm"],
        c=sub["BrkPedalPos"], cmap="RdYlGn_r",
        s=2, alpha=0.4, rasterized=True,
    )
    cbar = fig.colorbar(sc, ax=ax, label="BrkPedalPos (%)")
    ax.set_xlabel("Speed (km/h)")
    ax.set_ylabel("Motor torque (Nm)")
    ax.set_title("Motor torque vs speed (colour = brake pedal position)")
    ax.axhline(0, color="grey", ls="--", lw=0.8)

    out = os.path.join(FIGURES_DIR, "eng_trq_vs_speed.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"  保存: {out}")


def plot_telematics_sampling(df: pd.DataFrame):
    """Telematics 采样间隔直方图。"""
    dt = df["eventDatetime"].diff().dt.total_seconds().dropna()
    # 限制到 0~7200s（2小时）
    dt_clip = dt[dt.between(0, 7200)]

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H * 0.6))
    ax.hist(dt_clip / 60, bins=120, color="teal", edgecolor="none", alpha=0.8)
    ax.set_xlabel("Sampling interval (min)")
    ax.set_ylabel("Count")
    ax.set_title(f"Telematics sampling interval distribution (N={len(dt_clip):,})")
    ax.axvline(60, color="red", ls="--", lw=1.5, label="60 min")
    ax.legend()

    out = os.path.join(FIGURES_DIR, "telematics_sampling_interval.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"  保存: {out}")


def plot_eng_trq_distribution(df: pd.DataFrame):
    """EngTrq 百分比分布直方图（区分正/负扭矩区间）。"""
    col = "EngTrq"
    data = df[col].dropna()

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H * 0.7))
    ax.hist(data, bins=100, color="steelblue", edgecolor="none", alpha=0.8)
    ax.set_xlabel("EngTrq (%)")
    ax.set_ylabel("Count")
    ax.set_title(f"Motor torque percentage distribution (N={len(data):,})")
    median_val = data.median()
    ax.axvline(median_val, color="red", ls="--", lw=1.5,
               label=f"Median = {median_val:.1f}%")
    ax.legend()

    out = os.path.join(FIGURES_DIR, "eng_trq_distribution.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"  保存: {out}")


# ── 主函数 ──────────────────────────────────────────────────────────────────
def main():
    apply_style()
    plt.rcParams["font.family"] = "DejaVu Sans"

    print("=" * 60)
    print("YK73WFN 再生制动分析 — Step 1: 数据探索")
    print("=" * 60)

    # Logger
    logger_df = load_all_logger()
    if logger_df.empty:
        print("Logger 数据为空，退出。")
        sys.exit(1)
    logger_summary = summarise_logger(logger_df)

    # Telematics
    tele_df = load_telematics(CFG["vehicle"]["vehicleId"])
    if tele_df.empty:
        print("Telematics 数据为空，退出。")
        sys.exit(1)
    tele_summary = summarise_telematics(tele_df)

    # 时间重叠分析
    logger_min = logger_df["timestamp"].min()
    logger_max = logger_df["timestamp"].max()
    tele_min = tele_df["eventDatetime"].min()
    tele_max = tele_df["eventDatetime"].max()
    overlap_start = max(logger_min, tele_min)
    overlap_end = min(logger_max, tele_max)
    print(f"\n=== 时间重叠 ===")
    print(f"  Logger:     {logger_min} → {logger_max}")
    print(f"  Telematics: {tele_min} → {tele_max}")
    print(f"  重叠区间:   {overlap_start} → {overlap_end}")

    # 图表
    print("\n生成图表 ...")
    plot_brk_pedal_hist(logger_df)
    plot_eng_trq_vs_speed(logger_df)
    plot_eng_trq_distribution(logger_df)
    plot_telematics_sampling(tele_df)

    # 保存摘要
    combined = {"logger": logger_summary, "telematics": tele_summary}
    summary_path = os.path.join(TABLES_DIR, "data_explore_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n摘要已保存: {summary_path}")
    print("Step 1 完成。")


if __name__ == "__main__":
    main()
