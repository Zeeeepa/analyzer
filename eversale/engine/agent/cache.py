"""
Cache - Fast caching layer with TTL support and bounded memory.

Caches:
- Company research (24 hours)
- Page extractions (1 hour)
- Lead lists (6 hours)
- Login states (persistent)

Features:
- LRU eviction to prevent memory leaks
- Automatic cleanup of expired entries
- File-based persistence with memory cache
"""

import json
import hashlib
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Dict
from loguru import logger


class Cache:
    """File-based cache with TTL and bounded memory (LRU eviction)."""

    # Maximum items in memory cache before eviction
    MAX_MEMORY_ITEMS = 1000

    def __init__(self, cache_dir: str = ".cache", max_items: int = None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        # Use OrderedDict for LRU tracking
        self.memory_cache: OrderedDict[str, Dict] = OrderedDict()
        self.max_items = max_items or self.MAX_MEMORY_ITEMS
        self._cleanup_counter = 0

    def _get_key(self, namespace: str, key: str) -> str:
        """Generate cache key."""
        raw = f"{namespace}:{key}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _get_path(self, cache_key: str) -> Path:
        """Get file path for cache key."""
        return self.cache_dir / f"{cache_key}.json"

    def get(self, namespace: str, key: str) -> Optional[Any]:
        """Get value from cache if not expired (updates LRU order)."""
        cache_key = self._get_key(namespace, key)

        # Check memory first
        if cache_key in self.memory_cache:
            entry = self.memory_cache[cache_key]
            if datetime.fromisoformat(entry["expires"]) > datetime.now():
                # Move to end (most recently used) for LRU tracking
                self.memory_cache.move_to_end(cache_key)
                return entry["value"]
            else:
                del self.memory_cache[cache_key]

        # Check file
        path = self._get_path(cache_key)
        if path.exists():
            try:
                entry = json.loads(path.read_text())
                if datetime.fromisoformat(entry["expires"]) > datetime.now():
                    # Load into memory for faster access
                    self.memory_cache[cache_key] = entry
                    return entry["value"]
                else:
                    # Expired, delete
                    path.unlink()
            except Exception as e:
                logger.warning(f"Cache read error: {e}")

        return None

    def set(self, namespace: str, key: str, value: Any, ttl_seconds: int = 3600):
        """Set value in cache with TTL and LRU eviction."""
        cache_key = self._get_key(namespace, key)
        expires = datetime.now() + timedelta(seconds=ttl_seconds)

        entry = {
            "namespace": namespace,
            "key": key,
            "value": value,
            "expires": expires.isoformat(),
            "created": datetime.now().isoformat(),
        }

        # Remove if exists (to update LRU order)
        if cache_key in self.memory_cache:
            del self.memory_cache[cache_key]

        # Evict oldest items if at capacity (LRU eviction)
        while len(self.memory_cache) >= self.max_items:
            oldest_key = next(iter(self.memory_cache))
            del self.memory_cache[oldest_key]
            logger.debug(f"Cache evicted oldest entry: {oldest_key[:16]}...")

        # Save to memory (most recent goes to end)
        self.memory_cache[cache_key] = entry

        # Periodic cleanup of expired entries (every 100 writes)
        self._cleanup_counter += 1
        if self._cleanup_counter >= 100:
            self._cleanup_expired()
            self._cleanup_counter = 0

        # Save to file
        path = self._get_path(cache_key)
        try:
            path.write_text(json.dumps(entry, default=str))
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

    def _cleanup_expired(self):
        """Remove expired entries from memory cache."""
        now = datetime.now()
        expired_keys = [
            k for k, v in self.memory_cache.items()
            if datetime.fromisoformat(v["expires"]) <= now
        ]
        for k in expired_keys:
            del self.memory_cache[k]
        if expired_keys:
            logger.debug(f"Cache cleanup: removed {len(expired_keys)} expired entries")

    def delete(self, namespace: str, key: str):
        """Delete from cache."""
        cache_key = self._get_key(namespace, key)

        if cache_key in self.memory_cache:
            del self.memory_cache[cache_key]

        path = self._get_path(cache_key)
        if path.exists():
            path.unlink()

    def clear_namespace(self, namespace: str):
        """Clear all entries in a namespace."""
        # Clear memory
        to_delete = [k for k, v in self.memory_cache.items()
                    if v.get("namespace") == namespace]
        for k in to_delete:
            del self.memory_cache[k]

        # Clear files (would need to scan, so just clear all for simplicity)
        # In production, store namespace in filename or use proper DB

    def clear_all(self):
        """Clear entire cache."""
        self.memory_cache.clear()
        for f in self.cache_dir.glob("*.json"):
            f.unlink()


# Singleton cache instance
_cache = Cache()


# TTL presets (in seconds)
TTL_SHORT = 60 * 5  # 5 minutes
TTL_MEDIUM = 60 * 60  # 1 hour
TTL_LONG = 60 * 60 * 6  # 6 hours
TTL_DAY = 60 * 60 * 24  # 24 hours


# Convenience functions
def cache_research(company: str, data: Dict, ttl: int = TTL_DAY):
    """Cache company research."""
    _cache.set("research", company.lower(), data, ttl)


def get_cached_research(company: str) -> Optional[Dict]:
    """Get cached research for a company."""
    return _cache.get("research", company.lower())


def cache_page(url: str, data: Dict, ttl: int = TTL_MEDIUM):
    """Cache page extraction."""
    _cache.set("page", url, data, ttl)


def get_cached_page(url: str) -> Optional[Dict]:
    """Get cached page data."""
    return _cache.get("page", url)


def cache_leads(source: str, query: str, leads: list, ttl: int = TTL_LONG):
    """Cache lead list."""
    key = f"{source}:{query}"
    _cache.set("leads", key, leads, ttl)


def get_cached_leads(source: str, query: str) -> Optional[list]:
    """Get cached leads."""
    key = f"{source}:{query}"
    return _cache.get("leads", key)


def cache_login_state(service: str, logged_in: bool):
    """Cache login state (24 hours - validates more frequently for security)."""
    _cache.set("login", service, logged_in, TTL_DAY)


def get_cached_login_state(service: str) -> Optional[bool]:
    """Get cached login state."""
    return _cache.get("login", service)


class CachedExecutor:
    """Wrapper that adds caching to an executor."""

    def __init__(self, executor, cache_key_fn, ttl: int = TTL_MEDIUM):
        self.executor = executor
        self.cache_key_fn = cache_key_fn
        self.ttl = ttl

    async def execute(self, params: Dict) -> Any:
        # Generate cache key
        cache_key = self.cache_key_fn(params)

        # Check cache
        cached = _cache.get(self.executor.capability, cache_key)
        if cached:
            logger.info(f"Cache hit for {self.executor.capability}:{cache_key}")
            return cached

        # Execute and cache
        result = await self.executor.execute(params)

        if result.status.value == "success":
            _cache.set(self.executor.capability, cache_key, result, self.ttl)

        return result
