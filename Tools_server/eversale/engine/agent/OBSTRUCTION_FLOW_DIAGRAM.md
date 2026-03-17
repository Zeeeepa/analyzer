# Obstruction Detection & Handling Flow Diagram

## Overall Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     BrowserManager                              │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐   │
│  │         OBSTRUCTION DETECTION ENGINE                   │   │
│  │                                                          │   │
│  │  1. detect_obstructions()                               │   │
│  │     ├─ Scan DOM with pattern selectors                 │   │
│  │     ├─ Check z-index & viewport coverage               │   │
│  │     ├─ Find dismiss buttons                             │   │
│  │     └─ Return List[ObstructionInfo]                     │   │
│  │                                                          │   │
│  │  2. get_elements_by_z_index()                           │   │
│  │     └─ Find high z-index overlays (z >= 1000)          │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐   │
│  │         OBSTRUCTION DISMISSAL ENGINE                   │   │
│  │                                                          │   │
│  │  3. dismiss_obstruction(obs)                            │   │
│  │     ├─ Try click_close (close button)                  │   │
│  │     ├─ Try press_esc (ESC key)                         │   │
│  │     └─ Try click_outside (backdrop)                     │   │
│  │                                                          │   │
│  │  4. scan_and_dismiss_obstructions(aggressive)           │   │
│  │     ├─ Detect all obstructions                          │   │
│  │     ├─ Sort by priority                                 │   │
│  │     └─ Dismiss each dismissible obstruction             │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐   │
│  │         PRE-ACTION VALIDATION                          │   │
│  │                                                          │   │
│  │  5. ensure_element_clickable(selector)                  │   │
│  │     ├─ Find target element                              │   │
│  │     ├─ Check what's at element center                  │   │
│  │     ├─ If obstructed: scan_and_dismiss(aggressive)     │   │
│  │     └─ Re-check clickability                            │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐   │
│  │         POST-ACTION AUTO-DISMISS                       │   │
│  │                                                          │   │
│  │  6. auto_dismiss_on_navigation(url)                     │   │
│  │     ├─ Wait for page to settle (1.5s)                  │   │
│  │     └─ scan_and_dismiss_obstructions()                 │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐   │
│  │         STATE TRACKING                                 │   │
│  │                                                          │   │
│  │  • _dismissed_obstructions: Set[str]                    │   │
│  │  • _obstruction_check_count: int                        │   │
│  │  • stats['obstructions_detected']                       │   │
│  │  • stats['obstructions_dismissed']                      │   │
│  └────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Detection Flow

```
detect_obstructions()
    │
    ├─► For each pattern type (cookie_banner, modal, chat_widget, ...)
    │       │
    │       ├─► For each selector pattern
    │       │       │
    │       │       ├─► query_selector_all(selector)
    │       │       │
    │       │       ├─► For each matching element
    │       │       │       │
    │       │       │       ├─► Check visibility
    │       │       │       ├─► Get z-index & bounding box
    │       │       │       ├─► Calculate viewport coverage %
    │       │       │       ├─► Skip if z-index < 100 AND coverage < 10%
    │       │       │       │
    │       │       │       ├─► Find dismiss method
    │       │       │       │   ├─► Try dismiss selectors (close button)
    │       │       │       │   └─► Fallback to ESC or click_outside
    │       │       │       │
    │       │       │       └─► Create ObstructionInfo
    │       │       │
    │       │       └─► Continue to next selector
    │       │
    │       └─► Continue to next pattern type
    │
    ├─► Sort obstructions by priority (1=highest)
    ├─► Update stats['obstructions_detected']
    └─► Return List[ObstructionInfo]
```

## Dismissal Flow

```
scan_and_dismiss_obstructions(aggressive)
    │
    ├─► detect_obstructions()
    │       │
    │       └─► Get List[ObstructionInfo]
    │
    ├─► For each obstruction (sorted by priority)
    │       │
    │       ├─► Skip if priority > 2 (unless aggressive=True)
    │       ├─► Skip if not dismissible
    │       ├─► Skip if already dismissed
    │       │
    │       ├─► dismiss_obstruction(obs)
    │       │       │
    │       │       ├─► If method = "click_close"
    │       │       │   ├─► Find dismiss button
    │       │       │   ├─► Click button
    │       │       │   └─► Wait 0.5s for animation
    │       │       │
    │       │       ├─► If method = "press_esc"
    │       │       │   ├─► Press ESC key
    │       │       │   └─► Wait 0.5s
    │       │       │
    │       │       ├─► If method = "click_outside"
    │       │       │   ├─► Click at (10, 10)
    │       │       │   └─► Wait 0.5s
    │       │       │
    │       │       └─► Return True if dismissed
    │       │
    │       ├─► If dismissed:
    │       │   ├─► Mark as dismissed (add to set)
    │       │   └─► Increment dismissed_count
    │       │
    │       └─► Continue to next obstruction
    │
    ├─► Update stats['obstructions_dismissed']
    └─► Return dismissed_count
```

## Pre-Action Check Flow

```
ensure_element_clickable(selector)
    │
    ├─► Wait for element to exist (timeout=5s)
    │
    ├─► Get element bounding box
    │   ├─► center_x = box.x + box.width / 2
    │   └─► center_y = box.y + box.height / 2
    │
    ├─► Check what element is at (center_x, center_y)
    │   └─► elementFromPoint(center_x, center_y)
    │
    ├─► If top element == target element
    │   └─► Return True (already clickable)
    │
    ├─► Else (element is obstructed)
    │   │
    │   ├─► scan_and_dismiss_obstructions(aggressive=True)
    │   │
    │   ├─► Wait 0.5s for animations
    │   │
    │   ├─► Re-check elementFromPoint()
    │   │
    │   └─► If top element == target element NOW
    │       ├─► Return True (now clickable)
    │       └─► Else: Return False (still obstructed)
```

## Integration with ReAct Loop

```
ReAct Loop (brain_enhanced_v2.py)
    │
    ├─► BEFORE ACTION: playwright_click
    │       │
    │       ├─► ensure_element_clickable(selector)
    │       │   ├─► If False: log warning
    │       │   └─► If True: proceed
    │       │
    │       └─► Execute click
    │
    ├─► EXECUTE ACTION
    │       │
    │       ├─► Try: mcp.call_tool(action_name, args)
    │       │
    │       └─► Catch Exception
    │           ├─► If "not clickable" or "obscured" in error:
    │           │   ├─► scan_and_dismiss_obstructions(aggressive=True)
    │           │   └─► Retry action
    │           └─► Else: re-raise
    │
    ├─► AFTER ACTION: playwright_navigate
    │       │
    │       └─► auto_dismiss_on_navigation(url)
    │           ├─► Wait 1.5s for page to settle
    │           └─► scan_and_dismiss_obstructions()
    │
    └─► Continue to next action
```

## Obstruction Types & Detection

```
┌─────────────────────────────────────────────────────────────────┐
│                  OBSTRUCTION PATTERNS                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Priority 1 (ALWAYS DISMISS)                                    │
│  ├─ cookie_banner                                               │
│  │   ├─ Selectors: [class*='cookie'], [class*='consent'], ...  │
│  │   └─ Dismiss: [class*='accept'], button:has-text('Accept')  │
│  │                                                               │
│  └─ age_verification                                            │
│      ├─ Selectors: [class*='age-gate'], [id*='age-verify']     │
│      └─ Dismiss: button:has-text('Yes'), button:has-text('18') │
│                                                                  │
│  Priority 2 (HIGH - DISMISS BY DEFAULT)                         │
│  ├─ modal                                                       │
│  │   ├─ Selectors: [role='dialog'], [aria-modal='true'], ...   │
│  │   └─ Dismiss: .close, [aria-label='Close'], ESC key         │
│  │                                                               │
│  └─ newsletter_popup                                            │
│      ├─ Selectors: [class*='newsletter'][class*='popup']       │
│      └─ Dismiss: .close, button:has-text('No thanks')          │
│                                                                  │
│  Priority 3 (MEDIUM - ONLY IF AGGRESSIVE)                       │
│  └─ chat_widget                                                 │
│      ├─ Selectors: [class*='intercom'], [class*='zendesk']     │
│      └─ Dismiss: [class*='minimize'], [class*='close']         │
│                                                                  │
│  Priority 4 (LOW - ONLY IF AGGRESSIVE)                          │
│  └─ fixed_header                                                │
│      ├─ Selectors: header[style*='fixed']                      │
│      └─ Dismiss: None (scroll past instead)                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Z-Index Analysis

```
get_elements_by_z_index(min_z_index=1000)
    │
    ├─► Get all elements: document.querySelectorAll('*')
    │
    ├─► For each element
    │   ├─► Get computed style z-index
    │   ├─► Skip if z-index = 'auto'
    │   ├─► Skip if z-index < min_z_index
    │   │
    │   ├─► Get bounding box & calculate coverage %
    │   │
    │   ├─► Build selector (tag#id.class)
    │   │
    │   └─► Add to results: {selector, z_index, coverage, visible}
    │
    ├─► Sort by z-index (highest first)
    │
    └─► Return results

Example output:
[
    {selector: "div.modal-overlay", z_index: 9999, coverage: 100.0, visible: true},
    {selector: "div.cookie-banner", z_index: 9000, coverage: 15.0, visible: true},
    {selector: "iframe#chat-widget", z_index: 5000, coverage: 5.0, visible: true},
    ...
]
```

## State Machine

```
OBSTRUCTION STATE MACHINE

┌─────────────┐
│   Initial   │
│   (Clean)   │
└──────┬──────┘
       │
       │ Page loads with obstruction
       ▼
┌─────────────┐
│  Detected   │◄──────────┐
│ (Pending)   │           │
└──────┬──────┘           │
       │                   │
       │ scan_and_dismiss()│
       ▼                   │
┌─────────────┐           │
│ Dismissing  │           │
│ (Active)    │           │ New obstruction appears
└──────┬──────┘           │
       │                   │
       │ dismiss_obstruction()
       ▼                   │
┌─────────────┐           │
│  Dismissed  │           │
│  (Tracked)  │───────────┘
└─────────────┘

_dismissed_obstructions Set:
    ├─ "cookie_banner_[class*='cookie']_50_100"
    ├─ "modal_[role='dialog']_200_300"
    └─ ... (prevents re-dismissing)
```

## Statistics Flow

```
Browser Manager Stats

┌────────────────────────────────────┐
│ stats = {                          │
│   'screenshots_taken': 0,          │
│   'vision_calls': 0,               │
│   'health_checks': 0,              │
│   'reconnect_attempts': 0,         │
│   'recovery_attempts': 0,          │
│   'obstructions_detected': 0,  ←───┼── Incremented in detect_obstructions()
│   'obstructions_dismissed': 0, ←───┼── Incremented in dismiss_obstruction()
│ }                                  │
└────────────────────────────────────┘

Stats updated on:
├─ detect_obstructions()
│  └─ stats['obstructions_detected'] += len(obstructions)
│
└─ dismiss_obstruction()
   └─ stats['obstructions_dismissed'] += 1 (if successful)
```

## Error Handling & Recovery

```
ERROR HANDLING FLOW

Action execution
    │
    ├─► Try: click(selector)
    │       │
    │       └─► Raise: "Element not clickable at point (x, y). Other element would receive the click"
    │
    ├─► Catch Exception
    │       │
    │       ├─► Check error message for keywords:
    │       │   ├─ "not clickable"
    │       │   ├─ "obscured"
    │       │   ├─ "covered"
    │       │   ├─ "blocked"
    │       │   └─ "intercept"
    │       │
    │       ├─► If obstruction-related:
    │       │   ├─► scan_and_dismiss_obstructions(aggressive=True)
    │       │   ├─► If dismissed > 0: retry action
    │       │   └─► Else: raise original error
    │       │
    │       └─► Else: raise error
    │
    └─► Success or final failure
```

This visualization shows the complete flow of obstruction detection, dismissal, and integration with the ReAct loop.
