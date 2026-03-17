#!/usr/bin/env python3
"""
Redis Memory Adapter for Distributed Agent Memory

Enables distributed memory sharing across multiple agent instances using Redis as a backend.
Falls back to local SQLite if Redis is unavailable.

Features:
- Connection pooling for Redis
- Serialization/deserialization of memory objects
- Key namespacing by agent instance
- TTL support for automatic memory expiration
- Pub/sub for real-time memory sync between agents
- Fallback to local SQLite if Redis unavailable
- Async operations throughout
- Batch operations for efficiency
- Memory compression for large objects

Architecture:
- RedisMemoryAdapter mirrors MemoryArchitecture interface
- Transparent fallback to SQLite stores (EpisodicMemoryStore, etc.)
- Pub/sub notifications for cross-instance synchronization
- LRU-style eviction with configurable TTL
"""

import asyncio
import hashlib
import json
import pickle
import zlib
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set, Callable, Union
from dataclasses import asdict
from collections import defaultdict
from loguru import logger
import sqlite3

# Redis imports (optional)
try:
    import redis.asyncio as redis
    from redis.asyncio import Redis, ConnectionPool
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available - will use SQLite fallback only")

# Import memory architecture components
from memory_architecture import (
    MemoryType, MemoryImportance, MemoryEntry, WorkingMemoryStep,
    EpisodicMemory, SemanticMemory, SkillMemory,
    WorkingMemory, EpisodicMemoryStore, SemanticMemoryStore, SkillMemoryStore,
    MemoryCompressor, MemoryScorer, EmbeddingEngine,
    MEMORY_DIR, WORKING_MEMORY_CAPACITY, EPISODIC_DB, SEMANTIC_DB, SKILL_DB
)


# ============================================================================
# CONFIGURATION
# ============================================================================

# Redis configuration
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_PASSWORD = None
REDIS_MAX_CONNECTIONS = 50
REDIS_SOCKET_TIMEOUT = 5
REDIS_SOCKET_CONNECT_TIMEOUT = 5

# TTL configuration (in seconds)
DEFAULT_TTL = 86400 * 7  # 7 days
WORKING_MEMORY_TTL = 3600  # 1 hour
EPISODIC_MEMORY_TTL = 86400 * 30  # 30 days
SEMANTIC_MEMORY_TTL = 86400 * 90  # 90 days
SKILL_MEMORY_TTL = 86400 * 180  # 180 days

# Compression threshold (bytes)
COMPRESSION_THRESHOLD = 1024  # Compress objects larger than 1KB

# Batch operation settings
BATCH_SIZE = 100
BATCH_TIMEOUT = 0.1  # 100ms

# Pub/sub channels
PUBSUB_CHANNEL_PREFIX = "agent:memory:"


# ============================================================================
# SERIALIZATION / COMPRESSION
# ============================================================================

class MemorySerializer:
    """Handles serialization and compression of memory objects."""

    def __init__(self, compression_threshold: int = COMPRESSION_THRESHOLD):
        self.compression_threshold = compression_threshold

    def serialize(self, obj: Any, compress: bool = True) -> bytes:
        """
        Serialize object to bytes with optional compression.

        Args:
            obj: Object to serialize (MemoryEntry, dict, etc.)
            compress: Whether to compress if size exceeds threshold

        Returns:
            Serialized bytes (optionally compressed)
        """
        # Convert dataclass to dict if needed
        if hasattr(obj, '__dataclass_fields__'):
            data = asdict(obj)
        else:
            data = obj

        # Pickle the data
        pickled = pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)

        # Compress if larger than threshold
        if compress and len(pickled) > self.compression_threshold:
            compressed = zlib.compress(pickled, level=6)
            # Only use compression if it actually saves space
            if len(compressed) < len(pickled):
                # Prefix with marker to indicate compression
                return b'\x01' + compressed

        # No compression (prefix with marker)
        return b'\x00' + pickled

    def deserialize(self, data: bytes) -> Any:
        """
        Deserialize bytes to object with automatic decompression.

        Args:
            data: Serialized bytes

        Returns:
            Deserialized object
        """
        if not data:
            return None

        # Check compression marker
        compressed = data[0] == 1
        payload = data[1:]

        # Decompress if needed
        if compressed:
            payload = zlib.decompress(payload)

        # Unpickle
        return pickle.loads(payload)

    def serialize_json(self, obj: Any) -> str:
        """Serialize to JSON (for simple objects)."""
        if hasattr(obj, '__dataclass_fields__'):
            data = asdict(obj)
        else:
            data = obj
        return json.dumps(data)

    def deserialize_json(self, data: str) -> Any:
        """Deserialize from JSON."""
        return json.loads(data)


# ============================================================================
# REDIS CONNECTION POOL
# ============================================================================

class RedisConnectionManager:
    """Manages Redis connection pool with automatic fallback."""

    def __init__(
        self,
        host: str = REDIS_HOST,
        port: int = REDIS_PORT,
        db: int = REDIS_DB,
        password: Optional[str] = REDIS_PASSWORD,
        max_connections: int = REDIS_MAX_CONNECTIONS
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.max_connections = max_connections

        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[Redis] = None
        self._available = False
        self._lock = asyncio.Lock()

    async def connect(self) -> bool:
        """
        Connect to Redis and create connection pool.

        Returns:
            True if connected successfully, False otherwise
        """
        if not REDIS_AVAILABLE:
            logger.warning("Redis library not available")
            return False

        async with self._lock:
            if self._available:
                return True

            try:
                # Create connection pool
                self._pool = ConnectionPool(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    password=self.password,
                    max_connections=self.max_connections,
                    socket_timeout=REDIS_SOCKET_TIMEOUT,
                    socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
                    decode_responses=False  # We handle binary data
                )

                # Create client
                self._client = Redis(connection_pool=self._pool)

                # Test connection
                await self._client.ping()

                self._available = True
                logger.info(f"Connected to Redis at {self.host}:{self.port}")
                return True

            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
                self._available = False
                return False

    async def disconnect(self):
        """Disconnect from Redis and close pool."""
        async with self._lock:
            if self._client:
                await self._client.close()
                self._client = None

            if self._pool:
                await self._pool.disconnect()
                self._pool = None

            self._available = False
            logger.info("Disconnected from Redis")

    @property
    def available(self) -> bool:
        """Check if Redis is available."""
        return self._available

    @property
    def client(self) -> Optional[Redis]:
        """Get Redis client."""
        return self._client if self._available else None

    async def execute(self, coro):
        """
        Execute Redis command with automatic reconnection.

        Args:
            coro: Coroutine to execute

        Returns:
            Command result or None if failed
        """
        if not self._available:
            return None

        try:
            return await coro
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis command failed: {e}")
            self._available = False
            return None


# ============================================================================
# REDIS MEMORY ADAPTER
# ============================================================================

class RedisMemoryAdapter:
    """
    Redis-backed memory adapter with SQLite fallback.

    Mirrors the MemoryArchitecture interface but uses Redis for distributed
    memory sharing across multiple agent instances.

    Features:
    - Automatic fallback to SQLite if Redis unavailable
    - Pub/sub for real-time memory synchronization
    - Key namespacing by agent instance
    - TTL-based automatic expiration
    - Batch operations for efficiency
    - Compression for large objects
    """

    def __init__(
        self,
        agent_id: str = "default",
        redis_host: str = REDIS_HOST,
        redis_port: int = REDIS_PORT,
        redis_db: int = REDIS_DB,
        redis_password: Optional[str] = REDIS_PASSWORD,
        working_capacity: int = WORKING_MEMORY_CAPACITY,
        auto_consolidate: bool = True,
        session_id: Optional[str] = None,
        enable_pubsub: bool = True
    ):
        """
        Initialize Redis memory adapter.

        Args:
            agent_id: Unique agent instance identifier
            redis_host: Redis server host
            redis_port: Redis server port
            redis_db: Redis database number
            redis_password: Redis password (if required)
            working_capacity: Working memory capacity
            auto_consolidate: Enable automatic consolidation
            session_id: Session ID (generated if not provided)
            enable_pubsub: Enable pub/sub for real-time sync
        """
        self.agent_id = agent_id
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.enable_pubsub = enable_pubsub

        # Redis connection manager
        self.redis_manager = RedisConnectionManager(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password
        )

        # Serializer
        self.serializer = MemorySerializer()

        # SQLite fallback stores
        self.working = WorkingMemory(capacity=working_capacity)
        self.episodic = EpisodicMemoryStore()
        self.semantic = SemanticMemoryStore()
        self.skills = SkillMemoryStore()

        # Compressor and scorer
        self.compressor = MemoryCompressor()
        self.scorer = MemoryScorer()

        # Pub/sub
        self._pubsub = None
        self._pubsub_task = None

        # Batch operations
        self._batch_lock = asyncio.Lock()
        self._batch_queue: List[Tuple[str, Callable]] = []
        self._batch_task = None

        # Auto-consolidation
        self.auto_consolidate = auto_consolidate
        self.last_consolidation = time.time()
        self._consolidation_task = None

        # Initialization flag
        self._initialized = False

    async def initialize(self):
        """Initialize Redis connection and pub/sub."""
        if self._initialized:
            return

        # Try to connect to Redis
        connected = await self.redis_manager.connect()

        if connected and self.enable_pubsub:
            await self._start_pubsub()

        if not connected:
            logger.warning("Redis not available - using SQLite fallback only")

        # Update session ID in working memory
        self.working.session_id = self.session_id

        self._initialized = True
        logger.info(f"RedisMemoryAdapter initialized (agent_id={self.agent_id}, session_id={self.session_id})")

    async def close(self):
        """Close Redis connections and cleanup."""
        # Stop pub/sub
        if self._pubsub_task:
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass

        if self._pubsub:
            await self._pubsub.close()

        # Stop batch processing
        if self._batch_task:
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass

        # Disconnect from Redis
        await self.redis_manager.disconnect()

        logger.info("RedisMemoryAdapter closed")

    # ========================================================================
    # KEY NAMESPACING
    # ========================================================================

    def _make_key(self, memory_type: str, memory_id: str, agent_specific: bool = False) -> str:
        """
        Generate namespaced Redis key.

        Args:
            memory_type: Type of memory (episodic, semantic, skill, working)
            memory_id: Memory ID
            agent_specific: If True, include agent_id in key (for working memory)

        Returns:
            Namespaced key string
        """
        if agent_specific:
            return f"agent:{self.agent_id}:{memory_type}:{memory_id}"
        else:
            return f"memory:{memory_type}:{memory_id}"

    def _make_index_key(self, memory_type: str, index_name: str = "all") -> str:
        """Generate key for memory index (sorted set)."""
        return f"memory:{memory_type}:index:{index_name}"

    def _make_session_key(self, session_id: str) -> str:
        """Generate key for session data."""
        return f"session:{session_id}"

    # ========================================================================
    # PUB/SUB FOR REAL-TIME SYNC
    # ========================================================================

    async def _start_pubsub(self):
        """Start pub/sub listener for memory updates."""
        if not self.redis_manager.available:
            return

        try:
            # Create pub/sub client
            self._pubsub = self.redis_manager.client.pubsub()

            # Subscribe to memory update channels
            channels = [
                f"{PUBSUB_CHANNEL_PREFIX}episodic",
                f"{PUBSUB_CHANNEL_PREFIX}semantic",
                f"{PUBSUB_CHANNEL_PREFIX}skill"
            ]

            await self._pubsub.subscribe(*channels)

            # Start listener task
            self._pubsub_task = asyncio.create_task(self._pubsub_listener())

            logger.info(f"Pub/sub started on channels: {channels}")

        except Exception as e:
            logger.error(f"Failed to start pub/sub: {e}")

    async def _pubsub_listener(self):
        """Listen for pub/sub messages and sync memory."""
        try:
            async for message in self._pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    # Parse message
                    data = json.loads(message["data"])
                    memory_type = data.get("memory_type")
                    memory_id = data.get("memory_id")
                    operation = data.get("operation")  # add, update, delete
                    source_agent = data.get("agent_id")

                    # Ignore messages from this agent
                    if source_agent == self.agent_id:
                        continue

                    logger.debug(f"Received memory update: {operation} {memory_type} {memory_id} from {source_agent}")

                    # Handle different operations
                    if operation == "add" or operation == "update":
                        # Fetch and cache the memory locally
                        await self._sync_memory_from_redis(memory_type, memory_id)
                    elif operation == "delete":
                        # Remove from local cache if exists
                        await self._remove_from_local_cache(memory_type, memory_id)

                except Exception as e:
                    logger.error(f"Error processing pub/sub message: {e}")

        except asyncio.CancelledError:
            logger.info("Pub/sub listener cancelled")
        except Exception as e:
            logger.error(f"Pub/sub listener error: {e}")

    async def _publish_memory_update(self, memory_type: str, memory_id: str, operation: str):
        """Publish memory update notification."""
        if not self.redis_manager.available or not self.enable_pubsub:
            return

        try:
            channel = f"{PUBSUB_CHANNEL_PREFIX}{memory_type}"
            message = json.dumps({
                "memory_type": memory_type,
                "memory_id": memory_id,
                "operation": operation,
                "agent_id": self.agent_id,
                "timestamp": datetime.now().isoformat()
            })

            await self.redis_manager.execute(
                self.redis_manager.client.publish(channel, message)
            )

        except Exception as e:
            logger.error(f"Failed to publish memory update: {e}")

    async def _sync_memory_from_redis(self, memory_type: str, memory_id: str):
        """Sync a specific memory from Redis to local cache."""
        # This is a placeholder - in production, you might want to implement
        # local caching of frequently accessed memories
        pass

    async def _remove_from_local_cache(self, memory_type: str, memory_id: str):
        """Remove memory from local cache."""
        # This is a placeholder for local caching implementation
        pass

    # ========================================================================
    # BATCH OPERATIONS
    # ========================================================================

    async def _add_to_batch(self, key: str, operation: Callable):
        """Add operation to batch queue."""
        async with self._batch_lock:
            self._batch_queue.append((key, operation))

            # Start batch processor if not running
            if not self._batch_task or self._batch_task.done():
                self._batch_task = asyncio.create_task(self._process_batch())

    async def _process_batch(self):
        """Process queued batch operations."""
        await asyncio.sleep(BATCH_TIMEOUT)

        async with self._batch_lock:
            if not self._batch_queue:
                return

            # Process up to BATCH_SIZE operations
            batch = self._batch_queue[:BATCH_SIZE]
            self._batch_queue = self._batch_queue[BATCH_SIZE:]

            # Execute batch using pipeline
            if self.redis_manager.available:
                try:
                    pipeline = self.redis_manager.client.pipeline()

                    for key, operation in batch:
                        operation(pipeline)

                    await pipeline.execute()
                    logger.debug(f"Processed batch of {len(batch)} operations")

                except Exception as e:
                    logger.error(f"Batch processing failed: {e}")

    # ========================================================================
    # WORKING MEMORY OPERATIONS
    # ========================================================================

    async def add_step(
        self,
        action: str,
        observation: str,
        reasoning: str = "",
        tool_calls: List[Dict] = None,
        success: bool = True,
        error: Optional[str] = None
    ) -> WorkingMemoryStep:
        """Add a step to working memory (agent-specific)."""
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

        # Add to local working memory
        self.working.add_step(step)

        # Store in Redis with short TTL (working memory is transient)
        if self.redis_manager.available:
            try:
                key = self._make_key("working", step.step_id, agent_specific=True)
                value = self.serializer.serialize(step)

                await self.redis_manager.execute(
                    self.redis_manager.client.setex(key, WORKING_MEMORY_TTL, value)
                )

            except Exception as e:
                logger.error(f"Failed to store working memory step in Redis: {e}")

        return step

    async def get_context(self, detailed_steps: int = 10) -> str:
        """Get current context for LLM."""
        return self.working.get_context_window(detailed_steps)

    async def get_recent_steps(self, n: int = 10) -> List[WorkingMemoryStep]:
        """Get recent steps from working memory."""
        # Working memory is always local (agent-specific)
        return self.working.get_recent_steps(n)

    # ========================================================================
    # EPISODIC MEMORY OPERATIONS
    # ========================================================================

    async def save_episode(
        self,
        task_prompt: str,
        outcome: str,
        success: bool,
        duration_seconds: float,
        task_id: Optional[str] = None,
        tags: List[str] = None,
        importance: float = 0.5
    ) -> EpisodicMemory:
        """Save current working memory as an episode."""
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
            session_id=self.session_id,
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

        # Save to both Redis and SQLite
        await self._save_episode_dual(episode)

        # Clear working memory
        self.working.clear(save_to_episodic=False)

        return episode

    async def _save_episode_dual(self, episode: EpisodicMemory):
        """Save episode to both Redis and SQLite."""
        # Save to SQLite (fallback)
        self.episodic.add_episode(episode)

        # Save to Redis
        if self.redis_manager.available:
            try:
                # Store episode data
                key = self._make_key("episodic", episode.memory_id)
                value = self.serializer.serialize(episode)

                # Use pipeline for atomic operations
                pipeline = self.redis_manager.client.pipeline()

                # Set episode data with TTL
                pipeline.setex(key, EPISODIC_MEMORY_TTL, value)

                # Add to sorted set index (score by composite_score)
                index_key = self._make_index_key("episodic")
                pipeline.zadd(index_key, {episode.memory_id: episode.composite_score})

                # Add to session index
                session_index = f"session:{self.session_id}:episodes"
                pipeline.sadd(session_index, episode.memory_id)
                pipeline.expire(session_index, EPISODIC_MEMORY_TTL)

                # Execute pipeline
                await pipeline.execute()

                # Publish update notification
                await self._publish_memory_update("episodic", episode.memory_id, "add")

            except Exception as e:
                logger.error(f"Failed to save episode to Redis: {e}")

    async def search_episodes(
        self,
        query: str,
        limit: int = 5,
        success_only: bool = False,
        include_linked_sessions: bool = True
    ) -> List[EpisodicMemory]:
        """Search episodic memories."""
        # Try Redis first
        if self.redis_manager.available:
            try:
                results = await self._search_episodes_redis(query, limit, success_only)
                if results:
                    return results
            except Exception as e:
                logger.error(f"Redis episode search failed: {e}")

        # Fallback to SQLite
        session_id = self.session_id if include_linked_sessions else None
        return self.episodic.search_episodes(
            query=query,
            session_id=session_id,
            limit=limit,
            success_only=success_only
        )

    async def _search_episodes_redis(
        self,
        query: str,
        limit: int,
        success_only: bool
    ) -> List[EpisodicMemory]:
        """Search episodes in Redis using semantic similarity."""
        # Generate query embedding
        query_embedding = self.scorer.embedding_engine.get_embedding(query)

        # Get all episode IDs from index
        index_key = self._make_index_key("episodic")
        episode_ids = await self.redis_manager.execute(
            self.redis_manager.client.zrevrange(index_key, 0, -1)
        )

        if not episode_ids:
            return []

        # Fetch episodes and calculate similarity
        episodes_with_scores = []

        # Use pipeline for batch fetching
        pipeline = self.redis_manager.client.pipeline()
        for episode_id in episode_ids:
            key = self._make_key("episodic", episode_id.decode() if isinstance(episode_id, bytes) else episode_id)
            pipeline.get(key)

        results = await pipeline.execute()

        for episode_id, data in zip(episode_ids, results):
            if not data:
                continue

            episode = self.serializer.deserialize(data)

            # Reconstruct as EpisodicMemory object
            episode_obj = EpisodicMemory(**episode)

            # Filter by success if requested
            if success_only and not episode_obj.success:
                continue

            # Calculate similarity
            if episode_obj.embedding and query_embedding:
                similarity = self.scorer.embedding_engine.cosine_similarity(
                    query_embedding,
                    episode_obj.embedding
                )
                episodes_with_scores.append((episode_obj, similarity))

        # Sort by similarity and return top results
        episodes_with_scores.sort(key=lambda x: x[1], reverse=True)
        return [ep for ep, _ in episodes_with_scores[:limit]]

    # ========================================================================
    # SEMANTIC MEMORY OPERATIONS
    # ========================================================================

    async def search_semantic(self, query: str, limit: int = 5) -> List[SemanticMemory]:
        """Search semantic memories (generalized knowledge)."""
        # Try Redis first
        if self.redis_manager.available:
            try:
                results = await self._search_semantic_redis(query, limit)
                if results:
                    return results
            except Exception as e:
                logger.error(f"Redis semantic search failed: {e}")

        # Fallback to SQLite
        return self.semantic.search_semantic(query, limit)

    async def _search_semantic_redis(self, query: str, limit: int) -> List[SemanticMemory]:
        """Search semantic memories in Redis."""
        # Generate query embedding
        query_embedding = self.scorer.embedding_engine.get_embedding(query)

        # Get all semantic IDs from index
        index_key = self._make_index_key("semantic")
        semantic_ids = await self.redis_manager.execute(
            self.redis_manager.client.zrevrange(index_key, 0, -1)
        )

        if not semantic_ids:
            return []

        # Fetch and score
        memories_with_scores = []

        pipeline = self.redis_manager.client.pipeline()
        for sem_id in semantic_ids:
            key = self._make_key("semantic", sem_id.decode() if isinstance(sem_id, bytes) else sem_id)
            pipeline.get(key)

        results = await pipeline.execute()

        for sem_id, data in zip(semantic_ids, results):
            if not data:
                continue

            semantic = self.serializer.deserialize(data)
            semantic_obj = SemanticMemory(**semantic)

            # Calculate similarity
            if semantic_obj.embedding and query_embedding:
                similarity = self.scorer.embedding_engine.cosine_similarity(
                    query_embedding,
                    semantic_obj.embedding
                )
                memories_with_scores.append((semantic_obj, similarity))

        # Sort and return
        memories_with_scores.sort(key=lambda x: x[1], reverse=True)
        return [sem for sem, _ in memories_with_scores[:limit]]

    async def add_semantic(self, semantic: SemanticMemory):
        """Add semantic memory to both Redis and SQLite."""
        # Save to SQLite
        self.semantic.add_semantic(semantic)

        # Save to Redis
        if self.redis_manager.available:
            try:
                key = self._make_key("semantic", semantic.memory_id)
                value = self.serializer.serialize(semantic)

                pipeline = self.redis_manager.client.pipeline()
                pipeline.setex(key, SEMANTIC_MEMORY_TTL, value)

                # Add to index
                index_key = self._make_index_key("semantic")
                pipeline.zadd(index_key, {semantic.memory_id: semantic.composite_score})

                await pipeline.execute()

                # Publish update
                await self._publish_memory_update("semantic", semantic.memory_id, "add")

            except Exception as e:
                logger.error(f"Failed to save semantic memory to Redis: {e}")

    # ========================================================================
    # SKILL MEMORY OPERATIONS
    # ========================================================================

    async def save_skill(
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
            success_rate=0.5,
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

        # Save to both stores
        await self._save_skill_dual(skill)

        return skill

    async def _save_skill_dual(self, skill: SkillMemory):
        """Save skill to both Redis and SQLite."""
        # Save to SQLite
        self.skills.add_skill(skill)

        # Save to Redis
        if self.redis_manager.available:
            try:
                key = self._make_key("skill", skill.memory_id)
                value = self.serializer.serialize(skill)

                pipeline = self.redis_manager.client.pipeline()
                pipeline.setex(key, SKILL_MEMORY_TTL, value)

                # Add to index
                index_key = self._make_index_key("skill")
                pipeline.zadd(index_key, {skill.memory_id: skill.composite_score})

                # Add to skill name index
                skill_name_key = f"skill:name:{skill.skill_name}"
                pipeline.set(skill_name_key, skill.memory_id)
                pipeline.expire(skill_name_key, SKILL_MEMORY_TTL)

                await pipeline.execute()

                # Publish update
                await self._publish_memory_update("skill", skill.memory_id, "add")

            except Exception as e:
                logger.error(f"Failed to save skill to Redis: {e}")

    async def search_skills(self, query: str, limit: int = 5) -> List[SkillMemory]:
        """Search skills by query."""
        # Try Redis first
        if self.redis_manager.available:
            try:
                results = await self._search_skills_redis(query, limit)
                if results:
                    return results
            except Exception as e:
                logger.error(f"Redis skill search failed: {e}")

        # Fallback to SQLite
        return self.skills.search_skills(query, limit)

    async def _search_skills_redis(self, query: str, limit: int) -> List[SkillMemory]:
        """Search skills in Redis."""
        # Generate query embedding
        query_embedding = self.scorer.embedding_engine.get_embedding(query)

        # Get all skill IDs from index
        index_key = self._make_index_key("skill")
        skill_ids = await self.redis_manager.execute(
            self.redis_manager.client.zrevrange(index_key, 0, -1)
        )

        if not skill_ids:
            return []

        # Fetch and score
        skills_with_scores = []

        pipeline = self.redis_manager.client.pipeline()
        for skill_id in skill_ids:
            key = self._make_key("skill", skill_id.decode() if isinstance(skill_id, bytes) else skill_id)
            pipeline.get(key)

        results = await pipeline.execute()

        for skill_id, data in zip(skill_ids, results):
            if not data:
                continue

            skill = self.serializer.deserialize(data)
            skill_obj = SkillMemory(**skill)

            # Calculate similarity
            if skill_obj.embedding and query_embedding:
                similarity = self.scorer.embedding_engine.cosine_similarity(
                    query_embedding,
                    skill_obj.embedding
                )
                skills_with_scores.append((skill_obj, similarity))

        # Sort and return
        skills_with_scores.sort(key=lambda x: x[1], reverse=True)
        return [skill for skill, _ in skills_with_scores[:limit]]

    async def get_skill(self, skill_name: str) -> Optional[SkillMemory]:
        """Get a specific skill by name."""
        # Try Redis first
        if self.redis_manager.available:
            try:
                # Look up skill ID by name
                skill_name_key = f"skill:name:{skill_name}"
                skill_id = await self.redis_manager.execute(
                    self.redis_manager.client.get(skill_name_key)
                )

                if skill_id:
                    # Fetch skill data
                    key = self._make_key("skill", skill_id.decode() if isinstance(skill_id, bytes) else skill_id)
                    data = await self.redis_manager.execute(
                        self.redis_manager.client.get(key)
                    )

                    if data:
                        skill = self.serializer.deserialize(data)
                        return SkillMemory(**skill)

            except Exception as e:
                logger.error(f"Redis skill lookup failed: {e}")

        # Fallback to SQLite
        return self.skills.get_skill(skill_name)

    async def record_skill_execution(
        self,
        skill_name: str,
        success: bool,
        duration: float
    ):
        """Record skill execution to update statistics."""
        # Update in SQLite
        self.skills.record_execution(skill_name, success, duration)

        # Update in Redis
        if self.redis_manager.available:
            try:
                # Get skill
                skill = await self.get_skill(skill_name)
                if skill:
                    # Update statistics
                    skill.times_executed += 1
                    total_duration = skill.average_duration * (skill.times_executed - 1) + duration
                    skill.average_duration = total_duration / skill.times_executed

                    if success:
                        skill.success_rate = (
                            skill.success_rate * (skill.times_executed - 1) + 1.0
                        ) / skill.times_executed
                    else:
                        skill.success_rate = (
                            skill.success_rate * (skill.times_executed - 1)
                        ) / skill.times_executed

                    # Save updated skill
                    await self._save_skill_dual(skill)

            except Exception as e:
                logger.error(f"Failed to update skill execution in Redis: {e}")

    # ========================================================================
    # UNIFIED SEARCH
    # ========================================================================

    async def search_all(
        self,
        query: str,
        limit_per_type: int = 3
    ) -> Dict[str, List[MemoryEntry]]:
        """Search all memory types and return unified results."""
        # Run searches in parallel
        episodic_task = self.search_episodes(query, limit_per_type)
        semantic_task = self.search_semantic(query, limit_per_type)
        skills_task = self.search_skills(query, limit_per_type)

        episodic, semantic, skills = await asyncio.gather(
            episodic_task,
            semantic_task,
            skills_task
        )

        return {
            "episodic": episodic,
            "semantic": semantic,
            "skills": skills
        }

    async def get_enriched_context(
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
        working_context = await self.get_context(detailed_steps)
        parts.append(f"[Current Task Context]\n{working_context}")

        # Search all memory types
        results = await self.search_all(query, limit_per_type)

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
    # SESSION MANAGEMENT
    # ========================================================================

    async def rotate_session(self, new_session_id: Optional[str] = None) -> str:
        """Rotate to a new session while maintaining memory continuity."""
        old_session_id = self.session_id

        # Generate or use provided new session ID
        if new_session_id is None:
            new_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Record the session link (new -> old)
        self.episodic.link_session(new_session_id, old_session_id)

        # Store link in Redis
        if self.redis_manager.available:
            try:
                session_key = self._make_session_key(new_session_id)
                await self.redis_manager.execute(
                    self.redis_manager.client.setex(
                        session_key,
                        EPISODIC_MEMORY_TTL,
                        json.dumps({"previous_session": old_session_id})
                    )
                )
            except Exception as e:
                logger.error(f"Failed to store session link in Redis: {e}")

        logger.info(f"Session rotated: {old_session_id} -> {new_session_id}")

        # Update current session
        self.session_id = new_session_id
        self.working.session_id = new_session_id

        return new_session_id

    async def get_session_history(self) -> List[str]:
        """Get the full session history (current and all linked previous sessions)."""
        linked = self.episodic.get_linked_sessions(self.session_id)
        return list(reversed(linked))


# ============================================================================
# FACTORY METHOD
# ============================================================================

async def create_memory_adapter(
    backend: Optional[str] = None,
    agent_id: str = "default",
    **kwargs
) -> Union[RedisMemoryAdapter, 'MemoryArchitecture']:
    """
    Factory method to create memory adapter based on configuration.

    Args:
        backend: Memory backend ("redis" or "sqlite"). If None, checks MEMORY_BACKEND env var
        agent_id: Agent instance identifier
        **kwargs: Additional arguments for adapter initialization

    Returns:
        Memory adapter instance (RedisMemoryAdapter or MemoryArchitecture)

    Example:
        # Use Redis backend
        memory = await create_memory_adapter(backend="redis", agent_id="agent1")
        await memory.initialize()

        # Use SQLite backend (default)
        memory = await create_memory_adapter(backend="sqlite")
        await memory.initialize()

        # Use environment variable
        # export MEMORY_BACKEND=redis
        memory = await create_memory_adapter()
        await memory.initialize()
    """
    import os
    from memory_architecture import MemoryArchitecture

    # Determine backend
    if backend is None:
        backend = os.environ.get("MEMORY_BACKEND", "sqlite").lower()

    backend = backend.lower()

    if backend == "redis":
        logger.info(f"Creating Redis memory adapter (agent_id={agent_id})")
        adapter = RedisMemoryAdapter(agent_id=agent_id, **kwargs)
        await adapter.initialize()
        return adapter

    elif backend == "sqlite":
        logger.info("Creating SQLite memory adapter")
        # Return standard MemoryArchitecture with SQLite
        return MemoryArchitecture(**kwargs)

    else:
        raise ValueError(f"Unknown memory backend: {backend}. Use 'redis' or 'sqlite'")


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

async def main():
    """Example usage of RedisMemoryAdapter."""

    # Create adapter (will fallback to SQLite if Redis unavailable)
    memory = await create_memory_adapter(
        backend="redis",
        agent_id="agent_001",
        session_id="demo_session"
    )

    try:
        # Add working memory steps
        await memory.add_step(
            action="search_web",
            observation="Found 10 results",
            reasoning="User requested information",
            success=True
        )

        await memory.add_step(
            action="extract_data",
            observation="Extracted key facts",
            reasoning="Consolidating information",
            success=True
        )

        # Save as episode
        episode = await memory.save_episode(
            task_prompt="Research topic X",
            outcome="Successfully gathered information",
            success=True,
            duration_seconds=5.2,
            tags=["research", "web_search"]
        )

        print(f"Saved episode: {episode.memory_id}")

        # Search memories
        results = await memory.search_episodes("research", limit=5)
        print(f"Found {len(results)} matching episodes")

        # Save a skill
        skill = await memory.save_skill(
            skill_name="web_research",
            description="Search web and extract information",
            action_sequence=[
                {"action": "search_web", "params": {"query": "{{query}}"}},
                {"action": "extract_data", "params": {"format": "structured"}}
            ],
            tags=["research"]
        )

        print(f"Saved skill: {skill.skill_name}")

        # Get enriched context
        context = await memory.get_enriched_context(
            query="how to do research",
            detailed_steps=5,
            limit_per_type=2
        )

        print("\nEnriched context:")
        print(context)

    finally:
        # Cleanup
        await memory.close()


if __name__ == "__main__":
    asyncio.run(main())
