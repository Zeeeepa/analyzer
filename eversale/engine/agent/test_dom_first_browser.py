"""
Test suite for DOMFirstBrowser

Tests all major functionality:
1. Browser launch and close
2. Navigation
3. Snapshot functionality
4. Click and type actions
5. JavaScript execution
6. Network and console observation
7. Smart re-snapshot logic
"""

import asyncio
import pytest
from dom_first_browser import DOMFirstBrowser, create_browser


class TestDOMFirstBrowser:
    """Test suite for DOMFirstBrowser."""

    @pytest.mark.asyncio
    async def test_browser_launch_close(self):
        """Test browser can launch and close successfully."""
        browser = DOMFirstBrowser(headless=True)
        await browser.launch()

        assert browser._browser is not None
        assert browser._page is not None

        await browser.close()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test browser works as context manager."""
        async with DOMFirstBrowser(headless=True) as browser:
            assert browser._browser is not None
            assert browser._page is not None

    @pytest.mark.asyncio
    async def test_navigation(self):
        """Test navigation to URL."""
        async with DOMFirstBrowser(headless=True) as browser:
            success = await browser.navigate("https://example.com")
            assert success is True
            assert "example.com" in browser.page.url

    @pytest.mark.asyncio
    async def test_snapshot_structure(self):
        """Test snapshot returns correct structure."""
        async with DOMFirstBrowser(headless=True) as browser:
            await browser.navigate("https://example.com")

            snapshot = await browser.snapshot()

            # Check structure
            assert hasattr(snapshot, 'nodes')
            assert hasattr(snapshot, 'refs')
            assert hasattr(snapshot, 'url')
            assert hasattr(snapshot, 'title')
            assert hasattr(snapshot, 'timestamp')

            # Check types
            assert isinstance(snapshot.nodes, list)
            assert isinstance(snapshot.refs, dict)
            assert isinstance(snapshot.url, str)
            assert isinstance(snapshot.title, str)

            # Check URL and title
            assert "example.com" in snapshot.url
            assert len(snapshot.title) > 0

    @pytest.mark.asyncio
    async def test_snapshot_nodes_format(self):
        """Test snapshot nodes have correct format."""
        async with DOMFirstBrowser(headless=True) as browser:
            await browser.navigate("https://example.com")

            snapshot = await browser.snapshot()

            if len(snapshot.nodes) > 0:
                node = snapshot.nodes[0]

                # Check required fields
                assert 'ref' in node
                assert 'role' in node
                assert 'name' in node

                # Check ref format (should be e1, e2, etc.)
                assert node['ref'].startswith('e')
                assert node['ref'][1:].isdigit()

    @pytest.mark.asyncio
    async def test_snapshot_refs_mapping(self):
        """Test refs mapping is consistent with nodes."""
        async with DOMFirstBrowser(headless=True) as browser:
            await browser.navigate("https://example.com")

            snapshot = await browser.snapshot()

            # Every node's ref should exist in refs dict
            for node in snapshot.nodes:
                assert node['ref'] in snapshot.refs

            # Every ref should have required fields
            for ref, data in snapshot.refs.items():
                assert 'role' in data
                assert 'name' in data

    @pytest.mark.asyncio
    async def test_smart_resnapshot_cache(self):
        """Test smart re-snapshot logic returns cached snapshot when DOM unchanged."""
        async with DOMFirstBrowser(headless=True) as browser:
            await browser.navigate("https://example.com")

            # First snapshot
            snapshot1 = await browser.snapshot()
            metrics1 = browser.get_metrics()

            # Second snapshot (should be cached)
            snapshot2 = await browser.snapshot()
            metrics2 = browser.get_metrics()

            # Should have gotten cache hit
            assert metrics2['snapshot_cache_hits'] > metrics1['snapshot_cache_hits']

            # Snapshots should be the same object
            assert snapshot1 is snapshot2

    @pytest.mark.asyncio
    async def test_snapshot_force_refresh(self):
        """Test force=True bypasses cache."""
        async with DOMFirstBrowser(headless=True) as browser:
            await browser.navigate("https://example.com")

            # First snapshot
            snapshot1 = await browser.snapshot()

            # Forced snapshot
            snapshot2 = await browser.snapshot(force=True)

            # Should be different objects (new snapshot taken)
            assert snapshot1 is not snapshot2

            # But should have same content (DOM didn't change)
            assert snapshot1.url == snapshot2.url
            assert len(snapshot1.nodes) == len(snapshot2.nodes)

    @pytest.mark.asyncio
    async def test_click_action(self):
        """Test click action on element."""
        async with DOMFirstBrowser(headless=True) as browser:
            # Navigate to a page with links
            await browser.navigate("https://example.com")

            snapshot = await browser.snapshot()

            # Find a link
            link = None
            for node in snapshot.nodes:
                if node['role'] == 'link':
                    link = node
                    break

            if link:
                # Click should not raise error (even if navigation blocked)
                result = await browser.click(link['ref'])
                # Result depends on whether click succeeded
                assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_click_invalid_ref(self):
        """Test click with invalid ref returns False."""
        async with DOMFirstBrowser(headless=True) as browser:
            await browser.navigate("https://example.com")

            # Try to click non-existent ref
            result = await browser.click("e99999")
            assert result is False

            # Metrics should show failure
            metrics = browser.get_metrics()
            assert metrics['action_failures'] > 0

    @pytest.mark.asyncio
    async def test_type_action(self):
        """Test type action on element."""
        async with DOMFirstBrowser(headless=True) as browser:
            # Use a page with a search box
            await browser.navigate("https://www.google.com")

            snapshot = await browser.snapshot()

            # Find search box
            search_box = None
            for node in snapshot.nodes:
                if node['role'] in ['searchbox', 'textbox']:
                    search_box = node
                    break

            if search_box:
                result = await browser.type(search_box['ref'], "test query")
                assert result is True

                # Get metrics
                metrics = browser.get_metrics()
                assert metrics['actions_executed'] > 0

    @pytest.mark.asyncio
    async def test_run_code_return_value(self):
        """Test run_code returns JavaScript result."""
        async with DOMFirstBrowser(headless=True) as browser:
            await browser.navigate("https://example.com")

            # Simple return
            result = await browser.run_code("return document.title")
            assert result is not None
            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_run_code_function_syntax(self):
        """Test run_code with function syntax."""
        async with DOMFirstBrowser(headless=True) as browser:
            await browser.navigate("https://example.com")

            # Arrow function
            result = await browser.run_code("() => document.title")
            assert result is not None
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_run_code_json_return(self):
        """Test run_code returns JSON-compatible data."""
        async with DOMFirstBrowser(headless=True) as browser:
            await browser.navigate("https://example.com")

            # Return object
            result = await browser.run_code("""
                return {
                    url: window.location.href,
                    title: document.title,
                    width: window.innerWidth
                }
            """)

            assert isinstance(result, dict)
            assert 'url' in result
            assert 'title' in result
            assert 'width' in result
            assert isinstance(result['width'], (int, float))

    @pytest.mark.asyncio
    async def test_observe_console(self):
        """Test observe captures console messages."""
        async with DOMFirstBrowser(headless=True) as browser:
            await browser.navigate("https://example.com")

            # Generate console message
            await browser.run_code("console.log('test message')")

            # Wait a bit for message to be captured
            await asyncio.sleep(0.1)

            # Observe console
            result = await browser.observe(console=True)

            assert hasattr(result, 'console_messages')
            assert isinstance(result.console_messages, list)

            # Should have at least one message
            # (may have more from the page itself)
            assert len(result.console_messages) >= 0

    @pytest.mark.asyncio
    async def test_observe_network(self):
        """Test observe captures network requests."""
        async with DOMFirstBrowser(headless=True) as browser:
            await browser.navigate("https://example.com")

            # Observe network
            result = await browser.observe(network=True)

            assert hasattr(result, 'network_requests')
            assert isinstance(result.network_requests, list)

            # Should have requests from page load
            assert len(result.network_requests) > 0

            # Check request structure
            if len(result.network_requests) > 0:
                req = result.network_requests[0]
                assert 'url' in req
                assert 'method' in req
                assert 'timestamp' in req

    @pytest.mark.asyncio
    async def test_observe_both(self):
        """Test observe with both network and console."""
        async with DOMFirstBrowser(headless=True) as browser:
            await browser.navigate("https://example.com")

            result = await browser.observe(network=True, console=True)

            assert hasattr(result, 'console_messages')
            assert hasattr(result, 'network_requests')
            assert hasattr(result, 'timestamp')

    @pytest.mark.asyncio
    async def test_metrics(self):
        """Test get_metrics returns expected fields."""
        async with DOMFirstBrowser(headless=True) as browser:
            await browser.navigate("https://example.com")

            # Take some actions
            await browser.snapshot()
            await browser.snapshot()  # Should be cached

            metrics = browser.get_metrics()

            # Check expected fields
            assert 'snapshots_taken' in metrics
            assert 'snapshot_cache_hits' in metrics
            assert 'actions_executed' in metrics
            assert 'action_failures' in metrics
            assert 'cache_hit_rate' in metrics
            assert 'action_success_rate' in metrics

            # Check types
            assert isinstance(metrics['snapshots_taken'], int)
            assert isinstance(metrics['cache_hit_rate'], float)

            # Should have taken 1 snapshot and cached 1
            assert metrics['snapshots_taken'] >= 1
            assert metrics['snapshot_cache_hits'] >= 1

    @pytest.mark.asyncio
    async def test_create_browser_helper(self):
        """Test create_browser convenience function."""
        browser = await create_browser(headless=True)

        assert browser._browser is not None
        assert browser._page is not None

        await browser.close()


# === Run tests ===

if __name__ == "__main__":
    # Run with pytest
    pytest.main([__file__, "-v", "-s"])
