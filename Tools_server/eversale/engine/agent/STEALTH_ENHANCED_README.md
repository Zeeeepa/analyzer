# Enhanced Anti-Bot Stealth System for Eversale

**Author:** Claude
**Date:** 2025-12-02
**Version:** 1.0.0

## Overview

The Enhanced Stealth System (`stealth_enhanced.py`) provides comprehensive anti-bot detection for Eversale based on 2025 research from playwright-extra, undetected-playwright, and anti-bot evasion experts.

This system goes beyond basic stealth measures to provide:
- Advanced fingerprint management (canvas, WebGL, audio, fonts)
- CDP detection mitigation
- Human-like behavioral mimicry
- Smart proxy rotation
- Detection response (CAPTCHA, blocks, honeypots)
- Site-specific profiles (LinkedIn, Facebook, Amazon, Google)

## Key Features

### 1. Fingerprint Management

**What it does:** Randomizes browser fingerprints to avoid tracking and detection.

**Techniques:**
- Canvas fingerprint noise injection (subtle pixel variations)
- WebGL vendor/renderer spoofing (realistic GPU signatures)
- Audio context fingerprint randomization
- Font enumeration control
- Screen resolution variation (common resolutions only)
- Language/locale matching to proxy location
- Timezone alignment with IP geolocation
- Plugin masking (realistic Chrome plugins)

**Example:**
```python
from agent.stealth_enhanced import FingerprintManager

# Create consistent fingerprint for session
fp_manager = FingerprintManager(seed="session-123")

# Access fingerprint details
fp = fp_manager.fingerprint
print(f"Screen: {fp['screen']['width']}x{fp['screen']['height']}")
print(f"WebGL: {fp['webgl']['vendor']}")
print(f"CPU cores: {fp['hardware']['cores']}")

# Get injection script
script = fp_manager.get_injection_script()
await page.add_init_script(script)
```

### 2. CDP Detection Mitigation

**What it does:** Hides Chrome DevTools Protocol (CDP) messages that indicate automation.

**Techniques:**
- Patch WebSocket to filter CDP messages
- Remove automation indicators from runtime
- Hide WebDriver flag (navigator.webdriver = undefined)
- Mask Playwright/Puppeteer signatures
- Suppress automation-related console logs

**Automatically included** in fingerprint injection script.

### 3. Behavioral Mimicry

**What it does:** Makes browser interactions look human-like.

**Techniques:**
- Bezier curve mouse movements (no teleporting)
- Natural typing with occasional typos (2% default)
- Variable scroll behavior (chunks with pauses)
- Click delay randomization (50-200ms variation)
- Reading time simulation (proportional to content)
- Tab focus patterns
- Random micro-movements while "thinking"
- Pauses between actions (1-5s)

**Example:**
```python
from agent.stealth_enhanced import BehaviorMimicry

# Natural mouse movement
await BehaviorMimicry.move_mouse_naturally(page, 500, 300)

# Natural typing with typos
await BehaviorMimicry.type_naturally(
    page,
    "#email",
    "user@example.com",
    typo_probability=0.02
)

# Natural scrolling
await BehaviorMimicry.scroll_naturally(page, "down", 500)

# Reading pause (proportional to content)
await BehaviorMimicry.reading_pause(content_length=2000)

# Random micro-movements
await BehaviorMimicry.random_micro_movements(page, count=3)
```

### 4. Proxy Management

**What it does:** Smart proxy rotation with health checking and sticky sessions.

**Features:**
- Multiple proxy types (residential, mobile, datacenter)
- Automatic rotation
- Sticky sessions for related requests (same domain = same proxy)
- Health checking (avoid failed proxies)
- Geo-targeting
- Automatic failover

**Example:**
```python
from agent.stealth_enhanced import ProxyManager

# Create proxy manager
proxy_manager = ProxyManager()

# Add proxies
proxy_manager.add_proxy(
    server="http://proxy1.example.com:8080",
    username="user1",
    password="pass1",
    proxy_type="residential"
)

proxy_manager.add_proxy(
    server="http://proxy2.example.com:8080",
    proxy_type="mobile"
)

# Get proxy with sticky session for domain
proxy = proxy_manager.get_proxy(domain="linkedin.com", sticky=True)

# Record success/failure
proxy_manager.record_success(proxy)
# or
proxy_manager.record_failure(proxy)

# Get stats
stats = proxy_manager.get_stats()
print(stats)
```

### 5. Detection Response

**What it does:** Detects and responds to bot detection measures.

**Features:**
- CAPTCHA detection (reCAPTCHA v2/v3, hCaptcha, Turnstile)
- Block page detection (access denied, suspicious activity)
- Bot score monitoring
- Honeypot link avoidance (hidden/off-screen elements)

**Example:**
```python
from agent.stealth_enhanced import DetectionResponse

# Detect CAPTCHA
captcha_info = await DetectionResponse.detect_captcha(page)
if captcha_info["has_captcha"]:
    print(f"CAPTCHA type: {captcha_info['captcha_type']}")
    print(f"Site key: {captcha_info['site_key']}")

# Detect block
is_blocked = await DetectionResponse.detect_block(page)
if is_blocked:
    print("Page is blocked!")

# Detect honeypots
honeypots = await DetectionResponse.detect_honeypots(page)
print(f"Found {len(honeypots)} honeypot elements to avoid")
```

### 6. Site-Specific Profiles

**What it does:** Automatically adjusts stealth behavior based on site.

**Profiles:**

| Site | Proxy Type | Navigation Delay | Behavior |
|------|------------|------------------|----------|
| **LinkedIn** | Mobile | 3-7s | Slow, cautious, scrolling, random movements |
| **Facebook** | Residential | 2-5s | Human-like, scrolling, reading pauses |
| **Amazon** | Residential | 3-8s | Very slow, warmup required, shopping mimicry |
| **Google** | Datacenter | 1-3s | Fast, no unnecessary actions, frequent rotation |
| **Default** | Datacenter | 2-4s | Balanced settings |

**Example:**
```python
from agent.stealth_enhanced import SiteProfile

# Get profile for URL
profile = SiteProfile.get_profile("https://linkedin.com/in/someone")
print(f"Profile: {profile['name']}")
print(f"Proxy type: {profile['proxy_type']}")
print(f"Delays: {profile['delays']}")
print(f"Behavior: {profile['behavior']}")
print(f"Requirements: {profile['requirements']}")
```

**Automatic in EnhancedStealthSession** - profile is detected from URL.

### 7. Enhanced Stealth Session

**What it does:** Complete stealth session manager integrating all components.

**Usage:**
```python
from agent.stealth_enhanced import get_stealth_session

async with get_stealth_session(page) as session:
    # Navigate with automatic profile detection
    await session.navigate("https://linkedin.com")

    # All interactions are now human-like
    await session.click(".sign-in-button")
    await session.type("#username", "user@example.com")
    await session.scroll("down")
    await session.wait_and_read(2000)
```

**Features:**
- Automatic fingerprint injection
- Site profile detection
- Natural behavioral patterns
- CAPTCHA handling (if enabled)
- Block detection
- Honeypot avoidance
- Mouse position tracking
- Action counting

## Integration with Existing Eversale Components

### With `playwright_direct.py`

```python
from agent.playwright_direct import PlaywrightClient
from agent.stealth_enhanced import enhance_existing_page, get_stealth_session

# Create client
client = PlaywrightClient(headless=False)
await client.connect()

# Enhance with stealth
await enhance_existing_page(client.page, fingerprint_seed="session-123")

# Use stealth session
async with get_stealth_session(client.page) as session:
    await session.navigate("https://example.com")
    # ... do work ...

await client.disconnect()
```

### With `stealth_utils.py`

```python
from agent.stealth_utils import get_stealth_args, get_random_user_agent
from agent.stealth_enhanced import FingerprintManager, create_stealth_context

# Combine existing stealth args with enhanced fingerprint
async with async_playwright() as p:
    launch_args = get_stealth_args()
    user_agent = get_random_user_agent()

    fp_manager = FingerprintManager()

    browser = await p.chromium.launch(headless=False, args=launch_args)
    context_options = fp_manager.get_context_options()
    context_options["user_agent"] = user_agent

    context = await browser.new_context(**context_options)
    await context.add_init_script(fp_manager.get_injection_script())

    # Now has BOTH old stealth utils AND new fingerprinting
```

### With `captcha_solver.py`

```python
from agent.captcha_solver import PageCaptchaHandler, ScrappyCaptchaBypasser
from agent.stealth_enhanced import get_stealth_session

async with get_stealth_session(page, enable_captcha_solver=True) as session:
    await session.navigate("https://protected-site.com")

    # CAPTCHA detection and handling is automatic
    # Uses ScrappyCaptchaBypasser first (free)
    # Falls back to manual solve if needed
```

### With `bs_detector.py`

```python
from agent.bs_detector import get_integrity_validator
from agent.stealth_enhanced import get_stealth_session

validator = get_integrity_validator()

async with get_stealth_session(page) as session:
    await session.navigate("https://example.com")

    # Extract data
    data = await page.evaluate("() => { return {...}; }")

    # Validate (no hallucinations)
    page_content = await page.content()
    is_valid, issues, hint = validator.verify_output(
        claimed_output=str(data),
        actual_page_content=page_content,
        task_type="extraction"
    )
```

## Quick Start

### Basic Usage

```python
from playwright.async_api import async_playwright
from agent.stealth_enhanced import create_stealth_context, get_stealth_session

async def main():
    async with async_playwright() as p:
        # Create stealth context
        context, fp_manager = await create_stealth_context(
            p,
            headless=False,
            fingerprint_seed="my-session"
        )

        page = await context.new_page()

        # Use stealth session
        async with get_stealth_session(page) as session:
            await session.navigate("https://example.com")
            await session.click(".button")
            await session.type("#input", "text")

        await context.close()

asyncio.run(main())
```

### Production Pattern

```python
from agent.stealth_enhanced import (
    ProxyManager,
    create_stealth_context,
    get_stealth_session
)
from agent.bs_detector import get_integrity_validator

async def scrape_with_full_stealth(url: str):
    # Setup
    proxy_manager = ProxyManager()
    proxy_manager.add_proxy("http://proxy:8080", proxy_type="residential")
    validator = get_integrity_validator()

    async with async_playwright() as p:
        # Get proxy
        proxy = proxy_manager.get_proxy(domain="target.com", sticky=True)

        # Create stealth context
        context, fp_manager = await create_stealth_context(
            p,
            headless=False,
            proxy=proxy,
            fingerprint_seed="production-session"
        )

        page = await context.new_page()

        try:
            async with get_stealth_session(page, proxy_manager=proxy_manager) as session:
                # Navigate
                await session.navigate(url)

                # Wait and scroll
                await session.wait_and_read(2000)
                await session.scroll("down")

                # Extract data
                data = await page.evaluate("() => { return {...}; }")

                # Validate
                page_content = await page.content()
                is_valid, issues, hint = validator.verify_output(
                    str(data),
                    page_content,
                    task_type="extraction"
                )

                if is_valid:
                    proxy_manager.record_success(proxy)
                    return data
                else:
                    logger.warning(f"Validation failed: {issues}")

        except Exception as e:
            proxy_manager.record_failure(proxy)
            raise

        finally:
            await context.close()
```

## Configuration

### Fingerprint Seeds

Use consistent seeds for reproducible fingerprints within a session:

```python
fp_manager = FingerprintManager(seed="my-session-123")
```

Without seed, fingerprint is randomized each time.

### Site Profiles

Customize profiles by modifying `SiteProfile.PROFILES`:

```python
from agent.stealth_enhanced import SiteProfile

# Add custom profile
SiteProfile.PROFILES["mysite"] = {
    "name": "MySite",
    "proxy_type": "residential",
    "delays": {
        "navigation": (2, 5),
        "action": (0.5, 2),
        "typing": (0.1, 0.2),
    },
    "behavior": {
        "scroll_before_extract": True,
        "random_movements": True,
        "reading_pauses": True,
    },
    "requirements": {}
}
```

### Proxy Types

- **residential:** Highest quality, residential IPs (best for social media)
- **mobile:** Mobile IPs (good for LinkedIn, Facebook)
- **datacenter:** Datacenter IPs (faster, cheaper, less trusted)

### CAPTCHA Handling

Enable/disable CAPTCHA solver in session:

```python
async with get_stealth_session(page, enable_captcha_solver=True) as session:
    # CAPTCHA handling is automatic
    pass
```

Set CAPTCHA API key (for paid solving):

```bash
export CAPTCHA_API_KEY="your-2captcha-api-key"
```

If no API key, uses free ScrappyCaptchaBypasser (human-like + manual fallback).

## Testing

Test individual components:

```python
# Test fingerprint
from agent.stealth_enhanced import FingerprintManager

fp_manager = FingerprintManager()
script = fp_manager.get_injection_script()
print(script[:500])

# Test behavioral mimicry
from agent.stealth_enhanced import BehaviorMimicry

async with async_playwright() as p:
    browser = await p.chromium.launch(headless=False)
    page = await browser.new_page()
    await page.goto("https://example.com")

    await BehaviorMimicry.move_mouse_naturally(page, 500, 300)
    await BehaviorMimicry.scroll_naturally(page, "down")

    await browser.close()

# Test proxy manager
from agent.stealth_enhanced import ProxyManager

proxy_manager = ProxyManager()
proxy_manager.add_proxy("http://proxy:8080")
proxy = proxy_manager.get_proxy()
print(proxy)

# Test detection
from agent.stealth_enhanced import DetectionResponse

async with async_playwright() as p:
    browser = await p.chromium.launch(headless=False)
    page = await browser.new_page()
    await page.goto("https://google.com/recaptcha/api2/demo")

    captcha_info = await DetectionResponse.detect_captcha(page)
    print(captcha_info)

    await browser.close()
```

Run integration examples:

```bash
cd /mnt/c/ev29/agent
python3 stealth_enhanced_integration.py
```

## Performance

Enhanced stealth adds minimal overhead:

- Fingerprint injection: <100ms (one-time per page)
- Behavioral delays: Configurable (fast mode available)
- Proxy overhead: Network-dependent
- Detection checks: <50ms

For speed-critical operations, use fast profile or disable unnecessary behaviors.

## Limitations

### Sites with Advanced Anti-Bot (Still Challenging)

- **Cloudflare Turnstile:** Requires manual solve or paid solver
- **PerimeterX:** Very aggressive, may require residential proxies + warmup
- **DataDome:** Advanced behavioral analysis, requires slow/careful interaction

### Recommendations for Difficult Sites

1. Use residential/mobile proxies
2. Enable all behavioral mimicry
3. Warm up session (visit homepage first)
4. Use logged-in browser profile when possible
5. Add long delays between actions
6. Rotate proxies frequently

### When Stealth May Not Help

- Sites that require verified accounts (email verification)
- Sites that block entire IP ranges
- Sites with phone verification
- Sites that use device attestation (Android/iOS only)

## Troubleshooting

### Still Getting Detected

1. Check fingerprint consistency (use seed)
2. Verify proxy quality (residential > datacenter)
3. Increase delays (use slow profile)
4. Check for honeypots (avoid hidden links)
5. Warm up session (visit multiple pages)
6. Use logged-in browser profile

### CAPTCHA Not Solving

1. Check CAPTCHA_API_KEY is set
2. Verify CAPTCHA service balance
3. Try manual solve (ScrappyCaptchaBypasser waits for you)
4. Check CAPTCHA type is supported

### Proxy Issues

1. Check proxy is alive (ping server)
2. Verify credentials are correct
3. Check proxy health stats
4. Try different proxy type

## API Reference

See inline documentation in:
- `/mnt/c/ev29/agent/stealth_enhanced.py` - Main implementation
- `/mnt/c/ev29/agent/stealth_enhanced_integration.py` - Usage examples

Key classes:
- `FingerprintManager` - Fingerprint generation and injection
- `BehaviorMimicry` - Human-like behavioral patterns
- `ProxyManager` - Smart proxy rotation
- `DetectionResponse` - Bot detection handling
- `SiteProfile` - Site-specific configurations
- `EnhancedStealthSession` - Complete stealth session manager

Key functions:
- `create_stealth_context()` - Create stealth browser context
- `get_stealth_session()` - Get stealth session for page
- `enhance_existing_page()` - Add stealth to existing page

## Future Enhancements

Potential improvements:

1. **Browser Profiles:** Save/load full browser profiles with cookies
2. **ML-Based Timing:** Learn optimal delays from successful sessions
3. **Advanced CAPTCHA:** Integrate more CAPTCHA solvers (CapSolver, NopeCHA)
4. **Bot Score API:** Real-time bot score monitoring (when available)
5. **Session Recording:** Record successful sessions for replay
6. **A/B Testing:** Test different stealth strategies automatically

## Contributing

To add new features:

1. Add to appropriate class in `stealth_enhanced.py`
2. Add example to `stealth_enhanced_integration.py`
3. Update this README
4. Test with real sites

## License

Part of Eversale project.

## Support

For issues or questions:
1. Check existing Eversale documentation
2. Review integration examples
3. Test with simple sites first (example.com)
4. Gradually increase complexity

---

**Remember:** Stealth is not about being undetectable - it's about being indistinguishable from real users. The key is natural, human-like behavior, not just technical evasion.

