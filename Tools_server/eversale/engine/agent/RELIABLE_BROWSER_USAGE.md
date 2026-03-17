# Reliable Browser Tools - Usage Guide

## Quick Start

The reliable browser tools are **automatically enabled** in the main execution path. You don't need to change existing code!

### For Existing Code (No Changes Needed)

```python
# Your existing code works exactly the same
from brain_enhanced_v2 import EnhancedBrain

config = {...}
brain = EnhancedBrain(config, mcp_client)

# All browser operations now have validation, health checks, and retry
# No code changes required!
```

### For New Code (Use Wrapper Directly)

```python
from reliable_browser_tools import wrap_mcp_client

# Wrap your MCP client
mcp = get_mcp_client()
reliable_mcp = wrap_mcp_client(mcp, enable_reliability=True)

# Use normally - reliability is transparent
result = await reliable_mcp.call_tool('playwright_navigate', {'url': 'https://example.com'})
```

## Advanced Usage

### 1. Direct ReliableBrowser API

For more control, use ReliableBrowser directly:

```python
from reliable_browser_tools import ReliableBrowser

# Create browser instance
browser = ReliableBrowser(mcp_client)

# Navigate with ToolResult return
result = await browser.navigate("https://example.com", timeout=15)
if result.success:
    print(f"Success! Data: {result.data}")
    print(f"Retries used: {result.retries}")
else:
    print(f"Failed: {result.error}")

# Click with validation
result = await browser.click("#button", timeout=5)

# Type with validation
result = await browser.type("#input", "search query", timeout=5)

# Get snapshot
result = await browser.get_snapshot(timeout=5)

# Screenshot
result = await browser.screenshot("page.png", timeout=5)
```

### 2. Custom Validation

```python
from reliable_browser_tools import BrowserInputValidator

validator = BrowserInputValidator()

# Validate before operations
url = user_input_url
valid, error = validator.validate_url(url)
if not valid:
    print(f"Invalid URL: {error}")
    return

# Validate selector
selector = "#user-" + user_id
valid, error = validator.validate_target(selector)
if not valid:
    print(f"Invalid selector: {error}")
    return

# Validate text input
text = user_input_text
valid, error = validator.validate_text(text)
if not valid:
    print(f"Invalid text: {error}")
    return
```

### 3. Health Checking

```python
from reliable_browser_tools import BrowserHealthChecker

# Create health checker
health_checker = BrowserHealthChecker(mcp_client)

# Check before critical operation
healthy, error = await health_checker.check()
if not healthy:
    print(f"Browser unhealthy: {error}")
    # Reconnect or abort
    return

# Health is cached for 5 seconds
# Subsequent checks within 5s use cached result
```

### 4. Configure Retry Behavior

```python
from reliable_browser_tools import ReliableBrowser

browser = ReliableBrowser(mcp_client)

# Default: max_retries=2, retry_delay=1.0
# Customize for your needs
browser.set_retry_config(max_retries=3, retry_delay=2.0)

# Now operations will retry up to 3 times with 2s delay
result = await browser.navigate("https://flaky-site.com")
```

### 5. Conditional Reliability

```python
from reliable_browser_tools import wrap_mcp_client

# Enable for production
if env == "production":
    mcp = wrap_mcp_client(mcp_client, enable_reliability=True)
else:
    # Disable for testing (faster, no retries)
    mcp = wrap_mcp_client(mcp_client, enable_reliability=False)
```

## Understanding ToolResult

ReliableBrowser returns `ToolResult` objects:

```python
@dataclass
class ToolResult:
    success: bool          # True if operation succeeded
    data: Any = None       # Result data (if successful)
    error: str = None      # Error message (if failed)
    cached: bool = False   # True if result was cached
    retries: int = 0       # Number of retries used
```

Example:
```python
result = await browser.navigate("https://example.com")

print(f"Success: {result.success}")
print(f"Data: {result.data}")
print(f"Error: {result.error}")
print(f"Retries: {result.retries}")

# Use in conditionals
if result.success:
    process(result.data)
else:
    handle_error(result.error)
```

## Integration Points

### Where Reliability is Active

1. **EnhancedBrain** (`/mnt/c/ev29/cli/engine/agent/brain_enhanced_v2.py`)
   - All MCP tool calls
   - All browser operations
   - Deterministic workflows
   - Cloudflare handler
   - Accessibility finder

2. **BrowserToolAdapter** (`/mnt/c/ev29/cli/engine/agent/brain_enhanced_v2.py`)
   - Workflow execution
   - Alternative site routing
   - Challenge handling

3. **PlaywrightClient** (`/mnt/c/ev29/cli/engine/agent/playwright_direct.py`)
   - Direct Playwright operations
   - Input validation layer
   - navigate(), click(), fill() methods

## Validation Examples

### Valid Inputs (Pass)
```python
# URLs
✓ "https://example.com"
✓ "http://localhost:3000"
✓ "https://sub.domain.co.uk/path?query=value"

# Selectors
✓ "#button"
✓ ".class-name"
✓ "div > span.active"
✓ "[data-testid='submit']"

# Text
✓ "normal text"
✓ "text with spaces"
✓ "text with 'quotes'"
✓ "" (empty string is valid for text)

# Timeouts
✓ 1 (1 second)
✓ 5.5 (5.5 seconds)
✓ 30 (30 seconds)
```

### Invalid Inputs (Caught)
```python
# URLs
✗ "not-a-url" (missing http://)
✗ "" (empty string)
✗ None (not a string)
✗ "x" * 3000 (too long)

# Selectors
✗ "" (empty string)
✗ None (not a string)
✗ "x" * 1100 (too long)

# Text
✗ 123 (not a string)
✗ None (not a string)
✗ "x" * 11000 (too long)

# Timeouts
✗ -1 (negative)
✗ 0 (too short)
✗ 500 (too long)
✗ "5" (not a number)
```

## Error Handling

### Transient Errors (Will Retry)
```python
# These errors trigger automatic retry:
- "timeout"
- "network error"
- "connection refused"
- "ECONNRESET"
- "ETIMEDOUT"
- "temporarily unavailable"

# Example:
result = await browser.navigate("https://slow-site.com")
# If navigation times out, will retry 2 more times
# Total attempts: 3 (1 initial + 2 retries)
```

### Permanent Errors (Won't Retry)
```python
# These errors fail immediately:
- "element not found"
- "selector not found"
- "no element matches"
- "element is not visible"
- "invalid selector"

# Example:
result = await browser.click("#nonexistent")
# Fails immediately without retry
# result.success = False
# result.error = "element not found: #nonexistent"
```

## Logging

### What Gets Logged

```python
# Successful operations
[BROWSER] navigate('https://example.com') completed in 1234ms

# Failed operations
[BROWSER] click(#button) failed (retrying): timeout
[BROWSER] type(#input, 'text') failed after 3 attempts: element not found

# Validation errors
[RELIABLE] URL validation failed: URL must start with http://
[RELIABLE] Selector validation failed: Target must be a non-empty string

# Integration points
[RELIABLE] EnhancedBrain using ReliableBrowser wrapper
[RELIABLE] BrowserToolAdapter using ReliableBrowser wrapper
[RELIABLE] PlaywrightClient initialized with validation layer
```

### Log Levels

- `DEBUG`: Operation timing, cache hits, retry attempts
- `INFO`: Integration initialization
- `WARNING`: Validation failures, health check failures
- `ERROR`: Operation failures after all retries

## Best Practices

### 1. Let Validation Happen Early
```python
# Good - validation happens first
result = await browser.navigate(user_url)
if not result.success:
    return {"error": result.error}

# Bad - manual validation when automatic exists
if not user_url.startswith("http"):
    return {"error": "Invalid URL"}
result = await browser.navigate(user_url)
```

### 2. Use ToolResult Properties
```python
# Good - check success property
result = await browser.click("#button")
if result.success:
    process(result.data)
else:
    log_error(result.error)

# Bad - assume success
result = await browser.click("#button")
process(result)  # Might be error dict!
```

### 3. Configure Retries Appropriately
```python
# Fast operations - fewer retries
browser.set_retry_config(max_retries=1, retry_delay=0.5)
result = await browser.click("#button")

# Slow/flaky operations - more retries
browser.set_retry_config(max_retries=3, retry_delay=2.0)
result = await browser.navigate("https://slow-site.com")
```

### 4. Check Health for Long-Running Tasks
```python
# Good - check health before critical operation
healthy, error = await health_checker.check()
if healthy:
    result = await browser.navigate("https://important-site.com")
else:
    await reconnect_browser()

# Bad - assume browser is always healthy
result = await browser.navigate("https://important-site.com")
```

## Troubleshooting

### Problem: Too many retries slowing things down
**Solution**: Reduce retry count or disable for specific operations
```python
browser.set_retry_config(max_retries=1, retry_delay=0.5)
# or
mcp = wrap_mcp_client(mcp_client, enable_reliability=False)
```

### Problem: Valid inputs being rejected
**Solution**: Check validation rules, might need to adjust
```python
# If URL is rejected but should be valid:
valid, error = validator.validate_url(url)
print(f"Validation: {valid}, Error: {error}")
# Adjust URL format or validation rules
```

### Problem: Operations failing with "Browser not healthy"
**Solution**: Browser connection is dead, need to reconnect
```python
healthy, error = await health_checker.check()
if not healthy:
    await browser_client.reconnect()
```

### Problem: Logs showing validation but no retries
**Solution**: Validation happens before retry logic
```python
# Validation errors are permanent, won't retry
[RELIABLE] URL validation failed: URL must start with http://
# Fix the input, don't expect retry
```

## Performance Tips

1. **Health checks are cached** - Only run every 5 seconds
2. **Validation is fast** - <1ms per operation
3. **Retries only on failure** - No overhead for successful operations
4. **Configure based on use case** - Adjust retry settings per operation type

## Summary

- ✅ **Automatic**: Enabled by default in main execution path
- ✅ **Transparent**: Existing code works without changes
- ✅ **Configurable**: Adjust retry behavior as needed
- ✅ **Validated**: Inputs checked before execution
- ✅ **Resilient**: Automatic retry on transient failures
- ✅ **Observable**: Comprehensive logging for debugging

**Bottom Line**: Your browser operations are now more reliable with minimal code changes!
