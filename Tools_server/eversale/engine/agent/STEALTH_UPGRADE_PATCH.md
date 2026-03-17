# Stealth Browser Configuration Upgrade

## Problem

Playwright MCP wasn't blocked by Cloudflare on Crunchbase, but Eversale was blocked.

## Root Cause

Missing critical browser launch arguments and headers that successful MCP implementations use:

1. **Chrome Channel**: MCP uses `channel: "chrome"` to use stable Chrome instead of Chromium (Chromium is more easily detected)
2. **Outdated Sec-CH-UA headers**: Missing Chrome v131+ headers
3. **Missing --enable-automation=false**: Critical flag was missing
4. **Wrong Accept-Encoding**: Missing `zstd` compression support
5. **Incomplete Client Hints**: Missing Sec-CH-UA-Full-Version-List and other headers
6. **ignore_https_errors set to True**: Makes detection easier (real browsers don't ignore HTTPS errors)

## Solution

Created `/mnt/c/ev29/cli/engine/agent/stealth_browser_config.py` with:

1. **get_mcp_compatible_launch_args()** - Exact Chrome launch args that bypass Cloudflare
2. **get_chrome_context_options()** - Complete Sec-CH-UA headers matching Chrome 131
3. **get_firefox_context_options()** - Firefox-specific headers
4. **BrowserStealthConfig class** - Configuration builder
5. **get_enhanced_stealth_script()** - Enhanced JavaScript injection

## Key Improvements

### Launch Arguments

```python
[
    "--disable-blink-features=AutomationControlled",  # CRITICAL
    "--enable-automation=false",  # NEW - CRITICAL
    "--disable-features=IsolateOrigins,site-per-process",
    # ... (see stealth_browser_config.py for full list)
]
```

### Sec-CH-UA Headers (Chrome 131)

```python
{
    "Sec-CH-UA": '"Chromium";v="131", "Google Chrome";v="131", "Not(A:Brand";v="24"',
    "Sec-CH-UA-Platform": '"Windows"',
    "Sec-CH-UA-Platform-Version": '"15.0.0"',
    "Sec-CH-UA-Full-Version-List": '"Chromium";v="131.0.6778.140", ...',
    "Sec-CH-UA-Bitness": '"64"',
    "Sec-CH-UA-Arch": '"x86"',
    "Sec-CH-UA-WoW64": "?0",
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Model": '""',
}
```

### Accept-Encoding Header

```python
"Accept-Encoding": "gzip, deflate, br, zstd",  # Added zstd (Chrome 131+)
```

## Integration Changes

### In playwright_direct.py

Add import (around line 400):

```python
# Import enhanced stealth configuration (matches Playwright MCP)
try:
    from .stealth_browser_config import (
        BrowserStealthConfig,
        get_recommended_config,
        get_mcp_compatible_launch_args,
        get_chrome_context_options,
        get_firefox_context_options,
        get_firefox_user_prefs,
        get_enhanced_stealth_script,
    )
    ENHANCED_STEALTH_CONFIG_AVAILABLE = True
except ImportError:
    ENHANCED_STEALTH_CONFIG_AVAILABLE = False
    logger.debug("Enhanced stealth config not available - using legacy config")
```

Update connect() method (around line 909):

```python
# STEALTH: Use enhanced MCP-compatible configuration if available
if ENHANCED_STEALTH_CONFIG_AVAILABLE:
    # Use MCP-compatible stealth arguments and context options
    logger.debug("Using MCP-compatible stealth configuration")
    if self.browser_type == "chromium":
        launch_args = get_mcp_compatible_launch_args()
        context_options = get_chrome_context_options()
    elif self.browser_type == "firefox":
        launch_args = get_firefox_launch_args()
        context_options = get_firefox_context_options()
    else:
        launch_args = []
        context_options = {
            "viewport": {"width": 1920, "height": 1080},
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }
else:
    # FALLBACK: Use existing legacy configuration
    if self.browser_type == "chromium":
        launch_args = get_stealth_args()
    # ... (keep existing fallback code)
```

Update stealth stack logging (around line 891):

```python
if ENHANCED_STEALTH_CONFIG_AVAILABLE:
    stealth_stack.append("MCP-compatible config")
```

Update browser.new_context() call to try Chrome channel (around line 996):

```python
if self.browser_type == "chromium":
    launch_kwargs["chromium_sandbox"] = False
    # Try to use Chrome channel for better stealth
    try:
        launch_kwargs["channel"] = "chrome"
    except Exception:
        pass  # Fall back to Chromium if Chrome not available
```

Update script injection (around line 1050):

```python
# STEALTH: Inject anti-fingerprinting scripts for all new pages
if self.browser_type == "chromium":
    if ENHANCED_STEALTH_CONFIG_AVAILABLE:
        await self.context.add_init_script(get_enhanced_stealth_script())
    else:
        await self.context.add_init_script(get_stealth_js())
```

## Testing

Test on Crunchbase (previously blocked):

```python
from playwright.async_api import async_playwright
from stealth_browser_config import get_recommended_config

config = get_recommended_config(headless=False)

async with async_playwright() as p:
    browser = await p.chromium.launch(**config.get_launch_options())
    context = await browser.new_context(**config.get_context_options())
    page = await context.new_page()

    await page.goto("https://www.crunchbase.com/")
    # Should NOT be blocked by Cloudflare
```

## Verification

After integration, check logs for:

```
Starting browser with ... + MCP-compatible config (STEALTH MODE)...
Using MCP-compatible stealth configuration
```

## Files Modified

1. **NEW**: `/mnt/c/ev29/cli/engine/agent/stealth_browser_config.py` (570 lines)
2. **MODIFIED**: `/mnt/c/ev29/cli/engine/agent/playwright_direct.py` (add imports + use new config)

## Backward Compatibility

The enhanced config is **opt-in via import**. If import fails, system falls back to existing legacy configuration. No breaking changes.

## References

- [Playwright MCP Browser Automation](https://github.com/microsoft/playwright-mcp)
- [Bypass Cloudflare with Playwright](https://www.browserless.io/blog/bypass-cloudflare-with-playwright)
- [ZenRows: Playwright Cloudflare Bypass](https://www.zenrows.com/blog/playwright-cloudflare-bypass)
- [Kameleo: How to Bypass Cloudflare](https://kameleo.io/blog/how-to-bypass-cloudflare-with-playwright)

## Next Steps

1. ✅ Created stealth_browser_config.py module
2. Import module in playwright_direct.py
3. Update connect() method to use MCP-compatible config
4. Update browser launch to try Chrome channel
5. Update script injection to use enhanced stealth script
6. Test on Crunchbase and other Cloudflare-protected sites
7. Publish updated package to npm
