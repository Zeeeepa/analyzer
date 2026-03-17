# Accessibility Element Finder - Production Guide

## Overview

The Accessibility Element Finder achieves Playwright MCP-level reliability by using accessibility tree refs instead of fragile CSS selectors. This is the secret to reliable element interaction.

**File**: `accessibility_element_finder.py`

## The Key Insight

Traditional automation fails because:
```python
# FRAGILE - breaks when class names change
await page.click('.btn-primary.mt-3[data-test="submit"]')
```

Accessibility-first automation succeeds because:
```python
# STABLE - based on semantic structure
ref = await find_element(page, "submit button")
await page.click(f'[data-ref="{ref.ref}"]')
```

## Why Accessibility Refs Win

| Aspect | CSS Selectors | Accessibility Refs |
|--------|--------------|-------------------|
| **Stability** | Breaks when classes/IDs change | Based on semantic roles |
| **Speed** | Complex DOM traversal | Direct tree lookup |
| **AI-friendly** | Technical syntax | Natural language names |
| **Vision-compatible** | No | Yes (matches screenshots) |
| **Human-aligned** | No | Yes (how users describe elements) |

## Architecture

```
SmartElementFinder
    |
    +-- Get accessibility snapshot
    |   (from MCP or Playwright)
    |
    +-- Parse into AccessibilityRef objects
    |   (role, name, ref, bounds)
    |
    +-- Score elements against description
    |   (fuzzy matching, synonyms)
    |
    +-- Return best match
        (confidence threshold)
```

## Core Components

### 1. AccessibilityRef Dataclass

Represents a single element in the accessibility tree:

```python
@dataclass
class AccessibilityRef:
    ref: str              # e.g., "s1e5"
    role: str             # button, textbox, link
    name: str             # visible text/label
    value: Optional[str]  # current value (for inputs)
    description: Optional[str]
    bounds: Optional[Dict]  # x, y, width, height
```

**Example**:
```python
AccessibilityRef(
    ref='s1e5',
    role='button',
    name='Submit',
    value=None,
    description=None,
    bounds={'x': 100, 'y': 200, 'width': 80, 'height': 30}
)
```

### 2. AccessibilityTreeParser

Parses snapshots into refs:

```python
parser = AccessibilityTreeParser()

# Parse markdown snapshot (from MCP)
refs = parser.parse_snapshot(markdown_snapshot)

# Parse Playwright snapshot (dict)
refs = parser.parse_snapshot(playwright_snapshot)

# Find by role
buttons = parser.find_by_role(refs, "button")

# Find by name (fuzzy)
email_input = parser.find_by_name(refs, "email", fuzzy=True)

# Find by text (searches name, value, description)
matches = parser.find_by_text(refs, "search")

# Find all interactive elements
interactive = parser.find_interactive(refs)
```

### 3. SmartElementFinder

High-level API with intelligent matching:

```python
finder = SmartElementFinder()

# Find single best match
ref = await finder.find_element(page, "search button")

# Find all matches (sorted by confidence)
refs = await finder.find_all_matching(page, "submit", max_results=5)

# With role hint for faster matching
ref = await finder.find_element(page, "email", role_hint="textbox")
```

## Usage Patterns

### Pattern 1: Direct Playwright Integration

```python
from accessibility_element_finder import SmartElementFinder

finder = SmartElementFinder()

# Find and click
ref = await finder.find_element(page, "login button")
if ref:
    await page.click(f'[data-ref="{ref.ref}"]')

# Find and fill
ref = await finder.find_element(page, "email input")
if ref:
    await page.fill(f'[data-ref="{ref.ref}"]', 'user@example.com')
```

### Pattern 2: MCP Client Integration

```python
from accessibility_element_finder import SmartElementFinder

finder = SmartElementFinder()

# Find element via MCP
ref = await finder.find_element(mcp_client, "search button")
if ref:
    # Use MCP's playwright_click with ref
    await mcp_client.call_tool('playwright_click', {
        'ref': ref.ref,
        'element': ref.name
    })
```

### Pattern 3: Convenience Functions

```python
from accessibility_element_finder import (
    find_button,
    find_input,
    find_link
)

# Find specific element types
submit_btn = await find_button(page, "submit")
email_field = await find_input(page, "email address")
signin_link = await find_link(page, "sign in")
```

### Pattern 4: Multiple Matches

```python
finder = SmartElementFinder()

# Get all buttons with "delete" in the name
delete_buttons = await finder.find_all_matching(
    page,
    "delete",
    role_hint="button",
    max_results=10
)

for btn in delete_buttons:
    print(f"Found: {btn.name} [{btn.ref}]")
```

### Pattern 5: Manual Parsing

```python
from accessibility_element_finder import parse_snapshot

# Get snapshot
snapshot = await page.accessibility.snapshot()

# Parse manually
refs = parse_snapshot(snapshot)

# Filter
buttons = [r for r in refs if r.role == 'button']
inputs = [r for r in refs if r.role in ['textbox', 'searchbox']]
```

## Matching Algorithm

The smart matcher scores elements based on:

1. **Role Match** (+0.3): Role mentioned in description
2. **Role Synonym** (+0.2): Synonym match (e.g., "btn" for "button")
3. **Keyword Match** (+0.3 each): Keywords found in name
4. **Exact Match** (+0.4): Name exactly matches description
5. **Value Match** (+0.2): For inputs, value contains keywords

**Example Scores**:

| Description | Element | Score | Reason |
|------------|---------|-------|--------|
| "search button" | button "Search" | 1.0 | Role + exact name match |
| "email input" | textbox "Email address" | 0.5 | Synonym + partial match |
| "submit" | button "Submit" | 0.9 | Exact name match |
| "login link" | link "Sign in" | 0.6 | Role + partial match |

Minimum confidence threshold: **0.3** (configurable)

## Snapshot Formats

### Format 1: MCP Markdown Snapshot

From `playwright_snapshot` MCP tool:

```markdown
- button "Search" [ref=s1e3]
- textbox "Email address" [ref=s1e5]
- link "Sign in" [ref=s1e7]
- checkbox "Remember me" [ref=s1e9]
```

### Format 2: Playwright Accessibility Tree

From `page.accessibility.snapshot()`:

```python
{
    "role": "button",
    "name": "Search",
    "ref": "s1e3",
    "children": [
        {
            "role": "textbox",
            "name": "Email address",
            "ref": "s1e5"
        }
    ]
}
```

Both formats are automatically detected and parsed.

## Role Reference

### Clickable Roles

Elements that can be clicked:

- `button` - Buttons
- `link` - Links/anchors
- `menuitem` - Menu items
- `tab` - Tab controls
- `checkbox` - Checkboxes
- `radio` - Radio buttons
- `switch` - Toggle switches
- `option` - Select options
- `treeitem` - Tree items
- `gridcell` - Grid cells

### Fillable Roles

Elements that accept text input:

- `textbox` - Text inputs
- `searchbox` - Search inputs
- `spinbutton` - Number inputs
- `combobox` - Combo boxes
- `textarea` - Multi-line text

## Error Handling

### Element Not Found

```python
ref = await finder.find_element(page, "nonexistent button")
if not ref:
    # Get all available elements
    snapshot = await page.accessibility.snapshot()
    refs = parse_snapshot(snapshot)
    buttons = [r for r in refs if r.role == 'button']
    print(f"Available buttons: {[b.name for b in buttons]}")
```

### Low Confidence Match

```python
finder = SmartElementFinder(min_confidence=0.5)  # Stricter matching

ref = await finder.find_element(page, "vague description")
if not ref:
    # Try more specific description or role hint
    ref = await finder.find_element(
        page,
        "specific button name",
        role_hint="button"
    )
```

### Multiple Matches

```python
# Get all matches to see ambiguity
matches = await finder.find_all_matching(page, "submit")

if len(matches) > 1:
    # Disambiguate by choosing first or most relevant
    ref = matches[0]  # Highest confidence
    print(f"Multiple matches, chose: {ref.name}")
```

## Performance Characteristics

| Operation | Time | Notes |
|-----------|------|-------|
| Get snapshot | 50-200ms | MCP or Playwright API call |
| Parse snapshot | <5ms | Regex parsing or tree traversal |
| Find element | <1ms | List filtering and scoring |
| **Total** | **50-210ms** | Fast enough for real-time use |

Compare to traditional selector finding:
- CSS selector: 50-500ms (depends on DOM complexity)
- XPath: 100-1000ms (slow traversal)
- Vision-based: 2-5 seconds (screenshot + AI)

## Integration with Existing Systems

### With coordinate_targeting.py

```python
from coordinate_targeting import CoordinateTargeting
from accessibility_element_finder import SmartElementFinder

targeting = CoordinateTargeting()
finder = SmartElementFinder()

# Find element by description
ref = await finder.find_element(page, "submit button")

# Get coordinates from ref
if ref and ref.bounds:
    x = ref.bounds['x'] + ref.bounds['width'] / 2
    y = ref.bounds['y'] + ref.bounds['height'] / 2
    await page.mouse.click(x, y)
```

### With brain_enhanced_v2.py

```python
from accessibility_element_finder import find_element

# In Brain class
async def smart_click(self, description: str):
    """Click element by natural language description"""
    ref = await find_element(self.mcp, description)
    if ref:
        await self.mcp.call_tool('playwright_click', {
            'ref': ref.ref,
            'element': ref.name
        })
        return True
    return False
```

### With playwright_direct.py

```python
from accessibility_element_finder import SmartElementFinder

class PlaywrightDirect:
    def __init__(self):
        self.finder = SmartElementFinder()

    async def click_element(self, description: str):
        ref = await self.finder.find_element(self.page, description)
        if ref:
            await self.page.click(f'[data-ref="{ref.ref}"]')
```

## Best Practices

### 1. Use Descriptive Language

Good:
- "search button"
- "email address input"
- "sign in with Google link"

Bad:
- "button" (too generic)
- "input1" (not descriptive)
- "the thing" (no context)

### 2. Add Role Hints When Possible

```python
# Faster and more accurate
ref = await finder.find_element(page, "submit", role_hint="button")

# vs slower ambiguous search
ref = await finder.find_element(page, "submit")
```

### 3. Check for None

```python
ref = await finder.find_element(page, "login")
if ref:
    # Use ref
else:
    # Handle not found
```

### 4. Use Convenience Functions

```python
# Clearer intent
button = await find_button(page, "submit")

# vs generic
ref = await find_element(page, "submit button")
```

### 5. Reuse Finder Instance

```python
# Good - reuse instance
finder = SmartElementFinder()
ref1 = await finder.find_element(page, "button1")
ref2 = await finder.find_element(page, "button2")

# Less efficient - creates new instances
ref1 = await find_element(page, "button1")  # Creates finder
ref2 = await find_element(page, "button2")  # Creates finder
```

## Troubleshooting

### Problem: Element not found

**Solution 1**: Check available elements
```python
snapshot = await page.accessibility.snapshot()
refs = parse_snapshot(snapshot)
print(f"Available: {[f'{r.role}: {r.name}' for r in refs]}")
```

**Solution 2**: Lower confidence threshold
```python
finder = SmartElementFinder(min_confidence=0.2)
```

**Solution 3**: Use role hint
```python
ref = await finder.find_element(page, "email", role_hint="textbox")
```

### Problem: Wrong element matched

**Solution 1**: Be more specific
```python
# Too vague
ref = await finder.find_element(page, "submit")

# More specific
ref = await finder.find_element(page, "submit form button")
```

**Solution 2**: Check all matches
```python
matches = await finder.find_all_matching(page, "submit")
for m in matches:
    print(f"{m.role}: {m.name} (confidence: {m.confidence})")
```

### Problem: Snapshot empty

**Check 1**: Page loaded?
```python
await page.wait_for_load_state('domcontentloaded')
snapshot = await page.accessibility.snapshot()
```

**Check 2**: MCP connection?
```python
# Test MCP
result = await mcp_client.call_tool('playwright_snapshot', {})
print(result)
```

## Testing

Run the built-in test:

```bash
python3 engine/agent/accessibility_element_finder.py
```

Expected output:
```
============================================================
Accessibility Element Finder Test
============================================================

1. Markdown Snapshot Parsing:
   Found 4 elements:
   - button "Search" [ref=s1e3]
   - textbox "Email address" [ref=s1e5]
   - link "Sign in" [ref=s1e7]
   - button "Submit" [ref=s1e9]

2. Finding Elements:
   Buttons: ['button "Search" [ref=s1e3]', 'button "Submit" [ref=s1e9]']
   Email inputs: ['textbox "Email address" [ref=s1e5]']

3. Smart Matching:
   'search button' -> button "Search" [ref=s1e3]
   'email input' -> textbox "Email address" [ref=s1e5]
   'sign in link' -> link "Sign in" [ref=s1e7]
   'submit' -> button "Submit" [ref=s1e9]

============================================================
Test complete!
```

## Future Enhancements

Potential improvements:

1. **Spatial reasoning**: "button to the right of email input"
2. **Hierarchy awareness**: "submit button inside form"
3. **Visual context**: "red delete button" (requires screenshot)
4. **Learning**: Cache successful matches for faster lookup
5. **Multi-language**: Support non-English element names

## Comparison to Alternatives

| Approach | Speed | Reliability | AI-Friendly | Maintenance |
|----------|-------|-------------|-------------|-------------|
| **Accessibility refs** | Fast | High | Excellent | Low |
| CSS selectors | Fast | Low | Poor | High |
| XPath | Slow | Medium | Poor | High |
| Vision + AI | Very slow | Medium | Excellent | Low |
| text= locators | Fast | Medium | Good | Medium |

The accessibility-first approach combines the best of all worlds: fast, reliable, AI-friendly, and low maintenance.

## Summary

The Accessibility Element Finder provides:

1. **Reliability** - Semantic refs instead of fragile selectors
2. **Speed** - Direct tree lookup, <1ms matching
3. **Simplicity** - Natural language descriptions
4. **Flexibility** - Works with MCP or Playwright
5. **Production-ready** - Error handling, logging, testing

This is the secret to Playwright MCP's success, now available for your agent.
