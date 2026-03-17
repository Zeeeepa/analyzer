# Reliable Browser Tools - Quick Reference

One-page cheat sheet for common operations.

## Setup

```python
from reliable_browser_tools import ReliableBrowser

browser = ReliableBrowser(mcp_client)
```

## Navigation

```python
# Basic
result = await browser.navigate("https://example.com")

# With timeout
result = await browser.navigate("https://example.com", timeout=30)

# Check result
if result.success:
    print("Loaded!")
else:
    print(f"Failed: {result.error}")
```

## Clicking

```python
# By CSS selector
await browser.click(".submit-button")
await browser.click("#login-btn")

# By accessibility ref (from snapshot)
await browser.click("ref=mm1")

# By XPath
await browser.click("//button[@type='submit']")

# By description (tries multiple strategies)
await browser.click("Submit button")
```

## Typing

```python
# By CSS selector
await browser.type("#email", "user@example.com")

# By accessibility ref
await browser.type("ref=mm2", "Password123")

# By description
await browser.type("Email input", "user@example.com")
```

## Getting Page Data

```python
# Accessibility snapshot (with mmid refs)
result = await browser.get_snapshot()
if result.success:
    snapshot = result.data
    refs = snapshot.get("mmids", {})

# Text content
result = await browser.get_text()
if result.success:
    text = result.data["content"]

# Screenshot
await browser.screenshot("page.png")
await browser.screenshot()  # Auto filename
```

## Waiting

```python
# Wait for text
await browser.wait_for("Dashboard")

# Wait for selector
await browser.wait_for(".success-message")

# With timeout
await browser.wait_for("Loading complete", timeout=30)
```

## Error Handling

```python
result = await browser.navigate("https://example.com")

if result.success:
    print(f"Success! Data: {result.data}")
    print(f"Retries: {result.retries}")
else:
    print(f"Failed: {result.error}")
    print(f"Attempted {result.retries + 1} times")
```

## Configuration

```python
# More aggressive retry
browser.set_retry_config(max_retries=5, retry_delay=0.5)

# Less aggressive
browser.set_retry_config(max_retries=1, retry_delay=2.0)
```

## Complete Workflow Example

```python
browser = ReliableBrowser(mcp_client)

# 1. Navigate
if not (await browser.navigate("https://app.example.com/login")).success:
    return

# 2. Fill form
await browser.type("#email", "user@example.com")
await browser.type("#password", "SecurePass123")

# 3. Submit
await browser.click("button[type='submit']")

# 4. Wait for redirect
await browser.wait_for("Dashboard", timeout=10)

# 5. Capture result
await browser.screenshot("logged-in.png")
```

## Target Resolution Cheat Sheet

| Input | Resolved As | Tool Used |
|-------|-------------|-----------|
| `ref=mm1` | Accessibility ref | `browser_click` |
| `.button` | CSS selector | `playwright_click` |
| `#submit` | CSS selector | `playwright_click` |
| `//button` | XPath | `playwright_click` |
| `Submit button` | Description | Multiple strategies |

## Retry Behavior

**Will Retry:**
- Timeout errors
- Network errors
- Connection failures
- Temporary unavailability

**Won't Retry:**
- Element not found
- Invalid selector
- Element not visible
- Validation errors

## Result Object

```python
result.success   # bool - operation succeeded
result.data      # Any - result data
result.error     # str - error message (if failed)
result.retries   # int - number of retries performed
```

## Common Patterns

### Pattern 1: Navigate and Interact
```python
await browser.navigate(url)
await browser.click(target)
```

### Pattern 2: Fill Multi-Field Form
```python
fields = [
    ("#name", "John Doe"),
    ("#email", "john@example.com"),
    ("#phone", "555-1234")
]

for selector, value in fields:
    result = await browser.type(selector, value)
    if not result.success:
        print(f"Failed to fill {selector}: {result.error}")
        break
```

### Pattern 3: Get Snapshot + Click by Ref
```python
# Get snapshot to see available refs
snapshot = await browser.get_snapshot()
refs = snapshot.data.get("mmids", {})

# Click by ref
await browser.click("ref=mm1")
```

### Pattern 4: Retry Configuration by Task
```python
# Critical task - aggressive retry
browser.set_retry_config(max_retries=5, retry_delay=1.0)
await browser.navigate(critical_url)

# Fast task - minimal retry
browser.set_retry_config(max_retries=1, retry_delay=0.5)
await browser.click(simple_button)
```

## Tips

1. Always check `result.success` before using `result.data`
2. Use accessibility refs when available (more reliable)
3. Set appropriate timeouts based on expected load time
4. Handle errors gracefully - log and continue or abort
5. Use descriptions for readability, selectors for precision

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Invalid URL" | Ensure URL starts with http:// or https:// |
| "Browser not healthy" | Browser may have crashed - restart |
| "Element not found" | Check selector, wait for page load |
| "Timeout" | Increase timeout or check network |
| Too many retries | Reduce max_retries or fix underlying issue |
