"""
共享物理模型 — 标准行驶剖面能耗计算
基准参数来源：[1] J. Hu, IEEE ITSC 2026, Table I & III（实车标定，Volvo 同级别 HGV）
"""
from __future__ import annotations
import sys
from pathlib import Path

# Bootstrap the versioned toolkit (src-layout) onto sys.path so the canonical
# eta_bat re-export below resolves regardless of the caller's working directory.
_SRC = Path(__file__).resolve().parents[3] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from jolt_toolkit.analysis.physics import eta_bat  # noqa: F401 — canonical home since toolkit v2.2.4 (sub-project independence convention)

# ── 基准参数 ──────────────────────────────────────────────────────────────────
BASELINE: dict = dict(
    m       = 42_000.0,   # kg  — 满载 GVW
    v_c     = 25.0,       # m/s — 巡航速度（90 km/h）
    a_acc   = 0.58,       # m/s² — 加速度（实测驾驶员行为）
    a_dec   = 0.83,       # m/s² — 减速度（实测驾驶员行为）
    crr     = 0.00465,    # —   — 滚阻系数（干燥沥青，实车标定）
    cda     = 6.16,       # m²  — 风阻面积积（实车标定）
    rho     = 1.225,      # kg/m³ — 空气密度（海平面 20°C）
    eta_dt  = 0.90,       # —   — 驱动系效率（电机 0.95 × 传动链 0.95）
    eta_regen = 0.90,     # —   — 再生制动效率
    v_wind  = 0.0,        # m/s — 风速（0 = 无风）
    delta_h = 0.0,        # m   — 净海拔变化
    n_stop  = 0,          # —   — 中途停车次数
    T_amb   = 20.0,       # °C  — 环境温度（基准）
    d_total = 100_000.0,  # m   — 总路程（100 km）
    g       = 9.81,       # m/s²
)

_J_TO_KWH = 1.0 / 3_600_000.0  # J → kWh 转换系数


# ── 电池效率模型（Arrhenius）─────────────────────────────────────────────────
# eta_bat was promoted into the versioned toolkit on 2026-06-11 (sub-project
# independence convention); its canonical implementation now lives in
# jolt_toolkit.analysis.physics and is re-exported via the import above for
# backward compatibility. compute_ep() below still calls eta_bat(T_amb) directly.


# ── 主能耗计算 ────────────────────────────────────────────────────────────────
def compute_ep(
    m: float,
    v_c: float     = BASELINE['v_c'],
    a_acc: float   = BASELINE['a_acc'],
    a_dec: float   = BASELINE['a_dec'],
    crr: float     = BASELINE['crr'],
    cda: float     = BASELINE['cda'],
    rho: float     = BASELINE['rho'],
    eta_dt: float  = BASELINE['eta_dt'],
    eta_regen: float = BASELINE['eta_regen'],
    v_wind: float  = 0.0,
    delta_h: float = 0.0,
    n_stop: int    = 0,
    T_amb: float   = 20.0,
    d_total: float = BASELINE['d_total'],
    g: float       = BASELINE['g'],
) -> dict:
    """
    计算标准行驶剖面的 Energy Performance (EP, kWh/km)。

    行驶剖面（纯定速巡航基线）：
      基线 — 全程以 v_c 匀速巡航（起点 v_c，终点 v_c），无加减速阶段
      启停 — 每次中途停车为 v_c → 0 → v_c 循环（减速 + 加速各占 d_dec + d_acc 距离）
      n_stop 次启停事件均匀分布在 d_total 总行程中

    风向处理：随机均匀风向积分后等效风阻
      <F_aero> = 0.5 * rho * cda * (v² + V_wind² / 2)

    Returns
    -------
    dict with keys: EP, E_bat, E_mech, E_acc, E_cruise, E_regen,
                    E_stop_net, E_elev, eta_bat_val,
                    d_acc, d_dec, d_cruise, F_rr, F_aero_cruise
    """
    # ── 行程几何 ────────────────────────────────────────────────────────────
    d_acc   = v_c**2 / (2.0 * a_acc)          # 单次加速段 (m)
    d_dec   = v_c**2 / (2.0 * a_dec)          # 单次减速段 (m)
    # 基线为纯定速巡航（全程 v_c）；每次启停事件占用 (d_dec + d_acc) 距离
    d_cruise = d_total - n_stop * (d_acc + d_dec)
    if d_cruise < 0:
        raise ValueError(
            f"n_stop={n_stop} 过多，巡航距离为负 ({d_cruise:.0f} m)。"
            f"建议 n_stop ≤ {int(d_total / (d_acc + d_dec))}。"
        )

    # ── 阻力 ─────────────────────────────────────────────────────────────────
    F_rr = crr * m * g                               # 滚阻 (N)
    # 巡航段：随机风向积分等效风阻
    F_aero_cruise = 0.5 * rho * cda * (v_c**2 + v_wind**2 / 2.0)
    # 加减速段：以平均速度 v_c/2 处理
    F_aero_avg    = 0.5 * rho * cda * ((v_c / 2.0)**2 + v_wind**2 / 2.0)

    # ── 能量计算（Joules）───────────────────────────────────────────────────
    KE = 0.5 * m * v_c**2                           # 动能 (J)

    # 单次加速耗能（电池侧）
    E_acc_one = (KE + (F_rr + F_aero_avg) * d_acc) / eta_dt

    # 单次减速再生回收（回流电池）
    regen_base = KE - (F_rr + F_aero_avg) * d_dec
    E_regen_one = eta_regen * max(0.0, regen_base)

    # 启停净消耗（n_stop 次，每次 v_c→0→v_c）
    E_stop_net = (E_acc_one - E_regen_one) * n_stop

    # 巡航耗能
    E_cruise = (F_rr + F_aero_cruise) * d_cruise / eta_dt

    # 海拔势能贡献（净海拔差 delta_h）
    # 不考虑再生制动：上坡/下坡均通过驱动系统（效率 eta_dt），无独立再生路径
    # 上坡：电机额外做功 / eta_dt；下坡：重力助力减少电机耗功，同样经过 eta_dt
    E_elev = m * g * delta_h / eta_dt            # 对称；delta_h < 0 时节省能量 (J)

    # 机械能合计（基线 = 纯巡航，启停事件叠加）
    E_mech = E_stop_net + E_cruise + E_elev

    # 电池效率修正（T_amb 影响放电损耗）
    _eta_bat = eta_bat(T_amb)
    E_bat = E_mech / _eta_bat                    # 电池实际输出能量 (J)

    # EP (kWh/km)
    EP = (E_bat * _J_TO_KWH) / (d_total / 1000.0)

    return dict(
        EP           = EP,
        E_bat        = E_bat * _J_TO_KWH,
        E_mech       = E_mech * _J_TO_KWH,
        E_acc        = E_acc_one * _J_TO_KWH,
        E_cruise     = E_cruise * _J_TO_KWH,
        E_regen      = E_regen_one * _J_TO_KWH,
        E_stop_net   = E_stop_net * _J_TO_KWH,
        E_elev       = E_elev * _J_TO_KWH,
        eta_bat_val  = _eta_bat,
        d_acc        = d_acc,
        d_dec        = d_dec,
        d_cruise     = d_cruise,
        F_rr         = F_rr,
        F_aero_cruise= F_aero_cruise,
    )


# ── 绘图样式（与 figure-plotter skill 保持一致）────────────────────────────
# Style constants — must match .claude/skills/figure-plotter/SKILL.md
FIG_W, FIG_H = 10, 6
DPI          = 300
FS_LABEL     = 14
FS_TITLE     = 14
FS_TICK      = 12
FS_LEGEND    = 9
FIT_LW       = 2
FIT_ALPHA    = 0.9
GRID_ALPHA   = 0.3


def apply_style():
    """统一仿真图表样式（与 figure-plotter 保持一致）。"""
    import matplotlib as mpl
    mpl.rcParams.update({
        'axes.titlesize'  : FS_TITLE,
        'axes.labelsize'  : FS_LABEL,
        'xtick.labelsize' : FS_TICK,
        'ytick.labelsize' : FS_TICK,
        'legend.fontsize' : FS_LEGEND,
        'figure.dpi'      : 120,
        'savefig.dpi'     : DPI,
        'savefig.bbox'    : 'tight',
        'axes.grid'       : True,
        'grid.alpha'      : GRID_ALPHA,
        'lines.linewidth' : FIT_LW,
    })
