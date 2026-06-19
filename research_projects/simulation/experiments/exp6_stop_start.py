"""
Exp 6 — 启停次数对 EP 的影响
变量：n_stop 0 → 30，步长 2；联合质量 18,000 / 27,000 / 42,000 kg（验证 α₅ ∝ m）
再生制动效率：η_regen = 0.90（基准）、0.50（部分再生）、0（无再生）
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
from models.vehicle_physics import (compute_ep, BASELINE, apply_style,
                                     FIG_W, FIG_H, DPI, FS_LEGEND,
                                     FS_LABEL, FS_TITLE, FS_TICK)

RESULTS_FIG         = ROOT / 'simulation' / 'results' / 'figures' / 'exp6_stop_start.png'
RESULTS_FIG_COMPARE = ROOT / 'simulation' / 'results' / 'figures' / 'exp6_noregen_compare.png'
RESULTS_FIG_CYCLE   = ROOT / 'simulation' / 'results' / 'figures' / 'exp6_driving_cycle.png'
RESULTS_TABLE       = ROOT / 'simulation' / 'results' / 'tables'  / 'exp6_stop_start.csv'

MASSES = [18_000, 27_000, 42_000]   # kg
COLORS = ['#2196F3', '#4CAF50', '#E91E63']

# Driving-cycle illustration cases
CYCLE_N_STOPS  = [0, 5, 10, 20, 30]
CYCLE_COLORS   = ['#1a237e', '#1565C0', '#0288D1', '#FF9800', '#E91E63']


# ── Driving-cycle profile builder ───────────────────────────────────────────
def _build_speed_profile(n_stop: int,
                          d_total: float = BASELINE['d_total'],
                          v_c: float     = BASELINE['v_c'],
                          a_acc: float   = BASELINE['a_acc'],
                          a_dec: float   = BASELINE['a_dec'],
                          n_pts_ramp: int = 60):
    """
    构建速度-距离剖面（纯定速巡航基线）。
    基线全程 v_c，起止速度均为 v_c。
    每次启停事件：cruise → dec(v_c→0) → acc(0→v_c) → cruise
    Profile: [cruise → dec → acc] × n_stop → cruise（尾段）
    Returns (distance_km, speed_kmh) or (None, None) if infeasible.
    """
    d_acc = v_c ** 2 / (2.0 * a_acc)
    d_dec = v_c ** 2 / (2.0 * a_dec)
    d_cruise_total = d_total - n_stop * (d_acc + d_dec)
    if d_cruise_total < 0:
        return None, None
    # 巡航段均匀分配：n_stop 次停车将行程分为 (n_stop + 1) 段
    d_per = d_cruise_total / (n_stop + 1) if n_stop > 0 else d_cruise_total

    xs: list[float] = []
    vs: list[float] = []
    d = 0.0

    def _dec():
        nonlocal d
        x = np.linspace(0.0, d_dec, n_pts_ramp)
        xs.extend(d + x)
        vs.extend(np.sqrt(np.maximum(0.0, v_c ** 2 - 2.0 * a_dec * x)))
        d += d_dec

    def _acc():
        nonlocal d
        x = np.linspace(0.0, d_acc, n_pts_ramp)
        xs.extend(d + x)
        vs.extend(np.sqrt(2.0 * a_acc * x))
        d += d_acc

    def _cruise(dist: float):
        nonlocal d
        xs.extend([d, d + dist])
        vs.extend([v_c, v_c])
        d += dist

    # 起始速度 = v_c（纯巡航基线）
    for i in range(n_stop):
        _cruise(d_per)        # 巡航段
        _dec()                # v_c → 0
        _acc()                # 0 → v_c
    _cruise(d_per)            # 最后一段巡航（到达终点，速度 = v_c）

    return np.array(xs) / 1_000, np.array(vs) * 3.6   # km, km/h


def run() -> dict:
    n_stops   = np.arange(0, 31, 2)
    rows      = []
    alpha5s   = {}

    # ── 计算 ────────────────────────────────────────────────────────────────
    results_per_mass = {}
    for m in MASSES:
        eps = []
        for n in n_stops:
            try:
                ep = compute_ep(m=m, n_stop=int(n))['EP']
            except ValueError:
                ep = float('nan')
            eps.append(ep)
        eps = np.array(eps)
        results_per_mass[m] = eps

        # 线性拟合 EP vs n_stop
        valid = ~np.isnan(eps)
        slope, intercept, r, _, _ = linregress(n_stops[valid], eps[valid])
        alpha5s[m] = slope   # kWh/(km·stop)

        for n, ep in zip(n_stops, eps):
            rows.append({'mass_kg': m, 'n_stop': n, 'EP_kWh_per_km': ep})

    # ── Half-regen case (eta_regen=0.50) ────────────────────────────────────
    results_halfregen = {}
    alpha5s_halfregen = {}
    for m in MASSES:
        eps_hr = []
        for n in n_stops:
            try:
                ep = compute_ep(m=m, n_stop=int(n), eta_regen=0.5)['EP']
            except ValueError:
                ep = float('nan')
            eps_hr.append(ep)
        eps_hr = np.array(eps_hr)
        results_halfregen[m] = eps_hr
        valid_hr = ~np.isnan(eps_hr)
        slope_hr, _, _, _, _ = linregress(n_stops[valid_hr], eps_hr[valid_hr])
        alpha5s_halfregen[m] = slope_hr

    # ── No-regen case (eta_regen=0) ─────────────────────────────────────────
    results_noregen = {}
    alpha5s_noregen = {}
    for m in MASSES:
        eps_nr = []
        for n in n_stops:
            try:
                ep = compute_ep(m=m, n_stop=int(n), eta_regen=0.0)['EP']
            except ValueError:
                ep = float('nan')
            eps_nr.append(ep)
        eps_nr = np.array(eps_nr)
        results_noregen[m] = eps_nr
        valid_nr = ~np.isnan(eps_nr)
        slope_nr, _, r_nr, _, _ = linregress(n_stops[valid_nr], eps_nr[valid_nr])
        alpha5s_noregen[m] = slope_nr

    # 验证 α₅ ∝ m
    m_arr      = np.array(MASSES, dtype=float)
    alpha5_arr = np.array([alpha5s[m] for m in MASSES])
    slope_a5m, intercept_a5m, r_a5m, _, _ = linregress(m_arr, alpha5_arr)

    # 保存表格
    pd.DataFrame(rows).to_csv(RESULTS_TABLE, index=False)

    # ── 图表（双子图）───────────────────────────────────────────────────────
    apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(FIG_W * 1.2, FIG_H * 0.75), dpi=DPI)

    # Left: EP vs n_stop (multi-mass curves)
    for m, c in zip(MASSES, COLORS):
        eps   = results_per_mass[m]
        valid = ~np.isnan(eps)
        ax = axes[0]
        ax.scatter(n_stops[valid], eps[valid], color=c, zorder=5)
        fit_x = np.linspace(0, 30, 60)
        a5    = alpha5s[m]
        ep0_m = results_per_mass[m][0]
        ax.plot(fit_x, a5 * fit_x + ep0_m,
                color=c, linestyle='--',
                label=f'{m//1000} t  α₅={a5 * 1e4:.3f}×10⁻⁴ kWh/(km·stop)')
    axes[0].set_xlabel('Number of stops $n_{stop}$')
    axes[0].set_ylabel('EP (kWh/km)')
    axes[0].set_title('EP vs Number of Stops (multi-mass)')
    axes[0].legend(fontsize=FS_LEGEND)

    # Right: α₅ vs mass (verify linear)
    axes[1].scatter(m_arr / 1000, alpha5_arr * 1e4, color='steelblue',
                    s=80, zorder=5, label='Simulation')
    fit_m = np.linspace(15, 45, 100)
    axes[1].plot(fit_m,
                 (slope_a5m * fit_m * 1000 + intercept_a5m) * 1e4, 'r--',
                 label=f'R² = {r_a5m**2:.5f}')
    axes[1].set_xlabel('Gross Vehicle Weight (tonnes)')
    axes[1].set_ylabel('α₅ (×10⁻⁴ kWh/(km·stop))')
    axes[1].set_title('α₅(m) — linear mass dependence')
    axes[1].legend(fontsize=FS_LEGEND)

    fig.suptitle('Exp 6 — Effect of Stop-Start Cycles on Energy Performance', fontsize=14)
    fig.tight_layout()
    fig.savefig(RESULTS_FIG, dpi=DPI, bbox_inches='tight')
    plt.close(fig)

    # ── Comparison figure: regen vs half-regen vs no-regen ──────────────────
    fig2, axes2 = plt.subplots(1, 2, figsize=(FIG_W * 1.2, FIG_H * 0.75), dpi=DPI)

    m_ref = 42_000
    ax = axes2[0]
    fit_x = np.linspace(0, 30, 60)

    # η=0.90 (full regen)
    a5_r  = alpha5s[m_ref]
    ep0_r = results_per_mass[m_ref][0]
    ax.scatter(n_stops, results_per_mass[m_ref], color='steelblue', zorder=5)
    ax.plot(fit_x, a5_r * fit_x + ep0_r, color='steelblue', linestyle='--',
            label=f'η=90%  α₅={a5_r*1e4:.3f}×10⁻⁴')

    # η=0.50 (half regen)
    a5_hr  = alpha5s_halfregen[m_ref]
    ep0_hr = results_halfregen[m_ref][0]
    ax.scatter(n_stops, results_halfregen[m_ref], color='#FF9800', zorder=5)
    ax.plot(fit_x, a5_hr * fit_x + ep0_hr, color='#FF9800', linestyle='--',
            label=f'η=50%  α₅={a5_hr*1e4:.3f}×10⁻⁴')

    # η=0 (no regen)
    a5_nr  = alpha5s_noregen[m_ref]
    ep0_nr = results_noregen[m_ref][0]
    ax.scatter(n_stops, results_noregen[m_ref], color='tomato', zorder=5)
    ax.plot(fit_x, a5_nr * fit_x + ep0_nr, color='tomato', linestyle='--',
            label=f'η=0%   α₅={a5_nr*1e4:.3f}×10⁻⁴')

    ax.set_xlabel('Number of stops $n_{stop}$')
    ax.set_ylabel('EP (kWh/km)')
    ax.set_title('EP vs Stops at 42 t: η = 90% / 50% / 0%')
    ax.legend(fontsize=FS_LEGEND, loc='upper left')

    # Right: α₅ vs mass for all three cases
    ax2 = axes2[1]
    m_arr_t = m_arr / 1000  # tonnes
    alpha5_regen_arr   = np.array([alpha5s[m]           for m in MASSES])
    alpha5_halfregen_arr = np.array([alpha5s_halfregen[m] for m in MASSES])
    alpha5_noregen_arr = np.array([alpha5s_noregen[m]   for m in MASSES])

    ax2.scatter(m_arr_t, alpha5_regen_arr   * 1e4, color='steelblue', s=80, zorder=5)
    ax2.plot(m_arr_t,    alpha5_regen_arr   * 1e4, color='steelblue', linestyle='--',
             label='η=90% (full regen)')
    ax2.scatter(m_arr_t, alpha5_halfregen_arr * 1e4, color='#FF9800', s=80, zorder=5)
    ax2.plot(m_arr_t,    alpha5_halfregen_arr * 1e4, color='#FF9800', linestyle='--',
             label='η=50% (half regen)')
    ax2.scatter(m_arr_t, alpha5_noregen_arr * 1e4, color='tomato', s=80, zorder=5)
    ax2.plot(m_arr_t,    alpha5_noregen_arr * 1e4, color='tomato', linestyle='--',
             label='η=0% (no regen)')
    ax2.axhline(0, color='grey', linestyle=':', linewidth=1)
    ax2.set_xlabel('Gross Vehicle Weight (tonnes)')
    ax2.set_ylabel('α₅ (×10⁻⁴ kWh/(km·stop))')
    ax2.set_title('α₅(m): η = 90% / 50% / 0%')
    ax2.legend(fontsize=FS_LEGEND, loc='upper left')

    fig2.suptitle('Exp 6 — Stop-Start: Effect of Regenerative Braking Efficiency', fontsize=14)
    fig2.tight_layout()
    fig2.savefig(RESULTS_FIG_COMPARE, dpi=DPI, bbox_inches='tight')
    plt.close(fig2)

    # ── Driving-cycle illustration ───────────────────────────────────────────
    _plot_driving_cycle()

    return dict(
        alpha5s              = alpha5s,
        alpha5s_halfregen    = alpha5s_halfregen,
        alpha5s_noregen      = alpha5s_noregen,
        alpha5_units         = 'kWh/(km·stop)',
        slope_alpha5_mass    = slope_a5m,
        r_squared_a5m        = r_a5m**2,
        n_stops              = n_stops,
        results_per_mass     = results_per_mass,
        results_halfregen    = results_halfregen,
        results_noregen      = results_noregen,
    )


def _plot_driving_cycle():
    """Speed vs Distance for different n_stop values — illustrative driving cycles."""
    apply_style()

    v_c_kmh = BASELINE['v_c'] * 3.6          # 90 km/h
    d_total_km = BASELINE['d_total'] / 1_000  # 100 km

    # Pre-build profiles for all cases
    profiles = {}
    for n in CYCLE_N_STOPS:
        xs, vs = _build_speed_profile(n)
        if xs is not None:
            profiles[n] = (xs, vs)

    # ── Figure: 2-row layout ─────────────────────────────────────────────────
    # Top  — full 100 km overview
    # Bottom — first 15 km zoom (individual stop-start cycle structure)
    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1, figsize=(FIG_W * 1.4, FIG_H * 1.1), dpi=DPI,
        gridspec_kw={'height_ratios': [3, 2]},
    )

    for n, color in zip(CYCLE_N_STOPS, CYCLE_COLORS):
        if n not in profiles:
            continue
        xs, vs = profiles[n]
        lw = 2.2 if n == 0 else 1.8
        ls = '--' if n == 0 else '-'
        label = f'n = {n} stop{"s" if n != 1 else ""}'
        ax_top.plot(xs, vs, color=color, linewidth=lw, linestyle=ls,
                    label=label, alpha=0.9, zorder=5 - CYCLE_N_STOPS.index(n) * 0.1)
        # zoom: first 15 km
        mask = xs <= 15.0
        if mask.any():
            ax_bot.plot(xs[mask], vs[mask], color=color, linewidth=lw,
                        linestyle=ls, alpha=0.9)

    # ── Top axes — overview ──────────────────────────────────────────────────
    ax_top.axhline(y=v_c_kmh, color='grey', linewidth=0.8, linestyle=':', alpha=0.5)
    ax_top.set_xlim(0, d_total_km)
    ax_top.set_ylim(-3, v_c_kmh + 8)
    ax_top.set_xlabel('Distance (km)', fontsize=FS_LABEL)
    ax_top.set_ylabel('Speed (km/h)', fontsize=FS_LABEL)
    ax_top.set_title(
        'Exp 6 — Simulated Driving Cycles for Different Stop Counts\n'
        f'(v_c = {v_c_kmh:.0f} km/h, d = {d_total_km:.0f} km, m = 42 t)',
        fontsize=FS_TITLE,
    )
    ax_top.legend(fontsize=FS_LEGEND, loc='center right', framealpha=0.9)
    ax_top.text(0.50, 0.06,
                'Baseline: constant $v_c$ = 90 km/h.  Each dip: '
                'cruise → decelerate → full stop → accelerate → cruise',
                transform=ax_top.transAxes, ha='center', fontsize=8.5, color='#555555',
                style='italic')

    # ── Bottom axes — 15 km zoom ─────────────────────────────────────────────
    ax_bot.axhline(y=v_c_kmh, color='grey', linewidth=0.8, linestyle=':', alpha=0.5)
    ax_bot.set_xlim(0, 15)
    ax_bot.set_ylim(-3, v_c_kmh + 8)
    ax_bot.set_xlabel('Distance (km)', fontsize=FS_LABEL - 1)
    ax_bot.set_ylabel('Speed (km/h)', fontsize=FS_LABEL - 1)
    ax_bot.set_title('Zoom: First 15 km — Individual Stop-Start Cycle Structure',
                     fontsize=FS_TITLE - 1)
    ax_bot.tick_params(labelsize=FS_TICK - 1)

    # Annotate deceleration and acceleration distances on zoom panel
    # 新剖面从巡航开始；第一个停车事件的减速/加速段位于第一段巡航之后
    d_acc_km = BASELINE['v_c'] ** 2 / (2.0 * BASELINE['a_acc']) / 1_000  # km
    d_dec_km = BASELINE['v_c'] ** 2 / (2.0 * BASELINE['a_dec']) / 1_000  # km
    # n=5 时第一段巡航约 15.9 km，第一个减速段起始位置
    d_cruise_5 = (BASELINE['d_total'] - 5 * (d_acc_km + d_dec_km) * 1000) / 6 / 1000  # km
    if d_cruise_5 > 0:
        ax_bot.text(d_cruise_5 + d_dec_km / 2, v_c_kmh / 2,
                    f'dec\n{d_dec_km*1000:.0f} m',
                    ha='center', va='center', fontsize=7.5, color='#333333')
        ax_bot.text(d_cruise_5 + d_dec_km + d_acc_km / 2, v_c_kmh / 2,
                    f'acc\n{d_acc_km*1000:.0f} m',
                    ha='center', va='center', fontsize=7.5, color='#333333')

    fig.tight_layout(h_pad=1.5)
    fig.savefig(RESULTS_FIG_CYCLE, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {RESULTS_FIG_CYCLE.name}')


if __name__ == '__main__':
    res = run()
    print('Exp 6 — With regen (eta_regen=0.90):')
    for m, a5 in res['alpha5s'].items():
        print(f'  m = {m//1000} t:  a5 = {a5 * 1e4:.4f}e-4 kWh/(km·stop)')
    print(f'  a5 prop m  R2 = {res["r_squared_a5m"]:.6f}')
    print()
    print('Exp 6 — Half regen (eta_regen=0.50):')
    for m, a5 in res['alpha5s_halfregen'].items():
        print(f'  m = {m//1000} t:  a5 = {a5 * 1e4:.4f}e-4 kWh/(km·stop)')
    print()
    print('Exp 6 — No regen (eta_regen=0):')
    for m, a5 in res['alpha5s_noregen'].items():
        print(f'  m = {m//1000} t:  a5 = {a5 * 1e4:.4f}e-4 kWh/(km·stop)')
