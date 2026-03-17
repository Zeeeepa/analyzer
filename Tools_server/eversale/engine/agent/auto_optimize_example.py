#!/usr/bin/env python3
"""
Auto-Optimization Example - Demonstrates fully optimized browser agent usage.

This example shows how to use get_optimized_agent() for common tasks
with all optimizations automatically enabled.
"""

import asyncio
import json
from pathlib import Path

# Import auto-optimization module
try:
    from auto_optimize import get_optimized_agent
except ImportError:
    from agent.auto_optimize import get_optimized_agent


async def example_1_basic_usage():
    """Example 1: Basic usage with auto-optimization."""
    print("\n" + "=" * 60)
    print("Example 1: Basic Usage")
    print("=" * 60 + "\n")

    # One line to get fully optimized agent
    agent = await get_optimized_agent()

    try:
        # Connect
        connected = await agent.connect()
        print(f"Connected: {connected}")

        if connected:
            # Navigate
            print("\nNavigating to example.com...")
            await agent.navigate("https://example.com")

            # Get snapshot (automatically compressed and cached)
            print("Getting page snapshot...")
            snapshot1 = await agent.snapshot()
            print(f"  Snapshot 1: {len(snapshot1.elements) if hasattr(snapshot1, 'elements') else 'N/A'} elements")

            # Second snapshot uses cache (if still valid)
            snapshot2 = await agent.snapshot()
            print(f"  Snapshot 2: Cached")

            # Get optimization stats
            stats = agent.get_optimization_stats()
            print(f"\nOptimization Stats:")
            print(f"  Backend: {stats['backend']['type']}")
            print(f"  Cache hits: {stats['token_optimizer']['cache_hits']}")
            print(f"  Tokens saved: {stats['token_optimizer']['tokens_saved']}")

    finally:
        await agent.disconnect()


async def example_2_extraction_shortcuts():
    """Example 2: Using extraction shortcuts."""
    print("\n" + "=" * 60)
    print("Example 2: Extraction Shortcuts")
    print("=" * 60 + "\n")

    agent = await get_optimized_agent(headless=False)

    try:
        connected = await agent.connect()
        if not connected:
            print("Failed to connect")
            return

        # Navigate to a real site
        print("Navigating to GitHub...")
        await agent.navigate("https://github.com")

        # Extract links with filtering
        print("\nExtracting signup links...")
        signup_links = await agent.extract_links(
            contains_text='sign up',
            limit=5
        )
        print(f"Found {len(signup_links)} signup links:")
        for link in signup_links[:3]:
            print(f"  - {link.get('text', 'N/A')}: {link.get('href', 'N/A')}")

        # Extract all forms
        print("\nExtracting forms...")
        forms = await agent.extract_forms()
        print(f"Found {len(forms)} forms")

        # Extract buttons
        print("\nExtracting buttons...")
        buttons = await agent.extract_clickable(role='button', limit=10)
        print(f"Found {len(buttons)} buttons")

    finally:
        await agent.disconnect()


async def example_3_error_monitoring():
    """Example 3: Error monitoring with DevTools."""
    print("\n" + "=" * 60)
    print("Example 3: Error Monitoring")
    print("=" * 60 + "\n")

    # Enable error capture
    agent = await get_optimized_agent(
        capture_errors=True,
        headless=False
    )

    try:
        connected = await agent.connect()
        if not connected:
            print("Failed to connect")
            return

        # Navigate to a site (might have errors)
        print("Navigating to example site...")
        await agent.navigate("https://example.com")

        # Wait for page to load and capture errors
        await asyncio.sleep(2)

        # Get captured errors
        errors = await agent.get_errors()
        print(f"\nPage errors: {len(errors)}")
        if errors:
            for error in errors[:3]:
                print(f"  - {error.get('message', 'Unknown error')}")

        # Get failed network requests
        failed_requests = await agent.get_failed_requests()
        print(f"\nFailed requests: {len(failed_requests)}")
        if failed_requests:
            for req in failed_requests[:3]:
                print(f"  - {req.get('url', 'N/A')}: {req.get('failure_reason', 'N/A')}")

        # Get console errors
        console_errors = await agent.get_console_errors()
        print(f"\nConsole errors: {len(console_errors)}")

        # Get full DevTools summary
        summary = agent.get_devtools_summary()
        print(f"\nDevTools Summary:")
        print(f"  Total network requests: {summary.get('network', {}).get('total_requests', 0)}")
        print(f"  Failed requests: {summary.get('network', {}).get('failed_requests', 0)}")
        print(f"  Console errors: {summary.get('console', {}).get('errors', 0)}")

    finally:
        await agent.disconnect()


async def example_4_token_optimization():
    """Example 4: Token optimization and budget tracking."""
    print("\n" + "=" * 60)
    print("Example 4: Token Optimization")
    print("=" * 60 + "\n")

    agent = await get_optimized_agent(
        token_budget=5000,  # Smaller budget for demo
        max_snapshot_elements=50
    )

    try:
        connected = await agent.connect()
        if not connected:
            print("Failed to connect")
            return

        print("Navigating to complex page...")
        await agent.navigate("https://github.com/explore")

        # Get snapshot (automatically compressed)
        print("\nGetting snapshot...")
        snapshot = await agent.snapshot()

        # Check token budget
        context = json.dumps(snapshot.to_dict() if hasattr(snapshot, 'to_dict') else {})
        within_budget, tokens, message = agent.check_token_budget(context)
        print(f"\nToken Budget Check:")
        print(f"  {message}")
        print(f"  Within budget: {within_budget}")

        # Estimate tokens for different content
        test_texts = [
            "Short text",
            "Medium length text " * 50,
            "Very long text " * 200,
        ]

        print(f"\nToken Estimation:")
        for text in test_texts:
            tokens = agent.estimate_tokens(text)
            print(f"  {len(text)} chars -> ~{tokens} tokens")

        # Get compression stats
        stats = agent.get_optimization_stats()
        print(f"\nCompression Stats:")
        print(f"  Tokens saved: {stats['token_optimizer']['tokens_saved']}")
        print(f"  Cache hit rate: {stats['token_optimizer']['cache_hit_rate']}")
        print(f"  Auto-compressions: {stats['token_optimizer']['auto_compressions']}")

    finally:
        await agent.disconnect()


async def example_5_comprehensive_workflow():
    """Example 5: Comprehensive workflow with all features."""
    print("\n" + "=" * 60)
    print("Example 5: Comprehensive Workflow")
    print("=" * 60 + "\n")

    # Create agent with all optimizations
    agent = await get_optimized_agent(
        prefer_cdp=True,           # Try CDP first
        headless=False,            # Show browser
        capture_errors=True,       # Enable DevTools
        token_budget=10000,        # 10K token budget
        max_snapshot_elements=100  # Up to 100 elements
    )

    try:
        # Connect
        print("Connecting to browser...")
        connected = await agent.connect()
        if not connected:
            print("Failed to connect")
            return

        connection_stats = agent.get_optimization_stats()
        print(f"  Backend: {connection_stats['backend']['type']}")
        print(f"  Connection time: {connection_stats['backend']['connection_time_ms']:.1f}ms")

        # Navigate
        print("\nNavigating to GitHub...")
        nav_result = await agent.navigate("https://github.com")

        # Wait for page to load
        await asyncio.sleep(2)

        # Get snapshot with optimization
        print("\nGetting optimized snapshot...")
        start = asyncio.get_event_loop().time()
        snapshot = await agent.snapshot()
        duration = (asyncio.get_event_loop().time() - start) * 1000
        print(f"  Snapshot time: {duration:.1f}ms")

        # Check for errors
        print("\nChecking for errors...")
        errors = await agent.get_errors()
        failed_requests = await agent.get_failed_requests()
        console_errors = await agent.get_console_errors()

        print(f"  Page errors: {len(errors)}")
        print(f"  Failed requests: {len(failed_requests)}")
        print(f"  Console errors: {len(console_errors)}")

        # Extract data
        print("\nExtracting data...")

        # Links
        links = await agent.extract_links(limit=10)
        print(f"  Links: {len(links)}")

        # Forms
        forms = await agent.extract_forms()
        print(f"  Forms: {len(forms)}")

        # Buttons
        buttons = await agent.extract_clickable(role='button', limit=10)
        print(f"  Buttons: {len(buttons)}")

        # Get comprehensive stats
        print("\n" + "-" * 60)
        print("Final Optimization Statistics")
        print("-" * 60)

        stats = agent.get_optimization_stats()
        print(f"\nBackend:")
        print(f"  Type: {stats['backend']['type']}")
        print(f"  Connected: {stats['backend']['connected']}")
        print(f"  Connection time: {stats['backend']['connection_time_ms']:.1f}ms")

        print(f"\nToken Optimizer:")
        print(f"  Tokens saved: {stats['token_optimizer']['tokens_saved']}")
        print(f"  Cache hits: {stats['token_optimizer']['cache_hits']}")
        print(f"  Cache misses: {stats['token_optimizer']['cache_misses']}")
        print(f"  Cache hit rate: {stats['token_optimizer']['cache_hit_rate']}")
        print(f"  Auto-compressions: {stats['token_optimizer']['auto_compressions']}")

        print(f"\nDevTools:")
        print(f"  Errors captured: {stats['devtools']['errors_captured']}")
        print(f"  Failed requests: {stats['devtools']['failed_requests']}")
        print(f"  Console errors: {stats['devtools']['console_errors']}")

        print(f"\nPerformance:")
        print(f"  Snapshots taken: {stats['performance']['snapshots_taken']}")
        print(f"  Snapshots cached: {stats['performance']['snapshots_cached']}")
        print(f"  Avg snapshot time: {stats['performance']['avg_snapshot_time_ms']:.1f}ms")

        # Save stats to file
        output_path = Path("logs/optimization_stats.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(stats, f, indent=2)
        print(f"\nStats saved to: {output_path}")

    finally:
        await agent.disconnect()
        print("\nDisconnected.")


async def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("Auto-Optimization Examples")
    print("=" * 60)

    examples = [
        ("Basic Usage", example_1_basic_usage),
        ("Extraction Shortcuts", example_2_extraction_shortcuts),
        ("Error Monitoring", example_3_error_monitoring),
        ("Token Optimization", example_4_token_optimization),
        ("Comprehensive Workflow", example_5_comprehensive_workflow),
    ]

    print("\nAvailable Examples:")
    for i, (name, func) in enumerate(examples, 1):
        print(f"  {i}. {name}")

    print("\nRunning all examples...")

    for name, func in examples:
        try:
            await func()
        except Exception as e:
            print(f"\nError in {name}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("Examples Complete")
    print("=" * 60 + "\n")


if __name__ == '__main__':
    # Run examples
    asyncio.run(main())
