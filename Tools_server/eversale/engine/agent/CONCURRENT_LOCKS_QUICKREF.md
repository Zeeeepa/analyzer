# Concurrent Locks - Quick Reference Card

## Import

```python
from concurrent_locks import get_lock_manager, read_lock, write_lock, distributed_lock
```

## Get Manager

```python
manager = get_lock_manager()  # Singleton instance
```

## Usage Patterns

### 1. Async Read Lock (Decorator)

```python
@read_lock("database", timeout=10.0)
async def query_data(key: str):
    return await db.get(key)
```

**Use for**: Queries, lookups, non-modifying operations
**Allows**: Multiple concurrent readers
**Blocks**: Only when writer is active

### 2. Async Write Lock (Decorator)

```python
@write_lock("database", timeout=30.0)
async def update_data(key: str, value: Any):
    await db.set(key, value)
```

**Use for**: Updates, inserts, deletes
**Allows**: Only one writer
**Blocks**: All readers and other writers

### 3. Async Context Manager

```python
async def process():
    manager = get_lock_manager()

    # Read
    async with manager.read_lock("database"):
        data = await read_data()

    # Write
    async with manager.write_lock("database"):
        await write_data(data)
```

**Use for**: Dynamic resource names, multiple locks

### 4. Distributed Lock (Cross-Process)

```python
@distributed_lock("shared_file", timeout=60.0)
def save_file(data):
    with open("file.json", "w") as f:
        json.dump(data, f)

# Or context manager
with manager.distributed_lock("shared_file"):
    with open("file.json", "r+") as f:
        data = json.load(f)
        data["counter"] += 1
        f.seek(0)
        json.dump(data, f)
```

**Use for**: File I/O, cross-process resources
**Works**: Across multiple processes

## Default Timeouts

- Read: 10 seconds
- Write: 30 seconds
- Distributed: 60 seconds

## Common Integration Pattern

```python
class MyStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock_manager = get_lock_manager()
        self._resource_name = f"my_store:{db_path.name}"

    @read_lock("my_store:data.db", timeout=10.0)
    async def get(self, key: str):
        # Read operation
        pass

    @write_lock("my_store:data.db", timeout=30.0)
    async def set(self, key: str, value: Any):
        # Write operation
        pass

    def save_to_file(self):
        # File I/O with distributed lock
        with self._lock_manager.distributed_lock(f"{self._resource_name}:file"):
            with open(self.file_path, "w") as f:
                json.dump(self.data, f)
```

## Monitoring

### Get Statistics

```python
# All resources
stats = manager.get_statistics()

# Specific resource
stats = manager.get_statistics("database")

print(f"Read acquisitions: {stats['locks']['read']['total_acquisitions']}")
print(f"Avg wait time: {stats['locks']['read']['avg_wait_time_ms']:.2f}ms")
```

### Get Current Status

```python
status = manager.get_lock_status("database")

print(f"Readers: {status['readers']}")
print(f"Writer active: {status['writer_active']}")
print(f"Pending writes: {status['pending_writes']}")
```

### Detect Deadlocks

```python
deadlocks = await manager.detect_deadlocks()

if deadlocks:
    for dl in deadlocks:
        print(f"Resource: {dl['resource']}")
        print(f"Wait time: {dl['wait_time_seconds']:.2f}s")
```

## Error Handling

```python
try:
    async with manager.write_lock("database", timeout=5.0):
        await long_operation()
except TimeoutError:
    logger.error("Lock timeout - increase timeout or optimize operation")
```

**Note**: Locks are always released, even on exception!

## Testing

```python
# Run all tests
pytest test_concurrent_locks.py -v

# Run specific test
pytest test_concurrent_locks.py::test_async_rwlock_multiple_readers -v

# Run examples
python concurrent_locks_example.py
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| TimeoutError | Increase timeout or optimize critical section |
| High wait times | Check statistics, reduce lock hold time |
| Deadlock detected | Review lock order, ensure proper release |
| File lock fails (Windows) | Use Linux/Unix or accept threading.Lock fallback |

## When to Use Each Lock Type

| Operation | Lock Type | Why |
|-----------|-----------|-----|
| Database SELECT | Read Lock | Allow concurrent queries |
| Database INSERT/UPDATE | Write Lock | Prevent race conditions |
| Read JSON file | Distributed Lock | Cross-process safety |
| Write JSON file | Distributed Lock | Cross-process safety |
| In-memory read | Read Lock | High concurrency |
| In-memory write | Write Lock | Consistency |

## Best Practices

1. ✅ Always use timeouts
2. ✅ Keep critical sections short
3. ✅ Use read locks for queries
4. ✅ Use write locks for modifications
5. ✅ Use distributed locks for file I/O
6. ✅ Monitor statistics regularly
7. ✅ Test with multiple agents

## Quick Decision Tree

```
Need to access resource?
│
├─ Read only? → Use read_lock
│
├─ Modify data?
│  ├─ In-memory/database? → Use write_lock
│  └─ File on disk? → Use distributed_lock
│
└─ Multiple processes? → Use distributed_lock
```

## File Locations

- Core: `/mnt/c/ev29/agent/concurrent_locks.py`
- Docs: `/mnt/c/ev29/agent/CONCURRENT_LOCKS_README.md`
- Integration: `/mnt/c/ev29/agent/CONCURRENT_LOCKS_INTEGRATION.md`
- Examples: `/mnt/c/ev29/agent/concurrent_locks_example.py`
- Tests: `/mnt/c/ev29/agent/test_concurrent_locks.py`
- Summary: `/mnt/c/ev29/agent/CONCURRENT_LOCKS_SUMMARY.md`

## Support

- Review README for full documentation
- Check integration guide for patterns
- Run examples for demonstrations
- See tests for comprehensive usage

