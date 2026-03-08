"""
Structured Logger - JSON logging for debugging and analytics

Features:
- JSON formatted logs for easy parsing
- Correlation IDs for request tracing
- Performance timing built-in
- Log levels with filtering
- File rotation and compression
- Drop-in replacement for loguru

Usage:
    from agent.structured_logger import logger, with_correlation_id, timed

    # Basic logging
    logger.info("User logged in", user_id=123, ip="192.168.1.1")

    # With correlation ID
    with with_correlation_id("task-abc123"):
        logger.info("Starting task")
        logger.debug("Processing step 1")

    # Timed operations
    with logger.timed("database_query"):
        run_query()

    # Decorator
    @timed("fetch_data")
    async def fetch_data():
        ...

Migration from loguru:
    # Before:
    from loguru import logger
    logger.info("Hello")

    # After:
    from agent.structured_logger import logger
    logger.info("Hello")  # Same API!
"""

import asyncio
import gzip
import json
import os
import sys
import threading
import time
import traceback
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from enum import Enum
import uuid


class LogLevel(Enum):
    """Log levels matching standard logging conventions"""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50

    def __str__(self):
        return self.name


class LogSink:
    """Base class for log output destinations"""

    def write(self, record: Dict[str, Any]) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class ConsoleSink(LogSink):
    """Human-readable console output"""

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m',
        'BOLD': '\033[1m',
        'DIM': '\033[2m',
    }

    def __init__(self, use_colors: bool = True):
        self.use_colors = use_colors and sys.stdout.isatty()

    def write(self, record: Dict[str, Any]) -> None:
        """Write human-readable log to console"""
        level = record['level']
        timestamp = record['timestamp'][:19]  # Trim microseconds

        # Build message parts
        parts = []

        if self.use_colors:
            color = self.COLORS.get(level, '')
            reset = self.COLORS['RESET']
            dim = self.COLORS['DIM']
            bold = self.COLORS['BOLD']

            # Timestamp (dim)
            parts.append(f"{dim}{timestamp}{reset}")

            # Level (colored, bold)
            parts.append(f"{color}{bold}{level:8s}{reset}")

            # Component (if present)
            if record.get('component'):
                parts.append(f"{dim}[{record['component']}]{reset}")

            # Correlation ID (if present, dim)
            if record.get('correlation_id'):
                parts.append(f"{dim}({record['correlation_id'][:8]}){reset}")

            # Message
            parts.append(record['message'])

            # Duration (if present, dim)
            if record.get('duration_ms') is not None:
                parts.append(f"{dim}({record['duration_ms']:.1f}ms){reset}")
        else:
            # No colors
            parts.append(timestamp)
            parts.append(f"{level:8s}")
            if record.get('component'):
                parts.append(f"[{record['component']}]")
            if record.get('correlation_id'):
                parts.append(f"({record['correlation_id'][:8]})")
            parts.append(record['message'])
            if record.get('duration_ms') is not None:
                parts.append(f"({record['duration_ms']:.1f}ms)")

        print(' '.join(parts), file=sys.stdout, flush=True)

        # Print metadata if present (excluding standard fields)
        metadata = record.get('metadata', {})
        if metadata:
            excluded_keys = {'timestamp', 'level', 'message', 'component',
                           'correlation_id', 'duration_ms', 'success', 'action', 'tool'}
            filtered_meta = {k: v for k, v in metadata.items() if k not in excluded_keys}
            if filtered_meta:
                if self.use_colors:
                    print(f"  {self.COLORS['DIM']}{json.dumps(filtered_meta, indent=2)}{self.COLORS['RESET']}")
                else:
                    print(f"  {json.dumps(filtered_meta, indent=2)}")

        # Print exception if present
        if record.get('exception'):
            if self.use_colors:
                print(f"{self.COLORS['ERROR']}{record['exception']}{self.COLORS['RESET']}")
            else:
                print(record['exception'])


class JSONFileSink(LogSink):
    """JSON file output with rotation and compression"""

    def __init__(
        self,
        base_path: Union[str, Path],
        rotation_days: int = 1,
        retention_days: int = 7,
        compress_old: bool = True
    ):
        self.base_path = Path(base_path)
        self.base_path.parent.mkdir(parents=True, exist_ok=True)
        self.rotation_days = rotation_days
        self.retention_days = retention_days
        self.compress_old = compress_old

        self._current_file: Optional[Path] = None
        self._current_handle = None
        self._current_date: Optional[datetime] = None
        self._lock = threading.Lock()

    def _get_log_path(self, dt: datetime) -> Path:
        """Get log file path for a given date"""
        date_str = dt.strftime('%Y-%m-%d')
        return self.base_path.parent / f"{self.base_path.stem}-{date_str}.jsonl"

    def _rotate_if_needed(self, now: datetime) -> None:
        """Rotate log file if needed"""
        current_date = now.date()

        if self._current_date != current_date:
            # Close old file
            if self._current_handle:
                self._current_handle.close()

                # Compress old file if enabled
                if self.compress_old and self._current_file:
                    self._compress_file(self._current_file)

            # Open new file
            self._current_file = self._get_log_path(now)
            self._current_handle = open(self._current_file, 'a', encoding='utf-8')
            self._current_date = current_date

            # Clean old files
            self._clean_old_files(now)

    def _compress_file(self, file_path: Path) -> None:
        """Compress a log file with gzip"""
        try:
            gz_path = file_path.with_suffix('.jsonl.gz')
            with open(file_path, 'rb') as f_in:
                with gzip.open(gz_path, 'wb') as f_out:
                    f_out.writelines(f_in)
            file_path.unlink()  # Delete original
        except Exception as e:
            # Don't fail logging if compression fails
            print(f"Warning: Failed to compress {file_path}: {e}", file=sys.stderr)

    def _clean_old_files(self, now: datetime) -> None:
        """Delete files older than retention period"""
        try:
            cutoff = now - timedelta(days=self.retention_days)
            pattern = f"{self.base_path.stem}-*.jsonl*"

            for file_path in self.base_path.parent.glob(pattern):
                # Extract date from filename
                try:
                    date_str = file_path.stem.split('-')[-1]
                    if date_str.endswith('.jsonl'):
                        date_str = date_str[:-6]
                    file_date = datetime.strptime(date_str, '%Y-%m-%d')

                    if file_date < cutoff:
                        file_path.unlink()
                except (ValueError, IndexError):
                    # Skip files that don't match expected format
                    continue
        except Exception as e:
            print(f"Warning: Failed to clean old files: {e}", file=sys.stderr)

    def write(self, record: Dict[str, Any]) -> None:
        """Write JSON record to file"""
        with self._lock:
            # Handle timestamp with 'Z' suffix
            timestamp = record['timestamp'].replace('Z', '+00:00')
            now = datetime.fromisoformat(timestamp)
            self._rotate_if_needed(now)

            if self._current_handle:
                json.dump(record, self._current_handle)
                self._current_handle.write('\n')
                self._current_handle.flush()

    def close(self) -> None:
        """Close file handle"""
        with self._lock:
            if self._current_handle:
                self._current_handle.close()
                self._current_handle = None


class WebhookSink(LogSink):
    """Send logs to remote webhook (non-blocking)"""

    def __init__(self, url: str, batch_size: int = 10, flush_interval: float = 5.0):
        self.url = url
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._buffer: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._last_flush = time.time()

    def write(self, record: Dict[str, Any]) -> None:
        """Buffer record and flush if needed"""
        with self._lock:
            self._buffer.append(record)

            should_flush = (
                len(self._buffer) >= self.batch_size or
                time.time() - self._last_flush >= self.flush_interval
            )

            if should_flush:
                self._flush()

    def _flush(self) -> None:
        """Send buffered records to webhook (async, non-blocking)"""
        if not self._buffer:
            return

        records = self._buffer[:]
        self._buffer.clear()
        self._last_flush = time.time()

        # Send asynchronously in background thread
        threading.Thread(target=self._send, args=(records,), daemon=True).start()

    def _send(self, records: List[Dict[str, Any]]) -> None:
        """Actually send records to webhook"""
        try:
            import requests
            response = requests.post(
                self.url,
                json={'logs': records},
                timeout=5.0
            )
            response.raise_for_status()
        except Exception as e:
            # Don't fail logging if webhook fails
            print(f"Warning: Failed to send logs to webhook: {e}", file=sys.stderr)

    def close(self) -> None:
        """Flush remaining records"""
        with self._lock:
            self._flush()


class PerformanceTracker:
    """Track performance metrics with percentiles"""

    def __init__(self):
        self._timings: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def record(self, operation: str, duration_ms: float) -> None:
        """Record a timing"""
        with self._lock:
            self._timings[operation].append(duration_ms)

            # Keep last 1000 samples per operation to avoid unbounded growth
            if len(self._timings[operation]) > 1000:
                self._timings[operation] = self._timings[operation][-1000:]

    def get_stats(self, operation: str) -> Optional[Dict[str, float]]:
        """Get percentile stats for an operation"""
        with self._lock:
            timings = self._timings.get(operation)
            if not timings:
                return None

            sorted_timings = sorted(timings)
            count = len(sorted_timings)

            return {
                'count': count,
                'min': sorted_timings[0],
                'max': sorted_timings[-1],
                'mean': sum(sorted_timings) / count,
                'p50': sorted_timings[int(count * 0.5)],
                'p95': sorted_timings[int(count * 0.95)],
                'p99': sorted_timings[int(count * 0.99)],
            }

    def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        """Get stats for all operations"""
        with self._lock:
            return {op: self.get_stats(op) for op in self._timings.keys()}


class StructuredLogger:
    """
    Structured logger with JSON output, correlation IDs, and performance tracking.

    Drop-in replacement for loguru.logger with enhanced features.
    """

    def __init__(self):
        self.sinks: List[LogSink] = []
        self.min_level = LogLevel.DEBUG
        self.component_filters: Set[str] = set()  # Empty = log all
        self.correlation_id_filters: Set[str] = set()  # Empty = log all

        # Thread-local storage for correlation ID
        self._local = threading.local()

        # Performance tracking
        self.perf_tracker = PerformanceTracker()

        # Default sinks
        self.add_console_sink()

    def add_console_sink(self, use_colors: bool = True) -> "StructuredLogger":
        """Add console sink for human-readable output"""
        self.sinks.append(ConsoleSink(use_colors=use_colors))
        return self

    def add_json_file_sink(
        self,
        base_path: Union[str, Path],
        rotation_days: int = 1,
        retention_days: int = 7,
        compress_old: bool = True
    ) -> "StructuredLogger":
        """Add JSON file sink with rotation"""
        self.sinks.append(JSONFileSink(
            base_path=base_path,
            rotation_days=rotation_days,
            retention_days=retention_days,
            compress_old=compress_old
        ))
        return self

    def add_webhook_sink(
        self,
        url: str,
        batch_size: int = 10,
        flush_interval: float = 5.0
    ) -> "StructuredLogger":
        """Add webhook sink for remote logging"""
        self.sinks.append(WebhookSink(
            url=url,
            batch_size=batch_size,
            flush_interval=flush_interval
        ))
        return self

    def set_level(self, level: Union[str, LogLevel]) -> "StructuredLogger":
        """Set minimum log level"""
        if isinstance(level, str):
            level = LogLevel[level.upper()]
        self.min_level = level
        return self

    def filter_components(self, *components: str) -> "StructuredLogger":
        """Only log from specific components (empty = log all)"""
        self.component_filters = set(components)
        return self

    def filter_correlation_ids(self, *correlation_ids: str) -> "StructuredLogger":
        """Only log specific correlation IDs (empty = log all)"""
        self.correlation_id_filters = set(correlation_ids)
        return self

    def _get_correlation_id(self) -> Optional[str]:
        """Get current correlation ID from thread-local storage"""
        return getattr(self._local, 'correlation_id', None)

    def _set_correlation_id(self, correlation_id: Optional[str]) -> None:
        """Set correlation ID in thread-local storage"""
        self._local.correlation_id = correlation_id

    def _should_log(self, level: LogLevel, component: Optional[str]) -> bool:
        """Check if log should be written based on filters"""
        # Level filter
        if level.value < self.min_level.value:
            return False

        # Component filter
        if self.component_filters and component not in self.component_filters:
            return False

        # Correlation ID filter
        correlation_id = self._get_correlation_id()
        if self.correlation_id_filters and correlation_id not in self.correlation_id_filters:
            return False

        return True

    def _log(
        self,
        level: LogLevel,
        message: str,
        component: Optional[str] = None,
        action: Optional[str] = None,
        tool: Optional[str] = None,
        duration_ms: Optional[float] = None,
        success: Optional[bool] = None,
        exception: Optional[Exception] = None,
        **metadata: Any
    ) -> None:
        """Internal logging method"""
        if not self._should_log(level, component):
            return

        # Build record
        record = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': str(level),
            'message': message,
        }

        # Add optional fields
        if component:
            record['component'] = component

        correlation_id = self._get_correlation_id()
        if correlation_id:
            record['correlation_id'] = correlation_id

        if action:
            record['action'] = action

        if tool:
            record['tool'] = tool

        if duration_ms is not None:
            record['duration_ms'] = duration_ms

        if success is not None:
            record['success'] = success

        if exception:
            record['exception'] = ''.join(traceback.format_exception(
                type(exception), exception, exception.__traceback__
            ))

        if metadata:
            record['metadata'] = metadata

        # Write to all sinks
        for sink in self.sinks:
            try:
                sink.write(record)
            except Exception as e:
                # Don't fail logging if a sink fails
                print(f"Error writing to sink: {e}", file=sys.stderr)

    # Public API (loguru-compatible)

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message"""
        self._log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        """Log info message"""
        self._log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message"""
        self._log(LogLevel.WARNING, message, **kwargs)

    def warn(self, message: str, **kwargs) -> None:
        """Alias for warning()"""
        self.warning(message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        """Log error message"""
        self._log(LogLevel.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs) -> None:
        """Log critical message"""
        self._log(LogLevel.CRITICAL, message, **kwargs)

    def exception(self, message: str, **kwargs) -> None:
        """Log exception with traceback"""
        exc_info = sys.exc_info()
        if exc_info[1]:
            kwargs['exception'] = exc_info[1]
        self._log(LogLevel.ERROR, message, **kwargs)

    @contextmanager
    def timed(self, operation: str, component: Optional[str] = None, **metadata: Any):
        """
        Context manager for timing operations.

        Usage:
            with logger.timed("database_query", component="db"):
                run_query()
        """
        start = time.perf_counter()
        success = True
        exception = None

        try:
            yield
        except Exception as e:
            success = False
            exception = e
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000

            # Record performance
            self.perf_tracker.record(operation, duration_ms)

            # Log
            self._log(
                LogLevel.INFO if success else LogLevel.ERROR,
                f"Operation: {operation}",
                component=component,
                action=operation,
                duration_ms=duration_ms,
                success=success,
                exception=exception,
                **metadata
            )

    def get_performance_stats(self, operation: Optional[str] = None) -> Union[Dict, None]:
        """
        Get performance statistics.

        Args:
            operation: Specific operation name, or None for all operations

        Returns:
            Stats dict or dict of stats
        """
        if operation:
            return self.perf_tracker.get_stats(operation)
        return self.perf_tracker.get_all_stats()

    def close(self) -> None:
        """Close all sinks"""
        for sink in self.sinks:
            try:
                sink.close()
            except Exception as e:
                print(f"Error closing sink: {e}", file=sys.stderr)


# Global logger instance
logger = StructuredLogger()


# Context managers and decorators

@contextmanager
def with_correlation_id(correlation_id: Optional[str] = None):
    """
    Context manager to set correlation ID for all logs in scope.

    Usage:
        with with_correlation_id("task-123"):
            logger.info("Starting task")  # Will include correlation_id
            do_work()
            logger.info("Task complete")  # Will include same correlation_id

    Args:
        correlation_id: ID to use, or None to generate a new UUID
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    old_id = logger._get_correlation_id()
    logger._set_correlation_id(correlation_id)

    try:
        yield correlation_id
    finally:
        logger._set_correlation_id(old_id)


def timed(operation: str, component: Optional[str] = None, **metadata: Any):
    """
    Decorator for timing functions.

    Usage:
        @timed("fetch_user", component="api")
        async def fetch_user(user_id: int):
            ...
    """
    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                with logger.timed(operation, component=component, **metadata):
                    return await func(*args, **kwargs)
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                with logger.timed(operation, component=component, **metadata):
                    return func(*args, **kwargs)
            return sync_wrapper

    return decorator


def logged(
    level: str = "INFO",
    component: Optional[str] = None,
    log_args: bool = False,
    log_result: bool = False
):
    """
    Decorator for auto-logging function calls.

    Usage:
        @logged("INFO", component="api", log_args=True)
        async def fetch_user(user_id: int):
            ...
    """
    def decorator(func: Callable) -> Callable:
        func_name = func.__name__
        log_level = LogLevel[level.upper()]

        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                # Log call
                metadata = {}
                if log_args:
                    metadata['args'] = args
                    metadata['kwargs'] = kwargs

                logger._log(
                    log_level,
                    f"Calling {func_name}",
                    component=component,
                    action="function_call",
                    **metadata
                )

                # Execute
                try:
                    result = await func(*args, **kwargs)

                    # Log success
                    result_metadata = {}
                    if log_result:
                        result_metadata['result'] = result

                    logger._log(
                        log_level,
                        f"Completed {func_name}",
                        component=component,
                        action="function_complete",
                        success=True,
                        **result_metadata
                    )

                    return result
                except Exception as e:
                    # Log error
                    logger._log(
                        LogLevel.ERROR,
                        f"Failed {func_name}",
                        component=component,
                        action="function_error",
                        success=False,
                        exception=e
                    )
                    raise

            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                # Log call
                metadata = {}
                if log_args:
                    metadata['args'] = args
                    metadata['kwargs'] = kwargs

                logger._log(
                    log_level,
                    f"Calling {func_name}",
                    component=component,
                    action="function_call",
                    **metadata
                )

                # Execute
                try:
                    result = func(*args, **kwargs)

                    # Log success
                    result_metadata = {}
                    if log_result:
                        result_metadata['result'] = result

                    logger._log(
                        log_level,
                        f"Completed {func_name}",
                        component=component,
                        action="function_complete",
                        success=True,
                        **result_metadata
                    )

                    return result
                except Exception as e:
                    # Log error
                    logger._log(
                        LogLevel.ERROR,
                        f"Failed {func_name}",
                        component=component,
                        action="function_error",
                        success=False,
                        exception=e
                    )
                    raise

            return sync_wrapper

    return decorator


# Configuration helper

def configure_logger(
    level: str = "INFO",
    log_dir: Optional[Union[str, Path]] = None,
    console: bool = True,
    json_file: bool = True,
    webhook_url: Optional[str] = None,
    component_filter: Optional[List[str]] = None,
    **kwargs
) -> StructuredLogger:
    """
    Configure the global logger with common settings.

    Args:
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files (default: ./logs)
        console: Enable console output
        json_file: Enable JSON file output
        webhook_url: Optional webhook URL for remote logging
        component_filter: List of components to log (None = log all)
        **kwargs: Additional sink configuration

    Returns:
        Configured logger instance
    """
    # Clear existing sinks
    logger.sinks.clear()

    # Set level
    logger.set_level(level)

    # Add console sink
    if console:
        logger.add_console_sink(use_colors=kwargs.get('use_colors', True))

    # Add JSON file sink
    if json_file:
        if log_dir is None:
            log_dir = Path.cwd() / "logs"
        else:
            log_dir = Path(log_dir)

        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add_json_file_sink(
            base_path=log_dir / "eversale.jsonl",
            rotation_days=kwargs.get('rotation_days', 1),
            retention_days=kwargs.get('retention_days', 7),
            compress_old=kwargs.get('compress_old', True)
        )

    # Add webhook sink
    if webhook_url:
        logger.add_webhook_sink(
            url=webhook_url,
            batch_size=kwargs.get('webhook_batch_size', 10),
            flush_interval=kwargs.get('webhook_flush_interval', 5.0)
        )

    # Set component filter
    if component_filter:
        logger.filter_components(*component_filter)

    return logger


# Module cleanup
def shutdown():
    """Shutdown logger and flush all sinks"""
    logger.close()


# Register cleanup on exit
import atexit
atexit.register(shutdown)


if __name__ == '__main__':
    # Demo usage
    configure_logger(level='DEBUG', log_dir='./demo_logs')

    logger.info("Structured logger demo", component="demo", version="1.0")

    with with_correlation_id("demo-123"):
        logger.debug("Starting task", component="demo", task_id=1)

        with logger.timed("slow_operation", component="demo"):
            time.sleep(0.1)

        logger.info("Task progress", component="demo", progress=0.5)

        try:
            raise ValueError("Demo error")
        except Exception:
            logger.exception("Task failed", component="demo")

    # Show performance stats
    stats = logger.get_performance_stats()
    print("\nPerformance Stats:")
    print(json.dumps(stats, indent=2))
