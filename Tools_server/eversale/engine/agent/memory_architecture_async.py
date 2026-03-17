#!/usr/bin/env python3
"""
Async I/O Extensions for Memory Architecture

Provides comprehensive async support for parallel agent access to memory stores.
This module extends memory_architecture.py with:
- Async database operations using aiosqlite
- Read/Write locks for safe concurrent access
- Async context managers for batch operations
- Async generators for streaming large result sets
- Backward compatibility with sync callers

Usage:
    # For async code
    from memory_architecture_async import AsyncEpisodicMemoryStore
    store = AsyncEpisodicMemoryStore()
    episodes = await store.search_episodes_async(query="test")

    # For sync code (backward compatible)
    episodes = store.search_episodes(query="test")  # Uses sync wrapper
"""

import asyncio
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, AsyncIterator
from loguru import logger

# Import from main module
try:
    from memory_architecture import (
        EPISODIC_DB, SEMANTIC_DB, SKILL_DB,
        EpisodicMemory, SemanticMemory, SkillMemory,
        MemoryScorer, MemoryType,
        MAX_DB_SIZE_MB, DB_SIZE_WARNING_THRESHOLD, DB_CLEANUP_TARGET
    )
except ImportError:
    logger.error("Failed to import from memory_architecture. Ensure the module is in the Python path.")
    raise

# Async SQLite support
try:
    import aiosqlite
    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False
    logger.warning("aiosqlite not available - install with: pip install aiosqlite")


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


class AsyncBatchContext:
    """
    Async context manager for batch database operations.
    Acquires write lock once for multiple operations, improving performance.
    """

    def __init__(self, store, db_path: Path):
        self.store = store
        self.db_path = db_path
        self.conn = None
        self._operations = []

    async def __aenter__(self):
        # Acquire write lock for exclusive access
        await self.store._rw_lock.acquire_write()
        if AIOSQLITE_AVAILABLE:
            self.conn = await aiosqlite.connect(str(self.db_path))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.conn:
                if exc_type is None:
                    # Commit if no exception
                    await self.conn.commit()
                await self.conn.close()
        finally:
            await self.store._rw_lock.release_write()
        return False

    async def execute(self, sql: str, params: tuple = ()):
        """Execute a SQL statement in the batch."""
        if self.conn:
            await self.conn.execute(sql, params)
        else:
            # Fallback to sync
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(sql, params)


# ============================================================================
# ASYNC EPISODIC MEMORY STORE
# ============================================================================

class AsyncEpisodicMemoryStore:
    """
    Async-enabled Episodic Memory Store.
    Supports safe concurrent access from parallel agents.
    """

    def __init__(self, db_path: Path = EPISODIC_DB):
        self.db_path = db_path
        self.scorer = MemoryScorer()
        self._rw_lock = AsyncReadWriteLock()
        self._consolidation_lock = asyncio.Lock()
        self._init_db_sync()  # Use sync init for now

    def _init_db_sync(self):
        """Initialize database synchronously (called from __init__)."""
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

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.executescript(schema)
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")

    # ========================================================================
    # ASYNC DATABASE OPERATIONS
    # ========================================================================

    async def add_episode_async(self, episode: EpisodicMemory):
        """Add an episode to memory (async version)."""
        async with self._rw_lock.writer():
            if not AIOSQLITE_AVAILABLE:
                # Fallback to sync
                return self._add_episode_sync(episode)

            async with aiosqlite.connect(str(self.db_path)) as conn:
                await conn.execute("""
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
                await conn.commit()

    def _add_episode_sync(self, episode: EpisodicMemory):
        """Sync fallback for add_episode."""
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

    async def get_episode_async(self, memory_id: str) -> Optional[EpisodicMemory]:
        """Retrieve an episode by ID (async version)."""
        async with self._rw_lock.reader():
            if not AIOSQLITE_AVAILABLE:
                return self._get_episode_sync(memory_id)

            async with aiosqlite.connect(str(self.db_path)) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT * FROM episodes WHERE memory_id = ?",
                    (memory_id,)
                ) as cursor:
                    row = await cursor.fetchone()

                    if not row:
                        return None

                    return self._row_to_episode(row)

    def _get_episode_sync(self, memory_id: str) -> Optional[EpisodicMemory]:
        """Sync fallback for get_episode."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM episodes WHERE memory_id = ?",
                (memory_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_episode(row)

    async def search_episodes_async(
        self,
        query: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        success_only: bool = False,
        limit: int = 10,
        min_score: float = 0.0
    ) -> List[EpisodicMemory]:
        """Search episodes with multiple filters (async version)."""
        async with self._rw_lock.reader():
            if not AIOSQLITE_AVAILABLE:
                return self._search_episodes_sync(
                    query, task_id, session_id, tags, success_only, limit, min_score
                )

            # Build SQL query
            conditions = []
            params = []

            if task_id:
                conditions.append("task_id = ?")
                params.append(task_id)

            if session_id:
                conditions.append("session_id = ?")
                params.append(session_id)

            if success_only:
                conditions.append("success = 1")

            if min_score > 0:
                conditions.append("composite_score >= ?")
                params.append(min_score)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            async with aiosqlite.connect(str(self.db_path)) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    f"SELECT * FROM episodes WHERE {where_clause} ORDER BY composite_score DESC LIMIT ?",
                    params + [limit * 2]
                ) as cursor:
                    rows = await cursor.fetchall()

            episodes = [self._row_to_episode(row) for row in rows]

            # Semantic filtering if query provided
            if query:
                episodes = self._semantic_filter(episodes, query, limit)
            else:
                episodes = episodes[:limit]

            # Update access counts asynchronously
            for episode in episodes:
                asyncio.create_task(self._update_access_async(episode.memory_id))

            return episodes

    def _search_episodes_sync(
        self,
        query: Optional[str],
        task_id: Optional[str],
        session_id: Optional[str],
        tags: Optional[List[str]],
        success_only: bool,
        limit: int,
        min_score: float
    ) -> List[EpisodicMemory]:
        """Sync fallback for search_episodes."""
        conditions = []
        params = []

        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

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
                params + [limit * 2]
            )
            rows = cursor.fetchall()

        episodes = [self._row_to_episode(row) for row in rows]

        if query:
            episodes = self._semantic_filter(episodes, query, limit)
        else:
            episodes = episodes[:limit]

        return episodes

    async def _update_access_async(self, memory_id: str):
        """Update access count and timestamp (async version)."""
        now = datetime.now().isoformat()
        async with self._rw_lock.writer():
            if not AIOSQLITE_AVAILABLE:
                return self._update_access_sync(memory_id)

            async with aiosqlite.connect(str(self.db_path)) as conn:
                await conn.execute("""
                    UPDATE episodes
                    SET access_count = access_count + 1,
                        last_accessed = ?
                    WHERE memory_id = ?
                """, (now, memory_id))
                await conn.commit()

    def _update_access_sync(self, memory_id: str):
        """Sync fallback for update_access."""
        now = datetime.now().isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                UPDATE episodes
                SET access_count = access_count + 1,
                    last_accessed = ?
                WHERE memory_id = ?
            """, (now, memory_id))
            conn.commit()

    # ========================================================================
    # ASYNC GENERATORS FOR STREAMING
    # ========================================================================

    async def stream_episodes_async(
        self,
        batch_size: int = 100,
        min_score: float = 0.0
    ) -> AsyncIterator[List[EpisodicMemory]]:
        """
        Stream episodes in batches (async generator).
        Useful for processing large result sets without loading everything into memory.
        """
        async with self._rw_lock.reader():
            if not AIOSQLITE_AVAILABLE:
                # Fallback to sync streaming
                async for batch in self._stream_episodes_sync_fallback(batch_size, min_score):
                    yield batch
                return

            async with aiosqlite.connect(str(self.db_path)) as conn:
                conn.row_factory = aiosqlite.Row
                offset = 0

                while True:
                    async with conn.execute(
                        """
                        SELECT * FROM episodes
                        WHERE composite_score >= ?
                        ORDER BY composite_score DESC
                        LIMIT ? OFFSET ?
                        """,
                        (min_score, batch_size, offset)
                    ) as cursor:
                        rows = await cursor.fetchall()

                    if not rows:
                        break

                    episodes = [self._row_to_episode(row) for row in rows]
                    yield episodes

                    offset += batch_size

                    if len(rows) < batch_size:
                        break

    async def _stream_episodes_sync_fallback(
        self, batch_size: int, min_score: float
    ) -> AsyncIterator[List[EpisodicMemory]]:
        """Sync fallback for streaming (wrapped as async generator)."""
        offset = 0

        while True:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT * FROM episodes
                    WHERE composite_score >= ?
                    ORDER BY composite_score DESC
                    LIMIT ? OFFSET ?
                    """,
                    (min_score, batch_size, offset)
                )
                rows = cursor.fetchall()

            if not rows:
                break

            episodes = [self._row_to_episode(row) for row in rows]
            yield episodes

            offset += batch_size

            if len(rows) < batch_size:
                break

            # Yield control to event loop
            await asyncio.sleep(0)

    # ========================================================================
    # BATCH OPERATIONS
    # ========================================================================

    def batch_operations(self) -> AsyncBatchContext:
        """
        Create a batch context for multiple operations.

        Usage:
            async with store.batch_operations() as batch:
                await batch.execute("INSERT INTO ...", (...))
                await batch.execute("UPDATE ...", (...))
        """
        return AsyncBatchContext(self, self.db_path)

    # ========================================================================
    # BACKWARD COMPATIBLE SYNC WRAPPERS
    # ========================================================================

    def add_episode(self, episode: EpisodicMemory):
        """Sync wrapper for add_episode_async."""
        return run_async(self.add_episode_async(episode))

    def get_episode(self, memory_id: str) -> Optional[EpisodicMemory]:
        """Sync wrapper for get_episode_async."""
        return run_async(self.get_episode_async(memory_id))

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
        """Sync wrapper for search_episodes_async."""
        return run_async(self.search_episodes_async(
            query, task_id, session_id, tags, success_only, limit, min_score
        ))

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _row_to_episode(self, row) -> EpisodicMemory:
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

    def _semantic_filter(
        self,
        episodes: List[EpisodicMemory],
        query: str,
        limit: int
    ) -> List[EpisodicMemory]:
        """Filter episodes by semantic relevance."""
        query_embedding = self.scorer.embedding_engine.get_embedding(query)

        scored = []
        for episode in episodes:
            score = self.scorer.score_memory(episode, query, query_embedding)
            scored.append((episode, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        for episode, score in scored:
            episode.composite_score = score

        return [ep for ep, _ in scored[:limit]]


# ============================================================================
# ASYNC SEMANTIC MEMORY STORE
# ============================================================================

class AsyncSemanticMemoryStore:
    """
    Async-enabled Semantic Memory Store.
    Supports safe concurrent access from parallel agents.
    """

    def __init__(self, db_path: Path = SEMANTIC_DB):
        self.db_path = db_path
        self.scorer = MemoryScorer()
        self._rw_lock = AsyncReadWriteLock()
        self._init_db_sync()

    def _init_db_sync(self):
        """Initialize database synchronously."""
        schema = """
            CREATE TABLE IF NOT EXISTS semantic (
                memory_id TEXT PRIMARY KEY,
                pattern TEXT,
                context TEXT,
                content TEXT,
                confidence REAL,
                times_validated INTEGER,
                times_invalidated INTEGER,
                created_at TEXT,
                last_accessed TEXT,
                access_count INTEGER,
                importance REAL,
                composite_score REAL,
                tags TEXT,
                embedding BLOB,
                source_episodes TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_semantic_score ON semantic(composite_score DESC);
            CREATE INDEX IF NOT EXISTS idx_semantic_pattern ON semantic(pattern);
        """

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.executescript(schema)
        except Exception as e:
            logger.error(f"Failed to initialize semantic database: {e}")

    async def add_semantic_async(self, semantic: SemanticMemory):
        """Add semantic memory (async version)."""
        async with self._rw_lock.writer():
            if not AIOSQLITE_AVAILABLE:
                return self._add_semantic_sync(semantic)

            async with aiosqlite.connect(str(self.db_path)) as conn:
                await conn.execute("""
                    INSERT OR REPLACE INTO semantic VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """, (
                    semantic.memory_id,
                    semantic.pattern,
                    semantic.context,
                    semantic.content,
                    semantic.confidence,
                    semantic.times_validated,
                    semantic.times_invalidated,
                    semantic.created_at,
                    semantic.last_accessed,
                    semantic.access_count,
                    semantic.importance,
                    semantic.composite_score,
                    json.dumps(semantic.tags),
                    self._serialize_embedding(semantic.embedding),
                    json.dumps(semantic.source_episodes)
                ))
                await conn.commit()

    def _add_semantic_sync(self, semantic: SemanticMemory):
        """Sync fallback for add_semantic."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO semantic VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                semantic.memory_id,
                semantic.pattern,
                semantic.context,
                semantic.content,
                semantic.confidence,
                semantic.times_validated,
                semantic.times_invalidated,
                semantic.created_at,
                semantic.last_accessed,
                semantic.access_count,
                semantic.importance,
                semantic.composite_score,
                json.dumps(semantic.tags),
                self._serialize_embedding(semantic.embedding),
                json.dumps(semantic.source_episodes)
            ))
            conn.commit()

    async def search_semantic_async(
        self,
        query: str,
        limit: int = 5
    ) -> List[SemanticMemory]:
        """Search semantic memories (async version)."""
        async with self._rw_lock.reader():
            if not AIOSQLITE_AVAILABLE:
                return self._search_semantic_sync(query, limit)

            async with aiosqlite.connect(str(self.db_path)) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT * FROM semantic ORDER BY composite_score DESC LIMIT ?",
                    (limit * 2,)
                ) as cursor:
                    rows = await cursor.fetchall()

            memories = [self._row_to_semantic(row) for row in rows]

            # Semantic filtering
            query_embedding = self.scorer.embedding_engine.get_embedding(query)
            scored = []
            for mem in memories:
                score = self.scorer.score_memory(mem, query, query_embedding)
                scored.append((mem, score))

            scored.sort(key=lambda x: x[1], reverse=True)
            return [mem for mem, _ in scored[:limit]]

    def _search_semantic_sync(self, query: str, limit: int) -> List[SemanticMemory]:
        """Sync fallback for search_semantic."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM semantic ORDER BY composite_score DESC LIMIT ?",
                (limit * 2,)
            )
            rows = cursor.fetchall()

        memories = [self._row_to_semantic(row) for row in rows]

        query_embedding = self.scorer.embedding_engine.get_embedding(query)
        scored = []
        for mem in memories:
            score = self.scorer.score_memory(mem, query, query_embedding)
            scored.append((mem, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [mem for mem, _ in scored[:limit]]

    # Sync wrappers
    def add_semantic(self, semantic: SemanticMemory):
        """Sync wrapper for add_semantic_async."""
        return run_async(self.add_semantic_async(semantic))

    def search_semantic(self, query: str, limit: int = 5) -> List[SemanticMemory]:
        """Sync wrapper for search_semantic_async."""
        return run_async(self.search_semantic_async(query, limit))

    def _row_to_semantic(self, row) -> SemanticMemory:
        """Convert database row to SemanticMemory object."""
        return SemanticMemory(
            memory_id=row['memory_id'],
            memory_type=MemoryType.SEMANTIC,
            pattern=row['pattern'],
            context=row['context'],
            content=row['content'],
            confidence=row['confidence'],
            times_validated=row['times_validated'],
            times_invalidated=row['times_invalidated'],
            created_at=row['created_at'],
            last_accessed=row['last_accessed'],
            access_count=row['access_count'],
            importance=row['importance'],
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
# ASYNC SKILL MEMORY STORE
# ============================================================================

class AsyncSkillMemoryStore:
    """
    Async-enabled Skill Memory Store.
    Supports safe concurrent access from parallel agents.
    """

    def __init__(self, db_path: Path = SKILL_DB):
        self.db_path = db_path
        self.scorer = MemoryScorer()
        self._rw_lock = AsyncReadWriteLock()
        self._init_db_sync()

    def _init_db_sync(self):
        """Initialize database synchronously."""
        schema = """
            CREATE TABLE IF NOT EXISTS skills (
                memory_id TEXT PRIMARY KEY,
                skill_name TEXT UNIQUE,
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
                importance REAL,
                composite_score REAL,
                tags TEXT,
                embedding BLOB,
                error_handling TEXT,
                decision_logic TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(skill_name);
            CREATE INDEX IF NOT EXISTS idx_skills_score ON skills(composite_score DESC);
        """

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.executescript(schema)
        except Exception as e:
            logger.error(f"Failed to initialize skills database: {e}")

    async def add_skill_async(self, skill: SkillMemory):
        """Add skill memory (async version)."""
        async with self._rw_lock.writer():
            if not AIOSQLITE_AVAILABLE:
                return self._add_skill_sync(skill)

            async with aiosqlite.connect(str(self.db_path)) as conn:
                await conn.execute("""
                    INSERT OR REPLACE INTO skills VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                    skill.importance,
                    skill.composite_score,
                    json.dumps(skill.tags),
                    self._serialize_embedding(skill.embedding),
                    json.dumps(skill.error_handling),
                    json.dumps(skill.decision_logic)
                ))
                await conn.commit()

    def _add_skill_sync(self, skill: SkillMemory):
        """Sync fallback for add_skill."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO skills VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                skill.importance,
                skill.composite_score,
                json.dumps(skill.tags),
                self._serialize_embedding(skill.embedding),
                json.dumps(skill.error_handling),
                json.dumps(skill.decision_logic)
            ))
            conn.commit()

    async def get_skill_async(self, skill_name: str) -> Optional[SkillMemory]:
        """Get skill by name (async version)."""
        async with self._rw_lock.reader():
            if not AIOSQLITE_AVAILABLE:
                return self._get_skill_sync(skill_name)

            async with aiosqlite.connect(str(self.db_path)) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT * FROM skills WHERE skill_name = ?",
                    (skill_name,)
                ) as cursor:
                    row = await cursor.fetchone()

                    if not row:
                        return None

                    return self._row_to_skill(row)

    def _get_skill_sync(self, skill_name: str) -> Optional[SkillMemory]:
        """Sync fallback for get_skill."""
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

    async def search_skills_async(self, query: str, limit: int = 5) -> List[SkillMemory]:
        """Search skills (async version)."""
        async with self._rw_lock.reader():
            if not AIOSQLITE_AVAILABLE:
                return self._search_skills_sync(query, limit)

            async with aiosqlite.connect(str(self.db_path)) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT * FROM skills ORDER BY composite_score DESC LIMIT ?",
                    (limit * 2,)
                ) as cursor:
                    rows = await cursor.fetchall()

            skills = [self._row_to_skill(row) for row in rows]

            # Semantic filtering
            query_embedding = self.scorer.embedding_engine.get_embedding(query)
            scored = []
            for skill in skills:
                score = self.scorer.score_memory(skill, query, query_embedding)
                scored.append((skill, score))

            scored.sort(key=lambda x: x[1], reverse=True)
            return [skill for skill, _ in scored[:limit]]

    def _search_skills_sync(self, query: str, limit: int) -> List[SkillMemory]:
        """Sync fallback for search_skills."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM skills ORDER BY composite_score DESC LIMIT ?",
                (limit * 2,)
            )
            rows = cursor.fetchall()

        skills = [self._row_to_skill(row) for row in rows]

        query_embedding = self.scorer.embedding_engine.get_embedding(query)
        scored = []
        for skill in skills:
            score = self.scorer.score_memory(skill, query, query_embedding)
            scored.append((skill, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [skill for skill, _ in scored[:limit]]

    # Sync wrappers
    def add_skill(self, skill: SkillMemory):
        """Sync wrapper for add_skill_async."""
        return run_async(self.add_skill_async(skill))

    def get_skill(self, skill_name: str) -> Optional[SkillMemory]:
        """Sync wrapper for get_skill_async."""
        return run_async(self.get_skill_async(skill_name))

    def search_skills(self, query: str, limit: int = 5) -> List[SkillMemory]:
        """Sync wrapper for search_skills_async."""
        return run_async(self.search_skills_async(query, limit))

    def _row_to_skill(self, row) -> SkillMemory:
        """Convert database row to SkillMemory object."""
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
            importance=row['importance'],
            composite_score=row['composite_score'],
            tags=json.loads(row['tags']),
            embedding=self._deserialize_embedding(row['embedding']),
            error_handling=json.loads(row['error_handling']),
            decision_logic=json.loads(row['decision_logic'])
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
# USAGE EXAMPLES
# ============================================================================

async def example_async_usage():
    """Example of async usage with parallel agents."""
    # Create async stores
    episodic = AsyncEpisodicMemoryStore()
    semantic = AsyncSemanticMemoryStore()
    skills = AsyncSkillMemoryStore()

    # Parallel reads (multiple agents can read simultaneously)
    results = await asyncio.gather(
        episodic.search_episodes_async(query="test task"),
        semantic.search_semantic_async(query="test pattern"),
        skills.search_skills_async(query="test skill")
    )
    episodes, semantics, skill_list = results

    # Streaming large result sets
    async for batch in episodic.stream_episodes_async(batch_size=100):
        print(f"Processing batch of {len(batch)} episodes")
        # Process batch...

    # Batch operations (single write lock for multiple ops)
    async with episodic.batch_operations() as batch:
        await batch.execute("UPDATE episodes SET importance = ? WHERE memory_id = ?", (0.9, "id1"))
        await batch.execute("UPDATE episodes SET importance = ? WHERE memory_id = ?", (0.8, "id2"))

    print("Async operations completed!")


def example_sync_usage():
    """Example of backward-compatible sync usage."""
    # Create async stores but use sync methods
    episodic = AsyncEpisodicMemoryStore()

    # Sync methods work transparently
    episodes = episodic.search_episodes(query="test task")
    print(f"Found {len(episodes)} episodes")


if __name__ == "__main__":
    print("Async Memory Architecture Module")
    print("=" * 50)
    print()
    print("Features:")
    print("- Async database operations with aiosqlite")
    print("- Read/Write locks for safe concurrent access")
    print("- Async context managers for batch operations")
    print("- Async generators for streaming large result sets")
    print("- Backward compatible sync wrappers")
    print()
    print("Install dependencies:")
    print("  pip install aiosqlite")
    print()
    print("Usage:")
    print("  # Async usage")
    print("  store = AsyncEpisodicMemoryStore()")
    print("  episodes = await store.search_episodes_async(query='test')")
    print()
    print("  # Sync usage (backward compatible)")
    print("  episodes = store.search_episodes(query='test')")
