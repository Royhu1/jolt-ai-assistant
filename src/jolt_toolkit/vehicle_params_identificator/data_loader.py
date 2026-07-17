"""
数据加载模块。
从 SRF API 下载 Logger 遥测数据（1s 分辨率），保存为 per-leg CSV。

支持两种能量来源：
- EEC1 (J1939): 电机转速 × 扭矩百分比 → 功率积分（需 max_torque_nm）
- Channel 6 SOC: SOC 变化 × 标称容量 → 电池能量（精度较低，fallback）
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
import srf_client
from srf_client import filter as srf_filter
from srf_client import paging, sort

from jolt_toolkit.vehicle_params_identificator.config import DATA_DIR

logger = logging.getLogger(__name__)


def _make_srf_client(cache_dir: str = "./cache") -> srf_client.SRFData:
    """创建 SRF API 客户端。"""
    api_key = os.environ.get("SRF_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 SRF_API_KEY 环境变量，请在 .env 中配置。")
    srf = srf_client.SRFData(
        api_key=api_key,
        cache_dir=cache_dir,
        root="https://data.csrf.ac.uk/api/",
        verify=True,
    )
    return srf


def haversine_series_m(
    latitude: np.ndarray,
    longitude: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Haversine 逐点距离 (米) 和累积距离。"""
    lat = np.radians(latitude.astype(float))
    lon = np.radians(longitude.astype(float))
    dlat = np.diff(lat)
    dlon = np.diff(lon)
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat[:-1]) * np.cos(lat[1:]) * np.sin(dlon / 2) ** 2
    )
    c = 2 * np.arcsin(np.sqrt(a))
    step = 6371000.0 * c
    step = np.insert(step, 0, 0.0)
    cum = np.cumsum(step)
    return step, cum


def download_logger_data(
    vehicle_reg: str,
    srf_reg: str,
    date_start: str,
    date_end: str,
    *,
    srf: srf_client.SRFData | None = None,
    output_dir: Path | None = None,
    skip_existing: bool = True,
    min_duration_s: float = 300,
) -> Path:
    """
    从 SRF API 下载 Logger leg 数据，合并各通道为统一 CSV。

    每条 leg 输出一个 CSV，列名与原始 CRRCDA 管线兼容：
    UnixTime, Longitude, Latitude, Spd_Kmph_x, BrkPedalPos, EngSpd, EngTrq,
    MassKg, elevation, distance_gps, soc_pct, ...

    Args:
        vehicle_reg: 车牌号
        srf_reg: SRF API 注册名
        date_start/date_end: 日期范围 "YYYY-MM-DD"
        min_duration_s: 最短 leg 时长 (秒)，过滤过短 legs
    """
    if srf is None:
        srf = _make_srf_client()
    if output_dir is None:
        output_dir = DATA_DIR / vehicle_reg
    output_dir.mkdir(parents=True, exist_ok=True)

    ds = dt.datetime.strptime(date_start, "%Y-%m-%d")
    de = dt.datetime.strptime(date_end, "%Y-%m-%d")

    logger.info(
        "下载 Logger 数据: %s (%s) %s ~ %s", vehicle_reg, srf_reg, date_start, date_end
    )

    params = {
        "start_time": srf_filter.between(
            dt.datetime.combine(ds, dt.time.min, dt.timezone.utc),
            dt.datetime.combine(de, dt.time.max, dt.timezone.utc),
        ),
        "sort": sort.asc("startTime"),
    }

    n_saved = 0
    n_skipped = 0
    n_short = 0
    n_failed = 0

    try:
        legs_iter = paging.paged_items(
            srf.legs.find_all(**params, **{"trip.vehicle.registration": srf_reg})
        )
    except Exception as exc:
        logger.error("Legs 拉取失败: %s", exc)
        return output_dir

    for leg in legs_iter:
        try:
            src = leg.trip.source or ""
            if not src.startswith("SRFLOGGER"):
                continue

            dur = (leg.end_time - leg.start_time).total_seconds()
            if dur < min_duration_s:
                n_short += 1
                continue

            # 文件名
            ts_s = leg.start_time.strftime("%Y%m%d%H%M")
            ts_e = leg.end_time.strftime("%Y%m%d%H%M")
            fname = f"{ts_s}_{ts_e}.csv"
            out_path = output_dir / fname

            if skip_existing and out_path.exists():
                n_skipped += 1
                continue

            # 获取可用通道
            avail = set(leg.types)

            # 必须有 GPS (Channel 2) 和 CCVS (速度)
            if "2" not in avail or "CCVS" not in avail:
                n_failed += 1
                continue

            df = _build_leg_dataframe(leg, avail)
            if df is None or len(df) < 60:
                n_failed += 1
                continue

            df.to_csv(out_path, index=False)
            n_saved += 1

        except Exception as exc:
            logger.debug("Leg 处理失败: %s", exc)
            n_failed += 1

    logger.info(
        "下载完成: %s — 保存 %d, 跳过 %d, 过短 %d, 失败 %d",
        vehicle_reg,
        n_saved,
        n_skipped,
        n_short,
        n_failed,
    )
    return output_dir


def _build_leg_dataframe(leg, avail: set[str]) -> pd.DataFrame | None:
    """从 Logger leg 的各通道构建统一 DataFrame。"""
    try:
        # GPS (Channel 2) — 作为时间基准
        gps = leg.get_data_frame("2", resolution="1s")
        if gps is None or gps.empty:
            return None

        out = pd.DataFrame(index=gps.index)

        # UnixTime (ms)
        idx = gps.index
        if idx.tz is not None:
            idx_utc = idx.tz_convert("UTC").tz_localize(None)
        else:
            idx_utc = idx
        out["UnixTime"] = (
            idx_utc.to_numpy(dtype="datetime64[ns]").astype("int64") // 1_000_000
        ).astype("int64")

        out["Longitude"] = pd.to_numeric(gps["2 longitude"], errors="coerce")
        out["Latitude"] = pd.to_numeric(gps["2 latitude"], errors="coerce")
        out["elevation"] = pd.to_numeric(gps["2 altitude"], errors="coerce")
        out["Spd_Kmph_y"] = (
            pd.to_numeric(gps["2 speed"], errors="coerce") * 3.6
        )  # m/s → km/h

        # CCVS (速度 + 制动)
        if "CCVS" in avail:
            ccvs = leg.get_data_frame("CCVS", resolution="1s")
            if ccvs is not None and not ccvs.empty:
                ccvs = ccvs.reindex(gps.index, method="nearest")
                out["Spd_Kmph_x"] = pd.to_numeric(
                    ccvs["CCVS wheel based vehicle speed"], errors="coerce"
                )
                if "CCVS brake switch" in ccvs.columns:
                    out["BrakeSwitch_CCVS"] = pd.to_numeric(
                        ccvs["CCVS brake switch"], errors="coerce"
                    ).fillna(0)

        # 确保 Spd_Kmph_x 存在
        if "Spd_Kmph_x" not in out.columns:
            out["Spd_Kmph_x"] = out.get(
                "Spd_Kmph_y", pd.Series(np.nan, index=out.index)
            )

        # EBC1 (制动踏板)
        if "EBC1" in avail:
            ebc1 = leg.get_data_frame("EBC1", resolution="1s")
            if ebc1 is not None and not ebc1.empty:
                ebc1 = ebc1.reindex(gps.index, method="nearest")
                out["BrkPedalPos"] = pd.to_numeric(
                    ebc1["EBC1 brake pedal position"], errors="coerce"
                ).fillna(0)
        if "BrkPedalPos" not in out.columns:
            out["BrkPedalPos"] = out.get(
                "BrakeSwitch_CCVS", pd.Series(0.0, index=out.index)
            )

        # EEC1 (电机转速 + 扭矩百分比)
        if "EEC1" in avail:
            eec1 = leg.get_data_frame("EEC1", resolution="1s")
            if eec1 is not None and not eec1.empty:
                eec1 = eec1.reindex(gps.index, method="nearest")
                out["EngSpd"] = pd.to_numeric(
                    eec1["EEC1 engine speed"], errors="coerce"
                )
                out["EngTrq"] = pd.to_numeric(
                    eec1["EEC1 actual engine percent torque"], errors="coerce"
                )

        # CVW (质量)
        if "CVW" in avail:
            cvw = leg.get_data_frame("CVW", resolution="1s")
            if cvw is not None and not cvw.empty:
                cvw = cvw.reindex(gps.index, method="nearest")
                out["MassKg"] = pd.to_numeric(
                    cvw["CVW gross combination vehicle weight"], errors="coerce"
                )

        # VW (备选质量 — Mercedes 无 CVW 时使用)
        if "MassKg" not in out.columns and "VW" in avail:
            vw = leg.get_data_frame("VW", resolution="1s")
            if vw is not None and not vw.empty:
                vw = vw.reindex(gps.index, method="nearest")
                # VW 有 cargo_weight, trailer_weight, axle_weight — 取 axle_weight 合计
                for col_candidate in ["VW axle weight", "VW cargo weight"]:
                    if col_candidate in vw.columns:
                        out["MassKg"] = pd.to_numeric(
                            vw[col_candidate], errors="coerce"
                        )
                        break

        # Channel 6 (电池 SOC)
        if "6" in avail:
            ch6 = leg.get_data_frame("6", resolution="1s")
            if ch6 is not None and not ch6.empty:
                ch6 = ch6.reindex(gps.index, method="nearest")
                if "6 charge" in ch6.columns:
                    out["soc_pct"] = pd.to_numeric(ch6["6 charge"], errors="coerce")
                if "6 capacity" in ch6.columns:
                    out["battery_capacity"] = pd.to_numeric(
                        ch6["6 capacity"], errors="coerce"
                    )

        # VDHR (里程表)
        if "VDHR" in avail:
            vdhr = leg.get_data_frame("VDHR", resolution="1s")
            if vdhr is not None and not vdhr.empty:
                vdhr = vdhr.reindex(gps.index, method="nearest")
                out["hr_total_distance"] = pd.to_numeric(
                    vdhr["VDHR hr total vehicle distance"], errors="coerce"
                )

        # Channel 7 (天气)
        if "7" in avail:
            ch7 = leg.get_data_frame("7", resolution="1s")
            if ch7 is not None and not ch7.empty:
                ch7 = ch7.reindex(gps.index, method="nearest")
                if "7 wind speed" in ch7.columns:
                    out["wind_speed_mps"] = pd.to_numeric(
                        ch7["7 wind speed"], errors="coerce"
                    )
                if "7 wind direction" in ch7.columns:
                    out["wind_dir"] = pd.to_numeric(
                        ch7["7 wind direction"], errors="coerce"
                    )

        # 距离 (GPS haversine)
        lat = out["Latitude"].interpolate(limit_direction="both")
        lon = out["Longitude"].interpolate(limit_direction="both")
        if lat.notna().any() and lon.notna().any():
            step, cum = haversine_series_m(
                lat.to_numpy(dtype=float), lon.to_numpy(dtype=float)
            )
            out["distance_gps_per_step"] = step
            out["distance_gps"] = cum
        else:
            return None

        return out

    except Exception as exc:
        logger.debug("构建 leg DataFrame 失败: %s", exc)
        return None


def load_vehicle_csvs(
    vehicle_reg: str, data_dir: Path | None = None
) -> list[pd.DataFrame]:
    """加载已下载的 per-leg CSV 文件。"""
    if data_dir is None:
        data_dir = DATA_DIR / vehicle_reg
    if not data_dir.exists():
        raise FileNotFoundError(f"数据目录不存在: {data_dir}")

    csv_files = sorted(data_dir.glob("*.csv"))
    if not csv_files:
        raise ValueError(f"无 CSV 文件: {data_dir}")

    dfs = []
    for fp in csv_files:
        df = pd.read_csv(fp)
        if not df.empty:
            dfs.append(df)

    logger.info("加载 %d 个 leg CSV — %s", len(dfs), vehicle_reg)
    return dfs


def discover_logger_channels(
    vehicle_reg: str,
    srf_reg: str,
    date_start: str,
    date_end: str,
    *,
    srf: srf_client.SRFData | None = None,
    max_legs: int = 5,
) -> dict:
    """
    探测指定车辆的 Logger 可用通道。

    Returns:
        {"logger_sources": {source: {count, channels}}, "fps_count": int}
    """
    if srf is None:
        srf = _make_srf_client()

    ds = dt.datetime.strptime(date_start, "%Y-%m-%d")
    de = dt.datetime.strptime(date_end, "%Y-%m-%d")

    params = {
        "start_time": srf_filter.between(
            dt.datetime.combine(ds, dt.time.min, dt.timezone.utc),
            dt.datetime.combine(de, dt.time.max, dt.timezone.utc),
        ),
        "sort": sort.asc("startTime"),
    }

    sources: dict[str, dict] = {}
    fps_count = 0

    try:
        for leg in paging.paged_items(
            srf.legs.find_all(**params, **{"trip.vehicle.registration": srf_reg})
        ):
            src = leg.trip.source or ""
            if src.startswith("SRFLOGGER"):
                if src not in sources:
                    sources[src] = {
                        "count": 0,
                        "channels": None,
                        "first": str(leg.start_time)[:10],
                    }
                sources[src]["count"] += 1
                sources[src]["last"] = str(leg.start_time)[:10]
                if sources[src]["channels"] is None:
                    try:
                        sources[src]["channels"] = sorted(leg.types)
                    except Exception:
                        pass
            elif src == "FPS":
                fps_count += 1
    except Exception as exc:
        logger.warning("探测失败: %s", exc)

    return {"logger_sources": sources, "fps_count": fps_count}
