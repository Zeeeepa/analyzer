#!/usr/bin/env python3
"""Serena Adapter - Unified Semantic Search, Context Management & LSP Diagnostics

Provides comprehensive integration with the Serena library for:
- Semantic code search across repositories  
- Context-aware code editing and retrieval
- Persistent memory management for code context
- LSP diagnostics collection and enrichment (via SolidLSP)
- Runtime error collection and analysis
- Integration with analyzer orchestration

This adapter wraps both Serena's semantic capabilities and SolidLSP's
language server protocol handling to provide complete error context.
"""

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict, Union

logger = logging.getLogger(__name__)

# Check if serena is available
try:
    # Import from serena library submodule
    import sys
    serena_path = str(Path(__file__).parent / "serena" / "src")
    if serena_path not in sys.path:
        sys.path.insert(0, serena_path)
    
    # Serena semantic search
    from serena import SerenaAgent
    from serena.config import SerenaConfig
    
    # SolidLSP components
    from solidlsp.ls import SolidLanguageServer
    from solidlsp.ls_config import Language, LanguageServerConfig
    from solidlsp.ls_logger import LanguageServerLogger
    from solidlsp.ls_utils import PathUtils
    from solidlsp.lsp_protocol_handler.lsp_types import (
        Diagnostic, 
        DocumentUri, 
        Range,
        DiagnosticSeverity
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


# ================================================================================
# SERENA CLIENT CONFIGURATION
# ================================================================================

def get_serena_client(config_path: Optional[str] = None) -> Optional[Any]:
    """Get configured Serena client.
    
    Args:
        config_path: Optional path to serena config file
        
    Returns:
        SerenaAgent instance or None if not available
    """
    if not SERENA_AVAILABLE:
        logger.error("❌ Serena library not available")
        return None
    
    try:
        # Load config if provided
        if config_path and Path(config_path).exists():
            config = SerenaConfig.from_file(config_path)
        else:
            # Use default config
            config = SerenaConfig()
        
        # Create agent
        agent = SerenaAgent(config=config)
        logger.info("✅ Serena agent initialized")
        return agent
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize Serena: {e}")
        return None


# ================================================================================
# SEMANTIC CODE SEARCH
# ================================================================================

def semantic_search(
    query: str,
    repository_path: str,
    max_results: int = 10,
    file_patterns: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Perform semantic code search across repository.
    
    Args:
        query: Natural language search query
        repository_path: Path to repository to search
        max_results: Maximum number of results to return
        file_patterns: Optional file patterns to filter (e.g., ["*.py"])
        
    Returns:
        List of search results with code snippets and metadata
    """
    if not SERENA_AVAILABLE:
        logger.warning("Serena not available, returning empty results")
        return []
    
    try:
        agent = get_serena_client()
        if not agent:
            return []
        
        # Perform semantic search
        results = agent.search(
            query=query,
            path=repository_path,
            max_results=max_results,
            file_patterns=file_patterns or ["*.py"]
        )
        
        # Format results
        formatted_results = []
        for result in results:
            formatted_results.append({
                "file_path": result.get("file_path"),
                "code_snippet": result.get("code"),
                "line_number": result.get("line_number"),
                "relevance_score": result.get("score", 0.0),
                "context": result.get("context", "")
            })
        
        logger.info(f"✅ Found {len(formatted_results)} semantic search results")
        return formatted_results
        
    except Exception as e:
        logger.error(f"❌ Semantic search failed: {e}")
        return []


def find_similar_code(
    code_snippet: str,
    repository_path: str,
    threshold: float = 0.7,
    max_results: int = 5
) -> List[Dict[str, Any]]:
    """Find code similar to given snippet using semantic similarity.
    
    Args:
        code_snippet: Code to find similar examples of
        repository_path: Path to repository to search
        threshold: Similarity threshold (0.0-1.0)
        max_results: Maximum results to return
        
    Returns:
        List of similar code snippets with metadata
    """
    if not SERENA_AVAILABLE:
        return []
    
    try:
        agent = get_serena_client()
        if not agent:
            return []
        
        # Find similar code
        results = agent.find_similar(
            code=code_snippet,
            path=repository_path,
            threshold=threshold,
            max_results=max_results
        )
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Similar code search failed: {e}")
        return []


# ================================================================================
# CONTEXT RETRIEVAL
# ================================================================================

def get_relevant_context(
    error_location: Dict[str, Any],
    repository_path: str,
    context_window: int = 10
) -> Dict[str, Any]:
    """Get relevant code context for an error location.
    
    Args:
        error_location: Dict with 'file_path' and 'line_number'
        repository_path: Path to repository
        context_window: Number of lines before/after to include
        
    Returns:
        Dict with context information including related code
    """
    if not SERENA_AVAILABLE:
        return {
            "error_context": "",
            "related_code": [],
            "dependencies": [],
            "status": "error",
            "message": "Serena not available"
        }
    
    try:
        agent = get_serena_client()
        if not agent:
            return {"status": "error", "message": "Failed to initialize Serena"}
        
        file_path = error_location.get("file_path")
        line_number = error_location.get("line_number", 0)
        
        # Get context around error
        context = agent.get_context(
            file_path=file_path,
            line_number=line_number,
            window=context_window
        )
        
        # Find related code semantically
        error_code = context.get("code", "")
        related = find_similar_code(
            code_snippet=error_code,
            repository_path=repository_path,
            max_results=5
        )
        
        return {
            "error_context": context.get("code", ""),
            "surrounding_functions": context.get("functions", []),
            "related_code": related,
            "imports": context.get("imports", []),
            "dependencies": context.get("dependencies", []),
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"❌ Context retrieval failed: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


def get_function_context(
    function_name: str,
    repository_path: str
) -> Optional[Dict[str, Any]]:
    """Get comprehensive context for a specific function.
    
    Args:
        function_name: Name of function to analyze
        repository_path: Path to repository
        
    Returns:
        Dict with function definition, callers, callees, and documentation
    """
    if not SERENA_AVAILABLE:
        return None
    
    try:
        agent = get_serena_client()
        if not agent:
            return None
        
        # Search for function definition
        results = semantic_search(
            query=f"def {function_name}",
            repository_path=repository_path,
            max_results=1
        )
        
        if not results:
            return None
        
        function_info = results[0]
        
        # Get callers and callees
        callers = agent.find_callers(function_name, repository_path)
        callees = agent.find_callees(function_name, repository_path)
        
        return {
            "definition": function_info.get("code_snippet"),
            "file_path": function_info.get("file_path"),
            "line_number": function_info.get("line_number"),
            "callers": callers,
            "callees": callees,
            "documentation": function_info.get("context", "")
        }
        
    except Exception as e:
        logger.error(f"❌ Function context retrieval failed: {e}")
        return None


# ================================================================================
# MEMORY MANAGEMENT
# ================================================================================

class SerenaMemory:
    """Persistent memory management for code analysis sessions."""
    
    def __init__(self, memory_dir: Optional[str] = None):
        """Initialize memory manager.
        
        Args:
            memory_dir: Directory to store memory files
        """
        self.memory_dir = Path(memory_dir or ".serena/memories")
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.memories: Dict[str, Any] = {}
        
    def store(self, key: str, value: Any) -> None:
        """Store value in memory.
        
        Args:
            key: Memory key
            value: Value to store
        """
        self.memories[key] = value
        
        # Persist to disk
        memory_file = self.memory_dir / f"{key}.json"
        try:
            import json
            with open(memory_file, 'w') as f:
                json.dump(value, f, indent=2)
            logger.debug(f"💾 Stored memory: {key}")
        except Exception as e:
            logger.warning(f"Failed to persist memory {key}: {e}")
    
    def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve value from memory.
        
        Args:
            key: Memory key
            
        Returns:
            Stored value or None if not found
        """
        # Check in-memory first
        if key in self.memories:
            return self.memories[key]
        
        # Try loading from disk
        memory_file = self.memory_dir / f"{key}.json"
        if memory_file.exists():
            try:
                import json
                with open(memory_file, 'r') as f:
                    value = json.load(f)
                self.memories[key] = value
                logger.debug(f"💾 Retrieved memory: {key}")
                return value
            except Exception as e:
                logger.warning(f"Failed to load memory {key}: {e}")
        
        return None
    
    def clear(self, key: Optional[str] = None) -> None:
        """Clear memory.
        
        Args:
            key: Specific key to clear, or None to clear all
        """
        if key:
            self.memories.pop(key, None)
            memory_file = self.memory_dir / f"{key}.json"
            if memory_file.exists():
                memory_file.unlink()
        else:
            self.memories.clear()
            for memory_file in self.memory_dir.glob("*.json"):
                memory_file.unlink()


# ================================================================================
# CONTEXT-AWARE EDITING
# ================================================================================

def suggest_edits(
    file_path: str,
    error_info: Dict[str, Any],
    repository_path: str
) -> List[Dict[str, Any]]:
    """Suggest context-aware code edits based on error.
    
    Args:
        file_path: Path to file with error
        error_info: Error information dict
        repository_path: Path to repository
        
    Returns:
        List of suggested edits with explanations
    """
    if not SERENA_AVAILABLE:
        return []
    
    try:
        agent = get_serena_client()
        if not agent:
            return []
        
        # Get context around error
        context = get_relevant_context(
            error_location={
                "file_path": file_path,
                "line_number": error_info.get("line_number", 0)
            },
            repository_path=repository_path
        )
        
        # Use context to suggest edits
        suggestions = agent.suggest_edits(
            file_path=file_path,
            error_context=context,
            error_info=error_info
        )
        
        return suggestions
        
    except Exception as e:
        logger.error(f"❌ Edit suggestion failed: {e}")
        return []


# ================================================================================
# UTILITY FUNCTIONS
# ================================================================================

def index_repository(repository_path: str) -> bool:
    """Index repository for semantic search.
    
    Args:
        repository_path: Path to repository to index
        
    Returns:
        True if indexing succeeded
    """
    if not SERENA_AVAILABLE:
        logger.warning("Serena not available, skipping indexing")
        return False
    
    try:
        agent = get_serena_client()
        if not agent:
            return False
        
        logger.info(f"🔍 Indexing repository: {repository_path}")
        agent.index_repository(repository_path)
        logger.info("✅ Repository indexed successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Repository indexing failed: {e}")
        return False


def is_serena_available() -> bool:
    """Check if Serena library is available.
    
    Returns:
        True if Serena is available
    """
    return SERENA_AVAILABLE


# ================================================================================
# INTEGRATION WITH ANALYZER
# ================================================================================

def enrich_error_with_serena_context(
    error_dict: Dict[str, Any],
    repository_path: str
) -> Dict[str, Any]:
    """Enrich error information with Serena semantic context.
    
    This is the main integration point for the analyzer.
    
    Args:
        error_dict: Error information from analyzer
        repository_path: Path to repository
        
    Returns:
        Enriched error dict with Serena context
    """
    if not SERENA_AVAILABLE:
        error_dict["serena_context"] = {
            "status": "unavailable",
            "message": "Serena library not available"
        }
        return error_dict
    
    try:
        # Get relevant context
        context = get_relevant_context(
            error_location={
                "file_path": error_dict.get("file_path"),
                "line_number": error_dict.get("line_number", 0)
            },
            repository_path=repository_path
        )
        
        # Add to error dict
        error_dict["serena_context"] = {
            "status": "success",
            "surrounding_code": context.get("error_context"),
            "related_code": context.get("related_code", []),
            "dependencies": context.get("dependencies", []),
            "functions": context.get("surrounding_functions", [])
        }
        
        logger.info("✅ Enriched error with Serena context")
        
    except Exception as e:
        logger.error(f"❌ Failed to enrich error with Serena: {e}")
        error_dict["serena_context"] = {
            "status": "error",
            "message": str(e)
        }
    
    return error_dict


# ================================================================================
# LSP DIAGNOSTICS INTEGRATION (via SolidLSP)
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
# UNIFIED INTERFACE FOR ANALYZER INTEGRATION
# ================================================================================

def create_serena_lsp_manager(
    codebase_root: str,
    language: str = "python",
    serena_config: Optional[Dict[str, Any]] = None
) -> tuple[Optional[Any], Optional[LSPDiagnosticsManager]]:
    """Create both Serena agent and LSP manager for unified error analysis.
    
    Args:
        codebase_root: Root directory of codebase
        language: Programming language
        serena_config: Optional Serena configuration
        
    Returns:
        Tuple of (serena_agent, lsp_manager)
    """
    # Create Serena agent
    serena_agent = get_serena_client()
    
    # Create LSP manager
    lsp_manager = None
    if LSP_AVAILABLE:
        lsp_manager = LSPDiagnosticsManager(
            codebase_root=codebase_root,
            language=language
        )
    
    return serena_agent, lsp_manager


if __name__ == "__main__":
    # Test Serena and LSP availability
    print("=" * 60)
    print("Serena + SolidLSP Adapter Test")
    print("=" * 60)
    print(f"Serena Available: {is_serena_available()}")
    print(f"LSP Available: {LSP_AVAILABLE}")
    
    if is_serena_available():
        print("\n✅ Serena semantic search initialized successfully")
    else:
        print("\n⚠️  Serena library not available")
    
    if LSP_AVAILABLE:
        print("✅ SolidLSP diagnostics initialized successfully")
    else:
        print("⚠️  SolidLSP not available")
    
    print("\nInstall with: pip install -e .")
