# Snapshot Conflicts - Quick Reference

## Five Concurrent Systems

```
┌─────────────────────────────────────────────────────────────┐
│              PAGE SNAPSHOT REQUEST                          │
│                                                             │
│    browser.snapshot(diff_mode=use_diff_mode)               │
└────────────────────────────────────────────────────────────┐
                           ↓
        ┌─────────────────────────────────────┐
        │  SYSTEM 1: A11y Snapshot Cache      │
        │  (URL → full Snapshot, TTL=2s)      │
        │  Config: ENABLE_SNAPSHOT_CACHE      │
        └────────────────────────────────────┐
                           ↓ (if cache miss)
        ┌─────────────────────────────────────┐
        │  Generate Fresh Snapshot             │
        │  (Parse a11y tree, fallback DOM)    │
        └────────────────────────────────────┐
                           ↓
        ┌─────────────────────────────────────┐
        │  SYSTEM 2: Snapshot Diffing         │
        │  (delta-only if diff_mode=True)    │
        │  Config: ENABLE_SNAPSHOT_DIFF       │
        │  Depends on: _previous_snapshot     │
        └────────────────────────────────────┐
                           ↓
        ┌─────────────────────────────────────┐
        │  SYSTEM 3: ConversationContext      │
        │  (adds to UITARS, prunes to 5 SS)   │
        │  Config: max_screenshots=5          │
        └────────────────────────────────────┐
                           ↓
        ┌─────────────────────────────────────┐
        │  SYSTEM 4: HistoryPruner            │
        │  (message-level pruning, 1 SS)      │
        │  Config: KEEP_LAST_N_SCREENSHOTS=1  │
        └────────────────────────────────────┐
                           ↓
        ┌─────────────────────────────────────┐
        │  SYSTEM 5: DOM Diff Cache           │
        │  (separate HTML-based diffing)      │
        │  Status: Not currently integrated   │
        └────────────────────────────────────┘
                           ↓
                    Final Result
        (Snapshot | SnapshotDiff | Pruned)
```

---

## Three Critical Conflicts

### CONFLICT #1: Cache + Diff State Tracking
```
Timeline:
T=0.0s:  snapshot() → fresh Snapshot A
         _previous_snapshot = A
         Cache: A (TTL=2s)

T=0.5s:  User clicks, page changes to B

T=0.8s:  snapshot(diff_mode=True)
         Cache hit! Returns A
         _previous_snapshot still = A
         diff = A.to_diff(A) ← WRONG! Should be A→B

EXPECTED:
         diff = [+ new elements, - removed, ~ changed]

ACTUAL:
         diff = "No changes"  ← BUG!
```

### CONFLICT #2: Multiple Screenshot Limits
```
System           Limit    Trigger              Impact
─────────────────────────────────────────────────────
ConversationContext    5   add_message()        Removes images after 5
HistoryPruner          1   prune()              Removes images after 1
A11y Cache            ∞   Cache store          Full snapshots cached
Snapshot Diff         N/A  diff_mode=True      Doesn't capture images

Cumulative Effect:
1. ConversationContext: Keep 5 screenshots
2. HistoryPruner runs: Reduce to 1 screenshot
3. Result: Aggressive, unpredictable pruning
```

### CONFLICT #3: Type Ambiguity
```
Return Type: Union[Snapshot, SnapshotDiff]

Case 1 (Cache Hit):
  snapshot(diff_mode=True)
  → Cache returns: Snapshot (not SnapshotDiff!)

Case 2 (Cache Miss):
  snapshot(diff_mode=True)
  → Fresh snapshot returns: SnapshotDiff

Caller expects:
  if isinstance(result, SnapshotDiff): ...

Bug: Sometimes gets Snapshot instead!
```

---

## Configuration Conflict Matrix

| Setting | Value | Purpose | Conflicts With |
|---------|-------|---------|-----------------|
| ENABLE_SNAPSHOT_CACHE | True | Speed | ENABLE_SNAPSHOT_DIFF (state tracking) |
| SNAPSHOT_CACHE_TTL | 2.0s | Speed | Misses changes in <2s window |
| ENABLE_SNAPSHOT_DIFF | True | Tokens | ENABLE_SNAPSHOT_CACHE (type/state) |
| ENABLE_HISTORY_PRUNING | True | Tokens | ConversationContext (screenshot limits) |
| KEEP_LAST_N_SCREENSHOTS | 1 | Tokens | ConversationContext (limit=5, conflicts!) |
| ConversationContext.max_screenshots | 5 | UITARS | HistoryPruner (limit=1, conflicts!) |

**Problem:** `KEEP_LAST_N_SCREENSHOTS=1` vs `max_screenshots=5` creates ambiguity.

---

## Impact Assessment

### If All Systems Active (Default)

```
Step 1: Take full snapshot A
  ✓ Cache stores A
  ✓ Diff: _previous = A
  ✓ ConversationContext: A added (1/5)

Step 2: User clicks

Step 3: Request diff snapshot
  PROBLEM 1: Cache returns A (might want fresh)
  PROBLEM 2: Diff compares A→A (no changes detected)
  PROBLEM 3: If B was captured, ConversationContext limits to 5

Step 4: Call LLM
  PROBLEM 4: HistoryPruner removes all but 1 screenshot
  PROBLEM 5: LLM gets A or B, but not both

Result: Inaccurate diffs + aggressive pruning + lost context
```

### Screenshot Death Path
```
Initial: User gets fresh screenshot
  ↓
ConversationContext: OK (1/5 threshold)
  ↓
HistoryPruner: REMOVES! (KEEP_LAST_N_SCREENSHOTS=1, now 0)
  ↓
LLM Call: Screenshot missing
  ↓
Agent confused about page state
```

---

## Enabled By Default

These are all **ON by default** (creating the conflict):

```python
# a11y_config.py

# Caching & Compression
ENABLE_SNAPSHOT_CACHE = True        # Cache full snapshots
ENABLE_SNAPSHOT_DIFF = True         # Send diffs instead
ENABLE_HISTORY_PRUNING = True       # Remove old messages
PRUNE_SCREENSHOTS = True            # Remove images from old messages

# Screenshot Limits
MAX_HISTORY_ITEMS = 10
KEEP_LAST_N_SCREENSHOTS = 1   ← AGGRESSIVE!
ConversationContext.max_screenshots = 5  ← LESS AGGRESSIVE
```

**Result:** THREE different screenshot limits active simultaneously!

---

## Decision Tree: Should You Worry?

```
Are you using simple_agent.py or universal_agent.py?
├─ YES → Diff mode enabled automatically
│        Check: Does snapshot work correctly?
│        Run: Log diff output to verify deltas
│
└─ NO → Might use brain_enhanced_v2.py directly
        Check: Are you calling snapshot() with diff_mode?
        Check: Are you using UITARS context?
```

---

## Quick Diagnosis

### Is the conflict affecting you?

```bash
# Check 1: Enable snapshot logging
config.LOG_SNAPSHOTS = True

# Look for patterns like:
# [a11y] Cache hit for https://example.com
# [a11y] Snapshot diff: +0 -0 ~0  ← NO CHANGES DETECTED!
# This suggests cache state tracking bug

# Check 2: Monitor screenshot count
# ConversationContext: "Pruned X old screenshots, keeping last 5"
# HistoryPruner: (no logs, but removes images)

# Check 3: Verify diff accuracy
# Request two different snapshots in <2s
# First diff should show changes, second might show none
```

---

## Hottest Issues

### Issue 1: Cache returns wrong type (MEDIUM)
When `diff_mode=True` after cache hit:
- Expect: `SnapshotDiff`
- Get: `Snapshot`
- Impact: Diff analysis code breaks

### Issue 2: Diff state staleness (CRITICAL)
Cache hit doesn't update `_previous_snapshot`:
- Diff compares against old state
- Shows no changes when page changed
- Token savings calculation wrong
- Agent gets incorrect page state

### Issue 3: Screenshot aggressive removal (MEDIUM)
`KEEP_LAST_N_SCREENSHOTS=1` too aggressive:
- Removes screenshot too fast
- Agent loses visual context after 1 message
- Conflicts with ConversationContext (5 limit)

---

## Files Involved

| File | Lines | Role | Conflict |
|------|-------|------|----------|
| `a11y_browser.py` | 436, 1162-1270 | Caching & diffing | Cache + diff state |
| `a11y_config.py` | 64-206 | Configuration | Multiple limits |
| `ui_tars_patterns.py` | 101-137 | Screenshot context | Limit=5 |
| `history_pruner.py` | 1-325 | Message pruning | Limit=1 |
| `simple_agent.py` | ~1750 | Usage | Enables diff |
| `universal_agent.py` | ~2150 | Usage | Enables diff |
| `brain_enhanced_v2.py` | 1024, 1034 | Integration | Two systems |
| `dom_diff_cache.py` | 1-422 | Alternate system | Unused but risk |

---

## Recommendation Priority

**P0 (Do This First):** Fix cache state tracking bug in a11y_browser.py
- Cache hit must update `_previous_snapshot` before returning
- Or bypass cache when `diff_mode=True`

**P1 (High):** Unify screenshot limits
- Choose: 1, 3, or 5 screenshots? Not all three
- Update config to single source of truth

**P2 (Medium):** Document caching behavior clearly
- What does diff_mode return on cache hit?
- What are exact pruning semantics?

**P3 (Nice-to-have):** Consider disabling ENABLE_SNAPSHOT_CACHE
- Diffs provide better compression anyway
- Reduces complexity significantly

---

## Status of Each System

| System | Mature | Tested | Documented | Conflicts | Risk |
|--------|--------|--------|------------|-----------|------|
| Snapshot Cache | Yes | Basic | OK | With Diff | Medium |
| Snapshot Diff | Yes | Yes | Excellent | With Cache | Low |
| ConversationContext | Yes | Basic | OK | With Pruner | Medium |
| HistoryPruner | Yes | Basic | OK | With Context | Medium |
| DOM Diff Cache | Partial | No | Basic | Unused | Low |

---

## Key Takeaway

**The systems work independently but create interference when all enabled together.**

Focus on:
1. Fixing the cache→diff state bug (accuracy)
2. Choosing one screenshot limit (consistency)
3. Testing the interaction (verification)

Then you're safe to use all optimizations!
