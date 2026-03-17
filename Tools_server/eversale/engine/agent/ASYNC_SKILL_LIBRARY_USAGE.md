# Async Skill Library Usage Guide

## Overview

The Skill Library has been enhanced with async operations to support concurrent skill access from parallel agents. All original sync methods remain available for backward compatibility.

## New Async Features

### 1. Async Read/Write Locking

**Purpose**: Allows multiple agents to read skills simultaneously while ensuring exclusive access for writes.

```python
from skill_library import get_skill_library

library = get_skill_library()

# Multiple agents can read concurrently
skill1 = await library.get_skill_async("skill_id_1")
skill2 = await library.get_skill_async("skill_id_2")

# Writes get exclusive access
await library.add_skill_async(new_skill)
```

**Implementation**: `AsyncRWLock` class with `read_lock()` and `write_lock()` context managers.

### 2. Skill Caching with Invalidation

**Purpose**: Reduce I/O and improve performance with LRU cache and TTL.

```python
# Get skill with caching (default)
skill = await library.get_skill_async("skill_id", use_cache=True)

# Search with caching
skills = await library.search_skills_async(
    query="login to website",
    use_cache=True
)

# Cache is automatically invalidated on updates
await library.add_skill_async(updated_skill)  # Invalidates cache
```

**Configuration**:
- Max cache size: 100 items (configurable in `SkillCache` init)
- TTL: 3600 seconds (1 hour)
- Pattern-based invalidation supported

### 3. Async Skill Execution with Timeout

**Purpose**: Execute skills asynchronously with automatic timeout protection.

```python
# Execute with default 30s timeout
result = await library.execute_skill_async(
    skill_id="nav_login_generic",
    context={"url": "https://example.com"},
    timeout=30.0
)

# Custom timeout
result = await library.execute_skill_async(
    skill_id="slow_skill",
    context={},
    timeout=60.0  # 60 seconds
)
```

**Features**:
- Automatic timeout handling
- Metrics recording (success/failure/time)
- Cache invalidation on usage updates

### 4. Batch Skill Operations

**Purpose**: Add or execute multiple skills concurrently for better performance.

#### Batch Add
```python
skills = [skill1, skill2, skill3]

results = await library.batch_add_skills(skills, validate=True)
# Returns: {"skill_id_1": True, "skill_id_2": True, "skill_id_3": False}
```

#### Batch Execute
```python
executions = [
    ("skill_id_1", {"param": "value1"}),
    ("skill_id_2", {"param": "value2"}),
    ("skill_id_3", {"param": "value3"}),
]

results = await library.batch_execute_skills(
    executions,
    timeout=30.0,
    max_concurrent=10  # Limit concurrent executions
)

# Results: [(skill_id, result, error), ...]
for skill_id, result, error in results:
    if error:
        print(f"{skill_id} failed: {error}")
    else:
        print(f"{skill_id} succeeded: {result}")
```

### 5. Skill Versioning and Optimistic Locking

**Purpose**: Prevent conflicts when multiple agents update the same skill.

```python
# Get current version
version = await library.get_version("skill_id")
print(f"Current version: {version.version}")

# Update with optimistic locking
try:
    await library.add_skill_async(
        updated_skill,
        expected_version=version.version  # Will fail if version changed
    )
except ValueError as e:
    print(f"Version conflict: {e}")
    # Reload and retry
```

**Version History**:
```python
# Get all versions
history = await library.get_version_history("skill_id")

for version_data in history:
    print(f"Version {version_data['version']}: {version_data['saved_at']}")
```

### 6. Concurrent Skill Composition

**Purpose**: Execute multiple skills in sequence asynchronously.

```python
result = await library.compose_skills_async(
    skill_ids=["nav_login", "extract_data", "save_results"],
    context={"url": "https://example.com"},
    workflow_name="Login and Extract Workflow",
    timeout_per_skill=30.0
)

print(f"Workflow: {result['workflow_name']}")
print(f"Success: {result['success']}")
print(f"Completed: {result['completed_steps']}/{result['total_steps']}")
```

## Concurrent Agent Example

```python
import asyncio
from skill_library import get_skill_library

async def agent_task(agent_id: int):
    """Simulates an agent using skills"""
    library = get_skill_library()

    # Search for skills (cached)
    skills = await library.search_skills_async(
        query="login",
        limit=5,
        use_cache=True
    )

    # Execute skill with timeout
    result = await library.execute_skill_async(
        skill_id=skills[0].skill_id,
        context={"agent_id": agent_id},
        timeout=30.0
    )

    return result

async def main():
    # Run 5 agents concurrently
    agents = [agent_task(i) for i in range(5)]
    results = await asyncio.gather(*agents)
    print(f"Completed {len(results)} agent tasks")

asyncio.run(main())
```

## Migration Guide

### From Sync to Async

**Before (Sync)**:
```python
library = get_skill_library()

# Sync operations
skill = library.get_skill("skill_id")
skills = library.search_skills("login")
result = skill.execute(context)
```

**After (Async)**:
```python
library = get_skill_library()

# Async operations with caching
skill = await library.get_skill_async("skill_id", use_cache=True)
skills = await library.search_skills_async("login", use_cache=True)
result = await skill.execute_async(context, timeout=30.0)
```

### Backward Compatibility

All original sync methods still work:
```python
# These still work (no changes needed)
library.add_skill(skill)
library.get_skill("skill_id")
library.search_skills("query")
skill.execute(context)
```

## Performance Considerations

### When to Use Async Methods

✅ **Use Async When**:
- Multiple agents accessing skills concurrently
- Performing batch operations
- Need timeout protection
- Want caching benefits
- Building scalable agent systems

❌ **Use Sync When**:
- Single-threaded simple scripts
- Quick prototyping
- Backward compatibility required
- No concurrency needs

### Concurrency Limits

```python
# Control concurrent executions
await library.batch_execute_skills(
    executions,
    max_concurrent=10  # Adjust based on system resources
)
```

**Recommended limits**:
- CPU-bound skills: `max_concurrent = cpu_count`
- I/O-bound skills: `max_concurrent = 20-50`
- Mixed workloads: `max_concurrent = 10-20`

## Error Handling

```python
import asyncio

try:
    result = await library.execute_skill_async(
        skill_id="skill_id",
        context={},
        timeout=5.0
    )
except asyncio.TimeoutError:
    print("Skill execution timed out")
except ValueError as e:
    print(f"Skill not found or invalid: {e}")
except RuntimeError as e:
    print(f"Skill execution failed: {e}")
```

## Best Practices

1. **Always use timeouts** for skill execution:
   ```python
   result = await library.execute_skill_async(skill_id, context, timeout=30.0)
   ```

2. **Enable caching** for read-heavy workloads:
   ```python
   skill = await library.get_skill_async(skill_id, use_cache=True)
   ```

3. **Use batch operations** for multiple skills:
   ```python
   results = await library.batch_execute_skills(executions, max_concurrent=10)
   ```

4. **Handle version conflicts** when updating:
   ```python
   try:
       await library.add_skill_async(skill, expected_version=current_version)
   except ValueError:
       # Reload and retry
   ```

5. **Limit concurrency** based on resources:
   ```python
   await library.batch_execute_skills(
       executions,
       max_concurrent=min(len(executions), 20)
   )
   ```

## API Reference

### Async Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `add_skill_async(skill, validate, expected_version)` | Add skill with optimistic locking | `bool` |
| `get_skill_async(skill_id, use_cache)` | Get skill with caching | `Optional[Skill]` |
| `search_skills_async(query, category, min_success_rate, limit, use_cache)` | Search with caching | `List[Skill]` |
| `execute_skill_async(skill_id, context, timeout)` | Execute with timeout | `Any` |
| `batch_add_skills(skills, validate)` | Add multiple skills | `Dict[str, bool]` |
| `batch_execute_skills(executions, timeout, max_concurrent)` | Execute multiple skills | `List[Tuple]` |
| `compose_skills_async(skill_ids, context, workflow_name, timeout_per_skill)` | Execute workflow | `Dict[str, Any]` |
| `get_version(skill_id)` | Get current version | `Optional[SkillVersion]` |
| `get_version_history(skill_id)` | Get all versions | `List[Dict]` |

### Helper Classes

- **AsyncRWLock**: Read/Write lock for concurrent access
- **SkillCache**: LRU cache with TTL (100 items, 1 hour TTL)
- **SkillVersion**: Version tracking for optimistic locking

## Examples

See `/mnt/c/ev29/agent/skill_library.py` for complete examples:
- `example_usage()`: Basic async operations
- `example_concurrent_agents()`: Multi-agent concurrent access

Run examples:
```bash
python skill_library.py
```

