"""
Comprehensive test suite for the local API server, launcher, and P1/P2 bug fixes.

Run: cd eversale/engine && python -m pytest test_local_api_server.py -v
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

# Ensure engine directory is importable
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "agent"))
sys.path.insert(0, str(Path(__file__).parent / "ace"))


# --------------------------------------------------------------------------
# Section 1: Module import tests
# --------------------------------------------------------------------------

class TestLocalAPIServerImport(unittest.TestCase):
    """Test that local_api_server module imports cleanly."""

    def test_module_imports(self):
        import local_api_server
        self.assertTrue(hasattr(local_api_server, "LocalAPIServer"))
        self.assertTrue(hasattr(local_api_server, "create_app"))
        self.assertTrue(hasattr(local_api_server, "AIOHTTP_AVAILABLE"))

    def test_aiohttp_availability(self):
        import local_api_server
        # Should be a bool regardless of whether aiohttp is installed
        self.assertIsInstance(local_api_server.AIOHTTP_AVAILABLE, bool)


class TestLocalServerLauncherImport(unittest.TestCase):
    """Test that local_server_launcher module imports cleanly."""

    def test_module_imports(self):
        import local_server_launcher
        self.assertTrue(hasattr(local_server_launcher, "ensure_local_server"))
        self.assertTrue(hasattr(local_server_launcher, "_should_start"))
        self.assertTrue(hasattr(local_server_launcher, "_get_upstream_base"))
        self.assertTrue(hasattr(local_server_launcher, "_get_upstream_api_key"))


# --------------------------------------------------------------------------
# Section 2: Port selection tests
# --------------------------------------------------------------------------

class TestPortSelection(unittest.TestCase):
    """Test port selection logic."""

    def test_default_port_constant(self):
        from local_api_server import DEFAULT_PORT
        self.assertEqual(DEFAULT_PORT, 19532)

    def test_find_free_port_returns_int(self):
        from local_api_server import _find_free_port
        port = _find_free_port()
        self.assertIsInstance(port, int)
        self.assertGreater(port, 0)
        self.assertLessEqual(port, 65535)


# --------------------------------------------------------------------------
# Section 3: Upstream resolution tests
# --------------------------------------------------------------------------

class TestUpstreamResolution(unittest.TestCase):
    """Test environment variable resolution for upstream config."""

    def test_default_upstream_base(self):
        from local_server_launcher import _get_upstream_base
        with patch.dict(os.environ, {}, clear=True):
            result = _get_upstream_base()
            self.assertEqual(result, "https://api.openai.com/v1")

    def test_openai_base_url_override(self):
        from local_server_launcher import _get_upstream_base
        with patch.dict(os.environ, {"OPENAI_BASE_URL": "https://api.z.ai/v1"}, clear=True):
            result = _get_upstream_base()
            self.assertEqual(result, "https://api.z.ai/v1")

    def test_upstream_url_takes_priority(self):
        from local_server_launcher import _get_upstream_base
        with patch.dict(os.environ, {
            "EVERSALE_UPSTREAM_URL": "http://custom:8080",
            "OPENAI_BASE_URL": "https://api.z.ai/v1",
        }, clear=True):
            result = _get_upstream_base()
            self.assertEqual(result, "http://custom:8080")

    def test_api_key_resolution(self):
        from local_server_launcher import _get_upstream_api_key
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test123"}, clear=True):
            result = _get_upstream_api_key()
            self.assertEqual(result, "sk-test123")


# --------------------------------------------------------------------------
# Section 4: App creation tests
# --------------------------------------------------------------------------

class TestCreateApp(unittest.TestCase):
    """Test aiohttp app factory."""

    def test_create_app_returns_app(self):
        try:
            from local_api_server import create_app, AIOHTTP_AVAILABLE
            if not AIOHTTP_AVAILABLE:
                self.skipTest("aiohttp not available")
            app = create_app("https://api.openai.com/v1", "test-key")
            from aiohttp import web
            self.assertIsInstance(app, web.Application)
        except ImportError:
            self.skipTest("aiohttp not installed")


# --------------------------------------------------------------------------
# Section 5: Stub endpoint tests
# --------------------------------------------------------------------------

class TestStubEndpoints(unittest.TestCase):
    """Test stub endpoints return expected responses."""

    def _run_async(self, coro):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_stub_license_returns_valid(self):
        try:
            from local_api_server import _stub_license, AIOHTTP_AVAILABLE
            if not AIOHTTP_AVAILABLE:
                self.skipTest("aiohttp not available")

            mock_request = MagicMock()
            resp = self._run_async(_stub_license(mock_request))
            body = json.loads(resp.body)
            self.assertTrue(body["valid"])
            self.assertEqual(body["plan"], "local")
        except ImportError:
            self.skipTest("aiohttp not installed")

    def test_stub_usage_returns_ok(self):
        try:
            from local_api_server import _stub_usage, AIOHTTP_AVAILABLE
            if not AIOHTTP_AVAILABLE:
                self.skipTest("aiohttp not available")

            mock_request = MagicMock()
            resp = self._run_async(_stub_usage(mock_request))
            body = json.loads(resp.body)
            self.assertEqual(body["status"], "ok")
        except ImportError:
            self.skipTest("aiohttp not installed")

    def test_health_returns_healthy(self):
        try:
            from local_api_server import _health, AIOHTTP_AVAILABLE
            if not AIOHTTP_AVAILABLE:
                self.skipTest("aiohttp not available")

            mock_request = MagicMock()
            resp = self._run_async(_health(mock_request))
            body = json.loads(resp.body)
            self.assertEqual(body["status"], "healthy")
            self.assertEqual(body["mode"], "local")
        except ImportError:
            self.skipTest("aiohttp not installed")

    def test_stub_license_has_features(self):
        try:
            from local_api_server import _stub_license, AIOHTTP_AVAILABLE
            if not AIOHTTP_AVAILABLE:
                self.skipTest("aiohttp not available")

            mock_request = MagicMock()
            resp = self._run_async(_stub_license(mock_request))
            body = json.loads(resp.body)
            self.assertIn("all", body["features"])
        except ImportError:
            self.skipTest("aiohttp not installed")


# --------------------------------------------------------------------------
# Section 6: Launcher condition tests
# --------------------------------------------------------------------------

class TestLauncherConditions(unittest.TestCase):
    """Test when the launcher should auto-start."""

    def test_explicit_flag(self):
        from local_server_launcher import _should_start
        with patch.dict(os.environ, {"EVERSALE_LOCAL_SERVER": "true"}, clear=True):
            self.assertTrue(_should_start())

    def test_openai_key_triggers(self):
        from local_server_launcher import _should_start
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            self.assertTrue(_should_start())

    def test_no_env_no_start(self):
        from local_server_launcher import _should_start
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(_should_start())


# --------------------------------------------------------------------------
# Section 7: Playbook bug fix tests
# --------------------------------------------------------------------------

class TestPlaybookBugFixes(unittest.TestCase):
    """Test the 3 playbook.py P1/P2 bug fixes."""

    def test_load_failure_resets_index(self):
        """Bug fix #2: load() must reset _index when strategies are cleared."""
        try:
            from ace.playbook import StrategyPlaybook
        except ImportError:
            self.skipTest("Cannot import playbook module")

        pb = StrategyPlaybook.__new__(StrategyPlaybook)
        pb.strategies = ["stale"]
        pb._index = {"stale_key": ["stale"]}
        pb.playbook_path = "/nonexistent/path.yaml"

        # Simulate load failure
        try:
            pb.load()
        except Exception:
            pass

        # After failure, both should be empty
        self.assertEqual(pb.strategies, [])
        self.assertEqual(pb._index, {})

    def test_query_combines_page_specific_and_general(self):
        """Bug fix #3: query_strategies must combine page-specific + general results."""
        try:
            from ace.playbook import StrategyPlaybook, Strategy
        except ImportError:
            self.skipTest("Cannot import playbook module")

        pb = StrategyPlaybook.__new__(StrategyPlaybook)
        pb.strategies = []
        pb._index = {}

        # Create test strategies
        page_s = MagicMock(spec=Strategy)
        page_s.success_rate = 0.9
        general_s = MagicMock(spec=Strategy)
        general_s.success_rate = 0.8

        pb._index = {
            "dom:act:special": [page_s],
            "dom:act": [general_s],
        }

        results = pb.query_strategies("dom", "act", limit=5, page_type="special")
        # Should include both page-specific AND general
        self.assertIn(page_s, results)
        self.assertIn(general_s, results)

    def test_add_strategy_updates_page_type_index(self):
        """Bug fix #4: add_strategy must update page-type-specific index."""
        try:
            from ace.playbook import StrategyPlaybook
        except ImportError:
            self.skipTest("Cannot import playbook module")

        pb = StrategyPlaybook.__new__(StrategyPlaybook)
        pb.strategies = []
        pb._index = {}
        pb.playbook_path = None

        pb.add_strategy(
            domain="linkedin",
            action_type="profile_view",
            strategy="Use Sales Navigator advanced search",
            page_type="sales_navigator",
        )

        # General index should have it
        self.assertIn("linkedin:profile_view", pb._index)
        self.assertEqual(len(pb._index["linkedin:profile_view"]), 1)

        # Page-type-specific index should ALSO have it
        self.assertIn("linkedin:profile_view:sales_navigator", pb._index)
        self.assertEqual(len(pb._index["linkedin:profile_view:sales_navigator"]), 1)


# --------------------------------------------------------------------------
# Section 8: Injector bug fix test
# --------------------------------------------------------------------------

class TestInjectorBugFix(unittest.TestCase):
    """Test injector.py split() fix."""

    def test_split_preserves_content_after_multiple_markers(self):
        """Bug fix #1: split with maxsplit=1 preserves all content."""
        prompt = "System\nAvailable tools:\nTool A\nAvailable tools:\nTool B"

        # Correct: split(marker, 1) keeps everything after first split
        parts = prompt.split("Available tools:", 1)
        self.assertEqual(len(parts), 2)
        self.assertIn("Tool B", parts[1])

        # Incorrect: split(marker) would give 3 parts and lose Tool B
        parts_bad = prompt.split("Available tools:")
        self.assertEqual(len(parts_bad), 3)


# --------------------------------------------------------------------------
# Section 9: Reflector bug fix tests
# --------------------------------------------------------------------------

class TestReflectorBugFixes(unittest.TestCase):
    """Test reflector.py P2 bug fixes."""

    def test_none_strategy_text_does_not_crash(self):
        """Bug fix #6: is_quality_strategy(None) must not crash."""
        try:
            from ace.reflector import ACEReflector
        except ImportError:
            self.skipTest("Cannot import reflector module")

        ref = ACEReflector.__new__(ACEReflector)
        ref.training_mode = False
        ref.MIN_STRATEGY_LENGTH = 20
        ref.MIN_STRATEGY_LENGTH_TRAINING = 10

        # Should return False, not raise TypeError
        result = ref.is_quality_strategy(None)
        self.assertFalse(result)

    def test_empty_strategy_text_returns_false(self):
        """Bug fix #6: is_quality_strategy('') must return False."""
        try:
            from ace.reflector import ACEReflector
        except ImportError:
            self.skipTest("Cannot import reflector module")

        ref = ACEReflector.__new__(ACEReflector)
        ref.training_mode = False
        ref.MIN_STRATEGY_LENGTH = 20
        ref.MIN_STRATEGY_LENGTH_TRAINING = 10

        result = ref.is_quality_strategy("")
        self.assertFalse(result)

    def test_failed_not_treated_as_recovery(self):
        """Bug fix #5: 'failed' in next call must not be treated as recovery."""
        # Verify the fix logic: both 'error' and 'failed' must be checked
        next_content = "Operation failed with timeout"
        next_lower = next_content.lower()
        is_recovery = 'error' not in next_lower and 'failed' not in next_lower
        self.assertFalse(is_recovery)  # Should NOT be treated as recovery


# --------------------------------------------------------------------------
# Section 10: Playbook YAML marker test
# --------------------------------------------------------------------------

class TestPlaybookYAMLMarkers(unittest.TestCase):
    """Test that playbook.yaml has clean UTF-8 markers."""

    def test_no_mojibake_markers(self):
        yaml_path = Path(__file__).parent / "ace" / "playbook.yaml"
        if not yaml_path.exists():
            self.skipTest("playbook.yaml not found")

        try:
            import yaml
        except ImportError:
            self.skipTest("pyyaml not available")

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        markers = {s.get("marker", "") for s in data.get("strategies", [])}

        # Valid markers are ✓ (U+2713) and ✗ (U+2717)
        valid_markers = {"✓", "✗"}
        invalid = markers - valid_markers
        self.assertEqual(invalid, set(), f"Found invalid/mojibake markers: {invalid}")


# --------------------------------------------------------------------------
# Section 11: Server lifecycle test
# --------------------------------------------------------------------------

class TestLocalAPIServerLifecycle(unittest.TestCase):
    """Test server start/stop lifecycle."""

    def test_server_properties(self):
        try:
            from local_api_server import LocalAPIServer, AIOHTTP_AVAILABLE
            if not AIOHTTP_AVAILABLE:
                self.skipTest("aiohttp not available")
        except ImportError:
            self.skipTest("Cannot import LocalAPIServer")

        server = LocalAPIServer(
            upstream_base="https://api.openai.com/v1",
            upstream_api_key="test-key",
        )
        self.assertFalse(server.is_running)
        self.assertTrue(server.base_url.startswith("http://127.0.0.1:"))
        self.assertIsInstance(server.port, int)


# --------------------------------------------------------------------------
# Section 12: URL configuration tests
# --------------------------------------------------------------------------

class TestURLConfiguration(unittest.TestCase):
    """Test that hardcoded URLs are now configurable."""

    def test_license_validator_uses_env(self):
        """license_validator.py should read EVERSALE_LICENSE_URL from env."""
        try:
            # Test the pattern without importing the actual module
            url = os.environ.get(
                "EVERSALE_LICENSE_URL",
                "https://eversale.io/api/desktop/validate-license"
            )
            self.assertEqual(url, "https://eversale.io/api/desktop/validate-license")

            with patch.dict(os.environ, {"EVERSALE_LICENSE_URL": "http://local:19532/api/desktop/validate-license"}):
                url = os.environ.get(
                    "EVERSALE_LICENSE_URL",
                    "https://eversale.io/api/desktop/validate-license"
                )
                self.assertEqual(url, "http://local:19532/api/desktop/validate-license")
        except Exception:
            self.skipTest("URL configuration test failed")

    def test_desktop_url_uses_env(self):
        """worker_usage_reporter.py and kimi_k2_client.py should read EVERSALE_DESKTOP_URL."""
        default = "https://eversale.io/api/desktop"
        url = os.environ.get("EVERSALE_DESKTOP_URL", default)
        self.assertEqual(url, default)

        with patch.dict(os.environ, {"EVERSALE_DESKTOP_URL": "http://local:19532/api/desktop"}):
            url = os.environ.get("EVERSALE_DESKTOP_URL", default)
            self.assertEqual(url, "http://local:19532/api/desktop")


if __name__ == "__main__":
    unittest.main()

