"""
Log Rotation and Trimming Module

Prevents unbounded growth of log files in forever mode by:
1. Rotating JSONL files when they exceed size limits
2. Keeping only last N rotated files
3. Trimming in-memory lists periodically
4. Cleaning up old checkpoint files

Usage:
    from log_rotation import LogRotator, cleanup_old_checkpoints

    rotator = LogRotator(max_size_mb=10, max_rotations=5)
    rotator.rotate_if_needed(journal_file_path)
    rotator.trim_in_memory_list(my_list, max_size=1000)
    cleanup_old_checkpoints(checkpoint_dir, max_age_days=7)
"""

import json
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Any, Dict, Optional
from loguru import logger


class LogRotator:
    """
    Handles rotation of log files to prevent unbounded growth.

    Features:
    - Automatic rotation when files exceed size limit
    - Keeps only N most recent rotated files
    - Supports JSONL and JSON formats
    - Thread-safe rotation
    """

    def __init__(
        self,
        max_size_mb: float = 10.0,
        max_rotations: int = 5,
        compression: bool = False
    ):
        """
        Initialize log rotator.

        Args:
            max_size_mb: Maximum file size in MB before rotation
            max_rotations: Maximum number of rotated files to keep
            compression: Whether to compress rotated files (future feature)
        """
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        self.max_rotations = max_rotations
        self.compression = compression

    def rotate_if_needed(self, file_path: Path) -> bool:
        """
        Rotate file if it exceeds size limit.

        Args:
            file_path: Path to file to check and potentially rotate

        Returns:
            True if rotation was performed, False otherwise
        """
        if not isinstance(file_path, Path):
            file_path = Path(file_path)

        # Check if file exists and needs rotation
        if not file_path.exists():
            return False

        file_size = file_path.stat().st_size
        if file_size < self.max_size_bytes:
            return False

        # Perform rotation
        try:
            self._rotate_file(file_path)
            logger.info(f"[LOG_ROTATION] Rotated {file_path.name} ({file_size / 1024 / 1024:.2f}MB)")
            return True
        except Exception as e:
            logger.warning(f"[LOG_ROTATION] Failed to rotate {file_path}: {e}")
            return False

    def _rotate_file(self, file_path: Path):
        """
        Perform the actual file rotation.

        Renames file to file.1, shifts existing rotations (file.1 -> file.2),
        and removes oldest rotation if exceeding max_rotations.
        """
        # Shift existing rotations
        for i in range(self.max_rotations - 1, 0, -1):
            old_file = file_path.with_suffix(f"{file_path.suffix}.{i}")
            new_file = file_path.with_suffix(f"{file_path.suffix}.{i + 1}")

            if old_file.exists():
                if i == self.max_rotations - 1:
                    # Remove oldest rotation
                    old_file.unlink()
                    logger.debug(f"[LOG_ROTATION] Removed oldest rotation: {old_file.name}")
                else:
                    # Shift rotation
                    old_file.rename(new_file)

        # Rotate current file to .1
        rotated_file = file_path.with_suffix(f"{file_path.suffix}.1")
        file_path.rename(rotated_file)

        # Create new empty file
        file_path.touch()

    def trim_in_memory_list(
        self,
        data_list: List[Any],
        max_size: int,
        keep_recent: bool = True
    ) -> List[Any]:
        """
        Trim in-memory list to prevent unbounded growth.

        Args:
            data_list: List to trim
            max_size: Maximum size to keep
            keep_recent: If True, keep most recent items; if False, keep oldest

        Returns:
            Trimmed list
        """
        if len(data_list) <= max_size:
            return data_list

        if keep_recent:
            trimmed = data_list[-max_size:]
        else:
            trimmed = data_list[:max_size]

        removed_count = len(data_list) - len(trimmed)
        logger.debug(f"[LOG_ROTATION] Trimmed list from {len(data_list)} to {len(trimmed)} items ({removed_count} removed)")

        return trimmed

    def get_total_size_mb(self, file_path: Path) -> float:
        """
        Get total size of file and all its rotations.

        Args:
            file_path: Base file path

        Returns:
            Total size in MB
        """
        if not isinstance(file_path, Path):
            file_path = Path(file_path)

        total_bytes = 0

        # Main file
        if file_path.exists():
            total_bytes += file_path.stat().st_size

        # Rotated files
        for i in range(1, self.max_rotations + 1):
            rotated = file_path.with_suffix(f"{file_path.suffix}.{i}")
            if rotated.exists():
                total_bytes += rotated.stat().st_size

        return total_bytes / 1024 / 1024


class JSONLRotator(LogRotator):
    """
    Specialized rotator for JSONL files with line-based rotation.

    Can rotate based on:
    - File size (bytes)
    - Number of lines
    - Age (time-based)
    """

    def __init__(
        self,
        max_size_mb: float = 10.0,
        max_lines: Optional[int] = None,
        max_age_hours: Optional[float] = None,
        max_rotations: int = 5
    ):
        """
        Initialize JSONL rotator.

        Args:
            max_size_mb: Maximum file size in MB
            max_lines: Maximum number of lines before rotation
            max_age_hours: Maximum file age in hours before rotation
            max_rotations: Maximum rotated files to keep
        """
        super().__init__(max_size_mb=max_size_mb, max_rotations=max_rotations)
        self.max_lines = max_lines
        self.max_age_hours = max_age_hours

    def should_rotate(self, file_path: Path) -> bool:
        """
        Check if file should be rotated based on multiple criteria.

        Args:
            file_path: Path to JSONL file

        Returns:
            True if rotation is needed
        """
        if not isinstance(file_path, Path):
            file_path = Path(file_path)

        if not file_path.exists():
            return False

        # Check size
        if file_path.stat().st_size >= self.max_size_bytes:
            return True

        # Check line count
        if self.max_lines is not None:
            try:
                line_count = sum(1 for _ in open(file_path, 'r'))
                if line_count >= self.max_lines:
                    logger.debug(f"[LOG_ROTATION] {file_path.name} has {line_count} lines, exceeds max {self.max_lines}")
                    return True
            except (IOError, OSError) as e:
                logger.warning(f"[LOG_ROTATION] Failed to count lines in {file_path}: {e}")
                pass

        # Check age
        if self.max_age_hours is not None:
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                age_hours = (datetime.now() - mtime).total_seconds() / 3600
                if age_hours >= self.max_age_hours:
                    logger.debug(f"[LOG_ROTATION] {file_path.name} is {age_hours:.1f}h old, exceeds max {self.max_age_hours}h")
                    return True
            except (OSError, ValueError) as e:
                logger.warning(f"[LOG_ROTATION] Failed to check age of {file_path}: {e}")
                pass

        return False

    def trim_to_lines(self, file_path: Path, max_lines: int):
        """
        Trim JSONL file to keep only last N lines.

        Args:
            file_path: Path to JSONL file
            max_lines: Maximum lines to keep
        """
        if not isinstance(file_path, Path):
            file_path = Path(file_path)

        if not file_path.exists():
            return

        try:
            # Read all lines
            with open(file_path, 'r') as f:
                lines = f.readlines()

            if len(lines) <= max_lines:
                return

            # Keep only last max_lines
            kept_lines = lines[-max_lines:]

            # Write back
            with open(file_path, 'w') as f:
                f.writelines(kept_lines)

            removed = len(lines) - len(kept_lines)
            logger.info(f"[LOG_ROTATION] Trimmed {file_path.name} from {len(lines)} to {len(kept_lines)} lines ({removed} removed)")

        except Exception as e:
            logger.warning(f"[LOG_ROTATION] Failed to trim {file_path}: {e}")


def cleanup_old_checkpoints(
    checkpoint_dir: Path,
    max_age_days: int = 7,
    exclude_patterns: Optional[List[str]] = None
) -> int:
    """
    Remove old checkpoint files.

    Args:
        checkpoint_dir: Directory containing checkpoint files
        max_age_days: Remove files older than this many days
        exclude_patterns: List of glob patterns to exclude from cleanup

    Returns:
        Number of files removed
    """
    if not isinstance(checkpoint_dir, Path):
        checkpoint_dir = Path(checkpoint_dir)

    if not checkpoint_dir.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=max_age_days)
    exclude_patterns = exclude_patterns or []
    removed = 0

    try:
        for file_path in checkpoint_dir.glob('*.json'):
            # Check if file matches exclusion pattern
            excluded = False
            for pattern in exclude_patterns:
                if file_path.match(pattern):
                    excluded = True
                    break

            if excluded:
                continue

            # Check file age
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime < cutoff:
                    file_path.unlink()
                    removed += 1
            except (OSError, ValueError) as e:
                logger.debug(f"[LOG_ROTATION] Failed to remove {file_path}: {e}")
                pass

        if removed > 0:
            logger.info(f"[LOG_ROTATION] Cleaned up {removed} old checkpoint files from {checkpoint_dir}")

        return removed

    except Exception as e:
        logger.warning(f"[LOG_ROTATION] Failed to cleanup checkpoints: {e}")
        return 0


def cleanup_rotated_logs(
    log_dir: Path,
    max_age_days: int = 30,
    patterns: Optional[List[str]] = None
) -> int:
    """
    Remove old rotated log files.

    Args:
        log_dir: Directory containing log files
        max_age_days: Remove rotated files older than this many days
        patterns: List of file patterns to clean (e.g., ['*.log.*', '*.jsonl.*'])

    Returns:
        Number of files removed
    """
    if not isinstance(log_dir, Path):
        log_dir = Path(log_dir)

    if not log_dir.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=max_age_days)
    patterns = patterns or ['*.log.*', '*.jsonl.*', '*.json.*']
    removed = 0

    try:
        for pattern in patterns:
            for file_path in log_dir.glob(pattern):
                try:
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mtime < cutoff:
                        file_path.unlink()
                        removed += 1
                except (OSError, ValueError) as e:
                    logger.debug(f"[LOG_ROTATION] Failed to remove {file_path}: {e}")
                    pass

        if removed > 0:
            logger.info(f"[LOG_ROTATION] Cleaned up {removed} old rotated log files from {log_dir}")

        return removed

    except Exception as e:
        logger.warning(f"[LOG_ROTATION] Failed to cleanup rotated logs: {e}")
        return 0


def get_disk_usage_summary(work_dir: Path) -> Dict[str, Any]:
    """
    Get disk usage summary for worker directory.

    Args:
        work_dir: Worker directory to analyze

    Returns:
        Dictionary with usage statistics
    """
    if not isinstance(work_dir, Path):
        work_dir = Path(work_dir)

    if not work_dir.exists():
        return {"error": "Directory does not exist"}

    summary = {
        "total_size_mb": 0.0,
        "file_count": 0,
        "by_extension": {},
        "largest_files": []
    }

    try:
        files_with_sizes = []

        for file_path in work_dir.rglob('*'):
            if file_path.is_file():
                try:
                    size = file_path.stat().st_size
                    size_mb = size / 1024 / 1024

                    summary["total_size_mb"] += size_mb
                    summary["file_count"] += 1

                    # Track by extension
                    ext = file_path.suffix or 'no_extension'
                    if ext not in summary["by_extension"]:
                        summary["by_extension"][ext] = {"count": 0, "size_mb": 0.0}
                    summary["by_extension"][ext]["count"] += 1
                    summary["by_extension"][ext]["size_mb"] += size_mb

                    # Track for largest files
                    files_with_sizes.append((str(file_path), size_mb))

                except (OSError, ValueError) as e:
                    logger.debug(f"[LOG_ROTATION] Failed to stat {file_path}: {e}")
                    pass

        # Get top 10 largest files
        files_with_sizes.sort(key=lambda x: -x[1])
        summary["largest_files"] = [
            {"path": p, "size_mb": round(s, 2)}
            for p, s in files_with_sizes[:10]
        ]

        # Round totals
        summary["total_size_mb"] = round(summary["total_size_mb"], 2)
        for ext in summary["by_extension"]:
            summary["by_extension"][ext]["size_mb"] = round(
                summary["by_extension"][ext]["size_mb"], 2
            )

        return summary

    except Exception as e:
        logger.warning(f"[LOG_ROTATION] Failed to get disk usage: {e}")
        return {"error": str(e)}


# Convenience function for periodic cleanup
def periodic_cleanup(
    work_dir: Path,
    checkpoint_dir: Path,
    checkpoint_age_days: int = 7,
    rotated_logs_age_days: int = 30
) -> Dict[str, int]:
    """
    Run all cleanup operations in one call.

    Args:
        work_dir: Worker work directory
        checkpoint_dir: Checkpoint directory
        checkpoint_age_days: Max age for checkpoints
        rotated_logs_age_days: Max age for rotated logs

    Returns:
        Dictionary with cleanup statistics
    """
    stats = {
        "checkpoints_removed": 0,
        "rotated_logs_removed": 0
    }

    # Cleanup old checkpoints
    stats["checkpoints_removed"] = cleanup_old_checkpoints(
        checkpoint_dir,
        max_age_days=checkpoint_age_days
    )

    # Cleanup old rotated logs
    stats["rotated_logs_removed"] = cleanup_rotated_logs(
        work_dir,
        max_age_days=rotated_logs_age_days
    )

    logger.info(
        f"[LOG_ROTATION] Periodic cleanup complete: "
        f"{stats['checkpoints_removed']} checkpoints, "
        f"{stats['rotated_logs_removed']} rotated logs removed"
    )

    return stats
