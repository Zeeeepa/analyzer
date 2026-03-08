"""
Fast Mode Execution System

Bypasses LLM planning for simple browser actions to achieve 15-30x speedup.
Compares to Playwright MCP's instant execution by pattern matching common commands
and directly executing them without AI interpretation.

Architecture:
1. Pattern matching for simple actions (navigate, click, type, scroll, etc.)
2. Direct MCP tool calls without LLM overhead
3. Fallback to full LLM mode for complex/ambiguous tasks
4. Configurable via config.yaml or runtime flag

Speed Comparison:
- Playwright MCP: ~200ms per action (direct execution)
- Eversale (normal): ~3-6s per action (LLM planning + execution)
- Eversale (fast mode): ~200-500ms per action (pattern match + execution)

Result: 10-30x faster for simple tasks!
"""

import re
import time
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from loguru import logger
from rich.console import Console

console = Console()


@dataclass
class FastModeResult:
    """Result from fast mode execution attempt."""
    success: bool
    executed: bool  # True if fast mode handled it, False if needs LLM
    result: Optional[str] = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    action_type: str = "unknown"


class FastModeExecutor:
    """
    Fast mode executor that bypasses LLM planning for simple browser actions.

    Handles commands like:
    - "go to google.com" -> direct navigate
    - "click Login" -> direct click
    - "type hello in search box" -> direct type
    - "scroll down" -> direct scroll
    - "wait 2 seconds" -> direct wait

    Falls back to LLM for:
    - Complex multi-step tasks
    - Ambiguous commands
    - Tasks requiring reasoning
    - Unknown patterns
    """

    def __init__(self, mcp_client, enabled: bool = True, verbose: bool = False):
        """
        Initialize fast mode executor.

        Args:
            mcp_client: MCP client for tool calls
            enabled: Whether fast mode is enabled (default: True)
            verbose: Log all fast mode attempts
        """
        self.mcp = mcp_client
        self.enabled = enabled
        self.verbose = verbose
        self.stats = {
            'attempts': 0,
            'successes': 0,
            'fallbacks': 0,
            'errors': 0,
            'total_time_saved_ms': 0.0
        }

        # Import command parser for pattern matching
        try:
            from .command_parser import get_parser
            self.parser = get_parser()
            self.parser_available = True
        except ImportError:
            logger.warning("Command parser not available - fast mode limited")
            self.parser_available = False

    def _is_multi_task_prompt(self, prompt: str) -> bool:
        """
        Detect if prompt contains multiple distinct tasks.

        Multi-task prompts should go to LLM for proper planning, not fast mode.
        """
        prompt_lower = prompt.lower()

        # Count navigation keywords (go to, navigate, open, visit)
        nav_keywords = ['go to ', 'navigate to ', 'open ', 'visit ']
        nav_count = sum(prompt_lower.count(kw) for kw in nav_keywords)
        if nav_count > 1:
            return True

        # Count task indicators (numbered lists, semicolons between tasks)
        if prompt.count('. Go to ') >= 1 or prompt.count('; ') >= 2:
            return True

        # Check for numbered task list
        import re
        numbered_pattern = r'\d+\.\s+(go|click|type|search|find|navigate)'
        if len(re.findall(numbered_pattern, prompt_lower)) > 1:
            return True

        # Detect compound actions: "do X and Y", "do X then Y", "do X, Y"
        # Look for action verbs after conjunctions
        action_verbs = ['search', 'find', 'extract', 'output', 'get', 'click', 'type', 'scroll', 'select', 'tell', 'show', 'list', 'describe', 'give', 'return']
        compound_patterns = [' and ', ' then ', ', then ', ' after that ']

        for pattern in compound_patterns:
            if pattern in prompt_lower:
                # Check if there's an action verb after the conjunction
                parts = prompt_lower.split(pattern)
                if len(parts) > 1:
                    after_part = parts[1]
                    for verb in action_verbs:
                        if after_part.startswith(verb) or f' {verb} ' in after_part[:30]:
                            return True

        # Check prompt length - long prompts usually have multiple tasks
        if len(prompt) > 200:
            return True

        return False

    async def try_execute(self, prompt: str) -> FastModeResult:
        """
        Try to execute command in fast mode.

        Args:
            prompt: User command

        Returns:
            FastModeResult with execution details
        """
        start_time = time.time()
        self.stats['attempts'] += 1

        if not self.enabled:
            return FastModeResult(
                success=False,
                executed=False,
                result="Fast mode disabled"
            )

        if not self.parser_available:
            return FastModeResult(
                success=False,
                executed=False,
                result="Parser not available"
            )

        try:
            # Check for multi-task prompts (should go to LLM, not fast mode)
            if self._is_multi_task_prompt(prompt):
                if self.verbose:
                    logger.debug("Fast mode: Multi-task prompt detected - falling back to LLM")
                self.stats['fallbacks'] += 1
                return FastModeResult(
                    success=False,
                    executed=False,
                    result="Multi-task prompt requires LLM planning"
                )

            # Parse command
            action = self.parser.parse(prompt)

            # Check if we can handle it
            if action.confidence < 0.8:
                if self.verbose:
                    logger.debug(f"Fast mode: Low confidence ({action.confidence:.2f}) - falling back to LLM")
                self.stats['fallbacks'] += 1
                return FastModeResult(
                    success=False,
                    executed=False,
                    result=f"Low confidence: {action.confidence:.2f}",
                    action_type=action.action_type.value
                )

            # Execute action
            if self.verbose:
                console.print(f"[cyan]Fast mode: {action.action_type.value}[/cyan]")

            result = await self._execute_action(action)

            execution_time_ms = (time.time() - start_time) * 1000

            # Estimate time saved (typical LLM call: 2-5 seconds)
            estimated_llm_time_ms = 3000  # Conservative estimate
            time_saved_ms = max(0, estimated_llm_time_ms - execution_time_ms)
            self.stats['total_time_saved_ms'] += time_saved_ms

            if result:
                self.stats['successes'] += 1

                if self.verbose:
                    console.print(
                        f"[green]Fast mode success: {execution_time_ms:.0f}ms "
                        f"(saved ~{time_saved_ms:.0f}ms)[/green]"
                    )

                return FastModeResult(
                    success=True,
                    executed=True,
                    result=result,
                    execution_time_ms=execution_time_ms,
                    action_type=action.action_type.value
                )
            else:
                self.stats['fallbacks'] += 1
                return FastModeResult(
                    success=False,
                    executed=False,
                    result="Execution returned None",
                    action_type=action.action_type.value
                )

        except Exception as e:
            self.stats['errors'] += 1
            logger.warning(f"Fast mode error: {e}")
            return FastModeResult(
                success=False,
                executed=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000
            )

    async def _execute_action(self, action) -> Optional[str]:
        """
        Execute a parsed action via MCP.

        Args:
            action: ParsedAction from command parser

        Returns:
            Result string or None if failed
        """
        mcp_call = action.to_mcp_call()
        if not mcp_call:
            logger.debug(f"No MCP call available for action type: {action.action_type}")
            return None

        tool_name, params = mcp_call

        try:
            # Execute MCP tool call
            result = await self.mcp.call_tool(tool_name, params)

            # Format result
            if action.action_type.value == "navigate":
                return f"Navigated to {action.target}"
            elif action.action_type.value == "click":
                return f"Clicked {action.target}"
            elif action.action_type.value == "type":
                return f"Typed '{action.value}' in {action.target}"
            elif action.action_type.value == "scroll":
                direction = params.get('direction', 'down')
                return f"Scrolled {direction}"
            elif action.action_type.value == "wait":
                seconds = params.get('seconds', 2)
                return f"Waited {seconds} seconds"
            elif action.action_type.value == "screenshot":
                return "Took screenshot"
            elif action.action_type.value == "search":
                return f"Searched for '{action.value}'"
            elif action.action_type.value == "back":
                return "Navigated back"
            elif action.action_type.value == "forward":
                return "Navigated forward"
            elif action.action_type.value == "refresh":
                return "Refreshed page"
            elif action.action_type.value == "close":
                return "Closed browser/tab"
            elif action.action_type.value == "hover":
                return f"Hovered over {action.target}"
            elif action.action_type.value == "press_key":
                return f"Pressed {action.value} key"
            else:
                return f"Executed {action.action_type.value}"

        except Exception as e:
            logger.debug(f"MCP call failed: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get fast mode statistics."""
        if self.stats['attempts'] == 0:
            success_rate = 0.0
        else:
            success_rate = (self.stats['successes'] / self.stats['attempts']) * 100

        return {
            **self.stats,
            'success_rate_pct': round(success_rate, 1),
            'avg_time_saved_ms': (
                round(self.stats['total_time_saved_ms'] / self.stats['successes'], 0)
                if self.stats['successes'] > 0 else 0
            ),
            'enabled': self.enabled
        }

    def reset_stats(self):
        """Reset statistics."""
        self.stats = {
            'attempts': 0,
            'successes': 0,
            'fallbacks': 0,
            'errors': 0,
            'total_time_saved_ms': 0.0
        }


def should_use_fast_mode(prompt: str, config: Optional[Dict] = None) -> bool:
    """
    Determine if fast mode should be attempted for a prompt.

    Args:
        prompt: User command
        config: Optional config dict

    Returns:
        True if fast mode should be tried
    """
    # Check config
    if config:
        fast_mode_config = config.get('fast_mode', {})
        if not fast_mode_config.get('enabled', True):
            return False

    # Skip fast mode for obviously complex tasks
    complexity_indicators = [
        'and then',
        'after that',
        'followed by',
        'if ',
        'when ',
        'unless',
        'extract all',
        'scrape all',
        'loop through',
        'for each',
        'until',
        'while',
    ]

    prompt_lower = prompt.lower()
    for indicator in complexity_indicators:
        if indicator in prompt_lower:
            return False

    # Skip for multi-sentence prompts
    if len(prompt.split('.')) > 2:
        return False

    return True


# Singleton instance
_executor_instance = None


def get_fast_mode_executor(mcp_client, enabled: bool = True, verbose: bool = False) -> FastModeExecutor:
    """Get or create the singleton fast mode executor."""
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = FastModeExecutor(mcp_client, enabled=enabled, verbose=verbose)
    return _executor_instance


async def try_fast_mode(prompt: str, mcp_client, config: Optional[Dict] = None) -> FastModeResult:
    """
    Convenience function to try fast mode execution.

    Args:
        prompt: User command
        mcp_client: MCP client
        config: Optional config dict

    Returns:
        FastModeResult
    """
    if not should_use_fast_mode(prompt, config):
        return FastModeResult(
            success=False,
            executed=False,
            result="Complex task - skipping fast mode"
        )

    # Get config settings
    enabled = True
    verbose = False
    if config:
        fast_mode_config = config.get('fast_mode', {})
        enabled = fast_mode_config.get('enabled', True)
        verbose = fast_mode_config.get('verbose', False)

    executor = get_fast_mode_executor(mcp_client, enabled=enabled, verbose=verbose)
    return await executor.try_execute(prompt)


def try_fast(prompt: str) -> Optional[Dict[str, Any]]:
    """
    Quick pattern matcher - checks if prompt matches any fast mode pattern.
    Returns action dict if matched, None to fall back to LLM.

    This is a synchronous, lightweight check that doesn't execute anything.
    Use this to decide whether to use fast mode BEFORE creating MCP client.

    Args:
        prompt: User command

    Returns:
        Dict with action info if pattern matched, None otherwise
        Example: {'action': 'navigate', 'target': 'google.com', 'confidence': 0.95}

    Examples:
        >>> try_fast("go to google.com")
        {'action': 'navigate', 'target': 'https://google.com', 'confidence': 0.95}

        >>> try_fast("click the login button")
        {'action': 'click', 'target': 'login button', 'confidence': 0.85}

        >>> try_fast("complex multi-step task with reasoning")
        None  # Falls back to LLM
    """
    try:
        # Try relative import first, fall back to absolute
        try:
            from .command_parser import get_parser
        except ImportError:
            from command_parser import get_parser

        # Quick complexity check
        if not should_use_fast_mode(prompt):
            return None

        # Parse command
        parser = get_parser()
        action = parser.parse(prompt)

        # Check confidence
        if action.confidence < 0.8:
            return None

        # Return action info
        return {
            'action': action.action_type.value,
            'target': action.target,
            'value': action.value,
            'params': action.params,
            'confidence': action.confidence,
            'raw_text': action.raw_text
        }

    except Exception as e:
        logger.debug(f"try_fast error: {e}")
        return None
