"""
Test suite for the unified cache base class.
Run with: python -m pytest test_cache_base.py -v
"""
import time
import asyncio
import tempfile
from pathlib import Path
from utils.cache_base import (
    CacheBase,
    AsyncCacheBase,
    create_llm_cache,
    create_selector_cache,
    create_dom_cache
)


def test_basic_get_set():
    """Test basic get/set operations."""
    cache = CacheBase(max_size=10)
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"
    assert cache.get("missing") is None
    assert cache.get("missing", "default") == "default"


def test_lru_eviction():
    """Test LRU eviction when max_size is exceeded."""
    cache = CacheBase(max_size=3)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert len(cache) == 3

    # Adding 4th item should evict 'a' (oldest)
    cache.set("d", 4)
    assert len(cache) == 3
    assert cache.get("a") is None  # evicted
    assert cache.get("b") == 2
    assert cache.get("c") == 3
    assert cache.get("d") == 4


def test_lru_access_updates_order():
    """Test that accessing an item makes it most recently used."""
    cache = CacheBase(max_size=3)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    # Access 'a' to make it most recently used
    cache.get("a")

    # Add new item - should evict 'b' (now oldest)
    cache.set("d", 4)
    assert cache.get("b") is None  # evicted
    assert cache.get("a") == 1  # kept (recently accessed)
    assert cache.get("c") == 3
    assert cache.get("d") == 4


def test_ttl_expiration():
    """Test TTL expiration."""
    cache = CacheBase(max_size=10, ttl_seconds=1)
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"

    # Wait for expiration
    time.sleep(1.1)
    assert cache.get("key1") is None  # expired


def test_delete():
    """Test delete operation."""
    cache = CacheBase(max_size=10)
    cache.set("key1", "value1")
    assert cache.delete("key1") is True
    assert cache.get("key1") is None
    assert cache.delete("missing") is False


def test_clear():
    """Test clear operation."""
    cache = CacheBase(max_size=10)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert len(cache) == 3

    cache.clear()
    assert len(cache) == 0
    assert cache.get("a") is None


def test_contains():
    """Test __contains__ operator."""
    cache = CacheBase(max_size=10)
    cache.set("key1", "value1")
    assert "key1" in cache
    assert "missing" not in cache


def test_persistence():
    """Test persistence to disk."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        temp_path = f.name

    try:
        # Create cache with persistence
        cache1 = CacheBase(max_size=10, persist_path=temp_path)
        cache1.set("key1", "value1")
        cache1.set("key2", "value2")

        # Load cache from same file
        cache2 = CacheBase(max_size=10, persist_path=temp_path)
        assert cache2.get("key1") == "value1"
        assert cache2.get("key2") == "value2"

    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_eviction_callback():
    """Test on_evict callback."""
    evicted_items = []

    def on_evict(key, value):
        evicted_items.append((key, value))

    cache = CacheBase(max_size=2, on_evict=on_evict)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)  # Should evict 'a'

    assert len(evicted_items) == 1
    assert evicted_items[0] == ("a", 1)


def test_stats():
    """Test cache statistics."""
    cache = CacheBase(max_size=10, ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)

    stats = cache.stats()
    assert stats['size'] == 2
    assert stats['max_size'] == 10
    assert stats['ttl_seconds'] == 60
    assert stats['expired_count'] == 0


def test_async_cache():
    """Test async cache operations."""
    async def run_test():
        cache = AsyncCacheBase(max_size=10)
        await cache.aset("key1", "value1")
        value = await cache.aget("key1")
        assert value == "value1"

        deleted = await cache.adelete("key1")
        assert deleted is True

        value = await cache.aget("key1")
        assert value is None

    asyncio.run(run_test())


def test_factory_llm_cache():
    """Test LLM cache factory."""
    cache = create_llm_cache(max_size=100, ttl_hours=2)
    assert cache._max_size == 100
    assert cache._ttl == 2 * 3600
    assert cache._persist_path is not None


def test_factory_selector_cache():
    """Test selector cache factory."""
    cache = create_selector_cache(max_size=50)
    assert cache._max_size == 50
    assert cache._ttl == 86400  # 24 hours


def test_factory_dom_cache():
    """Test DOM cache factory."""
    cache = create_dom_cache(max_size=25)
    assert cache._max_size == 25
    assert cache._ttl == 60  # 1 minute


def test_keys_values_items():
    """Test keys(), values(), items() methods."""
    cache = CacheBase(max_size=10)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    assert set(cache.keys()) == {"a", "b", "c"}
    assert set(cache.values()) == {1, 2, 3}
    assert set(cache.items()) == {("a", 1), ("b", 2), ("c", 3)}


def test_update_existing_key():
    """Test updating an existing key moves it to end (most recent)."""
    cache = CacheBase(max_size=3)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    # Update 'a' - should move to end
    cache.set("a", 10)

    # Add new item - should evict 'b' (now oldest)
    cache.set("d", 4)
    assert cache.get("b") is None  # evicted
    assert cache.get("a") == 10  # updated and kept
    assert cache.get("c") == 3
    assert cache.get("d") == 4


if __name__ == "__main__":
    print("Running cache tests...")
    test_basic_get_set()
    print("  basic get/set - PASS")

    test_lru_eviction()
    print("  LRU eviction - PASS")

    test_lru_access_updates_order()
    print("  LRU access order - PASS")

    test_ttl_expiration()
    print("  TTL expiration - PASS")

    test_delete()
    print("  delete - PASS")

    test_clear()
    print("  clear - PASS")

    test_contains()
    print("  contains - PASS")

    test_persistence()
    print("  persistence - PASS")

    test_eviction_callback()
    print("  eviction callback - PASS")

    test_stats()
    print("  stats - PASS")

    test_async_cache()
    print("  async cache - PASS")

    test_factory_llm_cache()
    print("  LLM cache factory - PASS")

    test_factory_selector_cache()
    print("  selector cache factory - PASS")

    test_factory_dom_cache()
    print("  DOM cache factory - PASS")

    test_keys_values_items()
    print("  keys/values/items - PASS")

    test_update_existing_key()
    print("  update existing key - PASS")

    print("\nAll tests passed!")
