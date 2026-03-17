# Obstruction Detection and Handling

This document describes the obstruction detection and handling features added to `BrowserManager`.

## Overview

Modern websites often display overlays, modals, cookie banners, and chat widgets that can block user interactions. The obstruction handling system automatically detects and dismisses these elements **before** they interfere with browser automation.

## Features

### 1. Obstruction Detection

The `detect_obstructions()` method scans the page for common obstruction patterns:

```python
obstructions = await browser_mgr.detect_obstructions()
for obs in obstructions:
    print(f"{obs.type}: z-index={obs.z_index}, coverage={obs.covers_percent}%")
```

**Detected Obstruction Types:**

| Type | Examples | Priority |
|------|----------|----------|
| `cookie_banner` | GDPR consent, cookie notices | 1 (highest) |
| `age_verification` | Age gates | 1 (highest) |
| `modal` | Login prompts, dialogs | 2 (high) |
| `newsletter_popup` | Email signup modals | 2 (high) |
| `chat_widget` | Intercom, Zendesk, Drift | 3 (medium) |
| `fixed_header` | Sticky navigation bars | 4 (low) |

### 2. Automatic Dismissal

The `scan_and_dismiss_obstructions()` method automatically dismisses detected obstructions:

```python
# Default: only dismiss high-priority obstructions (priority <= 2)
dismissed = await browser_mgr.scan_and_dismiss_obstructions()

# Aggressive: dismiss all obstructions
dismissed = await browser_mgr.scan_and_dismiss_obstructions(aggressive=True)
```

**Dismiss Methods:**

- **click_close**: Clicks close/dismiss button (X, "Close", "No thanks")
- **press_esc**: Presses ESC key (for modals)
- **click_outside**: Clicks outside the modal (for dismissible overlays)

### 3. Pre-Action Element Check

The `ensure_element_clickable()` method checks if an element is obstructed before clicking:

```python
# Check if element is clickable, dismiss obstructions if needed
if await browser_mgr.ensure_element_clickable('#submit-button'):
    await page.click('#submit-button')
else:
    print("Element is still obstructed")
```

**What it does:**

1. Finds the target element
2. Checks what element is at its center coordinates
3. If obstructed, runs `scan_and_dismiss_obstructions(aggressive=True)`
4. Re-checks if element is now clickable

### 4. Auto-Dismiss on Navigation

The `auto_dismiss_on_navigation()` method proactively dismisses obstructions after page load:

```python
await page.goto('https://example.com')

# Wait for page to settle, then dismiss common obstructions
dismissed = await browser_mgr.auto_dismiss_on_navigation('https://example.com')
```

**Use case:** Call this after every navigation to automatically handle cookie banners and popups.

### 5. Z-Index Analysis

The `get_elements_by_z_index()` method finds all high-z-index elements (likely overlays):

```python
# Get elements with z-index >= 1000
high_z = await browser_mgr.get_elements_by_z_index(min_z_index=1000)

for elem in high_z:
    print(f"{elem['selector']}: z={elem['z_index']}, coverage={elem['coverage']}%")
```

**What it returns:**

```python
[
    {
        'selector': 'div.modal-overlay',
        'z_index': 9999,
        'coverage': 85.3,  # % of viewport covered
        'position': 'fixed',
        'visible': True
    },
    # ...
]
```

## Usage Examples

### Example 1: Automatically Handle Cookie Banners

```python
from agent.browser_manager import BrowserManager

# Create BrowserManager
browser_mgr = BrowserManager(mcp_client=mcp)

# Navigate to site
await page.goto('https://example.com')

# Auto-dismiss cookie banners and modals
await browser_mgr.auto_dismiss_on_navigation('https://example.com')

# Now interact with the page normally
await page.click('#login-button')
```

### Example 2: Ensure Element is Clickable

```python
# Check if submit button is clickable before clicking
if await browser_mgr.ensure_element_clickable('#submit-button', timeout=5000):
    await page.click('#submit-button')
    print("Button clicked successfully")
else:
    print("Button is obstructed and couldn't be cleared")
```

### Example 3: Manual Obstruction Handling

```python
# Detect all obstructions
obstructions = await browser_mgr.detect_obstructions()

# Filter for high-priority obstructions
high_priority = [
    obs for obs in obstructions
    if obs.type in ['cookie_banner', 'age_verification']
]

# Dismiss each one
for obs in high_priority:
    if obs.dismissible:
        await browser_mgr.dismiss_obstruction(obs)
```

### Example 4: Integration with ReAct Loop

```python
# In brain_enhanced_v2.py or similar

# After navigation action
if action_name == 'playwright_navigate':
    # Auto-dismiss obstructions
    dismissed = await self.browser_manager.auto_dismiss_on_navigation(url)
    if dismissed > 0:
        logger.info(f"Auto-dismissed {dismissed} obstruction(s) after navigation")

# Before click action
if action_name == 'playwright_click':
    selector = tool_args.get('selector')
    # Ensure element is clickable
    if not await self.browser_manager.ensure_element_clickable(selector):
        logger.warning(f"Element {selector} may be obstructed")
```

## ObstructionInfo Data Class

```python
@dataclass
class ObstructionInfo:
    type: str                      # "modal", "cookie_banner", etc.
    selector: str                  # CSS selector for the element
    z_index: int                   # Z-index value
    covers_percent: float          # % of viewport covered
    dismissible: bool              # Whether it can be dismissed
    dismiss_method: Optional[str]  # "click_close", "press_esc", "click_outside"
    dismiss_selector: Optional[str] # CSS selector for dismiss button
```

## Obstruction Patterns

The system uses pattern-based detection defined in `OBSTRUCTION_PATTERNS`:

```python
OBSTRUCTION_PATTERNS = {
    "cookie_banner": {
        "selectors": [
            "[class*='cookie' i]",
            "[id*='cookie' i]",
            "[class*='consent' i]",
            # ... more patterns
        ],
        "dismiss": [
            "[class*='accept' i]",
            "button:has-text('Accept')",
            # ... more dismiss selectors
        ],
        "priority": 1  # High priority - always dismiss
    },
    # ... more patterns
}
```

### Adding Custom Patterns

To add detection for new obstruction types:

```python
# Add to OBSTRUCTION_PATTERNS in browser_manager.py
OBSTRUCTION_PATTERNS["custom_overlay"] = {
    "selectors": [
        "[class*='custom-modal' i]",
        "#custom-overlay",
    ],
    "dismiss": [
        ".custom-close-btn",
        "button:has-text('Skip')",
    ],
    "priority": 2  # High priority
}
```

## Statistics Tracking

The BrowserManager tracks obstruction stats:

```python
stats = browser_mgr.get_stats()
print(f"Obstructions detected: {stats['obstructions_detected']}")
print(f"Obstructions dismissed: {stats['obstructions_dismissed']}")
```

## State Management

### Dismissed Obstruction Tracking

The system tracks dismissed obstructions to avoid re-dismissing:

```python
# Internal set of dismissed obstruction IDs
browser_mgr._dismissed_obstructions

# Reset tracking (e.g., on new page)
browser_mgr.reset_obstruction_tracking()
```

### When to Reset Tracking

```python
# Reset when navigating to a new domain
if new_url_domain != current_domain:
    browser_mgr.reset_obstruction_tracking()
```

## Performance Considerations

1. **Detection is fast**: Uses CSS selectors and DOM queries, typically < 500ms
2. **Dismissal is async**: Non-blocking, uses short timeouts (2s max)
3. **Caching**: Tracks dismissed obstructions to avoid re-checking
4. **Selective scanning**: Default mode only dismisses high-priority obstructions

## Limitations

1. **Dynamic obstructions**: Some sites load obstructions after initial page load
2. **Custom implementations**: Sites with unique modal implementations may not be detected
3. **CAPTCHA**: Cannot dismiss CAPTCHA challenges (use separate CAPTCHA handling)
4. **Authentication walls**: Cannot bypass login requirements

## Troubleshooting

### Obstruction Not Detected

If an obstruction isn't detected:

1. Check z-index: `await browser_mgr.get_elements_by_z_index(min_z_index=0)`
2. Inspect element classes/IDs and add to patterns
3. Use aggressive mode: `scan_and_dismiss_obstructions(aggressive=True)`

### Obstruction Not Dismissed

If detected but not dismissed:

1. Check if `dismissible=True`
2. Verify dismiss button selector is correct
3. Try manual dismiss: `await browser_mgr.dismiss_obstruction(obs)`
4. Check logs for specific error

### False Positives

If legitimate elements are being dismissed:

1. Lower the z-index threshold (default: 100)
2. Adjust pattern selectors to be more specific
3. Use non-aggressive mode (only high-priority)

## Testing

Run the test suite:

```bash
cd /mnt/c/ev29/agent
python test_obstruction_handling.py
```

The test suite demonstrates:
- Detection of cookie banners, modals, chat widgets
- Automatic dismissal
- Element clickability checking
- Z-index analysis

## Future Enhancements

Potential improvements:

1. **Machine learning**: Train model to detect obstructions by visual features
2. **Site-specific rules**: Custom dismissal logic per domain
3. **Retry strategies**: Multiple attempts with different methods
4. **Screenshot comparison**: Detect obstructions by comparing before/after
5. **A/B testing**: Try different dismiss methods and learn which works

## Integration with Other Features

### Continuous Perception

Obstruction detection works alongside continuous perception:

```python
# Start perception
await browser_mgr.start_perception()

# Auto-dismiss obstructions when detected
def on_perception_change(state):
    if state.change_detected:
        asyncio.create_task(browser_mgr.scan_and_dismiss_obstructions())

browser_mgr.on_page_change(on_perception_change)
```

### Cascading Recovery

Obstructions are checked during recovery:

```python
# In cascading_recovery.py
if error_type == "element_not_clickable":
    # Try dismissing obstructions
    await browser_mgr.scan_and_dismiss_obstructions(aggressive=True)
    # Retry action
    return await retry_action()
```

### Humanization

Dismissal uses human-like interactions:

```python
# Future: Use BezierCursor for dismissal
from agent.humanization import BezierCursor

cursor = BezierCursor()
await cursor.click_at(page, selector=obstruction.dismiss_selector)
```

## API Reference

### BrowserManager Methods

#### `detect_obstructions() -> List[ObstructionInfo]`

Detect elements that might block interactions.

**Returns:** List of `ObstructionInfo` objects.

#### `dismiss_obstruction(obstruction: ObstructionInfo) -> bool`

Try to dismiss an obstruction.

**Args:**
- `obstruction`: ObstructionInfo object to dismiss

**Returns:** True if successfully dismissed, False otherwise.

#### `scan_and_dismiss_obstructions(aggressive: bool = False) -> int`

Proactively find and dismiss all obstructions.

**Args:**
- `aggressive`: If True, dismiss all obstructions. If False, only high-priority.

**Returns:** Number of obstructions successfully dismissed.

#### `ensure_element_clickable(selector: str, timeout: int = 5000) -> bool`

Ensure element is not obstructed before click.

**Args:**
- `selector`: CSS selector for the target element
- `timeout`: Maximum time to wait for element (milliseconds)

**Returns:** True if element is clickable, False if obstructed.

#### `get_elements_by_z_index(min_z_index: int = 1000) -> List[Dict]`

Get all elements with high z-index (likely overlays).

**Args:**
- `min_z_index`: Minimum z-index to consider

**Returns:** List of element info dicts.

#### `auto_dismiss_on_navigation(url: str) -> int`

Automatically dismiss common obstructions after navigation.

**Args:**
- `url`: The URL that was navigated to

**Returns:** Number of obstructions dismissed.

#### `reset_obstruction_tracking()`

Reset obstruction tracking state.

## Summary

The obstruction handling system provides:

- **Proactive detection** of 6+ common obstruction types
- **Automatic dismissal** with multiple strategies
- **Pre-action checks** to ensure elements are clickable
- **Z-index analysis** for custom overlay detection
- **Statistics tracking** for monitoring and optimization

This makes browser automation more robust and reduces failures from cookie banners, modals, and other overlays.

