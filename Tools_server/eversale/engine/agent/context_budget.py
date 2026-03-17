"""
Context Budget Manager
Actively monitors and manages context window usage.

Key features:
- Track token usage in real-time
- Compress context when approaching limits
- Prioritize recent/relevant memories
- Reset after N iterations (like Claude Code does every 20)
"""

# tiktoken is optional - use approximation if not available
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    tiktoken = None

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class ContextEntry:
    """A single entry in the context."""
    role: str  # system, user, assistant, tool
    content: str
    token_count: int
    timestamp: datetime = field(default_factory=datetime.now)
    importance: float = 1.0  # Higher = keep longer
    compressible: bool = True

@dataclass
class ContextBudget:
    """Current budget state."""
    max_tokens: int = 128000  # Default for most models
    current_tokens: int = 0
    warning_threshold: float = 0.7  # Warn at 70%
    compress_threshold: float = 0.85  # Compress at 85%
    iteration_count: int = 0
    max_iterations_before_reset: int = 20  # Claude Code pattern

class ContextBudgetManager:
    """
    Actively manages context to prevent degradation.

    Key insight from Claude Code: "Performance craters after 20 iterations.
    Fresh start = fresh code."

    Usage:
        budget = ContextBudgetManager(max_tokens=128000)
        budget.add_message({"role": "user", "content": "..."})

        if budget.should_compress():
            messages = budget.compress_context(messages)

        if budget.should_reset():
            summary = budget.create_reset_summary()
            # Start fresh with summary
    """

    def __init__(self, max_tokens: int = 128000, model: str = "gpt-4"):
        self.budget = ContextBudget(max_tokens=max_tokens)
        self.entries: List[ContextEntry] = []
        self.encoder = None
        if TIKTOKEN_AVAILABLE:
            try:
                self.encoder = tiktoken.encoding_for_model(model)
            except KeyError:
                logger.warning(f"Model '{model}' not found in tiktoken, falling back to cl100k_base encoding")
                try:
                    self.encoder = tiktoken.get_encoding("cl100k_base")
                except Exception as e:
                    logger.error(f"Failed to load cl100k_base encoding: {e}. Token counting will use approximation.")
                    self.encoder = None
            except Exception as e:
                logger.error(f"Unexpected error loading tiktoken encoder for model '{model}': {e}. Using approximation.")
                self.encoder = None

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if self.encoder:
            try:
                return len(self.encoder.encode(text))
            except Exception as e:
                logger.warning(f"Failed to encode text with tiktoken: {e}. Using approximation.")
        # Fallback: rough estimate (1 token ~ 4 chars)
        return len(text) // 4

    def add_message(self, message: Dict[str, str], importance: float = 1.0):
        """Add a message and track its tokens."""
        content = message.get("content", "")
        tokens = self.count_tokens(content)

        entry = ContextEntry(
            role=message.get("role", "user"),
            content=content,
            token_count=tokens,
            importance=importance,
            compressible=message.get("role") != "system"
        )

        self.entries.append(entry)
        self.budget.current_tokens += tokens
        self.budget.iteration_count += 1

        self._log_status()

    def _log_status(self):
        """Log current status."""
        usage = self.budget.current_tokens / self.budget.max_tokens
        if usage > self.budget.compress_threshold:
            logger.warning(f"[CONTEXT] {usage:.0%} used - COMPRESSION NEEDED")
        elif usage > self.budget.warning_threshold:
            logger.info(f"[CONTEXT] {usage:.0%} used - approaching limit")

    def should_compress(self) -> bool:
        """Should we compress the context?"""
        usage = self.budget.current_tokens / self.budget.max_tokens
        return usage > self.budget.compress_threshold

    def should_reset(self) -> bool:
        """Should we reset context (every 20 iterations)?"""
        return self.budget.iteration_count >= self.budget.max_iterations_before_reset

    def get_usage(self) -> Dict[str, Any]:
        """Get current usage stats."""
        return {
            "current_tokens": self.budget.current_tokens,
            "max_tokens": self.budget.max_tokens,
            "usage_percent": self.budget.current_tokens / self.budget.max_tokens,
            "iteration_count": self.budget.iteration_count,
            "entry_count": len(self.entries),
            "should_compress": self.should_compress(),
            "should_reset": self.should_reset()
        }

    def compress_context(self, messages: List[Dict],
                        keep_recent: int = 5,
                        summarize_fn = None) -> List[Dict]:
        """
        Compress context while preserving important information.

        Strategy:
        1. Keep system prompt
        2. Keep last N messages verbatim
        3. Summarize older messages
        """
        if len(messages) <= keep_recent + 1:
            return messages

        # Split: system + old + recent
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        if len(non_system) <= keep_recent:
            return messages

        old_msgs = non_system[:-keep_recent]
        recent_msgs = non_system[-keep_recent:]

        # Summarize old messages
        if summarize_fn:
            summary = summarize_fn(old_msgs)
        else:
            # Default: extract key points
            summary = self._default_summarize(old_msgs)

        summary_msg = {
            "role": "system",
            "content": f"[Previous context summary]\n{summary}"
        }

        # Recalculate tokens
        new_messages = system_msgs + [summary_msg] + recent_msgs
        self._recalculate_tokens(new_messages)

        logger.info(f"[CONTEXT] Compressed {len(messages)} -> {len(new_messages)} messages")
        return new_messages

    def _default_summarize(self, messages: List[Dict]) -> str:
        """Default summarization without LLM."""
        # Extract key information
        actions = []
        results = []

        for msg in messages:
            content = msg.get("content", "")[:200]
            role = msg.get("role", "")

            if role == "assistant":
                actions.append(f"- Agent: {content[:100]}...")
            elif role == "tool":
                results.append(f"- Result: {content[:100]}...")

        summary_parts = []
        if actions:
            summary_parts.append("Actions taken:\n" + "\n".join(actions[-5:]))
        if results:
            summary_parts.append("Key results:\n" + "\n".join(results[-5:]))

        return "\n\n".join(summary_parts) if summary_parts else "Previous conversation context"

    def _recalculate_tokens(self, messages: List[Dict]):
        """Recalculate token count after compression."""
        total = sum(self.count_tokens(m.get("content", "")) for m in messages)
        self.budget.current_tokens = total

    def create_reset_summary(self, messages: List[Dict],
                            goal: str = "",
                            summarize_fn = None) -> Dict:
        """
        Create a summary for fresh context restart.

        Returns a single message that captures:
        - Original goal
        - What was accomplished
        - Current state
        - What remains to be done
        """
        if summarize_fn:
            summary = summarize_fn(messages, goal)
        else:
            # Default summary
            summary = f"""
## Task Continuation Summary

**Original Goal**: {goal or "Complete the user task"}

**Progress So Far**:
- Completed {self.budget.iteration_count} iterations
- Processed {len(messages)} messages

**Current State**:
{self._extract_current_state(messages)}

**Remaining Work**:
Continue from where we left off.
"""

        # Reset counters
        self.budget.iteration_count = 0
        self.budget.current_tokens = 0
        self.entries.clear()

        return {
            "role": "system",
            "content": summary.strip()
        }

    def _extract_current_state(self, messages: List[Dict]) -> str:
        """Extract current state from recent messages."""
        recent = messages[-3:] if len(messages) >= 3 else messages
        state_parts = []

        for msg in recent:
            role = msg.get("role", "")
            content = msg.get("content", "")[:150]
            if role == "tool":
                state_parts.append(f"- Last tool result: {content}")
            elif role == "assistant":
                state_parts.append(f"- Last action: {content}")

        return "\n".join(state_parts) if state_parts else "No specific state captured"

    def get_priority_messages(self, messages: List[Dict],
                             budget_tokens: int) -> List[Dict]:
        """
        Select most important messages within token budget.

        Priority:
        1. System prompts (always keep)
        2. Most recent messages
        3. Messages with tool results
        4. User messages
        """
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        # Calculate available budget
        system_tokens = sum(self.count_tokens(m.get("content", "")) for m in system_msgs)
        available = budget_tokens - system_tokens

        # Add messages from most recent, track tokens
        selected = []
        used_tokens = 0

        for msg in reversed(other_msgs):
            tokens = self.count_tokens(msg.get("content", ""))
            if used_tokens + tokens <= available:
                selected.insert(0, msg)
                used_tokens += tokens
            else:
                break

        return system_msgs + selected


# Global instance
_budget: Optional[ContextBudgetManager] = None

def get_context_budget() -> ContextBudgetManager:
    """Get global context budget manager."""
    global _budget
    if _budget is None:
        _budget = ContextBudgetManager()
    return _budget
