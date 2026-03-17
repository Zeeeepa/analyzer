# Accessibility Element Finder - Quick Reference

## 1-Minute Setup

```python
from accessibility_element_finder import SmartElementFinder

finder = SmartElementFinder()
ref = await finder.find_element(page, "search button")
if ref:
    await page.click(f'[data-ref="{ref.ref}"]')
```

## Core API

### SmartElementFinder

```python
finder = SmartElementFinder(min_confidence=0.3)

# Find single element
ref = await finder.find_element(page, "login button")
ref = await finder.find_element(page, "email", role_hint="textbox")

# Find multiple elements
refs = await finder.find_all_matching(page, "delete", max_results=10)
```

### AccessibilityRef

```python
ref.ref          # "s1e5" - use for targeting
ref.role         # "button", "textbox", "link"
ref.name         # Visible text/label
ref.value        # Current value (inputs)
ref.bounds       # {x, y, width, height}
```

### Convenience Functions

```python
from accessibility_element_finder import (
    find_element,  # Generic
    find_button,   # Buttons only
    find_input,    # Inputs only
    find_link,     # Links only
    parse_snapshot # Manual parsing
)

# Quick finding
button = await find_button(page, "submit")
input_field = await find_input(page, "email")
link = await find_link(page, "sign in")
```

## Common Patterns

### Pattern 1: Click by Description

```python
ref = await finder.find_element(page, "search button")
if ref:
    await page.click(f'[data-ref="{ref.ref}"]')
```

### Pattern 2: Fill Input

```python
ref = await finder.find_element(page, "email input")
if ref:
    await page.fill(f'[data-ref="{ref.ref}"]', 'user@example.com')
```

### Pattern 3: MCP Integration

```python
ref = await finder.find_element(mcp_client, "submit button")
if ref:
    await mcp_client.call_tool('playwright_click', {
        'ref': ref.ref,
        'element': ref.name
    })
```

### Pattern 4: Multiple Matches

```python
matches = await finder.find_all_matching(page, "delete button")
for m in matches:
    print(f"{m.name} [{m.ref}]")
```

### Pattern 5: Manual Parsing

```python
snapshot = await page.accessibility.snapshot()
refs = parse_snapshot(snapshot)
buttons = [r for r in refs if r.role == 'button']
```

## Role Reference

**Clickable**: button, link, menuitem, tab, checkbox, radio, switch

**Fillable**: textbox, searchbox, spinbutton, combobox, textarea

## Matching Examples

| Description | Matches | Score |
|------------|---------|-------|
| "search button" | button "Search" | 1.0 |
| "email input" | textbox "Email address" | 0.5 |
| "submit" | button "Submit" | 0.9 |
| "login link" | link "Sign in" | 0.6 |

## Error Handling

```python
ref = await finder.find_element(page, "button")
if not ref:
    # Get available elements
    snapshot = await page.accessibility.snapshot()
    refs = parse_snapshot(snapshot)
    print(f"Available: {[r.name for r in refs]}")
```

## Performance

- Get snapshot: 50-200ms
- Parse: <5ms
- Find: <1ms
- **Total: 50-210ms**

## Best Practices

1. **Be specific**: "search button" not "button"
2. **Use role hints**: `role_hint="button"` for speed
3. **Check for None**: Always validate before using ref
4. **Reuse finder**: Create once, use many times
5. **Use convenience functions**: Clearer intent

## Testing

```bash
python3 engine/agent/accessibility_element_finder.py
```

## Integration

```python
# With coordinate_targeting.py
from coordinate_targeting import CoordinateTargeting
ref = await finder.find_element(page, "button")
if ref.bounds:
    x = ref.bounds['x'] + ref.bounds['width'] / 2
    y = ref.bounds['y'] + ref.bounds['height'] / 2
    await page.mouse.click(x, y)

# With brain_enhanced_v2.py
ref = await finder.find_element(self.mcp, "search")
await self.mcp.call_tool('playwright_click', {'ref': ref.ref})

# With playwright_direct.py
ref = await self.finder.find_element(self.page, "login")
await self.page.click(f'[data-ref="{ref.ref}"]')
```

## Troubleshooting

**Element not found?**
- Check: `parse_snapshot(snapshot)` to see all elements
- Lower threshold: `SmartElementFinder(min_confidence=0.2)`
- Add role hint: `find_element(page, "text", role_hint="textbox")`

**Wrong element?**
- Be more specific in description
- Use `find_all_matching()` to see all matches
- Add role hint for disambiguation

**Snapshot empty?**
- Wait for page load: `await page.wait_for_load_state()`
- Check MCP connection
- Verify Playwright version

## Why It Works

- **Stable**: Semantic structure > CSS classes
- **Fast**: Direct tree lookup
- **AI-friendly**: Natural language
- **Production-ready**: Error handling, logging

This is how Playwright MCP achieves reliability.
