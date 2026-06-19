"""
04_regen_analysis.py -- YK73WFN regenerative braking: per-window analysis

Iteration 3 improvements:
  1. GPS altitude noise: 201-point smoothing + terrain-dominated filter (E_PE/E_KE > 2.0)
  2. Brake type classification per decel event: motor_only / blended / coasting
  3. Time alignment quality: gap_start_s / gap_end_s between telematics and logger timestamps
  4. EngTrq=0 regen candidate analysis
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
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec

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

# Terrain-dominated threshold: if PE/KE > this, flag as terrain-dominated
PE_KE_TERRAIN_THRESHOLD = 2.0

# Smoothing window for GPS altitude (201 pts at 1 Hz ~ 3.4 min)
ELEV_SMOOTH_WINDOW = 201


def apply_style():
    matplotlib.rcParams.update({
        "axes.titlesize": 12, "axes.labelsize": 12,
        "xtick.labelsize": 10, "ytick.labelsize": 10,
        "legend.fontsize": 9, "figure.dpi": 120,
        "savefig.dpi": 300, "savefig.bbox": "tight",
        "axes.grid": True, "grid.alpha": 0.3,
    })


# -- Telematics index + window loader -----------------------------------------
def build_telematics_index() -> pd.DataFrame:
    """Build an index of telematics CSV files for vehicleId=116.

    Stores the calendar DATE of each file (from first-row timestamp) so that
    load_telematics_window() can match by date rather than by precise timestamp.
    This avoids the midnight-UTC first-row problem where daytime windows go unmatched.
    """
    telem_dir = os.path.join(ROOT, "cache", "srf_raw")
    vehicle_id = CFG["vehicle"]["vehicleId"]
    files = sorted(glob.glob(os.path.join(telem_dir, "*.csv")))
    records = []
    for f in files:
        try:
            df = pd.read_csv(f, usecols=["vehicleId", "eventDatetime"], nrows=1)
            if int(df["vehicleId"].iloc[0]) != vehicle_id:
                continue
            t = pd.to_datetime(df["eventDatetime"].iloc[0], utc=True)
            records.append({"file_path": f, "date": t.date()})
        except Exception:
            pass
    if not records:
        return pd.DataFrame(columns=["file_path", "date"])
    return pd.DataFrame(records).sort_values("date").reset_index(drop=True)


def load_telematics_window(telem_idx: pd.DataFrame,
                           t_start, t_end) -> pd.DataFrame:
    """
    Load telematics rows for vehicleId=116 within [t_start, t_end].
    Returns DataFrame with columns [t_rel_s, recup_wh_norm] where
    the first recuperation value is normalised to 0.

    Matches candidate files by date (covering start_date to end_date of the
    window) rather than by a narrow timestamp margin, so daytime windows
    are correctly matched to daily files whose first row is at midnight UTC.
    """
    recup_col = "electric_energy_recuperation_watthours"
    # Include the day before start to catch hourly records that straddle midnight
    start_date = (t_start - pd.Timedelta(hours=1)).date()
    end_date = t_end.date()
    mask = telem_idx["date"].apply(lambda d: start_date <= d <= end_date)
    candidate_files = telem_idx.loc[mask, "file_path"].tolist()
    if not candidate_files:
        return pd.DataFrame()

    dfs = []
    for f in candidate_files:
        try:
            df = pd.read_csv(f, usecols=["eventDatetime", recup_col])
            df["t"] = pd.to_datetime(df["eventDatetime"], utc=True)
            mask2 = (df["t"] >= t_start) & (df["t"] <= t_end)
            sub = df.loc[mask2 & df[recup_col].notna(), ["t", recup_col]].copy()
            if not sub.empty:
                dfs.append(sub)
        except Exception:
            pass

    if not dfs:
        return pd.DataFrame()

    combined = pd.concat(dfs).sort_values("t").drop_duplicates("t").reset_index(drop=True)
    combined["t_rel_s"] = (combined["t"] - t_start).dt.total_seconds()
    # Normalise: first value → 0
    combined["recup_wh_norm"] = combined[recup_col] - combined[recup_col].iloc[0]
    return combined[["t_rel_s", "recup_wh_norm"]]


# -- Logger index + window data -----------------------------------------------
def build_logger_index() -> pd.DataFrame:
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


# -- Brake type classification ------------------------------------------------
def classify_brake_type(df: pd.DataFrame, start_idx: int, end_idx: int) -> str:
    """
    Classify brake type for a decel event using rows [start_idx:end_idx+1].

    Rules:
      - "blended"    : mean BrkPedalPos > 5 (friction + motor braking)
      - "motor_only" : BrkPedalPos <= 5 AND BrakeSwitch_CCVS == 0 (pure motor)
      - "coasting"   : EngTrq == 0 AND BrkPedalPos <= 5 AND no BrakeSwitch
                       (unpowered, gravity/drag decel)
    """
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


# -- Deceleration event detection ---------------------------------------------
def detect_decel_events(df: pd.DataFrame,
                        min_speed_ms: float = 1.0,
                        min_decel_ms2: float = 0.1,
                        min_duration: int = 1) -> list[dict]:
    """
    Detect deceleration events and classify brake type per event.
    Returns list of dicts with KE change, speed bins, brake_type, etc.
    """
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

        v_start = v_smooth[i]
        v_end = v_smooth[j]
        duration = j - i
        if duration < min_duration:
            i = j + 1
            continue
        avg_decel = (v_start - v_end) / max(duration, 1)
        if avg_decel < min_decel_ms2:
            i = j + 1
            continue

        m = df["MassKg"].iloc[i:j + 1].median()
        if pd.isna(m):
            m = CFG.get("calibration", {}).get("mass_median_kg", 20000)
        KE_change = 0.5 * m * (v_start**2 - v_end**2)
        brake_type = classify_brake_type(df, i, j)

        events.append({
            "start_idx": i, "end_idx": j,
            "v_start_ms": v_start, "v_end_ms": v_end,
            "v_start_kmh": v_start * 3.6, "v_end_kmh": v_end * 3.6,
            "duration_s": duration, "avg_decel_ms2": avg_decel,
            "mass_kg": m, "KE_change_J": KE_change,
            "brake_type": brake_type,
        })
        i = j + 1
    return events


# -- Potential energy (downhill) calculation ----------------------------------
def compute_downhill_PE(df: pd.DataFrame) -> float:
    """
    Compute total potential energy recoverable from downhill segments (J).
    PE = m * g * delta_h_down (only negative elevation changes).

    Uses 201-point moving average (improved from 101) to suppress GPS noise.
    At 80 km/h, 201s ~ 4.5 km smoothing window.
    """
    h = df["elevation"].values
    m = df["MassKg"].median()
    if pd.isna(m):
        m = CFG.get("calibration", {}).get("mass_median_kg", 20000)

    h_smooth = pd.Series(h).rolling(ELEV_SMOOTH_WINDOW, center=True, min_periods=1).mean().values
    dh = np.diff(h_smooth)
    downhill_dh = dh[dh < 0]
    PE_down = float(m * G * np.abs(downhill_dh).sum())
    return PE_down


# -- Time alignment quality ---------------------------------------------------
def compute_time_alignment(df: pd.DataFrame, t_telem_start, t_telem_end) -> dict:
    """
    Compute gap between telematics window boundary and actual logger records.
    Returns gap_start_s and gap_end_s (seconds).
    """
    if df.empty:
        return {"gap_start_s": np.nan, "gap_end_s": np.nan, "alignment_quality": "unknown"}

    t_logger_first = df["timestamp"].iloc[0]
    t_logger_last = df["timestamp"].iloc[-1]

    # Ensure both are timezone-aware for subtraction
    gap_start = abs((t_logger_first - t_telem_start).total_seconds())
    gap_end = abs((t_logger_last - t_telem_end).total_seconds())

    quality = "high" if (gap_start < 300 and gap_end < 300) else "low"
    return {
        "gap_start_s": round(gap_start, 1),
        "gap_end_s": round(gap_end, 1),
        "alignment_quality": quality,
    }


# -- Per-window analysis ------------------------------------------------------
def analyse_window(df: pd.DataFrame, delta_recup_wh: float,
                   window_idx: int, t_telem_start=None, t_telem_end=None) -> dict:
    """
    Per-window regen analysis including KE + PE recoverable energy,
    brake type classification, terrain-dominated flag, and time alignment.
    """
    events = detect_decel_events(df)
    total_KE_J = sum(e["KE_change_J"] for e in events)
    total_KE_Wh = total_KE_J / 3600.0

    # Potential energy from downhill (201-pt smoothing)
    PE_down_J = compute_downhill_PE(df)
    PE_down_Wh = PE_down_J / 3600.0

    # Total recoverable energy
    E_recoverable_Wh = total_KE_Wh + PE_down_Wh

    # Terrain-dominated flag (PE/KE > threshold)
    pe_ke_ratio = PE_down_Wh / total_KE_Wh if total_KE_Wh > 0 else np.nan
    terrain_dominated = bool(pd.notna(pe_ke_ratio) and pe_ke_ratio > PE_KE_TERRAIN_THRESHOLD)

    # Observed regen efficiency
    eta_regen_obs = delta_recup_wh / E_recoverable_Wh if E_recoverable_Wh > 0 else np.nan

    # Speed-bin KE breakdown
    speed_bins = {"low_0_30": (0, 30), "mid_30_60": (30, 60), "high_60_plus": (60, 200)}
    speed_analysis = {}
    for label, (lo, hi) in speed_bins.items():
        bin_events = [e for e in events if lo <= e["v_start_kmh"] < hi]
        speed_analysis[label] = {
            "n_events": len(bin_events),
            "total_KE_Wh": sum(e["KE_change_J"] for e in bin_events) / 3600,
        }

    # Brake type breakdown across decel events
    brake_types = {"motor_only": 0, "blended": 0, "coasting": 0}
    brake_type_KE = {"motor_only": 0.0, "blended": 0.0, "coasting": 0.0}
    for e in events:
        bt = e["brake_type"]
        brake_types[bt] += 1
        brake_type_KE[bt] += e["KE_change_J"] / 3600.0

    n_events_total = len(events)
    bt_pct = {}
    bt_ke_pct = {}
    for bt in ["motor_only", "blended", "coasting"]:
        bt_pct[bt] = round(brake_types[bt] / n_events_total * 100, 2) if n_events_total > 0 else 0.0
        bt_ke_pct[bt] = round(brake_type_KE[bt] / total_KE_Wh * 100, 2) if total_KE_Wh > 0 else 0.0

    # Brake condition (row-level)
    total_rows = len(df)
    braking_rows = (df["BrkPedalPos"] > 5).sum()
    switch_rows = (df["BrakeSwitch_CCVS"] == 1).sum()
    coasting_rows = ((df["BrkPedalPos"] <= 5) & (df["BrakeSwitch_CCVS"] == 0)
                     & (df["Spd_Kmph_y"] > 0)).sum()

    eng_trq_zero = (df["EngTrq"] == 0).sum()

    # EngTrq during decel events
    decel_trq_vals = []
    for e in events:
        trqs = df["EngTrq"].iloc[e["start_idx"]:e["end_idx"] + 1]
        decel_trq_vals.extend(trqs.dropna().tolist())
    avg_decel_trq = np.mean(decel_trq_vals) if decel_trq_vals else np.nan

    # Elevation change
    h = df["elevation"].dropna()
    elev_change = h.iloc[-1] - h.iloc[0] if len(h) > 1 else 0

    # Time alignment quality
    align = {}
    if t_telem_start is not None and t_telem_end is not None:
        align = compute_time_alignment(df, t_telem_start, t_telem_end)
    else:
        align = {"gap_start_s": np.nan, "gap_end_s": np.nan, "alignment_quality": "unknown"}

    return {
        "window_idx": window_idx,
        "n_decel_events": n_events_total,
        "total_KE_Wh": round(total_KE_Wh, 2),
        "PE_down_Wh": round(PE_down_Wh, 2),
        "pe_ke_ratio": round(float(pe_ke_ratio), 3) if pd.notna(pe_ke_ratio) else np.nan,
        "terrain_dominated": terrain_dominated,
        "E_recoverable_Wh": round(E_recoverable_Wh, 2),
        "delta_recup_wh": round(delta_recup_wh, 2),
        "eta_regen_obs": round(eta_regen_obs, 4) if pd.notna(eta_regen_obs) else np.nan,
        "elev_change_m": round(float(elev_change), 1),
        "braking_pedal_pct": round(braking_rows / total_rows * 100, 2),
        "brake_switch_pct": round(switch_rows / total_rows * 100, 2),
        "coasting_pct": round(coasting_rows / total_rows * 100, 2),
        "eng_trq_zero_pct": round(eng_trq_zero / total_rows * 100, 2),
        "avg_decel_trq_pct": round(avg_decel_trq, 2) if pd.notna(avg_decel_trq) else np.nan,
        # Brake type event counts and KE share
        "n_motor_only": brake_types["motor_only"],
        "n_blended": brake_types["blended"],
        "n_coasting": brake_types["coasting"],
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
        **{f"KE_{k}_Wh": round(v["total_KE_Wh"], 2) for k, v in speed_analysis.items()},
        **{f"n_events_{k}": v["n_events"] for k, v in speed_analysis.items()},
    }


# -- Window visualisation -----------------------------------------------------
def plot_window(df: pd.DataFrame, events: list[dict],
                delta_recup_wh: float, window_idx: int, analysis: dict,
                telem_ts: pd.DataFrame | None = None):
    """4-panel validation figure per window.

    telem_ts: DataFrame with columns [t_rel_s, recup_wh_norm], telematics
              recuperation values normalised to 0 at window start.
              If None or empty, falls back to a horizontal reference line.
    """
    # Use actual UTC timestamps as x-axis so panels show clock time (HH:MM:SS)
    t = df["timestamp"]
    t0 = t.iloc[0]   # window origin, used to convert telematics t_rel_s

    fig = plt.figure(figsize=(14, 10))
    gs = GridSpec(4, 1, hspace=0.35)

    # Pre-compute elevation smoothing (used in Panel 1 and Panel 4)
    h_raw = df["elevation"].values
    h_smooth = pd.Series(h_raw).rolling(ELEV_SMOOTH_WINDOW, center=True, min_periods=1).mean().values

    # Panel 1: Speed (left) + Elevation (right twin) + decel event spans
    ax1 = fig.add_subplot(gs[0])
    ax1.plot(t, df["Spd_Kmph_y"], color="steelblue", lw=0.8, label="Speed (km/h)")
    bt_colours = {"motor_only": "green", "blended": "red", "coasting": "orange"}
    for e in events:
        ax1.axvspan(t.iloc[e["start_idx"]], t.iloc[e["end_idx"]],
                    alpha=0.2, color=bt_colours.get(e["brake_type"], "grey"))
    ax1.set_ylabel("Speed (km/h)")
    terrain_tag = " [TERRAIN-DOM]" if analysis.get("terrain_dominated") else ""
    ax1.set_title(f"Window {window_idx}: {len(events)} decel events{terrain_tag}")
    ax1_twin = ax1.twinx()
    ax1_twin.plot(t, h_raw, color="brown", lw=0.5, alpha=0.3, label="Elevation (raw)")
    ax1_twin.plot(t, h_smooth, color="saddlebrown", lw=1.2, label="Elevation (201-pt smooth)")
    ax1_twin.set_ylabel("Elevation (m)")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax1_twin.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right")

    # Panel 2: Brake pedal + switch
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax2.plot(t, df["BrkPedalPos"], color="coral", lw=0.8, label="BrkPedalPos (%)")
    ax2_twin = ax2.twinx()
    ax2_twin.plot(t, df["BrakeSwitch_CCVS"], color="green", lw=0.8,
                  alpha=0.6, label="BrakeSwitch")
    ax2.set_ylabel("BrkPedalPos (%)")
    ax2_twin.set_ylabel("BrakeSwitch")
    ax2_twin.set_ylim(-0.1, 1.5)
    lines1, labels1 = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2_twin.get_legend_handles_labels()
    ax2.legend(lines1 + lines2, labels1 + labels2, loc="upper right")

    # Panel 3: Motor shaft power = Torque × EngSpd (kW)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    trq_nm = df["EngTrq"] / 100.0 * MAX_TORQUE
    omega_rad_s = df["EngSpd"] * (2 * np.pi / 60.0)
    power_kw = trq_nm * omega_rad_s / 1000.0
    ax3.plot(t, power_kw, color="purple", lw=0.8, label="Motor power (kW)")
    ax3.axhline(0, color="grey", ls="--", lw=0.8)
    ax3.set_ylabel("Motor power (kW)")
    lines1, labels1 = ax3.get_legend_handles_labels()
    ax3.legend(lines1, labels1, loc="upper right")

    # Panel 4: Cumulative regen energy (model vs telematics)
    ax4 = fig.add_subplot(gs[3], sharex=ax1)
    eta_regen = CFG["physics"]["eta_regen"]
    model_cumul = np.zeros(len(t))
    for e in events:
        regen_wh = e["KE_change_J"] * eta_regen / 3600.0
        model_cumul[e["end_idx"]:] += regen_wh
    dh = np.diff(h_smooth)
    m = df["MassKg"].median()
    if pd.isna(m):
        m = CFG.get("calibration", {}).get("mass_median_kg", 20000)
    pe_cumul = np.zeros(len(t))
    for idx in range(len(dh)):
        if dh[idx] < 0:
            pe_cumul[idx + 1:] += abs(dh[idx]) * m * G * eta_regen / 3600.0

    total_model = model_cumul + pe_cumul
    ax4.plot(t, model_cumul, color="blue", lw=1.2, ls="--",
             label=f"KE only (eta={eta_regen})")
    ax4.plot(t, total_model, color="blue", lw=1.5,
             label=f"KE + PE (eta={eta_regen})")
    # Telematics recuperation signal: straight line normalised to 0 at window start
    has_telem_curve = (telem_ts is not None and not telem_ts.empty
                       and len(telem_ts) >= 2)
    if has_telem_curve:
        # Prepend (0, 0) so the line starts from the window origin
        t_rel = telem_ts["t_rel_s"].values
        r_pts = telem_ts["recup_wh_norm"].values
        if t_rel[0] > 0:
            t_rel = np.concatenate([[0.0], t_rel])
            r_pts = np.concatenate([[0.0], r_pts])
        # Convert relative seconds to absolute timestamps for x-axis alignment
        t_abs = [t0 + pd.Timedelta(seconds=float(s)) for s in t_rel]
        ax4.plot(t_abs, r_pts, color="red", lw=1.8,
                 label=f"Telematics ({len(telem_ts)} pts)")
        telem_abs = [t0 + pd.Timedelta(seconds=float(s))
                     for s in telem_ts["t_rel_s"].values]
        ax4.scatter(telem_abs, telem_ts["recup_wh_norm"].values,
                    color="red", s=40, zorder=5)
    else:
        # Fallback: straight line from window start to window end
        ax4.plot([t0, t.iloc[-1]], [0, delta_recup_wh],
                 color="red", lw=1.5, ls="--",
                 label=f"Telematics linear ({delta_recup_wh:.0f} Wh)")
        ax4.scatter([t0, t.iloc[-1]], [0, delta_recup_wh],
                    color="red", s=40, zorder=5)
    ax4.set_xlabel("Time (UTC)")
    ax4.set_ylabel("Cumulative regen (Wh)")
    eta_obs = analysis.get("eta_regen_obs", float("nan"))
    eta_str = f"{eta_obs:.3f}" if pd.notna(eta_obs) else "N/A"
    align_str = f"gap={analysis.get('gap_start_s', 'N/A'):.0f}s" if pd.notna(analysis.get('gap_start_s', np.nan)) else ""
    ax4.set_title(
        f"Model KE+PE={total_model[-1]:.0f} Wh, "
        f"Telem={delta_recup_wh:.0f} Wh, "
        f"eta_obs={eta_str}  {align_str}"
    )
    ax4.legend(loc="upper left")

    # Apply HH:MM:SS clock-time format to x-axis (shared across all panels)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    fig.autofmt_xdate(rotation=30, ha="right")

    out = os.path.join(FIGURES_DIR, f"window_{window_idx:03d}.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"  Saved: {out}")


# -- Main ---------------------------------------------------------------------
def main():
    apply_style()
    plt.rcParams["font.family"] = "DejaVu Sans"

    print("=" * 60)
    print("YK73WFN Regen Analysis - Step 4: Per-Window Analysis (iter3)")
    print("=" * 60)

    windows_path = os.path.join(TABLES_DIR, "valid_windows.csv")
    if not os.path.exists(windows_path):
        print(f"Missing {windows_path}, run 02_find_windows.py first")
        sys.exit(1)
    windows = pd.read_csv(windows_path)
    windows["t_start"] = pd.to_datetime(windows["t_start"])
    windows["t_end"] = pd.to_datetime(windows["t_end"])

    # Select top 10 by delta_recup_wh
    if len(windows) > 10:
        selected = windows.nlargest(10, "delta_recup_wh")
    else:
        selected = windows
    print(f"Analysing {len(selected)} windows")

    logger_idx = build_logger_index()
    telem_idx = build_telematics_index()
    print(f"Telematics index: {len(telem_idx)} files for vehicleId={CFG['vehicle']['vehicleId']}")

    all_results = []
    for _, win in selected.iterrows():
        idx = int(win["window_idx"])
        print(f"\n--- Window {idx} ({win['t_start']} ~ {win['t_end']}, "
              f"delta_recup={win['delta_recup_wh']:.0f} Wh) ---")

        df = load_logger_window(logger_idx, win["t_start"], win["t_end"])
        if df.empty or len(df) < 10:
            print(f"  Insufficient logger data, skipping")
            continue

        analysis = analyse_window(df, win["delta_recup_wh"], idx,
                                  t_telem_start=win["t_start"],
                                  t_telem_end=win["t_end"])
        all_results.append(analysis)
        terrain_tag = " [TERRAIN-DOM]" if analysis["terrain_dominated"] else ""
        print(f"  Decel events: {analysis['n_decel_events']}, "
              f"KE={analysis['total_KE_Wh']:.0f} Wh, "
              f"PE_down={analysis['PE_down_Wh']:.0f} Wh (PE/KE={analysis['pe_ke_ratio']}), "
              f"E_recov={analysis['E_recoverable_Wh']:.0f} Wh, "
              f"eta={analysis['eta_regen_obs']}{terrain_tag}")
        print(f"  BrakeType: motor_only={analysis['pct_motor_only']}%, "
              f"blended={analysis['pct_blended']}%, "
              f"coasting={analysis['pct_coasting']}%")
        print(f"  Alignment: gap_start={analysis['gap_start_s']}s, "
              f"gap_end={analysis['gap_end_s']}s "
              f"[{analysis['alignment_quality']}]")

        events = detect_decel_events(df)
        telem_ts = load_telematics_window(telem_idx, win["t_start"], win["t_end"])
        print(f"  Telematics points in window: {len(telem_ts)}")
        plot_window(df, events, win["delta_recup_wh"], idx, analysis,
                    telem_ts=telem_ts)

    if all_results:
        results_df = pd.DataFrame(all_results)
        out_path = os.path.join(TABLES_DIR, "window_analysis_detail.csv")
        results_df.to_csv(out_path, index=False)
        print(f"\nResults saved: {out_path}")
    else:
        print("No windows analysed.")

    print("\nStep 4 done.")


if __name__ == "__main__":
    main()
