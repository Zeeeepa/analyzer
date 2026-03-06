"""
Smart Retry System - Intelligent failure handling for agents.

Addresses the biggest agent weaknesses:
1. Stuck loops - Detects repeated failures, switches strategy
2. Silent failures - Verifies success, alerts on issues
3. No learning - Records what works/fails per site/task
4. Hallucination - Cross-checks results against expectations
5. Brittle selectors - Tries multiple approaches

Enhanced Features (Dec 2024):
- Exponential backoff with jitter
- Per-error-type retry strategies
- Circuit breaker integration
- Smart retry conditions (permanent vs transient)
- Partial retry support
- Retry context and decorators

Usage:
    # Context manager
    async with retry_context(max_attempts=3, backoff=True):
        result = await do_action()

    # Decorator
    @with_retry(max_attempts=5, strategy="exponential")
    async def my_action():
        return await do_something()

    # Manual
    retry_manager = SmartRetryManager()
    async with retry_manager.attempt("click_button", context={"url": url}) as attempt:
        result = await do_action()
        attempt.record_result(result, success=True)
"""

import json
import hashlib
import time
import asyncio
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Tuple, Union
from dataclasses import dataclass, field
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from functools import wraps
from enum import Enum
from loguru import logger
from rich.console import Console

console = Console()


class ErrorType(Enum):
    """Error types with specific retry strategies."""
    NETWORK_TIMEOUT = "network_timeout"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    CAPTCHA = "captcha"
    SELECTOR_NOT_FOUND = "selector_not_found"
    STALE_ELEMENT = "stale_element"
    NOT_FOUND = "not_found"
    AUTH_REQUIRED = "auth_required"
    CONNECTION_RESET = "connection_reset"
    PAGE_CRASH = "page_crash"
    UNKNOWN = "unknown"


class RetryStrategy(Enum):
    """Retry backoff strategies."""
    IMMEDIATE = "immediate"  # No delay
    LINEAR = "linear"  # Base delay * attempt
    EXPONENTIAL = "exponential"  # Base delay * 2^attempt
    EXPONENTIAL_JITTER = "exponential_jitter"  # Exponential + random jitter


@dataclass
class RetryConfig:
    """Configuration for retry behavior per error type."""
    error_type: ErrorType
    max_attempts: int
    strategy: RetryStrategy
    base_delay_ms: int
    max_delay_ms: int
    should_retry: bool
    immediate_retry_once: bool = False  # For network timeouts
    requires_escalation: bool = False  # For CAPTCHA, auth


# Default retry configurations per error type
DEFAULT_RETRY_CONFIGS = {
    ErrorType.NETWORK_TIMEOUT: RetryConfig(
        error_type=ErrorType.NETWORK_TIMEOUT,
        max_attempts=3,
        strategy=RetryStrategy.IMMEDIATE,  # Retry immediately once
        base_delay_ms=0,
        max_delay_ms=10000,
        should_retry=True,
        immediate_retry_once=True
    ),
    ErrorType.RATE_LIMIT: RetryConfig(
        error_type=ErrorType.RATE_LIMIT,
        max_attempts=3,
        strategy=RetryStrategy.EXPONENTIAL_JITTER,
        base_delay_ms=30000,  # Start at 30s
        max_delay_ms=300000,  # Cap at 5 minutes
        should_retry=True
    ),
    ErrorType.SERVER_ERROR: RetryConfig(
        error_type=ErrorType.SERVER_ERROR,
        max_attempts=4,
        strategy=RetryStrategy.EXPONENTIAL_JITTER,
        base_delay_ms=5000,  # Start at 5s
        max_delay_ms=60000,  # Cap at 60s
        should_retry=True
    ),
    ErrorType.CAPTCHA: RetryConfig(
        error_type=ErrorType.CAPTCHA,
        max_attempts=1,
        strategy=RetryStrategy.IMMEDIATE,
        base_delay_ms=0,
        max_delay_ms=0,
        should_retry=False,  # Don't retry, escalate
        requires_escalation=True
    ),
    ErrorType.SELECTOR_NOT_FOUND: RetryConfig(
        error_type=ErrorType.SELECTOR_NOT_FOUND,
        max_attempts=3,
        strategy=RetryStrategy.LINEAR,
        base_delay_ms=1000,  # Short retry
        max_delay_ms=5000,
        should_retry=True
    ),
    ErrorType.STALE_ELEMENT: RetryConfig(
        error_type=ErrorType.STALE_ELEMENT,
        max_attempts=3,
        strategy=RetryStrategy.IMMEDIATE,
        base_delay_ms=500,
        max_delay_ms=2000,
        should_retry=True
    ),
    ErrorType.NOT_FOUND: RetryConfig(
        error_type=ErrorType.NOT_FOUND,
        max_attempts=1,
        strategy=RetryStrategy.IMMEDIATE,
        base_delay_ms=0,
        max_delay_ms=0,
        should_retry=False  # 404 is permanent
    ),
    ErrorType.AUTH_REQUIRED: RetryConfig(
        error_type=ErrorType.AUTH_REQUIRED,
        max_attempts=1,
        strategy=RetryStrategy.IMMEDIATE,
        base_delay_ms=0,
        max_delay_ms=0,
        should_retry=False,  # Auth required is permanent
        requires_escalation=True
    ),
    ErrorType.CONNECTION_RESET: RetryConfig(
        error_type=ErrorType.CONNECTION_RESET,
        max_attempts=3,
        strategy=RetryStrategy.EXPONENTIAL_JITTER,
        base_delay_ms=1000,
        max_delay_ms=10000,
        should_retry=True
    ),
    ErrorType.PAGE_CRASH: RetryConfig(
        error_type=ErrorType.PAGE_CRASH,
        max_attempts=2,
        strategy=RetryStrategy.LINEAR,
        base_delay_ms=2000,
        max_delay_ms=10000,
        should_retry=True
    ),
    ErrorType.UNKNOWN: RetryConfig(
        error_type=ErrorType.UNKNOWN,
        max_attempts=3,
        strategy=RetryStrategy.EXPONENTIAL_JITTER,
        base_delay_ms=2000,
        max_delay_ms=30000,
        should_retry=True
    ),
}


class ErrorClassifier:
    """Classifies errors into types for smart retry decisions."""

    @staticmethod
    def classify(error: Union[str, Exception]) -> ErrorType:
        """
        Classify an error into an ErrorType.

        Args:
            error: Error message string or exception

        Returns:
            ErrorType enum value
        """
        error_str = str(error).lower()

        # Network timeouts
        if any(x in error_str for x in ["timeout", "timed out", "time out"]):
            return ErrorType.NETWORK_TIMEOUT

        # Rate limiting
        if any(x in error_str for x in ["429", "rate limit", "too many requests", "throttle"]):
            return ErrorType.RATE_LIMIT

        # Server errors
        if any(x in error_str for x in ["500", "502", "503", "504", "server error", "internal server"]):
            return ErrorType.SERVER_ERROR

        # CAPTCHA
        if any(x in error_str for x in ["captcha", "recaptcha", "challenge", "bot detected"]):
            return ErrorType.CAPTCHA

        # Selector issues
        if any(x in error_str for x in ["selector", "element not found", "no such element", "cannot find element"]):
            return ErrorType.SELECTOR_NOT_FOUND

        # Stale element
        if any(x in error_str for x in ["stale element", "element is not attached", "detached"]):
            return ErrorType.STALE_ELEMENT

        # Not found
        if any(x in error_str for x in ["404", "not found", "does not exist"]):
            return ErrorType.NOT_FOUND

        # Auth required
        if any(x in error_str for x in ["auth", "login required", "unauthorized", "401", "403", "forbidden"]):
            return ErrorType.AUTH_REQUIRED

        # Connection reset
        if any(x in error_str for x in ["connection reset", "connection closed", "connection refused", "econnreset"]):
            return ErrorType.CONNECTION_RESET

        # Page crash
        if any(x in error_str for x in ["page crash", "renderer", "out of memory", "oom"]):
            return ErrorType.PAGE_CRASH

        return ErrorType.UNKNOWN

    @staticmethod
    def is_permanent(error_type: ErrorType) -> bool:
        """Check if error is permanent (shouldn't retry)."""
        return error_type in [ErrorType.NOT_FOUND, ErrorType.AUTH_REQUIRED]

    @staticmethod
    def is_transient(error_type: ErrorType) -> bool:
        """Check if error is transient (retry immediately)."""
        return error_type in [
            ErrorType.NETWORK_TIMEOUT,
            ErrorType.CONNECTION_RESET,
            ErrorType.STALE_ELEMENT
        ]


class BackoffCalculator:
    """Calculates retry delays with various strategies."""

    @staticmethod
    def calculate_delay(
        strategy: RetryStrategy,
        attempt: int,
        base_delay_ms: int,
        max_delay_ms: int
    ) -> int:
        """
        Calculate delay in milliseconds for this attempt.

        Args:
            strategy: Retry strategy to use
            attempt: Attempt number (0-indexed)
            base_delay_ms: Base delay in milliseconds
            max_delay_ms: Maximum delay cap in milliseconds

        Returns:
            Delay in milliseconds
        """
        if strategy == RetryStrategy.IMMEDIATE:
            return 0

        elif strategy == RetryStrategy.LINEAR:
            delay = base_delay_ms * (attempt + 1)

        elif strategy == RetryStrategy.EXPONENTIAL:
            delay = base_delay_ms * (2 ** attempt)

        elif strategy == RetryStrategy.EXPONENTIAL_JITTER:
            # Exponential backoff with jitter to prevent thundering herd
            exponential_delay = base_delay_ms * (2 ** attempt)
            # Add random jitter: 0% to 25% of the delay
            jitter = random.uniform(0, exponential_delay * 0.25)
            delay = exponential_delay + jitter

        else:
            delay = base_delay_ms

        # Cap at max delay
        return min(int(delay), max_delay_ms)


@dataclass
class FailurePattern:
    """Tracks a specific failure pattern."""
    pattern_hash: str
    action: str
    error_signature: str
    occurrences: int = 0
    last_seen: datetime = field(default_factory=datetime.now)
    strategies_tried: List[str] = field(default_factory=list)
    successful_strategy: Optional[str] = None


@dataclass
class ActionAttempt:
    """Records a single action attempt."""
    action: str
    strategy: str
    args: Dict[str, Any]
    timestamp: datetime
    success: bool
    error: Optional[str] = None
    result_hash: Optional[str] = None
    duration_ms: int = 0


class SmartRetryManager:
    """
    Intelligent retry manager that:
    - Detects when we're stuck in a loop
    - Switches strategies automatically
    - Learns from failures
    - Escalates to user when truly stuck
    - Verifies success (anti-hallucination)
    - Circuit breaker integration
    - Error-type-specific retry strategies
    - Exponential backoff with jitter
    - Partial retry support
    """

    def __init__(
        self,
        max_same_strategy_attempts: int = 3,
        max_total_attempts: int = 10,
        loop_detection_window: int = 5,
        memory_path: Path = Path("memory/retry_patterns.json"),
        max_attempts_history: int = 100,
        enable_circuit_breaker: bool = True
    ):
        self.max_same_strategy = max_same_strategy_attempts
        self.max_total = max_total_attempts
        self.loop_window = loop_detection_window
        self.memory_path = memory_path
        self.max_attempts_history = max_attempts_history
        self.enable_circuit_breaker = enable_circuit_breaker

        # Runtime state - using deque with maxlen to prevent unbounded growth
        self.current_attempts: deque = deque(maxlen=max_attempts_history)
        self.failure_patterns: Dict[str, FailurePattern] = {}
        self.strategy_success_rates: Dict[str, Dict[str, float]] = defaultdict(dict)

        # Error tracking per domain for circuit breaker
        self.domain_errors: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
        self.domain_cooloff: Dict[str, datetime] = {}

        # Retry configs
        self.retry_configs = DEFAULT_RETRY_CONFIGS.copy()

        # Strategy registry
        self.strategies: Dict[str, List[Callable]] = {}
        self._register_default_strategies()

        # Circuit breaker integration
        self._circuit_breaker = None
        if enable_circuit_breaker:
            try:
                from .circuit_breaker import get_circuit_breaker
                self._circuit_breaker = get_circuit_breaker()
            except ImportError:
                logger.warning("Circuit breaker not available, continuing without it")

        # Load learned patterns
        self._load_memory()

    def _register_default_strategies(self):
        """Register default alternative strategies for common actions."""

        # Click strategies
        self.strategies["click"] = [
            ("css_selector", "Try CSS selector"),
            ("xpath", "Try XPath"),
            ("text_content", "Try by text content"),
            ("coordinates", "Try by coordinates"),
            ("javascript", "Try JavaScript click"),
            ("focus_then_enter", "Focus + Enter key"),
        ]

        # Fill/type strategies
        self.strategies["fill"] = [
            ("direct_fill", "Direct fill"),
            ("clear_then_type", "Clear field first"),
            ("javascript_value", "Set via JavaScript"),
            ("type_slowly", "Type character by character"),
            ("focus_first", "Focus before typing"),
        ]

        # Navigate strategies
        self.strategies["navigate"] = [
            ("direct", "Direct navigation"),
            ("wait_longer", "Wait for page load"),
            ("clear_cookies", "Clear cookies first"),
            ("new_context", "Fresh browser context"),
        ]

        # Extract strategies
        self.strategies["extract"] = [
            ("css_selector", "CSS selector"),
            ("xpath", "XPath query"),
            ("regex", "Regex on page text"),
            ("visual", "Visual/OCR extraction"),
            ("javascript", "JavaScript extraction"),
        ]

    def _load_memory(self):
        """Load learned patterns from disk."""
        if self.memory_path.exists():
            try:
                data = json.loads(self.memory_path.read_text())
                self.strategy_success_rates = defaultdict(dict, data.get("success_rates", {}))
                # Restore failure patterns
                for ph, pd in data.get("failure_patterns", {}).items():
                    self.failure_patterns[ph] = FailurePattern(
                        pattern_hash=ph,
                        action=pd["action"],
                        error_signature=pd["error_signature"],
                        occurrences=pd["occurrences"],
                        strategies_tried=pd["strategies_tried"],
                        successful_strategy=pd.get("successful_strategy")
                    )
            except Exception as e:
                logger.warning(f"Failed to load retry memory: {e}")

    def _save_memory(self):
        """Persist learned patterns to disk."""
        try:
            self.memory_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "success_rates": dict(self.strategy_success_rates),
                "failure_patterns": {
                    ph: {
                        "action": p.action,
                        "error_signature": p.error_signature,
                        "occurrences": p.occurrences,
                        "strategies_tried": p.strategies_tried,
                        "successful_strategy": p.successful_strategy,
                    }
                    for ph, p in self.failure_patterns.items()
                },
                "updated": datetime.now().isoformat(),
            }
            self.memory_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning(f"Failed to save retry memory: {e}")

    def _get_error_signature(self, error: str) -> str:
        """Extract a normalized signature from an error message."""
        # Remove variable parts (numbers, timestamps, IDs)
        import re
        normalized = re.sub(r'\d+', 'N', error)
        normalized = re.sub(r'[a-f0-9]{8,}', 'ID', normalized, flags=re.I)
        normalized = re.sub(r'\s+', ' ', normalized)
        return hashlib.md5(normalized.encode()).hexdigest()[:12]

    def _get_pattern_hash(self, action: str, context: Dict, error: str) -> str:
        """Generate a hash for this failure pattern."""
        sig = self._get_error_signature(error)
        ctx_str = json.dumps(sorted(context.items()), default=str)
        return hashlib.md5(f"{action}:{ctx_str}:{sig}".encode()).hexdigest()[:16]

    def is_stuck_in_loop(self) -> Tuple[bool, str]:
        """Detect if we're stuck repeating the same failed action."""
        if len(self.current_attempts) < self.loop_window:
            return False, ""

        recent = self.current_attempts[-self.loop_window:]

        # Check if all recent attempts are the same action with same result
        if all(not a.success for a in recent):
            actions = [a.action for a in recent]
            errors = [a.error for a in recent]

            if len(set(actions)) == 1 and len(set(errors)) <= 2:
                return True, f"Stuck on '{actions[0]}' - failed {len(recent)} times with same error"

        return False, ""

    def get_next_strategy(self, action: str, context: Dict, tried: List[str]) -> Optional[Tuple[str, str]]:
        """Get the next untried strategy, prioritized by success rate."""
        action_type = action.split("_")[0] if "_" in action else action

        available = self.strategies.get(action_type, [])
        if not available:
            return None

        # Sort by historical success rate for this context
        context_key = self._context_key(context)

        def score(strategy):
            name = strategy[0]
            if name in tried:
                return -1  # Already tried
            rate = self.strategy_success_rates.get(context_key, {}).get(name, 0.5)
            return rate

        sorted_strategies = sorted(available, key=score, reverse=True)

        for strategy, desc in sorted_strategies:
            if strategy not in tried:
                return strategy, desc

        return None

    def _context_key(self, context: Dict) -> str:
        """Generate a key for this context (e.g., domain)."""
        url = context.get("url", "")
        if url:
            from urllib.parse import urlparse
            return urlparse(url).netloc
        return "default"

    def should_retry(
        self,
        error: Union[str, Exception],
        attempt: int,
        context: Dict
    ) -> Tuple[bool, str, int]:
        """
        Smart decision: should we retry this error?

        Args:
            error: Error that occurred
            attempt: Current attempt number (0-indexed)
            context: Context dict with url, action, etc.

        Returns:
            Tuple of (should_retry, reason, delay_ms)
        """
        # Classify the error
        error_type = ErrorClassifier.classify(error)
        config = self.retry_configs.get(error_type, self.retry_configs[ErrorType.UNKNOWN])

        # Check if error type is retryable
        if not config.should_retry:
            return False, f"{error_type.value} is not retryable", 0

        # Check if we've exceeded max attempts for this error type
        if attempt >= config.max_attempts:
            return False, f"Max attempts ({config.max_attempts}) reached for {error_type.value}", 0

        # Check circuit breaker
        domain = self._context_key(context)
        if self._circuit_breaker and not self._check_circuit_breaker(domain, context.get("action", "unknown")):
            return False, f"Circuit breaker OPEN for {domain}", 0

        # Check domain cooloff
        if domain in self.domain_cooloff:
            cooloff_until = self.domain_cooloff[domain]
            if datetime.now() < cooloff_until:
                remaining = (cooloff_until - datetime.now()).total_seconds()
                return False, f"Domain {domain} in cooloff for {remaining:.1f}s more", 0

        # Calculate backoff delay
        delay_ms = BackoffCalculator.calculate_delay(
            config.strategy,
            attempt,
            config.base_delay_ms,
            config.max_delay_ms
        )

        # Special handling for immediate retry once (network timeouts)
        if config.immediate_retry_once and attempt == 0:
            delay_ms = 0

        reason = f"Retry #{attempt + 1} with {config.strategy.value} backoff ({delay_ms}ms delay)"
        return True, reason, delay_ms

    def _check_circuit_breaker(self, domain: str, action: str) -> bool:
        """
        Check if circuit breaker allows execution.

        Args:
            domain: Domain being accessed
            action: Action being performed

        Returns:
            True if can proceed, False if circuit is open
        """
        if not self._circuit_breaker:
            return True

        circuit_id = f"{domain}:{action}"
        return self._circuit_breaker.can_execute(circuit_id)

    def record_circuit_result(self, domain: str, action: str, success: bool):
        """Record success/failure with circuit breaker."""
        if not self._circuit_breaker:
            return

        circuit_id = f"{domain}:{action}"
        if success:
            self._circuit_breaker.record_success(circuit_id)
        else:
            self._circuit_breaker.record_failure(circuit_id)

    def check_domain_circuit_breaker(self, domain: str) -> Tuple[bool, str]:
        """
        Check if domain has too many consecutive errors (circuit breaker).

        Args:
            domain: Domain to check

        Returns:
            Tuple of (is_broken, reason)
        """
        errors = self.domain_errors.get(domain, deque())
        if len(errors) < 3:
            return False, ""

        # Check last 3 errors
        recent_errors = list(errors)[-3:]
        recent_timestamps = [e["timestamp"] for e in recent_errors]

        # If 3 errors in last 30 seconds, trigger circuit breaker
        time_window = 30  # seconds
        if all((datetime.now() - ts).total_seconds() < time_window for ts in recent_timestamps):
            # Set cooloff period
            cooloff_duration = timedelta(seconds=60)
            self.domain_cooloff[domain] = datetime.now() + cooloff_duration

            return True, f"3 consecutive errors in {time_window}s - cooling off for 60s"

        return False, ""

    def record_domain_error(self, domain: str, error: str):
        """Record an error for a domain."""
        self.domain_errors[domain].append({
            "timestamp": datetime.now(),
            "error": error
        })

    async def partial_retry(
        self,
        items: List[Any],
        processor: Callable,
        context: Dict,
        max_attempts: int = 3
    ) -> Tuple[List[Any], List[Tuple[Any, str]]]:
        """
        Retry only failed items from a batch.

        Args:
            items: List of items to process
            processor: Async function to process each item
            context: Context dict
            max_attempts: Max retry attempts per item

        Returns:
            Tuple of (successful_results, failed_items_with_errors)
        """
        results = []
        failed = []
        attempts = {i: 0 for i in range(len(items))}

        remaining_indices = list(range(len(items)))

        while remaining_indices and max(attempts.values()) < max_attempts:
            retry_indices = []

            for idx in remaining_indices:
                item = items[idx]
                attempts[idx] += 1

                try:
                    result = await processor(item)
                    results.append(result)
                    logger.info(f"Item {idx} succeeded on attempt {attempts[idx]}")
                except Exception as e:
                    error_type = ErrorClassifier.classify(e)

                    # Check if should retry
                    should_retry, reason, delay_ms = self.should_retry(
                        e,
                        attempts[idx] - 1,
                        context
                    )

                    if should_retry and attempts[idx] < max_attempts:
                        retry_indices.append(idx)
                        logger.warning(f"Item {idx} failed (attempt {attempts[idx]}): {e} - {reason}")

                        # Apply backoff
                        if delay_ms > 0:
                            await asyncio.sleep(delay_ms / 1000)
                    else:
                        failed.append((item, str(e)))
                        logger.error(f"Item {idx} failed permanently: {e}")

            remaining_indices = retry_indices

        return results, failed

    def record_attempt(
        self,
        action: str,
        strategy: str,
        args: Dict,
        success: bool,
        error: Optional[str] = None,
        result: Any = None,
        duration_ms: int = 0
    ):
        """Record an action attempt and update learning."""
        attempt = ActionAttempt(
            action=action,
            strategy=strategy,
            args=args,
            timestamp=datetime.now(),
            success=success,
            error=error,
            result_hash=hashlib.md5(str(result).encode()).hexdigest()[:8] if result else None,
            duration_ms=duration_ms
        )

        # Log when the deque is full and an old attempt will be pruned
        if len(self.current_attempts) == self.max_attempts_history:
            oldest = self.current_attempts[0]
            logger.debug(
                f"Pruning oldest attempt from history (limit: {self.max_attempts_history}): "
                f"{oldest.action} from {oldest.timestamp.isoformat()}"
            )

        self.current_attempts.append(attempt)

        # Update success rates
        context_key = self._context_key(args)
        current_rate = self.strategy_success_rates[context_key].get(strategy, 0.5)
        # Exponential moving average
        new_rate = current_rate * 0.8 + (1.0 if success else 0.0) * 0.2
        self.strategy_success_rates[context_key][strategy] = new_rate

        # Update circuit breaker
        domain = self._context_key(args)
        self.record_circuit_result(domain, action, success)

        # Update failure patterns if failed
        if not success and error:
            # Record domain error
            self.record_domain_error(domain, error)

            pattern_hash = self._get_pattern_hash(action, args, error)
            if pattern_hash not in self.failure_patterns:
                self.failure_patterns[pattern_hash] = FailurePattern(
                    pattern_hash=pattern_hash,
                    action=action,
                    error_signature=self._get_error_signature(error)
                )

            pattern = self.failure_patterns[pattern_hash]
            pattern.occurrences += 1
            pattern.last_seen = datetime.now()
            if strategy not in pattern.strategies_tried:
                pattern.strategies_tried.append(strategy)

        # Record successful strategy for pattern
        if success:
            for ph, pattern in self.failure_patterns.items():
                if pattern.action == action and not pattern.successful_strategy:
                    pattern.successful_strategy = strategy

        # Periodically save
        if len(self.current_attempts) % 10 == 0:
            self._save_memory()

    def get_recommendation(self, action: str, context: Dict, error: str) -> Dict[str, Any]:
        """Get intelligent recommendation for how to proceed."""
        pattern_hash = self._get_pattern_hash(action, context, error)

        # Classify error type
        error_type = ErrorClassifier.classify(error)
        config = self.retry_configs.get(error_type, self.retry_configs[ErrorType.UNKNOWN])

        # If requires escalation (CAPTCHA, auth), escalate immediately
        if config.requires_escalation:
            return {
                "action": "escalate",
                "reason": f"{error_type.value} requires user intervention",
                "error_type": error_type.value,
                "confidence": 0.95
            }

        # Check circuit breaker for domain
        domain = self._context_key(context)
        is_broken, break_reason = self.check_domain_circuit_breaker(domain)
        if is_broken:
            return {
                "action": "cooloff",
                "reason": break_reason,
                "domain": domain,
                "confidence": 0.9
            }

        # Check if we've seen this exact pattern before
        if pattern_hash in self.failure_patterns:
            pattern = self.failure_patterns[pattern_hash]

            # If we found a successful strategy before, use it
            if pattern.successful_strategy:
                return {
                    "action": "retry_with_strategy",
                    "strategy": pattern.successful_strategy,
                    "reason": f"Previously successful for this error pattern",
                    "error_type": error_type.value,
                    "confidence": 0.8
                }

            # If we've tried many strategies, escalate
            if len(pattern.strategies_tried) >= 4:
                return {
                    "action": "escalate",
                    "reason": f"Tried {len(pattern.strategies_tried)} strategies without success",
                    "tried": pattern.strategies_tried,
                    "error_type": error_type.value,
                    "confidence": 0.9
                }

        # Check for loop
        is_loop, loop_msg = self.is_stuck_in_loop()
        if is_loop:
            return {
                "action": "break_loop",
                "reason": loop_msg,
                "suggestion": "Try completely different approach or skip this step",
                "error_type": error_type.value,
                "confidence": 0.95
            }

        # Get next strategy to try
        tried = [a.strategy for a in self.current_attempts if a.action == action]
        next_strategy = self.get_next_strategy(action, context, tried)

        if next_strategy:
            return {
                "action": "retry_with_strategy",
                "strategy": next_strategy[0],
                "description": next_strategy[1],
                "reason": f"Trying alternative approach ({len(tried)+1}/{len(self.strategies.get(action.split('_')[0], []))})",
                "error_type": error_type.value,
                "confidence": 0.6
            }

        # No more strategies
        return {
            "action": "escalate",
            "reason": "Exhausted all known strategies",
            "error_type": error_type.value,
            "confidence": 0.95
        }

    def clear_session(self):
        """Clear current session attempts (call between tasks)."""
        self.current_attempts.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get retry statistics."""
        return {
            "session_attempts": len(self.current_attempts),
            "known_patterns": len(self.failure_patterns),
            "patterns_with_solutions": sum(1 for p in self.failure_patterns.values() if p.successful_strategy),
            "strategy_success_rates": dict(self.strategy_success_rates),
        }


class SuccessVerifier:
    """
    Verifies that actions actually succeeded (anti-hallucination).

    Agents often think they succeeded when they didn't.
    This cross-checks results against expectations.
    """

    def __init__(self):
        self.verification_rules: Dict[str, List[Callable]] = {}
        self._register_default_rules()

    def _register_default_rules(self):
        """Register default verification rules."""

        # Click verification
        self.verification_rules["click"] = [
            self._verify_page_changed,
            self._verify_no_error_message,
            self._verify_expected_result,
        ]

        # Navigation verification
        self.verification_rules["navigate"] = [
            self._verify_url_changed,
            self._verify_page_loaded,
            self._verify_no_error_page,
        ]

        # Extraction verification
        self.verification_rules["extract"] = [
            self._verify_data_not_empty,
            self._verify_data_format,
            self._verify_data_reasonable,
        ]

        # Fill verification
        self.verification_rules["fill"] = [
            self._verify_value_set,
            self._verify_no_validation_error,
        ]

    async def verify(
        self,
        action: str,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        page_state: Optional[Dict] = None
    ) -> Tuple[bool, str, float]:
        """
        Verify an action succeeded.

        Returns: (success, reason, confidence)
        """
        action_type = action.split("_")[0]
        rules = self.verification_rules.get(action_type, [])

        if not rules:
            # No verification rules - assume success but low confidence
            return True, "No verification rules", 0.5

        failures = []
        for rule in rules:
            try:
                passed, reason = await rule(expected, actual, page_state)
                if not passed:
                    failures.append(reason)
            except Exception as e:
                logger.debug(f"Verification rule failed: {e}")

        if failures:
            return False, "; ".join(failures), 0.9

        return True, "All checks passed", 0.85

    async def _verify_page_changed(self, expected: Dict, actual: Dict, state: Dict) -> Tuple[bool, str]:
        """Verify the page state changed after click."""
        if state and state.get("url_before") == state.get("url_after"):
            if state.get("content_hash_before") == state.get("content_hash_after"):
                return False, "Page did not change after click"
        return True, ""

    async def _verify_no_error_message(self, expected: Dict, actual: Dict, state: Dict) -> Tuple[bool, str]:
        """Check for error messages on page."""
        if state:
            page_text = state.get("page_text", "").lower()
            error_indicators = ["error", "failed", "invalid", "unable to", "something went wrong"]
            for indicator in error_indicators:
                if indicator in page_text:
                    return False, f"Error indicator found: '{indicator}'"
        return True, ""

    async def _verify_expected_result(self, expected: Dict, actual: Dict, state: Dict) -> Tuple[bool, str]:
        """Verify we got the expected result."""
        if expected.get("should_navigate") and state:
            if expected.get("target_url") and expected["target_url"] not in state.get("url_after", ""):
                return False, f"Did not navigate to expected URL"
        return True, ""

    async def _verify_url_changed(self, expected: Dict, actual: Dict, state: Dict) -> Tuple[bool, str]:
        """Verify URL changed for navigation."""
        if expected.get("url") and state:
            if expected["url"] not in state.get("url_after", ""):
                return False, "URL did not change to expected target"
        return True, ""

    async def _verify_page_loaded(self, expected: Dict, actual: Dict, state: Dict) -> Tuple[bool, str]:
        """Verify page fully loaded."""
        if state and state.get("load_state") not in ["complete", "domcontentloaded"]:
            return False, "Page did not fully load"
        return True, ""

    async def _verify_no_error_page(self, expected: Dict, actual: Dict, state: Dict) -> Tuple[bool, str]:
        """Check for error pages (404, 500, etc)."""
        if state:
            status = state.get("status_code", 200)
            if status >= 400:
                return False, f"Error page: HTTP {status}"
            title = state.get("title", "").lower()
            if any(err in title for err in ["404", "not found", "error", "503", "500"]):
                return False, f"Error page detected: {title}"
        return True, ""

    async def _verify_data_not_empty(self, expected: Dict, actual: Dict, state: Dict) -> Tuple[bool, str]:
        """Verify extracted data is not empty."""
        data = actual.get("data", actual.get("result", []))
        if not data:
            return False, "Extracted data is empty"
        return True, ""

    async def _verify_data_format(self, expected: Dict, actual: Dict, state: Dict) -> Tuple[bool, str]:
        """Verify data format matches expectations."""
        if expected.get("expected_fields"):
            data = actual.get("data", actual.get("result", {}))
            if isinstance(data, list) and data:
                data = data[0]
            if isinstance(data, dict):
                missing = [f for f in expected["expected_fields"] if f not in data]
                if missing:
                    return False, f"Missing expected fields: {missing}"
        return True, ""

    async def _verify_data_reasonable(self, expected: Dict, actual: Dict, state: Dict) -> Tuple[bool, str]:
        """Verify data looks reasonable (not garbage)."""
        data = actual.get("data", actual.get("result", []))
        if isinstance(data, list):
            # Check for suspiciously uniform data (might be repeated error)
            if len(data) > 3:
                unique = len(set(str(d) for d in data))
                if unique == 1:
                    return False, "All extracted items are identical (likely error)"
        return True, ""

    async def _verify_value_set(self, expected: Dict, actual: Dict, state: Dict) -> Tuple[bool, str]:
        """Verify form value was set."""
        if expected.get("value") and state:
            actual_value = state.get("field_value", "")
            if actual_value != expected["value"]:
                return False, f"Field value mismatch: expected '{expected['value']}', got '{actual_value}'"
        return True, ""

    async def _verify_no_validation_error(self, expected: Dict, actual: Dict, state: Dict) -> Tuple[bool, str]:
        """Check for form validation errors."""
        if state:
            validation_error = state.get("validation_error")
            if validation_error:
                return False, f"Validation error: {validation_error}"
        return True, ""


class UserEscalation:
    """
    Handles escalation to user when agent is truly stuck.

    Shows clear options:
    1. Try again with different approach
    2. Skip this step
    3. Provide manual guidance
    4. Abort task
    """

    def __init__(self):
        self.escalation_count = 0
        self.max_auto_escalations = 3

    def should_escalate(self, attempts: int, strategies_tried: int) -> bool:
        """Determine if we should escalate to user."""
        return (
            attempts >= 5 or
            strategies_tried >= 4 or
            self.escalation_count < self.max_auto_escalations
        )

    def format_escalation(
        self,
        action: str,
        error: str,
        strategies_tried: List[str],
        context: Dict
    ) -> str:
        """Format escalation message for user."""
        self.escalation_count += 1

        return f"""
[yellow]I'm stuck and need your help:[/yellow]

[bold]Action:[/bold] {action}
[bold]Error:[/bold] {error[:200]}

[bold]What I've tried:[/bold]
{chr(10).join(f'  - {s}' for s in strategies_tried)}

[bold]Options:[/bold]
  [cyan]1[/cyan] - Try again (I'll use a different approach)
  [cyan]2[/cyan] - Skip this step and continue
  [cyan]3[/cyan] - Give me guidance (type instructions)
  [cyan]4[/cyan] - Abort this task

[dim]Type 1-4 or your guidance:[/dim]
"""

    def parse_response(self, response: str) -> Tuple[str, Optional[str]]:
        """Parse user's escalation response."""
        response = response.strip()

        if response == "1":
            return "retry", None
        elif response == "2":
            return "skip", None
        elif response == "3":
            return "guidance", None
        elif response == "4":
            return "abort", None
        else:
            # Assume it's guidance
            return "guidance", response


# Singleton instances
_retry_manager: Optional[SmartRetryManager] = None
_verifier: Optional[SuccessVerifier] = None
_escalation: Optional[UserEscalation] = None


def get_retry_manager() -> SmartRetryManager:
    global _retry_manager
    if _retry_manager is None:
        _retry_manager = SmartRetryManager()
    return _retry_manager


def get_verifier() -> SuccessVerifier:
    global _verifier
    if _verifier is None:
        _verifier = SuccessVerifier()
    return _verifier


def get_escalation() -> UserEscalation:
    global _escalation
    if _escalation is None:
        _escalation = UserEscalation()
    return _escalation


# Decorator and context manager for convenient retry usage


@dataclass
class RetryContext:
    """Context for a retry operation."""
    action: str
    context: Dict[str, Any]
    max_attempts: int
    strategy: RetryStrategy
    retry_manager: SmartRetryManager
    attempt: int = 0
    last_error: Optional[Exception] = None
    allow_modify: bool = True  # Allow modifying request on retry

    def modify_on_retry(self, **kwargs):
        """Modify context for next retry (e.g., different selector)."""
        if self.allow_modify:
            self.context.update(kwargs)
            logger.info(f"Modified retry context: {kwargs}")


@asynccontextmanager
async def retry_context(
    action: str = "operation",
    context: Optional[Dict] = None,
    max_attempts: int = 3,
    strategy: Union[str, RetryStrategy] = "exponential_jitter",
    backoff: bool = True,
    retry_manager: Optional[SmartRetryManager] = None
):
    """
    Context manager for retry operations with automatic backoff.

    Usage:
        async with retry_context(
            action="fetch_data",
            context={"url": "https://example.com"},
            max_attempts=5,
            strategy="exponential_jitter"
        ) as ctx:
            result = await fetch_data()
            # On error, automatically retries with backoff

    Args:
        action: Name of the action being performed
        context: Context dict (must include 'url' for domain-based circuit breaking)
        max_attempts: Maximum retry attempts
        strategy: Retry strategy name or enum
        backoff: Enable exponential backoff
        retry_manager: Optional custom retry manager
    """
    if retry_manager is None:
        retry_manager = get_retry_manager()

    if context is None:
        context = {}

    if isinstance(strategy, str):
        strategy = RetryStrategy[strategy.upper()]

    retry_ctx = RetryContext(
        action=action,
        context=context,
        max_attempts=max_attempts,
        strategy=strategy,
        retry_manager=retry_manager
    )

    last_error = None
    result = None

    for attempt in range(max_attempts):
        retry_ctx.attempt = attempt
        start_time = time.time()

        try:
            yield retry_ctx
            # Success - record it
            duration_ms = int((time.time() - start_time) * 1000)
            retry_manager.record_attempt(
                action=action,
                strategy=strategy.value,
                args=context,
                success=True,
                duration_ms=duration_ms
            )
            return

        except Exception as e:
            last_error = e
            retry_ctx.last_error = e
            duration_ms = int((time.time() - start_time) * 1000)

            # Record failure
            retry_manager.record_attempt(
                action=action,
                strategy=strategy.value,
                args=context,
                success=False,
                error=str(e),
                duration_ms=duration_ms
            )

            # Check if should retry
            should_retry, reason, delay_ms = retry_manager.should_retry(
                error=e,
                attempt=attempt,
                context=context
            )

            if not should_retry or attempt >= max_attempts - 1:
                logger.error(f"Retry failed permanently: {reason}")
                raise

            logger.warning(f"Attempt {attempt + 1}/{max_attempts} failed: {e} - {reason}")

            # Apply backoff
            if backoff and delay_ms > 0:
                logger.info(f"Backing off for {delay_ms}ms before retry")
                await asyncio.sleep(delay_ms / 1000)

    # Should not reach here, but just in case
    if last_error:
        raise last_error


def with_retry(
    max_attempts: int = 3,
    strategy: Union[str, RetryStrategy] = "exponential_jitter",
    backoff: bool = True,
    action_name: Optional[str] = None,
    context_builder: Optional[Callable] = None
):
    """
    Decorator for automatic retry with backoff.

    Usage:
        @with_retry(max_attempts=5, strategy="exponential")
        async def fetch_data(url: str):
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                return response.json()

        # With custom context builder
        @with_retry(
            max_attempts=3,
            context_builder=lambda *args, **kwargs: {"url": args[0] if args else "unknown"}
        )
        async def scrape_page(url: str):
            ...

    Args:
        max_attempts: Maximum retry attempts
        strategy: Retry strategy (exponential, linear, etc.)
        backoff: Enable exponential backoff
        action_name: Custom action name (defaults to function name)
        context_builder: Function to extract context from args/kwargs
    """
    if isinstance(strategy, str):
        strategy = RetryStrategy[strategy.upper()]

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            action = action_name or func.__name__

            # Build context
            if context_builder:
                context = context_builder(*args, **kwargs)
            else:
                # Default: try to extract URL from args/kwargs
                context = {}
                if args:
                    context["arg0"] = str(args[0])
                if "url" in kwargs:
                    context["url"] = kwargs["url"]

            retry_manager = get_retry_manager()
            last_error = None

            for attempt in range(max_attempts):
                start_time = time.time()

                try:
                    result = await func(*args, **kwargs)

                    # Success
                    duration_ms = int((time.time() - start_time) * 1000)
                    retry_manager.record_attempt(
                        action=action,
                        strategy=strategy.value,
                        args=context,
                        success=True,
                        result=result,
                        duration_ms=duration_ms
                    )
                    return result

                except Exception as e:
                    last_error = e
                    duration_ms = int((time.time() - start_time) * 1000)

                    # Record failure
                    retry_manager.record_attempt(
                        action=action,
                        strategy=strategy.value,
                        args=context,
                        success=False,
                        error=str(e),
                        duration_ms=duration_ms
                    )

                    # Check if should retry
                    should_retry, reason, delay_ms = retry_manager.should_retry(
                        error=e,
                        attempt=attempt,
                        context=context
                    )

                    if not should_retry or attempt >= max_attempts - 1:
                        logger.error(f"Retry failed permanently: {reason}")
                        raise

                    logger.warning(f"Attempt {attempt + 1}/{max_attempts} failed: {e} - {reason}")

                    # Apply backoff
                    if backoff and delay_ms > 0:
                        logger.info(f"Backing off for {delay_ms}ms before retry")
                        await asyncio.sleep(delay_ms / 1000)

            # Should not reach here
            if last_error:
                raise last_error

        return wrapper
    return decorator


# Export helper for getting retry statistics
def get_retry_stats() -> Dict[str, Any]:
    """Get comprehensive retry statistics."""
    manager = get_retry_manager()
    stats = manager.get_stats()

    # Add error type distribution
    error_types = defaultdict(int)
    for attempt in manager.current_attempts:
        if not attempt.success and attempt.error:
            error_type = ErrorClassifier.classify(attempt.error)
            error_types[error_type.value] += 1

    stats["error_type_distribution"] = dict(error_types)

    # Add circuit breaker status
    if manager._circuit_breaker:
        try:
            from .circuit_breaker import CircuitState
            circuits = {}
            for domain in manager.domain_errors.keys():
                state = manager._circuit_breaker.get_state(f"{domain}:unknown")
                circuits[domain] = state.value
            stats["circuit_breaker_states"] = circuits
        except:
            pass

    return stats
