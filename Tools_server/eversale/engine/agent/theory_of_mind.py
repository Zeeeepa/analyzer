"""
Theory of Mind - Model What Others Think, Believe, Want

This system gives Eversale the ability to model the mental states of others:
- What do they believe?
- What do they want?
- What are they planning to do?
- What do they know/not know?
- How are they feeling?
- How should I communicate with them?

The ToM system predicts how others will respond to actions, infers their mental
state from their words/actions, and adapts communication strategies accordingly.

Integration with Organism:
- Subscribes to: USER_MESSAGE, TASK_COMPLETE, MISSION_COMPLETE events
- Updates agent models based on interactions
- Provides predictions to Planner for simulation
- Tracks customer emotional state for Valence system
- Stores interaction patterns in Episode Compressor

Core Capabilities:
1. Mental State Modeling - Track beliefs, desires, intentions, knowledge, emotions
2. Response Prediction - "If I say X, they'll think Y"
3. State Inference - Infer mental state from their words/actions
4. Adaptive Communication - Adjust approach based on their mental state
5. History Tracking - Model how their mental state changes over time

Performance Targets:
- <100ms prediction latency
- 80%+ prediction accuracy on response type
- 90%+ retention of agent model history
- <500KB memory per agent model
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

# Import organism core
try:
    from .organism_core import EventBus, EventType, OrganismEvent
    from .llm_client import LLMClient, LLMResponse
    from .config_loader import load_config
    INTEGRATION_AVAILABLE = True
except ImportError:
    INTEGRATION_AVAILABLE = False
    logger.warning("Integration modules not available - running in standalone mode")


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class EmotionalState(Enum):
    """Emotional states an agent can be in."""
    FRUSTRATED = "frustrated"       # Repeated failures, confusion
    SATISFIED = "satisfied"         # Success, goals achieved
    CONFUSED = "confused"           # Unclear instructions, missing context
    IMPATIENT = "impatient"         # Waiting too long, slow progress
    CURIOUS = "curious"             # Asking questions, exploring
    TRUSTING = "trusting"           # Confident in the system
    SKEPTICAL = "skeptical"         # Doubtful, needs convincing
    NEUTRAL = "neutral"             # Baseline state
    DELIGHTED = "delighted"         # Exceeded expectations
    ANXIOUS = "anxious"             # Worried about outcome


class CommunicationStyle(Enum):
    """Communication styles we observe."""
    DIRECT = "direct"               # "Just do X"
    DETAILED = "detailed"           # Provides lots of context
    CASUAL = "casual"               # Informal, friendly
    FORMAL = "formal"               # Professional, structured
    TECHNICAL = "technical"         # Uses jargon, technical terms
    QUESTIONING = "questioning"     # Asks many questions
    DIRECTIVE = "directive"         # Gives clear commands
    COLLABORATIVE = "collaborative" # Works together


class BeliefType(Enum):
    """Types of beliefs we track."""
    FACTUAL = "factual"             # "The system can do X"
    EVALUATIVE = "evaluative"       # "The system is good at Y"
    NORMATIVE = "normative"         # "The system should do Z"
    EPISTEMIC = "epistemic"         # "I know/don't know W"


@dataclass
class Belief:
    """A belief an agent holds."""
    belief_id: str
    belief_type: BeliefType
    content: str                    # "Eversale can scrape LinkedIn"
    confidence: float               # 0-1, how strongly they believe it
    evidence: List[str] = field(default_factory=list)  # What led to this belief
    formed_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'belief_id': self.belief_id,
            'belief_type': self.belief_type.value,
            'content': self.content,
            'confidence': self.confidence,
            'evidence': self.evidence,
            'formed_at': self.formed_at,
            'last_updated': self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Belief':
        data['belief_type'] = BeliefType(data['belief_type'])
        return cls(**data)


@dataclass
class Desire:
    """A goal or want an agent has."""
    desire_id: str
    content: str                    # "Get leads from Facebook Ads"
    priority: float                 # 0-1, how important
    urgency: float                  # 0-1, how urgent
    satisfied: bool = False         # Has this been achieved?
    evidence: List[str] = field(default_factory=list)
    formed_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Desire':
        return cls(**data)


@dataclass
class Intention:
    """A plan or intention to act."""
    intention_id: str
    content: str                    # "Ask the agent to research X"
    preconditions: List[str] = field(default_factory=list)  # What needs to be true first
    expected_outcome: str = ""      # What they expect to happen
    confidence: float = 0.5         # How sure they are this will work
    formed_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Intention':
        return cls(**data)


@dataclass
class Interaction:
    """A single interaction with an agent."""
    timestamp: float
    agent_action: str               # What they said/did
    our_response: str               # What we said/did
    their_reaction: Optional[str] = None  # How they reacted
    emotional_state: EmotionalState = EmotionalState.NEUTRAL
    inferred_beliefs: List[str] = field(default_factory=list)  # Belief IDs
    inferred_desires: List[str] = field(default_factory=list)  # Desire IDs

    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'agent_action': self.agent_action,
            'our_response': self.our_response,
            'their_reaction': self.their_reaction,
            'emotional_state': self.emotional_state.value,
            'inferred_beliefs': self.inferred_beliefs,
            'inferred_desires': self.inferred_desires,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Interaction':
        data['emotional_state'] = EmotionalState(data['emotional_state'])
        return cls(**data)


@dataclass
class Reaction:
    """Predicted reaction to an action."""
    predicted_emotion: EmotionalState
    predicted_response: str
    confidence: float               # How confident in this prediction
    reasoning: str                  # Why we predict this


@dataclass
class PredictedResponse:
    """Predicted response to an action."""
    most_likely: str                # Most likely response
    alternatives: List[str]         # Other possible responses
    emotional_impact: str           # Positive/Negative/Neutral
    confidence: float               # 0-1
    reasoning: str                  # Why we predict this


@dataclass
class MentalStateUpdate:
    """Update to mental state based on observation."""
    new_beliefs: List[Belief]
    updated_beliefs: List[str]      # Belief IDs
    new_desires: List[Desire]
    satisfied_desires: List[str]    # Desire IDs
    emotional_state: EmotionalState
    communication_style: CommunicationStyle
    confidence: float               # How confident in this inference


@dataclass
class SuggestedApproach:
    """Suggested communication approach."""
    tone: str                       # "empathetic", "confident", "cautious"
    detail_level: str               # "brief", "moderate", "detailed"
    emphasis: List[str]             # What to emphasize
    avoid: List[str]                # What to avoid
    example_phrasing: str           # Example of how to say it
    reasoning: str                  # Why this approach


# =============================================================================
# AGENT MODEL
# =============================================================================

class AgentModel:
    """
    Model of another agent's mental state.

    Tracks beliefs, desires, intentions, knowledge, emotions, and communication
    style based on observed interactions.
    """

    def __init__(
        self,
        agent_id: str,
        llm_client: Optional['LLMClient'] = None,
    ):
        self.agent_id = agent_id
        self.llm_client = llm_client

        # Mental state
        self.beliefs: Dict[str, Belief] = {}
        self.desires: Dict[str, Desire] = {}
        self.intentions: Dict[str, Intention] = {}
        self.knowledge: Set[str] = set()  # Things they know
        self.gaps: Set[str] = set()       # Things they don't know

        # Emotional/communication state
        self.emotional_state = EmotionalState.NEUTRAL
        self.communication_style = CommunicationStyle.DIRECT

        # Interaction history
        self.history: deque = deque(maxlen=100)  # Last 100 interactions

        # Metadata
        self.first_seen = time.time()
        self.last_seen = time.time()
        self.interaction_count = 0

        # Prediction accuracy tracking
        self.predictions_made = 0
        self.predictions_correct = 0
        self.prediction_accuracy = 0.0

    def add_belief(self, belief: Belief):
        """Add or update a belief."""
        self.beliefs[belief.belief_id] = belief

    def add_desire(self, desire: Desire):
        """Add or update a desire."""
        self.desires[desire.desire_id] = desire

    def add_intention(self, intention: Intention):
        """Add or update an intention."""
        self.intentions[intention.intention_id] = intention

    def add_interaction(self, interaction: Interaction):
        """Record an interaction."""
        self.history.append(interaction)
        self.last_seen = interaction.timestamp
        self.interaction_count += 1

        # Update emotional state
        self.emotional_state = interaction.emotional_state

    def predict_reaction(self, action: str) -> Reaction:
        """
        Predict how this agent will react to an action.

        Uses LLM if available, otherwise uses heuristics.
        """
        # Use LLM for rich prediction
        if self.llm_client:
            return self._predict_reaction_llm(action)

        # Fallback: simple heuristic
        return self._predict_reaction_heuristic(action)

    def _predict_reaction_llm(self, action: str) -> Reaction:
        """Predict reaction using LLM (sync wrapper)."""
        try:
            # Try to get event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is already running, use heuristic
                logger.debug("Event loop running, using heuristic for prediction")
                return self._predict_reaction_heuristic(action)

            # Run async prediction
            return loop.run_until_complete(self._predict_reaction_llm_async(action))
        except Exception as e:
            logger.warning(f"LLM prediction failed: {e}, using heuristic")
            return self._predict_reaction_heuristic(action)

    async def _predict_reaction_llm_async(self, action: str) -> Reaction:
        """Async LLM prediction."""
        context = self._build_context()

        prompt = f"""You are modeling the mental state of a user to predict their reaction.

User Profile:
{context}

Your Planned Action:
{action}

Predict how this user will react emotionally and what they might say/do next.

Respond in JSON:
{{
    "predicted_emotion": "frustrated|satisfied|confused|impatient|curious|trusting|skeptical|neutral|delighted|anxious",
    "predicted_response": "What they will likely say/do",
    "confidence": 0.0-1.0,
    "reasoning": "Why you predict this"
}}"""

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                temperature=0.3,
                max_tokens=500,
            )

            data = json.loads(response.content)

            return Reaction(
                predicted_emotion=EmotionalState(data['predicted_emotion']),
                predicted_response=data['predicted_response'],
                confidence=data['confidence'],
                reasoning=data['reasoning'],
            )
        except Exception as e:
            logger.warning(f"Async LLM prediction failed: {e}")
            return self._predict_reaction_heuristic(action)

    def _predict_reaction_heuristic(self, action: str) -> Reaction:
        """Simple heuristic-based prediction."""
        # Check emotional state
        if self.emotional_state == EmotionalState.FRUSTRATED:
            return Reaction(
                predicted_emotion=EmotionalState.IMPATIENT,
                predicted_response="They might express frustration or ask for faster results",
                confidence=0.6,
                reasoning="User is already frustrated, likely to remain impatient",
            )
        elif self.emotional_state == EmotionalState.SATISFIED:
            return Reaction(
                predicted_emotion=EmotionalState.TRUSTING,
                predicted_response="They will likely accept the action positively",
                confidence=0.7,
                reasoning="User is satisfied with previous results",
            )
        else:
            return Reaction(
                predicted_emotion=EmotionalState.NEUTRAL,
                predicted_response="They will acknowledge and wait for results",
                confidence=0.5,
                reasoning="Neutral state, hard to predict strongly",
            )

    def optimal_framing(self, message: str) -> str:
        """
        Suggest optimal framing for a message to this agent.
        """
        if self.llm_client:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    logger.debug("Event loop running, skipping LLM framing")
                    return message
                return loop.run_until_complete(self._optimal_framing_llm_async(message))
            except Exception as e:
                logger.warning(f"Message framing failed: {e}")
                return message
        return message  # No change if no LLM

    async def _optimal_framing_llm_async(self, message: str) -> str:
        """Use LLM to reframe message optimally."""
        context = self._build_context()

        prompt = f"""You are adapting a message to match a user's communication style and emotional state.

User Profile:
{context}

Message to Deliver:
{message}

Reframe this message to be most effective for this user. Keep the same meaning but adjust:
- Tone (empathetic/confident/cautious)
- Detail level (brief/moderate/detailed)
- Emphasis (what to highlight)

Respond with just the reframed message (no JSON, no explanation)."""

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                temperature=0.3,
                max_tokens=300,
            )
            return response.content.strip()
        except Exception as e:
            logger.warning(f"Async message framing failed: {e}")
            return message

    def _build_context(self) -> str:
        """Build context string for LLM prompts."""
        lines = []

        # Emotional state
        lines.append(f"Emotional State: {self.emotional_state.value}")
        lines.append(f"Communication Style: {self.communication_style.value}")

        # Recent beliefs
        if self.beliefs:
            lines.append("\nKey Beliefs:")
            for belief in list(self.beliefs.values())[:5]:
                lines.append(f"  - {belief.content} (confidence: {belief.confidence:.2f})")

        # Active desires
        active_desires = [d for d in self.desires.values() if not d.satisfied]
        if active_desires:
            lines.append("\nActive Goals:")
            for desire in sorted(active_desires, key=lambda d: d.priority, reverse=True)[:5]:
                lines.append(f"  - {desire.content} (priority: {desire.priority:.2f})")

        # Recent interactions
        if self.history:
            lines.append(f"\nRecent Interactions: {len(self.history)}")
            for interaction in list(self.history)[-3:]:
                lines.append(f"  - Them: {interaction.agent_action[:100]}")
                lines.append(f"    Us: {our_response[:100]}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            'agent_id': self.agent_id,
            'beliefs': {k: v.to_dict() for k, v in self.beliefs.items()},
            'desires': {k: v.to_dict() for k, v in self.desires.items()},
            'intentions': {k: v.to_dict() for k, v in self.intentions.items()},
            'knowledge': list(self.knowledge),
            'gaps': list(self.gaps),
            'emotional_state': self.emotional_state.value,
            'communication_style': self.communication_style.value,
            'history': [i.to_dict() for i in self.history],
            'first_seen': self.first_seen,
            'last_seen': self.last_seen,
            'interaction_count': self.interaction_count,
            'predictions_made': self.predictions_made,
            'predictions_correct': self.predictions_correct,
            'prediction_accuracy': self.prediction_accuracy,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], llm_client: Optional['LLMClient'] = None) -> 'AgentModel':
        """Deserialize from dict."""
        model = cls(data['agent_id'], llm_client)

        # Restore mental state
        model.beliefs = {k: Belief.from_dict(v) for k, v in data.get('beliefs', {}).items()}
        model.desires = {k: Desire.from_dict(v) for k, v in data.get('desires', {}).items()}
        model.intentions = {k: Intention.from_dict(v) for k, v in data.get('intentions', {}).items()}
        model.knowledge = set(data.get('knowledge', []))
        model.gaps = set(data.get('gaps', []))

        # Restore state
        model.emotional_state = EmotionalState(data.get('emotional_state', 'neutral'))
        model.communication_style = CommunicationStyle(data.get('communication_style', 'direct'))

        # Restore history
        model.history = deque(
            [Interaction.from_dict(i) for i in data.get('history', [])],
            maxlen=100
        )

        # Restore metadata
        model.first_seen = data.get('first_seen', time.time())
        model.last_seen = data.get('last_seen', time.time())
        model.interaction_count = data.get('interaction_count', 0)
        model.predictions_made = data.get('predictions_made', 0)
        model.predictions_correct = data.get('predictions_correct', 0)
        model.prediction_accuracy = data.get('prediction_accuracy', 0.0)

        return model


# =============================================================================
# THEORY OF MIND SYSTEM
# =============================================================================

class TheoryOfMind:
    """
    Theory of Mind - Model what others think, believe, want.

    Maintains models of other agents' mental states and uses them to:
    1. Predict how they will respond to actions
    2. Infer their mental state from observations
    3. Adapt communication strategies
    4. Track mental state changes over time
    """

    def __init__(
        self,
        memory_path: Optional[Path] = None,
        llm_client: Optional['LLMClient'] = None,
        event_bus: Optional['EventBus'] = None,
    ):
        self.llm_client = llm_client
        self.event_bus = event_bus

        # Agent models
        self.agent_models: Dict[str, AgentModel] = {}

        # Storage
        self.memory_path = memory_path or Path("memory/agent_models.json")
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)

        # Stats
        self.total_predictions = 0
        self.total_inferences = 0
        self.total_adaptations = 0

        # State
        self._initialized = False
        self._subscription_id: Optional[str] = None

    async def initialize(self):
        """Async initialization."""
        if self._initialized:
            return

        # Load persisted models
        self._load_models()

        # Subscribe to event bus
        if self.event_bus:
            self._subscribe_to_events()

        self._initialized = True
        logger.info("Theory of Mind initialized")

    def _subscribe_to_events(self):
        """Subscribe to relevant events."""
        if not self.event_bus:
            return

        # Subscribe to action completions and failures
        self._subscription_id = self.event_bus.subscribe(
            EventType.ACTION_COMPLETE,
            self._handle_event
        )

        # Also subscribe to action failures
        self.event_bus.subscribe(
            EventType.ACTION_FAILED,
            self._handle_event
        )

        # Subscribe to lessons learned
        self.event_bus.subscribe(
            EventType.LESSON_LEARNED,
            self._handle_event
        )

        logger.debug("Subscribed to EventBus")

    def _handle_event(self, event: 'OrganismEvent'):
        """Handle events from EventBus."""
        try:
            # Extract agent/user ID
            agent_id = event.data.get('user_id') or event.data.get('agent_id', 'default_user')

            if event.event_type == EventType.ACTION_COMPLETE:
                # Track successful action completion
                success = event.data.get('success', True)
                model = self.get_or_create_model(agent_id)

                if success:
                    # Move toward satisfied state
                    model.emotional_state = EmotionalState.SATISFIED
                else:
                    # Move toward frustrated state
                    model.emotional_state = EmotionalState.FRUSTRATED

            elif event.event_type == EventType.ACTION_FAILED:
                # Track action failure
                model = self.get_or_create_model(agent_id)
                model.emotional_state = EmotionalState.FRUSTRATED

            elif event.event_type == EventType.LESSON_LEARNED:
                # Track learning moments
                lesson = event.data.get('lesson', '')
                if lesson:
                    self.infer_state(agent_id, f"Learned: {lesson}")

        except Exception as e:
            logger.error(f"Error handling event: {e}")

    def get_or_create_model(self, agent_id: str) -> AgentModel:
        """Get or create agent model."""
        if agent_id not in self.agent_models:
            self.agent_models[agent_id] = AgentModel(agent_id, self.llm_client)
            logger.debug(f"Created new agent model: {agent_id}")

        return self.agent_models[agent_id]

    def model_agent(self, agent_id: str, observations: List[str]) -> AgentModel:
        """
        Model an agent based on observations.

        Args:
            agent_id: Unique identifier for the agent
            observations: List of observed actions/statements

        Returns:
            Updated AgentModel
        """
        model = self.get_or_create_model(agent_id)

        # Process each observation
        for obs in observations:
            self.infer_state(agent_id, obs)

        return model

    def predict_response(self, agent_id: str, my_action: str) -> PredictedResponse:
        """
        Predict how an agent will respond to an action.

        Args:
            agent_id: Agent to predict
            my_action: Action we plan to take

        Returns:
            PredictedResponse with likely responses
        """
        self.total_predictions += 1

        model = self.get_or_create_model(agent_id)

        # Use LLM if available
        if self.llm_client:
            return self._predict_response_llm(model, my_action)

        # Fallback: simple heuristic
        return self._predict_response_heuristic(model, my_action)

    def _predict_response_llm(self, model: AgentModel, my_action: str) -> PredictedResponse:
        """Use LLM to predict response (sync wrapper)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.debug("Event loop running, using heuristic")
                return self._predict_response_heuristic(model, my_action)
            return loop.run_until_complete(self._predict_response_llm_async(model, my_action))
        except Exception as e:
            logger.warning(f"LLM prediction failed: {e}")
            return self._predict_response_heuristic(model, my_action)

    async def _predict_response_llm_async(self, model: AgentModel, my_action: str) -> PredictedResponse:
        """Async LLM prediction."""
        context = model._build_context()

        prompt = f"""You are predicting how a user will respond to an action.

User Profile:
{context}

Your Planned Action:
{my_action}

Predict the user's most likely response and alternatives.

Respond in JSON:
{{
    "most_likely": "Most likely response",
    "alternatives": ["Alternative 1", "Alternative 2"],
    "emotional_impact": "positive|negative|neutral",
    "confidence": 0.0-1.0,
    "reasoning": "Why you predict this"
}}"""

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                temperature=0.3,
                max_tokens=500,
            )

            data = json.loads(response.content)

            return PredictedResponse(
                most_likely=data['most_likely'],
                alternatives=data.get('alternatives', []),
                emotional_impact=data['emotional_impact'],
                confidence=data['confidence'],
                reasoning=data['reasoning'],
            )

        except Exception as e:
            logger.warning(f"Async LLM prediction failed: {e}")
            return self._predict_response_heuristic(model, my_action)

    def _predict_response_heuristic(self, model: AgentModel, my_action: str) -> PredictedResponse:
        """Simple heuristic prediction."""
        # Base on emotional state
        if model.emotional_state == EmotionalState.SATISFIED:
            return PredictedResponse(
                most_likely="They will accept this positively",
                alternatives=["They might ask for more details"],
                emotional_impact="positive",
                confidence=0.6,
                reasoning="User is currently satisfied",
            )
        elif model.emotional_state == EmotionalState.FRUSTRATED:
            return PredictedResponse(
                most_likely="They might express impatience or concern",
                alternatives=["They might ask to try a different approach"],
                emotional_impact="negative",
                confidence=0.7,
                reasoning="User is currently frustrated",
            )
        else:
            return PredictedResponse(
                most_likely="They will acknowledge and wait",
                alternatives=["They might ask clarifying questions"],
                emotional_impact="neutral",
                confidence=0.5,
                reasoning="User is in neutral state",
            )

    def infer_state(self, agent_id: str, their_action: str) -> MentalStateUpdate:
        """
        Infer mental state from an agent's action.

        Args:
            agent_id: Agent who acted
            their_action: What they said/did

        Returns:
            MentalStateUpdate with inferred changes
        """
        self.total_inferences += 1

        model = self.get_or_create_model(agent_id)

        # Use LLM if available
        if self.llm_client:
            return self._infer_state_llm(model, their_action)

        # Fallback: simple heuristic
        return self._infer_state_heuristic(model, their_action)

    def _infer_state_llm(self, model: AgentModel, their_action: str) -> MentalStateUpdate:
        """Use LLM to infer mental state (sync wrapper)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.debug("Event loop running, using heuristic")
                return self._infer_state_heuristic(model, their_action)
            return loop.run_until_complete(self._infer_state_llm_async(model, their_action))
        except Exception as e:
            logger.warning(f"LLM inference failed: {e}")
            return self._infer_state_heuristic(model, their_action)

    async def _infer_state_llm_async(self, model: AgentModel, their_action: str) -> MentalStateUpdate:
        """Async LLM inference."""
        context = model._build_context()

        prompt = f"""You are inferring a user's mental state from their action.

User Profile:
{context}

Their Latest Action:
{their_action}

Infer:
1. What new beliefs might they have formed?
2. What new goals/desires might they have?
3. What is their emotional state?
4. What is their communication style?

Respond in JSON:
{{
    "new_beliefs": [
        {{"content": "belief content", "confidence": 0.0-1.0, "type": "factual|evaluative|normative|epistemic"}}
    ],
    "new_desires": [
        {{"content": "goal/want", "priority": 0.0-1.0, "urgency": 0.0-1.0}}
    ],
    "emotional_state": "frustrated|satisfied|confused|impatient|curious|trusting|skeptical|neutral|delighted|anxious",
    "communication_style": "direct|detailed|casual|formal|technical|questioning|directive|collaborative",
    "confidence": 0.0-1.0
}}"""

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                temperature=0.3,
                max_tokens=800,
            )

            data = json.loads(response.content)

            # Create beliefs
            new_beliefs = []
            for b in data.get('new_beliefs', []):
                belief = Belief(
                    belief_id=hashlib.md5(b['content'].encode()).hexdigest()[:16],
                    belief_type=BeliefType(b.get('type', 'factual')),
                    content=b['content'],
                    confidence=b['confidence'],
                    evidence=[their_action],
                )
                model.add_belief(belief)
                new_beliefs.append(belief)

            # Create desires
            new_desires = []
            for d in data.get('new_desires', []):
                desire = Desire(
                    desire_id=hashlib.md5(d['content'].encode()).hexdigest()[:16],
                    content=d['content'],
                    priority=d['priority'],
                    urgency=d['urgency'],
                    evidence=[their_action],
                )
                model.add_desire(desire)
                new_desires.append(desire)

            # Update state
            emotional_state = EmotionalState(data['emotional_state'])
            communication_style = CommunicationStyle(data['communication_style'])

            model.emotional_state = emotional_state
            model.communication_style = communication_style

            return MentalStateUpdate(
                new_beliefs=new_beliefs,
                updated_beliefs=[],
                new_desires=new_desires,
                satisfied_desires=[],
                emotional_state=emotional_state,
                communication_style=communication_style,
                confidence=data['confidence'],
            )

        except Exception as e:
            logger.warning(f"LLM inference failed: {e}")
            return self._infer_state_heuristic(model, their_action)

    def _infer_state_heuristic(self, model: AgentModel, their_action: str) -> MentalStateUpdate:
        """Simple heuristic inference."""
        action_lower = their_action.lower()

        # Detect emotional state
        emotional_state = EmotionalState.NEUTRAL
        if any(word in action_lower for word in ['frustrated', 'annoying', 'slow', 'broken']):
            emotional_state = EmotionalState.FRUSTRATED
        elif any(word in action_lower for word in ['great', 'perfect', 'excellent', 'thanks']):
            emotional_state = EmotionalState.SATISFIED
        elif any(word in action_lower for word in ['confused', 'unclear', 'understand', 'what']):
            emotional_state = EmotionalState.CONFUSED

        # Detect communication style
        communication_style = CommunicationStyle.DIRECT
        if len(their_action) > 200:
            communication_style = CommunicationStyle.DETAILED
        elif '?' in their_action:
            communication_style = CommunicationStyle.QUESTIONING

        model.emotional_state = emotional_state
        model.communication_style = communication_style

        return MentalStateUpdate(
            new_beliefs=[],
            updated_beliefs=[],
            new_desires=[],
            satisfied_desires=[],
            emotional_state=emotional_state,
            communication_style=communication_style,
            confidence=0.5,
        )

    def get_approach(self, agent_id: str) -> SuggestedApproach:
        """
        Get suggested communication approach for an agent.

        Args:
            agent_id: Agent to communicate with

        Returns:
            SuggestedApproach with recommendations
        """
        self.total_adaptations += 1

        model = self.get_or_create_model(agent_id)

        # Use LLM if available
        if self.llm_client:
            return self._get_approach_llm(model)

        # Fallback: simple heuristic
        return self._get_approach_heuristic(model)

    def _get_approach_llm(self, model: AgentModel) -> SuggestedApproach:
        """Use LLM to suggest approach (sync wrapper)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.debug("Event loop running, using heuristic")
                return self._get_approach_heuristic(model)
            return loop.run_until_complete(self._get_approach_llm_async(model))
        except Exception as e:
            logger.warning(f"LLM approach suggestion failed: {e}")
            return self._get_approach_heuristic(model)

    async def _get_approach_llm_async(self, model: AgentModel) -> SuggestedApproach:
        """Async LLM approach suggestion."""
        context = model._build_context()

        prompt = f"""You are suggesting how to communicate with a user.

User Profile:
{context}

Suggest the optimal communication approach.

Respond in JSON:
{{
    "tone": "empathetic|confident|cautious|encouraging|professional",
    "detail_level": "brief|moderate|detailed",
    "emphasis": ["What to emphasize"],
    "avoid": ["What to avoid"],
    "example_phrasing": "Example of how to phrase a message",
    "reasoning": "Why this approach"
}}"""

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                temperature=0.3,
                max_tokens=500,
            )

            data = json.loads(response.content)

            return SuggestedApproach(
                tone=data['tone'],
                detail_level=data['detail_level'],
                emphasis=data.get('emphasis', []),
                avoid=data.get('avoid', []),
                example_phrasing=data['example_phrasing'],
                reasoning=data['reasoning'],
            )

        except Exception as e:
            logger.warning(f"Async LLM approach suggestion failed: {e}")
            return self._get_approach_heuristic(model)

    def _get_approach_heuristic(self, model: AgentModel) -> SuggestedApproach:
        """Simple heuristic approach."""
        # Base on emotional state
        if model.emotional_state == EmotionalState.FRUSTRATED:
            return SuggestedApproach(
                tone="empathetic",
                detail_level="brief",
                emphasis=["Acknowledging their frustration", "Concrete next steps"],
                avoid=["Technical jargon", "Long explanations"],
                example_phrasing="I understand this is frustrating. Let me try a different approach that should work better.",
                reasoning="User is frustrated, need empathy and quick action",
            )
        elif model.emotional_state == EmotionalState.CONFUSED:
            return SuggestedApproach(
                tone="patient",
                detail_level="detailed",
                emphasis=["Clear explanations", "Step-by-step guidance"],
                avoid=["Assumptions", "Skipping steps"],
                example_phrasing="Let me walk you through this step by step to make sure it's clear.",
                reasoning="User is confused, need clarity and patience",
            )
        else:
            return SuggestedApproach(
                tone="confident",
                detail_level="moderate",
                emphasis=["Progress", "Results"],
                avoid=["Over-explaining"],
                example_phrasing="I'll get started on this right away.",
                reasoning="User is neutral, standard professional approach",
            )

    def update(self, agent_id: str, observation: str):
        """
        Update agent model with new observation.

        Args:
            agent_id: Agent to update
            observation: New observation about them
        """
        self.infer_state(agent_id, observation)

    def _load_models(self):
        """Load persisted agent models."""
        if not self.memory_path.exists():
            return

        try:
            with open(self.memory_path) as f:
                data = json.load(f)

            for agent_id, model_data in data.items():
                self.agent_models[agent_id] = AgentModel.from_dict(
                    model_data,
                    self.llm_client
                )

            logger.info(f"Loaded {len(self.agent_models)} agent models")

        except Exception as e:
            logger.error(f"Failed to load agent models: {e}")

    def save_models(self):
        """Persist agent models."""
        try:
            data = {
                agent_id: model.to_dict()
                for agent_id, model in self.agent_models.items()
            }

            # Atomic write
            temp_path = self.memory_path.with_suffix('.tmp')
            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2)

            temp_path.replace(self.memory_path)

            logger.debug(f"Saved {len(self.agent_models)} agent models")

        except Exception as e:
            logger.error(f"Failed to save agent models: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics."""
        total_accuracy = 0.0
        if self.agent_models:
            total_accuracy = sum(
                m.prediction_accuracy for m in self.agent_models.values()
            ) / len(self.agent_models)

        return {
            'total_models': len(self.agent_models),
            'total_predictions': self.total_predictions,
            'total_inferences': self.total_inferences,
            'total_adaptations': self.total_adaptations,
            'avg_prediction_accuracy': total_accuracy,
        }

    async def shutdown(self):
        """Cleanup on shutdown."""
        # Save models
        self.save_models()

        # Unsubscribe from events
        if self.event_bus and self._subscription_id:
            self.event_bus.unsubscribe(self._subscription_id)

        logger.info("Theory of Mind shutdown complete")


# =============================================================================
# STANDALONE USAGE
# =============================================================================

async def demo():
    """Demonstration of Theory of Mind system."""
    from pathlib import Path

    # Initialize
    tom = TheoryOfMind(
        memory_path=Path("memory/agent_models.json"),
        llm_client=None,  # Will use heuristics
    )
    await tom.initialize()

    # Model a user
    user_id = "demo_user"

    # Observe some actions
    observations = [
        "I'm frustrated with how slow this is",
        "Can you make it faster?",
        "I need leads from Facebook Ads ASAP",
    ]

    print("=== Modeling User ===")
    for obs in observations:
        print(f"\nObservation: {obs}")
        update = tom.infer_state(user_id, obs)
        print(f"Emotional State: {update.emotional_state.value}")
        print(f"Communication Style: {update.communication_style.value}")
        print(f"Confidence: {update.confidence:.2f}")

    # Predict response to an action
    print("\n=== Predicting Response ===")
    my_action = "I'll optimize the scraping and have results in 10 minutes"
    prediction = tom.predict_response(user_id, my_action)
    print(f"My Action: {my_action}")
    print(f"Predicted Response: {prediction.most_likely}")
    print(f"Emotional Impact: {prediction.emotional_impact}")
    print(f"Confidence: {prediction.confidence:.2f}")

    # Get communication approach
    print("\n=== Suggested Approach ===")
    approach = tom.get_approach(user_id)
    print(f"Tone: {approach.tone}")
    print(f"Detail Level: {approach.detail_level}")
    print(f"Example: {approach.example_phrasing}")

    # Stats
    print("\n=== Stats ===")
    stats = tom.get_stats()
    for key, value in stats.items():
        print(f"{key}: {value}")

    await tom.shutdown()


if __name__ == "__main__":
    asyncio.run(demo())
