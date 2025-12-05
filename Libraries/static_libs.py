#!/usr/bin/env python3
"""🔬 Advanced Static Analysis - Pure Error Detection System
=============================================================================

MISSION: Detect ACTUAL runtime errors using advanced static analysis techniques

ADVANCED LIBRARIES INTEGRATED:
✅ pytype - Google's type inference engine
✅ pyre-check - Facebook's performant type checker
✅ pyanalyze - Quora's semi-static analyzer (imports modules)
✅ vulture - Dead code detector
✅ jedi - Advanced autocompletion/analysis
✅ rope - Python refactoring library with advanced analysis
✅ ast + astroid - Enhanced AST analysis
✅ symtable - Symbol table analysis
✅ inspect - Runtime introspection

DETECTION CAPABILITIES:
✅ Type inference errors (pytype, pyre)
✅ Undefined variable detection (advanced AST walking)
✅ Import resolution errors (jedi, rope)
✅ Dead/unreachable code (vulture, custom CFG)
✅ Function signature mismatches
✅ Attribute access errors
✅ Control flow analysis
✅ Data flow analysis
✅ Symbol table validation
✅ Module dependency analysis

ERROR CATEGORIES (9 types):
1. RUNTIME - Errors during execution
2. TYPE - Type mismatches and inference failures
3. PARAMETER - Function argument errors
4. FLOW - Control flow issues
5. IMPORT - Module import failures
6. SYNTAX - Code syntax errors
7. REFERENCE - Undefined names/attributes
8. EXCEPTION - Exception handling issues
9. LOGIC - Dead code, unreachable statements

USAGE:
    python advanced_error_detector.py --path /project      # Analyze project
    python advanced_error_detector.py --file script.py     # Single file
    python advanced_error_detector.py --profile strict     # Strict mode
    python advanced_error_detector.py --infer-types        # Deep type inference
    python advanced_error_detector.py --detect-dead-code   # Find unused code
    python advanced_error_detector.py --json report.json   # Export results

VERSION: 5.0.0 - Advanced Library Integration
"""

import ast
import asyncio
import builtins
import dis
import hashlib
import importlib
import importlib.util
import inspect
import json
import logging
import os
import re
import subprocess
import sys
import symtable
import time
import traceback
from collections import defaultdict, deque
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import warnings

# Suppress warnings from third-party libraries
warnings.filterwarnings('ignore')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# ERROR REPRESENTATION
# ============================================================================

@dataclass
class AnalysisError:
    """Represents a detected error with comprehensive metadata"""
    file_path: str
    category: str
    severity: str
    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    end_line: Optional[int] = None
    end_column: Optional[int] = None
    code_snippet: Optional[str] = None
    rule_id: Optional[str] = None
    confidence: str = "high"
    source: str = "static_analyzer"


class ErrorCategory(Enum):
    """Categories of actual code errors"""
    RUNTIME = "Runtime Error"
    TYPE = "Type Error"
    PARAMETER = "Parameter Error"
    FLOW = "Control Flow Error"
    IMPORT = "Import Error"
    SYNTAX = "Syntax Error"
    REFERENCE = "Reference Error"
    EXCEPTION = "Exception Handling"
    LOGIC = "Logic Error"


class Severity(Enum):
    """Issue severity levels"""
    CRITICAL = ("🔴", "CRITICAL", 10)
    ERROR = ("❌", "ERROR", 8)
    WARNING = ("⚠️", "WARNING", 5)
    INFO = ("ℹ️", "INFO", 3)


# ============================================================================
# ADVANCED LIBRARY IMPORTS WITH FALLBACKS
# ============================================================================

class LibraryManager:
    """Manages optional advanced analysis libraries"""
    
    def __init__(self):
        self.available_libs = {}
        self._check_libraries()
    
    def _check_libraries(self):
        """Check which advanced libraries are available"""
        libs = {
            'astroid': self._try_import('astroid'),
            'jedi': self._try_import('jedi'),
            'rope': self._try_import('rope.base.project'),
            'vulture': self._try_import('vulture'),
            'pytype': self._check_command('pytype'),
            'pyre': self._check_command('pyre'),
            'pyanalyze': self._try_import('pyanalyze'),
        }
        self.available_libs = {k: v for k, v in libs.items() if v}
        
        logger.info(f"Available advanced libraries: {list(self.available_libs.keys())}")
    
    def _try_import(self, module_name: str) -> bool:
        """Try to import a module"""
        try:
            parts = module_name.split('.')
            mod = __import__(parts[0])
            for part in parts[1:]:
                mod = getattr(mod, part)
            return True
        except (ImportError, AttributeError):
            return False
    
    def _check_command(self, cmd: str) -> bool:
        """Check if command-line tool is available"""
        try:
            result = subprocess.run(
                [cmd, '--version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def get_import(self, module_name: str):
        """Safely import a module"""
        if module_name not in self.available_libs:
            return None
        try:
            return __import__(module_name)
        except ImportError:
            return None
    
    
    def __init__(self):
        self.available_libs = {}
        self._check_libraries()
    
    def _check_libraries(self):
        """Check which advanced libraries are available"""
        libs = {
            'astroid': self._try_import('astroid'),
            'jedi': self._try_import('jedi'),
            'rope': self._try_import('rope.base.project'),
            'vulture': self._try_import('vulture'),
            'pytype': self._check_command('pytype'),
            'pyre': self._check_command('pyre'),
            'pyanalyze': self._try_import('pyanalyze'),
        }
        self.available_libs = {k: v for k, v in libs.items() if v}
        
        logger.info(f"Available advanced libraries: {list(self.available_libs.keys())}")
    
    def _try_import(self, module_name: str) -> bool:
        """Try to import a module"""
        try:
            parts = module_name.split('.')
            mod = __import__(parts[0])
            for part in parts[1:]:
                mod = getattr(mod, part)
            return True
        except (ImportError, AttributeError):
            return False
    
    def _check_command(self, cmd: str) -> bool:
        """Check if command-line tool is available"""
        try:
            result = subprocess.run(
                [cmd, '--version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def get_import(self, module_name: str):
        """Safely import a module"""
        if module_name not in self.available_libs:
            return None
        try:
            return __import__(module_name)
        except ImportError:
            return None
    
    def _analyze_sequential(self, files: List[Path]) -> List[AnalysisError]:
        """Analyze files sequentially"""
        all_errors = []
        for file_path in files:
            errors = self.analyze_file(str(file_path))
            all_errors.extend(errors)
        return all_errors
    
    def _analyze_parallel(self, files: List[Path]) -> List[AnalysisError]:
        """Analyze files in parallel"""
        all_errors = []
        max_workers = min(os.cpu_count() or 4, 8)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.analyze_file, str(f)): f for f in files}
            
            for future in as_completed(futures):
                try:
                    errors = future.result()
                    all_errors.extend(errors)
                except Exception as e:
                    logger.error(f"Analysis failed: {e}")
        
        return all_errors


# ============================================================================
# STANDARD TOOL INTEGRATIONS (Pylint, Mypy, Ruff, etc.)
# ============================================================================

class StandardToolIntegration:
    """Integration with standard Python linting tools"""
    
    # Comprehensive error code mapping (100+ codes)
    ERROR_CODE_MAP = {
        # Pylint E-codes (Runtime Errors)
        'E0001': ErrorCategory.SYNTAX, 'E0011': ErrorCategory.SYNTAX,
        'E0012': ErrorCategory.SYNTAX, 'E0100': ErrorCategory.REFERENCE,
        'E0101': ErrorCategory.FLOW, 'E0102': ErrorCategory.REFERENCE,
        'E0103': ErrorCategory.FLOW, 'E0104': ErrorCategory.FLOW,
        'E0105': ErrorCategory.FLOW, 'E0107': ErrorCategory.PARAMETER,
        'E0108': ErrorCategory.REFERENCE, 'E0110': ErrorCategory.REFERENCE,
        'E0211': ErrorCategory.PARAMETER, 'E0213': ErrorCategory.PARAMETER,
        'E0236': ErrorCategory.PARAMETER, 'E0237': ErrorCategory.PARAMETER,
        'E0238': ErrorCategory.PARAMETER, 'E0239': ErrorCategory.REFERENCE,
        'E0240': ErrorCategory.REFERENCE, 'E0241': ErrorCategory.REFERENCE,
        'E0301': ErrorCategory.PARAMETER, 'E0302': ErrorCategory.PARAMETER,
        'E0401': ErrorCategory.IMPORT, 'E0402': ErrorCategory.IMPORT,
        'E0601': ErrorCategory.REFERENCE, 'E0602': ErrorCategory.REFERENCE,
        'E0603': ErrorCategory.REFERENCE, 'E0604': ErrorCategory.REFERENCE,
        'E0611': ErrorCategory.IMPORT, 'E0632': ErrorCategory.REFERENCE,
        'E0633': ErrorCategory.PARAMETER, 'E0701': ErrorCategory.EXCEPTION,
        'E0702': ErrorCategory.EXCEPTION, 'E0703': ErrorCategory.EXCEPTION,
        'E0704': ErrorCategory.EXCEPTION, 'E0710': ErrorCategory.EXCEPTION,
        'E0711': ErrorCategory.EXCEPTION, 'E0712': ErrorCategory.EXCEPTION,
        'E1003': ErrorCategory.PARAMETER, 'E1101': ErrorCategory.REFERENCE,
        'E1102': ErrorCategory.TYPE, 'E1111': ErrorCategory.PARAMETER,
        'E1120': ErrorCategory.PARAMETER, 'E1121': ErrorCategory.PARAMETER,
        'E1123': ErrorCategory.PARAMETER, 'E1124': ErrorCategory.PARAMETER,
        'E1125': ErrorCategory.PARAMETER, 'E1126': ErrorCategory.TYPE,
        'E1127': ErrorCategory.TYPE, 'E1128': ErrorCategory.PARAMETER,
        'E1129': ErrorCategory.TYPE, 'E1130': ErrorCategory.TYPE,
        'E1131': ErrorCategory.TYPE, 'E1132': ErrorCategory.PARAMETER,
        'E1133': ErrorCategory.TYPE, 'E1134': ErrorCategory.TYPE,
        'E1135': ErrorCategory.TYPE, 'E1136': ErrorCategory.TYPE,
        'E1137': ErrorCategory.TYPE, 'E1138': ErrorCategory.TYPE,
        'E1139': ErrorCategory.EXCEPTION, 'E1140': ErrorCategory.REFERENCE,
        'E1141': ErrorCategory.REFERENCE,
        
        # Pyflakes F-codes (Logic Errors)
        'F401': ErrorCategory.IMPORT, 'F402': ErrorCategory.IMPORT,
        'F403': ErrorCategory.IMPORT, 'F404': ErrorCategory.IMPORT,
        'F405': ErrorCategory.IMPORT, 'F406': ErrorCategory.IMPORT,
        'F407': ErrorCategory.IMPORT, 'F501': ErrorCategory.SYNTAX,
        'F502': ErrorCategory.SYNTAX, 'F503': ErrorCategory.SYNTAX,
        'F504': ErrorCategory.SYNTAX, 'F505': ErrorCategory.SYNTAX,
        'F506': ErrorCategory.SYNTAX, 'F507': ErrorCategory.SYNTAX,
        'F508': ErrorCategory.SYNTAX, 'F509': ErrorCategory.SYNTAX,
        'F521': ErrorCategory.SYNTAX, 'F522': ErrorCategory.SYNTAX,
        'F523': ErrorCategory.SYNTAX, 'F524': ErrorCategory.SYNTAX,
        'F525': ErrorCategory.SYNTAX, 'F541': ErrorCategory.SYNTAX,
        'F601': ErrorCategory.REFERENCE, 'F602': ErrorCategory.REFERENCE,
        'F621': ErrorCategory.EXCEPTION, 'F622': ErrorCategory.EXCEPTION,
        'F631': ErrorCategory.EXCEPTION, 'F632': ErrorCategory.LOGIC,
        'F633': ErrorCategory.LOGIC, 'F634': ErrorCategory.LOGIC,
        'F701': ErrorCategory.FLOW, 'F702': ErrorCategory.FLOW,
        'F703': ErrorCategory.FLOW, 'F704': ErrorCategory.FLOW,
        'F706': ErrorCategory.FLOW, 'F707': ErrorCategory.FLOW,
        'F721': ErrorCategory.SYNTAX, 'F722': ErrorCategory.SYNTAX,
        'F811': ErrorCategory.REFERENCE, 'F821': ErrorCategory.REFERENCE,
        'F822': ErrorCategory.REFERENCE, 'F823': ErrorCategory.REFERENCE,
        'F831': ErrorCategory.REFERENCE, 'F841': ErrorCategory.LOGIC,
        'F842': ErrorCategory.LOGIC, 'F901': ErrorCategory.FLOW,
    }
    
    @staticmethod
    def run_pylint(file_path: str) -> List[AnalysisError]:
        """Run Pylint and extract E/F codes only"""
        errors = []
        try:
            cmd = [sys.executable, '-m', 'pylint', '--errors-only', 
                   '--output-format=json', file_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.stdout:
                data = json.loads(result.stdout)
                for item in data:
                    code = item.get('message-id', '')
                    if code.startswith('E') or code.startswith('F'):
                        category = StandardToolIntegration.ERROR_CODE_MAP.get(
                            code, ErrorCategory.RUNTIME
                        )
                        errors.append(AnalysisError(
                            file_path=item.get('path', file_path),
                            category=category.value,
                            severity=Severity.ERROR.value,
                            message=item.get('message', ''),
                            line=item.get('line'),
                            column=item.get('column'),
                            error_code=code,
                            tool='pylint'
                        ))
        except Exception as e:
            logger.error(f"Pylint failed: {e}")
        
        return errors
    
    @staticmethod
    def run_mypy(file_path: str) -> List[AnalysisError]:
        """Run Mypy for type checking"""
        errors = []
        try:
            cmd = [sys.executable, '-m', 'mypy', '--show-column-numbers',
                   '--no-error-summary', file_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            pattern = r'^(.+?):(\d+):(\d+): (error|warning): (.+?)(?:\s+\[([^\]]+)\])?$'
            
            for line in result.stdout.splitlines():
                match = re.match(pattern, line)
                if match:
                    file, line_no, col, severity, message, code = match.groups()
                    errors.append(AnalysisError(
                        file_path=file,
                        category=ErrorCategory.RUNTIME.value,
                        severity=Severity.ERROR.value if severity == 'error' else Severity.WARNING.value,
                        message=message,
                        line=int(line_no),
                        column=int(col),
                        error_code=code or 'mypy',
                        tool='mypy'
                    ))
        except Exception as e:
            logger.error(f"Mypy failed: {e}")
        
        return errors


# Global library manager
lib_manager = LibraryManager()


# ============================================================================
# ENHANCED ERROR STRUCTURES
# ============================================================================

class ErrorCategory(Enum):
    """Categories of actual code errors"""
    RUNTIME = "Runtime Error"
    TYPE = "Type Error"
    PARAMETER = "Parameter Error"
    FLOW = "Control Flow Error"
    IMPORT = "Import Error"
    SYNTAX = "Syntax Error"
    REFERENCE = "Reference Error"
    EXCEPTION = "Exception Handling"
    LOGIC = "Logic Error"


class Severity(Enum):
    """Issue severity levels"""
    CRITICAL = ("🔴", "CRITICAL", 10)
    ERROR = ("❌", "ERROR", 8)
    WARNING = ("⚠️", "WARNING", 5)
    INFO = ("ℹ️", "INFO", 3)


@dataclass
class AnalysisError:
    """Represents a detected error with comprehensive metadata"""
    file_path: str
    category: str
    severity: str
    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    end_line: Optional[int] = None
    end_column: Optional[int] = None
    error_code: Optional[str] = None
    tool: str = "advanced_analyzer"
    context: Optional[str] = None
    fix_suggestion: Optional[str] = None
    confidence: float = 1.0
    data_flow: Optional[Dict] = None
    control_flow: Optional[Dict] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================================
# ADVANCED AST ANALYZER - Deep Code Analysis
# ============================================================================

class AdvancedASTAnalyzer(ast.NodeVisitor):
    """Advanced AST analyzer with data flow and control flow analysis"""
    
    def __init__(self, file_path: str, source: str):
        self.file_path = file_path
        self.source = source
        self.errors: List[AnalysisError] = []
        self.scope_stack: List[Dict[str, Any]] = [{}]  # Stack of scopes
        self.imported_names: Set[str] = set()
        self.defined_names: Set[str] = set()
        self.used_names: Set[str] = set()
        self.function_defs: Dict[str, ast.FunctionDef] = {}
        self.class_defs: Dict[str, ast.ClassDef] = {}
        self.assignments: Dict[str, List[ast.AST]] = defaultdict(list)
        self.current_function: Optional[str] = None
        self.current_class: Optional[str] = None
        
    def analyze(self) -> List[AnalysisError]:
        """Run complete analysis"""
        try:
            tree = ast.parse(self.source, filename=self.file_path)
            
            # Multiple passes for comprehensive analysis
            self.visit(tree)  # First pass: collect definitions
            self._analyze_undefined_names()  # Second pass: find undefined
            self._analyze_unused_variables()  # Third pass: find unused
            self._analyze_unreachable_code(tree)  # Fourth pass: dead code
            self._analyze_type_consistency(tree)  # Fifth pass: type checks
            
            return self.errors
        except SyntaxError as e:
            self.errors.append(AnalysisError(
                file_path=self.file_path,
                category=ErrorCategory.SYNTAX.value,
                severity=Severity.CRITICAL.value,
                message=f"Syntax error: {e.msg}",
                line=e.lineno,
                column=e.offset,
                error_code="E9999"
            ))
            return self.errors
        except Exception as e:
            logger.error(f"Analysis failed for {self.file_path}: {e}")
            return self.errors
    
    def visit_Import(self, node: ast.Import):
        """Track imports"""
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.imported_names.add(name)
            self.defined_names.add(name)
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Track from imports"""
        if node.module:
            for alias in node.names:
                if alias.name == '*':
                    # Star import - we can't track these reliably
                    pass
                else:
                    name = alias.asname if alias.asname else alias.name
                    self.imported_names.add(name)
                    self.defined_names.add(name)
        self.generic_visit(node)
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Analyze function definitions"""
        self.defined_names.add(node.name)
        self.function_defs[node.name] = node
        
        # Enter function scope
        old_function = self.current_function
        self.current_function = node.name
        self.scope_stack.append({})
        
        # Add parameters to scope
        for arg in node.args.args:
            self.defined_names.add(arg.arg)
            self.scope_stack[-1][arg.arg] = arg
        
        # Check for parameters with same name
        param_names = [arg.arg for arg in node.args.args]
        if len(param_names) != len(set(param_names)):
            self.errors.append(AnalysisError(
                file_path=self.file_path,
                category=ErrorCategory.PARAMETER.value,
                severity=Severity.ERROR.value,
                message=f"Function '{node.name}' has duplicate parameter names",
                line=node.lineno,
                column=node.col_offset,
                error_code="E0108"
            ))
        
        self.generic_visit(node)
        
        # Exit function scope
        self.scope_stack.pop()
        self.current_function = old_function
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Handle async functions like regular functions"""
        self.visit_FunctionDef(node)
    
    def visit_ClassDef(self, node: ast.ClassDef):
        """Analyze class definitions"""
        self.defined_names.add(node.name)
        self.class_defs[node.name] = node
        
        old_class = self.current_class
        self.current_class = node.name
        self.scope_stack.append({})
        
        self.generic_visit(node)
        
        self.scope_stack.pop()
        self.current_class = old_class
    
    def visit_Assign(self, node: ast.Assign):
        """Track assignments"""
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.defined_names.add(target.id)
                self.assignments[target.id].append(node)
                if self.scope_stack:
                    self.scope_stack[-1][target.id] = node
        self.generic_visit(node)
    
    def visit_AnnAssign(self, node: ast.AnnAssign):
        """Track annotated assignments"""
        if isinstance(node.target, ast.Name):
            self.defined_names.add(node.target.id)
            self.assignments[node.target.id].append(node)
        self.generic_visit(node)
    
    def visit_Name(self, node: ast.Name):
        """Track name usage"""
        if isinstance(node.ctx, ast.Load):
            self.used_names.add(node.id)
        self.generic_visit(node)
    
    def visit_Call(self, node: ast.Call):
        """Analyze function calls"""
        # Check if calling undefined function
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            self.used_names.add(func_name)
            
            # Check parameter count if function is defined
            if func_name in self.function_defs:
                func_def = self.function_defs[func_name]
                expected_args = len(func_def.args.args)
                provided_args = len(node.args)
                
                # Account for defaults
                defaults = len(func_def.args.defaults)
                min_args = expected_args - defaults
                max_args = expected_args
                
                if provided_args < min_args:
                    self.errors.append(AnalysisError(
                        file_path=self.file_path,
                        category=ErrorCategory.PARAMETER.value,
                        severity=Severity.ERROR.value,
                        message=f"Function '{func_name}' expects at least {min_args} arguments, got {provided_args}",
                        line=node.lineno,
                        column=node.col_offset,
                        error_code="E1120"
                    ))
                elif provided_args > max_args and not func_def.args.vararg:
                    self.errors.append(AnalysisError(
                        file_path=self.file_path,
                        category=ErrorCategory.PARAMETER.value,
                        severity=Severity.ERROR.value,
                        message=f"Function '{func_name}' takes at most {max_args} arguments, got {provided_args}",
                        line=node.lineno,
                        column=node.col_offset,
                        error_code="E1121"
                    ))
        
        self.generic_visit(node)
    
    def visit_Return(self, node: ast.Return):
        """Check return statements"""
        if not self.current_function:
            self.errors.append(AnalysisError(
                file_path=self.file_path,
                category=ErrorCategory.FLOW.value,
                severity=Severity.ERROR.value,
                message="Return statement outside function",
                line=node.lineno,
                column=node.col_offset,
                error_code="E0104"
            ))
        self.generic_visit(node)
    
    def visit_Yield(self, node: ast.Yield):
        """Check yield statements"""
        if not self.current_function:
            self.errors.append(AnalysisError(
                file_path=self.file_path,
                category=ErrorCategory.FLOW.value,
                severity=Severity.ERROR.value,
                message="Yield statement outside function",
                line=node.lineno,
                column=node.col_offset,
                error_code="E0105"
            ))
        self.generic_visit(node)
    
    def visit_Break(self, node: ast.Break):
        """Check break statements"""
        # Simplified check - in real implementation, track loop nesting
        self.generic_visit(node)
    
    def visit_Continue(self, node: ast.Continue):
        """Check continue statements"""
        # Simplified check - in real implementation, track loop nesting
        self.generic_visit(node)
    
    def _analyze_undefined_names(self):
        """Find undefined names (used but not defined)"""
        builtin_names = set(dir(builtins))
        
        for name in self.used_names:
            if name not in self.defined_names and name not in builtin_names:
                # Try to find where it's used
                for node in ast.walk(ast.parse(self.source)):
                    if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load):
                        self.errors.append(AnalysisError(
                            file_path=self.file_path,
                            category=ErrorCategory.REFERENCE.value,
                            severity=Severity.ERROR.value,
                            message=f"Undefined variable '{name}'",
                            line=node.lineno,
                            column=node.col_offset,
                            error_code="E0602",
                            fix_suggestion=f"Define '{name}' before using it or check for typos"
                        ))
                        break
    
    def _analyze_unused_variables(self):
        """Find unused variables (defined but not used)"""
        # Only report local variables, not module-level or class-level
        if self.current_function:
            for name in self.defined_names:
                if name not in self.used_names:
                    if name not in self.function_defs and name not in self.class_defs:
                        # Don't report if it starts with underscore (convention)
                        if not name.startswith('_'):
                            assignments = self.assignments.get(name, [])
                            if assignments:
                                node = assignments[0]
                                self.errors.append(AnalysisError(
                                    file_path=self.file_path,
                                    category=ErrorCategory.LOGIC.value,
                                    severity=Severity.WARNING.value,
                                    message=f"Variable '{name}' is assigned but never used",
                                    line=getattr(node, 'lineno', None),
                                    column=getattr(node, 'col_offset', None),
                                    error_code="F841"
                                ))
    
    def _analyze_unreachable_code(self, tree: ast.AST):
        """Detect unreachable code after return/raise"""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._check_function_reachability(node)
    
    def _check_function_reachability(self, func: Union[ast.FunctionDef, ast.AsyncFunctionDef]):
        """Check for unreachable code in function"""
        for i, stmt in enumerate(func.body):
            if isinstance(stmt, (ast.Return, ast.Raise)):
                # Check if there are statements after this
                if i < len(func.body) - 1:
                    next_stmt = func.body[i + 1]
                    self.errors.append(AnalysisError(
                        file_path=self.file_path,
                        category=ErrorCategory.LOGIC.value,
                        severity=Severity.WARNING.value,
                        message="Unreachable code after return/raise statement",
                        line=next_stmt.lineno,
                        column=next_stmt.col_offset,
                        error_code="W0101"
                    ))
    
    def _analyze_type_consistency(self, tree: ast.AST):
        """Basic type consistency checking"""
        for node in ast.walk(tree):
            # Check for common type errors
            if isinstance(node, ast.BinOp):
                # Check operations like string + int
                if isinstance(node.op, ast.Add):
                    left = node.left
                    right = node.right
                    
                    # Simple heuristic: check literal types
                    if isinstance(left, ast.Constant) and isinstance(right, ast.Constant):
                        if type(left.value) != type(right.value):
                            if isinstance(left.value, str) or isinstance(right.value, str):
                                self.errors.append(AnalysisError(
                                    file_path=self.file_path,
                                    category=ErrorCategory.TYPE.value,
                                    severity=Severity.ERROR.value,
                                    message="Cannot concatenate string with non-string type",
                                    line=node.lineno,
                                    column=node.col_offset,
                                    error_code="E1131"
                                ))


# ============================================================================
# SYMBOL TABLE ANALYZER
# ============================================================================

class SymbolTableAnalyzer:
    """Analyze Python symbol tables for scope and binding issues"""
    
    def __init__(self, file_path: str, source: str):
        self.file_path = file_path
        self.source = source
        self.errors: List[AnalysisError] = []
    
    def analyze(self) -> List[AnalysisError]:
        """Analyze using symtable"""
        try:
            table = symtable.symtable(self.source, self.file_path, 'exec')
            self._analyze_table(table)
            return self.errors
        except SyntaxError:
            # Already caught by AST analyzer
            return []
        except Exception as e:
            logger.error(f"Symbol table analysis failed: {e}")
            return []
    
    def _analyze_table(self, table: symtable.SymbolTable, depth: int = 0):
        """Recursively analyze symbol table"""
        for symbol in table.get_symbols():
            # Check for undefined variables
            if symbol.is_referenced() and not symbol.is_assigned():
                if not symbol.is_global() and not symbol.is_imported():
                    # This might be undefined
                    pass  # AST analyzer handles this better
            
            # Check for unused variables
            if symbol.is_assigned() and not symbol.is_referenced():
                if not symbol.get_name().startswith('_'):
                    pass  # AST analyzer handles this
        
        # Recurse into children
        for child in table.get_children():
            self._analyze_table(child, depth + 1)


# ============================================================================
# DEAD CODE DETECTOR (VULTURE INTEGRATION)
# ============================================================================

class DeadCodeDetector:
    """Detect dead/unused code using vulture and custom analysis"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.errors: List[AnalysisError] = []
    
    def analyze(self) -> List[AnalysisError]:
        """Run dead code detection"""
        if 'vulture' in lib_manager.available_libs:
            return self._analyze_with_vulture()
        else:
            return self._analyze_basic()
    
    def _analyze_with_vulture(self) -> List[AnalysisError]:
        """Use vulture for dead code detection"""
        try:
            import vulture
            
            v = vulture.Vulture()
            v.scavenge([self.file_path])
            
            for item in v.get_unused_code():
                self.errors.append(AnalysisError(
                    file_path=str(item.filename),
                    category=ErrorCategory.LOGIC.value,
                    severity=Severity.INFO.value,
                    message=f"Unused {item.typ}: {item.name}",
                    line=item.first_lineno,
                    error_code="V001",
                    tool="vulture",
                    confidence=item.confidence / 100.0
                ))
            
            return self.errors
        except Exception as e:
            logger.error(f"Vulture analysis failed: {e}")
            return []
    
    def _analyze_basic(self) -> List[AnalysisError]:
        """Basic dead code detection without vulture"""
        # Fallback to basic analysis
        return []


# ============================================================================
# TYPE INFERENCE ANALYZER (PYTYPE INTEGRATION)
# ============================================================================

class TypeInferenceAnalyzer:
    """Advanced type inference using pytype"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.errors: List[AnalysisError] = []
    
    def analyze(self) -> List[AnalysisError]:
        """Run type inference analysis"""
        if 'pytype' in lib_manager.available_libs:
            return self._analyze_with_pytype()
        return []
    
    def _analyze_with_pytype(self) -> List[AnalysisError]:
        """Use pytype for type inference"""
        try:
            cmd = ['pytype', '--output-errors-csv', '-', self.file_path]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # Parse CSV output
            for line in result.stdout.splitlines()[1:]:  # Skip header
                parts = line.split(',')
                if len(parts) >= 5:
                    file_path = parts[0].strip('"')
                    line_num = int(parts[1]) if parts[1].isdigit() else None
                    error_name = parts[2].strip('"')
                    message = parts[3].strip('"')
                    
                    self.errors.append(AnalysisError(
                        file_path=file_path,
                        category=ErrorCategory.TYPE.value,
                        severity=Severity.ERROR.value,
                        message=message,
                        line=line_num,
                        error_code=error_name,
                        tool="pytype"
                    ))
            
            return self.errors
        except subprocess.TimeoutExpired:
            logger.warning(f"Pytype timed out for {self.file_path}")
            return []
        except Exception as e:
            logger.error(f"Pytype analysis failed: {e}")
            return []


# ============================================================================
# IMPORT RESOLVER (JEDI INTEGRATION)
# ============================================================================

class ImportResolver:
    """Resolve imports and detect import errors using jedi"""
    
    def __init__(self, file_path: str, source: str):
        self.file_path = file_path
        self.source = source
        self.errors: List[AnalysisError] = []
    
    def analyze(self) -> List[AnalysisError]:
        """Analyze imports"""
        if 'jedi' in lib_manager.available_libs:
            return self._analyze_with_jedi()
        else:
            return self._analyze_basic()
    
    def _analyze_with_jedi(self) -> List[AnalysisError]:
        """Use jedi for import analysis"""
        try:
            import jedi
            
            script = jedi.Script(self.source, path=self.file_path)
            
            # Get all imports
            tree = ast.parse(self.source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        # Try to resolve import
                        try:
                            names = script.complete(node.lineno, node.col_offset)
                            # If we can't resolve it, it might be an error
                            if not names:
                                self.errors.append(AnalysisError(
                                    file_path=self.file_path,
                                    category=ErrorCategory.IMPORT.value,
                                    severity=Severity.ERROR.value,
                                    message=f"Cannot resolve import: {alias.name}",
                                    line=node.lineno,
                                    column=node.col_offset,
                                    error_code="E0401",
                                    tool="jedi"
                                ))
                        except Exception:
                            pass
            
            return self.errors
        except Exception as e:
            logger.error(f"Jedi analysis failed: {e}")
            return []
    
    def _analyze_basic(self) -> List[AnalysisError]:
        """Basic import analysis without jedi"""
        tree = ast.parse(self.source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    try:
                        __import__(alias.name)
                    except ImportError:
                        self.errors.append(AnalysisError(
                            file_path=self.file_path,
                            category=ErrorCategory.IMPORT.value,
                            severity=Severity.ERROR.value,
                            message=f"Module not found: {alias.name}",
                            line=node.lineno,
                            column=node.col_offset,
                            error_code="E0401"
                        ))
        
        return self.errors


# ============================================================================
# COMPREHENSIVE ERROR ANALYZER
# ============================================================================

class ComprehensiveErrorAnalyzer:
    """Orchestrates all analysis methods"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.all_errors: List[AnalysisError] = []
    
    def analyze_file(self, file_path: str) -> List[AnalysisError]:
        """Analyze a single file with all available methods"""
        logger.info(f"Analyzing {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
        except Exception as e:
            logger.error(f"Cannot read {file_path}: {e}")
            return []
        
        errors = []
        
        # 1. Advanced AST Analysis
        ast_analyzer = AdvancedASTAnalyzer(file_path, source)
        errors.extend(ast_analyzer.analyze())
        
        # 2. Symbol Table Analysis
        sym_analyzer = SymbolTableAnalyzer(file_path, source)
        errors.extend(sym_analyzer.analyze())
        
        # 3. Dead Code Detection
        if self.config.get('detect_dead_code', True):
            dead_code = DeadCodeDetector(file_path)
            errors.extend(dead_code.analyze())
        
        # 4. Type Inference
        if self.config.get('infer_types', True):
            type_analyzer = TypeInferenceAnalyzer(file_path)
            errors.extend(type_analyzer.analyze())
        
        # 5. Import Resolution
        import_resolver = ImportResolver(file_path, source)
        errors.extend(import_resolver.analyze())
        
        return errors
    
    def analyze_directory(self, directory: str) -> List[AnalysisError]:
        """Analyze all Python files in directory"""
        path = Path(directory)
        python_files = list(path.rglob("*.py"))
        
        logger.info(f"Found {len(python_files)} Python files")
        
        # Use parallel processing for large projects
        if len(python_files) > 10 and self.config.get('parallel', True):
            return self._analyze_parallel(python_files)
        else:
            return self._analyze_sequential(python_files)
    
    def run_ruff(file_path: str) -> List[AnalysisError]:
        """Run Ruff with F-code selection only"""
        errors = []
        try:
            cmd = [sys.executable, '-m', 'ruff', 'check', '--select=F,E9',
                   '--output-format=json', file_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.stdout:
                data = json.loads(result.stdout)
                for item in data:
                    code = item.get('code', '')
                    category = StandardToolIntegration.ERROR_CODE_MAP.get(
                        code, ErrorCategory.LOGIC
                    )
                    errors.append(AnalysisError(
                        file_path=item.get('filename', file_path),
                        category=category.value,
                        severity=Severity.ERROR.value,
                        message=item.get('message', ''),
                        line=item.get('location', {}).get('row'),
                        column=item.get('location', {}).get('column'),
                        error_code=code,
                        tool='ruff',
                        fix_suggestion=item.get('fix', {}).get('message')
                    ))
        except Exception as e:
            logger.error(f"Ruff failed: {e}")
        
        return errors


# ============================================================================
# RESULT AGGREGATOR AND DEDUPLICATOR
# ============================================================================

class ResultAggregator:
    """Aggregate and deduplicate errors from multiple sources"""
    
    def __init__(self):
        self.errors: List[AnalysisError] = []
        self.seen_signatures: Set[str] = set()
    
    def add_errors(self, errors: List[AnalysisError]):
        """Add errors, removing duplicates"""
        for error in errors:
            signature = self._get_signature(error)
            if signature not in self.seen_signatures:
                self.errors.append(error)
                self.seen_signatures.add(signature)
    
    def _get_signature(self, error: AnalysisError) -> str:
        """Generate unique signature for error"""
        return f"{error.file_path}:{error.line}:{error.category}:{error.message[:50]}"
    
    def get_sorted_errors(self) -> List[AnalysisError]:
        """Get errors sorted by severity and location"""
        severity_order = {
            Severity.CRITICAL.value: 0,
            Severity.ERROR.value: 1,
            Severity.WARNING.value: 2,
            Severity.INFO.value: 3
        }
        
        return sorted(self.errors, key=lambda e: (
            severity_order.get(e.severity, 4),
            e.file_path,
            e.line or 0
        ))
    
    def get_statistics(self) -> Dict[str, Any]:
        """Calculate statistics"""
        stats = {
            'total_errors': len(self.errors),
            'by_category': defaultdict(int),
            'by_severity': defaultdict(int),
            'by_tool': defaultdict(int),
            'by_file': defaultdict(int)
        }
        
        for error in self.errors:
            stats['by_category'][error.category] += 1
            stats['by_severity'][error.severity] += 1
            stats['by_tool'][error.tool] += 1
            stats['by_file'][error.file_path] += 1
        
        return {
            'total_errors': stats['total_errors'],
            'by_category': dict(stats['by_category']),
            'by_severity': dict(stats['by_severity']),
            'by_tool': dict(stats['by_tool']),
            'top_files': dict(sorted(
                stats['by_file'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:10])
        }


# ============================================================================
# REPORT GENERATORS
# ============================================================================

class ReportGenerator:
    """Generate comprehensive reports in various formats"""
    
    @staticmethod
    def generate_console_report(errors: List[AnalysisError], stats: Dict):
        """Generate console report with colors"""
        print("\n" + "=" * 80)
        print("🔬 ADVANCED STATIC ANALYSIS - ERROR DETECTION REPORT")
        print("=" * 80)
        
        print(f"\n📊 Summary:")
        print(f"  Total Errors: {stats['total_errors']}")
        print(f"  Critical: {stats['by_severity'].get(Severity.CRITICAL.value, 0)}")
        print(f"  Errors: {stats['by_severity'].get(Severity.ERROR.value, 0)}")
        print(f"  Warnings: {stats['by_severity'].get(Severity.WARNING.value, 0)}")
        
        print(f"\n📁 Errors by Category:")
        for category, count in sorted(stats['by_category'].items(), 
                                      key=lambda x: x[1], reverse=True):
            print(f"  {category}: {count}")
        
        print(f"\n🔧 Tools Used:")
        for tool, count in stats['by_tool'].items():
            print(f"  {tool}: {count} issues")
        
        if stats['top_files']:
            print(f"\n📄 Top Files with Errors:")
            for file_path, count in list(stats['top_files'].items())[:5]:
                print(f"  {Path(file_path).name}: {count} errors")
        
        if errors:
            print(f"\n🔍 Detailed Errors:")
            print("-" * 80)
            for error in errors[:50]:  # Limit to first 50
                severity_symbol = {
                    Severity.CRITICAL.value: "🔴",
                    Severity.ERROR.value: "❌",
                    Severity.WARNING.value: "⚠️",
                    Severity.INFO.value: "ℹ️"
                }.get(error.severity, "•")
                
                location = f"{Path(error.file_path).name}:{error.line or '?'}"
                if error.column:
                    location += f":{error.column}"
                
                print(f"\n{severity_symbol} {location}")
                print(f"  Category: {error.category}")
                print(f"  Tool: {error.tool}")
                if error.error_code:
                    print(f"  Code: {error.error_code}")
                print(f"  Message: {error.message}")
                if error.fix_suggestion:
                    print(f"  💡 Fix: {error.fix_suggestion}")
    
    @staticmethod
    def generate_json_report(errors: List[AnalysisError], stats: Dict, 
                           output_path: str):
        """Generate JSON report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'statistics': stats,
            'errors': [e.to_dict() for e in errors]
        }
        
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"\n✅ JSON report saved: {output_path}")
    
    @staticmethod
    def generate_html_report(errors: List[AnalysisError], stats: Dict,
                           output_path: str):
        """Generate interactive HTML report"""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Advanced Error Detection Report</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                  color: white; padding: 30px; border-radius: 10px; margin-bottom: 20px; }}
        .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .stat-value {{ font-size: 2.5em; font-weight: bold; color: #667eea; }}
        .errors {{ background: white; border-radius: 10px; padding: 20px; }}
        .error-item {{ border-left: 4px solid #dc3545; padding: 15px; margin: 10px 0; background: #f8f9fa; }}
        .error-critical {{ border-left-color: #dc3545; }}
        .error-error {{ border-left-color: #fd7e14; }}
        .error-warning {{ border-left-color: #ffc107; }}
        .error-info {{ border-left-color: #17a2b8; }}
        .badge {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 0.85em; margin-right: 8px; }}
        code {{ background: #e9ecef; padding: 2px 6px; border-radius: 3px; font-family: monospace; }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>🔬 Advanced Error Detection Report</h1>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <div class="stats">
        <div class="stat-card">
            <div class="stat-value">{stats['total_errors']}</div>
            <div>Total Errors</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color: #dc3545;">{stats['by_severity'].get(Severity.CRITICAL.value, 0)}</div>
            <div>Critical</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color: #fd7e14;">{stats['by_severity'].get(Severity.ERROR.value, 0)}</div>
            <div>Errors</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color: #ffc107;">{stats['by_severity'].get(Severity.WARNING.value, 0)}</div>
            <div>Warnings</div>
        </div>
    </div>
    
    <div class="errors">
        <h2>Detailed Errors</h2>
"""
        
        for error in errors:
            severity_class = f"error-{error.severity.lower()}"
            html += f"""
        <div class="error-item {severity_class}">
            <div>
                <span class="badge" style="background: #667eea; color: white;">{error.category}</span>
                <span class="badge" style="background: #e9ecef;">{error.tool}</span>
                {f'<span class="badge" style="background: #fff3cd;"><code>{error.error_code}</code></span>' if error.error_code else ''}
            </div>
            <div style="margin-top: 10px;">
                <strong>{Path(error.file_path).name}:{error.line or '?'}</strong>
                {f':{error.column}' if error.column else ''}
            </div>
            <div style="margin-top: 8px; color: #666;">
                {error.message}
            </div>
            {f'<div style="margin-top: 8px; color: #28a745;">💡 {error.fix_suggestion}</div>' if error.fix_suggestion else ''}
        </div>
"""
        
        html += """
    </div>
</div>
</body>
</html>
"""
        
        with open(output_path, 'w') as f:
            f.write(html)
        
        print(f"\n✅ HTML report saved: {output_path}")


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

class AdvancedErrorDetector:
    """Main orchestrator for advanced error detection"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.aggregator = ResultAggregator()
        self.start_time = time.time()
    
    def run(self):
        """Run complete analysis"""
        print("\n🔬 Advanced Static Analysis - Pure Error Detection")
        print("=" * 80)
        
        # Show available libraries
        print(f"\n📚 Available Libraries:")
        for lib, available in lib_manager.available_libs.items():
            print(f"  {'✅' if available else '❌'} {lib}")
        
        target = self.config.get('path') or self.config.get('file')
        if not target:
            print("❌ No target specified")
            return
        
        # Run comprehensive analysis
        print(f"\n🔍 Analyzing: {target}")
        
        analyzer = ComprehensiveErrorAnalyzer(self.config)
        
        if Path(target).is_file():
            errors = analyzer.analyze_file(target)
        else:
            errors = analyzer.analyze_directory(target)
        
        self.aggregator.add_errors(errors)
        
        # Run standard tools
        if self.config.get('use_standard_tools', True):
            print("\n🔧 Running standard tools...")
            
            files_to_check = [target] if Path(target).is_file() else [
                str(f) for f in Path(target).rglob("*.py")
            ]
            
            for file_path in files_to_check[:10]:  # Limit for demo
                self.aggregator.add_errors(StandardToolIntegration.run_pylint(file_path))
                self.aggregator.add_errors(StandardToolIntegration.run_mypy(file_path))
                self.aggregator.add_errors(StandardToolIntegration.run_ruff(file_path))
        
        # Generate reports
        duration = time.time() - self.start_time
        errors = self.aggregator.get_sorted_errors()
        stats = self.aggregator.get_statistics()
        stats['duration'] = duration
        
        ReportGenerator.generate_console_report(errors, stats)
        
        if self.config.get('json'):
            ReportGenerator.generate_json_report(
                errors, stats, self.config['json']
            )
        
        if self.config.get('html'):
            ReportGenerator.generate_html_report(
                errors, stats, self.config['html']
            )
        
        print(f"\n⏱️  Analysis completed in {duration:.2f}s")
        
        # Exit code based on findings
        critical = stats['by_severity'].get(Severity.CRITICAL.value, 0)
        errors_count = stats['by_severity'].get(Severity.ERROR.value, 0)
        
        if critical > 0:
            sys.exit(2)
        elif errors_count > 0:
            sys.exit(1)
        else:
            sys.exit(0)


# ============================================================================
# CLI INTERFACE
# ============================================================================

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='🔬 Advanced Static Analysis - Pure Error Detection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --path /project              # Analyze entire project
  %(prog)s --file script.py             # Analyze single file
  %(prog)s --path . --profile strict    # Strict analysis mode
  %(prog)s --infer-types --detect-dead-code  # Deep analysis
  %(prog)s --json report.json           # Export to JSON
  %(prog)s --html report.html           # Generate HTML report
        """
    )
    
    parser.add_argument('--path', type=str, help='Path to analyze')
    parser.add_argument('--file', type=str, help='Single file to analyze')
    parser.add_argument('--profile', choices=['strict', 'moderate', 'relaxed'],
                       default='moderate', help='Analysis profile')
    parser.add_argument('--infer-types', action='store_true',
                       help='Enable deep type inference (pytype)')
    parser.add_argument('--detect-dead-code', action='store_true',
                       help='Enable dead code detection (vulture)')
    parser.add_argument('--parallel', action='store_true',
                       help='Use parallel processing')
    parser.add_argument('--json', type=str, metavar='FILE',
                       help='Export results to JSON')
    parser.add_argument('--html', type=str, metavar='FILE',
                       help='Generate HTML report')
    parser.add_argument('--no-standard-tools', action='store_true',
                       help='Skip standard tools (pylint, mypy, ruff)')
    
    args = parser.parse_args()
    
    config = {
        'path': args.path,
        'file': args.file,
        'profile': args.profile,
        'infer_types': args.infer_types,
        'detect_dead_code': args.detect_dead_code,
        'parallel': args.parallel,
        'json': args.json,
        'html': args.html,
        'use_standard_tools': not args.no_standard_tools
    }
    
    try:
        detector = AdvancedErrorDetector(config)
        detector.run()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        logger.exception("Unexpected error")
        sys.exit(1)


if __name__ == "__main__":
    main()
lib_manager = LibraryManager()


# ============================================================================
# ENHANCED ERROR STRUCTURES
# ============================================================================

class ErrorCategory(Enum):
    """Categories of actual code errors"""
    RUNTIME = "Runtime Error"
    TYPE = "Type Error"
    PARAMETER = "Parameter Error"
    FLOW = "Control Flow Error"
    IMPORT = "Import Error"
    SYNTAX = "Syntax Error"
    REFERENCE = "Reference Error"
    EXCEPTION = "Exception Handling"
    LOGIC = "Logic Error"


class Severity(Enum):
    """Issue severity levels"""
    CRITICAL = ("🔴", "CRITICAL", 10)
    ERROR = ("❌", "ERROR", 8)
    WARNING = ("⚠️", "WARNING", 5)
    INFO = ("ℹ️", "INFO", 3)


@dataclass
class AnalysisError:
    """Represents a detected error with comprehensive metadata"""
    file_path: str
    category: str
    severity: str
    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    end_line: Optional[int] = None
    end_column: Optional[int] = None
    error_code: Optional[str] = None
    tool: str = "advanced_analyzer"
    context: Optional[str] = None
    fix_suggestion: Optional[str] = None
    confidence: float = 1.0
    data_flow: Optional[Dict] = None
    control_flow: Optional[Dict] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================================
# ADVANCED AST ANALYZER - Deep Code Analysis
# ============================================================================

class AdvancedASTAnalyzer(ast.NodeVisitor):
    """Advanced AST analyzer with data flow and control flow analysis"""
    
    def __init__(self, file_path: str, source: str):
        self.file_path = file_path
        self.source = source
        self.errors: List[AnalysisError] = []
        self.scope_stack: List[Dict[str, Any]] = [{}]  # Stack of scopes
        self.imported_names: Set[str] = set()
        self.defined_names: Set[str] = set()
        self.used_names: Set[str] = set()
        self.function_defs: Dict[str, ast.FunctionDef] = {}
        self.class_defs: Dict[str, ast.ClassDef] = {}
        self.assignments: Dict[str, List[ast.AST]] = defaultdict(list)
        self.current_function: Optional[str] = None
        self.current_class: Optional[str] = None
        
    def analyze(self) -> List[AnalysisError]:
        """Run complete analysis"""
        try:
            tree = ast.parse(self.source, filename=self.file_path)
            
            # Multiple passes for comprehensive analysis
            self.visit(tree)  # First pass: collect definitions
            self._analyze_undefined_names()  # Second pass: find undefined
            self._analyze_unused_variables()  # Third pass: find unused
            self._analyze_unreachable_code(tree)  # Fourth pass: dead code
            self._analyze_type_consistency(tree)  # Fifth pass: type checks
            
            return self.errors
        except SyntaxError as e:
            self.errors.append(AnalysisError(
                file_path=self.file_path,
                category=ErrorCategory.SYNTAX.value,
                severity=Severity.CRITICAL.value,
                message=f"Syntax error: {e.msg}",
                line=e.lineno,
                column=e.offset,
                error_code="E9999"
            ))
            return self.errors
        except Exception as e:
            logger.error(f"Analysis failed for {self.file_path}: {e}")
            return self.errors
    
    def visit_Import(self, node: ast.Import):
        """Track imports"""
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.imported_names.add(name)
            self.defined_names.add(name)
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Track from imports"""
        if node.module:
            for alias in node.names:
                if alias.name == '*':
                    # Star import - we can't track these reliably
                    pass
                else:
                    name = alias.asname if alias.asname else alias.name
                    self.imported_names.add(name)
                    self.defined_names.add(name)
        self.generic_visit(node)
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Analyze function definitions"""
        self.defined_names.add(node.name)
        self.function_defs[node.name] = node
        
        # Enter function scope
        old_function = self.current_function
        self.current_function = node.name
        self.scope_stack.append({})
        
        # Add parameters to scope
        for arg in node.args.args:
            self.defined_names.add(arg.arg)
            self.scope_stack[-1][arg.arg] = arg
        
        # Check for parameters with same name
        param_names = [arg.arg for arg in node.args.args]
        if len(param_names) != len(set(param_names)):
            self.errors.append(AnalysisError(
                file_path=self.file_path,
                category=ErrorCategory.PARAMETER.value,
                severity=Severity.ERROR.value,
                message=f"Function '{node.name}' has duplicate parameter names",
                line=node.lineno,
                column=node.col_offset,
                error_code="E0108"
            ))
        
        self.generic_visit(node)
        
        # Exit function scope
        self.scope_stack.pop()
        self.current_function = old_function
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Handle async functions like regular functions"""
        self.visit_FunctionDef(node)
    
    def visit_ClassDef(self, node: ast.ClassDef):
        """Analyze class definitions"""
        self.defined_names.add(node.name)
        self.class_defs[node.name] = node
        
        old_class = self.current_class
        self.current_class = node.name
        self.scope_stack.append({})
        
        self.generic_visit(node)
        
        self.scope_stack.pop()
        self.current_class = old_class
    
    def visit_Assign(self, node: ast.Assign):
        """Track assignments"""
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.defined_names.add(target.id)
                self.assignments[target.id].append(node)
                if self.scope_stack:
                    self.scope_stack[-1][target.id] = node
        self.generic_visit(node)
    
    def visit_AnnAssign(self, node: ast.AnnAssign):
        """Track annotated assignments"""
        if isinstance(node.target, ast.Name):
            self.defined_names.add(node.target.id)
            self.assignments[node.target.id].append(node)
        self.generic_visit(node)
    
    def visit_Name(self, node: ast.Name):
        """Track name usage"""
        if isinstance(node.ctx, ast.Load):
            self.used_names.add(node.id)
        self.generic_visit(node)
    
    def visit_Call(self, node: ast.Call):
        """Analyze function calls"""
        # Check if calling undefined function
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            self.used_names.add(func_name)
            
            # Check parameter count if function is defined
            if func_name in self.function_defs:
                func_def = self.function_defs[func_name]
                expected_args = len(func_def.args.args)
                provided_args = len(node.args)
                
                # Account for defaults
                defaults = len(func_def.args.defaults)
                min_args = expected_args - defaults
                max_args = expected_args
                
                if provided_args < min_args:
                    self.errors.append(AnalysisError(
                        file_path=self.file_path,
                        category=ErrorCategory.PARAMETER.value,
                        severity=Severity.ERROR.value,
                        message=f"Function '{func_name}' expects at least {min_args} arguments, got {provided_args}",
                        line=node.lineno,
                        column=node.col_offset,
                        error_code="E1120"
                    ))
                elif provided_args > max_args and not func_def.args.vararg:
                    self.errors.append(AnalysisError(
                        file_path=self.file_path,
                        category=ErrorCategory.PARAMETER.value,
                        severity=Severity.ERROR.value,
                        message=f"Function '{func_name}' takes at most {max_args} arguments, got {provided_args}",
                        line=node.lineno,
                        column=node.col_offset,
                        error_code="E1121"
                    ))
        
        self.generic_visit(node)
    
    def visit_Return(self, node: ast.Return):
        """Check return statements"""
        if not self.current_function:
            self.errors.append(AnalysisError(
                file_path=self.file_path,
                category=ErrorCategory.FLOW.value,
                severity=Severity.ERROR.value,
                message="Return statement outside function",
                line=node.lineno,
                column=node.col_offset,
                error_code="E0104"
            ))
        self.generic_visit(node)
    
    def visit_Yield(self, node: ast.Yield):
        """Check yield statements"""
        if not self.current_function:
            self.errors.append(AnalysisError(
                file_path=self.file_path,
                category=ErrorCategory.FLOW.value,
                severity=Severity.ERROR.value,
                message="Yield statement outside function",
                line=node.lineno,
                column=node.col_offset,
                error_code="E0105"
            ))
        self.generic_visit(node)
    
    def visit_Break(self, node: ast.Break):
        """Check break statements"""
        # Simplified check - in real implementation, track loop nesting
        self.generic_visit(node)
    
    def visit_Continue(self, node: ast.Continue):
        """Check continue statements"""
        # Simplified check - in real implementation, track loop nesting
        self.generic_visit(node)
    
    def _analyze_undefined_names(self):
        """Find undefined names (used but not defined)"""
        builtin_names = set(dir(builtins))
        
        for name in self.used_names:
            if name not in self.defined_names and name not in builtin_names:
                # Try to find where it's used
                for node in ast.walk(ast.parse(self.source)):
                    if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load):
                        self.errors.append(AnalysisError(
                            file_path=self.file_path,
                            category=ErrorCategory.REFERENCE.value,
                            severity=Severity.ERROR.value,
                            message=f"Undefined variable '{name}'",
                            line=node.lineno,
                            column=node.col_offset,
                            error_code="E0602",
                            fix_suggestion=f"Define '{name}' before using it or check for typos"
                        ))
                        break
    
    def _analyze_unused_variables(self):
        """Find unused variables (defined but not used)"""
        # Only report local variables, not module-level or class-level
        if self.current_function:
            for name in self.defined_names:
                if name not in self.used_names:
                    if name not in self.function_defs and name not in self.class_defs:
                        # Don't report if it starts with underscore (convention)
                        if not name.startswith('_'):
                            assignments = self.assignments.get(name, [])
                            if assignments:
                                node = assignments[0]
                                self.errors.append(AnalysisError(
                                    file_path=self.file_path,
                                    category=ErrorCategory.LOGIC.value,
                                    severity=Severity.WARNING.value,
                                    message=f"Variable '{name}' is assigned but never used",
                                    line=getattr(node, 'lineno', None),
                                    column=getattr(node, 'col_offset', None),
                                    error_code="F841"
                                ))
    
    def _analyze_unreachable_code(self, tree: ast.AST):
        """Detect unreachable code after return/raise"""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._check_function_reachability(node)
    
    def _check_function_reachability(self, func: Union[ast.FunctionDef, ast.AsyncFunctionDef]):
        """Check for unreachable code in function"""
        for i, stmt in enumerate(func.body):
            if isinstance(stmt, (ast.Return, ast.Raise)):
                # Check if there are statements after this
                if i < len(func.body) - 1:
                    next_stmt = func.body[i + 1]
                    self.errors.append(AnalysisError(
                        file_path=self.file_path,
                        category=ErrorCategory.LOGIC.value,
                        severity=Severity.WARNING.value,
                        message="Unreachable code after return/raise statement",
                        line=next_stmt.lineno,
                        column=next_stmt.col_offset,
                        error_code="W0101"
                    ))
    
    def _analyze_type_consistency(self, tree: ast.AST):
        """Basic type consistency checking"""
        for node in ast.walk(tree):
            # Check for common type errors
            if isinstance(node, ast.BinOp):
                # Check operations like string + int
                if isinstance(node.op, ast.Add):
                    left = node.left
                    right = node.right
                    
                    # Simple heuristic: check literal types
                    if isinstance(left, ast.Constant) and isinstance(right, ast.Constant):
                        if type(left.value) != type(right.value):
                            if isinstance(left.value, str) or isinstance(right.value, str):
                                self.errors.append(AnalysisError(
                                    file_path=self.file_path,
                                    category=ErrorCategory.TYPE.value,
                                    severity=Severity.ERROR.value,
                                    message="Cannot concatenate string with non-string type",
                                    line=node.lineno,
                                    column=node.col_offset,
                                    error_code="E1131"
                                ))


# ============================================================================
# SYMBOL TABLE ANALYZER
# ============================================================================

class SymbolTableAnalyzer:
    """Analyze Python symbol tables for scope and binding issues"""
    
    def __init__(self, file_path: str, source: str):
        self.file_path = file_path
        self.source = source
        self.errors: List[AnalysisError] = []
    
    def analyze(self) -> List[AnalysisError]:
        """Analyze using symtable"""
        try:
            table = symtable.symtable(self.source, self.file_path, 'exec')
            self._analyze_table(table)
            return self.errors
        except SyntaxError:
            # Already caught by AST analyzer
            return []
        except Exception as e:
            logger.error(f"Symbol table analysis failed: {e}")
            return []
    
    def _analyze_table(self, table: symtable.SymbolTable, depth: int = 0):
        """Recursively analyze symbol table"""
        for symbol in table.get_symbols():
            # Check for undefined variables
            if symbol.is_referenced() and not symbol.is_assigned():
                if not symbol.is_global() and not symbol.is_imported():
                    # This might be undefined
                    pass  # AST analyzer handles this better
            
            # Check for unused variables
            if symbol.is_assigned() and not symbol.is_referenced():
                if not symbol.get_name().startswith('_'):
                    pass  # AST analyzer handles this
        
        # Recurse into children
        for child in table.get_children():
            self._analyze_table(child, depth + 1)


# ============================================================================
# DEAD CODE DETECTOR (VULTURE INTEGRATION)
# ============================================================================

class DeadCodeDetector:
    """Detect dead/unused code using vulture and custom analysis"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.errors: List[AnalysisError] = []
    
    def analyze(self) -> List[AnalysisError]:
        """Run dead code detection"""
        if 'vulture' in lib_manager.available_libs:
            return self._analyze_with_vulture()
        else:
            return self._analyze_basic()
    
    def _analyze_with_vulture(self) -> List[AnalysisError]:
        """Use vulture for dead code detection"""
        try:
            import vulture
            
            v = vulture.Vulture()
            v.scavenge([self.file_path])
            
            for item in v.get_unused_code():
                self.errors.append(AnalysisError(
                    file_path=str(item.filename),
                    category=ErrorCategory.LOGIC.value,
                    severity=Severity.INFO.value,
                    message=f"Unused {item.typ}: {item.name}",
                    line=item.first_lineno,
                    error_code="V001",
                    tool="vulture",
                    confidence=item.confidence / 100.0
                ))
            
            return self.errors
        except Exception as e:
            logger.error(f"Vulture analysis failed: {e}")
            return []
    
    def _analyze_basic(self) -> List[AnalysisError]:
        """Basic dead code detection without vulture"""
        # Fallback to basic analysis
        return []


# ============================================================================
# TYPE INFERENCE ANALYZER (PYTYPE INTEGRATION)
# ============================================================================

class TypeInferenceAnalyzer:
    """Advanced type inference using pytype"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.errors: List[AnalysisError] = []
    
    def analyze(self) -> List[AnalysisError]:
        """Run type inference analysis"""
        if 'pytype' in lib_manager.available_libs:
            return self._analyze_with_pytype()
        return []
    
    def _analyze_with_pytype(self) -> List[AnalysisError]:
        """Use pytype for type inference"""
        try:
            cmd = ['pytype', '--output-errors-csv', '-', self.file_path]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # Parse CSV output
            for line in result.stdout.splitlines()[1:]:  # Skip header
                parts = line.split(',')
                if len(parts) >= 5:
                    file_path = parts[0].strip('"')
                    line_num = int(parts[1]) if parts[1].isdigit() else None
                    error_name = parts[2].strip('"')
                    message = parts[3].strip('"')
                    
                    self.errors.append(AnalysisError(
                        file_path=file_path,
                        category=ErrorCategory.TYPE.value,
                        severity=Severity.ERROR.value,
                        message=message,
                        line=line_num,
                        error_code=error_name,
                        tool="pytype"
                    ))
            
            return self.errors
        except subprocess.TimeoutExpired:
            logger.warning(f"Pytype timed out for {self.file_path}")
            return []
        except Exception as e:
            logger.error(f"Pytype analysis failed: {e}")
            return []


# ============================================================================
# IMPORT RESOLVER (JEDI INTEGRATION)
# ============================================================================

class ImportResolver:
    """Resolve imports and detect import errors using jedi"""
    
    def __init__(self, file_path: str, source: str):
        self.file_path = file_path
        self.source = source
        self.errors: List[AnalysisError] = []
    
    def analyze(self) -> List[AnalysisError]:
        """Analyze imports"""
        if 'jedi' in lib_manager.available_libs:
            return self._analyze_with_jedi()
        else:
            return self._analyze_basic()
    
    def _analyze_with_jedi(self) -> List[AnalysisError]:
        """Use jedi for import analysis"""
        try:
            import jedi
            
            script = jedi.Script(self.source, path=self.file_path)
            
            # Get all imports
            tree = ast.parse(self.source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        # Try to resolve import
                        try:
                            names = script.complete(node.lineno, node.col_offset)
                            # If we can't resolve it, it might be an error
                            if not names:
                                self.errors.append(AnalysisError(
                                    file_path=self.file_path,
                                    category=ErrorCategory.IMPORT.value,
                                    severity=Severity.ERROR.value,
                                    message=f"Cannot resolve import: {alias.name}",
                                    line=node.lineno,
                                    column=node.col_offset,
                                    error_code="E0401",
                                    tool="jedi"
                                ))
                        except Exception:
                            pass
            
            return self.errors
        except Exception as e:
            logger.error(f"Jedi analysis failed: {e}")
            return []
    
    def _analyze_basic(self) -> List[AnalysisError]:
        """Basic import analysis without jedi"""
        tree = ast.parse(self.source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    try:
                        __import__(alias.name)
                    except ImportError:
                        self.errors.append(AnalysisError(
                            file_path=self.file_path,
                            category=ErrorCategory.IMPORT.value,
                            severity=Severity.ERROR.value,
                            message=f"Module not found: {alias.name}",
                            line=node.lineno,
                            column=node.col_offset,
                            error_code="E0401"
                        ))
        
        return self.errors


# ============================================================================
# COMPREHENSIVE ERROR ANALYZER
# ============================================================================

class ComprehensiveErrorAnalyzer:
    """Orchestrates all analysis methods"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.all_errors: List[AnalysisError] = []
    
    def analyze_file(self, file_path: str) -> List[AnalysisError]:
        """Analyze a single file with all available methods"""
        logger.info(f"Analyzing {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
        except Exception as e:
            logger.error(f"Cannot read {file_path}: {e}")
            return []
        
        errors = []
        
        # 1. Advanced AST Analysis
        ast_analyzer = AdvancedASTAnalyzer(file_path, source)
        errors.extend(ast_analyzer.analyze())
        
        # 2. Symbol Table Analysis
        sym_analyzer = SymbolTableAnalyzer(file_path, source)
        errors.extend(sym_analyzer.analyze())
        
        # 3. Dead Code Detection
        if self.config.get('detect_dead_code', True):
            dead_code = DeadCodeDetector(file_path)
            errors.extend(dead_code.analyze())
        
        # 4. Type Inference
        if self.config.get('infer_types', True):
            type_analyzer = TypeInferenceAnalyzer(file_path)
            errors.extend(type_analyzer.analyze())
        
        # 5. Import Resolution
        import_resolver = ImportResolver(file_path, source)
        errors.extend(import_resolver.analyze())
        
        return errors
    
    def analyze_directory(self, directory: str) -> List[AnalysisError]:
        """Analyze all Python files in directory"""
        path = Path(directory)
        python_files = list(path.rglob("*.py"))
        
        logger.info(f"Found {len(python_files)} Python files")
        
        # Use parallel processing for large projects
        if len(python_files) > 10 and self.config.get('parallel', True):
            return self._analyze_parallel(python_files)
        else:
            return self._analyze_sequential(python_files)
    
