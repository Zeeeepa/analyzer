# Caching Implementation for Agent Engine

This document describes the caching optimizations added to the agent engine to reduce expensive operations.

## Overview

Three key modules now have intelligent caching:

1. **llm_client.py** - Caches LLM API responses
2. **dom_distillation.py** - Caches DOM extraction results
3. **skill_library.py** - Caches skill search text generation

## 1. LLM Client Caching (llm_client.py)

### LLMCache Class
- **Purpose**: Cache repeated API calls with same parameters
- **Strategy**: Dict-based cache with TTL and LRU eviction
- **Configuration**:
  - TTL: 300 seconds (5 minutes)
  - Max size: 100 entries

### Key Features
- Generates MD5 hash key from: prompt + model + temperature + images_hash
- Only caches deterministic requests (temperature == 0)
- Automatic eviction of oldest entries when at capacity
- TTL-based expiration to prevent stale responses

### Usage
```python
client = LLMClient()
# First call - hits API
response1 = await client.generate("What is 2+2?", temperature=0)

# Second call with same prompt - uses cache
response2 = await client.generate("What is 2+2?", temperature=0)

# Clear cache if needed
client.clear_cache()
```

### Cache Key Generation
```python
key = MD5(prompt + "|" + model + "|" + str(temperature) + "|" + images_hash)
```

### When Cache is Used
- ✓ Temperature = 0 (deterministic)
- ✓ Successful response (no errors)
- ✗ Temperature > 0 (non-deterministic)
- ✗ Failed responses

## 2. DOM Distillation Caching (dom_distillation.py)

### DOMSnapshotCache Class
- **Purpose**: Prevent re-extracting unchanged pages
- **Strategy**: URL+mode as key, content hash validation
- **Configuration**:
  - TTL: 30 seconds
  - Max size: 50 snapshots

### Key Features
- Generates cache key from: URL + DistillationMode
- Content hash validation: MD5(title + innerHTML)
- Automatic invalidation when page content changes
- TTL to handle dynamic pages

### Usage
```python
engine = DOMDistillationEngine()

# First call - extracts DOM
snapshot1 = await engine.distill_page(page, DistillationMode.HYBRID)

# Second call on same page - uses cache
snapshot2 = await engine.distill_page(page, DistillationMode.HYBRID)

# If page changed - cache miss, re-extracts
await page.click("button")
snapshot3 = await engine.distill_page(page, DistillationMode.HYBRID)
```

### Cache Key Generation
```python
key = f"{url}|{mode.value}"
content_hash = MD5(title + "|" + innerHTML[:10000])
```

### Cache Invalidation Triggers
- TTL expired (30 seconds)
- Page content changed (detected via hash)
- Different distillation mode requested
- Manual clear_cache() call

## 3. Skill Library Caching (skill_library.py)

### Search Text Caching
- **Purpose**: Cache skill search text generation
- **Strategy**: functools.lru_cache on pure function
- **Configuration**: Max size: 500 entries

### Key Features
- Caches `_create_search_text_cached()` with @lru_cache(maxsize=500)
- Converts mutable types (lists) to hashable tuples
- Pure function with no side effects
- Automatic LRU eviction

### Usage
```python
retriever = SkillRetriever()

# First call - generates search text
search_text1 = retriever._create_search_text(skill)

# Second call with same skill - uses cache
search_text2 = retriever._create_search_text(skill)
```

### Cacheable Parameters
```python
@lru_cache(maxsize=500)
def _create_search_text_cached(
    skill_id: str,
    name: str,
    description: str,
    category: str,
    tags: tuple,      # Converted from list
    params: tuple     # Converted from dict.keys()
) -> str
```

### Async Caching (Already Present)
The skill library already had sophisticated async caching:
- SkillCache class with TTL and LRU
- AsyncRWLock for thread-safe concurrent access
- Pattern-based cache invalidation
- Batch operations support

## Performance Impact

### Expected Improvements

**LLM Client:**
- Deterministic queries (temp=0): 100% speedup (no API call)
- Typical scenario: 30-50% reduction in API calls
- Cost savings: Proportional to cache hit rate

**DOM Distillation:**
- Unchanged pages: 95%+ speedup (no extraction)
- Typical scenario: 40-60% reduction in extractions
- Most impactful for repeated page analysis

**Skill Library:**
- Search text generation: 80%+ speedup on repeated skills
- Most impactful during skill retrieval operations

### Memory Usage

**LLMCache:** ~10-50 MB (100 entries, depends on response size)
**DOMSnapshotCache:** ~50-200 MB (50 snapshots, depends on page complexity)
**SkillSearchCache:** ~1-5 MB (500 entries, small strings)

Total overhead: ~60-255 MB (acceptable for desktop agent)

## Cache Management

### Manual Cache Clearing

```python
# Clear LLM cache
llm_client.clear_cache()

# Clear DOM cache
dom_engine.clear_cache()

# Clear skill search cache (method level)
SkillRetriever._create_search_text_cached.cache_clear()
```

### Automatic Cache Management

All caches handle:
- TTL-based expiration
- LRU eviction at max capacity
- Thread-safe operations
- Graceful degradation on cache miss

## Best Practices

1. **LLM Client:**
   - Use temperature=0 for cacheable queries
   - Clear cache when switching contexts
   - Monitor cache hit rate via logs

2. **DOM Distillation:**
   - Let cache handle invalidation automatically
   - Don't rely on cache for rapidly changing pages
   - Consider TTL when analyzing dynamic content

3. **Skill Library:**
   - Cache cleared on skill updates (handled automatically)
   - No manual intervention needed
   - Monitor memory if skill count > 1000

## Debugging

Enable debug logs to see caching in action:

```python
import logging
logging.getLogger("loguru").setLevel("DEBUG")
```

Look for log messages:
- "Cache hit for LLM request"
- "Using cached DOM snapshot"
- "DOM cache hit for {url}"

## Future Enhancements

Potential improvements (not implemented):

1. **Persistent caching** - Save to disk between sessions
2. **Cache warming** - Pre-populate common queries
3. **Adaptive TTL** - Adjust based on page change frequency
4. **Distributed caching** - Share cache across agent instances
5. **Cache metrics** - Track hit rate, memory usage, etc.

## Testing

Basic test to verify caching works:

```python
import asyncio
from agent.llm_client import LLMClient

async def test_llm_cache():
    client = LLMClient()

    # First call - should hit API
    start = time.time()
    r1 = await client.generate("test", temperature=0)
    t1 = time.time() - start

    # Second call - should use cache
    start = time.time()
    r2 = await client.generate("test", temperature=0)
    t2 = time.time() - start

    print(f"First call: {t1:.2f}s")
    print(f"Second call: {t2:.2f}s")
    print(f"Speedup: {t1/t2:.1f}x")

    assert r1.content == r2.content
    assert t2 < t1 * 0.1  # Should be 10x faster

asyncio.run(test_llm_cache())
```

## Conclusion

These caching implementations provide significant performance improvements with minimal code changes and acceptable memory overhead. The caches are transparent to calling code and degrade gracefully on misses.
