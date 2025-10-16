#!/usr/bin/env python3
"""Serena Adapter - Semantic Code Search and Context Management

Provides integration with the Serena library for:
- Semantic code search across repositories
- Context-aware code editing and retrieval
- Persistent memory management for code context
- Integration with analyzer orchestration

This adapter wraps Serena's powerful semantic capabilities to provide
intelligent code understanding and manipulation for error resolution.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# Check if serena is available
try:
    # Import from serena library submodule
    import sys
    sys.path.insert(0, str(Path(__file__).parent / "serena" / "src"))
    
    from serena import SerenaAgent
    from serena.config import SerenaConfig
    SERENA_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Serena library not available: {e}")
    SERENA_AVAILABLE = False
    SerenaAgent = None
    SerenaConfig = None


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


if __name__ == "__main__":
    # Test Serena availability
    print("=" * 60)
    print("Serena Adapter Test")
    print("=" * 60)
    print(f"Serena Available: {is_serena_available()}")
    
    if is_serena_available():
        # Test semantic search
        print("\n✅ Serena adapter initialized successfully")
    else:
        print("\n⚠️  Serena library not available")
        print("Install with: pip install serena")

