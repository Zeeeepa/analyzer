"""
Online Reflection Loop
Reflects during execution, not just at the end.

Key insight: Waiting until task fails to reflect wastes iterations.
Reflecting every N steps catches problems early.

From research:
- "Without proper guardrails, reflection can lead to unproductive loops"
- Solution: Well-designed exit conditions + maximum iteration limits
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class ReflectionTrigger(Enum):
    """When to trigger reflection."""
    ITERATION_COUNT = "iteration_count"  # Every N iterations
    FAILURE = "failure"  # After any failure
    STALL = "stall"  # No progress detected
    CONFIDENCE_DROP = "confidence_drop"  # Confidence decreased
    GOAL_CHECK = "goal_check"  # Periodic goal verification

@dataclass
class ReflectionResult:
    """Result of a reflection."""
    trigger: ReflectionTrigger
    observation: str
    assessment: str  # on_track, off_track, stuck, completed
    adjustments: List[str]
    confidence_delta: float  # How much confidence changed
    should_continue: bool
    should_reset: bool = False
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class ExecutionState:
    """Current execution state for reflection."""
    iteration: int
    goal: str
    actions_taken: List[Dict]
    results: List[Dict]
    failures: List[Dict]
    current_page_url: Optional[str] = None
    current_page_title: Optional[str] = None
    last_success_iteration: int = 0

class OnlineReflectionLoop:
    """
    Performs reflection during execution, not just at end.

    Key patterns:
    1. Reflect every N iterations (default: 5)
    2. Reflect immediately after failures
    3. Reflect when confidence drops significantly
    4. Reflect when goal seems off-track

    Usage:
        reflector = OnlineReflectionLoop(reflect_every=5)

        for i in range(max_iterations):
            # Execute action
            result = execute_action(action)

            # Check if reflection needed
            if reflector.should_reflect(state):
                reflection = reflector.reflect(state)

                if not reflection.should_continue:
                    break
                if reflection.should_reset:
                    reset_context()
    """

    def __init__(self,
                 reflect_every: int = 5,
                 max_failures_before_reflect: int = 2,
                 confidence_drop_threshold: float = 0.2,
                 stall_iterations: int = 3,
                 reflect_fn: Optional[Callable] = None):
        """
        Args:
            reflect_every: Reflect every N iterations
            max_failures_before_reflect: Reflect after this many consecutive failures
            confidence_drop_threshold: Reflect if confidence drops by this much
            stall_iterations: Reflect if no progress for this many iterations
            reflect_fn: Optional custom reflection function (uses LLM)
        """
        self.reflect_every = reflect_every
        self.max_failures_before_reflect = max_failures_before_reflect
        self.confidence_drop_threshold = confidence_drop_threshold
        self.stall_iterations = stall_iterations
        self.reflect_fn = reflect_fn

        self.last_reflection_iteration = 0
        self.consecutive_failures = 0
        self.last_confidence = 0.5
        self.reflections: List[ReflectionResult] = []
        self.last_meaningful_progress = 0

    def should_reflect(self, state: ExecutionState,
                      current_confidence: float = 0.5) -> Optional[ReflectionTrigger]:
        """
        Check if reflection should happen now.

        Returns the trigger if reflection needed, None otherwise.
        """
        # Check iteration count
        if state.iteration - self.last_reflection_iteration >= self.reflect_every:
            return ReflectionTrigger.ITERATION_COUNT

        # Check failures
        if self.consecutive_failures >= self.max_failures_before_reflect:
            return ReflectionTrigger.FAILURE

        # Check confidence drop
        if self.last_confidence - current_confidence >= self.confidence_drop_threshold:
            return ReflectionTrigger.CONFIDENCE_DROP

        # Check stall
        if state.iteration - self.last_meaningful_progress >= self.stall_iterations:
            return ReflectionTrigger.STALL

        return None

    def reflect(self, state: ExecutionState,
               trigger: Optional[ReflectionTrigger] = None) -> ReflectionResult:
        """
        Perform reflection on current state.

        Returns assessment and recommended adjustments.
        """
        trigger = trigger or ReflectionTrigger.ITERATION_COUNT
        self.last_reflection_iteration = state.iteration

        # Use custom reflection function if provided
        if self.reflect_fn:
            result = self.reflect_fn(state, trigger)
            self.reflections.append(result)
            return result

        # Default rule-based reflection
        result = self._default_reflect(state, trigger)
        self.reflections.append(result)

        # Reset counters
        self.consecutive_failures = 0

        logger.info(f"[REFLECT] {trigger.value}: {result.assessment} - {result.observation}")

        return result

    def _default_reflect(self, state: ExecutionState,
                        trigger: ReflectionTrigger) -> ReflectionResult:
        """Default rule-based reflection."""
        observation_parts = []
        adjustments = []
        assessment = "on_track"
        should_continue = True
        should_reset = False
        confidence_delta = 0.0

        # Analyze recent results
        recent_results = state.results[-5:] if state.results else []
        recent_failures = state.failures[-5:] if state.failures else []

        success_count = len([r for r in recent_results if r.get("success", False)])
        failure_count = len(recent_failures)

        # Check progress
        if success_count == 0 and failure_count > 2:
            observation_parts.append(f"No successes in last {len(recent_results)} actions")
            assessment = "stuck"
            confidence_delta = -0.2
            adjustments.append("Try a different approach")
            adjustments.append("Check if the page has changed")

        elif failure_count > success_count:
            observation_parts.append(f"More failures ({failure_count}) than successes ({success_count})")
            assessment = "struggling"
            confidence_delta = -0.1
            adjustments.append("Review error messages")
            adjustments.append("Simplify the approach")

        else:
            observation_parts.append(f"Making progress: {success_count} successes")
            assessment = "on_track"
            confidence_delta = 0.05

        # Check for loops (same actions repeated)
        if len(state.actions_taken) >= 3:
            last_3 = [str(a.get("name")) for a in state.actions_taken[-3:]]
            if len(set(last_3)) == 1:  # All same action
                observation_parts.append("Detected action loop - same action repeated 3 times")
                assessment = "stuck"
                adjustments.append("Break the loop - try something different")
                should_reset = state.iteration > 10

        # Check goal alignment
        if state.current_page_url:
            observation_parts.append(f"Currently on: {state.current_page_url}")

        # Trigger-specific observations
        if trigger == ReflectionTrigger.FAILURE:
            observation_parts.append("Triggered by repeated failures")
            adjustments.append("Analyze failure patterns")

        elif trigger == ReflectionTrigger.STALL:
            observation_parts.append("Triggered by lack of progress")
            adjustments.append("Re-evaluate the approach")
            adjustments.append("Check if goal is achievable")

        elif trigger == ReflectionTrigger.CONFIDENCE_DROP:
            observation_parts.append("Triggered by confidence drop")
            adjustments.append("Verify assumptions")
            adjustments.append("Consider asking for clarification")

        # Decide if should continue
        if assessment == "stuck" and state.iteration > 15:
            should_continue = False
            adjustments.append("Consider resetting or asking for help")

        return ReflectionResult(
            trigger=trigger,
            observation="; ".join(observation_parts),
            assessment=assessment,
            adjustments=adjustments,
            confidence_delta=confidence_delta,
            should_continue=should_continue,
            should_reset=should_reset
        )

    def record_action_result(self, success: bool, had_meaningful_progress: bool = False):
        """Record the result of an action for reflection tracking."""
        if success:
            self.consecutive_failures = 0
            if had_meaningful_progress:
                self.last_meaningful_progress = 0  # Will be set by caller
        else:
            self.consecutive_failures += 1

    def update_confidence(self, new_confidence: float):
        """Update tracked confidence."""
        self.last_confidence = new_confidence

    def get_reflection_summary(self) -> Dict:
        """Get summary of reflections."""
        if not self.reflections:
            return {"count": 0}

        assessments = {}
        for r in self.reflections:
            assessments[r.assessment] = assessments.get(r.assessment, 0) + 1

        return {
            "count": len(self.reflections),
            "assessments": assessments,
            "average_confidence_delta": sum(r.confidence_delta for r in self.reflections) / len(self.reflections),
            "resets_recommended": sum(1 for r in self.reflections if r.should_reset),
            "stops_recommended": sum(1 for r in self.reflections if not r.should_continue)
        }

    def reset(self):
        """Reset for new task."""
        self.last_reflection_iteration = 0
        self.consecutive_failures = 0
        self.last_confidence = 0.5
        self.reflections.clear()
        self.last_meaningful_progress = 0


# Global instance
_reflector: Optional[OnlineReflectionLoop] = None

def get_online_reflector() -> OnlineReflectionLoop:
    """Get global online reflection loop."""
    global _reflector
    if _reflector is None:
        _reflector = OnlineReflectionLoop()
    return _reflector
