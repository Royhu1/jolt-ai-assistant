"""
多因素耦合仿真 — 二维热力图
验证 Section 1.2.2 中识别的非零二阶混合偏导（交互效应）：
  (a) EP(m, C_rr)   — 滚阻力 ∝ m·Crr
  (b) EP(m, Δh)     — 势能 ∝ m·Δh
  (c) EP(CdA, V_wind) — 风阻 ∝ CdA·V²
  (d) EP(m, T)      — 温度全局缩放
"""
from __future__ import annotations
import sys, pathlib
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'simulation'))
from models.vehicle_physics import (
    compute_ep, BASELINE, apply_style,
    FIG_W, FIG_H, DPI, FS_LABEL, FS_TITLE, FS_TICK,
)

FIG_DIR = ROOT / 'simulation' / 'results' / 'figures'


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _ep_grid(xname: str, xvals: np.ndarray,
             yname: str, yvals: np.ndarray) -> np.ndarray:
    """在 (xvals × yvals) 网格上调用 compute_ep，返回 EP 矩阵 [ny, nx]。"""
    Z = np.empty((len(yvals), len(xvals)))
    for j, yv in enumerate(yvals):
        for i, xv in enumerate(xvals):
            kw = {**BASELINE, xname: float(xv), yname: float(yv)}
            Z[j, i] = compute_ep(**kw)['EP']
    return Z


def _plot_heatmap(
    ax, X, Y, Z, *,
    xlabel: str, ylabel: str, title: str,
    cmap: str = 'viridis',
    contour_levels: int = 10,
    fmt: str = '%.2f',
):
    """在给定 Axes 上绘制 pcolormesh + contour 等值线。"""
    pcm = ax.pcolormesh(X, Y, Z, cmap=cmap, shading='gouraud')
    cs = ax.contour(X, Y, Z, levels=contour_levels,
                    colors='white', linewidths=0.8, alpha=0.85)
    ax.clabel(cs, inline=True, fontsize=8, fmt=fmt)
    cb = plt.colorbar(pcm, ax=ax, pad=0.02)
    cb.set_label('EP (kWh/km)', fontsize=FS_LABEL - 1)
    cb.ax.tick_params(labelsize=FS_TICK - 1)
    ax.set_xlabel(xlabel, fontsize=FS_LABEL)
    ax.set_ylabel(ylabel, fontsize=FS_LABEL)
    ax.set_title(title, fontsize=FS_TITLE)
    ax.tick_params(labelsize=FS_TICK)
    return pcm


# ── (a) EP(m, C_rr) ─────────────────────────────────────────────────────────

def heatmap_m_crr():
    masses = np.linspace(10_000, 44_000, 18)
    crrs   = np.linspace(0.004, 0.010, 13)
    Z = _ep_grid('m', masses, 'crr', crrs)

    X, Y = np.meshgrid(masses / 1000, crrs)
    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    _plot_heatmap(
        ax, X, Y, Z,
        xlabel='Gross Vehicle Weight (tonnes)',
        ylabel='Rolling Resistance Coefficient $C_{rr}$',
        title='(a)  EP($m$, $C_{rr}$) — '
              'Rolling Resistance Interaction',
        contour_levels=12, fmt='%.2f',
    )
    fig.tight_layout()
    out = FIG_DIR / 'heatmap_m_crr.png'
    fig.savefig(out, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  [heatmap] 已保存 {out.name}')
    return Z, masses, crrs


# ── (b) EP(m, Δh) ───────────────────────────────────────────────────────────

def heatmap_m_dh():
    masses  = np.linspace(10_000, 44_000, 18)
    delta_hs = np.linspace(-200, 200, 21)
    Z = _ep_grid('m', masses, 'delta_h', delta_hs)

    X, Y = np.meshgrid(masses / 1000, delta_hs)
    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    _plot_heatmap(
        ax, X, Y, Z,
        xlabel='Gross Vehicle Weight (tonnes)',
        ylabel='Net Elevation Change $\\Delta h$ (m)',
        title='(b)  EP($m$, $\\Delta h$) — '
              'Gravitational Potential Interaction',
        cmap='coolwarm', contour_levels=12, fmt='%.2f',
    )
    fig.tight_layout()
    out = FIG_DIR / 'heatmap_m_dh.png'
    fig.savefig(out, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  [heatmap] 已保存 {out.name}')
    return Z, masses, delta_hs


# ── (c) EP(CdA, V_wind) ─────────────────────────────────────────────────────

def heatmap_cda_wind():
    cdas   = np.linspace(3.0, 9.0, 13)
    winds  = np.linspace(0, 15, 16)
    Z = _ep_grid('cda', cdas, 'v_wind', winds)

    X, Y = np.meshgrid(cdas, winds)
    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    _plot_heatmap(
        ax, X, Y, Z,
        xlabel='Drag Area $C_dA$ (m²)',
        ylabel='Wind Speed $V_{wind}$ (m/s)',
        title='(c)  EP($C_dA$, $V_{wind}$) — '
              'Aerodynamic Drag Interaction',
        contour_levels=10, fmt='%.2f',
    )
    fig.tight_layout()
    out = FIG_DIR / 'heatmap_cda_wind.png'
    fig.savefig(out, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  [heatmap] 已保存 {out.name}')
    return Z, cdas, winds


# ── (d) EP(m, T) ─────────────────────────────────────────────────────────────

def heatmap_m_temp():
    masses = np.linspace(10_000, 44_000, 18)
    temps  = np.linspace(-5, 35, 9)
    Z = _ep_grid('m', masses, 'T_amb', temps)

    X, Y = np.meshgrid(masses / 1000, temps)
    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    _plot_heatmap(
        ax, X, Y, Z,
        xlabel='Gross Vehicle Weight (tonnes)',
        ylabel='Ambient Temperature $T$ (°C)',
        title='(d)  EP($m$, $T$) — '
              'Temperature Scaling Interaction',
        contour_levels=10, fmt='%.3f',
    )
    fig.tight_layout()
    out = FIG_DIR / 'heatmap_m_temp.png'
    fig.savefig(out, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  [heatmap] 已保存 {out.name}')
    return Z, masses, temps


# ── 主入口 ────────────────────────────────────────────────────────────────────

def run() -> dict:
    """运行全部 4 张热力图并返回结果摘要。"""
    print('== Multi-factor coupling heatmaps ==')
    Z_mc, masses_mc, crrs   = heatmap_m_crr()
    Z_mh, masses_mh, dhs    = heatmap_m_dh()
    Z_cw, cdas, winds       = heatmap_cda_wind()
    Z_mt, masses_mt, temps  = heatmap_m_temp()

    return dict(
        heatmap_m_crr   = dict(EP_min=Z_mc.min(), EP_max=Z_mc.max()),
        heatmap_m_dh    = dict(EP_min=Z_mh.min(), EP_max=Z_mh.max()),
        heatmap_cda_wind= dict(EP_min=Z_cw.min(), EP_max=Z_cw.max()),
        heatmap_m_temp  = dict(EP_min=Z_mt.min(), EP_max=Z_mt.max()),
    )


if __name__ == '__main__':
    res = run()
    for name, vals in res.items():
        print(f'  {name}: EP ∈ [{vals["EP_min"]:.3f}, '
              f'{vals["EP_max"]:.3f}] kWh/km')
