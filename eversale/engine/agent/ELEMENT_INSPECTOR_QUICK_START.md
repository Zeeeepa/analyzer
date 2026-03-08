# Element Inspector - Quick Start Guide

## 30-Second Intro

Element Inspector provides deep DOM analysis for robust browser automation. It combines visual targeting (Moondream) with intelligent selector strategies to make your automation self-healing and reliable.

## Installation

No installation needed - already integrated into Eversale!

Dependencies (already installed):
- `playwright`
- `loguru`

## Quick Examples

### 1. Smart Click (Easiest Way)

```python
from agent.smart_selector import SmartSelector

# Initialize
selector = SmartSelector(page)

# Click anything by description
result = await selector.click("Submit button")

if result.success:
    print(f"Clicked via {result.method}")
else:
    print(f"Failed: {result.issues}")
    print(f"Try: {result.suggestions}")
```

### 2. Fill Input Field

```python
result = await selector.fill(
    "Email input",
    "user@example.com",
    humanized=True  # Human-like typing
)
```

### 3. Extract List Items

```python
items = await selector.extract_list("First product card")

for item in items:
    print(f"{item['text']} - {item['href']}")
```

### 4. Deep Inspection

```python
from agent.element_inspector import ElementInspector

inspector = ElementInspector(page)

# Get full element info
snapshot = await inspector.inspect_element('#submit-btn')

print(f"Tag: {snapshot.tag_name}")
print(f"Visible: {snapshot.is_visible}")
print(f"ARIA Label: {snapshot.aria_label}")
print(f"React Component: {snapshot.has_react_fiber}")
```

### 5. Diagnose Why Click Failed

```python
diagnosis = await inspector.diagnose_interaction_failure('#submit-btn')

if not diagnosis['is_interactable']:
    for issue in diagnosis['issues']:
        print(f"Issue: {issue}")

    for suggestion in diagnosis['suggestions']:
        print(f"Try: {suggestion}")
```

### 6. Get Best Selector

```python
snapshot = await inspector.inspect_element('.some-element')
quality = await inspector.analyze_selector_quality(snapshot)

print(f"Use this: {quality.recommended_selector}")
print(f"Confidence: {quality.confidence:.0%}")
print(f"Strategy: {quality.strategy}")
```

### 7. Check If Element Is Dynamic (React/Vue)

```python
dynamic = await inspector.is_element_dynamic('#loading-spinner')

if dynamic.is_dynamic:
    print(f"Changes {dynamic.change_frequency}")
    print(f"Use stable selector: {dynamic.recommended_stable_selector}")
```

### 8. Comprehensive Report

```python
from agent.element_inspector import inspect_and_report

await inspect_and_report(page, '#submit-btn')
# Prints detailed report with all info
```

## Key Methods

### SmartSelector (High-Level API)

| Method | Purpose | Example |
|--------|---------|---------|
| `click(description)` | Click element by description | `await selector.click("Submit button")` |
| `fill(description, text)` | Fill input field | `await selector.fill("Email", "test@test.com")` |
| `extract_list(description)` | Get all list items | `await selector.extract_list("First item")` |
| `wait_for_element(description)` | Wait for element to appear | `await selector.wait_for_element("Success msg")` |
| `get_element_text(description)` | Get text content | `text = await selector.get_element_text("Title")` |

### ElementInspector (Low-Level API)

| Method | Purpose | Example |
|--------|---------|---------|
| `inspect_element(selector)` | Get full element snapshot | `snapshot = await inspector.inspect_element('#btn')` |
| `analyze_selector_quality(snapshot)` | Get best selector | `quality = await inspector.analyze_selector_quality(snapshot)` |
| `is_element_dynamic(selector)` | Check if element changes | `dynamic = await inspector.is_element_dynamic('#el')` |
| `diagnose_interaction_failure(selector)` | Diagnose issues | `diag = await inspector.diagnose_interaction_failure('#btn')` |
| `get_element_ancestry(selector)` | Get parent elements | `parents = await inspector.get_element_ancestry('#el')` |
| `get_similar_siblings(selector)` | Find similar elements | `siblings = await inspector.get_similar_siblings('li:first')` |

## Common Patterns

### Pattern: Robust Click with Auto-Retry

```python
selector = SmartSelector(page)

# Try visual first, falls back to selectors, auto-scrolls, waits
result = await selector.click(
    description="Submit button",
    context="Login form",
    fallback_selectors=['#submit', 'button[type="submit"]']
)
```

### Pattern: Extract All Products

```python
products = await selector.extract_list("First product card", max_items=50)

for product in products:
    print(f"Product {product['index']}: {product['text']}")
    print(f"  Link: {product['href']}")
```

### Pattern: Smart Wait

```python
# Wait up to 10 seconds for element
result = await selector.wait_for_element("Success message", timeout=10.0)

if result.success:
    text = await selector.get_element_text("Success message")
    print(f"Success: {text}")
```

### Pattern: Validate Before Interaction

```python
inspector = ElementInspector(page)

# Check element before clicking
diagnosis = await inspector.diagnose_interaction_failure('#risky-button')

if diagnosis['is_interactable']:
    await page.click('#risky-button')
else:
    print("Not safe to click:", diagnosis['issues'])
```

## What Makes It Smart?

1. **Visual Targeting**: Uses Moondream vision model to find elements by appearance
2. **Selector Strategies**: Tries 7 different selector types (ID, ARIA, data-testid, text, class, structure, XPath)
3. **Stability Detection**: Identifies unstable IDs/classes (CSS-in-JS, timestamps)
4. **Auto-Fixes**: Scrolls into view, waits for visible/enabled
5. **Framework Aware**: Detects React/Vue/Angular components
6. **Self-Healing**: If selector breaks, recommends alternatives
7. **Detailed Diagnostics**: Explains why interactions fail

## Selector Preference Order

The inspector chooses selectors in this order (most stable first):

1. **Stable ID** - `#submit-btn` (if ID doesn't look random)
2. **ARIA Label** - `[aria-label="Submit"]` (accessibility-first)
3. **data-testid** - `[data-testid="submit-button"]` (designed for testing)
4. **Text Content** - `button:has-text("Submit")` (for buttons/links)
5. **Stable Classes** - `.submit-button` (not CSS-in-JS)
6. **Structure** - `form > button:nth-child(2)` (position-based)
7. **XPath** - `//button[contains(text(), "Submit")]` (fallback)

## Performance

| Operation | Time | Notes |
|-----------|------|-------|
| Smart click (visual) | ~600ms | Includes screenshot + vision model |
| Smart click (selector) | ~100ms | Fast DOM query |
| Element inspection | ~50ms | Single evaluate() call |
| Selector quality analysis | ~10ms | Pure Python, no DOM access |
| Dynamic detection | ~2s | Configurable observation period |

## Troubleshooting

### Issue: "Element not found"

```python
# Get diagnostics
diagnosis = await inspector.diagnose_interaction_failure(selector)
print(diagnosis['reason'])
print(diagnosis['suggestions'])
```

### Issue: Visual targeting slow

```python
# Force selector-only mode
selector = SmartSelector(page, prefer_visual=False)
```

### Issue: Selectors keep breaking

```python
# Find most stable selector
snapshot = await inspector.inspect_element(selector)
quality = await inspector.analyze_selector_quality(snapshot)

print(f"Use this instead: {quality.recommended_selector}")
print(f"Warnings: {quality.warnings}")
```

## Testing

```bash
# Run tests
pytest agent/test_element_inspector.py -v

# Run examples
python agent/element_inspector_example.py
```

## Full Documentation

- **README**: `agent/ELEMENT_INSPECTOR_README.md` - Complete documentation
- **Integration**: `agent/ELEMENT_INSPECTOR_INTEGRATION.md` - Integration guide
- **Examples**: `agent/element_inspector_example.py` - 10 usage examples
- **Tests**: `agent/test_element_inspector.py` - Full test suite

## Need Help?

1. Check examples: `agent/element_inspector_example.py`
2. Read full README: `agent/ELEMENT_INSPECTOR_README.md`
3. Run tests to see it working: `pytest agent/test_element_inspector.py -v`
4. Use `diagnose_interaction_failure()` for detailed diagnostics

## Next Steps

1. Try the examples: `python agent/element_inspector_example.py`
2. Integrate into ReAct loop: See `ELEMENT_INSPECTOR_INTEGRATION.md`
3. Replace old `page.click()` calls with `selector.click()`
4. Add element inspection to failed interactions for debugging

---

**Quick Wins:**

- Replace fragile CSS selectors with `SmartSelector.click(description)`
- Use `diagnose_interaction_failure()` when automation fails
- Extract lists with `extract_list()` instead of manual loops
- Get stable selectors with `analyze_selector_quality()`
