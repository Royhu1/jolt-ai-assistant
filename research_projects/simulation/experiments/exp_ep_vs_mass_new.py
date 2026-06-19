# -*- coding: utf-8 -*-
"""
EP vs Mass 新图：DC 事件数、驾驶风格、再生制动效率

使用 exp_non_cruise.py 中的 _build_dc_segments 和
compute_ep_segmented 构建多质量扫描下的 EP 曲线族。

输出图（research_projects/simulation/results/figures/）：
    ep_vs_mass_dc.png      不同 DC 事件数
    ep_vs_mass_driver.png   不同驾驶风格
    ep_vs_mass_regen.png    不同再生制动效率
"""
from __future__ import annotations
import sys
import pathlib
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from scipy.stats import linregress

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'simulation'))
from models.vehicle_physics import (
    BASELINE, apply_style,
    FIG_W, FIG_H, DPI, FS_LABEL, FS_TITLE, FS_TICK, FS_LEGEND,
    FIT_LW, FIT_ALPHA, GRID_ALPHA,
)
from experiments.exp_non_cruise import (
    _build_dc_segments, compute_ep_segmented,
)

OUT = ROOT / 'simulation' / 'results' / 'figures'

MASSES = np.arange(10_000, 44_001, 2_000)  # 10-44 t

PERF_YLIM = (0.3, 3.2)
MASS_XLIM = (8_000, 46_000)


def _apply_style(ax, title: str,
                 xlabel: str = 'Vehicle Total Mass (kg)',
                 ylabel: str = 'Energy Performance (kWh/km)'):
    ax.set_xlabel(xlabel, fontsize=FS_LABEL)
    ax.set_ylabel(ylabel, fontsize=FS_LABEL)
    ax.set_title(title, fontsize=FS_TITLE)
    ax.tick_params(labelsize=FS_TICK)
    ax.grid(True, alpha=GRID_ALPHA)
    ax.set_xlim(MASS_XLIM)
    ax.set_ylim(PERF_YLIM)
    ax.legend(fontsize=FS_LEGEND, loc='upper left')


def _ep_line_seg(masses, n_events, a_acc, a_dec,
                 eta_regen, **extra):
    """EP vs mass 扫描（分段法）。"""
    eps = []
    for m in masses:
        segs = _build_dc_segments(
            n_events, a_acc=a_acc, a_dec=a_dec)
        res = compute_ep_segmented(
            segs, m=m, eta_regen=eta_regen, **extra)
        eps.append(res['EP_total'])
    eps = np.array(eps)
    slope, intercept, *_ = linregress(masses, eps)
    return slope, intercept, eps


def _plot_line(ax, masses, slope, intercept, color, label,
               lw=FIT_LW, alpha=FIT_ALPHA, ls='-', zorder=3):
    ax.plot(masses, slope * masses + intercept,
            color=color, linewidth=lw, alpha=alpha,
            linestyle=ls, label=label, zorder=zorder)


# ─────────────────────────────────────────────────────────
# 1. EP vs Mass -- 不同 DC 事件数
# ─────────────────────────────────────────────────────────
DC_CONDITIONS = [
    ('$N_a$ = 0 (pure cruise)', 0,  True),
    ('$N_a$ = 5',               5,  False),
    ('$N_a$ = 10',              10, False),
    ('$N_a$ = 20',              20, False),
    ('$N_a$ = 30',              30, False),
]


def plot_dc():
    apply_style()
    cmap = cm.get_cmap('YlOrRd', len(DC_CONDITIONS) + 2)
    colors = [cmap(i + 1) for i in range(len(DC_CONDITIONS))]

    a_acc = BASELINE['a_acc']
    a_dec = BASELINE['a_dec']

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
    for (label, na, is_base), color in zip(
            DC_CONDITIONS, colors):
        if na == 0:
            # 纯巡航：用单段巡航
            from models.vehicle_physics import compute_ep
            eps = np.array([
                compute_ep(m=m)['EP'] for m in MASSES])
            slope, intercept, *_ = linregress(MASSES, eps)
        else:
            slope, intercept, eps = _ep_line_seg(
                MASSES, n_events=na,
                a_acc=a_acc, a_dec=a_dec,
                eta_regen=0.0)
        ls = '--' if is_base else '-'
        lw = FIT_LW + 0.5 if is_base else FIT_LW
        _plot_line(ax, MASSES, slope, intercept, color,
                   label, lw=lw, ls=ls,
                   zorder=5 if is_base else 3)

    _apply_style(
        ax,
        'EP vs Mass — Effect of Driving Cycle Events\n'
        '($\\eta_{regen} = 0$, Standard driving)')
    fig.tight_layout()
    fig.savefig(OUT / 'ep_vs_mass_dc.png',
                dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print('  Saved: ep_vs_mass_dc.png')


# ─────────────────────────────────────────────────────────
# 2. EP vs Mass -- 不同驾驶风格
# ─────────────────────────────────────────────────────────
DRIVER_CONDITIONS = [
    ('Conservative ($a_{acc}$=0.30, $a_{dec}$=0.50)',
     0.30, 0.50, False),
    ('Standard ($a_{acc}$=0.58, $a_{dec}$=0.83)',
     0.58, 0.83, True),
    ('Aggressive ($a_{acc}$=1.50, $a_{dec}$=2.00)',
     1.50, 2.00, False),
]


def plot_driver():
    apply_style()
    colors = ['#2196F3', '#4CAF50', '#FF5722']

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
    for (label, a_acc, a_dec, is_base), color in zip(
            DRIVER_CONDITIONS, colors):
        slope, intercept, eps = _ep_line_seg(
            MASSES, n_events=10,
            a_acc=a_acc, a_dec=a_dec,
            eta_regen=0.0)
        ls = '--' if is_base else '-'
        lw = FIT_LW + 0.5 if is_base else FIT_LW
        _plot_line(ax, MASSES, slope, intercept, color,
                   label, lw=lw, ls=ls,
                   zorder=5 if is_base else 3)

    _apply_style(
        ax,
        'EP vs Mass — Effect of Driving Style\n'
        '($N_a = 10$, $\\eta_{regen} = 0$)')
    fig.tight_layout()
    fig.savefig(OUT / 'ep_vs_mass_driver.png',
                dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print('  Saved: ep_vs_mass_driver.png')


# ─────────────────────────────────────────────────────────
# 3. EP vs Mass -- 不同再生制动效率
# ─────────────────────────────────────────────────────────
REGEN_CONDITIONS = [
    ('$\\eta_{regen}$ = 0',    0.0,  False),
    ('$\\eta_{regen}$ = 0.3',  0.3,  False),
    ('$\\eta_{regen}$ = 0.5',  0.5,  False),
    ('$\\eta_{regen}$ = 0.7',  0.7,  False),
    ('$\\eta_{regen}$ = 0.9',  0.9,  True),
]


def plot_regen():
    apply_style()
    cmap = cm.get_cmap('RdYlGn', len(REGEN_CONDITIONS) + 1)
    colors = [cmap(i) for i in range(len(REGEN_CONDITIONS))]

    a_acc = BASELINE['a_acc']
    a_dec = BASELINE['a_dec']

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
    for (label, eta_r, is_base), color in zip(
            REGEN_CONDITIONS, colors):
        slope, intercept, eps = _ep_line_seg(
            MASSES, n_events=10,
            a_acc=a_acc, a_dec=a_dec,
            eta_regen=eta_r)
        ls = '--' if is_base else '-'
        lw = FIT_LW + 0.5 if is_base else FIT_LW
        _plot_line(ax, MASSES, slope, intercept, color,
                   label, lw=lw, ls=ls,
                   zorder=5 if is_base else 3)

    _apply_style(
        ax,
        'EP vs Mass — Effect of Regenerative Braking\n'
        '($N_a = 10$, Standard driving)')
    fig.tight_layout()
    fig.savefig(OUT / 'ep_vs_mass_regen.png',
                dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print('  Saved: ep_vs_mass_regen.png')


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────
def run():
    print('EP vs Mass (new): DC events, driver, regen')
    plot_dc()
    plot_driver()
    plot_regen()


if __name__ == '__main__':
    import matplotlib
    matplotlib.use('Agg')
    run()
