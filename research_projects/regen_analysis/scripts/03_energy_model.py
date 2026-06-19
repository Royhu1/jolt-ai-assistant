"""
03_energy_model.py — YK73WFN 再生制动分析：能耗模型参数标定
利用 logger 数据中的 EngSpd + EngTrq 标定 Crr 和 CdA。

方法：
  P_motor = EngTrq% * MaxTorque * EngSpd * 2pi/60  （电机轴功率）
  P_motor * eta_total = F_traction * v
  F_traction = m*a + Crr*m*g + 0.5*rho*CdA*v^2 + m*g*sin(theta)

  改写为线性回归形式：
  P_motor = (1/eta_total) * [Crr * (m*g*v) + CdA * (0.5*rho*v^3) + (m*a*v) + (m*g*sin_theta*v)]

  令 y = P_motor - (m*a*v + m*g*sin_theta*v) / eta_total
      x1 = m*g*v / eta_total
      x2 = 0.5*rho*v^3 / eta_total
  则 y = Crr * x1 + CdA * x2  → 线性最小二乘

  由于 eta_total 未知，使用三参数联合标定：Crr, CdA, eta_total
"""
from __future__ import annotations

import json
import glob
import os
import sys

import numpy as np
import pandas as pd
from scipy.optimize import least_squares
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── 项目路径 ────────────────────────────────────────────────────────────────
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


def apply_style():
    matplotlib.rcParams.update({
        "axes.titlesize": 14, "axes.labelsize": 14,
        "xtick.labelsize": 12, "ytick.labelsize": 12,
        "legend.fontsize": 9, "figure.dpi": 120,
        "savefig.dpi": 300, "savefig.bbox": "tight",
        "axes.grid": True, "grid.alpha": 0.3,
    })


# ── 数据加载 ────────────────────────────────────────────────────────────────
def load_logger_for_calibration(max_files: int = 0) -> pd.DataFrame:
    """加载所有 logger 数据，仅保留用于标定的关键列。"""
    logger_dir = os.path.join(ROOT, CFG["paths"]["logger_dir"])
    files = sorted(glob.glob(os.path.join(logger_dir, "*.csv")))
    if max_files > 0:
        files = files[:max_files]

    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f)
            if df["EngTrq"].isna().all() or df["EngSpd"].isna().all():
                continue
            df["timestamp"] = pd.to_datetime(df["UnixTime"], unit="ms", utc=True)
            df["_source"] = os.path.basename(f)
            dfs.append(df)
        except Exception:
            pass

    if not dfs:
        return pd.DataFrame()
    all_df = pd.concat(dfs, ignore_index=True)
    all_df = all_df.sort_values("timestamp").reset_index(drop=True)
    print(f"[Load] {len(all_df)} rows from {len(dfs)} files")
    return all_df


def prepare_segments(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-trip preprocessing:
    1. Compute acceleration a = dv/dt (1Hz finite difference)
    2. Compute slope sin(theta) = dh/dt / v (time-based to avoid div-by-zero)
    3. Compute motor shaft power P_motor = Torque * omega
    4. Filter: positive traction, cruising (|a| < 0.3), v > 10 km/h
    """
    results = []
    for source, grp in df.groupby("_source"):
        grp = grp.sort_values("timestamp").copy()
        if len(grp) < 20:
            continue

        v_ms = grp["Spd_Kmph_y"].values / 3.6
        dt = grp["timestamp"].diff().dt.total_seconds().values.copy()
        dt[0] = 1.0  # first step = 1s
        dt = np.where(np.isnan(dt) | (dt <= 0), 1.0, dt)

        # Acceleration (m/s^2) — central finite diff with 3-pt smoothing
        v_smooth = pd.Series(v_ms).rolling(3, center=True, min_periods=1).mean().values
        a = np.zeros_like(v_smooth)
        a[1:-1] = (v_smooth[2:] - v_smooth[:-2]) / (dt[1:-1] + dt[2:])
        a[0] = (v_smooth[1] - v_smooth[0]) / dt[1] if dt[1] > 0 else 0
        a[-1] = (v_smooth[-1] - v_smooth[-2]) / dt[-1] if dt[-1] > 0 else 0

        # Slope: dh/dt then sin(theta) = (dh/dt) / v
        h = grp["elevation"].values
        h_smooth = pd.Series(h).rolling(11, center=True, min_periods=1).mean().values
        dhdt = np.zeros_like(h_smooth)
        dhdt[1:] = (h_smooth[1:] - h_smooth[:-1]) / dt[1:]
        # sin(theta) = dhdt / v, but only where v > 1 m/s
        sin_theta = np.where(v_ms > 1.0, dhdt / v_ms, 0.0)
        sin_theta = np.clip(sin_theta, -0.15, 0.15)

        # Motor shaft power (W)
        eng_spd_rpm = grp["EngSpd"].values
        eng_trq_pct = grp["EngTrq"].values
        torque_nm = eng_trq_pct / 100.0 * MAX_TORQUE
        omega = eng_spd_rpm / 60.0 * 2 * np.pi
        P_motor = torque_nm * omega

        grp = grp.copy()
        grp["v_ms"] = v_ms
        grp["a_ms2"] = a
        grp["sin_theta"] = sin_theta
        grp["P_motor_W"] = P_motor
        results.append(grp)

    if not results:
        return pd.DataFrame()
    out = pd.concat(results, ignore_index=True)

    # Filtering: cruising traction points only
    mask = (
        out["v_ms"].notna() &
        (out["v_ms"] > 10 / 3.6) &           # > 10 km/h
        out["a_ms2"].notna() &
        (out["a_ms2"].abs() < 0.3) &          # near-cruise
        out["MassKg"].notna() &
        out["P_motor_W"].notna() &
        (out["P_motor_W"] > 5000) &            # > 5 kW (definite traction)
        out["sin_theta"].notna() &
        np.isfinite(out["sin_theta"]) &
        (out["BrkPedalPos"] < 1) &             # no braking
        (out["BrakeSwitch_CCVS"] == 0)         # brake switch off
    )
    filtered = out.loc[mask].copy().reset_index(drop=True)
    print(f"[Filter] {len(filtered)} rows ({len(filtered)/len(out)*100:.1f}%)")
    return filtered


# ── 参数标定 ────────────────────────────────────────────────────────────────
def calibrate_crr_cda(data: pd.DataFrame) -> dict:
    """
    Joint calibration of Crr, CdA, eta_total using nonlinear least squares.

    Model: P_motor = (m*a + Crr*m*g + 0.5*rho*CdA*v^2 + m*g*sin_theta) * v / eta_total
    """
    v = data["v_ms"].values
    a = data["a_ms2"].values
    m = data["MassKg"].values
    sin_th = data["sin_theta"].values
    P_mot = data["P_motor_W"].values

    def residuals(params):
        crr, cda, eta = params
        F_traction = m * a + crr * m * G + 0.5 * RHO * cda * v**2 + m * G * sin_th
        P_pred = F_traction * v / eta
        # Normalised residual
        res = (P_pred - P_mot) / np.sqrt(P_mot**2 + 1e6)
        return res

    x0 = [0.005, 6.0, 0.25]
    # Bounds: Crr [0.002, 0.015], CdA [2.0, 15.0], eta [0.1, 0.5]
    # eta_total = eta_drivetrain / gear_ratio_factor; for electric truck
    # with reduction gear ratio ~3-5, eta could be quite variable
    result = least_squares(residuals, x0,
                           bounds=([0.002, 2.0, 0.05], [0.015, 15.0, 0.95]),
                           method="trf", loss="soft_l1")

    crr_fit, cda_fit, eta_fit = result.x

    # R^2
    P_pred = (m * a + crr_fit * m * G + 0.5 * RHO * cda_fit * v**2
              + m * G * sin_th) * v / eta_fit
    ss_res = np.sum((P_mot - P_pred) ** 2)
    ss_tot = np.sum((P_mot - P_mot.mean()) ** 2)
    r_sq = 1 - ss_res / ss_tot

    print(f"\n=== Calibration results ===")
    print(f"  Crr        = {crr_fit:.5f}")
    print(f"  CdA        = {cda_fit:.3f} m^2")
    print(f"  eta_total  = {eta_fit:.4f}")
    print(f"  R^2        = {r_sq:.4f}")
    print(f"  N          = {len(data)}")
    print(f"  Mass (median) = {np.median(m):.0f} kg")

    return {
        "crr": round(float(crr_fit), 6),
        "cda": round(float(cda_fit), 4),
        "eta_total": round(float(eta_fit), 4),
        "r_squared": round(float(r_sq), 4),
        "n_samples": len(data),
        "mass_median_kg": round(float(np.median(m)), 0),
    }


def plot_calibration(data: pd.DataFrame, cal: dict):
    """Calibration validation: predicted vs measured power."""
    crr = cal["crr"]
    cda = cal["cda"]
    eta = cal["eta_total"]

    v = data["v_ms"].values
    a = data["a_ms2"].values
    m = data["MassKg"].values
    sin_th = data["sin_theta"].values
    P_mot = data["P_motor_W"].values

    P_pred = (m * a + crr * m * G + 0.5 * RHO * cda * v**2 + m * G * sin_th) * v / eta

    P_mot_kw = P_mot / 1000
    P_pred_kw = P_pred / 1000

    # Downsample for plot
    if len(P_mot_kw) > 20000:
        idx = np.random.RandomState(42).choice(len(P_mot_kw), 20000, replace=False)
        P_mot_kw = P_mot_kw[idx]
        P_pred_kw = P_pred_kw[idx]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Left: scatter
    axes[0].scatter(P_mot_kw, P_pred_kw, s=1, alpha=0.15, color="steelblue", rasterized=True)
    lim = max(np.percentile(P_mot_kw, 99), np.percentile(P_pred_kw, 99)) * 1.05
    axes[0].plot([0, lim], [0, lim], "r--", lw=1.5, label="y = x")
    axes[0].set_xlabel("Measured motor power (kW)")
    axes[0].set_ylabel("Predicted power (kW)")
    axes[0].set_title(f"Calibration validation (R$^2$ = {cal['r_squared']:.3f})")
    axes[0].legend()
    axes[0].set_xlim(0, lim)
    axes[0].set_ylim(0, lim)

    # Right: residual
    residual = P_pred_kw - P_mot_kw
    axes[1].hist(residual, bins=100, color="steelblue", edgecolor="none", alpha=0.8)
    axes[1].set_xlabel("Residual (kW)")
    axes[1].set_ylabel("Count")
    axes[1].set_title(f"Residual distribution (mean={residual.mean():.2f}, std={residual.std():.2f} kW)")
    axes[1].axvline(0, color="red", ls="--", lw=1.5)

    fig.suptitle(f"Crr = {crr:.5f}, CdA = {cda:.3f} m$^2$, $\\eta_{{total}}$ = {eta:.4f}", fontsize=12)
    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "calibration_result.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"  Saved: {out}")


# ── 主函数 ──────────────────────────────────────────────────────────────────
def main():
    apply_style()
    plt.rcParams["font.family"] = "DejaVu Sans"

    print("=" * 60)
    print("YK73WFN Regen Analysis - Step 3: Energy Model Calibration")
    print("=" * 60)

    raw = load_logger_for_calibration()
    if raw.empty:
        print("No valid data.")
        sys.exit(1)

    data = prepare_segments(raw)
    if len(data) < 100:
        print(f"Insufficient data ({len(data)} rows).")
        sys.exit(1)

    cal = calibrate_crr_cda(data)

    # Sanity checks
    if not (0.003 <= cal["crr"] <= 0.008):
        print(f"  [WARNING] Crr={cal['crr']} outside expected [0.003, 0.008]")
    if not (3.0 <= cal["cda"] <= 10.0):
        print(f"  [WARNING] CdA={cal['cda']} outside expected [3.0, 10.0]")

    # Update config
    CFG["physics"]["crr"] = cal["crr"]
    CFG["physics"]["cda"] = cal["cda"]
    CFG["calibration"] = cal
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(CFG, f, indent=2, ensure_ascii=False)
    print(f"\n  config.json updated")

    plot_calibration(data, cal)
    print("\nStep 3 done.")


if __name__ == "__main__":
    main()
