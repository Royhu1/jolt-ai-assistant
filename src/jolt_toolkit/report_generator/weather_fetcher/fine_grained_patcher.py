"""
fine_grained_patcher.py
=======================
精细化天气数据补全工具（FineGrainedWeatherPatcher）。

与 ``weather_patcher.WeatherPatcher`` 的区别：
    - 旧 patcher 只用 trip 起点 / 终点 2 个采样点，对长 trip 粒度过粗。
    - 本 patcher 在 raw_telematics CSV 中按 trip 时间窗筛选所有
      ``(eventDatetime, latitude, longitude)`` 三元组，按 ``min_sample_interval_s``
      下采样（默认 60 s），对每个采样点查 OpenWeather History API，
      最后按列聚合：
        * 数值列（temp / pressure / humidity / wind_speed / wind_deg）→ 平均
          （wind_deg 在写入前转 8 方位 cardinal string，与旧 patcher 一致）
        * 文字列（Weather Type / Description）→ 众数（mode）

cache 设计：
    与旧 patcher 同样的 JSON schema，但默认放在
    ``cache/weather/.weather_cache_fine.json``（避免污染旧主 cache）。
    Key 仍是 ``"{lat:.{precision}f},{lon:.{precision}f},{dt}"``，精度可配置：
        precision=2  → ~1 km 网格（约 0.01°），时间桶按 hour 量化
        precision=4  → ~10 m 网格（默认仍走 hour 时间桶）
    时间桶通过构造参数 ``time_bucket_s`` 控制（默认 3600，即按小时聚合，因
    OpenWeather timemachine API 是小时粒度的）。

用法：
    from jolt_toolkit.report_generator.weather_fetcher.fine_grained_patcher \
        import FineGrainedWeatherPatcher
    patcher = FineGrainedWeatherPatcher(
        raw_telematics_dir="excel_report_database/2.2.2/YK73WFN/raw_telematics",
        min_sample_interval_s=60,
    )
    patcher.patch_file("excel_report_database/2.2.2/YK73WFN/jolt_report_*.xlsx")

注意：
    - patcher 是独立后置工具，**不嵌入** ``generate_report()`` 流程，与旧
      ``WeatherPatcher`` 一致。
    - 删除 cache 文件不会破坏可恢复性（cache 只是 API 结果的本地副本）。
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests
from filelock import FileLock
from openpyxl import load_workbook
from tqdm import tqdm

from jolt_toolkit.report_generator.report_builder import HEADERS, DIESEL_HEADERS

logger = logging.getLogger(__name__)

# ── Excel 列名集（与 HEADERS / DIESEL_HEADERS 对齐，1-based 索引动态推导）────
_TEMP_COL_NAME        = 'Average Temperature (C)'
_PRESS_COL_NAME       = 'Average Pressure (hPa)'
_HUMID_COL_NAME       = 'Average Humidity (%)'
_WIND_SPEED_COL_NAME  = 'Average Wind Speed (m/s)'
_WIND_DIR_COL_NAME    = 'Average Wind Direction'
_WEATHER_TYPE_NAME    = 'Weather Type'
_LEG_TYPE_COL_NAME    = 'Leg Type'
_START_TIME_COL_NAME  = 'Start Time (UTC)'
_END_TIME_COL_NAME    = 'End Time (UTC)'
_ORIGIN_COL_NAME      = 'Origin (Lat, Lon)'
_DEST_COL_NAME        = 'Destination (Lat, Lon)'


# ── 通用工具 ─────────────────────────────────────────────────────────────

def _resolve_col_indices(headers: tuple) -> dict[str, int]:
    """从 HEADERS 元组动态推导 1-based 列索引。"""
    return {
        'leg_type':     headers.index(_LEG_TYPE_COL_NAME) + 1,
        'start_time':   headers.index(_START_TIME_COL_NAME) + 1,
        'end_time':     headers.index(_END_TIME_COL_NAME) + 1,
        'origin':       headers.index(_ORIGIN_COL_NAME) + 1,
        'destination':  headers.index(_DEST_COL_NAME) + 1,
        'temp':         headers.index(_TEMP_COL_NAME) + 1,
        'pressure':     headers.index(_PRESS_COL_NAME) + 1,
        'humidity':     headers.index(_HUMID_COL_NAME) + 1,
        'wind_speed':   headers.index(_WIND_SPEED_COL_NAME) + 1,
        'wind_dir':     headers.index(_WIND_DIR_COL_NAME) + 1,
        'weather_type': headers.index(_WEATHER_TYPE_NAME) + 1,
    }


def _parse_point(point_str) -> tuple[float | None, float | None]:
    """解析 'Point(lat lon)' 格式坐标字符串。"""
    if not point_str or not isinstance(point_str, str):
        return None, None
    m = re.match(r'Point\(([+-]?\d+\.?\d*)\s+([+-]?\d+\.?\d*)\)', point_str)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None


def _deg_to_cardinal(deg: float) -> str:
    """角度 → 8 方位 cardinal。"""
    directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    idx = round(deg / 45) % 8
    return directions[idx]


def _to_utc_dt(dt_val) -> datetime | None:
    """openpyxl 读取的日期值 → UTC datetime。"""
    if dt_val is None:
        return None
    if isinstance(dt_val, datetime):
        if dt_val.tzinfo is None:
            dt_val = dt_val.replace(tzinfo=timezone.utc)
        return dt_val
    return None


def _cell_needs_patch(cell) -> bool:
    """单元格为空 / =NA() / NaN 视为需补全。"""
    v = cell.value
    if v is None:
        return True
    if isinstance(v, str) and (v.strip() == '' or v.strip().upper() == '=NA()'):
        return True
    if isinstance(v, float) and np.isnan(v):
        return True
    return False


# ── API 密钥管理 + cache（与旧 patcher 同结构）───────────────────────────

class _KeyManager:
    """多 API key 轮转，从 OPENWEATHER_API_KEYS 环境变量加载。"""

    def __init__(self):
        keys_str = os.environ.get('OPENWEATHER_API_KEYS', '')
        self._keys = {
            k.strip(): {'active': True, 'usage': 0}
            for k in keys_str.split(',') if k.strip()
        }
        if self._keys:
            logger.info(f"FineGrainedWeatherPatcher: {len(self._keys)} API key(s) loaded")
        else:
            logger.warning("FineGrainedWeatherPatcher: OPENWEATHER_API_KEYS not set")

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


class _WeatherCache:
    """
    JSON 文件 cache，schema 与旧 ``WeatherPatcher._WeatherCache`` 兼容。

    cache value 增至 6 元素：(temp, pressure, humidity, wind_speed, wind_deg, weather_type)
    与旧 weather_patcher.py 的 6 元素结构一致。
    """

    def __init__(self, cache_file: str | Path, precision: int = 4,
                 time_bucket_s: int = 3600):
        self._path = Path(cache_file)
        self._lock_path = Path(str(cache_file) + '.lock')
        self._precision = precision
        self._time_bucket_s = max(int(time_bucket_s), 1)
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, 'w', encoding='utf-8') as f:
                json.dump({
                    "metadata": {
                        "version": "1.0",
                        "precision": self._precision,
                        "time_bucket_s": self._time_bucket_s,
                        "description": (
                            "FineGrainedWeatherPatcher cache "
                            "(value = [temp, pressure, humidity, wind_speed, "
                            "wind_deg, weather_type])"
                        ),
                    },
                    "cache": {},
                }, f, indent=2)
            logger.info(f"Initialized fine-grained cache: {self._path}")

    def _key(self, lat: float, lon: float, dt: int) -> str:
        # 时间量化到 bucket（OpenWeather timemachine 是小时粒度，3600s 足够）
        dt_bucket = (int(dt) // self._time_bucket_s) * self._time_bucket_s
        return f"{lat:.{self._precision}f},{lon:.{self._precision}f},{dt_bucket}"

    def get_batch(self, locations: list[tuple]) -> tuple[dict, list]:
        """returns (hit_map: {loc: weather_tuple}, miss_list)."""
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


# ── raw_telematics CSV 缓存 ──────────────────────────────────────────────

class _RawTelematicsIndex:
    """
    raw_telematics 目录索引：按需懒加载 CSV，提取
    ``(timestamp_utc, latitude, longitude)`` 序列，缓存在内存里。

    每个 CSV 文件覆盖一天（命名 ``raw_YYYY-MM-DD_NNNN.csv``）。
    """

    def __init__(self, raw_dir: Path):
        self._raw_dir = Path(raw_dir)
        # date(str YYYY-MM-DD) → DataFrame[ts, lat, lon]
        self._cache: dict[str, pd.DataFrame] = {}
        # 文件名按日期 prefix 索引
        self._date_to_file: dict[str, Path] = {}
        if self._raw_dir.is_dir():
            for fp in self._raw_dir.glob('raw_*.csv'):
                m = re.match(r'raw_(\d{4}-\d{2}-\d{2})_\d+\.csv$', fp.name)
                if m:
                    self._date_to_file[m.group(1)] = fp

    @property
    def available(self) -> bool:
        return bool(self._date_to_file)

    # raw_telematics CSV 的两套经纬度 schema（按优先级排列）：
    #   早期 CSV（约 ≤2025-10）同时有 gnss_latitude/longitude 与
    #     latitude/longitude，两套数值完全相同（实测 max abs diff = 0）。
    #   近期 CSV（约 2025-11 起）只剩 latitude/longitude，gnss_* 列被移除。
    # 优先 gnss_*（与 canonical 历史一致），缺失时回退 latitude/longitude，
    # 使两种 schema 都能读进、都走真正的多点采样。
    _LAT_CANDIDATES = ('gnss_latitude', 'latitude')
    _LON_CANDIDATES = ('gnss_longitude', 'longitude')

    def _load_day(self, date_str: str) -> Optional[pd.DataFrame]:
        if date_str in self._cache:
            return self._cache[date_str]
        fp = self._date_to_file.get(date_str)
        if fp is None or not fp.is_file():
            self._cache[date_str] = pd.DataFrame(columns=['ts', 'lat', 'lon'])
            return self._cache[date_str]

        # 先探测实际表头，再按存在的列选 usecols；缺 gnss_* 不再硬抛
        # "Usecols do not match columns"（近期 CSV 因此读不进、退化成两端点）。
        try:
            available = set(pd.read_csv(fp, nrows=0).columns)
        except Exception as exc:
            logger.warning(f"Failed to read header of {fp.name}: {exc}")
            self._cache[date_str] = pd.DataFrame(columns=['ts', 'lat', 'lon'])
            return self._cache[date_str]

        lat_cols = [c for c in self._LAT_CANDIDATES if c in available]
        lon_cols = [c for c in self._LON_CANDIDATES if c in available]
        if 'eventDatetime' not in available or not lat_cols or not lon_cols:
            logger.warning(
                f"{fp.name}: missing eventDatetime / lat / lon columns "
                f"(lat={lat_cols}, lon={lon_cols}); skipping"
            )
            self._cache[date_str] = pd.DataFrame(columns=['ts', 'lat', 'lon'])
            return self._cache[date_str]

        usecols = ['eventDatetime', *lat_cols, *lon_cols]
        try:
            df = pd.read_csv(fp, usecols=usecols, low_memory=False)
        except Exception as exc:
            logger.warning(f"Failed to read {fp.name}: {exc}")
            self._cache[date_str] = pd.DataFrame(columns=['ts', 'lat', 'lon'])
            return self._cache[date_str]

        # 优先 gnss_*（候选列已按优先级排序），缺值回退 latitude/longitude
        lat = pd.to_numeric(df[lat_cols[0]], errors='coerce')
        for c in lat_cols[1:]:
            lat = lat.fillna(pd.to_numeric(df[c], errors='coerce'))
        lon = pd.to_numeric(df[lon_cols[0]], errors='coerce')
        for c in lon_cols[1:]:
            lon = lon.fillna(pd.to_numeric(df[c], errors='coerce'))
        ts = pd.to_datetime(df['eventDatetime'], utc=True, errors='coerce')

        df_out = pd.DataFrame({'ts': ts, 'lat': lat, 'lon': lon}).dropna()
        df_out = df_out.sort_values('ts').reset_index(drop=True)
        self._cache[date_str] = df_out
        return df_out

    def slice_trip(self, t_start: datetime, t_end: datetime) -> pd.DataFrame:
        """提取 [t_start, t_end] 时间窗内所有 GPS 点（跨天合并）。"""
        if t_start.tzinfo is None:
            t_start = t_start.replace(tzinfo=timezone.utc)
        if t_end.tzinfo is None:
            t_end = t_end.replace(tzinfo=timezone.utc)

        ts_start = pd.Timestamp(t_start).tz_convert('UTC')
        ts_end = pd.Timestamp(t_end).tz_convert('UTC')

        dfs = []
        cur = ts_start.normalize()
        last = ts_end.normalize()
        while cur <= last:
            date_str = cur.strftime('%Y-%m-%d')
            df_day = self._load_day(date_str)
            if df_day is not None and not df_day.empty:
                dfs.append(df_day)
            cur = cur + pd.Timedelta(days=1)

        if not dfs:
            return pd.DataFrame(columns=['ts', 'lat', 'lon'])

        df_all = pd.concat(dfs, ignore_index=True)
        mask = (df_all['ts'] >= ts_start) & (df_all['ts'] <= ts_end)
        return df_all.loc[mask].reset_index(drop=True)


def _downsample_by_interval(df: pd.DataFrame, min_interval_s: int) -> pd.DataFrame:
    """
    按时间间隔下采样：保留首行，后续行只保留与上一保留行 timestamp 差
    ≥ ``min_interval_s`` 的。
    """
    if df.empty:
        return df
    if min_interval_s <= 0:
        return df.reset_index(drop=True)

    keep_idx = [0]
    last_ts = df['ts'].iloc[0]
    interval = pd.Timedelta(seconds=min_interval_s)
    for i in range(1, len(df)):
        ts = df['ts'].iloc[i]
        if ts - last_ts >= interval:
            keep_idx.append(i)
            last_ts = ts
    return df.iloc[keep_idx].reset_index(drop=True)


# ── 主类 ─────────────────────────────────────────────────────────────────

class FineGrainedWeatherPatcher:
    """
    精细化天气数据补全工具。

    Args:
        raw_telematics_dir:     raw_*.csv 所在目录（一般是
                                ``excel_report_database/{ver}/{REG}/raw_telematics/``）。
                                若 None，则尝试自动定位 xlsx 同级 raw_telematics 目录。
        min_sample_interval_s:  trip 内最小采样间隔（秒，默认 60）。
        cache_file:             cache JSON 文件路径，默认
                                ``cache/weather/.weather_cache_fine.json``。
        precision:              坐标量化精度（默认 2，约 1 km 网格）。
                                OpenWeather timemachine 本身按小时返回历史数据，
                                ~1 km 内的气温/风速变化可忽略，所以 precision=2
                                既能保证精度又能大幅提高跨车 cache 命中率。
        time_bucket_s:          时间桶大小（默认 3600，按小时聚合）。
        max_workers:            并发 API 请求数（默认 20）。
        headers:                列结构，默认为 EV ``HEADERS``；柴油传 ``DIESEL_HEADERS``。
    """

    API_URL = "https://api.openweathermap.org/data/3.0/onecall/timemachine"

    def __init__(
        self,
        raw_telematics_dir: str | Path | None = None,
        min_sample_interval_s: int = 60,
        cache_file: str | Path | None = None,
        precision: int = 2,
        time_bucket_s: int = 3600,
        max_workers: int = 20,
        headers: tuple = HEADERS,
    ):
        self._raw_dir = Path(raw_telematics_dir) if raw_telematics_dir else None
        self._raw_index: Optional[_RawTelematicsIndex] = None
        self._min_interval = max(int(min_sample_interval_s), 0)
        self._headers = headers
        self._col_idx = _resolve_col_indices(headers)

        cache_file = cache_file or os.environ.get(
            'WEATHER_CACHE_FILE_FINE',
            './cache/weather/.weather_cache_fine.json',
        )
        self._cache = _WeatherCache(cache_file, precision=precision,
                                    time_bucket_s=time_bucket_s)
        self._keys = _KeyManager()
        self._lock = threading.Lock()
        self._max_workers = max_workers

        # 统计计数器（每次 patch_file 重置）
        self._stat_api_calls = 0
        self._stat_cache_hits = 0
        self._stat_failures = 0

    # ── 公开接口 ──────────────────────────────────────────────────────────

    def patch_file(self, xlsx_path: str | Path,
                   overwrite: bool = True,
                   force_repatch: bool = False) -> dict:
        """
        补全单个 xlsx 报告。

        Args:
            xlsx_path:     目标 xlsx 文件。
            overwrite:     True 直接覆盖原文件；False 写入 ``*_fineweather.xlsx``。
            force_repatch: True 时忽略 ``_cell_needs_patch`` 判定，对所有 trip-like
                           行重写天气列（用于 fine-grained 重算覆盖旧 coarse 结果）。

        Returns:
            统计 dict: ``{patched_rows, total_samples, api_calls, cache_hits, failures}``.
        """
        xlsx_path = Path(xlsx_path)
        if not xlsx_path.exists():
            logger.error(f"File not found: {xlsx_path}")
            return {'patched_rows': 0, 'total_samples': 0,
                    'api_calls': 0, 'cache_hits': 0, 'failures': 0}

        # 自动定位 raw_telematics
        raw_dir = self._raw_dir or (xlsx_path.parent / 'raw_telematics')
        self._raw_index = _RawTelematicsIndex(raw_dir)
        if not self._raw_index.available:
            logger.error(
                f"raw_telematics directory not found or empty: {raw_dir}. "
                f"FineGrainedWeatherPatcher requires --debug raw CSVs."
            )
            return {'patched_rows': 0, 'total_samples': 0,
                    'api_calls': 0, 'cache_hits': 0, 'failures': 0}

        logger.info(f"Fine-grained patching: {xlsx_path.name} "
                    f"(min_interval={self._min_interval}s)")
        wb = load_workbook(str(xlsx_path))
        if 'Report' not in wb.sheetnames:
            logger.error(f"  'Report' sheet not found")
            wb.close()
            return {'patched_rows': 0, 'total_samples': 0,
                    'api_calls': 0, 'cache_hits': 0, 'failures': 0}
        ws = wb['Report']

        # 重置统计
        self._stat_api_calls = 0
        self._stat_cache_hits = 0
        self._stat_failures = 0

        # 1. 扫描需要补全的行（只处理 trip-like leg：含 Trip / In Transit）
        weather_cols = (
            self._col_idx['temp'], self._col_idx['pressure'],
            self._col_idx['humidity'], self._col_idx['wind_speed'],
            self._col_idx['wind_dir'], self._col_idx['weather_type'],
        )
        tasks: list[dict] = []
        total_rows = ws.max_row - 1
        for row_idx in range(2, ws.max_row + 1):
            if not force_repatch:
                if not any(_cell_needs_patch(ws.cell(row_idx, c)) for c in weather_cols):
                    continue

            leg_type = ws.cell(row_idx, self._col_idx['leg_type']).value
            t_s = _to_utc_dt(ws.cell(row_idx, self._col_idx['start_time']).value)
            t_e = _to_utc_dt(ws.cell(row_idx, self._col_idx['end_time']).value)
            if t_s is None or t_e is None:
                continue

            # 充电 / Stop leg：raw_telematics 里没有移动 GPS 序列，fallback
            # 用 origin/dest 两点（与旧 patcher 一致）。
            is_moving = isinstance(leg_type, str) and \
                ('Trip' in leg_type or 'Transit' in leg_type)

            origin_pt = _parse_point(ws.cell(row_idx, self._col_idx['origin']).value)
            dest_pt = _parse_point(ws.cell(row_idx, self._col_idx['destination']).value)

            tasks.append({
                'row': row_idx,
                't_s': t_s,
                't_e': t_e,
                'is_moving': bool(is_moving),
                'origin': origin_pt,
                'dest': dest_pt,
            })

        if not tasks:
            logger.info(f"  No rows need weather patching")
            wb.close()
            return {'patched_rows': 0, 'total_samples': 0,
                    'api_calls': 0, 'cache_hits': 0, 'failures': 0}

        logger.info(f"  {len(tasks)} rows need weather data (of {total_rows} total)")

        # 2. 为每个 task 收集采样点 (lat, lon, dt_unix)
        task_samples: dict[int, list[tuple[float, float, int]]] = {}
        all_locs: set[tuple] = set()
        total_samples = 0

        for t in tasks:
            samples = self._collect_samples_for_trip(t)
            task_samples[t['row']] = samples
            for loc in samples:
                all_locs.add(loc)
            total_samples += len(samples)

        logger.info(f"  Collected {total_samples} samples across {len(tasks)} rows, "
                    f"{len(all_locs)} unique (after cache-key quantization)")

        # 3. 查 cache + 拉 API
        all_locs_list = list(all_locs)
        weather_map, missing = self._cache.get_batch(all_locs_list)
        self._stat_cache_hits = len(weather_map)
        logger.info(f"  {self._stat_cache_hits}/{len(all_locs_list)} cache hits, "
                    f"{len(missing)} need API")

        if missing:
            fetched = self._fetch_batch(missing)
            weather_map.update(fetched)
            if fetched:
                self._cache.put_batch(fetched)
                logger.info(f"  Fetched and cached {len(fetched)} new entries")

        # 4. 聚合 + 写回 xlsx
        patched = 0
        for t in tasks:
            samples = task_samples[t['row']]
            agg = self._aggregate_weather(samples, weather_map)
            if agg is None:
                continue
            temp, press, humid, wind_s, wind_deg, w_type = agg
            ws.cell(t['row'], self._col_idx['temp']).value         = temp
            ws.cell(t['row'], self._col_idx['pressure']).value     = press
            ws.cell(t['row'], self._col_idx['humidity']).value     = humid
            ws.cell(t['row'], self._col_idx['wind_speed']).value   = wind_s
            ws.cell(t['row'], self._col_idx['wind_dir']).value     = _deg_to_cardinal(wind_deg)
            ws.cell(t['row'], self._col_idx['weather_type']).value = w_type
            patched += 1

        # 5. 保存
        if patched > 0:
            out_path = xlsx_path if overwrite else xlsx_path.with_name(
                xlsx_path.stem + '_fineweather' + xlsx_path.suffix)
            wb.save(str(out_path))
            logger.info(f"  Patched {patched} rows, saved {out_path.name}")
        else:
            logger.info(f"  No weather data available for any rows")
        wb.close()

        summary = self._keys.summary()
        logger.info(
            f"  Summary: {patched} rows patched, {total_samples} samples, "
            f"{self._stat_api_calls} API calls, {self._stat_cache_hits} cache hits, "
            f"{self._stat_failures} failures"
        )
        logger.info(
            f"  API keys: {summary['active']}/{summary['total_keys']} active, "
            f"{summary['total_usage']} total calls this session"
        )

        return {
            'patched_rows': patched,
            'total_samples': total_samples,
            'api_calls': self._stat_api_calls,
            'cache_hits': self._stat_cache_hits,
            'failures': self._stat_failures,
        }

    def patch_folder(self, folder_path: str | Path,
                     overwrite: bool = True,
                     force_repatch: bool = False) -> dict[str, dict]:
        """补全文件夹下所有 ``jolt_report_*.xlsx``（排除 ``*_finetuned.xlsx``）。"""
        folder = Path(folder_path)
        if not folder.is_dir():
            logger.error(f"Folder not found: {folder}")
            return {}
        xlsx_files = sorted(
            fp for fp in folder.glob('jolt_report_*.xlsx')
            if not fp.stem.endswith('_finetuned')
        )
        if not xlsx_files:
            logger.info(f"No jolt_report_*.xlsx files in {folder}")
            return {}

        results: dict[str, dict] = {}
        for fp in tqdm(xlsx_files, desc="fine-grained weather"):
            results[fp.name] = self.patch_file(
                fp, overwrite=overwrite, force_repatch=force_repatch,
            )
        return results

    # ── 采样收集 ──────────────────────────────────────────────────────────

    def _collect_samples_for_trip(self, task: dict) -> list[tuple[float, float, int]]:
        """
        为一条 trip 收集采样点。

        移动 leg：从 raw_telematics 切 [t_s, t_e] 时间窗，按
        ``min_sample_interval_s`` 下采样。若一个点都没有，fallback 到
        origin / dest 两端点。

        非移动 leg（充电 / Stop）：直接用 origin / dest 两端点（如果有）。
        """
        t_s, t_e = task['t_s'], task['t_e']
        origin = task['origin']
        dest = task['dest']

        samples: list[tuple[float, float, int]] = []

        if task['is_moving'] and self._raw_index is not None:
            df = self._raw_index.slice_trip(t_s, t_e)
            df = _downsample_by_interval(df, self._min_interval)
            for _, r in df.iterrows():
                lat = float(r['lat'])
                lon = float(r['lon'])
                ts = int(r['ts'].timestamp())
                samples.append((lat, lon, ts))

        # fallback: 起点 / 终点
        if not samples:
            o_lat, o_lon = origin
            d_lat, d_lon = dest
            if o_lat is not None and o_lon is not None:
                samples.append((o_lat, o_lon, int(t_s.timestamp())))
            if d_lat is not None and d_lon is not None:
                samples.append((d_lat, d_lon, int(t_e.timestamp())))

        return samples

    # ── 聚合 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _aggregate_weather(samples: list[tuple],
                           weather_map: dict) -> Optional[tuple]:
        """
        把若干 (lat, lon, dt) 样本对应的 weather tuple 聚合成单条 trip 级值。

        Returns: (temp, pressure, humidity, wind_speed, wind_deg, weather_type)
                 或 None（如果没一条样本拿到 weather）。
        """
        if not samples:
            return None
        temps, presses, humids, winds, degs, types = [], [], [], [], [], []
        for loc in samples:
            w = weather_map.get(loc)
            if w is None:
                continue
            # 兼容 5 元素 (老 cache) / 6 元素
            temps.append(float(w[0]))
            presses.append(float(w[1]))
            humids.append(float(w[2]))
            winds.append(float(w[3]))
            degs.append(float(w[4]))
            if len(w) > 5 and w[5] is not None:
                types.append(str(w[5]))
        if not temps:
            return None

        temp = round(float(np.mean(temps)), 1)
        press = round(float(np.mean(presses)), 1)
        humid = round(float(np.mean(humids)), 1)
        wind_s = round(float(np.mean(winds)), 1)
        # 风向用 sin/cos 取均值再反算（避免 359°/1° 平均回 180°）
        sin_mean = float(np.mean([np.sin(np.deg2rad(d)) for d in degs]))
        cos_mean = float(np.mean([np.cos(np.deg2rad(d)) for d in degs]))
        wind_deg = (np.rad2deg(np.arctan2(sin_mean, cos_mean)) + 360) % 360

        if types:
            cnt = Counter(types).most_common()
            w_type = cnt[0][0]  # 平手取首个
        else:
            w_type = None

        return temp, press, humid, wind_s, wind_deg, w_type

    # ── API 调用 ──────────────────────────────────────────────────────────

    def _fetch_single(self, loc: tuple) -> tuple[tuple, tuple | None]:
        lat, lon, dt = loc
        with self._lock:
            api_key = self._keys.get_key()
        if not api_key:
            with self._lock:
                self._stat_failures += 1
            return loc, None
        try:
            resp = requests.get(self.API_URL, params={
                'lat': lat, 'lon': lon, 'dt': dt, 'appid': api_key,
            }, timeout=10)
            if resp.status_code == 429:
                with self._lock:
                    self._keys.disable(api_key)
                    self._stat_failures += 1
                return loc, None
            if resp.status_code != 200:
                logger.debug(f"  HTTP {resp.status_code} for ({lat:.4f},{lon:.4f},dt={dt})")
                with self._lock:
                    self._stat_failures += 1
                return loc, None

            w = resp.json()['data'][0]
            with self._lock:
                self._keys.increment(api_key)
                self._stat_api_calls += 1

            weather_type = None
            if 'weather' in w and w['weather']:
                weather_type = w['weather'][0].get('main')
            return loc, (
                round(w['temp'] - 273.15, 1),
                w['pressure'],
                w['humidity'],
                w['wind_speed'],
                w['wind_deg'],
                weather_type,
            )
        except Exception as e:
            logger.debug(f"  API error ({lat:.4f},{lon:.4f}): {e}")
            with self._lock:
                self._stat_failures += 1
            return loc, None

    def _fetch_batch(self, locations: list[tuple]) -> dict:
        results: dict = {}
        logger.info(f"  Fetching {len(locations)} locations "
                    f"({self._max_workers} workers)...")
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {pool.submit(self._fetch_single, loc): loc
                       for loc in locations}
            for f in tqdm(as_completed(futures), desc="OpenWeather API",
                          total=len(futures), leave=False):
                loc, weather = f.result()
                if weather is not None:
                    results[loc] = weather
        return results
