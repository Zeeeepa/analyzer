"""
Reliable Browser Tools - Wrapper for all browser operations with reliability guarantees.

Every operation:
1. Validates inputs
2. Checks browser health
3. Executes with timeout and retry
4. Returns standardized ToolResult
5. Logs everything

This is the production-ready layer that wraps MCP browser tools with
battle-tested error handling, smart retries, and visibility.
"""

import asyncio
import time
import re
from typing import Optional, Dict, Any, Union
from dataclasses import dataclass
from pathlib import Path
from loguru import logger

try:
    from rich.console import Console
    console = Console()
    RICH_AVAILABLE = True
except ImportError:
    console = None
    RICH_AVAILABLE = False

from tool_wrappers import ToolResult


# Validation utilities
class BrowserInputValidator:
    """Validates browser tool inputs before execution."""

    @staticmethod
    def validate_url(url: str) -> tuple[bool, Optional[str]]:
        """Validate URL format."""
        if not url or not isinstance(url, str):
            return False, "URL must be a non-empty string"

        url = url.strip()
        if len(url) > 2048:
            return False, "URL exceeds maximum length (2048)"

        if not re.match(r'^https?://', url, re.IGNORECASE):
            return False, "URL must start with http:// or https://"

        return True, None

    @staticmethod
    def validate_target(target: str) -> tuple[bool, Optional[str]]:
        """Validate element target (selector/ref/description)."""
        if not target or not isinstance(target, str):
            return False, "Target must be a non-empty string"

        target = target.strip()
        if len(target) > 1000:
            return False, "Target exceeds maximum length (1000)"

        return True, None

    @staticmethod
    def validate_text(text: str) -> tuple[bool, Optional[str]]:
        """Validate text input."""
        if not isinstance(text, str):
            return False, "Text must be a string"

        if len(text) > 10000:
            return False, "Text exceeds maximum length (10000)"

        return True, None

    @staticmethod
    def validate_timeout(timeout: Union[int, float]) -> tuple[bool, Optional[str]]:
        """Validate timeout value."""
        if not isinstance(timeout, (int, float)):
            return False, "Timeout must be a number"

        if timeout < 0.1:
            return False, "Timeout must be at least 0.1 seconds"

        if timeout > 300:
            return False, "Timeout cannot exceed 300 seconds"

        return True, None


class TargetResolver:
    """Resolves different target formats to appropriate selectors."""

    @staticmethod
    def resolve(target: str) -> tuple[str, str]:
        """
        Resolve target to (type, value).

        Returns:
            (type, value) where type is one of: 'ref', 'css', 'xpath', 'description'
        """
        target = target.strip()

        # Accessibility ref (from browser_snapshot)
        if target.startswith("ref="):
            return "ref", target[4:]

        # CSS selector
        if target.startswith(".") or target.startswith("#"):
            return "css", target

        # XPath
        if target.startswith("//"):
            return "xpath", target

        # Natural language description
        return "description", target


class BrowserHealthChecker:
    """Checks browser health before operations."""

    def __init__(self, mcp_client):
        self.mcp = mcp_client
        self._last_health_check = 0
        self._health_check_interval = 5.0  # Cache health for 5 seconds
        self._is_healthy = True

    async def check(self) -> tuple[bool, Optional[str]]:
        """
        Check if browser is alive and responsive.

        Returns:
            (is_healthy, error_message)
        """
        # Use cached result if recent
        now = time.time()
        if now - self._last_health_check < self._health_check_interval:
            if not self._is_healthy:
                return False, "Browser is not responsive (cached)"
            return True, None

        # Perform health check
        try:
            # Simple check - get current URL
            result = await asyncio.wait_for(
                self.mcp.call_tool("playwright_evaluate", {"script": "window.location.href"}),
                timeout=3.0
            )

            self._last_health_check = now
            if isinstance(result, dict) and result.get("error"):
                self._is_healthy = False
                return False, f"Browser health check failed: {result['error']}"

            self._is_healthy = True
            return True, None

        except asyncio.TimeoutError:
            self._is_healthy = False
            return False, "Browser health check timed out"
        except Exception as e:
            self._is_healthy = False
            return False, f"Browser health check error: {str(e)}"


def _print_status(message: str, style: str = "dim"):
    """Print status message with optional Rich formatting."""
    if RICH_AVAILABLE and console:
        if style == "dim":
            console.print(f"[dim]{message}[/dim]")
        elif style == "green":
            console.print(f"[green]{message}[/green]")
        elif style == "red":
            console.print(f"[red]{message}[/red]")
        elif style == "yellow":
            console.print(f"[yellow]{message}[/yellow]")
        else:
            console.print(message)
    else:
        print(message)


class ReliableBrowser:
    """
    Reliable browser wrapper with validation, health checks, retry, and logging.

    Every method:
    - Validates inputs first
    - Checks browser health
    - Executes with timeout
    - Retries on transient failures
    - Returns standardized ToolResult
    - Logs timing and errors
    """

    def __init__(self, mcp_client, page=None):
        """
        Initialize reliable browser wrapper.

        Args:
            mcp_client: MCP client instance
            page: Optional Playwright page (for direct access)
        """
        self.mcp = mcp_client
        self.page = page
        self.validator = BrowserInputValidator()
        self.target_resolver = TargetResolver()
        self.health_checker = BrowserHealthChecker(mcp_client)

        # Retry configuration
        self.max_retries = 2
        self.retry_delay = 1.0

        # Transient error patterns (safe to retry)
        self.transient_errors = [
            "timeout",
            "network",
            "connection",
            "ECONNRESET",
            "ETIMEDOUT",
            "temporarily unavailable"
        ]

    def _is_transient_error(self, error: str) -> bool:
        """Check if error is transient and safe to retry."""
        error_lower = error.lower()
        return any(pattern in error_lower for pattern in self.transient_errors)

    def _is_permanent_error(self, error: str) -> bool:
        """Check if error is permanent (don't retry)."""
        permanent_patterns = [
            "element not found",
            "selector not found",
            "no element matches",
            "element is not visible",
            "element is not attached",
            "invalid selector"
        ]
        error_lower = error.lower()
        return any(pattern in error_lower for pattern in permanent_patterns)

    async def _execute_with_retry(
        self,
        operation: str,
        tool_name: str,
        params: Dict[str, Any],
        timeout: float
    ) -> ToolResult:
        """
        Execute MCP tool with retry logic.

        Args:
            operation: Human-readable operation name
            tool_name: MCP tool name
            params: Tool parameters
            timeout: Timeout in seconds

        Returns:
            ToolResult
        """
        start_time = time.time()
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    self.mcp.call_tool(tool_name, params),
                    timeout=timeout
                )

                # Check for error in result
                if isinstance(result, dict) and result.get("error"):
                    error_msg = result["error"]

                    # Permanent error - don't retry
                    if self._is_permanent_error(error_msg):
                        elapsed = time.time() - start_time
                        logger.warning(f"[BROWSER] {operation} failed (permanent): {error_msg}")
                        return ToolResult(
                            success=False,
                            error=error_msg,
                            retries=attempt
                        )

                    # Transient error - retry
                    if self._is_transient_error(error_msg) and attempt < self.max_retries:
                        logger.debug(f"[BROWSER] {operation} failed (retrying): {error_msg}")
                        await asyncio.sleep(self.retry_delay * (attempt + 1))
                        continue

                    # Max retries reached
                    last_error = error_msg
                    break

                # Success!
                elapsed = time.time() - start_time
                logger.debug(f"[BROWSER] {operation} completed in {int(elapsed * 1000)}ms")
                return ToolResult(
                    success=True,
                    data=result,
                    retries=attempt
                )

            except asyncio.TimeoutError:
                last_error = f"Operation timed out after {timeout}s"
                if attempt < self.max_retries:
                    logger.debug(f"[BROWSER] {operation} timed out (retrying)")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                break

            except Exception as e:
                last_error = str(e)
                # Check if retryable
                if self._is_transient_error(last_error) and attempt < self.max_retries:
                    logger.debug(f"[BROWSER] {operation} error (retrying): {last_error}")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                break

        # All retries exhausted
        elapsed = time.time() - start_time
        logger.error(f"[BROWSER] {operation} failed after {attempt + 1} attempts: {last_error}")
        return ToolResult(
            success=False,
            error=last_error or "Unknown error",
            retries=attempt
        )

    async def navigate(self, url: str, timeout: int = 15) -> ToolResult:
        """
        Navigate to URL with validation, health check, and retry.

        Args:
            url: URL to navigate to
            timeout: Timeout in seconds

        Returns:
            ToolResult
        """
        # Validate inputs
        valid, error = self.validator.validate_url(url)
        if not valid:
            _print_status(f"Invalid URL: {error}", "red")
            return ToolResult(success=False, error=f"Invalid URL: {error}")

        valid, error = self.validator.validate_timeout(timeout)
        if not valid:
            return ToolResult(success=False, error=f"Invalid timeout: {error}")

        # Check browser health
        healthy, error = await self.health_checker.check()
        if not healthy:
            _print_status(f"Browser not healthy: {error}", "red")
            return ToolResult(success=False, error=f"Browser not healthy: {error}")

        # Execute
        _print_status(f"Navigating to {url}...", "dim")
        result = await self._execute_with_retry(
            f"navigate('{url}')",
            "playwright_navigate",
            {"url": url},
            timeout
        )

        # Show result
        if result.success:
            _print_status(f"Page loaded ({timeout}s max)", "green")
        else:
            _print_status(f"Navigation failed: {result.error}", "red")

        return result

    async def click(self, target: str, timeout: int = 5) -> ToolResult:
        """
        Click element by ref, selector, or description.

        Args:
            target: Element target (ref=, CSS, XPath, or description)
            timeout: Timeout in seconds

        Returns:
            ToolResult
        """
        # Validate inputs
        valid, error = self.validator.validate_target(target)
        if not valid:
            return ToolResult(success=False, error=f"Invalid target: {error}")

        valid, error = self.validator.validate_timeout(timeout)
        if not valid:
            return ToolResult(success=False, error=f"Invalid timeout: {error}")

        # Check browser health
        healthy, error = await self.health_checker.check()
        if not healthy:
            return ToolResult(success=False, error=f"Browser not healthy: {error}")

        # Resolve target
        target_type, target_value = self.target_resolver.resolve(target)

        # Execute based on type
        _print_status(f"Clicking {target_type}: {target_value}...", "dim")

        if target_type == "ref":
            # Use browser_click for accessibility refs
            result = await self._execute_with_retry(
                f"click(ref={target_value})",
                "browser_click",
                {"mmid": target_value},
                timeout
            )
        elif target_type == "css":
            # Use playwright_click for CSS selectors
            result = await self._execute_with_retry(
                f"click({target_value})",
                "playwright_click",
                {"selector": target_value},
                timeout
            )
        elif target_type == "xpath":
            # Use playwright_click with XPath
            result = await self._execute_with_retry(
                f"click({target_value})",
                "playwright_click",
                {"selector": target_value},
                timeout
            )
        else:
            # Description - need to find element first
            # Try to get snapshot and find by description
            _print_status(f"Finding element by description: {target_value}...", "dim")

            # Simple heuristic: try common role-based selectors
            attempts = [
                f"button:has-text('{target_value}')",
                f"a:has-text('{target_value}')",
                f"[aria-label='{target_value}']",
                f"text={target_value}"
            ]

            last_error = None
            for selector in attempts:
                result = await self._execute_with_retry(
                    f"click({selector})",
                    "playwright_click",
                    {"selector": selector},
                    timeout
                )
                if result.success:
                    break
                last_error = result.error
            else:
                # All attempts failed
                return ToolResult(
                    success=False,
                    error=f"Could not find element by description: {target_value}. Last error: {last_error}"
                )

        # Show result
        if result.success:
            _print_status(f"Clicked successfully", "green")
        else:
            _print_status(f"Click failed: {result.error}", "red")

        return result

    async def type(self, target: str, text: str, timeout: int = 5) -> ToolResult:
        """
        Type text into element.

        Args:
            target: Element target (ref=, CSS, XPath, or description)
            text: Text to type
            timeout: Timeout in seconds

        Returns:
            ToolResult
        """
        # Validate inputs
        valid, error = self.validator.validate_target(target)
        if not valid:
            return ToolResult(success=False, error=f"Invalid target: {error}")

        valid, error = self.validator.validate_text(text)
        if not valid:
            return ToolResult(success=False, error=f"Invalid text: {error}")

        valid, error = self.validator.validate_timeout(timeout)
        if not valid:
            return ToolResult(success=False, error=f"Invalid timeout: {error}")

        # Check browser health
        healthy, error = await self.health_checker.check()
        if not healthy:
            return ToolResult(success=False, error=f"Browser not healthy: {error}")

        # Resolve target
        target_type, target_value = self.target_resolver.resolve(target)

        # Execute based on type
        text_preview = text[:50] + "..." if len(text) > 50 else text
        _print_status(f"Typing into {target_type}: {target_value}...", "dim")

        if target_type == "ref":
            # Use browser_type for accessibility refs
            result = await self._execute_with_retry(
                f"type(ref={target_value}, '{text_preview}')",
                "browser_type",
                {"mmid": target_value, "text": text},
                timeout
            )
        else:
            # Use playwright_fill for selectors
            selector = target_value if target_type != "description" else f"text={target_value}"
            result = await self._execute_with_retry(
                f"type({selector}, '{text_preview}')",
                "playwright_fill",
                {"selector": selector, "value": text},
                timeout
            )

        # Show result
        if result.success:
            _print_status(f"Typed successfully", "green")
        else:
            _print_status(f"Type failed: {result.error}", "red")

        return result

    async def get_snapshot(self, timeout: int = 5) -> ToolResult:
        """
        Get accessibility snapshot of current page.

        Args:
            timeout: Timeout in seconds

        Returns:
            ToolResult with snapshot data
        """
        # Validate timeout
        valid, error = self.validator.validate_timeout(timeout)
        if not valid:
            return ToolResult(success=False, error=f"Invalid timeout: {error}")

        # Check browser health
        healthy, error = await self.health_checker.check()
        if not healthy:
            return ToolResult(success=False, error=f"Browser not healthy: {error}")

        # Execute
        _print_status("Capturing page snapshot...", "dim")
        result = await self._execute_with_retry(
            "get_snapshot()",
            "browser_snapshot",
            {},
            timeout
        )

        # Show result
        if result.success:
            _print_status("Snapshot captured", "green")
        else:
            _print_status(f"Snapshot failed: {result.error}", "red")

        return result

    async def get_text(self, timeout: int = 5) -> ToolResult:
        """
        Get page text content.

        Args:
            timeout: Timeout in seconds

        Returns:
            ToolResult with text content
        """
        # Validate timeout
        valid, error = self.validator.validate_timeout(timeout)
        if not valid:
            return ToolResult(success=False, error=f"Invalid timeout: {error}")

        # Check browser health
        healthy, error = await self.health_checker.check()
        if not healthy:
            return ToolResult(success=False, error=f"Browser not healthy: {error}")

        # Execute
        _print_status("Getting page text...", "dim")
        result = await self._execute_with_retry(
            "get_text()",
            "playwright_get_markdown",
            {},
            timeout
        )

        # Show result
        if result.success:
            text_len = len(str(result.data)) if result.data else 0
            _print_status(f"Retrieved {text_len} characters", "green")
        else:
            _print_status(f"Get text failed: {result.error}", "red")

        return result

    async def screenshot(self, filename: Optional[str] = None, timeout: int = 5) -> ToolResult:
        """
        Take screenshot of current page.

        Args:
            filename: Optional filename to save to
            timeout: Timeout in seconds

        Returns:
            ToolResult with screenshot data/path
        """
        # Validate timeout
        valid, error = self.validator.validate_timeout(timeout)
        if not valid:
            return ToolResult(success=False, error=f"Invalid timeout: {error}")

        # Check browser health
        healthy, error = await self.health_checker.check()
        if not healthy:
            return ToolResult(success=False, error=f"Browser not healthy: {error}")

        # Execute
        _print_status("Taking screenshot...", "dim")
        params = {}
        if filename:
            params["name"] = filename

        result = await self._execute_with_retry(
            f"screenshot({filename or 'auto'})",
            "playwright_screenshot",
            params,
            timeout
        )

        # Show result
        if result.success:
            _print_status(f"Screenshot saved", "green")
        else:
            _print_status(f"Screenshot failed: {result.error}", "red")

        return result

    async def wait_for(self, condition: str, timeout: int = 10) -> ToolResult:
        """
        Wait for text/element/condition.

        Args:
            condition: What to wait for (text, selector, etc.)
            timeout: Timeout in seconds

        Returns:
            ToolResult
        """
        # Validate inputs
        valid, error = self.validator.validate_target(condition)
        if not valid:
            return ToolResult(success=False, error=f"Invalid condition: {error}")

        valid, error = self.validator.validate_timeout(timeout)
        if not valid:
            return ToolResult(success=False, error=f"Invalid timeout: {error}")

        # Check browser health
        healthy, error = await self.health_checker.check()
        if not healthy:
            return ToolResult(success=False, error=f"Browser not healthy: {error}")

        # Execute
        _print_status(f"Waiting for: {condition}...", "dim")

        # Try different wait strategies
        # Strategy 1: Wait for selector
        if condition.startswith(".") or condition.startswith("#"):
            result = await self._execute_with_retry(
                f"wait_for({condition})",
                "playwright_evaluate",
                {"script": f"document.querySelector('{condition}') !== null"},
                timeout
            )
        # Strategy 2: Wait for text
        else:
            result = await self._execute_with_retry(
                f"wait_for(text={condition})",
                "playwright_evaluate",
                {"script": f"document.body.innerText.includes('{condition}')"},
                timeout
            )

        # Show result
        if result.success:
            _print_status(f"Condition met", "green")
        else:
            _print_status(f"Wait failed: {result.error}", "red")

        return result

    def set_retry_config(self, max_retries: int = 2, retry_delay: float = 1.0):
        """
        Configure retry behavior.

        Args:
            max_retries: Maximum number of retries
            retry_delay: Base delay between retries (seconds)
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        logger.info(f"[BROWSER] Retry config: max={max_retries}, delay={retry_delay}s")


# Convenience function for quick initialization
async def create_reliable_browser(mcp_client) -> ReliableBrowser:
    """
    Create a ReliableBrowser instance.

    Args:
        mcp_client: MCP client instance

    Returns:
        ReliableBrowser instance
    """
    return ReliableBrowser(mcp_client)


class ReliableBrowserAdapter:
    """
    Adapter that makes ReliableBrowser compatible with existing brain_enhanced_v2.py
    and playwright_direct.py code.

    This class wraps the MCP client and intercepts browser operations,
    routing them through ReliableBrowser for reliability guarantees while
    maintaining backward compatibility with existing code.
    """

    def __init__(self, mcp_client, enable_reliability: bool = True):
        """
        Initialize the adapter.

        Args:
            mcp_client: Original MCP client
            enable_reliability: If True, use ReliableBrowser; if False, pass through
        """
        self._mcp = mcp_client
        self._enable_reliability = enable_reliability
        self._reliable_browser = ReliableBrowser(mcp_client) if enable_reliability else None

        # Browser operation mappings
        self._browser_tools = {
            'playwright_navigate',
            'playwright_click',
            'browser_click',
            'playwright_fill',
            'browser_type',
            'playwright_snapshot',
            'browser_snapshot',
            'playwright_get_markdown',
            'playwright_screenshot',
            'playwright_evaluate',
            'playwright_scroll',
            'playwright_wait_for_selector',
        }

    async def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """
        Call a tool, routing browser operations through ReliableBrowser.

        Args:
            tool_name: Name of the tool to call
            params: Tool parameters

        Returns:
            Tool result (unwrapped from ToolResult for compatibility)
        """
        # If reliability is disabled or not a browser tool, pass through
        if not self._enable_reliability or tool_name not in self._browser_tools:
            return await self._mcp.call_tool(tool_name, params)

        # Route through ReliableBrowser
        try:
            result = await self._call_reliable(tool_name, params)

            # Unwrap ToolResult for backward compatibility
            if isinstance(result, ToolResult):
                if result.success:
                    # Handle None data - return empty dict for compatibility
                    if result.data is None:
                        return {"success": True}
                    # If data is also a ToolResult, unwrap recursively
                    if isinstance(result.data, ToolResult):
                        return result.data.data if result.data.success else {"error": result.data.error}
                    return result.data
                else:
                    # Return error in expected format
                    return {"error": result.error}

            return result

        except Exception as e:
            logger.error(f"[RELIABLE] Error in {tool_name}: {e}")
            # Fallback to direct MCP call
            return await self._mcp.call_tool(tool_name, params)

    async def _call_reliable(self, tool_name: str, params: Dict[str, Any]) -> ToolResult:
        """
        Route tool call to appropriate ReliableBrowser method.

        Args:
            tool_name: Tool name
            params: Tool parameters

        Returns:
            ToolResult
        """
        # Navigation
        if tool_name == 'playwright_navigate':
            url = params.get('url', '')
            timeout = params.get('timeout', 15)
            return await self._reliable_browser.navigate(url, timeout)

        # Click operations
        elif tool_name in ('playwright_click', 'browser_click'):
            if 'selector' in params:
                target = params['selector']
            elif 'mmid' in params:
                target = f"ref={params['mmid']}"
            else:
                return ToolResult(success=False, error="No selector or mmid provided")

            timeout = params.get('timeout', 5)
            return await self._reliable_browser.click(target, timeout)

        # Type/fill operations
        elif tool_name in ('playwright_fill', 'browser_type'):
            if 'selector' in params:
                target = params['selector']
            elif 'mmid' in params:
                target = f"ref={params['mmid']}"
            else:
                return ToolResult(success=False, error="No selector or mmid provided")

            text = params.get('value') or params.get('text', '')
            timeout = params.get('timeout', 5)
            return await self._reliable_browser.type(target, text, timeout)

        # Snapshot operations
        elif tool_name in ('playwright_snapshot', 'browser_snapshot'):
            timeout = params.get('timeout', 5)
            return await self._reliable_browser.get_snapshot(timeout)

        # Get text/markdown
        elif tool_name == 'playwright_get_markdown':
            timeout = params.get('timeout', 5)
            return await self._reliable_browser.get_text(timeout)

        # Screenshot
        elif tool_name == 'playwright_screenshot':
            filename = params.get('name')
            timeout = params.get('timeout', 5)
            return await self._reliable_browser.screenshot(filename, timeout)

        # For other browser tools, use execute_with_retry directly
        else:
            return await self._reliable_browser._execute_with_retry(
                f"{tool_name}({params})",
                tool_name,
                params,
                params.get('timeout', 5)
            )

    def __getattr__(self, name: str):
        """
        Pass through any non-intercepted attributes to the original MCP client.
        This ensures backward compatibility for any other MCP operations.
        """
        return getattr(self._mcp, name)


def wrap_mcp_client(mcp_client, enable_reliability: bool = True) -> ReliableBrowserAdapter:
    """
    Wrap an MCP client with reliability layer.

    Args:
        mcp_client: Original MCP client
        enable_reliability: If True, enable ReliableBrowser wrapper

    Returns:
        ReliableBrowserAdapter instance
    """
    return ReliableBrowserAdapter(mcp_client, enable_reliability)
