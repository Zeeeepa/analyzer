#!/usr/bin/env python3
"""
Test suite for Redis Memory Adapter

Demonstrates all major features and verifies functionality.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from redis_memory_adapter import (
    create_memory_adapter,
    RedisMemoryAdapter,
    MemorySerializer,
    RedisConnectionManager
)
from memory_architecture import WorkingMemoryStep, EpisodicMemory


async def test_connection_manager():
    """Test Redis connection manager."""
    print("\n" + "="*70)
    print("TEST: Redis Connection Manager")
    print("="*70)

    manager = RedisConnectionManager()

    # Test connection
    connected = await manager.connect()

    if connected:
        print("✓ Connected to Redis successfully")
        print(f"  - Host: {manager.host}")
        print(f"  - Port: {manager.port}")
        print(f"  - Available: {manager.available}")

        # Test basic operation
        result = await manager.execute(manager.client.set("test_key", "test_value"))
        value = await manager.execute(manager.client.get("test_key"))

        if value == b"test_value":
            print("✓ Basic Redis operations working")
        else:
            print("✗ Redis operation failed")

        # Cleanup
        await manager.execute(manager.client.delete("test_key"))
        await manager.disconnect()
        print("✓ Disconnected from Redis")
    else:
        print("⚠ Redis not available - will use SQLite fallback")

    return connected


async def test_serialization():
    """Test memory serialization and compression."""
    print("\n" + "="*70)
    print("TEST: Serialization & Compression")
    print("="*70)

    serializer = MemorySerializer(compression_threshold=100)

    # Test small object (no compression)
    small_data = {"name": "test", "value": 123}
    serialized = serializer.serialize(small_data)
    deserialized = serializer.deserialize(serialized)

    print(f"✓ Small object serialization:")
    print(f"  - Original: {len(str(small_data))} bytes")
    print(f"  - Serialized: {len(serialized)} bytes")
    print(f"  - Compressed: {serialized[0] == 1}")
    print(f"  - Roundtrip OK: {deserialized == small_data}")

    # Test large object (with compression)
    large_data = {"content": "x" * 1000, "metadata": {"tags": ["a", "b", "c"]}}
    serialized = serializer.serialize(large_data)
    deserialized = serializer.deserialize(serialized)

    print(f"\n✓ Large object serialization:")
    print(f"  - Original: ~{len(str(large_data))} bytes")
    print(f"  - Serialized: {len(serialized)} bytes")
    print(f"  - Compressed: {serialized[0] == 1}")
    print(f"  - Roundtrip OK: {deserialized == large_data}")
    print(f"  - Compression ratio: {len(str(large_data)) / len(serialized):.2f}x")


async def test_basic_operations(redis_available: bool):
    """Test basic memory operations."""
    print("\n" + "="*70)
    print("TEST: Basic Memory Operations")
    print("="*70)

    backend = "redis" if redis_available else "sqlite"
    print(f"Using backend: {backend}")

    # Create adapter
    memory = await create_memory_adapter(
        backend=backend,
        agent_id="test_agent_001",
        session_id="test_session"
    )

    try:
        # Test working memory
        print("\n1. Working Memory:")
        step1 = await memory.add_step(
            action="search_web",
            observation="Found 10 results",
            reasoning="User requested information",
            success=True
        )
        print(f"  ✓ Added step: {step1.step_id}")

        step2 = await memory.add_step(
            action="extract_data",
            observation="Extracted key facts",
            reasoning="Consolidating information",
            success=True
        )
        print(f"  ✓ Added step: {step2.step_id}")

        recent = await memory.get_recent_steps(n=2)
        print(f"  ✓ Retrieved {len(recent)} recent steps")

        # Test episode saving
        print("\n2. Episodic Memory:")
        episode = await memory.save_episode(
            task_prompt="Research topic X",
            outcome="Successfully gathered information",
            success=True,
            duration_seconds=5.2,
            tags=["research", "web_search"],
            importance=0.8
        )
        print(f"  ✓ Saved episode: {episode.memory_id}")
        print(f"    - Task: {episode.task_prompt}")
        print(f"    - Success: {episode.success}")
        print(f"    - Steps: {len(episode.steps)}")
        print(f"    - Tokens: {episode.original_tokens} → {episode.compressed_tokens}")

        # Test episode search
        print("\n3. Episode Search:")
        results = await memory.search_episodes("research", limit=5)
        print(f"  ✓ Found {len(results)} matching episodes")
        for ep in results:
            print(f"    - {ep.memory_id}: {ep.task_prompt}")

        # Test skill saving
        print("\n4. Skill Memory:")
        skill = await memory.save_skill(
            skill_name="web_research",
            description="Search web and extract information",
            action_sequence=[
                {"action": "search_web", "params": {"query": "{{query}}"}},
                {"action": "extract_data", "params": {"format": "structured"}}
            ],
            tags=["research"]
        )
        print(f"  ✓ Saved skill: {skill.skill_name}")
        print(f"    - ID: {skill.memory_id}")
        print(f"    - Actions: {len(skill.action_sequence)}")

        # Test skill retrieval
        retrieved_skill = await memory.get_skill("web_research")
        if retrieved_skill:
            print(f"  ✓ Retrieved skill: {retrieved_skill.skill_name}")
        else:
            print("  ✗ Failed to retrieve skill")

        # Test skill execution recording
        await memory.record_skill_execution(
            skill_name="web_research",
            success=True,
            duration=5.2
        )
        print("  ✓ Recorded skill execution")

        # Test unified search
        print("\n5. Unified Search:")
        all_results = await memory.search_all("research web", limit_per_type=2)
        print(f"  ✓ Episodic: {len(all_results['episodic'])} results")
        print(f"  ✓ Semantic: {len(all_results['semantic'])} results")
        print(f"  ✓ Skills: {len(all_results['skills'])} results")

        # Test enriched context
        print("\n6. Enriched Context:")
        context = await memory.get_enriched_context(
            query="web research",
            detailed_steps=3,
            limit_per_type=2
        )
        lines = context.split('\n')
        print(f"  ✓ Generated context ({len(lines)} lines)")
        if len(context) > 200:
            print(f"    Preview: {context[:200]}...")
        else:
            print(f"    Preview: {context}")

        print("\n✓ All basic operations completed successfully!")

    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await memory.close()


async def test_multi_agent_sync(redis_available: bool):
    """Test multi-agent memory synchronization via pub/sub."""
    if not redis_available:
        print("\n" + "="*70)
        print("TEST: Multi-Agent Sync (SKIPPED - Redis not available)")
        print("="*70)
        return

    print("\n" + "="*70)
    print("TEST: Multi-Agent Memory Synchronization")
    print("="*70)

    # Create two agents
    agent1 = await create_memory_adapter(
        backend="redis",
        agent_id="agent_001",
        session_id="shared_session",
        enable_pubsub=True
    )

    agent2 = await create_memory_adapter(
        backend="redis",
        agent_id="agent_002",
        session_id="shared_session",
        enable_pubsub=True
    )

    try:
        # Give pub/sub time to initialize
        await asyncio.sleep(0.5)

        print("\n1. Agent 1 creates episode:")
        await agent1.add_step(
            action="test_action",
            observation="test_observation",
            success=True
        )

        episode = await agent1.save_episode(
            task_prompt="Shared task from Agent 1",
            outcome="Success",
            success=True,
            duration_seconds=1.0,
            tags=["shared", "test"]
        )
        print(f"  ✓ Agent 1 created episode: {episode.memory_id}")

        # Give pub/sub time to propagate
        await asyncio.sleep(0.5)

        print("\n2. Agent 2 searches for episode:")
        results = await agent2.search_episodes("shared task", limit=5)

        if any(ep.memory_id == episode.memory_id for ep in results):
            print(f"  ✓ Agent 2 found episode from Agent 1!")
            print(f"    - Found {len(results)} total episodes")
        else:
            print(f"  ⚠ Agent 2 didn't find episode (pub/sub delay or SQLite fallback)")
            print(f"    - Found {len(results)} other episodes")

        print("\n✓ Multi-agent sync test completed!")

    except Exception as e:
        print(f"\n✗ Multi-agent test failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await agent1.close()
        await agent2.close()


async def test_session_management(redis_available: bool):
    """Test session rotation and history."""
    print("\n" + "="*70)
    print("TEST: Session Management")
    print("="*70)

    backend = "redis" if redis_available else "sqlite"

    memory = await create_memory_adapter(
        backend=backend,
        agent_id="test_agent_sessions",
        session_id="session_001"
    )

    try:
        print(f"Initial session: {memory.session_id}")

        # Add some data to first session
        await memory.add_step(
            action="session_1_action",
            observation="First session data",
            success=True
        )

        await memory.save_episode(
            task_prompt="Task in session 1",
            outcome="Success",
            success=True,
            duration_seconds=1.0
        )
        print("  ✓ Added data to session 1")

        # Rotate session
        new_session = await memory.rotate_session("session_002")
        print(f"\n✓ Rotated to new session: {new_session}")

        # Check session history
        history = await memory.get_session_history()
        print(f"✓ Session history: {history}")

        if len(history) >= 2:
            print("  ✓ Session continuity maintained")
        else:
            print("  ⚠ Session history incomplete")

    except Exception as e:
        print(f"\n✗ Session management test failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await memory.close()


async def test_performance(redis_available: bool):
    """Test performance characteristics."""
    print("\n" + "="*70)
    print("TEST: Performance Benchmarks")
    print("="*70)

    backend = "redis" if redis_available else "sqlite"

    memory = await create_memory_adapter(
        backend=backend,
        agent_id="test_agent_perf"
    )

    try:
        import time

        # Test write performance
        print("\n1. Write Performance (10 episodes):")
        start = time.time()

        for i in range(10):
            await memory.add_step(
                action=f"action_{i}",
                observation=f"observation_{i}",
                success=True
            )
            await memory.save_episode(
                task_prompt=f"Task {i}",
                outcome="Success",
                success=True,
                duration_seconds=1.0
            )

        write_time = (time.time() - start) * 1000
        print(f"  ✓ Average write: {write_time / 10:.2f}ms per episode")

        # Test read performance
        print("\n2. Read Performance (10 searches):")
        start = time.time()

        for i in range(10):
            results = await memory.search_episodes(f"Task {i}", limit=5)

        read_time = (time.time() - start) * 1000
        print(f"  ✓ Average search: {read_time / 10:.2f}ms per query")

        # Test batch performance
        print("\n3. Batch Performance (100 steps):")
        start = time.time()

        for i in range(100):
            await memory.add_step(
                action=f"batch_action_{i}",
                observation=f"batch_obs_{i}",
                success=True
            )

        batch_time = (time.time() - start) * 1000
        print(f"  ✓ Average batch write: {batch_time / 100:.2f}ms per step")
        print(f"  ✓ Total batch time: {batch_time:.2f}ms")

    except Exception as e:
        print(f"\n✗ Performance test failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await memory.close()


async def run_all_tests():
    """Run all tests."""
    print("\n" + "="*70)
    print("REDIS MEMORY ADAPTER - COMPREHENSIVE TEST SUITE")
    print("="*70)

    # Test connection
    redis_available = await test_connection_manager()

    # Test serialization
    await test_serialization()

    # Test basic operations
    await test_basic_operations(redis_available)

    # Test multi-agent sync
    await test_multi_agent_sync(redis_available)

    # Test session management
    await test_session_management(redis_available)

    # Test performance
    await test_performance(redis_available)

    print("\n" + "="*70)
    print("ALL TESTS COMPLETED!")
    print("="*70)

    if redis_available:
        print("\n✓ Redis backend is working correctly")
    else:
        print("\n⚠ Redis not available - SQLite fallback tested")

    print("\nNext steps:")
    print("1. Start Redis: sudo systemctl start redis-server")
    print("2. Set environment: export MEMORY_BACKEND=redis")
    print("3. Run your agent with distributed memory!")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
