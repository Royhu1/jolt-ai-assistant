"""
Exp 1 — 车辆质量对 EP 的影响
变量：GVW 18,000 → 44,000 kg，步长 2,000 kg
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

RESULTS_FIG  = ROOT / 'simulation' / 'results' / 'figures' / 'exp1_mass.png'
RESULTS_TABLE= ROOT / 'simulation' / 'results' / 'tables'  / 'exp1_mass.csv'


def run() -> dict:
    masses = np.arange(10_000, 44_001, 2_000)  # kg
    eps    = [compute_ep(m=m)['EP'] for m in masses]
    eps    = np.array(eps)

    # 线性拟合
    slope, intercept, r, _, _ = linregress(masses, eps)
    alpha1 = slope   # kWh/(km·kg)

    # 保存表格
    df = pd.DataFrame({'GVW_kg': masses, 'EP_kWh_per_km': eps})
    df.to_csv(RESULTS_TABLE, index=False)

    # ── 图表 ────────────────────────────────────────────────────────────────
    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)

    ax.scatter(masses / 1000, eps, color='steelblue', zorder=5, label='Simulation')
    fit_x = np.array([18, 44])
    ax.plot(fit_x, slope * fit_x * 1000 + intercept, 'r--',
            label=f'Linear fit  α₁ = {alpha1 * 1e5:.3f}×10⁻⁵ kWh/(km·kg)\n'
                  f'R² = {r**2:.5f}')

    ax.set_xlabel('Gross Vehicle Weight GVW (tonnes)')
    ax.set_ylabel('EP (kWh/km)')
    ax.set_title('Exp 1 — Effect of Vehicle Mass on Energy Performance')
    ax.legend(fontsize=FS_LEGEND)
    fig.tight_layout()
    fig.savefig(RESULTS_FIG, dpi=DPI, bbox_inches='tight')
    plt.close(fig)

    return dict(
        alpha1       = alpha1,
        alpha1_units = 'kWh/(km·kg)',
        r_squared    = r**2,
        masses_kg    = masses,
        eps          = eps,
    )


if __name__ == '__main__':
    res = run()
    print(f'Exp 1 完成: α₁ = {res["alpha1"]:.4e} kWh/(km·kg),  R² = {res["r_squared"]:.6f}')
