"""
Search Handler Module - Grep and Glob operations for LLM agents.

Borrowed from OpenCode's search patterns:
- Glob file search with result limiting
- Grep content search with context
- Smart output formatting
"""

import os
import re
import fnmatch
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

MAX_RESULTS = 100  # Maximum files/matches to return
MAX_LINE_LENGTH = 2000  # Truncate lines longer than this
DEFAULT_CONTEXT_LINES = 2  # Lines before/after match


@dataclass
class SearchMatch:
    """A single search match."""
    file_path: str
    line_number: int
    content: str
    context_before: List[str] = field(default_factory=list)
    context_after: List[str] = field(default_factory=list)


@dataclass
class GlobResult:
    """Result of a glob search."""
    files: List[str]
    total_found: int
    truncated: bool
    pattern: str
    search_path: str

    def to_llm_format(self) -> str:
        """Format for LLM consumption."""
        parts = []

        if not self.files:
            return f"No files found matching '{self.pattern}' in {self.search_path}"

        parts.append(f"Found {self.total_found} files matching '{self.pattern}':")

        if self.truncated:
            parts.append(f"(Showing first {len(self.files)} - use more specific pattern)")

        parts.append("")
        for f in self.files:
            parts.append(f"  {f}")

        return "\n".join(parts)


@dataclass
class GrepResult:
    """Result of a grep search."""
    matches: List[SearchMatch]
    total_matches: int
    files_searched: int
    truncated: bool
    pattern: str

    def to_llm_format(self) -> str:
        """Format for LLM consumption."""
        parts = []

        if not self.matches:
            return f"No matches found for pattern '{self.pattern}'"

        parts.append(f"Found {self.total_matches} matches in {self.files_searched} files:")

        if self.truncated:
            parts.append(f"(Showing first {len(self.matches)} matches)")

        parts.append("")

        # Group by file
        by_file: Dict[str, List[SearchMatch]] = {}
        for match in self.matches:
            if match.file_path not in by_file:
                by_file[match.file_path] = []
            by_file[match.file_path].append(match)

        for file_path, file_matches in by_file.items():
            parts.append(f"--- {file_path} ---")
            for match in file_matches:
                # Show context before
                for ctx in match.context_before:
                    parts.append(f"    {ctx}")

                # Show match with line number
                line = match.content
                if len(line) > MAX_LINE_LENGTH:
                    line = line[:MAX_LINE_LENGTH] + "..."
                parts.append(f"  {match.line_number}: {line}")

                # Show context after
                for ctx in match.context_after:
                    parts.append(f"    {ctx}")

            parts.append("")

        return "\n".join(parts)


class SearchHandler:
    """
    Handle search operations for LLM agents.

    Features:
    - Glob file pattern matching
    - Grep content searching with regex
    - Result limiting and truncation
    - Sort by modification time
    """

    def __init__(
        self,
        max_results: int = MAX_RESULTS,
        max_line_length: int = MAX_LINE_LENGTH
    ):
        self.max_results = max_results
        self.max_line_length = max_line_length

    def glob_search(
        self,
        pattern: str,
        path: str = ".",
        include_hidden: bool = False
    ) -> GlobResult:
        """
        Search for files matching glob pattern.

        Args:
            pattern: Glob pattern (e.g., "*.py", "**/*.ts")
            path: Directory to search in
            include_hidden: Include hidden files/dirs

        Returns:
            GlobResult with matching files
        """
        search_path = os.path.abspath(path)

        if not os.path.exists(search_path):
            return GlobResult(
                files=[],
                total_found=0,
                truncated=False,
                pattern=pattern,
                search_path=search_path
            )

        results = []
        total_found = 0

        try:
            # Use Path.glob for recursive patterns
            base = Path(search_path)

            for file_path in base.glob(pattern):
                # Skip hidden files unless requested
                if not include_hidden:
                    if any(part.startswith('.') for part in file_path.parts):
                        continue

                total_found += 1

                if len(results) < self.max_results:
                    results.append(str(file_path))

            # Sort by modification time (newest first)
            results.sort(key=lambda x: os.path.getmtime(x), reverse=True)

            return GlobResult(
                files=results,
                total_found=total_found,
                truncated=total_found > len(results),
                pattern=pattern,
                search_path=search_path
            )

        except Exception as e:
            logger.warning(f"Glob search error: {e}")
            return GlobResult(
                files=[],
                total_found=0,
                truncated=False,
                pattern=pattern,
                search_path=search_path
            )

    def grep_search(
        self,
        pattern: str,
        path: str = ".",
        file_pattern: Optional[str] = None,
        context_lines: int = DEFAULT_CONTEXT_LINES,
        case_sensitive: bool = True,
        use_regex: bool = True
    ) -> GrepResult:
        """
        Search file contents for pattern.

        Args:
            pattern: Search pattern (regex or literal)
            path: File or directory to search
            file_pattern: Glob pattern to filter files (e.g., "*.py")
            context_lines: Lines before/after match to include
            case_sensitive: Case sensitive search
            use_regex: Treat pattern as regex

        Returns:
            GrepResult with matches
        """
        search_path = os.path.abspath(path)

        if not os.path.exists(search_path):
            return GrepResult(
                matches=[],
                total_matches=0,
                files_searched=0,
                truncated=False,
                pattern=pattern
            )

        # Compile regex
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            if use_regex:
                regex = re.compile(pattern, flags)
            else:
                regex = re.compile(re.escape(pattern), flags)
        except re.error as e:
            logger.warning(f"Invalid regex pattern: {e}")
            return GrepResult(
                matches=[],
                total_matches=0,
                files_searched=0,
                truncated=False,
                pattern=pattern
            )

        matches = []
        total_matches = 0
        files_searched = 0

        # Get files to search
        if os.path.isfile(search_path):
            files_to_search = [search_path]
        else:
            if file_pattern:
                glob_result = self.glob_search(file_pattern, search_path)
                files_to_search = glob_result.files
            else:
                # Search all text files
                glob_result = self.glob_search("**/*", search_path)
                files_to_search = [f for f in glob_result.files if self._is_text_file(f)]

        for file_path in files_to_search:
            if len(matches) >= self.max_results:
                break

            file_matches = self._search_file(
                file_path, regex, context_lines
            )

            if file_matches:
                files_searched += 1
                for match in file_matches:
                    total_matches += 1
                    if len(matches) < self.max_results:
                        matches.append(match)

        return GrepResult(
            matches=matches,
            total_matches=total_matches,
            files_searched=files_searched,
            truncated=total_matches > len(matches),
            pattern=pattern
        )

    def _search_file(
        self,
        file_path: str,
        regex: re.Pattern,
        context_lines: int
    ) -> List[SearchMatch]:
        """Search a single file for matches."""
        matches = []

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            for i, line in enumerate(lines):
                line = line.rstrip('\n\r')

                if regex.search(line):
                    # Get context
                    context_before = []
                    context_after = []

                    for j in range(max(0, i - context_lines), i):
                        context_before.append(lines[j].rstrip('\n\r'))

                    for j in range(i + 1, min(len(lines), i + context_lines + 1)):
                        context_after.append(lines[j].rstrip('\n\r'))

                    matches.append(SearchMatch(
                        file_path=file_path,
                        line_number=i + 1,
                        content=line,
                        context_before=context_before,
                        context_after=context_after
                    ))

        except Exception as e:
            logger.debug(f"Error searching {file_path}: {e}")

        return matches

    def _is_text_file(self, path: str) -> bool:
        """Check if file is likely a text file."""
        # Check extension
        text_extensions = {
            '.py', '.js', '.ts', '.jsx', '.tsx', '.vue', '.svelte',
            '.html', '.css', '.scss', '.sass', '.less',
            '.json', '.yaml', '.yml', '.toml', '.xml',
            '.md', '.txt', '.rst', '.csv',
            '.sh', '.bash', '.zsh', '.fish',
            '.sql', '.graphql',
            '.go', '.rs', '.rb', '.php', '.java', '.c', '.cpp', '.h',
            '.env', '.gitignore', '.dockerignore',
            'Makefile', 'Dockerfile', 'Procfile',
        }

        ext = Path(path).suffix.lower()
        name = Path(path).name

        if ext in text_extensions or name in text_extensions:
            return True

        # Check if no extension (might be script)
        if not ext:
            return True

        return False

    def ripgrep_search(
        self,
        pattern: str,
        path: str = ".",
        file_type: Optional[str] = None,
        context_lines: int = DEFAULT_CONTEXT_LINES
    ) -> GrepResult:
        """
        Search using ripgrep if available (faster for large codebases).

        Args:
            pattern: Search pattern
            path: Directory to search
            file_type: File type filter (e.g., "py", "js")
            context_lines: Context lines to show

        Returns:
            GrepResult with matches
        """
        try:
            # Check if ripgrep is available
            subprocess.run(['rg', '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fall back to Python grep
            return self.grep_search(pattern, path, context_lines=context_lines)

        search_path = os.path.abspath(path)

        cmd = [
            'rg',
            '--line-number',
            '--with-filename',
            f'--context={context_lines}',
            '--max-count=100',
        ]

        if file_type:
            cmd.extend(['--type', file_type])

        cmd.extend([pattern, search_path])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            matches = self._parse_ripgrep_output(result.stdout)

            return GrepResult(
                matches=matches,
                total_matches=len(matches),
                files_searched=len(set(m.file_path for m in matches)),
                truncated=False,
                pattern=pattern
            )

        except subprocess.TimeoutExpired:
            logger.warning("Ripgrep search timed out")
            return GrepResult(
                matches=[],
                total_matches=0,
                files_searched=0,
                truncated=False,
                pattern=pattern
            )
        except Exception as e:
            logger.warning(f"Ripgrep error: {e}")
            return self.grep_search(pattern, path, context_lines=context_lines)

    def _parse_ripgrep_output(self, output: str) -> List[SearchMatch]:
        """Parse ripgrep output into SearchMatch objects."""
        matches = []
        current_file = None
        current_match = None

        for line in output.split('\n'):
            if not line.strip():
                continue

            # Context separator
            if line == '--':
                if current_match:
                    matches.append(current_match)
                    current_match = None
                continue

            # Parse line (format: file:line:content or file-line-content for context)
            match = re.match(r'^(.+?)[:-](\d+)[:-](.*)$', line)
            if match:
                file_path, line_num, content = match.groups()
                is_match = ':' in line[:len(file_path) + len(line_num) + 2]

                if is_match:
                    if current_match:
                        matches.append(current_match)

                    current_match = SearchMatch(
                        file_path=file_path,
                        line_number=int(line_num),
                        content=content
                    )
                elif current_match:
                    if int(line_num) < current_match.line_number:
                        current_match.context_before.append(content)
                    else:
                        current_match.context_after.append(content)

        if current_match:
            matches.append(current_match)

        return matches


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_default_handler = None


def get_search_handler() -> SearchHandler:
    """Get the default search handler singleton."""
    global _default_handler
    if _default_handler is None:
        _default_handler = SearchHandler()
    return _default_handler


def glob_files(pattern: str, path: str = ".") -> List[str]:
    """Quick glob search helper."""
    handler = get_search_handler()
    result = handler.glob_search(pattern, path)
    return result.files


def grep_content(pattern: str, path: str = ".", file_pattern: Optional[str] = None) -> str:
    """Quick grep search helper."""
    handler = get_search_handler()
    result = handler.grep_search(pattern, path, file_pattern)
    return result.to_llm_format()


def find_files_by_name(name: str, path: str = ".") -> List[str]:
    """Find files by exact name."""
    handler = get_search_handler()
    result = handler.glob_search(f"**/{name}", path)
    return result.files


def find_files_containing(pattern: str, path: str = ".") -> List[str]:
    """Find files containing pattern."""
    handler = get_search_handler()
    result = handler.grep_search(pattern, path)
    return list(set(m.file_path for m in result.matches))


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    handler = SearchHandler()

    # Test glob
    print("=== GLOB TEST ===")
    result = handler.glob_search("*.py", ".")
    print(f"Found {len(result.files)} Python files")
    print(result.to_llm_format()[:500])

    # Test grep
    print("\n=== GREP TEST ===")
    result = handler.grep_search("def ", ".", file_pattern="*.py")
    print(f"Found {result.total_matches} function definitions")
    print(result.to_llm_format()[:500])

    print("\nAll tests passed!")
