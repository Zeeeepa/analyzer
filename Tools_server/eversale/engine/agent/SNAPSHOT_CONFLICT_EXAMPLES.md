# Snapshot Conflicts - Code Examples & Demonstrations

## Example 1: Cache + Diff State Staleness Bug

### The Bug in Action

**File:** `/mnt/c/ev29/cli/engine/agent/a11y_browser.py` (lines 1162-1170)

```python
# Current code:
if config.ENABLE_SNAPSHOT_CACHE and not force and current_url in self._snapshot_cache:
    cached_snapshot, cached_time = self._snapshot_cache[current_url]
    age = current_time - cached_time

    if age < config.SNAPSHOT_CACHE_TTL:
        self._metrics["cache_hits"] += 1
        if config.LOG_METRICS:
            print(f"[a11y] Cache hit for {current_url} (age: {age:.2f}s)")
        return cached_snapshot  # BUG: _previous_snapshot NOT updated!
```

### Why It's a Bug

**State tracking assumption:**
```python
# Lines 1249-1253 (diff mode):
if diff_mode:
    diff = snapshot.to_diff(self._previous_snapshot)  # Assumes _previous_snapshot is fresh
    self._previous_snapshot = snapshot
    self._last_snapshot = snapshot
    return diff
```

**Scenario:**
```
T=0.0s: Take fresh snapshot
  snapshot = Snapshot(elements=[a, b, c])
  _previous_snapshot = snapshot
  _snapshot_cache["URL"] = (snapshot, timestamp)

T=0.5s: User modifies page (adds element d)

T=0.8s: Request snapshot with diff_mode=True
  Cache check: (0.8s - 0.0s) = 0.8s < 2.0s ← Cache HIT
  return cached_snapshot  ← Returns [a, b, c]
  _previous_snapshot still = [a, b, c]  ← NEVER UPDATED

  BUT: Page now has [a, b, c, d]!

  Later code does: result = await browser.snapshot(diff_mode=True)
  # Actually returns Snapshot([a,b,c]), not SnapshotDiff
  # If caller does: diff = result.to_diff(_previous)
  # It compares [a,b,c].to_diff([a,b,c]) = No changes!
```

### The Fix

```python
# Fixed version:
if config.ENABLE_SNAPSHOT_CACHE and not force and current_url in self._snapshot_cache:
    cached_snapshot, cached_time = self._snapshot_cache[current_url]
    age = current_time - cached_time

    if age < config.SNAPSHOT_CACHE_TTL:
        self._metrics["cache_hits"] += 1

        # FIX: Update state before returning
        old_previous = self._previous_snapshot
        self._previous_snapshot = cached_snapshot
        self._last_snapshot = cached_snapshot

        # FIX: Handle diff mode properly
        if diff_mode and old_previous and old_previous != cached_snapshot:
            diff = cached_snapshot.to_diff(old_previous)
            if config.LOG_METRICS:
                print(f"[a11y] Cache hit diff for {current_url} (age: {age:.2f}s)")
            return diff

        if config.LOG_METRICS:
            print(f"[a11y] Cache hit for {current_url} (age: {age:.2f}s)")
        return cached_snapshot
```

---

## Example 2: Screenshot Limit Conflict

### Three Different Limits Operating

**Location 1:** `ui_tars_patterns.py` (lines 108, 125-137)
```python
class ConversationContext:
    max_screenshots: int = 5  # LIMIT 1: Keep 5 screenshots

    def _prune_screenshots(self):
        if self.screenshot_count <= self.max_screenshots:  # Threshold: 5
            return
        # Removes images when over 5
```

**Location 2:** `history_pruner.py` (line 178, 269-324)
```python
# LIMIT 2: Keep only 1 screenshot
KEEP_LAST_N_SCREENSHOTS = 1

def prune_screenshots_from_history(messages, keep_last_n: int = 1):
    """Remove all screenshots except the last 1."""
    # Removes ALL but 1 screenshot
```

**Location 3:** `a11y_config.py` (lines 174-178)
```python
# Configuration conflicts
ENABLE_HISTORY_PRUNING = True
MAX_HISTORY_ITEMS = 10
PRESERVE_RECENT_MESSAGES = 3
PRUNE_SCREENSHOTS = True
KEEP_LAST_N_SCREENSHOTS = 1  # Too aggressive!
```

### What Happens When Both Run

```python
# Scenario: Agent taking screenshots and calling LLM

# Step 1: Take screenshot A
browser_context.add_message("assistant", "Screenshot", screenshot_A_b64)
# State: ConversationContext has [msg_with_A] (1/5 OK)

# Step 2: Take screenshot B
browser_context.add_message("assistant", "Screenshot", screenshot_B_b64)
# State: ConversationContext has [msg_with_A, msg_with_B] (2/5 OK)

# Step 3: Take screenshot C
browser_context.add_message("assistant", "Screenshot", screenshot_C_b64)
# State: ConversationContext has [msg_with_A, msg_with_B, msg_with_C] (3/5 OK)

# Step 4: Now call LLM (brain calls prune before LLM)
pruned_history = history_pruner.prune(all_messages)
# HistoryPruner sees 3 messages with images
# Keeps only LAST 1 screenshot
# Result: [msg_with_A (images removed),
#          msg_with_B (images removed),
#          msg_with_C (images remain)]

# Step 5: Call LLM with pruned history
# LLM sees only 1 screenshot (the last one)
# BUT: ConversationContext was designed for 5!
```

### Conflict Manifestation

```
Timeline:
─────────────────────────────────────────────────────
ConversationContext:  [A] [A,B] [A,B,C] [A,B,C,D] [A,B,C,D,E]
                      1/5 2/5   3/5     4/5       5/5 (OK)

HistoryPruner runs:   [A] [A,B] [A,B,C] [A,B,C,D] [A,B,C,D,E]
                      ↓   ↓     ↓       ↓         ↓
                      [ ]  [ ]   [C]    [D]      [E]
                      Only E has images!

LLM receives:
- Message 1: No images
- Message 2: No images
- Message 3: No images
- Message 4: No images
- Message 5: Yes, has E

Result: Agent has no visual context until the very last action!
```

### The Root Cause

Two independent systems don't know about each other:
```python
# brain_enhanced_v2.py initialization (lines 1023-1040)

# System 1: ConversationContext (max_screenshots=5)
if UITARS_AVAILABLE and ConversationContext:
    self._uitars_context = ConversationContext(max_screenshots=5)
    # This uses 5 as the limit

# System 2: HistoryPruner (KEEP_LAST_N_SCREENSHOTS=1)
if HISTORY_PRUNER_AVAILABLE and HistoryPruner:
    self._history_pruner = HistoryPruner(
        max_history_items=self._max_context_messages,
        preserve_recent=10,  # Keep 10 recent messages
        summarize_older=True
    )
    # But doesn't know about ConversationContext's 5-screenshot limit!
```

### The Fix

Choose ONE screenshot limit:
```python
# Option A: Use 5 screenshots everywhere
ENABLE_HISTORY_PRUNING = True
MAX_HISTORY_ITEMS = 10
PRESERVE_RECENT_MESSAGES = 10
KEEP_LAST_N_SCREENSHOTS = 5  # Match ConversationContext

# Then update:
# - ConversationContext: max_screenshots = 5
# - HistoryPruner: keep_last_n = 5
```

Or:
```python
# Option B: Use 1 screenshot (aggressive)
# - ConversationContext: max_screenshots = 1
# - HistoryPruner: keep_last_n = 1
# - But this might lose too much context
```

Or:
```python
# Option C: Use 3 screenshots (balanced)
# - ConversationContext: max_screenshots = 3
# - HistoryPruner: keep_last_n = 3
# - HistoryPruner: preserve_recent = 3  # Keep recent messages intact
```

---

## Example 3: Type Ambiguity Bug

### The Problem

**File:** `simple_agent.py` and `universal_agent.py`

```python
# Usage code (both files):
use_diff_mode = self._first_snapshot_taken and config.ENABLE_SNAPSHOT_DIFF
snapshot = await self.browser.snapshot(diff_mode=use_diff_mode)

# Next line expects snapshot object:
action = await self._get_action(goal, snapshot, steps)
```

**But `snapshot()` can return different types:**

```python
# a11y_browser.py return type (line ~1130):
async def snapshot(
    self,
    force: bool = False,
    diff_mode: bool = False,
) -> Union[Snapshot, SnapshotDiff]:  # EITHER TYPE!
```

### Conflict Scenario

```python
# Case 1: Fresh snapshot (normal)
snapshot = await self.browser.snapshot(diff_mode=True)
# Returns: SnapshotDiff(added=[...], removed=[...], changed=[...])
# Type: SnapshotDiff ✓

# Case 2: Cache hit (BUG)
snapshot = await self.browser.snapshot(diff_mode=True)
# Returns: Snapshot(elements=[...], url="...", title="...")
# Type: Snapshot (not SnapshotDiff!) ✗

# Caller code that expects SnapshotDiff:
if isinstance(snapshot, SnapshotDiff):
    elements = snapshot.changed_elements  # ✓ Works in Case 1
    # ✗ Fails in Case 2 - Snapshot doesn't have changed_elements!
```

### Real World Example

```python
# In agent action generation (_get_action method):
async def _get_action(self, goal: str, snapshot: Union[Snapshot, SnapshotDiff]):
    # Code assumes SnapshotDiff properties

    if hasattr(snapshot, 'added_elements'):
        # Process new elements
        for el in snapshot.added_elements:  # OK for SnapshotDiff
            ...

    # But on cache hit, gets Snapshot instead:
    # snapshot.added_elements doesn't exist!
    # AttributeError!
```

### The Fix

Make cache behavior explicit:
```python
async def snapshot(self, diff_mode: bool = False):
    # Option 1: Never use cache when diff mode requested
    if config.ENABLE_SNAPSHOT_CACHE and not force and not diff_mode:
        # Use cache

    # Option 2: Make cache compatibility explicit
    if cache_hit:
        if diff_mode:
            # Generate diff from cache
            diff = cached_snapshot.to_diff(self._previous)
            return diff  # Consistent type
        else:
            return cached_snapshot
```

---

## Example 4: TTL Cache Window Bug

### The Scenario

**File:** `a11y_browser.py` line 1166, `a11y_config.py` line 11

```python
SNAPSHOT_CACHE_TTL = 2.0  # 2 seconds

# Cache check:
if age < config.SNAPSHOT_CACHE_TTL:
    return cached_snapshot
```

### Realistic Timing

```
Timeline (milliseconds):
─────────────────────────────────────────────────────
T=0.0s:    snapshot() taken
           _previous = snapshot_A = [elements a, b, c]
           Cache: snapshot_A with timestamp 0.0s

T=100ms:   LLM thinks about what to do

T=500ms:   User clicks button
           Page now shows [elements a, b, c, d, e]
           (New elements added)

T=1100ms:  Request next snapshot with diff_mode=True
           Cache check: (1.1s - 0.0s) = 1.1s < 2.0s
           CACHE HIT! Return cached snapshot_A

T=1100ms:  Caller expects: SnapshotDiff with +[d, e]
           Caller gets: Snapshot([a, b, c]) from cache

T=1100ms:  Agent compares: A.to_diff(A) = No changes
           But page HAS changed!

T=1900ms:  Still within TTL window (1.9s < 2.0s)
           Cache still returns stale snapshot_A
           Agent still thinks no changes

T=2100ms:  (2.1s >= 2.0s) Finally cache expires
           Fresh snapshot taken, finally shows [a,b,c,d,e]
```

### Impact on Agent

```
Without cache conflict:
Action 1 (T=0s):   Take snapshot → [a, b, c]
Action 2 (T=0.5s): Click button, take snapshot → [a, b, c, d, e]
                   Diff detects +[d, e]
                   Agent reacts immediately

With cache conflict:
Action 1 (T=0s):   Take snapshot → [a, b, c]
Action 2 (T=0.5s): Click button, take snapshot → [a, b, c] (cached!)
                   Diff detects nothing
                   Agent waits 1.5 more seconds...
Action 3 (T=2.1s): Cache expires, finally sees [a, b, c, d, e]
                   Agent reacts with 2.1 second delay!
```

### The Fix

Option 1: Disable cache when using diff mode
```python
if config.ENABLE_SNAPSHOT_CACHE and not force and not diff_mode:
    # Use cache only for non-diff mode
```

Option 2: Shorten TTL
```python
SNAPSHOT_CACHE_TTL = 0.5  # 500ms (shorter window)
```

Option 3: Invalidate cache on certain actions
```python
async def click(self, element_ref):
    result = await self.page.click(...)
    self._snapshot_cache.clear()  # Invalidate cache after action
    return result
```

---

## Example 5: ConversationContext Auto-Pruning Surprise

### The Surprise

**File:** `ui_tars_patterns.py` lines 112-121

```python
def add_message(self, role: str, content: str, screenshot_b64: Optional[str] = None):
    message = {"role": role, "content": content}

    if screenshot_b64:
        message["images"] = [screenshot_b64]
        self.screenshot_count += 1

        # Automatic pruning!
        self._prune_screenshots()  # Might remove OTHER images!

    self.messages.append(message)
```

### What Developers Expect

```python
# My code:
brain._uitars_context.add_message("assistant", "Took screenshot", screenshot1)
brain._uitars_context.add_message("assistant", "Took screenshot", screenshot2)
brain._uitars_context.add_message("assistant", "Took screenshot", screenshot3)

# I expect:
# 3 messages, all with images

# Reality (if max_screenshots=2):
# 3 messages, but 1st has no image (auto-removed!)
```

### Auto-Pruning Details

```python
def _prune_screenshots(self):
    if self.screenshot_count <= self.max_screenshots:
        return  # No pruning needed

    removed = 0
    for msg in self.messages:
        if "images" in msg and removed < (self.screenshot_count - self.max_screenshots):
            del msg["images"]  # Silently removes from arbitrary message!
            removed += 1
```

### The Surprise Scenario

```python
# Assume max_screenshots = 2

add_message("assistant", "Found element", screenshot_A)
# messages = [
#   {role: "assistant", content: "Found element", images: [A]}
# ]
# screenshot_count = 1 (OK)

add_message("assistant", "Clicked button", screenshot_B)
# messages = [
#   {role: "assistant", content: "Found element", images: [A]},
#   {role: "assistant", content: "Clicked button", images: [B]}
# ]
# screenshot_count = 2 (OK)

add_message("assistant", "Result shown", screenshot_C)
# screenshot_count = 3, max = 2
# _prune_screenshots() called
# Removes image from FIRST message (index 0)!
# messages = [
#   {role: "assistant", content: "Found element"},  ← Lost A!
#   {role: "assistant", content: "Clicked button", images: [B]},
#   {role: "assistant", content: "Result shown", images: [C]}
# ]
# screenshot_count = 2
```

### The Problem

Developer doesn't control WHICH screenshot gets removed:
```python
# My expectation:
Keep latest screenshots: [B, C] ← Makes sense (recent context)

# What actually happens:
Remove oldest: [B, C] ← Also makes sense
(but could remove middle one in different order)

# If messages not in insertion order:
Might remove [A, C] and keep [B] ← Confusing!
```

### Better Implementation

```python
def _prune_screenshots(self):
    if self.screenshot_count <= self.max_screenshots:
        return

    # Remove from oldest messages first (better predictability)
    removed = 0
    # Go backwards from oldest
    for msg in reversed(self.messages):
        if "images" in msg and removed < (self.screenshot_count - self.max_screenshots):
            del msg["images"]
            removed += 1

            # Log what we removed
            logger.debug(f"Auto-removed image from: {msg.get('content', '')[:50]}")
```

---

## Example 6: Integration Nightmare

### Real Flow in brain_enhanced_v2.py

```python
# Initialization (lines 1023-1040)
self._uitars_context = ConversationContext(max_screenshots=5)
self._history_pruner = HistoryPruner(
    max_history_items=10,
    preserve_recent=10,
    summarize_older=True
)

# During task execution (hypothetical):
async def execute_task(self, goal: str):
    for step in range(10):
        # Step 1: Take screenshot
        snapshot = await self.browser.snapshot()

        # Step 2: Add to UITARS context
        self._uitars_context.add_message(
            "assistant",
            f"Step {step}: {action}",
            screenshot_b64
        )

        # Step 3: Process action
        result = await self._process_action(action)

        # Step 4: Call LLM
        if step % 3 == 0:  # Every 3 steps
            # BEFORE LLM call, prune history
            pruned = self._history_pruner.prune(self.messages)

            # Send to LLM
            response = await self.call_llm(pruned)

            # Process response...

# Multiple systems touched:
# 1. A11y snapshot cache (may return cached/fresh)
# 2. Snapshot diff (may return Snapshot/SnapshotDiff)
# 3. ConversationContext (auto-prunes at max_screenshots=5)
# 4. HistoryPruner (auto-prunes images to KEEP_LAST_N_SCREENSHOTS=1)
# 5. Message list (self.messages from brain)

# Result: Screenshot appears in 3+ places:
# - A11y cache
# - Snapshot object
# - ConversationContext.messages
# - Brain.messages
# - LLM request

# Possible for SAME screenshot to be pruned multiple times!
```

---

## Summary of Conflicts

| Conflict | File | Line | Impact | Severity |
|----------|------|------|--------|----------|
| Cache doesn't update `_previous_snapshot` | a11y_browser.py | 1162-1170 | Diff accuracy | CRITICAL |
| Multiple screenshot limits (5 vs 1) | a11y_config.py + ui_tars_patterns.py + history_pruner.py | Various | Token explosion | HIGH |
| Return type ambiguity (Snapshot vs SnapshotDiff) | a11y_browser.py | 1130 | Type errors | MEDIUM |
| TTL window misses page changes | a11y_config.py | 11 | Stale snapshots | MEDIUM |
| Auto-pruning surprises | ui_tars_patterns.py | 121 | Lost context | LOW |
| Multiple systems touching same data | brain_enhanced_v2.py | Multiple | State corruption | MEDIUM |

