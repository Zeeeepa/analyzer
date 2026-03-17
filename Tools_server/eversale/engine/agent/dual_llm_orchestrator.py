"""
Dual-LLM Orchestrator - ChromePilot v2 Pattern
================================================

Based on ChromePilot v2 architecture from Reddit LocalLLaMA.

Key Insight:
-----------
Vision model (expensive) plans ONCE. Execution model (cheap) runs per-step.
This drastically reduces costs while maintaining high quality automation.

Architecture (3 models only):
----------------------------
1. Orchestrator (Vision Model): UI-TARS
   - Sees page screenshot ONCE
   - Analyzes DOM structure
   - Creates step-by-step execution plan
   - Expensive call, done rarely (only on new pages or failures)

2. Executor (Fast Model): 0000/ui-tars-1.5-7b:latest
   - Runs per-step with native function calling
   - Has full context from previous step outputs
   - Cheap, fast calls
   - Can reference earlier results ("click video from step 2")

3. Complex Tasks: Kimi API (optional)
   - Only when 0000/ui-tars-1.5-7b:latest struggles
   - Long context understanding
   - External API call

Benefits:
--------
- 10x cost reduction (vision call once vs per-step)
- Faster execution (executor is lightweight)
- Better context (steps build on each other)
- Self-correcting (can replan on failure)

References:
----------
ChromePilot v2: Reddit LocalLLaMA discussion on dual-model browser automation
"""

import asyncio
import base64
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from loguru import logger


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class PlanStatus(Enum):
    """Status of execution plan."""
    DRAFT = "draft"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REPLANNING = "replanning"


class StepStatus(Enum):
    """Status of individual step."""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    """
    Single step in execution plan.

    Each step is designed for the fast executor model with function calling.
    Steps can reference outputs from previous steps.
    """
    step_id: str
    description: str  # Human-readable description
    tool_name: str  # Function to call (e.g., "playwright_click")
    arguments: Dict[str, Any] = field(default_factory=dict)

    # Dependencies
    depends_on: List[str] = field(default_factory=list)  # Step IDs this depends on

    # Execution state
    status: StepStatus = StepStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    # Timing
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    # Context from previous steps
    context_keys: List[str] = field(default_factory=list)  # Which outputs to include in context

    def to_dict(self) -> Dict:
        """Serialize step to dict."""
        return {
            'step_id': self.step_id,
            'description': self.description,
            'tool_name': self.tool_name,
            'arguments': self.arguments,
            'depends_on': self.depends_on,
            'status': self.status.value,
            'result': self.result,
            'error': self.error,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'context_keys': self.context_keys,
        }


@dataclass
class ExecutionPlan:
    """
    Plan created by vision model, executed by fast model.
    """
    plan_id: str
    goal: str
    steps: List[PlanStep]

    # Context at planning time
    url: str
    screenshot_hash: str  # Hash of screenshot used for planning
    dom_snapshot: Optional[Dict] = None

    # Execution state
    status: PlanStatus = PlanStatus.DRAFT
    current_step_index: int = 0

    # Results
    execution_context: Dict[str, Any] = field(default_factory=dict)  # Accumulated outputs

    # Timing
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    # Replanning
    replan_count: int = 0
    parent_plan_id: Optional[str] = None

    def to_dict(self) -> Dict:
        """Serialize plan to dict."""
        return {
            'plan_id': self.plan_id,
            'goal': self.goal,
            'steps': [s.to_dict() for s in self.steps],
            'url': self.url,
            'screenshot_hash': self.screenshot_hash,
            'dom_snapshot': self.dom_snapshot,
            'status': self.status.value,
            'current_step_index': self.current_step_index,
            'execution_context': self.execution_context,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'replan_count': self.replan_count,
            'parent_plan_id': self.parent_plan_id,
        }


@dataclass
class StepResult:
    """Result of executing a single step."""
    step_id: str
    success: bool
    data: Optional[Dict] = None
    error: Optional[str] = None

    # Context for next steps
    outputs: Dict[str, Any] = field(default_factory=dict)

    # Timing
    execution_time_ms: float = 0.0


@dataclass
class JobResult:
    """Final result of entire job."""
    goal: str
    success: bool
    plan_id: str

    # Results
    outputs: Dict[str, Any] = field(default_factory=dict)
    completed_steps: int = 0
    failed_steps: int = 0

    # Execution details
    plans_created: int = 1  # Including replans
    total_time_ms: float = 0.0

    # Error handling
    error: Optional[str] = None
    failed_at_step: Optional[str] = None


# =============================================================================
# DUAL-LLM ORCHESTRATOR
# =============================================================================

class DualLLMOrchestrator:
    """
    Orchestrates dual-LLM pattern: Vision model plans, fast model executes.

    Usage:
        orchestrator = DualLLMOrchestrator(llm_client)
        result = await orchestrator.run_job("Find CEO email", page)
    """

    # Model assignments (3 models only)
    ORCHESTRATOR_MODEL = "0000/ui-tars-1.5-7b:latest"  # UI-TARS for vision planning
    EXECUTOR_MODEL = "0000/ui-tars-1.5-7b:latest"  # qwen3 for execution + function calling

    # Limits
    MAX_STEPS_PER_PLAN = 20
    MAX_REPLANS = 3
    STEP_TIMEOUT_SECONDS = 30

    def __init__(self, llm_client, browser_manager=None, mcp=None):
        """
        Initialize orchestrator.

        Args:
            llm_client: LLMClient instance from llm_client.py
            browser_manager: BrowserManager instance (optional, for screenshots)
            mcp: MCP instance (optional, for tool execution)
        """
        self.llm_client = llm_client
        self.browser_manager = browser_manager
        self.mcp = mcp

        # State
        self.current_plan: Optional[ExecutionPlan] = None
        self.plans_history: List[ExecutionPlan] = []

        # Stats
        self.stats = {
            'total_plans': 0,
            'total_steps': 0,
            'vision_calls': 0,
            'executor_calls': 0,
        }

        logger.info("DualLLMOrchestrator initialized")
        logger.info(f"  Orchestrator (vision): {self.ORCHESTRATOR_MODEL}")
        logger.info(f"  Executor (fast): {self.EXECUTOR_MODEL}")

    async def create_plan(
        self,
        goal: str,
        screenshot: bytes,
        dom: Optional[Dict] = None,
        url: str = ""
    ) -> ExecutionPlan:
        """
        Create execution plan using vision model.

        This is the EXPENSIVE call - done once per page or on replan.

        Args:
            goal: User's goal (e.g., "Find CEO email")
            screenshot: Page screenshot as bytes
            dom: Optional DOM snapshot
            url: Current page URL

        Returns:
            ExecutionPlan with steps to execute
        """
        logger.info(f"Creating plan for goal: {goal}")
        self.stats['vision_calls'] += 1

        # Hash screenshot for tracking
        screenshot_hash = hashlib.sha256(screenshot).hexdigest()[:16]

        # Convert screenshot to base64
        screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')

        # Build prompt for vision model
        prompt = self._build_planning_prompt(goal, dom, url)

        # Call vision model
        start_time = time.time()
        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                model=self.ORCHESTRATOR_MODEL,
                images=[screenshot_b64],
                temperature=0.1,
                max_tokens=2048,
            )

            if response.error:
                logger.error(f"Vision model error: {response.error}")
                raise Exception(f"Planning failed: {response.error}")

            # Parse plan from response
            plan_data = self._parse_plan_response(response.content)

            # Create execution plan
            steps = []
            for i, step_data in enumerate(plan_data['steps']):
                step = PlanStep(
                    step_id=f"step_{i+1}",
                    description=step_data.get('description', ''),
                    tool_name=step_data.get('tool', ''),
                    arguments=step_data.get('arguments', {}),
                    depends_on=step_data.get('depends_on', []),
                    context_keys=step_data.get('context_keys', []),
                )
                steps.append(step)

            plan = ExecutionPlan(
                plan_id=f"plan_{int(time.time())}_{screenshot_hash}",
                goal=goal,
                steps=steps,
                url=url,
                screenshot_hash=screenshot_hash,
                dom_snapshot=dom,
                status=PlanStatus.DRAFT,
            )

            self.current_plan = plan
            self.plans_history.append(plan)
            self.stats['total_plans'] += 1

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(f"Plan created with {len(steps)} steps in {elapsed_ms:.0f}ms")

            return plan

        except Exception as e:
            logger.error(f"Planning failed: {e}")
            raise

    async def execute_step(
        self,
        step: PlanStep,
        context: Dict[str, Any]
    ) -> StepResult:
        """
        Execute single step using fast executor model.

        This is the CHEAP call - done per step.

        Args:
            step: Step to execute
            context: Context from previous steps

        Returns:
            StepResult with outputs
        """
        logger.info(f"Executing step: {step.step_id} - {step.description}")
        self.stats['executor_calls'] += 1

        step.status = StepStatus.EXECUTING
        step.started_at = time.time()

        start_time = time.time()

        try:
            # Build context for executor
            step_context = self._build_step_context(step, context)

            # Call executor model (function calling)
            response = await self._call_executor(step, step_context)

            # Execute the tool call
            if self.mcp:
                tool_result = await self._execute_tool(
                    step.tool_name,
                    step.arguments,
                    timeout=self.STEP_TIMEOUT_SECONDS
                )
            else:
                # Simulation mode (no MCP)
                tool_result = {'status': 'simulated', 'data': {}}

            # Extract outputs
            outputs = self._extract_step_outputs(tool_result, step)

            step.status = StepStatus.COMPLETED
            step.result = tool_result
            step.completed_at = time.time()

            elapsed_ms = (time.time() - start_time) * 1000

            logger.info(f"Step completed in {elapsed_ms:.0f}ms")

            return StepResult(
                step_id=step.step_id,
                success=True,
                data=tool_result,
                outputs=outputs,
                execution_time_ms=elapsed_ms,
            )

        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.completed_at = time.time()

            elapsed_ms = (time.time() - start_time) * 1000

            logger.error(f"Step failed after {elapsed_ms:.0f}ms: {e}")

            return StepResult(
                step_id=step.step_id,
                success=False,
                error=str(e),
                execution_time_ms=elapsed_ms,
            )

    async def run_job(
        self,
        goal: str,
        page,
        replan_on_failure: bool = True
    ) -> JobResult:
        """
        Run complete job: plan + execute.

        This is the main entry point.

        Args:
            goal: User's goal
            page: Playwright page object
            replan_on_failure: Whether to replan on step failure

        Returns:
            JobResult with final outputs
        """
        logger.info(f"Starting job: {goal}")
        start_time = time.time()

        # Capture page state
        screenshot = await self._capture_screenshot(page)
        url = page.url
        dom = await self._capture_dom(page)

        # Create initial plan
        plan = await self.create_plan(goal, screenshot, dom, url)
        plan.status = PlanStatus.EXECUTING
        plan.started_at = time.time()

        # Execute steps
        completed_steps = 0
        failed_steps = 0
        failed_at_step = None  # Track which step failed

        for step in plan.steps:
            # Check dependencies
            if not self._check_dependencies(step, plan):
                logger.warning(f"Skipping step {step.step_id} - dependencies not met")
                step.status = StepStatus.SKIPPED
                continue

            # Execute step
            result = await self.execute_step(step, plan.execution_context)
            self.stats['total_steps'] += 1

            if result.success:
                # Merge outputs into context
                plan.execution_context.update(result.outputs)
                completed_steps += 1
            else:
                failed_steps += 1
                # Track first failure
                if failed_at_step is None:
                    failed_at_step = step.step_id

                # Should we replan?
                if replan_on_failure and plan.replan_count < self.MAX_REPLANS:
                    logger.warning(f"Step failed, replanning... (attempt {plan.replan_count + 1})")
                    plan.status = PlanStatus.REPLANNING

                    # Capture new screenshot
                    screenshot = await self._capture_screenshot(page)
                    url = page.url
                    dom = await self._capture_dom(page)

                    # Create new plan
                    new_plan = await self.create_plan(goal, screenshot, dom, url)
                    new_plan.parent_plan_id = plan.plan_id
                    new_plan.replan_count = plan.replan_count + 1
                    new_plan.execution_context = plan.execution_context.copy()

                    # Switch to new plan
                    plan = new_plan
                    plan.status = PlanStatus.EXECUTING
                    plan.started_at = time.time()
                    continue
                else:
                    # No more replans, job failed
                    plan.status = PlanStatus.FAILED
                    break

        # Job completed
        if failed_steps == 0:
            plan.status = PlanStatus.COMPLETED
        else:
            plan.status = PlanStatus.FAILED

        plan.completed_at = time.time()

        total_time_ms = (time.time() - start_time) * 1000

        logger.info(f"Job completed in {total_time_ms:.0f}ms")
        logger.info(f"  Steps: {completed_steps} completed, {failed_steps} failed")
        logger.info(f"  Plans created: {len(self.plans_history)}")

        return JobResult(
            goal=goal,
            success=(plan.status == PlanStatus.COMPLETED),
            plan_id=plan.plan_id,
            outputs=plan.execution_context,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            plans_created=len(self.plans_history),
            total_time_ms=total_time_ms,
            error=None if plan.status == PlanStatus.COMPLETED else "Job failed",
            failed_at_step=failed_at_step,  # Track which step failed first
        )

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    def _build_planning_prompt(self, goal: str, dom: Optional[Dict], url: str) -> str:
        """Build prompt for vision model to create plan."""
        prompt = f"""You are a planning agent analyzing a webpage screenshot.

Goal: {goal}
URL: {url}

Your task is to create a step-by-step execution plan to achieve this goal.

Available tools:
- playwright_navigate: Navigate to URL
- playwright_click: Click element (by selector)
- playwright_fill: Fill input field
- playwright_extract_page_fast: Extract structured data
- playwright_get_text: Get text content
- playwright_screenshot: Take screenshot

Respond with a JSON plan:
{{
  "steps": [
    {{
      "description": "Click the CEO profile link",
      "tool": "playwright_click",
      "arguments": {{"selector": "a.ceo-link"}},
      "depends_on": [],
      "context_keys": []
    }},
    {{
      "description": "Extract email from contact section",
      "tool": "playwright_extract_page_fast",
      "arguments": {{"schema": {{"email": "string"}}}},
      "depends_on": ["step_1"],
      "context_keys": ["clicked_element"]
    }}
  ]
}}

Guidelines:
1. Keep steps atomic and focused
2. Use selectors visible in the screenshot
3. Specify dependencies between steps
4. List which context outputs are needed from previous steps
5. Maximum {self.MAX_STEPS_PER_PLAN} steps

Analyze the screenshot and create the plan:
"""

        if dom:
            prompt += f"\n\nDOM Summary: {json.dumps(dom, indent=2)[:500]}..."

        return prompt

    def _parse_plan_response(self, content: str) -> Dict:
        """Parse plan from vision model response."""
        try:
            # Try to extract JSON from response
            if '```json' in content:
                json_start = content.find('```json') + 7
                json_end = content.find('```', json_start)
                content = content[json_start:json_end].strip()
            elif '```' in content:
                json_start = content.find('```') + 3
                json_end = content.find('```', json_start)
                content = content[json_start:json_end].strip()

            plan_data = json.loads(content)

            if 'steps' not in plan_data:
                raise ValueError("Plan missing 'steps' field")

            return plan_data

        except Exception as e:
            logger.error(f"Failed to parse plan: {e}")
            logger.debug(f"Response content: {content}")
            raise ValueError(f"Invalid plan format: {e}")

    def _build_step_context(self, step: PlanStep, context: Dict[str, Any]) -> Dict:
        """Build context for executor from previous step outputs."""
        step_context = {
            'goal': self.current_plan.goal if self.current_plan else '',
            'step_description': step.description,
            'step_number': step.step_id,
        }

        # Include requested context keys
        for key in step.context_keys:
            if key in context:
                step_context[key] = context[key]

        return step_context

    async def _call_executor(self, step: PlanStep, context: Dict) -> Dict:
        """Call fast executor model with function calling."""
        # Build prompt for executor
        prompt = f"""Execute the following step:

Description: {step.description}
Tool: {step.tool_name}
Arguments: {json.dumps(step.arguments, indent=2)}

Context from previous steps:
{json.dumps(context, indent=2)}

Execute this step now.
"""

        response = await self.llm_client.generate(
            prompt=prompt,
            model=self.EXECUTOR_MODEL,
            temperature=0.0,
            max_tokens=512,
        )

        if response.error:
            raise Exception(f"Executor failed: {response.error}")

        return {'content': response.content}

    async def _execute_tool(
        self,
        tool_name: str,
        arguments: Dict,
        timeout: int
    ) -> Dict:
        """Execute tool via MCP."""
        if not self.mcp:
            return {'status': 'no_mcp', 'simulated': True}

        try:
            # Call MCP tool
            result = await asyncio.wait_for(
                self.mcp.call_tool(tool_name, arguments),
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            raise Exception(f"Tool execution timeout after {timeout}s")
        except Exception as e:
            raise Exception(f"Tool execution failed: {e}")

    def _extract_step_outputs(self, tool_result: Dict, step: PlanStep) -> Dict:
        """Extract outputs from tool result for context propagation."""
        outputs = {}

        # Standard outputs
        if 'data' in tool_result:
            outputs[f"{step.step_id}_data"] = tool_result['data']

        if 'text' in tool_result:
            outputs[f"{step.step_id}_text"] = tool_result['text']

        if 'elements' in tool_result:
            outputs[f"{step.step_id}_elements"] = tool_result['elements']

        # Store full result
        outputs[f"{step.step_id}_result"] = tool_result

        return outputs

    def _check_dependencies(self, step: PlanStep, plan: ExecutionPlan) -> bool:
        """Check if step dependencies are satisfied."""
        if not step.depends_on:
            return True

        for dep_id in step.depends_on:
            # Find dependency step
            dep_step = next((s for s in plan.steps if s.step_id == dep_id), None)
            if not dep_step:
                logger.error(f"Dependency not found: {dep_id}")
                return False

            if dep_step.status != StepStatus.COMPLETED:
                logger.warning(f"Dependency not completed: {dep_id} ({dep_step.status})")
                return False

        return True

    async def _capture_screenshot(self, page) -> bytes:
        """Capture page screenshot."""
        if self.browser_manager:
            return await self.browser_manager.take_screenshot()
        else:
            # Direct page screenshot
            screenshot = await page.screenshot(full_page=False)
            return screenshot

    async def _capture_dom(self, page) -> Optional[Dict]:
        """Capture DOM snapshot (optional)."""
        try:
            # Get basic page info
            title = await page.title()
            url = page.url

            return {
                'title': title,
                'url': url,
            }
        except Exception as e:
            logger.warning(f"Failed to capture DOM: {e}")
            return None

    def get_stats(self) -> Dict:
        """Get orchestrator statistics."""
        return {
            **self.stats,
            'current_plan_id': self.current_plan.plan_id if self.current_plan else None,
            'plans_in_history': len(self.plans_history),
        }
