# import necessary libraries
import dataclasses
from typing import ClassVar, Optional
import pandas as pd
import srf_client
import numpy as np
import datetime


# define the ServerData class
@dataclasses.dataclass
class ServerData:
    """Container for data retrieved from SRF API."""
    vehicle: srf_client.model.Vehicle
    legs: srf_client.model.Leg
    charging_events: srf_client.model.ChargerTransaction

# define the Link class
@dataclasses.dataclass
class Link:
    """Hyperlink for Excel reports."""
    href: Optional[str] = None
    text: str = "Link"

# define the LegRecordDataframe class

@dataclasses.dataclass(slots=True)
class LegRecord:
    """
    Comprehensive record for a single trip or charging event.
    Note: This class uses __slots__ to prevent dynamic attribute addition.
    Only attributes defined in the class can be set.
    """
    leg_type: Optional[str] = dataclasses.field(default=None, metadata={"Excel Header": "Leg Type", "dtype": str, "decimal_places": None})
    telematics_link: Optional[Link] = dataclasses.field(default=None, metadata={"Excel Header": "Telematics Link", "dtype": Link, "decimal_places": None})
    charger_link: Optional[Link] = dataclasses.field(default=None, metadata={"Excel Header": "Charger Link", "dtype": Link, "decimal_places": None})
    logger_link: Optional[Link] = dataclasses.field(default=None, metadata={"Excel Header": "Logger Link", "dtype": Link, "decimal_places": None})
    time_start: Optional[datetime.datetime] = dataclasses.field(default=None, metadata={"Excel Header": "Start Time (UTC)", "dtype": datetime.datetime, "decimal_places": None})
    origin: Optional[tuple[float, float]] = dataclasses.field(default=None, metadata={"Excel Header": "Origin (Lat, Lon)", "dtype": str, "decimal_places": None})
    origin_name: Optional[str] = dataclasses.field(default=None, metadata={"Excel Header": "Origin Place", "dtype": str, "decimal_places": None})
    time_end: Optional[datetime.datetime] = dataclasses.field(default=None, metadata={"Excel Header": "End Time (UTC)", "dtype": datetime.datetime, "decimal_places": None})
    destination: Optional[tuple[float, float]] = dataclasses.field(default=None, metadata={"Excel Header": "Destination (Lat, Lon)", "dtype": str, "decimal_places": None})
    destination_name: Optional[str] = dataclasses.field(default=None, metadata={"Excel Header": "Destination Place", "dtype": str, "decimal_places": None})
    duration: Optional[datetime.timedelta] = dataclasses.field(default=None, metadata={"Excel Header": "Duration", "dtype": datetime.timedelta, "decimal_places": None})
    distance: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Distance (km)", "dtype": float, "decimal_places": 2})
    average_speed: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Average Speed (km/h)", "dtype": float, "decimal_places": 2})
    elevation_difference: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Elevation Difference (m)", "dtype": float, "decimal_places": 0})
    vehicle_weight: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Vehicle Weight (kg)", "dtype": float, "decimal_places": 0})
    # vehicle_weight_cv: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Vehicle Weight CV", "dtype": float, "decimal_places": 2})
    recuperation: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Recuperation Energy (kWh)", "dtype": float, "decimal_places": 2})
    start_soc: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Start SOC (%)", "dtype": float, "decimal_places": 1})
    end_soc: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "End SOC (%)", "dtype": float, "decimal_places": 1})
    soc_change: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "SOC Change (%)", "dtype": float, "decimal_places": 1})
    energy_change: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Energy Change (kWh)", "dtype": float, "decimal_places": 2})
    energy_charged_ac: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Energy Charged AC (kWh)", "dtype": float, "decimal_places": 2})
    energy_charged_dc: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Energy Charged DC (kWh)", "dtype": float, "decimal_places": 2})
    co2_per_kwh: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "CO2 (g/kWh)", "dtype": float, "decimal_places": 2})
    cumulative_distance: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Cumulative Distance (km)", "dtype": float, "decimal_places": 2})
    total_co2: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Total CO2 (g)", "dtype": float, "decimal_places": 2})
    cumulative_co2: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Cumulative CO2 (g)", "dtype": float, "decimal_places": 2})
    charging_rate: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Charging Rate (kW)", "dtype": float, "decimal_places": 2})
    energy_performance: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Energy Performance (kWh/km)", "dtype": float, "decimal_places": 2})
    energy_performance_corrected: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Corrected Energy Performance (kWh/km)", "dtype": float, "decimal_places": 2})
    battery_capacity: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Battery Capacity (kWh)", "dtype": float, "decimal_places": 2})
    energy_output_from_charger: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Energy Output from Charger (kWh)", "dtype": float, "decimal_places": 2})
    energy_efficiency: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Energy Efficiency", "dtype": float, "decimal_places": 2})
    peak_charging: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Peak Charging (kW)", "dtype": float, "decimal_places": 2})
    average_charging: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Average Charging (kW)", "dtype": float, "decimal_places": 2})
    energy_change_motor: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Energy Change Motor (kWh)", "dtype": float, "decimal_places": 2})
    avg_temp: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Average Temperature (°C)", "dtype": float, "decimal_places": 2})
    avg_pressure: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Average Pressure (hPa)", "dtype": float, "decimal_places": 2})
    avg_humidity: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Average Humidity (%)", "dtype": float, "decimal_places": 2})
    avg_wind_speed: Optional[float] = dataclasses.field(default=np.nan, metadata={"Excel Header": "Average Wind Speed (m/s)", "dtype": float, "decimal_places": 2})
    cardinal_wind_direction: Optional[str] = dataclasses.field(default=None, metadata={"Excel Header": "Cardinal Wind Direction", "dtype": str, "decimal_places": None})
    weather_type: Optional[str] = dataclasses.field(default=None, metadata={"Excel Header": "Weather Type", "dtype": str, "decimal_places": None})
    acc_pedal_position_hist_string: Optional[str] = dataclasses.field(default=None, metadata={"Excel Header": "Acceleration Pedal Position Histogram", "dtype": str, "decimal_places": None})  # 为了excel存储方便，改成string
    dec_pedal_position_hist_string: Optional[str] = dataclasses.field(default=None, metadata={"Excel Header": "Deceleration Pedal Position Histogram", "dtype": str, "decimal_places": None})  # 为了excel存储方便，改成string

class LegRecordDataframe(pd.DataFrame):
    """A pandas DataFrame with the standardized `LegRecord` column schema."""
    # 定义列名，写入Excel时的表头名称，以及列的数据类型
    COLUMNS_HEADERS_TYPES: ClassVar[dict[str, tuple[str, type]]] = {
        "leg_type": ("Leg Type", str),
        "telematics_link": ("Telematics Link", Link),
        "charger_link": ("Charger Link", Link),
        "logger_link": ("Logger Link", Link),
        "start": ("Start Time (UTC)", pd.Timestamp),
        "origin": ("Origin (Lat, Lon)", str),
        "origin_name": ("Origin Place", str),
        "end": ("End Time (UTC)", pd.Timestamp),
        "destination": ("Destination (Lat, Lon)", str),
        "destination_name": ("Destination Place", str),
        "duration": ("Duration (HH:MM:SS)", pd.Timedelta),
        "distance": ("Distance (km)", float),
        "average_speed": ("Average Speed (km/h)", float),
        "elevation_difference": ("Elevation Difference (m)", float),
        "vehicle_weight": ("Vehicle Weight (kg)", float),
        # "vehicle_weight_cv": ("Vehicle Weight CV", float),
        "recuperation": ("Recuperation Energy(kWh)", float),
        "start_soc": ("Start SOC (%)", float),
        "end_soc": ("End SOC (%)", float),
        "soc_change": ("SOC Change (%)", float),
        "energy_change": ("Energy Change (kWh)", float),
        "energy_charged_ac": ("Energy Charged AC (kWh)", float),
        "energy_charged_dc": ("Energy Charged DC (kWh)", float),
        "energy_performance": ("Energy Performance (kWh/100km)", float),
        "energy_performance_corrected": ("Corrected Energy Performance (kWh/100km)", float),
        "co2_per_kwh": ("CO2 (g/kWh)", float),
        "cumulative_distance": ("Cumulative Distance (km)", float),
        "total_co2": ("Total CO2 (g)", float),
        "cumulative_co2": ("Cumulative CO2 (g)", float),
        "charging_rate": ("Charging Rate (kW)", float),
        "battery_capacity": ("Battery Capacity (kWh)", float),
        "energy_output_from_charger": ("Energy Output from Charger (kWh)", float),
        "energy_efficiency": ("Energy Efficiency", float),
        "peak_charging": ("Peak Charging (kW)", float),
        "average_charging": ("Average Charging (kW)", float),
        "energy_change_motor": ("Energy Change Motor (kWh)", float),
        "avg_temp": ("Average Temperature (°C)", float),
        "avg_pressure": ("Average Pressure (hPa)", float),
        "avg_humidity": ("Average Humidity (%)", float),
        "avg_wind_speed": ("Average Wind Speed (m/s)", float),
        "cardinal_wind_direction": ("Cardinal Wind Direction", str),
        "weather_type": ("Weather Type", str),
        "acc_pedal_position_hist_string": ("Acceleration Pedal Position Histogram", str),
        "dec_pedal_position_hist_string": ("Deceleration Pedal Position Histogram", str),
    }

    # Number of decimal places to display in Excel for each numeric column.
    # If a column is not listed here, the default Excel formatting is used.
    COLUMN_DECIMAL_PLACES: ClassVar[dict[str, int]] = {
        "vehicle_weight": 0,
        "vehicle_weight_cv": 2,
        "distance": 2,
        "average_speed": 2,
        "elevation_difference": 0,
        "recuperation": 2,
        "start_soc": 1,
        "end_soc": 1,
        "soc_change": 1,
        "energy_change": 2,
        "energy_charged_ac": 2,
        "energy_charged_dc": 2,
        "energy_performance": 2,
        "energy_performance_corrected": 2,
        "co2_per_kwh": 2,
        "cumulative_distance": 2,
    }

    COLUMN_DTYPES: ClassVar[dict[str, str]] = {
        "leg_type": "string",
        "origin_name": "string",
        "destination_name": "string",
        "cardinal_wind_direction": "string",
        "acc_pedal_position_hist_string": "string",
        "dec_pedal_position_hist_string": "string",
        "origin": "object",
        "destination": "object",
        "telematics_link": "object",
        "charger_link": "object",
        "logger_link": "object",
        "start": "object",
        "end": "object",
        "duration": "timedelta64[ns]",
        "distance": "float64",
        "average_speed": "float64",
        "elevation_difference": "float64",
        "vehicle_weight": "float64",
        # "vehicle_weight_cv": "float64",
        "recuperation": "float64",
        "start_soc": "float64",
        "end_soc": "float64",
        "soc_change": "float64",
        "energy_change": "float64",
        "energy_charged_ac": "float64",
        "energy_charged_dc": "float64",
        "energy_performance": "float64",
        "energy_performance_corrected": "float64",
        "co2_per_kwh": "float64",
        "cumulative_distance": "float64",
        "total_co2": "float64",
        "cumulative_co2": "float64",
        "charging_rate": "float64",
        "battery_capacity": "float64",
        "energy_output_from_charger": "float64",
        "energy_efficiency": "float64",
        "peak_charging": "float64",
        "average_charging": "float64",
        "energy_change_motor": "float64",
        "avg_temp": "float64",
        "avg_pressure": "float64",
        "avg_humidity": "float64",
        "avg_wind_speed": "float64",
        "cardinal_wind_direction": "string",
        "weather_type": "string",
        "acc_pedal_position_hist_string": "string",
        "dec_pedal_position_hist_string": "string",
    }

    def __init__(self, *args, **kwargs):
        if not args and "data" not in kwargs and "columns" not in kwargs:
            columns = list(self.COLUMNS_HEADERS_TYPES.keys())
            kwargs["data"] = {
                col: pd.Series(dtype=self.COLUMN_DTYPES.get(col, "float64"))
                for col in columns
            }
        super().__init__(*args, **kwargs)
