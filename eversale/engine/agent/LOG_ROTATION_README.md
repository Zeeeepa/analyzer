# Log Rotation System

Prevents unbounded growth in forever mode by automatically rotating log files, trimming in-memory data, and cleaning up old files.

## Overview

The log rotation system provides:

1. **Automatic file rotation** - Rotates JSONL/JSON files when they exceed size limits
2. **Configurable retention** - Keeps only last N rotated files
3. **In-memory trimming** - Prevents memory leaks from unbounded lists
4. **Periodic cleanup** - Removes old checkpoints and rotated logs
5. **Zero-config integration** - Enabled by default in ForeverWorker

## Quick Start

### Using with ForeverWorker

Log rotation is enabled by default:

```python
from forever_operations import ForeverWorker, ForeverConfig

# Default config has rotation enabled
worker = MyWorker()
worker.run_forever()

# Custom rotation settings
config = ForeverConfig(
    journal_max_size_mb=10.0,      # Rotate journal at 10MB
    journal_max_rotations=5,       # Keep last 5 rotations
    cleanup_interval_hours=6.0,    # Cleanup every 6 hours
    checkpoint_max_age_days=7,     # Remove checkpoints older than 7 days
    rotated_logs_max_age_days=30   # Remove old rotated logs after 30 days
)
worker = MyWorker(config=config)
```

### Standalone Usage

```python
from log_rotation import LogRotator, JSONLRotator

# Basic file rotation
rotator = LogRotator(max_size_mb=10.0, max_rotations=5)
rotator.rotate_if_needed(Path('my_log.json'))

# JSONL with line-based rotation
jsonl_rotator = JSONLRotator(
    max_size_mb=10.0,
    max_lines=50000,      # Rotate after 50k lines
    max_age_hours=24.0,   # Or after 24 hours
    max_rotations=5
)
jsonl_rotator.rotate_if_needed(Path('activity.jsonl'))

# In-memory list trimming
trimmed = rotator.trim_in_memory_list(
    my_large_list,
    max_size=1000,
    keep_recent=True  # Keep most recent items
)
```

## Configuration Options

### ForeverConfig Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `log_rotation_enabled` | `True` | Enable/disable log rotation |
| `journal_max_size_mb` | `10.0` | Rotate journal when exceeding this size |
| `journal_max_rotations` | `5` | Number of rotated files to keep |
| `cleanup_interval_hours` | `6.0` | How often to run cleanup |
| `checkpoint_max_age_days` | `7` | Remove checkpoints older than this |
| `rotated_logs_max_age_days` | `30` | Remove rotated logs older than this |

### LogRotator Parameters

```python
LogRotator(
    max_size_mb=10.0,      # File size limit before rotation
    max_rotations=5,       # Number of rotated files to keep
    compression=False      # Future: compress rotated files
)
```

### JSONLRotator Parameters

```python
JSONLRotator(
    max_size_mb=10.0,      # Size-based rotation
    max_lines=50000,       # Line-based rotation (optional)
    max_age_hours=24.0,    # Time-based rotation (optional)
    max_rotations=5        # Rotations to keep
)
```

## How It Works

### File Rotation

When a file exceeds the size limit:

1. `file.jsonl` is renamed to `file.jsonl.1`
2. Existing rotations are shifted: `.1` -> `.2`, `.2` -> `.3`, etc.
3. Oldest rotation (`.5` if max_rotations=5) is deleted
4. New empty `file.jsonl` is created

Example rotation sequence:

```
Initial state:
  activity_journal.jsonl (15 MB)

After rotation:
  activity_journal.jsonl (0 KB)       <- New file
  activity_journal.jsonl.1 (15 MB)    <- Previous file
  activity_journal.jsonl.2 (12 MB)    <- Older
  activity_journal.jsonl.3 (10 MB)    <- Older
  activity_journal.jsonl.4 (11 MB)    <- Older
  activity_journal.jsonl.5 (9 MB)     <- Oldest
```

### In-Memory Trimming

Prevents unbounded growth of in-memory data structures:

```python
# Automatically trimmed during periodic cleanup:
- activity_history: kept to 500 items
- dreams: kept to max_dreams config value
- processed_items: kept to max_processed_history config value
```

### Periodic Cleanup

Runs every `cleanup_interval_hours`:

1. **Checkpoint cleanup** - Removes checkpoint files older than `checkpoint_max_age_days`
2. **Rotated log cleanup** - Removes rotated logs older than `rotated_logs_max_age_days`
3. **In-memory trimming** - Trims large lists
4. **File rotation** - Rotates supplemental files (dreams.json, processed.json)

## Files Managed

### Automatically Rotated

| File | Description | Rotation Trigger |
|------|-------------|------------------|
| `activity_journal.jsonl` | Main activity log | Size exceeds limit |
| `dreams.json` | Dream mode insights | Size exceeds limit |
| `processed.json` | Processed items cache | Size exceeds limit |

### Cleaned Up

| File Pattern | Max Age | Description |
|--------------|---------|-------------|
| `*.json` (in checkpoint dir) | 7 days | Old checkpoint files |
| `*.jsonl.*` | 30 days | Old rotated journal files |
| `*.json.*` | 30 days | Old rotated JSON files |

## Monitoring

### Check Status

```python
status = worker.get_status()

print(f"Log rotation enabled: {status['log_rotation']['enabled']}")
print(f"Journal total size: {status['log_rotation']['journal_total_size_mb']} MB")
print(f"Hours since cleanup: {status['log_rotation']['hours_since_cleanup']}")
print(f"Next cleanup in: {status['log_rotation']['next_cleanup_in_hours']} hours")
```

### Disk Usage Summary

```python
from log_rotation import get_disk_usage_summary

summary = get_disk_usage_summary(worker.work_dir)

print(f"Total size: {summary['total_size_mb']} MB")
print(f"File count: {summary['file_count']}")
print("By extension:", summary['by_extension'])
print("Largest files:", summary['largest_files'])
```

## Manual Operations

### Force Rotation

```python
from log_rotation import LogRotator

rotator = LogRotator(max_size_mb=10.0, max_rotations=5)
journal_path = worker.work_dir / 'activity_journal.jsonl'

# Force rotation regardless of size
rotator._rotate_file(journal_path)
```

### Manual Cleanup

```python
from log_rotation import periodic_cleanup

stats = periodic_cleanup(
    work_dir=worker.work_dir,
    checkpoint_dir=Path.home() / '.eversale' / 'checkpoints',
    checkpoint_age_days=7,
    rotated_logs_age_days=30
)

print(f"Removed {stats['checkpoints_removed']} checkpoints")
print(f"Removed {stats['rotated_logs_removed']} rotated logs")
```

### Trim JSONL File

```python
from log_rotation import JSONLRotator

rotator = JSONLRotator()
rotator.trim_to_lines(
    Path('large_log.jsonl'),
    max_lines=10000  # Keep only last 10k lines
)
```

## Best Practices

### For Long-Running Workers

```python
config = ForeverConfig(
    # Conservative rotation
    journal_max_size_mb=5.0,       # Rotate more frequently
    journal_max_rotations=10,      # Keep more history

    # Frequent cleanup
    cleanup_interval_hours=3.0,    # Cleanup every 3 hours

    # Aggressive old file removal
    checkpoint_max_age_days=3,     # Remove checkpoints after 3 days
    rotated_logs_max_age_days=14   # Keep rotated logs for 2 weeks
)
```

### For High-Volume Workers

```python
config = ForeverConfig(
    # More aggressive rotation
    journal_max_size_mb=2.0,       # Smaller files
    journal_max_rotations=5,       # Less history

    # More frequent cleanup
    cleanup_interval_hours=1.0,    # Cleanup every hour

    # In-memory limits
    max_processed_history=5000,    # Smaller cache
    max_dreams=50                  # Fewer dreams
)
```

### For Development/Testing

```python
config = ForeverConfig(
    # Disabled rotation for debugging
    log_rotation_enabled=False
)
```

## Troubleshooting

### Logs Growing Too Fast

1. Reduce `journal_max_size_mb` to rotate more frequently
2. Decrease `journal_max_rotations` to keep less history
3. Reduce `cleanup_interval_hours` for more frequent cleanup
4. Check if you're logging too much data per entry

### Out of Disk Space

```python
# Get disk usage summary
from log_rotation import get_disk_usage_summary, cleanup_rotated_logs

summary = get_disk_usage_summary(worker.work_dir)
print("Largest files:", summary['largest_files'])

# Emergency cleanup - remove all old rotated logs
cleanup_rotated_logs(worker.work_dir, max_age_days=1)
```

### Memory Growing

1. Check in-memory list sizes: `activity_history`, `dreams`, `processed_items`
2. Reduce `max_processed_history` and `max_dreams` in config
3. Force cleanup: `worker._trim_in_memory_data()`

### Rotation Not Working

```python
# Check if rotation is enabled
print(f"Rotator exists: {worker.journal_rotator is not None}")

# Check file size
journal_path = worker.work_dir / worker.config.journal_file
if journal_path.exists():
    size_mb = journal_path.stat().st_size / 1024 / 1024
    print(f"Journal size: {size_mb} MB (limit: {worker.config.journal_max_size_mb} MB)")

# Force rotation
if worker.journal_rotator:
    worker.journal_rotator.rotate_if_needed(journal_path)
```

## Testing

Run the test suite:

```bash
python test_log_rotation.py
```

Tests cover:
- Basic file rotation
- JSONL rotation with line count
- In-memory list trimming
- Checkpoint cleanup
- Disk usage summary
- ForeverWorker integration

## Performance Impact

The log rotation system is designed for minimal overhead:

- **Rotation check**: O(1) - simple file size check
- **Rotation operation**: O(1) - file renames only
- **In-memory trim**: O(n) - but runs infrequently
- **Cleanup**: O(m) where m = number of files in directory

Typical overhead: <0.1% of worker runtime

## Future Enhancements

Planned features:

1. **Compression** - gzip rotated files to save disk space
2. **Remote archival** - Upload old rotations to S3/cloud storage
3. **Smart rotation** - Rotate based on activity patterns
4. **Custom callbacks** - Hooks for rotation events
5. **Metrics export** - Export rotation stats to monitoring systems

## Related Files

- `log_rotation.py` - Main rotation module
- `forever_operations.py` - ForeverWorker integration
- `test_log_rotation.py` - Test suite
- `LOG_ROTATION_README.md` - This file

## Support

For issues or questions, check:

1. Worker status: `worker.get_status()`
2. Disk usage: `get_disk_usage_summary(worker.work_dir)`
3. Test rotation: `python test_log_rotation.py`
