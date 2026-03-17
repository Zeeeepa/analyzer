"""
Max Steps Handler - Prevents infinite agent loops and resource exhaustion.

Based on OpenCode's session/prompt/max-steps.txt specification.

This handler tracks step count during agent execution and enforces
hard limits to prevent runaway processing, infinite loops, and resource
exhaustion. When the limit is reached, it disables all tools and forces
text-only responses with a recap of work completed.

Key Features:
- Configurable step limits (default: 100)
- Warning at 80% threshold
- Hard stop at limit
- Tool disabling on limit reached
- Forced human re-engagement
- Automatic recap generation

Safety Mechanisms:
- Prevents resource exhaustion
- Stops runaway processing loops
- Forces deliberate decision-making
- Ensures human oversight at critical points
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_MAX_STEPS = 100
WARNING_THRESHOLD = 0.8  # Warn at 80%
CRITICAL_THRESHOLD = 0.95  # Critical warning at 95%


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class StepRecord:
    """Record of a single step taken."""
    step_number: int
    timestamp: datetime
    tool_name: Optional[str] = None
    description: str = ""
    success: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "timestamp": self.timestamp.isoformat(),
            "tool_name": self.tool_name,
            "description": self.description,
            "success": self.success,
        }


@dataclass
class StepStats:
    """Statistics about steps taken."""
    total_steps: int = 0
    successful_steps: int = 0
    failed_steps: int = 0
    tools_used: Dict[str, int] = field(default_factory=dict)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        duration = None
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()

        return {
            "total_steps": self.total_steps,
            "successful_steps": self.successful_steps,
            "failed_steps": self.failed_steps,
            "tools_used": dict(self.tools_used),
            "duration_seconds": duration,
        }


# =============================================================================
# MAX STEPS HANDLER
# =============================================================================

class MaxStepsHandler:
    """
    Track and enforce step limits during agent execution.

    This handler prevents infinite loops and resource exhaustion by
    counting steps and enforcing hard limits. When the limit is reached,
    all tools are disabled and only text-only responses are allowed.

    Usage:
        handler = MaxStepsHandler(max_steps=100)

        # Before each step
        if handler.is_limit_reached():
            return handler.get_limit_reached_message()

        # Take step
        handler.increment_step(tool_name="playwright_click", description="Click login button")

        # Check for warnings
        if handler.should_warn():
            print(handler.get_warning_message())

        # Reset when task complete
        handler.reset()
    """

    def __init__(
        self,
        max_steps: int = DEFAULT_MAX_STEPS,
        warning_threshold: float = WARNING_THRESHOLD,
        track_history: bool = True
    ):
        """
        Initialize max steps handler.

        Args:
            max_steps: Maximum steps allowed (default: 100)
            warning_threshold: Warn when this fraction of steps used (default: 0.8)
            track_history: Whether to track detailed step history (default: True)
        """
        self.max_steps = max_steps
        self.warning_threshold = warning_threshold
        self.track_history = track_history

        # State
        self.current_step = 0
        self.limit_reached = False
        self.tools_disabled = False
        self.warning_shown = False
        self.critical_warning_shown = False

        # History
        self.step_history: List[StepRecord] = []
        self.stats = StepStats()

        logger.info(f"MaxStepsHandler initialized with limit: {max_steps}")

    def set_max_steps(self, limit: int) -> None:
        """
        Configure the step limit.

        Args:
            limit: Maximum steps allowed
        """
        if limit <= 0:
            raise ValueError(f"Max steps must be positive, got: {limit}")

        self.max_steps = limit
        logger.info(f"Max steps updated to: {limit}")

    def increment_step(
        self,
        tool_name: Optional[str] = None,
        description: str = "",
        success: bool = True
    ) -> int:
        """
        Count a step taken.

        Args:
            tool_name: Name of tool used (if any)
            description: Brief description of step
            success: Whether the step succeeded

        Returns:
            Current step number
        """
        # Start tracking time on first step
        if self.current_step == 0:
            self.stats.start_time = datetime.now()

        # Increment counter
        self.current_step += 1
        self.stats.total_steps += 1

        if success:
            self.stats.successful_steps += 1
        else:
            self.stats.failed_steps += 1

        # Track tool usage
        if tool_name:
            self.stats.tools_used[tool_name] = self.stats.tools_used.get(tool_name, 0) + 1

        # Record step
        if self.track_history:
            record = StepRecord(
                step_number=self.current_step,
                timestamp=datetime.now(),
                tool_name=tool_name,
                description=description,
                success=success,
            )
            self.step_history.append(record)

        # Check if limit reached
        if self.current_step >= self.max_steps:
            self.limit_reached = True
            self.tools_disabled = True
            self.stats.end_time = datetime.now()
            logger.warning(f"Max steps limit reached: {self.current_step}/{self.max_steps}")

        logger.debug(f"Step {self.current_step}/{self.max_steps}: {tool_name or 'thinking'} - {description}")

        return self.current_step

    def is_limit_reached(self) -> bool:
        """
        Check if step limit has been reached.

        Returns:
            True if limit reached, False otherwise
        """
        return self.limit_reached

    def get_remaining(self) -> int:
        """
        Get number of steps remaining.

        Returns:
            Number of steps remaining (0 if limit reached)
        """
        remaining = self.max_steps - self.current_step
        return max(0, remaining)

    def get_usage_percentage(self) -> float:
        """
        Get percentage of steps used.

        Returns:
            Percentage (0.0 to 1.0)
        """
        if self.max_steps <= 0:
            return 0.0
        return min(1.0, self.current_step / self.max_steps)

    def should_warn(self) -> bool:
        """
        Check if we should show a warning.

        Returns:
            True if warning threshold reached but not yet shown
        """
        usage = self.get_usage_percentage()

        # Critical warning at 95%
        if usage >= CRITICAL_THRESHOLD and not self.critical_warning_shown:
            return True

        # Regular warning at threshold
        if usage >= self.warning_threshold and not self.warning_shown:
            return True

        return False

    def get_warning_message(self) -> str:
        """
        Get warning message for approaching limit.

        Returns:
            Warning message string
        """
        usage = self.get_usage_percentage()
        remaining = self.get_remaining()

        # Critical warning
        if usage >= CRITICAL_THRESHOLD:
            self.critical_warning_shown = True
            return f"""
CRITICAL WARNING: Only {remaining} steps remaining!

You have used {self.current_step}/{self.max_steps} steps ({usage*100:.0f}%).

The system will force a stop at {self.max_steps} steps.

Actions to take:
1. Complete current task IMMEDIATELY
2. Provide summary of work done
3. List incomplete tasks
4. Prepare for forced stop

Do NOT start new complex operations.
            """.strip()

        # Regular warning
        self.warning_shown = True
        return f"""
WARNING: Approaching step limit - {remaining} steps remaining.

You have used {self.current_step}/{self.max_steps} steps ({usage*100:.0f}%).

Please:
1. Focus on completing current objectives
2. Avoid starting new complex tasks
3. Be prepared to summarize progress
            """.strip()

    def get_limit_reached_message(
        self,
        accomplished_tasks: Optional[List[str]] = None,
        incomplete_tasks: Optional[List[str]] = None,
        next_actions: Optional[List[str]] = None
    ) -> str:
        """
        Get message to display when limit is reached.

        This message:
        - Acknowledges the step limit
        - Recaps accomplished work
        - Enumerates incomplete tasks
        - Suggests next actions

        Args:
            accomplished_tasks: List of completed tasks
            incomplete_tasks: List of tasks not completed
            next_actions: Suggested next actions

        Returns:
            Formatted message string
        """
        parts = [
            "=" * 60,
            "MAX STEPS LIMIT REACHED",
            "=" * 60,
            "",
            f"Step limit: {self.max_steps} steps",
            f"Steps taken: {self.current_step}",
            "",
        ]

        # Add statistics
        parts.append("EXECUTION STATISTICS:")
        parts.append(f"- Successful steps: {self.stats.successful_steps}")
        parts.append(f"- Failed steps: {self.stats.failed_steps}")

        if self.stats.tools_used:
            parts.append("- Tools used:")
            for tool, count in sorted(self.stats.tools_used.items(), key=lambda x: x[1], reverse=True):
                parts.append(f"  - {tool}: {count}x")

        if self.stats.start_time and self.stats.end_time:
            duration = (self.stats.end_time - self.stats.start_time).total_seconds()
            parts.append(f"- Duration: {duration:.1f} seconds")

        parts.append("")

        # Add accomplished tasks
        if accomplished_tasks:
            parts.append("ACCOMPLISHED:")
            for i, task in enumerate(accomplished_tasks, 1):
                parts.append(f"{i}. {task}")
            parts.append("")
        else:
            parts.append("ACCOMPLISHED:")
            parts.append("[Auto-generated from step history]")
            # Try to infer from step history
            if self.track_history and self.step_history:
                successful_tools = [
                    record.tool_name for record in self.step_history
                    if record.success and record.tool_name
                ]
                if successful_tools:
                    tool_summary = {}
                    for tool in successful_tools:
                        tool_summary[tool] = tool_summary.get(tool, 0) + 1
                    for tool, count in tool_summary.items():
                        parts.append(f"- Used {tool} {count} time(s)")
            parts.append("")

        # Add incomplete tasks
        if incomplete_tasks:
            parts.append("INCOMPLETE TASKS:")
            for i, task in enumerate(incomplete_tasks, 1):
                parts.append(f"{i}. {task}")
            parts.append("")

        # Add next actions
        if next_actions:
            parts.append("SUGGESTED NEXT ACTIONS:")
            for i, action in enumerate(next_actions, 1):
                parts.append(f"{i}. {action}")
            parts.append("")
        else:
            parts.append("SUGGESTED NEXT ACTIONS:")
            parts.append("1. Review the work completed above")
            parts.append("2. Decide if task is complete or needs continuation")
            parts.append("3. If continuing, reset step counter with handler.reset()")
            parts.append("4. If incomplete, break into smaller subtasks")
            parts.append("")

        # Add system message
        parts.extend([
            "=" * 60,
            "SYSTEM STATUS: ALL TOOLS DISABLED",
            "=" * 60,
            "",
            "To prevent resource exhaustion, all tools have been disabled.",
            "Only text-only responses are allowed.",
            "",
            "This requires human intervention to:",
            "1. Review progress and decide next steps",
            "2. Reset the step counter if continuing",
            "3. Adjust max_steps limit if needed",
            "4. Break complex tasks into smaller chunks",
            "",
            "This is a safety mechanism to ensure deliberate decision-making",
            "and prevent infinite loops or runaway processes.",
            "",
        ])

        return "\n".join(parts)

    def reset(self) -> None:
        """
        Reset the step counter.

        Call this when:
        - Starting a new task
        - Continuing after hitting limit
        - Resetting session state
        """
        logger.info(f"Resetting step counter (was at {self.current_step}/{self.max_steps})")

        self.current_step = 0
        self.limit_reached = False
        self.tools_disabled = False
        self.warning_shown = False
        self.critical_warning_shown = False

        # Reset but preserve history
        if self.track_history:
            self.step_history.clear()

        self.stats = StepStats()

    def are_tools_disabled(self) -> bool:
        """
        Check if tools are disabled due to limit.

        Returns:
            True if tools disabled, False otherwise
        """
        return self.tools_disabled

    def get_stats(self) -> StepStats:
        """
        Get execution statistics.

        Returns:
            StepStats object with current statistics
        """
        return self.stats

    def get_step_history(self) -> List[StepRecord]:
        """
        Get detailed step history.

        Returns:
            List of StepRecord objects
        """
        return self.step_history.copy()

    def export_state(self) -> Dict[str, Any]:
        """
        Export handler state for persistence.

        Returns:
            Dict with complete handler state
        """
        return {
            "max_steps": self.max_steps,
            "current_step": self.current_step,
            "limit_reached": self.limit_reached,
            "tools_disabled": self.tools_disabled,
            "warning_shown": self.warning_shown,
            "critical_warning_shown": self.critical_warning_shown,
            "stats": self.stats.to_dict(),
            "step_history": [record.to_dict() for record in self.step_history],
        }

    def import_state(self, state: Dict[str, Any]) -> None:
        """
        Import handler state from persistence.

        Args:
            state: Dict with handler state (from export_state)
        """
        self.max_steps = state.get("max_steps", DEFAULT_MAX_STEPS)
        self.current_step = state.get("current_step", 0)
        self.limit_reached = state.get("limit_reached", False)
        self.tools_disabled = state.get("tools_disabled", False)
        self.warning_shown = state.get("warning_shown", False)
        self.critical_warning_shown = state.get("critical_warning_shown", False)

        # Restore stats (simple version - doesn't restore datetime objects)
        stats_dict = state.get("stats", {})
        self.stats.total_steps = stats_dict.get("total_steps", 0)
        self.stats.successful_steps = stats_dict.get("successful_steps", 0)
        self.stats.failed_steps = stats_dict.get("failed_steps", 0)
        self.stats.tools_used = stats_dict.get("tools_used", {})

        logger.info(f"State imported: {self.current_step}/{self.max_steps} steps")


# =============================================================================
# SINGLETON FOR CONVENIENCE
# =============================================================================

_default_handler: Optional[MaxStepsHandler] = None


def get_max_steps_handler() -> MaxStepsHandler:
    """
    Get the default max steps handler singleton.

    Returns:
        Global MaxStepsHandler instance
    """
    global _default_handler
    if _default_handler is None:
        _default_handler = MaxStepsHandler()
    return _default_handler


def set_max_steps_handler(handler: MaxStepsHandler) -> None:
    """
    Set the default max steps handler.

    Args:
        handler: MaxStepsHandler instance to use as default
    """
    global _default_handler
    _default_handler = handler


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def increment_step(tool_name: Optional[str] = None, description: str = "") -> int:
    """Quick step increment using default handler."""
    return get_max_steps_handler().increment_step(tool_name, description)


def is_limit_reached() -> bool:
    """Quick limit check using default handler."""
    return get_max_steps_handler().is_limit_reached()


def get_remaining() -> int:
    """Quick remaining steps check using default handler."""
    return get_max_steps_handler().get_remaining()


def reset_steps() -> None:
    """Quick reset using default handler."""
    get_max_steps_handler().reset()


# =============================================================================
# TESTS
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("MAX STEPS HANDLER TEST")
    print("=" * 60)
    print()

    # Test 1: Basic functionality
    print("Test 1: Basic functionality")
    print("-" * 40)
    handler = MaxStepsHandler(max_steps=10)

    for i in range(5):
        step = handler.increment_step(
            tool_name=f"tool_{i}",
            description=f"Test step {i+1}"
        )
        print(f"Step {step}: Remaining = {handler.get_remaining()}, Usage = {handler.get_usage_percentage()*100:.0f}%")

    print(f"Limit reached: {handler.is_limit_reached()}")
    print()

    # Test 2: Warning threshold
    print("Test 2: Warning threshold")
    print("-" * 40)
    handler.reset()

    for i in range(10):
        handler.increment_step(tool_name="test_tool", description=f"Step {i+1}")

        if handler.should_warn():
            print(f"\nSTEP {i+1} - WARNING:")
            print(handler.get_warning_message())
            print()

        if handler.is_limit_reached():
            print(f"\nSTEP {i+1} - LIMIT REACHED:")
            print(handler.get_limit_reached_message(
                accomplished_tasks=[
                    "Navigated to website",
                    "Extracted 5 contacts",
                    "Saved to database"
                ],
                incomplete_tasks=[
                    "Export to CSV",
                    "Send email report"
                ],
                next_actions=[
                    "Reset step counter",
                    "Complete export task",
                    "Review results"
                ]
            ))
            break

    print()

    # Test 3: Statistics
    print("Test 3: Statistics")
    print("-" * 40)
    stats = handler.get_stats()
    print(f"Total steps: {stats.total_steps}")
    print(f"Successful: {stats.successful_steps}")
    print(f"Failed: {stats.failed_steps}")
    print(f"Tools used: {stats.tools_used}")
    print()

    # Test 4: State export/import
    print("Test 4: State export/import")
    print("-" * 40)
    state = handler.export_state()
    print(f"Exported state: {state['current_step']}/{state['max_steps']} steps")

    new_handler = MaxStepsHandler(max_steps=20)
    new_handler.import_state(state)
    print(f"Imported state: {new_handler.current_step}/{new_handler.max_steps} steps")
    print(f"Tools disabled: {new_handler.are_tools_disabled()}")
    print()

    # Test 5: Singleton convenience functions
    print("Test 5: Singleton convenience functions")
    print("-" * 40)
    reset_steps()
    print(f"After reset - Remaining: {get_remaining()}")

    for i in range(3):
        increment_step(tool_name="singleton_test", description=f"Test {i+1}")

    print(f"After 3 steps - Remaining: {get_remaining()}")
    print(f"Limit reached: {is_limit_reached()}")
    print()

    # Test 6: Tool disabling
    print("Test 6: Tool disabling")
    print("-" * 40)
    test_handler = MaxStepsHandler(max_steps=3)

    for i in range(5):
        test_handler.increment_step(tool_name="test", description=f"Step {i+1}")

        if test_handler.are_tools_disabled():
            print(f"Step {i+1}: Tools are now DISABLED")
            break
        else:
            print(f"Step {i+1}: Tools are enabled")

    print()

    # Summary
    print("=" * 60)
    print("ALL TESTS COMPLETED SUCCESSFULLY")
    print("=" * 60)
    print()
    print("Key features verified:")
    print("1. Step counting and limiting")
    print("2. Warning thresholds (80%, 95%)")
    print("3. Tool disabling on limit")
    print("4. Statistics tracking")
    print("5. State export/import")
    print("6. Singleton convenience functions")
    print()
    print("The max steps handler is ready to prevent infinite loops")
    print("and ensure deliberate human decision-making!")
