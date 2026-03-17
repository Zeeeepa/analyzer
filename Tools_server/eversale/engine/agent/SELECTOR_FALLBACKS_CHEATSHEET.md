# Selector Fallbacks Cheatsheet

Quick reference for the comprehensive selector fallback system.

## One-Liner Examples

### Basic Usage
```python
from selector_fallbacks import find_with_fallbacks

# Simplest usage
result = await find_with_fallbacks(page, "#submit", "Submit", element_type="button")
if result.found:
    await result.element.click()
```

### With Context
```python
# Maximum success rate
result = await find_with_fallbacks(
    page, ".btn", "Login",
    context={"aria_label": "Login", "role": "button", "text": "Login"},
    element_type="button"
)
```

### Fuzzy Text
```python
from selector_fallbacks import find_by_fuzzy_text

# Handles typos
result = await find_by_fuzzy_text(page, "Submitt", threshold=0.8)
```

### DOM Exploration
```python
from selector_fallbacks import explore_dom_for_element

# Find by hints
candidates = await explore_dom_for_element(page, {
    "tag": "button", "text_contains": "login", "visible": True
})
```

### Selector Variants
```python
from selector_fallbacks import generate_selector_variants

# Generate alternatives
variants = generate_selector_variants("#submit-btn")
# Returns: ['[id="submit-btn"]', 'button#submit-btn', ...]
```

### Metrics
```python
from selector_fallbacks import get_fallback_metrics

# Track performance
metrics = get_fallback_metrics()
print(f"Cache hits: {metrics['by_method']['cached']}")
```

## Fallback Chain

```
1. Cached     → Fastest (1-5ms)
2. CSS        → Very Fast (5-10ms)
3. Variants   → Fast (10-50ms)
4. XPath      → Fast (10-50ms)
5. Fuzzy Text → Medium (50-200ms)
6. Vision     → Slow (1-5s) but reliable
7. DOM        → Medium (100-500ms)
8. Human Help → Returns helpful error
```

## FallbackResult Fields

```python
result.found         # bool: Was element found?
result.selector      # str: Selector that worked
result.method        # str: Strategy used
result.confidence    # float: 0.0 to 1.0
result.element       # ElementHandle: The element
result.coordinates   # tuple: (x, y) for clicking
result.alternatives  # list: Other selectors to try
result.error         # str: Error message if failed
```

## Context Dictionary

```python
context = {
    "aria_label": "Submit form",     # Aria label
    "role": "button",                 # ARIA role
    "data_testid": "submit-btn",     # Test ID
    "text": "Submit",                 # Text content
    "placeholder": "Email",           # For inputs
    "name": "email",                  # Name attribute
    "type": "submit",                 # Type attribute
    "near": "form"                    # CSS selector for nearby element
}
```

## Common Patterns

### Click with Fallback
```python
result = await find_with_fallbacks(page, "#btn", "Click Me", element_type="button")
if result.found:
    if result.element:
        await result.element.click()
    elif result.coordinates:
        await page.mouse.click(*result.coordinates)
```

### Fill with Fallback
```python
from selector_fallbacks import SelfHealingSelector

healer = SelfHealingSelector(page)
result = await healer.find_and_fill(
    "#email", "test@example.com",
    description="email", element_type="input"
)
```

### Add to Cache
```python
from selector_fallbacks import SelectorCache

SelectorCache.set(
    url=page.url,
    element_type="button",
    description="Login",
    selector="button[data-testid='login']",
    method="manual"
)
```

### Check Metrics
```python
metrics = get_fallback_metrics()

# High fallback usage?
if len(metrics['high_fallback_sites']) > 0:
    print(f"Add selectors for: {metrics['high_fallback_sites']}")

# Sites needing vision?
if len(metrics['sites_needing_vision']) > 0:
    print(f"Dynamic selectors on: {metrics['sites_needing_vision']}")

# Cache hit rate
cache_rate = metrics['by_method']['cached'] / metrics['total_attempts']
print(f"Cache hit rate: {cache_rate:.1%}")
```

## Troubleshooting

### Element Not Found
```python
result = await find_with_fallbacks(page, "#btn", "Submit")

if not result.found:
    print(f"Error: {result.error}")
    print("Try these selectors:")
    for alt in result.alternatives[:5]:
        print(f"  {alt}")
```

### Wait for Element
```python
# Wait before searching
await page.wait_for_load_state("networkidle")
result = await find_with_fallbacks(page, "#btn", "Submit")
```

### Check if in Iframe
```python
# Search all frames
for frame in page.frames:
    result = await find_with_fallbacks(frame, "#btn", "Submit")
    if result.found:
        break
```

## Performance Tips

1. **Provide rich context** → Higher success rate
2. **Use data-testid** → Most stable attribute
3. **Add to site memory** → 100x faster subsequent visits
4. **Monitor metrics** → Identify problematic sites
5. **Specific element types** → Narrows search space

## Import Shortcuts

```python
from selector_fallbacks import (
    find_with_fallbacks,           # Main entry point
    FallbackResult,                 # Result type
    SelfHealingSelector,            # Class-based usage
    find_by_fuzzy_text,            # Fuzzy matching
    explore_dom_for_element,       # DOM search
    generate_selector_variants,    # Generate alternatives
    get_fallback_metrics,          # Track performance
    SelectorCache,                 # Cache management
)
```

## Files

- **Code:** `/mnt/c/ev29/agent/selector_fallbacks.py`
- **Guide:** `/mnt/c/ev29/agent/SELECTOR_FALLBACKS_GUIDE.md`
- **Examples:** `/mnt/c/ev29/agent/selector_fallbacks_example.py`
- **Summary:** `/mnt/c/ev29/agent/SELECTOR_FALLBACKS_SUMMARY.md`
- **Cheatsheet:** `/mnt/c/ev29/agent/SELECTOR_FALLBACKS_CHEATSHEET.md`

