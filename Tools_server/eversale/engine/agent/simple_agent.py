"""
Simple Agent - Accessibility-First Browser Automation

This is the new primary agent for Eversale CLI v2.9+.
Uses accessibility snapshots and refs (like Playwright MCP).

Philosophy:
- Simple loop: snapshot -> LLM -> action -> repeat
- Refs are stable - no complex recovery needed
- Let the LLM reason on semantic elements
- Minimal code, maximum reliability

Usage:
    agent = SimpleAgent()
    result = await agent.run("Search Google for AI news")
"""

import asyncio
import json
import re
import random
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

try:
    from .a11y_browser import A11yBrowser, Snapshot, ActionResult
    from . import a11y_config as config
except ImportError:
    from a11y_browser import A11yBrowser, Snapshot, ActionResult
    import a11y_config as config


@dataclass
class AgentResult:
    """Result of agent execution."""
    success: bool
    goal: str
    steps_taken: int
    final_url: str
    error: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)


class SimpleAgent:
    """
    Simple accessibility-first browser agent.

    This agent uses a straightforward loop:
    1. Get accessibility snapshot
    2. Send snapshot + goal to LLM
    3. Execute LLM's action
    4. Repeat until done or max steps

    No complex recovery - if something fails, retry once.
    The accessibility approach is inherently more reliable.
    """

    SYSTEM_PROMPT = '''You are a browser automation agent. You can see the page as an accessibility snapshot with element refs like [e38].

Available actions (respond with exactly ONE action per turn):
- navigate <url> - Go to a URL
- click <ref> - Click element by ref (e.g., "click e38")
- type <ref> <text> - Type into element (e.g., "type e12 hello world")
- press <key> - Press keyboard key (e.g., "press Enter")
- scroll <direction> - Scroll up or down
- wait <seconds> - Wait for page to load
- done <summary> - Task complete, provide summary

Rules:
1. Use element refs from the snapshot (e.g., e38, e12)
2. One action at a time
3. Say "done" when the task is complete
4. If an element isn't visible, scroll or navigate to find it

Respond with just the action, nothing else.
Example responses:
- navigate https://google.com
- click e38
- type e12 python tutorial
- press Enter
- scroll down
- done Found 10 search results for Python tutorials'''

    FLASH_MODE_PROMPT = '''You are a browser agent. Given the page snapshot, output ONLY:
ACTION: <action>(ref="<ref>", value="<value if needed>")
MEMORY: <one line summary of what you did>

No thinking, no evaluation, no explanation. Just action and memory.

Available actions:
- navigate <url>
- click <ref>
- type <ref> <text>
- press <key>
- scroll <direction>
- wait <seconds>
- done <summary>

Example:
ACTION: click e38
MEMORY: Clicked search button'''

    def __init__(
        self,
        llm_client=None,  # Inject LLM client
        max_steps: int = None,
        headless: bool = None,
        flash_mode: bool = False,  # NEW: Skip reasoning for simple tasks
    ):
        self.llm_client = llm_client
        self.max_steps = max_steps or config.MAX_AGENT_STEPS
        self.headless = headless if headless is not None else config.DEFAULT_HEADLESS
        self.flash_mode = flash_mode
        self.browser: Optional[A11yBrowser] = None

        # Performance tracking
        self.start_time: Optional[float] = None
        self.llm_calls: int = 0
        self.retries: int = 0

        # Snapshot diffing tracking
        self._first_snapshot_taken: bool = False

    def _should_use_flash_mode(self, goal: str) -> bool:
        """Detect if task is simple enough for flash mode."""
        simple_patterns = [
            "click", "type", "fill", "navigate to", "go to",
            "search for", "enter", "submit", "login"
        ]
        goal_lower = goal.lower()
        # Flash mode for single-action goals
        return any(p in goal_lower for p in simple_patterns) and len(goal.split()) < 15

    async def run(self, goal: str) -> AgentResult:
        """
        Run the agent to achieve a goal.

        Args:
            goal: Natural language description of what to do

        Returns:
            AgentResult with success status, data, and metrics
        """
        steps = 0
        error = None
        self.start_time = time.time()
        self.llm_calls = 0
        self.retries = 0
        self._first_snapshot_taken = False  # Reset for new run

        # Auto-detect flash mode if not explicitly set
        if not self.flash_mode and config.FLASH_MODE_AUTO_DETECT:
            if self._should_use_flash_mode(goal):
                self.flash_mode = True
                if config.LOG_ACTIONS:
                    print("[agent] Auto-enabled flash mode for simple task")

        try:
            # Launch browser
            self.browser = A11yBrowser(headless=self.headless)
            await self.browser.launch()

            if config.LOG_ACTIONS:
                mode_str = " (flash mode)" if self.flash_mode else ""
                print(f"[agent] Starting{mode_str}: {goal}")

            # Main loop
            while steps < self.max_steps:
                steps += 1

                # Get snapshot with automatic diff mode after first snapshot
                # First snapshot: full (diff_mode=False)
                # Subsequent snapshots: diff only (diff_mode=True) when config.ENABLE_SNAPSHOT_DIFF is True
                use_diff_mode = self._first_snapshot_taken and config.ENABLE_SNAPSHOT_DIFF
                snapshot = await self.browser.snapshot(diff_mode=use_diff_mode)

                # Mark first snapshot as taken
                if not self._first_snapshot_taken:
                    self._first_snapshot_taken = True
                    if config.LOG_METRICS:
                        print("[agent] First snapshot taken, enabling diff mode for subsequent snapshots")

                # Get action from LLM
                action = await self._get_action(goal, snapshot, steps)

                if action is None:
                    error = "LLM returned no action"
                    if config.LOG_ERRORS:
                        print(f"[agent] Error: {error}")
                    break

                # Check if done
                if action.startswith("done"):
                    summary = action[4:].strip()
                    return self._create_result(
                        success=True,
                        goal=goal,
                        steps=steps,
                        data={"summary": summary}
                    )

                # Execute action with retry
                result = await self._execute_with_retry(action)

                if not result.success:
                    if config.LOG_ERRORS:
                        print(f"[agent] Action failed after retries: {result.error}")
                    # Continue - maybe next action will work

                # Small delay between actions
                await asyncio.sleep(config.ACTION_DELAY)

            # Max steps reached
            error = f"Max steps reached ({self.max_steps})"
            if config.LOG_ERRORS:
                print(f"[agent] {error}")

            return self._create_result(
                success=False,
                goal=goal,
                steps=steps,
                error=error
            )

        except Exception as e:
            error = str(e)
            if config.LOG_ERRORS:
                print(f"[agent] Exception: {error}")

            return self._create_result(
                success=False,
                goal=goal,
                steps=steps,
                error=error
            )
        finally:
            if self.browser:
                await self.browser.close()

    def _create_result(
        self,
        success: bool,
        goal: str,
        steps: int,
        error: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """Create an AgentResult with metrics."""
        total_time = time.time() - self.start_time if self.start_time else 0.0

        metrics = {
            "total_time": total_time,
            "llm_calls": self.llm_calls,
            "retries": self.retries,
            "flash_mode": self.flash_mode,
        }

        # Add browser metrics if available
        if self.browser and config.ENABLE_METRICS:
            metrics.update(self.browser.get_metrics())

        final_url = ""
        if self.browser and self.browser._page:
            try:
                final_url = self.browser.page.url
            except Exception as e:
                if config.LOG_ERRORS:
                    print(f"[agent] Failed to get final URL: {e}")

        return AgentResult(
            success=success,
            goal=goal,
            steps_taken=steps,
            final_url=final_url,
            error=error,
            data=data or {},
            metrics=metrics
        )

    async def _execute_with_retry(self, action: str) -> ActionResult:
        """
        Execute action with exponential backoff retry.

        Retries failed actions with increasing delays and random jitter.
        """
        if not config.ENABLE_AUTO_RETRY:
            return await self._execute_action(action)

        max_retries = config.MAX_RETRIES
        delay = config.RETRY_DELAY

        for attempt in range(max_retries + 1):
            result = await self._execute_action(action)

            if result.success:
                return result

            # Last attempt - return failure
            if attempt >= max_retries:
                return result

            # Retry with backoff
            self.retries += 1

            # Calculate delay with exponential backoff
            if config.ENABLE_EXPONENTIAL_BACKOFF:
                current_delay = delay * (config.RETRY_BACKOFF_MULTIPLIER ** attempt)
            else:
                current_delay = delay

            # Add jitter
            if config.ENABLE_RETRY_JITTER:
                jitter = current_delay * config.RETRY_JITTER * random.random()
                current_delay += jitter

            if config.LOG_ERRORS:
                print(f"[agent] Retry {attempt + 1}/{max_retries} after {current_delay:.2f}s: {result.error}")

            await asyncio.sleep(current_delay)

        return result

    async def _get_action(self, goal: str, snapshot: Snapshot, step: int) -> Optional[str]:
        """
        Get next action from LLM.

        Includes better error messages and logging.
        """
        # Format snapshot for LLM
        snapshot_text = self._format_snapshot(snapshot)

        # Build prompt
        user_prompt = f"""Goal: {goal}

Current page: {snapshot.title}
URL: {snapshot.url}
Step: {step}/{self.max_steps}

Page elements:
{snapshot_text}

What is your next action?"""

        # Call LLM
        if self.llm_client:
            try:
                response = await self._call_llm(user_prompt)
                action = self._parse_action(response)

                if action and config.LOG_ACTIONS:
                    print(f"[agent] Step {step}: {action}")

                return action
            except Exception as e:
                if config.LOG_ERRORS:
                    print(f"[agent] LLM error: {e}")
                return None
        else:
            # Fallback: use simple pattern matching for testing
            action = await self._fallback_action(goal, snapshot, step)
            if config.LOG_ACTIONS:
                print(f"[agent] Step {step} (fallback): {action}")
            return action

    def _format_snapshot(self, snapshot: Snapshot) -> str:
        """
        Format snapshot for LLM consumption.

        Limits elements based on estimated token count to prevent huge prompts.
        """
        lines = []

        # Calculate max elements based on token budget
        max_elements = min(
            len(snapshot.elements),
            config.MAX_PROMPT_TOKENS // config.TOKENS_PER_ELEMENT
        )

        for el in snapshot.elements[:max_elements]:
            lines.append(str(el))

        if len(snapshot.elements) > max_elements:
            lines.append(f"... and {len(snapshot.elements) - max_elements} more elements")

        return "\n".join(lines) if lines else "(no interactive elements found)"

    async def _call_llm(self, prompt: str) -> str:
        """
        Call the LLM client.

        Tracks LLM call count for metrics.
        Uses flash mode prompt if enabled for token reduction.
        """
        self.llm_calls += 1

        try:
            # Choose system prompt based on mode
            system_prompt = self.FLASH_MODE_PROMPT if self.flash_mode else self.SYSTEM_PROMPT

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
            response = await self.llm_client.chat(messages)
            content = response.get("content", "").strip()

            if not content and config.LOG_ERRORS:
                print("[agent] LLM returned empty response")

            return content
        except Exception as e:
            if config.LOG_ERRORS:
                print(f"[agent] LLM error: {e}")
            raise

    def _parse_action(self, response: str) -> Optional[str]:
        """Parse LLM response into action."""
        if not response:
            return None

        # Flash mode format: "ACTION: <action>\nMEMORY: <memory>"
        if self.flash_mode and "ACTION:" in response:
            # Extract action line
            for line in response.split("\n"):
                if line.strip().startswith("ACTION:"):
                    action = line.replace("ACTION:", "").strip()
                    # Remove any ref="..." or value="..." formatting if present
                    action = re.sub(r'\(ref="([^"]+)"(?:, value="([^"]+)")?\)', r'\1 \2', action).strip()
                    return action if action else None

        # Standard format: Take first line, strip any markdown
        action = response.split("\n")[0].strip()
        action = re.sub(r'^```\w*\s*', '', action)
        action = re.sub(r'\s*```$', '', action)

        return action if action else None

    async def _fallback_action(self, goal: str, snapshot: Snapshot, step: int) -> str:
        """Fallback action logic when no LLM is available."""
        goal_lower = goal.lower()

        # Step 1: Navigate if needed
        if step == 1:
            if "google" in goal_lower:
                return "navigate https://google.com"
            elif "http" in goal_lower:
                # Extract URL from goal
                match = re.search(r'https?://\S+', goal)
                if match:
                    return f"navigate {match.group()}"
            return "navigate https://google.com"

        # Step 2+: Look for search box or relevant elements
        search_boxes = snapshot.find_by_role("searchbox") + snapshot.find_by_role("textbox")
        if search_boxes and step == 2:
            # Extract search query from goal
            query = re.sub(r'(search|google|for|find)', '', goal_lower).strip()
            return f"type {search_boxes[0].ref} {query}"

        if step == 3:
            return "press Enter"

        if step == 4:
            return "wait 2"

        return "done Completed fallback execution"

    async def _execute_action(self, action: str) -> ActionResult:
        """Execute a parsed action."""
        parts = action.split(None, 2)  # Split into max 3 parts

        if not parts:
            return ActionResult(success=False, action="unknown", error="Empty action")

        cmd = parts[0].lower()

        if cmd == "navigate" and len(parts) > 1:
            return await self.browser.navigate(parts[1])

        elif cmd == "click" and len(parts) > 1:
            return await self.browser.click(parts[1])

        elif cmd == "type" and len(parts) > 2:
            ref = parts[1]
            text = parts[2]
            return await self.browser.type(ref, text)

        elif cmd == "press" and len(parts) > 1:
            return await self.browser.press(parts[1])

        elif cmd == "scroll":
            direction = parts[1] if len(parts) > 1 else "down"
            return await self.browser.scroll(direction)

        elif cmd == "wait" and len(parts) > 1:
            try:
                seconds = float(parts[1])
                return await self.browser.wait(seconds)
            except ValueError:
                return await self.browser.wait(1)

        elif cmd == "hover" and len(parts) > 1:
            return await self.browser.hover(parts[1])

        elif cmd == "back":
            return await self.browser.go_back()

        elif cmd == "forward":
            return await self.browser.go_forward()

        elif cmd == "refresh":
            return await self.browser.refresh()

        elif cmd == "screenshot":
            path = parts[1] if len(parts) > 1 else None
            return await self.browser.screenshot(path)

        elif cmd == "done":
            return ActionResult(success=True, action="done")

        else:
            return ActionResult(
                success=False,
                action=cmd,
                error=f"Unknown action: {action}"
            )


# === Convenience functions ===

async def run_task(goal: str, llm_client=None, headless: bool = False, flash_mode: bool = False) -> AgentResult:
    """Run a single task with the simple agent."""
    agent = SimpleAgent(llm_client=llm_client, headless=headless, flash_mode=flash_mode)
    return await agent.run(goal)


# === Example usage ===

async def example():
    """Example usage of SimpleAgent."""
    # Without LLM (uses fallback logic)
    agent = SimpleAgent(headless=False)
    result = await agent.run("Search Google for Python tutorials")

    print(f"Success: {result.success}")
    print(f"Steps: {result.steps_taken}")
    print(f"Final URL: {result.final_url}")
    if result.data:
        print(f"Summary: {result.data.get('summary')}")
    if result.error:
        print(f"Error: {result.error}")


if __name__ == "__main__":
    asyncio.run(example())
