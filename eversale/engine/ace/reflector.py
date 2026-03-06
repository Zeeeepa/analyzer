"""
Post-task reflection system for extracting learnings from task execution.
Analyzes conversation history to identify novel strategies worth preserving.
"""

import re
from typing import List, Dict, Optional, Tuple
from loguru import logger
from .playbook import Strategy


class Reflector:
    """
    Analyzes task execution to extract learned strategies.
    Uses lightweight heuristics instead of separate LLM calls to minimize overhead.
    """

    # Action types that warrant reflection (complex decisions)
    COMPLEX_ACTIONS = {
        'search', 'extract_contacts', 'navigate_to_profile',
        'fill_form', 'handle_popup', 'handle_error', 'handle_captcha',
        'handle_login', 'filter', 'export'
    }

    # Simple actions we skip (too trivial to learn from)
    SIMPLE_ACTIONS = {
        'click', 'type', 'scroll', 'wait', 'screenshot', 'hover'
    }

    # Quality filters - strategies must meet these criteria
    MIN_STRATEGY_LENGTH = 20  # Minimum characters for specificity
    MIN_STRATEGY_LENGTH_TRAINING = 15  # Looser for training mode
    VAGUE_PHRASES = [
        'try clicking', 'maybe', 'probably', 'just click', 'use the button',
        'it works', 'try it', 'do this', 'check if', 'see if'
    ]
    REQUIRED_SPECIFICITY_MARKERS = [
        # At least one of these should be present for quality
        'selector', 'class=', 'id=', 'css', 'xpath',  # Selectors
        'wait', 'timeout', 'seconds', 'ms',  # Timing
        'before', 'after', 'then', 'first', 'instead',  # Ordering
        'filter', 'search', 'input', 'button', 'form',  # Elements
        'http', 'url', 'navigate', 'page',  # Navigation
        'error', 'failed', '429', '404', 'timeout',  # Errors
        # Additional markers for training mode (more permissive)
        'click', 'scroll', 'extract', 'data', 'text', 'element',
        'reddit', 'linkedin', 'facebook', 'ads', 'library',
        'found', 'success', 'works', 'better', 'faster',
    ]

    # Training mode flag - set externally to learn more
    training_mode = False

    def __init__(self):
        self.reflection_count = 0

    def reflect_on_task(
        self,
        conversation_history: List[Dict],
        task_success: bool,
        user_prompt: str
    ) -> List[Tuple[str, str, str, str]]:
        """
        Analyze task execution and extract learnings.

        Args:
            conversation_history: List of conversation turns (user, assistant, tool)
            task_success: Whether the overall task succeeded
            user_prompt: Original user request

        Returns:
            List of (domain, action_type, strategy, marker) tuples
        """
        learnings = []

        # Extract domain from task
        domain = self._extract_domain(conversation_history, user_prompt)

        # Analyze tool usage patterns
        tool_sequences = self._extract_tool_sequences(conversation_history)

        # Find patterns in successful vs failed tool calls
        for tool_name, tool_calls in tool_sequences.items():
            action_type = self._classify_action_type(tool_name, tool_calls)

            # Skip simple actions
            if action_type in self.SIMPLE_ACTIONS:
                continue

            # Extract patterns from this tool's usage
            patterns = self._extract_patterns(
                tool_name, tool_calls, task_success, conversation_history
            )

            for strategy, marker in patterns:
                learnings.append((domain, action_type, strategy, marker))

        # Analyze error recovery patterns if task succeeded after errors
        if task_success:
            error_learnings = self._extract_error_recovery_patterns(
                conversation_history, domain
            )
            learnings.extend(error_learnings)

        self.reflection_count += 1
        logger.info(f"Reflection #{self.reflection_count}: Extracted {len(learnings)} learnings")

        return learnings

    def _extract_domain(self, conversation_history: List[Dict], user_prompt: str) -> str:
        """Extract the primary domain from navigation actions."""
        # Look for navigate tool calls
        for turn in conversation_history:
            if turn.get('role') == 'tool' and 'navigate' in turn.get('tool', '').lower():
                content = turn.get('content', '')
                # Extract domain from URL
                match = re.search(r'https?://(?:www\.)?([^/]+)', content)
                if match:
                    domain = match.group(1)
                    # Simplify common domains
                    domain = domain.replace('www.', '')
                    return domain

        # Fallback: look for domain mentions in user prompt
        common_domains = ['linkedin.com', 'facebook.com', 'apollo.io', 'twitter.com', 'reddit.com']
        user_prompt_lower = user_prompt.lower()

        for domain in common_domains:
            if domain.split('.')[0] in user_prompt_lower:
                return domain

        # Default to wildcard if no domain found
        return '*'

    def _extract_tool_sequences(self, conversation_history: List[Dict]) -> Dict[str, List[Dict]]:
        """Group tool calls by tool name."""
        sequences = {}

        for turn in conversation_history:
            if turn.get('role') == 'tool':
                tool_name = turn.get('tool', '')
                if tool_name not in sequences:
                    sequences[tool_name] = []
                sequences[tool_name].append(turn)

        return sequences

    def _classify_action_type(self, tool_name: str, tool_calls: List[Dict]) -> str:
        """Classify tool usage into action type."""
        tool_name_lower = tool_name.lower()

        # Map tool names to action types
        if 'navigate' in tool_name_lower:
            return 'navigate'
        elif 'click' in tool_name_lower:
            return 'click'
        elif 'fill' in tool_name_lower or 'type' in tool_name_lower:
            return 'fill_form'
        elif 'screenshot' in tool_name_lower:
            return 'screenshot'
        elif 'scroll' in tool_name_lower:
            return 'scroll'
        elif 'save_contact' in tool_name_lower:
            return 'extract_contacts'
        elif 'search' in tool_name_lower:
            return 'search'
        elif 'evaluate' in tool_name_lower:
            # Check if used for extraction or manipulation
            if any('extract' in str(call).lower() for call in tool_calls):
                return 'extract_contacts'
            return 'handle_popup'
        else:
            return 'wait'

    def _extract_patterns(
        self,
        tool_name: str,
        tool_calls: List[Dict],
        task_success: bool,
        conversation_history: List[Dict]
    ) -> List[Tuple[str, str]]:
        """
        Extract strategy patterns from tool usage.
        Returns list of (strategy_text, marker) tuples.
        """
        patterns = []

        # Pattern 1: Successful selector patterns
        if 'click' in tool_name.lower() or 'fill' in tool_name.lower():
            successful_selectors = self._extract_successful_selectors(tool_calls)
            if successful_selectors and task_success:
                for selector in successful_selectors:
                    strategy = f"Use selector '{selector}' for reliable element targeting"
                    patterns.append((strategy, '✓'))

        # Pattern 2: Error recovery patterns
        error_patterns = self._find_error_recovery_patterns(tool_calls)
        for pattern in error_patterns:
            patterns.append((pattern, '✓'))

        # Pattern 3: Failed approaches (if task failed)
        if not task_success:
            failed_patterns = self._extract_failed_patterns(tool_calls, conversation_history)
            for pattern in failed_patterns:
                patterns.append((pattern, '✗'))

        return patterns

    def _extract_successful_selectors(self, tool_calls: List[Dict]) -> List[str]:
        """Extract CSS selectors that worked."""
        selectors = []

        for call in tool_calls:
            content = str(call.get('content', ''))

            # Skip if this call had an error
            if 'error' in content.lower() or 'failed' in content.lower():
                continue

            # Extract selector from content
            # Look for common patterns like: selector: "...", css: "...", etc.
            matches = re.findall(r'(?:selector|css)["\s:]+([^"]+)["\s]', content, re.IGNORECASE)
            selectors.extend(matches)

        return selectors[:3]  # Return top 3 to avoid bloat

    def _find_error_recovery_patterns(self, tool_calls: List[Dict]) -> List[str]:
        """Identify patterns where errors were successfully recovered."""
        patterns = []

        for i, call in enumerate(tool_calls):
            content = str(call.get('content', ''))

            # Check if this call had an error
            if 'error' in content.lower() or 'failed' in content.lower():
                # Check if next call succeeded
                if i + 1 < len(tool_calls):
                    next_content = str(tool_calls[i + 1].get('content', ''))
                    if 'error' not in next_content.lower():
                        # Extract what changed
                        recovery_strategy = self._compare_calls(call, tool_calls[i + 1])
                        if recovery_strategy:
                            patterns.append(recovery_strategy)

        return patterns

    def _compare_calls(self, failed_call: Dict, success_call: Dict) -> Optional[str]:
        """Compare failed and successful calls to extract recovery pattern."""
        failed_content = str(failed_call.get('content', ''))
        success_content = str(success_call.get('content', ''))

        # Simple heuristic: if successful call has different selector/approach
        if 'selector' in success_content.lower():
            return "If initial selector fails, try alternative selector approach"

        if 'wait' in success_content.lower() or 'sleep' in success_content.lower():
            return "Add wait time before retry when element not immediately available"

        return None

    def _extract_failed_patterns(
        self,
        tool_calls: List[Dict],
        conversation_history: List[Dict]
    ) -> List[str]:
        """Extract patterns that led to failure."""
        patterns = []

        # Count repeated failures
        error_counts = {}
        for call in tool_calls:
            content = str(call.get('content', ''))
            if 'error' in content.lower():
                # Extract error type
                error_type = self._extract_error_type(content)
                error_counts[error_type] = error_counts.get(error_type, 0) + 1

        # Patterns from repeated errors
        for error_type, count in error_counts.items():
            if count >= 3:
                patterns.append(f"Avoid repeated {error_type} - try different approach after 2 failures")

        return patterns

    def _extract_error_type(self, content: str) -> str:
        """Extract error type from error message."""
        content_lower = content.lower()

        if 'timeout' in content_lower:
            return 'timeout errors'
        elif 'not found' in content_lower or 'no element' in content_lower:
            return 'element not found errors'
        elif 'rate limit' in content_lower or '429' in content:
            return 'rate limit errors'
        elif 'captcha' in content_lower:
            return 'CAPTCHA challenges'
        else:
            return 'errors'

    def _extract_error_recovery_patterns(
        self,
        conversation_history: List[Dict],
        domain: str
    ) -> List[Tuple[str, str, str, str]]:
        """Extract patterns where errors were successfully resolved."""
        patterns = []

        # Track error -> recovery sequences
        error_indices = []
        for i, turn in enumerate(conversation_history):
            if turn.get('role') == 'tool':
                content = str(turn.get('content', ''))
                if 'error' in content.lower():
                    error_indices.append(i)

        # For each error, check if task eventually succeeded
        for error_idx in error_indices:
            # Look at next few turns to see recovery
            recovery_window = conversation_history[error_idx:error_idx + 5]

            for turn in recovery_window:
                if turn.get('role') == 'tool' and 'error' not in str(turn.get('content', '')).lower():
                    # Found recovery - extract strategy
                    tool_name = turn.get('tool', '')
                    action_type = self._classify_action_type(tool_name, [turn])

                    strategy = f"After error, retry with {tool_name} tool succeeded"
                    patterns.append((domain, action_type, strategy, '✓'))
                    break

        return patterns

    def is_novel_strategy(self, strategy_text: str, existing_strategies: List[Strategy]) -> bool:
        """
        Check if a strategy is novel compared to existing ones.
        Uses simple text similarity to avoid duplicates.
        """
        if not existing_strategies:
            return True

        # Normalize for comparison
        normalized_new = strategy_text.lower().strip()

        for existing in existing_strategies:
            normalized_existing = existing.strategy.lower().strip()

            # Check for exact match
            if normalized_new == normalized_existing:
                return False

            # Check for high similarity (>80% overlap)
            similarity = self._text_similarity(normalized_new, normalized_existing)
            if similarity > 0.8:
                return False

        return True

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple word overlap similarity."""
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        overlap = len(words1 & words2)
        total = len(words1 | words2)

        return overlap / total if total > 0 else 0.0

    def is_quality_strategy(self, strategy_text: str) -> bool:
        """
        Filter out vague, useless strategies that small models sometimes generate.

        Quality criteria:
        1. Minimum length (avoid "click button" type vagueness)
        2. No vague phrases like "try clicking" or "maybe"
        3. Contains specific markers (selectors, timing, concrete actions)

        In training_mode: More permissive to learn more patterns.

        Returns True if strategy meets quality threshold.
        """
        min_length = self.MIN_STRATEGY_LENGTH_TRAINING if self.training_mode else self.MIN_STRATEGY_LENGTH

        if not strategy_text or len(strategy_text) < min_length:
            logger.debug(f"Strategy too short ({len(strategy_text)} chars): {strategy_text[:30]}...")
            return False

        text_lower = strategy_text.lower()

        # Check for vague phrases (skip some checks in training mode)
        if not self.training_mode:
            for vague in self.VAGUE_PHRASES:
                if vague in text_lower:
                    logger.debug(f"Strategy contains vague phrase '{vague}': {strategy_text[:50]}...")
                    return False

        # Check for specificity markers
        has_specificity = any(marker in text_lower for marker in self.REQUIRED_SPECIFICITY_MARKERS)

        # In training mode, also accept strategies with action words
        if self.training_mode and not has_specificity:
            training_markers = ['go to', 'visit', 'click', 'type', 'extract', 'find', 'get', 'use']
            has_specificity = any(marker in text_lower for marker in training_markers)

        if not has_specificity:
            logger.debug(f"Strategy lacks specificity: {strategy_text[:50]}...")
            return False

        return True
