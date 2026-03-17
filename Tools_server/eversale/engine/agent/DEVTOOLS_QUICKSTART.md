# DevToolsHooks Quick Start Guide

## 30-Second Start

```python
from devtools_hooks import DevToolsHooks

# Create and start
devtools = DevToolsHooks(page)
await devtools.start_capture(network=True, console=True)

# Run automation
await page.goto("https://example.com")

# Get summary
summary = devtools.summary()
print(f"Requests: {summary['network']['total_requests']}")
print(f"Errors: {summary['console']['errors']}")

# Cleanup
await devtools.cleanup()
```

## 5-Minute Tutorial

### Step 1: Import

```python
from devtools_hooks import DevToolsHooks, quick_devtools_summary
```

### Step 2: Create Instance

```python
# Basic (default settings)
devtools = DevToolsHooks(page)

# Memory-efficient (for long sessions)
devtools = DevToolsHooks(
    page,
    max_network_entries=100,
    max_console_entries=50,
    capture_response_bodies=False
)
```

### Step 3: Start Capture

```python
# Capture everything
await devtools.start_capture(network=True, console=True)

# Network only
await devtools.start_capture(network=True, console=False)

# Console only
await devtools.start_capture(network=False, console=True)
```

### Step 4: Run Automation

```python
# Your normal automation code
await page.goto("https://example.com")
await page.click("button")
await page.fill("input", "test")
```

### Step 5: Check for Issues

```python
# Quick summary
summary = devtools.summary()
print(f"Total requests: {summary['network']['total_requests']}")
print(f"Failed requests: {summary['network']['failed_requests']}")
print(f"Console errors: {summary['console']['errors']}")

# Detailed checks
if summary['network']['failed_requests'] > 0:
    failed = devtools.get_failed_requests()
    for req in failed:
        print(f"Failed: {req['url']} - {req['failure_reason']}")

if summary['console']['errors'] > 0:
    errors = devtools.get_console_log(level="error")
    for err in errors:
        print(f"Error: {err['text']}")
```

### Step 6: Cleanup

```python
await devtools.cleanup()
```

## Common Use Cases

### Use Case 1: Detect Errors During Automation

```python
devtools = DevToolsHooks(page)
await devtools.start_capture(network=True, console=True)

try:
    await page.goto("https://example.com")
    await page.click("button")
except Exception as e:
    # Diagnose with DevTools
    print(f"Failed: {e}")
    print(f"Failed requests: {len(devtools.get_failed_requests())}")
    print(f"Console errors: {len(devtools.get_console_log(level='error'))}")
finally:
    await devtools.cleanup()
```

### Use Case 2: Performance Testing

```python
devtools = DevToolsHooks(page)
await devtools.start_capture(network=True, console=False)

await page.goto("https://example.com")

# Find slow requests
slow = devtools.get_slow_requests(threshold_ms=1000)
print(f"Slow requests: {len(slow)}")
for req in slow:
    print(f"  {req['duration_ms']}ms - {req['url']}")

await devtools.cleanup()
```

### Use Case 3: Monitor Multiple Pages

```python
devtools = DevToolsHooks(page)
await devtools.start_capture(network=True, console=True)

for url in ["https://example.com", "https://github.com"]:
    devtools.clear()  # Clear before each page
    await page.goto(url)

    summary = devtools.summary()
    print(f"{url}: {summary['network']['total_requests']} requests")

await devtools.cleanup()
```

### Use Case 4: Quick Check (One-Liner)

```python
# Quick 5-second capture
summary = await quick_devtools_summary(page, duration_seconds=5)
print(f"Errors: {summary['console']['errors']}")
```

## Key Methods Cheat Sheet

| Method | Purpose | Example |
|--------|---------|---------|
| `start_capture(network, console)` | Start monitoring | `await devtools.start_capture(True, True)` |
| `stop_capture()` | Stop monitoring | `await devtools.stop_capture()` |
| `cleanup()` | Stop and clear | `await devtools.cleanup()` |
| `clear()` | Clear data only | `devtools.clear()` |
| `summary()` | Get overview | `summary = devtools.summary()` |
| `get_network_log()` | Get all requests | `logs = devtools.get_network_log()` |
| `get_failed_requests()` | Get failures | `failed = devtools.get_failed_requests()` |
| `get_slow_requests(ms)` | Get slow requests | `slow = devtools.get_slow_requests(1000)` |
| `get_status_code_errors()` | Get 4xx/5xx | `errors = devtools.get_status_code_errors()` |
| `get_blocked_resources()` | Get blocked | `blocked = devtools.get_blocked_resources()` |
| `get_console_log(level)` | Get console logs | `logs = devtools.get_console_log("error")` |
| `get_errors()` | Get page errors | `errors = devtools.get_errors()` |

## Filtering Cheat Sheet

### Network Filtering

```python
# By resource type
xhr = devtools.get_network_log(filter_type="xhr")
images = devtools.get_network_log(filter_type="image")
docs = devtools.get_network_log(filter_type="document")

# By status code
success = devtools.get_network_log(filter_status="2xx")
redirects = devtools.get_network_log(filter_status="3xx")
client_errors = devtools.get_network_log(filter_status="4xx")
server_errors = devtools.get_network_log(filter_status="5xx")
failures = devtools.get_network_log(filter_status="failed")

# Combined
failed_xhr = devtools.get_network_log(
    filter_type="xhr",
    filter_status="failed"
)
```

### Console Filtering

```python
# By level (each includes more severe levels)
errors_only = devtools.get_console_log(level="error")
errors_and_warnings = devtools.get_console_log(level="warning")
all_important = devtools.get_console_log(level="info")
everything = devtools.get_console_log(level="debug")
```

## Summary Output Format

```python
{
    "capture_duration_seconds": 30,
    "network": {
        "total_requests": 150,
        "failed_requests": 2,
        "status_4xx": 3,
        "status_5xx": 1,
        "average_duration_ms": 250,
        "resource_types": {
            "xhr": 45,
            "fetch": 20,
            "document": 5,
            "image": 50
        }
    },
    "console": {
        "total_messages": 25,
        "errors": 2,
        "warnings": 5
    },
    "errors": {
        "page_errors": 1
    },
    "capturing": {
        "network": True,
        "console": True
    }
}
```

## Configuration Guide

### Default (Balanced)
```python
DevToolsHooks(
    page,
    max_network_entries=500,
    max_console_entries=200,
    max_error_entries=100,
    capture_response_bodies=False
)
```
Memory: 1-2 MB | Use: Short sessions (<5 min)

### Memory-Efficient (Long Sessions)
```python
DevToolsHooks(
    page,
    max_network_entries=100,
    max_console_entries=50,
    max_error_entries=25,
    capture_response_bodies=False
)
```
Memory: 200-500 KB | Use: Long sessions (>30 min)

### Performance Testing
```python
DevToolsHooks(
    page,
    max_network_entries=1000,
    max_console_entries=100,
    max_error_entries=50,
    capture_response_bodies=False
)
```
Memory: 2-5 MB | Use: Detailed analysis

## Troubleshooting

### No data captured?
Make sure you called `start_capture()`:
```python
await devtools.start_capture(network=True, console=True)
```

### Missing recent entries?
Buffer full. Increase size or clear periodically:
```python
devtools = DevToolsHooks(page, max_network_entries=1000)
# or
devtools.clear()  # Clear periodically
```

### Memory growing?
Reduce buffer sizes:
```python
devtools = DevToolsHooks(page, max_network_entries=100)
```

## Best Practices

1. **Always cleanup**: Use try/finally
   ```python
   devtools = DevToolsHooks(page)
   try:
       await devtools.start_capture(network=True, console=True)
       # ... automation ...
   finally:
       await devtools.cleanup()
   ```

2. **Choose right buffer size**: Match your use case
   - Short sessions: Default (500/200/100)
   - Long sessions: Small (100/50/25)
   - Analysis: Large (1000/100/50)

3. **Clear between operations**: For continuous monitoring
   ```python
   for url in urls:
       devtools.clear()
       await page.goto(url)
       # ... check summary ...
   ```

4. **Don't capture response bodies**: Unless needed (memory intensive)
   ```python
   devtools = DevToolsHooks(page, capture_response_bodies=False)
   ```

5. **Use quick_devtools_summary**: For spot checks
   ```python
   summary = await quick_devtools_summary(page, duration_seconds=5)
   ```

## Next Steps

- Read full API docs: `DEVTOOLS_HOOKS_README.md`
- See examples: `devtools_hooks_example.py`
- Integration guide: `devtools_integration_example.py`
- Run tests: `pytest test_devtools_hooks.py -v`

## Getting Help

1. Check `DEVTOOLS_HOOKS_README.md` for full documentation
2. See `devtools_hooks_example.py` for working examples
3. Review `test_devtools_hooks.py` for detailed usage patterns
4. Check troubleshooting section in README
