# DOMFirstBrowser Quick Reference

## Import & Setup

```python
from dom_first_browser import DOMFirstBrowser, create_browser

# Context manager (recommended)
async with DOMFirstBrowser(headless=False, slow_mo=500) as browser:
    # ... use browser ...

# Or manual
browser = await create_browser(headless=True)
# ... use browser ...
await browser.close()
```

## Navigation

```python
# Navigate to URL
await browser.navigate("https://example.com")

# With custom wait
await browser.navigate("https://example.com", wait_until="networkidle")
```

## Snapshots

```python
# Get snapshot
snapshot = await browser.snapshot()

# Force fresh snapshot (bypass cache)
snapshot = await browser.snapshot(force=True)

# Access snapshot data
snapshot.url        # "https://example.com"
snapshot.title      # "Example Domain"
snapshot.nodes      # [{"ref": "e1", "role": "button", ...}, ...]
snapshot.refs       # {"e1": {"role": "button", ...}, ...}
snapshot.timestamp  # 1234567890.123
```

## Finding Elements

```python
snapshot = await browser.snapshot()

# By role
buttons = [n for n in snapshot.nodes if n['role'] == 'button']

# By name (partial match)
search = [n for n in snapshot.nodes if 'search' in n['name'].lower()]

# By ref
element = snapshot.refs.get('e5')

# First match
first_link = next((n for n in snapshot.nodes if n['role'] == 'link'), None)
```

## Actions

```python
# Click element
success = await browser.click("e3")

# Type text
success = await browser.type("e5", "hello world")

# Type without clearing
success = await browser.type("e5", " more text", clear=False)
```

## JavaScript

```python
# Simple return
title = await browser.run_code("return document.title")

# Arrow function
url = await browser.run_code("() => window.location.href")

# Complex data
data = await browser.run_code("""
    return {
        title: document.title,
        links: Array.from(document.querySelectorAll('a')).length,
        cookies: document.cookie.split(';').length
    }
""")
```

## Observation

```python
# Console messages
obs = await browser.observe(console=True)
for msg in obs.console_messages:
    print(f"[{msg['type']}] {msg['text']}")

# Network requests
obs = await browser.observe(network=True)
for req in obs.network_requests:
    print(f"{req['method']} {req['url']}")

# Both
obs = await browser.observe(network=True, console=True)
```

## Metrics

```python
metrics = browser.get_metrics()

metrics['snapshots_taken']         # 10
metrics['snapshot_cache_hits']     # 7
metrics['cache_hit_rate']          # 70.0
metrics['actions_executed']        # 15
metrics['action_failures']         # 1
metrics['action_success_rate']     # 93.8
metrics['dom_mutations_detected']  # 3
```

## Advanced: Direct Page Access

```python
# Access Playwright page for advanced features
page = browser.page

# Set headers
await page.set_extra_http_headers({"X-Custom": "value"})

# Route requests
await page.route("**/*.png", lambda route: route.abort())

# Evaluate
result = await page.evaluate("() => document.body.innerHTML")
```

## Common Patterns

### LLM-Driven Workflow

```python
async with DOMFirstBrowser() as browser:
    await browser.navigate("https://example.com")

    # Get snapshot for LLM
    snapshot = await browser.snapshot()

    # Format for LLM
    elements = "\n".join([
        f"[{n['ref']}] {n['role']} \"{n['name']}\""
        for n in snapshot.nodes[:20]
    ])

    prompt = f"Elements:\n{elements}\n\nTask: Click submit button"

    # LLM responds: {"action": "click", "ref": "e3"}
    # Execute
    await browser.click("e3")
```

### Form Filling

```python
async with DOMFirstBrowser() as browser:
    await browser.navigate("https://example.com/form")

    snapshot = await browser.snapshot()

    # Fill fields
    for node in snapshot.nodes:
        if node['role'] == 'textbox':
            if 'email' in node['name'].lower():
                await browser.type(node['ref'], "user@example.com")
            elif 'password' in node['name'].lower():
                await browser.type(node['ref'], "secret123")

    # Submit
    submit = next((n for n in snapshot.nodes
                   if n['role'] == 'button' and 'submit' in n['name'].lower()),
                  None)
    if submit:
        await browser.click(submit['ref'])
```

### Data Extraction

```python
async with DOMFirstBrowser() as browser:
    await browser.navigate("https://news.ycombinator.com")

    data = await browser.run_code("""
        return {
            title: document.title,
            stories: Array.from(document.querySelectorAll('.titleline > a'))
                .slice(0, 10)
                .map(a => ({
                    title: a.textContent,
                    url: a.href
                }))
        }
    """)

    for story in data['stories']:
        print(f"{story['title']}: {story['url']}")
```

### Error Handling

```python
async with DOMFirstBrowser() as browser:
    await browser.navigate("https://example.com")

    snapshot = await browser.snapshot()

    # Try action with fallback
    success = await browser.click("e99")

    if not success:
        # Fallback: find first button
        button = next((n for n in snapshot.nodes if n['role'] == 'button'), None)
        if button:
            await browser.click(button['ref'])
```

### Monitoring & Debugging

```python
async with DOMFirstBrowser(headless=False, slow_mo=500) as browser:
    await browser.navigate("https://example.com")

    # Take actions
    snapshot = await browser.snapshot()
    await browser.click(snapshot.nodes[0]['ref'])

    # Check what happened
    obs = await browser.observe(network=True, console=True)

    print("Console:")
    for msg in obs.console_messages[-5:]:  # Last 5
        print(f"  {msg['type']}: {msg['text']}")

    print("Network:")
    for req in obs.network_requests[-5:]:  # Last 5
        print(f"  {req['method']} {req['url']}")

    # Performance
    metrics = browser.get_metrics()
    print(f"Cache hit rate: {metrics['cache_hit_rate']:.1f}%")
```

## Return Types

| Method | Returns | On Error |
|--------|---------|----------|
| `navigate()` | `bool` | `False` |
| `snapshot()` | `SnapshotResult` | Raises |
| `click()` | `bool` | `False` |
| `type()` | `bool` | `False` |
| `run_code()` | `Any` (JSON) | `None` |
| `observe()` | `ObserveResult` | Empty lists |
| `get_metrics()` | `dict` | Never fails |

## Constructor Options

```python
DOMFirstBrowser(
    headless: bool = True,         # Headless mode
    slow_mo: int = 0,              # Slow down actions (ms)
    viewport: tuple = (1280, 720), # Browser window size
    user_agent: Optional[str] = None # Custom user agent
)
```

## Tips

1. **Use context manager** - Ensures cleanup
2. **Check return values** - `False` means action failed
3. **Force refresh when needed** - After major DOM changes
4. **Limit snapshot elements** - First 20-50 for LLM prompts
5. **Monitor metrics** - Track cache hit rate
6. **Handle None returns** - JavaScript can fail
7. **Use observation** - Debug network/console issues

## File Locations

```
/mnt/c/ev29/cli/engine/agent/
  dom_first_browser.py              - Main implementation
  test_dom_first_browser.py         - Test suite
  dom_first_integration_example.py  - Integration examples
  DOM_FIRST_BROWSER_README.md       - Full documentation
  DOM_FIRST_BROWSER_SUMMARY.md      - Implementation summary
  DOM_FIRST_BROWSER_QUICKREF.md     - This file
```
