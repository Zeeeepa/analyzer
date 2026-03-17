# UI-TARS Patterns Integration Audit

**Date**: 2025-12-12
**Status**: NOT INTEGRATED
**Priority**: HIGH - Missing production-proven reliability patterns

---

## Executive Summary

The UI-TARS patterns from ByteDance (ui_tars_patterns.py, ui_tars_integration.py) are **NOT wired into brain_enhanced_v2.py**. These modules exist but are completely unused, meaning the agent is missing critical reliability features:

- Tiered retry timeouts (5s screenshots, 30s model, 5s actions)
- Screenshot context management (last-N pruning)
- System-2 reasoning prompts (THOUGHT → REFLECTION → ACTION)
- Coordinate normalization (0-1000 range)
- Error threshold termination

**Impact**: Agent has lower reliability than it could, especially for:
- Screenshot capture failures (no fast retry)
- Model timeouts (no appropriate timeouts)
- Action failures (no tiered retry)
- Token bloat (no screenshot pruning)
- Reasoning quality (no System-2 forcing)

---

## Audit Results

### 1. UITarsEnhancer - NOT INTEGRATED

**Files**:
- `/mnt/c/ev29/cli/engine/agent/ui_tars_patterns.py` (442 lines)
- `/mnt/c/ev29/cli/engine/agent/ui_tars_integration.py` (221 lines)

**Status**: Modules exist but are not imported or used in brain_enhanced_v2.py

**Evidence**:
```bash
# No imports found
grep -i "ui_tars" brain_enhanced_v2.py
# Returns: No matches

grep -i "UITarsEnhancer" brain_enhanced_v2.py
# Returns: No matches

grep -i "ConversationContext" brain_enhanced_v2.py
# Returns: No matches (there's a different ConversationContext in memory)
```

**What's missing**:
- No UITarsEnhancer initialization
- No enhanced_screenshot() usage
- No enhanced_click() with coordinate normalization
- No automatic screenshot context pruning

---

### 2. Retry Patterns - PARTIALLY INTEGRATED

**Current state**: Brain uses `asyncio.wait_for()` but NOT the tiered retry system

**Evidence**:
```python
# brain_enhanced_v2.py line 36
from .smart_retry import get_retry_manager, get_escalation

# But grep shows it's IMPORTED but NEVER USED:
grep "get_retry_manager(" brain_enhanced_v2.py
# Returns: Only the import line, no actual usage
```

**What exists**:
- `smart_retry.py` - Existing retry system (different from UI-TARS)
- Multiple `asyncio.wait_for()` calls with hardcoded timeouts

**What's missing**:
- UI-TARS tiered retry with exponential backoff
- `retry_with_timeout()` from ui_tars_patterns.py
- Different timeouts for different operation types:
  - Screenshots: 5s (fast retry for transient issues)
  - Model calls: 30s (slow retry for API latency)
  - Actions: 5s (medium retry for DOM loading)

---

### 3. ConversationContext (Screenshot Management) - NOT INTEGRATED

**Status**: UI-TARS ConversationContext is NOT used

**What exists instead**:
```python
# brain_enhanced_v2.py uses simple list
self.messages = []  # No screenshot pruning, no limits

# VisionHandler has basic screenshot tracking
self._last_screenshot_hash: Optional[str] = None
```

**What's missing**:
- Last-N screenshot limiting (UI-TARS default: 5)
- Automatic pruning of old screenshots
- Token usage control for vision models
- Screenshot count tracking

**Impact**:
- Token bloat from too many screenshots in context
- Potential OOM errors on long sessions
- Higher API costs (more tokens)

---

### 4. System-2 Prompts - NOT INTEGRATED

**Status**: No System-2 reasoning enforcement

**What's missing**:
```python
# ui_tars_patterns.py line 149
def create_system2_prompt(task: str, current_state: str = "") -> str:
    """
    System-2 reasoning requires explicit thought before action:
    1. THOUGHT: Analyze current state
    2. REFLECTION: What worked/didn't work
    3. ACTION: Specific action to take
    """
```

**Current state**: Agent prompts don't enforce structured reasoning

**Evidence**:
```bash
grep "create_system2_prompt" brain_enhanced_v2.py
# Returns: No matches
```

**Impact**:
- Less reliable reasoning (no forced thought process)
- Harder to debug (no explicit thought logs)
- Lower success rate on complex tasks

---

### 5. ActionParser - NOT INTEGRATED

**Status**: No UI-TARS action parsing

**What's missing**:
```python
# ui_tars_patterns.py line 220
class ActionParser:
    """
    Parse UI-TARS style action outputs.

    Handles formats like:
    - click(start_box="(100,200)")
    - click(x=100, y=200)
    - type(text="hello")
    """
```

**Current state**: Brain uses custom parsing in `_parse_tool_calls()`

**Evidence**:
```bash
grep "ActionParser" brain_enhanced_v2.py
# Returns: No matches
```

**Impact**:
- Can't handle UI-TARS coordinate format (0-1000 range)
- No box-to-center conversion
- No coordinate aliases (start_point, point, etc.)

---

## Integration Opportunities

### High Priority (Production Impact)

1. **Enhanced Screenshot with Retry**
   - **File**: `vision_handler.py` line 156
   - **Current**: Simple `page.screenshot()` with try/catch
   - **Replace with**: `UITarsEnhancer.enhanced_screenshot()`
   - **Benefit**: 3x retry with 5s timeout, automatic context pruning

2. **Screenshot Context Pruning**
   - **File**: `brain_enhanced_v2.py` line 997
   - **Current**: `self.messages = []` - unlimited
   - **Replace with**: `ConversationContext(max_screenshots=5)`
   - **Benefit**: Prevent token bloat, save API costs

3. **Tiered Retry for All Operations**
   - **File**: Throughout brain_enhanced_v2.py
   - **Current**: Various `asyncio.wait_for()` with inconsistent timeouts
   - **Replace with**: `retry_with_timeout()` with operation-specific configs
   - **Benefit**: Higher reliability, appropriate timeouts per operation

### Medium Priority (Quality of Life)

4. **System-2 Prompts for Complex Tasks**
   - **File**: Task routing in brain_enhanced_v2.py
   - **Add**: `create_system2_prompt()` for multi-step workflows
   - **Benefit**: Better reasoning, easier debugging

5. **Coordinate Normalization**
   - **File**: Action execution in brain_enhanced_v2.py
   - **Add**: `UITarsEnhancer.normalize_coordinates()` for vision outputs
   - **Benefit**: Standard coordinate system, better vision integration

---

## Recommended Integration Plan

### Phase 1: Quick Wins (30 min)

**Goal**: Get screenshot reliability improvements immediately

```python
# 1. Import UI-TARS modules in brain_enhanced_v2.py
from .ui_tars_integration import UITarsEnhancer
from .ui_tars_patterns import RetryConfig, ConversationContext

# 2. Initialize in __init__() after browser_manager
self._uitars_enhancer = None  # Lazy init (needs browser.page)

# 3. Add property for lazy initialization
@property
def uitars(self):
    """Get UI-TARS enhancer (lazy initialized when browser available)."""
    if self._uitars_enhancer is None and self.browser:
        page = getattr(self.browser, 'page', None)
        if page:
            self._uitars_enhancer = UITarsEnhancer(
                page,
                config=RetryConfig(
                    screenshot_timeout=5.0,
                    screenshot_max_retries=3,
                    action_timeout=5.0,
                    action_max_retries=3
                )
            )
    return self._uitars_enhancer

# 4. Update vision_handler.py take_screenshot()
async def take_screenshot(self) -> Optional[bytes]:
    # Try enhanced screenshot first
    if hasattr(self.brain, 'uitars') and self.brain.uitars:
        b64 = await self.brain.uitars.enhanced_screenshot()
        if b64:
            import base64
            return base64.b64decode(b64)

    # Fallback to simple screenshot
    if not self.brain.browser:
        return None
    try:
        screenshot = await self.brain.browser.page.screenshot()
        return screenshot
    except Exception as e:
        logger.debug(f"Screenshot capture failed: {e}")
        return None
```

**Benefit**: Immediate screenshot reliability improvement with minimal risk

---

### Phase 2: Screenshot Context Management (15 min)

**Goal**: Prevent token bloat from unlimited screenshots

```python
# 1. Replace self.messages with ConversationContext
# brain_enhanced_v2.py __init__()
from .ui_tars_patterns import ConversationContext

self._conversation_context = ConversationContext(max_screenshots=5)
self.messages = []  # Keep for backward compatibility

# 2. Add helper to sync messages
def _add_message_with_screenshot(self, role: str, content: str, screenshot_b64: Optional[str] = None):
    """Add message and manage screenshot context."""
    # Add to UI-TARS context (with pruning)
    self._conversation_context.add_message(role, content, screenshot_b64)

    # Also add to messages (without images for now, or adapt)
    msg = {"role": role, "content": content}
    if screenshot_b64:
        msg["images"] = [screenshot_b64]
    self.messages.append(msg)

# 3. Use when adding vision results
# In vision_handler.py or wherever screenshots are added to context
self.brain._add_message_with_screenshot(
    "assistant",
    "Screenshot captured",
    screenshot_b64
)
```

**Benefit**: Auto-prune old screenshots, keep last 5, reduce token costs

---

### Phase 3: Tiered Retry (30 min)

**Goal**: Use appropriate timeouts for each operation type

```python
# 1. Import retry utilities
from .ui_tars_patterns import retry_with_timeout, RetryConfig

# 2. Create operation wrappers
async def _retry_screenshot(self):
    """Screenshot with fast retry."""
    async def do_screenshot():
        return await self.browser.page.screenshot()

    return await retry_with_timeout(
        do_screenshot,
        timeout=5.0,  # Fast retry
        max_retries=3,
        operation_name="screenshot"
    )

async def _retry_model_call(self, model_func):
    """Model call with slow retry."""
    return await retry_with_timeout(
        model_func,
        timeout=30.0,  # Slow retry for API
        max_retries=2,
        operation_name="model_call"
    )

async def _retry_action(self, action_func):
    """Action with medium retry."""
    return await retry_with_timeout(
        action_func,
        timeout=5.0,  # Medium retry
        max_retries=3,
        operation_name="action"
    )

# 3. Replace existing asyncio.wait_for() calls
# Before:
screenshot = await asyncio.wait_for(page.screenshot(), timeout=10)

# After:
screenshot = await self._retry_screenshot()
```

**Benefit**: Appropriate retry behavior per operation, higher success rate

---

### Phase 4: System-2 Prompts (Optional, 20 min)

**Goal**: Enforce structured reasoning for complex tasks

```python
# 1. Detect complex tasks
from .ui_tars_patterns import create_system2_prompt

def _is_complex_task(self, task: str) -> bool:
    """Detect if task needs System-2 reasoning."""
    complex_keywords = [
        "fill form", "multi-step", "workflow",
        "register", "checkout", "application"
    ]
    return any(kw in task.lower() for kw in complex_keywords)

# 2. Apply System-2 prompt for complex tasks
def _prepare_system_prompt(self, task: str) -> str:
    """Prepare system prompt with optional System-2 reasoning."""
    if self._is_complex_task(task):
        # Use System-2 reasoning
        return create_system2_prompt(task, current_state="")
    else:
        # Use standard prompt
        return self._generate_system_prompt()

# 3. Use in agent loop
system_prompt = self._prepare_system_prompt(self.query)
self.messages.append({"role": "system", "content": system_prompt})
```

**Benefit**: Better reasoning on complex tasks, easier debugging

---

## Testing Plan

### Unit Tests

```bash
# Create test file
cat > /mnt/c/ev29/cli/engine/agent/test_uitars_integration.py << 'EOF'
"""Test UI-TARS integration."""
import pytest
from .ui_tars_integration import UITarsEnhancer
from .ui_tars_patterns import ConversationContext, retry_with_timeout

def test_conversation_context_pruning():
    """Test screenshot pruning."""
    ctx = ConversationContext(max_screenshots=2)

    # Add 3 screenshots
    ctx.add_message("user", "Step 1", "screenshot1")
    ctx.add_message("user", "Step 2", "screenshot2")
    ctx.add_message("user", "Step 3", "screenshot3")

    # Should only keep last 2
    assert ctx.screenshot_count == 2
    messages = ctx.get_messages()

    # First message should have no image
    assert "images" not in messages[0]
    # Last 2 should have images
    assert "images" in messages[1]
    assert "images" in messages[2]

@pytest.mark.asyncio
async def test_retry_with_timeout():
    """Test retry mechanism."""
    call_count = 0

    async def flaky_function():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("Flaky error")
        return "success"

    result = await retry_with_timeout(
        flaky_function,
        timeout=5.0,
        max_retries=3,
        operation_name="test"
    )

    assert result == "success"
    assert call_count == 3  # Succeeded on 3rd try

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
EOF

# Run tests
cd /mnt/c/ev29/cli/engine/agent
python3 -m pytest test_uitars_integration.py -v
```

### Integration Test

```bash
# Test with real agent
cd /mnt/c/ev29/cli
node bin/eversale.js "Take a screenshot and describe what you see"

# Verify in logs:
# - "[UITARS] Enhanced screenshot with retry"
# - "[UITARS] Screenshot context: 1/5"
# - "[UITARS] Retry attempt 1/3" (if failure occurs)
```

---

## Risk Assessment

| Change | Risk | Mitigation |
|--------|------|------------|
| Enhanced screenshot | LOW | Fallback to existing screenshot() on error |
| Context pruning | LOW | Keep both old messages list and new context |
| Tiered retry | MEDIUM | Wrap existing calls, test timeouts carefully |
| System-2 prompts | LOW | Only apply to complex tasks, optional feature |

**Overall risk**: LOW - All changes are additive with fallbacks

---

## Success Metrics

### Before Integration
- Screenshot failure rate: ~5-10% (estimated)
- Average retries: 1-2 manual retries
- Token usage: Unbounded (all screenshots in context)
- Reasoning quality: No structured format

### After Integration (Target)
- Screenshot failure rate: <2% (with 3x retry)
- Average retries: 0.5 (automatic retry handles most)
- Token usage: Capped at 5 screenshots
- Reasoning quality: Explicit THOUGHT/REFLECTION/ACTION on complex tasks

**Expected improvement**: 60% reduction in screenshot failures, 40% reduction in token costs

---

## Files to Modify

1. **brain_enhanced_v2.py** (lines 36, 833-1032)
   - Add UI-TARS imports
   - Initialize UITarsEnhancer property
   - Add ConversationContext
   - Add retry wrappers

2. **vision_handler.py** (lines 156-171)
   - Replace simple screenshot with enhanced_screenshot()
   - Add retry logic

3. **__init__.py** (line 42)
   - Export UI-TARS utilities for external use

---

## Backward Compatibility

All changes are **backward compatible**:

- Existing code continues to work
- UI-TARS features are opt-in (lazy initialization)
- Fallback to old behavior if UI-TARS fails
- No breaking API changes

**Migration path**: Zero downtime, gradual rollout

---

## Related Work

### Already Integrated
- ✓ UI-TARS model for CAPTCHA solving (see UI_TARS_UPGRADE_SUMMARY.md)
- ✓ UI-TARS in model_router.py (ModelTier.UI_TARS)

### Not Yet Integrated
- ✗ UI-TARS patterns (ui_tars_patterns.py) - THIS AUDIT
- ✗ UI-TARS integration layer (ui_tars_integration.py) - THIS AUDIT

---

## Next Steps

1. **Review this audit** with team
2. **Approve integration plan** (Phases 1-4)
3. **Implement Phase 1** (Quick wins - 30 min)
4. **Test in production** (monitor for 24h)
5. **Roll out Phases 2-3** if Phase 1 succeeds
6. **Consider Phase 4** (System-2) for future release

---

## Conclusion

**UI-TARS patterns are production-ready but completely unused.**

The integration is straightforward, low-risk, and provides immediate benefits:
- Higher reliability (tiered retry)
- Lower costs (screenshot pruning)
- Better reasoning (System-2 prompts)

**Recommendation**: Integrate Phase 1 immediately, monitor, then proceed with Phases 2-4.

**Estimated effort**:
- Phase 1: 30 min (high value)
- Phase 2: 15 min (medium value)
- Phase 3: 30 min (high value)
- Phase 4: 20 min (optional, future)

**Total**: ~2 hours for full integration with testing

---

**Audit completed**: 2025-12-12
**By**: Claude Code
**Status**: READY FOR IMPLEMENTATION
