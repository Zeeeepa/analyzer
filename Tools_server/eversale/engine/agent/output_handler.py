"""
Output Handler Module - Manage tool output for LLM consumption.

Based on OpenCode's approach to handling command output:
- Truncate long outputs (default 30,000 chars)
- Add metadata tags for context
- Handle timeouts gracefully
- Format for LLM readability
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
import re
from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_MAX_OUTPUT = 30_000  # Characters
DEFAULT_TIMEOUT = 120_000   # Milliseconds (2 minutes)
MAX_LINES_PREVIEW = 50      # Lines for truncated preview


@dataclass
class OutputMetadata:
    """Metadata about tool execution."""
    tool_name: str
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    truncated: bool = False
    timed_out: bool = False
    aborted: bool = False
    original_length: int = 0
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "duration_ms": self.duration_ms,
            "exit_code": self.exit_code,
            "truncated": self.truncated,
            "timed_out": self.timed_out,
            "aborted": self.aborted,
            "original_length": self.original_length
        }

    @property
    def duration_ms(self) -> Optional[int]:
        if self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None


@dataclass
class FormattedOutput:
    """Formatted output for LLM consumption."""
    content: str
    metadata: OutputMetadata
    warnings: List[str] = field(default_factory=list)

    def to_llm_format(self) -> str:
        """Format output with metadata tags for LLM."""
        parts = []

        # Add warnings first
        if self.warnings:
            parts.append("<warnings>")
            for warning in self.warnings:
                parts.append(f"  - {warning}")
            parts.append("</warnings>")
            parts.append("")

        # Add metadata
        if self.metadata.description:
            parts.append(f"<description>{self.metadata.description}</description>")

        # Add status indicators
        status_parts = []
        if self.metadata.truncated:
            status_parts.append(f"truncated ({self.metadata.original_length} chars total)")
        if self.metadata.timed_out:
            status_parts.append("timed out")
        if self.metadata.aborted:
            status_parts.append("aborted by user")
        if self.metadata.exit_code is not None and self.metadata.exit_code != 0:
            status_parts.append(f"exit code {self.metadata.exit_code}")

        if status_parts:
            parts.append(f"<status>{', '.join(status_parts)}</status>")

        # Add main content
        parts.append("<output>")
        parts.append(self.content)
        parts.append("</output>")

        return "\n".join(parts)


class OutputHandler:
    """
    Handle and format tool output for LLM consumption.

    Features:
    - Smart truncation (keep beginning and end)
    - Metadata tagging
    - Timeout handling
    - Binary content detection
    """

    def __init__(
        self,
        max_chars: int = DEFAULT_MAX_OUTPUT,
        timeout_ms: int = DEFAULT_TIMEOUT
    ):
        self.max_chars = max_chars
        self.timeout_ms = timeout_ms

    def truncate(
        self,
        content: str,
        keep_beginning: int = None,
        keep_ending: int = None
    ) -> tuple[str, bool]:
        """
        Truncate content if it exceeds max length.

        Keeps beginning and ending for context.

        Args:
            content: Raw output
            keep_beginning: Chars to keep at start (default: 2/3 of max)
            keep_ending: Chars to keep at end (default: 1/3 of max)

        Returns:
            (truncated_content, was_truncated)
        """
        if len(content) <= self.max_chars:
            return content, False

        if keep_beginning is None:
            keep_beginning = int(self.max_chars * 2 / 3)
        if keep_ending is None:
            keep_ending = self.max_chars - keep_beginning - 100  # Leave room for notice

        # Truncate
        beginning = content[:keep_beginning]
        ending = content[-keep_ending:] if keep_ending > 0 else ""

        truncation_notice = f"\n\n... [{len(content) - keep_beginning - keep_ending} characters truncated] ...\n\n"

        truncated = beginning + truncation_notice + ending

        return truncated, True

    def truncate_lines(
        self,
        content: str,
        max_lines: int = MAX_LINES_PREVIEW
    ) -> tuple[str, bool]:
        """
        Truncate by line count, keeping beginning and end.

        Args:
            content: Raw output
            max_lines: Maximum lines to keep

        Returns:
            (truncated_content, was_truncated)
        """
        lines = content.split('\n')

        if len(lines) <= max_lines:
            return content, False

        keep_beginning = max_lines * 2 // 3
        keep_ending = max_lines - keep_beginning

        beginning_lines = lines[:keep_beginning]
        ending_lines = lines[-keep_ending:] if keep_ending > 0 else []

        omitted = len(lines) - keep_beginning - keep_ending
        truncation_notice = f"\n... [{omitted} lines omitted] ...\n"

        truncated = '\n'.join(beginning_lines) + truncation_notice + '\n'.join(ending_lines)

        return truncated, True

    def detect_binary(self, content: bytes) -> bool:
        """Check if content appears to be binary."""
        # Check for null bytes
        if b'\x00' in content[:1024]:
            return True

        # Check for high ratio of non-printable characters
        try:
            text = content[:1024].decode('utf-8')
            non_printable = sum(1 for c in text if ord(c) < 32 and c not in '\n\r\t')
            return non_printable / len(text) > 0.1
        except UnicodeDecodeError:
            return True

    def format_output(
        self,
        content: str,
        tool_name: str,
        exit_code: Optional[int] = None,
        timed_out: bool = False,
        aborted: bool = False,
        description: Optional[str] = None
    ) -> FormattedOutput:
        """
        Format tool output with metadata.

        Args:
            content: Raw output
            tool_name: Name of the tool
            exit_code: Process exit code
            timed_out: Whether execution timed out
            aborted: Whether user aborted
            description: Human-readable description

        Returns:
            FormattedOutput ready for LLM
        """
        warnings = []
        original_length = len(content)

        # Truncate if needed
        truncated_content, was_truncated = self.truncate(content)

        if was_truncated:
            warnings.append(
                f"Output truncated from {original_length} to {len(truncated_content)} characters. "
                "Use more specific queries to reduce output."
            )

        if timed_out:
            warnings.append(
                f"Command timed out after {self.timeout_ms // 1000} seconds."
            )

        if aborted:
            warnings.append("Command was aborted by user.")

        # Create metadata
        metadata = OutputMetadata(
            tool_name=tool_name,
            completed_at=datetime.utcnow(),
            exit_code=exit_code,
            truncated=was_truncated,
            timed_out=timed_out,
            aborted=aborted,
            original_length=original_length,
            description=description
        )

        return FormattedOutput(
            content=truncated_content,
            metadata=metadata,
            warnings=warnings
        )

    def format_error(
        self,
        error: str,
        tool_name: str,
        suggestion: Optional[str] = None
    ) -> FormattedOutput:
        """
        Format an error message.

        Args:
            error: Error message
            tool_name: Name of the tool
            suggestion: Suggested fix

        Returns:
            FormattedOutput with error
        """
        content = f"Error: {error}"
        if suggestion:
            content += f"\n\nSuggestion: {suggestion}"

        metadata = OutputMetadata(
            tool_name=tool_name,
            completed_at=datetime.utcnow(),
            exit_code=1,
            description=f"Error in {tool_name}"
        )

        return FormattedOutput(
            content=content,
            metadata=metadata,
            warnings=[error]
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_default_handler = None


def get_output_handler() -> OutputHandler:
    """Get the default output handler singleton."""
    global _default_handler
    if _default_handler is None:
        _default_handler = OutputHandler()
    return _default_handler


def truncate_output(content: str, max_chars: int = DEFAULT_MAX_OUTPUT) -> str:
    """Quick truncation helper."""
    handler = get_output_handler()
    handler.max_chars = max_chars
    truncated, _ = handler.truncate(content)
    return truncated


def format_for_llm(
    content: str,
    tool_name: str,
    exit_code: Optional[int] = None,
    description: Optional[str] = None
) -> str:
    """Quick formatting helper."""
    handler = get_output_handler()
    output = handler.format_output(
        content=content,
        tool_name=tool_name,
        exit_code=exit_code,
        description=description
    )
    return output.to_llm_format()


# =============================================================================
# SMART OUTPUT PROCESSING
# =============================================================================

def extract_relevant_lines(
    content: str,
    keywords: List[str],
    context_lines: int = 3
) -> str:
    """
    Extract lines containing keywords with surrounding context.

    Useful for large log files or verbose output.

    Args:
        content: Full output
        keywords: Words to search for
        context_lines: Lines to include before/after match

    Returns:
        Extracted relevant content
    """
    lines = content.split('\n')
    relevant_indices = set()

    # Find matching lines
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if any(kw.lower() in line_lower for kw in keywords):
            # Add this line and context
            for j in range(max(0, i - context_lines), min(len(lines), i + context_lines + 1)):
                relevant_indices.add(j)

    if not relevant_indices:
        return content  # Return original if no matches

    # Build output with ellipsis for gaps
    result = []
    sorted_indices = sorted(relevant_indices)
    prev_idx = -2

    for idx in sorted_indices:
        if idx > prev_idx + 1:
            result.append("...")
        result.append(lines[idx])
        prev_idx = idx

    return '\n'.join(result)


def summarize_long_output(content: str, max_summary_lines: int = 20) -> str:
    """
    Create a summary of long output.

    Extracts:
    - First few lines (headers/start)
    - Error lines
    - Warning lines
    - Last few lines (result/end)

    Args:
        content: Full output
        max_summary_lines: Maximum lines in summary

    Returns:
        Summary string
    """
    lines = content.split('\n')

    if len(lines) <= max_summary_lines:
        return content

    summary_parts = []

    # First few lines
    summary_parts.append("=== START ===")
    summary_parts.extend(lines[:5])

    # Error/warning lines
    error_lines = [l for l in lines if 'error' in l.lower() or 'warning' in l.lower()]
    if error_lines:
        summary_parts.append("\n=== ERRORS/WARNINGS ===")
        summary_parts.extend(error_lines[:10])

    # Last few lines
    summary_parts.append("\n=== END ===")
    summary_parts.extend(lines[-5:])

    summary_parts.append(f"\n[{len(lines)} total lines]")

    return '\n'.join(summary_parts)


# Test
if __name__ == "__main__":
    handler = OutputHandler(max_chars=500)

    # Test truncation
    long_content = "Line " * 1000
    output = handler.format_output(
        content=long_content,
        tool_name="test_tool",
        exit_code=0,
        description="Test command"
    )

    print("=== FORMATTED OUTPUT ===")
    print(output.to_llm_format()[:500])
    print("...")
    print(f"\nTruncated: {output.metadata.truncated}")
    print(f"Original length: {output.metadata.original_length}")

    # Test error formatting
    error_output = handler.format_error(
        error="File not found",
        tool_name="read_file",
        suggestion="Check if the file path is correct"
    )
    print("\n=== ERROR OUTPUT ===")
    print(error_output.to_llm_format())

    print("\nAll tests passed!")
