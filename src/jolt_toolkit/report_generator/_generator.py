"""
report_generator.py
=========================
编排 fetch -> segment -> write 主流程。
使用 segment_algorithms 进行统一充放电分段，
通过 report_builder 生成 Excel 报告和可选的验证图。
"""

import io
import os
import re
import datetime
import logging
from pathlib import Path
from time import perf_counter

import pandas as pd
from srf_client import paging
from tqdm import tqdm

from jolt_toolkit import __version__
from jolt_toolkit.report_generator.paths import get_cache_dir, get_srf_api_root
from jolt_toolkit.report_generator.data_class import ServerData
from jolt_toolkit.report_generator.data_fetcher import fetch_events
from jolt_toolkit.report_generator.segment_algorithms import (
    run_segment_detection,
    resolve_mass_agg,
    VEHICLE_CONFIG,
    PIPELINE_CONFIGS,
    SOC_COL,
    TIME_COL,
    _ANCHOR_PRIVATE_KEYS,
)
from jolt_toolkit.report_generator.report_builder import (
    HEADERS,
    DIESEL_HEADERS,
    _seg_to_row,
    _insert_stop_rows,
    _write_excel_report,
    _write_html_viewer,
)
from jolt_toolkit.report_generator.diesel_pipeline import (
    process_diesel_leg,
)
from jolt_toolkit.report_generator.operators import derive_leg_operator
from jolt_toolkit.report_generator.xlsx_patch_common import make_srf_client
from jolt_toolkit.report_generator.capacity import (  # noqa: F401
    _row_idx,
    _IDX_LEG_TYPE, _IDX_SOC_CHANGE, _IDX_ENERGY, _IDX_DISTANCE, _IDX_EPERF,
    _IDX_CAP, _IDX_ESOURCE, _IDX_BPOWER, _IDX_DURATION, _IDX_ELEV, _IDX_MASS,
    _IDX_EPERF_CORR, _IDX_EPERF_KIN, _IDX_EP_EXCL_AUX, _IDX_START,
    CAP_WINDOW_HALF_DAYS, _DAY_NS, MIN_DONORS,
    SOC_FALLBACK_MIN_DSOC_PCT, SOC_FALLBACK_MIN_DEV,
    _resolve_soc_fallback, _cap_is_valid, _soc_weighted_cap,
    _period_capacity_from_rows, _recompute_weighted_capacity,
    _correct_effective_capacity, _persist_effective_capacity,
)

logger = logging.getLogger(__name__)


# ── Logger 值转换：srf_client.pandas.to_numeric 的超集 ───────────────────────
# srf_client 默认的 to_numeric 只处理数字和 "NaN" 字符串；遇到 J1939 布尔字段
# （如 CCVS cruise control active / brake switch / clutch switch 的 "true"/"false"）
# 会无差别返回 math.nan，导致这些列在 Logger CSV 中全部丢失。
# 这里把布尔字符串映射到 0/1，保留对其他值的原有行为，是一个严格超集。
_LOGGER_BOOL_TRUE = frozenset({'true', 'True', 'TRUE'})
_LOGGER_BOOL_FALSE = frozenset({'false', 'False', 'FALSE'})


def _logger_to_numeric(v: str):
    """布尔感知版本的数值转换器，用于 leg.get_data_frame(conversion=...)."""
    import math
    if v in _LOGGER_BOOL_TRUE:
        return 1
    if v in _LOGGER_BOOL_FALSE:
        return 0
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return math.nan


def _ensure_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    """确保 DataFrame 索引为 UTC 时区。"""
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    else:
        df.index = df.index.tz_convert('UTC')
    return df


def _load_logger_channel(
    logger_legs: list,
    channels: list[tuple[str, str | tuple[str, ...]]],
    *,
    target_col: str,
    desc: str,
) -> pd.DataFrame | None:
    """从 Logger legs 加载指定通道数据的通用函数。

    Args:
        logger_legs: Logger leg 对象列表
        channels:    按优先级排列的 (channel_name, column_name_or_candidates) 元组列表。
                     column_name 可为单个字符串或多个候选列名的元组（按优先级尝试）。
        target_col:  输出 DataFrame 的列名
        desc:        tqdm 进度条描述
    Returns:
        合并后的 DataFrame（索引为 UTC 时间戳）或 None
    """
    dfs = []
    for lg in tqdm(logger_legs, desc=desc, leave=False):
        try:
            avail = lg.types
            for channel, col_spec in channels:
                if channel in avail:
                    df_ch = lg.get_data_frame(channel, resolution='1s')
                    # col_spec 支持单列名或多个候选列名
                    candidates = (col_spec,) if isinstance(col_spec, str) else col_spec
                    for col in candidates:
                        if col in df_ch.columns:
                            dfs.append(df_ch[[col]].rename(columns={col: target_col}))
                            break
                    break  # 使用第一个匹配的通道
        except Exception:
            pass
    if not dfs:
        return None
    result = pd.concat(dfs).sort_index()
    return _ensure_utc_index(result)


class JOLTReportGenerator:
    """从 SRF API 获取数据，运行分段算法，生成 Excel 报告。"""

    def __init__(
        self,
        report_output_folder="./excel_report_database",
        overwrite_existing_report=True,
        debug_mode=False,
        fast_mode=False,
        save_figures=True,
    ):
        """
        save_figures
            仅在 ``debug_mode=True`` 时有意义：是否在 generate 阶段绘制烤入标注的
            validation 图。设为 ``False`` 时仍落盘 raw telematics CSV + inspect HTML，
            但跳过画图（图稍后由 :class:`ValidationGenerator` overlay regenerate 统一
            重画新样式，避免画两遍）。raw CSV 落盘与画图本就解耦（前者 gated on
            ``debug_mode``，后者 gated on ``debug_mode and save_figures``）。
        """
        self.srf_data = self._make_srf_data(
            api_key=os.environ.get("SRF_API_KEY"),
            root=get_srf_api_root(),
            cache_dir=str(get_cache_dir()),
            verify=True,
        )
        self.report_output_folder = report_output_folder
        self.overwrite_existing_report = overwrite_existing_report
        self.debug_mode = debug_mode
        self.fast_mode = fast_mode
        self.save_figures = save_figures

    def generate_report(self, vehicle_registration, date_start, date_end):
        """为指定车辆和日期范围生成 JOLT Excel 报告。返回 Excel 路径或 None。"""
        time_start = perf_counter()
        logger.info("开始生成报告: %s  %s ~ %s", vehicle_registration, date_start, date_end)

        reg = vehicle_registration.replace(" ", "")
        cfg = VEHICLE_CONFIG.get(reg)
        if cfg is None:
            raise ValueError(
                f"车辆 {vehicle_registration!r} 未在 jolt_toolkit/report_generator/configs/vehicles.json 中注册"
            )
        reg_srf = cfg["srf_reg"]
        # 报告周期串（YYYYMMDD_YYYYMMDD），与季度报告 / quarterly schema key 1:1
        period_key = f"{date_start.replace('-', '')}_{date_end.replace('-', '')}"
        # v2.2.2: 柴油车没有电池，跳过所有容量相关字段
        is_diesel = str(cfg.get("fuel_type", "")).upper() == "DIESEL"
        nominal_kwh = cfg.get("nominal_kwh") if not is_diesel else None
        srf_capacity_kwh = cfg.get("srf_capacity_kwh", nominal_kwh)
        # effective_capacity_kwh: 全量可靠季度的 donor 加权平均（v2.2.6+ schema）；
        # 未计算时为 None，回退到 srf_capacity。
        eff_cap_kwh = cfg.get("effective_capacity_kwh")
        # SOC 估算容量种子（v2.2.6+）：优先取**本报告周期**且可靠（n ≥ MIN_DONORS）的
        # 季度容量，否则全量加权平均 effective_capacity_kwh，再否则 srf_capacity /
        # nominal。让每期 SOC 种子用该期对应容量（随后仍被逐 leg time-local 修正覆盖，
        # 故仅影响 window 全无 donor 时的兜底取值，不改 measured-leg 数值）。
        quarterly_cfg = cfg.get("effective_capacity_quarterly") or {}
        this_q = quarterly_cfg.get(period_key)
        if (this_q and this_q.get("n", 0) >= MIN_DONORS
                and this_q.get("kwh") is not None):
            soc_est_cap = this_q["kwh"]
        else:
            soc_est_cap = eff_cap_kwh or srf_capacity_kwh or nominal_kwh
        altitude_col = cfg.get("altitude_col")
        speed_col = cfg.get("speed_col", "wheel_based_speed")
        # v2.2.6: per-segment 质量聚合方法（vehicle > pipeline > 默认 'mean'）。
        # 解析一次后透传给每个 _seg_to_row，使 Excel 列与校验图同口径稳健估计。
        mass_agg = resolve_mass_agg(
            reg, PIPELINE_CONFIGS.get(cfg.get("pipeline", "default_soc"))
        )
        cap_lo = nominal_kwh * 0.5 if nominal_kwh else None
        cap_hi = nominal_kwh * 2.0 if nominal_kwh else None

        out_dir = Path(self.report_output_folder) / reg
        out_dir.mkdir(parents=True, exist_ok=True)
        raw_dir = None
        if self.debug_mode:
            raw_dir = out_dir / "raw_telematics"
            raw_dir.mkdir(exist_ok=True)

        ds = datetime.datetime.strptime(date_start, "%Y-%m-%d")
        de = datetime.datetime.strptime(date_end, "%Y-%m-%d")
        server_data = fetch_events(
            vehicle_registration=reg_srf, date_start=ds,
            date_end=de, srf_data=self.srf_data,
        )
        time_fetch = perf_counter()
        logger.info("数据拉取完成，耗时 %.2f 秒", time_fetch - time_start)

        charger_windows, charger_objects = self._collect_charger_windows(
            server_data)

        (logger_windows, logger_legs, logger_legs_by_src,
         fps_legs) = self._collect_legs(server_data, is_diesel, charger_windows)

        if self.debug_mode:
            self._save_charger_data(charger_objects, out_dir)
            for src_name, src_legs in logger_legs_by_src.items():
                self._save_logger_data(src_legs, out_dir, source=src_name)

        (logger_speed_all, logger_mass_all, logger_acc_pedal_all,
         logger_dec_pedal_all) = self._preload_logger_channels(
            logger_legs, is_diesel)

        charger_meter_all = self._preload_charger_meter(charger_objects)

        all_rows = []
        cumulative_km = 0.0
        home_point = None

        # ── 运营商解析（v2.2.5 恢复）────────────────────────────────────
        # SRF 为主：round-robin 车取 leg.trip.trial.description（per-leg 变），
        # 专属车取 vehicle.organisation.name（整车一致）。fetch 一次静态 org，
        # trial.description 按 trip URI 记忆化，op_acc 汇总一次性日志。
        srf_org_raw = None
        try:
            srf_org_raw = self.srf_data.vehicles.get(obj_id=reg_srf).organisation.name
        except Exception as exc:
            logger.debug("无法获取 vehicle.organisation.name: %s", exc)
        trial_cache: dict = {}
        op_acc: dict = {}

        # ── 柴油车分支：用 SRFLOGGER_V1 legs 作为主循环源 ────────────────
        if is_diesel:
            cumulative_km = self._process_diesel_legs(
                logger_legs, cfg, reg, out_dir, cumulative_km,
                srf_org_raw, trial_cache, op_acc, all_rows)
            # 跳过 FPS 主循环和 home_point / charger reclassification
            fps_legs = []

        cumulative_km, home_point = self._process_fps_legs(
            fps_legs, reg, out_dir, raw_dir, cap_lo, cap_hi,
            logger_speed_all, logger_mass_all, logger_acc_pedal_all,
            logger_dec_pedal_all, charger_meter_all, logger_legs,
            altitude_col, speed_col, mass_agg, srf_org_raw, trial_cache,
            op_acc, home_point, cumulative_km, all_rows)

        self._reclassify_home_charging(all_rows, home_point)

        time_process = perf_counter()
        logger.info("分段处理完成，耗时 %.2f 秒", time_process - time_fetch)

        all_rows.sort(key=lambda x: (
            pd.Timestamp(x[0]).tz_convert(None)
            if pd.Timestamp(x[0]).tzinfo is not None
            else pd.Timestamp(x[0])
        ))
        sorted_rows = [r for _, r in all_rows]

        if not sorted_rows:
            logger.warning("未检测到有效分段，跳过 Excel 生成")
            return None

        # 根据 fuel type 选择列布局（电车 HEADERS / 柴油 DIESEL_HEADERS）
        out_headers = DIESEL_HEADERS if is_diesel else HEADERS

        # ── 一次性运营商解析汇总 ────────────────────────────────────────
        if op_acc:
            unknown = op_acc.pop("_unknown", set())
            dist = ", ".join(
                f"{(k if k is not None else '<none>')}={v}"
                for k, v in sorted(op_acc.items(), key=lambda kv: -kv[1])
            )
            logger.info("运营商解析（按 leg 计）：%s", dist or "无")
            bad = {c for c in unknown if c is not None}
            if bad:
                logger.warning("运营商代码未在 KNOWN_OPERATOR_CODES 中：%s", ", ".join(sorted(bad)))
            if None in op_acc:
                logger.warning("有 %d 个 leg 无法确定运营商", op_acc[None])

        sorted_rows, period_cap_kwh, period_n, period_src = self._finalize_rows(
            sorted_rows, out_headers, is_diesel, cfg, soc_est_cap)

        return self._write_outputs(
            sorted_rows, out_headers, reg, ds, de, out_dir, is_diesel,
            period_cap_kwh, period_n, period_src, period_key,
            charger_windows, logger_legs, logger_windows, time_start)

    def _collect_charger_windows(self, server_data):
        """Collect charger transactions into (start, end, uri, energy_kwh) windows
        and keep the raw charger objects. fast_mode skips both."""
        charger_windows = []
        charger_objects = []
        if not self.fast_mode:
            try:
                for ct in paging.paged_items(server_data.charging_events):
                    try:
                        energy_kwh = None
                        if ct.start_meter is not None and ct.end_meter is not None:
                            energy_kwh = ct.end_meter - ct.start_meter
                        charger_windows.append((ct.start_time, ct.end_time, ct.uri, energy_kwh))
                        charger_objects.append(ct)
                    except AttributeError:
                        pass
            except Exception as exc:
                logger.warning("充电桩事件拉取失败: %s", exc)
        return charger_windows, charger_objects

    def _collect_legs(self, server_data, is_diesel, charger_windows):
        """Split legs into SRFLOGGER (logger) and FPS; fast_mode still collects the
        logger legs for diesel. Logs the per-source counts."""
        logger_windows = []
        logger_legs = []          # 所有 logger legs
        logger_legs_by_src = {}   # {source_str: [legs]} 按版本分组
        fps_legs = []
        # 柴油车的 legs 全部来自 SRFLOGGER_V1，fast_mode 也必须收集
        _collect_logger = (not self.fast_mode) or is_diesel
        try:
            for leg in paging.paged_items(server_data.legs):
                try:
                    src = leg.trip.source or ""
                    if _collect_logger and src.startswith("SRFLOGGER"):
                        logger_windows.append((leg.start_time, leg.end_time, leg.uri))
                        logger_legs.append(leg)
                        logger_legs_by_src.setdefault(src, []).append(leg)
                    elif src == "FPS":
                        fps_legs.append(leg)
                except AttributeError:
                    pass
        except Exception as exc:
            logger.warning("Legs 拉取失败: %s", exc)

        if self.fast_mode:
            logger.info("Fast 模式: 跳过 Charger/Logger 数据。FPS 腿数: %d", len(fps_legs))
        else:
            logger.info(
                "FPS 腿数: %d  充电桩: %d  Logger: %d (%s)",
                len(fps_legs), len(charger_windows), len(logger_windows),
                ", ".join(f"{k}={len(v)}" for k, v in logger_legs_by_src.items()) or "none",
            )
        return logger_windows, logger_legs, logger_legs_by_src, fps_legs

    def _preload_logger_channels(self, logger_legs, is_diesel):
        """Preload the speed / mass / accelerator / brake logger channels once for
        the whole period (EV only; diesel pulls its channels per leg)."""
        # ── 预加载 Logger 各通道数据 ─────────────────────────────────────
        # 柴油车的 diesel_pipeline 自行按 leg 拉取所需 channel，不依赖预加载。
        logger_speed_all = None
        logger_mass_all = None
        logger_acc_pedal_all = None
        logger_dec_pedal_all = None
        if logger_legs and not is_diesel:
            logger_speed_all = _load_logger_channel(
                logger_legs,
                [('CCVS', 'CCVS wheel based vehicle speed'),
                 ('2', '2 speed')],
                target_col='logger_speed',
                desc="加载 Logger speed",
            )
            if logger_speed_all is not None:
                logger.info("Logger speed 数据: %d 条", len(logger_speed_all))

            logger_mass_all = _load_logger_channel(
                logger_legs,
                [('CVW', 'CVW gross combination vehicle weight'),
                 ('VW', ('VW axle weight', 'VW cargo weight'))],
                target_col='logger_mass',
                desc="加载 Logger mass",
            )
            if logger_mass_all is not None:
                logger.info("Logger mass 数据: %d 条", len(logger_mass_all))

            logger_acc_pedal_all = _load_logger_channel(
                logger_legs,
                [('EEC2', 'EEC2 accelerator pedal position 1')],
                target_col='EEC2 accelerator pedal position 1',
                desc="加载 Logger EEC2",
            )
            if logger_acc_pedal_all is not None:
                logger.info("Logger EEC2 油门踏板数据: %d 条", len(logger_acc_pedal_all))

            logger_dec_pedal_all = _load_logger_channel(
                logger_legs,
                [('EBC1', 'EBC1 brake pedal position')],
                target_col='EBC1 brake pedal position',
                desc="加载 Logger EBC1",
            )
            if logger_dec_pedal_all is not None:
                logger.info("Logger EBC1 制动踏板数据: %d 条", len(logger_dec_pedal_all))
        return (logger_speed_all, logger_mass_all,
                logger_acc_pedal_all, logger_dec_pedal_all)

    def _preload_charger_meter(self, charger_objects):
        """Preload charger start/end meter readings into a time-indexed frame for
        the validation figures (debug_mode only)."""
        # ── 预加载 Charger meter 数据（用于 validation 图）──────────────
        charger_meter_all = None
        if self.debug_mode and charger_objects:
            meter_rows = []
            for ct in charger_objects:
                try:
                    if ct.start_meter is not None and ct.end_meter is not None:
                        ts_start = pd.Timestamp(ct.start_time)
                        ts_end   = pd.Timestamp(ct.end_time)
                        if ts_start.tzinfo is None:
                            ts_start = ts_start.tz_localize('UTC')
                        if ts_end.tzinfo is None:
                            ts_end = ts_end.tz_localize('UTC')
                        meter_rows.append({'time': ts_start, 'meter_kwh': ct.start_meter})
                        meter_rows.append({'time': ts_end,   'meter_kwh': ct.end_meter})
                except Exception:
                    pass
            if meter_rows:
                charger_meter_all = pd.DataFrame(meter_rows).sort_values('time')
                charger_meter_all = charger_meter_all.set_index('time')
        return charger_meter_all

    def _process_diesel_legs(self, logger_legs, cfg, reg, out_dir,
                             cumulative_km, srf_org_raw, trial_cache,
                             op_acc, all_rows):
        """Diesel branch: build rows from SRFLOGGER_V1 legs via process_diesel_leg,
        appending them to all_rows. Returns the updated cumulative_km."""
        logger.info("柴油车分支: 处理 %d 个 SRFLOGGER leg", len(logger_legs))
        for leg_idx, leg in enumerate(tqdm(logger_legs, desc="处理 diesel logger legs")):
            try:
                trip_rows, cumulative_km = process_diesel_leg(
                    leg, cfg, cumulative_km, srf_data=self.srf_data,
                    out_dir=out_dir,
                    reg=reg,
                    reg_code=reg,
                    srf_org_raw=srf_org_raw,
                    trial_cache=trial_cache,
                    op_acc=op_acc,
                    debug_mode=self.debug_mode,
                    # 柴油 raw logger CSV 由 _save_logger_data 独立落盘（gated on
                    # debug_mode）；此处仅控制 4 面板 diesel validation 图，故
                    # --raw-only 时关图不影响 raw 落盘。
                    generate_validation_fig=self.save_figures,
                    leg_idx=leg_idx,
                )
                all_rows.extend(trip_rows)
            except Exception:
                logger.exception("柴油 leg 处理失败: %s", getattr(leg, 'uri', '?'))
        return cumulative_km

    def _process_fps_legs(self, fps_legs, reg, out_dir, raw_dir, cap_lo,
                          cap_hi, logger_speed_all, logger_mass_all,
                          logger_acc_pedal_all, logger_dec_pedal_all,
                          charger_meter_all, logger_legs, altitude_col,
                          speed_col, mass_agg, srf_org_raw, trial_cache,
                          op_acc, home_point, cumulative_km, all_rows):
        """Main EV loop: per FPS leg cache raw telematics, run segmentation, build
        charge/discharge rows, and detect the home charging point. Returns the
        updated (cumulative_km, home_point)."""
        for leg_idx, leg in enumerate(tqdm(fps_legs, desc="处理 FPS legs")):
            try:
                # ── 应用层缓存：按 leg URI 缓存原始遥测 CSV ──────────
                leg_uri_hash = leg.uri.rstrip("/").rsplit("/", 1)[-1]
                cache_path = get_cache_dir() / "srf_raw" / f"{leg_uri_hash}.csv"

                if cache_path.exists():
                    df_leg = pd.read_csv(cache_path, dtype=str)
                else:
                    raw_chunks = list(leg.get_raw_data())
                    if not raw_chunks:
                        continue
                    csv_text = "\n".join(c for c in raw_chunks if c.strip())
                    df_leg = pd.read_csv(io.StringIO(csv_text), dtype=str)
                    # 缓存到磁盘
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    df_leg.to_csv(cache_path, index=False)
            except Exception as exc:
                logger.warning("腿 %d 读取失败: %s", leg_idx, exc)
                continue

            if df_leg.empty or SOC_COL not in df_leg.columns:
                continue

            leg_date = str(leg.start_time.date())
            leg_uri = leg.uri
            suffix = f"{leg_date}_{leg_idx:04d}"

            if self.debug_mode:
                raw_name = f"raw_{suffix}.csv"
                df_leg.to_csv(raw_dir / raw_name, index=False)

            # 当前 leg 时间窗口
            ts_s = pd.Timestamp(leg.start_time)
            ts_e = pd.Timestamp(leg.end_time)
            if ts_s.tzinfo is None:
                ts_s = ts_s.tz_localize('UTC')
            if ts_e.tzinfo is None:
                ts_e = ts_e.tz_localize('UTC')

            # 切片当前 leg 时间窗口的 logger speed 数据
            leg_logger_spd = None
            if logger_speed_all is not None:
                try:
                    leg_logger_spd = logger_speed_all.loc[ts_s:ts_e]
                    if leg_logger_spd.empty:
                        leg_logger_spd = None
                except Exception:
                    leg_logger_spd = None

            # 切片当前 leg 时间窗口的 logger mass 数据
            leg_logger_mass = None
            if logger_mass_all is not None:
                try:
                    leg_logger_mass = logger_mass_all.loc[ts_s:ts_e]
                    if leg_logger_mass.empty:
                        leg_logger_mass = None
                except Exception:
                    leg_logger_mass = None

            # 切片当前 leg 时间窗口的 charger meter 数据
            leg_charger_meter = None
            if charger_meter_all is not None:
                try:
                    leg_charger_meter = charger_meter_all.loc[ts_s:ts_e]
                    if leg_charger_meter.empty:
                        leg_charger_meter = None
                except Exception:
                    leg_charger_meter = None

            # 画图 gated on debug_mode AND save_figures；raw CSV 已在上面独立落盘
            # （gated on debug_mode），故 --raw-only 时此处只关图、不影响 raw 落盘。
            make_figs = self.debug_mode and self.save_figures
            c_segs, d_segs = run_segment_detection(
                df_leg, reg=reg, suffix=suffix,
                out_dir=str(out_dir) if make_figs else None,
                generate_validation_fig=make_figs,
                cap_lo=cap_lo, cap_hi=cap_hi,
                logger_speed_df=leg_logger_spd,
                logger_mass_df=leg_logger_mass,
                charger_meter_df=leg_charger_meter,
            )

            # ── 运营商代码（per-leg；同一 leg 的所有 seg 共用）──────────
            op_code, _op_src, _op_unknown = derive_leg_operator(
                leg, reg,
                srf_org_raw=srf_org_raw,
                vehicles=VEHICLE_CONFIG,
                trial_cache=trial_cache,
            )
            op_acc.setdefault(op_code, 0)
            op_acc[op_code] += 1
            if _op_unknown:
                op_acc.setdefault("_unknown", set())
                op_acc["_unknown"].add(op_code)

            for seg in c_segs:
                seg_clean = {k: v for k, v in seg.items() if k not in _ANCHOR_PRIVATE_KEYS}
                row, _ = _seg_to_row(
                    seg_clean, "charge", leg_uri,
                    [], [],  # charger/logger links 由 patcher 补全
                    df_leg, cumulative_km, home_point,
                    srf_data=self.srf_data,
                    altitude_col=altitude_col,
                    speed_col=speed_col,
                    operator=op_code,
                    mass_agg=mass_agg,
                )
                all_rows.append((seg["start_time"], list(row)))

            for seg in d_segs:
                seg_clean = {k: v for k, v in seg.items() if k not in _ANCHOR_PRIVATE_KEYS}
                row, cumulative_km = _seg_to_row(
                    seg_clean, "discharge", leg_uri,
                    [], [],  # charger/logger links 由 patcher 补全
                    df_leg, cumulative_km, home_point,
                    srf_data=self.srf_data,
                    altitude_col=altitude_col,
                    speed_col=speed_col,
                    has_logger=bool(logger_legs),
                    logger_speed_all=logger_speed_all,
                    logger_acc_pedal_all=logger_acc_pedal_all,
                    logger_dec_pedal_all=logger_dec_pedal_all,
                    operator=op_code,
                    mass_agg=mass_agg,
                )
                all_rows.append((seg["start_time"], list(row)))

            if home_point is None and c_segs:
                from geopy import Point as GeoPoint
                for s in c_segs:
                    lat_h = s.get("latitude")
                    lon_h = s.get("longitude")
                    if lat_h is not None and lon_h is not None:
                        try:
                            home_point = GeoPoint(float(lat_h), float(lon_h))
                            logger.info("Home point: (%.4f, %.4f)", lat_h, lon_h)
                        except Exception:
                            pass
                        if home_point is not None:
                            break
        return cumulative_km, home_point

    def _reclassify_home_charging(self, all_rows, home_point):
        """Post-process: relabel 'Away' charge rows within 0.5 km of the detected
        home point as 'Home' (mutates all_rows in place)."""
        # ── 后处理：用检测到的 home_point 重新分类充电段 ────────────────
        # 首批充电段在 home_point 未知时被分类为 Away，此处修正
        if home_point is not None:
            from geopy import Point as GeoPoint
            from geopy.distance import geodesic
            _ri_leg_type = _row_idx('Leg Type')
            _ri_origin   = _row_idx('Origin (Lat, Lon)')
            reclassified = 0
            for _, row in all_rows:
                lt = row[_ri_leg_type]
                if not isinstance(lt, str) or 'Away' not in lt:
                    continue
                origin_str = row[_ri_origin]
                if not origin_str or not isinstance(origin_str, str):
                    continue
                m = re.match(r'Point\(([+-]?\d+\.?\d*)\s+([+-]?\d+\.?\d*)\)', origin_str)
                if not m:
                    continue
                lat_f, lon_f = float(m.group(1)), float(m.group(2))
                try:
                    if geodesic(home_point, GeoPoint(lat_f, lon_f)).km < 0.5:
                        row[_ri_leg_type] = lt.replace('Away', 'Home')
                        reclassified += 1
                except Exception:
                    pass
            if reclassified:
                logger.info("充电段重新分类: %d 行 Away → Home", reclassified)

    def _finalize_rows(self, sorted_rows, out_headers, is_diesel, cfg,
                       soc_est_cap):
        """Effective-capacity correction (EV) + non-discharge EP scrub + per-period
        donor capacity + Stop-row insertion. Returns
        (sorted_rows, period_cap_kwh, period_n, period_src)."""
        # ── 后处理：effective capacity 修正 ──────────────────────────────
        # 柴油车没有 SOC / 电池容量，跳过此步骤。
        if is_diesel:
            computed_eff_cap = None
            cap_source = 'diesel'
            period_cap_kwh = period_n = None
            period_src = 'diesel'
        else:
            sorted_rows, computed_eff_cap, cap_source = self._correct_effective_capacity(
                sorted_rows,
                _IDX_CAP, _IDX_ENERGY, _IDX_SOC_CHANGE, _IDX_EPERF,
                _IDX_DISTANCE, _IDX_ESOURCE, _IDX_BPOWER, _IDX_DURATION,
                _IDX_EPERF_CORR, _IDX_ELEV, _IDX_MASS,
                soc_est_cap, _IDX_EPERF_KIN, idx_start=_IDX_START,
                soc_fallback=_resolve_soc_fallback(cfg))

            # Bug fix: 充电行的 Energy Performance 理应永远为 NaN，但某些路径
            # （例如 effective-capacity step 2 剔除 ±1σ 异常值后反算时，对有
            # 误填 distance > 0 的充电事件）会意外写入 EP 值。这里显式清空
            # 所有非 discharge 行的三个 EP 列作为最后兜底。
            for row in sorted_rows:
                lt = row[_IDX_LEG_TYPE]
                if not isinstance(lt, str):
                    continue
                lt_low = lt.strip().lower()
                if lt_low == 'stop' or re.match(
                        r'^(ac|dc|charge|mix|estimated)', lt_low):
                    row[_IDX_EPERF] = float('nan')
                    row[_IDX_EPERF_CORR] = float('nan')
                    row[_IDX_EPERF_KIN] = float('nan')
                    row[_IDX_EP_EXCL_AUX] = float('nan')

            # v2.2.6+: 本报告周期的 donor-based capacity (kwh, n)，与
            # _correct_effective_capacity 的 avg_eff_cap 同口径（充电优先 measured
            # leg 均值）。在 Stop 行插入之前、于 _correct 后的同一 sorted_rows 上算，
            # 供 _persist_effective_capacity 合入 quarterly 加权平均。
            period_cap_kwh, period_n, period_src = _period_capacity_from_rows(
                sorted_rows, _IDX_CAP, _IDX_SOC_CHANGE, _IDX_ESOURCE)

        # ── 后处理：填充 Stop 行（trip/charge 之间的静止段）────────────────
        # Must run AFTER sorting + effective capacity correction so that the
        # Stop rows pick up the corrected SOC/mass endpoints from their
        # neighbours.
        n_before_stops = len(sorted_rows)
        sorted_rows = _insert_stop_rows(sorted_rows, headers=out_headers)
        n_stops_added = len(sorted_rows) - n_before_stops
        if n_stops_added:
            logger.info("插入 %d 个 Stop 行（合计 %d 行）",
                         n_stops_added, len(sorted_rows))
        return sorted_rows, period_cap_kwh, period_n, period_src

    def _write_outputs(self, sorted_rows, out_headers, reg, ds, de, out_dir,
                       is_diesel, period_cap_kwh, period_n, period_src,
                       period_key, charger_windows, logger_legs,
                       logger_windows, time_start):
        """Persist effective capacity (EV), write the xlsx (+ inspect HTML in debug
        mode), then run the charger/logger patchers (EV only). Returns the
        report path (or the existing path when overwrite is disabled)."""
        # 持久化 effective_capacity 到 vehicles.json（v2.2.6+ merge 语义：写本期
        # quarterly[period_key] = {kwh, n}，再用所有可靠季度重算 donor 加权平均）
        if not is_diesel:
            self._persist_effective_capacity(
                reg, period_cap_kwh, period_n, period_src, period_key)

        ds_str = ds.strftime("%Y%m%d")
        de_str = de.strftime("%Y%m%d")
        report_name = f"jolt_report_{reg}_{ds_str}_{de_str}.xlsx"
        report_path = out_dir / report_name

        if report_path.exists() and not self.overwrite_existing_report:
            logger.info("报告已存在且未启用覆盖: %s", report_path)
            return str(report_path)

        period_start = ds.date()
        period_end = de.date()
        _write_excel_report(sorted_rows, reg, period_start, period_end,
                            report_path, headers=out_headers)

        if self.debug_mode:
            _write_html_viewer(out_dir, reg, period_start, period_end, report_name)

        time_write = perf_counter()

        # ── 后处理：用 patcher 补全 Charger/Logger 数据 ───────────────────
        # 柴油车在主管线里已经直接从 Logger 通道填好 mass / temperature / 链接，
        # 也没有充电事件，跳过两个 patcher。
        if not self.fast_mode and not is_diesel:
            from jolt_toolkit.report_generator.charger_patcher import ChargerPatcher
            from jolt_toolkit.report_generator.logger_patcher import LoggerPatcher

            ChargerPatcher(srf_data=self.srf_data).patch_file(
                report_path, charger_windows=charger_windows)
            LoggerPatcher(srf_data=self.srf_data).patch_file(
                report_path, logger_legs=logger_legs,
                logger_windows=logger_windows)

        logger.info("Report written: %s", report_path)
        logger.info("Excel 写入完成，耗时 %.2f 秒", perf_counter() - time_write)
        logger.info("报告总耗时: %.2f 秒", perf_counter() - time_start)
        return str(report_path)

    @staticmethod
    def _save_charger_data(charger_objects, out_dir):
        """保存充电桩事务汇总数据到 CSV（合并已有数据，按 uri 去重）。

        委托给 charger_patcher.merge_save_charger_transactions —— 每次运行只拉取本
        周期的事务，若直接覆盖会让 raw_charger CSV 忘掉窗口外的历史，故改为「与现有
        CSV 合并、按 uri 去重（保留最新）、按 start_time 排序」。schema 与旧版一致。
        """
        from jolt_toolkit.report_generator.charger_patcher import (
            merge_save_charger_transactions,
        )
        merge_save_charger_transactions(charger_objects, out_dir)

    @staticmethod
    def _save_logger_data(logger_legs, out_dir, source: str = "SRFLOGGER"):
        """通过 get_data_frame 保存 SRF Logger 数据到 CSV。"""
        if not logger_legs:
            return
        # 按版本命名文件夹：SRFLOGGER_V1 → raw_logger_v1
        suffix = source.replace("SRFLOGGER", "").strip("_").lower()
        dir_name = f"raw_logger_{suffix}" if suffix else "raw_logger"
        logger_dir = out_dir / dir_name
        logger_dir.mkdir(exist_ok=True)
        saved = 0
        for idx, leg in enumerate(logger_legs):
            try:
                available = leg.types
                if not available:
                    continue
                df = leg.get_data_frame(
                    list(available), resolution='1s',
                    conversion=_logger_to_numeric,
                )
                if df is None or df.empty:
                    continue
                leg_date = str(leg.start_time.date())
                csv_name = f"logger_{leg_date}_{idx:04d}.csv"
                df.to_csv(logger_dir / csv_name)
                saved += 1
            except Exception as exc:
                logger.warning("Logger leg %d 读取失败: %s", idx, exc)
        if saved:
            logger.info("保存 Logger 数据: %d 条 -> %s", saved, logger_dir.name)

    @staticmethod
    def _make_srf_data(api_key, root, cache_dir=None, verify=True):
        try:
            return make_srf_client(
                cache_dir, api_key=api_key, root=root, verify=verify)
        except Exception as e:
            logger.error("SRF 客户端创建失败: %s", e)
            raise


# The two capacity post-processing helpers now live in ``report_generator.capacity``;
# re-expose them as staticmethods so existing call sites (``JOLTReportGenerator.
# _correct_effective_capacity`` in scripts.recompute_from_cache, and ``self.<name>``
# inside generate_report) keep resolving unchanged.
JOLTReportGenerator._correct_effective_capacity = staticmethod(_correct_effective_capacity)
JOLTReportGenerator._persist_effective_capacity = staticmethod(_persist_effective_capacity)
