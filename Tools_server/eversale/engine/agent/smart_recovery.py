import asyncio
from dataclasses import dataclass
from typing import Optional, List, Callable
from enum import Enum
from loguru import logger

class ErrorType(Enum):
    ELEMENT_NOT_FOUND = "element_not_found"
    TIMEOUT = "timeout"
    NAVIGATION_FAILED = "navigation_failed"
    CLICK_FAILED = "click_failed"
    FILL_FAILED = "fill_failed"
    PAGE_CHANGED = "page_changed"
    CAPTCHA = "captcha"
    LOGIN_REQUIRED = "login_required"
    UNKNOWN = "unknown"

@dataclass
class RecoveryAttempt:
    strategy: str
    success: bool
    error: Optional[str] = None

class SmartRecovery:
    def __init__(self, mcp_client, visual_finder=None, ollama_client=None, vision_model: str = "moondream"):
        self.mcp = mcp_client
        self.visual_finder = visual_finder
        self.ollama = ollama_client
        self.vision_model = vision_model
        self.max_retries = 3

    async def execute_with_recovery(
        self,
        action: Callable,
        action_name: str,
        fallback_actions: List[Callable] = None
    ) -> tuple[bool, any]:
        """Execute an action with automatic recovery on failure."""

        for attempt in range(self.max_retries):
            try:
                result = await action()
                return True, result
            except Exception as e:
                error_type = self._classify_error(str(e))
                logger.warning(f"Attempt {attempt + 1} failed: {error_type.value} - {e}")

                # Try recovery strategies
                recovered = await self._try_recovery(error_type, action_name)
                if recovered and attempt < self.max_retries - 1:
                    continue

                # Try fallback actions
                if fallback_actions:
                    for fallback in fallback_actions:
                        try:
                            result = await fallback()
                            logger.info(f"Fallback succeeded for {action_name}")
                            return True, result
                        except:
                            continue

        return False, None

    def _classify_error(self, error_msg: str) -> ErrorType:
        error_lower = error_msg.lower()

        if any(kw in error_lower for kw in ['not found', 'no element', 'selector']):
            return ErrorType.ELEMENT_NOT_FOUND
        if 'timeout' in error_lower:
            return ErrorType.TIMEOUT
        if any(kw in error_lower for kw in ['navigation', 'navigate', 'page']):
            return ErrorType.NAVIGATION_FAILED
        if 'click' in error_lower:
            return ErrorType.CLICK_FAILED
        if 'fill' in error_lower:
            return ErrorType.FILL_FAILED
        if 'captcha' in error_lower:
            return ErrorType.CAPTCHA
        if any(kw in error_lower for kw in ['login', 'auth', 'sign in']):
            return ErrorType.LOGIN_REQUIRED
        return ErrorType.UNKNOWN

    async def _try_recovery(self, error_type: ErrorType, action_name: str) -> bool:
        """Attempt to recover from an error."""

        if error_type == ErrorType.ELEMENT_NOT_FOUND:
            # Wait and retry - element might be loading
            await asyncio.sleep(2)
            return True

        if error_type == ErrorType.TIMEOUT:
            # Refresh page and retry
            try:
                await self.mcp.call_tool('playwright_navigate', {'url': 'javascript:location.reload()'})
                await asyncio.sleep(3)
                return True
            except:
                return False

        if error_type == ErrorType.PAGE_CHANGED:
            # Take screenshot and analyze
            return await self._analyze_and_adapt()

        if error_type == ErrorType.CAPTCHA:
            # Alert user or try automated solving
            logger.warning("CAPTCHA detected - may need manual intervention")
            return False

        return False

    async def _analyze_and_adapt(self) -> bool:
        """Use accessibility snapshot to understand current page state and adapt."""
        try:
            # Get accessibility snapshot instead of vision model analysis
            # A11y snapshots provide structured page data without requiring vision models
            snapshot_result = await self.mcp.call_tool('playwright_snapshot', {})
            if not snapshot_result:
                return False

            # The snapshot provides structured accessibility tree data
            # that can be used to understand page state and find interactive elements
            logger.debug("Retrieved accessibility snapshot for page analysis")
            return True
        except Exception as e:
            logger.debug(f"Failed to get accessibility snapshot: {e}")
            return False

    async def click_with_recovery(self, selector: str, description: str = "") -> bool:
        """Click with multiple fallback strategies."""

        strategies = [
            # Strategy 1: Direct selector
            lambda: self.mcp.call_tool('playwright_click', {'selector': selector}),
            # Strategy 2: Wait and click
            lambda: self._wait_and_click(selector),
            # Strategy 3: JavaScript click
            lambda: self._js_click(selector),
            # Strategy 4: Visual click (if available)
            lambda: self._visual_click(description) if description and self.visual_finder else None,
        ]

        strategies = [s for s in strategies if s is not None]

        for i, strategy in enumerate(strategies):
            try:
                await strategy()
                logger.info(f"Click succeeded with strategy {i + 1}")
                return True
            except Exception as e:
                logger.debug(f"Strategy {i + 1} failed: {e}")
                continue

        return False

    async def fill_with_recovery(self, selector: str, value: str, description: str = "") -> bool:
        """Fill with multiple fallback strategies."""

        strategies = [
            lambda: self.mcp.call_tool('playwright_fill', {'selector': selector, 'value': value}),
            lambda: self._wait_and_fill(selector, value),
            lambda: self._clear_and_fill(selector, value),
        ]

        for i, strategy in enumerate(strategies):
            try:
                await strategy()
                logger.info(f"Fill succeeded with strategy {i + 1}")
                return True
            except Exception as e:
                logger.debug(f"Fill strategy {i + 1} failed: {e}")
                continue

        return False

    async def _wait_and_click(self, selector: str):
        await asyncio.sleep(1)
        await self.mcp.call_tool('playwright_click', {'selector': selector})

    async def _js_click(self, selector: str):
        # Use JavaScript to click
        script = f"document.querySelector('{selector}')?.click()"
        await self.mcp.call_tool('playwright_evaluate', {'expression': script})

    async def _visual_click(self, description: str):
        if self.visual_finder:
            return await self.visual_finder.find_and_click(None, description)
        raise Exception("Visual finder not available")

    async def _wait_and_fill(self, selector: str, value: str):
        await asyncio.sleep(1)
        await self.mcp.call_tool('playwright_fill', {'selector': selector, 'value': value})

    async def _clear_and_fill(self, selector: str, value: str):
        # Clear field first, then fill
        await self.mcp.call_tool('playwright_fill', {'selector': selector, 'value': ''})
        await asyncio.sleep(0.3)
        await self.mcp.call_tool('playwright_fill', {'selector': selector, 'value': value})
