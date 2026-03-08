#!/usr/bin/env python3
"""
Test script for health monitoring functionality.

Usage:
    python test_health_monitoring.py
"""

import asyncio
import time
from health_check import HealthWriter, check_health_cli, is_agent_alive

async def test_health_monitoring():
    """Test health monitoring system."""
    print("=" * 60)
    print("Health Monitoring Test")
    print("=" * 60)

    # Test 1: Create and start health writer
    print("\nTest 1: Creating health writer...")
    health = HealthWriter(interval=5)  # 5 second interval for testing
    health.start()
    print("Health writer started")

    # Test 2: Update activity
    print("\nTest 2: Updating activity...")
    for i in range(5):
        health.update_activity(f"Test iteration {i+1}")
        health.increment_iterations()
        print(f"  Iteration {i+1} - activity updated")
        await asyncio.sleep(2)

    # Test 3: Simulate errors
    print("\nTest 3: Simulating errors...")
    health.increment_errors()
    health.set_status("error")
    print("  Error recorded")
    await asyncio.sleep(2)

    # Reset status
    health.set_status("running")
    await asyncio.sleep(2)

    # Test 4: Check if agent is alive
    print("\nTest 4: Checking if agent is alive...")
    alive = is_agent_alive()
    print(f"  Agent is alive: {alive}")

    # Test 5: Get current status
    print("\nTest 5: Current health status...")
    status = health.get_status()
    print(f"  Status: {status['status']}")
    print(f"  Iterations: {status['iterations_completed']}")
    print(f"  Errors: {status['errors_count']}")
    print(f"  Uptime: {status['uptime_seconds']:.1f}s")

    # Stop health monitoring
    print("\nStopping health monitoring...")
    health.stop()
    print("Health writer stopped")

    # Test 6: Display health CLI
    print("\nTest 6: Health CLI display...")
    print("-" * 60)
    exit_code = check_health_cli()
    print("-" * 60)
    print(f"Exit code: {exit_code}")

    print("\n" + "=" * 60)
    print("Test completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_health_monitoring())
