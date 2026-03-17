# Visual Grounding Quick Start Guide

## 5-Minute Setup

### 1. Install Vision Model

```bash
# Install Ollama (if not already installed)
curl -fsSL https://ollama.com/install.sh | sh

# Pull vision model
ollama pull minicpm-v
```

### 2. Basic Usage

```python
from playwright.async_api import async_playwright
from visual_grounding import ground_and_click, ground_and_fill

async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await browser.new_page()

    await page.goto("https://example.com")

    # Click an element
    await ground_and_click(page, "the login button")

    # Fill an input
    await ground_and_fill(page, "the email input", "user@example.com")

    await browser.close()
```

## Common Patterns

### Pattern 1: Smart Click (Selector + Visual Fallback)

```python
from visual_grounding import VisualGroundingEngine

engine = VisualGroundingEngine()

# Try selector first, fallback to vision
async def smart_click(page, selector=None, description=None):
    if selector:
        try:
            await page.click(selector, timeout=3000)
            return True
        except:
            pass

    if description:
        result = await engine.ground_element(page, description)
        if result.success:
            return await engine.click_grounded_element(page, result.best_match)

    return False

# Usage
await smart_click(page, "button.submit", "the Submit button")
```

### Pattern 2: Form Filling

```python
from visual_grounding import VisualGroundingEngine, ElementType

engine = VisualGroundingEngine()

async def fill_form(page, form_data):
    """
    form_data = {
        "email input": "user@example.com",
        "password input": "password123"
    }
    """
    for field_desc, value in form_data.items():
        result = await engine.ground_element(
            page,
            field_desc,
            element_type=ElementType.INPUT
        )
        if result.success:
            await engine.fill_grounded_element(
                page,
                result.best_match,
                value
            )
```

### Pattern 3: Canvas Interaction

```python
from visual_grounding import VisualGroundingEngine

engine = VisualGroundingEngine()

# Find and click element in canvas
element = await engine.ground_canvas_element(
    page,
    "the red circle tool",
    canvas_selector="canvas#drawing"
)

if element:
    await engine.click_grounded_element(page, element)
```

## Strategies Cheat Sheet

| Strategy | Speed | Accuracy | Use When |
|----------|-------|----------|----------|
| `DOM_ONLY` | ⚡⚡⚡ | ⭐⭐⭐ | Standard HTML elements |
| `VISION_ONLY` | ⚡ | ⭐⭐⭐ | Canvas/non-DOM elements |
| `HYBRID` | ⚡⚡ | ⭐⭐⭐⭐ | General purpose (default) |
| `COORDINATED` | ⚡ | ⭐⭐⭐⭐⭐ | Critical actions |
| `REGION_FOCUS` | ⚡ | ⭐⭐⭐⭐ | Complex/cluttered pages |

## Examples by Use Case

### Use Case: Login Form

```python
from visual_grounding import ground_and_fill, ground_and_click

# Fill credentials
await ground_and_fill(page, "email input", "user@example.com")
await ground_and_fill(page, "password input", "password123")

# Click login
await ground_and_click(page, "the login button")
```

### Use Case: Search

```python
from visual_grounding import VisualGroundingEngine, GroundingStrategy

engine = VisualGroundingEngine()

# Find search box
result = await engine.ground_element(
    page,
    "the search input",
    strategy=GroundingStrategy.HYBRID
)

if result.success:
    await engine.fill_grounded_element(
        page,
        result.best_match,
        "search query"
    )

    # Click search button
    search_result = await engine.ground_element(
        page,
        "the search button"
    )
    if search_result.success:
        await engine.click_grounded_element(page, search_result.best_match)
```

### Use Case: Extract Text

```python
from visual_grounding import ground_and_extract_text

# Extract error message
error_text = await ground_and_extract_text(page, "the error message")
print(f"Error: {error_text}")

# Extract status
status = await ground_and_extract_text(page, "the status indicator")
print(f"Status: {status}")
```

### Use Case: Multiple Elements

```python
from visual_grounding import VisualGroundingEngine

engine = VisualGroundingEngine()

# Find all form fields at once
fields = await engine.ground_multiple_elements(
    page,
    [
        "email input",
        "password input",
        "confirm password input",
        "submit button"
    ]
)

# Check what was found
for desc, result in fields.items():
    if result.success:
        print(f"✓ Found: {desc} (confidence: {result.best_match.confidence:.2f})")
    else:
        print(f"✗ Missing: {desc}")
```

## Debugging

### Check Confidence Scores

```python
result = await engine.ground_element(page, "some element")

if result.success:
    print(f"Confidence: {result.best_match.confidence:.2f}")
    print(f"Method: {result.best_match.match_method.value}")

    if result.best_match.confidence < 0.7:
        print("⚠️ Low confidence - consider alternative description")
```

### View Statistics

```python
from visual_grounding import get_engine

engine = get_engine()

# After some operations...
stats = engine.get_stats()

print(f"Total: {stats['total_groundings']}")
print(f"DOM: {stats['dom_successes']}")
print(f"Vision: {stats['vision_successes']}")
print(f"Avg confidence: {stats['avg_confidence']:.2f}")
```

### Save Screenshots

```python
result = await engine.ground_element(page, "some element")

if result.success and result.best_match.screenshot_path:
    print(f"Screenshot saved: {result.best_match.screenshot_path}")
```

## Common Errors

### Error: "Ollama not available"

**Solution**: Install Ollama and pull a vision model:
```bash
ollama pull minicpm-v
```

### Error: "Element not found"

**Solutions**:
1. Try alternative descriptions
2. Use different strategies
3. Check if element is in iframe
4. Verify page has loaded

```python
# Try alternatives
descriptions = [
    "the submit button",
    "the blue button",
    "the button at bottom right"
]

for desc in descriptions:
    result = await engine.ground_element(page, desc)
    if result.success and result.best_match.confidence > 0.7:
        break
```

### Error: Low confidence scores

**Solutions**:
1. Be more specific in description
2. Try COORDINATED strategy
3. Use element_type hint

```python
result = await engine.ground_element(
    page,
    "the blue Submit button in the login form",  # More specific
    strategy=GroundingStrategy.COORDINATED,       # More thorough
    element_type=ElementType.BUTTON               # Type hint
)
```

## Integration with Eversale

### With Playwright Direct

```python
# In playwright_direct.py
from visual_grounding import ground_and_click

async def enhanced_click(page, selector=None, description=None):
    """Click with visual fallback."""
    if selector:
        try:
            await page.click(selector)
            return True
        except:
            pass

    if description:
        return await ground_and_click(page, description)

    return False
```

### With DOM Distillation

```python
from dom_distillation import get_engine as get_dom_engine
from visual_grounding import VisualGroundingEngine

# Use DOM for fast enumeration
dom_engine = get_dom_engine()
snapshot = await dom_engine.distill_page(page)

# Use visual grounding for uncertain elements
visual_engine = VisualGroundingEngine()
result = await visual_engine.ground_element(page, "ambiguous element")
```

### With Action Engine

```python
# In action_engine.py
from visual_grounding import VisualGroundingEngine

class EnhancedActionEngine:
    def __init__(self):
        self.grounding = VisualGroundingEngine()

    async def execute_action(self, page, action_desc):
        """Execute action using visual grounding."""
        result = await self.grounding.ground_element(page, action_desc)
        if result.success:
            return await self.grounding.click_grounded_element(
                page,
                result.best_match
            )
        return False
```

## Performance Tips

1. **Use DOM_ONLY when possible** - 50ms vs 2s
2. **Cache grounding results** - Don't re-ground static elements
3. **Ground multiple elements in parallel** - Use `ground_multiple_elements()`
4. **Specify element_type** - Narrows search space
5. **Be specific in descriptions** - "the blue Submit button" > "button"

## Next Steps

- Read full documentation: `VISUAL_GROUNDING_README.md`
- Run tests: `python test_visual_grounding.py`
- See integrations: `python visual_grounding_integration.py`
- Check examples in: `visual_grounding_integration.py`

## Quick Reference

```python
# Import
from visual_grounding import (
    VisualGroundingEngine,
    GroundingStrategy,
    ElementType,
    ground_and_click,
    ground_and_fill,
    ground_and_extract_text
)

# Initialize
engine = VisualGroundingEngine()

# Ground
result = await engine.ground_element(page, "description")

# Actions
await engine.click_grounded_element(page, element)
await engine.fill_grounded_element(page, element, "text")
text = await engine.extract_text_from_element(page, element)

# Convenience
await ground_and_click(page, "description")
await ground_and_fill(page, "description", "text")
text = await ground_and_extract_text(page, "description")
```

## Support

For issues, see the main Eversale documentation or check:
- Full docs: `VISUAL_GROUNDING_README.md`
- Test suite: `test_visual_grounding.py`
- Integration examples: `visual_grounding_integration.py`
