"""
Mentor Hub Core Module

Contains shared utilities and configuration for the Mentor Hub platform.
"""

from .user_cache import (
    load_user_cache,
    save_user_cache,
    get_cached_user,
    add_to_cache,
    get_user_with_api_fallback,
    get_cache_stats,
)
from .config import (
    CHANNEL_IDS,
    SYSTEM_SETTINGS,
    TRACKS,
    get_readable_track_name,
    get_track_emoji,
    get_track_channel_id,
)

__all__ = [
    # user_cache functions
    "load_user_cache",
    "save_user_cache",
    "get_cached_user",
    "add_to_cache",
    "get_user_with_api_fallback",
    "get_cache_stats",
    # config exports
    "CHANNEL_IDS",
    "SYSTEM_SETTINGS",
    "TRACKS",
    "get_readable_track_name",
    "get_track_emoji",
    "get_track_channel_id",
]
