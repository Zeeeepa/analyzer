"""
Confidence Orchestrator
Unifies confidence scoring across all systems and uses it to drive agent behavior.

Key behaviors driven by confidence:
- Low confidence (<0.5): Ask user, use more tools, verify more
- Medium confidence (0.5-0.8): Normal operation
- High confidence (>0.8): Skip verification, use faster paths
"""

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class ConfidenceSignal:
    """A single confidence measurement from any system."""
    source: str  # reflexion, verifier, retry, tool_result
    value: float  # 0.0 to 1.0
    reason: str
    timestamp: datetime = field(default_factory=datetime.now)
    weight: float = 1.0  # How much to trust this source

@dataclass
class ConfidenceState:
    """Current aggregated confidence for the task."""
    overall: float = 0.5
    signals: List[ConfidenceSignal] = field(default_factory=list)
    action_count: int = 0
    failure_count: int = 0
    last_updated: datetime = field(default_factory=datetime.now)

class ConfidenceOrchestrator:
    """
    Central confidence tracking that DRIVES behavior.

    Usage:
        confidence = ConfidenceOrchestrator()
        confidence.add_signal("tool_result", 0.9, "Extraction successful")

        if confidence.should_verify():
            # Do extra verification
        if confidence.should_escalate():
            # Ask user for help
    """

    # Thresholds that drive behavior
    ESCALATE_THRESHOLD = 0.3  # Below this, ask user
    VERIFY_THRESHOLD = 0.6    # Below this, verify results
    FAST_PATH_THRESHOLD = 0.85  # Above this, skip extra checks

    def __init__(self):
        self.state = ConfidenceState()
        self.history: List[ConfidenceState] = []
        self.callbacks: Dict[str, List[Callable]] = {
            'low_confidence': [],
            'high_confidence': [],
            'escalation_needed': []
        }

    def add_signal(self, source: str, value: float, reason: str, weight: float = 1.0):
        """Add a confidence signal from any system."""
        signal = ConfidenceSignal(
            source=source,
            value=max(0.0, min(1.0, value)),  # Clamp to 0-1
            reason=reason,
            weight=weight
        )
        self.state.signals.append(signal)
        self._recalculate_overall()
        self._check_triggers()
        logger.debug(f"[CONFIDENCE] {source}: {value:.2f} - {reason}")

    def record_action(self, success: bool):
        """Record action outcome to adjust confidence."""
        self.state.action_count += 1
        if not success:
            self.state.failure_count += 1

        # Adjust confidence based on success rate
        if self.state.action_count >= 3:
            success_rate = 1 - (self.state.failure_count / self.state.action_count)
            self.add_signal("action_history", success_rate,
                          f"{self.state.action_count - self.state.failure_count}/{self.state.action_count} actions succeeded",
                          weight=0.5)

    def _recalculate_overall(self):
        """Weighted average of recent signals."""
        if not self.state.signals:
            return

        # Use last 10 signals, weighted by recency and source weight
        recent = self.state.signals[-10:]
        total_weight = sum(s.weight for s in recent)
        if total_weight > 0:
            weighted_sum = sum(s.value * s.weight for s in recent)
            self.state.overall = weighted_sum / total_weight
        self.state.last_updated = datetime.now()

    def _check_triggers(self):
        """Check if any behavioral triggers should fire."""
        if self.state.overall < self.ESCALATE_THRESHOLD:
            for callback in self.callbacks['escalation_needed']:
                callback(self.state)
        elif self.state.overall < self.VERIFY_THRESHOLD:
            for callback in self.callbacks['low_confidence']:
                callback(self.state)
        elif self.state.overall > self.FAST_PATH_THRESHOLD:
            for callback in self.callbacks['high_confidence']:
                callback(self.state)

    # Behavioral decisions based on confidence

    def should_escalate(self) -> bool:
        """Should we ask the user for help?"""
        return self.state.overall < self.ESCALATE_THRESHOLD

    def should_verify(self) -> bool:
        """Should we do extra verification?"""
        return self.state.overall < self.VERIFY_THRESHOLD

    def can_fast_path(self) -> bool:
        """Can we skip extra checks?"""
        return self.state.overall > self.FAST_PATH_THRESHOLD

    def get_retry_intensity(self) -> int:
        """How many retries based on confidence?"""
        if self.state.overall > 0.8:
            return 1  # High confidence, minimal retry
        elif self.state.overall > 0.5:
            return 3  # Medium confidence, normal retry
        else:
            return 5  # Low confidence, aggressive retry

    def get_tool_selection_mode(self) -> str:
        """Which tools to prefer based on confidence?"""
        if self.state.overall > 0.8:
            return "fast"  # Use quick tools
        elif self.state.overall > 0.5:
            return "balanced"
        else:
            return "thorough"  # Use verification tools

    def get_explanation(self) -> str:
        """Why is confidence at this level?"""
        if not self.state.signals:
            return "No signals yet"

        recent = self.state.signals[-5:]
        reasons = [f"- {s.source}: {s.value:.0%} ({s.reason})" for s in recent]
        return f"Confidence: {self.state.overall:.0%}\nRecent signals:\n" + "\n".join(reasons)

    def reset(self):
        """Reset for new task."""
        self.history.append(self.state)
        self.state = ConfidenceState()

    def on(self, event: str, callback: Callable):
        """Register callback for confidence events."""
        if event in self.callbacks:
            self.callbacks[event].append(callback)

    def get_state(self) -> Dict[str, Any]:
        """Get current state for logging/debugging."""
        return {
            "overall": self.state.overall,
            "action_count": self.state.action_count,
            "failure_count": self.state.failure_count,
            "signal_count": len(self.state.signals),
            "should_escalate": self.should_escalate(),
            "should_verify": self.should_verify(),
            "can_fast_path": self.can_fast_path()
        }


# Singleton instance for global access
_confidence: Optional[ConfidenceOrchestrator] = None

def get_confidence() -> ConfidenceOrchestrator:
    """Get global confidence orchestrator."""
    global _confidence
    if _confidence is None:
        _confidence = ConfidenceOrchestrator()
    return _confidence
