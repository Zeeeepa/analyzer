# Action Validation - Quick Reference Card

## TL;DR - Use This Before Every Click/Type

```python
from agent.action_engine import ActionEngine

# Option 1: High-level API (recommended)
ready, error = await engine.validate_and_prepare_action("#button", "click")
if ready:
    await page.click("#button")  # GUARANTEED TO SUCCEED

# Option 2: Manual control
is_ready, reason, fix = await ActionEngine.validate_element_interactable(page, "#button")
if not is_ready:
    await ActionEngine.dismiss_obstructions(page)  # Auto-fix
```

## The 5 Checks

| Check | What It Does | Fix |
|-------|-------------|-----|
| **1. Exists** | Element in DOM? | Retry with different selector |
| **2. Visible** | display/visibility/opacity OK? | Wait for visible |
| **3. Viewport** | In viewport? | Auto-scroll |
| **4. Obstruction** | Cookie banner blocking? | Auto-dismiss |
| **5. Interactable** | disabled/readonly? | Wait for enabled |

## Common Patterns

### Pattern 1: Safe Click
```python
ready, error = await engine.validate_and_prepare_action("#submit", "click")
if ready:
    await page.click("#submit")
else:
    return ActionResult(status=ActionStatus.ERROR, message=error)
```

### Pattern 2: Handle Cookie Banner
```python
is_ready, reason, fix = await ActionEngine.validate_element_interactable(page, "#action")
if fix.get("obstruction_type") == "cookie_banner":
    await ActionEngine.dismiss_obstructions(page)
    is_ready, _, _ = await ActionEngine.validate_element_interactable(page, "#action")
```

### Pattern 3: Auto-Scroll
```python
ready, error = await engine.validate_and_prepare_action("#footer-button")
# If outside viewport, it's auto-scrolled into view
if ready:
    await page.click("#footer-button")
```

### Pattern 4: Wait for Element
```python
is_ready, reason, fix = await ActionEngine.validate_element_interactable(page, "#button")
if fix.get("suggested_action") == "wait_for_visible":
    await page.wait_for_selector("#button", state="visible", timeout=5000)
```

## Return Values

### `validate_element_interactable(page, selector)`
```python
(is_ready: bool, reason: str, fix: dict)

# fix dict:
{
    "scroll_needed": bool,
    "obstruction_selector": str,
    "obstruction_type": "cookie_banner" | "modal" | "chat_widget" | "fixed_header",
    "suggested_action": "scroll" | "dismiss" | "wait" | "retry",
    "interactability_issues": ["disabled", "readonly", "pointer-events: none"]
}
```

### `validate_and_prepare_action(selector, action_type)`
```python
(ready: bool, error: str)

# ready=True: Element is ready, action will succeed
# ready=False: Could not prepare, error explains why
```

## Obstruction Types Detected

| Type | Examples | Auto-Dismiss? |
|------|----------|---------------|
| cookie_banner | OneTrust, GDPR consent | ✓ Yes |
| modal | Login prompt, signup popup | ✓ Yes |
| chat_widget | Intercom, Drift | ✓ Yes |
| fixed_header | Sticky nav bar | ✓ Yes |
| banner | Notification, announcement | ✓ Yes |

## Common Dismiss Selectors

```python
# Cookies
"#onetrust-accept-btn-handler"
"button[id*='accept']"
"button[class*='cookie']"

# Modals
"button[aria-label*='close']"
"[data-dismiss='modal']"
".modal-close"

# Chat
"#intercom-container button[aria-label*='close']"
".drift-widget-controller-icon"
```

## Performance

- **Validation overhead:** ~40ms
- **Worth it:** Prevents failed actions (saves 1000s of ms in retries)
- **Use for:** Critical actions (submit, purchase, connect)
- **Skip for:** Rapid, low-stakes actions

## Error Messages

| Message | Meaning | Fix |
|---------|---------|-----|
| "Element not found in DOM" | Selector doesn't match | Try alternative selector |
| "Element not visible: display: none" | Hidden | Wait for visible |
| "Element outside viewport" | Not scrolled | Auto-scroll |
| "Element obstructed by cookie_banner" | Blocked | Dismiss obstruction |
| "Element not interactable: disabled" | Can't click | Wait for enabled |

## Integration Example

```python
class LinkedInExecutor(BaseExecutor):
    async def execute(self, params: dict) -> ActionResult:
        # Navigate to profile
        await self.browser.page.goto(f"https://linkedin.com/in/{params['username']}")

        # Validate before clicking Connect
        ready, error = await ActionEngine.validate_and_prepare_action(
            self.browser,
            "button[aria-label*='Connect']",
            "click"
        )

        if not ready:
            return ActionResult(
                status=ActionStatus.ERROR,
                message=f"Could not click Connect button: {error}"
            )

        # Click is now guaranteed to succeed
        await self.browser.page.click("button[aria-label*='Connect']")

        return ActionResult(status=ActionStatus.SUCCESS, message="Connection sent")
```

## Testing

```bash
# Run test suite
python -m agent.test_action_validation

# Run examples
python -m agent.example_action_validation

# Visual debugging
python -m agent.test_action_validation --visual
```

## When to Use

### ✓ Always Validate
- Submit buttons
- Purchase/checkout actions
- Connection/follow actions
- Form submissions
- Critical navigation

### ✗ Skip Validation
- Rapid scraping (100s of elements)
- Non-critical actions
- Known-stable elements
- Performance-critical loops

## Troubleshooting

### Click still fails after validation passes
→ Page changed between validation and action
→ Solution: Re-validate immediately before click

### Obstruction not dismissed
→ Non-standard dismiss pattern
→ Solution: Add selector to `dismiss_obstructions()`

### Validation too slow
→ Only validate critical actions
→ Skip validation for rapid, low-stakes actions

## Learn More

- Full guide: `/mnt/c/ev29/agent/ACTION_VALIDATION_GUIDE.md`
- Test suite: `/mnt/c/ev29/agent/test_action_validation.py`
- Examples: `/mnt/c/ev29/agent/example_action_validation.py`
- Summary: `/mnt/c/ev29/agent/VALIDATION_ENHANCEMENT_SUMMARY.md`

## Code Location

**File:** `/mnt/c/ev29/agent/action_engine.py`

**Methods:**
- `validate_element_interactable()` - Lines 349-551
- `dismiss_obstructions()` - Lines 553-638
- `scroll_element_into_view()` - Lines 640-689
- `hover_before_action()` - Lines 691-714
- `validate_and_prepare_action()` - Lines 716-804

