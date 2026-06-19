"""
Weather API Key Manager for OpenWeather API.

Manages multiple OpenWeather API keys with automatic rotation when quota is exceeded.
"""

import os
import logging
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


class WeatherAPIKeyManager:
    """
    Manages multiple OpenWeather API keys with automatic rotation.

    Features:
    - Multiple API key support
    - Automatic key rotation on quota exceeded (429 error)
    - Usage tracking per key
    - Status management (active/disabled)

    Usage:
        manager = WeatherAPIKeyManager(['key1', 'key2'])
        key = manager.get_available_key()
        manager.increment_usage(key)
        # If API returns 429:
        manager.disable_api_key(key)
    """

    _instance = None

    @classmethod
    def get_instance(cls):
        """Get singleton instance with keys from environment."""
        if cls._instance is None:
            keys_str = os.environ.get('OPENWEATHER_API_KEYS', '')
            keys = [k.strip() for k in keys_str.split(',') if k.strip()]
            if keys:
                cls._instance = cls(keys)
                logger.info(f"Initialized WeatherAPIKeyManager with {len(keys)} keys")
            else:
                logger.warning("No OPENWEATHER_API_KEYS found in environment")
                cls._instance = cls([])
        return cls._instance

    def __init__(self, api_keys: Optional[List[str]] = None):
        """
        Initialize the key manager.

        Args:
            api_keys: List of OpenWeather API keys
        """
        self.api_keys_dict: Dict[str, Dict] = {}
        if api_keys:
            for key in api_keys:
                self.add_api_key(key)

    def add_api_key(self, api_key: str) -> None:
        """
        Add a new API key to the manager.

        Args:
            api_key: OpenWeather API key string
        """
        if api_key not in self.api_keys_dict:
            masked_key = f"...{api_key[-8:]}" if len(api_key) > 8 else "***"
            logger.debug(f"Adding weather API key: {masked_key}")

            self.api_keys_dict[api_key] = {
                'status': True,
                'usage_count': 0
            }

    def get_available_key(self) -> Optional[str]:
        """
        Get an available (active) API key.

        Returns:
            API key string if available, None if all keys are disabled
        """
        for api_key, info in self.api_keys_dict.items():
            if info['status']:
                return api_key

        logger.error("No available weather API keys - all have been disabled")
        return None

    def increment_usage(self, api_key: str) -> None:
        """
        Increment the usage counter for a key.

        Args:
            api_key: The API key that was used
        """
        if api_key in self.api_keys_dict:
            self.api_keys_dict[api_key]['usage_count'] += 1

    def disable_api_key(self, api_key: str) -> bool:
        """
        Disable an API key (typically after quota exceeded).

        Args:
            api_key: The API key to disable

        Returns:
            True if key was disabled (first time), False if already disabled
        """
        if api_key in self.api_keys_dict:
            if self.api_keys_dict[api_key]['status']:
                self.api_keys_dict[api_key]['status'] = False
                masked_key = f"...{api_key[-8:]}" if len(api_key) > 8 else "***"
                logger.warning(f"Disabled weather API key: {masked_key}")
                return True
            return False
        return False

    def get_usage_count(self, api_key: str) -> int:
        """
        Get the usage count for a specific key.

        Args:
            api_key: The API key to check

        Returns:
            Usage count, or 0 if key not found
        """
        if api_key in self.api_keys_dict:
            return self.api_keys_dict[api_key]['usage_count']
        return 0

    def get_usage_summary(self) -> dict:
        """
        Get a summary of all keys and their usage.

        Returns:
            Dictionary with usage statistics
        """
        total_usage = sum(info['usage_count'] for info in self.api_keys_dict.values())
        active_keys = sum(1 for info in self.api_keys_dict.values() if info['status'])

        return {
            'total_keys': len(self.api_keys_dict),
            'active_keys': active_keys,
            'disabled_keys': len(self.api_keys_dict) - active_keys,
            'total_usage': total_usage,
            'keys_status': [
                {
                    'key': f"...{key[-8:]}" if len(key) > 8 else "***",
                    'status': 'active' if info['status'] else 'disabled',
                    'usage': info['usage_count']
                }
                for key, info in self.api_keys_dict.items()
            ]
        }


def get_weather_key_manager() -> WeatherAPIKeyManager:
    """
    Get the global WeatherAPIKeyManager instance.

    Returns:
        Singleton instance of WeatherAPIKeyManager
    """
    return WeatherAPIKeyManager.get_instance()
