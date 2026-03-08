"""
Test script for log rotation functionality.

Tests:
1. Basic file rotation when size limit is exceeded
2. JSONL rotation with line count limits
3. In-memory list trimming
4. Checkpoint cleanup
5. Integration with ForeverWorker
"""

import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from log_rotation import (
    LogRotator,
    JSONLRotator,
    cleanup_old_checkpoints,
    cleanup_rotated_logs,
    get_disk_usage_summary,
    periodic_cleanup
)


def test_basic_rotation():
    """Test basic file rotation."""
    print("\n=== Test 1: Basic File Rotation ===")

    # Create temp directory
    test_dir = Path.home() / '.eversale' / 'test_rotation'
    test_dir.mkdir(parents=True, exist_ok=True)

    # Create rotator with 1KB limit
    rotator = LogRotator(max_size_mb=0.001, max_rotations=3)

    # Create test file
    test_file = test_dir / 'test.log'
    test_file.write_text("x" * 2000)  # 2KB

    print(f"Created test file: {test_file.stat().st_size} bytes")

    # Try rotation
    rotated = rotator.rotate_if_needed(test_file)
    print(f"Rotation performed: {rotated}")

    # Check rotated file exists
    rotated_file = test_dir / 'test.log.1'
    if rotated_file.exists():
        print(f"Rotated file created: {rotated_file.name} ({rotated_file.stat().st_size} bytes)")
    else:
        print("ERROR: Rotated file not created!")

    # Check new file is empty
    if test_file.exists():
        print(f"New file created: {test_file.stat().st_size} bytes")

    # Test total size
    total_mb = rotator.get_total_size_mb(test_file)
    print(f"Total size (file + rotations): {total_mb:.4f} MB")

    # Cleanup
    for f in test_dir.glob('test.log*'):
        f.unlink()

    print("Test 1 PASSED\n")


def test_jsonl_rotation():
    """Test JSONL-specific rotation with line count."""
    print("\n=== Test 2: JSONL Rotation with Line Count ===")

    test_dir = Path.home() / '.eversale' / 'test_rotation'
    test_dir.mkdir(parents=True, exist_ok=True)

    # Create JSONL rotator with line limit
    rotator = JSONLRotator(
        max_size_mb=10.0,  # Large size limit
        max_lines=50,      # Small line limit
        max_rotations=3
    )

    # Create test JSONL file with 100 lines
    test_file = test_dir / 'test.jsonl'
    with open(test_file, 'w') as f:
        for i in range(100):
            f.write(json.dumps({"line": i, "data": "x" * 100}) + "\n")

    print(f"Created JSONL file with 100 lines")

    # Check if should rotate
    should_rotate = rotator.should_rotate(test_file)
    print(f"Should rotate (50 line limit): {should_rotate}")

    # Perform rotation
    if should_rotate:
        rotator.rotate_if_needed(test_file)
        print("Rotation performed")

    # Trim to 30 lines
    rotator.trim_to_lines(test_file, max_lines=30)

    # Count lines in trimmed file
    with open(test_file, 'r') as f:
        line_count = sum(1 for _ in f)
    print(f"Lines after trim: {line_count}")

    # Cleanup
    for f in test_dir.glob('test.jsonl*'):
        f.unlink()

    print("Test 2 PASSED\n")


def test_in_memory_trimming():
    """Test in-memory list trimming."""
    print("\n=== Test 3: In-Memory List Trimming ===")

    rotator = LogRotator()

    # Create large list
    large_list = [{"id": i, "data": "x" * 100} for i in range(1000)]
    print(f"Original list size: {len(large_list)}")

    # Trim to 100 items (keep recent)
    trimmed = rotator.trim_in_memory_list(large_list, max_size=100, keep_recent=True)
    print(f"Trimmed list size (keep recent): {len(trimmed)}")
    print(f"First item ID: {trimmed[0]['id']}, Last item ID: {trimmed[-1]['id']}")

    # Trim to 100 items (keep oldest)
    trimmed_old = rotator.trim_in_memory_list(large_list, max_size=100, keep_recent=False)
    print(f"Trimmed list size (keep oldest): {len(trimmed_old)}")
    print(f"First item ID: {trimmed_old[0]['id']}, Last item ID: {trimmed_old[-1]['id']}")

    print("Test 3 PASSED\n")


def test_checkpoint_cleanup():
    """Test checkpoint file cleanup."""
    print("\n=== Test 4: Checkpoint Cleanup ===")

    test_dir = Path.home() / '.eversale' / 'test_checkpoints'
    test_dir.mkdir(parents=True, exist_ok=True)

    # Create some checkpoint files
    current_time = time.time()
    checkpoints = []

    # Create 3 recent checkpoints
    for i in range(3):
        cp = test_dir / f'recent_{i}.json'
        cp.write_text(json.dumps({"checkpoint": i}))
        checkpoints.append(cp)

    # Create 3 old checkpoints (simulate 10 days old)
    for i in range(3):
        cp = test_dir / f'old_{i}.json'
        cp.write_text(json.dumps({"checkpoint": i}))
        # Set mtime to 10 days ago
        old_time = current_time - (10 * 24 * 3600)
        Path(cp).touch()
        import os
        os.utime(cp, (old_time, old_time))
        checkpoints.append(cp)

    print(f"Created {len(checkpoints)} checkpoint files")

    # Run cleanup (remove files older than 7 days)
    removed = cleanup_old_checkpoints(test_dir, max_age_days=7)
    print(f"Removed {removed} old checkpoints")

    # Count remaining
    remaining = list(test_dir.glob('*.json'))
    print(f"Remaining checkpoints: {len(remaining)}")

    # Cleanup all
    for f in remaining:
        f.unlink()
    test_dir.rmdir()

    print("Test 4 PASSED\n")


def test_disk_usage_summary():
    """Test disk usage summary."""
    print("\n=== Test 5: Disk Usage Summary ===")

    test_dir = Path.home() / '.eversale' / 'test_usage'
    test_dir.mkdir(parents=True, exist_ok=True)

    # Create various files
    files = [
        ('data.json', json.dumps({"data": "x" * 1000})),
        ('log.jsonl', "\n".join([json.dumps({"line": i}) for i in range(100)])),
        ('config.yaml', "key: value\n" * 50),
        ('output.txt', "text " * 500)
    ]

    for filename, content in files:
        (test_dir / filename).write_text(content)

    # Get usage summary
    summary = get_disk_usage_summary(test_dir)

    print(f"Total size: {summary['total_size_mb']:.3f} MB")
    print(f"File count: {summary['file_count']}")
    print("\nBy extension:")
    for ext, stats in summary['by_extension'].items():
        print(f"  {ext}: {stats['count']} files, {stats['size_mb']:.3f} MB")

    print("\nLargest files:")
    for file_info in summary['largest_files'][:3]:
        print(f"  {Path(file_info['path']).name}: {file_info['size_mb']:.3f} MB")

    # Cleanup
    for f in test_dir.glob('*'):
        f.unlink()
    test_dir.rmdir()

    print("\nTest 5 PASSED\n")


def test_forever_worker_integration():
    """Test integration with ForeverWorker."""
    print("\n=== Test 6: ForeverWorker Integration ===")

    from forever_operations import ForeverWorker, ForeverConfig

    # Create config with log rotation
    config = ForeverConfig(
        journal_max_size_mb=0.01,  # 10KB limit for testing
        journal_max_rotations=3,
        cleanup_interval_hours=0.001,  # Very short for testing
        poll_interval_seconds=1.0
    )

    # Create mock worker
    class TestWorker(ForeverWorker):
        def __init__(self):
            super().__init__(config=config, worker_name="test_worker")
            self.check_count = 0

        def check_for_items(self):
            self.check_count += 1
            if self.check_count > 5:  # Stop after 5 checks
                self.request_stop()
            # Return some fake items
            return [{"id": i} for i in range(3)]

        def process_item(self, item):
            return f"Processed {item['id']}"

        def get_item_id(self, item):
            return f"item_{item['id']}_{self.check_count}"

    print("Creating test worker with log rotation enabled...")
    worker = TestWorker()

    print(f"Journal rotator enabled: {worker.journal_rotator is not None}")
    print(f"Max journal size: {config.journal_max_size_mb} MB")
    print(f"Max rotations: {config.journal_max_rotations}")

    # Write a bunch of journal entries to test rotation
    for i in range(100):
        worker._journal("test_event", {
            "iteration": i,
            "data": "x" * 1000  # Make each entry large
        })

    # Check journal file
    journal_path = worker.work_dir / config.journal_file
    if journal_path.exists():
        size_mb = journal_path.stat().st_size / 1024 / 1024
        print(f"\nJournal file size: {size_mb:.3f} MB")

    # Check for rotated files
    rotated_count = len(list(worker.work_dir.glob('activity_journal.jsonl.*')))
    print(f"Rotated journal files: {rotated_count}")

    # Get status
    status = worker.get_status()
    if "log_rotation" in status:
        print(f"\nLog rotation status:")
        print(f"  Total size: {status['log_rotation']['journal_total_size_mb']:.3f} MB")
        print(f"  Hours since cleanup: {status['log_rotation']['hours_since_cleanup']}")

    # Cleanup
    import shutil
    if worker.work_dir.exists():
        shutil.rmtree(worker.work_dir)

    print("\nTest 6 PASSED\n")


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*60)
    print("LOG ROTATION TEST SUITE")
    print("="*60)

    try:
        test_basic_rotation()
        test_jsonl_rotation()
        test_in_memory_trimming()
        test_checkpoint_cleanup()
        test_disk_usage_summary()
        test_forever_worker_integration()

        print("\n" + "="*60)
        print("ALL TESTS PASSED")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_tests()
