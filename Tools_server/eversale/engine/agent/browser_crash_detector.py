"""Browser crash detection and recovery."""
import asyncio
import time
from typing import Optional, Callable, Any
from loguru import logger
from playwright.async_api import Page, Error as PlaywrightError


class BrowserCrashDetector:
    """
    Detects and handles browser/page crashes.

    Features:
    - Detects unresponsive pages
    - Detects closed contexts/pages
    - Automatic browser restart
    - Task resumption after restart

    Usage:
        detector = BrowserCrashDetector()

        try:
            result = await detector.execute_with_crash_detection(
                page=page,
                operation=lambda p: p.click("button"),
                operation_name="click button"
            )
        except BrowserCrashError as e:
            # Handle crash - browser will be restarted
            logger.error(f"Browser crashed: {e}")
    """

    def __init__(
        self,
        response_timeout: float = 30.0,
        max_restart_attempts: int = 3
    ):
        """
        Initialize crash detector.

        Args:
            response_timeout: Seconds to wait for page response before considering it crashed
            max_restart_attempts: Maximum browser restart attempts
        """
        self.response_timeout = response_timeout
        self.max_restart_attempts = max_restart_attempts
        self.crash_count = 0
        self.last_crash_time: Optional[float] = None
        self.restart_callback: Optional[Callable] = None

    def register_restart_callback(self, callback: Callable):
        """
        Register callback to restart browser.

        Callback should accept no arguments and return new page instance.

        Example:
            async def restart_browser():
                await browser.close()
                browser = await playwright.chromium.launch()
                context = await browser.new_context()
                return await context.new_page()

            detector.register_restart_callback(restart_browser)
        """
        self.restart_callback = callback

    async def is_page_responsive(self, page: Page) -> bool:
        """
        Check if page is responsive.

        Args:
            page: Playwright page to check

        Returns:
            True if page is responsive, False otherwise
        """
        try:
            # Try simple JavaScript evaluation
            await asyncio.wait_for(
                page.evaluate("() => true"),
                timeout=5.0
            )
            return True
        except asyncio.TimeoutError:
            logger.warning("[CRASH] Page evaluation timed out - page may be unresponsive")
            return False
        except PlaywrightError as e:
            error_str = str(e).lower()
            if any(kw in error_str for kw in [
                "target closed",
                "context destroyed",
                "page closed",
                "browser closed"
            ]):
                logger.error(f"[CRASH] Page/context closed: {e}")
                return False
            # Other playwright errors - page might still be responsive
            logger.warning(f"[CRASH] Playwright error during responsiveness check: {e}")
            return False
        except Exception as e:
            logger.error(f"[CRASH] Unexpected error checking page responsiveness: {e}")
            return False

    def detect_crash_from_error(self, error: Exception) -> bool:
        """
        Detect if an error indicates a browser/page crash.

        Args:
            error: Exception to analyze

        Returns:
            True if error indicates crash, False otherwise
        """
        error_str = str(error).lower()

        crash_indicators = [
            "target closed",
            "context destroyed",
            "page closed",
            "browser closed",
            "execution context was destroyed",
            "page crashed",
            "browser disconnected",
            "protocol error",
            "session closed",
            "connection closed"
        ]

        return any(indicator in error_str for indicator in crash_indicators)

    async def execute_with_crash_detection(
        self,
        page: Page,
        operation: Callable[[Page], Any],
        operation_name: str = "operation"
    ) -> Any:
        """
        Execute operation with crash detection and automatic recovery.

        Args:
            page: Playwright page
            operation: Async function that takes page and performs operation
            operation_name: Name for logging

        Returns:
            Result of operation

        Raises:
            BrowserCrashError: If browser crashes and cannot be recovered
        """
        attempt = 0

        while attempt < self.max_restart_attempts:
            try:
                # Check if page is responsive before executing
                if not await self.is_page_responsive(page):
                    raise BrowserCrashError(
                        f"Page unresponsive before {operation_name}",
                        recoverable=True
                    )

                # Execute operation with timeout
                result = await asyncio.wait_for(
                    operation(page),
                    timeout=self.response_timeout
                )

                # Success - reset crash count
                if attempt > 0:
                    logger.info(f"[CRASH] Successfully recovered after {attempt} restart(s)")

                return result

            except asyncio.TimeoutError:
                logger.warning(
                    f"[CRASH] Operation '{operation_name}' timed out after "
                    f"{self.response_timeout}s"
                )

                # Check if page is still responsive
                if not await self.is_page_responsive(page):
                    # Page crashed
                    attempt += 1
                    if attempt >= self.max_restart_attempts:
                        raise BrowserCrashError(
                            f"Page unresponsive after timeout in {operation_name}",
                            recoverable=False
                        )

                    # Try restart
                    page = await self._handle_crash_and_restart(
                        page,
                        f"timeout in {operation_name}"
                    )
                else:
                    # Page responsive but operation timed out - propagate timeout
                    raise

            except Exception as e:
                # Check if error indicates crash
                if self.detect_crash_from_error(e):
                    attempt += 1
                    if attempt >= self.max_restart_attempts:
                        raise BrowserCrashError(
                            f"Browser crashed during {operation_name}: {e}",
                            recoverable=False
                        ) from e

                    # Try restart
                    page = await self._handle_crash_and_restart(
                        page,
                        f"crash during {operation_name}: {e}"
                    )
                else:
                    # Not a crash - propagate error
                    raise

        # Exhausted all restart attempts
        raise BrowserCrashError(
            f"Failed to recover from crash after {self.max_restart_attempts} attempts",
            recoverable=False
        )

    async def _handle_crash_and_restart(
        self,
        page: Page,
        reason: str
    ) -> Page:
        """
        Handle crash and restart browser.

        Args:
            page: Crashed page
            reason: Reason for crash

        Returns:
            New page instance

        Raises:
            BrowserCrashError: If no restart callback registered
        """
        self.crash_count += 1
        self.last_crash_time = time.time()

        logger.error(
            f"[CRASH] Browser/page crash detected: {reason}\n"
            f"  Total crashes: {self.crash_count}\n"
            f"  Attempting restart..."
        )

        if not self.restart_callback:
            raise BrowserCrashError(
                "Browser crashed but no restart callback registered",
                recoverable=False
            )

        try:
            # Close crashed page if possible
            try:
                await page.close()
            except:
                pass

            # Call restart callback
            new_page = await self.restart_callback()

            logger.info("[CRASH] Browser restarted successfully")

            return new_page

        except Exception as e:
            raise BrowserCrashError(
                f"Failed to restart browser: {e}",
                recoverable=False
            ) from e

    def get_stats(self) -> dict:
        """Get crash statistics."""
        return {
            "total_crashes": self.crash_count,
            "last_crash_time": self.last_crash_time,
            "max_restart_attempts": self.max_restart_attempts
        }


class BrowserCrashError(Exception):
    """Raised when browser crashes and cannot be recovered."""

    def __init__(self, message: str, recoverable: bool = False):
        super().__init__(message)
        self.recoverable = recoverable


# Global instance
_global_crash_detector: Optional[BrowserCrashDetector] = None


def get_crash_detector() -> BrowserCrashDetector:
    """Get or create global crash detector instance."""
    global _global_crash_detector
    if _global_crash_detector is None:
        _global_crash_detector = BrowserCrashDetector()
    return _global_crash_detector
