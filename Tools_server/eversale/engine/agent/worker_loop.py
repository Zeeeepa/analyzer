"""
Worker execution loop implementing task-based agent architecture.

Based on Reddit LocalLLaMA patterns:
- Task graph, not conversation
- Planner -> Tool Selection -> Execution -> Self-Healing
- Context trimming to prevent token overflow
- Step-by-step trace recording
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Job execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    MAX_STEPS_REACHED = "max_steps_reached"
    SAFETY_VIOLATION = "safety_violation"


class ExecutionMode(Enum):
    """Execution modes for the planner."""
    TOOL_CALL = "tool_call"
    DOM_NAVIGATE = "dom_navigate"
    FINAL_ANSWER = "final_answer"
    ERROR_RECOVERY = "error_recovery"


@dataclass
class SafetyConstraints:
    """Safety constraints for worker execution."""
    allowed_domains: List[str] = field(default_factory=list)
    blocked_domains: List[str] = field(default_factory=list)
    max_retries_per_step: int = 3
    timeout_per_step: int = 30
    allow_form_submissions: bool = True
    allow_downloads: bool = False


@dataclass
class WorkerJob:
    """Job specification for the worker."""
    job_id: str
    goal: str
    start_url: str
    max_steps: int = 20
    safety: Optional[SafetyConstraints] = None
    context: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.safety is None:
            self.safety = SafetyConstraints()
        if self.context is None:
            self.context = {}


@dataclass
class StepResult:
    """Result of a single execution step."""
    step_number: int
    mode: ExecutionMode
    tool_name: Optional[str]
    action: Optional[Dict[str, Any]]
    success: bool
    result: Optional[Dict[str, Any]]
    error: Optional[str]
    timestamp: datetime
    context_size: int
    retry_count: int = 0


@dataclass
class JobResult:
    """Final result of job execution."""
    job_id: str
    status: JobStatus
    final_answer: Optional[str]
    steps: List[StepResult]
    total_steps: int
    execution_time_seconds: float
    error: Optional[str] = None
    shared_state: Optional[Dict[str, Any]] = None


class SharedState:
    """Shared state maintained across execution steps."""

    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.history: List[Dict[str, Any]] = []
        self.current_url: Optional[str] = None
        self.page_title: Optional[str] = None
        self.last_action: Optional[Dict[str, Any]] = None
        self.extracted_data: Dict[str, Any] = {}

    def update(self, key: str, value: Any):
        """Update a value in shared state."""
        self.data[key] = value

    def get(self, key: str, default=None) -> Any:
        """Get a value from shared state."""
        return self.data.get(key, default)

    def add_history(self, event: Dict[str, Any]):
        """Add an event to history."""
        self.history.append({
            **event,
            "timestamp": datetime.now().isoformat()
        })

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "data": self.data,
            "current_url": self.current_url,
            "page_title": self.page_title,
            "last_action": self.last_action,
            "extracted_data": self.extracted_data,
            "history_size": len(self.history)
        }


class ContextTrimmer:
    """Manages context size by trimming old steps."""

    def __init__(self, max_recent_steps: int = 3):
        self.max_recent_steps = max_recent_steps

    def trim_context(
        self,
        system_prompt: str,
        step_history: List[StepResult],
        current_dom: Optional[str],
        shared_state: SharedState
    ) -> Dict[str, Any]:
        """
        Trim context to prevent token overflow.

        Strategy:
        - Always keep: system prompt
        - Keep recent: last N steps
        - Keep current: DOM snapshot, shared state
        - Summarize: older steps
        """
        recent_steps = step_history[-self.max_recent_steps:] if len(step_history) > self.max_recent_steps else step_history

        # Summarize older steps if any
        older_steps_summary = None
        if len(step_history) > self.max_recent_steps:
            older_count = len(step_history) - self.max_recent_steps
            older_steps_summary = f"[{older_count} earlier steps executed]"

        return {
            "system_prompt": system_prompt,
            "older_steps_summary": older_steps_summary,
            "recent_steps": recent_steps,
            "current_dom": current_dom,
            "shared_state": shared_state.to_dict()
        }


class WorkerLoop:
    """
    Main worker execution loop.

    Implements task-based agent architecture:
    1. Planner decides next action
    2. DOM Navigator for web interactions
    3. Executor runs actions
    4. Self-Healing on errors
    5. Loop until final answer or max steps
    """

    def __init__(
        self,
        planner_node,
        dom_navigator_node,
        browser_executor,
        self_healing_node
    ):
        """
        Initialize worker loop with dependencies.

        Args:
            planner_node: PlannerNode instance
            dom_navigator_node: DOMNavigatorNode instance
            browser_executor: BrowserExecutor instance
            self_healing_node: SelfHealingNode instance
        """
        self.planner = planner_node
        self.dom_navigator = dom_navigator_node
        self.executor = browser_executor
        self.healer = self_healing_node
        self.context_trimmer = ContextTrimmer(max_recent_steps=3)

        logger.info("WorkerLoop initialized with all components")

    async def run(self, job: WorkerJob) -> JobResult:
        """
        Main execution loop.

        Args:
            job: WorkerJob specification

        Returns:
            JobResult with execution details
        """
        logger.info(f"Starting job {job.job_id}: {job.goal}")
        start_time = datetime.now()

        # Initialize state
        shared_state = SharedState()
        shared_state.current_url = job.start_url
        step_history: List[StepResult] = []
        final_answer: Optional[str] = None
        status = JobStatus.RUNNING
        error_message: Optional[str] = None

        # System prompt
        system_prompt = self._build_system_prompt(job)

        try:
            # Navigate to start URL
            await self._initialize_browser(job.start_url)

            # Main execution loop
            for step_num in range(1, job.max_steps + 1):
                logger.info(f"Step {step_num}/{job.max_steps}")

                try:
                    # Get current DOM snapshot
                    current_dom = await self._get_compressed_dom()

                    # Trim context
                    context = self.context_trimmer.trim_context(
                        system_prompt=system_prompt,
                        step_history=step_history,
                        current_dom=current_dom,
                        shared_state=shared_state
                    )

                    # Step 1: Planner decides next action
                    planner_decision = await self._call_planner(
                        goal=job.goal,
                        context=context,
                        shared_state=shared_state
                    )

                    logger.debug(f"Planner decision: mode={planner_decision.get('mode')}, tool={planner_decision.get('tool_name')}")

                    # Check if final answer
                    if planner_decision.get("mode") == ExecutionMode.FINAL_ANSWER.value:
                        final_answer = planner_decision.get("answer")
                        step_result = StepResult(
                            step_number=step_num,
                            mode=ExecutionMode.FINAL_ANSWER,
                            tool_name=None,
                            action=None,
                            success=True,
                            result={"answer": final_answer},
                            error=None,
                            timestamp=datetime.now(),
                            context_size=len(str(context))
                        )
                        step_history.append(step_result)
                        status = JobStatus.SUCCESS
                        break

                    # Step 2: Execute action with retry logic
                    step_result = await self._execute_step_with_retry(
                        step_num=step_num,
                        planner_decision=planner_decision,
                        current_dom=current_dom,
                        shared_state=shared_state,
                        job=job,
                        context_size=len(str(context))
                    )

                    step_history.append(step_result)

                    # Update shared state on success
                    if step_result.success:
                        await self._update_shared_state(shared_state, step_result)
                    else:
                        logger.warning(f"Step {step_num} failed: {step_result.error}")
                        # Continue to next step to allow recovery

                    # Small delay between steps
                    await asyncio.sleep(0.5)

                except Exception as step_error:
                    logger.error(f"Error in step {step_num}: {step_error}", exc_info=True)
                    step_result = StepResult(
                        step_number=step_num,
                        mode=ExecutionMode.ERROR_RECOVERY,
                        tool_name=None,
                        action=None,
                        success=False,
                        result=None,
                        error=str(step_error),
                        timestamp=datetime.now(),
                        context_size=0
                    )
                    step_history.append(step_result)

                    # Decide whether to continue or abort
                    if self._is_fatal_error(step_error):
                        status = JobStatus.FAILED
                        error_message = str(step_error)
                        break

            # Check if max steps reached
            if step_num >= job.max_steps and status == JobStatus.RUNNING:
                status = JobStatus.MAX_STEPS_REACHED
                logger.warning(f"Max steps ({job.max_steps}) reached for job {job.job_id}")

        except Exception as e:
            logger.error(f"Fatal error in job {job.job_id}: {e}", exc_info=True)
            status = JobStatus.FAILED
            error_message = str(e)

        # Calculate execution time
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        # Build final result
        result = JobResult(
            job_id=job.job_id,
            status=status,
            final_answer=final_answer,
            steps=step_history,
            total_steps=len(step_history),
            execution_time_seconds=execution_time,
            error=error_message,
            shared_state=shared_state.to_dict()
        )

        logger.info(f"Job {job.job_id} completed: status={status.value}, steps={len(step_history)}, time={execution_time:.2f}s")

        return result

    async def _execute_step_with_retry(
        self,
        step_num: int,
        planner_decision: Dict[str, Any],
        current_dom: str,
        shared_state: SharedState,
        job: WorkerJob,
        context_size: int
    ) -> StepResult:
        """
        Execute a step with retry logic and self-healing.

        Args:
            step_num: Current step number
            planner_decision: Decision from planner
            current_dom: Current DOM snapshot
            shared_state: Shared state
            job: Job specification
            context_size: Size of current context

        Returns:
            StepResult
        """
        mode_str = planner_decision.get("mode")
        mode = ExecutionMode(mode_str) if mode_str else ExecutionMode.TOOL_CALL
        tool_name = planner_decision.get("tool_name")

        last_error: Optional[str] = None

        for retry in range(job.safety.max_retries_per_step):
            try:
                # Execute based on mode
                if mode == ExecutionMode.DOM_NAVIGATE:
                    # Call DOM Navigator
                    nav_result = await self._call_dom_navigator(
                        goal=job.goal,
                        current_dom=current_dom,
                        shared_state=shared_state
                    )

                    # Execute actions via Executor
                    exec_result = await self.executor.execute_actions(nav_result.get("actions", []))

                    if exec_result.get("success"):
                        return StepResult(
                            step_number=step_num,
                            mode=mode,
                            tool_name="dom_navigator",
                            action=nav_result,
                            success=True,
                            result=exec_result,
                            error=None,
                            timestamp=datetime.now(),
                            context_size=context_size,
                            retry_count=retry
                        )
                    else:
                        last_error = exec_result.get("error", "Unknown execution error")

                elif mode == ExecutionMode.TOOL_CALL:
                    # Execute tool directly
                    tool_params = planner_decision.get("parameters", {})
                    exec_result = await self.executor.execute_tool(tool_name, tool_params)

                    if exec_result.get("success"):
                        return StepResult(
                            step_number=step_num,
                            mode=mode,
                            tool_name=tool_name,
                            action=tool_params,
                            success=True,
                            result=exec_result,
                            error=None,
                            timestamp=datetime.now(),
                            context_size=context_size,
                            retry_count=retry
                        )
                    else:
                        last_error = exec_result.get("error", "Unknown tool error")

                # If we got an error, try self-healing
                if last_error and retry < job.safety.max_retries_per_step - 1:
                    logger.info(f"Attempting self-healing (retry {retry + 1})")
                    healing_result = await self._call_self_healing(
                        error=last_error,
                        action=planner_decision,
                        current_dom=current_dom
                    )

                    if healing_result.get("can_retry"):
                        # Update action with healed parameters
                        planner_decision = healing_result.get("modified_action", planner_decision)
                        await asyncio.sleep(1)  # Brief delay before retry
                        continue
                    else:
                        # Can't heal, break retry loop
                        break

            except asyncio.TimeoutError:
                last_error = f"Step timeout after {job.safety.timeout_per_step}s"
                logger.warning(last_error)
            except Exception as e:
                last_error = str(e)
                logger.error(f"Error executing step: {e}", exc_info=True)

        # All retries failed
        return StepResult(
            step_number=step_num,
            mode=mode,
            tool_name=tool_name,
            action=planner_decision,
            success=False,
            result=None,
            error=last_error or "Failed after retries",
            timestamp=datetime.now(),
            context_size=context_size,
            retry_count=job.safety.max_retries_per_step
        )

    async def _call_planner(
        self,
        goal: str,
        context: Dict[str, Any],
        shared_state: SharedState
    ) -> Dict[str, Any]:
        """
        Call planner node to decide next action.

        Args:
            goal: User's goal
            context: Trimmed context
            shared_state: Current shared state

        Returns:
            Planner decision
        """
        try:
            decision = await self.planner.plan(
                goal=goal,
                context=context,
                shared_state=shared_state.to_dict()
            )
            return decision
        except Exception as e:
            logger.error(f"Planner error: {e}", exc_info=True)
            # Fallback: return a safe default action
            return {
                "mode": ExecutionMode.FINAL_ANSWER.value,
                "answer": f"Error in planning: {str(e)}"
            }

    async def _call_dom_navigator(
        self,
        goal: str,
        current_dom: str,
        shared_state: SharedState
    ) -> Dict[str, Any]:
        """
        Call DOM navigator node to generate navigation actions.

        Args:
            goal: User's goal
            current_dom: Compressed DOM
            shared_state: Current shared state

        Returns:
            Navigation actions
        """
        try:
            nav_result = await self.dom_navigator.navigate(
                goal=goal,
                dom=current_dom,
                state=shared_state.to_dict()
            )
            return nav_result
        except Exception as e:
            logger.error(f"DOM Navigator error: {e}", exc_info=True)
            return {
                "actions": [],
                "error": str(e)
            }

    async def _call_self_healing(
        self,
        error: str,
        action: Dict[str, Any],
        current_dom: str
    ) -> Dict[str, Any]:
        """
        Call self-healing node to recover from error.

        Args:
            error: Error message
            action: Failed action
            current_dom: Current DOM state

        Returns:
            Healing result with modified action
        """
        try:
            healing_result = await self.healer.heal(
                error=error,
                action=action,
                dom=current_dom
            )
            return healing_result
        except Exception as e:
            logger.error(f"Self-healing error: {e}", exc_info=True)
            return {
                "can_retry": False,
                "reason": str(e)
            }

    async def _initialize_browser(self, url: str):
        """Initialize browser and navigate to start URL."""
        try:
            await self.executor.navigate(url)
            logger.info(f"Navigated to start URL: {url}")
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")
            raise

    async def _get_compressed_dom(self) -> Optional[str]:
        """Get compressed DOM snapshot from current page."""
        try:
            dom = await self.executor.get_compressed_dom()
            return dom
        except Exception as e:
            logger.error(f"Failed to get compressed DOM: {e}")
            return None

    async def _update_shared_state(
        self,
        shared_state: SharedState,
        step_result: StepResult
    ):
        """
        Update shared state based on step result.

        Args:
            shared_state: Shared state to update
            step_result: Result of execution step
        """
        try:
            # Update last action
            shared_state.last_action = step_result.action

            # Update current URL if changed
            current_url = await self.executor.get_current_url()
            if current_url:
                shared_state.current_url = current_url

            # Update page title
            page_title = await self.executor.get_page_title()
            if page_title:
                shared_state.page_title = page_title

            # Add to history
            shared_state.add_history({
                "step": step_result.step_number,
                "mode": step_result.mode.value,
                "tool": step_result.tool_name,
                "success": step_result.success
            })

            # Extract any data from result
            if step_result.result and "extracted_data" in step_result.result:
                shared_state.extracted_data.update(step_result.result["extracted_data"])

        except Exception as e:
            logger.error(f"Error updating shared state: {e}", exc_info=True)

    def _build_system_prompt(self, job: WorkerJob) -> str:
        """Build system prompt for the job."""
        return f"""You are an autonomous web agent executing a specific task.

Task: {job.goal}
Starting URL: {job.start_url}
Max Steps: {job.max_steps}

Your job is to:
1. Analyze the current page state
2. Decide on the next action
3. Execute actions to progress toward the goal
4. Extract relevant information
5. Provide a final answer when the task is complete

Remember:
- Be efficient and goal-oriented
- Handle errors gracefully
- Extract structured data when possible
- Provide clear final answers
"""

    def _is_fatal_error(self, error: Exception) -> bool:
        """
        Check if an error is fatal and should abort execution.

        Args:
            error: Exception that occurred

        Returns:
            True if fatal, False if recoverable
        """
        fatal_error_types = (
            MemoryError,
            SystemExit,
            KeyboardInterrupt
        )
        return isinstance(error, fatal_error_types)


# Convenience function for running a job
async def run_worker_job(
    job: WorkerJob,
    planner_node,
    dom_navigator_node,
    browser_executor,
    self_healing_node
) -> JobResult:
    """
    Convenience function to run a worker job.

    Args:
        job: WorkerJob specification
        planner_node: PlannerNode instance
        dom_navigator_node: DOMNavigatorNode instance
        browser_executor: BrowserExecutor instance
        self_healing_node: SelfHealingNode instance

    Returns:
        JobResult
    """
    worker = WorkerLoop(
        planner_node=planner_node,
        dom_navigator_node=dom_navigator_node,
        browser_executor=browser_executor,
        self_healing_node=self_healing_node
    )

    return await worker.run(job)
