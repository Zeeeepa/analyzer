"""
Example: Natural Language Triggers for Instant Browser Actions

This demonstrates the natural language trigger system that bypasses LLM
processing for common browser operations. Zero tokens, instant results.

Key Benefits:
- No LLM tokens consumed
- Instant execution (no planning delay)
- Predictable output
- Lower cost for repetitive tasks
"""

import asyncio
from playwright_direct import PlaywrightClient


async def demo_extraction_triggers():
    """Demo: Direct extraction without LLM overhead."""
    print("\n=== EXTRACTION TRIGGERS (No LLM) ===\n")

    client = PlaywrightClient()
    await client.connect()

    # Navigate to a sample page
    await client.navigate("https://example.com")

    # Trigger 1: Extract all links
    print("User: extract all links")
    result = await client.process_natural_language("extract all links")
    if result:
        print(f"Result: Found {result.get('count', 0)} links")
        print(f"Links: {result.get('links', [])[:3]}...")  # First 3
    print()

    # Trigger 2: Extract with filter
    print('User: extract links containing "more"')
    result = await client.process_natural_language('extract links containing "more"')
    if result:
        print(f"Result: Found {result.get('count', 0)} matching links")
    print()

    # Trigger 3: Extract forms
    print("User: find forms")
    result = await client.process_natural_language("find forms")
    if result:
        print(f"Result: Found {result.get('count', 0)} forms")
    print()

    # Trigger 4: Extract tables
    print("User: get table data")
    result = await client.process_natural_language("get table data")
    if result:
        print(f"Result: Found {result.get('count', 0)} tables")
    print()

    # Trigger 5: Extract input fields
    print("User: list fields")
    result = await client.process_natural_language("list fields")
    if result:
        print(f"Result: Found {result.get('count', 0)} input fields")
    print()

    await client.disconnect()


async def demo_debug_triggers():
    """Demo: Debug output with DevTools integration."""
    print("\n=== DEBUG TRIGGERS (DevTools) ===\n")

    client = PlaywrightClient()
    await client.connect()

    # Enable MCP features for network/console capture
    await client.call_tool('playwright_enable_mcp_features', {
        'enable_console': True,
        'enable_network': True
    })

    # Navigate to trigger some network activity
    await client.navigate("https://example.com")

    # Trigger 1: Show console errors
    print("User: show console errors")
    result = await client.process_natural_language("show console errors")
    if result:
        errors = result.get('errors', [])
        print(f"Result: Found {len(errors)} console errors")
        if errors:
            print(f"First error: {errors[0]}")
    print()

    # Trigger 2: Show all console logs
    print("User: console logs")
    result = await client.process_natural_language("console logs")
    if result:
        logs = result.get('logs', [])
        print(f"Result: Found {len(logs)} console messages")
    print()

    # Trigger 3: Show network errors
    print("User: what failed")
    result = await client.process_natural_language("what failed")
    if result:
        failed = result.get('failed_requests', [])
        print(f"Result: Found {len(failed)} failed requests")
    print()

    # Trigger 4: Show API calls
    print("User: api calls")
    result = await client.process_natural_language("api calls")
    if result:
        print(f"Result: API call data returned")
    print()

    await client.disconnect()


async def demo_cdp_trigger():
    """Demo: Connect to existing Chrome browser."""
    print("\n=== CDP TRIGGER (Session Reuse) ===\n")

    # First, user needs to launch Chrome with debugging:
    # chrome --remote-debugging-port=9222

    client = PlaywrightClient()
    await client.connect()

    # Trigger: Use existing Chrome
    print("User: use my chrome")
    result = await client.process_natural_language("use my chrome")

    if result and result.get('success'):
        print("Result: Connected to existing Chrome browser")
        print(f"Current URL: {result.get('url', 'unknown')}")
        print("All logged-in sessions preserved!")
    else:
        print("Result: Failed to connect")
        print("Make sure Chrome is running with: chrome --remote-debugging-port=9222")
    print()

    await client.disconnect()


async def demo_quick_inspect_trigger():
    """Demo: Quick HTML parsing without browser overhead."""
    print("\n=== QUICK INSPECT TRIGGER (No Browser) ===\n")

    client = PlaywrightClient()
    await client.connect()

    # Load a page first
    await client.navigate("https://example.com")

    # Trigger: Quick extract
    print("User: quick extract")
    result = await client.process_natural_language("quick extract")

    if result and result.get('success'):
        print("Result: HTML parsed instantly (no browser overhead)")
        print(f"Links found: {result.get('links_count', 0)}")
        print(f"Forms found: {result.get('forms_count', 0)}")
        print(f"Headings: {result.get('headings', {})}")
    print()

    await client.disconnect()


async def demo_integration_with_llm():
    """Demo: How to integrate triggers with LLM-based planning."""
    print("\n=== INTEGRATION EXAMPLE ===\n")

    client = PlaywrightClient()
    await client.connect()

    await client.navigate("https://example.com")

    # Example prompts
    prompts = [
        "extract all links",  # Has trigger
        "find the login button and click it",  # No trigger - needs LLM
        "get all forms",  # Has trigger
        "navigate to the pricing page",  # No trigger - needs LLM
    ]

    for prompt in prompts:
        print(f"User: {prompt}")

        # Try natural language trigger first
        result = await client.process_natural_language(prompt)

        if result:
            print(f"  -> DIRECT ACTION: Executed instantly without LLM")
            print(f"  -> Success: {result.get('success', False)}")
        else:
            print(f"  -> LLM PLANNING: No trigger matched, using AI")
            # Here you would call your LLM-based planning system
            # result = await llm_based_planning(prompt)
        print()

    await client.disconnect()


async def demo_all_triggers():
    """Run all trigger examples."""
    print("=" * 60)
    print("NATURAL LANGUAGE TRIGGERS - Complete Demo")
    print("=" * 60)

    await demo_extraction_triggers()
    await demo_debug_triggers()
    await demo_cdp_trigger()
    await demo_quick_inspect_trigger()
    await demo_integration_with_llm()

    print("\n" + "=" * 60)
    print("All triggers demonstrated!")
    print("=" * 60)


if __name__ == "__main__":
    # Run individual demos
    print("Choose a demo:")
    print("1. Extraction triggers (links, forms, tables)")
    print("2. Debug triggers (console, network)")
    print("3. CDP trigger (existing Chrome)")
    print("4. Quick inspect trigger")
    print("5. Integration example")
    print("6. All demos")

    choice = input("\nEnter choice (1-6): ").strip()

    if choice == "1":
        asyncio.run(demo_extraction_triggers())
    elif choice == "2":
        asyncio.run(demo_debug_triggers())
    elif choice == "3":
        asyncio.run(demo_cdp_trigger())
    elif choice == "4":
        asyncio.run(demo_quick_inspect_trigger())
    elif choice == "5":
        asyncio.run(demo_integration_with_llm())
    elif choice == "6":
        asyncio.run(demo_all_triggers())
    else:
        print("Running all demos...")
        asyncio.run(demo_all_triggers())
