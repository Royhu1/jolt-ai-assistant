import pandas as pd
from jolt_toolkit.deprecated.data_processors.volvo import VolvoProcessor
from jolt_toolkit.deprecated.data_processors.scania import ScaniaProcessor
from jolt_toolkit.deprecated.data_processors.renault import RenaultProcessor
from jolt_toolkit.deprecated.data_processors.mercedes import MercedesProcessor

class DataProcessorRegistry:
    def __init__(self):
        self._registry = pd.DataFrame(columns=["registration", "make", "model", "processor", "Battery Capacity (kWh)"])
        self.register_processor("YK73WFN", "Volvo", "FE Electric", VolvoProcessor, 378.0)
        self.register_processor("EV73SAL", "Volvo", "FE Electric", VolvoProcessor, 378.0)
        self.register_processor("KY24LHT", "Volvo", None, VolvoProcessor, 540.0)
        self.register_processor("AV24LXK", "Volvo", "FL Electric", VolvoProcessor, 265.0)
        self.register_processor("AV24LXL", "Volvo", "FL Electric", VolvoProcessor, 265.0)
        self.register_processor("AV24LXJ", "Volvo", "FL Electric", VolvoProcessor, 265.0)
        self.register_processor("N88GNW", "Renault", "E-Tech T", RenaultProcessor, 417.0)
        self.register_processor("EX74JXW", "Scania", "23P", ScaniaProcessor, 475.0)
        self.register_processor("EX74JXY", "Scania", "23P", ScaniaProcessor, 475.0)
        self.register_processor("YN25RSY", "Mercedes", "eActros 600", MercedesProcessor, 600.0)

    def register_processor(self, registration: str, make: str, model: str, processor: type, battery_capacity_kwh: float):
        new_entry = pd.DataFrame(
            [
                {
                    "registration": registration,
                    "make": make,
                    "model": model,
                    "processor": processor,
                    "Battery Capacity (kWh)": battery_capacity_kwh,
                }
            ],
            columns=self._registry.columns,
        )
        if self._registry.empty:
            self._registry = new_entry
        else:
            self._registry = pd.concat([self._registry, new_entry], ignore_index=True)

    def get_data_processor(self, registration: str) -> type | None:
        entry = self._registry[self._registry["registration"] == registration]
        # print('entry: ', entry)
        if entry.empty:
            raise ValueError(f"No processor found for registration: {registration}")
        return entry.iloc[0]["processor"]
    
    def get_battery_capacity(self, registration: str) -> float | None:
        entry = self._registry[self._registry["registration"] == registration]
        if entry.empty:
            raise ValueError(f"No battery capacity found for registration: {registration}")
        return entry.iloc[0]["Battery Capacity (kWh)"]
