"""
非定速巡航下的 EP 仿真实验
=========================

验证 Section 1.2.3 推导的分段拼接 EP 公式（Eq.15–21）。

Exp A：标准启停工况（分段法 vs compute_ep 一致性验证）
Exp B：混合速度巡��（多种巡航速度的 speed profile）
Exp C：不同驾驶风格的��响（加减速度分布）
Exp D：EP_cruise@90 修正验证（Section 1.2.4）

Section 2.3.2：不同工况下的仿真 EP（eta_regen=0）
Section 2.3.3：不同驾驶行为下的仿真 EP（eta_regen=0）
Section 2.3.4：再生制动效率的影响（eta_regen 扫描）
Section 2.3.5：Driving cycle 修正验证（eta_regen=0）
"""
from __future__ import annotations
import sys
import pathlib
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'simulation'))
from models.vehicle_physics import (
    compute_ep, BASELINE, eta_bat, apply_style,
    FIG_W, FIG_H, DPI, FS_LABEL, FS_TITLE, FS_TICK, FS_LEGEND,
    FIT_LW, GRID_ALPHA,
)

_J_TO_KWH = 1.0 / 3_600_000.0
FIG_DIR   = ROOT / 'simulation' / 'results' / 'figures'
TABLE_DIR = ROOT / 'simulation' / 'results' / 'tables'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  分段能耗计算函数（严格按照 Eq.15–21 实现）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _v2_bar(v0: float, v1: float) -> float:
    """
    恒加速度下 v^2 的时间均值（Eq.15 下方公式）。
    v0: 段起始速度，v1: 段终止速度
    返回 (v0^2 + v0*v1 + v1^2) / 3
    """
    return (v0**2 + v0 * v1 + v1**2) / 3.0


def _acc_segment_energy(
    v_start: float, v_end: float, a_acc: float,
    m: float, crr: float, cda: float, rho: float,
    eta_dt: float, g: float, v_wind: float = 0.0,
) -> dict:
    """
    单个加速段能耗（Eq.15–16）。
    v_start < v_end，a_acc > 0。
    返回 dict(d_acc, E_acc, delta_KE, F_aero_avg)
    """
    d_acc = (v_end**2 - v_start**2) / (2.0 * a_acc)          # Eq.15
    delta_KE = 0.5 * m * (v_end**2 - v_start**2)
    F_rr = crr * m * g
    v2bar = _v2_bar(v_start, v_end)
    F_aero_avg = 0.5 * rho * cda * (v2bar + v_wind**2 / 2.0)
    E_acc = (delta_KE + (F_rr + F_aero_avg) * d_acc) / eta_dt  # Eq.16
    return dict(d_acc=d_acc, E_acc=E_acc, delta_KE=delta_KE,
                F_aero_avg=F_aero_avg)


def _dec_segment_energy(
    v_start: float, v_end: float, a_dec: float,
    m: float, crr: float, cda: float, rho: float,
    eta_regen: float, g: float, v_wind: float = 0.0,
) -> dict:
    """
    单个减速段能耗（Eq.17）。
    v_start > v_end，a_dec > 0。
    返回 dict(d_dec, E_regen, delta_KE, F_aero_avg)
    """
    d_dec = (v_start**2 - v_end**2) / (2.0 * a_dec)
    delta_KE = 0.5 * m * (v_start**2 - v_end**2)
    F_rr = crr * m * g
    v2bar = _v2_bar(v_end, v_start)
    F_aero_avg = 0.5 * rho * cda * (v2bar + v_wind**2 / 2.0)
    regen_base = delta_KE - (F_rr + F_aero_avg) * d_dec
    E_regen = eta_regen * max(0.0, regen_base)               # Eq.17
    return dict(d_dec=d_dec, E_regen=E_regen, delta_KE=delta_KE,
                F_aero_avg=F_aero_avg)


def _cruise_segment_energy(
    v_c: float, d_cruise: float,
    m: float, crr: float, cda: float, rho: float,
    eta_dt: float, g: float, v_wind: float = 0.0,
) -> dict:
    """
    单个巡航段能耗（Eq.18）。
    返回 dict(E_cruise, F_rr, F_aero_c)
    """
    F_rr = crr * m * g
    F_aero_c = 0.5 * rho * cda * (v_c**2 + v_wind**2 / 2.0)
    E_cruise = (F_rr + F_aero_c) * d_cruise / eta_dt          # Eq.18
    return dict(E_cruise=E_cruise, F_rr=F_rr, F_aero_c=F_aero_c)


def compute_ep_segmented(
    segments: list[dict],
    m: float       = BASELINE['m'],
    crr: float     = BASELINE['crr'],
    cda: float     = BASELINE['cda'],
    rho: float     = BASELINE['rho'],
    eta_dt: float  = BASELINE['eta_dt'],
    eta_regen: float = BASELINE['eta_regen'],
    v_wind: float  = 0.0,
    delta_h: float = 0.0,
    T_amb: float   = 20.0,
    g: float       = BASELINE['g'],
) -> dict:
    """
    分段拼接计算 EP（Eq.19–21）。

    Parameters
    ----------
    segments : list of dict
        每个 dict 描述一个段落：
        - {'type': 'cruise', 'v': v_c (m/s), 'd': distance (m)}
        - {'type': 'acc', 'v0': v_start, 'v1': v_end, 'a': a_acc}
        - {'type': 'dec', 'v0': v_start, 'v1': v_end, 'a': a_dec}

    Returns
    -------
    dict with keys:
        EP_total, EP_cruise, EP_nocruise,
        E_acc_total, E_regen_total, E_cruise_total,
        E_elev, d_total, eta_bat_val,
        segments_detail (每段的能耗明细)
    """
    common = dict(m=m, crr=crr, cda=cda, rho=rho, g=g,
                  v_wind=v_wind)

    total_E_acc    = 0.0   # J
    total_E_regen  = 0.0   # J
    total_E_cruise = 0.0   # J
    d_total        = 0.0   # m
    details        = []

    for seg in segments:
        stype = seg['type']
        if stype == 'cruise':
            res = _cruise_segment_energy(
                v_c=seg['v'], d_cruise=seg['d'],
                eta_dt=eta_dt, **common)
            total_E_cruise += res['E_cruise']
            d_total += seg['d']
            details.append({**seg, **res})

        elif stype == 'acc':
            res = _acc_segment_energy(
                v_start=seg['v0'], v_end=seg['v1'], a_acc=seg['a'],
                eta_dt=eta_dt, **common)
            total_E_acc += res['E_acc']
            d_total += res['d_acc']
            details.append({**seg, 'd': res['d_acc'], **res})

        elif stype == 'dec':
            res = _dec_segment_energy(
                v_start=seg['v0'], v_end=seg['v1'], a_dec=seg['a'],
                eta_regen=eta_regen, **common)
            total_E_regen += res['E_regen']
            d_total += res['d_dec']
            details.append({**seg, 'd': res['d_dec'], **res})

    # 海拔势能（平路时为 0）
    E_elev = m * g * delta_h / eta_dt  # J

    # Eq.19: EP_cruise
    _eta_bat = eta_bat(T_amb)
    EP_cruise = (total_E_cruise + E_elev) * _J_TO_KWH / (
        _eta_bat * d_total / 1000.0)

    # Eq.20: EP_nocruise
    EP_nocruise = (total_E_acc - total_E_regen) * _J_TO_KWH / (
        _eta_bat * d_total / 1000.0)

    # Eq.21: EP_total
    EP_total = EP_cruise + EP_nocruise

    return dict(
        EP_total     = EP_total,
        EP_cruise    = EP_cruise,
        EP_nocruise  = EP_nocruise,
        E_acc_total  = total_E_acc * _J_TO_KWH,
        E_regen_total= total_E_regen * _J_TO_KWH,
        E_cruise_total= total_E_cruise * _J_TO_KWH,
        E_elev       = E_elev * _J_TO_KWH,
        d_total      = d_total,
        eta_bat_val  = _eta_bat,
        details      = details,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Speed profile 构造器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_stop_start_segments(
    n_stop: int,
    v_c: float    = BASELINE['v_c'],
    a_acc: float  = BASELINE['a_acc'],
    a_dec: float  = BASELINE['a_dec'],
    d_total: float = BASELINE['d_total'],
) -> list[dict]:
    """
    构造 n_stop 次 v_c→0→v_c 启停事件的 segment 列表。
    基线为纯定速巡航（起止速度均为 v_c）。
    """
    d_acc_one = v_c**2 / (2.0 * a_acc)
    d_dec_one = v_c**2 / (2.0 * a_dec)
    d_cruise_total = d_total - n_stop * (d_acc_one + d_dec_one)
    if d_cruise_total < 0:
        raise ValueError(f"n_stop={n_stop} 过多")
    d_per = d_cruise_total / (n_stop + 1)

    segs = []
    for _ in range(n_stop):
        segs.append({'type': 'cruise', 'v': v_c, 'd': d_per})
        segs.append({'type': 'dec', 'v0': v_c, 'v1': 0.0,
                     'a': a_dec})
        segs.append({'type': 'acc', 'v0': 0.0, 'v1': v_c,
                     'a': a_acc})
    segs.append({'type': 'cruise', 'v': v_c, 'd': d_per})
    return segs


def _build_mixed_speed_segments(
    a_acc: float  = BASELINE['a_acc'],
    a_dec: float  = BASELINE['a_dec'],
) -> list[dict]:
    """
    构造混合速度行程（Exp B）。

    Profile:
      30 km @90 km/h → 减速到 60 km/h → 20 km @60 km/h
      → 加速到 90 km/h → 30 km @90 km/h
      → 减速到 40 km/h → 20 km @40 km/h

    总行程 ≈ 100 km（加减速段距离微调后精确计算）。
    注：加减速段距离需从总巡航距离中扣除以保持 100 km。
    """
    v90 = 25.0          # 90 km/h in m/s
    v60 = 60.0 / 3.6    # ≈ 16.667 m/s
    v40 = 40.0 / 3.6    # ≈ 11.111 m/s

    # 加减速段距离
    d_90_60_dec = (v90**2 - v60**2) / (2.0 * a_dec)
    d_60_90_acc = (v90**2 - v60**2) / (2.0 * a_acc)
    d_90_40_dec = (v90**2 - v40**2) / (2.0 * a_dec)

    # 原始巡航段名义距离（km → m）
    d_c1_nominal = 30_000.0  # @90 km/h
    d_c2_nominal = 20_000.0  # @60 km/h
    d_c3_nominal = 30_000.0  # @90 km/h
    d_c4_nominal = 20_000.0  # @40 km/h

    # 总行程固定 100 km，分配剩余距离
    d_trans = d_90_60_dec + d_60_90_acc + d_90_40_dec
    d_cruise_budget = 100_000.0 - d_trans
    # 按名义比例分配
    total_nominal = (d_c1_nominal + d_c2_nominal
                     + d_c3_nominal + d_c4_nominal)
    d_c1 = d_c1_nominal / total_nominal * d_cruise_budget
    d_c2 = d_c2_nominal / total_nominal * d_cruise_budget
    d_c3 = d_c3_nominal / total_nominal * d_cruise_budget
    d_c4 = d_c4_nominal / total_nominal * d_cruise_budget

    segs = [
        {'type': 'cruise', 'v': v90, 'd': d_c1},
        {'type': 'dec', 'v0': v90, 'v1': v60, 'a': a_dec},
        {'type': 'cruise', 'v': v60, 'd': d_c2},
        {'type': 'acc', 'v0': v60, 'v1': v90, 'a': a_acc},
        {'type': 'cruise', 'v': v90, 'd': d_c3},
        {'type': 'dec', 'v0': v90, 'v1': v40, 'a': a_dec},
        {'type': 'cruise', 'v': v40, 'd': d_c4},
    ]
    return segs


def _build_speed_profile_plot(segments: list[dict]) -> tuple:
    """
    从 segment 列表生成用于绘图的 (distance_km, speed_kmh) 数组。
    """
    xs, vs = [0.0], []
    d = 0.0
    n_pts = 80  # 加减速段的绘图点数

    # 确定起始速度
    seg0 = segments[0]
    if seg0['type'] == 'cruise':
        vs.append(seg0['v'] * 3.6)
    elif seg0['type'] == 'acc':
        vs.append(seg0['v0'] * 3.6)
    elif seg0['type'] == 'dec':
        vs.append(seg0['v0'] * 3.6)

    for seg in segments:
        if seg['type'] == 'cruise':
            d += seg['d']
            xs.append(d / 1000.0)
            vs.append(seg['v'] * 3.6)
        elif seg['type'] == 'acc':
            d_seg = (seg['v1']**2 - seg['v0']**2) / (2.0 * seg['a'])
            x_local = np.linspace(0, d_seg, n_pts)
            v_local = np.sqrt(
                np.maximum(0, seg['v0']**2 + 2.0 * seg['a'] * x_local))
            for xi, vi in zip(x_local[1:], v_local[1:]):
                xs.append((d + xi) / 1000.0)
                vs.append(vi * 3.6)
            d += d_seg
        elif seg['type'] == 'dec':
            d_seg = (seg['v0']**2 - seg['v1']**2) / (2.0 * seg['a'])
            x_local = np.linspace(0, d_seg, n_pts)
            v_local = np.sqrt(
                np.maximum(0, seg['v0']**2 - 2.0 * seg['a'] * x_local))
            for xi, vi in zip(x_local[1:], v_local[1:]):
                xs.append((d + xi) / 1000.0)
                vs.append(vi * 3.6)
            d += d_seg

    return np.array(xs), np.array(vs)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Exp A：标准启停工况验证
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_exp_a() -> dict:
    """
    构造 n=5 次 v_c→0→v_c 启停事件，用分段法计算 EP 并分解。
    """
    print('\n=== Exp A: 标准启停工况 ===')
    n_stop = 5
    p = BASELINE.copy()

    # ── 分段法 ────────────────────────────────────────────────
    segs = _build_stop_start_segments(n_stop)
    new = compute_ep_segmented(segs, m=p['m'])

    # baseline（纯巡航）
    baseline_ep = compute_ep(m=p['m'], n_stop=0)['EP']

    print(f'  分段法 EP_total   = {new["EP_total"]:.6f} kWh/km')
    print(f'  EP_cruise         = {new["EP_cruise"]:.6f} kWh/km')
    print(f'  EP_nocruise       = {new["EP_nocruise"]:.6f} kWh/km')
    print(f'  Baseline EP       = {baseline_ep:.6f} kWh/km')
    delta_pct = (new['EP_total'] - baseline_ep) / baseline_ep * 100
    print(f'  vs baseline       = {delta_pct:+.2f}%')

    # ── 绘图 ──────────────────────────────────────────────────
    apply_style()
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(FIG_W * 1.2, FIG_H * 0.8), dpi=DPI)

    # Left: speed profile
    xs, vs = _build_speed_profile_plot(segs)
    ax1.plot(xs, vs, color='#1565C0', linewidth=2.0)
    ax1.axhline(y=90, color='grey', linestyle=':', linewidth=0.8,
                alpha=0.5)
    ax1.set_xlabel('Distance (km)', fontsize=FS_LABEL)
    ax1.set_ylabel('Speed (km/h)', fontsize=FS_LABEL)
    ax1.set_title('Exp A: Speed Profile (5 stops)',
                  fontsize=FS_TITLE)
    ax1.set_xlim(0, 100)
    ax1.set_ylim(-3, 100)

    # Right: EP 分解堆叠柱状图
    labels = ['Baseline\n(pure cruise)', 'Exp A\n(5 stops)']
    ep_cruise_vals = [baseline_ep, new['EP_cruise']]
    ep_nocruise_vals = [0.0, new['EP_nocruise']]

    bars1 = ax2.bar(labels, ep_nocruise_vals, color='#FF5722',
                    width=0.5, edgecolor='#333', linewidth=0.8,
                    label='$EP_{no\\_cruise}$')
    bars2 = ax2.bar(labels, ep_cruise_vals, color='#2196F3',
                    width=0.5, edgecolor='#333', linewidth=0.8,
                    bottom=ep_nocruise_vals,
                    label='$EP_{cruise}$')

    # 标注总 EP
    for i, (b1, b2) in enumerate(zip(bars1, bars2)):
        total = ep_cruise_vals[i] + ep_nocruise_vals[i]
        ax2.text(b1.get_x() + b1.get_width() / 2,
                 total + 0.005,
                 f'{total:.4f}', ha='center', va='bottom',
                 fontsize=FS_TICK, fontweight='bold')

    ax2.set_ylabel('EP (kWh/km)', fontsize=FS_LABEL)
    ax2.set_title('EP Decomposition',
                  fontsize=FS_TITLE)
    ax2.set_ylim(0, max(baseline_ep, new['EP_total']) * 1.15)
    ax2.legend(fontsize=FS_LEGEND, loc='upper left')

    fig.suptitle(
        'Exp A: Standard Stop-Start (5 events)',
        fontsize=FS_TITLE + 1)
    fig.tight_layout()
    fig.savefig(FIG_DIR / 'exp_noncruise_a.png',
                dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: exp_noncruise_a.png')

    return dict(
        ep_total=new['EP_total'],
        ep_cruise=new['EP_cruise'],
        ep_nocruise=new['EP_nocruise'],
        baseline_ep=baseline_ep,
        delta_pct=delta_pct,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Exp B：混合速度巡航
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_exp_b() -> dict:
    """
    构造包含 90/60/40 km/h 多种巡航速度的 speed profile，
    用分段法计算 EP，与纯 90 km/h 巡航对比。
    """
    print('\n=== Exp B: 混合速度巡航 ===')
    p = BASELINE.copy()

    # 混合工况
    segs = _build_mixed_speed_segments()
    res = compute_ep_segmented(segs, m=p['m'])

    # 纯 90 km/h 巡航 baseline
    baseline_ep = compute_ep(m=p['m'], n_stop=0)['EP']

    print(f'  混合工况 EP_total    = {res["EP_total"]:.6f} kWh/km')
    print(f'  混合工况 EP_cruise   = {res["EP_cruise"]:.6f} kWh/km')
    print(f'  混合工况 EP_nocruise = {res["EP_nocruise"]:.6f} kWh/km')
    print(f'  纯 90 km/h baseline  = {baseline_ep:.6f} kWh/km')
    print(f'  d_total              = {res["d_total"]:.1f} m')

    # 各段明细
    seg_info = []
    for i, det in enumerate(res['details']):
        stype = det['type']
        if stype == 'cruise':
            seg_info.append({
                'seg': i + 1, 'type': 'cruise',
                'v_kmh': det['v'] * 3.6,
                'd_m': det['d'],
                'E_kWh': det['E_cruise'] * _J_TO_KWH,
            })
        elif stype == 'acc':
            seg_info.append({
                'seg': i + 1, 'type': 'acc',
                'v_kmh': f"{det['v0']*3.6:.0f}→{det['v1']*3.6:.0f}",
                'd_m': det['d_acc'],
                'E_kWh': det['E_acc'] * _J_TO_KWH,
            })
        elif stype == 'dec':
            seg_info.append({
                'seg': i + 1, 'type': 'dec',
                'v_kmh': f"{det['v0']*3.6:.0f}→{det['v1']*3.6:.0f}",
                'd_m': det['d_dec'],
                'E_kWh': (-det['E_regen'] * _J_TO_KWH
                          if 'E_regen' in det else 0),
            })

    # ── 绘图 ──────────────────────────────────────────────────
    apply_style()
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(FIG_W * 1.3, FIG_H * 0.85), dpi=DPI)

    # Left: speed profile with annotations
    xs, vs = _build_speed_profile_plot(segs)
    ax1.plot(xs, vs, color='#1565C0', linewidth=2.2)
    ax1.axhline(y=90, color='grey', linestyle=':', linewidth=0.8,
                alpha=0.5, label='90 km/h ref')

    # 标注巡航段
    d_cursor = 0.0
    for seg in segs:
        if seg['type'] == 'cruise':
            d_mid = (d_cursor + seg['d'] / 2) / 1000.0
            ax1.annotate(
                f'{seg["v"]*3.6:.0f} km/h\n{seg["d"]/1000:.1f} km',
                xy=(d_mid, seg['v'] * 3.6),
                xytext=(0, 12), textcoords='offset points',
                ha='center', fontsize=8, color='#333',
                arrowprops=dict(arrowstyle='-', color='#999',
                                lw=0.5))
            d_cursor += seg['d']
        elif seg['type'] == 'acc':
            d_seg = (seg['v1']**2 - seg['v0']**2) / (2 * seg['a'])
            d_cursor += d_seg
        elif seg['type'] == 'dec':
            d_seg = (seg['v0']**2 - seg['v1']**2) / (2 * seg['a'])
            d_cursor += d_seg

    ax1.set_xlabel('Distance (km)', fontsize=FS_LABEL)
    ax1.set_ylabel('Speed (km/h)', fontsize=FS_LABEL)
    ax1.set_title('Exp B: Mixed Speed Profile',
                  fontsize=FS_TITLE)
    ax1.set_xlim(0, 100)
    ax1.set_ylim(-3, 105)

    # Right: EP decomposition bar chart
    cats = ['EP_nocruise\n(Eq.20)',
            'EP_cruise\n(Eq.19)',
            'EP_total\n(Eq.21)',
            'Baseline\n(90 km/h)']
    vals = [res['EP_nocruise'], res['EP_cruise'],
            res['EP_total'], baseline_ep]
    colors = ['#FF9800', '#4CAF50', '#2196F3', '#9E9E9E']
    bars = ax2.bar(cats, vals, color=colors, width=0.55,
                   edgecolor='#333', linewidth=0.8)
    for bar, v in zip(bars, vals):
        ypos = bar.get_height() if v >= 0 else 0
        ax2.text(bar.get_x() + bar.get_width() / 2, ypos,
                 f'{v:.4f}', ha='center',
                 va='bottom' if v >= 0 else 'top',
                 fontsize=FS_TICK - 1, fontweight='bold')
    ax2.set_ylabel('EP (kWh/km)', fontsize=FS_LABEL)
    ax2.set_title('EP Decomposition: Mixed vs Baseline',
                  fontsize=FS_TITLE)
    ax2.axhline(0, color='black', linewidth=0.5)

    fig.suptitle(
        'Exp B — Mixed Cruising Speeds: '
        'EP Decomposition (Eq.19–21)',
        fontsize=FS_TITLE + 1)
    fig.tight_layout()
    fig.savefig(FIG_DIR / 'exp_noncruise_b.png',
                dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: exp_noncruise_b.png')

    return dict(
        ep_total=res['EP_total'],
        ep_cruise=res['EP_cruise'],
        ep_nocruise=res['EP_nocruise'],
        baseline_ep=baseline_ep,
        d_total=res['d_total'],
        seg_info=seg_info,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Exp C：不同驾驶风格的影响
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_exp_c() -> dict:
    """
    固定 5 次 v_c→0→v_c 启停，改变加减速度分布，
    对比不同驾驶风格下的 EP。
    """
    print('\n=== Exp C: 不同驾驶风格的影响 ===')
    p = BASELINE.copy()

    styles = [
        ('Gentle',   0.3,  0.5),
        ('Standard', 0.58, 0.83),
        ('Aggressive', 1.0, 1.5),
        ('Extreme',  2.0,  2.0),
    ]

    n_stop = 5
    results = []
    for name, a_acc, a_dec in styles:
        segs = _build_stop_start_segments(
            n_stop, a_acc=a_acc, a_dec=a_dec)
        res = compute_ep_segmented(
            segs, m=p['m'], eta_dt=p['eta_dt'],
            eta_regen=p['eta_regen'])
        results.append({
            'style': name,
            'a_acc': a_acc, 'a_dec': a_dec,
            'EP_total': res['EP_total'],
            'EP_cruise': res['EP_cruise'],
            'EP_nocruise': res['EP_nocruise'],
            'E_acc': res['E_acc_total'],
            'E_regen': res['E_regen_total'],
        })
        print(f'  {name:12s}  a_acc={a_acc:.2f}  a_dec={a_dec:.2f}  '
              f'EP={res["EP_total"]:.6f}  '
              f'EP_nc={res["EP_nocruise"]:.6f}')

    # ── 绘图 ──────────────────────────────────────────────────
    apply_style()
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(FIG_W * 1.3, FIG_H * 0.85), dpi=DPI)

    # Left: EP_total stacked bar (EP_cruise + EP_nocruise)
    names = [r['style'] for r in results]
    ep_c  = [r['EP_cruise'] for r in results]
    ep_nc = [r['EP_nocruise'] for r in results]
    ep_t  = [r['EP_total'] for r in results]

    x = np.arange(len(names))
    w = 0.5
    bars1 = ax1.bar(x, ep_nc, w, label='$EP_{no\\_cruise}$ (Eq.20)',
                    color='#FF9800', edgecolor='#333', linewidth=0.6)
    bars2 = ax1.bar(x, ep_c, w, bottom=ep_nc,
                    label='$EP_{cruise}$ (Eq.19)',
                    color='#4CAF50', edgecolor='#333', linewidth=0.6)

    for i, (b1, b2, ept) in enumerate(zip(bars1, bars2, ep_t)):
        ax1.text(b2.get_x() + b2.get_width() / 2,
                 b2.get_y() + b2.get_height(),
                 f'{ept:.4f}', ha='center', va='bottom',
                 fontsize=FS_TICK - 1, fontweight='bold')

    ax1.set_xticks(x)
    ax1.set_xticklabels(
        [f'{n}\n($a_{{acc}}$={r["a_acc"]}, '
         f'$a_{{dec}}$={r["a_dec"]})'
         for n, r in zip(names, results)],
        fontsize=FS_TICK - 2)
    ax1.set_ylabel('EP (kWh/km)', fontsize=FS_LABEL)
    ax1.set_title('EP Decomposition by Driving Style',
                  fontsize=FS_TITLE)
    ax1.legend(fontsize=FS_LEGEND, loc='upper left')

    # Right: EP_nocruise vs a_acc
    a_accs = [r['a_acc'] for r in results]
    ep_ncs = [r['EP_nocruise'] for r in results]
    ax2.plot(a_accs, ep_ncs, 'o-', color='#E91E63',
             markersize=8, linewidth=2, label='$EP_{no\\_cruise}$')
    for aa, enc, name in zip(a_accs, ep_ncs, names):
        ax2.annotate(f'{name}\n{enc:.4f}',
                     xy=(aa, enc),
                     xytext=(8, 8), textcoords='offset points',
                     fontsize=8, color='#333')
    ax2.set_xlabel(
        'Acceleration $a_{acc}$ (m/s²)', fontsize=FS_LABEL)
    ax2.set_ylabel('$EP_{no\\_cruise}$ (kWh/km)',
                   fontsize=FS_LABEL)
    ax2.set_title('$EP_{no\\_cruise}$ vs Acceleration',
                  fontsize=FS_TITLE)

    fig.suptitle(
        'Exp C — Driving Style: Effect of Acceleration/'
        'Deceleration on EP (5 stops)',
        fontsize=FS_TITLE + 1)
    fig.tight_layout()
    fig.savefig(FIG_DIR / 'exp_noncruise_c.png',
                dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: exp_noncruise_c.png')

    return dict(results=results)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Exp D：EP_cruise@90 修正验证
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _compute_f_cycle(
    segments: list[dict], ep_cruise_90: float,
    m: float, crr: float, cda: float, rho: float,
    eta_dt: float, eta_regen: float, g: float,
    v_wind: float, T_amb: float,
) -> dict:
    """
    按 Eq.23–25 计算 f_cycle = f_cruise + f_nocruise。
    """
    v_ref = 25.0  # 90 km/h
    F_rr = crr * m * g
    F_aero_ref = 0.5 * rho * cda * (v_ref**2 + v_wind**2 / 2.0)
    F_total_ref = F_rr + F_aero_ref

    # 计算各段的详细结果
    common = dict(m=m, crr=crr, cda=cda, rho=rho, g=g,
                  v_wind=v_wind)
    _eta = eta_bat(T_amb)

    # f_cruise（Eq.24）
    d_total = 0.0
    f_cruise_num = 0.0
    total_E_acc = 0.0
    total_E_regen = 0.0

    for seg in segments:
        if seg['type'] == 'cruise':
            d_total += seg['d']
            F_aero_k = 0.5 * rho * cda * (
                seg['v']**2 + v_wind**2 / 2.0)
            ratio_k = (F_rr + F_aero_k) / F_total_ref
            f_cruise_num += seg['d'] * ratio_k
        elif seg['type'] == 'acc':
            d_seg = (seg['v1']**2 - seg['v0']**2) / (2 * seg['a'])
            d_total += d_seg
            res = _acc_segment_energy(
                seg['v0'], seg['v1'], seg['a'],
                eta_dt=eta_dt, **common)
            total_E_acc += res['E_acc']
        elif seg['type'] == 'dec':
            d_seg = (seg['v0']**2 - seg['v1']**2) / (2 * seg['a'])
            d_total += d_seg
            res = _dec_segment_energy(
                seg['v0'], seg['v1'], seg['a'],
                eta_regen=eta_regen, **common)
            total_E_regen += res['E_regen']

    f_cruise = f_cruise_num / d_total                          # Eq.24

    # f_nocruise（Eq.25）
    EP_nocruise = (total_E_acc - total_E_regen) * _J_TO_KWH / (
        _eta * d_total / 1000.0)
    f_nocruise = EP_nocruise / ep_cruise_90                    # Eq.25

    f_cycle = f_cruise + f_nocruise

    return dict(
        f_cruise=f_cruise, f_nocruise=f_nocruise,
        f_cycle=f_cycle, d_total=d_total,
        EP_nocruise=EP_nocruise,
    )


def run_exp_d() -> dict:
    """
    对 Exp B 的混合速度行程，计算 f_cycle 并验证
    EP_cruise@90 修正后是否接近纯巡航 baseline。
    """
    print('\n=== Exp D: EP_cruise@90 修正验证 ===')
    p = BASELINE.copy()

    # 纯 90 km/h baseline
    baseline = compute_ep(m=p['m'], n_stop=0)
    ep_baseline = baseline['EP']  # = EP_cruise@90 for baseline

    # 混合工况
    segs = _build_mixed_speed_segments()
    res = compute_ep_segmented(segs, m=p['m'])
    ep_total = res['EP_total']

    # 计算 f_cycle
    fc = _compute_f_cycle(
        segs, ep_baseline,
        m=p['m'], crr=p['crr'], cda=p['cda'], rho=p['rho'],
        eta_dt=p['eta_dt'], eta_regen=p['eta_regen'],
        g=p['g'], v_wind=0.0, T_amb=20.0)

    # 反向修正（Eq.26）
    ep_corrected = ep_total / fc['f_cycle']

    print(f'  EP_total (mixed)     = {ep_total:.6f} kWh/km')
    print(f'  f_cruise             = {fc["f_cruise"]:.6f}')
    print(f'  f_nocruise           = {fc["f_nocruise"]:.6f}')
    print(f'  f_cycle              = {fc["f_cycle"]:.6f}')
    print(f'  EP_cruise@90 修正后  = {ep_corrected:.6f} kWh/km')
    print(f'  纯巡航 baseline      = {ep_baseline:.6f} kWh/km')
    corr_err = abs(ep_corrected - ep_baseline) / ep_baseline * 100
    print(f'  修正误差             = {corr_err:.6f}%')

    # ── 也对 Exp A 的标准启停做修正验证 ──
    segs_a = _build_stop_start_segments(5)
    res_a = compute_ep_segmented(segs_a, m=p['m'])
    fc_a = _compute_f_cycle(
        segs_a, ep_baseline,
        m=p['m'], crr=p['crr'], cda=p['cda'], rho=p['rho'],
        eta_dt=p['eta_dt'], eta_regen=p['eta_regen'],
        g=p['g'], v_wind=0.0, T_amb=20.0)
    ep_corrected_a = res_a['EP_total'] / fc_a['f_cycle']
    corr_err_a = abs(
        ep_corrected_a - ep_baseline) / ep_baseline * 100
    print(f'\n  --- 启停工况（n=5）修正验证 ---')
    print(f'  EP_total (5 stops)   = {res_a["EP_total"]:.6f}')
    print(f'  f_cycle              = {fc_a["f_cycle"]:.6f}')
    print(f'  EP_cruise@90 修正后  = {ep_corrected_a:.6f}')
    print(f'  修正误差             = {corr_err_a:.6f}%')

    # ── 绘图 ──────────────────────────────────────────────────
    apply_style()
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(FIG_W * 1.3, FIG_H * 0.85), dpi=DPI)

    # Left: EP comparison
    labels = ['$EP_{total}$\n(mixed)',
              '$EP_{cruise@90}$\n(corrected)',
              '$EP_{baseline}$\n(pure 90)']
    vals = [ep_total, ep_corrected, ep_baseline]
    colors = ['#FF9800', '#2196F3', '#4CAF50']
    bars = ax1.bar(labels, vals, color=colors, width=0.5,
                   edgecolor='#333', linewidth=0.8)
    for bar, v in zip(bars, vals):
        ax1.text(bar.get_x() + bar.get_width() / 2,
                 bar.get_height(),
                 f'{v:.4f}', ha='center', va='bottom',
                 fontsize=FS_TICK, fontweight='bold')
    ax1.set_ylabel('EP (kWh/km)', fontsize=FS_LABEL)
    ax1.set_title('Mixed Speed Profile Correction',
                  fontsize=FS_TITLE)
    ax1.set_ylim(0, max(vals) * 1.15)
    ax1.text(0.5, 0.05,
             f'Correction error: {corr_err:.4f}%',
             transform=ax1.transAxes, ha='center',
             fontsize=10, color='#555', style='italic')

    # Right: f_cycle decomposition
    cats = ['$f_{cruise}$\n(Eq.24)',
            '$f_{no\\_cruise}$\n(Eq.25)',
            '$f_{cycle}$\n(Eq.23)']
    fvals = [fc['f_cruise'], fc['f_nocruise'], fc['f_cycle']]
    fcolors = ['#4CAF50', '#FF9800', '#2196F3']
    bars2 = ax2.bar(cats, fvals, color=fcolors, width=0.5,
                    edgecolor='#333', linewidth=0.8)
    for bar, v in zip(bars2, fvals):
        ypos = bar.get_height() if v >= 0 else 0
        ax2.text(bar.get_x() + bar.get_width() / 2, ypos,
                 f'{v:.4f}', ha='center',
                 va='bottom' if v >= 0 else 'top',
                 fontsize=FS_TICK, fontweight='bold')
    ax2.set_ylabel('Factor value', fontsize=FS_LABEL)
    ax2.set_title('Cycle Correction Factors (Mixed Trip)',
                  fontsize=FS_TITLE)
    ax2.axhline(1.0, color='grey', linestyle=':', linewidth=0.8)
    ax2.axhline(0, color='black', linewidth=0.5)

    fig.suptitle(
        'Exp D — $EP_{cruise@90}$ Correction Verification '
        '(Section 1.2.4)',
        fontsize=FS_TITLE + 1)
    fig.tight_layout()
    fig.savefig(FIG_DIR / 'exp_noncruise_d.png',
                dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: exp_noncruise_d.png')

    return dict(
        ep_total_mixed=ep_total,
        ep_corrected=ep_corrected,
        ep_baseline=ep_baseline,
        f_cruise=fc['f_cruise'],
        f_nocruise=fc['f_nocruise'],
        f_cycle=fc['f_cycle'],
        correction_error_pct=corr_err,
        # 启停修正
        ep_total_stops=res_a['EP_total'],
        ep_corrected_stops=ep_corrected_a,
        f_cycle_stops=fc_a['f_cycle'],
        correction_error_stops_pct=corr_err_a,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Section 2.3.1 DC 构造器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _kmh2ms(v: float) -> float:
    return v / 3.6


# 加速类型（比例 2:1:1:1）
_ACC_TYPES = [
    (0.0,  _kmh2ms(90)),   # A1: 0 -> 90 km/h
    (0.0,  _kmh2ms(80)),   # A2: 0 -> 80 km/h
    (_kmh2ms(20), _kmh2ms(90)),  # A3: 20 -> 90 km/h
    (_kmh2ms(20), _kmh2ms(80)),  # A4: 20 -> 80 km/h
]
_ACC_WEIGHTS = [2, 1, 1, 1]  # 比例 2:1:1:1

# 减速类型（与加速对称）
_DEC_TYPES = [
    (_kmh2ms(90), 0.0),    # D1: 90 -> 0 km/h
    (_kmh2ms(80), 0.0),    # D2: 80 -> 0 km/h
    (_kmh2ms(90), _kmh2ms(20)),  # D3: 90 -> 20 km/h
    (_kmh2ms(80), _kmh2ms(20)),  # D4: 80 -> 20 km/h
]
_DEC_WEIGHTS = [2, 1, 1, 1]


def _assign_types(n: int, weights: list[int]) -> list[int]:
    """
    将 n 个事件按 weights 比例分配到各类型。
    返回长度为 n 的类型索引列表。
    """
    total_w = sum(weights)
    counts = [0] * len(weights)
    # 先按比例分配
    remainder = n
    for i, w in enumerate(weights):
        counts[i] = n * w // total_w
        remainder -= counts[i]
    # 剩余按权重从大到小依次分配
    fracs = [(n * w / total_w - n * w // total_w, i)
             for i, w in enumerate(weights)]
    fracs.sort(reverse=True)
    for _, i in fracs[:remainder]:
        counts[i] += 1

    result = []
    for i, c in enumerate(counts):
        result.extend([i] * c)
    return result


def _build_dc_segments(
    n_events: int,
    a_acc: float = BASELINE['a_acc'],
    a_dec: float = BASELINE['a_dec'],
    d_total: float = BASELINE['d_total'],
) -> list[dict]:
    """
    按 Section 2.3.1 构造完整 DC segment 列表。

    Parameters
    ----------
    n_events : int
        加速事件数（= 减速事件数），即 N_a = N_d。
    a_acc : float
        统一加速度 (m/s^2)。
    a_dec : float
        统一减速度 (m/s^2)。
    d_total : float
        总行程 (m)。

    Returns
    -------
    list[dict]
        可直接传给 compute_ep_segmented() 的 segment 列表。
    """
    acc_indices = _assign_types(n_events, _ACC_WEIGHTS)
    dec_indices = _assign_types(n_events, _DEC_WEIGHTS)

    # 构建减速-加速配对（保证速度连续性）
    # 配对规则：dec 终速 = acc 起速
    # D1(90->0) + A1(0->90), D1(90->0) + A1(0->90),
    # D2(80->0) + A2(0->80),
    # D3(90->20) + A3(20->90),
    # D4(80->20) + A4(20->80)
    # 终速=0 的减速配 起速=0 的加速，终速=20 的配起速=20 的
    pairs_0 = []   # 终速/起速 = 0
    pairs_20 = []  # 终速/起速 = 20 km/h

    dec_pool_0 = []
    dec_pool_20 = []
    for di in dec_indices:
        v0, vf = _DEC_TYPES[di]
        if abs(vf) < 0.01:
            dec_pool_0.append(di)
        else:
            dec_pool_20.append(di)

    acc_pool_0 = []
    acc_pool_20 = []
    for ai in acc_indices:
        v0, vf = _ACC_TYPES[ai]
        if abs(v0) < 0.01:
            acc_pool_0.append(ai)
        else:
            acc_pool_20.append(ai)

    # 配对：0-speed
    for di, ai in zip(dec_pool_0, acc_pool_0):
        pairs_0.append((di, ai))
    # 配对：20 km/h
    for di, ai in zip(dec_pool_20, acc_pool_20):
        pairs_20.append((di, ai))

    # 若不平衡则交叉配对（D1+A3 等）
    leftover_dec_0 = dec_pool_0[len(acc_pool_0):]
    leftover_acc_0 = acc_pool_0[len(dec_pool_0):]
    leftover_dec_20 = dec_pool_20[len(acc_pool_20):]
    leftover_acc_20 = acc_pool_20[len(dec_pool_20):]
    # D 终速=0 多余 → 配 A 起速=20 的（中间加一段短巡航 @20km/h）
    # 但为简化，改配对策略：直接 D→A 不论速度，
    # 中间插入过渡巡航段
    extra_pairs = list(zip(leftover_dec_0, leftover_acc_20)) + \
                  list(zip(leftover_dec_20, leftover_acc_0))

    all_pairs = pairs_0 + pairs_20 + extra_pairs

    # 计算加减速段总距离
    d_acc_dec = 0.0
    for di, ai in all_pairs:
        v0d, vfd = _DEC_TYPES[di]
        d_acc_dec += (v0d**2 - vfd**2) / (2.0 * a_dec)
        v0a, vfa = _ACC_TYPES[ai]
        d_acc_dec += (vfa**2 - v0a**2) / (2.0 * a_acc)

    d_cruise_total = d_total - d_acc_dec
    if d_cruise_total < 0:
        raise ValueError(
            f"n_events={n_events} 的加减速段总距离 "
            f"({d_acc_dec/1000:.1f} km) 超过总行程")

    # 巡航距离按 3:1 分配至 90/80 km/h
    d_at_90 = d_cruise_total * 3.0 / 4.0
    d_at_80 = d_cruise_total * 1.0 / 4.0

    # n_events 对 dec-acc → (n_events+1) 个巡航间隔
    n_cruise = n_events + 1
    # 确定各间隔的巡航速度：
    # 前一个 acc 的终速决定后续巡航速度
    # 第一个巡航段的速度由场景决定（初始 90 km/h）
    cruise_v_list = [_kmh2ms(90)]  # 第一段
    for di, ai in all_pairs:
        _, vfa = _ACC_TYPES[ai]
        # acc 结束速度即下一段巡航速度
        # 但如果终速 = 80 km/h，巡航 @80；= 90，巡航 @90
        if abs(vfa - _kmh2ms(90)) < 0.1:
            cruise_v_list.append(_kmh2ms(90))
        else:
            cruise_v_list.append(_kmh2ms(80))

    # 计算 @90 和 @80 的巡航段数量
    n90 = sum(1 for v in cruise_v_list
              if abs(v - _kmh2ms(90)) < 0.1)
    n80 = sum(1 for v in cruise_v_list
              if abs(v - _kmh2ms(80)) < 0.1)

    # 为每段分配距离
    cruise_d_list = []
    for v in cruise_v_list:
        if abs(v - _kmh2ms(90)) < 0.1:
            cruise_d_list.append(d_at_90 / max(n90, 1))
        else:
            cruise_d_list.append(d_at_80 / max(n80, 1))

    # 组装 segment 列表
    segs = []
    for idx in range(n_events):
        # 巡航段
        segs.append({'type': 'cruise',
                     'v': cruise_v_list[idx],
                     'd': cruise_d_list[idx]})
        # 减速段
        di, ai = all_pairs[idx]
        v0d, vfd = _DEC_TYPES[di]
        segs.append({'type': 'dec',
                     'v0': v0d, 'v1': vfd, 'a': a_dec})

        # 若 dec 终速 != acc 起速，插入短巡航过渡
        v0a, vfa = _ACC_TYPES[ai]
        if abs(vfd - v0a) > 0.1:
            # 需要过渡（例如 dec 终速 0 → acc 起速 20）
            # 此情况下插入一段 0 距离巡航（无实际距离）
            pass

        # 加速段
        segs.append({'type': 'acc',
                     'v0': v0a, 'v1': vfa, 'a': a_acc})

    # 最后一段巡航
    segs.append({'type': 'cruise',
                 'v': cruise_v_list[-1],
                 'd': cruise_d_list[-1]})
    return segs


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Section 2.3.2：不同工况下的仿真 EP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_exp_232() -> dict:
    """
    使用 2.3.1 定义的 DC 工况，扫描 N_a = N_d = 5, 10, 20, 30，
    对每个 N_a 计算 EP_total, EP_cruise, EP_nocruise。
    """
    print('\n=== Section 2.3.2: 不同工况下的仿真 EP ===')
    p = BASELINE.copy()
    baseline_ep = compute_ep(m=p['m'], n_stop=0)['EP']

    na_values = [5, 10, 20, 30]
    results = []

    for na in na_values:
        segs = _build_dc_segments(na)
        res = compute_ep_segmented(segs, m=p['m'], eta_regen=0.0)
        delta_pct = (res['EP_total'] - baseline_ep) / baseline_ep * 100
        row = {
            'N_a': na,
            'EP_total': res['EP_total'],
            'EP_cruise': res['EP_cruise'],
            'EP_nocruise': res['EP_nocruise'],
            'E_acc': res['E_acc_total'],
            'E_regen': res['E_regen_total'],
            'E_cruise': res['E_cruise_total'],
            'd_total': res['d_total'],
            'delta_pct': delta_pct,
        }
        results.append(row)
        print(f'  N_a={na:2d}  EP_total={res["EP_total"]:.4f}  '
              f'EP_cruise={res["EP_cruise"]:.4f}  '
              f'EP_nc={res["EP_nocruise"]:.4f}  '
              f'delta={delta_pct:+.2f}%')

    # 保存 CSV
    df = pd.DataFrame(results)
    df.to_csv(TABLE_DIR / 'exp_noncruise_232.csv', index=False)

    # ── 绘图 ──────────────────────────────────────────────────
    apply_style()
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(FIG_W * 1.3, FIG_H * 0.85), dpi=DPI)

    na_arr = [r['N_a'] for r in results]
    ep_c = [r['EP_cruise'] for r in results]
    ep_nc = [r['EP_nocruise'] for r in results]
    ep_t = [r['EP_total'] for r in results]

    # Left: EP_total 折线 + baseline
    ax1.plot(na_arr, ep_t, 'o-', color='#1565C0', linewidth=2.2,
             markersize=8, label='$EP_{total}$ (Eq.21)')
    ax1.axhline(baseline_ep, color='#4CAF50', linestyle='--',
                linewidth=1.5, label=f'Baseline = {baseline_ep:.4f}')
    for na, ept in zip(na_arr, ep_t):
        ax1.annotate(f'{ept:.4f}', xy=(na, ept),
                     xytext=(0, 10), textcoords='offset points',
                     ha='center', fontsize=FS_TICK - 1,
                     fontweight='bold')
    ax1.set_xlabel('$N_a = N_d$ (number of events)',
                   fontsize=FS_LABEL)
    ax1.set_ylabel('EP (kWh/km)', fontsize=FS_LABEL)
    ax1.set_title('$EP_{total}$ vs Number of Events',
                  fontsize=FS_TITLE)
    ax1.legend(fontsize=FS_LEGEND, loc='upper left')
    ax1.set_xticks(na_arr)
    ax1.grid(alpha=GRID_ALPHA)

    # Right: 堆叠柱状图 EP_cruise + EP_nocruise
    x = np.arange(len(na_arr))
    w = 0.5
    bars1 = ax2.bar(x, ep_c, w, label='$EP_{cruise}$ (Eq.19)',
                    color='#2196F3', edgecolor='#333',
                    linewidth=0.6)
    bars2 = ax2.bar(x, ep_nc, w, bottom=ep_c,
                    label='$EP_{no\\_cruise}$ (Eq.20)',
                    color='#FF5722', edgecolor='#333',
                    linewidth=0.6)
    for i, (b1, b2, ept) in enumerate(zip(bars1, bars2, ep_t)):
        y_top = b2.get_y() + b2.get_height()
        ax2.text(b2.get_x() + b2.get_width() / 2, y_top,
                 f'{ept:.4f}', ha='center', va='bottom',
                 fontsize=FS_TICK - 2, fontweight='bold')
    ax2.set_xticks(x)
    ax2.set_xticklabels([f'$N_a$={n}' for n in na_arr],
                        fontsize=FS_TICK)
    ax2.set_ylabel('EP (kWh/km)', fontsize=FS_LABEL)
    ax2.set_title('EP Decomposition by $N_a$',
                  fontsize=FS_TITLE)
    ax2.legend(fontsize=FS_LEGEND, loc='upper left')
    ax2.grid(alpha=GRID_ALPHA)

    fig.suptitle(
        'Section 2.3.2 — EP vs Driving Cycle Events '
        '(DC from Section 2.3.1)',
        fontsize=FS_TITLE + 1)
    fig.tight_layout()
    fig.savefig(FIG_DIR / 'exp_noncruise_232.png',
                dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: exp_noncruise_232.png')

    return dict(results=results, baseline_ep=baseline_ep)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Section 2.3.3：不同驾驶行为下的仿真 EP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_exp_233() -> dict:
    """
    固定 N_a = N_d = 10，使用 2.3.1 的 DC 工况，
    三种驾驶风格：Conservative / Standard / Aggressive。
    """
    print('\n=== Section 2.3.3: 不同驾驶行为下的仿真 EP ===')
    p = BASELINE.copy()
    baseline_ep = compute_ep(m=p['m'], n_stop=0)['EP']
    n_events = 10

    styles = [
        ('Conservative', 0.30, 0.50),
        ('Standard',     0.58, 0.83),
        ('Aggressive',   1.50, 2.00),
    ]

    results = []
    for name, a_acc, a_dec in styles:
        segs = _build_dc_segments(n_events, a_acc=a_acc, a_dec=a_dec)
        res = compute_ep_segmented(
            segs, m=p['m'], eta_dt=p['eta_dt'],
            eta_regen=0.0)
        delta_pct = (res['EP_total'] - baseline_ep) / baseline_ep * 100
        row = {
            'style': name,
            'a_acc': a_acc, 'a_dec': a_dec,
            'EP_total': res['EP_total'],
            'EP_cruise': res['EP_cruise'],
            'EP_nocruise': res['EP_nocruise'],
            'E_acc': res['E_acc_total'],
            'E_regen': res['E_regen_total'],
            'delta_pct': delta_pct,
        }
        results.append(row)
        print(f'  {name:14s}  a_acc={a_acc:.2f}  a_dec={a_dec:.2f}  '
              f'EP={res["EP_total"]:.4f}  '
              f'EP_nc={res["EP_nocruise"]:.4f}  '
              f'delta={delta_pct:+.2f}%')

    # 保存 CSV
    df = pd.DataFrame(results)
    df.to_csv(TABLE_DIR / 'exp_noncruise_233.csv', index=False)

    # ── 绘图：分组柱状图 ─────────────────────────────────────
    apply_style()
    fig, ax = plt.subplots(figsize=(FIG_W * 0.9, FIG_H), dpi=DPI)

    names = [r['style'] for r in results]
    ep_c = [r['EP_cruise'] for r in results]
    ep_nc = [r['EP_nocruise'] for r in results]
    ep_t = [r['EP_total'] for r in results]

    x = np.arange(len(names))
    w = 0.22

    bars_nc = ax.bar(x - w, ep_nc, w,
                     label='$EP_{no\\_cruise}$ (Eq.20)',
                     color='#FF9800', edgecolor='#333',
                     linewidth=0.6)
    bars_c = ax.bar(x, ep_c, w,
                    label='$EP_{cruise}$ (Eq.19)',
                    color='#4CAF50', edgecolor='#333',
                    linewidth=0.6)
    bars_t = ax.bar(x + w, ep_t, w,
                    label='$EP_{total}$ (Eq.21)',
                    color='#2196F3', edgecolor='#333',
                    linewidth=0.6)

    # 标注数值（水平放置）
    for bars in [bars_nc, bars_c, bars_t]:
        for bar in bars:
            h = bar.get_height()
            y_pos = h if h >= 0 else 0
            va = 'bottom' if h >= 0 else 'top'
            ax.text(bar.get_x() + bar.get_width() / 2,
                    y_pos, f'{h:.4f}', ha='center', va=va,
                    fontsize=FS_TICK - 3, fontweight='bold')

    # baseline 参考线
    ax.axhline(baseline_ep, color='grey', linestyle='--',
               linewidth=1.2,
               label=f'Baseline = {baseline_ep:.4f}')

    ax.set_xticks(x)
    ax.set_xticklabels(
        [f'{n}\n($a_{{acc}}$={r["a_acc"]}, '
         f'$a_{{dec}}$={r["a_dec"]})'
         for n, r in zip(names, results)],
        fontsize=FS_TICK - 1)
    ax.set_ylabel('EP (kWh/km)', fontsize=FS_LABEL)
    ax.set_title(
        'Section 2.3.3 — Driving Style Comparison '
        '($N_a = N_d = 10$, DC from 2.3.1)',
        fontsize=FS_TITLE)
    ax.legend(fontsize=FS_LEGEND, loc='upper left')
    ax.grid(alpha=GRID_ALPHA, axis='y')

    fig.tight_layout()
    fig.savefig(FIG_DIR / 'exp_noncruise_233.png',
                dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: exp_noncruise_233.png')

    return dict(results=results, baseline_ep=baseline_ep)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Section 2.3.4：再生制动效率的影响
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_exp_234_regen() -> dict:
    """
    固定 N_a = N_d = 10（Standard 工况），扫描 eta_regen，
    观察再生制动效率对 EP_total 和 EP_nocruise 的影响。
    """
    print('\n=== Section 2.3.4: 再生制动效率的影响 ===')
    p = BASELINE.copy()
    baseline_ep = compute_ep(m=p['m'], n_stop=0)['EP']
    n_events = 10

    eta_values = [0.0, 0.3, 0.5, 0.7, 0.9]
    results = []

    for eta_r in eta_values:
        segs = _build_dc_segments(n_events)
        res = compute_ep_segmented(
            segs, m=p['m'], eta_dt=p['eta_dt'],
            eta_regen=eta_r)
        delta_pct = (
            (res['EP_total'] - baseline_ep) / baseline_ep * 100)
        row = {
            'eta_regen': eta_r,
            'EP_total': res['EP_total'],
            'EP_cruise': res['EP_cruise'],
            'EP_nocruise': res['EP_nocruise'],
            'E_acc': res['E_acc_total'],
            'E_regen': res['E_regen_total'],
            'delta_pct': delta_pct,
        }
        results.append(row)
        print(f'  eta_regen={eta_r:.1f}  '
              f'EP_total={res["EP_total"]:.4f}  '
              f'EP_cruise={res["EP_cruise"]:.4f}  '
              f'EP_nc={res["EP_nocruise"]:.4f}  '
              f'E_regen={res["E_regen_total"]:.2f}  '
              f'delta={delta_pct:+.2f}%')

    # 保存 CSV
    df = pd.DataFrame(results)
    df.to_csv(TABLE_DIR / 'exp_noncruise_234_regen.csv',
              index=False)

    # ── 绘图 ──────────────────────────────────────────────────
    apply_style()
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(FIG_W * 1.3, FIG_H * 0.85), dpi=DPI)

    etas = [r['eta_regen'] for r in results]
    ep_t = [r['EP_total'] for r in results]
    ep_c = [r['EP_cruise'] for r in results]
    ep_nc = [r['EP_nocruise'] for r in results]

    # Left: EP_total vs eta_regen
    ax1.plot(etas, ep_t, 'o-', color='#1565C0', linewidth=2.2,
             markersize=8, label='$EP_{total}$ (Eq.21)')
    ax1.axhline(baseline_ep, color='#4CAF50', linestyle='--',
                linewidth=1.5,
                label=f'Baseline = {baseline_ep:.4f}')
    for eta_r, ept in zip(etas, ep_t):
        ax1.annotate(f'{ept:.4f}', xy=(eta_r, ept),
                     xytext=(0, 10), textcoords='offset points',
                     ha='center', fontsize=FS_TICK - 1,
                     fontweight='bold')
    ax1.set_xlabel(r'$\eta_{regen}$', fontsize=FS_LABEL)
    ax1.set_ylabel('EP (kWh/km)', fontsize=FS_LABEL)
    ax1.set_title('$EP_{total}$ vs $\\eta_{regen}$',
                  fontsize=FS_TITLE)
    ax1.legend(fontsize=FS_LEGEND, loc='upper right')
    ax1.set_xticks(etas)
    ax1.grid(alpha=GRID_ALPHA)

    # Right: 堆叠柱状图 EP_nocruise + EP_cruise
    x = np.arange(len(etas))
    w = 0.5
    bars1 = ax2.bar(x, ep_nc, w,
                    label='$EP_{no\\_cruise}$ (Eq.20)',
                    color='#FF5722', edgecolor='#333',
                    linewidth=0.6)
    bars2 = ax2.bar(x, ep_c, w, bottom=ep_nc,
                    label='$EP_{cruise}$ (Eq.19)',
                    color='#2196F3', edgecolor='#333',
                    linewidth=0.6)
    for i, (b1, b2, ept) in enumerate(zip(bars1, bars2, ep_t)):
        y_top = b2.get_y() + b2.get_height()
        ax2.text(b2.get_x() + b2.get_width() / 2, y_top,
                 f'{ept:.4f}', ha='center', va='bottom',
                 fontsize=FS_TICK - 2, fontweight='bold')
    ax2.axhline(baseline_ep, color='#4CAF50', linestyle='--',
                linewidth=1.2, alpha=0.7,
                label=f'Baseline = {baseline_ep:.4f}')
    ax2.set_xticks(x)
    ax2.set_xticklabels(
        [f'$\\eta_{{regen}}$={e:.1f}' for e in etas],
        fontsize=FS_TICK - 1)
    ax2.set_ylabel('EP (kWh/km)', fontsize=FS_LABEL)
    ax2.set_title('EP Decomposition by $\\eta_{regen}$',
                  fontsize=FS_TITLE)
    ax2.legend(fontsize=FS_LEGEND, loc='upper right')
    ax2.grid(alpha=GRID_ALPHA)

    fig.suptitle(
        'Section 2.3.4 — Effect of Regenerative Braking '
        'Efficiency ($N_a = N_d = 10$, Standard)',
        fontsize=FS_TITLE + 1)
    fig.tight_layout()
    fig.savefig(FIG_DIR / 'exp_noncruise_234_regen.png',
                dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: exp_noncruise_234_regen.png')

    return dict(results=results, baseline_ep=baseline_ep)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Section 2.3.5：Driving cycle 修正验证
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_exp_235() -> dict:
    """
    取 2.3.2 中 N_a = 10 的工况（eta_regen=0），按 Eq.22-26 计算
    f_cruise, f_nocruise, f_cycle，验证修正后 EP_cruise@90
    是否恢���为 baseline EP。
    """
    print('\n=== Section 2.3.5: Driving cycle 修正验证 ===')
    p = BASELINE.copy()
    baseline = compute_ep(m=p['m'], n_stop=0)
    ep_baseline = baseline['EP']

    # N_a = 10 的 DC 工况（eta_regen=0，与 2.3.2/2.3.3 一致）
    segs = _build_dc_segments(10)
    res = compute_ep_segmented(segs, m=p['m'], eta_regen=0.0)
    ep_total = res['EP_total']

    # 计算 f_cycle（Eq.23-25）
    fc = _compute_f_cycle(
        segs, ep_baseline,
        m=p['m'], crr=p['crr'], cda=p['cda'], rho=p['rho'],
        eta_dt=p['eta_dt'], eta_regen=0.0,
        g=p['g'], v_wind=0.0, T_amb=20.0)

    # 反向修正（Eq.26）
    ep_corrected = ep_total / fc['f_cycle']
    corr_err = abs(
        ep_corrected - ep_baseline) / ep_baseline * 100

    print(f'  EP_total (N_a=10 DC)   = {ep_total:.6f} kWh/km')
    print(f'  f_cruise               = {fc["f_cruise"]:.6f}')
    print(f'  f_nocruise             = {fc["f_nocruise"]:.6f}')
    print(f'  f_cycle                = {fc["f_cycle"]:.6f}')
    print(f'  EP_cruise@90 (Eq.26)   = {ep_corrected:.6f} kWh/km')
    print(f'  Baseline EP            = {ep_baseline:.6f} kWh/km')
    print(f'  Correction error       = {corr_err:.6f}%')

    # ── 绘图 ──────────────────────────────────────────────────
    apply_style()
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(FIG_W * 1.3, FIG_H * 0.85), dpi=DPI)

    # Left: EP comparison
    labels = ['$EP_{total}$\n(DC, $N_a$=10)',
              '$EP_{cruise@90}$\n(Eq.26)',
              '$EP_{baseline}$\n(pure 90)']
    vals = [ep_total, ep_corrected, ep_baseline]
    colors = ['#FF9800', '#2196F3', '#4CAF50']
    bars = ax1.bar(labels, vals, color=colors, width=0.5,
                   edgecolor='#333', linewidth=0.8)
    for bar, v in zip(bars, vals):
        ax1.text(bar.get_x() + bar.get_width() / 2,
                 bar.get_height(),
                 f'{v:.4f}', ha='center', va='bottom',
                 fontsize=FS_TICK, fontweight='bold')
    ax1.set_ylabel('EP (kWh/km)', fontsize=FS_LABEL)
    ax1.set_title('Driving Cycle Correction ($N_a$=10)',
                  fontsize=FS_TITLE)
    ax1.set_ylim(0, max(vals) * 1.15)
    ax1.text(0.5, 0.05,
             f'Correction error: {corr_err:.4f}%',
             transform=ax1.transAxes, ha='center',
             fontsize=10, color='#555', style='italic')

    # Right: f_cycle decomposition
    cats = ['$f_{cruise}$\n(Eq.24)',
            '$f_{no\\_cruise}$\n(Eq.25)',
            '$f_{cycle}$\n(Eq.23)']
    fvals = [fc['f_cruise'], fc['f_nocruise'], fc['f_cycle']]
    fcolors = ['#4CAF50', '#FF9800', '#2196F3']
    bars2 = ax2.bar(cats, fvals, color=fcolors, width=0.5,
                    edgecolor='#333', linewidth=0.8)
    for bar, v in zip(bars2, fvals):
        ypos = bar.get_height() if v >= 0 else 0
        ax2.text(bar.get_x() + bar.get_width() / 2, ypos,
                 f'{v:.4f}', ha='center',
                 va='bottom' if v >= 0 else 'top',
                 fontsize=FS_TICK, fontweight='bold')
    ax2.set_ylabel('Factor value', fontsize=FS_LABEL)
    ax2.set_title('Cycle Correction Factors',
                  fontsize=FS_TITLE)
    ax2.axhline(1.0, color='grey', linestyle=':', linewidth=0.8)
    ax2.axhline(0, color='black', linewidth=0.5)

    fig.suptitle(
        'Section 2.3.5 — $EP_{cruise@90}$ Correction '
        'Verification (DC from 2.3.1, $N_a$=10)',
        fontsize=FS_TITLE + 1)
    fig.tight_layout()
    fig.savefig(FIG_DIR / 'exp_noncruise_235.png',
                dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: exp_noncruise_235.png')

    return dict(
        ep_total=ep_total,
        ep_corrected=ep_corrected,
        ep_baseline=ep_baseline,
        f_cruise=fc['f_cruise'],
        f_nocruise=fc['f_nocruise'],
        f_cycle=fc['f_cycle'],
        correction_error_pct=corr_err,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  主入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run() -> dict:
    """��行所有非定速巡航实验（Exp A–D + Section 2.3.2–2.3.5）。"""
    res_a = run_exp_a()
    res_b = run_exp_b()
    res_c = run_exp_c()
    res_d = run_exp_d()
    res_232 = run_exp_232()
    res_233 = run_exp_233()
    res_234 = run_exp_234_regen()
    res_235 = run_exp_235()
    return dict(exp_a=res_a, exp_b=res_b,
                exp_c=res_c, exp_d=res_d,
                exp_232=res_232, exp_233=res_233,
                exp_234=res_234, exp_235=res_235)


if __name__ == '__main__':
    run()
