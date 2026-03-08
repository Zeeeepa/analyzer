"""Circuit breaker pattern for error recovery."""
import time
import threading
from enum import Enum
from typing import Dict, Optional, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class CircuitStats:
    """Statistics for a circuit."""
    failures: int = 0
    successes: int = 0
    last_failure_time: float = 0
    last_success_time: float = 0


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures and infinite retry loops.

    State transitions:
    - CLOSED -> OPEN: After N consecutive failures (failure_threshold)
    - OPEN -> HALF_OPEN: After timeout period (reset_timeout)
    - HALF_OPEN -> CLOSED: After N consecutive successes (success_threshold)
    - HALF_OPEN -> OPEN: On any failure during testing

    Usage:
        breaker = CircuitBreaker(failure_threshold=5, reset_timeout=60.0)

        circuit_id = "linkedin.com:click"

        if not breaker.can_execute(circuit_id):
            # Circuit is open, don't retry
            raise CircuitOpenError(circuit_id)

        try:
            result = await perform_action()
            breaker.record_success(circuit_id)
        except Exception as e:
            breaker.record_failure(circuit_id)
            raise
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        reset_timeout: float = 60.0,
        half_open_max_calls: int = 3
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            success_threshold: Number of successes to close circuit from half-open
            reset_timeout: Seconds to wait before trying half-open (default: 60s)
            half_open_max_calls: Max concurrent calls in half-open state
        """
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.reset_timeout = reset_timeout
        self.half_open_max_calls = half_open_max_calls

        self._circuits: Dict[str, CircuitState] = {}
        self._stats: Dict[str, CircuitStats] = {}
        self._half_open_calls: Dict[str, int] = {}
        self._lock = threading.Lock()

    def get_state(self, circuit_id: str) -> CircuitState:
        """
        Get current state of circuit, transitioning to HALF_OPEN if timeout expired.

        Args:
            circuit_id: Unique identifier for circuit (e.g., "domain:action")

        Returns:
            Current circuit state
        """
        with self._lock:
            state = self._circuits.get(circuit_id, CircuitState.CLOSED)

            # Check if OPEN circuit should transition to HALF_OPEN
            if state == CircuitState.OPEN:
                stats = self._stats.get(circuit_id, CircuitStats())
                if time.time() - stats.last_failure_time >= self.reset_timeout:
                    self._circuits[circuit_id] = CircuitState.HALF_OPEN
                    self._half_open_calls[circuit_id] = 0
                    logger.info(f"Circuit {circuit_id}: OPEN -> HALF_OPEN (timeout expired)")
                    return CircuitState.HALF_OPEN

            return state

    def can_execute(self, circuit_id: str) -> bool:
        """
        Check if operation can execute (circuit not open).

        Args:
            circuit_id: Unique identifier for circuit

        Returns:
            True if operation can proceed, False if circuit is open
        """
        state = self.get_state(circuit_id)

        if state == CircuitState.CLOSED:
            return True
        elif state == CircuitState.OPEN:
            return False
        else:  # HALF_OPEN
            with self._lock:
                calls = self._half_open_calls.get(circuit_id, 0)
                if calls < self.half_open_max_calls:
                    self._half_open_calls[circuit_id] = calls + 1
                    return True
                return False

    def record_success(self, circuit_id: str):
        """
        Record successful operation.

        Updates stats and transitions HALF_OPEN -> CLOSED if enough successes.

        Args:
            circuit_id: Unique identifier for circuit
        """
        with self._lock:
            if circuit_id not in self._stats:
                self._stats[circuit_id] = CircuitStats()

            stats = self._stats[circuit_id]
            stats.successes += 1
            stats.last_success_time = time.time()
            stats.failures = 0  # Reset consecutive failures on success

            state = self._circuits.get(circuit_id, CircuitState.CLOSED)

            if state == CircuitState.HALF_OPEN:
                if stats.successes >= self.success_threshold:
                    self._circuits[circuit_id] = CircuitState.CLOSED
                    logger.info(
                        f"Circuit {circuit_id}: HALF_OPEN -> CLOSED "
                        f"({stats.successes} consecutive successes)"
                    )

    def record_failure(self, circuit_id: str):
        """
        Record failed operation.

        Updates stats and transitions to OPEN if threshold exceeded.

        Args:
            circuit_id: Unique identifier for circuit
        """
        with self._lock:
            if circuit_id not in self._stats:
                self._stats[circuit_id] = CircuitStats()

            stats = self._stats[circuit_id]
            stats.failures += 1
            stats.last_failure_time = time.time()
            stats.successes = 0  # Reset consecutive successes on failure

            state = self._circuits.get(circuit_id, CircuitState.CLOSED)

            if state == CircuitState.CLOSED:
                if stats.failures >= self.failure_threshold:
                    self._circuits[circuit_id] = CircuitState.OPEN
                    logger.warning(
                        f"Circuit {circuit_id}: CLOSED -> OPEN "
                        f"({stats.failures} consecutive failures)"
                    )

            elif state == CircuitState.HALF_OPEN:
                # Any failure in half-open state reopens circuit
                self._circuits[circuit_id] = CircuitState.OPEN
                logger.warning(f"Circuit {circuit_id}: HALF_OPEN -> OPEN (test failed)")

    def reset(self, circuit_id: str):
        """
        Manually reset circuit to CLOSED state.

        Args:
            circuit_id: Unique identifier for circuit
        """
        with self._lock:
            self._circuits[circuit_id] = CircuitState.CLOSED
            self._stats[circuit_id] = CircuitStats()
            self._half_open_calls.pop(circuit_id, None)
            logger.info(f"Circuit {circuit_id}: Manually reset to CLOSED")

    def get_all_stats(self) -> Dict[str, dict]:
        """
        Get statistics for all circuits.

        Returns:
            Dictionary mapping circuit_id to stats dict
        """
        with self._lock:
            return {
                cid: {
                    "state": self._circuits.get(cid, CircuitState.CLOSED).value,
                    "failures": stats.failures,
                    "successes": stats.successes,
                    "last_failure": stats.last_failure_time,
                    "last_success": stats.last_success_time
                }
                for cid, stats in self._stats.items()
            }

    def get_circuit_info(self, circuit_id: str) -> Dict[str, Any]:
        """
        Get detailed info for a specific circuit.

        Args:
            circuit_id: Unique identifier for circuit

        Returns:
            Dictionary with circuit state and stats
        """
        state = self.get_state(circuit_id)
        stats = self._stats.get(circuit_id, CircuitStats())

        info = {
            "circuit_id": circuit_id,
            "state": state.value,
            "failures": stats.failures,
            "successes": stats.successes,
            "last_failure_time": stats.last_failure_time,
            "last_success_time": stats.last_success_time
        }

        if state == CircuitState.OPEN:
            time_until_retry = max(
                0,
                self.reset_timeout - (time.time() - stats.last_failure_time)
            )
            info["retry_in_seconds"] = time_until_retry

        return info


# Global instance
_global_circuit_breaker: Optional[CircuitBreaker] = None


def get_circuit_breaker() -> CircuitBreaker:
    """Get or create global circuit breaker instance."""
    global _global_circuit_breaker
    if _global_circuit_breaker is None:
        _global_circuit_breaker = CircuitBreaker()
    return _global_circuit_breaker


class CircuitOpenError(Exception):
    """Raised when attempting to execute on an open circuit."""

    def __init__(self, circuit_id: str, retry_after: float = 0):
        self.circuit_id = circuit_id
        self.retry_after = retry_after
        msg = f"Circuit '{circuit_id}' is open"
        if retry_after > 0:
            msg += f", retry after {retry_after:.0f}s"
        super().__init__(msg)
