"""
validation_generator.py
=======================
独立的 Validation 图 + Inspect HTML 生成器。

适用场景：先用 --debug --fast 生成报告，再用 LoggerPatcher 补全数据，
最后用此模块重新生成包含 Logger speed/mass 叠加的验证图和 inspect HTML。

Logger 速度 / 质量数据有两条来源路径：

* **本地 CSV（默认，优先）** —— 直接复用 ``--debug`` 模式落盘的
  ``raw_logger_*/logger_*.csv``。这些 CSV 由 :func:`_save_logger_data`
  以 ``get_data_frame(list(types), resolution='1s')`` 落盘，含 CCVS / 2 speed /
  CVW 等通道，与 ``_load_logger_channel`` 实时拉取等价；用本地 CSV 免去 SRF
  API 往返，对多周期 / 大体量车辆（如 WU70GLV 上千条 logger leg）更快更稳，
  且天然覆盖整段 raw_telematics 时间跨度。
* **SRF API（兜底）** —— 当目录下没有任何 ``raw_logger_*`` CSV 时，回退到
  :meth:`_fetch_logger_data` 按整段 raw_telematics 跨度拉取。

多周期布局：一个车辆目录下可能有 *一个* ``raw_telematics/`` 但 *多个* 周期
xlsx / inspect HTML（``feat/full-range-report`` 全量布局）。:meth:`regenerate`
会为目录下 *每一个* 非 finetuned 周期 xlsx 各重写一份 inspect HTML。

用法：
    from jolt_toolkit.report_generator.validation_generator import ValidationGenerator
    gen = ValidationGenerator()
    gen.regenerate("excel_report_database/2.2.3/YN25RSY")
"""

from __future__ import annotations

import datetime
import io
import logging
import os
import re
from pathlib import Path

import pandas as pd
import srf_client
from srf_client import paging

from jolt_toolkit.report_generator.segment_algorithms import (
    run_segment_detection,
    VEHICLE_CONFIG,
    SOC_COL,
    TIME_COL,
)
from jolt_toolkit.report_generator.report_builder import _write_html_viewer

logger = logging.getLogger(__name__)

# ── Logger 数据列名 ──────────────────────────────────────────────────────
_CVW_COL = "CVW gross combination vehicle weight"

# 本地 CSV 通道列优先级（镜像 _generator._load_logger_channel 的 channels 顺序）。
# 速度：优先 CCVS 轮速，备选 GPS '2 speed'（YN25RSY / TA70WTL 等纯 GPS 车）。
_SPEED_COLS: tuple[str, ...] = (
    "CCVS wheel based vehicle speed",
    "2 speed",
)
# 质量：优先 CVW 组合车重，备选 VW 轴重 / 货重。
_MASS_COLS: tuple[str, ...] = (
    _CVW_COL,
    "VW axle weight",
    "VW cargo weight",
)

# 报告文件名解析：jolt_report_<REG>_<YYYYMMDD>_<YYYYMMDD>[_finetuned].xlsx
_XLSX_RE = re.compile(
    r"jolt_report_(?P<reg>\w+?)_(?P<ds>\d{8})_(?P<de>\d{8})"
    r"(?P<ft>_finetuned)?\.xlsx$"
)


class ValidationGenerator:
    """
    从已有的 raw_telematics CSV 重新生成验证图和 inspect HTML。

    自动从 SRF API 获取 Logger 速度（CCVS/2 speed）和质量（CVW）数据，
    叠加到验证图 Panel 1（速度右轴）和 Panel 4（质量）。

    Args:
        srf_data:  可选的已有 SRF 客户端实例
        cache_dir: SRF API 缓存目录
    """

    def __init__(self, srf_data=None, cache_dir: str = "./cache"):
        if srf_data is not None:
            self._srf_data = srf_data
        else:
            api_key = os.environ.get("SRF_API_KEY")
            if not api_key:
                logger.warning("ValidationGenerator: SRF_API_KEY 未设置")
            self._srf_data = srf_client.SRFData(
                api_key=api_key,
                cache_dir=cache_dir,
                root="https://data.csrf.ac.uk/api/",
                verify=True,
            )

    def regenerate(
        self, report_dir: str | Path, *, use_local_logger: bool = True
    ) -> int:
        """
        重新生成指定报告目录下的验证图和 inspect HTML。

        ``report_dir`` 应包含 ``raw_telematics/`` 子目录（由 ``--debug`` 模式
        生成）和一个或多个 ``jolt_report_*.xlsx`` 报告文件。目录下若有
        ``raw_logger_*/`` CSV，则默认从本地 CSV 重建 Logger 速度 / 质量
        叠加（见模块 docstring）；否则回退 SRF API。

        多周期目录：为 *每一个* 非 finetuned 周期 xlsx 各重写一份 inspect
        HTML（``_finetuned`` xlsx 由 report-finetuner 流程负责，跳过）。

        Args:
            report_dir:        车辆报告目录。
            use_local_logger:  True 时优先用本地 raw_logger CSV；False 强制走
                               SRF API。

        Returns:
            重新生成的验证图数量。
        """
        report_dir = Path(report_dir)

        # 从目录中找到报告文件以解析车辆（reg 在各周期一致，取首个即可）。
        # 先解析 reg/cfg —— 柴油分支需要据此分流，且不依赖 raw_telematics。
        xlsx_files = sorted(report_dir.glob("jolt_report_*.xlsx"))
        if not xlsx_files:
            logger.error("未找到报告文件: %s", report_dir)
            return 0

        m = _XLSX_RE.match(xlsx_files[0].name)
        if not m:
            logger.error("无法解析文件名: %s", xlsx_files[0].name)
            return 0

        reg = m.group("reg")
        cfg = VEHICLE_CONFIG.get(reg)
        if cfg is None:
            logger.error("车辆 %s 未在 vehicles.json 中注册", reg)
            return 0

        # ── 柴油车：分流到独立的离线重画路径 ────────────────────────────────
        # 下方 EV 分支依赖 SOC + ``nominal_kwh`` + ``run_segment_detection`` 的
        # 电车分段，柴油 logger 管线都不适用（且柴油 cfg 没有 ``nominal_kwh``，
        # 旧代码在此处 ``KeyError``）。柴油检测沿用 ``_generator`` 的判定
        # （``fuel_type == "DIESEL"``），route 给 ``diesel_pipeline`` 的
        # :func:`regenerate_diesel_validation` —— 它从本地 ``raw_logger_*`` CSV
        # 重建 4 面板柴油图 + inspect HTML，并以 ``export_overlay=True`` 外置
        # ``<png>.boxes.json`` 叠加（与 EV 的 ``export_dsoc_overlay`` 对齐）。
        if str(cfg.get("fuel_type", "")).upper() == "DIESEL":
            from jolt_toolkit.report_generator.diesel_pipeline import (
                regenerate_diesel_validation,
            )

            return regenerate_diesel_validation(report_dir, reg=reg, cfg=cfg)

        # ── 以下为电车（EV）路径 ────────────────────────────────────────────
        raw_dir = report_dir / "raw_telematics"
        if not raw_dir.exists():
            logger.error("raw_telematics 目录不存在: %s", raw_dir)
            return 0

        reg_srf = cfg["srf_reg"]
        nominal_kwh = cfg["nominal_kwh"]
        cap_lo = nominal_kwh * 0.5
        cap_hi = nominal_kwh * 2.0

        # raw 遥测 CSV（决定整段时间跨度 + 待重生成的验证图集合）
        raw_csvs = sorted(raw_dir.glob("raw_*.csv"))
        if not raw_csvs:
            logger.warning("raw_telematics 目录下无 CSV 文件")
            return 0
        span_ds, span_de = self._raw_telematics_span(raw_csvs)

        logger.info(
            "ValidationGenerator: %s (%s ~ %s, %d 周期, %d raw legs)",
            reg,
            span_ds.date(),
            span_de.date(),
            len(xlsx_files),
            len(raw_csvs),
        )

        # 1. 获取 Logger 数据（速度 + 质量）：本地 CSV 优先，API 兜底
        logger_speed_all: pd.DataFrame | None = None
        logger_mass_all: pd.DataFrame | None = None
        if use_local_logger:
            logger_speed_all, logger_mass_all = self._load_logger_from_csv(report_dir)
        if logger_speed_all is None and logger_mass_all is None:
            logger.info("  本地无 Logger CSV，回退 SRF API（整段跨度）")
            logger_speed_all, logger_mass_all = self._fetch_logger_data(
                reg_srf, span_ds, span_de
            )

        # 2. 遍历 raw CSV，重新运行分段 + 生成验证图（带 Logger 叠加）
        fig_count = 0
        for csv_path in raw_csvs:
            # 从文件名解析 suffix: raw_2025-10-20_0000.csv
            fname_m = re.match(r"raw_(.+)\.csv$", csv_path.name)
            if not fname_m:
                continue
            suffix = fname_m.group(1)

            df_leg = pd.read_csv(csv_path, dtype=str)
            if df_leg.empty or SOC_COL not in df_leg.columns:
                continue

            # 切片 Logger 数据到当前 leg 时间窗口
            leg_logger_spd = self._slice_logger_data(df_leg, logger_speed_all)
            leg_logger_mass = self._slice_logger_data(df_leg, logger_mass_all)

            run_segment_detection(
                df_leg,
                reg=reg,
                suffix=suffix,
                out_dir=str(report_dir),
                generate_validation_fig=True,
                cap_lo=cap_lo,
                cap_hi=cap_hi,
                logger_speed_df=leg_logger_spd,
                logger_mass_df=leg_logger_mass,
                # Externalise Panel-1 dSOC boxes → sidecar JSON for the inspect
                # HTML's interactive hover overlay (the PNG no longer bakes them).
                export_dsoc_overlay=True,
            )
            fig_count += 1

        # 3. 为每个非 finetuned 周期 xlsx 各重写一份 inspect HTML
        html_count = 0
        for xlsx in xlsx_files:
            pm = _XLSX_RE.match(xlsx.name)
            if not pm or pm.group("ft"):
                # finetuned 周期由 report-finetuner 的 regenerate_inspect_html
                # 负责，避免覆盖其 *_finetuned.png 引用
                continue
            p_start = datetime.datetime.strptime(pm.group("ds"), "%Y%m%d").date()
            p_end = datetime.datetime.strptime(pm.group("de"), "%Y%m%d").date()
            _write_html_viewer(report_dir, reg, p_start, p_end, xlsx.name)
            html_count += 1

        logger.info(
            "ValidationGenerator: 完成 %d 张验证图, %d 份 inspect HTML",
            fig_count,
            html_count,
        )
        return fig_count

    def regenerate_folder(self, base_dir: str | Path) -> dict[str, int]:
        """批量重新生成 base_dir 下所有车辆子目录的验证图。

        电车走 ``raw_telematics/``；柴油车从 ``raw_logger_*/`` 重画（见
        :meth:`regenerate` 的柴油分支），故两类原始数据任一存在即处理 ——
        否则混合车队里只有 raw_logger 的柴油车会被漏掉。
        """
        base = Path(base_dir)
        results = {}
        for sub in sorted(base.iterdir()):
            if not sub.is_dir():
                continue
            has_telematics = (sub / "raw_telematics").exists()
            has_logger = any(sub.glob("raw_logger*"))
            if has_telematics or has_logger:
                results[sub.name] = self.regenerate(sub)
        return results

    # ── 内部方法 ──────────────────────────────────────────────────────────

    @staticmethod
    def _raw_telematics_span(
        raw_csvs: list[Path],
    ) -> tuple[datetime.datetime, datetime.datetime]:
        """从 raw_telematics CSV 文件名解析整段时间跨度（覆盖所有周期）。

        文件名形如 ``raw_2025-10-20_0000.csv``；取最早 / 最晚日期作为 API
        兜底拉取窗口，避免只覆盖第一个周期。
        """
        dates: list[datetime.datetime] = []
        for p in raw_csvs:
            mm = re.match(r"raw_(\d{4}-\d{2}-\d{2})_", p.name)
            if mm:
                try:
                    dates.append(datetime.datetime.strptime(mm.group(1), "%Y-%m-%d"))
                except ValueError:
                    pass
        if not dates:
            # 兜底：用一个宽窗口（不应发生）
            now = datetime.datetime.utcnow()
            return now - datetime.timedelta(days=3650), now
        return min(dates), max(dates)

    @classmethod
    def _load_logger_from_csv(
        cls,
        report_dir: Path,
    ) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
        """从本地 ``raw_logger_*/logger_*.csv`` 重建 Logger 速度 / 质量。

        复用 ``--debug`` 模式落盘的 logger CSV（由 :func:`_save_logger_data`
        以 1s 分辨率写出，首列为时间戳索引），按 :data:`_SPEED_COLS` /
        :data:`_MASS_COLS` 优先级各取一列，合并为单列 DataFrame，索引统一为
        UTC。与 ``_load_logger_channel`` 的实时拉取结果等价。

        Returns:
            ``(speed_df, mass_df)``；缺数据的一侧返回 None。当目录下完全没有
            ``raw_logger_*`` CSV 时返回 ``(None, None)``，由调用方决定是否回退
            SRF API。
        """
        logger_dirs = [d for d in sorted(report_dir.glob("raw_logger*")) if d.is_dir()]
        csvs: list[Path] = []
        for d in logger_dirs:
            csvs.extend(sorted(d.glob("logger_*.csv")))
        if not csvs:
            return None, None

        spd_parts: list[pd.Series] = []
        mass_parts: list[pd.Series] = []
        for path in csvs:
            try:
                df = pd.read_csv(path, index_col=0)
            except Exception:
                continue
            if df.empty:
                continue
            idx = pd.to_datetime(df.index, errors="coerce", utc=True)
            df = df.loc[~idx.isna()]
            df.index = idx[~idx.isna()]
            if df.empty:
                continue

            spd = cls._pick_series(df, _SPEED_COLS, "logger_speed")
            if spd is not None:
                spd_parts.append(spd)
            mass = cls._pick_series(df, _MASS_COLS, "logger_mass")
            if mass is not None:
                mass_parts.append(mass)

        speed_all = cls._finalise_local_logger(spd_parts, "速度")
        mass_all = cls._finalise_local_logger(mass_parts, "CVW 质量")
        return speed_all, mass_all

    @staticmethod
    def _pick_series(
        df: pd.DataFrame,
        candidates: tuple[str, ...],
        out_name: str,
    ) -> pd.Series | None:
        """按优先级从 logger CSV 取第一个可用通道列，返回去 NaN 的数值 Series。"""
        for col in candidates:
            if col in df.columns:
                s = pd.to_numeric(df[col], errors="coerce").dropna()
                if not s.empty:
                    return s.rename(out_name)
                # 该候选列全 NaN（如 hex / 缺采样），继续尝试下一候选
        return None

    @staticmethod
    def _finalise_local_logger(
        parts: list[pd.Series],
        label: str,
    ) -> pd.DataFrame | None:
        """合并各 leg 的单通道 Series 为按时间排序的单列 DataFrame。"""
        if not parts:
            logger.info("  本地 Logger 中无 %s 数据", label)
            return None
        df = pd.concat(parts).sort_index().to_frame()
        logger.info("  本地 Logger %s 数据: %d 条", label, len(df))
        return df

    def _fetch_logger_data(
        self,
        reg_srf: str,
        ds: datetime.datetime,
        de: datetime.datetime,
    ) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
        """从 SRF API 获取 Logger 速度和 CVW 质量数据。"""
        params = {
            "start_time": srf_client.filter.between(
                datetime.datetime.combine(ds, datetime.time.min, datetime.timezone.utc),
                datetime.datetime.combine(de, datetime.time.max, datetime.timezone.utc),
            ),
            "sort": srf_client.sort.asc("startTime"),
        }

        logger_legs = []
        try:
            for leg in paging.paged_items(
                self._srf_data.legs.find_all(
                    **params, **{"trip.vehicle.registration": reg_srf}
                )
            ):
                try:
                    src = leg.trip.source or ""
                    if src.startswith("SRFLOGGER"):
                        logger_legs.append(leg)
                except AttributeError:
                    pass
        except Exception as exc:
            logger.warning("Logger legs 拉取失败: %s", exc)

        if not logger_legs:
            logger.info("  无 Logger legs")
            return None, None

        logger.info("  获取到 %d 个 Logger legs", len(logger_legs))

        # 速度数据
        spd_dfs = []
        mass_dfs = []
        for lg in logger_legs:
            avail = lg.types
            # 速度：优先 CCVS，备选 2 speed
            try:
                if "CCVS" in avail:
                    df_spd = lg.get_data_frame("CCVS", resolution="1s")
                    col = "CCVS wheel based vehicle speed"
                    if col in df_spd.columns:
                        spd_dfs.append(
                            df_spd[[col]].rename(columns={col: "logger_speed"})
                        )
                elif "2" in avail:
                    df_spd = lg.get_data_frame("2", resolution="1s")
                    col = "2 speed"
                    if col in df_spd.columns:
                        spd_dfs.append(
                            df_spd[[col]].rename(columns={col: "logger_speed"})
                        )
            except Exception:
                pass

            # 质量：CVW 优先，VW 备选
            try:
                if "CVW" in avail:
                    df_m = lg.get_data_frame("CVW", resolution="1s")
                    if _CVW_COL in df_m.columns:
                        mass_dfs.append(df_m[[_CVW_COL]])
                elif "VW" in avail:
                    df_m = lg.get_data_frame("VW", resolution="1s")
                    for col_c in ("VW axle weight", "VW cargo weight"):
                        if col_c in df_m.columns:
                            mass_dfs.append(
                                df_m[[col_c]].rename(columns={col_c: _CVW_COL})
                            )
                            break
            except Exception:
                pass

        speed_all = self._concat_tz(spd_dfs, "速度")
        mass_all = self._concat_tz(mass_dfs, "CVW 质量")
        return speed_all, mass_all

    @staticmethod
    def _concat_tz(dfs: list, label: str) -> pd.DataFrame | None:
        """合并多个 DataFrame 并统一时区。"""
        if not dfs:
            logger.info("  Logger 中无 %s 数据", label)
            return None
        df = pd.concat(dfs).sort_index()
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        logger.info("  Logger %s 数据: %d 条", label, len(df))
        return df

    @staticmethod
    def _slice_logger_data(
        df_leg: pd.DataFrame,
        logger_df: pd.DataFrame | None,
    ) -> pd.DataFrame | None:
        """将 Logger 数据切片到当前 leg 的时间窗口。"""
        if logger_df is None or logger_df.empty:
            return None
        try:
            times = pd.to_datetime(df_leg[TIME_COL], errors="coerce", utc=True)
            ts_s = times.min()
            ts_e = times.max()
            if pd.isna(ts_s) or pd.isna(ts_e):
                return None
            sliced = logger_df.loc[ts_s:ts_e]
            return sliced if not sliced.empty else None
        except Exception:
            return None
