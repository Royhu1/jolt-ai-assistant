"""
参数辨识算法单元测试。
使用合成数据验证能量平衡方程和约束线交点法的正确性。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _make_cruise_segment(
    *,
    n_points: int = 500,
    speed_kmph: float = 70.0,
    mass_kg: float = 20000.0,
    distance_m: float = 5000.0,
    elevation_start: float = 100.0,
    elevation_end: float = 105.0,
    true_crr: float = 0.007,
    true_cda: float = 6.0,
    motor_efficiency: float = 0.90,
    gravity: float = 9.81,
    air_density: float = 1.225,
) -> pd.DataFrame:
    """
    生成一个合成巡航段 DataFrame，其能量由 true_crr 和 true_cda 精确计算。
    """
    speed_mps = speed_kmph / 3.6
    ds = np.linspace(0, distance_m, n_points)
    dt_each = distance_m / n_points / speed_mps  # seconds per step

    # 恒速 → ΔE_kinetic = 0
    # 势能变化
    delta_h = elevation_end - elevation_start
    delta_pe = mass_kg * gravity * delta_h

    # 滚阻
    e_rr = true_crr * mass_kg * gravity * distance_m

    # 空阻
    e_aero = true_cda * 0.5 * air_density * speed_mps**2 * distance_m

    # 总电池能量 (J)
    e_battery_J = (delta_pe + e_rr + e_aero) / motor_efficiency
    e_battery_kwh = e_battery_J / 3_600_000

    # 构造 DataFrame
    altitudes = np.linspace(elevation_start, elevation_end, n_points)
    speeds = np.full(n_points, speed_kmph) + np.random.normal(0, 0.5, n_points)
    masses = np.full(n_points, mass_kg) + np.random.normal(0, 50, n_points)
    energies = np.linspace(0, e_battery_kwh, n_points)  # 累积能量计数器
    timestamps = pd.date_range("2025-01-01", periods=n_points, freq="1s")

    return pd.DataFrame({
        "timestamp": timestamps,
        "speed_kmph": speeds,
        "mass_kg": masses,
        "altitude_m": altitudes,
        "energy_kwh": energies,
        "distance_m": ds,
        "latitude": np.linspace(52.0, 52.045, n_points),
        "longitude": np.linspace(0.0, 0.063, n_points),
    })


def test_single_constraint():
    """验证单个约束线的斜率和截距方向。"""
    from jolt_toolkit.vehicle_params_identificator.identification import calculate_linear_constraint

    df = _make_cruise_segment(mass_kg=15000, speed_kmph=60)
    result = calculate_linear_constraint(df, motor_efficiency=0.90)

    assert result is not None, "约束计算不应返回 None"
    assert "slope" in result
    assert "intercept" in result
    # slope 应为负数（C_dA 增大时 C_rr 减小）
    assert result["slope"] < 0, f"斜率应为负: {result['slope']}"
    assert result["intercept"] > 0, f"截距应为正: {result['intercept']}"
    print(f"单约束测试通过: slope={result['slope']:.6e}, intercept={result['intercept']:.6f}")


def test_identification_with_synthetic_data():
    """
    使用两组不同质量的合成数据验证交线法辨识。
    真实值: C_rr = 0.007, C_dA = 6.0
    """
    from jolt_toolkit.vehicle_params_identificator.identification import (
        calculate_all_constraints,
        identify_parameters,
    )

    TRUE_CRR = 0.007
    TRUE_CDA = 6.0

    segments = []

    # 轻载组 (~15000 kg)
    for i in range(30):
        mass = 13000 + np.random.uniform(0, 4000)
        speed = 55 + np.random.uniform(0, 20)
        df = _make_cruise_segment(
            mass_kg=mass, speed_kmph=speed,
            true_crr=TRUE_CRR, true_cda=TRUE_CDA,
            elevation_start=100, elevation_end=100 + np.random.uniform(-5, 5),
        )
        segments.append({"segment_period": (f"seg_{i}", f"seg_{i}"), "segment_df": df})

    # 重载组 (~30000 kg)
    for i in range(30):
        mass = 28000 + np.random.uniform(0, 4000)
        speed = 55 + np.random.uniform(0, 20)
        df = _make_cruise_segment(
            mass_kg=mass, speed_kmph=speed,
            true_crr=TRUE_CRR, true_cda=TRUE_CDA,
            elevation_start=100, elevation_end=100 + np.random.uniform(-5, 5),
        )
        segments.append({"segment_period": (f"seg_{30+i}", f"seg_{30+i}"), "segment_df": df})

    # 计算约束
    constraints = calculate_all_constraints(segments)
    assert len(constraints) >= 50, f"约束数量不足: {len(constraints)}"

    # 辨识
    result = identify_parameters(constraints)
    assert result["c_rr_identified"] is not None, "未辨识出 C_rr"
    assert result["c_da_identified"] is not None, "未辨识出 C_dA"

    crr = result["c_rr_identified"]
    cda = result["c_da_identified"]

    print(f"\n辨识结果: C_rr = {crr:.6f} (真实: {TRUE_CRR}), C_dA = {cda:.2f} (真实: {TRUE_CDA})")
    print(f"相对误差: C_rr = {abs(crr - TRUE_CRR)/TRUE_CRR*100:.1f}%, C_dA = {abs(cda - TRUE_CDA)/TRUE_CDA*100:.1f}%")

    # 允许 20% 的误差范围（合成数据含噪声 + 海拔变化）
    assert abs(crr - TRUE_CRR) / TRUE_CRR < 0.20, f"C_rr 误差过大: {crr:.6f} vs {TRUE_CRR}"
    assert abs(cda - TRUE_CDA) / TRUE_CDA < 0.20, f"C_dA 误差过大: {cda:.2f} vs {TRUE_CDA}"
    print("交线法辨识测试通过！")


def test_cruise_segment_extraction():
    """验证巡航段提取的筛选逻辑。"""
    from jolt_toolkit.vehicle_params_identificator.preprocessing import get_cruise_segments

    # 制造一条 leg 数据：前 10 km 恒速 60 km/h，后 5 km 变速
    n = 1000
    speed = np.concatenate([
        np.full(700, 60.0) + np.random.normal(0, 2, 700),  # 前段恒速
        np.linspace(60, 10, 300),  # 后段减速
    ])
    df = pd.DataFrame({
        "speed_kmph": speed,
        "distance_m": np.linspace(0, 15000, n),
        "mass_kg": np.full(n, 20000.0),
        "altitude_m": np.linspace(100, 110, n),
        "energy_kwh": np.linspace(0, 5.0, n),
        "timestamp": pd.date_range("2025-01-01", periods=n, freq="1s"),
    })

    segs = get_cruise_segments(df, seg_distance_m=5000, min_avg_speed_kmph=40)
    # 应至少从恒速段提取到一个巡航段
    assert len(segs) >= 1, f"应提取到至少 1 个巡航段，实际: {len(segs)}"
    print(f"巡航段提取测试通过: 提取 {len(segs)} 个段")


def test_preprocessing_filters():
    """验证：低速/停车段应被过滤掉。"""
    from jolt_toolkit.vehicle_params_identificator.preprocessing import get_cruise_segments

    # 全程低速 (<30 km/h)
    n = 500
    df = pd.DataFrame({
        "speed_kmph": np.full(n, 25.0),
        "distance_m": np.linspace(0, 10000, n),
        "mass_kg": np.full(n, 20000.0),
        "altitude_m": np.linspace(100, 105, n),
        "energy_kwh": np.linspace(0, 2.0, n),
    })
    segs = get_cruise_segments(df, seg_distance_m=5000, min_avg_speed_kmph=40)
    assert len(segs) == 0, "低速段不应被提取"
    print("低速过滤测试通过")


def test_visualization():
    """验证绘图不报错。"""
    from jolt_toolkit.vehicle_params_identificator.identification import calculate_all_constraints, identify_parameters
    from jolt_toolkit.vehicle_params_identificator.visualization import plot_comprehensive_analysis
    import tempfile
    import os

    segments = []
    for mass in [15000, 30000]:
        for _ in range(10):
            df = _make_cruise_segment(mass_kg=mass + np.random.uniform(-1000, 1000))
            segments.append({"segment_period": ("a", "b"), "segment_df": df})

    constraints = calculate_all_constraints(segments, verbose=False)
    result = identify_parameters(constraints)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test_plot.png")
        saved = plot_comprehensive_analysis(result, "Test Vehicle", save_path=path)
        assert saved is not None, "图应成功保存"
        assert os.path.exists(path), f"图文件不存在: {path}"
        print(f"绘图测试通过: {os.path.getsize(path)} bytes")


if __name__ == "__main__":
    print("=" * 60)
    print("  JOLT 参数辨识算法单元测试")
    print("=" * 60)

    test_single_constraint()
    print()
    test_cruise_segment_extraction()
    print()
    test_preprocessing_filters()
    print()
    test_identification_with_synthetic_data()
    print()
    test_visualization()

    print("\n✓ 所有测试通过")
