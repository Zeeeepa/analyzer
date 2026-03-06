"""
Strategy injection for enhancing prompts with learned patterns.
Keeps injection compact (<200 tokens) to minimize overhead.
"""

from typing import List
from loguru import logger
from .playbook import Strategy


class StrategyInjector:
    """
    Injects relevant learned strategies into prompts.
    Formats strategies compactly to minimize token overhead.
    """

    # Hard cap to prevent token explosion even if config is wrong
    ABSOLUTE_MAX_TOKENS = 250

    def __init__(self, max_strategies: int = 5, max_tokens: int = 200):
        self.max_strategies = max_strategies
        # Enforce absolute maximum
        self.max_tokens = min(max_tokens, self.ABSOLUTE_MAX_TOKENS)

    def enhance_prompt(
        self,
        base_prompt: str,
        strategies: List[Strategy],
        domain: str,
        action_type: str
    ) -> str:
        """
        Enhance a prompt with relevant learned strategies.

        Args:
            base_prompt: Original prompt text
            strategies: Relevant strategies to inject
            domain: Current domain context
            action_type: Current action type

        Returns:
            Enhanced prompt with strategies injected
        """
        if not strategies:
            return base_prompt

        # Format strategies compactly
        strategy_section = self._format_strategies(strategies, domain, action_type)

        # Inject into prompt (add after system instructions, before task)
        enhanced = f"{base_prompt}\n\n{strategy_section}"

        return enhanced

    def _format_strategies(
        self,
        strategies: List[Strategy],
        domain: str,
        action_type: str
    ) -> str:
        """
        Format strategies into compact text section.
        Target: <200 tokens total, hard cap at 250 tokens.
        """
        # Build compact strategy list with budget enforcement
        lines = [
            f"## Learned Strategies for {domain} ({action_type})",
            ""
        ]

        # Add strategies one by one, checking token budget
        current_tokens = self.estimate_token_count("\n".join(lines))

        for strategy in strategies[:self.max_strategies]:
            # Format: "✓ Strategy text (success rate: 85%)"
            success_pct = int(strategy.success_rate * 100)
            line = f"{strategy.marker} {strategy.strategy} ({success_pct}% success)"

            # Check if adding this line would exceed budget
            new_total = current_tokens + self.estimate_token_count(line)

            if new_total > self.max_tokens:
                logger.debug(f"Token budget reached ({new_total} > {self.max_tokens}), stopping injection")
                break

            lines.append(line)
            current_tokens = new_total

        result = "\n".join(lines)

        # Final safety check - truncate if somehow over limit
        if self.estimate_token_count(result) > self.ABSOLUTE_MAX_TOKENS:
            logger.warning(f"Injection exceeded absolute max, truncating")
            # Fallback to ultra-compact format
            return self.create_compact_injection(strategies[:3])

        return result

    def format_strategies_for_display(self, strategies: List[Strategy]) -> str:
        """
        Format strategies for human-readable display.
        Used for debugging and playbook inspection.
        """
        if not strategies:
            return "No strategies available."

        lines = []
        for i, strategy in enumerate(strategies, 1):
            success_pct = int(strategy.success_rate * 100)
            usage_count = strategy.success_count + strategy.failure_count

            lines.append(
                f"{i}. [{strategy.marker}] {strategy.strategy}\n"
                f"   Domain: {strategy.domain} | Action: {strategy.action_type}\n"
                f"   Success: {success_pct}% ({strategy.success_count}✓ / {strategy.failure_count}✗) "
                f"| Used: {usage_count} times"
            )

        return "\n\n".join(lines)

    def inject_for_complex_action(
        self,
        system_prompt: str,
        strategies: List[Strategy],
        domain: str,
        action_type: str
    ) -> str:
        """
        Inject strategies specifically for complex actions.
        Adds context to the system prompt about learned patterns.
        """
        if not strategies:
            return system_prompt

        # Format strategies with more detailed guidance
        injection = self._format_detailed_strategies(strategies, domain, action_type)

        # Find appropriate injection point (before tool list or at end)
        if "Available tools:" in system_prompt:
            parts = system_prompt.split("Available tools:")
            return f"{parts[0]}\n\n{injection}\n\nAvailable tools:{parts[1]}"
        else:
            return f"{system_prompt}\n\n{injection}"

    def _format_detailed_strategies(
        self,
        strategies: List[Strategy],
        domain: str,
        action_type: str
    ) -> str:
        """Format strategies with detailed context for complex actions."""
        lines = [
            f"### Learned Patterns for {domain}",
            f"When performing '{action_type}' actions, apply these proven strategies:",
            ""
        ]

        for strategy in strategies[:self.max_strategies]:
            success_pct = int(strategy.success_rate * 100)

            if strategy.marker == '✓':
                prefix = "DO:"
            elif strategy.marker == '✗':
                prefix = "DON'T:"
            else:
                prefix = "NOTE:"

            lines.append(f"• {prefix} {strategy.strategy} (proven {success_pct}% effective)")

        return "\n".join(lines)

    def create_compact_injection(self, strategies: List[Strategy]) -> str:
        """
        Create ultra-compact strategy injection for token-constrained scenarios.
        Target: <100 tokens.
        """
        if not strategies:
            return ""

        # Group by marker
        helpful = [s for s in strategies if s.marker == '✓']
        harmful = [s for s in strategies if s.marker == '✗']

        lines = []

        if helpful:
            # Take top 3 helpful strategies
            top_helpful = sorted(helpful, key=lambda s: s.success_rate, reverse=True)[:3]
            lines.append("✓ DO: " + " | ".join(s.strategy for s in top_helpful))

        if harmful:
            # Take top 2 harmful patterns to avoid
            top_harmful = sorted(harmful, key=lambda s: s.failure_count, reverse=True)[:2]
            lines.append("✗ AVOID: " + " | ".join(s.strategy for s in top_harmful))

        return "\n".join(lines)

    def estimate_token_count(self, text: str) -> int:
        """
        Rough token count estimation (1 token ≈ 4 characters).
        Used to stay within token budget.
        """
        return len(text) // 4

    def inject_with_budget(
        self,
        base_prompt: str,
        strategies: List[Strategy],
        domain: str,
        action_type: str,
        token_budget: int = 200
    ) -> str:
        """
        Inject strategies while staying within token budget.
        Automatically reduces strategy count if needed.
        """
        # Try full injection first
        full_injection = self._format_strategies(strategies, domain, action_type)

        if self.estimate_token_count(full_injection) <= token_budget:
            return f"{base_prompt}\n\n{full_injection}"

        # Reduce strategies until we fit budget
        for count in range(self.max_strategies - 1, 0, -1):
            reduced_strategies = strategies[:count]
            injection = self._format_strategies(reduced_strategies, domain, action_type)

            if self.estimate_token_count(injection) <= token_budget:
                return f"{base_prompt}\n\n{injection}"

        # Fallback: use ultra-compact format
        compact = self.create_compact_injection(strategies[:3])
        return f"{base_prompt}\n\n{compact}"
