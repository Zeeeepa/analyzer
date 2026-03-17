# CacheBase - Unified Cache System

## Quick Links

| Document | Description | When to Read |
|----------|-------------|--------------|
| **[CACHE_BASE_QUICKREF.md](CACHE_BASE_QUICKREF.md)** | Quick reference card | Starting a new feature, need syntax reminder |
| **[CACHE_BASE_README.md](CACHE_BASE_README.md)** | Full documentation | Understanding features, API reference |
| **[CACHE_MIGRATION_MAP.md](CACHE_MIGRATION_MAP.md)** | Migration guide | Replacing old cache implementations |
| **[CACHE_BASE_SUMMARY.md](CACHE_BASE_SUMMARY.md)** | Implementation summary | Project overview, what was built |

## Files

| File | Purpose | Lines |
|------|---------|-------|
| `cache_base.py` | Core implementation | 300 |
| `test_cache_base.py` | Test suite | 280 |
| `cache_base_example.py` | Usage examples | 180 |

## Quick Start

```python
from utils import create_llm_cache

# Create cache
cache = create_llm_cache(max_size=500, ttl_hours=1)

# Use cache
def expensive_call(arg):
    result = cache.get(arg)
    if result is None:
        result = compute(arg)
        cache.set(arg, result)
    return result
```

## Common Tasks

### I want to...

**...add a cache to my new feature**
→ Read: [CACHE_BASE_QUICKREF.md](CACHE_BASE_QUICKREF.md)

**...replace an existing cache**
→ Read: [CACHE_MIGRATION_MAP.md](CACHE_MIGRATION_MAP.md)

**...understand how it works**
→ Read: [CACHE_BASE_README.md](CACHE_BASE_README.md)

**...see working examples**
→ See: `cache_base_example.py`

**...run the tests**
→ Run: `python3 test_cache_base.py`

**...understand the API**
→ Read: [CACHE_BASE_README.md#api-reference](CACHE_BASE_README.md#api-reference)

## Factory Functions Cheat Sheet

| Function | Use Case | Max Size | TTL | Persist |
|----------|----------|----------|-----|---------|
| `create_llm_cache()` | LLM responses | 500 | 1 hour | Yes |
| `create_selector_cache()` | CSS selectors | 200 | 24 hours | No |
| `create_dom_cache()` | DOM snapshots | 50 | 60 seconds | No |
| `create_session_cache()` | Browser sessions | 100 | 30 minutes | Yes |
| `create_api_cache()` | API responses | 1000 | 24 hours | Yes |
| `create_memory_only_cache()` | Temporary data | Custom | Custom | No |

## Features

- ✓ LRU eviction
- ✓ TTL expiration
- ✓ Disk persistence
- ✓ Thread-safe
- ✓ Async support
- ✓ Eviction callbacks
- ✓ Cache statistics

## Testing

```bash
# Run test suite
cd /mnt/c/ev29/cli/engine/agent
python3 test_cache_base.py

# Quick import test
python3 -c "from utils import CacheBase; print('OK')"
```

## Documentation Map

```
utils/
├── cache_base.py                   # Implementation
├── cache_base_example.py           # Code examples
├── test_cache_base.py              # Tests (in agent/)
│
├── CACHE_BASE_INDEX.md             # This file (navigation)
├── CACHE_BASE_QUICKREF.md          # Quick reference
├── CACHE_BASE_README.md            # Full documentation
├── CACHE_MIGRATION_MAP.md          # Migration guide
└── CACHE_BASE_SUMMARY.md           # Implementation summary
```

## Integration

The cache system is integrated into the utils module:

```python
# Import from utils
from utils import CacheBase, AsyncCacheBase
from utils import create_llm_cache, create_selector_cache

# All exports available in utils.__all__
```

## Performance

- **O(1)** for get, set, delete
- **Thread-safe** with minimal locking
- **Memory-efficient** with automatic eviction

## Migration Status

**Found:** 55+ separate cache implementations
**Migrated:** 0 (ready to start)
**Next:** Follow [CACHE_MIGRATION_MAP.md](CACHE_MIGRATION_MAP.md)

## Support

**Issues?** Check the test suite:
```bash
python3 test_cache_base.py
```

**Questions?** Read the docs:
- Quick answer: [CACHE_BASE_QUICKREF.md](CACHE_BASE_QUICKREF.md)
- Deep dive: [CACHE_BASE_README.md](CACHE_BASE_README.md)

## Version

**Created:** 2025-12-12
**Status:** Production-ready, fully tested
**Tests:** 16/16 passing
