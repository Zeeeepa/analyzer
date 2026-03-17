# A11y Browser - Quick Start Guide

## Installation

The a11y system is built-in to the Eversale CLI. No additional installation needed.

## 30-Second Example

```python
from engine.agent import A11yBrowser

async with A11yBrowser() as browser:
    # Navigate
    await browser.navigate("https://google.com")

    # Get snapshot (shows all interactive elements with refs)
    snapshot = await browser.snapshot()

    # Find search box
    search = snapshot.find_by_role("searchbox")[0]

    # Type and submit
    await browser.type(search.ref, "AI news")
    await browser.press("Enter")
```

## Core Concepts

### 1. Snapshots
A snapshot shows all interactive elements on the page with stable refs:

```python
snapshot = await browser.snapshot()

# Each element has:
# - ref: Stable identifier (e.g., "e38")
# - role: Semantic role (e.g., "button", "textbox")
# - name: Human-readable name
# - value: Current value (for inputs)

for element in snapshot.elements:
    print(element)
    # Output: [e38] searchbox "Search"
```

### 2. Element Refs
Refs are stable identifiers that don't change:

```python
# Find element by role
buttons = snapshot.find_by_role("button")

# Find element by name
login = snapshot.find_by_name("login", partial=True)

# Use ref to interact
await browser.click(login[0].ref)
```

### 3. Actions
All actions use refs from the snapshot:

```python
# Click
await browser.click("e38")

# Type
await browser.type("e12", "hello world")

# Press key
await browser.press("Enter")

# Scroll
await browser.scroll("down")

# Hover
await browser.hover("e5")
```

## Common Patterns

### Pattern 1: Navigate and Search
```python
async with A11yBrowser() as browser:
    await browser.navigate("https://google.com")
    snapshot = await browser.snapshot()

    # Find and use search box
    search = snapshot.find_by_role("searchbox")[0]
    await browser.type(search.ref, "Python tutorials")
    await browser.press("Enter")
```

### Pattern 2: Find and Click Button
```python
snapshot = await browser.snapshot()

# Find button by name
buttons = snapshot.find_by_name("submit")
if buttons:
    await browser.click(buttons[0].ref)
```

### Pattern 3: Fill Form
```python
snapshot = await browser.snapshot()

# Find inputs by role
inputs = snapshot.find_by_role("textbox")

# Type into specific inputs by name
for input_el in inputs:
    if "email" in input_el.name.lower():
        await browser.type(input_el.ref, "user@example.com")
    elif "password" in input_el.name.lower():
        await browser.type(input_el.ref, "secret123")

# Submit
submit = snapshot.find_by_name("submit")[0]
await browser.click(submit.ref)
```

### Pattern 4: Check Result
```python
# Wait for page to load
await browser.wait(2)

# Get new snapshot
snapshot = await browser.snapshot()

# Check if we're on the right page
print(f"Current URL: {snapshot.url}")
print(f"Page title: {snapshot.title}")
```

## Configuration

### Enable Debug Logging
```python
from engine.agent import a11y_config

a11y_config.LOG_ACTIONS = True
a11y_config.LOG_SNAPSHOTS = True
a11y_config.LOG_ERRORS = True
```

### Adjust Performance
```python
# Faster snapshots (more caching)
a11y_config.SNAPSHOT_CACHE_TTL = 5.0

# More retries (more reliable)
a11y_config.MAX_RETRIES = 3

# Longer timeouts (slower sites)
a11y_config.DEFAULT_TIMEOUT = 10000  # 10 seconds
```

### Production Settings
```python
# Recommended for production
a11y_config.ENABLE_SNAPSHOT_CACHE = True
a11y_config.ENABLE_AUTO_RETRY = True
a11y_config.LOG_ACTIONS = True
a11y_config.LOG_SNAPSHOTS = False  # Too verbose
a11y_config.LOG_ERRORS = True
```

## Using with SimpleAgent

The SimpleAgent uses A11yBrowser automatically:

```python
from engine.agent import SimpleAgent

# Create agent (no LLM = uses fallback logic)
agent = SimpleAgent()

# Run task
result = await agent.run("Search Google for AI news")

print(f"Success: {result.success}")
print(f"Steps: {result.steps_taken}")
print(f"Final URL: {result.final_url}")

# Check metrics
print(f"Cache hits: {result.metrics['cache_hits']}")
print(f"Retries: {result.metrics['retries']}")
print(f"Total time: {result.metrics['total_time']:.2f}s")
```

## With LLM Integration

```python
from engine.agent import SimpleAgent

# Inject your LLM client
agent = SimpleAgent(llm_client=my_llm_client)

# LLM will see snapshot and decide actions
result = await agent.run("Find the cheapest flight to NYC")
```

## Error Handling

```python
# Actions return ActionResult with success/error
result = await browser.click("e999")  # Non-existent ref

if not result.success:
    print(f"Action failed: {result.error}")
    # Error: Element ref 'e999' not found. Get a new snapshot.

# Retries happen automatically (configurable)
a11y_config.ENABLE_AUTO_RETRY = True
a11y_config.MAX_RETRIES = 2
```

## Performance Monitoring

```python
# Get metrics from browser
metrics = browser.get_metrics()

print(f"Snapshots taken: {metrics['snapshots_taken']}")
print(f"Cache hit rate: {metrics['cache_hit_rate']:.1f}%")
print(f"Actions executed: {metrics['actions_executed']}")
print(f"Action failures: {metrics['action_failures']}")
print(f"Avg action time: {metrics['avg_action_time']:.3f}s")

# Reset metrics
browser.reset_metrics()

# Clear cache
browser.clear_cache()
```

## Advanced Features

### Force New Snapshot
```python
# Bypass cache and get fresh snapshot
snapshot = await browser.snapshot(force=True)
```

### Custom Timeouts
```python
# Per-action timeout (in milliseconds)
await browser.click("e38", timeout=10000)  # 10 second timeout
await browser.type("e12", "text", timeout=5000)  # 5 second timeout
```

### JavaScript Evaluation
```python
# Execute JavaScript
result = await browser.evaluate("document.title")
print(result.data["result"])
```

### Screenshots
```python
# Take screenshot
await browser.screenshot("page.png")

# Full page screenshot
await browser.screenshot("full.png", full_page=True)
```

### Navigation
```python
# Go back
await browser.go_back()

# Go forward
await browser.go_forward()

# Refresh
await browser.refresh()
```

## Troubleshooting

### "Element ref not found"
- The page changed after the snapshot
- Solution: Get a new snapshot

```python
snapshot = await browser.snapshot()
# ... page changes ...
snapshot = await browser.snapshot()  # Refresh
```

### Slow Snapshots
- Check `LOG_METRICS` to see timing
- Increase cache TTL: `a11y_config.SNAPSHOT_CACHE_TTL = 5.0`
- Enable parallel resolution: `a11y_config.PARALLEL_ELEMENT_RESOLUTION = True`

### Actions Failing
- Check `LOG_ERRORS` for details
- Increase timeout: `a11y_config.DEFAULT_TIMEOUT = 10000`
- Add more retries: `a11y_config.MAX_RETRIES = 3`
- Add delay before action: `await browser.wait(1)`

### Too Many Elements
- Limit shown: `a11y_config.MAX_ELEMENTS_PER_SNAPSHOT = 50`
- Filter by role: `snapshot.find_by_role("button")`
- Filter by name: `snapshot.find_by_name("submit")`

## Best Practices

1. **Always get fresh snapshot after navigation**
   ```python
   await browser.navigate("https://example.com")
   snapshot = await browser.snapshot()  # Get snapshot AFTER navigation
   ```

2. **Use semantic search**
   ```python
   # Good: Use role-based search
   buttons = snapshot.find_by_role("button")

   # Better: Combine role and name
   submit = snapshot.find_by_role("button")
   submit = [b for b in buttons if "submit" in b.name.lower()]
   ```

3. **Handle missing elements gracefully**
   ```python
   buttons = snapshot.find_by_name("submit")
   if buttons:
       await browser.click(buttons[0].ref)
   else:
       print("Submit button not found")
   ```

4. **Wait after actions that change the page**
   ```python
   await browser.click(submit_button.ref)
   await browser.wait(2)  # Let page load
   snapshot = await browser.snapshot()  # Fresh snapshot
   ```

5. **Use metrics to optimize**
   ```python
   metrics = browser.get_metrics()
   if metrics['cache_hit_rate'] < 50:
       # Increase cache TTL
       a11y_config.SNAPSHOT_CACHE_TTL = 5.0
   ```

## Complete Example

```python
from engine.agent import A11yBrowser, a11y_config

# Configure
a11y_config.LOG_ACTIONS = True
a11y_config.ENABLE_AUTO_RETRY = True

async def search_and_click():
    async with A11yBrowser(headless=False) as browser:
        # Navigate
        print("Navigating to Google...")
        await browser.navigate("https://google.com")

        # Get snapshot
        snapshot = await browser.snapshot()
        print(f"Found {len(snapshot.elements)} elements")

        # Find search box
        search = snapshot.find_by_role("searchbox")
        if not search:
            print("Search box not found!")
            return

        # Type query
        print(f"Typing into: {search[0]}")
        await browser.type(search[0].ref, "Python tutorials")

        # Submit
        print("Pressing Enter...")
        await browser.press("Enter")

        # Wait for results
        await browser.wait(2)

        # Get new snapshot
        snapshot = await browser.snapshot()
        print(f"Results page: {snapshot.title}")

        # Show metrics
        metrics = browser.get_metrics()
        print(f"\nMetrics:")
        print(f"  Cache hit rate: {metrics['cache_hit_rate']:.1f}%")
        print(f"  Actions executed: {metrics['actions_executed']}")
        print(f"  Avg action time: {metrics['avg_action_time']:.3f}s")

# Run it
await search_and_click()
```

## Next Steps

- Read `A11Y_OPTIMIZATION_SUMMARY.md` for advanced features
- See `test_a11y_optimized.py` for test examples
- Check `a11y_config.py` for all configuration options
