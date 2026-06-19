#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""构建 JOLT 车队聊天机器人的知识库（fleet_kb.json）。

把项目里分散的真实数据聚合成一份紧凑 JSON，供两处共用：
  1. 网页前端的离线规则引擎（直接读 JSON 回答示例类问题）；
  2. 桥接服务把它作为 system prompt 注入 ``claude -p``，让自由问答有真实数据支撑。

数据来源（全部为聚合量，无 API 密钥、无原始遥测，可安全提交）：
  - src/jolt_toolkit/configs/vehicles.json                     车辆规格
  - test_data_config.json                                      标准数据日期区间
  - data_analysis_workspace/ep_multifactor_regression/data/fleet_trip.csv     17k 行 per-trip 能耗
  - .../results/cross_vehicle/summary_table.csv                per-vehicle 回归 + EP 统计
  - data_analysis_workspace/driving_cycle_correction/results/
        telematics_fcycle_fleet_summary.csv                    巡航修正到 90 km/h 的 EP

用法：
    python chatbot/build_kb.py
输出：
    chatbot/data/fleet_kb.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

# Windows 控制台默认 cp1252，重配为 utf-8 以免打印中文 / 符号时崩溃。
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # 老版本 Python 或非标准 stdout
    pass

# ── 路径 ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "data" / "fleet_kb.json"

VEHICLES_JSON = ROOT / "src" / "jolt_toolkit" / "configs" / "vehicles.json"
TEST_CONFIG = ROOT / ".claude" / "skills" / "generate-excel-report" / "test_data_config.json"
FLEET_TRIP = ROOT / "data_analysis_workspace" / "ep_multifactor_regression" / "data" / "fleet_trip.csv"
SUMMARY_TABLE = (
    ROOT / "data_analysis_workspace" / "ep_multifactor_regression" / "results"
    / "cross_vehicle" / "summary_table.csv"
)
FCYCLE_SUMMARY = (
    ROOT / "data_analysis_workspace" / "driving_cycle_correction" / "results"
    / "telematics_fcycle_fleet_summary.csv"
)

# 报告与温度分析建议用 2.2.2（2.2.3 温度未 patch），知识库版本标签用此。
SOURCE_VERSION = "2.2.2"

# 车队效率排名 / per-vehicle 可靠性的最小样本量。
MIN_TRIPS_FOR_RANK = 50
# EP 物理合理区间（kWh/km）：近零里程的行程会算出离谱的 EP 尖刺，
# 计算 per-vehicle 统计量时剔除（仅影响均值/分位，不改 n_trips）。
EP_MIN, EP_MAX = 0.1, 5.0


def _r(x, n=2):
    """安全四舍五入；NaN / None → None。"""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, n)


def load_json(p: Path) -> dict:
    with p.open(encoding="utf-8") as fh:
        return json.load(fh)


# ── 1. 车辆规格 ─────────────────────────────────────────────────────────────
def build_specs() -> dict:
    veh = load_json(VEHICLES_JSON)
    specs = {}
    for reg, v in veh.items():
        fuel = v.get("fuel_type", "BEV")
        specs[reg] = {
            "reg": reg,
            "srf_reg": v.get("srf_reg", reg),
            "make": v.get("make"),
            "model": v.get("model"),
            "fuel_type": fuel,
            "is_diesel": fuel.upper() == "DIESEL",
            "nominal_kwh": v.get("nominal_kwh"),
            "srf_capacity_kwh": v.get("srf_capacity_kwh"),
            "effective_capacity_kwh": v.get("effective_capacity_kwh"),
            "max_torque_nm": v.get("max_torque_nm"),
            "weight_class_t": v.get("weight_class_t"),
            "pipeline": v.get("pipeline"),
        }
    return specs


# ── 2. 数据覆盖区间 ─────────────────────────────────────────────────────────
def build_coverage() -> dict:
    cfg = load_json(TEST_CONFIG)
    cov = {}
    for entry in cfg.get("vehicles", []):
        reg = entry["registration"]
        ranges = entry.get("ranges", [])
        if not ranges:
            continue
        starts = [r["start"] for r in ranges]
        ends = [r["end"] for r in ranges]
        cov[reg] = {
            "date_start": min(starts),
            "date_end": max(ends),
            "n_periods": len(ranges),
            "ranges": [{"start": r["start"], "end": r["end"]} for r in ranges],
        }
    return cov


# ── 3. per-trip 聚合（fleet_trip.csv）───────────────────────────────────────
def build_trip_aggregates() -> dict:
    if not FLEET_TRIP.exists():
        return {}
    df = pd.read_csv(FLEET_TRIP)
    agg = {}
    for reg, g in df.groupby("registration"):
        ep_all = g["ep_kwh_per_km"].dropna()
        # 剔除物理上不可能的 EP（近零里程导致的尖刺，如 YN25RSY 的 53.8 kWh/km）
        ep = ep_all[(ep_all > EP_MIN) & (ep_all < EP_MAX)]
        n_outliers = int(len(ep_all) - len(ep))
        if ep.empty:                      # 极端兜底：全被过滤则退回原始
            ep = ep_all
        mass = g["mass_t"].dropna()
        spd = g["speed_kmh"].dropna()
        temp = g["t_amb_c"].dropna()
        elev = g["elev_change_m"].dropna()
        wind = g["v_wind_mps"].dropna()
        weather = g["weather_type"].dropna()
        weather_counts = (
            weather.value_counts().head(5).to_dict() if not weather.empty else {}
        )
        agg[reg] = {
            "n_trips": int(len(g)),
            "low_sample": bool(len(g) < MIN_TRIPS_FOR_RANK),
            "ep_outliers_dropped": n_outliers,
            "total_distance_km": _r(g["distance_km"].sum(), 1),
            "ep_kwh_per_km": {
                "mean": _r(ep.mean(), 3),
                "median": _r(ep.median(), 3),
                "std": _r(ep.std(), 3),
                "p10": _r(ep.quantile(0.10), 3),
                "p90": _r(ep.quantile(0.90), 3),
                "min": _r(ep.min(), 3),
                "max": _r(ep.max(), 3),
            },
            "mass_t": {
                "mean": _r(mass.mean(), 1),
                "std": _r(mass.std(), 1),
                "min": _r(mass.min(), 1),
                "max": _r(mass.max(), 1),
            },
            "speed_kmh_mean": _r(spd.mean(), 1),
            "t_amb_c": {
                "mean": _r(temp.mean(), 1),
                "min": _r(temp.min(), 1),
                "max": _r(temp.max(), 1),
            },
            "elev_change_m_abs_mean": _r(elev.abs().mean(), 1),
            "v_wind_mps_mean": _r(wind.mean(), 2),
            "weather_counts": {str(k): int(v) for k, v in weather_counts.items()},
            "date_first_trip": str(g["date"].min()),
            "date_last_trip": str(g["date"].max()),
        }
    return agg


# ── 4. 回归 / 巡航修正统计 ──────────────────────────────────────────────────
def build_regression() -> dict:
    if not SUMMARY_TABLE.exists():
        return {}
    df = pd.read_csv(SUMMARY_TABLE)
    out = {}
    for _, row in df.iterrows():
        out[row["registration"]] = {
            "n": int(row["n"]),
            "r2": _r(row["R^2"], 3),
            "rmse": _r(row["RMSE"], 3),
            "ep_mean": _r(row["ep_mean"], 3),
            "ep_std": _r(row["ep_std"], 3),
            "mass_t_mean": _r(row["mass_t_mean"], 1),
        }
    return out


def build_cruise() -> dict:
    if not FCYCLE_SUMMARY.exists():
        return {}
    df = pd.read_csv(FCYCLE_SUMMARY)
    out = {}
    for _, row in df.iterrows():
        out[row["reg"]] = {
            "n_trips": int(row["n_trips"]),
            "ep_raw_mean": _r(row["ep_raw_mean"], 3),
            "ep_cruise90_mean": _r(row["ep_c90_mean"], 3),
            "ep_cruise90_std": _r(row["ep_c90_std"], 3),
        }
    return out


# ── 组装 ────────────────────────────────────────────────────────────────────
def main() -> None:
    specs = build_specs()
    coverage = build_coverage()
    trips = build_trip_aggregates()
    regression = build_regression()
    cruise = build_cruise()

    fleet = {}
    for reg, spec in specs.items():
        rec = {"spec": spec}
        rec["coverage"] = coverage.get(reg)
        rec["trips"] = trips.get(reg)
        rec["regression"] = regression.get(reg)
        rec["cruise_correction"] = cruise.get(reg)
        # 能耗数据可用性标记，方便规则引擎判断该回答到什么程度。
        has_energy = bool(trips.get(reg)) or bool(regression.get(reg))
        if spec["is_diesel"]:
            rec["energy_note"] = (
                "柴油车，能耗以 L/100km 计量（非 kWh/km），不参与电车 EP 统计；"
                "详见报告 excel_report_database/2.2.2/WU70GLV/。"
            )
            rec["energy_available"] = False
        elif not has_energy:
            rec["energy_note"] = (
                "该车暂未纳入 per-trip 能耗聚合（数据量不足或新近接入），"
                "目前仅有规格与数据覆盖信息。"
            )
            rec["energy_available"] = False
        else:
            rec["energy_available"] = True
        fleet[reg] = rec

    # ── fleet 级聚合 ────────────────────────────────────────────────────────
    ev_with_ep = {
        reg: r for reg, r in fleet.items()
        if r.get("energy_available") and r.get("trips")
    }
    # 车队效率排名只纳入样本充足的车（n_trips >= MIN_TRIPS_FOR_RANK），避免新车
    # 小样本噪声（如 YN25RSY 仅 26 trip，EP 均值不可靠）误导结论。
    ep_means = {
        reg: r["trips"]["ep_kwh_per_km"]["mean"]
        for reg, r in ev_with_ep.items()
        if r["trips"]["ep_kwh_per_km"]["mean"] is not None
        and r["trips"]["n_trips"] >= MIN_TRIPS_FOR_RANK
    }
    most_eff = min(ep_means, key=ep_means.get) if ep_means else None
    least_eff = max(ep_means, key=ep_means.get) if ep_means else None
    total_trips = sum(
        r["trips"]["n_trips"] for r in fleet.values() if r.get("trips")
    )
    total_dist = sum(
        (r["trips"]["total_distance_km"] or 0)
        for r in fleet.values() if r.get("trips")
    )
    makes = sorted({r["spec"]["make"] for r in fleet.values() if r["spec"]["make"]})

    fleet_aggregates = {
        "n_vehicles": len(fleet),
        "n_ev": sum(1 for r in fleet.values() if not r["spec"]["is_diesel"]),
        "n_diesel": sum(1 for r in fleet.values() if r["spec"]["is_diesel"]),
        "makes": makes,
        "n_makes": len(makes),
        "total_trips_analysed": total_trips,
        "total_distance_km": _r(total_dist, 0),
        "ep_kwh_per_km_fleet_range": {
            "ranking_min_trips": MIN_TRIPS_FOR_RANK,
            "most_efficient": {"reg": most_eff, "ep": ep_means.get(most_eff)} if most_eff else None,
            "least_efficient": {"reg": least_eff, "ep": ep_means.get(least_eff)} if least_eff else None,
        },
        "vehicles_with_energy_stats": sorted(ev_with_ep.keys()),
        "low_sample_vehicles": sorted(
            reg for reg, r in ev_with_ep.items()
            if r["trips"]["n_trips"] < MIN_TRIPS_FOR_RANK
        ),
    }

    glossary = {
        "EP (Energy Performance)": "能耗强度，单位 kWh/km，= |ΔE_total| / 行驶距离。xlsx 中为 net EP（已扣除再生回收）。",
        "EP_gross": "把再生回收能量加回去的能耗：(|ΔE_total| + E_recup) / 距离。",
        "EP_cruise@90": "把整车 telematics EP 经驾驶工况修正投射到 90 km/h 稳态巡航的等效能耗，用于跨车公平对比。",
        "SOC": "State of Charge，电池荷电状态（%）。",
        "Effective capacity": "经修正的有效电池容量（kWh），可与标称 / SRF 容量不同。",
        "Regen / Recuperation": "再生制动回收能量。YK73WFN 系统级 η_regen ≈ 0.42。",
        "GCVW": "Gross Combination Vehicle Weight，总组合车重（含挂车与载荷），单位 t。",
        "Driving cycle correction": "驾驶工况修正（Case 1/2/3），消除速度剖面差异后比较巡航能耗。",
        "Crr / CdA": "滚动阻力系数 / 风阻面积，参数辨识专题量。",
        "Diesel fuel consumption": "柴油车能耗以 L/100km 计量；柴油 LHV 默认 10 kWh/L。",
    }

    kb = {
        "meta": {
            "title": "JOLT 电动重卡车队知识库",
            "description": "由 build_kb.py 从 jolt_toolkit 真实聚合数据生成，供聊天机器人使用。",
            "source_version": SOURCE_VERSION,
            "note": "所有数值为聚合统计量（无原始遥测、无密钥）。温度相关取自 excel_report_database/2.2.2。",
        },
        "fleet_aggregates": fleet_aggregates,
        "glossary": glossary,
        "fleet": fleet,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        json.dump(kb, fh, ensure_ascii=False, indent=2)

    # 额外产出一个 JS 包装版，让网页用 file:// 双击打开时也能加载知识库
    # （浏览器对 file:// 的 fetch() 有 CORS 限制，但 <script> 标签不受限）。
    js_out = OUT.with_suffix(".js")
    compact = json.dumps(kb, ensure_ascii=False, separators=(",", ":"))
    with js_out.open("w", encoding="utf-8") as fh:
        fh.write("// 自动生成，勿手改。运行 `python chatbot/build_kb.py` 重新生成。\n")
        fh.write("window.FLEET_KB = " + compact + ";\n")

    # ── 控制台摘要 ──────────────────────────────────────────────────────────
    print(f"✓ 写入 {OUT.relative_to(ROOT)}  +  {js_out.relative_to(ROOT)}")
    print(f"  车辆数: {len(fleet)}  (EV {fleet_aggregates['n_ev']} / 柴油 {fleet_aggregates['n_diesel']})")
    print(f"  含能耗统计: {len(ev_with_ep)} 辆 -> {', '.join(sorted(ev_with_ep))}")
    print(f"  总分析 trip 数: {total_trips:,}   总里程: {total_dist:,.0f} km")
    if most_eff:
        print(f"  最省: {most_eff} ({ep_means[most_eff]} kWh/km)   "
              f"最费: {least_eff} ({ep_means[least_eff]} kWh/km)")
    spec_only = [reg for reg, r in fleet.items() if not r.get("energy_available")]
    if spec_only:
        print(f"  仅规格(无能耗统计): {', '.join(spec_only)}")
    print(f"  文件大小: {OUT.stat().st_size/1024:.1f} KB")


if __name__ == "__main__":
    main()
