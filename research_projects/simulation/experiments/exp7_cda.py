"""
Exp 7 — 车辆构型（CdA）对 EP 的影响
变量：CdA 3.9 → 8.5 m²（5 种典型构型）
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

RESULTS_FIG  = ROOT / 'simulation' / 'results' / 'figures' / 'exp7_cda.png'
RESULTS_TABLE= ROOT / 'simulation' / 'results' / 'tables'  / 'exp7_cda.csv'

# 构型定义
CONFIGURATIONS = [
    ('Tractor only',  3.9),
    ('Flatbed',       5.0),
    ('Box trailer',   6.16),   # baseline, in-situ calibration
    ('Curtain-side',  7.2),
    ('Tanker',        8.5),
]


def run() -> dict:
    labels = [c[0] for c in CONFIGURATIONS]
    cdas   = np.array([c[1] for c in CONFIGURATIONS])
    eps    = np.array([compute_ep(m=BASELINE['m'], cda=c)['EP'] for c in cdas])
    ep0    = compute_ep(m=BASELINE['m'])['EP']
    delta_ep = eps - ep0

    # 线性拟合（密集扫描以得到精确系数）
    cda_dense = np.linspace(3.0, 9.5, 50)
    eps_dense = np.array([compute_ep(m=BASELINE['m'], cda=c)['EP'] for c in cda_dense])
    slope, intercept, r, _, _ = linregress(cda_dense, eps_dense)
    alpha7 = slope   # kWh/(km·m²)

    # 理论值
    rho, v_c, eta_dt = BASELINE['rho'], BASELINE['v_c'], BASELINE['eta_dt']
    _J_TO_KWH = 1 / 3_600_000
    # 巡航段主导（忽略加减速段小量）：
    # F_aero = 0.5·ρ·CdA·v_c²，能量/距离 = F_aero/η_dt
    # d_cruise ≈ d_total（加减速段占比小）
    alpha7_theory = 0.5 * rho * v_c**2 / eta_dt * 1000 * _J_TO_KWH  # kWh/(km·m²)

    # 保存表格
    df = pd.DataFrame({
        'configuration': labels,
        'CdA_m2'       : cdas,
        'EP_kWh_per_km': eps,
        'delta_EP'     : delta_ep,
    })
    df.to_csv(RESULTS_TABLE, index=False)

    # ── 图表（双子图）───────────────────────────────────────────────────────
    apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(FIG_W * 1.2, FIG_H * 0.75), dpi=DPI)
    colors = ['#2196F3', '#4CAF50', '#FF9800', '#E91E63', '#9C27B0']

    # Left: EP bar chart by configuration
    bars = axes[0].bar(labels, eps, color=colors, edgecolor='white', linewidth=0.5)
    axes[0].axhline(y=ep0, color='gray', linestyle='--', label=f'Baseline {ep0:.3f} kWh/km')
    for bar, ep in zip(bars, eps):
        axes[0].text(bar.get_x() + bar.get_width() / 2, ep + 0.003,
                     f'{ep:.3f}', ha='center', va='bottom', fontsize=9)
    axes[0].set_xticklabels(labels, rotation=15, ha='right')
    axes[0].set_ylabel('EP (kWh/km)')
    axes[0].set_title('EP vs Vehicle Configuration')
    axes[0].legend()
    axes[0].set_ylim(0, max(eps) * 1.12)

    # Right: ΔEP vs CdA (verify linear)
    axes[1].scatter(cdas, delta_ep, color='steelblue', s=80, zorder=5, label='Simulation')
    axes[1].plot(cda_dense, slope * cda_dense + intercept - ep0, 'r--',
                 label=f'α₇ = {alpha7:.4f} kWh/(km·m²)\n'
                       f'Theory = {alpha7_theory:.4f}\nR² = {r**2:.5f}')
    for c, dep, lab in zip(cdas, delta_ep, labels):
        axes[1].annotate(lab, (c, dep), textcoords='offset points',
                         xytext=(4, 4), fontsize=9)
    axes[1].set_xlabel('$C_d A$ (m²)')
    axes[1].set_ylabel('ΔEP (kWh/km)')
    axes[1].set_title('ΔEP vs $C_dA$ (linear relationship)')
    axes[1].legend(fontsize=FS_LEGEND)

    fig.suptitle('Exp 7 — Effect of Vehicle Configuration ($C_dA$) on Energy Performance', fontsize=14)
    fig.tight_layout()
    fig.savefig(RESULTS_FIG, dpi=DPI, bbox_inches='tight')
    plt.close(fig)

    return dict(
        alpha7        = alpha7,
        alpha7_theory = alpha7_theory,
        alpha7_units  = 'kWh/(km·m²)',
        r_squared     = r**2,
        cdas          = cdas,
        eps           = eps,
        labels        = labels,
    )


if __name__ == '__main__':
    res = run()
    print(f'Exp 7 完成: α₇ = {res["alpha7"]:.5f} kWh/(km·m²)  '
          f'(理论 = {res["alpha7_theory"]:.5f}),  R² = {res["r_squared"]:.6f}')
