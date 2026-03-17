#!/usr/bin/env python3
"""
World Model - Persistent Understanding of How Reality Works

This is the agent's CAUSAL MODEL of reality - a learned understanding of:
- What entities exist (customers, tools, concepts, relationships)
- How things interact ("X causes Y with probability P")
- Current state of the world
- Predictions about future outcomes
- Learning from experience

The World Model transforms the agent from reactive to predictive:
- BEFORE acting: "If I do X, Y will probably happen"
- AFTER acting: "Y happened, update my causal understanding"
- WHEN stuck: "Why did unexpected Z happen? What's the causal chain?"
- WHEN curious: "What would happen if I tried W?"

Integration with Organism:
- Subscribes to: ACTION_COMPLETE, GAP_DETECTED, SURPRISE events
- Feeds to: Gap detector (for predictions), Curiosity engine (for hypotheticals)
- Updated by: Episode compressor (causal rules from patterns)
- Queried by: Brain (before actions), Reflexion (after failures)

Visual Grounding (Optional):
- Accepts optional visual_model parameter (VisualWorldModel instance)
- Provides capture_visual_state(), verify_visual_state(), get_visual_diff() methods
- Graceful fallback if visual model not configured (returns None/False)
- Visual stats included in get_stats() when available

Key Insight: A world model is NOT a knowledge base. It's a CAUSAL ENGINE
that understands WHY things happen and predicts WHAT WILL happen.

Architecture:
1. Entity Graph: Nodes (customers, tools, concepts) + Edges (relationships)
2. Causal Rules: "If context C, then action A → outcome O with probability P"
3. State Tracker: Current known state of all entities
4. Prediction Engine: Use rules to predict action outcomes
5. Update Engine: Learn from reality, strengthen/weaken rules
6. Query Engine: Answer "What?", "Why?", "What if?"
7. Visual Grounding (Optional): Delegate to VisualWorldModel for visual perception

Performance Targets:
- <50ms prediction time
- 80%+ prediction accuracy after 100 episodes
- 90%+ causal rule confidence after validation
- <5MB memory footprint for 1000 entities
"""

import asyncio
import hashlib
import json
import time
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict, deque
from loguru import logger
import math

# Import existing components
try:
    from .organism_core import EventBus, EventType, OrganismEvent
    from .llm_client import LLMClient, LLMResponse
    INTEGRATION_AVAILABLE = True
except ImportError:
    INTEGRATION_AVAILABLE = False
    logger.warning("Integration modules not available - running in standalone mode")


# =============================================================================
# CONFIGURATION
# =============================================================================

MEMORY_DIR = Path("memory")
MEMORY_DIR.mkdir(exist_ok=True)

WORLD_MODEL_FILE = MEMORY_DIR / "world_model.json"
CAUSAL_RULES_FILE = MEMORY_DIR / "causal_rules.json"
ENTITY_GRAPH_FILE = MEMORY_DIR / "entity_graph.json"

# Learning parameters
MIN_OBSERVATIONS_FOR_RULE = 3  # Need 3+ observations to create a rule
RULE_CONFIDENCE_THRESHOLD = 0.6  # Only use rules with 60%+ confidence
PREDICTION_DECAY_HOURS = 24  # Predictions older than 24h decay
ENTITY_STALENESS_HOURS = 72  # Entities older than 3 days are stale

# Performance targets
TARGET_PREDICTION_TIME_MS = 50
TARGET_PREDICTION_ACCURACY = 0.80
TARGET_RULE_CONFIDENCE = 0.90


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class EntityType(Enum):
    """Types of entities in the world model."""
    CUSTOMER = "customer"           # Users, clients
    TOOL = "tool"                  # APIs, services, platforms
    CONCEPT = "concept"            # Abstract ideas, patterns
    TASK = "task"                  # Work items, goals
    RESOURCE = "resource"          # Files, data, assets
    ENVIRONMENT = "environment"    # System state, context
    UNKNOWN = "unknown"            # Not yet classified


class RelationType(Enum):
    """Types of relationships between entities."""
    OWNS = "owns"                  # Customer owns resource
    USES = "uses"                  # Task uses tool
    DEPENDS_ON = "depends_on"      # Tool depends on another
    AFFECTS = "affects"            # Action affects entity
    CAUSED_BY = "caused_by"        # Event caused by action
    SIMILAR_TO = "similar_to"      # Entities are similar
    PART_OF = "part_of"           # Component relationship
    CONTRADICTS = "contradicts"    # Conflicting information


class CausalRuleType(Enum):
    """Types of causal rules."""
    DIRECT = "direct"              # A directly causes B
    CONDITIONAL = "conditional"    # If C, then A causes B
    PROBABILISTIC = "probabilistic"  # A causes B with probability P
    TEMPORAL = "temporal"          # A causes B after time T
    PREVENTIVE = "preventive"      # A prevents B


@dataclass
class Entity:
    """
    An entity in the world - anything the agent knows about.

    Entities are nodes in the knowledge graph. They have:
    - Identity (what it is)
    - State (current properties)
    - History (how it's changed)
    - Relationships (how it connects to others)
    """
    entity_id: str
    entity_type: EntityType
    name: str
    description: str

    # State tracking
    properties: Dict[str, Any] = field(default_factory=dict)
    state_history: List[Dict[str, Any]] = field(default_factory=list)
    last_observed: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

    # Confidence and validation
    confidence: float = 0.5  # How confident are we this entity exists?
    observations: int = 0    # How many times have we observed it?

    # Metadata
    created_at: float = field(default_factory=time.time)
    tags: List[str] = field(default_factory=list)
    source: str = "unknown"  # How did we learn about this?

    def is_stale(self) -> bool:
        """Check if entity information is stale."""
        age_hours = (time.time() - self.last_observed) / 3600
        return age_hours > ENTITY_STALENESS_HOURS

    def update_state(self, new_properties: Dict[str, Any]):
        """Update entity state and track history."""
        # Save old state to history
        if self.properties:
            self.state_history.append({
                'timestamp': time.time(),
                'state': self.properties.copy()
            })

        # Update properties
        self.properties.update(new_properties)
        self.last_updated = time.time()
        self.last_observed = time.time()
        self.observations += 1

        # Increase confidence with observations (logarithmic)
        self.confidence = min(0.95, 0.5 + 0.1 * (self.observations ** 0.5))


@dataclass
class Relationship:
    """A relationship between two entities."""
    relation_id: str
    source_entity: str  # Entity ID
    target_entity: str  # Entity ID
    relation_type: RelationType

    # Strength and confidence
    strength: float = 0.5  # How strong is this relationship?
    confidence: float = 0.5  # How confident are we it exists?

    # Evidence
    observations: int = 0
    last_observed: float = field(default_factory=time.time)

    # Metadata
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class CausalRule:
    """
    A causal rule: "If context C, then action A → outcome O with probability P"

    This is the core of predictive ability. Rules are learned from experience
    and refined over time.
    """
    rule_id: str
    rule_type: CausalRuleType

    # The rule: action → outcome
    action_pattern: str         # What action triggers this?
    outcome_pattern: str        # What outcome is expected?
    context_conditions: Dict[str, Any] = field(default_factory=dict)  # When does this apply?

    # Probabilistic tracking
    probability: float = 0.5    # P(outcome | action, context)
    confidence: float = 0.5     # How confident are we in this probability?

    # Evidence
    observations: int = 0       # Total times we've seen this scenario
    successes: int = 0         # Times outcome matched prediction
    failures: int = 0          # Times outcome didn't match

    # Temporal aspects
    typical_delay_seconds: Optional[float] = None  # How long until outcome?

    # Metadata
    created_at: float = field(default_factory=time.time)
    last_validated: float = field(default_factory=time.time)
    last_invalidated: Optional[float] = None

    # Source tracking
    learned_from_episodes: List[str] = field(default_factory=list)

    def update_from_observation(self, outcome_matched: bool):
        """Update rule based on new observation."""
        self.observations += 1
        if outcome_matched:
            self.successes += 1
        else:
            self.failures += 1
            self.last_invalidated = time.time()

        # Update probability
        if self.observations > 0:
            self.probability = self.successes / self.observations

        # Update confidence (increases with observations, but failures reduce it)
        if self.observations >= MIN_OBSERVATIONS_FOR_RULE:
            # Confidence based on consistency
            consistency = abs(2 * self.probability - 1)  # 0 if p=0.5, 1 if p=0 or p=1
            observation_confidence = min(0.95, self.observations / 20)
            self.confidence = consistency * observation_confidence
        else:
            self.confidence = 0.3  # Low confidence until enough observations

        self.last_validated = time.time()

    def is_reliable(self) -> bool:
        """Check if this rule is reliable enough to use."""
        return (
            self.confidence >= RULE_CONFIDENCE_THRESHOLD and
            self.observations >= MIN_OBSERVATIONS_FOR_RULE
        )


@dataclass
class Prediction:
    """A prediction about what will happen."""
    prediction_id: str
    action: str
    predicted_outcome: str

    # Context
    context: Dict[str, Any] = field(default_factory=dict)

    # Confidence
    probability: float = 0.5
    confidence: float = 0.5

    # Source
    based_on_rules: List[str] = field(default_factory=list)  # Rule IDs
    reasoning: str = ""

    # Validation
    actual_outcome: Optional[str] = None
    outcome_matched: Optional[bool] = None

    # Timing
    created_at: float = field(default_factory=time.time)
    validated_at: Optional[float] = None


@dataclass
class CausalChain:
    """A chain of causation: A → B → C → D"""
    chain_id: str
    steps: List[Tuple[str, str]]  # [(cause, effect), ...]
    confidence: float = 0.5
    explanation: str = ""


# =============================================================================
# ADVANCED CAUSAL REASONING - Temporal, Hidden, Bayesian, Multi-Agent
# =============================================================================

@dataclass
class TemporalCausalRule:
    """A causal rule with time delay."""
    cause: str
    effect: str
    probability: float
    time_delay_seconds: float  # Expected delay between cause and effect
    time_variance: float       # Standard deviation of delay
    observations: int = 0

    def expected_effect_time(self, cause_time: float) -> Tuple[float, float]:
        """Return (expected_time, uncertainty) for when effect will occur."""
        return (
            cause_time + self.time_delay_seconds,
            self.time_variance
        )


class TemporalCausalGraph:
    """Tracks time-delayed causal relationships."""

    def __init__(self):
        self.temporal_rules: Dict[str, List[TemporalCausalRule]] = defaultdict(list)
        self.pending_effects: List[Dict] = []  # Effects we're waiting for
        self.observed_sequences: List[Tuple] = []  # (cause, effect, delay)

    def add_temporal_rule(
        self,
        cause: str,
        effect: str,
        probability: float,
        delay_seconds: float,
        variance: float = 1.0
    ):
        """Add a time-delayed causal rule."""
        rule = TemporalCausalRule(
            cause=cause,
            effect=effect,
            probability=probability,
            time_delay_seconds=delay_seconds,
            time_variance=variance
        )
        self.temporal_rules[cause].append(rule)

    def predict_with_timing(
        self,
        cause: str,
        cause_time: float
    ) -> List[Dict]:
        """Predict effects and WHEN they will occur."""
        predictions = []
        for rule in self.temporal_rules.get(cause, []):
            expected_time, uncertainty = rule.expected_effect_time(cause_time)
            predictions.append({
                "effect": rule.effect,
                "probability": rule.probability,
                "expected_time": expected_time,
                "time_window": (
                    expected_time - 2 * uncertainty,
                    expected_time + 2 * uncertainty
                )
            })
        return predictions

    def observe_sequence(self, cause: str, effect: str, delay: float):
        """Learn from observed cause-effect sequences."""
        self.observed_sequences.append((cause, effect, delay))

        # Update existing rule or create new one
        for rule in self.temporal_rules.get(cause, []):
            if rule.effect == effect:
                # Update running average
                n = rule.observations
                rule.time_delay_seconds = (
                    (rule.time_delay_seconds * n + delay) / (n + 1)
                )
                rule.observations += 1
                return

        # New rule discovered
        self.add_temporal_rule(cause, effect, 0.5, delay)


@dataclass
class HiddenVariable:
    """A latent/unobserved causal variable."""
    name: str
    inferred_from: List[str]  # Observable effects that suggest this variable
    probability: float        # Confidence it exists
    hypothesized_effects: List[str]
    evidence_count: int = 0


class HiddenVariableDetector:
    """Infers existence of unobserved causal variables."""

    def __init__(self):
        self.hidden_variables: Dict[str, HiddenVariable] = {}
        self.correlation_matrix: Dict[Tuple, float] = {}  # (A, B) -> correlation
        self.unexplained_effects: List[str] = []

    def record_correlation(self, var_a: str, var_b: str, correlation: float):
        """Record correlation between two observed variables."""
        self.correlation_matrix[(var_a, var_b)] = correlation
        self.correlation_matrix[(var_b, var_a)] = correlation

    def detect_hidden_cause(
        self,
        effects: List[str],
        threshold: float = 0.7
    ) -> Optional[HiddenVariable]:
        """
        Detect if multiple correlated effects suggest a hidden common cause.

        If A and B are correlated but neither causes the other,
        there may be a hidden variable C causing both.
        """
        # Check if effects are correlated
        if len(effects) < 2:
            return None

        avg_correlation = 0
        count = 0
        for i, a in enumerate(effects):
            for b in effects[i+1:]:
                corr = self.correlation_matrix.get((a, b), 0)
                avg_correlation += abs(corr)
                count += 1

        if count > 0:
            avg_correlation /= count

        if avg_correlation >= threshold:
            # Likely a hidden common cause
            hidden_name = f"hidden_cause_of_{'_'.join(effects[:2])}"
            hidden = HiddenVariable(
                name=hidden_name,
                inferred_from=effects,
                probability=avg_correlation,
                hypothesized_effects=effects
            )
            self.hidden_variables[hidden_name] = hidden
            return hidden

        return None

    def explain_unexplained(self, effect: str) -> Optional[str]:
        """Try to explain an effect with no known cause."""
        self.unexplained_effects.append(effect)

        # Check if this effect correlates with other unexplained effects
        if len(self.unexplained_effects) >= 3:
            recent = self.unexplained_effects[-5:]
            hidden = self.detect_hidden_cause(recent)
            if hidden:
                return f"Possible hidden cause: {hidden.name}"

        return None


@dataclass
class BayesianCausalNode:
    """A node in a Bayesian causal network."""
    name: str
    prior: float              # P(node)
    parents: List[str]        # Causal parents
    cpt: Dict[Tuple, float]   # Conditional probability table: P(node | parents)


class BayesianCausalNetwork:
    """Simple Bayesian network for causal reasoning with uncertainty."""

    def __init__(self):
        self.nodes: Dict[str, BayesianCausalNode] = {}
        self.evidence: Dict[str, bool] = {}  # Observed values

    def add_node(
        self,
        name: str,
        prior: float = 0.5,
        parents: Optional[List[str]] = None,
        cpt: Optional[Dict[Tuple, float]] = None
    ):
        """Add a node to the network."""
        self.nodes[name] = BayesianCausalNode(
            name=name,
            prior=prior,
            parents=parents or [],
            cpt=cpt or {}
        )

    def set_evidence(self, node: str, value: bool):
        """Set observed evidence."""
        self.evidence[node] = value

    def query(self, node: str) -> Tuple[float, float]:
        """
        Query probability of a node given evidence.
        Returns (probability, confidence_interval).
        """
        if node in self.evidence:
            return (1.0 if self.evidence[node] else 0.0, 0.0)

        if node not in self.nodes:
            return (0.5, 0.5)  # Unknown node

        n = self.nodes[node]

        # Simple inference (not full belief propagation)
        if not n.parents:
            return (n.prior, 0.1)

        # Check parent evidence
        parent_values = []
        confidence = 1.0
        for parent in n.parents:
            if parent in self.evidence:
                parent_values.append(self.evidence[parent])
            else:
                # Unknown parent, use prior
                parent_prob, conf = self.query(parent)
                parent_values.append(parent_prob > 0.5)
                confidence *= conf

        # Look up in CPT
        key = tuple(parent_values)
        prob = n.cpt.get(key, n.prior)

        return (prob, 0.2 / confidence)

    def do_intervention(self, node: str, value: bool) -> Dict[str, float]:
        """
        Perform do-calculus intervention: do(node=value)
        Returns posterior probabilities of all nodes.
        """
        # Save original evidence
        original_evidence = self.evidence.copy()

        # Set intervention (breaks incoming arrows)
        self.evidence[node] = value

        # Query all other nodes
        results = {}
        for other in self.nodes:
            if other != node:
                prob, _ = self.query(other)
                results[other] = prob

        # Restore original evidence
        self.evidence = original_evidence

        return results

    def counterfactual(
        self,
        observation: Dict[str, bool],
        intervention: Dict[str, bool],
        query_node: str
    ) -> float:
        """
        Answer counterfactual: "If we had done X instead, what would Y have been?"

        Given: observation happened
        Question: If we had intervened with intervention, what would query_node be?
        """
        # Set observed evidence
        for node, value in observation.items():
            self.evidence[node] = value

        # Perform intervention
        for node, value in intervention.items():
            self.evidence[node] = value

        # Query result
        prob, _ = self.query(query_node)

        # Clear evidence
        self.evidence = {}

        return prob


@dataclass
class AgentBeliefModel:
    """Model of another agent's causal beliefs."""
    agent_id: str
    beliefs: Dict[str, float]    # What they believe about the world
    goals: List[str]             # What they want
    capabilities: List[str]      # What they can do
    predicted_actions: List[str] # What we predict they'll do


class MultiAgentCausalReasoner:
    """Reason about causality involving multiple agents."""

    def __init__(self, theory_of_mind: Optional[Any] = None):
        self.theory_of_mind = theory_of_mind
        self.agent_models: Dict[str, AgentBeliefModel] = {}
        self.interaction_history: List[Dict] = []

    def model_agent(
        self,
        agent_id: str,
        beliefs: Optional[Dict[str, float]] = None,
        goals: Optional[List[str]] = None,
        capabilities: Optional[List[str]] = None
    ):
        """Create or update model of another agent."""
        self.agent_models[agent_id] = AgentBeliefModel(
            agent_id=agent_id,
            beliefs=beliefs or {},
            goals=goals or [],
            capabilities=capabilities or [],
            predicted_actions=[]
        )

    def predict_agent_action(
        self,
        agent_id: str,
        context: Dict
    ) -> List[str]:
        """Predict what another agent will do based on their model."""
        if agent_id not in self.agent_models:
            return []

        model = self.agent_models[agent_id]
        predictions = []

        # Simple prediction: agent will act toward their goals using capabilities
        for goal in model.goals:
            for capability in model.capabilities:
                if self._capability_helps_goal(capability, goal, context):
                    predictions.append(f"{agent_id} will {capability} to achieve {goal}")

        model.predicted_actions = predictions
        return predictions

    def _capability_helps_goal(
        self,
        capability: str,
        goal: str,
        context: Dict
    ) -> bool:
        """Check if capability helps achieve goal (simplified)."""
        # Simple keyword matching
        cap_words = set(capability.lower().split())
        goal_words = set(goal.lower().split())
        return len(cap_words & goal_words) > 0

    def explain_agent_action(
        self,
        agent_id: str,
        action: str
    ) -> str:
        """Explain WHY an agent took an action."""
        if agent_id not in self.agent_models:
            return f"Unknown agent {agent_id}"

        model = self.agent_models[agent_id]

        # Find goal that action serves
        for goal in model.goals:
            if any(word in action.lower() for word in goal.lower().split()):
                return f"{agent_id} did '{action}' because they want '{goal}'"

        return f"{agent_id} did '{action}' for unknown reasons"

    def record_interaction(
        self,
        agent_id: str,
        action: str,
        outcome: str
    ):
        """Record an interaction for learning."""
        self.interaction_history.append({
            "agent": agent_id,
            "action": action,
            "outcome": outcome,
            "time": time.time()
        })

        # Update agent model based on observed behavior
        if agent_id in self.agent_models:
            # Infer goals from actions
            model = self.agent_models[agent_id]
            if action not in model.capabilities:
                model.capabilities.append(action)


# =============================================================================
# WORLD MODEL - The Causal Engine
# =============================================================================

class WorldModel:
    """
    The agent's understanding of how reality works.

    This is the breakthrough that enables prediction and learning:
    - Before acting: Predict what will happen
    - After acting: Update causal model based on reality
    - When stuck: Explain why something happened
    - When curious: Explore hypothetical scenarios
    """

    def __init__(
        self,
        event_bus: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        config: Optional[Dict] = None,
        visual_model: Optional[Any] = None
    ):
        self.event_bus = event_bus
        self.llm_client = llm_client
        self.config = config or {}
        self.visual_model = visual_model

        # Entity graph
        self.entities: Dict[str, Entity] = {}
        self.relationships: Dict[str, Relationship] = {}

        # Causal rules
        self.causal_rules: Dict[str, CausalRule] = {}

        # Predictions tracking
        self.predictions: Dict[str, Prediction] = {}
        self.recent_predictions: deque = deque(maxlen=100)

        # Current state
        self.current_state: Dict[str, Any] = {
            'timestamp': time.time(),
            'active_tasks': [],
            'recent_events': deque(maxlen=50),
            'environment': {}
        }

        # Statistics
        self.stats = {
            'predictions_made': 0,
            'predictions_validated': 0,
            'predictions_correct': 0,
            'rules_learned': 0,
            'entities_discovered': 0,
            'relationships_discovered': 0,
        }

        # Initialization flag
        self._initialized = False

        # Log visual capabilities
        if self.visual_model:
            logger.info("WorldModel initialized with visual grounding enabled")
        else:
            logger.info("WorldModel initialized (visual grounding disabled)")

    async def initialize(self):
        """Async initialization - load from disk, subscribe to events."""
        if self._initialized:
            return

        # Load persisted state
        await self._load_from_disk()

        # Subscribe to EventBus
        if self.event_bus and INTEGRATION_AVAILABLE:
            self.event_bus.subscribe(EventType.ACTION_COMPLETE, self._on_action_complete)
            self.event_bus.subscribe(EventType.GAP_DETECTED, self._on_gap_detected)
            self.event_bus.subscribe(EventType.SURPRISE, self._on_surprise)
            self.event_bus.subscribe(EventType.LESSON_LEARNED, self._on_lesson_learned)
            logger.info("WorldModel subscribed to EventBus")

        self._initialized = True
        logger.info(f"WorldModel initialized with {len(self.entities)} entities, "
                   f"{len(self.causal_rules)} rules")

    # =========================================================================
    # PREDICTION ENGINE
    # =========================================================================

    async def predict(
        self,
        action: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Prediction:
        """
        Predict the outcome of an action given current context.

        This is the core predictive function:
        1. Find applicable causal rules
        2. Combine predictions from multiple rules
        3. Return best prediction with confidence

        Args:
            action: Description of action to take
            context: Current context (state, entities involved, etc.)

        Returns:
            Prediction with expected outcome and confidence
        """
        start_time = time.time()
        context = context or {}

        # Find applicable rules
        applicable_rules = self._find_applicable_rules(action, context)

        if not applicable_rules:
            # No rules found - make LLM-based prediction if available
            prediction = await self._llm_predict(action, context)
        else:
            # Combine predictions from rules
            prediction = self._combine_rule_predictions(action, context, applicable_rules)

        # Store prediction for later validation
        self.predictions[prediction.prediction_id] = prediction
        self.recent_predictions.append(prediction.prediction_id)
        self.stats['predictions_made'] += 1

        # Update state
        self.current_state['recent_events'].append({
            'type': 'prediction',
            'action': action,
            'predicted_outcome': prediction.predicted_outcome,
            'timestamp': time.time()
        })

        # Emit event
        if self.event_bus and INTEGRATION_AVAILABLE:
            self.event_bus.publish(OrganismEvent(
                event_type=EventType.PREDICTION_MADE,
                source="world_model",
                data={
                    'action': action,
                    'predicted_outcome': prediction.predicted_outcome,
                    'confidence': prediction.confidence,
                    'prediction_id': prediction.prediction_id
                }
            ))

        elapsed_ms = (time.time() - start_time) * 1000
        if elapsed_ms > TARGET_PREDICTION_TIME_MS:
            logger.warning(f"Prediction took {elapsed_ms:.1f}ms (target: {TARGET_PREDICTION_TIME_MS}ms)")

        return prediction

    def _find_applicable_rules(
        self,
        action: str,
        context: Dict[str, Any]
    ) -> List[CausalRule]:
        """Find causal rules that apply to this action and context."""
        applicable = []

        for rule in self.causal_rules.values():
            # Skip unreliable rules
            if not rule.is_reliable():
                continue

            # Check if action matches
            if not self._action_matches_pattern(action, rule.action_pattern):
                continue

            # Check if context matches
            if not self._context_matches(context, rule.context_conditions):
                continue

            applicable.append(rule)

        # Sort by confidence
        applicable.sort(key=lambda r: r.confidence, reverse=True)

        return applicable

    def _action_matches_pattern(self, action: str, pattern: str) -> bool:
        """Check if action matches pattern (simple substring for now)."""
        action_lower = action.lower()
        pattern_lower = pattern.lower()

        # Extract key terms
        action_terms = set(re.findall(r'\w+', action_lower))
        pattern_terms = set(re.findall(r'\w+', pattern_lower))

        # Check overlap
        overlap = len(action_terms & pattern_terms)
        return overlap >= min(2, len(pattern_terms))

    def _context_matches(
        self,
        context: Dict[str, Any],
        conditions: Dict[str, Any]
    ) -> bool:
        """Check if context matches rule conditions."""
        if not conditions:
            return True  # No conditions means always applicable

        for key, expected_value in conditions.items():
            if key not in context:
                return False

            actual_value = context[key]

            # Handle different comparison types
            if isinstance(expected_value, (int, float)):
                if actual_value != expected_value:
                    return False
            elif isinstance(expected_value, str):
                if expected_value.lower() not in str(actual_value).lower():
                    return False
            elif actual_value != expected_value:
                return False

        return True

    def _combine_rule_predictions(
        self,
        action: str,
        context: Dict[str, Any],
        rules: List[CausalRule]
    ) -> Prediction:
        """Combine predictions from multiple rules."""
        if not rules:
            return Prediction(
                prediction_id=self._generate_id("prediction"),
                action=action,
                predicted_outcome="Unknown",
                confidence=0.0,
                reasoning="No applicable rules found"
            )

        # Use highest confidence rule as primary
        primary_rule = rules[0]

        # Combine confidence from multiple rules
        total_confidence = sum(r.confidence for r in rules) / len(rules)

        # Generate prediction
        prediction = Prediction(
            prediction_id=self._generate_id("prediction"),
            action=action,
            predicted_outcome=primary_rule.outcome_pattern,
            probability=primary_rule.probability,
            confidence=total_confidence,
            context=context,
            based_on_rules=[r.rule_id for r in rules],
            reasoning=f"Based on {len(rules)} rule(s), primary: {primary_rule.action_pattern} → {primary_rule.outcome_pattern}"
        )

        return prediction

    async def _llm_predict(
        self,
        action: str,
        context: Dict[str, Any]
    ) -> Prediction:
        """Use LLM to make prediction when no rules available."""
        if not self.llm_client:
            return Prediction(
                prediction_id=self._generate_id("prediction"),
                action=action,
                predicted_outcome="Unknown",
                confidence=0.1,
                reasoning="No LLM available and no rules found"
            )

        # Build prompt
        prompt = f"""Given this action and context, predict the most likely outcome.

Action: {action}

Context:
{json.dumps(context, indent=2)}

Known entities: {list(self.entities.keys())[:20]}
Recent events: {list(self.current_state['recent_events'])[-5:]}

Respond with JSON:
{{
    "predicted_outcome": "brief description of expected outcome",
    "confidence": 0.0-1.0,
    "reasoning": "why this outcome is expected"
}}"""

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                model=self.llm_client.fast_model,
                temperature=0.1,
                max_tokens=500
            )

            if response.error:
                raise Exception(response.error)

            # Parse JSON
            result = json.loads(response.content)

            return Prediction(
                prediction_id=self._generate_id("prediction"),
                action=action,
                predicted_outcome=result['predicted_outcome'],
                confidence=float(result['confidence']) * 0.5,  # Reduce confidence for LLM predictions
                context=context,
                reasoning=result['reasoning']
            )

        except Exception as e:
            logger.error(f"LLM prediction failed: {e}")
            return Prediction(
                prediction_id=self._generate_id("prediction"),
                action=action,
                predicted_outcome="Unknown",
                confidence=0.1,
                reasoning=f"LLM prediction failed: {e}"
            )

    # =========================================================================
    # UPDATE ENGINE - Learning from Reality
    # =========================================================================

    async def update(
        self,
        action: str,
        actual_outcome: str,
        prediction_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Update world model based on what actually happened.

        This is where learning happens:
        1. Validate prediction (if made)
        2. Update causal rules
        3. Discover new rules if pattern emerges
        4. Update entity states

        Args:
            action: Action that was taken
            actual_outcome: What actually happened
            prediction_id: ID of prediction to validate (if exists)
            context: Context in which action was taken
        """
        context = context or {}

        # Validate prediction
        if prediction_id and prediction_id in self.predictions:
            prediction = self.predictions[prediction_id]
            prediction.actual_outcome = actual_outcome
            prediction.validated_at = time.time()

            # Check if prediction matched
            prediction.outcome_matched = self._outcomes_match(
                prediction.predicted_outcome,
                actual_outcome
            )

            self.stats['predictions_validated'] += 1
            if prediction.outcome_matched:
                self.stats['predictions_correct'] += 1

            # Update rules used for prediction
            for rule_id in prediction.based_on_rules:
                if rule_id in self.causal_rules:
                    self.causal_rules[rule_id].update_from_observation(
                        prediction.outcome_matched
                    )

            # Emit event if prediction was wrong (surprise!)
            if not prediction.outcome_matched and self.event_bus and INTEGRATION_AVAILABLE:
                self.event_bus.publish(OrganismEvent(
                    event_type=EventType.SURPRISE,
                    source="world_model",
                    data={
                        'action': action,
                        'predicted': prediction.predicted_outcome,
                        'actual': actual_outcome,
                        'context': context
                    }
                ))

        # Learn new rule or strengthen existing
        await self._learn_from_experience(action, actual_outcome, context)

        # Update state
        self.current_state['recent_events'].append({
            'type': 'action_outcome',
            'action': action,
            'outcome': actual_outcome,
            'timestamp': time.time()
        })

        # Persist changes
        await self._save_to_disk()

    def _outcomes_match(self, predicted: str, actual: str) -> bool:
        """Check if predicted and actual outcomes match."""
        predicted_lower = predicted.lower()
        actual_lower = actual.lower()

        # Extract key terms
        predicted_terms = set(re.findall(r'\w+', predicted_lower))
        actual_terms = set(re.findall(r'\w+', actual_lower))

        # Check overlap
        overlap = len(predicted_terms & actual_terms)
        total = len(predicted_terms | actual_terms)

        if total == 0:
            return False

        # 60%+ overlap = match
        similarity = overlap / total
        return similarity >= 0.6

    async def _learn_from_experience(
        self,
        action: str,
        outcome: str,
        context: Dict[str, Any]
    ):
        """Learn or update causal rules from this experience."""
        # Find existing rule for this pattern
        existing_rule = None
        for rule in self.causal_rules.values():
            if (self._action_matches_pattern(action, rule.action_pattern) and
                self._context_matches(context, rule.context_conditions)):
                existing_rule = rule
                break

        if existing_rule:
            # Update existing rule
            outcome_matched = self._outcomes_match(existing_rule.outcome_pattern, outcome)
            existing_rule.update_from_observation(outcome_matched)

            # If outcome didn't match, maybe create new rule
            if not outcome_matched and existing_rule.observations >= 3:
                await self._create_new_rule(action, outcome, context)
        else:
            # Create new rule
            await self._create_new_rule(action, outcome, context)

    async def _create_new_rule(
        self,
        action: str,
        outcome: str,
        context: Dict[str, Any]
    ):
        """Create a new causal rule from observation."""
        rule_id = self._generate_id("rule")

        # Extract context conditions (simple version)
        conditions = {}
        if 'environment' in context:
            conditions['environment'] = context['environment']

        rule = CausalRule(
            rule_id=rule_id,
            rule_type=CausalRuleType.PROBABILISTIC,
            action_pattern=action,
            outcome_pattern=outcome,
            context_conditions=conditions,
            observations=1,
            successes=1,
            probability=1.0,
            confidence=0.3  # Low confidence until more observations
        )

        self.causal_rules[rule_id] = rule
        self.stats['rules_learned'] += 1

        logger.info(f"Learned new rule: {action} → {outcome}")

    # =========================================================================
    # ENTITY MANAGEMENT
    # =========================================================================

    async def add_entity(
        self,
        entity_type: EntityType,
        name: str,
        description: str = "",
        properties: Optional[Dict[str, Any]] = None,
        source: str = "unknown"
    ) -> Entity:
        """Add or update an entity in the world model."""
        entity_id = self._generate_id(f"entity_{name}")

        if entity_id in self.entities:
            # Update existing entity
            entity = self.entities[entity_id]
            entity.description = description or entity.description
            if properties:
                entity.update_state(properties)
            entity.observations += 1
        else:
            # Create new entity
            entity = Entity(
                entity_id=entity_id,
                entity_type=entity_type,
                name=name,
                description=description,
                properties=properties or {},
                source=source,
                observations=1
            )
            self.entities[entity_id] = entity
            self.stats['entities_discovered'] += 1
            logger.info(f"Discovered entity: {name} ({entity_type.value})")

        return entity

    async def add_relationship(
        self,
        source_entity: str,
        target_entity: str,
        relation_type: RelationType,
        properties: Optional[Dict[str, Any]] = None
    ) -> Relationship:
        """Add or update a relationship between entities."""
        relation_id = self._generate_id(f"rel_{source_entity}_{target_entity}")

        if relation_id in self.relationships:
            # Update existing relationship
            rel = self.relationships[relation_id]
            rel.observations += 1
            rel.last_observed = time.time()
            if properties:
                rel.properties.update(properties)
        else:
            # Create new relationship
            rel = Relationship(
                relation_id=relation_id,
                source_entity=source_entity,
                target_entity=target_entity,
                relation_type=relation_type,
                properties=properties or {},
                observations=1
            )
            self.relationships[relation_id] = rel
            self.stats['relationships_discovered'] += 1

        return rel

    async def query_entity(self, entity_id: str) -> Optional[Entity]:
        """Query information about an entity."""
        return self.entities.get(entity_id)

    async def find_entities(
        self,
        entity_type: Optional[EntityType] = None,
        name_pattern: Optional[str] = None,
        has_property: Optional[str] = None
    ) -> List[Entity]:
        """Find entities matching criteria."""
        results = []

        for entity in self.entities.values():
            # Filter by type
            if entity_type and entity.entity_type != entity_type:
                continue

            # Filter by name pattern
            if name_pattern and name_pattern.lower() not in entity.name.lower():
                continue

            # Filter by property
            if has_property and has_property not in entity.properties:
                continue

            results.append(entity)

        return results

    # =========================================================================
    # QUERY ENGINE - Understanding and Explanation
    # =========================================================================

    async def query_causation(self, question: str) -> str:
        """
        Answer causal questions: "Why did X happen?"

        This uses the causal graph to explain events.
        """
        if not self.llm_client:
            return "LLM not available for causal reasoning"

        # Build context from world model
        context = {
            'recent_events': list(self.current_state['recent_events'])[-10:],
            'entities': {k: v.name for k, v in list(self.entities.items())[:50]},
            'rules_count': len(self.causal_rules),
            'predictions_accuracy': (
                self.stats['predictions_correct'] / self.stats['predictions_validated']
                if self.stats['predictions_validated'] > 0 else 0
            )
        }

        prompt = f"""Use the world model to answer this causal question.

Question: {question}

World Model Context:
{json.dumps(context, indent=2)}

Recent causal rules:
{self._format_recent_rules(5)}

Explain the causation chain that led to the event or outcome.
Be specific and reference actual entities/rules from the world model."""

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                model=self.llm_client.main_model,
                temperature=0.2,
                max_tokens=1000
            )

            return response.content if not response.error else f"Error: {response.error}"

        except Exception as e:
            logger.error(f"Causal query failed: {e}")
            return f"Error answering causal question: {e}"

    async def what_if(self, hypothetical_action: str) -> Prediction:
        """
        Answer "what if" questions: "What would happen if I did X?"

        This is counterfactual reasoning using the causal model.
        """
        # Same as predict, but explicitly marked as hypothetical
        prediction = await self.predict(hypothetical_action, context={'hypothetical': True})
        prediction.reasoning = f"Hypothetical: {prediction.reasoning}"
        return prediction

    async def find_causal_chain(
        self,
        start_event: str,
        end_event: str
    ) -> Optional[CausalChain]:
        """
        Find causal chain from start event to end event.

        This uses graph search through causal rules.
        """
        # Simplified version - use LLM to find chain
        if not self.llm_client:
            return None

        prompt = f"""Find the causal chain from start event to end event.

Start Event: {start_event}
End Event: {end_event}

Available causal rules:
{self._format_recent_rules(20)}

Return JSON with causal chain:
{{
    "steps": [
        ["event1", "event2"],
        ["event2", "event3"],
        ["event3", "end_event"]
    ],
    "confidence": 0.0-1.0,
    "explanation": "brief explanation of the chain"
}}"""

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                model=self.llm_client.fast_model,
                temperature=0.1,
                max_tokens=500
            )

            if response.error:
                raise Exception(response.error)

            result = json.loads(response.content)

            return CausalChain(
                chain_id=self._generate_id("chain"),
                steps=[(s[0], s[1]) for s in result['steps']],
                confidence=float(result['confidence']),
                explanation=result['explanation']
            )

        except Exception as e:
            logger.error(f"Causal chain search failed: {e}")
            return None

    # =========================================================================
    # EPISODE COMPRESSOR INTEGRATION
    # =========================================================================

    async def extract_rules_from_episodes(
        self,
        episodes: List[Dict[str, Any]]
    ) -> List[CausalRule]:
        """
        Extract causal rules from compressed episodes.

        This is called by the episode compressor to feed patterns into world model.
        """
        if not self.llm_client:
            logger.warning("Cannot extract rules - no LLM available")
            return []

        # Group similar episodes
        episode_groups = self._group_similar_episodes(episodes)

        new_rules = []

        for group in episode_groups:
            if len(group) < MIN_OBSERVATIONS_FOR_RULE:
                continue

            # Extract pattern from group
            rule = await self._extract_rule_from_group(group)
            if rule:
                self.causal_rules[rule.rule_id] = rule
                new_rules.append(rule)
                self.stats['rules_learned'] += 1

        logger.info(f"Extracted {len(new_rules)} causal rules from {len(episodes)} episodes")

        return new_rules

    def _group_similar_episodes(
        self,
        episodes: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """Group similar episodes together."""
        groups = []

        for episode in episodes:
            # Find matching group
            matched = False
            for group in groups:
                if self._episodes_similar(episode, group[0]):
                    group.append(episode)
                    matched = True
                    break

            if not matched:
                groups.append([episode])

        return groups

    def _episodes_similar(self, ep1: Dict[str, Any], ep2: Dict[str, Any]) -> bool:
        """Check if two episodes are similar."""
        # Simple similarity check
        action1 = ep1.get('action', '')
        action2 = ep2.get('action', '')

        terms1 = set(re.findall(r'\w+', action1.lower()))
        terms2 = set(re.findall(r'\w+', action2.lower()))

        if not terms1 or not terms2:
            return False

        overlap = len(terms1 & terms2)
        total = len(terms1 | terms2)

        return overlap / total >= 0.5

    async def _extract_rule_from_group(
        self,
        episode_group: List[Dict[str, Any]]
    ) -> Optional[CausalRule]:
        """Extract a causal rule from a group of similar episodes."""
        if not episode_group:
            return None

        # Count outcomes
        outcomes = defaultdict(int)
        for ep in episode_group:
            outcome = ep.get('outcome', 'unknown')
            outcomes[outcome] += 1

        # Most common outcome
        most_common_outcome = max(outcomes.items(), key=lambda x: x[1])
        outcome_pattern = most_common_outcome[0]
        successes = most_common_outcome[1]

        # Action pattern from first episode
        action_pattern = episode_group[0].get('action', '')

        # Create rule
        rule_id = self._generate_id("rule")
        rule = CausalRule(
            rule_id=rule_id,
            rule_type=CausalRuleType.PROBABILISTIC,
            action_pattern=action_pattern,
            outcome_pattern=outcome_pattern,
            observations=len(episode_group),
            successes=successes,
            failures=len(episode_group) - successes,
            probability=successes / len(episode_group),
            learned_from_episodes=[ep.get('episode_id', '') for ep in episode_group]
        )

        # Update confidence
        rule.update_from_observation(True)  # Update based on current stats

        return rule

    # =========================================================================
    # VISUAL GROUNDING - Optional Integration with VisualWorldModel
    # =========================================================================

    async def capture_visual_state(
        self,
        context: str,
        analyze: bool = True
    ) -> Optional[Any]:
        """
        Capture visual state using visual model if available.

        This delegates to VisualWorldModel.capture_state() if a visual model
        has been configured. Otherwise, returns None gracefully.

        Args:
            context: Context label for the visual capture (e.g., "before_action_123")
            analyze: Whether to run vision analysis (default: True)

        Returns:
            VisualState object if visual model available, None otherwise
        """
        if not self.visual_model:
            logger.debug("Visual state capture skipped - no visual model configured")
            return None

        try:
            if hasattr(self.visual_model, 'capture_state'):
                visual_state = await self.visual_model.capture_state(context, analyze)
                logger.debug(f"Visual state captured: {context}")
                return visual_state
            else:
                logger.warning("Visual model does not support capture_state()")
                return None

        except Exception as e:
            logger.error(f"Visual state capture failed: {e}")
            return None

    async def verify_visual_state(
        self,
        expected: str,
        context: str = "verification"
    ) -> bool:
        """
        Verify current visual state matches expectations using visual model.

        This delegates to VisualWorldModel.verify_state() if a visual model
        has been configured. Otherwise, returns False gracefully.

        Args:
            expected: Expected state description
            context: Context for verification (default: "verification")

        Returns:
            True if state matches expectations, False if no visual model or verification fails
        """
        if not self.visual_model:
            logger.debug("Visual state verification skipped - no visual model configured")
            return False

        try:
            if hasattr(self.visual_model, 'verify_state'):
                is_verified = await self.visual_model.verify_state(expected, context)
                logger.debug(f"Visual state verification: {is_verified}")
                return is_verified
            else:
                logger.warning("Visual model does not support verify_state()")
                return False

        except Exception as e:
            logger.error(f"Visual state verification failed: {e}")
            return False

    async def get_visual_diff(
        self,
        before_context: str,
        after_context: str
    ) -> Optional[Any]:
        """
        Get visual difference between two captured states.

        This retrieves visual states from the visual model's history and
        computes the diff. Returns None if visual model not available or
        if the requested states don't exist.

        Args:
            before_context: Context label for "before" state
            after_context: Context label for "after" state

        Returns:
            VisualDiff object if visual model available and states exist, None otherwise
        """
        if not self.visual_model:
            logger.debug("Visual diff skipped - no visual model configured")
            return None

        try:
            # Check if visual model has the necessary methods
            if not hasattr(self.visual_model, 'visual_history'):
                logger.warning("Visual model does not have visual_history")
                return None

            if not hasattr(self.visual_model, 'compute_visual_diff'):
                logger.warning("Visual model does not support compute_visual_diff()")
                return None

            # Get visual states from history
            before_states = self.visual_model.visual_history.get(before_context, [])
            after_states = self.visual_model.visual_history.get(after_context, [])

            if not before_states or not after_states:
                logger.debug(f"Visual states not found for contexts: {before_context}, {after_context}")
                return None

            # Use most recent state from each context
            before_state = before_states[-1]
            after_state = after_states[-1]

            # Compute diff
            visual_diff = await self.visual_model.compute_visual_diff(before_state, after_state)
            logger.debug(f"Visual diff computed between {before_context} and {after_context}")
            return visual_diff

        except Exception as e:
            logger.error(f"Visual diff computation failed: {e}")
            return None

    # =========================================================================
    # ADVANCED CAUSAL REASONING - Integration Methods
    # =========================================================================

    def add_temporal_reasoning(self):
        """Add temporal causal graph to WorldModel."""
        if not hasattr(self, 'temporal_graph'):
            self.temporal_graph = TemporalCausalGraph()
            logger.info("Temporal causal reasoning enabled")

    def add_hidden_variable_detection(self):
        """Add hidden variable detector to WorldModel."""
        if not hasattr(self, 'hidden_detector'):
            self.hidden_detector = HiddenVariableDetector()
            logger.info("Hidden variable detection enabled")

    def add_bayesian_network(self):
        """Add Bayesian causal network to WorldModel."""
        if not hasattr(self, 'bayesian_network'):
            self.bayesian_network = BayesianCausalNetwork()
            logger.info("Bayesian causal network enabled")

    def add_multi_agent_reasoning(self, theory_of_mind: Optional[Any] = None):
        """Add multi-agent causal reasoner to WorldModel."""
        if not hasattr(self, 'multi_agent'):
            self.multi_agent = MultiAgentCausalReasoner(theory_of_mind)
            logger.info("Multi-agent causal reasoning enabled")

    async def predict_temporal(
        self,
        cause: str,
        cause_time: Optional[float] = None
    ) -> List[Dict]:
        """
        Predict effects with timing information.

        Requires temporal_graph to be initialized via add_temporal_reasoning().

        Args:
            cause: The causal event
            cause_time: Time when cause occurred (defaults to now)

        Returns:
            List of predictions with timing windows
        """
        if not hasattr(self, 'temporal_graph'):
            logger.warning("Temporal reasoning not enabled - call add_temporal_reasoning() first")
            return []

        if cause_time is None:
            cause_time = time.time()

        return self.temporal_graph.predict_with_timing(cause, cause_time)

    async def detect_hidden_causes(
        self,
        unexplained_effects: List[str],
        threshold: float = 0.7
    ) -> Optional[HiddenVariable]:
        """
        Detect hidden causal variables from unexplained effects.

        Requires hidden_detector to be initialized via add_hidden_variable_detection().

        Args:
            unexplained_effects: List of effects with no known causes
            threshold: Correlation threshold for detection

        Returns:
            HiddenVariable if detected, None otherwise
        """
        if not hasattr(self, 'hidden_detector'):
            logger.warning("Hidden variable detection not enabled - call add_hidden_variable_detection() first")
            return None

        return self.hidden_detector.detect_hidden_cause(unexplained_effects, threshold)

    async def bayesian_query(
        self,
        query_node: str,
        evidence: Optional[Dict[str, bool]] = None
    ) -> Tuple[float, float]:
        """
        Query Bayesian network for probability given evidence.

        Requires bayesian_network to be initialized via add_bayesian_network().

        Args:
            query_node: Node to query
            evidence: Observed evidence {node: value}

        Returns:
            (probability, confidence_interval)
        """
        if not hasattr(self, 'bayesian_network'):
            logger.warning("Bayesian network not enabled - call add_bayesian_network() first")
            return (0.5, 0.5)

        # Set evidence
        if evidence:
            for node, value in evidence.items():
                self.bayesian_network.set_evidence(node, value)

        # Query
        result = self.bayesian_network.query(query_node)

        # Clear evidence
        self.bayesian_network.evidence = {}

        return result

    async def bayesian_intervention(
        self,
        intervention_node: str,
        intervention_value: bool
    ) -> Dict[str, float]:
        """
        Perform causal intervention and get posterior probabilities.

        Requires bayesian_network to be initialized via add_bayesian_network().

        Args:
            intervention_node: Node to intervene on
            intervention_value: Value to set

        Returns:
            Posterior probabilities for all other nodes
        """
        if not hasattr(self, 'bayesian_network'):
            logger.warning("Bayesian network not enabled - call add_bayesian_network() first")
            return {}

        return self.bayesian_network.do_intervention(intervention_node, intervention_value)

    async def bayesian_counterfactual(
        self,
        observation: Dict[str, bool],
        intervention: Dict[str, bool],
        query_node: str
    ) -> float:
        """
        Answer counterfactual questions using Bayesian network.

        Requires bayesian_network to be initialized via add_bayesian_network().

        Args:
            observation: What actually happened
            intervention: What we would have done instead
            query_node: What we want to know about

        Returns:
            Probability of query_node under counterfactual
        """
        if not hasattr(self, 'bayesian_network'):
            logger.warning("Bayesian network not enabled - call add_bayesian_network() first")
            return 0.5

        return self.bayesian_network.counterfactual(observation, intervention, query_node)

    async def predict_agent_behavior(
        self,
        agent_id: str,
        context: Optional[Dict] = None
    ) -> List[str]:
        """
        Predict another agent's actions based on their beliefs/goals.

        Requires multi_agent to be initialized via add_multi_agent_reasoning().

        Args:
            agent_id: ID of agent to predict
            context: Current context

        Returns:
            List of predicted actions
        """
        if not hasattr(self, 'multi_agent'):
            logger.warning("Multi-agent reasoning not enabled - call add_multi_agent_reasoning() first")
            return []

        return self.multi_agent.predict_agent_action(agent_id, context or {})

    async def explain_agent_behavior(
        self,
        agent_id: str,
        action: str
    ) -> str:
        """
        Explain why another agent took an action.

        Requires multi_agent to be initialized via add_multi_agent_reasoning().

        Args:
            agent_id: ID of agent
            action: Action they took

        Returns:
            Explanation of why they took the action
        """
        if not hasattr(self, 'multi_agent'):
            logger.warning("Multi-agent reasoning not enabled - call add_multi_agent_reasoning() first")
            return f"Unknown - multi-agent reasoning not enabled"

        return self.multi_agent.explain_agent_action(agent_id, action)

    # =========================================================================
    # EVENT HANDLERS
    # =========================================================================

    async def _on_action_complete(self, event: Any):
        """Handle ACTION_COMPLETE event."""
        data = event.data if hasattr(event, 'data') else {}

        action = data.get('action', '')
        outcome = data.get('outcome', '')
        prediction_id = data.get('prediction_id')
        context = data.get('context', {})

        if action and outcome:
            await self.update(action, outcome, prediction_id, context)

    async def _on_gap_detected(self, event: Any):
        """Handle GAP_DETECTED event."""
        data = event.data if hasattr(event, 'data') else {}

        # Gap detected means our prediction was wrong
        # This is valuable signal for learning
        topic = data.get('topic', '')
        context = data.get('context', '')

        logger.debug(f"Gap detected: {topic} - updating world model")

    async def _on_surprise(self, event: Any):
        """Handle SURPRISE event."""
        data = event.data if hasattr(event, 'data') else {}

        # Surprise = prediction failure
        # This is the most important learning signal
        action = data.get('action', '')
        predicted = data.get('predicted', '')
        actual = data.get('actual', '')

        logger.info(f"Surprise! Predicted '{predicted}' but got '{actual}' for action '{action}'")

        # Learn from this surprise
        if action and actual:
            await self._learn_from_experience(action, actual, data.get('context', {}))

    async def _on_lesson_learned(self, event: Any):
        """Handle LESSON_LEARNED event."""
        data = event.data if hasattr(event, 'data') else {}

        # Lesson learned from reflexion - can become causal rule
        lesson = data.get('lesson', '')
        context = data.get('context', {})

        # Try to extract causal relationship
        if "→" in lesson or "causes" in lesson.lower() or "leads to" in lesson.lower():
            # Parse into action→outcome
            parts = re.split(r'→|causes|leads to', lesson, maxsplit=1)
            if len(parts) == 2:
                action = parts[0].strip()
                outcome = parts[1].strip()
                await self._create_new_rule(action, outcome, context)

    # =========================================================================
    # PERSISTENCE
    # =========================================================================

    async def _save_to_disk(self):
        """Persist world model to disk."""
        try:
            # Save entities
            entities_data = {
                k: {
                    'entity_id': v.entity_id,
                    'entity_type': v.entity_type.value,
                    'name': v.name,
                    'description': v.description,
                    'properties': v.properties,
                    'last_observed': v.last_observed,
                    'confidence': v.confidence,
                    'observations': v.observations,
                    'tags': v.tags,
                    'source': v.source
                }
                for k, v in self.entities.items()
            }

            with open(ENTITY_GRAPH_FILE, 'w') as f:
                json.dump(entities_data, f, indent=2)

            # Save causal rules
            rules_data = {
                k: {
                    'rule_id': v.rule_id,
                    'rule_type': v.rule_type.value,
                    'action_pattern': v.action_pattern,
                    'outcome_pattern': v.outcome_pattern,
                    'context_conditions': v.context_conditions,
                    'probability': v.probability,
                    'confidence': v.confidence,
                    'observations': v.observations,
                    'successes': v.successes,
                    'failures': v.failures,
                    'created_at': v.created_at,
                    'last_validated': v.last_validated
                }
                for k, v in self.causal_rules.items()
            }

            with open(CAUSAL_RULES_FILE, 'w') as f:
                json.dump(rules_data, f, indent=2)

            # Save world model state
            world_model_data = {
                'current_state': {
                    'timestamp': self.current_state['timestamp'],
                    'active_tasks': self.current_state['active_tasks'],
                    'recent_events': list(self.current_state['recent_events']),
                    'environment': self.current_state['environment']
                },
                'stats': self.stats,
                'last_saved': time.time()
            }

            with open(WORLD_MODEL_FILE, 'w') as f:
                json.dump(world_model_data, f, indent=2)

            logger.debug("World model saved to disk")

        except Exception as e:
            logger.error(f"Failed to save world model: {e}")

    async def _load_from_disk(self):
        """Load world model from disk."""
        try:
            # Load entities
            if ENTITY_GRAPH_FILE.exists():
                with open(ENTITY_GRAPH_FILE, 'r') as f:
                    entities_data = json.load(f)

                for entity_id, data in entities_data.items():
                    self.entities[entity_id] = Entity(
                        entity_id=data['entity_id'],
                        entity_type=EntityType(data['entity_type']),
                        name=data['name'],
                        description=data['description'],
                        properties=data['properties'],
                        last_observed=data['last_observed'],
                        confidence=data['confidence'],
                        observations=data['observations'],
                        tags=data['tags'],
                        source=data['source']
                    )

            # Load causal rules
            if CAUSAL_RULES_FILE.exists():
                with open(CAUSAL_RULES_FILE, 'r') as f:
                    rules_data = json.load(f)

                for rule_id, data in rules_data.items():
                    self.causal_rules[rule_id] = CausalRule(
                        rule_id=data['rule_id'],
                        rule_type=CausalRuleType(data['rule_type']),
                        action_pattern=data['action_pattern'],
                        outcome_pattern=data['outcome_pattern'],
                        context_conditions=data['context_conditions'],
                        probability=data['probability'],
                        confidence=data['confidence'],
                        observations=data['observations'],
                        successes=data['successes'],
                        failures=data['failures'],
                        created_at=data['created_at'],
                        last_validated=data['last_validated']
                    )

            # Load world model state
            if WORLD_MODEL_FILE.exists():
                with open(WORLD_MODEL_FILE, 'r') as f:
                    world_model_data = json.load(f)

                if 'stats' in world_model_data:
                    self.stats.update(world_model_data['stats'])

                if 'current_state' in world_model_data:
                    state = world_model_data['current_state']
                    self.current_state['timestamp'] = state.get('timestamp', time.time())
                    self.current_state['active_tasks'] = state.get('active_tasks', [])
                    self.current_state['recent_events'] = deque(state.get('recent_events', []), maxlen=50)
                    self.current_state['environment'] = state.get('environment', {})

            logger.info(f"Loaded world model: {len(self.entities)} entities, {len(self.causal_rules)} rules")

        except Exception as e:
            logger.error(f"Failed to load world model: {e}")

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _generate_id(self, prefix: str) -> str:
        """Generate unique ID."""
        timestamp = str(time.time())
        return hashlib.sha256(f"{prefix}_{timestamp}".encode()).hexdigest()[:16]

    def _format_recent_rules(self, limit: int = 10) -> str:
        """Format recent rules for prompts."""
        rules = sorted(
            self.causal_rules.values(),
            key=lambda r: r.last_validated,
            reverse=True
        )[:limit]

        lines = []
        for rule in rules:
            lines.append(
                f"- {rule.action_pattern} → {rule.outcome_pattern} "
                f"(p={rule.probability:.2f}, conf={rule.confidence:.2f}, n={rule.observations})"
            )

        return '\n'.join(lines) if lines else "No rules learned yet"

    def get_stats(self) -> Dict[str, Any]:
        """Get world model statistics."""
        accuracy = (
            self.stats['predictions_correct'] / self.stats['predictions_validated']
            if self.stats['predictions_validated'] > 0 else 0
        )

        base_stats = {
            **self.stats,
            'prediction_accuracy': accuracy,
            'entities_count': len(self.entities),
            'relationships_count': len(self.relationships),
            'rules_count': len(self.causal_rules),
            'reliable_rules_count': sum(1 for r in self.causal_rules.values() if r.is_reliable())
        }

        # Add visual stats if visual model is available
        if self.visual_model and hasattr(self.visual_model, 'get_visual_stats'):
            try:
                visual_stats = self.visual_model.get_visual_stats()
                base_stats['visual'] = visual_stats
            except Exception as e:
                logger.debug(f"Could not get visual stats: {e}")

        return base_stats


# =============================================================================
# STANDALONE TEST
# =============================================================================

async def test_world_model():
    """Test world model functionality."""
    logger.info("=== Testing World Model ===")

    # Create world model
    wm = WorldModel()
    await wm.initialize()

    # Add some entities
    customer = await wm.add_entity(
        EntityType.CUSTOMER,
        "TestCustomer",
        "A test customer",
        {'email': 'test@example.com', 'tier': 'premium'},
        source="test"
    )

    tool = await wm.add_entity(
        EntityType.TOOL,
        "Email API",
        "Email sending service",
        {'status': 'active'},
        source="test"
    )

    # Add relationship
    await wm.add_relationship(
        customer.entity_id,
        tool.entity_id,
        RelationType.USES
    )

    # Test prediction (no rules yet)
    prediction = await wm.predict("Send email to customer", {'customer': customer.entity_id})
    logger.info(f"Prediction 1: {prediction.predicted_outcome} (confidence: {prediction.confidence:.2f})")

    # Update with actual outcome
    await wm.update("Send email to customer", "Email sent successfully", prediction.prediction_id)

    # Make same prediction again (should have learned)
    prediction2 = await wm.predict("Send email to customer", {'customer': customer.entity_id})
    logger.info(f"Prediction 2: {prediction2.predicted_outcome} (confidence: {prediction2.confidence:.2f})")

    # Test with multiple observations
    for i in range(5):
        pred = await wm.predict("Process payment", {'amount': 100})
        await wm.update("Process payment", "Payment successful", pred.prediction_id)

    # Now prediction should be confident
    final_pred = await wm.predict("Process payment", {'amount': 100})
    logger.info(f"Final prediction: {final_pred.predicted_outcome} (confidence: {final_pred.confidence:.2f})")

    # Query entities
    customers = await wm.find_entities(EntityType.CUSTOMER)
    logger.info(f"Found {len(customers)} customers")

    # Get stats
    stats = wm.get_stats()
    logger.info(f"Stats: {json.dumps(stats, indent=2)}")

    logger.info("=== World Model Test Complete ===")


if __name__ == "__main__":
    asyncio.run(test_world_model())
