"""
Sleep Cycle - The Consolidation System

This is the AGI organism's rest and reorganization mechanism. Continuous operation
without consolidation leads to memory bloat, knowledge drift, and degraded performance.
Sleep is when learning becomes permanent, memories consolidate, and the system resets.

Purpose:
- Prevent memory bloat from continuous operation
- Consolidate episodic memories into semantic wisdom
- Decay unused/stale memories to maintain relevance
- Reinforce frequently-used pathways for faster access
- Recalibrate self-model based on accumulated experience
- Dream (optional): simulate edge cases for robustness

Architecture:
    Heartbeat → Tick Counter → Threshold Check → Enter Sleep
        ↓
    5 Sleep Phases:
        1. Compress - Episodes → Wisdom (via episode_compressor)
        2. Decay - Remove stale, unused memories
        3. Reinforce - Strengthen hot paths
        4. Recalibrate - Update self-model
        5. Dream - Simulate edge cases (optional)
        ↓
    Exit Sleep → Reset Counter → Resume Operation

Integration:
- Called by HeartbeatLoop every beat via tick()
- Subscribes to EventBus for HEARTBEAT events
- Publishes SLEEP_START, SLEEP_END events
- Coordinates with: episode_compressor, memory_architecture, self_model

Performance Targets:
- Sleep cycle: 5-30 seconds (non-blocking where possible)
- Memory reduction: 20-50% during consolidation
- Wisdom creation: 10:1 compression ratio
- Zero data loss of critical information

References:
- Cognitive science: sleep consolidation
- Active Inference: belief updating during rest
- Mem0: memory compression architecture
"""

import asyncio
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from loguru import logger

# Import organism components
try:
    from .organism_core import EventBus, EventType, OrganismEvent
    from .episode_compressor import EpisodeCompressor
    from .memory_architecture import MemoryArchitecture
    from .self_model import SelfModel
    INTEGRATION_AVAILABLE = True
except ImportError:
    INTEGRATION_AVAILABLE = False
    logger.warning("Integration modules not available - sleep cycle running in standalone mode")


# =============================================================================
# SLEEP EVENTS
# =============================================================================

class SleepEventType(Enum):
    """Sleep-specific events."""
    SLEEP_START = "sleep_start"
    SLEEP_END = "sleep_end"
    SLEEP_PHASE_START = "sleep_phase_start"
    SLEEP_PHASE_END = "sleep_phase_end"
    DREAM_SCENARIO = "dream_scenario"


# =============================================================================
# SLEEP PHASES
# =============================================================================

@dataclass
class SleepPhase:
    """A phase of the sleep cycle."""
    name: str
    description: str
    async_fn: Optional[Callable] = None
    duration_ms: float = 0.0
    success: bool = False
    error: Optional[str] = None


@dataclass
class SleepReport:
    """Report of what happened during sleep."""
    cycle_id: str
    started_at: str
    ended_at: str
    duration_seconds: float

    # Phase results
    phases_completed: List[str] = field(default_factory=list)
    phases_failed: List[str] = field(default_factory=list)

    # Consolidation metrics
    episodes_compressed: int = 0
    wisdom_created: int = 0
    memories_decayed: int = 0
    pathways_reinforced: int = 0
    self_model_updates: int = 0
    dream_scenarios: int = 0

    # Before/after metrics
    memory_size_before_bytes: int = 0
    memory_size_after_bytes: int = 0
    memory_reduction_pct: float = 0.0

    # Errors
    errors: List[str] = field(default_factory=list)

    def get_summary(self) -> str:
        """Get human-readable summary."""
        lines = [
            f"Sleep Cycle {self.cycle_id}",
            f"Duration: {self.duration_seconds:.1f}s",
            f"Phases: {len(self.phases_completed)}/{len(self.phases_completed) + len(self.phases_failed)} completed",
            f"",
            f"Consolidation:",
            f"  - Episodes compressed: {self.episodes_compressed}",
            f"  - Wisdom created: {self.wisdom_created}",
            f"  - Memories decayed: {self.memories_decayed}",
            f"  - Pathways reinforced: {self.pathways_reinforced}",
            f"  - Self-model updates: {self.self_model_updates}",
        ]

        if self.dream_scenarios > 0:
            lines.append(f"  - Dream scenarios: {self.dream_scenarios}")

        if self.memory_reduction_pct > 0:
            lines.append(f"  - Memory reduction: {self.memory_reduction_pct:.1f}%")

        if self.errors:
            lines.append(f"")
            lines.append(f"Errors: {len(self.errors)}")
            for err in self.errors[:3]:
                lines.append(f"  - {err}")

        return "\n".join(lines)


# =============================================================================
# DREAM ENGINE (Optional)
# =============================================================================

class DreamEngine:
    """
    Simulate edge case scenarios during sleep for robustness.

    Dreams are mental simulations that:
    - Test learned patterns against edge cases
    - Generate synthetic experiences from recent surprises
    - Discover failure modes before they occur
    - Strengthen decision boundaries
    """

    def __init__(self, memory_arch=None, self_model=None):
        self.memory = memory_arch
        self.self_model = self_model
        self.dream_history: List[Dict] = []

    async def simulate_scenarios(self, count: int = 3) -> int:
        """
        Simulate edge case scenarios.

        Args:
            count: Number of scenarios to simulate

        Returns:
            Number of scenarios simulated
        """
        if not self.memory or not self.self_model:
            logger.debug("Dream engine requires memory and self-model")
            return 0

        scenarios_run = 0

        try:
            # Get recent failures from episodic memory
            recent_failures = self.memory.search_episodes(
                query="failed error",
                limit=5,
                success_only=False
            )

            # Generate variations on those failures
            for episode in recent_failures[:count]:
                scenario = self._generate_scenario_from_failure(episode)
                if scenario:
                    self._simulate_scenario(scenario)
                    scenarios_run += 1

            logger.debug(f"Dream engine simulated {scenarios_run} scenarios")

        except Exception as e:
            logger.warning(f"Dream simulation error: {e}")

        return scenarios_run

    def _generate_scenario_from_failure(self, episode) -> Optional[Dict]:
        """Generate a 'what-if' scenario from a failure."""
        try:
            scenario = {
                "original_task": episode.task_prompt,
                "failure_mode": episode.outcome,
                "what_if": f"What if {episode.task_prompt} with different approach?",
                "timestamp": time.time()
            }
            return scenario
        except Exception:
            return None

    def _simulate_scenario(self, scenario: Dict):
        """Run mental simulation of scenario."""
        # In a full implementation, this would:
        # 1. Generate hypothetical actions
        # 2. Predict outcomes using gap detector
        # 3. Store insights as semantic memory

        # For now, just record that we dreamed about it
        self.dream_history.append(scenario)

        # Keep dream history bounded
        if len(self.dream_history) > 100:
            self.dream_history.pop(0)


# =============================================================================
# SLEEP CYCLE
# =============================================================================

class SleepCycle:
    """
    The consolidation cycle - rest, reorganize, reinforce.

    This is the agent's sleep mechanism. During sleep:
    - Raw experiences compress into wisdom
    - Stale memories decay to prevent bloat
    - Frequently-used patterns strengthen
    - Self-model recalibrates from experience
    - Edge cases get mentally simulated (dreams)

    Sleep is triggered automatically based on heartbeat count,
    or can be forced manually.
    """

    def __init__(
        self,
        episode_compressor: Optional['EpisodeCompressor'] = None,
        memory_arch: Optional['MemoryArchitecture'] = None,
        self_model: Optional['SelfModel'] = None,
        gap_detector = None,
        event_bus: Optional[EventBus] = None,
        heartbeat = None,
        sleep_threshold: int = 1000,  # Heartbeats before sleep needed
        enable_dreams: bool = True
    ):
        """
        Initialize the sleep cycle.

        Args:
            episode_compressor: For compressing episodes into wisdom
            memory_arch: Memory architecture to consolidate
            self_model: Self-model to recalibrate
            gap_detector: For prediction during dreams (optional)
            event_bus: For publishing sleep events
            heartbeat: Heartbeat loop for tick tracking
            sleep_threshold: Heartbeats before sleep is triggered
            enable_dreams: Whether to run dream simulations
        """
        self.episode_compressor = episode_compressor
        self.memory = memory_arch
        self.self_model = self_model
        self.gap_detector = gap_detector
        self.event_bus = event_bus
        self.heartbeat = heartbeat

        # Sleep configuration
        self.sleep_threshold = sleep_threshold
        self.enable_dreams = enable_dreams

        # State
        self.cycles_since_sleep = 0
        self.is_sleeping = False
        self.total_sleep_cycles = 0
        self.last_sleep_time: Optional[float] = None

        # Dream engine (optional)
        self.dream_engine = DreamEngine(memory_arch, self_model) if enable_dreams else None

        # Sleep history
        self.sleep_reports: List[SleepReport] = []
        self._max_reports = 20  # Keep last N reports

        # Persistence
        self._state_path = Path("memory/sleep_cycle_state.json")
        self._reports_path = Path("memory/sleep_reports.json")

        # Load state
        self._load_state()

        # Subscribe to heartbeat
        if self.event_bus and INTEGRATION_AVAILABLE:
            self.event_bus.subscribe(EventType.HEARTBEAT, self._on_heartbeat)

        logger.info(f"Sleep cycle initialized (threshold: {sleep_threshold} beats, dreams: {enable_dreams})")

    # =========================================================================
    # HEARTBEAT INTEGRATION
    # =========================================================================

    async def _on_heartbeat(self, event: OrganismEvent):
        """Handle heartbeat events - check if sleep is needed."""
        if not self.is_sleeping:
            self.tick()
            await self.maybe_sleep()

    def tick(self):
        """Called each heartbeat to track wakefulness."""
        if not self.is_sleeping:
            self.cycles_since_sleep += 1

    # =========================================================================
    # SLEEP DECISION & EXECUTION
    # =========================================================================

    async def maybe_sleep(self) -> bool:
        """
        Check if sleep is needed and trigger if so.

        Returns:
            True if sleep was triggered
        """
        if self.cycles_since_sleep >= self.sleep_threshold and not self.is_sleeping:
            logger.info(f"Sleep threshold reached ({self.cycles_since_sleep} beats), entering sleep...")
            await self.enter_sleep()
            return True
        return False

    async def enter_sleep(self):
        """
        Begin sleep cycle - reduces activity, starts consolidation.
        """
        if self.is_sleeping:
            logger.warning("Already sleeping, cannot enter sleep again")
            return

        self.is_sleeping = True
        self.total_sleep_cycles += 1

        start_time = time.time()
        cycle_id = f"sleep_{int(start_time)}"

        logger.info(f"[{cycle_id}] Entering sleep cycle...")

        # Publish sleep start event
        if self.event_bus and INTEGRATION_AVAILABLE:
            await self.event_bus.publish(OrganismEvent(
                event_type=EventType.HEARTBEAT,  # Using HEARTBEAT as base, extend if needed
                source="sleep_cycle",
                data={
                    "event": "sleep_start",
                    "cycle_id": cycle_id,
                    "cycles_awake": self.cycles_since_sleep,
                    "total_cycles": self.total_sleep_cycles
                }
            ))

        # Create report
        report = SleepReport(
            cycle_id=cycle_id,
            started_at=datetime.now().isoformat(),
            ended_at="",
            duration_seconds=0.0
        )

        # Get memory size before
        report.memory_size_before_bytes = self._estimate_memory_size()

        # Run consolidation
        await self.consolidate(report)

        # Get memory size after
        report.memory_size_after_bytes = self._estimate_memory_size()

        # Calculate reduction
        if report.memory_size_before_bytes > 0:
            reduction = report.memory_size_before_bytes - report.memory_size_after_bytes
            report.memory_reduction_pct = (reduction / report.memory_size_before_bytes) * 100

        # Complete report
        end_time = time.time()
        report.ended_at = datetime.now().isoformat()
        report.duration_seconds = end_time - start_time

        # Store report
        self.sleep_reports.append(report)
        if len(self.sleep_reports) > self._max_reports:
            self.sleep_reports.pop(0)

        # Publish sleep end event
        if self.event_bus and INTEGRATION_AVAILABLE:
            await self.event_bus.publish(OrganismEvent(
                event_type=EventType.HEARTBEAT,
                source="sleep_cycle",
                data={
                    "event": "sleep_end",
                    "cycle_id": cycle_id,
                    "duration_seconds": report.duration_seconds,
                    "memory_reduction_pct": report.memory_reduction_pct,
                    "wisdom_created": report.wisdom_created,
                    "memories_decayed": report.memories_decayed
                }
            ))

        # Exit sleep
        self.is_sleeping = False
        self.cycles_since_sleep = 0
        self.last_sleep_time = end_time

        # Save state
        self._save_state()

        logger.info(f"[{cycle_id}] Sleep cycle complete: {report.get_summary()}")

    async def consolidate(self, report: SleepReport):
        """
        The main sleep work - 5 consolidation phases.

        Args:
            report: Sleep report to populate with results
        """
        phases = [
            SleepPhase(
                name="compress",
                description="Compress episodes into wisdom",
                async_fn=self._phase_compress
            ),
            SleepPhase(
                name="decay",
                description="Decay stale, unaccessed memories",
                async_fn=self._phase_decay
            ),
            SleepPhase(
                name="reinforce",
                description="Reinforce frequently-used pathways",
                async_fn=self._phase_reinforce
            ),
            SleepPhase(
                name="recalibrate",
                description="Recalibrate self-model",
                async_fn=self._phase_recalibrate
            ),
            SleepPhase(
                name="dream",
                description="Simulate edge case scenarios",
                async_fn=self._phase_dream
            ),
        ]

        # Run each phase
        for phase in phases:
            if phase.async_fn is None:
                continue

            logger.debug(f"Sleep phase: {phase.name} - {phase.description}")

            phase_start = time.time()

            try:
                # Run phase
                result = await phase.async_fn(report)

                phase.success = True
                phase.duration_ms = (time.time() - phase_start) * 1000
                report.phases_completed.append(phase.name)

                logger.debug(f"Phase {phase.name} completed in {phase.duration_ms:.0f}ms")

            except Exception as e:
                phase.success = False
                phase.error = str(e)
                phase.duration_ms = (time.time() - phase_start) * 1000
                report.phases_failed.append(phase.name)
                report.errors.append(f"{phase.name}: {str(e)}")

                logger.error(f"Phase {phase.name} failed: {e}")

    # =========================================================================
    # SLEEP PHASES IMPLEMENTATION
    # =========================================================================

    async def _phase_compress(self, report: SleepReport):
        """Phase 1: Compress episodes into wisdom using episode compressor."""
        if not self.episode_compressor:
            logger.debug("Episode compressor not available, skipping compress phase")
            return

        # Get metrics before
        before_metrics = self.episode_compressor.metrics

        # Run compression cycle
        await self.episode_compressor.run_compression_cycle()

        # Get metrics after
        after_metrics = self.episode_compressor.metrics

        # Update report
        report.episodes_compressed = (
            after_metrics.total_episodes_processed - before_metrics.total_episodes_processed
        )
        report.wisdom_created = (
            after_metrics.total_wisdom_created - before_metrics.total_wisdom_created
        )

        logger.debug(f"Compressed {report.episodes_compressed} episodes into {report.wisdom_created} wisdom")

    async def _phase_decay(self, report: SleepReport):
        """Phase 2: Decay old, unaccessed memories."""
        if not self.memory:
            logger.debug("Memory architecture not available, skipping decay phase")
            return

        # Run memory decay
        decayed = await self.memory.decay_memories(
            max_age_days=30,
            min_score=0.3
        )

        report.memories_decayed = decayed

        logger.debug(f"Decayed {decayed} stale memories")

    async def _phase_reinforce(self, report: SleepReport):
        """Phase 3: Reinforce frequently-used pathways."""
        if not self.memory:
            logger.debug("Memory architecture not available, skipping reinforce phase")
            return

        # Reinforce hot paths by boosting their scores
        # This happens implicitly through access count tracking
        # Here we just log what was reinforced

        # Get frequently accessed memories
        # (In a full implementation, we'd boost their composite scores)

        reinforced = 0

        # For now, just count high-access memories as "reinforced"
        try:
            import sqlite3

            # Check episodic memory
            with sqlite3.connect(str(self.memory.episodic.db_path)) as conn:
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM episodes
                    WHERE access_count >= 5
                """)
                episodic_reinforced = cursor.fetchone()[0]
                reinforced += episodic_reinforced

            # Check semantic memory
            with sqlite3.connect(str(self.memory.semantic.db_path)) as conn:
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM semantic
                    WHERE access_count >= 3
                """)
                semantic_reinforced = cursor.fetchone()[0]
                reinforced += semantic_reinforced

        except Exception as e:
            logger.debug(f"Could not count reinforced paths: {e}")

        report.pathways_reinforced = reinforced

        logger.debug(f"Reinforced {reinforced} frequently-used pathways")

    async def _phase_recalibrate(self, report: SleepReport):
        """Phase 4: Recalibrate self-model from accumulated experience."""
        if not self.self_model:
            logger.debug("Self-model not available, skipping recalibrate phase")
            return

        # Get current capability count
        before_caps = len(self.self_model.capabilities)
        before_profs = len(self.self_model.proficiencies)

        # Recalibrate by saving current state (persists learned capabilities)
        self.self_model.force_save()

        # Get after count
        after_caps = len(self.self_model.capabilities)
        after_profs = len(self.self_model.proficiencies)

        updates = (after_caps - before_caps) + (after_profs - before_profs)
        report.self_model_updates = max(0, updates)

        logger.debug(f"Self-model recalibrated: {after_caps} capabilities, {after_profs} proficiencies")

    async def _phase_dream(self, report: SleepReport):
        """Phase 5: Dream - simulate edge case scenarios (optional)."""
        if not self.enable_dreams or not self.dream_engine:
            logger.debug("Dreams disabled or engine not available, skipping dream phase")
            return

        # Simulate scenarios
        scenarios = await self.dream_engine.simulate_scenarios(count=3)

        report.dream_scenarios = scenarios

        logger.debug(f"Dreamed {scenarios} edge case scenarios")

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def get_tiredness(self) -> float:
        """
        Return 0-1 how badly sleep is needed.

        Returns:
            0.0 = fully rested, 1.0 = urgently needs sleep
        """
        return min(1.0, self.cycles_since_sleep / self.sleep_threshold)

    def should_defer_task(self, task_importance: float = 0.5) -> bool:
        """
        If very tired, should we defer non-critical tasks?

        Args:
            task_importance: 0-1 importance of task

        Returns:
            True if task should be deferred until after sleep
        """
        tiredness = self.get_tiredness()

        # If very tired (>90%) and task is not critical (<0.8 importance)
        if tiredness > 0.9 and task_importance < 0.8:
            return True

        # If critically tired (>95%) and task is not urgent (<0.9 importance)
        if tiredness > 0.95 and task_importance < 0.9:
            return True

        return False

    def force_sleep(self):
        """
        Manually trigger immediate sleep.

        Use this for:
        - End of long missions
        - After major state changes
        - Manual maintenance
        """
        if self.is_sleeping:
            logger.warning("Already sleeping, cannot force sleep")
            return

        logger.info("Forcing immediate sleep cycle...")

        # Create async task to enter sleep
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.enter_sleep())
        except RuntimeError:
            # No running loop - create one
            asyncio.run(self.enter_sleep())

    def get_sleep_report(self, cycle_id: Optional[str] = None) -> Optional[SleepReport]:
        """
        Get report from a specific sleep cycle.

        Args:
            cycle_id: ID of cycle to get report for (None = most recent)

        Returns:
            SleepReport if found, None otherwise
        """
        if not self.sleep_reports:
            return None

        if cycle_id is None:
            return self.sleep_reports[-1]

        for report in reversed(self.sleep_reports):
            if report.cycle_id == cycle_id:
                return report

        return None

    def get_last_sleep_summary(self) -> str:
        """Get summary of last sleep cycle."""
        report = self.get_sleep_report()

        if not report:
            return "No sleep cycles yet"

        return report.get_summary()

    def get_stats(self) -> Dict[str, Any]:
        """Get sleep cycle statistics."""
        avg_duration = 0.0
        avg_wisdom = 0.0
        avg_decay = 0.0

        if self.sleep_reports:
            avg_duration = sum(r.duration_seconds for r in self.sleep_reports) / len(self.sleep_reports)
            avg_wisdom = sum(r.wisdom_created for r in self.sleep_reports) / len(self.sleep_reports)
            avg_decay = sum(r.memories_decayed for r in self.sleep_reports) / len(self.sleep_reports)

        time_since_sleep = None
        if self.last_sleep_time:
            time_since_sleep = time.time() - self.last_sleep_time

        return {
            "is_sleeping": self.is_sleeping,
            "cycles_since_sleep": self.cycles_since_sleep,
            "sleep_threshold": self.sleep_threshold,
            "tiredness": self.get_tiredness(),
            "total_sleep_cycles": self.total_sleep_cycles,
            "time_since_sleep_seconds": time_since_sleep,
            "avg_sleep_duration_seconds": avg_duration,
            "avg_wisdom_per_sleep": avg_wisdom,
            "avg_decay_per_sleep": avg_decay,
            "dreams_enabled": self.enable_dreams,
        }

    def _estimate_memory_size(self) -> int:
        """Estimate total memory size in bytes."""
        total_bytes = 0

        try:
            # Get database file sizes
            if self.memory:
                if self.memory.episodic.db_path.exists():
                    total_bytes += self.memory.episodic.db_path.stat().st_size

                if self.memory.semantic.db_path.exists():
                    total_bytes += self.memory.semantic.db_path.stat().st_size

                if self.memory.skills.db_path.exists():
                    total_bytes += self.memory.skills.db_path.stat().st_size
        except Exception as e:
            logger.debug(f"Could not estimate memory size: {e}")

        return total_bytes

    # =========================================================================
    # PERSISTENCE
    # =========================================================================

    def _save_state(self):
        """Save sleep cycle state to disk."""
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "cycles_since_sleep": self.cycles_since_sleep,
                "total_sleep_cycles": self.total_sleep_cycles,
                "last_sleep_time": self.last_sleep_time,
                "sleep_threshold": self.sleep_threshold,
                "enable_dreams": self.enable_dreams,
                "saved_at": datetime.now().isoformat()
            }

            self._state_path.write_text(json.dumps(data, indent=2))

            # Save reports separately
            self._save_reports()

        except Exception as e:
            logger.debug(f"Failed to save sleep cycle state: {e}")

    def _load_state(self):
        """Load sleep cycle state from disk."""
        try:
            if self._state_path.exists():
                data = json.loads(self._state_path.read_text())

                self.cycles_since_sleep = data.get("cycles_since_sleep", 0)
                self.total_sleep_cycles = data.get("total_sleep_cycles", 0)
                self.last_sleep_time = data.get("last_sleep_time")

                # Load reports
                self._load_reports()

                logger.debug(f"Loaded sleep cycle state: {self.total_sleep_cycles} total cycles")
        except Exception as e:
            logger.debug(f"Could not load sleep cycle state: {e}")

    def _save_reports(self):
        """Save sleep reports to disk."""
        try:
            self._reports_path.parent.mkdir(parents=True, exist_ok=True)

            reports_data = [asdict(report) for report in self.sleep_reports]

            self._reports_path.write_text(json.dumps(reports_data, indent=2))

        except Exception as e:
            logger.debug(f"Failed to save sleep reports: {e}")

    def _load_reports(self):
        """Load sleep reports from disk."""
        try:
            if self._reports_path.exists():
                reports_data = json.loads(self._reports_path.read_text())

                self.sleep_reports = []
                for data in reports_data:
                    report = SleepReport(**data)
                    self.sleep_reports.append(report)

                logger.debug(f"Loaded {len(self.sleep_reports)} sleep reports")
        except Exception as e:
            logger.debug(f"Could not load sleep reports: {e}")


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================

def create_sleep_cycle(
    episode_compressor=None,
    memory_arch=None,
    self_model=None,
    gap_detector=None,
    event_bus=None,
    heartbeat=None,
    **kwargs
) -> SleepCycle:
    """Factory function to create sleep cycle."""
    return SleepCycle(
        episode_compressor=episode_compressor,
        memory_arch=memory_arch,
        self_model=self_model,
        gap_detector=gap_detector,
        event_bus=event_bus,
        heartbeat=heartbeat,
        **kwargs
    )


# =============================================================================
# MAIN / DEMO
# =============================================================================

if __name__ == "__main__":
    async def demo():
        """Demo the sleep cycle."""
        print("Sleep Cycle - Demo")
        print("=" * 60)

        # Create sleep cycle (standalone mode)
        sleep = SleepCycle(
            sleep_threshold=10,  # Sleep after 10 ticks for demo
            enable_dreams=True
        )

        print(f"\nSleep threshold: {sleep.sleep_threshold} beats")
        print(f"Dreams enabled: {sleep.enable_dreams}")

        # Simulate heartbeats
        print("\nSimulating heartbeats...")
        for i in range(15):
            sleep.tick()
            tiredness = sleep.get_tiredness()
            print(f"Beat {i+1}: tiredness = {tiredness:.1%}")

            # Check if sleep needed
            if sleep.cycles_since_sleep >= sleep.sleep_threshold:
                print(f"\nSleep threshold reached at beat {i+1}")
                await sleep.enter_sleep()
                break

            await asyncio.sleep(0.1)  # Simulate time passing

        # Show stats
        print("\nSleep Cycle Statistics:")
        stats = sleep.get_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")

        # Show last sleep report
        print("\nLast Sleep Report:")
        print(sleep.get_last_sleep_summary())

        print("\nDemo complete!")

    asyncio.run(demo())
