"""
Step Registry - Explicit memory for long multi-step sequences (100-300+ steps).

This module solves the context window bottleneck where the LLM "forgets"
earlier steps after context compaction. It provides:

1. Persistent step storage - all steps survive context compaction
2. Queryable history - retrieve relevant past steps for context
3. Dependency tracking - know which steps depend on which
4. Result caching - reuse results from completed steps

Designed for enterprise workflows with 100-300+ steps.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from loguru import logger


@dataclass
class StepRecord:
    """A single step in a long workflow."""
    step_id: str
    step_number: int
    action: str
    tool: str
    arguments: Dict[str, Any]
    status: str = "pending"  # pending, running, completed, failed, skipped
    result: Any = None
    error: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: int = 0
    depends_on: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class StepRegistry:
    """
    Maintains explicit memory of all steps in a long workflow.

    Unlike context messages which get compacted, the step registry
    preserves ALL step information for the entire workflow duration.

    Usage:
        registry = StepRegistry(workflow_id="task_123")

        # Record a step starting
        registry.start_step("s1", 1, "Navigate to site", "playwright_navigate", {"url": "..."})

        # Record step completion
        registry.complete_step("s1", {"success": True, "url": "..."})

        # Get recent context for LLM
        context = registry.get_step_context(current_step=50, lookback=10)
    """

    def __init__(
        self,
        workflow_id: str = None,
        persist_path: str = "memory/step_registry",
        auto_persist: bool = True
    ):
        self.workflow_id = workflow_id or f"wf_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.persist_path = Path(persist_path)
        self.persist_path.mkdir(parents=True, exist_ok=True)
        self.auto_persist = auto_persist

        # In-memory storage
        self.steps: Dict[str, StepRecord] = {}
        self.step_order: List[str] = []  # Maintains insertion order

        # Statistics
        self.stats = {
            "total_steps": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "total_duration_ms": 0,
            "started_at": datetime.now().isoformat(),
        }

        # Load existing if resuming
        self._load_if_exists()

    def _load_if_exists(self):
        """Load existing workflow state if resuming."""
        state_file = self.persist_path / f"{self.workflow_id}.json"
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text())
                self.stats = data.get("stats", self.stats)
                for step_data in data.get("steps", []):
                    step = StepRecord(**step_data)
                    self.steps[step.step_id] = step
                    self.step_order.append(step.step_id)
                logger.info(f"Resumed workflow {self.workflow_id} with {len(self.steps)} steps")
            except Exception as e:
                logger.warning(f"Failed to load workflow state: {e}")

    def _persist(self):
        """Save workflow state to disk."""
        if not self.auto_persist:
            return
        try:
            state_file = self.persist_path / f"{self.workflow_id}.json"
            data = {
                "workflow_id": self.workflow_id,
                "stats": self.stats,
                "steps": [asdict(self.steps[sid]) for sid in self.step_order],
                "saved_at": datetime.now().isoformat()
            }
            state_file.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger.error(f"Failed to persist workflow state: {e}")

    def start_step(
        self,
        step_id: str,
        step_number: int,
        action: str,
        tool: str,
        arguments: Dict[str, Any],
        depends_on: List[str] = None,
        metadata: Dict[str, Any] = None
    ) -> StepRecord:
        """
        Record a step starting execution.

        Args:
            step_id: Unique identifier for this step
            step_number: Sequential step number (1-based)
            action: Human-readable description of what this step does
            tool: The tool being called (e.g., "playwright_navigate")
            arguments: Tool arguments
            depends_on: List of step_ids this depends on
            metadata: Additional metadata

        Returns:
            StepRecord for this step
        """
        step = StepRecord(
            step_id=step_id,
            step_number=step_number,
            action=action,
            tool=tool,
            arguments=arguments,
            status="running",
            started_at=datetime.now().isoformat(),
            depends_on=depends_on or [],
            metadata=metadata or {}
        )

        self.steps[step_id] = step
        self.step_order.append(step_id)
        self.stats["total_steps"] += 1

        self._persist()
        return step

    def complete_step(
        self,
        step_id: str,
        result: Any,
        metadata: Dict[str, Any] = None
    ) -> StepRecord:
        """
        Record a step completing successfully.

        Args:
            step_id: The step identifier
            result: The result from the tool call
            metadata: Additional metadata to store

        Returns:
            Updated StepRecord
        """
        if step_id not in self.steps:
            logger.warning(f"Step {step_id} not found in registry")
            return None

        step = self.steps[step_id]
        step.status = "completed"
        step.result = result
        step.completed_at = datetime.now().isoformat()

        # Calculate duration
        if step.started_at:
            start = datetime.fromisoformat(step.started_at)
            end = datetime.fromisoformat(step.completed_at)
            step.duration_ms = int((end - start).total_seconds() * 1000)
            self.stats["total_duration_ms"] += step.duration_ms

        if metadata:
            step.metadata.update(metadata)

        self.stats["completed"] += 1
        self._persist()
        return step

    def fail_step(
        self,
        step_id: str,
        error: str,
        metadata: Dict[str, Any] = None
    ) -> StepRecord:
        """
        Record a step failing.

        Args:
            step_id: The step identifier
            error: Error message
            metadata: Additional metadata to store

        Returns:
            Updated StepRecord
        """
        if step_id not in self.steps:
            logger.warning(f"Step {step_id} not found in registry")
            return None

        step = self.steps[step_id]
        step.status = "failed"
        step.error = error
        step.completed_at = datetime.now().isoformat()

        if step.started_at:
            start = datetime.fromisoformat(step.started_at)
            end = datetime.fromisoformat(step.completed_at)
            step.duration_ms = int((end - start).total_seconds() * 1000)

        if metadata:
            step.metadata.update(metadata)

        self.stats["failed"] += 1
        self._persist()
        return step

    def skip_step(self, step_id: str, reason: str = "") -> StepRecord:
        """Mark a step as skipped."""
        if step_id not in self.steps:
            return None

        step = self.steps[step_id]
        step.status = "skipped"
        step.error = reason or "Skipped"
        step.completed_at = datetime.now().isoformat()

        self.stats["skipped"] += 1
        self._persist()
        return step

    def get_step(self, step_id: str) -> Optional[StepRecord]:
        """Get a specific step by ID."""
        return self.steps.get(step_id)

    def get_step_by_number(self, step_number: int) -> Optional[StepRecord]:
        """Get a step by its sequential number."""
        for step in self.steps.values():
            if step.step_number == step_number:
                return step
        return None

    def get_step_context(
        self,
        current_step: int,
        lookback: int = 10,
        include_failed: bool = True
    ) -> str:
        """
        Get a context string for the LLM summarizing recent steps.

        This is designed to be injected into prompts to maintain
        awareness of what has been done in a long workflow.

        Args:
            current_step: Current step number
            lookback: How many previous steps to include
            include_failed: Whether to include failed steps

        Returns:
            Formatted context string for LLM prompt
        """
        # Get steps in range
        start_step = max(1, current_step - lookback)
        relevant_steps = []

        for step in self.steps.values():
            if start_step <= step.step_number < current_step:
                if include_failed or step.status == "completed":
                    relevant_steps.append(step)

        if not relevant_steps:
            return ""

        # Sort by step number
        relevant_steps.sort(key=lambda s: s.step_number)

        # Build context string
        lines = [f"[Previous {len(relevant_steps)} steps:]"]
        for step in relevant_steps:
            status_icon = "✓" if step.status == "completed" else "✗" if step.status == "failed" else "○"
            result_preview = ""
            if step.result:
                # Truncate large results
                result_str = str(step.result)[:100]
                result_preview = f" → {result_str}"
            lines.append(f"  {status_icon} Step {step.step_number}: {step.action}{result_preview}")

        return "\n".join(lines)

    def get_results_for_steps(self, step_ids: List[str]) -> Dict[str, Any]:
        """
        Get results for specific steps (for dependency resolution).

        Args:
            step_ids: List of step IDs to get results for

        Returns:
            Dict mapping step_id to result
        """
        return {
            sid: self.steps[sid].result
            for sid in step_ids
            if sid in self.steps and self.steps[sid].result is not None
        }

    def find_steps_by_tool(self, tool: str) -> List[StepRecord]:
        """Find all steps that used a specific tool."""
        return [s for s in self.steps.values() if s.tool == tool]

    def find_steps_by_keyword(self, keyword: str) -> List[StepRecord]:
        """Find steps whose action contains a keyword."""
        keyword_lower = keyword.lower()
        return [
            s for s in self.steps.values()
            if keyword_lower in s.action.lower()
        ]

    def get_summary(self) -> Dict[str, Any]:
        """Get workflow summary statistics."""
        return {
            "workflow_id": self.workflow_id,
            "total_steps": self.stats["total_steps"],
            "completed": self.stats["completed"],
            "failed": self.stats["failed"],
            "skipped": self.stats["skipped"],
            "pending": self.stats["total_steps"] - self.stats["completed"] - self.stats["failed"] - self.stats["skipped"],
            "success_rate": self.stats["completed"] / max(1, self.stats["total_steps"]),
            "total_duration_seconds": self.stats["total_duration_ms"] / 1000,
            "started_at": self.stats["started_at"],
        }

    def get_failed_steps(self) -> List[StepRecord]:
        """Get all failed steps for retry/analysis."""
        return [s for s in self.steps.values() if s.status == "failed"]

    def get_pending_steps(self) -> List[StepRecord]:
        """Get all pending steps."""
        return [s for s in self.steps.values() if s.status == "pending"]

    def clear(self):
        """Clear all step data (for new workflow)."""
        self.steps.clear()
        self.step_order.clear()
        self.stats = {
            "total_steps": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "total_duration_ms": 0,
            "started_at": datetime.now().isoformat(),
        }
        # Delete persisted file
        state_file = self.persist_path / f"{self.workflow_id}.json"
        if state_file.exists():
            state_file.unlink()

    def export_to_jsonl(self, output_path: str = None) -> str:
        """
        Export all steps to JSONL format for analysis.

        Returns:
            Path to the exported file
        """
        output_path = output_path or str(self.persist_path / f"{self.workflow_id}_export.jsonl")
        with open(output_path, "w") as f:
            for step_id in self.step_order:
                step = self.steps[step_id]
                f.write(json.dumps(asdict(step), default=str) + "\n")
        return output_path


# Singleton instance for current workflow
_current_registry: Optional[StepRegistry] = None


def get_step_registry(workflow_id: str = None) -> StepRegistry:
    """
    Get or create the step registry for a workflow.

    Args:
        workflow_id: Optional workflow ID. If None, uses current or creates new.

    Returns:
        StepRegistry instance
    """
    global _current_registry

    if workflow_id and (_current_registry is None or _current_registry.workflow_id != workflow_id):
        _current_registry = StepRegistry(workflow_id=workflow_id)
    elif _current_registry is None:
        _current_registry = StepRegistry()

    return _current_registry


def reset_step_registry():
    """Reset the current registry (for new task)."""
    global _current_registry
    if _current_registry:
        _current_registry.clear()
    _current_registry = None
