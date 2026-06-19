"""
Weather Data Cache Module

Provides local caching for OpenWeather API results to reduce API calls and costs.
Caches coordinate-timestamp-weather tuples in a JSON file with thread-safe operations.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from filelock import FileLock

logger = logging.getLogger(__name__)


class WeatherCache:
    """
    Manages local cache for weather data.

    Features:
    - Stores coordinate-timestamp-weather tuples in JSON format
    - Thread-safe file operations using filelock
    - Configurable coordinate precision for matching
    - Automatic cache initialization
    - Weather data includes: temperature, pressure, humidity, wind_speed, wind_deg
    """

    def __init__(self,
                 cache_file: Optional[str] = None,
                 precision: int = 6):
        """
        Initialize the weather cache.

        Args:
            cache_file: Path to cache file (default: from env or './cache/.weather_cache.json')
            precision: Decimal places for coordinate precision (default: 6)
        """
        if cache_file is None:
            cache_file = os.environ.get('WEATHER_CACHE_FILE', './cache/.weather_cache.json')

        self.cache_file = Path(cache_file)
        self.lock_file = Path(str(cache_file) + '.lock')
        self.precision = precision

        if not self.cache_file.exists():
            self._initialize_cache()

        logger.info(f"Weather cache initialized: {self.cache_file} (precision={precision})")

    def _initialize_cache(self) -> None:
        """Create a new cache file with initial structure."""
        initial_data = {
            "metadata": {
                "version": "1.0",
                "precision": self.precision,
                "description": "Weather cache for OpenWeather API results"
            },
            "cache": {}
        }

        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(initial_data, f, indent=2)

        logger.info(f"Initialized new weather cache: {self.cache_file}")

    def _normalize_key(self, lat: float, lon: float, dt: int) -> str:
        """
        Normalize coordinate and timestamp to cache key.

        Args:
            lat: Latitude
            lon: Longitude
            dt: Unix timestamp

        Returns:
            String key in format "lat,lon,timestamp" with specified precision
        """
        return f"{lat:.{self.precision}f},{lon:.{self.precision}f},{dt}"

    def _load_cache(self) -> Dict:
        """
        Load cache data from file with thread safety.

        Returns:
            Dictionary containing cache data
        """
        with FileLock(self.lock_file, timeout=10):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if "cache" not in data:
                    logger.warning("Old cache format detected, migrating...")
                    data = {
                        "metadata": {
                            "version": "1.0",
                            "precision": self.precision
                        },
                        "cache": data
                    }

                return data

            except (json.JSONDecodeError, FileNotFoundError) as e:
                logger.error(f"Error loading cache file: {e}")
                self._initialize_cache()
                return self._load_cache()

    def _save_cache(self, data: Dict) -> None:
        """
        Save cache data to file with thread safety.

        Args:
            data: Dictionary containing cache data
        """
        with FileLock(self.lock_file, timeout=10):
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    def get(self, lat: float, lon: float, dt: int) -> Optional[Tuple[float, float, float, float, int]]:
        """
        Get weather from cache for a coordinate and timestamp.

        Args:
            lat: Latitude
            lon: Longitude
            dt: Unix timestamp

        Returns:
            Tuple of (temp_C, pressure_hPa, humidity_%, wind_speed_m/s, wind_deg),
            or None if not found in cache
        """
        cache_key = self._normalize_key(lat, lon, dt)
        data = self._load_cache()

        weather_data = data.get("cache", {}).get(cache_key)

        if weather_data is not None:
            logger.debug(f"Cache HIT: {cache_key}")
            return tuple(weather_data)

        return None

    def get_batch(
        self,
        locations: List[Tuple[float, float, int]]
    ) -> Tuple[List[Optional[Tuple]], List[Tuple[float, float, int]]]:
        """
        Get weather for multiple coordinate-timestamp pairs, identifying cache hits and misses.

        Args:
            locations: List of (latitude, longitude, timestamp) tuples

        Returns:
            Tuple of (weather_data, missing_locations)
            - weather_data: List with cached tuples or None for misses
            - missing_locations: List of coordinates not found in cache
        """
        data = self._load_cache()
        cache = data.get("cache", {})

        weather_data = []
        missing_locations = []

        for lat, lon, dt in locations:
            cache_key = self._normalize_key(lat, lon, dt)
            weather = cache.get(cache_key)

            if weather is not None:
                weather_data.append(tuple(weather))
                logger.debug(f"Cache HIT: {cache_key}")
            else:
                weather_data.append(None)
                missing_locations.append((lat, lon, dt))
                logger.debug(f"Cache MISS: {cache_key}")

        hit_rate = (len(locations) - len(missing_locations)) / len(locations) * 100 if locations else 0
        logger.info(f"Weather cache statistics: {len(locations) - len(missing_locations)}/{len(locations)} hits ({hit_rate:.1f}%)")

        return weather_data, missing_locations

    def put(
        self,
        lat: float,
        lon: float,
        dt: int,
        temp: float,
        pressure: float,
        humidity: float,
        wind_speed: float,
        wind_deg: int
    ) -> None:
        """
        Store weather data in cache for a coordinate and timestamp.

        Args:
            lat: Latitude
            lon: Longitude
            dt: Unix timestamp
            temp: Temperature in Celsius
            pressure: Pressure in hPa
            humidity: Humidity in %
            wind_speed: Wind speed in m/s
            wind_deg: Wind direction in degrees
        """
        cache_key = self._normalize_key(lat, lon, dt)

        data = self._load_cache()
        data["cache"][cache_key] = [temp, pressure, humidity, wind_speed, wind_deg]
        self._save_cache(data)

        logger.debug(f"Cached: {cache_key} -> temp={temp}C")

    def put_batch(
        self,
        locations: List[Tuple[float, float, int]],
        weather_data: List[Tuple[float, float, float, float, int]]
    ) -> None:
        """
        Store multiple coordinate-timestamp-weather tuples in cache.

        Args:
            locations: List of (latitude, longitude, timestamp) tuples
            weather_data: List of (temp, pressure, humidity, wind_speed, wind_deg) tuples
        """
        if len(locations) != len(weather_data):
            raise ValueError("Locations and weather_data lists must have the same length")

        data = self._load_cache()
        cache = data.get("cache", {})

        count = 0
        for (lat, lon, dt), weather in zip(locations, weather_data):
            if weather is not None and len(weather) == 5:
                cache_key = self._normalize_key(lat, lon, dt)
                cache[cache_key] = list(weather)
                count += 1

        data["cache"] = cache
        self._save_cache(data)

        logger.info(f"Cached {count} new weather data entries")

    def get_stats(self) -> Dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        data = self._load_cache()
        cache = data.get("cache", {})

        return {
            "total_entries": len(cache),
            "cache_file": str(self.cache_file),
            "file_size_kb": self.cache_file.stat().st_size / 1024 if self.cache_file.exists() else 0,
            "precision": self.precision
        }

    def clear(self) -> None:
        """Clear all cache entries."""
        data = self._load_cache()
        data["cache"] = {}
        self._save_cache(data)
        logger.info("Weather cache cleared")


# Global cache instances (keyed by precision)
_weather_caches = {}


def get_weather_cache(precision: int = 6) -> WeatherCache:
    """
    Get or create a global weather cache instance for the specified precision.

    Args:
        precision: Coordinate precision (default: 6)

    Returns:
        WeatherCache instance
    """
    global _weather_caches
    if precision not in _weather_caches:
        _weather_caches[precision] = WeatherCache(precision=precision)
    return _weather_caches[precision]
