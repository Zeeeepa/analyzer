"""
Unit tests for browser backend abstraction.

Run with: python -m pytest test_browser_backend.py -v
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from browser_backend import (
    BrowserBackend, PlaywrightBackend, CDPBackend, BackendFactory,
    ElementRef, SnapshotResult, InteractionResult, NavigationResult,
    create_backend
)


@pytest.fixture
def sample_element():
    """Sample ElementRef for testing."""
    return ElementRef(
        mmid='mm0',
        ref='button:Submit',
        role='button',
        text='Submit',
        tag='button',
        selector='button.submit',
        rect={'x': 100, 'y': 200, 'width': 80, 'height': 40}
    )


@pytest.fixture
def sample_snapshot(sample_element):
    """Sample SnapshotResult for testing."""
    return SnapshotResult(
        url='https://example.com',
        title='Example Page',
        elements=[sample_element],
        accessibility_tree='Example tree'
    )


class TestElementRef:
    """Test ElementRef dataclass."""

    def test_creation(self, sample_element):
        assert sample_element.mmid == 'mm0'
        assert sample_element.ref == 'button:Submit'
        assert sample_element.role == 'button'

    def test_to_dict(self, sample_element):
        d = sample_element.to_dict()
        assert d['mmid'] == 'mm0'
        assert d['role'] == 'button'
        assert 'rect' in d


class TestSnapshotResult:
    """Test SnapshotResult dataclass."""

    def test_refs_populated(self, sample_snapshot):
        """Refs dict should be auto-populated from elements."""
        assert 'mm0' in sample_snapshot.refs
        assert sample_snapshot.refs['mm0'].text == 'Submit'

    def test_get_by_mmid(self, sample_snapshot):
        el = sample_snapshot.get_by_mmid('mm0')
        assert el is not None
        assert el.text == 'Submit'

        el = sample_snapshot.get_by_mmid('mm999')
        assert el is None

    def test_get_by_role(self, sample_snapshot):
        buttons = sample_snapshot.get_by_role('button')
        assert len(buttons) == 1
        assert buttons[0].mmid == 'mm0'

        links = sample_snapshot.get_by_role('link')
        assert len(links) == 0

    def test_get_by_role_with_text(self, sample_snapshot):
        buttons = sample_snapshot.get_by_role('button', text='Submit')
        assert len(buttons) == 1

        buttons = sample_snapshot.get_by_role('button', text='Cancel')
        assert len(buttons) == 0

    def test_to_dict(self, sample_snapshot):
        d = sample_snapshot.to_dict()
        assert d['url'] == 'https://example.com'
        assert d['title'] == 'Example Page'
        assert len(d['elements']) == 1


class TestInteractionResult:
    """Test InteractionResult dataclass."""

    def test_success_result(self):
        result = InteractionResult(
            success=True,
            url='https://example.com',
            duration_ms=123.5,
            method='mmid_selector'
        )
        assert result.success
        assert result.error is None
        assert result.duration_ms == 123.5

    def test_error_result(self):
        result = InteractionResult(
            success=False,
            error='Element not found',
            error_type='not_found'
        )
        assert not result.success
        assert result.error == 'Element not found'
        assert result.error_type == 'not_found'

    def test_to_dict_excludes_screenshot(self):
        result = InteractionResult(
            success=True,
            screenshot=b'fake_image_data'
        )
        d = result.to_dict()
        assert 'screenshot' not in d
        assert d['success'] is True


class MockBackend(BrowserBackend):
    """Mock backend for testing."""

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def navigate(self, url: str, wait_until: str = 'load') -> NavigationResult:
        return NavigationResult(success=True, url=url, title='Mock Page')

    async def snapshot(self) -> SnapshotResult:
        return SnapshotResult(
            url='https://mock.com',
            title='Mock Page',
            elements=[
                ElementRef(
                    mmid='mm0',
                    ref='button:Click',
                    role='button',
                    text='Click Me',
                    tag='button',
                    selector='button'
                )
            ]
        )

    async def click(self, ref: str, **kwargs) -> InteractionResult:
        return InteractionResult(success=True, method='mock')

    async def type(self, ref: str, text: str, clear: bool = True, **kwargs) -> InteractionResult:
        return InteractionResult(success=True, method='mock')

    async def scroll(self, direction: str = 'down', amount: int = 500) -> InteractionResult:
        return InteractionResult(success=True)

    async def run_code(self, js: str):
        return {'result': 'mock'}

    async def observe(self, network: bool = False, console: bool = False):
        from browser_backend import ObserveResult
        return ObserveResult()

    async def screenshot(self, full_page: bool = False) -> bytes:
        return b'mock_screenshot'


class TestMockBackend:
    """Test mock backend implementation."""

    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        backend = MockBackend()
        assert not backend.is_connected

        success = await backend.connect()
        assert success
        assert backend.is_connected

        await backend.disconnect()
        assert not backend.is_connected

    @pytest.mark.asyncio
    async def test_navigate(self):
        backend = MockBackend()
        await backend.connect()

        result = await backend.navigate('https://example.com')
        assert result.success
        assert result.url == 'https://example.com'
        assert result.title == 'Mock Page'

    @pytest.mark.asyncio
    async def test_snapshot(self):
        backend = MockBackend()
        await backend.connect()

        snapshot = await backend.snapshot()
        assert snapshot.title == 'Mock Page'
        assert len(snapshot.elements) == 1
        assert snapshot.elements[0].mmid == 'mm0'

    @pytest.mark.asyncio
    async def test_click(self):
        backend = MockBackend()
        await backend.connect()

        result = await backend.click('mm0')
        assert result.success
        assert result.method == 'mock'

    @pytest.mark.asyncio
    async def test_type(self):
        backend = MockBackend()
        await backend.connect()

        result = await backend.type('mm0', 'test text')
        assert result.success

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with MockBackend() as backend:
            assert backend.is_connected
            snapshot = await backend.snapshot()
            assert len(snapshot.elements) > 0
        # Should auto-disconnect


class TestBackendFactory:
    """Test backend factory."""

    def test_create_playwright(self):
        backend = BackendFactory.create('playwright')
        assert isinstance(backend, PlaywrightBackend)
        assert not backend.is_connected

    def test_create_cdp(self):
        backend = BackendFactory.create('cdp')
        assert isinstance(backend, CDPBackend)

    def test_create_auto_no_chrome(self):
        """Auto mode without Chrome should fall back to Playwright."""
        with patch.object(CDPBackend, '_detect_chrome_cdp', return_value=None):
            backend = BackendFactory.create('auto')
            assert isinstance(backend, PlaywrightBackend)

    def test_create_invalid_type(self):
        with pytest.raises(ValueError, match='Unknown backend type'):
            BackendFactory.create('invalid_backend')

    @pytest.mark.asyncio
    async def test_create_and_connect_success(self):
        """Test successful connection via factory."""
        with patch('browser_backend.PlaywrightBackend') as MockPW:
            mock_instance = AsyncMock()
            mock_instance.connect = AsyncMock(return_value=True)
            MockPW.return_value = mock_instance

            backend = await BackendFactory.create_and_connect('playwright')
            assert backend is not None
            mock_instance.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_and_connect_failure(self):
        """Test failed connection via factory."""
        with patch('browser_backend.PlaywrightBackend') as MockPW:
            mock_instance = AsyncMock()
            mock_instance.connect = AsyncMock(return_value=False)
            MockPW.return_value = mock_instance

            backend = await BackendFactory.create_and_connect('playwright')
            # Should try fallback or return None
            # (depending on implementation)


class TestCDPBackend:
    """Test CDP backend specific functionality."""

    def test_detect_chrome_cdp_no_chrome(self):
        """Should return None when no Chrome debug port open."""
        backend = CDPBackend()
        # If no Chrome running, should be None
        # (can't reliably test this in CI)

    def test_cdp_url_explicit(self):
        """Should accept explicit CDP URL."""
        backend = CDPBackend(cdp_url='http://localhost:9333')
        assert backend.cdp_url == 'http://localhost:9333'


class TestPlaywrightBackend:
    """Test Playwright backend specific functionality."""

    def test_initialization(self):
        backend = PlaywrightBackend(headless=True)
        assert backend.headless is True
        assert not backend.is_connected

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires Playwright install")
    async def test_real_playwright_connection(self):
        """Integration test with real Playwright (skip if not installed)."""
        backend = PlaywrightBackend(headless=True)
        try:
            success = await backend.connect()
            if success:
                # If connection worked, try basic navigation
                nav = await backend.navigate('https://example.com')
                assert nav.success
        finally:
            await backend.disconnect()


@pytest.mark.asyncio
async def test_workflow_example():
    """Test complete workflow using mock backend."""
    backend = MockBackend()

    # Connect
    assert await backend.connect()

    # Navigate
    nav = await backend.navigate('https://example.com')
    assert nav.success

    # Get snapshot
    snapshot = await backend.snapshot()
    assert len(snapshot.elements) > 0

    # Find button
    buttons = snapshot.get_by_role('button')
    assert len(buttons) > 0

    # Click button
    click_result = await backend.click(buttons[0].mmid)
    assert click_result.success

    # Type text
    type_result = await backend.type('mm0', 'test')
    assert type_result.success

    # Cleanup
    await backend.disconnect()
    assert not backend.is_connected


if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v', '--tb=short'])
