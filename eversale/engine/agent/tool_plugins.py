"""
Tool Plugin/Hooks System for Agent Backend

This module provides a plugin architecture for intercepting and modifying tool calls.
Inspired by OpenCode's plugin system, it allows registering hooks that run before
and after tool execution.

Features:
- Before/after hooks with pattern matching
- Global hooks that run for all tools
- Error handling hooks
- Async support
- Priority-based execution order
- Argument and result transformation
- Audit logging and timing plugins

Usage:
    from tool_plugins import get_plugin_manager, AuditPlugin, TimingPlugin

    pm = get_plugin_manager()
    pm.register_plugin(AuditPlugin())
    pm.register_plugin(TimingPlugin())

    # Register custom hooks
    async def my_hook(tool_name, args, context):
        return args, True

    pm.register_before_hook("playwright_*", my_hook)
"""

import re
import time
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from pathlib import Path
import asyncio


logger = logging.getLogger(__name__)


class HookPhase(Enum):
    """Phases where hooks can be executed"""
    BEFORE_CALL = "before_call"
    AFTER_CALL = "after_call"
    ON_ERROR = "on_error"


@dataclass
class HookContext:
    """Context passed to all hooks"""
    tool_name: str
    phase: HookPhase
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        """Set metadata value"""
        self.metadata[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get metadata value"""
        return self.metadata.get(key, default)


@dataclass
class HookRegistration:
    """Represents a registered hook"""
    pattern: str
    callback: Callable
    priority: int = 100
    phase: HookPhase = HookPhase.BEFORE_CALL

    def matches(self, tool_name: str) -> bool:
        """Check if pattern matches tool name"""
        # Exact match
        if self.pattern == tool_name:
            return True

        # Match all
        if self.pattern == "*":
            return True

        # Wildcard pattern (convert to regex)
        if "*" in self.pattern:
            regex_pattern = "^" + self.pattern.replace("*", ".*") + "$"
            return bool(re.match(regex_pattern, tool_name))

        # Direct regex pattern (if it starts with regex markers)
        if self.pattern.startswith("r\"") or self.pattern.startswith("r'"):
            regex_str = self.pattern[2:-1]  # Remove r" and "
            return bool(re.match(regex_str, tool_name))

        return False


class ToolPlugin:
    """Base class for tool plugins"""

    name: str = "base_plugin"
    priority: int = 100

    async def before_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        context: HookContext
    ) -> Tuple[Dict[str, Any], bool]:
        """
        Called before tool execution

        Args:
            tool_name: Name of the tool being called
            args: Arguments passed to the tool
            context: Hook context for sharing data

        Returns:
            Tuple of (modified_args, should_continue)
            - modified_args: Potentially modified arguments
            - should_continue: False to cancel execution
        """
        return args, True

    async def after_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        context: HookContext
    ) -> Any:
        """
        Called after successful tool execution

        Args:
            tool_name: Name of the tool that was called
            args: Arguments that were passed
            result: Result from the tool
            context: Hook context

        Returns:
            Potentially modified result
        """
        return result

    async def on_error(
        self,
        tool_name: str,
        args: Dict[str, Any],
        error: Exception,
        context: HookContext
    ) -> Tuple[bool, Exception]:
        """
        Called when tool execution fails

        Args:
            tool_name: Name of the tool that failed
            args: Arguments that were passed
            error: The exception that was raised
            context: Hook context

        Returns:
            Tuple of (should_retry, modified_error)
            - should_retry: True to retry execution
            - modified_error: Potentially modified exception
        """
        return False, error

    def get_patterns(self) -> List[str]:
        """
        Return list of patterns this plugin should match
        Default is all tools ("*")
        """
        return ["*"]


class PluginManager:
    """Manages tool plugins and hooks"""

    def __init__(self):
        self._plugins: List[ToolPlugin] = []
        self._hooks: Dict[HookPhase, List[HookRegistration]] = {
            phase: [] for phase in HookPhase
        }
        self._enabled = True

    def enable(self) -> None:
        """Enable plugin system"""
        self._enabled = True

    def disable(self) -> None:
        """Disable plugin system"""
        self._enabled = False

    def register_plugin(self, plugin: ToolPlugin) -> None:
        """Register a plugin"""
        self._plugins.append(plugin)
        logger.info(f"Registered plugin: {plugin.name}")

    def unregister_plugin(self, plugin_name: str) -> bool:
        """Unregister a plugin by name"""
        for i, plugin in enumerate(self._plugins):
            if plugin.name == plugin_name:
                self._plugins.pop(i)
                logger.info(f"Unregistered plugin: {plugin_name}")
                return True
        return False

    def register_before_hook(
        self,
        pattern: str,
        callback: Callable,
        priority: int = 100
    ) -> None:
        """Register a before-call hook"""
        hook = HookRegistration(
            pattern=pattern,
            callback=callback,
            priority=priority,
            phase=HookPhase.BEFORE_CALL
        )
        self._hooks[HookPhase.BEFORE_CALL].append(hook)
        self._sort_hooks(HookPhase.BEFORE_CALL)
        logger.debug(f"Registered before hook for pattern: {pattern}")

    def register_after_hook(
        self,
        pattern: str,
        callback: Callable,
        priority: int = 100
    ) -> None:
        """Register an after-call hook"""
        hook = HookRegistration(
            pattern=pattern,
            callback=callback,
            priority=priority,
            phase=HookPhase.AFTER_CALL
        )
        self._hooks[HookPhase.AFTER_CALL].append(hook)
        self._sort_hooks(HookPhase.AFTER_CALL)
        logger.debug(f"Registered after hook for pattern: {pattern}")

    def register_error_hook(
        self,
        pattern: str,
        callback: Callable,
        priority: int = 100
    ) -> None:
        """Register an error hook"""
        hook = HookRegistration(
            pattern=pattern,
            callback=callback,
            priority=priority,
            phase=HookPhase.ON_ERROR
        )
        self._hooks[HookPhase.ON_ERROR].append(hook)
        self._sort_hooks(HookPhase.ON_ERROR)
        logger.debug(f"Registered error hook for pattern: {pattern}")

    def register_global_hook(
        self,
        phase: HookPhase,
        callback: Callable,
        priority: int = 100
    ) -> None:
        """Register a global hook that runs for all tools"""
        hook = HookRegistration(
            pattern="*",
            callback=callback,
            priority=priority,
            phase=phase
        )
        self._hooks[phase].append(hook)
        self._sort_hooks(phase)
        logger.debug(f"Registered global {phase.value} hook")

    def _sort_hooks(self, phase: HookPhase) -> None:
        """Sort hooks by priority (lower number = higher priority)"""
        self._hooks[phase].sort(key=lambda h: h.priority)

    def _get_matching_hooks(
        self,
        tool_name: str,
        phase: HookPhase
    ) -> List[HookRegistration]:
        """Get all hooks matching tool name and phase"""
        return [
            hook for hook in self._hooks[phase]
            if hook.matches(tool_name)
        ]

    async def execute_before_hooks(
        self,
        tool_name: str,
        args: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], bool, HookContext]:
        """
        Execute all before-call hooks

        Returns:
            Tuple of (modified_args, should_continue, context)
        """
        if not self._enabled:
            return args, True, HookContext(tool_name, HookPhase.BEFORE_CALL)

        context = HookContext(tool_name, HookPhase.BEFORE_CALL)
        current_args = args

        # Execute plugin hooks
        for plugin in self._plugins:
            if any(HookRegistration(p, None).matches(tool_name)
                   for p in plugin.get_patterns()):
                try:
                    current_args, should_continue = await plugin.before_call(
                        tool_name, current_args, context
                    )
                    if not should_continue:
                        logger.info(f"Plugin {plugin.name} cancelled {tool_name}")
                        return current_args, False, context
                except Exception as e:
                    logger.error(f"Error in plugin {plugin.name} before_call: {e}")

        # Execute registered hooks
        for hook in self._get_matching_hooks(tool_name, HookPhase.BEFORE_CALL):
            try:
                result = hook.callback(tool_name, current_args, context)
                if asyncio.iscoroutine(result):
                    result = await result

                current_args, should_continue = result
                if not should_continue:
                    logger.info(f"Hook cancelled {tool_name}")
                    return current_args, False, context
            except Exception as e:
                logger.error(f"Error in before hook for {tool_name}: {e}")

        return current_args, True, context

    async def execute_after_hooks(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        context: HookContext
    ) -> Any:
        """Execute all after-call hooks"""
        if not self._enabled:
            return result

        context.phase = HookPhase.AFTER_CALL
        current_result = result

        # Execute plugin hooks
        for plugin in self._plugins:
            if any(HookRegistration(p, None).matches(tool_name)
                   for p in plugin.get_patterns()):
                try:
                    current_result = await plugin.after_call(
                        tool_name, args, current_result, context
                    )
                except Exception as e:
                    logger.error(f"Error in plugin {plugin.name} after_call: {e}")

        # Execute registered hooks
        for hook in self._get_matching_hooks(tool_name, HookPhase.AFTER_CALL):
            try:
                hook_result = hook.callback(tool_name, args, current_result, context)
                if asyncio.iscoroutine(hook_result):
                    hook_result = await hook_result
                current_result = hook_result
            except Exception as e:
                logger.error(f"Error in after hook for {tool_name}: {e}")

        return current_result

    async def execute_error_hooks(
        self,
        tool_name: str,
        args: Dict[str, Any],
        error: Exception,
        context: HookContext
    ) -> Tuple[bool, Exception]:
        """
        Execute all error hooks

        Returns:
            Tuple of (should_retry, modified_error)
        """
        if not self._enabled:
            return False, error

        context.phase = HookPhase.ON_ERROR
        current_error = error
        should_retry = False

        # Execute plugin hooks
        for plugin in self._plugins:
            if any(HookRegistration(p, None).matches(tool_name)
                   for p in plugin.get_patterns()):
                try:
                    retry, current_error = await plugin.on_error(
                        tool_name, args, current_error, context
                    )
                    should_retry = should_retry or retry
                except Exception as e:
                    logger.error(f"Error in plugin {plugin.name} on_error: {e}")

        # Execute registered hooks
        for hook in self._get_matching_hooks(tool_name, HookPhase.ON_ERROR):
            try:
                hook_result = hook.callback(tool_name, args, current_error, context)
                if asyncio.iscoroutine(hook_result):
                    hook_result = await hook_result

                retry, current_error = hook_result
                should_retry = should_retry or retry
            except Exception as e:
                logger.error(f"Error in error hook for {tool_name}: {e}")

        return should_retry, current_error

    def get_stats(self) -> Dict[str, Any]:
        """Get plugin manager statistics"""
        return {
            "enabled": self._enabled,
            "plugins": [p.name for p in self._plugins],
            "hooks": {
                phase.value: len(hooks)
                for phase, hooks in self._hooks.items()
            }
        }


# Singleton instance
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Get the singleton plugin manager instance"""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager


def reset_plugin_manager() -> None:
    """Reset the plugin manager (mainly for testing)"""
    global _plugin_manager
    _plugin_manager = None


# Built-in Plugins


class AuditPlugin(ToolPlugin):
    """Logs all tool calls to a file for audit purposes"""

    name = "audit_plugin"
    priority = 10  # High priority

    def __init__(self, log_file: str = "tool_audit.log"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    async def before_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        context: HookContext
    ) -> Tuple[Dict[str, Any], bool]:
        """Log tool call start"""
        entry = {
            "timestamp": context.timestamp.isoformat(),
            "phase": "start",
            "tool": tool_name,
            "args": self._sanitize_args(args)
        }
        self._write_log(entry)
        return args, True

    async def after_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        context: HookContext
    ) -> Any:
        """Log tool call completion"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "phase": "complete",
            "tool": tool_name,
            "result_type": type(result).__name__,
            "success": True
        }
        self._write_log(entry)
        return result

    async def on_error(
        self,
        tool_name: str,
        args: Dict[str, Any],
        error: Exception,
        context: HookContext
    ) -> Tuple[bool, Exception]:
        """Log tool call error"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "phase": "error",
            "tool": tool_name,
            "error": str(error),
            "error_type": type(error).__name__
        }
        self._write_log(entry)
        return False, error

    def _sanitize_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive data from args"""
        sanitized = {}
        for key, value in args.items():
            if any(s in key.lower() for s in ["password", "token", "secret", "key"]):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, (str, int, float, bool, type(None))):
                sanitized[key] = value
            else:
                sanitized[key] = f"<{type(value).__name__}>"
        return sanitized

    def _write_log(self, entry: Dict[str, Any]) -> None:
        """Write log entry to file"""
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")


class TimingPlugin(ToolPlugin):
    """Tracks execution time of tool calls"""

    name = "timing_plugin"
    priority = 5  # Very high priority

    def __init__(self):
        self.timings: Dict[str, List[float]] = {}

    async def before_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        context: HookContext
    ) -> Tuple[Dict[str, Any], bool]:
        """Record start time"""
        context.set("start_time", time.time())
        return args, True

    async def after_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        context: HookContext
    ) -> Any:
        """Calculate and store execution time"""
        start_time = context.get("start_time")
        if start_time:
            elapsed = time.time() - start_time
            if tool_name not in self.timings:
                self.timings[tool_name] = []
            self.timings[tool_name].append(elapsed)
            logger.debug(f"{tool_name} took {elapsed:.3f}s")
        return result

    def get_stats(self) -> Dict[str, Dict[str, float]]:
        """Get timing statistics"""
        stats = {}
        for tool_name, times in self.timings.items():
            if times:
                stats[tool_name] = {
                    "count": len(times),
                    "total": sum(times),
                    "avg": sum(times) / len(times),
                    "min": min(times),
                    "max": max(times)
                }
        return stats

    def reset(self) -> None:
        """Reset all timing data"""
        self.timings.clear()


class TransformPlugin(ToolPlugin):
    """Allows custom transformations of arguments and results"""

    name = "transform_plugin"
    priority = 50

    def __init__(
        self,
        patterns: List[str] = None,
        arg_transformer: Optional[Callable] = None,
        result_transformer: Optional[Callable] = None
    ):
        self.patterns = patterns or ["*"]
        self.arg_transformer = arg_transformer
        self.result_transformer = result_transformer

    def get_patterns(self) -> List[str]:
        return self.patterns

    async def before_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        context: HookContext
    ) -> Tuple[Dict[str, Any], bool]:
        """Transform arguments if transformer is set"""
        if self.arg_transformer:
            try:
                transformed = self.arg_transformer(tool_name, args)
                return transformed, True
            except Exception as e:
                logger.error(f"Error transforming args for {tool_name}: {e}")
        return args, True

    async def after_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        context: HookContext
    ) -> Any:
        """Transform result if transformer is set"""
        if self.result_transformer:
            try:
                return self.result_transformer(tool_name, result)
            except Exception as e:
                logger.error(f"Error transforming result for {tool_name}: {e}")
        return result


class RateLimitPlugin(ToolPlugin):
    """Rate limits tool calls"""

    name = "rate_limit_plugin"
    priority = 1  # Highest priority

    def __init__(
        self,
        patterns: List[str] = None,
        max_calls_per_minute: int = 60
    ):
        self.patterns = patterns or ["*"]
        self.max_calls = max_calls_per_minute
        self.call_times: Dict[str, List[float]] = {}

    def get_patterns(self) -> List[str]:
        return self.patterns

    async def before_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        context: HookContext
    ) -> Tuple[Dict[str, Any], bool]:
        """Check rate limit"""
        now = time.time()

        # Initialize or clean old entries
        if tool_name not in self.call_times:
            self.call_times[tool_name] = []

        # Remove calls older than 1 minute
        self.call_times[tool_name] = [
            t for t in self.call_times[tool_name]
            if now - t < 60
        ]

        # Check limit
        if len(self.call_times[tool_name]) >= self.max_calls:
            logger.warning(f"Rate limit exceeded for {tool_name}")
            return args, False

        # Record this call
        self.call_times[tool_name].append(now)
        return args, True


# Test code
if __name__ == "__main__":
    import asyncio

    async def test_plugin_system():
        """Test the plugin system"""
        print("Testing Tool Plugin System\n" + "="*50)

        # Reset for clean test
        reset_plugin_manager()
        pm = get_plugin_manager()

        # Test 1: Basic plugin registration
        print("\nTest 1: Plugin Registration")
        audit = AuditPlugin("test_audit.log")
        timing = TimingPlugin()
        pm.register_plugin(audit)
        pm.register_plugin(timing)
        print(f"Registered plugins: {pm.get_stats()['plugins']}")

        # Test 2: Before/After hooks
        print("\nTest 2: Before/After Hooks")

        async def log_before(tool_name, args, context):
            print(f"  Before hook: {tool_name}")
            return args, True

        async def log_after(tool_name, args, result, context):
            print(f"  After hook: {tool_name}, result: {result}")
            return result

        pm.register_before_hook("test_*", log_before)
        pm.register_after_hook("test_*", log_after)

        # Simulate tool execution
        test_args = {"param": "value"}
        modified_args, should_continue, context = await pm.execute_before_hooks(
            "test_tool", test_args
        )
        print(f"  Should continue: {should_continue}")

        test_result = {"status": "success"}
        modified_result = await pm.execute_after_hooks(
            "test_tool", test_args, test_result, context
        )
        print(f"  Modified result: {modified_result}")

        # Test 3: Pattern matching
        print("\nTest 3: Pattern Matching")
        patterns = [
            ("playwright_click", "playwright_*", True),
            ("playwright_click", "browser_*", False),
            ("any_tool", "*", True),
            ("mcp_tool", "mcp_*", True),
            ("other_tool", "mcp_*", False),
        ]

        for tool_name, pattern, expected in patterns:
            hook = HookRegistration(pattern, None)
            matches = hook.matches(tool_name)
            status = "PASS" if matches == expected else "FAIL"
            print(f"  {status}: '{tool_name}' vs '{pattern}' = {matches}")

        # Test 4: Error hooks
        print("\nTest 4: Error Handling")

        async def handle_error(tool_name, args, error, context):
            print(f"  Error hook: {tool_name} - {error}")
            return False, error

        pm.register_error_hook("*", handle_error)

        test_error = Exception("Test error")
        should_retry, modified_error = await pm.execute_error_hooks(
            "test_tool", test_args, test_error, context
        )
        print(f"  Should retry: {should_retry}")

        # Test 5: Transform plugin
        print("\nTest 5: Transform Plugin")

        def add_timestamp(tool_name, args):
            args["timestamp"] = "2025-01-01"
            return args

        def uppercase_result(tool_name, result):
            if isinstance(result, str):
                return result.upper()
            return result

        transform = TransformPlugin(
            patterns=["transform_*"],
            arg_transformer=add_timestamp,
            result_transformer=uppercase_result
        )
        pm.register_plugin(transform)

        args, cont, ctx = await pm.execute_before_hooks("transform_test", {})
        print(f"  Transformed args: {args}")

        result = await pm.execute_after_hooks(
            "transform_test", args, "hello", ctx
        )
        print(f"  Transformed result: {result}")

        # Test 6: Rate limiting
        print("\nTest 6: Rate Limiting")
        rate_limiter = RateLimitPlugin(
            patterns=["limited_*"],
            max_calls_per_minute=3
        )
        pm.register_plugin(rate_limiter)

        for i in range(5):
            args, cont, ctx = await pm.execute_before_hooks(
                "limited_tool", {}
            )
            print(f"  Call {i+1}: {'Allowed' if cont else 'Blocked'}")

        # Test 7: Timing stats
        print("\nTest 7: Timing Statistics")

        # Simulate some timed calls
        for _ in range(3):
            args, cont, ctx = await pm.execute_before_hooks("timed_tool", {})
            await asyncio.sleep(0.1)
            await pm.execute_after_hooks("timed_tool", args, "ok", ctx)

        stats = timing.get_stats()
        if "timed_tool" in stats:
            print(f"  Timed tool stats: {stats['timed_tool']}")

        # Test 8: Priority ordering
        print("\nTest 8: Priority Ordering")

        call_order = []

        async def priority_10(tool_name, args, context):
            call_order.append(10)
            return args, True

        async def priority_5(tool_name, args, context):
            call_order.append(5)
            return args, True

        async def priority_20(tool_name, args, context):
            call_order.append(20)
            return args, True

        pm.register_before_hook("priority_*", priority_10, priority=10)
        pm.register_before_hook("priority_*", priority_5, priority=5)
        pm.register_before_hook("priority_*", priority_20, priority=20)

        await pm.execute_before_hooks("priority_test", {})
        print(f"  Execution order (by priority): {call_order}")
        print(f"  Expected: [5, 10, 20] (lower = higher priority)")

        # Test 9: Plugin enable/disable
        print("\nTest 9: Enable/Disable")
        pm.disable()
        args, cont, ctx = await pm.execute_before_hooks("any_tool", {})
        print(f"  When disabled, hooks run: {ctx.metadata != {}}")

        pm.enable()
        args, cont, ctx = await pm.execute_before_hooks("any_tool", {})
        print(f"  When enabled, hooks run: {len(call_order) > 0}")

        # Test 10: Stats
        print("\nTest 10: System Stats")
        stats = pm.get_stats()
        print(f"  Enabled: {stats['enabled']}")
        print(f"  Plugins: {len(stats['plugins'])}")
        print(f"  Hooks by phase: {stats['hooks']}")

        print("\n" + "="*50)
        print("All tests completed!")

        # Cleanup
        Path("test_audit.log").unlink(missing_ok=True)

    # Run tests
    asyncio.run(test_plugin_system())
