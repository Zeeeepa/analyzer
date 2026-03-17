"""
Simple Workflow Executor - Reliable, Deterministic Task Execution

This provides a SIMPLE, RELIABLE way to execute common workflows without
complex cascading recovery or AI dependency.

Philosophy:
- NO complex recovery - if step fails, return error or skip if optional
- NO AI dependency - purely deterministic
- NO cascading logic - linear execution
- CLEAR status - show each step as it runs
- FAST timeout - 10s per step max

Use this when you want:
- Predictable, repeatable workflows
- Fast execution without AI overhead
- Clear success/failure states
- Simple debugging

Example:
    executor = SimpleWorkflowExecutor(mcp_tools)

    # Pre-built workflow
    result = await executor.execute(GOOGLE_SEARCH, {"query": "AI agents"})

    # Custom workflow
    workflow = SimpleWorkflow(
        name="login_flow",
        steps=[
            WorkflowStep("navigate", "https://example.com/login"),
            WorkflowStep("type", "input[name='email']", "user@example.com"),
            WorkflowStep("type", "input[name='password']", "secret123"),
            WorkflowStep("click", "button[type='submit']"),
            WorkflowStep("wait", value="3"),
        ]
    )
    result = await executor.execute(workflow)
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from loguru import logger
from rich.console import Console

console = Console()


@dataclass
class WorkflowStep:
    """
    A single step in a workflow.

    Actions:
        - navigate: Go to URL (target = URL)
        - click: Click element (target = selector)
        - type: Type text (target = selector, value = text)
        - wait: Wait for time (value = seconds)
        - extract: Get page content
        - screenshot: Take screenshot
        - press: Press key (value = key name)
        - scroll: Scroll page (value = "up"/"down"/"top"/"bottom")
    """
    action: str
    target: Optional[str] = None
    value: Optional[str] = None
    required: bool = True
    timeout: int = 10

    def __repr__(self) -> str:
        parts = [f"action={self.action}"]
        if self.target:
            parts.append(f"target={self.target[:30]}...")
        if self.value:
            parts.append(f"value={self.value[:20]}...")
        return f"WorkflowStep({', '.join(parts)})"


@dataclass
class StepResult:
    """Result from executing a single step."""
    step_number: int
    step: WorkflowStep
    success: bool
    message: str
    time_ms: int
    screenshot_b64: Optional[str] = None
    extracted_data: Optional[str] = None
    error: Optional[str] = None


@dataclass
class WorkflowResult:
    """Result from executing entire workflow."""
    success: bool
    workflow_name: str
    step_results: List[StepResult]
    failed_step: Optional[int] = None
    error: Optional[str] = None
    extracted_data: Optional[str] = None
    total_time_ms: int = 0
    completed_steps: int = 0
    total_steps: int = 0


@dataclass
class SimpleWorkflow:
    """
    A simple workflow - just a list of steps to execute in order.

    No complex logic, no AI, no recovery - just do these things.
    """
    name: str
    steps: List[WorkflowStep]
    timeout_per_step: int = 10
    description: str = ""

    def __repr__(self) -> str:
        return f"SimpleWorkflow(name={self.name}, steps={len(self.steps)})"


class SimpleWorkflowExecutor:
    """
    Execute workflows step by step - simple and reliable.

    No AI, no complex recovery, no cascading logic.
    Just execute the steps and report what happened.

    If a required step fails, stop and return error.
    If an optional step fails, log it and continue.
    """

    def __init__(self, mcp_tools):
        """
        Initialize with MCP tools instance.

        Args:
            mcp_tools: Instance of MCPTools for browser automation
        """
        self.tools = mcp_tools

    async def execute(
        self,
        workflow: SimpleWorkflow,
        variables: Optional[Dict[str, str]] = None
    ) -> WorkflowResult:
        """
        Execute workflow step by step.

        Args:
            workflow: The workflow to execute
            variables: Optional dict to replace {placeholders} in steps
                      e.g., {"query": "AI agents"} replaces {query}

        Returns:
            WorkflowResult with success status and all step results
        """
        start_time = time.time()
        results = []
        variables = variables or {}

        console.print(f"\n[bold cyan]Starting workflow: {workflow.name}[/bold cyan]")
        if workflow.description:
            console.print(f"[dim]{workflow.description}[/dim]")
        console.print(f"[dim]Total steps: {len(workflow.steps)}[/dim]\n")

        for i, step in enumerate(workflow.steps):
            step_num = i + 1

            # Apply variable substitution
            step = self._apply_variables(step, variables)

            console.print(f"[cyan]Step {step_num}/{len(workflow.steps)}:[/cyan] {step.action}", end=" ")
            if step.target:
                console.print(f"[dim]({step.target[:50]})[/dim]", end="")
            console.print()

            # Execute step
            step_start = time.time()
            result = await self._execute_step(step, step_num)
            step_time = int((time.time() - step_start) * 1000)
            result.time_ms = step_time

            results.append(result)

            # Check result
            if not result.success:
                if step.required:
                    # Required step failed - abort workflow
                    console.print(f"[red]Step failed (required): {result.error}[/red]")

                    total_time = int((time.time() - start_time) * 1000)
                    return WorkflowResult(
                        success=False,
                        workflow_name=workflow.name,
                        step_results=results,
                        failed_step=step_num,
                        error=result.error,
                        total_time_ms=total_time,
                        completed_steps=step_num - 1,
                        total_steps=len(workflow.steps)
                    )
                else:
                    # Optional step failed - continue
                    console.print(f"[yellow]Step failed (optional), continuing: {result.error}[/yellow]")
            else:
                console.print(f"[green]Success[/green] [dim]({step_time}ms)[/dim]")

        # All steps completed
        total_time = int((time.time() - start_time) * 1000)

        # Extract final data if last step was extract
        final_data = None
        if results and results[-1].extracted_data:
            final_data = results[-1].extracted_data

        console.print(f"\n[bold green]Workflow completed successfully![/bold green]")
        console.print(f"[dim]Total time: {total_time}ms[/dim]\n")

        return WorkflowResult(
            success=True,
            workflow_name=workflow.name,
            step_results=results,
            extracted_data=final_data,
            total_time_ms=total_time,
            completed_steps=len(workflow.steps),
            total_steps=len(workflow.steps)
        )

    def _apply_variables(self, step: WorkflowStep, variables: Dict[str, str]) -> WorkflowStep:
        """Replace {placeholders} in step with actual values."""
        import copy
        step = copy.copy(step)

        if step.target:
            for key, value in variables.items():
                step.target = step.target.replace(f"{{{key}}}", value)

        if step.value:
            for key, value in variables.items():
                step.value = step.value.replace(f"{{{key}}}", value)

        return step

    async def _execute_step(self, step: WorkflowStep, step_num: int) -> StepResult:
        """
        Execute a single workflow step.

        Maps step actions to MCP tool calls.
        """
        try:
            if step.action == "navigate":
                result = await self.tools.navigate(step.target)
                return StepResult(
                    step_number=step_num,
                    step=step,
                    success=result.success,
                    message=result.message,
                    time_ms=0,
                    screenshot_b64=result.screenshot_b64,
                    error=None if result.success else result.message
                )

            elif step.action == "click":
                result = await self.tools.click(step.target)
                return StepResult(
                    step_number=step_num,
                    step=step,
                    success=result.success,
                    message=result.message,
                    time_ms=0,
                    screenshot_b64=result.screenshot_b64,
                    error=None if result.success else result.message
                )

            elif step.action == "type":
                result = await self.tools.fill(step.target, step.value)
                return StepResult(
                    step_number=step_num,
                    step=step,
                    success=result.success,
                    message=result.message,
                    time_ms=0,
                    screenshot_b64=result.screenshot_b64,
                    error=None if result.success else result.message
                )

            elif step.action == "wait":
                seconds = float(step.value or "2")
                await asyncio.sleep(seconds)
                # Take screenshot after wait
                result = await self.tools.screenshot()
                return StepResult(
                    step_number=step_num,
                    step=step,
                    success=True,
                    message=f"Waited {seconds}s",
                    time_ms=0,
                    screenshot_b64=result.screenshot_b64
                )

            elif step.action == "extract":
                result = await self.tools.extract_content()
                return StepResult(
                    step_number=step_num,
                    step=step,
                    success=result.success,
                    message=result.message,
                    time_ms=0,
                    screenshot_b64=result.screenshot_b64,
                    extracted_data=result.data,
                    error=None if result.success else result.message
                )

            elif step.action == "screenshot":
                result = await self.tools.screenshot()
                return StepResult(
                    step_number=step_num,
                    step=step,
                    success=result.success,
                    message=result.message,
                    time_ms=0,
                    screenshot_b64=result.screenshot_b64,
                    error=None if result.success else result.message
                )

            elif step.action == "press":
                result = await self.tools.press_key(step.value or "Enter")
                return StepResult(
                    step_number=step_num,
                    step=step,
                    success=result.success,
                    message=result.message,
                    time_ms=0,
                    screenshot_b64=result.screenshot_b64,
                    error=None if result.success else result.message
                )

            elif step.action == "scroll":
                direction = step.value or "down"
                result = await self.tools.scroll(direction)
                return StepResult(
                    step_number=step_num,
                    step=step,
                    success=result.success,
                    message=result.message,
                    time_ms=0,
                    screenshot_b64=result.screenshot_b64,
                    error=None if result.success else result.message
                )

            else:
                return StepResult(
                    step_number=step_num,
                    step=step,
                    success=False,
                    message=f"Unknown action: {step.action}",
                    time_ms=0,
                    error=f"Unknown action: {step.action}"
                )

        except Exception as e:
            logger.error(f"Step {step_num} failed: {e}")
            return StepResult(
                step_number=step_num,
                step=step,
                success=False,
                message=f"Exception: {str(e)}",
                time_ms=0,
                error=str(e)
            )


# =============================================================================
# PRE-BUILT WORKFLOWS - Common patterns ready to use
# =============================================================================

# Google Search
GOOGLE_SEARCH = SimpleWorkflow(
    name="google_search",
    description="Search Google for a query",
    steps=[
        WorkflowStep("navigate", "https://www.google.com"),
        WorkflowStep("type", "textarea[name='q']", "{query}"),
        WorkflowStep("press", value="Enter"),
        WorkflowStep("wait", value="2"),
        WorkflowStep("extract"),
    ]
)

# Simple Navigate and Extract
SIMPLE_NAVIGATE = SimpleWorkflow(
    name="simple_navigate",
    description="Navigate to URL and extract content",
    steps=[
        WorkflowStep("navigate", "{url}"),
        WorkflowStep("wait", value="2"),
        WorkflowStep("extract"),
    ]
)

# LinkedIn Login (example of multi-step form)
LINKEDIN_LOGIN = SimpleWorkflow(
    name="linkedin_login",
    description="Log in to LinkedIn",
    steps=[
        WorkflowStep("navigate", "https://www.linkedin.com/login"),
        WorkflowStep("type", "input[name='session_key']", "{email}"),
        WorkflowStep("type", "input[name='session_password']", "{password}"),
        WorkflowStep("click", "button[type='submit']"),
        WorkflowStep("wait", value="3"),
        WorkflowStep("screenshot"),
    ]
)

# Amazon Product Search
AMAZON_SEARCH = SimpleWorkflow(
    name="amazon_search",
    description="Search Amazon for products",
    steps=[
        WorkflowStep("navigate", "https://www.amazon.com"),
        WorkflowStep("type", "input[name='field-keywords']", "{query}"),
        WorkflowStep("press", value="Enter"),
        WorkflowStep("wait", value="3"),
        WorkflowStep("extract"),
    ]
)

# Twitter/X Post
TWITTER_POST = SimpleWorkflow(
    name="twitter_post",
    description="Post a tweet on Twitter/X",
    steps=[
        WorkflowStep("navigate", "https://twitter.com/home"),
        WorkflowStep("wait", value="2"),
        WorkflowStep("click", "a[href='/compose/tweet']", required=False),  # New compose button
        WorkflowStep("type", "div[role='textbox']", "{tweet_text}"),
        WorkflowStep("wait", value="1"),
        WorkflowStep("click", "div[data-testid='tweetButtonInline']"),
        WorkflowStep("wait", value="2"),
        WorkflowStep("screenshot"),
    ]
)

# GitHub Repository Browse
GITHUB_REPO_BROWSE = SimpleWorkflow(
    name="github_repo_browse",
    description="Browse GitHub repository",
    steps=[
        WorkflowStep("navigate", "https://github.com/{owner}/{repo}"),
        WorkflowStep("wait", value="2"),
        WorkflowStep("extract"),
    ]
)

# Simple Form Fill (generic)
SIMPLE_FORM_FILL = SimpleWorkflow(
    name="simple_form_fill",
    description="Fill a simple form with name and email",
    steps=[
        WorkflowStep("navigate", "{form_url}"),
        WorkflowStep("wait", value="2"),
        WorkflowStep("type", "input[name='name']", "{name}"),
        WorkflowStep("type", "input[name='email']", "{email}"),
        WorkflowStep("click", "button[type='submit']"),
        WorkflowStep("wait", value="2"),
        WorkflowStep("screenshot"),
    ]
)

# YouTube Search
YOUTUBE_SEARCH = SimpleWorkflow(
    name="youtube_search",
    description="Search YouTube for videos",
    steps=[
        WorkflowStep("navigate", "https://www.youtube.com"),
        WorkflowStep("wait", value="2"),
        WorkflowStep("type", "input[name='search_query']", "{query}"),
        WorkflowStep("press", value="Enter"),
        WorkflowStep("wait", value="3"),
        WorkflowStep("extract"),
    ]
)

# Reddit Subreddit Browse
REDDIT_BROWSE = SimpleWorkflow(
    name="reddit_browse",
    description="Browse a subreddit",
    steps=[
        WorkflowStep("navigate", "https://www.reddit.com/r/{subreddit}"),
        WorkflowStep("wait", value="3"),
        WorkflowStep("extract"),
    ]
)

# HackerNews Browse
HACKERNEWS_BROWSE = SimpleWorkflow(
    name="hackernews_browse",
    description="Browse HackerNews front page",
    steps=[
        WorkflowStep("navigate", "https://news.ycombinator.com"),
        WorkflowStep("wait", value="2"),
        WorkflowStep("extract"),
    ]
)


# Workflow registry for easy lookup
WORKFLOW_REGISTRY: Dict[str, SimpleWorkflow] = {
    "google_search": GOOGLE_SEARCH,
    "simple_navigate": SIMPLE_NAVIGATE,
    "linkedin_login": LINKEDIN_LOGIN,
    "amazon_search": AMAZON_SEARCH,
    "twitter_post": TWITTER_POST,
    "github_repo": GITHUB_REPO_BROWSE,
    "simple_form": SIMPLE_FORM_FILL,
    "youtube_search": YOUTUBE_SEARCH,
    "reddit_browse": REDDIT_BROWSE,
    "hackernews_browse": HACKERNEWS_BROWSE,
}


def get_workflow(name: str) -> Optional[SimpleWorkflow]:
    """Get a pre-built workflow by name."""
    return WORKFLOW_REGISTRY.get(name)


def list_workflows() -> List[str]:
    """List all available pre-built workflows."""
    return list(WORKFLOW_REGISTRY.keys())
