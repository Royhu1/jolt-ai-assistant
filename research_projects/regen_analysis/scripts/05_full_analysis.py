"""
05_full_analysis.py -- YK73WFN regenerative braking: full-dataset statistics

Iteration 3 improvements:
  1. GPS noise: 201-pt smoothing; terrain-dominated filter (PE/KE > 2.0)
     Output two eta sets: all windows vs non-terrain-dominated
  2. Brake type classification: motor_only / blended / coasting per event
     Stacked bar chart of KE by brake type
  3. Speed range x brake type cross-analysis (4 speed bins: <30/30-60/60-80/>80)
  4. EngTrq=0 regen candidate analysis -> regen_candidate_analysis.csv
  5. Time alignment quality: gap_start_s / gap_end_s; high-quality filter
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

# -- Paths --------------------------------------------------------------------
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CFG_PATH = os.path.join(ROOT, "research_projects", "regen_analysis", "config.json")
with open(CFG_PATH, encoding="utf-8") as f:
    CFG = json.load(f)

FIGURES_DIR = os.path.join(ROOT, CFG["paths"]["figures_dir"])
TABLES_DIR = os.path.join(ROOT, CFG["paths"]["tables_dir"])
os.makedirs(FIGURES_DIR, exist_ok=True)
os.makedirs(TABLES_DIR, exist_ok=True)

G = CFG["physics"]["g"]
RHO = CFG["physics"]["rho"]
MAX_TORQUE = CFG["vehicle"]["max_torque_nm"]

PE_KE_TERRAIN_THRESHOLD = 2.0
ELEV_SMOOTH_WINDOW = 201


def apply_style():
    matplotlib.rcParams.update({
        "axes.titlesize": 14, "axes.labelsize": 14,
        "xtick.labelsize": 12, "ytick.labelsize": 12,
        "legend.fontsize": 9, "figure.dpi": 120,
        "savefig.dpi": 300, "savefig.bbox": "tight",
        "axes.grid": True, "grid.alpha": 0.3,
    })


# -- Reused functions (iter3 versions) ----------------------------------------
def build_logger_index():
    logger_dir = os.path.join(ROOT, CFG["paths"]["logger_dir"])
    files = sorted(glob.glob(os.path.join(logger_dir, "*.csv")))
    records = []
    for f in files:
        try:
            df = pd.read_csv(f, usecols=["UnixTime", "EngTrq"])
            if df["EngTrq"].isna().all():
                continue
            ts = pd.to_datetime(df["UnixTime"], unit="ms", utc=True)
            records.append({"file_path": f, "start_ts": ts.min(), "end_ts": ts.max()})
        except Exception:
            pass
    return pd.DataFrame(records).sort_values("start_ts").reset_index(drop=True)


def load_logger_window(logger_idx, t_start, t_end):
    overlap = logger_idx[
        (logger_idx["end_ts"] >= t_start) & (logger_idx["start_ts"] <= t_end)
    ]
    if overlap.empty:
        return pd.DataFrame()
    dfs = []
    for _, row in overlap.iterrows():
        df = pd.read_csv(row["file_path"])
        df["timestamp"] = pd.to_datetime(df["UnixTime"], unit="ms", utc=True)
        mask = (df["timestamp"] >= t_start) & (df["timestamp"] <= t_end)
        dfs.append(df.loc[mask])
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True).sort_values("timestamp").reset_index(drop=True)


def classify_brake_type(df: pd.DataFrame, start_idx: int, end_idx: int) -> str:
    seg = df.iloc[start_idx:end_idx + 1]
    mean_pedal = seg["BrkPedalPos"].mean()
    mean_switch = seg["BrakeSwitch_CCVS"].mean()
    mean_trq = seg["EngTrq"].mean()
    if mean_pedal > 5:
        return "blended"
    elif mean_trq == 0 and mean_pedal <= 5 and mean_switch < 0.1:
        return "coasting"
    else:
        return "motor_only"


def detect_decel_events(df, min_speed_ms=1.0, min_decel_ms2=0.1, min_duration=1):
    v = df["Spd_Kmph_y"].values / 3.6
    v_smooth = pd.Series(v).rolling(3, center=True, min_periods=1).mean().values
    events = []
    i = 0
    n = len(v_smooth)
    while i < n - 1:
        if v_smooth[i] < min_speed_ms or v_smooth[i + 1] >= v_smooth[i]:
            i += 1
            continue
        j = i + 1
        while j < n - 1 and v_smooth[j + 1] < v_smooth[j]:
            j += 1
        v_start, v_end = v_smooth[i], v_smooth[j]
        duration = j - i
        if duration < min_duration:
            i = j + 1
            continue
        avg_decel = (v_start - v_end) / max(duration, 1)
        if avg_decel < min_decel_ms2:
            i = j + 1
            continue
        m = df["MassKg"].iloc[i:j+1].median()
        if pd.isna(m):
            m = CFG.get("calibration", {}).get("mass_median_kg", 20000)
        brake_type = classify_brake_type(df, i, j)
        events.append({
            "start_idx": i, "end_idx": j,
            "v_start_ms": v_start, "v_end_ms": v_end,
            "v_start_kmh": v_start * 3.6, "v_end_kmh": v_end * 3.6,
            "duration_s": duration, "avg_decel_ms2": avg_decel,
            "mass_kg": m, "KE_change_J": 0.5 * m * (v_start**2 - v_end**2),
            "brake_type": brake_type,
        })
        i = j + 1
    return events


def compute_downhill_PE(df):
    """201-pt smoothing to suppress GPS noise."""
    h = df["elevation"].values
    m = df["MassKg"].median()
    if pd.isna(m):
        m = CFG.get("calibration", {}).get("mass_median_kg", 20000)
    h_smooth = pd.Series(h).rolling(ELEV_SMOOTH_WINDOW, center=True, min_periods=1).mean().values
    dh = np.diff(h_smooth)
    return float(m * G * np.abs(dh[dh < 0]).sum())


def compute_time_alignment(df, t_telem_start, t_telem_end):
    if df.empty:
        return {"gap_start_s": np.nan, "gap_end_s": np.nan, "alignment_quality": "unknown"}
    t_logger_first = df["timestamp"].iloc[0]
    t_logger_last = df["timestamp"].iloc[-1]
    gap_start = abs((t_logger_first - t_telem_start).total_seconds())
    gap_end = abs((t_logger_last - t_telem_end).total_seconds())
    quality = "high" if (gap_start < 300 and gap_end < 300) else "low"
    return {"gap_start_s": round(gap_start, 1), "gap_end_s": round(gap_end, 1),
            "alignment_quality": quality}


# -- Batch analysis (iter3) ---------------------------------------------------
def batch_analyse(windows, logger_idx):
    results = []
    # Accumulate all decel events for regen candidate and speed-x-brake analyses
    all_events_records = []

    n = len(windows)
    for i, (_, win) in enumerate(windows.iterrows()):
        if (i + 1) % 20 == 0 or i == 0:
            print(f"  Processing window {i+1}/{n} ...")

        t_start = win["t_start"]
        t_end = win["t_end"]
        df = load_logger_window(logger_idx, t_start, t_end)
        if df.empty or len(df) < 10:
            continue

        events = detect_decel_events(df)
        total_KE_Wh = sum(e["KE_change_J"] for e in events) / 3600.0
        PE_down_Wh = compute_downhill_PE(df) / 3600.0
        E_recov = total_KE_Wh + PE_down_Wh

        # Terrain-dominated flag
        pe_ke_ratio = PE_down_Wh / total_KE_Wh if total_KE_Wh > 0 else np.nan
        terrain_dominated = bool(pd.notna(pe_ke_ratio) and pe_ke_ratio > PE_KE_TERRAIN_THRESHOLD)

        delta_recup = win["delta_recup_wh"]
        eta = delta_recup / E_recov if E_recov > 0 else np.nan

        # Speed-bin KE (4 bins for iter3: <30, 30-60, 60-80, >80)
        speed_bins_4 = {
            "v_0_30": (0, 30), "v_30_60": (30, 60),
            "v_60_80": (60, 80), "v_80_plus": (80, 300),
        }
        KE_by_speed4 = {k: 0.0 for k in speed_bins_4}
        n_by_speed4 = {k: 0 for k in speed_bins_4}

        # Legacy 3-bin for backwards compat
        KE_by_speed = {"low_0_30": 0.0, "mid_30_60": 0.0, "high_60_plus": 0.0}
        n_by_speed = {"low_0_30": 0, "mid_30_60": 0, "high_60_plus": 0}

        # Brake type counts and KE
        bt_n = {"motor_only": 0, "blended": 0, "coasting": 0}
        bt_ke = {"motor_only": 0.0, "blended": 0.0, "coasting": 0.0}

        for e in events:
            v = e["v_start_kmh"]
            ke = e["KE_change_J"] / 3600.0
            bt = e["brake_type"]

            # 3-bin legacy
            k3 = "low_0_30" if v < 30 else ("mid_30_60" if v < 60 else "high_60_plus")
            KE_by_speed[k3] += ke
            n_by_speed[k3] += 1

            # 4-bin
            for k4, (lo, hi) in speed_bins_4.items():
                if lo <= v < hi:
                    KE_by_speed4[k4] += ke
                    n_by_speed4[k4] += 1
                    break

            # Brake type
            bt_n[bt] += 1
            bt_ke[bt] += ke

            # Record for cross-analysis
            all_events_records.append({
                "window_idx": int(win["window_idx"]),
                "v_start_kmh": v,
                "KE_Wh": ke,
                "brake_type": bt,
            })

        n_events_total = len(events)
        bt_pct = {bt: round(bt_n[bt] / n_events_total * 100, 2)
                  if n_events_total > 0 else 0.0 for bt in bt_n}
        bt_ke_pct = {bt: round(bt_ke[bt] / total_KE_Wh * 100, 2)
                     if total_KE_Wh > 0 else 0.0 for bt in bt_ke}

        # Brake conditions (row-level)
        total_rows = len(df)
        brake_pedal = (df["BrkPedalPos"] > 5).sum()
        brake_switch = (df["BrakeSwitch_CCVS"] == 1).sum()
        moving = (df["Spd_Kmph_y"] > 0).sum()
        eng_trq_zero_moving = ((df["EngTrq"] == 0) & (df["Spd_Kmph_y"] > 0)).sum()

        # Elevation
        h = df["elevation"].dropna()
        elev_change = h.iloc[-1] - h.iloc[0] if len(h) > 1 else 0

        # Time alignment
        align = compute_time_alignment(df, t_start, t_end)

        results.append({
            "window_idx": int(win["window_idx"]),
            "t_start": t_start,
            "duration_min": win["duration_min"],
            "delta_recup_wh": delta_recup,
            "total_KE_Wh": round(total_KE_Wh, 2),
            "PE_down_Wh": round(PE_down_Wh, 2),
            "pe_ke_ratio": round(float(pe_ke_ratio), 3) if pd.notna(pe_ke_ratio) else np.nan,
            "terrain_dominated": terrain_dominated,
            "E_recoverable_Wh": round(E_recov, 2),
            "eta_regen_obs": round(eta, 4) if pd.notna(eta) else np.nan,
            "n_decel_events": n_events_total,
            "max_speed_kmh": win["max_speed_kmh"],
            "mean_speed_kmh": win.get("mean_speed_kmh", np.nan),
            "mass_kg": win.get("mass_median_kg", np.nan),
            "elev_change_m": round(float(elev_change), 1),
            "brake_pedal_pct": round(brake_pedal / total_rows * 100, 2),
            "brake_switch_pct": round(brake_switch / total_rows * 100, 2),
            "eng_trq_zero_moving_pct": round(eng_trq_zero_moving / max(moving, 1) * 100, 2),
            # Brake type
            "n_motor_only": bt_n["motor_only"],
            "n_blended": bt_n["blended"],
            "n_coasting": bt_n["coasting"],
            "pct_motor_only": bt_pct["motor_only"],
            "pct_blended": bt_pct["blended"],
            "pct_coasting": bt_pct["coasting"],
            "KE_pct_motor_only": bt_ke_pct["motor_only"],
            "KE_pct_blended": bt_ke_pct["blended"],
            "KE_pct_coasting": bt_ke_pct["coasting"],
            # Time alignment
            "gap_start_s": align["gap_start_s"],
            "gap_end_s": align["gap_end_s"],
            "alignment_quality": align["alignment_quality"],
            # Legacy 3-bin
            **{f"KE_{k}_Wh": round(v2, 2) for k, v2 in KE_by_speed.items()},
            **{f"n_events_{k}": v2 for k, v2 in n_by_speed.items()},
            # 4-bin
            **{f"KE_{k}_Wh": round(v2, 2) for k, v2 in KE_by_speed4.items()},
            **{f"n_events_{k}": v2 for k, v2 in n_by_speed4.items()},
        })

    events_df = pd.DataFrame(all_events_records) if all_events_records else pd.DataFrame()
    return pd.DataFrame(results), events_df


# -- EngTrq=0 regen candidate analysis ----------------------------------------
def analyse_regen_candidates(windows, logger_idx):
    """
    Improved 4: identify regen candidate periods (EngTrq=0, speed>5kmh, decel).
    Outputs regen_candidate_analysis.csv and comparison figure.
    """
    print("\nAnalysing EngTrq=0 regen candidates ...")
    candidate_rows = []
    decel_all_rows = []

    n = len(windows)
    for i, (_, win) in enumerate(windows.iterrows()):
        if (i + 1) % 30 == 0 or i == 0:
            print(f"  Candidate scan {i+1}/{n} ...")
        df = load_logger_window(logger_idx, win["t_start"], win["t_end"])
        if df.empty or len(df) < 10:
            continue

        # Compute acceleration proxy (diff of smoothed speed)
        v_ms = df["Spd_Kmph_y"].values / 3.6
        v_smooth = pd.Series(v_ms).rolling(3, center=True, min_periods=1).mean().values
        a = np.gradient(v_smooth)  # m/s per sample (1 Hz => m/s^2)

        is_regen_candidate = (
            (df["Spd_Kmph_y"].values > 5) &
            (df["EngTrq"].values == 0) &
            (a < -0.05)
        )
        is_decel_all = (
            (df["Spd_Kmph_y"].values > 5) &
            (a < -0.05)
        )

        rc_df = df[is_regen_candidate]
        da_df = df[is_decel_all]

        for _, row in rc_df.iterrows():
            candidate_rows.append({
                "window_idx": int(win["window_idx"]),
                "speed_kmh": row["Spd_Kmph_y"],
                "BrkPedalPos": row["BrkPedalPos"],
                "EngTrq": row["EngTrq"],
                "source": "regen_candidate",
            })
        for _, row in da_df.iterrows():
            decel_all_rows.append({
                "window_idx": int(win["window_idx"]),
                "speed_kmh": row["Spd_Kmph_y"],
                "BrkPedalPos": row["BrkPedalPos"],
                "EngTrq": row["EngTrq"],
                "source": "all_decel",
            })

    combined = pd.concat([
        pd.DataFrame(candidate_rows),
        pd.DataFrame(decel_all_rows),
    ], ignore_index=True)

    out_path = os.path.join(TABLES_DIR, "regen_candidate_analysis.csv")
    combined.to_csv(out_path, index=False)
    print(f"  Regen candidate table saved: {out_path}")

    # Summary stats
    rc = pd.DataFrame(candidate_rows)
    da = pd.DataFrame(decel_all_rows)
    if rc.empty or da.empty:
        print("  Insufficient data for candidate analysis.")
        return

    print(f"  Regen candidate rows: {len(rc)}, All-decel rows: {len(da)}")
    print(f"  Candidate share of all decel: {len(rc)/len(da)*100:.1f}%")
    print(f"  Candidate speed median: {rc['speed_kmh'].median():.1f} km/h")
    print(f"  Candidate BrkPedalPos median: {rc['BrkPedalPos'].median():.1f}%")

    # Figure: speed and BrkPedalPos distributions
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    bins_spd = np.arange(0, 110, 5)
    axes[0].hist(rc["speed_kmh"], bins=bins_spd, alpha=0.6,
                 color="steelblue", label="Regen candidate (EngTrq=0, decel)")
    axes[0].hist(da["speed_kmh"], bins=bins_spd, alpha=0.4,
                 color="coral", label="All decel periods")
    axes[0].set_xlabel("Speed (km/h)")
    axes[0].set_ylabel("Row count")
    axes[0].set_title("Speed distribution: regen candidates vs all decel")
    axes[0].legend()

    bins_ped = np.arange(0, 105, 5)
    axes[1].hist(rc["BrkPedalPos"], bins=bins_ped, alpha=0.6,
                 color="steelblue", label="Regen candidate")
    axes[1].set_xlabel("BrkPedalPos (%)")
    axes[1].set_ylabel("Row count")
    axes[1].set_title("Brake pedal position during regen candidates")
    axes[1].legend()

    fig.tight_layout()
    out_fig = os.path.join(FIGURES_DIR, "regen_candidate_analysis.png")
    fig.savefig(out_fig)
    plt.close(fig)
    print(f"  Figure saved: {out_fig}")


# -- Plots (iter3) ------------------------------------------------------------
def plot_eta_distribution_dual(df):
    """Two sets: all windows vs non-terrain-dominated."""
    eta_all = df["eta_regen_obs"].dropna()
    eta_all = eta_all[(eta_all > 0) & (eta_all < 1.5)]
    eta_notd = df.loc[~df["terrain_dominated"], "eta_regen_obs"].dropna()
    eta_notd = eta_notd[(eta_notd > 0) & (eta_notd < 1.5)]

    fig, axes = plt.subplots(1, 2, figsize=(16, 6), sharey=False)

    for ax, eta, label in [
        (axes[0], eta_all, "All windows"),
        (axes[1], eta_notd, "Non-terrain-dominated"),
    ]:
        ax.hist(eta, bins=30, color="steelblue", edgecolor="white", alpha=0.8)
        ax.set_xlabel("Observed regen efficiency")
        ax.set_ylabel("Window count")
        ax.set_title(f"{label} (N={len(eta)}, median={eta.median():.3f})")
        ax.axvline(eta.median(), color="red", ls="--", lw=1.5,
                   label=f"Median = {eta.median():.3f}")
        ax.axvline(0.9, color="orange", ls=":", lw=1.5, label="Theoretical = 0.9")
        ax.legend()

    fig.suptitle("Regen efficiency distribution: all vs non-terrain-dominated")
    out = os.path.join(FIGURES_DIR, "eta_regen_distribution_dual.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"  Saved: {out}")


def plot_eta_distribution(df):
    """Legacy single-panel eta distribution."""
    eta = df["eta_regen_obs"].dropna()
    eta_valid = eta[(eta > 0) & (eta < 1.5)]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(eta_valid, bins=30, color="steelblue", edgecolor="white", alpha=0.8)
    ax.set_xlabel("Observed regen efficiency")
    ax.set_ylabel("Window count")
    ax.set_title(f"Regen efficiency distribution (N={len(eta_valid)}, "
                 f"median={eta_valid.median():.3f}, mean={eta_valid.mean():.3f})")
    ax.axvline(eta_valid.median(), color="red", ls="--", lw=1.5,
               label=f"Median = {eta_valid.median():.3f}")
    ax.axvline(0.9, color="orange", ls=":", lw=1.5, label="Theoretical = 0.9")
    ax.legend()
    out = os.path.join(FIGURES_DIR, "eta_regen_distribution.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"  Saved: {out}")


def plot_brake_type_stacked(df):
    """Stacked bar chart: KE by brake type across all windows."""
    mask = df["eta_regen_obs"].notna() & (df["eta_regen_obs"] > 0) & (df["eta_regen_obs"] < 1.5)
    sub = df[mask]

    ke_motor = sub["KE_pct_motor_only"].mean()
    ke_blended = sub["KE_pct_blended"].mean()
    ke_coasting = sub["KE_pct_coasting"].mean()

    # Also compute absolute Wh totals
    total_ke = sub["total_KE_Wh"].sum()
    abs_motor = sub.apply(lambda r: r["total_KE_Wh"] * r["KE_pct_motor_only"] / 100, axis=1).sum()
    abs_blended = sub.apply(lambda r: r["total_KE_Wh"] * r["KE_pct_blended"] / 100, axis=1).sum()
    abs_coasting = sub.apply(lambda r: r["total_KE_Wh"] * r["KE_pct_coasting"] / 100, axis=1).sum()

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    # Left: mean % stacked bar
    labels_bt = ["motor_only", "blended", "coasting"]
    vals_pct = [ke_motor, ke_blended, ke_coasting]
    colours = ["#2196F3", "#F44336", "#FF9800"]
    bottom = 0
    for label, val, col in zip(labels_bt, vals_pct, colours):
        axes[0].bar(["Brake type\nKE share (%)"], val, bottom=bottom,
                    color=col, alpha=0.85, label=label)
        if val > 2:
            axes[0].text(0, bottom + val / 2, f"{val:.1f}%", ha="center",
                         va="center", fontsize=12, color="white", fontweight="bold")
        bottom += val
    axes[0].set_ylim(0, 110)
    axes[0].set_ylabel("Mean KE share (%)")
    axes[0].set_title("Recoverable KE distribution by brake type\n(mean across windows)")
    axes[0].legend(loc="upper right")

    # Right: absolute kWh
    abs_vals = [abs_motor / 1000, abs_blended / 1000, abs_coasting / 1000]
    x = range(len(labels_bt))
    bars = axes[1].bar(labels_bt, abs_vals, color=colours, alpha=0.85)
    axes[1].set_ylabel("Total recoverable KE (kWh)")
    axes[1].set_title("Total recoverable KE by brake type\n(all valid windows)")
    for bar, val in zip(bars, abs_vals):
        axes[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                     f"{val:.0f} kWh", ha="center", fontsize=11)

    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "brake_type_ke_distribution.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"  Saved: {out}")


def plot_speed_x_brake_type(events_df):
    """
    Improvement 3: speed range x brake type cross-analysis.
    4 speed bins x 3 brake types, grouped bar chart.
    """
    if events_df.empty:
        print("  No events data for speed-x-brake analysis.")
        return

    speed_bins = [
        ("< 30 km/h", 0, 30),
        ("30-60 km/h", 30, 60),
        ("60-80 km/h", 60, 80),
        ("> 80 km/h", 80, 300),
    ]
    brake_types = ["motor_only", "blended", "coasting"]
    colours = {"motor_only": "#2196F3", "blended": "#F44336", "coasting": "#FF9800"}

    # Event count matrix
    count_matrix = {}
    ke_matrix = {}
    for label, lo, hi in speed_bins:
        seg = events_df[(events_df["v_start_kmh"] >= lo) & (events_df["v_start_kmh"] < hi)]
        n_total = len(seg)
        ke_total = seg["KE_Wh"].sum()
        count_matrix[label] = {}
        ke_matrix[label] = {}
        for bt in brake_types:
            n_bt = (seg["brake_type"] == bt).sum()
            ke_bt = seg.loc[seg["brake_type"] == bt, "KE_Wh"].sum()
            count_matrix[label][bt] = n_bt / n_total * 100 if n_total > 0 else 0
            ke_matrix[label][bt] = ke_bt / ke_total * 100 if ke_total > 0 else 0

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    x = np.arange(len(speed_bins))
    width = 0.25

    for ax, matrix, ylabel, title in [
        (axes[0], count_matrix, "Event count share (%)",
         "Brake type distribution by speed range\n(event count %)"),
        (axes[1], ke_matrix, "KE share (%)",
         "Brake type KE distribution by speed range\n(KE share %)"),
    ]:
        for j, bt in enumerate(brake_types):
            vals = [matrix[lb][bt] for lb, _, _ in speed_bins]
            bars = ax.bar(x + j * width, vals, width, label=bt,
                          color=colours[bt], alpha=0.85)
            for bar, val in zip(bars, vals):
                if val > 3:
                    ax.text(bar.get_x() + bar.get_width() / 2,
                            bar.get_height() + 0.5, f"{val:.0f}%",
                            ha="center", va="bottom", fontsize=9)
        ax.set_xticks(x + width)
        ax.set_xticklabels([lb for lb, _, _ in speed_bins])
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend()
        ax.set_ylim(0, 110)

    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "speed_x_brake_type.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"  Saved: {out}")


def plot_eta_vs_speed(df):
    mask = df["eta_regen_obs"].notna() & (df["eta_regen_obs"] > 0) & (df["eta_regen_obs"] < 1.5)
    sub = df[mask]
    fig, ax = plt.subplots(figsize=(10, 6))
    sc = ax.scatter(sub["max_speed_kmh"], sub["eta_regen_obs"],
                    c=sub["mass_kg"], cmap="viridis", s=30, alpha=0.7, edgecolors="none")
    if sub["mass_kg"].notna().any():
        fig.colorbar(sc, ax=ax, label="Mass (kg)")
    ax.set_xlabel("Max speed in window (km/h)")
    ax.set_ylabel("Observed regen efficiency")
    ax.set_title("Regen efficiency vs max window speed")
    ax.axhline(0.9, color="orange", ls=":", lw=1.5, label="Theoretical limit")
    ax.legend()
    out = os.path.join(FIGURES_DIR, "eta_vs_max_speed.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"  Saved: {out}")


def plot_brake_condition_analysis(df):
    mask = df["eta_regen_obs"].notna() & (df["eta_regen_obs"] > 0) & (df["eta_regen_obs"] < 1.5)
    sub = df[mask]
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    axes[0].scatter(sub["brake_pedal_pct"], sub["eta_regen_obs"],
                    s=20, alpha=0.6, color="coral")
    axes[0].set_xlabel("Brake pedal press ratio (%)")
    axes[0].set_ylabel("Observed regen efficiency")
    axes[0].set_title("Regen efficiency vs brake pedal usage")

    ke_cols = ["KE_low_0_30_Wh", "KE_mid_30_60_Wh", "KE_high_60_plus_Wh"]
    labels = ["<30 km/h", "30-60 km/h", ">60 km/h"]
    ke_sums = [sub[c].sum() for c in ke_cols]
    total_ke = sum(ke_sums)
    pcts = [k / total_ke * 100 if total_ke > 0 else 0 for k in ke_sums]
    bars = axes[1].bar(labels, pcts, color=["#4daf4a", "#ff7f00", "#e41a1c"], alpha=0.8)
    axes[1].set_ylabel("KE recoverable share (%)")
    axes[1].set_title("Recoverable KE by speed range (3-bin)")
    for bar, pct in zip(bars, pcts):
        axes[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                     f"{pct:.1f}%", ha="center", fontsize=11)
    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "brake_condition_analysis.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"  Saved: {out}")


def plot_speed_regen_comparison(df):
    mask = df["eta_regen_obs"].notna() & (df["eta_regen_obs"] > 0) & (df["eta_regen_obs"] < 1.5)
    sub = df[mask].copy()
    sub["speed_group"] = sub["max_speed_kmh"].apply(
        lambda x: ">60 km/h" if x > 60 else "<=60 km/h")
    groups = sub.groupby("speed_group")["eta_regen_obs"]
    data = [g.values for _, g in groups]
    labels = [name for name, _ in groups]

    fig, ax = plt.subplots(figsize=(8, 6))
    bp = ax.boxplot(data, labels=labels, patch_artist=True)
    colours = ["#4daf4a", "#ff7f00"]
    for patch, colour in zip(bp["boxes"], colours):
        patch.set_facecolor(colour)
        patch.set_alpha(0.6)
    ax.set_ylabel("Observed regen efficiency")
    ax.set_title("High speed vs low speed regen efficiency")
    for i2, (name, grp) in enumerate(groups):
        ax.text(i2 + 1, ax.get_ylim()[1] * 0.95,
                f"N={len(grp)}\nmed={grp.median():.3f}",
                ha="center", va="top", fontsize=10)
    out = os.path.join(FIGURES_DIR, "speed_regen_comparison.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"  Saved: {out}")


def plot_telematics_sampling_error(df):
    mask = df["eta_regen_obs"].notna() & (df["eta_regen_obs"] > 0)
    sub = df[mask]
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    axes[0].scatter(sub["E_recoverable_Wh"], sub["delta_recup_wh"],
                    s=20, alpha=0.6, color="steelblue")
    lim = max(sub["E_recoverable_Wh"].max(), sub["delta_recup_wh"].max()) * 1.1
    x_line = np.linspace(0, lim, 100)
    for eta_line in [0.5, 0.7, 0.9]:
        axes[0].plot(x_line, eta_line * x_line, "--", lw=1, label=f"eta={eta_line}")
    axes[0].set_xlabel("Recoverable energy (Wh)")
    axes[0].set_ylabel("Telematics delta recuperation (Wh)")
    axes[0].set_title("Energy budget: model vs telematics")
    axes[0].legend()
    axes[0].set_xlim(0, lim)
    axes[0].set_ylim(0, lim)

    axes[1].scatter(sub["duration_min"], sub["eta_regen_obs"],
                    s=20, alpha=0.6, color="coral")
    axes[1].set_xlabel("Window duration (min)")
    axes[1].set_ylabel("Observed regen efficiency")
    axes[1].set_title("Sampling error: eta vs window duration")
    axes[1].axhline(0.9, color="orange", ls=":", lw=1.5)

    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "telematics_sampling_error.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"  Saved: {out}")


def plot_eng_trq_zero_analysis(df):
    mask = df["eta_regen_obs"].notna() & (df["eta_regen_obs"] > 0) & (df["eta_regen_obs"] < 1.5)
    sub = df[mask]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(sub["eng_trq_zero_moving_pct"], sub["eta_regen_obs"],
               s=20, alpha=0.6, color="purple")
    ax.set_xlabel("EngTrq=0 while moving (%)")
    ax.set_ylabel("Observed regen efficiency")
    ax.set_title("Regen efficiency vs zero-torque time (regen indicator)")
    out = os.path.join(FIGURES_DIR, "eng_trq_zero_vs_eta.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"  Saved: {out}")


def plot_alignment_quality(df):
    """Improvement 5: time alignment quality summary."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    gap_s = df["gap_start_s"].dropna()
    gap_e = df["gap_end_s"].dropna()

    axes[0].hist(gap_s, bins=30, color="steelblue", alpha=0.7, label="gap_start_s")
    axes[0].hist(gap_e, bins=30, color="coral", alpha=0.7, label="gap_end_s")
    axes[0].axvline(300, color="red", ls="--", lw=1.5, label="5-min threshold")
    axes[0].set_xlabel("Time gap (s)")
    axes[0].set_ylabel("Window count")
    axes[0].set_title("Telematics-logger time alignment gaps")
    axes[0].legend()

    # Eta comparison by alignment quality
    high_q = df.loc[df["alignment_quality"] == "high", "eta_regen_obs"].dropna()
    high_q = high_q[(high_q > 0) & (high_q < 1.5)]
    low_q = df.loc[df["alignment_quality"] == "low", "eta_regen_obs"].dropna()
    low_q = low_q[(low_q > 0) & (low_q < 1.5)]
    data = [g.values for g in [high_q, low_q] if len(g) > 0]
    labels = []
    if len(high_q) > 0:
        labels.append(f"High quality\n(N={len(high_q)})")
    if len(low_q) > 0:
        labels.append(f"Low quality\n(N={len(low_q)})")

    if data:
        bp = axes[1].boxplot(data, labels=labels, patch_artist=True)
        colours_aq = ["#4daf4a", "#e41a1c"]
        for patch, c in zip(bp["boxes"], colours_aq[:len(data)]):
            patch.set_facecolor(c)
            patch.set_alpha(0.6)
        axes[1].set_ylabel("Observed regen efficiency")
        axes[1].set_title("Regen efficiency by alignment quality")

    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "time_alignment_quality.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"  Saved: {out}")


# -- Summary table (iter3) ----------------------------------------------------
def generate_summary_table(df):
    mask = df["eta_regen_obs"].notna() & (df["eta_regen_obs"] > 0) & (df["eta_regen_obs"] < 1.5)
    valid = df[mask]
    valid_notd = valid[~valid["terrain_dominated"]]
    valid_hq = valid[valid["alignment_quality"] == "high"]

    terrain_count = valid["terrain_dominated"].sum()
    low_align_count = (valid["alignment_quality"] == "low").sum()

    summary = {
        "Total valid windows": len(df),
        "Windows with eta in (0, 1.5)": len(valid),
        "Terrain-dominated windows (PE/KE > 2.0)": int(terrain_count),
        "Low alignment quality windows (gap > 5 min)": int(low_align_count),
        "--- All valid windows ---": "",
        "eta_regen mean (all)": round(valid["eta_regen_obs"].mean(), 4) if len(valid) > 0 else "N/A",
        "eta_regen median (all)": round(valid["eta_regen_obs"].median(), 4) if len(valid) > 0 else "N/A",
        "eta_regen std (all)": round(valid["eta_regen_obs"].std(), 4) if len(valid) > 0 else "N/A",
        "--- Non-terrain-dominated ---": "",
        "N (non-terrain-dom)": len(valid_notd),
        "eta_regen mean (non-TD)": round(valid_notd["eta_regen_obs"].mean(), 4) if len(valid_notd) > 0 else "N/A",
        "eta_regen median (non-TD)": round(valid_notd["eta_regen_obs"].median(), 4) if len(valid_notd) > 0 else "N/A",
        "eta_regen std (non-TD)": round(valid_notd["eta_regen_obs"].std(), 4) if len(valid_notd) > 0 else "N/A",
        "--- High alignment quality ---": "",
        "N (high alignment)": len(valid_hq),
        "eta_regen median (high-align)": round(valid_hq["eta_regen_obs"].median(), 4) if len(valid_hq) > 0 else "N/A",
        "--- Energy budget ---": "",
        "Total recoverable KE (kWh)": round(valid["total_KE_Wh"].sum() / 1000, 2),
        "Total recoverable PE (kWh)": round(valid["PE_down_Wh"].sum() / 1000, 2),
        "Total actual recuperation (kWh)": round(valid["delta_recup_wh"].sum() / 1000, 2),
        "--- Brake types (event count %) ---": "",
        "Mean motor_only event %": round(valid["pct_motor_only"].mean(), 1) if len(valid) > 0 else "N/A",
        "Mean blended event %": round(valid["pct_blended"].mean(), 1) if len(valid) > 0 else "N/A",
        "Mean coasting event %": round(valid["pct_coasting"].mean(), 1) if len(valid) > 0 else "N/A",
        "--- Brake types (KE %) ---": "",
        "Mean motor_only KE %": round(valid["KE_pct_motor_only"].mean(), 1) if len(valid) > 0 else "N/A",
        "Mean blended KE %": round(valid["KE_pct_blended"].mean(), 1) if len(valid) > 0 else "N/A",
        "Mean coasting KE %": round(valid["KE_pct_coasting"].mean(), 1) if len(valid) > 0 else "N/A",
        "--- Other metrics ---": "",
        "Mean window duration (min)": round(valid["duration_min"].mean(), 1),
        "Mean decel events per window": round(valid["n_decel_events"].mean(), 1),
        "Mean brake pedal usage (%)": round(valid["brake_pedal_pct"].mean(), 1),
        "Mean EngTrq=0 while moving (%)": round(valid["eng_trq_zero_moving_pct"].mean(), 1),
    }
    return pd.DataFrame([summary]).T.rename(columns={0: "Value"})


# -- Main ---------------------------------------------------------------------
def main():
    apply_style()
    plt.rcParams["font.family"] = "DejaVu Sans"

    print("=" * 60)
    print("YK73WFN Regen Analysis - Step 5: Full Statistics (iter3)")
    print("=" * 60)

    windows_path = os.path.join(TABLES_DIR, "valid_windows.csv")
    if not os.path.exists(windows_path):
        print(f"Missing {windows_path}")
        sys.exit(1)
    windows = pd.read_csv(windows_path)
    windows["t_start"] = pd.to_datetime(windows["t_start"])
    windows["t_end"] = pd.to_datetime(windows["t_end"])
    print(f"Total {len(windows)} valid windows")

    logger_idx = build_logger_index()

    print("\nBatch analysing ...")
    results, events_df = batch_analyse(windows, logger_idx)
    if results.empty:
        print("No results.")
        sys.exit(1)
    print(f"\nAnalysed: {len(results)} windows")

    # Print terrain-dominated and alignment quality summary
    td_count = results["terrain_dominated"].sum()
    hq_count = (results["alignment_quality"] == "high").sum()
    lq_count = (results["alignment_quality"] == "low").sum()
    print(f"Terrain-dominated windows (PE/KE > {PE_KE_TERRAIN_THRESHOLD}): {td_count}")
    print(f"High alignment quality: {hq_count}, Low: {lq_count}")

    out_path = os.path.join(TABLES_DIR, "full_analysis_results.csv")
    results.to_csv(out_path, index=False)
    print(f"Results saved: {out_path}")

    # Save events table for cross-analysis
    if not events_df.empty:
        events_path = os.path.join(TABLES_DIR, "all_decel_events.csv")
        events_df.to_csv(events_path, index=False)
        print(f"Events table saved: {events_path}")

    print("\nGenerating plots ...")
    plot_eta_distribution(results)
    plot_eta_distribution_dual(results)
    plot_eta_vs_speed(results)
    plot_brake_condition_analysis(results)
    plot_speed_regen_comparison(results)
    plot_telematics_sampling_error(results)
    plot_eng_trq_zero_analysis(results)
    plot_brake_type_stacked(results)
    plot_speed_x_brake_type(events_df)
    plot_alignment_quality(results)

    # EngTrq=0 regen candidate analysis (improvement 4)
    analyse_regen_candidates(windows, logger_idx)

    summary = generate_summary_table(results)
    summary_path = os.path.join(TABLES_DIR, "summary_statistics.csv")
    summary.to_csv(summary_path)
    print(f"\nSummary saved: {summary_path}")
    print(summary.to_string())
    print("\nStep 5 done.")


if __name__ == "__main__":
    main()
