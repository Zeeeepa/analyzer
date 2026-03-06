"""
Optional patches to integrate DevToolsHooks into existing modules.

This file shows how to add DevTools monitoring to existing browser automation
modules without breaking changes.

USAGE:
  1. Copy relevant patches to the target files
  2. Test thoroughly
  3. Enable via config flag (e.g., enable_devtools_monitoring=True)
"""


# ==============================================================================
# PATCH 1: Add DevTools to playwright_direct.py
# ==============================================================================

def patch_playwright_direct():
    """
    Example: Add optional DevTools monitoring to playwright_direct.py

    Add this to the PlaywrightBrowser class or create_browser_session function.
    """

    # Add to class init or function
    example_code = """
from devtools_hooks import DevToolsHooks

class PlaywrightBrowser:
    def __init__(self, enable_devtools=False, **kwargs):
        self.enable_devtools = enable_devtools
        self.devtools = None
        # ... existing init code ...

    async def start(self):
        # ... existing start code ...

        if self.enable_devtools:
            self.devtools = DevToolsHooks(
                self.page,
                max_network_entries=500,
                max_console_entries=200,
                capture_response_bodies=False
            )
            await self.devtools.start_capture(network=True, console=True)
            logger.debug("DevTools monitoring enabled")

    async def close(self):
        if self.devtools:
            summary = self.devtools.summary()
            if summary['network']['failed_requests'] > 0:
                logger.warning(f"Session had {summary['network']['failed_requests']} failed requests")
            if summary['console']['errors'] > 0:
                logger.warning(f"Session had {summary['console']['errors']} console errors")
            await self.devtools.cleanup()

        # ... existing close code ...

    def get_diagnostics(self):
        '''Get DevTools diagnostics for debugging.'''
        if not self.devtools:
            return None

        return {
            "summary": self.devtools.summary(),
            "failed_requests": self.devtools.get_failed_requests(),
            "console_errors": self.devtools.get_console_log(level="error"),
            "page_errors": self.devtools.get_errors(),
            "slow_requests": self.devtools.get_slow_requests(threshold_ms=1000),
        }
"""
    return example_code


# ==============================================================================
# PATCH 2: Add DevTools to agentic_browser.py
# ==============================================================================

def patch_agentic_browser():
    """
    Example: Add DevTools to AgenticBrowser for error detection.

    This enhances the agent's ability to detect and diagnose issues.
    """

    example_code = """
from devtools_hooks import DevToolsHooks

class AgenticBrowser:
    def __init__(self, config=None):
        self.config = config or {}
        self.devtools = None
        # ... existing init ...

    async def initialize(self):
        # ... existing initialization ...

        # Enable DevTools in debug mode
        if self.config.get('debug_mode', False):
            self.devtools = DevToolsHooks(
                self.page,
                max_network_entries=200,  # Smaller for agent use
                max_console_entries=100,
                capture_response_bodies=False
            )
            await self.devtools.start_capture(network=True, console=True)
            logger.info("AgenticBrowser: DevTools monitoring enabled")

    async def execute_action(self, action):
        '''Execute action and check for errors via DevTools.'''

        # Clear DevTools before action
        if self.devtools:
            self.devtools.clear()

        # Execute action
        result = await self._execute_action_impl(action)

        # Check for issues after action
        if self.devtools and not result.success:
            diagnostics = self._get_devtools_diagnostics()
            if diagnostics:
                logger.warning(f"Action failed with DevTools diagnostics: {diagnostics}")
                result.diagnostics = diagnostics

        return result

    def _get_devtools_diagnostics(self):
        '''Get relevant DevTools info for failed actions.'''
        if not self.devtools:
            return None

        failed_requests = self.devtools.get_failed_requests()
        console_errors = self.devtools.get_console_log(level="error")
        page_errors = self.devtools.get_errors()

        if not (failed_requests or console_errors or page_errors):
            return None

        return {
            "failed_requests": len(failed_requests),
            "console_errors": len(console_errors),
            "page_errors": len(page_errors),
            "details": {
                "failed_urls": [r['url'] for r in failed_requests[:3]],
                "error_messages": [e['text'] for e in console_errors[:3]],
            }
        }

    async def cleanup(self):
        if self.devtools:
            # Log final summary
            summary = self.devtools.summary()
            logger.info(f"AgenticBrowser session summary: {summary}")
            await self.devtools.cleanup()

        # ... existing cleanup ...
"""
    return example_code


# ==============================================================================
# PATCH 3: Add DevTools to simple_agent.py
# ==============================================================================

def patch_simple_agent():
    """
    Example: Add DevTools monitoring to SimpleAgent.

    Enhance AgentResult with diagnostics information.
    """

    example_code = """
from devtools_hooks import DevToolsHooks
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class AgentResult:
    success: bool
    data: Any = None
    error: Optional[str] = None
    screenshots: list = field(default_factory=list)
    diagnostics: Optional[Dict[str, Any]] = None  # NEW: DevTools diagnostics

class SimpleAgent:
    def __init__(self, enable_diagnostics=False):
        self.enable_diagnostics = enable_diagnostics
        self.devtools = None
        # ... existing init ...

    async def initialize(self):
        # ... existing initialization ...

        if self.enable_diagnostics:
            self.devtools = DevToolsHooks(
                self.browser.page,
                max_network_entries=300,
                max_console_entries=100,
                capture_response_bodies=False
            )
            await self.devtools.start_capture(network=True, console=True)

    async def run_task(self, task_description: str) -> AgentResult:
        '''Run task and include DevTools diagnostics in result.'''

        # Clear DevTools before task
        if self.devtools:
            self.devtools.clear()

        try:
            # ... existing task execution ...

            result = AgentResult(success=True, data=task_data)

            # Add diagnostics if enabled
            if self.devtools:
                result.diagnostics = self._collect_diagnostics()

            return result

        except Exception as e:
            result = AgentResult(
                success=False,
                error=str(e),
                diagnostics=self._collect_diagnostics() if self.devtools else None
            )
            return result

    def _collect_diagnostics(self) -> Dict[str, Any]:
        '''Collect DevTools diagnostics for the task.'''
        if not self.devtools:
            return None

        summary = self.devtools.summary()

        return {
            "network": {
                "total_requests": summary['network']['total_requests'],
                "failed_requests": summary['network']['failed_requests'],
                "avg_duration_ms": summary['network']['average_duration_ms'],
                "slow_requests": len(self.devtools.get_slow_requests(threshold_ms=2000)),
            },
            "console": {
                "errors": summary['console']['errors'],
                "warnings": summary['console']['warnings'],
            },
            "issues": {
                "failed_urls": [r['url'] for r in self.devtools.get_failed_requests()[:5]],
                "error_messages": [e['text'] for e in self.devtools.get_console_log(level="error")[:5]],
            }
        }
"""
    return example_code


# ==============================================================================
# PATCH 4: Add DevTools to reliability_core.py
# ==============================================================================

def patch_reliability_core():
    """
    Example: Use DevTools data to enhance ToolResult reliability scoring.

    Track flaky requests and error patterns.
    """

    example_code = """
from devtools_hooks import DevToolsHooks

class ReliabilityMonitor:
    def __init__(self, page):
        self.page = page
        self.devtools = DevToolsHooks(
            page,
            max_network_entries=200,
            max_console_entries=100,
            capture_response_bodies=False
        )

    async def start(self):
        await self.devtools.start_capture(network=True, console=True)

    def assess_reliability(self, tool_result):
        '''Enhance ToolResult with DevTools reliability data.'''

        # Get DevTools summary
        summary = self.devtools.summary()

        # Calculate reliability score based on DevTools data
        reliability_score = 1.0

        # Penalize for failed requests
        if summary['network']['failed_requests'] > 0:
            reliability_score -= 0.1 * summary['network']['failed_requests']

        # Penalize for console errors
        if summary['console']['errors'] > 0:
            reliability_score -= 0.05 * summary['console']['errors']

        # Penalize for slow requests (>3s)
        slow_count = len(self.devtools.get_slow_requests(threshold_ms=3000))
        if slow_count > 0:
            reliability_score -= 0.05 * slow_count

        # Penalize for HTTP errors
        http_errors = len(self.devtools.get_status_code_errors())
        if http_errors > 0:
            reliability_score -= 0.1 * http_errors

        reliability_score = max(0.0, min(1.0, reliability_score))

        # Add to ToolResult
        tool_result.reliability_score = reliability_score
        tool_result.devtools_summary = summary

        return tool_result

    async def cleanup(self):
        await self.devtools.cleanup()
"""
    return example_code


# ==============================================================================
# PATCH 5: Add DevTools to cascading_recovery.py
# ==============================================================================

def patch_cascading_recovery():
    """
    Example: Use DevTools to inform recovery strategy.

    Different recovery actions based on error type detected.
    """

    example_code = """
from devtools_hooks import DevToolsHooks

class RecoveryOrchestrator:
    def __init__(self, page):
        self.page = page
        self.devtools = DevToolsHooks(
            page,
            max_network_entries=100,
            max_console_entries=50,
            capture_response_bodies=False
        )

    async def start(self):
        await self.devtools.start_capture(network=True, console=True)

    async def diagnose_and_recover(self, error):
        '''Use DevTools to diagnose error and choose recovery strategy.'''

        # Get DevTools diagnostics
        failed_requests = self.devtools.get_failed_requests()
        console_errors = self.devtools.get_console_log(level="error")
        page_errors = self.devtools.get_errors()
        blocked = self.devtools.get_blocked_resources()

        # Determine recovery strategy based on DevTools data

        # Strategy 1: Network issues
        if failed_requests:
            failure_reasons = [r.get('failure_reason', '') for r in failed_requests]
            if any('timeout' in reason.lower() for reason in failure_reasons):
                return await self._recover_from_timeout()
            if any('connection' in reason.lower() for reason in failure_reasons):
                return await self._recover_from_connection_error()

        # Strategy 2: CORS/CSP blocking
        if blocked:
            return await self._recover_from_blocking()

        # Strategy 3: JavaScript errors
        if console_errors or page_errors:
            return await self._recover_from_js_error()

        # Strategy 4: HTTP errors
        http_errors = self.devtools.get_status_code_errors()
        if http_errors:
            if any(e['status_code'] == 404 for e in http_errors):
                return await self._recover_from_404()
            if any(e['status_code'] >= 500 for e in http_errors):
                return await self._recover_from_server_error()

        # Default recovery
        return await self._generic_recovery()

    async def _recover_from_timeout(self):
        logger.info("Recovery: Increasing timeout and retrying")
        # ... recovery logic ...

    async def _recover_from_blocking(self):
        logger.info("Recovery: Detected resource blocking, adjusting headers")
        # ... recovery logic ...

    async def _recover_from_js_error(self):
        logger.info("Recovery: JavaScript errors detected, injecting error handler")
        # ... recovery logic ...
"""
    return example_code


# ==============================================================================
# Configuration helpers
# ==============================================================================

def create_devtools_config():
    """
    Example: Configuration for DevTools across different use cases.
    """

    configs = {
        "debug": {
            "enabled": True,
            "max_network_entries": 500,
            "max_console_entries": 200,
            "max_error_entries": 100,
            "capture_response_bodies": False,
        },
        "production_monitoring": {
            "enabled": True,
            "max_network_entries": 100,  # Smaller for production
            "max_console_entries": 50,
            "max_error_entries": 25,
            "capture_response_bodies": False,
        },
        "performance_testing": {
            "enabled": True,
            "max_network_entries": 1000,  # Large for analysis
            "max_console_entries": 100,
            "max_error_entries": 50,
            "capture_response_bodies": False,
        },
        "disabled": {
            "enabled": False,
        }
    }

    return configs


# ==============================================================================
# Usage examples
# ==============================================================================

if __name__ == "__main__":
    print("DevTools Integration Patches\n")
    print("=" * 60)
    print("\nThese are example patches showing how to integrate DevToolsHooks")
    print("into existing modules. Copy relevant sections to your files.\n")

    print("\n1. playwright_direct.py patch:")
    print("-" * 60)
    print(patch_playwright_direct())

    print("\n2. agentic_browser.py patch:")
    print("-" * 60)
    print(patch_agentic_browser())

    print("\n3. simple_agent.py patch:")
    print("-" * 60)
    print(patch_simple_agent())

    print("\n4. reliability_core.py patch:")
    print("-" * 60)
    print(patch_reliability_core())

    print("\n5. cascading_recovery.py patch:")
    print("-" * 60)
    print(patch_cascading_recovery())

    print("\nConfiguration examples:")
    print("-" * 60)
    import json
    configs = create_devtools_config()
    print(json.dumps(configs, indent=2))
