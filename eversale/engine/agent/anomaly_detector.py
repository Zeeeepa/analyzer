"""
Behavioral Anomaly Detection

Detect when agent behavior drifts from baseline patterns.
Catch failures early before MaxSteps or circuit breaker triggers.

Features:
- Baseline behavior profiling
- Real-time drift detection
- Cascading failure pattern detection
- Auto-escalation triggers
- Integration with circuit breaker
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, deque
from enum import Enum
import statistics
from loguru import logger


class AnomalyType(Enum):
    """Types of anomalies that can be detected"""
    SLOW_ACTION = "slow_action"  # Action taking too long
    FAST_ACTION = "fast_action"  # Action suspiciously fast (failed early?)
    REPEATED_ERROR = "repeated_error"  # Same error multiple times
    STUCK_PATTERN = "stuck_pattern"  # Same URL/state repeatedly
    TOKEN_SPIKE = "token_spike"  # Sudden increase in token usage
    NAVIGATION_DRIFT = "navigation_drift"  # Going to unrelated URLs
    CASCADING_FAILURE = "cascading_failure"  # Error -> retry -> error pattern
    UNUSUAL_SEQUENCE = "unusual_sequence"  # Action sequence not seen before


class AlertSeverity(Enum):
    """Severity levels for anomaly alerts"""
    INFO = "info"  # Informational, no action needed
    WARNING = "warning"  # Worth watching
    CRITICAL = "critical"  # Needs immediate attention
    FATAL = "fatal"  # Should stop execution


@dataclass
class AnomalyAlert:
    """An anomaly detection alert"""
    anomaly_type: AnomalyType
    severity: AlertSeverity
    message: str
    details: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    action_recommended: str = ""


@dataclass
class ActionMetrics:
    """Metrics for a single action"""
    action_type: str
    duration_ms: float
    success: bool
    url: str = ""
    error: str = ""
    tokens_used: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class BaselineProfile:
    """Baseline behavior profile for an action type"""
    action_type: str
    samples: List[float] = field(default_factory=list)
    mean_duration: float = 0
    std_duration: float = 0
    min_duration: float = 0
    max_duration: float = 0
    success_rate: float = 1.0

    def update(self, duration: float, success: bool):
        """Update baseline with new sample"""
        self.samples.append(duration)

        # Keep last 100 samples
        if len(self.samples) > 100:
            self.samples = self.samples[-100:]

        if len(self.samples) >= 3:
            self.mean_duration = statistics.mean(self.samples)
            self.std_duration = statistics.stdev(self.samples) if len(self.samples) > 1 else 0
            self.min_duration = min(self.samples)
            self.max_duration = max(self.samples)

        # Update success rate (exponential moving average)
        alpha = 0.1
        self.success_rate = alpha * (1.0 if success else 0.0) + (1 - alpha) * self.success_rate

    def is_anomaly(self, duration: float) -> Tuple[bool, str]:
        """Check if duration is anomalous"""
        if len(self.samples) < 5:
            return False, ""  # Not enough data

        # Z-score based detection
        if self.std_duration > 0:
            z_score = abs(duration - self.mean_duration) / self.std_duration
            if z_score > 3:  # 3 standard deviations
                if duration > self.mean_duration:
                    return True, f"Duration {duration:.0f}ms is {z_score:.1f} std devs above mean ({self.mean_duration:.0f}ms)"
                else:
                    return True, f"Duration {duration:.0f}ms is {z_score:.1f} std devs below mean ({self.mean_duration:.0f}ms)"

        # Absolute threshold (10x mean is always suspicious)
        if duration > self.mean_duration * 10:
            return True, f"Duration {duration:.0f}ms is 10x the mean ({self.mean_duration:.0f}ms)"

        return False, ""


class AnomalyDetector:
    """
    Detect behavioral anomalies in agent execution.

    Usage:
        detector = AnomalyDetector()

        # Record actions
        detector.record_action("click", duration_ms=150, success=True, url="https://...")

        # Check for anomalies
        alerts = detector.check_all_anomalies()
        for alert in alerts:
            if alert.severity == AlertSeverity.CRITICAL:
                # Take action
                ...
    """

    def __init__(
        self,
        window_size: int = 20,
        cascade_threshold: int = 3,
        stuck_threshold: int = 5
    ):
        # Baseline profiles by action type
        self.baselines: Dict[str, BaselineProfile] = {}

        # Recent action history (sliding window)
        self.history: deque = deque(maxlen=window_size)

        # URL visit tracking
        self.url_visits: Dict[str, int] = defaultdict(int)

        # Error tracking
        self.recent_errors: deque = deque(maxlen=10)

        # Thresholds
        self.cascade_threshold = cascade_threshold  # Errors in a row before cascade alert
        self.stuck_threshold = stuck_threshold  # Same URL visits before stuck alert

        # Alert history
        self.alerts: List[AnomalyAlert] = []

        # Callbacks
        self.alert_callbacks: List[Callable[[AnomalyAlert], None]] = []

        # Stats
        self.stats = {
            'actions_recorded': 0,
            'anomalies_detected': 0,
            'critical_alerts': 0,
            'cascading_failures': 0,
        }

    def record_action(
        self,
        action_type: str,
        duration_ms: float,
        success: bool,
        url: str = "",
        error: str = "",
        tokens_used: int = 0
    ) -> List[AnomalyAlert]:
        """Record an action and check for anomalies"""
        metrics = ActionMetrics(
            action_type=action_type,
            duration_ms=duration_ms,
            success=success,
            url=url,
            error=error,
            tokens_used=tokens_used
        )

        self.history.append(metrics)
        self.stats['actions_recorded'] += 1

        # Update baseline
        if action_type not in self.baselines:
            self.baselines[action_type] = BaselineProfile(action_type)
        self.baselines[action_type].update(duration_ms, success)

        # Track URL visits
        if url:
            self.url_visits[url] += 1

        # Track errors
        if not success and error:
            self.recent_errors.append((datetime.now(), error))

        # Check for anomalies
        return self.check_all_anomalies(metrics)

    def check_all_anomalies(self, latest: ActionMetrics = None) -> List[AnomalyAlert]:
        """Run all anomaly checks and return alerts"""
        alerts = []

        if latest:
            # Duration anomaly
            alert = self._check_duration_anomaly(latest)
            if alert:
                alerts.append(alert)

            # Token spike
            alert = self._check_token_spike(latest)
            if alert:
                alerts.append(alert)

        # Pattern-based anomalies
        alert = self._check_cascading_failure()
        if alert:
            alerts.append(alert)

        alert = self._check_stuck_pattern()
        if alert:
            alerts.append(alert)

        alert = self._check_repeated_errors()
        if alert:
            alerts.append(alert)

        # Record and notify
        for alert in alerts:
            self.alerts.append(alert)
            self.stats['anomalies_detected'] += 1

            if alert.severity == AlertSeverity.CRITICAL:
                self.stats['critical_alerts'] += 1

            # Notify callbacks
            for callback in self.alert_callbacks:
                try:
                    callback(alert)
                except Exception as e:
                    logger.error(f"[ANOMALY] Alert callback failed: {e}")

            # Log
            log_method = {
                AlertSeverity.INFO: logger.debug,
                AlertSeverity.WARNING: logger.warning,
                AlertSeverity.CRITICAL: logger.error,
                AlertSeverity.FATAL: logger.critical,
            }.get(alert.severity, logger.info)

            log_method(f"[ANOMALY] {alert.anomaly_type.value}: {alert.message}")

        return alerts

    def _check_duration_anomaly(self, metrics: ActionMetrics) -> Optional[AnomalyAlert]:
        """Check if action duration is anomalous"""
        baseline = self.baselines.get(metrics.action_type)
        if not baseline:
            return None

        is_anomaly, reason = baseline.is_anomaly(metrics.duration_ms)

        if is_anomaly:
            severity = AlertSeverity.WARNING
            anomaly_type = AnomalyType.SLOW_ACTION if metrics.duration_ms > baseline.mean_duration else AnomalyType.FAST_ACTION

            # Critical if very slow
            if metrics.duration_ms > baseline.mean_duration * 20:
                severity = AlertSeverity.CRITICAL

            return AnomalyAlert(
                anomaly_type=anomaly_type,
                severity=severity,
                message=reason,
                details={
                    'action': metrics.action_type,
                    'duration_ms': metrics.duration_ms,
                    'baseline_mean': baseline.mean_duration,
                    'baseline_std': baseline.std_duration,
                },
                action_recommended="Consider timeout adjustment or retry"
            )

        return None

    def _check_token_spike(self, metrics: ActionMetrics) -> Optional[AnomalyAlert]:
        """Check for sudden spike in token usage"""
        if metrics.tokens_used == 0:
            return None

        # Get recent token usage
        recent_tokens = [
            m.tokens_used for m in self.history
            if m.tokens_used > 0 and m != metrics
        ]

        if len(recent_tokens) < 3:
            return None

        avg_tokens = statistics.mean(recent_tokens)

        # Alert if 5x more than average
        if metrics.tokens_used > avg_tokens * 5:
            return AnomalyAlert(
                anomaly_type=AnomalyType.TOKEN_SPIKE,
                severity=AlertSeverity.WARNING,
                message=f"Token usage spike: {metrics.tokens_used} tokens (avg: {avg_tokens:.0f})",
                details={
                    'tokens_used': metrics.tokens_used,
                    'average': avg_tokens,
                    'ratio': metrics.tokens_used / avg_tokens,
                },
                action_recommended="Check for context bloat or prompt issues"
            )

        return None

    def _check_cascading_failure(self) -> Optional[AnomalyAlert]:
        """Check for cascading failure pattern (error -> retry -> error)"""
        if len(self.history) < self.cascade_threshold:
            return None

        # Check last N actions
        recent = list(self.history)[-self.cascade_threshold:]
        failures = sum(1 for m in recent if not m.success)

        if failures >= self.cascade_threshold:
            self.stats['cascading_failures'] += 1

            # Get unique errors
            error_msgs = list(set(m.error for m in recent if m.error))

            return AnomalyAlert(
                anomaly_type=AnomalyType.CASCADING_FAILURE,
                severity=AlertSeverity.CRITICAL,
                message=f"{failures} consecutive failures detected",
                details={
                    'failure_count': failures,
                    'errors': error_msgs[:3],
                    'actions': [m.action_type for m in recent],
                },
                action_recommended="Consider circuit breaker trigger or human escalation"
            )

        return None

    def _check_stuck_pattern(self) -> Optional[AnomalyAlert]:
        """Check if agent is stuck on same URL/state"""
        for url, count in self.url_visits.items():
            if count >= self.stuck_threshold:
                return AnomalyAlert(
                    anomaly_type=AnomalyType.STUCK_PATTERN,
                    severity=AlertSeverity.WARNING if count < self.stuck_threshold * 2 else AlertSeverity.CRITICAL,
                    message=f"Visited same URL {count} times: {url[:50]}...",
                    details={
                        'url': url,
                        'visit_count': count,
                        'threshold': self.stuck_threshold,
                    },
                    action_recommended="Agent may be stuck - consider navigation reset"
                )

        return None

    def _check_repeated_errors(self) -> Optional[AnomalyAlert]:
        """Check for repeated identical errors"""
        if len(self.recent_errors) < 3:
            return None

        # Group by error message
        error_counts = defaultdict(int)
        for _, error in self.recent_errors:
            error_counts[error] += 1

        # Check for dominant error
        for error, count in error_counts.items():
            if count >= 3:
                return AnomalyAlert(
                    anomaly_type=AnomalyType.REPEATED_ERROR,
                    severity=AlertSeverity.WARNING,
                    message=f"Same error {count} times: {error[:50]}...",
                    details={
                        'error': error,
                        'count': count,
                    },
                    action_recommended="Investigate root cause - may need different approach"
                )

        return None

    def on_alert(self, callback: Callable[[AnomalyAlert], None]):
        """Register a callback for anomaly alerts"""
        self.alert_callbacks.append(callback)

    def should_escalate(self) -> bool:
        """Check if anomalies warrant human escalation"""
        # Count critical alerts in last minute
        recent_critical = sum(
            1 for a in self.alerts
            if a.severity in (AlertSeverity.CRITICAL, AlertSeverity.FATAL)
            and datetime.now() - a.timestamp < timedelta(minutes=1)
        )

        return recent_critical >= 2

    def should_circuit_break(self) -> bool:
        """Check if anomalies warrant circuit breaker trigger"""
        # Cascading failure pattern
        if self.stats['cascading_failures'] >= 2:
            return True

        # Too many critical alerts
        recent_critical = sum(
            1 for a in self.alerts
            if a.severity == AlertSeverity.CRITICAL
            and datetime.now() - a.timestamp < timedelta(seconds=30)
        )

        return recent_critical >= 3

    def get_health_score(self) -> float:
        """Get overall health score (0-100)"""
        score = 100.0

        # Deduct for anomalies
        for alert in self.alerts[-20:]:  # Last 20 alerts
            if datetime.now() - alert.timestamp > timedelta(minutes=5):
                continue

            if alert.severity == AlertSeverity.INFO:
                score -= 1
            elif alert.severity == AlertSeverity.WARNING:
                score -= 5
            elif alert.severity == AlertSeverity.CRITICAL:
                score -= 15
            elif alert.severity == AlertSeverity.FATAL:
                score -= 30

        # Deduct for low success rate
        recent = list(self.history)[-10:]
        if recent:
            success_rate = sum(1 for m in recent if m.success) / len(recent)
            score -= (1 - success_rate) * 30

        return max(0, min(100, score))

    def reset(self):
        """Reset detector state"""
        self.history.clear()
        self.url_visits.clear()
        self.recent_errors.clear()
        self.alerts.clear()
        # Keep baselines - they're learned

    def get_stats(self) -> Dict:
        """Get detector statistics"""
        return {
            **self.stats,
            'health_score': self.get_health_score(),
            'should_escalate': self.should_escalate(),
            'should_circuit_break': self.should_circuit_break(),
            'baseline_profiles': len(self.baselines),
            'recent_alerts': len([a for a in self.alerts if datetime.now() - a.timestamp < timedelta(minutes=5)]),
        }


# Singleton
_detector: Optional[AnomalyDetector] = None

def get_anomaly_detector() -> AnomalyDetector:
    """Get or create the global anomaly detector"""
    global _detector
    if _detector is None:
        _detector = AnomalyDetector()
    return _detector
