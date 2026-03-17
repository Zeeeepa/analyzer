# Element Inspector

## Overview

The Element Inspector provides comprehensive DOM element analysis for robust browser automation. It goes beyond basic Playwright selectors to understand element characteristics, stability, and interactability.

## Purpose

Traditional browser automation relies on CSS selectors that can be:
- **Fragile**: Break when classes change (CSS-in-JS)
- **Ambiguous**: Match multiple elements
- **Opaque**: Don't explain why interactions fail

The Element Inspector solves these problems by providing:
1. **Deep element snapshots** with all attributes, styles, and state
2. **Selector quality analysis** to find the most stable selectors
3. **Dynamic element detection** for React/Vue apps
4. **Interaction failure diagnosis** to debug automation issues
5. **Framework awareness** (React Fiber, Vue instances, Angular)

## Key Features

### 1. Comprehensive Element Snapshots

```python
from agent.element_inspector import ElementInspector

inspector = ElementInspector(page)
snapshot = await inspector.inspect_element('#submit-btn')

# Access 40+ properties
print(snapshot.tag_name)           # 'button'
print(snapshot.is_visible)         # True
print(snapshot.aria_label)         # 'Submit form'
print(snapshot.has_react_fiber)    # True (if React component)
print(snapshot.bounding_box)       # {x, y, width, height}
```

**Available Properties:**
- **Basic**: tag_name, id, classes, attributes
- **Text**: inner_text, text_content, value, placeholder
- **Position**: bounding_box, is_in_viewport
- **Visibility**: is_visible, is_displayed, opacity
- **Interactability**: is_enabled, is_readonly, accepts_pointer, is_focusable
- **Accessibility**: role, aria_label, aria_describedby, tabindex
- **Hierarchy**: parent_tag, child_count, sibling_index
- **Styles**: z_index, position, overflow, display
- **Framework**: has_react_fiber, has_vue_instance, has_angular_scope

### 2. Selector Quality Analysis

Automatically recommends the best selector based on stability:

```python
snapshot = await inspector.inspect_element('.some-element')
quality = await inspector.analyze_selector_quality(snapshot)

print(quality.recommended_selector)  # '[aria-label="Submit"]'
print(quality.confidence)            # 0.9 (90% confidence)
print(quality.strategy)              # SelectorStrategy.ARIA_LABEL
print(quality.stability_score)       # 0.85 (85% stable)
print(quality.warnings)              # ["ID looks dynamically generated"]
```

**Selector Strategies (in priority order):**
1. **ID** - If stable (not timestamp/hash)
2. **ARIA Label** - Very stable, accessibility-first
3. **data-testid** - Designed for testing
4. **Text Content** - For buttons/links
5. **Stable Classes** - Not CSS-in-JS
6. **Tag Structure** - Parent > child:nth-child
7. **XPath** - Fallback

**Stability Detection:**
- Detects unstable IDs: `btn-1638234567890` (timestamp), `el-a1b2c3d4` (hash)
- Detects CSS-in-JS: `css-1dbjc4n`, `_3a4bc`
- Flags dynamically generated classes

### 3. Dynamic Element Detection

Monitor elements over time to detect React re-renders, Vue reactivity, etc.:

```python
dynamic = await inspector.is_element_dynamic(
    '#loading-spinner',
    observation_duration=2.0,    # Watch for 2 seconds
    observation_interval=0.4     # Check every 400ms
)

print(dynamic.is_dynamic)                # True
print(dynamic.change_frequency)          # "frequent"
print(dynamic.changed_attributes)        # ['classes', 'attributes', 'inner_text']
print(dynamic.recommended_stable_selector)  # '[aria-label="Loading"]'
```

**Use Cases:**
- Detect loading states
- Find elements that React/Vue re-renders frequently
- Choose stable selectors for dynamic UIs

### 4. Interaction Failure Diagnosis

Understand why clicks, fills, or other interactions fail:

```python
diagnosis = await inspector.diagnose_interaction_failure('#submit-btn')

if not diagnosis['is_interactable']:
    print("Issues:")
    for issue in diagnosis['issues']:
        print(f"  - {issue}")

    print("\nSuggestions:")
    for suggestion in diagnosis['suggestions']:
        print(f"  - {suggestion}")
```

**Example Output:**
```
Issues:
  - Element is not visible
  - Element is outside viewport

Suggestions:
  - Scroll element into view before interacting
  - Wait for element to become visible
```

**Detects:**
- Element not found
- Hidden (display: none, visibility: hidden, opacity: 0)
- Outside viewport
- Disabled or readonly
- Covered by other elements (z-index)
- Unstable selector

### 5. Element Ancestry

Get parent elements for structural selectors:

```python
ancestry = await inspector.get_element_ancestry('#submit-btn', depth=5)

for i, ancestor in enumerate(ancestry):
    print(f"Level {i}: <{ancestor.tag_name}> #{ancestor.id}")
```

**Output:**
```
Level 0: <form> #login-form
Level 1: <div> #form-container
Level 2: <main> #main-content
Level 3: <body>
Level 4: <html>
```

### 6. Sibling Analysis

Find similar elements (useful for lists, grids, repeated components):

```python
siblings = await inspector.get_similar_siblings('li.product:first-child')

print(f"Found {len(siblings)} similar products")

for sib in siblings:
    print(f"  - {sib.inner_text[:30]}")
```

**Use Cases:**
- Extract all items from a list
- Find repeated components
- Batch operations on similar elements

### 7. Comprehensive Report

Generate a detailed inspection report:

```python
from agent.element_inspector import inspect_and_report

await inspect_and_report(page, '#submit-btn')
```

**Sample Output:**
```
================================================================================
ELEMENT INSPECTION REPORT: #submit-btn
================================================================================

Basic Info:
  Tag: <button>
  ID: submit-btn
  Classes: btn, btn-primary
  Text: Submit

Visibility:
  Visible: True
  In Viewport: True
  Opacity: 1.0

Interactability:
  Enabled: True
  Focusable: True
  Editable: False

Accessibility:
  Role: button
  ARIA Label: Submit form

Selector Quality:
  Recommended: #submit-btn
  Confidence: 95%
  Strategy: id
  Stability Score: 90%

Dynamic Analysis:
  Is Dynamic: False
  Change Frequency: stable

Framework Hints:
  - React component detected
```

## Integration with Visual Targeting

Combine element inspection with visual targeting for the best of both worlds:

```python
from agent.visual_targeting import get_visual_targeting
from agent.element_inspector import ElementInspector, enhance_visual_targeting_with_inspection

targeting = get_visual_targeting()
inspector = ElementInspector(page)

# Try visual targeting first
result = await targeting.locate_element(screenshot_b64, "Submit button")

if result.success:
    # Enhance with element inspection
    snapshot = await inspector.inspect_element_at_coordinates(result.coordinates)
    enhanced = enhance_visual_targeting_with_inspection(result, snapshot)

    # Now we have both visual coordinates AND element metadata
    print(f"Visual coords: {enhanced['visual_coordinates']}")
    print(f"ARIA label: {enhanced['aria_label']}")
    print(f"Stable selector: {enhanced['recommended_selector']}")
```

## Usage Patterns

### Pattern 1: Robust Click

```python
async def robust_click(page, description):
    """Click with automatic fallbacks."""
    inspector = ElementInspector(page)

    # Try visual targeting first
    result = await targeting.locate_element(screenshot, description)

    if result.success:
        # Verify element is interactable
        diagnosis = await inspector.diagnose_interaction_failure_at_coords(result.coordinates)

        if diagnosis['is_interactable']:
            await page.mouse.click(*result.coordinates)
        else:
            # Fix issues first
            for suggestion in diagnosis['suggestions']:
                if 'scroll' in suggestion.lower():
                    await page.evaluate('el.scrollIntoView()', el)

    # Fallback to selector
    quality = await inspector.analyze_selector_quality(snapshot)
    await page.click(quality.recommended_selector)
```

### Pattern 2: Smart Selector Generation

```python
async def generate_best_selector(page, element_description):
    """Find the most stable selector for an element."""
    inspector = ElementInspector(page)

    # Multiple strategies
    candidates = [
        f'[aria-label="{element_description}"]',
        f'button:has-text("{element_description}")',
        f'[data-testid*="{element_description.lower()}"]'
    ]

    for selector in candidates:
        snapshot = await inspector.inspect_element(selector)
        if snapshot:
            quality = await inspector.analyze_selector_quality(snapshot)

            if quality.confidence > 0.8:
                return quality.recommended_selector

    return None
```

### Pattern 3: Pre-Interaction Validation

```python
async def safe_fill(page, selector, text):
    """Fill input with validation."""
    inspector = ElementInspector(page)

    # Diagnose first
    diagnosis = await inspector.diagnose_interaction_failure(selector)

    if not diagnosis['found']:
        raise ElementNotFoundError(f"Element not found: {selector}")

    if not diagnosis['is_interactable']:
        # Try to fix issues
        snapshot = diagnosis['snapshot']

        if not snapshot.is_in_viewport:
            await page.locator(selector).scroll_into_view_if_needed()

        if not snapshot.is_enabled:
            raise ElementNotInteractableError("Element is disabled")

    # Now safe to fill
    await page.fill(selector, text)
```

### Pattern 4: List Extraction

```python
async def extract_all_items(page, first_item_selector):
    """Extract all similar items in a list."""
    inspector = ElementInspector(page)

    # Find similar siblings
    siblings = await inspector.get_similar_siblings(first_item_selector)

    items = []

    # Include the first item
    first = await inspector.inspect_element(first_item_selector)
    items.append({
        'text': first.inner_text,
        'id': first.id,
        'position': first.sibling_index
    })

    # Add siblings
    for sibling in siblings:
        items.append({
            'text': sibling.inner_text,
            'id': sibling.id,
            'position': sibling.sibling_index
        })

    return items
```

## Testing

Run the test suite:

```bash
# All tests
pytest agent/test_element_inspector.py -v

# Specific test
pytest agent/test_element_inspector.py::TestElementInspector::test_selector_quality_stable_id -v

# With output
pytest agent/test_element_inspector.py -v -s
```

## Examples

Run the examples:

```bash
# All examples
python agent/element_inspector_example.py

# Individual functions can be called programmatically
```

## Architecture

```
element_inspector.py
├── ElementSnapshot          - Data class for element state
├── SelectorQualityReport    - Selector analysis results
├── DynamicAnalysis          - Dynamic element analysis
├── SelectorStrategy         - Enum of selector types
└── ElementInspector         - Main inspector class
    ├── inspect_element()
    ├── analyze_selector_quality()
    ├── is_element_dynamic()
    ├── diagnose_interaction_failure()
    ├── get_element_ancestry()
    └── get_similar_siblings()
```

## Performance

- **Element inspection**: ~50ms per element
- **Dynamic analysis**: 2s (configurable)
- **Ancestry/siblings**: ~30ms per query
- **Selector quality**: ~10ms (no DOM access needed)

**Optimization tips:**
- Cache snapshots if inspecting same element multiple times
- Use shorter observation durations for dynamic analysis when possible
- Batch sibling analysis instead of inspecting individually

## Limitations

1. **Event Listeners**: CDP required to inspect event listeners (not yet implemented)
2. **Shadow DOM**: Doesn't traverse into shadow roots (can be added)
3. **Iframes**: Requires switching context first
4. **Cross-origin**: Limited by browser security policies

## Future Enhancements

- [ ] Event listener extraction via CDP
- [ ] Shadow DOM traversal
- [ ] Iframe auto-detection
- [ ] Screenshot-based element matching
- [ ] Machine learning selector prediction
- [ ] Automatic repair for broken selectors
- [ ] Selector diff between page versions

## Related Modules

- **visual_targeting.py**: Pixel-perfect clicking via Moondream vision model
- **humanization/bezier_cursor.py**: Human-like mouse movements
- **stealth_enhanced.py**: Anti-detection for browser automation
- **browser_manager.py**: Browser lifecycle management

## References

- [Playwright Selectors](https://playwright.dev/docs/selectors)
- [ARIA Best Practices](https://www.w3.org/WAI/ARIA/apg/)
- [CSS-in-JS Detection](https://github.com/styled-components/styled-components)
- [React Fiber Architecture](https://github.com/acdlite/react-fiber-architecture)
