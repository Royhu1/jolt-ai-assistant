"""
weather_patcher.py
==================
独立的天气数据补全工具。

读取已生成的 Excel 报告，通过 OpenWeather API 获取历史天气数据，
补全报告中缺失的天气列（温度、气压、湿度、风速、风向）。

用法：
    from jolt_toolkit.report_generator.weather_patcher import WeatherPatcher
    patcher = WeatherPatcher()
    patcher.patch_folder("excel_report_database/1.0.0/KY24LHT/")
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from filelock import FileLock
from openpyxl import load_workbook
from tqdm import tqdm

from jolt_toolkit.report_generator.report_builder import is_trip_leg

logger = logging.getLogger(__name__)

# ── Excel 列索引 (1-based, openpyxl 约定) ────────────────────────────────
_COL_LEG_TYPE   = 2
_COL_START_TIME = 6
_COL_ORIGIN     = 7
_COL_END_TIME   = 9
_COL_DEST       = 10
_COL_TEMP       = 38
_COL_PRESSURE   = 39
_COL_HUMIDITY   = 40
_COL_WIND_SPEED = 41
_COL_WIND_DIR      = 42
_COL_WEATHER_TYPE  = 43

_WEATHER_COLS = (_COL_TEMP, _COL_PRESSURE, _COL_HUMIDITY, _COL_WIND_SPEED, _COL_WIND_DIR, _COL_WEATHER_TYPE)


# ── 工具函数 ──────────────────────────────────────────────────────────────

def _parse_point(point_str) -> tuple[float | None, float | None]:
    """解析 'Point(lat lon)' 格式的坐标字符串。"""
    if not point_str or not isinstance(point_str, str):
        return None, None
    m = re.match(r'Point\(([+-]?\d+\.?\d*)\s+([+-]?\d+\.?\d*)\)', point_str)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None


def _deg_to_cardinal(deg: float) -> str:
    """角度 → 8 方位风向。"""
    directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    idx = round(deg / 45) % 8
    return directions[idx]


def _cell_needs_patch(cell) -> bool:
    """判断单元格是否需要补全天气数据（空值或 =NA() 公式）。"""
    v = cell.value
    if v is None:
        return True
    if isinstance(v, str) and (v.strip() == '' or v.strip().upper() == '=NA()'):
        return True
    return False


def _to_unix_utc(dt_val) -> int | None:
    """将 openpyxl 读取的日期时间值转为 UTC unix 时间戳。"""
    if dt_val is None:
        return None
    try:
        if isinstance(dt_val, datetime):
            # openpyxl 读取的 datetime 通常是 naive，报告中标注为 UTC
            if dt_val.tzinfo is None:
                dt_val = dt_val.replace(tzinfo=timezone.utc)
            return int(dt_val.timestamp())
        return None
    except (AttributeError, TypeError, ValueError):
        return None


# ── API 密钥管理 ─────────────────────────────────────────────────────────

class _KeyManager:
    """简化的多密钥轮转管理器（从 OPENWEATHER_API_KEYS 环境变量加载）。"""

    def __init__(self):
        keys_str = os.environ.get('OPENWEATHER_API_KEYS', '')
        self._keys = {
            k.strip(): {'active': True, 'usage': 0}
            for k in keys_str.split(',') if k.strip()
        }
        if self._keys:
            logger.info(f"WeatherPatcher: {len(self._keys)} API key(s) loaded")
        else:
            logger.warning("WeatherPatcher: OPENWEATHER_API_KEYS not set")

    def get_key(self) -> str | None:
        for k, v in self._keys.items():
            if v['active']:
                return k
        return None

    def increment(self, key: str):
        if key in self._keys:
            self._keys[key]['usage'] += 1

    def disable(self, key: str):
        if key in self._keys and self._keys[key]['active']:
            self._keys[key]['active'] = False
            masked = f"...{key[-8:]}" if len(key) > 8 else "***"
            logger.warning(f"Disabled API key: {masked}")

    def summary(self) -> dict:
        total = sum(v['usage'] for v in self._keys.values())
        active = sum(1 for v in self._keys.values() if v['active'])
        return {'total_keys': len(self._keys), 'active': active, 'total_usage': total}


# ── 天气缓存 ─────────────────────────────────────────────────────────────

class _WeatherCache:
    """JSON 文件缓存（filelock 线程安全）。"""

    def __init__(self, cache_file: str | Path, precision: int = 6):
        self._path = Path(cache_file)
        self._lock_path = Path(str(cache_file) + '.lock')
        self._precision = precision
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, 'w', encoding='utf-8') as f:
                json.dump({"cache": {}}, f)

    def _key(self, lat: float, lon: float, dt: int) -> str:
        return f"{lat:.{self._precision}f},{lon:.{self._precision}f},{dt}"

    def get_batch(self, locations: list[tuple]) -> tuple[dict, list]:
        """返回 (hit_map, miss_list)。hit_map: {loc: weather_tuple}。"""
        with FileLock(self._lock_path, timeout=10):
            with open(self._path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        cache = data.get("cache", {})
        hit_map: dict = {}
        misses: list = []
        for loc in locations:
            k = self._key(*loc)
            if k in cache:
                hit_map[loc] = tuple(cache[k])
            else:
                misses.append(loc)
        return hit_map, misses

    def put_batch(self, results: dict):
        """results: {(lat, lon, dt): (temp, press, humid, wind_s, wind_d, weather_type)}。"""
        with FileLock(self._lock_path, timeout=10):
            with open(self._path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            cache = data.get("cache", {})
            for loc, weather in results.items():
                cache[self._key(*loc)] = list(weather)
            data["cache"] = cache
            with open(self._path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    @property
    def size(self) -> int:
        with FileLock(self._lock_path, timeout=10):
            with open(self._path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        return len(data.get("cache", {}))


# ── 主类 ─────────────────────────────────────────────────────────────────

class WeatherPatcher:
    """
    天气数据补全工具。

    读取已生成的 xlsx 报告文件，通过 OpenWeather timemachine API
    获取出发地和目的地的历史天气数据，取平均值写入报告。

    仅补全 **行驶 / trip 行**（``is_trip_leg`` 判定）：充电段与 Stop 行不需要
    天气，且查询它们只会白白消耗 OpenWeather 配额，因此在收集坐标之前就被跳过
    （根本不进入唯一位置集合）。

    Args:
        cache_file:  缓存文件路径（默认 ./cache/.weather_cache.json）
        precision:   坐标缓存精度（小数位数，默认 6）
        max_workers: 并发请求数（默认 30）
    """

    API_URL = "https://api.openweathermap.org/data/3.0/onecall/timemachine"

    def __init__(self, cache_file: str | Path | None = None,
                 precision: int = 6, max_workers: int = 30):
        cache_file = cache_file or os.environ.get(
            'WEATHER_CACHE_FILE', './cache/.weather_cache.json')
        self._cache = _WeatherCache(cache_file, precision)
        self._keys = _KeyManager()
        self._lock = threading.Lock()
        self._max_workers = max_workers

    # ── 公开接口 ──────────────────────────────────────────────────────────

    def patch_file(self, xlsx_path: str | Path) -> int:
        """
        补全单个 xlsx 报告的天气数据。

        读取 Report 工作表中 **行驶 / trip 行** 的坐标和时间（充电 / Stop 行被
        跳过，见类 docstring），查询 OpenWeather API，将温度/气压/湿度/风速/风向
        写入对应列。

        Returns:
            补全的行数。
        """
        xlsx_path = Path(xlsx_path)
        if not xlsx_path.exists():
            logger.error(f"File not found: {xlsx_path}")
            return 0

        logger.info(f"Patching: {xlsx_path.name}")
        wb = load_workbook(str(xlsx_path))
        if 'Report' not in wb.sheetnames:
            logger.error(f"  'Report' sheet not found in {xlsx_path.name}")
            wb.close()
            return 0
        ws = wb['Report']

        # 1. 收集需要补全的行
        tasks = []  # (row_idx, o_lat, o_lon, o_dt, d_lat, d_lon, d_dt)
        total_rows = ws.max_row - 1  # 减去标题行
        for row_idx in tqdm(range(2, ws.max_row + 1), desc="扫描天气行",
                            total=total_rows, leave=False):  # 跳过标题行
            # Weather is backfilled on driving / trip rows ONLY. Charge and Stop
            # rows do not need weather, and querying them would only waste
            # OpenWeather quota, so skip any non-trip row before its coordinates
            # are ever collected (kept out of the unique-location set entirely).
            # ``is_trip_leg`` is the shared trip definition used by the chart
            # ``driving_only`` filter, so both agree on what a trip is.
            if not is_trip_leg(ws.cell(row_idx, _COL_LEG_TYPE).value):
                continue
            if not any(_cell_needs_patch(ws.cell(row_idx, c)) for c in _WEATHER_COLS):
                continue

            origin_str = ws.cell(row_idx, _COL_ORIGIN).value
            dest_str   = ws.cell(row_idx, _COL_DEST).value
            o_lat, o_lon = _parse_point(origin_str)
            d_lat, d_lon = _parse_point(dest_str)
            if o_lat is None or d_lat is None:
                continue

            o_dt = _to_unix_utc(ws.cell(row_idx, _COL_START_TIME).value)
            d_dt = _to_unix_utc(ws.cell(row_idx, _COL_END_TIME).value)
            if o_dt is None or d_dt is None:
                continue

            tasks.append((row_idx, o_lat, o_lon, o_dt, d_lat, d_lon, d_dt))

        if not tasks:
            logger.info(f"  No rows need weather patching in {xlsx_path.name}")
            wb.close()
            return 0

        logger.info(f"  {len(tasks)} rows need weather data")

        # 2. 收集所有唯一 (lat, lon, dt) 位置
        loc_set: set[tuple] = set()
        for _, o_lat, o_lon, o_dt, d_lat, d_lon, d_dt in tasks:
            loc_set.add((o_lat, o_lon, o_dt))
            loc_set.add((d_lat, d_lon, d_dt))
        all_locs = list(loc_set)

        # 3. 查缓存
        weather_map, missing = self._cache.get_batch(all_locs)
        logger.info(f"  {len(all_locs)} unique locations: "
                    f"{len(weather_map)} cached, {len(missing)} need API")

        # 4. 从 API 获取缺失数据
        if missing:
            fetched = self._fetch_batch(missing)
            weather_map.update(fetched)
            if fetched:
                self._cache.put_batch(fetched)
                logger.info(f"  Fetched and cached {len(fetched)} new locations")

        # 5. 写入 Excel
        patched = 0
        for row_idx, o_lat, o_lon, o_dt, d_lat, d_lon, d_dt in tasks:
            o_w = weather_map.get((o_lat, o_lon, o_dt))
            d_w = weather_map.get((d_lat, d_lon, d_dt))
            if o_w is None or d_w is None:
                continue

            avg_temp  = round((o_w[0] + d_w[0]) / 2, 1)
            avg_press = round((o_w[1] + d_w[1]) / 2, 1)
            avg_humid = round((o_w[2] + d_w[2]) / 2, 1)
            avg_wind  = round((o_w[3] + d_w[3]) / 2, 1)
            avg_dir   = (o_w[4] + d_w[4]) / 2
            cardinal  = _deg_to_cardinal(avg_dir)
            # 起点天气类型（兼容旧版 5 元素缓存）
            weather_type = o_w[5] if len(o_w) > 5 else None

            ws.cell(row_idx, _COL_TEMP).value          = avg_temp
            ws.cell(row_idx, _COL_PRESSURE).value       = avg_press
            ws.cell(row_idx, _COL_HUMIDITY).value        = avg_humid
            ws.cell(row_idx, _COL_WIND_SPEED).value     = avg_wind
            ws.cell(row_idx, _COL_WIND_DIR).value       = cardinal
            ws.cell(row_idx, _COL_WEATHER_TYPE).value   = weather_type
            patched += 1

        if patched > 0:
            wb.save(str(xlsx_path))
            logger.info(f"  Patched {patched} rows, saved {xlsx_path.name}")
        else:
            logger.info(f"  No weather data available for any rows")

        wb.close()

        summary = self._keys.summary()
        logger.info(f"  API keys: {summary['active']}/{summary['total_keys']} active, "
                    f"{summary['total_usage']} calls this session")

        return patched

    def patch_folder(self, folder_path: str | Path) -> dict[str, int]:
        """
        补全指定文件夹下所有 jolt_report_*.xlsx 报告的天气数据。

        Returns:
            {文件名: 补全行数} 字典。
        """
        folder = Path(folder_path)
        if not folder.is_dir():
            logger.error(f"Folder not found: {folder}")
            return {}

        xlsx_files = sorted(folder.glob('jolt_report_*.xlsx'))
        if not xlsx_files:
            logger.info(f"No jolt_report_*.xlsx files in {folder}")
            return {}

        logger.info(f"Found {len(xlsx_files)} report(s) in {folder}")
        results = {}
        for fp in tqdm(xlsx_files, desc="天气 patch 文件"):
            results[fp.name] = self.patch_file(fp)
        return results

    # ── 内部方法 ──────────────────────────────────────────────────────────

    def _fetch_single(self, loc: tuple) -> tuple[tuple, tuple | None]:
        """获取单个位置的天气数据（线程安全）。"""
        lat, lon, dt = loc
        with self._lock:
            api_key = self._keys.get_key()
        if not api_key:
            return loc, None

        try:
            resp = requests.get(self.API_URL, params={
                'lat': lat, 'lon': lon, 'dt': dt, 'appid': api_key
            }, timeout=10)

            if resp.status_code == 429:
                with self._lock:
                    self._keys.disable(api_key)
                return loc, None

            if resp.status_code != 200:
                logger.debug(f"  HTTP {resp.status_code} for ({lat:.4f}, {lon:.4f}, dt={dt})")
                return loc, None

            w = resp.json()['data'][0]

            with self._lock:
                self._keys.increment(api_key)

            # 提取天气类型（如 Clear, Clouds, Rain 等）
            weather_type = None
            if 'weather' in w and w['weather']:
                weather_type = w['weather'][0].get('main')

            return loc, (
                round(w['temp'] - 273.15, 1),  # K → C
                w['pressure'],                  # hPa
                w['humidity'],                  # %
                w['wind_speed'],                # m/s
                w['wind_deg'],                  # degrees
                weather_type,                   # 天气类型
            )
        except Exception as e:
            logger.debug(f"  API error for ({lat:.4f}, {lon:.4f}): {e}")
            return loc, None

    def _fetch_batch(self, locations: list[tuple]) -> dict:
        """并发获取多个位置的天气数据。"""
        results: dict = {}
        logger.info(f"  Fetching {len(locations)} locations "
                    f"({self._max_workers} workers)...")

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {pool.submit(self._fetch_single, loc): loc
                       for loc in locations}
            for f in tqdm(as_completed(futures), desc="获取天气 API",
                          total=len(futures), leave=False):
                loc, weather = f.result()
                if weather is not None:
                    results[loc] = weather

        failed = len(locations) - len(results)
        if failed > 0:
            logger.warning(f"  {failed}/{len(locations)} locations failed")

        return results
