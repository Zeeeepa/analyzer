"""
Stateful tool wrappers with guardrails for making small LLMs behave sanely.

Based on Reddit LocalLLaMA research: the idea is to make small models "smarter"
by having the tool layer quietly handle bad decisions through validation,
retry logic, and failure tracking.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from functools import wraps
import hashlib
import json
import re


class ToolStatus(Enum):
    """Status of a tool in the registry."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    LOCKED = "locked"


@dataclass
class ToolResult:
    """Result from a tool execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    cached: bool = False
    retries: int = 0


@dataclass
class ValidationRule:
    """A validation rule for tool parameters."""
    param_name: str
    validator: Callable[[Any], bool]
    error_message: str


class ToolValidator:
    """Common validators for tool parameters."""

    @staticmethod
    def is_valid_css_selector(selector: str) -> bool:
        """Check if CSS selector is reasonable."""
        if not selector or not isinstance(selector, str):
            return False
        if len(selector) > 500:  # Unreasonably long
            return False
        # Basic sanity check - should start with valid CSS selector chars
        if not re.match(r'^[#.\w\[\]:>~+*\s-]', selector):
            return False
        return True

    @staticmethod
    def is_valid_timeout(timeout: float) -> bool:
        """Check if timeout is reasonable (0.1s to 300s)."""
        if not isinstance(timeout, (int, float)):
            return False
        return 0.1 <= timeout <= 300

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Check if URL is reasonable."""
        if not url or not isinstance(url, str):
            return False
        if len(url) > 2048:  # Max reasonable URL length
            return False
        # Must start with http:// or https://
        if not re.match(r'^https?://', url, re.IGNORECASE):
            return False
        return True

    @staticmethod
    def is_valid_page_range(start: int, end: int, max_pages: int = 1000) -> bool:
        """Check if page range is reasonable."""
        if not isinstance(start, int) or not isinstance(end, int):
            return False
        if start < 0 or end < 0:
            return False
        if end < start:
            return False
        if (end - start) > max_pages:
            return False
        return True

    @staticmethod
    def is_valid_path(path: str) -> bool:
        """Check if file path is reasonable."""
        if not path or not isinstance(path, str):
            return False
        if len(path) > 4096:  # Max reasonable path length
            return False
        # Check for obviously malicious patterns
        malicious_patterns = ['../', '..\\', '~/', '/etc/passwd', 'null', '\x00']
        path_lower = path.lower()
        if any(pattern in path_lower for pattern in malicious_patterns):
            return False
        return True

    @staticmethod
    def is_valid_string_length(s: str, min_len: int = 0, max_len: int = 10000) -> bool:
        """Check if string length is reasonable."""
        if not isinstance(s, str):
            return False
        return min_len <= len(s) <= max_len

    @staticmethod
    def is_valid_retry_count(count: int) -> bool:
        """Check if retry count is reasonable."""
        if not isinstance(count, int):
            return False
        return 0 <= count <= 10

    @staticmethod
    def is_positive_number(n: Any) -> bool:
        """Check if value is a positive number."""
        if not isinstance(n, (int, float)):
            return False
        return n > 0

    @staticmethod
    def is_valid_dict(d: Any) -> bool:
        """Check if value is a dictionary."""
        return isinstance(d, dict)


class CacheEntry:
    """Cache entry with TTL support."""

    def __init__(self, result: ToolResult, ttl_seconds: float):
        self.result = result
        self.timestamp = time.time()
        self.ttl_seconds = ttl_seconds

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return (time.time() - self.timestamp) > self.ttl_seconds


class ToolCache:
    """Simple cache for tool results."""

    def __init__(self, max_size: int = 100, default_ttl: float = 300):
        self.cache: Dict[str, CacheEntry] = {}
        self.max_size = max_size
        self.default_ttl = default_ttl

    def _make_key(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Create cache key from tool name and arguments."""
        # Sort args for consistent hashing
        sorted_args = json.dumps(args, sort_keys=True)
        key_str = f"{tool_name}:{sorted_args}"
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(self, tool_name: str, args: Dict[str, Any]) -> Optional[ToolResult]:
        """Get cached result if available and not expired."""
        key = self._make_key(tool_name, args)
        entry = self.cache.get(key)

        if entry is None:
            return None

        if entry.is_expired():
            del self.cache[key]
            return None

        # Mark result as cached
        cached_result = ToolResult(
            success=entry.result.success,
            data=entry.result.data,
            error=entry.result.error,
            cached=True,
            retries=0
        )
        return cached_result

    def set(self, tool_name: str, args: Dict[str, Any], result: ToolResult, ttl: Optional[float] = None):
        """Store result in cache."""
        # Don't cache failures
        if not result.success:
            return

        key = self._make_key(tool_name, args)

        # Evict oldest entry if cache is full
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k].timestamp)
            del self.cache[oldest_key]

        ttl = ttl or self.default_ttl
        self.cache[key] = CacheEntry(result, ttl)

    def clear(self):
        """Clear all cache entries."""
        self.cache.clear()

    def invalidate(self, tool_name: str):
        """Invalidate all cache entries for a specific tool."""
        keys_to_delete = [
            key for key in self.cache.keys()
            if key.startswith(hashlib.sha256(f"{tool_name}:".encode()).hexdigest()[:8])
        ]
        for key in keys_to_delete:
            del self.cache[key]


class ToolWrapper:
    """
    Stateful wrapper that makes small LLMs behave sanely.

    Features:
    - Parameter validation with custom rules
    - Automatic retry with exponential backoff
    - Failure tracking and status management
    - Tool lockout after repeated failures
    - Result caching for repeated calls
    """

    def __init__(
        self,
        tool_fn: Callable,
        name: str,
        validation_rules: Optional[List[ValidationRule]] = None,
        max_retries: int = 3,
        base_backoff: float = 1.0,
        failure_threshold: int = 5,
        lockout_duration: float = 60.0,
        cache_ttl: Optional[float] = None,
        cacheable: bool = True
    ):
        self.tool_fn = tool_fn
        self.name = name
        self.validation_rules = validation_rules or []
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.failure_threshold = failure_threshold
        self.lockout_duration = lockout_duration
        self.cache_ttl = cache_ttl
        self.cacheable = cacheable

        # State tracking
        self.failure_count = 0
        self.success_count = 0
        self.status = ToolStatus.HEALTHY
        self.last_error: Optional[str] = None
        self.lockout_until: Optional[float] = None
        self.failure_history: List[tuple[float, str]] = []  # (timestamp, error)

    def _validate_args(self, args: Dict[str, Any]) -> Optional[str]:
        """
        Validate arguments against defined rules.
        Returns error message if validation fails, None if valid.
        """
        for rule in self.validation_rules:
            param_value = args.get(rule.param_name)
            if param_value is None:
                continue  # Skip validation for missing optional params

            try:
                if not rule.validator(param_value):
                    return f"{rule.param_name}: {rule.error_message}"
            except Exception as e:
                return f"{rule.param_name}: validation error - {str(e)}"

        return None

    def _check_status(self) -> Optional[str]:
        """
        Check if tool is available for use.
        Returns error message if unavailable, None if available.
        """
        if self.status == ToolStatus.LOCKED:
            if self.lockout_until and time.time() < self.lockout_until:
                remaining = int(self.lockout_until - time.time())
                return f"Tool '{self.name}' is locked out (retry in {remaining}s)"
            else:
                # Lockout expired, reset to degraded
                self._reset_lockout()

        return None

    def _reset_lockout(self):
        """Reset lockout and downgrade to degraded status."""
        self.status = ToolStatus.DEGRADED
        self.lockout_until = None
        self.failure_count = 0
        self.failure_history.clear()

    def _record_failure(self, error: str):
        """Record a failure and update tool status."""
        self.failure_count += 1
        self.last_error = error
        self.failure_history.append((time.time(), error))

        # Keep only recent failures (last 10 minutes)
        cutoff_time = time.time() - 600
        self.failure_history = [
            (ts, err) for ts, err in self.failure_history
            if ts > cutoff_time
        ]

        # Update status based on failure count
        if self.failure_count >= self.failure_threshold:
            self.status = ToolStatus.LOCKED
            self.lockout_until = time.time() + self.lockout_duration
        elif self.failure_count >= self.failure_threshold // 2:
            self.status = ToolStatus.DEGRADED

    def _record_success(self):
        """Record a success and potentially improve tool status."""
        self.success_count += 1

        # Gradually recover from degraded state
        if self.status == ToolStatus.DEGRADED:
            self.failure_count = max(0, self.failure_count - 1)
            if self.failure_count == 0:
                self.status = ToolStatus.HEALTHY
                self.last_error = None

    async def call(self, cache: Optional[ToolCache] = None, **args) -> ToolResult:
        """
        Execute the tool with guardrails.

        Args:
            cache: Optional cache instance for result caching
            **args: Tool arguments

        Returns:
            ToolResult with execution outcome
        """
        # Check if tool is available
        status_error = self._check_status()
        if status_error:
            return ToolResult(success=False, error=status_error)

        # Validate arguments
        validation_error = self._validate_args(args)
        if validation_error:
            error_msg = f"Invalid arguments: {validation_error}"
            self._record_failure(error_msg)
            return ToolResult(success=False, error=error_msg)

        # Check cache
        if cache and self.cacheable:
            cached_result = cache.get(self.name, args)
            if cached_result:
                return cached_result

        # Execute with retry logic
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                # Execute tool function (supports both sync and async)
                if asyncio.iscoroutinefunction(self.tool_fn):
                    result_data = await self.tool_fn(**args)
                else:
                    result_data = self.tool_fn(**args)

                # Success!
                self._record_success()
                result = ToolResult(
                    success=True,
                    data=result_data,
                    retries=attempt
                )

                # Cache successful result
                if cache and self.cacheable:
                    cache.set(self.name, args, result, self.cache_ttl)

                return result

            except Exception as e:
                last_exception = e

                # Don't retry on validation/argument errors
                if isinstance(e, (TypeError, ValueError)):
                    error_msg = f"Argument error: {str(e)}"
                    self._record_failure(error_msg)
                    return ToolResult(
                        success=False,
                        error=error_msg,
                        retries=attempt
                    )

                # Retry with exponential backoff
                if attempt < self.max_retries:
                    backoff_time = self.base_backoff * (2 ** attempt)
                    await asyncio.sleep(backoff_time)

        # All retries exhausted
        error_msg = f"Failed after {self.max_retries} retries: {str(last_exception)}"
        self._record_failure(error_msg)
        return ToolResult(
            success=False,
            error=error_msg,
            retries=self.max_retries
        )

    def get_status_info(self) -> Dict[str, Any]:
        """Get detailed status information about this tool."""
        return {
            "name": self.name,
            "status": self.status.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_error": self.last_error,
            "locked_until": self.lockout_until,
            "recent_failures": len(self.failure_history)
        }


class ToolRegistry:
    """
    Registry of wrapped tools with status tracking.

    Provides centralized management of tool wrappers including:
    - Tool registration and lookup
    - Status tracking across all tools
    - Cache management
    - Bulk status queries
    """

    def __init__(self, cache_size: int = 100, default_cache_ttl: float = 300):
        self.tools: Dict[str, ToolWrapper] = {}
        self.cache = ToolCache(max_size=cache_size, default_ttl=default_cache_ttl)

    def register(
        self,
        name: str,
        tool_fn: Callable,
        validation_rules: Optional[List[ValidationRule]] = None,
        **wrapper_kwargs
    ) -> ToolWrapper:
        """
        Register a new tool with the registry.

        Args:
            name: Tool name
            tool_fn: Tool function to wrap
            validation_rules: Optional validation rules
            **wrapper_kwargs: Additional arguments for ToolWrapper

        Returns:
            The created ToolWrapper instance
        """
        wrapper = ToolWrapper(
            tool_fn=tool_fn,
            name=name,
            validation_rules=validation_rules,
            **wrapper_kwargs
        )
        self.tools[name] = wrapper
        return wrapper

    def get(self, name: str) -> Optional[ToolWrapper]:
        """Get a tool wrapper by name."""
        return self.tools.get(name)

    async def call(self, name: str, **args) -> ToolResult:
        """
        Call a tool by name with arguments.

        Args:
            name: Tool name
            **args: Tool arguments

        Returns:
            ToolResult with execution outcome
        """
        wrapper = self.tools.get(name)
        if not wrapper:
            return ToolResult(
                success=False,
                error=f"Tool '{name}' not found in registry"
            )

        return await wrapper.call(cache=self.cache, **args)

    def get_available_tools(self) -> List[str]:
        """Return list of tools that aren't locked out."""
        return [
            name for name, wrapper in self.tools.items()
            if wrapper.status != ToolStatus.LOCKED or
            (wrapper.lockout_until and time.time() >= wrapper.lockout_until)
        ]

    def get_all_tools(self) -> List[str]:
        """Return list of all registered tools."""
        return list(self.tools.keys())

    def get_tools_by_status(self, status: ToolStatus) -> List[str]:
        """Return list of tools with specific status."""
        return [
            name for name, wrapper in self.tools.items()
            if wrapper.status == status
        ]

    def mark_degraded(self, tool_name: str):
        """Manually mark a tool as degraded."""
        wrapper = self.tools.get(tool_name)
        if wrapper:
            wrapper.status = ToolStatus.DEGRADED

    def mark_healthy(self, tool_name: str):
        """Manually mark a tool as healthy and reset failures."""
        wrapper = self.tools.get(tool_name)
        if wrapper:
            wrapper.status = ToolStatus.HEALTHY
            wrapper.failure_count = 0
            wrapper.last_error = None
            wrapper.lockout_until = None
            wrapper.failure_history.clear()

    def get_status_summary(self) -> Dict[str, Any]:
        """Get summary of all tool statuses."""
        summary = {
            "total_tools": len(self.tools),
            "healthy": 0,
            "degraded": 0,
            "locked": 0,
            "tools": {}
        }

        for name, wrapper in self.tools.items():
            status_info = wrapper.get_status_info()
            summary["tools"][name] = status_info

            if wrapper.status == ToolStatus.HEALTHY:
                summary["healthy"] += 1
            elif wrapper.status == ToolStatus.DEGRADED:
                summary["degraded"] += 1
            elif wrapper.status == ToolStatus.LOCKED:
                summary["locked"] += 1

        return summary

    def clear_cache(self):
        """Clear the entire tool result cache."""
        self.cache.clear()

    def invalidate_tool_cache(self, tool_name: str):
        """Invalidate cache entries for a specific tool."""
        self.cache.invalidate(tool_name)


# Decorator for easy tool wrapping
def wrapped_tool(
    name: str,
    validation_rules: Optional[List[ValidationRule]] = None,
    **wrapper_kwargs
):
    """
    Decorator to automatically wrap a function as a tool.

    Usage:
        @wrapped_tool("my_tool", validation_rules=[...])
        async def my_tool(arg1: str, arg2: int):
            # Tool implementation
            return result
    """
    def decorator(func: Callable) -> Callable:
        wrapper = ToolWrapper(
            tool_fn=func,
            name=name,
            validation_rules=validation_rules,
            **wrapper_kwargs
        )

        @wraps(func)
        async def wrapped(**args):
            return await wrapper.call(**args)

        # Attach wrapper for introspection
        wrapped._tool_wrapper = wrapper
        return wrapped

    return decorator


# Pre-built validation rule sets for common tool types
class CommonValidationRules:
    """Common validation rule sets for typical tool categories."""

    @staticmethod
    def browser_navigation() -> List[ValidationRule]:
        """Validation rules for browser navigation tools."""
        return [
            ValidationRule(
                param_name="url",
                validator=ToolValidator.is_valid_url,
                error_message="Invalid URL format"
            ),
            ValidationRule(
                param_name="timeout",
                validator=ToolValidator.is_valid_timeout,
                error_message="Timeout must be between 0.1 and 300 seconds"
            )
        ]

    @staticmethod
    def browser_interaction() -> List[ValidationRule]:
        """Validation rules for browser interaction tools."""
        return [
            ValidationRule(
                param_name="selector",
                validator=ToolValidator.is_valid_css_selector,
                error_message="Invalid CSS selector"
            ),
            ValidationRule(
                param_name="timeout",
                validator=ToolValidator.is_valid_timeout,
                error_message="Timeout must be between 0.1 and 300 seconds"
            )
        ]

    @staticmethod
    def file_operations() -> List[ValidationRule]:
        """Validation rules for file operation tools."""
        return [
            ValidationRule(
                param_name="path",
                validator=ToolValidator.is_valid_path,
                error_message="Invalid file path"
            ),
            ValidationRule(
                param_name="file_path",
                validator=ToolValidator.is_valid_path,
                error_message="Invalid file path"
            )
        ]

    @staticmethod
    def api_calls() -> List[ValidationRule]:
        """Validation rules for API call tools."""
        return [
            ValidationRule(
                param_name="url",
                validator=ToolValidator.is_valid_url,
                error_message="Invalid API URL"
            ),
            ValidationRule(
                param_name="timeout",
                validator=ToolValidator.is_valid_timeout,
                error_message="Timeout must be between 0.1 and 300 seconds"
            ),
            ValidationRule(
                param_name="retries",
                validator=ToolValidator.is_valid_retry_count,
                error_message="Retry count must be between 0 and 10"
            )
        ]
