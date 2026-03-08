"""
Vision Processor Mixin - Handles screenshot capture and vision analysis.

This mixin provides vision-related functionality for the agent, including:
- Screenshot capture from browser
- Vision model analysis of screenshots
- Screenshot tracking and change detection
- Vision tool message logging
"""

import asyncio
import base64
import hashlib
import json
from typing import Dict, List, Optional, Any
from loguru import logger


class VisionProcessorMixin:
    """
    Mixin for vision processing capabilities.

    Required parent class attributes:
    - self.browser: Browser instance with page attribute
    - self.browser_manager: BrowserManager instance with capture_screenshot method
    - self.vision_model: str - Name of vision model to use
    - self.ollama_client: Ollama client instance
    - self.messages: List[Dict] - Message history
    - self.stats: Dict with 'vision_calls' key
    - self._last_screenshot_hash: Optional[str] - Hash of last screenshot
    - self._last_screenshot_issue: Optional[str] - Issue from last screenshot
    - self._actions_expected_change: Set[str] - Actions that should change the page
    """

    async def _collect_vision_insight(self, results: List) -> Dict:
        """
        Ensure we always have a vision-based check; try existing screenshots first,
        then capture a fresh one if needed.

        Args:
            results: List of ActionResult objects

        Returns:
            Dict with vision analysis results
        """
        screenshot = next((r.screenshot for r in reversed(results) if r.screenshot), None)
        if not screenshot and self.browser:
            screenshot = await self._take_screenshot()

        if screenshot:
            self._record_screenshot_bytes(screenshot, action_name=None)
            result = await self._vision_analyze(screenshot)
            self.stats['vision_calls'] += 1
            if result:
                return result

        return {}

    def _append_vision_tool_message(self, vision_result: Dict, name: str):
        """
        Log vision analysis output into the message stream for auditing.

        Args:
            vision_result: Dict containing vision analysis results
            name: Name of the vision tool/operation
        """
        try:
            self.messages.append({
                'role': 'tool',
                'name': name,
                'content': json.dumps(vision_result)[:2000]
            })
        except Exception as e:
            logger.debug(f"Failed to append vision message {name}: {e}")

    def _record_screenshot_bytes(self, screenshot: Optional[bytes], action_name: Optional[str] = None) -> Optional[str]:
        """
        Track screenshot hashes and flag unexpected no-change scenarios.

        Args:
            screenshot: Screenshot bytes
            action_name: Name of action that triggered screenshot

        Returns:
            Issue description if screenshot unchanged after expected change, None otherwise
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

    async def _vision_analyze(self, screenshot: bytes) -> Dict:
        """
        Use vision model to analyze screenshot.

        Args:
            screenshot: Screenshot bytes to analyze

        Returns:
            Dict with keys:
            - error_detected: bool
            - task_complete: bool
            - summary: str (truncated to 500 chars)
            - raw_summary: str (full text)
        """
        if not self.vision_model:
            logger.warning("No vision model configured; skipping visual analysis")
            return {'error': 'vision model not configured'}

        try:
            # Encode screenshot
            b64 = base64.b64encode(screenshot).decode('utf-8')

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
                # Keep a compact summary but also return the full text for describe mode
                'summary': summary_full[:500],
                'raw_summary': summary_full
            }

        except Exception as e:
            logger.warning(f"Vision analysis failed: {e}")
            return {}

    async def _take_screenshot(self) -> Optional[bytes]:
        """
        Take screenshot of current page.

        Returns:
            Screenshot bytes, or None if capture fails
        """
        if not self.browser:
            return None

        try:
            screenshot = await self.browser.page.screenshot()
            return screenshot
        except Exception as e:
            logger.debug(f"Screenshot capture failed: {e}")
            return None

    async def _capture_screenshot(self, tool_name: str, result: Any) -> Optional[bytes]:
        """
        Prefer the screenshot produced by the tool (if it saved a file),
        otherwise fall back to capturing the current page.

        Args:
            tool_name: Name of tool that was executed
            result: Result from tool execution

        Returns:
            Screenshot bytes, or None if capture fails
        """
        return await self.browser_manager.capture_screenshot(tool_name, result)
