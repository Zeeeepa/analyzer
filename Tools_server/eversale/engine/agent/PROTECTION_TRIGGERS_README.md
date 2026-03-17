# Protection Trigger Patterns

Natural language triggers for CAPTCHA handling, Cloudflare bypass, and stealth mode automation.

## Overview

Added P-series (Protection) capabilities to the intent detector and executor system. These allow users to invoke anti-detection features using natural language commands.

## Capabilities

### P1 - CAPTCHA Solver

**Purpose**: Detect and solve CAPTCHAs using local vision models (no paid APIs).

**Supported CAPTCHA types**:
- reCAPTCHA v2/v3
- hCaptcha
- Cloudflare Turnstile
- Image-based CAPTCHAs

**Natural language triggers**:
```
"handle captcha"
"solve the captcha"
"bypass recaptcha"
"captcha detected"
"hcaptcha verification"
"solve turnstile challenge"
```

**Implementation**:
- Uses `captcha_solver.py` with local vision models (moondream, llama3.2-vision)
- No external paid APIs required (2captcha, anti-captcha, etc.)
- Falls back to manual browser interaction if vision solving fails

**Example usage**:
```python
from agent.intent_detector import detect_intent
from agent.executors import ALL_EXECUTORS

intent = detect_intent("handle captcha")
# intent.capability = "P1"
# intent.action = "solve_captcha"

executor = ALL_EXECUTORS["P1"](browser=browser, context={})
result = await executor.execute({})
```

---

### P2 - Cloudflare Challenge Handler

**Purpose**: Bypass Cloudflare challenges or find alternative data sources.

**Natural language triggers**:
```
"bypass cloudflare"
"cloudflare is blocking"
"handle cloudflare challenge"
"site is blocked by cloudflare"
"solve cloudflare block"
```

**Implementation**:
- Uses `challenge_handler.py` with multi-strategy approach:
  1. Wait for JS challenge auto-completion (10-15s)
  2. Try stealth mode refresh
  3. Invoke CAPTCHA solver if challenge appears
  4. Suggest alternative data sources if blocked

**Alternative sources** (when blocked):
- Crunchbase blocked → LinkedIn, Tracxn, Google Search
- LinkedIn blocked → Google site search, company websites
- Google blocked → DuckDuckGo, Bing

**Example usage**:
```python
intent = detect_intent("bypass cloudflare")
# intent.capability = "P2"
# intent.action = "handle_cloudflare"

executor = ALL_EXECUTORS["P2"](browser=browser, context={})
result = await executor.execute({})
# result.data["bypassed"] = True/False
# result.data["alternatives"] = [list of alternative sources]
```

---

### P3 - Stealth Mode

**Purpose**: Enable enhanced anti-detection browser configuration.

**Natural language triggers**:
```
"use stealth mode"
"enable anti-detection"
"avoid bot detection"
"turn on stealth"
"anti-bot mode"
"stealth browsing"
```

**Implementation**:
- Uses `stealth_browser_config.py` with MCP-compatible settings:
  - Chrome launch args (`--disable-blink-features=AutomationControlled`)
  - Undetectable HTTP headers (Sec-CH-UA, User-Agent)
  - Fingerprint randomization (WebGL, Canvas)
  - TLS fingerprinting

**Features enabled**:
- Automation detection bypass
- Real Chrome fingerprint
- Persistent session support
- HTTP/2 and TLS consistency
- WebGL/Canvas randomization per session

**Example usage**:
```python
intent = detect_intent("use stealth mode")
# intent.capability = "P3"
# intent.action = "enable_stealth"

executor = ALL_EXECUTORS["P3"](browser=browser, context={})
result = await executor.execute({})
# result.data["stealth_enabled"] = True
# result.data["restart_required"] = True (for full effect)
```

---

## Integration with Workflow System

Protection triggers work seamlessly with existing workflows like FB Ads, LinkedIn, Reddit:

### Example: FB Ads with automatic Cloudflare bypass

```python
# User says: "Find 20 advertisers on FB Ads Library for SaaS"
intent = detect_intent(user_input)
# intent.capability = "D10" (FB Ads extraction)

executor = ALL_EXECUTORS["D10"](browser=browser, context={})
result = await executor.execute({"search_term": "SaaS", "max_ads": 20})

# If Cloudflare blocks during execution:
if result.status == ActionStatus.BLOCKED:
    # Automatically invoke P2 handler
    cf_executor = ALL_EXECUTORS["P2"](browser=browser, context={})
    cf_result = await cf_executor.execute({})

    if cf_result.data["bypassed"]:
        # Retry original task
        result = await executor.execute({"search_term": "SaaS", "max_ads": 20})
```

### Example: LinkedIn with stealth mode

```python
# Enable stealth mode first for LinkedIn scraping
stealth_executor = ALL_EXECUTORS["P3"](browser=browser, context={})
await stealth_executor.execute({})

# Then execute LinkedIn workflow
linkedin_executor = ALL_EXECUTORS["D4"](browser=browser, context={})
result = await linkedin_executor.execute({"name": "John Doe"})
```

---

## Testing

Run comprehensive tests:

```bash
python3 agent/test_protection_triggers.py
```

Expected output:
```
================================================================================
PROTECTION TRIGGER PATTERN TESTS
================================================================================

Testing intent detection:
--------------------------------------------------------------------------------
[PASS] handle captcha                           -> P1/solve_captcha
[PASS] solve the captcha                        -> P1/solve_captcha
[PASS] bypass cloudflare                        -> P2/handle_cloudflare
[PASS] use stealth mode                         -> P3/enable_stealth
...
Results: 12 passed, 0 failed

Testing executor registration:
--------------------------------------------------------------------------------
[PASS] P1: P1_CaptchaSolver - solve_captcha
[PASS] P2: P2_CloudflareHandler - handle_cloudflare
[PASS] P3: P3_StealthMode - enable_stealth
Results: 3 passed, 0 failed

ALL TESTS PASSED
================================================================================
```

---

## Files Modified/Created

### Modified:
1. `/mnt/c/ev29/cli/engine/agent/intent_detector.py`
   - Added P1, P2, P3 intent patterns

2. `/mnt/c/ev29/cli/engine/agent/executors/__init__.py`
   - Imported PROTECTION_EXECUTORS
   - Added to ALL_EXECUTORS registry
   - Exported in `__all__`

### Created:
1. `/mnt/c/ev29/cli/engine/agent/executors/protection.py`
   - P1_CaptchaSolver executor
   - P2_CloudflareHandler executor
   - P3_StealthMode executor

2. `/mnt/c/ev29/cli/engine/agent/test_protection_triggers.py`
   - Comprehensive test suite

3. `/mnt/c/ev29/cli/engine/agent/PROTECTION_TRIGGERS_README.md`
   - This documentation

---

## Architecture

### Trigger Pattern Flow

```
User Input: "handle captcha"
     ↓
intent_detector.py (regex pattern matching)
     ↓
DetectedIntent(capability="P1", action="solve_captcha")
     ↓
brain_enhanced_v2.py (executor routing)
     ↓
ALL_EXECUTORS["P1"] → P1_CaptchaSolver
     ↓
P1_CaptchaSolver._execute()
     ↓
captcha_solver.py (LocalCaptchaSolver + vision models)
     ↓
ActionResult(status=SUCCESS, data={...})
```

### Executor Registration

```python
# executors/__init__.py
from .protection import (
    P1_CaptchaSolver,
    P2_CloudflareHandler,
    P3_StealthMode,
    PROTECTION_EXECUTORS,
)

ALL_EXECUTORS = {
    **SDR_EXECUTORS,
    **ADMIN_EXECUTORS,
    **BUSINESS_EXECUTORS,
    **WORKFLOW_EXECUTORS,
    **PROTECTION_EXECUTORS,  # ← New
}
```

---

## Regression Testing

Ensure existing workflows still work:

```bash
# Test FB Ads trigger (D10)
python3 -c "from agent.intent_detector import detect_intent; print(detect_intent('fb ads for SaaS'))"

# Test LinkedIn trigger (D4)
python3 -c "from agent.intent_detector import detect_intent; print(detect_intent('find on linkedin'))"

# Test Reddit trigger
python3 -c "from agent.intent_detector import detect_intent; print(detect_intent('reddit commenters'))"
```

All existing triggers should continue to work unchanged.

---

## Future Enhancements

### Potential additions:
1. **P4**: 2FA Handler - SMS/authenticator app automation
2. **P5**: Proxy Rotation - Automatic IP rotation for rate limits
3. **P6**: Session Persistence - Save/restore browser sessions
4. **P7**: Human Behavior Simulation - Mouse movements, typing patterns

### Intelligent auto-detection:
- Automatically invoke P1 when CAPTCHA detected (no manual trigger needed)
- Automatically invoke P2 when Cloudflare blocks (no manual trigger needed)
- Automatically enable P3 for high-risk sites (LinkedIn, Facebook)

---

## Author

Claude (Anthropic)
Date: 2025-12-12

## Version

1.0.0 - Initial implementation
