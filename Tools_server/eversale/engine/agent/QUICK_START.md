# SiteMemory Async - Quick Start Guide

## 1. Install Dependencies (1 minute)

```bash
cd /mnt/c/ev29/eversale-cli/engine/agent
pip install -r requirements_async.txt
```

## 2. Choose Your Migration Path

### Path A: Full Async (Recommended for New Code)

**Step 1:** Update your imports (no changes needed)
```python
from site_memory import SiteMemory
```

**Step 2:** Make your function async
```python
# Before
def process_sites():
    memory = SiteMemory()
    # ...

# After
async def process_sites():
    memory = SiteMemory()
    await memory.initialize()
    # ...
```

**Step 3:** Add await to method calls
```python
# Before
profile = memory.get_profile(url)

# After
profile = await memory.get_profile(url)
```

**Step 4:** Run with asyncio
```python
import asyncio
asyncio.run(process_sites())
```

### Path B: Quick Sync Migration (Minimal Changes)

Just add `_sync` to method names:

```python
# Before
memory = SiteMemory()
profile = memory.get_profile(url)
memory.record_visit(url, 5.0)

# After
memory = SiteMemory()
profile = memory.get_profile_sync(url)
memory.record_visit_sync(url, 5.0)
```

That's it! No other changes needed.

## 3. Run the Example (2 minutes)

```bash
python site_memory_example.py
```

This shows:
- Basic async usage
- Concurrent access from 5 agents
- Backward compatibility

## 4. Test with Your Code (5 minutes)

### Async Version
```python
import asyncio
from site_memory import SiteMemory

async def test():
    memory = SiteMemory()
    await memory.initialize()

    # Record a visit
    await memory.record_visit("https://example.com", 5.0)

    # Cache a selector
    await memory.cache_selector(
        "https://example.com",
        "search_box",
        "input[name='q']"
    )

    # Get it back
    selector = await memory.get_selector("https://example.com", "search_box")
    print(f"Cached selector: {selector.primary}")

    # Get LLM context
    context = await memory.get_context_for_prompt("https://example.com")
    print(context)

asyncio.run(test())
```

### Sync Version
```python
from site_memory import SiteMemory

memory = SiteMemory()

# Record a visit
memory.record_visit_sync("https://example.com", 5.0)

# Cache a selector
memory.cache_selector_sync(
    "https://example.com",
    "search_box",
    "input[name='q']"
)

# Get it back
selector = memory.get_selector_sync("https://example.com", "search_box")
print(f"Cached selector: {selector.primary}")

# Get LLM context
context = memory.get_context_for_prompt_sync("https://example.com")
print(context)
```

## 5. Concurrent Usage (5 minutes)

Run multiple agents in parallel:

```python
import asyncio
from site_memory import SiteMemory

async def agent_task(agent_id, memory):
    url = f"https://example.com/page{agent_id}"

    # Each agent works independently
    await memory.record_visit(url, 5.0)
    await memory.cache_selector(url, "button", f"#btn-{agent_id}")

    # Read operations happen in parallel
    profile = await memory.get_profile(url)
    print(f"Agent {agent_id}: {profile.domain}")

async def run_agents():
    memory = SiteMemory()
    await memory.initialize()

    # Run 10 agents concurrently
    tasks = [agent_task(i, memory) for i in range(10)]
    await asyncio.gather(*tasks)

    await memory.flush()

asyncio.run(run_agents())
```

## 6. Configuration (Optional)

Tune for your use case:

```python
# Single agent (no cache refresh)
memory = SiteMemory(cache_ttl=0)

# High-read system (long cache)
memory = SiteMemory(cache_ttl=300)

# High-write system (short cache)
memory = SiteMemory(cache_ttl=10)

# Custom timeout
memory = SiteMemory(lock_timeout=30)
```

## Common Method Mapping

| Old Method | New Async Method | Sync Compatible Method |
|------------|------------------|------------------------|
| `get_profile()` | `await get_profile()` | `get_profile_sync()` |
| `get_or_create_profile()` | `await get_or_create_profile()` | `get_or_create_profile_sync()` |
| `record_visit()` | `await record_visit()` | `record_visit_sync()` |
| `cache_selector()` | `await cache_selector()` | `cache_selector_sync()` |
| `get_selector()` | `await get_selector()` | `get_selector_sync()` |
| `record_quirk()` | `await record_quirk()` | `record_quirk_sync()` |
| `get_quirks()` | `await get_quirks()` | `get_quirks_sync()` |
| `cache_action_pattern()` | `await cache_action_pattern()` | `cache_action_pattern_sync()` |
| `get_action_pattern()` | `await get_action_pattern()` | `get_action_pattern_sync()` |
| `get_context_for_prompt()` | `await get_context_for_prompt()` | `get_context_for_prompt_sync()` |

## Troubleshooting

### "No module named 'aiofiles'"
```bash
pip install aiofiles
```

### "Failed to acquire lock" TimeoutError
```python
# Increase timeout
memory = SiteMemory(lock_timeout=30)

# Or check for stuck processes
rm ~/.eversale/site_memory.json.lock
```

### Data not saving
```python
# Force save before exit
await memory.flush()
```

## Next Steps

1. Read `SITE_MEMORY_ASYNC_README.md` for detailed docs
2. Check `MIGRATION_CHECKLIST.md` for migration guide
3. Review `ARCHITECTURE_DIAGRAM.txt` for internals
4. See `CHANGES_SUMMARY.md` for what changed

## Need Help?

Run the example to see it working:
```bash
python site_memory_example.py
```

All features demonstrated with clear output.

