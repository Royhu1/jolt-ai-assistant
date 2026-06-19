"""
charger_patcher.py
==================
独立的充电桩数据补全工具。

读取已生成的 Excel 报告，从 SRF API 获取充电桩事件，
补全报告中缺失的 Charger Link 列。

用法：
    from jolt_toolkit.report_generator.charger_patcher import ChargerPatcher
    patcher = ChargerPatcher()
    patcher.patch_file("excel_report_database/1.0.0/KY24LHT/jolt_report_KY24LHT_20250101_20250131.xlsx")
"""

from __future__ import annotations

import datetime
import logging
import os
import re
from pathlib import Path

import srf_client
from srf_client import paging
from openpyxl import load_workbook
from openpyxl.styles import Font

import pandas as pd

from jolt_toolkit.report_generator.segment_algorithms import VEHICLE_CONFIG
from jolt_toolkit.report_generator.report_builder import (
    _build_charger_url,
)

logger = logging.getLogger(__name__)

# ── Excel 列索引 (1-based, openpyxl 约定) ────────────────────────────────
_COL_LEG_TYPE       = 2
_COL_CHARGER        = 4   # Charger Link
_COL_START_TIME     = 6
_COL_END_TIME       = 9
_COL_CHARGER_ENERGY = 33  # Energy Output from Charger (kWh)


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
    return v is None or (isinstance(v, str) and v.strip() == '')


def _find_charger_match(windows: list, t_start, t_end, tol_min: float = 4):
    """
    在充电桩窗口列表中查找与 [t_start, t_end] 重叠的第一个条目。

    windows: list of (start, end, uri, energy_kwh)
    返回 (uri, energy_kwh) 或 None。
    """
    tol = pd.Timedelta(minutes=tol_min)
    t_s = pd.Timestamp(t_start)
    t_e = pd.Timestamp(t_end)
    if t_s.tzinfo is None:
        t_s = t_s.tz_localize('UTC')
    if t_e.tzinfo is None:
        t_e = t_e.tz_localize('UTC')
    ext_s = t_s - tol
    ext_e = t_e + tol
    for (ws, we, uri, energy_kwh) in windows:
        try:
            ws = pd.Timestamp(ws)
            we = pd.Timestamp(we)
            if ws.tzinfo is None:
                ws = ws.tz_localize('UTC')
            if we.tzinfo is None:
                we = we.tz_localize('UTC')
            if ws <= ext_e and we >= ext_s:
                return (uri, energy_kwh)
        except Exception:
            continue
    return None


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

class ChargerPatcher:
    """
    充电桩数据补全工具。

    读取已生成的 xlsx 报告文件，从 SRF API 获取充电桩事件，
    通过时间窗口匹配将 Charger Link URL 写入报告。

    Args:
        srf_data:    可选的已有 SRF 客户端实例（共享连接以避免重复创建）
        cache_dir:   SRF API 缓存目录
    """

    def __init__(self, srf_data=None, cache_dir: str = "./cache"):
        if srf_data is not None:
            self._srf_data = srf_data
        else:
            api_key = os.environ.get("SRF_API_KEY")
            if not api_key:
                logger.warning("ChargerPatcher: SRF_API_KEY 未设置")
            cache = None
            if cache_dir:
                from cachecontrol.caches import SeparateBodyFileCache
                srf_cache_path = os.path.join(cache_dir, "srf_http")
                os.makedirs(srf_cache_path, exist_ok=True)
                cache = SeparateBodyFileCache(srf_cache_path)
            self._srf_data = srf_client.SRFData(
                api_key=api_key, cache=cache,
                root="https://data.csrf.ac.uk/api/", verify=True,
            )

    # ── 公开接口 ──────────────────────────────────────────────────────────

    def patch_file(self, xlsx_path: str | Path, *,
                   charger_windows: list | None = None) -> int:
        """
        补全单个 xlsx 报告的 Charger Link。

        Args:
            xlsx_path:        报告文件路径
            charger_windows:  可选的预加载充电桩窗口列表 [(start, end, uri), ...]
                              若为 None，则从 SRF API 自动获取

        Returns:
            补全的行数。
        """
        xlsx_path = Path(xlsx_path)
        if not xlsx_path.exists():
            logger.error("文件不存在: %s", xlsx_path)
            return 0

        # 1. 获取 charger windows
        if charger_windows is None:
            charger_windows = self._fetch_charger_windows(xlsx_path)
            if charger_windows is None:
                return 0

        if not charger_windows:
            logger.info("ChargerPatcher: 无充电桩事件，跳过 %s", xlsx_path.name)
            return 0

        # 2. 打开 xlsx
        logger.info("ChargerPatcher: 补全 %s", xlsx_path.name)
        wb = load_workbook(str(xlsx_path))
        if 'Report' not in wb.sheetnames:
            logger.error("  'Report' 工作表未找到: %s", xlsx_path.name)
            wb.close()
            return 0
        ws = wb['Report']

        # 3. 遍历行，匹配充电段
        patched = 0
        for row_idx in range(2, ws.max_row + 1):
            if not _cell_is_empty(ws.cell(row_idx, _COL_CHARGER)):
                continue

            # 只对充电段补全 Charger Link
            leg_type = ws.cell(row_idx, _COL_LEG_TYPE).value
            if not isinstance(leg_type, str):
                continue
            if not any(kw in leg_type for kw in ('AC', 'DC')):
                continue

            t_s = _to_timestamp(ws.cell(row_idx, _COL_START_TIME).value)
            t_e = _to_timestamp(ws.cell(row_idx, _COL_END_TIME).value)
            if t_s is None or t_e is None:
                continue

            match = _find_charger_match(charger_windows, t_s, t_e, tol_min=4)
            if match is None:
                continue

            uri, energy_kwh = match
            url = _build_charger_url(uri, t_s, t_e)
            if url:
                cell = ws.cell(row_idx, _COL_CHARGER)
                cell.value = 'Link'
                cell.hyperlink = url
                cell.font = Font(color='0000FF', underline='single')
            if energy_kwh is not None:
                ws.cell(row_idx, _COL_CHARGER_ENERGY).value = round(energy_kwh, 3)
            patched += 1

        if patched > 0:
            wb.save(str(xlsx_path))
            logger.info("  补全 %d 行 Charger Link，已保存", patched)
        else:
            logger.info("  无需补全 Charger Link")

        wb.close()
        return patched

    def patch_folder(self, folder_path: str | Path) -> dict[str, int]:
        """补全文件夹下所有 jolt_report_*.xlsx 的 Charger Link。"""
        folder = Path(folder_path)
        if not folder.is_dir():
            logger.error("文件夹不存在: %s", folder)
            return {}

        xlsx_files = sorted(folder.glob('jolt_report_*.xlsx'))
        if not xlsx_files:
            logger.info("ChargerPatcher: %s 下无报告文件", folder)
            return {}

        results = {}
        for fp in xlsx_files:
            results[fp.name] = self.patch_file(fp)
        return results

    # ── 内部方法 ──────────────────────────────────────────────────────────

    def _fetch_charger_windows(self, xlsx_path: Path) -> list | None:
        """从 SRF API 获取充电桩事件窗口列表。"""
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

        logger.info("  从 SRF API 获取充电桩事件: %s  %s ~ %s", reg_srf, ds_str, de_str)
        params = {
            "start_time": srf_client.filter.between(
                datetime.datetime.combine(ds, datetime.time.min, datetime.timezone.utc),
                datetime.datetime.combine(de, datetime.time.max, datetime.timezone.utc),
            ),
            "sort": srf_client.sort.asc("startTime"),
        }

        windows = []
        try:
            for ct in paging.paged_items(
                self._srf_data.transactions.find_all(
                    **params, **{"vehicle.registration": reg_srf}
                )
            ):
                try:
                    energy_kwh = None
                    if ct.start_meter is not None and ct.end_meter is not None:
                        energy_kwh = ct.end_meter - ct.start_meter
                    windows.append((ct.start_time, ct.end_time, ct.uri, energy_kwh))
                except AttributeError:
                    pass
        except Exception as exc:
            logger.warning("  充电桩事件拉取失败: %s", exc)
            return []

        logger.info("  获取到 %d 个充电桩事件", len(windows))
        return windows
