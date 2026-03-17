# Action Validation Flow Diagram

## High-Level Flow: `validate_and_prepare_action()`

```
┌─────────────────────────────────────────────────────────────┐
│                    USER WANTS TO CLICK                      │
│                     await page.click("#button")             │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│            STEP 1: Validate Element                         │
│    is_ready, reason, fix = validate_element_interactable()  │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ├─────► is_ready=True? ──────┐
                      │                             │
                      ▼                             ▼
                  is_ready=False          ┌─────────────────┐
                      │                   │ HOVER & RETURN  │
                      │                   │   ready=True    │
                      ▼                   └─────────────────┘
┌─────────────────────────────────────────────────────────────┐
│         STEP 2: Check Fix Suggestion                        │
│         suggested_action = fix.get("suggested_action")      │
└─────────────────────┬───────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┬──────────────┐
        │             │             │              │
        ▼             ▼             ▼              ▼
   scroll_into   dismiss_      wait_for_    retry_with_alt
      _view     obstruction    visible         _selector
        │             │             │              │
        │             │             │              │
        ▼             ▼             ▼              ▼
┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐
│   SCROLL   │ │  DISMISS   │ │   WAIT     │ │  RETURN  │
│  ELEMENT   │ │ OBSTRUCTION│ │  5 SECS    │ │  ERROR   │
└──────┬─────┘ └──────┬─────┘ └──────┬─────┘ └──────────┘
       │              │              │
       │              │              │
       └──────────────┴──────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│           STEP 3: Re-Validate After Fix                     │
│    is_ready, reason, _ = validate_element_interactable()    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ├─────► is_ready=True? ──────┐
                      │                             │
                      ▼                             ▼
                 is_ready=False          ┌─────────────────┐
                      │                  │ HOVER & RETURN  │
                      │                  │   ready=True    │
                      ▼                  └─────────────────┘
            ┌─────────────────┐
            │  RETURN ERROR   │
            │  Could not fix  │
            └─────────────────┘
```

## Detailed Validation Checks: `validate_element_interactable()`

```
┌─────────────────────────────────────────────────────────────┐
│             validate_element_interactable(page, selector)   │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │  CHECK 1: Element Exists?   │
        │  element = query_selector() │
        └─────────┬───────────────────┘
                  │
         ┌────────┴────────┐
         │                 │
         ▼                 ▼
      EXISTS           DOESN'T EXIST
         │                 │
         │                 └──► RETURN (False, "Element not found",
         │                              {suggested_action: "retry_with_alt"})
         │
         ▼
        ┌──────────────────────────────┐
        │  CHECK 2: Visibility         │
        │  - display != none?          │
        │  - visibility != hidden?     │
        │  - opacity > 0?              │
        │  - width > 0 && height > 0?  │
        └─────────┬────────────────────┘
                  │
         ┌────────┴────────┐
         │                 │
         ▼                 ▼
      VISIBLE          NOT VISIBLE
         │                 │
         │                 └──► RETURN (False, "Element not visible: [reason]",
         │                              {suggested_action: "wait_for_visible"})
         │
         ▼
        ┌──────────────────────────────┐
        │  CHECK 3: In Viewport?       │
        │  box = bounding_box()        │
        │  viewport = innerWidth/Height│
        └─────────┬────────────────────┘
                  │
         ┌────────┴────────┐
         │                 │
         ▼                 ▼
    IN VIEWPORT     OUTSIDE VIEWPORT
         │                 │
         │                 └──► RETURN (False, "Element outside viewport",
         │                              {scroll_needed: true, coords: {...}})
         │
         ▼
        ┌──────────────────────────────────────┐
        │  CHECK 4: Obstruction? (CRITICAL!)   │
        │  topEl = elementFromPoint(x, y)      │
        │  Is topEl the target element?        │
        └─────────┬────────────────────────────┘
                  │
         ┌────────┴────────┐
         │                 │
         ▼                 ▼
    NOT OBSTRUCTED     OBSTRUCTED
         │                 │
         │                 ├──► Identify blocker type
         │                 │    (cookie_banner, modal, chat, etc.)
         │                 │
         │                 └──► RETURN (False, "Element obstructed by [type]",
         │                              {obstruction_type: "...",
         │                               obstruction_selector: "...",
         │                               suggested_action: "dismiss"})
         │
         ▼
        ┌──────────────────────────────┐
        │  CHECK 5: Interactable?      │
        │  - disabled?                 │
        │  - readonly?                 │
        │  - pointer-events: none?     │
        │  - aria-disabled?            │
        └─────────┬────────────────────┘
                  │
         ┌────────┴────────┐
         │                 │
         ▼                 ▼
    INTERACTABLE      NOT INTERACTABLE
         │                 │
         │                 └──► RETURN (False, "Not interactable: [issues]",
         │                              {interactability_issues: [...]})
         │
         ▼
    ┌──────────────────────────┐
    │  ALL CHECKS PASSED!      │
    │  RETURN (True, "Ready", │
    │          None)           │
    └──────────────────────────┘
```

## Obstruction Detection Detail

```
┌─────────────────────────────────────────────────────────────┐
│              OBSTRUCTION CHECK PROCESS                      │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────┐
        │  Get element bounding box    │
        │  box = {x, y, width, height} │
        └──────────────┬───────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  Calculate center point      │
        │  x = box.x + width/2         │
        │  y = box.y + height/2        │
        └──────────────┬───────────────┘
                       │
                       ▼
        ┌──────────────────────────────────┐
        │  Ask browser: What element is    │
        │  at this point?                  │
        │  topEl = elementFromPoint(x, y)  │
        └──────────────┬───────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │                           │
         ▼                           ▼
   topEl == target            topEl != target
         │                           │
         │                           ▼
         │              ┌──────────────────────────┐
         │              │  OBSTRUCTION DETECTED!   │
         │              │  blocker = topEl         │
         │              └──────────┬───────────────┘
         │                         │
         │                         ▼
         │              ┌──────────────────────────────────────┐
         │              │  Analyze blocker:                    │
         │              │  - Get id, className, innerText      │
         │              │  - Build selector (#id or .class)    │
         │              │  - Identify type by patterns:        │
         │              │    • "cookie"/"consent" → cookie     │
         │              │    • "modal"/"dialog" → modal        │
         │              │    • "chat"/"intercom" → chat        │
         │              │    • position:fixed → fixed_header   │
         │              └──────────┬───────────────────────────┘
         │                         │
         │                         ▼
         │              ┌──────────────────────────────────────┐
         │              │  Return obstruction details:         │
         │              │  {                                   │
         │              │    obstructed: true,                 │
         │              │    blocker_selector: "#cookie-bar",  │
         │              │    blocker_type: "cookie_banner",    │
         │              │    blocker_text: "Accept Cookies"    │
         │              │  }                                   │
         │              └──────────────────────────────────────┘
         │
         ▼
    ┌──────────────────────────┐
    │  NOT OBSTRUCTED          │
    │  Return {obstructed: false}│
    └──────────────────────────┘
```

## Dismissal Strategies

```
┌─────────────────────────────────────────────────────────────┐
│             dismiss_obstructions(page)                      │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────┐
        │  STRATEGY 1: Press ESC       │
        │  page.keyboard.press("Escape")│
        │  Wait 300ms                  │
        └──────────────┬───────────────┘
                       │
                       ▼  Dismissed? ──► YES ──► RETURN True
                       │
                       ▼ NO
        ┌────────────────────────────────────────────┐
        │  STRATEGY 2: Click Common Dismiss Buttons  │
        │  Try 30+ selectors:                        │
        │  - button[id*='accept']                    │
        │  - #onetrust-accept-btn-handler            │
        │  - button[aria-label*='close']             │
        │  - [data-dismiss='modal']                  │
        │  - etc...                                  │
        └──────────────┬─────────────────────────────┘
                       │
                       ▼  Found & clicked? ──► YES ──► RETURN True
                       │
                       ▼ NO
        ┌──────────────────────────────┐
        │  STRATEGY 3: Click Backdrop  │
        │  Find:                       │
        │  - .modal-backdrop           │
        │  - .overlay-backdrop         │
        │  - [class*='backdrop']       │
        │  Click if visible            │
        └──────────────┬───────────────┘
                       │
                       ▼  Clicked? ──► YES ──► RETURN True
                       │
                       ▼ NO
        ┌──────────────────────────────────────┐
        │  STRATEGY 4: JavaScript Removal      │
        │  Find all elements with:             │
        │  - class/id contains "cookie/modal"  │
        │  - position: fixed                   │
        │  - z-index > 1000                    │
        │  Remove them from DOM                │
        └──────────────┬───────────────────────┘
                       │
                       ▼  Removed > 0? ──► YES ──► RETURN True
                       │
                       ▼ NO
                ┌──────────────┐
                │ RETURN False │
                │ (Could not   │
                │  dismiss)    │
                └──────────────┘
```

## Example: Full Flow for Cookie-Blocked Button

```
User wants to click button on page with cookie banner

1. validate_and_prepare_action("#submit-btn")
   │
   ├─► validate_element_interactable()
   │   │
   │   ├─► CHECK 1: Element exists? ✓ YES
   │   ├─► CHECK 2: Visible? ✓ YES (display:block, opacity:1, 100x40px)
   │   ├─► CHECK 3: In viewport? ✓ YES (at x:200, y:300)
   │   ├─► CHECK 4: Obstructed? ✗ YES!
   │   │              elementFromPoint(200, 300) returns <div id="cookie-banner">
   │   │              Analysis: blocker_type = "cookie_banner"
   │   │
   │   └─► RETURN (False, "Obstructed by cookie_banner",
   │                {suggested_action: "dismiss_obstruction"})
   │
   ├─► DETECTED: suggested_action = "dismiss_obstruction"
   │
   ├─► dismiss_obstructions()
   │   │
   │   ├─► STRATEGY 1: Press ESC → No effect
   │   ├─► STRATEGY 2: Try selectors
   │   │              Found: button#accept-cookies
   │   │              Click it!
   │   │              Cookie banner removed from DOM
   │   │
   │   └─► RETURN True (Dismissed!)
   │
   ├─► RE-VALIDATE: validate_element_interactable()
   │   │
   │   ├─► CHECK 1: Element exists? ✓ YES
   │   ├─► CHECK 2: Visible? ✓ YES
   │   ├─► CHECK 3: In viewport? ✓ YES
   │   ├─► CHECK 4: Obstructed? ✓ NO (elementFromPoint now returns target!)
   │   ├─► CHECK 5: Interactable? ✓ YES (not disabled)
   │   │
   │   └─► RETURN (True, "Element is interactable", None)
   │
   ├─► hover_before_action() → Hover over button
   │
   └─► RETURN (True, None)

2. NOW SAFE TO CLICK!
   await page.click("#submit-btn")  ✓ SUCCESS!
```

## Performance Timeline

```
TIME    ACTION                                      COST
────────────────────────────────────────────────────────────
0ms     Start validate_and_prepare_action()

+10ms   ├─► Check element exists                   10ms
+15ms   ├─► Check visibility (compute styles)       5ms
+20ms   ├─► Check viewport (bounding box)           5ms
+35ms   ├─► Check obstruction (elementFromPoint)   15ms
+45ms   └─► Check interactability                  10ms

        First validation: NOT READY (obstructed)

+45ms   Start dismiss_obstructions()
+50ms   ├─► Press ESC                               5ms
+350ms  ├─► Try dismiss selectors                 300ms
        │   (Found and clicked dismiss button)

+350ms  Start RE-VALIDATE
+360ms  ├─► Check exists                           10ms
+365ms  ├─► Check visible                           5ms
+370ms  ├─► Check viewport                          5ms
+385ms  ├─► Check obstruction                      15ms
+395ms  └─► Check interactable                     10ms

        Second validation: READY!

+400ms  Hover before action                         5ms

+405ms  RETURN ready=True
────────────────────────────────────────────────────────────
TOTAL: ~405ms (but saved 1000s of ms in avoided retries!)
```

## State Machine Diagram

```
                    ┌──────────────┐
                    │   UNKNOWN    │
                    │   (Initial)  │
                    └──────┬───────┘
                           │
                           ▼
        ┌──────────────────────────────────────┐
        │         VALIDATING                   │
        │  (Running 5 checks)                  │
        └──────┬─────────────────┬─────────────┘
               │                 │
               ▼                 ▼
          ┌────────┐      ┌──────────────┐
          │ READY  │      │  NOT READY   │
          └────┬───┘      └──────┬───────┘
               │                 │
               │          ┌──────┴───────┬────────────┐
               │          ▼              ▼            ▼
               │     ┌────────┐   ┌──────────┐  ┌─────────┐
               │     │ SCROLL │   │ DISMISS  │  │  WAIT   │
               │     └────┬───┘   └────┬─────┘  └────┬────┘
               │          │            │             │
               │          └────────────┴─────────────┘
               │                       │
               │                       ▼
               │              ┌──────────────┐
               │              │ RE-VALIDATING│
               │              └──────┬───────┘
               │                     │
               │          ┌──────────┴──────────┐
               │          ▼                     ▼
               │     ┌────────┐          ┌──────────┐
               │     │ READY  │          │  FAILED  │
               │     └────┬───┘          └──────────┘
               │          │
               └──────────┘
                     │
                     ▼
              ┌──────────────┐
              │   HOVERING   │
              └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │   SUCCESS    │
              │ (Ready for   │
              │   action!)   │
              └──────────────┘
```
