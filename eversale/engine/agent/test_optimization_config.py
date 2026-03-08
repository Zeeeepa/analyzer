#!/usr/bin/env python3
"""Tests for browser optimization configuration system."""

import os
import pytest
from config_loader import (
    load_browser_optimizations,
    is_optimization_enabled,
    is_snapshot_first_enabled,
    is_token_optimizer_enabled,
    is_devtools_enabled,
    is_cdp_enabled,
    get_token_budget,
    get_cdp_port,
    get_optimization_setting,
    matches_trigger,
    reload_config
)


class TestConfigLoading:
    """Test configuration loading and defaults."""

    def test_config_loads_successfully(self):
        """Config should load without errors."""
        config = load_browser_optimizations()
        assert isinstance(config, dict)
        assert 'optimization' in config or 'triggers' in config

    def test_master_switch_default(self):
        """Optimizations should be enabled by default."""
        assert is_optimization_enabled() is True

    def test_feature_flags_default(self):
        """All features should be enabled by default."""
        assert is_snapshot_first_enabled() is True
        assert is_token_optimizer_enabled() is True
        assert is_devtools_enabled() is True
        assert is_cdp_enabled() is True

    def test_value_getters(self):
        """Value getters should return expected defaults."""
        assert get_token_budget() == 8000
        assert get_cdp_port() == 9222

    def test_nested_settings(self):
        """Should access nested settings via path."""
        max_text = get_optimization_setting('optimization.token_optimizer.max_text_length', 200)
        assert max_text == 200

        cache_ttl = get_optimization_setting('optimization.snapshot_first.cache_ttl_seconds', 30)
        assert cache_ttl == 30


class TestTriggerMatching:
    """Test natural language trigger matching."""

    def test_exact_match(self):
        """Exact trigger text should match."""
        assert matches_trigger("use my chrome", "use_cdp") is True
        assert matches_trigger("extract links", "extract_links") is True

    def test_fuzzy_match(self):
        """All words from trigger should be present (fuzzy)."""
        assert matches_trigger("extract all links from page", "extract_links") is True
        assert matches_trigger("show me the errors", "show_errors") is True

    def test_no_match(self):
        """Non-matching input should return False."""
        assert matches_trigger("just navigate", "extract_links") is False
        assert matches_trigger("open website", "show_errors") is False

    def test_case_insensitive(self):
        """Matching should be case-insensitive."""
        assert matches_trigger("USE MY CHROME", "use_cdp") is True
        assert matches_trigger("Extract Links", "extract_links") is True


class TestEnvironmentOverrides:
    """Test environment variable overrides."""

    def test_token_budget_override(self):
        """EVERSALE_TOKEN_BUDGET should override default."""
        original = get_token_budget()
        os.environ['EVERSALE_TOKEN_BUDGET'] = '4000'
        reload_config()

        assert get_token_budget() == 4000

        # Cleanup
        del os.environ['EVERSALE_TOKEN_BUDGET']
        reload_config()
        assert get_token_budget() == original

    def test_cdp_port_override(self):
        """EVERSALE_CDP_PORT should override default."""
        original = get_cdp_port()
        os.environ['EVERSALE_CDP_PORT'] = '9333'
        reload_config()

        assert get_cdp_port() == 9333

        # Cleanup
        del os.environ['EVERSALE_CDP_PORT']
        reload_config()
        assert get_cdp_port() == original

    def test_snapshot_first_override(self):
        """EVERSALE_SNAPSHOT_FIRST should override default."""
        os.environ['EVERSALE_SNAPSHOT_FIRST'] = 'false'
        reload_config()

        assert is_snapshot_first_enabled() is False

        # Cleanup
        del os.environ['EVERSALE_SNAPSHOT_FIRST']
        reload_config()

    def test_master_switch_override(self):
        """EVERSALE_OPTIMIZATION_ENABLED should disable all."""
        os.environ['EVERSALE_OPTIMIZATION_ENABLED'] = 'false'
        reload_config()

        assert is_optimization_enabled() is False
        # All features should be disabled when master is off
        assert is_snapshot_first_enabled() is False
        assert is_token_optimizer_enabled() is False

        # Cleanup
        del os.environ['EVERSALE_OPTIMIZATION_ENABLED']
        reload_config()


class TestTriggerCategories:
    """Test all trigger categories."""

    def test_use_cdp_triggers(self):
        """CDP triggers should match correctly."""
        test_cases = [
            ("use my chrome", True),
            ("existing chrome session", True),
            ("preserve my session", True),
            ("keep logged in", True),
            ("just open browser", False),
        ]
        for user_input, expected in test_cases:
            assert matches_trigger(user_input, 'use_cdp') == expected

    def test_extract_links_triggers(self):
        """Link extraction triggers should match correctly."""
        test_cases = [
            ("extract links", True),
            ("get all links", True),
            ("find links on page", True),
            ("click button", False),
        ]
        for user_input, expected in test_cases:
            assert matches_trigger(user_input, 'extract_links') == expected

    def test_show_errors_triggers(self):
        """Error display triggers should match correctly."""
        test_cases = [
            ("show errors", True),
            ("what failed", True),
            ("debug this", True),
            ("network errors", True),
            ("just navigate", False),
        ]
        for user_input, expected in test_cases:
            assert matches_trigger(user_input, 'show_errors') == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
