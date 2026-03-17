#!/usr/bin/env python3
"""
Test suite for auto-optimization module.

Tests all features of get_optimized_agent() to ensure proper functionality.
"""

import asyncio
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from agent.auto_optimize import (
        get_optimized_agent,
        OptimizedAgent,
        OptimizationConfig,
        OptimizationStats
    )
    print("Import successful")
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)


async def test_basic_creation():
    """Test basic agent creation."""
    print("\n" + "=" * 60)
    print("Test 1: Basic Agent Creation")
    print("=" * 60)

    try:
        agent = await get_optimized_agent()
        print("Agent created successfully")
        print(f"  Type: {type(agent).__name__}")
        print(f"  Backend: {type(agent.backend).__name__ if hasattr(agent, 'backend') else 'N/A'}")
        return True
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_with_options():
    """Test agent creation with custom options."""
    print("\n" + "=" * 60)
    print("Test 2: Agent Creation with Options")
    print("=" * 60)

    try:
        agent = await get_optimized_agent(
            prefer_cdp=False,
            headless=True,
            capture_errors=True,
            token_budget=5000,
            max_snapshot_elements=50
        )
        print("Agent created with custom options")
        print(f"  Config token_budget: {agent.config.token_budget}")
        print(f"  Config max_snapshot_elements: {agent.config.max_snapshot_elements}")
        print(f"  Config headless: {agent.config.headless}")
        return True
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_optimization_components():
    """Test that optimization components are initialized."""
    print("\n" + "=" * 60)
    print("Test 3: Optimization Components")
    print("=" * 60)

    try:
        agent = await get_optimized_agent()
        print("Checking components:")

        # Check token optimizer
        has_token_optimizer = agent.token_optimizer is not None
        print(f"  Token optimizer: {'Enabled' if has_token_optimizer else 'Disabled'}")

        # Check DevTools
        has_devtools = agent.devtools is not None
        print(f"  DevTools hooks: {'Enabled' if has_devtools else 'Disabled'}")

        # Check stats
        stats = agent.get_optimization_stats()
        print(f"  Stats available: {bool(stats)}")
        print(f"  Backend type: {stats.get('backend', {}).get('type', 'N/A')}")

        return True
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_extraction_methods():
    """Test that extraction methods are available."""
    print("\n" + "=" * 60)
    print("Test 4: Extraction Methods")
    print("=" * 60)

    try:
        agent = await get_optimized_agent()
        print("Checking extraction methods:")

        # Check methods exist
        has_extract_links = hasattr(agent, 'extract_links')
        has_extract_forms = hasattr(agent, 'extract_forms')
        has_extract_clickable = hasattr(agent, 'extract_clickable')

        print(f"  extract_links: {'Available' if has_extract_links else 'Missing'}")
        print(f"  extract_forms: {'Available' if has_extract_forms else 'Missing'}")
        print(f"  extract_clickable: {'Available' if has_extract_clickable else 'Missing'}")

        return has_extract_links and has_extract_forms and has_extract_clickable
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_devtools_methods():
    """Test that DevTools methods are available."""
    print("\n" + "=" * 60)
    print("Test 5: DevTools Methods")
    print("=" * 60)

    try:
        agent = await get_optimized_agent()
        print("Checking DevTools methods:")

        # Check methods exist
        has_get_errors = hasattr(agent, 'get_errors')
        has_get_failed = hasattr(agent, 'get_failed_requests')
        has_get_console = hasattr(agent, 'get_console_errors')
        has_summary = hasattr(agent, 'get_devtools_summary')

        print(f"  get_errors: {'Available' if has_get_errors else 'Missing'}")
        print(f"  get_failed_requests: {'Available' if has_get_failed else 'Missing'}")
        print(f"  get_console_errors: {'Available' if has_get_console else 'Missing'}")
        print(f"  get_devtools_summary: {'Available' if has_summary else 'Missing'}")

        return has_get_errors and has_get_failed and has_get_console and has_summary
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_stats_structure():
    """Test optimization stats structure."""
    print("\n" + "=" * 60)
    print("Test 6: Stats Structure")
    print("=" * 60)

    try:
        agent = await get_optimized_agent()
        stats = agent.get_optimization_stats()

        print("Stats structure:")
        print(f"  backend: {bool(stats.get('backend'))}")
        print(f"  token_optimizer: {bool(stats.get('token_optimizer'))}")
        print(f"  devtools: {bool(stats.get('devtools'))}")
        print(f"  performance: {bool(stats.get('performance'))}")

        # Check required fields
        backend_ok = 'type' in stats.get('backend', {})
        token_ok = 'tokens_saved' in stats.get('token_optimizer', {})
        devtools_ok = 'errors_captured' in stats.get('devtools', {})
        perf_ok = 'snapshots_taken' in stats.get('performance', {})

        print(f"\n  Required fields present: {backend_ok and token_ok and devtools_ok and perf_ok}")

        return backend_ok and token_ok and devtools_ok and perf_ok
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_browser_methods():
    """Test that core browser methods are available."""
    print("\n" + "=" * 60)
    print("Test 7: Core Browser Methods")
    print("=" * 60)

    try:
        agent = await get_optimized_agent()
        print("Checking browser methods:")

        methods = [
            'connect', 'disconnect', 'navigate', 'snapshot',
            'click', 'type', 'scroll', 'run_code',
            'observe', 'screenshot'
        ]

        all_present = True
        for method in methods:
            has_method = hasattr(agent, method)
            print(f"  {method}: {'Available' if has_method else 'Missing'}")
            all_present = all_present and has_method

        return all_present
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_token_utilities():
    """Test token estimation and budget checking."""
    print("\n" + "=" * 60)
    print("Test 8: Token Utilities")
    print("=" * 60)

    try:
        agent = await get_optimized_agent()
        print("Testing token utilities:")

        # Test token estimation
        test_text = "Hello world"
        tokens = agent.estimate_tokens(test_text)
        print(f"  Estimated tokens for '{test_text}': {tokens}")

        # Test budget checking
        context = "Some context text " * 100
        within_budget, token_count, message = agent.check_token_budget(context)
        print(f"  Budget check: {message}")
        print(f"  Within budget: {within_budget}")

        return True
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_stats_reset():
    """Test stats reset functionality."""
    print("\n" + "=" * 60)
    print("Test 9: Stats Reset")
    print("=" * 60)

    try:
        agent = await get_optimized_agent()

        # Get initial stats
        stats_before = agent.get_optimization_stats()
        print(f"Stats before reset: {bool(stats_before)}")

        # Reset
        agent.reset_stats()

        # Get stats after reset
        stats_after = agent.get_optimization_stats()
        print(f"Stats after reset: {bool(stats_after)}")

        # Check that stats were reset (should be zero)
        tokens_saved = stats_after.get('token_optimizer', {}).get('tokens_saved', -1)
        print(f"  Tokens saved after reset: {tokens_saved}")

        return tokens_saved == 0
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "=" * 60)
    print("Auto-Optimization Module Test Suite")
    print("=" * 60)

    tests = [
        ("Basic Creation", test_basic_creation),
        ("Custom Options", test_with_options),
        ("Optimization Components", test_optimization_components),
        ("Extraction Methods", test_extraction_methods),
        ("DevTools Methods", test_devtools_methods),
        ("Stats Structure", test_stats_structure),
        ("Browser Methods", test_browser_methods),
        ("Token Utilities", test_token_utilities),
        ("Stats Reset", test_stats_reset),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\nUnexpected error in {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        symbol = "+" if result else "-"
        print(f"  [{symbol}] {name}: {status}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\nAll tests passed!")
        return 0
    else:
        print(f"\n{total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
