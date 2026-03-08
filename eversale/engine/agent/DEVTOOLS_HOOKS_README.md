# DevToolsHooks - Production-Ready DevTools Inspection

Comprehensive DevTools inspection capabilities for Playwright pages with memory-efficient logging, flexible filtering, and production-ready error handling.

## Features

- Network request/response capture with timing
- Console log capture (all levels: error, warning, info, log, debug)
- Page error and exception tracking
- Resource loading failure detection
- Memory-efficient circular buffers
- Flexible filtering by type, status, level
- Quick summary for debugging
- Production-ready cleanup and error handling

## Quick Start

```python
from devtools_hooks import DevToolsHooks, quick_devtools_summary

# Basic usage
devtools = DevToolsHooks(page)
await devtools.start_capture(network=True, console=True)

# Run your automation
await page.goto("https://example.com")
await page.click("button")

# Get diagnostics
summary = devtools.summary()
errors = devtools.get_errors()
failed_requests = devtools.get_failed_requests()

await devtools.stop_capture()
```

## Installation

No additional dependencies required. Uses standard Playwright API.

Compatible with:
- `playwright`
- `patchright` (anti-bot)
- `rebrowser-playwright` (anti-bot)

## API Reference

### DevToolsHooks Class

#### Initialization

```python
DevToolsHooks(
    page: Page,
    max_network_entries: int = 500,
    max_console_entries: int = 200,
    max_error_entries: int = 100,
    capture_response_bodies: bool = False
)
```

**Parameters:**
- `page`: Playwright page instance
- `max_network_entries`: Max network requests to store (circular buffer)
- `max_console_entries`: Max console logs to store (circular buffer)
- `max_error_entries`: Max errors to store (circular buffer)
- `capture_response_bodies`: Whether to capture response bodies (memory intensive)

**Memory Usage:**
- Default config: ~1-2 MB for typical session
- With response bodies: ~10-50 MB (depends on content)

#### Core Methods

##### start_capture()

```python
await devtools.start_capture(network=True, console=True)
```

Start capturing DevTools events.

**Parameters:**
- `network`: Capture network requests/responses
- `console`: Capture console logs and page errors

##### stop_capture()

```python
await devtools.stop_capture()
```

Stop capturing and remove event handlers.

##### cleanup()

```python
await devtools.cleanup()
```

Full cleanup - stops capture and clears all data.

#### Network Methods

##### get_network_log()

```python
devtools.get_network_log(
    filter_type: Optional[str] = None,
    filter_status: Optional[str] = None
) -> List[Dict[str, Any]]
```

Get network log with optional filtering.

**Parameters:**
- `filter_type`: Filter by resource type (xhr, fetch, document, image, stylesheet, script, etc.)
- `filter_status`: Filter by status code pattern (2xx, 3xx, 4xx, 5xx, failed)

**Returns:** List of network log entries

**Entry Format:**
```python
{
    "timestamp": "2024-01-15T10:30:00.123",
    "url": "https://example.com/api/data",
    "method": "GET",
    "resource_type": "xhr",
    "status_code": 200,
    "status_text": "OK",
    "duration_ms": 150,
    "headers": {"content-type": "application/json"},
    "failed": False,
    # If failed:
    "failure_reason": "net::ERR_CONNECTION_REFUSED"
}
```

##### get_failed_requests()

```python
devtools.get_failed_requests() -> List[Dict[str, Any]]
```

Get all failed network requests.

##### get_status_code_errors()

```python
devtools.get_status_code_errors() -> List[Dict[str, Any]]
```

Get requests with 4xx or 5xx status codes.

##### get_slow_requests()

```python
devtools.get_slow_requests(threshold_ms: int = 3000) -> List[Dict[str, Any]]
```

Get requests that took longer than threshold (sorted by duration, slowest first).

##### get_blocked_resources()

```python
devtools.get_blocked_resources() -> List[Dict[str, Any]]
```

Get resources blocked by CORS, CSP, mixed content, etc.

#### Console Methods

##### get_console_log()

```python
devtools.get_console_log(
    level: Optional[Literal["error", "warning", "info", "log", "debug"]] = None
) -> List[Dict[str, Any]]
```

Get console log with optional level filtering.

**Parameters:**
- `level`: Filter by console level (each level includes more severe levels)
  - `error`: Only errors
  - `warning`: Errors + warnings
  - `info`: Errors + warnings + info
  - `log`: Errors + warnings + info + logs
  - `debug`: All messages

**Returns:** List of console log entries

**Entry Format:**
```python
{
    "timestamp": "2024-01-15T10:30:00.123",
    "level": "error",
    "text": "Uncaught TypeError: Cannot read property 'x' of undefined",
    "location": {"url": "...", "lineNumber": 42},
    "args": []
}
```

##### get_errors()

```python
devtools.get_errors() -> List[Dict[str, Any]]
```

Get all captured page errors (uncaught exceptions).

**Entry Format:**
```python
{
    "timestamp": "2024-01-15T10:30:00.123",
    "type": "pageerror",
    "message": "TypeError: Cannot read property 'x' of undefined",
    "stack": "..."
}
```

#### Summary Method

##### summary()

```python
devtools.summary() -> Dict[str, Any]
```

Get quick overview of captured data.

**Returns:**
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
            "image": 50,
            "stylesheet": 15,
            "script": 15
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

#### Utility Methods

##### clear()

```python
devtools.clear()
```

Clear all captured data without stopping capture.

### Quick Summary Function

```python
await quick_devtools_summary(page: Page, duration_seconds: int = 5) -> Dict[str, Any]
```

Convenience function for quick DevTools capture and summary.

**Example:**
```python
summary = await quick_devtools_summary(page, duration_seconds=10)
print(f"Errors: {summary['console']['errors']}")
print(f"Failed requests: {summary['network']['failed_requests']}")
```

## Usage Examples

### Basic Error Detection

```python
devtools = DevToolsHooks(page)
await devtools.start_capture(network=True, console=True)

await page.goto("https://example.com")

# Check for errors
errors = devtools.get_errors()
console_errors = devtools.get_console_log(level="error")
failed_requests = devtools.get_failed_requests()

if errors or console_errors or failed_requests:
    print("Issues detected!")
    for error in errors:
        print(f"  Page error: {error['message']}")

await devtools.cleanup()
```

### Network Performance Analysis

```python
devtools = DevToolsHooks(page)
await devtools.start_capture(network=True, console=False)

await page.goto("https://example.com")

# Find slow requests
slow_requests = devtools.get_slow_requests(threshold_ms=1000)
print(f"Slow requests (>1s): {len(slow_requests)}")
for req in slow_requests[:5]:
    print(f"  {req['duration_ms']}ms - {req['url']}")

# Check for HTTP errors
http_errors = devtools.get_status_code_errors()
print(f"\nHTTP errors: {len(http_errors)}")
for req in http_errors:
    print(f"  {req['status_code']} - {req['url']}")

await devtools.cleanup()
```

### Debugging Automation Failures

```python
devtools = DevToolsHooks(page)
await devtools.start_capture(network=True, console=True)

try:
    await page.goto("https://example.com")
    await page.click("button")  # Might fail
except Exception as e:
    print(f"\nAutomation failed: {e}")
    print("\nDiagnostics:")

    # Check for JavaScript errors
    errors = devtools.get_errors()
    if errors:
        print(f"  JavaScript errors: {len(errors)}")
        for err in errors:
            print(f"    - {err['message']}")

    # Check for failed API calls
    failed = devtools.get_failed_requests()
    if failed:
        print(f"  Failed requests: {len(failed)}")
        for req in failed[:5]:
            print(f"    - {req['url']}")

    # Check for console errors
    console_errors = devtools.get_console_log(level="error")
    if console_errors:
        print(f"  Console errors: {len(console_errors)}")
        for log in console_errors[:5]:
            print(f"    - {log['text']}")

finally:
    await devtools.cleanup()
```

### Memory-Efficient Long-Running Sessions

```python
# Configure with smaller buffers for long sessions
devtools = DevToolsHooks(
    page,
    max_network_entries=100,  # Keep last 100 requests only
    max_console_entries=50,   # Keep last 50 console logs only
    capture_response_bodies=False  # Don't capture bodies (saves memory)
)

await devtools.start_capture(network=True, console=True)

# Run long automation - logs automatically rotate
for i in range(100):
    await page.goto(f"https://example.com/page{i}")
    # Logs are automatically pruned to stay within limits

summary = devtools.summary()
print(f"Network log size: {summary['network']['total_requests']}")  # Max 100

await devtools.cleanup()
```

### Integration with Existing Code

```python
# Add DevTools to existing automation
async def my_automation(page):
    # Wrap existing code with DevTools
    devtools = DevToolsHooks(page)
    await devtools.start_capture(network=True, console=True)

    try:
        # Your existing automation code
        await page.goto("https://example.com")
        await page.fill("#username", "test")
        await page.click("#submit")

        # Check for issues
        summary = devtools.summary()
        if summary['network']['failed_requests'] > 0:
            print("Warning: Some requests failed")
        if summary['console']['errors'] > 0:
            print("Warning: JavaScript errors detected")

    finally:
        await devtools.cleanup()
```

## Performance Characteristics

### Memory Usage

| Configuration | Memory Usage (Typical) |
|---------------|----------------------|
| Default (500/200/100) | 1-2 MB |
| Small (100/50/25) | 200-500 KB |
| With response bodies | 10-50 MB |

### CPU Overhead

- Minimal: <1% CPU overhead in most cases
- Event handlers are lightweight
- No polling or timers

### Recommendations

**For short sessions (<5 minutes):**
- Use default settings
- Enable all capture types

**For long sessions (>30 minutes):**
- Reduce buffer sizes to 100/50/25
- Disable response body capture
- Consider clearing logs periodically

**For production monitoring:**
- Use `quick_devtools_summary()` for spot checks
- Only enable when debugging issues
- Clear logs after each critical section

## Thread Safety

DevToolsHooks is designed for single-threaded async usage. Do not share instances across multiple pages or threads.

## Cleanup Best Practices

Always clean up to prevent memory leaks:

```python
# Option 1: Explicit cleanup
devtools = DevToolsHooks(page)
try:
    await devtools.start_capture(network=True, console=True)
    # ... automation ...
finally:
    await devtools.cleanup()

# Option 2: Context manager (if implemented)
# async with DevToolsHooks(page) as devtools:
#     await devtools.start_capture(network=True, console=True)
#     # ... automation ...
```

## Troubleshooting

### Issue: No data captured

**Cause:** Forgot to call `start_capture()`

**Fix:**
```python
await devtools.start_capture(network=True, console=True)
```

### Issue: Memory keeps growing

**Cause:** Buffers too large or response bodies enabled

**Fix:**
```python
devtools = DevToolsHooks(
    page,
    max_network_entries=100,
    capture_response_bodies=False
)
```

### Issue: Missing recent entries

**Cause:** Circular buffer limit reached

**Fix:** Increase buffer size or clear periodically
```python
devtools = DevToolsHooks(page, max_network_entries=1000)
# Or clear periodically:
devtools.clear()
```

### Issue: Events not captured after page navigation

**Cause:** DevTools hooks survive navigation, but make sure you don't recreate the page

**Fix:** Keep using the same page and DevTools instance across navigations

## Integration with Other Tools

### Loguru Logging

```python
from loguru import logger

devtools = DevToolsHooks(page)
await devtools.start_capture(network=True, console=True)

# ... automation ...

# Log summary
summary = devtools.summary()
logger.info(f"DevTools summary: {summary}")

# Log errors
for error in devtools.get_errors():
    logger.error(f"Page error: {error['message']}")
```

### Metrics Collection

```python
import time

start_time = time.time()
devtools = DevToolsHooks(page)
await devtools.start_capture(network=True, console=True)

# ... automation ...

summary = devtools.summary()
metrics = {
    "duration_seconds": time.time() - start_time,
    "total_requests": summary['network']['total_requests'],
    "failed_requests": summary['network']['failed_requests'],
    "page_errors": summary['errors']['page_errors'],
    "console_errors": summary['console']['errors'],
}

# Send to your metrics service
# send_metrics(metrics)
```

## License

Same as parent project (Eversale CLI).

## Contributing

When contributing, ensure:
1. All tests pass: `pytest test_devtools_hooks.py -v`
2. No memory leaks in long-running tests
3. Event handlers are properly cleaned up
4. Documentation is updated

## Changelog

### v1.0.0 (2024-01-15)
- Initial release
- Network request/response capture
- Console log capture
- Page error tracking
- Circular buffer implementation
- Filtering capabilities
- Summary generation
- Production-ready cleanup
