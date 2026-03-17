# Reliability Core Module

**Production-ready error handling and browser health management for Eversale CLI**

Location: `/mnt/c/ev29/cli/engine/agent/reliability_core.py`

## Overview

The Reliability Core provides foundational reliability patterns for all Eversale CLI tools:

1. **ToolResult** - Standard return format with rich error context
2. **BrowserHealthCheck** - Browser lifecycle and recovery management
3. **ReliableExecutor** - Retry logic with exponential backoff and jitter
4. **InputValidator** - Comprehensive input validation
5. **TimeoutConfig** - Standard timeout constants

## Philosophy

- **NEVER swallow errors** - Surface them with clear messages
- **Every operation returns ToolResult** - Success/failure explicit
- **Log everything with timing** - Full observability
- **Retry intelligently** - Exponential backoff with jitter
- **Validate early** - Fail fast on invalid inputs

## Quick Start

```python
from reliability_core import (
    ToolResult, BrowserHealthCheck, ReliableExecutor,
    InputValidator, TimeoutConfig
)

# Execute with retry
executor = ReliableExecutor()
result = await executor.execute(
    operation=lambda: page.click("button"),
    timeout=TimeoutConfig.NORMAL,
    retries=2
)

if result.success:
    print(f"Clicked button in {result.duration_ms}ms")
else:
    print(f"Failed: {result.error} [{result.error_code}]")
```

## 1. ToolResult - Standard Return Format

Every tool should return `ToolResult` for consistent error handling.

### Structure

```python
@dataclass
class ToolResult:
    success: bool                    # True if succeeded
    data: Any = None                # Result data
    error: Optional[str] = None     # Human-readable error
    error_code: Optional[str] = None  # Machine-readable code
    duration_ms: int = 0            # Execution time
    retries_used: int = 0           # Retry attempts
```

### Usage

```python
# Manual creation
result = ToolResult(
    success=True,
    data={"status": "complete"},
    duration_ms=123
)

# Convenience functions
from reliability_core import create_success_result, create_error_result

result = create_success_result(data="Hello", duration_ms=100)
error = create_error_result("Not found", "ELEMENT_NOT_FOUND")

# Check result
if result.success:
    print(f"Success: {result.data}")
else:
    print(f"Error: {result.error} [{result.error_code}]")
    print(f"Took {result.duration_ms}ms with {result.retries_used} retries")

# Convert to dict for JSON
data = result.to_dict()
```

### Common Error Codes

| Code | Meaning |
|------|---------|
| `ELEMENT_NOT_FOUND` | Element selector didn't match |
| `TIMEOUT` | Operation timed out |
| `VALIDATION_ERROR` | Input validation failed |
| `RECOVERY_FAILED` | Browser recovery unsuccessful |
| `PAGE_READY_TIMEOUT` | Page didn't become ready in time |
| `FAIL_FAST` | Non-retryable exception occurred |

## 2. TimeoutConfig - Standard Timeouts

Use these constants instead of magic numbers.

```python
class TimeoutConfig:
    FAST = 2      # Quick operations (clicks, checks)
    NORMAL = 5    # Standard operations (navigation, forms)
    SLOW = 15     # Slow operations (complex pages, heavy JS)
    MAX = 30      # Maximum wait (file uploads, API calls)

    @staticmethod
    def to_ms(seconds: float) -> int:
        """Convert to milliseconds for Playwright"""
```

### Usage

```python
# Python (seconds)
result = await executor.execute(operation, timeout=TimeoutConfig.NORMAL)

# Playwright (milliseconds)
await page.click("button", timeout=TimeoutConfig.to_ms(TimeoutConfig.FAST))
```

## 3. BrowserHealthCheck - Browser Management

Monitor and recover browser health.

### Methods

#### `check_browser_alive(page) -> bool`

Quick check if browser is responsive.

```python
health = BrowserHealthCheck()

if not await health.check_browser_alive(page):
    print("Browser is unresponsive!")
    result = await health.recover_browser(page)
```

#### `check_page_loaded(page) -> bool`

Check if page is fully loaded (readyState complete/interactive).

```python
if await health.check_page_loaded(page):
    print("Page ready for interaction")
```

#### `wait_for_ready(page, timeout=5) -> ToolResult`

Wait until page is interactive.

```python
result = await health.wait_for_ready(page, timeout=TimeoutConfig.NORMAL)
if result.success:
    # Page is ready
    pass
```

#### `recover_browser(page) -> ToolResult`

Attempt multi-strategy browser recovery:

1. Reload current page
2. Navigate to blank page
3. Report failure if all strategies fail

```python
result = await health.recover_browser(page)
if result.success:
    print(f"Recovered via {result.data}")
else:
    print(f"Recovery failed: {result.error}")
```

#### `is_unhealthy` property

Check if browser has had too many consecutive failures (3+).

```python
if health.is_unhealthy:
    # Consider restarting browser
    pass
```

## 4. ReliableExecutor - Retry with Backoff

Execute operations with intelligent retry logic.

### Basic Usage

```python
executor = ReliableExecutor()

result = await executor.execute(
    operation=async_function,
    timeout=5,        # Timeout per attempt
    retries=2,        # Number of retries (3 total attempts)
    backoff=True      # Use exponential backoff with jitter
)
```

### Advanced Configuration

```python
result = await executor.execute(
    operation=operation,
    timeout=TimeoutConfig.NORMAL,
    retries=3,
    backoff=True,
    backoff_base=1.0,          # Base delay (1s)
    backoff_max=10.0,          # Max delay cap (10s)
    retry_on=(Exception,),     # Retry these exceptions
    fail_fast_on=(KeyboardInterrupt,)  # Don't retry these
)
```

### Backoff Strategy

Uses **decorrelated jitter** (AWS recommended):

```
delay = random(base_delay, min(max_delay, last_delay * 3))
```

This prevents thundering herd problems when multiple clients retry simultaneously.

### Statistics

```python
stats = executor.get_stats()
print(stats)
# {
#   'total_operations': 10,
#   'successful_operations': 8,
#   'failed_operations': 2,
#   'total_retries': 5,
#   'success_rate_pct': 80.0,
#   'avg_duration_ms': 1234.5
# }

executor.reset_stats()  # Clear counters
```

### Example: Flaky API Call

```python
executor = ReliableExecutor()

async def fetch_data():
    response = await api.get("/data")
    return response.json()

result = await executor.execute(
    operation=fetch_data,
    timeout=TimeoutConfig.NORMAL,
    retries=3,
    backoff=True
)

if result.success:
    data = result.data
    print(f"Got data after {result.retries_used} retries")
else:
    print(f"Failed: {result.error}")
```

## 5. InputValidator - Input Validation

Validate inputs before execution to fail early with clear errors.

### Methods

#### `validate_url(url) -> (bool, Optional[str])`

Validate URL format and scheme.

```python
validator = InputValidator()

is_valid, error = validator.validate_url("https://example.com")
if not is_valid:
    return create_validation_error("url", error)
```

**Valid schemes:** http, https, about, data, file

**Examples:**
```python
validator.validate_url("https://example.com")  # (True, None)
validator.validate_url("example.com")          # (False, "URL must include scheme...")
validator.validate_url("ftp://example.com")    # (False, "Invalid URL scheme...")
```

#### `validate_selector(selector) -> (bool, Optional[str])`

Validate selector format (CSS, XPath, Playwright selectors).

```python
is_valid, error = validator.validate_selector("button.primary")
if not is_valid:
    return create_validation_error("selector", error)
```

**Supported formats:**
- CSS: `button.primary`, `#submit`, `[data-testid=btn]`
- XPath: `//div[@class='test']`
- Playwright: `text=Click me`, `role=button`, `placeholder=Search`

**Examples:**
```python
validator.validate_selector("button.primary")  # (True, None)
validator.validate_selector("text=Submit")     # (True, None)
validator.validate_selector("")                # (False, "Selector must be...")
```

#### `validate_ref(ref) -> (bool, Optional[str])`

Validate accessibility reference (MMID from dom_distillation).

```python
is_valid, error = validator.validate_ref("element-123")
if not is_valid:
    return create_validation_error("ref", error)
```

**Format:** Alphanumeric with hyphens and underscores only, max 100 chars.

**Examples:**
```python
validator.validate_ref("element-123")      # (True, None)
validator.validate_ref("btn_submit")       # (True, None)
validator.validate_ref("invalid ref!")     # (False, "Ref must be alphanumeric...")
```

#### `validate_text_input(text, max_length=10000) -> (bool, Optional[str])`

Validate text for typing operations.

```python
is_valid, error = validator.validate_text_input("Hello world")
```

#### `validate_timeout(timeout) -> (bool, Optional[str])`

Validate timeout value (must be positive, max 30s).

```python
is_valid, error = validator.validate_timeout(5.0)
```

## Integration Patterns

### Pattern 1: Tool Wrapper

Wrap existing tools to return ToolResult:

```python
from reliability_core import (
    ToolResult, TimeoutConfig, InputValidator,
    create_success_result, create_error_result, create_validation_error
)
import time

async def click_element(page, selector: str) -> ToolResult:
    """Click element with validation and error handling."""
    start_time = time.time()
    validator = InputValidator()

    # Validate input
    is_valid, error = validator.validate_selector(selector)
    if not is_valid:
        return create_validation_error("selector", error)

    # Execute with try/catch
    try:
        await page.click(selector, timeout=TimeoutConfig.to_ms(TimeoutConfig.NORMAL))
        duration_ms = int((time.time() - start_time) * 1000)
        return create_success_result(data="clicked", duration_ms=duration_ms)

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return create_error_result(
            error=str(e),
            error_code="CLICK_FAILED",
            duration_ms=duration_ms
        )
```

### Pattern 2: Health Check Before Critical Operations

```python
from reliability_core import BrowserHealthCheck

async def perform_critical_operation(page):
    health = BrowserHealthCheck()

    # Check browser before proceeding
    if not await health.check_browser_alive(page):
        result = await health.recover_browser(page)
        if not result.success:
            return result  # Return recovery failure

    # Wait for page ready
    result = await health.wait_for_ready(page)
    if not result.success:
        return result

    # Proceed with operation
    # ...
```

### Pattern 3: Reliable Execution with Validation

```python
from reliability_core import (
    ReliableExecutor, InputValidator, TimeoutConfig,
    create_validation_error
)

async def navigate_to_url(page, url: str) -> ToolResult:
    """Navigate with validation and retry."""
    validator = InputValidator()

    # Validate first
    is_valid, error = validator.validate_url(url)
    if not is_valid:
        return create_validation_error("url", error)

    # Execute with retry
    executor = ReliableExecutor()
    result = await executor.execute(
        operation=lambda: page.goto(url, wait_until="domcontentloaded"),
        timeout=TimeoutConfig.SLOW,
        retries=2,
        backoff=True
    )

    return result
```

### Pattern 4: Batch Operations with Statistics

```python
executor = ReliableExecutor()

# Process many operations
for item in items:
    result = await executor.execute(
        operation=lambda: process_item(item),
        timeout=TimeoutConfig.NORMAL,
        retries=2
    )

    if not result.success:
        logger.error(f"Failed {item}: {result.error}")

# Show overall stats
stats = executor.get_stats()
logger.info(f"Batch complete: {stats['success_rate_pct']}% success rate")
```

## Best Practices

### 1. Always Return ToolResult

```python
# GOOD
async def my_tool(page, selector):
    try:
        result = await page.click(selector)
        return create_success_result(data=result)
    except Exception as e:
        return create_error_result(str(e), "TOOL_ERROR")

# BAD - Don't raise exceptions from tools
async def my_tool(page, selector):
    result = await page.click(selector)  # Can raise
    return result  # Wrong return type
```

### 2. Validate Early

```python
async def my_tool(page, url):
    validator = InputValidator()

    # Validate BEFORE executing
    is_valid, error = validator.validate_url(url)
    if not is_valid:
        return create_validation_error("url", error)

    # Now execute
    # ...
```

### 3. Use Standard Timeouts

```python
# GOOD
timeout = TimeoutConfig.NORMAL
result = await executor.execute(operation, timeout=timeout)

# BAD - Magic numbers
result = await executor.execute(operation, timeout=5)
```

### 4. Log with Context

```python
result = await executor.execute(operation, timeout=TimeoutConfig.NORMAL)

if result.success:
    logger.info(f"Operation succeeded in {result.duration_ms}ms")
else:
    logger.error(
        f"Operation failed: {result.error} [{result.error_code}] "
        f"after {result.retries_used} retries ({result.duration_ms}ms)"
    )
```

### 5. Check Browser Health

```python
health = BrowserHealthCheck()

# Before critical operations
if health.is_unhealthy:
    await health.recover_browser(page)

# Verify browser is alive
if not await health.check_browser_alive(page):
    return create_error_result("Browser unresponsive", "BROWSER_DEAD")
```

## Testing

Run the test suite:

```bash
cd /mnt/c/ev29/cli/engine/agent
python3 test_reliability_core.py
```

The test suite validates:
- ToolResult creation and serialization
- TimeoutConfig constants
- ReliableExecutor retry logic and backoff
- InputValidator for URLs, selectors, refs, timeouts
- BrowserHealthCheck with mock browser

## Migration Guide

To adopt reliability_core in existing tools:

1. **Import the module:**
   ```python
   from reliability_core import (
       ToolResult, ReliableExecutor, InputValidator, TimeoutConfig
   )
   ```

2. **Change return types to ToolResult:**
   ```python
   # Before
   async def my_tool(page):
       result = await page.click("button")
       return result

   # After
   async def my_tool(page) -> ToolResult:
       try:
           result = await page.click("button")
           return create_success_result(data=result)
       except Exception as e:
           return create_error_result(str(e), "CLICK_FAILED")
   ```

3. **Add input validation:**
   ```python
   validator = InputValidator()
   is_valid, error = validator.validate_selector(selector)
   if not is_valid:
       return create_validation_error("selector", error)
   ```

4. **Use ReliableExecutor for retry:**
   ```python
   executor = ReliableExecutor()
   result = await executor.execute(
       operation=lambda: page.click(selector),
       timeout=TimeoutConfig.NORMAL,
       retries=2
   )
   ```

5. **Replace magic timeouts with constants:**
   ```python
   # Before
   await page.click("button", timeout=5000)

   # After
   await page.click("button", timeout=TimeoutConfig.to_ms(TimeoutConfig.NORMAL))
   ```

## Error Code Registry

Maintain consistent error codes across tools:

| Code | Category | Meaning |
|------|----------|---------|
| `VALIDATION_ERROR` | Input | Input validation failed |
| `ELEMENT_NOT_FOUND` | Browser | Element selector didn't match |
| `TIMEOUT` | Timing | Operation exceeded timeout |
| `BROWSER_DEAD` | Browser | Browser unresponsive |
| `RECOVERY_FAILED` | Browser | Recovery unsuccessful |
| `PAGE_READY_TIMEOUT` | Browser | Page didn't load in time |
| `CLICK_FAILED` | Browser | Click operation failed |
| `NAVIGATION_FAILED` | Browser | Navigation failed |
| `FAIL_FAST` | Execution | Non-retryable error |

## Summary

The Reliability Core provides:

- **ToolResult** - Standard return format (never throw, always return)
- **TimeoutConfig** - Standard timeouts (no magic numbers)
- **BrowserHealthCheck** - Browser monitoring and recovery
- **ReliableExecutor** - Retry with exponential backoff + jitter
- **InputValidator** - Early validation with clear errors

Use these patterns to build robust, observable, and recoverable tools.
