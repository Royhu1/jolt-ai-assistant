"""
logger_patcher.py
=================
独立的 SRF Logger 数据补全工具。

读取已生成的 Excel 报告，从 SRF API 获取 Logger legs，
补全报告中缺失的 Logger Link、天气列和质量数据。

用法：
    from jolt_toolkit.report_generator.logger_patcher import LoggerPatcher
    patcher = LoggerPatcher()
    patcher.patch_file("excel_report_database/1.0.0/YK73WFN/jolt_report_YK73WFN_20250820_20250822.xlsx")
"""

from __future__ import annotations

import datetime
import logging
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
import srf_client
from srf_client import paging
from openpyxl import load_workbook
from openpyxl.styles import Font
from tqdm import tqdm

from jolt_toolkit.report_generator.paths import get_cache_dir, get_srf_api_root
from jolt_toolkit.report_generator.segment_algorithms import VEHICLE_CONFIG
from jolt_toolkit.report_generator.report_builder import (
    _find_overlap,
    _build_logger_url,
    _kinetics_corrected_energy_perf,
    _get_trip_speed_array,
)
from jolt_toolkit.report_generator.pedal_histogram import (
    compute_pedal_histogram,
    MIN_DISTANCE_FOR_PEDAL_KM,
    EEC2_COL,
    EBC1_COL,
)

logger = logging.getLogger(__name__)

# ── Excel 列索引 (1-based, openpyxl 约定) ────────────────────────────────
_COL_LEG_TYPE    = 2   # Leg Type
_COL_LOGGER_LINK = 5   # SRF Logger Link
_COL_START_TIME  = 6
_COL_END_TIME    = 9
_COL_MASS        = 16  # Vehicle Mass (kg)
_COL_MASS_CV     = 17  # Vehicle Mass CV (reliability)
_COL_TEMP        = 38
_COL_PRESSURE    = 39
_COL_HUMIDITY    = 40
_COL_WIND_SPEED  = 41
_COL_WIND_DIR    = 42

_COL_DISTANCE    = 13  # Distance (km)
_COL_ELEV_DIFF   = 15  # Elevation Difference (m)
_COL_ENERGY      = 22  # Energy Change (kWh)
_COL_EPERF_KIN   = 47  # Energy Performance Kinetics Corrected (kWh/km)
_COL_HIST_ACC    = 44  # Histogram of Accelerator Pedal Position
_COL_HIST_DEC    = 45  # Histogram of Decelerator Pedal Position

_WEATHER_COLS = (_COL_TEMP, _COL_PRESSURE, _COL_HUMIDITY, _COL_WIND_SPEED, _COL_WIND_DIR)

# ── Logger Channel 7 列名 ─────────────────────────────────────────────────
_W_TEMP   = '7 temperature'
_W_PRESS  = '7 pressure'
_W_HUMID  = '7 humidity'
_W_WIND_S = '7 wind speed'
_W_WIND_D = '7 wind direction'

# ── Logger CVW 列名 ──────────────────────────────────────────────────────
_CVW_COL = 'CVW gross combination vehicle weight'

_CARDINALS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']

# ── 充电类型正则（与 report_builder 一致）──────────────────────────────────
_CHARGE_RE = re.compile(r'^(AC|DC|Charge|Mix|estimated)', re.IGNORECASE)


# ── 工具函数 ──────────────────────────────────────────────────────────────

def _parse_report_filename(path: Path) -> tuple[str, str, str] | None:
    """从报告文件名解析 (reg, date_start, date_end)。"""
    m = re.match(r'jolt_report_(\w+)_(\d{8})_(\d{8})\.xlsx$', path.name)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)


def _cell_is_empty(cell) -> bool:
    """判断单元格是否为空。"""
    v = cell.value
    if v is None:
        return True
    if isinstance(v, str) and v.strip() == '':
        return True
    return False


def _cell_needs_weather(cell) -> bool:
    """判断天气单元格是否需要补全。"""
    v = cell.value
    if v is None:
        return True
    if isinstance(v, str) and (v.strip() == '' or v.strip().upper() == '=NA()'):
        return True
    return False


def _to_timestamp(dt_val):
    """将 openpyxl 读取的日期时间值转为 pd.Timestamp (UTC)。"""
    if dt_val is None:
        return None
    try:
        ts = pd.Timestamp(dt_val)
        if ts.tzinfo is None:
            ts = ts.tz_localize('UTC')
        return ts
    except Exception:
        return None


# ── 主类 ─────────────────────────────────────────────────────────────────

class LoggerPatcher:
    """
    SRF Logger 数据补全工具。

    读取已生成的 xlsx 报告文件，从 SRF API 获取 Logger legs，
    通过时间窗口匹配补全 Logger Link URL 和天气列。

    补全内容：
    - SRF Logger Link — 可点击的 Logger 可视化 URL
    - Average Temperature / Pressure / Humidity / Wind Speed / Wind Direction
      — 从 Logger Channel 7 天气数据按时间窗口平均
    - Vehicle Mass (kg) + CV — 从 Logger CVW 通道按时间窗口取中位数
      （仅当报告中该行无有效质量数据时补全，不覆盖已有值）
    - Energy Performance Kinetics Corrected (kWh/km) — 使用 Logger 1Hz 速度数据
      逐秒计算动能修正后的能量效率（90% 再生制动效率）

    Args:
        srf_data:    可选的已有 SRF 客户端实例（共享连接以避免重复创建）
        cache_dir:   SRF API 缓存目录
    """

    def __init__(self, srf_data=None, cache_dir: str | None = None):
        if cache_dir is None:
            cache_dir = str(get_cache_dir())
        if srf_data is not None:
            self._srf_data = srf_data
        else:
            api_key = os.environ.get("SRF_API_KEY")
            if not api_key:
                logger.warning("LoggerPatcher: SRF_API_KEY 未设置")
            cache = None
            if cache_dir:
                from cachecontrol.caches import SeparateBodyFileCache
                srf_cache_path = os.path.join(cache_dir, "srf_http")
                os.makedirs(srf_cache_path, exist_ok=True)
                cache = SeparateBodyFileCache(srf_cache_path)
            self._srf_data = srf_client.SRFData(
                api_key=api_key, cache=cache,
                root=get_srf_api_root(), verify=True,
            )

    # ── 公开接口 ──────────────────────────────────────────────────────────

    def patch_file(self, xlsx_path: str | Path, *,
                   logger_legs: list | None = None,
                   logger_windows: list | None = None) -> int:
        """
        补全单个 xlsx 报告的 Logger Link 和天气数据。

        Args:
            xlsx_path:       报告文件路径
            logger_legs:     可选的预加载 Logger leg 对象列表
            logger_windows:  可选的预加载 Logger 时间窗口列表 [(start, end, uri), ...]
                             若 logger_legs 和 logger_windows 均为 None，从 SRF API 获取

        Returns:
            补全的行数（Link 或天气至少补全一列即计数）。
        """
        xlsx_path = Path(xlsx_path)
        if not xlsx_path.exists():
            logger.error("文件不存在: %s", xlsx_path)
            return 0

        # 1. 获取 logger 数据
        if logger_legs is None or logger_windows is None:
            fetched = self._fetch_logger_data(xlsx_path)
            if fetched is None:
                return 0
            if logger_legs is None:
                logger_legs = fetched[0]
            if logger_windows is None:
                logger_windows = fetched[1]

        if not logger_legs and not logger_windows:
            logger.info("LoggerPatcher: 无 Logger 数据，跳过 %s", xlsx_path.name)
            return 0

        # 2. 预加载 Channel 7 天气数据 + CVW 质量数据 + CCVS 速度数据 + 踏板数据
        weather_df = self._load_weather_data(logger_legs)
        mass_df = self._load_mass_data(logger_legs)
        speed_df = self._load_speed_data(logger_legs)
        acc_pedal_df = self._load_pedal_data(logger_legs, channel='EEC2')
        dec_pedal_df = self._load_pedal_data(logger_legs, channel='EBC1')

        # 3. 打开 xlsx
        logger.info("LoggerPatcher: 补全 %s", xlsx_path.name)
        wb = load_workbook(str(xlsx_path))
        if 'Report' not in wb.sheetnames:
            logger.error("  'Report' 工作表未找到: %s", xlsx_path.name)
            wb.close()
            return 0
        ws = wb['Report']

        # 4. 遍历行，补全 Link 和天气（仅放电/行程段，跳过充电段）
        patched = 0
        total_rows = ws.max_row - 1  # 减去标题行
        for row_idx in tqdm(range(2, ws.max_row + 1), desc="Logger 补全行",
                            total=total_rows, leave=False):
            # 充电段不应有 Logger 数据
            leg_type_val = ws.cell(row_idx, _COL_LEG_TYPE).value
            if leg_type_val and isinstance(leg_type_val, str) and _CHARGE_RE.match(leg_type_val):
                continue

            t_s = _to_timestamp(ws.cell(row_idx, _COL_START_TIME).value)
            t_e = _to_timestamp(ws.cell(row_idx, _COL_END_TIME).value)
            if t_s is None or t_e is None:
                continue

            row_patched = False

            # 4a. Logger Link
            if _cell_is_empty(ws.cell(row_idx, _COL_LOGGER_LINK)):
                uri = _find_overlap(logger_windows, t_s, t_e, tol_min=5)
                if uri:
                    url = _build_logger_url(uri, t_s, t_e)
                    if url:
                        cell = ws.cell(row_idx, _COL_LOGGER_LINK)
                        cell.value = 'Link'
                        cell.hyperlink = url
                        cell.font = Font(color='0000FF', underline='single')
                        row_patched = True

            # 4b. 天气数据
            if weather_df is not None and any(
                _cell_needs_weather(ws.cell(row_idx, c)) for c in _WEATHER_COLS
            ):
                matched = weather_df.loc[t_s:t_e]
                if not matched.empty:
                    if _W_TEMP in matched.columns:
                        ws.cell(row_idx, _COL_TEMP).value = round(
                            float(matched[_W_TEMP].mean()), 1)
                    if _W_PRESS in matched.columns:
                        ws.cell(row_idx, _COL_PRESSURE).value = round(
                            float(matched[_W_PRESS].mean()), 1)
                    if _W_HUMID in matched.columns:
                        ws.cell(row_idx, _COL_HUMIDITY).value = round(
                            float(matched[_W_HUMID].mean()), 1)
                    if _W_WIND_S in matched.columns:
                        ws.cell(row_idx, _COL_WIND_SPEED).value = round(
                            float(matched[_W_WIND_S].mean()), 1)
                    if _W_WIND_D in matched.columns:
                        wind_d = matched[_W_WIND_D].dropna()
                        if not wind_d.empty:
                            avg_deg = float(wind_d.mean())
                            ws.cell(row_idx, _COL_WIND_DIR).value = (
                                _CARDINALS[round(avg_deg / 45) % 8])
                    row_patched = True

            # 4c. 质量数据（仅当报告中无有效质量时补全）
            if mass_df is not None and _cell_needs_weather(ws.cell(row_idx, _COL_MASS)):
                matched_m = mass_df.loc[t_s:t_e]
                valid_m = matched_m[_CVW_COL].dropna()
                valid_m = valid_m[valid_m > 0]
                if len(valid_m) >= 5:
                    median_mass = float(np.median(valid_m.values))
                    cv = float(valid_m.std() / valid_m.mean()) if valid_m.mean() > 0 else None
                    ws.cell(row_idx, _COL_MASS).value = round(median_mass, 0)
                    if cv is not None:
                        ws.cell(row_idx, _COL_MASS_CV).value = round(cv, 3)
                    row_patched = True

            # 4d. 动能修正能量效率（使用 Logger 1Hz 速度数据逐秒计算）
            if speed_df is not None and _cell_needs_weather(ws.cell(row_idx, _COL_EPERF_KIN)):
                energy_val = ws.cell(row_idx, _COL_ENERGY).value
                dist_val = ws.cell(row_idx, _COL_DISTANCE).value
                elev_val = ws.cell(row_idx, _COL_ELEV_DIFF).value
                mass_val = ws.cell(row_idx, _COL_MASS).value
                if (energy_val is not None and dist_val is not None
                        and mass_val is not None):
                    try:
                        energy_kwh = float(energy_val)
                        distance_km = float(dist_val)
                        elevation_m = float(elev_val) if elev_val is not None else float('nan')
                        mass_kg = float(mass_val)
                        speed_arr = _get_trip_speed_array(speed_df, t_s, t_e)
                        if speed_arr is not None and distance_km > 0:
                            ep_kin = _kinetics_corrected_energy_perf(
                                energy_kwh, distance_km, elevation_m, mass_kg, speed_arr)
                            if not np.isnan(ep_kin):
                                ws.cell(row_idx, _COL_EPERF_KIN).value = ep_kin
                                row_patched = True
                    except (TypeError, ValueError):
                        pass

            # 4e. 踏板位置直方图（仅放电段，距离 > 10 km）
            dist_val = ws.cell(row_idx, _COL_DISTANCE).value
            try:
                dist_km = float(dist_val) if dist_val is not None else 0.0
            except (TypeError, ValueError):
                dist_km = 0.0

            if dist_km > MIN_DISTANCE_FOR_PEDAL_KM:
                # 油门踏板直方图
                if acc_pedal_df is not None and _cell_is_empty(ws.cell(row_idx, _COL_HIST_ACC)):
                    try:
                        acc_slice = acc_pedal_df.loc[t_s:t_e].dropna()
                        hist_str = compute_pedal_histogram(acc_slice, value_col=EEC2_COL)
                        if hist_str is not None:
                            ws.cell(row_idx, _COL_HIST_ACC).value = hist_str
                            row_patched = True
                    except Exception:
                        pass
                # 制动踏板直方图
                if dec_pedal_df is not None and _cell_is_empty(ws.cell(row_idx, _COL_HIST_DEC)):
                    try:
                        dec_slice = dec_pedal_df.loc[t_s:t_e].dropna()
                        hist_str = compute_pedal_histogram(dec_slice, value_col=EBC1_COL)
                        if hist_str is not None:
                            ws.cell(row_idx, _COL_HIST_DEC).value = hist_str
                            row_patched = True
                    except Exception:
                        pass

            if row_patched:
                patched += 1

        if patched > 0:
            wb.save(str(xlsx_path))
            logger.info("  补全 %d 行 (Logger Link + 天气 + 质量 + 动能修正 + 踏板直方图)，已保存", patched)
        else:
            logger.info("  无需补全 Logger 数据")

        wb.close()
        return patched

    def patch_folder(self, folder_path: str | Path) -> dict[str, int]:
        """补全文件夹下所有 jolt_report_*.xlsx 的 Logger 数据。"""
        folder = Path(folder_path)
        if not folder.is_dir():
            logger.error("文件夹不存在: %s", folder)
            return {}

        xlsx_files = sorted(folder.glob('jolt_report_*.xlsx'))
        if not xlsx_files:
            logger.info("LoggerPatcher: %s 下无报告文件", folder)
            return {}

        results = {}
        for fp in tqdm(xlsx_files, desc="Logger patch 文件"):
            results[fp.name] = self.patch_file(fp)
        return results

    # ── 内部方法 ──────────────────────────────────────────────────────────

    def _fetch_logger_data(self, xlsx_path: Path) -> tuple[list, list] | None:
        """从 SRF API 获取 Logger legs 和时间窗口。返回 (legs, windows) 或 None。"""
        parsed = _parse_report_filename(xlsx_path)
        if parsed is None:
            logger.error("  无法从文件名解析车辆信息: %s", xlsx_path.name)
            return None

        reg, ds_str, de_str = parsed
        cfg = VEHICLE_CONFIG.get(reg)
        if cfg is None:
            logger.error("  车辆 %s 未在 vehicles.json 中注册", reg)
            return None

        reg_srf = cfg["srf_reg"]
        ds = datetime.datetime.strptime(ds_str, "%Y%m%d")
        de = datetime.datetime.strptime(de_str, "%Y%m%d")

        logger.info("  从 SRF API 获取 Logger legs: %s  %s ~ %s", reg_srf, ds_str, de_str)
        params = {
            "start_time": srf_client.filter.between(
                datetime.datetime.combine(ds, datetime.time.min, datetime.timezone.utc),
                datetime.datetime.combine(de, datetime.time.max, datetime.timezone.utc),
            ),
            "sort": srf_client.sort.asc("startTime"),
        }

        legs = []
        windows = []
        try:
            for leg in paging.paged_items(
                self._srf_data.legs.find_all(
                    **params, **{"trip.vehicle.registration": reg_srf}
                )
            ):
                try:
                    src = leg.trip.source or ""
                    if src.startswith("SRFLOGGER"):
                        legs.append(leg)
                        windows.append((leg.start_time, leg.end_time, leg.uri))
                except AttributeError:
                    pass
        except Exception as exc:
            logger.warning("  Logger legs 拉取失败: %s", exc)
            return [], []

        logger.info("  获取到 %d 个 Logger legs", len(legs))
        return legs, windows

    def _load_weather_data(self, logger_legs: list) -> pd.DataFrame | None:
        """从所有 Logger legs 的 Channel 7 加载天气数据。"""
        if not logger_legs:
            return None

        dfs = []
        for leg in tqdm(logger_legs, desc="加载 Logger 天气", leave=False):
            try:
                if '7' not in leg.types:
                    continue
                df_w = leg.get_data_frame('7', resolution='1s')
                if df_w is not None and not df_w.empty:
                    dfs.append(df_w)
            except Exception as exc:
                logger.debug("  Logger 天气提取失败: %s", exc)

        if not dfs:
            logger.info("  Logger 中无 Channel 7 天气数据")
            return None

        weather_df = pd.concat(dfs).sort_index()
        if weather_df.index.tz is None:
            weather_df.index = weather_df.index.tz_localize('UTC')
        else:
            weather_df.index = weather_df.index.tz_convert('UTC')
        logger.info("  从 Logger 提取到 %d 条天气读数", len(weather_df))
        return weather_df

    def _load_mass_data(self, logger_legs: list) -> pd.DataFrame | None:
        """从所有 Logger legs 的 CVW 通道加载质量数据。"""
        if not logger_legs:
            return None

        dfs = []
        for leg in tqdm(logger_legs, desc="加载 Logger CVW", leave=False):
            try:
                if 'CVW' not in leg.types:
                    continue
                df_m = leg.get_data_frame('CVW', resolution='1s')
                if df_m is not None and not df_m.empty and _CVW_COL in df_m.columns:
                    dfs.append(df_m[[_CVW_COL]])
            except Exception as exc:
                logger.debug("  Logger CVW 提取失败: %s", exc)

        if not dfs:
            logger.info("  Logger 中无 CVW 质量数据")
            return None

        mass_df = pd.concat(dfs).sort_index()
        if mass_df.index.tz is None:
            mass_df.index = mass_df.index.tz_localize('UTC')
        else:
            mass_df.index = mass_df.index.tz_convert('UTC')
        logger.info("  从 Logger 提取到 %d 条 CVW 质量读数", len(mass_df))
        return mass_df

    def _load_speed_data(self, logger_legs: list) -> pd.DataFrame | None:
        """从所有 Logger legs 的 CCVS 通道加载车轮速度数据（用于动能修正）。"""
        if not logger_legs:
            return None

        dfs = []
        for leg in tqdm(logger_legs, desc="加载 Logger speed", leave=False):
            try:
                avail = leg.types
                if 'CCVS' in avail:
                    df_spd = leg.get_data_frame('CCVS', resolution='1s')
                    col = 'CCVS wheel based vehicle speed'
                    if col in df_spd.columns:
                        dfs.append(df_spd[[col]].rename(columns={col: 'logger_speed'}))
                elif '2' in avail:
                    df_spd = leg.get_data_frame('2', resolution='1s')
                    col = '2 speed'
                    if col in df_spd.columns:
                        dfs.append(df_spd[[col]].rename(columns={col: 'logger_speed'}))
            except Exception as exc:
                logger.debug("  Logger CCVS 速度提取失败: %s", exc)

        if not dfs:
            logger.info("  Logger 中无 CCVS 速度数据")
            return None

        speed_df = pd.concat(dfs).sort_index()
        if speed_df.index.tz is None:
            speed_df.index = speed_df.index.tz_localize('UTC')
        else:
            speed_df.index = speed_df.index.tz_convert('UTC')
        logger.info("  从 Logger 提取到 %d 条 CCVS 速度读数", len(speed_df))
        return speed_df

    def _load_pedal_data(self, logger_legs: list,
                         channel: str = 'EEC2') -> pd.DataFrame | None:
        """从所有 Logger legs 加载踏板位置数据。

        Args:
            logger_legs: Logger leg 对象列表
            channel: 'EEC2'（油门踏板）或 'EBC1'（制动踏板）

        Returns:
            DataFrame（索引为 UTC 时间戳，列为踏板位置百分比）或 None
        """
        if not logger_legs:
            return None

        col_map = {
            'EEC2': EEC2_COL,
            'EBC1': EBC1_COL,
        }
        target_col = col_map.get(channel)
        if target_col is None:
            return None

        dfs = []
        for leg in tqdm(logger_legs, desc=f"加载 Logger {channel}", leave=False):
            try:
                if channel not in leg.types:
                    continue
                df_p = leg.get_data_frame(channel, resolution='1s')
                if df_p is not None and not df_p.empty and target_col in df_p.columns:
                    dfs.append(df_p[[target_col]])
            except Exception as exc:
                logger.debug("  Logger %s 提取失败: %s", channel, exc)

        if not dfs:
            logger.info("  Logger 中无 %s 踏板数据", channel)
            return None

        pedal_df = pd.concat(dfs).sort_index()
        if pedal_df.index.tz is None:
            pedal_df.index = pedal_df.index.tz_localize('UTC')
        else:
            pedal_df.index = pedal_df.index.tz_convert('UTC')
        logger.info("  从 Logger 提取到 %d 条 %s 踏板读数", len(pedal_df), channel)
        return pedal_df
