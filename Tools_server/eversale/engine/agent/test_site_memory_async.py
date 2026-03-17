"""
Comprehensive tests for async SiteMemory implementation.

Tests cover:
- Async operations
- Concurrent access
- File locking
- Cache behavior
- Atomic writes
- Backward compatibility
"""

import asyncio
import os
import tempfile
import time
from site_memory import SiteMemory, FileLock, ReadWriteLock


class TestResults:
    """Track test results."""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def record_pass(self, test_name):
        self.passed += 1
        print(f"  ✓ {test_name}")

    def record_fail(self, test_name, error):
        self.failed += 1
        self.errors.append((test_name, error))
        print(f"  ✗ {test_name}: {error}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Test Results: {self.passed}/{total} passed")
        if self.failed > 0:
            print(f"\nFailed tests:")
            for name, error in self.errors:
                print(f"  - {name}: {error}")
        print(f"{'='*60}\n")


async def test_basic_async_operations(results: TestResults):
    """Test basic async CRUD operations."""
    print("\n[Test] Basic Async Operations")

    # Create temporary storage
    temp_dir = tempfile.mkdtemp()
    storage_path = os.path.join(temp_dir, "test_memory.json")

    try:
        memory = SiteMemory(storage_path=storage_path, cache_ttl=0)
        await memory.initialize()

        # Test record visit
        url = "https://example.com"
        await memory.record_visit(url, 5.0)
        profile = await memory.get_profile(url)
        assert profile is not None, "Profile should exist after visit"
        assert profile.visit_count == 1, f"Visit count should be 1, got {profile.visit_count}"
        results.record_pass("record_visit and get_profile")

        # Test cache selector
        await memory.cache_selector(url, "search", "input[name='q']", ["#search"])
        selector = await memory.get_selector(url, "search")
        assert selector is not None, "Selector should exist"
        assert selector.primary == "input[name='q']", f"Wrong selector: {selector.primary}"
        assert "#search" in selector.fallbacks, "Fallback not saved"
        results.record_pass("cache_selector and get_selector")

        # Test record quirk
        await memory.record_quirk(url, "Test quirk", "Test workaround")
        quirks = await memory.get_quirks(url)
        assert len(quirks) == 1, f"Should have 1 quirk, got {len(quirks)}"
        assert quirks[0].description == "Test quirk", "Wrong quirk description"
        results.record_pass("record_quirk and get_quirks")

        # Test quirk occurrence increment
        await memory.record_quirk(url, "Test quirk", "Test workaround")
        quirks = await memory.get_quirks(url)
        assert quirks[0].occurrences == 2, f"Occurrences should be 2, got {quirks[0].occurrences}"
        results.record_pass("quirk occurrence increment")

        # Test cache action pattern
        actions = [{"action": "click", "selector": "#btn"}]
        await memory.cache_action_pattern(url, "login", actions)
        cached = await memory.get_action_pattern(url, "login")
        assert cached == actions, "Action pattern mismatch"
        results.record_pass("cache_action_pattern and get_action_pattern")

        # Test LLM context
        context = await memory.get_context_for_prompt(url)
        assert "example.com" in context, "Domain not in context"
        assert "Test quirk" in context, "Quirk not in context"
        results.record_pass("get_context_for_prompt")

    except AssertionError as e:
        results.record_fail("basic_async_operations", str(e))
    except Exception as e:
        results.record_fail("basic_async_operations", f"Unexpected error: {e}")
    finally:
        # Cleanup
        try:
            os.remove(storage_path)
            os.remove(storage_path + ".lock")
            os.rmdir(temp_dir)
        except:
            pass


async def test_file_locking(results: TestResults):
    """Test file locking mechanism."""
    print("\n[Test] File Locking")

    temp_dir = tempfile.mkdtemp()
    lock_file = os.path.join(temp_dir, "test.lock")

    try:
        # Test exclusive lock
        lock1 = FileLock(lock_file, timeout=1.0)
        await lock1.acquire(exclusive=True)
        results.record_pass("acquire exclusive lock")

        # Try to acquire another exclusive lock (should timeout)
        lock2 = FileLock(lock_file, timeout=0.1)
        try:
            await lock2.acquire(exclusive=True)
            results.record_fail("exclusive lock timeout", "Should have timed out")
        except TimeoutError:
            results.record_pass("exclusive lock blocks another exclusive lock")

        await lock1.release()
        results.record_pass("release exclusive lock")

        # Test shared locks
        lock3 = FileLock(lock_file, timeout=1.0)
        lock4 = FileLock(lock_file, timeout=1.0)

        await lock3.acquire(exclusive=False)
        await lock4.acquire(exclusive=False)
        results.record_pass("multiple shared locks acquired")

        await lock3.release()
        await lock4.release()
        results.record_pass("shared locks released")

    except AssertionError as e:
        results.record_fail("file_locking", str(e))
    except Exception as e:
        results.record_fail("file_locking", f"Unexpected error: {e}")
    finally:
        try:
            os.remove(lock_file)
            os.rmdir(temp_dir)
        except:
            pass


async def test_concurrent_access(results: TestResults):
    """Test concurrent access from multiple agents."""
    print("\n[Test] Concurrent Access")

    temp_dir = tempfile.mkdtemp()
    storage_path = os.path.join(temp_dir, "test_memory.json")

    async def agent_task(agent_id, memory):
        """Simulated agent task."""
        url = f"https://example.com/page{agent_id}"

        # Write operations
        await memory.record_visit(url, float(agent_id))
        await memory.cache_selector(url, "btn", f"#btn-{agent_id}")

        # Read operations
        profile = await memory.get_profile(url)
        selector = await memory.get_selector(url, "btn")

        return profile is not None and selector is not None

    try:
        memory = SiteMemory(storage_path=storage_path, cache_ttl=1.0, lock_timeout=5.0)
        await memory.initialize()

        # Run 5 agents concurrently
        tasks = [agent_task(i, memory) for i in range(5)]
        results_list = await asyncio.gather(*tasks)

        assert all(results_list), "Some agents failed"
        results.record_pass("5 concurrent agents")

        # Verify all data was saved
        for i in range(5):
            url = f"https://example.com/page{i}"
            profile = await memory.get_profile(url)
            assert profile is not None, f"Profile {i} missing"
            assert profile.visit_count == 1, f"Profile {i} visit count wrong"

        results.record_pass("all concurrent data persisted")

    except AssertionError as e:
        results.record_fail("concurrent_access", str(e))
    except Exception as e:
        results.record_fail("concurrent_access", f"Unexpected error: {e}")
    finally:
        try:
            os.remove(storage_path)
            os.remove(storage_path + ".lock")
            os.rmdir(temp_dir)
        except:
            pass


async def test_cache_behavior(results: TestResults):
    """Test cache TTL and invalidation."""
    print("\n[Test] Cache Behavior")

    temp_dir = tempfile.mkdtemp()
    storage_path = os.path.join(temp_dir, "test_memory.json")

    try:
        # Test with short TTL
        memory = SiteMemory(storage_path=storage_path, cache_ttl=0.5)
        await memory.initialize()

        url = "https://example.com"
        await memory.record_visit(url, 1.0)

        # Should be cached
        assert memory._is_cache_valid(), "Cache should be valid"
        results.record_pass("cache valid after write")

        # Wait for cache to expire
        await asyncio.sleep(0.6)
        assert not memory._is_cache_valid(), "Cache should be stale"
        results.record_pass("cache expires after TTL")

        # Test cache disabled (TTL=0)
        memory2 = SiteMemory(storage_path=storage_path, cache_ttl=0)
        await memory2.initialize()
        await asyncio.sleep(1.0)
        assert memory2._is_cache_valid(), "Cache should always be valid with TTL=0"
        results.record_pass("cache disabled with TTL=0")

    except AssertionError as e:
        results.record_fail("cache_behavior", str(e))
    except Exception as e:
        results.record_fail("cache_behavior", f"Unexpected error: {e}")
    finally:
        try:
            os.remove(storage_path)
            os.remove(storage_path + ".lock")
            os.rmdir(temp_dir)
        except:
            pass


async def test_atomic_writes(results: TestResults):
    """Test atomic write behavior."""
    print("\n[Test] Atomic Writes")

    temp_dir = tempfile.mkdtemp()
    storage_path = os.path.join(temp_dir, "test_memory.json")

    try:
        memory = SiteMemory(storage_path=storage_path, cache_ttl=0)
        await memory.initialize()

        # Write data
        url = "https://example.com"
        await memory.record_visit(url, 5.0)

        # File should exist and be valid JSON
        assert os.path.exists(storage_path), "Storage file should exist"

        import json
        with open(storage_path, 'r') as f:
            data = json.load(f)
            assert "example.com" in data, "Data not in file"

        results.record_pass("atomic write creates valid JSON")

        # Write again to ensure rename works
        await memory.record_visit(url, 10.0)

        with open(storage_path, 'r') as f:
            data = json.load(f)
            assert data["example.com"]["visit_count"] == 2, "Update not saved"

        results.record_pass("atomic write updates correctly")

    except AssertionError as e:
        results.record_fail("atomic_writes", str(e))
    except Exception as e:
        results.record_fail("atomic_writes", f"Unexpected error: {e}")
    finally:
        try:
            os.remove(storage_path)
            os.remove(storage_path + ".lock")
            os.rmdir(temp_dir)
        except:
            pass


def test_sync_compatibility(results: TestResults):
    """Test synchronous compatibility methods."""
    print("\n[Test] Sync Compatibility")

    temp_dir = tempfile.mkdtemp()
    storage_path = os.path.join(temp_dir, "test_memory.json")

    try:
        memory = SiteMemory(storage_path=storage_path, cache_ttl=0)

        # Test sync methods
        url = "https://example.com"
        memory.record_visit_sync(url, 5.0)

        profile = memory.get_profile_sync(url)
        assert profile is not None, "Profile should exist"
        assert profile.visit_count == 1, "Visit count wrong"
        results.record_pass("sync record_visit and get_profile")

        memory.cache_selector_sync(url, "search", "input[name='q']")
        selector = memory.get_selector_sync(url, "search")
        assert selector is not None, "Selector should exist"
        results.record_pass("sync cache_selector and get_selector")

        memory.record_quirk_sync(url, "Test", "Workaround")
        quirks = memory.get_quirks_sync(url)
        assert len(quirks) == 1, "Should have 1 quirk"
        results.record_pass("sync record_quirk and get_quirks")

        context = memory.get_context_for_prompt_sync(url)
        assert "example.com" in context, "Context missing domain"
        results.record_pass("sync get_context_for_prompt")

    except AssertionError as e:
        results.record_fail("sync_compatibility", str(e))
    except Exception as e:
        results.record_fail("sync_compatibility", f"Unexpected error: {e}")
    finally:
        try:
            os.remove(storage_path)
            os.remove(storage_path + ".lock")
            os.rmdir(temp_dir)
        except:
            pass


async def run_all_tests():
    """Run all tests."""
    print("="*60)
    print("SiteMemory Async Implementation Tests")
    print("="*60)

    results = TestResults()

    # Async tests
    await test_basic_async_operations(results)
    await test_file_locking(results)
    await test_concurrent_access(results)
    await test_cache_behavior(results)
    await test_atomic_writes(results)

    # Sync test (not async)
    test_sync_compatibility(results)

    # Summary
    results.summary()

    return results.failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
