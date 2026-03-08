# Snapshot Caching & Diffing Conflict Analysis

## Executive Summary

Analysis of existing snapshot caching, diffing, and deduplication mechanisms in `/mnt/c/ev29/cli/engine/agent/` reveals **THREE SEPARATE SYSTEMS** operating in parallel:

1. **A11y Snapshot Caching** (`a11y_browser.py`) - URL-based TTL cache
2. **UI-TARS ConversationContext** (`ui_tars_patterns.py`) - Screenshot count limiter
3. **History Pruner** (`history_pruner.py`) - Message-level screenshot removal
4. **Snapshot Diffing** (`a11y_browser.py`) - Delta compression (ENABLE_SNAPSHOT_DIFF)

**CRITICAL FINDING:** These systems operate at different abstraction levels and have **POTENTIAL CONFLICTS** in screenshot deduplication, caching strategy, and diff tracking behavior.

---

## System 1: A11y Snapshot Caching

**Location:** `/mnt/c/ev29/cli/engine/agent/a11y_browser.py` (lines 436, 1162-1246)

### What It Does
- Caches full `Snapshot` objects by URL
- TTL-based expiration: `SNAPSHOT_CACHE_TTL = 2.0` seconds
- LRU eviction when cache exceeds `SNAPSHOT_CACHE_SIZE = 10`
- Triggered by: `config.ENABLE_SNAPSHOT_CACHE = True`

### Implementation Details
```python
self._snapshot_cache: Dict[str, Tuple[Snapshot, float]] = {}  # url -> (snapshot, timestamp)

# Cache check (lines 1162-1170)
if config.ENABLE_SNAPSHOT_CACHE and not force and current_url in self._snapshot_cache:
    cached_snapshot, cached_time = self._snapshot_cache[current_url]
    age = current_time - cached_time
    if age < config.SNAPSHOT_CACHE_TTL:
        return cached_snapshot  # RETURNS CACHED FULL SNAPSHOT

# Cache store (lines 1238-1246)
if config.ENABLE_SNAPSHOT_CACHE:
    self._snapshot_cache[current_url] = (snapshot, current_time)
    if len(self._snapshot_cache) > config.SNAPSHOT_CACHE_SIZE:
        oldest_url = min(self._snapshot_cache.keys(),
                        key=lambda k: self._snapshot_cache[k][1])
        del self._snapshot_cache[oldest_url]
```

### State Tracking
- `self._previous_snapshot: Optional[Snapshot]` - Stores previous for diffing
- `self._last_snapshot: Optional[Snapshot]` - Current snapshot reference

---

## System 2: Snapshot Diffing (ENABLE_SNAPSHOT_DIFF)

**Location:** `/mnt/c/ev29/cli/engine/agent/a11y_browser.py` (lines 1249-1270)

### What It Does
- Returns `SnapshotDiff` instead of full `Snapshot` when `diff_mode=True`
- Computes delta: added/removed/changed elements only
- 70-80% token reduction claimed in documentation
- Requires semantic tracking of `_previous_snapshot`

### Implementation Details
```python
# Diff mode logic (lines 1248-1261)
if diff_mode:
    diff = snapshot.to_diff(self._previous_snapshot)
    self._previous_snapshot = snapshot  # ALWAYS UPDATE
    self._last_snapshot = snapshot
    return diff

# Normal mode (lines 1263-1270)
self._previous_snapshot = snapshot  # ALWAYS UPDATE
self._last_snapshot = snapshot
return snapshot
```

### Key Method: Snapshot.to_diff()
**Location:** `a11y_browser.py` (in SnapshotDiff class)
- Compares `ElementRef` objects by hash
- Hash based on: `role|name|value|focused|disabled`
- Uses set operations: `current - previous`, `previous - current`
- O(n) complexity

### Configuration
- `ENABLE_SNAPSHOT_DIFF = True` (default, in `a11y_config.py`)
- `DIFF_FORMAT = "minimal"` (compact representation)

### Usage Pattern
- `simple_agent.py` (line ~1750): First snapshot full, subsequent snapshots use diff mode
- `universal_agent.py` (line ~2150): Same pattern - diff after first snapshot
- Controlled by: `use_diff_mode = self._first_snapshot_taken and config.ENABLE_SNAPSHOT_DIFF`

---

## System 3: UI-TARS ConversationContext Screenshot Management

**Location:** `/mnt/c/ev29/cli/engine/agent/ui_tars_patterns.py` (lines 101-137)

### What It Does
- Manages screenshot count in conversation history
- Auto-prunes screenshots when exceeding `max_screenshots = 5`
- **REMOVES IMAGE DATA** from oldest messages (not the messages themselves)
- Separate from `a11y_browser.py` caching

### Implementation Details
```python
class ConversationContext:
    max_screenshots: int = 5
    messages: List[Dict[str, Any]] = field(default_factory=list)
    screenshot_count: int = 0

    def add_message(self, role: str, content: str, screenshot_b64: Optional[str] = None):
        """Add message with optional screenshot"""
        message = {"role": role, "content": content}
        if screenshot_b64:
            message["images"] = [screenshot_b64]
            self.screenshot_count += 1
            self._prune_screenshots()  # PRUNE IF OVER LIMIT
        self.messages.append(message)

    def _prune_screenshots(self):
        """Remove screenshots from oldest messages to stay under limit"""
        if self.screenshot_count <= self.max_screenshots:
            return

        removed = 0
        for msg in self.messages:
            if "images" in msg and removed < (self.screenshot_count - self.max_screenshots):
                del msg["images"]  # REMOVES IMAGE DATA
                removed += 1
```

### Where It's Used
- **brain_enhanced_v2.py** (line 1024): Initialized as `self._uitars_context = ConversationContext(max_screenshots=5)`
- **ui_tars_integration.py** (line 46, 135-139): Enhanced screenshot calls add to context
- **ui_tars_patterns.py** (line 364): Automatic screenshot pruning during agent loop

### Key Behavior
- **Image removal**, not message removal
- **5 screenshot limit** (hardcoded default)
- **Independent tracking** of screenshot count

---

## System 4: History Pruner (ENABLE_HISTORY_PRUNING)

**Location:** `/mnt/c/ev29/cli/engine/agent/history_pruner.py`

### What It Does
- Prunes conversation history to reduce token usage (50-60% claimed)
- **Removes all screenshots** from non-recent messages (lines 269-324)
- Summarizes old messages or just caps them

### Key Functions
```python
class HistoryPruner:
    def __init__(
        self,
        max_history_items: int = 10,
        preserve_recent: int = 3,
        summarize_older: bool = True
    ):
        # DIFFERENT LIMITS than ConversationContext!

    def prune(self, messages: List[Dict]) -> List[Dict]:
        """
        Rules:
        1. Always keep system prompt
        2. Always keep last preserve_recent messages in full
        3. Summarize older messages or delete
        4. Remove all screenshots from non-recent messages  <-- AGGRESSIVE
        5. Cap total at max_history_items
        """

def prune_screenshots_from_history(messages: List[Dict], keep_last_n: int = 1) -> List[Dict]:
    """
    Remove all screenshots except the last N.
    Aggressive pruning for screenshot-heavy conversations.
    Keeps only most recent N screenshots for context.
    """
```

### Configuration
- `ENABLE_HISTORY_PRUNING = True` (default, in `a11y_config.py`)
- `MAX_HISTORY_ITEMS = 10`
- `PRESERVE_RECENT_MESSAGES = 3`
- `PRUNE_SCREENSHOTS = True`
- `KEEP_LAST_N_SCREENSHOTS = 1` (aggressive!)

### Where It's Used
- **brain_enhanced_v2.py** (line 1034-1039): Initialized as `HistoryPruner(..., preserve_recent=10, ...)`

---

## System 5: DOM Diff Cache (Separate System)

**Location:** `/mnt/c/ev29/cli/engine/agent/dom_diff_cache.py`

### What It Does
- Completely separate DOM caching system (not accessibility-based)
- Caches previous DOM states per URL
- Computes semantic diffs (added/removed/modified elements)
- Designed for HTML-based diffing, not accessibility trees

### Key Components
- `DOMDiffEngine` - Computes diffs
- `DOMCache` - Maintains history per URL
- Volatility tracking to determine if full DOM needed

### Note
- **NOT CURRENTLY INTEGRATED** with a11y_browser.py
- Would create another caching layer if activated
- Different diff algorithm (path/hash based vs. semantic)

---

## CONFLICT MATRIX

### Conflict 1: Multiple Screenshot Limits (CRITICAL)

| System | Limit | Trigger | Behavior |
|--------|-------|---------|----------|
| **ConversationContext** | 5 screenshots | `add_message()` | Removes image data from oldest |
| **HistoryPruner** | 1 screenshot | `prune()` | Removes image data from all but last 1 |
| **A11y Cache** | N/A (full snapshots) | TTL=2s | Caches full Snapshot objects |
| **Snapshot Diff** | N/A (diffs) | `diff_mode=True` | Returns delta only |

**CONFLICT:** Different systems using different screenshot limits (5 vs 1 vs unlimited). If multiple systems run sequentially:
1. ConversationContext keeps last 5 screenshots
2. HistoryPruner reduces to last 1 screenshot
3. Result: Aggressive pruning destroys context

### Conflict 2: Diff State Tracking Collision (CRITICAL)

**Problem:** `_previous_snapshot` used by diffing may get stale if caching returns early.

```python
# If cache hit happens:
if config.ENABLE_SNAPSHOT_CACHE and ... in self._snapshot_cache:
    return cached_snapshot  # RETURNS WITHOUT UPDATING _previous_snapshot!

# But diffing relies on _previous_snapshot being current:
if diff_mode:
    diff = snapshot.to_diff(self._previous_snapshot)  # May be old!
    self._previous_snapshot = snapshot
```

**Impact:** When diff_mode=True after cache hit, the diff compares against stale `_previous_snapshot`, producing incorrect deltas.

**Example Scenario:**
1. T=0: Take snapshot A on URL X, cache it, set `_previous_snapshot = A`
2. T=0.5s: Click button (page changes), request snapshot with `diff_mode=True`
3. T=0.5s: Cache returns A (cache is still valid), `_previous_snapshot` still = A
4. T=0.5s: Diff should compare A→B (changed), but _previous_snapshot = A (correct)
5. T=1s: Another diff request comes, cache returns A (TTL=2s still valid)
6. T=1s: **BUG**: Diff compares A→A (no changes) when should compare B→C

**Root Cause:** Cache returns snapshot without ensuring `_previous_snapshot` is updated.

### Conflict 3: Caching Inefficiency with Diffing

**Problem:** Full snapshot caching contradicts diff strategy.

```
diff_mode=True wants: Only deltas (save tokens)
ENABLE_SNAPSHOT_CACHE wants: Full snapshots (fast hits)
```

If caching returns full snapshot when diff mode is requested:
- `snapshot()` called with `diff_mode=True`
- Cache hit returns full Snapshot, not SnapshotDiff
- Caller expects SnapshotDiff but gets Snapshot
- Type mismatch: `Union[Snapshot, SnapshotDiff]` ambiguous

### Conflict 4: Screenshot Pruning Happens at Multiple Levels

**Level 1:** A11y snapshot caching (full objects)
**Level 2:** ConversationContext (removes image data after 5)
**Level 3:** HistoryPruner (removes image data after 1, summarizes messages)
**Level 4:** Snapshot diffing (reduces what's even captured)

**Problem:** Multiple independent pruning decisions create:
- Unpredictable total token usage
- Screenshots removed by multiple systems
- Difficult debugging when context missing

### Conflict 5: TTL Cache Invalidation

**Problem:** 2-second cache TTL might miss important diffs.

```python
SNAPSHOT_CACHE_TTL = 2.0  # seconds

Scenario:
1. T=0.0s: Take snapshot A, cache with timestamp
2. T=0.5s: User clicks button on page
3. T=0.8s: Take snapshot B
   - Cache check: age = 0.8s < 2.0s, so RETURNS CACHED A!
   - But page changed at T=0.5s

Diff should be: A→B
Actually returns: A (cached, no diff possible)
```

**Impact:** Cache returns stale snapshot, breaking diff detection.

---

## INTEGRATION POINTS (Where Conflicts Manifest)

### Point 1: brain_enhanced_v2.py (~1020-1040)

```python
# Line 1024: ConversationContext initialized
self._uitars_context = ConversationContext(max_screenshots=5)

# Line 1034: HistoryPruner initialized with different params
self._history_pruner = HistoryPruner(
    max_history_items=self._max_context_messages,  # ~100
    preserve_recent=10,
    summarize_older=True
)
```

**Conflict:** Two separate systems managing screenshots independently.
- ConversationContext: Prunes at add_message() time
- HistoryPruner: Prunes at prune() time
- Both remove image data but with different limits

### Point 2: simple_agent.py & universal_agent.py

```python
# Enables diff mode after first snapshot
use_diff_mode = self._first_snapshot_taken and config.ENABLE_SNAPSHOT_DIFF
snapshot = await self.browser.snapshot(diff_mode=use_diff_mode)
```

**Conflict:** Diff mode enabled regardless of cache state.
- If cache hit, full snapshot returned (not diff)
- If fresh snapshot, diff returned
- Caller gets inconsistent types

### Point 3: ui_tars_integration.py (line 135-139)

```python
# Enhanced screenshot adds to UITARS context
self.context.add_message(
    "assistant",
    "Screenshot captured",
    b64_screenshot
)
```

**Conflict:** Screenshot added to ConversationContext, which may auto-prune.
- Could prune screenshot user just captured
- Brain doesn't know ConversationContext has limited to 5

### Point 4: brain_enhanced_v2.py LLM calls

When brain calls LLM with conversation history:
1. History may be pruned by HistoryPruner (removes screenshots)
2. Then sent to UITARS enhancer (expects images in messages)
3. Or sent to ConversationContext (auto-prunes images)
4. Final message set is unpredictable

---

## RECOMMENDED FIXES

### Fix 1: Unify Screenshot Limits (HIGH PRIORITY)

**Problem:** ConversationContext (5 screenshots) vs HistoryPruner (1 screenshot) creates confusion.

**Solution:** Single source of truth in `a11y_config.py`:
```python
# Unified screenshot management
MAX_SCREENSHOTS_IN_CONTEXT = 5
HISTORY_PRUNE_SCREENSHOTS = True
KEEP_LAST_N_SCREENSHOTS = 5  # Match ConversationContext
```

Then update:
- `ConversationContext.__init__()` to read from config
- `HistoryPruner.__init__()` to read same limits
- Both systems use identical pruning strategy

### Fix 2: Fix Cache + Diff State Tracking (CRITICAL)

**Problem:** Cache returns without updating `_previous_snapshot`.

**Solution:** In `a11y_browser.py` snapshot() method:

```python
# BEFORE returning cached snapshot
if config.ENABLE_SNAPSHOT_CACHE and not force and current_url in self._snapshot_cache:
    cached_snapshot, cached_time = self._snapshot_cache[current_url]
    age = current_time - cached_time

    if age < config.SNAPSHOT_CACHE_TTL:
        # FIX: Always update _previous_snapshot when returning cached snapshot
        old_previous = self._previous_snapshot
        self._previous_snapshot = cached_snapshot
        self._last_snapshot = cached_snapshot

        # If diff_mode requested, return diff from old state
        if diff_mode and old_previous:
            diff = cached_snapshot.to_diff(old_previous)
            return diff

        return cached_snapshot
```

### Fix 3: Separate URL-Based vs Message-Based Caching (MEDIUM)

**Problem:** A11y caching (URL-based) competes with ConversationContext (message-based).

**Solution:** Use different caching strategies:
- **A11y Cache:** Keep for performance (TTL snapshots)
- **ConversationContext:** Only for screenshot count management (no duplicate caching)
- **HistoryPruner:** Only for history size management (no duplicate caching)

Make them explicitly complementary, not overlapping:
```python
# a11y_browser.py
ENABLE_SNAPSHOT_CACHE = True  # Performance optimization

# a11y_config.py
ENABLE_HISTORY_PRUNING = True  # Token optimization (separate concern)
```

### Fix 4: Document Diff Mode Caching Behavior (MEDIUM)

**Problem:** Unclear what diff_mode returns when cache hits.

**Solution:** Add to a11y_browser.py documentation:

```python
async def snapshot(
    self,
    force: bool = False,
    diff_mode: bool = False,
    selector: Optional[str] = None,
    exclude_selectors: Optional[List[str]] = None
) -> Union[Snapshot, SnapshotDiff]:
    """
    Get page snapshot or differential.

    Caching Behavior:
    - If ENABLE_SNAPSHOT_CACHE and cache hit:
        - diff_mode=False: Returns cached Snapshot
        - diff_mode=True: Returns SnapshotDiff from previous to cached
    - If ENABLE_SNAPSHOT_CACHE and cache miss:
        - Returns fresh Snapshot or SnapshotDiff
    - If force=True: Bypasses cache entirely

    Note: Diff accuracy depends on _previous_snapshot state.
    """
```

### Fix 5: Consider Disabling One System (OPTIONAL)

**Option A:** Keep diffing, disable URL-based caching:
```python
ENABLE_SNAPSHOT_CACHE = False  # Disable URL cache
ENABLE_SNAPSHOT_DIFF = True     # Use diffs instead
# Result: Diffs provide compression without cache inconsistency
```

**Option B:** Keep caching, disable diffing at snapshot level:
```python
ENABLE_SNAPSHOT_CACHE = True    # Use URL-based cache
ENABLE_SNAPSHOT_DIFF = False    # Disable at browser level
# Result: Use HistoryPruner for token optimization instead
```

**Option C:** Keep both but with clear hierarchy:
```
Default: ENABLE_SNAPSHOT_DIFF = True (compression first)
         ENABLE_SNAPSHOT_CACHE = False (conflicts with diff tracking)
         Use HistoryPruner for message-level optimization
```

### Fix 6: Consolidate History Management (LONG-TERM)

**Problem:** Three separate history-pruning systems (ConversationContext, HistoryPruner, A11y cache).

**Solution:** Implement unified history manager:
```python
class UnifiedHistoryManager:
    """Single source of truth for conversation history management."""

    def __init__(self, max_messages=10, max_screenshots=5, cache_ttl=2.0):
        self.messages = []
        self.max_messages = max_messages
        self.max_screenshots = max_screenshots
        self.cache_ttl = cache_ttl
        self._url_cache = {}  # Optional performance cache

    def add_snapshot(self, url, snapshot):
        """Unified snapshot addition with all pruning rules applied."""
        # Add to history
        # Prune if needed
        # Update cache if enabled
        # Return processed result

    def prune(self):
        """Single pruning operation respecting all constraints."""
        # Apply all rules: max_messages, max_screenshots, cache_ttl
        # Return pruned history
```

---

## DETECTION CHECKLIST

To identify if conflicts are manifesting:

- [ ] Run agent, check if diff mode working: `config.LOG_SNAPSHOTS = True`
- [ ] Verify diff reduces tokens: `[a11y] Snapshot diff: +X -Y ~Z` should show changes
- [ ] Check cache hits: Look for `[a11y] Cache hit for URL` messages
- [ ] Verify history pruning: Count message count over time
- [ ] Monitor screenshot count: Should stay within configured limits
- [ ] Check LLM context: See if screenshots progressively disappear
- [ ] Run with multiple diff requests to same URL within 2s window
- [ ] Verify `_previous_snapshot` state in debugger

---

## SUMMARY TABLE

| Mechanism | Location | Purpose | Configuration | Risk |
|-----------|----------|---------|---------------|------|
| **Snapshot Cache** | a11y_browser.py:436,1162-1246 | Performance (URL→full snapshot TTL) | ENABLE_SNAPSHOT_CACHE=True, TTL=2s | State staleness, diff collision |
| **Snapshot Diff** | a11y_browser.py:1249-1270 | Compression (delta only) | ENABLE_SNAPSHOT_DIFF=True | Cache bypass, type ambiguity |
| **ConversationContext** | ui_tars_patterns.py:101-137 | Screenshot limit (last 5) | max_screenshots=5 | Image removal, independent tracking |
| **HistoryPruner** | history_pruner.py:1-325 | History compression (last 1 screenshot) | KEEP_LAST_N_SCREENSHOTS=1 | Aggressive pruning, message loss |
| **DOM Diff Cache** | dom_diff_cache.py | Alternative diff system (unused) | Not integrated | Potential duplicate system |

---

## CONCLUSION

**Severity: MEDIUM-HIGH**

The existing systems are mostly independent but have **three critical interaction points**:

1. **Cache + Diff state tracking** (affects accuracy of deltas)
2. **Multiple screenshot limits** (affects token usage consistency)
3. **Type inconsistency** (cache returns Snapshot when SnapshotDiff expected)

**Recommendation:**
- Prioritize Fix #2 (cache state tracking) to prevent diff accuracy bugs
- Prioritize Fix #1 (unified screenshot limits) to prevent token accumulation
- Document caching behavior clearly (Fix #4) so developers understand interactions

The systems are architecturally sound but need explicit coordination rules to coexist safely.
