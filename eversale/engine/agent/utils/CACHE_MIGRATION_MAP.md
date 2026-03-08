# Cache Migration Map

This document maps the 24+ separate cache implementations found in the codebase and shows how to replace them with `CacheBase`.

## Cache Locations

### 1. brain_enhanced_v2.py - Accessibility Cache

**Location:** Line ~150
```python
# OLD
self._accessibility_cache = {}  # url -> (timestamp, refs)

# NEW
from utils import create_memory_only_cache
self._accessibility_cache = create_memory_only_cache(max_size=100, ttl_seconds=300)
# Then use: self._accessibility_cache.set(url, (timestamp, refs))
#           self._accessibility_cache.get(url)
```

### 2. dom_distillation.py - DOM Snapshot Cache

**Location:** Line ~50
```python
# OLD
self._cache: Dict[str, Tuple[DOMSnapshot, str, float]] = {}

# NEW
from utils import create_dom_cache
self._cache = create_dom_cache(max_size=50)  # 60s TTL built-in
```

### 3. dom_distillation.py - Element Cache

**Location:** Line ~55
```python
# OLD
self._element_cache: Dict[str, ElementInfo] = {}

# NEW
from utils import create_memory_only_cache
self._element_cache = create_memory_only_cache(max_size=200, ttl_seconds=60)
```

### 4. llm_client.py - LLM Response Cache

**Location:** Line ~100
```python
# OLD
self._cache: Dict[str, tuple[LLMResponse, float]] = {}

# NEW
from utils import create_llm_cache
self._cache = create_llm_cache(max_size=500, ttl_hours=1)
# No need to manually store timestamps - TTL is built-in
```

### 5. playwright_direct.py - Page Cache (Global)

**Location:** Line ~30
```python
# OLD
_PAGE_CACHE: Dict[str, Tuple[Dict, float]] = {}

# NEW
from utils import create_dom_cache
_PAGE_CACHE = create_dom_cache(max_size=50)
# Remove manual timestamp tracking
```

### 6. playwright_direct.py - Instance Page Cache

**Location:** Line ~150
```python
# OLD
self._page_cache: Dict[str, Dict[str, Any]] = {}

# NEW
from utils import create_dom_cache
self._page_cache = create_dom_cache(max_size=50)
```

### 7. humanization/self_healing_selectors.py - Selector Cache

**Location:** Line ~40
```python
# OLD
self._cache: Dict[str, Dict[str, SelectorCacheEntry]] = {}

# NEW
from utils import create_selector_cache
self._cache = create_selector_cache(max_size=200)
# Store nested structure as-is or flatten keys like "domain:selector"
```

### 8. planner.py - Plan Cache

**Location:** Line ~70
```python
# OLD
self.plan_cache: Dict[str, ActionPlan] = {}

# NEW
from utils import create_memory_only_cache
self.plan_cache = create_memory_only_cache(max_size=100, ttl_seconds=3600)
```

### 9. planning_agent.py - Plan Cache

**Location:** Line ~80
```python
# OLD
self.plan_cache: Dict[str, Plan] = {}

# NEW
from utils import create_memory_only_cache
self.plan_cache = create_memory_only_cache(max_size=100, ttl_seconds=3600)
```

### 10. memory_architecture.py - Embedding Cache

**Location:** Line ~120
```python
# OLD
self.cache: Dict[str, List[float]] = {}

# NEW
from utils import CacheBase
self.cache = CacheBase(max_size=1000, ttl_seconds=86400, persist_path="~/.eversale/cache/embeddings.json")
```

### 11. episode_compressor.py - Wisdom Cache

**Location:** Line ~60
```python
# OLD
self._wisdom_cache: Dict[str, Wisdom] = {}

# NEW
from utils import CacheBase
self._wisdom_cache = CacheBase(max_size=200, ttl_seconds=7200, persist_path="~/.eversale/cache/wisdom.json")
```

### 12. prompt_cache.py - Action Cache

**Location:** Line ~40
```python
# OLD
self.cache: Dict[str, CachedAction] = {}

# NEW
from utils import create_memory_only_cache
self.cache = create_memory_only_cache(max_size=150, ttl_seconds=1800)
```

### 13. coordinate_targeting.py - Position Cache

**Location:** Line ~50
```python
# OLD
self.position_cache: Dict[str, ElementCoordinate] = {}

# NEW
from utils import create_memory_only_cache
self.position_cache = create_memory_only_cache(max_size=100, ttl_seconds=300)
```

### 14. reddit_handler.py - Response Cache

**Location:** Line ~25
```python
# OLD
_RESPONSE_CACHE: Dict[str, tuple] = {}  # url -> (data, timestamp)

# NEW
from utils import create_api_cache
_RESPONSE_CACHE = create_api_cache(max_size=500, ttl_hours=24)
# Remove manual timestamp tracking
```

### 15. pre_execution_validator.py - Approval Cache

**Location:** Line ~60
```python
# OLD
self.approval_cache: Dict[str, bool] = {}

# NEW
from utils import create_memory_only_cache
self.approval_cache = create_memory_only_cache(max_size=50, ttl_seconds=600)
```

### 16. lsp_client.py - Diagnostics Cache

**Location:** Line ~70
```python
# OLD
self.diagnostics_cache: Dict[str, List[Dict[str, Any]]] = {}

# NEW
from utils import create_memory_only_cache
self.diagnostics_cache = create_memory_only_cache(max_size=100, ttl_seconds=300)
```

## Migration Pattern

### Pattern 1: Simple Dict Cache

```python
# BEFORE
cache = {}
cache[key] = value
result = cache.get(key)

# AFTER
from utils import CacheBase
cache = CacheBase(max_size=100)
cache.set(key, value)
result = cache.get(key)
```

### Pattern 2: Dict with Manual Size Limit

```python
# BEFORE
cache = {}
cache[key] = value
if len(cache) > 100:
    cache.popitem()

# AFTER
from utils import CacheBase
cache = CacheBase(max_size=100)  # Auto-evicts
cache.set(key, value)
```

### Pattern 3: Dict with Timestamps (TTL)

```python
# BEFORE
cache = {}
timestamps = {}
cache[key] = value
timestamps[key] = time.time()
# Later: check if time.time() - timestamps[key] < 60

# AFTER
from utils import CacheBase
cache = CacheBase(max_size=100, ttl_seconds=60)
cache.set(key, value)  # Timestamp tracked automatically
# Later: cache.get(key) returns None if expired
```

### Pattern 4: Dict with JSON Persistence

```python
# BEFORE
try:
    with open('cache.json') as f:
        cache = json.load(f)
except:
    cache = {}
# Later: save manually

# AFTER
from utils import CacheBase
cache = CacheBase(max_size=100, persist_path="cache.json")
# Loads automatically on init, saves on every set()
```

### Pattern 5: Nested Dict Cache

```python
# BEFORE
cache = {}  # domain -> selector -> entry
if domain not in cache:
    cache[domain] = {}
cache[domain][selector] = entry

# AFTER
from utils import CacheBase
cache = CacheBase(max_size=200)
# Flatten keys: "domain:selector"
cache.set(f"{domain}:{selector}", entry)
```

### Pattern 6: @lru_cache Decorator

```python
# BEFORE
from functools import lru_cache

@lru_cache(maxsize=100)
def expensive_call(arg):
    return compute(arg)

# AFTER
from utils import CacheBase
cache = CacheBase(max_size=100)

def expensive_call(arg):
    result = cache.get(arg)
    if result is None:
        result = compute(arg)
        cache.set(arg, result)
    return result
```

## Benefits of Migration

1. **Unified API**: Same interface everywhere
2. **Automatic LRU**: No manual eviction logic
3. **Built-in TTL**: No timestamp tracking needed
4. **Thread-safe**: No manual locking required
5. **Persistence**: Optional, automatic save/load
6. **Statistics**: Monitor cache efficiency
7. **Callbacks**: Clean up resources on eviction

## Migration Checklist

For each cache to migrate:

- [ ] Identify cache type (simple dict, TTL, persistent, etc.)
- [ ] Choose appropriate factory function or CacheBase params
- [ ] Replace initialization
- [ ] Replace `cache[key] = value` with `cache.set(key, value)`
- [ ] Replace `cache.get(key)` (already compatible!)
- [ ] Remove manual eviction logic (if any)
- [ ] Remove manual timestamp tracking (if any)
- [ ] Remove manual persistence code (if any)
- [ ] Test thoroughly
- [ ] Remove old imports (time, json, etc. if no longer needed)

## Example Migration

### Before (brain_enhanced_v2.py)

```python
class BrainEnhanced:
    def __init__(self):
        self._accessibility_cache = {}  # url -> (timestamp, refs)

    def _get_cached_accessibility(self, url: str) -> Optional[Dict]:
        if url in self._accessibility_cache:
            timestamp, refs = self._accessibility_cache[url]
            if time.time() - timestamp < 300:  # 5 min TTL
                return refs
            del self._accessibility_cache[url]
        return None

    def _cache_accessibility(self, url: str, refs: Dict):
        self._accessibility_cache[url] = (time.time(), refs)
        # Manual eviction
        if len(self._accessibility_cache) > 100:
            oldest = min(self._accessibility_cache.keys(),
                        key=lambda k: self._accessibility_cache[k][0])
            del self._accessibility_cache[oldest]
```

### After (brain_enhanced_v2.py)

```python
from utils import create_memory_only_cache

class BrainEnhanced:
    def __init__(self):
        self._accessibility_cache = create_memory_only_cache(
            max_size=100,
            ttl_seconds=300
        )

    def _get_cached_accessibility(self, url: str) -> Optional[Dict]:
        return self._accessibility_cache.get(url)

    def _cache_accessibility(self, url: str, refs: Dict):
        self._accessibility_cache.set(url, refs)
```

**Lines reduced:** 20 → 8 (60% reduction)
**Manual logic removed:** TTL checking, eviction, timestamp tracking

## Testing After Migration

```python
# Add to test suite
def test_cache_migration():
    cache = create_memory_only_cache(max_size=3, ttl_seconds=1)

    # Test LRU
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    cache.set("d", 4)
    assert cache.get("a") is None  # evicted

    # Test TTL
    cache.set("e", 5)
    time.sleep(1.1)
    assert cache.get("e") is None  # expired
```

## Roll-out Strategy

1. **Phase 1: New Code** - Use CacheBase for all new features
2. **Phase 2: High-Impact** - Migrate llm_client, playwright_direct
3. **Phase 3: Medium-Impact** - Migrate dom_distillation, memory_architecture
4. **Phase 4: Low-Impact** - Migrate remaining caches
5. **Phase 5: Cleanup** - Remove old cache utilities

## Notes

- All migrations are **backward-compatible** (get/set API is the same)
- Migrations can be done **incrementally** (no big-bang required)
- **No performance regression** (O(1) operations maintained)
- **Reduced memory usage** (automatic eviction vs unbounded growth)
- **Easier testing** (mock cache, inspect stats)
