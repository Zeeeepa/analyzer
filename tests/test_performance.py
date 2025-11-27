#!/usr/bin/env python3
"""Performance benchmarks for SerenaAdapter

Tests Phase 19: Performance benchmarking of all tool methods
Ensures error tracking overhead is < 5ms per call
"""

import time
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "Libraries"))

from serena_adapter import SerenaAdapter


# ================================================================================
# PHASE 19: PERFORMANCE BENCHMARKS
# ================================================================================

@pytest.fixture
def temp_project():
    """Create temporary project for performance tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir) / "perf_test"
        project_root.mkdir()
        (project_root / "test.py").write_text("print('hello')")
        yield project_root


def test_find_symbol_performance(temp_project):
    """Benchmark find_symbol() execution time."""
    with patch('serena_adapter.SerenaAgent') as mock_agent_class:
        with patch('serena_adapter.Project'):
            mock_agent = Mock()
            mock_agent_class.return_value = mock_agent
            mock_agent.apply_ex.return_value = []
            
            adapter = SerenaAdapter(str(temp_project))
            
            # Warm-up
            adapter.find_symbol("test")
            
            # Benchmark 100 iterations
            iterations = 100
            start_time = time.time()
            
            for i in range(iterations):
                adapter.find_symbol(f"symbol_{i}")
            
            total_time = time.time() - start_time
            avg_time_ms = (total_time / iterations) * 1000
            
            # Verify overhead < 5ms per call
            assert avg_time_ms < 5.0, f"Average time {avg_time_ms:.2f}ms exceeds 5ms limit"
            
            print(f"\nfind_symbol() avg: {avg_time_ms:.3f}ms per call")


def test_read_file_performance(temp_project):
    """Benchmark read_file() execution time."""
    with patch('serena_adapter.SerenaAgent') as mock_agent_class:
        with patch('serena_adapter.Project'):
            mock_agent = Mock()
            mock_agent_class.return_value = mock_agent
            mock_agent.apply_ex.return_value = "file content"
            
            adapter = SerenaAdapter(str(temp_project))
            
            iterations = 100
            start_time = time.time()
            
            for _ in range(iterations):
                adapter.read_file("test.py")
            
            total_time = time.time() - start_time
            avg_time_ms = (total_time / iterations) * 1000
            
            assert avg_time_ms < 5.0, f"Average time {avg_time_ms:.2f}ms exceeds 5ms limit"
            
            print(f"\nread_file() avg: {avg_time_ms:.3f}ms per call")


def test_memory_operations_performance(temp_project):
    """Benchmark memory operations performance."""
    with patch('serena_adapter.SerenaAgent') as mock_agent_class:
        with patch('serena_adapter.Project'):
            mock_agent = Mock()
            mock_agent_class.return_value = mock_agent
            mock_agent.apply_ex.side_effect = [True] * 200  # save + load iterations
            
            adapter = SerenaAdapter(str(temp_project))
            
            iterations = 100
            start_time = time.time()
            
            for i in range(iterations):
                adapter.save_memory(f"key_{i}", f"value_{i}")
                adapter.load_memory(f"key_{i}")
            
            total_time = time.time() - start_time
            avg_time_ms = (total_time / (iterations * 2)) * 1000  # 2 ops per iteration
            
            assert avg_time_ms < 5.0, f"Average time {avg_time_ms:.2f}ms exceeds 5ms limit"
            
            print(f"\nmemory ops avg: {avg_time_ms:.3f}ms per call")


def test_error_tracking_overhead(temp_project):
    """Measure overhead of error tracking mechanism."""
    with patch('serena_adapter.SerenaAgent') as mock_agent_class:
        with patch('serena_adapter.Project'):
            mock_agent = Mock()
            mock_agent_class.return_value = mock_agent
            mock_agent.apply_ex.return_value = []
            
            # Test with error collection enabled
            adapter_with_tracking = SerenaAdapter(str(temp_project), enable_error_collection=True)
            
            iterations = 100
            start_time = time.time()
            for _ in range(iterations):
                adapter_with_tracking.find_symbol("test")
            time_with_tracking = time.time() - start_time
            
            # Test with error collection disabled
            adapter_no_tracking = SerenaAdapter(str(temp_project), enable_error_collection=False)
            
            start_time = time.time()
            for _ in range(iterations):
                adapter_no_tracking.find_symbol("test")
            time_no_tracking = time.time() - start_time
            
            # Calculate overhead
            overhead_ms = ((time_with_tracking - time_no_tracking) / iterations) * 1000
            
            # Overhead should be minimal (< 1ms)
            assert overhead_ms < 1.0, f"Error tracking overhead {overhead_ms:.2f}ms is too high"
            
            print(f"\nError tracking overhead: {overhead_ms:.3f}ms per call")


def test_get_error_statistics_performance(temp_project):
    """Benchmark get_error_statistics() with large error history."""
    with patch('serena_adapter.SerenaAgent'):
        with patch('serena_adapter.Project'):
            adapter = SerenaAdapter(str(temp_project))
            
            # Add 1000 mock errors
            for i in range(1000):
                adapter.error_history.append({
                    'tool': f'Tool{i % 10}',
                    'error': f'Error {i}',
                    'resolved': i % 3 == 0
                })
            
            # Benchmark statistics calculation
            iterations = 100
            start_time = time.time()
            
            for _ in range(iterations):
                stats = adapter.get_error_statistics()
            
            total_time = time.time() - start_time
            avg_time_ms = (total_time / iterations) * 1000
            
            # Should handle 1000 errors efficiently (< 10ms)
            assert avg_time_ms < 10.0, f"Statistics calculation {avg_time_ms:.2f}ms too slow"
            
            print(f"\nget_error_statistics() with 1000 errors: {avg_time_ms:.3f}ms")


def test_runtime_error_collection_performance(temp_project):
    """Benchmark RuntimeErrorCollector performance."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        # Generate large log file with many errors
        for i in range(100):
            f.write(f"""
Traceback (most recent call last):
  File "/app/module_{i}.py", line {i+10}, in function_{i}
    result = data['key_{i}']
KeyError: 'key_{i}'
""")
        log_file = f.name
    
    try:
        with patch('serena_adapter.SerenaAgent'):
            with patch('serena_adapter.Project'):
                adapter = SerenaAdapter(str(temp_project))
                
                # Benchmark error collection
                start_time = time.time()
                errors = adapter.runtime_collector.collect_python_runtime_errors(log_file)
                collection_time = time.time() - start_time
                
                # Should collect 100 errors quickly (< 1 second)
                assert collection_time < 1.0, f"Collection took {collection_time:.2f}s"
                assert len(errors) == 100
                
                print(f"\nCollected 100 errors in {collection_time*1000:.1f}ms")
    finally:
        import os
        os.unlink(log_file)


def test_memory_usage_stability(temp_project):
    """Test memory usage remains stable over many operations."""
    import psutil
    import os
    
    process = psutil.Process(os.getpid())
    
    with patch('serena_adapter.SerenaAgent') as mock_agent_class:
        with patch('serena_adapter.Project'):
            mock_agent = Mock()
            mock_agent_class.return_value = mock_agent
            mock_agent.apply_ex.return_value = []
            
            adapter = SerenaAdapter(str(temp_project))
            
            # Record initial memory
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            # Perform 1000 operations
            for i in range(1000):
                adapter.find_symbol(f"test_{i}")
                if i % 100 == 0:
                    adapter.get_error_statistics()
            
            # Record final memory
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = final_memory - initial_memory
            
            # Memory increase should be minimal (< 50MB for 1000 operations)
            assert memory_increase < 50, f"Memory increased by {memory_increase:.1f}MB"
            
            print(f"\nMemory increase after 1000 ops: {memory_increase:.1f}MB")


def test_performance_stats_collection_overhead(temp_project):
    """Test that performance stats collection itself is fast."""
    with patch('serena_adapter.SerenaAgent') as mock_agent_class:
        with patch('serena_adapter.Project'):
            mock_agent = Mock()
            mock_agent_class.return_value = mock_agent
            mock_agent.apply_ex.return_value = []
            
            adapter = SerenaAdapter(str(temp_project))
            
            # Generate performance data
            for _ in range(100):
                adapter.find_symbol("test")
            
            # Benchmark stats retrieval
            iterations = 1000
            start_time = time.time()
            
            for _ in range(iterations):
                stats = adapter.get_performance_stats()
            
            total_time = time.time() - start_time
            avg_time_ms = (total_time / iterations) * 1000
            
            # Stats retrieval should be very fast (< 1ms)
            assert avg_time_ms < 1.0, f"Stats retrieval {avg_time_ms:.3f}ms too slow"
            
            print(f"\nget_performance_stats() avg: {avg_time_ms:.3f}ms")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])  # -s to see print outputs

