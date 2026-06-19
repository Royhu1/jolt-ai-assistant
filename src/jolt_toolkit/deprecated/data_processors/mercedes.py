"""Mercedes processing pipeline.

This module contains Mercedes-specific telematics processing logic. Unlike Volvo
which uses trigger events (IGNITION_ON/OFF, BATTERY_PACK_CHARGING_*), Mercedes
uses a sequential scan approach based on SOC gain rate and average speed.
"""

from __future__ import annotations

import dataclasses
from typing import Optional
import logging
import geopy
import numpy as np
import pandas as pd
import srf_client
from sklearn.cluster import DBSCAN
import random
from time import perf_counter

from urllib.parse import urlencode, urljoin
from jolt_toolkit.report_generator.data_class import LegRecord, ServerData, Link
from jolt_toolkit.report_generator.weather_fetcher import enrich_weather_data


@dataclasses.dataclass(frozen=True)
class MercedesModelConfig:
    raw_telematics_source: str = "FPS"
    logger_data_types: tuple[str, ...] = (
        "2",
        "7",
        "VDHR",
        "CVW",
        "EBC1",
        "EEC2",
        "CCVS",
    )
    logger_interval: str = "1s"
    # Trip detection parameters
    min_trip_dist_km: float = 2.0
    average_speed_threshold_kmh: float = 2.0
    max_speed_threshold_kmh: float = 120.0
    # Charging detection parameters
    min_charge_gain_pct: float = 3.0
    average_charging_soc_rate_pct_per_h: float = 20.0
    charging_speed_cap_kmh: float = 10.0
    max_flat_minutes_after_charging_start: float = 10.0
    extend_charge_start_back_minutes: float = 30.0
    flat_minutes_mid_soc: float = 30.0
    flat_minutes_high_soc: float = 60.0
    mid_soc_threshold: float = 90.0
    high_soc_threshold: float = 95.0


class MercedesProcessor:
    def __init__(
        self,
        *,
        include_srf_logger_data: bool,
        include_charger_data: bool,
        include_weather_data: bool,
        use_auto_battery_capacity_calibration: bool,
        use_energy_correction_by_elevation: bool,
        srf_data: srf_client.SRFData,
        debug_mode: bool
    ):
        self.include_srf_logger_data = include_srf_logger_data
        self.include_charger_data = include_charger_data
        self.include_weather_data = include_weather_data
        self.use_auto_battery_capacity_calibration = use_auto_battery_capacity_calibration
        self.use_energy_correction_by_elevation = use_energy_correction_by_elevation
        self.srf_data = srf_data

        self.debug_mode = debug_mode

        # Model-specific configuration
        self.config = MercedesModelConfig()

        logging.info("Include SRF logger data: %s", self.include_srf_logger_data)
        logging.info("Include charger data: %s", self.include_charger_data)
        logging.info("Include weather data: %s", self.include_weather_data)
        logging.info("Use auto battery capacity calibration: %s", self.use_auto_battery_capacity_calibration)
        logging.info("Use energy correction by elevation: %s", self.use_energy_correction_by_elevation)

    def __name__(self) -> str:
        return "MercedesProcessor"
    
    def process(self,
                server_data: ServerData,
                battery_capacity_kwh_default: float) -> list[LegRecord]:

        # 获取原始telematics数据
        raw_telematics_df = self._get_raw_telematics_df(legs=server_data.legs)

        # NEED REVIEW: 划分行程和充电记录并将划分后的基本指标写入LegRecord
        leg_record_list = self._extract_leg_record_list(
            raw_telematics_df,
            battery_capacity_kwh_default=battery_capacity_kwh_default,
        )

        if not leg_record_list:
            return []
        
        # 判断是否包含logger数据
        if self.include_srf_logger_data:
            # 获取logger数据
            time_logger_fetch_start = perf_counter()
            logger_df = self._get_logger_df(
                legs=server_data.legs,
                data_types=list(self.config.logger_data_types),
                interval=self.config.logger_interval,
            )
            time_logger_fetch_end = perf_counter()
            print(f"Fetched SRF logger data in {time_logger_fetch_end - time_logger_fetch_start:.2f} seconds.")
            # 融合logger数据
            leg_record_list = self._fuse_logger_data_into_leg_record(
                leg_record_list=leg_record_list,
                logger_df=logger_df,
            )

        # 判断是否包含充电事件数据
        if self.include_charger_data:
            # 获取充电事件数据
            charging_df = self._get_charging_df(charging_events=server_data.charging_events)
            # 融合充电事件数据
            leg_record_list = self._fuse_charger_data_into_leg_record(
                leg_record_list=leg_record_list,
                charging_df=charging_df,
            )
        
        if self.include_weather_data:
            leg_record_list = self._fuse_weather_data_into_leg_record(
                leg_record_list=leg_record_list
            )

        return leg_record_list

    def _get_raw_telematics_df(self, legs: srf_client.paging.Page) -> pd.DataFrame:
        raw_telematics_df = pd.DataFrame()
        for leg in srf_client.paging.paged_items(legs):
            if leg.trip.source == self.config.raw_telematics_source:
                tmp_raw_df = pd.DataFrame()
                for i, chunk in enumerate(leg.get_raw_data()):
                    if i == 0:
                        tmp_raw_df = pd.DataFrame(columns=chunk.split(','))
                    else:
                        try:
                            tmp_raw_df.loc[len(tmp_raw_df)] = chunk.split(',')
                        except Exception as e:
                            logging.warning("Error processing chunk %d for leg %s: %s", i, leg.uri, e)
                            continue

                tmp_raw_df = tmp_raw_df.assign(uri=leg.uri)
                raw_telematics_df = pd.concat([raw_telematics_df, tmp_raw_df], ignore_index=True)
        return raw_telematics_df

    def _get_logger_df(self, legs: srf_client.paging.Page,
                       data_types: list[str],
                       interval: str,
                       ) -> pd.DataFrame:
        logger_df = pd.DataFrame(index=pd.DatetimeIndex([]))
        for leg in srf_client.paging.paged_items(legs):
            if leg.trip.source.startswith('SRFLOGGER'):
                logger_df = pd.concat(
                    [logger_df,
                    (leg.get_data_frame(data_types,
                    interval).assign(uri=leg.uri))], axis=0)
        return logger_df

    def _get_charging_df(self, charging_events: srf_client.model.ChargerTransaction) -> pd.DataFrame:
        charging_df = pd.DataFrame(index=pd.DatetimeIndex([]))
        for charging_event in srf_client.paging.paged_items(charging_events):
            charging_df = pd.concat(
                [charging_df,
                (charging_event.get_data_frame().assign(uri=charging_event.uri))], axis=0)
        return charging_df

    def _extract_leg_record_list(
        self,
        raw_telematics_df: pd.DataFrame,
        *,
        battery_capacity_kwh_default: float
    ) -> list[LegRecord]:
        """
        顺序扫描 Mercedes telematics (eventDatetime, SOC, odometer) 识别 TRIP / CHARGING。

        与 Volvo 不同，Mercedes 不使用 trigger_type 事件，而是基于：
        - SOC 增益率（用于充电检测）
        - 平均速度（用于行程检测）
        """

        # 检查必要列是否存在
        telematics_required_columns = (
            "eventDatetime",
            "latitude",
            "longitude",
            "electricBatteryLevelPercent",
            "odometer",
        )
        if raw_telematics_df.empty:
            logging.warning("Empty telematics DataFrame, returning empty list")
            return []

        if not all(col in raw_telematics_df.columns for col in telematics_required_columns):
            logging.warning(
                "Required columns not found in the telematics DataFrame: %s. Available: %s",
                list(telematics_required_columns),
                list(raw_telematics_df.columns)
            )
            return []

        # 准备数据
        df = raw_telematics_df.copy()
        df["eventDatetime"] = pd.to_datetime(df["eventDatetime"], errors="coerce")
        df = df.sort_values("eventDatetime").reset_index(drop=True)

        # 数值化 + 缺失补全
        df["electricBatteryLevelPercent"] = pd.to_numeric(
            df["electricBatteryLevelPercent"], errors="coerce"
        ).interpolate().bfill().ffill()

        df["odometer"] = pd.to_numeric(df["odometer"], errors="coerce").interpolate().bfill().ffill()
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

        # 可选列数值化
        for col in ["gross_combination_vehicle_weight", "battery_pack_ac_watthours",
                    "battery_pack_dc_watthours", "total_electric_energy_used"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        n = len(df)
        if n < 2:
            logging.warning("Insufficient data points (%d) for trip/charge detection", n)
            return []

        # 计算 forward 差分
        dt_forward = df["eventDatetime"].shift(-1) - df["eventDatetime"]
        dt_forward_sec = dt_forward.dt.total_seconds()

        dist_forward = df["odometer"].shift(-1) - df["odometer"]
        soc_gain_forward = (
            df["electricBatteryLevelPercent"].shift(-1) - df["electricBatteryLevelPercent"]
        )

        df["soc_gain_rate"] = np.where(
            dt_forward_sec > 0, soc_gain_forward / dt_forward_sec * 3600.0, 0.0
        )
        df["avg_speed"] = np.where(dt_forward_sec > 0, dist_forward / dt_forward_sec * 3600.0, 0.0)

        # 初始化
        df["state"] = "resting"
        leg_record_list: list[LegRecord] = []

        # 配置参数
        min_trip_dist_km = self.config.min_trip_dist_km
        min_charge_gain_pct = self.config.min_charge_gain_pct
        average_charging_soc_rate_pct_per_h = self.config.average_charging_soc_rate_pct_per_h
        average_speed_threshold_kmh = self.config.average_speed_threshold_kmh
        max_speed_threshold_kmh = self.config.max_speed_threshold_kmh
        charging_speed_cap_kmh = self.config.charging_speed_cap_kmh
        extend_charge_start_back_minutes = self.config.extend_charge_start_back_minutes
        max_flat_minutes_after_charging_start = self.config.max_flat_minutes_after_charging_start
        flat_minutes_mid_soc = self.config.flat_minutes_mid_soc
        flat_minutes_high_soc = self.config.flat_minutes_high_soc
        mid_soc_threshold = self.config.mid_soc_threshold
        high_soc_threshold = self.config.high_soc_threshold

        # 平台允许时间（充电已确认后）
        def allowed_flat_minutes(current_soc: float) -> float:
            if current_soc < mid_soc_threshold:
                return max_flat_minutes_after_charging_start
            if current_soc < high_soc_threshold:
                return max(max_flat_minutes_after_charging_start, flat_minutes_mid_soc)
            return max(max_flat_minutes_after_charging_start, flat_minutes_high_soc)

        i = 0
        while i < n - 1:
            prev_i = i  # 防止 i 不推进/倒退

            avg_speed_i = float(df.at[i, "avg_speed"])
            avg_soc_rate_i = float(df.at[i, "soc_gain_rate"])

            # ============================================================
            # CHARGING（低速范围内优先）
            # ============================================================
            if (avg_soc_rate_i > average_charging_soc_rate_pct_per_h) and (
                avg_speed_i <= charging_speed_cap_kmh
            ):
                start_idx = i

                # 回溯 start（可选）
                if extend_charge_start_back_minutes and extend_charge_start_back_minutes > 0:
                    back_limit_sec = extend_charge_start_back_minutes * 60.0
                    k = start_idx
                    start_time0 = df.at[start_idx, "eventDatetime"]
                    start_soc0 = float(df.at[start_idx, "electricBatteryLevelPercent"])

                    while k > 0:
                        t_prev = df.at[k - 1, "eventDatetime"]
                        if (start_time0 - t_prev).total_seconds() > back_limit_sec:
                            break
                        if float(df.at[k - 1, "avg_speed"]) > charging_speed_cap_kmh:
                            break
                        # 如果回溯到的 SOC 反而明显更高，停止（避免跨到上一个事件）
                        if float(df.at[k - 1, "electricBatteryLevelPercent"]) > start_soc0 + 0.5:
                            break
                        k -= 1
                    start_idx = k

                df.at[start_idx, "state"] = "charge_start"

                # 向后扩展充电段
                j = start_idx + 1
                flat_minutes = 0.0

                seen_increase = False
                flat_limit_before_first_increase = max(
                    float(extend_charge_start_back_minutes or 0.0),
                    float(max_flat_minutes_after_charging_start),
                )

                while j < n:
                    # 一旦明显移动就结束
                    if float(df.at[j - 1, "avg_speed"]) > charging_speed_cap_kmh:
                        break

                    soc_step = float(
                        df.at[j, "electricBatteryLevelPercent"]
                        - df.at[j - 1, "electricBatteryLevelPercent"]
                    )

                    if soc_step > 0:
                        seen_increase = True
                        flat_minutes = 0.0
                    else:
                        flat_minutes += (
                            df.at[j, "eventDatetime"] - df.at[j - 1, "eventDatetime"]
                        ).total_seconds() / 60.0

                        cur_soc = float(df.at[j - 1, "electricBatteryLevelPercent"])
                        limit = allowed_flat_minutes(cur_soc) if seen_increase else flat_limit_before_first_increase

                        if flat_minutes > limit:
                            break

                    df.at[j, "state"] = "charging"
                    j += 1

                end_idx = j - 1
                if end_idx > start_idx:
                    df.at[end_idx, "state"] = "charge_end"

                # 统计并过滤
                segment_df = df.loc[start_idx:end_idx].copy()
                start_time = df.at[start_idx, "eventDatetime"]
                end_time = df.at[end_idx, "eventDatetime"]
                distance_km = float(df.at[end_idx, "odometer"] - df.at[start_idx, "odometer"])
                start_soc = float(df.at[start_idx, "electricBatteryLevelPercent"])
                end_soc = float(df.at[end_idx, "electricBatteryLevelPercent"])
                soc_gain = end_soc - start_soc

                if soc_gain >= min_charge_gain_pct:
                    # 创建 LegRecord
                    leg_record = LegRecord()
                    leg_record.leg_type = "Charge"
                    leg_record.time_start = start_time
                    leg_record.time_end = end_time
                    leg_record.duration = end_time - start_time
                    leg_record.battery_capacity = battery_capacity_kwh_default
                    leg_record.start_soc = start_soc
                    leg_record.end_soc = end_soc
                    leg_record.soc_change = soc_gain
                    leg_record.distance = distance_km

                    # 位置信息
                    leg_record.origin = self._extract_location(segment_df, "first")
                    leg_record.destination = self._extract_location(segment_df, "last")

                    # 生成 Link
                    uri = segment_df["uri"].iloc[0] if "uri" in segment_df.columns and not segment_df["uri"].empty else ""
                    leg_record.telematics_link = self._create_leg_link(
                        start_time=start_time,
                        end_time=end_time,
                        resource_uri=uri,
                        source="telematics"
                    )

                    # 位置名称
                    if leg_record.origin is not None:
                        leg_record.origin_name, _ = self._get_location_name_postcode(
                            srf_data=self.srf_data,
                            location_point=geopy.Point(leg_record.origin[0], leg_record.origin[1])
                        )
                    if leg_record.destination is not None:
                        leg_record.destination_name, _ = self._get_location_name_postcode(
                            srf_data=self.srf_data,
                            location_point=geopy.Point(leg_record.destination[0], leg_record.destination[1])
                        )

                    # 平均速度
                    duration_seconds = leg_record.duration.total_seconds() if leg_record.duration else 0
                    leg_record.average_speed = (distance_km / (duration_seconds / 3600)) if duration_seconds > 0 else np.nan

                    # 充电能量计算
                    leg_record.energy_change = battery_capacity_kwh_default * (soc_gain / 100) if not pd.isna(soc_gain) else np.nan

                    # AC/DC 充电能量（如果有）
                    if "battery_pack_ac_watthours" in segment_df.columns:
                        ac_start = segment_df["battery_pack_ac_watthours"].dropna().iloc[0] if not segment_df["battery_pack_ac_watthours"].dropna().empty else np.nan
                        ac_end = segment_df["battery_pack_ac_watthours"].dropna().iloc[-1] if not segment_df["battery_pack_ac_watthours"].dropna().empty else np.nan
                        if not np.isnan(ac_start) and not np.isnan(ac_end):
                            leg_record.energy_charged_ac = (ac_end - ac_start) / 1000.0

                    if "battery_pack_dc_watthours" in segment_df.columns:
                        dc_start = segment_df["battery_pack_dc_watthours"].dropna().iloc[0] if not segment_df["battery_pack_dc_watthours"].dropna().empty else np.nan
                        dc_end = segment_df["battery_pack_dc_watthours"].dropna().iloc[-1] if not segment_df["battery_pack_dc_watthours"].dropna().empty else np.nan
                        if not np.isnan(dc_start) and not np.isnan(dc_end):
                            leg_record.energy_charged_dc = (dc_end - dc_start) / 1000.0

                    # 充电率
                    if duration_seconds > 0 and not np.isnan(leg_record.energy_change):
                        leg_record.charging_rate = leg_record.energy_change / (duration_seconds / 3600)

                    leg_record_list.append(leg_record)
                else:
                    # 误检：回滚 state
                    df.loc[start_idx:end_idx, "state"] = "resting"

                # 保证 i 前进
                if end_idx <= prev_i:
                    i = prev_i + 1
                else:
                    i = end_idx
                continue

            # ============================================================
            # TRIP
            # ============================================================
            if avg_speed_i > average_speed_threshold_kmh and avg_speed_i <= max_speed_threshold_kmh:
                start_idx = i
                df.at[start_idx, "state"] = "trip_start"

                j = i + 1
                while j < n and float(df.at[j - 1, "avg_speed"]) > average_speed_threshold_kmh and float(df.at[j - 1, "avg_speed"]) <= max_speed_threshold_kmh:
                    df.at[j, "state"] = "triping"
                    j += 1

                end_idx = j - 1
                if end_idx > start_idx:
                    df.at[end_idx, "state"] = "trip_end"

                segment_df = df.loc[start_idx:end_idx].copy()
                start_time = df.at[start_idx, "eventDatetime"]
                end_time = df.at[end_idx, "eventDatetime"]
                distance_km = float(df.at[end_idx, "odometer"] - df.at[start_idx, "odometer"])
                start_soc = float(df.at[start_idx, "electricBatteryLevelPercent"])
                end_soc = float(df.at[end_idx, "electricBatteryLevelPercent"])
                soc_change = end_soc - start_soc

                if distance_km >= min_trip_dist_km:
                    # 创建 LegRecord
                    leg_record = LegRecord()
                    leg_record.leg_type = "Trip"
                    leg_record.time_start = start_time
                    leg_record.time_end = end_time
                    leg_record.duration = end_time - start_time
                    leg_record.battery_capacity = battery_capacity_kwh_default
                    leg_record.start_soc = start_soc
                    leg_record.end_soc = end_soc
                    leg_record.soc_change = soc_change
                    leg_record.distance = distance_km

                    # 位置信息
                    leg_record.origin = self._extract_location(segment_df, "first")
                    leg_record.destination = self._extract_location(segment_df, "last")

                    # 生成 Link
                    uri = segment_df["uri"].iloc[0] if "uri" in segment_df.columns and not segment_df["uri"].empty else ""
                    leg_record.telematics_link = self._create_leg_link(
                        start_time=start_time,
                        end_time=end_time,
                        resource_uri=uri,
                        source="telematics"
                    )

                    # 位置名称
                    if leg_record.origin is not None:
                        leg_record.origin_name, _ = self._get_location_name_postcode(
                            srf_data=self.srf_data,
                            location_point=geopy.Point(leg_record.origin[0], leg_record.origin[1])
                        )
                    if leg_record.destination is not None:
                        leg_record.destination_name, _ = self._get_location_name_postcode(
                            srf_data=self.srf_data,
                            location_point=geopy.Point(leg_record.destination[0], leg_record.destination[1])
                        )

                    # 平均速度
                    duration_seconds = leg_record.duration.total_seconds() if leg_record.duration else 0
                    leg_record.average_speed = (distance_km / (duration_seconds / 3600)) if duration_seconds > 0 else np.nan

                    # 车辆重量
                    if "gross_combination_vehicle_weight" in segment_df.columns:
                        weight_series = segment_df["gross_combination_vehicle_weight"].dropna()
                        leg_record.vehicle_weight = weight_series.mean() if not weight_series.empty else np.nan

                    # 能量变化计算
                    if "total_electric_energy_used" in segment_df.columns:
                        energy_start = segment_df["total_electric_energy_used"].dropna().iloc[0] if not segment_df["total_electric_energy_used"].dropna().empty else np.nan
                        energy_end = segment_df["total_electric_energy_used"].dropna().iloc[-1] if not segment_df["total_electric_energy_used"].dropna().empty else np.nan
                        if not np.isnan(energy_start) and not np.isnan(energy_end) and (energy_start - energy_end) != 0:
                            leg_record.energy_change = (energy_start - energy_end) / 1000.0  # Wh to kWh
                            # 通过能量变化和SOC变化反推电池容量
                            if soc_change != 0:
                                leg_record.battery_capacity = leg_record.energy_change / (soc_change / 100)
                        else:
                            leg_record.energy_change = battery_capacity_kwh_default * (soc_change / 100) if not pd.isna(soc_change) else np.nan
                    else:
                        leg_record.energy_change = battery_capacity_kwh_default * (soc_change / 100) if not pd.isna(soc_change) else np.nan

                    # 能量性能
                    if not np.isnan(leg_record.energy_change) and distance_km > 0:
                        leg_record.energy_performance = -(leg_record.energy_change / distance_km)

                    leg_record_list.append(leg_record)
                else:
                    df.loc[start_idx:end_idx, "state"] = "resting"

                # 保证 i 前进
                if end_idx <= prev_i:
                    i = prev_i + 1
                else:
                    i = end_idx
                continue

            # REST
            i += 1

        # 按时间排序
        leg_record_list.sort(key=lambda lr: lr.time_start or pd.Timestamp.min)

        # 找到 home_point 位置
        origin_destination_coords = []
        for lr in leg_record_list:
            if lr.origin is not None:
                origin_destination_coords.append((lr.origin[0], lr.origin[1]))
            if lr.destination is not None:
                origin_destination_coords.append((lr.destination[0], lr.destination[1]))

        home_point, home_address, home_postcode = self._find_home_location(
            origin_destination_coords=origin_destination_coords, srf_data=self.srf_data
        )
        logging.info("Find home location: %s, address: %s, postcode: %s", home_point, home_address, home_postcode)

        # 根据 home_point 对 leg_type 进行细分
        for leg_record in leg_record_list:
            leg_record.leg_type = self._classify_charging_trip_type(
                leg_record.leg_type,
                leg_record.origin,
                leg_record.destination,
                home_point
            )
            # 将 AC/DC 充电信息额外写入 leg_record.leg_type
            if not np.isnan(leg_record.energy_charged_ac) and leg_record.energy_charged_ac > 0:
                if np.isnan(leg_record.energy_charged_dc) or leg_record.energy_charged_dc <= 0:
                    leg_record.leg_type += " AC"
                else:
                    leg_record.leg_type += " AC/DC"
            elif not np.isnan(leg_record.energy_charged_dc) and leg_record.energy_charged_dc > 0:
                leg_record.leg_type += " DC"

        # 写入 cumulative_distance
        cumulative_distance_km = 0.0
        for leg_record in leg_record_list:
            leg_record.cumulative_distance = cumulative_distance_km
            cumulative_distance_km += leg_record.distance if not np.isnan(leg_record.distance) else 0.0

        return leg_record_list

    @staticmethod
    def _extract_location(segment_df: pd.DataFrame, position: str) -> Optional[tuple[float, float]]:
        """从 segment_df 提取位置坐标"""
        if segment_df.empty:
            return None
        lat_lon_df = segment_df[["latitude", "longitude"]].dropna()
        if lat_lon_df.empty:
            return None
        if position == "first":
            return (float(lat_lon_df.iloc[0]["latitude"]), float(lat_lon_df.iloc[0]["longitude"]))
        else:  # last
            return (float(lat_lon_df.iloc[-1]["latitude"]), float(lat_lon_df.iloc[-1]["longitude"]))

    def _fuse_logger_data_into_leg_record(self,
                                         leg_record_list: list[LegRecord],
                                         logger_df: pd.DataFrame,
                                         logger_time_difference_tolerance: pd.Timedelta = pd.Timedelta(minutes=5)) -> list[LegRecord]:
        if logger_df.empty:
            return leg_record_list

        for leg_record in leg_record_list:
            logger_df.index = pd.to_datetime(logger_df.index, errors="coerce", utc=True)
            logger_df_slice = logger_df.loc[
                (logger_df.index >= (leg_record.time_start - logger_time_difference_tolerance)) &
                (logger_df.index <= (leg_record.time_end + logger_time_difference_tolerance))
            ]

            if not logger_df_slice.empty:
                logger_link = self._create_leg_link(
                    start_time=logger_df_slice.index[0],
                    end_time=logger_df_slice.index[-1],
                    resource_uri=logger_df_slice.loc[logger_df_slice.index[0], 'uri'],
                    source="logger"
                )
                leg_record.logger_link = logger_link

                logger_vehicle_weight = logger_df_slice["CVW gross combination vehicle weight"].mean(skipna=True)
                print(leg_record.vehicle_weight, not leg_record.vehicle_weight)
                print(f"Logger vehicle weight mean: {logger_vehicle_weight}")
                if np.isnan(leg_record.vehicle_weight) and logger_vehicle_weight: # 如果leg_record.vehicle_weight为空，则用logger_df_slice的平均值填充
                    print("Fusing logger vehicle weight of {} kg into leg record from {} to {}".format(
                        logger_vehicle_weight, leg_record.time_start, leg_record.time_end))
                    leg_record.vehicle_weight = logger_vehicle_weight
        return leg_record_list

    def _fuse_charger_data_into_leg_record(self,
                                           leg_record_list: list[LegRecord],
                                           charging_df: pd.DataFrame,
                                           charger_time_difference_tolerance: pd.Timedelta = pd.Timedelta(minutes=5)) -> list[LegRecord]:
        if charging_df.empty:
            return leg_record_list

        for leg_record in leg_record_list:
            if leg_record.leg_type is not None and "Charge" in leg_record.leg_type:
                charging_df.index = pd.to_datetime(charging_df.index, errors="coerce", utc=True)
                charging_df_slice = charging_df.loc[
                    (charging_df.index >= (leg_record.time_start - charger_time_difference_tolerance)) &
                    (charging_df.index <= (leg_record.time_end + charger_time_difference_tolerance))
                ]

                if not charging_df_slice.empty:
                    charger_link = self._create_leg_link(
                        start_time=charging_df_slice.index[0],
                        end_time=charging_df_slice.index[-1],
                        resource_uri=charging_df_slice.loc[charging_df_slice.index[0], 'uri'],
                        source="charger"
                    )
                    leg_record.charger_link = charger_link
                    logging.debug("Fused charger link into leg record from %s to %s",
                                  leg_record.time_start, leg_record.time_end)

        return leg_record_list

    def _fuse_weather_data_into_leg_record(self,
                                           leg_record_list: list[LegRecord]) -> list[LegRecord]:
        """
        Fuse weather data into leg records using OpenWeather API.

        This method enriches LegRecord objects with weather data (temperature,
        pressure, humidity, wind speed, wind direction) fetched from OpenWeather API.

        Features:
        - Multi-key API management with automatic rotation on quota exceeded
        - Local caching to reduce API calls
        - Concurrent API requests for better performance

        Args:
            leg_record_list: List of LegRecord objects to enrich

        Returns:
            List of LegRecord objects with weather data populated
        """
        if not leg_record_list:
            return leg_record_list

        try:
            leg_record_list = enrich_weather_data(
                leg_record_list=leg_record_list,
                use_cache=True,
                precision=6
            )
            logging.info("Weather data enrichment completed successfully")
        except Exception as e:
            logging.error(f"Failed to enrich weather data: {e}")

        return leg_record_list

    def _find_home_location(self,
                            origin_destination_coords: list[tuple[float, float]],
                            *,
                            ellipsoid: str = "Airy (1830)",
                            srf_data=None,
                            max_location_samples: int = 25000,
                            cluster_radius_km: float = 5.0,
                            min_samples: int = 3,
                            location_search_radius_km: float = 0.5,
                            home_detection_radius_km: float = 5.0,
                            ) -> tuple[geopy.Point | None, str | None, str | None]:

        home_point = None
        home_address = None
        home_postcode = None

        if not origin_destination_coords:
            logging.warning("No records for home location detection.")
            return home_point, home_address, home_postcode

        # 抽样降计算量
        if len(origin_destination_coords) > max_location_samples:
            origin_destination_coords = random.sample(origin_destination_coords, max_location_samples)

        # 转为 numpy 数组（弧度）
        coords_float: list[tuple[float, float]] = []
        for item in origin_destination_coords:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                continue
            lat, lon = item
            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except (TypeError, ValueError):
                continue
            if not (np.isfinite(lat_f) and np.isfinite(lon_f)):
                continue
            coords_float.append((lat_f, lon_f))

        if len(coords_float) < min_samples:
            logging.warning("Not enough valid coordinates for home location detection.")
            return home_point, home_address, home_postcode

        coords_rad = np.radians(np.asarray(coords_float, dtype=float))

        if ellipsoid not in geopy.distance.ELLIPSOIDS:
            ellipsoid = "WGS-84"
        a, b, _ = geopy.distance.ELLIPSOIDS[ellipsoid]
        mean_radius_km = (a + b) / 2.0

        db = DBSCAN(
            eps=cluster_radius_km / mean_radius_km,
            min_samples=min_samples,
            metric="haversine",
            algorithm="ball_tree",
        ).fit(coords_rad)

        labels = db.labels_

        if labels is None or len(labels) == 0:
            logging.warning("DBSCAN produced no labels.")
            return home_point, home_address, home_postcode

        # 找到最大簇的平均点
        best_label = pd.Series(labels).value_counts().idxmax()
        home_cluster = pd.DataFrame(coords_rad[labels == best_label], columns=["lat", "lon"])
        home_point = geopy.Point(
            float(np.degrees(home_cluster["lat"].mean())),
            float(np.degrees(home_cluster["lon"].mean()))
        )

        home_address, home_postcode = self._get_location_name_postcode(
            srf_data,
            home_point,
            location_search_radius_km=location_search_radius_km
        )

        return home_point, home_address, home_postcode

    @staticmethod
    def _get_location_name_postcode(srf_data: srf_client.SRFData,
                           location_point: geopy.Point,
                           location_search_radius_km: float = 0.5
                           ) -> tuple[str | None, str | None]:
        location_name = None
        location_postcode = None
        if location_point is None or srf_data is None:
            return None, None
        try:
            places = srf_data.locations.find_all(
                point=srf_client.filter.near(location_point, geopy.distance.Distance(kilometers=location_search_radius_km))
            )
        except Exception as e:
            logging.warning("Failed to find locations near %s: %s", location_point, e)
            return None, None

        if places.total == 1:
            p = places.items[0]
            location_name = p.name or p.post_code
            location_postcode = p.post_code
        elif places.total > 1:
            dis = [(p, geopy.distance.geodesic(location_point, p.point))
                for p in srf_client.paging.paged_items(places)]
            closest_place, _ = min(dis, key=lambda pair: pair[1])
            location_name = closest_place.name or closest_place.post_code
            location_postcode = closest_place.post_code

        return location_name, location_postcode

    @staticmethod
    def _classify_charging_trip_type(leg_type: str,
                                     origin: tuple[float, float] | None,
                                     destination: tuple[float, float] | None,
                                     home_point: geopy.Point | None,
                                     max_near_home_distance_km: float = 2.0,
                                     ) -> str:

        if home_point is None or origin is None or destination is None:
            logging.warning("Home point or origin/destination is None/NA, cannot classify leg type further.")
            return leg_type

        origin_point = geopy.Point(float(origin[0]), float(origin[1]))
        destination_point = geopy.Point(float(destination[0]), float(destination[1]))
        start_home_distance = geopy.distance.geodesic(origin_point, home_point).km
        end_home_distance = geopy.distance.geodesic(destination_point, home_point).km

        if leg_type == "Charge":
            if start_home_distance < max_near_home_distance_km and end_home_distance < max_near_home_distance_km:
                return "Home Charge"
            if start_home_distance > max_near_home_distance_km and end_home_distance > max_near_home_distance_km:
                return "Away Charge"
            return "Error"

        if leg_type == "Trip":
            if start_home_distance < max_near_home_distance_km and end_home_distance > max_near_home_distance_km:
                return "Outbound"
            if start_home_distance > max_near_home_distance_km and end_home_distance < max_near_home_distance_km:
                return "Return"
            return "In Transition"

        return leg_type

    @staticmethod
    def _create_leg_link(start_time: pd.Timestamp,
                        end_time: pd.Timestamp,
                        resource_uri: str,
                        source: str = "telematics",
                        channels: list[str] = ['2', '96', '95', '7', 'EEC1', 'CVW', 'VDHR']
                        ) -> Link:
        leg_link = Link()

        # 处理时区
        if hasattr(start_time, 'tz') and start_time.tz is not None:
            utc_start_time = start_time.tz_convert('UTC').strftime('%Y-%m-%dT%H:%M:%SZ')
        else:
            utc_start_time = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')

        if hasattr(end_time, 'tz') and end_time.tz is not None:
            utc_end_time = end_time.tz_convert('UTC').strftime('%Y-%m-%dT%H:%M:%SZ')
        else:
            utc_end_time = end_time.strftime('%Y-%m-%dT%H:%M:%SZ')

        query = urlencode({
            'start': utc_start_time,
            'end': utc_end_time,
            'type': channels,
            'resourceUri': resource_uri
        }, doseq=True)

        if source == "telematics":
            leg_link.href = urljoin(resource_uri, '/explore/graphics/plots') + '?' + query
        elif source == "logger":
            leg_link.href = urljoin(resource_uri, '/explore/graphics/plots') + '?' + query
        elif source == "charger":
            leg_link.href = urljoin(resource_uri, '/explore/graphics/usage') + '?' + query
        return leg_link

