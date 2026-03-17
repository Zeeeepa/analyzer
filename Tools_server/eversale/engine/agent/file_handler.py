"""
File Handler Module - Smart file operations for LLM agents.

Borrowed from OpenCode's file handling patterns:
- Binary detection
- Line truncation
- Smart reading with offset/limit
- File type detection
"""

import os
import mimetypes
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass, field
from loguru import logger
import fnmatch

# =============================================================================
# CONSTANTS
# =============================================================================

MAX_LINE_LENGTH = 2000  # Truncate lines longer than this
DEFAULT_READ_LIMIT = 2000  # Default lines to read
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB max for text files
BINARY_CHECK_SIZE = 4096  # Bytes to check for binary detection

# Known binary extensions
BINARY_EXTENSIONS = {
    # Archives
    '.zip', '.tar', '.gz', '.bz2', '.7z', '.rar', '.xz',
    # Images
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.svg',
    # Documents
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    # Executables
    '.exe', '.dll', '.so', '.dylib', '.bin', '.app',
    # Media
    '.mp3', '.mp4', '.avi', '.mov', '.wav', '.flac', '.mkv',
    # Data
    '.sqlite', '.db', '.pyc', '.pyo', '.wasm', '.class',
    # Fonts
    '.ttf', '.otf', '.woff', '.woff2', '.eot',
}

# Protected files that shouldn't be read/written
# Format: (pattern, match_type) where match_type is 'exact', 'glob', or 'extension'
PROTECTED_PATTERNS = [
    # Environment files - exact filenames
    ('.env', 'exact'),
    ('.env.local', 'exact'),
    ('.env.production', 'exact'),
    ('.env.development', 'exact'),
    ('.env.test', 'exact'),
    ('.env.*', 'glob'),  # Match .env.anything

    # SSH keys - exact filenames and extensions
    ('id_rsa', 'exact'),
    ('id_dsa', 'exact'),
    ('id_ecdsa', 'exact'),
    ('id_ed25519', 'exact'),
    ('.pem', 'extension'),
    ('.key', 'extension'),
    ('.p12', 'extension'),
    ('.pfx', 'extension'),

    # Credentials - exact filenames
    ('credentials.json', 'exact'),
    ('secrets.yaml', 'exact'),
    ('secrets.yml', 'exact'),
    ('config.json', 'exact'),  # Often contains secrets

    # Cloud provider credentials
    ('.aws/credentials', 'glob'),
    ('.azure/credentials', 'glob'),
    ('gcloud/credentials', 'glob'),

    # Private keys and certificates
    ('*.key', 'glob'),
    ('*.pem', 'glob'),
    ('*_rsa', 'glob'),
    ('*_dsa', 'glob'),
]


@dataclass
class FileMetadata:
    """Metadata about a file."""
    path: str
    size: int
    is_binary: bool
    is_protected: bool
    extension: str
    mime_type: Optional[str] = None
    line_count: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "size": self.size,
            "is_binary": self.is_binary,
            "is_protected": self.is_protected,
            "extension": self.extension,
            "mime_type": self.mime_type,
            "line_count": self.line_count,
        }


@dataclass
class ReadResult:
    """Result of a file read operation."""
    success: bool
    content: str
    metadata: FileMetadata
    truncated: bool = False
    total_lines: int = 0
    lines_read: int = 0
    error: Optional[str] = None

    def to_llm_format(self) -> str:
        """Format for LLM consumption."""
        parts = []

        if not self.success:
            return f"Error reading {self.metadata.path}: {self.error}"

        if self.metadata.is_binary:
            return f"[Binary file: {self.metadata.path} ({self.metadata.size} bytes)]"

        # Add header
        parts.append(f"File: {self.metadata.path}")

        if self.truncated:
            parts.append(f"[Showing lines 1-{self.lines_read} of {self.total_lines}]")

        parts.append("")
        parts.append(self.content)

        return "\n".join(parts)


class FileHandler:
    """
    Handle file operations for LLM agents.

    Features:
    - Binary detection (extension + content analysis)
    - Line truncation for long lines
    - Offset/limit reading for large files
    - Protected file detection
    - Path traversal protection with workspace boundary validation
    """

    def __init__(
        self,
        max_line_length: int = MAX_LINE_LENGTH,
        default_limit: int = DEFAULT_READ_LIMIT,
        allow_protected: bool = False,
        workspace_root: Optional[str] = None
    ):
        self.max_line_length = max_line_length
        self.default_limit = default_limit
        self.allow_protected = allow_protected

        # Set workspace root for boundary validation
        if workspace_root:
            self.workspace_root = Path(workspace_root).resolve()
        else:
            # Default to current working directory
            self.workspace_root = Path.cwd().resolve()

        logger.debug(f"FileHandler initialized with workspace_root: {self.workspace_root}")

    def is_binary_extension(self, path: str) -> bool:
        """Check if file has binary extension."""
        ext = Path(path).suffix.lower()
        return ext in BINARY_EXTENSIONS

    def is_binary_content(self, content: bytes) -> bool:
        """
        Check if content appears to be binary.

        Multi-layered approach:
        1. Check for null bytes
        2. Count non-printable characters
        3. Flag if >30% non-printable
        """
        if not content:
            return False

        # Check for null bytes
        if b'\x00' in content:
            return True

        # Count non-printable characters
        non_printable = 0
        for byte in content:
            # Control characters (except tab, newline, carriage return)
            if byte < 9 or (13 < byte < 32):
                non_printable += 1

        # Flag as binary if >30% non-printable
        ratio = non_printable / len(content)
        return ratio > 0.3

    def validate_path(self, path: str) -> Tuple[bool, str, Optional[Path]]:
        """
        Validate path for security issues.

        Returns:
            (is_valid, error_message, resolved_path)
        """
        try:
            # Convert to Path object and resolve to canonical form
            # This resolves symlinks, removes ../, ./, etc.
            resolved = Path(path).resolve(strict=False)

            # Check for path traversal attempts
            # The resolved path must be within workspace_root
            try:
                resolved.relative_to(self.workspace_root)
            except ValueError:
                return False, f"Path outside workspace boundary: {path}", None

            # Additional checks for suspicious patterns
            path_str = str(resolved)
            if '..' in path_str.split(os.sep):
                return False, f"Path contains suspicious traversal patterns: {path}", None

            return True, "", resolved

        except Exception as e:
            return False, f"Invalid path: {e}", None

    def is_protected_file(self, path: str) -> Tuple[bool, str]:
        """
        Check if file is protected using exact matching, glob patterns, or extensions.

        Args:
            path: File path to check

        Returns:
            (is_protected, reason)
        """
        # Get the filename and full path
        filename = Path(path).name
        filename_lower = filename.lower()
        path_lower = str(path).lower()

        for pattern, match_type in PROTECTED_PATTERNS:
            pattern_lower = pattern.lower()

            if match_type == 'exact':
                # Exact filename match
                if filename_lower == pattern_lower:
                    return True, f"Protected file (exact match): {pattern}"

            elif match_type == 'extension':
                # Extension match (e.g., .pem, .key)
                if filename_lower.endswith(pattern_lower):
                    # Ensure it's actually an extension, not just ending with those chars
                    if pattern_lower.startswith('.'):
                        ext = Path(filename).suffix.lower()
                        if ext == pattern_lower:
                            return True, f"Protected file extension: {pattern}"

            elif match_type == 'glob':
                # Glob pattern match (e.g., *.key, .env.*)
                if fnmatch.fnmatch(filename_lower, pattern_lower):
                    return True, f"Protected file (glob match): {pattern}"

                # Also check against full path for patterns like .aws/credentials
                if fnmatch.fnmatch(path_lower, f"*{pattern_lower}"):
                    return True, f"Protected file path (glob match): {pattern}"

        return False, ""

    def get_metadata(self, path: str) -> FileMetadata:
        """Get file metadata without reading content."""
        # Validate path first
        is_valid, error_msg, resolved = self.validate_path(path)

        if not is_valid:
            # Return metadata with error information
            logger.warning(f"Path validation failed: {error_msg}")
            return FileMetadata(
                path=str(path),
                size=0,
                is_binary=False,
                is_protected=True,  # Mark as protected to prevent access
                extension="",
                mime_type=None,
            )

        abs_path = str(resolved)

        try:
            stat = os.stat(abs_path)
            size = stat.st_size
        except OSError:
            size = 0

        ext = Path(abs_path).suffix.lower()
        mime_type, _ = mimetypes.guess_type(abs_path)

        is_protected, _ = self.is_protected_file(abs_path)
        is_binary = self.is_binary_extension(abs_path)

        return FileMetadata(
            path=abs_path,
            size=size,
            is_binary=is_binary,
            is_protected=is_protected,
            extension=ext,
            mime_type=mime_type,
        )

    def read_file(
        self,
        path: str,
        offset: int = 0,
        limit: Optional[int] = None
    ) -> ReadResult:
        """
        Read a file with smart handling.

        Args:
            path: File path to read
            offset: Line number to start from (0-based)
            limit: Maximum lines to read (default: 2000)

        Returns:
            ReadResult with content and metadata
        """
        if limit is None:
            limit = self.default_limit

        # Validate path for security
        is_valid, error_msg, resolved = self.validate_path(path)

        if not is_valid:
            metadata = FileMetadata(
                path=str(path),
                size=0,
                is_binary=False,
                is_protected=True,
                extension="",
            )
            return ReadResult(
                success=False,
                content="",
                metadata=metadata,
                error=f"Path validation failed: {error_msg}"
            )

        abs_path = str(resolved)
        metadata = self.get_metadata(abs_path)

        # Check if file exists
        if not os.path.exists(abs_path):
            # Try fuzzy matching
            suggestions = self._find_similar_files(path)
            error_msg = f"File not found: {path}"
            if suggestions:
                error_msg += f". Did you mean: {', '.join(suggestions[:3])}"

            return ReadResult(
                success=False,
                content="",
                metadata=metadata,
                error=error_msg
            )

        # Check protected
        if metadata.is_protected and not self.allow_protected:
            is_protected, reason = self.is_protected_file(abs_path)
            return ReadResult(
                success=False,
                content="",
                metadata=metadata,
                error=f"Protected file: {reason}"
            )

        # Check binary by extension
        if metadata.is_binary:
            return ReadResult(
                success=True,
                content=f"[Binary file: {metadata.size} bytes]",
                metadata=metadata,
            )

        # Check file size
        if metadata.size > MAX_FILE_SIZE:
            return ReadResult(
                success=False,
                content="",
                metadata=metadata,
                error=f"File too large: {metadata.size} bytes (max {MAX_FILE_SIZE})"
            )

        try:
            # Read and check for binary content
            with open(abs_path, 'rb') as f:
                header = f.read(BINARY_CHECK_SIZE)
                if self.is_binary_content(header):
                    metadata.is_binary = True
                    return ReadResult(
                        success=True,
                        content=f"[Binary file detected: {metadata.size} bytes]",
                        metadata=metadata,
                    )

            # Read as text
            with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                all_lines = f.readlines()

            total_lines = len(all_lines)
            metadata.line_count = total_lines

            # Apply offset and limit
            selected_lines = all_lines[offset:offset + limit]
            lines_read = len(selected_lines)

            # Truncate long lines
            truncated_lines = []
            for line in selected_lines:
                line = line.rstrip('\n\r')
                if len(line) > self.max_line_length:
                    line = line[:self.max_line_length] + "..."
                truncated_lines.append(line)

            # Format with line numbers
            content_lines = []
            for i, line in enumerate(truncated_lines, start=offset + 1):
                content_lines.append(f"{i:6}| {line}")

            content = '\n'.join(content_lines)
            truncated = (offset + lines_read) < total_lines

            return ReadResult(
                success=True,
                content=content,
                metadata=metadata,
                truncated=truncated,
                total_lines=total_lines,
                lines_read=lines_read,
            )

        except UnicodeDecodeError:
            metadata.is_binary = True
            return ReadResult(
                success=True,
                content=f"[Binary/non-UTF8 file: {metadata.size} bytes]",
                metadata=metadata,
            )
        except Exception as e:
            return ReadResult(
                success=False,
                content="",
                metadata=metadata,
                error=str(e)
            )

    def _find_similar_files(self, path: str, max_results: int = 3) -> List[str]:
        """Find similar file names for suggestions."""
        target_name = Path(path).name.lower()
        target_dir = Path(path).parent

        if not target_dir.exists():
            target_dir = Path('.')

        suggestions = []
        try:
            for file in target_dir.iterdir():
                if file.is_file():
                    similarity = self._string_similarity(target_name, file.name.lower())
                    if similarity > 0.5:
                        suggestions.append((similarity, str(file)))

            suggestions.sort(reverse=True)
            return [s[1] for s in suggestions[:max_results]]
        except Exception:
            return []

    def _string_similarity(self, s1: str, s2: str) -> float:
        """Calculate simple string similarity."""
        if not s1 or not s2:
            return 0.0

        # Simple Jaccard similarity on characters
        set1 = set(s1)
        set2 = set(s2)
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    def write_file(
        self,
        path: str,
        content: str,
        create_dirs: bool = True
    ) -> Tuple[bool, str]:
        """
        Write content to a file.

        Args:
            path: File path to write
            content: Content to write
            create_dirs: Create parent directories if needed

        Returns:
            (success, message)
        """
        # Validate path for security
        is_valid, error_msg, resolved = self.validate_path(path)

        if not is_valid:
            return False, f"Path validation failed: {error_msg}"

        abs_path = str(resolved)

        # Check protected
        is_protected, reason = self.is_protected_file(abs_path)
        if is_protected and not self.allow_protected:
            return False, f"Cannot write to protected file: {reason}"

        try:
            # Create parent directories
            if create_dirs:
                parent_dir = Path(abs_path).parent

                # Validate parent directory is also within workspace
                is_parent_valid, parent_error, _ = self.validate_path(str(parent_dir))
                if not is_parent_valid:
                    return False, f"Parent directory validation failed: {parent_error}"

                parent_dir.mkdir(parents=True, exist_ok=True)

            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(content)

            return True, f"Successfully wrote {len(content)} bytes to {abs_path}"

        except Exception as e:
            return False, f"Failed to write: {e}"

    def list_directory(
        self,
        path: str = ".",
        pattern: str = "*",
        max_results: int = 100
    ) -> Tuple[List[str], bool]:
        """
        List files in directory matching pattern.

        Args:
            path: Directory path
            pattern: Glob pattern
            max_results: Maximum files to return

        Returns:
            (files, truncated)
        """
        # Validate path for security
        is_valid, error_msg, resolved = self.validate_path(path)

        if not is_valid:
            logger.warning(f"Path validation failed in list_directory: {error_msg}")
            return [], False

        abs_path = resolved

        if not abs_path.exists():
            return [], False

        if not abs_path.is_dir():
            return [str(abs_path)], False

        results = []
        try:
            for file in abs_path.glob(pattern):
                # Validate each result is within workspace
                file_valid, _, _ = self.validate_path(str(file))
                if file_valid:
                    results.append(str(file))
                    if len(results) >= max_results:
                        return results, True

            # Sort by modification time (newest first)
            results.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            return results, False

        except Exception as e:
            logger.warning(f"Error listing directory: {e}")
            return [], False


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_default_handler = None


def get_file_handler() -> FileHandler:
    """Get the default file handler singleton."""
    global _default_handler
    if _default_handler is None:
        _default_handler = FileHandler()
    return _default_handler


def read_file(path: str, offset: int = 0, limit: Optional[int] = None) -> str:
    """Quick file read helper."""
    handler = get_file_handler()
    result = handler.read_file(path, offset, limit)
    return result.to_llm_format()


def is_binary(path: str) -> bool:
    """Quick binary check helper."""
    handler = get_file_handler()
    metadata = handler.get_metadata(path)
    return metadata.is_binary


def file_exists(path: str) -> bool:
    """Check if file exists."""
    return os.path.exists(os.path.abspath(path))


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    handler = FileHandler()

    # Test reading this file
    result = handler.read_file(__file__, limit=20)
    print("=== READ TEST ===")
    print(f"Success: {result.success}")
    print(f"Lines: {result.lines_read}/{result.total_lines}")
    print(f"Truncated: {result.truncated}")
    print(result.content[:500])

    # Test binary detection
    print("\n=== BINARY DETECTION ===")
    print(f".png is binary: {handler.is_binary_extension('test.png')}")
    print(f".py is binary: {handler.is_binary_extension('test.py')}")

    # Test protected detection
    print("\n=== PROTECTED DETECTION ===")
    print(f".env protected: {handler.is_protected_file('.env')}")
    print(f"main.py protected: {handler.is_protected_file('main.py')}")

    print("\nAll tests passed!")
