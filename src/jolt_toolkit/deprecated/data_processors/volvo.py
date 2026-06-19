"""Volvo processing pipeline.

This module contains Volvo-specific telematics processing logic. It is extracted
from the previous monolithic `scripts/data_processor.py` implementation so
`DataProcessor` can stay as a thin dispatcher.
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

from urllib.parse import urlencode, urljoin
from jolt_toolkit.report_generator.data_class import LegRecord, ServerData, Link


@dataclasses.dataclass(frozen=True)
class VolvoModelConfig:
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
    min_trip_dist_km: float = 2.0
    min_charge_gain_pct: float = 3.0
    soc_drop_tolerance_pct: float = 2.0
    max_start_end_charging_distance_km: float = 0.5
    vehicle_weight_change_threshold: float = 10000.0

class VolvoProcessor:
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
        self.config = VolvoModelConfig()
        # For identification
        self.name = "VolvoProcessor"

        # logging.info("Initialized VolvoProcessor with config: %s", self.config)
        logging.info("Include SRF logger data: %s", self.include_srf_logger_data)
        logging.info("Include charger data: %s", self.include_charger_data)
        logging.info("Include weather data: %s", self.include_weather_data)
        logging.info("Use auto battery capacity calibration: %s", self.use_auto_battery_capacity_calibration)
        logging.info("Use energy correction by elevation: %s", self.use_energy_correction_by_elevation)

    def process(self, 
                server_data: ServerData,
                battery_capacity_kwh_default: float) -> list[LegRecord]:
        # 获取原始telematics数据
        raw_telematics_df = self._get_raw_telematics_df(legs=server_data.legs)

        logger_df = pd.DataFrame()
        charging_df = pd.DataFrame()

        # TODO: 获取srf logger数据
        if self.include_srf_logger_data:
            logger_df = self._get_logger_df(
                legs=server_data.legs,
                data_types=list(self.config.logger_data_types),
                interval=self.config.logger_interval,
            )

        # TODO: 获取充电事件数据
        if self.include_charger_data:
            charging_df = self._get_charging_df(charging_events = server_data.charging_events)

        # NEED REVIEW: 划分行程和充电记录并将划分后的基本指标写入LegRecordDataframe
        leg_record_list = self._extract_leg_record_list(
            raw_telematics_df,
            min_trip_dist_km=self.config.min_trip_dist_km,
            min_charge_gain_pct=self.config.min_charge_gain_pct,
            soc_drop_tolerance_pct=self.config.soc_drop_tolerance_pct,
            max_start_end_charging_distance_km=self.config.max_start_end_charging_distance_km,
            vehicle_weight_change_threshold=self.config.vehicle_weight_change_threshold,
            battery_capacity_kwh_default=battery_capacity_kwh_default,
        )
        if not leg_record_list:
            return []
        
        if self.include_srf_logger_data:
            leg_record_list = self._fuse_logger_data_into_leg_record(
                leg_record_list=leg_record_list,
                logger_df=logger_df,
            )

        if self.include_charger_data:
            leg_record_list = self._fuse_charger_data_into_leg_record(
                leg_record_list=leg_record_list,
                charging_df=charging_df,
            )

        # TODO: 判断是否需要进行自动校准
        # if self.use_auto_battery_capacity_calibration:
        #     base_leg_record_df['battery_capacity_kwh'] = self._auto_calibrate_battery_capacity()


        return leg_record_list

    def _get_raw_telematics_df(self, legs: srf_client.paging.Page) -> pd.DataFrame:
        raw_telematics_df = pd.DataFrame()
        for leg in srf_client.paging.paged_items(legs):
            # doc: https://data.csrf.ac.uk/python/docs/srf_client.model.html#srf_client.model.Leg
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
            # doc: https://data.csrf.ac.uk/python/docs/srf_client.model.html#srf_client.model.Leg
            if leg.trip.source.startswith('SRFLOGGER'):
                logger_df = pd.concat(
                    [logger_df,
                    (leg.get_data_frame(data_types,
                    interval).assign(uri=leg.uri))], axis=0)
        return logger_df

    def _get_charging_df(self, charging_events: srf_client.model.ChargerTransaction) -> pd.DataFrame:
        charging_df = pd.DataFrame(index=pd.DatetimeIndex([]))
        for charging_event in srf_client.paging.paged_items(charging_events):
            # doc: https://data.csrf.ac.uk/python/docs/srf_client.model.html#srf_client.model.ChargerTransaction
            charging_df = pd.concat(
                [charging_df,
                (charging_event.get_data_frame().assign(uri=charging_event.uri))], axis=0)
        return charging_df

    @staticmethod
    def extract_charging_periods_from_telematics(raw_telematics_df: pd.DataFrame,
                                                 soc_drop_tolerance_pct=2.0, 
                                                 min_charge_gain_pct=3.0,
                                                 max_start_end_charging_distance_km=0.5
                                                 ) -> list[tuple[pd.Timestamp, pd.Timestamp, str]]:
        '''
        仅根据telematics数据划分充电记录
        逻辑 1: 充电识别 (筛选相关事件 -> 基于SOC非下降趋势聚类 -> 校验累计增量)
        '''
        charging_periods = []
        CHARGE_TRIGGER_TYPES = [
            "BATTERY_PACK_CHARGING_CONNECTION_STATUS_CHANGE",
            "BATTERY_PACK_CHARGING_STATUS_CHANGE",
        ]
        charging_events_df = raw_telematics_df.loc[
            raw_telematics_df["trigger_type"].isin(CHARGE_TRIGGER_TYPES)
        ].copy()
        if charging_events_df.empty:
            return []
        # 计算相邻事件SOC差分，当差分小于-soc_drop_tolerance_pct时，视为新充电段的开始
        soc_diff = charging_events_df["electricBatteryLevelPercent"].diff()
        charging_events_df["charging_event_id"] = soc_diff.lt(-soc_drop_tolerance_pct).cumsum() # `lt` means less than
        # print(soc_diff.lt(-soc_drop_tolerance_pct))
        # print('charging_events_df: ', charging_events_df)

        for _, segment_df in charging_events_df.groupby("charging_event_id"):
            # print('segment_df: ', segment_df)
            start_time = pd.to_datetime(segment_df.iloc[0].get("eventDatetime"), errors="coerce")
            end_time = pd.to_datetime(segment_df.iloc[-1].get("eventDatetime"), errors="coerce")
            charging_periods.append((start_time, end_time, "Charge"))
        return charging_periods
  
    @staticmethod
    def extract_trip_periods_from_telematics(
        raw_telematics_df: pd.DataFrame,
        *,
        min_trip_dist_km: float = 2.0,
        vehicle_weight_change_threshold: float = 10000.0,
    ) -> list[tuple[pd.Timestamp, pd.Timestamp, str]]:
        '''
        仅根据telematics数据划分行程
        逻辑 2: 行程识别 (提取点火信号 -> 匹配ON/OFF事件对 -> 校验里程增量)
        '''
        trip_periods = []
        IGNITION_TRIGGER_TYPES = ["IGNITION_ON", "IGNITION_OFF"]
        ignition_events_df = raw_telematics_df.loc[
            raw_telematics_df["trigger_type"].isin(IGNITION_TRIGGER_TYPES)
        ].copy()
        if ignition_events_df.empty:
            return []

        # 用 ON 的累计次数作为“原始组号”
        is_on_df = ignition_events_df["trigger_type"].eq("IGNITION_ON")
        on_id = is_on_df.cumsum()
        ignition_events_df = ignition_events_df[on_id > 0].copy()
        ignition_events_df["trip_id"] = on_id.loc[ignition_events_df.index].astype(int)

        for _, trip_df in ignition_events_df.groupby("trip_id"):
            start_time = pd.to_datetime(trip_df.iloc[0].get("eventDatetime"), errors="coerce")
            end_time = pd.to_datetime(trip_df.iloc[-1].get("eventDatetime"), errors="coerce") 

            # 提取这个时间区间内的raw_telematics_df数据
            trip_telematics_df = raw_telematics_df.loc[
                (pd.to_datetime(raw_telematics_df["eventDatetime"], errors="coerce") >= start_time) &
                (pd.to_datetime(raw_telematics_df["eventDatetime"], errors="coerce") <= end_time)
            ].copy()

            # 检查区间内质量是否有突变, 若有突变将行程划分为多段
            # TODO: 这里的逻辑未规避质量测量误差导致的跳变，当质量发生变化时，应该呈现区间变化，比如在0-30分钟内质量稳定在8000kg，然后在30-60分钟内稳定在12000kg，应采取区间均值而不是单点跳变
            weight_series = trip_telematics_df["gross_combination_vehicle_weight"].dropna()
            trip_telematics_df["subtrip_id"] = 0
            if not weight_series.empty:
                weight_diff = weight_series.diff().abs()
                if (weight_diff > vehicle_weight_change_threshold).any():
                    jump_mask = weight_diff > vehicle_weight_change_threshold
                    trip_telematics_df["subtrip_id"] = jump_mask.fillna(False).cumsum()
                else:
                    trip_telematics_df["subtrip_id"] = 0
            
            for _, subtrip_df in trip_telematics_df.groupby("subtrip_id"):
                start_time = pd.to_datetime(subtrip_df.iloc[0].get("eventDatetime"), errors="coerce")
                end_time = pd.to_datetime(subtrip_df.iloc[-1].get("eventDatetime"), errors="coerce")
                start_odometer, end_odometer = subtrip_df["odometer"].iloc[[0, -1]] # 获取起止里程,odometer这个通道一直有数据所以不需要dropna检查
                # 计算里程增量,并应用过滤条件
                distance_km = end_odometer - start_odometer
                if pd.isna(distance_km) or distance_km < min_trip_dist_km:
                    continue

                trip_periods.append((start_time, end_time, "Trip"))
        return trip_periods
    
    # TODO: 人工验证划分的结果是否正确
    # 返回含基础指标的LegRecordDataframe

    def _extract_leg_record_list(
        self,
        raw_telematics_df: pd.DataFrame,
        *,
        min_trip_dist_km: float = 2.0, # Minimum distance (km) to consider a trip valid
        min_charge_gain_pct: float = 3.0, # Minimum SOC gain (%) to consider a charging session valid
        soc_drop_tolerance_pct: float = 2.0, # Tolerance for SOC drop (%) within a charging session
        max_start_end_charging_distance_km: float = 0.5, # Maximum distance (km) between start and end of a charging session
        vehicle_weight_change_threshold: float = 10000.0, # Threshold for vehicle weight change (kg) to be considered as a loading/unloading event
        battery_capacity_kwh_default: float
    ) -> list[LegRecord]:
        
        # 检查必要列是否存在,否则报错
        telematics_required_columns = (
            "eventDatetime",
            "trigger_type",
            "latitude",
            "longitude",
            "electricBatteryLevelPercent",
            "odometer",
            "gross_combination_vehicle_weight",
        )
        if not all(col in raw_telematics_df.columns for col in telematics_required_columns):
            raise ValueError(
                "Required columns not found in the telematics DataFrame: "
                f"{list(telematics_required_columns)}"
            )
        
        # 确保raw_telematics_df按时间排序, 并将electricBatteryLevelPercent, odometer, gross_combination_vehicle_weight转换为numeric类型
        raw_telematics_df = raw_telematics_df.sort_values("eventDatetime", kind="mergesort")
        raw_telematics_df = raw_telematics_df.assign(**{
            c: pd.to_numeric(raw_telematics_df[c], errors="coerce")
            for c in [
                "electricBatteryLevelPercent",
                "odometer",
                "gross_combination_vehicle_weight",
                "latitude",
                "longitude",
                "battery_pack_ac_watthours",
                "battery_pack_dc_watthours",
                "total_electric_energy_used",
            ]
        })
        # 将eventDatetime转换为pd.Timestamp类型
        raw_telematics_df["eventDatetime"] = pd.to_datetime(raw_telematics_df["eventDatetime"], errors="coerce")

        # 初始化LegRecord的list
        leg_record_list: list[LegRecord] = []

        # 
        charging_periods = self.extract_charging_periods_from_telematics(
            raw_telematics_df, soc_drop_tolerance_pct=soc_drop_tolerance_pct, 
            min_charge_gain_pct=min_charge_gain_pct, max_start_end_charging_distance_km=max_start_end_charging_distance_km # TODO: 未使用max_start_end_charging_distance_km参数
        )

        trip_periods = self.extract_trip_periods_from_telematics(
            raw_telematics_df,
            min_trip_dist_km=min_trip_dist_km,
            vehicle_weight_change_threshold=vehicle_weight_change_threshold,
        )
        
        leg_periods = charging_periods + trip_periods

        # 通过leg_periods和trip_periods填充leg_record_list, 每一个LegRecord代表一个行程或充电记录
        for start_time, end_time, leg_type in leg_periods:
            # 初始化LegRecord对象
            leg_record = LegRecord()
            leg_record.leg_type = leg_type
            leg_record.time_start = start_time
            leg_record.time_end = end_time
            leg_record.duration = end_time - start_time
            leg_record.battery_capacity = battery_capacity_kwh_default
            # 根据时间区间提取telematics数据段segment_df
            segment_df = raw_telematics_df.loc[
                (raw_telematics_df["eventDatetime"] >= start_time) & (raw_telematics_df["eventDatetime"] <= end_time)
            ].copy()
            # 生成Link
            leg_record.telematics_link = self._create_leg_link(start_time=start_time, 
                                            end_time=end_time, 
                                            resource_uri= segment_df.loc[segment_df.index[0], 'uri'],
                                            source="telematics")
            
            leg_record.start_soc, leg_record.end_soc = segment_df["electricBatteryLevelPercent"].dropna().iloc[[0, -1]] if not segment_df["electricBatteryLevelPercent"].dropna().empty else (np.nan, np.nan)
            leg_record.soc_change = leg_record.end_soc - leg_record.start_soc
            leg_record.distance = segment_df["odometer"].iloc[-1] - segment_df["odometer"].iloc[0]
            leg_record.origin = tuple(segment_df[["latitude", "longitude"]].dropna().iloc[0]) if not segment_df[["latitude", "longitude"]].dropna().empty else None
            leg_record.destination = tuple(segment_df[["latitude", "longitude"]].dropna().iloc[-1]) if not segment_df[["latitude", "longitude"]].dropna().empty else None
            leg_record.vehicle_weight = segment_df["gross_combination_vehicle_weight"].dropna().mean() if not segment_df["gross_combination_vehicle_weight"].dropna().empty else np.nan
            # 计算衍生指标：origin_name, destination_name, avg_speed_kmh, cumulative_distance_km
            leg_record.origin_name, _ = self._get_location_name_postcode(
                srf_data=self.srf_data,
                location_point=geopy.Point(leg_record.origin[0], leg_record.origin[1])
            )
            leg_record.destination_name, _ = self._get_location_name_postcode(
                srf_data=self.srf_data,
                location_point=geopy.Point(leg_record.destination[0], leg_record.destination[1])
            )
            leg_record.average_speed = (leg_record.distance / (leg_record.duration.total_seconds() / 3600)) if leg_record.duration.total_seconds() > 0 else np.nan

            if leg_type == "Trip":
                # 计算energy_change, battery capacity, energy_performance
                segment_df_with_valid_soc = segment_df.dropna(subset=["electricBatteryLevelPercent"]).copy()
                total_electric_energy_used_start = segment_df_with_valid_soc["total_electric_energy_used"].iloc[0] if not segment_df_with_valid_soc["total_electric_energy_used"].empty else np.nan
                total_electric_energy_used_end = segment_df_with_valid_soc["total_electric_energy_used"].iloc[-1] if not segment_df_with_valid_soc["total_electric_energy_used"].empty else np.nan
                if (total_electric_energy_used_start-total_electric_energy_used_end):
                    # print("Debug: total_electric_energy_used_start:", total_electric_energy_used_start, "total_electric_energy_used_end:", total_electric_energy_used_end)
                    leg_record.energy_change = (total_electric_energy_used_start - total_electric_energy_used_end)/1000.0  # from Wh convert to kWh
                    leg_record.battery_capacity = leg_record.energy_change / (leg_record.soc_change / 100) if leg_record.soc_change != 0 else battery_capacity_kwh_default # 通过能量变化和SOC变化反推电池容量
                else:
                    # print("Warning: total_electric_energy_used data missing for Trip leg from {} to {}".format(start_time, end_time))
                    leg_record.energy_change = leg_record.battery_capacity * (leg_record.soc_change / 100) if not pd.isna(leg_record.soc_change) and not pd.isna(leg_record.battery_capacity) else np.nan
                leg_record.energy_performance = -(leg_record.energy_change / leg_record.distance)

            elif leg_type == "Charge":
                # 计算energy_change, energy_charged_ac, energy_charged_dc, battery_capacity
                energy_charged_ac_start = segment_df['battery_pack_ac_watthours'].dropna().iloc[0] if not segment_df['battery_pack_ac_watthours'].dropna().empty else np.nan
                energy_charged_ac_end = segment_df['battery_pack_ac_watthours'].dropna().iloc[-1] if not segment_df['battery_pack_ac_watthours'].dropna().empty else np.nan
                energy_charged_dc_start = segment_df['battery_pack_dc_watthours'].dropna().iloc[0] if not segment_df['battery_pack_dc_watthours'].dropna().empty else np.nan
                energy_charged_dc_end = segment_df['battery_pack_dc_watthours'].dropna().iloc[-1] if not segment_df['battery_pack_dc_watthours'].dropna().empty else np.nan
                if not np.isnan(energy_charged_ac_start) and not np.isnan(energy_charged_ac_end):
                    leg_record.energy_charged_ac = (energy_charged_ac_end - energy_charged_ac_start)/1000.0  # from Wh convert to kWh
                if not np.isnan(energy_charged_dc_start) and not np.isnan(energy_charged_dc_end):
                    leg_record.energy_charged_dc = (energy_charged_dc_end - energy_charged_dc_start)/1000.0  # from Wh convert to kWh
                if not np.isnan(leg_record.energy_charged_ac) and not np.isnan(leg_record.energy_charged_dc):
                    leg_record.energy_change = leg_record.energy_charged_ac + leg_record.energy_charged_dc
                    leg_record.battery_capacity = leg_record.energy_change / (leg_record.soc_change / 100) if leg_record.soc_change != 0 else battery_capacity_kwh_default
                else:
                    leg_record.energy_change = battery_capacity_kwh_default * (leg_record.soc_change / 100) if not pd.isna(leg_record.soc_change) and not pd.isna(battery_capacity_kwh_default) else np.nan
                
            # 写入leg_record_list
            leg_record_list.append(leg_record)
        
        # 将leg_record_list中的leg_record按照时间顺序排序
        leg_record_list.sort(key=lambda leg_record: leg_record.time_start or pd.Timestamp.min)

        # 找到home_point位置
        origin_destination_coords = [(leg_record_list[i].origin[0], leg_record_list[i].origin[1]) for i in range(len(leg_record_list))] + \
                                    [(leg_record_list[i].destination[0], leg_record_list[i].destination[1]) for i in range(len(leg_record_list))]
        home_point, home_address, home_postcode = self._find_home_location(
            origin_destination_coords=origin_destination_coords, srf_data=self.srf_data
        )
        logging.info("Find home location: %s, address: %s, postcode: %s", home_point, home_address, home_postcode)

        # 根据home_point对leg_type进行细分
        for leg_record in leg_record_list:
            leg_record.leg_type = self._classify_charging_trip_type(leg_record.leg_type,
                                                                    leg_record.origin,
                                                                    leg_record.destination,
                                                                    home_point)
            # 将AC/DC充电信息额外写入leg_record.leg_type
            if leg_record.energy_charged_ac > 0 and leg_record.energy_charged_dc <= 0:
                leg_record.leg_type += " AC"
            elif leg_record.energy_charged_dc > 0 and leg_record.energy_charged_ac <= 0:
                leg_record.leg_type += " DC"
            elif leg_record.energy_charged_ac > 0 and leg_record.energy_charged_dc > 0:
                leg_record.leg_type += " AC/DC"

        # 写入cummulative_distance_km
        cumulative_distance_km = 0.0
        for leg_record in leg_record_list:
            leg_record.cumulative_distance = cumulative_distance_km
            cumulative_distance_km += leg_record.distance

        return leg_record_list
    
    def _fuse_logger_data_into_leg_record(self,
                                         leg_record_list: list[LegRecord],
                                         logger_df: pd.DataFrame,
                                         logger_time_difference_tolerance: pd.Timedelta = pd.Timedelta(minutes=5)) -> list[LegRecord]:
        for leg_record in leg_record_list:
            if logger_df is not None:
                logger_df.index = pd.to_datetime(logger_df.index, errors="coerce", utc=True)
                logger_df_slice = logger_df.loc[
                    (logger_df.index >= (leg_record.time_start - logger_time_difference_tolerance)) &
                    (logger_df.index <= (leg_record.time_end + logger_time_difference_tolerance))
                ]

                logger_link = self._create_leg_link(
                    start_time=logger_df_slice.index[0],
                    end_time=logger_df_slice.index[-1],
                    resource_uri= logger_df_slice.loc[logger_df_slice.index[0], 'uri'],
                    source="logger"
                )
                leg_record.logger_link = logger_link
        return leg_record_list

    def _fuse_charger_data_into_leg_record(self,
                                           leg_record_list: list[LegRecord],
                                           charging_df: pd.DataFrame, 
                                           charger_time_difference_tolerance: pd.Timedelta = pd.Timedelta(minutes=5)) -> list[LegRecord]:

        for leg_record in leg_record_list:
            if charging_df is not None and leg_record.leg_type.startswith("charge"):
                charging_df.index = pd.to_datetime(charging_df.index, errors="coerce", utc=True)
                charging_df_slice = charging_df.loc[
                    (charging_df.index >= (leg_record.time_start - charger_time_difference_tolerance)) &
                    (charging_df.index <= (leg_record.time_end + charger_time_difference_tolerance))
                ]
                # 过滤charging_df，获取时间在leg_start和leg_end之间的记录
                charger_link = self._create_leg_link(start_time=charging_df_slice.index[0],
                                                    end_time=charging_df_slice.index[-1],
                                                    resource_uri= charging_df_slice.loc[charging_df_slice.index[0], 'uri'],
                                                    source="charger")   
                leg_record.charger_link = charger_link
                if charger_link is not None:
                    print("Fused charger link %s into leg record from %s to %s",
                                  charger_link.uri,
                                    leg_record.time_start,
                                    leg_record.time_end)

        return leg_record_list


    def _find_home_location(self, 
                            origin_destination_coords: list[tuple[float, float]],
                            *,
                            ellipsoid: str = "Airy (1830)",
                            srf_data=None,                         # srf_client.SRFData
                            max_location_samples: int = 25000,
                            cluster_radius_km: float = 5.0,        # DBSCAN 半径（km）
                            min_samples: int = 3,                  # DBSCAN 最小点数（可按需改 1/3/5）
                            location_search_radius_km: float = 0.5,   # 反查地址的 near 半径（km）
                            home_detection_radius_km: float = 5.0, # 多地点时取最近点的阈值（km）
                            ) -> tuple[geopy.Point | None, str | None, str | None]:
        
        home_point = None
        home_address = None
        home_postcode = None

        # ---------- 1) 收集 start/end 坐标，并扁平化 ----------
        if not origin_destination_coords:
            print("No records for home location detection.")
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
            print("No valid coordinates for home location detection.")
            return home_point, home_address, home_postcode

        coords_rad = np.radians(np.asarray(coords_float, dtype=float))

        # geopy.distance.ELLIPSOIDS 的 a,b 通常是 km
        if ellipsoid not in geopy.distance.ELLIPSOIDS:
            ellipsoid = "WGS-84"
        a, b, _ = geopy.distance.ELLIPSOIDS[ellipsoid]
        mean_radius_km = (a + b) / 2.0

        db = DBSCAN(
            eps=cluster_radius_km / mean_radius_km,  # km -> radians
            min_samples=min_samples,
            metric="haversine",
            algorithm="ball_tree",
        ).fit(coords_rad)

        labels = db.labels_

        if labels is None or len(labels) == 0:
            print("DBSCAN produced no labels.")
            return home_point, home_address, home_postcode

        # 找到最大簇的平均点
        best_label = pd.Series(labels).value_counts().idxmax()
        home_cluster = pd.DataFrame(coords_rad[labels == best_label], columns=["lat", "lon"])
        home_point = geopy.Point(
            float(np.degrees(home_cluster["lat"].mean())),
            float(np.degrees(home_cluster["lon"].mean()))
        )
        
        # TODO: 测试home_address和home_postcode的反查效果
        home_address, home_postcode = self._get_location_name_postcode(
            srf_data,
            home_point,
            location_search_radius_km=location_search_radius_km
        )

        # print("--------------------------------")
        # print("home_point:", home_point, "home_address:", home_address, "home_postcode:", home_postcode)
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
            print(f"Failed to find locations near {location_point}: {e}")
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
        utc_start_time = start_time.tz_convert('UTC').strftime('%Y-%m-%dT%H:%M:%SZ')
        utc_end_time = end_time.tz_convert('UTC').strftime('%Y-%m-%dT%H:%M:%SZ')
        query = urlencode({
            # All times in index are in UTC and localized straight from first dfs
            'start': utc_start_time,
            'end': utc_end_time,
            'type': channels,
            'resourceUri': resource_uri
        }, doseq=True)
        
        # TODO: 区分telematics, logger, charger不同情况的链接
        if source == "telematics":
            leg_link.href = urljoin(resource_uri, '/explore/graphics/plots') + '?' + query
        elif source == "logger":
            leg_link.href = urljoin(resource_uri, '/explore/graphics/plots') + '?' + query
        elif source == "charger":
            leg_link.href = urljoin(resource_uri, '/explore/graphics/usage') + '?' + query
        return leg_link 
    
    def _auto_calibrate_battery_capacity(self) -> float:
        pass
    
    @staticmethod
    def _format_latlon(value: object) -> object:
        if isinstance(value, (tuple, list)) and len(value) == 2:
            lat, lon = value
            if pd.isna(lat) or pd.isna(lon):
                return pd.NA
            return f"{lat}, {lon}"
        return pd.NA
    
