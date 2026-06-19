"""
Exp 6 补充图 — n_stop = 5 的速度剖面示意图
上面板：100 km 全程概览
下面板：放大第一次启停事件，标注 d_acc、d_dec 距离
"""
from __future__ import annotations
import sys, pathlib
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'simulation'))
from models.vehicle_physics import (BASELINE, apply_style,
                                     FIG_W, FIG_H, DPI, FS_LABEL,
                                     FS_TITLE, FS_TICK, FS_LEGEND)

OUTPUT = ROOT / 'simulation' / 'results' / 'figures' / 'exp6_speed_profile_n5.png'

N_STOP = 5
MAIN_COLOR = '#1565C0'


def _build_speed_profile(n_stop: int,
                          d_total: float = BASELINE['d_total'],
                          v_c: float     = BASELINE['v_c'],
                          a_acc: float   = BASELINE['a_acc'],
                          a_dec: float   = BASELINE['a_dec'],
                          n_pts_ramp: int = 120):
    """
    构建速度-距离剖面（纯定速巡航基线）。
    基线全程 v_c，起止速度均为 v_c。
    每次启停事件：cruise → dec(v_c→0) → acc(0→v_c) → cruise
    Profile: [cruise → dec → acc] × n_stop → cruise（尾段）
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


def plot():
    apply_style()

    v_c = BASELINE['v_c']
    v_c_kmh = v_c * 3.6
    a_acc = BASELINE['a_acc']
    a_dec = BASELINE['a_dec']
    d_acc_m = v_c ** 2 / (2.0 * a_acc)
    d_dec_m = v_c ** 2 / (2.0 * a_dec)
    d_total_km = BASELINE['d_total'] / 1_000

    d_cruise_total_m = BASELINE['d_total'] - N_STOP * (d_acc_m + d_dec_m)
    d_per_m = d_cruise_total_m / (N_STOP + 1)

    xs, vs = _build_speed_profile(N_STOP)
    if xs is None:
        raise RuntimeError('无法构建 speed profile，检查参数。')

    # ── 两行子图 ────────────────────────────────────────────────────────────
    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1, figsize=(FIG_W, FIG_H * 1.15), dpi=DPI,
        gridspec_kw={'height_ratios': [3, 2.5], 'hspace': 0.38},
    )

    # ═══════════════════════════════════════════════════════════════════════
    # 上面板：100 km 全程概览
    # ═══════════════════════════════════════════════════════════════════════
    ax_top.plot(xs, vs, color=MAIN_COLOR, linewidth=2.0, zorder=5)

    # 巡航速度参考线
    ax_top.axhline(y=v_c_kmh, color='grey', linewidth=0.8, linestyle=':', alpha=0.5)
    ax_top.text(d_total_km * 0.98, v_c_kmh + 1.5,
                f'$v_c$ = {v_c_kmh:.0f} km/h', ha='right', va='bottom',
                fontsize=FS_TICK - 1, color='grey')

    # 停车点三角标记（每次停车点 = 巡航段结束 + d_dec）
    stop_positions_km = []
    pos_m = d_per_m  # 第一段巡航后开始减速
    for i in range(N_STOP):
        stop_km = (pos_m + d_dec_m) / 1_000   # 减速结束 = 停车点
        stop_positions_km.append(stop_km)
        pos_m += d_dec_m + d_acc_m + d_per_m
    for i, sp in enumerate(stop_positions_km):
        ax_top.plot(sp, 0, 'v', color='#E91E63', markersize=7, zorder=6)
        ax_top.text(sp, -4.5, f'#{i+1}', ha='center', va='top',
                    fontsize=8, color='#E91E63', fontweight='bold')

    # n_stop 标注框
    ax_top.text(d_total_km * 0.5, v_c_kmh * 0.22,
                f'$n_{{stop}}$ = {N_STOP}     $d_{{total}}$ = {d_total_km:.0f} km',
                ha='center', va='center', fontsize=11, color='#333333',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='#E3F2FD',
                          edgecolor='#90CAF9', alpha=0.9))

    ax_top.set_xlim(0, d_total_km)
    ax_top.set_ylim(-8, v_c_kmh + 8)
    ax_top.set_xlabel('Distance (km)', fontsize=FS_LABEL)
    ax_top.set_ylabel('Speed (km/h)', fontsize=FS_LABEL)
    ax_top.set_title(
        f'Speed Profile with {N_STOP} Stop-Start Events\n'
        f'($v_c$ = {v_c_kmh:.0f} km/h,  '
        f'$a_{{acc}}$ = {a_acc:.2f} m/s$^2$,  '
        f'$a_{{dec}}$ = {a_dec:.2f} m/s$^2$)',
        fontsize=FS_TITLE)

    # 放大区域指示框（第一个停车事件附近）
    zoom_left_km  = max(0, (d_per_m - 500) / 1_000)
    zoom_right_km = (d_per_m + d_dec_m + d_acc_m + 500) / 1_000
    rect = mpatches.FancyBboxPatch(
        (zoom_left_km, -6), zoom_right_km - zoom_left_km, v_c_kmh + 12,
        boxstyle='round,pad=0.05',
        linewidth=1.5, edgecolor='#FF9800', facecolor='#FFF3E0', alpha=0.3,
        linestyle='--', zorder=2)
    ax_top.add_patch(rect)
    ax_top.text(zoom_right_km + 0.8, v_c_kmh * 0.50,
                'zoom\nbelow', fontsize=8, color='#E65100',
                fontstyle='italic', va='center', ha='left',
                fontweight='bold')

    # ═══════════════════════════════════════════════════════════════════════
    # 下面板：放大第一次启停事件
    # ═══════════════════════════════════════════════════════════════════════

    # 关键距离点（米）：巡航 d_per → 减速 d_dec → 停车 → 加速 d_acc → 巡航
    p_dec_start = d_per_m                       # 第一段巡航结束，开始减速
    p_dec_end   = p_dec_start + d_dec_m         # 停车点（v = 0）
    p_acc_start = p_dec_end                     # 停车后开始加速
    p_acc_end   = p_acc_start + d_acc_m         # 加速回 v_c

    # 放大范围
    margin = max(d_dec_m, d_acc_m) * 1.8
    zoom_l_m = p_dec_start - margin
    zoom_r_m = p_acc_end + margin

    mask = (xs * 1_000 >= zoom_l_m) & (xs * 1_000 <= zoom_r_m)

    # 用浅色填充减速和加速区域
    ax_bot.axvspan(p_dec_start, p_dec_end, alpha=0.12, color='#FF9800', zorder=1)
    ax_bot.axvspan(p_acc_start, p_acc_end, alpha=0.12, color='#E91E63', zorder=1)

    # 速度曲线
    ax_bot.plot(xs[mask] * 1_000, vs[mask], color=MAIN_COLOR, linewidth=2.5, zorder=5)

    # 巡航参考线
    ax_bot.axhline(y=v_c_kmh, color='grey', linewidth=0.8, linestyle=':', alpha=0.5)

    # ── 减速段标注 ──────────────────────────────────────────────────────────
    # 底部水平尺寸线（与速度曲线完全分离）
    y_dim = -12
    # 减速 — 左侧
    ax_bot.annotate('',
                    xy=(p_dec_start, y_dim), xytext=(p_dec_end, y_dim),
                    arrowprops=dict(arrowstyle='<->', color='#E65100', lw=1.6,
                                   shrinkA=0, shrinkB=0))
    ax_bot.text((p_dec_start + p_dec_end) / 2, y_dim - 3,
                f'$d_{{dec}}$ = {d_dec_m:.0f} m',
                ha='center', va='top', fontsize=10, color='#E65100',
                fontweight='bold')
    # 竖直虚线引导
    for xv in [p_dec_start, p_dec_end]:
        ax_bot.plot([xv, xv], [0, y_dim], color='#E65100', lw=0.7,
                    linestyle=':', alpha=0.6, zorder=3)

    # 加速 — 右侧
    ax_bot.annotate('',
                    xy=(p_acc_start, y_dim), xytext=(p_acc_end, y_dim),
                    arrowprops=dict(arrowstyle='<->', color='#C2185B', lw=1.6,
                                   shrinkA=0, shrinkB=0))
    ax_bot.text((p_acc_start + p_acc_end) / 2, y_dim - 3,
                f'$d_{{acc}}$ = {d_acc_m:.0f} m',
                ha='center', va='top', fontsize=10, color='#C2185B',
                fontweight='bold')
    for xv in [p_acc_start, p_acc_end]:
        ax_bot.plot([xv, xv], [0, y_dim], color='#C2185B', lw=0.7,
                    linestyle=':', alpha=0.6, zorder=3)

    # 停车点标记
    ax_bot.plot(p_dec_end, 0, 'o', color='#E91E63', markersize=8, zorder=7,
                markeredgecolor='white', markeredgewidth=1.5)
    ax_bot.text(p_dec_end, 4, 'v = 0\n(full stop)', ha='center', va='bottom',
                fontsize=8.5, color='#C2185B', fontweight='bold')

    # 区域标签（在阴影区域顶部）
    ax_bot.text((p_dec_start + p_dec_end) / 2, v_c_kmh * 0.80,
                'deceleration\n(regen braking)',
                ha='center', va='center', fontsize=9,
                color='#E65100', fontstyle='italic',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                          edgecolor='none', alpha=0.7))
    ax_bot.text((p_acc_start + p_acc_end) / 2, v_c_kmh * 0.80,
                'acceleration\n(motor drive)',
                ha='center', va='center', fontsize=9,
                color='#C2185B', fontstyle='italic',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                          edgecolor='none', alpha=0.7))

    # 巡航段标签
    cruise_mid_l = (zoom_l_m + p_dec_start) / 2
    cruise_mid_r = (p_acc_end + zoom_r_m) / 2
    ax_bot.text(cruise_mid_l, v_c_kmh - 4,
                'cruise @ 90 km/h', ha='center', va='top', fontsize=9,
                color='#555', fontstyle='italic')
    ax_bot.text(cruise_mid_r, v_c_kmh - 4,
                'cruise @ 90 km/h', ha='center', va='top', fontsize=9,
                color='#555', fontstyle='italic')

    ax_bot.set_xlim(zoom_l_m, zoom_r_m)
    ax_bot.set_ylim(-22, v_c_kmh + 8)
    ax_bot.set_xlabel('Distance (m)', fontsize=FS_LABEL)
    ax_bot.set_ylabel('Speed (km/h)', fontsize=FS_LABEL)
    ax_bot.set_title(
        'Zoom: First Stop-Start Event  (cruise $\\rightarrow$ dec $\\rightarrow$ stop '
        '$\\rightarrow$ acc $\\rightarrow$ cruise)',
        fontsize=FS_TITLE - 1)

    fig.savefig(OUTPUT, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {OUTPUT}')


if __name__ == '__main__':
    plot()
