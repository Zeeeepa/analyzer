#!/usr/bin/env python3
"""
Tests for Concurrent Locking System

Comprehensive test suite for the concurrent_locks module.
Tests AsyncRWLock, DistributedLock, LockManager, decorators, and monitoring.
"""

import asyncio
import json
import multiprocessing
import os
import time
from pathlib import Path
from typing import List

import pytest
from loguru import logger

from concurrent_locks import (
    get_lock_manager,
    read_lock,
    write_lock,
    distributed_lock,
    AsyncRWLock,
    DistributedLock,
    LockManager,
    LockType,
    LockStatus,
    LOCK_DIR
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def lock_manager():
    """Get a fresh lock manager for testing."""
    manager = get_lock_manager()
    manager.reset_statistics()
    yield manager
    manager.reset_statistics()


@pytest.fixture
def test_resource_name():
    """Unique resource name for testing."""
    return f"test_resource_{int(time.time() * 1000)}"


# ============================================================================
# ASYNCRWLOCK TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_async_rwlock_multiple_readers(test_resource_name):
    """Test that multiple readers can access simultaneously."""
    lock = AsyncRWLock(test_resource_name)
    read_count = 0
    max_concurrent_readers = 0

    async def reader(reader_id: int):
        nonlocal read_count, max_concurrent_readers

        async with lock.read_lock(requester=f"reader_{reader_id}"):
            read_count += 1
            max_concurrent_readers = max(max_concurrent_readers, read_count)
            await asyncio.sleep(0.1)  # Simulate read operation
            read_count -= 1

    # Run 5 concurrent readers
    await asyncio.gather(*[reader(i) for i in range(5)])

    # Verify multiple readers were concurrent
    assert max_concurrent_readers >= 3, "Should have had at least 3 concurrent readers"


@pytest.mark.asyncio
async def test_async_rwlock_writer_exclusivity(test_resource_name):
    """Test that writers get exclusive access."""
    lock = AsyncRWLock(test_resource_name)
    concurrent_count = 0
    max_concurrent = 0

    async def writer(writer_id: int):
        nonlocal concurrent_count, max_concurrent

        async with lock.write_lock(requester=f"writer_{writer_id}"):
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.05)  # Simulate write operation
            concurrent_count -= 1

    # Run 3 writers - should be sequential
    await asyncio.gather(*[writer(i) for i in range(3)])

    # Verify only one writer at a time
    assert max_concurrent == 1, "Should have had only 1 concurrent writer"


@pytest.mark.asyncio
async def test_async_rwlock_writer_blocks_readers(test_resource_name):
    """Test that active writer blocks readers."""
    lock = AsyncRWLock(test_resource_name)
    writer_started = asyncio.Event()
    writer_finished = asyncio.Event()
    reader_got_lock = asyncio.Event()

    async def writer():
        async with lock.write_lock(requester="writer"):
            writer_started.set()
            await asyncio.sleep(0.2)  # Hold write lock
            writer_finished.set()

    async def reader():
        # Wait for writer to start
        await writer_started.wait()

        # Try to get read lock (should wait for writer)
        async with lock.read_lock(requester="reader"):
            reader_got_lock.set()

        # Verify writer finished before reader got lock
        assert writer_finished.is_set(), "Reader should wait for writer to finish"

    # Start writer first, then reader
    await asyncio.gather(writer(), reader())

    assert reader_got_lock.is_set(), "Reader should eventually get lock"


@pytest.mark.asyncio
async def test_async_rwlock_timeout(test_resource_name):
    """Test lock timeout handling."""
    lock = AsyncRWLock(test_resource_name)

    async def long_writer():
        async with lock.write_lock(requester="long_writer"):
            await asyncio.sleep(2.0)  # Hold lock for 2 seconds

    async def impatient_writer():
        await asyncio.sleep(0.1)  # Let long_writer acquire first

        with pytest.raises(TimeoutError):
            async with lock.write_lock(timeout=0.5, requester="impatient_writer"):
                pass

    await asyncio.gather(long_writer(), impatient_writer())


# ============================================================================
# DISTRIBUTEDLOCK TESTS
# ============================================================================

def test_distributed_lock_basic(test_resource_name):
    """Test basic distributed lock functionality."""
    lock = DistributedLock(test_resource_name)

    with lock.lock():
        # Lock acquired successfully
        assert True


def test_distributed_lock_cross_process():
    """Test distributed lock across processes."""
    resource_name = f"cross_process_test_{int(time.time() * 1000)}"

    def process_worker(worker_id: int, results: List):
        """Worker function that tries to acquire lock."""
        lock = DistributedLock(resource_name)

        with lock.lock(timeout=5.0):
            # Simulate critical section
            results.append(worker_id)
            time.sleep(0.1)

    # Use manager for shared list
    manager = multiprocessing.Manager()
    results = manager.list()

    # Create 3 processes
    processes = []
    for i in range(3):
        p = multiprocessing.Process(target=process_worker, args=(i, results))
        processes.append(p)
        p.start()

    # Wait for all processes
    for p in processes:
        p.join(timeout=10)

    # All processes should have completed
    assert len(results) == 3, "All processes should have acquired lock"


def test_distributed_lock_timeout():
    """Test distributed lock timeout."""
    resource_name = f"timeout_test_{int(time.time() * 1000)}"
    lock = DistributedLock(resource_name)

    # Acquire lock in one "process"
    with lock.lock():
        # Try to acquire in another (simulated by creating new lock instance)
        lock2 = DistributedLock(resource_name)

        with pytest.raises(TimeoutError):
            with lock2.lock(timeout=0.5):
                pass


# ============================================================================
# LOCKMANAGER TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_lock_manager_read_lock(lock_manager, test_resource_name):
    """Test LockManager read lock."""
    data = []

    async def reader(reader_id: int):
        async with lock_manager.read_lock(test_resource_name):
            data.append(f"read_{reader_id}")
            await asyncio.sleep(0.05)

    # Multiple concurrent readers
    await asyncio.gather(*[reader(i) for i in range(3)])

    assert len(data) == 3, "All readers should complete"


@pytest.mark.asyncio
async def test_lock_manager_write_lock(lock_manager, test_resource_name):
    """Test LockManager write lock."""
    data = []

    async def writer(writer_id: int):
        async with lock_manager.write_lock(test_resource_name):
            data.append(f"write_{writer_id}")
            await asyncio.sleep(0.05)

    # Sequential writers
    await asyncio.gather(*[writer(i) for i in range(3)])

    assert len(data) == 3, "All writers should complete"


def test_lock_manager_distributed_lock(lock_manager, test_resource_name):
    """Test LockManager distributed lock."""
    data = []

    with lock_manager.distributed_lock(test_resource_name):
        data.append("locked")

    assert len(data) == 1, "Lock should work"


@pytest.mark.asyncio
async def test_lock_manager_statistics(lock_manager, test_resource_name):
    """Test lock statistics tracking."""
    # Perform some lock operations
    async with lock_manager.read_lock(test_resource_name):
        await asyncio.sleep(0.01)

    async with lock_manager.write_lock(test_resource_name):
        await asyncio.sleep(0.01)

    # Get statistics
    stats = lock_manager.get_statistics(test_resource_name)

    assert test_resource_name in stats or "resource_name" in stats
    if "resource_name" in stats:
        assert stats["resource_name"] == test_resource_name
        assert "locks" in stats
        assert "read" in stats["locks"]
        assert "write" in stats["locks"]

        read_stats = stats["locks"]["read"]
        write_stats = stats["locks"]["write"]

        assert read_stats["total_acquisitions"] >= 1
        assert write_stats["total_acquisitions"] >= 1


@pytest.mark.asyncio
async def test_lock_manager_status(lock_manager, test_resource_name):
    """Test lock status reporting."""
    # Acquire a read lock and check status
    async with lock_manager.read_lock(test_resource_name):
        status = lock_manager.get_lock_status(test_resource_name)

        assert test_resource_name in status
        assert status[test_resource_name]["readers"] >= 1


# ============================================================================
# DECORATOR TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_read_lock_decorator():
    """Test @read_lock decorator."""
    resource = f"decorator_test_{int(time.time() * 1000)}"
    call_count = 0

    @read_lock(resource, timeout=5.0)
    async def read_operation():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)
        return "data"

    result = await read_operation()

    assert result == "data"
    assert call_count == 1


@pytest.mark.asyncio
async def test_write_lock_decorator():
    """Test @write_lock decorator."""
    resource = f"decorator_test_{int(time.time() * 1000)}"
    call_count = 0

    @write_lock(resource, timeout=5.0)
    async def write_operation(value):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)
        return value * 2

    result = await write_operation(21)

    assert result == 42
    assert call_count == 1


def test_distributed_lock_decorator():
    """Test @distributed_lock decorator."""
    resource = f"decorator_test_{int(time.time() * 1000)}"
    call_count = 0

    @distributed_lock(resource, timeout=5.0)
    def sync_operation(value):
        nonlocal call_count
        call_count += 1
        time.sleep(0.01)
        return value + 1

    result = sync_operation(41)

    assert result == 42
    assert call_count == 1


# ============================================================================
# CONCURRENT ACCESS TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_concurrent_reads_writes(lock_manager, test_resource_name):
    """Test concurrent reads and writes work correctly."""
    shared_data = {"value": 0}
    read_count = 0
    write_count = 0

    async def reader(reader_id: int):
        nonlocal read_count
        async with lock_manager.read_lock(test_resource_name):
            # Read data
            _ = shared_data["value"]
            read_count += 1
            await asyncio.sleep(0.01)

    async def writer(writer_id: int):
        nonlocal write_count
        async with lock_manager.write_lock(test_resource_name):
            # Write data
            shared_data["value"] += 1
            write_count += 1
            await asyncio.sleep(0.01)

    # Mix of readers and writers
    tasks = []
    for i in range(5):
        tasks.append(reader(i))
    for i in range(3):
        tasks.append(writer(i))
    for i in range(5, 10):
        tasks.append(reader(i))

    await asyncio.gather(*tasks)

    assert read_count == 10, "All readers should complete"
    assert write_count == 3, "All writers should complete"
    assert shared_data["value"] == 3, "Data should be updated correctly"


@pytest.mark.asyncio
async def test_deadlock_detection(lock_manager, test_resource_name):
    """Test deadlock detection."""
    # Create a long-running write lock
    async def long_writer():
        async with lock_manager.write_lock(test_resource_name, timeout=10.0):
            await asyncio.sleep(5.0)

    # Create a writer that will wait
    async def waiting_writer():
        await asyncio.sleep(0.1)  # Let long_writer acquire first
        async with lock_manager.write_lock(test_resource_name, timeout=10.0):
            await asyncio.sleep(0.1)

    # Start both
    task1 = asyncio.create_task(long_writer())
    task2 = asyncio.create_task(waiting_writer())

    # Wait a bit for lock contention
    await asyncio.sleep(0.5)

    # Check for potential deadlocks
    deadlocks = await lock_manager.detect_deadlocks()

    # Should not detect deadlock (both will eventually complete)
    # But might detect long wait time
    # This test mainly verifies the detection runs without error

    # Cancel tasks
    task1.cancel()
    task2.cancel()

    try:
        await task1
    except asyncio.CancelledError:
        pass

    try:
        await task2
    except asyncio.CancelledError:
        pass


# ============================================================================
# STRESS TESTS
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.slow
async def test_stress_many_readers(lock_manager):
    """Stress test with many concurrent readers."""
    resource = f"stress_test_{int(time.time() * 1000)}"
    num_readers = 50
    completed = 0

    async def reader(reader_id: int):
        nonlocal completed
        async with lock_manager.read_lock(resource):
            await asyncio.sleep(0.001)
            completed += 1

    await asyncio.gather(*[reader(i) for i in range(num_readers)])

    assert completed == num_readers


@pytest.mark.asyncio
@pytest.mark.slow
async def test_stress_mixed_operations(lock_manager):
    """Stress test with mixed reads and writes."""
    resource = f"stress_test_{int(time.time() * 1000)}"
    data = {"counter": 0}
    num_operations = 100

    async def operation(op_id: int):
        if op_id % 3 == 0:  # 1/3 writes
            async with lock_manager.write_lock(resource):
                data["counter"] += 1
                await asyncio.sleep(0.001)
        else:  # 2/3 reads
            async with lock_manager.read_lock(resource):
                _ = data["counter"]
                await asyncio.sleep(0.001)

    await asyncio.gather(*[operation(i) for i in range(num_operations)])

    expected_writes = num_operations // 3
    assert data["counter"] == expected_writes


# ============================================================================
# CLEANUP TESTS
# ============================================================================

def test_lock_file_cleanup():
    """Test that lock files are properly cleaned up."""
    resource = f"cleanup_test_{int(time.time() * 1000)}"
    lock = DistributedLock(resource)

    with lock.lock():
        # Lock file should exist
        assert lock.lock_file_path.exists()

    # Lock file should be cleaned up after release
    # Note: There might be a small race condition, give it a moment
    time.sleep(0.1)
    assert not lock.lock_file_path.exists(), "Lock file should be cleaned up"


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_error_in_locked_section(lock_manager, test_resource_name):
    """Test that locks are released even if error occurs."""

    async def faulty_operation():
        async with lock_manager.write_lock(test_resource_name):
            raise ValueError("Simulated error")

    # Should raise error
    with pytest.raises(ValueError):
        await faulty_operation()

    # Lock should be released - next operation should work
    async with lock_manager.write_lock(test_resource_name):
        pass  # Should acquire successfully


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
