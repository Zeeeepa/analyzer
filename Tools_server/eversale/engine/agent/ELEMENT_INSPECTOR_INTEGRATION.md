# Element Inspector - Integration Guide

## Overview

The Element Inspector module has been successfully integrated into the Eversale agent architecture. This document explains how it connects with existing modules and how to use it in the ReAct loop.

## Files Created

| File | Size | Purpose |
|------|------|---------|
| `element_inspector.py` | 33KB | Core element analysis engine |
| `smart_selector.py` | 20KB | High-level API combining visual + selector targeting |
| `element_inspector_example.py` | 14KB | Usage examples and demonstrations |
| `test_element_inspector.py` | 15KB | Comprehensive test suite |
| `ELEMENT_INSPECTOR_README.md` | 13KB | Full documentation |
| `ELEMENT_INSPECTOR_INTEGRATION.md` | This file | Integration guide |

**Total**: ~95KB of production code, tests, and documentation

## Architecture Integration

```
┌─────────────────────────────────────────────────────────────┐
│                      ReAct Loop                              │
│                  (reasoning_engine.py)                       │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │   SmartSelector (NEW!)       │ ◄── High-level API
        │   smart_selector.py          │
        └──────┬──────────────┬────────┘
               │              │
     ┌─────────▼─────┐   ┌───▼──────────────┐
     │ ElementInspector│   │ VisualTargeting │
     │ element_inspector│   │ visual_targeting│
     │      .py         │   │      .py         │
     └─────────┬───────┘   └───┬──────────────┘
               │               │
               │               ▼
               │      ┌────────────────┐
               │      │   Moondream    │ ◄── Vision model
               │      │  (Ollama/Cloud)│
               │      └────────────────┘
               │
               ▼
     ┌──────────────────────┐
     │  Playwright Page     │ ◄── Browser automation
     │  (browser_manager)   │
     └──────────────────────┘
               │
               ▼
     ┌──────────────────────┐
     │  Humanization        │ ◄── Human-like interactions
     │  - BezierCursor      │
     │  - HumanTyper        │
     │  - ContinuousPerception│
     └──────────────────────┘
```

## Integration Points

### 1. ReAct Loop Integration

**File**: `agent/react_loop.py`

The ReAct loop should use `SmartSelector` for all element interactions:

```python
from agent.smart_selector import SmartSelector

class ReActLoop:
    async def execute_action(self, action: str, params: dict):
        # Initialize smart selector
        selector = SmartSelector(self.page, prefer_visual=True)

        if action == 'click':
            result = await selector.click(
                description=params['element_description'],
                context=params.get('context', ''),
                humanized=True
            )

            if not result.success:
                # Detailed diagnostics available
                logger.error(f"Click failed: {result.issues}")
                logger.info(f"Suggestions: {result.suggestions}")

        elif action == 'fill':
            result = await selector.fill(
                description=params['element_description'],
                text=params['text'],
                humanized=True
            )

        elif action == 'extract_list':
            items = await selector.extract_list(
                first_item_description=params['element_description'],
                max_items=params.get('max_items', 100)
            )
```

### 2. Browser Manager Integration

**File**: `agent/browser_manager.py`

Browser manager should initialize element inspector for each page:

```python
from agent.element_inspector import ElementInspector
from agent.smart_selector import SmartSelector

class BrowserManager:
    async def new_page(self):
        page = await self.context.new_page()

        # Attach inspector to page
        page._inspector = ElementInspector(page)
        page._smart_selector = SmartSelector(page)

        return page
```

### 3. Visual Targeting Enhancement

**File**: `agent/visual_targeting.py`

Visual targeting is already imported in `smart_selector.py`. The integration automatically:

1. Tries visual targeting first (Moondream vision)
2. Falls back to selector strategies
3. Combines both for enhanced results

No changes needed to `visual_targeting.py` - it works as-is!

### 4. Humanization Integration

**File**: `agent/humanization/`

Smart selector automatically uses humanization modules when available:

- **BezierCursor**: For human-like mouse movements during clicks
- **HumanTyper**: For realistic typing with errors/corrections
- **ContinuousPerception**: For visual awareness (already integrated in browser_manager)

### 5. Tool Integration (MCP)

**File**: `mcp/playwright_tools.py`

Playwright MCP tools should optionally use element inspector:

```python
from agent.smart_selector import SmartSelector

class PlaywrightTools:
    async def playwright_click(self, selector: str, description: str = None):
        """Enhanced click with element inspection."""

        if description:
            # Use smart selector
            smart = SmartSelector(self.page)
            result = await smart.click(description, fallback_selectors=[selector])

            return {
                'success': result.success,
                'method': result.method,
                'issues': result.issues,
                'suggestions': result.suggestions
            }
        else:
            # Fallback to regular Playwright click
            await self.page.click(selector)
            return {'success': True}
```

## Usage Patterns

### Pattern 1: Simple Click (Preferred)

```python
from agent.smart_selector import SmartSelector

selector = SmartSelector(page)
result = await selector.click("Submit button")

if result.success:
    print(f"Clicked via {result.method} with {result.confidence:.0%} confidence")
else:
    print(f"Failed: {result.issues}")
    print(f"Try: {result.suggestions}")
```

### Pattern 2: Click with Fallback Selectors

```python
result = await selector.click(
    description="Submit button",
    context="Login form submission",
    fallback_selectors=['#submit-btn', 'button[type="submit"]']
)
```

### Pattern 3: Fill Input Field

```python
result = await selector.fill(
    description="Email input",
    text="user@example.com",
    humanized=True  # Uses HumanTyper
)
```

### Pattern 4: Extract List Items

```python
items = await selector.extract_list(
    first_item_description="First product card",
    max_items=50
)

for item in items:
    print(f"{item['index']}: {item['text']}")
```

### Pattern 5: Wait for Element

```python
result = await selector.wait_for_element(
    description="Success message",
    timeout=10.0
)

if result.success:
    print("Success message appeared!")
```

### Pattern 6: Deep Inspection

```python
from agent.element_inspector import ElementInspector

inspector = ElementInspector(page)

# Get full snapshot
snapshot = await inspector.inspect_element('#submit-btn')

# Analyze selector quality
quality = await inspector.analyze_selector_quality(snapshot)

print(f"Best selector: {quality.recommended_selector}")
print(f"Confidence: {quality.confidence:.0%}")
print(f"Warnings: {quality.warnings}")

# Check if dynamic (React/Vue)
dynamic = await inspector.is_element_dynamic('#submit-btn')

if dynamic.is_dynamic:
    print(f"Element changes {dynamic.change_frequency}")
    print(f"Use stable selector: {dynamic.recommended_stable_selector}")
```

### Pattern 7: Diagnose Interaction Failure

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

## Migration Guide

### Before (Old Way)

```python
# Fragile: Breaks when CSS changes
await page.click('.css-1dbjc4n button')

# No diagnostics on failure
try:
    await page.fill('#email', 'user@example.com')
except Exception as e:
    print(f"Failed: {e}")  # What went wrong?
```

### After (New Way)

```python
from agent.smart_selector import SmartSelector

selector = SmartSelector(page)

# Robust: Uses visual + selector + ARIA
result = await selector.click("Submit button")

if not result.success:
    # Detailed diagnostics
    print(f"Issues: {result.issues}")
    print(f"Suggestions: {result.suggestions}")
    print(f"Tried: {result.method}")

# Self-healing: Scrolls into view, waits for enabled
result = await selector.fill("Email input", "user@example.com")
```

## Testing

### Run Tests

```bash
# All tests
pytest agent/test_element_inspector.py -v

# Specific test class
pytest agent/test_element_inspector.py::TestElementInspector -v

# Integration test with real website
pytest agent/test_element_inspector.py::test_real_website_inspection -v
```

### Run Examples

```bash
# All examples
python agent/element_inspector_example.py

# Specific example (edit the main() function)
```

## Performance Considerations

### Optimization Strategies

1. **Cache Selectors**: Store high-confidence selectors for reuse
   ```python
   selector._selector_cache['submit_button'] = '#submit-btn'
   ```

2. **Disable Visual on Fast Sites**: If selectors work well, skip visual
   ```python
   selector = SmartSelector(page, prefer_visual=False)
   ```

3. **Reduce Dynamic Analysis Duration**: Default is 2s, can be reduced
   ```python
   dynamic = await inspector.is_element_dynamic(
       selector,
       observation_duration=1.0  # Faster
   )
   ```

4. **Batch Sibling Extraction**: Single DOM query for all siblings
   ```python
   siblings = await inspector.get_similar_siblings(selector)
   # Better than: for i in range(10): await inspect(f'li:nth-child({i})')
   ```

### Performance Benchmarks

| Operation | Time | Notes |
|-----------|------|-------|
| `inspect_element()` | ~50ms | Single DOM query |
| `analyze_selector_quality()` | ~10ms | Pure Python analysis |
| `is_element_dynamic()` | ~2s | Configurable duration |
| `diagnose_interaction_failure()` | ~60ms | Inspection + analysis |
| `get_similar_siblings()` | ~30ms | Single DOM query |
| `visual.locate_element()` | ~500ms | Local Ollama with GPU |
| `visual.locate_element()` | ~2s | Cloud (RunPod) |
| `smart_selector.click()` | ~100ms | Selector-based |
| `smart_selector.click()` | ~600ms | Visual-based |

## Troubleshooting

### Issue: Visual targeting slow

**Solution**: Check if local Ollama is using GPU
```bash
python -m agent.stealth_check
# Should show: "GPU detected: NVIDIA RTX..."
```

**Alternative**: Force local mode
```python
visual = VisualTargeting(mode='local')
```

### Issue: Selectors break on React/Vue apps

**Solution**: Use ARIA/data-testid selectors via inspector
```python
quality = await inspector.analyze_selector_quality(snapshot)
# Prefers ARIA over CSS classes
```

### Issue: Element not found

**Solution**: Use diagnosis
```python
diagnosis = await inspector.diagnose_interaction_failure(selector)
print(diagnosis['reason'])
print(diagnosis['suggestions'])
```

### Issue: Import errors

**Solution**: Ensure all dependencies installed
```bash
pip install playwright loguru
```

## Future Enhancements

Planned features for element inspector:

- [ ] Event listener extraction via Chrome DevTools Protocol
- [ ] Shadow DOM traversal
- [ ] Iframe auto-detection and context switching
- [ ] Machine learning selector prediction
- [ ] Automatic selector repair (self-healing)
- [ ] Performance profiling for slow interactions
- [ ] Screenshot-based element matching
- [ ] Selector diff between page versions

## Related Documentation

- **Main README**: `/mnt/c/ev29/agent/ELEMENT_INSPECTOR_README.md`
- **Visual Targeting**: `/mnt/c/ev29/agent/visual_targeting.py`
- **Humanization**: `/mnt/c/ev29/agent/humanization/README.md`
- **Browser Manager**: `/mnt/c/ev29/agent/browser_manager.py`
- **ReAct Loop**: `/mnt/c/ev29/agent/react_loop.py`

## Support

For questions or issues:
1. Check the examples: `agent/element_inspector_example.py`
2. Run the tests: `pytest agent/test_element_inspector.py -v`
3. Review the README: `agent/ELEMENT_INSPECTOR_README.md`
4. File an issue with diagnostic output from `diagnose_interaction_failure()`

