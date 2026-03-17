# Enhanced Stealth - Quick Reference

**TL;DR:** Copy-paste ready code snippets for common stealth scenarios.

---

## 1. Basic Stealth Session (Most Common)

```python
from playwright.async_api import async_playwright
from agent.stealth_enhanced import create_stealth_context, get_stealth_session

async with async_playwright() as p:
    # Create stealth context
    context, fp_manager = await create_stealth_context(p, headless=False)
    page = await context.new_page()

    # Use stealth session
    async with get_stealth_session(page) as session:
        await session.navigate("https://example.com")
        await session.scroll("down")
        await session.click(".button")
        await session.type("#input", "text")

    await context.close()
```

---

## 2. Add Stealth to Existing PlaywrightClient

```python
from agent.playwright_direct import PlaywrightClient
from agent.stealth_enhanced import enhance_existing_page, get_stealth_session

client = PlaywrightClient(headless=False)
await client.connect()

# Add stealth
await enhance_existing_page(client.page)

# Use it
async with get_stealth_session(client.page) as session:
    await session.navigate("https://example.com")

await client.disconnect()
```

---

## 3. Use Proxies with Stealth

```python
from agent.stealth_enhanced import ProxyManager, create_stealth_context, get_stealth_session

# Setup proxies
proxy_manager = ProxyManager()
proxy_manager.add_proxy(
    server="http://proxy.example.com:8080",
    username="user",
    password="pass",
    proxy_type="residential"
)

# Get proxy
proxy = proxy_manager.get_proxy(domain="target.com", sticky=True)

# Create context with proxy
async with async_playwright() as p:
    context, fp_manager = await create_stealth_context(p, proxy=proxy)
    page = await context.new_page()

    async with get_stealth_session(page, proxy_manager=proxy_manager) as session:
        try:
            await session.navigate("https://target.com")
            # ... work ...
            proxy_manager.record_success(proxy)
        except:
            proxy_manager.record_failure(proxy)

    await context.close()
```

---

## 4. Human-Like Interactions (Manual Control)

```python
from agent.stealth_enhanced import BehaviorMimicry

# Natural mouse movement
await BehaviorMimicry.move_mouse_naturally(page, 500, 300)

# Natural typing (with typos)
await BehaviorMimicry.type_naturally(page, "#email", "user@example.com")

# Natural scrolling
await BehaviorMimicry.scroll_naturally(page, "down", 500)

# Reading pause
await BehaviorMimicry.reading_pause(content_length=2000)

# Random movements (fidgeting)
await BehaviorMimicry.random_micro_movements(page, count=3)
```

---

## 5. Check for Bot Detection

```python
from agent.stealth_enhanced import DetectionResponse

# Check for CAPTCHA
captcha_info = await DetectionResponse.detect_captcha(page)
if captcha_info["has_captcha"]:
    print(f"CAPTCHA: {captcha_info['captcha_type']}")

# Check for block
is_blocked = await DetectionResponse.detect_block(page)
if is_blocked:
    print("Access denied!")

# Find honeypots to avoid
honeypots = await DetectionResponse.detect_honeypots(page)
print(f"Avoid: {honeypots}")
```

---

## 6. Site-Specific Profiles (Auto)

```python
async with get_stealth_session(page) as session:
    # LinkedIn: slow, mobile proxy, human-like
    await session.navigate("https://linkedin.com")

    # Amazon: very slow, residential proxy
    await session.navigate("https://amazon.com")

    # Google: fast, datacenter OK
    await session.navigate("https://google.com")

    # Profile is automatically detected from URL
```

---

## 7. Custom Fingerprint (Reproducible)

```python
from agent.stealth_enhanced import FingerprintManager

# Same seed = same fingerprint
fp_manager = FingerprintManager(seed="my-session-123")

# Check what fingerprint looks like
fp = fp_manager.fingerprint
print(f"Screen: {fp['screen']['width']}x{fp['screen']['height']}")
print(f"CPU: {fp['hardware']['cores']} cores")
print(f"Timezone: {fp['locale']['timezone']}")

# Use it
context_options = fp_manager.get_context_options()
await context.add_init_script(fp_manager.get_injection_script())
```

---

## 8. Handle CAPTCHAs

```python
from agent.captcha_solver import ScrappyCaptchaBypasser

async with get_stealth_session(page, enable_captcha_solver=True) as session:
    await session.navigate("https://protected-site.com")

    # CAPTCHA detected automatically
    # 1. Tries human-like behavior (click checkbox)
    # 2. Tries accessibility options
    # 3. Waits for you to solve manually (30s timeout)

    # Or manually:
    bypasser = ScrappyCaptchaBypasser(page)
    success = await bypasser.bypass(manual_fallback=True, manual_timeout=60)
```

---

## 9. Production Pattern (All Features)

```python
from agent.stealth_enhanced import (
    ProxyManager, create_stealth_context, get_stealth_session
)
from agent.bs_detector import get_integrity_validator

# Setup
proxy_manager = ProxyManager()
proxy_manager.add_proxy("http://proxy:8080", proxy_type="residential")
validator = get_integrity_validator()

async with async_playwright() as p:
    proxy = proxy_manager.get_proxy("target.com", sticky=True)
    context, fp = await create_stealth_context(p, proxy=proxy)
    page = await context.new_page()

    try:
        async with get_stealth_session(page, proxy_manager=proxy_manager) as session:
            await session.navigate("https://target.com")
            await session.wait_and_read(2000)
            await session.scroll("down")

            # Extract
            data = await page.evaluate("() => { return {...}; }")

            # Validate (no hallucinations)
            is_valid, issues, hint = validator.verify_output(
                str(data),
                await page.content(),
                task_type="extraction"
            )

            if is_valid:
                proxy_manager.record_success(proxy)
                return data
            else:
                logger.warning(f"Invalid: {issues} - {hint}")

    except Exception as e:
        proxy_manager.record_failure(proxy)
        raise
    finally:
        await context.close()
```

---

## 10. Test Fingerprint (Browser Leak Sites)

```python
async with async_playwright() as p:
    context, fp_manager = await create_stealth_context(p, headless=False)
    page = await context.new_page()

    # Test sites
    await page.goto("https://browserleaks.com/canvas")
    await asyncio.sleep(5)

    await page.goto("https://abrahamjuliot.github.io/creepjs/")
    await asyncio.sleep(10)

    await page.goto("https://bot.sannysoft.com/")
    await asyncio.sleep(5)

    # Check results visually
    await context.close()
```

---

## Common Patterns

### Pattern: LinkedIn Scraping

```python
async with get_stealth_session(page) as session:
    # LinkedIn profile uses:
    # - Mobile proxy
    # - Slow delays (3-7s navigation)
    # - Human-like scrolling
    # - Reading pauses

    await session.navigate("https://linkedin.com/in/someone")
    await session.wait_and_read(2000)
    await session.scroll("down")

    # Extract profile data
    data = await page.evaluate("() => { ... }")
```

### Pattern: Facebook Ads Library

```python
async with get_stealth_session(page) as session:
    # Facebook profile uses:
    # - Residential proxy
    # - Human-like behavior
    # - Random movements

    await session.navigate("https://facebook.com/ads/library")
    await session.type("#search", "dog food")
    await session.click("button[type='submit']")
    await session.wait_and_read(3000)
```

### Pattern: Amazon Product Research

```python
async with get_stealth_session(page) as session:
    # Amazon profile uses:
    # - Residential proxy
    # - Very slow delays (3-8s)
    # - Session warmup

    await session.navigate("https://amazon.com")  # Warmup
    await session.wait_and_read(2000)

    await session.navigate("https://amazon.com/product/B0...")
    await session.scroll("down")
    await session.wait_and_read(3000)
```

### Pattern: Google Search

```python
async with get_stealth_session(page) as session:
    # Google profile uses:
    # - Datacenter proxy OK
    # - Fast delays (1-3s)
    # - No unnecessary actions

    await session.navigate("https://google.com/search?q=test")
    # Fast extraction
```

---

## Troubleshooting Quick Fixes

### Still Getting Detected

```python
# Slower delays
SiteProfile.PROFILES["default"]["delays"]["navigation"] = (5, 10)

# More human behavior
SiteProfile.PROFILES["default"]["behavior"]["random_movements"] = True
SiteProfile.PROFILES["default"]["behavior"]["reading_pauses"] = True

# Better proxy
proxy_manager.add_proxy("...", proxy_type="residential")
```

### CAPTCHA Issues

```bash
# Set API key for paid solving
export CAPTCHA_API_KEY="your-2captcha-key"
```

```python
# Or use manual solve (free)
bypasser = ScrappyCaptchaBypasser(page)
await bypasser.bypass(manual_fallback=True, manual_timeout=120)
```

### Proxy Issues

```python
# Check proxy health
stats = proxy_manager.get_stats()
print(stats)

# Reset failed proxy
proxy_manager.record_success(proxy)  # Force reset
```

---

## Environment Variables

```bash
# CAPTCHA solving (optional)
export CAPTCHA_API_KEY="your-2captcha-api-key"
```

---

## Import Reference

```python
# Main classes
from agent.stealth_enhanced import (
    FingerprintManager,       # Fingerprint generation
    BehaviorMimicry,          # Human-like behavior
    ProxyManager,             # Proxy rotation
    DetectionResponse,        # Bot detection
    SiteProfile,              # Site-specific configs
    EnhancedStealthSession,   # Complete session
)

# Convenience functions
from agent.stealth_enhanced import (
    create_stealth_context,   # Create stealth browser
    get_stealth_session,      # Get session for page
    enhance_existing_page,    # Add stealth to existing page
)

# Integration
from agent.playwright_direct import PlaywrightClient
from agent.captcha_solver import PageCaptchaHandler, ScrappyCaptchaBypasser
from agent.bs_detector import get_integrity_validator
```

---

## Files

- `/mnt/c/ev29/agent/stealth_enhanced.py` - Main implementation (1555 lines)
- `/mnt/c/ev29/agent/stealth_enhanced_integration.py` - Integration examples (493 lines)
- `/mnt/c/ev29/agent/STEALTH_ENHANCED_README.md` - Full documentation (643 lines)
- `/mnt/c/ev29/agent/STEALTH_QUICK_REFERENCE.md` - This file

---

**Remember:** Start simple, add complexity as needed. Most sites only need basic stealth.

