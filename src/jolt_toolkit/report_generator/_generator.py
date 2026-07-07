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

import numpy as np
import pandas as pd
import srf_client
from srf_client import paging
from tqdm import tqdm

from jolt_toolkit import __version__
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


# ── row-tuple 列索引（从 HEADERS 动态派生，排除首列 Leg Number）─────────────
# 这些常量仅用于电车分支的 effective-capacity 后处理，柴油车用独立的 DIESEL_HEADERS
# 不经过此路径。
def _row_idx(header_name: str) -> int:
    """返回 header_name 在 row tuple 中的 0-based 索引（不含 Leg Number 列）。"""
    return HEADERS.index(header_name) - 1


_IDX_LEG_TYPE   = _row_idx('Leg Type')
_IDX_SOC_CHANGE = _row_idx('SOC Change (%)')
_IDX_ENERGY     = _row_idx('Energy Change (kWh)')
_IDX_DISTANCE   = _row_idx('Distance (km)')
_IDX_EPERF      = _row_idx('Energy Performance (kWh/km)')
_IDX_CAP        = _row_idx('Battery Capacity (kWh)')
_IDX_ESOURCE    = _row_idx('Energy Source')
_IDX_BPOWER     = _row_idx('Battery Power (kW)')
_IDX_DURATION   = _row_idx('Duration (HH:MM:SS)')
_IDX_ELEV       = _row_idx('Elevation Difference (m)')
_IDX_MASS       = _row_idx('Vehicle Mass (kg)')
_IDX_EPERF_CORR = _row_idx('Energy Performance Corrected by Elevation Difference (kWh/km)')
_IDX_EPERF_KIN  = _row_idx('Energy Performance Kinetics Corrected (kWh/km)')
_IDX_EP_EXCL_AUX = _row_idx('EP_exclude_aux')
_IDX_START      = _row_idx('Start Time (UTC)')

# ── v2.2.4: time-local (~1-month) effective-capacity window ──────────────────
# soc_estimate 段的容量改由「该行 Start Time ±CAP_WINDOW_HALF_DAYS 天」窗口内的
# 非 soc_estimate effective capacity 推算，以反映电池老化与季节温度漂移（长/全
# 量程报告尤甚，如 EX74JXY 2025-04→2026-02）。窗口内仍保持「充电段优先于放电段」。
# 窗口若无 donor 则逐步加倍半宽，最终退化为全周期均值（等价旧的全局行为），再退化
# 为 fallback_kwh。短报告（≤3 个月）由于周期跨度小，窗口很快覆盖全周期，行为与旧版
# 几乎一致。改这个常量即可整体调节窗宽。
CAP_WINDOW_HALF_DAYS = 15   # 半窗宽（天）；总窗口 ≈ 1 个月
_DAY_NS = 86_400 * 1_000_000_000


# ── v2.2.6+: 季度（报告周期）级 effective-capacity 加权平均 schema ────────────
# vehicles.json 的 ``effective_capacity_kwh`` 不再被「最后一次生成的那个周期均值」
# 覆盖（旧实现 = 容量漂移 / 丢失退化轨迹）。改为对 ``effective_capacity_quarterly``
# （``{period_key: {kwh, n}}``，period_key = 报告周期串 ``YYYYMMDD_YYYYMMDD``，与
# 季度报告 1:1）里所有「可靠」季度按 donor 数加权平均：Σ(kwh·n)/Σn。
# 一个季度若 donor 数 ``n < MIN_DONORS`` 视为不可靠（样本太少，单个异常容量读数即
# 可显著拉偏季度均值，标准误 ≈ σ/√n）：不计入加权平均，其存储 ``kwh`` 回退为该平均
# 值（``n`` 照存以便识别）。保留 ``effective_capacity_kwh`` 键名 = PDF 续航 /
# dashboard / SOC 估算种子等所有读者零改动地自动拿到稳定平均。
# 阈值取 5：活跃电车一个季度通常有数十次 measured 充/放电 donor，远超 5；< 5 干净
# 地标记「真正稀疏」的部分窗口（如 CMZ6260 的 ~6 周补窗）或几乎没跑的车。
MIN_DONORS = 5


def _cap_is_valid(v) -> bool:
    """容量 / SOC 值是否为有效数字（非 None / 非 NaN）。"""
    if v is None:
        return False
    try:
        return not np.isnan(v)
    except (TypeError, ValueError):
        return False


def _soc_weighted_cap(caps, weights):
    """ΔSOC-weighted (combined-ratio) donor effective capacity — replaces the
    plain mean of per-segment implied capacities.

    Each donor's implied capacity is ``C_i = |ΔE_i| / (|ΔSOC_i|/100)``. SOC is
    integer-% quantised, so a single leg's ``C_i`` is noisy AND upward-biased for
    small ``|ΔSOC|`` (σ_C/C ≈ 0.5/|ΔSOC|, and Jensen makes ``E[1/ΔSOC] > 1/ΔSOC``);
    a **plain mean** of donor ``C_i`` is therefore inflated whenever the donor pool
    contains small-ΔSOC legs. This helper instead returns the ΔSOC-weighted mean

        C_eff = Σ(C_i · |ΔSOC_i|) / Σ|ΔSOC_i|  ==  100 · Σ|ΔE_i| / Σ|ΔSOC_i|

    i.e. the combined-ratio estimator — it uses all data (no arbitrary ΔSOC
    cutoff), smoothly down-weights the noisy short legs, and never divides by a
    single small ΔSOC, removing the small-ΔSOC bias entirely.

    Rejected alternatives (verified on AV24LXJ discharge donors): a hard
    ``|ΔSOC| ≥ X%`` cutoff (threshold-sensitive — ≥5% ok but ≥10% over-restricts
    and drifts, and discards data) and ``ΔSOC²`` / inverse-variance weighting
    (over-weights the largest legs and drifts low).

    ``weights`` are the per-donor ``|ΔSOC|`` (%). Entries whose weight is invalid
    / non-positive are excluded from the weighted sum (they can't be weighted); if
    the total usable weight is 0 the result degrades to a plain mean of ``caps``
    (guards ``Σ|ΔSOC| == 0``). Returns ``None`` for an empty pool.
    """
    caps = [float(c) for c in caps]
    if not caps:
        return None
    ws = [abs(float(w)) if (_cap_is_valid(w) and float(w) != 0.0) else 0.0
          for w in weights]
    tot = sum(ws)
    if tot <= 0.0:
        return float(np.mean(caps))
    return sum(c * w for c, w in zip(caps, ws)) / tot


def _period_capacity_from_rows(rows, idx_cap, idx_soc, idx_esrc):
    """复刻 ``_correct_effective_capacity`` 的 donor-based ``avg_eff_cap`` 定义：
    从非 ``soc_estimate`` 段（measured charge / discharge leg）按「充电优先」取
    effective capacity，donor 集内用 **ΔSOC 加权均值**（组合比估计
    ``100·Σ|ΔE|/Σ|ΔSOC|``，见 :func:`_soc_weighted_cap`）而非普通均值——普通均值在
    donor 池含小 ΔSOC 段时上偏（整数 % 量化 + Jensen）。返回
    ``(kwh|None, n_donors, source)``，source ∈ {'charge', 'discharge', 'fallback'}。
    ``n_donors`` 仍为 donor **计数**（供跨季度 donor 数加权平均，语义不变）。

    与 ``_persist_effective_capacity`` / backfill 共用同一口径：``rows`` 既可为报告
    row-tuple（传 ``_IDX_CAP`` / ``_IDX_SOC_CHANGE`` / ``_IDX_ESOURCE``），也可为从
    xlsx 读出的 ``(cap, soc, src)`` 三元组（传 0, 1, 2），保证 live 与 backfill 一致。

    donor 必须满足：``Energy Source`` 是真实的 measured 字符串（``isinstance str`` 且
    != 'soc_estimate'）、``cap`` 为正的有效数字、且 ``SOC Change`` 为可用的非零数值
    （作为加权权重；缺 ΔSOC 的段无法加权，故排除）。measured-leg 判据在 live 路径下对
    真实 measured leg 恒成立（其 energy_source 总是字符串），故对 live donor 集零影响；
    但在 backfill 读最终 xlsx 时它**排除掉 Stop 行**——Stop 行的 ``Energy Source`` /
    ``Battery Capacity`` 是 ``=NA()`` 公式，openpyxl ``data_only=True`` 会把 ``=NA()``
    读成整数 ``0``，否则会被误当成 cap=0 的 donor 污染均值。``cap > 0`` 是额外保险
    （effective capacity 物理上必为正；真实 donor 恒 > 0，故同样不影响 live 数值）。
    """
    charge, discharge = [], []   # list[(cap, |ΔSOC|)]
    for row in rows:
        cap = row[idx_cap]
        src = row[idx_esrc]
        soc = row[idx_soc]
        if (isinstance(src, str) and src != 'soc_estimate'
                and _cap_is_valid(cap) and cap > 0 and _cap_is_valid(soc)):
            if soc > 0:
                charge.append((float(cap), abs(float(soc))))
            elif soc < 0:
                discharge.append((float(cap), abs(float(soc))))
    if charge:
        caps, ws = zip(*charge)
        return _soc_weighted_cap(caps, ws), len(charge), 'charge'
    if discharge:
        caps, ws = zip(*discharge)
        return _soc_weighted_cap(caps, ws), len(discharge), 'discharge'
    return None, 0, 'fallback'


def _recompute_weighted_capacity(quarterly: dict, min_donors: int = MIN_DONORS):
    """给定 ``{period_key: {kwh, n}}``，对**可靠**季度（``n >= min_donors``）按 donor
    数加权平均：Σ(kwh·n)/Σn。就地把稀疏季度（``n < min_donors``）的存储 ``kwh`` 回填
    为该平均值（``n`` 不动）。返回 ``(weighted_avg|None, n_reliable, n_sparse)``。

    退化：若没有任何可靠季度但存在 donor 季度（``0 < n < min_donors``），改用全部
    donor 季度做同样的加权平均，保证 ``effective_capacity_kwh`` 仍写得出（PDF 续航不
    落空）。完全没有 donor 季度 → 返回 ``(None, 0, 0)``，调用方不动既有标量。
    """
    reliable = [(v['kwh'], v['n']) for v in quarterly.values()
                if v.get('kwh') is not None and v.get('n', 0) >= min_donors]
    n_sparse = sum(1 for v in quarterly.values()
                   if v.get('kwh') is not None and 0 < v.get('n', 0) < min_donors)
    pool = reliable or [(v['kwh'], v['n']) for v in quarterly.values()
                        if v.get('kwh') is not None and v.get('n', 0) > 0]
    if not pool:
        return None, 0, n_sparse
    total_n = sum(n for _, n in pool)
    wavg = round(sum(k * n for k, n in pool) / total_n, 1)
    # 稀疏季度的存储 kwh 回退为加权平均（n 保留以便判定）
    for v in quarterly.values():
        if v.get('n', 0) < min_donors:
            v['kwh'] = wavg
    return wavg, len(reliable), n_sparse


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
            root="https://data.csrf.ac.uk/api/",
            cache_dir="./cache",
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
        logging.info("开始生成报告: %s  %s ~ %s", vehicle_registration, date_start, date_end)

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
        logging.info("数据拉取完成，耗时 %.2f 秒", time_fetch - time_start)

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
                logging.warning("充电桩事件拉取失败: %s", exc)

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
            logging.warning("Legs 拉取失败: %s", exc)

        if self.fast_mode:
            logging.info("Fast 模式: 跳过 Charger/Logger 数据。FPS 腿数: %d", len(fps_legs))
        else:
            logging.info(
                "FPS 腿数: %d  充电桩: %d  Logger: %d (%s)",
                len(fps_legs), len(charger_windows), len(logger_windows),
                ", ".join(f"{k}={len(v)}" for k, v in logger_legs_by_src.items()) or "none",
            )

        if self.debug_mode:
            self._save_charger_data(charger_objects, out_dir)
            for src_name, src_legs in logger_legs_by_src.items():
                self._save_logger_data(src_legs, out_dir, source=src_name)

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
                logging.info("Logger speed 数据: %d 条", len(logger_speed_all))

            logger_mass_all = _load_logger_channel(
                logger_legs,
                [('CVW', 'CVW gross combination vehicle weight'),
                 ('VW', ('VW axle weight', 'VW cargo weight'))],
                target_col='logger_mass',
                desc="加载 Logger mass",
            )
            if logger_mass_all is not None:
                logging.info("Logger mass 数据: %d 条", len(logger_mass_all))

            logger_acc_pedal_all = _load_logger_channel(
                logger_legs,
                [('EEC2', 'EEC2 accelerator pedal position 1')],
                target_col='EEC2 accelerator pedal position 1',
                desc="加载 Logger EEC2",
            )
            if logger_acc_pedal_all is not None:
                logging.info("Logger EEC2 油门踏板数据: %d 条", len(logger_acc_pedal_all))

            logger_dec_pedal_all = _load_logger_channel(
                logger_legs,
                [('EBC1', 'EBC1 brake pedal position')],
                target_col='EBC1 brake pedal position',
                desc="加载 Logger EBC1",
            )
            if logger_dec_pedal_all is not None:
                logging.info("Logger EBC1 制动踏板数据: %d 条", len(logger_dec_pedal_all))

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
            logging.debug("无法获取 vehicle.organisation.name: %s", exc)
        trial_cache: dict = {}
        op_acc: dict = {}

        # ── 柴油车分支：用 SRFLOGGER_V1 legs 作为主循环源 ────────────────
        if is_diesel:
            logging.info("柴油车分支: 处理 %d 个 SRFLOGGER leg", len(logger_legs))
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
                    logging.exception("柴油 leg 处理失败: %s", getattr(leg, 'uri', '?'))
            # 跳过 FPS 主循环和 home_point / charger reclassification
            fps_legs = []

        for leg_idx, leg in enumerate(tqdm(fps_legs, desc="处理 FPS legs")):
            try:
                # ── 应用层缓存：按 leg URI 缓存原始遥测 CSV ──────────
                leg_uri_hash = leg.uri.rstrip("/").rsplit("/", 1)[-1]
                cache_path = Path("./cache/srf_raw") / f"{leg_uri_hash}.csv"

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
                logging.warning("腿 %d 读取失败: %s", leg_idx, exc)
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
                            logging.info("Home point: (%.4f, %.4f)", lat_h, lon_h)
                        except Exception:
                            pass
                        if home_point is not None:
                            break

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
                logging.info("充电段重新分类: %d 行 Away → Home", reclassified)

        time_process = perf_counter()
        logging.info("分段处理完成，耗时 %.2f 秒", time_process - time_fetch)

        all_rows.sort(key=lambda x: (
            pd.Timestamp(x[0]).tz_convert(None)
            if pd.Timestamp(x[0]).tzinfo is not None
            else pd.Timestamp(x[0])
        ))
        sorted_rows = [r for _, r in all_rows]

        if not sorted_rows:
            logging.warning("未检测到有效分段，跳过 Excel 生成")
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
            logging.info("运营商解析（按 leg 计）：%s", dist or "无")
            bad = {c for c in unknown if c is not None}
            if bad:
                logging.warning("运营商代码未在 KNOWN_OPERATOR_CODES 中：%s", ", ".join(sorted(bad)))
            if None in op_acc:
                logging.warning("有 %d 个 leg 无法确定运营商", op_acc[None])

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
                soc_est_cap, _IDX_EPERF_KIN, idx_start=_IDX_START)

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
            logging.info("插入 %d 个 Stop 行（合计 %d 行）",
                         n_stops_added, len(sorted_rows))

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
            logging.info("报告已存在且未启用覆盖: %s", report_path)
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

        print(f"Report written: {report_path}")
        logging.info("Excel 写入完成，耗时 %.2f 秒", perf_counter() - time_write)
        logging.info("报告总耗时: %.2f 秒", perf_counter() - time_start)
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
                logging.warning("Logger leg %d 读取失败: %s", idx, exc)
        if saved:
            logging.info("保存 Logger 数据: %d 条 -> %s", saved, logger_dir.name)

    @staticmethod
    def _correct_effective_capacity(rows, idx_cap, idx_energy, idx_soc,
                                     idx_eperf, idx_dist, idx_esrc,
                                     idx_bpower, idx_dur,
                                     idx_eperf_corr, idx_elev, idx_mass,
                                     fallback_kwh, idx_eperf_kin=None,
                                     idx_start=None):
        """
        后处理：修正 effective battery capacity 并反算相关字段。

        返回 (rows, effective_cap, cap_source)：
        - effective_cap: 整个报告周期的最终 effective capacity 均值 (kWh)，
          供 ``_persist_effective_capacity`` 写回 vehicles.json（语义不变）。
        - cap_source: 'charge' | 'discharge' | 'fallback'

        time-local (~1-month) 容量（v2.2.4）
        --------------------------------------
        每个 soc_estimate 段的替换容量改由「该段 Start Time ±``CAP_WINDOW_HALF_DAYS``
        天」窗口内的非 soc_estimate effective capacity 推算，窗口内仍保持
        「充电段优先于放电段」。这样长报告里的电池老化 / 季节温度漂移就不会被一个
        全周期均值抹平。``idx_start`` 是 row tuple 中 'Start Time (UTC)' 列的索引
        （值为 ``pd.Timestamp``）；为 ``None`` 时退回旧的全周期单一均值行为。

        优雅降级（逐级）：
        1. ±CAP_WINDOW_HALF_DAYS 天窗口内的 donor（充电优先，再放电）。
        2. 窗口无 donor → 逐步加倍半宽，直到找到 donor 或窗口覆盖整个周期
           （覆盖整个周期即等价于旧的全局均值行为）。
        3. 整个周期都没有 donor（或该行缺时间戳）→ 全局均值。
        4. 全局也没有 donor → ``fallback_kwh``。

        步骤 1：按上述时间局部逻辑替代每个 soc_estimate 段的容量值并反算 energy。
        步骤 2：用**全局 ±1σ** 检测异常 effective capacity，替换值同样取「inlier
                donor 的时间局部窗口均值」，避免把错误季节的偏差重新注入。
                **energy 反算按 ``energy_source`` 门控**：只有 soc_estimate 段
                （energy 本就由 SOC × capacity 推得）才重算 energy / EP / corrected
                / kinetics；counter-sourced 段（``energy_source`` ∈ {total_energy,
                moving_energy}）只修正 capacity 列本身，其 energy / EP / corrected /
                kinetics 一律保留计数器原值 —— 异常的 IMPLIED capacity 源于分母
                ΔSOC 的整数 % 量化不可靠（短程/小 ΔSOC 被低估），而非计数器 energy
                有误，用 SOC 反算会把整数 % 的低估注入短程 leg 形成伪低 EP 带。

        已评估并否决的替代方案（MODE B，v2.2.7 A/B 对比，不采用）
        --------------------------------------------------------------
        曾评估一个「随 ΔSOC 缩放的异常阈值」方案：把固定 ±1σ 换成逐 leg 的
        σ_i = sqrt(σ_true² + σ_soc²)（σ_soc = C·0.5/|ΔSOC%| 为量化噪声，σ_true 由
        干净大 ΔSOC(≥10%) 段稳健估计），|C−μ| > 2σ_i 判异常，且异常行**无论
        energy_source** 都用 SOC 反算。**否决**：AV24LXJ/K/L 全量对比显示它主要在
        **中等 ΔSOC（中位 8%，仅约 1/3 ≥10%）**触发——此处 SOC 量化仍达 ±5–12%——
        用「ΔSOC×车队平均容量」这个**推断值**覆盖了原始计数器的**实测能量**
        （逐 trip 计数器增量与报告 E 吻合、零 reset、基本单调，且首尾快照多紧贴 trip
        边界，是可信的直接能量测量），把真实 EP 变异同质化、单车造出几十条不合理
        EP（>2.0 kWh/km，例如把教科书级 EP 1.00 改写成 1.51、1.23 改写成 0.81）。两法
        对原始伪低带的修复完全一致（小 ΔSOC 段两法都不触发、保留计数器）。故保留此
        二元门控（MODE A）。

        待查（FUTURE，勿在此处理）
        --------------------------
        1. 差异集里计数器 energy **系统性低于** SOC 推断（约 248 升 vs 65 降），
           可能是 SOC 表在短/中程 trip 上的非线性；值得单独排查，但不应由「盲目
           SOC 替换」来掩盖。
        2. 少数「陈旧快照」导致的 anchor spillover（首快照早于 trip 起点很久 → 计数器
           增量多计 → EP 虚高，如 AV24LXJ 2024-06-24 07:45 EP 2.34）应由**专门的
           anchor-spillover 守卫**处理，而非全盘 SOC 反算。
        """
        import numpy as np

        def _is_valid(v):
            if v is None:
                return False
            try:
                return not np.isnan(v)
            except (TypeError, ValueError):
                return False

        def _recalc_eperf_corrected(row):
            """energy 修改后重算海拔修正和动能修正能量效率。"""
            e = row[idx_energy]
            d = row[idx_dist]
            h = row[idx_elev]
            m = row[idx_mass]
            if not all(_is_valid(v) for v in (e, d, h, m)):
                return
            if d <= 0:
                return
            ke_per_d = None
            if idx_eperf_kin is not None:
                old_corr = row[idx_eperf_corr]
                old_kin = row[idx_eperf_kin]
                if _is_valid(old_corr) and _is_valid(old_kin):
                    ke_per_d = old_corr - old_kin
            e_grav = m * 9.81 * h / 3_600_000.0
            row[idx_eperf_corr] = round((abs(e) - e_grav) / d, 4)
            if ke_per_d is not None and idx_eperf_kin is not None:
                row[idx_eperf_kin] = round(row[idx_eperf_corr] - ke_per_d, 4)

        # ── 时间戳与窗口准备 ───────────────────────────────────────────
        def _naive_ns(v):
            """row 的 Start Time → tz-naive ns 整数；不可解析则 None。"""
            if v is None:
                return None
            try:
                ts = pd.Timestamp(v)
            except (TypeError, ValueError):
                return None
            if ts is pd.NaT or pd.isna(ts):
                return None
            if ts.tzinfo is not None:
                ts = ts.tz_convert(None)
            # pd.Timestamp.value 对标量恒为 ns，无需 .as_unit
            return int(ts.value)

        # 每个 row 的起始时间（ns）；idx_start 为 None 时全部 None → 退回全局行为
        if idx_start is not None:
            row_ns = [_naive_ns(row[idx_start]) for row in rows]
        else:
            row_ns = [None] * len(rows)
        valid_ns = [n for n in row_ns if n is not None]
        period_span_days = ((max(valid_ns) - min(valid_ns)) / _DAY_NS
                            if len(valid_ns) >= 2 else 0.0)
        # 加倍半宽的上限：覆盖整个周期即等价旧全局行为
        max_half_days = max(float(CAP_WINDOW_HALF_DAYS), period_span_days)

        def _window_mean(donors, t_ns, base_half_days):
            """donors: list[(ns, cap, w)]，w = |ΔSOC|。在 ±base_half 天窗口内取
            **ΔSOC 加权均值**（组合比估计 Σ(cap·w)/Σw，见 :func:`_soc_weighted_cap`），
            无 donor 则逐步加倍半宽直至找到或覆盖整个周期。返回
            (mean|None, n_used, half_used)；窗口内 Σw==0 时降级为普通均值。"""
            if not donors or t_ns is None:
                return None, 0, base_half_days
            arr_ns = np.array([d[0] for d in donors], dtype=np.int64)
            arr_cap = np.array([d[1] for d in donors], dtype=float)
            arr_w = np.array([d[2] for d in donors], dtype=float)
            half = float(base_half_days)
            while True:
                win_ns = int(half * _DAY_NS)
                mask = np.abs(arr_ns - t_ns) <= win_ns
                if mask.any():
                    caps_w = arr_cap[mask]
                    ws_w = arr_w[mask]
                    tot = float(ws_w.sum())
                    m = (float((caps_w * ws_w).sum() / tot) if tot > 0.0
                         else float(caps_w.mean()))
                    return m, int(mask.sum()), half
                if half >= max_half_days:
                    return None, 0, half
                half = min(half * 2.0, max_half_days)

        # ── 步骤 1：time-local effective capacity 替换 soc_estimate 段 ────
        # 充电段: SOC 上升 (soc > 0)；放电段: SOC 下降 (soc < 0)
        # donor 携带 |ΔSOC| 作为组合比权重（充/放电容量在段内用 ΔSOC 加权均值，
        # 消除小 ΔSOC 段的整数 % 量化上偏；见 _soc_weighted_cap）。
        charge_donors = []      # list[(ns, cap, w)] ; w = |ΔSOC|
        discharge_donors = []
        charge_caps = []        # list[(cap, w)]  全周期（不要求有时间戳）
        discharge_caps = []
        for row, n in zip(rows, row_ns):
            cap = row[idx_cap]
            src = row[idx_esrc]
            soc = row[idx_soc]
            if _is_valid(cap) and src != 'soc_estimate' and _is_valid(soc):
                w = abs(float(soc))
                if soc > 0:
                    charge_caps.append((cap, w))
                    if n is not None:
                        charge_donors.append((n, cap, w))
                elif soc < 0:
                    discharge_caps.append((cap, w))
                    if n is not None:
                        discharge_donors.append((n, cap, w))

        # 全周期 ΔSOC 加权均值（充电优先），用于退化与最终持久化语义（口径不变）。
        # 用不依赖时间戳的 *_caps，确保即使 idx_start=None（旧调用）也能给出
        # 正确的全局 charge/discharge 加权均值而非误落到 fallback。
        if charge_caps:
            caps, ws = zip(*charge_caps)
            avg_eff_cap = _soc_weighted_cap(caps, ws)
            cap_source = 'charge'
        elif discharge_caps:
            caps, ws = zip(*discharge_caps)
            avg_eff_cap = _soc_weighted_cap(caps, ws)
            cap_source = 'discharge'
        else:
            avg_eff_cap = fallback_kwh
            cap_source = 'fallback'

        def _local_cap_for(t_ns):
            """充电优先的时间局部 effective capacity。返回 (cap|None, src, half)。"""
            m, _, half = _window_mean(charge_donors, t_ns, CAP_WINDOW_HALF_DAYS)
            if m is not None:
                return m, 'charge', half
            m, _, half = _window_mean(discharge_donors, t_ns, CAP_WINDOW_HALF_DAYS)
            if m is not None:
                return m, 'discharge', half
            return None, cap_source, half

        n_local = n_widened = n_global = n_fallback = 0
        widened_half_max = 0.0
        for row, t_ns in zip(rows, row_ns):
            if row[idx_esrc] == 'soc_estimate' and _is_valid(row[idx_soc]):
                cap, _src, half = _local_cap_for(t_ns)
                if cap is None:
                    # 该行缺时间戳或全周期无 donor → 全局均值（或 fallback_kwh）
                    cap = avg_eff_cap
                    if cap_source == 'fallback':
                        n_fallback += 1
                    else:
                        n_global += 1
                elif half <= CAP_WINDOW_HALF_DAYS:
                    n_local += 1
                else:
                    n_widened += 1
                    widened_half_max = max(widened_half_max, half)
                row[idx_cap] = round(cap, 2)
                soc_chg = row[idx_soc]
                row[idx_energy] = round(soc_chg / 100.0 * cap, 3)
                dist = row[idx_dist]
                if _is_valid(dist) and dist > 0 and _is_valid(row[idx_energy]):
                    row[idx_eperf] = round(abs(row[idx_energy]) / dist, 4)
                dur_days = row[idx_dur]
                if _is_valid(dur_days) and dur_days > 0 and _is_valid(row[idx_energy]):
                    dur_h = dur_days * 24.0
                    row[idx_bpower] = round(row[idx_energy] / dur_h, 3)
                _recalc_eperf_corrected(row)

        logging.info(
            "步骤 1 (time-local ±%d天, 周期跨度=%.0f天): soc_estimate 替换 — "
            "局部=%d, 扩窗=%d(最大半宽 %.0f天), 全局回退=%d, fallback=%d; "
            "donor(充电=%d, 放电=%d), 全局均值=%.1f kWh(来源=%s)",
            CAP_WINDOW_HALF_DAYS, period_span_days, n_local, n_widened,
            widened_half_max, n_global, n_fallback,
            len(charge_donors), len(discharge_donors), avg_eff_cap, cap_source)

        # ── 步骤 2：全局 ±1σ 检测 + 时间局部 inlier 均值替换 ─────────────
        all_caps = [row[idx_cap] for row in rows if _is_valid(row[idx_cap])]
        if len(all_caps) >= 3:
            cap_mean = float(np.mean(all_caps))
            cap_std  = float(np.std(all_caps))
            lo = cap_mean - cap_std
            hi = cap_mean + cap_std
            # inlier donors（±1σ 内）连同时间戳 + |ΔSOC| 权重，供异常行做时间局部
            # 替换。替换均值同样用 ΔSOC 加权（组合比估计），避免小 ΔSOC 段的量化上偏
            # 重新注入替换值。缺 ΔSOC 的行权重记 0（自然排除出加权和）。
            inlier_donors = [
                (n, row[idx_cap],
                 abs(float(row[idx_soc])) if _is_valid(row[idx_soc]) else 0.0)
                for row, n in zip(rows, row_ns)
                if n is not None and _is_valid(row[idx_cap]) and lo <= row[idx_cap] <= hi
            ]
            inlier_global_mean = (
                _soc_weighted_cap([c for _, c, _ in inlier_donors],
                                  [w for _, _, w in inlier_donors])
                if inlier_donors else cap_mean)
            corrected = n_repl_local = n_energy_kept = 0
            for row, t_ns in zip(rows, row_ns):
                cap = row[idx_cap]
                if _is_valid(cap) and (cap < lo or cap > hi):
                    repl, _, _ = _window_mean(inlier_donors, t_ns,
                                              CAP_WINDOW_HALF_DAYS)
                    if repl is not None:
                        n_repl_local += 1
                    else:
                        repl = inlier_global_mean
                    # 始终修正 capacity 列本身：既让展示合理，也让本周期最终
                    # 持久化的均值不被异常 IMPLIED capacity 污染（持久化语义不变）。
                    row[idx_cap] = round(repl, 2)
                    # energy 反算**仅**适用于 soc_estimate 段（无可靠能量计数器，
                    # 其 energy 本就由 SOC × capacity 推得）。对 counter-sourced 段
                    # （energy_source ∈ {total_energy, moving_energy}），异常的
                    # IMPLIED capacity 说明分母 ΔSOC 不可靠（整数 % 量化，短程/小
                    # ΔSOC 被低估），而非计数器 energy 有误 —— 因此必须保留计数器
                    # 给出的 energy / EP / corrected / kinetics，绝不能用 SOC 反算
                    # 覆盖（否则短程 leg 会得到虚低 EP，形成伪低带）。
                    if row[idx_esrc] == 'soc_estimate':
                        soc_chg = row[idx_soc]
                        if _is_valid(soc_chg) and soc_chg != 0:
                            row[idx_energy] = round(soc_chg / 100.0 * repl, 3)
                            dist = row[idx_dist]
                            if _is_valid(dist) and dist > 0:
                                row[idx_eperf] = round(abs(row[idx_energy]) / dist, 4)
                            dur_days = row[idx_dur]
                            if _is_valid(dur_days) and dur_days > 0:
                                dur_h = dur_days * 24.0
                                row[idx_bpower] = round(row[idx_energy] / dur_h, 3)
                            _recalc_eperf_corrected(row)
                    else:
                        n_energy_kept += 1
                    corrected += 1
            logging.info(
                "步骤 2 (全局 ±1σ 检测 + time-local 替换): 修正 %d 行异常 effective "
                "capacity (其中 %d 行用局部窗口均值; %d 行为 counter-sourced，仅修"
                "容量列、保留计数器 energy; 全局均值=%.1f, σ=%.1f, "
                "范围=[%.1f, %.1f], inlier donor=%d)",
                corrected, n_repl_local, n_energy_kept, cap_mean, cap_std, lo, hi,
                len(inlier_donors))
            # 步骤 2 后的全周期均值作为最终持久化的 effective capacity（语义不变）
            final_caps = [row[idx_cap] for row in rows if _is_valid(row[idx_cap])]
            if final_caps:
                avg_eff_cap = float(np.mean(final_caps))

        return rows, round(avg_eff_cap, 1), cap_source

    @staticmethod
    def _persist_effective_capacity(reg, eff_cap, n_donors, source, period_key):
        """将本报告周期的 effective capacity 合入 vehicles.json（v2.2.6+ merge）。

        新 schema：
        - ``effective_capacity_quarterly``: ``{period_key: {kwh, n}}``，period_key =
          报告周期串 ``YYYYMMDD_YYYYMMDD``，与季度报告 1:1。本期写
          ``{kwh: round(eff_cap, 1), n: n_donors}``。
        - ``effective_capacity_kwh``: 对所有可靠季度（``n >= MIN_DONORS``）按 donor
          数加权平均（Σ(kwh·n)/Σn）。稀疏季度（``n < MIN_DONORS``）不计入，其存储
          ``kwh`` 由 :func:`_recompute_weighted_capacity` 回填为该平均。保留键名使
          PDF 续航 / dashboard / SOC 种子零改动地拿到稳定平均。

        仅当 source 为 'charge' / 'discharge'（来自遥测 donor）时写入；
        source='fallback'（无 donor，如纯 soc_estimate 的 SOC-only Mercedes）不写、
        不动既有标量。这同时修掉了旧实现「单周期均值覆盖」导致的容量漂移 bug。
        """
        if source == 'fallback' or eff_cap is None:
            logging.info("effective capacity 来源为 fallback（无 donor），"
                         "不更新 vehicles.json: %s %s", reg, period_key)
            return

        import json
        from jolt_toolkit.configs import get_config_path
        path = get_config_path('vehicles.json')
        with open(path, 'r', encoding='utf-8') as f:
            all_cfg = json.load(f)
        if reg not in all_cfg:
            return

        entry = all_cfg[reg]
        old_val = entry.get('effective_capacity_kwh')
        quarterly = entry.get('effective_capacity_quarterly') or {}
        quarterly[period_key] = {'kwh': round(float(eff_cap), 1), 'n': int(n_donors)}

        wavg, n_rel, n_sparse = _recompute_weighted_capacity(quarterly)
        entry['effective_capacity_quarterly'] = quarterly
        if wavg is not None:
            entry['effective_capacity_kwh'] = wavg

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(all_cfg, f, indent=2, ensure_ascii=False)
            f.write('\n')
        # 同步内存中的 VEHICLE_CONFIG
        VEHICLE_CONFIG.setdefault(reg, {})
        VEHICLE_CONFIG[reg]['effective_capacity_quarterly'] = quarterly
        if wavg is not None:
            VEHICLE_CONFIG[reg]['effective_capacity_kwh'] = wavg
        logging.info(
            "effective_capacity 已更新: %s  %.1f → %.1f kWh "
            "(本期 %s: kwh=%.1f n=%d 来源=%s; 可靠季度=%d, 稀疏=%d)",
            reg, old_val or 0, wavg if wavg is not None else (old_val or 0),
            period_key, round(float(eff_cap), 1), int(n_donors), source,
            n_rel, n_sparse)

    @staticmethod
    def _make_srf_data(api_key, root, cache_dir=None, verify=True):
        try:
            cache = None
            if cache_dir:
                from cachecontrol.caches import SeparateBodyFileCache
                srf_cache_path = os.path.join(cache_dir, "srf_http")
                os.makedirs(srf_cache_path, exist_ok=True)
                cache = SeparateBodyFileCache(srf_cache_path)
            return srf_client.SRFData(
                api_key=api_key, cache=cache, root=root, verify=verify,
            )
        except Exception as e:
            logging.error("SRF 客户端创建失败: %s", e)
            raise
