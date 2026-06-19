"""
批量生成报告。两种模式：

1) 配置文件模式（默认）—— 按 test_data_config.json 里的车队 + 日期区间逐个生成：
     python batch_generate.py                 # 普通模式
     python batch_generate.py --fast          # 跳过 Charger/Logger
     python batch_generate.py --debug         # 生成验证图 + 原始 CSV
     python batch_generate.py --raw-only      # 只存 raw CSV + HTML，不画烤版图（提速）
     python batch_generate.py --debug --fast  # 常用测试组合
     python batch_generate.py --veh YK73WFN   # 仅生成配置文件里的某辆车

2) 自动切分模式 —— 给单车一个总起止区间，**默认按气象季度**（DJF/MAM/JJA/SON，含末日、
   无重叠）切成多份逐个生成；末段按 date_end 裁剪。--months N 是等长切分逃生口。
   触发条件：同时给出 --veh / --ds / --de（此时忽略配置文件）。
     python batch_generate.py --veh YK73WFN --ds 2024-06-01 --de 2026-06-09            # 默认气象季度切分
     python batch_generate.py --veh YK73WFN --ds 2024-06-01 --de 2025-12-01 --months 1 # 每月一份（等长逃生口）
   想要单份覆盖整段（不切分），直接用 generate_report.py：
     python generate_report.py -veh YK73WFN -ds 2024-06-01 -de 2026-06-09

输出目录默认 ./excel_report_database/<package_version>，可用 --out-dir 覆盖。版本号由
已安装的 jolt_toolkit 决定，整个 conda env 共享，并行会话会互相覆盖——批量生成前务必
先与用户确认版本号与输出目录一致（见 SKILL.md 的前置确认规则）。
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from jolt_toolkit import __version__
from jolt_toolkit.report_generator._generator import JOLTReportGenerator


def _met_quarter_start_on_or_before(ts: pd.Timestamp) -> pd.Timestamp:
    """返回 ``ts`` 当天或之前最近的气象季度起始日（12-01 / 03-01 / 06-01 / 09-01）。"""
    candidates = [
        pd.Timestamp(ts.year - 1, 12, 1),
        pd.Timestamp(ts.year, 3, 1),
        pd.Timestamp(ts.year, 6, 1),
        pd.Timestamp(ts.year, 9, 1),
        pd.Timestamp(ts.year, 12, 1),
    ]
    return max(s for s in candidates if s <= ts)


def _next_met_quarter_start(qstart: pd.Timestamp) -> pd.Timestamp:
    """给定一个气象季度起始日，返回下一个季度的起始日（exclusive 边界）。"""
    if qstart.month == 12:
        return pd.Timestamp(qstart.year + 1, 3, 1)
    return pd.Timestamp(qstart.year, qstart.month + 3, 1)


def split_into_meteorological_quarters(
    date_start: str, date_end: str
) -> list[tuple[str, str]]:
    """把 [date_start, date_end] 按气象季度切成连续多段，**含末日、无重叠**。

    气象季度边界固定在 12-01（DJF 冬）/ 03-01（MAM 春）/ 06-01（JJA 夏）/
    09-01（SON 秋）。每段 = ``[季度起始, 下一季度起始的前一天]``，即 end 是**含末日**
    （例：12-01 → 02-28/29、03-01 → 05-31、06-01 → 08-31、09-01 → 11-30；闰年
    02-29 由 pandas 自动处理）。首段从 ``date_start`` 起、末段到 ``date_end`` 止
    （首尾按数据范围裁剪）。

    含末日 end 不丢数据由 :func:`report_generator.data_fetcher.fetch_events` 保证：
    它把 date_end 与 ``datetime.time.max`` 组合（23:59:59.999999）后再下发 SRF 查询，
    故"含末日"标签天然覆盖该日全天；查询 filter 作用在 ``leg.start_time`` 上，相邻段
    （前段含末日、后段次日 00:00 起）不会把同一条 leg 重复计入两份报告。

    Args:
        date_start: 总起始日期 (YYYY-MM-DD)。
        date_end:   总结束日期 (YYYY-MM-DD，含末日)，需不早于 ``date_start``。

    Returns:
        ``[(start_str, end_str), ...]``，日期均为 ``YYYY-MM-DD``（含末日）。

    Raises:
        ValueError: ``date_end < date_start``。
    """
    start = pd.Timestamp(date_start)
    end = pd.Timestamp(date_end)
    if end < start:
        raise ValueError(f"date_end ({date_end}) 不能早于 date_start ({date_start})")

    periods: list[tuple[str, str]] = []
    qstart = _met_quarter_start_on_or_before(start)
    while qstart <= end:
        nxt = _next_met_quarter_start(qstart)            # 下一季度起始（exclusive）
        seg_start = max(qstart, start)                   # 首段裁剪到 date_start
        seg_end = min(nxt - pd.Timedelta(days=1), end)   # 含末日；末段裁剪到 date_end
        if seg_start <= seg_end:
            periods.append(
                (seg_start.strftime("%Y-%m-%d"), seg_end.strftime("%Y-%m-%d"))
            )
        qstart = nxt
    return periods


def split_into_periods(
    date_start: str, date_end: str, months: int | None = None
) -> list[tuple[str, str]]:
    """把 [date_start, date_end] 切成连续多段，**含末日、无重叠**。

    默认（``months=None``）按**气象季度**切分（DJF/MAM/JJA/SON，见
    :func:`split_into_meteorological_quarters`）——这是全队报告的标准跨度。

    ``months=N`` 是等长切分的逃生口：每份覆盖 ``N`` 个日历月，同样**含末日、无重叠**
    （每段 = ``[cur, cur + N 个月 - 1 天]``，末段裁剪到 ``date_end``）。

    Args:
        date_start: 总起始日期 (YYYY-MM-DD)。
        date_end:   总结束日期 (YYYY-MM-DD，含末日)，需不早于 ``date_start``。
        months:     ``None`` → 气象季度（默认）；``>= 1`` → 等长 N 月切分。

    Returns:
        ``[(start_str, end_str), ...]``，日期均为 ``YYYY-MM-DD``（含末日）。

    Raises:
        ValueError: ``months`` 给定且 ``< 1``，或 ``date_end < date_start``。
    """
    if months is None:
        return split_into_meteorological_quarters(date_start, date_end)
    if months < 1:
        raise ValueError(f"months 必须 >= 1，收到 {months}")

    start = pd.Timestamp(date_start)
    end = pd.Timestamp(date_end)
    if end < start:
        raise ValueError(f"date_end ({date_end}) 不能早于 date_start ({date_start})")

    periods: list[tuple[str, str]] = []
    cur = start
    while cur <= end:
        nxt = cur + pd.DateOffset(months=months)         # 下一段起始（exclusive）
        seg_end = min(nxt - pd.Timedelta(days=1), end)   # 含末日；末段裁剪到 date_end
        periods.append((cur.strftime("%Y-%m-%d"), seg_end.strftime("%Y-%m-%d")))
        cur = nxt
    return periods


def _load_vehicles_from_config(cfg_path: Path, only_veh: str | None) -> list[dict]:
    """从 test_data_config.json 读取车队（可选只取一辆）。"""
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    vehicles = cfg["vehicles"]
    if only_veh:
        vehicles = [v for v in vehicles if v["registration"] == only_veh.upper()]
    return vehicles


def main() -> int:
    parser = argparse.ArgumentParser(
        description="批量生成报告（配置文件模式 / 单车自动按月切分模式）"
    )
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parent / "test_data_config.json"),
        help="配置文件路径（配置文件模式）",
    )
    parser.add_argument("--debug", action="store_true", help="生成验证图和原始 CSV")
    parser.add_argument(
        "--raw-only",
        dest="raw_only",
        action="store_true",
        help="只落盘 raw telematics CSV + inspect HTML（等同 --debug 的数据落盘），"
             "但跳过 generate 阶段烤入标注的 validation 图。用于「批量重生成 + 随后 "
             "overlay regenerate 重画新样式图」工作流，避免把图画两遍。",
    )
    parser.add_argument("--fast", action="store_true", help="跳过 Charger/Logger 数据")
    parser.add_argument(
        "--veh",
        type=str,
        default=None,
        help="指定车辆（车牌号）。配置文件模式下仅生成该车；与 --ds/--de 同用则进入自动切分模式",
    )
    parser.add_argument(
        "-ds",
        "--ds",
        dest="ds",
        type=str,
        default=None,
        help="自动切分模式：总起始日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "-de",
        "--de",
        dest="de",
        type=str,
        default=None,
        help="自动切分模式：总结束日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=None,
        help="自动切分模式的等长切分逃生口：每份报告跨度（日历月数）。不传则默认按"
             "气象季度（DJF/MAM/JJA/SON，含末日、无重叠）切分。仅在 --ds/--de 模式下生效",
    )
    parser.add_argument(
        "--out-dir",
        "--report-output-folder",
        dest="out_dir",
        type=str,
        default=None,
        help=("输出目录，默认 ./excel_report_database/<package_version>。"
              "版本号全 conda env 共享，批量前请先与用户确认版本与目录"),
    )
    args = parser.parse_args()

    load_dotenv(".env")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        force=True,
    )

    # ── 组装待生成的 (reg, ranges) 列表 ───────────────────────────────────
    adhoc = bool(args.veh and args.ds and args.de)
    if adhoc:
        # 自动切分模式：忽略配置文件，默认按气象季度（--months 给定则等长 N 月）切分单车总区间。
        try:
            ranges = split_into_periods(args.ds, args.de, months=args.months)
        except ValueError as exc:
            logging.error("日期切分失败: %s", exc)
            return 1
        vehicles = [{"registration": args.veh.upper(), "ranges": [
            {"start": s, "end": e} for s, e in ranges]}]
        split_desc = (
            "气象季度" if args.months is None else f"每 {args.months} 个月"
        )
        logging.info(
            "自动切分模式: %s  %s ~ %s  按%s（含末日、无重叠）→ %d 份报告",
            args.veh.upper(), args.ds, args.de, split_desc, len(ranges),
        )
    else:
        if (args.ds or args.de) and not (args.veh and args.ds and args.de):
            logging.error("自动切分模式需要同时提供 --veh / --ds / --de")
            return 1
        cfg_path = Path(args.config)
        if not cfg_path.exists():
            logging.error("配置文件不存在: %s", cfg_path)
            return 1
        vehicles = _load_vehicles_from_config(cfg_path, args.veh)
        if not vehicles:
            logging.error("车辆 %s 不在配置文件中", args.veh)
            return 1

    # 输出目录默认由已安装 jolt_toolkit 版本号决定；可用 --out-dir 覆盖。
    out_dir = args.out_dir or f"./excel_report_database/{__version__}"

    # --raw-only：仍落盘 raw CSV + HTML（需 debug_mode 数据落盘），但跳过烤版图。
    debug_mode = args.debug or args.raw_only
    save_figures = not args.raw_only

    generator = JOLTReportGenerator(
        report_output_folder=out_dir,
        overwrite_existing_report=True,
        debug_mode=debug_mode,
        fast_mode=args.fast,
        save_figures=save_figures,
    )

    total = sum(len(v["ranges"]) for v in vehicles)
    done = 0
    failed = []
    t0 = time.time()

    logging.info("JOLT Report Generator v%s — 批量模式", __version__)
    logging.info("输出目录: %s", out_dir)
    logging.info("共 %d 辆车, %d 个日期区间", len(vehicles), total)

    for veh in vehicles:
        reg = veh["registration"]
        for r in veh["ranges"]:
            done += 1
            ds, de = r["start"], r["end"]
            logging.info("[%d/%d] %s  %s ~ %s", done, total, reg, ds, de)
            try:
                generator.generate_report(
                    vehicle_registration=reg,
                    date_start=ds,
                    date_end=de,
                )
            except Exception:
                logging.exception("生成失败: %s %s~%s", reg, ds, de)
                failed.append(f"{reg} {ds}~{de}")

    elapsed = time.time() - t0
    logging.info("批量生成完成: %d/%d 成功, 耗时 %.1f 秒", done - len(failed), total, elapsed)
    if failed:
        logging.warning("失败列表:\n  %s", "\n  ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
