"""
History Manager - Message History Truncation with Step Omission

Based on browser-use's message manager pattern, this module provides intelligent
history truncation to prevent context window overflow while preserving critical
information.

Features:
- Preserves first step (establishes context)
- Preserves last N steps (most relevant recent actions)
- Summarizes middle steps with count
- Content truncation for large outputs (60k char hard limit)
- Token savings estimation
- Integration with session_state.py and brain messages

Usage:
    from history_manager import HistoryManager

    manager = HistoryManager(max_history_items=20, always_keep_last=5)
    manager.add_step(step_data)
    truncated_history = manager.get_truncated_history()
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger


@dataclass
class StepData:
    """
    Represents a single step in the execution history.

    Attributes:
        role: Message role (user, assistant, tool, system)
        content: Message content
        timestamp: When the step occurred
        tool_name: Name of tool used (if role is 'tool')
        success: Whether the step succeeded (if applicable)
        metadata: Additional metadata (iteration, attempt, etc.)
    """
    role: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    tool_name: Optional[str] = None
    success: Optional[bool] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for messages list."""
        msg = {
            'role': self.role,
            'content': self.content
        }
        if self.tool_name:
            msg['name'] = self.tool_name
        return msg

    def estimate_tokens(self) -> int:
        """Estimate token count (rough approximation: 1 token per 4 chars)."""
        return len(self.content) // 4

    def truncate_content(self, max_chars: int = 60000) -> 'StepData':
        """
        Truncate content if it exceeds max_chars.

        Args:
            max_chars: Maximum characters to keep (default 60k)

        Returns:
            New StepData with truncated content
        """
        if len(self.content) <= max_chars:
            return self

        truncated_content = self.content[:max_chars]
        truncated_content += f"\n\n[... Content truncated - {len(self.content) - max_chars} chars omitted ...]"

        return StepData(
            role=self.role,
            content=truncated_content,
            timestamp=self.timestamp,
            tool_name=self.tool_name,
            success=self.success,
            metadata={**self.metadata, 'content_truncated': True}
        )


class HistoryManager:
    """
    Manages execution history with intelligent truncation.

    Uses browser-use's pattern:
    1. Always keep first step (establishes context)
    2. Always keep last N steps (most relevant)
    3. Summarize middle steps with count
    4. Truncate large content to prevent memory issues

    Example:
        Original: [step1, step2, step3, step4, step5, step6, step7, step8, step9, step10]
        With max_history_items=6, always_keep_last=3:
        Result: [step1, "... 6 previous steps omitted...", step8, step9, step10]
    """

    def __init__(
        self,
        max_history_items: int = 20,
        always_keep_first: bool = True,
        always_keep_last: int = 5,
        content_max_chars: int = 60000
    ):
        """
        Initialize history manager.

        Args:
            max_history_items: Maximum steps to keep in full detail (default 20)
            always_keep_first: Always preserve first step (default True)
            always_keep_last: Always preserve N most recent steps (default 5)
            content_max_chars: Hard limit for content truncation (default 60k)
        """
        self.max_history_items = max_history_items
        self.always_keep_first = always_keep_first
        self.always_keep_last = always_keep_last
        self.content_max_chars = content_max_chars

        # History storage
        self._history: List[StepData] = []

        # Statistics
        self._total_steps_added = 0
        self._total_chars_truncated = 0
        self._total_steps_omitted = 0

        logger.debug(f"HistoryManager initialized: max={max_history_items}, keep_last={always_keep_last}")

    def add_step(
        self,
        role: str,
        content: str,
        tool_name: Optional[str] = None,
        success: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add a new step to history.

        Args:
            role: Message role (user, assistant, tool, system)
            content: Message content
            tool_name: Name of tool used (if role is 'tool')
            success: Whether the step succeeded (if applicable)
            metadata: Additional metadata (iteration, attempt, etc.)
        """
        step = StepData(
            role=role,
            content=content,
            tool_name=tool_name,
            success=success,
            metadata=metadata or {}
        )

        # Truncate content if too large
        if len(content) > self.content_max_chars:
            chars_removed = len(content) - self.content_max_chars
            step = step.truncate_content(self.content_max_chars)
            self._total_chars_truncated += chars_removed
            logger.warning(f"Content truncated: {chars_removed} chars removed (total truncated: {self._total_chars_truncated})")

        self._history.append(step)
        self._total_steps_added += 1

        logger.debug(f"Step added: {role} ({len(content)} chars) - total steps: {len(self._history)}")

    def add_step_from_dict(self, msg: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a step from a message dictionary.

        Args:
            msg: Message dictionary with 'role' and 'content' keys
            metadata: Additional metadata
        """
        self.add_step(
            role=msg.get('role', 'user'),
            content=msg.get('content', ''),
            tool_name=msg.get('name'),
            metadata=metadata
        )

    def get_truncated_history(self) -> List[Dict[str, Any]]:
        """
        Get history with middle steps summarized.

        Strategy:
        1. Keep first step (if always_keep_first is True)
        2. Keep last N steps (always_keep_last)
        3. Summarize middle steps with count

        Returns:
            List of message dictionaries suitable for LLM context
        """
        if len(self._history) <= self.max_history_items:
            # No truncation needed
            return [step.to_dict() for step in self._history]

        # Calculate truncation
        result = []
        omitted_count = 0

        if self.always_keep_first and len(self._history) > 0:
            # Add first step
            result.append(self._history[0].to_dict())

            # Calculate middle section to omit
            start_idx = 1
            end_idx = len(self._history) - self.always_keep_last

            if end_idx > start_idx:
                omitted_count = end_idx - start_idx
                self._total_steps_omitted = omitted_count

                # Add omission message
                omission_msg = self._format_omission_message(omitted_count)
                result.append(omission_msg)

                logger.info(f"History truncated: {omitted_count} steps omitted (keeping first + last {self.always_keep_last})")

            # Add last N steps
            for step in self._history[-self.always_keep_last:]:
                result.append(step.to_dict())
        else:
            # No first step preservation - just keep last N
            omitted_count = len(self._history) - self.always_keep_last
            if omitted_count > 0:
                self._total_steps_omitted = omitted_count
                omission_msg = self._format_omission_message(omitted_count)
                result.append(omission_msg)
                logger.info(f"History truncated: {omitted_count} steps omitted (keeping last {self.always_keep_last})")

            for step in self._history[-self.always_keep_last:]:
                result.append(step.to_dict())

        return result

    def _format_omission_message(self, omitted_count: int) -> Dict[str, Any]:
        """
        Format the omission message indicating steps were removed.

        Args:
            omitted_count: Number of steps that were omitted

        Returns:
            Message dictionary with omission notice
        """
        # Get summary of omitted section (tool names, success counts)
        start_idx = 1 if self.always_keep_first else 0
        end_idx = len(self._history) - self.always_keep_last
        omitted_steps = self._history[start_idx:end_idx]

        # Count tool calls and successes
        tool_calls = []
        success_count = 0
        failure_count = 0

        for step in omitted_steps:
            if step.tool_name:
                tool_calls.append(step.tool_name)
            if step.success is True:
                success_count += 1
            elif step.success is False:
                failure_count += 1

        # Build summary
        summary_parts = [f"[... {omitted_count} previous steps omitted...]"]

        if tool_calls:
            # Deduplicate and count
            from collections import Counter
            tool_counts = Counter(tool_calls)
            top_tools = tool_counts.most_common(5)
            tools_summary = ', '.join([f"{name} ({count}x)" for name, count in top_tools])
            summary_parts.append(f"Tools used: {tools_summary}")

        if success_count > 0 or failure_count > 0:
            summary_parts.append(f"Results: {success_count} succeeded, {failure_count} failed")

        content = '\n'.join(summary_parts)

        return {
            'role': 'system',
            'content': content
        }

    def get_full_history(self) -> List[Dict[str, Any]]:
        """
        Get complete history without truncation.

        Returns:
            List of all message dictionaries
        """
        return [step.to_dict() for step in self._history]

    def estimate_token_savings(self) -> Tuple[int, int, float]:
        """
        Estimate token savings from truncation.

        Returns:
            Tuple of (tokens_before, tokens_after, savings_percentage)
        """
        # Calculate tokens for full history
        tokens_before = sum(step.estimate_tokens() for step in self._history)

        # Calculate tokens for truncated history
        truncated = self.get_truncated_history()
        tokens_after = sum(len(msg['content']) // 4 for msg in truncated)

        # Calculate savings
        savings = 0.0
        if tokens_before > 0:
            savings = ((tokens_before - tokens_after) / tokens_before) * 100

        return tokens_before, tokens_after, savings

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about history management.

        Returns:
            Dictionary with statistics
        """
        tokens_before, tokens_after, savings_pct = self.estimate_token_savings()

        return {
            'total_steps': len(self._history),
            'total_steps_added': self._total_steps_added,
            'steps_in_truncated': len(self.get_truncated_history()),
            'steps_omitted': self._total_steps_omitted,
            'total_chars_truncated': self._total_chars_truncated,
            'estimated_tokens_before': tokens_before,
            'estimated_tokens_after': tokens_after,
            'estimated_savings_pct': round(savings_pct, 2),
            'config': {
                'max_history_items': self.max_history_items,
                'always_keep_first': self.always_keep_first,
                'always_keep_last': self.always_keep_last,
                'content_max_chars': self.content_max_chars
            }
        }

    def clear(self) -> None:
        """Clear all history."""
        self._history.clear()
        self._total_steps_omitted = 0
        logger.debug("History cleared")

    def reset_statistics(self) -> None:
        """Reset statistics counters (but keep history)."""
        self._total_steps_added = len(self._history)
        self._total_chars_truncated = 0
        self._total_steps_omitted = 0
        logger.debug("Statistics reset")

    def export_to_session_state(self, session_state) -> None:
        """
        Export history to SessionState format.

        Args:
            session_state: SessionState instance from session_state.py
        """
        for step in self._history:
            session_state.log_action(
                name=step.tool_name or step.role,
                args=step.metadata,
                success=step.success if step.success is not None else True,
                result=step.content if step.success else None,
                error=step.content if step.success is False else None
            )
        logger.debug(f"Exported {len(self._history)} steps to SessionState")

    def import_from_messages(self, messages: List[Dict[str, Any]]) -> None:
        """
        Import history from existing messages list.

        Args:
            messages: List of message dictionaries
        """
        self.clear()
        for msg in messages:
            self.add_step_from_dict(msg)
        logger.info(f"Imported {len(messages)} messages into HistoryManager")

    def __len__(self) -> int:
        """Return number of steps in history."""
        return len(self._history)

    def __repr__(self) -> str:
        """String representation."""
        stats = self.get_statistics()
        return (
            f"HistoryManager(steps={stats['total_steps']}, "
            f"omitted={stats['steps_omitted']}, "
            f"savings={stats['estimated_savings_pct']}%)"
        )


def truncate_content(text: str, max_chars: int = 60000) -> str:
    """
    Truncate content to maximum character length with warning.

    Args:
        text: Content to truncate
        max_chars: Maximum characters to keep (default 60k)

    Returns:
        Truncated content with notice if truncation occurred
    """
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    chars_removed = len(text) - max_chars
    truncated += f"\n\n[... Content truncated - {chars_removed} chars omitted ...]"

    logger.warning(f"Content truncated: {chars_removed} chars removed")
    return truncated


def format_omission_message(omitted_count: int) -> str:
    """
    Format a simple omission message.

    Args:
        omitted_count: Number of steps omitted

    Returns:
        Formatted omission message
    """
    return f"[... {omitted_count} previous steps omitted...]"


# Singleton instance for global access (optional)
_global_history_manager: Optional[HistoryManager] = None


def get_global_history_manager(
    max_history_items: int = 20,
    always_keep_first: bool = True,
    always_keep_last: int = 5
) -> HistoryManager:
    """
    Get or create global HistoryManager instance.

    Args:
        max_history_items: Maximum steps to keep (only used on first call)
        always_keep_first: Keep first step (only used on first call)
        always_keep_last: Keep last N steps (only used on first call)

    Returns:
        Global HistoryManager instance
    """
    global _global_history_manager

    if _global_history_manager is None:
        _global_history_manager = HistoryManager(
            max_history_items=max_history_items,
            always_keep_first=always_keep_first,
            always_keep_last=always_keep_last
        )
        logger.info("Global HistoryManager created")

    return _global_history_manager


def reset_global_history_manager() -> None:
    """Reset the global history manager (creates new instance on next access)."""
    global _global_history_manager
    _global_history_manager = None
    logger.info("Global HistoryManager reset")


# Alias for consistency with other modules
get_history_manager = get_global_history_manager
