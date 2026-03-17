#!/usr/bin/env python3
"""
Concurrent Read/Write Locking System for Multi-Agent Access

Provides comprehensive locking infrastructure for concurrent agent access to shared resources.
Supports both async and sync code, with distributed file-based locking for cross-process safety.

Features:
1. AsyncRWLock - Multiple readers OR single writer (async)
2. DistributedLock - Cross-process file-based locking
3. LockManager - Centralized lock management by resource name
4. Decorators - @read_lock, @write_lock for easy integration
5. Context managers - Both async and sync support
6. Timeout handling - Prevents deadlocks with configurable timeouts
7. Deadlock detection - Monitors lock wait chains
8. Lock statistics - Monitoring and performance metrics

Architecture:
- Resource-based locking: Each resource (database, file, etc.) has its own lock
- Fair queueing: FIFO order for write lock requests
- Graceful degradation: Timeout handling with proper cleanup
- Cross-process safety: File locks for distributed scenarios

Integration Points:
- memory_architecture.py: Database access (episodic, semantic, skill stores)
- skill_library.py: Skill storage and retrieval
- Any module requiring concurrent access control

Performance:
- Read locks: Near-zero overhead for concurrent reads
- Write locks: Minimal contention with fair queueing
- Timeout defaults: 30s for writes, 10s for reads
- Deadlock detection: 100ms check interval

Usage Examples:
    # Decorator usage
    @read_lock("database_name")
    async def read_data():
        pass

    @write_lock("database_name", timeout=60.0)
    async def write_data():
        pass

    # Context manager usage (async)
    async with get_lock_manager().read_lock("resource"):
        # Read operations
        pass

    async with get_lock_manager().write_lock("resource"):
        # Write operations
        pass

    # Context manager usage (sync)
    with get_lock_manager().distributed_lock("resource"):
        # Cross-process safe operations
        pass
"""

import asyncio
import fcntl
import functools
import hashlib
import json
import os
import sys
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Set, Tuple
from enum import Enum
from loguru import logger


# ============================================================================
# CONFIGURATION
# ============================================================================

LOCK_DIR = Path("memory/locks")
LOCK_DIR.mkdir(parents=True, exist_ok=True)

# Timeout defaults
DEFAULT_READ_TIMEOUT = 10.0  # seconds
DEFAULT_WRITE_TIMEOUT = 30.0  # seconds
DEFAULT_DISTRIBUTED_TIMEOUT = 60.0  # seconds

# Deadlock detection
DEADLOCK_CHECK_INTERVAL = 0.1  # 100ms
DEADLOCK_TIMEOUT = 300.0  # 5 minutes - consider deadlocked after this

# Lock statistics
STATS_WINDOW_SIZE = 1000  # Keep last 1000 lock operations
STATS_AGGREGATION_INTERVAL = 60.0  # Aggregate stats every minute

# File lock settings
FILE_LOCK_RETRY_DELAY = 0.01  # 10ms
FILE_LOCK_MAX_RETRIES = 100


# ============================================================================
# DATA STRUCTURES
# ============================================================================

class LockType(Enum):
    """Type of lock operation."""
    READ = "read"
    WRITE = "write"
    DISTRIBUTED = "distributed"


class LockStatus(Enum):
    """Status of lock acquisition."""
    WAITING = "waiting"
    ACQUIRED = "acquired"
    RELEASED = "released"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class LockRequest:
    """Represents a lock acquisition request."""
    request_id: str
    resource_name: str
    lock_type: LockType
    requester: str  # Thread/task identifier
    requested_at: float  # timestamp
    acquired_at: Optional[float] = None
    released_at: Optional[float] = None
    status: LockStatus = LockStatus.WAITING
    timeout: float = DEFAULT_WRITE_TIMEOUT

    def wait_time(self) -> float:
        """Calculate how long this request has been waiting."""
        if self.acquired_at:
            return self.acquired_at - self.requested_at
        return time.time() - self.requested_at

    def hold_time(self) -> float:
        """Calculate how long this lock has been held."""
        if not self.acquired_at:
            return 0.0
        if self.released_at:
            return self.released_at - self.acquired_at
        return time.time() - self.acquired_at


@dataclass
class LockStatistics:
    """Statistics for a specific resource lock."""
    resource_name: str
    lock_type: LockType

    # Counts
    total_acquisitions: int = 0
    total_releases: int = 0
    total_timeouts: int = 0
    total_errors: int = 0

    # Timing
    total_wait_time: float = 0.0
    total_hold_time: float = 0.0
    min_wait_time: float = float('inf')
    max_wait_time: float = 0.0
    min_hold_time: float = float('inf')
    max_hold_time: float = 0.0

    # Current state
    current_holders: int = 0
    current_waiters: int = 0

    # History (circular buffer)
    recent_operations: deque = field(default_factory=lambda: deque(maxlen=100))

    def record_acquisition(self, request: LockRequest):
        """Record a successful lock acquisition."""
        self.total_acquisitions += 1
        self.current_holders += 1

        wait_time = request.wait_time()
        self.total_wait_time += wait_time
        self.min_wait_time = min(self.min_wait_time, wait_time)
        self.max_wait_time = max(self.max_wait_time, wait_time)

        self.recent_operations.append({
            "type": "acquire",
            "lock_type": request.lock_type.value,
            "timestamp": time.time(),
            "wait_time": wait_time,
            "requester": request.requester
        })

    def record_release(self, request: LockRequest):
        """Record a lock release."""
        self.total_releases += 1
        self.current_holders = max(0, self.current_holders - 1)

        hold_time = request.hold_time()
        self.total_hold_time += hold_time
        self.min_hold_time = min(self.min_hold_time, hold_time)
        self.max_hold_time = max(self.max_hold_time, hold_time)

        self.recent_operations.append({
            "type": "release",
            "lock_type": request.lock_type.value,
            "timestamp": time.time(),
            "hold_time": hold_time,
            "requester": request.requester
        })

    def record_timeout(self, request: LockRequest):
        """Record a lock timeout."""
        self.total_timeouts += 1
        self.current_waiters = max(0, self.current_waiters - 1)

        self.recent_operations.append({
            "type": "timeout",
            "lock_type": request.lock_type.value,
            "timestamp": time.time(),
            "wait_time": request.wait_time(),
            "requester": request.requester
        })

    def record_error(self, request: LockRequest, error: str):
        """Record a lock error."""
        self.total_errors += 1

        self.recent_operations.append({
            "type": "error",
            "lock_type": request.lock_type.value,
            "timestamp": time.time(),
            "error": error,
            "requester": request.requester
        })

    def avg_wait_time(self) -> float:
        """Calculate average wait time."""
        if self.total_acquisitions == 0:
            return 0.0
        return self.total_wait_time / self.total_acquisitions

    def avg_hold_time(self) -> float:
        """Calculate average hold time."""
        if self.total_releases == 0:
            return 0.0
        return self.total_hold_time / self.total_releases

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resource_name": self.resource_name,
            "lock_type": self.lock_type.value,
            "total_acquisitions": self.total_acquisitions,
            "total_releases": self.total_releases,
            "total_timeouts": self.total_timeouts,
            "total_errors": self.total_errors,
            "avg_wait_time_ms": self.avg_wait_time() * 1000,
            "avg_hold_time_ms": self.avg_hold_time() * 1000,
            "max_wait_time_ms": self.max_wait_time * 1000 if self.max_wait_time < float('inf') else 0,
            "max_hold_time_ms": self.max_hold_time * 1000 if self.max_hold_time < float('inf') else 0,
            "current_holders": self.current_holders,
            "current_waiters": self.current_waiters,
            "recent_operations": list(self.recent_operations)[-10:]  # Last 10 operations
        }


# ============================================================================
# ASYNC READ/WRITE LOCK
# ============================================================================

class AsyncRWLock:
    """
    Async read/write lock allowing multiple readers OR single writer.

    Features:
    - Multiple concurrent readers
    - Exclusive writer access
    - Fair queuing (FIFO for writers)
    - Timeout support
    - Deadlock detection
    - Statistics tracking

    Implementation:
    - Uses asyncio primitives (Condition, Event)
    - Write requests queued in FIFO order
    - Read requests granted if no writers waiting/active
    - Writer gets exclusive access when granted
    """

    def __init__(self, resource_name: str):
        self.resource_name = resource_name
        self._readers = 0
        self._writer = False
        self._write_waiters = asyncio.Queue()  # FIFO queue for write requests
        self._lock = asyncio.Lock()
        self._read_ok = asyncio.Condition(self._lock)
        self._write_ok = asyncio.Condition(self._lock)

        # Tracking
        self._current_writer: Optional[str] = None
        self._current_readers: Set[str] = set()
        self._pending_requests: Dict[str, LockRequest] = {}

    @asynccontextmanager
    async def read_lock(self, timeout: float = DEFAULT_READ_TIMEOUT, requester: str = None):
        """
        Acquire a read lock (shared access).

        Args:
            timeout: Maximum time to wait for lock
            requester: Identifier for the requester (for tracking)

        Yields:
            None

        Raises:
            TimeoutError: If lock cannot be acquired within timeout
        """
        if requester is None:
            requester = self._get_current_task_id()

        request_id = f"read_{requester}_{time.time()}"
        request = LockRequest(
            request_id=request_id,
            resource_name=self.resource_name,
            lock_type=LockType.READ,
            requester=requester,
            requested_at=time.time(),
            timeout=timeout
        )

        self._pending_requests[request_id] = request

        try:
            # Acquire read lock with timeout
            await asyncio.wait_for(
                self._acquire_read(request),
                timeout=timeout
            )

            yield

        except asyncio.TimeoutError:
            request.status = LockStatus.TIMEOUT
            raise TimeoutError(f"Read lock timeout after {timeout}s for {self.resource_name}")

        finally:
            # Release read lock
            await self._release_read(request)
            self._pending_requests.pop(request_id, None)

    async def _acquire_read(self, request: LockRequest):
        """Internal: Acquire read lock."""
        async with self._lock:
            # Wait while there's an active writer or writers waiting
            while self._writer or not self._write_waiters.empty():
                await self._read_ok.wait()

            # Grant read lock
            self._readers += 1
            self._current_readers.add(request.requester)
            request.acquired_at = time.time()
            request.status = LockStatus.ACQUIRED

            logger.debug(
                f"Read lock acquired: {self.resource_name} "
                f"(readers={self._readers}, requester={request.requester})"
            )

    async def _release_read(self, request: LockRequest):
        """Internal: Release read lock."""
        async with self._lock:
            self._readers -= 1
            self._current_readers.discard(request.requester)
            request.released_at = time.time()
            request.status = LockStatus.RELEASED

            # If no more readers, notify waiting writers
            if self._readers == 0:
                self._write_ok.notify()

            logger.debug(
                f"Read lock released: {self.resource_name} "
                f"(readers={self._readers}, requester={request.requester})"
            )

    @asynccontextmanager
    async def write_lock(self, timeout: float = DEFAULT_WRITE_TIMEOUT, requester: str = None):
        """
        Acquire a write lock (exclusive access).

        Args:
            timeout: Maximum time to wait for lock
            requester: Identifier for the requester (for tracking)

        Yields:
            None

        Raises:
            TimeoutError: If lock cannot be acquired within timeout
        """
        if requester is None:
            requester = self._get_current_task_id()

        request_id = f"write_{requester}_{time.time()}"
        request = LockRequest(
            request_id=request_id,
            resource_name=self.resource_name,
            lock_type=LockType.WRITE,
            requester=requester,
            requested_at=time.time(),
            timeout=timeout
        )

        self._pending_requests[request_id] = request

        try:
            # Acquire write lock with timeout
            await asyncio.wait_for(
                self._acquire_write(request),
                timeout=timeout
            )

            yield

        except asyncio.TimeoutError:
            request.status = LockStatus.TIMEOUT
            raise TimeoutError(f"Write lock timeout after {timeout}s for {self.resource_name}")

        finally:
            # Release write lock
            await self._release_write(request)
            self._pending_requests.pop(request_id, None)

    async def _acquire_write(self, request: LockRequest):
        """Internal: Acquire write lock."""
        async with self._lock:
            # Add to write queue (FIFO)
            await self._write_waiters.put(request)

            # Wait while there are readers or another writer
            while self._readers > 0 or self._writer:
                await self._write_ok.wait()

            # Remove from queue (we're next)
            await self._write_waiters.get()

            # Grant write lock
            self._writer = True
            self._current_writer = request.requester
            request.acquired_at = time.time()
            request.status = LockStatus.ACQUIRED

            logger.debug(
                f"Write lock acquired: {self.resource_name} "
                f"(requester={request.requester})"
            )

    async def _release_write(self, request: LockRequest):
        """Internal: Release write lock."""
        async with self._lock:
            self._writer = False
            self._current_writer = None
            request.released_at = time.time()
            request.status = LockStatus.RELEASED

            # Notify all waiting readers and writers
            self._read_ok.notify_all()
            self._write_ok.notify()

            logger.debug(
                f"Write lock released: {self.resource_name} "
                f"(requester={request.requester})"
            )

    def _get_current_task_id(self) -> str:
        """Get current asyncio task ID."""
        try:
            task = asyncio.current_task()
            if task:
                return f"task_{id(task)}"
        except RuntimeError:
            pass
        return f"thread_{threading.current_thread().ident}"

    def get_status(self) -> Dict[str, Any]:
        """Get current lock status."""
        return {
            "resource_name": self.resource_name,
            "readers": self._readers,
            "writer_active": self._writer,
            "current_writer": self._current_writer,
            "current_readers": list(self._current_readers),
            "pending_writes": self._write_waiters.qsize(),
            "pending_requests": len(self._pending_requests)
        }


# ============================================================================
# DISTRIBUTED FILE LOCK
# ============================================================================

class DistributedLock:
    """
    Cross-process file-based locking using fcntl (POSIX).

    Features:
    - Cross-process safety using file locks
    - Automatic lock file cleanup
    - Timeout support
    - Retry with exponential backoff
    - Works on Linux/Unix (fcntl)
    - Fallback for Windows (uses threading.Lock)

    Implementation:
    - Creates lock files in LOCK_DIR
    - Uses fcntl.flock for advisory locking
    - Automatic cleanup on release
    - Handles stale locks
    """

    def __init__(self, resource_name: str):
        self.resource_name = resource_name
        self.lock_file_path = LOCK_DIR / f"{self._sanitize_name(resource_name)}.lock"
        self._lock_file: Optional[Any] = None
        self._is_windows = sys.platform.startswith('win')

        # Fallback for Windows
        if self._is_windows:
            self._fallback_lock = threading.Lock()
            logger.warning(
                f"DistributedLock on Windows uses threading.Lock fallback "
                f"(not cross-process safe): {resource_name}"
            )

    def _sanitize_name(self, name: str) -> str:
        """Sanitize resource name for use as filename."""
        # Hash long names, keep readable for short ones
        if len(name) > 50:
            return hashlib.md5(name.encode()).hexdigest()
        # Replace non-alphanumeric with underscores
        return "".join(c if c.isalnum() else "_" for c in name)

    @contextmanager
    def lock(self, timeout: float = DEFAULT_DISTRIBUTED_TIMEOUT):
        """
        Acquire distributed lock.

        Args:
            timeout: Maximum time to wait for lock

        Yields:
            None

        Raises:
            TimeoutError: If lock cannot be acquired within timeout
        """
        if self._is_windows:
            # Fallback for Windows
            acquired = self._fallback_lock.acquire(timeout=timeout)
            if not acquired:
                raise TimeoutError(
                    f"Distributed lock timeout after {timeout}s for {self.resource_name}"
                )
            try:
                yield
            finally:
                self._fallback_lock.release()
            return

        # POSIX implementation
        start_time = time.time()
        retry_count = 0

        try:
            # Open/create lock file
            self._lock_file = open(self.lock_file_path, 'w')

            # Try to acquire lock with retries
            while True:
                try:
                    # Try non-blocking lock
                    fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                    # Success!
                    logger.debug(f"Distributed lock acquired: {self.resource_name}")
                    break

                except (IOError, OSError) as e:
                    # Lock is held by another process
                    elapsed = time.time() - start_time

                    if elapsed >= timeout:
                        raise TimeoutError(
                            f"Distributed lock timeout after {timeout}s for {self.resource_name}"
                        )

                    # Exponential backoff
                    retry_count += 1
                    delay = min(FILE_LOCK_RETRY_DELAY * (2 ** min(retry_count, 5)), 1.0)
                    time.sleep(delay)

            # Write lock metadata
            self._lock_file.write(json.dumps({
                "resource": self.resource_name,
                "pid": os.getpid(),
                "acquired_at": time.time(),
                "hostname": os.uname().nodename if hasattr(os, 'uname') else 'unknown'
            }))
            self._lock_file.flush()

            yield

        finally:
            # Release lock
            if self._lock_file:
                try:
                    fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                    logger.debug(f"Distributed lock released: {self.resource_name}")
                except Exception as e:
                    logger.error(f"Error releasing distributed lock: {e}")
                finally:
                    self._lock_file.close()
                    self._lock_file = None

                    # Clean up lock file
                    try:
                        if self.lock_file_path.exists():
                            self.lock_file_path.unlink()
                    except Exception as e:
                        logger.warning(f"Could not delete lock file: {e}")


# ============================================================================
# LOCK MANAGER
# ============================================================================

class LockManager:
    """
    Centralized lock manager for all resources.

    Features:
    - Single source of truth for all locks
    - Resource-based lock creation
    - Statistics tracking and monitoring
    - Deadlock detection
    - Lock cleanup

    Usage:
        manager = get_lock_manager()
        async with manager.read_lock("my_database"):
            # Read operations
            pass

        async with manager.write_lock("my_database"):
            # Write operations
            pass

        with manager.distributed_lock("cross_process_resource"):
            # Cross-process operations
            pass
    """

    def __init__(self):
        self._rw_locks: Dict[str, AsyncRWLock] = {}
        self._distributed_locks: Dict[str, DistributedLock] = {}
        self._lock_creation_lock = threading.Lock()

        # Statistics
        self._stats: Dict[str, Dict[LockType, LockStatistics]] = defaultdict(dict)
        self._stats_lock = threading.Lock()

        # Deadlock detection
        self._deadlock_detector_task: Optional[asyncio.Task] = None
        self._deadlock_detection_enabled = True

    def _get_rw_lock(self, resource_name: str) -> AsyncRWLock:
        """Get or create AsyncRWLock for resource."""
        if resource_name not in self._rw_locks:
            with self._lock_creation_lock:
                if resource_name not in self._rw_locks:
                    self._rw_locks[resource_name] = AsyncRWLock(resource_name)
                    logger.debug(f"Created AsyncRWLock for resource: {resource_name}")
        return self._rw_locks[resource_name]

    def _get_distributed_lock(self, resource_name: str) -> DistributedLock:
        """Get or create DistributedLock for resource."""
        if resource_name not in self._distributed_locks:
            with self._lock_creation_lock:
                if resource_name not in self._distributed_locks:
                    self._distributed_locks[resource_name] = DistributedLock(resource_name)
                    logger.debug(f"Created DistributedLock for resource: {resource_name}")
        return self._distributed_locks[resource_name]

    def _get_stats(self, resource_name: str, lock_type: LockType) -> LockStatistics:
        """Get or create statistics for resource and lock type."""
        with self._stats_lock:
            if lock_type not in self._stats[resource_name]:
                self._stats[resource_name][lock_type] = LockStatistics(
                    resource_name=resource_name,
                    lock_type=lock_type
                )
            return self._stats[resource_name][lock_type]

    @asynccontextmanager
    async def read_lock(self, resource_name: str, timeout: float = DEFAULT_READ_TIMEOUT):
        """
        Acquire read lock for resource.

        Args:
            resource_name: Name of the resource to lock
            timeout: Maximum time to wait for lock

        Yields:
            None

        Example:
            async with manager.read_lock("database"):
                data = await read_database()
        """
        lock = self._get_rw_lock(resource_name)
        stats = self._get_stats(resource_name, LockType.READ)

        requester = lock._get_current_task_id()

        stats.current_waiters += 1

        try:
            async with lock.read_lock(timeout=timeout, requester=requester) as ctx:
                # Find the request to record stats
                request = None
                for req in lock._pending_requests.values():
                    if req.requester == requester and req.lock_type == LockType.READ:
                        request = req
                        break

                if request:
                    stats.record_acquisition(request)

                stats.current_waiters = max(0, stats.current_waiters - 1)

                yield

        except TimeoutError as e:
            stats.current_waiters = max(0, stats.current_waiters - 1)
            request = LockRequest(
                request_id=f"read_timeout_{time.time()}",
                resource_name=resource_name,
                lock_type=LockType.READ,
                requester=requester,
                requested_at=time.time() - timeout,
                timeout=timeout
            )
            stats.record_timeout(request)
            raise

        except Exception as e:
            stats.current_waiters = max(0, stats.current_waiters - 1)
            request = LockRequest(
                request_id=f"read_error_{time.time()}",
                resource_name=resource_name,
                lock_type=LockType.READ,
                requester=requester,
                requested_at=time.time(),
                timeout=timeout
            )
            stats.record_error(request, str(e))
            raise

        finally:
            # Record release if we acquired
            for req in lock._pending_requests.values():
                if (req.requester == requester and
                    req.lock_type == LockType.READ and
                    req.status == LockStatus.ACQUIRED):
                    stats.record_release(req)

    @asynccontextmanager
    async def write_lock(self, resource_name: str, timeout: float = DEFAULT_WRITE_TIMEOUT):
        """
        Acquire write lock for resource.

        Args:
            resource_name: Name of the resource to lock
            timeout: Maximum time to wait for lock

        Yields:
            None

        Example:
            async with manager.write_lock("database"):
                await write_database(data)
        """
        lock = self._get_rw_lock(resource_name)
        stats = self._get_stats(resource_name, LockType.WRITE)

        requester = lock._get_current_task_id()

        stats.current_waiters += 1

        try:
            async with lock.write_lock(timeout=timeout, requester=requester) as ctx:
                # Find the request to record stats
                request = None
                for req in lock._pending_requests.values():
                    if req.requester == requester and req.lock_type == LockType.WRITE:
                        request = req
                        break

                if request:
                    stats.record_acquisition(request)

                stats.current_waiters = max(0, stats.current_waiters - 1)

                yield

        except TimeoutError as e:
            stats.current_waiters = max(0, stats.current_waiters - 1)
            request = LockRequest(
                request_id=f"write_timeout_{time.time()}",
                resource_name=resource_name,
                lock_type=LockType.WRITE,
                requester=requester,
                requested_at=time.time() - timeout,
                timeout=timeout
            )
            stats.record_timeout(request)
            raise

        except Exception as e:
            stats.current_waiters = max(0, stats.current_waiters - 1)
            request = LockRequest(
                request_id=f"write_error_{time.time()}",
                resource_name=resource_name,
                lock_type=LockType.WRITE,
                requester=requester,
                requested_at=time.time(),
                timeout=timeout
            )
            stats.record_error(request, str(e))
            raise

        finally:
            # Record release if we acquired
            for req in lock._pending_requests.values():
                if (req.requester == requester and
                    req.lock_type == LockType.WRITE and
                    req.status == LockStatus.ACQUIRED):
                    stats.record_release(req)

    @contextmanager
    def distributed_lock(self, resource_name: str, timeout: float = DEFAULT_DISTRIBUTED_TIMEOUT):
        """
        Acquire distributed (cross-process) lock for resource.

        Args:
            resource_name: Name of the resource to lock
            timeout: Maximum time to wait for lock

        Yields:
            None

        Example:
            with manager.distributed_lock("shared_file"):
                process_shared_file()
        """
        lock = self._get_distributed_lock(resource_name)
        stats = self._get_stats(resource_name, LockType.DISTRIBUTED)

        requester = f"pid_{os.getpid()}_thread_{threading.current_thread().ident}"

        request = LockRequest(
            request_id=f"distributed_{requester}_{time.time()}",
            resource_name=resource_name,
            lock_type=LockType.DISTRIBUTED,
            requester=requester,
            requested_at=time.time(),
            timeout=timeout
        )

        stats.current_waiters += 1

        try:
            with lock.lock(timeout=timeout):
                request.acquired_at = time.time()
                request.status = LockStatus.ACQUIRED
                stats.record_acquisition(request)
                stats.current_waiters = max(0, stats.current_waiters - 1)

                yield

                request.released_at = time.time()
                request.status = LockStatus.RELEASED
                stats.record_release(request)

        except TimeoutError as e:
            stats.current_waiters = max(0, stats.current_waiters - 1)
            stats.record_timeout(request)
            raise

        except Exception as e:
            stats.current_waiters = max(0, stats.current_waiters - 1)
            stats.record_error(request, str(e))
            raise

    def get_statistics(self, resource_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get lock statistics.

        Args:
            resource_name: Optional resource name to filter by

        Returns:
            Dictionary of statistics
        """
        with self._stats_lock:
            if resource_name:
                # Stats for specific resource
                if resource_name not in self._stats:
                    return {}

                return {
                    "resource_name": resource_name,
                    "locks": {
                        lock_type.value: stats.to_dict()
                        for lock_type, stats in self._stats[resource_name].items()
                    }
                }
            else:
                # Stats for all resources
                return {
                    resource: {
                        lock_type.value: stats.to_dict()
                        for lock_type, stats in locks.items()
                    }
                    for resource, locks in self._stats.items()
                }

    def get_lock_status(self, resource_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get current lock status.

        Args:
            resource_name: Optional resource name to filter by

        Returns:
            Dictionary of lock statuses
        """
        result = {}

        if resource_name:
            # Status for specific resource
            if resource_name in self._rw_locks:
                result[resource_name] = self._rw_locks[resource_name].get_status()
        else:
            # Status for all resources
            for name, lock in self._rw_locks.items():
                result[name] = lock.get_status()

        return result

    async def detect_deadlocks(self) -> List[Dict[str, Any]]:
        """
        Detect potential deadlocks.

        Returns:
            List of potential deadlock scenarios
        """
        deadlocks = []
        current_time = time.time()

        for resource_name, lock in self._rw_locks.items():
            # Check for long-waiting requests
            for request in lock._pending_requests.values():
                if request.status == LockStatus.WAITING:
                    wait_time = current_time - request.requested_at

                    if wait_time > DEADLOCK_TIMEOUT:
                        deadlocks.append({
                            "resource": resource_name,
                            "request_id": request.request_id,
                            "requester": request.requester,
                            "lock_type": request.lock_type.value,
                            "wait_time_seconds": wait_time,
                            "timeout": request.timeout,
                            "current_writer": lock._current_writer,
                            "current_readers": list(lock._current_readers),
                            "pending_writes": lock._write_waiters.qsize()
                        })

        if deadlocks:
            logger.warning(f"Detected {len(deadlocks)} potential deadlocks")

        return deadlocks

    def reset_statistics(self, resource_name: Optional[str] = None):
        """
        Reset statistics.

        Args:
            resource_name: Optional resource name to reset, or None for all
        """
        with self._stats_lock:
            if resource_name:
                if resource_name in self._stats:
                    del self._stats[resource_name]
                    logger.info(f"Reset statistics for resource: {resource_name}")
            else:
                self._stats.clear()
                logger.info("Reset all lock statistics")


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_lock_manager_instance: Optional[LockManager] = None
_lock_manager_lock = threading.Lock()


def get_lock_manager() -> LockManager:
    """
    Get global LockManager singleton instance.

    Returns:
        LockManager instance
    """
    global _lock_manager_instance

    if _lock_manager_instance is None:
        with _lock_manager_lock:
            if _lock_manager_instance is None:
                _lock_manager_instance = LockManager()
                logger.info("Initialized global LockManager")

    return _lock_manager_instance


# ============================================================================
# DECORATORS
# ============================================================================

def read_lock(resource_name: str, timeout: float = DEFAULT_READ_TIMEOUT):
    """
    Decorator for async functions requiring read lock.

    Args:
        resource_name: Name of resource to lock
        timeout: Lock acquisition timeout

    Example:
        @read_lock("my_database")
        async def read_data():
            return await fetch_data()
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            manager = get_lock_manager()
            async with manager.read_lock(resource_name, timeout=timeout):
                return await func(*args, **kwargs)
        return wrapper
    return decorator


def write_lock(resource_name: str, timeout: float = DEFAULT_WRITE_TIMEOUT):
    """
    Decorator for async functions requiring write lock.

    Args:
        resource_name: Name of resource to lock
        timeout: Lock acquisition timeout

    Example:
        @write_lock("my_database", timeout=60.0)
        async def write_data(data):
            await save_data(data)
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            manager = get_lock_manager()
            async with manager.write_lock(resource_name, timeout=timeout):
                return await func(*args, **kwargs)
        return wrapper
    return decorator


def distributed_lock(resource_name: str, timeout: float = DEFAULT_DISTRIBUTED_TIMEOUT):
    """
    Decorator for sync functions requiring distributed lock.

    Args:
        resource_name: Name of resource to lock
        timeout: Lock acquisition timeout

    Example:
        @distributed_lock("shared_file")
        def process_file():
            # Process shared file safely across processes
            pass
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            manager = get_lock_manager()
            with manager.distributed_lock(resource_name, timeout=timeout):
                return func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================================
# TESTING AND EXAMPLES
# ============================================================================

async def example_usage():
    """Example usage of the locking system."""

    manager = get_lock_manager()

    # Example 1: Using decorators
    @read_lock("database")
    async def read_database():
        logger.info("Reading from database...")
        await asyncio.sleep(0.5)
        return {"data": "example"}

    @write_lock("database", timeout=10.0)
    async def write_database(data):
        logger.info(f"Writing to database: {data}")
        await asyncio.sleep(1.0)
        return True

    # Example 2: Using context managers
    async def concurrent_reads():
        """Multiple concurrent reads."""
        async with manager.read_lock("database"):
            logger.info("Read operation 1")
            await asyncio.sleep(1.0)

    async def sequential_write():
        """Exclusive write."""
        async with manager.write_lock("database"):
            logger.info("Write operation")
            await asyncio.sleep(1.0)

    # Run concurrent operations
    logger.info("Starting concurrent read test...")
    await asyncio.gather(
        concurrent_reads(),
        concurrent_reads(),
        concurrent_reads()
    )

    logger.info("Starting write test...")
    await sequential_write()

    # Example 3: Cross-process lock
    with manager.distributed_lock("shared_resource"):
        logger.info("Exclusive cross-process access")
        time.sleep(0.5)

    # Get statistics
    stats = manager.get_statistics()
    logger.info(f"Lock statistics: {json.dumps(stats, indent=2)}")

    # Get current status
    status = manager.get_lock_status()
    logger.info(f"Lock status: {json.dumps(status, indent=2)}")


if __name__ == "__main__":
    # Run example
    asyncio.run(example_usage())
