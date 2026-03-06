"""
Wildcard matching system for pattern-based text matching.

Based on OpenCode's util/wildcard.ts patterns with support for:
- * (zero or more characters)
- ? (exactly one character)
- ** (matches across path segments)

Usage Examples:
    from wildcard_matcher import WildcardMatcher

    matcher = WildcardMatcher()

    # Basic matching
    matcher.match("*.py", "file.py")  # True
    matcher.match("test_??.py", "test_01.py")  # True
    matcher.match("**.py", "src/lib/file.py")  # True

    # Multiple patterns
    matcher.match_any(["*.py", "*.js"], "file.py")  # True
    matcher.match_all(["test*", "*file*"], "test_file_1")  # True

    # Extract captured groups
    result = matcher.extract("Hello *", "Hello world")
    # result = {'match': 'Hello world', 'groups': ['world']}

    # Path matching
    matcher.match_path("src/**/*.py", "src/lib/utils/helper.py")  # True
    matcher.match_path("**.py", "test.py")  # True

    # Permission-style matching (dot-separated)
    matcher.match_permission("file.read.*", "file.read.txt")  # True
    matcher.match_permission("admin.**", "admin.users.create")  # True

    # Utility functions
    matcher.is_pattern("*.py")  # True
    matcher.normalize_pattern("a***b")  # "a**b"
    matcher.sort_patterns(["long", "short", "medium"])  # ["short", "medium", "long"]
    matcher.expand_pattern("*.py", ["a.py", "b.js", "c.py"])  # ["a.py", "c.py"]
"""

import re
from typing import List, Optional, Dict, Any, Tuple


class WildcardMatcher:
    """Pattern matching with wildcard support (* and ? and **)."""

    def __init__(self):
        """Initialize the wildcard matcher."""
        pass

    @staticmethod
    def _escape_regex_chars(text: str) -> str:
        """Escape special regex characters except * and ?."""
        # Use re.escape but preserve * and ?
        # First, replace * and ? with placeholders
        text = text.replace('*', '__STAR__')
        text = text.replace('?', '__QUESTION__')

        # Escape everything else
        escaped = re.escape(text)

        # Restore * and ?
        escaped = escaped.replace('__STAR__', '*')
        escaped = escaped.replace('__QUESTION__', '?')

        return escaped

    @staticmethod
    def _pattern_to_regex(pattern: str, multiline: bool = False) -> re.Pattern:
        """
        Convert wildcard pattern to regex.

        Args:
            pattern: Wildcard pattern with *, ?, **
            multiline: Whether to match across newlines

        Returns:
            Compiled regex pattern
        """
        # First escape special regex characters (but not * and ?)
        escaped = WildcardMatcher._escape_regex_chars(pattern)

        # Handle ** (matches across segments/newlines)
        # Replace ** with a temporary placeholder first
        escaped = escaped.replace('**', '__DOUBLESTAR__')

        # Replace single * (zero or more characters, not crossing newlines by default)
        if multiline:
            escaped = escaped.replace('*', '.*')
        else:
            escaped = escaped.replace('*', '[^\n]*')

        # Replace ? (exactly one character)
        escaped = escaped.replace('?', '.')

        # Replace ** placeholder (matches across segments)
        escaped = escaped.replace('__DOUBLESTAR__', '.*')

        # Anchor the pattern to match the entire string
        regex_pattern = f'^{escaped}$'

        # Compile with appropriate flags
        flags = re.DOTALL if multiline else 0
        return re.compile(regex_pattern, flags)

    def match(self, pattern: str, text: str, multiline: bool = False) -> bool:
        """
        Check if text matches the wildcard pattern.

        Args:
            pattern: Wildcard pattern
            text: Text to match against
            multiline: Whether to match across newlines (auto-enabled for ** patterns)

        Returns:
            True if text matches pattern
        """
        # Auto-enable multiline for ** patterns
        if '**' in pattern:
            multiline = True
        regex = self._pattern_to_regex(pattern, multiline)
        return regex.match(text) is not None

    def match_any(self, patterns: List[str], text: str, multiline: bool = False) -> bool:
        """
        Check if text matches any of the patterns.

        Args:
            patterns: List of wildcard patterns
            text: Text to match against
            multiline: Whether to match across newlines

        Returns:
            True if text matches at least one pattern
        """
        return any(self.match(pattern, text, multiline) for pattern in patterns)

    def match_all(self, patterns: List[str], text: str, multiline: bool = False) -> bool:
        """
        Check if text matches all patterns.

        Args:
            patterns: List of wildcard patterns
            text: Text to match against
            multiline: Whether to match across newlines

        Returns:
            True if text matches all patterns
        """
        return all(self.match(pattern, text, multiline) for pattern in patterns)

    def extract(self, pattern: str, text: str, multiline: bool = False) -> Optional[Dict[str, str]]:
        """
        Extract matched portions from text based on pattern.

        Wildcards become capture groups in the result.

        Args:
            pattern: Wildcard pattern
            text: Text to match and extract from
            multiline: Whether to match across newlines

        Returns:
            Dictionary with 'match' (full match) and 'groups' (list of captured parts)
            Returns None if no match
        """
        # Convert pattern to regex with capture groups
        escaped = self._escape_regex_chars(pattern)

        # Replace ** with capturing group
        escaped = escaped.replace('**', '(__DOUBLESTAR__)')

        # Replace * with capturing group
        if multiline:
            escaped = escaped.replace('*', '(.*)')
        else:
            escaped = escaped.replace('*', '([^\n]*)')

        # Replace ? with capturing group
        escaped = escaped.replace('?', '(.)')

        # Replace ** placeholder
        escaped = escaped.replace('(__DOUBLESTAR__)', '(.*)')

        regex_pattern = f'^{escaped}$'
        flags = re.DOTALL if multiline else 0
        regex = re.compile(regex_pattern, flags)

        match_result = regex.match(text)
        if match_result:
            return {
                'match': match_result.group(0),
                'groups': list(match_result.groups())
            }
        return None

    def match_structured(self, pattern: str, parts: List[str]) -> bool:
        """
        Match pattern against array of parts.

        Supports recursive sequence matching for permission-style patterns.

        Args:
            pattern: Wildcard pattern (can use whitespace as separator)
            parts: List of parts to match against

        Returns:
            True if pattern matches the parts sequence
        """
        # Split pattern by whitespace if it contains spaces
        pattern_parts = pattern.split() if ' ' in pattern else [pattern]

        return self._match_sequence(pattern_parts, parts)

    def _match_sequence(self, pattern_parts: List[str], text_parts: List[str]) -> bool:
        """
        Recursively match pattern parts against text parts.

        Args:
            pattern_parts: List of pattern segments
            text_parts: List of text segments to match

        Returns:
            True if sequences match
        """
        if not pattern_parts:
            return not text_parts

        if not text_parts:
            # Check if remaining patterns can match empty
            return all(p == '*' or p == '**' for p in pattern_parts)

        current_pattern = pattern_parts[0]

        # Handle ** - matches zero or more parts
        if current_pattern == '**':
            # Try matching rest of pattern with current position
            if self._match_sequence(pattern_parts[1:], text_parts):
                return True
            # Try consuming one part and continuing with **
            if text_parts:
                return self._match_sequence(pattern_parts, text_parts[1:])
            return False

        # Handle patterns starting with ** (like **.py)
        # This should match across all remaining segments
        if current_pattern.startswith('**'):
            # Try matching this pattern against each remaining part
            for i in range(len(text_parts)):
                # Try matching the pattern against the current part
                # Remove ** from pattern and match the rest
                simple_pattern = current_pattern[2:]  # Remove **
                if self.match('*' + simple_pattern, text_parts[i]):
                    # Check if rest of patterns match rest of parts
                    if self._match_sequence(pattern_parts[1:], text_parts[i+1:]):
                        return True
            return False

        # Handle * - matches one part with wildcards
        if self.match(current_pattern, text_parts[0]):
            return self._match_sequence(pattern_parts[1:], text_parts[1:])

        return False

    @staticmethod
    def is_pattern(text: str) -> bool:
        """
        Check if text contains wildcard characters.

        Args:
            text: Text to check

        Returns:
            True if text contains * or ?
        """
        return '*' in text or '?' in text

    @staticmethod
    def normalize_pattern(pattern: str) -> str:
        """
        Normalize pattern by cleaning up redundant wildcards.

        Args:
            pattern: Pattern to normalize

        Returns:
            Normalized pattern
        """
        # Replace three or more consecutive * with **
        normalized = re.sub(r'\*{3,}', '**', pattern)

        # Clean up whitespace
        normalized = ' '.join(normalized.split())

        return normalized

    @staticmethod
    def sort_patterns(patterns: List[str]) -> List[str]:
        """
        Sort patterns by priority (shorter first, alphabetical within same length).

        First match wins in pattern matching systems.

        Args:
            patterns: List of patterns to sort

        Returns:
            Sorted list of patterns
        """
        return sorted(patterns, key=lambda p: (len(p), p))

    def expand_pattern(self, pattern: str, candidates: List[str]) -> List[str]:
        """
        Expand pattern to all matching candidates.

        Args:
            pattern: Wildcard pattern
            candidates: List of possible values

        Returns:
            List of candidates that match the pattern
        """
        return [c for c in candidates if self.match(pattern, c)]

    def match_path(self, pattern: str, path: str) -> bool:
        """
        Match file path patterns with ** support.

        Examples:
            **.py matches any .py file at any depth
            src/**/test matches deeply nested test directories
            file.read.* matches file.read.txt, file.read.json, etc.

        Args:
            pattern: Path pattern with wildcards
            path: File path to match

        Returns:
            True if path matches pattern
        """
        # Normalize path separators
        normalized_path = path.replace('\\', '/')
        normalized_pattern = pattern.replace('\\', '/')

        # Split into segments
        pattern_segments = [s for s in normalized_pattern.split('/') if s]
        path_segments = [s for s in normalized_path.split('/') if s]

        return self._match_sequence(pattern_segments, path_segments)

    def match_permission(self, pattern: str, permission: str) -> bool:
        """
        Match permission-style patterns (dot-separated).

        Examples:
            file.read.* matches file.read.txt
            admin.** matches admin.users.create
            *.write matches file.write, db.write, etc.

        Args:
            pattern: Permission pattern with wildcards
            permission: Permission string to match

        Returns:
            True if permission matches pattern
        """
        # Split by dots
        pattern_parts = pattern.split('.')
        permission_parts = permission.split('.')

        return self._match_sequence(pattern_parts, permission_parts)


# Test suite
if __name__ == '__main__':
    print("Testing WildcardMatcher...\n")

    matcher = WildcardMatcher()

    # Test 1: Basic wildcard matching
    print("Test 1: Basic wildcard matching")
    assert matcher.match("hello*", "hello world") == True
    assert matcher.match("hello*", "hello") == True
    assert matcher.match("hello*", "hi world") == False
    assert matcher.match("*world", "hello world") == True
    assert matcher.match("*world", "world") == True
    print("PASSED\n")

    # Test 2: Question mark matching
    print("Test 2: Question mark matching")
    assert matcher.match("h?llo", "hello") == True
    assert matcher.match("h?llo", "hallo") == True
    assert matcher.match("h?llo", "hllo") == False
    assert matcher.match("h??lo", "hello") == True
    assert matcher.match("h??lo", "halo") == False
    print("PASSED\n")

    # Test 3: Double star matching
    print("Test 3: Double star matching")
    assert matcher.match("a**z", "az") == True
    assert matcher.match("a**z", "abcz") == True
    assert matcher.match("a**z", "a\nb\ncz") == True
    print("PASSED\n")

    # Test 4: Match any
    print("Test 4: Match any")
    patterns = ["*.py", "*.js", "*.ts"]
    assert matcher.match_any(patterns, "file.py") == True
    assert matcher.match_any(patterns, "file.js") == True
    assert matcher.match_any(patterns, "file.txt") == False
    print("PASSED\n")

    # Test 5: Match all
    print("Test 5: Match all")
    patterns = ["test*", "*file*"]
    assert matcher.match_all(patterns, "test_file_1") == True
    assert matcher.match_all(patterns, "test_data") == False
    assert matcher.match_all(patterns, "my_file") == False
    print("PASSED\n")

    # Test 6: Extract
    print("Test 6: Extract")
    result = matcher.extract("hello *", "hello world")
    assert result is not None
    assert result['groups'] == ['world']
    result = matcher.extract("*.py", "test.py")
    assert result['groups'] == ['test']
    print("PASSED\n")

    # Test 7: Path matching
    print("Test 7: Path matching")
    assert matcher.match_path("**.py", "test.py") == True
    assert matcher.match_path("**.py", "src/test.py") == True
    assert matcher.match_path("**.py", "src/lib/test.py") == True
    assert matcher.match_path("src/**/test", "src/test") == True
    assert matcher.match_path("src/**/test", "src/a/b/c/test") == True
    assert matcher.match_path("src/*/test.py", "src/lib/test.py") == True
    assert matcher.match_path("src/*/test.py", "src/a/b/test.py") == False
    print("PASSED\n")

    # Test 8: Permission matching
    print("Test 8: Permission matching")
    assert matcher.match_permission("file.read.*", "file.read.txt") == True
    assert matcher.match_permission("file.read.*", "file.read.json") == True
    assert matcher.match_permission("file.read.*", "file.write.txt") == False
    assert matcher.match_permission("admin.**", "admin.users.create") == True
    assert matcher.match_permission("admin.**", "admin.delete") == True
    assert matcher.match_permission("*.write", "file.write") == True
    assert matcher.match_permission("*.write", "db.write") == True
    print("PASSED\n")

    # Test 9: Structured matching
    print("Test 9: Structured matching")
    assert matcher.match_structured("a * c", ["a", "b", "c"]) == True
    assert matcher.match_structured("a * c", ["a", "x", "c"]) == True
    assert matcher.match_structured("a * c", ["a", "b", "d"]) == False
    print("PASSED\n")

    # Test 10: Is pattern
    print("Test 10: Is pattern")
    assert matcher.is_pattern("*.py") == True
    assert matcher.is_pattern("test?") == True
    assert matcher.is_pattern("hello") == False
    print("PASSED\n")

    # Test 11: Normalize pattern
    print("Test 11: Normalize pattern")
    assert matcher.normalize_pattern("a***b") == "a**b"
    assert matcher.normalize_pattern("a**b") == "a**b"
    assert matcher.normalize_pattern("a****b") == "a**b"
    print("PASSED\n")

    # Test 12: Sort patterns
    print("Test 12: Sort patterns")
    patterns = ["longer_pattern", "short", "medium_one"]
    sorted_patterns = matcher.sort_patterns(patterns)
    assert sorted_patterns == ["short", "medium_one", "longer_pattern"]
    print("PASSED\n")

    # Test 13: Expand pattern
    print("Test 13: Expand pattern")
    candidates = ["file.py", "test.py", "file.js", "readme.md"]
    matches = matcher.expand_pattern("*.py", candidates)
    assert set(matches) == {"file.py", "test.py"}
    print("PASSED\n")

    # Test 14: Special characters escaping
    print("Test 14: Special characters escaping")
    assert matcher.match("test.py", "test.py") == True
    assert matcher.match("test.py", "testXpy") == False
    assert matcher.match("test[1].txt", "test[1].txt") == True
    assert matcher.match("file(2).py", "file(2).py") == True
    print("PASSED\n")

    # Test 15: Complex patterns
    print("Test 15: Complex patterns")
    assert matcher.match("src/**/*.py", "src/lib/utils/helper.py") == True
    assert matcher.match("test_*.py", "test_auth.py") == True
    assert matcher.match("*_test.py", "auth_test.py") == True
    assert matcher.match("??-??-????", "12-31-2023") == True
    print("PASSED\n")

    print("All tests passed!")
