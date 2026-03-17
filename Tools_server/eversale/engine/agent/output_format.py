"""
Eversale CLI Output Format - Consistent output for browser automation.

Every tool call outputs in this format:
### Action
<what was done>

### Result
<outcome>

### Page state (if browser action)
- URL: <current url>
- Title: <page title>
"""

from typing import Dict, Any, Optional
from datetime import datetime


class OutputFormatter:
    """
    Consistent output formatting for all Eversale CLI actions.
    Clean, predictable format for browser automation results.
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self._action_count = 0

    def format_action(
        self,
        action: str,
        target: str = "",
        result: Dict[str, Any] = None,
        page_url: str = None,
        page_title: str = None,
        duration_ms: int = None,
        error: str = None
    ) -> str:
        """
        Format a single action output.

        Args:
            action: The action name (e.g., "navigate", "click", "type")
            target: The target (e.g., URL, selector, text)
            result: The result dict from the action
            page_url: Current page URL (for browser actions)
            page_title: Current page title (for browser actions)
            duration_ms: How long the action took
            error: Error message if action failed

        Returns:
            Formatted output string
        """
        self._action_count += 1
        lines = []

        # Action header
        lines.append(f"### Action")
        lines.append(self._format_action_line(action, target))
        lines.append("")

        # Result section
        if error:
            lines.append(f"### Error")
            lines.append(f"- {error}")
        elif result:
            lines.append(f"### Result")
            lines.extend(self._format_result(result))
        else:
            lines.append(f"### Result")
            lines.append("- success: true")

        # Page state (for browser actions)
        if page_url:
            lines.append("")
            lines.append(f"### Page state")
            lines.append(f"- URL: {page_url}")
            if page_title:
                lines.append(f"- Title: {page_title}")

        # Duration (optional)
        if duration_ms and duration_ms > 100:
            lines.append("")
            lines.append(f"[{duration_ms}ms]")

        return "\n".join(lines)

    def _format_action_line(self, action: str, target: str) -> str:
        """Format the action line with human-readable description."""
        action_verbs = {
            "navigate": "Navigated to",
            "click": "Clicked",
            "type": "Typed",
            "fill": "Filled",
            "press": "Pressed",
            "scroll": "Scrolled",
            "wait": "Waited",
            "snapshot": "Captured snapshot",
            "screenshot": "Took screenshot",
            "extract": "Extracted data",
            "evaluate": "Evaluated script",
            "select": "Selected",
            "hover": "Hovered over",
            "go_back": "Went back",
            "go_forward": "Went forward",
            "reload": "Reloaded page",
            "close": "Closed",
        }

        verb = action_verbs.get(action, action.replace("_", " ").capitalize())

        if target:
            # Truncate long targets
            display_target = target[:80] + "..." if len(target) > 80 else target
            return f"{verb}: {display_target}"
        return verb

    def _format_result(self, result: Dict[str, Any]) -> list:
        """Format result dict as clean lines."""
        lines = []

        # Handle common result fields
        if "success" in result:
            lines.append(f"- success: {str(result['success']).lower()}")

        if "data" in result and result["data"]:
            data = result["data"]
            if isinstance(data, list):
                lines.append(f"- items: {len(data)}")
                # Show first few items
                for i, item in enumerate(data[:3]):
                    if isinstance(item, dict):
                        preview = ", ".join(f"{k}={v}" for k, v in list(item.items())[:3])
                        lines.append(f"  [{i+1}] {preview[:60]}...")
                    else:
                        lines.append(f"  [{i+1}] {str(item)[:60]}...")
                if len(data) > 3:
                    lines.append(f"  ... and {len(data) - 3} more")
            elif isinstance(data, dict):
                for k, v in list(data.items())[:5]:
                    v_str = str(v)[:50] + "..." if len(str(v)) > 50 else str(v)
                    lines.append(f"- {k}: {v_str}")
            else:
                lines.append(f"- data: {str(data)[:100]}")

        if "count" in result:
            lines.append(f"- count: {result['count']}")

        if "url" in result and "success" not in result:
            lines.append(f"- url: {result['url']}")

        if "text" in result:
            text = result["text"]
            preview = text[:100] + "..." if len(text) > 100 else text
            lines.append(f"- text: {preview}")

        if "file" in result or "path" in result:
            path = result.get("file") or result.get("path")
            lines.append(f"- saved: {path}")

        # If no specific fields, show raw
        if not lines:
            for k, v in list(result.items())[:5]:
                if k not in ("success", "error"):
                    v_str = str(v)[:50] + "..." if len(str(v)) > 50 else str(v)
                    lines.append(f"- {k}: {v_str}")

        return lines if lines else ["- success: true"]

    def format_browser_action(
        self,
        action: str,
        code: str,
        page_url: str = None,
        page_title: str = None,
        result: Any = None,
        snapshot_yaml: str = None
    ) -> str:
        """
        Format browser action output.

        Args:
            action: Action name
            code: The browser action code/description
            page_url: Current page URL
            page_title: Current page title
            result: Return value if any
            snapshot_yaml: Page snapshot in YAML format
        """
        lines = []

        # Code section
        lines.append("### Ran Eversale action")
        lines.append(code)

        # Result section (if there's a return value)
        if result is not None:
            lines.append("")
            lines.append("### Result")
            if isinstance(result, (dict, list)):
                import json
                lines.append(json.dumps(result, indent=2, default=str)[:500])
            else:
                lines.append(str(result)[:500])

        # Page state
        if page_url:
            lines.append("")
            lines.append("### Page state")
            lines.append(f"- Page URL: {page_url}")
            if page_title:
                lines.append(f"- Page Title: {page_title}")

            # Snapshot
            if snapshot_yaml:
                lines.append("- Page Snapshot:")
                lines.append("```yaml")
                # Limit snapshot size
                snapshot_lines = snapshot_yaml.split("\n")[:50]
                lines.extend(snapshot_lines)
                if len(snapshot_yaml.split("\n")) > 50:
                    lines.append("... [truncated]")
                lines.append("```")

        return "\n".join(lines)

    def format_step(self, step_num: int, action: str, status: str = "running") -> str:
        """Format a step indicator."""
        icons = {
            "running": "*",
            "success": "+",
            "error": "x",
            "skipped": "-"
        }
        icon = icons.get(status, "*")
        return f"  {icon} [{step_num}] {action}"

    def format_completion(
        self,
        total_actions: int,
        duration_seconds: float,
        output_file: str = None,
        error: str = None
    ) -> str:
        """Format completion summary."""
        lines = []

        if error:
            lines.append(f"### Error")
            lines.append(f"- {error}")
        else:
            lines.append(f"### Complete")
            lines.append(f"- Actions: {total_actions}")

            if duration_seconds < 60:
                lines.append(f"- Duration: {duration_seconds:.1f}s")
            else:
                mins = int(duration_seconds // 60)
                secs = int(duration_seconds % 60)
                lines.append(f"- Duration: {mins}m {secs}s")

            if output_file:
                lines.append(f"- Output: {output_file}")

        return "\n".join(lines)


# Global formatter instance
_formatter = OutputFormatter()


def format_action(action: str, target: str = "", **kwargs) -> str:
    """Convenience function to format an action."""
    return _formatter.format_action(action, target, **kwargs)


def format_browser_action(action: str, code: str, **kwargs) -> str:
    """Convenience function to format a browser action."""
    return _formatter.format_browser_action(action, code, **kwargs)


def format_step(step_num: int, action: str, status: str = "running") -> str:
    """Convenience function to format a step."""
    return _formatter.format_step(step_num, action, status)


def format_completion(**kwargs) -> str:
    """Convenience function to format completion."""
    return _formatter.format_completion(**kwargs)
