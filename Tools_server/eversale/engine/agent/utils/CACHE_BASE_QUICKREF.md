# CacheBase Quick Reference

## Import

```python
from utils import CacheBase, AsyncCacheBase
from utils import create_llm_cache, create_selector_cache, create_dom_cache
```

## Common Patterns

### Basic Cache
```python
cache = CacheBase(max_size=100)
cache.set("key", "value")
value = cache.get("key")  # Returns "value"
value = cache.get("missing", "default")  # Returns "default"
```

### Cache with TTL
```python
cache = CacheBase(max_size=100, ttl_seconds=3600)  # 1 hour
cache.set("key", "value")
# After 1 hour, cache.get("key") returns None
```

### Cache with Persistence
```python
cache = CacheBase(max_size=100, persist_path="~/.eversale/cache/data.json")
cache.set("key", "value")  # Automatically saved to disk
```

### Cache with Eviction Callback
```python
def cleanup(key, value):
    print(f"Evicting {key}")

cache = CacheBase(max_size=10, on_evict=cleanup)
```

### Async Cache
```python
async_cache = AsyncCacheBase(max_size=100)
await async_cache.aset("key", "value")
value = await async_cache.aget("key")
```

## Factory Functions

```python
# LLM responses (500 items, 1 hour TTL, persisted)
llm_cache = create_llm_cache(max_size=500, ttl_hours=1)

# Selectors (200 items, 24 hour TTL, memory only)
selector_cache = create_selector_cache(max_size=200)

# DOM snapshots (50 items, 60 second TTL, memory only)
dom_cache = create_dom_cache(max_size=50)

# Sessions (100 items, 30 min TTL, persisted)
session_cache = create_session_cache(max_size=100, ttl_minutes=30)

# API responses (1000 items, 24 hour TTL, persisted)
api_cache = create_api_cache(max_size=1000, ttl_hours=24)

# Temporary (100 items, 5 min TTL, memory only)
temp_cache = create_memory_only_cache(max_size=100, ttl_seconds=300)
```

## Operations

| Operation | Code | Returns |
|-----------|------|---------|
| Get | `cache.get("key")` | Value or None |
| Get with default | `cache.get("key", "default")` | Value or default |
| Set | `cache.set("key", value)` | None |
| Delete | `cache.delete("key")` | True/False |
| Clear | `cache.clear()` | None |
| Check exists | `"key" in cache` | True/False |
| Size | `len(cache)` | int |
| Keys | `cache.keys()` | list |
| Values | `cache.values()` | list |
| Items | `cache.items()` | list of tuples |
| Stats | `cache.stats()` | dict |

## Migration Cheat Sheet

| Old Pattern | New Pattern |
|-------------|-------------|
| `cache = {}` | `cache = CacheBase(max_size=100)` |
| `cache[key] = value` | `cache.set(key, value)` |
| `cache.get(key, default)` | `cache.get(key, default)` |
| `if key in cache:` | `if key in cache:` |
| `del cache[key]` | `cache.delete(key)` |
| `cache.clear()` | `cache.clear()` |
| `len(cache)` | `len(cache)` |
| `@lru_cache(maxsize=100)` | Use `CacheBase` manually |
| Manual TTL checking | `ttl_seconds` parameter |
| Manual JSON save/load | `persist_path` parameter |

## Examples

### Replace @lru_cache
```python
# OLD
from functools import lru_cache

@lru_cache(maxsize=100)
def expensive_call(arg):
    return compute(arg)

# NEW
cache = CacheBase(max_size=100)

def expensive_call(arg):
    result = cache.get(arg)
    if result is None:
        result = compute(arg)
        cache.set(arg, result)
    return result
```

### Replace Dict with TTL
```python
# OLD
cache = {}
timestamps = {}

def get_value(key):
    if key in cache and time.time() - timestamps[key] < 60:
        return cache[key]
    return None

def set_value(key, value):
    cache[key] = value
    timestamps[key] = time.time()

# NEW
cache = CacheBase(max_size=100, ttl_seconds=60)

def get_value(key):
    return cache.get(key)

def set_value(key, value):
    cache.set(key, value)
```

### Replace Dict with Size Limit
```python
# OLD
cache = {}

def set_value(key, value):
    cache[key] = value
    if len(cache) > 100:
        cache.popitem()

# NEW
cache = CacheBase(max_size=100)

def set_value(key, value):
    cache.set(key, value)  # Auto-evicts when full
```

## Thread Safety

All operations are thread-safe:

```python
cache = CacheBase(max_size=100)

def worker(i):
    cache.set(f"key_{i}", f"value_{i}")
    print(cache.get(f"key_{i}"))

threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

## Performance

- **O(1)** for get, set, delete
- **O(1)** for LRU eviction
- Thread-safe with minimal locking

## Testing

```bash
cd /mnt/c/ev29/cli/engine/agent
python3 test_cache_base.py
```
