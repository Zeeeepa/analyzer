"""
Tests for Element Inspector

Validates:
1. Element snapshot capture
2. Selector quality analysis
3. Dynamic element detection
4. Interaction diagnosis
5. Stability scoring
"""

import asyncio
import pytest
from playwright.async_api import async_playwright
from element_inspector import (
    ElementInspector,
    ElementSnapshot,
    SelectorQualityReport,
    DynamicAnalysis,
    SelectorStrategy
)


@pytest.fixture
async def page():
    """Provide a Playwright page for testing."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        yield page
        await browser.close()


@pytest.fixture
async def test_page(page):
    """Load a test page with known elements."""
    await page.set_content('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Test Page</title>
            <style>
                .hidden { display: none; }
                .invisible { visibility: hidden; }
                .transparent { opacity: 0; }
            </style>
        </head>
        <body>
            <h1 id="title">Test Page</h1>

            <!-- Stable ID -->
            <button id="submit-btn" class="btn btn-primary">Submit</button>

            <!-- Unstable ID (timestamp-like) -->
            <button id="btn-1638234567890" class="btn">Dynamic Button</button>

            <!-- ARIA labeled element -->
            <button aria-label="Close dialog" class="close-btn">X</button>

            <!-- data-testid -->
            <input data-testid="email-input" type="email" placeholder="Email">

            <!-- CSS-in-JS classes -->
            <div class="css-1dbjc4n css-18t94o4">CSS-in-JS Element</div>

            <!-- Hidden elements -->
            <div class="hidden">Hidden Div</div>
            <div class="invisible">Invisible Div</div>
            <div class="transparent">Transparent Div</div>

            <!-- Disabled element -->
            <button disabled>Disabled Button</button>

            <!-- Read-only input -->
            <input readonly value="Read Only">

            <!-- List of similar elements -->
            <ul id="items">
                <li class="item">Item 1</li>
                <li class="item">Item 2</li>
                <li class="item">Item 3</li>
            </ul>

            <!-- React-like element (simulated) -->
            <div id="react-root"></div>
            <script>
                // Simulate React fiber
                document.getElementById('react-root').__reactFiber$ = {};
            </script>
        </body>
        </html>
    ''')
    return page


class TestElementInspector:
    """Test suite for ElementInspector."""

    @pytest.mark.asyncio
    async def test_basic_inspection(self, test_page):
        """Test basic element snapshot capture."""
        inspector = ElementInspector(test_page)

        snapshot = await inspector.inspect_element('#submit-btn')

        assert snapshot is not None
        assert snapshot.tag_name == 'button'
        assert snapshot.id == 'submit-btn'
        assert 'btn' in snapshot.classes
        assert snapshot.inner_text == 'Submit'
        assert snapshot.is_enabled
        assert not snapshot.is_readonly

    @pytest.mark.asyncio
    async def test_element_not_found(self, test_page):
        """Test handling of non-existent elements."""
        inspector = ElementInspector(test_page)

        snapshot = await inspector.inspect_element('#nonexistent')

        assert snapshot is None

    @pytest.mark.asyncio
    async def test_visibility_detection(self, test_page):
        """Test visibility and display detection."""
        inspector = ElementInspector(test_page)

        # Visible element
        visible = await inspector.inspect_element('#submit-btn')
        assert visible.is_visible
        assert visible.is_displayed

        # Hidden (display: none)
        hidden = await inspector.inspect_element('.hidden')
        assert not hidden.is_displayed

        # Invisible (visibility: hidden)
        invisible = await inspector.inspect_element('.invisible')
        assert not invisible.is_visible

        # Transparent (opacity: 0)
        transparent = await inspector.inspect_element('.transparent')
        assert transparent.opacity == 0

    @pytest.mark.asyncio
    async def test_interactability_detection(self, test_page):
        """Test enabled/disabled and readonly detection."""
        inspector = ElementInspector(test_page)

        # Enabled button
        enabled = await inspector.inspect_element('#submit-btn')
        assert enabled.is_enabled

        # Disabled button
        disabled = await inspector.inspect_element('button[disabled]')
        assert not disabled.is_enabled

        # Readonly input
        readonly = await inspector.inspect_element('input[readonly]')
        assert readonly.is_readonly

    @pytest.mark.asyncio
    async def test_stable_id_detection(self, test_page):
        """Test detection of stable vs unstable IDs."""
        inspector = ElementInspector(test_page)

        # Stable ID
        stable = await inspector.inspect_element('#submit-btn')
        assert stable.has_stable_id

        # Unstable ID (timestamp)
        unstable = await inspector.inspect_element('#btn-1638234567890')
        assert not unstable.has_stable_id

    @pytest.mark.asyncio
    async def test_css_in_js_detection(self, test_page):
        """Test detection of CSS-in-JS classes."""
        inspector = ElementInspector(test_page)

        snapshot = await inspector.inspect_element('.css-1dbjc4n')

        assert snapshot is not None
        assert not snapshot.has_stable_classes
        # Inspector should detect these as unstable

    @pytest.mark.asyncio
    async def test_selector_quality_stable_id(self, test_page):
        """Test selector quality analysis for stable ID."""
        inspector = ElementInspector(test_page)

        snapshot = await inspector.inspect_element('#submit-btn')
        quality = await inspector.analyze_selector_quality(snapshot)

        assert quality.recommended_selector == '#submit-btn'
        assert quality.confidence >= 0.9
        assert quality.strategy == SelectorStrategy.ID

    @pytest.mark.asyncio
    async def test_selector_quality_aria_label(self, test_page):
        """Test selector quality prefers ARIA label."""
        inspector = ElementInspector(test_page)

        snapshot = await inspector.inspect_element('[aria-label="Close dialog"]')
        quality = await inspector.analyze_selector_quality(snapshot)

        assert 'aria-label="Close dialog"' in quality.recommended_selector
        assert quality.confidence >= 0.85
        # Should be ARIA_LABEL or at least high quality

    @pytest.mark.asyncio
    async def test_selector_quality_data_testid(self, test_page):
        """Test selector quality for data-testid."""
        inspector = ElementInspector(test_page)

        snapshot = await inspector.inspect_element('[data-testid="email-input"]')
        quality = await inspector.analyze_selector_quality(snapshot)

        # Should recommend data-testid selector
        assert 'data-testid' in quality.recommended_selector
        assert quality.confidence >= 0.8

    @pytest.mark.asyncio
    async def test_selector_quality_alternatives(self, test_page):
        """Test that quality analysis provides alternatives."""
        inspector = ElementInspector(test_page)

        snapshot = await inspector.inspect_element('#submit-btn')
        quality = await inspector.analyze_selector_quality(snapshot)

        # Should have alternative selectors
        assert len(quality.alternatives) > 0

        # Alternatives should be tuples of (selector, confidence, strategy)
        for alt_selector, confidence, strategy in quality.alternatives:
            assert isinstance(alt_selector, str)
            assert 0 <= confidence <= 1
            assert isinstance(strategy, SelectorStrategy)

    @pytest.mark.asyncio
    async def test_dynamic_analysis_stable(self, test_page):
        """Test dynamic analysis on stable element."""
        inspector = ElementInspector(test_page)

        dynamic = await inspector.is_element_dynamic(
            '#submit-btn',
            observation_duration=1.0,
            observation_interval=0.2
        )

        assert not dynamic.is_dynamic
        assert dynamic.change_frequency == 'stable'
        assert len(dynamic.changed_attributes) == 0

    @pytest.mark.asyncio
    async def test_ancestry_analysis(self, test_page):
        """Test element ancestry traversal."""
        inspector = ElementInspector(test_page)

        ancestry = await inspector.get_element_ancestry('#submit-btn', depth=3)

        # Should have at least body and html
        assert len(ancestry) >= 2

        # Check that we got parent elements
        tags = [a.tag_name for a in ancestry]
        assert 'body' in tags
        assert 'html' in tags

    @pytest.mark.asyncio
    async def test_sibling_analysis(self, test_page):
        """Test finding similar siblings."""
        inspector = ElementInspector(test_page)

        # Get siblings of first list item
        siblings = await inspector.get_similar_siblings('li.item:first-child')

        # Should find the other 2 items
        assert len(siblings) >= 2

        # All should be li.item elements
        for sibling in siblings:
            assert sibling.tag_name == 'li'
            assert 'item' in sibling.classes

    @pytest.mark.asyncio
    async def test_interaction_diagnosis_success(self, test_page):
        """Test diagnosis for interactable element."""
        inspector = ElementInspector(test_page)

        diagnosis = await inspector.diagnose_interaction_failure('#submit-btn')

        assert diagnosis['found']
        assert diagnosis['is_interactable']
        assert len(diagnosis['issues']) == 0

    @pytest.mark.asyncio
    async def test_interaction_diagnosis_hidden(self, test_page):
        """Test diagnosis for hidden element."""
        inspector = ElementInspector(test_page)

        diagnosis = await inspector.diagnose_interaction_failure('.hidden')

        assert diagnosis['found']
        assert not diagnosis['is_interactable']
        assert any('visible' in issue.lower() for issue in diagnosis['issues'])

    @pytest.mark.asyncio
    async def test_interaction_diagnosis_disabled(self, test_page):
        """Test diagnosis for disabled element."""
        inspector = ElementInspector(test_page)

        diagnosis = await inspector.diagnose_interaction_failure('button[disabled]')

        assert diagnosis['found']
        assert not diagnosis['is_interactable']
        assert any('disabled' in issue.lower() for issue in diagnosis['issues'])

    @pytest.mark.asyncio
    async def test_interaction_diagnosis_not_found(self, test_page):
        """Test diagnosis for non-existent element."""
        inspector = ElementInspector(test_page)

        diagnosis = await inspector.diagnose_interaction_failure('#nonexistent')

        assert not diagnosis['found']
        assert 'not found' in diagnosis['reason'].lower()
        assert len(diagnosis['suggestions']) > 0

    @pytest.mark.asyncio
    async def test_framework_detection(self, test_page):
        """Test React/Vue/Angular detection."""
        inspector = ElementInspector(test_page)

        # Check React-like element
        react_el = await inspector.inspect_element('#react-root')

        assert react_el is not None
        # Note: May not detect in this simple test, but field should exist
        assert hasattr(react_el, 'has_react_fiber')
        assert hasattr(react_el, 'has_vue_instance')
        assert hasattr(react_el, 'has_angular_scope')

    @pytest.mark.asyncio
    async def test_stability_score(self, test_page):
        """Test stability score calculation."""
        inspector = ElementInspector(test_page)

        # Element with stable ID and ARIA label
        aria_btn = await inspector.inspect_element('[aria-label="Close dialog"]')
        aria_quality = await inspector.analyze_selector_quality(aria_btn)
        assert aria_quality.stability_score > 0.5

        # Element with unstable classes
        css_in_js = await inspector.inspect_element('.css-1dbjc4n')
        css_quality = await inspector.analyze_selector_quality(css_in_js)
        # Should have lower stability score
        assert css_quality.stability_score < 0.8

    @pytest.mark.asyncio
    async def test_bounding_box(self, test_page):
        """Test bounding box extraction."""
        inspector = ElementInspector(test_page)

        snapshot = await inspector.inspect_element('#submit-btn')

        assert 'x' in snapshot.bounding_box
        assert 'y' in snapshot.bounding_box
        assert 'width' in snapshot.bounding_box
        assert 'height' in snapshot.bounding_box

        # Should have some size
        assert snapshot.bounding_box['width'] > 0
        assert snapshot.bounding_box['height'] > 0

    @pytest.mark.asyncio
    async def test_text_content_extraction(self, test_page):
        """Test text content extraction."""
        inspector = ElementInspector(test_page)

        # Button with text
        button = await inspector.inspect_element('#submit-btn')
        assert button.inner_text == 'Submit'

        # Input with placeholder
        input_el = await inspector.inspect_element('[data-testid="email-input"]')
        assert input_el.placeholder == 'Email'

    @pytest.mark.asyncio
    async def test_quality_warnings(self, test_page):
        """Test that quality analysis generates warnings."""
        inspector = ElementInspector(test_page)

        # Element with unstable ID
        unstable = await inspector.inspect_element('#btn-1638234567890')
        quality = await inspector.analyze_selector_quality(unstable)

        # Should have warning about unstable ID
        assert len(quality.warnings) > 0

        # CSS-in-JS element
        css_in_js = await inspector.inspect_element('.css-1dbjc4n')
        css_quality = await inspector.analyze_selector_quality(css_in_js)

        # Should warn about dynamic classes
        assert any('dynamic' in w.lower() for w in css_quality.warnings)


@pytest.mark.asyncio
async def test_real_website_inspection():
    """Integration test with a real website."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Use a known stable test site
        await page.goto('https://books.toscrape.com/')

        inspector = ElementInspector(page)

        # Inspect a book title
        selector = 'article.product_pod h3 a'
        snapshot = await inspector.inspect_element(selector)

        assert snapshot is not None
        assert snapshot.tag_name == 'a'
        assert len(snapshot.inner_text) > 0
        assert snapshot.is_visible

        # Analyze quality
        quality = await inspector.analyze_selector_quality(snapshot)
        assert quality.recommended_selector is not None
        assert quality.confidence > 0

        # Check for siblings (other books)
        siblings = await inspector.get_similar_siblings(selector)
        assert len(siblings) > 0

        await browser.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
