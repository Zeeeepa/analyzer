"""
Reliability Core Module - Production-Ready Error Handling and Browser Health

This module provides foundational reliability patterns for all Eversale CLI tools:

1. ToolResult - Standard return format with rich error context
2. BrowserHealthCheck - Browser lifecycle and recovery management
3. ReliableExecutor - Retry logic with exponential backoff and jitter
4. InputValidator - Comprehensive input validation for URLs, selectors, refs
5. TimeoutConfig - Standard timeout constants across the system

Philosophy:
- NEVER swallow errors - surface them with clear messages
- Every operation returns ToolResult (success/failure explicit)
- Log everything with timing information
- Retry intelligently with backoff, but fail fast when appropriate
- Validate inputs before execution to fail early

Usage:
    from reliability_core import (
        ToolResult, BrowserHealthCheck, ReliableExecutor,
        InputValidator, TimeoutConfig
    )

    # Execute with retry
    executor = ReliableExecutor()
    result = await executor.execute(
        operation=lambda: page.click("button"),
        timeout=TimeoutConfig.NORMAL,
        retries=2
    )

    # Validate inputs
    validator = InputValidator()
    if not validator.validate_url(url):
        return ToolResult(success=False, error="Invalid URL")

    # Check browser health
    health = BrowserHealthCheck()
    if not await health.check_browser_alive(page):
        await health.recover_browser(page)
"""

import asyncio
import random
import time
import re
from typing import Any, Optional, Callable, Awaitable, TypeVar, Union
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse
from loguru import logger

T = TypeVar('T')


# =============================================================================
# STANDARD RESULT FORMAT
# =============================================================================

@dataclass
class ToolResult:
    """
    Standard return format for ALL tools.

    Every tool should return this to ensure consistent error handling.
    Never return raw values or raise exceptions from tools - wrap everything.

    Attributes:
        success: True if operation succeeded, False otherwise
        data: Operation result data (any type)
        error: Human-readable error message if failed
        error_code: Machine-readable error code (e.g., "ELEMENT_NOT_FOUND")
        duration_ms: How long the operation took in milliseconds
        retries_used: Number of retries that were attempted
    """
    success: bool
    data: Any = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    duration_ms: int = 0
    retries_used: int = 0

    def __str__(self) -> str:
        """Human-readable string representation."""
        if self.success:
            return f"Success ({self.duration_ms}ms)"
        else:
            return f"Failed: {self.error} [{self.error_code}] ({self.duration_ms}ms)"

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-compatible get method for backwards compatibility."""
        return getattr(self, key, default)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'success': self.success,
            'data': self.data,
            'error': self.error,
            'error_code': self.error_code,
            'duration_ms': self.duration_ms,
            'retries_used': self.retries_used
        }


# =============================================================================
# STANDARD TIMEOUTS
# =============================================================================

class TimeoutConfig:
    """
    Standard timeout constants used across the system.

    Use these instead of magic numbers to ensure consistency.

    Examples:
        await page.click("button", timeout=TimeoutConfig.NORMAL * 1000)
        result = await executor.execute(op, timeout=TimeoutConfig.SLOW)
    """
    FAST = 2      # 2 seconds - Quick operations (clicks, simple checks)
    NORMAL = 5    # 5 seconds - Standard operations (navigation, form fills)
    SLOW = 15     # 15 seconds - Slow operations (complex pages, heavy JS)
    MAX = 30      # 30 seconds - Maximum wait time (file uploads, API calls)

    @staticmethod
    def to_ms(seconds: float) -> int:
        """Convert seconds to milliseconds for Playwright."""
        return int(seconds * 1000)


# =============================================================================
# BROWSER HEALTH MANAGEMENT
# =============================================================================

class BrowserHealthCheck:
    """
    Browser lifecycle and health management.

    Provides methods to verify browser state and recover from crashes.
    Use before critical operations to ensure browser is responsive.
    """

    def __init__(self):
        self._last_check: Optional[datetime] = None
        self._consecutive_failures = 0
        self._max_failures = 3

    async def check_browser_alive(self, page: Any) -> bool:
        """
        Check if browser is responsive.

        Args:
            page: Playwright Page object

        Returns:
            True if browser is alive and responsive, False otherwise
        """
        try:
            # Quick health check - evaluate simple JS
            result = await asyncio.wait_for(
                page.evaluate("() => true"),
                timeout=TimeoutConfig.FAST
            )
            self._consecutive_failures = 0
            self._last_check = datetime.now()
            return result is True

        except asyncio.TimeoutError:
            logger.warning("[RELIABILITY] Browser health check timeout")
            self._consecutive_failures += 1
            return False

        except Exception as e:
            logger.warning(f"[RELIABILITY] Browser health check failed: {e}")
            self._consecutive_failures += 1
            return False

    async def check_page_loaded(self, page: Any) -> bool:
        """
        Check if page is fully loaded and ready for interaction.

        Args:
            page: Playwright Page object

        Returns:
            True if page is loaded, False otherwise
        """
        try:
            # Check document.readyState
            state = await asyncio.wait_for(
                page.evaluate("() => document.readyState"),
                timeout=TimeoutConfig.FAST
            )

            if state in ("complete", "interactive"):
                logger.debug(f"[RELIABILITY] Page loaded (state={state})")
                return True

            logger.debug(f"[RELIABILITY] Page not ready (state={state})")
            return False

        except Exception as e:
            logger.warning(f"[RELIABILITY] Page load check failed: {e}")
            return False

    async def recover_browser(self, page: Any) -> ToolResult:
        """
        Attempt to recover from browser crash or freeze.

        Tries multiple recovery strategies:
        1. Reload current page
        2. Navigate to blank page
        3. Close and reopen page (requires context)

        Args:
            page: Playwright Page object

        Returns:
            ToolResult indicating recovery success/failure
        """
        start_time = time.time()

        try:
            logger.warning("[RELIABILITY] Attempting browser recovery...")

            # Strategy 1: Try to reload
            try:
                await asyncio.wait_for(
                    page.reload(wait_until="domcontentloaded"),
                    timeout=TimeoutConfig.NORMAL
                )
                if await self.check_browser_alive(page):
                    duration_ms = int((time.time() - start_time) * 1000)
                    logger.info("[RELIABILITY] Browser recovered via reload")
                    return ToolResult(
                        success=True,
                        data="reload",
                        duration_ms=duration_ms
                    )
            except Exception as e:
                logger.debug(f"[RELIABILITY] Reload failed: {e}")

            # Strategy 2: Navigate to blank page
            try:
                await asyncio.wait_for(
                    page.goto("about:blank"),
                    timeout=TimeoutConfig.NORMAL
                )
                if await self.check_browser_alive(page):
                    duration_ms = int((time.time() - start_time) * 1000)
                    logger.info("[RELIABILITY] Browser recovered via blank navigation")
                    return ToolResult(
                        success=True,
                        data="blank_navigation",
                        duration_ms=duration_ms
                    )
            except Exception as e:
                logger.debug(f"[RELIABILITY] Blank navigation failed: {e}")

            # All strategies failed
            duration_ms = int((time.time() - start_time) * 1000)
            return ToolResult(
                success=False,
                error="Browser recovery failed after all strategies",
                error_code="RECOVERY_FAILED",
                duration_ms=duration_ms
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return ToolResult(
                success=False,
                error=f"Recovery exception: {str(e)}",
                error_code="RECOVERY_EXCEPTION",
                duration_ms=duration_ms
            )

    async def wait_for_ready(self, page: Any, timeout: float = TimeoutConfig.NORMAL) -> ToolResult:
        """
        Wait until page is interactive and ready for operations.

        Args:
            page: Playwright Page object
            timeout: Maximum time to wait in seconds

        Returns:
            ToolResult indicating if page became ready
        """
        start_time = time.time()
        deadline = start_time + timeout

        try:
            while time.time() < deadline:
                if await self.check_page_loaded(page):
                    duration_ms = int((time.time() - start_time) * 1000)
                    return ToolResult(
                        success=True,
                        data="ready",
                        duration_ms=duration_ms
                    )

                # Wait a bit before next check
                await asyncio.sleep(0.5)

            # Timeout
            duration_ms = int((time.time() - start_time) * 1000)
            return ToolResult(
                success=False,
                error=f"Page did not become ready within {timeout}s",
                error_code="PAGE_READY_TIMEOUT",
                duration_ms=duration_ms
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return ToolResult(
                success=False,
                error=f"Wait for ready failed: {str(e)}",
                error_code="WAIT_READY_EXCEPTION",
                duration_ms=duration_ms
            )

    @property
    def is_unhealthy(self) -> bool:
        """Check if browser has had too many consecutive failures."""
        return self._consecutive_failures >= self._max_failures


# =============================================================================
# RELIABLE EXECUTION WITH RETRY
# =============================================================================

class ReliableExecutor:
    """
    Execute operations with retry logic and exponential backoff.

    Features:
    - Exponential backoff with jitter (prevents thundering herd)
    - Configurable retries and timeouts
    - Detailed logging with timing
    - Never swallows errors - always returns ToolResult

    Usage:
        executor = ReliableExecutor()

        result = await executor.execute(
            operation=lambda: page.click("button"),
            timeout=5,
            retries=2,
            backoff=True
        )

        if result.success:
            print(f"Success: {result.data}")
        else:
            print(f"Failed: {result.error} [{result.error_code}]")
    """

    def __init__(self):
        self._stats = {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'total_retries': 0,
            'total_duration_ms': 0
        }

    async def execute(
        self,
        operation: Callable[[], Awaitable[Any]],
        timeout: float = TimeoutConfig.NORMAL,
        retries: int = 2,
        backoff: bool = True,
        backoff_base: float = 1.0,
        backoff_max: float = 10.0,
        retry_on: tuple = (Exception,),
        fail_fast_on: tuple = (KeyboardInterrupt,)
    ) -> ToolResult:
        """
        Execute operation with retry logic.

        Args:
            operation: Async callable to execute
            timeout: Timeout per attempt in seconds
            retries: Number of retry attempts (0 = no retries)
            backoff: Whether to use exponential backoff
            backoff_base: Base delay for backoff in seconds
            backoff_max: Maximum backoff delay in seconds
            retry_on: Tuple of exceptions that trigger retry
            fail_fast_on: Tuple of exceptions that skip retry

        Returns:
            ToolResult with operation result or error details
        """
        start_time = time.time()
        self._stats['total_operations'] += 1

        last_error: Optional[Exception] = None
        last_delay = backoff_base

        for attempt in range(retries + 1):
            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    operation(),
                    timeout=timeout
                )

                # Success!
                duration_ms = int((time.time() - start_time) * 1000)
                self._stats['successful_operations'] += 1
                self._stats['total_duration_ms'] += duration_ms

                if attempt > 0:
                    logger.info(f"[RELIABILITY] Operation succeeded after {attempt} retries")

                return ToolResult(
                    success=True,
                    data=result,
                    duration_ms=duration_ms,
                    retries_used=attempt
                )

            except fail_fast_on as e:
                # Don't retry these exceptions
                duration_ms = int((time.time() - start_time) * 1000)
                self._stats['failed_operations'] += 1
                self._stats['total_duration_ms'] += duration_ms

                logger.error(f"[RELIABILITY] Fail-fast exception: {type(e).__name__}")

                return ToolResult(
                    success=False,
                    error=str(e),
                    error_code="FAIL_FAST",
                    duration_ms=duration_ms,
                    retries_used=attempt
                )

            except retry_on as e:
                last_error = e

                # If this was the last attempt, fail
                if attempt >= retries:
                    duration_ms = int((time.time() - start_time) * 1000)
                    self._stats['failed_operations'] += 1
                    self._stats['total_duration_ms'] += duration_ms

                    error_type = type(e).__name__
                    error_msg = str(e)

                    logger.error(
                        f"[RELIABILITY] Operation failed after {attempt} retries: "
                        f"{error_type}: {error_msg}"
                    )

                    return ToolResult(
                        success=False,
                        error=error_msg,
                        error_code=error_type.upper(),
                        duration_ms=duration_ms,
                        retries_used=attempt
                    )

                # Calculate backoff delay
                if backoff:
                    # Exponential backoff with decorrelated jitter
                    delay = random.uniform(backoff_base, min(backoff_max, last_delay * 3))
                    last_delay = delay
                else:
                    delay = backoff_base

                logger.warning(
                    f"[RELIABILITY] Attempt {attempt + 1}/{retries + 1} failed: "
                    f"{type(e).__name__}: {str(e)[:100]}. "
                    f"Retrying in {delay:.2f}s..."
                )

                self._stats['total_retries'] += 1
                await asyncio.sleep(delay)

        # Should never reach here, but handle it gracefully
        duration_ms = int((time.time() - start_time) * 1000)
        return ToolResult(
            success=False,
            error="Unexpected execution path",
            error_code="UNEXPECTED_PATH",
            duration_ms=duration_ms,
            retries_used=retries
        )

    def get_stats(self) -> dict:
        """Get execution statistics."""
        total_ops = self._stats['total_operations']
        if total_ops == 0:
            return self._stats

        success_rate = (self._stats['successful_operations'] / total_ops) * 100
        avg_duration = self._stats['total_duration_ms'] / total_ops

        return {
            **self._stats,
            'success_rate_pct': round(success_rate, 2),
            'avg_duration_ms': round(avg_duration, 2)
        }

    def reset_stats(self):
        """Reset statistics counters."""
        self._stats = {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'total_retries': 0,
            'total_duration_ms': 0
        }


# =============================================================================
# INPUT VALIDATION
# =============================================================================

class InputValidator:
    """
    Comprehensive input validation for browser operations.

    Validates URLs, selectors, refs, and other inputs before execution.
    Provides clear error messages for invalid inputs.
    """

    # Supported URL schemes
    VALID_SCHEMES = ('http', 'https', 'about', 'data', 'file')

    # Selector type patterns
    SELECTOR_PATTERNS = {
        'css': r'^[a-zA-Z0-9#.\[\]\-_:(),>+~\s*="\']+$',
        'xpath': r'^(//|\.\.?/)',
        'text': r'^text=',
        'role': r'^role=',
        'test_id': r'^data-testid=',
        'placeholder': r'^placeholder=',
        'alt': r'^alt=',
        'title': r'^title=',
    }

    # Accessibility ref pattern (MMIDs from dom_distillation)
    REF_PATTERN = r'^[a-zA-Z0-9\-_]+$'

    def validate_url(self, url: str) -> tuple[bool, Optional[str]]:
        """
        Validate URL format and scheme.

        Args:
            url: URL string to validate

        Returns:
            (is_valid, error_message) tuple
        """
        if not url or not isinstance(url, str):
            return False, "URL must be a non-empty string"

        # Strip whitespace
        url = url.strip()

        # Parse URL
        try:
            parsed = urlparse(url)
        except Exception as e:
            return False, f"Invalid URL format: {str(e)}"

        # Check scheme
        if not parsed.scheme:
            return False, "URL must include scheme (http:// or https://)"

        if parsed.scheme not in self.VALID_SCHEMES:
            return False, f"Invalid URL scheme: {parsed.scheme}. Must be one of: {', '.join(self.VALID_SCHEMES)}"

        # Check netloc for http/https
        if parsed.scheme in ('http', 'https') and not parsed.netloc:
            return False, "URL must include domain (e.g., example.com)"

        return True, None

    def validate_selector(self, selector: str) -> tuple[bool, Optional[str]]:
        """
        Validate selector format.

        Supports: CSS, XPath, text=, role=, and other Playwright selectors.

        Args:
            selector: Selector string to validate

        Returns:
            (is_valid, error_message) tuple
        """
        if not selector or not isinstance(selector, str):
            return False, "Selector must be a non-empty string"

        selector = selector.strip()

        # Empty after strip
        if not selector:
            return False, "Selector cannot be empty or whitespace only"

        # Check if it matches any known pattern
        for selector_type, pattern in self.SELECTOR_PATTERNS.items():
            if re.match(pattern, selector, re.IGNORECASE):
                return True, None

        # If no pattern matches, it might still be valid CSS
        # Just check it's not obviously malformed
        if selector.count('(') != selector.count(')'):
            return False, "Unbalanced parentheses in selector"

        if selector.count('[') != selector.count(']'):
            return False, "Unbalanced brackets in selector"

        if selector.count('{') != selector.count('}'):
            return False, "Unbalanced braces in selector"

        # Passed basic checks
        return True, None

    def validate_ref(self, ref: str) -> tuple[bool, Optional[str]]:
        """
        Validate accessibility reference (MMID) format.

        Refs are injected by dom_distillation.py and should be alphanumeric
        with hyphens and underscores only.

        Args:
            ref: Reference string to validate

        Returns:
            (is_valid, error_message) tuple
        """
        if not ref or not isinstance(ref, str):
            return False, "Ref must be a non-empty string"

        ref = ref.strip()

        if not ref:
            return False, "Ref cannot be empty or whitespace only"

        # Check pattern
        if not re.match(self.REF_PATTERN, ref):
            return False, f"Ref must be alphanumeric with hyphens/underscores only. Got: {ref}"

        # Length check (reasonable bounds)
        if len(ref) > 100:
            return False, f"Ref is too long ({len(ref)} chars). Max 100 chars."

        return True, None

    def validate_text_input(self, text: str, max_length: int = 10000) -> tuple[bool, Optional[str]]:
        """
        Validate text input for forms and typing.

        Args:
            text: Text to validate
            max_length: Maximum allowed length

        Returns:
            (is_valid, error_message) tuple
        """
        if text is None:
            return False, "Text cannot be None"

        if not isinstance(text, str):
            return False, f"Text must be string, got {type(text).__name__}"

        if len(text) > max_length:
            return False, f"Text too long ({len(text)} chars). Max {max_length} chars."

        return True, None

    def validate_timeout(self, timeout: float) -> tuple[bool, Optional[str]]:
        """
        Validate timeout value.

        Args:
            timeout: Timeout in seconds

        Returns:
            (is_valid, error_message) tuple
        """
        if not isinstance(timeout, (int, float)):
            return False, f"Timeout must be numeric, got {type(timeout).__name__}"

        if timeout <= 0:
            return False, f"Timeout must be positive, got {timeout}"

        if timeout > TimeoutConfig.MAX:
            return False, f"Timeout too large ({timeout}s). Max {TimeoutConfig.MAX}s."

        return True, None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_success_result(data: Any = None, duration_ms: int = 0) -> ToolResult:
    """Create a success ToolResult with data."""
    return ToolResult(success=True, data=data, duration_ms=duration_ms)


def create_error_result(
    error: str,
    error_code: str = "UNKNOWN_ERROR",
    duration_ms: int = 0
) -> ToolResult:
    """Create a failure ToolResult with error details."""
    return ToolResult(
        success=False,
        error=error,
        error_code=error_code,
        duration_ms=duration_ms
    )


def create_timeout_result(operation: str, timeout: float) -> ToolResult:
    """Create a timeout error result."""
    return ToolResult(
        success=False,
        error=f"{operation} timed out after {timeout}s",
        error_code="TIMEOUT",
        duration_ms=int(timeout * 1000)
    )


def create_validation_error(field: str, message: str) -> ToolResult:
    """Create a validation error result."""
    return ToolResult(
        success=False,
        error=f"Validation failed for {field}: {message}",
        error_code="VALIDATION_ERROR"
    )


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'ToolResult',
    'TimeoutConfig',
    'BrowserHealthCheck',
    'ReliableExecutor',
    'InputValidator',
    'create_success_result',
    'create_error_result',
    'create_timeout_result',
    'create_validation_error',
]
