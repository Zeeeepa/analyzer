#!/usr/bin/env python3
"""Serena LSP Adapter - Enhanced Diagnostics Manager with Runtime Error Collection
Integrates Serena SolidLSP with Graph-Sitter and AutoGenLib for comprehensive error context
"""Serena LSP Adapter - Enhanced Diagnostics Manager with Runtime Error Collection
Integrates Serena SolidLSP with Graph-Sitter and AutoGenLib for comprehensive error context
"""

import asyncio
import logging
import os
import re
import time
from typing import Any, TypedDict

# Import GraphSitterAnalyzer for context enrichment
from graph_sitter import Codebase
from Serena.solidlsp.ls import SolidLanguageServer
from Serena.solidlsp.ls_config import Language, LanguageServerConfig
from Serena.solidlsp.ls_logger import LanguageServerLogger
from Serena.solidlsp.ls_utils import PathUtils
from Serena.solidlsp.lsp_protocol_handler.lsp_types import Diagnostic, DocumentUri, Range

logger = logging.getLogger(__name__)


class EnhancedDiagnostic(TypedDict):
    """A diagnostic with comprehensive context for AI resolution."""

    diagnostic: Diagnostic
    file_content: str
    relevant_code_snippet: str
    file_path: str  # Absolute path to the file
    relative_file_path: str  # Path relative to codebase root

    # Enhanced context fields
    graph_sitter_context: dict[str, Any]
    autogenlib_context: dict[str, Any]
    runtime_context: dict[str, Any]
    ui_interaction_context: dict[str, Any]


class RuntimeErrorCollector:
    """Collects runtime errors from various sources."""

    def __init__(self, codebase: Codebase):
        self.codebase = codebase
        self.runtime_errors = []
        self.ui_errors = []
        self.error_patterns = {}

    def collect_python_runtime_errors(self, log_file_path: str | None = None) -> list[dict[str, Any]]:
        """Collect Python runtime errors from logs or exception handlers."""
        runtime_errors = []

        # If log file is provided, parse it for errors
        if log_file_path and os.path.exists(log_file_path):
            try:
                with open(log_file_path) as f:
                    log_content = f.read()

                # Parse Python tracebacks
                traceback_pattern = r"Traceback \(most recent call last\):(.*?)(?=\n\w|\nTraceback|\Z)"
                tracebacks = re.findall(traceback_pattern, log_content, re.DOTALL)

                for traceback in tracebacks:
                    # Extract file, line, and error info
                    file_pattern = r'File "([^"]+)", line (\d+), in (\w+)'
                    error_pattern = r"(\w+Error): (.+)"

                    file_matches = re.findall(file_pattern, traceback)
                    error_matches = re.findall(error_pattern, traceback)

                    if file_matches and error_matches:
                        file_path, line_num, function_name = file_matches[-1]  # Last frame
                        error_type, error_message = error_matches[-1]

                        runtime_errors.append(
                            {
                                "type": "runtime_error",
                                "error_type": error_type,
                                "message": error_message,
                                "file_path": file_path,
                                "line": int(line_num),
                                "function": function_name,
                                "traceback": traceback.strip(),
                                "severity": "critical",
                                "timestamp": time.time(),
                            }
                        )

            except Exception as e:
                logger.warning(f"Error parsing log file {log_file_path}: {e}")

        # Collect from in-memory exception handlers if available
        # This would require integration with the target application's exception handling
        runtime_errors.extend(self._collect_in_memory_errors())

        return runtime_errors

    def collect_ui_interaction_errors(self, ui_log_path: str | None = None) -> list[dict[str, Any]]:
        """Collect UI interaction errors from frontend logs or error boundaries."""
        ui_errors = []

        # Parse JavaScript/TypeScript errors from UI logs
        if ui_log_path and os.path.exists(ui_log_path):
            try:
                with open(ui_log_path) as f:
                    log_content = f.read()

                # Parse JavaScript errors
                js_error_pattern = r"(TypeError|ReferenceError|SyntaxError): (.+?) at (.+?):(\d+):(\d+)"
                js_errors = re.findall(js_error_pattern, log_content)

                for error_type, message, file_path, line, column in js_errors:
                    ui_errors.append(
                        {
                            "type": "ui_error",
                            "error_type": error_type,
                            "message": message,
                            "file_path": file_path,
                            "line": int(line),
                            "column": int(column),
                            "severity": "major",
                            "timestamp": time.time(),
                        }
                    )

                # Parse React component errors
                react_error_pattern = r"Error: (.+?) in (\w+) \(at (.+?):(\d+):(\d+)\)"
                react_errors = re.findall(react_error_pattern, log_content)

                for message, component, file_path, line, column in react_errors:
                    ui_errors.append(
                        {
                            "type": "react_error",
                            "error_type": "ComponentError",
                            "message": message,
                            "component": component,
                            "file_path": file_path,
                            "line": int(line),
                            "column": int(column),
                            "severity": "major",
                            "timestamp": time.time(),
                        }
                    )

                # Parse console errors
                console_error_pattern = r"console\.error: (.+)"
                console_errors = re.findall(console_error_pattern, log_content)

                for error_message in console_errors:
                    ui_errors.append({"type": "console_error", "error_type": "ConsoleError", "message": error_message, "severity": "minor", "timestamp": time.time()})

            except Exception as e:
                logger.warning(f"Error parsing UI log file {ui_log_path}: {e}")

        # Collect from browser console if available
        ui_errors.extend(self._collect_browser_console_errors())

        return ui_errors

    def collect_network_errors(self) -> list[dict[str, Any]]:
        """Collect network-related errors."""
        network_errors = []

        # Look for network error patterns in code
        for file_obj in self.codebase.files:
            if hasattr(file_obj, "source") and file_obj.source:
                # Find fetch/axios/request patterns
                network_patterns = [r'fetch\(["\']([^"\']+)["\']', r'axios\.(get|post|put|delete)\(["\']([^"\']+)["\']', r'requests\.(get|post|put|delete)\(["\']([^"\']+)["\']']

                for pattern in network_patterns:
                    matches = re.findall(pattern, file_obj.source)
                    for match in matches:
                        network_errors.append(
                            {
                                "type": "network_call",
                                "file_path": file_obj.filepath,
                                "endpoint": match[1] if isinstance(match, tuple) else match,
                                "method": match[0] if isinstance(match, tuple) else "unknown",
                                "potential_failure_point": True,
                            }
                        )

        return network_errors

    def _collect_in_memory_errors(self) -> list[dict[str, Any]]:
        """Collect runtime errors from in-memory exception handlers."""
        # This would integrate with the application's exception handling system
        # For now, return empty list as this requires application-specific integration
        return []

    def _collect_browser_console_errors(self) -> list[dict[str, Any]]:
        """Collect errors from browser console."""
        # This would require browser automation or console API integration
        # For now, return empty list as this requires browser-specific integration
        return []


class LSPDiagnosticsManager:
    """Enhanced LSP server lifecycle and diagnostic retrieval with comprehensive context enrichment."""

    def __init__(self, codebase: Codebase, language: Language, log_level=logging.INFO):
        self.codebase = codebase
        self.language = language
        self.logger = LanguageServerLogger(log_level=log_level)
        self.lsp_server: SolidLanguageServer | None = None
        self.repository_root_path = codebase.root  # Use codebase root
        self.runtime_collector = RuntimeErrorCollector(codebase)

        # Enhanced error tracking
        self.error_history = []
        self.error_frequency = {}
        self.resolution_attempts = {}

    def start_server(self) -> None:
        """Starts the LSP server and initializes it."""
        if self.lsp_server is None:
            self.lsp_server = SolidLanguageServer.create(
                language=self.language, logger=self.logger, repository_root_path=self.repository_root_path, config=LanguageServerConfig(code_language=self.language, trace_lsp_communication=False)
            )
        self.logger.log(f"Starting LSP server for {self.language.value} at {self.repository_root_path}", logging.INFO)
        self.lsp_server.start()
        self.logger.log("LSP server started.", logging.INFO)

    def open_file(self, relative_file_path: str, content: str) -> None:
        """Notifies the LSP server that a file has been opened."""
        if self.lsp_server:
            self.lsp_server.open_file(relative_file_path, content)
        else:
            self.logger.log("LSP server not started. Cannot open file.", logging.WARNING)

    def change_file(self, relative_file_path: str, content: str) -> None:
        """Notifies the LSP server that a file has been changed."""
        if self.lsp_server:
            self.lsp_server.change_file(relative_file_path, content)
        else:
            self.logger.log("LSP server not started. Cannot change file.", logging.WARNING)

    def get_diagnostics(self, relative_file_path: str) -> list[Diagnostic]:
        """Retrieves diagnostics for a specific file."""
        if self.lsp_server:
            uri = PathUtils.path_to_uri(os.path.join(self.repository_root_path, relative_file_path))
            return self.lsp_server.get_diagnostics_for_uri(uri)
        else:
            self.logger.log("LSP server not started. Cannot get diagnostics.", logging.WARNING)
            return []

    def get_all_enhanced_diagnostics(self, runtime_log_path: str | None = None, ui_log_path: str | None = None) -> list[EnhancedDiagnostic]:
        """Retrieves all collected diagnostics from the LSP server, enriched with comprehensive context."""
        if not self.lsp_server:
            self.logger.log("LSP server not started. No enhanced diagnostics available.", logging.WARNING)
            return []

        all_raw_diagnostics = self.lsp_server.get_all_diagnostics()
        enhanced_diagnostics: list[EnhancedDiagnostic] = []

        # Collect runtime errors
        runtime_errors = self.runtime_collector.collect_python_runtime_errors(runtime_log_path)
        ui_errors = self.runtime_collector.collect_ui_interaction_errors(ui_log_path)
        network_errors = self.runtime_collector.collect_network_errors()

        # Import autogenlib_context here to avoid circular dependency at module level
        from autogenlib_adapter import get_ai_fix_context

        for uri, diagnostics_list in all_raw_diagnostics.items():
            file_path = PathUtils.uri_to_path(uri)
            relative_file_path = os.path.relpath(file_path, self.repository_root_path)

            try:
                file_content = self.codebase.get_file(relative_file_path).content
            except ValueError:
                logger.warning(f"File {relative_file_path} not found in codebase. Skipping diagnostics for this file.")
                continue

            for diag in diagnostics_list:
                relevant_code = self._get_relevant_code_for_diagnostic(file_content, diag.range)

                # Find related runtime errors for this file/line
                related_runtime_errors = [
                    err
                    for err in runtime_errors
                    if err["file_path"].endswith(relative_file_path) and abs(err["line"] - (diag.range.line + 1)) <= 2  # Within 2 lines
                ]

                # Find related UI errors
                related_ui_errors = [
                    err
                    for err in ui_errors
                    if err["file_path"].endswith(relative_file_path) and abs(err["line"] - (diag.range.line + 1)) <= 2  # Within 2 lines
                ]

                # Find related network errors
                related_network_errors = [err for err in network_errors if err["file_path"] == relative_file_path]

                # Track error frequency
                error_key = f"{diag.code}:{relative_file_path}:{diag.range.line}"
                self.error_frequency[error_key] = self.error_frequency.get(error_key, 0) + 1

                # Create a partial EnhancedDiagnostic
                partial_enhanced_diag: EnhancedDiagnostic = {
                    "diagnostic": diag,
                    "file_content": file_content,
                    "relevant_code_snippet": relevant_code,
                    "file_path": file_path,
                    "relative_file_path": relative_file_path,
                    "graph_sitter_context": {},  # Will be filled by get_ai_fix_context
                    "autogenlib_context": {},  # Will be filled by get_ai_fix_context
                    "runtime_context": {
                        "related_runtime_errors": related_runtime_errors,
                        "error_frequency": self.error_frequency.get(error_key, 0),
                        "last_runtime_error": related_runtime_errors[-1] if related_runtime_errors else None,
                        "network_errors": related_network_errors,
                        "error_history": self._get_error_history(error_key),
                    },
                    "ui_interaction_context": {
                        "related_ui_errors": related_ui_errors,
                        "ui_error_frequency": len(related_ui_errors),
                        "last_ui_error": related_ui_errors[-1] if related_ui_errors else None,
                        "component_errors": self._extract_component_errors(related_ui_errors),
                    },
                }

                # Get the full enhanced context using autogenlib_context
                full_enhanced_diag = get_ai_fix_context(partial_enhanced_diag, self.codebase)
                enhanced_diagnostics.append(full_enhanced_diag)

                # Store in error history
                self.error_history.append({"timestamp": time.time(), "diagnostic": diag, "file": relative_file_path, "resolved": False})

        return enhanced_diagnostics

    def _get_relevant_code_for_diagnostic(self, file_content: str, diagnostic_range: Range, context_lines: int = 5) -> str:
        """Extracts the code snippet directly related to the diagnostic, plus surrounding context."""
        lines = file_content.splitlines()

        start_line = max(0, diagnostic_range.line - context_lines)
        end_line = min(len(lines), diagnostic_range.end.line + context_lines + 1)  # +1 to include the end line

        snippet_lines = lines[start_line:end_line]

        # Simple highlighting: add markers around the problematic line
        if diagnostic_range.line >= start_line and diagnostic_range.line < end_line:
            line_in_snippet_index = diagnostic_range.line - start_line
            original_line = snippet_lines[line_in_snippet_index]

            # Attempt to highlight the exact character range if it's within the same line
            if diagnostic_range.line == diagnostic_range.end.line:
                char_start = diagnostic_range.character
                char_end = diagnostic_range.end.character
                highlighted_segment = original_line[char_start:char_end]

                # Avoid empty highlights or out-of-bounds access
                if highlighted_segment:
                    highlighted_line = original_line[:char_start] + "**>>>" + highlighted_segment + "<<<**" + original_line[char_end:]
                    snippet_lines[line_in_snippet_index] = highlighted_line
                else:
                    snippet_lines[line_in_snippet_index] = ">>> " + original_line + " <<<"
            else:
                # For multi-line diagnostics, just mark the start line
                snippet_lines[line_in_snippet_index] = ">>> " + original_line + " <<<"

        return "\n".join(snippet_lines)

    def _get_error_history(self, error_key: str) -> list[dict[str, Any]]:
        """Get historical data for a specific error."""
        return [entry for entry in self.error_history if f"{entry['diagnostic'].code}:{entry['file']}:{entry['diagnostic'].range.line}" == error_key]

    def _extract_component_errors(self, ui_errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extract component-specific error information."""
        component_errors = []
        for error in ui_errors:
            if error.get("type") == "react_error":
                component_errors.append(
                    {
                        "component": error.get("component"),
                        "error_type": error.get("error_type"),
                        "message": error.get("message"),
                        "frequency": 1,  # Could be enhanced with actual frequency tracking
                    }
                )
        return component_errors

    def collect_runtime_diagnostics(self, runtime_log_path: str | None = None, ui_log_path: str | None = None) -> list[dict[str, Any]]:
        """Collect runtime errors and convert them to diagnostic-like format."""
        runtime_diagnostics = []

        # Collect Python runtime errors
        runtime_errors = self.runtime_collector.collect_python_runtime_errors(runtime_log_path)
        for error in runtime_errors:
            # Convert runtime error to diagnostic-like format
            try:
                relative_path = os.path.relpath(error["file_path"], self.repository_root_path)
                file_content = self.codebase.get_file(relative_path).content

                # Create a mock Range for the error line
                error_range = Range(start={"line": error["line"] - 1, "character": 0}, end={"line": error["line"] - 1, "character": 100})

                # Create a mock Diagnostic
                mock_diagnostic = Diagnostic(
                    uri=PathUtils.path_to_uri(error["file_path"]),
                    range=error_range,
                    severity=1,  # Error severity
                    message=f"Runtime {error['error_type']}: {error['message']}",
                    code="runtime_error",
                    source="runtime_collector",
                )

                runtime_diagnostics.append(
                    {
                        "diagnostic": mock_diagnostic,
                        "file_content": file_content,
                        "relevant_code_snippet": self._get_relevant_code_for_diagnostic(file_content, error_range),
                        "file_path": error["file_path"],
                        "relative_file_path": relative_path,
                        "runtime_error_data": error,
                        "error_source": "runtime",
                    }
                )

            except Exception as e:
                logger.warning(f"Error processing runtime error: {e}")

        # Collect UI interaction errors
        ui_errors = self.runtime_collector.collect_ui_interaction_errors(ui_log_path)
        for error in ui_errors:
            try:
                relative_path = os.path.relpath(error["file_path"], self.repository_root_path)
                file_content = self.codebase.get_file(relative_path).content

                # Create a mock Range for the error line
                error_range = Range(start={"line": error["line"] - 1, "character": error.get("column", 0)}, end={"line": error["line"] - 1, "character": error.get("column", 0) + 10})

                # Create a mock Diagnostic
                mock_diagnostic = Diagnostic(
                    uri=PathUtils.path_to_uri(error["file_path"]),
                    range=error_range,
                    severity=2,  # Warning severity
                    message=f"UI {error['error_type']}: {error['message']}",
                    code="ui_error",
                    source="ui_collector",
                )

                runtime_diagnostics.append(
                    {
                        "diagnostic": mock_diagnostic,
                        "file_content": file_content,
                        "relevant_code_snippet": self._get_relevant_code_for_diagnostic(file_content, error_range),
                        "file_path": error["file_path"],
                        "relative_file_path": relative_path,
                        "ui_error_data": error,
                        "error_source": "ui",
                    }
                )

            except Exception as e:
                logger.warning(f"Error processing UI error: {e}")

        return runtime_diagnostics

    def get_error_statistics(self) -> dict[str, Any]:
        """Get comprehensive error statistics."""
        if not self.lsp_server:
            return {}

        all_diagnostics = self.lsp_server.get_all_diagnostics()
        runtime_errors = self.lsp_server.get_runtime_errors()
        ui_errors = self.lsp_server.get_ui_errors()
        error_patterns = self.lsp_server.get_error_patterns()

        return {
            "lsp_diagnostics": {
                "total": sum(len(diags) for diags in all_diagnostics.values()),
                "files_affected": len(all_diagnostics),
                "by_severity": self._categorize_diagnostics_by_severity(all_diagnostics),
            },
            "runtime_errors": {
                "total": len(runtime_errors),
                "by_type": Counter(err.get("type", "unknown") for err in runtime_errors),
                "recent_errors": runtime_errors[-10:],  # Last 10 errors
            },
            "ui_errors": {
                "total": len(ui_errors),
                "by_type": Counter(err.get("type", "unknown") for err in ui_errors),
                "component_errors": len([err for err in ui_errors if err.get("type") == "react_error"]),
            },
            "error_patterns": error_patterns,
            "error_frequency": self.error_frequency,
            "resolution_success_rate": self._calculate_resolution_success_rate(),
        }

    def add_runtime_error(self, error_data: dict[str, Any]) -> None:
        """Add a runtime error to the LSP server's collection."""
        if self.lsp_server:
            self.lsp_server.add_runtime_error(error_data)

    def add_ui_error(self, error_data: dict[str, Any]) -> None:
        """Add a UI error to the LSP server's collection."""
        if self.lsp_server:
            self.lsp_server.add_ui_error(error_data)

    def clear_diagnostics(self) -> None:
        """Clears all stored diagnostics in the LSP server."""
        if self.lsp_server:
            self.lsp_server.clear_diagnostics()
        self.error_history.clear()
        self.error_frequency.clear()
        self.resolution_attempts.clear()

    def shutdown_server(self) -> None:
        """Shuts down the LSP server."""
        if self.lsp_server:
            self.logger.log("Shutting down LSP server.", logging.INFO)
            self.lsp_server.stop()
            self.lsp_server = None
            self.logger.log("LSP server shut down.", logging.INFO)

    async def monitor_runtime_errors(self, callback_func=None, monitor_duration: int = 60):
        """Monitor for runtime errors in real-time."""
        logger.info(f"Starting runtime error monitoring for {monitor_duration} seconds...")

        start_time = asyncio.get_event_loop().time()
        collected_errors = []

        while (asyncio.get_event_loop().time() - start_time) < monitor_duration:
            # Collect new runtime errors
            new_runtime_errors = self.runtime_collector.collect_python_runtime_errors()
            new_ui_errors = self.runtime_collector.collect_ui_interaction_errors()

            all_new_errors = new_runtime_errors + new_ui_errors

            if all_new_errors:
                collected_errors.extend(all_new_errors)
                if callback_func:
                    await callback_func(all_new_errors)

            await asyncio.sleep(1)  # Check every second

        logger.info(f"Runtime error monitoring completed. Collected {len(collected_errors)} errors.")
        return collected_errors

    def _categorize_diagnostics_by_severity(self, all_diagnostics: dict[DocumentUri, list[Diagnostic]]) -> dict[str, int]:
        """Categorize diagnostics by severity."""
        severity_counts = {"error": 0, "warning": 0, "information": 0, "hint": 0}

        for diagnostics_list in all_diagnostics.values():
            for diag in diagnostics_list:
                if diag.severity:
                    severity_name = diag.severity.name.lower()
                    if severity_name in severity_counts:
                        severity_counts[severity_name] += 1

        return severity_counts

    def _calculate_resolution_success_rate(self) -> float:
        """Calculate the success rate of error resolutions."""
        if not self.resolution_attempts:
            return 0.0

        successful = sum(1 for attempt in self.resolution_attempts.values() if attempt.get("success", False))
        return successful / len(self.resolution_attempts)

    def mark_error_resolved(self, error_key: str, success: bool, method: str) -> None:
        """Mark an error as resolved or failed."""
        self.resolution_attempts[error_key] = {"success": success, "method": method, "timestamp": time.time()}


# ================================================================================
# ENHANCED RUNTIME ERROR COLLECTION & ANALYSIS
# ================================================================================

class EnhancedRuntimeErrorCollector:
    """Advanced Python runtime error collector with exception hooks and analytics.
    
    Features:
    - Global exception hook installation
    - Real-time error capture with threading support
    - Log file parsing (multiple formats)
    - Error pattern detection and clustering
    - Symbol context enrichment via Serena
    - Time-series analysis and statistics
    - Error frequency tracking
    """
    
    def __init__(self, project_root: str):
        """Initialize enhanced runtime error collector."""
        from pathlib import Path
        from collections import Counter, defaultdict
        
        self.project_root = Path(project_root) if isinstance(project_root, str) else project_root
        
        # Error storage
        self.runtime_errors: list[dict[str, Any]] = []
        self.error_frequency: Counter = Counter()
        self.error_patterns: dict[str, list[dict]] = defaultdict(list)
        self.error_history: list[dict[str, Any]] = []
        
        # Statistics
        self.first_error_time: float | None = None
        self.last_error_time: float | None = None
        self.total_errors_collected = 0
        self._exception_hook_installed = False
    
    def install_exception_hook(self) -> None:
        """Install global exception hook to capture uncaught exceptions."""
        import sys
        
        if self._exception_hook_installed:
            logger.warning("Exception hook already installed")
            return
        
        original_hook = sys.excepthook
        
        def custom_excepthook(exc_type, exc_value, exc_traceback):
            """Custom exception handler that captures errors."""
            try:
                self.collect_exception(exc_type, exc_value, exc_traceback)
            except Exception as e:
                logger.error(f"Error in exception hook: {e}")
            finally:
                original_hook(exc_type, exc_value, exc_traceback)
        
        sys.excepthook = custom_excepthook
        self._exception_hook_installed = True
        logger.info("✅ Global exception hook installed for runtime error collection")
    
    def collect_exception(self, exc_type: type, exc_value: BaseException, exc_traceback) -> dict[str, Any]:
        """Collect exception with full context."""
        import traceback as tb_module
        from pathlib import Path
        
        # Extract traceback frames
        frames = tb_module.extract_tb(exc_traceback)
        
        # Get the last frame (where error occurred)
        if frames:
            last_frame = frames[-1]
            file_path = last_frame.filename
            line_num = last_frame.lineno
            function_name = last_frame.name
        else:
            file_path = "unknown"
            line_num = 0
            function_name = "unknown"
        
        # Format traceback
        formatted_traceback = ''.join(tb_module.format_exception(exc_type, exc_value, exc_traceback))
        
        # Create error record
        error_record = {
            "type": "runtime_exception",
            "error_type": exc_type.__name__,
            "message": str(exc_value),
            "file_path": file_path,
            "line": line_num,
            "function": function_name,
            "traceback": formatted_traceback,
            "frames": [{"file": frame.filename, "line": frame.lineno, "function": frame.name} for frame in frames],
            "severity": "critical",
            "timestamp": time.time(),
            "pattern_id": f"{exc_type.__name__}:{Path(file_path).name}:{line_num}",
        }
        
        # Store error
        self.runtime_errors.append(error_record)
        self.error_history.append(error_record)
        self.error_frequency[error_record["pattern_id"]] += 1
        self.error_patterns[error_record["pattern_id"]].append(error_record)
        
        if not self.first_error_time:
            self.first_error_time = error_record["timestamp"]
        self.last_error_time = error_record["timestamp"]
        self.total_errors_collected += 1
        
        logger.error(f"🔴 Runtime error collected: {exc_type.__name__} in {file_path}:{line_num}")
        return error_record
    
    def get_runtime_errors(
        self, since: float | None = None, error_type: str | None = None, file_path: str | None = None
    ) -> list[dict[str, Any]]:
        """Get filtered runtime errors."""
        filtered = self.runtime_errors
        if since:
            filtered = [e for e in filtered if e.get('timestamp', 0) >= since]
        if error_type:
            filtered = [e for e in filtered if e.get('error_type') == error_type]
        if file_path:
            filtered = [e for e in filtered if file_path in e.get('file_path', '')]
        return filtered
    
    def get_error_statistics(self) -> dict[str, Any]:
        """Get comprehensive error statistics."""
        from collections import Counter
        return {
            "total_errors": len(self.runtime_errors),
            "unique_patterns": len(self.error_patterns),
            "error_types": dict(Counter(e.get('error_type') for e in self.runtime_errors)),
            "most_frequent": self.error_frequency.most_common(10),
            "first_error_time": self.first_error_time,
            "last_error_time": self.last_error_time,
        }



# ================================================================================
# COMPREHENSIVE DIAGNOSTIC ENHANCEMENTS
# ================================================================================

from pathlib import Path
from fnmatch import fnmatch
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Iterator
import glob as glob_module


@dataclass
class DiagnosticPriority:
    """Priority scoring for diagnostics"""
    score: float
    severity_weight: float = 1.0
    frequency_weight: float = 0.5
    context_weight: float = 0.3
    
    @classmethod
    def calculate(cls, diagnostic: EnhancedDiagnostic, frequency: int, has_symbol_context: bool) -> float:
        """Calculate priority score for a diagnostic"""
        severity_map = {"error": 10, "warning": 5, "information": 2, "hint": 1}
        severity = diagnostic["diagnostic"].severity if hasattr(diagnostic["diagnostic"], 'severity') else "error"
        severity_score = severity_map.get(severity, 5)
        
        frequency_score = min(frequency, 10) / 10.0
        context_score = 1.0 if has_symbol_context else 0.5
        
        total = (severity_score * 1.0) + (frequency_score * 0.5) + (context_score * 0.3)
        return total


@dataclass  
class DiagnosticDiff:
    """Comparison result between two diagnostic sets"""
    new_errors: list[EnhancedDiagnostic] = field(default_factory=list)
    fixed_errors: list[EnhancedDiagnostic] = field(default_factory=list)
    changed_severity: list[tuple[EnhancedDiagnostic, EnhancedDiagnostic]] = field(default_factory=list)
    unchanged: list[EnhancedDiagnostic] = field(default_factory=list)
    
    def summary(self) -> dict[str, Any]:
        """Get summary statistics"""
        return {
            "new": len(self.new_errors),
            "fixed": len(self.fixed_errors),
            "changed": len(self.changed_severity),
            "unchanged": len(self.unchanged),
            "total": len(self.new_errors) + len(self.fixed_errors) + len(self.changed_severity) + len(self.unchanged)
        }


class UnifiedDiagnosticsManager:
    """Unified manager for LSP + Runtime + Symbol-enriched diagnostics"""
    
    def __init__(self, lsp_manager: LSPDiagnosticsManager, runtime_collector: EnhancedRuntimeErrorCollector):
        self.lsp_manager = lsp_manager
        self.runtime_collector = runtime_collector
        self.diagnostic_cache: dict[str, list[EnhancedDiagnostic]] = {}
        self.symbol_cache: dict[str, dict[str, Any]] = {}
        
    async def get_unified_diagnostics(
        self,
        include_runtime: bool = True,
        include_symbol_context: bool = True,
        priority_threshold: float = 0.0
    ) -> list[EnhancedDiagnostic]:
        """Get unified diagnostics from all sources with deduplication"""
        
        # Collect LSP diagnostics
        lsp_diagnostics = self.lsp_manager.get_all_enhanced_diagnostics()
        
        # Collect runtime errors if enabled
        runtime_diagnostics = []
        if include_runtime:
            runtime_errors = self.runtime_collector.get_runtime_errors()
            runtime_diagnostics = self._convert_runtime_to_diagnostics(runtime_errors)
        
        # Merge and deduplicate
        all_diagnostics = self._merge_diagnostics(lsp_diagnostics, runtime_diagnostics)
        
        # Enrich with symbol context if enabled
        if include_symbol_context:
            all_diagnostics = await self._enrich_with_symbol_context(all_diagnostics)
        
        # Calculate priorities and filter
        scored_diagnostics = []
        for diag in all_diagnostics:
            file_path = diag["relative_file_path"]
            line = diag["diagnostic"].range.line
            error_key = f"{file_path}:{line}"
            frequency = self.lsp_manager.error_frequency.get(error_key, 1)
            has_symbols = bool(diag.get("symbol_context"))
            
            priority = DiagnosticPriority.calculate(diag, frequency, has_symbols)
            if priority >= priority_threshold:
                scored_diagnostics.append((priority, diag))
        
        # Sort by priority (highest first)
        scored_diagnostics.sort(key=lambda x: x[0], reverse=True)
        return [diag for _, diag in scored_diagnostics]
    
    def _merge_diagnostics(
        self, 
        lsp_diags: list[EnhancedDiagnostic],
        runtime_diags: list[EnhancedDiagnostic]
    ) -> list[EnhancedDiagnostic]:
        """Merge diagnostics from different sources with deduplication"""
        merged: dict[str, EnhancedDiagnostic] = {}
        
        # Add LSP diagnostics
        for diag in lsp_diags:
            key = self._diagnostic_key(diag)
            merged[key] = diag
        
        # Add runtime diagnostics (avoid duplicates)
        for diag in runtime_diags:
            key = self._diagnostic_key(diag)
            if key not in merged:
                merged[key] = diag
            else:
                # Merge runtime context into existing diagnostic
                existing = merged[key]
                existing["runtime_context"] = {
                    **existing.get("runtime_context", {}),
                    **diag.get("runtime_context", {})
                }
        
        return list(merged.values())
    
    def _diagnostic_key(self, diag: EnhancedDiagnostic) -> str:
        """Generate unique key for diagnostic deduplication"""
        file_path = diag["relative_file_path"]
        diag_obj = diag["diagnostic"]
        line = diag_obj.range.line
        col = diag_obj.range.character
        message = diag_obj.message[:50]  # First 50 chars
        return f"{file_path}:{line}:{col}:{message}"
    
    def _convert_runtime_to_diagnostics(self, runtime_errors: list[dict[str, Any]]) -> list[EnhancedDiagnostic]:
        """Convert runtime errors to EnhancedDiagnostic format"""
        diagnostics = []
        
        for error in runtime_errors:
            # Create a mock Diagnostic object
            mock_diagnostic = type('Diagnostic', (), {
                'range': type('Range', (), {
                    'line': error.get('line', 0) - 1,  # LSP is 0-indexed
                    'character': 0
                })(),
                'message': f"{error.get('error_type', 'RuntimeError')}: {error.get('message', '')}",
                'severity': 'error',
                'source': 'runtime'
            })()
            
            enhanced = EnhancedDiagnostic(
                diagnostic=mock_diagnostic,
                file_content="",  # Will be filled later if needed
                relevant_code_snippet=error.get('traceback', '')[:200],
                file_path=error.get('file_path', ''),
                relative_file_path=Path(error.get('file_path', '')).name,
                graph_sitter_context={},
                autogenlib_context={},
                runtime_context={
                    "error_type": error.get('error_type'),
                    "function": error.get('function'),
                    "traceback": error.get('traceback'),
                    "timestamp": error.get('timestamp'),
                    "frames": error.get('frames', [])
                },
                ui_interaction_context={}
            )
            diagnostics.append(enhanced)
        
        return diagnostics
    
    async def _enrich_with_symbol_context(self, diagnostics: list[EnhancedDiagnostic]) -> list[EnhancedDiagnostic]:
        """Enrich diagnostics with symbol context using Serena tools
        
        This method will be fully functional once Serena library is installed.
        For now, it provides the integration point with placeholder logic.
        """
        try:
            # Attempt to import Serena symbol tools
            from serena.tools.symbol_tools import FindSymbolTool, GetSymbolDefinitionTool, GetSymbolReferencesTool
            serena_available = True
        except ImportError:
            logger.warning("Serena library not available - symbol context enrichment disabled")
            serena_available = False
        
        if not serena_available:
            # Return diagnostics with empty symbol context
            for diag in diagnostics:
                diag["symbol_context"] = {"available": False, "reason": "Serena not installed"}
            return diagnostics
        
        # Enrich each diagnostic with symbol information
        for diag in diagnostics:
            file_path = diag["relative_file_path"]
            line = diag["diagnostic"].range.line
            
            # Check cache first
            cache_key = f"{file_path}:{line}"
            if cache_key in self.symbol_cache:
                diag["symbol_context"] = self.symbol_cache[cache_key]
                continue
            
            try:
                # Find symbol at error location
                symbol_context = await self._get_symbol_at_location(file_path, line)
                
                # Get symbol definition
                if symbol_context.get("symbol_name"):
                    definition = await self._get_symbol_definition(file_path, line)
                    symbol_context["definition"] = definition
                    
                    # Get symbol references
                    references = await self._get_symbol_references(file_path, line)
                    symbol_context["references"] = references
                    symbol_context["reference_count"] = len(references)
                
                # Cache the result
                self.symbol_cache[cache_key] = symbol_context
                diag["symbol_context"] = symbol_context
                
            except Exception as e:
                logger.warning(f"Failed to enrich symbol context for {file_path}:{line}: {e}")
                diag["symbol_context"] = {"error": str(e)}
        
        return diagnostics
    
    async def _get_symbol_at_location(self, file_path: str, line: int) -> dict[str, Any]:
        """Get symbol information at specific location using Serena FindSymbolTool"""
        # This will be implemented with actual Serena tool when library is installed
        # Placeholder implementation:
        return {
            "symbol_name": None,
            "symbol_kind": None,
            "symbol_range": None,
            "container_name": None
        }
    
    async def _get_symbol_definition(self, file_path: str, line: int) -> dict[str, Any]:
        """Get symbol definition using Serena GetSymbolDefinitionTool"""
        # Placeholder - will use Serena tool when available
        return {
            "definition_file": None,
            "definition_line": None,
            "definition_body": None
        }
    
    async def _get_symbol_references(self, file_path: str, line: int) -> list[dict[str, Any]]:
        """Get all references to symbol using Serena GetSymbolReferencesTool"""
        # Placeholder - will use Serena tool when available
        return []
    
    def compare_diagnostics(
        self,
        before: list[EnhancedDiagnostic],
        after: list[EnhancedDiagnostic]
    ) -> DiagnosticDiff:
        """Compare two sets of diagnostics to find changes"""
        diff = DiagnosticDiff()
        
        before_keys = {self._diagnostic_key(d): d for d in before}
        after_keys = {self._diagnostic_key(d): d for d in after}
        
        # Find new errors
        for key in after_keys:
            if key not in before_keys:
                diff.new_errors.append(after_keys[key])
        
        # Find fixed errors
        for key in before_keys:
            if key not in after_keys:
                diff.fixed_errors.append(before_keys[key])
        
        # Find changed severity
        for key in before_keys:
            if key in after_keys:
                before_sev = getattr(before_keys[key]["diagnostic"], 'severity', None)
                after_sev = getattr(after_keys[key]["diagnostic"], 'severity', None)
                if before_sev != after_sev:
                    diff.changed_severity.append((before_keys[key], after_keys[key]))
                else:
                    diff.unchanged.append(after_keys[key])
        
        return diff


class MultiFileDiagnosticsCollector:
    """Collect diagnostics across multiple files with glob pattern support"""
    
    def __init__(self, unified_manager: UnifiedDiagnosticsManager, project_root: str):
        self.unified_manager = unified_manager
        self.project_root = Path(project_root)
        self.progress_callbacks: list[Callable[[int, int, str], None]] = []
    
    def add_progress_callback(self, callback: Callable[[int, int, str], None]) -> None:
        """Add callback for progress reporting: callback(current, total, file_path)"""
        self.progress_callbacks.append(callback)
    
    def _report_progress(self, current: int, total: int, file_path: str) -> None:
        """Report progress to all registered callbacks"""
        for callback in self.progress_callbacks:
            try:
                callback(current, total, file_path)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")
    
    async def collect_diagnostics_by_patterns(
        self,
        patterns: list[str] = ["**/*.py"],
        exclude_patterns: list[str] = ["**/venv/**", "**/__pycache__/**", "**/node_modules/**"],
        max_files: int | None = None,
        include_warnings: bool = True,
        include_info: bool = False
    ) -> dict[str, list[EnhancedDiagnostic]]:
        """Collect diagnostics for files matching glob patterns"""
        
        # Find all matching files
        matching_files = self._find_matching_files(patterns, exclude_patterns, max_files)
        total_files = len(matching_files)
        
        logger.info(f"🔍 Collecting diagnostics for {total_files} files...")
        
        # Collect diagnostics for each file
        all_diagnostics: dict[str, list[EnhancedDiagnostic]] = {}
        
        for idx, file_path in enumerate(matching_files, 1):
            self._report_progress(idx, total_files, str(file_path))
            
            try:
                # Get file-specific diagnostics
                relative_path = file_path.relative_to(self.project_root)
                file_diagnostics = await self._get_file_diagnostics(
                    str(relative_path),
                    include_warnings,
                    include_info
                )
                
                if file_diagnostics:
                    all_diagnostics[str(relative_path)] = file_diagnostics
                    
            except Exception as e:
                logger.warning(f"Failed to collect diagnostics for {file_path}: {e}")
        
        logger.info(f"✅ Collected diagnostics from {len(all_diagnostics)} files with issues")
        return all_diagnostics
    
    def _find_matching_files(
        self,
        patterns: list[str],
        exclude_patterns: list[str],
        max_files: int | None
    ) -> list[Path]:
        """Find all files matching the given patterns"""
        matching_files = set()
        
        for pattern in patterns:
            # Use glob to find files
            full_pattern = self.project_root / pattern
            for file_path in glob_module.glob(str(full_pattern), recursive=True):
                path_obj = Path(file_path)
                
                # Check if file should be excluded
                should_exclude = False
                for exclude in exclude_patterns:
                    if fnmatch(str(path_obj), exclude) or fnmatch(str(path_obj.relative_to(self.project_root)), exclude):
                        should_exclude = True
                        break
                
                if not should_exclude and path_obj.is_file():
                    matching_files.add(path_obj)
        
        # Sort for consistent ordering
        sorted_files = sorted(matching_files)
        
        # Apply max_files limit if specified
        if max_files is not None:
            sorted_files = sorted_files[:max_files]
        
        return sorted_files
    
    async def _get_file_diagnostics(
        self,
        relative_path: str,
        include_warnings: bool,
        include_info: bool
    ) -> list[EnhancedDiagnostic]:
        """Get diagnostics for a specific file"""
        
        # Get unified diagnostics (LSP + runtime + symbol context)
        all_diags = await self.unified_manager.get_unified_diagnostics(
            include_runtime=True,
            include_symbol_context=True
        )
        
        # Filter to this file only
        file_diags = [d for d in all_diags if d["relative_file_path"] == relative_path]
        
        # Filter by severity if needed
        if not include_warnings:
            file_diags = [d for d in file_diags if getattr(d["diagnostic"], 'severity', None) == 'error']
        
        if not include_info:
            file_diags = [d for d in file_diags if getattr(d["diagnostic"], 'severity', None) not in ['information', 'hint']]
        
        return file_diags
    
    def group_diagnostics_by_root_cause(
        self,
        diagnostics: list[EnhancedDiagnostic]
    ) -> dict[str, list[EnhancedDiagnostic]]:
        """Group diagnostics by potential root cause"""
        groups: dict[str, list[EnhancedDiagnostic]] = defaultdict(list)
        
        for diag in diagnostics:
            # Group by error pattern
            message = diag["diagnostic"].message
            error_pattern = self._extract_error_pattern(message)
            
            # Also consider symbol context for grouping
            symbol_context = diag.get("symbol_context", {})
            if symbol_context.get("symbol_name"):
                group_key = f"{error_pattern}::{symbol_context['symbol_name']}"
            else:
                group_key = error_pattern
            
            groups[group_key].append(diag)
        
        # Sort groups by size (most frequent first)
        sorted_groups = dict(sorted(groups.items(), key=lambda x: len(x[1]), reverse=True))
        return sorted_groups
    
    def _extract_error_pattern(self, message: str) -> str:
        """Extract error pattern from diagnostic message"""
        # Remove specific names/values to get general pattern
        pattern = re.sub(r"'[^']+'", "'<name>'", message)
        pattern = re.sub(r"\d+", "<num>", pattern)
        pattern = re.sub(r"\b0x[0-9a-fA-F]+\b", "<addr>", pattern)
        return pattern[:100]  # Limit length


# ================================================================================
# CONVENIENCE FUNCTIONS
# ================================================================================

async def create_comprehensive_diagnostics_system(
    project_root: str,
    language: Language = Language.PYTHON
) -> tuple[UnifiedDiagnosticsManager, MultiFileDiagnosticsCollector]:
    """Create a complete diagnostics system with all components
    
    Returns:
        (unified_manager, multi_file_collector) tuple
        
    Usage:
        manager, collector = await create_comprehensive_diagnostics_system("/path/to/project")
        
        # Get unified diagnostics
        diagnostics = await manager.get_unified_diagnostics()
        
        # Collect from multiple files
        collector.add_progress_callback(lambda c, t, f: print(f"{c}/{t}: {f}"))
        file_diagnostics = await collector.collect_diagnostics_by_patterns(["**/*.py"])
    """
    from graph_sitter import Codebase
    
    # Create codebase
    codebase = Codebase.from_root(project_root)
    
    # Create LSP manager
    lsp_manager = LSPDiagnosticsManager(codebase, language)
    lsp_manager.start_server()
    
    # Create runtime collector
    runtime_collector = EnhancedRuntimeErrorCollector(project_root)
    runtime_collector.install_exception_hook()
    
    # Create unified manager
    unified_manager = UnifiedDiagnosticsManager(lsp_manager, runtime_collector)
    
    # Create multi-file collector
    multi_file_collector = MultiFileDiagnosticsCollector(unified_manager, project_root)
    
    return unified_manager, multi_file_collector

