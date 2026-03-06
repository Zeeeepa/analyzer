"""
Universal Agent - Works on ANY website like Playwright MCP

This agent uses:
1. A11yBrowser for accessibility-first automation
2. LLM planning with proper tool definitions
3. Universal extraction that works on any page
4. Smart scrolling for infinite scroll pages

The key insight from Playwright MCP: give the LLM a snapshot,
let it reason about what to do, execute it, repeat.
"""

import asyncio
import json
import re
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from loguru import logger

try:
    from .a11y_browser import A11yBrowser, Snapshot, ElementRef
    from .llm_client import LLMClient
except ImportError:
    from a11y_browser import A11yBrowser, Snapshot, ElementRef
    from llm_client import LLMClient


@dataclass
class AgentResult:
    """Result from running the agent."""
    success: bool
    goal: str
    steps_taken: int
    final_url: str
    data: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    history: List[str] = field(default_factory=list)


# System prompt for the LLM planner
SYSTEM_PROMPT = """You are a browser automation agent. You can see the page through accessibility snapshots and interact using element refs.

AVAILABLE ACTIONS (respond with exactly one JSON object):

1. Navigate to URL:
   {"action": "navigate", "url": "https://example.com"}

2. Click an element (use the ref from snapshot):
   {"action": "click", "ref": "e42", "description": "Login button"}

3. Type text into an input:
   {"action": "type", "ref": "e15", "text": "search query", "submit": true}
   (submit: true will press Enter after typing)

4. Scroll the page:
   {"action": "scroll", "direction": "down", "amount": 1000}

5. Wait for content to load:
   {"action": "wait", "seconds": 2}

6. Extract data from the page:
   {"action": "extract", "type": "list|table|cards", "description": "what to extract"}

7. Task complete:
   {"action": "done", "summary": "what was accomplished"}

RULES:
- Look at the snapshot carefully - elements show as [ref] role "name"
- Use the EXACT ref from the snapshot (e.g., "e42", not "42")
- For search: type into searchbox/textbox, then submit or click search button
- For extraction: scroll down first to load more content if it's infinite scroll
- If stuck or page unchanged after 3 attempts, try a different approach
- When goal is achieved, use "done" action with summary

Respond with ONLY a JSON object, no explanation."""


class UniversalAgent:
    """
    Universal browser automation agent.

    Works on any website by:
    1. Taking accessibility snapshots
    2. Using LLM to plan next action
    3. Executing actions via A11yBrowser
    4. Extracting data universally
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        max_steps: int = 150,
        headless: bool = True
    ):
        self.llm_client = llm_client
        self.max_steps = max_steps
        self.headless = headless
        self.browser: Optional[A11yBrowser] = None

        # Snapshot diffing tracking
        self._first_snapshot_taken: bool = False

        # State tracking
        self.history: List[str] = []
        self.extracted_data: List[Dict[str, Any]] = []
        self.last_url: str = ""
        self.stuck_count: int = 0

    async def run(self, goal: str) -> AgentResult:
        """
        Run the agent to accomplish a goal.

        Args:
            goal: Natural language description of what to do

        Returns:
            AgentResult with success status and extracted data
        """
        logger.info(f"Starting universal agent with goal: {goal}")

        steps = 0
        self.history = []
        self.extracted_data = []
        self.stuck_count = 0
        self._first_snapshot_taken = False  # Reset for new run

        try:
            async with A11yBrowser(headless=self.headless) as browser:
                self.browser = browser

                while steps < self.max_steps:
                    steps += 1

                    # Get current state (force=True after actions that change page)
                    need_fresh = len(self.history) > 0 and any(
                        "scroll" in h.lower() or "navigate" in h.lower()
                        for h in self.history[-3:]
                    )

                    # Use diff mode after first snapshot (unless forcing fresh snapshot)
                    try:
                        from . import a11y_config as config
                    except ImportError:
                        import a11y_config as config

                    use_diff_mode = self._first_snapshot_taken and config.ENABLE_SNAPSHOT_DIFF and not need_fresh
                    snapshot = await browser.snapshot(force=need_fresh, diff_mode=use_diff_mode)

                    # Mark first snapshot as taken
                    if not self._first_snapshot_taken:
                        self._first_snapshot_taken = True
                        logger.debug("First snapshot taken, enabling diff mode for subsequent snapshots")
                    current_url = snapshot.url if snapshot else ""

                    # Check if stuck (same URL, no progress)
                    if current_url == self.last_url:
                        self.stuck_count += 1
                    else:
                        self.stuck_count = 0
                        self.last_url = current_url

                    # Plan next action
                    action = await self._plan_action(goal, snapshot)

                    if not action:
                        logger.warning("No action returned from planner")
                        continue

                    # Execute action
                    result = await self._execute_action(action, snapshot)

                    # Record history
                    action_summary = f"Step {steps}: {action.get('action')} - {result}"
                    self.history.append(action_summary)
                    logger.debug(action_summary)

                    # Check if done
                    if action.get("action") == "done":
                        logger.info(f"Goal achieved in {steps} steps")
                        return AgentResult(
                            success=True,
                            goal=goal,
                            steps_taken=steps,
                            final_url=current_url,
                            data=self.extracted_data if self.extracted_data else None,
                            history=self.history
                        )

                    # Small delay between actions
                    await asyncio.sleep(0.3)

                # Max steps reached
                logger.warning(f"Max steps ({self.max_steps}) reached")
                return AgentResult(
                    success=len(self.extracted_data) > 0,  # Partial success if we got data
                    goal=goal,
                    steps_taken=steps,
                    final_url=self.last_url,
                    data=self.extracted_data if self.extracted_data else None,
                    error=f"Max steps ({self.max_steps}) reached",
                    history=self.history
                )

        except Exception as e:
            logger.error(f"Agent failed: {e}")
            return AgentResult(
                success=False,
                goal=goal,
                steps_taken=steps,
                final_url=self.last_url,
                error=str(e),
                history=self.history
            )

    async def _plan_action(self, goal: str, snapshot: Optional[Snapshot]) -> Dict[str, Any]:
        """
        Use LLM to plan the next action.

        Strategy:
        1. Use rule-based for known site patterns (FB Ads, LinkedIn, etc.) - more reliable
        2. Use LLM for unknown/complex situations
        """
        goal_lower = goal.lower()

        # For known patterns, prefer rule-based planning (more reliable than LLM)
        known_patterns = ["facebook", "fb ads", "linkedin", "google", "twitter", "reddit"]
        if any(pattern in goal_lower for pattern in known_patterns):
            return self._rule_based_plan(goal, snapshot)

        # Format snapshot for LLM
        snapshot_text = self._format_snapshot(snapshot) if snapshot else "No snapshot available"

        # Build the prompt
        user_prompt = f"""GOAL: {goal}

CURRENT PAGE:
URL: {snapshot.url if snapshot else 'No page loaded'}
Title: {snapshot.title if snapshot else 'N/A'}

ACCESSIBILITY SNAPSHOT:
{snapshot_text}

HISTORY:
{chr(10).join(self.history[-5:]) if self.history else "No actions yet"}

EXTRACTED SO FAR: {len(self.extracted_data)} items

{"WARNING: Stuck for " + str(self.stuck_count) + " steps - try a different approach!" if self.stuck_count >= 2 else ""}

What action should I take next? Respond with JSON only."""

        # Try LLM for unknown patterns
        if self.llm_client:
            try:
                # Combine system + user prompt (LLMClient doesn't have separate system_prompt)
                full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"
                response = await self.llm_client.generate(
                    full_prompt,
                    temperature=0.1
                )

                # Parse JSON from response
                content = response.content.strip()

                # Handle markdown code blocks
                if "```" in content:
                    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
                    if match:
                        content = match.group(1)

                # Find JSON object
                json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))

            except Exception as e:
                logger.warning(f"LLM planning failed: {e}")

        # Fallback: rule-based planning
        return self._rule_based_plan(goal, snapshot)

    def _rule_based_plan(self, goal: str, snapshot: Optional[Snapshot]) -> Dict[str, Any]:
        """
        Rule-based fallback planner when LLM is unavailable.

        Uses a state machine approach:
        1. Navigate to target site
        2. (Optional) Search if needed
        3. Scroll to load content
        4. Extract data
        5. Done
        """
        goal_lower = goal.lower()

        # Track what we've done to avoid repetition
        actions_done = set()
        for h in self.history:
            if "navigate" in h.lower():
                actions_done.add("navigate")
            if "type" in h.lower():
                actions_done.add("type")
            if "scroll" in h.lower():
                actions_done.add("scroll")
            if "extract" in h.lower():
                actions_done.add("extract")

        # Count scrolls
        scroll_count = sum(1 for h in self.history if "scroll" in h.lower())

        # Phase 1: Navigate if not done
        if "navigate" not in actions_done:
            if not snapshot or not snapshot.url or snapshot.url == "about:blank":
                # Extract URL from goal if present
                url_match = re.search(r'https?://[^\s]+', goal)
                if url_match:
                    return {"action": "navigate", "url": url_match.group(0)}

                # Known site patterns
                if "facebook" in goal_lower or "fb ads" in goal_lower:
                    query = self._extract_query(goal)
                    if query:
                        return {
                            "action": "navigate",
                            "url": f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&media_type=all&q={query.replace(' ', '%20')}&search_type=keyword_unordered"
                        }
                    return {"action": "navigate", "url": "https://www.facebook.com/ads/library/"}

                if "linkedin" in goal_lower:
                    query = self._extract_query(goal)
                    if query:
                        return {"action": "navigate", "url": f"https://www.linkedin.com/search/results/all/?keywords={query.replace(' ', '%20')}"}
                    return {"action": "navigate", "url": "https://www.linkedin.com/"}

                if "google" in goal_lower:
                    query = self._extract_query(goal)
                    if query:
                        return {"action": "navigate", "url": f"https://www.google.com/search?q={query.replace(' ', '+')}"}
                    return {"action": "navigate", "url": "https://www.google.com/"}

                # Default for unknown sites
                query = self._extract_query(goal)
                if query:
                    return {"action": "navigate", "url": f"https://www.google.com/search?q={query.replace(' ', '+')}"}

        # Phase 2: Wait for page to load after navigation
        if "navigate" in actions_done and len(self.history) == 1:
            return {"action": "wait", "seconds": 3}

        # Phase 3: Scroll + Extract cycles for infinite scroll pages
        # Pattern: scroll 3-5 times, extract, repeat
        extract_count = sum(1 for h in self.history if "extract" in h.lower())

        # How many scroll-extract cycles have we done?
        cycle = extract_count  # Each extraction marks end of a cycle
        scrolls_in_cycle = scroll_count - (cycle * 4)  # 4 scrolls per cycle

        # Max 25 cycles (25 extractions = 100+ items for infinite scroll)
        # Increased from 5 to support large-scale extraction
        if cycle < 25:
            # Within a cycle: scroll 4 times, then extract
            if scrolls_in_cycle < 4:
                return {"action": "scroll", "direction": "down", "amount": 1000}
            else:
                # Done scrolling for this cycle, extract
                return self._get_extract_action(goal)

        # Phase 5: Done if we have data, or try more scrolls if not
        if len(self.extracted_data) > 0:
            return {"action": "done", "summary": f"Extracted {len(self.extracted_data)} items"}

        # No data yet - scroll more and try again (increased from 20 to 100)
        if scroll_count < 100:
            return {"action": "scroll", "direction": "down", "amount": 1000}

        # Final extraction attempt
        return {"action": "extract", "type": "list", "description": goal}

    def _extract_query(self, goal: str) -> Optional[str]:
        """Extract search query from goal."""
        patterns = [
            r'for\s+["\']([^"\']+)["\']',  # for "query"
            r'for\s+(\w+(?:\s+\w+)*?)(?:\s+on|\s+in|\s*$)',  # for query on/in
            r'search\s+["\']([^"\']+)["\']',  # search "query"
            r'search\s+(?:for\s+)?(\w+(?:\s+\w+)*)',  # search [for] query
        ]

        for pattern in patterns:
            match = re.search(pattern, goal, re.IGNORECASE)
            if match:
                query = match.group(1).strip()
                # Clean up common suffixes
                for suffix in [" on facebook", " on linkedin", " on google", " ads", " library"]:
                    if query.lower().endswith(suffix):
                        query = query[:-len(suffix)].strip()
                return query

        return None

    def _format_snapshot(self, snapshot: Snapshot) -> str:
        """Format snapshot for LLM consumption."""
        if not snapshot or not snapshot.elements:
            return "Page is empty or loading..."

        lines = []
        for el in snapshot.elements[:100]:  # Limit to avoid token overflow
            parts = [f"[{el.ref}]", el.role]
            if el.name:
                # Truncate long names
                name = el.name[:80] + "..." if len(el.name) > 80 else el.name
                parts.append(f'"{name}"')
            if el.value:
                parts.append(f"value={el.value[:30]}")
            if el.focused:
                parts.append("(focused)")
            lines.append(" ".join(parts))

        if len(snapshot.elements) > 100:
            lines.append(f"... and {len(snapshot.elements) - 100} more elements")

        return "\n".join(lines)

    async def _execute_action(self, action: Dict[str, Any], snapshot: Optional[Snapshot]) -> str:
        """
        Execute an action using A11yBrowser.
        """
        action_type = action.get("action", "").lower()

        try:
            # Navigate
            if action_type == "navigate":
                url = action.get("url", "")
                if not url:
                    return "No URL provided"
                result = await self.browser.navigate(url)
                await asyncio.sleep(2)  # Wait for page load
                return f"Navigated to {url}"

            # Click
            if action_type == "click":
                ref = action.get("ref", "")
                if not ref:
                    return "No ref provided"
                result = await self.browser.click(ref)
                return f"Clicked {ref}" if result.success else f"Click failed: {result.error}"

            # Type
            if action_type == "type":
                ref = action.get("ref", "")
                text = action.get("text", "")
                submit = action.get("submit", False)

                if not ref or not text:
                    return "Missing ref or text"

                result = await self.browser.type(ref, text)
                if result.success and submit:
                    await asyncio.sleep(0.3)
                    await self.browser.press("Enter")
                    await asyncio.sleep(2)  # Wait for results
                    return f"Typed '{text}' and submitted"
                return f"Typed '{text}'" if result.success else f"Type failed: {result.error}"

            # Scroll
            if action_type == "scroll":
                direction = action.get("direction", "down")
                amount = action.get("amount", 500)
                result = await self.browser.scroll(direction, amount)
                await asyncio.sleep(1)  # Wait for content to load
                return f"Scrolled {direction} {amount}px"

            # Wait
            if action_type == "wait":
                seconds = action.get("seconds", 2)
                await asyncio.sleep(seconds)
                return f"Waited {seconds}s"

            # Extract
            if action_type == "extract":
                extract_type = action.get("type", "list")
                description = action.get("description", "")

                # For FB Ads, use specialized extractor from template_executor
                current_url = await self.browser.get_url() if hasattr(self.browser, 'get_url') else ""
                if "facebook.com/ads/library" in current_url:
                    try:
                        from .a11y_template_executor import _extract_fb_ads
                        result = await _extract_fb_ads(self.browser, max_ads=200)
                        if result.success and result.data:
                            extracted = result.data.get("ads", [])
                            self.extracted_data.extend(extracted)
                            return f"Extracted {len(extracted)} FB ads (total: {len(self.extracted_data)})"
                    except Exception as e:
                        logger.warning(f"FB Ads extraction failed, using universal: {e}")

                # Get fresh snapshot (force=True bypasses cache)
                fresh_snapshot = await self.browser.snapshot(force=True)

                # Debug: log element count
                if fresh_snapshot and fresh_snapshot.elements:
                    logger.debug(f"Snapshot has {len(fresh_snapshot.elements)} elements")
                    link_count = sum(1 for el in fresh_snapshot.elements if el.role == "link")
                    logger.debug(f"  {link_count} links found")
                else:
                    logger.warning("Snapshot is empty!")

                # Universal extraction
                extracted = await self._universal_extract(fresh_snapshot, extract_type, description)
                self.extracted_data.extend(extracted)

                return f"Extracted {len(extracted)} items (total: {len(self.extracted_data)})"

            # Done
            if action_type == "done":
                return action.get("summary", "Task complete")

            return f"Unknown action: {action_type}"

        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return f"Error: {e}"

    async def _universal_extract(
        self,
        snapshot: Snapshot,
        extract_type: str,
        description: str
    ) -> List[Dict[str, Any]]:
        """
        Universal extraction that works on any page.

        Extracts meaningful data from the accessibility snapshot:
        - Links with names (potential leads/results)
        - Text blocks (descriptions, metadata)
        - Structured groups (cards, list items)
        """
        if not snapshot or not snapshot.elements:
            return []

        items = []
        seen = set()

        # Skip patterns for filtering
        skip_names = {
            "home", "back", "next", "previous", "menu", "close", "settings",
            "help", "about", "privacy", "terms", "cookies", "sign in", "log in",
            "sign up", "register", "facebook", "twitter", "instagram", "linkedin",
            "share", "like", "comment", "follow", "subscribe", "newsletter",
            "ad library", "meta ad library", "filters", "sort", "view",
        }

        skip_patterns = [
            "sorry", "error", "trouble", "loading", "please wait",
            "learn more", "see more", "show more", "load more",
            "cookie", "privacy policy", "terms of service"
        ]

        elements = snapshot.elements
        i = 0

        while i < len(elements):
            el = elements[i]

            # Look for links (main extraction target)
            if el.role == "link" and el.name:
                name = el.name.strip()
                name_lower = name.lower()

                # Skip if too short, too long, or in skip list
                if len(name) < 3 or len(name) > 200:
                    i += 1
                    continue

                if name_lower in skip_names:
                    i += 1
                    continue

                if any(pattern in name_lower for pattern in skip_patterns):
                    i += 1
                    continue

                # Extract clean name (remove ad copy appended to advertiser names)
                clean_name = name
                for splitter in [" Read ", " Ready ", " Discover ", " Learn ", " Get ", " Start ", " Join ", " - "]:
                    if splitter in name:
                        clean_name = name.split(splitter)[0].strip()
                        break

                # Deduplicate
                dedup_key = clean_name.lower()[:50]
                if dedup_key in seen:
                    i += 1
                    continue
                seen.add(dedup_key)

                # Look for associated metadata
                metadata = {}
                for j in range(i + 1, min(i + 15, len(elements))):
                    next_el = elements[j]

                    # Stop if we hit another link (new item)
                    if next_el.role == "link" and next_el.name and len(next_el.name) > 10:
                        break

                    if next_el.role == "text" and next_el.name:
                        text = next_el.name.strip()
                        text_lower = text.lower()

                        # Skip UI text
                        if any(p in text_lower for p in skip_patterns):
                            continue

                        # Capture meaningful metadata
                        if "started running" in text_lower:
                            metadata["started"] = text
                        elif "active" in text_lower and len(text) < 50:
                            metadata["status"] = text
                        elif len(text) > 20 and len(text) < 300 and "description" not in metadata:
                            metadata["description"] = text[:200]

                # Build item
                item = {
                    "name": clean_name,
                    "full_text": name if name != clean_name else None,
                    "ref": el.ref,
                }
                item.update(metadata)

                # Remove None values
                item = {k: v for k, v in item.items() if v is not None}

                items.append(item)

            i += 1

        return items


async def run_universal(goal: str, headless: bool = False, max_steps: int = 150) -> AgentResult:
    """
    Convenience function to run the universal agent.

    Args:
        goal: What to accomplish
        headless: Run browser in headless mode
        max_steps: Maximum steps before giving up (default 150 to support 100+ item extraction)

    Returns:
        AgentResult with extracted data
    """
    # Try to initialize LLM client
    llm_client = None
    try:
        llm_client = LLMClient()
    except Exception as e:
        logger.warning(f"LLM client unavailable: {e}")

    agent = UniversalAgent(
        llm_client=llm_client,
        max_steps=max_steps,
        headless=headless
    )

    return await agent.run(goal)


# CLI entry point
if __name__ == "__main__":
    import sys

    goal = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "search fb ads library for CRM software"

    print(f"\nGoal: {goal}\n")

    result = asyncio.run(run_universal(goal, headless=False))

    print(f"\n{'='*50}")
    print("SUCCESS" if result.success else "FAILED")
    print(f"{'='*50}")
    print(f"Steps: {result.steps_taken}")
    print(f"URL: {result.final_url}")

    if result.data:
        print(f"\nExtracted {len(result.data)} items:")
        for i, item in enumerate(result.data[:10], 1):
            print(f"  {i}. {item.get('name', 'N/A')}")
        if len(result.data) > 10:
            print(f"  ... and {len(result.data) - 10} more")

    if result.error:
        print(f"\nError: {result.error}")
