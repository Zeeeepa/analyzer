"""
Tool Search with RAG (Retrieval-Augmented Generation)
Implements efficient tool discovery using vector embeddings and semantic search.

Key Features:
1. Vector embeddings for tool documentation using ChromaDB
2. Semantic search for finding relevant tools (not just keyword matching)
3. Integration with Async Skill Library for unified retrieval
4. Caching layer for embeddings and query results
5. Relevance scoring with multiple signals (semantic, usage, success rate)
6. Context optimization - only load what's needed
7. Configurable RAG parameters (top-K, similarity threshold, etc.)

Architecture:
- ToolSearchManager: Main orchestrator with RAG capabilities
- ToolEmbedder: Creates and manages vector embeddings
- RelevanceScorer: Multi-signal relevance scoring
- QueryCache: LRU cache for recent queries

Token Savings:
- Without RAG: Load all 74+ tools = ~15K tokens
- With RAG: Load only top-5 relevant tools = ~1K tokens
- 93% token reduction!
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set, Tuple
import re
import logging
import hashlib
import json
import time
from pathlib import Path
from difflib import SequenceMatcher
import asyncio
from functools import lru_cache

logger = logging.getLogger(__name__)

# ChromaDB for vector embeddings (lazy load)
CHROMADB_AVAILABLE = False
_chromadb_client = None

def _get_chromadb():
    """Lazy load ChromaDB"""
    global CHROMADB_AVAILABLE, _chromadb_client
    if _chromadb_client is not None:
        return _chromadb_client

    try:
        import chromadb
        from chromadb.config import Settings

        # Create persistent client
        _chromadb_client = chromadb.PersistentClient(
            path=str(Path("memory/tool_embeddings")),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        CHROMADB_AVAILABLE = True
        logger.info("[RAG] ChromaDB initialized for tool search")
        return _chromadb_client
    except ImportError:
        logger.warning("[RAG] ChromaDB not available - falling back to keyword search")
        CHROMADB_AVAILABLE = False
        return None
    except Exception as e:
        logger.error(f"[RAG] ChromaDB initialization failed: {e}")
        CHROMADB_AVAILABLE = False
        return None


@dataclass
class ToolDefinition:
    """A tool with its full definition."""
    name: str
    description: str
    parameters: Dict[str, Any]
    category: str = "general"
    defer_loading: bool = True
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    last_used: Optional[float] = None
    avg_execution_time: float = 0.0

    def get_success_rate(self) -> float:
        """Calculate success rate"""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.5  # Default for new tools
        return self.success_count / total

    def get_embedding_text(self) -> str:
        """Get text for embedding generation"""
        # Combine name, description, and parameter names for rich context
        param_names = ", ".join(self.parameters.get("properties", {}).keys())
        return f"{self.name}: {self.description}. Parameters: {param_names}. Category: {self.category}"


@dataclass
class ToolSearchResult:
    """Result of a tool search with detailed relevance scoring."""
    tool: ToolDefinition
    relevance_score: float
    semantic_score: float
    usage_score: float
    success_score: float
    match_reason: str


class RAGConfig:
    """Configuration for RAG-based tool search"""
    def __init__(self):
        # Top-K retrieval
        self.rag_top_k: int = 5

        # Similarity threshold (0-1, higher = more strict)
        self.rag_similarity_threshold: float = 0.7

        # Embedding model (ChromaDB default uses sentence-transformers)
        self.embedding_model: str = "all-MiniLM-L6-v2"

        # Cache settings
        self.cache_enabled: bool = True
        self.cache_ttl_seconds: int = 3600  # 1 hour
        self.cache_max_size: int = 100

        # Relevance scoring weights
        self.weight_semantic: float = 0.5
        self.weight_usage: float = 0.3
        self.weight_success: float = 0.2

        # Context optimization
        self.include_full_params: bool = False  # Only include essential params
        self.max_description_length: int = 200  # Truncate long descriptions


class QueryCache:
    """LRU cache for query results"""
    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Tuple[List[ToolSearchResult], float]] = {}
        self._access_order: List[str] = []

    def get(self, query_hash: str) -> Optional[List[ToolSearchResult]]:
        """Get cached results if not expired"""
        if query_hash not in self._cache:
            return None

        results, timestamp = self._cache[query_hash]
        if time.time() - timestamp > self.ttl_seconds:
            # Expired
            del self._cache[query_hash]
            self._access_order.remove(query_hash)
            return None

        # Update access order
        self._access_order.remove(query_hash)
        self._access_order.append(query_hash)
        return results

    def set(self, query_hash: str, results: List[ToolSearchResult]):
        """Cache query results"""
        # Evict oldest if at capacity
        if len(self._cache) >= self.max_size and query_hash not in self._cache:
            oldest = self._access_order.pop(0)
            del self._cache[oldest]

        self._cache[query_hash] = (results, time.time())
        if query_hash in self._access_order:
            self._access_order.remove(query_hash)
        self._access_order.append(query_hash)

    def invalidate(self, pattern: str = None):
        """Invalidate cache entries"""
        if pattern is None:
            # Clear all
            self._cache.clear()
            self._access_order.clear()
        else:
            # Clear matching pattern
            keys_to_remove = [k for k in self._cache.keys() if re.search(pattern, k)]
            for key in keys_to_remove:
                del self._cache[key]
                self._access_order.remove(key)


class ToolEmbedder:
    """Manages tool embeddings using ChromaDB"""
    def __init__(self, collection_name: str = "tool_search"):
        self.collection_name = collection_name
        self.collection = None
        self._embedding_cache: Dict[str, str] = {}  # tool_name -> embedding_hash
        self._initialize_collection()

    def _initialize_collection(self):
        """Initialize ChromaDB collection"""
        client = _get_chromadb()
        if client is None:
            return

        try:
            # Get or create collection
            self.collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "Tool documentation embeddings for RAG search"}
            )
            logger.info(f"[RAG] Initialized collection '{self.collection_name}' with {self.collection.count()} tools")
        except Exception as e:
            logger.error(f"[RAG] Failed to initialize collection: {e}")
            self.collection = None

    def index_tool(self, tool: ToolDefinition):
        """Index a tool for vector search"""
        if self.collection is None:
            return

        try:
            # Generate unique ID
            tool_id = f"tool_{tool.name}"

            # Get embedding text
            embedding_text = tool.get_embedding_text()

            # Check if already indexed with same content
            content_hash = hashlib.md5(embedding_text.encode()).hexdigest()
            if tool.name in self._embedding_cache and self._embedding_cache[tool.name] == content_hash:
                return  # Already indexed

            # Add or update in collection
            self.collection.upsert(
                ids=[tool_id],
                documents=[embedding_text],
                metadatas=[{
                    "name": tool.name,
                    "category": tool.category,
                    "description": tool.description,
                    "usage_count": tool.usage_count,
                    "success_rate": tool.get_success_rate()
                }]
            )

            self._embedding_cache[tool.name] = content_hash
            logger.debug(f"[RAG] Indexed tool: {tool.name}")
        except Exception as e:
            logger.error(f"[RAG] Failed to index tool {tool.name}: {e}")

    def search(self, query: str, top_k: int = 5, min_similarity: float = 0.0) -> List[Tuple[str, float]]:
        """Search for tools using semantic similarity"""
        if self.collection is None:
            return []

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=min(top_k, self.collection.count())
            )

            # Extract tool names and distances
            matches = []
            if results['ids'] and len(results['ids']) > 0:
                for i, tool_id in enumerate(results['ids'][0]):
                    tool_name = tool_id.replace("tool_", "")
                    # ChromaDB returns L2 distance, convert to similarity (0-1)
                    distance = results['distances'][0][i] if results['distances'] else 0
                    similarity = max(0, 1 - (distance / 2))  # Normalize

                    if similarity >= min_similarity:
                        matches.append((tool_name, similarity))

            logger.debug(f"[RAG] Found {len(matches)} tools for query: {query[:50]}...")
            return matches
        except Exception as e:
            logger.error(f"[RAG] Search failed: {e}")
            return []

    def rebuild_index(self, tools: List[ToolDefinition]):
        """Rebuild entire index"""
        if self.collection is None:
            return

        try:
            # Clear existing
            self.collection.delete(where={})
            self._embedding_cache.clear()

            # Re-index all tools
            for tool in tools:
                self.index_tool(tool)

            logger.info(f"[RAG] Rebuilt index with {len(tools)} tools")
        except Exception as e:
            logger.error(f"[RAG] Failed to rebuild index: {e}")


class ToolSearchManager:
    """
    Manages tool discovery with RAG-based semantic search.

    Key improvements over keyword search:
    1. Semantic understanding - finds tools by meaning, not just keywords
    2. Multi-signal relevance - combines semantic, usage, and success signals
    3. Efficient context - only loads top-K relevant tools
    4. Caching - recent queries cached for instant retrieval
    5. Skill integration - combines tools and skills for unified search
    """

    # Tools that should NEVER be deferred (always available)
    CRITICAL_TOOLS = {
        'playwright_navigate',
        'playwright_click',
        'playwright_fill',
        'playwright_snapshot',
        'playwright_get_markdown',
    }

    def __init__(self, config: Optional[RAGConfig] = None, skill_library=None):
        self.config = config or RAGConfig()
        self.skill_library = skill_library

        self.all_tools: Dict[str, ToolDefinition] = {}
        self.active_tools: Set[str] = set()

        # RAG components
        self.embedder = ToolEmbedder()
        self.query_cache = QueryCache(
            max_size=self.config.cache_max_size,
            ttl_seconds=self.config.cache_ttl_seconds
        )

        # Fallback to keyword search if ChromaDB unavailable
        self.search_index: Dict[str, Set[str]] = {}  # keyword -> tool names

    def register_tool(self, name: str, description: str,
                     parameters: Dict, category: str = "general",
                     defer_loading: bool = True):
        """Register a tool, optionally deferring its loading."""

        # Critical tools are never deferred
        if name in self.CRITICAL_TOOLS:
            defer_loading = False

        tool = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            category=category,
            defer_loading=defer_loading
        )

        self.all_tools[name] = tool

        # If not deferred, activate immediately
        if not defer_loading:
            self.active_tools.add(name)

        # Index for both RAG and keyword search
        self._index_tool(tool)

        logger.debug(f"[TOOL-SEARCH] Registered {name} (deferred={defer_loading})")

    def _index_tool(self, tool: ToolDefinition):
        """Index tool for both vector and keyword search."""
        # Vector embedding (RAG)
        self.embedder.index_tool(tool)

        # Keyword index (fallback)
        text = f"{tool.name} {tool.description}".lower()
        words = re.findall(r'\b\w+\b', text)
        for word in words:
            if len(word) >= 3:
                if word not in self.search_index:
                    self.search_index[word] = set()
                self.search_index[word].add(tool.name)

    def get_active_tools(self) -> List[Dict]:
        """Get only active (non-deferred) tool definitions."""
        active = []
        for name in self.active_tools:
            if name in self.all_tools:
                tool = self.all_tools[name]
                active.append(self._format_tool(tool))

        logger.info(f"[TOOL-SEARCH] Returning {len(active)}/{len(self.all_tools)} active tools")
        return active

    def _format_tool(self, tool: ToolDefinition, include_full_params: bool = None) -> Dict:
        """Format tool for context, optionally optimizing size"""
        if include_full_params is None:
            include_full_params = self.config.include_full_params

        # Truncate description if too long
        description = tool.description
        if len(description) > self.config.max_description_length:
            description = description[:self.config.max_description_length] + "..."

        result = {
            "name": tool.name,
            "description": description,
        }

        if include_full_params:
            result["parameters"] = tool.parameters
        else:
            # Only include parameter names, not full schemas
            param_names = list(tool.parameters.get("properties", {}).keys())
            result["parameters"] = {"required": param_names[:3]}  # Top 3 params

        return result

    def search(self, query: str, max_results: int = 5, category: str = None) -> List[ToolSearchResult]:
        """
        Search for tools using RAG (semantic search) with multi-signal relevance.

        Falls back to keyword search if ChromaDB unavailable.
        """
        # Check cache first
        query_hash = hashlib.md5(f"{query}:{max_results}:{category}".encode()).hexdigest()
        if self.config.cache_enabled:
            cached = self.query_cache.get(query_hash)
            if cached is not None:
                logger.info(f"[RAG] Cache hit for query: {query[:50]}...")
                return cached[:max_results]

        # Try RAG search first
        if CHROMADB_AVAILABLE and self.embedder.collection is not None:
            results = self._search_rag(query, max_results, category)
        else:
            # Fallback to keyword search
            results = self._search_keyword(query, max_results, category)

        # Cache results
        if self.config.cache_enabled:
            self.query_cache.set(query_hash, results)

        return results

    def _search_rag(self, query: str, max_results: int, category: str = None) -> List[ToolSearchResult]:
        """RAG-based semantic search"""
        # Get semantic matches
        semantic_matches = self.embedder.search(
            query,
            top_k=max_results * 2,  # Get more candidates for filtering
            min_similarity=self.config.rag_similarity_threshold
        )

        # Score and rank candidates
        results = []
        for tool_name, semantic_score in semantic_matches:
            if tool_name not in self.all_tools:
                continue

            tool = self.all_tools[tool_name]

            # Skip if already active or wrong category
            if tool_name in self.active_tools:
                continue
            if category and tool.category != category:
                continue

            # Multi-signal relevance scoring
            usage_score = self._compute_usage_score(tool)
            success_score = tool.get_success_rate()

            # Weighted combination
            total_score = (
                semantic_score * self.config.weight_semantic +
                usage_score * self.config.weight_usage +
                success_score * self.config.weight_success
            )

            match_reason = (
                f"Semantic: {semantic_score:.1%}, "
                f"Usage: {usage_score:.1%}, "
                f"Success: {success_score:.1%}"
            )

            results.append(ToolSearchResult(
                tool=tool,
                relevance_score=total_score,
                semantic_score=semantic_score,
                usage_score=usage_score,
                success_score=success_score,
                match_reason=match_reason
            ))

        # Sort by total relevance
        results.sort(key=lambda x: x.relevance_score, reverse=True)

        logger.info(f"[RAG] Found {len(results)} tools for '{query[:50]}...'")
        return results[:max_results]

    def _search_keyword(self, query: str, max_results: int, category: str = None) -> List[ToolSearchResult]:
        """Fallback keyword-based search"""
        query_lower = query.lower()
        query_words = set(re.findall(r'\b\w+\b', query_lower))

        candidates: Dict[str, float] = {}

        # Keyword matching
        for word in query_words:
            if word in self.search_index:
                for tool_name in self.search_index[word]:
                    if tool_name not in self.active_tools:
                        if category and self.all_tools[tool_name].category != category:
                            continue
                        candidates[tool_name] = candidates.get(tool_name, 0) + 1

        # Score and rank
        results = []
        for tool_name, keyword_score in candidates.items():
            tool = self.all_tools[tool_name]

            # Fuzzy match on description
            desc_score = SequenceMatcher(
                None, query_lower, tool.description.lower()
            ).ratio()

            # Combined score
            total_score = (keyword_score / max(len(query_words), 1)) * 0.6 + desc_score * 0.4

            results.append(ToolSearchResult(
                tool=tool,
                relevance_score=total_score,
                semantic_score=desc_score,
                usage_score=self._compute_usage_score(tool),
                success_score=tool.get_success_rate(),
                match_reason=f"Matched {int(keyword_score)} keywords, {desc_score:.0%} description similarity"
            ))

        # Sort by relevance
        results.sort(key=lambda x: x.relevance_score, reverse=True)

        logger.info(f"[KEYWORD] Found {len(results)} tools for '{query[:50]}...'")
        return results[:max_results]

    def _compute_usage_score(self, tool: ToolDefinition) -> float:
        """Compute usage score (0-1) based on usage patterns"""
        if tool.usage_count == 0:
            return 0.5  # Neutral for new tools

        # Normalize usage count (log scale to handle large ranges)
        import math
        max_usage = max(t.usage_count for t in self.all_tools.values())
        if max_usage == 0:
            return 0.5

        normalized = math.log(tool.usage_count + 1) / math.log(max_usage + 1)
        return min(1.0, normalized)

    async def search_with_skills(self, query: str, max_results: int = 5) -> Dict[str, List]:
        """
        Search both tools and skills, returning unified results.

        Integration with Async Skill Library for comprehensive search.
        """
        # Search tools
        tool_results = self.search(query, max_results)

        # Search skills if available
        skill_results = []
        if self.skill_library is not None:
            try:
                from skill_library import SkillCategory
                skills = await self.skill_library.search_skills_async(
                    query=query,
                    limit=max_results,
                    use_cache=True
                )
                skill_results = skills
            except Exception as e:
                logger.warning(f"[TOOL-SEARCH] Skill search failed: {e}")

        return {
            "tools": [
                {
                    "name": r.tool.name,
                    "description": r.tool.description,
                    "relevance": f"{r.relevance_score:.0%}",
                    "reason": r.match_reason
                }
                for r in tool_results
            ],
            "skills": [
                {
                    "name": s.name,
                    "description": s.description,
                    "category": s.category.value if hasattr(s.category, 'value') else str(s.category),
                    "success_rate": f"{s.success_rate:.0%}"
                }
                for s in skill_results
            ]
        }

    def activate_tool(self, name: str) -> bool:
        """Activate a deferred tool."""
        if name in self.all_tools:
            self.active_tools.add(name)
            tool = self.all_tools[name]
            tool.usage_count += 1
            tool.last_used = time.time()
            logger.info(f"[TOOL-SEARCH] Activated tool: {name}")
            return True
        return False

    def record_tool_result(self, name: str, success: bool, execution_time: float = 0.0):
        """Record tool execution result for relevance scoring"""
        if name in self.all_tools:
            tool = self.all_tools[name]
            if success:
                tool.success_count += 1
            else:
                tool.failure_count += 1

            # Update average execution time
            if execution_time > 0:
                if tool.avg_execution_time == 0:
                    tool.avg_execution_time = execution_time
                else:
                    # Exponential moving average
                    tool.avg_execution_time = 0.9 * tool.avg_execution_time + 0.1 * execution_time

    def deactivate_tool(self, name: str) -> bool:
        """Deactivate a tool (return to deferred state)."""
        if name in self.active_tools and name not in self.CRITICAL_TOOLS:
            self.active_tools.discard(name)
            logger.info(f"[TOOL-SEARCH] Deactivated tool: {name}")
            return True
        return False

    def get_token_savings(self) -> Dict[str, int]:
        """Estimate token savings from RAG-based search."""
        TOKENS_PER_TOOL = 200

        total_tools = len(self.all_tools)
        active_tools = len(self.active_tools)
        deferred_tools = total_tools - active_tools

        tokens_if_all_loaded = total_tools * TOKENS_PER_TOOL
        tokens_with_deferral = active_tools * TOKENS_PER_TOOL

        return {
            "total_tools": total_tools,
            "active_tools": active_tools,
            "deferred_tools": deferred_tools,
            "tokens_without_deferral": tokens_if_all_loaded,
            "tokens_with_deferral": tokens_with_deferral,
            "tokens_saved": tokens_if_all_loaded - tokens_with_deferral,
            "savings_percent": (deferred_tools / total_tools * 100) if total_tools > 0 else 0,
            "rag_enabled": CHROMADB_AVAILABLE,
            "cache_size": len(self.query_cache._cache)
        }

    def create_search_tool(self) -> Dict:
        """
        Create the Tool Search tool itself.
        This is what the agent calls to discover more tools.
        """
        return {
            "name": "search_tools",
            "description": "Search for additional tools using semantic search. Describe what you want to do and this will find relevant tools based on meaning, not just keywords.",
            "parameters": {
                "query": {
                    "type": "string",
                    "description": "Natural language description of what you want to do, e.g. 'extract structured data from a table' or 'upload a file'"
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter (e.g. 'web', 'data', 'file')",
                    "optional": True
                }
            }
        }

    async def handle_search_tool(self, query: str, category: str = None) -> Dict:
        """Handle a search_tools call from the agent."""
        # Use RAG search with skill integration
        results = await self.search_with_skills(query, max_results=self.config.rag_top_k)

        tools_found = results["tools"]
        skills_found = results["skills"]

        if not tools_found and not skills_found:
            return {
                "found": False,
                "message": "No additional tools or skills found for that query. Try rephrasing or use available tools."
            }

        # Activate found tools
        activated_tools = []
        for tool_info in tools_found:
            self.activate_tool(tool_info["name"])
            activated_tools.append(tool_info)

        return {
            "found": True,
            "activated_tools": activated_tools,
            "available_skills": skills_found,
            "message": f"Found and activated {len(activated_tools)} tools. Found {len(skills_found)} relevant skills.",
            "rag_enabled": CHROMADB_AVAILABLE
        }

    def reset_to_critical(self):
        """Reset to only critical tools (for context reset)."""
        self.active_tools = set(self.CRITICAL_TOOLS)
        logger.info(f"[TOOL-SEARCH] Reset to {len(self.active_tools)} critical tools")

    def rebuild_index(self):
        """Rebuild RAG index for all tools"""
        self.embedder.rebuild_index(list(self.all_tools.values()))
        self.query_cache.invalidate()
        logger.info("[TOOL-SEARCH] Rebuilt RAG index and cleared cache")


# Global instance
_tool_search: Optional[ToolSearchManager] = None

def get_tool_search(config: Optional[RAGConfig] = None, skill_library=None) -> ToolSearchManager:
    """Get global tool search manager."""
    global _tool_search
    if _tool_search is None:
        _tool_search = ToolSearchManager(config, skill_library)
    return _tool_search

def reset_tool_search():
    """Reset global instance (for testing)"""
    global _tool_search
    _tool_search = None
