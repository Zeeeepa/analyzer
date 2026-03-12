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

        # Map ref_id -> (role, name) for element resolution
        self._ref_map: Dict[str, Dict[str, str]] = {}

    async def _init_browser(self):
        """Initialize Playwright browser.

        Auto-detects headless environments (no DISPLAY on Linux) and forces
        headless mode to prevent silent hangs when no display server is available.
        """
        if self.browser is not None:
            return

        # Auto-detect: if no DISPLAY on Linux and headless wasn't explicitly set,
        # force headless to prevent silent hang waiting for a GUI window.
        headless = self.headless
        if not headless and sys.platform.startswith("linux"):
            display = os.environ.get("DISPLAY", "")
            wayland = os.environ.get("WAYLAND_DISPLAY", "")
            if not display and not wayland:
                headless = True
                logger.warning("No display server detected — auto-enabling headless mode")
                print("⚠ No display detected, running headless", flush=True)

        try:
            from playwright.async_api import async_playwright

            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=headless)
            self.page = await self.browser.new_page()

            logger.debug(f"Browser initialized (headless={headless})")
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
        """Get accessibility snapshot of current page and build ref map.

        Uses Playwright's aria_snapshot() API (v1.49+) which returns a
        YAML-like accessibility tree. Falls back to page.accessibility.snapshot()
        for older versions.
        """
        try:
            # Wait briefly for SPA rendering to settle
            await asyncio.sleep(0.3)

            # Try modern aria_snapshot() first (Playwright 1.49+)
            aria_text = None
            try:
                aria_text = await self.page.locator('body').aria_snapshot()
            except Exception:
                pass

            if not aria_text:
                # Retry after wait
                await asyncio.sleep(1.5)
                try:
                    aria_text = await self.page.locator('body').aria_snapshot()
                except Exception:
                    pass

            if not aria_text:
                # Last resort: try deprecated API
                try:
                    snapshot = await self.page.accessibility.snapshot()
                    refs = self.parser.parse_snapshot(snapshot)
                    self._ref_map.clear()
                    for ref in refs:
                        self._ref_map[ref.ref] = {"role": ref.role, "name": ref.name, "value": ref.value or ""}
                    lines = [f"- {r.role} \"{r.name}\" [ref={r.ref}]" for r in refs]
                    return "\n".join(lines) if lines else "(page is empty or still loading)"
                except Exception:
                    return "(page is empty or still loading)"

            # Parse the aria_snapshot YAML text into ref map
            self._ref_map.clear()
            lines_out = []
            ref_counter = 0

            import re as _re
            for line in aria_text.split('\n'):
                stripped = line.strip()
                if not stripped or stripped.startswith('/url:') or stripped.startswith('#'):
                    continue

                # Match patterns like: - role "name"  or  - role:  or  - text: content
                match = _re.match(r'^-\s+(\w+)(?:\s+"([^"]*)")?(?:\s*:\s*(.*))?', stripped)
                if match:
                    role = match.group(1).lower()
                    name = match.group(2) or match.group(3) or ''
                    name = name.strip()

                    # Skip purely structural/decorative elements
                    if role in ('text',) and not name:
                        continue

                    ref_id = f"e{ref_counter}"
                    ref_counter += 1

                    self._ref_map[ref_id] = {
                        "role": role,
                        "name": name,
                        "value": "",
                    }

                    lines_out.append(f"- {role} \"{name}\" [ref={ref_id}]")

            return "\n".join(lines_out) if lines_out else "(page is empty or still loading)"
        except Exception as e:
            logger.error(f"Failed to get snapshot: {e}")
            return "(snapshot failed)"

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
        prompt = f"""You are a fast browser automation agent. Goal: {goal}

URL: {self.page.url}

Page elements:
{snapshot}

History (last 8):
{chr(10).join(history[-8:]) if history else "None"}

Actions: navigate(target=URL), click(target=ref), type(target=ref, value=text), press(value=key), scroll(value=down/up), wait(value=seconds), extract, done

CRITICAL RULES:
1. ALWAYS use the exact [ref=...] ID from "Page elements" as target (e.g. "s3e3", "s5e5")
2. NEVER use descriptive names like "email" or "password" as target — use the ref ID
3. Be EFFICIENT — avoid unnecessary wait/extract. Act directly on visible elements
4. For textbox elements: use "type" with the ref and value
5. For buttons/links: use "click" with the ref
6. After filling ALL form fields AND solving captcha, click the submit/sign-in button
7. Only use "done" when the original goal is fully complete (e.g. response retrieved)
8. If an element was "not found", the page may have changed — try a different ref from a fresh snapshot

JSON only:
{{"action":"...","target":"ref","value":"text if needed","reason":"why"}}"""

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

    async def _resolve_element(self, target: str):
        """
        Resolve an element reference to a Playwright locator.

        Uses the ref map built during _get_snapshot() to convert
        synthetic ref IDs (e.g., 'e9') into actual Playwright locators
        based on accessibility role + name.

        Falls back to:
        1. Role + name based locator (most reliable for SPAs)
        2. Text-based search
        3. CSS selector (if target looks like a selector)

        Returns the first visible, enabled locator or None.
        """
        # Check the ref map first
        ref_info = self._ref_map.get(target)
        if ref_info:
            role = ref_info["role"]
            name = ref_info["name"]

            # Map accessibility roles to Playwright get_by_role roles
            role_map = {
                "textbox": "textbox",
                "text": "textbox",
                "searchbox": "searchbox",
                "button": "button",
                "link": "link",
                "checkbox": "checkbox",
                "radio": "radio",
                "combobox": "combobox",
                "menuitem": "menuitem",
                "tab": "tab",
                "heading": "heading",
                "img": "img",
                "dialog": "dialog",
                "navigation": "navigation",
                "listitem": "listitem",
            }
            pw_role = role_map.get(role)

            if pw_role and name:
                try:
                    loc = self.page.get_by_role(pw_role, name=name, exact=False)
                    count = await loc.count()
                    if count > 0:
                        logger.debug(f"Resolved {target} via role={pw_role} name='{name}' ({count} match)")
                        return loc.first
                except Exception as e:
                    logger.debug(f"Role locator failed for {target}: {e}")

            # Fallback: match by name text
            if name:
                try:
                    loc = self.page.get_by_text(name, exact=False)
                    count = await loc.count()
                    if count > 0:
                        logger.debug(f"Resolved {target} via text='{name}' ({count} match)")
                        return loc.first
                except Exception as e:
                    logger.debug(f"Text locator failed for {target}: {e}")

            # Fallback: match by placeholder/label (for inputs)
            if role in ("textbox", "searchbox", "text") and name:
                try:
                    loc = self.page.get_by_placeholder(name, exact=False)
                    count = await loc.count()
                    if count > 0:
                        logger.debug(f"Resolved {target} via placeholder='{name}'")
                        return loc.first
                except Exception:
                    pass
                try:
                    loc = self.page.get_by_label(name, exact=False)
                    count = await loc.count()
                    if count > 0:
                        logger.debug(f"Resolved {target} via label='{name}'")
                        return loc.first
                except Exception:
                    pass

        # If target is NOT a ref ID, LLM may have sent a name like "email" or "Sign in"
        # Search the ref map by name to find a matching element
        if not ref_info and target:
            target_lower = str(target).lower().strip()
            for ref_id, info in self._ref_map.items():
                if info["name"].lower() == target_lower or target_lower in info["name"].lower():
                    logger.debug(f"Matched target '{target}' to ref {ref_id} ({info['role']} '{info['name']}')")
                    return await self._resolve_element(ref_id)  # Recurse with the actual ref

        # If target looks like a CSS selector, try it directly
        if any(c in str(target) for c in ['#', '.', '[', '>', ' ']):
            try:
                element = await self.page.query_selector(str(target))
                if element:
                    logger.debug(f"Resolved {target} via CSS selector")
                    return element
            except Exception:
                pass

        # Last resort: try getting element by visible text
        if target:
            try:
                loc = self.page.get_by_text(str(target), exact=False)
                count = await loc.count()
                if count > 0:
                    return loc.first
            except Exception:
                pass

        # Last-last resort: try by placeholder
        if target:
            try:
                loc = self.page.get_by_placeholder(str(target), exact=False)
                count = await loc.count()
                if count > 0:
                    return loc.first
            except Exception:
                pass

        return None

    async def _execute_action(self, action: Dict[str, Any]) -> str:
        """
        Execute a single action using accessibility-aware element resolution.

        Uses the ref map from the latest snapshot to find elements via
        Playwright's role-based locators instead of fragile CSS selectors.
        """
        action_type = action.get("action", "").lower()
        target = action.get("target")
        value = action.get("value")

        try:
            if action_type == "navigate":
                # Resolve the actual URL: LLMs sometimes return target="URL" (literal)
                # with the real URL in the value field. Prefer whichever looks like a URL.
                url = target
                if value and isinstance(value, str) and value.startswith(("http://", "https://")):
                    # If value is a valid URL, prefer it when target isn't
                    if not target or not isinstance(target, str) or not target.startswith(("http://", "https://")):
                        url = value
                elif target and isinstance(target, str) and not target.startswith(("http://", "https://")):
                    # Target isn't a URL — try value, or prepend https://
                    if value and isinstance(value, str) and value.startswith(("http://", "https://")):
                        url = value
                    elif target and "." in target and " " not in target:
                        url = f"https://{target}"  # bare domain like "chat.z.ai"

                nav_error = None
                try:
                    await self.page.goto(url, wait_until="networkidle", timeout=15000)
                except Exception as e1:
                    # Fallback: some SPAs never reach networkidle
                    try:
                        await self.page.goto(url, wait_until="domcontentloaded", timeout=10000)
                    except Exception as e2:
                        nav_error = e2

                if nav_error is not None:
                    logger.error(f"Navigation to {url} failed: {nav_error}")
                    return f"Navigation failed for {url}: {nav_error}"

                # Extra wait for SPA hydration
                await asyncio.sleep(1.0)
                return f"Navigated to {url}"

            elif action_type == "click":
                element = await self._resolve_element(target)
                if element:
                    await element.click(timeout=5000)
                    await asyncio.sleep(0.5)  # Wait for response to click
                    return f"Clicked {target}"
                else:
                    return f"Element not found: {target}"

            elif action_type == "type":
                element = await self._resolve_element(target)
                if element:
                    await element.click(timeout=3000)  # Focus first
                    await asyncio.sleep(0.1)
                    await element.fill(value, timeout=5000)
                    return f"Typed '{value}' into {target}"
                else:
                    return f"Element not found: {target}"

            elif action_type == "press":
                key = value or target or "Enter"
                await self.page.keyboard.press(key)
                return f"Pressed {key}"

            elif action_type == "scroll":
                direction = (value or "down").lower()
                delta = 400 if direction == "down" else -400
                await self.page.mouse.wheel(0, delta)
                await asyncio.sleep(0.3)
                return f"Scrolled {direction}"

            elif action_type == "wait":
                wait_time = float(value) if value else 2.0
                await asyncio.sleep(wait_time)
                return f"Waited {wait_time}s"

            elif action_type == "extract":
                content = await self.page.inner_text("body")
                # Truncate for history but include useful prefix
                preview = content[:500].strip()
                return f"Extracted content: {preview}"

            elif action_type == "screenshot":
                if value:
                    path = value
                else:
                    import tempfile
                    path = str(Path(tempfile.gettempdir()) / "eversale_screenshot.png")
                await self.page.screenshot(path=path)
                return f"Screenshot saved to {path}"

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
        steps = 0
        history = []

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
            consecutive_passive = 0  # Track consecutive extract/wait actions

            while steps < self.max_steps:
                steps += 1

                # Get current state
                snapshot = await self._get_snapshot()
                current_url = self.page.url

                # Add hint if LLM is stuck in extract/wait loop
                extra_hint = ""
                if consecutive_passive >= 2:
                    extra_hint = "\n⚠️ You've done multiple extract/wait actions in a row. The page content is already visible in the elements list above. TAKE ACTION NOW — click a button or type in a field!"

                # Plan next action
                action = await self._plan_next_action(goal, snapshot + extra_hint, history)

                # Track passive vs active actions
                if action.get("action") in ("extract", "wait"):
                    consecutive_passive += 1
                else:
                    consecutive_passive = 0

                # Execute
                status = await self._execute_action(action)
                history.append(f"Step {steps}: {action.get('action')} - {status}")

                # Print progress so CLI users see what's happening
                reason = action.get("reason", "")
                print(f"  [{steps}/{self.max_steps}] {action.get('action', '?')}: {reason or status}", flush=True)
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
    r"""Print startup banner."""
    print(r"""
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
    # Auto-start local API server if personal API keys are detected
    try:
        from local_server_launcher import ensure_local_server
        local_url = ensure_local_server()
        if local_url:
            logger.info(f"[run_simple] Local API server active at {local_url}")
    except ImportError:
        pass

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
