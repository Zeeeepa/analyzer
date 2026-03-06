# Unified Cache System (CacheBase)

## Overview

The `CacheBase` class replaces 24 separate cache implementations across the codebase with one flexible, thread-safe cache system featuring:

- LRU (Least Recently Used) eviction
- TTL (Time To Live) expiration
- Optional disk persistence
- Eviction callbacks
- Async support
- Thread-safe operations
- Factory functions for common use cases

## Quick Start

```python
from utils.cache_base import CacheBase, create_llm_cache

# Basic usage
cache = CacheBase(max_size=100)
cache.set("key", "value")
value = cache.get("key")

# With TTL
cache = CacheBase(max_size=100, ttl_seconds=3600)  # 1 hour

# With persistence
cache = CacheBase(max_size=100, persist_path="~/.eversale/cache/my_cache.json")

# Use factory functions
llm_cache = create_llm_cache(max_size=500, ttl_hours=1)
```

## Features

### 1. LRU Eviction

When the cache reaches `max_size`, the least recently used item is automatically removed:

```python
cache = CacheBase(max_size=3)
cache.set("a", 1)
cache.set("b", 2)
cache.set("c", 3)
cache.set("d", 4)  # "a" is evicted (oldest)

assert cache.get("a") is None  # evicted
assert cache.get("b") == 2     # still there
```

Accessing an item makes it "recently used":

```python
cache.set("a", 1)
cache.set("b", 2)
cache.set("c", 3)
cache.get("a")     # Mark "a" as recently used
cache.set("d", 4)  # "b" is evicted (now oldest)

assert cache.get("b") is None  # evicted
assert cache.get("a") == 1     # kept (recently accessed)
```

### 2. TTL Expiration

Items automatically expire after a specified time:

```python
cache = CacheBase(max_size=100, ttl_seconds=60)
cache.set("key", "value")

# After 60 seconds
assert cache.get("key") is None  # expired
```

### 3. Disk Persistence

Save cache to disk and reload across sessions:

```python
# First session
cache = CacheBase(max_size=100, persist_path="~/.eversale/cache/data.json")
cache.set("key", "value")
# Automatically saves to disk

# Later session
cache = CacheBase(max_size=100, persist_path="~/.eversale/cache/data.json")
assert cache.get("key") == "value"  # Loaded from disk
```

### 4. Eviction Callbacks

Execute cleanup code when items are evicted:

```python
def on_evict(key, value):
    print(f"Evicting {key}: {value}")
    cleanup_resource(value)

cache = CacheBase(max_size=10, on_evict=on_evict)
```

### 5. Async Support

Thread-safe async operations:

```python
from utils.cache_base import AsyncCacheBase

async_cache = AsyncCacheBase(max_size=100)

async def process():
    await async_cache.aset("key", "value")
    value = await async_cache.aget("key")
    await async_cache.adelete("key")
```

## API Reference

### CacheBase

#### Constructor

```python
CacheBase(
    max_size: int = 100,
    ttl_seconds: Optional[int] = None,
    persist_path: Optional[str] = None,
    on_evict: Optional[Callable] = None
)
```

**Parameters:**
- `max_size`: Maximum number of items (LRU eviction when exceeded)
- `ttl_seconds`: Time to live in seconds (None = no expiration)
- `persist_path`: Path to JSON file for persistence (None = memory only)
- `on_evict`: Callback function called when items are evicted

#### Methods

**get(key, default=None)**
```python
value = cache.get("key")
value = cache.get("missing", "default_value")
```
Returns value or default if key is missing or expired.

**set(key, value)**
```python
cache.set("key", "value")
```
Sets value with automatic LRU eviction if needed.

**delete(key)**
```python
deleted = cache.delete("key")  # Returns True if existed
```
Deletes key and returns whether it existed.

**clear()**
```python
cache.clear()
```
Removes all entries from cache.

**keys()**
```python
for key in cache.keys():
    print(key)
```
Returns list of cache keys.

**values()**
```python
for value in cache.values():
    print(value)
```
Returns list of cache values.

**items()**
```python
for key, value in cache.items():
    print(f"{key}: {value}")
```
Returns list of (key, value) tuples.

**stats()**
```python
stats = cache.stats()
# {
#   'size': 50,
#   'max_size': 100,
#   'expired_count': 5,
#   'avg_age_seconds': 120.5,
#   'ttl_seconds': 3600,
#   'has_persistence': True
# }
```
Returns cache statistics dictionary.

**__contains__(key)**
```python
if "key" in cache:
    print("Found!")
```
Check if key exists (not expired).

**__len__()**
```python
count = len(cache)
```
Returns number of items in cache.

### AsyncCacheBase

Extends `CacheBase` with async methods:

- `await aget(key, default=None)`
- `await aset(key, value)`
- `await adelete(key)`
- `await aclear()`
- `await astats()`

## Factory Functions

### create_llm_cache()
```python
create_llm_cache(max_size=500, ttl_hours=1)
```
Cache for LLM responses with persistence.

### create_selector_cache()
```python
create_selector_cache(max_size=200)
```
Cache for successful selectors (24 hour TTL).

### create_dom_cache()
```python
create_dom_cache(max_size=50)
```
Cache for DOM snapshots (60 second TTL).

### create_session_cache()
```python
create_session_cache(max_size=100, ttl_minutes=30)
```
Cache for browser sessions with persistence.

### create_api_cache()
```python
create_api_cache(max_size=1000, ttl_hours=24)
```
Cache for API responses with persistence.

### create_memory_only_cache()
```python
create_memory_only_cache(max_size=100, ttl_seconds=300)
```
Temporary in-memory cache (no persistence).

## Migration Guide

### Before (scattered implementations)

```python
# Pattern 1: Simple dict
selector_cache = {}
if url in selector_cache:
    return selector_cache[url]
selector_cache[url] = selector

# Pattern 2: Dict with size limit
if len(cache) > 100:
    cache.popitem()

# Pattern 3: Dict with TTL
cache_timestamps = {}
if url in cache and time.time() - cache_timestamps[url] < 60:
    return cache[url]

# Pattern 4: @lru_cache decorator
@lru_cache(maxsize=100)
def expensive_call(key):
    return result

# Pattern 5: Persistence
try:
    with open('cache.json') as f:
        cache = json.load(f)
except:
    cache = {}
```

### After (unified CacheBase)

```python
# All patterns unified
cache = CacheBase(max_size=100, ttl_seconds=60, persist_path="cache.json")

# Get with default
value = cache.get(key, default="not_found")

# Set (automatic eviction + persistence)
cache.set(key, value)

# Check existence
if key in cache:
    ...

# Statistics
stats = cache.stats()
```

## Thread Safety

All operations are thread-safe using `threading.RLock`:

```python
# Safe from multiple threads
cache = CacheBase(max_size=100)

def worker(i):
    cache.set(f"key_{i}", f"value_{i}")
    value = cache.get(f"key_{i}")

threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
for t in threads:
    t.start()
```

## Performance

- **O(1)** - get, set, delete operations
- **O(1)** - LRU eviction (OrderedDict.move_to_end)
- **O(n)** - clear, stats (where n = cache size)

## Persistence Format

Caches are saved as JSON with timestamps:

```json
{
  "cache": {
    "key1": "value1",
    "key2": "value2"
  },
  "timestamps": {
    "key1": 1702345678.123,
    "key2": 1702345680.456
  }
}
```

Expired entries are cleaned up on load.

## Common Use Cases

### 1. LLM Response Caching
```python
llm_cache = create_llm_cache(max_size=500, ttl_hours=1)

def call_llm(prompt):
    cached = llm_cache.get(prompt)
    if cached:
        return cached

    result = llm_api.complete(prompt)
    llm_cache.set(prompt, result)
    return result
```

### 2. Selector Caching
```python
selector_cache = create_selector_cache(max_size=200)

def find_element(url):
    selector = selector_cache.get(url)
    if selector:
        return selector

    selector = discover_selector(url)
    selector_cache.set(url, selector)
    return selector
```

### 3. Session Management
```python
session_cache = create_session_cache(max_size=100, ttl_minutes=30)

def on_session_evict(session_id, session_data):
    session_data.browser.close()

session_cache = CacheBase(
    max_size=100,
    ttl_seconds=1800,
    on_evict=on_session_evict
)
```

### 4. API Rate Limiting
```python
api_cache = create_api_cache(max_size=1000, ttl_hours=1)

def call_api(endpoint):
    # Check cache first (avoid rate limits)
    cached = api_cache.get(endpoint)
    if cached:
        return cached

    response = requests.get(endpoint)
    api_cache.set(endpoint, response.json())
    return response.json()
```

## Best Practices

1. **Choose appropriate max_size**: Balance memory usage vs hit rate
2. **Set TTL for data that can become stale**: Don't cache forever
3. **Use persistence for expensive operations**: LLM calls, API responses
4. **Use eviction callbacks for cleanup**: Close connections, free resources
5. **Monitor with stats()**: Track cache efficiency
6. **Use factory functions**: Pre-configured for common use cases

## Testing

Run the test suite:

```bash
cd /mnt/c/ev29/cli/engine/agent
python3 test_cache_base.py
```

All 16 tests should pass.

## Future Enhancements

Possible additions (not yet implemented):

- Cache warming strategies
- Hit/miss rate tracking
- Automatic cleanup of expired entries (background thread)
- Custom serialization for complex objects
- Cache key prefixing/namespacing
- Multi-level cache (L1/L2)
