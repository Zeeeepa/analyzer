# Obstruction Handling - Quick Reference

## Import

```python
from agent.browser_manager import BrowserManager, ObstructionInfo, OBSTRUCTION_PATTERNS
```

## Quick Start

```python
# Create BrowserManager
browser_mgr = BrowserManager(mcp_client=mcp)

# Auto-dismiss after navigation
await page.goto('https://example.com')
await browser_mgr.auto_dismiss_on_navigation('https://example.com')

# Check element clickability
if await browser_mgr.ensure_element_clickable('#button'):
    await page.click('#button')
```

## Core Methods

| Method | Purpose | Returns |
|--------|---------|---------|
| `detect_obstructions()` | Find all obstructions | `List[ObstructionInfo]` |
| `dismiss_obstruction(obs)` | Dismiss single obstruction | `bool` |
| `scan_and_dismiss_obstructions(aggressive=False)` | Dismiss all obstructions | `int` (count) |
| `ensure_element_clickable(selector, timeout=5000)` | Check if element clickable | `bool` |
| `get_elements_by_z_index(min_z_index=1000)` | Find high z-index elements | `List[Dict]` |
| `auto_dismiss_on_navigation(url)` | Auto-dismiss after page load | `int` (count) |
| `reset_obstruction_tracking()` | Reset dismissed tracking | `None` |

## Obstruction Types (Priority Order)

| Type | Priority | When Dismissed |
|------|----------|----------------|
| `cookie_banner` | 1 | Always |
| `age_verification` | 1 | Always |
| `modal` | 2 | Default |
| `newsletter_popup` | 2 | Default |
| `chat_widget` | 3 | Aggressive only |
| `fixed_header` | 4 | Aggressive only |

## Usage Patterns

### Pattern 1: Auto-Dismiss After Navigation

```python
await page.goto(url)
dismissed = await browser_mgr.auto_dismiss_on_navigation(url)
# Auto-dismisses cookie banners, modals
```

### Pattern 2: Safe Element Interaction

```python
# Check clickability before clicking
if await browser_mgr.ensure_element_clickable('#submit'):
    await page.click('#submit')
else:
    logger.warning("Element is obstructed")
```

### Pattern 3: Manual Detection & Dismissal

```python
# Detect obstructions
obstructions = await browser_mgr.detect_obstructions()

# Filter high-priority
high_priority = [o for o in obstructions if o.type == 'cookie_banner']

# Dismiss each
for obs in high_priority:
    await browser_mgr.dismiss_obstruction(obs)
```

### Pattern 4: Aggressive Scan

```python
# Dismiss ALL obstructions (including chat widgets)
dismissed = await browser_mgr.scan_and_dismiss_obstructions(aggressive=True)
print(f"Dismissed {dismissed} obstructions")
```

### Pattern 5: Z-Index Analysis

```python
# Find overlays by z-index
high_z = await browser_mgr.get_elements_by_z_index(min_z_index=1000)
for elem in high_z:
    print(f"{elem['selector']}: z={elem['z_index']}, coverage={elem['coverage']}%")
```

## Integration with ReAct Loop

```python
# In brain_enhanced_v2.py

# BEFORE ACTION
if action_name == 'playwright_click':
    selector = tool_args.get('selector')
    await browser_mgr.ensure_element_clickable(selector)

# AFTER ACTION
if action_name == 'playwright_navigate':
    url = tool_args.get('url')
    await browser_mgr.auto_dismiss_on_navigation(url)

# ERROR RECOVERY
except Exception as e:
    if 'not clickable' in str(e).lower():
        dismissed = await browser_mgr.scan_and_dismiss_obstructions(aggressive=True)
        if dismissed > 0:
            # Retry action
            result = await mcp.call_tool(action_name, tool_args)
```

## Dismiss Methods

| Method | Description | Use Case |
|--------|-------------|----------|
| `click_close` | Click close button | Cookie banners, modals |
| `press_esc` | Press ESC key | Modals, popups |
| `click_outside` | Click outside element | Dismissible overlays |

## Statistics

```python
stats = browser_mgr.get_stats()
print(stats['obstructions_detected'])   # Total detected
print(stats['obstructions_dismissed'])  # Total dismissed
```

## ObstructionInfo Fields

```python
@dataclass
class ObstructionInfo:
    type: str                      # Obstruction type
    selector: str                  # CSS selector
    z_index: int                   # Z-index value
    covers_percent: float          # % of viewport
    dismissible: bool              # Can dismiss?
    dismiss_method: Optional[str]  # How to dismiss
    dismiss_selector: Optional[str] # Close button selector
```

## Common Selectors

### Cookie Banners
- `[class*='cookie' i]`
- `[class*='consent' i]`
- `[class*='gdpr' i]`

### Modals
- `[role='dialog']`
- `[aria-modal='true']`
- `[class*='modal' i]`

### Chat Widgets
- `[class*='intercom' i]`
- `[class*='zendesk' i]`
- `[class*='drift' i]`

### Dismiss Buttons
- `[class*='accept' i]`
- `[aria-label='Close' i]`
- `button:has-text('×')`

## Configuration

### Default Behavior
- Detects obstructions with z-index >= 100 OR coverage >= 10%
- Dismisses priority 1-2 by default (cookie banners, modals)
- Tracks dismissed to avoid re-dismissing

### Aggressive Mode
- Dismisses ALL obstructions (priority 1-4)
- Includes chat widgets and fixed headers
- Use when element definitely obstructed

## Best Practices

1. **Always check after navigation**
   ```python
   await browser_mgr.auto_dismiss_on_navigation(url)
   ```

2. **Check before critical clicks**
   ```python
   await browser_mgr.ensure_element_clickable(selector)
   ```

3. **Use aggressive mode for recovery**
   ```python
   await browser_mgr.scan_and_dismiss_obstructions(aggressive=True)
   ```

4. **Reset tracking on domain change**
   ```python
   if new_domain != old_domain:
       browser_mgr.reset_obstruction_tracking()
   ```

5. **Monitor statistics**
   ```python
   stats = browser_mgr.get_stats()
   if stats['obstructions_dismissed'] > threshold:
       # High obstruction rate - investigate
   ```

## Troubleshooting

### Obstruction Not Detected

```python
# Check z-index manually
high_z = await browser_mgr.get_elements_by_z_index(min_z_index=0)
# Inspect elements, add pattern if needed
```

### Obstruction Not Dismissed

```python
# Try aggressive mode
dismissed = await browser_mgr.scan_and_dismiss_obstructions(aggressive=True)

# Check if dismissible
obstructions = await browser_mgr.detect_obstructions()
for obs in obstructions:
    print(f"{obs.type}: dismissible={obs.dismissible}, method={obs.dismiss_method}")
```

### False Positives

```python
# Lower z-index threshold in detection
# Or use non-aggressive mode (default)
dismissed = await browser_mgr.scan_and_dismiss_obstructions(aggressive=False)
```

## Examples

See:
- `/mnt/c/ev29/agent/OBSTRUCTION_HANDLING.md` - Full guide
- `/mnt/c/ev29/agent/test_obstruction_handling.py` - Test suite
- `/mnt/c/ev29/agent/obstruction_integration_example.py` - Integration examples

