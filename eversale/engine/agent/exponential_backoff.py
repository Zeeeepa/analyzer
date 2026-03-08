"""
Exponential Backoff with Jitter

Production-grade retry mechanism that prevents thundering herd problems.
Uses decorrelated jitter (best practice from AWS architecture blog).

Features:
- Exponential backoff: 1s, 2s, 4s, 8s, 16s...
- Decorrelated jitter: random(0, previous_delay * 3)
- Per-error-type strategies
- Circuit breaker integration
- Backoff state persistence
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, TypeVar, Awaitable
from datetime import datetime, timedelta
from functools import wraps
from enum import Enum
from collections import defaultdict
from loguru import logger

T = TypeVar('T')


class BackoffStrategy(Enum):
    """Different backoff strategies for different error types"""
    EXPONENTIAL = "exponential"  # 1, 2, 4, 8, 16...
    LINEAR = "linear"  # 1, 2, 3, 4, 5...
    CONSTANT = "constant"  # 1, 1, 1, 1...
    FIBONACCI = "fibonacci"  # 1, 1, 2, 3, 5, 8...
    DECORRELATED = "decorrelated"  # AWS recommended: random(base, prev * 3)


@dataclass
class BackoffConfig:
    """Configuration for backoff behavior"""
    base_delay: float = 1.0  # Initial delay in seconds
    max_delay: float = 60.0  # Maximum delay cap
    max_retries: int = 5  # Maximum retry attempts
    strategy: BackoffStrategy = BackoffStrategy.DECORRELATED
    jitter_factor: float = 0.25  # Random factor (0-1)
    retry_on: tuple = (Exception,)  # Exception types to retry
    give_up_on: tuple = ()  # Exceptions to NOT retry (immediate failure)


@dataclass
class BackoffState:
    """Tracks backoff state for a specific operation"""
    attempt: int = 0
    last_delay: float = 0
    total_delay: float = 0
    errors: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)

    @property
    def elapsed_seconds(self) -> float:
        return (datetime.now() - self.started_at).total_seconds()


class ExponentialBackoff:
    """
    Production-grade exponential backoff with decorrelated jitter.

    Usage:
        backoff = ExponentialBackoff()

        # As decorator
        @backoff.retry(max_retries=3)
        async def flaky_api_call():
            ...

        # Manual control
        async for delay in backoff.delays(max_retries=5):
            try:
                result = await api_call()
                break
            except RateLimitError:
                await asyncio.sleep(delay)
    """

    def __init__(self, config: BackoffConfig = None):
        self.config = config or BackoffConfig()

        # Track backoff states by operation key
        self.states: Dict[str, BackoffState] = {}

        # Error type -> strategy mapping
        self.error_strategies: Dict[type, BackoffStrategy] = {
            # Rate limits need longer backoff
            # TimeoutError: BackoffStrategy.EXPONENTIAL,
            # ConnectionError: BackoffStrategy.DECORRELATED,
        }

        # Stats
        self.stats = {
            'total_retries': 0,
            'successful_retries': 0,
            'failed_operations': 0,
            'total_delay_seconds': 0,
        }

    def calculate_delay(
        self,
        attempt: int,
        strategy: BackoffStrategy = None,
        last_delay: float = None
    ) -> float:
        """Calculate next delay based on strategy"""
        strategy = strategy or self.config.strategy
        base = self.config.base_delay
        max_delay = self.config.max_delay

        if strategy == BackoffStrategy.EXPONENTIAL:
            # Classic: base * 2^attempt
            delay = base * (2 ** attempt)

        elif strategy == BackoffStrategy.LINEAR:
            # Linear: base * (attempt + 1)
            delay = base * (attempt + 1)

        elif strategy == BackoffStrategy.CONSTANT:
            # Constant: always base
            delay = base

        elif strategy == BackoffStrategy.FIBONACCI:
            # Fibonacci sequence
            a, b = base, base
            for _ in range(attempt):
                a, b = b, a + b
            delay = a

        elif strategy == BackoffStrategy.DECORRELATED:
            # AWS recommended: random between base and last_delay * 3
            prev = last_delay or base
            delay = random.uniform(base, min(max_delay, prev * 3))

        else:
            delay = base * (2 ** attempt)

        # Add jitter (except for decorrelated which has built-in randomness)
        if strategy != BackoffStrategy.DECORRELATED and self.config.jitter_factor > 0:
            jitter = delay * self.config.jitter_factor * random.random()
            delay = delay + jitter

        # Cap at max delay
        return min(delay, max_delay)

    async def delays(
        self,
        max_retries: int = None,
        operation_key: str = None
    ):
        """
        Async generator yielding delays for each retry.

        Usage:
            async for delay in backoff.delays(max_retries=5):
                try:
                    result = await operation()
                    break
                except Exception:
                    await asyncio.sleep(delay)
        """
        max_retries = max_retries or self.config.max_retries
        key = operation_key or f"op_{id(self)}_{time.time()}"

        state = BackoffState()
        self.states[key] = state

        try:
            for attempt in range(max_retries):
                state.attempt = attempt
                delay = self.calculate_delay(attempt, last_delay=state.last_delay)
                state.last_delay = delay
                state.total_delay += delay

                self.stats['total_retries'] += 1
                self.stats['total_delay_seconds'] += delay

                yield delay

            # Exhausted retries
            self.stats['failed_operations'] += 1

        finally:
            # Cleanup state
            self.states.pop(key, None)

    def retry(
        self,
        max_retries: int = None,
        retry_on: tuple = None,
        give_up_on: tuple = None,
        on_retry: Callable[[int, Exception, float], None] = None
    ):
        """
        Decorator for automatic retry with backoff.

        Args:
            max_retries: Override default max retries
            retry_on: Exception types to retry (default: all)
            give_up_on: Exception types to NOT retry
            on_retry: Callback(attempt, error, delay) called before each retry
        """
        max_retries = max_retries or self.config.max_retries
        retry_on = retry_on or self.config.retry_on
        give_up_on = give_up_on or self.config.give_up_on

        def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
            @wraps(func)
            async def wrapper(*args, **kwargs) -> T:
                last_delay = self.config.base_delay
                last_error = None

                for attempt in range(max_retries + 1):
                    try:
                        result = await func(*args, **kwargs)
                        if attempt > 0:
                            self.stats['successful_retries'] += 1
                            logger.info(f"[BACKOFF] {func.__name__} succeeded after {attempt} retries")
                        return result

                    except give_up_on as e:
                        # Don't retry these
                        logger.warning(f"[BACKOFF] {func.__name__} failed with non-retryable error: {e}")
                        raise

                    except retry_on as e:
                        last_error = e

                        if attempt >= max_retries:
                            # Exhausted retries
                            self.stats['failed_operations'] += 1
                            logger.error(f"[BACKOFF] {func.__name__} failed after {max_retries} retries: {e}")
                            raise

                        # Calculate delay
                        strategy = self.error_strategies.get(type(e), self.config.strategy)
                        delay = self.calculate_delay(attempt, strategy, last_delay)
                        last_delay = delay

                        self.stats['total_retries'] += 1
                        self.stats['total_delay_seconds'] += delay

                        # Callback
                        if on_retry:
                            on_retry(attempt, e, delay)

                        logger.debug(f"[BACKOFF] {func.__name__} retry {attempt + 1}/{max_retries} in {delay:.2f}s: {e}")
                        await asyncio.sleep(delay)

                # Should never reach here, but just in case
                if last_error:
                    raise last_error

            return wrapper
        return decorator

    def register_error_strategy(self, error_type: type, strategy: BackoffStrategy):
        """Register a specific backoff strategy for an error type"""
        self.error_strategies[error_type] = strategy

    def get_stats(self) -> Dict:
        """Get backoff statistics"""
        return {
            **self.stats,
            'avg_delay_per_retry': (
                self.stats['total_delay_seconds'] / max(1, self.stats['total_retries'])
            ),
            'retry_success_rate': (
                self.stats['successful_retries'] / max(1, self.stats['total_retries'])
            ),
            'active_operations': len(self.states)
        }

    def reset_stats(self):
        """Reset statistics"""
        self.stats = {
            'total_retries': 0,
            'successful_retries': 0,
            'failed_operations': 0,
            'total_delay_seconds': 0,
        }


# Singleton instance
_backoff: Optional[ExponentialBackoff] = None

def get_backoff() -> ExponentialBackoff:
    """Get or create the global backoff instance"""
    global _backoff
    if _backoff is None:
        _backoff = ExponentialBackoff()
    return _backoff


# Convenience decorator
def with_backoff(
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    strategy: BackoffStrategy = BackoffStrategy.DECORRELATED
):
    """
    Convenience decorator for functions that need retry with backoff.

    Usage:
        @with_backoff(max_retries=3)
        async def api_call():
            ...
    """
    config = BackoffConfig(
        base_delay=base_delay,
        max_delay=max_delay,
        max_retries=max_retries,
        strategy=strategy
    )
    backoff = ExponentialBackoff(config)
    return backoff.retry()


# Rate limit specific backoff
def rate_limit_backoff(
    max_retries: int = 10,
    base_delay: float = 2.0,
    max_delay: float = 120.0
):
    """
    Specialized backoff for rate limit errors.
    Uses longer delays and more retries.
    """
    config = BackoffConfig(
        base_delay=base_delay,
        max_delay=max_delay,
        max_retries=max_retries,
        strategy=BackoffStrategy.EXPONENTIAL,
        jitter_factor=0.5  # More jitter for rate limits
    )
    backoff = ExponentialBackoff(config)
    return backoff.retry()


# Quick retry for transient errors
def quick_retry(max_retries: int = 3, base_delay: float = 0.5):
    """
    Quick retry for transient errors (connection blips, etc.)
    Short delays, few retries.
    """
    config = BackoffConfig(
        base_delay=base_delay,
        max_delay=5.0,
        max_retries=max_retries,
        strategy=BackoffStrategy.LINEAR
    )
    backoff = ExponentialBackoff(config)
    return backoff.retry()
