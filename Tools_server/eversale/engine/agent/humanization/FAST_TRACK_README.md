# FAST_TRACK Mode - High-Speed Automation for Internal Tools

## Overview

FAST_TRACK mode allows you to skip all humanization (bezier curves, typing delays, scroll pauses) for **massive performance gains** when processing high-volume tasks on internal, non-sensitive websites.

### Performance Comparison

| Operation | Normal Mode | FAST_TRACK Mode | Speedup |
|-----------|-------------|-----------------|---------|
| Mouse move (500px) | 150-400ms | <10ms | **40x faster** |
| Type text (50 chars) | 8-12 seconds | <100ms | **100x faster** |
| Scroll to element | 1-3 seconds | <20ms | **150x faster** |
| **1000 form fills** | **3-4 hours** | **2-3 minutes** | **~100x faster** |

## When to Use FAST_TRACK

### ✅ SAFE - Use FAST_TRACK for:

- **Internal dashboards** (company.local, internal-tools.company.com)
- **Local development** (localhost, 127.0.0.1)
- **Admin panels** (behind authentication, not public)
- **Private APIs** (internal microservices)
- **High-volume data entry** (1000+ items on internal systems)
- **Bulk operations** (mass updates on internal DBs)
- **Testing/QA** (automated tests on staging)

### ❌ UNSAFE - NEVER use FAST_TRACK for:

- **Public e-commerce** (Amazon, eBay, Shopify stores)
- **Social media** (LinkedIn, Twitter, Facebook)
- **Government sites** (IRS, DMV, permits)
- **Banking/Financial** (any site with fraud detection)
- **Lead generation** (contact forms on public websites)
- **Web scraping** (public sites with anti-bot measures)
- **Any site where being detected = blocked/banned**

## Safety System

FAST_TRACK includes **automatic safety checks** that prevent it from being used on public websites:

```python
from agent.humanization import is_fast_track_safe, FastTrackSafety

# Automatic whitelist check
is_fast_track_safe("https://localhost:8080")  # ✅ True - safe
is_fast_track_safe("https://internal-crm.company.local")  # ✅ True - .local domain
is_fast_track_safe("https://192.168.1.100")  # ✅ True - private IP

is_fast_track_safe("https://amazon.com")  # ❌ False - public site
is_fast_track_safe("https://linkedin.com")  # ❌ False - bot detection
```

### Default Safe Domains

The following domains/IPs are whitelisted by default:
- `localhost`, `127.0.0.1`, `0.0.0.0`
- `*.local`, `*.test`, `*.dev`
- Private IPs: `192.168.*`, `10.*`, `172.16.*`

### Adding Custom Safe Domains

For your internal tools:

```python
from agent.humanization import get_safety_checker

safety = get_safety_checker()

# Whitelist your internal domain
safety.add_safe_domain("internal-crm.mycompany.com")
safety.add_safe_domain("admin-dashboard.mycompany.com")

# Whitelist with pattern
safety.add_safe_pattern(r'^https://.*\.internal\.mycompany\.com')
```

## Usage Examples

### Basic Usage

```python
from agent.humanization import (
    BezierCursor, HumanTyper, HumanScroller,
    CursorConfig, TypingConfig, ScrollConfig,
    is_fast_track_safe
)

url = "https://internal-dashboard.company.local"

# Check if FAST_TRACK is safe
if is_fast_track_safe(url):
    # Enable FAST_TRACK mode
    cursor = BezierCursor(CursorConfig(fast_track=True))
    typer = HumanTyper(TypingConfig(fast_track=True))
    scroller = HumanScroller(ScrollConfig(fast_track=True))

    print("FAST_TRACK enabled - processing at maximum speed")
else:
    # Use normal humanization
    cursor = BezierCursor()
    typer = HumanTyper()
    scroller = HumanScroller()

    print("Using full humanization for safety")

# Use as normal
await cursor.click_at(page, selector=".submit")
await typer.type_text(page, "Data", selector="#input")
await scroller.scroll_to_element(page, "#target")
```

### High-Volume Processing

```python
from agent.humanization import (
    BezierCursor, CursorConfig,
    HumanTyper, TypingConfig,
    is_fast_track_safe
)

async def process_bulk_orders(page, orders):
    """Process 1000+ orders on internal admin panel."""

    url = await page.url

    # Enable FAST_TRACK for internal tools
    if is_fast_track_safe(url):
        cursor = BezierCursor(CursorConfig(fast_track=True))
        typer = HumanTyper(TypingConfig(fast_track=True))
    else:
        cursor = BezierCursor()
        typer = HumanTyper()

    for i, order in enumerate(orders):
        # Click order
        await cursor.click_at(page, selector=f"#order-{order.id}")

        # Fill status
        await typer.type_text(page, order.status, selector="#status")

        # Fill notes
        await typer.type_text(page, order.notes, selector="#notes")

        # Submit
        await cursor.click_at(page, selector=".save-btn")

        if i % 100 == 0:
            print(f"Processed {i}/{len(orders)} orders")

    print(f"✅ Completed {len(orders)} orders")
```

### Automatic Safety Enforcement

```python
from agent.humanization import (
    CursorConfig, TypingConfig, ScrollConfig,
    enforce_fast_track_safety
)

# Create configs with FAST_TRACK enabled
cursor_config = CursorConfig(fast_track=True)
typer_config = TypingConfig(fast_track=True)
scroller_config = ScrollConfig(fast_track=True)

# Enforce safety - automatically disables FAST_TRACK if URL is unsafe
url = await page.url
enforce_fast_track_safety(url, cursor_config, typer_config, scroller_config)

# Now configs are safe to use - FAST_TRACK will be disabled if needed
cursor = BezierCursor(cursor_config)
typer = HumanTyper(typer_config)
scroller = HumanScroller(scroller_config)
```

### Orchestrator Integration

For orchestrators that manage multiple tasks:

```python
class TaskOrchestrator:
    def __init__(self):
        self.safety = get_safety_checker()

    async def execute_task(self, task):
        """Execute task with appropriate humanization level."""

        # Determine if FAST_TRACK is safe
        is_safe = self.safety.is_safe(task.url)

        # Configure humanization
        if is_safe and task.volume > 100:
            # High volume + safe domain = FAST_TRACK
            logger.info(f"Using FAST_TRACK for {task.name} ({task.volume} items)")
            cursor_config = CursorConfig(fast_track=True)
            typer_config = TypingConfig(fast_track=True)
            scroller_config = ScrollConfig(fast_track=True)
        else:
            # Low volume or public site = full humanization
            logger.info(f"Using full humanization for {task.name}")
            cursor_config = CursorConfig(fast_track=False)
            typer_config = TypingConfig(fast_track=False)
            scroller_config = ScrollConfig(fast_track=False)

        # Execute task with appropriate config
        cursor = BezierCursor(cursor_config)
        typer = HumanTyper(typer_config)
        scroller = HumanScroller(scroller_config)

        await self.run_task_actions(task, cursor, typer, scroller)
```

## How It Works

### Normal Mode (Humanization Enabled)

```python
# Bezier curve calculation
control_points = generate_control_points(start, end)  # ~5ms
curve = generate_bezier_curve(control_points)  # ~10ms
curve = apply_distortion(curve)  # Tremor simulation ~5ms
curve = apply_easing(curve)  # Fitts's Law ~3ms

# Execute movement (100+ points)
for i, (x, y) in enumerate(curve):
    await page.mouse.move(x, y)
    await asyncio.sleep(delay)  # 80-400ms total
```

### FAST_TRACK Mode (Humanization Disabled)

```python
# Direct movement
await page.mouse.move(target_x, target_y)  # <5ms
# No delays, no curve calculation, instant
```

### Typing Comparison

**Normal Mode:**
```python
# Type "Hello World" (11 chars)
# - Keystroke delays: ~280 CPM = ~210ms per char
# - Error injection: 1% chance + correction
# - Thinking pauses: 150-400ms at word boundaries
# - Fatigue modeling: slowdown over time
# Total: ~2.5-4 seconds
```

**FAST_TRACK Mode:**
```python
# Type "Hello World" (11 chars)
await page.keyboard.type("Hello World")  # <50ms
# No delays, no errors, instant
```

## Logging

FAST_TRACK mode logs when activated:

```
[INFO] FAST_TRACK mode enabled: Using direct cursor movement (no humanization)
[INFO] FAST_TRACK mode enabled: Using instant typing (no humanization)
[INFO] FAST_TRACK mode enabled: Using instant scrolling (no humanization)
```

When rejected for safety:

```
[WARNING] FAST_TRACK REJECTED for 'amazon.com': Not in whitelist (strict mode).
          Using full humanization to avoid detection.
          To enable FAST_TRACK, add domain to whitelist.
```

## Best Practices

### 1. Always Check Safety

```python
# ✅ Good
if is_fast_track_safe(url):
    config = CursorConfig(fast_track=True)

# ❌ Bad - don't hardcode
config = CursorConfig(fast_track=True)  # Unsafe!
```

### 2. Use for High-Volume Only

```python
# ✅ Good - high volume justifies FAST_TRACK
if is_fast_track_safe(url) and len(items) > 100:
    config = CursorConfig(fast_track=True)

# ❌ Bad - overkill for 5 items
if is_fast_track_safe(url):  # Only 5 items
    config = CursorConfig(fast_track=True)
```

### 3. Log FAST_TRACK Usage

```python
# ✅ Good
if is_fast_track_safe(url) and task.volume > 100:
    logger.info(f"FAST_TRACK enabled for {task.name} ({task.volume} items)")
    config = CursorConfig(fast_track=True)
else:
    logger.info(f"Full humanization for {task.name}")
    config = CursorConfig(fast_track=False)
```

### 4. Whitelist Conservatively

```python
# ✅ Good - specific internal domains
safety.add_safe_domain("internal-crm.mycompany.com")

# ❌ Bad - too broad
safety.add_safe_pattern(r'.*')  # Whitelists EVERYTHING - dangerous!
```

## Performance Tuning

### Minimal Delays (Still Fast, Slightly Safer)

If you want speed but some minimal humanization:

```python
config = CursorConfig(
    fast_track=False,  # Keep humanization
    min_duration_ms=20,  # But make it faster
    max_duration_ms=80,
    overshoot_chance=0.0,  # Disable overshoot
    distortion_frequency=0.0  # Disable tremor
)
```

### Hybrid Approach

```python
# FAST_TRACK for clicks, humanized typing
cursor = BezierCursor(CursorConfig(fast_track=True))
typer = HumanTyper(TypingConfig(fast_track=False))  # Still humanized
```

## Troubleshooting

### "FAST_TRACK rejected for my internal domain"

Add your domain to the whitelist:

```python
from agent.humanization import get_safety_checker

safety = get_safety_checker()
safety.add_safe_domain("your-internal-site.com")
```

### "Performance not improving"

Ensure all three modules are in FAST_TRACK:

```python
# All three needed for max speed
cursor = BezierCursor(CursorConfig(fast_track=True))
typer = HumanTyper(TypingConfig(fast_track=True))
scroller = HumanScroller(ScrollConfig(fast_track=True))
```

### "Accidentally enabled on public site"

The safety system should prevent this, but to force disable:

```python
config.fast_track = False  # Force disable
```

## Summary

- **FAST_TRACK = 40-150x faster** for high-volume tasks
- **Only use on internal tools** - automatic safety checks enforce this
- **Whitelist your domains** for custom internal tools
- **Log usage** for debugging and auditing
- **Perfect for 100+ item processing** on admin panels

For public-facing sites, **always use normal humanization** to avoid detection.
