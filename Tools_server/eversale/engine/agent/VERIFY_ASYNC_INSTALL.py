#!/usr/bin/env python3
"""
Quick verification script for async memory architecture installation.

Run this to verify everything is installed and working correctly.
"""

import sys
import asyncio

def check_dependencies():
    """Check if all dependencies are installed."""
    print("Checking dependencies...")
    print("-" * 60)

    dependencies = {
        "aiosqlite": False,
        "memory_architecture": False,
        "memory_architecture_async": False,
    }

    # Check aiosqlite
    try:
        import aiosqlite
        dependencies["aiosqlite"] = True
        print("✓ aiosqlite is installed")
    except ImportError:
        print("✗ aiosqlite NOT installed - run: pip install aiosqlite")

    # Check memory_architecture
    try:
        from memory_architecture import EpisodicMemory, MemoryType
        dependencies["memory_architecture"] = True
        print("✓ memory_architecture.py is available")
    except ImportError as e:
        print(f"✗ memory_architecture.py NOT found - {e}")

    # Check memory_architecture_async
    try:
        from memory_architecture_async import AsyncEpisodicMemoryStore
        dependencies["memory_architecture_async"] = True
        print("✓ memory_architecture_async.py is available")
    except ImportError as e:
        print(f"✗ memory_architecture_async.py NOT found - {e}")

    print("-" * 60)

    if all(dependencies.values()):
        print("\n✓ All dependencies are installed!\n")
        return True
    else:
        print("\n✗ Some dependencies are missing. Please install them.\n")
        return False


async def test_basic_operations():
    """Test basic async operations."""
    print("\nTesting basic async operations...")
    print("-" * 60)

    try:
        from memory_architecture_async import AsyncEpisodicMemoryStore
        from memory_architecture import EpisodicMemory, MemoryType
        from datetime import datetime
        import hashlib

        # Create store
        print("Creating AsyncEpisodicMemoryStore...")
        store = AsyncEpisodicMemoryStore()
        print("✓ Store created successfully")

        # Create test episode
        print("\nCreating test episode...")
        memory_id = hashlib.sha256(f"test_{datetime.now()}".encode()).hexdigest()[:16]
        episode = EpisodicMemory(
            memory_id=memory_id,
            memory_type=MemoryType.EPISODIC,
            task_prompt="Test task",
            content="Test content",
            compressed_content="Test summary",
            outcome="success",
            success=True,
            duration_seconds=0.1,
            tools_used=["test_tool"],
            created_at=datetime.now().isoformat(),
            last_accessed=datetime.now().isoformat(),
            access_count=0,
            importance=0.7,
            composite_score=0.8,
            task_id="test_task",
            session_id="test_session",
            tags=["test"],
            embedding=[0.1 * i for i in range(10)],
            reflection_ids=[]
        )
        print("✓ Test episode created")

        # Test async add
        print("\nTesting async add operation...")
        await store.add_episode_async(episode)
        print("✓ Episode added successfully (async)")

        # Test async search
        print("\nTesting async search operation...")
        results = await store.search_episodes_async(query="test", limit=5)
        print(f"✓ Search completed successfully (found {len(results)} episodes)")

        # Test sync wrapper
        print("\nTesting sync wrapper (backward compatibility)...")
        sync_results = store.search_episodes(query="test", limit=5)
        print(f"✓ Sync wrapper works (found {len(sync_results)} episodes)")

        # Test parallel reads
        print("\nTesting parallel reads (3 simultaneous)...")
        parallel_results = await asyncio.gather(
            store.search_episodes_async(query="test", limit=2),
            store.search_episodes_async(query="test", limit=2),
            store.search_episodes_async(query="test", limit=2),
        )
        print(f"✓ Parallel reads completed successfully")

        print("-" * 60)
        print("\n✓ All basic operations working correctly!\n")
        return True

    except Exception as e:
        print(f"\n✗ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_all_stores():
    """Test all memory store types."""
    print("\nTesting all memory store types...")
    print("-" * 60)

    try:
        from memory_architecture_async import (
            AsyncEpisodicMemoryStore,
            AsyncSemanticMemoryStore,
            AsyncSkillMemoryStore,
        )

        # Test episodic
        print("Testing AsyncEpisodicMemoryStore...")
        episodic = AsyncEpisodicMemoryStore()
        print("✓ Episodic store initialized")

        # Test semantic
        print("Testing AsyncSemanticMemoryStore...")
        semantic = AsyncSemanticMemoryStore()
        print("✓ Semantic store initialized")

        # Test skills
        print("Testing AsyncSkillMemoryStore...")
        skills = AsyncSkillMemoryStore()
        print("✓ Skill store initialized")

        print("-" * 60)
        print("\n✓ All memory store types working!\n")
        return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main verification function."""
    print("\n" + "=" * 60)
    print("ASYNC MEMORY ARCHITECTURE - INSTALLATION VERIFICATION")
    print("=" * 60 + "\n")

    # Check dependencies
    if not check_dependencies():
        print("\nPlease install missing dependencies and try again.")
        sys.exit(1)

    # Run async tests
    try:
        # Test basic operations
        result1 = asyncio.run(test_basic_operations())

        # Test all stores
        result2 = asyncio.run(test_all_stores())

        # Final summary
        print("=" * 60)
        print("VERIFICATION SUMMARY")
        print("=" * 60)

        if result1 and result2:
            print("\n✓✓✓ ALL TESTS PASSED ✓✓✓")
            print("\nAsync memory architecture is installed and working correctly!")
            print("\nNext steps:")
            print("1. Read ASYNC_QUICK_START.md for quick start guide")
            print("2. Run: python test_async_memory.py")
            print("3. Run: python example_async_integration.py")
            print("4. Read ASYNC_MEMORY_README.md for full documentation")
        else:
            print("\n✗✗✗ SOME TESTS FAILED ✗✗✗")
            print("\nPlease check the errors above and fix them.")

        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n✗ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
