"""生成 N_a=N_d=5 时的非定速巡航 speed profile 示意图。
巡航段距离按 3:1 比例分配至 90/80 km/h。"""
import sys, pathlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'simulation'))
from models.vehicle_physics import (
    apply_style, FIG_W, FIG_H, DPI,
    FS_LABEL, FS_TITLE, FS_TICK,
)

FIG_DIR = ROOT / 'simulation' / 'results' / 'figures'

A_ACC = 0.58  # m/s²
A_DEC = 0.83  # m/s²
D_TOTAL = 100_000  # m

def kmh2ms(v):
    return v / 3.6

def d_seg(v0_kmh, vf_kmh, a):
    return abs(kmh2ms(vf_kmh)**2 - kmh2ms(v0_kmh)**2) / (2 * a)


def main():
    # ── 定义 5 对 dec-acc 事件（保证速度连续）──
    # 配对方式: dec 终速 = acc 起速
    # D1(90→0)+A1(0→90), D1(90→0)+A1(0→90),
    # D3(90→20)+A3(20→90),
    # D1(90→0)+A2(0→80),  [用 D1 代替 D2 避免需要先到 80]
    # D4(80→20)+A4(20→80)
    pairs = [
        (90, 0, 0, 90),     # D1 + A1
        (90, 0, 0, 90),     # D1 + A1
        (90, 20, 20, 90),   # D3 + A3
        (90, 0, 0, 80),     # D1 + A2 (减速到 0, 加速到 80)
        (80, 20, 20, 80),   # D4 + A4
    ]

    # 计算加减速段总距离
    d_acc_dec = 0
    for dv0, dvf, av0, avf in pairs:
        d_acc_dec += d_seg(dv0, dvf, A_DEC)
        d_acc_dec += d_seg(av0, avf, A_ACC)

    d_cruise_total = D_TOTAL - d_acc_dec

    # 巡航距离按 3:1 分配 (90/80 km/h)
    d_at_90 = d_cruise_total * 3 / 4
    d_at_80 = d_cruise_total * 1 / 4

    # 分配巡航段：
    # 5 对 dec-acc → 6 个巡航段间隔
    # 前 3 个间隔 @90, 第 4 个 @90, 第 5 个 @80, 第 6 个 @80
    # 按 pair 后的速度决定巡航速度:
    # pair 1 结束 @90 → cruise@90
    # pair 2 结束 @90 → cruise@90
    # pair 3 结束 @90 → cruise@90
    # pair 4 结束 @80 → cruise@80
    # pair 5 结束 @80 → cruise@80
    cruise_speeds = [90, 90, 90, 90, 80, 80]  # 6 段
    cruise_dists = []
    n90 = sum(1 for v in cruise_speeds if v == 90)
    n80 = sum(1 for v in cruise_speeds if v == 80)
    for v in cruise_speeds:
        if v == 90:
            cruise_dists.append(d_at_90 / n90)
        else:
            cruise_dists.append(d_at_80 / n80)

    # ── 构建连续 speed profile ──
    dist = [0.0]
    speed = [cruise_speeds[0]]

    # 交替: cruise → dec → acc → cruise → ...
    for idx in range(5):
        # 巡航段
        dist.append(dist[-1] + cruise_dists[idx])
        speed.append(cruise_speeds[idx])

        # 减速段
        dv0, dvf, av0, avf = pairs[idx]
        d_dec = d_seg(dv0, dvf, A_DEC)
        dist.append(dist[-1] + d_dec)
        speed.append(dvf)

        # 加速段
        d_acc = d_seg(av0, avf, A_ACC)
        dist.append(dist[-1] + d_acc)
        speed.append(avf)

    # 最后一段巡航
    dist.append(dist[-1] + cruise_dists[5])
    speed.append(cruise_speeds[5])

    dist_km = np.array(dist) / 1000
    speed_kmh = np.array(speed)

    # ── 绘图 ──
    apply_style()
    fig, ax = plt.subplots(
        figsize=(FIG_W * 1.1, FIG_H * 0.6), dpi=DPI)

    ax.plot(dist_km, speed_kmh, color='#1565C0', linewidth=2.0)

    ax.axhline(y=90, color='grey', linestyle=':', lw=0.8, alpha=0.4)
    ax.axhline(y=80, color='grey', linestyle=':', lw=0.8, alpha=0.4)
    ax.text(dist_km[-1] * 0.99, 91, '90 km/h', ha='right',
            va='bottom', fontsize=FS_TICK - 1, color='grey')
    ax.text(dist_km[-1] * 0.99, 81, '80 km/h', ha='right',
            va='bottom', fontsize=FS_TICK - 1, color='grey')

    ax.set_xlabel('Distance (km)', fontsize=FS_LABEL)
    ax.set_ylabel('Speed (km/h)', fontsize=FS_LABEL)
    ax.set_title(
        'Speed Profile ($N_a = N_d = 5$, '
        'cruise 90:80 = 3:1)',
        fontsize=FS_TITLE)
    ax.set_xlim(0, dist_km[-1])
    ax.set_ylim(-3, 100)
    ax.grid(alpha=0.3)

    fig.tight_layout()
    out = FIG_DIR / 'exp_noncruise_profile_n5.png'
    fig.savefig(out, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'Saved: {out}')
    print(f'Total: {dist_km[-1]:.1f} km, '
          f'd_cruise@90={d_at_90/1000:.1f} km, '
          f'd_cruise@80={d_at_80/1000:.1f} km, '
          f'ratio={d_at_90/d_at_80:.1f}')


if __name__ == '__main__':
    main()
