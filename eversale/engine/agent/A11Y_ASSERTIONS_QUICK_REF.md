# A11yBrowser Assertions - Quick Reference

All 10 testing/assertion methods at a glance.

---

## Visibility

```python
# Assert visible
await browser.expect_visible("e42", timeout=5000)

# Assert hidden
await browser.expect_hidden("e99", timeout=5000)
```

---

## Content

```python
# Assert text (partial match)
await browser.expect_text("e15", "Submit", timeout=5000)

# Assert input value (exact match)
await browser.expect_value("e10", "john@example.com", timeout=5000)
```

---

## Page State

```python
# Assert URL pattern
await browser.expect_url("https://example.com.*", timeout=5000)

# Assert title pattern
await browser.expect_title("Dashboard.*", timeout=5000)
```

---

## Counting

```python
# Count elements
result = await browser.count_elements(role="button", name="Submit")
count = result.data['count']

# Assert count
await browser.expect_count(5, role="button")
```

---

## HTML

```python
# Get inner HTML
result = await browser.get_inner_html("e20", timeout=5000)
html = result.data['html']

# Get outer HTML
result = await browser.get_outer_html("e20", timeout=5000)
html = result.data['html']
```

---

## Return Pattern

All methods return `ActionResult`:

```python
result = await browser.expect_visible("e42")

if result.success:
    print("Assertion passed")
    print(result.data)  # Method-specific data
else:
    print(f"Assertion failed: {result.error}")
```

---

## Common Patterns

### Form Testing
```python
# Type and verify
await browser.type("e10", "test@example.com")
await browser.expect_value("e10", "test@example.com")

# Submit and verify redirect
await browser.click("e15")
await browser.expect_url(".*/success")
```

### Element Counting
```python
# Count buttons
result = await browser.count_elements(role="button")
# Assert count
await browser.expect_count(3, role="button")
```

### Visibility Testing
```python
# Before action
await browser.expect_hidden("e99")
# Trigger action
await browser.click("e42")
# After action
await browser.expect_visible("e99")
```

---

**File:** `/mnt/c/ev29/cli/engine/agent/a11y_browser.py`
**Full Docs:** `/mnt/c/ev29/cli/engine/agent/A11Y_ASSERTION_METHODS.md`
