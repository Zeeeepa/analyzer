#!/usr/bin/env python3
"""
Episode Compressor - Convert Raw Experience to Compressed Wisdom

This is the system that transforms raw episodic traces (task steps, outcomes)
into distilled, reusable wisdom stored in semantic memory. It prevents log bloat
while allowing knowledge to compound over time.

Core Philosophy:
- Raw logs grow forever → Wisdom compounds
- Forgetting is strategic → Compress before forgetting
- Patterns emerge from repetition → Group similar episodes
- Confidence increases with validation → Track usefulness over time

Architecture:
1. Episode Intake: Receive raw task execution traces from EventBus
2. Significance Filter: Decide what's worth compressing (skip trivial)
3. Pattern Extraction: Group similar episodes, find common threads
4. Wisdom Generation: Use LLM to distill insights from grouped experiences
5. Validation Tracking: Monitor how often wisdom proves true
6. Storage & Retrieval: Persist to semantic memory, retrieve when relevant

Integration with Organism:
- Subscribes to: ACTION_COMPLETE, LESSON_LEARNED events
- Publishes: STRATEGY_UPDATED when new wisdom created
- Triggered by: Heartbeat sleep cycles (periodic compression)
- Feeds: SemanticMemoryStore with compressed wisdom

Performance Targets:
- 10:1 compression ratio (10 episodes → 1 wisdom)
- <200ms compression time per episode
- 85%+ pattern recognition accuracy
- 90%+ validation rate on reused wisdom

References:
- Mem0 compression architecture
- Cognitive science on memory consolidation
- Active Inference on belief updating
"""

import asyncio
import hashlib
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict, deque
from loguru import logger

# Import existing components
try:
    from .memory_architecture import (
        SemanticMemoryStore,
        EpisodicMemoryStore,
        SemanticMemory,
        EpisodicMemory,
        MemoryType,
        EmbeddingEngine
    )
    from .organism_core import EventBus, EventType, OrganismEvent
    INTEGRATION_AVAILABLE = True
except ImportError:
    INTEGRATION_AVAILABLE = False
    logger.warning("Integration modules not available - running in standalone mode")


# ============================================================================
# DATA STRUCTURES
# ============================================================================

class WisdomType(Enum):
    """Types of wisdom extracted from experiences."""
    STRATEGY = "strategy"           # How to accomplish goals
    PATTERN = "pattern"            # Recurring patterns observed
    PITFALL = "pitfall"            # Things to avoid
    INSIGHT = "insight"            # General understanding
    HEURISTIC = "heuristic"        # Rule of thumb


@dataclass
class Wisdom:
    """Compressed wisdom from multiple episodes."""
    wisdom_id: str
    pattern: str                    # "billing confusion", "login failures"
    insight: str                    # "always check subscription tier first"
    wisdom_type: WisdomType

    # Validation tracking
    confidence: float               # 0-1, increases with validation
    times_validated: int            # How many times this proved true
    times_invalidated: int          # How many times this was wrong
    validation_rate: float          # validated / (validated + invalidated)

    # Source tracking
    source_episodes: List[str] = field(default_factory=list)  # Episode IDs
    source_count: int = 0           # Number of episodes that created this

    # Context
    context: str = ""               # When/where this applies
    examples: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    # Metadata
    created_at: float = field(default_factory=time.time)
    last_validated: float = field(default_factory=time.time)
    last_used: float = 0.0
    access_count: int = 0

    # Embedding for retrieval
    embedding: Optional[List[float]] = None


@dataclass
class EpisodePattern:
    """A pattern identified across multiple episodes."""
    pattern_id: str
    common_tools: List[str]         # Tools frequently used together
    common_context: str             # Common task context
    success_rate: float             # How often this pattern succeeds
    avg_duration: float             # Average time to complete
    episodes: List[str]             # Episode IDs in this pattern
    insights: List[str]             # Insights extracted


@dataclass
class CompressionMetrics:
    """Metrics for monitoring compression performance."""
    total_episodes_processed: int = 0
    total_wisdom_created: int = 0
    total_patterns_found: int = 0

    compression_ratio: float = 0.0  # episodes / wisdom
    avg_compression_time_ms: float = 0.0

    wisdom_validation_rate: float = 0.0
    pattern_accuracy: float = 0.0

    last_compression_time: float = 0.0
    compression_cycles: int = 0


# ============================================================================
# EPISODE COMPRESSOR
# ============================================================================

class EpisodeCompressor:
    """
    Convert raw episodic experiences into compressed wisdom.

    This is the memory consolidation system - like sleep for the agent's brain.
    """

    # Configuration
    MIN_EPISODES_FOR_PATTERN = 2    # Need at least 2 similar episodes
    COMPRESSION_BATCH_SIZE = 20     # Process N episodes per cycle
    SIMILARITY_THRESHOLD = 0.75     # Cosine similarity for grouping
    MIN_CONFIDENCE = 0.6            # Minimum confidence to create wisdom

    def __init__(
        self,
        episodic_store: 'EpisodicMemoryStore' = None,
        semantic_store: 'SemanticMemoryStore' = None,
        event_bus: 'EventBus' = None,
        llm_client = None,
        fast_model: str = "llama3.2:3b-instruct-q4_0"
    ):
        """
        Initialize the episode compressor.

        Args:
            episodic_store: Where to read raw episodes from
            semantic_store: Where to write compressed wisdom to
            event_bus: For subscribing to events and publishing updates
            llm_client: For generating insights (ollama client)
            fast_model: Fast LLM for compression tasks
        """
        # Storage
        self.episodic = episodic_store
        self.semantic = semantic_store
        self.event_bus = event_bus

        # LLM for insight generation
        self.llm_client = llm_client
        self.fast_model = fast_model

        # Embedding engine for similarity
        self.embedding_engine = EmbeddingEngine() if INTEGRATION_AVAILABLE else None

        # Wisdom cache (in-memory for fast access)
        self._wisdom_cache: Dict[str, Wisdom] = {}

        # Processed episode tracking
        self._processed_episodes: Set[str] = set()
        self._pending_episodes: deque = deque(maxlen=100)

        # Metrics
        self.metrics = CompressionMetrics()

        # State persistence
        self._state_path = Path("memory/compressor_state.json")
        self._wisdom_path = Path("memory/compressed_wisdom.json")

        # Load state
        self._load_state()

        # Wire up event subscriptions
        if self.event_bus:
            self._subscribe_to_events()

        logger.info("Episode Compressor initialized")

    # ========================================================================
    # EVENT SUBSCRIPTIONS
    # ========================================================================

    def _subscribe_to_events(self):
        """Subscribe to relevant organism events."""
        # Listen for completed actions
        self.event_bus.subscribe(EventType.ACTION_COMPLETE, self._on_action_complete)

        # Listen for lessons learned (from reflexion, etc.)
        self.event_bus.subscribe(EventType.LESSON_LEARNED, self._on_lesson_learned)

        logger.info("Subscribed to organism events")

    async def _on_action_complete(self, event: OrganismEvent):
        """Handle action completion events."""
        # Queue episode for compression if significant
        episode_data = event.data
        if await self.should_compress(episode_data):
            # Warn if deque is at capacity and will drop oldest episode
            if len(self._pending_episodes) >= self._pending_episodes.maxlen:
                oldest_ep = self._pending_episodes[0]
                logger.warning(
                    f"Episode queue at capacity ({self._pending_episodes.maxlen}). "
                    f"Dropping oldest uncompressed episode: {oldest_ep.get('episode_id', oldest_ep.get('memory_id', 'unknown'))}"
                )
            self._pending_episodes.append(episode_data)
            logger.debug(f"Queued episode for compression: {episode_data.get('tool', 'unknown')}")

    async def _on_lesson_learned(self, event: OrganismEvent):
        """Handle lesson learned events."""
        # Directly create wisdom from explicit lessons
        lesson_data = event.data
        wisdom = await self._create_wisdom_from_lesson(lesson_data)
        if wisdom:
            await self._store_wisdom(wisdom)
            logger.info(f"Created wisdom from lesson: {wisdom.pattern}")

    # ========================================================================
    # COMPRESSION DECISION
    # ========================================================================

    async def should_compress(self, episode: Dict[str, Any]) -> bool:
        """
        Decide if an episode is worth compressing.

        Skip trivial episodes to save resources.

        Args:
            episode: Episode data dict

        Returns:
            True if episode should be compressed
        """
        # Skip if already processed
        episode_id = episode.get('episode_id', episode.get('memory_id'))
        if episode_id and episode_id in self._processed_episodes:
            return False

        # Compress if episode has significant content
        significance_score = 0.0

        # 1. Duration indicates effort spent
        duration = episode.get('duration_seconds', 0)
        if duration > 5:  # More than 5 seconds
            significance_score += 0.3

        # 2. Multiple steps indicate complexity
        steps = episode.get('steps', [])
        if len(steps) >= 3:
            significance_score += 0.3

        # 3. Errors indicate learning opportunity
        errors = episode.get('error_messages', [])
        if errors:
            significance_score += 0.2

        # 4. Explicit importance flag
        importance = episode.get('importance', 0.5)
        significance_score += importance * 0.3

        # 5. Success/failure matters
        success = episode.get('success', True)
        if not success:
            significance_score += 0.2  # Failures are valuable

        # Compress if significance exceeds threshold
        return significance_score >= 0.5

    # ========================================================================
    # PATTERN EXTRACTION
    # ========================================================================

    async def extract_pattern(self, episodes: List[Dict]) -> Optional[EpisodePattern]:
        """
        Find common patterns across multiple similar episodes.

        Groups episodes by:
        - Similar tool usage
        - Similar outcomes
        - Similar context

        Args:
            episodes: List of episode dicts

        Returns:
            EpisodePattern if found, None otherwise
        """
        if len(episodes) < self.MIN_EPISODES_FOR_PATTERN:
            return None

        # Extract common tools
        tool_sets = []
        for ep in episodes:
            tools = ep.get('tools_used', [])
            if tools:
                tool_sets.append(set(tools))

        if not tool_sets:
            return None

        # Find intersection of tool sets
        common_tools = set.intersection(*tool_sets) if len(tool_sets) > 1 else tool_sets[0]
        common_tools = list(common_tools)

        if not common_tools:
            # Try union instead (tools used across group)
            common_tools = list(set.union(*tool_sets))[:5]  # Top 5

        # Calculate success rate
        successes = sum(1 for ep in episodes if ep.get('success', False))
        success_rate = successes / len(episodes)

        # Calculate average duration
        durations = [ep.get('duration_seconds', 0) for ep in episodes]
        avg_duration = sum(durations) / len(durations)

        # Extract common context (simplified)
        prompts = [ep.get('task_prompt', '') for ep in episodes]
        common_words = self._find_common_words(prompts)
        common_context = ' '.join(common_words[:5])

        # Generate pattern ID
        pattern_id = hashlib.sha256(
            f"{'_'.join(common_tools)}_{common_context}".encode()
        ).hexdigest()[:16]

        # Extract episode IDs
        episode_ids = [ep.get('memory_id', ep.get('episode_id', '')) for ep in episodes]

        pattern = EpisodePattern(
            pattern_id=pattern_id,
            common_tools=common_tools,
            common_context=common_context,
            success_rate=success_rate,
            avg_duration=avg_duration,
            episodes=episode_ids,
            insights=[]  # Will be populated by LLM
        )

        return pattern

    def _find_common_words(self, texts: List[str]) -> List[str]:
        """Find most common words across texts."""
        from collections import Counter

        # Split into words
        all_words = []
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'}

        for text in texts:
            words = text.lower().split()
            filtered = [w for w in words if w not in stopwords and len(w) > 3]
            all_words.extend(filtered)

        # Get most common
        counter = Counter(all_words)
        return [word for word, _ in counter.most_common(10)]

    # ========================================================================
    # WISDOM GENERATION
    # ========================================================================

    async def compress_episode(self, episode: Dict) -> Optional[Wisdom]:
        """
        Compress a single episode into wisdom.

        Args:
            episode: Episode data dict

        Returns:
            Wisdom object if compression successful
        """
        # Generate insight from episode using LLM
        insight_text = await self._generate_insight([episode])

        if not insight_text:
            return None

        # Extract pattern description
        pattern = self._extract_pattern_description(episode)

        # Determine wisdom type
        wisdom_type = self._classify_wisdom_type(episode, insight_text)

        # Create wisdom object
        wisdom = Wisdom(
            wisdom_id=f"wisdom_{int(time.time()*1000)}",
            pattern=pattern,
            insight=insight_text,
            wisdom_type=wisdom_type,
            confidence=0.6,  # Initial confidence
            times_validated=0,
            times_invalidated=0,
            validation_rate=0.0,
            source_episodes=[episode.get('memory_id', '')],
            source_count=1,
            context=episode.get('task_prompt', '')[:200],
            tags=episode.get('tags', []),
            created_at=time.time()
        )

        # Generate embedding
        if self.embedding_engine:
            wisdom.embedding = self.embedding_engine.get_embedding(
                f"{pattern} {insight_text}"
            )

        return wisdom

    async def compress_episodes_batch(
        self,
        episodes: List[Dict]
    ) -> List[Wisdom]:
        """
        Compress multiple related episodes into wisdom.

        More efficient than one-by-one compression.

        Args:
            episodes: List of related episodes

        Returns:
            List of wisdom objects created
        """
        if not episodes:
            return []

        # Find pattern
        pattern = await self.extract_pattern(episodes)

        if not pattern:
            # No clear pattern - compress individually
            wisdom_list = []
            for ep in episodes:
                wisdom = await self.compress_episode(ep)
                if wisdom:
                    wisdom_list.append(wisdom)
            return wisdom_list

        # Generate insight from pattern
        insight_text = await self._generate_insight_from_pattern(pattern, episodes)

        if not insight_text:
            return []

        # Create wisdom from pattern
        wisdom = Wisdom(
            wisdom_id=f"wisdom_pattern_{pattern.pattern_id}",
            pattern=f"Pattern: {pattern.common_context}",
            insight=insight_text,
            wisdom_type=WisdomType.STRATEGY,
            confidence=min(0.9, 0.6 + (len(episodes) * 0.05)),  # More episodes = higher confidence
            times_validated=0,
            times_invalidated=0,
            validation_rate=0.0,
            source_episodes=pattern.episodes,
            source_count=len(episodes),
            context=pattern.common_context,
            examples=[ep.get('task_prompt', '')[:100] for ep in episodes[:3]],
            tags=list(set(tag for ep in episodes for tag in ep.get('tags', []))),
            created_at=time.time()
        )

        # Generate embedding
        if self.embedding_engine:
            wisdom.embedding = self.embedding_engine.get_embedding(
                f"{wisdom.pattern} {wisdom.insight}"
            )

        self.metrics.total_patterns_found += 1

        return [wisdom]

    async def _generate_insight(self, episodes: List[Dict]) -> str:
        """Generate insight text from episodes using LLM."""
        if not self.llm_client:
            # Fallback: basic heuristic insight
            return self._heuristic_insight(episodes)

        try:
            # Prepare episode summary
            summary = self._summarize_episodes(episodes)

            prompt = f"""You are analyzing agent task execution to extract reusable wisdom.

Episodes:
{summary}

Generate a concise, actionable insight that can be applied to future similar tasks.
Focus on:
1. What strategy worked or didn't work
2. What to watch out for
3. Specific recommendations

Respond with just the insight (1-2 sentences, specific and actionable):"""

            response = self.llm_client.chat(
                model=self.fast_model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.3, "num_predict": 100}
            )

            insight = response['message']['content'].strip()
            return insight if insight else self._heuristic_insight(episodes)

        except Exception as e:
            logger.debug(f"LLM insight generation failed: {e}")
            return self._heuristic_insight(episodes)

    async def _generate_insight_from_pattern(
        self,
        pattern: EpisodePattern,
        episodes: List[Dict]
    ) -> str:
        """Generate insight from identified pattern."""
        if not self.llm_client:
            return f"Use {', '.join(pattern.common_tools)} when {pattern.common_context}"

        try:
            prompt = f"""You are analyzing a pattern in agent behavior.

Pattern identified:
- Common tools: {', '.join(pattern.common_tools)}
- Context: {pattern.common_context}
- Success rate: {pattern.success_rate*100:.0f}%
- Number of instances: {len(episodes)}
- Average time: {pattern.avg_duration:.1f}s

Generate a strategic insight about when and how to use this pattern effectively.
Be specific and actionable (1-2 sentences):"""

            response = self.llm_client.chat(
                model=self.fast_model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.3, "num_predict": 100}
            )

            return response['message']['content'].strip()

        except Exception as e:
            logger.debug(f"Pattern insight generation failed: {e}")
            return f"Use {', '.join(pattern.common_tools)} for {pattern.common_context} tasks (success rate: {pattern.success_rate*100:.0f}%)"

    def _heuristic_insight(self, episodes: List[Dict]) -> str:
        """Generate basic insight without LLM."""
        if not episodes:
            return "No insight available"

        # Check if mostly successful or failed
        successes = sum(1 for ep in episodes if ep.get('success', False))
        success_rate = successes / len(episodes)

        # Get common tools
        all_tools = []
        for ep in episodes:
            all_tools.extend(ep.get('tools_used', []))

        from collections import Counter
        common_tools = [tool for tool, _ in Counter(all_tools).most_common(3)]

        if success_rate > 0.7:
            return f"Successful approach: use {', '.join(common_tools)} for this type of task"
        else:
            return f"Avoid using {', '.join(common_tools)} alone - try alternative approaches"

    def _summarize_episodes(self, episodes: List[Dict]) -> str:
        """Create summary of episodes for LLM."""
        lines = []
        for i, ep in enumerate(episodes[:5], 1):  # Max 5 episodes
            lines.append(f"{i}. {ep.get('task_prompt', 'Unknown task')[:80]}")
            lines.append(f"   Outcome: {ep.get('outcome', 'Unknown')[:80]}")
            lines.append(f"   Success: {ep.get('success', False)}")
            lines.append(f"   Tools: {', '.join(ep.get('tools_used', [])[:3])}")

        return "\n".join(lines)

    def _extract_pattern_description(self, episode: Dict) -> str:
        """Extract pattern description from episode."""
        task = episode.get('task_prompt', '')
        tools = episode.get('tools_used', [])

        # Simple pattern: category + tools
        if tools:
            return f"{tools[0]} tasks"

        # Fallback to task keywords
        words = task.lower().split()
        keywords = [w for w in words if len(w) > 4][:2]
        return ' '.join(keywords) if keywords else "general tasks"

    def _classify_wisdom_type(self, episode: Dict, insight: str) -> WisdomType:
        """Classify the type of wisdom."""
        insight_lower = insight.lower()

        if 'avoid' in insight_lower or 'don\'t' in insight_lower:
            return WisdomType.PITFALL

        if 'always' in insight_lower or 'use' in insight_lower:
            return WisdomType.STRATEGY

        if 'when' in insight_lower or 'if' in insight_lower:
            return WisdomType.HEURISTIC

        if episode.get('success', False):
            return WisdomType.STRATEGY
        else:
            return WisdomType.PITFALL

    # ========================================================================
    # COMPRESSION CYCLE
    # ========================================================================

    async def run_compression_cycle(self):
        """
        Periodic compression cycle - called by sleep or heartbeat.

        Steps:
        1. Get recent uncompressed episodes
        2. Group by similarity
        3. Compress each group into wisdom
        4. Store wisdom in semantic memory
        5. Mark episodes as processed
        """
        start_time = time.time()
        logger.info("Starting compression cycle...")

        try:
            # 1. Get uncompressed episodes
            episodes = await self._get_uncompressed_episodes()

            if not episodes:
                logger.debug("No episodes to compress")
                return

            logger.info(f"Processing {len(episodes)} episodes")

            # 2. Group by similarity
            groups = self._group_similar_episodes(episodes)
            logger.info(f"Grouped into {len(groups)} pattern groups")

            # 3. Compress each group
            wisdom_created = 0
            for group in groups:
                wisdom_list = await self.compress_episodes_batch(group)
                for wisdom in wisdom_list:
                    await self._store_wisdom(wisdom)
                    wisdom_created += 1

            # 4. Mark episodes as processed
            for ep in episodes:
                ep_id = ep.get('memory_id', ep.get('episode_id'))
                if ep_id:
                    self._processed_episodes.add(ep_id)

            # 5. Update metrics
            self.metrics.total_episodes_processed += len(episodes)
            self.metrics.total_wisdom_created += wisdom_created
            self.metrics.compression_cycles += 1

            elapsed_ms = (time.time() - start_time) * 1000
            self.metrics.avg_compression_time_ms = (
                (self.metrics.avg_compression_time_ms * (self.metrics.compression_cycles - 1) + elapsed_ms)
                / self.metrics.compression_cycles
            )
            self.metrics.last_compression_time = time.time()

            if len(episodes) > 0:
                self.metrics.compression_ratio = (
                    self.metrics.total_episodes_processed / max(self.metrics.total_wisdom_created, 1)
                )

            # 6. Save state
            self._save_state()

            logger.info(f"Compression cycle complete: {wisdom_created} wisdom created from {len(episodes)} episodes in {elapsed_ms:.0f}ms")

            # 7. Publish update event
            if self.event_bus:
                await self.event_bus.publish(OrganismEvent(
                    event_type=EventType.STRATEGY_UPDATED,
                    source="episode_compressor",
                    data={
                        "wisdom_created": wisdom_created,
                        "episodes_processed": len(episodes),
                        "compression_ratio": self.metrics.compression_ratio,
                    }
                ))

        except Exception as e:
            logger.error(f"Compression cycle error: {e}")

    async def _get_uncompressed_episodes(self) -> List[Dict]:
        """Get episodes that haven't been compressed yet."""
        # First, check pending queue
        episodes = []
        while self._pending_episodes and len(episodes) < self.COMPRESSION_BATCH_SIZE:
            ep = self._pending_episodes.popleft()
            episodes.append(ep)

        # If using episodic store, query for recent unprocessed
        if self.episodic and len(episodes) < self.COMPRESSION_BATCH_SIZE:
            try:
                # Get recent episodes from store
                import sqlite3
                with sqlite3.connect(str(self.episodic.db_path)) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute("""
                        SELECT * FROM episodes
                        ORDER BY created_at DESC
                        LIMIT ?
                    """, (self.COMPRESSION_BATCH_SIZE,))
                    rows = cursor.fetchall()

                for row in rows:
                    ep_id = row['memory_id']
                    if ep_id not in self._processed_episodes:
                        # Convert row to dict
                        ep_dict = {
                            'memory_id': row['memory_id'],
                            'task_prompt': row['task_prompt'],
                            'outcome': row['outcome'],
                            'success': bool(row['success']),
                            'duration_seconds': row['duration_seconds'],
                            'tools_used': json.loads(row['tools_used']),
                            'created_at': row['created_at'],
                            'importance': row['importance'],
                            'tags': json.loads(row['tags']),
                        }
                        episodes.append(ep_dict)

                        if len(episodes) >= self.COMPRESSION_BATCH_SIZE:
                            break
            except Exception as e:
                logger.debug(f"Could not query episodic store: {e}")

        return episodes

    def _group_similar_episodes(self, episodes: List[Dict]) -> List[List[Dict]]:
        """
        Group episodes by similarity.

        Uses tool usage + embeddings for grouping.
        """
        if len(episodes) <= 1:
            return [episodes]

        # Strategy 1: Group by tool usage
        tool_groups = defaultdict(list)
        for ep in episodes:
            tools = ep.get('tools_used', [])
            tool_key = tuple(sorted(tools)) if tools else ('no_tools',)
            tool_groups[tool_key].append(ep)

        # Strategy 2: For groups > 1, try embedding similarity
        final_groups = []
        for tool_key, group in tool_groups.items():
            if len(group) < self.MIN_EPISODES_FOR_PATTERN or not self.embedding_engine:
                # Keep as is
                final_groups.append(group)
            else:
                # Further split by semantic similarity
                subgroups = self._cluster_by_embedding(group)
                final_groups.extend(subgroups)

        return final_groups

    def _cluster_by_embedding(self, episodes: List[Dict]) -> List[List[Dict]]:
        """Cluster episodes by embedding similarity."""
        if len(episodes) <= 1:
            return [episodes]

        # Generate embeddings for each episode
        embeddings = []
        for ep in episodes:
            text = ep.get('task_prompt', '') + ' ' + ep.get('outcome', '')
            emb = self.embedding_engine.get_embedding(text)
            embeddings.append(emb)

        # Simple hierarchical clustering
        clusters = [[i] for i in range(len(episodes))]

        while len(clusters) > 1:
            # Find most similar pair
            best_sim = -1
            best_pair = None

            for i in range(len(clusters)):
                for j in range(i+1, len(clusters)):
                    # Average similarity between clusters
                    sims = []
                    for idx_i in clusters[i]:
                        for idx_j in clusters[j]:
                            sim = self.embedding_engine.cosine_similarity(
                                embeddings[idx_i],
                                embeddings[idx_j]
                            )
                            sims.append(sim)

                    avg_sim = sum(sims) / len(sims)
                    if avg_sim > best_sim:
                        best_sim = avg_sim
                        best_pair = (i, j)

            # If best similarity below threshold, stop
            if best_sim < self.SIMILARITY_THRESHOLD:
                break

            # Merge best pair
            i, j = best_pair
            clusters[i].extend(clusters[j])
            clusters.pop(j)

        # Convert cluster indices back to episodes
        result = []
        for cluster in clusters:
            result.append([episodes[idx] for idx in cluster])

        return result

    # ========================================================================
    # WISDOM STORAGE & RETRIEVAL
    # ========================================================================

    async def _store_wisdom(self, wisdom: Wisdom):
        """Store wisdom in semantic memory and cache."""
        # Store in cache
        self._wisdom_cache[wisdom.wisdom_id] = wisdom

        # Store in semantic memory if available
        if self.semantic:
            # Convert to SemanticMemory format
            semantic = SemanticMemory(
                memory_id=wisdom.wisdom_id,
                memory_type=MemoryType.SEMANTIC,
                pattern=wisdom.pattern,
                content=wisdom.insight,
                context=wisdom.context,
                confidence=wisdom.confidence,
                times_validated=wisdom.times_validated,
                times_invalidated=wisdom.times_invalidated,
                created_at=datetime.fromtimestamp(wisdom.created_at).isoformat(),
                last_accessed=datetime.fromtimestamp(wisdom.last_validated).isoformat(),
                source_episodes=wisdom.source_episodes,
                tags=wisdom.tags,
                embedding=wisdom.embedding,
                examples=wisdom.examples
            )

            self.semantic.add_semantic(semantic)

        # Persist to disk
        self._save_wisdom(wisdom)

        logger.debug(f"Stored wisdom: {wisdom.pattern}")

    def get_relevant_wisdom(self, context: str, limit: int = 5) -> List[Wisdom]:
        """
        Retrieve wisdom relevant to current task.

        Args:
            context: Current task context (prompt, description)
            limit: Maximum number of wisdom to return

        Returns:
            List of relevant wisdom, sorted by relevance
        """
        # If semantic store available, use it
        if self.semantic:
            try:
                semantic_results = self.semantic.search_semantic(
                    query=context,
                    limit=limit
                )

                # Convert back to Wisdom format
                wisdom_list = []
                for sem in semantic_results:
                    wisdom = Wisdom(
                        wisdom_id=sem.memory_id,
                        pattern=sem.pattern,
                        insight=sem.content,
                        wisdom_type=WisdomType.STRATEGY,  # Default
                        confidence=sem.confidence,
                        times_validated=sem.times_validated,
                        times_invalidated=sem.times_invalidated,
                        validation_rate=(
                            sem.times_validated / max(sem.times_validated + sem.times_invalidated, 1)
                        ),
                        source_episodes=sem.source_episodes,
                        source_count=len(sem.source_episodes),
                        context=sem.context,
                        examples=sem.examples,
                        tags=sem.tags,
                        embedding=sem.embedding
                    )
                    wisdom_list.append(wisdom)

                return wisdom_list

            except Exception as e:
                logger.debug(f"Semantic search failed: {e}")

        # Fallback: search cache
        if not self._wisdom_cache:
            return []

        # Simple keyword matching
        context_lower = context.lower()
        context_words = set(context_lower.split())

        scored = []
        for wisdom in self._wisdom_cache.values():
            # Score by word overlap
            wisdom_text = f"{wisdom.pattern} {wisdom.insight}".lower()
            wisdom_words = set(wisdom_text.split())

            overlap = len(context_words & wisdom_words)
            score = overlap / max(len(context_words), 1)

            # Boost by confidence and validation rate
            score *= wisdom.confidence
            score *= (wisdom.validation_rate + 0.5)  # Even unvalidated gets some weight

            scored.append((score, wisdom))

        # Sort by score
        scored.sort(key=lambda x: x[0], reverse=True)

        return [wisdom for _, wisdom in scored[:limit]]

    def validate_wisdom(self, wisdom_id: str, validated: bool):
        """
        Update wisdom validation based on usage.

        Args:
            wisdom_id: ID of wisdom that was used
            validated: True if wisdom proved helpful, False if not
        """
        wisdom = self._wisdom_cache.get(wisdom_id)
        if not wisdom:
            return

        # Update validation counts
        if validated:
            wisdom.times_validated += 1
        else:
            wisdom.times_invalidated += 1

        # Recalculate validation rate
        total = wisdom.times_validated + wisdom.times_invalidated
        wisdom.validation_rate = wisdom.times_validated / total

        # Update confidence (exponential moving average)
        alpha = 0.2
        wisdom.confidence = (
            (1 - alpha) * wisdom.confidence +
            alpha * (1.0 if validated else 0.3)
        )

        wisdom.last_validated = time.time()

        # Update in semantic store if available
        if self.semantic:
            try:
                # Re-store with updated stats
                asyncio.create_task(self._store_wisdom(wisdom))
            except Exception as e:
                logger.debug(f"Failed to update semantic store: {e}")

        logger.info(f"Validated wisdom '{wisdom.pattern}': {validated} (confidence: {wisdom.confidence:.2f})")

    # ========================================================================
    # LESSON INTEGRATION
    # ========================================================================

    async def _create_wisdom_from_lesson(self, lesson_data: Dict) -> Optional[Wisdom]:
        """Create wisdom directly from a lesson learned event."""
        pattern = lesson_data.get('pattern', 'general')
        insight = lesson_data.get('insight', lesson_data.get('message', ''))

        if not insight:
            return None

        wisdom = Wisdom(
            wisdom_id=f"wisdom_lesson_{int(time.time()*1000)}",
            pattern=pattern,
            insight=insight,
            wisdom_type=WisdomType.INSIGHT,
            confidence=lesson_data.get('confidence', 0.7),
            times_validated=0,
            times_invalidated=0,
            validation_rate=0.0,
            source_episodes=[lesson_data.get('source', 'lesson')],
            source_count=1,
            context=lesson_data.get('context', ''),
            tags=lesson_data.get('tags', []),
            created_at=time.time()
        )

        # Generate embedding
        if self.embedding_engine:
            wisdom.embedding = self.embedding_engine.get_embedding(
                f"{pattern} {insight}"
            )

        return wisdom

    # ========================================================================
    # PERSISTENCE
    # ========================================================================

    def _save_state(self):
        """Save compressor state to disk."""
        try:
            self._state_path.parent.mkdir(exist_ok=True)

            state = {
                "processed_episodes": list(self._processed_episodes),
                "metrics": asdict(self.metrics),
                "saved_at": datetime.now().isoformat()
            }

            self._state_path.write_text(json.dumps(state, indent=2))
        except Exception as e:
            logger.debug(f"Failed to save compressor state: {e}")

    def _load_state(self):
        """Load compressor state from disk."""
        try:
            if self._state_path.exists():
                data = json.loads(self._state_path.read_text())

                self._processed_episodes = set(data.get('processed_episodes', []))

                metrics_data = data.get('metrics', {})
                for key, value in metrics_data.items():
                    if hasattr(self.metrics, key):
                        setattr(self.metrics, key, value)

                logger.info(f"Loaded compressor state: {len(self._processed_episodes)} episodes processed")
        except Exception as e:
            logger.debug(f"Could not load compressor state: {e}")

    def _save_wisdom(self, wisdom: Wisdom):
        """Save individual wisdom to disk."""
        try:
            self._wisdom_path.parent.mkdir(exist_ok=True)

            # Append to wisdom file
            wisdom_file = self._wisdom_path.parent / f"{wisdom.wisdom_id}.json"
            wisdom_file.write_text(json.dumps(asdict(wisdom), indent=2, default=str))
        except Exception as e:
            logger.debug(f"Failed to save wisdom: {e}")

    # ========================================================================
    # MONITORING
    # ========================================================================

    def get_stats(self) -> Dict:
        """Get compressor statistics."""
        return {
            "episodes_processed": self.metrics.total_episodes_processed,
            "wisdom_created": self.metrics.total_wisdom_created,
            "patterns_found": self.metrics.total_patterns_found,
            "compression_ratio": f"{self.metrics.compression_ratio:.1f}:1",
            "avg_compression_time_ms": f"{self.metrics.avg_compression_time_ms:.0f}ms",
            "compression_cycles": self.metrics.compression_cycles,
            "cached_wisdom": len(self._wisdom_cache),
            "wisdom_validation_rate": f"{self.metrics.wisdom_validation_rate*100:.0f}%",
        }

    def print_stats(self):
        """Print compression statistics."""
        stats = self.get_stats()
        print("\n=== Episode Compressor Statistics ===")
        print(f"Episodes processed: {stats['episodes_processed']}")
        print(f"Wisdom created: {stats['wisdom_created']}")
        print(f"Compression ratio: {stats['compression_ratio']}")
        print(f"Average time: {stats['avg_compression_time_ms']}")
        print(f"Cached wisdom: {stats['cached_wisdom']}")
        print()


# ============================================================================
# INTEGRATION HELPERS
# ============================================================================

def create_compressor(
    episodic_store=None,
    semantic_store=None,
    event_bus=None,
    llm_client=None,
    **kwargs
) -> EpisodeCompressor:
    """Factory function to create episode compressor."""
    return EpisodeCompressor(
        episodic_store=episodic_store,
        semantic_store=semantic_store,
        event_bus=event_bus,
        llm_client=llm_client,
        **kwargs
    )


# ============================================================================
# MAIN / DEMO
# ============================================================================

if __name__ == "__main__":
    async def demo():
        """Demo the episode compressor."""
        print("Episode Compressor - Demo")
        print("=" * 60)

        # Create compressor (standalone mode)
        compressor = EpisodeCompressor()

        # Simulate some episodes
        episodes = [
            {
                'episode_id': 'ep1',
                'task_prompt': 'Navigate to example.com and extract emails',
                'outcome': 'Found 3 email addresses',
                'success': True,
                'duration_seconds': 4.2,
                'tools_used': ['playwright_navigate', 'playwright_extract_page_fast'],
                'importance': 0.7,
                'tags': ['extraction', 'email']
            },
            {
                'episode_id': 'ep2',
                'task_prompt': 'Extract contact info from company website',
                'outcome': 'Found emails and phone numbers',
                'success': True,
                'duration_seconds': 5.1,
                'tools_used': ['playwright_navigate', 'playwright_extract_page_fast'],
                'importance': 0.8,
                'tags': ['extraction', 'contacts']
            },
            {
                'episode_id': 'ep3',
                'task_prompt': 'Find pricing information on site',
                'outcome': 'Could not locate pricing page',
                'success': False,
                'duration_seconds': 8.3,
                'tools_used': ['playwright_navigate', 'playwright_click'],
                'importance': 0.6,
                'tags': ['navigation', 'pricing']
            }
        ]

        # Check which should be compressed
        print("\nEvaluating episodes for compression...")
        for ep in episodes:
            should = await compressor.should_compress(ep)
            print(f"Episode {ep['episode_id']}: {'COMPRESS' if should else 'SKIP'}")

        # Run compression
        print("\nRunning compression cycle...")
        for ep in episodes:
            compressor._pending_episodes.append(ep)

        await compressor.run_compression_cycle()

        # Show results
        compressor.print_stats()

        # Test retrieval
        print("\nTesting wisdom retrieval...")
        wisdom_list = compressor.get_relevant_wisdom("extract emails from website")
        print(f"Found {len(wisdom_list)} relevant wisdom:")
        for w in wisdom_list:
            print(f"  - {w.pattern}: {w.insight}")

        print("\nDemo complete!")

    asyncio.run(demo())
