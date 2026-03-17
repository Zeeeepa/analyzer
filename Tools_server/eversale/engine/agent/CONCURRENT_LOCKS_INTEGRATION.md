# Concurrent Locks Integration Guide

This document describes how to integrate the new concurrent locking system into the agent codebase.

## Overview

The `concurrent_locks.py` module provides:
1. **AsyncRWLock** - Multiple readers OR single writer (async)
2. **DistributedLock** - Cross-process file-based locking
3. **LockManager** - Centralized lock management by resource name
4. **Decorators** - `@read_lock`, `@write_lock` for easy integration
5. **Context managers** - Both async and sync support
6. **Timeout handling** - Prevents deadlocks
7. **Lock statistics** - Monitoring and performance metrics

## Integration Changes

### 1. memory_architecture.py

The module has been updated with the import statement. Now update the memory store classes:

#### Import (ALREADY DONE)
```python
# Import concurrent locking system for safe multi-agent access
from .concurrent_locks import get_lock_manager, read_lock, write_lock
```

#### EpisodicMemoryStore - Add to __init__ method

FIND (around line 1398):
```python
def __init__(self, db_path: Path = EPISODIC_DB, cache_adapter: Optional[CacheAdapter] = None):
    self.db_path = db_path
    self.scorer = MemoryScorer()
    # Locking strategy: Use asyncio.Lock for all operations to prevent race conditions
    # This allows safe usage in both sync (via asyncio.run()) and async contexts
    # Avoids deadlocks from mixing threading.Lock with asyncio.Lock
    self._lock = asyncio.Lock()
    self._consolidation_lock = None  # Will be set to asyncio.Lock() when needed
```

REPLACE WITH:
```python
def __init__(self, db_path: Path = EPISODIC_DB, cache_adapter: Optional[CacheAdapter] = None):
    self.db_path = db_path
    self.scorer = MemoryScorer()

    # Use centralized LockManager for concurrent access control
    self._lock_manager = get_lock_manager()
    self._resource_name = f"episodic_db:{self.db_path.name}"

    # Legacy asyncio.Lock kept for backward compatibility with internal methods
    self._lock = asyncio.Lock()
    self._consolidation_lock = None  # Will be set to asyncio.Lock() when needed
```

#### EpisodicMemoryStore - Wrap key methods

FIND methods like `add_episode`, `get_episode`, `query_episodes`, etc.

ADD decorators to read methods (queries):
```python
@read_lock("episodic_db:episodic_memory.db", timeout=10.0)
async def get_episode(self, memory_id: str) -> Optional[EpisodicMemory]:
    # ... existing code ...
```

```python
@read_lock("episodic_db:episodic_memory.db", timeout=10.0)
async def query_episodes(
    self,
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
    min_score: float = 0.0,
    limit: int = 10
) -> List[EpisodicMemory]:
    # ... existing code ...
```

ADD decorators to write methods (add/update/delete):
```python
@write_lock("episodic_db:episodic_memory.db", timeout=30.0)
async def add_episode(self, episode: EpisodicMemory):
    # ... existing code ...
```

```python
@write_lock("episodic_db:episodic_memory.db", timeout=30.0)
async def update_episode(self, memory_id: str, updates: Dict[str, Any]):
    # ... existing code ...
```

OR use context managers directly:
```python
async def add_episode(self, episode: EpisodicMemory):
    async with self._lock_manager.write_lock(self._resource_name):
        # ... existing database write code ...
```

```python
async def query_episodes(
    self,
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
    min_score: float = 0.0,
    limit: int = 10
) -> List[EpisodicMemory]:
    async with self._lock_manager.read_lock(self._resource_name):
        # ... existing database read code ...
```

#### SemanticMemoryStore - Same pattern

FIND class `SemanticMemoryStore` (around line 1800):

ADD to __init__:
```python
def __init__(self, db_path: Path = SEMANTIC_DB, cache_adapter: Optional[CacheAdapter] = None):
    # ... existing init code ...

    # Use centralized LockManager
    self._lock_manager = get_lock_manager()
    self._resource_name = f"semantic_db:{self.db_path.name}"

    # ... rest of init ...
```

WRAP methods:
- Read methods: `get_knowledge`, `query_semantic`, `search_by_pattern` → `@read_lock`
- Write methods: `add_knowledge`, `update_knowledge`, `validate_knowledge` → `@write_lock`

#### SkillMemoryStore - Same pattern

FIND class `SkillMemoryStore` (around line 2200):

ADD to __init__:
```python
def __init__(self, db_path: Path = SKILL_DB, cache_adapter: Optional[CacheAdapter] = None):
    # ... existing init code ...

    # Use centralized LockManager
    self._lock_manager = get_lock_manager()
    self._resource_name = f"skill_db:{self.db_path.name}"

    # ... rest of init ...
```

WRAP methods:
- Read methods: `get_skill`, `query_skills`, `get_by_category` → `@read_lock`
- Write methods: `add_skill`, `update_skill_stats`, `record_execution` → `@write_lock`

### 2. skill_library.py

#### Import

ADD after existing imports (around line 41):
```python
# Import concurrent locking system for safe multi-agent access
from .concurrent_locks import get_lock_manager, read_lock, write_lock
```

#### SkillLibrary class

FIND `class SkillLibrary:` (around line 1268):

ADD to __init__ (around line 1273):
```python
def __init__(self):
    self.skills: Dict[str, Skill] = {}
    self.retriever = SkillRetriever()
    self.validator = SkillValidator()
    self.generator = SkillGenerator()
    self.composer = SkillComposer()

    # Use centralized LockManager for concurrent access
    self._lock_manager = get_lock_manager()
    self._resource_name = "skill_library"

    # Load existing skills
    self._load_skills()

    # Initialize with pre-built skills if library is empty
    if not self.skills:
        self._initialize_prebuilt_skills()

    logger.info(f"Initialized SkillLibrary with {len(self.skills)} skills")
```

WRAP key methods:

Read operations (concurrent access):
```python
@read_lock("skill_library", timeout=10.0)
def get_skill(self, skill_id: str) -> Optional[Skill]:
    """Get a skill by ID"""
    return self.skills.get(skill_id)

@read_lock("skill_library", timeout=10.0)
def search_skills(
    self,
    query: str,
    category: Optional[SkillCategory] = None,
    min_success_rate: float = 0.0,
    limit: int = 10
) -> List[Skill]:
    # ... existing code ...
```

Write operations (exclusive access):
```python
@write_lock("skill_library", timeout=30.0)
def add_skill(self, skill: Skill, validate: bool = True) -> bool:
    # ... existing code ...

@write_lock("skill_library", timeout=30.0)
def record_skill_usage(
    self,
    skill_id: str,
    success: bool,
    execution_time: float,
    error: str = ""
):
    # ... existing code ...

@write_lock("skill_library", timeout=30.0)
def deprecate_skill(self, skill_id: str, replacement_id: Optional[str] = None):
    # ... existing code ...
```

File I/O operations (use distributed lock for cross-process safety):
```python
def _save_skills(self):
    """Save skills to disk"""
    with self._lock_manager.distributed_lock(f"{self._resource_name}:file"):
        try:
            skills_data = [skill.to_dict() for skill in self.skills.values()]
            skills_file = SKILLS_DIR / "skills.json"
            skills_file.write_text(json.dumps(skills_data, indent=2))
            logger.debug(f"Saved {len(self.skills)} skills to disk")
        except Exception as e:
            logger.error(f"Failed to save skills: {e}")

def _load_skills(self):
    """Load skills from disk"""
    with self._lock_manager.distributed_lock(f"{self._resource_name}:file"):
        skills_file = SKILLS_DIR / "skills.json"
        if not skills_file.exists():
            return

        try:
            data = json.loads(skills_file.read_text())
            for skill_data in data:
                skill = Skill.from_dict(skill_data)
                self.skills[skill.skill_id] = skill

                # Add to vector database if active
                if skill.status == SkillStatus.ACTIVE:
                    self.retriever.add_skill(skill)

            logger.info(f"Loaded {len(self.skills)} skills from disk")
        except Exception as e:
            logger.error(f"Failed to load skills: {e}")
```

#### SkillRetriever class

FIND `class SkillRetriever:` (around line 344):

ADD to __init__:
```python
def __init__(self, collection_name: str = "skills"):
    self.collection_name = collection_name
    self.client = None
    self.collection = None

    # Use lock for vector database access (if ChromaDB is available)
    self._lock_manager = get_lock_manager()
    self._resource_name = f"skill_retriever:{collection_name}"

    # ... rest of existing init code ...
```

WRAP vector DB methods:
```python
def add_skill(self, skill: Skill):
    """Add skill to vector database"""
    if not self.collection:
        return

    with self._lock_manager.distributed_lock(f"{self._resource_name}:add"):
        # ... existing code ...

def search(
    self,
    query: str,
    category: Optional[SkillCategory] = None,
    min_success_rate: float = 0.0,
    limit: int = 10
) -> List[Tuple[str, float]]:
    """Search for skills matching query"""
    if not self.collection:
        return []

    # Read operation - use read lock
    with self._lock_manager.distributed_lock(f"{self._resource_name}:search"):
        # ... existing code ...
```

### 3. site_memory.py (if it exists)

If there's a site_memory.py file with database operations:

1. Import the lock manager
2. Add lock manager to __init__
3. Wrap read operations with `@read_lock` or `async with manager.read_lock()`
4. Wrap write operations with `@write_lock` or `async with manager.write_lock()`
5. Wrap file operations with `with manager.distributed_lock()`

## Example Usage

### Async Methods (Database Access)

```python
class MyStore:
    def __init__(self):
        self._lock_manager = get_lock_manager()
        self._resource_name = "my_database"

    # Using decorators
    @read_lock("my_database", timeout=10.0)
    async def read_data(self, key: str):
        # Read from database
        pass

    @write_lock("my_database", timeout=30.0)
    async def write_data(self, key: str, value: Any):
        # Write to database
        pass

    # Using context managers
    async def query_data(self, query: str):
        async with self._lock_manager.read_lock(self._resource_name):
            # Execute read query
            pass

    async def update_data(self, updates: Dict):
        async with self._lock_manager.write_lock(self._resource_name):
            # Execute write query
            pass
```

### Sync Methods (File Access)

```python
class MyLibrary:
    def __init__(self):
        self._lock_manager = get_lock_manager()
        self._resource_name = "my_library"

    def save_to_file(self, data: Dict):
        # Use distributed lock for cross-process safety
        with self._lock_manager.distributed_lock(f"{self._resource_name}:file"):
            with open("data.json", "w") as f:
                json.dump(data, f)

    def load_from_file(self):
        with self._lock_manager.distributed_lock(f"{self._resource_name}:file"):
            with open("data.json", "r") as f:
                return json.load(f)
```

## Monitoring

Get lock statistics:
```python
from concurrent_locks import get_lock_manager

manager = get_lock_manager()

# Get statistics for all resources
all_stats = manager.get_statistics()
print(json.dumps(all_stats, indent=2))

# Get statistics for specific resource
db_stats = manager.get_statistics("episodic_db:episodic_memory.db")
print(f"Read locks: {db_stats['locks']['read']['total_acquisitions']}")
print(f"Write locks: {db_stats['locks']['write']['total_acquisitions']}")
print(f"Avg wait time: {db_stats['locks']['read']['avg_wait_time_ms']:.2f}ms")

# Get current lock status
status = manager.get_lock_status()
print(json.dumps(status, indent=2))

# Detect deadlocks (async)
deadlocks = await manager.detect_deadlocks()
if deadlocks:
    print(f"Warning: {len(deadlocks)} potential deadlocks detected")
```

## Testing

See `test_concurrent_locks.py` for comprehensive test suite.

Run tests:
```bash
python -m pytest test_concurrent_locks.py -v
```

## Performance Notes

- Read locks have near-zero overhead when no writers are present
- Write locks use FIFO queuing for fairness
- Default timeouts: 10s (read), 30s (write), 60s (distributed)
- Distributed locks use fcntl on Linux/Unix, threading.Lock fallback on Windows
- Lock statistics are tracked in memory (negligible overhead)

## Troubleshooting

**TimeoutError: Lock timeout**
- Increase timeout parameter for long-running operations
- Check for deadlocks using `manager.detect_deadlocks()`
- Review lock statistics to identify bottlenecks

**RuntimeError: Cannot use _sync_lock in running event loop**
- Use `async with self._lock` in async context
- Don't call sync methods from async code

**File lock errors on Windows**
- Distributed locks fall back to threading.Lock (not cross-process safe)
- Use Linux/Unix for true cross-process locking

## Migration Path

1. **Phase 1**: Import lock manager (DONE)
2. **Phase 2**: Add lock manager to __init__ methods
3. **Phase 3**: Wrap critical sections with locks
4. **Phase 4**: Test concurrent access
5. **Phase 5**: Monitor statistics and adjust timeouts

Start with read-heavy operations first (lower risk), then add write locks.

## Best Practices

1. **Always use timeouts** - Prevents indefinite blocking
2. **Lock granularity** - Lock at resource level, not method level
3. **Read vs Write** - Use read locks for queries, write locks for modifications
4. **Short critical sections** - Minimize time holding locks
5. **Consistent naming** - Use descriptive resource names
6. **Monitor statistics** - Track lock contention and performance
7. **Test concurrency** - Run multi-agent tests to verify safety

## Questions?

- Check `concurrent_locks.py` docstrings for detailed API documentation
- Review example usage in `__main__` section of concurrent_locks.py
- Look at test_concurrent_locks.py for comprehensive examples
