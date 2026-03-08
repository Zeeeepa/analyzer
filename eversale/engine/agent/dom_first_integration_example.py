"""
Integration example showing how DOMFirstBrowser fits into the CLI agent ecosystem.

This demonstrates:
1. Using DOMFirstBrowser in orchestration workflows
2. Integrating with existing LLM-based decision making
3. Converting between DOMFirstBrowser and existing patterns
4. Error handling and recovery
"""

import asyncio
from typing import Dict, Any, List, Optional
from dom_first_browser import DOMFirstBrowser
from loguru import logger


# === Example 1: Basic LLM-driven workflow ===

async def llm_driven_workflow_example():
    """
    Example: LLM sees snapshot, decides action, agent executes.

    This mirrors the existing brain_enhanced_v2.py pattern but uses
    DOMFirstBrowser's cleaner JSON interface.
    """
    print("\n=== Example 1: LLM-Driven Workflow ===\n")

    async with DOMFirstBrowser(headless=False, slow_mo=300) as browser:
        # Navigate
        await browser.navigate("https://www.google.com")

        # Get snapshot for LLM
        snapshot = await browser.snapshot()

        # Simulate LLM response (in real code, this calls Claude)
        llm_prompt = f"""
You are controlling a browser. Current page:

URL: {snapshot.url}
Title: {snapshot.title}

Interactive elements:
{format_snapshot_for_llm(snapshot)}

Task: Search for "web automation"

What action should I take? Respond in JSON:
{{"action": "type|click", "ref": "e1", "text": "..."}}
"""

        print(f"LLM Prompt:\n{llm_prompt}\n")

        # Simulate LLM deciding to type in search box
        # (In real code: llm_response = await call_llm(llm_prompt))
        llm_decision = {
            "action": "type",
            "ref": find_search_box(snapshot),
            "text": "web automation"
        }

        print(f"LLM Decision: {llm_decision}\n")

        # Execute LLM's decision
        if llm_decision["action"] == "type":
            success = await browser.type(
                llm_decision["ref"],
                llm_decision["text"]
            )
            print(f"Type action: {'✓ Success' if success else '✗ Failed'}")

        # Take new snapshot after action
        new_snapshot = await browser.snapshot()
        print(f"\nNew snapshot: {len(new_snapshot.nodes)} elements")

        # Show metrics
        metrics = browser.get_metrics()
        print(f"\nCache hit rate: {metrics['cache_hit_rate']:.1f}%")


def format_snapshot_for_llm(snapshot) -> str:
    """Format snapshot in concise way for LLM consumption."""
    lines = []
    for node in snapshot.nodes[:20]:  # Limit to first 20 for brevity
        role = node['role']
        name = node['name'][:50]  # Truncate long names
        ref = node['ref']
        disabled = " (disabled)" if node.get('disabled') else ""
        lines.append(f"[{ref}] {role} \"{name}\"{disabled}")

    if len(snapshot.nodes) > 20:
        lines.append(f"... and {len(snapshot.nodes) - 20} more elements")

    return "\n".join(lines)


def find_search_box(snapshot) -> Optional[str]:
    """Find search box ref in snapshot."""
    for node in snapshot.nodes:
        if node['role'] in ['searchbox', 'textbox']:
            if 'search' in node['name'].lower():
                return node['ref']
    return None


# === Example 2: Multi-step task with re-snapshot detection ===

async def multi_step_task_example():
    """
    Example: Complex task with multiple actions.

    Shows how smart re-snapshot reduces overhead.
    """
    print("\n=== Example 2: Multi-Step Task ===\n")

    async with DOMFirstBrowser(headless=False, slow_mo=200) as browser:
        # Step 1: Navigate
        print("Step 1: Navigate to form...")
        await browser.navigate("https://www.google.com/preferences")

        # Step 2: Get initial snapshot
        print("Step 2: Get snapshot...")
        snapshot = await browser.snapshot()
        print(f"  Found {len(snapshot.nodes)} elements")

        # Step 3: Interact with form (snapshot should be cached)
        print("Step 3: Check snapshot again (should be cached)...")
        snapshot2 = await browser.snapshot()

        metrics = browser.get_metrics()
        if metrics['snapshot_cache_hits'] > 0:
            print("  ✓ Cache hit - no DOM changes detected")
        else:
            print("  ✗ Cache miss - DOM changed")

        # Step 4: Modify DOM and snapshot again
        print("Step 4: Click something to trigger DOM change...")

        # Find a button or link
        target_ref = None
        for node in snapshot.nodes:
            if node['role'] in ['button', 'link']:
                target_ref = node['ref']
                break

        if target_ref:
            await browser.click(target_ref)

            print("Step 5: Snapshot after click (should detect change)...")
            snapshot3 = await browser.snapshot()

            # This snapshot should be fresh (not cached)
            print(f"  New snapshot: {len(snapshot3.nodes)} elements")

        # Final metrics
        metrics = browser.get_metrics()
        print(f"\nFinal metrics:")
        print(f"  Snapshots taken: {metrics['snapshots_taken']}")
        print(f"  Cache hits: {metrics['snapshot_cache_hits']}")
        print(f"  DOM mutations: {metrics['dom_mutations_detected']}")


# === Example 3: Data extraction with JavaScript ===

async def data_extraction_example():
    """
    Example: Extract structured data using JavaScript.

    Shows how run_code returns clean JSON data.
    """
    print("\n=== Example 3: Data Extraction ===\n")

    async with DOMFirstBrowser(headless=True) as browser:
        await browser.navigate("https://news.ycombinator.com")

        print("Extracting top stories with JavaScript...\n")

        # Extract data with custom JavaScript
        data = await browser.run_code("""
            return {
                title: document.title,
                stories: Array.from(document.querySelectorAll('.titleline > a'))
                    .slice(0, 5)
                    .map((a, i) => ({
                        rank: i + 1,
                        title: a.textContent,
                        url: a.href,
                        domain: a.href.split('/')[2]
                    })),
                timestamp: new Date().toISOString()
            }
        """)

        if data:
            print(f"Page: {data['title']}")
            print(f"Extracted at: {data['timestamp']}\n")
            print("Top 5 stories:")

            for story in data['stories']:
                print(f"  {story['rank']}. {story['title']}")
                print(f"     ({story['domain']})")
                print()


# === Example 4: Network and console monitoring ===

async def monitoring_example():
    """
    Example: Monitor network and console during interaction.

    Shows how to debug issues with observation.
    """
    print("\n=== Example 4: Network & Console Monitoring ===\n")

    async with DOMFirstBrowser(headless=True) as browser:
        print("Navigating and monitoring activity...\n")

        await browser.navigate("https://example.com")

        # Generate some console output
        await browser.run_code("""
            console.log('Test message 1');
            console.warn('Test warning');
            console.error('Test error');
            console.log('Test message 2');
        """)

        # Wait a bit for messages to be captured
        await asyncio.sleep(0.2)

        # Get observations
        obs = await browser.observe(network=True, console=True)

        print(f"Console Messages ({len(obs.console_messages)}):")
        for msg in obs.console_messages:
            print(f"  [{msg['type']}] {msg['text']}")

        print(f"\nNetwork Requests ({len(obs.network_requests)}):")
        for req in obs.network_requests[:5]:  # Show first 5
            print(f"  {req['method']} {req['url']}")


# === Example 5: Error handling and recovery ===

async def error_handling_example():
    """
    Example: Proper error handling patterns.

    Shows how to handle failures gracefully.
    """
    print("\n=== Example 5: Error Handling ===\n")

    async with DOMFirstBrowser(headless=True) as browser:
        await browser.navigate("https://example.com")

        snapshot = await browser.snapshot()

        # Try to click invalid ref
        print("Attempting invalid click...")
        success = await browser.click("e99999")

        if not success:
            print("  ✓ Correctly handled missing element")

            # Fallback strategy
            print("  Trying fallback: click first button...")

            # Find first button
            for node in snapshot.nodes:
                if node['role'] == 'button':
                    success = await browser.click(node['ref'])
                    if success:
                        print(f"  ✓ Fallback succeeded on {node['ref']}")
                    break

        # Try invalid JavaScript
        print("\nAttempting invalid JavaScript...")
        result = await browser.run_code("invalid.syntax.here()")

        if result is None:
            print("  ✓ Correctly handled JS error")

            # Fallback to safe JavaScript
            print("  Trying safe alternative...")
            result = await browser.run_code("return document.title")
            if result:
                print(f"  ✓ Alternative succeeded: '{result}'")

        # Check metrics
        metrics = browser.get_metrics()
        print(f"\nError tracking:")
        print(f"  Action failures: {metrics['action_failures']}")
        print(f"  Success rate: {metrics['action_success_rate']:.1f}%")


# === Example 6: Integration with existing ActionResult pattern ===

def convert_to_action_result(success: bool, action: str, data: Any = None) -> Dict[str, Any]:
    """
    Convert DOMFirstBrowser's bool returns to ActionResult-style dicts.

    This helps integrate with existing code expecting ActionResult.
    """
    return {
        "success": success,
        "action": action,
        "data": data or {},
        "error": None if success else "Action failed"
    }


async def action_result_integration_example():
    """
    Example: Integrate with existing ActionResult-based code.

    Shows how to bridge between DOMFirstBrowser and existing patterns.
    """
    print("\n=== Example 6: ActionResult Integration ===\n")

    async with DOMFirstBrowser(headless=True) as browser:
        await browser.navigate("https://example.com")

        snapshot = await browser.snapshot()

        # Convert snapshot to ActionResult-style
        snapshot_result = {
            "success": True,
            "action": "snapshot",
            "data": snapshot.to_dict(),
            "error": None
        }

        print(f"Snapshot result: {snapshot_result['success']}")
        print(f"  URL: {snapshot_result['data']['url']}")
        print(f"  Elements: {len(snapshot_result['data']['nodes'])}")

        # Find and click with ActionResult conversion
        target_ref = snapshot.nodes[0]['ref'] if snapshot.nodes else None

        if target_ref:
            success = await browser.click(target_ref)
            click_result = convert_to_action_result(
                success,
                "click",
                {"ref": target_ref}
            )

            print(f"\nClick result: {click_result}")


# === Run all examples ===

async def run_all_examples():
    """Run all integration examples."""
    examples = [
        ("LLM-Driven Workflow", llm_driven_workflow_example),
        ("Multi-Step Task", multi_step_task_example),
        ("Data Extraction", data_extraction_example),
        ("Monitoring", monitoring_example),
        ("Error Handling", error_handling_example),
        ("ActionResult Integration", action_result_integration_example),
    ]

    print("=" * 70)
    print("DOMFirstBrowser Integration Examples")
    print("=" * 70)

    for name, example_func in examples:
        try:
            await example_func()
        except KeyboardInterrupt:
            print(f"\n\nStopped at: {name}")
            break
        except Exception as e:
            print(f"\n✗ Example '{name}' failed: {e}")
            import traceback
            traceback.print_exc()

        print("\n" + "=" * 70)

    print("\nAll examples complete!")


if __name__ == "__main__":
    # Run all examples
    # asyncio.run(run_all_examples())

    # Or run individual example:
    asyncio.run(llm_driven_workflow_example())
    # asyncio.run(multi_step_task_example())
    # asyncio.run(data_extraction_example())
    # asyncio.run(monitoring_example())
    # asyncio.run(error_handling_example())
    # asyncio.run(action_result_integration_example())
