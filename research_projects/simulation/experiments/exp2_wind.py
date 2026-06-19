"""
Exp 2 — 风速对 EP 的影响（随机风向积分）
变量：V_wind 0 → 15 m/s，步长 1 m/s
其余参数保持基准值
"""
from __future__ import annotations
import sys, pathlib
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from scipy.stats import linregress

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'simulation'))
from models.vehicle_physics import compute_ep, BASELINE, apply_style, FIG_W, FIG_H, DPI, FS_LEGEND

RESULTS_FIG  = ROOT / 'simulation' / 'results' / 'figures' / 'exp2_wind.png'
RESULTS_TABLE= ROOT / 'simulation' / 'results' / 'tables'  / 'exp2_wind.csv'


def run() -> dict:
    winds = np.arange(0, 16, 1, dtype=float)   # m/s
    eps   = [compute_ep(m=BASELINE['m'], v_wind=v)['EP'] for v in winds]
    eps   = np.array(eps)
    ep0   = eps[0]

    # 理论预期：ΔEP ∝ V_wind²
    delta_ep  = eps - ep0
    v2        = winds**2

    # 线性拟合 ΔEP vs V²（跳过 V=0 点以防零）
    mask = v2 > 0
    slope, intercept, r, _, _ = linregress(v2[mask], delta_ep[mask])
    alpha2 = slope   # kWh/(km·(m/s)²)

    # 保存表格
    df = pd.DataFrame({'V_wind_ms': winds, 'EP_kWh_per_km': eps,
                       'delta_EP': delta_ep})
    df.to_csv(RESULTS_TABLE, index=False)

    # ── 图表（双子图）───────────────────────────────────────────────────────
    apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(FIG_W * 1.2, FIG_H * 0.75), dpi=DPI)

    # Left: EP vs V_wind
    axes[0].scatter(winds, eps, color='steelblue', zorder=5)
    axes[0].set_xlabel('Wind speed $V_{wind}$ (m/s)')
    axes[0].set_ylabel('EP (kWh/km)')
    axes[0].set_title('EP vs Wind Speed')

    # Right: ΔEP vs V² (verify quadratic)
    axes[1].scatter(v2, delta_ep, color='steelblue', zorder=5, label='Simulation')
    fit_x2 = np.linspace(0, 225, 100)
    axes[1].plot(fit_x2, slope * fit_x2 + intercept, 'r--',
                 label=f'α₂ = {alpha2:.4f} kWh/(km·(m/s)²)\nR² = {r**2:.5f}')
    axes[1].set_xlabel('$V_{wind}^2$ (m²/s²)')
    axes[1].set_ylabel('ΔEP (kWh/km)')
    axes[1].set_title('ΔEP vs $V_{wind}^2$ (quadratic relationship)')
    axes[1].legend(fontsize=FS_LEGEND)

    fig.suptitle('Exp 2 — Effect of Wind Speed on Energy Performance', fontsize=14)
    fig.tight_layout()
    fig.savefig(RESULTS_FIG, dpi=DPI, bbox_inches='tight')
    plt.close(fig)

    return dict(
        alpha2       = alpha2,
        alpha2_units = 'kWh/(km·(m/s)²)',
        r_squared    = r**2,
        winds        = winds,
        eps          = eps,
    )


if __name__ == '__main__':
    res = run()
    print(f'Exp 2 完成: α₂ = {res["alpha2"]:.6f} kWh/(km·(m/s)²),  R² = {res["r_squared"]:.6f}')
