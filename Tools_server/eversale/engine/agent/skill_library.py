#!/usr/bin/env python3
"""
Voyager-Style Skill Library for Eversale (Async-Enhanced)

Implements a self-improving skill acquisition and retrieval system based on the
Voyager research paper, adapted for web automation tasks. Skills are learned
from successful executions, generalized, and retrieved using semantic search.

Key Features:
1. Automatic skill extraction from successful task executions
2. Vector-based semantic retrieval using ChromaDB
3. Skill composition for complex multi-step tasks
4. Self-verification and iterative refinement
5. Success/failure tracking and skill versioning
6. Category-based organization (navigation, extraction, forms, etc.)
7. Pre-built skills for common web automation patterns
8. ASYNC SUPPORT: Concurrent skill access from parallel agents
9. READ/WRITE LOCKING: Thread-safe concurrent operations
10. SKILL CACHING: LRU cache with TTL and invalidation
11. BATCH OPERATIONS: Concurrent skill addition and execution
12. OPTIMISTIC LOCKING: Version-based conflict detection
13. SKILL VERSIONING: Complete version history tracking
14. ASYNC TIMEOUTS: Prevent hanging skill executions

Architecture:
- SkillLibrary: Main orchestrator for skill management (async-enhanced)
- Skill: Individual skill with code, metadata, and metrics (async execute)
- SkillRetriever: Vector-based semantic search
- SkillComposer: Combines skills into complex workflows
- SkillValidator: Verifies skill correctness before adding
- SkillGenerator: Extracts and generalizes skills from executions
- AsyncRWLock: Read/Write lock for concurrent access
- SkillCache: LRU cache with TTL and pattern invalidation
- SkillVersion: Optimistic locking version tracker

Async API:
- add_skill_async(): Add skill with optimistic locking
- get_skill_async(): Cached skill retrieval
- search_skills_async(): Cached semantic search
- execute_skill_async(): Execute with timeout
- batch_add_skills(): Concurrent skill addition
- batch_execute_skills(): Concurrent execution with semaphore
- compose_skills_async(): Sequential workflow execution
- get_version(): Get current skill version
- get_version_history(): Get all skill versions

Backward Compatibility:
All original sync methods (add_skill, get_skill, search_skills, execute)
remain available for backward compatibility.

Target: 500+ skills, 90%+ retrieval accuracy, concurrent agent support
"""

import asyncio
import hashlib
import json
import re
import ast
import inspect
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Tuple, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict, Counter
from loguru import logger
import threading
import time
from contextlib import asynccontextmanager
from functools import wraps, lru_cache

# Smart ChromaDB loading - auto-detects available memory
import os
CHROMADB_AVAILABLE = False
chromadb = None  # Lazy import
_chromadb_check_done = False

def _check_available_memory() -> int:
    """Check available system memory in MB"""
    try:
        import psutil
        mem = psutil.virtual_memory()
        return mem.available // (1024 * 1024)
    except ImportError:
        pass

    # Fallback: read from /proc/meminfo on Linux
    try:
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    # Value is in kB
                    return int(line.split()[1]) // 1024
    except:
        pass

    # Default: assume low memory if we can't detect
    return 500

def _should_enable_chromadb() -> bool:
    """Smart detection of whether ChromaDB should be enabled"""
    # Manual override via environment variable
    env_setting = os.environ.get('EVERSALE_ENABLE_CHROMADB', '').lower()
    if env_setting == '1' or env_setting == 'true':
        return True
    if env_setting == '0' or env_setting == 'false':
        return False

    # Auto-detect based on available memory
    # ChromaDB + ONNX needs ~800MB minimum for embeddings
    available_mb = _check_available_memory()
    min_required_mb = 800

    if available_mb < min_required_mb:
        logger.debug(f"ChromaDB disabled: only {available_mb}MB available (need {min_required_mb}MB)")
        return False

    # Check if running in WSL with limited resources
    is_wsl = os.path.exists('/proc/sys/fs/binfmt_misc/WSLInterop') or 'microsoft' in os.uname().release.lower()
    if is_wsl and available_mb < 1500:
        # WSL often has memory pressure issues, be more conservative
        logger.debug(f"ChromaDB disabled: WSL with {available_mb}MB (need 1500MB in WSL)")
        return False

    return True

def _get_chromadb():
    """Lazy import chromadb with smart memory detection"""
    global chromadb, CHROMADB_AVAILABLE, _chromadb_check_done

    # Return cached result
    if _chromadb_check_done:
        return chromadb if CHROMADB_AVAILABLE else None

    _chromadb_check_done = True

    # Smart check if we should enable
    if not _should_enable_chromadb():
        CHROMADB_AVAILABLE = False
        return None

    # Try to import
    try:
        import chromadb as _chromadb
        chromadb = _chromadb
        CHROMADB_AVAILABLE = True
        logger.debug(f"ChromaDB loaded successfully (available memory: {_check_available_memory()}MB)")
        return chromadb
    except ImportError:
        logger.debug("ChromaDB not installed - using fallback search")
        CHROMADB_AVAILABLE = False
        return None
    except MemoryError:
        logger.warning("ChromaDB import failed: out of memory - using fallback search")
        CHROMADB_AVAILABLE = False
        return None
    except Exception as e:
        error_str = str(e).lower()
        if any(x in error_str for x in ['memory', 'alloc', 'oom', 'pthread']):
            logger.warning("ChromaDB import failed: memory issue - using fallback search")
        else:
            logger.warning(f"ChromaDB import failed: {e} - using fallback search")
        CHROMADB_AVAILABLE = False
        return None

# Storage directories
SKILLS_DIR = Path("memory/skills")
SKILLS_DIR.mkdir(parents=True, exist_ok=True)

SKILL_HISTORY_DIR = Path("memory/skills/history")
SKILL_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

SKILL_METRICS_FILE = Path("memory/skills/metrics.json")


class AsyncRWLock:
    """
    Async Read/Write lock for concurrent skill access.
    Multiple readers can access simultaneously, but writers get exclusive access.
    """
    def __init__(self):
        self._readers = 0
        self._writers = 0
        self._read_ready = asyncio.Condition()
        self._write_ready = asyncio.Condition()

    @asynccontextmanager
    async def read_lock(self):
        """Acquire read lock"""
        async with self._read_ready:
            while self._writers > 0:
                await self._read_ready.wait()
            self._readers += 1
        try:
            yield
        finally:
            async with self._read_ready:
                self._readers -= 1
                if self._readers == 0:
                    async with self._write_ready:
                        self._write_ready.notify_all()

    @asynccontextmanager
    async def write_lock(self):
        """Acquire write lock"""
        async with self._write_ready:
            while self._writers > 0 or self._readers > 0:
                await self._write_ready.wait()
            self._writers += 1
        try:
            yield
        finally:
            async with self._write_ready:
                self._writers -= 1
                self._write_ready.notify_all()
            async with self._read_ready:
                self._read_ready.notify_all()


class SkillCache:
    """
    LRU cache for skills with invalidation support.
    """
    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._access_order: List[str] = []
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Get item from cache"""
        async with self._lock:
            if key not in self._cache:
                return None

            value, timestamp = self._cache[key]

            # Check if expired
            if time.time() - timestamp > self.ttl_seconds:
                del self._cache[key]
                self._access_order.remove(key)
                return None

            # Update access order
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

            return value

    async def set(self, key: str, value: Any):
        """Set item in cache"""
        async with self._lock:
            # Evict oldest if at capacity
            if len(self._cache) >= self.max_size and key not in self._cache:
                oldest = self._access_order.pop(0)
                del self._cache[oldest]

            self._cache[key] = (value, time.time())

            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

    async def invalidate(self, key: str):
        """Invalidate cache entry"""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._access_order.remove(key)

    async def invalidate_pattern(self, pattern: str):
        """Invalidate all keys matching pattern"""
        async with self._lock:
            keys_to_remove = [k for k in self._cache.keys() if re.match(pattern, k)]
            for key in keys_to_remove:
                del self._cache[key]
                self._access_order.remove(key)

    async def clear(self):
        """Clear entire cache"""
        async with self._lock:
            self._cache.clear()
            self._access_order.clear()


class SkillVersion:
    """
    Tracks skill versions for optimistic locking and concurrent updates.
    """
    def __init__(self, skill_id: str, version: int, content_hash: str, timestamp: str):
        self.skill_id = skill_id
        self.version = version
        self.content_hash = content_hash
        self.timestamp = timestamp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "version": self.version,
            "content_hash": self.content_hash,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillVersion":
        return cls(**data)


class SkillCategory(Enum):
    """Categories for organizing skills"""
    NAVIGATION = "navigation"  # Login, search, pagination, scroll
    EXTRACTION = "extraction"  # Tables, lists, contacts, prices
    INTERACTION = "interaction"  # Forms, clicks, uploads, downloads
    VERIFICATION = "verification"  # Check success, validate data
    RECOVERY = "recovery"  # Dismiss popups, handle errors
    COMPOSITE = "composite"  # Multi-step workflows
    STEALTH = "stealth"  # Anti-detection measures
    ANALYSIS = "analysis"  # Data processing, comparison
    COMMUNICATION = "communication"  # Email, messages, notifications


class SkillStatus(Enum):
    """Skill lifecycle status"""
    DRAFT = "draft"  # Newly created, not validated
    ACTIVE = "active"  # Validated and available
    DEPRECATED = "deprecated"  # Replaced by newer version
    FAILED = "failed"  # Failed validation


@dataclass
class SkillMetrics:
    """Tracks skill performance over time"""
    total_uses: int = 0
    successes: int = 0
    failures: int = 0
    avg_execution_time: float = 0.0
    last_used: Optional[str] = None
    last_success: Optional[str] = None
    last_failure: Optional[str] = None
    failure_reasons: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self.total_uses == 0:
            return 0.0
        return self.successes / self.total_uses

    def record_use(self, success: bool, execution_time: float, error: str = ""):
        """Record a skill execution"""
        self.total_uses += 1
        if success:
            self.successes += 1
            self.last_success = datetime.now().isoformat()
        else:
            self.failures += 1
            self.last_failure = datetime.now().isoformat()
            if error:
                self.failure_reasons.append(error)
                # Keep only last 10 failure reasons
                self.failure_reasons = self.failure_reasons[-10:]

        self.last_used = datetime.now().isoformat()

        # Update moving average for execution time
        alpha = 0.3  # Weight for new observation
        self.avg_execution_time = (
            alpha * execution_time + (1 - alpha) * self.avg_execution_time
            if self.avg_execution_time > 0 else execution_time
        )


@dataclass
class Skill:
    """
    A reusable skill that encapsulates a web automation pattern
    """
    skill_id: str
    name: str
    description: str
    category: SkillCategory

    # Executable code
    code: str  # Python function as string
    parameters: Dict[str, Any] = field(default_factory=dict)
    returns: Optional[str] = None

    # Metadata
    version: int = 1
    status: SkillStatus = SkillStatus.DRAFT
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    author: str = "system"  # "system", "user", or "learned"

    # Dependencies
    required_tools: List[str] = field(default_factory=list)  # playwright_navigate, etc.
    tags: List[str] = field(default_factory=list)

    # Metrics
    metrics: SkillMetrics = field(default_factory=SkillMetrics)

    # Learning metadata
    source_task: Optional[str] = None  # Task ID this was learned from
    generalization_level: int = 0  # 0=specific, 5=highly general

    # Decision logic metadata - NEW
    decision_metadata: Dict[str, Any] = field(default_factory=dict)  # Stores decision points, conditions, branches

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        data = asdict(self)
        data["category"] = self.category.value
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Skill":
        """Create skill from dictionary"""
        data = data.copy()
        data["category"] = SkillCategory(data["category"])
        data["status"] = SkillStatus(data["status"])
        if "metrics" in data and isinstance(data["metrics"], dict):
            data["metrics"] = SkillMetrics(**data["metrics"])
        return cls(**data)

    def get_hash(self) -> str:
        """Get hash of skill code for deduplication"""
        return hashlib.md5(self.code.encode()).hexdigest()

    def execute(self, context: Dict[str, Any]) -> Any:
        """
        Execute the skill with given context (sync version for backward compatibility)

        Args:
            context: Dictionary with parameters needed by the skill

        Returns:
            Result of skill execution
        """
        # Define safe builtins - only allow essential functions
        SAFE_BUILTINS = {
            'print': print,
            'len': len,
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'list': list,
            'dict': dict,
            'tuple': tuple,
            'set': set,
            'range': range,
            'enumerate': enumerate,
            'zip': zip,
            'map': map,
            'filter': filter,
            'sorted': sorted,
            'min': min,
            'max': max,
            'sum': sum,
            'any': any,
            'all': all,
            'abs': abs,
            'round': round,
            'isinstance': isinstance,
            'hasattr': hasattr,
            'getattr': getattr,
            'True': True,
            'False': False,
            'None': None,
        }

        # Create restricted globals dict that excludes dangerous modules
        restricted_globals = {
            '__builtins__': SAFE_BUILTINS,
            '__name__': '__skill__',
            '__doc__': None,
        }

        # Create namespace with context variables and 'context' itself
        namespace = {**restricted_globals, **context, "context": context}

        try:
            # Log what code is being executed (for security auditing)
            logger.debug(f"Executing skill '{self.name}' (ID: {self.skill_id}, Category: {self.category.value})")
            logger.trace(f"Skill code preview: {self.code[:200]}...")

            # Execute the skill code in sandboxed environment
            exec(self.code, namespace)

            # Return the result (skill should set a 'result' variable)
            result = namespace.get("result")
            logger.debug(f"Skill '{self.name}' executed successfully, result type: {type(result)}")
            return result

        except NameError as e:
            # Catch attempts to use forbidden builtins/modules
            logger.error(f"Skill '{self.name}' attempted to use forbidden function/module: {e}")
            raise ValueError(f"Skill execution blocked: forbidden function or module usage - {e}")
        except Exception as e:
            # Catch any other execution errors
            logger.error(f"Skill '{self.name}' execution failed: {type(e).__name__}: {e}")
            raise RuntimeError(f"Skill execution failed: {type(e).__name__}: {e}") from e

    async def execute_async(self, context: Dict[str, Any], timeout: Optional[float] = None) -> Any:
        """
        Execute the skill asynchronously with timeout support

        Args:
            context: Dictionary with parameters needed by the skill
            timeout: Optional timeout in seconds

        Returns:
            Result of skill execution

        Raises:
            asyncio.TimeoutError: If execution exceeds timeout
        """
        # Define safe builtins - only allow essential functions
        SAFE_BUILTINS = {
            'print': print,
            'len': len,
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'list': list,
            'dict': dict,
            'tuple': tuple,
            'set': set,
            'range': range,
            'enumerate': enumerate,
            'zip': zip,
            'map': map,
            'filter': filter,
            'sorted': sorted,
            'min': min,
            'max': max,
            'sum': sum,
            'any': any,
            'all': all,
            'abs': abs,
            'round': round,
            'isinstance': isinstance,
            'hasattr': hasattr,
            'getattr': getattr,
            'True': True,
            'False': False,
            'None': None,
            'asyncio': asyncio,  # Allow asyncio for async skills
        }

        # Create restricted globals dict that excludes dangerous modules
        restricted_globals = {
            '__builtins__': SAFE_BUILTINS,
            '__name__': '__skill__',
            '__doc__': None,
        }

        # Create namespace with context variables and 'context' itself
        namespace = {**restricted_globals, **context, "context": context}

        async def _execute():
            try:
                # Log what code is being executed (for security auditing)
                logger.debug(f"Executing async skill '{self.name}' (ID: {self.skill_id})")
                logger.trace(f"Skill code preview: {self.code[:200]}...")

                # Execute the skill code in sandboxed environment
                exec(self.code, namespace)

                # Check if the skill defined an async function
                if 'execute_skill' in namespace:
                    func = namespace['execute_skill']
                    if asyncio.iscoroutinefunction(func):
                        result = await func(context)
                    else:
                        result = func(context)
                else:
                    # Return the result (skill should set a 'result' variable)
                    result = namespace.get("result")

                logger.debug(f"Async skill '{self.name}' executed successfully")
                return result

            except NameError as e:
                logger.error(f"Skill '{self.name}' attempted to use forbidden function/module: {e}")
                raise ValueError(f"Skill execution blocked: forbidden function or module usage - {e}")
            except Exception as e:
                logger.error(f"Skill '{self.name}' async execution failed: {type(e).__name__}: {e}")
                raise RuntimeError(f"Skill execution failed: {type(e).__name__}: {e}") from e

        # Execute with optional timeout
        if timeout:
            return await asyncio.wait_for(_execute(), timeout=timeout)
        else:
            return await _execute()


class SkillRetriever:
    """
    Semantic retrieval of skills using vector embeddings
    """

    def __init__(self, collection_name: str = "skills"):
        self.collection_name = collection_name
        self.client = None
        self.collection = None

        # Use lazy import - only load chromadb if explicitly enabled
        chroma = _get_chromadb()
        if chroma is not None:
            try:
                # Initialize ChromaDB using new API
                chroma_dir = str(SKILLS_DIR / "chroma")
                self.client = chroma.PersistentClient(path=chroma_dir)

                # Get or create collection
                self.collection = self.client.get_or_create_collection(
                    name=collection_name,
                    metadata={"description": "Skill embeddings for semantic retrieval"}
                )
                logger.info(f"Initialized ChromaDB collection '{collection_name}'")
            except MemoryError:
                logger.warning("ChromaDB initialization failed due to OOM - using fallback search")
                self.client = None
                self.collection = None
            except Exception as e:
                error_str = str(e).lower()
                if any(indicator in error_str for indicator in [
                    "cannot allocate memory", "pthread_create failed",
                    "error code: 12", "oom", "bad_alloc"
                ]):
                    logger.warning("ChromaDB initialization failed due to OOM - using fallback search")
                else:
                    logger.error(f"Failed to initialize ChromaDB: {e}")
                self.client = None
                self.collection = None

    def add_skill(self, skill: Skill):
        """Add skill to vector database"""
        if not self.collection:
            return

        # Check memory before operation
        available_mb = _check_available_memory()
        if available_mb < 300:
            logger.warning(f"Low memory ({available_mb}MB) - skipping vector DB add")
            return

        try:
            # Create searchable text from skill
            search_text = self._create_search_text(skill)

            # Add to collection
            self.collection.add(
                documents=[search_text],
                metadatas=[{
                    "skill_id": skill.skill_id,
                    "name": skill.name,
                    "category": skill.category.value,
                    "status": skill.status.value,
                    "success_rate": skill.metrics.success_rate,
                    "total_uses": skill.metrics.total_uses,
                }],
                ids=[skill.skill_id]
            )
            logger.debug(f"Added skill {skill.skill_id} to vector database")
        except MemoryError:
            # OOM - disable ChromaDB for this session
            logger.warning("ChromaDB OOM - disabling vector search for this session")
            self._disable_chromadb()
        except Exception as e:
            error_str = str(e).lower()
            # Check for various OOM indicators
            if any(indicator in error_str for indicator in [
                "bad_alloc", "abort", "cannot allocate memory",
                "pthread_create failed", "error code: 12", "oom"
            ]):
                # ONNX/threading OOM - disable ChromaDB for this session
                logger.warning("ChromaDB OOM (ONNX/threading) - disabling vector search for this session")
                self._disable_chromadb()
            else:
                logger.error(f"Failed to add skill to vector DB: {e}")

    def _disable_chromadb(self):
        """Disable ChromaDB and clean up resources"""
        global CHROMADB_AVAILABLE
        self.collection = None
        self.client = None
        CHROMADB_AVAILABLE = False
        logger.info("ChromaDB disabled - falling back to keyword search")

    def remove_skill(self, skill_id: str):
        """Remove skill from vector database"""
        if not self.collection:
            return

        try:
            self.collection.delete(ids=[skill_id])
            logger.debug(f"Removed skill {skill_id} from vector database")
        except Exception as e:
            logger.error(f"Failed to remove skill from vector DB: {e}")

    def search(
        self,
        query: str,
        category: Optional[SkillCategory] = None,
        min_success_rate: float = 0.0,
        limit: int = 10
    ) -> List[Tuple[str, float]]:
        """
        Search for skills matching query

        Args:
            query: Natural language description of what you need
            category: Optional category filter
            min_success_rate: Minimum success rate (0.0-1.0)
            limit: Maximum number of results

        Returns:
            List of (skill_id, relevance_score) tuples
        """
        if not self.collection:
            return []

        try:
            # Build where clause for filtering
            where = {}
            if category:
                where["category"] = category.value
            if min_success_rate > 0:
                where["success_rate"] = {"$gte": min_success_rate}

            # Search
            results = self.collection.query(
                query_texts=[query],
                n_results=limit,
                where=where if where else None
            )

            # Extract skill IDs and scores
            if results and results["ids"] and results["distances"]:
                skill_ids = results["ids"][0]
                # Convert distances to similarity scores (lower distance = higher similarity)
                scores = [1.0 / (1.0 + d) for d in results["distances"][0]]
                return list(zip(skill_ids, scores))

            return []
        except Exception as e:
            logger.error(f"Failed to search skills: {e}")
            return []

    @lru_cache(maxsize=500)
    def _create_search_text_cached(self, skill_id: str, name: str, description: str,
                                    category: str, tags: tuple, params: tuple) -> str:
        """Create searchable text from skill components (cached)"""
        parts = [
            name,
            description,
            f"Category: {category}",
            f"Tags: {', '.join(tags)}",
        ]

        # Add parameter names for better matching
        if params:
            parts.append(f"Parameters: {', '.join(params)}")

        return " | ".join(parts)

    def _create_search_text(self, skill: Skill) -> str:
        """Create searchable text from skill"""
        # Convert mutable types to hashable for caching
        tags_tuple = tuple(skill.tags) if skill.tags else ()
        params_tuple = tuple(skill.parameters.keys()) if skill.parameters else ()

        return self._create_search_text_cached(
            skill.skill_id,
            skill.name,
            skill.description,
            skill.category.value,
            tags_tuple,
            params_tuple
        )


class SkillValidator:
    """
    Validates skills before adding to library
    """

    @staticmethod
    def validate_skill(skill: Skill) -> Tuple[bool, List[str]]:
        """
        Validate a skill

        Returns:
            (is_valid, list_of_errors)
        """
        errors = []

        # Check required fields
        if not skill.name:
            errors.append("Skill name is required")
        if not skill.description:
            errors.append("Skill description is required")
        if not skill.code:
            errors.append("Skill code is required")

        # Validate code syntax
        try:
            ast.parse(skill.code)
        except SyntaxError as e:
            errors.append(f"Syntax error in skill code: {e}")

        # Check that code defines a function or contains executable logic
        if "def " not in skill.code and "result =" not in skill.code:
            errors.append("Skill code must define a function or set a result variable")

        # Validate required tools are known
        known_tools = {
            "playwright_navigate", "playwright_click", "playwright_fill",
            "playwright_snapshot", "playwright_screenshot", "playwright_get_text",
            "playwright_extract_fb_ads", "playwright_extract_reddit",
            "playwright_extract_page_fast", "playwright_batch_extract",
            "playwright_find_contacts", "playwright_evaluate"
        }

        for tool in skill.required_tools:
            if tool not in known_tools:
                errors.append(f"Unknown required tool: {tool}")

        # Check for dangerous operations
        dangerous_patterns = [
            r"import\s+os",
            r"import\s+sys",
            r"eval\(",
            r"exec\(",
            r"__import__",
            r"subprocess",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, skill.code):
                errors.append(f"Skill contains potentially dangerous operation: {pattern}")

        return len(errors) == 0, errors

    @staticmethod
    def self_verify_skill(skill: Skill, test_contexts: List[Dict[str, Any]]) -> bool:
        """
        Self-verify skill by running test cases

        Args:
            skill: Skill to verify
            test_contexts: List of test contexts to run skill with

        Returns:
            True if all tests pass
        """
        try:
            for context in test_contexts:
                result = skill.execute(context)
                if result is None:
                    return False
            return True
        except Exception as e:
            logger.debug(f"Skill self-verification failed: {e}")
            return False


class SkillGenerator:
    """
    Extracts and generalizes skills from successful task executions
    """

    @staticmethod
    def extract_from_execution(
        task_description: str,
        actions: List[Dict[str, Any]],
        result: Any,
        category: SkillCategory
    ) -> Optional[Skill]:
        """
        Extract a skill from a successful execution with complete decision logic.

        Args:
            task_description: What the task was trying to do
            actions: List of actions that were executed (with decision/error metadata)
            result: Result of the execution
            category: Skill category

        Returns:
            Extracted skill or None if extraction fails

        Note:
            Actions should include metadata for decision logic:
            - decision_context: Dict with 'reason', 'description' for conditional actions
            - error_context: Dict with 'recovery_action' for error handling
            - is_conditional: Boolean indicating if this is a decision point
            - is_recovery: Boolean indicating if this is a recovery action
            - condition: String with the conditional expression
            - else_action: String describing alternative path
        """
        if not actions:
            return None

        try:
            # Enrich actions with inferred decision logic if not already present
            enriched_actions = SkillGenerator._enrich_actions_with_logic(actions)

            # Generate skill name from task description
            name = SkillGenerator._generate_skill_name(task_description)

            # Generate skill ID
            skill_id = f"skill_{hashlib.md5(name.encode()).hexdigest()[:12]}"

            # Generate code from actions (now with decision logic)
            code = SkillGenerator._generate_code(enriched_actions)

            # Extract parameters (including decision parameters)
            parameters = SkillGenerator._extract_parameters(enriched_actions)

            # Extract required tools
            required_tools = SkillGenerator._extract_required_tools(enriched_actions)

            # Generate tags (including decision-related tags)
            tags = SkillGenerator._generate_tags(task_description, enriched_actions)

            # Extract decision metadata for storage
            decision_metadata = SkillGenerator._extract_decision_metadata(enriched_actions)

            # Create skill
            skill = Skill(
                skill_id=skill_id,
                name=name,
                description=task_description,
                category=category,
                code=code,
                parameters=parameters,
                required_tools=required_tools,
                tags=tags,
                author="learned",
                status=SkillStatus.DRAFT,
                decision_metadata=decision_metadata
            )

            return skill
        except Exception as e:
            logger.error(f"Failed to extract skill: {e}")
            return None

    @staticmethod
    def _extract_decision_metadata(actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract and structure decision logic metadata from enriched actions.

        Returns a structured representation of:
        - Decision points: What choices were made and when
        - Error handling strategies: How errors are handled
        - Conditional branches: Alternative execution paths
        - Recovery patterns: How to recover from failures

        This metadata helps when reusing the skill in different contexts.
        """
        metadata = {
            "decision_points": [],
            "error_handling": [],
            "conditional_branches": [],
            "recovery_patterns": [],
            "execution_flow": "sequential"  # or "conditional", "parallel"
        }

        has_conditionals = False
        has_recovery = False

        for i, action in enumerate(actions):
            # Capture decision points
            if action.get("is_conditional"):
                has_conditionals = True
                decision_point = {
                    "step": i,
                    "condition": action.get("condition", ""),
                    "tool": action.get("tool", ""),
                    "context": action.get("decision_context", {}),
                    "else_action": action.get("else_action")
                }
                metadata["decision_points"].append(decision_point)

                # Also add to conditional branches
                branch = {
                    "step": i,
                    "condition": action.get("condition", ""),
                    "primary_action": action.get("tool", ""),
                    "alternative_action": action.get("else_action")
                }
                metadata["conditional_branches"].append(branch)

            # Capture error handling
            if action.get("error_context"):
                error_handling = {
                    "step": i,
                    "tool": action.get("tool", ""),
                    "recovery_action": action.get("error_context", {}).get("recovery_action", ""),
                    "strategy": "try-except with recovery"
                }
                metadata["error_handling"].append(error_handling)

            # Capture recovery patterns
            if action.get("is_recovery"):
                has_recovery = True
                recovery = {
                    "step": i,
                    "tool": action.get("tool", ""),
                    "trigger": "error or unexpected state",
                    "action": action.get("error_context", {}).get("recovery_action", ""),
                    "continue_on_failure": True
                }
                metadata["recovery_patterns"].append(recovery)

        # Determine execution flow type
        if has_conditionals and has_recovery:
            metadata["execution_flow"] = "conditional-with-recovery"
        elif has_conditionals:
            metadata["execution_flow"] = "conditional"
        elif has_recovery:
            metadata["execution_flow"] = "sequential-with-recovery"

        # Add summary statistics
        metadata["summary"] = {
            "total_steps": len(actions),
            "decision_points_count": len(metadata["decision_points"]),
            "error_handlers_count": len(metadata["error_handling"]),
            "recovery_patterns_count": len(metadata["recovery_patterns"]),
            "has_conditionals": has_conditionals,
            "has_error_handling": len(metadata["error_handling"]) > 0,
            "has_recovery": has_recovery
        }

        return metadata

    @staticmethod
    def _enrich_actions_with_logic(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enrich actions with inferred decision logic and error handling patterns.

        Analyzes action sequences to detect:
        - Conditional patterns (actions that might have been choices)
        - Error recovery patterns (retries, alternatives)
        - Context-dependent decisions

        Args:
            actions: Raw action list

        Returns:
            Enriched actions with decision/error metadata
        """
        enriched = []

        for i, action in enumerate(actions):
            # Create a copy to avoid modifying original
            enriched_action = action.copy()

            # Detect conditional patterns
            tool = action.get("tool", "")
            args = action.get("arguments", {})

            # Pattern 1: Multiple similar tools suggest a choice was made
            if i > 0:
                prev_tool = actions[i-1].get("tool", "")
                if tool == prev_tool:
                    enriched_action["decision_context"] = {
                        "reason": "repeated_tool",
                        "description": f"Chose to repeat {tool}, possibly after checking a condition"
                    }

            # Pattern 2: Recovery tools (dismiss, close, retry)
            recovery_keywords = ["dismiss", "close", "retry", "cancel", "skip"]
            if any(keyword in tool.lower() for keyword in recovery_keywords):
                enriched_action["is_recovery"] = True
                enriched_action["error_context"] = {
                    "recovery_action": f"Handle popup/modal/error using {tool}"
                }

            # Pattern 3: Navigation after interaction suggests verification
            if "navigate" in tool.lower() and i > 0:
                prev_tool = actions[i-1].get("tool", "")
                if "click" in prev_tool.lower() or "fill" in prev_tool.lower():
                    enriched_action["decision_context"] = {
                        "reason": "verification_step",
                        "description": "Navigate to verify previous action succeeded"
                    }

            # Pattern 4: Extract after navigation suggests conditional extraction
            if "extract" in tool.lower() and i > 0:
                prev_tool = actions[i-1].get("tool", "")
                if "navigate" in prev_tool.lower():
                    enriched_action["is_conditional"] = True
                    enriched_action["condition"] = "context.get('should_extract', True)"
                    enriched_action["decision_context"] = {
                        "reason": "conditional_extraction",
                        "description": "Extract data if available on page"
                    }

            # Pattern 5: Multiple clicks/fills in sequence suggest form filling with validation
            interaction_tools = ["click", "fill", "select"]
            if any(kw in tool.lower() for kw in interaction_tools):
                # Count consecutive interaction actions
                consecutive_interactions = 1
                for j in range(i+1, min(i+5, len(actions))):
                    next_tool = actions[j].get("tool", "")
                    if any(kw in next_tool.lower() for kw in interaction_tools):
                        consecutive_interactions += 1
                    else:
                        break

                if consecutive_interactions >= 3:
                    enriched_action["decision_context"] = {
                        "reason": "form_interaction",
                        "description": f"Part of {consecutive_interactions}-step interaction sequence"
                    }

            # Pattern 6: Detect potential error handling from action metadata
            if "error" in str(action).lower() or "exception" in str(action).lower():
                enriched_action["error_context"] = {
                    "recovery_action": "Handle error condition"
                }

            # Pattern 7: Wait/sleep actions suggest waiting for conditions
            if "wait" in tool.lower() or "sleep" in tool.lower():
                enriched_action["is_conditional"] = True
                enriched_action["condition"] = "context.get('wait_for_element', True)"
                enriched_action["decision_context"] = {
                    "reason": "wait_condition",
                    "description": "Wait for page state or element"
                }

            enriched.append(enriched_action)

        return enriched

    @staticmethod
    def _generate_skill_name(description: str) -> str:
        """Generate a concise skill name from description"""
        # Take first sentence and simplify
        first_sentence = description.split(".")[0].strip()

        # Remove common prefixes
        prefixes = ["please", "can you", "i want to", "i need to", "help me"]
        lower = first_sentence.lower()
        for prefix in prefixes:
            if lower.startswith(prefix):
                first_sentence = first_sentence[len(prefix):].strip()

        # Capitalize and truncate
        name = first_sentence[:80]
        return name[0].upper() + name[1:] if name else "Unnamed Skill"

    @staticmethod
    def _generate_code(actions: List[Dict[str, Any]]) -> str:
        """
        Generate Python code from action sequence with decision logic and error handling.

        Captures:
        - Conditional logic (if/else decisions)
        - Error handling patterns (try/except)
        - Context-dependent choices
        - Recovery steps
        """
        lines = [
            "# Auto-generated skill with decision logic and error handling",
            "async def execute_skill(context):",
            "    # Initialize result tracking",
            "    results = []",
            "    errors = []",
            "    recovery_attempted = False",
            "",
        ]

        for i, action in enumerate(actions):
            tool = action.get("tool", "unknown")
            args = action.get("arguments", {})

            # Extract metadata about decision logic
            decision_context = action.get("decision_context", {})
            error_context = action.get("error_context", {})
            is_conditional = action.get("is_conditional", False)
            is_recovery = action.get("is_recovery", False)
            condition = action.get("condition")

            # Add decision point documentation
            if decision_context:
                lines.append(f"    # Decision point {i}: {decision_context.get('reason', 'conditional action')}")
                lines.append(f"    # Context: {decision_context.get('description', 'N/A')}")

            # Add conditional wrapper if this is a decision point
            if is_conditional and condition:
                lines.append(f"    # Conditional: {condition}")
                lines.append(f"    if {condition}:")
                indent = "        "
            elif is_recovery:
                lines.append(f"    # Recovery action {i}")
                indent = "        "
            else:
                indent = "    "

            # Generate function call with error handling
            if tool.startswith("playwright_"):
                # Format arguments
                arg_strs = []
                for key, value in args.items():
                    if isinstance(value, str):
                        # Check if value is a parameter reference
                        if value.startswith("{") and value.endswith("}"):
                            param_name = value[1:-1]
                            arg_strs.append(f"{key}=context.get('{param_name}')")
                        else:
                            arg_strs.append(f"{key}='{value}'")
                    else:
                        arg_strs.append(f"{key}={value}")

                args_str = ", ".join(arg_strs)

                # Wrap in try/except to capture error handling patterns
                lines.append(f"{indent}try:")
                lines.append(f"{indent}    result_{i} = await {tool}({args_str})")
                lines.append(f"{indent}    results.append({{'step': {i}, 'tool': '{tool}', 'success': True, 'result': result_{i}}})")

                # Add error handling with recovery logic
                lines.append(f"{indent}except Exception as e:")
                lines.append(f"{indent}    error_info = {{'step': {i}, 'tool': '{tool}', 'error': str(e), 'args': {args}}}")
                lines.append(f"{indent}    errors.append(error_info)")

                # Check if there's a known recovery pattern
                if error_context or is_recovery:
                    recovery_action = error_context.get("recovery_action") if error_context else None
                    lines.append(f"{indent}    # Attempt recovery")
                    lines.append(f"{indent}    recovery_attempted = True")
                    if recovery_action:
                        lines.append(f"{indent}    # Recovery strategy: {recovery_action}")
                    lines.append(f"{indent}    result_{i} = None")
                else:
                    lines.append(f"{indent}    # No recovery available, continue with caution")
                    lines.append(f"{indent}    result_{i} = None")

                lines.append("")

            # Close conditional blocks
            if is_conditional and condition:
                else_action = action.get("else_action")
                if else_action:
                    lines.append("    else:")
                    lines.append(f"        # Alternative path: {else_action}")
                    lines.append("        pass")

        # Add result aggregation with error awareness
        lines.append("    # Aggregate results with decision context")
        lines.append("    result = {")
        lines.append("        'success': len(errors) == 0,")
        lines.append("        'steps_completed': len(results),")
        lines.append("        'total_steps': len([r for r in results]),")
        if actions:
            lines.append(f"        'final_result': result_{len(actions)-1} if {len(actions)-1} < len(results) else None,")
        else:
            lines.append("        'final_result': None,")
        lines.append("        'all_results': results,")
        lines.append("        'errors': errors,")
        lines.append("        'recovery_attempted': recovery_attempted,")
        lines.append("        'decision_points': [r for r in results if 'decision' in str(r)]")
        lines.append("    }")
        lines.append("    return result")

        return "\n".join(lines)

    @staticmethod
    def _extract_parameters(actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract parameters that should be configurable, including decision parameters.

        Includes:
        - Standard action parameters (URLs, selectors, etc.)
        - Decision control parameters (enable/disable branches)
        - Error handling parameters (retry counts, timeouts)
        """
        parameters = {}

        for action in actions:
            args = action.get("arguments", {})

            # Extract standard parameters
            for key, value in args.items():
                # Values that look like they should be parameters
                if isinstance(value, str):
                    # URLs, selectors, search terms, etc.
                    if any(pattern in key.lower() for pattern in ["url", "selector", "query", "text", "email"]):
                        parameters[key] = {
                            "type": "string",
                            "description": f"The {key} to use",
                            "default": value
                        }

            # Extract decision-related parameters
            if action.get("is_conditional"):
                condition = action.get("condition", "")
                # Extract parameter names from condition
                if "context.get(" in condition:
                    import re
                    param_matches = re.findall(r"context\.get\('(\w+)'", condition)
                    for param_name in param_matches:
                        if param_name not in parameters:
                            parameters[param_name] = {
                                "type": "boolean",
                                "description": f"Control parameter for decision: {param_name}",
                                "default": True
                            }

            # Extract error handling parameters
            if action.get("error_context"):
                error_context = action.get("error_context", {})
                recovery_action = error_context.get("recovery_action", "")

                # Add retry parameter if recovery is present
                if "retry" in recovery_action.lower():
                    parameters["max_retries"] = {
                        "type": "integer",
                        "description": "Maximum number of retry attempts",
                        "default": 3
                    }

                # Add timeout parameter for wait actions
                if "timeout" in recovery_action.lower() or "wait" in recovery_action.lower():
                    parameters["timeout_seconds"] = {
                        "type": "integer",
                        "description": "Timeout in seconds for operations",
                        "default": 30
                    }

        return parameters

    @staticmethod
    def _extract_required_tools(actions: List[Dict[str, Any]]) -> List[str]:
        """Extract list of required tools"""
        tools = set()
        for action in actions:
            tool = action.get("tool")
            if tool and tool.startswith("playwright_"):
                tools.add(tool)
        return sorted(list(tools))

    @staticmethod
    def _generate_tags(description: str, actions: List[Dict[str, Any]]) -> List[str]:
        """
        Generate tags for skill, including decision and error handling tags.

        Tags indicate:
        - Action types (navigation, extraction, etc.)
        - Decision logic presence
        - Error handling capabilities
        """
        tags = []

        # Extract keywords from description
        keywords = re.findall(r'\b\w{4,}\b', description.lower())
        common_words = {"this", "that", "with", "from", "have", "been", "were"}
        tags.extend([kw for kw in keywords[:5] if kw not in common_words])

        # Track decision logic features
        has_conditionals = False
        has_error_handling = False
        has_recovery = False

        # Add tags based on tools used and decision logic
        for action in actions:
            tool = action.get("tool", "")

            # Tool-based tags
            if "navigate" in tool:
                tags.append("navigation")
            elif "extract" in tool:
                tags.append("extraction")
            elif "click" in tool or "fill" in tool:
                tags.append("interaction")

            # Decision logic tags
            if action.get("is_conditional"):
                has_conditionals = True
            if action.get("error_context"):
                has_error_handling = True
            if action.get("is_recovery"):
                has_recovery = True

            # Recovery-specific tags
            decision_context = action.get("decision_context", {})
            if decision_context.get("reason") == "verification_step":
                tags.append("verification")

        # Add meta tags for skill capabilities
        if has_conditionals:
            tags.append("conditional")
            tags.append("decision-logic")
        if has_error_handling:
            tags.append("error-handling")
            tags.append("robust")
        if has_recovery:
            tags.append("recovery")
            tags.append("resilient")

        return list(set(tags))[:15]  # Limit to 15 unique tags (increased from 10)

    @staticmethod
    def generalize_skill(skill: Skill) -> Skill:
        """
        Make a skill more general and reusable

        Args:
            skill: Specific skill to generalize

        Returns:
            Generalized version of the skill
        """
        # Create a copy
        generalized = Skill(**skill.to_dict())
        generalized.skill_id = f"{skill.skill_id}_gen"
        generalized.version = skill.version + 1
        generalized.generalization_level = skill.generalization_level + 1

        # Replace hardcoded values with parameters
        code = skill.code

        # Find string literals that should be parameters
        string_literals = re.findall(r"'([^']+)'|\"([^\"]+)\"", code)
        for literal_tuple in string_literals:
            literal = literal_tuple[0] or literal_tuple[1]

            # Skip very short strings
            if len(literal) < 3:
                continue

            # Create parameter name
            param_name = re.sub(r'[^a-z0-9_]', '_', literal.lower())[:30]

            # Replace in code
            code = code.replace(f"'{literal}'", f"context.get('{param_name}', '{literal}')")
            code = code.replace(f'"{literal}"', f"context.get('{param_name}', '{literal}')")

            # Add to parameters
            if param_name not in generalized.parameters:
                generalized.parameters[param_name] = {
                    "type": "string",
                    "description": f"Parameter extracted from: {literal[:50]}",
                    "default": literal
                }

        generalized.code = code
        return generalized


class SkillComposer:
    """
    Composes multiple skills into complex workflows
    """

    @staticmethod
    def compose_skills(
        skills: List[Skill],
        workflow_name: str,
        workflow_description: str
    ) -> Skill:
        """
        Combine multiple skills into a composite skill

        Args:
            skills: List of skills to combine
            workflow_name: Name for the composite skill
            workflow_description: Description of what the workflow does

        Returns:
            Composite skill
        """
        # Generate composite skill ID
        skill_ids = [s.skill_id for s in skills]
        composite_id = f"composite_{hashlib.md5('_'.join(skill_ids).encode()).hexdigest()[:12]}"

        # Combine code - execute each skill's code in sequence
        code_parts = [
            f"# Composite skill: {workflow_name}",
            "# Executes multiple skills in sequence",
            "results = []",
        ]

        for i, skill in enumerate(skills):
            code_parts.append(f"# Step {i+1}: {skill.name}")
            code_parts.append(f"# Execute skill code:")
            # Indent the skill code
            skill_code_lines = skill.code.split("\n")
            for line in skill_code_lines:
                if line.strip():
                    code_parts.append(line)
            code_parts.append(f"step_{i}_result = result if 'result' in locals() else None")
            code_parts.append(f"results.append(step_{i}_result)")
            code_parts.append(f"context['prev_result'] = step_{i}_result")
            code_parts.append("")

        code_parts.append("result = results")

        composite_code = "\n".join(code_parts)

        # Combine parameters
        composite_params = {}
        for skill in skills:
            composite_params.update(skill.parameters)

        # Combine required tools
        composite_tools = []
        for skill in skills:
            composite_tools.extend(skill.required_tools)
        composite_tools = sorted(list(set(composite_tools)))

        # Combine tags
        composite_tags = []
        for skill in skills:
            composite_tags.extend(skill.tags)
        composite_tags = sorted(list(set(composite_tags)))[:10]

        # Create composite skill
        composite = Skill(
            skill_id=composite_id,
            name=workflow_name,
            description=workflow_description,
            category=SkillCategory.COMPOSITE,
            code=composite_code,
            parameters=composite_params,
            required_tools=composite_tools,
            tags=composite_tags,
            author="system"
        )

        return composite


class SkillLibrary:
    """
    Main skill library manager with async support for concurrent access
    """

    def __init__(self):
        self.skills: Dict[str, Skill] = {}
        self.retriever = SkillRetriever()
        self.validator = SkillValidator()
        self.generator = SkillGenerator()
        self.composer = SkillComposer()

        # Async concurrency primitives
        self._rw_lock = AsyncRWLock()
        self._cache = SkillCache(max_size=100, ttl_seconds=3600)
        self._versions: Dict[str, SkillVersion] = {}
        self._version_lock = asyncio.Lock()

        # Load existing skills
        self._load_skills()

        # Initialize with pre-built skills if library is empty
        if not self.skills:
            self._initialize_prebuilt_skills()

        logger.info(f"Initialized SkillLibrary with {len(self.skills)} skills")

    def _load_skills(self):
        """Load skills from disk"""
        skills_file = SKILLS_DIR / "skills.json"
        if not skills_file.exists():
            return

        try:
            data = json.loads(skills_file.read_text())
            for skill_data in data:
                skill = Skill.from_dict(skill_data)
                self.skills[skill.skill_id] = skill

                # Add to vector database if active
                if skill.status == SkillStatus.ACTIVE:
                    self.retriever.add_skill(skill)

            logger.info(f"Loaded {len(self.skills)} skills from disk")
        except Exception as e:
            logger.error(f"Failed to load skills: {e}")

    def _save_skills(self):
        """Save skills to disk"""
        try:
            skills_data = [skill.to_dict() for skill in self.skills.values()]
            skills_file = SKILLS_DIR / "skills.json"
            skills_file.write_text(json.dumps(skills_data, indent=2))
            logger.debug(f"Saved {len(self.skills)} skills to disk")
        except Exception as e:
            logger.error(f"Failed to save skills: {e}")

    def add_skill(self, skill: Skill, validate: bool = True) -> bool:
        """
        Add a skill to the library (sync version for backward compatibility)

        Args:
            skill: Skill to add
            validate: Whether to validate before adding

        Returns:
            True if skill was added successfully
        """
        # Validate if requested
        if validate:
            is_valid, errors = self.validator.validate_skill(skill)
            if not is_valid:
                logger.warning(f"Skill validation failed: {errors}")
                return False

        # Check for duplicates
        existing_hash = None
        for existing_skill in self.skills.values():
            if existing_skill.get_hash() == skill.get_hash():
                logger.info(f"Skill already exists: {existing_skill.skill_id}")
                return False

        # Add to library
        self.skills[skill.skill_id] = skill

        # Add to vector database if active
        if skill.status == SkillStatus.ACTIVE:
            self.retriever.add_skill(skill)

        # Save to disk
        self._save_skills()

        logger.info(f"Added skill: {skill.skill_id} - {skill.name}")
        return True

    async def add_skill_async(self, skill: Skill, validate: bool = True, expected_version: Optional[int] = None) -> bool:
        """
        Add a skill to the library asynchronously with optimistic locking

        Args:
            skill: Skill to add
            validate: Whether to validate before adding
            expected_version: Expected version for optimistic locking (None for new skills)

        Returns:
            True if skill was added successfully

        Raises:
            ValueError: If version conflict occurs
        """
        async with self._rw_lock.write_lock():
            # Validate if requested
            if validate:
                is_valid, errors = self.validator.validate_skill(skill)
                if not is_valid:
                    logger.warning(f"Skill validation failed: {errors}")
                    return False

            # Check version for optimistic locking
            if skill.skill_id in self._versions:
                current_version = self._versions[skill.skill_id].version
                if expected_version is not None and current_version != expected_version:
                    raise ValueError(
                        f"Version conflict: expected {expected_version}, current is {current_version}"
                    )

            # Check for duplicates
            existing_hash = None
            for existing_skill in self.skills.values():
                if existing_skill.get_hash() == skill.get_hash():
                    logger.info(f"Skill already exists: {existing_skill.skill_id}")
                    return False

            # Add to library
            self.skills[skill.skill_id] = skill

            # Update version tracking
            content_hash = skill.get_hash()
            new_version = SkillVersion(
                skill_id=skill.skill_id,
                version=skill.version,
                content_hash=content_hash,
                timestamp=datetime.now().isoformat()
            )
            self._versions[skill.skill_id] = new_version

            # Add to vector database if active
            if skill.status == SkillStatus.ACTIVE:
                self.retriever.add_skill(skill)

            # Invalidate cache
            await self._cache.invalidate(f"skill:{skill.skill_id}")
            await self._cache.invalidate("search:*")

            # Save to disk (async)
            await self._save_skills_async()

            # Save version history
            await self._save_version_history(skill)

            logger.info(f"Added skill async: {skill.skill_id} - {skill.name} (v{skill.version})")
            return True

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        """Get a skill by ID (sync version for backward compatibility)"""
        return self.skills.get(skill_id)

    async def get_skill_async(self, skill_id: str, use_cache: bool = True) -> Optional[Skill]:
        """
        Get a skill by ID asynchronously with caching

        Args:
            skill_id: Skill ID to retrieve
            use_cache: Whether to use cache

        Returns:
            Skill or None if not found
        """
        # Try cache first
        if use_cache:
            cache_key = f"skill:{skill_id}"
            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for skill: {skill_id}")
                return cached

        # Get from storage with read lock
        async with self._rw_lock.read_lock():
            skill = self.skills.get(skill_id)

        # Update cache
        if skill and use_cache:
            await self._cache.set(cache_key, skill)

        return skill

    def search_skills(
        self,
        query: str,
        category: Optional[SkillCategory] = None,
        min_success_rate: float = 0.0,
        limit: int = 10
    ) -> List[Skill]:
        """
        Search for skills matching query (sync version for backward compatibility)

        Args:
            query: Natural language description
            category: Optional category filter
            min_success_rate: Minimum success rate
            limit: Maximum results

        Returns:
            List of matching skills, sorted by relevance
        """
        # Use vector search if available
        if CHROMADB_AVAILABLE and self.retriever.collection:
            results = self.retriever.search(
                query=query,
                category=category,
                min_success_rate=min_success_rate,
                limit=limit
            )

            skills = []
            for skill_id, score in results:
                skill = self.get_skill(skill_id)
                if skill and skill.status == SkillStatus.ACTIVE:
                    skills.append(skill)

            return skills

        # Fallback to basic search
        return self._basic_search(query, category, min_success_rate, limit)

    async def search_skills_async(
        self,
        query: str,
        category: Optional[SkillCategory] = None,
        min_success_rate: float = 0.0,
        limit: int = 10,
        use_cache: bool = True
    ) -> List[Skill]:
        """
        Search for skills matching query asynchronously with caching

        Args:
            query: Natural language description
            category: Optional category filter
            min_success_rate: Minimum success rate
            limit: Maximum results
            use_cache: Whether to use cache

        Returns:
            List of matching skills, sorted by relevance
        """
        # Build cache key
        cache_key = f"search:{query}:{category}:{min_success_rate}:{limit}"

        # Try cache first
        if use_cache:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for search: {query[:50]}")
                return cached

        # Use vector search if available
        async with self._rw_lock.read_lock():
            if CHROMADB_AVAILABLE and self.retriever.collection:
                results = self.retriever.search(
                    query=query,
                    category=category,
                    min_success_rate=min_success_rate,
                    limit=limit
                )

                skills = []
                for skill_id, score in results:
                    skill = self.skills.get(skill_id)
                    if skill and skill.status == SkillStatus.ACTIVE:
                        skills.append(skill)

                # Cache results
                if use_cache:
                    await self._cache.set(cache_key, skills)

                return skills

            # Fallback to basic search
            skills = self._basic_search(query, category, min_success_rate, limit)

        # Cache results
        if use_cache:
            await self._cache.set(cache_key, skills)

        return skills

    def _basic_search(
        self,
        query: str,
        category: Optional[SkillCategory],
        min_success_rate: float,
        limit: int
    ) -> List[Skill]:
        """Basic keyword-based search fallback"""
        query_lower = query.lower()
        matches = []

        for skill in self.skills.values():
            if skill.status != SkillStatus.ACTIVE:
                continue

            if category and skill.category != category:
                continue

            if skill.metrics.success_rate < min_success_rate:
                continue

            # Simple keyword matching
            score = 0
            searchable = f"{skill.name} {skill.description} {' '.join(skill.tags)}".lower()

            for word in query_lower.split():
                if word in searchable:
                    score += 1

            if score > 0:
                matches.append((skill, score))

        # Sort by score and success rate
        matches.sort(key=lambda x: (x[1], x[0].metrics.success_rate), reverse=True)

        return [skill for skill, score in matches[:limit]]

    def learn_skill_from_execution(
        self,
        task_description: str,
        actions: List[Dict[str, Any]],
        result: Any,
        category: SkillCategory,
        auto_add: bool = True
    ) -> Optional[Skill]:
        """
        Learn a new skill from a successful execution

        Args:
            task_description: What the task was trying to do
            actions: Actions that were executed
            result: Result of the execution
            category: Skill category
            auto_add: Whether to automatically add to library

        Returns:
            Learned skill or None
        """
        skill = self.generator.extract_from_execution(
            task_description=task_description,
            actions=actions,
            result=result,
            category=category
        )

        if not skill:
            return None

        # Validate
        is_valid, errors = self.validator.validate_skill(skill)
        if not is_valid:
            logger.warning(f"Learned skill failed validation: {errors}")
            return None

        # Mark as active
        skill.status = SkillStatus.ACTIVE

        # Add to library if requested
        if auto_add:
            self.add_skill(skill, validate=False)

        return skill

    def compose_workflow(
        self,
        skill_ids: List[str],
        workflow_name: str,
        workflow_description: str
    ) -> Optional[Skill]:
        """
        Compose multiple skills into a workflow

        Args:
            skill_ids: List of skill IDs to combine
            workflow_name: Name for the workflow
            workflow_description: Description of the workflow

        Returns:
            Composite skill or None
        """
        skills = [self.get_skill(sid) for sid in skill_ids]

        # Check all skills exist
        if any(s is None for s in skills):
            logger.warning("Some skills not found for composition")
            return None

        composite = self.composer.compose_skills(
            skills=skills,
            workflow_name=workflow_name,
            workflow_description=workflow_description
        )

        # Validate and add
        is_valid, errors = self.validator.validate_skill(composite)
        if not is_valid:
            logger.warning(f"Composite skill validation failed: {errors}")
            return None

        composite.status = SkillStatus.ACTIVE
        self.add_skill(composite, validate=False)

        return composite

    def record_skill_usage(
        self,
        skill_id: str,
        success: bool,
        execution_time: float,
        error: str = ""
    ):
        """Record usage of a skill"""
        skill = self.get_skill(skill_id)
        if not skill:
            return

        skill.metrics.record_use(success, execution_time, error)
        skill.updated_at = datetime.now().isoformat()

        # Save periodically
        self._save_skills()

    def deprecate_skill(self, skill_id: str, replacement_id: Optional[str] = None):
        """Deprecate a skill"""
        skill = self.get_skill(skill_id)
        if not skill:
            return

        skill.status = SkillStatus.DEPRECATED
        skill.updated_at = datetime.now().isoformat()

        # Remove from vector database
        self.retriever.remove_skill(skill_id)

        # Save
        self._save_skills()

        logger.info(f"Deprecated skill: {skill_id}")

    def get_statistics(self) -> Dict[str, Any]:
        """Get library statistics"""
        total = len(self.skills)
        by_category = defaultdict(int)
        by_status = defaultdict(int)
        total_uses = 0
        avg_success_rate = 0.0

        for skill in self.skills.values():
            by_category[skill.category.value] += 1
            by_status[skill.status.value] += 1
            total_uses += skill.metrics.total_uses
            if skill.metrics.total_uses > 0:
                avg_success_rate += skill.metrics.success_rate

        active_count = by_status.get(SkillStatus.ACTIVE.value, 0)
        if active_count > 0:
            avg_success_rate /= active_count

        return {
            "total_skills": total,
            "by_category": dict(by_category),
            "by_status": dict(by_status),
            "total_uses": total_uses,
            "avg_success_rate": avg_success_rate,
            "retrieval_enabled": CHROMADB_AVAILABLE
        }

    def export_skills(self, output_path: Path):
        """Export skills to a file"""
        try:
            skills_data = [skill.to_dict() for skill in self.skills.values()]
            output_path.write_text(json.dumps(skills_data, indent=2))
            logger.info(f"Exported {len(skills_data)} skills to {output_path}")
        except Exception as e:
            logger.error(f"Failed to export skills: {e}")

    def import_skills(self, input_path: Path):
        """Import skills from a file"""
        try:
            data = json.loads(input_path.read_text())
            imported = 0

            for skill_data in data:
                skill = Skill.from_dict(skill_data)
                if self.add_skill(skill, validate=True):
                    imported += 1

            logger.info(f"Imported {imported} skills from {input_path}")
        except Exception as e:
            logger.error(f"Failed to import skills: {e}")

    def export_skill_as_code(
        self,
        skill_id: str,
        output_path: Path,
        format: str = "python_async"
    ) -> Optional[Dict[str, Any]]:
        """
        Export a skill as Playwright code

        Args:
            skill_id: ID of skill to export
            output_path: Where to save the generated code
            format: Output format (python_async, python_sync, pytest)

        Returns:
            Dict with code and metadata, or None if failed
        """
        try:
            # Import code generator
            from .code_generator import PlaywrightCodeGenerator

            skill = self.get_skill(skill_id)
            if not skill:
                logger.error(f"Skill not found: {skill_id}")
                return None

            # Convert skill to actions
            actions = []
            for tool in skill.required_tools:
                # Extract arguments from skill code if possible
                # For now, create basic action structure
                actions.append({
                    "tool": tool,
                    "arguments": {}
                })

            # Generate code
            generator = PlaywrightCodeGenerator()
            generated = generator.generate_from_trace(
                actions=actions,
                description=skill.description,
                format=format
            )

            # Save to file
            generator.save_to_file(generated, output_path)

            logger.info(f"Exported skill {skill_id} as {format} to {output_path}")

            return {
                "success": True,
                "skill_id": skill_id,
                "skill_name": skill.name,
                "code": generated.code,
                "format": generated.format.value,
                "output_path": str(output_path)
            }

        except ImportError:
            logger.error("Code generator not available - install code_generator module")
            return None
        except Exception as e:
            logger.error(f"Failed to export skill as code: {e}")
            return None

    async def execute_skill_async(
        self,
        skill_id: str,
        context: Dict[str, Any],
        timeout: Optional[float] = 30.0
    ) -> Any:
        """
        Execute a skill asynchronously with timeout

        Args:
            skill_id: ID of skill to execute
            context: Execution context
            timeout: Timeout in seconds (default 30)

        Returns:
            Skill execution result

        Raises:
            asyncio.TimeoutError: If execution exceeds timeout
            ValueError: If skill not found
        """
        skill = await self.get_skill_async(skill_id)
        if not skill:
            raise ValueError(f"Skill not found: {skill_id}")

        start_time = time.time()
        try:
            result = await skill.execute_async(context, timeout=timeout)
            execution_time = time.time() - start_time

            # Record success
            await self._record_skill_usage_async(skill_id, True, execution_time)

            return result
        except Exception as e:
            execution_time = time.time() - start_time

            # Record failure
            await self._record_skill_usage_async(skill_id, False, execution_time, str(e))

            raise

    async def batch_add_skills(self, skills: List[Skill], validate: bool = True) -> Dict[str, bool]:
        """
        Add multiple skills concurrently

        Args:
            skills: List of skills to add
            validate: Whether to validate before adding

        Returns:
            Dictionary mapping skill_id to success status
        """
        results = {}

        # Create tasks for concurrent addition
        tasks = []
        for skill in skills:
            task = self.add_skill_async(skill, validate=validate)
            tasks.append((skill.skill_id, task))

        # Execute concurrently
        for skill_id, task in tasks:
            try:
                success = await task
                results[skill_id] = success
            except Exception as e:
                logger.error(f"Failed to add skill {skill_id}: {e}")
                results[skill_id] = False

        logger.info(f"Batch added {sum(results.values())}/{len(skills)} skills")
        return results

    async def batch_execute_skills(
        self,
        executions: List[Tuple[str, Dict[str, Any]]],
        timeout: Optional[float] = 30.0,
        max_concurrent: int = 10
    ) -> List[Tuple[str, Any, Optional[Exception]]]:
        """
        Execute multiple skills concurrently with concurrency limit

        Args:
            executions: List of (skill_id, context) tuples
            timeout: Timeout per skill in seconds
            max_concurrent: Maximum concurrent executions

        Returns:
            List of (skill_id, result, error) tuples
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def execute_with_semaphore(skill_id: str, context: Dict[str, Any]):
            async with semaphore:
                try:
                    result = await self.execute_skill_async(skill_id, context, timeout)
                    return (skill_id, result, None)
                except Exception as e:
                    return (skill_id, None, e)

        # Create tasks
        tasks = [execute_with_semaphore(skill_id, context) for skill_id, context in executions]

        # Execute concurrently
        results = await asyncio.gather(*tasks)

        logger.info(f"Batch executed {len(results)} skills")
        return results

    async def compose_skills_async(
        self,
        skill_ids: List[str],
        context: Dict[str, Any],
        workflow_name: str,
        timeout_per_skill: Optional[float] = 30.0
    ) -> Dict[str, Any]:
        """
        Compose and execute multiple skills in sequence asynchronously

        Args:
            skill_ids: List of skill IDs to execute in order
            context: Shared execution context
            workflow_name: Name of the workflow
            timeout_per_skill: Timeout per skill

        Returns:
            Dictionary with workflow results
        """
        results = []
        errors = []

        for i, skill_id in enumerate(skill_ids):
            try:
                logger.info(f"Executing step {i+1}/{len(skill_ids)}: {skill_id}")

                result = await self.execute_skill_async(skill_id, context, timeout_per_skill)

                results.append({
                    "step": i + 1,
                    "skill_id": skill_id,
                    "success": True,
                    "result": result
                })

                # Update context with previous result
                context["prev_result"] = result

            except Exception as e:
                logger.error(f"Step {i+1} failed: {e}")

                errors.append({
                    "step": i + 1,
                    "skill_id": skill_id,
                    "error": str(e)
                })

                results.append({
                    "step": i + 1,
                    "skill_id": skill_id,
                    "success": False,
                    "error": str(e)
                })

                # Stop on error
                break

        return {
            "workflow_name": workflow_name,
            "total_steps": len(skill_ids),
            "completed_steps": len([r for r in results if r.get("success")]),
            "results": results,
            "errors": errors,
            "success": len(errors) == 0
        }

    async def _save_skills_async(self):
        """Save skills to disk asynchronously"""
        try:
            skills_data = [skill.to_dict() for skill in self.skills.values()]
            skills_file = SKILLS_DIR / "skills.json"

            # Use asyncio to write file in executor to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: skills_file.write_text(json.dumps(skills_data, indent=2))
            )

            logger.debug(f"Saved {len(self.skills)} skills to disk (async)")
        except Exception as e:
            logger.error(f"Failed to save skills async: {e}")

    async def _save_version_history(self, skill: Skill):
        """Save skill version to history"""
        try:
            history_file = SKILL_HISTORY_DIR / f"{skill.skill_id}_v{skill.version}.json"

            skill_data = skill.to_dict()
            skill_data["saved_at"] = datetime.now().isoformat()

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: history_file.write_text(json.dumps(skill_data, indent=2))
            )

            logger.debug(f"Saved version history for {skill.skill_id} v{skill.version}")
        except Exception as e:
            logger.error(f"Failed to save version history: {e}")

    async def _record_skill_usage_async(
        self,
        skill_id: str,
        success: bool,
        execution_time: float,
        error: str = ""
    ):
        """Record skill usage asynchronously"""
        async with self._rw_lock.write_lock():
            skill = self.skills.get(skill_id)
            if not skill:
                return

            skill.metrics.record_use(success, execution_time, error)
            skill.updated_at = datetime.now().isoformat()

            # Invalidate cache
            await self._cache.invalidate(f"skill:{skill_id}")

            # Save periodically (every 10 uses)
            if skill.metrics.total_uses % 10 == 0:
                await self._save_skills_async()

    async def get_version(self, skill_id: str) -> Optional[SkillVersion]:
        """Get current version info for a skill"""
        async with self._version_lock:
            return self._versions.get(skill_id)

    async def get_version_history(self, skill_id: str) -> List[Dict[str, Any]]:
        """Get version history for a skill"""
        history = []

        try:
            # Find all version files for this skill
            version_files = sorted(SKILL_HISTORY_DIR.glob(f"{skill_id}_v*.json"))

            for version_file in version_files:
                loop = asyncio.get_event_loop()
                content = await loop.run_in_executor(None, version_file.read_text)
                history.append(json.loads(content))

            logger.debug(f"Retrieved {len(history)} versions for {skill_id}")
            return history
        except Exception as e:
            logger.error(f"Failed to get version history: {e}")
            return []

    def _initialize_prebuilt_skills(self):
        """Initialize library with pre-built skills"""
        prebuilt_skills = self._create_prebuilt_skills()

        for skill in prebuilt_skills:
            skill.status = SkillStatus.ACTIVE
            self.add_skill(skill, validate=True)

        logger.info(f"Initialized {len(prebuilt_skills)} pre-built skills")

    def _create_prebuilt_skills(self) -> List[Skill]:
        """Create pre-built skills for common patterns"""
        skills = []

        # Navigation Skills
        skills.append(Skill(
            skill_id="nav_login_generic",
            name="Generic Login Flow",
            description="Navigate to login page and submit credentials",
            category=SkillCategory.NAVIGATION,
            code="""
async def login_generic(context):
    login_url = context.get('login_url')
    username = context.get('username')
    password = context.get('password')
    username_selector = context.get('username_selector', 'input[type="email"], input[name="username"]')
    password_selector = context.get('password_selector', 'input[type="password"]')
    submit_selector = context.get('submit_selector', 'button[type="submit"]')

    await playwright_navigate(url=login_url)
    await playwright_fill(selector=username_selector, value=username)
    await playwright_fill(selector=password_selector, value=password)
    await playwright_click(selector=submit_selector)
    result = True
    return result
""",
            parameters={
                "login_url": {"type": "string", "description": "URL of login page"},
                "username": {"type": "string", "description": "Username or email"},
                "password": {"type": "string", "description": "Password"},
            },
            required_tools=["playwright_navigate", "playwright_fill", "playwright_click"],
            tags=["login", "authentication", "navigation"],
        ))

        skills.append(Skill(
            skill_id="nav_pagination",
            name="Paginate Through Results",
            description="Click through multiple pages of results",
            category=SkillCategory.NAVIGATION,
            code="""
async def paginate_results(context):
    max_pages = context.get('max_pages', 10)
    next_selector = context.get('next_selector', 'a[rel="next"], button.next')

    results = []
    for page in range(max_pages):
        # Extract data from current page
        page_data = await playwright_snapshot()
        results.append(page_data)

        # Try to go to next page
        try:
            await playwright_click(selector=next_selector)
            await asyncio.sleep(2)  # Wait for page load
        except:
            break  # No more pages

    result = results
    return result
""",
            parameters={
                "max_pages": {"type": "int", "description": "Maximum pages to visit"},
                "next_selector": {"type": "string", "description": "Selector for next button"},
            },
            required_tools=["playwright_snapshot", "playwright_click"],
            tags=["pagination", "navigation", "scraping"],
        ))

        skills.append(Skill(
            skill_id="nav_infinite_scroll",
            name="Infinite Scroll Loading",
            description="Scroll down to load more content on infinite scroll pages",
            category=SkillCategory.NAVIGATION,
            code="""
async def infinite_scroll(context):
    scroll_count = context.get('scroll_count', 5)
    scroll_pause = context.get('scroll_pause', 2)

    for i in range(scroll_count):
        # Scroll to bottom
        await playwright_evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(scroll_pause)

    result = True
    return result
""",
            parameters={
                "scroll_count": {"type": "int", "description": "Number of scrolls"},
                "scroll_pause": {"type": "int", "description": "Seconds to wait between scrolls"},
            },
            required_tools=["playwright_evaluate"],
            tags=["scroll", "loading", "navigation"],
        ))

        # Extraction Skills
        skills.append(Skill(
            skill_id="extract_table_data",
            name="Extract Table Data",
            description="Extract all data from an HTML table",
            category=SkillCategory.EXTRACTION,
            code="""
async def extract_table(context):
    table_selector = context.get('table_selector', 'table')

    # Get table HTML
    table_html = await playwright_get_text(selector=table_selector)

    # Parse table (simplified - real implementation would use BeautifulSoup)
    result = {"extracted": True, "selector": table_selector}
    return result
""",
            parameters={
                "table_selector": {"type": "string", "description": "CSS selector for table"},
            },
            required_tools=["playwright_get_text"],
            tags=["extraction", "table", "data"],
        ))

        skills.append(Skill(
            skill_id="extract_contacts",
            name="Extract Contact Information",
            description="Find and extract emails and phone numbers from page",
            category=SkillCategory.EXTRACTION,
            code="""
async def extract_contacts(context):
    result = await playwright_find_contacts()
    return result
""",
            required_tools=["playwright_find_contacts"],
            tags=["extraction", "contacts", "emails", "phones"],
        ))

        # Interaction Skills
        skills.append(Skill(
            skill_id="interact_fill_form",
            name="Fill and Submit Form",
            description="Fill out a form with provided data and submit",
            category=SkillCategory.INTERACTION,
            code="""
async def fill_form(context):
    form_data = context.get('form_data', {})
    submit_selector = context.get('submit_selector', 'button[type="submit"]')

    # Fill each field
    for selector, value in form_data.items():
        await playwright_fill(selector=selector, value=value)

    # Submit
    await playwright_click(selector=submit_selector)
    result = True
    return result
""",
            parameters={
                "form_data": {"type": "dict", "description": "Dictionary of selector: value pairs"},
                "submit_selector": {"type": "string", "description": "Submit button selector"},
            },
            required_tools=["playwright_fill", "playwright_click"],
            tags=["forms", "interaction", "submission"],
        ))

        # Recovery Skills
        skills.append(Skill(
            skill_id="recovery_dismiss_popup",
            name="Dismiss Cookie/Modal Popups",
            description="Dismiss common cookie banners and modal dialogs",
            category=SkillCategory.RECOVERY,
            code="""
async def dismiss_popups(context):
    # Common selectors for dismiss buttons
    dismiss_selectors = [
        'button[aria-label="Close"]',
        'button.close',
        '.cookie-banner button',
        '[data-testid="cookie-accept"]',
        'button:has-text("Accept")',
        'button:has-text("Close")',
    ]

    dismissed = 0
    for selector in dismiss_selectors:
        try:
            await playwright_click(selector=selector)
            dismissed += 1
            await asyncio.sleep(0.5)
        except:
            pass

    result = {"dismissed": dismissed}
    return result
""",
            required_tools=["playwright_click"],
            tags=["recovery", "popups", "cookies", "modals"],
        ))

        # Verification Skills
        skills.append(Skill(
            skill_id="verify_login_success",
            name="Verify Login Success",
            description="Check if login was successful by looking for indicators",
            category=SkillCategory.VERIFICATION,
            code="""
async def verify_login(context):
    success_indicators = context.get('success_indicators', [
        'button:has-text("Logout")',
        'a:has-text("Profile")',
        '.user-menu',
    ])

    for indicator in success_indicators:
        try:
            element = await playwright_get_text(selector=indicator)
            if element:
                result = True
                return result
        except:
            pass

    result = False
    return result
""",
            parameters={
                "success_indicators": {"type": "list", "description": "List of selectors indicating success"},
            },
            required_tools=["playwright_get_text"],
            tags=["verification", "login", "validation"],
        ))

        return skills


# Global instance
_skill_library_instance = None


def get_skill_library() -> SkillLibrary:
    """Get global skill library instance"""
    global _skill_library_instance
    if _skill_library_instance is None:
        _skill_library_instance = SkillLibrary()
    return _skill_library_instance


# Example usage
async def example_usage():
    """Example of how to use the skill library with async operations"""

    # Get library instance
    library = get_skill_library()

    print("=== Async Skill Library Demo ===\n")

    # 1. Async search for skills with caching
    print("1. Searching for skills asynchronously...")
    skills = await library.search_skills_async(
        query="login to website",
        category=SkillCategory.NAVIGATION,
        min_success_rate=0.7,
        limit=5,
        use_cache=True
    )

    print(f"Found {len(skills)} skills:")
    for skill in skills:
        print(f"  - {skill.name}: {skill.description}")
        print(f"    Success rate: {skill.metrics.success_rate:.2%}")

    # 2. Async get skill with caching
    print("\n2. Getting skill asynchronously with caching...")
    skill = await library.get_skill_async("nav_login_generic", use_cache=True)
    if skill:
        print(f"Retrieved: {skill.name}")
        version = await library.get_version(skill.skill_id)
        if version:
            print(f"Version: {version.version}, Hash: {version.content_hash[:8]}")

    # 3. Batch add skills
    print("\n3. Batch adding skills concurrently...")
    new_skills = [
        Skill(
            skill_id="test_skill_1",
            name="Test Skill 1",
            description="Test skill for batch operations",
            category=SkillCategory.NAVIGATION,
            code="result = 'test1'",
            status=SkillStatus.ACTIVE
        ),
        Skill(
            skill_id="test_skill_2",
            name="Test Skill 2",
            description="Another test skill",
            category=SkillCategory.EXTRACTION,
            code="result = 'test2'",
            status=SkillStatus.ACTIVE
        )
    ]

    batch_results = await library.batch_add_skills(new_skills, validate=True)
    print(f"Batch add results: {batch_results}")

    # 4. Execute skill asynchronously with timeout
    print("\n4. Executing skill asynchronously with timeout...")
    try:
        result = await library.execute_skill_async(
            skill_id="test_skill_1",
            context={},
            timeout=5.0
        )
        print(f"Execution result: {result}")
    except asyncio.TimeoutError:
        print("Execution timed out")
    except Exception as e:
        print(f"Execution failed: {e}")

    # 5. Batch execute skills concurrently
    print("\n5. Batch executing skills concurrently...")
    executions = [
        ("test_skill_1", {}),
        ("test_skill_2", {}),
    ]

    batch_exec_results = await library.batch_execute_skills(
        executions,
        timeout=5.0,
        max_concurrent=5
    )

    for skill_id, result, error in batch_exec_results:
        if error:
            print(f"  {skill_id}: ERROR - {error}")
        else:
            print(f"  {skill_id}: SUCCESS - {result}")

    # 6. Compose and execute workflow
    print("\n6. Composing and executing workflow asynchronously...")
    workflow_result = await library.compose_skills_async(
        skill_ids=["test_skill_1", "test_skill_2"],
        context={"shared_data": "value"},
        workflow_name="Test Workflow",
        timeout_per_skill=5.0
    )

    print(f"Workflow: {workflow_result['workflow_name']}")
    print(f"Success: {workflow_result['success']}")
    print(f"Completed: {workflow_result['completed_steps']}/{workflow_result['total_steps']}")

    # 7. Get version history
    print("\n7. Getting version history...")
    history = await library.get_version_history("test_skill_1")
    print(f"Found {len(history)} versions in history")

    # 8. Get statistics
    print("\n8. Library Statistics:")
    stats = library.get_statistics()
    print(f"  Total skills: {stats['total_skills']}")
    print(f"  Active skills: {stats['by_status'].get('active', 0)}")
    print(f"  Total uses: {stats['total_uses']}")
    print(f"  Average success rate: {stats['avg_success_rate']:.2%}")
    print(f"  Retrieval enabled: {stats['retrieval_enabled']}")

    print("\n=== Demo Complete ===")


async def example_concurrent_agents():
    """Example showing multiple agents accessing skills concurrently"""

    library = get_skill_library()

    print("=== Concurrent Agents Demo ===\n")

    async def agent_task(agent_id: int, skill_id: str):
        """Simulates an agent accessing skills"""
        print(f"Agent {agent_id}: Starting...")

        # Search for skills
        skills = await library.search_skills_async(
            query="navigation",
            limit=3,
            use_cache=True
        )
        print(f"Agent {agent_id}: Found {len(skills)} skills")

        # Get specific skill
        skill = await library.get_skill_async(skill_id, use_cache=True)
        if skill:
            print(f"Agent {agent_id}: Retrieved {skill.name}")

        # Execute skill
        try:
            result = await library.execute_skill_async(
                skill_id=skill_id,
                context={"agent_id": agent_id},
                timeout=5.0
            )
            print(f"Agent {agent_id}: Executed successfully - {result}")
        except Exception as e:
            print(f"Agent {agent_id}: Execution failed - {e}")

        print(f"Agent {agent_id}: Complete")

    # Run multiple agents concurrently
    agents = [
        agent_task(1, "test_skill_1"),
        agent_task(2, "test_skill_2"),
        agent_task(3, "test_skill_1"),
        agent_task(4, "test_skill_2"),
        agent_task(5, "test_skill_1"),
    ]

    await asyncio.gather(*agents)

    print("\n=== All Agents Complete ===")


if __name__ == "__main__":
    asyncio.run(example_usage())
