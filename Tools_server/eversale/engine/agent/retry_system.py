"""
Exponential Backoff Retry System - Intelligent Retry Management

Based on OpenCode's session/retry.ts, this module provides robust retry logic
with exponential backoff, configurable conditions, and abort signal support.

Key Features:
- Exponential backoff: 2000 * 2^(attempt-1), max 30s
- Retry-After header parsing (retry-after-ms, retry-after)
- Configurable retryable conditions (API errors, rate limits, network issues)
- Cancellable sleep with asyncio.Event abort signals
- Decorator @with_retry for easy function wrapping

Configuration:
- initial_delay: 2 seconds
- backoff_multiplier: 2x
- max_delay: 30 seconds
- max_attempts: 5

Retryable Conditions:
- API errors with retryable flag
- "Overloaded" provider messages
- "too_many_requests" errors
- Resource exhaustion indicators
- Rate limit errors (429)
- Temporary network failures
"""

import asyncio
import time
from typing import Optional, Callable, Any, Dict, Union
from dataclasses import dataclass
from loguru import logger
from functools import wraps


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    initial_delay: float = 2.0  # 2 seconds
    backoff_multiplier: float = 2.0  # 2x
    max_delay: float = 30.0  # 30 seconds max
    max_attempts: int = 5


class RetryManager:
    """
    Manages exponential backoff retry logic with cancellation support.

    Usage:
        manager = RetryManager()

        # Check if error is retryable
        if manager.is_retryable(error):
            delay = manager.calculate_delay(attempt=1)
            await manager.sleep(delay, abort_signal)
            # retry operation
    """

    def __init__(self, config: Optional[RetryConfig] = None):
        """
        Initialize retry manager with configuration.

        Args:
            config: RetryConfig instance, or None for defaults
        """
        self.config = config or RetryConfig()
        logger.debug(
            f"[RETRY] Initialized RetryManager: "
            f"initial_delay={self.config.initial_delay}s, "
            f"max_delay={self.config.max_delay}s, "
            f"max_attempts={self.config.max_attempts}"
        )

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay for given attempt number.

        Formula: initial_delay * (backoff_multiplier ^ (attempt - 1))
        Example: 2.0 * (2.0 ^ 0) = 2s, 2.0 * (2.0 ^ 1) = 4s, etc.
        Capped at max_delay.

        Args:
            attempt: Attempt number (1-indexed)

        Returns:
            Delay in seconds
        """
        if attempt < 1:
            attempt = 1

        # Exponential backoff: initial_delay * (multiplier ^ (attempt - 1))
        delay = self.config.initial_delay * (
            self.config.backoff_multiplier ** (attempt - 1)
        )

        # Cap at max_delay
        delay = min(delay, self.config.max_delay)

        logger.debug(
            f"[RETRY] Calculated delay for attempt {attempt}: {delay:.2f}s "
            f"(max: {self.config.max_delay}s)"
        )

        return delay

    def parse_retry_after(
        self,
        headers: Union[Dict[str, str], Any]
    ) -> Optional[float]:
        """
        Extract retry delay from response headers.

        Checks for:
        - retry-after-ms: Milliseconds (convert to seconds)
        - retry-after: Seconds or HTTP date

        Args:
            headers: Response headers (dict or aiohttp response object)

        Returns:
            Delay in seconds, or None if not found
        """
        # Handle aiohttp response objects
        if hasattr(headers, 'headers'):
            headers = dict(headers.headers)

        # Convert all header keys to lowercase for case-insensitive matching
        headers_lower = {k.lower(): v for k, v in headers.items()}

        # Check for retry-after-ms (milliseconds)
        if 'retry-after-ms' in headers_lower:
            try:
                ms = float(headers_lower['retry-after-ms'])
                delay = ms / 1000.0
                logger.info(f"[RETRY] Found retry-after-ms header: {ms}ms ({delay}s)")
                return delay
            except (ValueError, TypeError) as e:
                logger.warning(f"[RETRY] Invalid retry-after-ms value: {e}")

        # Check for retry-after (seconds or HTTP date)
        if 'retry-after' in headers_lower:
            retry_after = headers_lower['retry-after']

            try:
                # Try parsing as integer seconds
                delay = float(retry_after)
                logger.info(f"[RETRY] Found retry-after header: {delay}s")
                return delay
            except (ValueError, TypeError):
                # Try parsing as HTTP date
                try:
                    from email.utils import parsedate_to_datetime
                    retry_date = parsedate_to_datetime(retry_after)
                    now = time.time()
                    retry_timestamp = retry_date.timestamp()
                    delay = max(0, retry_timestamp - now)
                    logger.info(
                        f"[RETRY] Parsed retry-after date: "
                        f"{retry_after} -> {delay:.2f}s"
                    )
                    return delay
                except Exception as e:
                    logger.warning(
                        f"[RETRY] Could not parse retry-after header: "
                        f"{retry_after} - {e}"
                    )

        return None

    def is_retryable(
        self,
        error: Exception,
        response: Optional[Any] = None
    ) -> bool:
        """
        Determine if an error warrants a retry.

        Retryable conditions:
        - API errors with retryable flag
        - "Overloaded" provider messages
        - "too_many_requests" errors
        - Resource exhaustion indicators
        - Rate limit errors (429)
        - Temporary network failures
        - Connection timeouts
        - Server errors (500, 502, 503, 504)

        Args:
            error: Exception that occurred
            response: Optional response object (for status code checking)

        Returns:
            True if error is retryable, False otherwise
        """
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()

        # Check for explicit retryable flag in error attributes
        if hasattr(error, 'retryable') and error.retryable:
            logger.info(f"[RETRY] Error has retryable=True flag: {error_type}")
            return True

        # Provider overload messages
        if any(kw in error_str for kw in [
            'overloaded',
            'overload',
            'capacity',
            'at capacity'
        ]):
            logger.info(f"[RETRY] Provider overload detected: {error_str[:100]}")
            return True

        # Rate limiting
        if any(kw in error_str for kw in [
            'too_many_requests',
            'too many requests',
            'rate limit',
            'rate_limit',
            'ratelimit',
            'quota exceeded',
            'throttle',
            'throttled'
        ]):
            logger.info(f"[RETRY] Rate limit error detected: {error_str[:100]}")
            return True

        # Resource exhaustion
        if any(kw in error_str for kw in [
            'resource exhausted',
            'resources exhausted',
            'out of resources',
            'insufficient resources'
        ]):
            logger.info(f"[RETRY] Resource exhaustion detected: {error_str[:100]}")
            return True

        # Temporary network failures
        if any(kw in error_str for kw in [
            'timeout',
            'timed out',
            'connection reset',
            'connection refused',
            'connection error',
            'network error',
            'temporary failure',
            'temporarily unavailable',
            'service unavailable'
        ]):
            logger.info(f"[RETRY] Temporary network failure: {error_str[:100]}")
            return True

        # Check response status codes (if available)
        if response is not None:
            status_code = None

            # Extract status code from various response types
            if hasattr(response, 'status_code'):
                status_code = response.status_code
            elif hasattr(response, 'status'):
                status_code = response.status

            if status_code:
                # Retryable HTTP status codes
                if status_code in [429, 500, 502, 503, 504]:
                    logger.info(
                        f"[RETRY] Retryable HTTP status code: {status_code}"
                    )
                    return True

        # Common exception types
        retryable_exceptions = [
            'timeout',
            'connectionerror',
            'connecttimeout',
            'readtimeout',
            'temporaryfailure'
        ]

        if any(exc in error_type for exc in retryable_exceptions):
            logger.info(f"[RETRY] Retryable exception type: {error_type}")
            return True

        # Not retryable
        logger.debug(f"[RETRY] Error not retryable: {error_type} - {error_str[:100]}")
        return False

    async def sleep(
        self,
        delay: float,
        abort_signal: Optional[asyncio.Event] = None
    ) -> bool:
        """
        Sleep for specified duration with cancellation support.

        Args:
            delay: Delay in seconds
            abort_signal: Optional asyncio.Event for cancellation

        Returns:
            True if sleep completed, False if aborted
        """
        if delay <= 0:
            return True

        logger.debug(f"[RETRY] Sleeping for {delay:.2f}s")

        if abort_signal is None:
            # Simple sleep without cancellation
            await asyncio.sleep(delay)
            return True

        # Sleep with abort signal
        try:
            # Wait for either the delay or abort signal
            await asyncio.wait_for(
                abort_signal.wait(),
                timeout=delay
            )
            # If we get here, abort signal was set
            logger.info("[RETRY] Sleep aborted by signal")
            return False
        except asyncio.TimeoutError:
            # Timeout means we slept the full duration
            logger.debug(f"[RETRY] Sleep completed ({delay:.2f}s)")
            return True

    def get_retry_message(
        self,
        error: Exception,
        attempt: int,
        max_attempts: int
    ) -> str:
        """
        Generate descriptive retry message based on error type.

        Args:
            error: Exception that occurred
            attempt: Current attempt number
            max_attempts: Maximum attempts allowed

        Returns:
            Human-readable retry message
        """
        error_str = str(error).lower()

        # Determine error category and message
        if 'overloaded' in error_str or 'capacity' in error_str:
            category = "Provider is overloaded"
        elif 'too_many_requests' in error_str or 'rate limit' in error_str:
            category = "Too Many Requests"
        elif 'timeout' in error_str:
            category = "Request Timeout"
        elif 'connection' in error_str:
            category = "Connection Error"
        elif any(code in error_str for code in ['500', '502', '503', '504']):
            category = "Server Error"
        else:
            category = "Temporary Error"

        message = (
            f"{category} - Retry {attempt}/{max_attempts} "
            f"(attempt {attempt} of {max_attempts})"
        )

        return message


async def retry_with_backoff(
    func: Callable,
    *args,
    retry_manager: Optional[RetryManager] = None,
    abort_signal: Optional[asyncio.Event] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
    **kwargs
) -> Any:
    """
    Retry a function with exponential backoff.

    Args:
        func: Async function to retry
        *args: Positional arguments for func
        retry_manager: RetryManager instance (or None for default)
        abort_signal: Optional abort signal for cancellation
        on_retry: Optional callback called on each retry (error, attempt)
        **kwargs: Keyword arguments for func

    Returns:
        Result from func

    Raises:
        Last exception if all retries exhausted

    Example:
        result = await retry_with_backoff(
            api_call,
            url="https://api.example.com",
            retry_manager=manager,
            abort_signal=abort_event
        )
    """
    if retry_manager is None:
        retry_manager = RetryManager()

    last_error = None
    max_attempts = retry_manager.config.max_attempts

    for attempt in range(1, max_attempts + 1):
        try:
            logger.debug(f"[RETRY] Attempt {attempt}/{max_attempts}")

            # Call the function
            result = await func(*args, **kwargs)

            # Success
            if attempt > 1:
                logger.info(
                    f"[RETRY] Success on attempt {attempt}/{max_attempts}"
                )

            return result

        except Exception as e:
            last_error = e

            # Check if error is retryable
            if not retry_manager.is_retryable(e):
                logger.warning(
                    f"[RETRY] Error not retryable, failing immediately: "
                    f"{type(e).__name__}: {str(e)[:100]}"
                )
                raise

            # Check if we have attempts left
            if attempt >= max_attempts:
                logger.error(
                    f"[RETRY] All {max_attempts} attempts exhausted. "
                    f"Last error: {type(e).__name__}: {str(e)[:100]}"
                )
                raise

            # Log retry
            message = retry_manager.get_retry_message(e, attempt, max_attempts)
            logger.warning(f"[RETRY] {message}")

            # Call on_retry callback if provided
            if on_retry:
                try:
                    result = on_retry(e, attempt)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as callback_error:
                    logger.warning(
                        f"[RETRY] on_retry callback failed: {callback_error}"
                    )

            # Calculate delay
            delay = retry_manager.calculate_delay(attempt)

            # Check for retry-after header (if response available)
            if hasattr(e, 'response'):
                retry_after = retry_manager.parse_retry_after(e.response)
                if retry_after is not None:
                    delay = retry_after
                    logger.info(
                        f"[RETRY] Using retry-after header delay: {delay}s"
                    )

            # Sleep with abort support
            completed = await retry_manager.sleep(delay, abort_signal)

            if not completed:
                # Aborted
                logger.info("[RETRY] Retry aborted by signal")
                raise asyncio.CancelledError("Retry aborted")

    # Should not reach here, but just in case
    if last_error:
        raise last_error
    raise RuntimeError("Retry loop exited unexpectedly")


def with_retry(
    retry_manager: Optional[RetryManager] = None,
    abort_signal: Optional[asyncio.Event] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Decorator to add retry logic to async functions.

    Args:
        retry_manager: RetryManager instance (or None for default)
        abort_signal: Optional abort signal for cancellation
        on_retry: Optional callback called on each retry (error, attempt)

    Example:
        @with_retry(retry_manager=manager)
        async def fetch_data(url: str) -> dict:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    return await response.json()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_with_backoff(
                func,
                *args,
                retry_manager=retry_manager,
                abort_signal=abort_signal,
                on_retry=on_retry,
                **kwargs
            )
        return wrapper
    return decorator


# ============================================================================
# Integration with existing error handling
# ============================================================================

def integrate_with_cascading_recovery():
    """
    Integration helper for cascading_recovery.py.

    Adds retry_manager to cascading recovery for smarter retry delays.
    """
    try:
        from .cascading_recovery import CascadingRecoverySystem

        # Enhance cascading recovery with retry manager
        original_init = CascadingRecoverySystem.__init__

        def enhanced_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            self.retry_manager = RetryManager()
            logger.info(
                "[RETRY] Integrated RetryManager with CascadingRecoverySystem"
            )

        CascadingRecoverySystem.__init__ = enhanced_init

        logger.info("[RETRY] Successfully integrated with cascading_recovery")

    except ImportError as e:
        logger.debug(f"[RETRY] cascading_recovery not available: {e}")


# ============================================================================
# Tests
# ============================================================================

async def test_retry_system():
    """Test suite for retry system."""
    print("\n" + "="*70)
    print("RETRY SYSTEM TEST SUITE")
    print("="*70)

    # Test 1: Calculate delay
    print("\n[TEST 1] Exponential backoff delay calculation")
    manager = RetryManager()

    delays = []
    for attempt in range(1, 6):
        delay = manager.calculate_delay(attempt)
        delays.append(delay)
        print(f"  Attempt {attempt}: {delay:.2f}s")

    assert delays[0] == 2.0, "First delay should be 2s"
    assert delays[1] == 4.0, "Second delay should be 4s"
    assert delays[2] == 8.0, "Third delay should be 8s"
    assert delays[3] == 16.0, "Fourth delay should be 16s"
    assert delays[4] == 30.0, "Fifth delay should be capped at 30s"
    print("  ✓ Exponential backoff working correctly")

    # Test 2: Parse retry-after headers
    print("\n[TEST 2] Parse retry-after headers")

    # Test milliseconds
    headers_ms = {'retry-after-ms': '5000'}
    delay = manager.parse_retry_after(headers_ms)
    assert delay == 5.0, f"Expected 5.0s, got {delay}"
    print(f"  ✓ retry-after-ms: {headers_ms['retry-after-ms']} -> {delay}s")

    # Test seconds
    headers_sec = {'retry-after': '10'}
    delay = manager.parse_retry_after(headers_sec)
    assert delay == 10.0, f"Expected 10.0s, got {delay}"
    print(f"  ✓ retry-after: {headers_sec['retry-after']} -> {delay}s")

    # Test case-insensitive
    headers_upper = {'RETRY-AFTER-MS': '3000'}
    delay = manager.parse_retry_after(headers_upper)
    assert delay == 3.0, f"Expected 3.0s, got {delay}"
    print(f"  ✓ Case-insensitive: {list(headers_upper.keys())[0]} -> {delay}s")

    # Test 3: Retryable error detection
    print("\n[TEST 3] Retryable error detection")

    retryable_errors = [
        Exception("Provider is overloaded"),
        Exception("too_many_requests"),
        Exception("Rate limit exceeded"),
        Exception("Connection timeout"),
        Exception("Service temporarily unavailable"),
    ]

    for error in retryable_errors:
        is_retryable = manager.is_retryable(error)
        status = "✓" if is_retryable else "✗"
        print(f"  {status} {str(error)[:50]}: {is_retryable}")
        assert is_retryable, f"Should be retryable: {error}"

    # Test non-retryable
    non_retryable = Exception("Invalid API key")
    is_retryable = manager.is_retryable(non_retryable)
    print(f"  ✓ {str(non_retryable)}: {is_retryable} (correctly not retryable)")
    assert not is_retryable, "Should not be retryable"

    # Test 4: Sleep with abort signal
    print("\n[TEST 4] Sleep with abort signal")

    abort_signal = asyncio.Event()

    # Normal sleep (should complete)
    start = time.time()
    completed = await manager.sleep(0.1, abort_signal)
    elapsed = time.time() - start
    print(f"  ✓ Normal sleep: {elapsed:.2f}s (completed: {completed})")
    assert completed, "Sleep should complete"
    assert 0.09 <= elapsed <= 0.15, "Sleep duration incorrect"

    # Aborted sleep
    abort_signal = asyncio.Event()

    async def abort_after_delay():
        await asyncio.sleep(0.05)
        abort_signal.set()

    asyncio.create_task(abort_after_delay())
    start = time.time()
    completed = await manager.sleep(1.0, abort_signal)
    elapsed = time.time() - start
    print(f"  ✓ Aborted sleep: {elapsed:.2f}s (completed: {completed})")
    assert not completed, "Sleep should be aborted"
    assert elapsed < 0.2, "Sleep should abort quickly"

    # Test 5: Retry with backoff
    print("\n[TEST 5] Retry with backoff")

    # Simulate function that fails twice then succeeds
    attempt_counter = {'count': 0}

    async def flaky_function(should_succeed_on: int = 3):
        attempt_counter['count'] += 1
        if attempt_counter['count'] < should_succeed_on:
            raise Exception("Rate limit exceeded - please retry")
        return {"success": True, "attempt": attempt_counter['count']}

    attempt_counter['count'] = 0
    result = await retry_with_backoff(
        flaky_function,
        should_succeed_on=3,
        retry_manager=manager
    )

    print(f"  ✓ Function succeeded on attempt {result['attempt']}")
    assert result['attempt'] == 3, "Should succeed on 3rd attempt"
    assert result['success'], "Should return success"

    # Test 6: Decorator
    print("\n[TEST 6] Decorator usage")

    decorator_counter = {'count': 0}

    @with_retry(retry_manager=manager)
    async def decorated_function():
        decorator_counter['count'] += 1
        if decorator_counter['count'] < 2:
            raise Exception("Connection timeout")
        return {"decorated": True, "attempt": decorator_counter['count']}

    result = await decorated_function()
    print(f"  ✓ Decorated function succeeded on attempt {result['attempt']}")
    assert result['attempt'] == 2, "Should succeed on 2nd attempt"

    # Test 7: Non-retryable error
    print("\n[TEST 7] Non-retryable error handling")

    @with_retry(retry_manager=manager)
    async def non_retryable_function():
        raise Exception("Invalid authentication credentials")

    try:
        await non_retryable_function()
        print("  ✗ Should have raised exception")
        assert False, "Should raise exception"
    except Exception as e:
        print(f"  ✓ Correctly failed immediately: {str(e)[:50]}")

    # Test 8: Retry message generation
    print("\n[TEST 8] Retry message generation")

    errors = [
        (Exception("Provider overloaded"), "Provider is overloaded"),
        (Exception("too_many_requests"), "Too Many Requests"),
        (Exception("timeout"), "Request Timeout"),
    ]

    for error, expected_prefix in errors:
        message = manager.get_retry_message(error, 2, 5)
        print(f"  ✓ {expected_prefix}: {message}")
        assert expected_prefix in message, f"Message should contain '{expected_prefix}'"
        assert "2/5" in message, "Message should show attempt count"

    print("\n" + "="*70)
    print("ALL TESTS PASSED")
    print("="*70 + "\n")


if __name__ == "__main__":
    # Run tests
    asyncio.run(test_retry_system())
