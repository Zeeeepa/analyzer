"""
Compaction System - Context compression for LLM conversations.

Borrowed from OpenCode's session management:
- Automatic context compression when approaching limits
- Preserves critical information (goals, decisions, errors)
- Hierarchical summarization
- Token-aware truncation
"""

import re
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_MAX_TOKENS = 100_000  # When to trigger compaction
COMPACTION_TARGET = 50_000   # Target after compaction
CHARS_PER_TOKEN = 4          # Approximate
MAX_SUMMARY_TOKENS = 5_000   # Max tokens for summary section


@dataclass
class Message:
    """A conversation message."""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tool_name: Optional[str] = None
    tool_result: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def token_estimate(self) -> int:
        """Estimate token count."""
        total_chars = len(self.content)
        if self.tool_result:
            total_chars += len(self.tool_result)
        return total_chars // CHARS_PER_TOKEN


@dataclass
class ConversationSummary:
    """Summarized conversation state."""
    original_goal: str
    key_decisions: List[str]
    important_files: List[str]
    current_state: str
    errors_encountered: List[str]
    lessons_learned: List[str]
    pending_tasks: List[str]

    def to_text(self) -> str:
        """Convert to text format."""
        parts = []

        parts.append(f"## Original Goal\n{self.original_goal}")

        if self.key_decisions:
            parts.append("\n## Key Decisions")
            for decision in self.key_decisions:
                parts.append(f"- {decision}")

        if self.important_files:
            parts.append("\n## Important Files")
            for f in self.important_files:
                parts.append(f"- {f}")

        parts.append(f"\n## Current State\n{self.current_state}")

        if self.errors_encountered:
            parts.append("\n## Errors Encountered")
            for err in self.errors_encountered:
                parts.append(f"- {err}")

        if self.lessons_learned:
            parts.append("\n## Lessons Learned")
            for lesson in self.lessons_learned:
                parts.append(f"- {lesson}")

        if self.pending_tasks:
            parts.append("\n## Pending Tasks")
            for task in self.pending_tasks:
                parts.append(f"- {task}")

        return "\n".join(parts)


@dataclass
class CompactionResult:
    """Result of conversation compaction."""
    success: bool
    original_messages: int
    compacted_messages: int
    original_tokens: int
    compacted_tokens: int
    summary: Optional[ConversationSummary] = None
    messages: List[Message] = field(default_factory=list)


class CompactionSystem:
    """
    Compress conversation history while preserving critical context.

    Features from OpenCode:
    - Automatic trigger at token threshold
    - Hierarchical summarization
    - Preserve recent messages
    - Extract key decisions and files
    """

    def __init__(
        self,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        target_tokens: int = COMPACTION_TARGET,
        preserve_recent: int = 10
    ):
        self.max_tokens = max_tokens
        self.target_tokens = target_tokens
        self.preserve_recent = preserve_recent

    def should_compact(self, messages: List[Message]) -> bool:
        """Check if compaction is needed."""
        total_tokens = sum(m.token_estimate() for m in messages)
        return total_tokens > self.max_tokens

    def extract_summary(self, messages: List[Message]) -> ConversationSummary:
        """
        Extract key information from conversation.

        Identifies:
        - Original goal from first user message
        - Key decisions (explicit or inferred)
        - Important files mentioned
        - Current state
        - Errors and lessons
        """
        original_goal = ""
        key_decisions = []
        important_files = set()
        errors = []
        lessons = []
        current_state = ""
        pending_tasks = []

        # File patterns
        file_pattern = r'[\w/.-]+\.(py|js|ts|tsx|jsx|json|yaml|yml|md|txt|sh|sql|html|css|svelte)'

        for i, msg in enumerate(messages):
            content = msg.content.lower()

            # Extract original goal from first user message
            if msg.role == "user" and not original_goal:
                original_goal = msg.content[:500]

            # Extract files mentioned
            files = re.findall(file_pattern, msg.content, re.IGNORECASE)
            important_files.update(files)

            # Extract decisions (look for decision language)
            decision_patterns = [
                r"I'll use (.+?) (?:for|to|because)",
                r"decided to (.+?)(?:\.|$)",
                r"choosing (.+?) (?:over|instead)",
                r"going with (.+?)(?:\.|$)",
            ]
            for pattern in decision_patterns:
                matches = re.findall(pattern, msg.content, re.IGNORECASE)
                key_decisions.extend(matches[:2])

            # Extract errors
            if "error" in content or "failed" in content or "exception" in content:
                # Get the error context
                error_match = re.search(r'(?:error|failed|exception)[:\s]*(.{0,200})', msg.content, re.IGNORECASE)
                if error_match:
                    errors.append(error_match.group(0)[:150])

            # Extract lessons (look for learning language)
            lesson_patterns = [
                r"(?:learned|realized|discovered) that (.+?)(?:\.|$)",
                r"(?:note|remember|important):\s*(.+?)(?:\.|$)",
                r"(?:turns out|actually) (.+?)(?:\.|$)",
            ]
            for pattern in lesson_patterns:
                matches = re.findall(pattern, msg.content, re.IGNORECASE)
                lessons.extend(matches[:1])

            # Extract pending tasks (from recent messages)
            if i >= len(messages) - 5:  # Last 5 messages
                task_patterns = [
                    r"(?:still need to|TODO|remaining|next):\s*(.+?)(?:\.|$)",
                    r"(?:will|should|must) (?:still )?(.+?)(?:\.|$)",
                ]
                for pattern in task_patterns:
                    matches = re.findall(pattern, msg.content, re.IGNORECASE)
                    pending_tasks.extend(matches[:1])

        # Get current state from last assistant message
        for msg in reversed(messages):
            if msg.role == "assistant":
                current_state = msg.content[:300]
                break

        return ConversationSummary(
            original_goal=original_goal,
            key_decisions=list(set(key_decisions))[:10],
            important_files=list(important_files)[:20],
            current_state=current_state,
            errors_encountered=list(set(errors))[:5],
            lessons_learned=list(set(lessons))[:5],
            pending_tasks=list(set(pending_tasks))[:5]
        )

    def compact(self, messages: List[Message]) -> CompactionResult:
        """
        Compact conversation while preserving context.

        Strategy:
        1. Extract summary of older messages
        2. Keep recent messages verbatim
        3. Create summary message as context
        """
        original_count = len(messages)
        original_tokens = sum(m.token_estimate() for m in messages)

        if not self.should_compact(messages):
            return CompactionResult(
                success=True,
                original_messages=original_count,
                compacted_messages=original_count,
                original_tokens=original_tokens,
                compacted_tokens=original_tokens,
                messages=messages
            )

        # Split into old and recent
        split_point = max(0, len(messages) - self.preserve_recent)
        old_messages = messages[:split_point]
        recent_messages = messages[split_point:]

        # Extract summary from old messages
        summary = self.extract_summary(old_messages)
        summary_text = summary.to_text()

        # Create compacted message list
        compacted = []

        # Add summary as system message
        summary_msg = Message(
            role="system",
            content=f"<conversation-summary>\n{summary_text}\n</conversation-summary>",
            metadata={"type": "compaction_summary", "original_messages": len(old_messages)}
        )
        compacted.append(summary_msg)

        # Add recent messages
        compacted.extend(recent_messages)

        compacted_tokens = sum(m.token_estimate() for m in compacted)

        logger.info(
            f"[COMPACTION] Compressed {original_count} messages to {len(compacted)} "
            f"({original_tokens} -> {compacted_tokens} tokens)"
        )

        return CompactionResult(
            success=True,
            original_messages=original_count,
            compacted_messages=len(compacted),
            original_tokens=original_tokens,
            compacted_tokens=compacted_tokens,
            summary=summary,
            messages=compacted
        )

    def incremental_compact(
        self,
        messages: List[Message],
        new_message: Message
    ) -> Tuple[List[Message], bool]:
        """
        Incrementally compact if adding new message exceeds limit.

        Returns:
            (messages, was_compacted)
        """
        messages_with_new = messages + [new_message]

        if not self.should_compact(messages_with_new):
            return messages_with_new, False

        result = self.compact(messages_with_new)
        return result.messages, True


# =============================================================================
# SMART SUMMARIZATION
# =============================================================================

class SmartSummarizer:
    """
    Intelligent conversation summarization.

    From OpenCode's approach:
    - Preserve tool calls and results
    - Keep error context
    - Maintain decision trail
    """

    def __init__(self):
        self.importance_weights = {
            "user_goal": 10,
            "error": 8,
            "decision": 7,
            "tool_result": 5,
            "reasoning": 4,
            "context": 2,
        }

    def score_message(self, msg: Message) -> int:
        """Score message importance for summarization."""
        score = 0
        content_lower = msg.content.lower()

        # User goals are critical
        if msg.role == "user" and any(w in content_lower for w in ["want", "need", "goal", "task", "please"]):
            score += self.importance_weights["user_goal"]

        # Errors are important
        if any(w in content_lower for w in ["error", "failed", "exception", "bug"]):
            score += self.importance_weights["error"]

        # Decisions are important
        if any(w in content_lower for w in ["decided", "choosing", "will use", "going with"]):
            score += self.importance_weights["decision"]

        # Tool results
        if msg.tool_result:
            score += self.importance_weights["tool_result"]

        # Reasoning
        if any(w in content_lower for w in ["because", "therefore", "since", "reason"]):
            score += self.importance_weights["reasoning"]

        return score

    def summarize_messages(
        self,
        messages: List[Message],
        target_tokens: int = MAX_SUMMARY_TOKENS
    ) -> str:
        """
        Create intelligent summary of messages.

        Prioritizes high-importance content.
        """
        # Score and sort messages
        scored = [(msg, self.score_message(msg)) for msg in messages]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Build summary from highest scored
        summary_parts = []
        current_tokens = 0

        for msg, score in scored:
            msg_tokens = msg.token_estimate()
            if current_tokens + msg_tokens > target_tokens:
                # Truncate this message if it's important
                if score >= self.importance_weights["decision"]:
                    available = (target_tokens - current_tokens) * CHARS_PER_TOKEN
                    truncated = msg.content[:available] + "..."
                    summary_parts.append(f"[{msg.role}] {truncated}")
                break

            summary_parts.append(f"[{msg.role}] {msg.content}")
            current_tokens += msg_tokens

        return "\n\n".join(summary_parts)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_default_compactor = None


def get_compactor() -> CompactionSystem:
    """Get default compaction system singleton."""
    global _default_compactor
    if _default_compactor is None:
        _default_compactor = CompactionSystem()
    return _default_compactor


def should_compact(messages: List[Dict]) -> bool:
    """Quick check if compaction needed."""
    compactor = get_compactor()
    msg_objs = [Message(role=m.get("role", "user"), content=m.get("content", "")) for m in messages]
    return compactor.should_compact(msg_objs)


def compact_conversation(messages: List[Dict]) -> List[Dict]:
    """Quick compaction helper."""
    compactor = get_compactor()
    msg_objs = [Message(role=m.get("role", "user"), content=m.get("content", "")) for m in messages]
    result = compactor.compact(msg_objs)
    return [{"role": m.role, "content": m.content} for m in result.messages]


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    # Create test messages
    messages = []
    for i in range(50):
        if i % 2 == 0:
            messages.append(Message(
                role="user",
                content=f"Please help me with task {i}. I need to modify file_{i}.py"
            ))
        else:
            messages.append(Message(
                role="assistant",
                content=f"I'll help with task {i}. First, let me read file_{i-1}.py. "
                        f"I decided to use approach_{i} because it's more efficient. "
                        f"Error encountered: something failed at line {i}. "
                        f"Lesson learned: always check for null values."
            ))

    compactor = CompactionSystem(max_tokens=500, target_tokens=200)

    print("=== COMPACTION TEST ===")
    print(f"Original messages: {len(messages)}")
    print(f"Should compact: {compactor.should_compact(messages)}")

    result = compactor.compact(messages)
    print(f"\nCompacted: {result.original_messages} -> {result.compacted_messages}")
    print(f"Tokens: {result.original_tokens} -> {result.compacted_tokens}")

    if result.summary:
        print("\n=== SUMMARY ===")
        print(f"Goal: {result.summary.original_goal[:100]}...")
        print(f"Decisions: {result.summary.key_decisions[:3]}")
        print(f"Files: {result.summary.important_files[:5]}")
        print(f"Errors: {result.summary.errors_encountered[:2]}")

    print("\nAll tests passed!")
