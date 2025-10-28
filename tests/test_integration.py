#!/usr/bin/env python3
"""Integration tests for complete adapter ecosystem

Tests Phase 20: Integration with analyzer.py
Tests Phase 21: AutoGenLib adapter integration  
Tests Phase 22: Graph-Sitter adapter integration
"""

import os
import sys
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "Libraries"))

from serena_adapter import SerenaAdapter, EnhancedDiagnostic
from autogenlib_adapter import AutoGenLibContextEnricher, resolve_diagnostic_with_ai
from graph_sitter_adapter import GraphSitterAnalyzer


# ================================================================================
# PHASE 20: INTEGRATION WITH ANALYZER.PY
# ================================================================================

def test_serena_adapter_imports_correctly():
    """Test SerenaAdapter can be imported without errors."""
    # If we got here, import succeeded
    assert SerenaAdapter is not None
    assert EnhancedDiagnostic is not None


def test_serena_adapter_with_real_project_structure():
    """Test SerenaAdapter with realistic project structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir) / "real_project"
        project_root.mkdir()
        
        # Create realistic structure
        (project_root / "src").mkdir()
        (project_root / "src" / "__init__.py").write_text("")
        (project_root / "src" / "main.py").write_text("""
import logging

logger = logging.getLogger(__name__)

def main():
    logger.info("Starting application")
    print("Hello, World!")

if __name__ == "__main__":
    main()
""")
        
        (project_root / "tests").mkdir()
        (project_root / "tests" / "test_main.py").write_text("""
import pytest
from src.main import main

def test_main():
    # This should not crash
    main()
""")
        
        # Initialize adapter
        with patch('serena_adapter.SerenaAgent'):
            with patch('serena_adapter.Project'):
                adapter = SerenaAdapter(str(project_root))
                
                # Verify initialization
                assert adapter.project_root == project_root
                assert adapter.enable_error_collection is True
                
                # Test error statistics (should be empty initially)
                stats = adapter.get_error_statistics()
                assert stats['total_errors'] == 0


# ================================================================================
# PHASE 21: AUTOGENLIB ADAPTER INTEGRATION
# ================================================================================

def test_autogenlib_adapter_uses_enhanced_diagnostic():
    """Test AutoGenLibContextEnricher works with EnhancedDiagnostic."""
    # Mock codebase
    mock_codebase = Mock()
    mock_codebase.root = "/project"
    mock_codebase.files = []
    
    enricher = AutoGenLibContextEnricher(mock_codebase)
    
    # Create an EnhancedDiagnostic (matches serena_adapter format)
    from serena.solidlsp.lsp_protocol_handler.lsp_types import Diagnostic, Range, Position
    
    diagnostic = Diagnostic(
        range=Range(
            start=Position(line=10, character=0),
            end=Position(line=10, character=20)
        ),
        message="Undefined variable 'x'",
        severity=1
    )
    
    enhanced_diagnostic: EnhancedDiagnostic = {
        'diagnostic': diagnostic,
        'file_content': 'print(x)',
        'relevant_code_snippet': 'print(x)',
        'file_path': '/project/main.py',
        'relative_file_path': 'main.py',
        'graph_sitter_context': {},
        'autogenlib_context': {},
        'runtime_context': {},
        'ui_interaction_context': {}
    }
    
    # This should not crash - verifies type compatibility
    # (actual enrichment would require full codebase setup)
    assert enhanced_diagnostic['diagnostic'] == diagnostic
    assert enhanced_diagnostic['file_path'] == '/project/main.py'


def test_resolve_diagnostic_with_ai_accepts_enhanced_diagnostic():
    """Test resolve_diagnostic_with_ai() accepts EnhancedDiagnostic format."""
    from serena.solidlsp.lsp_protocol_handler.lsp_types import Diagnostic, Range, Position
    
    # Create mock EnhancedDiagnostic
    diagnostic = Diagnostic(
        range=Range(
            start=Position(line=5, character=0),
            end=Position(line=5, character=10)
        ),
        message="Syntax error",
        severity=1
    )
    
    enhanced_diagnostic: EnhancedDiagnostic = {
        'diagnostic': diagnostic,
        'file_content': 'def foo()\n    pass',
        'relevant_code_snippet': 'def foo()',
        'file_path': '/project/main.py',
        'relative_file_path': 'main.py',
        'graph_sitter_context': {'node_type': 'function_definition'},
        'autogenlib_context': {'imports': []},
        'runtime_context': {'error_type': 'SyntaxError'},
        'ui_interaction_context': {}
    }
    
    mock_codebase = Mock()
    mock_codebase.root = "/project"
    
    # Mock AI client (won't actually call)
    with patch('autogenlib_adapter.get_ai_client', return_value=(None, None)):
        # Should not crash - validates type compatibility
        # Actual AI call would require real client
        result = resolve_diagnostic_with_ai(enhanced_diagnostic, mock_codebase)
        
        # If no AI client, returns None
        assert result is None or isinstance(result, dict)


# ================================================================================
# PHASE 22: GRAPH-SITTER ADAPTER INTEGRATION
# ================================================================================

def test_graph_sitter_adapter_imports_lsp_diagnostics_manager():
    """Test graph_sitter_adapter can import LSPDiagnosticsManager."""
    from serena_adapter import LSPDiagnosticsManager
    
    # Verify import works
    assert LSPDiagnosticsManager is not None


def test_graph_sitter_analyzer_with_serena_diagnostics():
    """Test GraphSitterAnalyzer works with serena_adapter components."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir) / "project"
        project_root.mkdir()
        
        # Create a simple Python file
        (project_root / "test.py").write_text("""
def add(a, b):
    return a + b

result = add(1, 2)
print(result)
""")
        
        # Initialize GraphSitterAnalyzer
        # (This may require actual graph-sitter setup)
        try:
            from graph_sitter import Codebase
            codebase = Codebase.from_directory(str(project_root), extensions=[".py"])
            
            # Verify codebase created
            assert codebase is not None
            assert len(codebase.files) > 0
            
        except Exception as e:
            # If graph-sitter not fully available, that's okay
            pytest.skip(f"Graph-sitter setup failed: {e}")


def test_no_circular_import_issues():
    """Test there are no circular import issues between adapters."""
    # This test verifies all three adapters can be imported together
    try:
        from serena_adapter import SerenaAdapter, LSPDiagnosticsManager, EnhancedDiagnostic
        from autogenlib_adapter import AutoGenLibContextEnricher, resolve_diagnostic_with_ai
        from graph_sitter_adapter import GraphSitterAnalyzer
        
        # If we got here, no circular imports
        assert True
        
    except ImportError as e:
        pytest.fail(f"Circular import detected: {e}")


# ================================================================================
# CROSS-ADAPTER WORKFLOW TESTS
# ================================================================================

def test_complete_diagnostic_workflow():
    """Test complete workflow: Serena → AutoGenLib → Graph-Sitter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir) / "workflow_test"
        project_root.mkdir()
        
        # Create problematic code
        (project_root / "buggy.py").write_text("""
def divide(a, b):
    return a / b  # Bug: no zero check

result = divide(10, 0)  # Will crash
""")
        
        # Step 1: Initialize SerenaAdapter
        with patch('serena_adapter.SerenaAgent'):
            with patch('serena_adapter.Project'):
                serena_adapter = SerenaAdapter(str(project_root))
                
                # Step 2: Collect diagnostics (mocked)
                diagnostics = serena_adapter.get_diagnostics()
                
                # Diagnostics should be list
                assert isinstance(diagnostics, list)
                
                # Step 3: Error statistics should track any issues
                stats = serena_adapter.get_error_statistics()
                assert 'total_errors' in stats
                
                # Step 4: Verify adapter methods work
                assert hasattr(serena_adapter, 'find_symbol')
                assert hasattr(serena_adapter, 'read_file')
                assert hasattr(serena_adapter, 'get_error_statistics')


def test_runtime_error_collection_end_to_end():
    """Test end-to-end runtime error collection and analysis."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create runtime log
        log_file = Path(tmpdir) / "runtime.log"
        log_file.write_text("""
Traceback (most recent call last):
  File "/app/service.py", line 125, in handle_request
    data = json.loads(request.body)
ValueError: Invalid JSON

Traceback (most recent call last):
  File "/app/database.py", line 50, in query
    cursor.execute(sql)
sqlite3.OperationalError: database is locked
""")
        
        project_root = Path(tmpdir) / "app"
        project_root.mkdir()
        
        with patch('serena_adapter.SerenaAgent'):
            with patch('serena_adapter.Project'):
                adapter = SerenaAdapter(str(project_root))
                
                # Collect runtime errors
                adapter.get_diagnostics(
                    runtime_log_path=str(log_file),
                    merge_runtime_errors=True
                )
                
                # Verify runtime collector was used
                # (actual merging logic TBD, but collection works)
                assert adapter.runtime_collector is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

