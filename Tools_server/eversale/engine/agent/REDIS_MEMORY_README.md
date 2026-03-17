# Redis Memory Adapter for Distributed Agent Memory

## Overview

The Redis Memory Adapter enables distributed memory sharing across multiple agent instances using Redis as a backend, with automatic fallback to local SQLite when Redis is unavailable.

## Features

### Core Capabilities
1. **Connection Pooling** - Efficient Redis connection management with automatic reconnection
2. **Serialization/Deserialization** - Automatic conversion of memory objects with compression for large data
3. **Key Namespacing** - Isolated memory spaces per agent instance
4. **TTL Support** - Automatic memory expiration based on memory type
5. **Pub/Sub** - Real-time memory synchronization between agents
6. **Fallback to SQLite** - Seamless operation when Redis is unavailable
7. **Async Operations** - Full async/await support throughout
8. **Batch Operations** - Efficient bulk operations with pipelining
9. **Memory Compression** - Automatic compression for objects >1KB

### Memory Types & TTLs

| Memory Type | Default TTL | Description |
|-------------|-------------|-------------|
| Working Memory | 1 hour | Current task context (agent-specific) |
| Episodic Memory | 30 days | Specific task experiences |
| Semantic Memory | 90 days | Generalized knowledge |
| Skill Memory | 180 days | Action sequences and procedures |

## Installation

### Prerequisites

```bash
# Install Redis (Ubuntu/Debian)
sudo apt-get install redis-server

# Or using Docker
docker run -d -p 6379:6379 redis:latest

# Install Python dependencies
pip install redis loguru numpy
```

### Optional Dependencies

```bash
# For better embeddings
pip install ollama
```

## Configuration

### Environment Variables

```bash
# Set memory backend (redis or sqlite)
export MEMORY_BACKEND=redis

# Redis connection settings (optional, defaults shown)
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_DB=0
export REDIS_PASSWORD=  # Leave empty if no password
```

### Programmatic Configuration

```python
from redis_memory_adapter import create_memory_adapter

# Using Redis
memory = await create_memory_adapter(
    backend="redis",
    agent_id="agent_001",
    redis_host="localhost",
    redis_port=6379,
    enable_pubsub=True
)

# Using SQLite (fallback)
memory = await create_memory_adapter(
    backend="sqlite",
    agent_id="agent_001"
)

# Using environment variable
memory = await create_memory_adapter(agent_id="agent_001")
```

## Usage

### Basic Operations

```python
import asyncio
from redis_memory_adapter import create_memory_adapter

async def main():
    # Create adapter
    memory = await create_memory_adapter(
        backend="redis",
        agent_id="agent_001",
        session_id="task_session_001"
    )

    try:
        # Add working memory steps
        await memory.add_step(
            action="search_web",
            observation="Found 10 results",
            reasoning="User requested information",
            success=True
        )

        await memory.add_step(
            action="extract_data",
            observation="Extracted key facts",
            reasoning="Consolidating information",
            success=True
        )

        # Save as episode
        episode = await memory.save_episode(
            task_prompt="Research topic X",
            outcome="Successfully gathered information",
            success=True,
            duration_seconds=5.2,
            tags=["research", "web_search"],
            importance=0.8
        )

        print(f"Saved episode: {episode.memory_id}")

        # Search memories
        results = await memory.search_episodes("research", limit=5)
        print(f"Found {len(results)} matching episodes")

        # Save a skill
        skill = await memory.save_skill(
            skill_name="web_research",
            description="Search web and extract information",
            action_sequence=[
                {"action": "search_web", "params": {"query": "{{query}}"}},
                {"action": "extract_data", "params": {"format": "structured"}}
            ],
            tags=["research"]
        )

        # Record skill execution
        await memory.record_skill_execution(
            skill_name="web_research",
            success=True,
            duration=5.2
        )

        # Get enriched context for LLM
        context = await memory.get_enriched_context(
            query="how to do research",
            detailed_steps=5,
            limit_per_type=2
        )

        print("\nEnriched context:")
        print(context)

    finally:
        # Cleanup
        await memory.close()

if __name__ == "__main__":
    asyncio.run(main())
```

### Advanced Features

#### Multi-Agent Memory Sharing

```python
# Agent 1
agent1_memory = await create_memory_adapter(
    backend="redis",
    agent_id="agent_001",
    enable_pubsub=True  # Enable real-time sync
)

# Agent 2
agent2_memory = await create_memory_adapter(
    backend="redis",
    agent_id="agent_002",
    enable_pubsub=True
)

# When agent_001 saves an episode, agent_002 will be notified via pub/sub
await agent1_memory.save_episode(...)

# Agent 2 can search and find it
results = await agent2_memory.search_episodes("relevant query")
```

#### Session Management

```python
# Create memory with specific session
memory = await create_memory_adapter(
    backend="redis",
    agent_id="agent_001",
    session_id="session_001"
)

# Rotate to new session (maintains continuity)
new_session_id = await memory.rotate_session()

# Get session history
history = await memory.get_session_history()
print(f"Session chain: {history}")
```

#### Unified Search Across Memory Types

```python
# Search all memory types at once
results = await memory.search_all(
    query="web scraping",
    limit_per_type=3
)

# Results contain:
# - results["episodic"]: Past experiences
# - results["semantic"]: Generalized knowledge
# - results["skills"]: Relevant skills

for episode in results["episodic"]:
    print(f"Episode: {episode.task_prompt}")

for semantic in results["semantic"]:
    print(f"Knowledge: {semantic.pattern}")

for skill in results["skills"]:
    print(f"Skill: {skill.skill_name} (success rate: {skill.success_rate:.1%})")
```

## Architecture

### Key Design Principles

1. **Transparent Fallback**: If Redis is unavailable, the adapter automatically uses SQLite without code changes
2. **Dual Storage**: Critical operations write to both Redis (for distribution) and SQLite (for persistence)
3. **Agent Namespacing**: Working memory is agent-specific; other memories are shared
4. **Pub/Sub Notifications**: Real-time updates when memories are created/modified
5. **Compression**: Large objects are automatically compressed using zlib
6. **Batch Processing**: Multiple operations are batched for efficiency

### Redis Key Structure

```
# Working memory (agent-specific)
agent:{agent_id}:working:{step_id}

# Shared memories
memory:episodic:{memory_id}
memory:semantic:{memory_id}
memory:skill:{memory_id}

# Indexes (sorted sets)
memory:episodic:index:all
memory:semantic:index:all
memory:skill:index:all

# Session data
session:{session_id}
session:{session_id}:episodes

# Skill name lookup
skill:name:{skill_name}

# Pub/sub channels
agent:memory:episodic
agent:memory:semantic
agent:memory:skill
```

### Serialization Format

```
Byte 0: Compression flag (0x00 = uncompressed, 0x01 = compressed)
Byte 1+: Pickled data (optionally zlib-compressed)
```

## Performance Characteristics

### Memory Overhead

- Compression threshold: 1KB
- Compression ratio: ~3-5x for text data
- Batch size: 100 operations
- Batch timeout: 100ms

### Network Efficiency

- Connection pooling (max 50 connections)
- Pipeline batching for bulk operations
- Socket timeout: 5 seconds
- Automatic reconnection on failure

### Latency Targets

- Single memory retrieval: <10ms (Redis) or <50ms (SQLite)
- Batch retrieval: <50ms for 100 items
- Search operations: <100ms
- Pub/sub latency: <50ms

## Monitoring & Debugging

### Enable Debug Logging

```python
from loguru import logger

logger.add("redis_memory.log", level="DEBUG")

# Now you'll see detailed logs:
# - Redis connections/disconnections
# - Pub/sub messages
# - Fallback events
# - Batch operations
```

### Check Redis Connection

```python
if memory.redis_manager.available:
    print("Redis is connected")
else:
    print("Using SQLite fallback")
```

### Monitor Pub/Sub

```python
# Pub/sub notifications are logged automatically
# Look for messages like:
# "Received memory update: add episodic abc123 from agent_002"
```

## Error Handling

The adapter handles errors gracefully:

1. **Connection Failures**: Automatic fallback to SQLite
2. **Timeout**: Operations timeout after 5 seconds
3. **Serialization Errors**: Logged and skipped
4. **Pub/Sub Errors**: Don't affect main operations

```python
# Example with error handling
try:
    episode = await memory.save_episode(...)
except Exception as e:
    logger.error(f"Failed to save episode: {e}")
    # Episode is still saved to SQLite fallback
```

## Migration from MemoryArchitecture

The Redis adapter is a drop-in replacement for `MemoryArchitecture`:

```python
# Before (using SQLite only)
from memory_architecture import MemoryArchitecture
memory = MemoryArchitecture()

# After (using Redis with fallback)
from redis_memory_adapter import create_memory_adapter
memory = await create_memory_adapter(backend="redis", agent_id="agent_001")
await memory.initialize()

# All methods work the same:
memory.add_step(...)  # Now async: await memory.add_step(...)
episode = memory.save_episode(...)  # Now async: episode = await memory.save_episode(...)
```

**Note**: All methods in `RedisMemoryAdapter` are async, so add `await` to method calls.

## Testing

### Unit Tests

```bash
# Run tests with Redis available
pytest tests/test_redis_memory_adapter.py

# Run tests without Redis (fallback mode)
REDIS_HOST=invalid pytest tests/test_redis_memory_adapter.py
```

### Manual Testing

```python
# Test basic functionality
python redis_memory_adapter.py

# Test with custom configuration
python -c "
import asyncio
from redis_memory_adapter import create_memory_adapter

async def test():
    memory = await create_memory_adapter(
        backend='redis',
        agent_id='test_agent'
    )

    await memory.add_step('test', 'observation', success=True)
    print('Test passed!')
    await memory.close()

asyncio.run(test())
"
```

## Troubleshooting

### Redis Connection Failed

```
WARNING - Failed to connect to Redis: Connection refused
WARNING - Redis not available - using SQLite fallback only
```

**Solution**:
1. Check if Redis is running: `redis-cli ping`
2. Verify connection settings (host, port, password)
3. Check firewall rules

### Import Error

```
ModuleNotFoundError: No module named 'redis.asyncio'
```

**Solution**: Install Redis library: `pip install redis>=4.5.0`

### Pub/Sub Not Working

```
# Messages not being received by other agents
```

**Solution**:
1. Ensure `enable_pubsub=True` on all agents
2. Verify agents are connected to same Redis instance
3. Check Redis pub/sub: `redis-cli PUBSUB CHANNELS`

### Performance Issues

```
# Slow memory operations
```

**Solution**:
1. Check Redis latency: `redis-cli --latency`
2. Increase connection pool size
3. Enable batch operations
4. Check network latency between agent and Redis

## Best Practices

1. **Use Unique Agent IDs**: Ensure each agent instance has a unique `agent_id`
2. **Enable Pub/Sub for Multi-Agent**: Always enable pub/sub when running multiple agents
3. **Set Appropriate TTLs**: Adjust TTLs based on your memory retention needs
4. **Monitor Redis Memory**: Use `redis-cli info memory` to track usage
5. **Regular Cleanup**: Redis will auto-expire old memories, but monitor disk usage
6. **Connection Pooling**: Don't create too many adapter instances; reuse them
7. **Graceful Shutdown**: Always call `await memory.close()` to cleanup connections

## Advanced Configuration

### Custom TTLs

```python
# Modify TTL constants in redis_memory_adapter.py
WORKING_MEMORY_TTL = 7200  # 2 hours instead of 1
EPISODIC_MEMORY_TTL = 86400 * 60  # 60 days instead of 30
```

### Custom Compression

```python
# Adjust compression threshold
serializer = MemorySerializer(compression_threshold=2048)  # 2KB threshold
```

### Custom Batch Settings

```python
# Modify batch constants in redis_memory_adapter.py
BATCH_SIZE = 200  # Process 200 operations at once
BATCH_TIMEOUT = 0.2  # Wait 200ms before processing
```

## Future Enhancements

Planned features:
- [ ] Redis Cluster support for horizontal scaling
- [ ] Memory replication across Redis instances
- [ ] Advanced eviction policies (LRU, LFU)
- [ ] Metrics and monitoring dashboard
- [ ] GraphQL API for memory queries
- [ ] Vector database integration for embeddings

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review Redis logs: `redis-cli MONITOR`
3. Enable debug logging in the adapter
4. Check SQLite fallback logs

## License

Same as parent project.
