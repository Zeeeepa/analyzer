"""
Test suite for structured_logger.py

Run: python -m pytest agent/test_structured_logger.py -v
Or: python agent/test_structured_logger.py
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path

import pytest

from agent.structured_logger import (
    StructuredLogger,
    configure_logger,
    logger,
    with_correlation_id,
    timed,
    logged,
    LogLevel,
    ConsoleSink,
    JSONFileSink,
)


def test_basic_logging():
    """Test basic logging methods"""
    test_logger = StructuredLogger()
    test_logger.sinks.clear()  # Remove default sinks

    # Capture logs
    logs = []

    class TestSink:
        def write(self, record):
            logs.append(record)

    test_logger.sinks.append(TestSink())

    # Log at different levels
    test_logger.debug("Debug message")
    test_logger.info("Info message")
    test_logger.warning("Warning message")
    test_logger.error("Error message")
    test_logger.critical("Critical message")

    assert len(logs) == 5
    assert logs[0]['level'] == 'DEBUG'
    assert logs[1]['level'] == 'INFO'
    assert logs[2]['level'] == 'WARNING'
    assert logs[3]['level'] == 'ERROR'
    assert logs[4]['level'] == 'CRITICAL'


def test_metadata():
    """Test structured metadata"""
    test_logger = StructuredLogger()
    test_logger.sinks.clear()

    logs = []

    class TestSink:
        def write(self, record):
            logs.append(record)

    test_logger.sinks.append(TestSink())

    test_logger.info(
        "User action",
        component="auth",
        user_id=123,
        action="login",
        ip="192.168.1.1"
    )

    assert len(logs) == 1
    record = logs[0]
    assert record['component'] == 'auth'
    assert record['action'] == 'login'
    assert record['metadata']['user_id'] == 123
    assert record['metadata']['ip'] == '192.168.1.1'


def test_correlation_id():
    """Test correlation ID context manager"""
    # Use global logger to test correlation ID context manager
    logs = []

    class TestSink:
        def write(self, record):
            logs.append(record)

    # Temporarily replace sinks
    old_sinks = logger.sinks[:]
    logger.sinks.clear()
    logger.sinks.append(TestSink())

    try:
        # Without correlation ID
        logger.info("Message 1")
        assert 'correlation_id' not in logs[0]

        # With correlation ID
        with with_correlation_id("test-123"):
            logger.info("Message 2")
            logger.info("Message 3")

        assert logs[1]['correlation_id'] == "test-123"
        assert logs[2]['correlation_id'] == "test-123"

        # After context
        logger.info("Message 4")
        assert 'correlation_id' not in logs[3]
    finally:
        # Restore original sinks
        logger.sinks = old_sinks


def test_timed_context_manager():
    """Test timed context manager"""
    test_logger = StructuredLogger()
    test_logger.sinks.clear()

    logs = []

    class TestSink:
        def write(self, record):
            logs.append(record)

    test_logger.sinks.append(TestSink())

    with test_logger.timed("slow_operation", component="test"):
        time.sleep(0.01)  # 10ms

    assert len(logs) == 1
    record = logs[0]
    assert record['action'] == 'slow_operation'
    assert record['component'] == 'test'
    assert record['duration_ms'] >= 10.0
    assert record['success'] is True


def test_timed_decorator_sync():
    """Test timed decorator on sync function"""
    logs = []

    class TestSink:
        def write(self, record):
            logs.append(record)

    # Temporarily replace sinks
    old_sinks = logger.sinks[:]
    logger.sinks.clear()
    logger.sinks.append(TestSink())

    try:
        @timed("fetch_data", component="api")
        def fetch_data(value):
            time.sleep(0.01)
            return value * 2

        result = fetch_data(5)
        assert result == 10
        assert len(logs) == 1
        assert logs[0]['action'] == 'fetch_data'
        assert logs[0]['duration_ms'] >= 10.0
    finally:
        logger.sinks = old_sinks


def test_timed_decorator_async():
    """Test timed decorator on async function"""
    logs = []

    class TestSink:
        def write(self, record):
            logs.append(record)

    # Temporarily replace sinks
    old_sinks = logger.sinks[:]
    logger.sinks.clear()
    logger.sinks.append(TestSink())

    try:
        @timed("fetch_async", component="api")
        async def fetch_async(value):
            await asyncio.sleep(0.01)
            return value * 2

        result = asyncio.run(fetch_async(5))
        assert result == 10
        assert len(logs) == 1
        assert logs[0]['action'] == 'fetch_async'
        assert logs[0]['duration_ms'] >= 10.0
    finally:
        logger.sinks = old_sinks


def test_logged_decorator():
    """Test logged decorator"""
    logs = []

    class TestSink:
        def write(self, record):
            logs.append(record)

    # Temporarily replace sinks
    old_sinks = logger.sinks[:]
    logger.sinks.clear()
    logger.sinks.append(TestSink())

    try:
        @logged("INFO", component="api", log_args=True, log_result=True)
        def fetch_user(user_id):
            return {"id": user_id, "name": "Alice"}

        result = fetch_user(123)

        assert result == {"id": 123, "name": "Alice"}
        assert len(logs) == 2  # Call + complete

        # Check call log
        assert logs[0]['message'] == 'Calling fetch_user'
        assert logs[0]['action'] == 'function_call'
        assert logs[0]['metadata']['args'] == (123,)

        # Check complete log
        assert logs[1]['message'] == 'Completed fetch_user'
        assert logs[1]['action'] == 'function_complete'
        assert logs[1]['success'] is True
        assert logs[1]['metadata']['result'] == {"id": 123, "name": "Alice"}
    finally:
        logger.sinks = old_sinks


def test_level_filtering():
    """Test log level filtering"""
    test_logger = StructuredLogger()
    test_logger.sinks.clear()
    test_logger.set_level('WARNING')

    logs = []

    class TestSink:
        def write(self, record):
            logs.append(record)

    test_logger.sinks.append(TestSink())

    test_logger.debug("Debug")
    test_logger.info("Info")
    test_logger.warning("Warning")
    test_logger.error("Error")

    # Only WARNING and above
    assert len(logs) == 2
    assert logs[0]['level'] == 'WARNING'
    assert logs[1]['level'] == 'ERROR'


def test_component_filtering():
    """Test component filtering"""
    test_logger = StructuredLogger()
    test_logger.sinks.clear()
    test_logger.filter_components('api', 'db')

    logs = []

    class TestSink:
        def write(self, record):
            logs.append(record)

    test_logger.sinks.append(TestSink())

    test_logger.info("Message 1", component="api")
    test_logger.info("Message 2", component="db")
    test_logger.info("Message 3", component="cache")
    test_logger.info("Message 4", component="api")

    # Only api and db
    assert len(logs) == 3
    assert logs[0]['component'] == 'api'
    assert logs[1]['component'] == 'db'
    assert logs[2]['component'] == 'api'


def test_performance_stats():
    """Test performance tracking"""
    test_logger = StructuredLogger()
    test_logger.sinks.clear()

    # Add dummy sink
    class TestSink:
        def write(self, record):
            pass

    test_logger.sinks.append(TestSink())

    # Time multiple operations
    for i in range(10):
        with test_logger.timed("db_query"):
            time.sleep(0.001 * (i + 1))  # 1-10ms

    stats = test_logger.get_performance_stats("db_query")
    assert stats['count'] == 10
    assert stats['min'] >= 1.0
    assert stats['max'] >= 10.0
    assert stats['p50'] > 0
    assert stats['p95'] > 0
    assert stats['p99'] > 0


def test_json_file_sink():
    """Test JSON file sink with rotation"""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "test.jsonl"

        sink = JSONFileSink(
            base_path=log_path,
            rotation_days=1,
            retention_days=7,
            compress_old=False  # Don't compress for test
        )

        # Write some logs
        sink.write({
            'timestamp': '2024-12-07T12:00:00Z',
            'level': 'INFO',
            'message': 'Test message 1'
        })
        sink.write({
            'timestamp': '2024-12-07T12:01:00Z',
            'level': 'DEBUG',
            'message': 'Test message 2'
        })

        sink.close()

        # Read back
        with open(sink._current_file) as f:
            lines = f.readlines()

        assert len(lines) == 2
        record1 = json.loads(lines[0])
        record2 = json.loads(lines[1])

        assert record1['message'] == 'Test message 1'
        assert record2['message'] == 'Test message 2'


def test_exception_logging():
    """Test exception logging"""
    test_logger = StructuredLogger()
    test_logger.sinks.clear()

    logs = []

    class TestSink:
        def write(self, record):
            logs.append(record)

    test_logger.sinks.append(TestSink())

    try:
        raise ValueError("Test error")
    except Exception:
        test_logger.exception("Operation failed")

    assert len(logs) == 1
    record = logs[0]
    assert record['level'] == 'ERROR'
    assert record['message'] == 'Operation failed'
    assert 'ValueError: Test error' in record['exception']
    assert 'Traceback' in record['exception']


def test_configure_logger():
    """Test configure_logger helper"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Save old state
        old_sinks = logger.sinks[:]
        old_level = logger.min_level

        try:
            # Configure
            configure_logger(
                level='WARNING',
                log_dir=tmpdir,
                console=True,
                json_file=True,
                use_colors=False
            )

            # Check configuration
            assert logger.min_level == LogLevel.WARNING
            assert len(logger.sinks) == 2  # Console + JSON file

            # Check sink types
            assert any(isinstance(s, ConsoleSink) for s in logger.sinks)
            assert any(isinstance(s, JSONFileSink) for s in logger.sinks)
        finally:
            # Restore old state
            logger.sinks = old_sinks
            logger.min_level = old_level


def test_timed_exception():
    """Test timed context manager with exception"""
    test_logger = StructuredLogger()
    test_logger.sinks.clear()

    logs = []

    class TestSink:
        def write(self, record):
            logs.append(record)

    test_logger.sinks.append(TestSink())

    try:
        with test_logger.timed("failing_operation"):
            raise ValueError("Test error")
    except ValueError:
        pass

    assert len(logs) == 1
    record = logs[0]
    assert record['action'] == 'failing_operation'
    assert record['success'] is False
    assert 'ValueError: Test error' in record['exception']


def test_nested_correlation_ids():
    """Test nested correlation ID contexts"""
    logs = []

    class TestSink:
        def write(self, record):
            logs.append(record)

    # Temporarily replace sinks
    old_sinks = logger.sinks[:]
    logger.sinks.clear()
    logger.sinks.append(TestSink())

    try:
        with with_correlation_id("outer"):
            logger.info("Outer 1")

            with with_correlation_id("inner"):
                logger.info("Inner 1")
                logger.info("Inner 2")

            logger.info("Outer 2")

        assert logs[0]['correlation_id'] == "outer"
        assert logs[1]['correlation_id'] == "inner"
        assert logs[2]['correlation_id'] == "inner"
        assert logs[3]['correlation_id'] == "outer"
    finally:
        logger.sinks = old_sinks


if __name__ == '__main__':
    # Run demo if executed directly
    print("Running structured logger demo...\n")

    # Configure logger
    with tempfile.TemporaryDirectory() as tmpdir:
        configure_logger(
            level='DEBUG',
            log_dir=tmpdir,
            console=True,
            json_file=True
        )

        # Demo usage
        logger.info("Starting demo", component="demo", version="1.0")

        with with_correlation_id("demo-task"):
            logger.debug("Debug message", component="demo")
            logger.info("Info message", component="demo")
            logger.warning("Warning message", component="demo")

            with logger.timed("slow_operation", component="demo"):
                time.sleep(0.1)

            try:
                raise ValueError("Demo error")
            except Exception:
                logger.exception("Error occurred", component="demo")

        # Show performance stats
        stats = logger.get_performance_stats()
        print("\n=== Performance Stats ===")
        print(json.dumps(stats, indent=2))

        # Show JSON log file
        json_files = list(Path(tmpdir).glob("*.jsonl"))
        if json_files:
            print(f"\n=== JSON Log File: {json_files[0]} ===")
            with open(json_files[0]) as f:
                for line in f:
                    record = json.loads(line)
                    print(json.dumps(record, indent=2))
                    print()

    print("\nDemo complete! Run tests with: python -m pytest agent/test_structured_logger.py -v")
