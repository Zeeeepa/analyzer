# SiteMemory Migration Checklist

## Quick Migration Guide

Use this checklist to migrate existing code to the new async SiteMemory.

## Option 1: Full Async Migration (Recommended)

### Step 1: Update Imports
```python
# No changes needed - imports remain the same
from site_memory import SiteMemory
```

### Step 2: Update Initialization
```python
# OLD
memory = SiteMemory()
# _load() was called automatically in __init__

# NEW
memory = SiteMemory()
await memory.initialize()  # Must call explicitly
```

### Step 3: Update Method Calls
Add `await` to all method calls:

```python
# OLD → NEW

memory.get_profile(url)
await memory.get_profile(url)

memory.get_or_create_profile(url)
await memory.get_or_create_profile(url)

memory.record_visit(url, duration)
await memory.record_visit(url, duration)

memory.cache_selector(url, purpose, selector)
await memory.cache_selector(url, purpose, selector)

memory.get_selector(url, purpose)
await memory.get_selector(url, purpose)

memory.record_quirk(url, description, workaround)
await memory.record_quirk(url, description, workaround)

memory.get_quirks(url)
await memory.get_quirks(url)

memory.cache_action_pattern(url, task_type, actions)
await memory.cache_action_pattern(url, task_type, actions)

memory.get_action_pattern(url, task_type)
await memory.get_action_pattern(url, task_type)

memory.get_context_for_prompt(url)
await memory.get_context_for_prompt(url)
```

### Step 4: Convert Functions to Async
```python
# OLD
def process_site(url):
    memory = SiteMemory()
    profile = memory.get_profile(url)
    # ...

# NEW
async def process_site(url):
    memory = SiteMemory()
    await memory.initialize()
    profile = await memory.get_profile(url)
    # ...
```

### Step 5: Update Callers
```python
# OLD
process_site("https://example.com")

# NEW
await process_site("https://example.com")

# Or from non-async code:
import asyncio
asyncio.run(process_site("https://example.com"))
```

### Step 6: Add Flush Before Exit (Optional)
```python
# Ensure pending writes are saved
await memory.flush()
```

## Option 2: Backward Compatible (Minimal Changes)

Use synchronous wrapper methods for quick migration:

### Step 1: Update Method Names
Add `_sync` suffix to all method calls:

```python
# OLD → NEW

memory.get_profile(url)
memory.get_profile_sync(url)

memory.get_or_create_profile(url)
memory.get_or_create_profile_sync(url)

memory.record_visit(url, duration)
memory.record_visit_sync(url, duration)

memory.cache_selector(url, purpose, selector)
memory.cache_selector_sync(url, purpose, selector)

memory.get_selector(url, purpose)
memory.get_selector_sync(url, purpose)

memory.record_quirk(url, description, workaround)
memory.record_quirk_sync(url, description, workaround)

memory.get_quirks(url)
memory.get_quirks_sync(url, purpose)

memory.cache_action_pattern(url, task_type, actions)
memory.cache_action_pattern_sync(url, task_type, actions)

memory.get_action_pattern(url, task_type)
memory.get_action_pattern_sync(url, task_type)

memory.get_context_for_prompt(url)
memory.get_context_for_prompt_sync(url)
```

### Step 2: Done!
No other changes needed. Code works as before.

**Note:** Plan to migrate to async methods eventually for better performance.

## Testing Checklist

After migration, verify:

- [ ] Code compiles without errors
- [ ] Single-agent operations work correctly
- [ ] Multi-agent concurrent operations don't corrupt data
- [ ] Lock timeouts are appropriate (no frequent timeouts)
- [ ] Cache TTL is appropriate (balance freshness vs performance)
- [ ] File permissions are correct
- [ ] Error handling works (try invalid paths, permissions)
- [ ] Backward compatibility (if using sync methods)

## Common Issues

### Issue: "RuntimeError: no running event loop"
**Solution:** You're using `_sync` methods from async code. Use async methods instead.

```python
# BAD (in async function)
async def foo():
    profile = memory.get_profile_sync(url)  # Wrong!

# GOOD
async def foo():
    profile = await memory.get_profile(url)  # Correct
```

### Issue: "TimeoutError: Failed to acquire lock"
**Solutions:**
1. Increase lock timeout: `SiteMemory(lock_timeout=30.0)`
2. Check for stuck processes holding locks
3. Delete lock file if process crashed: `rm ~/.eversale/site_memory.json.lock`

### Issue: Data not persisting
**Solution:** Call `await memory.flush()` before exit

```python
async def main():
    memory = SiteMemory()
    await memory.initialize()

    # ... operations ...

    await memory.flush()  # Ensure data saved

asyncio.run(main())
```

### Issue: "AttributeError: 'SiteMemory' object has no attribute 'get_profile_sync'"
**Solution:** You're using an old version of site_memory.py. Update the file.

## Performance Tuning

### For Single Agent Systems
```python
memory = SiteMemory(
    lock_timeout=5.0,   # Shorter timeout
    cache_ttl=0.0       # Disable cache refresh
)
```

### For Multi-Agent Systems (High Read)
```python
memory = SiteMemory(
    lock_timeout=15.0,  # Longer timeout for contention
    cache_ttl=120.0     # Long cache for read optimization
)
```

### For Multi-Agent Systems (High Write)
```python
memory = SiteMemory(
    lock_timeout=20.0,  # Longer timeout for write contention
    cache_ttl=10.0      # Short cache to see changes quickly
)
```

## Rollback Plan

If you need to rollback to the old version:

1. Restore old site_memory.py from git:
   ```bash
   git checkout HEAD~1 -- site_memory.py
   ```

2. Remove async-specific code:
   - Remove `await` keywords
   - Remove `async` function declarations
   - Remove `asyncio.run()` calls

3. Data format is compatible - no data migration needed

## Need Help?

- Read: `SITE_MEMORY_ASYNC_README.md` for detailed documentation
- Run: `python site_memory_example.py` to see working examples
- Check: Ensure `aiofiles` is installed: `pip install aiofiles`
