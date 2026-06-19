"""Vehicle telematics data processor (dispatcher).

This module intentionally stays thin: it selects the right per-make/model
processor and delegates the actual processing work to `scripts/processors/*`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import srf_client

from jolt_toolkit.report_generator.data_class import ServerData

if TYPE_CHECKING:
    import pandas as pd


ProcessorClassLoader = Callable[[], type]


def _normalize(value: object) -> str:
    return str(value or "").strip()


def _load_volvo_processor() -> type:
    from jolt_toolkit.report_generator.data_processors.volvo import VolvoProcessor

    return VolvoProcessor

def _load_scania_processor() -> type:
    from jolt_toolkit.report_generator.data_processors.scania import ScaniaProcessor

    return ScaniaProcessor


# Override per (make, model) when a specific model needs a different algorithm.
_MODEL_PROCESSORS: dict[tuple[str, str], ProcessorClassLoader] = {}

# Default processor per make.
# 若某个 model 需要完全不同算法，则在_MODEL_PROCESSORS中注册
_MAKE_PROCESSORS: dict[str, ProcessorClassLoader] = {
    "Volvo": _load_volvo_processor,
    "Scania": _load_scania_processor,
}


class DataProcessor:
    def __init__(
        self,
        vehicle: srf_client.model.Vehicle,
        include_srf_logger_data: bool,
        include_weather_data: bool,
        use_auto_battery_capacity_calibration: bool,
        use_energy_correction_by_elevation: bool,
        srf_data: srf_client.SRFData,
        debug_mode: bool,
    ):
        self.vehicle_registration = vehicle.registration
        self.vehicle_make = vehicle.make
        self.vehicle_model = vehicle.model
        self.include_srf_logger_data = include_srf_logger_data
        self.include_weather_data = include_weather_data
        self.use_auto_battery_capacity_calibration = use_auto_battery_capacity_calibration
        self.use_energy_correction_by_elevation = use_energy_correction_by_elevation
        self.srf_data = srf_data
        self.debug_mode = debug_mode

    def data_process(self, server_data: ServerData) -> "pd.DataFrame":
        make = _normalize(self.vehicle_make)
        model = _normalize(self.vehicle_model)

        loader = _MODEL_PROCESSORS.get((make, model)) or _MAKE_PROCESSORS.get(make)
        if loader is None:
            raise NotImplementedError(f"Unsupported make/model: make={make!r} model={model!r}")

        processor_cls = loader()
        processor = processor_cls(
            vehicle_model=model,
            include_srf_logger_data=self.include_srf_logger_data,
            include_weather_data=self.include_weather_data,
            use_auto_battery_capacity_calibration=self.use_auto_battery_capacity_calibration,
            use_energy_correction_by_elevation=self.use_energy_correction_by_elevation,
            srf_data=self.srf_data,
            debug_mode=self.debug_mode,
        )
        return processor.process(server_data)
