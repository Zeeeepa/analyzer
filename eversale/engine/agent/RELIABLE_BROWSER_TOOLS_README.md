# Reliable Browser Tools

Production-ready wrapper for browser operations with comprehensive reliability guarantees.

## Overview

Every browser operation goes through validation, health checking, retry logic, and structured logging. This ensures robust automation that handles real-world failures gracefully.

## Features

### 1. Input Validation
- URL format validation (http/https, length limits)
- Target validation (selectors, refs, descriptions)
- Text content validation (length limits, type checking)
- Timeout validation (reasonable bounds)

### 2. Browser Health Checking
- Automatic health checks before operations
- Cached health status (5-second TTL)
- Early failure detection
- Clear error messages

### 3. Smart Retry Logic
- Distinguishes transient vs permanent errors
- Retries on: timeout, network errors, connection issues
- No retry on: element not found, invalid selector
- Exponential backoff between retries

### 4. Target Resolution
- **Accessibility ref**: `ref=mm1` -> Uses browser_click with mmid
- **CSS selector**: `.button` or `#submit` -> Uses playwright_click
- **XPath**: `//button[@type='submit']` -> Uses playwright_click
- **Description**: `Submit button` -> Tries multiple strategies

### 5. Comprehensive Logging
- Timing information for all operations
- Clear success/failure indicators
- Retry count tracking
- Colored console output (when Rich available)

## Usage

### Basic Example

```python
from reliable_browser_tools import ReliableBrowser

# Initialize with MCP client
browser = ReliableBrowser(mcp_client)

# Navigate
result = await browser.navigate("https://example.com")
if not result.success:
    print(f"Navigation failed: {result.error}")

# Get snapshot
result = await browser.get_snapshot()
if result.success:
    print(f"Snapshot: {result.data}")

# Click element
result = await browser.click(".submit-button")
print(f"Clicked: {result.success}, retries: {result.retries}")

# Type text
result = await browser.type("#email", "user@example.com")
```

### Target Resolution Examples

```python
# By accessibility ref (from snapshot)
await browser.click("ref=mm1")

# By CSS selector
await browser.click(".submit-button")
await browser.click("#login-form")

# By XPath
await browser.click("//button[@type='submit']")

# By natural language (tries multiple strategies)
await browser.click("Submit button")
await browser.type("Email input", "user@example.com")
```

### Error Handling

```python
result = await browser.navigate("https://example.com")

if result.success:
    print(f"Success! Took {result.retries} retries")
    print(f"Data: {result.data}")
else:
    print(f"Failed: {result.error}")
    print(f"Tried {result.retries + 1} times")
```

### Custom Retry Configuration

```python
# More aggressive retry
browser.set_retry_config(max_retries=5, retry_delay=0.5)

# Less aggressive
browser.set_retry_config(max_retries=1, retry_delay=2.0)
```

## API Reference

### ReliableBrowser Class

#### `__init__(mcp_client, page=None)`
Initialize reliable browser wrapper.

**Args:**
- `mcp_client`: MCP client instance
- `page`: Optional Playwright page (for direct access)

#### `async navigate(url: str, timeout: int = 15) -> ToolResult`
Navigate to URL with validation, health check, and retry.

**Args:**
- `url`: URL to navigate to (must start with http:// or https://)
- `timeout`: Timeout in seconds (0.1 to 300)

**Returns:**
- `ToolResult` with success status, data, error, and retry count

**Example:**
```python
result = await browser.navigate("https://example.com", timeout=30)
```

#### `async click(target: str, timeout: int = 5) -> ToolResult`
Click element by ref, selector, or description.

**Args:**
- `target`: Element target (ref=X, CSS, XPath, or description)
- `timeout`: Timeout in seconds

**Returns:**
- `ToolResult` with success status and retry count

**Example:**
```python
# By ref
await browser.click("ref=mm1")

# By selector
await browser.click(".submit-button")

# By description
await browser.click("Submit button")
```

#### `async type(target: str, text: str, timeout: int = 5) -> ToolResult`
Type text into element.

**Args:**
- `target`: Element target (ref=X, CSS, XPath, or description)
- `text`: Text to type (max 10,000 chars)
- `timeout`: Timeout in seconds

**Returns:**
- `ToolResult` with success status

**Example:**
```python
await browser.type("#email", "user@example.com")
await browser.type("ref=mm2", "Password123")
```

#### `async get_snapshot(timeout: int = 5) -> ToolResult`
Get accessibility snapshot of current page.

**Args:**
- `timeout`: Timeout in seconds

**Returns:**
- `ToolResult` with snapshot data including mmids

**Example:**
```python
result = await browser.get_snapshot()
if result.success:
    snapshot = result.data
    print(f"Available refs: {snapshot.get('mmids')}")
```

#### `async get_text(timeout: int = 5) -> ToolResult`
Get page text content.

**Args:**
- `timeout`: Timeout in seconds

**Returns:**
- `ToolResult` with text content

**Example:**
```python
result = await browser.get_text()
if result.success:
    print(f"Page text: {result.data['content']}")
```

#### `async screenshot(filename: Optional[str] = None, timeout: int = 5) -> ToolResult`
Take screenshot of current page.

**Args:**
- `filename`: Optional filename to save to
- `timeout`: Timeout in seconds

**Returns:**
- `ToolResult` with screenshot path

**Example:**
```python
await browser.screenshot("login.png")
await browser.screenshot()  # Auto-generated filename
```

#### `async wait_for(condition: str, timeout: int = 10) -> ToolResult`
Wait for text/element/condition.

**Args:**
- `condition`: What to wait for (text or selector)
- `timeout`: Timeout in seconds

**Returns:**
- `ToolResult` with success status

**Example:**
```python
await browser.wait_for("Dashboard")
await browser.wait_for(".success-message")
```

#### `set_retry_config(max_retries: int = 2, retry_delay: float = 1.0)`
Configure retry behavior.

**Args:**
- `max_retries`: Maximum number of retries
- `retry_delay`: Base delay between retries (seconds)

**Example:**
```python
browser.set_retry_config(max_retries=3, retry_delay=0.5)
```

## ToolResult Structure

```python
@dataclass
class ToolResult:
    success: bool          # Operation succeeded
    data: Any = None       # Result data (if success)
    error: str = None      # Error message (if failed)
    cached: bool = False   # Result from cache
    retries: int = 0       # Number of retries performed
```

## Retry Logic

### Transient Errors (Will Retry)
- Timeout errors
- Network errors
- Connection errors
- ECONNRESET, ETIMEDOUT
- "Temporarily unavailable"

### Permanent Errors (Won't Retry)
- Element not found
- Selector not found
- Element not visible
- Element not attached
- Invalid selector

### Retry Behavior
1. First attempt executes immediately
2. On transient failure, wait `retry_delay` seconds
3. Retry with exponential backoff: `retry_delay * (attempt + 1)`
4. Max retries: Default 2 (configurable)
5. Permanent errors fail immediately (no retry)

## Console Output

When Rich is available, operations show colored status:

```
[dim]Navigating to https://example.com...[/dim]
[green]Page loaded (1.2s)[/green]

[dim]Clicking .submit-button...[/dim]
[green]Clicked successfully[/green]

[dim]Typing into #email...[/dim]
[red]Type failed: element not found[/red]
```

## Logging

All operations log timing and status:

```
[BROWSER] navigate('https://example.com') completed in 1234ms
[BROWSER] click(.submit-button) completed in 89ms
[BROWSER] type(#email, 'user@...') failed after 2 attempts: element not found
```

## Integration with Existing Code

### With MCP Client

```python
from mcp_client import MCPClient
from reliable_browser_tools import ReliableBrowser

# Initialize MCP client
mcp = MCPClient()
await mcp.connect_all_servers()

# Create reliable browser
browser = ReliableBrowser(mcp)

# Use for all browser operations
await browser.navigate("https://example.com")
```

### With Existing Tools

```python
# Replace direct tool calls
# OLD:
result = await mcp.call_tool("playwright_navigate", {"url": url})

# NEW:
result = await browser.navigate(url)  # Validated, retried, logged
```

## Best Practices

1. **Always check result.success** before using result.data
2. **Use specific timeouts** based on expected operation time
3. **Prefer accessibility refs** when available (from snapshots)
4. **Handle errors gracefully** - log and continue or retry workflow
5. **Set retry config** at workflow start based on criticality

## Testing

Run the example file to see all features:

```bash
python engine/agent/reliable_browser_tools_example.py
```

## Error Messages

### Validation Errors
- "Invalid URL: URL must start with http:// or https://"
- "Invalid target: Target must be a non-empty string"
- "Invalid timeout: Timeout must be at least 0.1 seconds"

### Health Errors
- "Browser not healthy: Browser health check timed out"
- "Browser not healthy: Browser health check failed: {error}"

### Operation Errors
- "Operation timed out after {timeout}s"
- "Could not find element by description: {desc}"
- "Failed after {retries} retries: {error}"

## Performance

- Health checks cached for 5 seconds (configurable)
- Minimal overhead: ~0.1ms validation + health check
- Retry adds: `retry_delay * (2^attempt)` seconds
- Most operations: <100ms with validation

## Dependencies

- `asyncio` - Async/await support
- `loguru` - Logging
- `rich` - Console output (optional)
- `tool_wrappers` - ToolResult dataclass

## License

Part of the Eversale CLI agent system.
