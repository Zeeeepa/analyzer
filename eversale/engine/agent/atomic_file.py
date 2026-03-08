"""
Atomic File Operations - Prevent corruption on crash.

Provides atomic write operations for JSON and text files to prevent
corruption if the process crashes mid-write.
"""

import json
import shutil
from pathlib import Path
from typing import Any, Dict
from loguru import logger


def atomic_write_json(path: Path, data: Dict[str, Any], indent: int = 2, backup: bool = True):
    """
    Write JSON atomically to prevent corruption.

    Args:
        path: Target file path
        data: Data to serialize as JSON
        indent: JSON indentation (default 2)
        backup: Create .bak backup before overwriting (default True)

    The write process:
    1. Create backup of existing file (if backup=True and file exists)
    2. Write to temp file in same directory
    3. Atomic rename of temp file to target (POSIX atomic, near-atomic on Windows)
    4. Clean up temp file on error

    This ensures the target file is never left in a partially-written state.
    """
    path = Path(path)

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Create backup of existing file
    if backup and path.exists():
        backup_path = path.with_suffix(path.suffix + '.bak')
        try:
            shutil.copy2(path, backup_path)
        except Exception as e:
            logger.warning(f"Failed to create backup for {path}: {e}")

    # Write to temp file in same directory (required for atomic rename)
    tmp_path = path.with_suffix('.tmp')

    try:
        # Write data to temp file
        tmp_path.write_text(json.dumps(data, indent=indent, default=str))

        # Atomic rename (POSIX guarantees atomicity, Windows is near-atomic)
        tmp_path.replace(path)

    except Exception as e:
        # Clean up temp file on error
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        raise Exception(f"Atomic write failed for {path}: {e}")


def atomic_write_text(path: Path, content: str, backup: bool = True):
    """
    Write text atomically to prevent corruption.

    Args:
        path: Target file path
        content: Text content to write
        backup: Create .bak backup before overwriting (default True)
    """
    path = Path(path)

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Create backup of existing file
    if backup and path.exists():
        backup_path = path.with_suffix(path.suffix + '.bak')
        try:
            shutil.copy2(path, backup_path)
        except Exception as e:
            logger.warning(f"Failed to create backup for {path}: {e}")

    # Write to temp file in same directory
    tmp_path = path.with_suffix('.tmp')

    try:
        # Write content to temp file
        tmp_path.write_text(content)

        # Atomic rename
        tmp_path.replace(path)

    except Exception as e:
        # Clean up temp file on error
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        raise Exception(f"Atomic write failed for {path}: {e}")
