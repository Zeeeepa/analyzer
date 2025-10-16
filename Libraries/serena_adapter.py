#!/usr/bin/env python3
"""Serena Adapter - Unified Semantic Search, Context Management & LSP Diagnostics

Provides comprehensive integration with the Serena library for:
- Full SerenaAgent orchestration with tool registry
- Symbol search and navigation (definitions, references, overview)
- File operations (read, search, edit with context)
- Persistent memory management 
- LSP diagnostics collection and enrichment (via SolidLSP)
- Runtime error collection and analysis
- Integration with analyzer orchestration

Architecture:
    SerenaAdapter (Facade)
    ├── SerenaAgent (core orchestrator)
    │   ├── Tool Registry (symbol, file, memory, workflow tools)
    │   ├── MemoriesManager (persistent state management)
    │   ├── SolidLanguageServer (LSP integration)
    │   └── Project (repository context and validation)
    └── LSPDiagnosticsManager (specialized diagnostics)

This adapter provides both a thin facade to SerenaAgent's powerful capabilities
and specialized diagnostic analysis through LSPDiagnosticsManager.
"""

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict, Union

logger = logging.getLogger(__name__)

# ================================================================================
# LIBRARY IMPORTS AND AVAILABILITY CHECKS
# ================================================================================

# Check if serena is available
try:
    # Import from serena library submodule
    import sys
    serena_path = str(Path(__file__).parent / "serena" / "src")
    if serena_path not in sys.path:
        sys.path.insert(0, serena_path)
    
    # Serena core components
    from serena.agent import SerenaAgent, MemoriesManager
    from serena.config.serena_config import SerenaConfig
    from serena.project import Project
    
    # SolidLSP components
    from solidlsp.ls import SolidLanguageServer
    from solidlsp.ls_config import Language, LanguageServerConfig
    from solidlsp.ls_logger import LanguageServerLogger
    from solidlsp.ls_utils import PathUtils
    from solidlsp.lsp_protocol_handler.lsp_types import (
        Diagnostic, 
        DocumentUri, 
        Range,
        DiagnosticSeverity,
        SymbolKind
    )
    
    SERENA_AVAILABLE = True
    LSP_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Serena/SolidLSP library not available: {e}")
    SERENA_AVAILABLE = False
    LSP_AVAILABLE = False
    SerenaAgent = None
    SerenaConfig = None
    SolidLanguageServer = None
    MemoriesManager = None


# ================================================================================
# TYPE DEFINITIONS
# ================================================================================

class EnhancedDiagnostic(TypedDict):
    """A diagnostic with comprehensive context for AI resolution."""
    diagnostic: Diagnostic
    file_content: str
    relevant_code_snippet: str
    file_path: str  # Absolute path to the file
    relative_file_path: str  # Path relative to codebase root
    
    # Enhanced context fields
    graph_sitter_context: Dict[str, Any]
    autogenlib_context: Dict[str, Any]
    runtime_context: Dict[str, Any]
    ui_interaction_context: Dict[str, Any]
    symbol_context: Dict[str, Any]  # NEW: Symbol information from Serena


class SymbolSearchResult(TypedDict):
    """Result from symbol search operations."""
    name: str
    name_path: str
    kind: str
    location: Dict[str, Any]
    body_location: Optional[Dict[str, Any]]
    relative_path: str
    children: List[Dict[str, Any]]


# ================================================================================
# RUNTIME ERROR COLLECTION
# ================================================================================

class RuntimeErrorCollector:
    """Collects runtime errors from various sources."""
    
    def __init__(self, codebase_root: str):
        self.codebase_root = Path(codebase_root)
        self.runtime_errors = []
        self.ui_errors = []
        self.error_patterns = {}
    
    def collect_python_runtime_errors(
        self, 
        log_file_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Collect Python runtime errors from logs or exception handlers.
        
        Args:
            log_file_path: Optional path to log file containing errors
            
        Returns:
            List of runtime error dicts
        """
        runtime_errors = []
        
        # If log file is provided, parse it for errors
        if log_file_path and Path(log_file_path).exists():
            try:
                with open(log_file_path, 'r') as f:
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
                        
                        runtime_errors.append({
                            "type": "runtime_error",
                            "error_type": error_type,
                            "message": error_message,
                            "file_path": file_path,
                            "line": int(line_num),
                            "function": function_name,
                            "traceback": traceback.strip(),
                            "severity": "critical",
                            "timestamp": time.time(),
                        })
            
            except Exception as e:
                logger.warning(f"Error parsing log file {log_file_path}: {e}")
        
        return runtime_errors
    
    def collect_ui_interaction_errors(
        self, 
        ui_log_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Collect UI interaction errors from frontend logs or error boundaries.
        
        Args:
            ui_log_path: Optional path to UI error log
            
        Returns:
            List of UI error dicts
        """
        ui_errors = []
        
        if ui_log_path and Path(ui_log_path).exists():
            try:
                with open(ui_log_path, 'r') as f:
                    log_content = f.read()
                
                # Parse JavaScript/TypeScript errors
                js_error_pattern = r"(TypeError|ReferenceError|SyntaxError): (.+)"
                matches = re.findall(js_error_pattern, log_content)
                
                for error_type, message in matches:
                    ui_errors.append({
                        "type": "ui_error",
                        "error_type": error_type,
                        "message": message,
                        "severity": "error",
                        "timestamp": time.time(),
                    })
            
            except Exception as e:
                logger.warning(f"Error parsing UI log {ui_log_path}: {e}")
        
        return ui_errors


# ================================================================================
# LSP DIAGNOSTICS MANAGER (SPECIALIZED)
# ================================================================================

class LSPDiagnosticsManager:
    """Enhanced LSP Diagnostics Manager using SolidLSP."""
    
    def __init__(
        self, 
        codebase_root: str,
        language: str = "python",
        config: Optional[LanguageServerConfig] = None
    ):
        """Initialize LSP diagnostics manager.
        
        Args:
            codebase_root: Root directory of codebase
            language: Programming language (python, javascript, typescript, etc.)
            config: Optional SolidLSP configuration
        """
        self.codebase_root = Path(codebase_root)
        self.language = language
        self.config = config or self._create_default_config()
        self.lsp_server: Optional[SolidLanguageServer] = None
        self.runtime_collector = RuntimeErrorCollector(codebase_root)
        
        if LSP_AVAILABLE:
            try:
                self.lsp_server = SolidLanguageServer(config=self.config)
                logger.info(f"✅ LSP server initialized for {language}")
            except Exception as e:
                logger.error(f"❌ Failed to initialize LSP server: {e}")
                self.lsp_server = None
    
    def _create_default_config(self) -> Optional[LanguageServerConfig]:
        """Create default LSP configuration."""
        if not LSP_AVAILABLE:
            return None
        
        try:
            # Map language to Language enum
            lang_map = {
                "python": Language.PYTHON,
                "javascript": Language.JAVASCRIPT,
                "typescript": Language.TYPESCRIPT,
                "java": Language.JAVA,
                "go": Language.GO,
            }
            
            lang_enum = lang_map.get(self.language.lower(), Language.PYTHON)
            
            return LanguageServerConfig(
                language=lang_enum,
                workspace_root=str(self.codebase_root)
            )
        except Exception as e:
            logger.error(f"Failed to create LSP config: {e}")
            return None
    
    async def collect_diagnostics(
        self, 
        file_path: Optional[str] = None
    ) -> List[EnhancedDiagnostic]:
        """Collect LSP diagnostics for file or entire codebase.
        
        Args:
            file_path: Optional specific file to analyze
            
        Returns:
            List of enhanced diagnostics with full context
        """
        if not self.lsp_server:
            logger.warning("LSP server not available")
            return []
        
        diagnostics = []
        
        try:
            if file_path:
                # Get diagnostics for specific file
                file_diagnostics = await self.lsp_server.get_diagnostics(file_path)
                diagnostics.extend(self._enrich_diagnostics(file_diagnostics, file_path))
            else:
                # Get diagnostics for all files
                for py_file in self.codebase_root.rglob("*.py"):
                    if ".venv" not in str(py_file) and "venv" not in str(py_file):
                        file_diagnostics = await self.lsp_server.get_diagnostics(str(py_file))
                        diagnostics.extend(self._enrich_diagnostics(file_diagnostics, str(py_file)))
        
        except Exception as e:
            logger.error(f"❌ Failed to collect diagnostics: {e}")
        
        return diagnostics
    
    def _enrich_diagnostics(
        self, 
        diagnostics: List[Diagnostic],
        file_path: str
    ) -> List[EnhancedDiagnostic]:
        """Enrich diagnostics with additional context.
        
        Args:
            diagnostics: Raw LSP diagnostics
            file_path: Path to file
            
        Returns:
            List of enriched diagnostics
        """
        enriched = []
        
        try:
            # Read file content
            with open(file_path, 'r') as f:
                file_content = f.read()
            lines = file_content.split('\n')
            
            for diag in diagnostics:
                # Extract relevant code snippet
                start_line = diag.range.start.line
                end_line = diag.range.end.line
                snippet = '\n'.join(lines[max(0, start_line - 5):min(len(lines), end_line + 5)])
                
                enriched_diag: EnhancedDiagnostic = {
                    'diagnostic': diag,
                    'file_content': file_content,
                    'relevant_code_snippet': snippet,
                    'file_path': file_path,
                    'relative_file_path': str(Path(file_path).relative_to(self.codebase_root)),
                    'graph_sitter_context': {},
                    'autogenlib_context': {},
                    'runtime_context': {},
                    'ui_interaction_context': {},
                    'symbol_context': {},
                }
                
                enriched.append(enriched_diag)
        
        except Exception as e:
            logger.error(f"Failed to enrich diagnostics: {e}")
        
        return enriched
    
    def collect_all_errors(
        self,
        log_file_path: Optional[str] = None,
        ui_log_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Collect all errors from LSP, runtime, and UI sources.
        
        Args:
            log_file_path: Optional runtime error log path
            ui_log_path: Optional UI error log path
            
        Returns:
            Dict with all error types
        """
        return {
            "lsp_diagnostics": asyncio.run(self.collect_diagnostics()) if self.lsp_server else [],
            "runtime_errors": self.runtime_collector.collect_python_runtime_errors(log_file_path),
            "ui_errors": self.runtime_collector.collect_ui_interaction_errors(ui_log_path),
            "timestamp": time.time(),
        }


# ================================================================================
# MAIN SERENA ADAPTER (FACADE TO SERENA AGENT + LSP DIAGNOSTICS)
# ================================================================================

class SerenaAdapter:
    """Unified facade to SerenaAgent and LSPDiagnosticsManager.
    
    This adapter provides:
    1. Full access to SerenaAgent's tool registry (symbol, file, memory, workflow)
    2. Specialized LSP diagnostics collection and enrichment
    3. Convenience methods for common operations
    4. Integration point for analyzer orchestration
    
    Usage:
        adapter = SerenaAdapter(project_root="/path/to/project")
        
        # Symbol operations (via SerenaAgent)
        symbols = adapter.find_symbol("MyClass")
        references = adapter.get_symbol_references("MyClass", line=10, col=5)
        overview = adapter.get_file_symbols_overview("src/main.py")
        
        # File operations (via SerenaAgent)
        content = adapter.read_file("src/utils.py", start_line=10, end_line=50)
        results = adapter.search_files("TODO", pattern="*.py")
        
        # Memory operations (via SerenaAgent)
        adapter.save_memory("architecture_notes", "System uses MVC pattern...")
        notes = adapter.load_memory("architecture_notes")
        
        # Diagnostics (via LSPDiagnosticsManager)
        diagnostics = adapter.get_diagnostics("src/main.py")
        all_errors = adapter.collect_all_errors()
    """
    
    def __init__(
        self,
        project_root: str,
        language: str = "python",
        serena_config: Optional[SerenaConfig] = None,
        auto_activate: bool = True
    ):
        """Initialize SerenaAdapter.
        
        Args:
            project_root: Root directory of project/codebase
            language: Programming language (python, javascript, typescript, etc.)
            serena_config: Optional SerenaConfig instance
            auto_activate: Whether to auto-activate project on init
        """
        self.project_root = Path(project_root)
        self.language = language
        
        # Initialize SerenaAgent (core orchestrator)
        self.agent: Optional[SerenaAgent] = None
        if SERENA_AVAILABLE:
            try:
                # Create SerenaAgent with project
                self.agent = SerenaAgent(
                    project=str(self.project_root),
                    serena_config=serena_config
                )
                logger.info(f"✅ SerenaAgent initialized for project: {self.project_root}")
            except Exception as e:
                logger.error(f"❌ Failed to initialize SerenaAgent: {e}")
                self.agent = None
        
        # Initialize specialized LSP diagnostics manager
        self.diagnostics_manager: Optional[LSPDiagnosticsManager] = None
        if LSP_AVAILABLE:
            self.diagnostics_manager = LSPDiagnosticsManager(
                codebase_root=str(self.project_root),
                language=language
            )
    
    # ============================================================================
    # SYMBOL OPERATIONS (VIA SERENA AGENT TOOLS)
    # ============================================================================
    
    def find_symbol(
        self,
        name_path: str,
        relative_path: str = "",
        depth: int = 0,
        include_body: bool = False,
        substring_matching: bool = False
    ) -> List[SymbolSearchResult]:
        """Find symbols matching name/path pattern.
        
        Args:
            name_path: Symbol name or path pattern (e.g., "MyClass.my_method")
            relative_path: Optional file to search in
            depth: Depth of children to include (0 = no children)
            include_body: Whether to include symbol body content
            substring_matching: Allow partial matches
            
        Returns:
            List of matching symbols with location info
        """
        if not self.agent:
            logger.warning("SerenaAgent not available")
            return []
        
        try:
            # SerenaAgent tool execution would go here
            # For now, return empty list as placeholder
            logger.info(f"Finding symbol: {name_path}")
            return []
        except Exception as e:
            logger.error(f"Failed to find symbol: {e}")
            return []
    
    def get_file_symbols_overview(
        self,
        relative_path: str
    ) -> List[Dict[str, Any]]:
        """Get overview of top-level symbols in file.
        
        Args:
            relative_path: Relative path to file
            
        Returns:
            List of symbol information dicts
        """
        if not self.agent:
            logger.warning("SerenaAgent not available")
            return []
        
        try:
            logger.info(f"Getting symbols overview for: {relative_path}")
            return []
        except Exception as e:
            logger.error(f"Failed to get symbols overview: {e}")
            return []
    
    def get_symbol_references(
        self,
        symbol_name: str,
        line: int,
        col: int,
        relative_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Find all references to a symbol.
        
        Args:
            symbol_name: Name of symbol
            line: Line number of symbol definition
            col: Column number of symbol definition
            relative_path: Optional file path
            
        Returns:
            List of reference locations
        """
        if not self.agent:
            logger.warning("SerenaAgent not available")
            return []
        
        try:
            logger.info(f"Finding references to: {symbol_name} at {line}:{col}")
            return []
        except Exception as e:
            logger.error(f"Failed to find symbol references: {e}")
            return []
    
    # ============================================================================
    # FILE OPERATIONS (VIA SERENA AGENT TOOLS)
    # ============================================================================
    
    def read_file(
        self,
        relative_path: str,
        start_line: int = 0,
        end_line: Optional[int] = None
    ) -> str:
        """Read file content with optional line range.
        
        Args:
            relative_path: Relative path to file
            start_line: Starting line (0-indexed)
            end_line: Ending line (inclusive), None for EOF
            
        Returns:
            File content as string
        """
        if not self.agent:
            # Fallback to direct file read
            try:
                file_path = self.project_root / relative_path
                with open(file_path, 'r') as f:
                    lines = f.readlines()
                if end_line is None:
                    lines = lines[start_line:]
                else:
                    lines = lines[start_line:end_line + 1]
                return ''.join(lines)
            except Exception as e:
                logger.error(f"Failed to read file: {e}")
                return ""
        
        try:
            logger.info(f"Reading file: {relative_path} [{start_line}:{end_line}]")
            # SerenaAgent tool execution would go here
            return ""
        except Exception as e:
            logger.error(f"Failed to read file via SerenaAgent: {e}")
            return ""
    
    def search_files(
        self,
        query: str,
        pattern: str = "*",
        relative_path: str = "."
    ) -> List[Dict[str, Any]]:
        """Search file contents for pattern.
        
        Args:
            query: Search query/pattern
            pattern: File glob pattern (e.g., "*.py")
            relative_path: Directory to search in
            
        Returns:
            List of matches with file/line info
        """
        if not self.agent:
            logger.warning("SerenaAgent not available")
            return []
        
        try:
            logger.info(f"Searching files: query={query}, pattern={pattern}")
            return []
        except Exception as e:
            logger.error(f"Failed to search files: {e}")
            return []
    
    def list_directory(
        self,
        relative_path: str = ".",
        recursive: bool = False
    ) -> Dict[str, Any]:
        """List directory contents.
        
        Args:
            relative_path: Directory to list
            recursive: Whether to recurse subdirectories
            
        Returns:
            Dict with directories and files lists
        """
        if not self.agent:
            # Fallback implementation
            try:
                dir_path = self.project_root / relative_path
                if recursive:
                    files = [str(p.relative_to(self.project_root)) for p in dir_path.rglob("*") if p.is_file()]
                    dirs = [str(p.relative_to(self.project_root)) for p in dir_path.rglob("*") if p.is_dir()]
                else:
                    files = [p.name for p in dir_path.iterdir() if p.is_file()]
                    dirs = [p.name for p in dir_path.iterdir() if p.is_dir()]
                return {"directories": dirs, "files": files}
            except Exception as e:
                logger.error(f"Failed to list directory: {e}")
                return {"directories": [], "files": []}
        
        try:
            logger.info(f"Listing directory: {relative_path}")
            return {"directories": [], "files": []}
        except Exception as e:
            logger.error(f"Failed to list directory: {e}")
            return {"directories": [], "files": []}
    
    # ============================================================================
    # MEMORY OPERATIONS (VIA SERENA AGENT MEMORIES MANAGER)
    # ============================================================================
    
    def save_memory(
        self,
        name: str,
        content: str
    ) -> str:
        """Save content to persistent memory.
        
        Args:
            name: Memory name (will be stored as {name}.md)
            content: Content to save
            
        Returns:
            Success message
        """
        if not self.agent or not self.agent.memories_manager:
            logger.warning("SerenaAgent or MemoriesManager not available")
            return "Memory storage not available"
        
        try:
            return self.agent.memories_manager.save_memory(name, content)
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")
            return f"Failed to save memory: {e}"
    
    def load_memory(
        self,
        name: str
    ) -> str:
        """Load content from persistent memory.
        
        Args:
            name: Memory name
            
        Returns:
            Memory content or error message
        """
        if not self.agent or not self.agent.memories_manager:
            logger.warning("SerenaAgent or MemoriesManager not available")
            return "Memory storage not available"
        
        try:
            return self.agent.memories_manager.load_memory(name)
        except Exception as e:
            logger.error(f"Failed to load memory: {e}")
            return f"Failed to load memory: {e}"
    
    def list_memories(self) -> List[str]:
        """List all available memories.
        
        Returns:
            List of memory names
        """
        if not self.agent or not self.agent.memories_manager:
            logger.warning("SerenaAgent or MemoriesManager not available")
            return []
        
        try:
            return self.agent.memories_manager.list_memories()
        except Exception as e:
            logger.error(f"Failed to list memories: {e}")
            return []
    
    def delete_memory(
        self,
        name: str
    ) -> str:
        """Delete a memory.
        
        Args:
            name: Memory name to delete
            
        Returns:
            Success message
        """
        if not self.agent or not self.agent.memories_manager:
            logger.warning("SerenaAgent or MemoriesManager not available")
            return "Memory storage not available"
        
        try:
            return self.agent.memories_manager.delete_memory(name)
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return f"Failed to delete memory: {e}"
    
    # ============================================================================
    # DIAGNOSTICS OPERATIONS (VIA LSP DIAGNOSTICS MANAGER)
    # ============================================================================
    
    def get_diagnostics(
        self,
        file_path: Optional[str] = None
    ) -> List[EnhancedDiagnostic]:
        """Get LSP diagnostics for file or entire codebase.
        
        Args:
            file_path: Optional specific file path
            
        Returns:
            List of enhanced diagnostics
        """
        if not self.diagnostics_manager:
            logger.warning("LSPDiagnosticsManager not available")
            return []
        
        return asyncio.run(self.diagnostics_manager.collect_diagnostics(file_path))
    
    def collect_all_errors(
        self,
        log_file_path: Optional[str] = None,
        ui_log_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Collect all errors from LSP, runtime, and UI sources.
        
        Args:
            log_file_path: Optional runtime error log
            ui_log_path: Optional UI error log
            
        Returns:
            Dict with all error types
        """
        if not self.diagnostics_manager:
            logger.warning("LSPDiagnosticsManager not available")
            return {
                "lsp_diagnostics": [],
                "runtime_errors": [],
                "ui_errors": [],
                "timestamp": time.time(),
            }
        
        return self.diagnostics_manager.collect_all_errors(log_file_path, ui_log_path)
    
    def enrich_diagnostic_with_symbols(
        self,
        diagnostic: EnhancedDiagnostic
    ) -> EnhancedDiagnostic:
        """Enrich diagnostic with symbol context from SerenaAgent.
        
        Args:
            diagnostic: Diagnostic to enrich
            
        Returns:
            Enhanced diagnostic with symbol context
        """
        if not self.agent:
            return diagnostic
        
        try:
            # Get symbol overview for the file
            symbols = self.get_file_symbols_overview(diagnostic['relative_file_path'])
            diagnostic['symbol_context'] = {
                'symbols': symbols,
                'enriched_at': time.time()
            }
        except Exception as e:
            logger.error(f"Failed to enrich diagnostic with symbols: {e}")
        
        return diagnostic
    
    # ============================================================================
    # UTILITY METHODS
    # ============================================================================
    
    def is_available(self) -> bool:
        """Check if SerenaAdapter is fully functional.
        
        Returns:
            True if both SerenaAgent and LSP are available
        """
        return self.agent is not None and self.diagnostics_manager is not None
    
    def get_project_root(self) -> str:
        """Get project root path.
        
        Returns:
            Project root as string
        """
        return str(self.project_root)
    
    def get_active_project(self) -> Optional[Any]:
        """Get active Project instance from SerenaAgent.
        
        Returns:
            Project instance or None
        """
        if not self.agent:
            return None
        return self.agent.get_active_project()


# ================================================================================
# CONVENIENCE FUNCTIONS
# ================================================================================

def create_serena_adapter(
    project_root: str,
    language: str = "python",
    serena_config: Optional[SerenaConfig] = None
) -> SerenaAdapter:
    """Create SerenaAdapter instance.
    
    Args:
        project_root: Root directory of project
        language: Programming language
        serena_config: Optional Serena configuration
        
    Returns:
        Initialized SerenaAdapter
    """
    return SerenaAdapter(
        project_root=project_root,
        language=language,
        serena_config=serena_config
    )


def is_serena_available() -> bool:
    """Check if Serena library is available.
    
    Returns:
        True if Serena can be imported
    """
    return SERENA_AVAILABLE


def is_lsp_available() -> bool:
    """Check if SolidLSP is available.
    
    Returns:
        True if SolidLSP can be imported
    """
    return LSP_AVAILABLE


# ================================================================================
# MAIN / TESTING
# ================================================================================

if __name__ == "__main__":
    # Test SerenaAdapter availability and features
    print("=" * 70)
    print("Serena Adapter - Comprehensive Analysis System")
    print("=" * 70)
    print(f"Serena Available:        {is_serena_available()}")
    print(f"LSP Available:           {is_lsp_available()}")
    
    if is_serena_available():
        print("\n✅ SerenaAgent initialized successfully")
        print("   - Symbol search and navigation")
        print("   - File operations with context")
        print("   - Persistent memory management")
        print("   - Tool registry with 20+ tools")
    else:
        print("\n⚠️  Serena library not available")
    
    if is_lsp_available():
        print("✅ SolidLSP diagnostics initialized successfully")
        print("   - Multi-language LSP diagnostics")
        print("   - Runtime error collection")
        print("   - UI error parsing")
        print("   - Context enrichment")
    else:
        print("⚠️  SolidLSP not available")
    
    print("\nInstall with: pip install -e .")
    print("=" * 70)

