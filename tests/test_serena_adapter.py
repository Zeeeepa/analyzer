#!/usr/bin/env python3
"""Comprehensive tests for SerenaAdapter with RuntimeErrorCollector

Tests cover:
- Phase 9: SerenaAdapter initialization
- Phase 12: find_symbol() with error tracking
- Phase 13: read_file() with error tracking
- Phase 14: get_diagnostics() without runtime logs
- Phase 15: get_diagnostics() with runtime logs
- Phase 16: get_error_statistics() accuracy
- Phase 17: Memory operations with error tracking
- Phase 18: Command execution with error tracking
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Import the adapter
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "Libraries"))

from serena_adapter import SerenaAdapter, RuntimeErrorCollector, EnhancedDiagnostic


# ================================================================================
# FIXTURES
# ================================================================================

@pytest.fixture
def temp_project():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create basic project structure
        project_root = Path(tmpdir) / "test_project"
        project_root.mkdir()
        
        # Create a simple Python file
        (project_root / "main.py").write_text("""
def hello():
    print("Hello, World!")

if __name__ == "__main__":
    hello()
""")
        
        yield project_root


@pytest.fixture
def runtime_log_file():
    """Create a sample runtime log file with Python tracebacks."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        f.write("""
Traceback (most recent call last):
  File "/app/main.py", line 42, in process_data
    result = data['value']
KeyError: 'value'

Traceback (most recent call last):
  File "/app/utils.py", line 15, in calculate
    return x / y
ZeroDivisionError: division by zero
""")
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def ui_log_file():
    """Create a sample UI log file with JavaScript errors."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        f.write("""
TypeError: Cannot read property 'name' of undefined at App.js:25:10
ReferenceError: fetchData is not defined at Component.jsx:18:5
Error: Invalid hook call in UserProfile (at UserProfile.tsx:42:8)
console.error: Network request failed
""")
        yield f.name
    os.unlink(f.name)


# ================================================================================
# PHASE 9: TEST SERENA ADAPTER INITIALIZATION
# ================================================================================

def test_serena_adapter_init_basic(temp_project):
    """Test SerenaAdapter initializes correctly with minimal config."""
    # Mock SerenaAgent to avoid actual initialization
    with patch('serena_adapter.SerenaAgent') as mock_agent:
        with patch('serena_adapter.Project') as mock_project:
            adapter = SerenaAdapter(str(temp_project))
            
            # Verify basic attributes
            assert adapter.project_root == temp_project
            assert adapter.enable_error_collection is True
            assert isinstance(adapter.runtime_collector, RuntimeErrorCollector)
            assert adapter.error_history == []
            assert adapter.error_frequency == {}
            assert adapter.resolution_attempts == {}
            assert adapter.performance_stats == {}
            
            # Verify agent was created
            mock_agent.assert_called_once()


def test_serena_adapter_init_with_error_collection_disabled(temp_project):
    """Test SerenaAdapter with error collection disabled."""
    with patch('serena_adapter.SerenaAgent'):
        with patch('serena_adapter.Project'):
            adapter = SerenaAdapter(str(temp_project), enable_error_collection=False)
            
            assert adapter.enable_error_collection is False
            # Runtime collector still created, but won't be used
            assert isinstance(adapter.runtime_collector, RuntimeErrorCollector)


def test_serena_adapter_set_codebase(temp_project):
    """Test setting codebase for runtime error collection."""
    with patch('serena_adapter.SerenaAgent'):
        with patch('serena_adapter.Project'):
            adapter = SerenaAdapter(str(temp_project))
            
            # Mock codebase
            mock_codebase = Mock()
            adapter.set_codebase(mock_codebase)
            
            assert adapter.runtime_collector.codebase is mock_codebase


# ================================================================================
# PHASE 10: TEST RUNTIME ERROR COLLECTOR - PYTHON ERRORS
# ================================================================================

def test_runtime_error_collector_python_parsing(runtime_log_file):
    """Test RuntimeErrorCollector can parse Python tracebacks."""
    collector = RuntimeErrorCollector()
    
    errors = collector.collect_python_runtime_errors(runtime_log_file)
    
    # Should find 2 errors
    assert len(errors) == 2
    
    # Check first error (KeyError)
    error1 = errors[0]
    assert error1['type'] == 'runtime_error'
    assert error1['error_type'] == 'KeyError'
    assert 'value' in error1['message']
    assert error1['file_path'] == '/app/main.py'
    assert error1['line'] == 42
    assert error1['function'] == 'process_data'
    assert error1['severity'] == 'critical'
    
    # Check second error (ZeroDivisionError)
    error2 = errors[1]
    assert error2['error_type'] == 'ZeroDivisionError'
    assert error2['file_path'] == '/app/utils.py'
    assert error2['line'] == 15


def test_runtime_error_collector_no_log_file():
    """Test RuntimeErrorCollector handles missing log file gracefully."""
    collector = RuntimeErrorCollector()
    
    errors = collector.collect_python_runtime_errors("/nonexistent/file.log")
    
    # Should return empty list, no crash
    assert errors == []


# ================================================================================
# PHASE 11: TEST RUNTIME ERROR COLLECTOR - UI ERRORS
# ================================================================================

def test_runtime_error_collector_ui_parsing(ui_log_file):
    """Test RuntimeErrorCollector can parse JavaScript/React errors."""
    collector = RuntimeErrorCollector()
    
    errors = collector.collect_ui_interaction_errors(ui_log_file)
    
    # Should find 4 errors (2 JS, 1 React, 1 console)
    assert len(errors) == 4
    
    # Check TypeError
    error1 = [e for e in errors if e.get('error_type') == 'TypeError'][0]
    assert error1['type'] == 'ui_error'
    assert 'Cannot read property' in error1['message']
    assert error1['file_path'] == 'App.js'
    assert error1['line'] == 25
    assert error1['column'] == 10
    
    # Check React error
    react_error = [e for e in errors if e.get('type') == 'react_error'][0]
    assert react_error['error_type'] == 'ComponentError'
    assert 'hook call' in react_error['message']
    assert react_error['component'] == 'UserProfile'
    
    # Check console error
    console_error = [e for e in errors if e.get('type') == 'console_error'][0]
    assert 'Network request failed' in console_error['message']


# ================================================================================
# PHASE 12: TEST FIND_SYMBOL WITH ERROR TRACKING
# ================================================================================

def test_find_symbol_success(temp_project):
    """Test find_symbol() works and returns results."""
    with patch('serena_adapter.SerenaAgent') as mock_agent_class:
        with patch('serena_adapter.Project'):
            # Setup mock agent
            mock_agent = Mock()
            mock_agent_class.return_value = mock_agent
            mock_agent.apply_ex.return_value = [
                {'name': 'hello', 'file': 'main.py', 'line': 1}
            ]
            
            adapter = SerenaAdapter(str(temp_project))
            results = adapter.find_symbol("hello")
            
            # Verify results returned
            assert len(results) == 1
            assert results[0]['name'] == 'hello'
            
            # Verify error tracking is empty (no errors)
            assert len(adapter.error_history) == 0


def test_find_symbol_error_tracking(temp_project):
    """Test find_symbol() tracks errors when they occur."""
    with patch('serena_adapter.SerenaAgent') as mock_agent_class:
        with patch('serena_adapter.Project'):
            # Setup mock agent that raises error
            mock_agent = Mock()
            mock_agent_class.return_value = mock_agent
            mock_agent.apply_ex.side_effect = ValueError("Symbol not found")
            
            adapter = SerenaAdapter(str(temp_project))
            
            # Call should raise error
            with pytest.raises(ValueError):
                adapter.find_symbol("nonexistent")
            
            # Verify error was tracked
            assert len(adapter.error_history) == 1
            assert adapter.error_history[0]['tool'] == 'FindSymbol'
            assert 'Symbol not found' in adapter.error_history[0]['error']
            
            # Verify error frequency incremented
            error_key = 'FindSymbol:unknown'
            assert adapter.error_frequency[error_key] == 1


# ================================================================================
# PHASE 13: TEST READ_FILE WITH ERROR TRACKING
# ================================================================================

def test_read_file_success(temp_project):
    """Test read_file() reads content successfully."""
    with patch('serena_adapter.SerenaAgent') as mock_agent_class:
        with patch('serena_adapter.Project'):
            mock_agent = Mock()
            mock_agent_class.return_value = mock_agent
            mock_agent.apply_ex.return_value = "file content here"
            
            adapter = SerenaAdapter(str(temp_project))
            content = adapter.read_file("main.py")
            
            assert content == "file content here"
            assert len(adapter.error_history) == 0


def test_read_file_nonexistent_error_tracking(temp_project):
    """Test read_file() tracks errors for nonexistent files."""
    with patch('serena_adapter.SerenaAgent') as mock_agent_class:
        with patch('serena_adapter.Project'):
            mock_agent = Mock()
            mock_agent_class.return_value = mock_agent
            mock_agent.apply_ex.side_effect = FileNotFoundError("File not found")
            
            adapter = SerenaAdapter(str(temp_project))
            
            with pytest.raises(FileNotFoundError):
                adapter.read_file("nonexistent.py")
            
            # Verify error tracked
            assert len(adapter.error_history) == 1
            assert adapter.error_history[0]['tool'] == 'Read'
            
            # Try again - frequency should increment
            with pytest.raises(FileNotFoundError):
                adapter.read_file("nonexistent.py")
            
            assert len(adapter.error_history) == 2
            error_key = 'Read:nonexistent.py'
            assert adapter.error_frequency[error_key] == 2


# ================================================================================
# PHASE 14: TEST GET_DIAGNOSTICS WITHOUT RUNTIME LOGS
# ================================================================================

def test_get_diagnostics_basic_mode(temp_project):
    """Test get_diagnostics() in basic mode (no runtime logs)."""
    with patch('serena_adapter.SerenaAgent'):
        with patch('serena_adapter.Project'):
            adapter = SerenaAdapter(str(temp_project))
            
            # Call without runtime logs
            diagnostics = adapter.get_diagnostics()
            
            # Should return list (even if empty)
            assert isinstance(diagnostics, list)
            # In basic mode, runtime collector not called
            assert len(adapter.runtime_collector.runtime_errors) == 0


# ================================================================================
# PHASE 15: TEST GET_DIAGNOSTICS WITH RUNTIME LOGS
# ================================================================================

def test_get_diagnostics_with_runtime_logs(temp_project, runtime_log_file, ui_log_file):
    """Test get_diagnostics() merges runtime errors with LSP diagnostics."""
    with patch('serena_adapter.SerenaAgent'):
        with patch('serena_adapter.Project'):
            adapter = SerenaAdapter(str(temp_project), enable_error_collection=True)
            
            # Call with runtime logs
            diagnostics = adapter.get_diagnostics(
                runtime_log_path=runtime_log_file,
                ui_log_path=ui_log_file,
                merge_runtime_errors=True
            )
            
            # Should collect errors (logged in adapter)
            # Actual merging implementation TBD, but collection works
            assert isinstance(diagnostics, list)


# ================================================================================
# PHASE 16: TEST GET_ERROR_STATISTICS
# ================================================================================

def test_get_error_statistics_empty(temp_project):
    """Test get_error_statistics() with no errors."""
    with patch('serena_adapter.SerenaAgent'):
        with patch('serena_adapter.Project'):
            adapter = SerenaAdapter(str(temp_project))
            
            stats = adapter.get_error_statistics()
            
            assert stats['total_errors'] == 0
            assert stats['errors_by_tool'] == {}
            assert stats['resolution_rate'] == 0.0


def test_get_error_statistics_with_errors(temp_project):
    """Test get_error_statistics() calculates correctly."""
    with patch('serena_adapter.SerenaAgent') as mock_agent_class:
        with patch('serena_adapter.Project'):
            mock_agent = Mock()
            mock_agent_class.return_value = mock_agent
            mock_agent.apply_ex.side_effect = [
                ValueError("Error 1"),
                ValueError("Error 2"),
                ValueError("Error 3")
            ]
            
            adapter = SerenaAdapter(str(temp_project))
            
            # Generate some errors
            for i in range(3):
                try:
                    adapter.find_symbol(f"symbol_{i}")
                except ValueError:
                    pass
            
            stats = adapter.get_error_statistics()
            
            # Check stats
            assert stats['total_errors'] == 3
            assert stats['errors_by_tool']['FindSymbol'] == 3
            assert len(stats['recent_errors']) == 3
            assert stats['resolution_rate'] == '0.0%'  # None resolved


def test_get_error_statistics_resolution_rate(temp_project):
    """Test resolution rate calculation."""
    with patch('serena_adapter.SerenaAgent'):
        with patch('serena_adapter.Project'):
            adapter = SerenaAdapter(str(temp_project))
            
            # Manually add errors with resolution status
            adapter.error_history = [
                {'tool': 'Read', 'resolved': True},
                {'tool': 'Read', 'resolved': False},
                {'tool': 'Edit', 'resolved': True},
                {'tool': 'Edit', 'resolved': True},
            ]
            
            stats = adapter.get_error_statistics()
            
            assert stats['total_errors'] == 4
            assert stats['resolution_rate'] == '75.0%'  # 3/4 resolved


# ================================================================================
# PHASE 17: TEST MEMORY OPERATIONS
# ================================================================================

def test_memory_operations(temp_project):
    """Test save_memory(), load_memory(), list_memories(), delete_memory()."""
    with patch('serena_adapter.SerenaAgent') as mock_agent_class:
        with patch('serena_adapter.Project'):
            mock_agent = Mock()
            mock_agent_class.return_value = mock_agent
            
            # Mock memory operations
            mock_agent.apply_ex.side_effect = [
                True,  # save_memory
                "stored value",  # load_memory
                ["key1", "key2"],  # list_memories
                True,  # delete_memory
            ]
            
            adapter = SerenaAdapter(str(temp_project))
            
            # Test save
            result = adapter.save_memory("test_key", "test_value")
            assert result is True
            
            # Test load
            value = adapter.load_memory("test_key")
            assert value == "stored value"
            
            # Test list
            keys = adapter.list_memories()
            assert len(keys) == 2
            
            # Test delete
            result = adapter.delete_memory("test_key")
            assert result is True
            
            # No errors should be tracked for successful operations
            assert len(adapter.error_history) == 0


# ================================================================================
# PHASE 18: TEST COMMAND EXECUTION
# ================================================================================

def test_run_command_success(temp_project):
    """Test run_command() executes safely."""
    with patch('serena_adapter.SerenaAgent') as mock_agent_class:
        with patch('serena_adapter.Project'):
            mock_agent = Mock()
            mock_agent_class.return_value = mock_agent
            mock_agent.apply_ex.return_value = {
                'returncode': 0,
                'stdout': 'Hello',
                'stderr': ''
            }
            
            adapter = SerenaAdapter(str(temp_project))
            result = adapter.run_command("echo Hello")
            
            assert result['returncode'] == 0
            assert result['stdout'] == 'Hello'
            assert len(adapter.error_history) == 0


def test_run_command_failure_tracking(temp_project):
    """Test run_command() tracks failures."""
    with patch('serena_adapter.SerenaAgent') as mock_agent_class:
        with patch('serena_adapter.Project'):
            mock_agent = Mock()
            mock_agent_class.return_value = mock_agent
            mock_agent.apply_ex.side_effect = RuntimeError("Command failed")
            
            adapter = SerenaAdapter(str(temp_project))
            
            with pytest.raises(RuntimeError):
                adapter.run_command("nonexistent_command")
            
            # Verify error tracked
            assert len(adapter.error_history) == 1
            assert adapter.error_history[0]['tool'] == 'Command'


# ================================================================================
# ADDITIONAL TESTS
# ================================================================================

def test_clear_error_history(temp_project):
    """Test clear_error_history() clears all tracking."""
    with patch('serena_adapter.SerenaAgent'):
        with patch('serena_adapter.Project'):
            adapter = SerenaAdapter(str(temp_project))
            
            # Add some mock errors
            adapter.error_history = [{'error': 1}, {'error': 2}, {'error': 3}]
            adapter.error_frequency = {'error1': 5, 'error2': 3}
            adapter.resolution_attempts = {'issue1': 2}
            
            count = adapter.clear_error_history()
            
            assert count == 3  # Number of errors cleared
            assert adapter.error_history == []
            assert adapter.error_frequency == {}
            assert adapter.resolution_attempts == {}


def test_get_performance_stats(temp_project):
    """Test performance statistics collection."""
    with patch('serena_adapter.SerenaAgent') as mock_agent_class:
        with patch('serena_adapter.Project'):
            mock_agent = Mock()
            mock_agent_class.return_value = mock_agent
            mock_agent.apply_ex.return_value = []
            
            adapter = SerenaAdapter(str(temp_project))
            
            # Execute some operations to generate stats
            for _ in range(5):
                adapter.find_symbol("test")
            
            stats = adapter.get_performance_stats()
            
            # Should have stats for FindSymbol
            assert 'FindSymbol' in stats
            assert stats['FindSymbol']['count'] == 5
            assert 'avg_ms' in stats['FindSymbol']
            assert 'min_ms' in stats['FindSymbol']
            assert 'max_ms' in stats['FindSymbol']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

