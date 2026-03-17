# Redis Memory Adapter - Quick Start Guide

Get distributed memory sharing working in 5 minutes!

## Prerequisites

```bash
# Install Redis
sudo apt-get install redis-server  # Ubuntu/Debian
# OR
brew install redis  # macOS
# OR
docker run -d -p 6379:6379 redis:latest  # Docker

# Install Python packages
pip install redis loguru
```

## Verify Redis is Running

```bash
# Check Redis status
redis-cli ping
# Should return: PONG

# Or check service status
sudo systemctl status redis-server
```

## Quick Start - 3 Steps

### Step 1: Set Environment Variable (Optional)

```bash
export MEMORY_BACKEND=redis
```

### Step 2: Update Your Code

**Before (using SQLite):**
```python
from memory_architecture import MemoryArchitecture

memory = MemoryArchitecture()
memory.add_step(action="test", observation="test", success=True)
episode = memory.save_episode(
    task_prompt="Test task",
    outcome="Success",
    success=True,
    duration_seconds=1.0
)
```

**After (using Redis):**
```python
import asyncio
from redis_memory_adapter import create_memory_adapter

async def main():
    # Create adapter (uses Redis by default if MEMORY_BACKEND=redis)
    memory = await create_memory_adapter(agent_id="my_agent")

    # Same interface, just add 'await'
    await memory.add_step(action="test", observation="test", success=True)
    episode = await memory.save_episode(
        task_prompt="Test task",
        outcome="Success",
        success=True,
        duration_seconds=1.0
    )

    print(f"Saved: {episode.memory_id}")

    # Cleanup
    await memory.close()

asyncio.run(main())
```

### Step 3: Run Your Agent

```bash
python your_agent.py
```

That's it! Your agent now has distributed memory.

## Verify It's Working

Run the test suite:

```bash
python test_redis_adapter.py
```

Expected output:
```
✓ Connected to Redis successfully
✓ Basic Redis operations working
✓ All basic operations completed successfully!
```

## Multi-Agent Setup

Run multiple agents sharing memory:

```bash
# Terminal 1
python -c "
import asyncio
from redis_memory_adapter import create_memory_adapter

async def agent1():
    memory = await create_memory_adapter(agent_id='agent_001', enable_pubsub=True)
    await memory.add_step('action', 'obs', success=True)
    episode = await memory.save_episode('Task from Agent 1', 'Success', True, 1.0)
    print(f'Agent 1 saved: {episode.memory_id}')
    await asyncio.sleep(5)  # Keep running
    await memory.close()

asyncio.run(agent1())
"

# Terminal 2
python -c "
import asyncio
from redis_memory_adapter import create_memory_adapter

async def agent2():
    await asyncio.sleep(2)  # Wait for agent 1
    memory = await create_memory_adapter(agent_id='agent_002', enable_pubsub=True)
    results = await memory.search_episodes('Task from Agent 1', limit=5)
    print(f'Agent 2 found {len(results)} episodes from Agent 1')
    await memory.close()

asyncio.run(agent2())
"
```

## Common Issues

### Redis Connection Refused
```
WARNING - Failed to connect to Redis: Connection refused
```
**Fix:** Start Redis: `sudo systemctl start redis-server`

### Module Not Found
```
ModuleNotFoundError: No module named 'redis.asyncio'
```
**Fix:** Install Redis library: `pip install redis>=4.5.0`

### Fallback to SQLite
```
WARNING - Redis not available - using SQLite fallback only
```
This is OK! The adapter works without Redis, just without distributed features.

## Next Steps

1. **Review Examples:** Check `redis_integration_example.py` for detailed usage
2. **Read Full Docs:** See `REDIS_MEMORY_README.md` for all features
3. **Run Tests:** Execute `test_redis_adapter.py` to verify everything works
4. **Configure TTLs:** Adjust memory expiration times in `redis_memory_adapter.py`
5. **Monitor Redis:** Use `redis-cli MONITOR` to watch memory operations

## Configuration Options

```python
memory = await create_memory_adapter(
    backend="redis",              # "redis" or "sqlite"
    agent_id="unique_agent_id",   # Unique identifier per agent
    redis_host="localhost",       # Redis server host
    redis_port=6379,              # Redis server port
    redis_db=0,                   # Redis database number
    redis_password=None,          # Redis password (if needed)
    session_id="my_session",      # Session identifier
    enable_pubsub=True,           # Enable real-time sync
    working_capacity=50           # Working memory size
)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORY_BACKEND` | sqlite | "redis" or "sqlite" |
| `REDIS_HOST` | localhost | Redis server hostname |
| `REDIS_PORT` | 6379 | Redis server port |
| `REDIS_DB` | 0 | Redis database number |
| `REDIS_PASSWORD` | None | Redis password |

## Performance Tips

1. **Use Batch Operations:** Group multiple memory operations together
2. **Enable Pub/Sub:** Only when you need real-time multi-agent sync
3. **Set Appropriate TTLs:** Longer TTLs for important memories
4. **Monitor Redis Memory:** Use `redis-cli info memory`
5. **Connection Pooling:** Reuse adapter instances instead of creating many

## Support

If something doesn't work:
1. Check Redis is running: `redis-cli ping`
2. Check logs for errors
3. Try SQLite fallback: `backend="sqlite"`
4. Run test suite: `python test_redis_adapter.py`

## What's Different from MemoryArchitecture?

| Feature | MemoryArchitecture | RedisMemoryAdapter |
|---------|-------------------|-------------------|
| Storage | Local SQLite only | Redis + SQLite fallback |
| Multi-agent | ❌ No | ✅ Yes |
| Real-time sync | ❌ No | ✅ Yes (pub/sub) |
| Distributed | ❌ No | ✅ Yes |
| Async methods | Some | All |
| Memory expiration | Manual cleanup | Automatic (TTL) |

## That's It!

You now have distributed, multi-agent memory sharing. Enjoy! 🚀
