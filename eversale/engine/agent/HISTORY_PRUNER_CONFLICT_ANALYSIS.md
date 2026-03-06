# History/Context Compaction Conflict Analysis

## Executive Summary

**CONFLICT DETECTED**: Two overlapping history/context management systems exist in the codebase that BOTH prune screenshots and messages:

1. **UI-TARS ConversationContext** (ui_tars_patterns.py)
   - Prunes screenshots to last N (default: 5)
   - Runs on `add_message()` calls
   - Separates images from text content
   - Active but appears UNUSED in brain_enhanced_v2.py

2. **HistoryPruner** (history_pruner.py)
   - Prunes messages and screenshots comprehensively
   - Summarizes old messages to compact them
   - Capped at max_history_items (default: 100)
   - Preserves last N recent messages (default: 10)
   - Has `_compact_context()` method but is NEVER CALLED

3. **brain_enhanced_v2.py `_compact_context()` method** (lines 4217-4286)
   - Defined but NEVER CALLED anywhere in the codebase
   - Should call HistoryPruner.prune() when invoked
   - Has fallback manual compaction logic if HistoryPruner unavailable

---

## Detailed Conflict Map

### 1. UI-TARS ConversationContext (ui_tars_patterns.py:100-147)

#### What it does:
```python
@dataclass
class ConversationContext:
    max_screenshots: int = 5        # Hard limit on screenshots
    messages: List[Dict]
    screenshot_count: int = 0

    def add_message(self, role, content, screenshot_b64=None):
        if screenshot_b64:
            self.screenshot_count += 1
            self._prune_screenshots()  # PRUNING HAPPENS HERE

    def _prune_screenshots(self):
        """Remove screenshots from oldest messages to stay under limit"""
        if self.screenshot_count <= self.max_screenshots:
            return
        # Removes image entries from oldest messages
```

#### Configuration:
- **Location**: brain_enhanced_v2.py:1023-1025
- **Initialization**: `self._uitars_context = ConversationContext(max_screenshots=5)`
- **Status**: Initialized if UI-TARS available
- **Usage**: **NEVER USED** - instantiated but `add_message()` is never called

#### Behavior:
- Keeps only last 5 screenshots
- Strips image entries from older messages
- Preserves message text content

---

### 2. HistoryPruner (history_pruner.py:1-325)

#### What it does:
```python
class HistoryPruner:
    def __init__(
        self,
        max_history_items: int = 10,      # Total message cap
        preserve_recent: int = 3,          # Keep recent in full
        summarize_older: bool = True       # Compress vs delete
    )

    def prune(self, messages: List[Dict]) -> List[Dict]:
        """
        1. Keep system prompt (always)
        2. Keep last `preserve_recent` messages in full
        3. Summarize older messages to compact form
        4. Remove all screenshots/images from non-recent
        5. Cap at max_history_items
        """
        # ... comprehensive pruning logic

    def _remove_images(self, message: Dict) -> Dict:
        """Strip base64 images and screenshot data"""
```

#### Configuration in brain_enhanced_v2.py:
```python
self._history_pruner = HistoryPruner(
    max_history_items=self._max_context_messages,    # Default: 100
    preserve_recent=10,                              # Keep last 10 full
    summarize_older=True                             # Compress others
)
```

#### Defaults from brain_config.py:
```python
DEFAULT_MAX_CONTEXT_MESSAGES = 100
DEFAULT_COMPACT_THRESHOLD = 80
```

#### Behavior:
- Keeps system prompt + last 10 messages in full detail
- Summarizes messages 11-90 to compact format: "Step N: [action] - [result]"
- Removes all images from messages outside the last 10
- When messages exceed 100 total, deletes/summarizes oldest
- Achieves 50-60% token reduction

---

### 3. brain_enhanced_v2.py::_compact_context() (lines 4217-4286)

#### Status: **DEFINED BUT NEVER CALLED**

```python
def _compact_context(self):
    """Compact context when messages exceed threshold."""
    if len(self.messages) < self._compact_threshold:  # 80 messages
        return

    logger.info(f"Compacting context: {len(self.messages)} messages")

    # BRANCH 1: Uses HistoryPruner if available
    if self._history_pruner:
        original_count = len(self.messages)
        self.messages = self._history_pruner.prune(self.messages)
        logger.info(f"[HISTORY] Pruned: {original_count} -> {len(self.messages)}")
        return

    # BRANCH 2: Fallback manual compaction
    # ... Manual logic that does similar pruning
```

#### Why it's never called:
- **Search result**: Only definition found at line 4217
- **No call sites**: `grep "_compact_context()"` returns no hits
- **No trigger**: No code path calls this method
- **Threshold**: Would only trigger at 80+ messages, but never invoked

---

## Conflict Summary Table

| Aspect | UI-TARS Context | HistoryPruner | _compact_context() |
|--------|-----------------|---------------|--------------------|
| **File** | ui_tars_patterns.py | history_pruner.py | brain_enhanced_v2.py |
| **Scope** | Screenshots only | Messages + screenshots | Messages + screenshots |
| **Screenshot limit** | 5 (hardcoded) | Via message summarization | Via fallback logic |
| **Message limit** | None (unlimited) | 100 (configurable) | 80 threshold (configurable) |
| **Summarization** | No | Yes (compact form) | Yes (fallback only) |
| **Status** | Initialized but unused | Implemented, ready but not called | Method exists but never invoked |
| **Active in flow** | No | No | No |

---

## Key Findings

### 1. **All Three Systems Are Partially Orphaned**

✗ UI-TARS ConversationContext
- Instantiated in line 1023-1024
- `add_message()` never called anywhere
- Acts as dead code / unused import

✗ HistoryPruner
- Instantiated in lines 1033-1038
- Object created but `.prune()` never called
- Stored in `self._history_pruner` but unused

✗ _compact_context()
- Defined but never invoked
- No trigger mechanism exists
- Would work if called, but no one calls it

### 2. **Message Handling Is Unmanaged**

`self.messages` is appended to throughout brain_enhanced_v2.py:
- Lines: 3690, 3839, 4065, 4129, and many more
- **No compaction trigger exists** to control growth
- Conversation can grow unbounded until hitting model context limits
- Screenshots accumulate in messages (base64 encoded)

### 3. **Screenshot Pruning Gap**

Two mechanisms exist but neither is active:
- **UI-TARS** wants to keep 5 screenshots max (aggressive)
- **HistoryPruner** strips images from non-recent messages (smart)
- **Reality** screenshots keep accumulating in `self.messages`

### 4. **Configuration Mismatch**

| Setting | Value | Where used |
|---------|-------|-----------|
| `DEFAULT_MAX_CONTEXT_MESSAGES` | 100 | HistoryPruner initialization |
| `DEFAULT_COMPACT_THRESHOLD` | 80 | Checked in _compact_context() |
| `ConversationContext.max_screenshots` | 5 | Never accessed |
| `preserve_recent` | 10 | HistoryPruner param |

These are defined but unused in actual flow.

---

## Architecture Issues

### Issue 1: Two Screenshot Pruning Strategies
```
Conflicting philosophies:
- UI-TARS: Keep ONLY last 5 screenshots (aggressive)
- HistoryPruner: Remove images from old messages, keep structure (smart)
- Reality: All screenshots stay in messages indefinitely
```

### Issue 2: Message Summarization Not Implemented
```
HistoryPruner has logic to summarize:
  "Step 5: User requested Navigate to example.com"

But this is never called, so messages stay verbose:
  [Full 500-char reasoning about navigation...]
  [Tool call with all parameters...]
  [Result with full page HTML...]
```

### Issue 3: No Compaction Trigger
```
Threshold exists (80 messages) but no code path calls _compact_context()

Current flow:
  message appended → LLM called → message appended → LLM called → ...

  No one ever says "enough messages, compact now"
```

### Issue 4: Token Accumulation Risk
```
With DEFAULT_MAX_ITERATIONS = 25 and each step = 2-3 messages:
  25 iterations × 2.5 msgs = 62.5 messages before hitting 80-message threshold

Plus vision/screenshots (base64):
  - 1 screenshot = ~4000 tokens (1/8 of typical context)
  - 25 iterations = ~25 screenshots if each step captures
  - Total screenshot tokens: ~100,000 tokens (EXCEEDS most model limits)

Risk: Model context exhaustion BEFORE compaction would trigger
```

---

## Precedence Recommendations

### IF implementing a new HistoryPruner-based system:

**Clear Priority Order** (best to worst):
1. **HistoryPruner.prune()** should take precedence
   - Most sophisticated (summarization + image removal)
   - Configurable (max_history_items, preserve_recent)
   - Already integrated in _compact_context()

2. **UI-TARS ConversationContext** should be REMOVED or REPURPOSED
   - Currently unused
   - If kept, only use for UI-TARS-specific vision batching (not pruning)
   - Conflicts with HistoryPruner approach

3. **Manual fallback logic** in _compact_context() is backup only
   - Use if HistoryPruner unavailable
   - Don't invoke both

### Recommended Architecture:

```python
# In brain_enhanced_v2.py

def _should_compact(self) -> bool:
    """Check if compaction needed"""
    return len(self.messages) >= self._compact_threshold  # 80 messages

def _run_compaction_cycle(self):
    """
    Intelligently prune messages to stay within token limits.

    Phases:
    1. Screenshot removal (aggressive)
    2. Message summarization (smart)
    3. Token estimation (verify reduction)
    4. Early termination if needed
    """
    if not self._should_compact():
        return

    logger.info(f"Compacting: {len(self.messages)} messages")

    # Use HistoryPruner exclusively
    if self._history_pruner:
        self.messages = self._history_pruner.prune(self.messages)
    else:
        logger.warning("No history pruner, context may grow unbounded")

    # Estimate remaining tokens
    tokens = self._estimate_tokens(self.messages)
    logger.info(f"After compaction: {tokens} tokens ({len(self.messages)} messages)")

# Call at key points:
async def _think_and_act(self):
    # ... before calling model
    self._run_compaction_cycle()

    # Call LLM
    response = self.ollama_client.chat(messages=self.messages)
```

---

## Conflict Resolution Checklist

### If starting fresh HistoryPruner implementation:

- [ ] **Keep HistoryPruner.prune()** - it's the most sophisticated system
- [ ] **Remove ConversationContext** - duplicate/conflicting logic
  - Check if `self._uitars_context` is used elsewhere (it's not)
  - Safe to remove or repurpose for non-pruning use
- [ ] **Activate _compact_context()** or replace with better trigger
  - Add compaction call before each LLM invocation
  - Or use token estimation instead of message count
- [ ] **Set aggressive pruning**
  - `preserve_recent=10` keeps context, good
  - `max_history_items=100` may be too high for long runs
  - Consider `max_history_items=50-60` for safety
- [ ] **Test with long conversations**
  - Ensure token reduction is actually achieved
  - Verify summarization works for vision tasks
- [ ] **Add monitoring**
  - Log before/after token counts
  - Track compaction frequency
  - Alert if tokens still growing

---

## Files Affected

| File | Lines | Conflict |
|------|-------|----------|
| history_pruner.py | 1-325 | Implemented but unused |
| ui_tars_patterns.py | 100-147 | Initialized but unused |
| brain_enhanced_v2.py | 1023-1024 | UI-TARS context created unused |
| brain_enhanced_v2.py | 1033-1038 | HistoryPruner initialized unused |
| brain_enhanced_v2.py | 4217-4286 | _compact_context() defined but never called |
| brain_config.py | 99-100 | Config values defined but never used |

---

## Conclusion

**No implementation conflicts** - both systems can coexist without technical errors, since neither is actually active.

**However, there IS an architectural conflict**:
- Two competing philosophies (aggressive screenshot removal vs. smart message summarization)
- No integration point between them
- Neither system is actually wired into the execution flow

**For a new HistoryPruner implementation**, **HistoryPruner should take precedence** because:
1. More sophisticated (summarization preserves context with fewer tokens)
2. Already partially integrated (_compact_context has branch for it)
3. More configurable and testable
4. UI-TARS system is simpler but unused

**Critical Gap**: The `_compact_context()` method exists but is NEVER CALLED. Adding an integration point to call it (with proper throttling) would activate the entire HistoryPruner system.
