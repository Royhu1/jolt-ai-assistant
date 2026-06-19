"""
Weather data fetching module for JOLT Report.

This module provides:
- Weather data fetching from OpenWeather API
- Multi-key management with automatic rotation
- Local caching to reduce API calls
- Weather data enrichment for LegRecord objects
"""

from .weather_fetcher import enrich_weather_data
from .weather_key_manager import WeatherAPIKeyManager, get_weather_key_manager
from .weather_cache import WeatherCache, get_weather_cache
from .fine_grained_patcher import FineGrainedWeatherPatcher

__all__ = [
    'enrich_weather_data',
    'WeatherAPIKeyManager',
    'get_weather_key_manager',
    'WeatherCache',
    'get_weather_cache',
    'FineGrainedWeatherPatcher',
]
