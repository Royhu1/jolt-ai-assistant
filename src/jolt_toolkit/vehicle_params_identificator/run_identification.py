"""
JOLT 电动重卡参数辨识 CLI 入口。

用法:
    # 探测通道
    python -m jolt_toolkit.vehicle_params_identificator.run_identification --probe --veh YN25RSY

    # 单辆车辨识（自动从 IDENTIFICATION_CONFIGS 读取 max_torque + 日期范围）
    python -m jolt_toolkit.vehicle_params_identificator.run_identification --veh YN25RSY

    # 全部有 Logger 的车辆
    python -m jolt_toolkit.vehicle_params_identificator.run_identification --all

    # 仅从已下载数据辨识
    python -m jolt_toolkit.vehicle_params_identificator.run_identification --veh YN25RSY --no-download

    # 自定义参数
    python -m jolt_toolkit.vehicle_params_identificator.run_identification --veh YN25RSY --max-torque 1200 --seg-distance 10000 --min-speed 60
"""

from __future__ import annotations

import argparse
import json
import logging
import pickle
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from jolt_toolkit.vehicle_params_identificator import config as cfg


def setup_logging(vehicle_reg: str = "all") -> logging.Logger:
    cfg.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = cfg.LOGS_DIR / f"identification_{vehicle_reg}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=getattr(logging, cfg.LOG_LEVEL),
        format=cfg.LOG_FORMAT,
        datefmt=cfg.LOG_DATE_FORMAT,
        handlers=[
            logging.FileHandler(str(log_file), encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )
    return logging.getLogger(__name__)


def probe_vehicle(vehicle_reg: str, srf_reg: str, srf=None):
    """探测车辆的全日期范围 Logger 数据。"""
    from jolt_toolkit.vehicle_params_identificator.data_loader import discover_logger_channels
    info = discover_logger_channels(
        vehicle_reg, srf_reg, "2024-01-01", "2026-12-31", srf=srf,
    )
    print(f"\n{'='*60}")
    print(f"  {vehicle_reg} ({srf_reg})")
    sources = info["logger_sources"]
    if sources:
        for src, d in sources.items():
            print(f"  {src}: {d['count']} legs, {d.get('first','')} ~ {d.get('last','')}")
            print(f"    channels: {d.get('channels', [])}")
    else:
        print("  NO LOGGER DATA")
    print(f"  FPS legs: {info['fps_count']}")
    print(f"{'='*60}\n")
    return info


def _apply_filters(
    constraints: list[dict],
    *,
    use_wind: bool,
    use_mass: bool,
    use_elev: bool,
    log: logging.Logger,
) -> list[dict]:
    """应用指定过滤器组合。"""
    from jolt_toolkit.vehicle_params_identificator.identification import (
        filter_by_wind_mean,
        filter_by_elevation_change,
        filter_by_mass_deviation,
    )
    filtered = constraints
    if use_wind:
        filtered = filter_by_wind_mean(filtered, wind_max_mps=cfg.WIND_MEAN_MAX_MPS)
    if use_mass:
        filtered = filter_by_mass_deviation(filtered, deviation_pct=cfg.MASS_DEVIATION_PCT)
    if use_elev:
        filtered = filter_by_elevation_change(
            filtered, threshold_m=cfg.ELEVATION_CHANGE_THRESHOLD_M,
        )
    return filtered


def run_single_vehicle(
    vehicle_reg: str,
    vehicle_cfg: dict,
    ds: str,
    de: str,
    *,
    srf=None,
    download: bool = True,
    max_torque_nm: float | None = None,
    drive_train_efficiency: float = cfg.MOTOR_EFFICIENCY,
    seg_distance_m: float | None = None,
    min_avg_speed: float | None = None,
    log: logging.Logger,
) -> dict | None:
    """对单辆车执行完整辨识流程。"""
    from jolt_toolkit.vehicle_params_identificator.data_loader import download_logger_data, load_vehicle_csvs
    from jolt_toolkit.vehicle_params_identificator.preprocessing import extract_all_cruise_segments
    from jolt_toolkit.vehicle_params_identificator.identification import (
        calculate_all_constraints,
        identify_parameters,
    )
    from jolt_toolkit.vehicle_params_identificator.visualization import plot_comprehensive_analysis, plot_mass_histogram

    srf_reg = vehicle_cfg["srf_reg"]

    # 1. 下载 Logger 数据
    if download:
        download_logger_data(vehicle_reg, srf_reg, ds, de, srf=srf)

    # 2. 加载
    try:
        dfs = load_vehicle_csvs(vehicle_reg)
    except (FileNotFoundError, ValueError) as exc:
        log.warning("加载失败: %s — %s", vehicle_reg, exc)
        return None

    if not dfs:
        log.warning("无有效数据: %s", vehicle_reg)
        return None

    total_rows = sum(len(d) for d in dfs)
    log.info("加载 %d 条 legs, 共 %d 行", len(dfs), total_rows)

    # 检查是否有 EEC1
    has_eec1 = any("EngSpd" in d.columns for d in dfs)
    energy_mode = "eec1" if has_eec1 else "battery"
    log.info("能量模式: %s (has_eec1=%s, max_torque=%.0f Nm)",
             energy_mode, has_eec1,
             max_torque_nm if max_torque_nm else 0)

    if energy_mode == "eec1" and max_torque_nm is None:
        log.error("EEC1 模式需要 max_torque_nm 参数")
        return None

    # 3. 提取巡航段
    seg_kwargs = {}
    if seg_distance_m is not None:
        seg_kwargs["seg_distance_m"] = seg_distance_m
    if min_avg_speed is not None:
        seg_kwargs["min_avg_speed_kmph"] = min_avg_speed

    segments = extract_all_cruise_segments(dfs, **seg_kwargs)
    if not segments:
        log.warning("未提取到巡航段: %s", vehicle_reg)
        return None

    # 4. 计算约束（无过滤）
    constraints = calculate_all_constraints(
        segments,
        max_torque_nm=max_torque_nm,
        drive_train_efficiency=drive_train_efficiency,
        energy_mode=energy_mode,
    )
    if len(constraints) < 2:
        log.warning("约束不足: %s (%d)", vehicle_reg, len(constraints))
        return None

    # 5. 聚类 + 标记
    result_all = identify_parameters(constraints)
    if result_all["cluster_labels"] is not None:
        for i, c in enumerate(constraints):
            c["cluster"] = int(result_all["cluster_labels"][i])

    # 6. 保存约束 PKL
    results_dir = cfg.RESULTS_DIR / vehicle_reg
    results_dir.mkdir(parents=True, exist_ok=True)
    pkl_path = results_dir / f"{vehicle_reg}_constraints.pkl"
    with open(pkl_path, "wb") as f:
        pickle.dump(constraints, f)
    log.info("约束保存: %s (%d 条)", pkl_path, len(constraints))

    # 7. 质量分布直方图
    plot_mass_histogram(
        constraints, vehicle_reg,
        save_path=str(results_dir / f"{vehicle_reg}_mass_hist.png"),
    )

    # 8. 7 种过滤组合图（与参考实现一致）
    make = vehicle_cfg.get("make", "")
    label = f"{vehicle_reg} ({make})"
    cases = [
        ("all",  "Unfiltered",                      dict(use_wind=False, use_mass=False, use_elev=False)),
        ("0",    f"Wind ≤{cfg.WIND_MEAN_MAX_MPS}m/s",                   dict(use_wind=True,  use_mass=False, use_elev=False)),
        ("1",    f"Mass ±{cfg.MASS_DEVIATION_PCT*100:.0f}%",             dict(use_wind=False, use_mass=True,  use_elev=False)),
        ("2",    f"Elev ±{cfg.ELEVATION_CHANGE_THRESHOLD_M:.0f}m",       dict(use_wind=False, use_mass=False, use_elev=True)),
        ("3",    f"Wind+Mass",                       dict(use_wind=True,  use_mass=True,  use_elev=False)),
        ("4",    f"Wind+Elev",                       dict(use_wind=True,  use_mass=False, use_elev=True)),
        ("5",    f"Wind+Mass+Elev",                  dict(use_wind=True,  use_mass=True,  use_elev=True)),
    ]

    best_result = None
    best_n = 0

    for suffix, note, flags in cases:
        if suffix == "all":
            filtered = constraints
        else:
            filtered = _apply_filters(constraints, log=log, **flags)

        if len(filtered) < 2:
            log.warning("过滤组合 %s 约束不足 (%d)", suffix, len(filtered))
            continue

        res = identify_parameters(filtered)
        if res["cluster_labels"] is not None:
            for i, c in enumerate(filtered):
                c["cluster"] = int(res["cluster_labels"][i])

        title = f"{label} | {note} | n={len(filtered)}"
        if res["c_rr_identified"] is not None:
            title += f" | C_rr={res['c_rr_identified']:.6f}, C_dA={res['c_da_identified']:.2f}"

        plot_comprehensive_analysis(
            res, title,
            save_path=str(results_dir / f"{vehicle_reg}_analysis_{suffix}.png"),
        )
        log.info("图 %s: n=%d, C_rr=%s, C_dA=%s",
                 suffix, len(filtered),
                 f"{res['c_rr_identified']:.6f}" if res['c_rr_identified'] else "N/A",
                 f"{res['c_da_identified']:.2f}" if res['c_da_identified'] else "N/A")

        # 记录最佳结果（最多约束的全过滤组合）
        if suffix == "5" and res["c_rr_identified"] is not None:
            best_result = res
            best_n = len(filtered)
        elif suffix == "all" and best_result is None:
            best_result = res
            best_n = len(filtered)

    # 9. 保存 JSON 结果
    summary = {
        "vehicle_reg": vehicle_reg,
        "make": make,
        "model": vehicle_cfg.get("model", ""),
        "date_range": f"{ds} ~ {de}",
        "max_torque_nm": max_torque_nm,
        "drive_train_efficiency": drive_train_efficiency,
        "energy_mode": energy_mode,
        "n_legs": len(dfs),
        "n_segments": len(segments),
        "n_constraints_total": len(constraints),
        "unfiltered": {
            "c_rr": result_all["c_rr_identified"],
            "c_da": result_all["c_da_identified"],
            "n_cluster_0": result_all["n_cluster_0"],
            "n_cluster_1": result_all["n_cluster_1"],
        },
    }
    # 添加全过滤结果
    if best_result:
        summary["best_filtered"] = {
            "c_rr": best_result["c_rr_identified"],
            "c_da": best_result["c_da_identified"],
            "n_constraints": best_n,
        }

    with open(results_dir / f"{vehicle_reg}_result.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    log.info("辨识完成: %s", vehicle_reg)
    return summary


def main():
    load_dotenv(str(cfg.JOLT_ROOT / ".env"))

    p = argparse.ArgumentParser(description="JOLT EV C_rr / C_dA 参数辨识 (基于 SRF Logger 数据)")
    p.add_argument("--veh", type=str, default=None, help="车牌号")
    p.add_argument("--all", action="store_true", help="辨识所有有 Logger 的车辆 (IDENTIFICATION_CONFIGS)")
    p.add_argument("--ds", type=str, default=None, help="开始日期 (默认从 IDENTIFICATION_CONFIGS)")
    p.add_argument("--de", type=str, default=None, help="结束日期 (默认从 IDENTIFICATION_CONFIGS)")
    p.add_argument("--probe", action="store_true", help="仅探测 Logger 通道")
    p.add_argument("--no-download", action="store_true", help="不下载，用已有 CSV")
    p.add_argument("--max-torque", type=float, default=None, help="覆盖电机最大扭矩 (Nm)")
    p.add_argument("--efficiency", type=float, default=cfg.MOTOR_EFFICIENCY, help="传动效率")
    p.add_argument("--seg-distance", type=float, default=None, help="巡航段距离 (m)")
    p.add_argument("--min-speed", type=float, default=None, help="最小平均速度 (km/h)")
    args = p.parse_args()

    vehicles = cfg.load_vehicle_configs()

    if args.veh:
        target_regs = [args.veh.upper()]
    elif args.all:
        # 仅辨识 IDENTIFICATION_CONFIGS 中有的车辆
        target_regs = list(cfg.IDENTIFICATION_CONFIGS.keys())
    else:
        p.error("请指定 --veh 或 --all")
        return

    log = setup_logging(args.veh or "all")

    # SRF 客户端
    srf = None
    if not args.no_download or args.probe:
        from jolt_toolkit.vehicle_params_identificator.data_loader import _make_srf_client
        srf = _make_srf_client()

    results = {}
    for reg in target_regs:
        vcfg = vehicles.get(reg)
        if vcfg is None:
            log.warning("车辆 %s 不在 vehicles.json 中", reg)
            continue

        if args.probe:
            probe_vehicle(reg, vcfg["srf_reg"], srf=srf)
            continue

        # 从 IDENTIFICATION_CONFIGS 获取参数
        id_cfg = cfg.IDENTIFICATION_CONFIGS.get(reg, {})
        max_torque = args.max_torque or id_cfg.get("max_torque_nm")
        ds = args.ds or (id_cfg.get("date_range", ("2024-01-01",))[0])
        de = args.de or (id_cfg.get("date_range", (None, "2026-03-01"))[1])

        log.info("=" * 60)
        log.info("辨识: %s (%s %s)", reg, vcfg.get("make", ""), vcfg.get("model", ""))
        log.info("日期范围: %s ~ %s, max_torque: %s Nm", ds, de, max_torque)
        log.info("=" * 60)

        result = run_single_vehicle(
            reg, vcfg, ds, de,
            srf=srf,
            download=not args.no_download,
            max_torque_nm=max_torque,
            drive_train_efficiency=args.efficiency,
            seg_distance_m=args.seg_distance,
            min_avg_speed=args.min_speed,
            log=log,
        )
        if result is not None:
            results[reg] = result

    # 汇总
    if results and not args.probe:
        summary_path = cfg.RESULTS_DIR / "summary.json"
        cfg.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 90)
        print(f"{'Vehicle':<12} {'Make':<15} {'Mode':<8} {'C_rr':>10} {'C_dA':>8} {'Segs':>6} {'Legs':>6}")
        print("-" * 90)
        for reg, r in results.items():
            bf = r.get("best_filtered") or r.get("unfiltered", {})
            crr = f"{bf['c_rr']:.6f}" if bf.get("c_rr") is not None else "N/A"
            cda = f"{bf['c_da']:.2f}" if bf.get("c_da") is not None else "N/A"
            print(f"{reg:<12} {r.get('make',''):<15} {r['energy_mode']:<8} {crr:>10} {cda:>8} "
                  f"{r['n_constraints_total']:>6} {r['n_legs']:>6}")
        print("=" * 90)


if __name__ == "__main__":
    main()
