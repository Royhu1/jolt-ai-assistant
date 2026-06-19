# -*- coding: utf-8 -*-
"""
仿真实验总运行脚本 — 依次执行 Exp 1–7，汇总系数，生成报告初稿。

用法：
    cd <project_root>
    python research_projects/simulation/run_all.py
"""
from __future__ import annotations
import sys, pathlib, datetime
import numpy as np

# 修复 Windows 控制台输出编码
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROOT = pathlib.Path(__file__).resolve().parent.parent
SIM  = ROOT / 'simulation'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIM))

# 延迟导入（matplotlib backend 可能需要先设置）
import matplotlib
matplotlib.use('Agg')

from models.vehicle_physics import BASELINE, compute_ep, eta_bat

# 自动生成的简版报告写入 _auto 后缀文件；手工维护的详细版见 EP_simulation_report.md
REPORT_PATH = SIM / 'results' / 'EP_simulation_report_auto.md'


def main():
    print('=' * 60)
    print('电动重卡 EP 仿真实验 — 运行所有实验')
    print('=' * 60)

    # ── 基准 EP ──────────────────────────────────────────────────────────────
    ep0_result = compute_ep(m=BASELINE['m'])
    EP0 = ep0_result['EP']
    print(f'\n基准 EP₀ = {EP0:.4f} kWh/km (m={BASELINE["m"]/1000:.0f} t, T={BASELINE["T_amb"]}°C)\n')

    # ── 运行各实验 ─────────────────────────────────────────────────────────
    from experiments.exp1_mass        import run as run1
    from experiments.exp2_wind        import run as run2
    from experiments.exp3_temperature import run as run3
    from experiments.exp4_road_surface import run as run4
    from experiments.exp5_elevation   import run as run5
    from experiments.exp6_stop_start  import run as run6
    from experiments.exp7_cda         import run as run7
    from experiments.exp8_ep_vs_mass_factors import run as run8

    print('Exp 1 — 车辆质量...')
    r1 = run1()
    print(f'  → α₁ = {r1["alpha1"]:.4e} kWh/(km·kg),  R² = {r1["r_squared"]:.6f}')

    print('Exp 2 — 风速...')
    r2 = run2()
    print(f'  → α₂ = {r2["alpha2"]:.6f} kWh/(km·(m/s)²),  R² = {r2["r_squared"]:.6f}')

    print('Exp 3 — 环境温度...')
    r3 = run3()
    idx_m5  = list(r3['temps']).index(-5.0)
    idx_p35 = list(r3['temps']).index(35.0)
    print(f'  → EP(-5°C) = {r3["eps"][idx_m5]:.4f}, EP(20°C) = {EP0:.4f}, EP(35°C) = {r3["eps"][idx_p35]:.4f} kWh/km')

    print('Exp 4 — 路面状况...')
    r4 = run4()
    print(f'  → α₃ = {r4["alpha3"]:.4f} kWh/(km·ΔCrr),  R² = {r4["r_squared"]:.6f}')

    print('Exp 5 — 海拔变化...')
    r5 = run5()
    print(f'  → α₄⁺ = {r5["alpha4_plus"] * 1e4:.4f}×10⁻⁴ kWh/(km·m), '
          f'α₄⁻ = {r5["alpha4_minus"] * 1e4:.4f}×10⁻⁴ kWh/(km·m)')

    print('Exp 6 — 启停次数...')
    r6 = run6()
    for m, a5 in r6['alpha5s'].items():
        print(f'  → m={m//1000}t: α₅ = {a5 * 1e4:.4f}×10⁻⁴ kWh/(km·stop)')

    print('Exp 7 — 车辆构型（CdA）...')
    r7 = run7()
    print(f'  → α₇ = {r7["alpha7"]:.5f} kWh/(km·m²),  R² = {r7["r_squared"]:.6f}')

    print('Exp 8 — EP vs Mass factor plots + Sensitivity...')
    r8 = run8()

    print('\n所有实验完成，正在生成报告...')

    # ── 计算 c₀（截距）──────────────────────────────────────────────────────
    # EP = c₀ + α₁·m + α₂·V² + f_T(T) + α₃·Crr + f_h(Δh) + α₅(m)·n + α₇·CdA
    # 在基准条件下：f_T(T₀)=0, f_h(0)=0, n=0, V=0
    # → c₀ = EP₀ − α₁·m₀ − α₃·Crr₀ − α₇·CdA₀
    alpha1 = r1['alpha1']
    alpha2 = r2['alpha2']
    alpha3 = r4['alpha3']
    alpha7 = r7['alpha7']
    m0     = BASELINE['m']
    crr0   = BASELINE['crr']
    cda0   = BASELINE['cda']

    c0 = EP0 - alpha1 * m0 - alpha3 * crr0 - alpha7 * cda0

    # α₅ 参数化为 α₅ = k₅ × m（从 Exp 6 拟合）
    alpha5_42t = r6['alpha5s'][42_000]

    # 报告由手写的 EP_simulation_report.md 维护，不再自动生成
    print(f'\n报告: results/EP_simulation_report.md（手工维护）')
    print('=' * 60)


def _write_report(path, now, EP0, c0, r1, r2, r3, r4, r5, r6, r7,
                  alpha1, alpha2, alpha3, alpha7, alpha5_42t):
    # f_T 代表值
    temps_sel = [-5, 0, 5, 10, 15, 20, 25, 30, 35]
    fT_rows = []
    for T in temps_sel:
        ep_T = compute_ep(m=BASELINE['m'], T_amb=T)['EP']
        fT = ep_T - EP0
        fT_rows.append((T, eta_bat(T), ep_T, fT))

    # α₅(m) 表
    alpha5_rows = [(m, a5) for m, a5 in r6['alpha5s'].items()]

    lines = [
        f'# 电动重卡 EP 仿真实验报告',
        f'',
        f'> 生成日期：{now}  ',
        f'> 基准参数来源：[1] J. Hu, IEEE ITSC 2026, Table I & III',
        f'',
        f'---',
        f'',
        f'## 1. 基准场景',
        f'',
        f'| 参数 | 值 |',
        f'|------|----|',
        f'| 总质量 $m_0$ | 42,000 kg |',
        f'| 巡航速度 $v_c$ | 90 km/h (25 m/s) |',
        f'| 加速度 $a_{{acc}}$ | 0.58 m/s² |',
        f'| 减速度 $a_{{dec}}$ | 0.83 m/s² |',
        f'| 滚阻系数 $C_{{rr,0}}$ | 0.00465 |',
        f'| 风阻面积 $C_dA_0$ | 6.16 m² |',
        f'| 空气密度 $\\rho$ | 1.225 kg/m³ |',
        f'| 驱动系效率 $\\eta_{{dt}}$ | 0.90 |',
        f'| 再生制动效率 $\\eta_{{regen}}$ | 0.90 |',
        f'| 环境温度 $T_0$ | 20°C |',
        f'| 风速 / 坡度 / 停车 | 0 |',
        f'',
        f'**基准 EP₀ = {EP0:.4f} kWh/km**',
        f'',
        f'---',
        f'',
        f'## 2. 各实验结果',
        f'',
        f'### Exp 1 — 车辆质量',
        f'',
        f'| 指标 | 值 |',
        f'|------|----|',
        f'| 系数 $\\alpha_1$ | {alpha1:.4e} kWh/(km·kg) = {alpha1 * 1e5:.3f}×10⁻⁵ kWh/(km·kg) |',
        f'| $R^2$ | {r1["r_squared"]:.6f} |',
        f'| 线性关系 | **已验证** — EP 与质量严格线性 |',
        f'',
        f'![]({_rel("exp1_mass.png")})',
        f'',
        f'**解读**：EP 与 GVW 严格线性，斜率 α₁ ≈ {alpha1 * 1e5:.3f}×10⁻⁵ kWh/(km·kg)。'
        f'从 18 t 到 44 t（+26 t），EP 增加约 {(r1["eps"][-1] - r1["eps"][0]):.3f} kWh/km'
        f'（+{(r1["eps"][-1]/r1["eps"][0] - 1)*100:.1f}%）。',
        f'',
        f'---',
        f'',
        f'### Exp 2 — 风速',
        f'',
        f'| 指标 | 值 |',
        f'|------|----|',
        f'| 系数 $\\alpha_2$ | {r2["alpha2"]:.6f} kWh/(km·(m/s)²) |',
        f'| $R^2$ (ΔEP vs $V^2$) | {r2["r_squared"]:.6f} |',
        f'| 二次关系 | **已验证** |',
        f'',
        f'![]({_rel("exp2_wind.png")})',
        f'',
        f'**解读**：随机风向下，额外 EP ∝ V²。15 m/s 风速下 ΔEP ≈ {(r2["eps"][-1] - r2["eps"][0]):.3f} kWh/km。',
        f'',
        f'---',
        f'',
        f'### Exp 3 — 环境温度（Arrhenius 电池效率）',
        f'',
        f'| $T$ (°C) | $\\eta_{{bat}}$ | EP (kWh/km) | $f_T(T)$ (kWh/km) |',
        f'|---------|--------------|------------|-----------------|',
    ]

    for T, eb, ep, ft in fT_rows:
        lines.append(f'| {T:+.0f} | {eb:.4f} | {ep:.4f} | {ft:+.4f} |')

    lines += [
        f'',
        f'![]({_rel("exp3_temperature.png")})',
        f'',
        f'**解读**：温度效应非线性（Arrhenius 指数），低温端（−5°C）EP 增加约'
        f' {fT_rows[0][3]:.3f} kWh/km（+{fT_rows[0][3]/EP0*100:.1f}%）。'
        f' 35°C 时效率与 25°C 相当，高温影响可忽略。',
        f'',
        f'---',
        f'',
        f'### Exp 4 — 路面状况',
        f'',
        f'| 路面 | $C_{{rr}}$ | EP (kWh/km) | ΔEP |',
        f'|------|----------|------------|-----|',
    ]

    for lab, crr, ep, dep in zip(r4['labels'], r4['crrs'], r4['eps'],
                                  r4['eps'] - r4['eps'][0]):
        lines.append(f'| {lab} | {crr:.5f} | {ep:.4f} | {dep:+.4f} |')

    lines += [
        f'',
        f'| 指标 | 值 |',
        f'|------|----|',
        f'| 系数 $\\alpha_3$ | {alpha3:.2f} kWh/(km per unit $C_{{rr}}$) |',
        f'| $R^2$ | {r4["r_squared"]:.6f} |',
        f'',
        f'![]({_rel("exp4_road_surface.png")})',
        f'',
        f'**解读**：EP 与 Crr 严格线性。积雪路面（Crr×2）导致 EP 增加'
        f' {(r4["eps"][-1] - r4["eps"][0]):.3f} kWh/km（+{(r4["eps"][-1]/r4["eps"][0]-1)*100:.1f}%）。',
        f'',
        f'---',
        f'',
        f'### Exp 5 — 净海拔变化',
        f'',
        f'| 指标 | 值 |',
        f'|------|----|',
        f'| 上坡系数 $\\alpha_4^+$ | {r5["alpha4_plus"] * 1e4:.4f}×10⁻⁴ kWh/(km·m) |',
        f'| 上坡理论值 | {r5["alpha4_plus_theory"] * 1e4:.4f}×10⁻⁴ kWh/(km·m) |',
        f'| 下坡系数 $\\alpha_4^-$ | {r5["alpha4_minus"] * 1e4:.4f}×10⁻⁴ kWh/(km·m) |',
        f'| 下坡理论值 | {r5["alpha4_minus_theory"] * 1e4:.4f}×10⁻⁴ kWh/(km·m) |',
        f'| $|\\alpha_4^+/\\alpha_4^-|$ | {abs(r5["alpha4_plus"]/r5["alpha4_minus"]):.4f} (理论 = $1/(\\eta_{{dt}} \\cdot \\eta_{{regen}})$ = {1/(BASELINE["eta_dt"]*BASELINE["eta_regen"]):.4f}) |',
        f'| $R^2$ (上坡) | {r5["r_up"]:.6f} |',
        f'| $R^2$ (下坡) | {r5["r_down"]:.6f} |',
        f'',
        f'![]({_rel("exp5_elevation.png")})',
        f'',
        f'**解读**：上下坡系数不对称，比值为 {abs(r5["alpha4_plus"]/r5["alpha4_minus"]):.3f}，'
        f'等于 $1/(\\eta_{{dt}} \\cdot \\eta_{{regen}}) = 1/(0.90\\times 0.90) \\approx 1.235$，与理论吻合。',
        f'',
        f'---',
        f'',
        f'### Exp 6 — 启停次数',
        f'',
        f'| 质量 (t) | $\\alpha_5$ (kWh/(km·stop)) |',
        f'|---------|--------------------------|',
    ]

    for m, a5 in alpha5_rows:
        lines.append(f'| {m//1000} | {a5:.6f} |')

    lines += [
        f'',
        f'α₅ 随质量线性增大，$R^2 = {r6["r_squared_a5m"]:.6f}$，',
        f'验证了 α₅(m) = k₅ × m 的参数化关系。',
        f'',
        f'![]({_rel("exp6_stop_start.png")})',
        f'',
        f'**解读**：每次启停（从 90 km/h 全停再加速）在 42 t 满载时净消耗约'
        f' {alpha5_42t * 1e4:.3f}×10⁻⁴ kWh/km·stop，等效于'
        f' {alpha5_42t / EP0 * 100:.2f}% EP 增量/次。',
        f'',
        f'---',
        f'',
        f'### Exp 7 — 车辆构型 ($C_dA$)',
        f'',
        f'| 构型 | $C_dA$ (m²) | EP (kWh/km) | ΔEP |',
        f'|------|------------|------------|-----|',
    ]

    for lab, c, ep, dep in zip(r7['labels'], r7['cdas'], r7['eps'],
                                r7['eps'] - r7['eps'][0]):
        lines.append(f'| {lab} | {c:.2f} | {ep:.4f} | {dep:+.4f} |')

    lines += [
        f'',
        f'| 指标 | 值 |',
        f'|------|----|',
        f'| 系数 $\\alpha_7$ | {alpha7:.5f} kWh/(km·m²) |',
        f'| 理论值 | {r7["alpha7_theory"]:.5f} kWh/(km·m²) |',
        f'| $R^2$ | {r7["r_squared"]:.6f} |',
        f'',
        f'![]({_rel("exp7_cda.png")})',
        f'',
        f'**解读**：EP 与 CdA 严格线性。Tanker（8.5 m²）比 Box trailer（6.16 m²）'
        f' 每 km 多消耗约 {(r7["eps"][-1] - r7["eps"][r7["cdas"].tolist().index(6.16)]):.3f} kWh'
        f'（+{(r7["eps"][-1]/r7["eps"][r7["cdas"].tolist().index(6.16)]-1)*100:.1f}%）。',
        f'',
        f'---',
        f'',
        f'## 3. 完整 EP 预测公式',
        f'',
        f'各实验系数汇总后，完整公式为：',
        f'',
        f'$$\\boxed{{EP = {c0:.4f} + {alpha1:.4e} \\cdot m + {alpha2:.6f} \\cdot V_{{wind}}^2 + f_T(T) + {alpha3:.2f} \\cdot C_{{rr}} + f_h(\\Delta h) + \\alpha_5(m) \\cdot n_{{stop}} + {alpha7:.5f} \\cdot C_dA}}$$',
        f'',
        f'其中：',
        f'',
        f'| 项 | 表达式 | 单位 | 数值 |',
        f'|----|--------|------|------|',
        f'| $c_0$ | 截距（基准条件下非线性残差） | kWh/km | {c0:.4f} |',
        f'| $\\alpha_1$ | 质量系数 | kWh/(km·kg) | {alpha1:.4e} |',
        f'| $\\alpha_2$ | 风速系数 | kWh/(km·(m/s)²) | {alpha2:.6f} |',
        f'| $f_T(T)$ | Arrhenius 温度效应（见 Exp 3 表） | kWh/km | 非线性 |',
        f'| $\\alpha_3$ | 滚阻系数 | kWh/(km per unit Crr) | {alpha3:.2f} |',
        f'| $\\alpha_4^+$ | 上坡系数（Δh > 0） | kWh/(km·m) | {r5["alpha4_plus"]:.4e} |',
        f'| $\\alpha_4^-$ | 下坡系数（Δh < 0） | kWh/(km·m) | {r5["alpha4_minus"]:.4e} |',
        f'| $\\alpha_5(m)$ | 启停系数（质量依赖） | kWh/(km·stop) | 见 Exp 6 表 |',
        f'| $\\alpha_7$ | 风阻面积系数 | kWh/(km·m²) | {alpha7:.5f} |',
        f'',
        f'**关键结论**：',
        f'',
        f'1. **线性因素**（质量、Crr、CdA）：R² > 0.999，严格线性，适合直接代入公式。',
        f'2. **二次因素**（风速）：ΔEP ∝ V²，已验证。',
        f'3. **非线性因素**（温度）：低温端效率损失显著（−5°C 损失约 {fT_rows[0][3]/EP0*100:.1f}%），高温（35°C）影响可忽略。',
        f'4. **不对称因素**（海拔）：上坡/下坡比 = {abs(r5["alpha4_plus"]/r5["alpha4_minus"]):.3f}，理论值 = 1/(η_dt × η_regen) ≈ 1.235。',
        f'5. **质量调制因素**（启停）：α₅ ∝ m，公式中 α₅ 需随质量参数化。',
        f'',
        f'---',
        f'',
        f'## 4. 因素贡献量级汇总',
        f'',
        f'以基准 EP₀ = {EP0:.3f} kWh/km 为参考，各因素在代表性条件下的 ΔEP：',
        f'',
        f'| 因素 | 代表条件 | ΔEP (kWh/km) | 相对贡献 |',
        f'|------|---------|------------|---------|',
        f'| 质量 +10 t | GVW 42→52 t | +{alpha1 * 10_000:.4f} | +{alpha1 * 10_000 / EP0 * 100:.1f}% |',
        f'| 风速 10 m/s | 逆风 10 m/s | +{r2["alpha2"] * 100:.4f} | +{r2["alpha2"] * 100 / EP0 * 100:.1f}% |',
        f'| 温度 −5°C | 20→−5°C | +{fT_rows[0][3]:.4f} | +{fT_rows[0][3]/EP0*100:.1f}% |',
        f'| 潮湿路面 | 干→重度湿 | +{r4["eps"][2] - r4["eps"][0]:.4f} | +{(r4["eps"][2] - r4["eps"][0])/EP0*100:.1f}% |',
        f'| 上坡 +100 m | Δh = +100 m | +{r5["alpha4_plus"] * 100:.4f} | +{r5["alpha4_plus"] * 100 / EP0 * 100:.1f}% |',
        f'| 10 次启停 | n_stop = 10 | +{alpha5_42t * 10:.4f} | +{alpha5_42t * 10 / EP0 * 100:.1f}% |',
        f'| 大 CdA | 6.16→8.5 m² | +{alpha7 * (8.5 - 6.16):.4f} | +{alpha7 * (8.5 - 6.16) / EP0 * 100:.1f}% |',
        f'',
        f'---',
        f'',
        f'## 5. 参考文献',
        f'',
        f'[1] J. Hu, "A Traffic-Aware Driving Cycle Predictor for Heavy Goods Vehicles," *IEEE ITSC 2026*.',
        f'',
        f'[2] NREL FY01 Report (OSTI/28716) — Li-ion battery temperature effects.',
        f'',
        f'[3] Battery University BU-808c — Internal resistance and temperature.',
        f'',
    ]

    path.write_text('\n'.join(lines), encoding='utf-8')


def _rel(fname: str) -> str:
    """相对路径（Markdown 图片引用）"""
    return f'figures/{fname}'


if __name__ == '__main__':
    main()
