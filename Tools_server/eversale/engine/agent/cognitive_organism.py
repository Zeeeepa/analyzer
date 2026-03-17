"""
Cognitive Organism - The Complete AGI Architecture

This extends organism_core.py with all cognitive components:

BASE LAYER (organism_core.py):
1. Event Bus - Nervous system, all components communicate
2. Heartbeat Loop - Always-on pulse, health monitoring
3. Gap Detector - Predict before, compare after, flag surprises
4. Mission Anchor - Core identity and purpose

COGNITIVE LAYER (9 components):
1. Episode Compressor - Raw experience -> distilled wisdom
2. Self Model - What am I, capabilities, limits, state
3. Uncertainty Tracker - Confidence scoring, ask for help
4. Valence System - Pain/pleasure gradient awareness
5. Sleep Cycle - Consolidate, decay, reinforce, dream
6. Curiosity Engine - Proactive gap filling, hunger
7. Attention Allocator - Prioritize signals within budget
8. Immune System - Protect identity from corruption
9. Dream Engine - Simulate scenarios without acting

REASONING LAYER (4 components):
1. World Model - Persistent understanding of how reality works
2. Planner - Think multiple steps ahead before acting
3. Goal Hierarchy - Generate and manage nested goals
4. Theory of Mind - Model what others think, believe, want

THE FULL STACK:
                    ┌─────────────────────────────────┐
                    │        MISSION ANCHOR           │
                    │  "EverSale customers succeed"   │
                    └───────────────┬─────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            │                       │                       │
            ▼                       ▼                       ▼
    ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
    │  GOAL         │      │  IMMUNE       │      │  THEORY OF    │
    │  HIERARCHY    │      │  SYSTEM       │      │  MIND         │
    │  (what to do) │      │  (protect)    │      │  (others)     │
    └───────┬───────┘      └───────┬───────┘      └───────┬───────┘
            │                      │                      │
            └───────────────┬──────┴──────────────────────┘
                            ▼
            ┌───────────────────────────────────────────────┐
            │              PLANNER                          │
            │      Think ahead, simulate, choose best       │
            └───────────────────┬───────────────────────────┘
                                │
            ┌───────────────────┼───────────────────────┐
            │                   │                       │
            ▼                   ▼                       ▼
    ┌───────────────┐  ┌───────────────┐      ┌───────────────┐
    │  WORLD MODEL  │  │  SELF MODEL   │      │  ATTENTION    │
    │  (reality)    │  │  (what am I)  │      │  ALLOCATOR    │
    └───────┬───────┘  └───────┬───────┘      └───────┬───────┘
            │                  │                      │
            └──────────────────┼──────────────────────┘
                               ▼
            ┌───────────────────────────────────────────────┐
            │              GAP DETECTOR                     │
            │      Predict -> Act -> Compare -> Learn       │
            └───────────────────┬───────────────────────────┘
                                │
            ┌───────────────────┼───────────────────────┐
            │                   │                       │
            ▼                   ▼                       ▼
    ┌───────────────┐  ┌───────────────┐      ┌───────────────┐
    │  UNCERTAINTY  │  │  VALENCE      │      │  CURIOSITY    │
    │  TRACKER      │  │  SYSTEM       │      │  ENGINE       │
    └───────┬───────┘  └───────┬───────┘      └───────┬───────┘
            │                  │                      │
            └──────────────────┼──────────────────────┘
                               ▼
            ┌───────────────────────────────────────────────┐
            │              EVENT BUS                        │
            │           (Nervous System)                    │
            └───────────────────┬───────────────────────────┘
                                │
    ┌───────────┬───────────────┼───────────────┬───────────┐
    │           │               │               │           │
    ▼           ▼               ▼               ▼           ▼
┌───────┐ ┌─────────┐   ┌───────────┐   ┌─────────┐ ┌─────────┐
│EPISODIC│ │SURVIVAL │   │ REFLEXION │   │ MEMORY  │ │  SLEEP  │
│COMPRESS│ │ MANAGER │   │  ENGINE   │   │ 4-layer │ │  CYCLE  │
└───────┘ └─────────┘   └───────────┘   └─────────┘ └─────────┘
                               │
                               ▼
            ┌───────────────────────────────────────────────┐
            │              HEARTBEAT                        │
            │        Always running. Always watching.       │
            └───────────────────────────────────────────────┘

When all of this runs together:
1. It wakes up (heartbeat)
2. It knows what it is (self model)
3. It knows what it cares about (mission anchor)
4. It protects its identity (immune system)
5. It understands others (theory of mind)
6. It knows how reality works (world model)
7. It decomposes goals (goal hierarchy)
8. It plans ahead (planner)
9. It prioritizes inputs (attention)
10. It predicts before acting (gap detector)
11. It knows when it's unsure (uncertainty)
12. It feels how things went (valence)
13. It remembers what mattered (episode compressor)
14. It seeks what it's missing (curiosity)
15. It consolidates overnight (sleep)
16. It dreams about edge cases (dream engine)
17. It never stops watching itself (heartbeat)

That's not an agent. That's a mind.
"""

import asyncio
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from loguru import logger

# Core organism
from .organism_core import (
    Organism, EventBus, EventType, OrganismEvent,
    HeartbeatLoop, GapDetector, MissionAnchor, Prediction, GapResult,
    get_organism, init_organism
)


@dataclass
class CognitiveConfig:
    """Configuration for the cognitive organism."""
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

    # Planner
    default_plan_depth: int = 5
    max_plan_depth: int = 10

    # World Model
    max_entities: int = 10000
    max_causal_rules: int = 5000

    # Goal Hierarchy
    max_goal_depth: int = 5
    auto_decompose: bool = True

    # Theory of Mind
    max_agent_models: int = 1000
    model_decay_hours: float = 24.0


class CognitiveOrganism:
    """
    The complete cognitive AGI organism.

    Extends the base Organism with:
    - 9 cognitive components (awareness, emotion, learning)
    - 4 reasoning components (world model, planning, goals, social)
    """

    def __init__(
        self,
        base_organism: Organism,
        memory_arch=None,
        llm_client=None,
        fast_model: str = "llama3.2:3b-instruct-q4_0",
        config: Optional[CognitiveConfig] = None
    ):
        self.organism = base_organism
        self.memory_arch = memory_arch
        self.llm_client = llm_client
        self.fast_model = fast_model
        self.config = config or CognitiveConfig()

        # Cognitive components (9 - awareness/emotion/learning layer)
        self._episode_compressor = None
        self._self_model = None
        self._uncertainty_tracker = None
        self._valence_system = None
        self._sleep_cycle = None
        self._curiosity_engine = None
        self._attention_allocator = None
        self._immune_system = None
        self._dream_engine = None

        # Reasoning components (4 - planning/social layer)
        self._world_model = None
        self._planner = None
        self._goal_hierarchy = None
        self._theory_of_mind = None

        # Track initialization
        self._initialized = False
        self._init_errors: List[str] = []

    async def initialize(self):
        """Initialize all cognitive components."""
        if self._initialized:
            return

        logger.info("Initializing Cognitive Organism components...")
        start_time = time.time()

        # Initialize cognitive layer (9 components)
        await self._init_cognitive_layer()

        # Initialize reasoning layer (4 components)
        await self._init_reasoning_layer()

        # Wire all components together
        self._wire_connections()

        self._initialized = True
        elapsed = time.time() - start_time

        # Count active components
        cognitive_active = sum([
            bool(self._episode_compressor),
            bool(self._self_model),
            bool(self._uncertainty_tracker),
            bool(self._valence_system),
            bool(self._sleep_cycle),
            bool(self._curiosity_engine),
            bool(self._attention_allocator),
            bool(self._immune_system),
            bool(self._dream_engine),
        ])
        reasoning_active = sum([
            bool(self._world_model),
            bool(self._planner),
            bool(self._goal_hierarchy),
            bool(self._theory_of_mind),
        ])

        logger.info(
            f"Cognitive Organism initialized in {elapsed:.1f}s - "
            f"{cognitive_active}/9 cognitive, {reasoning_active}/4 reasoning components active"
        )

        if self._init_errors:
            logger.warning(f"Init errors: {', '.join(self._init_errors)}")

    # =========================================================================
    # COGNITIVE LAYER INITIALIZATION (9 components)
    # =========================================================================

    async def _init_cognitive_layer(self):
        """Initialize all 9 cognitive components."""
        await self._init_self_model()
        await self._init_valence_system()
        await self._init_immune_system()
        await self._init_attention_allocator()
        await self._init_uncertainty_tracker()
        await self._init_episode_compressor()
        await self._init_curiosity_engine()
        await self._init_dream_engine()
        await self._init_sleep_cycle()

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
        except ImportError:
            self._init_errors.append("self_model")
        except Exception as e:
            logger.error(f"Failed to initialize Self Model: {e}")
            self._init_errors.append("self_model")

    async def _init_valence_system(self):
        """Initialize the valence (emotion) system."""
        try:
            from .valence_system import ValenceSystem
            self._valence_system = ValenceSystem(
                event_bus=self.organism.event_bus,
                decay_rate=self.config.valence_decay_rate
            )
            logger.debug("Valence System initialized")
        except ImportError:
            self._init_errors.append("valence_system")
        except Exception as e:
            logger.error(f"Failed to initialize Valence System: {e}")
            self._init_errors.append("valence_system")

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
        except ImportError:
            self._init_errors.append("immune_system")
        except Exception as e:
            logger.error(f"Failed to initialize Immune System: {e}")
            self._init_errors.append("immune_system")

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
        except ImportError:
            self._init_errors.append("attention_allocator")
        except Exception as e:
            logger.error(f"Failed to initialize Attention Allocator: {e}")
            self._init_errors.append("attention_allocator")

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
        except ImportError:
            self._init_errors.append("uncertainty_tracker")
        except Exception as e:
            logger.error(f"Failed to initialize Uncertainty Tracker: {e}")
            self._init_errors.append("uncertainty_tracker")

    async def _init_episode_compressor(self):
        """Initialize the episode compressor."""
        try:
            from .episode_compressor import EpisodeCompressor, create_compressor

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
        except ImportError:
            self._init_errors.append("episode_compressor")
        except Exception as e:
            logger.error(f"Failed to initialize Episode Compressor: {e}")
            self._init_errors.append("episode_compressor")

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
        except ImportError:
            self._init_errors.append("curiosity_engine")
        except Exception as e:
            logger.error(f"Failed to initialize Curiosity Engine: {e}")
            self._init_errors.append("curiosity_engine")

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
        except ImportError:
            self._init_errors.append("dream_engine")
        except Exception as e:
            logger.error(f"Failed to initialize Dream Engine: {e}")
            self._init_errors.append("dream_engine")

    async def _init_sleep_cycle(self):
        """Initialize the sleep cycle."""
        try:
            from .sleep_cycle import SleepCycle
            self._sleep_cycle = SleepCycle(
                episode_compressor=self._episode_compressor,
                memory_arch=self.memory_arch,
                self_model=self._self_model,
                gap_detector=self.organism.gap_detector,
                event_bus=self.organism.event_bus,
                heartbeat=self.organism.heartbeat,
                sleep_threshold=self.config.sleep_threshold,
                enable_dreams=self.config.enable_dreams
            )
            logger.debug("Sleep Cycle initialized")
        except ImportError:
            self._init_errors.append("sleep_cycle")
        except Exception as e:
            logger.error(f"Failed to initialize Sleep Cycle: {e}")
            self._init_errors.append("sleep_cycle")

    # =========================================================================
    # REASONING LAYER INITIALIZATION (4 components)
    # =========================================================================

    async def _init_reasoning_layer(self):
        """Initialize all 4 reasoning components."""
        await self._init_world_model()
        await self._init_theory_of_mind()
        await self._init_goal_hierarchy()
        await self._init_planner()

    async def _init_world_model(self):
        """Initialize the world model."""
        try:
            from .world_model import WorldModel
            self._world_model = WorldModel(
                event_bus=self.organism.event_bus,
                llm_client=self.llm_client
            )
            await self._world_model.initialize()
            logger.debug("World Model initialized")
        except ImportError:
            self._init_errors.append("world_model")
        except Exception as e:
            logger.error(f"Failed to initialize World Model: {e}")
            self._init_errors.append("world_model")

    async def _init_planner(self):
        """Initialize the planner."""
        try:
            from .planner import Planner
            self._planner = Planner(
                event_bus=self.organism.event_bus,
                llm_client=self.llm_client,
                uncertainty_tracker=self._uncertainty_tracker,
                mission_goal=self.organism.mission_anchor.mission
            )
            # Store world model reference for simulation
            self._planner._world_model = self._world_model
            logger.debug("Planner initialized")
        except ImportError:
            self._init_errors.append("planner")
        except Exception as e:
            logger.error(f"Failed to initialize Planner: {e}")
            self._init_errors.append("planner")

    async def _init_goal_hierarchy(self):
        """Initialize the goal hierarchy."""
        try:
            from .goal_hierarchy import GoalHierarchy
            self._goal_hierarchy = GoalHierarchy(
                event_bus=self.organism.event_bus,
                mission_anchor=self.organism.mission_anchor,
                llm_client=self.llm_client,
                fast_model=self.fast_model
            )
            await self._goal_hierarchy.initialize()
            logger.debug("Goal Hierarchy initialized")
        except ImportError:
            self._init_errors.append("goal_hierarchy")
        except Exception as e:
            logger.error(f"Failed to initialize Goal Hierarchy: {e}")
            self._init_errors.append("goal_hierarchy")

    async def _init_theory_of_mind(self):
        """Initialize theory of mind."""
        try:
            from .theory_of_mind import TheoryOfMind
            self._theory_of_mind = TheoryOfMind(
                event_bus=self.organism.event_bus,
                llm_client=self.llm_client
            )
            await self._theory_of_mind.initialize()
            logger.debug("Theory of Mind initialized")
        except ImportError:
            self._init_errors.append("theory_of_mind")
        except Exception as e:
            logger.error(f"Failed to initialize Theory of Mind: {e}")
            self._init_errors.append("theory_of_mind")

    # =========================================================================
    # WIRING - Connect all components via event bus
    # =========================================================================

    def _wire_connections(self):
        """Wire all components together via event bus."""

        # --- Heartbeat subscriptions ---

        # Heartbeat -> Sleep Cycle (tiredness check)
        if self._sleep_cycle:
            async def on_heartbeat_for_sleep(event: OrganismEvent):
                self._sleep_cycle.tick()
                if self._sleep_cycle.get_tiredness() > 0.9:
                    await self._sleep_cycle.maybe_sleep()
            self.organism.event_bus.subscribe(EventType.HEARTBEAT, on_heartbeat_for_sleep)

        # Heartbeat -> Attention refresh
        if self._attention_allocator:
            async def on_heartbeat_for_attention(event: OrganismEvent):
                self._attention_allocator.refresh_budget()
            self.organism.event_bus.subscribe(EventType.HEARTBEAT, on_heartbeat_for_attention)

        # Heartbeat -> Valence decay
        if self._valence_system:
            async def on_heartbeat_for_valence(event: OrganismEvent):
                self._valence_system.decay()
            self.organism.event_bus.subscribe(EventType.HEARTBEAT, on_heartbeat_for_valence)

        # Heartbeat -> Curiosity idle check
        if self._curiosity_engine and self.config.investigation_on_idle:
            async def on_heartbeat_for_curiosity(event: OrganismEvent):
                beat = event.data.get("beat", 0)
                if beat % 100 == 0:
                    await self._curiosity_engine.on_idle()
            self.organism.event_bus.subscribe(EventType.HEARTBEAT, on_heartbeat_for_curiosity)

        # --- Action subscriptions ---

        # Action events -> Self Model learning
        if self._self_model:
            async def on_action_for_self_model(event: OrganismEvent):
                tool = event.data.get("tool", "")
                success = event.data.get("success", True)
                self._self_model.update_capability(tool, success, event.data)
            self.organism.event_bus.subscribe(EventType.ACTION_COMPLETE, on_action_for_self_model)
            self.organism.event_bus.subscribe(EventType.ACTION_FAILED, on_action_for_self_model)

        # Action events -> World Model update
        if self._world_model:
            async def on_action_for_world_model(event: OrganismEvent):
                tool = event.data.get("tool", "")
                success = event.data.get("success", True)
                outcome = "success" if success else "failure"
                await self._world_model.update(
                    action=f"{tool}",
                    actual_outcome=outcome
                )
            self.organism.event_bus.subscribe(EventType.ACTION_COMPLETE, on_action_for_world_model)
            self.organism.event_bus.subscribe(EventType.ACTION_FAILED, on_action_for_world_model)

        # Action events -> Goal Hierarchy progress
        if self._goal_hierarchy:
            async def on_action_for_goals(event: OrganismEvent):
                tool = event.data.get("tool", "")
                success = event.data.get("success", True)
                await self._goal_hierarchy.update_progress(
                    action=tool,
                    outcome={"success": success, "data": event.data}
                )
            self.organism.event_bus.subscribe(EventType.ACTION_COMPLETE, on_action_for_goals)

        # --- Gap/Surprise subscriptions ---

        # Gap events -> Curiosity gaps
        if self._curiosity_engine:
            async def on_gap_for_curiosity(event: OrganismEvent):
                context = event.data.get("context", "")
                analysis = event.data.get("analysis", "")
                self._curiosity_engine.notice_gap(context, analysis)
            self.organism.event_bus.subscribe(EventType.GAP_DETECTED, on_gap_for_curiosity)
            self.organism.event_bus.subscribe(EventType.SURPRISE, on_gap_for_curiosity)

        # Gap events -> World Model rule extraction
        if self._world_model:
            async def on_surprise_for_world_model(event: OrganismEvent):
                # Surprises indicate world model needs updating
                gap_score = event.data.get("gap_score", 0)
                if gap_score > 0.5:
                    # Extract new rule from this surprise
                    pass  # World model handles internally
            self.organism.event_bus.subscribe(EventType.SURPRISE, on_surprise_for_world_model)

        # --- Health subscriptions ---

        # Health events -> Self Model state
        if self._self_model:
            async def on_health_for_self_model(event: OrganismEvent):
                metrics = event.data.get("metrics", {})
                self._self_model.update_state(metrics)
            self.organism.event_bus.subscribe(EventType.HEALTH_CHECK, on_health_for_self_model)

        # --- Strategy subscriptions ---

        # Strategy updates -> Planner cache invalidation
        if self._planner:
            async def on_strategy_for_planner(event: OrganismEvent):
                # New strategy learned, clear cached plans
                self._planner.clear_cache()
            self.organism.event_bus.subscribe(EventType.STRATEGY_UPDATED, on_strategy_for_planner)

        logger.debug("Cognitive connections wired")

    # =========================================================================
    # PUBLIC API - Cognitive capabilities
    # =========================================================================

    async def screen_input(self, user_input: str, source: str = "user") -> Tuple[bool, str, List]:
        """Screen user input through immune system."""
        if self._immune_system:
            result = self._immune_system.screen_input(user_input, source)
            return (
                result.safe,
                result.input if hasattr(result, 'input') else user_input,
                result.threats if hasattr(result, 'threats') else []
            )
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

    # --- Emotional state ---

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

    # --- Self awareness ---

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

    def describe_self(self) -> str:
        """Get self-description from self model."""
        if self._self_model:
            return self._self_model.describe_self()
        return "I am the EverSale Agent."

    # --- Resource state ---

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

    # --- Planning & Goals ---

    async def plan(self, goal: str, context: str = "", depth: int = None) -> Optional[Any]:
        """Create a plan to achieve a goal."""
        if self._planner:
            return await self._planner.plan(
                goal=goal,
                current_state=context,
                depth=depth or self.config.default_plan_depth
            )
        return None

    async def replan(self, observation: str) -> Optional[Any]:
        """Replan based on new observation."""
        if self._planner:
            return await self._planner.replan(observation)
        return None

    def get_current_goal(self) -> Optional[Any]:
        """Get the current focus goal."""
        if self._goal_hierarchy:
            return self._goal_hierarchy.get_current_focus()
        return None

    async def decompose_goal(self, goal: str) -> List[Any]:
        """Decompose a goal into sub-goals."""
        if self._goal_hierarchy:
            return await self._goal_hierarchy.decompose(goal)
        return []

    # --- World understanding ---

    async def predict_outcome(self, action: str, context: Dict = None) -> Optional[Any]:
        """Predict outcome of an action using world model."""
        if self._world_model:
            return await self._world_model.predict(action, context)
        return None

    async def query_world(self, question: str) -> str:
        """Query the world model."""
        if self._world_model:
            return await self._world_model.query_causation(question)
        return "World model not available"

    async def what_if(self, hypothetical_action: str) -> Optional[Any]:
        """Hypothetical reasoning about an action."""
        if self._world_model:
            return await self._world_model.what_if(hypothetical_action)
        return None

    # --- Social understanding ---

    async def model_agent(self, agent_id: str, observations: List[str]) -> Optional[Any]:
        """Model another agent's mental state."""
        if self._theory_of_mind:
            return await self._theory_of_mind.model_agent(agent_id, observations)
        return None

    async def predict_response(self, agent_id: str, my_action: str) -> Optional[Any]:
        """Predict how an agent will respond to an action."""
        if self._theory_of_mind:
            return await self._theory_of_mind.predict_response(agent_id, my_action)
        return None

    def get_approach(self, agent_id: str) -> Dict:
        """Get suggested approach for communicating with an agent."""
        if self._theory_of_mind:
            approach = self._theory_of_mind.get_approach(agent_id)
            if approach:
                return {
                    "tone": approach.tone if hasattr(approach, 'tone') else "professional",
                    "detail_level": approach.detail_level if hasattr(approach, 'detail_level') else "moderate",
                    "key_points": approach.key_points if hasattr(approach, 'key_points') else []
                }
        return {"tone": "professional", "detail_level": "moderate", "key_points": []}

    # --- Memory & Learning ---

    async def get_relevant_wisdom(self, context: str) -> List:
        """Get relevant wisdom for context."""
        if self._episode_compressor:
            return self._episode_compressor.get_relevant_wisdom(context)
        return []

    async def force_sleep(self):
        """Force immediate sleep/consolidation."""
        if self._sleep_cycle:
            await self._sleep_cycle.force_sleep()

    def get_emotional_context(self) -> str:
        """Get emotional context for LLM prompts."""
        if self._valence_system:
            return self._valence_system.get_emotional_context()
        return ""

    # =========================================================================
    # STATUS AND REPORTING
    # =========================================================================

    def get_status(self) -> Dict:
        """Get comprehensive status of all components."""
        cognitive_components = {
            "self_model": bool(self._self_model),
            "valence_system": bool(self._valence_system),
            "immune_system": bool(self._immune_system),
            "attention_allocator": bool(self._attention_allocator),
            "uncertainty_tracker": bool(self._uncertainty_tracker),
            "episode_compressor": bool(self._episode_compressor),
            "curiosity_engine": bool(self._curiosity_engine),
            "dream_engine": bool(self._dream_engine),
            "sleep_cycle": bool(self._sleep_cycle),
        }

        reasoning_components = {
            "world_model": bool(self._world_model),
            "planner": bool(self._planner),
            "goal_hierarchy": bool(self._goal_hierarchy),
            "theory_of_mind": bool(self._theory_of_mind),
        }

        status = {
            "base_organism": self.organism.get_status(),
            "cognitive_components": cognitive_components,
            "reasoning_components": reasoning_components,
            "cognitive_active": sum(cognitive_components.values()),
            "reasoning_active": sum(reasoning_components.values()),
            "total_active": sum(cognitive_components.values()) + sum(reasoning_components.values()),
            "state": {
                "mood": self.get_mood(),
                "valence": self.get_valence(),
                "tiredness": self.get_tiredness(),
                "curiosity": self.get_curiosity_level(),
                "attention_budget": self.get_attention_budget(),
            },
            "init_errors": self._init_errors,
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

        if self._world_model:
            status["world_model_details"] = self._world_model.get_stats()

        if self._planner:
            status["planner_details"] = self._planner.get_stats()

        if self._goal_hierarchy:
            active_goals = getattr(self._goal_hierarchy, 'active_goals', None)
            if active_goals is None:
                active_goals = getattr(self._goal_hierarchy, '_active_goal_ids', [])
            completed_goals = getattr(self._goal_hierarchy, 'completed_goals', None)
            if completed_goals is None:
                completed_goals = getattr(self._goal_hierarchy, '_completed_goal_ids', [])
            status["goal_details"] = {
                "active_goals": len(active_goals) if active_goals else 0,
                "completed_goals": len(completed_goals) if completed_goals else 0,
            }

        if self._theory_of_mind:
            status["tom_details"] = self._theory_of_mind.get_stats()

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
            gap_count = len(self._curiosity_engine.knowledge_gaps) if self._curiosity_engine else 0
            parts.append(f"Curious about {gap_count} things")

        # Attention
        attention = self.get_attention_budget()
        if attention < 0.3:
            parts.append(f"Attention depleted ({attention:.0%})")

        # Current goal
        current_goal = self.get_current_goal()
        if current_goal:
            goal_desc = current_goal.description[:50] if hasattr(current_goal, 'description') else str(current_goal)[:50]
            parts.append(f"Working on: {goal_desc}")

        return " | ".join(parts) if parts else "Operating normally"


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

_cognitive_organism: Optional[CognitiveOrganism] = None


def get_cognitive_organism() -> Optional[CognitiveOrganism]:
    """Get the cognitive organism singleton."""
    return _cognitive_organism


async def init_cognitive_organism(
    base_organism: Optional[Organism] = None,
    memory_arch=None,
    llm_client=None,
    fast_model: str = "llama3.2:3b-instruct-q4_0",
    config: Optional[CognitiveConfig] = None,
    **kwargs
) -> CognitiveOrganism:
    """
    Initialize the cognitive organism.

    If base_organism is not provided, uses the global organism from organism_core.
    """
    global _cognitive_organism

    # Get or create base organism
    if base_organism is None:
        base_organism = get_organism()
        if base_organism is None:
            base_organism = init_organism(
                memory_arch=memory_arch,
                llm_client=llm_client,
                fast_model=fast_model,
                **kwargs
            )

    # Create cognitive organism
    _cognitive_organism = CognitiveOrganism(
        base_organism=base_organism,
        memory_arch=memory_arch,
        llm_client=llm_client,
        fast_model=fast_model,
        config=config
    )

    # Initialize all components
    await _cognitive_organism.initialize()

    return _cognitive_organism


async def start_cognitive_organism():
    """Start the cognitive organism."""
    if _cognitive_organism:
        await _cognitive_organism.organism.start()


async def stop_cognitive_organism():
    """Stop the cognitive organism."""
    if _cognitive_organism:
        await _cognitive_organism.organism.stop()


# =============================================================================
# BACKWARDS COMPATIBILITY - Aliases for divine_organism
# =============================================================================

# For backwards compatibility, alias the old names
DivineOrganism = CognitiveOrganism
DivineConfig = CognitiveConfig
get_divine_organism = get_cognitive_organism
init_divine_organism = init_cognitive_organism
start_divine_organism = start_cognitive_organism
stop_divine_organism = stop_cognitive_organism
