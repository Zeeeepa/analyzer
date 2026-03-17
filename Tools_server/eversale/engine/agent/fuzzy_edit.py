"""
Advanced Fuzzy Edit System

Based on OpenCode's edit.ts implementation with 9 replacement strategies:
1. SimpleReplacer - Direct exact string match
2. LineTrimmedReplacer - Line-by-line whitespace trimming
3. BlockAnchorReplacer - Uses first/last lines as anchors with Levenshtein similarity
4. WhitespaceNormalizedReplacer - Collapses internal whitespace
5. IndentationFlexibleReplacer - Removes common indentation before comparison
6. EscapeNormalizedReplacer - Handles escape sequences
7. TrimmedBoundaryReplacer - Matches trimmed variants
8. ContextAwareReplacer - Matches blocks with context anchors
9. MultiOccurrenceReplacer - Replace all occurrences

Features:
- Levenshtein distance calculation for similarity scoring
- Unified diff generation using difflib
- Validate oldString != newString
- Track additions/deletions in diffs
- Return detailed match info (strategy used, confidence, line numbers)

This is critical for reliable file editing when LLM provides approximate text.
"""

import re
import difflib
import textwrap
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass
from loguru import logger


@dataclass
class EditResult:
    """Result of an edit operation."""
    success: bool
    new_content: str = ""
    strategy: str = ""
    confidence: float = 0.0
    line_start: int = -1
    line_end: int = -1
    diff: str = ""
    additions: int = 0
    deletions: int = 0
    error: str = ""
    diagnostics: str = ""


class FuzzyEditor:
    """
    Advanced fuzzy editor with 9 replacement strategies.

    Tries strategies in sequence until one succeeds.
    Based on OpenCode's edit.ts cascading approach.
    """

    def __init__(self):
        """Initialize the fuzzy editor with all strategies."""
        self.strategies = [
            ("SimpleReplacer", self._simple_replace),
            ("LineTrimmedReplacer", self._line_trimmed_replace),
            ("BlockAnchorReplacer", self._block_anchor_replace),
            ("WhitespaceNormalizedReplacer", self._whitespace_normalized_replace),
            ("IndentationFlexibleReplacer", self._indentation_flexible_replace),
            ("EscapeNormalizedReplacer", self._escape_normalized_replace),
            ("TrimmedBoundaryReplacer", self._trimmed_boundary_replace),
            ("ContextAwareReplacer", self._context_aware_replace),
            ("MultiOccurrenceReplacer", self._multi_occurrence_replace),
        ]

    def edit(
        self,
        content: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False
    ) -> EditResult:
        """
        Perform fuzzy edit using cascading strategies.

        Args:
            content: Original file content
            old_string: String to search for
            new_string: String to replace with
            replace_all: If True, replace all occurrences

        Returns:
            EditResult with success status and details
        """
        # Validate inputs
        if not old_string:
            return EditResult(
                success=False,
                new_content=content,
                error="old_string cannot be empty"
            )

        if old_string == new_string:
            return EditResult(
                success=False,
                new_content=content,
                error="old_string and new_string are identical - no changes needed"
            )

        # Try each strategy in sequence
        for strategy_name, strategy_func in self.strategies:
            try:
                result = strategy_func(content, old_string, new_string, replace_all)
                if result.success:
                    logger.debug(f"[FUZZY_EDIT] Matched using {strategy_name}")
                    return result
            except Exception as e:
                logger.debug(f"[FUZZY_EDIT] Strategy {strategy_name} failed: {e}")
                continue

        # All strategies failed - generate diagnostics
        diagnostics = self._generate_diagnostics(content, old_string)

        return EditResult(
            success=False,
            new_content=content,
            error=f"No strategy could find a match. Tried {len(self.strategies)} strategies.",
            diagnostics=diagnostics
        )

    # =========================================================================
    # STRATEGY 1: SimpleReplacer
    # =========================================================================

    def _simple_replace(
        self,
        content: str,
        old_string: str,
        new_string: str,
        replace_all: bool
    ) -> EditResult:
        """Strategy 1: Direct exact string match."""
        if old_string not in content:
            return EditResult(success=False, error="Exact match not found")

        # Check for multiple occurrences
        occurrences = content.count(old_string)
        if occurrences > 1 and not replace_all:
            return EditResult(
                success=False,
                error=f"Found {occurrences} occurrences. Use replace_all=True to replace all."
            )

        # Perform replacement
        new_content = content.replace(old_string, new_string, -1 if replace_all else 1)

        # Calculate line numbers
        line_start = content[:content.find(old_string)].count('\n') + 1
        line_end = line_start + old_string.count('\n')

        # Generate diff
        diff_result = self._generate_diff(content, new_content)

        return EditResult(
            success=True,
            new_content=new_content,
            strategy="SimpleReplacer",
            confidence=1.0,
            line_start=line_start,
            line_end=line_end,
            diff=diff_result['diff'],
            additions=diff_result['additions'],
            deletions=diff_result['deletions']
        )

    # =========================================================================
    # STRATEGY 2: LineTrimmedReplacer
    # =========================================================================

    def _line_trimmed_replace(
        self,
        content: str,
        old_string: str,
        new_string: str,
        replace_all: bool
    ) -> EditResult:
        """Strategy 2: Line-by-line whitespace trimming for multi-line blocks."""
        if '\n' not in old_string:
            return EditResult(success=False, error="Not a multi-line block")

        # Split into lines and trim each
        old_lines = [line.strip() for line in old_string.split('\n')]
        content_lines = content.split('\n')

        # Find matching sequences
        matches = []
        for i in range(len(content_lines) - len(old_lines) + 1):
            is_match = True
            for j, old_line in enumerate(old_lines):
                if content_lines[i + j].strip() != old_line:
                    is_match = False
                    break
            if is_match:
                matches.append((i, i + len(old_lines)))

        if not matches:
            return EditResult(success=False, error="No trimmed match found")

        if len(matches) > 1 and not replace_all:
            return EditResult(
                success=False,
                error=f"Found {len(matches)} matches. Use replace_all=True."
            )

        # Replace all matches (or just the first)
        new_content_lines = content_lines.copy()
        new_string_lines = new_string.split('\n')

        # Replace in reverse to maintain indices
        for start, end in reversed(matches if replace_all else [matches[0]]):
            # Preserve indentation from original
            indent = len(content_lines[start]) - len(content_lines[start].lstrip())
            indented_new = [' ' * indent + line if line.strip() else line
                           for line in new_string_lines]
            new_content_lines[start:end] = indented_new

        new_content = '\n'.join(new_content_lines)
        diff_result = self._generate_diff(content, new_content)

        first_match = matches[0]
        return EditResult(
            success=True,
            new_content=new_content,
            strategy="LineTrimmedReplacer",
            confidence=0.95,
            line_start=first_match[0] + 1,
            line_end=first_match[1],
            diff=diff_result['diff'],
            additions=diff_result['additions'],
            deletions=diff_result['deletions']
        )

    # =========================================================================
    # STRATEGY 3: BlockAnchorReplacer
    # =========================================================================

    def _block_anchor_replace(
        self,
        content: str,
        old_string: str,
        new_string: str,
        replace_all: bool
    ) -> EditResult:
        """
        Strategy 3: Uses first/last lines as anchors with Levenshtein similarity.
        Threshold: 0.0 for single line, 0.3 for multiple lines.
        """
        old_lines = old_string.split('\n')
        if len(old_lines) < 2:
            return EditResult(success=False, error="Block anchor requires multiple lines")

        first_line = old_lines[0].strip()
        last_line = old_lines[-1].strip()
        middle_lines = old_lines[1:-1]

        threshold = 0.3
        content_lines = content.split('\n')

        # Find blocks with matching anchors
        matches = []
        for i in range(len(content_lines)):
            # Check first line
            first_sim = self._similarity_ratio(content_lines[i].strip(), first_line)
            if first_sim < (1.0 - threshold):
                continue

            # Look ahead for last line
            for j in range(i + 1, min(i + len(old_lines) + 3, len(content_lines))):
                last_sim = self._similarity_ratio(content_lines[j].strip(), last_line)
                if last_sim < (1.0 - threshold):
                    continue

                # Check middle lines if present
                block_lines = content_lines[i+1:j]
                if len(middle_lines) > 0:
                    # Middle lines should have at least 50% similarity
                    middle_score = self._block_similarity(block_lines, middle_lines)
                    if middle_score < 0.5:
                        continue

                confidence = (first_sim + last_sim) / 2
                matches.append((i, j + 1, confidence))

        if not matches:
            return EditResult(success=False, error="No anchor match found")

        if len(matches) > 1 and not replace_all:
            return EditResult(
                success=False,
                error=f"Found {len(matches)} anchor matches. Use replace_all=True."
            )

        # Use the best match
        matches.sort(key=lambda x: x[2], reverse=True)
        best_match = matches[0]

        # Replace
        new_content_lines = content_lines.copy()
        new_string_lines = new_string.split('\n')

        # Preserve indentation
        indent = len(content_lines[best_match[0]]) - len(content_lines[best_match[0]].lstrip())
        indented_new = [' ' * indent + line if line.strip() else line
                       for line in new_string_lines]

        new_content_lines[best_match[0]:best_match[1]] = indented_new
        new_content = '\n'.join(new_content_lines)
        diff_result = self._generate_diff(content, new_content)

        return EditResult(
            success=True,
            new_content=new_content,
            strategy="BlockAnchorReplacer",
            confidence=best_match[2],
            line_start=best_match[0] + 1,
            line_end=best_match[1],
            diff=diff_result['diff'],
            additions=diff_result['additions'],
            deletions=diff_result['deletions']
        )

    # =========================================================================
    # STRATEGY 4: WhitespaceNormalizedReplacer
    # =========================================================================

    def _whitespace_normalized_replace(
        self,
        content: str,
        old_string: str,
        new_string: str,
        replace_all: bool
    ) -> EditResult:
        """Strategy 4: Collapses internal whitespace while preserving matching."""
        # Normalize whitespace
        old_normalized = re.sub(r'\s+', ' ', old_string).strip()

        # Find all positions where normalized content matches
        matches = []
        content_lines = content.split('\n')

        for i in range(len(content_lines)):
            for j in range(i, len(content_lines) + 1):
                block = '\n'.join(content_lines[i:j])
                block_normalized = re.sub(r'\s+', ' ', block).strip()

                if block_normalized == old_normalized:
                    matches.append((i, j, block))

        if not matches:
            return EditResult(success=False, error="No whitespace-normalized match found")

        if len(matches) > 1 and not replace_all:
            return EditResult(
                success=False,
                error=f"Found {len(matches)} normalized matches. Use replace_all=True."
            )

        # Replace first match
        match = matches[0]
        new_content = content.replace(match[2], new_string, 1 if not replace_all else -1)
        diff_result = self._generate_diff(content, new_content)

        return EditResult(
            success=True,
            new_content=new_content,
            strategy="WhitespaceNormalizedReplacer",
            confidence=0.90,
            line_start=match[0] + 1,
            line_end=match[1],
            diff=diff_result['diff'],
            additions=diff_result['additions'],
            deletions=diff_result['deletions']
        )

    # =========================================================================
    # STRATEGY 5: IndentationFlexibleReplacer
    # =========================================================================

    def _indentation_flexible_replace(
        self,
        content: str,
        old_string: str,
        new_string: str,
        replace_all: bool
    ) -> EditResult:
        """Strategy 5: Removes common indentation before comparison."""
        # Remove common indentation from old_string
        old_dedented = self._dedent(old_string)

        content_lines = content.split('\n')
        matches = []

        # Try to find blocks that match after dedenting
        for i in range(len(content_lines)):
            for j in range(i, min(i + old_string.count('\n') + 5, len(content_lines) + 1)):
                block = '\n'.join(content_lines[i:j])
                block_dedented = self._dedent(block)

                if block_dedented == old_dedented:
                    matches.append((i, j, block))

        if not matches:
            return EditResult(success=False, error="No indentation-flexible match found")

        if len(matches) > 1 and not replace_all:
            return EditResult(
                success=False,
                error=f"Found {len(matches)} dedented matches. Use replace_all=True."
            )

        # Replace preserving original indentation
        match = matches[0]
        original_block = match[2]

        # Get original indentation
        first_line_indent = len(content_lines[match[0]]) - len(content_lines[match[0]].lstrip())

        # Apply same indentation to new_string
        new_lines = new_string.split('\n')
        indented_new = [' ' * first_line_indent + line if line.strip() else line
                       for line in new_lines]
        new_string_indented = '\n'.join(indented_new)

        new_content = content.replace(original_block, new_string_indented, 1 if not replace_all else -1)
        diff_result = self._generate_diff(content, new_content)

        return EditResult(
            success=True,
            new_content=new_content,
            strategy="IndentationFlexibleReplacer",
            confidence=0.92,
            line_start=match[0] + 1,
            line_end=match[1],
            diff=diff_result['diff'],
            additions=diff_result['additions'],
            deletions=diff_result['deletions']
        )

    # =========================================================================
    # STRATEGY 6: EscapeNormalizedReplacer
    # =========================================================================

    def _escape_normalized_replace(
        self,
        content: str,
        old_string: str,
        new_string: str,
        replace_all: bool
    ) -> EditResult:
        """Strategy 6: Handles escape sequences (\\n, \\t, quotes, backslashes)."""
        # Normalize escape sequences
        escape_map = {
            '\\n': '\n',
            '\\t': '\t',
            '\\"': '"',
            "\\'": "'",
            '\\\\': '\\'
        }

        old_normalized = old_string
        for escaped, actual in escape_map.items():
            old_normalized = old_normalized.replace(escaped, actual)

        # Try to find match with normalized escapes
        if old_normalized in content:
            occurrences = content.count(old_normalized)
            if occurrences > 1 and not replace_all:
                return EditResult(
                    success=False,
                    error=f"Found {occurrences} escape-normalized matches. Use replace_all=True."
                )

            new_content = content.replace(old_normalized, new_string)
            line_start = content[:content.find(old_normalized)].count('\n') + 1
            line_end = line_start + old_normalized.count('\n')
            diff_result = self._generate_diff(content, new_content)

            return EditResult(
                success=True,
                new_content=new_content,
                strategy="EscapeNormalizedReplacer",
                confidence=0.88,
                line_start=line_start,
                line_end=line_end,
                diff=diff_result['diff'],
                additions=diff_result['additions'],
                deletions=diff_result['deletions']
            )

        return EditResult(success=False, error="No escape-normalized match found")

    # =========================================================================
    # STRATEGY 7: TrimmedBoundaryReplacer
    # =========================================================================

    def _trimmed_boundary_replace(
        self,
        content: str,
        old_string: str,
        new_string: str,
        replace_all: bool
    ) -> EditResult:
        """Strategy 7: Matches trimmed variants of search strings."""
        # Try trimmed versions
        variants = [
            old_string.strip(),
            old_string.lstrip(),
            old_string.rstrip(),
        ]

        for variant in variants:
            if variant in content:
                occurrences = content.count(variant)
                if occurrences > 1 and not replace_all:
                    return EditResult(
                        success=False,
                        error=f"Found {occurrences} trimmed matches. Use replace_all=True."
                    )

                new_content = content.replace(variant, new_string)
                line_start = content[:content.find(variant)].count('\n') + 1
                line_end = line_start + variant.count('\n')
                diff_result = self._generate_diff(content, new_content)

                return EditResult(
                    success=True,
                    new_content=new_content,
                    strategy="TrimmedBoundaryReplacer",
                    confidence=0.85,
                    line_start=line_start,
                    line_end=line_end,
                    diff=diff_result['diff'],
                    additions=diff_result['additions'],
                    deletions=diff_result['deletions']
                )

        return EditResult(success=False, error="No trimmed match found")

    # =========================================================================
    # STRATEGY 8: ContextAwareReplacer
    # =========================================================================

    def _context_aware_replace(
        self,
        content: str,
        old_string: str,
        new_string: str,
        replace_all: bool
    ) -> EditResult:
        """
        Strategy 8: Matches blocks with context anchors, 50% middle-line similarity.
        Uses surrounding context to locate the block.
        """
        old_lines = old_string.split('\n')
        if len(old_lines) < 3:
            return EditResult(success=False, error="Context-aware requires at least 3 lines")

        # Use first 2 and last 2 lines as context
        first_context = old_lines[:2]
        last_context = old_lines[-2:]
        middle_lines = old_lines[2:-2]

        content_lines = content.split('\n')
        matches = []

        for i in range(len(content_lines) - len(old_lines) + 1):
            # Check first context
            first_match = all(
                self._similarity_ratio(content_lines[i + j].strip(), first_context[j].strip()) > 0.7
                for j in range(len(first_context))
            )

            if not first_match:
                continue

            # Check last context
            last_start = i + len(old_lines) - len(last_context)
            last_match = all(
                self._similarity_ratio(content_lines[last_start + j].strip(), last_context[j].strip()) > 0.7
                for j in range(len(last_context))
            )

            if not last_match:
                continue

            # Check middle similarity
            block_middle = content_lines[i + len(first_context):last_start]
            if len(middle_lines) > 0:
                middle_score = self._block_similarity(block_middle, middle_lines)
                if middle_score < 0.5:
                    continue
                confidence = middle_score
            else:
                confidence = 0.85

            matches.append((i, i + len(old_lines), confidence))

        if not matches:
            return EditResult(success=False, error="No context-aware match found")

        if len(matches) > 1 and not replace_all:
            return EditResult(
                success=False,
                error=f"Found {len(matches)} context matches. Use replace_all=True."
            )

        # Use best match
        matches.sort(key=lambda x: x[2], reverse=True)
        best_match = matches[0]

        new_content_lines = content_lines.copy()
        new_string_lines = new_string.split('\n')

        # Preserve indentation
        indent = len(content_lines[best_match[0]]) - len(content_lines[best_match[0]].lstrip())
        indented_new = [' ' * indent + line if line.strip() else line
                       for line in new_string_lines]

        new_content_lines[best_match[0]:best_match[1]] = indented_new
        new_content = '\n'.join(new_content_lines)
        diff_result = self._generate_diff(content, new_content)

        return EditResult(
            success=True,
            new_content=new_content,
            strategy="ContextAwareReplacer",
            confidence=best_match[2],
            line_start=best_match[0] + 1,
            line_end=best_match[1],
            diff=diff_result['diff'],
            additions=diff_result['additions'],
            deletions=diff_result['deletions']
        )

    # =========================================================================
    # STRATEGY 9: MultiOccurrenceReplacer
    # =========================================================================

    def _multi_occurrence_replace(
        self,
        content: str,
        old_string: str,
        new_string: str,
        replace_all: bool
    ) -> EditResult:
        """Strategy 9: Replace all occurrences."""
        if not replace_all:
            return EditResult(success=False, error="Multi-occurrence requires replace_all=True")

        if old_string not in content:
            return EditResult(success=False, error="No occurrences found")

        occurrences = content.count(old_string)
        new_content = content.replace(old_string, new_string)

        # Find first occurrence for line numbers
        line_start = content[:content.find(old_string)].count('\n') + 1
        line_end = line_start + old_string.count('\n')

        diff_result = self._generate_diff(content, new_content)

        return EditResult(
            success=True,
            new_content=new_content,
            strategy=f"MultiOccurrenceReplacer ({occurrences} occurrences)",
            confidence=1.0,
            line_start=line_start,
            line_end=line_end,
            diff=diff_result['diff'],
            additions=diff_result['additions'],
            deletions=diff_result['deletions']
        )

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """
        Calculate Levenshtein distance between two strings.

        Args:
            s1: First string
            s2: Second string

        Returns:
            Edit distance (number of single-character edits)
        """
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def _similarity_ratio(self, s1: str, s2: str) -> float:
        """
        Calculate similarity ratio (0.0 to 1.0) between two strings.

        Args:
            s1: First string
            s2: Second string

        Returns:
            Similarity ratio (1.0 = identical, 0.0 = completely different)
        """
        if not s1 and not s2:
            return 1.0
        if not s1 or not s2:
            return 0.0

        distance = self._levenshtein_distance(s1, s2)
        max_len = max(len(s1), len(s2))
        return 1.0 - (distance / max_len)

    def _block_similarity(self, block1: List[str], block2: List[str]) -> float:
        """
        Calculate similarity between two blocks of lines.

        Args:
            block1: First block (list of lines)
            block2: Second block (list of lines)

        Returns:
            Average similarity ratio
        """
        if not block1 and not block2:
            return 1.0
        if not block1 or not block2:
            return 0.0

        # Use difflib for sequence matching
        matcher = difflib.SequenceMatcher(None, block1, block2)
        return matcher.ratio()

    def _dedent(self, text: str) -> str:
        """
        Remove common leading whitespace from all lines.

        Args:
            text: Text to dedent

        Returns:
            Dedented text
        """
        lines = text.split('\n')
        if not lines:
            return text

        # Find minimum indentation (excluding empty lines)
        min_indent = float('inf')
        for line in lines:
            if line.strip():
                indent = len(line) - len(line.lstrip())
                min_indent = min(min_indent, indent)

        if min_indent == float('inf'):
            return text

        # Remove common indentation
        dedented_lines = []
        for line in lines:
            if line.strip():
                dedented_lines.append(line[min_indent:])
            else:
                dedented_lines.append(line)

        return '\n'.join(dedented_lines)

    def _generate_diff(self, old_content: str, new_content: str) -> Dict[str, Any]:
        """
        Generate unified diff and count additions/deletions.

        Args:
            old_content: Original content
            new_content: New content

        Returns:
            Dict with diff string, additions count, and deletions count
        """
        old_lines = old_content.split('\n')
        new_lines = new_content.split('\n')

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            lineterm='',
            n=3
        )

        diff_text = '\n'.join(diff)

        # Count additions and deletions
        additions = diff_text.count('\n+') - diff_text.count('\n+++')
        deletions = diff_text.count('\n-') - diff_text.count('\n---')

        return {
            'diff': diff_text,
            'additions': max(0, additions),
            'deletions': max(0, deletions)
        }

    def _generate_diagnostics(self, content: str, old_string: str) -> str:
        """Generate helpful diagnostics when no match is found."""
        lines = []
        lines.append("No match found for old_string.")

        # Check if partial match exists
        old_lines = old_string.strip().split('\n')
        if old_lines:
            first_line = old_lines[0].strip()
            if first_line in content:
                lines.append(f"First line '{first_line[:50]}...' found in content.")
            else:
                # Find closest match using difflib
                content_lines = content.split('\n')
                matches = difflib.get_close_matches(
                    first_line,
                    [l.strip() for l in content_lines],
                    n=1,
                    cutoff=0.5
                )
                if matches:
                    lines.append(f"Similar line found: '{matches[0][:50]}...'")

        # Check content length
        if len(old_string) > len(content):
            lines.append("old_string is longer than entire file content.")

        return " ".join(lines)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def fuzzy_edit(
    content: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False
) -> EditResult:
    """
    Perform fuzzy text replacement using multiple strategies.

    Args:
        content: Original file content
        old_string: Text to find (may be approximate)
        new_string: Replacement text
        replace_all: Whether to replace all occurrences

    Returns:
        EditResult with success status and new content
    """
    editor = FuzzyEditor()
    return editor.edit(content, old_string, new_string, replace_all)


def edit_file(
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False
) -> EditResult:
    """
    Edit a file using fuzzy matching.

    Args:
        file_path: Path to file
        old_string: Text to find
        new_string: Replacement text
        replace_all: Replace all occurrences

    Returns:
        EditResult with success status
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return EditResult(
            success=False,
            new_content="",
            error=f"Failed to read file: {e}"
        )

    result = fuzzy_edit(content, old_string, new_string, replace_all)

    if result.success:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(result.new_content)
            logger.info(f"[FUZZY_EDIT] Successfully edited {file_path} using {result.strategy}")
        except Exception as e:
            return EditResult(
                success=False,
                new_content=result.new_content,
                strategy=result.strategy,
                error=f"Matched but failed to write: {e}"
            )

    return result


# =============================================================================
# TESTS
# =============================================================================

def test_fuzzy_editor():
    """Comprehensive test suite for FuzzyEditor."""
    editor = FuzzyEditor()
    test_results = []

    print("\n" + "=" * 60)
    print("FUZZY EDIT SYSTEM - TEST SUITE")
    print("=" * 60)

    # Test 1: Simple exact match
    print("\nTest 1: SimpleReplacer - Exact match")
    content1 = "def foo():\n    return 42\n\ndef bar():\n    return 24"
    result1 = editor.edit(content1, "return 42", "return 100")
    success1 = result1.success and "return 100" in result1.new_content
    test_results.append(("SimpleReplacer", success1))
    print(f"  Result: {'PASS' if success1 else 'FAIL'}")
    print(f"  Strategy: {result1.strategy}, Confidence: {result1.confidence}")

    # Test 2: Line trimmed match
    print("\nTest 2: LineTrimmedReplacer - Whitespace differences")
    content2 = "def foo():\n    x = 1\n    y = 2\n    return x + y"
    old2 = "x = 1\ny = 2\nreturn x + y"
    new2 = "total = 3\nreturn total"
    result2 = editor.edit(content2, old2, new2)
    success2 = result2.success and "total = 3" in result2.new_content
    test_results.append(("LineTrimmedReplacer", success2))
    print(f"  Result: {'PASS' if success2 else 'FAIL'}")
    print(f"  Strategy: {result2.strategy}")

    # Test 3: Multiple occurrences without replace_all
    print("\nTest 3: Multiple occurrences detection")
    content3 = "x = 1\nx = 1\nx = 1"
    result3 = editor.edit(content3, "x = 1", "x = 2")
    # Should fail because simple replacer detects multiple occurrences
    # Other strategies might not find a match either
    success3 = not result3.success
    test_results.append(("MultiOccurrence Detection", success3))
    print(f"  Result: {'PASS' if success3 else 'FAIL'}")
    print(f"  Error: {result3.error}")

    # Test 4: Multiple occurrences with replace_all
    print("\nTest 4: MultiOccurrenceReplacer - Replace all")
    result4 = editor.edit(content3, "x = 1", "x = 2", replace_all=True)
    success4 = result4.success and result4.new_content.count("x = 2") == 3
    test_results.append(("MultiOccurrenceReplacer", success4))
    print(f"  Result: {'PASS' if success4 else 'FAIL'}")
    print(f"  Strategy: {result4.strategy}")

    # Test 5: Indentation flexible
    print("\nTest 5: IndentationFlexibleReplacer")
    content5 = "def foo():\n    if True:\n        x = 1\n        y = 2"
    old5 = "x = 1\ny = 2"
    new5 = "z = 3"
    result5 = editor.edit(content5, old5, new5)
    success5 = result5.success and "z = 3" in result5.new_content
    test_results.append(("IndentationFlexibleReplacer", success5))
    print(f"  Result: {'PASS' if success5 else 'FAIL'}")
    print(f"  Strategy: {result5.strategy}")

    # Test 6: Whitespace normalized
    print("\nTest 6: WhitespaceNormalizedReplacer")
    content6 = "def foo():\n    x    =    1\n    y = 2"
    old6 = "x = 1"
    new6 = "x = 100"
    result6 = editor.edit(content6, old6, new6)
    success6 = result6.success and "100" in result6.new_content
    test_results.append(("WhitespaceNormalizedReplacer", success6))
    print(f"  Result: {'PASS' if success6 else 'FAIL'}")
    print(f"  Strategy: {result6.strategy}")

    # Test 7: Block anchor with fuzzy match
    print("\nTest 7: BlockAnchorReplacer - Fuzzy anchor matching")
    content7 = """def calculate():
    # Start calculation
    x = 1
    y = 2
    z = x + y
    # End calculation
    return z"""
    old7 = """# Start calculation
x = 1
y = 2
z = x + y
# End calculation"""
    new7 = """# New calculation
total = 3"""
    result7 = editor.edit(content7, old7, new7)
    success7 = result7.success and "total = 3" in result7.new_content
    test_results.append(("BlockAnchorReplacer", success7))
    print(f"  Result: {'PASS' if success7 else 'FAIL'}")
    print(f"  Strategy: {result7.strategy}, Confidence: {result7.confidence:.2f}")

    # Test 8: Escape sequences
    print("\nTest 8: EscapeNormalizedReplacer")
    content8 = 'print("Hello\\nWorld")'
    old8 = 'print("Hello\\nWorld")'
    new8 = 'print("Goodbye")'
    result8 = editor.edit(content8, old8, new8)
    success8 = result8.success and "Goodbye" in result8.new_content
    test_results.append(("EscapeNormalizedReplacer", success8))
    print(f"  Result: {'PASS' if success8 else 'FAIL'}")
    print(f"  Strategy: {result8.strategy}")

    # Test 9: Identical strings rejection
    print("\nTest 9: Identical string validation")
    result9 = editor.edit(content1, "return 42", "return 42")
    success9 = not result9.success and "identical" in result9.error.lower()
    test_results.append(("Identical String Check", success9))
    print(f"  Result: {'PASS' if success9 else 'FAIL'}")
    print(f"  Error: {result9.error}")

    # Test 10: Diff generation
    print("\nTest 10: Diff generation and statistics")
    content10 = "line1\nline2\nline3"
    result10 = editor.edit(content10, "line2", "LINE_TWO")
    success10 = result10.success and len(result10.diff) > 0
    test_results.append(("Diff Generation", success10))
    print(f"  Result: {'PASS' if success10 else 'FAIL'}")
    print(f"  Additions: {result10.additions}, Deletions: {result10.deletions}")
    if result10.diff:
        print(f"  Diff preview: {result10.diff[:200]}...")

    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = sum(1 for _, success in test_results if success)
    total = len(test_results)
    print(f"Passed: {passed}/{total}")
    for name, success in test_results:
        status = "PASS" if success else "FAIL"
        symbol = "[+]" if success else "[X]"
        print(f"  {symbol} {name}: {status}")

    if passed == total:
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)
        return True
    else:
        print("\n" + "=" * 60)
        print(f"SOME TESTS FAILED ({total - passed} failures)")
        print("=" * 60)
        return False


if __name__ == "__main__":
    test_fuzzy_editor()
