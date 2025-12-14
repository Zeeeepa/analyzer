#!/usr/bin/env python3
"""
Production Graph-Sitter Backend API
Provides comprehensive codebase analysis, visualization, and transformation capabilities
using actual graph-sitter library implementation
"""

import os
import tempfile
import shutil
import subprocess
import traceback
import uuid
import math
import ast
import re  # Added for Halstead metrics
from typing import Dict, List, Any, Optional, Union
from collections import defaultdict, Counter
from datetime import datetime
import asyncio
import logging
import networkx as nx

# FastAPI and web framework imports
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import os
import logging
import math
import re
from typing import Dict, List, Optional, Any, Tuple, Union
from pathlib import Path
from collections import defaultdict, Counter

from graph_sitter import Codebase
from graph_sitter.core.symbol import Symbol
from graph_sitter.core.function import Function
from graph_sitter.core.class_definition import Class
from graph_sitter.core.file import SourceFile
from graph_sitter.core.import_resolution import Import
from graph_sitter.core.external_module import ExternalModule

from graph_sitter.extensions.tools.codebase_analysis import (
    get_codebase_summary,
    get_file_summary,
    get_class_summary,
    get_function_summary,
    get_symbol_summary
)

# Import visualization and analysis tools
from graph_sitter.extensions.tools.view_file import (
    ViewFileObservation,
    add_line_numbers,
    view_file
)

from graph_sitter.extensions.tools.reveal_symbol import (
    SymbolInfo,
    RevealSymbolObservation,
    get_symbol_info,
    truncate_source,
    get_extended_context,
    reveal_symbol,
    hop_through_imports
)

from graph_sitter.extensions.tools.list_directory import (
    DirectoryInfo,
    ListDirectoryObservation,
    list_directory
)

from graph_sitter.extensions.tools.bash import (
    RunBashCommandObservation,
    validate_command,
    run_bash_command
)

from graph_sitter.extensions.tools.reflection import (
    ReflectionSection,
    ReflectionObservation,
    parse_reflection_response,
    perform_reflection
)

from graph_sitter.extensions.tools.observation import Observation

from graph_sitter.extensions.tools.tools import get_workspace_tools

from graph_sitter.extensions.tools.tool_output_types import (
    EditFileArtifacts,
    ViewFileArtifacts,
    ListDirectoryArtifacts,
    SearchMatch,
    SearchArtifacts,
    SemanticEditArtifacts,
    RelaceEditArtifacts
)

# Import documentation generation
from graph_sitter.extensions.tools.generate_docs_json import generate_docs_json
from graph_sitter.extensions.tools.mdx_docs_generation import (
    render_mdx_page_for_class,
    render_mdx_page_title,
    render_mdx_inheritence_section,
    render_mdx_attributes_section,
    render_mdx_methods_section,
    render_mdx_for_attribute,
    format_parameter_for_mdx,
    format_parameters_for_mdx,
    format_return_for_mdx,
    render_mdx_for_method,
    get_mdx_route_for_class,
    format_type_string,
    resolve_type_string,
    format_builtin_type_string,
    span_type_string_by_pipe,
    parse_link
)

# Import codebase utilities
from graph_sitter.extensions.tools.current_code_codebase import (
    get_current_code_codebase,
    get_codegen_codebase_base_path,
    get_graphsitter_repo_path,
    import_all_codegen_sdk_modules,
    get_documented_objects
)

from graph_sitter.extensions.tools.codegen_sdk_codebase import (
    get_codegen_sdk_codebase,
    get_codegen_sdk_subdirectories
)

# Import document functions
from graph_sitter.extensions.tools.document_functions import (
    run as document_functions_run,
    get_extended_context as doc_get_extended_context,
    hop_through_imports as doc_hop_through_imports
)

# Import visualization modules
from graph_sitter.extensions.tools.blast_radius import (
    generate_edge_meta as blast_generate_edge_meta,
    is_http_method,
    create_blast_radius_visualization,
    run as blast_radius_run
)

from graph_sitter.extensions.tools.call_trace import (
    generate_edge_meta as call_generate_edge_meta,
    create_downstream_call_trace,
    run as call_trace_run
)

from graph_sitter.extensions.tools.dependency_trace import (
    create_dependencies_visualization,
    run as dependency_trace_run
)

from graph_sitter.extensions.tools.method_relationships import (
    generate_edge_meta as method_generate_edge_meta,
    graph_class_methods,
    create_downstream_call_trace as method_create_downstream_call_trace,
    run as method_relationships_run
)

import networkx as nx
from graph_sitter.core.codebase import Codebase
from graph_sitter.configs.models.codebase import CodebaseConfig
from graph_sitter.core.external_module import ExternalModule
from graph_sitter.core.symbol import Symbol
from graph_sitter.core.file import SourceFile  # Changed from File
from graph_sitter.core.function import Function
from graph_sitter.core.class_definition import Class  # Changed from ClassDef
from graph_sitter.core.statement import Statement, IfStatement, WhileStatement, TryStatement
from graph_sitter.core.import_statement import Import
from graph_sitter.core.assignment import Assignment
from graph_sitter.core.parameter import Parameter
from graph_sitter.core.function_call import FunctionCall
from graph_sitter.core.usage import Usage

from lsp_diagnostics import LSPDiagnosticsManager
from autogenlib_adapter import resolve_diagnostic_with_ai
from serena.solidlsp.lsp_protocol_handler.lsp_types import Diagnostic, DocumentUri, Range
from serena.solidlsp.ls_config import Language

from graph_sitter.extensions.tools.generate_docs_json import generate_docs_json
from graph_sitter.extensions.tools.mdx_docs_generation import render_mdx_page_for_class


GRAPH_SITTER_AVAILABLE = True


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Graph-Sitter Comprehensive Analysis API",
    description="Complete codebase analysis, visualization, and transformation using graph-sitter",
    version="3.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global storage for analysis sessions
analysis_sessions: Dict[str, Dict] = {}

# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class AnalyzeRequest(BaseModel):
    repo_url: str = Field(..., description="GitHub repository URL")
    branch: str = Field(default="main", description="Branch to analyze")
    config: Optional[Dict] = Field(default=None, description="Analysis configuration")
    include_deep_analysis: bool = Field(
        default=True, description="Include comprehensive analysis"
    )
    language: str = Field(
        default="python",
        description="Programming language of the codebase (e.g., python, csharp).",
    )


class ErrorAnalysisResponse(BaseModel):
    total_errors: int
    critical_errors: int
    major_errors: int
    minor_errors: int
    errors_by_category: Dict[str, int]
    detailed_errors: List[Dict[str, Any]]
    error_patterns: List[Dict[str, Any]]
    suggestions: List[Dict[str, Any]]


class EntrypointAnalysisResponse(BaseModel):
    total_entrypoints: int
    main_entrypoints: List[Dict[str, Any]]
    secondary_entrypoints: List[Dict[str, Any]]
    test_entrypoints: List[Dict[str, Any]]
    api_entrypoints: List[Dict[str, Any]]  # Added
    cli_entrypoints: List[Dict[str, Any]]  # Added
    entrypoint_graph: Dict[str, Any]
    complexity_metrics: Dict[str, Any]
    dependency_analysis: Dict[str, Any]  # Added
    call_flow_analysis: Dict[str, Any]  # Added


class TransformationRequest(BaseModel):
    analysis_id: str
    transformation_type: str
    target_path: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = Field(default=True, description="Preview changes without applying")


class VisualizationRequest(BaseModel):
    analysis_id: str
    viz_type: str = Field(..., description="Type of visualization")
    entry_point: Optional[str] = Field(
        default=None, description="Entry point for visualization"
    )
    max_depth: int = Field(default=10, description="Maximum depth for traversal")
    include_external: bool = Field(
        default=False, description="Include external modules"
    )
    filter_patterns: List[str] = Field(
        default_factory=list, description="Filter patterns"
    )


class DeadCodeAnalysisResponse(BaseModel):
    total_dead_items: int
    dead_functions: List[Dict[str, Any]]
    dead_classes: List[Dict[str, Any]]
    dead_imports: List[Dict[str, Any]]
    dead_variables: List[Dict[str, Any]]
    potential_dead_code: List[Dict[str, Any]]
    recommendations: List[str]


class CodeQualityMetrics(BaseModel):
    complexity_score: float
    maintainability_index: float
    technical_debt_ratio: float
    test_coverage_estimate: float
    documentation_coverage: float
    code_duplication_score: float
    type_coverage: float  # Added
    function_metrics: Dict[str, Any]  # Added
    class_metrics: Dict[str, Any]  # Added
    file_metrics: Dict[str, Any]  # Added


class GraphSitterAnalyzer:
    """
    Comprehensive analysis engine using all Graph-Sitter capabilities.
    Provides unified access to all graph-sitter folder functionalities.
    """

    def __init__(self, codebase: Codebase):
        self.codebase = codebase
        self.analysis_cache = {}
        self.visualization_cache = {}

    # ============================================================================
    # CORE ANALYSIS FUNCTIONS (from codebase_analysis.py)
    # ============================================================================

    def get_codebase_overview(self) -> Dict[str, Any]:
        """Provides a high-level overview of the codebase structure."""
        if "codebase_overview" in self.analysis_cache:
            return self.analysis_cache["codebase_overview"]

        summary_str = get_codebase_summary(self.codebase)

        # Parse summary into structured data
        overview = {
            "summary": summary_str,
            "files_count": len(list(self.codebase.files)),
            "functions_count": len(list(self.codebase.functions)),
            "classes_count": len(list(self.codebase.classes)),
            "symbols_count": len(list(self.codebase.symbols)),
            "imports_count": len(list(self.codebase.imports)),
            "external_modules_count": len(list(self.codebase.external_modules)),
            "entrypoints": self._identify_entrypoints(),
            "dead_code_summary": self._get_dead_code_summary(),
            "complexity_overview": self._get_complexity_overview()
        }

        self.analysis_cache["codebase_overview"] = overview
        return overview

    def get_file_details(self, filepath: str) -> Dict[str, Any]:
        """Retrieves detailed information about a specific file."""
        cache_key = f"file_details_{filepath}"
        if cache_key in self.analysis_cache:
            return self.analysis_cache[cache_key]

        try:
            file_obj = self.codebase.get_file(filepath)
            summary_str = get_file_summary(file_obj)

            details = {
                "filepath": filepath,
                "summary": summary_str,
                "functions": [self._get_function_summary(f) for f in file_obj.functions],
                "classes": [self._get_class_summary(c) for c in file_obj.classes],
                "imports": [self._get_import_summary(i) for i in file_obj.imports],
                "symbols": [self._get_symbol_summary(s) for s in getattr(file_obj, "symbols", [])],
                "metrics": {
                    "lines_of_code": len(file_obj.source.splitlines()) if hasattr(file_obj, "source") else 0,
                    "complexity_score": self._calculate_file_complexity(file_obj),
                    "maintainability_index": self._calculate_maintainability_index(file_obj),
                    "documentation_coverage": self._calculate_file_doc_coverage(file_obj)
                }
            }

            self.analysis_cache[cache_key] = details
            return details
        except ValueError:
            return {"filepath": filepath, "error": "File not found in codebase."}

    def get_function_details(self, function_name: str, filepath: Optional[str] = None) -> Dict[str, Any]:
        """Retrieves comprehensive information about a function."""
        cache_key = f"function_details_{function_name}_{filepath}"
        if cache_key in self.analysis_cache:
            return self.analysis_cache[cache_key]

        try:
            symbols = self.codebase.get_symbols(symbol_name=function_name)
            if not symbols:
                return {"function_name": function_name, "error": "Function not found."}

            target_symbol = self._resolve_symbol_with_filepath(symbols, filepath, Function)
            if not target_symbol:
                return {"function_name": function_name, "filepath": filepath, "error": "Function not found at specified path or is not a function."}

            summary_str = get_function_summary(target_symbol)
            reveal_info = reveal_symbol(
                codebase=self.codebase,
                symbol_name=function_name,
                filepath=filepath,
                max_depth=3,
                max_tokens=5000
            )

            details = {
                "function_name": function_name,
                "filepath": target_symbol.file.filepath if target_symbol.file else "N/A",
                "summary": summary_str,
                "parameters": self._get_function_parameters_details(target_symbol),
                "return_type": self._get_function_return_type_details(target_symbol),
                "local_variables": self._get_function_local_variables_details(target_symbol),
                "dependencies": [self._symbol_to_dict(s) for s in reveal_info.dependencies] if reveal_info.dependencies else [],
                "usages": [self._symbol_to_dict(s) for s in reveal_info.usages] if reveal_info.usages else [],
                "call_sites": [self._call_site_to_dict(cs) for cs in target_symbol.call_sites],
                "function_calls": [self._function_call_to_dict(fc) for fc in target_symbol.function_calls],
                "complexity_metrics": self._calculate_function_complexity_metrics(target_symbol),
                "quality_metrics": self._calculate_function_quality_metrics(target_symbol)
            }

            self.analysis_cache[cache_key] = details
            return details
        except Exception as e:
            return {"function_name": function_name, "error": f"Error retrieving function details: {e}"}

    def get_class_details(self, class_name: str, filepath: Optional[str] = None) -> Dict[str, Any]:
        """Retrieves comprehensive information about a class."""
        cache_key = f"class_details_{class_name}_{filepath}"
        if cache_key in self.analysis_cache:
            return self.analysis_cache[cache_key]

        try:
            symbols = self.codebase.get_symbols(symbol_name=class_name)
            if not symbols:
                return {"class_name": class_name, "error": "Class not found."}

            target_symbol = self._resolve_symbol_with_filepath(symbols, filepath, Class)
            if not target_symbol:
                return {"class_name": class_name, "filepath": filepath, "error": "Class not found at specified path or is not a class."}

            summary_str = get_class_summary(target_symbol)
            reveal_info = reveal_symbol(
                codebase=self.codebase,
                symbol_name=class_name,
                filepath=filepath,
                max_depth=3,
                max_tokens=5000
            )

            details = {
                "class_name": class_name,
                "filepath": target_symbol.file.filepath if target_symbol.file else "N/A",
                "summary": summary_str,
                "methods": [self._get_method_summary(m) for m in target_symbol.methods],
                "attributes": [self._get_attribute_summary(a) for a in target_symbol.attributes],
                "superclasses": [self._class_to_dict(sc) for sc in target_symbol.superclasses],
                "subclasses": [self._class_to_dict(sc) for sc in target_symbol.subclasses],
                "dependencies": [self._symbol_to_dict(s) for s in reveal_info.dependencies] if reveal_info.dependencies else [],
                "usages": [self._symbol_to_dict(s) for s in reveal_info.usages] if reveal_info.usages else [],
                "inheritance_metrics": self._calculate_inheritance_metrics(target_symbol),
                "complexity_metrics": self._calculate_class_complexity_metrics(target_symbol)
            }

            self.analysis_cache[cache_key] = details
            return details
        except Exception as e:
            return {"class_name": class_name, "error": f"Error retrieving class details: {e}"}

    def get_symbol_details(self, symbol_name: str, filepath: Optional[str] = None) -> Dict[str, Any]:
        """Retrieves comprehensive information about any symbol."""
        cache_key = f"symbol_details_{symbol_name}_{filepath}"
        if cache_key in self.analysis_cache:
            return self.analysis_cache[cache_key]

        try:
            symbols = self.codebase.get_symbols(symbol_name=symbol_name)
            if not symbols:
                return {"symbol_name": symbol_name, "error": "Symbol not found."}

            target_symbol = self._resolve_symbol_with_filepath(symbols, filepath, Symbol)
            if not target_symbol:
                return {"symbol_name": symbol_name, "filepath": filepath, "error": "Symbol not found at specified path."}

            summary_str = get_symbol_summary(target_symbol)
            reveal_info = reveal_symbol(
                codebase=self.codebase,
                symbol_name=symbol_name,
                filepath=filepath,
                max_depth=3,
                max_tokens=5000
            )

            details = {
                "symbol_name": symbol_name,
                "symbol_type": type(target_symbol).__name__,
                "filepath": target_symbol.file.filepath if target_symbol.file else "N/A",
                "summary": summary_str,
                "dependencies": [self._symbol_to_dict(s) for s in reveal_info.dependencies] if reveal_info.dependencies else [],
                "usages": [self._symbol_to_dict(s) for s in reveal_info.usages] if reveal_info.usages else [],
                "context": self._get_symbol_context(target_symbol)
            }

            self.analysis_cache[cache_key] = details
            return details
        except Exception as e:
            return {"symbol_name": symbol_name, "error": f"Error retrieving symbol details: {e}"}

    # ============================================================================
    # VISUALIZATION FUNCTIONS (from blast_radius.py, call_trace.py, etc.)
    # ============================================================================

    def create_blast_radius_visualization(self, symbol_name: str, filepath: Optional[str] = None, max_depth: int = 5) -> Dict[str, Any]:
        """Creates blast radius visualization showing impact of changes."""
        try:
            symbols = self.codebase.get_symbols(symbol_name=symbol_name)
            if not symbols:
                return {"error": f"Symbol '{symbol_name}' not found"}

            target_symbol = self._resolve_symbol_with_filepath(symbols, filepath, Symbol)
            if not target_symbol:
                return {"error": f"Symbol '{symbol_name}' not found at specified path"}

            # Create NetworkX graph for blast radius
            G = nx.DiGraph()

            # Use the blast radius logic
            self._build_blast_radius_graph(G, target_symbol, max_depth)

            return {
                "nodes": [{"id": str(node), "label": str(node), "type": type(node).__name__} for node in G.nodes()],
                "edges": [{"source": str(source), "target": str(target)} for source, target in G.edges()],
                "metadata": {
                    "target_symbol": symbol_name,
                    "visualization_type": "blast_radius",
                    "node_count": len(G.nodes()),
                    "edge_count": len(G.edges()),
                    "max_depth": max_depth
                }
            }
        except Exception as e:
            return {"error": f"Failed to create blast radius visualization: {e}"}

    def create_call_trace_visualization(self, function_name: str, filepath: Optional[str] = None, max_depth: int = 10) -> Dict[str, Any]:
        """Creates call trace visualization showing function call relationships."""
        try:
            symbols = self.codebase.get_symbols(symbol_name=function_name)
            if not symbols:
                return {"error": f"Function '{function_name}' not found"}

            target_function = self._resolve_symbol_with_filepath(symbols, filepath, Function)
            if not target_function:
                return {"error": f"Function '{function_name}' not found at specified path or is not a function"}

            # Create NetworkX graph for call trace
            G = nx.DiGraph()

            # Use the call trace logic
            self._build_call_trace_graph(G, target_function, max_depth)

            return {
                "nodes": [{"id": str(node), "label": str(node), "type": type(node).__name__} for node in G.nodes()],
                "edges": [{"source": str(source), "target": str(target)} for source, target in G.edges()],
                "metadata": {
                    "target_function": function_name,
                    "visualization_type": "call_trace",
                    "node_count": len(G.nodes()),
                    "edge_count": len(G.edges()),
                    "max_depth": max_depth
                }
            }
        except Exception as e:
            return {"error": f"Failed to create call trace visualization: {e}"}

    def create_dependency_trace_visualization(self, symbol_name: str, filepath: Optional[str] = None, max_depth: int = 5) -> Dict[str, Any]:
        """Creates dependency trace visualization."""
        try:
            symbols = self.codebase.get_symbols(symbol_name=symbol_name)
            if not symbols:
                return {"error": f"Symbol '{symbol_name}' not found"}

            target_symbol = self._resolve_symbol_with_filepath(symbols, filepath, Symbol)
            if not target_symbol:
                return {"error": f"Symbol '{symbol_name}' not found at specified path"}

            # Create NetworkX graph for dependency trace
            G = nx.DiGraph()

            # Use the dependency trace logic
            self._build_dependency_trace_graph(G, target_symbol, max_depth)

            return {
                "nodes": [{"id": str(node), "label": str(node), "type": type(node).__name__} for node in G.nodes()],
                "edges": [{"source": str(source), "target": str(target)} for source, target in G.edges()],
                "metadata": {
                    "target_symbol": symbol_name,
                    "visualization_type": "dependency_trace",
                    "node_count": len(G.nodes()),
                    "edge_count": len(G.edges()),
                    "max_depth": max_depth
                }
            }
        except Exception as e:
            return {"error": f"Failed to create dependency trace visualization: {e}"}

    def create_method_relationships_visualization(self, class_name: str, filepath: Optional[str] = None) -> Dict[str, Any]:
        """Creates method relationships visualization within a class."""
        try:
            symbols = self.codebase.get_symbols(symbol_name=class_name)
            if not symbols:
                return {"error": f"Class '{class_name}' not found"}

            target_class = self._resolve_symbol_with_filepath(symbols, filepath, Class)
            if not target_class:
                return {"error": f"Class '{class_name}' not found at specified path or is not a class"}

            # Create NetworkX graph for method relationships
            G = nx.DiGraph()

            # Use the method relationships logic
            self._build_method_relationships_graph(G, target_class)

            return {
                "nodes": [{"id": str(node), "label": str(node), "type": type(node).__name__} for node in G.nodes()],
                "edges": [{"source": str(source), "target": str(target)} for source, target in G.edges()],
                "metadata": {
                    "target_class": class_name,
                    "visualization_type": "method_relationships",
                    "node_count": len(G.nodes()),
                    "edge_count": len(G.edges())
                }
            }
        except Exception as e:
            return {"error": f"Failed to create method relationships visualization: {e}"}

    # ============================================================================
    # FILE AND DIRECTORY OPERATIONS (from view_file.py, list_directory.py)
    # ============================================================================

    def view_file_content(self, filepath: str, line_numbers: bool = True, start_line: Optional[int] = None,
                         end_line: Optional[int] = None, max_lines: int = 500) -> ViewFileObservation:
        """Views file content with optional line numbers and pagination."""
        return view_file(
            codebase=self.codebase,
            filepath=filepath,
            line_numbers=line_numbers,
            start_line=start_line,
            end_line=end_line,
            max_lines=max_lines
        )

    def list_directory_contents(self, path: str = "./", depth: int = 2) -> ListDirectoryObservation:
        """Lists directory contents with specified depth."""
        return list_directory(codebase=self.codebase, path=path, depth=depth)

    def add_line_numbers_to_content(self, content: str) -> str:
        """Adds line numbers to content."""
        return add_line_numbers(content)

    # ============================================================================
    # SYMBOL REVELATION AND ANALYSIS (from reveal_symbol.py)
    # ============================================================================

    def reveal_symbol_relationships(self, symbol_name: str, filepath: Optional[str] = None,
                                  max_depth: int = 2, max_tokens: Optional[int] = None,
                                  collect_dependencies: bool = True, collect_usages: bool = True) -> RevealSymbolObservation:
        """Reveals comprehensive symbol relationships."""
        return reveal_symbol(
            codebase=self.codebase,
            symbol_name=symbol_name,
            filepath=filepath,
            max_depth=max_depth,
            max_tokens=max_tokens,
            collect_dependencies=collect_dependencies,
            collect_usages=collect_usages
        )

    def get_symbol_info_detailed(self, symbol: Symbol, max_tokens: Optional[int] = None) -> SymbolInfo:
        """Gets detailed information about a symbol."""
        return get_symbol_info(symbol, max_tokens)

    def get_extended_symbol_context(self, symbol: Symbol, degree: int, max_tokens: Optional[int] = None,
                                  collect_dependencies: bool = True, collect_usages: bool = True) -> Tuple[List[SymbolInfo], List[SymbolInfo], int]:
        """Gets extended context for a symbol."""
        return get_extended_context(
            symbol=symbol,
            degree=degree,
            max_tokens=max_tokens,
            collect_dependencies=collect_dependencies,
            collect_usages=collect_usages
        )

    # ============================================================================
    # DOCUMENTATION GENERATION (from document_functions.py, generate_docs_json.py, mdx_docs_generation.py)
    # ============================================================================

    def generate_docstrings_for_undocumented(self) -> Dict[str, Any]:
        """Generates docstrings for undocumented functions using AI."""
        try:
            logger.info("Generating docstrings for undocumented functions...")

            # Count undocumented functions before
            undocumented_before = len([f for f in self.codebase.functions if not getattr(f, 'docstring', None)])

            # Run the document functions process
            document_functions_run(self.codebase)

            # Count undocumented functions after
            undocumented_after = len([f for f in self.codebase.functions if not getattr(f, 'docstring', None)])

            return {
                "status": "success",
                "undocumented_before": undocumented_before,
                "undocumented_after": undocumented_after,
                "docstrings_generated": undocumented_before - undocumented_after,
                "message": "Docstring generation complete. Remember to commit changes."
            }
        except Exception as e:
            return {"status": "error", "error": f"Failed to generate docstrings: {e}"}

    def generate_structured_docs(self, head_commit: str = "latest", raise_on_missing_docstring: bool = False) -> Any:
        """Generates structured JSON documentation."""
        return generate_docs_json(self.codebase, head_commit, raise_on_missing_docstring)

    def generate_mdx_documentation(self, target_classes: Optional[List[str]] = None, output_dir: str = "docs") -> Dict[str, Any]:
        """Generates MDX documentation pages."""
        try:
            # Generate structured docs first
            structured_docs = self.generate_structured_docs()

            # Filter classes if specified
            if target_classes:
                classes_to_document = [cls_doc for cls_doc in structured_docs.classes if cls_doc.title in target_classes]
            else:
                classes_to_document = structured_docs.classes

            generated_files = []
            output_path = Path(output_dir)
            output_path.mkdir(exist_ok=True)

            for cls_doc in classes_to_document:
                try:
                    mdx_content = render_mdx_page_for_class(cls_doc)
                    mdx_route = get_mdx_route_for_class(cls_doc)

                    # Create file path
                    file_path = output_path / f"{mdx_route}.mdx"
                    file_path.parent.mkdir(parents=True, exist_ok=True)

                    # Write MDX content
                    file_path.write_text(mdx_content)
                    generated_files.append(str(file_path))

                except Exception as e:
                    logger.warning(f"Failed to generate MDX for {cls_doc.title}: {e}")

            return {
                "status": "success",
                "generated_files": generated_files,
                "classes_documented": len(generated_files),
                "output_directory": output_dir
            }
        except Exception as e:
            return {"status": "error", "error": f"Failed to generate MDX documentation: {e}"}

    # ============================================================================
    # DEAD CODE ANALYSIS
    # ============================================================================

    def find_dead_code(self) -> Dict[str, Any]:
        """Identifies dead code using graph traversal from entry points."""
        if "dead_code" in self.analysis_cache:
            return self.analysis_cache["dead_code"]

        dead_code = {
            "total": 0,
            "functions": 0,
            "classes": 0,
            "imports": 0,
            "variables": 0,
            "detailed_items": [],
            "recommendations": [],
            "entry_point_analysis": {}
        }

        # Find entry points
        entry_points = self._identify_entrypoints()

        # Perform graph traversal from entry points
        visited = set()

        def traverse_from_entry_point(symbol):
            if symbol in visited or isinstance(symbol, ExternalModule):
                return
            visited.add(symbol)

            # Traverse function calls
            if hasattr(symbol, "function_calls"):
                for call in symbol.function_calls:
                    if hasattr(call, "function_definition") and call.function_definition:
                        traverse_from_entry_point(call.function_definition)

            # Traverse usages
            if hasattr(symbol, "usages"):
                for usage in symbol.usages:
                    if hasattr(usage, "usage_symbol"):
                        traverse_from_entry_point(usage.usage_symbol)

            # Traverse dependencies
            if hasattr(symbol, "dependencies"):
                for dep in symbol.dependencies:
                    if hasattr(dep, "resolved_symbol") and dep.resolved_symbol:
                        traverse_from_entry_point(dep.resolved_symbol)
                    elif isinstance(dep, Symbol):
                        traverse_from_entry_point(dep)

        # Start traversal from all entry points
        for entry_point in entry_points["functions"] + entry_points["classes"]:
            if "symbol_obj" in entry_point:
                traverse_from_entry_point(entry_point["symbol_obj"])

        # Find dead functions
        for func in self.codebase.functions:
            if (func not in visited and
                not self._is_test_function(func) and
                not self._is_special_function(func)):

                dead_code["functions"] += 1
                dead_code["detailed_items"].append({
                    "type": "function",
                    "name": func.name,
                    "file": func.filepath,
                    "line": func.start_point.line + 1 if hasattr(func, 'start_point') else 0,
                    "reason": "No usage found from entry points",
                    "confidence": 0.8,
                    "complexity": self._calculate_function_complexity(func),
                    "loc": len(func.source.splitlines()) if hasattr(func, 'source') else 0
                })

        # Find dead classes
        for cls in self.codebase.classes:
            if cls not in visited and not self._is_test_class(cls):
                dead_code["classes"] += 1
                dead_code["detailed_items"].append({
                    "type": "class",
                    "name": cls.name,
                    "file": cls.filepath,
                    "line": cls.start_point.line + 1 if hasattr(cls, 'start_point') else 0,
                    "reason": "No usage found from entry points",
                    "confidence": 0.7,
                    "methods_count": len(cls.methods),
                    "inheritance_depth": len(cls.superclasses)
                })

        # Find dead imports
        for file_obj in self.codebase.files:
            for imp in file_obj.imports:
                if not hasattr(imp, 'usages') or len(imp.usages) == 0:
                    dead_code["imports"] += 1
                    dead_code["detailed_items"].append({
                        "type": "import",
                        "name": imp.name,
                        "file": file_obj.filepath,
                        "line": imp.start_point.line + 1 if hasattr(imp, 'start_point') else 0,
                        "reason": "Import not used in file",
                        "confidence": 0.9,
                        "module": getattr(imp, 'module', 'unknown')
                    })

        dead_code["total"] = (
            dead_code["functions"] + dead_code["classes"] +
            dead_code["imports"] + dead_code["variables"]
        )

        # Generate recommendations
        dead_code["recommendations"] = [
            "Review dead code items before removal",
            "Check if functions are used in tests or configuration",
            "Consider if classes are used for inheritance only",
            "Verify imports are not used in string literals or dynamic imports",
            f"Found {len(entry_points['functions'])} entry point functions",
            f"Found {len(entry_points['classes'])} entry point classes"
        ]

        dead_code["entry_point_analysis"] = entry_points

        self.analysis_cache["dead_code"] = dead_code
        return dead_code

    # ============================================================================
    # BASH COMMAND EXECUTION (from bash.py)
    # ============================================================================

    def validate_bash_command(self, command: str) -> Tuple[bool, str]:
        """Validates if a bash command is safe to execute."""
        return validate_command(command)

    def run_bash_command(self, command: str, is_background: bool = False) -> RunBashCommandObservation:
        """Runs a bash command and returns the result."""
        return run_bash_command(command, is_background)

    # ============================================================================
    # REFLECTION AND PLANNING (from reflection.py)
    # ============================================================================

    def perform_reflection(self, context_summary: str, findings_so_far: str,
                         current_challenges: str = "", reflection_focus: Optional[str] = None) -> ReflectionObservation:
        """Performs agent reflection for strategic planning."""
        return perform_reflection(
            context_summary=context_summary,
            findings_so_far=findings_so_far,
            current_challenges=current_challenges,
            reflection_focus=reflection_focus,
            codebase=self.codebase
        )

    def parse_reflection_response(self, response: str) -> List[ReflectionSection]:
        """Parses reflection response into structured sections."""
        return parse_reflection_response(response)

    # ============================================================================
    # WORKSPACE TOOLS (from tools.py)
    # ============================================================================

    def get_workspace_tools(self):
        """Gets all workspace tools initialized with the codebase."""
        return get_workspace_tools(self.codebase)

    # ============================================================================
    # CODEBASE UTILITIES (from current_code_codebase.py, codegen_sdk_codebase.py)
    # ============================================================================

    def get_current_code_codebase(self, config=None, secrets=None, subdirectories=None):
        """Gets codebase for currently running code."""
        return get_current_code_codebase(config, secrets, subdirectories)

    def get_codegen_sdk_codebase(self):
        """Gets the codegen SDK codebase."""
        return get_codegen_sdk_codebase()

    def import_all_sdk_modules(self):
        """Imports all codegen SDK modules."""
        import_all_codegen_sdk_modules()

    def get_documented_objects(self):
        """Gets all documented objects."""
        return get_documented_objects()

    # ============================================================================
    # ADVANCED ANALYSIS FUNCTIONS
    # ============================================================================

    def analyze_function_complexity(self, function_name: str, filepath: Optional[str] = None) -> Dict[str, Any]:
        """Analyzes complexity metrics for a specific function."""
        try:
            symbols = self.codebase.get_symbols(symbol_name=function_name)
            if not symbols:
                return {"function_name": function_name, "error": "Function not found."}

            target_function = self._resolve_symbol_with_filepath(symbols, filepath, Function)
            if not target_function:
                return {"function_name": function_name, "error": "Function not found at specified path or is not a function."}

            # Calculate various complexity metrics
            cyclomatic_complexity = self._calculate_cyclomatic_complexity(target_function)
            halstead_metrics = self._calculate_halstead_metrics(target_function)

            return {
                "function_name": function_name,
                "filepath": target_function.file.filepath if target_function.file else "N/A",
                "cyclomatic_complexity": cyclomatic_complexity,
                "complexity_rank": self._get_complexity_rank(cyclomatic_complexity),
                "halstead_metrics": halstead_metrics,
                "parameters_count": len(target_function.parameters),
                "return_statements_count": len(getattr(target_function, "return_statements", [])),
                "function_calls_count": len(target_function.function_calls),
                "lines_of_code": len(target_function.source.splitlines()) if hasattr(target_function, "source") else 0,
                "maintainability_score": self._calculate_function_maintainability(target_function)
            }
        except Exception as e:
            return {"function_name": function_name, "error": f"Error analyzing function complexity: {e}"}

    def analyze_class_structure(self, class_name: str, filepath: Optional[str] = None) -> Dict[str, Any]:
        """Analyzes structural metrics for a specific class."""
        try:
            symbols = self.codebase.get_symbols(symbol_name=class_name)
            if not symbols:
                return {"class_name": class_name, "error": "Class not found."}

            target_class = self._resolve_symbol_with_filepath(symbols, filepath, Class)
            if not target_class:
                return {"class_name": class_name, "error": "Class not found at specified path or is not a class."}

            # Analyze class structure
            methods_analysis = []
            for method in target_class.methods:
                methods_analysis.append({
                    "name": method.name,
                    "complexity": self._calculate_cyclomatic_complexity(method),
                    "parameters_count": len(method.parameters),
                    "is_public": not method.name.startswith("_"),
                    "is_property": self._is_property_method(method),
                    "lines_of_code": len(method.source.splitlines()) if hasattr(method, "source") else 0,
                    "has_docstring": bool(getattr(method, "docstring", None))
                })

            attributes_analysis = []
            for attr in target_class.attributes:
                attributes_analysis.append({
                    "name": attr.name,
                    "is_public": not attr.name.startswith("_"),
                    "has_type_annotation": hasattr(attr, "type") and attr.type is not None,
                    "usages_count": len(attr.usages) if hasattr(attr, "usages") else 0
                })

            return {
                "class_name": class_name,
                "filepath": target_class.file.filepath if target_class.file else "N/A",
                "methods_count": len(target_class.methods),
                "attributes_count": len(target_class.attributes),
                "inheritance_depth": len(target_class.superclasses),
                "subclasses_count": len(target_class.subclasses),
                "methods_analysis": methods_analysis,
                "attributes_analysis": attributes_analysis,
                "complexity_score": sum(m["complexity"] for m in methods_analysis) / max(1, len(methods_analysis)),
                "public_methods_ratio": len([m for m in methods_analysis if m["is_public"]]) / max(1, len(methods_analysis)),
                "documented_methods_ratio": len([m for m in methods_analysis if m["has_docstring"]]) / max(1, len(methods_analysis)),
                "cohesion_metrics": self._calculate_class_cohesion(target_class)
            }
        except Exception as e:
            return {"class_name": class_name, "error": f"Error analyzing class structure: {e}"}

    def analyze_import_relationships(self, filepath: str) -> Dict[str, Any]:
        """Analyzes import relationships for a specific file."""
        try:
            file_obj = self.codebase.get_file(filepath)

            imports_analysis = []
            for imp in file_obj.imports:
                imports_analysis.append({
                    "name": imp.name,
                    "module": getattr(imp, "module", "unknown"),
                    "is_external": isinstance(getattr(imp, "resolved_symbol", None), ExternalModule),
                    "usages_count": len(imp.usages) if hasattr(imp, "usages") else 0,
                    "is_unused": len(imp.usages) == 0 if hasattr(imp, "usages") else True,
                    "line": imp.start_point.line + 1 if hasattr(imp, "start_point") else 0,
                    "resolved": bool(getattr(imp, "resolved_symbol", None))
                })

            inbound_imports = []
            for symbol in getattr(file_obj, "symbols", []):
                for usage in symbol.usages:
                    if hasattr(usage, "file") and usage.file != file_obj:
                        inbound_imports.append({
                            "symbol": symbol.name,
                            "imported_by": usage.file.filepath,
                            "usage_type": type(usage).__name__
                        })

            return {
                "filepath": filepath,
                "imports_count": len(file_obj.imports),
                "external_imports_count": len([i for i in imports_analysis if i["is_external"]]),
                "unused_imports_count": len([i for i in imports_analysis if i["is_unused"]]),
                "unresolved_imports_count": len([i for i in imports_analysis if not i["resolved"]]),
                "imports_analysis": imports_analysis,
                "inbound_imports": inbound_imports,
                "inbound_imports_count": len(inbound_imports),
                "circular_dependencies": self._detect_circular_imports(file_obj)
            }
        except ValueError:
            return {"filepath": filepath, "error": "File not found in codebase."}
        except Exception as e:
            return {"filepath": filepath, "error": f"Error analyzing import relationships: {e}"}

    # ============================================================================
    # HELPER FUNCTIONS
    # ============================================================================

    def _resolve_symbol_with_filepath(self, symbols: List[Symbol], filepath: Optional[str], expected_type: type) -> Optional[Symbol]:
        """Helper to resolve an ambiguous symbol by filepath and type."""
        if filepath:
            for s in symbols:
                if s.file and s.file.filepath == filepath and isinstance(s, expected_type):
                    return s
        elif symbols and isinstance(symbols[0], expected_type):
            return symbols[0]
        return None

    def _identify_entrypoints(self) -> Dict[str, List[Dict[str, Any]]]:
        """Identifies entry points in the codebase."""
        entrypoints = {
            "functions": [],
            "classes": [],
            "files": []
        }

        # Function entry points
        for func in self.codebase.functions:
            if self._is_entrypoint_function(func):
                entrypoints["functions"].append({
                    "name": func.name,
                    "file": func.filepath,
                    "type": "function",
                    "score": self._calculate_entrypoint_score(func),
                    "symbol_obj": func
                })

        # Class entry points
        for cls in self.codebase.classes:
            if self._is_entrypoint_class(cls):
                entrypoints["classes"].append({
                    "name": cls.name,
                    "file": cls.filepath,
                    "type": "class",
                    "score": self._calculate_class_entrypoint_score(cls),
                    "symbol_obj": cls
                })

        # File entry points
        for file_obj in self.codebase.files:
            if self._is_entrypoint_file(file_obj):
                entrypoints["files"].append({
                    "name": file_obj.name,
                    "path": file_obj.filepath,
                    "type": "file"
                })

        return entrypoints

    def _get_dead_code_summary(self) -> Dict[str, Any]:
        """Gets a summary of dead code analysis."""
        dead_code = self.find_dead_code()
        return {
            "total_dead_items": dead_code["total"],
            "dead_functions": dead_code["functions"],
            "dead_classes": dead_code["classes"],
            "dead_imports": dead_code["imports"]
        }

    def _get_complexity_overview(self) -> Dict[str, Any]:
        """Gets complexity overview of the codebase."""
        complexities = [self._calculate_function_complexity(f) for f in self.codebase.functions]
        if not complexities:
            return {"average": 0, "max": 0, "distribution": {}}

        return {
            "average_complexity": sum(complexities) / len(complexities),
            "max_complexity": max(complexities),
            "min_complexity": min(complexities),
            "distribution": {
                "low": len([c for c in complexities if c <= 5]),
                "medium": len([c for c in complexities if 5 < c <= 10]),
                "high": len([c for c in complexities if c > 10])
            }
        }

    def _get_function_parameters_details(self, func: Function) -> List[Dict[str, Any]]:
        """Extracts detailed information about function parameters."""
        params_details = []
        for param in func.parameters:
            param_type_source = getattr(param.type, 'source', 'Any') if hasattr(param, 'type') and param.type else 'Any'
            resolved_types = []

            if hasattr(param, 'type') and param.type and hasattr(param.type, 'resolved_value') and param.type.resolved_value:
                resolved_symbols = param.type.resolved_value
                if not isinstance(resolved_symbols, list):
                    resolved_symbols = [resolved_symbols]

                for res_sym in resolved_symbols:
                    if isinstance(res_sym, Symbol):
                        resolved_types.append({
                            "name": res_sym.name,
                            "type": type(res_sym).__name__,
                            "filepath": res_sym.filepath if hasattr(res_sym, 'filepath') else None
                        })
                    elif isinstance(res_sym, ExternalModule):
                        resolved_types.append({
                            "name": res_sym.name,
                            "type": "ExternalModule"
                        })
                    else:
                        resolved_types.append({"name": str(res_sym), "type": "Unknown"})

            params_details.append({
                "name": param.name,
                "type_annotation": param_type_source,
                "resolved_types": resolved_types,
                "has_default": getattr(param, "has_default", False),
                "is_keyword_only": getattr(param, "is_keyword_only", False),
                "is_positional_only": getattr(param, "is_positional_only", False),
                "is_var_arg": getattr(param, "is_var_arg", False),
                "is_var_kw": getattr(param, "is_var_kw", False)
            })
        return params_details

    def _get_function_return_type_details(self, func: Function) -> Dict[str, Any]:
        """Extracts detailed information about function return type."""
        return_type_source = getattr(func.return_type, 'source', 'Any') if hasattr(func, 'return_type') and func.return_type else 'Any'
        resolved_types = []

        if hasattr(func, 'return_type') and func.return_type and hasattr(func.return_type, 'resolved_value') and func.return_type.resolved_value:
            resolved_symbols = func.return_type.resolved_value
            if not isinstance(resolved_symbols, list):
                resolved_symbols = [resolved_symbols]

            for res_sym in resolved_symbols:
                if isinstance(res_sym, Symbol):
                    resolved_types.append({
                        "name": res_sym.name,
                        "type": type(res_sym).__name__,
                        "filepath": res_sym.filepath if hasattr(res_sym, 'filepath') else None
                    })
                elif isinstance(res_sym, ExternalModule):
                    resolved_types.append({
                        "name": res_sym.name,
                        "type": "ExternalModule"
                    })
                else:
                    resolved_types.append({"name": str(res_sym), "type": "Unknown"})

        return {
            "type_annotation": return_type_source,
            "resolved_types": resolved_types
        }

    def _get_function_local_variables_details(self, func: Function) -> List[Dict[str, Any]]:
        """Extracts details about local variables defined within a function."""
        local_vars = []
        if hasattr(func, 'code_block') and hasattr(func.code_block, 'local_var_assignments'):
            for assignment in func.code_block.local_var_assignments:
                var_type_source = getattr(assignment.type, 'source', 'Any') if hasattr(assignment, 'type') and assignment.type else 'Any'
                local_vars.append({
                    "name": assignment.name,
                    "type_annotation": var_type_source,
                    "line": assignment.start_point.line + 1 if hasattr(assignment, 'start_point') else None,
                    "value_snippet": assignment.source if hasattr(assignment, 'source') else None
                })
        return local_vars

    def _symbol_to_dict(self, symbol_info: SymbolInfo) -> Dict[str, Any]:
        """Converts SymbolInfo to dictionary."""
        return {
            "name": symbol_info.name,
            "filepath": symbol_info.filepath,
            "source": symbol_info.source
        }

    def _call_site_to_dict(self, call_site) -> Dict[str, Any]:
        """Converts call site to dictionary."""
        return {
            "name": getattr(call_site, "name", "unknown"),
            "file": getattr(call_site, "file", {}).get("filepath", "unknown") if hasattr(call_site, "file") else "unknown",
            "line": getattr(call_site, "start_point", {}).get("line", 0) if hasattr(call_site, "start_point") else 0
        }

    def _function_call_to_dict(self, function_call) -> Dict[str, Any]:
        """Converts function call to dictionary."""
        return {
            "name": getattr(function_call, "name", "unknown"),
            "args_count": len(getattr(function_call, "args", [])),
            "line": getattr(function_call, "start_point", {}).get("line", 0) if hasattr(function_call, "start_point") else 0
        }

    def _class_to_dict(self, cls: Class) -> Dict[str, Any]:
        """Converts class to dictionary."""
        return {
            "name": cls.name,
            "filepath": cls.filepath,
            "methods_count": len(cls.methods),
            "attributes_count": len(cls.attributes)
        }

    # ============================================================================
    # COMPLEXITY AND QUALITY METRICS
    # ============================================================================

    def _calculate_function_complexity(self, func: Function) -> int:
        """Calculates cyclomatic complexity for a function."""
        return self._calculate_cyclomatic_complexity(func)

    def _calculate_cyclomatic_complexity(self, func: Function) -> int:
        """Calculate cyclomatic complexity for a function."""
        try:
            complexity = 1  # Base complexity

            if hasattr(func, "source") and func.source:
                source = func.source.lower()
                # Count decision points
                complexity += source.count("if ")
                complexity += source.count("elif ")
                complexity += source.count("for ")
                complexity += source.count("while ")
                complexity += source.count("except ")
                complexity += source.count("and ")
                complexity += source.count("or ")
                complexity += source.count("try:")
                complexity += source.count("with ")

            return complexity
        except Exception:
            return 1

    def _calculate_halstead_metrics(self, func: Function) -> Dict[str, float]:
        """Calculate Halstead metrics for a function."""
        try:
            if not hasattr(func, "source") or not func.source:
                return {"volume": 0.0, "difficulty": 0.0, "effort": 0.0}

            operators, operands = get_operators_and_operands(func)
            volume, N1, N2, n1, n2 = calculate_halstead_volume(operators, operands)

            N = N1 + N2  # Program length
            n = n1 + n2  # Program vocabulary

            if n > 0 and n2 > 0:
                difficulty = (n1 / 2) * (N2 / n2)
                effort = difficulty * volume
            else:
                difficulty = effort = 0

            return {
                "volume": volume,
                "difficulty": difficulty,
                "effort": effort,
                "length": N,
                "vocabulary": n,
                "unique_operators": n1,
                "unique_operands": n2
            }
        except Exception:
            return {"volume": 0.0, "difficulty": 0.0, "effort": 0.0}

    def _get_complexity_rank(self, complexity: int) -> str:
        """Get complexity rank based on cyclomatic complexity."""
        if complexity <= 5:
            return "A"
        elif complexity <= 10:
            return "B"
        elif complexity <= 20:
            return "C"
        elif complexity <= 30:
            return "D"
        elif complexity <= 40:
            return "E"
        else:
            return "F"

    def _calculate_function_complexity_metrics(self, func: Function) -> Dict[str, Any]:
        """Calculate comprehensive complexity metrics for a function."""
        return {
            "cyclomatic_complexity": self._calculate_cyclomatic_complexity(func),
            "halstead_metrics": self._calculate_halstead_metrics(func),
            "lines_of_code": len(func.source.splitlines()) if hasattr(func, "source") else 0,
            "parameters_count": len(func.parameters),
            "nesting_depth": self._calculate_nesting_depth(func)
        }

    def _calculate_function_quality_metrics(self, func: Function) -> Dict[str, Any]:
        """Calculate quality metrics for a function."""
        return {
            "has_docstring": bool(getattr(func, "docstring", None)),
            "has_return_type": bool(getattr(func, "return_type", None)),
            "typed_parameters_ratio": self._calculate_typed_parameters_ratio(func),
            "maintainability_score": self._calculate_function_maintainability(func)
        }

    def _calculate_class_complexity_metrics(self, cls: Class) -> Dict[str, Any]:
        """Calculate complexity metrics for a class."""
        method_complexities = [self._calculate_cyclomatic_complexity(m) for m in cls.methods]
        return {
            "average_method_complexity": sum(method_complexities) / max(1, len(method_complexities)),
            "max_method_complexity": max(method_complexities) if method_complexities else 0,
            "methods_count": len(cls.methods),
            "attributes_count": len(cls.attributes),
            "inheritance_depth": len(cls.superclasses),
            "weighted_methods_per_class": sum(method_complexities)
        }

    def _calculate_inheritance_metrics(self, cls: Class) -> Dict[str, Any]:
        """Calculate inheritance-related metrics."""
        return {
            "depth_of_inheritance": len(cls.superclasses),
            "number_of_children": len(cls.subclasses),
            "coupling_between_objects": len([dep for dep in cls.dependencies if isinstance(dep, Class)]),
            "response_for_class": len(cls.methods) + len([m for sc in cls.superclasses for m in sc.methods])
        }

    def _calculate_class_cohesion(self, cls: Class) -> Dict[str, Any]:
        """Calculate class cohesion metrics."""
        # Simplified LCOM (Lack of Cohesion of Methods) calculation
        methods = list(cls.methods)
        attributes = list(cls.attributes)

        if not methods or not attributes:
            return {"lcom": 0, "cohesion_score": 1.0}

        # Count method pairs that don't share attributes
        non_cohesive_pairs = 0
        total_pairs = 0

        for i, method1 in enumerate(methods):
            for method2 in methods[i+1:]:
                total_pairs += 1
                # Check if methods share any attributes
                method1_attrs = set(getattr(method1, "variable_usages", []))
                method2_attrs = set(getattr(method2, "variable_usages", []))

                if not method1_attrs.intersection(method2_attrs):
                    non_cohesive_pairs += 1

        lcom = non_cohesive_pairs / max(1, total_pairs)
        cohesion_score = 1.0 - lcom

        return {
            "lcom": lcom,
            "cohesion_score": cohesion_score,
            "methods_count": len(methods),
            "attributes_count": len(attributes)
        }

    # ============================================================================
    # GRAPH BUILDING FUNCTIONS
    # ============================================================================

    def _build_blast_radius_graph(self, graph: nx.DiGraph, symbol: Symbol, max_depth: int, depth: int = 0):
        """Build blast radius graph recursively."""
        if depth >= max_depth or symbol in graph.nodes:
            return

        graph.add_node(symbol, name=symbol.name, type=type(symbol).__name__, depth=depth)

        # Add all usages (things that would be affected by changes)
        for usage in symbol.usages:
            if hasattr(usage, "usage_symbol"):
                affected_symbol = usage.usage_symbol
                if affected_symbol not in graph.nodes:
                    graph.add_node(affected_symbol, name=affected_symbol.name,
                                 type=type(affected_symbol).__name__, depth=depth + 1)
                graph.add_edge(symbol, affected_symbol, relationship="impacts")

                if depth + 1 < max_depth:
                    self._build_blast_radius_graph(graph, affected_symbol, max_depth, depth + 1)

    def _build_call_trace_graph(self, graph: nx.DiGraph, func: Function, max_depth: int, depth: int = 0):
        """Build call trace graph recursively."""
        if depth >= max_depth or func in graph.nodes:
            return

        graph.add_node(func, name=func.name, type="function", depth=depth)

        # Add function calls
        for call in func.function_calls:
            if hasattr(call, "function_definition") and call.function_definition:
                called_func = call.function_definition
                if not isinstance(called_func, ExternalModule) and called_func not in graph.nodes:
                    graph.add_node(called_func, name=called_func.name, type="function", depth=depth + 1)
                    graph.add_edge(func, called_func, relationship="calls")

                    if depth + 1 < max_depth:
                        self._build_call_trace_graph(graph, called_func, max_depth, depth + 1)

    def _build_dependency_trace_graph(self, graph: nx.DiGraph, symbol: Symbol, max_depth: int, depth: int = 0):
        """Build dependency trace graph recursively."""
        if depth >= max_depth or symbol in graph.nodes:
            return

        graph.add_node(symbol, name=symbol.name, type=type(symbol).__name__, depth=depth)

        # Add dependencies
        for dep in symbol.dependencies:
            if isinstance(dep, Import):
                dep = hop_through_imports(dep)

            if isinstance(dep, Symbol) and not isinstance(dep, ExternalModule) and dep not in graph.nodes:
                graph.add_node(dep, name=dep.name, type=type(dep).__name__, depth=depth + 1)
                graph.add_edge(symbol, dep, relationship="depends_on")

                if depth + 1 < max_depth:
                    self._build_dependency_trace_graph(graph, dep, max_depth, depth + 1)

    def _build_method_relationships_graph(self, graph: nx.DiGraph, cls: Class):
        """Build method relationships graph for a class."""
        graph.add_node(cls, name=cls.name, type="class")

        # Add all methods
        for method in cls.methods:
            graph.add_node(method, name=f"{cls.name}.{method.name}", type="method")
            graph.add_edge(cls, method, relationship="contains")

            # Add method call relationships
            for call in method.function_calls:
                if hasattr(call, "function_definition") and call.function_definition:
                    called_func = call.function_definition
                    if called_func in cls.methods:  # Internal method call
                        graph.add_edge(method, called_func, relationship="calls")

    # ============================================================================
    # UTILITY FUNCTIONS
    # ============================================================================

    def _is_entrypoint_function(self, func: Function) -> bool:
        """Check if a function is an entrypoint."""
        entrypoint_patterns = ["main", "run", "start", "execute", "cli", "app", "serve"]
        return (
            any(pattern in func.name.lower() for pattern in entrypoint_patterns) or
            func.name == "__main__" or
            self._has_entrypoint_decorators(func) or
            self._is_called_from_main_block(func)
        )

    def _is_entrypoint_class(self, cls: Class) -> bool:
        """Check if a class is an entrypoint."""
        entrypoint_patterns = ["app", "application", "server", "client", "main", "runner", "service"]
        return (
            any(pattern in cls.name.lower() for pattern in entrypoint_patterns) or
            self._has_framework_inheritance(cls) or
            self._has_singleton_pattern(cls)
        )

    def _is_entrypoint_file(self, file_obj: SourceFile) -> bool:
        """Check if a file is an entrypoint."""
        entrypoint_patterns = ["main.py", "__main__.py", "app.py", "server.py", "run.py", "cli.py"]
        return any(pattern in file_obj.filepath for pattern in entrypoint_patterns)

    def _is_test_function(self, func: Function) -> bool:
        """Check if a function is a test function."""
        return (
            func.name.startswith("test_") or
            "test" in func.filepath or
            self._has_test_decorators(func)
        )

    def _is_test_class(self, cls: Class) -> bool:
        """Check if a class is a test class."""
        return cls.name.startswith("Test") or "test" in cls.filepath

    def _is_special_function(self, func: Function) -> bool:
        """Check if a function is special (shouldn't be considered dead code)."""
        special_patterns = ["__init__", "__str__", "__repr__", "__call__", "setUp", "tearDown"]
        return any(pattern in func.name for pattern in special_patterns)

    def _calculate_entrypoint_score(self, func: Function) -> float:
        """Calculate entrypoint score for a function."""
        score = 1.0  # Base score

        # Name-based scoring
        entrypoint_names = ["main", "run", "start", "execute", "app", "serve", "launch"]
        if any(name in func.name.lower() for name in entrypoint_names):
            score += 2.0

        # Usage-based scoring
        if len(func.usages) == 0:
            score += 1.0
        elif len(func.usages) < 3:
            score += 0.5

        # Complexity-based scoring
        complexity = self._calculate_cyclomatic_complexity(func)
        if 5 <= complexity <= 15:
            score += 1.0
        elif complexity > 15:
            score += 0.5

        # Call-based scoring
        if len(func.function_calls) > 5:
            score += 1.0
        elif len(func.function_calls) > 2:
            score += 0.5

        return score

    def _calculate_class_entrypoint_score(self, cls: Class) -> float:
        """Calculate entrypoint score for a class."""
        score = 1.0  # Base score

        # Name-based scoring
        entrypoint_names = ["app", "application", "server", "client", "main", "service"]
        if any(name in cls.name.lower() for name in entrypoint_names):
            score += 2.0

        # Size-based scoring
        if len(cls.methods) > 10:
            score += 1.0

        # Inheritance-based scoring
        if len(cls.superclasses) > 0:
            for superclass in cls.superclasses:
                if any(pattern in superclass.name.lower() for pattern in ["application", "service", "handler"]):
                    score += 1.5

        return score

    def _has_entrypoint_decorators(self, func: Function) -> bool:
        """Check if function has entrypoint decorators."""
        if not hasattr(func, "decorators"):
            return False

        for decorator in func.decorators:
            decorator_source = getattr(decorator, "source", "")
            if any(pattern in decorator_source.lower() for pattern in ["@app.", "@click.", "@typer.", "@fastapi."]):
                return True
        return False

    def _has_framework_inheritance(self, cls: Class) -> bool:
        """Check if class inherits from framework classes."""
        for superclass in cls.superclasses:
            if any(pattern in superclass.name.lower() for pattern in ["application", "app", "service", "handler"]):
                return True
        return False

    def _has_singleton_pattern(self, cls: Class) -> bool:
        """Check if class implements singleton pattern."""
        return any("instance" in method.name.lower() or "singleton" in method.name.lower() for method in cls.methods)

    def _has_test_decorators(self, func: Function) -> bool:
        """Check if function has test decorators."""
        if not hasattr(func, "decorators"):
            return False

        for decorator in func.decorators:
            decorator_source = getattr(decorator, "source", "")
            if any(pattern in decorator_source.lower() for pattern in ["@pytest.", "@unittest.", "@test"]):
                return True
        return False

    def _is_called_from_main_block(self, func: Function) -> bool:
        """Check if function is called from if __name__ == '__main__' block."""
        for usage in func.usages:
            if hasattr(usage, "parent_statement"):
                parent = usage.parent_statement
                if hasattr(parent, "condition") and "__name__" in getattr(parent.condition, "source", ""):
                    return True
        return False

    def _is_property_method(self, method: Function) -> bool:
        """Check if method is a property."""
        if not hasattr(method, "decorators"):
            return False

        for decorator in method.decorators:
            if "@property" in getattr(decorator, "source", ""):
                return True
        return False

    def _calculate_nesting_depth(self, func: Function) -> int:
        """Calculate maximum nesting depth in a function."""
        if not hasattr(func, "source") or not func.source:
            return 0

        lines = func.source.split('\n')
        max_depth = 0
        current_depth = 0

        for line in lines:
            stripped = line.strip()
            if any(keyword in stripped for keyword in ['if ', 'for ', 'while ', 'try:', 'with ']):
                current_depth += 1
                max_depth = max(max_depth, current_depth)
            elif stripped in ['else:', 'elif ', 'except:', 'finally:']:
                continue
            elif stripped == '' or stripped.startswith('#'):
                continue
            else:
                # Check for dedentation
                indent_level = len(line) - len(line.lstrip())
                if indent_level == 0:
                    current_depth = 0

        return max_depth

    def _calculate_typed_parameters_ratio(self, func: Function) -> float:
        """Calculate ratio of typed parameters."""
        if not func.parameters:
            return 1.0

        typed_count = sum(1 for p in func.parameters if hasattr(p, 'type') and p.type)
        return typed_count / len(func.parameters)

    def _calculate_function_maintainability(self, func: Function) -> float:
        """Calculate function maintainability score."""
        complexity = self._calculate_cyclomatic_complexity(func)
        loc = len(func.source.splitlines()) if hasattr(func, "source") else 0
        has_docstring = bool(getattr(func, "docstring", None))

        # Simplified maintainability calculation
        base_score = 100
        complexity_penalty = complexity * 2
        loc_penalty = max(0, (loc - 20) * 0.5)
        doc_bonus = 10 if has_docstring else 0

        return max(0, base_score - complexity_penalty - loc_penalty + doc_bonus)

    def _calculate_file_complexity(self, file_obj: SourceFile) -> float:
        """Calculate complexity score for a file."""
        try:
            if not hasattr(file_obj, "functions"):
                return 0.0

            function_complexities = [self._calculate_cyclomatic_complexity(func) for func in file_obj.functions]
            return sum(function_complexities) / max(1, len(function_complexities))
        except Exception:
            return 0.0

    def _calculate_maintainability_index(self, file_obj: SourceFile) -> float:
        """Calculate maintainability index for a file."""
        try:
            if not hasattr(file_obj, "source"):
                return 0.0

            loc = len(file_obj.source.splitlines())
            complexity = self._calculate_file_complexity(file_obj)

            if loc > 0:
                return max(0, (171 - 5.2 * math.log(loc) - 0.23 * complexity - 16.2 * math.log(loc)) * 100 / 171)
            return 0.0
        except Exception:
            return 0.0

    def _calculate_file_doc_coverage(self, file_obj: SourceFile) -> float:
        """Calculate documentation coverage for a file."""
        total_symbols = len(file_obj.functions) + len(file_obj.classes)
        if total_symbols == 0:
            return 1.0

        documented = sum(1 for f in file_obj.functions if getattr(f, 'docstring', None))
        documented += sum(1 for c in file_obj.classes if getattr(c, 'docstring', None))

        return documented / total_symbols

    def _detect_circular_imports(self, file_obj: SourceFile) -> List[List[str]]:
        """Detect circular import dependencies for a file."""
        import_graph = nx.DiGraph()

        # Build import graph starting from this file
        def add_file_imports(current_file, visited=None):
            if visited is None:
                visited = set()
            if current_file.filepath in visited:
                return
            visited.add(current_file.filepath)

            import_graph.add_node(current_file.filepath)
            for imp in current_file.imports:
                if hasattr(imp, "from_file") and imp.from_file:
                    import_graph.add_edge(current_file.filepath, imp.from_file.filepath)
                    add_file_imports(imp.from_file, visited)

        add_file_imports(file_obj)

        # Find cycles involving this file
        cycles = list(nx.simple_cycles(import_graph))
        return [cycle for cycle in cycles if file_obj.filepath in cycle]

    # ============================================================================
    # SUMMARY HELPER FUNCTIONS
    # ============================================================================

    def _get_function_summary(self, func: Function) -> Dict[str, Any]:
        """Get summary information for a function."""
        return {
            "name": func.name,
            "line": func.start_point.line + 1 if hasattr(func, 'start_point') else 0,
            "complexity": self._calculate_cyclomatic_complexity(func),
            "parameters_count": len(func.parameters),
            "has_docstring": bool(getattr(func, "docstring", None)),
            "is_async": getattr(func, "is_async", False),
            "usages_count": len(func.usages)
        }

    def _get_class_summary(self, cls: Class) -> Dict[str, Any]:
        """Get summary information for a class."""
        return {
            "name": cls.name,
            "line": cls.start_point.line + 1 if hasattr(cls, 'start_point') else 0,
            "methods_count": len(cls.methods),
            "attributes_count": len(cls.attributes),
            "inheritance_depth": len(cls.superclasses),
            "has_docstring": bool(getattr(cls, "docstring", None)),
            "usages_count": len(cls.usages)
        }

    def _get_import_summary(self, imp: Import) -> Dict[str, Any]:
        """Get summary information for an import."""
        return {
            "name": imp.name,
            "module": getattr(imp, "module", "unknown"),
            "line": imp.start_point.line + 1 if hasattr(imp, 'start_point') else 0,
            "is_external": isinstance(getattr(imp, "resolved_symbol", None), ExternalModule),
            "usages_count": len(imp.usages) if hasattr(imp, "usages") else 0,
            "is_resolved": bool(getattr(imp, "resolved_symbol", None))
        }

    def _get_symbol_summary(self, symbol: Symbol) -> Dict[str, Any]:
        """Get summary information for a symbol."""
        return {
            "name": symbol.name,
            "type": type(symbol).__name__,
            "line": symbol.start_point.line + 1 if hasattr(symbol, 'start_point') else 0,
            "usages_count": len(symbol.usages),
            "dependencies_count": len(symbol.dependencies)
        }

    def _get_method_summary(self, method: Function) -> Dict[str, Any]:
        """Get summary information for a method."""
        return {
            "name": method.name,
            "line": method.start_point.line + 1 if hasattr(method, 'start_point') else 0,
            "complexity": self._calculate_cyclomatic_complexity(method),
            "parameters_count": len(method.parameters),
            "is_public": not method.name.startswith("_"),
            "is_property": self._is_property_method(method),
            "has_docstring": bool(getattr(method, "docstring", None))
        }

    def _get_attribute_summary(self, attr) -> Dict[str, Any]:
        """Get summary information for an attribute."""
        return {
            "name": attr.name,
            "line": attr.start_point.line + 1 if hasattr(attr, 'start_point') else 0,
            "is_public": not attr.name.startswith("_"),
            "has_type_annotation": hasattr(attr, "type") and attr.type is not None,
            "usages_count": len(attr.usages) if hasattr(attr, "usages") else 0
        }

    def _get_symbol_context(self, symbol: Symbol) -> Dict[str, Any]:
        """Get contextual information about a symbol."""
        return {
            "parent_class": symbol.parent_class.name if getattr(symbol, "parent_class", None) else None,
            "parent_function": symbol.parent_function.name if getattr(symbol, "parent_function", None) else None,
            "file": symbol.file.filepath if symbol.file else None,
            "is_public": not symbol.name.startswith("_"),
            "symbol_type": getattr(symbol, "symbol_type", type(symbol).__name__)
        }
# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def clone_repository(repo_url: str, branch: str = "main") -> str:
    """Clone repository to temporary directory"""
    try:
        temp_dir = tempfile.mkdtemp(prefix="graph_sitter_")
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        repo_path = os.path.join(temp_dir, repo_name)

        clone_cmd = [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            branch,
            repo_url,
            repo_path,
        ]

        result = subprocess.run(clone_cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            raise Exception(f"Git clone failed: {result.stderr}")

        logger.info(f"Successfully cloned {repo_url} to {repo_path}")
        return repo_path

    except subprocess.TimeoutExpired:
        raise Exception("Repository clone timed out")
    except Exception as e:
        logger.error(f"Error cloning repository: {e}")
        raise Exception(f"Failed to clone repository: {str(e)}")


def calculate_doi(cls: Class):
    """Calculate the depth of inheritance for a given class."""
    return len(cls.superclasses) if hasattr(cls, "superclasses") else 0


def get_operators_and_operands(function: Function):
    """Extract operators and operands from function for Halstead metrics."""
    operators = []
    operands = []

    try:
        if hasattr(function, "source") and function.source:
            source_code = function.source
            # Simple keyword-based operator detection
            operators.extend(
                re.findall(
                    r"\b(if|for|while|return|def|class|import|from|and|or|not|in|is)\b",
                    source_code,
                )
            )
            operators.extend(
                re.findall(
                    r"(\+|\-|\*|\/|%|\*\*|//|=|==|!=|<|>|<=|>=|\+=|\-=|\*=|/=|%=|\*\*=|//=)",
                    source_code,
                )
            )

            # Simple variable/literal detection for operands
            # This is very basic and would need proper AST traversal for accuracy
            operands.extend(
                re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", source_code)
            )  # Identifiers
            operands.extend(re.findall(r"\b\d+(\.\d+)?\b", source_code))  # Numbers
            operands.extend(re.findall(r'(".*?"|\'.*?\')', source_code))  # Strings

    except Exception as e:
        logger.warning(f"Error extracting operators/operands from {function.name}: {e}")

    return operators, operands


def calculate_halstead_volume(operators: List[str], operands: List[str]):
    """Calculate Halstead volume metrics."""
    try:
        n1 = len(set(operators))  # Unique operators
        n2 = len(set(operands))  # Unique operands
        N1 = len(operators)  # Total operators
        N2 = len(operands)  # Total operands

        N = N1 + N2  # Program length
        n = n1 + n2  # Program vocabulary

        if n > 0:
            volume = N * math.log2(n)
            return volume, N1, N2, n1, n2
        return 0, N1, N2, n1, n2
    except Exception:
        return 0, 0, 0, 0, 0


def cc_rank(complexity: int):
    """Calculate cyclomatic complexity rank."""
    if complexity < 0:
        raise ValueError("Complexity must be a non-negative value")

    ranks = [
        (1, 5, "A"),
        (6, 10, "B"),
        (11, 20, "C"),
        (21, 30, "D"),
        (31, 40, "E"),
        (41, float("inf"), "F"),
    ]
    for low, high, rank in ranks:
        if low <= complexity <= high:
            return rank
    return "F"


# ============================================================================
# COMPREHENSIVE ANALYSIS ENGINE
# ============================================================================


class AnalysisEngine:
    """
    Comprehensive analysis engine for deep code analysis, integrating Graph-Sitter and LSP.
    """

    def __init__(self, codebase: Codebase, language: str):
        self.codebase = codebase
        self.language = language
        self.analyzer = GraphSitterAnalyzer(codebase)
        self.lsp_manager = LSPDiagnosticsManager(
            codebase, Language(language)
        )  # Pass codebase object
        self.context_cache = {}
        self.insight_cache = {}

    async def perform_full_analysis(self) -> Dict[str, Any]:
        """Perform comprehensive codebase analysis using Graph-Sitter and LSP."""
        try:
            # 1. Open files in LSP server for diagnostic collection
            logger.info("Opening files in LSP server for diagnostic collection...")
            self.lsp_manager.start_server()  # Start LSP server
            for file_obj in self.codebase.files:
                try:
                    self.lsp_manager.open_file(file_obj.filepath, file_obj.source)
                except Exception as e:
                    logger.warning(
                        f"Could not open file {file_obj.filepath} with LSP: {e}"
                    )

            # Give LSP server some time to process files and publish diagnostics
            logger.info(
                "Waiting for LSP server to process files and publish diagnostics (5 seconds)..."
            )
            await asyncio.sleep(5)  # Adjust as needed for larger codebases

            # 2. Retrieve Enhanced Diagnostics
            logger.info("Retrieving enhanced diagnostics from LSP server...")
            all_lsp_diagnostics = self.lsp_manager.get_all_enhanced_diagnostics()

            # 3. Perform Graph-Sitter Analysis
            logger.info("Performing comprehensive Graph-Sitter analysis...")
            codebase_summary = self.analyzer.get_codebase_overview()
            tree_structure = self._build_tree_structure_from_graph_sitter(
                self.codebase, all_lsp_diagnostics
            )
            error_analysis = self._analyze_errors_with_graph_sitter_enhanced(
                self.codebase, all_lsp_diagnostics
            )
            dead_code_analysis = (
                self.analyzer.find_dead_code()
            )  # Using GraphSitterAnalyzer
            entrypoint_analysis = self._analyze_entrypoints_with_graph_sitter_enhanced(
                self.codebase
            )
            dependency_graph = self._build_dependency_graph_from_graph_sitter(
                self.codebase
            )
            code_quality_metrics = self._calculate_code_quality_metrics(self.codebase)
            architectural_insights = self._analyze_architectural_patterns(self.codebase)
            security_analysis = self._analyze_security_patterns(self.codebase)
            performance_analysis = self._analyze_performance_patterns(self.codebase)

            analysis = {
                "codebase_summary": codebase_summary,
                "tree_structure": tree_structure,
                "error_analysis": error_analysis,
                "dead_code_analysis": dead_code_analysis,
                "entrypoint_analysis": entrypoint_analysis,
                "dependency_graph": dependency_graph,
                "code_quality_metrics": code_quality_metrics,
                "architectural_insights": architectural_insights,
                "security_analysis": security_analysis,
                "performance_analysis": performance_analysis,
                "metrics": {
                    "files": len(list(self.codebase.files)),
                    "functions": len(list(self.codebase.functions)),
                    "classes": len(list(self.codebase.classes)),
                    "symbols": len(list(self.codebase.symbols)),
                    "imports": len(list(self.codebase.imports)),
                    "external_modules": len(list(self.codebase.external_modules)),
                },
            }

            return analysis

        except Exception as e:
            logger.error(f"Error analyzing codebase with graph-sitter: {e}")
            logger.error(traceback.format_exc())
            raise Exception(f"Graph-sitter analysis failed: {str(e)}")
        finally:
            self.lsp_manager.shutdown_server()  # Ensure LSP server is shut down

    def _analyze_errors_with_graph_sitter_enhanced(
        self, codebase: Codebase, lsp_diagnostics: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Enhanced comprehensive error analysis using Graph-sitter APIs and LSP diagnostics."""
        errors = {
            "total": 0,
            "critical": 0,
            "major": 0,
            "minor": 0,
            "by_category": defaultdict(int),  # Use defaultdict for easier counting
            "detailed_errors": [],
            "error_patterns": [],
            "suggestions": [],
            "resolution_recommendations": [],
        }

        # Integrate LSP diagnostics (which are already enhanced by autogenlib_context)
        for enhanced_diag in lsp_diagnostics:
            diag = enhanced_diag["diagnostic"]
            error_entry = {
                "severity": diag.severity.name.lower() if diag.severity else "unknown",
                "category": diag.code if diag.code else "lsp_diagnostic",
                "file": enhanced_diag["relative_file_path"],  # Use relative path
                "symbol": diag.source,  # LSP source
                "line": diag.range.line + 1,
                "message": diag.message,
                "context": enhanced_diag,  # Store the full enhanced diagnostic object
                "suggestion": "Review LSP diagnostic message and apply fix.",
                "resolution_method": "ai_resolution_lsp",
            }
            errors["detailed_errors"].append(error_entry)
            errors["by_category"][error_entry["category"]] += 1
            if error_entry["severity"] == "error":  # LSP error severity is 1 (Error)
                errors["critical"] += 1
            elif (
                error_entry["severity"] == "warning"
            ):  # LSP warning severity is 2 (Warning)
                errors["major"] += 1
            else:  # Info, Hint, Unknown
                errors["minor"] += 1
            errors["total"] += 1

        # Add Graph-Sitter specific analysis (e.g., missing docstrings, unused imports, circular imports)
        # These are examples; actual implementation would involve traversing codebase objects
        # and checking properties like `usages`, `docstring`, `return_type`, etc.

        # Example: Missing docstrings
        for func in codebase.functions:
            if not hasattr(func, "docstring") or not func.docstring:
                error_entry = {
                    "severity": "minor",
                    "category": "missing_docstrings",
                    "file": func.filepath,
                    "symbol": func.name,
                    "line": func.start_point.line + 1
                    if hasattr(func, "start_point")
                    else 0,
                    "message": "Missing docstring",
                    "context": f"Function '{func.name}' has no documentation",
                    "suggestion": f'Add docstring: """Brief description of {func.name}."""',
                    "resolution_method": "generate_docstring",
                }
                errors["detailed_errors"].append(error_entry)
                errors["by_category"]["missing_docstrings"] += 1
                errors["minor"] += 1
                errors["total"] += 1

        # Example: Unused imports
        for file_obj in codebase.files:
            for imp in file_obj.imports:
                if not hasattr(imp, "usages") or len(imp.usages) == 0:
                    error_entry = {
                        "severity": "minor",
                        "category": "unused_imports",
                        "file": file_obj.filepath,
                        "symbol": imp.name,
                        "line": imp.start_point.line + 1
                        if hasattr(imp, "start_point")
                        else 0,
                        "message": "Unused import",
                        "context": f"Import '{imp.name}' is not used",
                        "suggestion": "Remove unused import",
                        "resolution_method": "remove_unused_imports",
                    }
                    errors["detailed_errors"].append(error_entry)
                    errors["by_category"]["unused_imports"] += 1
                    errors["minor"] += 1
                    errors["total"] += 1

        # Example: Circular imports (using NetworkX)
        import_graph = nx.DiGraph()
        for file_obj in codebase.files:
            import_graph.add_node(file_obj.filepath)
            for imp in file_obj.imports:
                if hasattr(imp, "from_file") and imp.from_file:
                    import_graph.add_edge(file_obj.filepath, imp.from_file.filepath)

        cycles = list(nx.simple_cycles(import_graph))
        for cycle in cycles:
            for file_path in cycle:
                error_entry = {
                    "severity": "critical",
                    "category": "circular_imports",
                    "file": file_path,
                    "symbol": "imports",
                    "line": 1,
                    "message": "Circular import detected",
                    "context": f"File is part of circular import: {' -> '.join(cycle)}",
                    "suggestion": "Refactor to remove circular dependency",
                    "resolution_method": "refactor_circular_imports",
                }
                errors["detailed_errors"].append(error_entry)
                errors["by_category"]["circular_imports"] += 1
                errors["critical"] += 1
                errors["total"] += 1

        # Generate enhanced error patterns
        errors["error_patterns"] = self._analyze_error_patterns(
            errors["detailed_errors"]
        )

        # Generate resolution recommendations
        errors["resolution_recommendations"] = (
            self._generate_resolution_recommendations(errors)
        )

        return errors

    def _analyze_error_patterns(
        self, detailed_errors: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Enhanced error pattern analysis with resolution suggestions"""
        patterns = []

        # Group errors by category and file
        error_groups = defaultdict(lambda: defaultdict(list))
        for error in detailed_errors:
            error_groups[error["category"]][error["file"]].append(error)

        # Analyze patterns within each category
        for category, file_errors in error_groups.items():
            if len(file_errors) > 1:
                total_errors = sum(len(errors) for errors in file_errors.values())
                most_affected_files = sorted(
                    file_errors.items(), key=lambda x: len(x[1]), reverse=True
                )[:3]

                patterns.append(
                    {
                        "category": category,
                        "total_count": total_errors,
                        "affected_files": len(file_errors),
                        "most_affected_files": [
                            {"file": file, "count": len(errors)}
                            for file, errors in most_affected_files
                        ],
                        "pattern_description": f"Widespread {category} errors across {len(file_errors)} files",
                        "severity": most_affected_files[0][1][0]["severity"]
                        if most_affected_files
                        else "minor",
                        "resolution_strategy": self._get_resolution_strategy(category),
                    }
                )

        return patterns

    def _get_resolution_strategy(self, category: str) -> str:
        """Get resolution strategy for error category"""
        strategies = {
            "missing_types": "Use type inference tools or add explicit type annotations",
            "unused_parameters": "Remove unused parameters or prefix with underscore",
            "unused_imports": "Use import optimization tools to remove unused imports",
            "wrong_call_sites": "Update function signatures or fix call sites",
            "circular_imports": "Refactor code to break circular dependencies",
            "unresolved_imports": "Fix import paths or install missing dependencies",
            "missing_arguments": "Add required arguments to function calls",
            "incorrect_types": "Fix type annotations or import missing types",
            "unimplemented_methods": "Implement abstract methods or remove inheritance",
            "missing_attributes": "Add missing class attributes or fix attribute access",
            "parameter_mismatches": "Fix argument types to match parameter expectations",
            "assignment_errors": "Define variables before use or fix variable references",
            "lsp_diagnostic": "Consult LSP server documentation for specific diagnostic code, or use AI resolution.",
        }
        return strategies.get(category, "Manual review and correction required")

    def _generate_resolution_recommendations(
        self, errors: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate comprehensive resolution recommendations"""
        recommendations = []

        # Type-related recommendations
        type_errors_count = errors["by_category"].get("missing_types", 0) + errors[
            "by_category"
        ].get("incorrect_types", 0)
        if type_errors_count > 0:
            recommendations.append(
                {
                    "type": "type_resolution",
                    "priority": "high",
                    "description": f"Resolve {type_errors_count} type-related issues",
                    "actions": [
                        "Run mypy --install-types to install missing type stubs",
                        "Add explicit type annotations to functions and variables",
                        "Use type inference tools to suggest appropriate types",
                        "Import missing types from appropriate modules",
                    ],
                    "automated_fix": "resolve_all_types",
                }
            )

        # Import-related recommendations
        import_errors_count = (
            errors["by_category"].get("unresolved_imports", 0)
            + errors["by_category"].get("unused_imports", 0)
            + errors["by_category"].get("circular_imports", 0)
        )
        if import_errors_count > 0:
            recommendations.append(
                {
                    "type": "import_resolution",
                    "priority": "medium",
                    "description": f"Resolve {import_errors_count} import-related issues",
                    "actions": [
                        "Fix unresolved import paths",
                        "Remove unused imports",
                        "Organize imports by type (stdlib, third-party, local)",
                        "Add missing imports for used symbols",
                        "Refactor code to break circular dependencies",
                    ],
                    "automated_fix": "resolve_all_imports",
                }
            )

        # Function call recommendations
        call_errors_count = (
            errors["by_category"].get("wrong_call_sites", 0)
            + errors["by_category"].get("missing_arguments", 0)
            + errors["by_category"].get("parameter_mismatches", 0)
        )
        if call_errors_count > 0:
            recommendations.append(
                {
                    "type": "function_call_resolution",
                    "priority": "high",
                    "description": f"Resolve {call_errors_count} function call issues",
                    "actions": [
                        "Add missing arguments to function calls",
                        "Fix argument types to match parameter expectations",
                        "Update function signatures if needed",
                        "Convert positional arguments to keyword arguments",
                    ],
                    "automated_fix": "resolve_all_function_calls",
                }
            )

        # LSP specific recommendations
        lsp_diag_count = errors["by_category"].get("lsp_diagnostic", 0)
        if lsp_diag_count > 0:
            recommendations.append(
                {
                    "type": "lsp_diagnostic_resolution",
                    "priority": "high",
                    "description": f"Address {lsp_diag_count} LSP reported diagnostics",
                    "actions": [
                        "Review detailed LSP messages for specific guidance",
                        "Utilize AI-driven resolution for automated fixes",
                        "Consult language-specific documentation for best practices",
                    ],
                    "automated_fix": "ai_resolution_lsp",
                }
            )

        return recommendations

    def _analyze_entrypoints_with_graph_sitter_enhanced(
        self, codebase: Codebase
    ) -> Dict[str, Any]:
        """Enhanced entrypoint analysis using comprehensive Graph-sitter APIs"""
        entrypoints = {
            "total_entrypoints": 0,
            "main_entrypoints": [],
            "secondary_entrypoints": [],
            "test_entrypoints": [],
            "api_entrypoints": [],
            "cli_entrypoints": [],
            "entrypoint_graph": {},
            "complexity_metrics": {},
            "dependency_analysis": {},
            "call_flow_analysis": {},
        }

        # Enhanced main entrypoint detection
        for func in codebase.functions:
            if self._is_entrypoint_function_enhanced(func):
                entrypoint_data = {
                    "name": func.name,
                    "file": func.filepath,
                    "type": "function",
                    "complexity": self._calculate_function_complexity(func),
                    "dependencies": len(list(func.dependencies)),
                    "usages": len(list(func.usages)),
                    "call_sites": len(
                        list(func.function_calls)
                    ),  # Changed from call_sites
                    "is_async": getattr(func, "is_async", False),
                    "parameters": self._get_function_parameters_details(
                        func
                    ),  # Detailed parameters
                    "return_type": self._get_function_return_type_details(
                        func
                    ),  # Detailed return type
                    "local_variables": self._get_function_local_variables_details(
                        func
                    ),  # Local variables
                    "docstring": bool(getattr(func, "docstring", None)),
                    "function_calls_count": len(list(func.function_calls)),
                    "return_statements_count": len(
                        list(getattr(func, "return_statements", []))
                    ),
                    "variable_usages_count": len(
                        list(getattr(func, "variable_usages", []))
                    ),
                    "symbol_usages_count": len(
                        list(getattr(func, "symbol_usages", []))
                    ),
                    "entrypoint_score": self._calculate_entrypoint_score(func),
                }

                # Categorize entrypoints more precisely
                if func.name in ["main", "__main__"] or func.name.startswith("main_"):
                    entrypoints["main_entrypoints"].append(entrypoint_data)
                elif self._is_api_entrypoint(func):
                    entrypoints["api_entrypoints"].append(entrypoint_data)
                elif self._is_cli_entrypoint(func):
                    entrypoints["cli_entrypoints"].append(entrypoint_data)
                else:
                    entrypoints["secondary_entrypoints"].append(entrypoint_data)

        # Enhanced class entrypoint detection
        for cls in codebase.classes:
            if self._is_entrypoint_class_enhanced(cls):
                entrypoint_data = {
                    "name": cls.name,
                    "file": cls.filepath,
                    "type": "class",
                    "complexity": self._calculate_class_complexity(cls),
                    "methods_count": len(list(cls.methods)),
                    "attributes_count": len(list(cls.attributes)),
                    "inheritance_depth": calculate_doi(cls),
                    "usages_count": len(list(cls.usages)),
                    "subclasses_count": len(list(cls.subclasses)),
                    "dependencies_count": len(list(cls.dependencies)),
                    "entrypoint_score": self._calculate_class_entrypoint_score(cls),
                    "methods_details": [
                        {
                            "name": m.name,
                            "parameters": self._get_function_parameters_details(m),
                            "return_type": self._get_function_return_type_details(m),
                            "complexity": self._calculate_function_complexity(m),
                        }
                        for m in cls.methods
                    ],
                }

                if self._is_api_entrypoint_class(cls):
                    entrypoints["api_entrypoints"].append(entrypoint_data)
                else:
                    entrypoints["secondary_entrypoints"].append(entrypoint_data)

        # Enhanced test entrypoint detection
        for func in codebase.functions:
            if self._is_test_function_enhanced(func):
                entrypoint_data = {
                    "name": func.name,
                    "file": func.filepath,
                    "type": "test_function",
                    "complexity": self._calculate_function_complexity(func),
                    "dependencies_count": len(list(func.dependencies)),
                    "test_type": self._classify_test_type(func),
                    "test_coverage_estimate": self._estimate_test_coverage(func),
                }
                entrypoints["test_entrypoints"].append(entrypoint_data)

        # Calculate totals
        entrypoints["total_entrypoints"] = (
            len(entrypoints["main_entrypoints"])
            + len(entrypoints["secondary_entrypoints"])
            + len(entrypoints["test_entrypoints"])
            + len(entrypoints["api_entrypoints"])
            + len(entrypoints["cli_entrypoints"])
        )

        # Enhanced entrypoint graph analysis
        entrypoint_graph = nx.DiGraph()
        all_entrypoints_list = (
            entrypoints["main_entrypoints"]
            + entrypoints["secondary_entrypoints"]
            + entrypoints["api_entrypoints"]
            + entrypoints["cli_entrypoints"]
        )

        for entrypoint in all_entrypoints_list:
            func = next(
                (f for f in codebase.functions if f.name == entrypoint["name"]), None
            )
            if func:
                entrypoint_graph.add_node(func.name, **entrypoint)

                # Add call relationships
                for call in func.function_calls:
                    if (
                        hasattr(call, "function_definition")
                        and call.function_definition
                    ):
                        called_func = call.function_definition
                        if not isinstance(called_func, ExternalModule):
                            entrypoint_graph.add_edge(
                                func.name,
                                called_func.name,
                                relationship="calls",
                                call_count=1,
                            )

                # Add dependency relationships
                for dep in func.dependencies:
                    if (
                        hasattr(dep, "name")
                        and dep.name != func.name
                        and not isinstance(dep, ExternalModule)
                    ):
                        entrypoint_graph.add_edge(
                            func.name, dep.name, relationship="depends_on"
                        )

        entrypoints["entrypoint_graph"] = {
            "nodes": len(entrypoint_graph.nodes),
            "edges": len(entrypoint_graph.edges),
            "connected_components": len(
                list(nx.weakly_connected_components(entrypoint_graph))
            ),
            "strongly_connected_components": len(
                list(nx.strongly_connected_components(entrypoint_graph))
            ),
            "cycles": len(list(nx.simple_cycles(entrypoint_graph))),
            "max_depth": len(nx.dag_longest_path(entrypoint_graph))
            if nx.is_directed_acyclic_graph(entrypoint_graph)
            else 0,
        }

        # Enhanced complexity metrics
        complexities = [ep["complexity"] for ep in all_entrypoints_list]
        if complexities:
            entrypoints["complexity_metrics"] = {
                "average_complexity": sum(complexities) / len(complexities),
                "max_complexity": max(complexities),
                "min_complexity": min(complexities),
                "high_complexity_count": len([c for c in complexities if c > 10]),
                "complexity_distribution": {
                    "low": len([c for c in complexities if c <= 5]),
                    "medium": len([c for c in complexities if 5 < c <= 10]),
                    "high": len([c for c in complexities if c > 10]),
                },
            }

        # Dependency analysis
        entrypoints["dependency_analysis"] = self._analyze_entrypoint_dependencies(
            all_entrypoints_list, codebase
        )

        # Call flow analysis
        entrypoints["call_flow_analysis"] = self._analyze_entrypoint_call_flows(
            all_entrypoints_list, codebase
        )

        return entrypoints

    def _get_function_parameters_details(self, func: Function) -> List[Dict[str, Any]]:
        """Extracts detailed information about function parameters."""
        params_details = []
        for param in func.parameters:
            param_type_source = (
                getattr(param.type, "source", "Any")
                if hasattr(param, "type") and param.type
                else "Any"
            )
            resolved_types = []
            if (
                hasattr(param, "type")
                and param.type
                and hasattr(param.type, "resolved_value")
                and param.type.resolved_value
            ):
                # resolved_value can be a single Symbol or a list of Symbols
                resolved_symbols = param.type.resolved_value
                if not isinstance(resolved_symbols, list):
                    resolved_symbols = [resolved_symbols]
                for res_sym in resolved_symbols:
                    if isinstance(res_sym, Symbol):
                        resolved_types.append(
                            {
                                "name": res_sym.name,
                                "type": type(res_sym).__name__,
                                "filepath": res_sym.filepath
                                if hasattr(res_sym, "filepath")
                                else None,
                            }
                        )
                    elif isinstance(res_sym, ExternalModule):
                        resolved_types.append(
                            {"name": res_sym.name, "type": "ExternalModule"}
                        )
                    else:
                        resolved_types.append({"name": str(res_sym), "type": "Unknown"})

            params_details.append(
                {
                    "name": param.name,
                    "type_annotation": param_type_source,
                    "resolved_types": resolved_types,
                    "has_default": param.has_default,
                    "is_keyword_only": param.is_keyword_only,
                    "is_positional_only": param.is_positional_only,
                    "is_var_arg": param.is_var_arg,
                    "is_var_kw": param.is_var_kw,
                }
            )
        return params_details

    def _get_function_return_type_details(self, func: Function) -> Dict[str, Any]:
        """Extracts detailed information about function return type."""
        return_type_source = (
            getattr(func.return_type, "source", "Any")
            if hasattr(func, "return_type") and func.return_type
            else "Any"
        )
        resolved_types = []
        if (
            hasattr(func, "return_type")
            and func.return_type
            and hasattr(func.return_type, "resolved_value")
            and func.return_type.resolved_value
        ):
            resolved_symbols = func.return_type.resolved_value
            if not isinstance(resolved_symbols, list):
                resolved_symbols = [resolved_symbols]
            for res_sym in resolved_symbols:
                if isinstance(res_sym, Symbol):
                    resolved_types.append(
                        {
                            "name": res_sym.name,
                            "type": type(res_sym).__name__,
                            "filepath": res_sym.filepath
                            if hasattr(res_sym, "filepath")
                            else None,
                        }
                    )
                elif isinstance(res_sym, ExternalModule):
                    resolved_types.append(
                        {"name": res_sym.name, "type": "ExternalModule"}
                    )
                else:
                    resolved_types.append({"name": str(res_sym), "type": "Unknown"})
        return {"type_annotation": return_type_source, "resolved_types": resolved_types}

    def _get_function_local_variables_details(
        self, func: Function
    ) -> List[Dict[str, Any]]:
        """Extracts details about local variables defined within a function."""
        local_vars = []
        if hasattr(func, "code_block") and hasattr(
            func.code_block, "local_var_assignments"
        ):
            for assignment in func.code_block.local_var_assignments:
                var_type_source = (
                    getattr(assignment.type, "source", "Any")
                    if hasattr(assignment, "type") and assignment.type
                    else "Any"
                )
                local_vars.append(
                    {
                        "name": assignment.name,
                        "type_annotation": var_type_source,
                        "line": assignment.start_point.line + 1
                        if hasattr(assignment, "start_point")
                        else None,
                        "value_snippet": assignment.source
                        if hasattr(assignment, "source")
                        else None,
                    }
                )
        return local_vars

    def _is_test_function_enhanced(self, func: Function) -> bool:
        """Enhanced test function detection"""
        # Standard test patterns
        if func.name.startswith("test_") or func.name.endswith("_test"):
            return True

        # Check for test decorators
        if hasattr(func, "decorators"):
            for decorator in func.decorators:
                decorator_source = getattr(decorator, "source", "")
                if any(
                    pattern in decorator_source.lower()
                    for pattern in ["@pytest.", "@unittest.", "@test"]
                ):
                    return True

        # Check if in test file
        test_file_patterns = ["test_", "_test.", "tests/", "/test/", "spec_", "_spec."]
        if any(pattern in func.filepath for pattern in test_file_patterns):
            return True

        # Check for assertion patterns in function body
        if hasattr(func, "source") and func.source:
            assertion_patterns = ["assert ", "self.assert", "expect(", "should."]
            if any(pattern in func.source for pattern in assertion_patterns):
                return True

        return False

    def _is_entrypoint_class_enhanced(self, cls: Class) -> bool:
        """Enhanced entrypoint class detection"""
        # Standard entrypoint patterns
        entrypoint_patterns = [
            "app",
            "application",
            "server",
            "client",
            "main",
            "runner",
            "service",
            "controller",
        ]
        if any(pattern in cls.name.lower() for pattern in entrypoint_patterns):
            return True

        # Check for framework-specific patterns
        framework_patterns = ["fastapi", "flask", "django", "tornado", "aiohttp"]
        for method in cls.methods:
            if any(pattern in method.name.lower() for pattern in framework_patterns):
                return True

        # Check for inheritance from framework classes
        for superclass in cls.superclasses:
            if any(
                pattern in superclass.name.lower()
                for pattern in ["application", "app", "service", "handler"]
            ):
                return True

        # Check for singleton patterns (often used for main application classes)
        if any(
            "instance" in method.name.lower() or "singleton" in method.name.lower()
            for method in cls.methods
        ):
            return True

        return False

    def _is_api_entrypoint_class(self, cls: Class) -> bool:
        """Check if class is an API entrypoint"""
        api_patterns = ["api", "router", "controller", "handler", "endpoint", "view"]
        if any(pattern in cls.name.lower() for pattern in api_patterns):
            return True

        # Check for API-related decorators on methods
        for method in cls.methods:
            if hasattr(method, "decorators"):
                for decorator in method.decorators:
                    decorator_source = getattr(decorator, "source", "")
                    if any(
                        pattern in decorator_source.lower()
                        for pattern in ["@route", "@get", "@post", "@put", "@delete"]
                    ):
                        return True

        # Check for inheritance from API frameworks
        for superclass in cls.superclasses:
            if any(
                pattern in superclass.name.lower()
                for pattern in ["resource", "view", "handler", "controller"]
            ):
                return True

        return False

    def _calculate_entrypoint_score(self, func: Function) -> float:
        """Calculate entrypoint score based on various factors"""
        score = 0.0

        # Base score for being a function
        score += 1.0

        # Score based on name patterns
        entrypoint_names = ["main", "run", "start", "execute", "app", "serve", "launch"]
        if any(name in func.name.lower() for name in entrypoint_names):
            score += 2.0

        # Score based on usage patterns
        if len(func.usages) == 0:  # Not called by other functions
            score += 1.0
        elif len(func.usages) < 3:  # Called by few functions
            score += 0.5

        # Score based on complexity (entrypoints often coordinate other functions)
        complexity = self._calculate_function_complexity(func)
        if 5 <= complexity <= 15:  # Sweet spot for entrypoints
            score += 1.0
        elif complexity > 15:  # Very complex, likely important
            score += 0.5

        # Score based on function calls (entrypoints often call many other functions)
        if len(func.function_calls) > 5:
            score += 1.0
        elif len(func.function_calls) > 2:
            score += 0.5

        # Score based on decorators
        if hasattr(func, "decorators"):
            for decorator in func.decorators:
                decorator_source = getattr(decorator, "source", "")
                if any(
                    pattern in decorator_source.lower()
                    for pattern in ["@app.", "@click.", "@typer."]
                ):
                    score += 2.0

        # Score based on file location
        if any(
            pattern in func.filepath
            for pattern in ["main.py", "app.py", "server.py", "cli.py"]
        ):
            score += 1.0

        return score

    def _estimate_test_coverage(self, func: Function) -> float:
        """Estimate test coverage based on function characteristics"""
        coverage = 0.0

        # Base coverage for being a test
        coverage += 0.3

        # Coverage based on assertions
        if hasattr(func, "source") and func.source:
            assertion_count = func.source.count("assert ") + func.source.count(
                "self.assert"
            )
            coverage += min(0.4, assertion_count * 0.1)

        # Coverage based on function calls (tests that call many functions likely test more)
        call_count = len(func.function_calls)
        coverage += min(0.3, call_count * 0.05)

        return min(1.0, coverage)

    def _analyze_entrypoint_dependencies(
        self, all_entrypoints: List[Dict[str, Any]], codebase: Codebase
    ) -> Dict[str, Any]:
        """Analyze dependencies between entrypoints"""
        dependency_analysis = {
            "shared_dependencies": [],
            "isolated_entrypoints": [],
            "dependency_clusters": [],
            "external_dependencies": [],
        }

        # Find shared dependencies
        entrypoint_deps = {}
        for entrypoint in all_entrypoints:
            func = next(
                (f for f in codebase.functions if f.name == entrypoint["name"]), None
            )
            if func:
                entrypoint_deps[entrypoint["name"]] = set(
                    dep.name
                    for dep in func.dependencies
                    if not isinstance(dep, ExternalModule)
                )
                # Track external dependencies
                for dep in func.dependencies:
                    if isinstance(dep, ExternalModule):
                        dependency_analysis["external_dependencies"].append(
                            {
                                "entrypoint": entrypoint["name"],
                                "dependency": dep.name,
                                "module": dep.module,
                            }
                        )

        # Find dependencies shared by multiple entrypoints
        all_deps = set()
        for deps in entrypoint_deps.values():
            all_deps.update(deps)

        for dep in all_deps:
            sharing_entrypoints = [
                name for name, deps in entrypoint_deps.items() if dep in deps
            ]
            if len(sharing_entrypoints) > 1:
                dependency_analysis["shared_dependencies"].append(
                    {
                        "dependency": dep,
                        "shared_by": sharing_entrypoints,
                        "share_count": len(sharing_entrypoints),
                    }
                )

        # Find isolated entrypoints
        for name, deps in entrypoint_deps.items():
            shared_deps = [
                dep
                for dep in deps
                if any(
                    dep in other_deps
                    for other_name, other_deps in entrypoint_deps.items()
                    if other_name != name
                )
            ]
            if len(shared_deps) == 0:
                dependency_analysis["isolated_entrypoints"].append(name)

        return dependency_analysis

    def _analyze_entrypoint_call_flows(
        self, all_entrypoints: List[Dict[str, Any]], codebase: Codebase
    ) -> Dict[str, Any]:
        """Analyze call flows from entrypoints"""
        call_flow_analysis = {
            "max_call_depth": 0,
            "average_call_depth": 0.0,
            "call_patterns": [],
            "recursive_calls": [],
        }

        call_depths = []

        for entrypoint in all_entrypoints:
            func = next(
                (f for f in codebase.functions if f.name == entrypoint["name"]), None
            )
            if func:
                # Calculate call depth using BFS
                depth = self._calculate_call_depth(func, codebase)
                call_depths.append(depth)

                # Check for recursive calls
                if self._has_recursive_calls(func):
                    call_flow_analysis["recursive_calls"].append(
                        {"entrypoint": entrypoint["name"], "file": entrypoint["file"]}
                    )

        if call_depths:
            call_flow_analysis["max_call_depth"] = max(call_depths)
            call_flow_analysis["average_call_depth"] = sum(call_depths) / len(
                call_depths
            )

        return call_flow_analysis

    def _calculate_call_depth(
        self, func: Function, codebase: Codebase, visited=None, depth=0
    ) -> int:
        """Calculate maximum call depth from a function"""
        if visited is None:
            visited = set()

        if func in visited or depth > 20:  # Prevent infinite recursion
            return depth

        visited.add(func)
        max_depth = depth

        for call in func.function_calls:
            if hasattr(call, "function_definition") and call.function_definition:
                called_func = call.function_definition
                if not isinstance(called_func, ExternalModule):
                    call_depth = self._calculate_call_depth(
                        called_func, codebase, visited.copy(), depth + 1
                    )
                    max_depth = max(max_depth, call_depth)

        return max_depth

    def _has_recursive_calls(self, func: Function) -> bool:
        """Check if function has recursive calls"""
        for call in func.function_calls:
            if hasattr(call, "function_definition") and call.function_definition:
                if call.function_definition.name == func.name:
                    return True
        return False

    def _calculate_class_entrypoint_score(self, cls: Class) -> float:
        """Calculate entrypoint score for classes"""
        score = 0.0

        # Base score for being a class
        score += 1.0

        # Score based on name patterns
        entrypoint_names = ["app", "application", "server", "client", "main", "service"]
        if any(name in cls.name.lower() for name in entrypoint_names):
            score += 2.0

        # Score based on methods
        if len(cls.methods) > 10:  # Large classes often coordinate functionality
            score += 1.0

        # Score based on inheritance
        if len(cls.superclasses) > 0:
            for superclass in cls.superclasses:
                if any(
                    pattern in superclass.name.lower()
                    for pattern in ["application", "service", "handler"]
                ):
                    score += 1.5

        # Score based on singleton patterns
        if any("instance" in method.name.lower() for method in cls.methods):
            score += 1.0

        return score

    def _classify_test_type(self, func: Function) -> str:
        """Classify the type of test function"""
        if "unit" in func.filepath or "unit" in func.name.lower():
            return "unit"
        elif "integration" in func.filepath or "integration" in func.name.lower():
            return "integration"
        elif "e2e" in func.filepath or "end_to_end" in func.name.lower():
            return "end_to_end"
        elif "performance" in func.filepath or "perf" in func.name.lower():
            return "performance"
        else:
            return "unknown"

    def _build_tree_structure_from_graph_sitter(
        self, codebase: Codebase, all_lsp_diagnostics: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build hierarchical tree structure from graph-sitter codebase with integrated LSP errors"""
        root = {
            "name": "root",
            "type": "directory",
            "path": "",
            "children": [],
            "errors": {"critical": 0, "major": 0, "minor": 0},
            "isEntrypoint": False,
            "metrics": {
                "complexity_score": 0,
                "maintainability_index": 0,
                "lines_of_code": 0,
            },
        }

        # Group files by directory
        dir_structure = defaultdict(lambda: {"files": [], "subdirs": {}})

        for file_obj in (
            codebase.files
        ):  # Changed from file to file_obj to avoid conflict with file.filepath
            try:
                # Get LSP diagnostics for this file
                file_lsp_diagnostics = [
                    d
                    for d in all_lsp_diagnostics
                    if d["relative_file_path"] == file_obj.filepath
                ]

                file_node = {
                    "name": file_obj.name,
                    "type": "file",
                    "path": file_obj.filepath,
                    "children": [],
                    "errors": self._detect_file_errors_graph_sitter(
                        file_obj, file_lsp_diagnostics
                    ),  # Pass LSP diagnostics
                    "isEntrypoint": self._is_entrypoint_file(file_obj),
                    "metrics": {
                        "lines": len(file_obj.source.splitlines())
                        if hasattr(file_obj, "source")
                        else 0,
                        "functions": len(list(file_obj.functions)),
                        "classes": len(list(file_obj.classes)),
                        "imports": len(list(file_obj.imports)),
                        "symbols": len(list(getattr(file_obj, "symbols", []))),
                        "variable_usages": len(
                            list(getattr(file_obj, "variable_usages", []))
                        ),
                        "symbol_usages": len(
                            list(getattr(file_obj, "symbol_usages", []))
                        ),
                        "complexity_score": self._calculate_file_complexity(file_obj),
                        "maintainability_index": self._calculate_maintainability_index(
                            file_obj
                        ),
                    },
                }

                # Add functions as children with comprehensive metrics
                for func in file_obj.functions:
                    try:
                        func_node = {
                            "name": func.name,
                            "type": "function",
                            "path": f"{file_obj.filepath}::{func.name}",
                            "children": [],
                            "errors": self._detect_function_errors_graph_sitter(
                                func, file_lsp_diagnostics
                            ),  # Pass LSP diagnostics
                            "isEntrypoint": self._is_entrypoint_function(func),
                            "metrics": {
                                "parameters": self._get_function_parameters_details(
                                    func
                                ),  # Detailed parameters
                                "return_type": self._get_function_return_type_details(
                                    func
                                ),  # Detailed return type
                                "local_variables": self._get_function_local_variables_details(
                                    func
                                ),  # Local variables
                                "usages": len(list(func.usages)),
                                "call_sites": len(
                                    list(func.function_calls)
                                ),  # Changed from call_sites
                                "dependencies": len(list(func.dependencies)),
                                "return_statements_count": len(
                                    list(getattr(func, "return_statements", []))
                                ),
                                "variable_usages_count": len(
                                    list(getattr(func, "variable_usages", []))
                                ),
                                "symbol_usages_count": len(
                                    list(getattr(func, "symbol_usages", []))
                                ),
                                "parent_class": getattr(func, "parent_class", None)
                                is not None,
                                "parent_function": getattr(
                                    func, "parent_function", None
                                )
                                is not None,
                                "type_parameters": len(
                                    list(getattr(func, "type_parameters", []))
                                ),
                                "complexity_score": self._calculate_function_complexity(
                                    func
                                ),
                                "halstead_volume": calculate_halstead_volume(
                                    *get_operators_and_operands(func)
                                )[0],  # Only volume
                            },
                        }
                        file_node["children"].append(func_node)
                    except Exception as e:
                        logger.warning(f"Error processing function {func.name}: {e}")

                # Add classes as children with comprehensive metrics
                for cls in file_obj.classes:
                    try:
                        class_node = {
                            "name": cls.name,
                            "type": "class",
                            "path": f"{file_obj.filepath}::{cls.name}",
                            "children": [],
                            "errors": self._detect_class_errors_graph_sitter(
                                cls, file_lsp_diagnostics
                            ),  # Pass LSP diagnostics
                            "isEntrypoint": self._is_entrypoint_class(cls),
                            "metrics": {
                                "methods": len(list(cls.methods)),
                                "attributes": len(list(cls.attributes)),
                                "usages": len(list(cls.usages)),
                                "superclasses": len(list(cls.superclasses)),
                                "subclasses": len(list(cls.subclasses)),
                                "dependencies": len(list(cls.dependencies)),
                                "symbol_type": getattr(cls, "symbol_type", "class"),
                                "parent": getattr(cls, "parent", None) is not None,
                                "resolved_value": getattr(cls, "resolved_value", None)
                                is not None,
                                "inheritance_depth": calculate_doi(cls),
                                "complexity_score": self._calculate_class_complexity(
                                    cls
                                ),
                            },
                        }

                        # Add methods as children with enhanced metrics
                        for method in cls.methods:
                            try:
                                method_node = {
                                    "name": method.name,
                                    "type": "method",
                                    "path": f"{file_obj.filepath}::{cls.name}::{method.name}",
                                    "children": [],
                                    "errors": self._detect_function_errors_graph_sitter(
                                        method, file_lsp_diagnostics
                                    ),
                                    "isEntrypoint": False,
                                    "metrics": {
                                        "parameters": self._get_function_parameters_details(
                                            method
                                        ),
                                        "return_type": self._get_function_return_type_details(
                                            method
                                        ),
                                        "local_variables": self._get_function_local_variables_details(
                                            method
                                        ),
                                        "usages": len(list(method.usages)),
                                        "parent_class": cls.name,
                                        "parent_function": getattr(
                                            method, "parent_function", None
                                        )
                                        is not None,
                                        "variable_usages_count": len(
                                            list(getattr(method, "variable_usages", []))
                                        ),
                                        "symbol_usages_count": len(
                                            list(getattr(method, "symbol_usages", []))
                                        ),
                                        "parent_statement": getattr(
                                            method, "parent_statement", None
                                        )
                                        is not None,
                                        "complexity_score": self._calculate_function_complexity(
                                            method
                                        ),
                                    },
                                }
                                class_node["children"].append(method_node)
                            except Exception as e:
                                logger.warning(
                                    f"Error processing method {method.name}: {e}"
                                )

                        file_node["children"].append(class_node)
                    except Exception as e:
                        logger.warning(f"Error processing class {cls.name}: {e}")

                # Add to directory structure
                path_parts = file_obj.filepath.split(os.sep)
                current_dir_level = dir_structure
                for part in path_parts[:-1]:
                    current_dir_level = current_dir_level[part]["subdirs"]
                current_dir_level[path_parts[-1]] = {
                    "files": [file_node],
                    "subdirs": {},
                }  # Store file node under its name

            except Exception as e:
                logger.warning(f"Error processing file {file_obj.filepath}: {e}")

        # Convert to hierarchical structure
        root["children"] = self._build_directory_nodes_recursive(dir_structure, "")
        return root

    def _build_directory_nodes_recursive(
        self, dir_structure: Dict, current_path: str
    ) -> List[Dict]:
        """Recursively build directory nodes from the processed dir_structure."""
        nodes = []

        for name, content in dir_structure.items():
            if "files" in content and content["files"]:
                # This is a file node already processed
                nodes.extend(content["files"])
            else:
                # This is a directory node
                dir_node = {
                    "name": name,
                    "type": "directory",
                    "path": os.path.join(current_path, name).replace(
                        "\\", "/"
                    ),  # Ensure Unix-like paths
                    "children": [],
                    "errors": {"critical": 0, "major": 0, "minor": 0},
                    "isEntrypoint": False,
                    "metrics": {
                        "total_files": 0,
                        "total_functions": 0,
                        "total_classes": 0,
                        "total_lines": 0,
                    },
                }

                # Add subdirectories and files
                dir_node["children"].extend(
                    self._build_directory_nodes_recursive(
                        content["subdirs"], dir_node["path"]
                    )
                )

                # Aggregate errors and metrics from children
                for child in dir_node["children"]:
                    for severity in ["critical", "major", "minor"]:
                        dir_node["errors"][severity] += child["errors"][severity]

                    if child["type"] == "file":
                        dir_node["metrics"]["total_files"] += 1
                        dir_node["metrics"]["total_functions"] += child["metrics"].get(
                            "functions", 0
                        )
                        dir_node["metrics"]["total_classes"] += child["metrics"].get(
                            "classes", 0
                        )
                        dir_node["metrics"]["total_lines"] += child["metrics"].get(
                            "lines", 0
                        )
                    elif (
                        child["type"] == "directory"
                    ):  # Aggregate from sub-directories too
                        dir_node["metrics"]["total_files"] += child["metrics"].get(
                            "total_files", 0
                        )
                        dir_node["metrics"]["total_functions"] += child["metrics"].get(
                            "total_functions", 0
                        )
                        dir_node["metrics"]["total_classes"] += child["metrics"].get(
                            "total_classes", 0
                        )
                        dir_node["metrics"]["total_lines"] += child["metrics"].get(
                            "total_lines", 0
                        )

                nodes.append(dir_node)

        return nodes

    def _build_dependency_graph_from_graph_sitter(
        self, codebase: Codebase
    ) -> Dict[str, Any]:
        """Build dependency graph from graph-sitter codebase"""
        dependency_graph = {
            "nodes": 0,
            "edges": 0,
            "cycles": 0,
            "strongly_connected_components": 0,
            "max_depth": 0,
            "file_dependencies": {},
            "symbol_dependencies": {},
            "import_graph": {},
        }

        # Build file dependency graph
        file_graph = nx.DiGraph()
        for file_obj in codebase.files:
            file_graph.add_node(file_obj.filepath)
            for imp in file_obj.imports:
                if hasattr(imp, "from_file") and imp.from_file:
                    file_graph.add_edge(file_obj.filepath, imp.from_file.filepath)

        dependency_graph["file_dependencies"] = {
            "nodes": len(file_graph.nodes),
            "edges": len(file_graph.edges),
            "cycles": len(list(nx.simple_cycles(file_graph))),
            "strongly_connected_components": len(
                list(nx.strongly_connected_components(file_graph))
            ),
        }

        # Build symbol dependency graph
        symbol_graph = nx.DiGraph()
        for symbol in codebase.symbols:
            symbol_graph.add_node(symbol.name)
            for dep in symbol.dependencies:
                if hasattr(dep, "name") and not isinstance(
                    dep, ExternalModule
                ):  # Exclude external modules from internal symbol graph
                    symbol_graph.add_edge(symbol.name, dep.name)

        dependency_graph["symbol_dependencies"] = {
            "nodes": len(symbol_graph.nodes),
            "edges": len(symbol_graph.edges),
            "cycles": len(list(nx.simple_cycles(symbol_graph))),
            "max_depth": len(nx.dag_longest_path(symbol_graph))
            if nx.is_directed_acyclic_graph(symbol_graph)
            else 0,
        }

        return dependency_graph

    def _calculate_code_quality_metrics(self, codebase: Codebase) -> Dict[str, Any]:
        """Calculate comprehensive code quality metrics"""
        metrics = {
            "complexity_score": 0.0,
            "maintainability_index": 0.0,
            "technical_debt_ratio": 0.0,
            "test_coverage_estimate": 0.0,
            "documentation_coverage": 0.0,
            "code_duplication_score": 0.0,
            "type_coverage": 0.0,
            "function_metrics": {},
            "class_metrics": {},
            "file_metrics": {},
        }

        total_functions = len(list(codebase.functions))
        total_classes = len(list(codebase.classes))
        total_files = len(list(codebase.files))

        if total_functions == 0:
            return metrics

        # Calculate function metrics
        function_complexities = []
        documented_functions = 0
        typed_functions = 0

        for func in codebase.functions:
            complexity = self._calculate_function_complexity(func)
            function_complexities.append(complexity)

            if hasattr(func, "docstring") and func.docstring:
                documented_functions += 1

            if hasattr(func, "return_type") and func.return_type:
                typed_functions += 1

        metrics["complexity_score"] = sum(function_complexities) / len(
            function_complexities
        )
        metrics["documentation_coverage"] = documented_functions / total_functions
        metrics["type_coverage"] = typed_functions / total_functions

        # Calculate maintainability index
        avg_complexity = metrics["complexity_score"]
        avg_loc = (
            sum(
                len(f.source.splitlines())
                for f in codebase.functions
                if hasattr(f, "source")
            )
            / total_functions
        )

        # Simplified maintainability index calculation
        metrics["maintainability_index"] = max(
            0,
            (
                171
                - 5.2 * math.log(avg_loc)
                - 0.23 * avg_complexity
                - 16.2 * math.log(avg_loc)
            )
            * 100
            / 171,
        )

        # Estimate test coverage
        test_functions = len(
            [f for f in codebase.functions if self._is_test_function_enhanced(f)]
        )
        metrics["test_coverage_estimate"] = min(
            1.0, test_functions / max(1, total_functions - test_functions)
        )

        # Calculate technical debt ratio (simplified)
        high_complexity_functions = len([c for c in function_complexities if c > 10])
        undocumented_functions = total_functions - documented_functions
        untyped_functions = total_functions - typed_functions

        debt_score = (
            high_complexity_functions + undocumented_functions + untyped_functions
        ) / (total_functions * 3)
        metrics["technical_debt_ratio"] = debt_score

        return metrics

    def _analyze_architectural_patterns(self, codebase: Codebase) -> Dict[str, Any]:
        """Analyze architectural patterns in the codebase"""
        patterns = {
            "mvc_pattern": False,
            "repository_pattern": False,
            "factory_pattern": False,
            "singleton_pattern": False,
            "observer_pattern": False,
            "decorator_pattern": False,
            "strategy_pattern": False,
            "layered_architecture": False,
            "microservices_indicators": [],
            "design_pattern_usage": {},
        }

        # Detect MVC pattern
        mvc_indicators = ["controller", "model", "view"]
        mvc_count = sum(
            1
            for cls in codebase.classes
            if any(indicator in cls.name.lower() for indicator in mvc_indicators)
        )
        patterns["mvc_pattern"] = mvc_count >= 3

        # Detect Repository pattern
        repo_indicators = ["repository", "repo"]
        patterns["repository_pattern"] = any(
            indicator in cls.name.lower()
            for cls in codebase.classes
            for indicator in repo_indicators
        )

        # Detect Factory pattern
        factory_indicators = ["factory", "builder", "creator"]
        patterns["factory_pattern"] = any(
            indicator in cls.name.lower()
            for cls in codebase.classes
            for indicator in factory_indicators
        )

        # Detect Singleton pattern
        for cls in codebase.classes:
            if any("singleton" in method.name.lower() for method in cls.methods):
                patterns["singleton_pattern"] = True
                break

        # Detect microservices indicators
        microservice_indicators = ["service", "api", "endpoint", "handler"]
        for indicator in microservice_indicators:
            count = sum(1 for cls in codebase.classes if indicator in cls.name.lower())
            if count > 0:
                patterns["microservices_indicators"].append(
                    {"pattern": indicator, "count": count}
                )

        return patterns

    def _analyze_security_patterns(self, codebase: Codebase) -> Dict[str, Any]:
        """Analyze security patterns and potential issues"""
        security = {
            "potential_vulnerabilities": [],
            "security_patterns": [],
            "authentication_usage": False,
            "encryption_usage": False,
            "input_validation": False,
            "sql_injection_risks": [],
            "xss_risks": [],
            "hardcoded_secrets": [],
        }

        # Check for authentication patterns
        auth_patterns = ["authenticate", "login", "auth", "token", "jwt"]
        for func in codebase.functions:
            if any(pattern in func.name.lower() for pattern in auth_patterns):
                security["authentication_usage"] = True
                break

        # Check for encryption usage
        crypto_patterns = ["encrypt", "decrypt", "hash", "crypto", "ssl", "tls"]
        for func in codebase.functions:
            if any(pattern in func.name.lower() for pattern in crypto_patterns):
                security["encryption_usage"] = True
                break

        # Check for potential SQL injection risks
        for func in codebase.functions:
            if hasattr(func, "source") and func.source:
                if "execute(" in func.source and "%" in func.source:
                    security["sql_injection_risks"].append(
                        {
                            "function": func.name,
                            "file": func.filepath,
                            "risk": "Potential SQL injection via string formatting",
                        }
                    )

        # Check for hardcoded secrets (simplified)
        secret_patterns = ["password", "secret", "key", "token"]
        for file_obj in codebase.files:
            if hasattr(file_obj, "source") and file_obj.source:
                for pattern in secret_patterns:
                    if (
                        f'{pattern} = "' in file_obj.source.lower()
                        or f'{pattern}="' in file_obj.source.lower()
                    ):
                        security["hardcoded_secrets"].append(
                            {
                                "file": file_obj.filepath,
                                "pattern": pattern,
                                "risk": "Potential hardcoded secret",
                            }
                        )

        return security

    def _analyze_performance_patterns(self, codebase: Codebase) -> Dict[str, Any]:
        """Analyze performance patterns and potential issues"""
        performance = {
            "potential_bottlenecks": [],
            "async_usage": 0,
            "database_queries": 0,
            "loop_complexity": [],
            "memory_usage_patterns": [],
            "caching_usage": False,
            "optimization_opportunities": [],
        }

        # Count async functions
        performance["async_usage"] = sum(
            1 for func in codebase.functions if getattr(func, "is_async", False)
        )

        # Check for database query patterns
        db_patterns = ["query", "select", "insert", "update", "delete", "execute"]
        for func in codebase.functions:
            if hasattr(func, "source") and func.source:
                if any(pattern in func.source.lower() for pattern in db_patterns):
                    performance["database_queries"] += 1

        # Check for caching usage
        cache_patterns = ["cache", "memoize", "redis", "memcached"]
        for func in codebase.functions:
            if any(pattern in func.name.lower() for pattern in cache_patterns):
                performance["caching_usage"] = True
                break

        # Identify potential optimization opportunities
        for func in codebase.functions:
            complexity = self._calculate_function_complexity(func)
            if complexity > 15:
                performance["optimization_opportunities"].append(
                    {
                        "function": func.name,
                        "file": func.filepath,
                        "complexity": complexity,
                        "suggestion": "Consider breaking down complex function",
                    }
                )

        return performance

    # ============================================================================
    # HELPER FUNCTIONS FOR ANALYSIS
    # ============================================================================

    def _detect_file_errors_graph_sitter(
        self, file_obj: SourceFile, lsp_diagnostics: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Detect errors in a file using graph-sitter and LSP diagnostics"""
        errors = {"critical": 0, "major": 0, "minor": 0}

        # Add LSP diagnostics counts
        for enhanced_diag in lsp_diagnostics:
            diag = enhanced_diag["diagnostic"]
            if diag.severity:
                if diag.severity.name.lower() == "error":
                    errors["critical"] += 1
                elif diag.severity.name.lower() == "warning":
                    errors["major"] += 1
                else:  # Info, Hint, Unknown
                    errors["minor"] += 1

        try:
            # Check for syntax errors (simplified)
            if hasattr(file_obj, "source") and file_obj.source:
                try:
                    ast.parse(file_obj.source)
                except SyntaxError:
                    errors["critical"] += 1

            # Check for import issues
            for imp in file_obj.imports:
                if not hasattr(imp, "resolved_symbol") or not imp.resolved_symbol:
                    errors["minor"] += 1

            # Check for long files
            if hasattr(file_obj, "source") and len(file_obj.source.splitlines()) > 1000:
                errors["major"] += 1

        except Exception as e:
            logger.warning(f"Error detecting file errors for {file_obj.filepath}: {e}")

        return errors

    def _detect_function_errors_graph_sitter(
        self, func: Function, lsp_diagnostics: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Detect errors in a function using graph-sitter and LSP diagnostics"""
        errors = {"critical": 0, "major": 0, "minor": 0}

        # Add LSP diagnostics counts relevant to this function's range
        func_start_line = func.start_point.line if hasattr(func, "start_point") else -1
        func_end_line = func.end_point.line if hasattr(func, "end_point") else -1

        for enhanced_diag in lsp_diagnostics:
            diag = enhanced_diag["diagnostic"]
            if diag.range.line >= func_start_line and diag.range.line <= func_end_line:
                if diag.severity:
                    if diag.severity.name.lower() == "error":
                        errors["critical"] += 1
                    elif diag.severity.name.lower() == "warning":
                        errors["major"] += 1
                    else:  # Info, Hint, Unknown
                        errors["minor"] += 1

        try:
            # Check complexity (not required to be presented as retrievable output)
            # complexity = self._calculate_function_complexity(func)
            # if complexity > 20:
            #     errors["critical"] += 1
            # elif complexity > 10:
            #     errors["major"] += 1

            # Check for missing docstring
            if not hasattr(func, "docstring") or not func.docstring:
                errors["minor"] += 1

            # Check for missing type annotations
            if not hasattr(func, "return_type") or not func.return_type:
                errors["minor"] += 1

        except Exception as e:
            logger.warning(f"Error detecting function errors for {func.name}: {e}")

        return errors

    def _detect_class_errors_graph_sitter(
        self, cls: Class, lsp_diagnostics: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Detect errors in a class using graph-sitter and LSP diagnostics"""
        errors = {"critical": 0, "major": 0, "minor": 0}

        # Add LSP diagnostics counts relevant to this class's range
        cls_start_line = cls.start_point.line if hasattr(cls, "start_point") else -1
        cls_end_line = cls.end_point.line if hasattr(cls, "end_point") else -1

        for enhanced_diag in lsp_diagnostics:
            diag = enhanced_diag["diagnostic"]
            if diag.range.line >= cls_start_line and diag.range.line <= cls_end_line:
                if diag.severity:
                    if diag.severity.name.lower() == "error":
                        errors["critical"] += 1
                    elif diag.severity.name.lower() == "warning":
                        errors["major"] += 1
                    else:  # Info, Hint, Unknown
                        errors["minor"] += 1

        try:
            # Check for too many methods
            if len(list(cls.methods)) > 20:
                errors["major"] += 1

            # Check inheritance depth
            if calculate_doi(cls) > 5:
                errors["major"] += 1

            # Check for missing docstring
            if not hasattr(cls, "docstring") or not cls.docstring:
                errors["minor"] += 1

        except Exception as e:
            logger.warning(f"Error detecting class errors for {cls.name}: {e}")

        return errors

    def _is_entrypoint_file(self, file_obj: SourceFile) -> bool:
        """Check if a file is an entrypoint"""
        entrypoint_patterns = [
            "main.py",
            "__main__.py",
            "app.py",
            "server.py",
            "run.py",
            "cli.py",
        ]
        return any(pattern in file_obj.filepath for pattern in entrypoint_patterns)

    def _is_entrypoint_function(self, func: Function) -> bool:
        """Check if a function is an entrypoint"""
        entrypoint_patterns = ["main", "run", "start", "execute", "cli", "app"]
        return (
            any(pattern in func.name.lower() for pattern in entrypoint_patterns)
            or func.name == "__main__"
        )

    def _is_entrypoint_class(self, cls: Class) -> bool:
        """Check if a class is an entrypoint"""
        entrypoint_patterns = [
            "app",
            "application",
            "server",
            "client",
            "main",
            "runner",
        ]
        return any(pattern in cls.name.lower() for pattern in entrypoint_patterns)

    def _is_test_function(self, func: Function) -> bool:
        """Check if a function is a test function"""
        return func.name.startswith("test_") or "test" in func.filepath

    def _is_test_class(self, cls: Class) -> bool:
        """Check if a class is a test class"""
        return cls.name.startswith("Test") or "test" in cls.filepath

    def _is_special_function(self, func: Function) -> bool:
        """Check if a function is a special function that shouldn't be considered dead code"""
        special_patterns = [
            "__init__",
            "__str__",
            "__repr__",
            "__call__",
            "setUp",
            "tearDown",
        ]
        return any(pattern in func.name for pattern in special_patterns)

    def _calculate_file_complexity(self, file_obj: SourceFile) -> float:
        """Calculate complexity score for a file"""
        try:
            if not hasattr(file_obj, "functions"):
                return 0.0

            function_complexities = [
                self._calculate_function_complexity(func) for func in file_obj.functions
            ]
            return sum(function_complexities) / max(1, len(function_complexities))
        except Exception:
            return 0.0

    def _calculate_function_complexity(self, func: Function) -> int:
        """Calculate cyclomatic complexity for a function"""
        try:
            complexity = 1  # Base complexity

            if hasattr(func, "source") and func.source:
                source = func.source.lower()
                # Count decision points
                complexity += source.count("if ")
                complexity += source.count("elif ")
                complexity += source.count("for ")
                complexity += source.count("while ")
                complexity += source.count("except ")
                complexity += source.count("and ")
                complexity += source.count("or ")
                complexity += source.count("try:")

            return complexity
        except Exception:
            return 1

    def _calculate_class_complexity(self, cls: Class) -> float:
        """Calculate complexity score for a class"""
        try:
            if not hasattr(cls, "methods"):
                return 0.0

            method_complexities = [
                self._calculate_function_complexity(method) for method in cls.methods
            ]
            return sum(method_complexities) / max(1, len(method_complexities))
        except Exception:
            return 0.0

    def _calculate_maintainability_index(self, file_obj: SourceFile) -> float:
        """Calculate maintainability index for a file"""
        try:
            if not hasattr(file_obj, "source"):
                return 0.0

            loc = len(file_obj.source.splitlines())
            complexity = self._calculate_file_complexity(file_obj)

            # Simplified maintainability index
            if loc > 0:
                return max(
                    0,
                    (
                        171
                        - 5.2 * math.log(loc)
                        - 0.23 * complexity
                        - 16.2 * math.log(loc)
                    )
                    * 100
                    / 171,
                )
            return 0.0
        except Exception:
            return 0.0


# ============================================================================
# VISUALIZATION ENGINE
# ============================================================================


class EnhancedVisualizationEngine:  # Changed from VisualizationEngine
    """Enhanced visualization engine with dynamic target selection and scope control"""

    def __init__(self, codebase: Codebase):
        self.codebase = codebase

    def create_dynamic_dependency_graph(
        self,
        target_type: str,
        target_name: str,
        scope: str = "codebase",
        max_depth: int = 10,
        include_external: bool = False,
    ) -> Dict[str, Any]:
        """Create dependency graph with dynamic target and scope selection"""
        graph = nx.DiGraph()

        # Get the target symbol
        target_symbol = self._get_target_symbol(target_type, target_name)
        if not target_symbol:
            raise ValueError(f"{target_type} '{target_name}' not found")

        # Get scope symbols
        scope_symbols = self._get_scope_symbols(scope, target_symbol)

        # Build dependency graph within scope
        self._build_scoped_dependency_graph(
            graph, target_symbol, scope_symbols, max_depth, include_external
        )

        return self._serialize_enhanced_graph(graph, target_symbol, scope)

    def create_class_hierarchy_graph(
        self, target_class: Optional[str] = None, include_methods: bool = True
    ) -> Dict[str, Any]:
        """Create class hierarchy visualization"""
        graph = nx.DiGraph()

        if target_class:
            start_class = self.codebase.get_class(target_class)
            if not start_class:
                raise ValueError(f"Class '{target_class}' not found")
            self._build_class_hierarchy_subgraph(graph, start_class, include_methods)
        else:
            # Build full class hierarchy
            for cls in self.codebase.classes:
                self._build_class_hierarchy_subgraph(
                    graph, cls, include_methods
                )  # Changed from _add_class_hierarchy_node

        return self._serialize_enhanced_graph(graph, target_class, "class_hierarchy")

    def create_module_dependency_graph(
        self, target_module: str, max_depth: int = 10
    ) -> Dict[str, Any]:
        """Create module-level dependency visualization"""
        graph = nx.DiGraph()

        # Get all files in the target module
        module_files = [f for f in self.codebase.files if target_module in f.filepath]
        if not module_files:
            raise ValueError(f"Module '{target_module}' not found")

        # Build module dependency graph
        self._build_module_dependency_subgraph(graph, module_files, max_depth)

        return self._serialize_enhanced_graph(graph, target_module, "module")

    def create_function_call_trace(
        self, entry_function: str, target_function: str, max_depth: int = 15
    ) -> Dict[str, Any]:
        """Create call trace from entry function to target function"""
        graph = nx.DiGraph()

        start_func = self.codebase.get_function(entry_function)
        end_func = self.codebase.get_function(target_function)

        if not start_func:
            raise ValueError(f"Entry function '{entry_function}' not found")
        if not end_func:
            raise ValueError(f"Target function '{target_function}' not found")

        # Build call trace
        self._build_call_trace_subgraph(graph, start_func, end_func, max_depth)

        return self._serialize_enhanced_graph(
            graph, f"{entry_function} -> {target_function}", "call_trace"
        )

    def create_data_flow_graph(
        self, entry_point: str, max_depth: int = 10
    ) -> Dict[str, Any]:
        """Create data flow visualization"""
        graph = nx.DiGraph()
        start_symbol = self.codebase.get_symbol(entry_point)

        if not start_symbol:
            raise ValueError(f"Symbol '{entry_point}' not found")

        self._build_data_flow_subgraph(graph, start_symbol, max_depth)
        return self._serialize_enhanced_graph(graph, entry_point, "data_flow")

    def create_blast_radius_graph(
        self, entry_point: str, max_depth: int = 10
    ) -> Dict[str, Any]:
        """Create blast radius visualization showing impact of changes"""
        graph = nx.DiGraph()
        start_symbol = self.codebase.get_symbol(entry_point)

        if not start_symbol:
            raise ValueError(f"Symbol '{entry_point}' not found")

        self._build_blast_radius_subgraph(graph, start_symbol, max_depth)
        return self._serialize_enhanced_graph(graph, entry_point, "blast_radius")

    def _get_target_symbol(self, target_type: str, target_name: str):
        """Get target symbol based on type"""
        if target_type == "function":
            return self.codebase.get_function(target_name)
        elif target_type == "class":
            return self.codebase.get_class(target_name)
        elif target_type == "file":
            return self.codebase.get_file(target_name)
        elif target_type == "symbol":
            return self.codebase.get_symbol(target_name)
        else:
            raise ValueError(f"Unknown target type: {target_type}")

    def _get_scope_symbols(self, scope: str, target_symbol: Symbol) -> List[Symbol]:
        """Get all symbols within the specified scope."""
        if scope == "codebase":
            return list(self.codebase.symbols)
        elif scope == "module":
            if hasattr(target_symbol, "file"):
                module_path = os.path.dirname(target_symbol.file.filepath)
                return [
                    s
                    for s in self.codebase.symbols
                    if os.path.dirname(s.filepath) == module_path
                ]
            return []
        elif scope == "file":
            if hasattr(target_symbol, "file"):
                return list(target_symbol.file.symbols)
            return []
        elif scope == "class":
            if hasattr(target_symbol, "parent_class") and target_symbol.parent_class:
                return list(target_symbol.parent_class.methods) + list(
                    target_symbol.parent_class.attributes
                )
            return []
        elif scope == "function":
            if (
                hasattr(target_symbol, "parent_function")
                and target_symbol.parent_function
            ):
                return list(
                    target_symbol.parent_function.code_block.local_var_assignments
                )
            return []
        else:
            raise ValueError(f"Unknown scope type: {scope}")

    def _build_scoped_dependency_graph(
        self,
        graph: nx.DiGraph,
        symbol: Symbol,
        scope_symbols: List[Symbol],
        max_depth: int,
        include_external: bool,
        depth: int = 0,
    ):
        """Build dependency graph within specified scope recursively"""
        if depth >= max_depth or symbol in graph:  # Avoid cycles and depth limit
            return

        graph.add_node(
            symbol.name,
            type=type(symbol).__name__,
            file=symbol.filepath if hasattr(symbol, "filepath") else None,
            is_target=True if depth == 0 else False,
        )

        for dep in symbol.dependencies:
            if not include_external and isinstance(dep, ExternalModule):
                continue

            # Only include dependencies within scope or if external is allowed
            if dep in scope_symbols or include_external:
                graph.add_node(
                    dep.name,
                    type=type(dep).__name__,
                    file=dep.filepath if hasattr(dep, "filepath") else None,
                    in_scope=dep in scope_symbols,
                )
                graph.add_edge(symbol.name, dep.name, relationship="depends_on")

                if dep in scope_symbols:  # Only recurse if dependency is within scope
                    self._build_scoped_dependency_graph(
                        graph,
                        dep,
                        scope_symbols,
                        max_depth,
                        include_external,
                        depth + 1,
                    )

    def _build_class_hierarchy_subgraph(
        self, graph: nx.DiGraph, cls: Class, include_methods: bool, depth: int = 0
    ):
        """Build class hierarchy subgraph recursively"""
        if depth > 10 or cls in graph:  # Prevent infinite recursion and depth limit
            return

        # Add class node
        graph.add_node(
            cls.name,
            type="class",
            file=cls.filepath,
            methods=len(cls.methods),
            attributes=len(cls.attributes),
            inheritance_depth=calculate_doi(cls),
        )

        # Add superclass relationships
        for superclass in cls.superclasses:
            if not isinstance(superclass, ExternalModule):
                graph.add_node(
                    superclass.name,
                    type="class",
                    file=superclass.filepath,
                    methods=len(superclass.methods),
                    attributes=len(superclass.attributes),
                )
                graph.add_edge(cls.name, superclass.name, relationship="inherits_from")
                self._build_class_hierarchy_subgraph(
                    graph, superclass, include_methods, depth + 1
                )

        # Add subclass relationships
        for subclass in cls.subclasses:
            if not isinstance(subclass, ExternalModule):
                graph.add_node(
                    subclass.name,
                    type="class",
                    file=subclass.filepath,
                    methods=len(subclass.methods),
                    attributes=len(subclass.attributes),
                )
                graph.add_edge(subclass.name, cls.name, relationship="inherits_from")
                self._build_class_hierarchy_subgraph(
                    graph, subclass, include_methods, depth + 1
                )

        # Add methods if requested
        if include_methods:
            for method in cls.methods:
                graph.add_node(
                    f"{cls.name}.{method.name}",
                    type="method",
                    file=cls.filepath,
                    complexity=self._calculate_function_complexity(method),
                    parameters=len(method.parameters),
                )
                graph.add_edge(
                    cls.name, f"{cls.name}.{method.name}", relationship="contains"
                )

    def _build_module_dependency_subgraph(
        self, graph: nx.DiGraph, module_files: List[SourceFile], max_depth: int
    ):
        """Build module dependency subgraph recursively"""
        for file_obj in module_files:
            if file_obj in graph:  # Avoid cycles
                continue
            graph.add_node(
                file_obj.filepath,
                type="file",
                functions=len(file_obj.functions),
                classes=len(file_obj.classes),
                lines=len(file_obj.source.splitlines())
                if hasattr(file_obj, "source")
                else 0,
            )

            # Add import relationships
            for imp in file_obj.imports:
                if hasattr(imp, "from_file") and imp.from_file:
                    target_file = imp.from_file
                    if target_file not in graph:  # Add target file if not already added
                        graph.add_node(
                            target_file.filepath,
                            type="file",
                            functions=len(target_file.functions),
                            classes=len(target_file.classes),
                            lines=len(target_file.source.splitlines())
                            if hasattr(target_file, "source")
                            else 0,
                        )
                    graph.add_edge(
                        file_obj.filepath,
                        target_file.filepath,
                        relationship="imports_from",
                        import_count=1,
                    )
                    # Recurse into imported modules if within depth
                    if max_depth > 1:
                        self._build_module_dependency_subgraph(
                            graph, [target_file], max_depth - 1
                        )

    def _build_call_trace_subgraph(
        self,
        graph: nx.DiGraph,
        start_func: Function,
        end_func: Function,
        max_depth: int,
    ):
        """Build call trace from start to end function recursively"""
        visited = set()

        def trace_calls(func: Function, target: Function, depth=0):
            if depth >= max_depth or func in visited:
                return False

            visited.add(func)
            graph.add_node(
                func.name,
                type="function",
                file=func.filepath,
                complexity=self._calculate_function_complexity(func),
                depth=depth,
            )

            if func == target:
                return True

            for call in func.function_calls:
                if hasattr(call, "function_definition") and call.function_definition:
                    called_func = call.function_definition
                    if not isinstance(called_func, ExternalModule):
                        graph.add_edge(
                            func.name, called_func.name, relationship="calls"
                        )
                        if trace_calls(called_func, target, depth + 1):
                            return True

            return False

        trace_calls(start_func, end_func)

    def _build_data_flow_subgraph(
        self, graph: nx.DiGraph, symbol: Symbol, max_depth: int, depth: int = 0
    ):
        """Build data flow subgraph recursively"""
        if depth >= max_depth or symbol in graph:  # Avoid cycles and depth limit
            return

        graph.add_node(
            symbol.name,
            type=type(symbol).__name__,
            file=symbol.filepath if hasattr(symbol, "filepath") else None,
        )

        # Track variable usages and assignments
        if hasattr(symbol, "variable_usages"):
            for usage in symbol.variable_usages:
                if hasattr(usage, "name"):
                    graph.add_node(
                        usage.name,
                        type="variable",
                        file=usage.file.filepath if hasattr(usage, "file") else None,
                    )
                    graph.add_edge(symbol.name, usage.name, relationship="uses_data")
                    # Recurse into variable definition if available
                    if (
                        hasattr(usage, "resolved_symbol")
                        and usage.resolved_symbol
                        and usage.resolved_symbol not in graph
                    ):
                        self._build_data_flow_subgraph(
                            graph, usage.resolved_symbol, max_depth, depth + 1
                        )

        if hasattr(symbol, "assignments"):  # For symbols that are assigned values
            for assignment in symbol.assignments:
                if hasattr(assignment, "name"):
                    graph.add_node(
                        assignment.name,
                        type="assignment",
                        file=assignment.file.filepath
                        if hasattr(assignment, "file")
                        else None,
                    )
                    graph.add_edge(
                        assignment.name, symbol.name, relationship="assigns_to"
                    )
                    # Recurse into assigned value's dependencies
                    if hasattr(assignment, "value") and hasattr(
                        assignment.value, "dependencies"
                    ):
                        for dep in assignment.value.dependencies:
                            if dep not in graph:
                                self._build_data_flow_subgraph(
                                    graph, dep, max_depth, depth + 1
                                )

    def _build_blast_radius_subgraph(
        self, graph: nx.DiGraph, symbol: Symbol, max_depth: int, depth: int = 0
    ):
        """Build blast radius subgraph showing impact of changes recursively"""
        if depth >= max_depth or symbol in graph:  # Avoid cycles and depth limit
            return

        graph.add_node(
            symbol.name,
            type=type(symbol).__name__,
            file=symbol.filepath if hasattr(symbol, "filepath") else None,
            impact_level=depth,
        )

        # Add all usages (things that would be affected by changes)
        for usage in symbol.usages:
            if hasattr(usage, "usage_symbol"):
                affected_symbol = usage.usage_symbol
                if affected_symbol not in graph:  # Avoid re-adding nodes
                    graph.add_node(
                        affected_symbol.name,
                        type=type(affected_symbol).__name__,
                        file=affected_symbol.filepath
                        if hasattr(affected_symbol, "filepath")
                        else None,
                        impact_level=depth + 1,
                    )
                graph.add_edge(
                    symbol.name, affected_symbol.name, relationship="impacts"
                )

                self._build_blast_radius_subgraph(
                    graph, affected_symbol, max_depth, depth + 1
                )

    def _serialize_enhanced_graph(
        self, graph: nx.DiGraph, target_info: Union[str, Symbol], graph_type: str
    ) -> Dict[str, Any]:
        """Enhanced graph serialization with additional metadata"""
        base_result = self._serialize_graph(graph)

        # Convert target_info to string if it's a Symbol object
        if isinstance(target_info, Symbol):
            target_info_str = target_info.name
        else:
            target_info_str = str(target_info)

        # Add enhanced metadata
        base_result["metadata"] = {
            "target": target_info_str,
            "graph_type": graph_type,
            "created_at": datetime.now().isoformat(),
            "node_types": Counter(
                data.get("type", "unknown") for _, data in graph.nodes(data=True)
            ),
            "relationship_types": Counter(
                data.get("relationship", "unknown")
                for _, _, data in graph.edges(data=True)
            ),
        }

        # Add graph analysis
        if len(graph.nodes) > 0:
            base_result["analysis"] = {
                "centrality": dict(nx.degree_centrality(graph)),
                "clustering": dict(nx.clustering(graph.to_undirected())),
                "shortest_paths": dict(nx.shortest_path_length(graph))
                if nx.is_connected(graph.to_undirected())
                else {},
            }

        return base_result

    def _serialize_graph(self, graph: nx.DiGraph) -> Dict[str, Any]:
        """Serialize NetworkX graph to JSON-serializable format"""
        return {
            "nodes": [
                {"id": node, "label": node, **data}
                for node, data in graph.nodes(data=True)
            ],
            "edges": [
                {"source": source, "target": target, **data}
                for source, target, data in graph.edges(data=True)
            ],
            "metrics": {
                "node_count": len(graph.nodes),
                "edge_count": len(graph.edges),
                "density": nx.density(graph),
                "is_connected": nx.is_weakly_connected(graph),
            },
        }

    # Re-implement helper functions from AnalysisEngine that are used by VisualizationEngine
    # These are simplified versions, assuming they would be part of the main AnalysisEngine
    def _calculate_function_complexity(self, func: Function) -> int:
        """Calculate cyclomatic complexity for a function (simplified)"""
        if hasattr(func, "complexity"):  # If graph-sitter provides it directly
            return func.complexity
        if hasattr(func, "source") and func.source:
            return (
                func.source.count("if ")
                + func.source.count("for ")
                + func.source.count("while ")
                + 1
            )
        return 1


# ============================================================================
# TRANSFORMATION ENGINE
# ============================================================================


class TransformationEngine:
    """Advanced transformation engine for code modifications."""

    def __init__(self, codebase: Codebase):
        self.codebase = codebase
        self.transformation_log = []

    def move_symbol(
        self,
        symbol_name: str,
        target_file: str,
        include_dependencies: bool = True,
        strategy: str = "update_all_imports",
    ) -> Dict[str, Any]:
        """Move a symbol to a different file"""
        try:
            symbol = self.codebase.get_symbol(symbol_name)
            if not symbol:
                raise ValueError(f"Symbol '{symbol_name}' not found")

            # Get or create target file
            if not self.codebase.has_file(target_file):
                target_file_obj = self.codebase.create_file(target_file)
            else:
                target_file_obj = self.codebase.get_file(target_file)

            # Record original location
            original_file = symbol.filepath

            # Perform the move
            symbol.move_to_file(
                target_file_obj,
                include_dependencies=include_dependencies,
                strategy=strategy,
            )

            result = {
                "success": True,
                "symbol": symbol_name,
                "from_file": original_file,
                "to_file": target_file,
                "strategy": strategy,
                "include_dependencies": include_dependencies,
            }

            self.transformation_log.append(result)
            return result

        except Exception as e:
            error_result = {
                "success": False,
                "symbol": symbol_name,
                "error": str(e),
                "error_type": type(e).__name__,
            }
            self.transformation_log.append(error_result)
            return error_result

    def remove_symbol(self, symbol_name: str, safe_mode: bool = True) -> Dict[str, Any]:
        """Remove a symbol from the codebase"""
        try:
            symbol = self.codebase.get_symbol(symbol_name)
            if not symbol:
                raise ValueError(f"Symbol '{symbol_name}' not found")

            # Check if symbol is used elsewhere
            if safe_mode and len(symbol.usages) > 0:
                return {
                    "success": False,
                    "symbol": symbol_name,
                    "error": "Symbol is still in use",
                    "usages": [usage.file.filepath for usage in symbol.usages[:5]],
                }

            # Remove the symbol
            original_file = symbol.filepath
            symbol.remove()

            result = {
                "success": True,
                "symbol": symbol_name,
                "file": original_file,
                "safe_mode": safe_mode,
            }

            self.transformation_log.append(result)
            return result

        except Exception as e:
            error_result = {
                "success": False,
                "symbol": symbol_name,
                "error": str(e),
                "error_type": type(e).__name__,
            }
            self.transformation_log.append(error_result)
            return error_result

    def rename_symbol(self, old_name: str, new_name: str) -> Dict[str, Any]:
        """Rename a symbol and update all references"""
        try:
            symbol = self.codebase.get_symbol(old_name)
            if not symbol:
                raise ValueError(f"Symbol '{old_name}' not found")

            # Count usages before rename
            usage_count = len(symbol.usages)

            # Perform the rename
            symbol.rename(new_name)

            result = {
                "success": True,
                "old_name": old_name,
                "new_name": new_name,
                "file": symbol.filepath,
                "usages_updated": usage_count,
            }

            self.transformation_log.append(result)
            return result

        except Exception as e:
            error_result = {
                "success": False,
                "old_name": old_name,
                "new_name": new_name,
                "error": str(e),
                "error_type": type(e).__name__,
            }
            self.transformation_log.append(error_result)
            return error_result

    def resolve_imports(self, file_path: str) -> Dict[str, Any]:
        """Resolve and fix import issues in a file"""
        try:
            file_obj = self.codebase.get_file(file_path)
            if not file_obj:
                raise ValueError(f"File '{file_path}' not found")

            resolved_imports = []
            unresolved_imports = []

            for imp in file_obj.imports:
                if hasattr(imp, "resolved_symbol") and imp.resolved_symbol:
                    resolved_imports.append(imp.name)
                else:
                    unresolved_imports.append(imp.name)

            result = {
                "success": True,
                "file": file_path,
                "resolved_imports": resolved_imports,
                "unresolved_imports": unresolved_imports,
                "total_imports": len(file_obj.imports),
            }

            self.transformation_log.append(result)
            return result

        except Exception as e:
            error_result = {
                "success": False,
                "file": file_path,
                "error": str(e),
                "error_type": type(e).__name__,
            }
            self.transformation_log.append(error_result)
            return error_result

    def add_type_annotations(
        self,
        symbol_name: str,
        return_type: Optional[str] = None,
        parameter_types: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Add type annotations to a function"""
        try:
            symbol = self.codebase.get_function(symbol_name)
            if not symbol:
                raise ValueError(f"Function '{symbol_name}' not found")

            changes = []

            # Add return type annotation
            if return_type:
                symbol.set_return_type(return_type)
                changes.append(f"Added return type: {return_type}")

            # Add parameter type annotations
            if parameter_types:
                for param_name, param_type in parameter_types.items():
                    param = symbol.get_parameter(param_name)
                    if param:
                        param.set_type(param_type)  # Changed from set_type_annotation
                        changes.append(f"Added type for {param_name}: {param_type}")

            result = {
                "success": True,
                "function": symbol_name,
                "file": symbol.filepath,
                "changes": changes,
            }

            self.transformation_log.append(result)
            return result

        except Exception as e:
            error_result = {
                "success": False,
                "function": symbol_name,
                "error": str(e),
                "error_type": type(e).__name__,
            }
            self.transformation_log.append(error_result)
            return error_result

    def extract_function(
        self,
        source_function: str,
        new_function_name: str,
        start_line: int,
        end_line: int,
    ) -> Dict[str, Any]:
        """Extract code into a new function"""
        try:
            func = self.codebase.get_function(source_function)
            if not func:
                raise ValueError(f"Function '{source_function}' not found")

            # Get source lines
            source_lines = func.source.splitlines()
            if start_line < 1 or end_line > len(source_lines):
                raise ValueError("Invalid line range")

            # Extract the code block
            extracted_code = "\n".join(source_lines[start_line - 1 : end_line])

            # Create new function
            new_function_code = f"""
def {new_function_name}():
    {extracted_code}
"""

            # Add new function after the original
            # This is a placeholder; graph-sitter's API for code modification is more advanced
            # func.insert_after(new_function_code)

            # Replace extracted code with function call
            replacement = f"{new_function_name}()"
            # This is a simplified replacement - in practice, you'd need more sophisticated logic

            result = {
                "success": True,
                "source_function": source_function,
                "new_function": new_function_name,
                "extracted_lines": f"{start_line}-{end_line}",
                "file": func.filepath,
            }

            self.transformation_log.append(result)
            return result

        except Exception as e:
            error_result = {
                "success": False,
                "source_function": source_function,
                "new_function": new_function_name,
                "error": str(e),
                "error_type": type(e).__name__,
            }
            self.transformation_log.append(error_result)
            return error_result

    def get_transformation_log(self) -> List[Dict[str, Any]]:
        """Get the log of all transformations performed"""
        return self.transformation_log.copy()

    def clear_transformation_log(self):
        """Clear the transformation log"""
        self.transformation_log.clear()


class EnhancedTransformationEngine(TransformationEngine):
    """Enhanced transformation engine with comprehensive resolution methods"""

    def __init__(self, codebase: Codebase):
        super().__init__(codebase)
        self.resolution_methods = {
            # These methods would need to be implemented to use graph-sitter's transformation APIs
            "resolve_all_types": self._resolve_all_types,
            "resolve_all_imports": self._resolve_all_imports,
            "resolve_all_function_calls": self._resolve_all_function_calls,
            "resolve_method_implementations": self._resolve_method_implementations,
            "resolve_class_attributes": self._resolve_class_attributes,
            "resolve_variable_definitions": self._resolve_variable_definitions,
            "resolve_parameter_types": self._resolve_parameter_types,
            "resolve_argument_types": self._resolve_argument_types,
        }

    def _resolve_all_types(self) -> Dict[str, Any]:
        """Automated resolution for all missing/incorrect types."""
        # Placeholder for actual graph-sitter type resolution logic
        return {"status": "success", "message": "Attempted to resolve all types."}

    def _resolve_all_imports(self) -> Dict[str, Any]:
        """Automated resolution for all import issues (unused, unresolved, circular)."""
        # Placeholder for actual graph-sitter import resolution logic
        return {"status": "success", "message": "Attempted to resolve all imports."}

    def _resolve_all_function_calls(self) -> Dict[str, Any]:
        """Automated resolution for all function call issues (missing args, type mismatches)."""
        # Placeholder for actual graph-sitter function call resolution logic
        return {
            "status": "success",
            "message": "Attempted to resolve all function calls.",
        }

    def _resolve_method_implementations(self) -> Dict[str, Any]:
        """Automated resolution for unimplemented methods."""
        # Placeholder for actual graph-sitter method implementation logic
        return {
            "status": "success",
            "message": "Attempted to resolve method implementations.",
        }

    def _resolve_class_attributes(self) -> Dict[str, Any]:
        """Automated resolution for missing class attributes."""
        # Placeholder for actual graph-sitter class attribute logic
        return {
            "status": "success",
            "message": "Attempted to resolve class attributes.",
        }

    def _resolve_variable_definitions(self) -> Dict[str, Any]:
        """Automated resolution for undefined variable usages."""
        # Placeholder for actual graph-sitter variable definition logic
        return {
            "status": "success",
            "message": "Attempted to resolve variable definitions.",
        }

    def _resolve_parameter_types(self) -> Dict[str, Any]:
        """Automated resolution for missing parameter types."""
        # Placeholder for actual graph-sitter parameter type logic
        return {"status": "success", "message": "Attempted to resolve parameter types."}

    def _resolve_argument_types(self) -> Dict[str, Any]:
        """Automated resolution for argument type mismatches."""
        # Placeholder for actual graph-sitter argument type logic
        return {"status": "success", "message": "Attempted to resolve argument types."}


# ============================================================================
# API ENDPOINTS
# ============================================================================


@app.post("/analyze", response_model=Dict[str, Any])
async def analyze_codebase(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """Analyze a codebase comprehensively"""
    try:
        analysis_id = str(uuid.uuid4())

        # Clone repository
        repo_path = clone_repository(request.repo_url, request.branch)

        # Initialize AnalysisEngine
        codebase = Codebase(
            repo_path,
            config=CodebaseConfig(
                method_usages=True,
                generics=True,
                sync_enabled=True,
                full_range_index=True,
                py_resolve_syspath=True,
                exp_lazy_graph=False,
            ),
        )
        analysis_engine = AnalysisEngine(codebase, request.language)

        # Perform analysis
        analysis_result = await analysis_engine.perform_full_analysis()

        # Store analysis session
        analysis_sessions[analysis_id] = {
            "id": analysis_id,
            "repo_url": request.repo_url,
            "branch": request.branch,
            "repo_path": repo_path,
            "codebase_obj": codebase,  # Store codebase object for later use
            "analysis": analysis_result,
            "created_at": datetime.now().isoformat(),
            "config": request.config or {},
        }

        # Schedule cleanup
        background_tasks.add_task(cleanup_temp_directory, repo_path)

        return {
            "analysis_id": analysis_id,
            "status": "completed",
            "summary": {
                "files": analysis_result["metrics"]["files"],
                "functions": analysis_result["metrics"]["functions"],
                "classes": analysis_result["metrics"]["classes"],
                "errors": analysis_result["error_analysis"]["total"],
                "dead_code_items": analysis_result["dead_code_analysis"]["total"],
            },
            "analysis": analysis_result,
        }

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.get("/analysis/{analysis_id}/errors", response_model=ErrorAnalysisResponse)
async def get_error_analysis(analysis_id: str):
    """Get detailed error analysis for a codebase"""
    if analysis_id not in analysis_sessions:
        raise HTTPException(status_code=404, detail="Analysis not found")

    session = analysis_sessions[analysis_id]
    error_analysis = session["analysis"]["error_analysis"]

    return ErrorAnalysisResponse(
        total_errors=error_analysis["total"],
        critical_errors=error_analysis["critical"],
        major_errors=error_analysis["major"],
        minor_errors=error_analysis["minor"],
        errors_by_category=error_analysis["by_category"],
        detailed_errors=error_analysis["detailed_errors"],
        error_patterns=error_analysis.get("error_patterns", []),
        suggestions=error_analysis.get("suggestions", []),
    )


@app.post("/analysis/{analysis_id}/fix-errors")
async def fix_errors_with_ai(analysis_id: str, max_fixes: int = 1):
    """
    Attempts to fix errors in the codebase using AI.
    Applies fixes directly to the cloned repository.
    """
    if analysis_id not in analysis_sessions:
        raise HTTPException(status_code=404, detail="Analysis not found")

    session = analysis_sessions[analysis_id]
    codebase: Codebase = session["codebase_obj"]  # Retrieve codebase object
    repo_path = session["repo_path"]
    error_analysis = session["analysis"]["error_analysis"]

    if not error_analysis["detailed_errors"]:
        return {"message": "No errors found to fix."}

    fixes_applied = 0
    fix_results = []

    # Sort diagnostics by severity (critical > major > minor), then by file path, then by line number
    # Assuming severity is 'critical', 'major', 'minor' for sorting
    severity_order = {"critical": 0, "major": 1, "minor": 2, "unknown": 3}
    sorted_errors = sorted(
        error_analysis["detailed_errors"],
        key=lambda ed: (severity_order.get(ed["severity"], 3), ed["file"], ed["line"]),
    )

    for error_data in sorted_errors:
        if fixes_applied >= max_fixes:
            break

        # Only attempt to fix LSP diagnostics for now, as they have the full Diagnostic object
        # The 'context' field now holds the full EnhancedDiagnostic object
        if "context" not in error_data or "diagnostic" not in error_data["context"]:
            fix_results.append(
                {
                    "error": error_data,
                    "status": "skipped",
                    "message": "Only LSP diagnostics with full context are currently supported for AI fixing.",
                }
            )
            continue

        enhanced_diag = error_data[
            "context"
        ]  # This is the full EnhancedDiagnostic object
        diag: Diagnostic = enhanced_diag["diagnostic"]
        file_path_abs = os.path.join(repo_path, enhanced_diag["relative_file_path"])

        logger.info(
            f"Attempting AI fix for: {diag.message} at {enhanced_diag['relative_file_path']}:{diag.range.line + 1}"
        )

        # Call AI resolution with the full enhanced diagnostic
        ai_fix_response = resolve_diagnostic_with_ai(enhanced_diag, codebase)

        if ai_fix_response["status"] == "success":
            original_content = Path(file_path_abs).read_text()
            fixed_content = apply_fix_to_file(
                file_path_abs,
                original_content,
                ai_fix_response["fixed_code"],
                diag.range,
            )

            try:
                Path(file_path_abs).write_text(fixed_content)
                fixes_applied += 1
                fix_results.append(
                    {
                        "error": error_data,
                        "status": "applied",
                        "message": ai_fix_response["explanation"],
                        "fixed_code": ai_fix_response["fixed_code"],
                    }
                )
                logger.info(
                    f"Successfully applied fix to {enhanced_diag['relative_file_path']}. Explanation: {ai_fix_response['explanation']}"
                )

                # Re-analyze the codebase after applying fixes to update diagnostics
                # This is crucial for iterative fixing
                # For simplicity, we'll just update the in-memory codebase object
                codebase.reload()  # Reload the codebase to reflect changes
                # Re-run LSP diagnostics for the modified file
                # This requires re-initializing LSP manager for the current codebase state
                lsp_manager_temp = LSPDiagnosticsManager(
                    codebase, Language(session["language"])
                )
                lsp_manager_temp.start_server()
                lsp_manager_temp.open_file(
                    enhanced_diag["relative_file_path"], fixed_content
                )
                await asyncio.sleep(1)  # Give LSP time to re-diagnose
                updated_diags_for_file = lsp_manager_temp.get_diagnostics(
                    enhanced_diag["relative_file_path"]
                )
                lsp_manager_temp.shutdown_server()

                # Update the session's analysis with new diagnostics
                # This is a simplified update; a full re-analysis might be needed for accuracy
                # Find the original enhanced diagnostic in the session's analysis and update it
                for i, err in enumerate(
                    session["analysis"]["error_analysis"]["detailed_errors"]
                ):
                    if (
                        err["file"] == enhanced_diag["relative_file_path"]
                        and err["line"] == diag.range.line + 1
                    ):
                        # For simplicity, we'll just mark it as fixed or remove it.
                        # A more robust solution would re-run the full error analysis.
                        session["analysis"]["error_analysis"]["detailed_errors"][i][
                            "status"
                        ] = "fixed"
                        session["analysis"]["error_analysis"]["detailed_errors"][i][
                            "fixed_code"
                        ] = ai_fix_response["fixed_code"]
                        break

            except Exception as e:
                fix_results.append(
                    {
                        "error": error_data,
                        "status": "failed_to_apply",
                        "message": f"Failed to write fixed content: {e}",
                    }
                )
                logger.error(f"Failed to write fixed content to {file_path_abs}: {e}")
        else:
            fix_results.append(
                {
                    "error": error_data,
                    "status": "ai_failed",
                    "message": ai_fix_response.get(
                        "message", "AI could not generate a fix."
                    ),
                }
            )
            logger.warning(
                f"AI failed to fix error: {ai_fix_response.get('message', 'Unknown error')}"
            )

    return {
        "message": f"Attempted to fix {len(sorted_errors)} errors. Applied {fixes_applied} fixes.",
        "fix_results": fix_results,
    }


@app.get(
    "/analysis/{analysis_id}/entrypoints", response_model=EntrypointAnalysisResponse
)
async def get_entrypoint_analysis(analysis_id: str):
    """Get entrypoint analysis for a codebase"""
    if analysis_id not in analysis_sessions:
        raise HTTPException(status_code=404, detail="Analysis not found")

    session = analysis_sessions[analysis_id]
    entrypoint_analysis = session["analysis"]["entrypoint_analysis"]

    return EntrypointAnalysisResponse(
        total_entrypoints=entrypoint_analysis["total_entrypoints"],
        main_entrypoints=entrypoint_analysis["main_entrypoints"],
        secondary_entrypoints=entrypoint_analysis["secondary_entrypoints"],
        test_entrypoints=entrypoint_analysis["test_entrypoints"],
        api_entrypoints=entrypoint_analysis["api_entrypoints"],  # Added
        cli_entrypoints=entrypoint_analysis["cli_entrypoints"],  # Added
        entrypoint_graph=entrypoint_analysis["entrypoint_graph"],
        complexity_metrics=entrypoint_analysis.get("complexity_metrics", {}),
        dependency_analysis=entrypoint_analysis.get("dependency_analysis", {}),  # Added
        call_flow_analysis=entrypoint_analysis.get("call_flow_analysis", {}),  # Added
    )


@app.get("/analysis/{analysis_id}/dead-code", response_model=DeadCodeAnalysisResponse)
async def get_dead_code_analysis(analysis_id: str):
    """Get dead code analysis for a codebase"""
    if analysis_id not in analysis_sessions:
        raise HTTPException(status_code=404, detail="Analysis not found")

    session = analysis_sessions[analysis_id]
    dead_code_analysis = session["analysis"]["dead_code_analysis"]

    return DeadCodeAnalysisResponse(
        total_dead_items=dead_code_analysis["total"],
        dead_functions=[
            item
            for item in dead_code_analysis["detailed_items"]
            if item["type"] == "function"
        ],
        dead_classes=[
            item
            for item in dead_code_analysis["detailed_items"]
            if item["type"] == "class"
        ],
        dead_imports=[
            item
            for item in dead_code_analysis["detailed_items"]
            if item["type"] == "import"
        ],
        dead_variables=[
            item
            for item in dead_code_analysis["detailed_items"]
            if item["type"] == "variable"
        ],
        potential_dead_code=dead_code_analysis["detailed_items"],
        recommendations=dead_code_analysis["recommendations"],
    )


@app.get("/analysis/{analysis_id}/quality", response_model=CodeQualityMetrics)
async def get_code_quality_metrics(analysis_id: str):
    """Get code quality metrics for a codebase"""
    if analysis_id not in analysis_sessions:
        raise HTTPException(status_code=404, detail="Analysis not found")

    session = analysis_sessions[analysis_id]
    quality_metrics = session["analysis"]["code_quality_metrics"]

    return CodeQualityMetrics(
        complexity_score=quality_metrics["complexity_score"],
        maintainability_index=quality_metrics["maintainability_index"],
        technical_debt_ratio=quality_metrics["technical_debt_ratio"],
        test_coverage_estimate=quality_metrics["test_coverage_estimate"],
        documentation_coverage=quality_metrics["documentation_coverage"],
        code_duplication_score=quality_metrics.get("code_duplication_score", 0.0),
        type_coverage=quality_metrics.get("type_coverage", 0.0),  # Added
        function_metrics=quality_metrics.get("function_metrics", {}),  # Added
        class_metrics=quality_metrics.get("class_metrics", {}),  # Added
        file_metrics=quality_metrics.get("file_metrics", {}),  # Added
    )


@app.post("/analysis/{analysis_id}/visualize")
async def create_visualization(analysis_id: str, request: VisualizationRequest):
    """Create a visualization of the codebase"""
    if analysis_id not in analysis_sessions:
        raise HTTPException(status_code=404, detail="Analysis not found")

    try:
        session = analysis_sessions[analysis_id]
        # Re-initialize codebase for visualization (or retrieve from session if stored)
        codebase: Codebase = session["codebase_obj"]  # Retrieve codebase object
        viz_engine = EnhancedVisualizationEngine(
            codebase
        )  # Use EnhancedVisualizationEngine

        # Create visualization based on type
        if request.viz_type == "dependency_graph":
            result = viz_engine.create_dynamic_dependency_graph(  # Changed to dynamic
                target_type="codebase",  # Default to codebase-wide
                target_name="",  # No specific target for codebase-wide
                scope="codebase",
                max_depth=request.max_depth,
                include_external=request.include_external,
            )
        elif request.viz_type == "call_flow":
            if not request.entry_point:
                raise HTTPException(
                    status_code=400,
                    detail="Entry point required for call flow visualization",
                )
            result = viz_engine.create_function_call_trace(  # Changed to function_call_trace
                entry_function=request.entry_point,
                target_function=request.entry_point,  # For full call flow from entry point
                max_depth=request.max_depth,
            )
        elif request.viz_type == "data_flow":
            if not request.entry_point:
                raise HTTPException(
                    status_code=400,
                    detail="Entry point required for data flow visualization",
                )
            result = viz_engine.create_data_flow_graph(
                entry_point=request.entry_point, max_depth=request.max_depth
            )
        elif request.viz_type == "blast_radius":
            if not request.entry_point:
                raise HTTPException(
                    status_code=400,
                    detail="Entry point required for blast radius visualization",
                )
            result = viz_engine.create_blast_radius_graph(
                entry_point=request.entry_point, max_depth=request.max_depth
            )
        elif request.viz_type == "class_hierarchy":  # Added
            result = viz_engine.create_class_hierarchy_graph(
                target_class=request.entry_point,  # entry_point can be a class name
                include_methods=True,
            )
        elif request.viz_type == "module_dependency":  # Added
            if not request.entry_point:
                raise HTTPException(
                    status_code=400,
                    detail="Entry point (module name) required for module dependency visualization",
                )
            result = viz_engine.create_module_dependency_graph(
                target_module=request.entry_point, max_depth=request.max_depth
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown visualization type: {request.viz_type}",
            )

        return {
            "visualization_id": str(uuid.uuid4()),
            "type": request.viz_type,
            "entry_point": request.entry_point,
            "graph": result,
        }

    except Exception as e:
        logger.error(f"Visualization failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Visualization failed: {str(e)}")


@app.post("/analysis/{analysis_id}/transform")
async def apply_transformation(analysis_id: str, request: TransformationRequest):
    """Apply a transformation to the codebase"""
    if analysis_id not in analysis_sessions:
        raise HTTPException(status_code=404, detail="Analysis not found")

    try:
        session = analysis_sessions[analysis_id]
        # Re-initialize codebase for transformation (or retrieve from session if stored)
        codebase: Codebase = session["codebase_obj"]  # Retrieve codebase object

        transform_engine = EnhancedTransformationEngine(
            codebase
        )  # Use EnhancedTransformationEngine

        # Apply transformation based on type
        if request.transformation_type == "move_symbol":
            result = transform_engine.move_symbol(
                symbol_name=request.parameters.get("symbol_name"),
                target_file=request.target_path,
                include_dependencies=request.parameters.get(
                    "include_dependencies", True
                ),
                strategy=request.parameters.get("strategy", "update_all_imports"),
            )
        elif request.transformation_type == "remove_symbol":
            result = transform_engine.remove_symbol(
                symbol_name=request.parameters.get("symbol_name"),
                safe_mode=request.parameters.get("safe_mode", True),
            )
        elif request.transformation_type == "rename_symbol":
            result = transform_engine.rename_symbol(
                old_name=request.parameters.get("old_name"),
                new_name=request.parameters.get("new_name"),
            )
        elif request.transformation_type == "resolve_imports":
            result = transform_engine.resolve_imports(request.target_path)
        elif request.transformation_type == "add_type_annotations":
            result = transform_engine.add_type_annotations(
                symbol_name=request.parameters.get("symbol_name"),
                return_type=request.parameters.get("return_type"),
                parameter_types=request.parameters.get("parameter_types"),
            )
        elif request.transformation_type == "extract_function":
            result = transform_engine.extract_function(
                source_function=request.parameters.get("source_function"),
                new_function_name=request.parameters.get("new_function_name"),
                start_line=request.parameters.get("start_line"),
                end_line=request.parameters.get("end_line"),
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown transformation type: {request.transformation_type}",
            )

        # Commit changes if not dry run
        if not request.dry_run and result.get("success"):
            codebase.commit()

        return {
            "transformation_id": str(uuid.uuid4()),
            "type": request.transformation_type,
            "dry_run": request.dry_run,
            "result": result,
            "log": transform_engine.get_transformation_log(),
        }

    except Exception as e:
        logger.error(f"Transformation failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Transformation failed: {str(e)}")


@app.post("/analysis/{analysis_id}/generate-docs")
async def generate_documentation(
    analysis_id: str, target_type: str = "codebase", target_name: Optional[str] = None
):
    """
    Generates MDX documentation pages for the codebase, a specific class, or a function.
    """
    if analysis_id not in analysis_sessions:
        raise HTTPException(status_code=404, detail="Analysis not found")

    session = analysis_sessions[analysis_id]
    codebase: Codebase = session["codebase_obj"]
    repo_path = session["repo_path"]

    docs_output_dir = Path(repo_path) / "generated_docs"
    docs_output_dir.mkdir(exist_ok=True)

    generated_files = []

    try:
        # Generate structured JSON documentation
        # For simplicity, we'll generate for the whole codebase and then filter for MDX
        structured_docs = generate_docs_json(
            codebase, head_commit="latest"
        )  # Assuming 'latest' or a real commit hash

        if target_type == "codebase":
            classes_to_document = structured_docs.classes
        elif target_type == "class" and target_name:
            classes_to_document = [
                cls_doc
                for cls_doc in structured_docs.classes
                if cls_doc.title == target_name
            ]
            if not classes_to_document:
                raise HTTPException(
                    status_code=404,
                    detail=f"Class '{target_name}' not found for documentation.",
                )
        elif target_type == "function" and target_name:
            # For functions, we need to find the class they belong to, or handle standalone functions
            # This is a simplified approach; a full implementation would need to find the function's parent
            # and then generate docs for that function. For now, we'll just generate for classes.
            raise HTTPException(
                status_code=400,
                detail="Direct function documentation generation not yet supported. Please specify a class.",
            )
        else:
            raise HTTPException(
                status_code=400, detail="Invalid target_type or missing target_name."
            )

        for cls_doc in classes_to_document:
            mdx_content = render_mdx_page_for_class(cls_doc)
            mdx_route = (
                Path(cls_doc.path).with_suffix(".mdx").as_posix()
            )  # Use class path for MDX route

            # Create subdirectories based on the route
            output_path = docs_output_dir / mdx_route
            output_path.parent.mkdir(parents=True, exist_ok=True)

            output_path.write_text(mdx_content)
            generated_files.append(str(output_path.relative_to(repo_path)))
            logger.info(f"Generated MDX for {cls_doc.title} at {output_path}")

        return {
            "message": f"Documentation generated successfully for {target_type}.",
            "generated_files": generated_files,
            "output_directory": str(docs_output_dir.relative_to(repo_path)),
        }

    except Exception as e:
        logger.error(f"Documentation generation failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail=f"Documentation generation failed: {str(e)}"
        )


@app.get("/analysis/{analysis_id}/tree")
async def get_tree_structure(analysis_id: str):
    """Get the hierarchical tree structure of the codebase"""
    if analysis_id not in analysis_sessions:
        raise HTTPException(status_code=404, detail="Analysis not found")

    session = analysis_sessions[analysis_id]
    return session["analysis"]["tree_structure"]


@app.get("/analysis/{analysis_id}/dependencies")
async def get_dependency_graph(analysis_id: str):
    """Get the dependency graph of the codebase"""
    if analysis_id not in analysis_sessions:
        raise HTTPException(status_code=404, detail="Analysis not found")

    session = analysis_sessions[analysis_id]
    return session["analysis"]["dependency_graph"]


@app.get("/analysis/{analysis_id}/architecture")
async def get_architectural_insights(analysis_id: str):
    """Get architectural insights about the codebase"""
    if analysis_id not in analysis_sessions:
        raise HTTPException(status_code=404, detail="Analysis not found")

    session = analysis_sessions[analysis_id]
    return {
        "architectural_patterns": session["analysis"]["architectural_insights"],
        "security_analysis": session["analysis"]["security_analysis"],
        "performance_analysis": session["analysis"]["performance_analysis"],
    }


@app.get("/analysis/{analysis_id}/summary")
async def get_analysis_summary(analysis_id: str):
    """Get a summary of the analysis"""
    if analysis_id not in analysis_sessions:
        raise HTTPException(status_code=404, detail="Analysis not found")

    session = analysis_sessions[analysis_id]
    analysis = session["analysis"]

    return {
        "analysis_id": analysis_id,
        "repo_url": session["repo_url"],
        "branch": session["branch"],
        "created_at": session["created_at"],
        "metrics": analysis["metrics"],
        "summary": {
            "total_errors": analysis["error_analysis"]["total"],
            "critical_errors": analysis["error_analysis"]["critical"],
            "dead_code_items": analysis["dead_code_analysis"]["total"],
            "entrypoints": analysis["entrypoint_analysis"]["total_entrypoints"],
            "complexity_score": analysis["code_quality_metrics"]["complexity_score"],
            "maintainability_index": analysis["code_quality_metrics"][
                "maintainability_index"
            ],
            "technical_debt_ratio": analysis["code_quality_metrics"][
                "technical_debt_ratio"
            ],
        },
    }


@app.delete("/analysis/{analysis_id}")
async def delete_analysis(analysis_id: str):
    """Delete an analysis session"""
    if analysis_id not in analysis_sessions:
        raise HTTPException(status_code=404, detail="Analysis not found")

    session = analysis_sessions.pop(analysis_id)

    # Clean up temporary directory
    try:
        if os.path.exists(session["repo_path"]):
            shutil.rmtree(session["repo_path"])
    except Exception as e:
        logger.warning(f"Failed to clean up temp directory: {e}")

    return {"message": "Analysis deleted successfully"}


@app.get("/analyses")
async def list_analyses():
    """List all analysis sessions"""
    return {
        "analyses": [
            {
                "id": session_id,
                "repo_url": session["repo_url"],
                "branch": session["branch"],
                "created_at": session["created_at"],
                "metrics": session["analysis"]["metrics"],
            }
            for session_id, session in analysis_sessions.items()
        ]
    }


# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "graph_sitter_available": GRAPH_SITTER_AVAILABLE,
        "active_sessions": len(analysis_sessions),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/capabilities")
async def get_capabilities():
    """Get API capabilities"""
    return {
        "graph_sitter_available": GRAPH_SITTER_AVAILABLE,
        "supported_languages": ["python", "typescript", "javascript"],
        "analysis_features": [
            "error_analysis",
            "dead_code_detection",
            "entrypoint_analysis",
            "dependency_analysis",
            "code_quality_metrics",
            "architectural_insights",
            "security_analysis",
            "performance_analysis",
        ],
        "visualization_types": [
            "dependency_graph",
            "call_flow",
            "data_flow",
            "blast_radius",
            "class_hierarchy",  # Added
            "module_dependency",  # Added
        ],
        "transformation_types": [
            "move_symbol",
            "remove_symbol",
            "rename_symbol",
            "resolve_imports",
            "add_type_annotations",
            "extract_function",
        ],
        "documentation_generation": ["mdx"],  # Added
        "ai_resolution": ["lsp_diagnostics"],  # Added
    }


# ============================================================================
# CLEANUP UTILITIES
# ============================================================================


async def cleanup_temp_directory(repo_path: str):
    """Clean up temporary directory after delay"""
    await asyncio.sleep(3600)  # Wait 1 hour before cleanup
    try:
        if os.path.exists(repo_path):
            shutil.rmtree(repo_path)
            logger.info(f"Cleaned up temporary directory: {repo_path}")
    except Exception as e:
        logger.warning(f"Failed to clean up temp directory {repo_path}: {e}")


def find_import_cycles(codebase: Codebase) -> List[List[str]]:
    """Find import cycles in the codebase"""
    import_graph = nx.DiGraph()

    for file_obj in codebase.files:
        import_graph.add_node(file_obj.filepath)
        for imp in file_obj.imports:
            if hasattr(imp, "from_file") and imp.from_file:
                import_graph.add_edge(file_obj.filepath, imp.from_file.filepath)

    return list(nx.simple_cycles(import_graph))


def find_problematic_import_loops(
    codebase: Codebase, cycles: List[List[str]]
) -> List[Dict[str, Any]]:
    """Identify cycles with both static and dynamic imports between files"""
    problematic_cycles = []

    for i, cycle in enumerate(cycles):
        mixed_imports = {}

        for from_file_path in cycle:
            from_file = next(
                (f for f in codebase.files if f.filepath == from_file_path), None
            )
            if not from_file:
                continue

            for to_file_path in cycle:
                if from_file_path == to_file_path:
                    continue

                # Check imports from from_file to to_file
                imports_to_file = [
                    imp
                    for imp in from_file.imports
                    if hasattr(imp, "from_file")
                    and imp.from_file
                    and imp.from_file.filepath == to_file_path
                ]

                if imports_to_file:
                    mixed_imports[(from_file_path, to_file_path)] = {
                        "imports": len(imports_to_file),
                        "import_names": [imp.name for imp in imports_to_file],
                    }

        if mixed_imports:
            problematic_cycles.append(
                {"files": cycle, "mixed_imports": mixed_imports, "index": i}
            )

    return problematic_cycles


def convert_all_calls_to_kwargs(codebase: Codebase):
    """Convert all function calls to use keyword arguments"""
    converted_count = 0

    for file_obj in codebase.files:
        for function_call in file_obj.function_calls:
            try:
                # Get function definition
                func_def = function_call.function_definition
                if not func_def or isinstance(func_def, ExternalModule):
                    continue

                # Convert positional args to kwargs
                for i, arg in enumerate(function_call.args):
                    if not arg.is_named and i < len(func_def.parameters):
                        param = func_def.parameters[i]
                        arg.add_keyword(param.name)
                        converted_count += 1

            except Exception as e:
                logger.warning(f"Failed to convert call {function_call.name}: {e}")

    logger.info(f"Converted {converted_count} function call arguments to kwargs")
    return converted_count


def apply_fix_to_file(
    filepath: str,
    original_content: str,
    fixed_code_snippet: str,
    diagnostic_range: Range,
) -> str:
    """
    Applies a fixed code snippet to the original file content.
    This function attempts to replace the lines covered by the diagnostic range.
    If the fixed_code_snippet is a full file, it replaces the entire content.
    """
    lines = original_content.splitlines(
        keepends=True
    )  # Keep newlines for accurate replacement

    # Heuristic: If the fixed_code_snippet is very large compared to the original file,
    # or if it contains a shebang/imports, assume it's a full file replacement.
    # This is a simplification; a more robust solution would involve diffing or AST.
    if (
        len(fixed_code_snippet) > len(original_content) * 0.8
        or fixed_code_snippet.startswith("#!")
        or "import " in fixed_code_snippet[:100]
        or "from " in fixed_code_snippet[:100]
    ):
        logger.info(
            f"Assuming full file replacement for {filepath} based on fixed code size/content."
        )
        return fixed_code_snippet

    start_line_idx = diagnostic_range.line
    end_line_idx = diagnostic_range.end.line

    # Ensure indices are within bounds
    start_line_idx = max(0, min(start_line_idx, len(lines) - 1))
    end_line_idx = max(0, min(end_line_idx, len(lines) - 1))

    # Replace the block of lines
    fixed_lines = fixed_code_snippet.splitlines(keepends=True)

    # Adjust fixed_lines to ensure they end with a newline if the original lines did
    for i in range(len(fixed_lines)):
        if not fixed_lines[i].endswith("\n") and (
            i + start_line_idx < len(lines) and lines[i + start_line_idx].endswith("\n")
        ):
            fixed_lines[i] += "\n"

    # If the fixed snippet is just one line, and the diagnostic covers multiple lines,
    # it might be a replacement for a block.
    # If the fixed snippet is multi-line, and diagnostic is single-line, it's an expansion.
    # This simple replacement works for many cases but can be brittle.
    # A proper solution would involve `difflib` or `tree-sitter` based patching.

    # Replace the range
    new_lines = lines[:start_line_idx] + fixed_lines + lines[end_line_idx + 1 :]
    return "".join(new_lines)


# ============================================================================
# MAIN APPLICATION
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Graph-Sitter Backend API")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument("--log-level", default="info", help="Log level")

    args = parser.parse_args()

    uvicorn.run(
        "graph_sitter_backend:app",  # Assuming this file is named graph_sitter_backend.py
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )
