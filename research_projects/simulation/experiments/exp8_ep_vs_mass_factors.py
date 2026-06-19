# -*- coding: utf-8 -*-
"""
Exp 8 — EP vs Mass fit lines under varying factor conditions + Sensitivity chart

For each factor, show how the EP-vs-mass linear relationship shifts as the
factor changes.  Also produce a single tornado chart comparing all factors
at a representative mass (m = 42,000 kg).

Output figures (research_projects/simulation/results/figures/):
    ep_vs_mass_wind.png
    ep_vs_mass_temperature.png
    ep_vs_mass_road.png
    ep_vs_mass_elevation.png
    ep_vs_mass_stops_regen.png      (with regenerative braking, η_regen=0.90)
    ep_vs_mass_stops_halfregen.png  (partial regenerative braking, η_regen=0.50)
    ep_vs_mass_stops_noregen.png    (no regenerative braking, η_regen=0)
    ep_vs_mass_cda.png
    sensitivity_tornado.png
"""
from __future__ import annotations
import sys, pathlib
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from scipy.stats import linregress

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'simulation'))
from models.vehicle_physics import compute_ep, BASELINE

OUT = ROOT / 'simulation' / 'results' / 'figures'

# ── Figure-plotter style constants ───────────────────────────────────────────
FIG_W, FIG_H = 10, 6
DPI          = 300
FS_LABEL     = 14
FS_TITLE     = 14
FS_TICK      = 12
FS_LEGEND    = 9
FIT_LW       = 2
FIT_ALPHA    = 0.9
GRID_ALPHA   = 0.3
PERF_YLIM    = (0.5, 2.8)
MASS_XLIM    = (15_000, 46_000)

MASSES = np.arange(18_000, 44_001, 2_000)   # kg sweep

M_REF = 42_000   # reference mass for sensitivity chart


def _apply_style(ax, title: str, xlabel: str = 'Vehicle Total Mass (kg)',
                 ylabel: str = 'Energy Performance (kWh/km)'):
    ax.set_xlabel(xlabel, fontsize=FS_LABEL)
    ax.set_ylabel(ylabel, fontsize=FS_LABEL)
    ax.set_title(title, fontsize=FS_TITLE)
    ax.tick_params(labelsize=FS_TICK)
    ax.grid(True, alpha=GRID_ALPHA)
    ax.set_xlim(MASS_XLIM)
    ax.set_ylim(PERF_YLIM)
    ax.legend(fontsize=FS_LEGEND, loc='upper left')


def _ep_line(masses, **kwargs):
    """Return (slope, intercept) of EP vs mass for given kwargs."""
    eps = np.array([compute_ep(m=m, **kwargs)['EP'] for m in masses])
    slope, intercept, *_ = linregress(masses, eps)
    return slope, intercept, eps


def _plot_line(ax, masses, slope, intercept, color, label, lw=FIT_LW,
               alpha=FIT_ALPHA, ls='-', zorder=3):
    ax.plot(masses, slope * masses + intercept,
            color=color, linewidth=lw, alpha=alpha, linestyle=ls,
            label=label, zorder=zorder)


# ─────────────────────────────────────────────────────────────────────────────
# 1.  EP vs Mass — Wind Speed
# ─────────────────────────────────────────────────────────────────────────────
WIND_CONDITIONS = [
    ('0 m/s (calm)',          0,  True),
    ('4 m/s (light breeze)',  4,  False),
    ('8 m/s (fresh breeze)',  8,  False),
    ('12 m/s (strong breeze)',12, False),
    ('15 m/s (near-gale)',   15,  False),
]

def plot_wind():
    cmap   = cm.get_cmap('Blues', len(WIND_CONDITIONS) + 2)
    colors = [cmap(i + 2) for i in range(len(WIND_CONDITIONS))]

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
    for (label, v, is_base), color in zip(WIND_CONDITIONS, colors):
        s, ic, _ = _ep_line(MASSES, v_wind=v)
        ls  = '--' if is_base else '-'
        lw  = FIT_LW + 0.5 if is_base else FIT_LW
        _plot_line(ax, MASSES, s, ic, color, label, lw=lw,
                   ls=ls, zorder=5 if is_base else 3)

    _apply_style(ax, 'EP vs Mass — Effect of Wind Speed')
    fig.tight_layout()
    fig.savefig(OUT / 'ep_vs_mass_wind.png', dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print('  Saved: ep_vs_mass_wind.png')


# ─────────────────────────────────────────────────────────────────────────────
# 2.  EP vs Mass — Ambient Temperature
# ─────────────────────────────────────────────────────────────────────────────
TEMP_CONDITIONS = [
    ('−5°C',  -5,  False),
    ('0°C',    0,  False),
    ('10°C',  10,  False),
    ('20°C (baseline)', 20, True),
    ('35°C',  35,  False),
]

def plot_temperature():
    # Blue (cold) → Red (hot)
    cmap   = cm.get_cmap('coolwarm', len(TEMP_CONDITIONS))
    colors = [cmap(i) for i in range(len(TEMP_CONDITIONS))]

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
    for (label, T, is_base), color in zip(TEMP_CONDITIONS, colors):
        s, ic, _ = _ep_line(MASSES, T_amb=T)
        ls = '--' if is_base else '-'
        lw = FIT_LW + 0.5 if is_base else FIT_LW
        _plot_line(ax, MASSES, s, ic, color, label, lw=lw,
                   ls=ls, zorder=5 if is_base else 3)

    _apply_style(ax, 'EP vs Mass — Effect of Ambient Temperature')
    fig.tight_layout()
    fig.savefig(OUT / 'ep_vs_mass_temperature.png', dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print('  Saved: ep_vs_mass_temperature.png')


# ─────────────────────────────────────────────────────────────────────────────
# 3.  EP vs Mass — Road Surface (Rolling Resistance)
# ─────────────────────────────────────────────────────────────────────────────
ROAD_CONDITIONS = [
    ('Dry asphalt (C_rr=0.00465)',  0.00465, True),
    ('Light wet  (C_rr=0.00605)',   0.00605, False),
    ('Heavy wet  (C_rr=0.00698)',   0.00698, False),
    ('Compacted snow (C_rr=0.0093)',0.00930, False),
]

def plot_road():
    colors = ['#2196F3', '#4CAF50', '#FF9800', '#9C27B0']

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
    for (label, crr, is_base), color in zip(ROAD_CONDITIONS, colors):
        s, ic, _ = _ep_line(MASSES, crr=crr)
        ls = '--' if is_base else '-'
        lw = FIT_LW + 0.5 if is_base else FIT_LW
        _plot_line(ax, MASSES, s, ic, color, label, lw=lw,
                   ls=ls, zorder=5 if is_base else 3)

    _apply_style(ax, 'EP vs Mass — Effect of Road Surface Condition')
    fig.tight_layout()
    fig.savefig(OUT / 'ep_vs_mass_road.png', dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print('  Saved: ep_vs_mass_road.png')


# ─────────────────────────────────────────────────────────────────────────────
# 4.  EP vs Mass — Elevation Change
# ─────────────────────────────────────────────────────────────────────────────
ELEV_CONDITIONS = [
    ('−200 m (descent)', -200, False),
    ('−100 m',           -100, False),
    ('  0 m (flat, baseline)', 0, True),
    ('+100 m',           +100, False),
    ('+200 m (ascent)',  +200, False),
]

def plot_elevation():
    cmap   = cm.get_cmap('RdBu_r', len(ELEV_CONDITIONS))
    colors = [cmap(i) for i in range(len(ELEV_CONDITIONS))]

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
    for (label, dh, is_base), color in zip(ELEV_CONDITIONS, colors):
        s, ic, _ = _ep_line(MASSES, delta_h=dh)
        ls = '--' if is_base else '-'
        lw = FIT_LW + 0.5 if is_base else FIT_LW
        _plot_line(ax, MASSES, s, ic, color, label, lw=lw,
                   ls=ls, zorder=5 if is_base else 3)

    _apply_style(ax, 'EP vs Mass — Effect of Net Elevation Change')
    fig.tight_layout()
    fig.savefig(OUT / 'ep_vs_mass_elevation.png', dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print('  Saved: ep_vs_mass_elevation.png')


# ─────────────────────────────────────────────────────────────────────────────
# 5.  EP vs Mass — Stop-Start Cycles
# ─────────────────────────────────────────────────────────────────────────────
STOP_CONDITIONS = [
    ('0 stops (baseline)', 0,  True),
    ('5 stops',            5,  False),
    ('10 stops',          10,  False),
    ('20 stops',          20,  False),
    ('30 stops',          30,  False),
]

def plot_stops():
    """Two variants: with regen (η_regen=0.90) and without regen (η_regen=0)."""
    cmap   = cm.get_cmap('YlOrRd', len(STOP_CONDITIONS) + 2)
    colors = [cmap(i + 1) for i in range(len(STOP_CONDITIONS))]

    # ── Variant A: with regenerative braking ─────────────────────────────────
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
    for (label, n, is_base), color in zip(STOP_CONDITIONS, colors):
        try:
            s, ic, _ = _ep_line(MASSES, n_stop=n)   # default eta_regen=0.90
        except ValueError:
            continue
        ls = '--' if is_base else '-'
        lw = FIT_LW + 0.5 if is_base else FIT_LW
        _plot_line(ax, MASSES, s, ic, color, label, lw=lw,
                   ls=ls, zorder=5 if is_base else 3)

    # Annotate the sign-change mass (~30 t)
    ax.axvline(x=30_000, color='gray', linewidth=1, linestyle=':',
               alpha=0.6, zorder=1)
    ax.text(30_400, PERF_YLIM[0] + 0.05, '~30 t\n(α₅ = 0)', fontsize=9,
            color='gray', va='bottom')

    _apply_style(ax, 'EP vs Mass — Stop-Start Cycles (with Regen, η_regen=0.90)\n'
                     '(note: α₅ < 0 below ~30 t — stops save energy at light loads)')
    fig.tight_layout()
    fig.savefig(OUT / 'ep_vs_mass_stops_regen.png', dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print('  Saved: ep_vs_mass_stops_regen.png')

    # ── Variant B: half regenerative braking (η_regen=0.50) ─────────────────
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
    for (label, n, is_base), color in zip(STOP_CONDITIONS, colors):
        try:
            s, ic, _ = _ep_line(MASSES, n_stop=n, eta_regen=0.5)
        except ValueError:
            continue
        ls = '--' if is_base else '-'
        lw = FIT_LW + 0.5 if is_base else FIT_LW
        _plot_line(ax, MASSES, s, ic, color, label, lw=lw,
                   ls=ls, zorder=5 if is_base else 3)

    # Annotate sign-change mass for η=0.50
    ax.axvline(x=30_000, color='gray', linewidth=1, linestyle=':',
               alpha=0.6, zorder=1)
    ax.text(30_400, PERF_YLIM[0] + 0.05, '~30 t\n(α₅ ≈ 0)', fontsize=9,
            color='gray', va='bottom')

    _apply_style(ax, 'EP vs Mass — Stop-Start Cycles (η_regen=0.50)\n'
                     '(partial regen: sign-change still around ~30 t)')
    fig.tight_layout()
    fig.savefig(OUT / 'ep_vs_mass_stops_halfregen.png', dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print('  Saved: ep_vs_mass_stops_halfregen.png')

    # ── Variant C: no regenerative braking ───────────────────────────────────
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
    for (label, n, is_base), color in zip(STOP_CONDITIONS, colors):
        try:
            s, ic, _ = _ep_line(MASSES, n_stop=n, eta_regen=0.0)
        except ValueError:
            continue
        ls = '--' if is_base else '-'
        lw = FIT_LW + 0.5 if is_base else FIT_LW
        _plot_line(ax, MASSES, s, ic, color, label, lw=lw,
                   ls=ls, zorder=5 if is_base else 3)

    _apply_style(ax, 'EP vs Mass — Stop-Start Cycles (no Regen, η_regen=0)\n'
                     '(α₅ > 0 at all masses — stops always cost energy without regen)')
    fig.tight_layout()
    fig.savefig(OUT / 'ep_vs_mass_stops_noregen.png', dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print('  Saved: ep_vs_mass_stops_noregen.png')


# ─────────────────────────────────────────────────────────────────────────────
# 6.  EP vs Mass — Vehicle Configuration (CdA)
# ─────────────────────────────────────────────────────────────────────────────
CDA_CONDITIONS = [
    ('Tractor only  (3.9 m²)',  3.9,  False),
    ('Flatbed       (5.0 m²)',  5.0,  False),
    ('Box trailer   (6.16 m², baseline)', 6.16, True),
    ('Curtain-side  (7.2 m²)',  7.2,  False),
    ('Tanker        (8.5 m²)',  8.5,  False),
]

def plot_cda():
    cmap   = cm.get_cmap('plasma', len(CDA_CONDITIONS) + 1)
    colors = [cmap(i) for i in range(len(CDA_CONDITIONS))]

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
    for (label, cda, is_base), color in zip(CDA_CONDITIONS, colors):
        s, ic, _ = _ep_line(MASSES, cda=cda)
        ls = '--' if is_base else '-'
        lw = FIT_LW + 0.5 if is_base else FIT_LW
        _plot_line(ax, MASSES, s, ic, color, label, lw=lw,
                   ls=ls, zorder=5 if is_base else 3)

    _apply_style(ax, 'EP vs Mass — Effect of Vehicle Configuration ($C_dA$)')
    fig.tight_layout()
    fig.savefig(OUT / 'ep_vs_mass_cda.png', dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print('  Saved: ep_vs_mass_cda.png')


# ─────────────────────────────────────────────────────────────────────────────
# 7.  Sensitivity Tornado Chart — all factors at m = 42,000 kg
# ─────────────────────────────────────────────────────────────────────────────
# (condition label, kwargs_override, factor_group)
SENSITIVITY_CONDITIONS = [
    # Wind
    ('Wind 4 m/s',      dict(v_wind=4),          'Wind'),
    ('Wind 8 m/s',      dict(v_wind=8),          'Wind'),
    ('Wind 12 m/s',     dict(v_wind=12),         'Wind'),
    ('Wind 15 m/s',     dict(v_wind=15),         'Wind'),
    # Temperature (relative to 20°C baseline)
    ('Temp 10°C',       dict(T_amb=10),          'Temperature'),
    ('Temp 5°C',        dict(T_amb=5),           'Temperature'),
    ('Temp 0°C',        dict(T_amb=0),           'Temperature'),
    ('Temp −5°C',       dict(T_amb=-5),          'Temperature'),
    # Road surface
    ('Light wet road',  dict(crr=0.00605),       'Road surface'),
    ('Heavy wet road',  dict(crr=0.00698),       'Road surface'),
    ('Compacted snow',  dict(crr=0.00930),       'Road surface'),
    # Elevation
    ('Elevation −200 m',dict(delta_h=-200),      'Elevation'),
    ('Elevation −100 m',dict(delta_h=-100),      'Elevation'),
    ('Elevation +100 m',dict(delta_h=+100),      'Elevation'),
    ('Elevation +200 m',dict(delta_h=+200),      'Elevation'),
    # Stop-start with full regen (η_regen=0.90, at 42 t, α₅ > 0)
    ('5 stops (η=90%)',  dict(n_stop=5),          'Stop-start (η=90%)'),
    ('10 stops (η=90%)', dict(n_stop=10),         'Stop-start (η=90%)'),
    ('20 stops (η=90%)', dict(n_stop=20),         'Stop-start (η=90%)'),
    # Stop-start with partial regen (η_regen=0.50)
    ('5 stops (η=50%)',  dict(n_stop=5,  eta_regen=0.5), 'Stop-start (η=50%)'),
    ('10 stops (η=50%)', dict(n_stop=10, eta_regen=0.5), 'Stop-start (η=50%)'),
    ('20 stops (η=50%)', dict(n_stop=20, eta_regen=0.5), 'Stop-start (η=50%)'),
    # Stop-start without regen (η_regen=0)
    ('5 stops (η=0%)',   dict(n_stop=5,  eta_regen=0.0), 'Stop-start (η=0%)'),
    ('10 stops (η=0%)',  dict(n_stop=10, eta_regen=0.0), 'Stop-start (η=0%)'),
    ('20 stops (η=0%)',  dict(n_stop=20, eta_regen=0.0), 'Stop-start (η=0%)'),
    ('30 stops (η=0%)',  dict(n_stop=30, eta_regen=0.0), 'Stop-start (η=0%)'),
    # CdA
    ('Tractor (3.9 m²)',dict(cda=3.9),           'CdA'),
    ('Curtain (7.2 m²)',dict(cda=7.2),           'CdA'),
    ('Tanker  (8.5 m²)',dict(cda=8.5),           'CdA'),
]

GROUP_COLORS = {
    'Wind'              : '#2196F3',
    'Temperature'       : '#FF5722',
    'Road surface'      : '#795548',
    'Elevation'         : '#4CAF50',
    'Stop-start (η=90%)': '#FF9800',
    'Stop-start (η=50%)': '#FF6F00',
    'Stop-start (η=0%)' : '#E91E63',
    'CdA'               : '#9C27B0',
}

def plot_sensitivity():
    ep_base = compute_ep(m=M_REF)['EP']

    rows = []
    for label, kw, group in SENSITIVITY_CONDITIONS:
        ep = compute_ep(m=M_REF, **kw)['EP']
        rows.append((label, ep - ep_base, group))

    # Sort by ΔEP (descending)
    rows.sort(key=lambda x: x[1], reverse=True)
    labels  = [r[0] for r in rows]
    deltas  = [r[1] for r in rows]
    groups  = [r[2] for r in rows]
    bar_clr = [GROUP_COLORS[g] for g in groups]
    # Desaturate slightly for negative bars
    bar_clr_final = []
    for d, c in zip(deltas, bar_clr):
        bar_clr_final.append(c if d >= 0 else c + '88')

    fig, ax = plt.subplots(figsize=(FIG_W, max(FIG_H, len(rows) * 0.38 + 1.5)),
                           dpi=DPI)

    y_pos = np.arange(len(rows))
    bars  = ax.barh(y_pos, deltas, color=bar_clr_final,
                    edgecolor='white', linewidth=0.4, height=0.7)

    # Value labels on bars
    for bar, d in zip(bars, deltas):
        x_off = 0.002 if d >= 0 else -0.002
        ha    = 'left' if d >= 0 else 'right'
        ax.text(bar.get_width() + x_off, bar.get_y() + bar.get_height() / 2,
                f'{d:+.3f}', va='center', ha=ha, fontsize=8)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=FS_TICK - 1)
    ax.axvline(x=0, color='black', linewidth=0.8)
    ax.set_xlabel('ΔEP relative to baseline (kWh/km)', fontsize=FS_LABEL)
    ax.set_title(
        f'Sensitivity: ΔEP at m = {M_REF//1000} t\n'
        f'(baseline EP₀ = {ep_base:.3f} kWh/km, 90 km/h, dry, 20°C, flat, no stops)',
        fontsize=FS_TITLE)
    ax.tick_params(axis='x', labelsize=FS_TICK)
    ax.grid(True, axis='x', alpha=GRID_ALPHA)

    # Legend for groups
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=c, label=g)
                       for g, c in GROUP_COLORS.items()]
    ax.legend(handles=legend_elements, fontsize=FS_LEGEND,
              loc='upper right', framealpha=0.9)

    fig.tight_layout()
    fig.savefig(OUT / 'sensitivity_tornado.png', dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print('  Saved: sensitivity_tornado.png')
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def run():
    print('Exp 8 — EP vs Mass factor plots + Sensitivity chart')
    plot_wind()
    plot_temperature()
    plot_road()
    plot_elevation()
    plot_stops()
    plot_cda()
    rows = plot_sensitivity()
    print(f'\n  Sensitivity at m={M_REF//1000} t (sorted by ΔEP):')
    for label, delta, group in rows:
        print(f'    [{group:12s}] {label:30s}  ΔEP = {delta:+.4f} kWh/km')
    return rows


if __name__ == '__main__':
    import matplotlib
    matplotlib.use('Agg')
    run()
