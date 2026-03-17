"""
Example: Forever worker with log rotation enabled.

This example demonstrates:
1. Setting up a forever worker with custom rotation config
2. Monitoring rotation status
3. Handling log growth in long-running tasks
"""

from pathlib import Path
from forever_operations import ForeverWorker, ForeverConfig
from log_rotation import get_disk_usage_summary


class ExampleWorker(ForeverWorker):
    """
    Example worker that monitors a data source and processes items.

    This worker demonstrates best practices for log rotation in
    long-running tasks.
    """

    def __init__(self):
        # Custom config optimized for high-volume tasks
        config = ForeverConfig(
            # Polling
            poll_interval_seconds=30.0,
            adaptive_polling=True,

            # Log rotation - aggressive settings for demo
            log_rotation_enabled=True,
            journal_max_size_mb=1.0,       # Rotate at 1MB for demo
            journal_max_rotations=3,       # Keep 3 rotations
            cleanup_interval_hours=0.1,    # Cleanup every 6 minutes for demo

            # Cleanup
            checkpoint_max_age_days=7,
            rotated_logs_max_age_days=30,

            # Memory management
            max_processed_history=1000,
            max_dreams=50,

            # Heartbeat
            heartbeat_interval_seconds=60.0
        )

        super().__init__(
            config=config,
            worker_name="example_rotated_worker"
        )

        self.items_checked = 0

    def check_for_items(self):
        """
        Check for new items to process.

        In a real worker, this would:
        - Query an API
        - Check a database
        - Monitor a file system
        - Watch a queue
        """
        self.items_checked += 1

        # Simulate finding items occasionally
        if self.items_checked % 3 == 0:
            return [
                {"id": f"item_{self.items_checked}_{i}", "data": "x" * 100}
                for i in range(5)
            ]

        return []

    def process_item(self, item):
        """
        Process a single item.

        In a real worker, this would:
        - Transform data
        - Call APIs
        - Update databases
        - Send notifications
        """
        import time
        time.sleep(0.1)  # Simulate processing time

        result = f"Processed {item['id']}"

        # Log to journal with some data
        self._journal("item_processing_detail", {
            "item_id": item['id'],
            "processing_time_ms": 100,
            "bytes_processed": len(item['data']),
            "result": result
        })

        return result

    def get_item_id(self, item):
        """Get unique ID for deduplication."""
        return item['id']


def print_status(worker: ForeverWorker):
    """Print detailed worker status including rotation info."""
    status = worker.get_status()

    print("\n" + "="*60)
    print("WORKER STATUS")
    print("="*60)
    print(f"Worker: {status['worker_name']}")
    print(f"State: {status['state']}")
    print(f"Uptime: {status['uptime_human']}")
    print(f"Items processed: {status['items_processed']}")
    print(f"Errors: {status['errors_count']}")
    print(f"Poll interval: {status['poll_interval']:.1f}s")
    print(f"\nMemory:")
    print(f"  Processed items tracked: {status['processed_items_tracked']}")
    print(f"  Dreams: {status['dreams_count']}")
    print(f"  Activity history: {status['activity_history_size']}")

    if "log_rotation" in status:
        lr = status["log_rotation"]
        print(f"\nLog Rotation:")
        print(f"  Enabled: {lr['enabled']}")
        print(f"  Journal total size: {lr['journal_total_size_mb']:.3f} MB")
        print(f"  Hours since cleanup: {lr['hours_since_cleanup']:.1f}")
        print(f"  Next cleanup in: {lr['next_cleanup_in_hours']:.1f} hours")

    # Get disk usage
    summary = get_disk_usage_summary(worker.work_dir)
    print(f"\nDisk Usage:")
    print(f"  Total size: {summary['total_size_mb']:.2f} MB")
    print(f"  File count: {summary['file_count']}")
    if summary['by_extension']:
        print(f"  By extension:")
        for ext, stats in summary['by_extension'].items():
            print(f"    {ext}: {stats['count']} files, {stats['size_mb']:.2f} MB")

    print("="*60 + "\n")


def run_example():
    """Run the example worker."""
    print("\n" + "="*60)
    print("FOREVER WORKER WITH LOG ROTATION - EXAMPLE")
    print("="*60 + "\n")

    print("Creating worker with log rotation enabled...")
    worker = ExampleWorker()

    print(f"Worker directory: {worker.work_dir}")
    print(f"Log rotation enabled: {worker.journal_rotator is not None}")
    print(f"Journal max size: {worker.config.journal_max_size_mb} MB")
    print(f"Max rotations: {worker.config.journal_max_rotations}")
    print(f"Cleanup interval: {worker.config.cleanup_interval_hours} hours")

    # Write a bunch of journal entries to demonstrate rotation
    print("\nGenerating journal entries to demonstrate rotation...")
    for i in range(500):
        worker._journal("demo_event", {
            "iteration": i,
            "data": "x" * 500,  # Make entries large to trigger rotation
            "timestamp_detail": f"2024-01-{i%30+1:02d}"
        })

        if i > 0 and i % 100 == 0:
            print(f"  Written {i} entries...")

    print("\nJournal generation complete.")

    # Check status
    print_status(worker)

    # Check for rotated files
    rotated_files = list(worker.work_dir.glob('activity_journal.jsonl.*'))
    if rotated_files:
        print(f"Rotated journal files found: {len(rotated_files)}")
        for f in sorted(rotated_files):
            size_mb = f.stat().st_size / 1024 / 1024
            print(f"  {f.name}: {size_mb:.3f} MB")
    else:
        print("No rotated files yet (journal under size limit)")

    print("\n" + "="*60)
    print("Example complete!")
    print("="*60)
    print("\nTo run the worker in forever mode:")
    print("  worker.run_forever()")
    print("\nTo stop the worker:")
    print("  Create file: " + str(worker.work_dir / "STOP"))
    print("  Or press Ctrl+C")
    print("="*60 + "\n")

    # Cleanup
    import shutil
    if worker.work_dir.exists():
        print(f"Cleaning up worker directory: {worker.work_dir}")
        shutil.rmtree(worker.work_dir)


if __name__ == "__main__":
    run_example()
