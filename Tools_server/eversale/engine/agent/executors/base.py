"""
Base Executor - Foundation for all action executors.

Each executor:
1. Validates required parameters
2. Checks login requirements
3. Executes the action
4. Returns structured results
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import asyncio
from loguru import logger


class ActionStatus(Enum):
    """Status of an action execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"  # Partially completed
    FAILED = "failed"
    BLOCKED = "blocked"  # Needs login or approval


@dataclass
class ActionResult:
    """Result of an action execution."""
    status: ActionStatus
    action_id: str
    capability: str
    action: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: int = 0
    next_actions: List[str] = field(default_factory=list)  # Suggested follow-ups
    message: str = ""  # Human-readable result


@dataclass
class ValidationResult:
    """Result of parameter validation."""
    valid: bool
    missing_params: List[str] = field(default_factory=list)
    invalid_params: Dict[str, str] = field(default_factory=dict)  # param -> error message
    warnings: List[str] = field(default_factory=list)


class BaseExecutor(ABC):
    """Base class for all action executors."""

    # Override in subclasses
    capability: str = ""
    action: str = ""
    required_params: List[str] = []
    optional_params: List[str] = []
    requires_login: List[str] = []

    def __init__(self, browser=None, context: Dict[str, Any] = None):
        self.browser = browser
        self.context = context or {}
        self.action_id = f"{self.capability}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def validate(self, params: Dict[str, Any]) -> ValidationResult:
        """Validate parameters before execution."""
        missing = []
        invalid = {}
        warnings = []

        # Check required params
        for param in self.required_params:
            if param not in params or not params[param]:
                missing.append(param)

        # Subclass-specific validation
        custom_result = self._validate_custom(params)
        invalid.update(custom_result.invalid_params)
        warnings.extend(custom_result.warnings)

        return ValidationResult(
            valid=len(missing) == 0 and len(invalid) == 0,
            missing_params=missing,
            invalid_params=invalid,
            warnings=warnings
        )

    def _validate_custom(self, params: Dict[str, Any]) -> ValidationResult:
        """Override for custom validation logic."""
        return ValidationResult(valid=True)

    async def execute(self, params: Dict[str, Any]) -> ActionResult:
        """Execute the action."""
        start_time = datetime.now()

        # Validate first
        validation = self.validate(params)
        if not validation.valid:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                error=f"Validation failed: missing {validation.missing_params}, invalid {validation.invalid_params}",
                message=f"Cannot execute: missing required parameters {validation.missing_params}"
            )

        try:
            # Execute the action
            result = await self._execute(params)
            result.duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            return result

        except Exception as e:
            logger.error(f"Executor {self.capability}.{self.action} failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                error=str(e),
                duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                message=f"Action failed: {str(e)}"
            )

    @abstractmethod
    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        """Implement the actual execution logic."""
        pass

    def get_login_prompt(self) -> str:
        """Get login prompt for required services."""
        if not self.requires_login:
            return ""

        services_str = ", ".join(self.requires_login)
        return f"Please log into {services_str} to continue."


class CompositeExecutor(BaseExecutor):
    """Executor that chains multiple actions together."""

    def __init__(self, executors: List[BaseExecutor], browser=None, context: Dict[str, Any] = None):
        super().__init__(browser, context)
        self.executors = executors
        self.results: List[ActionResult] = []

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        """Execute all chained actions."""
        self.results = []
        current_params = params.copy()

        for executor in self.executors:
            result = await executor.execute(current_params)
            self.results.append(result)

            if result.status == ActionStatus.FAILED:
                return ActionResult(
                    status=ActionStatus.PARTIAL,
                    action_id=self.action_id,
                    capability="composite",
                    action="chain",
                    data={"completed": len(self.results) - 1, "results": self.results},
                    error=f"Chain failed at step {len(self.results)}: {result.error}",
                    message=f"Completed {len(self.results) - 1} of {len(self.executors)} steps"
                )

            # Pass output to next executor
            if result.data:
                current_params.update(result.data)

        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_id=self.action_id,
            capability="composite",
            action="chain",
            data={"results": self.results},
            message=f"Successfully completed all {len(self.executors)} steps"
        )


class ParallelExecutor(BaseExecutor):
    """Executor that runs multiple actions in parallel."""

    def __init__(self, executors: List[BaseExecutor], browser=None, context: Dict[str, Any] = None):
        super().__init__(browser, context)
        self.executors = executors

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        """Execute all actions in parallel."""
        tasks = [executor.execute(params) for executor in self.executors]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        successes = []
        failures = []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failures.append({"executor": i, "error": str(result)})
            elif result.status == ActionStatus.SUCCESS:
                successes.append(result)
            else:
                failures.append({"executor": i, "result": result})

        status = ActionStatus.SUCCESS if not failures else (
            ActionStatus.PARTIAL if successes else ActionStatus.FAILED
        )

        return ActionResult(
            status=status,
            action_id=self.action_id,
            capability="parallel",
            action="batch",
            data={"successes": len(successes), "failures": len(failures), "results": results},
            message=f"Completed {len(successes)}/{len(self.executors)} actions"
        )
