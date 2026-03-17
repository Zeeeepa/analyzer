# Smart Scrolling Quick Reference

## TL;DR - Just Use This

```python
from agent.navigation_handlers import prepare_element_for_interaction

# Before ANY click or fill:
ready = await prepare_element_for_interaction(page, selector)
if ready:
    await page.click(selector)  # or page.fill()
```

## All Functions at a Glance

| Function | Purpose | Returns | Speed |
|----------|---------|---------|-------|
| `get_fixed_header_height(page)` | Get fixed header height | `int` (px) | <50ms |
| `is_element_in_viewport(page, selector)` | Check if visible | `Dict` | <50ms |
| `smart_scroll_to_element(page, selector)` | Scroll to center element | `bool` | 200-500ms |
| `focus_element_humanlike(page, selector)` | Human-like focus | `bool` | 200-400ms |
| `scroll_to_trigger_lazy_load(page, selector)` | Find lazy-loaded element | `bool` | 500ms-10s |
| `scroll_until_element_found(page, selector)` | Infinite scroll search | `bool` | 1s-30s |
| `scroll_element_into_view_if_needed(page, selector)` | Scroll only if needed | `bool` | <1s |
| **`prepare_element_for_interaction(page, selector)`** | **All-in-one (USE THIS)** | `bool` | **500ms-1s** |

## Common Patterns

### Pattern 1: Safe Click
```python
ready = await prepare_element_for_interaction(page, ".button")
if ready:
    await page.click(".button")
```

### Pattern 2: Check Before Scroll
```python
vis = await is_element_in_viewport(page, selector)
if not vis['visible']:
    await smart_scroll_to_element(page, selector)
```

### Pattern 3: Lazy Load
```python
found = await scroll_to_trigger_lazy_load(page, ".product-100", max_scrolls=15)
if found:
    # Extract data
    pass
```

### Pattern 4: Infinite Scroll
```python
found = await scroll_until_element_found(page, "[data-id='12345']", max_scrolls=50)
```

### Pattern 5: Form Fill
```python
for selector, value in fields:
    await prepare_element_for_interaction(page, selector)
    await page.fill(selector, value)
```

## Parameters Quick Guide

### `smart_scroll_to_element()`
- `padding`: Extra space from edges (default: 100px)
- `behavior`: `"smooth"` or `"auto"` (default: smooth)

### `scroll_to_trigger_lazy_load()`
- `max_scrolls`: Max attempts (default: 10)

### `scroll_until_element_found()`
- `max_scrolls`: Max attempts (default: 20)
- `scroll_pause`: Wait after scroll (default: 0.5s)

## When to Use What

| Scenario | Function |
|----------|----------|
| **Before ANY interaction** | `prepare_element_for_interaction()` |
| Check if element visible | `is_element_in_viewport()` |
| Scroll to specific element | `smart_scroll_to_element()` |
| Find element in lazy content | `scroll_to_trigger_lazy_load()` |
| Navigate infinite scroll | `scroll_until_element_found()` |
| Prepare input for typing | `focus_element_humanlike()` |
| Avoid unnecessary scroll | `scroll_element_into_view_if_needed()` |

## Import Statement

```python
from agent.navigation_handlers import (
    prepare_element_for_interaction,  # Most important
    is_element_in_viewport,
    smart_scroll_to_element,
    focus_element_humanlike,
    scroll_to_trigger_lazy_load,
    scroll_until_element_found,
)
```

## Error Handling

All functions are **fail-safe** (never throw exceptions):

```python
# Returns False on failure, never raises
ready = await prepare_element_for_interaction(page, ".invalid")
# ready == False

# Check result
if ready:
    # Safe to interact
    await page.click(selector)
else:
    # Handle failure
    logger.warning("Element not ready")
```

## Testing

```bash
python3 test_smart_scrolling.py
```

## Full Documentation

- **Guide:** `/mnt/c/ev29/agent/SMART_SCROLLING_GUIDE.md`
- **Summary:** `/mnt/c/ev29/SMART_SCROLLING_SUMMARY.md`
- **Code:** `/mnt/c/ev29/agent/navigation_handlers.py`

