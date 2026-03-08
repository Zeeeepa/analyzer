#!/usr/bin/env python3
"""
CDP Browser Connector - Connect to existing Chrome sessions via CDP

This module provides a way to connect to an existing Chrome browser instance
via the Chrome DevTools Protocol (CDP), preserving all login sessions, cookies,
and localStorage. This is superior to launching fresh browser instances because:

1. All existing logins are preserved (Gmail, LinkedIn, Facebook, etc.)
2. No CAPTCHA challenges (real browser fingerprint)
3. No bot detection (genuine user profile)
4. Faster startup (browser already running)
5. Uses user's existing extensions and settings

Usage:
    # Option 1: Connect to existing Chrome
    connector = CDPBrowserConnector(port=9222)
    browser = await connector.connect()
    await browser.goto("https://mail.google.com")  # Already logged in!

    # Option 2: Auto-launch Chrome with CDP if not running
    connector = CDPBrowserConnector(auto_launch=True)
    browser = await connector.connect()

    # Option 3: Find Chrome automatically
    connector = await CDPBrowserConnector.auto_discover()
    browser = await connector.connect()

Author: Eversale Team
Date: December 2024
"""

import asyncio
import json
import platform
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
from loguru import logger

# Check for Playwright CDP support
try:
    from playwright.async_api import async_playwright
    CDP_AVAILABLE = True
except ImportError:
    logger.warning("Playwright not available for CDP connection")
    CDP_AVAILABLE = False


@dataclass
class CDPBrowserInstance:
    """
    Wrapper around CDP-connected browser that implements the same interface
    as PlaywrightAgent for drop-in compatibility.
    """
    browser: Any
    context: Any
    page: Any
    port: int
    _mmid_elements: Dict[str, Any] = None

    async def goto(self, url: str, wait_until: str = "domcontentloaded") -> Dict[str, Any]:
        """Navigate to URL"""
        try:
            await self.page.goto(url, wait_until=wait_until, timeout=30000)
            return {"success": True, "url": self.page.url}
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return {"error": str(e)}

    async def snapshot(self) -> Dict[str, Any]:
        """Get accessibility-focused snapshot of current page"""
        try:
            title = await self.page.title()
            acc_tree = await self.page.accessibility.snapshot(interesting_only=True)
            snapshot_text = self._format_accessibility_tree(acc_tree)

            return {
                "success": True,
                "title": title,
                "url": self.page.url,
                "snapshot": snapshot_text,
                "tree": acc_tree
            }
        except Exception as e:
            logger.error(f"Snapshot failed: {e}")
            return {"error": str(e)}

    async def browser_snapshot(self) -> Dict[str, Any]:
        """
        Get page snapshot with actionable element references (mmid-based).
        This is the Claude Code style interface.
        """
        try:
            # Inject mmid markers and collect element data
            elements = await self.page.evaluate("""() => {
                const MMID_ATTR = 'data-mmid';
                const elements = [];
                let counter = 0;

                // Find all interactive elements
                const selectors = [
                    'a[href]',
                    'button',
                    'input',
                    'textarea',
                    'select',
                    '[role="button"]',
                    '[role="link"]',
                    '[role="textbox"]',
                    '[onclick]'
                ];

                const found = new Set();
                selectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        if (found.has(el)) return;
                        found.add(el);

                        // Inject mmid
                        const mmid = `mm${counter++}`;
                        el.setAttribute(MMID_ATTR, mmid);

                        // Get element info
                        const rect = el.getBoundingClientRect();
                        const role = el.getAttribute('role') || el.tagName.toLowerCase();
                        const text = el.innerText || el.value || el.placeholder || el.alt || '';

                        elements.push({
                            mmid: mmid,
                            role: role,
                            text: text.trim().substring(0, 100),
                            tag: el.tagName.toLowerCase(),
                            selector: el.id ? `#${el.id}` : '',
                            rect: {
                                x: rect.x,
                                y: rect.y,
                                width: rect.width,
                                height: rect.height
                            },
                            visible: rect.width > 0 && rect.height > 0
                        });
                    });
                });

                return elements;
            }()""")

            # Cache mmid -> element mapping
            self._mmid_elements = {}
            for el in elements:
                self._mmid_elements[el['mmid']] = el

            return {
                "success": True,
                "url": self.page.url,
                "title": await self.page.title(),
                "elements": elements,
                "count": len(elements)
            }

        except Exception as e:
            logger.error(f"Browser snapshot failed: {e}")
            return {"error": str(e)}

    async def click(self, ref: str) -> Dict[str, Any]:
        """
        Click element by mmid reference or CSS selector.

        Args:
            ref: mmid (e.g. "mm0") or CSS selector
        """
        try:
            # If mmid reference, convert to selector
            if ref.startswith("mm"):
                selector = f'[data-mmid="{ref}"]'
            else:
                selector = ref

            element = await self.page.query_selector(selector)
            if not element:
                return {"error": f"Element not found: {ref}"}

            await element.click()
            return {"success": True, "ref": ref}

        except Exception as e:
            logger.error(f"Click failed on {ref}: {e}")
            return {"error": str(e)}

    async def type(self, ref: str, text: str, clear: bool = True) -> Dict[str, Any]:
        """
        Type text into element by mmid reference or CSS selector.

        Args:
            ref: mmid (e.g. "mm0") or CSS selector
            text: Text to type
            clear: Clear existing text first
        """
        try:
            # If mmid reference, convert to selector
            if ref.startswith("mm"):
                selector = f'[data-mmid="{ref}"]'
            else:
                selector = ref

            element = await self.page.query_selector(selector)
            if not element:
                return {"error": f"Element not found: {ref}"}

            if clear:
                await element.fill("")

            await element.type(text, delay=50)  # Human-like typing
            return {"success": True, "ref": ref, "text": text}

        except Exception as e:
            logger.error(f"Type failed on {ref}: {e}")
            return {"error": str(e)}

    async def run_code(self, js_code: str) -> Dict[str, Any]:
        """
        Execute JavaScript code in page context.

        Args:
            js_code: JavaScript code to execute
        """
        try:
            result = await self.page.evaluate(js_code)
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"Code execution failed: {e}")
            return {"error": str(e)}

    async def close(self):
        """Close the browser connection (doesn't close Chrome itself)"""
        try:
            if self.browser:
                await self.browser.close()
        except Exception as e:
            logger.debug(f"Error closing browser: {e}")

    def _format_accessibility_tree(self, node: Dict, level: int = 0) -> str:
        """Format accessibility tree as readable text"""
        if not node:
            return ""

        lines = []
        indent = "  " * level

        # Format current node
        role = node.get("role", "")
        name = node.get("name", "")
        value = node.get("value", "")

        if role:
            line = f"{indent}{role}"
            if name:
                line += f": {name}"
            if value:
                line += f" = {value}"
            lines.append(line)

        # Process children
        for child in node.get("children", []):
            lines.append(self._format_accessibility_tree(child, level + 1))

        return "\n".join(lines)


class CDPBrowserConnector:
    """
    Connect to existing Chrome browser via Chrome DevTools Protocol (CDP).

    This connector can:
    1. Connect to existing Chrome instances with --remote-debugging-port
    2. Auto-launch Chrome with CDP enabled if not running
    3. Auto-discover Chrome debugging ports
    4. Reconnect if Chrome restarts
    """

    def __init__(
        self,
        port: int = 9222,
        host: str = "localhost",
        auto_launch: bool = False,
        user_data_dir: Optional[str] = None
    ):
        """
        Initialize CDP connector.

        Args:
            port: Chrome debugging port (default: 9222)
            host: Chrome debugging host (default: localhost)
            auto_launch: Auto-launch Chrome if not running
            user_data_dir: Optional Chrome profile directory
        """
        self.port = port
        self.host = host
        self.auto_launch = auto_launch
        self.user_data_dir = user_data_dir
        self.playwright = None
        self._browser = None
        self._context = None
        self._page = None

    async def connect(self) -> Optional[CDPBrowserInstance]:
        """
        Connect to existing Chrome browser via CDP.

        Returns:
            CDPBrowserInstance with page interface compatible with PlaywrightAgent

        Raises:
            ConnectionError: If Chrome is not running and auto_launch is False
        """
        if not CDP_AVAILABLE:
            raise ImportError("Playwright required for CDP connection")

        # Try to connect to existing Chrome
        cdp_url = f"http://{self.host}:{self.port}"

        # Check if Chrome is already running
        if not await self._is_chrome_running():
            if self.auto_launch:
                logger.info("Chrome not running, launching with CDP enabled...")
                await self._launch_chrome()
                # Wait for Chrome to start
                await asyncio.sleep(2)
            else:
                raise ConnectionError(
                    f"Chrome not running on port {self.port}. "
                    f"Start Chrome with: {self._get_chrome_launch_command()}"
                )

        logger.info(f"Connecting to existing browser at {cdp_url}")

        try:
            self.playwright = await async_playwright().start()

            # Connect over CDP
            self._browser = await self.playwright.chromium.connect_over_cdp(cdp_url)

            # Get existing context or create new one
            contexts = self._browser.contexts
            if contexts:
                self._context = contexts[0]
                logger.info(f"Connected to existing context with {len(self._context.pages)} tab(s)")
            else:
                self._context = await self._browser.new_context()
                logger.info("Created new context")

            # Get existing page or create new one
            pages = self._context.pages
            if pages:
                self._page = pages[-1]  # Use most recent page
                logger.info(f"Using existing page: {self._page.url}")
            else:
                self._page = await self._context.new_page()
                logger.info("Created new page")

            return CDPBrowserInstance(
                browser=self._browser,
                context=self._context,
                page=self._page,
                port=self.port
            )

        except Exception as e:
            error_msg = str(e)
            if "connect ECONNREFUSED" in error_msg or "Failed to connect" in error_msg:
                raise ConnectionError(
                    f"Cannot connect to Chrome at {cdp_url}. "
                    f"Start Chrome with: {self._get_chrome_launch_command()}"
                ) from e
            raise

    async def _is_chrome_running(self) -> bool:
        """Check if Chrome is running with debugging port open"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://{self.host}:{self.port}/json/version", timeout=2) as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def _launch_chrome(self):
        """Launch Chrome with CDP enabled"""
        cmd = self._get_chrome_launch_command()

        try:
            # Launch Chrome in background
            subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"Launched Chrome with CDP on port {self.port}")
        except Exception as e:
            logger.error(f"Failed to launch Chrome: {e}")
            raise

    def _get_chrome_launch_command(self) -> str:
        """Get the command to launch Chrome with remote debugging"""
        system = platform.system()

        # Build flags
        flags = [f"--remote-debugging-port={self.port}"]

        # Add user data dir if specified
        if self.user_data_dir:
            flags.append(f'--user-data-dir="{self.user_data_dir}"')

        flags_str = " ".join(flags)

        if system == "Windows":
            chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
            return f'"{chrome_path}" {flags_str}'
        elif system == "Darwin":  # macOS
            chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            return f'"{chrome_path}" {flags_str} &'
        else:  # Linux
            return f"google-chrome {flags_str} &"

    async def disconnect(self):
        """Disconnect from browser (doesn't close Chrome itself)"""
        if self._browser:
            await self._browser.close()
        if self.playwright:
            await self.playwright.stop()

        self._browser = None
        self._context = None
        self._page = None
        logger.info("Disconnected from browser")

    @staticmethod
    async def auto_discover(ports: List[int] = None) -> Optional['CDPBrowserConnector']:
        """
        Auto-discover Chrome debugging port.

        Args:
            ports: List of ports to check (default: [9222, 9223, 9224])

        Returns:
            CDPBrowserConnector instance if Chrome found, None otherwise
        """
        if ports is None:
            ports = [9222, 9223, 9224, 9229]

        for port in ports:
            connector = CDPBrowserConnector(port=port)
            if await connector._is_chrome_running():
                logger.info(f"Found Chrome on port {port}")
                return connector

        logger.warning(f"No Chrome found on ports {ports}")
        return None

    @staticmethod
    def get_launch_instructions() -> str:
        """Get user-friendly instructions for launching Chrome with CDP"""
        system = platform.system()

        if system == "Windows":
            return """
To launch Chrome with debugging enabled on Windows:

1. Close all Chrome windows
2. Open Command Prompt or PowerShell
3. Run:
   "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222

Or use CDPBrowserConnector with auto_launch=True
"""
        elif system == "Darwin":
            return """
To launch Chrome with debugging enabled on macOS:

1. Close all Chrome windows
2. Open Terminal
3. Run:
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 &

Or use CDPBrowserConnector with auto_launch=True
"""
        else:
            return """
To launch Chrome with debugging enabled on Linux:

1. Close all Chrome windows
2. Open Terminal
3. Run:
   google-chrome --remote-debugging-port=9222 &

Or use CDPBrowserConnector with auto_launch=True
"""


# Convenience functions

async def connect_to_existing_chrome(port: int = 9222) -> Optional[CDPBrowserInstance]:
    """
    Quick helper to connect to existing Chrome.

    Example:
        browser = await connect_to_existing_chrome(9222)
        if browser:
            await browser.goto("https://mail.google.com")  # Already logged in!

    Args:
        port: Chrome debugging port

    Returns:
        CDPBrowserInstance or None if connection fails
    """
    connector = CDPBrowserConnector(port=port)
    try:
        return await connector.connect()
    except ConnectionError:
        logger.error(f"Could not connect to Chrome on port {port}")
        logger.info(CDPBrowserConnector.get_launch_instructions())
        return None


async def auto_connect_chrome(auto_launch: bool = True) -> Optional[CDPBrowserInstance]:
    """
    Auto-discover and connect to Chrome, optionally launching if not running.

    Example:
        browser = await auto_connect_chrome(auto_launch=True)
        await browser.goto("https://example.com")

    Args:
        auto_launch: Launch Chrome if not running

    Returns:
        CDPBrowserInstance or None if connection fails
    """
    # Try auto-discovery first
    connector = await CDPBrowserConnector.auto_discover()

    # If not found and auto_launch enabled, launch on default port
    if not connector and auto_launch:
        connector = CDPBrowserConnector(port=9222, auto_launch=True)

    if connector:
        return await connector.connect()

    return None


# Testing CLI
async def _test_cdp_connector():
    """Test CDP connector"""
    print("=" * 60)
    print("CDP Browser Connector Test")
    print("=" * 60)

    # Test 1: Check if Chrome is running
    print("\n1. Checking for existing Chrome instances...")
    connector = await CDPBrowserConnector.auto_discover()

    if connector:
        print(f"   Found Chrome on port {connector.port}")

        # Try to connect
        print("\n2. Connecting to Chrome...")
        try:
            browser = await connector.connect()
            print(f"   Connected! Current URL: {browser.page.url}")

            # Test snapshot
            print("\n3. Taking snapshot...")
            snapshot = await browser.browser_snapshot()
            if "elements" in snapshot:
                print(f"   Found {snapshot['count']} interactive elements")
                # Show first 5 elements
                for el in snapshot['elements'][:5]:
                    print(f"     - {el['mmid']}: {el['role']} - {el['text'][:50]}")

            # Cleanup
            await connector.disconnect()
            print("\n4. Disconnected")

        except Exception as e:
            print(f"   Error: {e}")
    else:
        print("   No Chrome found")
        print("\n" + CDPBrowserConnector.get_launch_instructions())

    print("\n" + "=" * 60)
    print("Test complete!")


if __name__ == "__main__":
    asyncio.run(_test_cdp_connector())
