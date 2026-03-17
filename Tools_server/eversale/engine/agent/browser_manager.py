"""
Browser Manager - Handles browser lifecycle and screenshot management.

Extracted from brain_enhanced_v2.py to reduce file size and improve modularity.
Contains:
- Browser health checks and recovery
- Screenshot capture and tracking
- Vision analysis integration
- Cascading recovery for browser operations
- Continuous perception (human-like visual awareness)
"""

import asyncio
import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from ollama import Client as OllamaClient
    # DEPRECATED: cascading_recovery removed in v2.9
    try:
        from .cascading_recovery import CascadingRecoverySystem, RecoveryContext
    except ImportError:
        CascadingRecoverySystem = None
        RecoveryContext = None

# Import continuous perception (human-like visual awareness)
# Import directly from module file to avoid scipy dependency in other humanization modules
PERCEPTION_AVAILABLE = False
ContinuousPerception = None
PerceptionState = None
PerceptionConfig = None

try:
    # Direct import from file to avoid __init__.py pulling in scipy-dependent modules
    import importlib.util
    import os
    perception_path = os.path.join(os.path.dirname(__file__), 'humanization', 'continuous_perception.py')
    if os.path.exists(perception_path):
        spec = importlib.util.spec_from_file_location("continuous_perception", perception_path)
        perception_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(perception_module)
        ContinuousPerception = perception_module.ContinuousPerception
        PerceptionState = perception_module.PerceptionState
        PerceptionConfig = perception_module.PerceptionConfig
        PERCEPTION_AVAILABLE = True
except Exception as e:
    logger.debug(f"Continuous perception not available: {e}")


# =============================================================================
# Obstruction Detection and Handling
# =============================================================================

@dataclass
class ObstructionInfo:
    """Information about a detected page obstruction."""
    type: str  # "modal", "cookie_banner", "chat_widget", "fixed_header", "popup"
    selector: str  # CSS selector for the obstruction element
    z_index: int  # Z-index of the element
    covers_percent: float  # Percentage of viewport covered
    dismissible: bool  # Whether the obstruction can be dismissed
    dismiss_method: Optional[str] = None  # "click_close", "press_esc", "click_outside"
    dismiss_selector: Optional[str] = None  # Selector for dismiss button


# Common patterns for detecting obstructions
OBSTRUCTION_PATTERNS = {
    "cookie_banner": {
        "selectors": [
            "[class*='cookie' i]",
            "[id*='cookie' i]",
            "[class*='consent' i]",
            "[id*='consent' i]",
            "[class*='gdpr' i]",
            ".cc-banner",
            "#cookieNotice",
            "[class*='CookieConsent' i]",
            "[aria-label*='cookie' i]",
            "[role='dialog'][class*='cookie' i]",
        ],
        "dismiss": [
            "[class*='accept' i]",
            "[class*='agree' i]",
            "[class*='allow' i]",
            "button:has-text('Accept')",
            "button:has-text('Agree')",
            "button:has-text('Allow')",
            "button:has-text('OK')",
            ".cookie-accept",
            "#cookie-accept",
        ],
        "priority": 1,  # High priority - always dismiss
    },
    "modal": {
        "selectors": [
            "[class*='modal' i]:visible",
            "[role='dialog']:visible",
            "[class*='popup' i]:visible",
            "[class*='overlay' i]:visible",
            "[aria-modal='true']",
            ".modal.show",
            ".modal.is-active",
            "[class*='lightbox' i]:visible",
        ],
        "dismiss": [
            ".close",
            ".modal-close",
            "[aria-label='Close' i]",
            "[aria-label='Dismiss' i]",
            "button:has-text('×')",
            "button:has-text('Close')",
            "[class*='close' i]",
            "[data-dismiss='modal']",
        ],
        "priority": 2,  # Medium-high priority
    },
    "chat_widget": {
        "selectors": [
            "[class*='intercom' i]",
            "[class*='drift' i]",
            "[class*='zendesk' i]",
            "[class*='chat-widget' i]",
            "[class*='livechat' i]",
            "#hubspot-messages-iframe-container",
            "[class*='crisp' i]",
            "[id*='chat-widget' i]",
        ],
        "dismiss": [
            "[class*='minimize' i]",
            "[class*='close' i]",
            "[aria-label='Close chat' i]",
            "[aria-label='Minimize chat' i]",
        ],
        "priority": 3,  # Lower priority - only if blocking
    },
    "fixed_header": {
        "selectors": [
            "header[style*='fixed']",
            "[class*='sticky-header' i]",
            "[class*='fixed-header' i]",
            "header[class*='sticky' i]",
        ],
        "dismiss": None,  # Can't dismiss, need to scroll past
        "priority": 4,  # Lowest - usually not blocking
    },
    "newsletter_popup": {
        "selectors": [
            "[class*='newsletter' i][class*='popup' i]",
            "[class*='subscribe' i][class*='modal' i]",
            "[class*='email-signup' i]:visible",
            "[id*='newsletter-modal' i]",
        ],
        "dismiss": [
            ".close",
            "[aria-label='Close' i]",
            "button:has-text('No thanks')",
            "button:has-text('Maybe later')",
            "[class*='close' i]",
        ],
        "priority": 2,
    },
    "age_verification": {
        "selectors": [
            "[class*='age-gate' i]",
            "[class*='age-verification' i]",
            "[id*='age-verify' i]",
        ],
        "dismiss": [
            "button:has-text('Yes')",
            "button:has-text('Enter')",
            "button:has-text('I am 18')",
            "[class*='confirm' i]",
        ],
        "priority": 1,  # High priority
    },
}


class BrowserManager:
    """
    Manages browser lifecycle, health checks, and screenshot operations.

    Responsibilities:
    - Browser health monitoring and automatic reconnection
    - Screenshot capture, tracking, and change detection
    - Vision model analysis of screenshots
    - Cascading recovery for failed browser operations
    """

    # Actions that should change the page state
    ACTIONS_EXPECTED_CHANGE: Set[str] = {'playwright_navigate', 'playwright_click'}

    def __init__(
        self,
        mcp_client,
        ollama_client: Optional["OllamaClient"] = None,
        vision_model: Optional[str] = None,
        cascading_recovery: Optional["CascadingRecoverySystem"] = None,
        profile_manager=None
    ):
        """
        Initialize the BrowserManager.

        Args:
            mcp_client: MCP client for browser operations
            ollama_client: Optional Ollama client for vision analysis
            vision_model: Optional vision model name (e.g., 'minicpm-v')
            cascading_recovery: Optional cascading recovery system
            profile_manager: Optional ProfileManager for session persistence
        """
        self.mcp = mcp_client
        self.ollama_client = ollama_client
        self.vision_model = vision_model
        self.cascading_recovery = cascading_recovery
        self.profile_manager = profile_manager

        # Browser reference (lazy initialized)
        self._browser = None
        self._current_profile: Optional[str] = None

        # Screenshot tracking state
        self._last_screenshot_hash: Optional[str] = None
        self._last_screenshot_issue: Optional[str] = None

        # Stats tracking
        self.stats = {
            'screenshots_taken': 0,
            'vision_calls': 0,
            'health_checks': 0,
            'reconnect_attempts': 0,
            'recovery_attempts': 0,
            'obstructions_detected': 0,
            'obstructions_dismissed': 0,
        }

        # Continuous perception (human-like visual awareness)
        self._perception: Optional["ContinuousPerception"] = None
        self._perception_enabled = PERCEPTION_AVAILABLE

        # Obstruction tracking
        self._dismissed_obstructions: Set[str] = set()  # Track dismissed to avoid re-dismissing
        self._obstruction_check_count = 0

    @property
    def browser(self):
        """
        Get browser from MCP client.

        IMPORTANT: Do NOT cache the browser reference!
        After browser reconnection, the MCP server has a new client instance.
        Caching would return a stale reference to the old, disconnected browser.

        Supports two MCP architectures:
        - New: Internal MCP server with client
        - Legacy: Separate playwright server
        """
        # Always fetch fresh reference from MCP server
        if hasattr(self.mcp, '_mcp_server') and self.mcp._mcp_server:
            return self.mcp._mcp_server.client
        # Fallback to old architecture (separate playwright server)
        elif hasattr(self.mcp, 'servers') and "playwright" in self.mcp.servers:
            return self.mcp.servers["playwright"].get("client")
        return None

    @property
    def last_screenshot_issue(self) -> Optional[str]:
        """Get the last screenshot issue (if any) and clear it."""
        issue = self._last_screenshot_issue
        self._last_screenshot_issue = None
        return issue

    # =========================================================================
    # Browser Health Management
    # =========================================================================

    async def ensure_browser_health(self) -> bool:
        """
        Check browser health and attempt reconnection if unhealthy.

        Returns:
            True if browser is healthy or no browser is configured,
            False if browser is unhealthy and reconnection failed.
        """
        if not self.browser:
            return True

        self.stats['health_checks'] += 1

        try:
            if await self.browser.is_healthy():
                return True
        except Exception as e:
            logger.warning(f"Browser health probe failed: {e}")

        logger.warning("Browser unhealthy; attempting reconnect.")
        self.stats['reconnect_attempts'] += 1

        try:
            return await self.browser.ensure_connected()
        except Exception as e:
            logger.error(f"Browser reconnect failed: {e}")
            return False

    async def get_page_url(self) -> Optional[str]:
        """Get the current page URL safely."""
        if not self.browser or not self.browser.page:
            return None
        try:
            return self.browser.page.url
        except Exception:
            return None

    # =========================================================================
    # Screenshot Management
    # =========================================================================

    async def take_screenshot(self) -> Optional[bytes]:
        """
        Take a screenshot of the current page.

        Returns:
            Screenshot bytes or None if capture failed.
        """
        if not self.browser:
            return None

        try:
            screenshot = await self.browser.page.screenshot()
            self.stats['screenshots_taken'] += 1
            return screenshot
        except Exception as e:
            logger.debug(f"Screenshot capture failed: {e}")
            return None

    async def capture_screenshot(self, tool_name: str, result: Any) -> Optional[bytes]:
        """
        Capture a screenshot, preferring tool-returned paths.

        Prefers the screenshot produced by the tool (if it saved a file),
        otherwise falls back to capturing the current page.

        Args:
            tool_name: Name of the tool that was executed
            result: Result from the tool execution

        Returns:
            Screenshot bytes or None if capture failed.
        """
        # Try to read the path the tool returned
        if isinstance(result, dict):
            path = result.get('filepath') or result.get('path')
            if path:
                try:
                    file_path = Path(path)
                    if file_path.exists():
                        return file_path.read_bytes()
                except Exception as e:
                    logger.debug(f"Could not read screenshot from {path}: {e}")

        # Fallback: take a fresh screenshot
        try:
            return await self.take_screenshot()
        except Exception as e:
            logger.debug(f"Fallback screenshot failed after {tool_name}: {e}")
            return None

    def record_screenshot_bytes(
        self,
        screenshot: Optional[bytes],
        action_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Track screenshot hashes and flag unexpected no-change scenarios.

        Detects when a page-changing action (like navigate or click) didn't
        actually change the page content, which may indicate a loading issue.

        Args:
            screenshot: Screenshot bytes to track
            action_name: Optional name of the action that produced this screenshot

        Returns:
            Issue string if screenshot unchanged after expected-change action,
            None otherwise.
        """
        if not screenshot:
            return None

        new_hash = hashlib.md5(screenshot).hexdigest()
        issue = None

        if (
            self._last_screenshot_hash
            and action_name
            and action_name in self.ACTIONS_EXPECTED_CHANGE
            and new_hash == self._last_screenshot_hash
        ):
            issue = f"Screenshot unchanged after {action_name}; page may not have loaded or changed."

        self._last_screenshot_hash = new_hash
        self._last_screenshot_issue = issue
        return issue

    # =========================================================================
    # Vision Analysis
    # =========================================================================

    async def vision_analyze(self, screenshot: bytes) -> Dict[str, Any]:
        """
        Use vision model to analyze screenshot.

        Analyzes the screenshot to detect:
        - Error messages
        - Task/form completion
        - General page content

        Args:
            screenshot: Screenshot bytes to analyze

        Returns:
            Dict with keys:
            - error_detected: bool
            - task_complete: bool
            - summary: str (truncated to 500 chars)
            - raw_summary: str (full text)
            Or empty dict / error dict if analysis failed.
        """
        if not self.vision_model:
            logger.warning("No vision model configured; skipping visual analysis")
            return {'error': 'vision model not configured'}

        if not self.ollama_client:
            logger.warning("No Ollama client configured; skipping visual analysis")
            return {'error': 'ollama client not configured'}

        try:
            # Encode screenshot
            b64 = base64.b64encode(screenshot).decode('utf-8')

            self.stats['vision_calls'] += 1

            response = self.ollama_client.chat(
                model=self.vision_model,
                messages=[{
                    'role': 'user',
                    'content': 'Analyze this screenshot. Is there an error message? Is a task/form complete? What do you see?',
                    'images': [b64]
                }],
                options={'temperature': 0.1}
            )

            content = response.get('message', {}).get('content', '')

            # Parse response
            error_words = ['error', 'failed', 'invalid', 'wrong', 'denied']
            complete_words = ['success', 'complete', 'submitted', 'thank you', 'confirmed']
            summary_full = content.strip()

            return {
                'error_detected': any(w in content.lower() for w in error_words),
                'task_complete': any(w in content.lower() for w in complete_words),
                'summary': summary_full[:500],
                'raw_summary': summary_full
            }

        except Exception as e:
            logger.warning(f"Vision analysis failed: {e}")
            return {}

    async def collect_vision_insight(
        self,
        results: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """
        Collect vision-based insight from existing or new screenshots.

        Tries to use existing screenshots from results first,
        then captures a fresh one if needed.

        Args:
            results: Optional list of ActionResult objects with screenshot attribute

        Returns:
            Vision analysis result dict or empty dict.
        """
        # Try to find existing screenshot in results
        screenshot = None
        if results:
            for r in reversed(results):
                if hasattr(r, 'screenshot') and r.screenshot:
                    screenshot = r.screenshot
                    break

        # Capture fresh if no existing screenshot
        if not screenshot and self.browser:
            screenshot = await self.take_screenshot()

        if screenshot:
            self.record_screenshot_bytes(screenshot, action_name=None)
            return await self.vision_analyze(screenshot)

        return {}

    # =========================================================================
    # Cascading Recovery
    # =========================================================================

    async def attempt_cascading_recovery(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        error: Exception,
        call_tool_func
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt recovery using the cascading recovery system.

        Args:
            tool_name: Name of the failed tool
            tool_args: Arguments that were passed to the tool
            error: The exception that occurred
            call_tool_func: Async function to call tools (e.g., mcp.call_tool)

        Returns:
            Recovery result dict if successful, None otherwise.
            May include 'partial' key with partial results if full recovery failed.
        """
        if not self.cascading_recovery:
            return None

        self.stats['recovery_attempts'] += 1

        try:
            # DEPRECATED: RecoveryContext removed in v2.9 - use fallback
            try:
                from .cascading_recovery import RecoveryContext
            except ImportError:
                # Fallback stub for RecoveryContext
                class RecoveryContext:
                    def __init__(self, **kwargs):
                        for k, v in kwargs.items():
                            setattr(self, k, v)

            # Get current page if available
            page = None
            if hasattr(self.mcp, 'page'):
                page = self.mcp.page

            # Create recovery context
            context = RecoveryContext(
                action=tool_name,
                arguments=tool_args,
                error=error,
                attempt_number=1,
                page_url=page.url if page else None
            )

            # Define retry action
            async def retry_action():
                return await asyncio.wait_for(
                    call_tool_func(tool_name, tool_args),
                    timeout=45
                )

            # Attempt recovery
            logger.info(f"[RECOVERY] Attempting cascading recovery for {tool_name}")
            recovery_result = await self.cascading_recovery.attempt_recovery(
                context=context,
                page=page,
                retry_action=retry_action
            )

            if recovery_result.get("recovered"):
                logger.info(f"[RECOVERY] Successfully recovered at level {recovery_result.get('level')}")
                return recovery_result.get("result")
            else:
                logger.warning(f"[RECOVERY] Recovery failed: {recovery_result.get('error', 'Unknown')}")
                # Check for partial results
                if recovery_result.get("partial_results"):
                    logger.info("[RECOVERY] Returning partial results")
                    return {"partial": True, "data": recovery_result.get("partial_results")}

        except ImportError:
            logger.debug("Cascading recovery module not available")
        except Exception as recovery_error:
            logger.error(f"[RECOVERY] Cascading recovery itself failed: {recovery_error}")

        return None

    # =========================================================================
    # DOM Feedback
    # =========================================================================

    async def fetch_dom_feedback(self) -> str:
        """
        Capture text/DOM feedback for heuristic checks.

        Returns:
            Page content string from snapshot or text extraction,
            or empty string if unavailable.
        """
        try:
            from .mcp_client import MCPClient
            snapshot = await self.mcp.call_tool('playwright_snapshot', {})
            parts = [
                snapshot.get('summary', ''),
                snapshot.get('snapshot', ''),
                snapshot.get('url', '')
            ]
            content = "\n".join(line for line in parts if line)
            if content:
                return content
        except Exception as e:
            logger.debug(f"Snapshot feedback unavailable: {e}")

        try:
            text_result = await self.mcp.call_tool('playwright_get_text', {'selector': 'body'})
            text = text_result.get('text') if isinstance(text_result, dict) else ''
            return text or ''
        except Exception as e:
            logger.debug(f"Text feedback unavailable: {e}")
            return ''

    def detect_text_issue(self, text: str) -> Optional[str]:
        """
        Detect common error indicators in page text.

        Args:
            text: Page text content to analyze

        Returns:
            Issue description string if error detected, None otherwise.
        """
        if not text:
            return None

        lower = text.lower()
        error_keywords = [
            'error', 'failed', 'please try again', 'temporarily down',
            '500', '503', 'not available', 'blocked', 'denied', 'timed out'
        ]

        for word in error_keywords:
            if word in lower:
                return f"Common sense check: page text mentions '{word}'. Investigate before proceeding."

        return None

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_stats(self) -> Dict[str, int]:
        """Get browser manager statistics."""
        return dict(self.stats)

    def reset_screenshot_tracking(self):
        """Reset screenshot tracking state."""
        self._last_screenshot_hash = None
        self._last_screenshot_issue = None

    # =========================================================================
    # Obstruction Detection and Handling
    # =========================================================================

    async def detect_obstructions(self) -> List[ObstructionInfo]:
        """
        Detect elements that might block interactions.

        Returns:
            List of ObstructionInfo objects for detected obstructions.
        """
        if not self.browser or not self.browser.page:
            return []

        obstructions = []
        page = self.browser.page

        try:
            # Get viewport size
            viewport = await page.evaluate('''() => ({
                width: window.innerWidth,
                height: window.innerHeight
            })''')
            viewport_area = viewport['width'] * viewport['height']

            # Check each obstruction pattern
            for obstruction_type, pattern in OBSTRUCTION_PATTERNS.items():
                for selector in pattern['selectors']:
                    try:
                        # Find elements matching this selector
                        elements = await page.query_selector_all(selector)

                        for element in elements:
                            # Check if element is visible
                            is_visible = await element.is_visible()
                            if not is_visible:
                                continue

                            # Get element properties
                            props = await page.evaluate('''(element) => {
                                const rect = element.getBoundingClientRect();
                                const style = window.getComputedStyle(element);
                                return {
                                    zIndex: style.zIndex,
                                    position: style.position,
                                    display: style.display,
                                    width: rect.width,
                                    height: rect.height,
                                    top: rect.top,
                                    left: rect.left,
                                    opacity: style.opacity,
                                };
                            }''', element)

                            # Calculate coverage percentage
                            element_area = props['width'] * props['height']
                            coverage = (element_area / viewport_area) * 100 if viewport_area > 0 else 0

                            # Parse z-index
                            try:
                                z_index = int(props['zIndex']) if props['zIndex'] != 'auto' else 0
                            except (ValueError, TypeError):
                                z_index = 0

                            # Only consider obstructions with high z-index or significant coverage
                            if z_index < 100 and coverage < 10:
                                continue

                            # Create unique ID for this obstruction
                            obstruction_id = f"{obstruction_type}_{selector}_{int(props['top'])}_{int(props['left'])}"

                            # Skip if already dismissed
                            if obstruction_id in self._dismissed_obstructions:
                                continue

                            # Find dismiss method
                            dismiss_method = None
                            dismiss_selector = None
                            dismissible = False

                            if pattern['dismiss']:
                                for dismiss_sel in pattern['dismiss']:
                                    try:
                                        dismiss_elem = await element.query_selector(dismiss_sel)
                                        if not dismiss_elem:
                                            # Try searching in parent container
                                            dismiss_elem = await page.query_selector(dismiss_sel)

                                        if dismiss_elem and await dismiss_elem.is_visible():
                                            dismiss_selector = dismiss_sel
                                            dismiss_method = "click_close"
                                            dismissible = True
                                            break
                                    except Exception:
                                        continue

                            # If no close button found, try ESC or click outside
                            if not dismissible and obstruction_type in ['modal', 'newsletter_popup']:
                                dismiss_method = "press_esc"
                                dismissible = True

                            obstruction = ObstructionInfo(
                                type=obstruction_type,
                                selector=selector,
                                z_index=z_index,
                                covers_percent=coverage,
                                dismissible=dismissible,
                                dismiss_method=dismiss_method,
                                dismiss_selector=dismiss_selector
                            )

                            obstructions.append(obstruction)
                            logger.debug(f"Detected {obstruction_type}: z={z_index}, coverage={coverage:.1f}%")

                    except Exception as e:
                        logger.debug(f"Error checking selector {selector}: {e}")
                        continue

        except Exception as e:
            logger.warning(f"Obstruction detection failed: {e}")

        # Sort by priority (lower number = higher priority)
        obstructions.sort(key=lambda x: OBSTRUCTION_PATTERNS[x.type]['priority'])

        self._obstruction_check_count += 1
        if obstructions:
            self.stats['obstructions_detected'] += len(obstructions)

        return obstructions

    async def dismiss_obstruction(self, obstruction: ObstructionInfo) -> bool:
        """
        Try to dismiss an obstruction.

        Args:
            obstruction: ObstructionInfo object to dismiss

        Returns:
            True if successfully dismissed, False otherwise.
        """
        if not self.browser or not self.browser.page:
            return False

        page = self.browser.page

        try:
            logger.info(f"Attempting to dismiss {obstruction.type} (method: {obstruction.dismiss_method})")

            if obstruction.dismiss_method == "click_close" and obstruction.dismiss_selector:
                # Click close button
                try:
                    close_button = await page.wait_for_selector(
                        obstruction.dismiss_selector,
                        timeout=2000,
                        state='visible'
                    )
                    if close_button:
                        await close_button.click()
                        await asyncio.sleep(0.5)  # Wait for animation
                        logger.info(f"Dismissed {obstruction.type} via close button")
                        self.stats['obstructions_dismissed'] += 1
                        return True
                except Exception as e:
                    logger.debug(f"Click close failed: {e}")

            if obstruction.dismiss_method == "press_esc":
                # Press ESC key
                try:
                    await page.keyboard.press('Escape')
                    await asyncio.sleep(0.5)
                    logger.info(f"Dismissed {obstruction.type} via ESC key")
                    self.stats['obstructions_dismissed'] += 1
                    return True
                except Exception as e:
                    logger.debug(f"ESC key failed: {e}")

            if obstruction.dismiss_method == "click_outside":
                # Click outside the obstruction
                try:
                    # Click at top-left corner (usually outside modal)
                    await page.mouse.click(10, 10)
                    await asyncio.sleep(0.5)
                    logger.info(f"Dismissed {obstruction.type} via outside click")
                    self.stats['obstructions_dismissed'] += 1
                    return True
                except Exception as e:
                    logger.debug(f"Outside click failed: {e}")

            # Try generic dismiss strategies
            if obstruction.type == "cookie_banner":
                # For cookie banners, try clicking Accept/Agree
                for selector in OBSTRUCTION_PATTERNS["cookie_banner"]["dismiss"]:
                    try:
                        button = await page.query_selector(selector)
                        if button and await button.is_visible():
                            await button.click()
                            await asyncio.sleep(0.5)
                            logger.info(f"Dismissed cookie banner via {selector}")
                            self.stats['obstructions_dismissed'] += 1
                            return True
                    except Exception:
                        continue

        except Exception as e:
            logger.warning(f"Failed to dismiss {obstruction.type}: {e}")

        return False

    async def scan_and_dismiss_obstructions(self, aggressive: bool = False) -> int:
        """
        Proactively find and dismiss all obstructions.

        Args:
            aggressive: If True, try to dismiss all obstructions including low-priority ones.
                       If False (default), only dismiss high-priority obstructions.

        Returns:
            Number of obstructions successfully dismissed.
        """
        if not self.browser or not self.browser.page:
            return 0

        dismissed_count = 0
        obstructions = await self.detect_obstructions()

        if not obstructions:
            return 0

        logger.info(f"Found {len(obstructions)} obstruction(s) on page")

        for obstruction in obstructions:
            # Skip low-priority unless aggressive mode
            if not aggressive and OBSTRUCTION_PATTERNS[obstruction.type]['priority'] > 2:
                logger.debug(f"Skipping low-priority {obstruction.type} (priority={OBSTRUCTION_PATTERNS[obstruction.type]['priority']})")
                continue

            # Skip if not dismissible
            if not obstruction.dismissible:
                logger.debug(f"Cannot dismiss {obstruction.type} - no dismiss method")
                continue

            # Try to dismiss
            if await self.dismiss_obstruction(obstruction):
                dismissed_count += 1
                # Mark as dismissed
                obstruction_id = f"{obstruction.type}_{obstruction.selector}"
                self._dismissed_obstructions.add(obstruction_id)

        if dismissed_count > 0:
            logger.info(f"Successfully dismissed {dismissed_count} obstruction(s)")

        return dismissed_count

    async def ensure_element_clickable(self, selector: str, timeout: int = 5000) -> bool:
        """
        Ensure element is not obstructed before click.

        Checks if the target element is covered by any obstructions,
        and tries to dismiss them if necessary.

        Args:
            selector: CSS selector for the target element
            timeout: Maximum time to wait for element (milliseconds)

        Returns:
            True if element is clickable, False if obstructed and couldn't clear.
        """
        if not self.browser or not self.browser.page:
            return False

        page = self.browser.page

        try:
            # Wait for element to exist
            element = await page.wait_for_selector(selector, timeout=timeout, state='attached')
            if not element:
                logger.warning(f"Element not found: {selector}")
                return False

            # Get element bounding box
            box = await element.bounding_box()
            if not box:
                logger.warning(f"Element has no bounding box: {selector}")
                return False

            # Get center coordinates
            center_x = box['x'] + box['width'] / 2
            center_y = box['y'] + box['height'] / 2

            # Check what element is at those coordinates
            top_element = await page.evaluate('''(coords) => {
                const el = document.elementFromPoint(coords.x, coords.y);
                return el ? el.tagName + '.' + (el.className || '') : null;
            }''', {'x': center_x, 'y': center_y})

            # Get target element tag for comparison
            target_tag = await element.evaluate('el => el.tagName + "." + (el.className || "")')

            # If top element matches target, we're good
            if top_element == target_tag:
                return True

            logger.warning(f"Element {selector} is obstructed by {top_element}")

            # Try to dismiss obstructions
            dismissed = await self.scan_and_dismiss_obstructions(aggressive=True)

            if dismissed > 0:
                # Re-check if element is now clickable
                await asyncio.sleep(0.5)
                new_top_element = await page.evaluate('''(coords) => {
                    const el = document.elementFromPoint(coords.x, coords.y);
                    return el ? el.tagName + '.' + (el.className || '') : null;
                }''', {'x': center_x, 'y': center_y})

                if new_top_element == target_tag:
                    logger.info(f"Element {selector} is now clickable after dismissing obstructions")
                    return True

            logger.warning(f"Could not clear obstructions for {selector}")
            return False

        except Exception as e:
            logger.warning(f"Error checking element clickability: {e}")
            return False

    async def get_elements_by_z_index(self, min_z_index: int = 1000) -> List[Dict]:
        """
        Get all elements with high z-index (likely overlays).

        Args:
            min_z_index: Minimum z-index to consider (default: 1000)

        Returns:
            List of element info dicts with selector, z-index, and coverage.
        """
        if not self.browser or not self.browser.page:
            return []

        page = self.browser.page

        try:
            elements = await page.evaluate('''(minZ) => {
                const viewport = {
                    width: window.innerWidth,
                    height: window.innerHeight
                };
                const viewportArea = viewport.width * viewport.height;
                const results = [];

                // Get all elements
                const allElements = document.querySelectorAll('*');

                for (const el of allElements) {
                    const style = window.getComputedStyle(el);
                    const zIndex = style.zIndex;

                    // Parse z-index
                    if (zIndex === 'auto') continue;
                    const zNum = parseInt(zIndex);
                    if (isNaN(zNum) || zNum < minZ) continue;

                    // Get bounding box
                    const rect = el.getBoundingClientRect();
                    const area = rect.width * rect.height;
                    const coverage = (area / viewportArea) * 100;

                    // Build selector
                    let selector = el.tagName.toLowerCase();
                    if (el.id) {
                        selector += '#' + el.id;
                    } else if (el.className && typeof el.className === 'string') {
                        const classes = el.className.split(' ').filter(c => c).join('.');
                        if (classes) selector += '.' + classes;
                    }

                    results.push({
                        selector: selector,
                        z_index: zNum,
                        coverage: coverage,
                        position: style.position,
                        visible: style.display !== 'none' && style.visibility !== 'hidden'
                    });
                }

                return results.sort((a, b) => b.z_index - a.z_index);
            }''', min_z_index)

            logger.debug(f"Found {len(elements)} elements with z-index >= {min_z_index}")
            return elements

        except Exception as e:
            logger.warning(f"Failed to get high z-index elements: {e}")
            return []

    async def auto_dismiss_on_navigation(self, url: str) -> int:
        """
        Automatically dismiss common obstructions after navigation.

        Call this after navigating to a new page to proactively
        dismiss cookie banners, modals, etc.

        Args:
            url: The URL that was navigated to (for logging)

        Returns:
            Number of obstructions dismissed.
        """
        # Wait a bit for page to settle
        await asyncio.sleep(1.5)

        logger.debug(f"Auto-checking for obstructions on {url}")

        # Run aggressive obstruction scan
        dismissed = await self.scan_and_dismiss_obstructions(aggressive=False)

        if dismissed > 0:
            logger.info(f"Auto-dismissed {dismissed} obstruction(s) after navigation")

        return dismissed

    def reset_obstruction_tracking(self):
        """Reset obstruction tracking state."""
        self._dismissed_obstructions.clear()
        self._obstruction_check_count = 0
        logger.debug("Reset obstruction tracking")

    # =========================================================================
    # Continuous Perception (Human-like Visual Awareness)
    # =========================================================================

    async def start_perception(self, config: Optional["PerceptionConfig"] = None) -> bool:
        """
        Start continuous visual perception.

        This makes the agent "see" the page continuously like a human,
        rather than just taking snapshots when needed.

        Args:
            config: Optional perception configuration

        Returns:
            True if perception started, False if not available or failed
        """
        if not self._perception_enabled:
            logger.debug("Continuous perception not available (module not installed)")
            return False

        if self._perception and self._perception._running:
            logger.debug("Perception already running")
            return True

        # Need browser page to start perception
        if not self.browser or not self.browser.page:
            logger.warning("Cannot start perception: no browser page available")
            return False

        try:
            self._perception = ContinuousPerception(
                self.browser.page,
                config=config
            )
            await self._perception.start()
            logger.info("Continuous perception started (seeing page like a human)")
            return True
        except Exception as e:
            logger.error(f"Failed to start perception: {e}")
            return False

    async def stop_perception(self):
        """Stop continuous visual perception."""
        if self._perception:
            await self._perception.stop()
            self._perception = None
            logger.debug("Continuous perception stopped")

    def get_perception_state(self) -> Optional["PerceptionState"]:
        """
        Get current perception state.

        Returns:
            PerceptionState with current visual info, or None if not running
        """
        if self._perception:
            return self._perception.get_state()
        return None

    def is_perception_active(self) -> bool:
        """Check if perception is currently running."""
        return self._perception is not None and self._perception._running

    async def wait_for_page_change(self, timeout_ms: int = 5000) -> bool:
        """
        Wait for a visual or DOM change on the page.

        Useful after taking an action to wait for the page to update.

        Args:
            timeout_ms: How long to wait for a change

        Returns:
            True if change detected, False if timeout
        """
        if not self._perception:
            # Fallback: simple sleep-based wait
            await asyncio.sleep(timeout_ms / 1000)
            return True

        return await self._perception.wait_for_change(timeout_ms)

    def get_interactive_elements(self) -> List[Dict]:
        """
        Get list of interactive elements currently visible.

        Uses continuous perception's element tracking.

        Returns:
            List of element dicts with tag, text, rect, etc.
        """
        if self._perception:
            return self._perception.state.interactive_elements
        return []

    def find_elements_by_text(self, text: str) -> List[Dict]:
        """
        Find interactive elements containing specific text.

        Args:
            text: Text to search for

        Returns:
            List of matching element dicts
        """
        if self._perception:
            return self._perception.find_elements_by_text(text)
        return []

    async def describe_current_page(self) -> str:
        """
        Get a human-readable description of the current page.

        Uses perception to describe what's visible.

        Returns:
            Description string
        """
        if self._perception:
            return await self._perception.describe_page()

        # Fallback if no perception
        url = await self.get_page_url()
        return f"Page: {url or 'unknown'}\n(Continuous perception not active)"

    def on_page_change(self, callback):
        """
        Register callback for page changes.

        Args:
            callback: Function to call when page changes (receives PerceptionState)
        """
        if self._perception:
            self._perception.on_change(callback)

    def connect_to_organism(self, organism):
        """
        Connect perception to the Organism event bus.

        This allows visual changes to trigger organism-wide events,
        enabling predictive behavior and learning from visual feedback.

        Args:
            organism: Organism instance with event_bus attribute
        """
        if not organism or not hasattr(organism, 'event_bus'):
            logger.debug("Cannot connect perception: no organism or event bus")
            return

        if not self._perception:
            logger.debug("Cannot connect perception: perception not started")
            return

        # Import here to avoid circular imports
        try:
            from .organism_core import EventType, OrganismEvent
        except ImportError:
            logger.debug("Cannot connect perception: organism_core not available")
            return

        def on_perception_change(state):
            """Handle perception state changes by emitting organism events."""
            try:
                event = OrganismEvent(
                    event_type=EventType.PERCEPTION_CHANGE,
                    source="continuous_perception",
                    data={
                        'url': state.page_url,
                        'title': state.page_title,
                        'element_count': len(state.interactive_elements),
                        'change_detected': state.change_detected,
                    },
                    priority=7  # Medium-low priority (visual updates are frequent)
                )
                organism.event_bus.publish_sync(event)
            except Exception as e:
                logger.debug(f"Failed to publish perception event: {e}")

        self._perception.on_change(on_perception_change)
        logger.info("Perception connected to Organism event bus")

    # =========================================================================
    # Session Persistence (Profile Manager Integration)
    # =========================================================================

    async def save_session_for_current_domain(self, profile_name: str = "default"):
        """
        Save cookies and localStorage for the current page's domain.

        Args:
            profile_name: Profile to save session to
        """
        if not self.profile_manager or not self.browser or not self.browser.page:
            return

        try:
            domain = await self.browser.page.evaluate('() => window.location.hostname')
            await self.profile_manager.export_cookies(profile_name, self.browser.page, domain)
            await self.profile_manager.export_localstorage(profile_name, self.browser.page, domain)
            logger.debug(f"Saved session for {domain}")
        except Exception as e:
            logger.debug(f"Failed to save session: {e}")

    async def restore_session_for_domain(self, domain: str, profile_name: str = "default"):
        """
        Restore cookies and localStorage for a specific domain.

        Args:
            domain: Domain to restore session for
            profile_name: Profile to restore from
        """
        if not self.profile_manager or not self.browser or not self.browser.page:
            return

        try:
            await self.profile_manager.restore_session(profile_name, self.browser.page, domain)
            logger.debug(f"Restored session for {domain}")
        except Exception as e:
            logger.debug(f"Failed to restore session: {e}")

    async def verify_domain_session_health(self, domain: str, profile_name: str = "default") -> bool:
        """
        Check if session for a domain is still valid.

        Args:
            domain: Domain to check
            profile_name: Profile name

        Returns:
            True if session is healthy, False if needs refresh
        """
        if not self.profile_manager or not self.browser or not self.browser.page:
            return True

        try:
            return await self.profile_manager.verify_session_health(
                profile_name,
                self.browser.page,
                domain
            )
        except Exception as e:
            logger.debug(f"Failed to verify session health: {e}")
            return False

    def set_current_profile(self, profile_name: str):
        """Set the current profile being used."""
        self._current_profile = profile_name

    def get_current_profile(self) -> Optional[str]:
        """Get the current profile name."""
        return self._current_profile


# =============================================================================
# Standalone Functions (for backward compatibility)
# =============================================================================

async def take_screenshot(browser) -> Optional[bytes]:
    """
    Take a screenshot of the current page.

    Standalone function for backward compatibility.

    Args:
        browser: Browser client with page attribute

    Returns:
        Screenshot bytes or None if capture failed.
    """
    if not browser:
        return None

    try:
        screenshot = await browser.page.screenshot()
        return screenshot
    except Exception as e:
        logger.debug(f"Screenshot capture failed: {e}")
        return None


async def ensure_browser_health(browser) -> bool:
    """
    Check browser health and attempt reconnection if unhealthy.

    Standalone function for backward compatibility.

    Args:
        browser: Browser client with is_healthy() and ensure_connected() methods

    Returns:
        True if browser is healthy or no browser is configured,
        False if browser is unhealthy and reconnection failed.
    """
    if not browser:
        return True

    try:
        if await browser.is_healthy():
            return True
    except Exception as e:
        logger.warning(f"Browser health probe failed: {e}")

    logger.warning("Browser unhealthy; attempting reconnect.")

    try:
        return await browser.ensure_connected()
    except Exception as e:
        logger.error(f"Browser reconnect failed: {e}")
        return False


def record_screenshot_hash(
    screenshot: Optional[bytes],
    last_hash: Optional[str],
    action_name: Optional[str] = None,
    actions_expected_change: Optional[Set[str]] = None
) -> tuple[Optional[str], Optional[str]]:
    """
    Track screenshot hashes and flag unexpected no-change scenarios.

    Standalone function for backward compatibility.

    Args:
        screenshot: Screenshot bytes to track
        last_hash: Previous screenshot hash
        action_name: Optional name of the action that produced this screenshot
        actions_expected_change: Set of actions expected to change the page

    Returns:
        Tuple of (new_hash, issue_string or None)
    """
    if not screenshot:
        return last_hash, None

    if actions_expected_change is None:
        actions_expected_change = {'playwright_navigate', 'playwright_click'}

    new_hash = hashlib.md5(screenshot).hexdigest()
    issue = None

    if (
        last_hash
        and action_name
        and action_name in actions_expected_change
        and new_hash == last_hash
    ):
        issue = f"Screenshot unchanged after {action_name}; page may not have loaded or changed."

    return new_hash, issue
