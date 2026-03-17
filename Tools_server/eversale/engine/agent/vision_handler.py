"""
Vision Handler - Handles all vision-related operations for the brain.

This module extracts vision functionality including:
- Screenshot capture and management
- Vision model analysis
- Screenshot hash tracking
- Vision insight collection
"""

import base64
import hashlib
import json
from typing import Dict, List, Optional, Any
from loguru import logger


class VisionHandler:
    """Handles all vision-related operations for the enhanced brain."""

    def __init__(self, brain):
        """
        Initialize VisionHandler with a reference to the brain instance.

        Args:
            brain: The EnhancedBrain instance that owns this handler
        """
        self.brain = brain

        # Track screenshot state
        self._last_screenshot_hash: Optional[str] = None
        self._last_screenshot_issue: Optional[str] = None
        self._actions_expected_change = {'playwright_navigate', 'playwright_click'}

    async def collect_vision_insight(self, results: List[Any]) -> Dict:
        """
        Ensure we always have a vision-based check; try existing screenshots first,
        then capture a fresh one if needed.

        Args:
            results: List of ActionResult objects from recent actions

        Returns:
            Dictionary containing vision analysis results
        """
        screenshot = next((r.screenshot for r in reversed(results) if hasattr(r, 'screenshot') and r.screenshot), None)
        if not screenshot and self.brain.browser:
            screenshot = await self.take_screenshot()

        if screenshot:
            self.record_screenshot_bytes(screenshot, action_name=None)
            result = await self.vision_analyze(screenshot)
            self.brain.stats['vision_calls'] += 1
            if result:
                return result

        return {}

    def append_vision_tool_message(self, vision_result: Dict, name: str):
        """
        Log vision analysis output into the message stream for auditing.

        Args:
            vision_result: Dictionary containing vision analysis results
            name: Name of the vision tool/operation
        """
        try:
            self.brain.messages.append({
                'role': 'tool',
                'name': name,
                'content': json.dumps(vision_result)[:2000]
            })
        except Exception as e:
            logger.debug(f"Failed to append vision message {name}: {e}")

    def record_screenshot_bytes(self, screenshot: Optional[bytes], action_name: Optional[str] = None) -> Optional[str]:
        """
        Track screenshot hashes and flag unexpected no-change scenarios.

        Args:
            screenshot: Screenshot bytes to record
            action_name: Name of the action that produced this screenshot

        Returns:
            Issue message if screenshot unchanged when change was expected, None otherwise
        """
        if not screenshot:
            return None

        new_hash = hashlib.md5(screenshot).hexdigest()
        issue = None

        if (
            self._last_screenshot_hash
            and action_name
            and action_name in self._actions_expected_change
            and new_hash == self._last_screenshot_hash
        ):
            issue = f"Screenshot unchanged after {action_name}; page may not have loaded or changed."

        self._last_screenshot_hash = new_hash
        self._last_screenshot_issue = issue
        return issue

    async def vision_analyze(self, screenshot: bytes) -> Dict:
        """
        Use vision model to analyze screenshot.

        Args:
            screenshot: Screenshot bytes to analyze

        Returns:
            Dictionary containing:
                - error_detected: Boolean indicating if error message found
                - task_complete: Boolean indicating if task appears complete
                - summary: Compact summary of analysis (max 500 chars)
                - raw_summary: Full analysis text
        """
        if not self.brain.vision_model:
            logger.warning("No vision model configured; skipping visual analysis")
            return {'error': 'vision model not configured'}

        try:
            # Encode screenshot
            b64 = base64.b64encode(screenshot).decode('utf-8')

            response = self.brain.ollama_client.chat(
                model=self.brain.vision_model,
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
                # Keep a compact summary but also return the full text for describe mode
                'summary': summary_full[:500],
                'raw_summary': summary_full
            }

        except Exception as e:
            logger.warning(f"Vision analysis failed: {e}")
            return {}

    async def take_screenshot(self) -> Optional[bytes]:
        """
        Take screenshot of current page.

        Uses UI-TARS enhanced screenshot with retry if available.

        Returns:
            Screenshot bytes or None if capture failed
        """
        if not self.brain.browser:
            return None

        # Try UI-TARS enhanced screenshot first (with retry)
        if hasattr(self.brain, 'uitars') and self.brain.uitars:
            try:
                b64 = await self.brain.uitars.enhanced_screenshot()
                if b64:
                    import base64
                    screenshot_bytes = base64.b64decode(b64)
                    logger.debug("[UITARS] Enhanced screenshot captured with 3x retry")
                    return screenshot_bytes
            except Exception as e:
                logger.debug(f"[UITARS] Enhanced screenshot failed, falling back: {e}")

        # Fallback to simple screenshot
        try:
            screenshot = await self.brain.browser.page.screenshot()
            return screenshot
        except Exception as e:
            logger.debug(f"Screenshot capture failed: {e}")
            return None

    async def capture_screenshot(self, tool_name: str, result: Any) -> Optional[bytes]:
        """
        Prefer the screenshot produced by the tool (if it saved a file),
        otherwise fall back to capturing the current page.

        Args:
            tool_name: Name of the tool that was executed
            result: Result object from the tool execution

        Returns:
            Screenshot bytes or None if capture failed
        """
        return await self.brain.browser_manager.capture_screenshot(tool_name, result)
