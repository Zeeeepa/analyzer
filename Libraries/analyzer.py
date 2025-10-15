#!/usr/bin/env python3
"""Comprehensive Python Code Analysis Backend with Graph-Sitter Integration

This module provides a complete code analysis system that combines:
- Graph-sitter for structural codebase analysis
- SolidLSP for real-time language server diagnostics
- Multiple static analysis tools (ruff, mypy, pylint, etc.)
- AutoGenLib integration for AI-powered error fixing
- Advanced error categorization and reporting

Usage:
    python analysis.py --target /path/to/project --comprehensive
    python analysis.py --target /path/to/file.py --fix-errors
    python analysis.py --target . --interactive
"""

import argparse
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

import yaml

# Third-party imports
try:
    import openai
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.tree import Tree

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Console = None

# Graph-sitter integration
try:
    from graph_sitter import Codebase
    from graph_sitter.codebase.codebase_analysis import (
        get_class_summary,
        get_codebase_summary,
        get_file_summary,
        get_function_summary,
        get_symbol_summary,
    )
    from graph_sitter.configs.models.codebase import CodebaseConfig

    GRAPH_SITTER_AVAILABLE = True
except ImportError:
    GRAPH_SITTER_AVAILABLE = False
    Codebase = None

# SolidLSP integration
try:
    from graph_sitter.extensions.lsp.solidlsp.ls import SolidLanguageServer
    from graph_sitter.extensions.lsp.solidlsp.ls_config import Language, LanguageServerConfig
    from graph_sitter.extensions.lsp.solidlsp.ls_logger import LanguageServerLogger
    from graph_sitter.extensions.lsp.solidlsp.settings import SolidLSPSettings

    SOLIDLSP_AVAILABLE = True
except ImportError as e:
    logging.debug(f"SolidLSP not available: {e}")
    SOLIDLSP_AVAILABLE = False

# AutoGenLib integration
# Enhanced AutoGenLib Fixer - Safe runtime error fixing
try:
    from autogenlib_fixer_enhanced import AutoGenLibFixer
    AUTOGENLIB_FIXER_AVAILABLE = True
except ImportError as e:
    AUTOGENLIB_FIXER_AVAILABLE = False
    logging.debug(f"Enhanced AutoGenLib fixer not available: {e}")

try:
    from graph_sitter.extensions import autogenlib
    from graph_sitter.extensions.autogenlib._cache import cache_module
    from graph_sitter.extensions.autogenlib._exception_handler import generate_fix

    AUTOGENLIB_AVAILABLE = True
except ImportError as e:
    AUTOGENLIB_AVAILABLE = False
    logging.debug(f"AutoGenLib not available: {e}")


@dataclass
class AnalysisError:
    """Structured representation of a code analysis error."""

    file_path: str
    line: int
    column: int
    error_type: str
    severity: str
    message: str
    tool_source: str
    category: str = "general"
    fix_suggestion: str | None = None
    confidence: float = 1.0
    context: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "error_type": self.error_type,
            "severity": self.severity,
            "message": self.message,
            "tool_source": self.tool_source,
            "category": self.category,
            "fix_suggestion": self.fix_suggestion,
            "confidence": self.confidence,
            "context": self.context,
        }


@dataclass
class ToolConfig:
    """Configuration for a code analysis tool."""

    name: str
    command: str
    enabled: bool = True
    args: list[str] = field(default_factory=list)
    config_file: str | None = None
    timeout: int = 300
    priority: int = 2  # 1=critical, 2=important, 3=optional
    requires_network: bool = False


class GraphSitterAnalysis:
    """Graph-sitter based code analysis wrapper."""

    def __init__(self, target_path: str):
        """Initialize graph-sitter analysis."""
        if not GRAPH_SITTER_AVAILABLE:
            msg = "graph-sitter not available. Install with: pip install graph-sitter"
            raise ImportError(msg)

        self.target_path = target_path
        self.codebase = None
        self._initialize_codebase()

    def _initialize_codebase(self):
        """Initialize the graph-sitter codebase."""
        try:
            config = CodebaseConfig(
                method_usages=True,
                generics=True,
                sync_enabled=True,
                full_range_index=True,
                py_resolve_syspath=True,
                exp_lazy_graph=False,
            )
            self.codebase = Codebase(self.target_path, config=config)
        except Exception as e:
            logging.warning(f"Failed to initialize graph-sitter codebase: {e}")
            self.codebase = None

    @property
    def functions(self):
        """All functions in codebase."""
        if not self.codebase:
            return []
        return getattr(self.codebase, "functions", [])

    @property
    def classes(self):
        """All classes in codebase."""
        if not self.codebase:
            return []
        return getattr(self.codebase, "classes", [])

    @property
    def imports(self):
        """All imports in codebase."""
        if not self.codebase:
            return []
        return getattr(self.codebase, "imports", [])

    @property
    def files(self):
        """All files in codebase."""
        if not self.codebase:
            return []
        return getattr(self.codebase, "files", [])

    @property
    def symbols(self):
        """All symbols in codebase."""
        if not self.codebase:
            return []
        return getattr(self.codebase, "symbols", [])

    @property
    def external_modules(self):
        """External dependencies."""
        if not self.codebase:
            return []
        return getattr(self.codebase, "external_modules", [])

    def get_codebase_summary(self) -> dict[str, Any]:
        """Get comprehensive codebase summary."""
        if not self.codebase:
            return {}

        try:
            return get_codebase_summary(self.codebase)
        except Exception as e:
            logging.warning(f"Failed to get codebase summary: {e}")
            return {
                "files": len(self.files),
                "functions": len(self.functions),
                "classes": len(self.classes),
                "imports": len(self.imports),
                "external_modules": len(self.external_modules),
            }

    def get_function_analysis(self, function_name: str) -> dict[str, Any]:
        """Get detailed analysis for a specific function."""
        functions_attr = getattr(self.codebase, "functions", [])
        functions = list(functions_attr) if hasattr(functions_attr, "__iter__") else []

        for func in functions:
            if getattr(func, "name", "") == function_name:
                try:
                    return get_function_summary(func)
                except Exception:
                    # Fallback to basic analysis
                    return {
                        "name": func.name,
                        "parameters": [p.name for p in getattr(func, "parameters", [])],
                        "return_type": getattr(func, "return_type", None),
                        "decorators": [d.name for d in getattr(func, "decorators", [])],
                        "is_async": getattr(func, "is_async", False),
                        "complexity": getattr(func, "complexity", 0),
                        "usages": len(getattr(func, "usages", [])),
                    }
        return {}

    def get_class_analysis(self, class_name: str) -> dict[str, Any]:
        """Get detailed analysis for a specific class."""
        classes_attr = getattr(self.codebase, "classes", [])
        classes = list(classes_attr) if hasattr(classes_attr, "__iter__") else []

        for cls in classes:
            if getattr(cls, "name", "") == class_name:
                try:
                    return get_class_summary(cls)
                except Exception:
                    # Fallback to basic analysis
                    return {
                        "name": cls.name,
                        "methods": len(getattr(cls, "methods", [])),
                        "attributes": len(getattr(cls, "attributes", [])),
                        "superclasses": [sc.name for sc in getattr(cls, "superclasses", [])],
                        "subclasses": [sc.name for sc in getattr(cls, "subclasses", [])],
                        "is_abstract": getattr(cls, "is_abstract", False),
                    }
        return {}


class RuffIntegration:
    """Enhanced Ruff integration for comprehensive error detection."""

    def __init__(self, target_path: str):
        self.target_path = target_path

    def run_comprehensive_analysis(self) -> list[AnalysisError]:
        """Run comprehensive Ruff analysis with all rule categories."""
        errors = []

        # Ruff rule categories for comprehensive analysis
        rule_categories = [
            ("E", "pycodestyle errors"),
            ("W", "pycodestyle warnings"),
            ("F", "pyflakes"),
            ("C", "mccabe complexity"),
            ("I", "isort"),
            ("N", "pep8-naming"),
            ("D", "pydocstyle"),
            ("UP", "pyupgrade"),
            ("YTT", "flake8-2020"),
            ("ANN", "flake8-annotations"),
            ("ASYNC", "flake8-async"),
            ("S", "flake8-bandit"),
            ("BLE", "flake8-blind-except"),
            ("FBT", "flake8-boolean-trap"),
            ("B", "flake8-bugbear"),
            ("A", "flake8-builtins"),
            ("COM", "flake8-commas"),
            ("CPY", "flake8-copyright"),
            ("C4", "flake8-comprehensions"),
            ("DTZ", "flake8-datetimez"),
            ("T10", "flake8-debugger"),
            ("DJ", "flake8-django"),
            ("EM", "flake8-errmsg"),
            ("EXE", "flake8-executable"),
            ("FA", "flake8-future-annotations"),
            ("ISC", "flake8-implicit-str-concat"),
            ("ICN", "flake8-import-conventions"),
            ("G", "flake8-logging-format"),
            ("INP", "flake8-no-pep420"),
            ("PIE", "flake8-pie"),
            ("T20", "flake8-print"),
            ("PYI", "flake8-pyi"),
            ("PT", "flake8-pytest-style"),
            ("Q", "flake8-quotes"),
            ("RSE", "flake8-raise"),
            ("RET", "flake8-return"),
            ("SLF", "flake8-self"),
            ("SLOT", "flake8-slots"),
            ("SIM", "flake8-simplify"),
            ("TID", "flake8-tidy-imports"),
            ("TCH", "flake8-type-checking"),
            ("INT", "flake8-gettext"),
            ("ARG", "flake8-unused-arguments"),
            ("PTH", "flake8-use-pathlib"),
            ("TD", "flake8-todos"),
            ("FIX", "flake8-fixme"),
            ("ERA", "eradicate"),
            ("PD", "pandas-vet"),
            ("PGH", "pygrep-hooks"),
            ("PL", "pylint"),
            ("TRY", "tryceratops"),
            ("FLY", "flynt"),
            ("NPY", "numpy"),
            ("AIR", "airflow"),
            ("PERF", "perflint"),
            ("FURB", "refurb"),
            ("LOG", "flake8-logging"),
            ("RUF", "ruff-specific"),
        ]

        for category, description in rule_categories:
            try:
                cmd = [
                    "ruff",
                    "check",
                    "--select",
                    category,
                    "--output-format",
                    "json",
                    "--no-cache",
                    self.target_path,
                ]

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

                if result.stdout:
                    try:
                        ruff_errors = json.loads(result.stdout)
                        for error in ruff_errors:
                            errors.append(
                                AnalysisError(
                                    file_path=error.get("filename", ""),
                                    line=error.get("location", {}).get("row", 0),
                                    column=error.get("location", {}).get("column", 0),
                                    error_type=error.get("code", ""),
                                    severity=self._map_ruff_severity(error.get("code", "")),
                                    message=error.get("message", ""),
                                    tool_source="ruff",
                                    category=self._categorize_ruff_error(error.get("code", "")),
                                    confidence=0.9,
                                )
                            )
                    except json.JSONDecodeError:
                        pass

            except subprocess.TimeoutExpired:
                logging.warning(f"Ruff analysis timed out for category {category}")
            except Exception as e:
                logging.warning(f"Ruff analysis failed for category {category}: {e}")

        return errors

    def _map_ruff_severity(self, code: str) -> str:
        """Map Ruff error codes to severity levels."""
        if code.startswith(("E", "F")):
            return "ERROR"
        elif code.startswith(("W", "C", "N")):
            return "WARNING"
        elif code.startswith(("S", "B")):
            return "SECURITY"
        else:
            return "INFO"

    def _categorize_ruff_error(self, code: str) -> str:
        """Categorize Ruff errors by type."""
        category_map = {
            "E": "syntax_style",
            "W": "style_warning",
            "F": "logic_error",
            "C": "complexity",
            "I": "import_style",
            "N": "naming",
            "D": "documentation",
            "S": "security",
            "B": "bug_risk",
            "A": "builtin_shadow",
            "T": "debug_code",
            "UP": "modernization",
            "ANN": "type_annotation",
            "ASYNC": "async_issues",
            "PL": "pylint_issues",
            "RUF": "ruff_specific",
        }

        prefix = code.split("0")[0] if "0" in code else code[:1]
        return category_map.get(prefix, "general")


class LSPDiagnosticsCollector:
    """Collects diagnostics from Language Server Protocol servers."""

    def __init__(self, target_path: str):
        self.target_path = target_path
        self.diagnostics = []
        self.logger = LanguageServerLogger() if SOLIDLSP_AVAILABLE else None

    def collect_python_diagnostics(self) -> list[AnalysisError]:
        """Collect diagnostics from Python language servers."""
        if not SOLIDLSP_AVAILABLE:
            logging.warning("SolidLSP not available, skipping LSP diagnostics")
            return []

        errors = []

        try:
            # Configure Pyright for comprehensive analysis
            config = LanguageServerConfig(code_language=Language.PYTHON, trace_lsp_communication=False)

            settings = SolidLSPSettings()

            # Initialize Pyright language server
            from graph_sitter.extensions.lsp.solidlsp.language_servers.pyright_server import PyrightServer

            with PyrightServer(config, self.logger, self.target_path, settings) as lsp:
                lsp.start_server()

                # Find Python files to analyze
                python_files = []
                if os.path.isfile(self.target_path) and self.target_path.endswith(".py"):
                    python_files = [self.target_path]
                elif os.path.isdir(self.target_path):
                    for root, dirs, files in os.walk(self.target_path):
                        # Skip common ignore directories
                        dirs[:] = [
                            d
                            for d in dirs
                            if d
                            not in {
                                "__pycache__",
                                ".git",
                                ".venv",
                                "venv",
                                "node_modules",
                            }
                        ]
                        for file in files:
                            if file.endswith(".py"):
                                python_files.append(os.path.join(root, file))

                # Open files and collect diagnostics
                for file_path in python_files[:10]:  # Limit for performance
                    try:
                        with open(file_path, encoding="utf-8") as f:
                            content = f.read()

                        # Open document in LSP
                        lsp.open_document(file_path, content)

                        # Wait for diagnostics
                        time.sleep(0.5)

                        # Retrieve diagnostics
                        diagnostics = lsp.get_diagnostics(file_path)

                        for diag in diagnostics:
                            errors.append(
                                AnalysisError(
                                    file_path=file_path,
                                    line=diag.get("range", {}).get("start", {}).get("line", 0),
                                    column=diag.get("range", {}).get("start", {}).get("character", 0),
                                    error_type=diag.get("code", "LSP_ERROR"),
                                    severity=self._map_lsp_severity(diag.get("severity", 1)),
                                    message=diag.get("message", ""),
                                    tool_source="pyright",
                                    category="type_checking",
                                    confidence=0.95,
                                )
                            )

                        lsp.close_document(file_path)

                    except Exception as e:
                        logging.warning(f"Failed to analyze {file_path} with LSP: {e}")

        except Exception as e:
            logging.exception(f"LSP diagnostics collection failed: {e}")

        return errors

    def _map_lsp_severity(self, severity: int) -> str:
        """Map LSP severity to our severity levels."""
        severity_map = {1: "ERROR", 2: "WARNING", 3: "INFO", 4: "HINT"}
        return severity_map.get(severity, "INFO")


class ErrorDatabase:
    """SQLite database for storing and querying analysis errors."""

    def __init__(self, db_path: str = "analysis_errors.db"):
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """Initialize the SQLite database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analysis_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_path TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    tools_used TEXT NOT NULL,
                    total_errors INTEGER DEFAULT 0,
                    config_hash TEXT,
                    completed BOOLEAN DEFAULT FALSE
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    file_path TEXT NOT NULL,
                    line INTEGER,
                    column INTEGER,
                    error_type TEXT,
                    severity TEXT,
                    message TEXT,
                    tool_source TEXT,
                    category TEXT,
                    fix_suggestion TEXT,
                    confidence REAL,
                    context TEXT,
                    FOREIGN KEY (session_id) REFERENCES analysis_sessions (id)
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_errors_session
                ON errors (session_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_errors_category
                ON errors (category)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_errors_severity
                ON errors (severity)
            """)

    def create_session(self, target_path: str, tools_used: list[str], config: dict[str, Any]) -> int:
        """Create a new analysis session."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO analysis_sessions
                (target_path, timestamp, tools_used, config_hash)
                VALUES (?, ?, ?, ?)
            """,
                (
                    target_path,
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                    json.dumps(tools_used),
                    str(hash(json.dumps(config, sort_keys=True))),
                ),
            )
            return cursor.lastrowid

    def store_errors(self, errors: list[AnalysisError], session_id: int):
        """Store errors in the database."""
        with sqlite3.connect(self.db_path) as conn:
            for error in errors:
                conn.execute(
                    """
                    INSERT INTO errors
                    (session_id, file_path, line, column, error_type, severity,
                     message, tool_source, category, fix_suggestion, confidence, context)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        session_id,
                        error.file_path,
                        error.line,
                        error.column,
                        error.error_type,
                        error.severity,
                        error.message,
                        error.tool_source,
                        error.category,
                        error.fix_suggestion,
                        error.confidence,
                        error.context,
                    ),
                )

    def update_session(self, session_id: int, total_errors: int):
        """Update session with final error count."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE analysis_sessions
                SET total_errors = ?, completed = TRUE
                WHERE id = ?
            """,
                (total_errors, session_id),
            )

    def query_errors(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        """Query errors with filters."""
        query = "SELECT * FROM errors WHERE 1=1"
        params = []

        for key, value in filters.items():
            if key in ["severity", "category", "tool_source", "error_type"]:
                query += f" AND {key} = ?"
                params.append(value)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]


class AutoGenLibFixerLegacy:
    """Legacy wrapper for AutoGenLibFixer - now uses enhanced version.
    
    This class maintains backward compatibility while delegating to the
    new enhanced AutoGenLibFixer for safe runtime error fixing.
    """

    def __init__(self):
        """Initialize using enhanced fixer if available, otherwise raise error."""
        if AUTOGENLIB_FIXER_AVAILABLE:
            # Use enhanced fixer with full safety features
            self._fixer = AutoGenLibFixer(codebase=None)
            logging.info("✅ Using enhanced AutoGenLibFixer")
        elif AUTOGENLIB_AVAILABLE:
            # Fallback to basic autogenlib
            logging.warning("⚠️  Using basic AutoGenLib (enhanced fixer not available)")
            autogenlib.init(
                "Advanced Python code analysis and error fixing system",
                enable_exception_handler=True,
                enable_caching=True,
            )
            self._fixer = None
        else:
            msg = "AutoGenLib not available"
            raise ImportError(msg)

    def generate_fix_for_error(self, error: AnalysisError, source_code: str) -> dict[str, Any] | None:
        """Generate a fix using enhanced fixer if available."""
        if self._fixer:
            return self._fixer.generate_fix_for_error(error, source_code)
        
        # Fallback to basic generation (legacy code)
        try:
            mock_exception_type = type(error.error_type, (Exception,), {})
            mock_exception_value = Exception(error.message)
            mock_traceback = f"""
File "{error.file_path}", line {error.line}, in <module>
    {getattr(error, 'context', None) or "# Error context not available"}
{error.error_type}: {error.message}
"""
            fix_info = generate_fix(
                module_name=os.path.basename(error.file_path).replace(".py", ""),
                current_code=source_code,
                exc_type=mock_exception_type,
                exc_value=mock_exception_value,
                traceback_str=mock_traceback,
                is_autogenlib=False,
                source_file=error.file_path,
            )
            return fix_info
        except Exception as e:
            logging.exception(f"Failed to generate fix for error: {e}")
            return None

    def apply_fix_to_file(self, file_path: str, fixed_code: str) -> bool:
        """Apply fix using enhanced fixer if available."""
        if self._fixer:
            return self._fixer.apply_fix_to_file(file_path, fixed_code)
        
        # Fallback to basic application
        try:
            backup_path = f"{file_path}.backup_{int(time.time())}"
            with open(file_path) as original:
                with open(backup_path, "w") as backup:
                    backup.write(original.read())
            with open(file_path, "w") as f:
                f.write(fixed_code)
            return True
        except Exception as e:
            logging.exception(f"Failed to apply fix: {e}")
            return False


class ComprehensiveAnalyzer:
    """Main analyzer that orchestrates all analysis tools."""

    # Enhanced tool configuration with comprehensive coverage
    DEFAULT_TOOLS = {
        "ruff": ToolConfig(
            "ruff",
            "ruff",
            args=[
                "check",
                "--output-format=json",
                "--select=ALL",
                "--ignore=COM812,ISC001",
            ],
            timeout=180,
            priority=1,
        ),
        "mypy": ToolConfig(
            "mypy",
            "mypy",
            args=[
                "--strict",
                "--show-error-codes",
                "--show-column-numbers",
                "--json-report=/tmp/mypy.json",
            ],
            timeout=300,
            priority=1,
        ),
        "pyright": ToolConfig("pyright", "pyright", args=["--outputjson"], timeout=600, priority=1),
        "pylint": ToolConfig(
            "pylint",
            "pylint",
            args=["--output-format=json", "--reports=y", "--score=y"],
            timeout=300,
            priority=2,
        ),
        "bandit": ToolConfig(
            "bandit",
            "bandit",
            args=["-r", "-f", "json", "--severity-level=low", "--confidence-level=low"],
            timeout=180,
            priority=1,
        ),
        "safety": ToolConfig(
            "safety",
            "safety",
            args=["check", "--json", "--full-report"],
            timeout=120,
            priority=1,
            requires_network=True,
        ),
        "semgrep": ToolConfig(
            "semgrep",
            "semgrep",
            args=["--config=p/python", "--json", "--severity=WARNING"],
            timeout=300,
            priority=2,
            requires_network=True,
        ),
        "vulture": ToolConfig(
            "vulture",
            "vulture",
            args=["--min-confidence=60", "--sort-by-size"],
            timeout=120,
            priority=2,
        ),
        "radon": ToolConfig(
            "radon",
            "radon",
            args=["cc", "-j", "--total-average", "--show-complexity"],
            timeout=120,
            priority=2,
        ),
        "xenon": ToolConfig(
            "xenon",
            "xenon",
            args=["--max-absolute=B", "--max-modules=B", "--max-average=C"],
            timeout=120,
            priority=2,
        ),
        "black": ToolConfig("black", "black", args=["--check", "--diff"], timeout=60, priority=2),
        "isort": ToolConfig(
            "isort",
            "isort",
            args=["--check-only", "--diff", "--profile=black"],
            timeout=60,
            priority=2,
        ),
        "pydocstyle": ToolConfig(
            "pydocstyle",
            "pydocstyle",
            args=["--convention=google"],
            timeout=120,
            priority=2,
        ),
        "pyflakes": ToolConfig("pyflakes", "pyflakes", timeout=60, priority=2),
        "pycodestyle": ToolConfig(
            "pycodestyle",
            "pycodestyle",
            args=["--statistics", "--count"],
            timeout=120,
            priority=3,
        ),
        "mccabe": ToolConfig("mccabe", "python -m mccabe", args=["--min", "5"], timeout=60, priority=3),
    }

    def __init__(
        self,
        target_path: str,
        config: dict[str, Any] | None = None,
        verbose: bool = False,
    ):
        self.target_path = target_path
        self.config = config or {}
        self.verbose = verbose
        self.tools_config = self.DEFAULT_TOOLS.copy()
        self.console = Console() if RICH_AVAILABLE else None

        # Initialize components
        self.graph_sitter = None
        self.lsp_collector = None
        self.ruff_integration = None
        self.autogenlib_fixer = None
        self.error_db = ErrorDatabase()

        # Results storage
        self.last_results = None

        self._initialize_components()
        self._load_config()

    def _initialize_components(self):
        """Initialize analysis components."""
        try:
            if GRAPH_SITTER_AVAILABLE:
                self.graph_sitter = GraphSitterAnalysis(self.target_path)
                if self.verbose:
                    print("✓ Graph-sitter initialized")
        except Exception as e:
            logging.warning(f"Graph-sitter initialization failed: {e}")

        try:
            if SOLIDLSP_AVAILABLE:
                self.lsp_collector = LSPDiagnosticsCollector(self.target_path)
                if self.verbose:
                    print("✓ LSP diagnostics collector initialized")
        except Exception as e:
            logging.warning(f"LSP collector initialization failed: {e}")

        try:
            self.ruff_integration = RuffIntegration(self.target_path)
            if self.verbose:
                print("✓ Ruff integration initialized")
        except Exception as e:
            logging.warning(f"Ruff integration failed: {e}")

        try:
            if AUTOGENLIB_AVAILABLE:
                self.autogenlib_fixer = AutoGenLibFixer()
                if self.verbose:
                    print("✓ AutoGenLib fixer initialized")
        except Exception as e:
            logging.warning(f"AutoGenLib fixer initialization failed: {e}")

    def _load_config(self):
        """Load configuration from file or use defaults."""
        config_file = self.config.get("config_file")
        if config_file and os.path.exists(config_file):
            try:
                with open(config_file) as f:
                    if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                        file_config = yaml.safe_load(f)
                    else:
                        file_config = json.load(f)

                # Update tool configurations
                tools_config = file_config.get("analysis", {}).get("tools", {})
                for tool_name, tool_config in tools_config.items():
                    if tool_name in self.tools_config:
                        if "enabled" in tool_config:
                            self.tools_config[tool_name].enabled = tool_config["enabled"]
                        if "args" in tool_config:
                            self.tools_config[tool_name].args = tool_config["args"]
                        if "timeout" in tool_config:
                            self.tools_config[tool_name].timeout = tool_config["timeout"]
                        if "priority" in tool_config:
                            self.tools_config[tool_name].priority = tool_config["priority"]

                if self.verbose:
                    print(f"✓ Configuration loaded from {config_file}")

            except Exception as e:
                logging.warning(f"Failed to load config from {config_file}: {e}")

    def run_comprehensive_analysis(self) -> dict[str, Any]:
        """Run comprehensive analysis using all available tools and methods."""
        start_time = time.time()
        all_errors = []

        if self.console:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=self.console,
            ) as progress:
                task = progress.add_task("Running comprehensive analysis...", total=None)

                # Graph-sitter analysis
                progress.update(task, description="Analyzing codebase structure...")
                graph_sitter_results = self._run_graph_sitter_analysis()

                # LSP diagnostics
                progress.update(task, description="Collecting LSP diagnostics...")
                lsp_errors = self._collect_lsp_diagnostics()
                all_errors.extend(lsp_errors)

                # Ruff comprehensive analysis
                progress.update(task, description="Running Ruff analysis...")
                ruff_errors = self._run_ruff_analysis()
                all_errors.extend(ruff_errors)

                # Traditional tools
                progress.update(task, description="Running traditional analysis tools...")
                tool_errors = self._run_traditional_tools()
                all_errors.extend(tool_errors)

                progress.update(task, description="Categorizing and processing errors...")
        else:
            print("Running comprehensive analysis...")
            graph_sitter_results = self._run_graph_sitter_analysis()
            lsp_errors = self._collect_lsp_diagnostics()
            all_errors.extend(lsp_errors)
            ruff_errors = self._run_ruff_analysis()
            all_errors.extend(ruff_errors)
            tool_errors = self._run_traditional_tools()
            all_errors.extend(tool_errors)

        # Categorize errors
        categorized_errors = self._categorize_errors(all_errors)

        # Calculate metrics
        metrics = self._calculate_metrics(all_errors, graph_sitter_results)

        # Detect dead code
        dead_code = self._detect_dead_code(graph_sitter_results)

        # Generate summary
        summary = self._generate_summary(all_errors, categorized_errors, metrics)

        end_time = time.time()

        results = {
            "metadata": {
                "target_path": self.target_path,
                "analysis_time": round(end_time - start_time, 2),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "tools_used": [name for name, config in self.tools_config.items() if config.enabled],
                "graph_sitter_available": GRAPH_SITTER_AVAILABLE,
                "lsp_available": SOLIDLSP_AVAILABLE,
                "autogenlib_available": AUTOGENLIB_AVAILABLE,
            },
            "summary": summary,
            "errors": [error.to_dict() for error in all_errors],
            "categorized_errors": categorized_errors,
            "graph_sitter_results": graph_sitter_results,
            "dead_code": dead_code,
            "metrics": metrics,
            "quality_score": self._calculate_quality_score(all_errors, metrics),
        }

        # Store in database
        session_id = self.error_db.create_session(self.target_path, results["metadata"]["tools_used"], self.config)
        self.error_db.store_errors(all_errors, session_id)
        self.error_db.update_session(session_id, len(all_errors))

        self.last_results = results
        return results

    def _run_graph_sitter_analysis(self) -> dict[str, Any]:
        """Run graph-sitter analysis."""
        if not self.graph_sitter:
            return {}

        try:
            summary = self.graph_sitter.get_codebase_summary()

            # Add detailed analysis
            functions_analysis = []
            for func in self.graph_sitter.functions[:20]:  # Limit for performance
                func_name = getattr(func, "name", "") if hasattr(func, "name") else ""
                if func_name:
                    func_analysis = self.graph_sitter.get_function_analysis(func_name)
                    if func_analysis:
                        functions_analysis.append(func_analysis)

            classes_analysis = []
            for cls in self.graph_sitter.classes[:20]:  # Limit for performance
                cls_name = getattr(cls, "name", "") if hasattr(cls, "name") else ""
                if cls_name:
                    cls_analysis = self.graph_sitter.get_class_analysis(cls_name)
                    if cls_analysis:
                        classes_analysis.append(cls_analysis)

            return {
                "summary": summary,
                "functions": functions_analysis,
                "classes": classes_analysis,
                "external_modules": [getattr(mod, "name", "") for mod in self.graph_sitter.external_modules[:50]],
            }

        except Exception as e:
            logging.exception(f"Graph-sitter analysis failed: {e}")
            return {}

    def _collect_lsp_diagnostics(self) -> list[AnalysisError]:
        """Collect diagnostics from LSP servers."""
        if not self.lsp_collector:
            return []

        try:
            return self.lsp_collector.collect_python_diagnostics()
        except Exception as e:
            logging.exception(f"LSP diagnostics collection failed: {e}")
            return []

    def _run_ruff_analysis(self) -> list[AnalysisError]:
        """Run comprehensive Ruff analysis."""
        if not self.ruff_integration:
            return []

        try:
            return self.ruff_integration.run_comprehensive_analysis()
        except Exception as e:
            logging.exception(f"Ruff analysis failed: {e}")
            return []

    def _run_traditional_tools(self) -> list[AnalysisError]:
        """Run traditional analysis tools."""
        errors = []

        # Run tools in parallel by priority
        priority_groups = {}
        for tool_name, tool_config in self.tools_config.items():
            if not tool_config.enabled:
                continue

            priority = tool_config.priority
            if priority not in priority_groups:
                priority_groups[priority] = []
            priority_groups[priority].append((tool_name, tool_config))

        # Execute by priority (1=critical first, then 2, then 3)
        for priority in sorted(priority_groups.keys()):
            tools_group = priority_groups[priority]

            with ThreadPoolExecutor(max_workers=4) as executor:
                future_to_tool = {executor.submit(self._run_single_tool, tool_name, tool_config): tool_name for tool_name, tool_config in tools_group}

                for future in as_completed(future_to_tool):
                    tool_name = future_to_tool[future]
                    try:
                        tool_errors = future.result()
                        errors.extend(tool_errors)
                    except Exception as e:
                        logging.exception(f"Tool {tool_name} failed: {e}")

        return errors

    def _run_single_tool(self, tool_name: str, tool_config: ToolConfig) -> list[AnalysisError]:
        """Run a single analysis tool."""
        errors = []

        try:
            # Build command
            cmd = [tool_config.command, *tool_config.args, self.target_path]

            # Run tool
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=tool_config.timeout,
                cwd=os.path.dirname(self.target_path) or ".",
            )

            # Parse output based on tool
            if tool_name == "mypy" and result.stdout:
                errors.extend(self._parse_mypy_output(result.stdout))
            elif tool_name == "pylint" and result.stdout:
                errors.extend(self._parse_pylint_output(result.stdout))
            elif tool_name == "bandit" and result.stdout:
                errors.extend(self._parse_bandit_output(result.stdout))
            elif tool_name == "safety" and result.stdout:
                errors.extend(self._parse_safety_output(result.stdout))
            elif tool_name == "semgrep" and result.stdout:
                errors.extend(self._parse_semgrep_output(result.stdout))
            elif result.stdout or result.stderr:
                # Generic parsing for other tools
                errors.extend(self._parse_generic_output(tool_name, result))

        except subprocess.TimeoutExpired:
            logging.warning(f"Tool {tool_name} timed out")
        except Exception as e:
            logging.exception(f"Tool {tool_name} failed: {e}")

        return errors

    def _parse_mypy_output(self, output: str) -> list[AnalysisError]:
        """Parse MyPy JSON output."""
        errors = []
        try:
            # Try to parse as JSON first
            if output.strip().startswith("{"):
                data = json.loads(output)
                for error in data.get("errors", []):
                    errors.append(
                        AnalysisError(
                            file_path=error.get("file", ""),
                            line=error.get("line", 0),
                            column=error.get("column", 0),
                            error_type=error.get("code", "mypy-error"),
                            severity="ERROR" if error.get("severity") == "error" else "WARNING",
                            message=error.get("message", ""),
                            tool_source="mypy",
                            category="type_checking",
                            confidence=0.9,
                        )
                    )
            else:
                # Parse text format
                for line in output.split("\n"):
                    if ":" in line and ("error:" in line or "warning:" in line):
                        parts = line.split(":")
                        if len(parts) >= 4:
                            errors.append(
                                AnalysisError(
                                    file_path=parts[0],
                                    line=int(parts[1]) if parts[1].isdigit() else 0,
                                    column=int(parts[2]) if parts[2].isdigit() else 0,
                                    error_type="mypy-error",
                                    severity="ERROR" if "error:" in line else "WARNING",
                                    message=":".join(parts[3:]).strip(),
                                    tool_source="mypy",
                                    category="type_checking",
                                    confidence=0.9,
                                )
                            )
        except Exception as e:
            logging.warning(f"Failed to parse MyPy output: {e}")

        return errors

    def _parse_pylint_output(self, output: str) -> list[AnalysisError]:
        """Parse Pylint JSON output."""
        errors = []
        try:
            data = json.loads(output)
            for error in data:
                errors.append(
                    AnalysisError(
                        file_path=error.get("path", ""),
                        line=error.get("line", 0),
                        column=error.get("column", 0),
                        error_type=error.get("message-id", ""),
                        severity=error.get("type", "INFO").upper(),
                        message=error.get("message", ""),
                        tool_source="pylint",
                        category=self._categorize_pylint_error(error.get("message-id", "")),
                        confidence=0.8,
                    )
                )
        except Exception as e:
            logging.warning(f"Failed to parse Pylint output: {e}")

        return errors

    def _parse_bandit_output(self, output: str) -> list[AnalysisError]:
        """Parse Bandit JSON output."""
        errors = []
        try:
            data = json.loads(output)
            for result in data.get("results", []):
                errors.append(
                    AnalysisError(
                        file_path=result.get("filename", ""),
                        line=result.get("line_number", 0),
                        column=0,
                        error_type=result.get("test_id", ""),
                        severity="SECURITY",
                        message=result.get("issue_text", ""),
                        tool_source="bandit",
                        category="security_critical",
                        confidence=result.get("confidence", 0.5),
                    )
                )
        except Exception as e:
            logging.warning(f"Failed to parse Bandit output: {e}")

        return errors

    def _parse_safety_output(self, output: str) -> list[AnalysisError]:
        """Parse Safety JSON output."""
        errors = []
        try:
            data = json.loads(output)
            for vuln in data.get("vulnerabilities", []):
                errors.append(
                    AnalysisError(
                        file_path=self.target_path,
                        line=0,
                        column=0,
                        error_type=vuln.get("id", ""),
                        severity="SECURITY",
                        message=f"Vulnerable dependency: {vuln.get('package_name', '')} {vuln.get('installed_version', '')}",
                        tool_source="safety",
                        category="dependency_security",
                        confidence=0.95,
                    )
                )
        except Exception as e:
            logging.warning(f"Failed to parse Safety output: {e}")

        return errors

    def _parse_semgrep_output(self, output: str) -> list[AnalysisError]:
        """Parse Semgrep JSON output."""
        errors = []
        try:
            data = json.loads(output)
            for result in data.get("results", []):
                errors.append(
                    AnalysisError(
                        file_path=result.get("path", ""),
                        line=result.get("start", {}).get("line", 0),
                        column=result.get("start", {}).get("col", 0),
                        error_type=result.get("check_id", ""),
                        severity="WARNING",
                        message=result.get("extra", {}).get("message", ""),
                        tool_source="semgrep",
                        category="security_pattern",
                        confidence=0.85,
                    )
                )
        except Exception as e:
            logging.warning(f"Failed to parse Semgrep output: {e}")

        return errors

    def _parse_generic_output(self, tool_name: str, result: subprocess.CompletedProcess) -> list[AnalysisError]:
        """Parse generic tool output."""
        errors = []

        # If tool failed or has output, create a generic error
        if result.returncode != 0 or result.stdout.strip() or result.stderr.strip():
            output = result.stdout or result.stderr

            # Try to extract file:line information
            for line in output.split("\n"):
                if ":" in line and any(keyword in line.lower() for keyword in ["error", "warning", "issue"]):
                    parts = line.split(":")
                    if len(parts) >= 2:
                        errors.append(
                            AnalysisError(
                                file_path=parts[0] if os.path.exists(parts[0]) else self.target_path,
                                line=int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0,
                                column=0,
                                error_type=f"{tool_name}-issue",
                                severity="WARNING",
                                message=line.strip(),
                                tool_source=tool_name,
                                category="general",
                                confidence=0.7,
                            )
                        )

        return errors

    def _categorize_errors(self, errors: list[AnalysisError]) -> dict[str, list[AnalysisError]]:
        """Categorize errors into comprehensive categories."""
        categories = {
            "syntax_critical": [],
            "type_critical": [],
            "security_critical": [],
            "logic_critical": [],
            "import_critical": [],
            "performance_major": [],
            "complexity_major": [],
            "style_major": [],
            "documentation_major": [],
            "naming_major": [],
            "dependency_major": [],
            "async_major": [],
            "testing_minor": [],
            "formatting_minor": [],
            "optimization_minor": [],
            "general": [],
        }

        for error in errors:
            category = error.category

            # Enhanced categorization based on error type and severity
            if error.severity == "ERROR":
                if "syntax" in error.error_type.lower() or "F" in error.error_type:
                    categories["syntax_critical"].append(error)
                elif "type" in error.error_type.lower() or error.tool_source in [
                    "mypy",
                    "pyright",
                ]:
                    categories["type_critical"].append(error)
                elif "import" in error.error_type.lower():
                    categories["import_critical"].append(error)
                else:
                    categories["logic_critical"].append(error)
            elif error.severity == "SECURITY":
                categories["security_critical"].append(error)
            elif "performance" in category or "complexity" in category:
                categories["performance_major"].append(error)
            elif "style" in category or "format" in category:
                categories["style_major"].append(error)
            elif "doc" in category:
                categories["documentation_major"].append(error)
            elif "naming" in category:
                categories["naming_major"].append(error)
            elif "dependency" in category:
                categories["dependency_major"].append(error)
            elif "async" in category:
                categories["async_major"].append(error)
            else:
                categories["general"].append(error)

        return categories

    def _detect_dead_code(self, graph_sitter_results: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect dead code using graph-sitter analysis."""
        dead_code = []

        if not self.graph_sitter:
            return dead_code

        try:
            # Find unused functions
            for func in self.graph_sitter.functions:
                func_name = getattr(func, "name", "")
                usages = getattr(func, "usages", [])
                if func_name and len(usages) == 0:
                    dead_code.append(
                        {
                            "type": "function",
                            "name": func_name,
                            "file_path": getattr(func, "file_path", ""),
                            "line": getattr(func, "line", 0),
                            "reason": "Function is defined but never called",
                        }
                    )

            # Find unused classes
            for cls in self.graph_sitter.classes:
                cls_name = getattr(cls, "name", "")
                usages = getattr(cls, "usages", [])
                if cls_name and len(usages) == 0:
                    dead_code.append(
                        {
                            "type": "class",
                            "name": cls_name,
                            "file_path": getattr(cls, "file_path", ""),
                            "line": getattr(cls, "line", 0),
                            "reason": "Class is defined but never instantiated or referenced",
                        }
                    )

            # Find unused imports
            for imp in self.graph_sitter.imports:
                imp_name = getattr(imp, "name", "")
                usages = getattr(imp, "usages", [])
                if imp_name and len(usages) == 0:
                    dead_code.append(
                        {
                            "type": "import",
                            "name": imp_name,
                            "file_path": getattr(imp, "file_path", ""),
                            "line": getattr(imp, "line", 0),
                            "reason": "Import is unused",
                        }
                    )

        except Exception as e:
            logging.exception(f"Dead code detection failed: {e}")

        return dead_code

    def _calculate_metrics(self, errors: list[AnalysisError], graph_sitter_results: dict[str, Any]) -> dict[str, Any]:
        """Calculate comprehensive code metrics."""
        metrics = {
            "total_errors": len(errors),
            "error_density": 0,
            "complexity_metrics": {},
            "dependency_metrics": {},
            "performance_metrics": {},
        }

        # Error density calculation
        if graph_sitter_results.get("summary", {}).get("files", 0) > 0:
            metrics["error_density"] = len(errors) / graph_sitter_results["summary"]["files"]

        # Complexity metrics
        complexity_errors = [e for e in errors if "complexity" in e.category]
        metrics["complexity_metrics"] = {
            "high_complexity_count": len(complexity_errors),
            "average_complexity": sum(e.confidence for e in complexity_errors) / len(complexity_errors) if complexity_errors else 0,
        }

        # Dependency metrics
        dependency_errors = [e for e in errors if "dependency" in e.category]
        metrics["dependency_metrics"] = {
            "vulnerable_dependencies": len(dependency_errors),
            "external_dependencies": len(graph_sitter_results.get("external_modules", [])),
        }

        # Performance metrics
        performance_errors = [e for e in errors if "performance" in e.category]
        metrics["performance_metrics"] = {
            "performance_issues": len(performance_errors),
            "performance_warnings": [e.message for e in performance_errors[:5]],
        }

        return metrics

    def _generate_summary(
        self,
        errors: list[AnalysisError],
        categorized_errors: dict[str, list[AnalysisError]],
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate comprehensive analysis summary."""
        return {
            "overview": {
                "total_errors": len(errors),
                "critical_errors": len(categorized_errors.get("syntax_critical", [])) + len(categorized_errors.get("type_critical", [])) + len(categorized_errors.get("security_critical", [])),
                "major_issues": sum(len(categorized_errors.get(cat, [])) for cat in categorized_errors if "major" in cat),
                "minor_issues": sum(len(categorized_errors.get(cat, [])) for cat in categorized_errors if "minor" in cat),
            },
            "by_severity": {
                "ERROR": len([e for e in errors if e.severity == "ERROR"]),
                "WARNING": len([e for e in errors if e.severity == "WARNING"]),
                "SECURITY": len([e for e in errors if e.severity == "SECURITY"]),
                "INFO": len([e for e in errors if e.severity == "INFO"]),
            },
            "by_tool": {tool: len([e for e in errors if e.tool_source == tool]) for tool in set(e.tool_source for e in errors)},
            "quality_metrics": metrics,
        }

    def _calculate_quality_score(self, errors: list[AnalysisError], metrics: dict[str, Any]) -> float:
        """Calculate overall code quality score (0-100)."""
        if not errors:
            return 100.0

        # Base score
        score = 100.0

        # Deduct points for errors by severity
        for error in errors:
            if error.severity == "ERROR":
                score -= 5.0
            elif error.severity == "SECURITY":
                score -= 8.0
            elif error.severity == "WARNING":
                score -= 2.0
            else:
                score -= 0.5

        # Deduct for complexity
        complexity_count = metrics.get("complexity_metrics", {}).get("high_complexity_count", 0)
        score -= complexity_count * 3.0

        # Deduct for dependency issues
        vuln_deps = metrics.get("dependency_metrics", {}).get("vulnerable_dependencies", 0)
        score -= vuln_deps * 10.0

        return max(0.0, min(100.0, score))

    def _categorize_pylint_error(self, message_id: str) -> str:
        """Categorize Pylint errors."""
        if message_id.startswith("C"):
            return "style_major"
        elif message_id.startswith("R"):
            return "complexity_major"
        elif message_id.startswith("W"):
            return "warning_major"
        elif message_id.startswith("E"):
            return "logic_critical"
        else:
            return "general"

    def fix_errors_with_autogenlib(self, max_fixes: int = 5) -> dict[str, Any]:
        """Use AutoGenLib to generate fixes for errors."""
        if not self.autogenlib_fixer or not self.last_results:
            return {"error": "AutoGenLib not available or no analysis results"}

        fixes_applied = []
        errors_to_fix = []

        # Select errors to fix (prioritize critical errors)
        categorized = self.last_results.get("categorized_errors", {})

        # Get critical errors first
        for category in ["syntax_critical", "type_critical", "logic_critical"]:
            errors_to_fix.extend(categorized.get(category, [])[:2])  # Max 2 per category

        # Limit total fixes
        errors_to_fix = errors_to_fix[:max_fixes]

        for error_dict in errors_to_fix:
            error = AnalysisError(**error_dict)

            try:
                # Read source file
                with open(error.file_path) as f:
                    source_code = f.read()

                # Generate fix
                fix_info = self.autogenlib_fixer.generate_fix_for_error(error, source_code)

                if fix_info and fix_info.get("fixed_code"):
                    # Apply fix
                    success = self.autogenlib_fixer.apply_fix_to_file(error.file_path, fix_info["fixed_code"])

                    fixes_applied.append(
                        {
                            "error": error.to_dict(),
                            "fix_applied": success,
                            "fix_explanation": fix_info.get("explanation", ""),
                            "backup_created": success,
                        }
                    )

            except Exception as e:
                logging.exception(f"Failed to fix error in {error.file_path}: {e}")
                fixes_applied.append(
                    {
                        "error": error.to_dict(),
                        "fix_applied": False,
                        "error_message": str(e),
                    }
                )

        return {
            "fixes_attempted": len(errors_to_fix),
            "fixes_applied": len([f for f in fixes_applied if f.get("fix_applied")]),
            "fixes_details": fixes_applied,
        }


class InteractiveAnalyzer:
    """Interactive analysis session for code exploration."""

    def __init__(self, analyzer: ComprehensiveAnalyzer):
        self.analyzer = analyzer
        self.console = Console() if RICH_AVAILABLE else None

    def start_interactive_session(self):
        """Start an interactive analysis session."""
        if self.console:
            self.console.print(
                Panel.fit(
                    "🔍 Interactive Code Analysis Session\nCommands: summary, errors [category], function [name], class [name], fix, export [format], quit",
                    title="Analysis Shell",
                )
            )
        else:
            print("=== Interactive Code Analysis Session ===")
            print("Commands: summary, errors [category], function [name], class [name], fix, export [format], quit")

        while True:
            try:
                command = input("\nanalysis> ").strip().lower()

                if command == "quit" or command == "exit":
                    break
                elif command == "summary":
                    self._show_summary()
                elif command.startswith("errors"):
                    category = command.split()[1] if len(command.split()) > 1 else None
                    self._show_errors(category)
                elif command.startswith("function"):
                    func_name = command.split()[1] if len(command.split()) > 1 else None
                    self._show_function_analysis(func_name)
                elif command.startswith("class"):
                    class_name = command.split()[1] if len(command.split()) > 1 else None
                    self._show_class_analysis(class_name)
                elif command == "fix":
                    self._apply_fixes()
                elif command.startswith("export"):
                    format_type = command.split()[1] if len(command.split()) > 1 else "json"
                    self._export_results(format_type)
                else:
                    print("Unknown command. Available: summary, errors, function, class, fix, export, quit")

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")

        print("Interactive session ended.")

    def _show_summary(self):
        """Show analysis summary."""
        if not self.analyzer.last_results:
            print("No analysis results available. Run analysis first.")
            return

        summary = self.analyzer.last_results.get("summary", {})

        if self.console:
            table = Table(title="Analysis Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="magenta")

            overview = summary.get("overview", {})
            for key, value in overview.items():
                table.add_row(key.replace("_", " ").title(), str(value))

            self.console.print(table)
        else:
            print("\n=== Analysis Summary ===")
            overview = summary.get("overview", {})
            for key, value in overview.items():
                print(f"{key.replace('_', ' ').title()}: {value}")

    def _show_errors(self, category: str | None = None):
        """Show errors, optionally filtered by category."""
        if not self.analyzer.last_results:
            print("No analysis results available.")
            return

        categorized = self.analyzer.last_results.get("categorized_errors", {})

        if category:
            errors = categorized.get(category, [])
            print(f"\n=== {category.replace('_', ' ').title()} Errors ===")
        else:
            errors = self.analyzer.last_results.get("errors", [])
            print(f"\n=== All Errors ({len(errors)}) ===")

        for i, error in enumerate(errors[:20]):  # Show first 20
            print(f"{i + 1}. {error['file_path']}:{error['line']} - {error['message']} [{error['tool_source']}]")

    def _show_function_analysis(self, func_name: str | None):
        """Show function analysis."""
        if not func_name:
            print("Please specify a function name: function <name>")
            return

        if not self.analyzer.graph_sitter:
            print("Graph-sitter not available for function analysis.")
            return

        analysis = self.analyzer.graph_sitter.get_function_analysis(func_name)
        if analysis:
            print(f"\n=== Function Analysis: {func_name} ===")
            for key, value in analysis.items():
                print(f"{key}: {value}")
        else:
            print(f"Function '{func_name}' not found.")

    def _show_class_analysis(self, class_name: str | None):
        """Show class analysis."""
        if not class_name:
            print("Please specify a class name: class <name>")
            return

        if not self.analyzer.graph_sitter:
            print("Graph-sitter not available for class analysis.")
            return

        analysis = self.analyzer.graph_sitter.get_class_analysis(class_name)
        if analysis:
            print(f"\n=== Class Analysis: {class_name} ===")
            for key, value in analysis.items():
                print(f"{key}: {value}")
        else:
            print(f"Class '{class_name}' not found.")

    def _apply_fixes(self):
        """Apply AutoGenLib fixes."""
        if not self.analyzer.autogenlib_fixer:
            print("AutoGenLib not available for fixing.")
            return

        print("Applying AI-powered fixes...")
        fix_results = self.analyzer.fix_errors_with_autogenlib()

        print(f"Fixes attempted: {fix_results.get('fixes_attempted', 0)}")
        print(f"Fixes applied: {fix_results.get('fixes_applied', 0)}")

        for fix in fix_results.get("fixes_details", []):
            if fix.get("fix_applied"):
                print(f"✓ Fixed: {fix['error']['message']}")
            else:
                print(f"✗ Failed: {fix['error']['message']}")

    def _export_results(self, format_type: str):
        """Export results in specified format."""
        if not self.analyzer.last_results:
            print("No results to export.")
            return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"analysis_export_{timestamp}.{format_type}"

        try:
            if format_type == "json":
                with open(filename, "w") as f:
                    json.dump(self.analyzer.last_results, f, indent=2)
            elif format_type == "html":
                html_content = ReportGenerator(self.analyzer.last_results).generate_html_report()
                with open(filename, "w") as f:
                    f.write(html_content)
            else:
                print(f"Unsupported format: {format_type}")
                return

            print(f"Results exported to: {filename}")

        except Exception as e:
            print(f"Export failed: {e}")


class ReportGenerator:
    """Generate comprehensive analysis reports."""

    def __init__(self, results: dict[str, Any]):
        self.results = results

    def generate_terminal_report(self) -> str:
        """Generate a comprehensive terminal report."""
        lines = []

        # Header
        lines.append("=" * 100)
        lines.append("COMPREHENSIVE CODE ANALYSIS REPORT")
        lines.append("=" * 100)

        # Metadata
        metadata = self.results.get("metadata", {})
        lines.append(f"Target: {metadata.get('target_path', 'Unknown')}")
        lines.append(f"Analysis Time: {metadata.get('analysis_time', 0)}s")
        lines.append(f"Timestamp: {metadata.get('timestamp', 'Unknown')}")
        lines.append(f"Tools Used: {', '.join(metadata.get('tools_used', []))}")
        lines.append("")

        # Quality Score
        quality_score = self.results.get("quality_score", 0)
        lines.append(f"🎯 QUALITY SCORE: {quality_score:.1f}/100")
        lines.append("")

        # Summary
        summary = self.results.get("summary", {})
        overview = summary.get("overview", {})

        lines.append("📊 SUMMARY")
        lines.append("-" * 50)
        lines.append(f"Total Errors: {overview.get('total_errors', 0)}")
        lines.append(f"Critical Errors: {overview.get('critical_errors', 0)}")
        lines.append(f"Major Issues: {overview.get('major_issues', 0)}")
        lines.append(f"Minor Issues: {overview.get('minor_issues', 0)}")
        lines.append("")

        # Graph-sitter results
        gs_results = self.results.get("graph_sitter_results", {})
        if gs_results:
            lines.append("🏗️ CODEBASE STRUCTURE")
            lines.append("-" * 50)
            gs_summary = gs_results.get("summary", {})
            for key, value in gs_summary.items():
                lines.append(f"{key.replace('_', ' ').title()}: {value}")
            lines.append("")

        # Dead code
        dead_code = self.results.get("dead_code", [])
        if dead_code:
            lines.append(f"💀 DEAD CODE ({len(dead_code)} items)")
            lines.append("-" * 50)
            for item in dead_code[:10]:  # Show first 10
                lines.append(f"{item['type'].title()}: {item['name']} - {item['reason']}")
            if len(dead_code) > 10:
                lines.append(f"... and {len(dead_code) - 10} more items")
            lines.append("")

        # Categorized errors
        categorized = self.results.get("categorized_errors", {})
        lines.append("🔍 ERRORS BY CATEGORY")
        lines.append("-" * 50)

        for category, errors in categorized.items():
            if errors:
                lines.append(f"\n{category.replace('_', ' ').title()} ({len(errors)} errors):")
                for error in errors[:5]:  # Show first 5 per category
                    lines.append(f"  • {error['file_path']}:{error['line']} - {error['message']}")
                if len(errors) > 5:
                    lines.append(f"  ... and {len(errors) - 5} more")

        lines.append("")
        lines.append("=" * 100)

        return "\n".join(lines)

    def generate_html_report(self) -> str:
        """Generate comprehensive HTML report."""
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Comprehensive Code Analysis Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0; padding: 20px; background: #f5f5f5;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        h3 {{ color: #7f8c8d; }}
        .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
        .metric-card {{ background: #ecf0f1; padding: 15px; border-radius: 8px; text-align: center; }}
        .metric-value {{ font-size: 2em; font-weight: bold; color: #2980b9; }}
        .metric-label {{ color: #7f8c8d; margin-top: 5px; }}
        .error-category {{ margin: 15px 0; padding: 15px; border-left: 4px solid #e74c3c; background: #fdf2f2; }}
        .error-item {{ margin: 8px 0; padding: 10px; background: white; border-radius: 5px; border-left: 3px solid #95a5a6; }}
        .severity-ERROR {{ border-left-color: #e74c3c; }}
        .severity-WARNING {{ border-left-color: #f39c12; }}
        .severity-SECURITY {{ border-left-color: #8e44ad; }}
        .severity-INFO {{ border-left-color: #3498db; }}
        .quality-score {{ font-size: 3em; font-weight: bold; text-align: center; margin: 20px 0; }}
        .score-excellent {{ color: #27ae60; }}
        .score-good {{ color: #f39c12; }}
        .score-poor {{ color: #e74c3c; }}
        .dead-code {{ background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 15px 0; }}
        .code-snippet {{ background: #2c3e50; color: #ecf0f1; padding: 15px; border-radius: 5px; overflow-x: auto; }}
        pre {{ margin: 0; }}
        .tool-badge {{ display: inline-block; background: #3498db; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; margin-left: 10px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Comprehensive Code Analysis Report</h1>

        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-value">{self.results.get("quality_score", 0):.1f}</div>
                <div class="metric-label">Quality Score</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{len(self.results.get("errors", []))}</div>
                <div class="metric-label">Total Issues</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{len(self.results.get("dead_code", []))}</div>
                <div class="metric-label">Dead Code Items</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{len(self.results.get("metadata", {}).get("tools_used", []))}</div>
                <div class="metric-label">Tools Used</div>
            </div>
        </div>

        <h2>📈 Error Categories</h2>
        {self._generate_error_categories_html()}

        <h2>💀 Dead Code Analysis</h2>
        {self._generate_dead_code_html()}

        <h2>🏗️ Codebase Structure</h2>
        {self._generate_structure_html()}

        <h2>📊 Detailed Metrics</h2>
        {self._generate_metrics_html()}
    </div>
</body>
</html>
"""
        return html

    def _generate_error_categories_html(self) -> str:
        """Generate HTML for error categories."""
        categorized = self.results.get("categorized_errors", {})
        html_parts = []

        for category, errors in categorized.items():
            if not errors:
                continue

            html_parts.append('<div class="error-category">')
            html_parts.append(f"<h3>{category.replace('_', ' ').title()} ({len(errors)} errors)</h3>")

            for error in errors[:10]:  # Show first 10 per category
                html_parts.append(f"""
                <div class="error-item severity-{error["severity"]}">
                    <strong>{error["file_path"]}:{error["line"]}</strong>
                    <span class="tool-badge">{error["tool_source"]}</span>
                    <br>
                    {error["message"]}
                </div>
                """)

            if len(errors) > 10:
                html_parts.append(f"<p><em>... and {len(errors) - 10} more errors</em></p>")

            html_parts.append("</div>")

        return "".join(html_parts)

    def _generate_dead_code_html(self) -> str:
        """Generate HTML for dead code analysis."""
        dead_code = self.results.get("dead_code", [])

        if not dead_code:
            return "<p>No dead code detected.</p>"

        html_parts = ['<div class="dead-code">']

        for item in dead_code[:20]:  # Show first 20
            html_parts.append(f"""
            <div class="error-item">
                <strong>{item["type"].title()}: {item["name"]}</strong><br>
                <em>{item["file_path"]}:{item["line"]}</em><br>
                {item["reason"]}
            </div>
            """)

        if len(dead_code) > 20:
            html_parts.append(f"<p><em>... and {len(dead_code) - 20} more items</em></p>")

        html_parts.append("</div>")
        return "".join(html_parts)

    def _generate_structure_html(self) -> str:
        """Generate HTML for codebase structure."""
        gs_results = self.results.get("graph_sitter_results", {})

        if not gs_results:
            return "<p>Graph-sitter analysis not available.</p>"

        summary = gs_results.get("summary", {})
        html_parts = ['<div class="metric-grid">']

        for key, value in summary.items():
            html_parts.append(f"""
            <div class="metric-card">
                <div class="metric-value">{value}</div>
                <div class="metric-label">{key.replace("_", " ").title()}</div>
            </div>
            """)

        html_parts.append("</div>")
        return "".join(html_parts)

    def _generate_metrics_html(self) -> str:
        """Generate HTML for detailed metrics."""
        metrics = self.results.get("metrics", {})

        html_parts = []
        for category, data in metrics.items():
            html_parts.append(f"<h3>{category.replace('_', ' ').title()}</h3>")
            html_parts.append("<ul>")

            if isinstance(data, dict):
                for key, value in data.items():
                    html_parts.append(f"<li><strong>{key}:</strong> {value}</li>")
            else:
                html_parts.append(f"<li>{data}</li>")

            html_parts.append("</ul>")

        return "".join(html_parts)


def main():
    """Main entry point for the comprehensive analysis system."""
    parser = argparse.ArgumentParser(description="Comprehensive Python Code Analysis with Graph-Sitter, LSP, and AI-powered fixing")
    parser.add_argument("--target", required=True, help="Target file or directory to analyze")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--comprehensive", action="store_true", help="Run comprehensive analysis")
    parser.add_argument("--fix-errors", action="store_true", help="Apply AI-powered fixes")
    parser.add_argument("--interactive", action="store_true", help="Start interactive session")
    parser.add_argument(
        "--format",
        choices=["terminal", "json", "html"],
        default="terminal",
        help="Output format",
    )
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--max-fixes", type=int, default=5, help="Maximum number of fixes to apply")

    args = parser.parse_args()

    # Initialize analyzer
    config = {"config_file": args.config} if args.config else {}
    analyzer = ComprehensiveAnalyzer(args.target, config, args.verbose)

    try:
        if args.comprehensive or not (args.fix_errors or args.interactive):
            # Run comprehensive analysis
            print("🚀 Starting comprehensive analysis...")
            results = analyzer.run_comprehensive_analysis()

            # Generate report
            generator = ReportGenerator(results)

            if args.format == "terminal":
                report = generator.generate_terminal_report()
                print(report)

                if args.output:
                    with open(args.output, "w") as f:
                        f.write(report)
                    print(f"\nReport saved to: {args.output}")

            elif args.format == "json":
                output_file = args.output or f"analysis_report_{int(time.time())}.json"
                with open(output_file, "w") as f:
                    json.dump(results, f, indent=2)
                print(f"JSON report saved to: {output_file}")

            elif args.format == "html":
                output_file = args.output or f"analysis_report_{int(time.time())}.html"
                html_report = generator.generate_html_report()
                with open(output_file, "w") as f:
                    f.write(html_report)
                print(f"HTML report saved to: {output_file}")

                # Try to open in browser
                try:
                    import webbrowser

                    webbrowser.open(output_file)
                except Exception:
                    pass

        if args.fix_errors:
            # Apply fixes
            if not analyzer.last_results:
                print("Running analysis first...")
                analyzer.run_comprehensive_analysis()

            print("🔧 Applying AI-powered fixes...")
            fix_results = analyzer.fix_errors_with_autogenlib(args.max_fixes)

            print(f"Fixes attempted: {fix_results.get('fixes_attempted', 0)}")
            print(f"Fixes applied: {fix_results.get('fixes_applied', 0)}")

            for fix in fix_results.get("fixes_details", []):
                if fix.get("fix_applied"):
                    print(f"✓ Fixed: {fix['error']['message']}")
                else:
                    print(f"✗ Failed: {fix['error']['message']}")

        if args.interactive:
            # Start interactive session
            if not analyzer.last_results:
                print("Running analysis first...")
                analyzer.run_comprehensive_analysis()

            interactive = InteractiveAnalyzer(analyzer)
            interactive.start_interactive_session()

    except KeyboardInterrupt:
        print("\nAnalysis interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Analysis failed: {e}")
        if args.verbose:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    main()
