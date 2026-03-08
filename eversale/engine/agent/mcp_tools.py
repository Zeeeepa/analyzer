"""
MCP-Style Atomic Browser Tools - Battle-Hardened Edition

This module provides simple, atomic browser tools that mirror the Playwright MCP approach,
PLUS our battle-tested patterns for anti-detection, challenge handling, and recovery.

THE KEY INSIGHT:
Claude Code + Playwright MCP works because:
1. Each tool does ONE thing
2. Screenshot after EVERY action (LLM sees result)
3. Simple selectors (text=, role=, aria-label=)
4. NO pre-planning - LLM decides step by step
5. NO complex recovery - LLM tries different approach if something fails

BATTLE-HARDENED ADDITIONS:
6. Stealth mode (anti-bot detection)
7. Challenge detection (Cloudflare, captcha)
8. Human-like timing
9. Overlay auto-dismissal
10. Session persistence

Usage:
    tools = MCPTools()
    await tools.launch()

    # Simple loop - LLM is the brain
    while not done:
        screenshot = await tools.screenshot()
        next_action = await llm.decide(screenshot, task)
        result = await tools.execute(next_action)
"""

import asyncio
import base64
import re
import random
import time
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from pathlib import Path
from loguru import logger

# Import Playwright (prefer patchright for stealth)
try:
    from patchright.async_api import async_playwright, Page, Browser, BrowserContext
    BROWSER_LIB = "patchright"
except ImportError:
    try:
        from playwright.async_api import async_playwright, Page, Browser, BrowserContext
        BROWSER_LIB = "playwright"
    except ImportError:
        raise ImportError("Neither patchright nor playwright is installed")


# =============================================================================
# BATTLE-TESTED PATTERNS - From our production experience
# =============================================================================

# Challenge detection indicators (from stealth_enhanced.py)
CHALLENGE_INDICATORS = {
    "strong": [
        "cf-browser-verification", "cf_chl_opt", "Cloudflare Ray ID",
        "cf-spinner", "challenge-platform", "turnstile",
    ],
    "weak": [
        "Just a moment...", "Checking your browser", "security challenge",
        "Please verify you are human", "Enable JavaScript and cookies",
    ],
    "captcha": [
        "g-recaptcha", "h-captcha", "recaptcha", "hcaptcha", "captcha-container",
    ]
}

# Human-like timing patterns (from stealth_enhanced.py)
HUMAN_TIMING = {
    "click_delay": (50, 150),      # ms before click
    "type_delay": (30, 100),       # ms between keystrokes
    "scroll_delay": (100, 300),    # ms between scroll steps
    "page_wait": (500, 1500),      # ms after navigation
}

# Stealth JavaScript injection (from stealth_enhanced.py)
STEALTH_JS = """
// Delete webdriver property (main detection vector)
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// Spoof plugins to look like real browser
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});

// Block permissions.query (detection vector)
const originalQuery = navigator.permissions.query;
navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);
"""

# Common overlay/popup dismiss selectors (from cascading_recovery.py)
POPUP_DISMISS_SELECTORS = [
    # Cookie banners
    "[class*='cookie'] button[class*='accept']",
    "[class*='cookie'] button[class*='close']",
    "[class*='consent'] button[class*='accept']",
    "button[aria-label*='Accept']",
    "button[aria-label*='accept cookies']",
    # Modals
    ".modal .close", ".modal [data-dismiss='modal']",
    "[class*='modal'] button[class*='close']",
    "[role='dialog'] button[aria-label='Close']",
    # Generic
    "button[class*='dismiss']",
    "[class*='popup'] button[class*='close']",
    # Text-based
    'text="Accept"', 'text="Accept All"', 'text="Accept Cookies"',
    'text="I Accept"', 'text="Got it"', 'text="OK"',
    'text="Close"', 'text="No thanks"', 'text="Dismiss"',
]


@dataclass
class ToolResult:
    """Simple result from any tool call."""
    success: bool
    message: str
    data: Optional[Any] = None
    screenshot_b64: Optional[str] = None  # Always include screenshot for LLM


class MCPTools:
    """
    Simple, atomic browser tools - MCP style, Battle-Hardened Edition.

    Philosophy:
    - Each method does ONE thing
    - Returns screenshot with every result (so LLM can see what happened)
    - Simple selectors that work everywhere
    - If something fails, return the error - let LLM figure out what to do

    Battle-Hardened Features:
    - Stealth mode (anti-bot detection bypass)
    - Challenge detection (Cloudflare, captcha awareness)
    - Human-like timing (avoid bot patterns)
    - Auto popup dismissal
    """

    def __init__(
        self,
        headless: bool = True,
        slow_mo: int = 0,
        enable_stealth: bool = True,
        enable_human_timing: bool = True
    ):
        self.headless = headless
        self.slow_mo = slow_mo
        self.enable_stealth = enable_stealth
        self.enable_human_timing = enable_human_timing
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._challenge_detected = False
        self._action_count = 0

    async def launch(self, user_data_dir: Optional[str] = None) -> ToolResult:
        """Launch browser with stealth mode. Call this first."""
        try:
            self._playwright = await async_playwright().start()

            # Battle-tested launch args (from stealth_enhanced.py)
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu",
            ]

            # Common viewport to avoid fingerprinting
            viewport = {"width": 1280, "height": 800}

            # User agent (realistic Chrome on Windows)
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

            if user_data_dir:
                # Persistent context (keeps login sessions)
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=self.headless,
                    slow_mo=self.slow_mo,
                    args=launch_args,
                    viewport=viewport,
                    user_agent=user_agent,
                    locale="en-US",
                    timezone_id="America/New_York",
                    geolocation={"latitude": 40.7128, "longitude": -74.0060},
                    permissions=["geolocation"],
                )
                self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
            else:
                self._browser = await self._playwright.chromium.launch(
                    headless=self.headless,
                    slow_mo=self.slow_mo,
                    args=launch_args,
                )
                self._context = await self._browser.new_context(
                    viewport=viewport,
                    user_agent=user_agent,
                    locale="en-US",
                    timezone_id="America/New_York",
                    geolocation={"latitude": 40.7128, "longitude": -74.0060},
                    permissions=["geolocation"],
                )
                self._page = await self._context.new_page()

            # Apply stealth JavaScript (critical for anti-detection)
            if self.enable_stealth:
                await self._page.add_init_script(STEALTH_JS)
                logger.debug("[STEALTH] Anti-detection scripts injected")

            return ToolResult(success=True, message=f"Browser launched ({BROWSER_LIB}) with stealth mode")
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to launch: {e}")

    async def close(self) -> ToolResult:
        """Close browser."""
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            return ToolResult(success=True, message="Browser closed")
        except Exception as e:
            return ToolResult(success=False, message=f"Close error: {e}")

    # =========================================================================
    # CORE TOOLS - These are all you need
    # =========================================================================

    async def screenshot(self, full_page: bool = False) -> ToolResult:
        """
        Take a screenshot. This is THE critical tool.
        Call this after every action so LLM can see results.
        """
        try:
            img_bytes = await self._page.screenshot(full_page=full_page)
            b64 = base64.b64encode(img_bytes).decode()
            return ToolResult(
                success=True,
                message="Screenshot captured",
                screenshot_b64=b64
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Screenshot failed: {e}")

    async def navigate(self, url: str, wait_until: str = "domcontentloaded") -> ToolResult:
        """Navigate to a URL with challenge detection."""
        try:
            # Add protocol if missing
            if not url.startswith("http"):
                url = "https://" + url

            await self._page.goto(url, wait_until=wait_until, timeout=30000)

            # Human-like wait after navigation
            if self.enable_human_timing:
                delay = random.randint(*HUMAN_TIMING["page_wait"])
                await asyncio.sleep(delay / 1000)

            # Check for challenges (Cloudflare, captcha)
            challenge = await self._detect_challenge()
            challenge_msg = ""
            if challenge:
                self._challenge_detected = True
                challenge_msg = f" [WARNING: {challenge['type']} detected]"
                logger.warning(f"[CHALLENGE] {challenge['type']} detected on {url}")

            # Always return screenshot so LLM sees the result
            screenshot = await self._page.screenshot()
            return ToolResult(
                success=True,
                message=f"Navigated to {url}{challenge_msg}",
                data={
                    "url": self._page.url,
                    "title": await self._page.title(),
                    "challenge_detected": challenge
                },
                screenshot_b64=base64.b64encode(screenshot).decode()
            )
        except Exception as e:
            # Try with www prefix as fallback
            if "://" in url and "www." not in url:
                try:
                    alt_url = url.replace("://", "://www.")
                    await self._page.goto(alt_url, wait_until=wait_until, timeout=30000)
                    screenshot = await self._page.screenshot()
                    return ToolResult(
                        success=True,
                        message=f"Navigated to {alt_url} (www fallback)",
                        data={"url": self._page.url, "title": await self._page.title()},
                        screenshot_b64=base64.b64encode(screenshot).decode()
                    )
                except Exception as fallback_e:
                    logger.debug(f"WWW fallback also failed for {alt_url}: {fallback_e}")
            return ToolResult(success=False, message=f"Navigate failed: {e}")

    async def click(self, selector: str, timeout: int = 5000) -> ToolResult:
        """
        Click an element with human-like timing and fallback selectors.

        Selector tips (what works reliably):
        - text="Login"           - Exact text match
        - text="Login" >> nth=0  - First match
        - role=button[name="Submit"]  - ARIA role
        - [aria-label="Close"]   - Aria label
        - #id                    - ID selector
        - .class                 - Class selector

        AVOID: Complex CSS paths, XPath, indexes that change
        """
        self._action_count += 1

        # Human-like delay before click
        if self.enable_human_timing:
            delay = random.randint(*HUMAN_TIMING["click_delay"])
            await asyncio.sleep(delay / 1000)

        try:
            # Try to click with built-in waiting
            await self._page.click(selector, timeout=timeout)
            await self._page.wait_for_timeout(500)  # Brief pause for UI update

            screenshot = await self._page.screenshot()
            return ToolResult(
                success=True,
                message=f"Clicked: {selector}",
                screenshot_b64=base64.b64encode(screenshot).decode()
            )
        except Exception as e:
            error_msg = str(e).lower()

            # If element not visible, try closing overlays first
            if "not visible" in error_msg or "intercept" in error_msg:
                logger.debug(f"[RECOVERY] Click intercepted, trying to close overlays...")
                await self._close_overlays_internal()
                try:
                    await self._page.click(selector, timeout=timeout)
                    await self._page.wait_for_timeout(500)
                    screenshot = await self._page.screenshot()
                    return ToolResult(
                        success=True,
                        message=f"Clicked: {selector} (after closing overlays)",
                        screenshot_b64=base64.b64encode(screenshot).decode()
                    )
                except Exception as retry_e:
                    logger.debug(f"[RECOVERY] Retry after overlay close also failed: {retry_e}")

            # Return error with screenshot so LLM can see what's wrong
            try:
                screenshot = await self._page.screenshot()
                screenshot_b64 = base64.b64encode(screenshot).decode()
            except Exception as screenshot_e:
                logger.debug(f"Failed to capture error screenshot: {screenshot_e}")
                screenshot_b64 = None
            return ToolResult(
                success=False,
                message=f"Click failed on '{selector}': {e}",
                screenshot_b64=screenshot_b64
            )

    async def type(self, selector: str, text: str, clear_first: bool = True, timeout: int = 5000, press_key: str = None) -> ToolResult:
        """
        Type text into an input field.

        Args:
            selector: Element to type into
            text: Text to type
            clear_first: Clear existing text before typing (default True)
            press_key: Optional key to press after typing (e.g., "Enter")
        """
        try:
            if clear_first:
                await self._page.fill(selector, text, timeout=timeout)
            else:
                await self._page.type(selector, text, timeout=timeout)

            if press_key:
                await self._page.keyboard.press(press_key)
                await self._page.wait_for_timeout(300)

            screenshot = await self._page.screenshot()
            return ToolResult(
                success=True,
                message=f"Typed into {selector}" + (f" and pressed {press_key}" if press_key else ""),
                screenshot_b64=base64.b64encode(screenshot).decode()
            )
        except Exception as e:
            try:
                screenshot = await self._page.screenshot()
                screenshot_b64 = base64.b64encode(screenshot).decode()
            except Exception as screenshot_e:
                logger.debug(f"Failed to capture error screenshot: {screenshot_e}")
                screenshot_b64 = None
            return ToolResult(
                success=False,
                message=f"Type failed on '{selector}': {e}",
                screenshot_b64=screenshot_b64
            )

    async def press(self, key: str) -> ToolResult:
        """
        Press a keyboard key.

        Common keys: Enter, Tab, Escape, ArrowDown, ArrowUp, Backspace
        Combos: Control+a, Control+c, Control+v
        """
        try:
            await self._page.keyboard.press(key)
            await self._page.wait_for_timeout(300)

            screenshot = await self._page.screenshot()
            return ToolResult(
                success=True,
                message=f"Pressed: {key}",
                screenshot_b64=base64.b64encode(screenshot).decode()
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Press failed: {e}")

    async def scroll(self, direction: str = "down", amount: int = 500) -> ToolResult:
        """
        Scroll the page.

        Args:
            direction: "up", "down", "left", "right"
            amount: Pixels to scroll
        """
        try:
            delta = {
                "down": (0, amount),
                "up": (0, -amount),
                "right": (amount, 0),
                "left": (-amount, 0),
            }.get(direction, (0, amount))

            await self._page.mouse.wheel(delta[0], delta[1])
            await self._page.wait_for_timeout(500)

            screenshot = await self._page.screenshot()
            return ToolResult(
                success=True,
                message=f"Scrolled {direction} by {amount}px",
                screenshot_b64=base64.b64encode(screenshot).decode()
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Scroll failed: {e}")

    async def wait(self, selector: str, state: str = "visible", timeout: int = 10000) -> ToolResult:
        """
        Wait for an element.

        Args:
            selector: Element to wait for
            state: "visible", "hidden", "attached", "detached"
        """
        try:
            await self._page.wait_for_selector(selector, state=state, timeout=timeout)
            screenshot = await self._page.screenshot()
            return ToolResult(
                success=True,
                message=f"Element '{selector}' is {state}",
                screenshot_b64=base64.b64encode(screenshot).decode()
            )
        except Exception as e:
            try:
                screenshot = await self._page.screenshot()
                screenshot_b64 = base64.b64encode(screenshot).decode()
            except Exception as screenshot_e:
                logger.debug(f"Failed to capture error screenshot: {screenshot_e}")
                screenshot_b64 = None
            return ToolResult(
                success=False,
                message=f"Wait timeout for '{selector}': {e}",
                screenshot_b64=screenshot_b64
            )

    async def select(self, selector: str, value: str) -> ToolResult:
        """Select an option from a dropdown."""
        try:
            await self._page.select_option(selector, value)
            screenshot = await self._page.screenshot()
            return ToolResult(
                success=True,
                message=f"Selected '{value}' in {selector}",
                screenshot_b64=base64.b64encode(screenshot).decode()
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Select failed: {e}")

    async def hover(self, selector: str) -> ToolResult:
        """Hover over an element."""
        try:
            await self._page.hover(selector)
            await self._page.wait_for_timeout(300)
            screenshot = await self._page.screenshot()
            return ToolResult(
                success=True,
                message=f"Hovering over {selector}",
                screenshot_b64=base64.b64encode(screenshot).decode()
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Hover failed: {e}")

    async def get_text(self, selector: str) -> ToolResult:
        """Get text content of an element."""
        try:
            text = await self._page.text_content(selector)
            return ToolResult(
                success=True,
                message=f"Got text from {selector}",
                data={"text": text}
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Get text failed: {e}")

    async def get_attribute(self, selector: str, attribute: str) -> ToolResult:
        """Get an attribute value from an element."""
        try:
            value = await self._page.get_attribute(selector, attribute)
            return ToolResult(
                success=True,
                message=f"Got {attribute} from {selector}",
                data={"attribute": attribute, "value": value}
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Get attribute failed: {e}")

    async def evaluate(self, script: str) -> ToolResult:
        """Run JavaScript in the page."""
        try:
            result = await self._page.evaluate(script)
            return ToolResult(
                success=True,
                message="Script executed",
                data={"result": result}
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Evaluate failed: {e}")

    # =========================================================================
    # BATTLE-HARDENED INTERNAL METHODS
    # =========================================================================

    async def _detect_challenge(self) -> Optional[Dict[str, Any]]:
        """
        Detect Cloudflare, captcha, or other bot challenges.
        Returns challenge info dict or None if no challenge detected.
        """
        try:
            html = await self._page.content()
            html_lower = html.lower()
            page_length = len(html)

            # Check strong indicators (always trigger)
            for indicator in CHALLENGE_INDICATORS["strong"]:
                if indicator.lower() in html_lower:
                    return {
                        "type": "cloudflare",
                        "indicator": indicator,
                        "confidence": "high"
                    }

            # Check weak indicators (only if page is small - likely a challenge page)
            if page_length < 5000:
                for indicator in CHALLENGE_INDICATORS["weak"]:
                    if indicator.lower() in html_lower:
                        return {
                            "type": "challenge",
                            "indicator": indicator,
                            "confidence": "medium"
                        }

            # Check for captcha
            for indicator in CHALLENGE_INDICATORS["captcha"]:
                if indicator.lower() in html_lower:
                    return {
                        "type": "captcha",
                        "indicator": indicator,
                        "confidence": "high"
                    }

            return None
        except Exception as e:
            logger.debug(f"Challenge detection error: {e}")
            return None

    async def _close_overlays_internal(self) -> int:
        """
        Internal method to close overlays without returning ToolResult.
        Returns count of closed overlays.
        """
        closed_count = 0

        for selector in POPUP_DISMISS_SELECTORS:
            try:
                if await self._page.is_visible(selector, timeout=300):
                    await self._page.click(selector, timeout=1000)
                    closed_count += 1
                    await self._page.wait_for_timeout(200)
            except Exception as e:
                logger.debug(f"Failed to close overlay with selector {selector}: {e}")
                continue

        # Try pressing Escape as fallback
        try:
            await self._page.keyboard.press("Escape")
        except Exception as e:
            logger.debug(f"Failed to press Escape for overlay dismissal: {e}")

        return closed_count

    async def check_health(self) -> ToolResult:
        """
        Check if browser is healthy and responsive.
        Use this to detect if browser needs restart.
        """
        try:
            result = await self._page.evaluate("1 + 1", timeout=5000)
            if result == 2:
                return ToolResult(
                    success=True,
                    message="Browser healthy",
                    data={
                        "action_count": self._action_count,
                        "challenge_detected": self._challenge_detected
                    }
                )
            return ToolResult(success=False, message="Browser returned unexpected result")
        except Exception as e:
            return ToolResult(success=False, message=f"Browser unhealthy: {e}")

    # =========================================================================
    # HELPER METHODS - Common patterns
    # =========================================================================

    async def dismiss_popups(self) -> ToolResult:
        """
        Try to dismiss common popups/overlays.
        Call this if something is blocking the page.
        """
        dismissed = []

        # Common popup dismiss patterns
        dismiss_selectors = [
            'text="Accept"',
            'text="Accept All"',
            'text="Accept Cookies"',
            'text="I Accept"',
            'text="Got it"',
            'text="OK"',
            'text="Close"',
            'text="No thanks"',
            'text="Maybe later"',
            'text="Dismiss"',
            '[aria-label="Close"]',
            '[aria-label="Dismiss"]',
            'button:has-text("Accept")',
            'button:has-text("Close")',
            '.modal-close',
            '.popup-close',
            '#cookie-accept',
            '.cookie-accept',
        ]

        for selector in dismiss_selectors:
            try:
                if await self._page.is_visible(selector, timeout=500):
                    await self._page.click(selector, timeout=1000)
                    dismissed.append(selector)
                    await self._page.wait_for_timeout(300)
            except Exception as e:
                logger.debug(f"Failed to dismiss popup with selector {selector}: {e}")
                continue

        screenshot = await self._page.screenshot()
        return ToolResult(
            success=True,
            message=f"Dismissed: {dismissed}" if dismissed else "No popups found",
            data={"dismissed": dismissed},
            screenshot_b64=base64.b64encode(screenshot).decode()
        )

    async def get_page_info(self) -> ToolResult:
        """Get current page state - useful for LLM context."""
        try:
            info = {
                "url": self._page.url,
                "title": await self._page.title(),
            }

            # Get visible interactive elements (simplified accessibility tree)
            elements = await self._page.evaluate("""
                () => {
                    const items = [];
                    const selector = 'a, button, input, select, textarea, [role="button"], [role="link"], [onclick]';
                    document.querySelectorAll(selector).forEach((el, i) => {
                        if (el.offsetParent !== null && i < 50) {  // Visible and limit to 50
                            items.push({
                                tag: el.tagName.toLowerCase(),
                                text: (el.innerText || el.value || el.placeholder || '').slice(0, 50),
                                type: el.type || el.getAttribute('role') || '',
                                id: el.id || '',
                                name: el.name || '',
                                ariaLabel: el.getAttribute('aria-label') || '',
                            });
                        }
                    });
                    return items;
                }
            """)
            info["interactive_elements"] = elements

            screenshot = await self._page.screenshot()
            return ToolResult(
                success=True,
                message="Page info retrieved",
                data=info,
                screenshot_b64=base64.b64encode(screenshot).decode()
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Get page info failed: {e}")

    # =========================================================================
    # TOOL EXECUTION - For LLM tool calls
    # =========================================================================

    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """
        Execute a tool by name. Use this for LLM tool calling.

        Example:
            result = await tools.execute("click", selector='text="Login"')
        """
        tool_map = {
            "screenshot": self.screenshot,
            "navigate": self.navigate,
            "click": self.click,
            "type": self.type,
            "press": self.press,
            "scroll": self.scroll,
            "wait": self.wait,
            "select": self.select,
            "hover": self.hover,
            "get_text": self.get_text,
            "get_attribute": self.get_attribute,
            "evaluate": self.evaluate,
            "dismiss_popups": self.dismiss_popups,
            "get_page_info": self.get_page_info,
            "check_health": self.check_health,
        }

        if tool_name not in tool_map:
            return ToolResult(
                success=False,
                message=f"Unknown tool: {tool_name}. Available: {list(tool_map.keys())}"
            )

        return await tool_map[tool_name](**kwargs)

    def get_tool_definitions(self) -> List[Dict]:
        """
        Get tool definitions for LLM function calling.
        Format compatible with OpenAI/qwen function calling.
        """
        return [
            {
                "name": "screenshot",
                "description": "Take a screenshot of the current page",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "full_page": {"type": "boolean", "description": "Capture full scrollable page"}
                    }
                }
            },
            {
                "name": "navigate",
                "description": "Navigate to a URL",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to navigate to"}
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "click",
                "description": "Click an element. Use simple selectors: text=\"Login\", role=button, [aria-label=\"Close\"], #id, .class",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "Element selector"}
                    },
                    "required": ["selector"]
                }
            },
            {
                "name": "type",
                "description": "Type text into an input field",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "Input field selector"},
                        "text": {"type": "string", "description": "Text to type"},
                        "press_key": {"type": "string", "description": "Optional key to press after typing (e.g. Enter)"}
                    },
                    "required": ["selector", "text"]
                }
            },
            {
                "name": "press",
                "description": "Press a keyboard key (Enter, Tab, Escape, ArrowDown, Control+a, etc)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Key to press"}
                    },
                    "required": ["key"]
                }
            },
            {
                "name": "scroll",
                "description": "Scroll the page",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                        "amount": {"type": "integer", "description": "Pixels to scroll"}
                    }
                }
            },
            {
                "name": "wait",
                "description": "Wait for an element to appear",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "Element to wait for"},
                        "state": {"type": "string", "enum": ["visible", "hidden", "attached", "detached"]}
                    },
                    "required": ["selector"]
                }
            },
            {
                "name": "select",
                "description": "Select option from dropdown",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string"},
                        "value": {"type": "string"}
                    },
                    "required": ["selector", "value"]
                }
            },
            {
                "name": "hover",
                "description": "Hover over an element",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string"}
                    },
                    "required": ["selector"]
                }
            },
            {
                "name": "get_text",
                "description": "Get text content of an element",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string"}
                    },
                    "required": ["selector"]
                }
            },
            {
                "name": "dismiss_popups",
                "description": "Try to dismiss cookie banners, modals, and other popups",
                "parameters": {"type": "object", "properties": {}}
            },
            {
                "name": "get_page_info",
                "description": "Get current page URL, title, and list of interactive elements",
                "parameters": {"type": "object", "properties": {}}
            },
        ]


# =============================================================================
# SIMPLE AGENT LOOP - This replaces 6,000+ lines of brain/planning/action code
# =============================================================================

async def simple_agent_loop(
    task: str,
    llm_client,  # Your LLM client with vision support
    tools: MCPTools,
    max_steps: int = 30,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Simple agent loop - MCP style.

    This is what replaces brain_enhanced_v2.py, planning_agent.py, action_engine.py,
    and action_router.py combined (6,741 lines) with ~50 lines.

    The magic: Let the LLM be the brain. Don't try to be smart in code.
    """

    history = []

    # Get initial screenshot
    initial = await tools.get_page_info()

    system_prompt = f"""You are a browser automation agent. Your task: {task}

Available tools:
- navigate(url): Go to a URL
- click(selector): Click an element. Use selectors like: text="Login", role=button[name="Submit"], [aria-label="Close"], #id
- type(selector, text): Type into an input
- press(key): Press keyboard key (Enter, Tab, Escape, etc)
- scroll(direction, amount): Scroll up/down/left/right
- wait(selector): Wait for element to appear
- select(selector, value): Select from dropdown
- dismiss_popups(): Dismiss cookie banners and modals
- get_page_info(): Get page URL and interactive elements

RULES:
1. Look at the screenshot carefully before each action
2. Use simple selectors - prefer text= and role= over complex CSS
3. Do ONE action at a time
4. If something fails, try a different selector or approach
5. Say "TASK_COMPLETE" when done

Current page: {initial.data.get('url', 'about:blank')}
"""

    for step in range(max_steps):
        # Get current state
        screenshot_result = await tools.screenshot()

        if verbose:
            logger.info(f"Step {step + 1}/{max_steps}")

        # Ask LLM what to do
        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Step {step + 1}. What should I do next? Current screenshot:"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_result.screenshot_b64}"}}
                ]
            }
        ]

        # Get LLM response (this should be your vision model like UI-TARS or qwen)
        response = await llm_client.chat(messages)
        llm_text = response.content

        if verbose:
            logger.info(f"LLM: {llm_text[:200]}...")

        # Check if task is complete
        if "TASK_COMPLETE" in llm_text.upper():
            return {
                "success": True,
                "message": "Task completed",
                "steps": step + 1,
                "history": history
            }

        # Parse and execute tool call from LLM response
        # This is simplified - in production use proper function calling
        tool_result = await _parse_and_execute_tool(llm_text, tools)

        # Add to history
        history.append({"role": "assistant", "content": llm_text})
        history.append({"role": "user", "content": f"Tool result: {tool_result.message}"})

        if verbose:
            logger.info(f"Tool result: {tool_result.message}")

    return {
        "success": False,
        "message": f"Max steps ({max_steps}) reached",
        "steps": max_steps,
        "history": history
    }


async def _parse_and_execute_tool(llm_response: str, tools: MCPTools) -> ToolResult:
    """
    Parse tool call from LLM response and execute it.

    Expects format like:
    - click(selector='text="Login"')
    - navigate(url="https://example.com")
    - type(selector="#email", text="test@example.com")
    """
    import re

    # Try to find tool call pattern
    patterns = [
        r'(\w+)\s*\(\s*(.+?)\s*\)',  # tool(args)
        r'Tool:\s*(\w+)\s*\(\s*(.+?)\s*\)',  # Tool: tool(args)
        r'Action:\s*(\w+)\s*\(\s*(.+?)\s*\)',  # Action: tool(args)
    ]

    for pattern in patterns:
        match = re.search(pattern, llm_response, re.DOTALL)
        if match:
            tool_name = match.group(1).lower()
            args_str = match.group(2)

            # Parse arguments
            kwargs = {}
            # Handle key="value" and key='value' patterns
            arg_pattern = r"(\w+)\s*=\s*['\"](.+?)['\"]|(\w+)\s*=\s*(\d+)"
            for arg_match in re.finditer(arg_pattern, args_str):
                if arg_match.group(1):
                    kwargs[arg_match.group(1)] = arg_match.group(2)
                elif arg_match.group(3):
                    kwargs[arg_match.group(3)] = int(arg_match.group(4))

            return await tools.execute(tool_name, **kwargs)

    # No tool found - maybe LLM is just thinking
    return ToolResult(success=True, message="No tool call detected in response")


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

async def example_usage():
    """
    Example of how to use the simple MCP-style approach.

    This replaces the complex brain/planning/action engine stack with
    a simple loop that works on any site.
    """
    from .llm_client import LLMClient

    # Initialize
    tools = MCPTools(headless=False)
    llm = LLMClient()

    await tools.launch()

    try:
        # Run a task - the LLM figures everything out
        result = await simple_agent_loop(
            task="Go to google.com and search for 'playwright automation'",
            llm_client=llm,
            tools=tools,
            max_steps=20
        )

        print(f"Result: {result}")

    finally:
        await tools.close()


if __name__ == "__main__":
    asyncio.run(example_usage())
