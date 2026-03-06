"""
Workflow Engine - Chain actions together into multi-step workflows.

Pre-built workflows:
1. SDR Prospecting: Build leads → Research → Qualify → Draft emails
2. Inbox Zero: Triage → Categorize → Draft replies
3. Competitor Analysis: Research competitors → Compare → Report
"""

import asyncio
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from loguru import logger

from .executors.base import ActionResult, ActionStatus
from .executors.sdr import (
    D1_ResearchCompany,
    D2_WriteColdEmail,
    D5_BuildLeadList,
    D7_QualifyLead,
)
from .parallel import BatchProcessor


class WorkflowStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"  # Waiting for user input
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkflowStep:
    """A single step in a workflow."""
    name: str
    capability: str
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)  # Previous step names
    condition: Optional[str] = None  # e.g., "leads.count > 0"
    for_each: Optional[str] = None  # e.g., "leads" - iterate over list
    parallel: bool = False
    requires_approval: bool = False


@dataclass
class WorkflowResult:
    """Result of a workflow execution."""
    status: WorkflowStatus
    workflow_name: str
    steps_completed: int
    total_steps: int
    duration_ms: int
    step_results: Dict[str, ActionResult]
    final_output: Any = None
    error: Optional[str] = None


class Workflow:
    """A defined workflow with steps."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.steps: List[WorkflowStep] = []
        self.context: Dict[str, Any] = {}

    def add_step(self, step: WorkflowStep) -> "Workflow":
        """Add a step to the workflow."""
        self.steps.append(step)
        return self

    def add(
        self,
        name: str,
        capability: str,
        action: str,
        **kwargs
    ) -> "Workflow":
        """Convenience method to add a step."""
        step = WorkflowStep(
            name=name,
            capability=capability,
            action=action,
            **kwargs
        )
        return self.add_step(step)


class WorkflowEngine:
    """Executes workflows step by step."""

    def __init__(self, browser=None):
        self.browser = browser
        self.current_workflow: Optional[Workflow] = None
        self.step_results: Dict[str, ActionResult] = {}
        self.on_step_complete: Optional[Callable] = None
        self.on_approval_needed: Optional[Callable] = None

    async def run(self, workflow: Workflow, initial_params: Dict = None) -> WorkflowResult:
        """Run a complete workflow."""
        start = datetime.now()
        self.current_workflow = workflow
        self.step_results = {}
        workflow.context = initial_params or {}

        steps_completed = 0
        error = None

        try:
            for step in workflow.steps:
                # Check condition
                if step.condition and not self._evaluate_condition(step.condition, workflow.context):
                    logger.info(f"Skipping step {step.name} - condition not met")
                    continue

                # Check approval
                if step.requires_approval:
                    if self.on_approval_needed:
                        approved = await self.on_approval_needed(step, workflow.context)
                        if not approved:
                            return WorkflowResult(
                                status=WorkflowStatus.PAUSED,
                                workflow_name=workflow.name,
                                steps_completed=steps_completed,
                                total_steps=len(workflow.steps),
                                duration_ms=int((datetime.now() - start).total_seconds() * 1000),
                                step_results=self.step_results,
                                error="Waiting for approval"
                            )

                # Execute step
                if step.for_each:
                    result = await self._execute_for_each(step, workflow.context)
                else:
                    result = await self._execute_step(step, workflow.context)

                self.step_results[step.name] = result

                if result.status == ActionStatus.FAILED:
                    error = f"Step {step.name} failed: {result.error}"
                    break

                # Update context with result
                workflow.context[step.name] = result.data
                steps_completed += 1

                if self.on_step_complete:
                    self.on_step_complete(step.name, result)

        except Exception as e:
            error = str(e)
            logger.error(f"Workflow error: {e}")

        return WorkflowResult(
            status=WorkflowStatus.COMPLETED if not error else WorkflowStatus.FAILED,
            workflow_name=workflow.name,
            steps_completed=steps_completed,
            total_steps=len(workflow.steps),
            duration_ms=int((datetime.now() - start).total_seconds() * 1000),
            step_results=self.step_results,
            final_output=workflow.context,
            error=error
        )

    async def _execute_step(self, step: WorkflowStep, context: Dict) -> ActionResult:
        """Execute a single step."""
        # Merge params with context
        params = {**step.params}

        # Replace context references in params
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("$"):
                ref = value[1:]  # Remove $
                if "." in ref:
                    parts = ref.split(".")
                    val = context
                    for part in parts:
                        val = val.get(part, {}) if isinstance(val, dict) else getattr(val, part, None)
                    params[key] = val
                else:
                    params[key] = context.get(ref)

        # Get executor
        executor = self._get_executor(step.capability)
        if not executor:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=step.name,
                capability=step.capability,
                action=step.action,
                error=f"Unknown capability: {step.capability}"
            )

        instance = executor(browser=self.browser, context=context)
        return await instance.execute(params)

    async def _execute_for_each(self, step: WorkflowStep, context: Dict) -> ActionResult:
        """Execute a step for each item in a list."""
        items = context.get(step.for_each, [])

        if not items:
            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=step.name,
                capability=step.capability,
                action=step.action,
                data={"results": [], "count": 0},
                message="No items to process"
            )

        results = []

        if step.parallel:
            # Run in parallel
            tasks = []
            for item in items:
                item_context = {**context, "current_item": item}
                tasks.append(self._execute_step(step, item_context))
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            # Run sequentially
            for item in items:
                item_context = {**context, "current_item": item}
                result = await self._execute_step(step, item_context)
                results.append(result)

        successful = sum(1 for r in results if isinstance(r, ActionResult) and r.status == ActionStatus.SUCCESS)

        return ActionResult(
            status=ActionStatus.SUCCESS if successful > 0 else ActionStatus.FAILED,
            action_id=step.name,
            capability=step.capability,
            action=step.action,
            data={"results": results, "count": len(items), "successful": successful},
            message=f"Processed {successful}/{len(items)} items"
        )

    def _evaluate_condition(self, condition: str, context: Dict) -> bool:
        """Evaluate a simple condition."""
        try:
            # Very simple condition evaluation
            # Format: "variable.path > value" or "variable.path"
            if ">" in condition:
                left, right = condition.split(">")
                left_val = self._get_context_value(left.strip(), context)
                right_val = int(right.strip())
                return left_val > right_val if left_val else False
            elif "<" in condition:
                left, right = condition.split("<")
                left_val = self._get_context_value(left.strip(), context)
                right_val = int(right.strip())
                return left_val < right_val if left_val else False
            else:
                # Just check if truthy
                return bool(self._get_context_value(condition.strip(), context))
        except Exception:
            return False

    def _get_context_value(self, path: str, context: Dict):
        """Get a value from context using dot notation."""
        parts = path.split(".")
        val = context
        for part in parts:
            if isinstance(val, dict):
                val = val.get(part)
            elif isinstance(val, list) and part == "count":
                return len(val)
            else:
                return None
        return val

    def _get_executor(self, capability: str):
        """Get executor class for capability."""
        executors = {
            "D1": D1_ResearchCompany,
            "D2": D2_WriteColdEmail,
            "D5": D5_BuildLeadList,
            "D7": D7_QualifyLead,
        }
        return executors.get(capability)


# ============================================================
# PRE-BUILT WORKFLOWS
# ============================================================

def create_sdr_prospecting_workflow() -> Workflow:
    """
    SDR Prospecting Workflow:
    1. Build lead list from FB Ads
    2. Research each lead's website
    3. Qualify leads
    4. Draft cold emails for HOT leads
    """
    workflow = Workflow(
        name="sdr_prospecting",
        description="Build leads, research, qualify, and draft outreach"
    )

    workflow.add(
        name="build_leads",
        capability="D5",
        action="build_lead_list",
        params={"source": "fb_ads", "count": 20}
    )

    workflow.add(
        name="qualify_leads",
        capability="D7",
        action="qualify_lead",
        for_each="build_leads.leads",
        parallel=True
    )

    workflow.add(
        name="draft_emails",
        capability="D2",
        action="write_cold_email",
        for_each="build_leads.leads",
        condition="build_leads.leads.count > 0",
        params={"company": "$current_item.name"}
    )

    return workflow


def create_company_research_workflow(company: str) -> Workflow:
    """
    Company Deep Research Workflow:
    1. Research company website
    2. Find people on LinkedIn
    3. Qualify as lead
    4. Draft outreach
    """
    workflow = Workflow(
        name="company_research",
        description=f"Deep research on {company}"
    )

    workflow.add(
        name="research",
        capability="D1",
        action="research_company",
        params={"company": company}
    )

    workflow.add(
        name="qualify",
        capability="D7",
        action="qualify_lead",
        params={"lead": "$research"}
    )

    workflow.add(
        name="draft_email",
        capability="D2",
        action="write_cold_email",
        params={
            "company": company,
            "research": "$research"
        }
    )

    return workflow


def create_lead_enrichment_workflow() -> Workflow:
    """
    Lead Enrichment Workflow:
    1. Take existing leads
    2. Research each website
    3. Qualify and score
    4. Sort by score
    """
    workflow = Workflow(
        name="lead_enrichment",
        description="Enrich and qualify leads"
    )

    workflow.add(
        name="research_websites",
        capability="D1",
        action="research_company",
        for_each="leads",
        parallel=True,
        params={"company": "$current_item.name", "website": "$current_item.website"}
    )

    workflow.add(
        name="qualify",
        capability="D7",
        action="qualify_lead",
        for_each="leads",
        parallel=True
    )

    return workflow


# Workflow registry
WORKFLOWS = {
    "sdr_prospecting": create_sdr_prospecting_workflow,
    "company_research": create_company_research_workflow,
    "lead_enrichment": create_lead_enrichment_workflow,
}


def get_workflow(name: str, **kwargs) -> Optional[Workflow]:
    """Get a workflow by name."""
    factory = WORKFLOWS.get(name)
    if factory:
        return factory(**kwargs) if kwargs else factory()
    return None
