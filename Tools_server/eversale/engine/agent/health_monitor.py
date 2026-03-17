"""
Health Monitor - Extracted from brain_enhanced_v2.py

Provides health checking, common-sense verification, and browser health monitoring.
Includes both a standalone class (HealthMonitor) and a mixin (HealthMonitorMixin).
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any, List
from loguru import logger

try:
    import ollama
except ImportError:
    ollama = None


class HealthMonitor:
    """Standalone health monitor for delegation pattern."""

    def __init__(self, mcp, browser_manager, rescue_policy, survival, awareness,
                 session_state, ollama_client, stats: Dict, messages: List[Dict],
                 vision_model: str = 'moondream'):
        self.mcp = mcp
        self.browser_manager = browser_manager
        self.rescue_policy = rescue_policy
        self.survival = survival
        self.awareness = awareness
        self.session_state = session_state
        self.ollama_client = ollama_client
        self.stats = stats
        self.messages = messages
        self.browser = None
        self.vision_model = vision_model
        self._goal_summary = ""
        self._goal_keywords = []
        self._next_health_check_time = datetime.now()
        self._last_rescue_summary = ""
        self._preflight_done = False
        self._preflight_details = []
        self._preflight_attempts = 0
        self._max_preflight_attempts = 3
        self._preflight_retry_delay = 2
        # vision_model already set from constructor parameter

    def set_browser(self, browser):
        """Set browser reference."""
        self.browser = browser

    def update_goal(self, summary: str, keywords: List[str]):
        """Update goal tracking."""
        self._goal_summary = summary
        self._goal_keywords = keywords

    def get_last_rescue_summary(self) -> str:
        """Get last rescue summary."""
        return self._last_rescue_summary

    def _log_decision(self, kind: str, detail: Dict[str, Any]):
        """Log a decision (stub for standalone use)."""
        logger.debug(f"Decision [{kind}]: {detail}")

    async def _fetch_dom_feedback(self) -> str:
        """Capture text/DOM feedback for heuristic checks."""
        try:
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

    def _detect_text_issue(self, text: str) -> Optional[str]:
        """Detect common error keywords in page text."""
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

    async def _health_pulse(self, dom_feedback: str) -> Optional[str]:
        """Periodic health check executed every few iterations."""
        if self.stats['iterations'] == 0 or self.stats['iterations'] % 3 != 0:
            return None

        self.stats['health_checks'] = self.stats.get('health_checks', 0) + 1
        if not dom_feedback:
            return None

        lower = dom_feedback.lower()
        pulse_keywords = [
            'timeout', 'captcha', 'cloudflare', 'network error', 'service unavailable'
        ]
        for word in pulse_keywords:
            if word in lower:
                return f"Health pulse found '{word}' in page snapshot."
        return None

    async def _common_sense_verification(self, vision_result: Dict) -> Tuple[Optional[str], str]:
        """Run heuristics that enforce common-sense verification."""
        dom_feedback = await self._fetch_dom_feedback()
        text_issue = self._detect_text_issue(dom_feedback)
        if text_issue:
            return text_issue, dom_feedback

        screenshot_issue = self.browser_manager.last_screenshot_issue if self.browser_manager else None
        if screenshot_issue:
            return screenshot_issue, dom_feedback

        health_issue = await self._health_pulse(dom_feedback)
        if health_issue:
            return health_issue, dom_feedback

        return None, dom_feedback

    def _assert_success(self, dom_feedback: str, vision_result: Dict) -> Optional[str]:
        """Assert that goal keywords are present in the observed page."""
        if not self._goal_keywords:
            return None

        combined = " ".join([
            dom_feedback or "",
            vision_result.get('raw_summary', ''),
            vision_result.get('summary', '')
        ]).lower()

        if any(kw in combined for kw in self._goal_keywords):
            return None

        excerpt = ", ".join(self._goal_keywords[:3])
        return f"Goal keywords ({excerpt}) not referenced in the observed page."

    async def _maybe_run_scheduled_health(self) -> Optional[str]:
        """Run scheduled health check if it's time."""
        now = datetime.now()
        if now < self._next_health_check_time:
            return None
        dom_feedback = await self._fetch_dom_feedback()
        issue = await self._health_pulse(dom_feedback)
        self._next_health_check_time = now + timedelta(seconds=60)
        return issue

    async def _maybe_run_rescue(self):
        """Attempt recovery actions if the rescue policy triggers."""
        actions = await self.rescue_policy.attempt_recovery(self.survival, self.awareness)
        if not actions:
            return
        summary = "; ".join(actions)
        self._last_rescue_summary = summary
        self.messages.append({
            'role': 'user',
            'content': f"[Rescue] {summary}"
        })
        self._log_decision("rescue", {"actions": actions})

    async def _ensure_browser_health(self) -> bool:
        """Check browser health and attempt reconnection if unhealthy."""
        if not self.browser:
            return True

        try:
            if await self.browser.is_healthy():
                return True
        except Exception as e:
            logger.warning(f"Browser health probe failed: {e}")

        logger.warning("Browser unhealthy; attempting reconnect.")
        try:
            return await self.browser.ensure_connected()
        except Exception as e:
            logger.error(f"Browser reconnect failed: {e}")
            return False

    async def _preflight_checks(self) -> Tuple[bool, str]:
        """Ensure vision/browser/health are ready before any prompt executes."""
        if self._preflight_done:
            return True, "Awaiting previously passed preflight."

        self._preflight_details.clear()
        for attempt in range(1, self._max_preflight_attempts + 1):
            self._preflight_attempts = attempt
            ok, msg = await self._run_preflight_once(attempt)
            self._preflight_details.append(f"Attempt {attempt}: {msg or 'OK'}")
            if ok:
                self._preflight_done = True
                summary = f"Preflight succeeded on attempt {attempt}."
                return True, summary

            if attempt < self._max_preflight_attempts:
                await asyncio.sleep(self._preflight_retry_delay)

        final_msg = "; ".join(self._preflight_details)
        return False, final_msg

    async def _run_preflight_once(self, attempt: int) -> Tuple[bool, str]:
        """One shot of the preflight check."""
        issues = []
        if not await self._ensure_browser_health():
            issues.append("Browser not healthy/reachable.")

        # Vision model is optional - only warn if explicitly required
        if not self.vision_model:
            logger.debug("Vision model not configured - visual analysis disabled")
        if self.vision_model:
            fallback_env = os.environ.get("EVERSALE_VISION_FALLBACK", "1").lower()
            vision_fallback = fallback_env in {"1", "true", "yes"}
            if not vision_fallback and ollama:
                try:
                    ollama.list()
                except Exception as e:
                    issues.append(f"Vision service unavailable ({e}).")

        if issues:
            return False, "; ".join(issues)

        return True, "All checks passed."


class HealthMonitorMixin:
    """
    Mixin providing health monitoring and verification capabilities.

    Methods:
    - _detect_text_issue: Detect error keywords in page text
    - _health_pulse: Periodic health check every few iterations
    - _common_sense_verification: Run heuristics to verify page state
    - _assert_success: Assert goal keywords are present
    - _ensure_browser_health: Check and restore browser health
    - _maybe_run_scheduled_health: Run scheduled health checks
    - _maybe_run_rescue: Attempt recovery actions if needed
    """

    def _detect_text_issue(self, text: str) -> Optional[str]:
        """
        Detect common error keywords in page text.

        Args:
            text: Page text content

        Returns:
            Warning message if issue detected, None otherwise
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

    async def _health_pulse(self, dom_feedback: str) -> Optional[str]:
        """
        Periodic health check executed every few iterations.

        Args:
            dom_feedback: DOM/text feedback from page

        Returns:
            Warning message if issue detected, None otherwise
        """
        if self.stats['iterations'] == 0 or self.stats['iterations'] % 3 != 0:
            return None

        self.stats['health_checks'] = self.stats.get('health_checks', 0) + 1
        if not dom_feedback:
            return None

        lower = dom_feedback.lower()
        pulse_keywords = [
            'timeout', 'captcha', 'cloudflare', 'network error', 'service unavailable'
        ]
        for word in pulse_keywords:
            if word in lower:
                return f"Health pulse found '{word}' in page snapshot."
        return None

    async def _common_sense_verification(self, vision_result: Dict) -> Tuple[Optional[str], str]:
        """
        Run heuristics that enforce common-sense verification at every step.

        Args:
            vision_result: Result from vision/screenshot analysis

        Returns:
            Tuple of (warning message or None, dom_feedback string)
        """
        dom_feedback = await self._fetch_dom_feedback()
        text_issue = self._detect_text_issue(dom_feedback)
        if text_issue:
            return text_issue, dom_feedback

        # Check for screenshot issues from browser_manager
        screenshot_issue = self.browser_manager.last_screenshot_issue
        if screenshot_issue:
            return screenshot_issue, dom_feedback

        health_issue = await self._health_pulse(dom_feedback)
        if health_issue:
            return health_issue, dom_feedback

        return None, dom_feedback

    def _assert_success(self, dom_feedback: str, vision_result: Dict) -> Optional[str]:
        """
        Assert that goal keywords are present in the observed page.

        Args:
            dom_feedback: DOM/text feedback from page
            vision_result: Result from vision/screenshot analysis

        Returns:
            Warning message if goal keywords missing, None otherwise
        """
        if not self._goal_keywords:
            return None

        combined = " ".join([
            dom_feedback or "",
            vision_result.get('raw_summary', ''),
            vision_result.get('summary', '')
        ]).lower()

        if any(kw in combined for kw in self._goal_keywords):
            return None

        excerpt = ", ".join(self._goal_keywords[:3])
        return f"Goal keywords ({excerpt}) not referenced in the observed page."

    async def _maybe_run_scheduled_health(self) -> Optional[str]:
        """
        Run scheduled health check if it's time.

        Returns:
            Warning message if issue detected, None otherwise
        """
        now = datetime.now()
        if now < self._next_health_check_time:
            return None
        dom_feedback = await self._fetch_dom_feedback()
        issue = await self._health_pulse(dom_feedback)
        self._next_health_check_time = now + timedelta(seconds=60)
        return issue

    async def _maybe_run_rescue(self):
        """
        Attempt recovery actions if the rescue policy triggers.

        Adds rescue actions to the conversation history and logs decisions.
        """
        actions = await self.rescue_policy.attempt_recovery(self.survival, self.awareness)
        if not actions:
            return
        summary = "; ".join(actions)
        self._last_rescue_summary = summary
        self.messages.append({
            'role': 'user',
            'content': f"[Rescue] {summary}"
        })
        self._log_decision("rescue", {"actions": actions})

    async def _ensure_browser_health(self) -> bool:
        """
        Check browser health and attempt reconnection if unhealthy.

        Returns:
            True if browser is healthy or successfully reconnected, False otherwise
        """
        if not self.browser:
            return True

        try:
            if await self.browser.is_healthy():
                return True
        except Exception as e:
            logger.warning(f"Browser health probe failed: {e}")

        logger.warning("Browser unhealthy; attempting reconnect.")
        try:
            return await self.browser.ensure_connected()
        except Exception as e:
            logger.error(f"Browser reconnect failed: {e}")
            return False
