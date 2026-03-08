"""
Curiosity Engine - The Hunger for Knowledge

This is the breakthrough that transforms passive agents into active learners.
Divine agents don't wait for inputs - they SEEK information to fill their gaps.

PURPOSE:
- Notice what is UNKNOWN during work (knowledge gaps)
- Track what might be OUTDATED (staleness)
- PROACTIVELY investigate gaps before they cause failures
- Fill idle time with curiosity-driven exploration
- Build anticipatory knowledge that makes future actions faster

This is the difference between:
    Passive: "I'll wait for the next input"
    Divine: "I have 30 seconds - let me research this API I'll need later"

Integration:
- Subscribes to EventBus for GAP_DETECTED, ACTION_FAILED, SURPRISE events
- Parses LLM reasoning for uncertainty signals ("I don't know", "unsure", "might be")
- Called during idle periods by heartbeat
- Can trigger background investigations
- Updates memory with findings
- Feeds self_model with learned capabilities

Key Insight: Curiosity is NOT random exploration. It's TARGETED gap-filling
based on what the agent has encountered. It's the hunger that drives growth.
"""

import asyncio
import time
import re
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field, asdict
from collections import deque, defaultdict
from enum import Enum
from loguru import logger
import json

from .organism_core import EventBus, EventType, OrganismEvent


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class GapStatus(Enum):
    """Lifecycle status of a knowledge gap."""
    OPEN = "open"                    # Gap identified, not yet investigated
    INVESTIGATING = "investigating"  # Currently being investigated
    FILLED = "filled"               # Successfully filled with knowledge
    UNFILLABLE = "unfillable"       # Cannot be filled (external limitation)
    STALE = "stale"                 # Old gap, may no longer be relevant


class GapSource(Enum):
    """How was this gap discovered?"""
    REASONING = "reasoning"          # Parsed from LLM reasoning
    PREDICTION_FAILURE = "prediction_failure"  # Gap detector surprise
    ACTION_FAILURE = "action_failure"  # Failed action revealed gap
    EXPLICIT_QUESTION = "explicit_question"  # Direct question encountered
    STALENESS = "staleness"         # Information might be outdated
    CURIOSITY = "curiosity"         # Discovered during exploration


@dataclass
class KnowledgeGap:
    """
    A specific knowledge gap - something the agent knows it doesn't know.

    This is metacognition in action: awareness of ignorance.
    """
    gap_id: str
    topic: str                       # What don't we know?
    context: str                     # Where was this noticed?
    source: GapSource                # How was it discovered?

    # Priority factors
    priority: float = 0.5            # 0-1, how important to fill
    times_encountered: int = 0       # How often have we hit this gap?
    impact_score: float = 0.5        # Potential impact of filling this
    urgency: float = 0.5            # Time sensitivity

    # Lifecycle
    status: GapStatus = GapStatus.OPEN
    first_noticed: float = field(default_factory=time.time)
    last_encountered: float = field(default_factory=time.time)
    investigation_attempts: int = 0

    # Investigation results
    findings: Optional[str] = None
    confidence: float = 0.0          # 0-1, how confident are findings?
    sources: List[str] = field(default_factory=list)  # Where did we learn?

    # Related entities
    related_gaps: List[str] = field(default_factory=list)  # Other gap IDs
    related_tasks: List[str] = field(default_factory=list)  # Task IDs that hit this

    def calculate_priority(self):
        """
        Calculate priority score for this gap.

        Priority = weighted sum of:
        - Times encountered (frequency)
        - Impact score (potential value)
        - Urgency (time sensitivity)
        - Recency (how recently encountered)
        """
        # Frequency score (0-0.4)
        frequency_score = min(self.times_encountered / 10, 0.4)

        # Impact score (0-0.3)
        impact_component = self.impact_score * 0.3

        # Urgency score (0-0.2)
        urgency_component = self.urgency * 0.2

        # Recency score (0-0.1)
        time_since = time.time() - self.last_encountered
        recency = max(0, 1 - (time_since / 3600))  # Decay over 1 hour
        recency_component = recency * 0.1

        self.priority = frequency_score + impact_component + urgency_component + recency_component
        return self.priority


@dataclass
class StaleInformation:
    """Track information that might be outdated."""
    topic: str
    last_updated: float
    source: str                      # Where did we learn this?
    confidence: float = 1.0          # How confident were we?
    half_life_hours: float = 24.0   # How quickly does this become stale?

    def is_stale(self) -> bool:
        """Check if information is likely stale."""
        age_hours = (time.time() - self.last_updated) / 3600
        return age_hours > self.half_life_hours

    def staleness_score(self) -> float:
        """Return 0-1 staleness score (1 = definitely stale)."""
        age_hours = (time.time() - self.last_updated) / 3600
        return min(age_hours / self.half_life_hours, 1.0)


@dataclass
class Investigation:
    """An investigation into a knowledge gap."""
    investigation_id: str
    gap_id: str
    query: str
    method: str                      # "memory", "web", "tool", "inference"
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    success: bool = False
    findings: Optional[str] = None
    confidence: float = 0.0


# =============================================================================
# UNCERTAINTY DETECTION
# =============================================================================

class UncertaintyDetector:
    """
    Parse text for signals of uncertainty and knowledge gaps.

    This is the sensor that notices "I don't know" in reasoning.
    """

    # Uncertainty signal patterns
    UNCERTAINTY_PATTERNS = [
        # Explicit uncertainty
        r"(?i)(I (?:don't|do not) know|unsure|uncertain|unclear|ambiguous)",
        r"(?i)(not sure|can't tell|cannot determine|unable to (?:tell|determine|know))",
        r"(?i)(hard to (?:say|tell|know)|difficult to (?:say|tell|know))",

        # Hedging
        r"(?i)(might be|could be|possibly|perhaps|maybe|probably)",
        r"(?i)(appears to|seems to|looks like it (?:might|could))",
        r"(?i)(I (?:think|believe|assume|guess|suspect))",

        # Questions
        r"(?i)(what is|how (?:do|does|can)|why (?:is|does)|where (?:is|does))",
        r"(?i)(should I|do I need to|is it (?:necessary|required))",

        # Information gaps
        r"(?i)(need(?:s)? (?:more|additional) information)",
        r"(?i)((?:not|no) enough (?:data|information|context))",
        r"(?i)((?:lacking|missing) (?:information|data|context))",
        r"(?i)(would need to (?:check|verify|confirm|look up))",

        # Assumptions
        r"(?i)(assuming|if we assume|let's assume|presumably)",
        r"(?i)(based on (?:the )?assumption)",
    ]

    # Gap extraction patterns
    GAP_EXTRACTION = [
        # "I don't know [TOPIC]"
        r"(?i)(?:I )?don't know (?:about |how |what |why |if |whether )?([\w\s]+?)(?:\.|,|;|$)",

        # "unsure about [TOPIC]"
        r"(?i)(?:un)?(?:sure|certain|clear) (?:about |of |regarding |how |what |why )([\w\s]+?)(?:\.|,|;|$)",

        # "need to check [TOPIC]"
        r"(?i)need to (?:check|verify|confirm|look up|research) ([\w\s]+?)(?:\.|,|;|$)",

        # "what is [TOPIC]"
        r"(?i)what (?:is|are) (?:the )?([\w\s]+?)\?",

        # "how [ACTION]"
        r"(?i)how (?:do|does|can|to) ([\w\s]+?)\?",
    ]

    def detect_uncertainty(self, text: str) -> List[Dict[str, Any]]:
        """
        Detect uncertainty signals in text.

        Returns:
            List of detected uncertainties with context
        """
        uncertainties = []

        for pattern in self.UNCERTAINTY_PATTERNS:
            matches = re.finditer(pattern, text)
            for match in matches:
                # Extract surrounding context
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end].strip()

                uncertainties.append({
                    "signal": match.group(0),
                    "context": context,
                    "position": match.start(),
                })

        return uncertainties

    def extract_gaps(self, text: str) -> List[str]:
        """
        Extract specific knowledge gaps (topics) from text.

        Returns:
            List of topic strings representing gaps
        """
        gaps = set()

        for pattern in self.GAP_EXTRACTION:
            matches = re.finditer(pattern, text)
            for match in matches:
                if len(match.groups()) > 0:
                    topic = match.group(1).strip()
                    # Clean up the topic
                    topic = re.sub(r'\s+', ' ', topic)  # Normalize whitespace
                    topic = topic.lower()

                    # Filter out very short or very long topics
                    if 3 <= len(topic) <= 100:
                        gaps.add(topic)

        return list(gaps)

    def score_uncertainty(self, text: str) -> float:
        """
        Score overall uncertainty level in text (0-1).

        Returns:
            Uncertainty score
        """
        uncertainties = self.detect_uncertainty(text)

        if not uncertainties:
            return 0.0

        # Score based on frequency and strength
        word_count = len(text.split())
        if word_count == 0:
            return 0.0

        # Uncertainty rate (signals per 100 words)
        rate = len(uncertainties) / (word_count / 100)

        # Normalize to 0-1 (capping at 5 signals per 100 words = 1.0)
        return min(rate / 5, 1.0)


# =============================================================================
# CURIOSITY ENGINE
# =============================================================================

class CuriosityEngine:
    """
    The hunger for knowledge - proactive gap filling.

    This is what makes the agent SEEK instead of WAIT.
    """

    def __init__(
        self,
        memory_arch,           # MemoryArchitecture
        self_model,            # SelfModel
        gap_detector,          # GapDetector from organism_core
        event_bus: EventBus,
        llm_client=None,
        fast_model: str = "llama3.2:3b-instruct-q4_0",
        persistence_path: Optional[Path] = None
    ):
        self.memory = memory_arch
        self.self_model = self_model
        self.gap_detector = gap_detector
        self.event_bus = event_bus
        self.llm_client = llm_client
        self.fast_model = fast_model

        # Storage
        self.knowledge_gaps: Dict[str, KnowledgeGap] = {}
        self.stale_info: Dict[str, StaleInformation] = {}
        self.investigation_queue: deque = deque()  # Priority queue (manual sorting)

        # Detectors
        self.uncertainty_detector = UncertaintyDetector()

        # State
        self.curiosity_level: float = 0.5  # 0-1, how curious/hungry
        self.last_investigation: float = 0.0
        self.investigation_interval: float = 60.0  # Investigate every 60s when idle
        self.active_investigations: Dict[str, Investigation] = {}

        # Statistics
        self.gaps_discovered: int = 0
        self.gaps_filled: int = 0
        self.investigations_total: int = 0
        self.investigations_successful: int = 0

        # Persistence
        self.persistence_path = persistence_path or Path("memory/curiosity_state.json")

        # Load saved state
        self._load_state()

        # Subscribe to events
        self._subscribe_to_events()

        logger.info("CuriosityEngine initialized - agent is now hungry for knowledge")

    def _subscribe_to_events(self):
        """Subscribe to EventBus for automatic gap detection."""
        # Learn from gaps detected by gap detector
        self.event_bus.subscribe(EventType.GAP_DETECTED, self._on_gap_detected)

        # Learn from action failures
        self.event_bus.subscribe(EventType.ACTION_FAILED, self._on_action_failed)

        # Learn from surprises
        self.event_bus.subscribe(EventType.SURPRISE, self._on_surprise)

        # Trigger curiosity during idle periods
        self.event_bus.subscribe(EventType.HEARTBEAT, self._on_heartbeat)

        logger.debug("CuriosityEngine subscribed to EventBus")

    # =============================================================================
    # EVENT HANDLERS
    # =============================================================================

    async def _on_gap_detected(self, event: OrganismEvent):
        """Handle gap detection events."""
        gap_score = event.data.get("gap_score", 0)
        analysis = event.data.get("analysis", "")
        tool = event.data.get("tool", "")

        # Extract gaps from analysis
        if analysis:
            gaps = self.uncertainty_detector.extract_gaps(analysis)
            for topic in gaps:
                self.notice_gap(
                    context=f"Gap detected during {tool}: {analysis[:100]}",
                    reasoning=analysis,
                    topic=topic,
                    source=GapSource.PREDICTION_FAILURE,
                    impact_score=min(gap_score, 1.0)
                )

    async def _on_action_failed(self, event: OrganismEvent):
        """Handle action failure events."""
        tool = event.data.get("tool", "")
        error = event.data.get("error", "")

        # Action failures often reveal knowledge gaps
        context = f"Action failed: {tool} - {error}"

        # Extract potential gaps from error message
        gaps = self.uncertainty_detector.extract_gaps(error)
        for topic in gaps:
            self.notice_gap(
                context=context,
                reasoning=error,
                topic=topic,
                source=GapSource.ACTION_FAILURE,
                impact_score=0.7,  # Failures are high impact
                urgency=0.6
            )

    async def _on_surprise(self, event: OrganismEvent):
        """Handle critical surprises."""
        analysis = event.data.get("analysis", "")
        gap_score = event.data.get("gap_score", 0)

        # Surprises indicate significant gaps
        if analysis:
            self.notice_gap(
                context=f"Critical surprise: {analysis[:100]}",
                reasoning=analysis,
                topic=self._extract_surprise_topic(analysis),
                source=GapSource.PREDICTION_FAILURE,
                impact_score=gap_score,
                urgency=0.8  # Surprises need urgent investigation
            )

    async def _on_heartbeat(self, event: OrganismEvent):
        """Check for idle time to investigate gaps."""
        beat = event.data.get("beat", 0)

        # Investigate every N beats when idle
        if beat % 60 == 0:  # Every 60 beats (roughly 60 seconds)
            await self.on_idle()

    # =============================================================================
    # GAP DETECTION
    # =============================================================================

    def notice_gap(
        self,
        context: str,
        reasoning: str,
        topic: Optional[str] = None,
        source: GapSource = GapSource.REASONING,
        impact_score: float = 0.5,
        urgency: float = 0.5
    ):
        """
        Notice a knowledge gap during work.

        Args:
            context: Where was this noticed? (task description, URL, etc.)
            reasoning: Text containing uncertainty signals
            topic: Specific topic (extracted if not provided)
            source: How was this gap discovered?
            impact_score: 0-1 potential impact of filling this gap
            urgency: 0-1 time sensitivity
        """
        # Extract gaps from reasoning if topic not provided
        if not topic:
            gaps = self.uncertainty_detector.extract_gaps(reasoning)
            if not gaps:
                return  # No extractable gap
            topic = gaps[0]  # Take first gap

        # Generate gap ID
        gap_id = self._generate_gap_id(topic)

        # Check if we already know about this gap
        if gap_id in self.knowledge_gaps:
            gap = self.knowledge_gaps[gap_id]
            gap.times_encountered += 1
            gap.last_encountered = time.time()
            gap.calculate_priority()

            logger.debug(f"Known gap re-encountered: {topic} (times: {gap.times_encountered}, priority: {gap.priority:.2f})")
        else:
            # New gap discovered
            gap = KnowledgeGap(
                gap_id=gap_id,
                topic=topic,
                context=context,
                source=source,
                impact_score=impact_score,
                urgency=urgency,
                times_encountered=1
            )
            gap.calculate_priority()

            self.knowledge_gaps[gap_id] = gap
            self.gaps_discovered += 1

            logger.info(f"New knowledge gap discovered: {topic} (priority: {gap.priority:.2f})")

            # Add to investigation queue
            self._queue_investigation(gap)

        # Update curiosity level
        self._update_curiosity_level()

        # Save state
        if len(self.knowledge_gaps) % 5 == 0:
            self._save_state()

    def notice_staleness(self, topic: str, last_updated: float, source: str = "", half_life_hours: float = 24.0):
        """
        Track information that might be outdated.

        Args:
            topic: What information might be stale?
            last_updated: When was this last confirmed?
            source: Where did we learn this?
            half_life_hours: How quickly does this become stale?
        """
        stale_info = StaleInformation(
            topic=topic,
            last_updated=last_updated,
            source=source,
            half_life_hours=half_life_hours
        )

        self.stale_info[topic] = stale_info

        # If already stale, create a gap
        if stale_info.is_stale():
            self.notice_gap(
                context=f"Stale information: {topic}",
                reasoning=f"Information about {topic} is {stale_info.staleness_score():.0%} stale",
                topic=topic,
                source=GapSource.STALENESS,
                impact_score=0.3,
                urgency=stale_info.staleness_score()
            )

    def extract_gaps_from_reasoning(self, text: str) -> List[str]:
        """
        Parse reasoning text for uncertainty signals.

        Args:
            text: Reasoning text to parse

        Returns:
            List of discovered gap topics
        """
        return self.uncertainty_detector.extract_gaps(text)

    def _extract_surprise_topic(self, analysis: str) -> str:
        """Extract topic from surprise analysis."""
        # Try to extract a clear topic
        gaps = self.uncertainty_detector.extract_gaps(analysis)
        if gaps:
            return gaps[0]

        # Fallback: use first few words
        words = analysis.split()[:5]
        return " ".join(words)

    def _generate_gap_id(self, topic: str) -> str:
        """Generate deterministic gap ID from topic."""
        normalized = topic.lower().strip()
        return hashlib.md5(normalized.encode()).hexdigest()[:16]

    # =============================================================================
    # INVESTIGATION
    # =============================================================================

    async def on_idle(self):
        """
        Called when nothing to do - investigate gaps.

        This is where curiosity turns idle time into growth.
        """
        # Check if enough time has passed since last investigation
        if time.time() - self.last_investigation < self.investigation_interval:
            return

        # Get highest priority gap
        gap = self.get_highest_priority_gap()

        if gap and not self.should_interrupt_for_gap(gap):
            # Gap exists but not urgent - maybe investigate anyway
            if gap.priority < 0.3:
                return  # Too low priority for idle investigation

        if gap:
            logger.info(f"Idle time detected - investigating gap: {gap.topic}")
            await self.investigate(gap)
            self.last_investigation = time.time()

    async def investigate(self, gap: KnowledgeGap):
        """
        Proactively fill a knowledge gap.

        Investigation strategy:
        1. Check memory first (fastest)
        2. Use LLM inference if available
        3. Search web if needed (future: integration with WebFetch)
        4. Store findings in memory

        Args:
            gap: Knowledge gap to investigate
        """
        gap.status = GapStatus.INVESTIGATING
        gap.investigation_attempts += 1
        self.investigations_total += 1

        investigation_id = f"inv_{int(time.time() * 1000)}"
        investigation = Investigation(
            investigation_id=investigation_id,
            gap_id=gap.gap_id,
            query=gap.topic,
            method="unknown"
        )

        self.active_investigations[investigation_id] = investigation

        logger.debug(f"Investigating: {gap.topic} (attempt {gap.investigation_attempts})")

        try:
            # Step 1: Check memory
            findings = await self._investigate_memory(gap)
            if findings:
                investigation.method = "memory"
                investigation.success = True
                investigation.findings = findings
                investigation.confidence = 0.8
                logger.info(f"Gap filled from memory: {gap.topic}")

            # Step 2: Use LLM inference if memory didn't help
            if not findings and self.llm_client:
                findings = await self._investigate_llm(gap)
                if findings:
                    investigation.method = "inference"
                    investigation.success = True
                    investigation.findings = findings
                    investigation.confidence = 0.6
                    logger.info(f"Gap filled from LLM inference: {gap.topic}")

            # Step 3: Web search (placeholder for future integration)
            if not findings:
                findings = await self._investigate_web(gap)
                if findings:
                    investigation.method = "web"
                    investigation.success = True
                    investigation.findings = findings
                    investigation.confidence = 0.7
                    logger.info(f"Gap filled from web search: {gap.topic}")

            # Store findings
            if findings:
                gap.status = GapStatus.FILLED
                gap.findings = findings
                gap.confidence = investigation.confidence
                gap.sources = [investigation.method]
                self.gaps_filled += 1
                self.investigations_successful += 1

                # Store in memory
                await self._store_findings(gap, findings)

                # Publish success event
                await self.event_bus.publish(OrganismEvent(
                    event_type=EventType.LESSON_LEARNED,
                    source="curiosity_engine",
                    data={
                        "gap_topic": gap.topic,
                        "findings": findings[:200],
                        "method": investigation.method,
                        "confidence": investigation.confidence,
                    }
                ))
            else:
                # Failed to fill gap
                if gap.investigation_attempts >= 3:
                    gap.status = GapStatus.UNFILLABLE
                    logger.warning(f"Gap marked unfillable after {gap.investigation_attempts} attempts: {gap.topic}")
                else:
                    gap.status = GapStatus.OPEN

        except Exception as e:
            logger.error(f"Investigation failed: {e}")
            gap.status = GapStatus.OPEN

        finally:
            investigation.completed_at = time.time()
            del self.active_investigations[investigation_id]

            # Update curiosity level
            self._update_curiosity_level()

    async def _investigate_memory(self, gap: KnowledgeGap) -> Optional[str]:
        """Search memory for relevant information."""
        if not self.memory:
            return None

        try:
            # Search semantic memory
            semantic_results = self.memory.search_semantic(gap.topic, limit=3)

            if semantic_results:
                findings = []
                for result in semantic_results:
                    findings.append(f"{result.pattern}: {result.content}")

                return " | ".join(findings)

            # Search episodic memory
            episodic_results = self.memory.search_episodes(gap.topic, limit=2)

            if episodic_results:
                findings = []
                for result in episodic_results:
                    findings.append(f"From task '{result.task_prompt}': {result.compressed_content}")

                return " | ".join(findings)

        except Exception as e:
            logger.debug(f"Memory search failed: {e}")

        return None

    async def _investigate_llm(self, gap: KnowledgeGap) -> Optional[str]:
        """Use LLM to infer knowledge about the gap."""
        if not self.llm_client:
            return None

        try:
            prompt = f"""You are being asked about a knowledge gap.

Topic: {gap.topic}
Context: {gap.context}

Based on your training, provide a brief, factual answer (2-3 sentences max).
If you genuinely don't know, say "I don't have reliable information about this."

Answer:"""

            response = self.llm_client.chat(
                model=self.fast_model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.3, "num_predict": 150}
            )

            answer = response['message']['content'].strip()

            # Check if LLM admits ignorance
            if "don't have" in answer.lower() or "don't know" in answer.lower():
                return None

            return answer

        except Exception as e:
            logger.debug(f"LLM investigation failed: {e}")

        return None

    async def _investigate_web(self, gap: KnowledgeGap) -> Optional[str]:
        """
        Search web for information (placeholder).

        Future: Integrate with WebFetch tool for real web search.
        """
        # Placeholder - would use WebFetch or similar
        logger.debug(f"Web search not yet implemented for: {gap.topic}")
        return None

    async def _store_findings(self, gap: KnowledgeGap, findings: str):
        """Store investigation findings in memory."""
        if not self.memory:
            return

        try:
            # Store as semantic memory
            from .memory_architecture import SemanticMemory

            memory_id = hashlib.md5(f"{gap.topic}_findings".encode()).hexdigest()[:16]

            semantic = SemanticMemory(
                memory_id=memory_id,
                memory_type=self.memory.semantic.scorer.embedding_engine.get_embedding.__self__.__class__.__name__,  # Hack to get type
                pattern=f"Knowledge about: {gap.topic}",
                content=findings,
                context=gap.context,
                confidence=gap.confidence,
                created_at=datetime.now().isoformat(),
                last_accessed=datetime.now().isoformat(),
                tags=["curiosity", "gap_filled"]
            )

            # Generate embedding
            semantic.embedding = self.memory.scorer.embedding_engine.get_embedding(
                f"{gap.topic} {findings}"
            )

            self.memory.semantic.add_semantic(semantic)
            logger.debug(f"Stored findings in semantic memory: {gap.topic}")

        except Exception as e:
            logger.warning(f"Failed to store findings: {e}")

    # =============================================================================
    # PRIORITIZATION
    # =============================================================================

    def prioritize_gaps(self) -> List[KnowledgeGap]:
        """
        Rank gaps by importance.

        Returns:
            Sorted list of gaps (highest priority first)
        """
        # Update all priorities
        for gap in self.knowledge_gaps.values():
            if gap.status == GapStatus.OPEN:
                gap.calculate_priority()

        # Sort by priority
        open_gaps = [g for g in self.knowledge_gaps.values() if g.status == GapStatus.OPEN]
        return sorted(open_gaps, key=lambda g: g.priority, reverse=True)

    def get_highest_priority_gap(self) -> Optional[KnowledgeGap]:
        """Get the most important gap to investigate."""
        prioritized = self.prioritize_gaps()
        return prioritized[0] if prioritized else None

    def _queue_investigation(self, gap: KnowledgeGap):
        """Add gap to investigation queue."""
        # Simple priority queue (could be optimized with heapq)
        self.investigation_queue.append(gap.gap_id)

        # Keep queue bounded
        if len(self.investigation_queue) > 50:
            self.investigation_queue.popleft()

    def should_interrupt_for_gap(self, gap: KnowledgeGap) -> bool:
        """
        Is this gap important enough to investigate NOW?

        Returns:
            True if gap is urgent enough to interrupt current work
        """
        # High priority + high urgency = interrupt
        return gap.priority > 0.7 and gap.urgency > 0.7

    # =============================================================================
    # CURIOSITY METRICS
    # =============================================================================

    def get_curiosity_level(self) -> float:
        """
        Return 0-1 how curious/hungry the agent is.

        More gaps = more curiosity
        Recently filled gaps = less curiosity
        """
        return self.curiosity_level

    def _update_curiosity_level(self):
        """Recalculate curiosity level based on gaps."""
        open_gaps = [g for g in self.knowledge_gaps.values() if g.status == GapStatus.OPEN]

        if not open_gaps:
            self.curiosity_level = 0.1  # Minimal baseline curiosity
            return

        # Curiosity = (number of gaps / 10) * (average priority)
        gap_count_factor = min(len(open_gaps) / 10, 1.0)
        avg_priority = sum(g.priority for g in open_gaps) / len(open_gaps)

        self.curiosity_level = 0.1 + (0.9 * gap_count_factor * avg_priority)
        self.curiosity_level = max(0.0, min(1.0, self.curiosity_level))

    def get_exploration_suggestions(self) -> List[str]:
        """
        Suggest topics to explore when idle.

        Returns:
            List of topic suggestions
        """
        suggestions = []

        # Top priority gaps
        prioritized = self.prioritize_gaps()
        for gap in prioritized[:5]:
            suggestions.append(f"Investigate: {gap.topic} (priority: {gap.priority:.2f})")

        # Stale information
        for topic, info in self.stale_info.items():
            if info.is_stale():
                suggestions.append(f"Refresh stale info: {topic} (staleness: {info.staleness_score():.0%})")

        # Related gaps that might benefit from joint investigation
        gap_clusters = self._find_gap_clusters()
        for cluster in gap_clusters[:2]:
            suggestions.append(f"Explore cluster: {', '.join(cluster[:3])}")

        return suggestions

    def _find_gap_clusters(self) -> List[List[str]]:
        """Find clusters of related gaps."""
        # Simple keyword-based clustering
        clusters = defaultdict(list)

        for gap in self.knowledge_gaps.values():
            if gap.status == GapStatus.OPEN:
                # Use first two words as cluster key
                words = gap.topic.split()[:2]
                key = " ".join(words)
                clusters[key].append(gap.topic)

        # Return clusters with 2+ items
        return [topics for topics in clusters.values() if len(topics) >= 2]

    # =============================================================================
    # REPORTING
    # =============================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get curiosity engine status."""
        open_gaps = [g for g in self.knowledge_gaps.values() if g.status == GapStatus.OPEN]
        filled_gaps = [g for g in self.knowledge_gaps.values() if g.status == GapStatus.FILLED]
        unfillable_gaps = [g for g in self.knowledge_gaps.values() if g.status == GapStatus.UNFILLABLE]

        return {
            "curiosity_level": self.curiosity_level,
            "gaps": {
                "total": len(self.knowledge_gaps),
                "open": len(open_gaps),
                "filled": len(filled_gaps),
                "unfillable": len(unfillable_gaps),
                "fill_rate": self.gaps_filled / max(self.gaps_discovered, 1),
            },
            "investigations": {
                "total": self.investigations_total,
                "successful": self.investigations_successful,
                "success_rate": self.investigations_successful / max(self.investigations_total, 1),
                "active": len(self.active_investigations),
            },
            "top_gaps": [
                {
                    "topic": gap.topic,
                    "priority": gap.priority,
                    "times_encountered": gap.times_encountered,
                    "status": gap.status.value,
                }
                for gap in self.prioritize_gaps()[:5]
            ],
            "stale_info_count": len([i for i in self.stale_info.values() if i.is_stale()]),
        }

    def describe_hunger(self) -> str:
        """Generate natural language description of curiosity state."""
        status = self.get_status()

        hunger_desc = "ravenous" if self.curiosity_level > 0.8 else \
                     "hungry" if self.curiosity_level > 0.6 else \
                     "curious" if self.curiosity_level > 0.4 else \
                     "mildly curious" if self.curiosity_level > 0.2 else \
                     "satisfied"

        return f"""I am {hunger_desc} for knowledge (curiosity: {self.curiosity_level:.0%}).

Knowledge gaps: {status['gaps']['open']} open, {status['gaps']['filled']} filled
Fill rate: {status['gaps']['fill_rate']:.0%}
Investigation success rate: {status['investigations']['success_rate']:.0%}

Top curiosities:
{chr(10).join(f"- {g['topic']} (priority: {g['priority']:.2f}, seen {g['times_encountered']}x)" for g in status['top_gaps'][:3])}"""

    # =============================================================================
    # PERSISTENCE
    # =============================================================================

    def _save_state(self):
        """Save curiosity state to disk."""
        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "knowledge_gaps": {
                    gap_id: {
                        "topic": gap.topic,
                        "context": gap.context[:200],  # Truncate context
                        "source": gap.source.value,
                        "priority": gap.priority,
                        "times_encountered": gap.times_encountered,
                        "impact_score": gap.impact_score,
                        "urgency": gap.urgency,
                        "status": gap.status.value,
                        "first_noticed": gap.first_noticed,
                        "last_encountered": gap.last_encountered,
                        "investigation_attempts": gap.investigation_attempts,
                        "findings": gap.findings,
                        "confidence": gap.confidence,
                    }
                    for gap_id, gap in self.knowledge_gaps.items()
                },
                "statistics": {
                    "gaps_discovered": self.gaps_discovered,
                    "gaps_filled": self.gaps_filled,
                    "investigations_total": self.investigations_total,
                    "investigations_successful": self.investigations_successful,
                    "curiosity_level": self.curiosity_level,
                },
                "saved_at": datetime.now().isoformat(),
            }

            self.persistence_path.write_text(json.dumps(data, indent=2))
            logger.debug(f"Curiosity state saved to {self.persistence_path}")

        except Exception as e:
            logger.error(f"Failed to save curiosity state: {e}")

    def _load_state(self):
        """Load curiosity state from disk."""
        if not self.persistence_path.exists():
            return

        try:
            data = json.loads(self.persistence_path.read_text())

            # Load gaps
            for gap_id, gap_data in data.get("knowledge_gaps", {}).items():
                gap = KnowledgeGap(
                    gap_id=gap_id,
                    topic=gap_data["topic"],
                    context=gap_data["context"],
                    source=GapSource(gap_data["source"]),
                    priority=gap_data["priority"],
                    times_encountered=gap_data["times_encountered"],
                    impact_score=gap_data["impact_score"],
                    urgency=gap_data["urgency"],
                    status=GapStatus(gap_data["status"]),
                    first_noticed=gap_data["first_noticed"],
                    last_encountered=gap_data["last_encountered"],
                    investigation_attempts=gap_data["investigation_attempts"],
                    findings=gap_data.get("findings"),
                    confidence=gap_data.get("confidence", 0.0),
                )
                self.knowledge_gaps[gap_id] = gap

            # Load statistics
            stats = data.get("statistics", {})
            self.gaps_discovered = stats.get("gaps_discovered", 0)
            self.gaps_filled = stats.get("gaps_filled", 0)
            self.investigations_total = stats.get("investigations_total", 0)
            self.investigations_successful = stats.get("investigations_successful", 0)
            self.curiosity_level = stats.get("curiosity_level", 0.5)

            logger.info(f"Curiosity state loaded: {len(self.knowledge_gaps)} gaps, {self.gaps_filled} filled")

        except Exception as e:
            logger.warning(f"Failed to load curiosity state: {e}")

    def force_save(self):
        """Force immediate save of state."""
        self._save_state()


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_curiosity_engine: Optional[CuriosityEngine] = None


def get_curiosity_engine() -> Optional[CuriosityEngine]:
    """Get the current CuriosityEngine instance."""
    return _curiosity_engine


def init_curiosity_engine(
    memory_arch,
    self_model,
    gap_detector,
    event_bus: EventBus,
    **kwargs
) -> CuriosityEngine:
    """Initialize the CuriosityEngine singleton."""
    global _curiosity_engine
    _curiosity_engine = CuriosityEngine(
        memory_arch=memory_arch,
        self_model=self_model,
        gap_detector=gap_detector,
        event_bus=event_bus,
        **kwargs
    )
    return _curiosity_engine
