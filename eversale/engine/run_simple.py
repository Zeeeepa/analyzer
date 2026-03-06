#!/usr/bin/env python3
"""
run_simple.py - Accessibility-First Agent Entry Point

This is the new primary entry point for Eversale CLI v2.9+.
Uses accessibility snapshots and refs (like Playwright MCP).

Usage:
    python run_simple.py "Search Google for AI news"
    python run_simple.py --headless "Navigate to github.com"
    python run_simple.py --help

This replaces run_ultimate.py for most use cases.

Philosophy:
- Accessibility-first: Use refs instead of CSS selectors
- Simple: Linear execution, clear status
- Reliable: Deterministic browser automation
- Fast: Minimal LLM calls, direct actions
"""

import asyncio
import argparse
import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from agent.llm_client import LLMClient, LLMResponse
from agent.accessibility_element_finder import AccessibilityTreeParser, AccessibilityRef
from agent.action_templates import find_template, TEMPLATES
from loguru import logger

# Try to import a11y template executor (graceful fallback if not yet created)
try:
    from agent.a11y_template_executor import execute_template_a11y
    from agent.a11y_browser import A11yBrowser
    HAS_A11Y_EXECUTOR = True
except ImportError:
    HAS_A11Y_EXECUTOR = False
    A11yBrowser = None
    logger.debug("a11y_template_executor not available yet, will use LLM fallback")


@dataclass
class AgentResult:
    """Result from running the agent."""
    success: bool
    goal: str
    steps_taken: int
    final_url: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class SimpleAgent:
    """
    Simple accessibility-first browser agent.

    Uses:
    - Accessibility snapshots for element finding
    - LLM for planning (optional)
    - Direct Playwright actions

    This is a minimal viable agent - extend as needed.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        max_steps: int = 20,
        headless: bool = True
    ):
        """
        Initialize the simple agent.

        Args:
            llm_client: LLM client for planning (optional, uses fallback if None)
            max_steps: Maximum steps before giving up
            headless: Run browser in headless mode
        """
        self.llm_client = llm_client
        self.max_steps = max_steps
        self.headless = headless
        self.parser = AccessibilityTreeParser()

        # Browser state (initialized on first use)
        self.page = None
        self.browser = None

    async def _init_browser(self):
        """Initialize Playwright browser."""
        if self.browser is not None:
            return

        try:
            from playwright.async_api import async_playwright

            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=self.headless)
            self.page = await self.browser.new_page()

            logger.debug(f"Browser initialized (headless={self.headless})")
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            raise

    async def _close_browser(self):
        """Close browser and cleanup."""
        if self.page:
            await self.page.close()
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()

    async def _get_snapshot(self) -> str:
        """Get accessibility snapshot of current page."""
        try:
            # Get accessibility tree
            snapshot = await self.page.accessibility.snapshot()

            # Parse into refs
            refs = self.parser.parse_snapshot(snapshot)

            # Format as markdown (like MCP)
            lines = []
            for ref in refs:
                lines.append(f"- {ref.role} \"{ref.name}\" [ref={ref.ref}]")

            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Failed to get snapshot: {e}")
            return ""

    async def _plan_next_action(self, goal: str, snapshot: str, history: List[str]) -> Dict[str, Any]:
        """
        Use LLM to plan next action.

        Args:
            goal: User's goal
            snapshot: Current page accessibility snapshot
            history: List of actions taken so far

        Returns:
            Action dict: {"action": "navigate|click|type|wait", "target": "...", "value": "..."}
        """
        if not self.llm_client:
            # Fallback: simple logic without LLM
            return self._fallback_planner(goal, snapshot)

        # Build prompt
        prompt = f"""You are a browser automation agent. Your goal: {goal}

Current page state (accessibility tree):
{snapshot}

Actions taken so far:
{chr(10).join(history) if history else "None yet"}

What should I do next? Respond with JSON only:
{{"action": "navigate|click|type|wait|extract|done", "target": "ref or URL", "value": "text for type action", "reason": "why"}}

If goal is complete, use action "done".
"""

        try:
            response = await self.llm_client.generate(prompt, temperature=0.1)

            # Parse JSON from response
            import json
            import re

            # Extract JSON from response (handle markdown code blocks)
            content = response.content.strip()
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                action_data = json.loads(json_match.group(0))
                return action_data
            else:
                logger.warning(f"Could not parse LLM response: {content}")
                return {"action": "done", "reason": "Could not parse plan"}

        except Exception as e:
            logger.error(f"Planning failed: {e}")
            return {"action": "done", "reason": f"Planning error: {e}"}

    def _fallback_planner(self, goal: str, snapshot: str) -> Dict[str, Any]:
        """
        Simple fallback planner without LLM.

        Uses basic heuristics to navigate and interact.
        """
        goal_lower = goal.lower()

        # Extract search query if present
        if "search" in goal_lower or "find" in goal_lower:
            # Look for search box in snapshot
            refs = self.parser._parse_markdown(snapshot)
            search_box = None
            for ref in refs:
                if ref.role in ("textbox", "searchbox") and "search" in ref.name.lower():
                    search_box = ref
                    break

            if search_box:
                # Extract search term from goal
                import re
                match = re.search(r'(?:search|find)\s+(?:for\s+)?["\']?([^"\']+)["\']?', goal_lower)
                if match:
                    query = match.group(1).strip()
                    return {
                        "action": "type",
                        "target": search_box.ref,
                        "value": query,
                        "reason": "Typing search query"
                    }

        # Default: just navigate to Google
        if "http" not in goal_lower:
            return {
                "action": "navigate",
                "target": "https://www.google.com",
                "value": None,
                "reason": "Starting at Google"
            }

        return {"action": "done", "reason": "No clear next action"}

    async def _execute_action(self, action: Dict[str, Any]) -> str:
        """
        Execute a single action.

        Args:
            action: Action dict from planner

        Returns:
            Status message
        """
        action_type = action.get("action", "").lower()
        target = action.get("target")
        value = action.get("value")

        try:
            if action_type == "navigate":
                await self.page.goto(target, wait_until="domcontentloaded", timeout=10000)
                return f"Navigated to {target}"

            elif action_type == "click":
                # Find element by ref
                element = await self.page.query_selector(f'[data-ref="{target}"]')
                if element:
                    await element.click()
                    return f"Clicked {target}"
                else:
                    return f"Element not found: {target}"

            elif action_type == "type":
                element = await self.page.query_selector(f'[data-ref="{target}"]')
                if element:
                    await element.fill(value)
                    return f"Typed '{value}' into {target}"
                else:
                    return f"Element not found: {target}"

            elif action_type == "wait":
                wait_time = float(value) if value else 2.0
                await asyncio.sleep(wait_time)
                return f"Waited {wait_time}s"

            elif action_type == "extract":
                # Get page text content
                content = await self.page.inner_text("body")
                return f"Extracted page content ({len(content)} chars)"

            elif action_type == "done":
                return "Task complete"

            else:
                return f"Unknown action: {action_type}"

        except Exception as e:
            logger.error(f"Action failed: {e}")
            return f"Failed: {e}"

    async def run(self, goal: str) -> AgentResult:
        """
        Run the agent to accomplish a goal.

        Args:
            goal: Natural language description of what to do

        Returns:
            AgentResult with success status and details
        """
        logger.info(f"Starting agent with goal: {goal}")

        try:
            await self._init_browser()

            # Try template-based execution first (hybrid approach)
            if HAS_A11Y_EXECUTOR and A11yBrowser:
                template = find_template(goal)
                if template:
                    logger.info(f"Template match found: {template.name}")
                    try:
                        # Extract variables from the goal
                        variables = template.extract_variables(goal)

                        # Create A11yBrowser instance for template execution
                        async with A11yBrowser(headless=self.headless) as a11y_browser:
                            # Execute using a11y template executor
                            result = await execute_template_a11y(
                                template.name,
                                variables,
                                a11y_browser
                            )

                            if result.get('success'):
                                logger.info(f"Template execution successful: {template.name}")
                                return AgentResult(
                                    success=True,
                                    goal=goal,
                                    steps_taken=len(template.steps),
                                    final_url=result.get('url', result.get('final_url', '')),
                                    data=result.get('data')
                                )
                            else:
                                logger.warning(f"Template execution failed, falling back to LLM: {result.get('error', 'Unknown error')}")
                    except Exception as e:
                        logger.warning(f"Template execution error, falling back to LLM: {e}")

            # Fall back to LLM planning if template fails or doesn't exist
            logger.info("Using LLM-based planning")
            history = []
            steps = 0

            while steps < self.max_steps:
                steps += 1

                # Get current state
                snapshot = await self._get_snapshot()
                current_url = self.page.url

                # Plan next action
                action = await self._plan_next_action(goal, snapshot, history)

                # Execute
                status = await self._execute_action(action)
                history.append(f"Step {steps}: {action.get('action')} - {status}")

                logger.debug(f"Step {steps}: {action.get('action')} - {status}")

                # Check if done
                if action.get("action") == "done":
                    logger.info(f"Task complete in {steps} steps")
                    return AgentResult(
                        success=True,
                        goal=goal,
                        steps_taken=steps,
                        final_url=current_url,
                        data={"summary": status, "history": history}
                    )

                # Small delay between actions
                await asyncio.sleep(0.5)

            # Max steps reached
            logger.warning(f"Max steps ({self.max_steps}) reached")
            return AgentResult(
                success=False,
                goal=goal,
                steps_taken=steps,
                final_url=self.page.url,
                error=f"Max steps ({self.max_steps}) reached",
                data={"history": history}
            )

        except Exception as e:
            logger.error(f"Agent failed: {e}")
            return AgentResult(
                success=False,
                goal=goal,
                steps_taken=steps,
                final_url=self.page.url if self.page else "",
                error=str(e),
                data={"history": history}
            )

        finally:
            await self._close_browser()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Eversale CLI - Accessibility-First Browser Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run_simple.py "Search Google for Python tutorials"
    python run_simple.py --headless "Go to github.com and find trending repos"
    python run_simple.py --max-steps 30 "Complete multi-step task"
        """
    )

    parser.add_argument(
        "goal",
        nargs="?",
        help="The task to perform (in natural language)"
    )

    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode"
    )

    parser.add_argument(
        "--max-steps",
        type=int,
        default=20,
        help="Maximum steps before giving up (default: 20)"
    )

    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Run without LLM (uses fallback logic, for testing)"
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output"
    )

    parser.add_argument(
        "--version",
        action="version",
        version="Eversale CLI v2.9 (Accessibility-First)"
    )

    return parser.parse_args()


def print_banner():
    """Print startup banner."""
    print("""
 _____ _   _ _____ ____  ____    _    _     _____
| ____| | | | ____|  _ \/ ___|  / \  | |   | ____|
|  _| | | | |  _| | |_) \___ \ / _ \ | |   |  _|
| |___| |_| | |___|  _ < ___) / ___ \| |___| |___
|_____|\___/|_____|_| \_\____/_/   \_\_____|_____|
                                              v2.9
    Accessibility-First Browser Automation
    """)


def print_result(result: AgentResult, verbose: bool = False):
    """Print the agent result."""
    print("\n" + "=" * 50)

    if result.success:
        print("SUCCESS")
    else:
        print("FAILED")

    print("=" * 50)
    print(f"Goal: {result.goal}")
    print(f"Steps taken: {result.steps_taken}")
    print(f"Final URL: {result.final_url}")

    if result.data:
        if isinstance(result.data, dict) and result.data.get("summary"):
            print(f"\nSummary: {result.data['summary']}")
        elif isinstance(result.data, list) and len(result.data) > 0:
            print(f"\nExtracted {len(result.data)} items")

    if result.error:
        print(f"\nError: {result.error}")

    if verbose and result.data:
        print(f"\nFull data: {result.data}")


async def run_interactive():
    """Run in interactive mode."""
    print_banner()
    print("Interactive mode. Type your task and press Enter.")
    print("Type 'quit' or 'exit' to stop.\n")

    while True:
        try:
            goal = input("Task> ").strip()

            if not goal:
                continue

            if goal.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break

            # Create agent (no LLM for interactive - too slow)
            agent = SimpleAgent(headless=False, max_steps=20)
            result = await agent.run(goal)
            print_result(result)
            print()

        except KeyboardInterrupt:
            print("\nInterrupted. Goodbye!")
            break
        except EOFError:
            break


async def main():
    """Main entry point."""
    args = parse_args()

    # Interactive mode if no goal provided
    if not args.goal:
        await run_interactive()
        return 0

    if args.verbose:
        print_banner()
        print(f"Goal: {args.goal}")
        print(f"Headless: {args.headless}")
        print(f"Max steps: {args.max_steps}")
        print()

    # Initialize LLM client (unless --no-llm)
    llm_client = None
    if not args.no_llm:
        try:
            # Try to initialize LLM client
            # This will use the configured LLM (local Ollama or remote via eversale.io)
            llm_client = LLMClient()
        except Exception as e:
            if args.verbose:
                print(f"Warning: Could not initialize LLM client: {e}")
                print("Running with fallback logic...")

    # Run agent
    agent = SimpleAgent(
        llm_client=llm_client,
        max_steps=args.max_steps,
        headless=args.headless
    )

    result = await agent.run(args.goal)
    print_result(result, args.verbose)

    return 0 if result.success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
