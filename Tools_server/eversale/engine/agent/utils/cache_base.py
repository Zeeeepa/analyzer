"""
Unified cache system for the agent.
Replaces 24 separate cache implementations with one flexible base.
"""
import time
import json
import asyncio
from pathlib import Path
from typing import Any, Optional, Dict, Callable
from collections import OrderedDict
import threading


class CacheBase:
    """
    Flexible cache with LRU eviction, TTL, and optional persistence.

    Usage:
        cache = CacheBase(max_size=100, ttl_seconds=3600)
        cache.set("key", value)
        value = cache.get("key")

        # With persistence
        cache = CacheBase(max_size=100, persist_path="~/.eversale/cache/my_cache.json")
    """

    def __init__(
        self,
        max_size: int = 100,
        ttl_seconds: Optional[int] = None,
        persist_path: Optional[str] = None,
        on_evict: Optional[Callable] = None
    ):
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: Dict[str, float] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._persist_path = Path(persist_path).expanduser() if persist_path else None
        self._on_evict = on_evict
        self._lock = threading.RLock()

        if self._persist_path and self._persist_path.exists():
            self._load()

    def get(self, key: str, default: Any = None) -> Any:
        """Get value, returns default if missing or expired."""
        with self._lock:
            if key not in self._cache:
                return default

            if self._is_expired(key):
                self.delete(key)
                return default

            # Move to end (mark as recently used)
            self._cache.move_to_end(key)
            return self._cache[key]

    def set(self, key: str, value: Any) -> None:
        """Set value with automatic LRU eviction."""
        with self._lock:
            # If key exists, remove it first (will re-add at end)
            if key in self._cache:
                del self._cache[key]
                del self._timestamps[key]

            # Add new entry at end
            self._cache[key] = value
            self._timestamps[key] = time.time()

            # Evict oldest if over max_size
            if len(self._cache) > self._max_size:
                self._evict_oldest()

            # Persist if configured
            if self._persist_path:
                self._save()

    def delete(self, key: str) -> bool:
        """Delete key, returns True if existed."""
        with self._lock:
            if key not in self._cache:
                return False

            value = self._cache[key]
            del self._cache[key]
            del self._timestamps[key]

            # Call eviction callback if provided
            if self._on_evict:
                try:
                    self._on_evict(key, value)
                except Exception:
                    pass  # Don't let callback errors break cache

            # Persist if configured
            if self._persist_path:
                self._save()

            return True

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            # Call eviction callback for all items if provided
            if self._on_evict:
                for key, value in list(self._cache.items()):
                    try:
                        self._on_evict(key, value)
                    except Exception:
                        pass

            self._cache.clear()
            self._timestamps.clear()

            # Persist if configured
            if self._persist_path:
                self._save()

    def _is_expired(self, key: str) -> bool:
        """Check if key has expired."""
        if self._ttl is None:
            return False

        if key not in self._timestamps:
            return True

        age = time.time() - self._timestamps[key]
        return age > self._ttl

    def _evict_oldest(self) -> None:
        """Remove oldest entry if over max_size."""
        while len(self._cache) > self._max_size:
            # OrderedDict: first item is oldest (FIFO)
            oldest_key = next(iter(self._cache))
            oldest_value = self._cache[oldest_key]

            del self._cache[oldest_key]
            del self._timestamps[oldest_key]

            # Call eviction callback if provided
            if self._on_evict:
                try:
                    self._on_evict(oldest_key, oldest_value)
                except Exception:
                    pass

    def _load(self) -> None:
        """Load from persistence file."""
        try:
            with open(self._persist_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Load cache entries
            if 'cache' in data:
                for key, value in data['cache'].items():
                    self._cache[key] = value

            # Load timestamps
            if 'timestamps' in data:
                for key, ts in data['timestamps'].items():
                    self._timestamps[key] = float(ts)

            # Clean up expired entries
            expired_keys = [k for k in self._cache.keys() if self._is_expired(k)]
            for key in expired_keys:
                self.delete(key)

        except (json.JSONDecodeError, IOError, KeyError):
            # If load fails, start with empty cache
            self._cache.clear()
            self._timestamps.clear()

    def _save(self) -> None:
        """Save to persistence file."""
        if not self._persist_path:
            return

        try:
            # Ensure directory exists
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)

            # Prepare data
            data = {
                'cache': dict(self._cache),
                'timestamps': self._timestamps
            }

            # Write atomically (write to temp, then rename)
            temp_path = self._persist_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            temp_path.replace(self._persist_path)

        except (IOError, OSError):
            # If save fails, continue without persistence
            pass

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def keys(self):
        """Return list of cache keys."""
        with self._lock:
            return list(self._cache.keys())

    def values(self):
        """Return list of cache values."""
        with self._lock:
            return list(self._cache.values())

    def items(self):
        """Return list of (key, value) tuples."""
        with self._lock:
            return list(self._cache.items())

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        with self._lock:
            now = time.time()
            expired_count = sum(1 for k in self._cache.keys() if self._is_expired(k))

            ages = [now - ts for ts in self._timestamps.values()]
            avg_age = sum(ages) / len(ages) if ages else 0

            return {
                'size': len(self._cache),
                'max_size': self._max_size,
                'expired_count': expired_count,
                'avg_age_seconds': avg_age,
                'ttl_seconds': self._ttl,
                'has_persistence': self._persist_path is not None
            }


class AsyncCacheBase(CacheBase):
    """Async-safe version of CacheBase."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._async_lock = asyncio.Lock()

    async def aget(self, key: str, default: Any = None) -> Any:
        """Async get value, returns default if missing or expired."""
        async with self._async_lock:
            return self.get(key, default)

    async def aset(self, key: str, value: Any) -> None:
        """Async set value with automatic LRU eviction."""
        async with self._async_lock:
            self.set(key, value)

    async def adelete(self, key: str) -> bool:
        """Async delete key, returns True if existed."""
        async with self._async_lock:
            return self.delete(key)

    async def aclear(self) -> None:
        """Async clear all entries."""
        async with self._async_lock:
            self.clear()

    async def astats(self) -> Dict[str, Any]:
        """Async get cache statistics."""
        async with self._async_lock:
            return self.stats()


# Convenience factories for common cache types
def create_llm_cache(max_size: int = 500, ttl_hours: int = 1) -> CacheBase:
    """Cache for LLM responses."""
    return CacheBase(
        max_size=max_size,
        ttl_seconds=ttl_hours * 3600,
        persist_path="~/.eversale/cache/llm_cache.json"
    )


def create_selector_cache(max_size: int = 200) -> CacheBase:
    """Cache for successful selectors."""
    return CacheBase(max_size=max_size, ttl_seconds=86400)  # 24 hours


def create_dom_cache(max_size: int = 50) -> CacheBase:
    """Cache for DOM snapshots (short TTL)."""
    return CacheBase(max_size=max_size, ttl_seconds=60)  # 1 minute


def create_session_cache(max_size: int = 100, ttl_minutes: int = 30) -> CacheBase:
    """Cache for browser sessions."""
    return CacheBase(
        max_size=max_size,
        ttl_seconds=ttl_minutes * 60,
        persist_path="~/.eversale/cache/session_cache.json"
    )


def create_api_cache(max_size: int = 1000, ttl_hours: int = 24) -> CacheBase:
    """Cache for API responses."""
    return CacheBase(
        max_size=max_size,
        ttl_seconds=ttl_hours * 3600,
        persist_path="~/.eversale/cache/api_cache.json"
    )


def create_memory_only_cache(max_size: int = 100, ttl_seconds: Optional[int] = None) -> CacheBase:
    """Cache for temporary in-memory storage (no persistence)."""
    return CacheBase(max_size=max_size, ttl_seconds=ttl_seconds)
