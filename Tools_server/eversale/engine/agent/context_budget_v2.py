"""
Context Budget Manager v2 - Anchor + Sliding Window Pattern

Fixes the "amnesia bottleneck" by using a three-zone memory architecture:
1. ANCHOR ZONE - System prompt + original goal (NEVER compressed)
2. MILESTONE ZONE - Key discoveries, successes, state changes (compressed but preserved)
3. SLIDING WINDOW - Recent N messages (full detail)

This prevents:
- Goal amnesia (forgetting the original task)
- Milestone loss (forgetting important discoveries)
- Recent context loss (losing what just happened)

Based on research from Claude Code, Codex, and cognitive science:
- "Performance craters after 20 iterations" - Claude Code team
- Reset with summary preserves task continuity
- Anchor + Window pattern from transformer research

Key insight: The middle messages are least important. Compress/drop those first.
"""

import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple, Set, Callable
from datetime import datetime
from enum import Enum
import logging

# tiktoken is optional - use approximation if not available
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    tiktoken = None

logger = logging.getLogger(__name__)


class MessageImportance(Enum):
    """Importance levels for message retention."""
    CRITICAL = 1.0      # System prompt, original goal - NEVER drop
    MILESTONE = 0.8     # Key discoveries, state changes, successes
    NORMAL = 0.5        # Regular conversation turns
    LOW = 0.3           # Verbose tool outputs, debug info
    TRIVIAL = 0.1       # Can be dropped without loss


@dataclass
class ScoredMessage:
    """A message with retention scoring."""
    message: Dict[str, str]
    importance: MessageImportance
    token_count: int
    timestamp: datetime = field(default_factory=datetime.now)

    # Scores for retention decisions
    recency_score: float = 1.0       # Higher = more recent
    relevance_score: float = 0.5     # Higher = more relevant to current goal
    utility_score: float = 0.5       # Higher = more useful (tool results, discoveries)

    # Metadata
    is_anchor: bool = False          # Part of anchor zone (never drop)
    is_milestone: bool = False       # Important discovery/success
    is_tool_result: bool = False     # Contains tool output
    contains_data: bool = False      # Contains extracted data

    @property
    def composite_score(self) -> float:
        """Calculate composite retention score."""
        if self.is_anchor:
            return float('inf')  # Never drop anchors

        base = self.importance.value
        weighted = (
            0.3 * self.recency_score +
            0.4 * self.relevance_score +
            0.3 * self.utility_score
        )
        return base * weighted


@dataclass
class ContextZones:
    """The three zones of context management."""
    anchor: List[ScoredMessage]          # System + goal (fixed)
    milestones: List[ScoredMessage]      # Key discoveries (compressed)
    sliding_window: List[ScoredMessage]  # Recent messages (full)
    compressed_middle: Optional[str] = None  # Summary of dropped messages


@dataclass
class BudgetState:
    """Current budget state with detailed tracking."""
    max_tokens: int = 128000
    current_tokens: int = 0

    # Zone budgets (percentage of max)
    anchor_budget: float = 0.15       # 15% for system + goal
    milestone_budget: float = 0.20    # 20% for milestones
    window_budget: float = 0.50       # 50% for sliding window
    reserve_budget: float = 0.15      # 15% reserve for response

    # Thresholds
    warning_threshold: float = 0.70   # Warn at 70%
    compress_threshold: float = 0.85  # Compress at 85%

    # Iteration tracking
    iteration_count: int = 0
    max_iterations_before_reset: int = 20

    # Metrics
    compressions_performed: int = 0
    resets_performed: int = 0
    messages_dropped: int = 0
    tokens_saved: int = 0


class ContextBudgetManagerV2:
    """
    Advanced context budget manager with Anchor + Sliding Window pattern.

    Architecture:
    ```
    [ANCHOR ZONE]          [MILESTONE ZONE]       [SLIDING WINDOW]
    System prompt          Key discoveries         Recent N messages
    Original goal          State changes          Full detail
    Task parameters        Successes
    NEVER compressed       Compressed summary     NEVER compressed
    ```

    Usage:
        budget = ContextBudgetManagerV2(max_tokens=128000)

        # Add messages as they come
        budget.add_message({"role": "user", "content": "..."})

        # Check if management needed
        if budget.needs_management():
            messages = budget.manage_context(messages, goal="Find leads")

        # Periodic reset for long tasks
        if budget.should_reset():
            messages = budget.perform_reset(messages, goal="Find leads")
    """

    # Patterns that indicate milestone messages
    MILESTONE_PATTERNS = [
        r'\b(found|discovered|extracted|completed|success)\b',
        r'\b(logged in|authenticated|connected)\b',
        r'\b(saved|exported|downloaded)\b',
        r'\b(\d+)\s*(leads?|contacts?|results?|items?)\b',
        r'\b(error|failed|blocked)\b.*\b(because|due to)\b',
        r'✓|✔|success',
    ]

    # Patterns that indicate data-bearing messages
    DATA_PATTERNS = [
        r'@[\w.-]+\.[a-z]{2,}',  # Email
        r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',  # Phone
        r'https?://[^\s]+',  # URL
        r'"[^"]+"\s*:\s*"[^"]+"',  # JSON key-value
    ]

    # Patterns for low-importance content
    LOW_IMPORTANCE_PATTERNS = [
        r'^\[NAVIGATION\]',
        r'^\[DEBUG\]',
        r'^I\'ll now\b',
        r'^Let me\b',
        r'^I\'m going to\b',
    ]

    def __init__(
        self,
        max_tokens: int = 128000,
        model: str = "gpt-4",
        window_size: int = 10,
        milestone_capacity: int = 20
    ):
        """
        Initialize context budget manager.

        Args:
            max_tokens: Maximum context window size
            model: Model name for tokenization
            window_size: Number of recent messages to keep in full
            milestone_capacity: Maximum milestones to preserve
        """
        self.state = BudgetState(max_tokens=max_tokens)
        self.window_size = window_size
        self.milestone_capacity = milestone_capacity

        # Tokenizer
        self.encoder = None
        if TIKTOKEN_AVAILABLE:
            try:
                self.encoder = tiktoken.encoding_for_model(model)
            except Exception:
                try:
                    self.encoder = tiktoken.get_encoding("cl100k_base")
                except Exception:
                    pass

        # Zones
        self.zones = ContextZones(
            anchor=[],
            milestones=[],
            sliding_window=[]
        )

        # Goal tracking for relevance scoring
        self._current_goal: str = ""
        self._goal_keywords: Set[str] = set()

        # Milestone detection cache
        self._milestone_hashes: Set[str] = set()

        # LLM summarization function (can be injected)
        self._summarize_fn: Optional[Callable] = None

    def set_summarizer(self, fn: Callable[[List[Dict]], str]):
        """Set LLM-based summarization function."""
        self._summarize_fn = fn

    def set_goal(self, goal: str):
        """Set current goal for relevance scoring."""
        self._current_goal = goal
        self._goal_keywords = set(
            word.lower() for word in re.findall(r'\w+', goal)
            if len(word) > 3
        )

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if self.encoder:
            try:
                return len(self.encoder.encode(text))
            except Exception:
                pass
        # Fallback: rough estimate (1 token ~ 4 chars)
        return len(text) // 4

    def add_message(
        self,
        message: Dict[str, str],
        importance: Optional[MessageImportance] = None
    ) -> ScoredMessage:
        """
        Add a message with automatic importance scoring.

        Returns the scored message for inspection.
        """
        content = message.get("content", "")
        role = message.get("role", "user")
        tokens = self.count_tokens(content)

        # Auto-detect importance if not specified
        if importance is None:
            importance = self._detect_importance(message)

        scored = ScoredMessage(
            message=message,
            importance=importance,
            token_count=tokens,
            is_anchor=(role == "system"),
            is_milestone=self._is_milestone(content),
            is_tool_result=(role == "tool"),
            contains_data=self._contains_data(content)
        )

        # Calculate relevance to current goal
        scored.relevance_score = self._calculate_relevance(content)

        # Calculate utility (tool results and data are more useful)
        scored.utility_score = self._calculate_utility(scored)

        # Route to appropriate zone
        if scored.is_anchor:
            self.zones.anchor.append(scored)
        elif scored.is_milestone:
            self.zones.milestones.append(scored)
            # Trim milestones if over capacity
            if len(self.zones.milestones) > self.milestone_capacity:
                self._compress_milestones()
        else:
            self.zones.sliding_window.append(scored)

        # Update state
        self.state.current_tokens += tokens
        self.state.iteration_count += 1

        # Log status if approaching limits
        self._log_status()

        return scored

    def _detect_importance(self, message: Dict[str, str]) -> MessageImportance:
        """Auto-detect message importance."""
        role = message.get("role", "")
        content = message.get("content", "")

        # System messages are critical
        if role == "system":
            return MessageImportance.CRITICAL

        # First user message (goal) is critical
        if role == "user" and self.state.iteration_count == 0:
            return MessageImportance.CRITICAL

        # Check for milestone patterns
        for pattern in self.MILESTONE_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                return MessageImportance.MILESTONE

        # Check for low-importance patterns
        for pattern in self.LOW_IMPORTANCE_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                return MessageImportance.LOW

        # Tool results with data are important
        if role == "tool" and self._contains_data(content):
            return MessageImportance.MILESTONE

        # Default
        return MessageImportance.NORMAL

    def _is_milestone(self, content: str) -> bool:
        """Check if content represents a milestone."""
        # Check pattern
        for pattern in self.MILESTONE_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                return True

        # Check for substantial data
        if self._contains_data(content):
            return True

        return False

    def _contains_data(self, content: str) -> bool:
        """Check if content contains extracted data."""
        for pattern in self.DATA_PATTERNS:
            if re.search(pattern, content):
                return True
        return False

    def _calculate_relevance(self, content: str) -> float:
        """Calculate relevance to current goal (0-1)."""
        if not self._goal_keywords:
            return 0.5

        content_words = set(
            word.lower() for word in re.findall(r'\w+', content)
        )

        if not content_words:
            return 0.0

        overlap = len(content_words & self._goal_keywords)
        return min(1.0, overlap / max(1, len(self._goal_keywords) * 0.3))

    def _calculate_utility(self, scored: ScoredMessage) -> float:
        """Calculate utility score based on message characteristics."""
        utility = 0.5

        if scored.is_tool_result:
            utility += 0.2
        if scored.contains_data:
            utility += 0.3
        if scored.is_milestone:
            utility += 0.2

        return min(1.0, utility)

    def _log_status(self):
        """Log current status at thresholds."""
        usage = self.state.current_tokens / self.state.max_tokens

        if usage > self.state.compress_threshold:
            logger.warning(
                f"[CONTEXT] {usage:.0%} used ({self.state.current_tokens}/{self.state.max_tokens} tokens) - "
                f"COMPRESSION NEEDED"
            )
        elif usage > self.state.warning_threshold:
            logger.info(
                f"[CONTEXT] {usage:.0%} used - approaching limit"
            )

    def needs_management(self) -> bool:
        """Check if context management is needed."""
        usage = self.state.current_tokens / self.state.max_tokens
        return usage > self.state.compress_threshold

    def should_reset(self) -> bool:
        """Check if full reset is recommended (every 20 iterations)."""
        return self.state.iteration_count >= self.state.max_iterations_before_reset

    def get_usage(self) -> Dict[str, Any]:
        """Get detailed usage statistics."""
        return {
            "current_tokens": self.state.current_tokens,
            "max_tokens": self.state.max_tokens,
            "usage_percent": self.state.current_tokens / self.state.max_tokens,
            "iteration_count": self.state.iteration_count,
            "anchor_count": len(self.zones.anchor),
            "milestone_count": len(self.zones.milestones),
            "window_count": len(self.zones.sliding_window),
            "compressions": self.state.compressions_performed,
            "resets": self.state.resets_performed,
            "tokens_saved": self.state.tokens_saved,
            "should_compress": self.needs_management(),
            "should_reset": self.should_reset()
        }

    def manage_context(
        self,
        messages: List[Dict],
        goal: str = ""
    ) -> List[Dict]:
        """
        Apply Anchor + Sliding Window pattern to manage context.

        Strategy:
        1. Keep anchor zone (system + first user message) ALWAYS
        2. Keep sliding window (last N messages) ALWAYS
        3. Compress/drop middle messages based on importance
        4. Preserve milestones in compressed form

        Returns optimized message list.
        """
        if goal:
            self.set_goal(goal)

        if len(messages) <= self.window_size + 2:
            # Not enough messages to compress
            return messages

        original_count = len(messages)
        original_tokens = sum(self.count_tokens(m.get("content", "")) for m in messages)

        # Identify zones
        anchor_msgs = self._identify_anchors(messages)
        window_msgs = messages[-self.window_size:]
        middle_msgs = messages[len(anchor_msgs):-self.window_size] if len(messages) > self.window_size + len(anchor_msgs) else []

        # Score and sort middle messages
        scored_middle = [
            self._score_message_for_retention(msg)
            for msg in middle_msgs
        ]
        scored_middle.sort(key=lambda x: x.composite_score, reverse=True)

        # Calculate available budget for middle
        anchor_tokens = sum(self.count_tokens(m.get("content", "")) for m in anchor_msgs)
        window_tokens = sum(self.count_tokens(m.get("content", "")) for m in window_msgs)

        available_middle = int(
            self.state.max_tokens * (1 - self.state.reserve_budget) -
            anchor_tokens - window_tokens
        )

        # Keep high-scoring middle messages until budget exhausted
        kept_middle = []
        kept_tokens = 0
        dropped_messages = []

        for scored in scored_middle:
            if kept_tokens + scored.token_count <= available_middle:
                kept_middle.append(scored.message)
                kept_tokens += scored.token_count
            else:
                dropped_messages.append(scored.message)

        # Create compressed summary of dropped messages
        if dropped_messages:
            summary = self._create_summary(dropped_messages)
            summary_msg = {
                "role": "system",
                "content": f"[Compressed context - {len(dropped_messages)} messages summarized]\n{summary}"
            }
        else:
            summary_msg = None

        # Reconstruct message list
        result = anchor_msgs.copy()
        if summary_msg:
            result.append(summary_msg)
        result.extend(kept_middle)
        result.extend(window_msgs)

        # Update stats
        new_tokens = sum(self.count_tokens(m.get("content", "")) for m in result)
        self.state.tokens_saved += original_tokens - new_tokens
        self.state.messages_dropped += len(dropped_messages)
        self.state.compressions_performed += 1
        self.state.current_tokens = new_tokens

        logger.info(
            f"[CONTEXT] Managed: {original_count} -> {len(result)} messages, "
            f"{original_tokens} -> {new_tokens} tokens "
            f"({(original_tokens - new_tokens) / original_tokens:.0%} reduction)"
        )

        return result

    def _identify_anchors(self, messages: List[Dict]) -> List[Dict]:
        """Identify anchor messages that should never be dropped."""
        anchors = []

        for i, msg in enumerate(messages):
            role = msg.get("role", "")

            # System messages are always anchors
            if role == "system":
                anchors.append(msg)
            # First user message (original goal) is anchor
            elif role == "user" and i == 1:  # After system message
                anchors.append(msg)
            else:
                # Stop at first non-anchor
                break

        return anchors

    def _score_message_for_retention(self, message: Dict) -> ScoredMessage:
        """Score a message for retention priority."""
        content = message.get("content", "")
        role = message.get("role", "")
        tokens = self.count_tokens(content)

        importance = self._detect_importance(message)

        scored = ScoredMessage(
            message=message,
            importance=importance,
            token_count=tokens,
            is_milestone=self._is_milestone(content),
            is_tool_result=(role == "tool"),
            contains_data=self._contains_data(content),
            relevance_score=self._calculate_relevance(content)
        )

        scored.utility_score = self._calculate_utility(scored)

        return scored

    def _create_summary(self, messages: List[Dict]) -> str:
        """Create summary of compressed messages."""
        if self._summarize_fn:
            try:
                return self._summarize_fn(messages)
            except Exception as e:
                logger.warning(f"LLM summarization failed: {e}")

        # Default extractive summary
        return self._default_summarize(messages)

    def _default_summarize(self, messages: List[Dict]) -> str:
        """Default rule-based summarization."""
        actions = []
        results = []
        data_found = []

        for msg in messages:
            content = msg.get("content", "")
            role = msg.get("role", "")

            # Extract key information
            if role == "assistant":
                # Look for action descriptions
                action_match = re.search(r'(?:I\'ll|Let me|Going to)\s+([^.]+)', content)
                if action_match:
                    actions.append(action_match.group(1)[:80])

            elif role == "tool":
                # Look for results
                if "success" in content.lower() or "found" in content.lower():
                    results.append(content[:100])

                # Extract data patterns
                emails = re.findall(r'[\w.-]+@[\w.-]+\.\w+', content)
                if emails:
                    data_found.extend(emails[:3])

        # Build summary
        parts = []

        if actions:
            unique_actions = list(dict.fromkeys(actions))[:5]
            parts.append("Actions: " + "; ".join(unique_actions))

        if results:
            parts.append("Results: " + "; ".join(results[:3]))

        if data_found:
            parts.append(f"Data collected: {len(data_found)} items")

        return "\n".join(parts) if parts else "Previous conversation context"

    def _compress_milestones(self):
        """Compress milestone zone when over capacity."""
        if len(self.zones.milestones) <= self.milestone_capacity:
            return

        # Sort by composite score and keep top N
        self.zones.milestones.sort(key=lambda x: x.composite_score, reverse=True)
        dropped = self.zones.milestones[self.milestone_capacity:]
        self.zones.milestones = self.zones.milestones[:self.milestone_capacity]

        # Update compressed summary
        dropped_content = [m.message.get("content", "") for m in dropped]
        if self.zones.compressed_middle:
            dropped_content.insert(0, self.zones.compressed_middle)

        self.zones.compressed_middle = self._default_summarize(
            [{"content": c, "role": "system"} for c in dropped_content]
        )

    def perform_reset(
        self,
        messages: List[Dict],
        goal: str = "",
        progress_summary: str = ""
    ) -> List[Dict]:
        """
        Perform full context reset (every ~20 iterations).

        Creates a fresh context with:
        1. Original system prompt
        2. Summary of all progress so far
        3. Current state
        4. Remaining task
        """
        if goal:
            self.set_goal(goal)

        # Extract components
        system_msg = None
        original_goal_msg = None

        for msg in messages:
            if msg.get("role") == "system" and not system_msg:
                system_msg = msg
            elif msg.get("role") == "user" and not original_goal_msg:
                original_goal_msg = msg
                break

        # Create progress summary
        if not progress_summary:
            progress_summary = self._extract_progress(messages)

        # Create reset message
        reset_content = f"""## Task Continuation (Reset #{self.state.resets_performed + 1})

**Original Goal**: {goal or original_goal_msg.get('content', 'Complete the task')[:200] if original_goal_msg else 'Unknown'}

**Progress Summary**:
{progress_summary}

**Current State**:
{self._extract_current_state(messages)}

**Iteration**: {self.state.iteration_count} total steps completed

Continue the task from where we left off. Focus on completing any remaining objectives."""

        reset_msg = {
            "role": "user",
            "content": reset_content
        }

        # Build new message list
        result = []
        if system_msg:
            result.append(system_msg)
        result.append(reset_msg)

        # Keep last few messages for immediate context
        recent = messages[-3:] if len(messages) > 3 else []
        for msg in recent:
            if msg != system_msg:
                result.append(msg)

        # Update state
        self.state.resets_performed += 1
        self.state.iteration_count = 0
        old_tokens = self.state.current_tokens
        self.state.current_tokens = sum(
            self.count_tokens(m.get("content", "")) for m in result
        )
        self.state.tokens_saved += old_tokens - self.state.current_tokens

        # Clear zones
        self.zones.anchor.clear()
        self.zones.milestones.clear()
        self.zones.sliding_window.clear()
        self.zones.compressed_middle = None

        logger.info(
            f"[CONTEXT] Reset performed: {len(messages)} -> {len(result)} messages, "
            f"reset #{self.state.resets_performed}"
        )

        return result

    def _extract_progress(self, messages: List[Dict]) -> str:
        """Extract progress summary from message history."""
        progress_items = []

        for msg in messages:
            content = msg.get("content", "")

            # Look for success indicators
            if any(pattern in content.lower() for pattern in
                   ["found", "extracted", "completed", "success", "saved"]):
                # Extract the key finding
                for line in content.split("\n"):
                    if any(p in line.lower() for p in ["found", "extracted", "completed"]):
                        progress_items.append(f"- {line[:100]}")
                        break

        if not progress_items:
            return "- Task in progress, continuing from current state"

        return "\n".join(progress_items[:10])

    def _extract_current_state(self, messages: List[Dict]) -> str:
        """Extract current state from recent messages."""
        state_parts = []

        # Look at last 5 messages
        recent = messages[-5:] if len(messages) >= 5 else messages

        for msg in recent:
            role = msg.get("role", "")
            content = msg.get("content", "")[:200]

            if role == "tool":
                state_parts.append(f"- Last tool result: {content[:100]}")
            elif role == "assistant" and not content.startswith("["):
                state_parts.append(f"- Last action: {content[:100]}")

        return "\n".join(state_parts[-3:]) if state_parts else "No specific state captured"

    def reset_state(self):
        """Reset internal state for new task."""
        self.state = BudgetState(max_tokens=self.state.max_tokens)
        self.zones = ContextZones(anchor=[], milestones=[], sliding_window=[])
        self._current_goal = ""
        self._goal_keywords = set()
        self._milestone_hashes = set()


# ============================================================================
# INTEGRATION HELPERS
# ============================================================================

class ContextAwareExecutor:
    """
    Wraps execution with automatic context management.

    Usage:
        executor = ContextAwareExecutor(budget_manager)

        async def execute_task(messages, goal):
            with executor.manage(messages, goal) as managed_messages:
                result = await run_reasoning(managed_messages)
            return result
    """

    def __init__(self, budget_manager: ContextBudgetManagerV2):
        self.budget = budget_manager
        self._original_messages: List[Dict] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def prepare_context(
        self,
        messages: List[Dict],
        goal: str = ""
    ) -> List[Dict]:
        """Prepare context for LLM call, applying management if needed."""
        self._original_messages = messages.copy()

        if self.budget.should_reset():
            return self.budget.perform_reset(messages, goal)
        elif self.budget.needs_management():
            return self.budget.manage_context(messages, goal)
        else:
            return messages


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_budget_v2: Optional[ContextBudgetManagerV2] = None

def get_context_budget_v2() -> ContextBudgetManagerV2:
    """Get global context budget manager v2."""
    global _budget_v2
    if _budget_v2 is None:
        _budget_v2 = ContextBudgetManagerV2()
    return _budget_v2

def reset_context_budget_v2():
    """Reset global context budget manager."""
    global _budget_v2
    if _budget_v2:
        _budget_v2.reset_state()
