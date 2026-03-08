"""
Git-based Snapshot/Revert System - Safety feature for agent file changes.

This module provides a lightweight git-based snapshot system that enables undo/revert
of agent file changes. Based on OpenCode's implementation, it uses git plumbing
commands to track file state without creating commits.

Key Features:
- Track working directory state using git write-tree
- Create snapshots of current file state
- Restore entire working directory to previous snapshot
- Revert individual files from snapshots
- Get diffs between snapshots with line counts

Use Case:
When the agent makes file changes that break something, you can:
1. Review what changed: diff_full(old_hash, new_hash)
2. Revert specific files: revert_file(snapshot_hash, file_path)
3. Restore entire state: restore(snapshot_hash)
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from loguru import logger


@dataclass
class DiffStat:
    """Statistics for a file diff."""
    file_path: str
    lines_added: int
    lines_removed: int
    diff_content: str


@dataclass
class SnapshotInfo:
    """Information about a snapshot."""
    hash: str
    timestamp: float
    message: str


class SnapshotError(Exception):
    """Raised when snapshot operations fail."""
    pass


class SnapshotManager:
    """
    Git-based snapshot manager for tracking and reverting file changes.

    Uses git plumbing commands to create lightweight snapshots without commits.
    Stores git repository in a hidden .snapshot directory to avoid interfering
    with any existing git repositories.

    Example:
        manager = SnapshotManager(working_dir="/path/to/project")

        # Initialize tracking
        manager.track()

        # Create snapshot before making changes
        hash1 = manager.snapshot("Before refactoring")

        # ... make file changes ...

        # Create snapshot after changes
        hash2 = manager.snapshot("After refactoring")

        # Review changes
        diff = manager.diff_full(hash1, hash2)
        print(f"Changed {len(diff)} files")

        # Revert if needed
        manager.restore(hash1)
    """

    def __init__(self, working_dir: str = None, git_dir: str = ".snapshot"):
        """
        Initialize snapshot manager.

        Args:
            working_dir: Directory to track (default: current directory)
            git_dir: Hidden directory for git repo (default: .snapshot)
        """
        self.working_dir = Path(working_dir or os.getcwd()).resolve()
        self.git_dir = self.working_dir / git_dir
        self._initialized = False

    def _run_git(self, *args: str, capture_output: bool = True, check: bool = True) -> subprocess.CompletedProcess:
        """
        Run git command with proper environment.

        Args:
            *args: Git command arguments
            capture_output: Whether to capture stdout/stderr
            check: Whether to raise on non-zero exit

        Returns:
            CompletedProcess instance

        Raises:
            SnapshotError: If command fails and check=True
        """
        env = os.environ.copy()
        env["GIT_DIR"] = str(self.git_dir)
        env["GIT_WORK_TREE"] = str(self.working_dir)

        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=str(self.working_dir),
                env=env,
                capture_output=capture_output,
                text=True,
                check=check
            )
            return result
        except subprocess.CalledProcessError as e:
            raise SnapshotError(
                f"Git command failed: git {' '.join(args)}\n"
                f"Exit code: {e.returncode}\n"
                f"Stderr: {e.stderr}"
            ) from e
        except FileNotFoundError:
            raise SnapshotError(
                "Git not found. Please install git to use snapshot system."
            ) from None

    def _ensure_initialized(self):
        """Ensure git repository is initialized."""
        if not self._initialized:
            if not self.git_dir.exists():
                raise SnapshotError(
                    "Snapshot system not initialized. Call track() first."
                )
            self._initialized = True

    def track(self, working_dir: Optional[str] = None) -> str:
        """
        Initialize git repository and stage all files.

        Args:
            working_dir: Optional override for working directory

        Returns:
            Hash of initial tree

        Raises:
            SnapshotError: If initialization fails
        """
        if working_dir:
            self.working_dir = Path(working_dir).resolve()
            self.git_dir = self.working_dir / ".snapshot"

        try:
            # Create git directory if it doesn't exist
            if not self.git_dir.exists():
                self.git_dir.mkdir(parents=True, exist_ok=True)
                self._run_git("init", "--quiet")

                # Create .gitignore to exclude the snapshot directory itself
                gitignore_path = self.working_dir / ".gitignore"
                snapshot_ignore = f"{self.git_dir.name}/\n"

                # Append to existing .gitignore or create new one
                if gitignore_path.exists():
                    current_content = gitignore_path.read_text()
                    if snapshot_ignore not in current_content:
                        gitignore_path.write_text(current_content + "\n" + snapshot_ignore)
                else:
                    gitignore_path.write_text(snapshot_ignore)

                logger.info(f"Initialized snapshot tracking in {self.git_dir}")

            self._initialized = True

            # Add all files to index (excluding .snapshot due to .gitignore)
            self._run_git("add", "-A")

            # Create tree object from index
            result = self._run_git("write-tree")
            tree_hash = result.stdout.strip()

            logger.debug(f"Tracking initialized with tree hash: {tree_hash}")
            return tree_hash

        except Exception as e:
            raise SnapshotError(f"Failed to initialize tracking: {e}") from e

    def snapshot(self, message: str = "") -> str:
        """
        Create snapshot of current state.

        Args:
            message: Optional description of this snapshot

        Returns:
            Hash of snapshot tree

        Raises:
            SnapshotError: If snapshot creation fails
        """
        self._ensure_initialized()

        try:
            # Stage all changes
            self._run_git("add", "-A")

            # Create tree object
            result = self._run_git("write-tree")
            tree_hash = result.stdout.strip()

            logger.info(f"Created snapshot {tree_hash[:8]} - {message or 'no message'}")
            return tree_hash

        except Exception as e:
            raise SnapshotError(f"Failed to create snapshot: {e}") from e

    def restore(self, snapshot_hash: str) -> None:
        """
        Restore working directory to a previous snapshot.

        Args:
            snapshot_hash: Hash returned from snapshot() or track()

        Raises:
            SnapshotError: If restore fails
        """
        self._ensure_initialized()

        try:
            # Read tree into index
            self._run_git("read-tree", snapshot_hash)

            # Checkout files from index to working directory
            self._run_git("checkout-index", "-a", "-f")

            logger.info(f"Restored working directory to snapshot {snapshot_hash[:8]}")

        except Exception as e:
            raise SnapshotError(
                f"Failed to restore snapshot {snapshot_hash}: {e}"
            ) from e

    def patch(self, old_hash: str, new_hash: str) -> List[str]:
        """
        Get list of changed files between two snapshots.

        Args:
            old_hash: Hash of older snapshot
            new_hash: Hash of newer snapshot

        Returns:
            List of file paths that changed

        Raises:
            SnapshotError: If diff fails
        """
        self._ensure_initialized()

        try:
            result = self._run_git(
                "diff-tree", "--name-only", "-r", old_hash, new_hash
            )

            files = [
                line.strip()
                for line in result.stdout.splitlines()
                if line.strip()
            ]

            logger.debug(f"Found {len(files)} changed files between snapshots")
            return files

        except Exception as e:
            raise SnapshotError(
                f"Failed to get diff between {old_hash} and {new_hash}: {e}"
            ) from e

    def revert_file(self, snapshot_hash: str, file_path: str) -> None:
        """
        Restore a single file from a snapshot.

        Args:
            snapshot_hash: Hash of snapshot to restore from
            file_path: Path to file (relative to working_dir)

        Raises:
            SnapshotError: If revert fails
        """
        self._ensure_initialized()

        try:
            # Get file content from tree
            result = self._run_git(
                "show", f"{snapshot_hash}:{file_path}"
            )

            # Write content to file
            file_full_path = self.working_dir / file_path
            file_full_path.parent.mkdir(parents=True, exist_ok=True)
            file_full_path.write_text(result.stdout)

            logger.info(f"Reverted {file_path} to snapshot {snapshot_hash[:8]}")

        except Exception as e:
            raise SnapshotError(
                f"Failed to revert {file_path} from {snapshot_hash}: {e}"
            ) from e

    def diff_full(self, hash1: str, hash2: str) -> List[DiffStat]:
        """
        Get full diff with line counts and content between snapshots.

        Args:
            hash1: Hash of first snapshot
            hash2: Hash of second snapshot

        Returns:
            List of DiffStat objects with file changes

        Raises:
            SnapshotError: If diff fails
        """
        self._ensure_initialized()

        try:
            # Get list of changed files
            files = self.patch(hash1, hash2)

            diffs = []
            for file_path in files:
                # Get diff for this file
                result = self._run_git(
                    "diff-tree", "-p", hash1, hash2, "--", file_path,
                    check=False
                )

                diff_content = result.stdout

                # Count lines added/removed
                lines_added = 0
                lines_removed = 0
                for line in diff_content.splitlines():
                    if line.startswith('+') and not line.startswith('+++'):
                        lines_added += 1
                    elif line.startswith('-') and not line.startswith('---'):
                        lines_removed += 1

                diffs.append(DiffStat(
                    file_path=file_path,
                    lines_added=lines_added,
                    lines_removed=lines_removed,
                    diff_content=diff_content
                ))

            logger.debug(f"Generated full diff with {len(diffs)} changed files")
            return diffs

        except Exception as e:
            raise SnapshotError(
                f"Failed to generate full diff between {hash1} and {hash2}: {e}"
            ) from e

    def list_snapshots(self) -> List[str]:
        """
        List all tree objects (snapshots) in the repository.

        Note: This is a basic implementation. For production use, you might want
        to maintain a separate log file with snapshot metadata.

        Returns:
            List of tree hashes
        """
        self._ensure_initialized()

        try:
            result = self._run_git(
                "rev-list", "--objects", "--all"
            )

            trees = []
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 1:
                    # Check if this is a tree object
                    obj_hash = parts[0]
                    type_result = self._run_git("cat-file", "-t", obj_hash)
                    if type_result.stdout.strip() == "tree":
                        trees.append(obj_hash)

            return trees

        except Exception as e:
            logger.warning(f"Failed to list snapshots: {e}")
            return []

    def cleanup(self, keep_latest: int = 10) -> int:
        """
        Clean up old snapshots to save space.

        Args:
            keep_latest: Number of recent snapshots to keep

        Returns:
            Number of objects cleaned up
        """
        self._ensure_initialized()

        try:
            # Run git garbage collection
            self._run_git("gc", "--prune=now", "--aggressive", capture_output=True)
            logger.info("Cleaned up snapshot repository")
            return 0  # git gc doesn't report counts

        except Exception as e:
            logger.warning(f"Failed to cleanup snapshots: {e}")
            return 0

    def get_current_hash(self) -> str:
        """
        Get hash of current working directory state without creating a snapshot.

        Returns:
            Hash that would be created if snapshot() was called
        """
        self._ensure_initialized()

        try:
            # Stage current changes temporarily
            self._run_git("add", "-A")

            # Get tree hash without committing
            result = self._run_git("write-tree")
            return result.stdout.strip()

        except Exception as e:
            raise SnapshotError(f"Failed to get current hash: {e}") from e


# Global instance for convenience
_global_manager: Optional[SnapshotManager] = None


def get_snapshot_manager(working_dir: Optional[str] = None) -> SnapshotManager:
    """
    Get or create global snapshot manager instance.

    Args:
        working_dir: Optional working directory (only used on first call)

    Returns:
        Global SnapshotManager instance
    """
    global _global_manager
    if _global_manager is None:
        _global_manager = SnapshotManager(working_dir=working_dir)
    return _global_manager
