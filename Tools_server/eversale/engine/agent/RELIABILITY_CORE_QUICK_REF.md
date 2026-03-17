# Reliability Core - Quick Reference

## Import

```python
from reliability_core import (
    ToolResult, BrowserHealthCheck, ReliableExecutor,
    InputValidator, TimeoutConfig,
    create_success_result, create_error_result, create_validation_error
)
```

## ToolResult

```python
# Create success result
result = create_success_result(data="result", duration_ms=100)

# Create error result
result = create_error_result("Error message", "ERROR_CODE")

# Manual creation
result = ToolResult(
    success=True,
    data={"key": "value"},
    error=None,
    error_code=None,
    duration_ms=123,
    retries_used=0
)

# Check result
if result.success:
    print(result.data)
else:
    print(f"{result.error} [{result.error_code}]")
```

## TimeoutConfig

```python
# Standard timeouts
TimeoutConfig.FAST = 2      # Quick operations
TimeoutConfig.NORMAL = 5    # Standard operations
TimeoutConfig.SLOW = 15     # Slow operations
TimeoutConfig.MAX = 30      # Maximum wait

# Convert to milliseconds
ms = TimeoutConfig.to_ms(TimeoutConfig.NORMAL)  # 5000ms
```

## BrowserHealthCheck

```python
health = BrowserHealthCheck()

# Check browser alive
if not await health.check_browser_alive(page):
    result = await health.recover_browser(page)

# Check page loaded
if await health.check_page_loaded(page):
    # Page ready

# Wait for ready
result = await health.wait_for_ready(page, timeout=TimeoutConfig.NORMAL)

# Check if unhealthy
if health.is_unhealthy:
    # Too many failures, restart browser
```

## ReliableExecutor

```python
executor = ReliableExecutor()

# Execute with retry
result = await executor.execute(
    operation=lambda: page.click("button"),
    timeout=TimeoutConfig.NORMAL,
    retries=2,
    backoff=True
)

# Get statistics
stats = executor.get_stats()
print(f"Success rate: {stats['success_rate_pct']}%")

# Reset stats
executor.reset_stats()
```

## InputValidator

```python
validator = InputValidator()

# Validate URL
is_valid, error = validator.validate_url("https://example.com")
if not is_valid:
    return create_validation_error("url", error)

# Validate selector
is_valid, error = validator.validate_selector("button.primary")
if not is_valid:
    return create_validation_error("selector", error)

# Validate ref
is_valid, error = validator.validate_ref("element-123")
if not is_valid:
    return create_validation_error("ref", error)

# Validate timeout
is_valid, error = validator.validate_timeout(5.0)
if not is_valid:
    return create_validation_error("timeout", error)

# Validate text input
is_valid, error = validator.validate_text_input("Hello", max_length=1000)
```

## Common Patterns

### Pattern: Tool Wrapper

```python
async def my_tool(page, selector: str) -> ToolResult:
    start_time = time.time()
    validator = InputValidator()

    # Validate
    is_valid, error = validator.validate_selector(selector)
    if not is_valid:
        return create_validation_error("selector", error)

    # Execute
    try:
        result = await page.click(selector)
        duration_ms = int((time.time() - start_time) * 1000)
        return create_success_result(data=result, duration_ms=duration_ms)
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return create_error_result(str(e), "CLICK_FAILED", duration_ms)
```

### Pattern: Health Check + Retry

```python
async def safe_operation(page):
    health = BrowserHealthCheck()

    # Check browser
    if not await health.check_browser_alive(page):
        result = await health.recover_browser(page)
        if not result.success:
            return result

    # Execute with retry
    executor = ReliableExecutor()
    return await executor.execute(
        operation=lambda: page.click("button"),
        timeout=TimeoutConfig.NORMAL,
        retries=2
    )
```

### Pattern: Batch Operations

```python
executor = ReliableExecutor()

for item in items:
    result = await executor.execute(
        operation=lambda: process(item),
        timeout=TimeoutConfig.NORMAL,
        retries=2
    )

    if not result.success:
        logger.error(f"Failed: {result.error}")

stats = executor.get_stats()
logger.info(f"Done: {stats['success_rate_pct']}% success")
```

## Error Codes

| Code | Meaning |
|------|---------|
| `VALIDATION_ERROR` | Invalid input |
| `ELEMENT_NOT_FOUND` | Element not found |
| `TIMEOUT` | Operation timed out |
| `BROWSER_DEAD` | Browser unresponsive |
| `RECOVERY_FAILED` | Recovery failed |
| `PAGE_READY_TIMEOUT` | Page not ready |
| `FAIL_FAST` | Non-retryable error |

## Testing

```bash
cd /mnt/c/ev29/cli/engine/agent
python3 test_reliability_core.py
```
