"""
SIAO Core - The Complete AGI Architecture

This extends organism_core.py with all 9 core components:
1. Episode Compressor - Raw experience → distilled wisdom
2. Self Model - What am I, capabilities, limits, state
3. Uncertainty Tracker - Confidence scoring, ask for help
4. Valence System - Pain/pleasure gradient awareness
5. Sleep Cycle - Consolidate, decay, reinforce, dream
6. Curiosity Engine - Proactive gap filling, hunger
7. Attention Allocator - Prioritize signals within budget
8. Immune System - Protect identity from corruption
9. Dream Engine - Simulate scenarios without acting

THE FULL SIAO STACK:
┌─────────────────────────────────────────────────────────────────┐
│                        MISSION ANCHOR                           │
│              "EverSale customers succeed because of me"         │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                        IMMUNE SYSTEM                            │
│         Screens inputs/outputs for identity threats             │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ATTENTION ALLOCATOR                        │
│              Prioritizes signals within budget                  │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────┬──────────────┬──────────────┬───────────────────┐
│   PATTERN    │    SELF      │    WORLD     │    CURIOSITY      │
│   BRAIN      │    MODEL     │    MODEL     │    ENGINE         │
│   (LLM)      │  (what am I) │ (how things  │   (fill gaps)     │
│              │              │    work)     │                   │
└──────────────┴──────────────┴──────────────┴───────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                        GAP DETECTOR                             │
│              Predict → Act → Compare → Surprise                 │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      UNCERTAINTY TRACKER                        │
│              Track confidence, ask for help when low            │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      VALENCE SYSTEM                             │
│                Pain ←───────────→ Pleasure                      │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                         EVENT BUS                               │
│                    (Nervous System)                             │
└─────────────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  SURVIVAL   │ │  AWARENESS  │ │  REFLEXION  │ │   MEMORY    │
│  MANAGER    │ │    HUB      │ │   ENGINE    │ │  (4-layer)  │
└─────────────┴─┴─────────────┴─┴─────────────┴─┴─────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    EPISODE COMPRESSOR                           │
│              Raw experience → Distilled wisdom                  │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                       TOOL HANDS                                │
│                Execute actions in world                         │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SLEEP CYCLE                                 │
│         Consolidate → Decay → Reinforce → Dream                 │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                       HEARTBEAT                                 │
│                   Always running. Always watching.              │
└─────────────────────────────────────────────────────────────────┘

When all of this runs together:
1. It wakes up (heartbeat)
2. It knows what it is (self model)
3. It knows what it cares about (mission anchor)
4. It protects its identity (immune system)
5. It prioritizes inputs (attention)
6. It predicts before acting (gap detector)
7. It knows when it's unsure (uncertainty)
8. It feels how things went (valence)
9. It remembers what mattered (episode compressor)
10. It seeks what it's missing (curiosity)
11. It consolidates overnight (sleep)
12. It dreams about edge cases (dream engine)
13. It never stops watching itself (heartbeat)

That's not an agent. That's a mind.
"""

import asyncio
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from loguru import logger

# Core organism
from .organism_core import (
    Organism, EventBus, EventType, OrganismEvent,
    HeartbeatLoop, GapDetector, MissionAnchor, Prediction, GapResult,
    get_organism, init_organism
)


@dataclass
class SIAOConfig:
    """Configuration for the SIAO core."""
    # Sleep cycle
    sleep_threshold: int = 1000  # heartbeats before sleep
    enable_dreams: bool = True

    # Attention
    attention_budget: float = 1.0
    attention_refresh_rate: float = 0.05

    # Uncertainty
    confidence_threshold_high: float = 0.7
    confidence_threshold_low: float = 0.4

    # Valence
    valence_decay_rate: float = 0.99

    # Curiosity
    max_knowledge_gaps: int = 100
    investigation_on_idle: bool = True

    # Immune
    quarantine_enabled: bool = True
    threat_log_size: int = 1000


class SIAOCore:
    """
    The complete SIAO AGI organism.

    Extends the base Organism with all 9 core components.
    """

    def __init__(
        self,
        base_organism: Organism,
        memory_arch=None,
        llm_client=None,
        fast_model: str = "llama3.2:3b-instruct-q4_0",
        config: Optional[SIAOConfig] = None
    ):
        self.organism = base_organism
        self.memory_arch = memory_arch
        self.llm_client = llm_client
        self.fast_model = fast_model
        self.config = config or SIAOConfig()

        # Core components (initialized lazily)
        self._episode_compressor = None
        self._self_model = None
        self._uncertainty_tracker = None
        self._valence_system = None
        self._sleep_cycle = None
        self._curiosity_engine = None
        self._attention_allocator = None
        self._immune_system = None
        self._dream_engine = None

        # Track initialization
        self._initialized = False

    async def initialize(self):
        """Initialize all SIAO core components."""
        if self._initialized:
            return

        logger.info("Initializing SIAO Core components...")

        # Initialize in dependency order
        await self._init_self_model()
        await self._init_valence_system()
        await self._init_immune_system()
        await self._init_attention_allocator()
        await self._init_uncertainty_tracker()
        await self._init_episode_compressor()
        await self._init_curiosity_engine()
        await self._init_dream_engine()
        await self._init_sleep_cycle()

        # Wire organism components to event bus
        self._wire_core_connections()

        self._initialized = True
        logger.info("SIAO Core fully initialized - all 9 core components active")

    async def _init_self_model(self):
        """Initialize the self model."""
        try:
            from .self_model import SelfModel, create_self_model
            self._self_model = create_self_model(
                event_bus=self.organism.event_bus,
                identity_name="EverSale Agent",
                identity_purpose=self.organism.mission_anchor.mission
            )
            logger.debug("Self Model initialized")
        except ImportError as e:
            logger.warning(f"Self Model not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize Self Model: {e}")

    async def _init_valence_system(self):
        """Initialize the valence (emotion) system."""
        try:
            from .valence_system import ValenceSystem, create_valence_system
            self._valence_system = create_valence_system(
                event_bus=self.organism.event_bus,
                decay_rate=self.config.valence_decay_rate
            )
            logger.debug("Valence System initialized")
        except ImportError as e:
            logger.warning(f"Valence System not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize Valence System: {e}")

    async def _init_immune_system(self):
        """Initialize the immune system."""
        try:
            from .immune_system import ImmuneSystem, init_immune_system
            self._immune_system = init_immune_system(
                mission_anchor=self.organism.mission_anchor,
                self_model=self._self_model,
                event_bus=self.organism.event_bus
            )
            logger.debug("Immune System initialized")
        except ImportError as e:
            logger.warning(f"Immune System not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize Immune System: {e}")

    async def _init_attention_allocator(self):
        """Initialize the attention allocator."""
        try:
            from .attention_allocator import AttentionAllocator, create_attention_allocator
            self._attention_allocator = create_attention_allocator(
                mission_anchor=self.organism.mission_anchor,
                event_bus=self.organism.event_bus,
                initial_budget=self.config.attention_budget
            )
            logger.debug("Attention Allocator initialized")
        except ImportError as e:
            logger.warning(f"Attention Allocator not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize Attention Allocator: {e}")

    async def _init_uncertainty_tracker(self):
        """Initialize the uncertainty tracker."""
        try:
            from .uncertainty_tracker import UncertaintyTracker
            self._uncertainty_tracker = UncertaintyTracker(
                memory_arch=self.memory_arch,
                self_model=self._self_model,
                event_bus=self.organism.event_bus
            )
            logger.debug("Uncertainty Tracker initialized")
        except ImportError as e:
            logger.warning(f"Uncertainty Tracker not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize Uncertainty Tracker: {e}")

    async def _init_episode_compressor(self):
        """Initialize the episode compressor."""
        try:
            from .episode_compressor import EpisodeCompressor, create_compressor

            # Get memory stores if available
            episodic_store = getattr(self.memory_arch, 'episodic', None) if self.memory_arch else None
            semantic_store = getattr(self.memory_arch, 'semantic', None) if self.memory_arch else None

            self._episode_compressor = create_compressor(
                episodic_store=episodic_store,
                semantic_store=semantic_store,
                event_bus=self.organism.event_bus,
                llm_client=self.llm_client,
                fast_model=self.fast_model
            )
            logger.debug("Episode Compressor initialized")
        except ImportError as e:
            logger.warning(f"Episode Compressor not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize Episode Compressor: {e}")

    async def _init_curiosity_engine(self):
        """Initialize the curiosity engine."""
        try:
            from .curiosity_engine import CuriosityEngine, init_curiosity_engine
            self._curiosity_engine = init_curiosity_engine(
                memory_arch=self.memory_arch,
                self_model=self._self_model,
                gap_detector=self.organism.gap_detector,
                event_bus=self.organism.event_bus,
                llm_client=self.llm_client
            )
            logger.debug("Curiosity Engine initialized")
        except ImportError as e:
            logger.warning(f"Curiosity Engine not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize Curiosity Engine: {e}")

    async def _init_dream_engine(self):
        """Initialize the dream engine."""
        try:
            from .dream_engine import DreamEngine
            self._dream_engine = DreamEngine(
                gap_detector=self.organism.gap_detector,
                memory_arch=self.memory_arch,
                llm_client=self.llm_client,
                event_bus=self.organism.event_bus
            )
            logger.debug("Dream Engine initialized")
        except ImportError as e:
            logger.warning(f"Dream Engine not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize Dream Engine: {e}")

    async def _init_sleep_cycle(self):
        """Initialize the sleep cycle."""
        try:
            from .sleep_cycle import SleepCycle
            self._sleep_cycle = SleepCycle(
                episode_compressor=self._episode_compressor,
                memory_arch=self.memory_arch,
                self_model=self._self_model,
                event_bus=self.organism.event_bus,
                heartbeat=self.organism.heartbeat,
                gap_detector=self.organism.gap_detector,
                sleep_threshold=self.config.sleep_threshold,
                enable_dreams=self.config.enable_dreams
            )
            logger.debug("Sleep Cycle initialized")
        except ImportError as e:
            logger.warning(f"Sleep Cycle not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize Sleep Cycle: {e}")

    def _wire_core_connections(self):
        """Wire all organism components together via event bus."""

        # Heartbeat → Sleep Cycle (tiredness check)
        if self._sleep_cycle:
            async def on_heartbeat_for_sleep(event: OrganismEvent):
                self._sleep_cycle.tick()
                # Check if sleep is needed
                if self._sleep_cycle.get_tiredness() > 0.9:
                    await self._sleep_cycle.maybe_sleep()

            self.organism.event_bus.subscribe(EventType.HEARTBEAT, on_heartbeat_for_sleep)

        # Heartbeat → Attention refresh
        if self._attention_allocator:
            async def on_heartbeat_for_attention(event: OrganismEvent):
                self._attention_allocator.refresh_budget()

            self.organism.event_bus.subscribe(EventType.HEARTBEAT, on_heartbeat_for_attention)

        # Heartbeat → Valence decay
        if self._valence_system:
            async def on_heartbeat_for_valence(event: OrganismEvent):
                self._valence_system.decay()

            self.organism.event_bus.subscribe(EventType.HEARTBEAT, on_heartbeat_for_valence)

        # Heartbeat → Curiosity idle check
        if self._curiosity_engine and self.config.investigation_on_idle:
            async def on_heartbeat_for_curiosity(event: OrganismEvent):
                # Every 100 beats, check if we should investigate
                beat = event.data.get("beat", 0)
                if beat % 100 == 0:
                    await self._curiosity_engine.on_idle()

            self.organism.event_bus.subscribe(EventType.HEARTBEAT, on_heartbeat_for_curiosity)

        # Action events → Self Model learning
        if self._self_model:
            async def on_action_complete(event: OrganismEvent):
                tool = event.data.get("tool", "")
                success = event.data.get("success", True)
                self._self_model.update_capability(tool, success, event.data)

            self.organism.event_bus.subscribe(EventType.ACTION_COMPLETE, on_action_complete)
            self.organism.event_bus.subscribe(EventType.ACTION_FAILED, on_action_complete)

        # Gap events → Curiosity gaps
        if self._curiosity_engine:
            async def on_gap_for_curiosity(event: OrganismEvent):
                context = event.data.get("context", "")
                analysis = event.data.get("analysis", "")
                self._curiosity_engine.notice_gap(context, analysis)

            self.organism.event_bus.subscribe(EventType.GAP_DETECTED, on_gap_for_curiosity)
            self.organism.event_bus.subscribe(EventType.SURPRISE, on_gap_for_curiosity)

        # Health events → Self Model state
        if self._self_model:
            async def on_health_check(event: OrganismEvent):
                metrics = event.data.get("metrics", {})
                self._self_model.update_state(metrics)

            self.organism.event_bus.subscribe(EventType.HEALTH_CHECK, on_health_check)

        logger.debug("SIAO core connections wired")

    # =========================================================================
    # PUBLIC API - Enhanced action lifecycle
    # =========================================================================

    async def screen_input(self, user_input: str, source: str = "user") -> Tuple[bool, str, List]:
        """Screen user input through immune system."""
        if self._immune_system:
            result = self._immune_system.screen_input(user_input, source)
            return result.safe, result.input if hasattr(result, 'input') else user_input, result.threats if hasattr(result, 'threats') else []
        return True, user_input, []

    async def screen_output(self, output: str) -> str:
        """Screen output through immune system."""
        if self._immune_system:
            result = self._immune_system.screen_output(output)
            return result.content if hasattr(result, 'content') else result
        return output

    async def assess_decision(self, task: str, proposed_action: str, tool: str = "") -> Dict:
        """Assess a decision using uncertainty tracker."""
        if self._uncertainty_tracker:
            from .uncertainty_tracker import Decision
            decision = Decision(
                decision_id=f"dec_{time.time()}",
                task_description=task,
                proposed_action=proposed_action,
                tool=tool
            )
            action = self._uncertainty_tracker.assess(decision)
            return {
                "action": action.action_type.value if hasattr(action.action_type, 'value') else str(action.action_type),
                "confidence": action.confidence,
                "reason": action.reason,
                "questions": action.suggested_questions if hasattr(action, 'suggested_questions') else []
            }
        return {"action": "proceed", "confidence": 1.0, "reason": "No uncertainty tracker"}

    def get_mood(self) -> str:
        """Get current emotional mood."""
        if self._valence_system:
            return self._valence_system.get_mood()
        return "neutral"

    def get_valence(self) -> float:
        """Get current valence (-1 to +1)."""
        if self._valence_system:
            return self._valence_system.get_valence()
        return 0.0

    def get_motivation(self) -> Dict:
        """Get current motivation from valence."""
        if self._valence_system:
            return self._valence_system.get_motivation()
        return {"strategy": "normal", "speed": 1.0, "risk_tolerance": 0.5}

    def can_i(self, action: str) -> Tuple[bool, float, str]:
        """Query self model about capability."""
        if self._self_model:
            return self._self_model.can_i(action)
        return True, 1.0, "No self model"

    def should_ask_for_help(self, task: str) -> Tuple[bool, str]:
        """Check if should ask for help."""
        if self._self_model:
            return self._self_model.should_ask_for_help(task)
        return False, ""

    def get_tiredness(self) -> float:
        """Get tiredness level (0-1)."""
        if self._sleep_cycle:
            return self._sleep_cycle.get_tiredness()
        return 0.0

    def get_curiosity_level(self) -> float:
        """Get curiosity/hunger level (0-1)."""
        if self._curiosity_engine:
            return self._curiosity_engine.get_curiosity_level()
        return 0.0

    def get_attention_budget(self) -> float:
        """Get remaining attention budget (0-1)."""
        if self._attention_allocator:
            return self._attention_allocator.attention_budget
        return 1.0

    async def get_relevant_wisdom(self, context: str) -> List:
        """Get relevant wisdom for context."""
        if self._episode_compressor:
            return self._episode_compressor.get_relevant_wisdom(context)
        return []

    async def force_sleep(self):
        """Force immediate sleep/consolidation."""
        if self._sleep_cycle:
            await self._sleep_cycle.force_sleep()

    def describe_self(self) -> str:
        """Get self-description from self model."""
        if self._self_model:
            return self._self_model.describe_self()
        return "I am the EverSale Agent."

    def get_emotional_context(self) -> str:
        """Get emotional context for LLM prompts."""
        if self._valence_system:
            return self._valence_system.get_emotional_context()
        return ""

    # =========================================================================
    # PROPERTY ACCESSORS (for health checker compatibility)
    # =========================================================================

    @property
    def valence_system(self):
        """Accessor for valence system (for health checker)."""
        return self._valence_system

    @property
    def uncertainty_tracker(self):
        """Accessor for uncertainty tracker (for health checker)."""
        return self._uncertainty_tracker

    @property
    def self_model(self):
        """Accessor for self model (for health checker)."""
        return self._self_model

    @property
    def immune_system(self):
        """Accessor for immune system (for health checker)."""
        return self._immune_system

    @property
    def curiosity_engine(self):
        """Accessor for curiosity engine (for health checker)."""
        return self._curiosity_engine

    @property
    def sleep_cycle(self):
        """Accessor for sleep cycle (for health checker)."""
        return self._sleep_cycle

    @property
    def attention_allocator(self):
        """Accessor for attention allocator (for health checker)."""
        return self._attention_allocator

    @property
    def dream_engine(self):
        """Accessor for dream engine (for health checker)."""
        return self._dream_engine

    @property
    def episode_compressor(self):
        """Accessor for episode compressor (for health checker)."""
        return self._episode_compressor

    # =========================================================================
    # STATUS AND REPORTING
    # =========================================================================

    def get_core_status(self) -> Dict:
        """Get status of all SIAO core components."""
        status = {
            "base_organism": self.organism.get_status(),
            "core_components": {
                "self_model": bool(self._self_model),
                "valence_system": bool(self._valence_system),
                "immune_system": bool(self._immune_system),
                "attention_allocator": bool(self._attention_allocator),
                "uncertainty_tracker": bool(self._uncertainty_tracker),
                "episode_compressor": bool(self._episode_compressor),
                "curiosity_engine": bool(self._curiosity_engine),
                "dream_engine": bool(self._dream_engine),
                "sleep_cycle": bool(self._sleep_cycle),
            },
            "state": {
                "mood": self.get_mood(),
                "valence": self.get_valence(),
                "tiredness": self.get_tiredness(),
                "curiosity": self.get_curiosity_level(),
                "attention_budget": self.get_attention_budget(),
            }
        }

        # Add detailed component status
        if self._valence_system:
            status["valence_details"] = {
                "current": self._valence_system.get_valence(),
                "mood": self._valence_system.get_mood(),
                "motivation": self._valence_system.get_motivation(),
            }

        if self._sleep_cycle:
            status["sleep_details"] = {
                "tiredness": self._sleep_cycle.get_tiredness(),
                "is_sleeping": self._sleep_cycle.is_sleeping,
                "cycles_since_sleep": self._sleep_cycle.cycles_since_sleep,
            }

        if self._curiosity_engine:
            status["curiosity_details"] = {
                "level": self._curiosity_engine.get_curiosity_level(),
                "open_gaps": len(self._curiosity_engine.knowledge_gaps),
            }

        return status

    def describe_state(self) -> str:
        """Get human-readable state description."""
        parts = []

        # Mood
        mood = self.get_mood()
        valence = self.get_valence()
        if valence > 0.3:
            parts.append(f"Feeling {mood} (valence: {valence:.2f})")
        elif valence < -0.3:
            parts.append(f"Feeling {mood} (valence: {valence:.2f})")
        else:
            parts.append(f"Feeling {mood}")

        # Tiredness
        tiredness = self.get_tiredness()
        if tiredness > 0.7:
            parts.append(f"Very tired ({tiredness:.0%})")
        elif tiredness > 0.4:
            parts.append(f"Somewhat tired ({tiredness:.0%})")

        # Curiosity
        curiosity = self.get_curiosity_level()
        if curiosity > 0.5:
            parts.append(f"Curious about {len(self._curiosity_engine.knowledge_gaps) if self._curiosity_engine else 0} things")

        # Attention
        attention = self.get_attention_budget()
        if attention < 0.3:
            parts.append(f"Attention depleted ({attention:.0%})")

        return " | ".join(parts) if parts else "Operating normally"


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

_siao_core: Optional[SIAOCore] = None


def get_siao_core() -> Optional[SIAOCore]:
    """Get the SIAO core singleton."""
    return _siao_core


async def init_siao_core(
    base_organism: Optional[Organism] = None,
    memory_arch=None,
    llm_client=None,
    fast_model: str = "llama3.2:3b-instruct-q4_0",
    config: Optional[SIAOConfig] = None,
    **kwargs
) -> SIAOCore:
    """
    Initialize the SIAO core.

    If base_organism is not provided, uses the global organism from organism_core.
    """
    global _siao_core

    # Get or create base organism
    if base_organism is None:
        base_organism = get_organism()
        if base_organism is None:
            # Create base organism
            base_organism = init_organism(
                memory_arch=memory_arch,
                llm_client=llm_client,
                fast_model=fast_model,
                **kwargs
            )

    # Create SIAO core
    _siao_core = SIAOCore(
        base_organism=base_organism,
        memory_arch=memory_arch,
        llm_client=llm_client,
        fast_model=fast_model,
        config=config
    )

    # Initialize all components
    await _siao_core.initialize()

    return _siao_core


async def start_siao_core():
    """Start the SIAO core."""
    if _siao_core:
        await _siao_core.organism.start()


async def stop_siao_core():
    """Stop the SIAO core."""
    if _siao_core:
        await _siao_core.organism.stop()
