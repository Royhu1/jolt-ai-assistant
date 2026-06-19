"""
Weather data enrichment using OpenWeather API.

This module handles:
- Fetching historical weather data from OpenWeather API
- Coordinate format conversion
- Weather data enrichment for LegRecord objects
- Local caching to avoid repeated API requests
"""

import logging
import requests
import numpy as np
from typing import List, Tuple, Optional
from numpy import isnan
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from .weather_key_manager import get_weather_key_manager
from .weather_cache import get_weather_cache

logger = logging.getLogger(__name__)

# Thread-safe lock for key manager operations
_key_manager_lock = threading.Lock()


class QuotaExceededException(Exception):
    """Exception raised when API quota is exceeded (HTTP 429)."""
    pass


def fetch_weather_from_openweather_api(
    lat: float,
    lon: float,
    dt: int,
    api_key: str
) -> Tuple[float, float, float, float, int]:
    """
    Fetch historical weather data from OpenWeather API.

    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        dt: Unix timestamp
        api_key: OpenWeather API key

    Returns:
        Tuple of (temperature_C, pressure_hPa, humidity_%, wind_speed_m/s, wind_deg)

    Raises:
        QuotaExceededException: When API returns 429 status
        requests.RequestException: For other HTTP errors
    """
    url = f"https://api.openweathermap.org/data/3.0/onecall/timemachine?lat={lat}&lon={lon}&dt={dt}&appid={api_key}"

    try:
        response = requests.get(url, timeout=10)

        if response.status_code == 429:
            raise QuotaExceededException("API quota exceeded (429)")

        response.raise_for_status()
        weather = response.json()['data'][0]

        temp = weather['temp'] - 273.15  # Kelvin to Celsius
        pressure = weather['pressure']   # hPa
        humidity = weather['humidity']   # %
        wind_speed = weather['wind_speed']  # m/s
        wind_deg = weather['wind_deg']   # degrees

        return temp, pressure, humidity, wind_speed, wind_deg

    except requests.RequestException as e:
        logger.error(f"Weather API request failed: {e}")
        raise


def enrich_weather_data(
    leg_record_list: List,
    api_key: Optional[str] = None,
    use_cache: bool = True,
    precision: int = 6
) -> List:
    """
    Enrich trip records with weather data from OpenWeather API with caching support.

    Only processes records that:
    - Have valid energy_performance (not NaN, not 0)
    - Have valid origin and destination coordinates

    Args:
        leg_record_list: List of LegRecord objects
        api_key: Optional API key (uses multi-key manager if not provided)
        use_cache: Whether to use local caching (default: True)
        precision: Coordinate precision for caching (default: 6)

    Returns:
        Updated list of LegRecord objects with weather data
    """
    if not leg_record_list:
        logger.info("No records to process for weather enrichment")
        return leg_record_list

    key_manager = get_weather_key_manager()
    cache = get_weather_cache(precision=precision) if use_cache else None

    # Step 1: Filter records that need weather data
    records_to_process = []
    record_locations = []  # List of (origin_lat, origin_lon, origin_dt, dest_lat, dest_lon, dest_dt)

    for record in leg_record_list:
        # Filter: only process records with valid energy_performance
        if (record.energy_performance is None or
            (isinstance(record.energy_performance, float) and isnan(record.energy_performance)) or
            record.energy_performance == 0):
            continue

        # Check for valid coordinates
        if record.origin is None or record.destination is None:
            continue

        if record.time_start is None or record.time_end is None:
            continue

        try:
            origin_lat, origin_lon = record.origin
            dest_lat, dest_lon = record.destination

            if any(v is None for v in [origin_lat, origin_lon, dest_lat, dest_lon]):
                continue

            origin_dt = int(record.time_start.timestamp())
            dest_dt = int(record.time_end.timestamp())

            records_to_process.append(record)
            record_locations.append((origin_lat, origin_lon, origin_dt, dest_lat, dest_lon, dest_dt))

        except (ValueError, TypeError, AttributeError) as e:
            logger.debug(f"Failed to parse coordinates for record: {e}")
            continue

    if not records_to_process:
        logger.info("No records need weather enrichment")
        return leg_record_list

    logger.info(f"Processing weather for {len(records_to_process)}/{len(leg_record_list)} records")

    # Step 2: Collect all unique (lat, lon, timestamp) tuples for batch cache lookup
    all_locations = []
    location_set = set()

    for origin_lat, origin_lon, origin_dt, dest_lat, dest_lon, dest_dt in record_locations:
        origin_loc = (origin_lat, origin_lon, origin_dt)
        dest_loc = (dest_lat, dest_lon, dest_dt)

        if origin_loc not in location_set:
            all_locations.append(origin_loc)
            location_set.add(origin_loc)
        if dest_loc not in location_set:
            all_locations.append(dest_loc)
            location_set.add(dest_loc)

    # Step 3: Check cache for existing weather data
    location_weather_map = {}  # Map (lat, lon, timestamp) to weather data
    cache_hit_count = 0
    original_missing_count = 0

    if use_cache and cache:
        cached_weather, missing_locations = cache.get_batch(all_locations)

        for loc, weather in zip(all_locations, cached_weather):
            if weather is not None:
                location_weather_map[loc] = weather

        cache_hit_count = len(all_locations) - len(missing_locations)
        original_missing_count = len(missing_locations)

        if not missing_locations:
            logger.info(f"{len(all_locations)} unique locations, all found in cache")
        else:
            logger.info(f"{len(all_locations)} unique locations: {cache_hit_count} cached, {original_missing_count} need API")
            all_locations = missing_locations  # Only fetch missing locations
    else:
        missing_locations = all_locations
        original_missing_count = len(all_locations)
        logger.info(f"{len(all_locations)} unique locations need API requests")

    # Step 4: Fetch missing weather data from API (concurrent version)
    api_calls_count = 0
    newly_fetched = []
    failed_locations_count = 0

    if missing_locations:
        # Pre-check API availability before attempting any requests
        if not api_key:
            test_key = key_manager.get_available_key()
            if not test_key:
                logger.error(f"No available weather API keys. "
                           f"Cannot fetch data for {len(missing_locations)} locations. "
                           f"Weather fields will remain as NA for affected records.")
                failed_locations_count = len(missing_locations)
                missing_locations = []  # Skip API fetching

        # Concurrent API fetching with ThreadPoolExecutor
        max_workers = 30  # Concurrent requests (adjustable based on API limits)

        def fetch_single_location(location):
            """Fetch weather for a single location (thread-safe)."""
            lat, lon, dt = location

            # Thread-safe key retrieval
            with _key_manager_lock:
                current_api_key = api_key or key_manager.get_available_key()

            if not current_api_key:
                return location, None, "no_key"

            try:
                weather_data = fetch_weather_from_openweather_api(lat, lon, dt, current_api_key)

                # Thread-safe usage increment
                with _key_manager_lock:
                    key_manager.increment_usage(current_api_key)

                return location, weather_data, None

            except QuotaExceededException:
                # Thread-safe key disabling
                with _key_manager_lock:
                    was_disabled = key_manager.disable_api_key(current_api_key)
                    if was_disabled:
                        logger.warning(f"Weather API key quota exceeded, rotating to next available key")

                return location, None, "quota_exceeded"

            except Exception as e:
                return location, None, str(e)

        # Execute concurrent fetches
        logger.info(f"Fetching weather data for {len(missing_locations)} locations with {max_workers} concurrent workers...")

        # Error statistics
        quota_exceeded_count = 0
        network_error_count = 0
        other_error_count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_location = {
                executor.submit(fetch_single_location, loc): loc
                for loc in missing_locations
            }

            # Collect results as they complete
            for future in as_completed(future_to_location):
                location, weather_data, error = future.result()

                if weather_data is not None:
                    location_weather_map[location] = weather_data
                    newly_fetched.append((location, weather_data))
                    api_calls_count += 1
                else:
                    failed_locations_count += 1
                    if error == "no_key":
                        logger.warning(f"No available API keys, stopping fetch")
                        for f in future_to_location:
                            f.cancel()
                        break
                    elif error == "quota_exceeded":
                        quota_exceeded_count += 1
                    elif error and "timeout" in str(error).lower():
                        network_error_count += 1
                    elif error:
                        other_error_count += 1

        # Summary of errors
        if quota_exceeded_count > 0:
            logger.info(f"Quota exceeded for {quota_exceeded_count} requests (keys automatically rotated)")
        if network_error_count > 0:
            logger.warning(f"Network timeouts: {network_error_count} requests failed")
        if other_error_count > 0:
            logger.warning(f"Other errors: {other_error_count} requests failed")

        # Step 5: Cache newly fetched data
        if use_cache and cache and newly_fetched:
            locations_to_cache = [loc for loc, _ in newly_fetched]
            weather_to_cache = [weather for _, weather in newly_fetched]
            cache.put_batch(locations_to_cache, weather_to_cache)

    # Step 6: Update records with weather data
    enriched_count = 0

    for record, (origin_lat, origin_lon, origin_dt, dest_lat, dest_lon, dest_dt) in zip(
        records_to_process, record_locations
    ):
        origin_weather = location_weather_map.get((origin_lat, origin_lon, origin_dt))
        dest_weather = location_weather_map.get((dest_lat, dest_lon, dest_dt))

        if origin_weather and dest_weather:
            temp_ori, press_ori, humid_ori, wind_ori, dir_ori = origin_weather
            temp_dest, press_dest, humid_dest, wind_dest, dir_dest = dest_weather

            # Calculate averages and update record
            record.avg_temp = round(np.mean([temp_ori, temp_dest]), 1)
            record.avg_pressure = round(np.mean([press_ori, press_dest]), 1)
            record.avg_humidity = round(np.mean([humid_ori, humid_dest]), 1)
            record.avg_wind_speed = round(np.mean([wind_ori, wind_dest]), 1)
            avg_wind_deg = int(np.mean([dir_ori, dir_dest]))
            record.cardinal_wind_direction = str(avg_wind_deg)

            enriched_count += 1

    # Log concise summary
    total_unique_locations = cache_hit_count + original_missing_count
    logger.info(f"Weather enrichment: {enriched_count}/{len(records_to_process)} records enriched, "
                f"{api_calls_count} API calls, {cache_hit_count}/{total_unique_locations} cache hits, "
                f"{failed_locations_count} failures")

    summary = key_manager.get_usage_summary()
    logger.info(f"Weather API keys: {summary['active_keys']}/{summary['total_keys']} active, {summary['total_usage']} total calls")

    if use_cache and cache:
        cache_stats = cache.get_stats()
        logger.info(f"Weather cache: {cache_stats['total_entries']} entries, {cache_stats['file_size_kb']:.1f} KB")

    return leg_record_list
