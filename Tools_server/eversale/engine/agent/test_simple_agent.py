"""
Test Simple Agent

Basic tests to verify the simple agent works correctly.
"""

import asyncio
try:
    from simple_agent import SimpleAgent, run_task
    from a11y_browser import A11yBrowser
except ImportError:
    from .simple_agent import SimpleAgent, run_task
    from .a11y_browser import A11yBrowser


async def test_browser_basic():
    """Test basic browser operations."""
    print("\n=== Test 1: Basic Browser Operations ===")

    browser = A11yBrowser(headless=False)

    # Launch
    result = await browser.launch()
    assert result.success, f"Launch failed: {result.error}"
    print("✓ Browser launched")

    # Navigate
    result = await browser.navigate("https://example.com")
    assert result.success, f"Navigate failed: {result.error}"
    print("✓ Navigated to example.com")

    # Snapshot
    await asyncio.sleep(1)
    snapshot = await browser.snapshot()
    assert snapshot.url == "https://example.com/", "Wrong URL"
    assert "Example Domain" in snapshot.title, "Wrong title"
    print(f"✓ Snapshot: {len(snapshot.elements)} elements found")

    # Close
    await browser.close()
    print("✓ Browser closed")


async def test_snapshot_parsing():
    """Test snapshot parsing and element finding."""
    print("\n=== Test 2: Snapshot Parsing ===")

    browser = A11yBrowser(headless=False)
    await browser.launch()
    await browser.navigate("https://google.com")
    await asyncio.sleep(2)

    snapshot = await browser.snapshot()
    print(f"✓ Page: {snapshot.title}")
    print(f"✓ Elements: {len(snapshot.elements)}")

    # Find by role
    search_boxes = snapshot.find_by_role("searchbox")
    print(f"✓ Search boxes: {len(search_boxes)}")
    if search_boxes:
        print(f"  - {search_boxes[0]}")

    buttons = snapshot.find_by_role("button")
    print(f"✓ Buttons: {len(buttons)}")

    links = snapshot.find_by_role("link")
    print(f"✓ Links: {len(links)}")

    await browser.close()


async def test_agent_fallback():
    """Test agent with fallback logic (no LLM)."""
    print("\n=== Test 3: Agent Fallback Mode ===")

    agent = SimpleAgent(llm_client=None, headless=False)
    result = await agent.run("Search Google for Python tutorials")

    print(f"✓ Success: {result.success}")
    print(f"✓ Steps: {result.steps_taken}")
    print(f"✓ Final URL: {result.final_url}")
    if result.data:
        print(f"✓ Summary: {result.data.get('summary')}")
    if result.error:
        print(f"✗ Error: {result.error}")


async def test_agent_actions():
    """Test individual agent actions."""
    print("\n=== Test 4: Agent Actions ===")

    browser = A11yBrowser(headless=False)
    await browser.launch()

    # Navigate
    result = await browser.navigate("https://google.com")
    assert result.success, "Navigate failed"
    print("✓ Navigate")

    await asyncio.sleep(2)
    snapshot = await browser.snapshot()

    # Type
    search_boxes = snapshot.find_by_role("searchbox")
    if search_boxes:
        result = await browser.type(search_boxes[0].ref, "test query")
        assert result.success, "Type failed"
        print("✓ Type")

        # Press
        result = await browser.press("Escape")  # Don't submit
        assert result.success, "Press failed"
        print("✓ Press key")

    # Scroll
    result = await browser.scroll("down")
    assert result.success, "Scroll failed"
    print("✓ Scroll")

    # Wait
    result = await browser.wait(1)
    assert result.success, "Wait failed"
    print("✓ Wait")

    # Screenshot
    result = await browser.screenshot("test_screenshot.png")
    assert result.success, "Screenshot failed"
    print("✓ Screenshot")

    await browser.close()


async def main():
    """Run all tests."""
    print("Simple Agent Test Suite")
    print("=" * 50)

    try:
        await test_browser_basic()
        await test_snapshot_parsing()
        await test_agent_fallback()
        await test_agent_actions()

        print("\n" + "=" * 50)
        print("All tests passed!")

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
