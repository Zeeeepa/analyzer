"""
Strategic Planner - MCTS-inspired task decomposition.

This module provides strategic planning for complex multi-step tasks.

Flow:
1. User prompt → StrategicPlanner.plan()
2. Planner creates step-by-step plan (ONE API call)
3. Plan is passed to local LLM for execution
4. If 2x failures → StrategicPlanner.recover() escalates for recovery

Key insight: Planner is the "thinking" brain, local LLM is the "doing" brain.
"""

import asyncio
import json
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from loguru import logger

from .kimi_k2_client import (
    KimiK2Client,
    TaskPlan,
    PlanStep,
    get_kimi_client,
    should_use_kimi_planning,
)
from .llm_fallback_chain import (
    LLMFallbackChain,
    FallbackConfig,
    LLMTier,
    LLMCallResult,
)


# Plan storage
PLANS_DIR = Path("memory/strategic_plans")
PLANS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ExecutionState:
    """Tracks execution progress through a list of plans."""
    all_plans: List[TaskPlan]
    current_plan_index: int = 0
    # The following track state for the *current* plan
    current_step: int = 0
    completed_steps: List[int] = field(default_factory=list)
    failed_steps: List[Tuple[int, str]] = field(default_factory=list)  # (step_num, error)
    step_results: Dict[int, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "running"  # running, completed, failed, recovered, all_plans_completed

    @property
    def current_plan(self) -> Optional[TaskPlan]:
        if 0 <= self.current_plan_index < len(self.all_plans):
            return self.all_plans[self.current_plan_index]
        return None

    @property
    def is_current_plan_complete(self) -> bool:
        if not self.current_plan:
            return True
        return self.current_step >= len(self.current_plan.steps)

    @property
    def is_overall_task_complete(self) -> bool:
        return self.is_current_plan_complete and (self.current_plan_index >= len(self.all_plans) - 1)

    @property
    def consecutive_failures(self) -> int:
        """Count consecutive failures for the current step."""
        return sum(1 for step_num, _ in self.failed_steps if step_num == self.current_step)

    def next_step(self) -> Optional[PlanStep]:
        """Get the next step to execute from the current plan."""
        if self.is_current_plan_complete:
            return None
        return self.current_plan.steps[self.current_step]

    def peek_next_step(self) -> Optional[PlanStep]:
        """Peek at the next step without advancing (for auto-chaining)."""
        if not self.current_plan:
            return None
        next_idx = self.current_step + 1
        if next_idx >= len(self.current_plan.steps):
            return None
        return self.current_plan.steps[next_idx]

    def skip_next_step(self) -> None:
        """Skip the next step (after auto-handling it)."""
        if not self.current_plan:
            return
        if self.current_step < len(self.current_plan.steps):
            self.current_step += 1

    def mark_success(self, result: Any = None):
        """Mark current step as successful."""
        self.completed_steps.append(self.current_step)
        self.step_results[self.current_step] = result
        self.current_step += 1

    def mark_failure(self, error: str):
        """Mark current step as failed."""
        self.failed_steps.append((self.current_step, error))

    def advance_to_next_plan(self) -> bool:
        """Move to the next plan in the list. Returns True if there's a next plan."""
        if self.current_plan_index < len(self.all_plans) - 1:
            self.current_plan_index += 1
            # Reset step-specific trackers for the new plan
            self.current_step = 0
            self.completed_steps = []
            self.failed_steps = []
            self.step_results = {}
            logger.info(f"Advanced to next plan: {self.current_plan_index + 1}/{len(self.all_plans)}")
            return True
        return False

    def get_context_for_llm(self) -> str:
        """Get execution context for LLM prompting."""
        if not self.current_plan:
            return "No active plan."

        lines = [
            f"Overall task: {self.all_plans[0].original_prompt}",
            f"Executing plan {self.current_plan_index + 1}/{len(self.all_plans)}: {self.current_plan.summary}",
        ]
        lines.append(f"Progress on current plan: {len(self.completed_steps)}/{len(self.current_plan.steps)} steps")

        if self.step_results:
            lines.append("\nCompleted steps:")
            # Display last few completed steps for context
            for step_num in sorted(self.completed_steps, reverse=True)[:3]:
                step = self.current_plan.steps[step_num]
                result = self.step_results.get(step_num, "OK")
                result_str = str(result)[:100] if result else "OK"
                lines.append(f"  {step_num + 1}. {step.action} -> {result_str}")

        if self.current_step < len(self.current_plan.steps):
            next_step = self.current_plan.steps[self.current_step]
            lines.append(f"\nNext: {next_step.action}")
            lines.append(f"Tool: {next_step.tool}")
            if next_step.arguments:
                lines.append(f"Args: {json.dumps(next_step.arguments)}")

        return "\n".join(lines)


class StrategicPlanner:
    """
    Strategic planning layer that sits between user prompts and execution.

    Uses strategic planner for thinking, local LLM for tactical execution.
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize the strategic planner.

        Args:
            config: Configuration dict with 'strategic_planner' section
        """
        self.config = config or {}
        self.planner_client = get_kimi_client(self.config)

        # Track active executions
        self.active_executions: Dict[str, ExecutionState] = {}

        # Recovery threshold
        self.recovery_threshold = self.config.get("strategic_planner", {}).get("recovery_threshold", 2)

        # Initialize fallback chain
        self.fallback_chain = self._init_fallback_chain()

        logger.info(
            f"Strategic planner initialized (recovery_threshold={self.recovery_threshold}, "
            f"fallback_enabled={self.fallback_chain is not None})"
        )

    def _init_fallback_chain(self) -> Optional[LLMFallbackChain]:
        """Initialize LLM fallback chain for cost optimization."""
        try:
            # Get fallback config from strategic_planner section
            sp_config = self.config.get("strategic_planner", {})

            # Primary LLM is always 0000/ui-tars-1.5-7b:latest - best for tool calling
            # Kimi K2 is used as fallback after failures
            primary_llm_str = sp_config.get("primary_llm", "qwen").lower()
            if primary_llm_str == "kimi":
                primary_llm = LLMTier.KIMI_K2
            else:
                primary_llm = LLMTier.QWEN3_8B

            # Get LLM endpoints from config
            llm_config = self.config.get("llm", {})

            # Get proper config from config_loader for correct remote/local handling
            # This ensures model names are mapped for local Ollama and base_url is correct
            try:
                from .config_loader import load_config as loader_load_config
                loaded_config = loader_load_config()
                loaded_llm = loaded_config.get("llm", {})
                base_url = loaded_llm.get("base_url", "https://eversale.io/api/llm")
                main_model = loaded_llm.get("main_model", "0000/ui-tars-1.5-7b:latest")
                vision_model = loaded_llm.get("vision_model", "moondream:latest")
            except ImportError:
                base_url = llm_config.get("base_url", "https://eversale.io/api/llm")
                main_model = llm_config.get("main_model", "0000/ui-tars-1.5-7b:latest")
                vision_model = llm_config.get("vision_model", "moondream:latest")

            fallback_config = FallbackConfig(
                primary_llm=primary_llm,
                kimi_timeout=sp_config.get("kimi_timeout_seconds", 120.0),
                qwen_timeout=sp_config.get("qwen_timeout_seconds", 120.0),
                max_retries_per_tier=sp_config.get("max_fallback_retries", 3),
                max_total_retries=sp_config.get("max_total_retries", 5),
                use_qwen_for_minor_replans=True,
                escalate_to_kimi_after_failures=sp_config.get("escalate_after_failures", 3),
                main_model=main_model,
                vision_model=vision_model,
                ollama_url=base_url,
            )

            chain = LLMFallbackChain(
                config=fallback_config,
                kimi_client=self.planner_client
            )

            logger.info(f"Fallback chain initialized: primary={primary_llm.name}")
            return chain

        except Exception as e:
            logger.warning(f"Failed to initialize fallback chain: {e}, using Kimi only")
            return None

    async def should_plan(self, prompt: str) -> bool:
        """
        Decide if this task needs strategic planning.

        Simple tasks skip planning and go straight to execution.
        """
        if not self.planner_client.is_available():
            return False

        return should_use_kimi_planning(prompt, self.config)

    async def _plan_with_fallback(
        self,
        prompt: str,
        available_tools: List[str],
        context: str = "",
        is_minor_replan: bool = False,
    ) -> Optional[List[TaskPlan]]: # Changed return type to List[TaskPlan]
        """
        Create a plan using fallback chain (Kimi → Llama → Ollama).

        Args:
            prompt: User's task request
            available_tools: List of available tool names
            context: Additional context
            is_minor_replan: True if this is a minor adjustment (uses cheaper model)

        Returns:
            List[TaskPlan] or None if all tiers fail
        """
        # If no fallback chain, use original Kimi-only approach (which returns single TaskPlan)
        # Note: This path needs to be updated if the KimiK2Client.plan_task is also updated to return List[TaskPlan]
        if not self.fallback_chain:
            single_plan = await self.planner_client.plan_task(prompt, available_tools, context)
            return [single_plan] if single_plan else None

        # Build planning prompts
        system_prompt = """You are a strategic task planner for an AI browser automation agent.

JOB: Create PRECISE step-by-step execution plans for web automation tasks.
If the user's request contains multiple distinct goals (e.g., "Find X on Site A and Y on Site B"), break it down into a list of independent plans. Each plan should be for a single, focused goal.

AVAILABLE TOOLS:
{tools}

PLANNING RULES:
1. Think step-by-step: reason about tool relevance before selecting (ReAct pattern)
2. Each step = ONE tool call with CONCRETE arguments - NEVER use placeholders like {{variable}} or {{company_name}}
3. STRONGLY PREFER combined tools that do extract+save in one step (reduces complexity)
4. For data pipelines: use tools that extract AND save directly rather than separate extract then save
5. Include verification steps to check results before proceeding
6. Anticipate blockers: login walls, CAPTCHAs, rate limits, rate limiting, missing data
7. Plan fallbacks for likely failure points
8. For multi-part user requests, create multiple individual plans. Each plan should be self-contained and executable independently, focusing on one specific objective (e.g., finding information on one site, then finding information on another site).

CRITICAL - TOOL SELECTION (in order of preference):
1. playwright_extract_to_csv - BEST for extracting structured data to CSV (combines extract+save)
   Arguments: {{"schema": {{"name": "string", "url": "string"}}, "csv_path": "/home/user/output.csv"}}
2. playwright_batch_extract - For visiting multiple URLs and extracting contacts
   Arguments: {{"urls": ["https://site1.com", "https://site2.com"], "csv_path": "/path/to/out.csv"}}
3. playwright_navigate - Go to URL first
   Arguments: {{"url": "https://example.com"}}
4. playwright_fill + playwright_click - For forms and search
5. playwright_extract_entities - For structured data when not saving to CSV directly
   Arguments: {{"entity_types": ["company", "email", "phone"], "schema": {{"field": "type"}}}}
6. playwright_screenshot - For visual verification
7. playwright_get_markdown - For page content as text

IMPORTANT: Steps are executed INDEPENDENTLY - data from one step is NOT automatically available to the next.
Therefore:
- Use combined tools (extract_to_csv) instead of extract → save sequences
- Include full URLs and paths in each step, not references to previous results
- If processing multiple items, use batch tools or plan explicit iteration

OUTPUT FORMAT (JSON only, no markdown):
{{
    "plans": [
        {{
            "summary": "One-line task description for this specific plan",
            "steps": [
                {{
                    "step_number": 1,
                    "action": "Clear description of what this step achieves",
                    "tool": "exact_tool_name",
                    "arguments": {{"key": "specific_value_not_placeholder"}},
                    "expected_result": "Concrete success criteria",
                    "fallback": "Alternative approach if this fails"
                }}
            ],
            "estimated_iterations": 5,
            "potential_blockers": ["login required", "rate limiting", "CAPTCHA"],
            "success_criteria": "Specific measurable outcome (e.g., 'extracted 10+ contacts')"
        }}
    ]
}}"""

        # Get actual home directory for path expansion
        from pathlib import Path
        home_dir = str(Path.home())

        user_prompt = f"""TASK: {prompt}

ENVIRONMENT:
- Home directory (~): {home_dir}
- Use full paths, not ~. Example: {home_dir}/lead_research/output.csv

{f"CONTEXT: {context}" if context else ""}

Create an execution plan. Structure your response as JSON only."""

        # Call with fallback
        result = await self.fallback_chain.call_with_fallback(
            system_prompt=system_prompt.format(tools=", ".join(available_tools)),
            user_prompt=user_prompt,
            is_minor_replan=is_minor_replan,
            temperature=0.3,
            max_tokens=12288,
        )

        if not result.success:
            logger.error(f"All LLM tiers failed for planning: {result.error}")
            return None

        # Log which tier was used
        logger.info(f"Plan generated by: {result.tier_used.name} ({result.latency_ms}ms)")

        # Parse the response (same logic as original plan_task)
        content = result.content

        # Extract JSON from response (handle markdown code blocks)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        content = content.strip()

        # Try to fix truncated JSON
        try:
            parsed_data = json.loads(content)
        except json.JSONDecodeError:
            # Attempt to repair truncated JSON
            fixed = content

            # Count unclosed brackets
            open_braces = fixed.count('{') - fixed.count('}')
            open_brackets = fixed.count('[') - fixed.count(']')

            # If we're in the middle of a string, close it
            if fixed.count('"') % 2 == 1:
                fixed = fixed.rsplit('"', 1)[0] + '"'

            # Close any open arrays/objects
            if open_brackets > 0:
                fixed += ']' * open_brackets
            if open_braces > 0:
                fixed += '}' * open_braces

            try:
                parsed_data = json.loads(fixed)
                logger.warning("Repaired truncated JSON response from LLM")
            except json.JSONDecodeError as e:
                logger.error(f"Could not repair JSON: {e}")
                logger.debug(f"Raw content: {content[:500]}...")
                return None

        # --- MODIFIED: Extract a list of TaskPlan objects ---
        all_plans_data = parsed_data.get("plans", [])
        if not all_plans_data:
            logger.warning("No plans found in LLM response, trying to parse as single plan.")
            # Fallback for single plan format
            if parsed_data.get("steps"):
                all_plans_data = [parsed_data]
            else:
                return None

        task_plans: List[TaskPlan] = []
        for plan_data in all_plans_data:
            task_id = hashlib.md5(f"{prompt}{datetime.now().isoformat()}".encode()).hexdigest()[:12]

            steps = []
            for i, s in enumerate(plan_data.get("steps", [])):
                try:
                    step = PlanStep(
                        step_number=s.get("step_number", i + 1),
                        action=s.get("action", f"Step {i+1}"),
                        tool=s.get("tool", "playwright_navigate"),
                        arguments=s.get("arguments", s.get("args", {})),
                        expected_result=s.get("expected_result", s.get("expected", "Success")),
                        fallback=s.get("fallback")
                    )
                    steps.append(step)
                except Exception as step_error:
                    logger.warning(f"Error parsing step {i}: {step_error}, raw: {s}")
                    continue

            if not steps:
                logger.warning("No valid steps parsed for a plan in LLM response")
                continue

            plan = TaskPlan(
                task_id=task_id, # Re-using original task_id concept, but it's for individual plan now
                original_prompt=prompt, # Original overall prompt
                summary=plan_data.get("summary", "Execute subtask"),
                steps=steps,
                estimated_iterations=plan_data.get("estimated_iterations", len(steps)),
                potential_blockers=plan_data.get("potential_blockers", []),
                success_criteria=plan_data.get("success_criteria", "Subtask completed successfully")
            )
            task_plans.append(plan)

        if not task_plans:
            logger.warning("No valid TaskPlans generated from LLM response.")
            return None

        logger.info(f"Strategic planning complete. Generated {len(task_plans)} sub-plans.")
        return task_plans

    async def plan(
        self,
        prompt: str,
        available_tools: List[str],
        context: str = "",
    ) -> Optional[ExecutionState]:
        """
        Create a strategic plan for a task.

        Args:
            prompt: User's task request
            available_tools: List of available tool names
            context: Additional context

        Returns:
            ExecutionState ready for execution, or None if planning skipped/failed
        """
        # Reset per-task counter
        self.planner_client.reset_task_counter()

        # Check if planning is warranted
        if not await self.should_plan(prompt):
            logger.info(f"Skipping strategic planning for simple task")
            return None

        logger.info(f"Creating strategic plan...")

        # Get list of plans from planner (with fallback chain if available)
        all_plans = await self._plan_with_fallback(prompt, available_tools, context)

        if not all_plans:
            logger.warning("Strategic planning failed, falling back to direct execution")
            return None

        # Create execution state with all plans
        # Use the task_id of the *first* plan as the overall task_id for tracking
        overall_task_id = all_plans[0].task_id
        state = ExecutionState(all_plans=all_plans)
        self.active_executions[overall_task_id] = state

        # Save plans for debugging (each plan gets its own file)
        for plan in all_plans:
            self._save_plan(plan)

        logger.info(
            f"Overall strategic plan created for prompt '{prompt}'. "
            f"Decomposed into {len(all_plans)} sub-plans."
        )
        for i, plan in enumerate(all_plans):
            logger.info(
                f"  Sub-plan {i+1}: {plan.summary}\n"
                f"    Steps: {len(plan.steps)}\n"
                f"    Blockers: {plan.potential_blockers}\n"
                f"    Success: {plan.success_criteria}"
            )

        return state

    async def get_next_action(
        self,
        state: ExecutionState,
    ) -> Optional[Dict[str, Any]]:
        """
        Get the next action to execute from the current plan.
        If current plan is complete, advances to the next plan.

        Returns tool call dict ready for MCP execution.
        """
        if state.is_current_plan_complete:
            if not state.advance_to_next_plan():
                state.status = "all_plans_completed"
                return None # All plans are complete

        step = state.next_step()
        if not step:
            # This should ideally not happen if is_current_plan_complete check is correct
            return None

        return {
            "tool": step.tool,
            "arguments": step.arguments,
            "expected_result": step.expected_result,
            "step_number": step.step_number,
            "fallback": step.fallback,
            "plan_summary": state.current_plan.summary # Added for context in AgenticBrowser
        }

    async def report_result(
        self,
        state: ExecutionState,
        success: bool,
        result: Any = None,
        error: str = "",
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Report execution result and get guidance.

        Returns:
            Tuple of (status, next_action)
            - status: "continue", "complete", "recover", "abort", "all_plans_completed"
            - next_action: Next tool call if status is "continue" or "recover"
        """
        if not state.current_plan:
            logger.error("report_result called with no active plan.")
            return "abort", None

        if success:
            state.mark_success(result)

            if state.is_current_plan_complete:
                logger.info(f"Current sub-plan '{state.current_plan.summary}' completed.")
                if state.advance_to_next_plan():
                    # Successfully advanced to next plan, get its first step
                    return "continue", await self.get_next_action(state)
                else:
                    state.status = "all_plans_completed"
                    return "all_plans_completed", None # All plans are complete

            return "continue", await self.get_next_action(state)

        else: # Execution failed
            state.mark_failure(error)

            # Hard limit: abort if total failures exceed 10 (prevents infinite loops)
            if len(state.failed_steps) >= 10:
                logger.error(f"Hit hard limit of 10 total failures on current plan, aborting")
                state.status = "failed"
                return "abort", None

            # Check if we need recovery for the current plan
            if state.consecutive_failures >= self.recovery_threshold:
                logger.warning(f"Hit {state.consecutive_failures} consecutive failures on current plan, escalating for recovery")

                recovery = await self._attempt_recovery(state, error)
                if recovery:
                    state.status = "recovered" # Recovery was attempted for this plan
                    return "recover", recovery

                state.status = "failed" # Recovery failed, or not possible
                return "abort", None

            # Try fallback from current plan's step
            step = state.current_plan.steps[state.current_step]
            if step.fallback:
                logger.info(f"Using planned fallback: {step.fallback}")
                # For now, we don't change the current_step for fallback, it's just advisory.
                # The local LLM is expected to interpret and retry with a new approach based on the fallback.
                return "continue", await self.get_next_action(state)

            # Retry same step (local 7B will try different approach)
            return "continue", await self.get_next_action(state)

    async def _attempt_recovery(
        self,
        state: ExecutionState,
        last_error: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt recovery using strategic planner for the current plan.

        Returns recovery action if available.
        """
        if not self.planner_client.can_call():
            logger.warning("Cannot call planner for recovery - limit reached")
            return None
        if not state.current_plan:
            logger.error("_attempt_recovery called with no active plan.")
            return None

        # Gather failed attempts for the CURRENT plan
        failed_attempts = [
            {
                "step": state.current_plan.steps[step_num].action,
                "tool": state.current_plan.steps[step_num].tool,
                "error": error
            }
            for step_num, error in state.failed_steps[-3:]  # Last 3 failures on current plan
        ]

        # Get current state description
        current_state = state.get_context_for_llm()

        # Get available tools (from original plan)
        available_tools = list(set(s.tool for s in state.current_plan.steps))

        # Call planner for recovery
        recovery = await self.planner_client.recover(
            original_prompt=state.current_plan.original_prompt, # Use current plan's prompt or overall
            current_state=current_state,
            error=last_error,
            failed_attempts=failed_attempts,
            available_tools=available_tools,
        )

        if not recovery:
            return None

        # Check if we should abort this particular plan
        if recovery.get("should_abort", False):
            logger.warning(f"Planner recommends aborting current plan: {recovery.get('abort_reason', 'unknown')}")
            # If current plan is aborted, try to advance to the next
            if state.advance_to_next_plan():
                return await self.get_next_action(state) # Return first step of next plan
            else:
                state.status = "failed" # No more plans, overall task failed
                return None

        # Get first recovery step
        recovery_steps = recovery.get("recovery_steps", [])
        if not recovery_steps:
            return None

        first_step = recovery_steps[0]
        return {
            "tool": first_step["tool"],
            "arguments": first_step.get("arguments", {}),
            "expected_result": first_step.get("why", "Recovery attempt"),
            "is_recovery": True,
            "diagnosis": recovery.get("diagnosis", ""),
            "new_approach": recovery.get("new_approach", ""),
        }

    def _save_plan(self, plan: TaskPlan):
        """Save plan to disk for debugging."""
        path = PLANS_DIR / f"plan_{plan.task_id}.json"
        data = {
            "task_id": plan.task_id,
            "original_prompt": plan.original_prompt,
            "summary": plan.summary,
            "steps": [
                {
                    "step_number": s.step_number,
                    "action": s.action,
                    "tool": s.tool,
                    "arguments": s.arguments,
                    "expected_result": s.expected_result,
                    "fallback": s.fallback,
                }
                for s in plan.steps
            ],
            "estimated_iterations": plan.estimated_iterations,
            "potential_blockers": plan.potential_blockers,
            "success_criteria": plan.success_criteria,
            "created_at": plan.created_at,
        }
        path.write_text(json.dumps(data, indent=2))

    def get_execution_state(self, task_id: str) -> Optional[ExecutionState]:
        """Get execution state by task ID."""
        # Note: task_id here refers to the overall task_id which is the first plan's task_id
        return self.active_executions.get(task_id)

    def cleanup(self, task_id: str):
        """Remove completed execution from memory."""
        if task_id in self.active_executions:
            del self.active_executions[task_id]

    def get_cost_report(self) -> Dict[str, Any]:
        """
        Get cost tracking report from fallback chain.

        Returns:
            Dict with cost tracking info, including:
            - calls: breakdown by tier
            - kimi_cost_usd: actual Kimi costs
            - estimated_savings_usd: savings from using free models
            - free_call_percentage: % of calls that were free
        """
        if not self.fallback_chain:
            return {
                "fallback_enabled": False,
                "message": "Fallback chain not available"
            }

        report = self.fallback_chain.get_cost_report()
        report["fallback_enabled"] = True
        return report

    async def close(self):
        """Close fallback chain clients."""
        if self.fallback_chain:
            await self.fallback_chain.close()


def create_plan_guided_prompt(
    state: ExecutionState,
    page_content: str = "",
) -> str:
    """
    Create a prompt for the local 7B model that includes plan guidance.

    This is the key integration point - we tell the local model
    what step to execute and what success looks like.
    """
    step = state.next_step()
    if not step:
        return "Task complete. Summarize results."

    lines = [
        "=== STRATEGIC PLAN GUIDANCE ===",
        f"Overall task: {state.all_plans[0].original_prompt}",
        f"Current sub-plan ({state.current_plan_index + 1}/{len(state.all_plans)}): {state.current_plan.summary}",
        f"Progress on current sub-plan: {len(state.completed_steps)}/{len(state.current_plan.steps)} steps complete",
        "",
        f"CURRENT STEP ({step.step_number}/{len(state.current_plan.steps)}):",
        f"  Action: {step.action}",
        f"  Tool: {step.tool}",
        f"  Arguments: {json.dumps(step.arguments)}",
        f"  Expected: {step.expected_result}",
    ]

    if step.fallback:
        lines.append(f"  Fallback: {step.fallback}")

    if state.current_plan.potential_blockers:
        lines.append(f"\nWatch for: {', '.join(state.current_plan.potential_blockers)}")

    if page_content:
        lines.append(f"\n=== CURRENT PAGE ===\n{page_content[:2000]}")

    lines.append("\nExecute this step using the specified tool.")

    return "\n".join(lines)


# Singleton planner
_planner: Optional[StrategicPlanner] = None


def get_strategic_planner(config: Optional[Dict] = None) -> StrategicPlanner:
    """Get or create the strategic planner singleton."""
    global _planner
    if _planner is None:
        _planner = StrategicPlanner(config)
    return _planner
