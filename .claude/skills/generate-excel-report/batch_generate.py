"""
Batch report generation. Two modes:

1) Config-file mode (default) — generate one report per vehicle + date range listed
   in test_data_config.json:
     python batch_generate.py                 # normal mode
     python batch_generate.py --fast          # skip Charger/Logger
     python batch_generate.py --debug         # validation figures + raw CSV
     python batch_generate.py --raw-only      # raw CSV + HTML only, no baked figures (faster)
     python batch_generate.py --debug --fast  # common test combination
     python batch_generate.py --veh YK73WFN   # only one vehicle from the config file

2) Auto-split mode — give a single vehicle one overall start/end range; by default it
   is split into **meteorological quarters** (DJF/MAM/JJA/SON, inclusive end,
   non-overlapping) and generated one report per segment; the last segment is clipped
   to date_end. --months N is the equal-length escape hatch.
   Triggered by giving --veh / --ds / --de together (the config file is then ignored).
     python batch_generate.py --veh YK73WFN --ds 2024-06-01 --de 2026-06-09            # default quarter split
     python batch_generate.py --veh YK73WFN --ds 2024-06-01 --de 2025-12-01 --months 1 # one report per month (equal-length escape hatch)
   For a single report covering the whole range (no split), use generate_report.py directly:
     python generate_report.py -veh YK73WFN -ds 2024-06-01 -de 2026-06-09

The output dir defaults to ./excel_report_database/<package_version>, overridable with
--out-dir. The version comes from the installed jolt_toolkit, shared across the whole
conda env, so parallel sessions can overwrite each other — before a batch run, always
confirm the version and output dir with the user (see the pre-run confirmation rules
in SKILL.md).
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
    """Return the latest meteorological-quarter start on or before ``ts`` (12-01 / 03-01 / 06-01 / 09-01)."""
    candidates = [
        pd.Timestamp(ts.year - 1, 12, 1),
        pd.Timestamp(ts.year, 3, 1),
        pd.Timestamp(ts.year, 6, 1),
        pd.Timestamp(ts.year, 9, 1),
        pd.Timestamp(ts.year, 12, 1),
    ]
    return max(s for s in candidates if s <= ts)


def _next_met_quarter_start(qstart: pd.Timestamp) -> pd.Timestamp:
    """Given a meteorological-quarter start, return the next quarter's start (exclusive boundary)."""
    if qstart.month == 12:
        return pd.Timestamp(qstart.year + 1, 3, 1)
    return pd.Timestamp(qstart.year, qstart.month + 3, 1)


def split_into_meteorological_quarters(
    date_start: str, date_end: str
) -> list[tuple[str, str]]:
    """Split [date_start, date_end] into consecutive meteorological quarters — **inclusive end, non-overlapping**.

    Meteorological-quarter boundaries are fixed at 12-01 (DJF winter) / 03-01 (MAM
    spring) / 06-01 (JJA summer) / 09-01 (SON autumn). Each segment =
    ``[quarter start, day before the next quarter start]``, i.e. the end is
    **inclusive** (e.g. 12-01 → 02-28/29, 03-01 → 05-31, 06-01 → 08-31,
    09-01 → 11-30; leap-year 02-29 is handled automatically by pandas). The first
    segment starts at ``date_start`` and the last ends at ``date_end`` (first and
    last clipped to the data range).

    That an inclusive end loses no data is guaranteed by
    :func:`report_generator.data_fetcher.fetch_events`: it combines date_end with
    ``datetime.time.max`` (23:59:59.999999) before issuing the SRF query, so the
    "inclusive end" label naturally covers that whole day; the query filter acts on
    ``leg.start_time``, so adjacent segments (previous segment's inclusive end day
    vs the next segment starting 00:00 the following day) never count the same leg
    into two reports.

    Args:
        date_start: Overall start date (YYYY-MM-DD).
        date_end:   Overall end date (YYYY-MM-DD, inclusive); must not be earlier
            than ``date_start``.

    Returns:
        ``[(start_str, end_str), ...]``, all dates ``YYYY-MM-DD`` (inclusive end).

    Raises:
        ValueError: ``date_end < date_start``.
    """
    start = pd.Timestamp(date_start)
    end = pd.Timestamp(date_end)
    if end < start:
        raise ValueError(f"date_end ({date_end}) 不能早于 date_start ({date_start})")

    periods: list[tuple[str, str]] = []
    qstart = _met_quarter_start_on_or_before(start)
    while qstart <= end:
        nxt = _next_met_quarter_start(qstart)            # next quarter start (exclusive)
        seg_start = max(qstart, start)                   # first segment clipped to date_start
        seg_end = min(nxt - pd.Timedelta(days=1), end)   # inclusive end; last segment clipped to date_end
        if seg_start <= seg_end:
            periods.append(
                (seg_start.strftime("%Y-%m-%d"), seg_end.strftime("%Y-%m-%d"))
            )
        qstart = nxt
    return periods


def split_into_periods(
    date_start: str, date_end: str, months: int | None = None
) -> list[tuple[str, str]]:
    """Split [date_start, date_end] into consecutive segments — **inclusive end, non-overlapping**.

    By default (``months=None``) split into **meteorological quarters**
    (DJF/MAM/JJA/SON, see :func:`split_into_meteorological_quarters`) — the standard
    span for fleet reports.

    ``months=N`` is the equal-length escape hatch: each report covers ``N`` calendar
    months, likewise **inclusive-end and non-overlapping** (each segment =
    ``[cur, cur + N months - 1 day]``, the last clipped to ``date_end``).

    Args:
        date_start: Overall start date (YYYY-MM-DD).
        date_end:   Overall end date (YYYY-MM-DD, inclusive); must not be earlier
            than ``date_start``.
        months:     ``None`` → meteorological quarters (default); ``>= 1`` →
            equal-length N-month split.

    Returns:
        ``[(start_str, end_str), ...]``, all dates ``YYYY-MM-DD`` (inclusive end).

    Raises:
        ValueError: ``months`` given and ``< 1``, or ``date_end < date_start``.
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
        nxt = cur + pd.DateOffset(months=months)         # next segment start (exclusive)
        seg_end = min(nxt - pd.Timedelta(days=1), end)   # inclusive end; last segment clipped to date_end
        periods.append((cur.strftime("%Y-%m-%d"), seg_end.strftime("%Y-%m-%d")))
        cur = nxt
    return periods


def _load_vehicles_from_config(cfg_path: Path, only_veh: str | None) -> list[dict]:
    """Load the fleet from test_data_config.json (optionally a single vehicle only)."""
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    vehicles = cfg["vehicles"]
    if only_veh:
        vehicles = [v for v in vehicles if v["registration"] == only_veh.upper()]
    return vehicles


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch report generation (config-file mode / single-vehicle auto-split mode)"
    )
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parent / "test_data_config.json"),
        help="Path to the config file (config-file mode)",
    )
    parser.add_argument("--debug", action="store_true", help="Generate validation figures and raw CSV")
    parser.add_argument(
        "--raw-only",
        dest="raw_only",
        action="store_true",
        help="Save only the raw telematics CSV + inspect HTML (same data output as "
             "--debug), but skip baking the annotated validation figures during the "
             "generate stage. For the 'batch regenerate + subsequent overlay-regenerate "
             "redraw with the new style' workflow, to avoid plotting the figures twice.",
    )
    parser.add_argument("--fast", action="store_true", help="Skip Charger/Logger data")
    parser.add_argument(
        "--veh",
        type=str,
        default=None,
        help="Select one vehicle (registration). In config-file mode, generate only this "
             "vehicle; combined with --ds/--de it enters auto-split mode",
    )
    parser.add_argument(
        "-ds",
        "--ds",
        dest="ds",
        type=str,
        default=None,
        help="Auto-split mode: overall start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "-de",
        "--de",
        dest="de",
        type=str,
        default=None,
        help="Auto-split mode: overall end date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=None,
        help="Equal-length escape hatch for auto-split mode: span of each report "
             "(calendar months). If omitted, defaults to meteorological-quarter splits "
             "(DJF/MAM/JJA/SON, inclusive end, non-overlapping). Only effective in "
             "--ds/--de mode",
    )
    parser.add_argument(
        "--out-dir",
        "--report-output-folder",
        dest="out_dir",
        type=str,
        default=None,
        help=("Output folder, defaults to ./excel_report_database/<package_version>. "
              "The version is shared across the whole conda env — confirm the version "
              "and output dir with the user before a batch run"),
    )
    args = parser.parse_args()

    load_dotenv(".env")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        force=True,
    )

    # ── Assemble the (reg, ranges) list to generate ──────────────────────
    adhoc = bool(args.veh and args.ds and args.de)
    if adhoc:
        # Auto-split mode: ignore the config file; split the single vehicle's overall
        # range into meteorological quarters by default (equal-length N-month segments
        # when --months is given).
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

    # The output dir defaults to the installed jolt_toolkit version; override with --out-dir.
    out_dir = args.out_dir or f"./excel_report_database/{__version__}"

    # --raw-only: still writes the raw CSV + HTML (needs debug_mode), but skips the baked figures.
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
