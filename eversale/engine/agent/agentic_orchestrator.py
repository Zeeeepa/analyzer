"""
Agentic Orchestrator - Unified Coordination Layer

Coordinates all advanced agentic patterns in a single cohesive system:
1. Context Budget (Anchor + Sliding Window)
2. Confidence Orchestration (Adaptive behavior)
3. Online Reflection (Mid-execution thinking)
4. Pre-Execution Validation (Safety checks)

This module provides a single entry point for the ReAct loop to interact
with all cognitive systems, ensuring they work together harmoniously.

Based on research from:
- Claude Code: Context management, pre-execution validation
- Codex: Confidence-driven behavior
- Reflexion: Online reflection and self-correction
- Cognitive Science: Working memory, attention, metacognition

Architecture:
```
                    ┌─────────────────────────┐
                    │   AgenticOrchestrator   │
                    │   (Central Coordinator) │
                    └───────────┬─────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ContextBudget │     │   Confidence    │     │ OnlineReflection│
│  (Memory)    │     │ (Behavior Adj.) │     │  (Metacognition)│
└───────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                │
                                ▼
                    ┌─────────────────────────┐
                    │  PreExecutionValidator  │
                    │   (Safety + Gating)     │
                    └─────────────────────────┘
```
"""

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Callable
from datetime import datetime
from enum import Enum
import logging

# Import all agentic components
from .context_budget_v2 import (
    ContextBudgetManagerV2,
    get_context_budget_v2,
    MessageImportance
)
from .confidence_orchestrator import (
    ConfidenceOrchestrator,
    get_confidence,
    ConfidenceState
)
from .online_reflection import (
    OnlineReflectionLoop,
    get_online_reflector,
    ReflectionTrigger,
    ExecutionState,
    ReflectionResult
)
from .pre_execution_validator import (
    PreExecutionValidator,
    get_validator,
    ValidationResult,
    ValidationOutput
)

logger = logging.getLogger(__name__)


class AgentMode(Enum):
    """Operating modes based on confidence and context."""
    EXPLORATION = "exploration"      # Low confidence, try different approaches
    EXECUTION = "execution"          # Medium confidence, normal operation
    FAST_TRACK = "fast_track"        # High confidence, skip extra checks
    CAUTIOUS = "cautious"            # After failures, extra verification
    RECOVERY = "recovery"            # Multiple failures, need intervention


@dataclass
class OrchestratorState:
    """Current state of the orchestrator."""
    mode: AgentMode = AgentMode.EXECUTION
    iteration: int = 0
    total_actions: int = 0
    successful_actions: int = 0
    failed_actions: int = 0

    # Timing
    session_start: datetime = field(default_factory=datetime.now)
    last_action_time: Optional[datetime] = None
    last_reflection_time: Optional[datetime] = None
    last_context_management_time: Optional[datetime] = None

    # Goal tracking
    current_goal: str = ""
    goal_progress: float = 0.0

    # Flags
    needs_human_help: bool = False
    is_stuck: bool = False
    context_was_reset: bool = False


@dataclass
class IterationContext:
    """Context passed to each iteration of the ReAct loop."""
    iteration: int
    messages: List[Dict]
    goal: str
    mode: AgentMode
    confidence: float
    should_reflect: bool
    reflection_trigger: Optional[ReflectionTrigger]
    context_managed: bool
    context_was_reset: bool


@dataclass
class ActionDecision:
    """Decision about whether/how to execute an action."""
    should_execute: bool
    action: Dict
    modified_action: Optional[Dict] = None
    validation_result: Optional[ValidationOutput] = None
    confidence_adjustment: float = 0.0
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


class AgenticOrchestrator:
    """
    Central coordinator for all agentic systems.

    Provides unified API for:
    - Context management (when to compress/reset)
    - Confidence tracking (how certain are we?)
    - Reflection triggers (should we pause and think?)
    - Action validation (is this safe/correct?)
    - Mode adaptation (how should we behave?)

    Usage:
        orchestrator = AgenticOrchestrator()
        orchestrator.set_goal("Find leads from Facebook Ads")

        for iteration in range(max_iterations):
            # Prepare context for this iteration
            ctx = orchestrator.prepare_iteration(messages, iteration)

            # Manage messages if needed
            if ctx.context_managed:
                messages = ctx.messages

            # Check if reflection needed
            if ctx.should_reflect:
                reflection = orchestrator.reflect(messages, ctx.reflection_trigger)
                # Handle reflection results...

            # Validate action before execution
            decision = orchestrator.validate_action(action)
            if not decision.should_execute:
                continue

            # Execute action
            result = await execute(decision.action or decision.modified_action)

            # Record result
            orchestrator.record_result(action, result, success=result.success)
    """

    # Mode thresholds
    FAST_TRACK_CONFIDENCE = 0.85
    CAUTIOUS_CONFIDENCE = 0.4
    RECOVERY_CONFIDENCE = 0.25

    # Reflection intervals
    REFLECTION_INTERVAL = 5  # Reflect every N iterations
    MAX_FAILURES_BEFORE_REFLECTION = 2

    def __init__(
        self,
        context_budget: Optional[ContextBudgetManagerV2] = None,
        confidence: Optional[ConfidenceOrchestrator] = None,
        reflector: Optional[OnlineReflectionLoop] = None,
        validator: Optional[PreExecutionValidator] = None
    ):
        """
        Initialize orchestrator with component instances.

        If not provided, uses global singletons.
        """
        self.context_budget = context_budget or get_context_budget_v2()
        self.confidence = confidence or get_confidence()
        self.reflector = reflector or get_online_reflector()
        self.validator = validator or get_validator()

        self.state = OrchestratorState()

        # Callbacks for external systems
        self._on_mode_change: Optional[Callable[[AgentMode, AgentMode], None]] = None
        self._on_reflection: Optional[Callable[[ReflectionResult], None]] = None
        self._on_context_reset: Optional[Callable[[], None]] = None
        self._summarize_fn: Optional[Callable[[List[Dict]], str]] = None

    def set_goal(self, goal: str):
        """Set the current task goal."""
        self.state.current_goal = goal
        self.context_budget.set_goal(goal)
        logger.info(f"[ORCHESTRATOR] Goal set: {goal[:100]}...")

    def set_summarizer(self, fn: Callable[[List[Dict]], str]):
        """Set LLM summarization function for context compression."""
        self._summarize_fn = fn
        self.context_budget.set_summarizer(fn)

    def on_mode_change(self, callback: Callable[[AgentMode, AgentMode], None]):
        """Register callback for mode changes."""
        self._on_mode_change = callback

    def on_reflection(self, callback: Callable[[ReflectionResult], None]):
        """Register callback for reflections."""
        self._on_reflection = callback

    def on_context_reset(self, callback: Callable[[], None]):
        """Register callback for context resets."""
        self._on_context_reset = callback

    def prepare_iteration(
        self,
        messages: List[Dict],
        iteration: int
    ) -> IterationContext:
        """
        Prepare context for a new iteration.

        Handles:
        1. Context management (compress/reset if needed)
        2. Mode determination based on confidence
        3. Reflection trigger detection

        Returns IterationContext with all relevant info.
        """
        self.state.iteration = iteration

        # 1. Context Management
        context_managed = False
        context_was_reset = False
        managed_messages = messages

        if self.context_budget.should_reset():
            # Full reset - start fresh with summary
            managed_messages = self.context_budget.perform_reset(
                messages,
                goal=self.state.current_goal
            )
            context_managed = True
            context_was_reset = True
            self.state.context_was_reset = True
            logger.info(f"[ORCHESTRATOR] Context reset at iteration {iteration}")
            if self._on_context_reset:
                self._on_context_reset()

        elif self.context_budget.needs_management():
            # Compress context
            managed_messages = self.context_budget.manage_context(
                messages,
                goal=self.state.current_goal
            )
            context_managed = True
            logger.info(f"[ORCHESTRATOR] Context compressed at iteration {iteration}")

        # 2. Mode Determination
        old_mode = self.state.mode
        new_mode = self._determine_mode()
        if new_mode != old_mode:
            self.state.mode = new_mode
            logger.info(f"[ORCHESTRATOR] Mode changed: {old_mode.value} -> {new_mode.value}")
            if self._on_mode_change:
                self._on_mode_change(old_mode, new_mode)

        # 3. Reflection Trigger Check
        exec_state = ExecutionState(
            iteration=iteration,
            goal=self.state.current_goal,
            actions_taken=[],  # Will be filled by caller
            results=[],
            failures=[],
            last_success_iteration=self._last_success_iteration()
        )

        trigger = self.reflector.should_reflect(
            exec_state,
            current_confidence=self.confidence.state.overall
        )

        return IterationContext(
            iteration=iteration,
            messages=managed_messages,
            goal=self.state.current_goal,
            mode=self.state.mode,
            confidence=self.confidence.state.overall,
            should_reflect=(trigger is not None),
            reflection_trigger=trigger,
            context_managed=context_managed,
            context_was_reset=context_was_reset
        )

    def _determine_mode(self) -> AgentMode:
        """Determine operating mode based on confidence and state."""
        confidence = self.confidence.state.overall

        # Check for recovery conditions
        if self.state.failed_actions >= 5 and self.state.successful_actions == 0:
            return AgentMode.RECOVERY

        if confidence >= self.FAST_TRACK_CONFIDENCE:
            return AgentMode.FAST_TRACK
        elif confidence <= self.RECOVERY_CONFIDENCE:
            return AgentMode.RECOVERY
        elif confidence <= self.CAUTIOUS_CONFIDENCE:
            return AgentMode.CAUTIOUS
        else:
            return AgentMode.EXECUTION

    def _last_success_iteration(self) -> int:
        """Get last successful iteration."""
        # This would be tracked properly in full implementation
        return max(0, self.state.iteration - self.state.failed_actions)

    def reflect(
        self,
        messages: List[Dict],
        trigger: Optional[ReflectionTrigger] = None
    ) -> ReflectionResult:
        """
        Perform reflection on current state.

        Returns ReflectionResult with assessment and recommendations.
        """
        exec_state = ExecutionState(
            iteration=self.state.iteration,
            goal=self.state.current_goal,
            actions_taken=self._extract_actions(messages),
            results=self._extract_results(messages),
            failures=self._extract_failures(messages),
            last_success_iteration=self._last_success_iteration()
        )

        result = self.reflector.reflect(exec_state, trigger)

        # Update confidence based on reflection
        self.confidence.add_signal(
            source="reflection",
            value=0.5 + result.confidence_delta,
            reason=result.assessment,
            weight=0.8
        )

        # Update state
        self.state.last_reflection_time = datetime.now()
        self.state.is_stuck = (result.assessment == "stuck")
        self.state.needs_human_help = not result.should_continue

        if self._on_reflection:
            self._on_reflection(result)

        logger.info(
            f"[ORCHESTRATOR] Reflection: {result.assessment} "
            f"(trigger: {trigger.value if trigger else 'manual'})"
        )

        return result

    def _extract_actions(self, messages: List[Dict]) -> List[Dict]:
        """Extract actions from message history."""
        actions = []
        for msg in messages:
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                # Look for tool calls or action descriptions
                if "playwright_" in content or "I'll" in content:
                    actions.append({"content": content[:200]})
        return actions[-10:]  # Last 10

    def _extract_results(self, messages: List[Dict]) -> List[Dict]:
        """Extract results from message history."""
        results = []
        for msg in messages:
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                success = "error" not in content.lower() and "fail" not in content.lower()
                results.append({"content": content[:200], "success": success})
        return results[-10:]

    def _extract_failures(self, messages: List[Dict]) -> List[Dict]:
        """Extract failures from message history."""
        failures = []
        for msg in messages:
            content = msg.get("content", "").lower()
            if any(x in content for x in ["error", "failed", "timeout", "exception"]):
                failures.append({"content": msg.get("content", "")[:200]})
        return failures

    def validate_action(self, action: Dict) -> ActionDecision:
        """
        Validate an action before execution.

        Combines:
        - Pre-execution validation (safety)
        - Confidence-based gating (behavior)
        - Mode-specific adjustments

        Returns ActionDecision with execution guidance.
        """
        warnings = []
        suggestions = []

        # 1. Pre-execution validation
        validation = self.validator.validate(
            action,
            context={"task": self.state.current_goal}
        )

        if validation.result == ValidationResult.DENY:
            return ActionDecision(
                should_execute=False,
                action=action,
                validation_result=validation,
                warnings=[f"Blocked: {validation.reason}"]
            )

        # 2. Mode-specific behavior
        modified_action = action
        confidence_adjustment = 0.0

        if self.state.mode == AgentMode.FAST_TRACK:
            # Skip extra checks, trust the action
            suggestions.append("Fast-track mode: minimal verification")

        elif self.state.mode == AgentMode.CAUTIOUS:
            # Add extra verification
            warnings.append("Cautious mode: extra verification enabled")
            confidence_adjustment = -0.1

        elif self.state.mode == AgentMode.RECOVERY:
            # Maximum caution
            warnings.append("Recovery mode: maximum caution")
            suggestions.append("Consider asking for human guidance")
            confidence_adjustment = -0.2

        # 3. Handle modified actions
        if validation.result == ValidationResult.MODIFY:
            modified_action = validation.modified_action
            suggestions.append(f"Modified: {validation.reason}")

        # 4. Confidence-based gating
        if self.confidence.should_verify():
            suggestions.append("Low confidence: results should be verified")

        if self.confidence.should_escalate():
            warnings.append("Very low confidence: consider asking for help")
            if self.state.mode != AgentMode.RECOVERY:
                self.state.mode = AgentMode.RECOVERY

        return ActionDecision(
            should_execute=True,
            action=action,
            modified_action=modified_action if modified_action != action else None,
            validation_result=validation,
            confidence_adjustment=confidence_adjustment,
            warnings=warnings,
            suggestions=suggestions
        )

    def record_result(
        self,
        action: Dict,
        result: Any,
        success: bool,
        had_meaningful_progress: bool = False
    ):
        """
        Record action result and update all systems.

        Updates:
        - Confidence orchestrator
        - Online reflector
        - State counters
        """
        self.state.total_actions += 1
        self.state.last_action_time = datetime.now()

        if success:
            self.state.successful_actions += 1
        else:
            self.state.failed_actions += 1

        # Update confidence
        self.confidence.record_action(success)

        # Update reflector
        self.reflector.record_action_result(
            success,
            had_meaningful_progress=had_meaningful_progress
        )
        self.reflector.update_confidence(self.confidence.state.overall)

        # Add context budget tracking
        if hasattr(result, 'content') or isinstance(result, dict):
            content = result.get('content', str(result)) if isinstance(result, dict) else str(result)
            # Determine importance based on success and content
            importance = (
                MessageImportance.MILESTONE if success and had_meaningful_progress
                else MessageImportance.NORMAL if success
                else MessageImportance.LOW
            )
            self.context_budget.add_message(
                {"role": "tool", "content": content[:500]},
                importance=importance
            )

    def add_message(self, message: Dict[str, str], importance: Optional[MessageImportance] = None):
        """Add a message to context budget tracking."""
        self.context_budget.add_message(message, importance)

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all systems."""
        return {
            "orchestrator": {
                "mode": self.state.mode.value,
                "iteration": self.state.iteration,
                "total_actions": self.state.total_actions,
                "success_rate": (
                    self.state.successful_actions / max(1, self.state.total_actions)
                ),
                "is_stuck": self.state.is_stuck,
                "needs_human_help": self.state.needs_human_help,
                "goal_progress": self.state.goal_progress
            },
            "context": self.context_budget.get_usage(),
            "confidence": self.confidence.get_state(),
            "reflection": self.reflector.get_reflection_summary()
        }

    def get_retry_intensity(self) -> int:
        """Get recommended retry count based on confidence."""
        return self.confidence.get_retry_intensity()

    def get_tool_selection_mode(self) -> str:
        """Get recommended tool selection mode."""
        return self.confidence.get_tool_selection_mode()

    def should_ask_user(self) -> Tuple[bool, str]:
        """
        Check if we should ask the user for help.

        Returns (should_ask, reason).
        """
        if self.confidence.should_escalate():
            return True, "Confidence too low, need guidance"

        if self.state.is_stuck:
            return True, "Agent is stuck, need new approach"

        if self.state.needs_human_help:
            return True, "Reflection indicated human help needed"

        if self.state.failed_actions >= 5 and self.state.successful_actions == 0:
            return True, "No successful actions, may need help"

        return False, ""

    def reset(self):
        """Reset orchestrator for new task."""
        self.state = OrchestratorState()
        self.context_budget.reset_state()
        self.confidence.reset()
        self.reflector.reset()
        logger.info("[ORCHESTRATOR] Reset for new task")


# ============================================================================
# INTEGRATION DECORATORS
# ============================================================================

def with_orchestration(orchestrator: AgenticOrchestrator):
    """
    Decorator to add orchestration to async functions.

    Usage:
        @with_orchestration(orchestrator)
        async def execute_action(action):
            return await browser.do_action(action)
    """
    def decorator(fn):
        async def wrapper(action, *args, **kwargs):
            # Validate
            decision = orchestrator.validate_action(action)
            if not decision.should_execute:
                return {"success": False, "error": decision.warnings[0] if decision.warnings else "Blocked"}

            # Execute
            actual_action = decision.modified_action or action
            result = await fn(actual_action, *args, **kwargs)

            # Record
            success = result.get("success", True) if isinstance(result, dict) else bool(result)
            orchestrator.record_result(action, result, success)

            return result
        return wrapper
    return decorator


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_orchestrator: Optional[AgenticOrchestrator] = None

def get_orchestrator() -> AgenticOrchestrator:
    """Get global agentic orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgenticOrchestrator()
    return _orchestrator

def reset_orchestrator():
    """Reset global orchestrator."""
    global _orchestrator
    if _orchestrator:
        _orchestrator.reset()
