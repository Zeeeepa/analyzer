#!/usr/bin/env python3
"""
Comprehensive Python Code Analysis Backend with Graph-Sitter Integration

This advanced analysis tool provides deep codebase insights using graph-sitter for
structural analysis, LSP integration for real-time error detection, and comprehensive
static analysis tools for maximum error comprehension.

Features:
- Graph-sitter based codebase analysis
- LSP error detection and reporting
- Comprehensive static analysis tool integration
- Advanced error categorization and presentation
- Interactive analysis capabilities
- Performance profiling and metrics
- Security vulnerability detection
- Code quality assessment
- Dependency analysis
- Documentation coverage analysis

Usage:
    python analysis.py --target /path/to/codebase
    python analysis.py --target /path/to/file.py --interactive
    python analysis.py --target /path/to/project --graph-sitter
"""

import argparse
import ast
import dataclasses
import json
import logging
import os
import re
import subprocess
import sys
import time
import traceback
import threading
import queue
import hashlib
import sqlite3
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union, Callable
from urllib.parse import urlparse
import yaml
import pickle

# Graph-sitter imports (simulated - would be actual imports in real implementation)
try:
    from graph_sitter import Codebase
    from graph_sitter.configs.models.codebase import CodebaseConfig
    from graph_sitter.codebase.codebase_analysis import (
        get_codebase_summary,
        get_file_summary,
        get_class_summary,
        get_function_summary,
        get_symbol_summary
    )
    from graph_sitter.external_module import ExternalModule
    from graph_sitter.import_resolution import Import
    from graph_sitter.symbol import Symbol
    from graph_sitter.file import File
    from graph_sitter.function import Function
    from graph_sitter.class_def import ClassDef
    from graph_sitter.import_stmt import ImportStmt
    from graph_sitter.directory import Directory
    GRAPH_SITTER_AVAILABLE = True
except ImportError:
    # Fallback implementations for demonstration
    GRAPH_SITTER_AVAILABLE = False
    print("Warning: Graph-sitter not available. Using fallback implementations.")

# LSP types and error handling (based on solidlsp)
class ErrorCodes(Enum):
    """LSP error codes for categorization."""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    SERVER_ERROR_START = -32099
    SERVER_ERROR_END = -32000
    SERVER_NOT_INITIALIZED = -32002
    UNKNOWN_ERROR_CODE = -32001
    REQUEST_FAILED = -32803
    SERVER_CANCELLED = -32802
    CONTENT_MODIFIED = -32801
    REQUEST_CANCELLED = -32800


class MessageType(Enum):
    """LSP message types for severity classification."""
    ERROR = 1
    WARNING = 2
    INFO = 3
    LOG = 4


class DiagnosticSeverity(Enum):
    """Diagnostic severity levels."""
    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4


@dataclass
class Position:
    """Represents a position in a text document."""
    line: int
    character: int


@dataclass
class Range:
    """Represents a range in a text document."""
    start: Position
    end: Position


@dataclass
class Diagnostic:
    """Represents a diagnostic message."""
    range: Range
    severity: DiagnosticSeverity
    code: Optional[str]
    source: Optional[str]
    message: str
    related_information: Optional[List[Dict]] = None
    tags: Optional[List[int]] = None


@dataclass
class LSPError:
    """LSP error representation."""
    code: ErrorCodes
    message: str
    data: Optional[Dict] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"code": self.code.value, "message": self.message}
        if self.data:
            result["data"] = self.data
        return result


@dataclass
class AnalysisError:
    """Represents an analysis error with comprehensive context."""
    file_path: str
    line_number: Optional[int]
    column_number: Optional[int]
    error_type: str
    severity: DiagnosticSeverity
    message: str
    tool_source: str
    code_context: Optional[str] = None
    fix_suggestion: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    error_code: Optional[str] = None
    related_errors: List[str] = field(default_factory=list)
    confidence: float = 1.0
    tags: List[str] = field(default_factory=list)


@dataclass
class ToolConfig:
    """Configuration for a code analysis tool."""
    name: str
    command: str
    enabled: bool = True
    args: List[str] = field(default_factory=list)
    config_file: Optional[str] = None
    timeout: int = 300
    category: str = "general"
    priority: int = 1
    requires_network: bool = False
    output_format: str = "text"


class ErrorCategory(Enum):
    """Comprehensive error categorization system."""
    SYNTAX = "syntax"
    TYPE = "type"
    IMPORT = "import"
    LOGIC = "logic"
    STYLE = "style"
    SECURITY = "security"
    PERFORMANCE = "performance"
    COMPATIBILITY = "compatibility"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    MAINTAINABILITY = "maintainability"
    DESIGN = "design"
    DEPENDENCIES = "dependencies"
    CONFIGURATION = "configuration"
    DEPLOYMENT = "deployment"


class AnalysisSeverity(Enum):
    """Analysis severity levels with priority."""
    CRITICAL = 1
    ERROR = 2
    WARNING = 3
    INFO = 4
    HINT = 5


# Fallback Graph-sitter Analysis implementation for demonstration
class MockAnalysis:
    """Mock Analysis class when graph-sitter is not available."""
    
    def __init__(self, codebase_path: str):
        self.codebase_path = codebase_path
        self._files = []
        self._functions = []
        self._classes = []
        self._imports = []
        self._symbols = []
        self._external_modules = []
        self._scan_codebase()
    
    def _scan_codebase(self):
        """Scan the codebase and extract basic information."""
        for root, dirs, files in os.walk(self.codebase_path):
            # Skip common ignored directories
            dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', '.venv', 'venv', 'node_modules'}]
            
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    try:
                        self._analyze_file(file_path)
                    except Exception as e:
                        logging.warning(f"Failed to analyze {file_path}: {e}")
    
    def _analyze_file(self, file_path: str):
        """Analyze a single file using AST parsing."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            
            # Extract functions, classes, and imports
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    self._functions.append({
                        'name': node.name,
                        'file_path': file_path,
                        'line_number': node.lineno,
                        'is_async': isinstance(node, ast.AsyncFunctionDef),
                        'decorators': [d.id if isinstance(d, ast.Name) else str(d) for d in node.decorator_list],
                        'parameters': [arg.arg for arg in node.args.args]
                    })
                    self._symbols.append(self._functions[-1])
                
                elif isinstance(node, ast.ClassDef):
                    self._classes.append({
                        'name': node.name,
                        'file_path': file_path,
                        'line_number': node.lineno,
                        'bases': [base.id if isinstance(base, ast.Name) else str(base) for base in node.bases],
                        'decorators': [d.id if isinstance(d, ast.Name) else str(d) for d in node.decorator_list]
                    })
                    self._symbols.append(self._classes[-1])
                
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self._imports.append({
                                'module': alias.name,
                                'name': alias.asname or alias.name,
                                'file_path': file_path,
                                'line_number': node.lineno,
                                'is_external': not alias.name.startswith('.')
                            })
                    else:  # ImportFrom
                        module = node.module or ''
                        for alias in node.names:
                            self._imports.append({
                                'module': module,
                                'name': alias.name,
                                'file_path': file_path,
                                'line_number': node.lineno,
                                'is_external': not module.startswith('.')
                            })
            
            self._files.append({
                'path': file_path,
                'content': content,
                'line_count': len(content.splitlines())
            })
            
        except Exception as e:
            logging.warning(f"Error parsing {file_path}: {e}")
    
    @property
    def functions(self):
        return self._functions
    
    @property
    def classes(self):
        return self._classes
    
    @property
    def imports(self):
        return self._imports
    
    @property
    def files(self):
        return self._files
    
    @property
    def symbols(self):
        return self._symbols
    
    @property
    def external_modules(self):
        return self._external_modules


class GraphSitterAnalysis:
    """
    Enhanced Analysis class providing pre-computed graph element access and advanced analysis.
    
    Integrates with graph-sitter for comprehensive codebase understanding and provides
    the exact API shown in the documentation with additional error detection capabilities.
    """
    
    def __init__(self, codebase_path: str, config: Optional[Dict] = None):
        """Initialize Analysis with a Codebase instance."""
        self.codebase_path = codebase_path
        self.config = config or {}
        
        if GRAPH_SITTER_AVAILABLE:
            # Initialize with performance optimizations
            gs_config = CodebaseConfig(
                method_usages=True,          # Enable method usage resolution
                generics=True,               # Enable generic type resolution
                sync_enabled=True,           # Enable graph sync during commits
                full_range_index=True,       # Full range-to-node mapping
                py_resolve_syspath=True,     # Resolve sys.path imports
                exp_lazy_graph=False,        # Lazy graph construction
            )
            
            self.codebase = Codebase(codebase_path, config=gs_config)
            self.analysis = self.codebase  # Direct codebase access
        else:
            # Use fallback implementation
            self.analysis = MockAnalysis(codebase_path)
            self.codebase = None
    
    @property
    def functions(self):
        """
        All functions in codebase with enhanced analysis.
        
        Each function provides:
        - function.usages           # All usage sites
        - function.call_sites       # All call locations
        - function.dependencies     # Function dependencies
        - function.function_calls   # Functions this function calls
        - function.parameters       # Function parameters
        - function.return_statements # Return statements
        - function.decorators       # Function decorators
        - function.is_async         # Async function detection
        - function.is_generator     # Generator function detection
        """
        return self.analysis.functions
    
    @property
    def classes(self):
        """
        All classes in codebase with comprehensive analysis.
        
        Each class provides:
        - cls.superclasses         # Parent classes
        - cls.subclasses          # Child classes
        - cls.methods             # Class methods
        - cls.attributes          # Class attributes
        - cls.decorators          # Class decorators
        - cls.usages              # Class usage sites
        - cls.dependencies        # Class dependencies
        - cls.is_abstract         # Abstract class detection
        """
        return self.analysis.classes
    
    @property
    def imports(self):
        """All import statements in the codebase."""
        return self.analysis.imports
    
    @property
    def files(self):
        """
        All files in the codebase with import analysis.
        
        Each file provides:
        - file.imports            # Outbound imports
        - file.inbound_imports    # Files that import this file
        - file.symbols            # Symbols defined in file
        - file.external_modules   # External dependencies
        """
        return self.analysis.files
    
    @property
    def symbols(self):
        """All symbols (functions, classes, variables) in the codebase."""
        return self.analysis.symbols
    
    @property
    def external_modules(self):
        """External dependencies imported by the codebase."""
        return self.analysis.external_modules
    
    def get_codebase_summary(self) -> Dict[str, Any]:
        """Get comprehensive codebase summary."""
        if GRAPH_SITTER_AVAILABLE and self.codebase:
            return get_codebase_summary(self.codebase)
        
        # Fallback implementation
        return {
            "total_files": len(self.files),
            "total_functions": len(self.functions),
            "total_classes": len(self.classes),
            "total_imports": len(self.imports),
            "total_symbols": len(self.symbols),
            "external_dependencies": len(self.external_modules),
            "lines_of_code": sum(f.get('line_count', 0) for f in self.files),
            "complexity_score": self._calculate_complexity_score()
        }
    
    def get_file_summary(self, file_path: str) -> Dict[str, Any]:
        """Get detailed file summary."""
        if GRAPH_SITTER_AVAILABLE and self.codebase:
            file_obj = self.codebase.get_file(file_path)
            if file_obj:
                return get_file_summary(file_obj)
        
        # Fallback implementation
        file_info = next((f for f in self.files if f['path'] == file_path), None)
        if not file_info:
            return {"error": f"File not found: {file_path}"}
        
        file_functions = [f for f in self.functions if f['file_path'] == file_path]
        file_classes = [c for c in self.classes if c['file_path'] == file_path]
        file_imports = [i for i in self.imports if i['file_path'] == file_path]
        
        return {
            "path": file_path,
            "lines_of_code": file_info['line_count'],
            "functions": len(file_functions),
            "classes": len(file_classes),
            "imports": len(file_imports),
            "complexity": self._calculate_file_complexity(file_path)
        }
    
    def get_function_analysis(self, function_name: str) -> Dict[str, Any]:
        """Get detailed analysis for a specific function."""
        if GRAPH_SITTER_AVAILABLE and self.codebase:
            func = self.codebase.get_function(function_name)
            if func:
                return get_function_summary(func)
        
        # Fallback implementation
        func_info = next((f for f in self.functions if f['name'] == function_name), None)
        if not func_info:
            return {"error": f"Function not found: {function_name}"}
        
        return {
            'name': func_info['name'],
            'file_path': func_info['file_path'],
            'line_number': func_info['line_number'],
            'parameters': func_info.get('parameters', []),
            'decorators': func_info.get('decorators', []),
            'is_async': func_info.get('is_async', False),
            'complexity': self._calculate_function_complexity(func_info),
            'usages': self._find_function_usages(function_name)
        }
    
    def get_class_analysis(self, class_name: str) -> Dict[str, Any]:
        """Get detailed analysis for a specific class."""
        if GRAPH_SITTER_AVAILABLE and self.codebase:
            cls = self.codebase.get_class(class_name)
            if cls:
                return get_class_summary(cls)
        
        # Fallback implementation
        class_info = next((c for c in self.classes if c['name'] == class_name), None)
        if not class_info:
            return {"error": f"Class not found: {class_name}"}
        
        class_methods = [f for f in self.functions 
                        if f['file_path'] == class_info['file_path'] 
                        and f['line_number'] > class_info['line_number']]
        
        return {
            'name': class_info['name'],
            'file_path': class_info['file_path'],
            'line_number': class_info['line_number'],
            'methods': len(class_methods),
            'bases': class_info.get('bases', []),
            'decorators': class_info.get('decorators', []),
            'complexity': self._calculate_class_complexity(class_info)
        }
    
    def get_symbol_analysis(self, symbol_name: str) -> Dict[str, Any]:
        """Get detailed analysis for a specific symbol."""
        if GRAPH_SITTER_AVAILABLE and self.codebase:
            symbol = self.codebase.get_symbol(symbol_name)
            if symbol:
                return get_symbol_summary(symbol)
        
        # Fallback implementation
        symbol_info = next((s for s in self.symbols if s['name'] == symbol_name), None)
        if not symbol_info:
            return {"error": f"Symbol not found: {symbol_name}"}
        
        return {
            'name': symbol_info['name'],
            'type': 'function' if 'parameters' in symbol_info else 'class',
            'file_path': symbol_info['file_path'],
            'line_number': symbol_info['line_number'],
            'usage_count': len(self._find_symbol_usages(symbol_name))
        }
    
    def _calculate_complexity_score(self) -> float:
        """Calculate overall codebase complexity score."""
        if not self.functions:
            return 0.0
        
        total_complexity = sum(self._calculate_function_complexity(f) for f in self.functions)
        return total_complexity / len(self.functions)
    
    def _calculate_file_complexity(self, file_path: str) -> float:
        """Calculate complexity score for a specific file."""
        file_functions = [f for f in self.functions if f['file_path'] == file_path]
        if not file_functions:
            return 0.0
        
        total_complexity = sum(self._calculate_function_complexity(f) for f in file_functions)
        return total_complexity / len(file_functions)
    
    def _calculate_function_complexity(self, func_info: Dict) -> float:
        """Calculate complexity score for a function."""
        # Basic complexity calculation based on parameters and decorators
        base_complexity = 1.0
        param_complexity = len(func_info.get('parameters', [])) * 0.2
        decorator_complexity = len(func_info.get('decorators', [])) * 0.1
        async_complexity = 0.3 if func_info.get('is_async', False) else 0.0
        
        return base_complexity + param_complexity + decorator_complexity + async_complexity
    
    def _calculate_class_complexity(self, class_info: Dict) -> float:
        """Calculate complexity score for a class."""
        base_complexity = 2.0
        base_complexity += len(class_info.get('bases', [])) * 0.5
        base_complexity += len(class_info.get('decorators', [])) * 0.2
        return base_complexity
    
    def _find_function_usages(self, function_name: str) -> List[Dict]:
        """Find usages of a function across the codebase."""
        usages = []
        for file_info in self.files:
            try:
                content = file_info['content']
                lines = content.splitlines()
                for i, line in enumerate(lines):
                    if function_name in line and 'def ' not in line:
                        usages.append({
                            'file_path': file_info['path'],
                            'line_number': i + 1,
                            'context': line.strip()
                        })
            except Exception:
                continue
        return usages
    
    def _find_symbol_usages(self, symbol_name: str) -> List[Dict]:
        """Find usages of a symbol across the codebase."""
        return self._find_function_usages(symbol_name)


class LSPClient:
    """JSON-RPC client for Language Server Protocol communication."""
    
    def __init__(self, server_command: List[str], cwd: Optional[str] = None):
        self.server_command = server_command
        self.cwd = cwd or os.getcwd()
        self.process = None
        self.request_id = 0
        self.responses = {}
        self.notifications = []
        self.diagnostics = {}
        self._running = False
        
    def start(self):
        """Start the language server process."""
        try:
            self.process = subprocess.Popen(
                self.server_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.cwd,
                text=False
            )
            self._running = True
            
            # Start reader thread
            self.reader_thread = threading.Thread(target=self._read_messages)
            self.reader_thread.daemon = True
            self.reader_thread.start()
            
            # Initialize the server
            self._initialize()
            
        except Exception as e:
            logging.error(f"Failed to start LSP server: {e}")
            return False
        
        return True
    
    def stop(self):
        """Stop the language server process."""
        self._running = False
        if self.process:
            self.process.terminate()
            self.process.wait()
    
    def _initialize(self):
        """Initialize the language server."""
        init_params = {
            "processId": os.getpid(),
            "clientInfo": {"name": "AnalysisBackend", "version": "1.0.0"},
            "rootUri": f"file://{self.cwd}",
            "capabilities": {
                "textDocument": {
                    "publishDiagnostics": {"relatedInformation": True}
                }
            }
        }
        
        response = self.send_request("initialize", init_params)
        if response:
            self.send_notification("initialized", {})
    
    def send_request(self, method: str, params: Any) -> Optional[Dict]:
        """Send a request to the language server."""
        if not self.process:
            return None
        
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params
        }
        
        try:
            message = self._create_message(request)
            self.process.stdin.write(message)
            self.process.stdin.flush()
            
            # Wait for response (simplified - in real implementation would be async)
            time.sleep(0.1)
            return self.responses.get(self.request_id)
            
        except Exception as e:
            logging.error(f"Error sending request: {e}")
            return None
    
    def send_notification(self, method: str, params: Any):
        """Send a notification to the language server."""
        if not self.process:
            return
        
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        try:
            message = self._create_message(notification)
            self.process.stdin.write(message)
            self.process.stdin.flush()
        except Exception as e:
            logging.error(f"Error sending notification: {e}")
    
    def _create_message(self, payload: Dict) -> bytes:
        """Create a properly formatted LSP message."""
        body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        header = f"Content-Length: {len(body)}\r\n\r\n".encode('utf-8')
        return header + body
    
    def _read_messages(self):
        """Read messages from the language server."""
        while self._running and self.process:
            try:
                # Read header
                header = b""
                while not header.endswith(b"\r\n\r\n"):
                    chunk = self.process.stdout.read(1)
                    if not chunk:
                        break
                    header += chunk
                
                if not header:
                    break
                
                # Parse content length
                content_length = 0
                for line in header.decode('utf-8').split('\r\n'):
                    if line.startswith('Content-Length:'):
                        content_length = int(line.split(':')[1].strip())
                        break
                
                if content_length == 0:
                    continue
                
                # Read body
                body = self.process.stdout.read(content_length)
                if not body:
                    break
                
                # Parse message
                try:
                    message = json.loads(body.decode('utf-8'))
                    self._handle_message(message)
                except json.JSONDecodeError as e:
                    logging.error(f"Failed to parse LSP message: {e}")
                    
            except Exception as e:
                logging.error(f"Error reading LSP messages: {e}")
                break
    
    def _handle_message(self, message: Dict):
        """Handle incoming message from language server."""
        if "id" in message:
            # Response to our request
            self.responses[message["id"]] = message
        elif message.get("method") == "textDocument/publishDiagnostics":
            # Diagnostic notification
            params = message.get("params", {})
            uri = params.get("uri", "")
            diagnostics = params.get("diagnostics", [])
            self.diagnostics[uri] = diagnostics
        else:
            # Other notification
            self.notifications.append(message)
    
    def get_diagnostics(self, file_path: str) -> List[Diagnostic]:
        """Get diagnostics for a specific file."""
        file_uri = f"file://{os.path.abspath(file_path)}"
        raw_diagnostics = self.diagnostics.get(file_uri, [])
        
        diagnostics = []
        for diag in raw_diagnostics:
            try:
                range_info = diag.get("range", {})
                start_pos = Position(
                    line=range_info.get("start", {}).get("line", 0),
                    character=range_info.get("start", {}).get("character", 0)
                )
                end_pos = Position(
                    line=range_info.get("end", {}).get("line", 0),
                    character=range_info.get("end", {}).get("character", 0)
                )
                
                diagnostic = Diagnostic(
                    range=Range(start=start_pos, end=end_pos),
                    severity=DiagnosticSeverity(diag.get("severity", 1)),
                    code=diag.get("code"),
                    source=diag.get("source"),
                    message=diag.get("message", ""),
                    related_information=diag.get("relatedInformation"),
                    tags=diag.get("tags")
                )
                diagnostics.append(diagnostic)
            except Exception as e:
                logging.warning(f"Failed to parse diagnostic: {e}")
        
        return diagnostics


class RuffIntegration:
    """Integration with Ruff for comprehensive Python linting and type checking."""
    
    def __init__(self, target_path: str):
        self.target_path = target_path
        self.config_file = self._find_ruff_config()
    
    def _find_ruff_config(self) -> Optional[str]:
        """Find Ruff configuration file."""
        search_paths = [
            "ruff.toml",
            "pyproject.toml",
            ".ruff.toml"
        ]
        
        current_dir = Path(self.target_path if os.path.isdir(self.target_path) else os.path.dirname(self.target_path))
        
        while current_dir != current_dir.parent:
            for config_file in search_paths:
                config_path = current_dir / config_file
                if config_path.exists():
                    return str(config_path)
            current_dir = current_dir.parent
        
        return None
    
    def run_ruff_check(self) -> List[AnalysisError]:
        """Run Ruff check and parse results."""
        cmd = ["ruff", "check", "--output-format=json", self.target_path]
        
        if self.config_file:
            cmd.extend(["--config", self.config_file])
        
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300
            )
            
            errors = []
            if result.stdout:
                try:
                    ruff_results = json.loads(result.stdout)
                    for issue in ruff_results:
                        error = AnalysisError(
                            file_path=issue.get("filename", ""),
                            line_number=issue.get("location", {}).get("row"),
                            column_number=issue.get("location", {}).get("column"),
                            error_type="ruff",
                            severity=self._map_ruff_severity(issue.get("severity", "error")),
                            message=issue.get("message", ""),
                            tool_source="ruff",
                            error_code=issue.get("code"),
                            category=self._categorize_ruff_error(issue.get("code", "")),
                            fix_suggestion=issue.get("fix", {}).get("message")
                        )
                        errors.append(error)
                except json.JSONDecodeError:
                    # Fallback to text parsing
                    errors.extend(self._parse_ruff_text_output(result.stdout))
            
            return errors
            
        except subprocess.TimeoutExpired:
            return [AnalysisError(
                file_path=self.target_path,
                line_number=None,
                column_number=None,
                error_type="timeout",
                severity=DiagnosticSeverity.ERROR,
                message="Ruff analysis timed out",
                tool_source="ruff"
            )]
        except Exception as e:
            return [AnalysisError(
                file_path=self.target_path,
                line_number=None,
                column_number=None,
                error_type="execution_error",
                severity=DiagnosticSeverity.ERROR,
                message=f"Ruff execution failed: {str(e)}",
                tool_source="ruff"
            )]
    
    def run_ruff_format_check(self) -> List[AnalysisError]:
        """Run Ruff format check."""
        cmd = ["ruff", "format", "--check", "--diff", self.target_path]
        
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )
            
            errors = []
            if result.returncode != 0 and result.stdout:
                # Parse diff output for formatting issues
                errors.append(AnalysisError(
                    file_path=self.target_path,
                    line_number=None,
                    column_number=None,
                    error_type="formatting",
                    severity=DiagnosticSeverity.WARNING,
                    message="Code formatting issues detected",
                    tool_source="ruff-format",
                    category=ErrorCategory.STYLE.value,
                    code_context=result.stdout[:500]  # First 500 chars of diff
                ))
            
            return errors
            
        except Exception as e:
            return []
    
    def _map_ruff_severity(self, severity: str) -> DiagnosticSeverity:
        """Map Ruff severity to diagnostic severity."""
        mapping = {
            "error": DiagnosticSeverity.ERROR,
            "warning": DiagnosticSeverity.WARNING,
            "info": DiagnosticSeverity.INFORMATION,
            "hint": DiagnosticSeverity.HINT
        }
        return mapping.get(severity.lower(), DiagnosticSeverity.WARNING)
    
    def _categorize_ruff_error(self, code: str) -> str:
        """Categorize Ruff error based on error code."""
        if not code:
            return ErrorCategory.STYLE.value
        
        code_prefix = code.split()[0] if ' ' in code else code[:3]
        
        category_mapping = {
            "E": ErrorCategory.STYLE.value,
            "W": ErrorCategory.STYLE.value,
            "F": ErrorCategory.LOGIC.value,
            "C": ErrorCategory.DESIGN.value,
            "N": ErrorCategory.STYLE.value,
            "B": ErrorCategory.LOGIC.value,
            "A": ErrorCategory.COMPATIBILITY.value,
            "COM": ErrorCategory.STYLE.value,
            "CPY": ErrorCategory.DOCUMENTATION.value,
            "DJ": ErrorCategory.DESIGN.value,
            "EM": ErrorCategory.MAINTAINABILITY.value,
            "EXE": ErrorCategory.SECURITY.value,
            "FA": ErrorCategory.COMPATIBILITY.value,
            "FBT": ErrorCategory.DESIGN.value,
            "FLY": ErrorCategory.PERFORMANCE.value,
            "FURB": ErrorCategory.MAINTAINABILITY.value,
            "G": ErrorCategory.STYLE.value,
            "I": ErrorCategory.IMPORT.value,
            "ICN": ErrorCategory.STYLE.value,
            "INP": ErrorCategory.IMPORT.value,
            "INT": ErrorCategory.TYPE.value,
            "ISC": ErrorCategory.STYLE.value,
            "LOG": ErrorCategory.MAINTAINABILITY.value,
            "NPY": ErrorCategory.PERFORMANCE.value,
            "PD": ErrorCategory.PERFORMANCE.value,
            "PERF": ErrorCategory.PERFORMANCE.value,
            "PGH": ErrorCategory.MAINTAINABILITY.value,
            "PIE": ErrorCategory.LOGIC.value,
            "PL": ErrorCategory.LOGIC.value,
            "PT": ErrorCategory.TESTING.value,
            "PTH": ErrorCategory.COMPATIBILITY.value,
            "PYI": ErrorCategory.TYPE.value,
            "Q": ErrorCategory.STYLE.value,
            "RET": ErrorCategory.LOGIC.value,
            "RSE": ErrorCategory.LOGIC.value,
            "RUF": ErrorCategory.MAINTAINABILITY.value,
            "S": ErrorCategory.SECURITY.value,
            "SIM": ErrorCategory.MAINTAINABILITY.value,
            "SLF": ErrorCategory.DESIGN.value,
            "SLOT": ErrorCategory.PERFORMANCE.value,
            "T": ErrorCategory.STYLE.value,
            "TCH": ErrorCategory.TYPE.value,
            "TD": ErrorCategory.DOCUMENTATION.value,
            "TID": ErrorCategory.IMPORT.value,
            "TRY": ErrorCategory.LOGIC.value,
            "UP": ErrorCategory.COMPATIBILITY.value,
            "YTT": ErrorCategory.COMPATIBILITY.value
        }
        
        for prefix, category in category_mapping.items():
            if code.startswith(prefix):
                return category
        
        return ErrorCategory.STYLE.value
    
    def _parse_ruff_text_output(self, output: str) -> List[AnalysisError]:
        """Parse Ruff text output when JSON is not available."""
        errors = []
        for line in output.splitlines():
            if ':' in line and '.py:' in line:
                try:
                    parts = line.split(':')
                    if len(parts) >= 4:
                        file_path = parts[0]
                        line_num = int(parts[1])
                        col_num = int(parts[2])
                        message = ':'.join(parts[3:]).strip()
                        
                        # Extract error code if present
                        code_match = re.search(r'\[([A-Z0-9]+)\]', message)
                        error_code = code_match.group(1) if code_match else None
                        
                        error = AnalysisError(
                            file_path=file_path,
                            line_number=line_num,
                            column_number=col_num,
                            error_type="ruff",
                            severity=DiagnosticSeverity.WARNING,
                            message=message,
                            tool_source="ruff",
                            error_code=error_code,
                            category=self._categorize_ruff_error(error_code or "")
                        )
                        errors.append(error)
                except (ValueError, IndexError):
                    continue
        
        return errors


class ComprehensiveAnalyzer:
    """Main analyzer class that orchestrates all analysis tools and provides comprehensive error reporting."""
    
    # Extended tool configuration with categorization
    COMPREHENSIVE_TOOLS = {
        # Core Python linting and type checking
        "ruff": ToolConfig(
            "ruff", "ruff", 
            args=["check", "--output-format=json", "--select=ALL"],
            category=ErrorCategory.STYLE.value,
            priority=1
        ),
        "mypy": ToolConfig(
            "mypy", "mypy",
            args=["--strict", "--show-error-codes", "--show-column-numbers", "--pretty"],
            category=ErrorCategory.TYPE.value,
            priority=1
        ),
        "pyright": ToolConfig(
            "pyright", "pyright",
            args=["--outputjson"],
            category=ErrorCategory.TYPE.value,
            priority=1,
            timeout=600
        ),
        "pylint": ToolConfig(
            "pylint", "pylint",
            args=["--output-format=json", "--reports=y", "--score=y"],
            category=ErrorCategory.LOGIC.value,
            priority=2
        ),
        
        # Security analysis
        "bandit": ToolConfig(
            "bandit", "bandit",
            args=["-r", "-f", "json", "--severity-level=low", "--confidence-level=low"],
            category=ErrorCategory.SECURITY.value,
            priority=1
        ),
        "safety": ToolConfig(
            "safety", "safety",
            args=["check", "--json", "--full-report"],
            category=ErrorCategory.SECURITY.value,
            priority=1,
            requires_network=True
        ),
        "semgrep": ToolConfig(
            "semgrep", "semgrep",
            args=["--config=p/python", "--json", "--severity=WARNING"],
            category=ErrorCategory.SECURITY.value,
            priority=2,
            requires_network=True
        ),
        
        # Code quality and complexity
        "radon": ToolConfig(
            "radon", "radon",
            args=["cc", "-j", "--total-average"],
            category=ErrorCategory.MAINTAINABILITY.value,
            priority=2
        ),
        "xenon": ToolConfig(
            "xenon", "xenon",
            args=["--max-absolute=B", "--max-modules=B", "--max-average=C"],
            category=ErrorCategory.MAINTAINABILITY.value,
            priority=2
        ),
        "cohesion": ToolConfig(
            "cohesion", "cohesion",
            args=["--below", "80", "--format", "json"],
            category=ErrorCategory.DESIGN.value,
            priority=3
        ),
        
        # Import and dependency analysis
        "isort": ToolConfig(
            "isort", "isort",
            args=["--check-only", "--diff", "--profile=black"],
            category=ErrorCategory.IMPORT.value,
            priority=2
        ),
        "vulture": ToolConfig(
            "vulture", "vulture",
            args=["--min-confidence=60", "--sort-by-size"],
            category=ErrorCategory.LOGIC.value,
            priority=2
        ),
        "pydeps": ToolConfig(
            "pydeps", "pydeps",
            args=["--max-bacon=3", "--show-cycles", "--format", "json"],
            category=ErrorCategory.DEPENDENCIES.value,
            priority=3
        ),
        
        # Style and formatting
        "black": ToolConfig(
            "black", "black",
            args=["--check", "--diff"],
            category=ErrorCategory.STYLE.value,
            priority=2
        ),
        "pycodestyle": ToolConfig(
            "pycodestyle", "pycodestyle",
            args=["--statistics", "--count"],
            category=ErrorCategory.STYLE.value,
            priority=3
        ),
        "pydocstyle": ToolConfig(
            "pydocstyle", "pydocstyle",
            args=["--convention=google"],
            category=ErrorCategory.DOCUMENTATION.value,
            priority=2
        ),
        
        # Performance analysis
        "py-spy": ToolConfig(
            "py-spy", "py-spy",
            args=["record", "-o", "/tmp/profile.svg", "--", "python"],
            category=ErrorCategory.PERFORMANCE.value,
            priority=3,
            enabled=False  # Requires special setup
        ),
        
        # Testing analysis
        "pytest": ToolConfig(
            "pytest", "pytest",
            args=["--collect-only", "--quiet"],
            category=ErrorCategory.TESTING.value,
            priority=3
        ),
        "coverage": ToolConfig(
            "coverage", "coverage",
            args=["report", "--format=json"],
            category=ErrorCategory.TESTING.value,
            priority=3
        ),
        
        # Compatibility analysis
        "pyupgrade": ToolConfig(
            "pyupgrade", "pyupgrade",
            args=["--py312-plus"],
            category=ErrorCategory.COMPATIBILITY.value,
            priority=3
        ),
        "modernize": ToolConfig(
            "modernize", "python-modernize",
            args=["--print", "--no-diffs"],
            category=ErrorCategory.COMPATIBILITY.value,
            priority=3
        ),
        
        # Additional analysis tools
        "pyflakes": ToolConfig(
            "pyflakes", "pyflakes",
            category=ErrorCategory.LOGIC.value,
            priority=2
        ),
        "mccabe": ToolConfig(
            "mccabe", "python",
            args=["-m", "mccabe", "--min", "5"],
            category=ErrorCategory.MAINTAINABILITY.value,
            priority=3
        ),
        "dodgy": ToolConfig(
            "dodgy", "dodgy",
            args=["--ignore-paths=venv,.venv,env,.env,__pycache__,.git"],
            category=ErrorCategory.SECURITY.value,
            priority=3
        ),
        "dlint": ToolConfig(
            "dlint", "dlint",
            category=ErrorCategory.SECURITY.value,
            priority=3
        ),
        "codespell": ToolConfig(
            "codespell", "codespell",
            args=["--quiet-level=2"],
            category=ErrorCategory.DOCUMENTATION.value,
            priority=3
        ),
        
        # Advanced analysis
        "prospector": ToolConfig(
            "prospector", "prospector",
            args=["--output-format=json", "--full-pep8"],
            category=ErrorCategory.LOGIC.value,
            priority=2
        ),
        "pyanalyze": ToolConfig(
            "pyanalyze", "python",
            args=["-m", "pyanalyze"],
            category=ErrorCategory.TYPE.value,
            priority=3
        )
    }
    
    def __init__(self, target_path: str, config: Optional[Dict] = None, verbose: bool = False):
        """Initialize the comprehensive analyzer."""
        self.target_path = os.path.abspath(target_path)
        self.config = config or {}
        self.verbose = verbose
        self.tools_config = self.COMPREHENSIVE_TOOLS.copy()
        self.graph_analysis = None
        self.lsp_client = None
        self.ruff_integration = None
        self.analysis_cache = {}
        self.error_database = ErrorDatabase()
        
        # Initialize components
        self._initialize_graph_analysis()
        self._initialize_lsp_client()
        self._initialize_ruff_integration()
        
        # Apply configuration
        self._apply_config()
    
    def _initialize_graph_analysis(self):
        """Initialize graph-sitter analysis."""
        try:
            self.graph_analysis = GraphSitterAnalysis(self.target_path, self.config)
            if self.verbose:
                print("Graph-sitter analysis initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize graph-sitter analysis: {e}")
            self.graph_analysis = None
    
    def _initialize_lsp_client(self):
        """Initialize LSP client for real-time error detection."""
        # Try to find and start a Python language server
        lsp_commands = [
            ["pylsp"],  # Python LSP Server
            ["pyright-langserver", "--stdio"],  # Pyright
            ["jedi-language-server"]  # Jedi
        ]
        
        for cmd in lsp_commands:
            try:
                if self._command_exists(cmd[0]):
                    self.lsp_client = LSPClient(cmd, self.target_path)
                    if self.lsp_client.start():
                        if self.verbose:
                            print(f"LSP client started with {cmd[0]}")
                        break
                    else:
                        self.lsp_client = None
            except Exception as e:
                if self.verbose:
                    print(f"Failed to start LSP with {cmd[0]}: {e}")
                continue
    
    def _initialize_ruff_integration(self):
        """Initialize Ruff integration."""
        try:
            self.ruff_integration = RuffIntegration(self.target_path)
            if self.verbose:
                print("Ruff integration initialized")
        except Exception as e:
            logging.error(f"Failed to initialize Ruff integration: {e}")
    
    def _command_exists(self, command: str) -> bool:
        """Check if a command exists in the system."""
        try:
            subprocess.run(
                ["which", command], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                check=True
            )
            return True
        except subprocess.CalledProcessError:
            return False
    
    def _apply_config(self):
        """Apply configuration settings."""
        if "tools" in self.config:
            for tool_name, tool_config in self.config["tools"].items():
                if tool_name in self.tools_config:
                    self.tools_config[tool_name].enabled = tool_config.get("enabled", True)
                    if "args" in tool_config:
                        self.tools_config[tool_name].args = tool_config["args"]
                    if "timeout" in tool_config:
                        self.tools_config[tool_name].timeout = tool_config["timeout"]
    
    def run_comprehensive_analysis(self) -> Dict[str, Any]:
        """Run comprehensive analysis using all available tools and methods."""
        start_time = time.time()
        
        analysis_results = {
            "metadata": {
                "target_path": self.target_path,
                "analysis_start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "python_version": sys.version,
                "tools_used": [],
                "analysis_duration": 0
            },
            "graph_sitter_analysis": {},
            "lsp_diagnostics": {},
            "static_analysis": {},
            "errors": [],
            "summary": {},
            "entrypoints": [],
            "dead_code": [],
            "categorized_errors": {},
            "performance_metrics": {},
            "security_issues": [],
            "dependency_analysis": {},
            "quality_metrics": {}
        }
        
        try:
            # 1. Graph-sitter Analysis
            if self.graph_analysis:
                analysis_results["graph_sitter_analysis"] = self._run_graph_sitter_analysis()
                analysis_results["metadata"]["tools_used"].append("graph-sitter")
            
            # 2. LSP Diagnostics
            if self.lsp_client:
                analysis_results["lsp_diagnostics"] = self._run_lsp_analysis()
                analysis_results["metadata"]["tools_used"].append("lsp")
            
            # 3. Ruff Integration
            if self.ruff_integration:
                ruff_errors = self._run_ruff_analysis()
                analysis_results["errors"].extend(ruff_errors)
                analysis_results["metadata"]["tools_used"].append("ruff")
            
            # 4. Static Analysis Tools
            static_analysis_results = self._run_static_analysis()
            analysis_results["static_analysis"] = static_analysis_results
            analysis_results["errors"].extend(self._extract_errors_from_static_analysis(static_analysis_results))
            
            # 5. Advanced Analysis
            analysis_results["entrypoints"] = self._find_entrypoints()
            analysis_results["dead_code"] = self._find_dead_code()
            analysis_results["dependency_analysis"] = self._analyze_dependencies()
            analysis_results["performance_metrics"] = self._calculate_performance_metrics()
            analysis_results["quality_metrics"] = self._calculate_quality_metrics()
            
            # 6. Error Categorization and Prioritization
            analysis_results["categorized_errors"] = self._categorize_errors(analysis_results["errors"])
            
            # 7. Generate Summary
            analysis_results["summary"] = self._generate_comprehensive_summary(analysis_results)
            
        except Exception as e:
            logging.error(f"Error during comprehensive analysis: {e}")
            analysis_results["fatal_error"] = str(e)
        
        finally:
            # Cleanup
            if self.lsp_client:
                self.lsp_client.stop()
            
            # Calculate duration
            end_time = time.time()
            analysis_results["metadata"]["analysis_duration"] = round(end_time - start_time, 2)
            analysis_results["metadata"]["analysis_end_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        return analysis_results
    
    def _run_graph_sitter_analysis(self) -> Dict[str, Any]:
        """Run comprehensive graph-sitter analysis."""
        if not self.graph_analysis:
            return {"error": "Graph-sitter analysis not available"}
        
        try:
            results = {
                "codebase_summary": self.graph_analysis.get_codebase_summary(),
                "files_analysis": {},
                "symbols_analysis": {},
                "dependency_graph": {},
                "inheritance_hierarchy": {},
                "call_graph": {},
                "import_graph": {}
            }
            
            # Analyze each file
            for file_info in self.graph_analysis.files[:50]:  # Limit for performance
                file_path = file_info.get('path', '') if isinstance(file_info, dict) else getattr(file_info, 'path', '')
                if file_path:
                    results["files_analysis"][file_path] = self.graph_analysis.get_file_summary(file_path)
            
            # Analyze symbols
            for symbol_info in self.graph_analysis.symbols[:100]:  # Limit for performance
                symbol_name = symbol_info.get('name', '') if isinstance(symbol_info, dict) else getattr(symbol_info, 'name', '')
                if symbol_name:
                    symbol_analysis = self.graph_analysis.get_symbol_analysis(symbol_name)
                    results["symbols_analysis"][symbol_name] = symbol_analysis
                    
                    # Additional analysis based on symbol type
                    if symbol_analysis.get('type') == 'function':
                        func_analysis = self.graph_analysis.get_function_analysis(symbol_name)
                        results["symbols_analysis"][symbol_name].update(func_analysis)
                    elif symbol_analysis.get('type') == 'class':
                        class_analysis = self.graph_analysis.get_class_analysis(symbol_name)
                        results["symbols_analysis"][symbol_name].update(class_analysis)
            
            # Build dependency graph
            results["dependency_graph"] = self._build_dependency_graph()
            
            # Build inheritance hierarchy
            results["inheritance_hierarchy"] = self._build_inheritance_hierarchy()
            
            # Build call graph
            results["call_graph"] = self._build_call_graph()
            
            # Build import graph
            results["import_graph"] = self._build_import_graph()
            
            return results
            
        except Exception as e:
            logging.error(f"Error in graph-sitter analysis: {e}")
            return {"error": str(e)}
    
    def _run_lsp_analysis(self) -> Dict[str, Any]:
        """Run LSP analysis for real-time error detection."""
        if not self.lsp_client:
            return {"error": "LSP client not available"}
        
        try:
            results = {
                "diagnostics_by_file": {},
                "total_diagnostics": 0,
                "error_summary": {}
            }
            
            # Get diagnostics for each Python file
            if os.path.isfile(self.target_path):
                files_to_analyze = [self.target_path]
            else:
                files_to_analyze = []
                for root, dirs, files in os.walk(self.target_path):
                    for file in files:
                        if file.endswith('.py'):
                            files_to_analyze.append(os.path.join(root, file))
            
            for file_path in files_to_analyze[:20]:  # Limit for performance
                # Send textDocument/didOpen notification
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                self.lsp_client.send_notification("textDocument/didOpen", {
                    "textDocument": {
                        "uri": f"file://{file_path}",
                        "languageId": "python",
                        "version": 1,
                        "text": content
                    }
                })
                
                # Wait a bit for diagnostics
                time.sleep(0.5)
                
                # Get diagnostics
                diagnostics = self.lsp_client.get_diagnostics(file_path)
                if diagnostics:
                    results["diagnostics_by_file"][file_path] = [
                        {
                            "range": {
                                "start": {"line": d.range.start.line, "character": d.range.start.character},
                                "end": {"line": d.range.end.line, "character": d.range.end.character}
                            },
                            "severity": d.severity.value,
                            "message": d.message,
                            "source": d.source,
                            "code": d.code
                        }
                        for d in diagnostics
                    ]
                    results["total_diagnostics"] += len(diagnostics)
            
            # Generate error summary
            results["error_summary"] = self._summarize_lsp_diagnostics(results["diagnostics_by_file"])
            
            return results
            
        except Exception as e:
            logging.error(f"Error in LSP analysis: {e}")
            return {"error": str(e)}
    
    def _run_ruff_analysis(self) -> List[AnalysisError]:
        """Run comprehensive Ruff analysis."""
        if not self.ruff_integration:
            return []
        
        errors = []
        
        try:
            # Run standard Ruff check
            ruff_errors = self.ruff_integration.run_ruff_check()
            errors.extend(ruff_errors)
            
            # Run Ruff format check
            format_errors = self.ruff_integration.run_ruff_format_check()
            errors.extend(format_errors)
            
            # Additional Ruff configurations for comprehensive analysis
            additional_checks = [
                ["--select=ALL", "--ignore=COM812,ISC001"],  # All rules except conflicting ones
                ["--select=E,W,F", "--statistics"],          # Core errors and warnings
                ["--select=I", "--show-fixes"],              # Import sorting
                ["--select=N", "--show-source"],             # Naming conventions
                ["--select=S", "--show-source"],             # Security
                ["--select=B", "--show-source"],             # Bugbear
                ["--select=C90", "--show-source"],           # Complexity
                ["--select=PL", "--show-source"],            # Pylint
                ["--select=RUF", "--show-source"]            # Ruff-specific
            ]
            
            for check_args in additional_checks:
                try:
                    cmd = ["ruff", "check"] + check_args + [self.target_path]
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=120
                    )
                    
                    if result.stdout:
                        additional_errors = self._parse_ruff_output(result.stdout, check_args[0])
                        errors.extend(additional_errors)
                        
                except Exception as e:
                    if self.verbose:
                        print(f"Additional Ruff check failed: {e}")
                    continue
            
        except Exception as e:
            logging.error(f"Error in Ruff analysis: {e}")
        
        return errors
    
    def _run_static_analysis(self) -> Dict[str, Any]:
        """Run all configured static analysis tools."""
        results = {}
        
        # Group tools by category for organized execution
        tools_by_category = defaultdict(list)
        for tool_name, tool_config in self.tools_config.items():
            if tool_config.enabled:
                tools_by_category[tool_config.category].append((tool_name, tool_config))
        
        # Run tools in parallel within each category
        for category, tools in tools_by_category.items():
            if self.verbose:
                print(f"Running {category} analysis tools...")
            
            category_results = {}
            
            with ThreadPoolExecutor(max_workers=3) as executor:
                future_to_tool = {
                    executor.submit(self._run_single_tool, tool_name, tool_config): tool_name
                    for tool_name, tool_config in tools
                }
                
                for future in as_completed(future_to_tool):
                    tool_name = future_to_tool[future]
                    try:
                        tool_result = future.result()
                        category_results[tool_name] = tool_result
                    except Exception as e:
                        category_results[tool_name] = {
                            "error": str(e),
                            "success": False
                        }
            
            results[category] = category_results
        
        return results
    
    def _run_single_tool(self, tool_name: str, tool_config: ToolConfig) -> Dict[str, Any]:
        """Run a single analysis tool."""
        if not self._command_exists(tool_config.command.split()[0]):
            return {
                "error": f"Tool {tool_name} not found",
                "success": False,
                "skipped": True
            }
        
        # Build command
        cmd = [tool_config.command] + tool_config.args + [self.target_path]
        if tool_config.command == "python":
            cmd = tool_config.args + [self.target_path]
        
        # Find configuration file
        config_file = self._find_tool_config(tool_name, tool_config)
        if config_file:
            cmd = self._add_config_to_command(cmd, tool_name, config_file)
        
        try:
            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=tool_config.timeout,
                cwd=os.path.dirname(self.target_path) if os.path.isfile(self.target_path) else self.target_path
            )
            
            execution_time = time.time() - start_time
            
            return {
                "command": " ".join(cmd),
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0,
                "execution_time": execution_time,
                "tool_category": tool_config.category,
                "tool_priority": tool_config.priority
            }
            
        except subprocess.TimeoutExpired:
            return {
                "error": f"Tool {tool_name} timed out after {tool_config.timeout}s",
                "success": False,
                "timeout": True,
                "tool_category": tool_config.category
            }
        except Exception as e:
            return {
                "error": str(e),
                "success": False,
                "tool_category": tool_config.category
            }
    
    def _find_tool_config(self, tool_name: str, tool_config: ToolConfig) -> Optional[str]:
        """Find configuration file for a tool."""
        if not tool_config.config_file:
            return None
        
        search_dir = self.target_path if os.path.isdir(self.target_path) else os.path.dirname(self.target_path)
        current_dir = Path(search_dir)
        
        while current_dir != current_dir.parent:
            config_path = current_dir / tool_config.config_file
            if config_path.exists():
                return str(config_path)
            current_dir = current_dir.parent
        
        return None
    
    def _add_config_to_command(self, cmd: List[str], tool_name: str, config_file: str) -> List[str]:
        """Add configuration file to command."""
        config_mappings = {
            "pylint": f"--rcfile={config_file}",
            "mypy": f"--config-file={config_file}",
            "flake8": f"--config={config_file}",
            "bandit": f"--configfile={config_file}"
        }
        
        if tool_name in config_mappings:
            cmd.insert(-1, config_mappings[tool_name])
        
        return cmd
    
    def _extract_errors_from_static_analysis(self, static_results: Dict) -> List[AnalysisError]:
        """Extract and convert static analysis results to AnalysisError objects."""
        errors = []
        
        for category, tools in static_results.items():
            for tool_name, tool_result in tools.items():
                if not tool_result.get("success", False) or tool_result.get("stdout", "").strip():
                    errors.extend(self._parse_tool_output(tool_name, tool_result, category))
        
        return errors
    
    def _parse_tool_output(self, tool_name: str, tool_result: Dict, category: str) -> List[AnalysisError]:
        """Parse tool output and convert to AnalysisError objects."""
        errors = []
        
        if tool_result.get("timeout"):
            errors.append(AnalysisError(
                file_path=self.target_path,
                line_number=None,
                column_number=None,
                error_type="timeout",
                severity=DiagnosticSeverity.ERROR,
                message=f"{tool_name} analysis timed out",
                tool_source=tool_name,
                category=category
            ))
            return errors
        
        output = tool_result.get("stdout", "") + tool_result.get("stderr", "")
        
        # Tool-specific parsing
        if tool_name == "pylint":
            errors.extend(self._parse_pylint_output(output, tool_name, category))
        elif tool_name == "mypy":
            errors.extend(self._parse_mypy_output(output, tool_name, category))
        elif tool_name == "pyright":
            errors.extend(self._parse_pyright_output(output, tool_name, category))
        elif tool_name == "bandit":
            errors.extend(self._parse_bandit_output(output, tool_name, category))
        elif tool_name == "safety":
            errors.extend(self._parse_safety_output(output, tool_name, category))
        elif tool_name == "vulture":
            errors.extend(self._parse_vulture_output(output, tool_name, category))
        elif tool_name == "radon":
            errors.extend(self._parse_radon_output(output, tool_name, category))
        else:
            # Generic parsing
            errors.extend(self._parse_generic_output(output, tool_name, category))
        
        return errors
    
    def _parse_pylint_output(self, output: str, tool_name: str, category: str) -> List[AnalysisError]:
        """Parse Pylint output."""
        errors = []
        
        # Try JSON format first
        try:
            pylint_data = json.loads(output)
            for item in pylint_data:
                if isinstance(item, dict) and "path" in item:
                    error = AnalysisError(
                        file_path=item["path"],
                        line_number=item.get("line"),
                        column_number=item.get("column"),
                        error_type=item.get("type", "unknown"),
                        severity=self._map_pylint_severity(item.get("type", "")),
                        message=item.get("message", ""),
                        tool_source=tool_name,
                        error_code=item.get("message-id"),
                        category=self._categorize_pylint_error(item.get("message-id", "")),
                        confidence=item.get("confidence", 1.0) / 10.0  # Convert to 0-1 scale
                    )
                    errors.append(error)
        except json.JSONDecodeError:
            # Fallback to text parsing
            for line in output.splitlines():
                if ".py:" in line and ": " in line:
                    match = re.match(r"(.+?):(\d+):(\d+): (.+?): (.+)", line)
                    if match:
                        file_path, line_num, col_num, msg_type, message = match.groups()
                        error = AnalysisError(
                            file_path=file_path,
                            line_number=int(line_num),
                            column_number=int(col_num),
                            error_type=msg_type,
                            severity=self._map_pylint_severity(msg_type),
                            message=message,
                            tool_source=tool_name,
                            category=category
                        )
                        errors.append(error)
        
        return errors
    
    def _parse_mypy_output(self, output: str, tool_name: str, category: str) -> List[AnalysisError]:
        """Parse MyPy output."""
        errors = []
        
        for line in output.splitlines():
            if ".py:" in line and ": " in line:
                # MyPy format: file.py:line:column: error: message [error-code]
                match = re.match(r"(.+?):(\d+):(?:(\d+):)?\s*(\w+):\s*(.+?)(?:\s*\[(.+?)\])?$", line)
                if match:
                    file_path, line_num, col_num, severity, message, error_code = match.groups()
                    
                    error = AnalysisError(
                        file_path=file_path,
                        line_number=int(line_num),
                        column_number=int(col_num) if col_num else None,
                        error_type=severity,
                        severity=self._map_mypy_severity(severity),
                        message=message,
                        tool_source=tool_name,
                        error_code=error_code,
                        category=ErrorCategory.TYPE.value,
                        subcategory=self._categorize_mypy_error(error_code or message)
                    )
                    errors.append(error)
        
        return errors
    
    def _parse_pyright_output(self, output: str, tool_name: str, category: str) -> List[AnalysisError]:
        """Parse Pyright JSON output."""
        errors = []
        
        try:
            pyright_data = json.loads(output)
            
            for diagnostic in pyright_data.get("generalDiagnostics", []):
                error = AnalysisError(
                    file_path=diagnostic.get("file", ""),
                    line_number=diagnostic.get("range", {}).get("start", {}).get("line"),
                    column_number=diagnostic.get("range", {}).get("start", {}).get("character"),
                    error_type=diagnostic.get("severity", "error"),
                    severity=self._map_pyright_severity(diagnostic.get("severity", "error")),
                    message=diagnostic.get("message", ""),
                    tool_source=tool_name,
                    error_code=diagnostic.get("rule"),
                    category=ErrorCategory.TYPE.value
                )
                errors.append(error)
                
        except json.JSONDecodeError:
            # Fallback to text parsing
            for line in output.splitlines():
                if " - error:" in line or " - warning:" in line:
                    parts = line.split(" - ")
                    if len(parts) >= 2:
                        location = parts[0].strip()
                        severity_message = parts[1]
                        
                        # Extract file path and line number
                        location_match = re.match(r"(.+?):(\d+):(\d+)", location)
                        if location_match:
                            file_path, line_num, col_num = location_match.groups()
                            
                            severity = "error" if "error:" in severity_message else "warning"
                            message = severity_message.split(":", 1)[1].strip() if ":" in severity_message else severity_message
                            
                            error = AnalysisError(
                                file_path=file_path,
                                line_number=int(line_num),
                                column_number=int(col_num),
                                error_type=severity,
                                severity=DiagnosticSeverity.ERROR if severity == "error" else DiagnosticSeverity.WARNING,
                                message=message,
                                tool_source=tool_name,
                                category=ErrorCategory.TYPE.value
                            )
                            errors.append(error)
        
        return errors
    
    def _parse_bandit_output(self, output: str, tool_name: str, category: str) -> List[AnalysisError]:
        """Parse Bandit security analysis output."""
        errors = []
        
        try:
            bandit_data = json.loads(output)
            
            for result in bandit_data.get("results", []):
                error = AnalysisError(
                    file_path=result.get("filename", ""),
                    line_number=result.get("line_number"),
                    column_number=result.get("col_offset"),
                    error_type="security",
                    severity=self._map_bandit_severity(result.get("issue_severity", "MEDIUM")),
                    message=result.get("issue_text", ""),
                    tool_source=tool_name,
                    error_code=result.get("test_id"),
                    category=ErrorCategory.SECURITY.value,
                    subcategory=result.get("issue_type", "unknown"),
                    confidence=self._map_bandit_confidence(result.get("issue_confidence", "MEDIUM")),
                    code_context=result.get("code")
                )
                errors.append(error)
                
        except json.JSONDecodeError:
            # Fallback to text parsing
            current_file = None
            for line in output.splitlines():
                if "Test results:" in line:
                    break
                
                if line.startswith(">>"):
                    # File indicator
                    current_file = line.replace(">>", "").strip()
                elif "Issue:" in line and current_file:
                    # Parse issue line
                    issue_match = re.search(r"Issue: \[(.+?)\] (.+)", line)
                    if issue_match:
                        severity, message = issue_match.groups()
                        
                        error = AnalysisError(
                            file_path=current_file,
                            line_number=None,
                            column_number=None,
                            error_type="security",
                            severity=self._map_bandit_severity(severity),
                            message=message,
                            tool_source=tool_name,
                            category=ErrorCategory.SECURITY.value
                        )
                        errors.append(error)
        
        return errors
    
    def _parse_safety_output(self, output: str, tool_name: str, category: str) -> List[AnalysisError]:
        """Parse Safety vulnerability output."""
        errors = []
        
        try:
            # Safety can output JSON or text
            if output.strip().startswith('[') or output.strip().startswith('{'):
                safety_data = json.loads(output)
                
                vulnerabilities = safety_data if isinstance(safety_data, list) else safety_data.get("vulnerabilities", [])
                
                for vuln in vulnerabilities:
                    error = AnalysisError(
                        file_path=self.target_path,
                        line_number=None,
                        column_number=None,
                        error_type="vulnerability",
                        severity=DiagnosticSeverity.ERROR,
                        message=f"Vulnerability in {vuln.get('package_name', 'unknown')}: {vuln.get('advisory', '')}",
                        tool_source=tool_name,
                        error_code=vuln.get("vulnerability_id"),
                        category=ErrorCategory.SECURITY.value,
                        subcategory="dependency_vulnerability",
                        fix_suggestion=f"Upgrade to version {vuln.get('fixed_in', 'latest')}"
                    )
                    errors.append(error)
            else:
                # Text parsing
                for line in output.splitlines():
                    if "vulnerability" in line.lower() or "insecure" in line.lower():
                        error = AnalysisError(
                            file_path=self.target_path,
                            line_number=None,
                            column_number=None,
                            error_type="vulnerability",
                            severity=DiagnosticSeverity.ERROR,
                            message=line.strip(),
                            tool_source=tool_name,
                            category=ErrorCategory.SECURITY.value
                        )
                        errors.append(error)
                        
        except json.JSONDecodeError:
            pass
        
        return errors
    
    def _parse_vulture_output(self, output: str, tool_name: str, category: str) -> List[AnalysisError]:
        """Parse Vulture dead code output."""
        errors = []
        
        for line in output.splitlines():
            if ".py:" in line:
                # Vulture format: file.py:line: unused function/class/variable 'name'
                match = re.match(r"(.+?):(\d+):\s*(.+)", line)
                if match:
                    file_path, line_num, message = match.groups()
                    
                    error = AnalysisError(
                        file_path=file_path,
                        line_number=int(line_num),
                        column_number=None,
                        error_type="dead_code",
                        severity=DiagnosticSeverity.WARNING,
                        message=message,
                        tool_source=tool_name,
                        category=ErrorCategory.LOGIC.value,
                        subcategory="unused_code",
                        tags=["dead_code", "optimization"]
                    )
                    errors.append(error)
        
        return errors
    
    def _parse_radon_output(self, output: str, tool_name: str, category: str) -> List[AnalysisError]:
        """Parse Radon complexity output."""
        errors = []
        
        try:
            # Try JSON format
            if output.strip().startswith('{'):
                radon_data = json.loads(output)
                
                for file_path, metrics in radon_data.items():
                    for item in metrics:
                        complexity = item.get("complexity", 0)
                        if complexity > 10:  # High complexity threshold
                            error = AnalysisError(
                                file_path=file_path,
                                line_number=item.get("lineno"),
                                column_number=item.get("col_offset"),
                                error_type="complexity",
                                severity=DiagnosticSeverity.WARNING if complexity < 20 else DiagnosticSeverity.ERROR,
                                message=f"High complexity ({complexity}) in {item.get('name', 'unknown')}",
                                tool_source=tool_name,
                                category=ErrorCategory.MAINTAINABILITY.value,
                                subcategory="complexity"
                            )
                            errors.append(error)
            else:
                # Text parsing
                for line in output.splitlines():
                    if " - " in line and ("A " in line or "B " in line or "C " in line):
                        complexity_match = re.search(r"([A-F])\s*\((\d+)\)", line)
                        if complexity_match:
                            grade, complexity = complexity_match.groups()
                            complexity_value = int(complexity)
                            
                            if complexity_value > 10:
                                error = AnalysisError(
                                    file_path=self.target_path,
                                    line_number=None,
                                    column_number=None,
                                    error_type="complexity",
                                    severity=DiagnosticSeverity.WARNING if complexity_value < 20 else DiagnosticSeverity.ERROR,
                                    message=f"High complexity ({complexity_value}, grade {grade}): {line.split(' - ')[0]}",
                                    tool_source=tool_name,
                                    category=ErrorCategory.MAINTAINABILITY.value
                                )
                                errors.append(error)
                                
        except json.JSONDecodeError:
            pass
        
        return errors
    
    def _parse_generic_output(self, output: str, tool_name: str, category: str) -> List[AnalysisError]:
        """Generic parser for tool output."""
        errors = []
        
        # Look for common error patterns
        error_patterns = [
            r"(.+?):(\d+):(\d+):\s*(.+)",  # file:line:col: message
            r"(.+?):(\d+):\s*(.+)",        # file:line: message
            r"(.+?)\s*(.+?)\s*(.+)"       # Generic three-part pattern
        ]
        
        for line in output.splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            
            for pattern in error_patterns:
                match = re.match(pattern, line)
                if match:
                    groups = match.groups()
                    
                    if len(groups) >= 3 and '.py' in groups[0]:
                        try:
                            file_path = groups[0]
                            line_num = int(groups[1]) if groups[1].isdigit() else None
                            col_num = int(groups[2]) if len(groups) > 3 and groups[2].isdigit() else None
                            message = groups[-1]
                            
                            error = AnalysisError(
                                file_path=file_path,
                                line_number=line_num,
                                column_number=col_num,
                                error_type="unknown",
                                severity=DiagnosticSeverity.WARNING,
                                message=message,
                                tool_source=tool_name,
                                category=category
                            )
                            errors.append(error)
                            break
                        except (ValueError, IndexError):
                            continue
        
        return errors
    
    def _parse_ruff_output(self, output: str, select_arg: str) -> List[AnalysisError]:
        """Parse additional Ruff output."""
        errors = []
        
        try:
            if output.strip().startswith('['):
                ruff_data = json.loads(output)
                for issue in ruff_data:
                    error = AnalysisError(
                        file_path=issue.get("filename", ""),
                        line_number=issue.get("location", {}).get("row"),
                        column_number=issue.get("location", {}).get("column"),
                        error_type="ruff_extended",
                        severity=self._map_ruff_severity(issue.get("severity", "warning")),
                        message=issue.get("message", ""),
                        tool_source="ruff",
                        error_code=issue.get("code"),
                        category=self._categorize_ruff_error(issue.get("code", "")),
                        fix_suggestion=issue.get("fix", {}).get("message"),
                        tags=[select_arg.replace("--select=", "")]
                    )
                    errors.append(error)
        except json.JSONDecodeError:
            # Text parsing for additional ruff output
            for line in output.splitlines():
                if '.py:' in line and ':' in line:
                    parts = line.split(':')
                    if len(parts) >= 4:
                        try:
                            file_path = parts[0]
                            line_num = int(parts[1])
                            col_num = int(parts[2])
                            message = ':'.join(parts[3:]).strip()
                            
                            error = AnalysisError(
                                file_path=file_path,
                                line_number=line_num,
                                column_number=col_num,
                                error_type="ruff_extended",
                                severity=DiagnosticSeverity.WARNING,
                                message=message,
                                tool_source="ruff",
                                category=ErrorCategory.STYLE.value,
                                tags=[select_arg.replace("--select=", "")]
                            )
                            errors.append(error)
                        except (ValueError, IndexError):
                            continue
        
        return errors
    
    def _map_pylint_severity(self, msg_type: str) -> DiagnosticSeverity:
        """Map Pylint message type to diagnostic severity."""
        mapping = {
            "error": DiagnosticSeverity.ERROR,
            "warning": DiagnosticSeverity.WARNING,
            "refactor": DiagnosticSeverity.INFORMATION,
            "convention": DiagnosticSeverity.HINT,
            "info": DiagnosticSeverity.INFORMATION
        }
        return mapping.get(msg_type.lower(), DiagnosticSeverity.WARNING)
    
    def _map_mypy_severity(self, severity: str) -> DiagnosticSeverity:
        """Map MyPy severity to diagnostic severity."""
        mapping = {
            "error": DiagnosticSeverity.ERROR,
            "warning": DiagnosticSeverity.WARNING,
            "note": DiagnosticSeverity.INFORMATION
        }
        return mapping.get(severity.lower(), DiagnosticSeverity.ERROR)
    
    def _map_pyright_severity(self, severity: str) -> DiagnosticSeverity:
        """Map Pyright severity to diagnostic severity."""
        mapping = {
            "error": DiagnosticSeverity.ERROR,
            "warning": DiagnosticSeverity.WARNING,
            "information": DiagnosticSeverity.INFORMATION
        }
        return mapping.get(severity.lower(), DiagnosticSeverity.ERROR)
    
    def _map_bandit_severity(self, severity: str) -> DiagnosticSeverity:
        """Map Bandit severity to diagnostic severity."""
        mapping = {
            "HIGH": DiagnosticSeverity.ERROR,
            "MEDIUM": DiagnosticSeverity.WARNING,
            "LOW": DiagnosticSeverity.INFORMATION
        }
        return mapping.get(severity.upper(), DiagnosticSeverity.WARNING)
    
    def _map_bandit_confidence(self, confidence: str) -> float:
        """Map Bandit confidence to float value."""
        mapping = {
            "HIGH": 0.9,
            "MEDIUM": 0.6,
            "LOW": 0.3
        }
        return mapping.get(confidence.upper(), 0.5)
    
    def _categorize_pylint_error(self, message_id: str) -> str:
        """Categorize Pylint errors."""
        if not message_id:
            return ErrorCategory.LOGIC.value
        
        category_mapping = {
            "C": ErrorCategory.STYLE.value,
            "R": ErrorCategory.MAINTAINABILITY.value,
            "W": ErrorCategory.LOGIC.value,
            "E": ErrorCategory.LOGIC.value,
            "F": ErrorCategory.SYNTAX.value
        }
        
        prefix = message_id[0] if message_id else "W"
        return category_mapping.get(prefix, ErrorCategory.LOGIC.value)
    
    def _categorize_mypy_error(self, error_info: str) -> str:
        """Categorize MyPy errors."""
        if not error_info:
            return "type_checking"
        
        if any(keyword in error_info.lower() for keyword in ["import", "module"]):
            return "import_error"
        elif any(keyword in error_info.lower() for keyword in ["return", "yield"]):
            return "return_type"
        elif any(keyword in error_info.lower() for keyword in ["argument", "parameter"]):
            return "argument_type"
        elif any(keyword in error_info.lower() for keyword in ["attribute", "member"]):
            return "attribute_error"
        else:
            return "type_checking"
    
    def _categorize_errors(self, errors: List[AnalysisError]) -> Dict[str, Any]:
        """Categorize and organize errors for comprehensive presentation."""
        categorized = {
            "by_severity": defaultdict(list),
            "by_category": defaultdict(list),
            "by_file": defaultdict(list),
            "by_tool": defaultdict(list),
            "by_error_type": defaultdict(list),
            "statistics": {},
            "priority_errors": [],
            "fixable_errors": [],
            "security_critical": [],
            "performance_critical": [],
            "maintainability_issues": []
        }
        
        # Organize errors
        for error in errors:
            categorized["by_severity"][error.severity.name].append(error)
            categorized["by_category"][error.category or "uncategorized"].append(error)
            categorized["by_file"][error.file_path].append(error)
            categorized["by_tool"][error.tool_source].append(error)
            categorized["by_error_type"][error.error_type].append(error)
            
            # Special categorizations
            if error.severity in [DiagnosticSeverity.ERROR]:
                categorized["priority_errors"].append(error)
            
            if error.fix_suggestion:
                categorized["fixable_errors"].append(error)
            
            if error.category == ErrorCategory.SECURITY.value:
                categorized["security_critical"].append(error)
            
            if error.category == ErrorCategory.PERFORMANCE.value:
                categorized["performance_critical"].append(error)
            
            if error.category == ErrorCategory.MAINTAINABILITY.value:
                categorized["maintainability_issues"].append(error)
        
        # Calculate statistics
        categorized["statistics"] = {
            "total_errors": len(errors),
            "critical_errors": len([e for e in errors if e.severity == DiagnosticSeverity.ERROR]),
            "warnings": len([e for e in errors if e.severity == DiagnosticSeverity.WARNING]),
            "info_messages": len([e for e in errors if e.severity == DiagnosticSeverity.INFORMATION]),
            "files_with_errors": len(categorized["by_file"]),
            "tools_with_findings": len(categorized["by_tool"]),
            "categories_affected": len(categorized["by_category"]),
            "fixable_count": len(categorized["fixable_errors"]),
            "security_issues": len(categorized["security_critical"]),
            "performance_issues": len(categorized["performance_critical"])
        }
        
        return categorized
    
    def _find_entrypoints(self) -> List[Dict[str, Any]]:
        """Find entrypoints in the codebase."""
        entrypoints = []
        
        if self.graph_analysis:
            # Use graph-sitter to find entrypoints
            for func in self.graph_analysis.functions[:20]:  # Limit for performance
                func_name = func.get('name', '') if isinstance(func, dict) else getattr(func, 'name', '')
                if func_name in ['main', '__main__', 'run', 'start', 'execute']:
                    entrypoint = {
                        "type": "function",
                        "name": func_name,
                        "file_path": func.get('file_path', '') if isinstance(func, dict) else getattr(func, 'file_path', ''),
                        "line_number": func.get('line_number', 0) if isinstance(func, dict) else getattr(func, 'line_number', 0),
                        "category": "entrypoint"
                    }
                    entrypoints.append(entrypoint)
            
            # Look for classes that might be entrypoints
            for cls in self.graph_analysis.classes[:20]:
                cls_name = cls.get('name', '') if isinstance(cls, dict) else getattr(cls, 'name', '')
                if any(pattern in cls_name.lower() for pattern in ['app', 'main', 'server', 'client', 'runner']):
                    entrypoint = {
                        "type": "class",
                        "name": cls_name,
                        "file_path": cls.get('file_path', '') if isinstance(cls, dict) else getattr(cls, 'file_path', ''),
                        "line_number": cls.get('line_number', 0) if isinstance(cls, dict) else getattr(cls, 'line_number', 0),
                        "category": "entrypoint"
                    }
                    entrypoints.append(entrypoint)
        
        # Look for if __name__ == "__main__" patterns
        for file_info in (self.graph_analysis.files if self.graph_analysis else [])[:30]:
            file_path = file_info.get('path', '') if isinstance(file_info, dict) else getattr(file_info, 'path', '')
            if file_path and file_path.endswith('.py'):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    if 'if __name__ == "__main__"' in content:
                        entrypoint = {
                            "type": "script",
                            "name": os.path.basename(file_path),
                            "file_path": file_path,
                            "line_number": content.count('\n', 0, content.find('if __name__ == "__main__"')) + 1,
                            "category": "entrypoint"
                        }
                        entrypoints.append(entrypoint)
                        
                except Exception:
                    continue
        
        return entrypoints
    
    def _find_dead_code(self) -> List[Dict[str, Any]]:
        """Find dead code in the codebase."""
        dead_code = []
        
        if not self.graph_analysis:
            return dead_code
        
        # Find unused functions
        for func in self.graph_analysis.functions:
            func_name = func.get('name', '') if isinstance(func, dict) else getattr(func, 'name', '')
            if func_name:
                usages = self.graph_analysis._find_function_usages(func_name)
                if not usages and not func_name.startswith('_'):  # Ignore private functions
                    dead_code.append({
                        "type": "function",
                        "name": func_name,
                        "file_path": func.get('file_path', '') if isinstance(func, dict) else getattr(func, 'file_path', ''),
                        "line_number": func.get('line_number', 0) if isinstance(func, dict) else getattr(func, 'line_number', 0),
                        "category": "unused_function",
                        "context": "Not used by any other code"
                    })
        
        # Find unused classes
        for cls in self.graph_analysis.classes:
            cls_name = cls.get('name', '') if isinstance(cls, dict) else getattr(cls, 'name', '')
            if cls_name:
                usages = self.graph_analysis._find_symbol_usages(cls_name)
                if not usages and not cls_name.startswith('_'):
                    dead_code.append({
                        "type": "class",
                        "name": cls_name,
                        "file_path": cls.get('file_path', '') if isinstance(cls, dict) else getattr(cls, 'file_path', ''),
                        "line_number": cls.get('line_number', 0) if isinstance(cls, dict) else getattr(cls, 'line_number', 0),
                        "category": "unused_class",
                        "context": "Not used by any other code"
                    })
        
        # Find unused imports
        for imp in self.graph_analysis.imports:
            imp_name = imp.get('name', '') if isinstance(imp, dict) else getattr(imp, 'name', '')
            imp_file = imp.get('file_path', '') if isinstance(imp, dict) else getattr(imp, 'file_path', '')
            
            if imp_name and imp_file:
                # Check if the imported name is used in the file
                try:
                    with open(imp_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Simple check - look for the name in the file content
                    import_line_num = imp.get('line_number', 0) if isinstance(imp, dict) else getattr(imp, 'line_number', 0)
                    lines_after_import = content.splitlines()[import_line_num:]
                    
                    if not any(imp_name in line for line in lines_after_import):
                        dead_code.append({
                            "type": "import",
                            "name": imp_name,
                            "file_path": imp_file,
                            "line_number": import_line_num,
                            "category": "unused_import",
                            "context": f"Imported but never used in {os.path.basename(imp_file)}"
                        })
                        
                except Exception:
                    continue
        
        return dead_code
    
    def _analyze_dependencies(self) -> Dict[str, Any]:
        """Analyze project dependencies."""
        dependency_analysis = {
            "external_dependencies": [],
            "internal_dependencies": [],
            "circular_dependencies": [],
            "dependency_graph": {},
            "security_issues": [],
            "outdated_packages": [],
            "dependency_statistics": {}
        }
        
        try:
            # Analyze external dependencies
            if self.graph_analysis:
                for ext_mod in self.graph_analysis.external_modules:
                    mod_name = ext_mod.get('name', '') if isinstance(ext_mod, dict) else getattr(ext_mod, 'name', '')
                    if mod_name:
                        dependency_analysis["external_dependencies"].append({
                            "name": mod_name,
                            "usage_count": len(self.graph_analysis._find_symbol_usages(mod_name)),
                            "import_locations": [
                                imp.get('file_path', '') if isinstance(imp, dict) else getattr(imp, 'file_path', '')
                                for imp in self.graph_analysis.imports
                                if (imp.get('module', '') if isinstance(imp, dict) else getattr(imp, 'module', '')) == mod_name
                            ]
                        })
            
            # Check for circular dependencies using imports
            dependency_analysis["circular_dependencies"] = self._find_circular_dependencies()
            
            # Analyze requirements.txt or pyproject.toml
            dependency_analysis["dependency_statistics"] = self._analyze_dependency_files()
            
        except Exception as e:
            logging.error(f"Error in dependency analysis: {e}")
            dependency_analysis["error"] = str(e)
        
        return dependency_analysis
    
    def _find_circular_dependencies(self) -> List[Dict[str, Any]]:
        """Find circular dependencies in the codebase."""
        circular_deps = []
        
        if not self.graph_analysis:
            return circular_deps
        
        # Build a simple dependency graph
        deps_graph = defaultdict(set)
        
        for imp in self.graph_analysis.imports:
            imp_file = imp.get('file_path', '') if isinstance(imp, dict) else getattr(imp, 'file_path', '')
            imp_module = imp.get('module', '') if isinstance(imp, dict) else getattr(imp, 'module', '')
            
            if imp_file and imp_module and not imp.get('is_external', True):
                # Convert module name to file path (simplified)
                target_file = imp_module.replace('.', '/') + '.py'
                deps_graph[imp_file].add(target_file)
        
        # Simple cycle detection
        visited = set()
        rec_stack = set()
        
        def has_cycle(node, path):
            if node in rec_stack:
                # Found a cycle
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                return cycle
            
            if node in visited:
                return None
            
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in deps_graph.get(node, []):
                cycle = has_cycle(neighbor, path + [node])
                if cycle:
                    return cycle
            
            rec_stack.remove(node)
            return None
        
        for node in deps_graph:
            if node not in visited:
                cycle = has_cycle(node, [])
                if cycle:
                    circular_deps.append({
                        "cycle": cycle,
                        "type": "import_cycle",
                        "severity": "high",
                        "description": f"Circular import detected: {' -> '.join(cycle)}"
                    })
        
        return circular_deps
    
    def _analyze_dependency_files(self) -> Dict[str, Any]:
        """Analyze dependency configuration files."""
        stats = {
            "requirements_files": [],
            "pyproject_config": {},
            "total_dependencies": 0,
            "dev_dependencies": 0,
            "optional_dependencies": 0
        }
        
        # Check for requirements files
        req_files = ["requirements.txt", "requirements-dev.txt", "requirements-test.txt"]
        base_dir = self.target_path if os.path.isdir(self.target_path) else os.path.dirname(self.target_path)
        
        for req_file in req_files:
            req_path = os.path.join(base_dir, req_file)
            if os.path.exists(req_path):
                try:
                    with open(req_path, 'r') as f:
                        lines = [line.strip() for line in f.readlines() if line.strip() and not line.startswith('#')]
                    stats["requirements_files"].append({
                        "file": req_file,
                        "dependencies": len(lines),
                        "content": lines[:10]  # First 10 for sample
                    })
                    stats["total_dependencies"] += len(lines)
                except Exception:
                    pass
        
        # Check pyproject.toml
        pyproject_path = os.path.join(base_dir, "pyproject.toml")
        if os.path.exists(pyproject_path):
            try:
                import tomllib
                with open(pyproject_path, 'rb') as f:
                    pyproject_data = tomllib.load(f)
                
                project = pyproject_data.get("project", {})
                dependencies = project.get("dependencies", [])
                optional_deps = project.get("optional-dependencies", {})
                
                stats["pyproject_config"] = {
                    "dependencies": len(dependencies),
                    "optional_dependency_groups": len(optional_deps),
                    "total_optional": sum(len(deps) for deps in optional_deps.values())
                }
                stats["total_dependencies"] += len(dependencies)
                stats["optional_dependencies"] = sum(len(deps) for deps in optional_deps.values())
                
            except Exception as e:
                stats["pyproject_config"] = {"error": str(e)}
        
        return stats
    
    def _calculate_performance_metrics(self) -> Dict[str, Any]:
        """Calculate performance-related metrics."""
        metrics = {
            "complexity_analysis": {},
            "function_metrics": {},
            "class_metrics": {},
            "file_metrics": {},
            "performance_warnings": []
        }
        
        if not self.graph_analysis:
            return metrics
        
        try:
            # Function complexity metrics
            function_complexities = []
            for func in self.graph_analysis.functions:
                complexity = self.graph_analysis._calculate_function_complexity(func)
                function_complexities.append(complexity)
                
                if complexity > 15:  # High complexity threshold
                    func_name = func.get('name', '') if isinstance(func, dict) else getattr(func, 'name', '')
                    func_file = func.get('file_path', '') if isinstance(func, dict) else getattr(func, 'file_path', '')
                    
                    metrics["performance_warnings"].append({
                        "type": "high_complexity",
                        "function": func_name,
                        "file": func_file,
                        "complexity": complexity,
                        "recommendation": "Consider refactoring into smaller functions"
                    })
            
            metrics["function_metrics"] = {
                "total_functions": len(function_complexities),
                "average_complexity": sum(function_complexities) / len(function_complexities) if function_complexities else 0,
                "max_complexity": max(function_complexities) if function_complexities else 0,
                "high_complexity_count": len([c for c in function_complexities if c > 10])
            }
            
            # Class metrics
            class_complexities = []
            for cls in self.graph_analysis.classes:
                complexity = self.graph_analysis._calculate_class_complexity(cls)
                class_complexities.append(complexity)
            
            metrics["class_metrics"] = {
                "total_classes": len(class_complexities),
                "average_complexity": sum(class_complexities) / len(class_complexities) if class_complexities else 0,
                "max_complexity": max(class_complexities) if class_complexities else 0
            }
            
            # File metrics
            file_sizes = []
            for file_info in self.graph_analysis.files:
                size = file_info.get('line_count', 0) if isinstance(file_info, dict) else getattr(file_info, 'line_count', 0)
                file_sizes.append(size)
                
                if size > 500:  # Large file threshold
                    file_path = file_info.get('path', '') if isinstance(file_info, dict) else getattr(file_info, 'path', '')
                    metrics["performance_warnings"].append({
                        "type": "large_file",
                        "file": file_path,
                        "lines": size,
                        "recommendation": "Consider splitting into smaller modules"
                    })
            
            metrics["file_metrics"] = {
                "total_files": len(file_sizes),
                "average_file_size": sum(file_sizes) / len(file_sizes) if file_sizes else 0,
                "largest_file": max(file_sizes) if file_sizes else 0,
                "large_files_count": len([s for s in file_sizes if s > 300])
            }
            
        except Exception as e:
            logging.error(f"Error calculating performance metrics: {e}")
            metrics["error"] = str(e)
        
        return metrics
    
    def _calculate_quality_metrics(self) -> Dict[str, Any]:
        """Calculate code quality metrics."""
        metrics = {
            "documentation_coverage": 0.0,
            "test_coverage": 0.0,
            "maintainability_index": 0.0,
            "technical_debt_ratio": 0.0,
            "code_duplication": 0.0,
            "quality_gates": {},
            "recommendations": []
        }
        
        try:
            if self.graph_analysis:
                # Documentation coverage
                documented_functions = 0
                total_functions = len(self.graph_analysis.functions)
                
                for func in self.graph_analysis.functions:
                    func_file = func.get('file_path', '') if isinstance(func, dict) else getattr(func, 'file_path', '')
                    func_line = func.get('line_number', 0) if isinstance(func, dict) else getattr(func, 'line_number', 0)
                    
                    if func_file and func_line:
                        try:
                            with open(func_file, 'r', encoding='utf-8') as f:
                                lines = f.readlines()
                            
                            # Check for docstring after function definition
                            if func_line < len(lines):
                                for i in range(func_line, min(func_line + 5, len(lines))):
                                    if '"""' in lines[i] or "'''" in lines[i]:
                                        documented_functions += 1
                                        break
                        except Exception:
                            continue
                
                metrics["documentation_coverage"] = documented_functions / total_functions if total_functions > 0 else 0.0
                
                # Calculate maintainability index (simplified)
                avg_complexity = self.graph_analysis._calculate_complexity_score()
                total_loc = sum(f.get('line_count', 0) for f in self.graph_analysis.files)
                
                # Simplified maintainability index calculation
                metrics["maintainability_index"] = max(0, 100 - (avg_complexity * 10) - (total_loc / 1000))
                
                # Quality gates
                metrics["quality_gates"] = {
                    "documentation_gate": metrics["documentation_coverage"] >= 0.7,
                    "complexity_gate": avg_complexity <= 10,
                    "file_size_gate": all(f.get('line_count', 0) <= 500 for f in self.graph_analysis.files),
                    "maintainability_gate": metrics["maintainability_index"] >= 60
                }
                
                # Generate recommendations
                if metrics["documentation_coverage"] < 0.5:
                    metrics["recommendations"].append("Improve documentation coverage")
                if avg_complexity > 15:
                    metrics["recommendations"].append("Reduce code complexity")
                if metrics["maintainability_index"] < 50:
                    metrics["recommendations"].append("Focus on code maintainability")
        
        except Exception as e:
            logging.error(f"Error calculating quality metrics: {e}")
            metrics["error"] = str(e)
        
        return metrics
    
    def _build_dependency_graph(self) -> Dict[str, Any]:
        """Build comprehensive dependency graph."""
        graph = {
            "nodes": [],
            "edges": [],
            "clusters": [],
            "metrics": {}
        }
        
        if not self.graph_analysis:
            return graph
        
        try:
            # Add file nodes
            for file_info in self.graph_analysis.files:
                file_path = file_info.get('path', '') if isinstance(file_info, dict) else getattr(file_info, 'path', '')
                if file_path:
                    graph["nodes"].append({
                        "id": file_path,
                        "type": "file",
                        "label": os.path.basename(file_path),
                        "size": file_info.get('line_count', 0) if isinstance(file_info, dict) else getattr(file_info, 'line_count', 0)
                    })
            
            # Add dependency edges
            for imp in self.graph_analysis.imports:
                source_file = imp.get('file_path', '') if isinstance(imp, dict) else getattr(imp, 'file_path', '')
                target_module = imp.get('module', '') if isinstance(imp, dict) else getattr(imp, 'module', '')
                
                if source_file and target_module:
                    # Convert module to file path (simplified)
                    if not imp.get('is_external', True):
                        target_file = target_module.replace('.', '/') + '.py'
                        graph["edges"].append({
                            "source": source_file,
                            "target": target_file,
                            "type": "import",
                            "weight": 1
                        })
            
            # Calculate metrics
            graph["metrics"] = {
                "total_nodes": len(graph["nodes"]),
                "total_edges": len(graph["edges"]),
                "average_dependencies": len(graph["edges"]) / len(graph["nodes"]) if graph["nodes"] else 0
            }
            
        except Exception as e:
            logging.error(f"Error building dependency graph: {e}")
            graph["error"] = str(e)
        
        return graph
    
    def _build_inheritance_hierarchy(self) -> Dict[str, Any]:
        """Build inheritance hierarchy."""
        hierarchy = {
            "inheritance_trees": [],
            "abstract_classes": [],
            "leaf_classes": [],
            "metrics": {}
        }
        
        if not self.graph_analysis:
            return hierarchy
        
        try:
            # Build inheritance relationships
            class_inheritance = {}
            for cls in self.graph_analysis.classes:
                cls_name = cls.get('name', '') if isinstance(cls, dict) else getattr(cls, 'name', '')
                bases = cls.get('bases', []) if isinstance(cls, dict) else getattr(cls, 'bases', [])
                
                if cls_name:
                    class_inheritance[cls_name] = {
                        "bases": bases,
                        "file_path": cls.get('file_path', '') if isinstance(cls, dict) else getattr(cls, 'file_path', ''),
                        "line_number": cls.get('line_number', 0) if isinstance(cls, dict) else getattr(cls, 'line_number', 0)
                    }
            
            # Find inheritance chains
            for cls_name, cls_info in class_inheritance.items():
                if cls_info["bases"]:
                    chain = [cls_name]
                    current = cls_name
                    
                    while current in class_inheritance and class_inheritance[current]["bases"]:
                        bases = class_inheritance[current]["bases"]
                        if bases and bases[0] in class_inheritance:
                            current = bases[0]
                            chain.append(current)
                        else:
                            break
                    
                    if len(chain) > 1:
                        hierarchy["inheritance_trees"].append({
                            "chain": chain,
                            "depth": len(chain),
                            "root_class": chain[-1],
                            "leaf_class": chain[0]
                        })
            
            # Calculate metrics
            hierarchy["metrics"] = {
                "total_classes": len(class_inheritance),
                "classes_with_inheritance": len([c for c in class_inheritance.values() if c["bases"]]),
                "max_inheritance_depth": max([len(tree["chain"]) for tree in hierarchy["inheritance_trees"]], default=0),
                "average_inheritance_depth": sum([len(tree["chain"]) for tree in hierarchy["inheritance_trees"]]) / len(hierarchy["inheritance_trees"]) if hierarchy["inheritance_trees"] else 0
            }
            
        except Exception as e:
            logging.error(f"Error building inheritance hierarchy: {e}")
            hierarchy["error"] = str(e)
        
        return hierarchy
    
    def _build_call_graph(self) -> Dict[str, Any]:
        """Build function call graph."""
        call_graph = {
            "nodes": [],
            "edges": [],
            "metrics": {},
            "hotspots": [],
            "call_chains": []
        }
        
        if not self.graph_analysis:
            return call_graph
        
        try:
            # Add function nodes
            for func in self.graph_analysis.functions:
                func_name = func.get('name', '') if isinstance(func, dict) else getattr(func, 'name', '')
                if func_name:
                    call_graph["nodes"].append({
                        "id": func_name,
                        "type": "function",
                        "file": func.get('file_path', '') if isinstance(func, dict) else getattr(func, 'file_path', ''),
                        "complexity": self.graph_analysis._calculate_function_complexity(func),
                        "parameters": len(func.get('parameters', []) if isinstance(func, dict) else getattr(func, 'parameters', []))
                    })
            
            # Simple call relationship detection (would be more sophisticated with graph-sitter)
            for func in self.graph_analysis.functions:
                func_name = func.get('name', '') if isinstance(func, dict) else getattr(func, 'name', '')
                func_file = func.get('file_path', '') if isinstance(func, dict) else getattr(func, 'file_path', '')
                
                if func_file and func_name:
                    try:
                        with open(func_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        # Look for function calls (simplified)
                        for other_func in self.graph_analysis.functions:
                            other_name = other_func.get('name', '') if isinstance(other_func, dict) else getattr(other_func, 'name', '')
                            if other_name and other_name != func_name and f"{other_name}(" in content:
                                call_graph["edges"].append({
                                    "source": func_name,
                                    "target": other_name,
                                    "type": "function_call"
                                })
                    except Exception:
                        continue
            
            # Find hotspots (most called functions)
            call_counts = Counter(edge["target"] for edge in call_graph["edges"])
            call_graph["hotspots"] = [
                {"function": func, "call_count": count}
                for func, count in call_counts.most_common(10)
            ]
            
            # Calculate metrics
            call_graph["metrics"] = {
                "total_functions": len(call_graph["nodes"]),
                "total_calls": len(call_graph["edges"]),
                "average_calls_per_function": len(call_graph["edges"]) / len(call_graph["nodes"]) if call_graph["nodes"] else 0,
                "most_called_function": call_graph["hotspots"][0]["function"] if call_graph["hotspots"] else None
            }
            
        except Exception as e:
            logging.error(f"Error building call graph: {e}")
            call_graph["error"] = str(e)
        
        return call_graph
    
    def _build_import_graph(self) -> Dict[str, Any]:
        """Build import dependency graph."""
        import_graph = {
            "internal_imports": [],
            "external_imports": [],
            "import_clusters": [],
            "unused_imports": [],
            "metrics": {}
        }
        
        if not self.graph_analysis:
            return import_graph
        
        try:
            # Categorize imports
            for imp in self.graph_analysis.imports:
                imp_data = {
                    "module": imp.get('module', '') if isinstance(imp, dict) else getattr(imp, 'module', ''),
                    "name": imp.get('name', '') if isinstance(imp, dict) else getattr(imp, 'name', ''),
                    "file_path": imp.get('file_path', '') if isinstance(imp, dict) else getattr(imp, 'file_path', ''),
                    "line_number": imp.get('line_number', 0) if isinstance(imp, dict) else getattr(imp, 'line_number', 0)
                }
                
                if imp.get('is_external', True):
                    import_graph["external_imports"].append(imp_data)
                else:
                    import_graph["internal_imports"].append(imp_data)
            
            # Find import clusters (files that import similar modules)
            external_by_file = defaultdict(set)
            for imp in import_graph["external_imports"]:
                external_by_file[imp["file_path"]].add(imp["module"])
            
            # Group files with similar import patterns
            import_patterns = defaultdict(list)
            for file_path, modules in external_by_file.items():
                pattern_key = tuple(sorted(modules))
                import_patterns[pattern_key].append(file_path)
            
            for pattern, files in import_patterns.items():
                if len(files) > 1:
                    import_graph["import_clusters"].append({
                        "pattern": list(pattern),
                        "files": files,
                        "cluster_size": len(files)
                    })
            
            # Calculate metrics
            import_graph["metrics"] = {
                "total_imports": len(self.graph_analysis.imports),
                "external_imports": len(import_graph["external_imports"]),
                "internal_imports": len(import_graph["internal_imports"]),
                "unique_external_modules": len(set(imp["module"] for imp in import_graph["external_imports"])),
                "import_clusters": len(import_graph["import_clusters"]),
                "average_imports_per_file": len(self.graph_analysis.imports) / len(self.graph_analysis.files) if self.graph_analysis.files else 0
            }
            
        except Exception as e:
            logging.error(f"Error building import graph: {e}")
            import_graph["error"] = str(e)
        
        return import_graph
    
    def _summarize_lsp_diagnostics(self, diagnostics_by_file: Dict) -> Dict[str, Any]:
        """Summarize LSP diagnostics."""
        summary = {
            "total_files_with_errors": len(diagnostics_by_file),
            "severity_breakdown": defaultdict(int),
            "error_sources": defaultdict(int),
            "most_problematic_files": []
        }
        
        file_error_counts = []
        
        for file_path, diagnostics in diagnostics_by_file.items():
            error_count = len(diagnostics)
            file_error_counts.append((file_path, error_count))
            
            for diagnostic in diagnostics:
                severity = diagnostic.get("severity", 1)
                source = diagnostic.get("source", "unknown")
                
                summary["severity_breakdown"][severity] += 1
                summary["error_sources"][source] += 1
        
        # Sort files by error count
        file_error_counts.sort(key=lambda x: x[1], reverse=True)
        summary["most_problematic_files"] = file_error_counts[:10]
        
        return summary
    
    def _generate_comprehensive_summary(self, analysis_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive analysis summary."""
        summary = {
            "overview": {},
            "critical_findings": [],
            "recommendations": [],
            "quality_score": 0.0,
            "risk_assessment": {},
            "action_items": []
        }
        
        try:
            # Overview statistics
            total_errors = len(analysis_results.get("errors", []))
            categorized = analysis_results.get("categorized_errors", {})
            
            summary["overview"] = {
                "total_errors": total_errors,
                "critical_errors": categorized.get("statistics", {}).get("critical_errors", 0),
                "warnings": categorized.get("statistics", {}).get("warnings", 0),
                "files_analyzed": len(analysis_results.get("graph_sitter_analysis", {}).get("files_analysis", {})),
                "tools_used": len(analysis_results.get("metadata", {}).get("tools_used", [])),
                "analysis_duration": analysis_results.get("metadata", {}).get("analysis_duration", 0)
            }
            
            # Critical findings
            priority_errors = categorized.get("priority_errors", [])
            security_issues = categorized.get("security_critical", [])
            
            summary["critical_findings"] = [
                f"Found {len(priority_errors)} critical errors",
                f"Identified {len(security_issues)} security issues",
                f"Detected {len(analysis_results.get('dead_code', []))} dead code instances"
            ]
            
            # Risk assessment
            summary["risk_assessment"] = {
                "security_risk": "high" if len(security_issues) > 5 else "medium" if len(security_issues) > 0 else "low",
                "maintenance_risk": "high" if total_errors > 100 else "medium" if total_errors > 20 else "low",
                "quality_risk": "high" if categorized.get("statistics", {}).get("critical_errors", 0) > 10 else "low"
            }
            
            # Calculate quality score
            quality_metrics = analysis_results.get("quality_metrics", {})
            performance_metrics = analysis_results.get("performance_metrics", {})
            
            doc_coverage = quality_metrics.get("documentation_coverage", 0.0)
            maintainability = quality_metrics.get("maintainability_index", 0.0)
            error_penalty = min(total_errors * 0.5, 50)  # Cap penalty at 50 points
            
            summary["quality_score"] = max(0.0, (doc_coverage * 30) + (maintainability * 0.7) - error_penalty)
            
            # Generate recommendations
            if doc_coverage < 0.5:
                summary["recommendations"].append("Improve code documentation")
            if len(security_issues) > 0:
                summary["recommendations"].append("Address security vulnerabilities")
            if total_errors > 50:
                summary["recommendations"].append("Reduce overall error count")
            if len(analysis_results.get("dead_code", [])) > 10:
                summary["recommendations"].append("Remove dead code")
            
            # Action items
            summary["action_items"] = [
                {
                    "priority": "high",
                    "category": "security",
                    "action": f"Fix {len(security_issues)} security issues",
                    "estimated_effort": "medium"
                },
                {
                    "priority": "medium", 
                    "category": "quality",
                    "action": f"Address {categorized.get('statistics', {}).get('critical_errors', 0)} critical errors",
                    "estimated_effort": "high"
                },
                {
                    "priority": "low",
                    "category": "maintenance",
                    "action": f"Clean up {len(analysis_results.get('dead_code', []))} dead code items",
                    "estimated_effort": "low"
                }
            ]
            
        except Exception as e:
            logging.error(f"Error generating summary: {e}")
            summary["error"] = str(e)
        
        return summary


class ErrorDatabase:
    """Database for storing and querying analysis errors."""
    
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()
    
    def _create_tables(self):
        """Create database tables for storing errors."""
        cursor = self.connection.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analysis_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                line_number INTEGER,
                column_number INTEGER,
                error_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                tool_source TEXT NOT NULL,
                category TEXT,
                subcategory TEXT,
                error_code TEXT,
                confidence REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fixed BOOLEAN DEFAULT FALSE
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analysis_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_path TEXT NOT NULL,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                total_errors INTEGER,
                tools_used TEXT,
                config_hash TEXT
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_path ON analysis_errors(file_path);
            CREATE INDEX IF NOT EXISTS idx_severity ON analysis_errors(severity);
            CREATE INDEX IF NOT EXISTS idx_category ON analysis_errors(category);
            CREATE INDEX IF NOT EXISTS idx_tool_source ON analysis_errors(tool_source);
        """)
        
        self.connection.commit()
    
    def store_errors(self, errors: List[AnalysisError], session_id: int):
        """Store errors in the database."""
        cursor = self.connection.cursor()
        
        for error in errors:
            cursor.execute("""
                INSERT INTO analysis_errors 
                (file_path, line_number, column_number, error_type, severity, message, 
                 tool_source, category, subcategory, error_code, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                error.file_path,
                error.line_number,
                error.column_number,
                error.error_type,
                error.severity.name,
                error.message,
                error.tool_source,
                error.category,
                error.subcategory,
                error.error_code,
                error.confidence
            ))
        
        self.connection.commit()
    
    def create_session(self, target_path: str, tools_used: List[str], config: Dict) -> int:
        """Create a new analysis session."""
        cursor = self.connection.cursor()
        
        config_hash = hashlib.md5(json.dumps(config, sort_keys=True).encode()).hexdigest()
        
        cursor.execute("""
            INSERT INTO analysis_sessions (target_path, start_time, tools_used, config_hash)
            VALUES (?, ?, ?, ?)
        """, (target_path, time.strftime("%Y-%m-%d %H:%M:%S"), json.dumps(tools_used), config_hash))
        
        self.connection.commit()
        return cursor.lastrowid
    
    def update_session(self, session_id: int, total_errors: int):
        """Update session with final statistics."""
        cursor = self.connection.cursor()
        
        cursor.execute("""
            UPDATE analysis_sessions 
            SET end_time = ?, total_errors = ?
            WHERE id = ?
        """, (time.strftime("%Y-%m-%d %H:%M:%S"), total_errors, session_id))
        
        self.connection.commit()
    
    def query_errors(self, filters: Dict[str, Any]) -> List[Dict]:
        """Query errors with filters."""
        cursor = self.connection.cursor()
        
        query = "SELECT * FROM analysis_errors WHERE 1=1"
        params = []
        
        if "file_path" in filters:
            query += " AND file_path = ?"
            params.append(filters["file_path"])
        
        if "severity" in filters:
            query += " AND severity = ?"
            params.append(filters["severity"])
        
        if "category" in filters:
            query += " AND category = ?"
            params.append(filters["category"])
        
        if "tool_source" in filters:
            query += " AND tool_source = ?"
            params.append(filters["tool_source"])
        
        cursor.execute(query, params)
        columns = [description[0] for description in cursor.description]
        
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


class ReportGenerator:
    """Generate comprehensive analysis reports in multiple formats."""
    
    def __init__(self, analysis_results: Dict[str, Any]):
        self.results = analysis_results
    
    def generate_terminal_report(self) -> str:
        """Generate comprehensive terminal report."""
        lines = []
        
        # Header
        lines.extend([
            "="*100,
            "COMPREHENSIVE PYTHON CODE ANALYSIS REPORT",
            "="*100,
            ""
        ])
        
        # Metadata
        metadata = self.results.get("metadata", {})
        lines.extend([
            f"Target: {metadata.get('target_path', 'Unknown')}",
            f"Analysis Duration: {metadata.get('analysis_duration', 0):.2f}s",
            f"Tools Used: {', '.join(metadata.get('tools_used', []))}",
            f"Python Version: {metadata.get('python_version', 'Unknown')}",
            ""
        ])
        
        # Graph-sitter analysis summary
        gs_analysis = self.results.get("graph_sitter_analysis", {})
        if gs_analysis and "codebase_summary" in gs_analysis:
            summary = gs_analysis["codebase_summary"]
            lines.extend([
                "CODEBASE STRUCTURE:",
                "-" * 50,
                f"Files: {summary.get('total_files', 0)}",
                f"Functions: {summary.get('total_functions', 0)}",
                f"Classes: {summary.get('total_classes', 0)}",
                f"Imports: {summary.get('total_imports', 0)}",
                f"External Dependencies: {summary.get('external_dependencies', 0)}",
                f"Lines of Code: {summary.get('lines_of_code', 0)}",
                f"Complexity Score: {summary.get('complexity_score', 0):.2f}",
                ""
            ])
        
        # Entrypoints
        entrypoints = self.results.get("entrypoints", [])
        if entrypoints:
            lines.extend([
                f"ENTRYPOINTS: [{len(entrypoints)}]",
                "-" * 50
            ])
            for i, entry in enumerate(entrypoints[:10], 1):
                entry_type = entry.get("type", "unknown").title()
                entry_name = entry.get("name", "unknown")
                entry_file = entry.get("file_path", "")
                lines.append(f"{i}. {entry_type}: {entry_name} [{os.path.basename(entry_file)}]")
            lines.append("")
        
        # Dead code
        dead_code = self.results.get("dead_code", [])
        if dead_code:
            dead_by_type = defaultdict(int)
            for item in dead_code:
                dead_by_type[item.get("category", "unknown")] += 1
            
            lines.extend([
                f"DEAD CODE: {len(dead_code)} [{', '.join(f'{cat.title()}: {count}' for cat, count in dead_by_type.items())}]",
                "-" * 50
            ])
            for i, item in enumerate(dead_code[:20], 1):
                item_type = item.get("type", "unknown")
                item_name = item.get("name", "unknown")
                item_file = os.path.basename(item.get("file_path", ""))
                context = item.get("context", "")
                lines.append(f"{i}. {item_type.title()}: '{item_name}' [{item_file}] - {context}")
            
            if len(dead_code) > 20:
                lines.append(f"... and {len(dead_code) - 20} more items")
            lines.append("")
        
        # Error summary
        categorized = self.results.get("categorized_errors", {})
        stats = categorized.get("statistics", {})
        
        if stats:
            lines.extend([
                f"ERRORS: {stats.get('total_errors', 0)} "
                f"[Critical: {stats.get('critical_errors', 0)}] "
                f"[Warnings: {stats.get('warnings', 0)}] "
                f"[Info: {stats.get('info_messages', 0)}]",
                "-" * 50
            ])
            
            # List errors by severity and tool
            by_tool = categorized.get("by_tool", {})
            for i, (tool, tool_errors) in enumerate(by_tool.items(), 1):
                if tool_errors:
                    critical_count = len([e for e in tool_errors if e.severity == DiagnosticSeverity.ERROR])
                    warning_count = len([e for e in tool_errors if e.severity == DiagnosticSeverity.WARNING])
                    
                    lines.append(f"{i}. {tool.upper()}: {len(tool_errors)} issues "
                               f"[Critical: {critical_count}, Warnings: {warning_count}]")
            
            lines.append("")
            
            # Detailed error listing by category
            by_category = categorized.get("by_category", {})
            for category, category_errors in by_category.items():
                if category_errors:
                    lines.extend([
                        f"{category.upper()} ERRORS: {len(category_errors)}",
                        "-" * 30
                    ])
                    
                    # Group by file for better organization
                    errors_by_file = defaultdict(list)
                    for error in category_errors[:50]:  # Limit display
                        errors_by_file[error.file_path].append(error)
                    
                    for file_path, file_errors in list(errors_by_file.items())[:10]:  # Limit files
                        rel_path = os.path.relpath(file_path, self.results.get("metadata", {}).get("target_path", ""))
                        lines.append(f"  {rel_path}: {len(file_errors)} issues")
                        
                        for error in file_errors[:5]:  # Limit errors per file
                            severity_icon = {
                                DiagnosticSeverity.ERROR: "⚠️",
                                DiagnosticSeverity.WARNING: "👉",
                                DiagnosticSeverity.INFORMATION: "🔍",
                                DiagnosticSeverity.HINT: "💡"
                            }.get(error.severity, "•")
                            
                            location = f"Line {error.line_number}" if error.line_number else "Unknown location"
                            tool_info = f"[{error.tool_source}]"
                            
                            lines.append(f"    {severity_icon} {location}: {error.message[:80]}{'...' if len(error.message) > 80 else ''} {tool_info}")
                        
                        if len(file_errors) > 5:
                            lines.append(f"    ... and {len(file_errors) - 5} more issues in this file")
                    
                    if len(errors_by_file) > 10:
                        lines.append(f"  ... and {len(errors_by_file) - 10} more files with {category} errors")
                    
                    lines.append("")
            
            # Performance and quality insights
            perf_metrics = self.results.get("performance_metrics", {})
            quality_metrics = self.results.get("quality_metrics", {})
            
            if perf_metrics.get("function_metrics"):
                func_metrics = perf_metrics["function_metrics"]
                lines.extend([
                    "PERFORMANCE INSIGHTS:",
                    "-" * 30,
                    f"Average Function Complexity: {func_metrics.get('average_complexity', 0):.2f}",
                    f"High Complexity Functions: {func_metrics.get('high_complexity_count', 0)}",
                    f"Largest File: {perf_metrics.get('file_metrics', {}).get('largest_file', 0)} lines",
                    ""
                ])
            
            if quality_metrics:
                lines.extend([
                    "QUALITY METRICS:",
                    "-" * 30,
                    f"Documentation Coverage: {quality_metrics.get('documentation_coverage', 0)*100:.1f}%",
                    f"Maintainability Index: {quality_metrics.get('maintainability_index', 0):.1f}",
                    f"Quality Score: {self.results.get('summary', {}).get('quality_score', 0):.1f}/100",
                    ""
                ])
            
            # Recommendations
            recommendations = self.results.get("summary", {}).get("recommendations", [])
            if recommendations:
                lines.extend([
                    "RECOMMENDATIONS:",
                    "-" * 30
                ])
                for i, rec in enumerate(recommendations, 1):
                    lines.append(f"{i}. {rec}")
                lines.append("")
        
        except Exception as e:
            lines.extend([
                "ERROR GENERATING SUMMARY:",
                str(e),
                ""
            ])
        
        lines.append("="*100)
        return "\n".join(lines)
    
    def generate_json_report(self) -> str:
        """Generate JSON report."""
        return json.dumps(self.results, indent=2, default=str)
    
    def generate_html_report(self) -> str:
        """Generate comprehensive HTML report."""
        html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Comprehensive Code Analysis Report</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            line-height: 1.6;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 {
            margin: 0;
            font-size: 2.5em;
            font-weight: 300;
        }
        .header p {
            margin: 10px 0 0 0;
            opacity: 0.9;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f8f9fa;
        }
        .metric-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
        }
        .metric-value {
            font-size: 2em;
            font-weight: bold;
            color: #333;
        }
        .metric-label {
            color: #666;
            font-size: 0.9em;
            margin-top: 5px;
        }
        .section {
            padding: 30px;
            border-bottom: 1px solid #eee;
        }
        .section h2 {
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }
        .error-list {
            list-style: none;
            padding: 0;
        }
        .error-item {
            background: #f8f9fa;
            margin: 10px 0;
            padding: 15px;
            border-left: 4px solid #dc3545;
            border-radius: 4px;
        }
        .error-item.warning {
            border-left-color: #ffc107;
        }
        .error-item.info {
            border-left-color: #17a2b8;
        }
        .error-meta {
            font-size: 0.9em;
            color: #666;
            margin-top: 5px;
        }
        .category-section {
            margin: 20px 0;
        }
        .category-header {
            background: #e9ecef;
            padding: 10px 15px;
            border-radius: 4px;
            font-weight: bold;
            color: #495057;
        }
        .progress-bar {
            height: 20px;
            background: #e9ecef;
            border-radius: 10px;
            overflow: hidden;
            margin: 10px 0;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #28a745, #20c997);
            transition: width 0.3s ease;
        }
        .recommendations {
            background: #d4edda;
            border: 1px solid #c3e6cb;
            border-radius: 4px;
            padding: 15px;
            margin: 20px 0;
        }
        .recommendations h3 {
            color: #155724;
            margin-top: 0;
        }
        .tag {
            display: inline-block;
            background: #6c757d;
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.8em;
            margin: 2px;
        }
        .tag.critical { background: #dc3545; }
        .tag.warning { background: #ffc107; color: #333; }
        .tag.info { background: #17a2b8; }
        .expandable {
            cursor: pointer;
            user-select: none;
        }
        .expandable:hover {
            background-color: #f0f0f0;
        }
        .collapsed {
            display: none;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }
        th {
            background-color: #f2f2f2;
            font-weight: bold;
        }
        .file-tree {
            font-family: monospace;
            background: #f8f9fa;
            padding: 20px;
            border-radius: 4px;
            white-space: pre-line;
        }
    </style>
    <script>
        function toggleSection(id) {
            const element = document.getElementById(id);
            if (element) {
                element.classList.toggle('collapsed');
            }
        }
        
        function filterErrors(category) {
            const errorSections = document.querySelectorAll('.error-category');
            errorSections.forEach(section => {
                if (category === 'all' || section.dataset.category === category) {
                    section.style.display = 'block';
                } else {
                    section.style.display = 'none';
                }
            });
        }
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Code Analysis Report</h1>
            <p>Target: {target_path}</p>
            <p>Generated on {timestamp}</p>
        </div>
        
        <div class="metrics-grid">
            {metrics_cards}
        </div>
        
        <div class="section">
            <h2>📊 Analysis Overview</h2>
            {overview_content}
        </div>
        
        <div class="section">
            <h2>🎯 Entrypoints</h2>
            {entrypoints_content}
        </div>
        
        <div class="section">
            <h2>💀 Dead Code Analysis</h2>
            {dead_code_content}
        </div>
        
        <div class="section">
            <h2>🚨 Error Analysis</h2>
            {error_analysis_content}
        </div>
        
        <div class="section">
            <h2>📈 Performance Metrics</h2>
            {performance_content}
        </div>
        
        <div class="section">
            <h2>🔒 Security Analysis</h2>
            {security_content}
        </div>
        
        <div class="section">
            <h2>📋 Recommendations</h2>
            {recommendations_content}
        </div>
    </div>
</body>
</html>
        """
        
        # Generate content sections
        metadata = self.results.get("metadata", {})
        categorized = self.results.get("categorized_errors", {})
        stats = categorized.get("statistics", {})
        
        # Metrics cards
        metrics_cards = self._generate_metrics_cards(stats)
        
        # Overview content
        overview_content = self._generate_overview_content()
        
        # Entrypoints content
        entrypoints_content = self._generate_entrypoints_content()
        
        # Dead code content
        dead_code_content = self._generate_dead_code_content()
        
        # Error analysis content
        error_analysis_content = self._generate_error_analysis_content()
        
        # Performance content
        performance_content = self._generate_performance_content()
        
        # Security content
        security_content = self._generate_security_content()
        
        # Recommendations content
        recommendations_content = self._generate_recommendations_content()
        
        # Fill template
        html_report = html_template.format(
            target_path=metadata.get("target_path", "Unknown"),
            timestamp=metadata.get("analysis_start_time", "Unknown"),
            metrics_cards=metrics_cards,
            overview_content=overview_content,
            entrypoints_content=entrypoints_content,
            dead_code_content=dead_code_content,
            error_analysis_content=error_analysis_content,
            performance_content=performance_content,
            security_content=security_content,
            recommendations_content=recommendations_content
        )
        
        return html_report
    
    def _generate_metrics_cards(self, stats: Dict) -> str:
        """Generate HTML for metrics cards."""
        cards = []
        
        metrics = [
            ("Total Errors", stats.get("total_errors", 0), "dc3545"),
            ("Critical", stats.get("critical_errors", 0), "dc3545"),
            ("Warnings", stats.get("warnings", 0), "ffc107"),
            ("Files Analyzed", stats.get("files_with_errors", 0), "28a745"),
            ("Tools Used", stats.get("tools_with_findings", 0), "17a2b8"),
            ("Categories", stats.get("categories_affected", 0), "6f42c1"),
            ("Fixable", stats.get("fixable_count", 0), "28a745"),
            ("Security Issues", stats.get("security_issues", 0), "dc3545")
        ]
        
        for label, value, color in metrics:
            cards.append(f"""
                <div class="metric-card">
                    <div class="metric-value" style="color: #{color}">{value}</div>
                    <div class="metric-label">{label}</div>
                </div>
            """)
        
        return "".join(cards)
    
    def _generate_overview_content(self) -> str:
        """Generate overview content."""
        gs_analysis = self.results.get("graph_sitter_analysis", {})
        summary = self.results.get("summary", {})
        
        content = []
        
        if gs_analysis.get("codebase_summary"):
            codebase_sum = gs_analysis["codebase_summary"]
            content.append(f"""
                <div class="file-tree">
                    <strong>Codebase Structure:</strong>
                    📁 Total Files: {codebase_sum.get('total_files', 0)}
                    🔧 Functions: {codebase_sum.get('total_functions', 0)}
                    🏗️  Classes: {codebase_sum.get('total_classes', 0)}
                    📦 Imports: {codebase_sum.get('total_imports', 0)}
                    🌐 External Dependencies: {codebase_sum.get('external_dependencies', 0)}
                    📏 Lines of Code: {codebase_sum.get('lines_of_code', 0):,}
                    📊 Complexity Score: {codebase_sum.get('complexity_score', 0):.2f}
                </div>
            """)
        
        # Quality score with progress bar
        quality_score = summary.get("quality_score", 0)
        content.append(f"""
            <div>
                <h3>Quality Score: {quality_score:.1f}/100</h3>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {quality_score}%"></div>
                </div>
            </div>
        """)
        
        return "".join(content)
    
    def _generate_entrypoints_content(self) -> str:
        """Generate entrypoints content."""
        entrypoints = self.results.get("entrypoints", [])
        
        if not entrypoints:
            return "<p>No entrypoints detected in the codebase.</p>"
        
        content = [f"<p>Found {len(entrypoints)} entrypoints in the codebase:</p>"]
        content.append("<table>")
        content.append("<tr><th>Type</th><th>Name</th><th>File</th><th>Line</th></tr>")
        
        for entry in entrypoints:
            content.append(f"""
                <tr>
                    <td><span class="tag">{entry.get('type', 'unknown')}</span></td>
                    <td><code>{entry.get('name', 'unknown')}</code></td>
                    <td>{os.path.basename(entry.get('file_path', ''))}</td>
                    <td>{entry.get('line_number', 'N/A')}</td>
                </tr>
            """)
        
        content.append("</table>")
        return "".join(content)
    
    def _generate_dead_code_content(self) -> str:
        """Generate dead code content."""
        dead_code = self.results.get("dead_code", [])
        
        if not dead_code:
            return "<p>No dead code detected. Great job!</p>"
        
        # Group by type
        by_type = defaultdict(list)
        for item in dead_code:
            by_type[item.get("category", "unknown")].append(item)
        
        content = [f"<p>Found {len(dead_code)} dead code items:</p>"]
        
        for category, items in by_type.items():
            content.append(f"""
                <div class="category-section">
                    <div class="category-header">{category.replace('_', ' ').title()}: {len(items)} items</div>
                    <ul class="error-list">
            """)
            
            for item in items[:20]:  # Limit display
                content.append(f"""
                    <li class="error-item info">
                        <strong>{item.get('type', 'unknown').title()}: {item.get('name', 'unknown')}</strong>
                        <div class="error-meta">
                            📁 {os.path.basename(item.get('file_path', ''))} 
                            📍 Line {item.get('line_number', 'N/A')}
                            💭 {item.get('context', '')}
                        </div>
                    </li>
                """)
            
            if len(items) > 20:
                content.append(f"<li>... and {len(items) - 20} more items</li>")
            
            content.extend(["</ul>", "</div>"])
        
        return "".join(content)
    
    def _generate_error_analysis_content(self) -> str:
        """Generate error analysis content."""
        categorized = self.results.get("categorized_errors", {})
        
        content = []
        
        # Error category filter buttons
        content.append("""
            <div style="margin-bottom: 20px;">
                <button onclick="filterErrors('all')" style="margin-right: 10px; padding: 8px 16px; border: none; background: #007bff; color: white; border-radius: 4px; cursor: pointer;">All</button>
        """)
        
        by_category = categorized.get("by_category", {})
        for category in by_category.keys():
            content.append(f"""
                <button onclick="filterErrors('{category}')" style="margin-right: 10px; padding: 8px 16px; border: none; background: #6c757d; color: white; border-radius: 4px; cursor: pointer;">{category.title()}</button>
            """)
        
        content.append("</div>")
        
        # Error sections by category
        for category, errors in by_category.items():
            content.append(f"""
                <div class="error-category" data-category="{category}">
                    <div class="category-header">{category.upper()}: {len(errors)} issues</div>
                    <ul class="error-list">
            """)
            
            # Group errors by file for better organization
            errors_by_file = defaultdict(list)
            for error in errors[:100]:  # Limit for performance
                errors_by_file[error.file_path].append(error)
            
            for file_path, file_errors in list(errors_by_file.items())[:15]:  # Limit files shown
                content.append(f"""
                    <li class="expandable" onclick="toggleSection('file-{hashlib.md5(file_path.encode()).hexdigest()}')">
                        <strong>📁 {os.path.basename(file_path)}</strong> ({len(file_errors)} issues)
                    </li>
                    <div id="file-{hashlib.md5(file_path.encode()).hexdigest()}" class="collapsed">
                """)
                
                for error in file_errors[:10]:  # Limit errors per file
                    severity_class = {
                        DiagnosticSeverity.ERROR: "error",
                        DiagnosticSeverity.WARNING: "warning", 
                        DiagnosticSeverity.INFORMATION: "info"
                    }.get(error.severity, "info")
                    
                    severity_icon = {
                        DiagnosticSeverity.ERROR: "⚠️",
                        DiagnosticSeverity.WARNING: "👉",
                        DiagnosticSeverity.INFORMATION: "🔍"
                    }.get(error.severity, "•")
                    
                    content.append(f"""
                        <div class="error-item {severity_class}">
                            <strong>{severity_icon} {error.message}</strong>
                            <div class="error-meta">
                                📍 Line {error.line_number or 'N/A'}
                                🔧 {error.tool_source}
                                {f'🏷️ {error.error_code}' if error.error_code else ''}
                                {f'💡 {error.fix_suggestion}' if error.fix_suggestion else ''}
                            </div>
                        </div>
                    """)
                
                if len(file_errors) > 10:
                    content.append(f"<p>... and {len(file_errors) - 10} more errors in this file</p>")
                
                content.append("</div>")
            
            content.extend(["</ul>", "</div>"])
        
        return "".join(content)
    
    def _generate_performance_content(self) -> str:
        """Generate performance analysis content."""
        perf_metrics = self.results.get("performance_metrics", {})
        
        if not perf_metrics or "error" in perf_metrics:
            return "<p>Performance metrics not available.</p>"
        
        content = []
        
        # Function metrics
        func_metrics = perf_metrics.get("function_metrics", {})
        if func_metrics:
            content.append(f"""
                <div>
                    <h3>Function Analysis</h3>
                    <ul>
                        <li>Total Functions: {func_metrics.get('total_functions', 0)}</li>
                        <li>Average Complexity: {func_metrics.get('average_complexity', 0):.2f}</li>
                        <li>Maximum Complexity: {func_metrics.get('max_complexity', 0):.2f}</li>
                        <li>High Complexity Functions: {func_metrics.get('high_complexity_count', 0)}</li>
                    </ul>
                </div>
            """)
        
        # Performance warnings
        warnings = perf_metrics.get("performance_warnings", [])
        if warnings:
            content.append("<h3>Performance Warnings</h3>")
            content.append("<ul class='error-list'>")
            
            for warning in warnings:
                content.append(f"""
                    <li class="error-item warning">
                        <strong>{warning.get('type', 'unknown').replace('_', ' ').title()}</strong>
                        <div class="error-meta">
                            {warning.get('function', warning.get('file', 'Unknown'))}
                            - {warning.get('recommendation', '')}
                        </div>
                    </li>
                """)
            
            content.append("</ul>")
        
        return "".join(content)
    
    def _generate_security_content(self) -> str:
        """Generate security analysis content."""
        categorized = self.results.get("categorized_errors", {})
        security_issues = categorized.get("security_critical", [])
        
        if not security_issues:
            return "<div class='recommendations'><h3>✅ Security Status</h3><p>No critical security issues detected.</p></div>"
        
        content = [f"<p>Found {len(security_issues)} security issues requiring attention:</p>"]
        content.append("<ul class='error-list'>")
        
        for issue in security_issues:
            severity_class = "error" if issue.severity == DiagnosticSeverity.ERROR else "warning"
            
            content.append(f"""
                <li class="error-item {severity_class}">
                    <strong>🔒 {issue.message}</strong>
                    <div class="error-meta">
                        📁 {os.path.basename(issue.file_path)}
                        📍 Line {issue.line_number or 'N/A'}
                        🔧 {issue.tool_source}
                        {f'🏷️ {issue.error_code}' if issue.error_code else ''}
                        <br>
                        <span class="tag critical">Security Risk</span>
                        {f'<span class="tag">Confidence: {issue.confidence:.1%}</span>' if hasattr(issue, 'confidence') else ''}
                    </div>
                    {f'<div style="margin-top: 10px;"><strong>Fix:</strong> {issue.fix_suggestion}</div>' if issue.fix_suggestion else ''}
                </li>
            """)
        
        content.append("</ul>")
        return "".join(content)
    
    def _generate_recommendations_content(self) -> str:
        """Generate recommendations content."""
        summary = self.results.get("summary", {})
        recommendations = summary.get("recommendations", [])
        action_items = summary.get("action_items", [])
        
        content = []
        
        if recommendations:
            content.append("<div class='recommendations'>")
            content.append("<h3>🎯 Key Recommendations</h3>")
            content.append("<ul>")
            for rec in recommendations:
                content.append(f"<li>{rec}</li>")
            content.append("</ul>")
            content.append("</div>")
        
        if action_items:
            content.append("<h3>📋 Action Items</h3>")
            content.append("<table>")
            content.append("<tr><th>Priority</th><th>Category</th><th>Action</th><th>Effort</th></tr>")
            
            for item in action_items:
                priority_color = {
                    "high": "#dc3545",
                    "medium": "#ffc107", 
                    "low": "#28a745"
                }.get(item.get("priority", "low"), "#6c757d")
                
                content.append(f"""
                    <tr>
                        <td><span class="tag" style="background: {priority_color}">{item.get('priority', 'low').title()}</span></td>
                        <td>{item.get('category', 'unknown').title()}</td>
                        <td>{item.get('action', '')}</td>
                        <td>{item.get('estimated_effort', 'unknown').title()}</td>
                    </tr>
                """)
            
            content.append("</table>")
        
        return "".join(content)


class InteractiveAnalyzer:
    """Interactive analyzer for real-time code analysis and exploration."""
    
    def __init__(self, analyzer: ComprehensiveAnalyzer):
        self.analyzer = analyzer
        self.current_context = None
        self.analysis_history = []
    
    def start_interactive_session(self):
        """Start an interactive analysis session."""
        print("\n" + "="*80)
        print("INTERACTIVE CODE ANALYSIS SESSION")
        print("="*80)
        print("Commands:")
        print("  analyze <file>     - Analyze specific file")
        print("  summary           - Show codebase summary") 
        print("  errors <category> - Show errors by category")
        print("  function <name>   - Analyze specific function")
        print("  class <name>      - Analyze specific class")
        print("  deps              - Show dependency analysis")
        print("  security          - Show security issues")
        print("  performance       - Show performance metrics")
        print("  dead-code         - Show dead code")
        print("  export <format>   - Export report (json/html)")
        print("  help              - Show this help")
        print("  quit              - Exit session")
        print("\n")
        
        while True:
            try:
                command = input("analysis> ").strip().lower()
                
                if command == "quit" or command == "exit":
                    break
                elif command == "help":
                    self._show_help()
                elif command == "summary":
                    self._show_summary()
                elif command.startswith("analyze "):
                    file_path = command[8:].strip()
                    self._analyze_file(file_path)
                elif command.startswith("errors "):
                    category = command[7:].strip()
                    self._show_errors_by_category(category)
                elif command.startswith("function "):
                    func_name = command[9:].strip()
                    self._analyze_function(func_name)
                elif command.startswith("class "):
                    class_name = command[6:].strip()
                    self._analyze_class(class_name)
                elif command == "deps":
                    self._show_dependencies()
                elif command == "security":
                    self._show_security_issues()
                elif command == "performance":
                    self._show_performance_metrics()
                elif command == "dead-code":
                    self._show_dead_code()
                elif command.startswith("export "):
                    format_type = command[7:].strip()
                    self._export_report(format_type)
                else:
                    print(f"Unknown command: {command}. Type 'help' for available commands.")
                    
            except KeyboardInterrupt:
                print("\nSession interrupted. Type 'quit' to exit.")
            except Exception as e:
                print(f"Error: {e}")
    
    def _show_help(self):
        """Show detailed help information."""
        print("""
Available Commands:
        
📊 ANALYSIS COMMANDS:
  summary              - Show comprehensive codebase summary
  analyze <file>       - Deep analysis of specific file
  function <name>      - Detailed function analysis
  class <name>         - Detailed class analysis
        
🚨 ERROR COMMANDS:
  errors <category>    - Show errors by category (syntax, type, security, etc.)
  security            - Show all security-related issues
  performance         - Show performance bottlenecks
        
🔍 EXPLORATION COMMANDS:
  deps                - Show dependency analysis and graphs
  dead-code           - Show unused code detection results
        
📤 EXPORT COMMANDS:
  export json         - Export full report as JSON
  export html         - Export interactive HTML report
        
💡 TIPS:
  - Use tab completion for file names and function names
  - Commands are case-insensitive
  - Use 'quit' or Ctrl+C to exit
        """)
    
    def _show_summary(self):
        """Show interactive summary."""
        if not hasattr(self.analyzer, 'last_results'):
            print("No analysis results available. Run analysis first.")
            return
        
        results = self.analyzer.last_results
        summary = results.get("summary", {})
        overview = summary.get("overview", {})
        
        print("\n📊 CODEBASE SUMMARY")
        print("-" * 50)
        print(f"Total Errors: {overview.get('total_errors', 0)}")
        print(f"Critical Errors: {overview.get('critical_errors', 0)}")
        print(f"Warnings: {overview.get('warnings', 0)}")
        print(f"Files Analyzed: {overview.get('files_analyzed', 0)}")
        print(f"Analysis Duration: {overview.get('analysis_duration', 0):.2f}s")
        
        quality_score = summary.get("quality_score", 0)
        print(f"\nQuality Score: {quality_score:.1f}/100")
        
        # Show top recommendations
        recommendations = summary.get("recommendations", [])
        if recommendations:
            print("\n💡 TOP RECOMMENDATIONS:")
            for i, rec in enumerate(recommendations[:5], 1):
                print(f"  {i}. {rec}")
    
    def _analyze_file(self, file_path: str):
        """Analyze specific file interactively."""
        if not self.analyzer.graph_analysis:
            print("Graph analysis not available.")
            return
        
        file_summary = self.analyzer.graph_analysis.get_file_summary(file_path)
        
        if "error" in file_summary:
            print(f"Error: {file_summary['error']}")
            return
        
        print(f"\n📄 FILE ANALYSIS: {os.path.basename(file_path)}")
        print("-" * 50)
        print(f"Path: {file_path}")
        print(f"Lines of Code: {file_summary.get('lines_of_code', 0)}")
        print(f"Functions: {file_summary.get('functions', 0)}")
        print(f"Classes: {file_summary.get('classes', 0)}")
        print(f"Imports: {file_summary.get('imports', 0)}")
        print(f"Complexity: {file_summary.get('complexity', 0):.2f}")
        
        # Show file-specific errors
        if hasattr(self.analyzer, 'last_results'):
            categorized = self.analyzer.last_results.get("categorized_errors", {})
            file_errors = categorized.get("by_file", {}).get(file_path, [])
            
            if file_errors:
                print(f"\n🚨 ERRORS IN THIS FILE: {len(file_errors)}")
                for error in file_errors[:10]:
                    severity_icon = {
                        DiagnosticSeverity.ERROR: "⚠️",
                        DiagnosticSeverity.WARNING: "👉",
                        DiagnosticSeverity.INFORMATION: "🔍"
                    }.get(error.severity, "•")
                    
                    print(f"  {severity_icon} Line {error.line_number or 'N/A'}: {error.message} [{error.tool_source}]")
            else:
                print("\n✅ No errors found in this file!")
    
    def _show_errors_by_category(self, category: str):
        """Show errors filtered by category."""
        if not hasattr(self.analyzer, 'last_results'):
            print("No analysis results available.")
            return
        
        categorized = self.analyzer.last_results.get("categorized_errors", {})
        by_category = categorized.get("by_category", {})
        
        if category not in by_category:
            available = ", ".join(by_category.keys())
            print(f"Category '{category}' not found. Available: {available}")
            return
        
        errors = by_category[category]
        print(f"\n🚨 {category.upper()} ERRORS: {len(errors)}")
        print("-" * 50)
        
        # Group by file
        by_file = defaultdict(list)
        for error in errors:
            by_file[error.file_path].append(error)
        
        for file_path, file_errors in list(by_file.items())[:10]:
            print(f"\n📁 {os.path.basename(file_path)} ({len(file_errors)} issues):")
            
            for error in file_errors[:5]:
                severity_icon = {
                    DiagnosticSeverity.ERROR: "⚠️",
                    DiagnosticSeverity.WARNING: "👉",
                    DiagnosticSeverity.INFORMATION: "🔍"
                }.get(error.severity, "•")
                
                print(f"  {severity_icon} Line {error.line_number or 'N/A'}: {error.message}")
                if error.fix_suggestion:
                    print(f"      💡 Fix: {error.fix_suggestion}")
    
    def _analyze_function(self, function_name: str):
        """Analyze specific function."""
        if not self.analyzer.graph_analysis:
            print("Graph analysis not available.")
            return
        
        func_analysis = self.analyzer.graph_analysis.get_function_analysis(function_name)
        
        if "error" in func_analysis:
            print(f"Error: {func_analysis['error']}")
            return
        
        print(f"\n🔧 FUNCTION ANALYSIS: {function_name}")
        print("-" * 50)
        print(f"File: {os.path.basename(func_analysis.get('file_path', ''))}")
        print(f"Line: {func_analysis.get('line_number', 'N/A')}")
        print(f"Parameters: {', '.join(func_analysis.get('parameters', []))}")
        print(f"Async: {'Yes' if func_analysis.get('is_async', False) else 'No'}")
        print(f"Decorators: {', '.join(func_analysis.get('decorators', [])) or 'None'}")
        print(f"Complexity: {func_analysis.get('complexity', 0):.2f}")
        print(f"Usage Count: {func_analysis.get('usages', 0)}")
        
        # Show function-specific errors
        if hasattr(self.analyzer, 'last_results'):
            all_errors = self.analyzer.last_results.get("errors", [])
            func_errors = [e for e in all_errors if function_name in e.message or e.line_number == func_analysis.get('line_number')]
            
            if func_errors:
                print(f"\n🚨 ISSUES IN THIS FUNCTION: {len(func_errors)}")
                for error in func_errors:
                    print(f"  • {error.message} [{error.tool_source}]")
    
    def _export_report(self, format_type: str):
        """Export analysis report."""
        if not hasattr(self.analyzer, 'last_results'):
            print("No analysis results to export.")
            return
        
        generator = ReportGenerator(self.analyzer.last_results)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        if format_type == "json":
            filename = f"analysis_report_{timestamp}.json"
            content = generator.generate_json_report()
        elif format_type == "html":
            filename = f"analysis_report_{timestamp}.html"
            content = generator.generate_html_report()
        else:
            print(f"Unsupported format: {format_type}. Use 'json' or 'html'.")
            return
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Report exported to: {filename}")
        except Exception as e:
            print(f"Failed to export report: {e}")


def main():
    """Main entry point with comprehensive argument parsing."""
    parser = argparse.ArgumentParser(
        description="Comprehensive Python Code Analysis with Graph-Sitter Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python analysis.py --target /path/to/project --comprehensive
  python analysis.py --target file.py --interactive --verbose
  python analysis.py --target /path/to/project --graph-sitter --format html
  python analysis.py --target /path/to/project --security-focus --export-db
        """
    )
    
    # Core arguments
    parser.add_argument(
        "--target", required=True,
        help="Path to file or directory to analyze"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--config", 
        help="Path to configuration file (JSON/YAML)"
    )
    
    # Analysis modes
    parser.add_argument(
        "--comprehensive", action="store_true",
        help="Run comprehensive analysis with all tools"
    )
    parser.add_argument(
        "--graph-sitter", action="store_true",
        help="Enable graph-sitter analysis"
    )
    parser.add_argument(
        "--interactive", action="store_true",
        help="Start interactive analysis session"
    )
    parser.add_argument(
        "--lsp", action="store_true",
        help="Enable LSP diagnostics"
    )
    
    # Tool selection
    parser.add_argument(
        "--tools", nargs="+",
        choices=list(ComprehensiveAnalyzer.COMPREHENSIVE_TOOLS.keys()),
        help="Specific tools to run"
    )
    parser.add_argument(
        "--exclude", nargs="+", 
        choices=list(ComprehensiveAnalyzer.COMPREHENSIVE_TOOLS.keys()),
        help="Tools to exclude"
    )
    parser.add_argument(
        "--categories", nargs="+",
        choices=[cat.value for cat in ErrorCategory],
        help="Specific error categories to focus on"
    )
    
    # Focus modes
    parser.add_argument(
        "--security-focus", action="store_true",
        help="Focus on security analysis"
    )
    parser.add_argument(
        "--performance-focus", action="store_true",
        help="Focus on performance analysis"
    )
    parser.add_argument(
        "--type-focus", action="store_true",
        help="Focus on type checking"
    )
    
    # Output options
    parser.add_argument(
        "--format", choices=["text", "json", "html"],
        default="html",
        help="Output format"
    )
    parser.add_argument(
        "--output",
        help="Output file path"
    )
    parser.add_argument(
        "--export-db", action="store_true",
        help="Export results to SQLite database"
    )
    
    # Performance options
    parser.add_argument(
        "--timeout", type=int, default=300,
        help="Default timeout for tools"
    )
    parser.add_argument(
        "--parallel", type=int, default=3,
        help="Number of parallel tool executions"
    )
    parser.add_argument(
        "--cache", action="store_true",
        help="Enable analysis caching"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Load configuration
    config = {}
    if args.config and os.path.exists(args.config):
        try:
            with open(args.config, 'r') as f:
                if args.config.endswith('.json'):
                    config = json.load(f)
                elif args.config.endswith(('.yaml', '.yml')):
                    config = yaml.safe_load(f)
        except Exception as e:
            print(f"Warning: Failed to load config file: {e}")
    
    # Apply focus modes
    if args.security_focus:
        config["focus"] = "security"
        args.tools = ["ruff", "bandit", "safety", "semgrep", "dlint"]
    elif args.performance_focus:
        config["focus"] = "performance"
        args.tools = ["radon", "xenon", "vulture", "py-spy"]
    elif args.type_focus:
        config["focus"] = "type"
        args.tools = ["mypy", "pyright", "ruff"]
    
    # Apply tool filters
    if args.tools or args.exclude:
        tool_config = {}
        for tool_name in ComprehensiveAnalyzer.COMPREHENSIVE_TOOLS:
            enabled = True
            if args.tools:
                enabled = tool_name in args.tools
            if args.exclude:
                enabled = enabled and tool_name not in args.exclude
            tool_config[tool_name] = {"enabled": enabled}
        config["tools"] = tool_config
    
    # Initialize analyzer
    print("Initializing comprehensive analyzer...")
    analyzer = ComprehensiveAnalyzer(args.target, config, args.verbose)
    
    if args.interactive:
        # Run initial analysis then start interactive session
        print("Running initial analysis...")
        results = analyzer.run_comprehensive_analysis()
        analyzer.last_results = results
        
        # Start interactive session
        interactive = InteractiveAnalyzer(analyzer)
        interactive.start_interactive_session()
        
    else:
        # Run analysis
        print("Running comprehensive analysis...")
        results = analyzer.run_comprehensive_analysis()
        
        # Store in database if requested
        if args.export_db:
            db_path = f"analysis_{int(time.time())}.db"
            db = ErrorDatabase(db_path)
            session_id = db.create_session(
                args.target,
                results.get("metadata", {}).get("tools_used", []),
                config
            )
            db.store_errors(results.get("errors", []), session_id)
            db.update_session(session_id, len(results.get("errors", [])))
            print(f"Results stored in database: {db_path}")
        
        # Generate report
        generator = ReportGenerator(results)
        
        if args.format == "json":
            output = generator.generate_json_report()
        elif args.format == "html":
            output = generator.generate_html_report()
        else:
            output = generator.generate_terminal_report()
        
        # Determine output path
        if args.output:
            output_path = args.output
        else:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            target_name = os.path.basename(args.target)
            output_path = f"analysis_{target_name}_{timestamp}.{args.format}"
        
        # Write output
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"\nAnalysis complete! Report saved to: {output_path}")
            
            # Show summary in terminal
            if args.format != "text":
                print(generator.generate_terminal_report())
            
            # Open HTML report in browser
            if args.format == "html":
                try:
                    import webbrowser
                    webbrowser.open(f"file://{os.path.abspath(output_path)}")
                except Exception:
                    pass
                    
        except Exception as e:
            print(f"Error writing output: {e}")
            # Fallback to terminal output
            print(generator.generate_terminal_report())


if __name__ == "__main__":
    main()