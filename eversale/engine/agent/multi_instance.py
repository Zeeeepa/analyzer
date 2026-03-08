"""
Multi-Instance Coordination - Multiple Eversale agents working together.

Features:
- File-based locking for shared resources
- Work distribution (split tasks by range/hash)
- Shared result aggregation
- Instance health monitoring
- Leader election for coordination tasks

Usage:
    coord = MultiInstanceCoordinator(instance_id="agent-1")
    coord.register()

    # Claim work
    with coord.claim_work("lead-123"):
        # Only this instance works on lead-123
        process_lead("lead-123")

    # Check if work is mine
    if coord.should_handle("customer-456", split_by="hash"):
        process_customer("customer-456")
"""

import hashlib
import json
import os
import socket
import sys
import time
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Set
from loguru import logger

# Platform-specific file locking
_IS_WINDOWS = sys.platform == 'win32'

if _IS_WINDOWS:
    # Windows: use msvcrt for file locking (simplified, non-blocking)
    import msvcrt

    def _flock_exclusive(fd):
        """Acquire exclusive lock (non-blocking) on Windows."""
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except (IOError, OSError):
            return False

    def _flock_shared(fd):
        """Shared lock - on Windows just return True (no shared locks)."""
        return True

    def _flock_unlock(fd):
        """Release lock on Windows."""
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except:
            pass
else:
    # Unix: use fcntl for file locking
    import fcntl

    def _flock_exclusive(fd):
        """Acquire exclusive lock (non-blocking) on Unix."""
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (BlockingIOError, OSError):
            return False

    def _flock_shared(fd):
        """Acquire shared lock (non-blocking) on Unix."""
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            return True
        except (BlockingIOError, OSError):
            return False

    def _flock_unlock(fd):
        """Release lock on Unix."""
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except:
            pass

from .atomic_file import atomic_write_json


class MultiInstanceCoordinator:
    def __init__(
        self,
        instance_id: Optional[str] = None,
        coordination_dir: Path = Path("coordination"),
        heartbeat_interval: float = 30.0,
        instance_timeout: float = 120.0,
    ):
        self.instance_id = instance_id or self._generate_instance_id()
        self.coordination_dir = coordination_dir
        self.heartbeat_interval = heartbeat_interval
        self.instance_timeout = instance_timeout

        # Paths
        self.instances_dir = coordination_dir / "instances"
        self.locks_dir = coordination_dir / "locks"
        self.work_dir = coordination_dir / "work"
        self.results_dir = coordination_dir / "results"

        # State
        self._running = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._claimed_work: Set[str] = set()
        self._lock_fds: Dict[str, int] = {}  # Track open file descriptors for held locks

        # Ensure directories exist
        for d in [self.instances_dir, self.locks_dir, self.work_dir, self.results_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def _generate_instance_id(self) -> str:
        """Generate unique instance ID."""
        hostname = socket.gethostname()
        pid = os.getpid()
        timestamp = int(time.time() * 1000) % 100000
        return f"{hostname}-{pid}-{timestamp}"

    def register(self):
        """Register this instance and start heartbeat."""
        self._write_heartbeat()
        self._running = True
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()
        logger.info(f"Multi-instance coordinator registered: {self.instance_id}")

    def unregister(self):
        """Unregister this instance."""
        self._running = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=2)

        # Remove instance file
        instance_file = self.instances_dir / f"{self.instance_id}.json"
        if instance_file.exists():
            instance_file.unlink()

        # Release all claimed work
        for work_id in list(self._claimed_work):
            self.release_work(work_id)

        # Close any remaining lock file descriptors
        for work_id, fd in list(self._lock_fds.items()):
            try:
                _flock_unlock(fd)
                os.close(fd)
            except Exception:
                pass
        self._lock_fds.clear()

        logger.info(f"Multi-instance coordinator unregistered: {self.instance_id}")

    def _write_heartbeat(self):
        """Write heartbeat file."""
        instance_file = self.instances_dir / f"{self.instance_id}.json"
        data = {
            "instance_id": self.instance_id,
            "hostname": socket.gethostname(),
            "pid": os.getpid(),
            "heartbeat": datetime.now().isoformat(),
            "claimed_work": list(self._claimed_work),
        }
        atomic_write_json(instance_file, data, indent=2, backup=False)

    def _heartbeat_loop(self):
        """Background heartbeat loop."""
        while self._running:
            self._write_heartbeat()
            self._cleanup_stale_instances()
            time.sleep(self.heartbeat_interval)

    def _cleanup_stale_instances(self):
        """Remove stale instance registrations."""
        cutoff = datetime.now() - timedelta(seconds=self.instance_timeout)

        for instance_file in self.instances_dir.glob("*.json"):
            try:
                data = json.loads(instance_file.read_text())
                heartbeat = datetime.fromisoformat(data["heartbeat"])
                if heartbeat < cutoff:
                    logger.warning(f"Removing stale instance: {data['instance_id']}")
                    instance_file.unlink()

                    # Release their claimed work
                    for work_id in data.get("claimed_work", []):
                        lock_file = self.locks_dir / f"{work_id}.lock"
                        if lock_file.exists():
                            lock_file.unlink()
            except Exception as e:
                logger.debug(f"Error cleaning instance file: {e}")

    def get_active_instances(self) -> List[Dict[str, Any]]:
        """Get list of active instances."""
        instances = []
        cutoff = datetime.now() - timedelta(seconds=self.instance_timeout)

        for instance_file in self.instances_dir.glob("*.json"):
            try:
                data = json.loads(instance_file.read_text())
                heartbeat = datetime.fromisoformat(data["heartbeat"])
                if heartbeat >= cutoff:
                    data["is_self"] = data["instance_id"] == self.instance_id
                    instances.append(data)
            except Exception:
                pass

        return sorted(instances, key=lambda x: x["instance_id"])

    def get_instance_index(self) -> tuple[int, int]:
        """Get this instance's index and total count for work distribution."""
        instances = self.get_active_instances()
        instance_ids = [i["instance_id"] for i in instances]

        if self.instance_id in instance_ids:
            return instance_ids.index(self.instance_id), len(instance_ids)
        return 0, 1

    def should_handle(self, work_id: str, split_by: str = "hash") -> bool:
        """
        Check if this instance should handle the given work item.

        split_by options:
        - "hash": Distribute by hash of work_id (even distribution)
        - "range": Distribute by alphabetical range (A-M, N-Z style)
        """
        my_index, total_instances = self.get_instance_index()

        if total_instances <= 1:
            return True

        if split_by == "hash":
            # Hash-based distribution
            work_hash = int(hashlib.md5(work_id.encode()).hexdigest(), 16)
            return work_hash % total_instances == my_index

        elif split_by == "range":
            # Range-based distribution (alphabetical)
            first_char = work_id[0].lower() if work_id else 'a'
            char_index = ord(first_char) - ord('a')
            chars_per_instance = 26 / total_instances
            return int(char_index / chars_per_instance) == my_index

        return True

    @contextmanager
    def claim_work(self, work_id: str, timeout: float = 0):
        """
        Claim exclusive access to a work item.

        Args:
            work_id: Unique identifier for the work
            timeout: How long to wait for lock (0 = don't wait)

        Raises:
            WorkClaimedError if work is already claimed by another instance
        """
        lock_file = self.locks_dir / f"{work_id}.lock"

        try:
            # Try to acquire lock
            if not self._acquire_lock(lock_file, work_id, timeout):
                raise WorkClaimedError(f"Work {work_id} is claimed by another instance")

            self._claimed_work.add(work_id)
            yield

        finally:
            self._claimed_work.discard(work_id)
            self._release_lock(lock_file, work_id)

    def _acquire_lock(self, lock_file: Path, work_id: str, timeout: float) -> bool:
        """
        Acquire OS-level exclusive lock using fcntl.

        Uses O_CREAT | O_EXCL to atomically create lock file, then applies fcntl.flock().
        The file descriptor is kept open to maintain the lock.
        """
        start_time = time.time()
        max_timeout = timeout if timeout > 0 else 2.0

        while True:
            try:
                # Attempt atomic lock file creation with exclusive access
                # This fails immediately if file already exists
                fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)

                try:
                    # Apply OS-level exclusive lock (non-blocking)
                    if not _flock_exclusive(fd):
                        raise BlockingIOError("Could not acquire lock")

                    # Write lock metadata
                    lock_data = {
                        "work_id": work_id,
                        "instance_id": self.instance_id,
                        "locked_at": datetime.now().isoformat(),
                        "hostname": socket.gethostname(),
                        "pid": os.getpid()
                    }
                    os.write(fd, json.dumps(lock_data, indent=2).encode())

                    # Store file descriptor to keep lock held
                    self._lock_fds[work_id] = fd

                    logger.debug(f"Lock acquired for {work_id} by {self.instance_id}")
                    return True

                except (BlockingIOError, OSError) as e:
                    # Failed to acquire flock, close and cleanup
                    os.close(fd)
                    try:
                        lock_file.unlink()
                    except Exception:
                        pass
                    raise e

            except FileExistsError:
                # Lock file already exists, check if stale
                if self._try_steal_stale_lock(lock_file, work_id, max_timeout):
                    return True

                # Check timeout
                if (time.time() - start_time) >= max_timeout:
                    logger.debug(f"Lock timeout for {work_id}")
                    return False

                # Wait a bit and retry
                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Failed to acquire lock for {work_id}: {e}")
                return False

    def _try_steal_stale_lock(self, lock_file: Path, work_id: str, timeout: float) -> bool:
        """
        Attempt to steal a stale lock if the holding instance is dead.

        Returns:
            True if lock was stolen and acquired, False otherwise
        """
        try:
            if not lock_file.exists():
                return False

            # Try to read lock data
            with open(lock_file, 'r') as f:
                try:
                    # Try non-blocking shared lock to read
                    _flock_shared(f.fileno())
                    data = json.loads(f.read())
                    _flock_unlock(f.fileno())

                    # Check if lock is stale (older than instance_timeout)
                    locked_at = datetime.fromisoformat(data["locked_at"])
                    age = (datetime.now() - locked_at).total_seconds()

                    if age > self.instance_timeout:
                        logger.warning(f"Detected stale lock for {work_id} (age: {age}s), attempting to steal")

                        # Try to remove stale lock file and retry acquisition
                        try:
                            lock_file.unlink()
                            return False  # Let the main loop retry acquisition
                        except Exception as e:
                            logger.debug(f"Failed to remove stale lock: {e}")
                            return False

                except BlockingIOError:
                    # Lock is actively held, not stale
                    return False

        except Exception as e:
            logger.debug(f"Error checking for stale lock: {e}")

        return False

    def _release_lock(self, lock_file: Path, work_id: str = None):
        """
        Release OS-level lock and close file descriptor.

        Args:
            lock_file: Path to lock file
            work_id: Work ID for tracking (optional)
        """
        # Release and close file descriptor if we're tracking it
        if work_id and work_id in self._lock_fds:
            try:
                fd = self._lock_fds[work_id]
                _flock_unlock(fd)
                os.close(fd)
                logger.debug(f"Lock released for {work_id}")
            except Exception as e:
                logger.debug(f"Error releasing lock fd: {e}")
            finally:
                del self._lock_fds[work_id]

        # Remove lock file (only if we own it)
        try:
            if lock_file.exists():
                # Verify ownership before deletion
                try:
                    with open(lock_file, 'r') as f:
                        data = json.loads(f.read())
                        if data.get("instance_id") == self.instance_id:
                            lock_file.unlink()
                except (FileNotFoundError, json.JSONDecodeError):
                    # File already deleted or corrupted
                    pass
        except Exception as e:
            logger.debug(f"Error removing lock file: {e}")

    def release_work(self, work_id: str):
        """Explicitly release claimed work."""
        self._claimed_work.discard(work_id)
        lock_file = self.locks_dir / f"{work_id}.lock"
        self._release_lock(lock_file, work_id)

    def save_result(self, work_id: str, result: Any):
        """Save result to shared results directory."""
        result_file = self.results_dir / f"{work_id}.json"
        data = {
            "work_id": work_id,
            "instance_id": self.instance_id,
            "completed_at": datetime.now().isoformat(),
            "result": result,
        }
        atomic_write_json(result_file, data, indent=2, backup=True)

    def get_result(self, work_id: str) -> Optional[Any]:
        """Get result from shared results directory."""
        result_file = self.results_dir / f"{work_id}.json"
        if result_file.exists():
            try:
                data = json.loads(result_file.read_text())
                return data.get("result")
            except Exception:
                pass
        return None

    def get_all_results(self) -> List[Dict[str, Any]]:
        """Get all results from all instances."""
        results = []
        for result_file in self.results_dir.glob("*.json"):
            try:
                data = json.loads(result_file.read_text())
                results.append(data)
            except Exception:
                pass
        return results

    def is_leader(self) -> bool:
        """Check if this instance is the leader (lowest instance_id)."""
        instances = self.get_active_instances()
        if not instances:
            return True
        return instances[0]["instance_id"] == self.instance_id

    def status(self) -> dict:
        """Get coordination status."""
        instances = self.get_active_instances()
        my_index, total = self.get_instance_index()

        return {
            "instance_id": self.instance_id,
            "is_leader": self.is_leader(),
            "instance_index": my_index,
            "total_instances": total,
            "claimed_work": list(self._claimed_work),
            "active_instances": [i["instance_id"] for i in instances],
        }


class WorkClaimedError(Exception):
    """Raised when trying to claim work that's already claimed."""
    pass


# Default config
DEFAULT_CONFIG = """# Multi-Instance Coordination Configuration

# Heartbeat interval (seconds)
heartbeat_interval: 30.0

# Instance timeout - consider dead after this long without heartbeat (seconds)
instance_timeout: 120.0

# Work distribution strategy: "hash" or "range"
distribution_strategy: hash
"""


def create_default_config():
    """Create default config file."""
    config_path = Path("config/multi_instance.yaml")
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(DEFAULT_CONFIG)
        logger.info(f"Created multi-instance config: {config_path}")
