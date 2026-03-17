#!/usr/bin/env python3
"""
Quick test for Kimi K2 integration.

Run with: python -m agent.test_kimi_integration
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from agent.kimi_k2_client import KimiK2Client, should_use_kimi_planning


async def test_kimi_client():
    """Test Kimi K2 client connection and planning."""
    print("=" * 60)
    print("Testing Kimi K2 Integration")
    print("=" * 60)

    # Check API key
    api_key = os.getenv("MOONSHOT_API_KEY")
    if not api_key:
        print("❌ MOONSHOT_API_KEY not set in environment")
        return False

    print(f"✓ API key found: {api_key[:10]}...{api_key[-4:]}")

    # Initialize client
    client = KimiK2Client(api_key=api_key)

    if not client.is_available():
        print("❌ Kimi K2 client not available (budget or API issue)")
        return False

    print("✓ Kimi K2 client initialized")

    # Test planning
    test_prompt = "Find leads from Facebook Ads Library for 'CRM software' and extract their websites"
    available_tools = [
        "playwright_navigate",
        "playwright_click",
        "playwright_fill",
        "playwright_get_markdown",
        "playwright_extract_entities",
        "playwright_screenshot",
    ]

    print(f"\nTest prompt: {test_prompt}")
    print(f"Available tools: {len(available_tools)}")

    # Check if planning would be triggered
    would_plan = should_use_kimi_planning(test_prompt)
    print(f"\nWould trigger planning: {would_plan}")

    # Actually call Kimi K2
    print("\nCalling Kimi K2 for strategic planning...")
    plan = await client.plan_task(test_prompt, available_tools)

    if plan:
        print(f"\n✓ Plan created successfully!")
        print(f"  Summary: {plan.summary}")
        print(f"  Steps: {len(plan.steps)}")
        for step in plan.steps:
            print(f"    {step.step_number}. {step.action}")
            print(f"       Tool: {step.tool}")
        print(f"  Blockers: {plan.potential_blockers}")
        print(f"  Success criteria: {plan.success_criteria}")
    else:
        print("❌ Planning failed")
        return False

    # Check usage (include_costs=True for local dev)
    usage = client.get_usage_report(include_costs=True)
    print(f"\nUsage report (local dev view):")
    print(f"  Calls today: {usage['calls_today']}")
    print(f"  Planning calls: {usage['planning_calls']}")
    if 'today' in usage:  # Cost info only for local dev
        print(f"  [INTERNAL] Cost: ${usage['today']['total_cost_usd']:.4f}")
        print(f"  [INTERNAL] Budget remaining: ${usage['budget_remaining']:.4f}")

    await client.close()
    print("\n✓ All tests passed!")
    return True


async def test_simple_vs_complex():
    """Test that simple tasks skip planning, complex ones trigger it."""
    print("\n" + "=" * 60)
    print("Testing Simple vs Complex Task Detection")
    print("=" * 60)

    test_cases = [
        ("go to google.com", False),
        ("click the submit button", False),
        ("take a screenshot", False),
        ("Find leads from Facebook Ads Library for CRM software", True),
        ("Research competitor pricing on ProductHunt and create a comparison", True),
        ("Extract all email addresses from this page and save to CSV", True),
        ("Monitor Hacker News for AI posts every hour", True),
    ]

    all_passed = True
    for prompt, expected in test_cases:
        result = should_use_kimi_planning(prompt)
        status = "✓" if result == expected else "❌"
        if result != expected:
            all_passed = False
        print(f"{status} '{prompt[:50]}...' -> {result} (expected {expected})")

    return all_passed


if __name__ == "__main__":
    print("Kimi K2 Integration Test\n")

    # Test detection logic first (no API call)
    asyncio.run(test_simple_vs_complex())

    # Test actual API call
    success = asyncio.run(test_kimi_client())

    exit(0 if success else 1)
