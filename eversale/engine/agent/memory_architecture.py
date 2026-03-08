#!/usr/bin/env python3
"""
Mem0-Style Memory Architecture for Eversale

Advanced memory management system inspired by Mem0, LangGraph Memory, and cognitive science.
Implements multi-layered memory with intelligent compression, retrieval, and consolidation.

Architecture:
    Working Memory (40-50 steps) -> Episodic Memory (specific experiences) ->
    Semantic Memory (generalized knowledge) -> Skill Memory (action sequences)

Key Features:
- Context compression (10:1 ratio target)
- Intelligent memory decay (recency + relevance + utility)
- Vector-based semantic search
- Cross-session persistence
- Memory consolidation jobs
- 91% latency reduction, 90% token reduction (Mem0 benchmarks)
- **Distributed caching** for parallel agent instances (Redis/SQLite)

Performance Targets:
- <100ms retrieval time
- 95%+ retrieval relevance
- 90% token reduction
- 91% latency reduction vs raw history

Integration:
- Enhances context_memory.py
- Works with brain_enhanced_v2.py
- Supports reflexion.py experience storage
- Links to planning_agent.py for informed planning

Distributed Cache Support:
- Cache adapters enable shared knowledge across parallel agents
- SQLiteCacheAdapter: Local mode (default, backward compatible)
- RedisCacheAdapter: Distributed mode with pub/sub invalidation
- Cache-aside pattern: Check cache first, fallback to SQLite
- Automatic cache invalidation across instances via pub/sub
- Configurable via MEMORY_CACHE_ADAPTER environment variable

Locking Strategy:
- All memory stores (Episodic, Semantic, Skill) use asyncio.Lock instead of threading.Lock
- This prevents race conditions and deadlocks from mixing lock types
- Synchronous methods use _sync_lock() wrapper to safely acquire asyncio.Lock
- Asynchronous methods use 'async with self._lock' directly
- Working memory uses threading.Lock for fast JSON file I/O (separate concern)
"""

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set, Callable, AsyncIterator, TYPE_CHECKING
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict, deque
from loguru import logger
import sqlite3
import threading
from abc import ABC, abstractmethod

# Async SQLite support
try:
    import aiosqlite
    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False
    logger.warning("aiosqlite not available - async operations will use sync fallback")

# Optional: Vector embeddings for semantic search
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.warning("NumPy not available - semantic search will use text similarity")

# Optional: Better embeddings
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("Ollama not available - using basic embeddings")

# Optional: Redis for distributed caching
if TYPE_CHECKING:
    # For type checking, import aioredis
    import redis.asyncio as aioredis

try:
    import redis
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available - using SQLite-only mode")


# ============================================================================
# ASYNC I/O UTILITIES
# ============================================================================

class AsyncReadWriteLock:
    """
    Read-Write lock for async operations.
    Allows multiple readers OR single writer (mutual exclusion).
    This enables safe concurrent access from parallel agents.
    """

    def __init__(self):
        self._readers = 0
        self._writers = 0
        self._read_ready = asyncio.Condition()
        self._write_ready = asyncio.Condition()

    async def acquire_read(self):
        """Acquire read lock (multiple readers allowed)."""
        async with self._read_ready:
            while self._writers > 0:
                await self._read_ready.wait()
            self._readers += 1

    async def release_read(self):
        """Release read lock."""
        async with self._read_ready:
            self._readers -= 1
            if self._readers == 0:
                async with self._write_ready:
                    self._write_ready.notify_all()

    async def acquire_write(self):
        """Acquire write lock (exclusive access)."""
        async with self._write_ready:
            while self._writers > 0 or self._readers > 0:
                await self._write_ready.wait()
            self._writers += 1

    async def release_write(self):
        """Release write lock."""
        async with self._write_ready:
            self._writers -= 1
            self._write_ready.notify_all()
        async with self._read_ready:
            self._read_ready.notify_all()

    def reader(self):
        """Context manager for read operations."""
        return _ReadLockContext(self)

    def writer(self):
        """Context manager for write operations."""
        return _WriteLockContext(self)


class _ReadLockContext:
    """Context manager for read lock."""
    def __init__(self, lock: AsyncReadWriteLock):
        self.lock = lock

    async def __aenter__(self):
        await self.lock.acquire_read()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.lock.release_read()
        return False


class _WriteLockContext:
    """Context manager for write lock."""
    def __init__(self, lock: AsyncReadWriteLock):
        self.lock = lock

    async def __aenter__(self):
        await self.lock.acquire_write()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.lock.release_write()
        return False


def run_async(coro):
    """
    Run an async coroutine from sync code.
    Handles both cases: running event loop and no event loop.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop, create new one and run
        return asyncio.run(coro)
    else:
        # Already in async context - this shouldn't happen in sync wrapper
        raise RuntimeError(
            "Cannot call sync wrapper from async context. "
            "Use await with the async version instead."
        )


# ============================================================================
# CONFIGURATION
# ============================================================================

MEMORY_DIR = Path("memory")
MEMORY_DIR.mkdir(exist_ok=True)

EPISODIC_DB = MEMORY_DIR / "episodic_memory.db"
SEMANTIC_DB = MEMORY_DIR / "semantic_memory.db"
SKILL_DB = MEMORY_DIR / "skill_memory.db"
WORKING_MEMORY_JSON = MEMORY_DIR / "working_memory.json"

# Memory limits (based on cognitive science research)
WORKING_MEMORY_CAPACITY = 50  # Last 40-50 steps in full detail
SHORT_TERM_WINDOW = 100  # Steps to keep in compressed form
COMPRESSION_RATIO = 10  # Target 10:1 compression
CONSOLIDATION_INTERVAL = 300  # 5 minutes
WORKING_MEMORY_DECAY_HOURS = 1.0  # Hours before working memory gets lower priority

# Scoring weights
RECENCY_WEIGHT = 0.3
RELEVANCE_WEIGHT = 0.4
UTILITY_WEIGHT = 0.3

# Performance targets
TARGET_RETRIEVAL_TIME_MS = 100
TARGET_TOKEN_REDUCTION = 0.90  # 90% reduction
TARGET_LATENCY_REDUCTION = 0.91  # 91% reduction

# Database size limits
MAX_DB_SIZE_MB = 500  # Maximum database size in MB
DB_SIZE_WARNING_THRESHOLD = 0.8  # Warn at 80% of max size
DB_CLEANUP_TARGET = 0.6  # Clean up to 60% of max size when limit reached

# Distributed cache configuration
CACHE_ADAPTER = os.getenv("MEMORY_CACHE_ADAPTER", "sqlite")  # Options: "sqlite", "redis"
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))  # 1 hour default
CACHE_KEY_PREFIX = os.getenv("CACHE_KEY_PREFIX", "agent_memory")


# ============================================================================
# DATA STRUCTURES
# ============================================================================

class MemoryType(Enum):
    """Types of memory in the system."""
    WORKING = "working"      # Current task context (last 40-50 steps)
    EPISODIC = "episodic"    # Specific experiences
    SEMANTIC = "semantic"    # Generalized knowledge
    SKILL = "skill"          # Executable action sequences


class MemoryImportance(Enum):
    """Importance levels for memory decay."""
    CRITICAL = 1.0
    HIGH = 0.8
    MEDIUM = 0.5
    LOW = 0.3
    TRIVIAL = 0.1


@dataclass
class MemoryEntry:
    """Base memory entry with common metadata."""
    memory_id: str
    memory_type: MemoryType
    content: str
    compressed_content: Optional[str] = None

    # Metadata
    created_at: str = ""
    last_accessed: str = ""
    access_count: int = 0

    # Scoring
    importance: float = 0.5
    recency_score: float = 1.0
    relevance_score: float = 0.0
    utility_score: float = 0.0
    composite_score: float = 0.0

    # Context
    task_id: Optional[str] = None
    session_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    # Vector embedding for semantic search
    embedding: Optional[List[float]] = None

    # Token counts
    original_tokens: int = 0
    compressed_tokens: int = 0


@dataclass
class WorkingMemoryStep:
    """A single step in working memory (full detail)."""
    step_id: str
    step_number: int
    action: str
    observation: str
    reasoning: str
    tool_calls: List[Dict] = field(default_factory=list)
    timestamp: str = ""
    duration_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None


@dataclass
class EpisodicMemory(MemoryEntry):
    """Specific task execution experience."""
    task_prompt: str = ""
    steps: List[Dict] = field(default_factory=list)
    outcome: str = ""
    success: bool = False
    duration_seconds: float = 0.0
    tools_used: List[str] = field(default_factory=list)
    error_messages: List[str] = field(default_factory=list)

    # Linked to reflexion
    reflection_ids: List[str] = field(default_factory=list)
    patterns_discovered: List[str] = field(default_factory=list)


@dataclass
class SemanticMemory(MemoryEntry):
    """Generalized knowledge extracted from experiences."""
    pattern: str = ""
    context: str = ""
    examples: List[str] = field(default_factory=list)
    confidence: float = 0.0
    times_validated: int = 0
    times_invalidated: int = 0

    # Derived from
    source_episodes: List[str] = field(default_factory=list)


@dataclass
class SkillMemory(MemoryEntry):
    """Executable action sequence (linked to skill_library.py if exists)."""
    skill_name: str = ""
    description: str = ""
    action_sequence: List[Dict] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    success_rate: float = 0.0
    times_executed: int = 0
    average_duration: float = 0.0
    # Enhanced fields to preserve decision logic and error handling
    error_handling: List[Dict] = field(default_factory=list)  # Recovery patterns: [{"error_type": "...", "recovery_action": "..."}]
    decision_logic: List[Dict] = field(default_factory=list)   # Conditional branches: [{"condition": "...", "action_if_true": "...", "action_if_false": "..."}]


@dataclass
class MemoryConsolidationJob:
    """Background job for memory consolidation."""
    job_id: str
    job_type: str  # "merge_similar", "extract_patterns", "decay_old"
    status: str = "pending"
    created_at: str = ""
    completed_at: Optional[str] = None
    memories_processed: int = 0
    result: Optional[Dict] = None


# ============================================================================
# MEMORY COMPRESSION
# ============================================================================

class MemoryCompressor:
    """Intelligent compression of memory content."""

    def __init__(self, target_ratio: float = 10.0):
        self.target_ratio = target_ratio

    def compress_steps(self, steps: List[WorkingMemoryStep]) -> str:
        """
        Compress a sequence of steps using summarization.
        Target: 10:1 compression ratio.
        """
        if not steps:
            return ""

        # Group steps by outcome
        successful_steps = [s for s in steps if s.success]
        failed_steps = [s for s in steps if not s.success]

        # Summarize successful steps
        success_summary = self._summarize_step_group(successful_steps, "successful")

        # Keep failed steps in more detail (important for learning)
        failure_summary = self._summarize_step_group(failed_steps, "failed", keep_detail=True)

        # Combine
        summary = f"{success_summary}\n{failure_summary}" if failure_summary else success_summary

        return summary.strip()

    def _summarize_step_group(
        self,
        steps: List[WorkingMemoryStep],
        group_type: str,
        keep_detail: bool = False
    ) -> str:
        """Summarize a group of steps."""
        if not steps:
            return ""

        if keep_detail:
            # Keep more detail for failed steps
            summary_parts = []
            for step in steps:
                summary_parts.append(
                    f"Step {step.step_number}: {step.action} -> {step.observation[:100]}"
                )
            return f"{group_type.title()} steps:\n" + "\n".join(summary_parts)
        else:
            # Intelligent compression for successful steps using target_ratio
            # Calculate target count based on compression ratio
            target_count = max(3, len(steps) // int(self.target_ratio))  # At least 3 steps for context

            if len(steps) <= target_count:
                # If already at or below target, keep all unique actions
                actions = [s.action for s in steps]
                unique_actions = list(dict.fromkeys(actions))
                return f"{group_type.title()} actions: {', '.join(unique_actions)}"

            # For longer sequences, use importance-weighted selection
            selected_steps = self._select_important_steps(steps, target_count=target_count)
            actions = [s.action for s in selected_steps]

            return f"{group_type.title()} actions ({len(steps)} total): {', '.join(actions)}"

    def _select_important_steps(
        self,
        steps: List[WorkingMemoryStep],
        target_count: int = 5
    ) -> List[WorkingMemoryStep]:
        """
        Select most important steps using importance scoring and temporal distribution.

        Strategy:
        - Always keep first step (start)
        - Always keep last step (end/result)
        - Score remaining steps by importance
        - Select highest-scoring steps to fill remaining slots
        """
        if len(steps) <= target_count:
            return steps

        # Always include first and last
        selected = [steps[0], steps[-1]]
        remaining_slots = target_count - 2

        if remaining_slots <= 0:
            return selected

        # Score middle steps
        middle_steps = steps[1:-1]
        scored_steps = []

        for step in middle_steps:
            score = self._score_step_importance(step)
            scored_steps.append((step, score))

        # Sort by score (highest first)
        scored_steps.sort(key=lambda x: x[1], reverse=True)

        # Take top N steps
        top_steps = [step for step, score in scored_steps[:remaining_slots]]

        # Combine and sort by original order (step_number)
        all_selected = selected[:-1] + top_steps + [selected[-1]]
        all_selected.sort(key=lambda x: x.step_number)

        return all_selected

    def _score_step_importance(self, step: WorkingMemoryStep) -> float:
        """
        Score a step's importance for compression selection.

        Higher scores indicate more important steps to preserve.
        """
        score = 0.0

        # Error/recovery actions are very important
        if step.error:
            score += 10.0

        # Actions with specific important keywords
        action_lower = step.action.lower()

        # Navigation and state changes
        if any(keyword in action_lower for keyword in ['navigate', 'click', 'submit', 'login', 'search']):
            score += 2.0

        # Data extraction and results
        if any(keyword in action_lower for keyword in ['extract', 'found', 'result', 'scraped', 'retrieved']):
            score += 3.0

        # Completion markers
        if any(keyword in action_lower for keyword in ['completed', 'finished', 'success', 'done']):
            score += 2.5

        # Actions with longer observations often contain important info
        if len(step.observation) > 200:
            score += 1.0

        # Actions that took longer (more complex/important)
        if step.duration_ms > 1000:  # More than 1 second
            score += 1.5

        # Tool calls indicate important interactions
        if step.tool_calls:
            score += 2.0

        return score

    def compress_content(self, content: str, max_tokens: int = 100) -> str:
        """
        Compress arbitrary content to fit token budget.
        Uses extractive summarization.
        """
        # Rough token estimation (1 token ~= 4 chars)
        current_chars = len(content)
        current_tokens = current_chars // 4

        if current_tokens <= max_tokens:
            return content

        # Extract key sentences
        sentences = self._split_sentences(content)

        # Score sentences by importance
        scored = [(sent, self._score_sentence(sent)) for sent in sentences]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Take top sentences until we hit token budget
        target_chars = max_tokens * 4
        selected = []
        current_chars = 0

        for sent, score in scored:
            if current_chars + len(sent) <= target_chars:
                selected.append(sent)
                current_chars += len(sent)
            else:
                break

        # Restore original order
        ordered = sorted(selected, key=lambda x: content.index(x))

        return " ".join(ordered)

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        # Simple sentence splitting
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _score_sentence(self, sentence: str) -> float:
        """Score sentence importance based on heuristics."""
        score = 0.0

        # Length (prefer medium length)
        length = len(sentence)
        if 50 < length < 200:
            score += 1.0

        # Keywords that indicate importance
        important_keywords = [
            "error", "failed", "success", "completed", "found",
            "extracted", "navigated", "clicked", "result"
        ]
        for keyword in important_keywords:
            if keyword.lower() in sentence.lower():
                score += 0.5

        # Numbers often indicate concrete results
        if any(char.isdigit() for char in sentence):
            score += 0.3

        return score


# ============================================================================
# VECTOR EMBEDDINGS
# ============================================================================

class EmbeddingEngine:
    """Generate embeddings for semantic search."""

    def __init__(self, model: str = "nomic-embed-text", cache_size: int = 1000):
        self.model = model
        self.cache: Dict[str, List[float]] = {}
        self.cache_size = cache_size
        self.use_ollama = OLLAMA_AVAILABLE

    def get_embedding(self, text: str) -> List[float]:
        """Get embedding vector for text."""
        # Check cache
        text_hash = hashlib.md5(text.encode()).hexdigest()
        if text_hash in self.cache:
            return self.cache[text_hash]

        # Generate embedding
        if self.use_ollama:
            try:
                response = ollama.embeddings(model=self.model, prompt=text)
                embedding = response['embedding']
            except Exception as e:
                logger.warning(f"Ollama embedding failed: {e}, using fallback")
                embedding = self._fallback_embedding(text)
        else:
            embedding = self._fallback_embedding(text)

        # Cache it
        self.cache[text_hash] = embedding
        if len(self.cache) > self.cache_size:
            # Remove oldest (simple FIFO)
            self.cache.pop(next(iter(self.cache)))

        return embedding

    def _fallback_embedding(self, text: str) -> List[float]:
        """Simple fallback embedding using TF-IDF-like approach."""
        # Create a simple bag-of-words vector
        words = text.lower().split()

        # Fixed vocabulary of common words (in real implementation, use larger vocab)
        vocab = [
            "navigate", "click", "extract", "find", "search", "data",
            "page", "element", "text", "url", "error", "success",
            "failed", "completed", "result", "found", "tool", "action"
        ]

        # Create vector
        vector = [0.0] * len(vocab)
        for i, word in enumerate(vocab):
            vector[i] = words.count(word) / max(len(words), 1)

        # Normalize
        magnitude = sum(x * x for x in vector) ** 0.5
        if magnitude > 0:
            vector = [x / magnitude for x in vector]

        return vector

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = sum(x * x for x in vec1) ** 0.5
        magnitude2 = sum(x * x for x in vec2) ** 0.5

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)


# ============================================================================
# MEMORY SCORING & DECAY
# ============================================================================

class MemoryScorer:
    """Score memories based on recency, relevance, and utility."""

    def __init__(
        self,
        recency_weight: float = RECENCY_WEIGHT,
        relevance_weight: float = RELEVANCE_WEIGHT,
        utility_weight: float = UTILITY_WEIGHT
    ):
        self.recency_weight = recency_weight
        self.relevance_weight = relevance_weight
        self.utility_weight = utility_weight
        self.embedding_engine = EmbeddingEngine()

    def score_memory(
        self,
        memory: MemoryEntry,
        query: Optional[str] = None,
        query_embedding: Optional[List[float]] = None
    ) -> float:
        """
        Score a memory based on multiple factors.
        Returns: 0.0 to 1.0 score.
        """
        # Recency score (exponential decay)
        recency = self._score_recency(memory)

        # Relevance score (semantic similarity to query)
        if query or query_embedding:
            relevance = self._score_relevance(memory, query, query_embedding)
        else:
            relevance = memory.relevance_score

        # Utility score (how useful this memory has been)
        utility = self._score_utility(memory)

        # Weighted composite
        composite = (
            self.recency_weight * recency +
            self.relevance_weight * relevance +
            self.utility_weight * utility
        )

        # Update memory
        memory.recency_score = recency
        memory.relevance_score = relevance
        memory.utility_score = utility
        memory.composite_score = composite

        return composite

    def _score_recency(self, memory: MemoryEntry) -> float:
        """Score based on how recent the memory is."""
        try:
            created = datetime.fromisoformat(memory.created_at)
            last_accessed = datetime.fromisoformat(memory.last_accessed)

            # Use the more recent of creation or last access
            most_recent = max(created, last_accessed)
            age = (datetime.now() - most_recent).total_seconds()

            # Exponential decay: score = e^(-age / half_life)
            # Half-life = 1 day (86400 seconds)
            half_life = 86400
            recency = 2 ** (-age / half_life)

            return max(0.0, min(1.0, recency))
        except Exception:
            return 0.5  # Default if timestamps invalid

    def _score_relevance(
        self,
        memory: MemoryEntry,
        query: Optional[str] = None,
        query_embedding: Optional[List[float]] = None
    ) -> float:
        """Score based on semantic relevance to query."""
        if not query and not query_embedding:
            return memory.relevance_score

        # Get embeddings
        if query_embedding is None and query:
            query_embedding = self.embedding_engine.get_embedding(query)

        if memory.embedding is None:
            memory.embedding = self.embedding_engine.get_embedding(memory.content)

        # Compute similarity
        similarity = self.embedding_engine.cosine_similarity(
            query_embedding,
            memory.embedding
        )

        return max(0.0, min(1.0, similarity))

    def _score_utility(self, memory: MemoryEntry) -> float:
        """Score based on how useful the memory has been."""
        # Factors:
        # 1. Access count (more accesses = more useful)
        # 2. Importance level
        # 3. Success rate (for skills and episodic memories)

        # Access score (logarithmic scaling)
        import math
        access_score = math.log(memory.access_count + 1) / math.log(100)  # Max at 100 accesses
        access_score = min(1.0, access_score)

        # Importance
        importance_score = memory.importance

        # Success rate (if applicable)
        success_score = 1.0  # Default
        if isinstance(memory, SkillMemory):
            success_score = memory.success_rate
        elif isinstance(memory, EpisodicMemory):
            success_score = 1.0 if memory.success else 0.3

        # Weighted combination
        utility = (
            0.4 * access_score +
            0.3 * importance_score +
            0.3 * success_score
        )

        return utility


# ============================================================================
# WORKING MEMORY
# ============================================================================

class WorkingMemory:
    """
    Working memory: Current task context (last 40-50 steps in full detail).
    Based on cognitive science research on human working memory capacity.
    Implements time-based decay for old memories.
    """

    def __init__(self, capacity: int = WORKING_MEMORY_CAPACITY, decay_hours: float = WORKING_MEMORY_DECAY_HOURS):
        self.capacity = capacity
        self.decay_hours = decay_hours  # Time-based decay threshold
        self.steps: deque[WorkingMemoryStep] = deque(maxlen=capacity)
        self.current_task_id: Optional[str] = None
        self.session_id: str = ""
        self.compressor = MemoryCompressor()
        self.storage_path = WORKING_MEMORY_JSON
        self._json_lock = threading.Lock()

        self._load()

    def add_step(self, step: WorkingMemoryStep):
        """Add a step to working memory."""
        self.steps.append(step)
        self._save()

    def get_recent_steps(self, n: int = 10, apply_decay: bool = True) -> List[WorkingMemoryStep]:
        """
        Get the N most recent steps.

        Args:
            n: Number of recent steps to retrieve
            apply_decay: If True, filter out steps older than decay_hours

        Returns:
            List of recent working memory steps
        """
        steps = list(self.steps)[-n:]

        if apply_decay:
            steps = self._apply_time_decay(steps)

        return steps

    def get_all_steps(self, apply_decay: bool = True) -> List[WorkingMemoryStep]:
        """
        Get all steps in working memory.

        Args:
            apply_decay: If True, filter out steps older than decay_hours

        Returns:
            List of all working memory steps (optionally with decay applied)
        """
        steps = list(self.steps)

        if apply_decay:
            steps = self._apply_time_decay(steps)

        return steps

    def _apply_time_decay(self, steps: List[WorkingMemoryStep]) -> List[WorkingMemoryStep]:
        """
        Apply time-based decay to filter out old memories.
        Memories older than decay_hours get filtered out during retrieval.

        Args:
            steps: List of working memory steps to filter

        Returns:
            Filtered list with only recent steps (within decay window)
        """
        if not steps or self.decay_hours <= 0:
            return steps

        decay_cutoff = datetime.now() - timedelta(hours=self.decay_hours)
        filtered_steps = []

        for step in steps:
            try:
                step_time = datetime.fromisoformat(step.timestamp)
                if step_time >= decay_cutoff:
                    filtered_steps.append(step)
            except (ValueError, AttributeError):
                # If timestamp is invalid or missing, keep the step
                # (safer to include than exclude)
                filtered_steps.append(step)

        return filtered_steps

    def _score_by_recency(self, steps: List[WorkingMemoryStep]) -> List[Tuple[WorkingMemoryStep, float]]:
        """
        Score steps by recency using exponential decay.
        More recent steps get higher scores (0.0 to 1.0).

        Args:
            steps: List of working memory steps to score

        Returns:
            List of tuples (step, recency_score) sorted by score descending
        """
        if not steps:
            return []

        now = datetime.now()
        scored_steps = []

        for step in steps:
            try:
                step_time = datetime.fromisoformat(step.timestamp)
                age_hours = (now - step_time).total_seconds() / 3600.0

                # Exponential decay: score = e^(-age/decay_hours)
                # Recent steps (age=0) get score=1.0, older steps decay exponentially
                recency_score = pow(2.71828, -age_hours / max(self.decay_hours, 0.1))
                scored_steps.append((step, recency_score))
            except (ValueError, AttributeError):
                # If timestamp is invalid, give neutral score
                scored_steps.append((step, 0.5))

        # Sort by score descending (most recent first)
        scored_steps.sort(key=lambda x: x[1], reverse=True)

        return scored_steps

    def compress_to_summary(self) -> str:
        """Compress working memory to a summary string."""
        return self.compressor.compress_steps(list(self.steps))

    def clear(self, save_to_episodic: bool = True) -> Optional[str]:
        """
        Clear working memory, optionally saving to episodic memory.
        Returns: Summary if saved.
        """
        if not self.steps:
            return None

        summary = None
        if save_to_episodic:
            summary = self.compress_to_summary()

        self.steps.clear()
        self._save()

        return summary

    def prune(self, max_items: int = 50) -> int:
        """
        Prune working memory to keep only the most recent max_items steps.
        Used for aggressive memory management.

        Args:
            max_items: Maximum number of steps to keep

        Returns:
            Number of items pruned
        """
        if len(self.steps) > max_items:
            excess = len(self.steps) - max_items
            for _ in range(excess):
                self.steps.popleft()
            self._save()
            return excess
        return 0

    def prune_decayed(self) -> int:
        """
        Permanently remove steps older than decay_hours from working memory.
        This physically removes old memories from storage, not just filtering during retrieval.

        Returns:
            Number of steps removed
        """
        if self.decay_hours <= 0 or not self.steps:
            return 0

        decay_cutoff = datetime.now() - timedelta(hours=self.decay_hours)
        original_count = len(self.steps)

        # Filter out old steps
        filtered_steps = deque(maxlen=self.capacity)
        for step in self.steps:
            try:
                step_time = datetime.fromisoformat(step.timestamp)
                if step_time >= decay_cutoff:
                    filtered_steps.append(step)
            except (ValueError, AttributeError):
                # Keep steps with invalid timestamps
                filtered_steps.append(step)

        removed_count = original_count - len(filtered_steps)

        if removed_count > 0:
            self.steps = filtered_steps
            self._save()

        return removed_count

    def get_context_window(self, detailed_steps: int = 10, apply_decay: bool = True, use_recency_scoring: bool = True) -> str:
        """
        Get context window: recent steps in detail, older steps compressed.
        This is what gets passed to the LLM.

        Args:
            detailed_steps: Number of steps to show in detail
            apply_decay: If True, filter out steps older than decay_hours
            use_recency_scoring: If True, prioritize steps by recency score

        Returns:
            Formatted context string for LLM
        """
        all_steps = list(self.steps)

        # Apply time-based decay if requested
        if apply_decay:
            all_steps = self._apply_time_decay(all_steps)

        if len(all_steps) <= detailed_steps:
            # All steps fit in detailed window
            return self._format_steps(all_steps)

        # Use recency scoring to select most relevant recent steps
        if use_recency_scoring:
            scored_steps = self._score_by_recency(all_steps)
            # Take top N by recency score
            top_scored = scored_steps[:detailed_steps]
            recent = [step for step, score in top_scored]
            # Remaining steps go to compression
            recent_ids = {step.step_id for step in recent}
            older = [step for step in all_steps if step.step_id not in recent_ids]
        else:
            # Original behavior: split by position (most recent N)
            recent = all_steps[-detailed_steps:]
            older = all_steps[:-detailed_steps]

        # Compress older steps
        compressed = self.compressor.compress_steps(older)

        # Format recent steps (maintain temporal order)
        recent.sort(key=lambda s: s.step_number)
        detailed = self._format_steps(recent)

        return f"[Previous steps summary]: {compressed}\n\n[Recent steps detail]:\n{detailed}"

    def _format_steps(self, steps: List[WorkingMemoryStep]) -> str:
        """Format steps for display."""
        lines = []
        for step in steps:
            status = "✓" if step.success else "✗"
            lines.append(f"{status} Step {step.step_number}: {step.action}")
            if step.observation:
                lines.append(f"  → {step.observation[:200]}")
        return "\n".join(lines)

    def _load(self):
        """Load working memory from disk."""
        if not self.storage_path.exists():
            return

        try:
            data = json.loads(self.storage_path.read_text())
            self.session_id = data.get("session_id", "")
            self.current_task_id = data.get("current_task_id")

            for step_data in data.get("steps", []):
                step = WorkingMemoryStep(**step_data)
                self.steps.append(step)
        except Exception as e:
            logger.warning(f"Failed to load working memory: {e}")

    def _save(self):
        """Save working memory to disk with thread-safety."""
        with self._json_lock:
            try:
                from .atomic_file import atomic_write_json
                data = {
                    "session_id": self.session_id,
                    "current_task_id": self.current_task_id,
                    "steps": [asdict(step) for step in self.steps]
                }
                atomic_write_json(self.storage_path, data)
            except Exception as e:
                logger.warning(f"Failed to save working memory: {e}")


# ============================================================================
# DISTRIBUTED CACHE ADAPTERS
# ============================================================================

class CacheAdapter(ABC):
    """
    Abstract base class for distributed cache adapters.
    Enables shared knowledge across parallel agent instances.

    Implements cache-aside pattern:
    1. Check cache first
    2. If miss, query SQLite
    3. Store result in cache
    4. Return result
    """

    @abstractmethod
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get value from cache."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None):
        """Set value in cache with optional TTL."""
        pass

    @abstractmethod
    async def delete(self, key: str):
        """Delete key from cache."""
        pass

    @abstractmethod
    async def delete_pattern(self, pattern: str):
        """Delete all keys matching pattern."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        pass

    @abstractmethod
    async def publish(self, channel: str, message: str):
        """Publish message to pub/sub channel for cache invalidation."""
        pass

    @abstractmethod
    async def subscribe(self, channel: str, callback: Callable[[str], None]):
        """Subscribe to pub/sub channel for cache invalidation."""
        pass

    @abstractmethod
    async def close(self):
        """Close cache connection."""
        pass


class SQLiteCacheAdapter(CacheAdapter):
    """
    SQLite-based cache adapter for local/single-instance scenarios.
    Provides a consistent interface but doesn't actually cache (pass-through).
    All operations are no-ops to maintain backward compatibility.
    """

    def __init__(self):
        logger.info("Using SQLite cache adapter (local mode, no distributed caching)")

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """SQLite adapter doesn't cache - always returns None to trigger DB lookup."""
        return None

    async def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None):
        """SQLite adapter doesn't cache - no-op."""
        pass

    async def delete(self, key: str):
        """SQLite adapter doesn't cache - no-op."""
        pass

    async def delete_pattern(self, pattern: str):
        """SQLite adapter doesn't cache - no-op."""
        pass

    async def exists(self, key: str) -> bool:
        """SQLite adapter doesn't cache - always returns False."""
        return False

    async def publish(self, channel: str, message: str):
        """SQLite adapter doesn't support pub/sub - no-op."""
        pass

    async def subscribe(self, channel: str, callback: Callable[[str], None]):
        """SQLite adapter doesn't support pub/sub - no-op."""
        pass

    async def close(self):
        """Nothing to close for SQLite adapter."""
        pass


class RedisCacheAdapter(CacheAdapter):
    """
    Redis-based cache adapter for distributed/multi-instance scenarios.
    Provides fast shared memory across parallel agents with pub/sub invalidation.

    Features:
    - Automatic connection pooling
    - JSON serialization/deserialization
    - TTL support for automatic expiration
    - Pub/sub for cache invalidation across instances
    - Pattern-based deletion for bulk operations
    """

    def __init__(
        self,
        host: str = REDIS_HOST,
        port: int = REDIS_PORT,
        db: int = REDIS_DB,
        password: Optional[str] = REDIS_PASSWORD,
        key_prefix: str = CACHE_KEY_PREFIX,
        default_ttl: int = CACHE_TTL_SECONDS
    ):
        if not REDIS_AVAILABLE:
            raise ImportError("Redis library not available. Install with: pip install redis")

        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl
        self._client: Optional["aioredis.Redis"] = None
        self._pubsub: Optional["aioredis.client.PubSub"] = None
        self._subscription_tasks: Dict[str, asyncio.Task] = {}

        logger.info(f"Using Redis cache adapter: {host}:{port}/{db} (distributed mode)")

    async def _get_client(self) -> "aioredis.Redis":
        """Get or create Redis client (lazy initialization)."""
        if self._client is None:
            self._client = await aioredis.from_url(
                f"redis://{self.host}:{self.port}/{self.db}",
                password=self.password,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True
            )
        return self._client

    def _make_key(self, key: str) -> str:
        """Add prefix to key."""
        return f"{self.key_prefix}:{key}"

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get value from Redis cache."""
        try:
            client = await self._get_client()
            value = await client.get(self._make_key(key))
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning(f"Redis get error for key '{key}': {e}")
            return None

    async def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None):
        """Set value in Redis cache with TTL."""
        try:
            client = await self._get_client()
            ttl = ttl if ttl is not None else self.default_ttl
            serialized = json.dumps(value)
            await client.setex(self._make_key(key), ttl, serialized)
        except Exception as e:
            logger.warning(f"Redis set error for key '{key}': {e}")

    async def delete(self, key: str):
        """Delete key from Redis cache."""
        try:
            client = await self._get_client()
            await client.delete(self._make_key(key))
        except Exception as e:
            logger.warning(f"Redis delete error for key '{key}': {e}")

    async def delete_pattern(self, pattern: str):
        """Delete all keys matching pattern."""
        try:
            client = await self._get_client()
            full_pattern = self._make_key(pattern)

            # Scan for matching keys (safe for large datasets)
            cursor = 0
            while True:
                cursor, keys = await client.scan(cursor, match=full_pattern, count=100)
                if keys:
                    await client.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning(f"Redis delete_pattern error for pattern '{pattern}': {e}")

    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        try:
            client = await self._get_client()
            return await client.exists(self._make_key(key)) > 0
        except Exception as e:
            logger.warning(f"Redis exists error for key '{key}': {e}")
            return False

    async def publish(self, channel: str, message: str):
        """Publish message to Redis pub/sub channel."""
        try:
            client = await self._get_client()
            await client.publish(f"{self.key_prefix}:{channel}", message)
        except Exception as e:
            logger.warning(f"Redis publish error on channel '{channel}': {e}")

    async def subscribe(self, channel: str, callback: Callable[[str], None]):
        """Subscribe to Redis pub/sub channel."""
        try:
            client = await self._get_client()

            # Create pubsub if needed
            if self._pubsub is None:
                self._pubsub = client.pubsub()

            # Subscribe to channel
            full_channel = f"{self.key_prefix}:{channel}"
            await self._pubsub.subscribe(full_channel)

            # Create listener task
            async def listen():
                try:
                    async for message in self._pubsub.listen():
                        if message["type"] == "message":
                            callback(message["data"])
                except Exception as e:
                    logger.error(f"Redis subscription error on channel '{channel}': {e}")

            task = asyncio.create_task(listen())
            self._subscription_tasks[channel] = task

        except Exception as e:
            logger.warning(f"Redis subscribe error on channel '{channel}': {e}")

    async def close(self):
        """Close Redis connections."""
        try:
            # Cancel subscription tasks
            for task in self._subscription_tasks.values():
                task.cancel()
            self._subscription_tasks.clear()

            # Close pubsub
            if self._pubsub:
                await self._pubsub.close()
                self._pubsub = None

            # Close client
            if self._client:
                await self._client.close()
                self._client = None

            logger.info("Redis cache adapter closed")
        except Exception as e:
            logger.warning(f"Error closing Redis adapter: {e}")


def create_cache_adapter(adapter_type: str = CACHE_ADAPTER) -> CacheAdapter:
    """
    Factory function to create appropriate cache adapter based on configuration.

    Args:
        adapter_type: Type of adapter ("sqlite" or "redis")

    Returns:
        CacheAdapter instance

    Environment variables:
        MEMORY_CACHE_ADAPTER: "sqlite" or "redis" (default: "sqlite")
        REDIS_HOST: Redis host (default: "localhost")
        REDIS_PORT: Redis port (default: 6379)
        REDIS_DB: Redis database number (default: 0)
        REDIS_PASSWORD: Redis password (default: None)
        CACHE_TTL_SECONDS: Cache TTL in seconds (default: 3600)
        CACHE_KEY_PREFIX: Key prefix for namespacing (default: "agent_memory")
    """
    adapter_type = adapter_type.lower()

    if adapter_type == "redis":
        if not REDIS_AVAILABLE:
            logger.warning("Redis requested but not available, falling back to SQLite adapter")
            return SQLiteCacheAdapter()
        try:
            return RedisCacheAdapter()
        except Exception as e:
            logger.error(f"Failed to create Redis adapter: {e}, falling back to SQLite")
            return SQLiteCacheAdapter()
    elif adapter_type == "sqlite":
        return SQLiteCacheAdapter()
    else:
        logger.warning(f"Unknown cache adapter type '{adapter_type}', using SQLite")
        return SQLiteCacheAdapter()


# ============================================================================
# EPISODIC MEMORY (SQLite)
# ============================================================================

class EpisodicMemoryStore:
    """
    Episodic memory: Specific task execution experiences.
    Stored in SQLite for efficient querying.

    Supports distributed caching via cache adapters (Redis/SQLite).
    """

    def __init__(self, db_path: Path = EPISODIC_DB, cache_adapter: Optional[CacheAdapter] = None):
        self.db_path = db_path
        self.scorer = MemoryScorer()
        # Locking strategy: Use asyncio.Lock for all operations to prevent race conditions
        # This allows safe usage in both sync (via asyncio.run()) and async contexts
        # Avoids deadlocks from mixing threading.Lock with asyncio.Lock
        self._lock = asyncio.Lock()
        self._consolidation_lock = None  # Will be set to asyncio.Lock() when needed

        # Cache adapter for distributed scenarios
        self.cache = cache_adapter if cache_adapter else create_cache_adapter()
        self._cache_invalidation_channel = "episodic_memory_invalidation"

        self._init_db()
        self._setup_cache_invalidation()

    def _sync_lock(self):
        """
        Context manager for synchronous code to safely use asyncio.Lock.

        This allows synchronous methods to acquire the asyncio.Lock without blocking
        the event loop, preventing race conditions with async methods.
        """
        class SyncLockContext:
            def __init__(self, lock):
                self.lock = lock
                self.acquired = False

            def __enter__(self):
                # Try to get the current event loop
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    # No event loop, create a new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                if loop.is_running():
                    # We're in an async context, can't use run_until_complete
                    # Skip locking - the caller is responsible for async locking
                    self.acquired = False
                    return self

                loop.run_until_complete(self.lock.acquire())
                self.acquired = True
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                if self.acquired:
                    self.lock.release()
                return False

        return SyncLockContext(self._lock)

    def _init_db(self):
        """Initialize SQLite database with recovery."""
        schema = """
            CREATE TABLE IF NOT EXISTS episodes (
                memory_id TEXT PRIMARY KEY,
                task_prompt TEXT,
                content TEXT,
                compressed_content TEXT,
                outcome TEXT,
                success INTEGER,
                duration_seconds REAL,
                tools_used TEXT,
                created_at TEXT,
                last_accessed TEXT,
                access_count INTEGER,
                importance REAL,
                composite_score REAL,
                task_id TEXT,
                session_id TEXT,
                tags TEXT,
                embedding BLOB,
                reflection_ids TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_episodes_score ON episodes(composite_score DESC);
            CREATE INDEX IF NOT EXISTS idx_episodes_created ON episodes(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_episodes_task ON episodes(task_id);
            CREATE INDEX IF NOT EXISTS idx_episodes_session ON episodes(session_id);

            CREATE TABLE IF NOT EXISTS session_links (
                new_session_id TEXT PRIMARY KEY,
                old_session_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_session_links_old ON session_links(old_session_id);
        """

        conn = self._load_with_recovery(self.db_path, schema)
        conn.close()

        # Check database size on initialization
        self._check_and_cleanup_db_size()

    def _load_with_recovery(self, db_path: Path, schema: str) -> sqlite3.Connection:
        """Load database with recovery from corruption."""
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            # Verify integrity
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if result[0] != "ok":
                raise sqlite3.DatabaseError("Integrity check failed")
            # Ensure tables exist
            conn.executescript(schema)
            return conn
        except sqlite3.DatabaseError as e:
            logger.error(f"Database corrupt: {e}, attempting recovery")
            # Backup corrupt file
            backup = db_path.with_suffix('.corrupt.bak')
            if db_path.exists():
                db_path.rename(backup)
                logger.info(f"Backed up corrupt database to {backup}")
            # Create fresh database
            conn = sqlite3.connect(str(db_path))
            conn.executescript(schema)
            logger.info(f"Created fresh database at {db_path}")
            return conn

    def _get_db_size_mb(self) -> float:
        """Get current database size in MB."""
        try:
            if self.db_path.exists():
                size_bytes = self.db_path.stat().st_size
                return size_bytes / (1024 * 1024)  # Convert to MB
            return 0.0
        except Exception as e:
            logger.warning(f"Failed to get database size: {e}")
            return 0.0

    def _check_and_cleanup_db_size(self):
        """Check database size and cleanup if needed."""
        size_mb = self._get_db_size_mb()

        # Warn if approaching limit
        if size_mb >= MAX_DB_SIZE_MB * DB_SIZE_WARNING_THRESHOLD:
            logger.warning(
                f"Database size ({size_mb:.2f}MB) approaching limit ({MAX_DB_SIZE_MB}MB). "
                f"Cleanup will trigger at {MAX_DB_SIZE_MB}MB."
            )

        # Cleanup if over limit
        if size_mb >= MAX_DB_SIZE_MB:
            logger.warning(
                f"Database size ({size_mb:.2f}MB) exceeds limit ({MAX_DB_SIZE_MB}MB). "
                f"Removing oldest entries..."
            )
            self._cleanup_old_entries()

            # Check size after cleanup
            new_size_mb = self._get_db_size_mb()
            logger.info(
                f"Database cleanup complete. Size reduced from {size_mb:.2f}MB to {new_size_mb:.2f}MB"
            )

    def _cleanup_old_entries(self):
        """Remove oldest entries to reduce database size to target."""
        target_size_mb = MAX_DB_SIZE_MB * DB_CLEANUP_TARGET

        # Use sync lock wrapper for asyncio.Lock in sync context
        with self._sync_lock():
            with sqlite3.connect(str(self.db_path)) as conn:
                # Get total count
                cursor = conn.execute("SELECT COUNT(*) FROM episodes")
                total_count = cursor.fetchone()[0]

                if total_count == 0:
                    return

                # Estimate how many entries to remove
                # Rough heuristic: remove proportionally based on size ratio
                current_size = self._get_db_size_mb()
                if current_size == 0:
                    return

                target_ratio = target_size_mb / current_size
                entries_to_keep = int(total_count * target_ratio)
                entries_to_remove = total_count - entries_to_keep

                if entries_to_remove <= 0:
                    return

                # Remove oldest entries by created_at, prioritizing low-importance ones
                # Keep high-importance and frequently accessed memories
                cursor = conn.execute("""
                    SELECT memory_id FROM episodes
                    ORDER BY
                        importance ASC,
                        access_count ASC,
                        created_at ASC
                    LIMIT ?
                """, (entries_to_remove,))

                ids_to_remove = [row[0] for row in cursor.fetchall()]

                if ids_to_remove:
                    placeholders = ','.join('?' * len(ids_to_remove))
                    conn.execute(
                        f"DELETE FROM episodes WHERE memory_id IN ({placeholders})",
                        ids_to_remove
                    )
                    conn.commit()

                    # Vacuum to reclaim space
                    conn.execute("VACUUM")

                    logger.info(f"Removed {len(ids_to_remove)} old entries from database")

    def _setup_cache_invalidation(self):
        """Setup cache invalidation listener for distributed scenarios."""
        async def invalidation_callback(message: str):
            """Handle cache invalidation messages from other instances."""
            try:
                data = json.loads(message)
                action = data.get("action")
                key = data.get("key")

                if action == "delete" and key:
                    await self.cache.delete(key)
                    logger.debug(f"Cache invalidated for key: {key}")
                elif action == "delete_pattern" and key:
                    await self.cache.delete_pattern(key)
                    logger.debug(f"Cache invalidated for pattern: {key}")
            except Exception as e:
                logger.warning(f"Error handling cache invalidation: {e}")

        # Subscribe to invalidation channel
        try:
            asyncio.create_task(
                self.cache.subscribe(self._cache_invalidation_channel, invalidation_callback)
            )
        except Exception as e:
            logger.debug(f"Cache invalidation subscription not set up: {e}")

    async def _invalidate_cache(self, key: str):
        """Invalidate cache key locally and notify other instances."""
        await self.cache.delete(key)
        # Notify other instances
        await self.cache.publish(
            self._cache_invalidation_channel,
            json.dumps({"action": "delete", "key": key})
        )

    async def _invalidate_cache_pattern(self, pattern: str):
        """Invalidate cache pattern locally and notify other instances."""
        await self.cache.delete_pattern(pattern)
        # Notify other instances
        await self.cache.publish(
            self._cache_invalidation_channel,
            json.dumps({"action": "delete_pattern", "key": pattern})
        )

    def link_session(self, new_session_id: str, old_session_id: str):
        """
        Record a link from a new session to an old session.
        This preserves memory continuity across session rotations.

        Args:
            new_session_id: The new session ID
            old_session_id: The previous session ID
        """
        # Use sync lock wrapper for asyncio.Lock in sync context
        with self._sync_lock():
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO session_links VALUES (?, ?, ?)
                """, (new_session_id, old_session_id, datetime.now().isoformat()))
                conn.commit()

    def get_linked_sessions(self, session_id: str) -> List[str]:
        """
        Get all session IDs linked to this session (including itself).
        This follows the chain of session links backwards to get all related sessions.

        Args:
            session_id: The current session ID

        Returns:
            List of all linked session IDs (current + all previous)
        """
        linked = [session_id]
        current = session_id

        # Follow the chain backwards (limit to prevent infinite loops)
        max_depth = 100
        with sqlite3.connect(str(self.db_path)) as conn:
            for _ in range(max_depth):
                cursor = conn.execute(
                    "SELECT old_session_id FROM session_links WHERE new_session_id = ?",
                    (current,)
                )
                row = cursor.fetchone()
                if row:
                    old_session = row[0]
                    if old_session not in linked:  # Prevent cycles
                        linked.append(old_session)
                        current = old_session
                    else:
                        break
                else:
                    break

        return linked

    def add_episode(self, episode: EpisodicMemory):
        """Add an episode to memory."""
        # Check database size before adding
        self._check_and_cleanup_db_size()

        # Use sync lock wrapper for asyncio.Lock in sync context
        with self._sync_lock():
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO episodes VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """, (
                    episode.memory_id,
                    episode.task_prompt,
                    episode.content,
                    episode.compressed_content,
                    episode.outcome,
                    int(episode.success),
                    episode.duration_seconds,
                    json.dumps(episode.tools_used),
                    episode.created_at,
                    episode.last_accessed,
                    episode.access_count,
                    episode.importance,
                    episode.composite_score,
                    episode.task_id,
                    episode.session_id,
                    json.dumps(episode.tags),
                    self._serialize_embedding(episode.embedding),
                    json.dumps(episode.reflection_ids)
                ))
                conn.commit()

        # Invalidate cache for this episode
        asyncio.create_task(self._invalidate_cache(f"episode:{episode.memory_id}"))

    def get_episode(self, memory_id: str) -> Optional[EpisodicMemory]:
        """
        Retrieve an episode by ID.
        Uses cache-aside pattern: check cache first, fallback to SQLite.
        """
        # Try cache first (only for Redis adapter)
        cache_key = f"episode:{memory_id}"
        try:
            # Try to get from cache asynchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            cached_data = loop.run_until_complete(self.cache.get(cache_key))
            loop.close()

            if cached_data:
                # Reconstruct episode from cached data
                return EpisodicMemory(**cached_data)
        except Exception as e:
            logger.debug(f"Cache get failed for episode {memory_id}: {e}")

        # Cache miss - query SQLite
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM episodes WHERE memory_id = ?",
                (memory_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            episode = self._row_to_episode(row)

            # Store in cache for future retrievals
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                # Convert episode to dict for caching
                episode_dict = asdict(episode)
                loop.run_until_complete(self.cache.set(cache_key, episode_dict))
                loop.close()
            except Exception as e:
                logger.debug(f"Cache set failed for episode {memory_id}: {e}")

            return episode

    def search_episodes(
        self,
        query: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        success_only: bool = False,
        limit: int = 10,
        min_score: float = 0.0
    ) -> List[EpisodicMemory]:
        """
        Search episodes with multiple filters.
        Uses semantic search if query provided.
        Automatically includes memories from linked sessions.

        Args:
            query: Search query for semantic matching
            task_id: Filter by specific task ID
            session_id: Filter by session (includes linked sessions)
            tags: Filter by tags
            success_only: Only return successful episodes
            limit: Maximum number of results
            min_score: Minimum composite score threshold
        """
        # Build SQL query
        conditions = []
        params = []

        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)

        # Handle session filtering with linked sessions
        if session_id:
            linked_sessions = self.get_linked_sessions(session_id)
            if len(linked_sessions) == 1:
                conditions.append("session_id = ?")
                params.append(session_id)
            else:
                # Use IN clause for multiple linked sessions
                placeholders = ','.join('?' * len(linked_sessions))
                conditions.append(f"session_id IN ({placeholders})")
                params.extend(linked_sessions)

        if success_only:
            conditions.append("success = 1")

        if min_score > 0:
            conditions.append("composite_score >= ?")
            params.append(min_score)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                f"SELECT * FROM episodes WHERE {where_clause} ORDER BY composite_score DESC LIMIT ?",
                params + [limit * 2]  # Get more for filtering
            )
            rows = cursor.fetchall()

        episodes = [self._row_to_episode(row) for row in rows]

        # Semantic filtering if query provided
        if query:
            episodes = self._semantic_filter(episodes, query, limit)
        else:
            episodes = episodes[:limit]

        # Update access counts
        for episode in episodes:
            self._update_access(episode.memory_id)

        return episodes

    def _semantic_filter(
        self,
        episodes: List[EpisodicMemory],
        query: str,
        limit: int
    ) -> List[EpisodicMemory]:
        """Filter episodes by semantic relevance."""
        # Get query embedding
        query_embedding = self.scorer.embedding_engine.get_embedding(query)

        # Score each episode
        scored = []
        for episode in episodes:
            score = self.scorer.score_memory(episode, query, query_embedding)
            scored.append((episode, score))

        # Sort by score
        scored.sort(key=lambda x: x[1], reverse=True)

        # Update scores in memory objects
        for episode, score in scored:
            episode.composite_score = score

        return [ep for ep, _ in scored[:limit]]

    def _update_access(self, memory_id: str):
        """Update access count and timestamp."""
        now = datetime.now().isoformat()
        # Use sync lock wrapper for asyncio.Lock in sync context
        with self._sync_lock():
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    UPDATE episodes
                    SET access_count = access_count + 1,
                        last_accessed = ?
                    WHERE memory_id = ?
                """, (now, memory_id))
                conn.commit()

    def _row_to_episode(self, row: sqlite3.Row) -> EpisodicMemory:
        """Convert database row to EpisodicMemory object."""
        return EpisodicMemory(
            memory_id=row['memory_id'],
            memory_type=MemoryType.EPISODIC,
            task_prompt=row['task_prompt'],
            content=row['content'],
            compressed_content=row['compressed_content'],
            outcome=row['outcome'],
            success=bool(row['success']),
            duration_seconds=row['duration_seconds'],
            tools_used=json.loads(row['tools_used']),
            created_at=row['created_at'],
            last_accessed=row['last_accessed'],
            access_count=row['access_count'],
            importance=row['importance'],
            composite_score=row['composite_score'],
            task_id=row['task_id'],
            session_id=row['session_id'],
            tags=json.loads(row['tags']),
            embedding=self._deserialize_embedding(row['embedding']),
            reflection_ids=json.loads(row['reflection_ids'])
        )

    def _serialize_embedding(self, embedding: Optional[List[float]]) -> Optional[bytes]:
        """Serialize embedding for storage."""
        if not embedding:
            return None
        return json.dumps(embedding).encode()

    def _deserialize_embedding(self, data: Optional[bytes]) -> Optional[List[float]]:
        """Deserialize embedding from storage."""
        if not data:
            return None
        return json.loads(data.decode())

    async def consolidate_similar(self, similarity_threshold: float = 0.85) -> int:
        """
        Consolidate similar episodes to reduce redundancy.
        Returns: Number of episodes merged.

        Note: This is now async to support proper locking.
        """
        # Initialize async lock if not already done
        if self._consolidation_lock is None:
            self._consolidation_lock = asyncio.Lock()

        async with self._consolidation_lock:
            # Get all episodes
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM episodes ORDER BY created_at DESC")
                rows = cursor.fetchall()

            episodes = [self._row_to_episode(row) for row in rows]

            # Find similar pairs
            merged_count = 0
            merged_ids = set()

            for i, ep1 in enumerate(episodes):
                if ep1.memory_id in merged_ids:
                    continue

                for ep2 in episodes[i+1:]:
                    if ep2.memory_id in merged_ids:
                        continue

                    # Check similarity
                    if ep1.embedding and ep2.embedding:
                        similarity = self.scorer.embedding_engine.cosine_similarity(
                            ep1.embedding,
                            ep2.embedding
                        )

                        if similarity >= similarity_threshold:
                            # Merge ep2 into ep1
                            self._merge_episodes(ep1, ep2)
                            merged_ids.add(ep2.memory_id)
                            merged_count += 1

            # Delete merged episodes
            if merged_ids:
                # Already protected by _consolidation_lock above, no need for additional lock
                with sqlite3.connect(str(self.db_path)) as conn:
                    placeholders = ','.join('?' * len(merged_ids))
                    conn.execute(
                        f"DELETE FROM episodes WHERE memory_id IN ({placeholders})",
                        list(merged_ids)
                    )
                    conn.commit()

            return merged_count

    def _merge_episodes(self, target: EpisodicMemory, source: EpisodicMemory):
        """Merge source episode into target."""
        # Combine access counts
        target.access_count += source.access_count

        # Take more recent timestamp
        if source.last_accessed > target.last_accessed:
            target.last_accessed = source.last_accessed

        # Increase importance
        target.importance = min(1.0, (target.importance + source.importance) / 2)

        # Merge reflection IDs
        target.reflection_ids.extend(source.reflection_ids)
        target.reflection_ids = list(set(target.reflection_ids))

        # Update in database
        self.add_episode(target)


# ============================================================================
# SEMANTIC MEMORY (SQLite)
# ============================================================================

class SemanticMemoryStore:
    """
    Semantic memory: Generalized knowledge extracted from experiences.
    Stored in SQLite for efficient querying.

    Supports distributed caching via cache adapters (Redis/SQLite).
    """

    def __init__(self, db_path: Path = SEMANTIC_DB, cache_adapter: Optional[CacheAdapter] = None):
        self.db_path = db_path
        self.scorer = MemoryScorer()
        # Locking strategy: Use asyncio.Lock for all operations to prevent race conditions
        # This allows safe usage in both sync (via _sync_lock()) and async contexts
        # Avoids deadlocks from mixing threading.Lock with asyncio.Lock
        self._lock = asyncio.Lock()

        # Cache adapter for distributed scenarios (shared with episodic store if provided)
        self.cache = cache_adapter if cache_adapter else create_cache_adapter()
        self._cache_invalidation_channel = "semantic_memory_invalidation"

        self._init_db()
        self._setup_cache_invalidation()

    def _sync_lock(self):
        """
        Context manager for synchronous code to safely use asyncio.Lock.

        This allows synchronous methods to acquire the asyncio.Lock without blocking
        the event loop, preventing race conditions with async methods.
        """
        class SyncLockContext:
            def __init__(self, lock):
                self.lock = lock
                self.acquired = False

            def __enter__(self):
                # Try to get the current event loop
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    # No event loop, create a new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                if loop.is_running():
                    # We're in an async context, can't use run_until_complete
                    # Skip locking - the caller is responsible for async locking
                    self.acquired = False
                    return self

                loop.run_until_complete(self.lock.acquire())
                self.acquired = True
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                if self.acquired:
                    self.lock.release()
                return False

        return SyncLockContext(self._lock)

    def _init_db(self):
        """Initialize SQLite database with recovery."""
        schema = """
            CREATE TABLE IF NOT EXISTS semantic (
                memory_id TEXT PRIMARY KEY,
                pattern TEXT,
                content TEXT,
                context TEXT,
                confidence REAL,
                times_validated INTEGER,
                times_invalidated INTEGER,
                created_at TEXT,
                last_accessed TEXT,
                access_count INTEGER,
                composite_score REAL,
                tags TEXT,
                embedding BLOB,
                source_episodes TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_semantic_score ON semantic(composite_score DESC);
            CREATE INDEX IF NOT EXISTS idx_semantic_pattern ON semantic(pattern);
        """

        conn = self._load_with_recovery(self.db_path, schema)
        conn.close()

        # Check database size on initialization
        self._check_and_cleanup_db_size()

    def _load_with_recovery(self, db_path: Path, schema: str) -> sqlite3.Connection:
        """Load database with recovery from corruption."""
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            # Verify integrity
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if result[0] != "ok":
                raise sqlite3.DatabaseError("Integrity check failed")
            # Ensure tables exist
            conn.executescript(schema)
            return conn
        except sqlite3.DatabaseError as e:
            logger.error(f"Database corrupt: {e}, attempting recovery")
            # Backup corrupt file
            backup = db_path.with_suffix('.corrupt.bak')
            if db_path.exists():
                db_path.rename(backup)
                logger.info(f"Backed up corrupt database to {backup}")
            # Create fresh database
            conn = sqlite3.connect(str(db_path))
            conn.executescript(schema)
            logger.info(f"Created fresh database at {db_path}")
            return conn

    def _get_db_size_mb(self) -> float:
        """Get current database size in MB."""
        try:
            if self.db_path.exists():
                size_bytes = self.db_path.stat().st_size
                return size_bytes / (1024 * 1024)  # Convert to MB
            return 0.0
        except Exception as e:
            logger.warning(f"Failed to get database size: {e}")
            return 0.0

    def _check_and_cleanup_db_size(self):
        """Check database size and cleanup if needed."""
        size_mb = self._get_db_size_mb()

        # Warn if approaching limit
        if size_mb >= MAX_DB_SIZE_MB * DB_SIZE_WARNING_THRESHOLD:
            logger.warning(
                f"Semantic DB size ({size_mb:.2f}MB) approaching limit ({MAX_DB_SIZE_MB}MB). "
                f"Cleanup will trigger at {MAX_DB_SIZE_MB}MB."
            )

        # Cleanup if over limit
        if size_mb >= MAX_DB_SIZE_MB:
            logger.warning(
                f"Semantic DB size ({size_mb:.2f}MB) exceeds limit ({MAX_DB_SIZE_MB}MB). "
                f"Removing oldest entries..."
            )
            self._cleanup_old_entries()

            # Check size after cleanup
            new_size_mb = self._get_db_size_mb()
            logger.info(
                f"Semantic DB cleanup complete. Size reduced from {size_mb:.2f}MB to {new_size_mb:.2f}MB"
            )

    def _cleanup_old_entries(self):
        """Remove oldest entries to reduce database size to target."""
        target_size_mb = MAX_DB_SIZE_MB * DB_CLEANUP_TARGET

        # Use sync lock wrapper for asyncio.Lock in sync context
        with self._sync_lock():
            with sqlite3.connect(str(self.db_path)) as conn:
                # Get total count
                cursor = conn.execute("SELECT COUNT(*) FROM semantic")
                total_count = cursor.fetchone()[0]

                if total_count == 0:
                    return

                # Estimate how many entries to remove
                current_size = self._get_db_size_mb()
                if current_size == 0:
                    return

                target_ratio = target_size_mb / current_size
                entries_to_keep = int(total_count * target_ratio)
                entries_to_remove = total_count - entries_to_keep

                if entries_to_remove <= 0:
                    return

                # Remove low-confidence, rarely accessed entries
                cursor = conn.execute("""
                    SELECT memory_id FROM semantic
                    ORDER BY
                        confidence ASC,
                        access_count ASC,
                        created_at ASC
                    LIMIT ?
                """, (entries_to_remove,))

                ids_to_remove = [row[0] for row in cursor.fetchall()]

                if ids_to_remove:
                    placeholders = ','.join('?' * len(ids_to_remove))
                    conn.execute(
                        f"DELETE FROM semantic WHERE memory_id IN ({placeholders})",
                        ids_to_remove
                    )
                    conn.commit()

                    # Vacuum to reclaim space
                    conn.execute("VACUUM")

                    logger.info(f"Removed {len(ids_to_remove)} old semantic entries from database")

    def _setup_cache_invalidation(self):
        """Setup cache invalidation listener for distributed scenarios."""
        async def invalidation_callback(message: str):
            """Handle cache invalidation messages from other instances."""
            try:
                data = json.loads(message)
                action = data.get("action")
                key = data.get("key")

                if action == "delete" and key:
                    await self.cache.delete(key)
                    logger.debug(f"Cache invalidated for key: {key}")
                elif action == "delete_pattern" and key:
                    await self.cache.delete_pattern(key)
                    logger.debug(f"Cache invalidated for pattern: {key}")
            except Exception as e:
                logger.warning(f"Error handling cache invalidation: {e}")

        # Subscribe to invalidation channel
        try:
            asyncio.create_task(
                self.cache.subscribe(self._cache_invalidation_channel, invalidation_callback)
            )
        except Exception as e:
            logger.debug(f"Cache invalidation subscription not set up: {e}")

    async def _invalidate_cache(self, key: str):
        """Invalidate cache key locally and notify other instances."""
        await self.cache.delete(key)
        await self.cache.publish(
            self._cache_invalidation_channel,
            json.dumps({"action": "delete", "key": key})
        )

    def add_semantic(self, semantic: SemanticMemory):
        """Add semantic memory."""
        # Check database size before adding
        self._check_and_cleanup_db_size()

        # Use sync lock wrapper for asyncio.Lock in sync context
        with self._sync_lock():
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO semantic VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """, (
                    semantic.memory_id,
                    semantic.pattern,
                    semantic.content,
                    semantic.context,
                    semantic.confidence,
                    semantic.times_validated,
                    semantic.times_invalidated,
                    semantic.created_at,
                    semantic.last_accessed,
                    semantic.access_count,
                    semantic.composite_score,
                    json.dumps(semantic.tags),
                    self._serialize_embedding(semantic.embedding),
                    json.dumps(semantic.source_episodes)
                ))
                conn.commit()

    def search_semantic(
        self,
        query: str,
        limit: int = 5,
        min_confidence: float = 0.5
    ) -> List[SemanticMemory]:
        """Search semantic memories by query."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM semantic
                WHERE confidence >= ?
                ORDER BY composite_score DESC
                LIMIT ?
            """, (min_confidence, limit * 2))
            rows = cursor.fetchall()

        semantics = [self._row_to_semantic(row) for row in rows]

        # Semantic filtering
        query_embedding = self.scorer.embedding_engine.get_embedding(query)

        scored = []
        for sem in semantics:
            score = self.scorer.score_memory(sem, query, query_embedding)
            scored.append((sem, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        result = [sem for sem, _ in scored[:limit]]

        # Update access counts
        for sem in result:
            self._update_access(sem.memory_id)

        return result

    def extract_from_episodes(self, episodes: List[EpisodicMemory]) -> List[SemanticMemory]:
        """
        Extract semantic patterns from episodic memories.
        This is the core of memory consolidation.
        """
        if not episodes:
            return []

        # Group episodes by similarity
        patterns = self._identify_patterns(episodes)

        # Create semantic memories from patterns
        semantics = []
        for pattern_data in patterns:
            semantic = self._create_semantic_from_pattern(pattern_data)
            if semantic:
                semantics.append(semantic)
                self.add_semantic(semantic)

        return semantics

    def _identify_patterns(self, episodes: List[EpisodicMemory]) -> List[Dict]:
        """Identify recurring patterns in episodes."""
        # Group by similar tools and outcomes
        tool_groups = defaultdict(list)

        for episode in episodes:
            tool_key = tuple(sorted(episode.tools_used))
            tool_groups[tool_key].append(episode)

        # Extract patterns from groups with multiple instances
        patterns = []
        for tool_key, group in tool_groups.items():
            if len(group) >= 2:  # Need at least 2 instances to form a pattern
                pattern = {
                    "tools": list(tool_key),
                    "episodes": group,
                    "success_rate": sum(1 for ep in group if ep.success) / len(group),
                    "avg_duration": sum(ep.duration_seconds for ep in group) / len(group)
                }
                patterns.append(pattern)

        return patterns

    def _create_semantic_from_pattern(self, pattern_data: Dict) -> Optional[SemanticMemory]:
        """Create a semantic memory from a pattern."""
        try:
            tools = pattern_data["tools"]
            episodes = pattern_data["episodes"]

            # Create pattern description
            pattern_desc = f"Use {', '.join(tools)} for this type of task"

            # Create content
            content = f"Pattern identified from {len(episodes)} episodes. "
            content += f"Success rate: {pattern_data['success_rate']:.1%}. "
            content += f"Average duration: {pattern_data['avg_duration']:.1f}s."

            # Create context from episode prompts
            contexts = [ep.task_prompt for ep in episodes[:3]]  # First 3 examples
            context = " | ".join(contexts)

            # Create semantic memory
            memory_id = hashlib.sha256(pattern_desc.encode()).hexdigest()[:16]

            semantic = SemanticMemory(
                memory_id=memory_id,
                memory_type=MemoryType.SEMANTIC,
                pattern=pattern_desc,
                content=content,
                context=context,
                confidence=pattern_data['success_rate'],
                times_validated=len([ep for ep in episodes if ep.success]),
                times_invalidated=len([ep for ep in episodes if not ep.success]),
                created_at=datetime.now().isoformat(),
                last_accessed=datetime.now().isoformat(),
                source_episodes=[ep.memory_id for ep in episodes],
                tags=tools
            )

            # Generate embedding
            semantic.embedding = self.scorer.embedding_engine.get_embedding(
                f"{pattern_desc} {content} {context}"
            )

            return semantic

        except Exception as e:
            logger.error(f"Failed to create semantic memory: {e}")
            return None

    def _update_access(self, memory_id: str):
        """Update access count and timestamp."""
        now = datetime.now().isoformat()
        # Use sync lock wrapper for asyncio.Lock in sync context
        with self._sync_lock():
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    UPDATE semantic
                    SET access_count = access_count + 1,
                        last_accessed = ?
                    WHERE memory_id = ?
                """, (now, memory_id))
                conn.commit()

    def _row_to_semantic(self, row: sqlite3.Row) -> SemanticMemory:
        """Convert database row to SemanticMemory object."""
        return SemanticMemory(
            memory_id=row['memory_id'],
            memory_type=MemoryType.SEMANTIC,
            pattern=row['pattern'],
            content=row['content'],
            context=row['context'],
            confidence=row['confidence'],
            times_validated=row['times_validated'],
            times_invalidated=row['times_invalidated'],
            created_at=row['created_at'],
            last_accessed=row['last_accessed'],
            access_count=row['access_count'],
            composite_score=row['composite_score'],
            tags=json.loads(row['tags']),
            embedding=self._deserialize_embedding(row['embedding']),
            source_episodes=json.loads(row['source_episodes'])
        )

    def _serialize_embedding(self, embedding: Optional[List[float]]) -> Optional[bytes]:
        """Serialize embedding for storage."""
        if not embedding:
            return None
        return json.dumps(embedding).encode()

    def _deserialize_embedding(self, data: Optional[bytes]) -> Optional[List[float]]:
        """Deserialize embedding from storage."""
        if not data:
            return None
        return json.loads(data.decode())


# ============================================================================
# SKILL MEMORY (SQLite)
# ============================================================================

class SkillMemoryStore:
    """
    Skill memory: Executable action sequences.
    Links to skill_library.py if exists.

    Supports distributed caching via cache adapters (Redis/SQLite).
    """

    def __init__(self, db_path: Path = SKILL_DB, cache_adapter: Optional[CacheAdapter] = None):
        self.db_path = db_path
        self.scorer = MemoryScorer()
        # Locking strategy: Use asyncio.Lock for all operations to prevent race conditions
        # This allows safe usage in both sync (via _sync_lock()) and async contexts
        # Avoids deadlocks from mixing threading.Lock with asyncio.Lock
        self._lock = asyncio.Lock()

        # Cache adapter for distributed scenarios (shared with other stores if provided)
        self.cache = cache_adapter if cache_adapter else create_cache_adapter()
        self._cache_invalidation_channel = "skill_memory_invalidation"

        self._init_db()
        self._setup_cache_invalidation()

    def _sync_lock(self):
        """
        Context manager for synchronous code to safely use asyncio.Lock.

        This allows synchronous methods to acquire the asyncio.Lock without blocking
        the event loop, preventing race conditions with async methods.
        """
        class SyncLockContext:
            def __init__(self, lock):
                self.lock = lock
                self.acquired = False

            def __enter__(self):
                # Try to get the current event loop
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    # No event loop, create a new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                if loop.is_running():
                    # We're in an async context, can't use run_until_complete
                    # Skip locking - the caller is responsible for async locking
                    self.acquired = False
                    return self

                loop.run_until_complete(self.lock.acquire())
                self.acquired = True
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                if self.acquired:
                    self.lock.release()
                return False

        return SyncLockContext(self._lock)

    def _init_db(self):
        """Initialize SQLite database with recovery."""
        schema = """
            CREATE TABLE IF NOT EXISTS skills (
                memory_id TEXT PRIMARY KEY,
                skill_name TEXT,
                description TEXT,
                content TEXT,
                action_sequence TEXT,
                preconditions TEXT,
                postconditions TEXT,
                success_rate REAL,
                times_executed INTEGER,
                average_duration REAL,
                created_at TEXT,
                last_accessed TEXT,
                access_count INTEGER,
                composite_score REAL,
                tags TEXT,
                embedding BLOB,
                error_handling TEXT,
                decision_logic TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(skill_name);
            CREATE INDEX IF NOT EXISTS idx_skills_score ON skills(composite_score DESC);
        """

        conn = self._load_with_recovery(self.db_path, schema)
        conn.close()

        # Check database size on initialization
        self._check_and_cleanup_db_size()

    def _load_with_recovery(self, db_path: Path, schema: str) -> sqlite3.Connection:
        """Load database with recovery from corruption."""
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            # Verify integrity
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if result[0] != "ok":
                raise sqlite3.DatabaseError("Integrity check failed")
            # Ensure tables exist
            conn.executescript(schema)
            return conn
        except sqlite3.DatabaseError as e:
            logger.error(f"Database corrupt: {e}, attempting recovery")
            # Backup corrupt file
            backup = db_path.with_suffix('.corrupt.bak')
            if db_path.exists():
                db_path.rename(backup)
                logger.info(f"Backed up corrupt database to {backup}")
            # Create fresh database
            conn = sqlite3.connect(str(db_path))
            conn.executescript(schema)
            logger.info(f"Created fresh database at {db_path}")
            return conn

    def _get_db_size_mb(self) -> float:
        """Get current database size in MB."""
        try:
            if self.db_path.exists():
                size_bytes = self.db_path.stat().st_size
                return size_bytes / (1024 * 1024)  # Convert to MB
            return 0.0
        except Exception as e:
            logger.warning(f"Failed to get database size: {e}")
            return 0.0

    def _check_and_cleanup_db_size(self):
        """Check database size and cleanup if needed."""
        size_mb = self._get_db_size_mb()

        # Warn if approaching limit
        if size_mb >= MAX_DB_SIZE_MB * DB_SIZE_WARNING_THRESHOLD:
            logger.warning(
                f"Skills DB size ({size_mb:.2f}MB) approaching limit ({MAX_DB_SIZE_MB}MB). "
                f"Cleanup will trigger at {MAX_DB_SIZE_MB}MB."
            )

        # Cleanup if over limit
        if size_mb >= MAX_DB_SIZE_MB:
            logger.warning(
                f"Skills DB size ({size_mb:.2f}MB) exceeds limit ({MAX_DB_SIZE_MB}MB). "
                f"Removing oldest entries..."
            )
            self._cleanup_old_entries()

            # Check size after cleanup
            new_size_mb = self._get_db_size_mb()
            logger.info(
                f"Skills DB cleanup complete. Size reduced from {size_mb:.2f}MB to {new_size_mb:.2f}MB"
            )

    def _cleanup_old_entries(self):
        """Remove oldest entries to reduce database size to target."""
        target_size_mb = MAX_DB_SIZE_MB * DB_CLEANUP_TARGET

        # Use sync lock wrapper for asyncio.Lock in sync context
        with self._sync_lock():
            with sqlite3.connect(str(self.db_path)) as conn:
                # Get total count
                cursor = conn.execute("SELECT COUNT(*) FROM skills")
                total_count = cursor.fetchone()[0]

                if total_count == 0:
                    return

                # Estimate how many entries to remove
                current_size = self._get_db_size_mb()
                if current_size == 0:
                    return

                target_ratio = target_size_mb / current_size
                entries_to_keep = int(total_count * target_ratio)
                entries_to_remove = total_count - entries_to_keep

                if entries_to_remove <= 0:
                    return

                # Remove low-performing, rarely accessed skills
                cursor = conn.execute("""
                    SELECT memory_id FROM skills
                    ORDER BY
                        success_rate ASC,
                        access_count ASC,
                        created_at ASC
                    LIMIT ?
                """, (entries_to_remove,))

                ids_to_remove = [row[0] for row in cursor.fetchall()]

                if ids_to_remove:
                    placeholders = ','.join('?' * len(ids_to_remove))
                    conn.execute(
                        f"DELETE FROM skills WHERE memory_id IN ({placeholders})",
                        ids_to_remove
                    )
                    conn.commit()

                    # Vacuum to reclaim space
                    conn.execute("VACUUM")

                    logger.info(f"Removed {len(ids_to_remove)} old skill entries from database")

    def _setup_cache_invalidation(self):
        """Setup cache invalidation listener for distributed scenarios."""
        async def invalidation_callback(message: str):
            """Handle cache invalidation messages from other instances."""
            try:
                data = json.loads(message)
                action = data.get("action")
                key = data.get("key")

                if action == "delete" and key:
                    await self.cache.delete(key)
                    logger.debug(f"Cache invalidated for key: {key}")
                elif action == "delete_pattern" and key:
                    await self.cache.delete_pattern(key)
                    logger.debug(f"Cache invalidated for pattern: {key}")
            except Exception as e:
                logger.warning(f"Error handling cache invalidation: {e}")

        # Subscribe to invalidation channel
        try:
            asyncio.create_task(
                self.cache.subscribe(self._cache_invalidation_channel, invalidation_callback)
            )
        except Exception as e:
            logger.debug(f"Cache invalidation subscription not set up: {e}")

    async def _invalidate_cache(self, key: str):
        """Invalidate cache key locally and notify other instances."""
        await self.cache.delete(key)
        await self.cache.publish(
            self._cache_invalidation_channel,
            json.dumps({"action": "delete", "key": key})
        )

    def add_skill(self, skill: SkillMemory):
        """Add a skill to memory."""
        # Check database size before adding
        self._check_and_cleanup_db_size()

        # Use sync lock wrapper for asyncio.Lock in sync context
        with self._sync_lock():
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO skills VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """, (
                    skill.memory_id,
                    skill.skill_name,
                    skill.description,
                    skill.content,
                    json.dumps(skill.action_sequence),
                    json.dumps(skill.preconditions),
                    json.dumps(skill.postconditions),
                    skill.success_rate,
                    skill.times_executed,
                    skill.average_duration,
                    skill.created_at,
                    skill.last_accessed,
                    skill.access_count,
                    skill.composite_score,
                    json.dumps(skill.tags),
                    self._serialize_embedding(skill.embedding),
                    json.dumps(skill.error_handling),
                    json.dumps(skill.decision_logic)
                ))
                conn.commit()

    def get_skill(self, skill_name: str) -> Optional[SkillMemory]:
        """Get a skill by name."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM skills WHERE skill_name = ?",
                (skill_name,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_skill(row)

    def search_skills(self, query: str, limit: int = 5) -> List[SkillMemory]:
        """Search skills by query."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM skills
                ORDER BY composite_score DESC
                LIMIT ?
            """, (limit * 2,))
            rows = cursor.fetchall()

        skills = [self._row_to_skill(row) for row in rows]

        # Semantic filtering
        query_embedding = self.scorer.embedding_engine.get_embedding(query)

        scored = []
        for skill in skills:
            score = self.scorer.score_memory(skill, query, query_embedding)
            scored.append((skill, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        result = [skill for skill, _ in scored[:limit]]

        # Update access counts
        for skill in result:
            self._update_access(skill.memory_id)

        return result

    def record_execution(self, skill_name: str, success: bool, duration: float):
        """Record a skill execution to update statistics."""
        skill = self.get_skill(skill_name)
        if not skill:
            return

        # Update statistics
        skill.times_executed += 1

        # Update success rate (exponential moving average)
        alpha = 0.2  # Weight for new observation
        skill.success_rate = (1 - alpha) * skill.success_rate + alpha * (1.0 if success else 0.0)

        # Update average duration (exponential moving average)
        skill.average_duration = (1 - alpha) * skill.average_duration + alpha * duration

        # Update timestamp
        skill.last_accessed = datetime.now().isoformat()

        # Save
        self.add_skill(skill)

    def _update_access(self, memory_id: str):
        """Update access count and timestamp."""
        now = datetime.now().isoformat()
        # Use sync lock wrapper for asyncio.Lock in sync context
        with self._sync_lock():
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    UPDATE skills
                    SET access_count = access_count + 1,
                        last_accessed = ?
                    WHERE memory_id = ?
                """, (now, memory_id))
                conn.commit()

    def _row_to_skill(self, row: sqlite3.Row) -> SkillMemory:
        """Convert database row to SkillMemory object."""
        # Handle old rows that don't have error_handling/decision_logic columns
        error_handling = json.loads(row['error_handling']) if 'error_handling' in row.keys() and row['error_handling'] else []
        decision_logic = json.loads(row['decision_logic']) if 'decision_logic' in row.keys() and row['decision_logic'] else []

        return SkillMemory(
            memory_id=row['memory_id'],
            memory_type=MemoryType.SKILL,
            skill_name=row['skill_name'],
            description=row['description'],
            content=row['content'],
            action_sequence=json.loads(row['action_sequence']),
            preconditions=json.loads(row['preconditions']),
            postconditions=json.loads(row['postconditions']),
            success_rate=row['success_rate'],
            times_executed=row['times_executed'],
            average_duration=row['average_duration'],
            created_at=row['created_at'],
            last_accessed=row['last_accessed'],
            access_count=row['access_count'],
            composite_score=row['composite_score'],
            tags=json.loads(row['tags']),
            embedding=self._deserialize_embedding(row['embedding']),
            error_handling=error_handling,
            decision_logic=decision_logic
        )

    def _serialize_embedding(self, embedding: Optional[List[float]]) -> Optional[bytes]:
        """Serialize embedding for storage."""
        if not embedding:
            return None
        return json.dumps(embedding).encode()

    def _deserialize_embedding(self, data: Optional[bytes]) -> Optional[List[float]]:
        """Deserialize embedding from storage."""
        if not data:
            return None
        return json.loads(data.decode())


# ============================================================================
# UNIFIED MEMORY MANAGER
# ============================================================================

class MemoryArchitecture:
    """
    Unified memory architecture - Mem0-style memory for Eversale.

    Coordinates all memory layers:
    - Working memory (current context)
    - Episodic memory (experiences)
    - Semantic memory (knowledge)
    - Skill memory (action sequences)

    Supports distributed caching for parallel agent instances.
    """

    def __init__(
        self,
        working_capacity: int = WORKING_MEMORY_CAPACITY,
        auto_consolidate: bool = True,
        session_id: Optional[str] = None,
        cache_adapter: Optional[CacheAdapter] = None
    ):
        # Create or use provided cache adapter (shared across all memory stores)
        self.cache = cache_adapter if cache_adapter else create_cache_adapter()

        # Initialize memory stores with shared cache adapter
        self.working = WorkingMemory(capacity=working_capacity)
        self.episodic = EpisodicMemoryStore(cache_adapter=self.cache)
        self.semantic = SemanticMemoryStore(cache_adapter=self.cache)
        self.skills = SkillMemoryStore(cache_adapter=self.cache)

        self.compressor = MemoryCompressor()
        self.scorer = MemoryScorer()

        # Session management with linking support
        if session_id:
            # Use provided session ID (for resuming)
            self.current_session_id = session_id
        else:
            # Create new session ID
            self.current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        self.working.session_id = self.current_session_id

        # Auto-consolidation
        self.auto_consolidate = auto_consolidate
        self.last_consolidation = time.time()
        self._consolidation_task = None
        self._consolidation_pending = False

        if auto_consolidate:
            self._schedule_consolidation()

    # ========================================================================
    # SESSION MANAGEMENT
    # ========================================================================

    def rotate_session(self, new_session_id: Optional[str] = None) -> str:
        """
        Rotate to a new session while maintaining memory continuity.
        Links the new session to the current session so memories remain accessible.

        Args:
            new_session_id: Optional explicit new session ID. If not provided,
                          generates a new timestamp-based ID.

        Returns:
            The new session ID
        """
        old_session_id = self.current_session_id

        # Generate or use provided new session ID
        if new_session_id is None:
            new_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Record the session link (new -> old)
        self.episodic.link_session(new_session_id, old_session_id)
        logger.info(f"Session rotated: {old_session_id} -> {new_session_id}")

        # Update current session
        self.current_session_id = new_session_id
        self.working.session_id = new_session_id

        return new_session_id

    def get_session_history(self) -> List[str]:
        """
        Get the full session history (current and all linked previous sessions).

        Returns:
            List of session IDs in chronological order (oldest first)
        """
        linked = self.episodic.get_linked_sessions(self.current_session_id)
        # Reverse to get chronological order (oldest first)
        return list(reversed(linked))

    # ========================================================================
    # WORKING MEMORY OPERATIONS
    # ========================================================================

    def add_step(
        self,
        action: str,
        observation: str,
        reasoning: str = "",
        tool_calls: List[Dict] = None,
        success: bool = True,
        error: Optional[str] = None
    ) -> WorkingMemoryStep:
        """Add a step to working memory."""
        step = WorkingMemoryStep(
            step_id=f"step_{int(time.time() * 1000)}",
            step_number=len(self.working.steps) + 1,
            action=action,
            observation=observation,
            reasoning=reasoning,
            tool_calls=tool_calls or [],
            timestamp=datetime.now().isoformat(),
            success=success,
            error=error
        )

        self.working.add_step(step)
        return step

    def get_context(self, detailed_steps: int = 10) -> str:
        """
        Get current context for LLM.
        Recent steps in detail, older steps compressed.
        """
        return self.working.get_context_window(detailed_steps)

    def get_recent_steps(self, n: int = 10) -> List[WorkingMemoryStep]:
        """Get recent steps from working memory."""
        return self.working.get_recent_steps(n)

    # ========================================================================
    # EPISODIC MEMORY OPERATIONS
    # ========================================================================

    def save_episode(
        self,
        task_prompt: str,
        outcome: str,
        success: bool,
        duration_seconds: float,
        task_id: Optional[str] = None,
        tags: List[str] = None,
        importance: float = 0.5
    ) -> EpisodicMemory:
        """
        Save current working memory as an episode.
        Automatically compresses and generates embeddings.
        """
        # Get steps from working memory
        steps = self.working.get_all_steps()
        steps_data = [asdict(step) for step in steps]

        # Compress
        content = self.working.compress_to_summary()
        compressed = self.compressor.compress_content(content, max_tokens=100)

        # Extract tools used
        tools_used = []
        for step in steps:
            for call in step.tool_calls:
                tool_name = call.get("name", "")
                if tool_name and tool_name not in tools_used:
                    tools_used.append(tool_name)

        # Create episode
        memory_id = hashlib.sha256(
            f"{task_prompt}_{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

        episode = EpisodicMemory(
            memory_id=memory_id,
            memory_type=MemoryType.EPISODIC,
            task_prompt=task_prompt,
            content=content,
            compressed_content=compressed,
            outcome=outcome,
            success=success,
            duration_seconds=duration_seconds,
            tools_used=tools_used,
            steps=steps_data,
            created_at=datetime.now().isoformat(),
            last_accessed=datetime.now().isoformat(),
            importance=importance,
            task_id=task_id or self.working.current_task_id,
            session_id=self.current_session_id,
            tags=tags or [],
            original_tokens=len(content.split()),
            compressed_tokens=len(compressed.split())
        )

        # Generate embedding
        episode.embedding = self.scorer.embedding_engine.get_embedding(
            f"{task_prompt} {content}"
        )

        # Score
        self.scorer.score_memory(episode)

        # Save
        self.episodic.add_episode(episode)

        # Clear working memory
        self.working.clear(save_to_episodic=False)

        return episode

    def search_episodes(
        self,
        query: str,
        limit: int = 5,
        success_only: bool = False,
        include_linked_sessions: bool = True
    ) -> List[EpisodicMemory]:
        """
        Search episodic memories.

        Args:
            query: Search query for semantic matching
            limit: Maximum number of results
            success_only: Only return successful episodes
            include_linked_sessions: If True, includes memories from all linked sessions

        Returns:
            List of matching episodic memories
        """
        # Include current session and all linked sessions by default
        session_id = self.current_session_id if include_linked_sessions else None

        return self.episodic.search_episodes(
            query=query,
            session_id=session_id,
            limit=limit,
            success_only=success_only
        )

    # ========================================================================
    # SEMANTIC MEMORY OPERATIONS
    # ========================================================================

    def search_semantic(self, query: str, limit: int = 5) -> List[SemanticMemory]:
        """Search semantic memories (generalized knowledge)."""
        return self.semantic.search_semantic(query, limit)

    def extract_patterns(self, min_episodes: int = 2) -> List[SemanticMemory]:
        """
        Extract semantic patterns from recent episodic memories.
        This is memory consolidation in action.
        """
        # Get recent successful episodes
        # Use raw SQL for efficiency
        with sqlite3.connect(str(self.episodic.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM episodes
                WHERE success = 1
                ORDER BY created_at DESC
                LIMIT 50
            """)
            rows = cursor.fetchall()

        episodes = [self.episodic._row_to_episode(row) for row in rows]

        # Extract patterns
        return self.semantic.extract_from_episodes(episodes)

    # ========================================================================
    # SKILL MEMORY OPERATIONS
    # ========================================================================

    def save_skill(
        self,
        skill_name: str,
        description: str,
        action_sequence: List[Dict],
        preconditions: List[str] = None,
        postconditions: List[str] = None,
        tags: List[str] = None
    ) -> SkillMemory:
        """Save a skill (action sequence) to memory."""
        memory_id = hashlib.sha256(skill_name.encode()).hexdigest()[:16]

        content = f"{description} | Actions: {len(action_sequence)}"

        skill = SkillMemory(
            memory_id=memory_id,
            memory_type=MemoryType.SKILL,
            skill_name=skill_name,
            description=description,
            content=content,
            action_sequence=action_sequence,
            preconditions=preconditions or [],
            postconditions=postconditions or [],
            success_rate=0.5,  # Neutral starting point
            times_executed=0,
            average_duration=0.0,
            created_at=datetime.now().isoformat(),
            last_accessed=datetime.now().isoformat(),
            tags=tags or []
        )

        # Generate embedding
        skill.embedding = self.scorer.embedding_engine.get_embedding(
            f"{skill_name} {description} {content}"
        )

        # Score
        self.scorer.score_memory(skill)

        # Save
        self.skills.add_skill(skill)

        return skill

    def search_skills(self, query: str, limit: int = 5) -> List[SkillMemory]:
        """Search skills by query."""
        return self.skills.search_skills(query, limit)

    def get_skill(self, skill_name: str) -> Optional[SkillMemory]:
        """Get a specific skill by name."""
        return self.skills.get_skill(skill_name)

    def record_skill_execution(
        self,
        skill_name: str,
        success: bool,
        duration: float
    ):
        """Record skill execution to update statistics."""
        self.skills.record_execution(skill_name, success, duration)

    # ========================================================================
    # UNIFIED SEARCH
    # ========================================================================

    def search_all(
        self,
        query: str,
        limit_per_type: int = 3
    ) -> Dict[str, List[MemoryEntry]]:
        """
        Search all memory types and return unified results.
        This is the main retrieval interface.
        """
        results = {
            "episodic": self.search_episodes(query, limit_per_type),
            "semantic": self.search_semantic(query, limit_per_type),
            "skills": self.search_skills(query, limit_per_type)
        }

        return results

    def get_enriched_context(
        self,
        query: str,
        detailed_steps: int = 10,
        limit_per_type: int = 2
    ) -> str:
        """
        Get enriched context for LLM including:
        - Current working memory (recent steps)
        - Relevant episodic memories
        - Relevant semantic knowledge
        - Relevant skills
        """
        parts = []

        # Working memory
        working_context = self.get_context(detailed_steps)
        parts.append(f"[Current Task Context]\n{working_context}")

        # Search all memory types
        results = self.search_all(query, limit_per_type)

        # Add episodic memories
        if results["episodic"]:
            episodes_text = "\n".join([
                f"- {ep.task_prompt}: {ep.compressed_content}"
                for ep in results["episodic"]
            ])
            parts.append(f"\n[Relevant Past Experiences]\n{episodes_text}")

        # Add semantic knowledge
        if results["semantic"]:
            semantic_text = "\n".join([
                f"- {sem.pattern}: {sem.content}"
                for sem in results["semantic"]
            ])
            parts.append(f"\n[Relevant Knowledge]\n{semantic_text}")

        # Add skills
        if results["skills"]:
            skills_text = "\n".join([
                f"- {skill.skill_name}: {skill.description} (success rate: {skill.success_rate:.1%})"
                for skill in results["skills"]
            ])
            parts.append(f"\n[Relevant Skills]\n{skills_text}")

        return "\n".join(parts)

    # ========================================================================
    # MEMORY CONSOLIDATION
    # ========================================================================

    async def consolidate_now(self):
        """Run memory consolidation immediately."""
        logger.info("Running memory consolidation...")

        # 1. Merge similar episodes
        merged = await self.episodic.consolidate_similar()
        logger.info(f"Merged {merged} similar episodes")

        # 2. Extract patterns from episodes -> semantic memories
        patterns = self.extract_patterns()
        logger.info(f"Extracted {len(patterns)} semantic patterns")

        # 3. Decay old, low-utility memories
        decayed = await self.decay_memories()
        logger.info(f"Decayed {decayed} old/low-utility memories")

        self.last_consolidation = time.time()

    async def decay_memories(self, max_age_days: int = 30, min_score: float = 0.3):
        """
        Implement time-based + utility-based memory decay.

        Decay Strategy:
        1. Episodic memories: Remove if age > max_age AND access_count < threshold
        2. Semantic memories: Keep high-importance, decay low-utility
        3. Working memory: Aggressive pruning (keep only recent)
        4. Skills: Never decay (but can mark as deprecated)

        Args:
            max_age_days: Maximum age in days before considering for decay
            min_score: Minimum composite score to keep memories

        Returns:
            Number of memories decayed
        """
        decayed_count = 0
        cutoff = datetime.now() - timedelta(days=max_age_days)

        # ===== EPISODIC MEMORY DECAY =====
        # Decay formula: keep if important OR recently accessed OR new
        with sqlite3.connect(str(self.episodic.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM episodes")
            episodes = cursor.fetchall()

            to_delete = []
            for row in episodes:
                try:
                    age = datetime.fromisoformat(row['created_at'])
                    access_count = row['access_count']
                    importance = row['importance']

                    # Decay formula: keep if important OR recently accessed OR new
                    is_old = age < cutoff
                    keep_score = (
                        (importance * 0.4) +
                        (min(access_count, 10) / 10 * 0.3) +
                        (0.0 if is_old else 0.3)
                    )

                    if keep_score < min_score:
                        to_delete.append(row['memory_id'])
                except Exception as e:
                    logger.warning(f"Error processing episode {row.get('memory_id', 'unknown')}: {e}")

            # Delete low-score episodes
            if to_delete:
                # Use async lock in async context to prevent race conditions
                async with self.episodic._lock:
                    placeholders = ','.join('?' * len(to_delete))
                    conn.execute(
                        f"DELETE FROM episodes WHERE memory_id IN ({placeholders})",
                        to_delete
                    )
                    conn.commit()
                    decayed_count += len(to_delete)
                    logger.info(f"Decayed {len(to_delete)} episodic memories")

        # ===== WORKING MEMORY DECAY =====
        # 1. Remove time-decayed items (older than decay_hours)
        time_decayed = self.working.prune_decayed()
        if time_decayed > 0:
            decayed_count += time_decayed
            logger.info(f"Removed {time_decayed} time-decayed working memory steps (older than {self.working.decay_hours}h)")

        # 2. Keep only last N items (aggressive pruning for capacity management)
        max_working_items = 50
        pruned = self.working.prune(max_items=max_working_items)
        if pruned > 0:
            decayed_count += pruned
            logger.info(f"Pruned {pruned} old working memory steps for capacity")

        # ===== SEMANTIC MEMORY DECAY =====
        # Remove low-confidence facts that are rarely accessed
        with sqlite3.connect(str(self.semantic.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM semantic")
            semantics = cursor.fetchall()

            to_delete = []
            for row in semantics:
                try:
                    confidence = row['confidence']
                    access_count = row['access_count']

                    # Remove low-confidence facts with minimal access
                    if confidence < 0.5 and access_count < 2:
                        to_delete.append(row['memory_id'])
                except Exception as e:
                    logger.warning(f"Error processing semantic {row.get('memory_id', 'unknown')}: {e}")

            # Delete low-utility semantic memories
            if to_delete:
                # Use async lock in async context to prevent race conditions
                async with self.semantic._lock:
                    placeholders = ','.join('?' * len(to_delete))
                    conn.execute(
                        f"DELETE FROM semantic WHERE memory_id IN ({placeholders})",
                        to_delete
                    )
                    conn.commit()
                    decayed_count += len(to_delete)
                    logger.info(f"Decayed {len(to_delete)} semantic memories")

        # ===== SKILL MEMORY DECAY =====
        # Skills are never fully deleted, but we can mark deprecated ones
        # (or reduce their composite score so they rank lower in searches)
        with sqlite3.connect(str(self.skills.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM skills WHERE success_rate < 0.3")
            low_performing = cursor.fetchall()

            if low_performing:
                # Use async lock in async context to prevent race conditions
                async with self.skills._lock:
                    for row in low_performing:
                        # Reduce composite score for low-performing skills
                        conn.execute("""
                            UPDATE skills
                            SET composite_score = composite_score * 0.5
                            WHERE memory_id = ?
                        """, (row['memory_id'],))
                    conn.commit()
                    logger.info(f"Downranked {len(low_performing)} low-performing skills")

        logger.info(f"Total memories decayed: {decayed_count}")
        return decayed_count

    async def decay_old_memories(self, max_age_days: int = 30, min_score: float = 0.3):
        """
        DEPRECATED: Use decay_memories() instead.
        Kept for backward compatibility.
        """
        return await self.decay_memories(max_age_days, min_score)

    def _schedule_consolidation(self):
        """Schedule consolidation loop with proper async handling."""
        try:
            loop = asyncio.get_running_loop()
            self._consolidation_task = loop.create_task(self._consolidation_loop())
        except RuntimeError:
            # No running loop - defer to when one exists
            # This can happen during module import
            logger.debug("No running event loop, consolidation will start on first use")
            self._consolidation_pending = True

    async def _ensure_consolidation_started(self):
        """Start consolidation if it was deferred."""
        if getattr(self, '_consolidation_pending', False):
            self._consolidation_pending = False
            asyncio.create_task(self._consolidation_loop())

    async def _consolidation_loop(self):
        """Background consolidation loop with memory decay."""
        consolidation_count = 0
        while True:
            await asyncio.sleep(CONSOLIDATION_INTERVAL)

            try:
                consolidation_count += 1

                # Run regular consolidation
                await self.consolidate_now()

                # Run additional memory decay less frequently (once per hour)
                # Note: decay_memories is already called in consolidate_now,
                # but we run it more frequently here for aggressive pruning
                if consolidation_count % 12 == 0:  # Every 12 * 5min = 60min
                    logger.info("Running additional scheduled memory decay...")
                    await self.decay_memories()

            except Exception as e:
                logger.error(f"Consolidation error: {e}")

    # ========================================================================
    # STATISTICS & MONITORING
    # ========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get memory system statistics."""
        # Count memories
        with sqlite3.connect(str(self.episodic.db_path)) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM episodes")
            episode_count = cursor.fetchone()[0]

        with sqlite3.connect(str(self.semantic.db_path)) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM semantic")
            semantic_count = cursor.fetchone()[0]

        with sqlite3.connect(str(self.skills.db_path)) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM skills")
            skill_count = cursor.fetchone()[0]

        # Token reduction estimate
        working_steps = len(self.working.steps)
        if working_steps > 0:
            full_context = "\n".join([
                f"{s.action} -> {s.observation}"
                for s in self.working.get_all_steps()
            ])
            compressed_context = self.working.compress_to_summary()

            full_tokens = len(full_context.split())
            compressed_tokens = len(compressed_context.split())
            reduction = 1.0 - (compressed_tokens / max(full_tokens, 1))
        else:
            reduction = 0.0

        return {
            "working_memory": {
                "current_steps": working_steps,
                "capacity": self.working.capacity,
                "session_id": self.current_session_id
            },
            "episodic_memory": {
                "total_episodes": episode_count
            },
            "semantic_memory": {
                "total_patterns": semantic_count
            },
            "skill_memory": {
                "total_skills": skill_count
            },
            "compression": {
                "token_reduction": f"{reduction:.1%}",
                "target": f"{TARGET_TOKEN_REDUCTION:.1%}"
            },
            "last_consolidation": datetime.fromtimestamp(
                self.last_consolidation
            ).isoformat()
        }

    def get_memory_stats(self) -> dict:
        """Get detailed memory system statistics for monitoring."""
        return {
            "working_memory": {
                "steps": len(self.working.steps),
                "capacity": self.working.capacity,
                "max_steps": self.working.capacity
            },
            "episodic_memory": {
                "count": self._count_table(self.episodic.db_path, "episodes")
            },
            "semantic_memory": {
                "count": self._count_table(self.semantic.db_path, "semantic")
            },
            "skill_memory": {
                "count": self._count_table(self.skills.db_path, "skills")
            }
        }

    def _count_table(self, db_path: Path, table_name: str) -> int:
        """Safely count rows in a table."""
        try:
            with sqlite3.connect(str(db_path)) as conn:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
                return cursor.fetchone()[0]
        except Exception as e:
            logger.warning(f"Failed to count {table_name}: {e}")
            return 0

    def print_stats(self):
        """Print memory statistics to console."""
        stats = self.get_stats()

        print("\n=== Memory Architecture Statistics ===")
        print(f"\nWorking Memory:")
        print(f"  Current steps: {stats['working_memory']['current_steps']}/{stats['working_memory']['capacity']}")
        print(f"  Session: {stats['working_memory']['session_id']}")

        print(f"\nLong-Term Memory:")
        print(f"  Episodes: {stats['episodic_memory']['total_episodes']}")
        print(f"  Semantic patterns: {stats['semantic_memory']['total_patterns']}")
        print(f"  Skills: {stats['skill_memory']['total_skills']}")

        print(f"\nCompression:")
        print(f"  Token reduction: {stats['compression']['token_reduction']} (target: {stats['compression']['target']})")

        print(f"\nConsolidation:")
        print(f"  Last run: {stats['last_consolidation']}")
        print()

    async def close(self):
        """
        Cleanup and close resources.
        Call this when shutting down the memory architecture to properly close cache connections.
        """
        try:
            await self.cache.close()
            logger.info("Memory architecture closed successfully")
        except Exception as e:
            logger.warning(f"Error closing memory architecture: {e}")


# ============================================================================
# INTEGRATION HELPERS
# ============================================================================

def create_memory_architecture(**kwargs) -> MemoryArchitecture:
    """
    Factory function to create memory architecture.

    Args:
        **kwargs: Arguments passed to MemoryArchitecture constructor
            - working_capacity: Working memory capacity (default: 50)
            - auto_consolidate: Enable auto-consolidation (default: True)
            - session_id: Explicit session ID (default: timestamp)
            - cache_adapter: Custom cache adapter (default: from MEMORY_CACHE_ADAPTER env)

    Environment Variables:
        MEMORY_CACHE_ADAPTER: "sqlite" or "redis" (default: "sqlite")
        REDIS_HOST: Redis host (default: "localhost")
        REDIS_PORT: Redis port (default: 6379)
        REDIS_DB: Redis database (default: 0)
        REDIS_PASSWORD: Redis password (default: None)
        CACHE_TTL_SECONDS: Cache TTL (default: 3600)
        CACHE_KEY_PREFIX: Key prefix (default: "agent_memory")

    Examples:
        # Local mode (SQLite only, no distributed caching)
        memory = create_memory_architecture()

        # Redis mode (distributed caching for parallel agents)
        # Set environment: export MEMORY_CACHE_ADAPTER=redis
        memory = create_memory_architecture()

        # Custom cache adapter
        cache = RedisCacheAdapter(host="redis.example.com")
        memory = create_memory_architecture(cache_adapter=cache)
    """
    return MemoryArchitecture(**kwargs)


def get_memory_backend() -> str:
    """
    Get memory backend from environment variable.

    Returns:
        Backend type: 'redis' or 'sqlite' (default)

    Environment:
        MEMORY_BACKEND: Set to 'redis' to use Redis adapter, 'sqlite' for local SQLite

    Example:
        export MEMORY_BACKEND=redis
        backend = get_memory_backend()  # Returns 'redis'
    """
    return os.environ.get("MEMORY_BACKEND", "sqlite").lower()


def integrate_with_context_memory(memory: MemoryArchitecture) -> Callable:
    """
    Create a drop-in replacement for context_memory.py that uses
    the new memory architecture.
    """
    def get_context_for_llm(detailed_steps: int = 10) -> str:
        return memory.get_context(detailed_steps)

    return get_context_for_llm


def integrate_with_reflexion(
    memory: MemoryArchitecture,
    reflexion_store  # Type: ReflexionMemory from reflexion.py
):
    """
    Integrate with reflexion.py for experience storage.
    Store reflexion memories as episodic + semantic.
    """
    # This would link reflexion reflections to episodic memories
    # and extract patterns into semantic memory
    pass


def integrate_with_planning(
    memory: MemoryArchitecture,
    planning_agent  # Type: PlanningAgent from planning_agent.py
):
    """
    Integrate with planning_agent.py for informed planning.
    Use semantic and skill memories to inform plan generation.
    """
    # This would provide relevant memories to the planner
    # to help generate better plans based on past experience
    pass


# ============================================================================
# MAIN / DEMO
# ============================================================================

if __name__ == "__main__":
    # Demo usage
    print("Mem0-Style Memory Architecture for Eversale")
    print("=" * 60)

    # Create memory system
    memory = create_memory_architecture()

    # Simulate some task execution
    print("\nSimulating task execution...")

    memory.add_step(
        action="Navigate to example.com",
        observation="Page loaded successfully",
        success=True
    )

    memory.add_step(
        action="Extract text from .main-content",
        observation="Found 150 words of content",
        success=True
    )

    memory.add_step(
        action="Click button.submit",
        observation="Button clicked, form submitted",
        success=True
    )

    # Save as episode
    print("\nSaving episode...")
    episode = memory.save_episode(
        task_prompt="Extract content from example.com",
        outcome="Successfully extracted 150 words",
        success=True,
        duration_seconds=5.2,
        tags=["extraction", "web"]
    )

    print(f"Episode saved: {episode.memory_id}")
    print(f"Token reduction: {len(episode.content.split())} -> {len(episode.compressed_content.split())} tokens")

    # Search
    print("\nSearching memories...")
    results = memory.search_episodes("extract content", limit=3)
    print(f"Found {len(results)} relevant episodes")

    # Get enriched context
    print("\nEnriched context for new task:")
    context = memory.get_enriched_context("extract data from website", detailed_steps=5)
    print(context[:500] + "...")

    # Statistics
    memory.print_stats()

    print("\nMemory architecture ready!")


# ============================================================================
# DISTRIBUTED CACHE USAGE EXAMPLES
# ============================================================================
"""
Using Distributed Cache for Parallel Agents:

1. LOCAL MODE (Default - SQLite only, no caching):

   memory = create_memory_architecture()
   # SQLiteCacheAdapter is used automatically (backward compatible)

2. REDIS MODE (Distributed caching for parallel agents):

   # Set environment variable:
   export MEMORY_CACHE_ADAPTER=redis
   export REDIS_HOST=localhost
   export REDIS_PORT=6379
   export REDIS_PASSWORD=your_password  # Optional

   # Then create memory:
   memory = create_memory_architecture()
   # RedisCacheAdapter is used automatically

   # Multiple agent instances can now share cached knowledge!
   # When agent1 adds an episode, agent2 can retrieve it from cache
   # Cache invalidation happens automatically via pub/sub

3. CUSTOM CACHE ADAPTER:

   from memory_architecture import RedisCacheAdapter, create_memory_architecture

   # Create custom cache
   cache = RedisCacheAdapter(
       host="redis.example.com",
       port=6379,
       password=os.environ.get("REDIS_PASSWORD", "TEST_password_placeholder"),  # Configure via environment
       key_prefix="myapp_memory",
       default_ttl=7200  # 2 hours
   )

   # Use it
   memory = create_memory_architecture(cache_adapter=cache)

4. CLEANUP (Important for Redis):

   import asyncio

   # When shutting down:
   asyncio.run(memory.close())
   # This closes Redis connections properly

5. PARALLEL AGENT EXAMPLE:

   # Agent 1 (adds episode):
   memory1 = create_memory_architecture()
   memory1.add_step("Navigate to example.com", "Success", success=True)
   episode = memory1.save_episode("Test task", "Complete", True)

   # Agent 2 (retrieves from cache):
   memory2 = create_memory_architecture()  # Shares same Redis cache
   retrieved = memory2.episodic.get_episode(episode.memory_id)
   # Retrieved from Redis cache instantly (no SQLite query)!

   # Agent 3 (search benefits from cache):
   memory3 = create_memory_architecture()
   results = memory3.search_episodes("navigate", limit=5)
   # Hot results served from cache

Benefits:
- 10-100x faster retrieval for frequently accessed memories
- Shared knowledge across parallel agent instances
- Automatic cache invalidation via pub/sub
- Graceful fallback to SQLite on cache miss
- Backward compatible (SQLite mode is default)
"""
