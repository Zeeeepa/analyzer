# Smart Scrolling and Focus Management Guide

## Overview

The `navigation_handlers.py` module now includes comprehensive smart scrolling and focus management features that ensure target elements are always visible and properly focused before interaction. This eliminates common issues like:

- Clicking on elements outside the viewport
- Interactions blocked by fixed headers
- Missing elements due to lazy loading
- Failed interactions on infinite-scroll pages

## Key Features

### 1. Fixed Header Detection

Automatically detects fixed/sticky headers at the top of the page and accounts for them when scrolling.

```python
from agent.navigation_handlers import get_fixed_header_height

header_height = await get_fixed_header_height(page)
print(f"Fixed header: {header_height}px")
```

**How it works:**
- Searches for common header selectors: `header`, `nav`, `[class*="header"]`, etc.
- Checks if elements have `position: fixed` or `position: sticky`
- Only counts headers at the top of the page (`rect.top === 0`)
- Returns the maximum height to account for multiple headers

### 2. Element Visibility Checking

Check if an element is currently visible in the viewport.

```python
from agent.navigation_handlers import is_element_in_viewport

visibility = await is_element_in_viewport(page, ".submit-button")

if visibility['visible']:
    print("Element is fully visible")
elif visibility['partiallyVisible']:
    print("Element is partially visible")
else:
    print(f"Element not visible: {visibility['reason']}")
```

**Returns:**
```python
{
    'visible': bool,           # Fully in viewport
    'partiallyVisible': bool,  # At least partially visible
    'rect': {                  # Element position and size
        'top': float,
        'left': float,
        'bottom': float,
        'right': float,
        'width': float,
        'height': float
    },
    'viewport': {              # Viewport dimensions
        'width': int,
        'height': int
    },
    'reason': str             # 'ok', 'partially_visible', 'out_of_viewport', 'not_found'
}
```

### 3. Smart Scroll to Element

Intelligently scroll an element into view with optimal positioning.

```python
from agent.navigation_handlers import smart_scroll_to_element

success = await smart_scroll_to_element(
    page,
    selector=".important-button",
    padding=100,        # Extra padding from viewport edges
    behavior="smooth"   # 'smooth' or 'auto'
)
```

**Features:**
- Centers element vertically in viewport
- Accounts for fixed headers automatically
- Smooth scrolling for natural appearance
- Verifies element is visible after scrolling

**Best for:**
- Scrolling to specific sections
- Bringing buttons/forms into view
- Preparing elements for interaction

### 4. Human-Like Element Focus

Focus an element with realistic human-like mouse movement and pauses.

```python
from agent.navigation_handlers import focus_element_humanlike

success = await focus_element_humanlike(page, "#email-input")
```

**Behavior sequence:**
1. Move mouse near element (with slight randomness)
2. Pause briefly
3. Move to element center
4. Pause again
5. Hover over element
6. Focus the element

**Timing:**
- Random pauses: 50-150ms between steps
- Natural mouse movement with randomized offset

### 5. Lazy Load Scrolling

Scroll down progressively to trigger lazy loading and find elements.

```python
from agent.navigation_handlers import scroll_to_trigger_lazy_load

found = await scroll_to_trigger_lazy_load(
    page,
    target_selector=".product-card:nth-child(50)",
    max_scrolls=10  # Maximum scroll attempts
)
```

**How it works:**
- Scrolls down 80% of viewport height each iteration
- Waits 500ms after each scroll for content to load
- Checks if target element exists after each scroll
- Stops early if element found or page bottom reached

**Best for:**
- Finding elements in lazy-loaded content
- Infinite scroll pages
- Dynamic content loading

### 6. Infinite Scroll Handling

Continue scrolling until element found or maximum reached.

```python
from agent.navigation_handlers import scroll_until_element_found

found = await scroll_until_element_found(
    page,
    selector=".load-more-button",
    max_scrolls=20,
    scroll_pause=0.5
)
```

**Features:**
- Detects when page bottom is reached
- Configurable scroll pause for slow-loading pages
- Tracks scroll position to avoid infinite loops

**Best for:**
- Finding buttons at the bottom of long pages
- Social media feeds
- News/blog infinite scroll

### 7. Scroll If Needed (Convenience)

Check visibility and scroll only if needed.

```python
from agent.navigation_handlers import scroll_element_into_view_if_needed

success = await scroll_element_into_view_if_needed(page, ".footer-link")
```

**Logic:**
- Checks if element is already visible
- If visible: returns True immediately (no scroll)
- If not visible: scrolls element into view
- Returns True if element is now visible

### 8. Prepare Element for Interaction (All-in-One)

**The main function you should use** - combines all features for reliable interaction.

```python
from agent.navigation_handlers import prepare_element_for_interaction

ready = await prepare_element_for_interaction(page, ".submit-button")

if ready:
    # Element is now visible, focused, and ready to click
    await page.click(".submit-button")
```

**What it does:**
1. Verifies element exists
2. Scrolls into view if needed (accounting for fixed headers)
3. Focuses element with human-like behavior
4. Verifies element is visible (fully or partially)

**Returns:** `True` if element is ready for interaction, `False` otherwise

## Usage Examples

### Example 1: Safe Form Submission

```python
from agent.navigation_handlers import prepare_element_for_interaction

# Fill form fields
await page.fill("#email", "user@example.com")
await page.fill("#password", "password123")

# Prepare submit button (scroll + focus)
ready = await prepare_element_for_interaction(page, "#submit-btn")

if ready:
    await page.click("#submit-btn")
    print("Form submitted successfully")
else:
    print("Submit button not ready for interaction")
```

### Example 2: Finding Lazy-Loaded Products

```python
from agent.navigation_handlers import scroll_to_trigger_lazy_load

# Scroll to trigger lazy loading of product 100
found = await scroll_to_trigger_lazy_load(
    page,
    target_selector="[data-product-id='100']",
    max_scrolls=15
)

if found:
    # Product is now loaded, extract data
    product = await page.query_selector("[data-product-id='100']")
    name = await product.query_selector(".product-name").text_content()
    print(f"Found: {name}")
```

### Example 3: Handling Fixed Headers

```python
from agent.navigation_handlers import (
    get_fixed_header_height,
    smart_scroll_to_element
)

# Detect header height
header_height = await get_fixed_header_height(page)
print(f"Accounting for {header_height}px fixed header")

# Scroll to section (automatically accounts for header)
await smart_scroll_to_element(page, "#contact-section")
```

### Example 4: Infinite Scroll Social Feed

```python
from agent.navigation_handlers import scroll_until_element_found

# Scroll through feed to find specific post
found = await scroll_until_element_found(
    page,
    selector="[data-post-id='12345']",
    max_scrolls=50,
    scroll_pause=0.8  # Longer pause for slow network
)

if found:
    print("Found post in feed")
```

### Example 5: Check Visibility Before Action

```python
from agent.navigation_handlers import is_element_in_viewport

# Check if element is visible
visibility = await is_element_in_viewport(page, ".modal-close")

if visibility['visible']:
    # Element is fully visible, click directly
    await page.click(".modal-close")
elif visibility['partiallyVisible']:
    # Partially visible, might still work
    try:
        await page.click(".modal-close")
    except:
        # Scroll into full view
        await smart_scroll_to_element(page, ".modal-close")
        await page.click(".modal-close")
else:
    # Not visible at all
    print(f"Element not visible: {visibility['reason']}")
```

## Integration with NavigationHandlersMixin

The `NavigationHandlersMixin` class can use these functions internally. For example:

```python
class NavigationHandlersMixin:
    async def _try_click_through(self, prompt: str):
        # ... existing code ...

        # Before clicking, prepare the element
        page = self.browser.page
        from agent.navigation_handlers import prepare_element_for_interaction

        ready = await prepare_element_for_interaction(page, selector)
        if ready:
            click_result = await self._call_direct_tool("playwright_click", {"selector": selector})
        else:
            logger.warning(f"Element not ready: {selector}")
```

## Best Practices

### 1. Always Use `prepare_element_for_interaction` Before Clicks

```python
# DON'T do this:
await page.click(".button")  # Might fail if not visible

# DO this:
ready = await prepare_element_for_interaction(page, ".button")
if ready:
    await page.click(".button")
```

### 2. Use Appropriate Timeouts for Lazy Loading

```python
# Fast-loading page
await scroll_to_trigger_lazy_load(page, selector, max_scrolls=5)

# Slow network / heavy content
await scroll_to_trigger_lazy_load(page, selector, max_scrolls=20)
```

### 3. Check Visibility Before Deciding Action

```python
visibility = await is_element_in_viewport(page, selector)

if visibility['visible']:
    # Direct interaction
    await page.click(selector)
elif visibility['partiallyVisible']:
    # Might work, try with fallback
    try:
        await page.click(selector)
    except:
        await prepare_element_for_interaction(page, selector)
        await page.click(selector)
else:
    # Need to scroll/search
    await scroll_until_element_found(page, selector)
```

### 4. Combine with Humanization Features

```python
from agent.humanization import BezierCursor, HumanTyper

# Prepare element
await prepare_element_for_interaction(page, "#input")

# Type with human-like behavior
typer = HumanTyper()
await typer.type_text(page, "Hello world", selector="#input")

# Click with Bezier curve
cursor = BezierCursor()
await cursor.click_at(page, selector=".submit")
```

## Performance Considerations

### Function Speed

| Function | Typical Duration | Notes |
|----------|-----------------|-------|
| `get_fixed_header_height()` | <50ms | Fast DOM query |
| `is_element_in_viewport()` | <50ms | Fast visibility check |
| `smart_scroll_to_element()` | 200-500ms | Depends on scroll behavior |
| `focus_element_humanlike()` | 200-400ms | Includes random pauses |
| `scroll_to_trigger_lazy_load()` | 500ms-10s | Depends on max_scrolls |
| `scroll_until_element_found()` | 1s-30s | Depends on max_scrolls |
| `prepare_element_for_interaction()` | 500ms-1s | Combines multiple steps |

### Optimization Tips

1. **Use visibility checks first** to avoid unnecessary scrolling:
   ```python
   vis = await is_element_in_viewport(page, selector)
   if not vis['visible']:
       await smart_scroll_to_element(page, selector)
   ```

2. **Set reasonable max_scrolls** to avoid long waits:
   ```python
   # Don't do this:
   await scroll_until_element_found(page, selector, max_scrolls=1000)

   # Do this:
   await scroll_until_element_found(page, selector, max_scrolls=20)
   ```

3. **Use `behavior="auto"` for faster scrolling** when speed matters:
   ```python
   await smart_scroll_to_element(page, selector, behavior="auto")  # Instant
   ```

## Error Handling

All functions are designed to fail gracefully:

```python
# Example: smart_scroll_to_element
try:
    success = await smart_scroll_to_element(page, ".button")
    if success:
        print("Scrolled successfully")
    else:
        print("Element not found or scroll failed")
except Exception as e:
    print(f"Unexpected error: {e}")
```

Functions return:
- `True/False` for success/failure
- `Dict` with detailed info (visibility checks)
- Never raise exceptions (all caught internally)

## Testing

Run the test suite:

```bash
python test_smart_scrolling.py
```

This will test:
1. Fixed header detection
2. Viewport visibility checks
3. Smart scrolling
4. Human-like focus
5. Element preparation
6. Lazy load scrolling

## Troubleshooting

### Element Not Found After Scrolling

**Problem:** `scroll_until_element_found()` returns `False`

**Solutions:**
- Increase `max_scrolls`
- Increase `scroll_pause` for slow-loading content
- Check selector is correct
- Element might not exist on page

### Element Not Visible After `smart_scroll_to_element()`

**Problem:** Element scrolled but still not visible

**Solutions:**
- Fixed header might be blocking it - check `get_fixed_header_height()`
- Element might be in a scrollable container (not main page)
- Element might have `display: none` or `visibility: hidden`

### Focus Fails on Element

**Problem:** `focus_element_humanlike()` returns `False`

**Solutions:**
- Element might not be focusable (e.g., `<div>` without `tabindex`)
- Element might be disabled
- Try scrolling into view first

## API Reference

### Function Signatures

```python
async def get_fixed_header_height(page) -> int

async def is_element_in_viewport(page, selector: str) -> Dict

async def smart_scroll_to_element(
    page,
    selector: str,
    padding: int = 100,
    behavior: str = "smooth"
) -> bool

async def focus_element_humanlike(page, selector: str) -> bool

async def scroll_to_trigger_lazy_load(
    page,
    target_selector: str,
    max_scrolls: int = 10
) -> bool

async def scroll_until_element_found(
    page,
    selector: str,
    max_scrolls: int = 20,
    scroll_pause: float = 0.5
) -> bool

async def scroll_element_into_view_if_needed(page, selector: str) -> bool

async def prepare_element_for_interaction(page, selector: str) -> bool
```

## See Also

- `agent/humanization/bezier_cursor.py` - Human-like mouse movement
- `agent/humanization/human_typer.py` - Human-like typing
- `agent/humanization/continuous_perception.py` - Visual awareness
- `agent/selector_fallbacks.py` - Self-healing selectors
