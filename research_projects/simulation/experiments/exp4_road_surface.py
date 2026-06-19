"""
Exp 4 — 路面状况（滚阻系数 Crr）对 EP 的影响
变量：干燥 / 轻度潮湿 / 重度潮湿 / 压实积雪（4 个 Crr 值）
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

RESULTS_FIG  = ROOT / 'simulation' / 'results' / 'figures' / 'exp4_road_surface.png'
RESULTS_TABLE= ROOT / 'simulation' / 'results' / 'tables'  / 'exp4_road_surface.csv'

# 路面类型定义（来源：[1] Fig. 8b + 文献估计）
ROAD_CONDITIONS = [
    ('Dry asphalt',    0.00465),   # baseline, in-situ calibration
    ('Light wet',      0.00605),   # +30%
    ('Heavy wet',      0.00698),   # +50%
    ('Compacted snow', 0.00930),   # ×2 (literature estimate)
]


def run() -> dict:
    labels = [r[0] for r in ROAD_CONDITIONS]
    crrs   = np.array([r[1] for r in ROAD_CONDITIONS])
    eps    = np.array([compute_ep(m=BASELINE['m'], crr=c)['EP'] for c in crrs])
    ep0    = eps[0]
    delta_ep = eps - ep0

    # 线性拟合（Crr 扫描）
    crr_dense = np.linspace(0.003, 0.011, 50)
    eps_dense = np.array([compute_ep(m=BASELINE['m'], crr=c)['EP'] for c in crr_dense])
    slope, intercept, r, _, _ = linregress(crr_dense, eps_dense)
    alpha3 = slope   # kWh/(km per unit Crr)

    # 保存表格
    df = pd.DataFrame({
        'road_condition': labels,
        'Crr'           : crrs,
        'EP_kWh_per_km' : eps,
        'delta_EP'      : delta_ep,
    })
    df.to_csv(RESULTS_TABLE, index=False)

    # ── 图表（双子图）───────────────────────────────────────────────────────
    apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(FIG_W * 1.2, FIG_H * 0.75), dpi=DPI)
    colors = ['#2196F3', '#4CAF50', '#FF9800', '#9C27B0']

    # Left: EP bar chart by road condition
    bars = axes[0].bar(labels, eps, color=colors, edgecolor='white', linewidth=0.5)
    axes[0].axhline(y=ep0, color='gray', linestyle='--', label=f'Baseline {ep0:.3f} kWh/km')
    for bar, ep in zip(bars, eps):
        axes[0].text(bar.get_x() + bar.get_width() / 2, ep + 0.002,
                     f'{ep:.3f}', ha='center', va='bottom', fontsize=9)
    axes[0].set_ylabel('EP (kWh/km)')
    axes[0].set_title('EP vs Road Condition')
    axes[0].legend()
    axes[0].set_ylim(0, max(eps) * 1.12)

    # Right: ΔEP vs Crr (verify linear)
    axes[1].scatter(crrs, delta_ep, color='steelblue', s=80, zorder=5, label='Simulation')
    axes[1].plot(crr_dense, slope * crr_dense + intercept - ep0,
                 'r--',
                 label=f'α₃ = {alpha3:.1f} kWh/(km·ΔCrr)\nR² = {r**2:.5f}')
    for i, (c, dep, lab) in enumerate(zip(crrs, delta_ep, labels)):
        axes[1].annotate(lab, (c, dep), textcoords='offset points',
                         xytext=(4, 4), fontsize=9)
    axes[1].set_xlabel('Rolling resistance coefficient $C_{rr}$')
    axes[1].set_ylabel('ΔEP (kWh/km)')
    axes[1].set_title('ΔEP vs $C_{rr}$ (linear relationship)')
    axes[1].legend(fontsize=FS_LEGEND)

    fig.suptitle('Exp 4 — Effect of Road Surface on Energy Performance', fontsize=14)
    fig.tight_layout()
    fig.savefig(RESULTS_FIG, dpi=DPI, bbox_inches='tight')
    plt.close(fig)

    return dict(
        alpha3       = alpha3,
        alpha3_units = 'kWh/(km per unit Crr)',
        r_squared    = r**2,
        crrs         = crrs,
        eps          = eps,
        labels       = labels,
    )


if __name__ == '__main__':
    res = run()
    print(f'Exp 4 完成: α₃ = {res["alpha3"]:.2f} kWh/(km·ΔCrr),  R² = {res["r_squared"]:.6f}')
