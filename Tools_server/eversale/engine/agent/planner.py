#!/usr/bin/env python3
"""
Planner - Multi-Step Lookahead Planning with Tree Search

This module implements tree-based planning that thinks multiple steps ahead
before acting. It expands possible action sequences, simulates outcomes,
scores paths, and selects the best plan.

Purpose:
- Tree expansion: Given a goal, expand possible action sequences
- Simulation: Use world knowledge to predict outcomes of each path
- Scoring: Rate paths by success probability + mission alignment + efficiency
- Pruning: Cut bad branches early to save compute
- Replanning: After each observation, replan from new state
- Depth control: Configurable lookahead (default 3-5 steps)

Integration:
- EventBus subscription for action outcomes and state changes
- LLM client for tree expansion and outcome prediction
- Uncertainty tracker for confidence scoring
- Mission keeper for alignment scoring
- Self model for capability-based pruning
- ToolSelector for intelligent routing (Kimi K2, Browser, ChatGPT, MiniCPM)

Design Philosophy:
Instead of reactive "next action" thinking, this planner builds a tree
of possible futures, simulates them, and picks the best path. When reality
diverges from prediction, it replans.

Example:
    Goal: "Find Python books on books.toscrape.com"

    Tree expansion:
    1. Navigate → Search → Filter → Extract
    2. Navigate → Browse categories → Find Python → Extract
    3. Navigate → Extract all → Filter locally

    Simulation:
    Path 1: 4 steps, high reliability, medium efficiency
    Path 2: 5 steps, medium reliability, high quality
    Path 3: 3 steps, low reliability (might miss books)

    Selection: Path 1 (balanced)

    Execution: Start path 1
    Observation: Search box not found!
    Replanning: Switch to path 2

This makes the agent more robust to unexpected situations and better
at complex multi-step tasks.
"""

import asyncio
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set, Union
from dataclasses import dataclass, field, asdict
from collections import deque, defaultdict
from enum import Enum
from loguru import logger
import sqlite3
import threading
import hashlib

try:
    from .organism_core import EventBus, EventType, OrganismEvent
    from .llm_client import LLMClient, LLMResponse
    from .uncertainty_tracker import UncertaintyTracker
    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False
    logger.warning("Some imports not available - planner running in limited mode")

# ToolSelector integration with graceful fallback
try:
    from .tool_selector import ToolSelector, ToolType, ToolChoice
    TOOL_SELECTOR_AVAILABLE = True
except ImportError:
    TOOL_SELECTOR_AVAILABLE = False
    logger.debug("ToolSelector not available - planner will use default tool routing")


# =============================================================================
# CONFIGURATION
# =============================================================================

MEMORY_DIR = Path("memory")
MEMORY_DIR.mkdir(exist_ok=True)

PLANNER_DB = MEMORY_DIR / "planner.db"
PLAN_CACHE_JSON = MEMORY_DIR / "plan_cache.json"

# Planning parameters
DEFAULT_DEPTH = 5  # Default lookahead depth
MAX_DEPTH = 10  # Maximum depth to prevent runaway
MAX_BRANCHES = 5  # Maximum branches per node
SIMULATION_TIMEOUT = 300.0  # Seconds for simulation (increased for complex extractions)
REPLAN_THRESHOLD = 0.3  # If confidence drops below this, replan

# Scoring weights
SCORE_SUCCESS_PROB = 0.4  # Weight for predicted success probability
SCORE_MISSION_ALIGN = 0.3  # Weight for mission alignment
SCORE_EFFICIENCY = 0.2  # Weight for efficiency (fewer steps)
SCORE_UNCERTAINTY = 0.1  # Weight for uncertainty reduction

# Pruning thresholds
PRUNE_MIN_SUCCESS = 0.1  # Prune paths with <10% success probability
PRUNE_MIN_SCORE = 0.2  # Prune paths with <20% overall score


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class ActionStatus(Enum):
    """Status of a planned action."""
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlannedAction:
    """A single action in a plan."""
    action_type: str  # "navigate", "click", "extract", etc.
    parameters: Dict[str, Any]  # Action-specific parameters
    expected_duration: float = 1.0  # Estimated seconds
    success_probability: float = 0.8  # Predicted success rate
    status: ActionStatus = ActionStatus.PLANNED

    # Execution tracking
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    actual_duration: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "action_type": self.action_type,
            "parameters": self.parameters,
            "expected_duration": self.expected_duration,
            "success_probability": self.success_probability,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "actual_duration": self.actual_duration,
            "result": str(self.result) if self.result else None,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlannedAction':
        """Create from dictionary."""
        return cls(
            action_type=data["action_type"],
            parameters=data.get("parameters", {}),
            expected_duration=data.get("expected_duration", 1.0),
            success_probability=data.get("success_probability", 0.8),
            status=ActionStatus(data.get("status", "planned")),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            actual_duration=data.get("actual_duration"),
            error=data.get("error"),
        )


@dataclass
class PredictedOutcome:
    """Predicted outcome of executing a sequence of actions."""
    success_probability: float  # Overall probability of success
    expected_results: Dict[str, Any]  # What we expect to achieve
    confidence: float  # How confident are we in this prediction
    failure_modes: List[str]  # Potential ways this could fail
    resource_cost: float = 1.0  # Estimated resource cost (tokens, time, etc.)

    # Learning signals
    assumptions: List[str] = field(default_factory=list)  # What we're assuming
    uncertainties: List[str] = field(default_factory=list)  # What we're uncertain about

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ActionPlan:
    """A complete plan - sequence of actions with predicted outcome."""
    plan_id: str  # Unique identifier
    goal: str  # What we're trying to achieve
    steps: List[PlannedAction]  # Sequence of actions
    expected_outcome: PredictedOutcome  # What we expect to happen
    confidence: float  # Overall confidence in this plan
    score: float  # Overall score (higher = better)

    # Contingencies - backup plans if things go wrong
    contingencies: Dict[str, 'ActionPlan'] = field(default_factory=dict)

    # Execution tracking
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    current_step: int = 0

    # Metadata
    depth: int = 0  # Depth in planning tree
    parent_plan: Optional[str] = None  # Parent plan ID (for contingencies)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps": [step.to_dict() for step in self.steps],
            "expected_outcome": self.expected_outcome.to_dict(),
            "confidence": self.confidence,
            "score": self.score,
            "contingencies": {k: v.to_dict() for k, v in self.contingencies.items()},
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "current_step": self.current_step,
            "depth": self.depth,
            "parent_plan": self.parent_plan,
        }

    def get_current_action(self) -> Optional[PlannedAction]:
        """Get the current action being executed."""
        if 0 <= self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    def advance(self):
        """Move to next step."""
        self.current_step += 1

    def is_complete(self) -> bool:
        """Check if plan is fully executed."""
        return self.current_step >= len(self.steps)


@dataclass
class PlanNode:
    """Node in the planning tree."""
    node_id: str
    state_description: str  # Description of world state at this node
    action: Optional[PlannedAction]  # Action that led to this state
    parent: Optional['PlanNode'] = None
    children: List['PlanNode'] = field(default_factory=list)
    depth: int = 0

    # Evaluation
    score: float = 0.0
    visits: int = 0

    def get_path(self) -> List[PlannedAction]:
        """Get sequence of actions from root to this node."""
        path = []
        node = self
        while node.parent is not None:
            if node.action:
                path.insert(0, node.action)
            node = node.parent
        return path


@dataclass
class PlanTree:
    """Tree of possible action sequences."""
    root: PlanNode
    goal: str
    max_depth: int
    nodes: Dict[str, PlanNode] = field(default_factory=dict)

    def add_node(self, node: PlanNode):
        """Add node to tree."""
        self.nodes[node.node_id] = node
        if node.parent:
            node.parent.children.append(node)

    def get_leaf_nodes(self) -> List[PlanNode]:
        """Get all leaf nodes (potential complete plans)."""
        return [node for node in self.nodes.values() if not node.children]

    def get_best_path(self) -> List[PlannedAction]:
        """Get highest-scoring path through tree."""
        leaves = self.get_leaf_nodes()
        if not leaves:
            return []

        best_leaf = max(leaves, key=lambda n: n.score)
        return best_leaf.get_path()


# =============================================================================
# WORLD MODEL (SIMPLE STUB)
# =============================================================================

class SimpleWorldModel:
    """
    Simplified world model for outcome prediction.

    In production, this would be replaced with a more sophisticated
    world model that learns from experience. For now, it provides
    basic heuristic predictions.
    """

    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client

        # Simple heuristics for common action types
        self.action_success_rates = {
            "navigate": 0.95,
            "click": 0.85,
            "fill": 0.9,
            "extract": 0.8,
            "search": 0.85,
            "wait": 0.99,
            "screenshot": 0.95,
        }

        self.action_durations = {
            "navigate": 3.0,
            "click": 0.5,
            "fill": 1.0,
            "extract": 2.0,
            "search": 1.5,
            "wait": 1.0,
            "screenshot": 0.5,
        }

    async def predict_outcome(
        self,
        actions: List[PlannedAction],
        current_state: str,
    ) -> PredictedOutcome:
        """
        Predict outcome of executing a sequence of actions.

        Args:
            actions: Sequence of actions to execute
            current_state: Description of current world state

        Returns:
            Predicted outcome with success probability and expected results
        """
        if not actions:
            return PredictedOutcome(
                success_probability=1.0,
                expected_results={},
                confidence=1.0,
                failure_modes=[],
            )

        # Calculate overall success probability (product of individual probabilities)
        success_prob = 1.0
        total_duration = 0.0
        failure_modes = []

        for action in actions:
            base_prob = self.action_success_rates.get(action.action_type, 0.7)
            # Use action's own probability if specified
            action_prob = action.success_probability if action.success_probability > 0 else base_prob
            success_prob *= action_prob

            duration = self.action_durations.get(action.action_type, 1.0)
            total_duration += duration

            # Add potential failure modes
            if action_prob < 0.9:
                failure_modes.append(f"{action.action_type} might fail")

        # Use LLM for more sophisticated prediction if available
        if self.llm_client:
            try:
                prediction = await self._llm_predict(actions, current_state)
                # Blend LLM prediction with heuristic
                success_prob = 0.7 * success_prob + 0.3 * prediction.success_probability
            except Exception as e:
                logger.debug(f"LLM prediction failed, using heuristic: {e}")

        return PredictedOutcome(
            success_probability=success_prob,
            expected_results={"estimated_duration": total_duration},
            confidence=0.6,  # Moderate confidence in heuristic predictions
            failure_modes=failure_modes,
            resource_cost=len(actions) * 100,  # Rough token estimate
        )

    async def _llm_predict(
        self,
        actions: List[PlannedAction],
        current_state: str,
    ) -> PredictedOutcome:
        """Use LLM to predict outcome (optional enhancement)."""
        prompt = f"""Given the current state and planned actions, predict the outcome.

Current State:
{current_state}

Planned Actions:
{json.dumps([a.to_dict() for a in actions], indent=2)}

Predict:
1. Success probability (0-1)
2. Expected results
3. Potential failure modes

Respond in JSON format:
{{"success_probability": 0.8, "expected_results": {{}}, "failure_modes": []}}"""

        response = await self.llm_client.generate(
            prompt=prompt,
            temperature=0.1,
            max_tokens=500,
        )

        try:
            result = json.loads(response.content)
            return PredictedOutcome(
                success_probability=result.get("success_probability", 0.5),
                expected_results=result.get("expected_results", {}),
                confidence=0.7,
                failure_modes=result.get("failure_modes", []),
            )
        except json.JSONDecodeError:
            # Fallback to heuristic
            return PredictedOutcome(
                success_probability=0.5,
                expected_results={},
                confidence=0.3,
                failure_modes=["LLM prediction failed"],
            )


# =============================================================================
# PLANNER
# =============================================================================

class Planner:
    """
    Multi-step lookahead planner with tree search.

    This planner:
    1. Expands possible action sequences (tree search)
    2. Simulates outcomes using world model
    3. Scores paths by success probability + alignment + efficiency
    4. Prunes bad branches early
    5. Selects best plan
    6. Replans when reality diverges from prediction
    """

    def __init__(
        self,
        event_bus: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        uncertainty_tracker: Optional[Any] = None,
        mission_goal: Optional[str] = None,
        tool_selector: Optional[Any] = None,
        config: Optional[Dict] = None,
    ):
        self.event_bus = event_bus
        self.llm_client = llm_client
        self.uncertainty_tracker = uncertainty_tracker
        self.mission_goal = mission_goal or "Complete tasks efficiently and reliably"
        self.config = config or {}

        # World model for prediction
        self.world_model = SimpleWorldModel(llm_client)

        # Tool selector for intelligent routing
        self.tool_selector = tool_selector
        self._tool_selector_initialized = False

        # Plan cache
        self.plan_cache: Dict[str, ActionPlan] = {}
        self.active_plan: Optional[ActionPlan] = None

        # Performance tracking
        self.plans_created = 0
        self.plans_completed = 0
        self.plans_abandoned = 0
        self.replans = 0
        self.tool_selections = 0  # Track tool selector usage

        # Database for persistence
        self._db_lock = threading.Lock()
        self._init_db()

        # Subscribe to events
        if self.event_bus:
            self.event_bus.subscribe(EventType.ACTION_COMPLETE, self._on_action_complete)
            self.event_bus.subscribe(EventType.ACTION_FAILED, self._on_action_failed)
            self.event_bus.subscribe(EventType.SURPRISE, self._on_surprise)

        logger.info("Planner initialized")

    def _init_db(self):
        """Initialize SQLite database for plan persistence."""
        with self._db_lock:
            conn = sqlite3.connect(str(PLANNER_DB))
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS plans (
                    plan_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    plan_data TEXT NOT NULL,
                    score REAL,
                    confidence REAL,
                    created_at REAL,
                    status TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS plan_outcomes (
                    plan_id TEXT,
                    outcome TEXT,
                    success INTEGER,
                    actual_duration REAL,
                    recorded_at REAL,
                    FOREIGN KEY (plan_id) REFERENCES plans(plan_id)
                )
            """)

            conn.commit()
            conn.close()

    async def _ensure_tool_selector(self):
        """Ensure tool selector is initialized (lazy initialization)."""
        if not TOOL_SELECTOR_AVAILABLE:
            return

        if self.tool_selector and not self._tool_selector_initialized:
            try:
                await self.tool_selector.initialize()
                self._tool_selector_initialized = True
                logger.info("ToolSelector initialized for Planner")
            except Exception as e:
                logger.warning(f"Failed to initialize ToolSelector: {e}")

    async def _select_tool_for_action(
        self,
        action: PlannedAction,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        """
        Use ToolSelector to determine optimal tool for executing an action.

        Args:
            action: The planned action to execute
            goal: Overall goal context
            context: Additional context

        Returns:
            ToolChoice if ToolSelector available, None otherwise
        """
        if not TOOL_SELECTOR_AVAILABLE or not self.tool_selector:
            return None

        await self._ensure_tool_selector()

        if not self._tool_selector_initialized:
            return None

        try:
            # Build task description from action
            task_description = f"{action.action_type}"
            if action.parameters:
                # Add key parameters to task description
                param_str = ", ".join([f"{k}={v}" for k, v in list(action.parameters.items())[:3]])
                task_description += f" ({param_str})"

            # Add goal context
            task_description += f" - Goal: {goal}"

            # Merge context
            full_context = context or {}
            full_context.update({
                'action_type': action.action_type,
                'goal': goal,
                'step_in_plan': True,
            })

            # Select optimal tool
            tool_choice = await self.tool_selector.select(task_description, full_context)

            self.tool_selections += 1

            logger.debug(
                f"Tool selection for {action.action_type}: "
                f"{tool_choice.primary_tool.value} "
                f"({'+ ' + ', '.join([t.value for t in tool_choice.secondary_tools]) if tool_choice.secondary_tools else 'solo'}) "
                f"| confidence={tool_choice.confidence:.2f}"
            )

            return tool_choice

        except Exception as e:
            logger.warning(f"Tool selection failed for action {action.action_type}: {e}")
            return None

    def get_tool_routing(self, action: PlannedAction) -> Optional[Dict[str, Any]]:
        """
        Extract tool routing information from a planned action.

        Args:
            action: PlannedAction with embedded tool choice

        Returns:
            Dictionary with tool routing info, or None if not available
        """
        if '_tool_choice' in action.parameters:
            return action.parameters['_tool_choice']
        return None

    def log_tool_routing(self, plan: ActionPlan):
        """
        Log tool routing decisions for all actions in a plan.

        Args:
            plan: ActionPlan to log routing for
        """
        if not plan.steps:
            return

        logger.info(f"Tool routing for plan {plan.plan_id}:")
        for i, action in enumerate(plan.steps):
            routing = self.get_tool_routing(action)
            if routing:
                logger.info(
                    f"  Step {i+1} ({action.action_type}): "
                    f"{routing['primary_tool']} "
                    f"({'+ ' + ', '.join(routing['secondary_tools']) if routing['secondary_tools'] else 'solo'}) "
                    f"| confidence={routing['confidence']:.2f} | {routing['reasoning']}"
                )
            else:
                logger.info(f"  Step {i+1} ({action.action_type}): Default routing (no tool selector)")

    async def plan(
        self,
        goal: str,
        current_state: str,
        depth: int = DEFAULT_DEPTH,
        context: Optional[Dict[str, Any]] = None,
    ) -> ActionPlan:
        """
        Create a plan to achieve the goal.

        Args:
            goal: What we're trying to achieve
            current_state: Description of current world state
            depth: How many steps to look ahead
            context: Additional context (tools available, constraints, etc.)

        Returns:
            Best action plan
        """
        depth = min(depth, MAX_DEPTH)
        context = context or {}

        logger.info(f"Planning for goal: {goal} (depth={depth})")

        # Check cache first
        cache_key = self._get_cache_key(goal, current_state)
        if cache_key in self.plan_cache:
            cached_plan = self.plan_cache[cache_key]
            logger.debug(f"Using cached plan: {cached_plan.plan_id}")
            return cached_plan

        # Expand tree of possible action sequences
        tree = await self.expand_tree(goal, current_state, depth, context)

        # Select best path through tree
        plan = await self.select_best(tree)

        # Generate contingency plans for high-risk steps
        if plan.confidence < 0.7:
            await self._generate_contingencies(plan, current_state, context)

        # Cache plan
        self.plan_cache[cache_key] = plan
        self.plans_created += 1

        # Persist to database
        self._save_plan(plan)

        # Log tool routing decisions
        if TOOL_SELECTOR_AVAILABLE and self._tool_selector_initialized:
            self.log_tool_routing(plan)

        # Publish event
        if self.event_bus:
            await self.event_bus.publish(OrganismEvent(
                event_type=EventType.PREDICTION_MADE,
                source="planner",
                data={
                    "plan_id": plan.plan_id,
                    "goal": goal,
                    "steps": len(plan.steps),
                    "confidence": plan.confidence,
                    "tool_selections": self.tool_selections,
                }
            ))

        logger.info(f"Created plan {plan.plan_id}: {len(plan.steps)} steps, confidence={plan.confidence:.2f}")
        return plan

    async def expand_tree(
        self,
        goal: str,
        current_state: str,
        depth: int,
        context: Dict[str, Any],
    ) -> PlanTree:
        """
        Expand tree of possible action sequences.

        Args:
            goal: What we're trying to achieve
            current_state: Description of current world state
            depth: Maximum depth to expand
            context: Additional context

        Returns:
            Planning tree with all possible paths
        """
        # Create root node
        root = PlanNode(
            node_id="root",
            state_description=current_state,
            action=None,
            depth=0,
        )

        tree = PlanTree(
            root=root,
            goal=goal,
            max_depth=depth,
        )
        tree.add_node(root)

        # Expand tree breadth-first
        queue = deque([root])

        while queue:
            node = queue.popleft()

            # Stop if max depth reached
            if node.depth >= depth:
                continue

            # Generate possible next actions
            possible_actions = await self._generate_actions(
                goal=goal,
                current_state=node.state_description,
                context=context,
                depth=node.depth,
            )

            # Limit branching factor
            possible_actions = possible_actions[:MAX_BRANCHES]

            # Create child nodes for each action
            for action in possible_actions:
                # Predict resulting state
                new_state = await self._predict_state(node.state_description, action)

                # Create child node
                child = PlanNode(
                    node_id=f"{node.node_id}_{action.action_type}_{node.depth}",
                    state_description=new_state,
                    action=action,
                    parent=node,
                    depth=node.depth + 1,
                )

                tree.add_node(child)
                queue.append(child)

        logger.debug(f"Expanded tree: {len(tree.nodes)} nodes, max_depth={depth}")
        return tree

    async def _generate_actions(
        self,
        goal: str,
        current_state: str,
        context: Dict[str, Any],
        depth: int,
    ) -> List[PlannedAction]:
        """
        Generate possible next actions from current state.

        Uses LLM to reason about what actions could move us toward the goal.
        Integrates with ToolSelector to determine optimal execution tool.
        """
        if not self.llm_client:
            # Fallback: return basic actions
            return self._fallback_actions(goal, current_state)

        try:
            prompt = f"""You are planning actions to achieve a goal.

Goal: {goal}

Current State: {current_state}

Planning Depth: {depth}/{MAX_DEPTH}

Available Tools: {context.get('tools', 'navigate, click, fill, extract, search, wait')}

Generate 2-3 possible next actions that could move toward the goal.
Consider different approaches (fast vs thorough, risky vs safe).

Respond in JSON format:
[
  {{
    "action_type": "navigate",
    "parameters": {{"url": "example.com"}},
    "expected_duration": 3.0,
    "success_probability": 0.95,
    "reasoning": "Why this action helps"
  }}
]"""

            response = await self.llm_client.generate(
                prompt=prompt,
                temperature=0.3,  # Some creativity for diverse plans
                max_tokens=1000,
            )

            # Parse JSON response
            actions_data = json.loads(response.content)

            actions = []
            for action_data in actions_data:
                action = PlannedAction(
                    action_type=action_data["action_type"],
                    parameters=action_data.get("parameters", {}),
                    expected_duration=action_data.get("expected_duration", 1.0),
                    success_probability=action_data.get("success_probability", 0.8),
                )

                # Use ToolSelector to determine optimal tool for this action
                # Store tool choice in action parameters for later use
                tool_choice = await self._select_tool_for_action(action, goal, context)
                if tool_choice:
                    action.parameters['_tool_choice'] = {
                        'primary_tool': tool_choice.primary_tool.value,
                        'secondary_tools': [t.value for t in tool_choice.secondary_tools],
                        'confidence': tool_choice.confidence,
                        'reasoning': tool_choice.reasoning,
                    }

                actions.append(action)

            return actions

        except Exception as e:
            logger.warning(f"LLM action generation failed: {e}, using fallback")
            return self._fallback_actions(goal, current_state)

    def _fallback_actions(self, goal: str, current_state: str) -> List[PlannedAction]:
        """Fallback action generation without LLM."""
        # Very simple heuristic: suggest common actions
        actions = []

        if "navigate" in goal.lower() or "visit" in goal.lower():
            actions.append(PlannedAction(
                action_type="navigate",
                parameters={"url": "placeholder.com"},
                expected_duration=3.0,
                success_probability=0.9,
            ))

        if "search" in goal.lower() or "find" in goal.lower():
            actions.append(PlannedAction(
                action_type="search",
                parameters={"query": "placeholder"},
                expected_duration=1.5,
                success_probability=0.85,
            ))

        if "extract" in goal.lower() or "get" in goal.lower():
            actions.append(PlannedAction(
                action_type="extract",
                parameters={},
                expected_duration=2.0,
                success_probability=0.8,
            ))

        return actions if actions else [PlannedAction(
            action_type="wait",
            parameters={},
            expected_duration=1.0,
            success_probability=0.99,
        )]

    async def _predict_state(self, current_state: str, action: PlannedAction) -> str:
        """Predict resulting state after executing action."""
        # Simple state prediction
        return f"{current_state} → {action.action_type}({json.dumps(action.parameters)})"

    async def simulate_path(self, path: List[PlannedAction], current_state: str) -> PredictedOutcome:
        """
        Simulate executing a path and predict outcome.

        Args:
            path: Sequence of actions to simulate
            current_state: Starting state

        Returns:
            Predicted outcome
        """
        return await self.world_model.predict_outcome(path, current_state)

    def score_path(
        self,
        path: List[PlannedAction],
        outcome: PredictedOutcome,
        goal: str,
    ) -> float:
        """
        Score a path based on multiple factors.

        Args:
            path: Sequence of actions
            outcome: Predicted outcome
            goal: What we're trying to achieve

        Returns:
            Score (0-1, higher is better)
        """
        # Factor 1: Success probability
        success_score = outcome.success_probability

        # Factor 2: Mission alignment (how well does this serve the goal)
        alignment_score = self._score_mission_alignment(path, goal)

        # Factor 3: Efficiency (fewer steps = better)
        max_steps = 10
        efficiency_score = max(0, 1 - len(path) / max_steps)

        # Factor 4: Uncertainty reduction (more confident = better)
        uncertainty_score = outcome.confidence

        # Weighted combination
        total_score = (
            SCORE_SUCCESS_PROB * success_score +
            SCORE_MISSION_ALIGN * alignment_score +
            SCORE_EFFICIENCY * efficiency_score +
            SCORE_UNCERTAINTY * uncertainty_score
        )

        return total_score

    def _score_mission_alignment(self, path: List[PlannedAction], goal: str) -> float:
        """Score how well path aligns with mission goal."""
        # Simple heuristic: check if action types match goal keywords
        goal_lower = goal.lower()
        relevant_actions = 0

        for action in path:
            if action.action_type.lower() in goal_lower:
                relevant_actions += 1

        if not path:
            return 0.0

        return relevant_actions / len(path)

    async def select_best(self, tree: PlanTree) -> ActionPlan:
        """
        Select best path through planning tree.

        Args:
            tree: Planning tree with all possible paths

        Returns:
            Best action plan
        """
        leaf_nodes = tree.get_leaf_nodes()

        if not leaf_nodes:
            # No complete paths - return empty plan
            logger.warning("No complete paths in tree")
            return ActionPlan(
                plan_id=self._generate_plan_id(),
                goal=tree.goal,
                steps=[],
                expected_outcome=PredictedOutcome(
                    success_probability=0.0,
                    expected_results={},
                    confidence=0.0,
                    failure_modes=["No valid paths found"],
                ),
                confidence=0.0,
                score=0.0,
            )

        # Score all leaf paths
        best_score = -1
        best_leaf = None

        for leaf in leaf_nodes:
            path = leaf.get_path()

            # Simulate outcome
            outcome = await self.simulate_path(path, tree.root.state_description)

            # Score path
            score = self.score_path(path, outcome, tree.goal)

            # Prune low-scoring paths
            if score < PRUNE_MIN_SCORE or outcome.success_probability < PRUNE_MIN_SUCCESS:
                continue

            # Update node score
            leaf.score = score

            if score > best_score:
                best_score = score
                best_leaf = leaf

        if best_leaf is None:
            # All paths pruned - return least-bad option
            logger.warning("All paths pruned, selecting least-bad option")
            best_leaf = max(leaf_nodes, key=lambda n: n.score if n.score > 0 else 0)
            best_score = best_leaf.score

        # Build action plan from best path
        path = best_leaf.get_path()
        outcome = await self.simulate_path(path, tree.root.state_description)

        plan = ActionPlan(
            plan_id=self._generate_plan_id(),
            goal=tree.goal,
            steps=path,
            expected_outcome=outcome,
            confidence=outcome.confidence,
            score=best_score,
        )

        return plan

    async def _generate_contingencies(
        self,
        plan: ActionPlan,
        current_state: str,
        context: Dict[str, Any],
    ):
        """Generate contingency plans for risky steps."""
        # Find high-risk actions (low success probability)
        risky_actions = [
            (i, action) for i, action in enumerate(plan.steps)
            if action.success_probability < 0.7
        ]

        if not risky_actions:
            return

        logger.debug(f"Generating contingencies for {len(risky_actions)} risky actions")

        for step_idx, action in risky_actions[:3]:  # Limit to 3 contingencies
            # Generate alternative plan if this action fails
            contingency_goal = f"Alternative to {action.action_type} (step {step_idx})"

            try:
                # Create contingency plan with lower depth
                contingency = await self.plan(
                    goal=contingency_goal,
                    current_state=current_state,
                    depth=min(3, DEFAULT_DEPTH - 1),
                    context=context,
                )

                contingency.parent_plan = plan.plan_id
                plan.contingencies[f"step_{step_idx}_failed"] = contingency

            except Exception as e:
                logger.warning(f"Failed to generate contingency for step {step_idx}: {e}")

    async def replan(
        self,
        new_observation: str,
        current_plan: Optional[ActionPlan] = None,
    ) -> ActionPlan:
        """
        Replan based on new observation.

        When reality diverges from prediction, we need to replan.

        Args:
            new_observation: What we just observed
            current_plan: Current plan being executed (if any)

        Returns:
            Updated plan
        """
        current_plan = current_plan or self.active_plan

        if not current_plan:
            logger.warning("No current plan to replan from")
            return None

        logger.info(f"Replanning due to: {new_observation}")
        self.replans += 1

        # Check if we have a contingency plan for this situation
        current_step = current_plan.current_step
        contingency_key = f"step_{current_step}_failed"

        if contingency_key in current_plan.contingencies:
            logger.info(f"Using contingency plan: {contingency_key}")
            contingency = current_plan.contingencies[contingency_key]
            self.active_plan = contingency

            # Publish event
            if self.event_bus:
                await self.event_bus.publish(OrganismEvent(
                    event_type=EventType.STRATEGY_UPDATED,
                    source="planner",
                    data={
                        "plan_id": contingency.plan_id,
                        "reason": "contingency_activated",
                        "observation": new_observation,
                    }
                ))

            return contingency

        # No contingency - create new plan from current state
        remaining_goal = current_plan.goal  # Could refine this
        new_state = new_observation

        new_plan = await self.plan(
            goal=remaining_goal,
            current_state=new_state,
            depth=DEFAULT_DEPTH,
        )

        self.active_plan = new_plan

        # Publish event
        if self.event_bus:
            await self.event_bus.publish(OrganismEvent(
                event_type=EventType.STRATEGY_UPDATED,
                source="planner",
                data={
                    "old_plan_id": current_plan.plan_id,
                    "new_plan_id": new_plan.plan_id,
                    "reason": "observation_mismatch",
                    "observation": new_observation,
                }
            ))

        return new_plan

    async def _on_action_complete(self, event: Any):
        """Handle action completion event."""
        if not self.active_plan:
            return

        current_action = self.active_plan.get_current_action()
        if current_action:
            current_action.status = ActionStatus.COMPLETED
            current_action.completed_at = time.time()
            if current_action.started_at:
                current_action.actual_duration = current_action.completed_at - current_action.started_at

        # Advance to next step
        self.active_plan.advance()

        # Check if plan complete
        if self.active_plan.is_complete():
            self.plans_completed += 1
            self.active_plan.completed_at = time.time()
            logger.info(f"Plan {self.active_plan.plan_id} completed successfully")

    async def _on_action_failed(self, event: Any):
        """Handle action failure event."""
        if not self.active_plan:
            return

        current_action = self.active_plan.get_current_action()
        if current_action:
            current_action.status = ActionStatus.FAILED
            current_action.error = event.data.get("error", "Unknown error")

        # Trigger replan
        observation = f"Action {current_action.action_type} failed: {current_action.error}"
        await self.replan(observation)

    async def _on_surprise(self, event: Any):
        """Handle surprise event (unexpected observation)."""
        # Surprises indicate prediction mismatch - consider replanning
        if self.active_plan and self.active_plan.confidence < REPLAN_THRESHOLD:
            observation = event.data.get("message", "Unexpected observation")
            await self.replan(observation)

    def _generate_plan_id(self) -> str:
        """Generate unique plan ID."""
        timestamp = int(time.time() * 1000)
        random_part = hashlib.md5(str(timestamp).encode()).hexdigest()[:8]
        return f"plan_{timestamp}_{random_part}"

    def _get_cache_key(self, goal: str, state: str) -> str:
        """Generate cache key for plan."""
        combined = f"{goal}|{state}"
        return hashlib.md5(combined.encode()).hexdigest()

    def _save_plan(self, plan: ActionPlan):
        """Save plan to database."""
        with self._db_lock:
            try:
                conn = sqlite3.connect(str(PLANNER_DB))
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO plans
                    (plan_id, goal, plan_data, score, confidence, created_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        plan.plan_id,
                        plan.goal,
                        json.dumps(plan.to_dict()),
                        plan.score,
                        plan.confidence,
                        plan.created_at,
                        "active" if plan == self.active_plan else "cached",
                    )
                )

                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Failed to save plan: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get planner statistics."""
        stats = {
            "plans_created": self.plans_created,
            "plans_completed": self.plans_completed,
            "plans_abandoned": self.plans_abandoned,
            "replans": self.replans,
            "cache_size": len(self.plan_cache),
            "active_plan": self.active_plan.plan_id if self.active_plan else None,
            "tool_selections": self.tool_selections,
            "tool_selector_enabled": TOOL_SELECTOR_AVAILABLE and self._tool_selector_initialized,
        }

        # Add tool selector stats if available
        if self.tool_selector and self._tool_selector_initialized:
            try:
                tool_stats = self.tool_selector.get_tool_stats()
                stats["tool_selector_stats"] = tool_stats
            except Exception as e:
                logger.debug(f"Failed to get tool selector stats: {e}")

        return stats


# =============================================================================
# INITIALIZATION
# =============================================================================

async def initialize_planner(
    event_bus: Optional[Any] = None,
    llm_client: Optional[Any] = None,
    uncertainty_tracker: Optional[Any] = None,
    mission_goal: Optional[str] = None,
    tool_selector: Optional[Any] = None,
    config: Optional[Dict] = None,
) -> Planner:
    """
    Initialize planner with dependencies.

    Args:
        event_bus: EventBus instance
        llm_client: LLM client instance
        uncertainty_tracker: UncertaintyTracker instance
        mission_goal: Mission goal for alignment scoring
        tool_selector: ToolSelector instance for intelligent routing
        config: Configuration dictionary

    Returns:
        Initialized Planner instance
    """
    planner = Planner(
        event_bus=event_bus,
        llm_client=llm_client,
        uncertainty_tracker=uncertainty_tracker,
        mission_goal=mission_goal,
        tool_selector=tool_selector,
        config=config,
    )

    # Initialize tool selector if provided
    if tool_selector and TOOL_SELECTOR_AVAILABLE:
        try:
            await planner._ensure_tool_selector()
            logger.info("Planner initialized with ToolSelector integration")
        except Exception as e:
            logger.warning(f"Failed to initialize ToolSelector integration: {e}")
    else:
        logger.info("Planner initialized without ToolSelector")

    logger.info("Planner initialized and ready")
    return planner


# =============================================================================
# STANDALONE USAGE
# =============================================================================

async def main():
    """Standalone test."""
    from .llm_client import LLMClient
    from .organism_core import EventBus

    # Create dependencies
    event_bus = EventBus()

    # Load config
    config_path = Path("config/config.yaml")
    if config_path.exists():
        import yaml
        config = yaml.safe_load(config_path.read_text())
    else:
        config = {}

    llm_client = LLMClient(config)

    # Initialize ToolSelector if available
    tool_selector = None
    if TOOL_SELECTOR_AVAILABLE:
        try:
            from .tool_selector import create_tool_selector
            tool_selector = create_tool_selector(
                event_bus=event_bus,
                config=config
            )
            logger.info("ToolSelector created for testing")
        except Exception as e:
            logger.warning(f"Failed to create ToolSelector: {e}")

    # Initialize planner
    planner = await initialize_planner(
        event_bus=event_bus,
        llm_client=llm_client,
        mission_goal="Test planning capabilities",
        tool_selector=tool_selector,
        config=config,
    )

    # Test planning
    plan = await planner.plan(
        goal="Find Python books on books.toscrape.com",
        current_state="Browser ready, no page loaded",
        depth=5,
        context={"tools": ["navigate", "search", "extract", "click"]},
    )

    print(f"\nGenerated Plan: {plan.plan_id}")
    print(f"Goal: {plan.goal}")
    print(f"Steps: {len(plan.steps)}")
    print(f"Confidence: {plan.confidence:.2f}")
    print(f"Score: {plan.score:.2f}")
    print(f"\nAction Sequence:")
    for i, action in enumerate(plan.steps):
        print(f"  {i+1}. {action.action_type}({json.dumps(action.parameters)})")
        print(f"     Success prob: {action.success_probability:.2f}, Duration: {action.expected_duration}s")

    print(f"\nExpected Outcome:")
    print(f"  Success probability: {plan.expected_outcome.success_probability:.2f}")
    print(f"  Confidence: {plan.expected_outcome.confidence:.2f}")
    if plan.expected_outcome.failure_modes:
        print(f"  Potential failures: {', '.join(plan.expected_outcome.failure_modes)}")

    # Test replanning
    print(f"\nSimulating action failure...")
    plan.active_plan = plan
    new_plan = await planner.replan(
        new_observation="Search box not found on page",
        current_plan=plan,
    )

    print(f"\nReplanned: {new_plan.plan_id}")
    print(f"New steps: {len(new_plan.steps)}")

    # Stats
    print(f"\nPlanner Stats:")
    stats = planner.get_stats()
    for key, value in stats.items():
        if key == "tool_selector_stats":
            print(f"  {key}:")
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    print(f"    {sub_key}: {sub_value}")
        else:
            print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
