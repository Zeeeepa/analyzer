# A11yBrowser Testing/Assertion Methods

Full Playwright MCP parity for testing and assertions. All methods added to `/mnt/c/ev29/cli/engine/agent/a11y_browser.py`.

## Summary

10 new testing/assertion methods added for complete Playwright MCP compatibility:

| Method | Description | Return Type |
|--------|-------------|-------------|
| `expect_visible()` | Assert element is visible | ActionResult |
| `expect_hidden()` | Assert element is hidden | ActionResult |
| `expect_text()` | Assert element contains text | ActionResult |
| `expect_value()` | Assert input has value | ActionResult |
| `expect_url()` | Assert URL matches pattern | ActionResult |
| `expect_title()` | Assert title matches pattern | ActionResult |
| `count_elements()` | Count elements by role/name | ActionResult |
| `expect_count()` | Assert element count | ActionResult |
| `get_inner_html()` | Get element's inner HTML | ActionResult |
| `get_outer_html()` | Get element's outer HTML | ActionResult |

---

## Method Reference

### 1. expect_visible(ref, timeout=5000)

Assert that an element is visible.

**Parameters:**
- `ref` (str): Element ref from snapshot
- `timeout` (int): Max time to wait in milliseconds (default: 5000)

**Returns:**
- `ActionResult` with `success=True` if visible, `success=False` if hidden

**Example:**
```python
result = await browser.expect_visible("e42")
if result.success:
    print("Element is visible")
else:
    print(f"Assertion failed: {result.error}")
```

---

### 2. expect_hidden(ref, timeout=5000)

Assert that an element is hidden (not visible).

**Parameters:**
- `ref` (str): Element ref from snapshot
- `timeout` (int): Max time to wait in milliseconds (default: 5000)

**Returns:**
- `ActionResult` with `success=True` if hidden, `success=False` if visible

**Example:**
```python
result = await browser.expect_hidden("e99")
if result.success:
    print("Element is hidden")
```

---

### 3. expect_text(ref, text, timeout=5000)

Assert that an element contains specific text (partial match).

**Parameters:**
- `ref` (str): Element ref from snapshot
- `text` (str): Expected text (partial match)
- `timeout` (int): Max time to wait in milliseconds (default: 5000)

**Returns:**
- `ActionResult` with `success=True` if text found, `success=False` otherwise
- `data` contains `expected` and `actual` text

**Example:**
```python
result = await browser.expect_text("e15", "Submit")
if result.success:
    print(f"Found expected text: {result.data['expected']}")
    print(f"Actual text: {result.data['actual']}")
else:
    print(f"Text not found: {result.error}")
```

---

### 4. expect_value(ref, value, timeout=5000)

Assert that an input element has a specific value (exact match).

**Parameters:**
- `ref` (str): Element ref from snapshot (must be input element)
- `value` (str): Expected value (exact match)
- `timeout` (int): Max time to wait in milliseconds (default: 5000)

**Returns:**
- `ActionResult` with `success=True` if value matches, `success=False` otherwise
- `data` contains `expected` and `actual` values

**Example:**
```python
await browser.type("e10", "john@example.com")
result = await browser.expect_value("e10", "john@example.com")
if result.success:
    print("Input value matches expected")
```

---

### 5. expect_url(pattern, timeout=5000)

Assert that the current URL matches a regex pattern.

**Parameters:**
- `pattern` (str): Regex pattern to match against URL
- `timeout` (int): Currently unused, kept for API consistency (default: 5000)

**Returns:**
- `ActionResult` with `success=True` if URL matches, `success=False` otherwise
- `data` contains `pattern` and actual `url`

**Example:**
```python
result = await browser.expect_url("https://example.com.*")
if result.success:
    print(f"URL matches: {result.data['url']}")
```

---

### 6. expect_title(pattern, timeout=5000)

Assert that the page title matches a regex pattern.

**Parameters:**
- `pattern` (str): Regex pattern to match against title
- `timeout` (int): Currently unused, kept for API consistency (default: 5000)

**Returns:**
- `ActionResult` with `success=True` if title matches, `success=False` otherwise
- `data` contains `pattern` and actual `title`

**Example:**
```python
result = await browser.expect_title("Example.*")
if result.success:
    print(f"Title matches: {result.data['title']}")
```

---

### 7. count_elements(role=None, name=None)

Count elements matching role and/or name criteria.

**Parameters:**
- `role` (str, optional): Element role to filter by
- `name` (str, optional): Element name to filter by (partial match)

**Returns:**
- `ActionResult` with `data['count']` containing the count
- `data` also contains `role` and `name` used for filtering

**Example:**
```python
# Count all buttons
result = await browser.count_elements(role="button")
print(f"Found {result.data['count']} buttons")

# Count buttons with "Submit" in name
result = await browser.count_elements(role="button", name="Submit")
print(f"Found {result.data['count']} submit buttons")
```

---

### 8. expect_count(count, role=None, name=None)

Assert that the number of matching elements equals the expected count.

**Parameters:**
- `count` (int): Expected element count
- `role` (str, optional): Element role to filter by
- `name` (str, optional): Element name to filter by (partial match)

**Returns:**
- `ActionResult` with `success=True` if count matches, `success=False` otherwise
- `data` contains `expected` and `actual` counts

**Example:**
```python
# Assert there are exactly 3 buttons
result = await browser.expect_count(3, role="button")
if result.success:
    print("Button count matches")
else:
    print(f"Expected {result.data['expected']}, got {result.data['actual']}")
```

---

### 9. get_inner_html(ref, timeout=5000)

Get the inner HTML of an element.

**Parameters:**
- `ref` (str): Element ref from snapshot
- `timeout` (int): Max time to wait in milliseconds (default: 5000)

**Returns:**
- `ActionResult` with `data['html']` containing the inner HTML

**Example:**
```python
result = await browser.get_inner_html("e20")
if result.success:
    html = result.data['html']
    print(f"Inner HTML: {html}")
```

---

### 10. get_outer_html(ref, timeout=5000)

Get the outer HTML of an element (includes the element's own tag).

**Parameters:**
- `ref` (str): Element ref from snapshot
- `timeout` (int): Max time to wait in milliseconds (default: 5000)

**Returns:**
- `ActionResult` with `data['html']` containing the outer HTML

**Example:**
```python
result = await browser.get_outer_html("e20")
if result.success:
    html = result.data['html']
    print(f"Outer HTML: {html}")
```

---

## Usage Patterns

### Testing Form Submissions

```python
async with A11yBrowser() as browser:
    await browser.navigate("https://example.com/form")
    snapshot = await browser.snapshot()

    # Fill form
    name_input = snapshot.find_by_role("textbox")[0]
    await browser.type(name_input.ref, "John Doe")

    # Assert value was set
    result = await browser.expect_value(name_input.ref, "John Doe")
    assert result.success

    # Submit and wait
    submit_btn = snapshot.find_by_name("Submit")[0]
    await browser.click(submit_btn.ref)

    # Assert URL changed
    result = await browser.expect_url(".*/success")
    assert result.success
```

### Counting Elements

```python
# Get snapshot
snapshot = await browser.snapshot()

# Count manually
manual_count = len(snapshot.find_by_role("button"))

# Count via method
result = await browser.count_elements(role="button")
assert result.data['count'] == manual_count

# Assert count
result = await browser.expect_count(5, role="button")
if not result.success:
    print(f"Expected 5 buttons, got {result.data['actual']}")
```

### Visibility Testing

```python
# Test element visibility
modal_close = snapshot.find_by_name("Close")[0]

# Before showing modal
result = await browser.expect_hidden(modal_close.ref)
assert result.success

# Show modal
await browser.click(show_modal_btn.ref)

# After showing modal
result = await browser.expect_visible(modal_close.ref)
assert result.success
```

### Text Content Validation

```python
# Assert heading contains text
heading = snapshot.find_by_role("heading")[0]
result = await browser.expect_text(heading.ref, "Welcome")
assert result.success

# Get full text
result = await browser.get_text(heading.ref)
print(f"Full heading text: {result.data['text']}")
```

### HTML Inspection

```python
# Get inner HTML (content inside element)
container = snapshot.find_by_name("Container")[0]
result = await browser.get_inner_html(container.ref)
inner = result.data['html']

# Get outer HTML (includes element tag)
result = await browser.get_outer_html(container.ref)
outer = result.data['html']

# Parse HTML
from bs4 import BeautifulSoup
soup = BeautifulSoup(inner, 'html.parser')
links = soup.find_all('a')
print(f"Found {len(links)} links in container")
```

---

## Error Handling

All assertion methods return `ActionResult`. Always check `result.success`:

```python
result = await browser.expect_visible("e99")

if result.success:
    # Assertion passed
    print("Element is visible")
else:
    # Assertion failed
    print(f"Error: {result.error}")
    # Continue or handle error
```

---

## Integration with Existing Code

These methods integrate seamlessly with existing A11yBrowser code:

```python
# Standard workflow
snapshot = await browser.snapshot()
button = snapshot.find_by_name("Login")[0]
await browser.click(button.ref)

# Add assertions
result = await browser.expect_url(".*/dashboard")
assert result.success, "Login should redirect to dashboard"

result = await browser.expect_count(1, role="heading", name="Dashboard")
assert result.success, "Dashboard should have heading"
```

---

## Testing

Run the test suite:

```bash
cd /mnt/c/ev29/cli/engine/agent
python3 test_a11y_assertions.py
```

Test file: `/mnt/c/ev29/cli/engine/agent/test_a11y_assertions.py`

---

## Playwright MCP Parity Status

| Playwright MCP Tool | A11yBrowser Method | Status |
|---------------------|-------------------|--------|
| `expect.toBeVisible()` | `expect_visible()` | ✓ Complete |
| `expect.toBeHidden()` | `expect_hidden()` | ✓ Complete |
| `expect.toHaveText()` | `expect_text()` | ✓ Complete |
| `expect.toHaveValue()` | `expect_value()` | ✓ Complete |
| `expect.toHaveURL()` | `expect_url()` | ✓ Complete |
| `expect.toHaveTitle()` | `expect_title()` | ✓ Complete |
| `locator.count()` | `count_elements()` | ✓ Complete |
| `expect.toHaveCount()` | `expect_count()` | ✓ Complete |
| `innerHTML()` | `get_inner_html()` | ✓ Complete |
| `outerHTML()` | `get_outer_html()` | ✓ Complete |

**All 10 testing/assertion methods implemented. Full Playwright MCP parity achieved.**

---

## Notes

- All methods return `ActionResult` for consistency with existing A11yBrowser API
- Timeout parameters default to 5000ms (5 seconds)
- Pattern matching uses Python's `re` module for regex
- Assertion methods build on existing primitives like `is_visible()`, `get_text()`, `get_value()`
- HTML retrieval methods use Playwright's native `inner_html()` and `evaluate()`

---

**Last Updated:** 2025-12-12
**Version:** 1.0
**File:** `/mnt/c/ev29/cli/engine/agent/a11y_browser.py`
