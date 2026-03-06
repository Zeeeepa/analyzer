"""
Page State Tracker - Delta compression for context efficiency

Instead of sending full accessibility tree every step (800+ tokens),
track changes and send only deltas (50-100 tokens).

Expected savings: 80% reduction in context per step.
"""

import difflib
from typing import Dict, Any, Optional, List
from loguru import logger


class PageStateTracker:
    """
    Tracks page state and computes minimal deltas

    Maintains previous state and only sends what changed to the LLM.
    """

    def __init__(self, max_elements: int = 20):
        self.previous_state = None
        self.previous_url = None
        self.previous_action = None
        self.max_elements = max_elements
        self.state_history = []  # Keep last 3 states for advanced diffing

    def get_compressed_state(
        self,
        current_state: str,
        current_url: str,
        current_action: Optional[str] = None
    ) -> str:
        """
        Get compressed state representation

        First call: Compressed full state (~300 tokens)
        Subsequent: Delta only (~50-100 tokens)

        Args:
            current_state: Full accessibility tree or page content
            current_url: Current page URL
            current_action: Action that was just executed

        Returns:
            Compressed state string for LLM context
        """

        # URL changed = new page, send compressed full state
        if current_url != self.previous_url:
            logger.info(f"URL changed: {self.previous_url} -> {current_url}")
            compressed = self._compress_full_state(current_state, current_url)
            self._update_state(current_state, current_url, current_action)
            return compressed

        # Same page = send delta
        if self.previous_state:
            delta = self._compute_delta(
                self.previous_state,
                current_state,
                current_action
            )
            self._update_state(current_state, current_url, current_action)
            return delta

        # First call ever
        compressed = self._compress_full_state(current_state, current_url)
        self._update_state(current_state, current_url, current_action)
        return compressed

    def _compress_full_state(self, state: str, url: str) -> str:
        """
        Compress full state to essentials only

        Extract only:
        - Interactive elements (buttons, links, inputs)
        - Visible text in headings
        - Form fields
        - Key landmarks

        Limit to top N most important elements
        """

        lines = state.split('\n')
        compressed_lines = []

        # Priority keywords for filtering
        high_priority = ['button', 'input', 'link', 'a href', 'form', 'select', 'textarea']
        medium_priority = ['heading', 'h1', 'h2', 'h3', 'nav', 'menu']

        # Extract high priority elements
        for line in lines:
            line_lower = line.lower()

            if any(keyword in line_lower for keyword in high_priority):
                compressed_lines.append(line)
            elif any(keyword in line_lower for keyword in medium_priority):
                if len(compressed_lines) < self.max_elements:
                    compressed_lines.append(line)

        # Limit to max elements
        compressed_lines = compressed_lines[:self.max_elements]

        # Build compressed representation
        header = f"=== PAGE: {url} ==="
        elements = f"Interactive elements ({len(compressed_lines)}):"
        body = '\n'.join(compressed_lines)

        result = f"{header}\n{elements}\n{body}"

        logger.debug(f"Compressed state: {len(state)} -> {len(result)} chars ({len(result)/len(state)*100:.1f}%)")

        return result

    def _compute_delta(
        self,
        old_state: str,
        new_state: str,
        action: Optional[str]
    ) -> str:
        """
        Compute minimal delta between states

        Focus on what changed after the action was executed.
        """

        # If states are identical, return minimal update
        if old_state == new_state:
            return f"Previous action: {action}\nResult: No changes detected (page unchanged)"

        # Compute line-by-line diff
        old_lines = old_state.split('\n')
        new_lines = new_state.split('\n')

        # Find added/removed/changed lines
        differ = difflib.Differ()
        diff = list(differ.compare(old_lines, new_lines))

        added = [line[2:] for line in diff if line.startswith('+ ')]
        removed = [line[2:] for line in diff if line.startswith('- ')]
        unchanged = [line[2:] for line in diff if line.startswith('  ')]

        # If diff is huge (page completely changed), treat as new page
        if len(added) + len(removed) > len(old_lines) * 0.7:
            logger.info("Major page change detected (>70% diff), sending compressed full state")
            return self._compress_full_state(new_state, self.previous_url or "")

        # Build delta summary
        summary_parts = [f"Previous action: {action}"]

        if added:
            summary_parts.append(f"\nAdded elements ({len(added)}):")
            # Show first 5 added items
            for item in added[:5]:
                if item.strip():
                    summary_parts.append(f"  + {item.strip()[:100]}")
            if len(added) > 5:
                summary_parts.append(f"  ... and {len(added) - 5} more")

        if removed:
            summary_parts.append(f"\nRemoved elements ({len(removed)}):")
            for item in removed[:5]:
                if item.strip():
                    summary_parts.append(f"  - {item.strip()[:100]}")
            if len(removed) > 5:
                summary_parts.append(f"  ... and {len(removed) - 5} more")

        if not added and not removed:
            summary_parts.append("\nResult: No significant changes")

        delta = '\n'.join(summary_parts)

        logger.debug(f"Delta: {len(old_state)} + {len(new_state)} -> {len(delta)} chars")

        return delta

    def _update_state(self, state: str, url: str, action: Optional[str]):
        """Update internal state tracking"""

        # Keep history of last 3 states
        if len(self.state_history) >= 3:
            self.state_history.pop(0)

        self.state_history.append({
            "state": state,
            "url": url,
            "action": action
        })

        self.previous_state = state
        self.previous_url = url
        self.previous_action = action

    def reset(self):
        """Reset tracker (e.g., for new task)"""

        self.previous_state = None
        self.previous_url = None
        self.previous_action = None
        self.state_history = []
        logger.info("Page state tracker reset")

    def get_summary(self) -> Dict[str, Any]:
        """Get tracking statistics"""

        return {
            "history_length": len(self.state_history),
            "current_url": self.previous_url,
            "last_action": self.previous_action
        }


class GroundedPrompter:
    """
    Generates grounded prompts with explicit choices

    Instead of free-form tool calling, give LLM multiple choice options.
    Model just outputs "A" instead of full JSON = 50x faster.
    """

    def __init__(self):
        pass

    def generate_grounded_prompt(
        self,
        goal: str,
        page_state: str,
        available_actions: List[Dict[str, Any]]
    ) -> str:
        """
        Generate prompt with A/B/C/D choices

        Args:
            goal: User's goal
            page_state: Current page state (compressed)
            available_actions: List of possible actions extracted from page

        Returns:
            Prompt with multiple choice format
        """

        # Limit to top 5 actions
        actions = available_actions[:5]

        choices = []
        for i, action in enumerate(actions):
            letter = chr(ord('A') + i)
            desc = self._format_action_description(action)
            choices.append(f"{letter}) {desc}")

        # Add "Other" option
        choices.append("E) Other action (specify)")

        prompt = f"""Goal: {goal}

Current page:
{page_state[:500]}

Available actions:
{chr(10).join(choices)}

Choose the best action (respond with letter ONLY):"""

        return prompt

    def _format_action_description(self, action: Dict[str, Any]) -> str:
        """Format action as human-readable description"""

        tool = action.get("tool", "")
        params = action.get("params", {})

        if tool == "playwright_click":
            selector = params.get("selector", "")
            return f"Click '{selector}'"

        elif tool == "playwright_fill":
            selector = params.get("selector", "")
            value = params.get("value", "")
            return f"Type '{value}' in '{selector}'"

        elif tool == "playwright_navigate":
            url = params.get("url", "")
            return f"Navigate to {url}"

        elif tool == "save_contact":
            name = params.get("name", "")
            return f"Save contact: {name}"

        else:
            return f"{tool}"

    def parse_choice(
        self,
        response: str,
        available_actions: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Parse letter choice to action

        Args:
            response: LLM response (should be "A", "B", "C", etc.)
            available_actions: Same list passed to generate_grounded_prompt

        Returns:
            Action dict or None if "E) Other"
        """

        # Extract first letter
        response_clean = response.strip().upper()
        if not response_clean:
            return None

        choice_letter = response_clean[0]

        # Map letter to index
        if choice_letter in ['A', 'B', 'C', 'D']:
            idx = ord(choice_letter) - ord('A')

            if idx < len(available_actions):
                return available_actions[idx]

        # "E" or invalid = return None (fall back to full parsing)
        return None
