"""
Exp 3 — 环境温度对 EP 的影响（Arrhenius 电池效率模型）
变量：T -5 → 35°C，步长 2°C（英国运营范围）
其余参数保持基准值
"""
from __future__ import annotations
import sys, pathlib
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'simulation'))
from models.vehicle_physics import compute_ep, BASELINE, apply_style, eta_bat, FIG_W, FIG_H, DPI, FS_LEGEND

RESULTS_FIG  = ROOT / 'simulation' / 'results' / 'figures' / 'exp3_temperature.png'
RESULTS_TABLE= ROOT / 'simulation' / 'results' / 'tables'  / 'exp3_temperature.csv'

T_BASELINE = BASELINE['T_amb']   # 20°C


def run() -> dict:
    temps = np.arange(-5, 36, 2, dtype=float)   # °C
    eps   = [compute_ep(m=BASELINE['m'], T_amb=T)['EP'] for T in temps]
    eps   = np.array(eps)
    ep0   = compute_ep(m=BASELINE['m'], T_amb=T_BASELINE)['EP']

    delta_ep   = eps - ep0
    eta_values = np.array([eta_bat(T) for T in temps])

    # 保存表格
    df = pd.DataFrame({
        'T_C'          : temps,
        'eta_bat'      : eta_values,
        'EP_kWh_per_km': eps,
        'delta_EP'     : delta_ep,
    })
    df.to_csv(RESULTS_TABLE, index=False)

    # ── 图表（双子图）───────────────────────────────────────────────────────
    apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(FIG_W * 1.2, FIG_H * 0.75), dpi=DPI)

    # Left: η_bat vs temperature
    axes[0].plot(temps, eta_values, 'o-', color='darkorange', markerfacecolor='white')
    axes[0].axvline(x=T_BASELINE, color='gray', linestyle=':', label=f'Baseline {T_BASELINE}°C')
    axes[0].axhline(y=1.0, color='lightgray', linestyle='--')
    axes[0].set_xlabel('Ambient temperature $T$ (°C)')
    axes[0].set_ylabel('Battery discharge efficiency $\\eta_{bat}$')
    axes[0].set_title('Arrhenius Battery Efficiency Model')
    axes[0].legend()
    axes[0].set_ylim(0.90, 1.02)

    # Right: EP vs temperature with f_T(T) shading
    axes[1].plot(temps, eps, 'o-', color='steelblue', markerfacecolor='white', label='EP(T)')
    axes[1].axhline(y=ep0, color='gray', linestyle='--', label=f'Baseline EP₀ = {ep0:.3f} kWh/km')
    axes[1].fill_between(temps, ep0, eps,
                         where=(eps > ep0), alpha=0.2, color='red',   label='f_T(T) > 0 (efficiency loss)')
    axes[1].fill_between(temps, ep0, eps,
                         where=(eps <= ep0), alpha=0.2, color='green', label='f_T(T) ≤ 0 (efficiency gain)')
    axes[1].axvline(x=T_BASELINE, color='gray', linestyle=':', label=f'Baseline {T_BASELINE}°C')
    axes[1].set_xlabel('Ambient temperature $T$ (°C)')
    axes[1].set_ylabel('EP (kWh/km)')
    axes[1].set_title('EP vs Temperature (nonlinear Arrhenius effect)')
    axes[1].legend(fontsize=FS_LEGEND)

    fig.suptitle('Exp 3 — Effect of Ambient Temperature on Energy Performance', fontsize=14)
    fig.tight_layout()
    fig.savefig(RESULTS_FIG, dpi=DPI, bbox_inches='tight')
    plt.close(fig)

    return dict(
        temps   = temps,
        eps     = eps,
        ep0     = ep0,
        delta_ep= delta_ep,
        eta_bat = eta_values,
    )


if __name__ == '__main__':
    res = run()
    ep_minus5 = res['eps'][res['temps'] == -5][0]
    ep_plus35 = res['eps'][res['temps'] == 35][0]
    print(f'Exp 3 完成: EP(-5°C) = {ep_minus5:.4f},  EP(20°C) = {res["ep0"]:.4f},  '
          f'EP(35°C) = {ep_plus35:.4f} kWh/km')
