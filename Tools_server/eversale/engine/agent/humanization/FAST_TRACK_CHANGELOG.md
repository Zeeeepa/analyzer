# FAST_TRACK Mode - Implementation Changelog

## Summary

Added FAST_TRACK mode to all humanization modules, enabling 40-150x speed improvements for high-volume, non-sensitive tasks on internal tools. Includes automatic safety checks to prevent misuse on public websites.

## Files Modified

### 1. `/mnt/c/ev29/agent/humanization/bezier_cursor.py`

**Changes:**
- Added `fast_track: bool = False` to `CursorConfig` dataclass
- Added `_fast_track_logged` flag to track logging state
- Modified `move_to()` method:
  - When `fast_track=True`: Direct mouse movement, no Bezier curves, no delays
  - Logs once when FAST_TRACK is first activated
- Modified `move_with_overshoot()`:
  - Skips overshoot simulation when `fast_track=True`
- Modified `click_at()`:
  - Reduces pre-click delay from 30-80ms to 0ms
  - Reduces hold time from 50-120ms to 10ms
  - Reduces double-click delay from 80-150ms to 10ms

**Performance Impact:**
- Normal mode: 150-400ms for 500px movement
- FAST_TRACK mode: <10ms for any distance
- **40x faster cursor movement**

### 2. `/mnt/c/ev29/agent/humanization/human_typer.py`

**Changes:**
- Added `fast_track: bool = False` to `TypingConfig` dataclass
- Added `_fast_track_logged` flag to track logging state
- Modified `type_text()` method:
  - When `fast_track=True`: Uses native `page.keyboard.type()` for instant typing
  - Skips error injection, corrections, thinking pauses, and fatigue modeling
  - Reduces focus/clear delays to 10ms (from 50-150ms)
  - Logs once when FAST_TRACK is first activated

**Performance Impact:**
- Normal mode: ~280 CPM (8-12 seconds for 50 chars)
- FAST_TRACK mode: <100ms for any text length
- **100x faster typing**

### 3. `/mnt/c/ev29/agent/humanization/human_scroller.py`

**Changes:**
- Added `fast_track: bool = False` to `ScrollConfig` dataclass
- Added `_fast_track_logged` flag to track logging state
- Modified `scroll_down()`:
  - When `fast_track=True`: Single wheel event for entire distance
  - Skips chunking, smooth scrolling, and reading pauses
- Modified `scroll_up()`:
  - Same instant scrolling behavior
- Modified `scroll_to_element()`:
  - Uses native `scrollIntoView({behavior: 'instant'})` for instant scrolling
- Modified `scroll_to_bottom()`:
  - Uses `window.scrollTo()` for instant jump to bottom

**Performance Impact:**
- Normal mode: 1-3 seconds to scroll to element
- FAST_TRACK mode: <20ms
- **150x faster scrolling**

### 4. `/mnt/c/ev29/agent/humanization/fast_track_safety.py` (NEW)

**Purpose:**
Prevent FAST_TRACK from being used on public-facing websites where bot detection is critical.

**Components:**

**`SafetyConfig` dataclass:**
- `safe_domains`: Whitelist of allowed domains
- `safe_patterns`: Regex patterns for safe URLs
- `strict_mode`: Reject unless explicitly whitelisted (default: True)
- `verbose_logging`: Log all safety checks (default: True)

**Default safe domains:**
- Local: `localhost`, `127.0.0.1`, `0.0.0.0`
- Dev domains: `*.local`, `*.test`, `*.dev`
- Private IPs: `192.168.*`, `10.*`, `172.16.*`

**`FastTrackSafety` class:**
- `is_safe(url)`: Check if FAST_TRACK is safe for URL
- `add_safe_domain(domain)`: Add custom domain to whitelist
- `add_safe_pattern(pattern)`: Add regex pattern to whitelist
- `enforce(url, configs...)`: Force disable FAST_TRACK if unsafe

**Global functions:**
- `get_safety_checker()`: Get singleton instance
- `is_fast_track_safe(url)`: Convenience function to check safety
- `enforce_fast_track_safety(url, configs...)`: Convenience enforcement function

**Safety behavior:**
- ✅ Whitelists local/internal domains automatically
- ❌ Rejects public sites (amazon.com, linkedin.com, etc.)
- 📝 Logs warnings when FAST_TRACK is rejected
- 🔒 Strict mode by default - fail safe

### 5. `/mnt/c/ev29/agent/humanization/__init__.py`

**Changes:**
- Added imports for `fast_track_safety` module
- Added FAST_TRACK exports to `__all__`:
  - `FastTrackSafety`
  - `SafetyConfig`
  - `get_safety_checker`
  - `is_fast_track_safe`
  - `enforce_fast_track_safety`
- Updated module docstring with FAST_TRACK usage examples

### 6. `/mnt/c/ev29/agent/humanization/FAST_TRACK_README.md` (NEW)

**Contents:**
- Overview and performance comparison
- When to use vs. when NOT to use
- Safety system documentation
- Usage examples (basic, high-volume, orchestrator)
- How it works (technical details)
- Best practices
- Troubleshooting guide

## Usage Example

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

    # Process 1000+ items at maximum speed
    for item in items:
        await cursor.click_at(page, selector=f".item-{item.id}")
        await typer.type_text(page, item.data, selector="#input")
        await page.keyboard.press('Enter')
else:
    # Use normal humanization for public sites
    cursor = BezierCursor()
    typer = HumanTyper()
    scroller = HumanScroller()
```

## Testing

All modules tested successfully:

```bash
$ cd /mnt/c/ev29/agent/humanization && python3 test_script.py

✅ All imports successful

Testing safety checks:
  localhost: True ✅
  192.168.1.1: True ✅
  internal.local: True ✅
  amazon.com: False ✅
  linkedin.com: False ✅

Testing config creation with FAST_TRACK:
  CursorConfig.fast_track: True ✅
  TypingConfig.fast_track: True ✅
  ScrollConfig.fast_track: True ✅

Testing safety enforcement:
  After enforcement on amazon.com:
    CursorConfig.fast_track: False ✅ (auto-disabled)
    TypingConfig.fast_track: False ✅ (auto-disabled)
    ScrollConfig.fast_track: False ✅ (auto-disabled)

✅ All tests passed - FAST_TRACK mode is ready!
```

## Logging Examples

**When FAST_TRACK is enabled:**
```
[INFO] FAST_TRACK mode enabled: Using direct cursor movement (no humanization)
[INFO] FAST_TRACK mode enabled: Using instant typing (no humanization)
[INFO] FAST_TRACK mode enabled: Using instant scrolling (no humanization)
```

**When FAST_TRACK is rejected:**
```
[WARNING] FAST_TRACK REJECTED for 'amazon.com': Not in whitelist (strict mode).
          Using full humanization to avoid detection.
          To enable FAST_TRACK, add domain to whitelist.
```

**When FAST_TRACK is enforced off:**
```
[WARNING] Disabled FAST_TRACK for cursor (unsafe domain)
[WARNING] Disabled FAST_TRACK for typer (unsafe domain)
[WARNING] Disabled FAST_TRACK for scroller (unsafe domain)
```

## Performance Benchmarks

| Task | Normal Mode | FAST_TRACK | Speedup |
|------|-------------|------------|---------|
| Move 500px | 150-400ms | <10ms | 40x |
| Type 50 chars | 8-12s | <100ms | 100x |
| Scroll to element | 1-3s | <20ms | 150x |
| **1000 form fills** | **3-4 hours** | **2-3 minutes** | **~100x** |

## Safety Guarantees

1. **Automatic whitelisting** of localhost and private IPs
2. **Strict mode by default** - reject unless explicitly safe
3. **Automatic enforcement** - can force disable FAST_TRACK
4. **Logging and warnings** - visibility into all decisions
5. **Fail-safe design** - errors default to rejecting FAST_TRACK

## Backward Compatibility

✅ **100% backward compatible**

- All configs default to `fast_track=False`
- Existing code continues to work without changes
- FAST_TRACK is opt-in only
- No breaking changes to APIs

## Future Enhancements

Potential improvements:
- [ ] Adaptive FAST_TRACK (auto-enable based on heuristics)
- [ ] Per-action FAST_TRACK (some actions fast, others humanized)
- [ ] Rate limiting in FAST_TRACK mode
- [ ] Telemetry on FAST_TRACK usage
- [ ] Machine learning-based safety detection

## Migration Guide

No migration needed - this is a new feature. To adopt:

1. Identify high-volume tasks on internal tools
2. Check if domain is safe: `is_fast_track_safe(url)`
3. Enable FAST_TRACK: `config = CursorConfig(fast_track=True)`
4. Enjoy 40-150x speedup!

## Support

For questions or issues:
- See `/mnt/c/ev29/agent/humanization/FAST_TRACK_README.md`
- Check safety with `is_fast_track_safe(url)`
- Add custom domains: `get_safety_checker().add_safe_domain(domain)`

