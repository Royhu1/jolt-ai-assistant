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
class RenaultModelConfig:
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

class RenaultProcessor:
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
        self.config = RenaultModelConfig()
        # For identification
        self.name = "RenaultProcessor"

        # logging.info("Initialized RenaultProcessor with config: %s", self.config)
        logging.info("Include SRF logger data: %s", self.include_srf_logger_data)
        logging.info("Include charger data: %s", self.include_charger_data)
        logging.info("Include weather data: %s", self.include_weather_data)
        logging.info("Use auto battery capacity calibration: %s", self.use_auto_battery_capacity_calibration)
        logging.info("Use energy correction by elevation: %s", self.use_energy_correction_by_elevation)

 
    
