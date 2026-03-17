"""
Test script for A11yBrowser testing/assertion methods.

Tests all 10 new assertion methods for Playwright MCP parity.
"""

import asyncio
from a11y_browser import A11yBrowser


async def test_assertions():
    """Test all assertion methods."""
    print("Testing A11yBrowser Assertion Methods")
    print("=" * 60)

    async with A11yBrowser(headless=False) as browser:
        # Navigate to a test page
        print("\n1. Navigating to example.com...")
        await browser.navigate("https://example.com")
        await browser.wait(1)

        # Get snapshot
        print("\n2. Getting snapshot...")
        snapshot = await browser.snapshot()
        print(f"   Found {len(snapshot.elements)} elements")

        # Test expect_title
        print("\n3. Testing expect_title...")
        result = await browser.expect_title("Example Domain")
        print(f"   expect_title: {result.success} - {result.data if result.success else result.error}")

        # Test expect_url
        print("\n4. Testing expect_url...")
        result = await browser.expect_url("example.com")
        print(f"   expect_url: {result.success} - {result.data if result.success else result.error}")

        # Find a link element
        links = snapshot.find_by_role("link")
        if links:
            link_ref = links[0].ref
            print(f"\n5. Found link: {links[0]}")

            # Test expect_visible
            print("\n6. Testing expect_visible...")
            result = await browser.expect_visible(link_ref)
            print(f"   expect_visible: {result.success} - {result.error if not result.success else 'OK'}")

            # Test get_text
            print("\n7. Testing get_text...")
            result = await browser.get_text(link_ref)
            if result.success:
                text = result.data.get("text", "")
                print(f"   get_text: {text}")

                # Test expect_text
                print("\n8. Testing expect_text...")
                result = await browser.expect_text(link_ref, "More")
                print(f"   expect_text: {result.success} - {result.data if result.success else result.error}")

            # Test get_inner_html
            print("\n9. Testing get_inner_html...")
            result = await browser.get_inner_html(link_ref)
            if result.success:
                html = result.data.get("html", "")
                print(f"   get_inner_html: {html[:100]}...")

            # Test get_outer_html
            print("\n10. Testing get_outer_html...")
            result = await browser.get_outer_html(link_ref)
            if result.success:
                html = result.data.get("html", "")
                print(f"   get_outer_html: {html[:100]}...")

        # Test count_elements
        print("\n11. Testing count_elements...")
        result = await browser.count_elements(role="link")
        print(f"   count_elements (links): {result.data.get('count')} - {result.success}")

        # Test expect_count
        print("\n12. Testing expect_count...")
        result = await browser.expect_count(count=1, role="link")
        print(f"   expect_count: {result.success} - {result.data if result.success else result.error}")

        # Navigate to Google for input testing
        print("\n13. Navigating to Google for input testing...")
        await browser.navigate("https://google.com")
        await browser.wait(1)

        snapshot = await browser.snapshot()
        search_boxes = snapshot.find_by_role("searchbox") or snapshot.find_by_role("textbox")

        if search_boxes:
            search_ref = search_boxes[0].ref
            print(f"\n14. Found search box: {search_boxes[0]}")

            # Type some text
            print("\n15. Typing test text...")
            await browser.type(search_ref, "test value")
            await browser.wait(0.5)

            # Test get_value
            print("\n16. Testing get_value...")
            result = await browser.get_value(search_ref)
            if result.success:
                value = result.data.get("value", "")
                print(f"   get_value: {value}")

                # Test expect_value
                print("\n17. Testing expect_value...")
                result = await browser.expect_value(search_ref, "test value")
                print(f"   expect_value: {result.success} - {result.data if result.success else result.error}")

            # Clear and hide
            await browser.type(search_ref, "")

        # Test expect_hidden (create a scenario)
        print("\n18. Testing expect_hidden...")
        # Create a fake ref that doesn't exist - should be hidden
        result = await browser.expect_hidden("e9999", timeout=1000)
        print(f"   expect_hidden (non-existent): {result.success} - {result.error if not result.success else 'OK'}")

        print("\n" + "=" * 60)
        print("All assertion tests complete!")

        # Show metrics
        metrics = browser.get_metrics()
        print(f"\nMetrics:")
        print(f"  Actions executed: {metrics['actions_executed']}")
        print(f"  Action failures: {metrics['action_failures']}")
        print(f"  Snapshots taken: {metrics['snapshots_taken']}")


if __name__ == "__main__":
    asyncio.run(test_assertions())
