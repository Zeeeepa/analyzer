# Comprehensive Selector Fallback System

## Overview

The enhanced `selector_fallbacks.py` module provides a **NEVER-FAIL** element finding system with 8 fallback strategies. When a primary selector fails, the system automatically tries alternative methods until the element is found or all options are exhausted.

**Goal**: NEVER fail to find an element - always have a fallback path.

## Fallback Chain

```
1. Cached Selector (from site memory)
       ↓ (if fails)
2. Primary CSS Selector
       ↓ (if fails)
3. CSS Selector Variants (id, aria-label, data-testid)
       ↓ (if fails)
4. XPath Fallbacks (text content, structural)
       ↓ (if fails)
5. Fuzzy Text Matching (partial match, case-insensitive)
       ↓ (if fails)
6. Vision-Based Location (screenshot + LLM)
       ↓ (if fails)
7. DOM Exploration (find similar elements)
       ↓ (if fails)
8. Human Assistance Request
```

## Quick Start

### Basic Usage

```python
from selector_fallbacks import find_with_fallbacks, FallbackResult

# Simple element search with comprehensive fallbacks
result: FallbackResult = await find_with_fallbacks(
    page=page,
    primary_selector="#submit-btn",  # Try this first
    description="Submit",            # Fallback description
    element_type="button"
)

if result.found:
    # Click the element
    if result.element:
        await result.element.click()
    elif result.coordinates:
        x, y = result.coordinates
        await page.mouse.click(x, y)

    print(f"Found via: {result.method}")
    print(f"Confidence: {result.confidence}")
else:
    print(f"Not found: {result.error}")
```

### With Rich Context

```python
# Provide context to improve success rate
result = await find_with_fallbacks(
    page=page,
    primary_selector=".login-button",
    description="Login",
    context={
        "aria_label": "Log in to your account",
        "role": "button",
        "data_testid": "login-btn",
        "text": "Log In",
        "type": "submit",
        "near": "form"  # Element is near a form
    },
    element_type="button"
)
```

## Features

### 1. Selector Variant Generator

Generates comprehensive alternative selectors from an original.

**Example:**

If `#submit-btn` fails, the system tries:
- `[id='submit-btn']`
- `[id*='submit-btn']` (partial match)
- `//*[@id='submit-btn']` (XPath)
- `button[id='submit-btn']`
- `form button:last-child` (structural)
- `form input[type='submit']`

```python
from selector_fallbacks import generate_selector_variants

variants = generate_selector_variants(
    "#submit-btn",
    context={
        "aria_label": "Submit",
        "data_testid": "submit",
        "role": "button"
    }
)

# Returns: ['[id='submit-btn']', 'button[id='submit-btn']', ...]
```

### 2. Fuzzy Text Matcher

Finds elements containing similar text using `difflib.SequenceMatcher`.

**Example:**

```python
from selector_fallbacks import find_by_fuzzy_text

# Find element with ~80% text similarity
result = await find_by_fuzzy_text(
    page=page,
    target_text="Submitt Form",  # Typo
    threshold=0.8,               # 80% similarity required
    element_type="button"
)

if result:
    print(f"Matched: '{result['matched_text']}'")  # "Submit Form"
    print(f"Similarity: {result['similarity']}")   # 0.92
    print(f"Selector: {result['selector']}")
```

**How it works:**
- Searches all interactive elements (buttons, links, inputs)
- Tries text content, aria-label, placeholder, value
- Calculates similarity score (0.0 to 1.0)
- Returns best match above threshold

### 3. Vision-Based Fallback

Uses vision models to locate elements by description.

**Example:**

```python
result = await find_with_fallbacks(
    page=page,
    description="the blue Login button in the top right",
    element_type="button"
)

# Vision model analyzes screenshot and finds element
# Returns coordinates or synthesizes selector
```

**How it works:**
- Takes screenshot of page
- Uses vision model (if available) to locate element
- Returns coordinates for clicking
- Optionally synthesizes stable selector for caching

### 4. DOM Exploration

Explores DOM tree to find elements matching hints.

**Example:**

```python
from selector_fallbacks import explore_dom_for_element

candidates = await explore_dom_for_element(
    page=page,
    hints={
        "tag": "button",
        "text_contains": "submit",
        "near": "form",         # Element is inside or near a form
        "role": "button",
        "aria_label": "Submit",
        "data_testid": "submit-btn",
        "visible": True
    }
)

# Returns ranked candidates with scores
for candidate in candidates:
    print(f"Selector: {candidate['selector']}")
    print(f"Score: {candidate['score']}")
    print(f"Reasons: {candidate['match_reasons']}")
```

**Scoring System:**
- Text match: +30 points
- Aria-label match: +25 points
- Data-testid match: +25 points
- Role match: +20 points
- Proximity match: +15 points

### 5. Site Memory Integration

Successful selectors are cached per domain for future speed.

**How it works:**
1. First time: Tries all fallback strategies (slow)
2. Caches successful selector to `~/.eversale/selector_cache.json`
3. Next time: Uses cached selector first (fast)
4. If cached selector fails: Invalidates and tries fallbacks again (self-healing)

**Cache Structure:**
```json
{
  "example.com": {
    "abc123": {
      "selector": "button#submit",
      "method": "css",
      "element_type": "button",
      "description": "Submit",
      "timestamp": 1704067200,
      "success_count": 5
    }
  }
}
```

### 6. Metrics Tracking

Track which fallback strategies are being used.

```python
from selector_fallbacks import get_fallback_metrics, reset_fallback_metrics

# After some searches
metrics = get_fallback_metrics()

print(f"Total attempts: {metrics['total_attempts']}")
print(f"Success by method:")
for method, count in metrics['by_method'].items():
    if count > 0:
        print(f"  {method}: {count}")

print(f"Sites needing vision: {metrics['sites_needing_vision']}")
print(f"High fallback sites: {metrics['high_fallback_sites']}")

# Reset metrics
reset_fallback_metrics()
```

**Metrics tracked:**
- Total fallback attempts
- Success count per method
- Sites frequently needing vision (indicates missing selectors)
- Sites with high fallback usage (should add to site memory)

## API Reference

### Main Functions

#### `find_with_fallbacks()`

```python
async def find_with_fallbacks(
    page,
    primary_selector: str = None,
    description: str = None,
    context: Dict[str, Any] = None,
    element_type: str = "unknown"
) -> FallbackResult
```

**Parameters:**
- `page`: Playwright page object
- `primary_selector`: Primary CSS/XPath selector to try first
- `description`: Human-readable description for fallback
- `context`: Additional hints (aria-label, role, data-testid, text, etc.)
- `element_type`: Element type hint (button, input, link, etc.)

**Returns:** `FallbackResult` with:
- `found`: bool - Whether element was found
- `selector`: str - Selector that worked
- `method`: str - Which strategy succeeded
- `confidence`: float - Confidence score (0.0 to 1.0)
- `element`: ElementHandle - The found element
- `coordinates`: Tuple[int, int] - Optional coordinates
- `alternatives`: List[str] - Other selectors that might work
- `error`: str - Error message if not found

#### `generate_selector_variants()`

```python
def generate_selector_variants(
    original: str,
    context: Dict = None
) -> List[str]
```

Generate alternative selectors from an original.

#### `find_by_fuzzy_text()`

```python
async def find_by_fuzzy_text(
    page,
    target_text: str,
    threshold: float = 0.8,
    element_type: Optional[str] = None
) -> Optional[Dict[str, Any]]
```

Find element by fuzzy text matching.

#### `explore_dom_for_element()`

```python
async def explore_dom_for_element(
    page,
    hints: Dict[str, Any]
) -> List[Dict[str, Any]]
```

Explore DOM to find elements matching hints.

### Classes

#### `FallbackResult`

```python
@dataclass
class FallbackResult:
    found: bool
    selector: Optional[str] = None
    method: str = "none"
    confidence: float = 0.0
    coordinates: Optional[Tuple[int, int]] = None
    element: Optional[Any] = None
    alternatives: List[str] = field(default_factory=list)
    error: Optional[str] = None
```

#### `SelfHealingSelector`

```python
class SelfHealingSelector:
    def __init__(self, page)

    async def find_element(
        self,
        selector: Optional[str] = None,
        description: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        element_type: str = "unknown"
    ) -> Optional[Dict[str, Any]]

    async def find_and_click(...) -> Dict[str, Any]

    async def find_and_fill(...) -> Dict[str, Any]
```

## Best Practices

### 1. Provide Rich Context

More context = higher success rate.

```python
# ✗ Minimal context
result = await find_with_fallbacks(
    page=page,
    primary_selector="#btn"
)

# ✓ Rich context
result = await find_with_fallbacks(
    page=page,
    primary_selector="#submit-btn",
    description="Submit Form",
    context={
        "aria_label": "Submit your information",
        "role": "button",
        "data_testid": "form-submit",
        "text": "Submit",
        "type": "submit",
        "near": "form.contact-form"
    },
    element_type="button"
)
```

### 2. Use Descriptive Names

Good descriptions help vision and text matching.

```python
# ✗ Vague
description="button"

# ✓ Specific
description="blue Login button in top right corner"
```

### 3. Monitor Metrics

Track which strategies are being used.

```python
# Check metrics periodically
metrics = get_fallback_metrics()

if len(metrics['sites_needing_vision']) > 0:
    print("Warning: These sites frequently need vision:")
    print(metrics['sites_needing_vision'])
    print("→ Consider adding selectors to site memory")
```

### 4. Handle Failures Gracefully

Even with 8 strategies, elements might not be found.

```python
result = await find_with_fallbacks(page, ...)

if result.found:
    # Success
    await result.element.click()
else:
    # Try alternatives or ask user
    print(f"Could not find element: {result.error}")

    if result.alternatives:
        print("Try these selectors manually:")
        for alt in result.alternatives:
            print(f"  - {alt}")
```

### 5. Cache Successful Selectors

When you find a working selector, update site memory.

```python
from selector_fallbacks import SelectorCache

# After manual fix
SelectorCache.set(
    url=page.url,
    element_type="button",
    description="Login",
    selector="button.auth-submit",
    method="manual"
)

# Next time it will use cached selector first
```

## Performance

### Speed by Strategy

| Strategy | Speed | Reliability |
|----------|-------|-------------|
| Cached | **Fastest** (1-5ms) | High (if page unchanged) |
| CSS | Very Fast (5-10ms) | High |
| CSS Variants | Fast (10-50ms) | Medium |
| XPath | Fast (10-50ms) | Medium |
| Fuzzy Text | Medium (50-200ms) | Medium |
| Vision | **Slowest** (1-5s) | High |
| DOM Exploration | Medium (100-500ms) | Medium |

### Optimization Tips

1. **Add selectors to site memory** - Cached lookups are 100x faster
2. **Provide data-testid** - Most reliable attribute selector
3. **Use specific element types** - Narrows search space
4. **Rich context first time** - Increases cache hit rate

## Troubleshooting

### Element not found despite 8 strategies

**Possible causes:**
1. Element doesn't exist on page
2. Element is in iframe (need to switch context)
3. Element loads dynamically (need to wait)
4. Element is hidden/invisible
5. Page hasn't fully loaded

**Solutions:**
```python
# Wait for element to appear
await page.wait_for_selector("some-selector", timeout=5000)

# Check if in iframe
frames = page.frames
for frame in frames:
    result = await find_with_fallbacks(frame, ...)
    if result.found:
        break

# Wait for page load
await page.wait_for_load_state("networkidle")

# Check if visible
element = result.element
is_visible = await element.is_visible()
```

### High fallback usage (not using cache)

**Symptom:** Metrics show many fallback attempts, few cached hits.

**Cause:** Selectors keep changing between visits (dynamic classes, IDs).

**Solution:** Use stable selectors (data-testid, aria-label) or add to site memory.

```python
# Check metrics
metrics = get_fallback_metrics()
if "example.com" in metrics['high_fallback_sites']:
    print("Site has unstable selectors")
    # Add stable selector to memory
    SelectorCache.set(url, element_type, description, stable_selector, "manual")
```

### Vision strategy always needed

**Symptom:** `sites_needing_vision` metric shows certain domains.

**Cause:** Site uses dynamic selectors, no text content, or canvas/WebGL.

**Solution:**
1. Add selectors manually to site memory
2. Use data-testid if you control the site
3. Vision is working correctly - just cache the result

## Examples

See `selector_fallbacks_example.py` for comprehensive examples:

1. Basic fallback usage
2. Rich context usage
3. SelfHealingSelector class
4. Metrics tracking
5. Fuzzy text matching
6. DOM exploration
7. Selector variant generation

## Architecture

```
┌─────────────────────────────────────────────────────┐
│           find_with_fallbacks()                      │
│           (Main Entry Point)                         │
└────────────────┬────────────────────────────────────┘
                 │
    ┌────────────┴──────────────┐
    │  1. Check Selector Cache  │
    │     (site_memory.json)    │
    └────────────┬──────────────┘
                 │ (miss)
    ┌────────────┴──────────────┐
    │  2. Try Primary Selector  │
    └────────────┬──────────────┘
                 │ (fail)
    ┌────────────┴──────────────┐
    │  3. Generate CSS Variants │ ← generate_selector_variants()
    └────────────┬──────────────┘
                 │ (fail)
    ┌────────────┴──────────────┐
    │  4. Try XPath Fallbacks   │ ← css_to_xpath()
    └────────────┬──────────────┘
                 │ (fail)
    ┌────────────┴──────────────┐
    │  5. Fuzzy Text Match      │ ← find_by_fuzzy_text()
    └────────────┬──────────────┘
                 │ (fail)
    ┌────────────┴──────────────┐
    │  6. Vision-Based Search   │ ← VisualFallback
    └────────────┬──────────────┘
                 │ (fail)
    ┌────────────┴──────────────┐
    │  7. DOM Exploration       │ ← explore_dom_for_element()
    └────────────┬──────────────┘
                 │ (fail)
    ┌────────────┴──────────────┐
    │  8. Human Assistance      │
    │     (return error + alts) │
    └───────────────────────────┘
```

## Integration with Eversale

The comprehensive fallback system integrates with:

1. **Site Memory** - Caches successful selectors per domain
2. **Visual Grounding** - Vision-based element location
3. **DOM Distillation** - Simplified DOM representation
4. **Humanization** - Human-like element interaction
5. **Self-Healing System** - Automatic recovery from failures

## Version History

- **v2.0** (2025-12-07): Comprehensive fallback chain with 8 strategies
  - Added fuzzy text matching
  - Added DOM exploration
  - Added selector variant generator
  - Added metrics tracking
  - Added human assistance fallback

- **v1.0** (2024): Initial self-healing selector system
  - Basic fallback strategies
  - Selector caching
  - Visual similarity

## License

Part of Eversale - Autonomous AI Worker
