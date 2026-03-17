# History Pruner - Code Reference & Line Numbers

## System 1: UI-TARS ConversationContext

### Location
- **File**: `/mnt/c/ev29/cli/engine/agent/ui_tars_patterns.py`
- **Lines**: 100-147

### Class Definition
```python
# ui_tars_patterns.py:100-147
@dataclass
class ConversationContext:
    """
    Manages conversation history with screenshot context.

    UI-TARS pattern: Keep only last N screenshots to limit token usage.
    Default: 5 screenshots (configurable)
    """
    max_screenshots: int = 5
    messages: List[Dict[str, Any]] = field(default_factory=list)
    screenshot_count: int = 0

    def add_message(self, role: str, content: str, screenshot_b64: Optional[str] = None):
        """Add message with optional screenshot"""
        message = {"role": role, "content": content}

        if screenshot_b64:
            message["images"] = [screenshot_b64]
            self.screenshot_count += 1

            # Prune old screenshots if over limit
            self._prune_screenshots()  # LINE 121

        self.messages.append(message)

    def _prune_screenshots(self):  # LINE 125
        """Remove screenshots from oldest messages to stay under limit"""
        if self.screenshot_count <= self.max_screenshots:
            return

        removed = 0
        for msg in self.messages:
            if "images" in msg and removed < (self.screenshot_count - self.max_screenshots):
                del msg["images"]
                removed += 1

        self.screenshot_count -= removed
        logger.debug(f"Pruned {removed} old screenshots, keeping last {self.max_screenshots}")
```

### Status: **NOT USED**
- **Created at**: `brain_enhanced_v2.py:1023-1024`
- **Reference**: `self._uitars_context = ConversationContext(max_screenshots=5)`
- **Call site**: NO CALL TO `.add_message()` ANYWHERE
- **Impact**: Dead code - system initialized but never activated

### Search Results
```
grep -n "add_message.*screenshot" brain_enhanced_v2.py
grep -n "_uitars_context.add_message" brain_enhanced_v2.py
grep -n "\.add_message" ui_tars_patterns.py
# All return: (no matches)
```

---

## System 2: HistoryPruner

### Location
- **File**: `/mnt/c/ev29/cli/engine/agent/history_pruner.py`
- **Lines**: 1-325

### Main Classes

#### HistoryPruner Class (lines 12-231)
```python
# history_pruner.py:12-231
class HistoryPruner:
    """Prunes conversation history to reduce token usage by 50-60%."""

    def __init__(
        self,
        max_history_items: int = 10,
        preserve_recent: int = 3,
        summarize_older: bool = True
    ):
        """Initialize history pruner"""
        self.max_history_items = max_history_items
        self.preserve_recent = preserve_recent
        self.summarize_older = summarize_older

    def prune(self, messages: List[Dict]) -> List[Dict]:  # LINE 33
        """
        Prune conversation history.

        Rules:
        1. Always keep system prompt (first message)
        2. Always keep last `preserve_recent` messages in full
        3. Summarize older messages to: "Step N: [action] - [result]"
        4. Remove all screenshots/images from non-recent messages
        5. Cap total messages at max_history_items
        """
        # ... 60+ lines of logic

    def _summarize_step(self, message: Dict, step_num: int) -> Dict:  # LINE 97
        """Convert a full step message to a compact summary"""

    def _extract_user_intent(self, content: str) -> str:  # LINE 139
        """Extract main intent from user message"""

    def _extract_assistant_action(self, content: str) -> str:  # LINE 164
        """Extract main action from assistant message"""

    def _remove_images(self, message: Dict) -> Dict:  # LINE 193
        """
        Strip base64 images and screenshot data from message.

        Handles:
        - Multi-part content with image entries
        - String content with base64 data URLs
        - Converts to placeholder text
        """
        # ... image removal logic

    def _estimate_tokens(self, messages: List[Dict]) -> int:  # LINE 233
        """Rough token estimate (chars / 4)"""
```

#### Standalone Function (lines 269-324)
```python
# history_pruner.py:269-324
def prune_screenshots_from_history(messages: List[Dict], keep_last_n: int = 1) -> List[Dict]:
    """
    Remove all screenshots except the last N from conversation history.

    Aggressive pruning for screenshot-heavy conversations. Keeps only the
    most recent N screenshots for context while removing all older ones.
    """
    # ... aggressive screenshot removal logic
```

### Initialization in brain_enhanced_v2.py

**Location**: `brain_enhanced_v2.py:1033-1038`
```python
# brain_enhanced_v2.py:1033-1038
if HISTORY_PRUNER_AVAILABLE and HistoryPruner:
    self._history_pruner = HistoryPruner(
        max_history_items=self._max_context_messages,  # From config: 100
        preserve_recent=10,
        summarize_older=True
    )
    logger.info("[HISTORY] History pruner enabled for token optimization")
else:
    self._history_pruner = None
```

### Configuration Values

**File**: `/mnt/c/ev29/cli/engine/agent/brain_config.py`

```python
# brain_config.py:99-100
DEFAULT_MAX_CONTEXT_MESSAGES = 100
DEFAULT_COMPACT_THRESHOLD = 80
```

**Used at**: brain_enhanced_v2.py:1013-1014
```python
self._max_context_messages = self._brain_config.max_context_messages  # 100
self._compact_threshold = self._brain_config.compact_threshold        # 80
```

### Status: **READY BUT NOT CALLED**
- **Initialized**: Yes (line 1033)
- **Used by**: `_compact_context()` method (NEVER CALLED)
- **Active in flow**: No
- **Call site**: `_compact_context()` at line 4237, but _compact_context() is never invoked

---

## System 3: brain_enhanced_v2.py::_compact_context()

### Location
- **File**: `/mnt/c/ev29/cli/engine/agent/brain_enhanced_v2.py`
- **Lines**: 4217-4286 (70 lines)
- **Definition Only**: NO CALL SITES

### Method Implementation

```python
# brain_enhanced_v2.py:4217-4286
def _compact_context(self):
    """Compact context when messages exceed threshold.

    Like Claude Code's context compaction - summarizes older messages
    to fit within context window limits.

    Uses HistoryPruner if available for intelligent pruning with:
    - Screenshot removal from old messages (50-60% token reduction)
    - Message summarization (preserves context with minimal tokens)
    - Automatic preservation of recent messages for context
    """
    if len(self.messages) < self._compact_threshold:  # LINE 4228, threshold=80
        return

    logger.info(f"Compacting context: {len(self.messages)} messages")
    self._notify_progress("Compacting context")

    # Use HistoryPruner if available - it's smarter and more efficient
    if self._history_pruner:  # LINE 4235
        original_count = len(self.messages)
        self.messages = self._history_pruner.prune(self.messages)  # LINE 4237
        logger.info(f"[HISTORY] Pruned context: {original_count} -> {len(self.messages)} messages")
        return

    # Fallback to manual compaction if HistoryPruner not available
    # Keep system message and first user message
    system_msgs = [m for m in self.messages if m.get('role') == 'system']
    first_user = None
    for m in self.messages:
        if m.get('role') == 'user':
            first_user = m
            break

    # Keep last N messages for recency
    keep_recent = 10
    recent_msgs = self.messages[-keep_recent:]

    # Summarize middle section (tool calls and results)
    middle_start = len(system_msgs) + (1 if first_user else 0)
    middle_end = len(self.messages) - keep_recent
    middle_msgs = self.messages[middle_start:middle_end]

    if middle_msgs:
        # ... manual summarization logic (fallback)

    # Reconstruct messages
    self.messages = system_msgs
    if first_user:
        self.messages.append(first_user)
    self.messages.append(summary_msg)
    self.messages.extend(recent_msgs)

    logger.info(f"Context compacted to {len(self.messages)} messages")
```

### Trigger Analysis

**Search for calls to _compact_context()**:
```bash
$ grep -n "_compact_context()" brain_enhanced_v2.py
# Result: (no matches found)
# Only definition at line 4217 found
```

### Why It's Never Called

1. **No direct calls**: Zero invocations of `self._compact_context()`
2. **No conditional trigger**: No logic that says "if messages grow, compact"
3. **No periodic trigger**: No "every N steps, compact" logic
4. **No threshold check**: Method exists to check threshold but nothing triggers it

---

## Message Accumulation Points

### Where messages are appended (brain_enhanced_v2.py)

```
Line 3690:  self.messages.append({...})
Line 3839:  self.messages.append({...})
Line 4065:  self.messages.append({...})
Line 4129:  self.messages.append(system_message)
Line 4207:  inject_steering_message(self.messages, msg)
Line 4237:  self.messages = self._history_pruner.prune(...)  [COMPACTION - NEVER CALLED]
... and more
```

### No corresponding cleanup

- **Before LLM call**: No compaction
- **After tool execution**: No compaction
- **Every N steps**: No compaction
- **When message count exceeds X**: No compaction

---

## Import Chain

### HistoryPruner imports
```python
# brain_enhanced_v2.py:55-63
try:
    from .history_pruner import HistoryPruner, prune_screenshots_from_history
    HISTORY_PRUNER_AVAILABLE = True
except ImportError:
    HistoryPruner = None
    prune_screenshots_from_history = None
    HISTORY_PRUNER_AVAILABLE = False
    logger.debug("History pruner not available")
```

### UI-TARS imports
```python
# brain_enhanced_v2.py:42-53
try:
    from .ui_tars_integration import UITarsEnhancer
    from .ui_tars_patterns import RetryConfig, ConversationContext, retry_with_timeout
    UITARS_AVAILABLE = True
except ImportError:
    UITarsEnhancer = None
    RetryConfig = None
    ConversationContext = None
    retry_with_timeout = None
    UITARS_AVAILABLE = False
```

---

## Conflict Resolution: Which System Wins?

### Current State
```
UI-TARS Context:        Initialized (1023-1024) → Never used
HistoryPruner:          Initialized (1033-1038) → Never used
_compact_context():     Defined (4217-4286)    → Never called
Result:                 Message accumulation uncontrolled
```

### Recommended Architecture

**Keep**: HistoryPruner (most sophisticated)
- Removes images from old messages
- Summarizes complex messages to short form
- Configurable limits and preservation

**Remove**: ConversationContext
- Unused and creates confusion
- Conflicting philosophy (aggressive vs. smart)
- Simple screenshot limiting handled by HistoryPruner

**Activate**: _compact_context()
- Add trigger: `if len(self.messages) >= self._compact_threshold: self._compact_context()`
- Place before each `ollama_client.chat()` call
- Or call every N iterations

---

## Token Accumulation Risk

### Scenario: 25-iteration task with vision

```
Iteration 1: screenshot (4KB base64) + 2 messages = ~1000 tokens
Iteration 2: screenshot (4KB base64) + 2 messages = ~1000 tokens
...
Iteration 25: ~25 screenshots + 50 messages = ~30,000 tokens

With base64 screenshot encoding overhead:
  25 × (4000 chars base64) / 1.5 = ~67,000 tokens for screenshots alone

Total conversation: 50,000-100,000 tokens
Many models limit: 4k-8k context (can't fit)
Small models: 8k context (can fit early iterations only)

RISK: Context exhaustion BEFORE hitting 80-message threshold for compaction
```

---

## Files Needing Updates

| File | Lines | Action | Status |
|------|-------|--------|--------|
| `history_pruner.py` | All | Keep as-is (working code) | OK |
| `ui_tars_patterns.py` | 100-147 | Deprecate/remove unused ConversationContext | UNUSED |
| `brain_enhanced_v2.py` | 1023-1024 | Remove `_uitars_context` initialization | DEAD CODE |
| `brain_enhanced_v2.py` | 1033-1038 | Keep `_history_pruner` initialization | GOOD |
| `brain_enhanced_v2.py` | 4217-4286 | Add trigger/activation mechanism | NEEDS WIRING |
| `brain_config.py` | 99-100 | Keep config values | OK |

---

## Summary

**Three systems exist, zero are active:**
1. **UI-TARS ConversationContext** - Takes screenshots to 5 max, but never called
2. **HistoryPruner** - Full compression system, but never called
3. **_compact_context()** - Orchestrator method, but never called

**Recommended action:** Wire HistoryPruner into execution flow by:
1. Keeping HistoryPruner as-is (sophisticated, working)
2. Removing unused ConversationContext
3. Adding trigger to call `_compact_context()` periodically
4. Testing with long conversations to verify token reduction

**HistoryPruner should win** because it's more sophisticated and already has fallback logic in `_compact_context()`.
