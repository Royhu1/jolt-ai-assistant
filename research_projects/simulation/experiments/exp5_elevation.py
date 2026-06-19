"""
Exp 5 — 净海拔变化对 EP 的影响
变量：Δh -200 → +200 m，步长 20 m
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

RESULTS_FIG  = ROOT / 'simulation' / 'results' / 'figures' / 'exp5_elevation.png'
RESULTS_TABLE= ROOT / 'simulation' / 'results' / 'tables'  / 'exp5_elevation.csv'


def run() -> dict:
    delta_hs = np.arange(-200, 201, 20, dtype=float)   # m
    eps      = np.array([compute_ep(m=BASELINE['m'], delta_h=dh)['EP'] for dh in delta_hs])
    ep0      = compute_ep(m=BASELINE['m'])['EP']
    delta_ep = eps - ep0

    # 分段线性拟合（上坡 / 下坡分别拟合）
    mask_up   = delta_hs > 0
    mask_down = delta_hs < 0

    slope_up, ic_up, r_up, _, _     = linregress(delta_hs[mask_up],   eps[mask_up])
    slope_down, ic_down, r_down, _, _ = linregress(delta_hs[mask_down], eps[mask_down])

    alpha4_plus  = slope_up    # kWh/(km·m)
    alpha4_minus = slope_down  # kWh/(km·m)  (不含再生制动：与 α₄⁺ 对称)

    # 理论解析值（不含再生：上下坡均经过驱动系效率 eta_dt，对称）
    m, g    = BASELINE['m'], BASELINE['g']
    eta_dt  = BASELINE['eta_dt']
    d       = BASELINE['d_total']
    _J_TO_KWH = 1 / 3_600_000
    alpha4_plus_theory  =  m * g / (eta_dt * d) * 1000 * _J_TO_KWH  # kWh/(km·m)
    alpha4_minus_theory = -m * g / (eta_dt * d) * 1000 * _J_TO_KWH  # kWh/(km·m)

    # 保存表格
    df = pd.DataFrame({
        'delta_h_m'     : delta_hs,
        'EP_kWh_per_km' : eps,
        'delta_EP'      : delta_ep,
    })
    df.to_csv(RESULTS_TABLE, index=False)

    # ── 图表 ────────────────────────────────────────────────────────────────
    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)

    ax.scatter(delta_hs, eps, color='steelblue', zorder=5, label='Simulation')

    # Uphill fit line
    dh_up_fit = np.linspace(0, 200, 100)
    ax.plot(dh_up_fit, slope_up * dh_up_fit + ic_up, 'r--',
            label=f'Uphill α₄⁺ = {alpha4_plus * 1e4:.3f}×10⁻⁴ kWh/(km·m),  R² = {r_up**2:.5f}')

    # Downhill fit line
    dh_down_fit = np.linspace(-200, 0, 100)
    ax.plot(dh_down_fit, slope_down * dh_down_fit + ic_down, 'g--',
            label=f'Downhill α₄⁻ = {alpha4_minus * 1e4:.3f}×10⁻⁴ kWh/(km·m),  R² = {r_down**2:.5f}')

    ax.axvline(x=0, color='gray', linestyle=':', linewidth=1)
    ax.axhline(y=ep0, color='gray', linestyle='--', alpha=0.5, label=f'EP₀ = {ep0:.3f} kWh/km')
    ax.set_xlabel('Net elevation change Δh (m)')
    ax.set_ylabel('EP (kWh/km)')
    ax.set_title('Exp 5 — Effect of Elevation Change on Energy Performance (no regen, symmetric)')
    ax.legend(fontsize=FS_LEGEND)
    fig.tight_layout()
    fig.savefig(RESULTS_FIG, dpi=DPI, bbox_inches='tight')
    plt.close(fig)

    return dict(
        alpha4_plus         = alpha4_plus,
        alpha4_minus        = alpha4_minus,
        alpha4_plus_theory  = alpha4_plus_theory,
        alpha4_minus_theory = alpha4_minus_theory,
        r_up                = r_up**2,
        r_down              = r_down**2,
        delta_hs            = delta_hs,
        eps                 = eps,
    )


if __name__ == '__main__':
    res = run()
    print(f'Exp 5 完成:')
    print(f'  α₄⁺  (上坡，拟合) = {res["alpha4_plus"] * 1e4:.4f}×10⁻⁴ kWh/(km·m),  R² = {res["r_up"]:.6f}')
    print(f'  α₄⁻  (下坡，拟合) = {res["alpha4_minus"] * 1e4:.4f}×10⁻⁴ kWh/(km·m),  R² = {res["r_down"]:.6f}')
    print(f'  α₄⁺  (理论)      = {res["alpha4_plus_theory"] * 1e4:.4f}×10⁻⁴ kWh/(km·m)')
    print(f'  α₄⁻  (理论)      = {res["alpha4_minus_theory"] * 1e4:.4f}×10⁻⁴ kWh/(km·m)')
    print(f'  |alpha4+/alpha4-| = {abs(res["alpha4_plus"]/res["alpha4_minus"]):.4f}  (理论 = 1.0000，对称)')
