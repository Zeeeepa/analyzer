#!/usr/bin/env python3
"""
Example: Using the Coordinated Recovery System

This example demonstrates how to use the recovery coordinator to handle
errors with automatic routing between the three recovery systems.
"""

import asyncio
from recovery_coordinator import recover_with_coordination, get_recovery_coordinator


# Example 1: Basic recovery with automatic routing
async def example_basic_recovery():
    """Basic error recovery with automatic system selection."""
    print("\n" + "="*70)
    print("EXAMPLE 1: Basic Recovery")
    print("="*70)

    # Simulate an error
    error = Exception("Selector not found: #submit-button")

    # Recover with automatic routing
    result = await recover_with_coordination(
        error=error,
        action="click",
        arguments={"selector": "#submit-button"},
        page=None,  # Would be Playwright page in real usage
        retry_action=None,  # Would be lambda: page.click("#submit-button")
        attempt_number=1
    )

    print(f"\nRecovery Result:")
    print(f"  Recovered: {result.get('recovered')}")
    print(f"  System Used: {result.get('system')}")
    print(f"  Severity Level: {result.get('severity')}")
    print(f"  Duration: {result.get('duration_ms')}ms")
    print(f"  Escalated: {result.get('escalated')}")


# Example 2: Escalation through multiple attempts
async def example_escalation():
    """Demonstrate automatic escalation with retry attempts."""
    print("\n" + "="*70)
    print("EXAMPLE 2: Escalation Through Attempts")
    print("="*70)

    error = Exception("Selector not found: .dynamic-content")

    # Try multiple times - severity escalates with each attempt
    for attempt in range(1, 4):
        print(f"\n--- Attempt {attempt} ---")

        result = await recover_with_coordination(
            error=error,
            action="extract",
            arguments={"selector": ".dynamic-content"},
            page=None,
            retry_action=None,
            attempt_number=attempt  # Severity increases with attempt number
        )

        print(f"Severity Level: {result.get('severity')}")
        print(f"System: {result.get('system')}")
        print(f"Recovered: {result.get('recovered')}")

        if result.get('recovered'):
            break


# Example 3: Different error types routing to different systems
async def example_error_type_routing():
    """Show how different errors route to different systems."""
    print("\n" + "="*70)
    print("EXAMPLE 3: Error Type Routing")
    print("="*70)

    test_errors = [
        ("Network timeout", Exception("Network timeout")),
        ("Stale element", Exception("Stale element reference")),
        ("Selector not found", Exception("Selector not found")),
        ("Page crash", Exception("Target page crashed")),
        ("Authentication", Exception("Session expired, please login")),
        ("Out of memory", Exception("Out of memory")),
    ]

    coordinator = get_recovery_coordinator()

    for name, error in test_errors:
        severity = coordinator.assess_severity(error, {}, attempt_number=1)
        system = "self_healing" if severity.value <= 3 else "cascading" if severity.value <= 7 else "crash"

        print(f"\n{name}:")
        print(f"  Severity: {severity.name} (Level {severity.value})")
        print(f"  Routes to: {system}")


# Example 4: Checking recovery statistics
async def example_statistics():
    """Show how to check recovery statistics."""
    print("\n" + "="*70)
    print("EXAMPLE 4: Recovery Statistics")
    print("="*70)

    coordinator = get_recovery_coordinator()
    stats = coordinator.get_stats()

    print(f"\nRecovery System Statistics:")
    print(f"  Total Errors: {stats['total_errors']}")
    print(f"  Self-Healing: {stats['self_healing_handled']}")
    print(f"  Cascading: {stats['cascading_handled']}")
    print(f"  Crash: {stats['crash_handled']}")
    print(f"  Escalations: {stats['escalations']}")
    print(f"  Duplicates Prevented: {stats['duplicates_prevented']}")
    print(f"  Overall Success Rate: {stats['overall_success_rate']:.1%}")

    print(f"\nSuccess Rate by Level:")
    for level, rate in stats['success_rate_by_level'].items():
        if stats['success_rate_by_level'][level] > 0:
            print(f"  Level {level}: {rate:.1%}")


# Example 5: Real-world scenario with Playwright (commented out)
async def example_real_world():
    """
    Real-world usage with Playwright (for reference).

    Uncomment and adapt this when using with actual Playwright page.
    """
    print("\n" + "="*70)
    print("EXAMPLE 5: Real-World Usage (Reference)")
    print("="*70)

    print("""
# Example with Playwright page:

from playwright.async_api import async_playwright
from recovery_coordinator import recover_with_coordination

async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await browser.new_page()

    await page.goto("https://example.com")

    # Try to click a button
    try:
        await page.click("#submit")
    except Exception as e:
        # Use coordinated recovery
        result = await recover_with_coordination(
            error=e,
            action="click",
            arguments={"selector": "#submit"},
            page=page,
            retry_action=lambda: page.click("#submit"),
            attempt_number=1
        )

        if result["recovered"]:
            print("Successfully recovered and clicked button!")
        else:
            print(f"Recovery failed: {result.get('error')}")

    await browser.close()
    """)


# Example 6: Handling recovery chain
async def example_recovery_chain():
    """Show recovery chain tracking."""
    print("\n" + "="*70)
    print("EXAMPLE 6: Recovery Chain Tracking")
    print("="*70)

    print("""
Recovery chains are automatically logged to:
  memory/recovery_chains.jsonl

Each chain contains:
  - timestamp: When the error occurred
  - error_signature: Unique error identifier
  - error: Original error message
  - attempts: List of all recovery attempts
  - outcome: Final result (success/failure)
  - duration_ms: Total recovery time
  - escalations: Number of system escalations

Example chain:
{
  "timestamp": "2025-12-07T10:30:00",
  "error_signature": "abc123def456",
  "error": "Selector not found: #button",
  "attempts": [
    {
      "error_signature": "abc123def456",
      "system": "self_healing",
      "level": 3,
      "timestamp": 1701950400.0,
      "success": false,
      "duration_ms": 500
    },
    {
      "error_signature": "abc123def456",
      "system": "escalation",
      "level": 1,
      "timestamp": 1701950400.5,
      "success": false,
      "duration_ms": 200
    },
    {
      "error_signature": "abc123def456",
      "system": "cascading",
      "level": 5,
      "timestamp": 1701950400.7,
      "success": true,
      "duration_ms": 1800
    }
  ],
  "outcome": "success",
  "duration_ms": 2500,
  "escalations": 1
}
    """)


async def main():
    """Run all examples."""
    print("\n" + "#"*70)
    print("# COORDINATED RECOVERY SYSTEM - USAGE EXAMPLES")
    print("#"*70)

    await example_basic_recovery()
    await example_escalation()
    await example_error_type_routing()
    await example_statistics()
    await example_real_world()
    await example_recovery_chain()

    print("\n" + "="*70)
    print("Examples complete! Check the integration guide for more details:")
    print("  /mnt/c/ev29/agent/RECOVERY_SYSTEM_INTEGRATION.md")
    print("="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

