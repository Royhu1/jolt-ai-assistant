"""
Weather data fetching module for JOLT Report.

Exposes the fine-grained weather patcher used by the report pipeline. The coarse
patcher lives in ``report_generator.weather_patcher``; the legacy standalone
fetcher/cache/key-manager trio was removed in v3.0.0 (it was only reachable from
the retired ``deprecated/`` per-make processors).
"""

from .fine_grained_patcher import FineGrainedWeatherPatcher

__all__ = [
    "FineGrainedWeatherPatcher",
]
