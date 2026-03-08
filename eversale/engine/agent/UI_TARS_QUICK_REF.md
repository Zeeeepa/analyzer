# UI-TARS Integration Quick Reference

**Last updated**: 2025-12-12
**Status**: Phase 1 Complete

---

## What is UI-TARS?

**UI-TARS** (User Interface - Task Automation & Recognition System) from ByteDance.

**Key patterns**:
1. Tiered retry timeouts (screenshot: 5s, model: 30s, action: 5s)
2. Screenshot context pruning (keep last N)
3. System-2 reasoning (THOUGHT → REFLECTION → ACTION)
4. Coordinate normalization (0-1000 range)

**Paper**: https://arxiv.org/html/2501.12326v1
**Source**: https://github.com/bytedance/UI-TARS-desktop

---

## Current Integration Status

### ENABLED
- Enhanced screenshots with 3x retry
- Screenshot context pruning (max 5)
- Tiered retry config available

### NOT YET ENABLED
- System-2 reasoning prompts
- Full tiered retry for all operations
- ActionParser for coordinates

---

## How to Use

### 1. Enhanced Screenshots (Automatic)

**Before**:
```python
screenshot = await page.screenshot()  # No retry
```

**After** (automatic in vision_handler.py):
```python
# Automatically uses UI-TARS if available
screenshot = await brain.uitars.enhanced_screenshot()
# Falls back to simple screenshot if UI-TARS fails
```

### 2. Screenshot Context Pruning (Automatic)

**Automatic in brain initialization**:
```python
self._uitars_context = ConversationContext(max_screenshots=5)
```

No code changes needed - automatically prunes old screenshots.

### 3. Manual UI-TARS Usage (Advanced)

**Get enhancer**:
```python
if brain.uitars:
    # Enhanced click with coordinate normalization
    await brain.uitars.enhanced_click(500, 300, normalized=True)

    # Enhanced screenshot with retry
    b64_screenshot = await brain.uitars.enhanced_screenshot()

    # Get System-2 prompt
    prompt = brain.uitars.get_system2_prompt(task, state)
```

---

## Configuration

### Retry Timeouts (in RetryConfig)

```python
RetryConfig(
    screenshot_timeout=5.0,        # Fast retry (transient issues)
    screenshot_max_retries=3,

    model_timeout=30.0,            # Slow retry (API latency)
    model_max_retries=2,

    action_timeout=5.0,            # Medium retry (DOM loading)
    action_max_retries=3,

    max_screenshot_errors=5,       # Terminate after N errors
    max_consecutive_errors=3       # Terminate after N consecutive
)
```

### Screenshot Context

```python
ConversationContext(
    max_screenshots=5  # Keep only last 5
)
```

---

## Verification

**Check integration**:
```bash
cd /mnt/c/ev29/cli/engine/agent
python3 verify_uitars_integration.py
```

**Expected output**:
```
STATUS: SUCCESS - UI-TARS integration complete!
```

---

## Log Messages

### Startup
```
[UITARS] Screenshot context management enabled (max 5)
[UITARS] Enhanced browser automation with tiered retry enabled
```

### Screenshot Capture
```
[UITARS] Enhanced screenshot captured with 3x retry
```

### Context Pruning
```
Pruned 1 old screenshots, keeping last 5
```

### Retry (if failure)
```
screenshot timeout (attempt 1/3)
[UITARS] Enhanced screenshot failed, falling back: [error]
```

---

## Troubleshooting

### UI-TARS not available
```python
from brain_enhanced_v2 import UITARS_AVAILABLE

if not UITARS_AVAILABLE:
    print("UI-TARS patterns not installed")
```

**Fix**: Ensure ui_tars_patterns.py and ui_tars_integration.py exist

### Enhanced screenshot not being used
**Check**: vision_handler.py line 168-176

**Should see**:
```python
if hasattr(self.brain, 'uitars') and self.brain.uitars:
    b64 = await self.brain.uitars.enhanced_screenshot()
```

### Screenshot context not pruning
**Check**: brain_enhanced_v2.py line 1013-1017

**Should see**:
```python
if UITARS_AVAILABLE and ConversationContext:
    self._uitars_context = ConversationContext(max_screenshots=5)
```

---

## Future Enhancements

### Phase 2: Full Tiered Retry
Apply retry_with_timeout() to all operations:

```python
# Model calls
response = await retry_with_timeout(
    lambda: ollama.generate(model=model, prompt=prompt),
    timeout=30.0,
    max_retries=2,
    operation_name="model_call"
)

# Actions
await retry_with_timeout(
    lambda: page.click(selector),
    timeout=5.0,
    max_retries=3,
    operation_name="click"
)
```

### Phase 3: System-2 Prompts
For complex tasks:

```python
from ui_tars_patterns import create_system2_prompt

if is_complex_task(task):
    prompt = create_system2_prompt(task, current_state)
    # Forces THOUGHT → REFLECTION → ACTION format
```

### Phase 4: ActionParser
Parse UI-TARS coordinate outputs:

```python
from ui_tars_patterns import ActionParser

parser = ActionParser()
action = parser.parse("click(start_box=\"(500,300)\")", screen_context)
# Returns: {"action_type": "click", "x": 960, "y": 540}
```

---

## Key Files

| File | Purpose |
|------|---------|
| ui_tars_patterns.py | Core patterns (RetryConfig, ConversationContext, etc.) |
| ui_tars_integration.py | Integration helpers (UITarsEnhancer) |
| brain_enhanced_v2.py | Main brain with UI-TARS integration |
| vision_handler.py | Screenshot capture with UI-TARS retry |
| __init__.py | Exports UI-TARS utilities |

---

## API Reference

### UITarsEnhancer

```python
enhancer = UITarsEnhancer(page, config=RetryConfig())

# Enhanced screenshot (3x retry, 5s timeout)
b64 = await enhancer.enhanced_screenshot()

# Enhanced click (coordinate normalization + retry)
await enhancer.enhanced_click(500, 300, normalized=True)

# Normalize coordinates (0-1000 → pixels)
x, y = await enhancer.normalize_coordinates(500, 300)

# Get System-2 prompt
prompt = enhancer.get_system2_prompt(task, state)
```

### ConversationContext

```python
ctx = ConversationContext(max_screenshots=5)

# Add message with screenshot
ctx.add_message("user", "Step 1", screenshot_b64)

# Auto-prunes when over limit
# Keeps only last 5 screenshots

# Get messages for LLM
messages = ctx.get_messages()
```

### retry_with_timeout

```python
from ui_tars_patterns import retry_with_timeout

result = await retry_with_timeout(
    async_function,
    timeout=5.0,
    max_retries=3,
    operation_name="operation"
)
```

---

## Examples

### Example 1: Enhanced Screenshot
```python
# Automatic in vision_handler.py
async def take_screenshot(self):
    if self.brain.uitars:
        b64 = await self.brain.uitars.enhanced_screenshot()
        if b64:
            return base64.b64decode(b64)

    # Fallback
    return await self.brain.browser.page.screenshot()
```

### Example 2: Screenshot Context
```python
# Automatic in brain_enhanced_v2.py
self._uitars_context = ConversationContext(max_screenshots=5)

# Add screenshots
context.add_message("user", "Action result", screenshot_b64)
# Old screenshots auto-pruned when count > 5
```

### Example 3: Manual Retry
```python
from ui_tars_patterns import retry_with_timeout

# Retry click with timeout
async def click_with_retry(selector):
    await retry_with_timeout(
        lambda: page.click(selector),
        timeout=5.0,
        max_retries=3,
        operation_name="click"
    )
```

---

## Testing

### Unit Tests
```bash
cd /mnt/c/ev29/cli/engine/agent
python3 test_uitars_integration.py
```

### Integration Test
```bash
cd /mnt/c/ev29/cli
node bin/eversale.js "take a screenshot and describe it"
```

**Look for**: [UITARS] log messages

---

## Further Reading

- **Full audit**: UI_TARS_INTEGRATION_AUDIT.md
- **Completion summary**: UI_TARS_INTEGRATION_COMPLETE.md
- **Patterns source**: ui_tars_patterns.py (442 lines, fully documented)
- **Integration helpers**: ui_tars_integration.py (221 lines)
- **ByteDance paper**: https://arxiv.org/html/2501.12326v1

---

**Quick reference updated**: 2025-12-12
**For**: Eversale CLI Agent v2.9+
