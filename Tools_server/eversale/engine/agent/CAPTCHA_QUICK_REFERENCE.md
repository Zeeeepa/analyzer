# CAPTCHA & 2FA - Quick Reference Card (Free Methods)

## Import Statements

```python
from captcha_solver import (
    PageCaptchaHandler,
    AuthChallengeManager,
    ChallengeType,
)
from login_manager import LoginManager
```

## Common Use Cases

### 1. Detect Any Challenge (Quickest)
```python
handler = PageCaptchaHandler(page)
detection = await handler.detect_captcha()

if detection.detected:
    print(f"Found: {detection.challenge_type.value}")
```

### 2. Free CAPTCHA Solving Flow (Recommended)
```python
handler = PageCaptchaHandler(page)
detection = await handler.detect_captcha()

if detection.detected:
    # Step 1: Try scrappy bypass techniques
    success = await handler.scrappy.try_checkbox_click()
    if not success:
        success = await handler.scrappy.try_accessibility_bypass()

    # Step 2: Fall back to manual (popup for human)
    if not success:
        await handler.notify_user(detection)
        success = await handler.wait_for_user_resolution(detection, timeout=300)
```

### 3. Full Auth Flow (Recommended)
```python
auth_manager = AuthChallengeManager(page)
success = await auth_manager.check_and_handle_challenges(manual_timeout=300)
```

### 4. Login with Challenges
```python
login_manager = LoginManager()
success = await login_manager.login_with_challenge_handling(
    service_id="gmail",
    page=page,
    timeout=300
)
```

## Free CAPTCHA Solving Methods

### Method 1: Scrappy Bypass Techniques
- **Checkbox clicking** - For reCAPTCHA v2 checkbox
- **Accessibility bypass** - Try audio CAPTCHA option
- **Human-like behavior** - Mouse movements, delays to avoid detection
- **Cookie persistence** - Uses your logged-in browser sessions

### Method 2: Manual Solving
- **Browser popup** - Shows browser window for human to solve
- **Auto-resume** - Detects when solved and continues automatically
- **Console notifications** - Clear instructions in terminal
- **Configurable timeout** - Default 5 minutes, adjustable

### Method 3: Vision-Based Solving (AVAILABLE NOW)
- **Local LLM vision** - Uses moondream, llava:7b, llama3.2-vision
- **Multi-model fallback** - Tries 3 models in sequence
- **OCR error correction** - Fixes common mistakes (0↔O, 1↔l↔I)
- **Confidence scoring** - 0.0-1.0 score for reliability
- **Type-specific prompts** - Optimized for text, math, image selection
- **Image preprocessing** - Contrast/sharpness enhancement on retry
- **70-85% success rate** - vs 40-50% before enhancements

## Supported Challenge Types

| Type | Detection Confidence | Free Method Available |
|------|---------------------|----------------------|
| reCAPTCHA v2 | 95% | ✅ Scrappy + Manual |
| reCAPTCHA v3 | 90% | ✅ Manual only |
| hCaptcha | 95% | ✅ Scrappy + Manual |
| Cloudflare Turnstile | 95% | ✅ Manual only |
| Image CAPTCHA (Text) | 70% | ✅ Vision (70-85%) + Manual |
| Image CAPTCHA (Math) | 70% | ✅ Vision (70-85%) + Manual |
| SMS 2FA | 90% | ✅ Manual only |
| Authenticator 2FA | 90% | ✅ Manual only |
| Email 2FA | 90% | ✅ Manual only |

## Timeouts

```python
# Manual resolution timeout
await handler.wait_for_user_resolution(
    challenge,
    timeout=300  # 5 minutes (default)
)

# Full auth flow timeout
await auth_manager.check_and_handle_challenges(
    manual_timeout=300  # 5 minutes (default)
)
```

## Webhook Payload (Optional)

```json
{
  "type": "auth_challenge",
  "challenge_type": "recaptcha_v2",
  "url": "https://example.com",
  "timestamp": 1234567890.123,
  "metadata": {
    "site_key": "...",
    "confidence": 0.95
  }
}
```

## Custom Callback

```python
async def my_callback(challenge):
    print(f"Challenge: {challenge.challenge_type.value}")
    # Your custom logic here

handler = PageCaptchaHandler(page)
handler.set_notification_callback(my_callback)
```

## Error Handling

```python
try:
    success = await auth_manager.check_and_handle_challenges()
    if not success:
        logger.warning("Challenge not resolved within timeout")
except Exception as e:
    logger.error(f"Error: {e}")
```

## Testing

```python
# Test URLs
RECAPTCHA_V2 = "https://www.google.com/recaptcha/api2/demo"
HCAPTCHA = "https://accounts.hcaptcha.com/demo"

# Basic test
handler = PageCaptchaHandler(page)
await page.goto(RECAPTCHA_V2)
detection = await handler.detect_captcha()
assert detection.detected
assert detection.challenge_type == ChallengeType.RECAPTCHA_V2
```

## Common Patterns

### Pattern 1: Free-First Approach (Recommended)
```python
handler = PageCaptchaHandler(page)

# Try free methods first
if await handler.scrappy.try_checkbox_click():
    print("Solved via checkbox!")
elif await handler.scrappy.try_accessibility_bypass():
    print("Solved via accessibility!")
else:
    # Try vision-based solving for image CAPTCHAs
    detection = await handler.detect_captcha()
    if detection.challenge_type == ChallengeType.IMAGE_CAPTCHA:
        solver = LocalCaptchaSolver(vision_model="moondream")
        result = await solver.solve_image_with_vision(page)
        if result and result['confidence'] >= 0.7:
            await submit_captcha(result['answer'])
            print(f"Solved via vision! ({result['confidence']:.2%} confidence)")
        else:
            # Fall back to manual
            await handler.notify_user(detection)
            await handler.wait_for_user_resolution(detection)
    else:
        # Fall back to manual for other types
        await handler.notify_user(detection)
        await handler.wait_for_user_resolution(detection)
```

### Pattern 2: Check Multiple Challenge Types
```python
challenges = await handler.detect_all_challenges()

for challenge in challenges:
    if challenge.challenge_type == ChallengeType.RECAPTCHA_V2:
        # Try scrappy bypass
        await handler.scrappy.try_checkbox_click()
    else:
        # Use manual for 2FA or other types
        await handler.wait_for_user_resolution(challenge)
```

### Pattern 3: Login Flow with Retry
```python
login_manager = LoginManager()

for attempt in range(3):
    success = await login_manager.login_with_challenge_handling(
        service_id="gmail",
        page=page
    )
    if success:
        break
    logger.warning(f"Login attempt {attempt+1} failed, retrying...")
```

## Tips

1. **Use Persistent Browser Sessions**
   - Solve CAPTCHA once, cookies persist across tasks
   - Uses the isolated Eversale profile (~/.eversale/browser-profile) so your normal Chrome stays untouched

2. **Set Reasonable Timeouts**
   - 300s (5min) is good for most cases
   - 600s (10min) for SMS 2FA (may be delayed)

3. **Monitor Logs**
   - All challenges logged to console
   - Check logs/agent.log for details

4. **Free Methods Only**
   - No API keys required
   - No paid services needed
   - 100% free CAPTCHA solving

5. **Webhook for Remote Agents**
   - Use webhooks for headless/remote deployments
   - Get notified immediately when action needed

## Troubleshooting

| Issue | Solution |
|-------|----------|
| CAPTCHA not detected | Wait for page load, increase delays |
| Scrappy bypass fails | Fall back to manual solving |
| 2FA not detected | Add custom patterns to TwoFactorDetector |
| Timeout too short | Increase timeout parameter |
| Browser doesn't show | Check headless mode is disabled |

## Complete Example

```python
from playwright.async_api import async_playwright
from captcha_solver import AuthChallengeManager
from login_manager import LoginManager

async def login_to_gmail():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Method 1: Manual auth handling
        await page.goto("https://mail.google.com")
        auth_manager = AuthChallengeManager(page)
        success = await auth_manager.check_and_handle_challenges()

        # Method 2: Using LoginManager (recommended)
        login_manager = LoginManager()
        success = await login_manager.login_with_challenge_handling(
            service_id="gmail",
            page=page
        )

        if success:
            print("Logged in successfully!")
            # Continue with your task...

        await browser.close()
```

## Vision-Based CAPTCHA Solving (NEW)

### Quick Start

```python
from captcha_solver import LocalCaptchaSolver

# Initialize
solver = LocalCaptchaSolver(vision_model="moondream")

# Auto-detect type and solve
captcha_type = await solver.detect_captcha_type(page)
result = await solver.solve_image_with_vision(page, captcha_type=captcha_type)

if result:
    print(f"Answer: {result['answer']}")
    print(f"Confidence: {result['confidence']:.2%}")
    print(f"Model: {result['model']}")

    # Submit if confident
    if result['confidence'] >= 0.7:
        await submit_captcha(result['answer'])
```

### CAPTCHA Types

| Type | Example | Parameter |
|------|---------|-----------|
| Text | Distorted "Abc123" | `captcha_type="text"` |
| Math | "2 + 3 = ?" | `captcha_type="math"` |
| Image Selection | "Select all traffic lights" | `captcha_type="image_selection"` |

### Models Available

| Model | Speed | Accuracy | Fallback Order |
|-------|-------|----------|----------------|
| moondream | Fast | Good | 1st (default) |
| llava:7b | Medium | Better | 2nd |
| llama3.2-vision | Fast | OK | 3rd |

### Installation

```bash
# Install dependencies
pip install ollama pillow

# Download vision models
ollama pull moondream
ollama pull llava:7b
ollama pull llama3.2-vision
```

### Confidence Thresholds

- `>= 0.9` - Very high, submit immediately
- `>= 0.7` - High, recommended minimum
- `>= 0.5` - Medium, consider manual verify
- `< 0.5` - Low, try next model or manual

### Return Format

```python
{
    "answer": str,        # Solution (e.g., "Abc123")
    "confidence": float,  # Score 0.0-1.0
    "model": str         # Model used
}
```

## Documentation

- **Full Guide**: `/mnt/c/ev29/agent/CAPTCHA_2FA_README.md`
- **Vision Enhancements**: `/mnt/c/ev29/agent/CAPTCHA_VISION_IMPROVEMENTS.md`
- **Vision Examples**: `/mnt/c/ev29/agent/captcha_solver_example.py`
- **General Examples**: `/mnt/c/ev29/agent/captcha_usage_example.py`

