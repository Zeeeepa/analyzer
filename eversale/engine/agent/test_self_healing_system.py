#!/usr/bin/env python3
"""Tests for self-healing system."""
import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from .self_healing_system import (
    SelfHealingSystem,
    FailurePattern,
    SiteProfile,
    self_healing
)


class TestFailurePattern:
    """Tests for FailurePattern dataclass."""

    def test_failure_pattern_creation(self):
        """Test creating a failure pattern."""
        pattern = FailurePattern(
            error_type="selector_not_found",
            context='{"function": "click"}',
            failed_approach={"selector": "button.submit"},
            successful_approach=None,
            success_rate=0.0,
            occurrences=1,
            last_seen=datetime.now()
        )

        assert pattern.error_type == "selector_not_found"
        assert pattern.occurrences == 1
        assert pattern.success_rate == 0.0
        assert pattern.successful_approach is None


class TestSiteProfile:
    """Tests for SiteProfile dataclass."""

    def test_site_profile_creation(self):
        """Test creating a site profile."""
        profile = SiteProfile(
            domain="example.com",
            selector_patterns={"submit": "button[type='submit']"},
            success_rate=0.85,
            total_attempts=20,
            common_errors=["timeout", "selector_not_found"],
            preferred_strategies=["wait_then_retry", "use_generic_selector"]
        )

        assert profile.domain == "example.com"
        assert profile.success_rate == 0.85
        assert profile.total_attempts == 20
        assert len(profile.common_errors) == 2
        assert len(profile.preferred_strategies) == 2


class TestSelfHealingSystem:
    """Tests for SelfHealingSystem class."""

    def test_initialization(self):
        """Test system initialization."""
        healer = SelfHealingSystem()

        assert healer.failure_patterns == {}
        assert 'navigation' in healer.success_strategies
        assert 'interaction' in healer.success_strategies
        assert 'extraction' in healer.success_strategies
        assert healer.min_confidence == 0.8

    def test_generalize_selector(self):
        """Test selector generalization."""
        healer = SelfHealingSystem()

        # Test removing nth-child
        selector = "div.content:nth-child(2)"
        generalized = healer._generalize_selector(selector)
        assert ":nth-child" not in generalized

        # Test preferring class over ID
        selector = "div.main#specific"
        generalized = healer._generalize_selector(selector)
        assert "#" not in generalized

        # Test removing attribute values
        selector = 'input[type="text"]'
        generalized = healer._generalize_selector(selector)
        assert '"text"' not in generalized

    @pytest.mark.asyncio
    async def test_analyze_selector_failure(self):
        """Test selector failure analysis."""
        healer = SelfHealingSystem()
        context = {
            'function': 'playwright_click',
            'arguments': {'selector': 'button.submit:nth-child(3)'}
        }
        error = Exception("Element not found: selector")

        strategy = await healer.analyze_failure(error, context, 1)

        assert strategy is not None
        assert 'action' in strategy
        assert strategy['action'] == 'screenshot_first'

    @pytest.mark.asyncio
    async def test_analyze_timing_failure(self):
        """Test timing failure analysis."""
        healer = SelfHealingSystem()
        context = {
            'function': 'playwright_navigate',
            'arguments': {'url': 'https://example.com'}
        }
        error = Exception("Timeout waiting for page load")

        strategy = await healer.analyze_failure(error, context, 1)

        assert strategy is not None
        assert 'wait' in strategy or 'action' in strategy

    @pytest.mark.asyncio
    async def test_analyze_navigation_failure(self):
        """Test navigation failure analysis."""
        healer = SelfHealingSystem()
        context = {
            'function': 'playwright_navigate',
            'arguments': {'url': 'http://example.com'}
        }
        error = Exception("Navigation failed")

        strategy = await healer.analyze_failure(error, context, 1)

        assert strategy is not None
        assert 'action' in strategy
        assert strategy['action'] == 'force_https'
        assert 'https://' in strategy['modifications']['url']

    @pytest.mark.asyncio
    async def test_analyze_extraction_failure(self):
        """Test extraction failure analysis."""
        healer = SelfHealingSystem()
        context = {
            'function': 'playwright_extract_page_fast',
            'arguments': {}
        }
        error = Exception("Data not found on page")

        strategy = await healer.analyze_failure(error, context, 1)

        assert strategy is not None
        assert 'action' in strategy
        assert strategy['action'] == 'visual_check'

    @pytest.mark.asyncio
    async def test_analyze_unknown_failure(self):
        """Test unknown failure analysis."""
        healer = SelfHealingSystem()
        context = {'function': 'unknown_function'}
        error = Exception("Unknown error occurred")

        strategy = await healer.analyze_failure(error, context, 1)

        assert strategy is not None
        assert strategy['action'] == 'debug_mode'
        assert 'steps' in strategy

    @pytest.mark.asyncio
    async def test_heal_selector_failure_progression(self):
        """Test selector healing strategy progression."""
        healer = SelfHealingSystem()
        context = {
            'function': 'playwright_click',
            'arguments': {'selector': 'button.submit'}
        }

        # Attempt 1: Screenshot first
        strategy1 = await healer._heal_selector_failure(context, "selector not found", 1)
        assert strategy1['action'] == 'screenshot_first'

        # Attempt 2: Generic selector
        strategy2 = await healer._heal_selector_failure(context, "selector not found", 2)
        assert strategy2['action'] == 'use_generic_selector'

        # Attempt 3: Wait for load
        strategy3 = await healer._heal_selector_failure(context, "selector not found", 3)
        assert strategy3['action'] == 'wait_for_load'

        # Attempt 4: Scan page
        strategy4 = await healer._heal_selector_failure(context, "selector not found", 4)
        assert strategy4['action'] == 'scan_page'

        # Attempt 5+: Detailed report
        strategy5 = await healer._heal_selector_failure(context, "selector not found", 5)
        assert strategy5['action'] == 'detailed_report'

    @pytest.mark.asyncio
    async def test_heal_navigation_failure_strategies(self):
        """Test navigation healing strategies."""
        healer = SelfHealingSystem()
        context = {
            'function': 'playwright_navigate',
            'arguments': {'url': 'http://www.example.com/path'}
        }

        # Try HTTPS
        strategy1 = await healer._heal_navigation_failure(context, "nav error", 1)
        assert 'https://' in strategy1['modifications']['url']

        # Add www
        strategy2 = await healer._heal_navigation_failure(context, "nav error", 2)
        assert 'add_www' in strategy2['action']

        # Remove www
        strategy3 = await healer._heal_navigation_failure(context, "nav error", 3)
        assert 'remove_www' in strategy3['action']

        # Base domain
        strategy4 = await healer._heal_navigation_failure(context, "nav error", 4)
        assert strategy4['action'] == 'base_domain'

    def test_record_failure(self):
        """Test failure recording."""
        healer = SelfHealingSystem()
        context = {
            'function': 'playwright_click',
            'error_type': 'selector_not_found',
            'arguments': {'selector': 'button'}
        }
        error = "Element not found"

        healer.record_failure(error, context)

        pattern_key = "playwright_click_selector_not_found"
        assert pattern_key in healer.failure_patterns
        pattern = healer.failure_patterns[pattern_key]
        assert pattern.occurrences == 1
        assert pattern.success_rate == 0.0

    def test_record_failure_increments_occurrences(self):
        """Test failure recording increments occurrences."""
        healer = SelfHealingSystem()
        context = {
            'function': 'playwright_click',
            'error_type': 'selector_not_found'
        }

        healer.record_failure("error1", context)
        healer.record_failure("error2", context)
        healer.record_failure("error3", context)

        pattern_key = "playwright_click_selector_not_found"
        pattern = healer.failure_patterns[pattern_key]
        assert pattern.occurrences == 3

    def test_record_success(self):
        """Test success recording."""
        healer = SelfHealingSystem()
        context = {
            'function': 'playwright_click',
            'error_type': 'selector_not_found'
        }
        strategy = {
            'action': 'use_generic_selector'
        }

        healer.record_success(context, strategy)

        pattern_key = "playwright_click_use_generic_selector"
        assert pattern_key in healer.failure_patterns
        pattern = healer.failure_patterns[pattern_key]
        assert pattern.success_rate == 1.0
        assert pattern.occurrences == 1

    def test_record_success_updates_rate(self):
        """Test success recording updates success rate."""
        healer = SelfHealingSystem()
        context = {
            'function': 'playwright_click',
            'error_type': 'selector_not_found'
        }
        strategy = {'action': 'retry'}

        # Record 3 successes
        healer.record_success(context, strategy)
        healer.record_success(context, strategy)
        healer.record_success(context, strategy)

        pattern_key = "playwright_click_retry"
        pattern = healer.failure_patterns[pattern_key]
        assert pattern.success_rate == 1.0
        assert pattern.occurrences == 3

    def test_get_best_strategy_no_history(self):
        """Test getting best strategy with no history."""
        healer = SelfHealingSystem()
        context = {'function': 'playwright_click'}

        strategy = healer.get_best_strategy(context)

        assert strategy is None

    def test_get_best_strategy_with_history(self):
        """Test getting best strategy with history."""
        healer = SelfHealingSystem()

        # Record a successful strategy
        context = {'function': 'playwright_click'}
        strategy1 = {'action': 'wait_then_click', 'wait': 2}
        healer.record_success(context, strategy1)

        # Record another with lower success rate
        strategy2 = {'action': 'click_immediately'}
        healer.failure_patterns['playwright_click_click_immediately'] = FailurePattern(
            error_type='unknown',
            context=json.dumps(context),
            failed_approach={},
            successful_approach=strategy2,
            success_rate=0.6,
            occurrences=5,
            last_seen=datetime.now()
        )

        best = healer.get_best_strategy(context)

        assert best is not None
        assert best['action'] == 'wait_then_click'

    def test_get_best_strategy_filters_low_success(self):
        """Test that low success strategies are filtered out."""
        healer = SelfHealingSystem()

        context = {'function': 'playwright_navigate'}

        # Record strategy with low success rate (below 0.7 threshold)
        healer.failure_patterns['playwright_navigate_bad_strategy'] = FailurePattern(
            error_type='unknown',
            context=json.dumps(context),
            failed_approach={},
            successful_approach={'action': 'bad_strategy'},
            success_rate=0.5,  # Below 0.7 threshold
            occurrences=10,
            last_seen=datetime.now()
        )

        best = healer.get_best_strategy(context)

        assert best is None

    @pytest.mark.asyncio
    async def test_execute_strategy_wait(self):
        """Test executing wait strategy."""
        healer = SelfHealingSystem()
        strategy = {
            'action': 'wait',
            'steps': [
                {'type': 'wait', 'duration': 0.1}
            ]
        }

        result = await healer.execute_strategy(strategy)

        assert result['success'] is True
        assert 'waited 0.1s' in result['steps_executed']

    @pytest.mark.asyncio
    async def test_execute_strategy_screenshot(self):
        """Test executing screenshot strategy."""
        healer = SelfHealingSystem()

        # Mock playwright client
        mock_client = AsyncMock()
        mock_client.screenshot = AsyncMock()

        strategy = {
            'action': 'screenshot',
            'steps': [
                {'type': 'screenshot'}
            ]
        }

        result = await healer.execute_strategy(strategy, mock_client)

        assert result['success'] is True
        assert 'took screenshot' in result['steps_executed']
        mock_client.screenshot.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_strategy_refresh(self):
        """Test executing refresh strategy."""
        healer = SelfHealingSystem()

        # Mock playwright client
        mock_page = AsyncMock()
        mock_page.reload = AsyncMock()
        mock_client = Mock()
        mock_client.page = mock_page

        strategy = {
            'action': 'refresh',
            'steps': [
                {'type': 'refresh'}
            ]
        }

        result = await healer.execute_strategy(strategy, mock_client)

        assert result['success'] is True
        assert 'refreshed page' in result['steps_executed']
        mock_page.reload.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_strategy_javascript(self):
        """Test executing JavaScript strategy."""
        healer = SelfHealingSystem()

        # Mock playwright client
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=42)
        mock_client = Mock()
        mock_client.page = mock_page

        strategy = {
            'action': 'execute_js',
            'steps': [
                {'type': 'javascript', 'script': 'return 42;'}
            ]
        }

        result = await healer.execute_strategy(strategy, mock_client)

        assert result['success'] is True
        assert 'ran script' in result['steps_executed']
        assert result['js_result'] == 42

    @pytest.mark.asyncio
    async def test_execute_strategy_javascript_security(self):
        """Test JavaScript execution blocks dangerous code."""
        healer = SelfHealingSystem()

        mock_page = AsyncMock()
        mock_client = Mock()
        mock_client.page = mock_page

        # Try dangerous eval
        strategy = {
            'action': 'execute_js',
            'steps': [
                {'type': 'javascript', 'script': 'eval("malicious code")'}
            ]
        }

        result = await healer.execute_strategy(strategy, mock_client)

        # Should succeed but not execute the script
        assert result['success'] is True
        mock_page.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_strategy_retry_selector(self):
        """Test retry selector strategy."""
        healer = SelfHealingSystem()

        # Mock playwright client
        mock_element = Mock()
        mock_page = AsyncMock()
        mock_page.query_selector = AsyncMock(side_effect=[None, None, mock_element])
        mock_client = Mock()
        mock_client.page = mock_page

        strategy = {
            'action': 'retry_selector',
            'steps': [
                {
                    'type': 'retry_selector',
                    'selectors': ['button.primary', 'button[type="submit"]', 'button']
                }
            ]
        }

        result = await healer.execute_strategy(strategy, mock_client)

        assert result['success'] is True
        assert result['found_selector'] == 'button'
        assert mock_page.query_selector.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_strategy_error_handling(self):
        """Test strategy execution error handling."""
        healer = SelfHealingSystem()

        mock_page = AsyncMock()
        mock_page.reload = AsyncMock(side_effect=Exception("Page reload failed"))
        mock_client = Mock()
        mock_client.page = mock_page

        strategy = {
            'action': 'refresh',
            'steps': [
                {'type': 'refresh'}
            ]
        }

        result = await healer.execute_strategy(strategy, mock_client)

        assert result['success'] is False
        assert result['error'] == "Page reload failed"

    @pytest.mark.asyncio
    async def test_generate_failure_report(self):
        """Test failure report generation."""
        healer = SelfHealingSystem()
        context = {
            'function': 'playwright_click',
            'arguments': {'selector': 'button.missing'}
        }
        error = "Element not found"

        report = await healer._generate_failure_report(context, error)

        assert 'error' in report
        assert 'context' in report
        assert 'suggestions' in report
        assert 'next_steps' in report
        assert len(report['suggestions']) > 0
        assert len(report['next_steps']) > 0


class TestSingleton:
    """Test singleton instance."""

    def test_singleton_exists(self):
        """Test that singleton instance is available."""
        assert self_healing is not None
        assert isinstance(self_healing, SelfHealingSystem)
