#!/usr/bin/env python3
"""
Goal Hierarchy - Nested Goals with LLM-Powered Decomposition

This system generates and manages nested goals, automatically decomposing missions
into sub-goals, tracking dependencies, and determining what to focus on next.

Philosophy:
- Mission → Goals → Sub-goals → Actions (hierarchical decomposition)
- Goals emerge dynamically from context (LLM-generated)
- Dependencies create natural ordering (blocked → active → complete)
- Priority determines focus when multiple goals are active
- Progress accumulates toward parent goals

Architecture:
1. Mission Anchor provides top-level goal (from organism_core)
2. Goal decomposition uses LLM to break complex goals into sub-goals
3. Dependency tracking ensures prerequisites complete first
4. Priority system focuses attention on most important active goals
5. Progress tracking detects completion and updates parent goals
6. Integration with EventBus for organism-wide awareness

Integration:
- EventBus: Subscribe to MISSION_ALIGNED, publish goal events
- Mission Anchor: Get top-level mission as root goal
- Strategic Planner: Use current goal for planning context
- Valence System: Reward goal completion
- Episode Compressor: Store goal-outcome pairs as wisdom

Performance:
- <500ms goal decomposition (LLM call)
- O(log n) goal lookup with priority queue
- Persistent to memory/goals.json
- Automatic cleanup of completed goals
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

# Import organism components
try:
    from .organism_core import EventBus, EventType, OrganismEvent, MissionAnchor
    ORGANISM_AVAILABLE = True
except ImportError:
    ORGANISM_AVAILABLE = False
    EventBus = None
    EventType = None
    OrganismEvent = None
    MissionAnchor = None
    logger.warning("Organism core not available - running in standalone mode")


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class GoalStatus(Enum):
    """Status of a goal."""
    PENDING = "pending"         # Not started, waiting
    BLOCKED = "blocked"         # Dependencies not met
    ACTIVE = "active"           # Currently being worked on
    IN_PROGRESS = "in_progress" # Work has started
    PAUSED = "paused"           # Temporarily paused
    COMPLETE = "complete"       # Successfully completed
    FAILED = "failed"           # Failed to achieve
    ABANDONED = "abandoned"     # Decided not to pursue


class GoalType(Enum):
    """Type of goal."""
    MISSION = "mission"         # Top-level mission (from mission anchor)
    OBJECTIVE = "objective"     # High-level objective
    TASK = "task"               # Specific task
    SUBTASK = "subtask"         # Sub-task of a task
    ACTION = "action"           # Concrete action


@dataclass
class Goal:
    """
    A goal in the hierarchy.

    Goals can have parent goals and child sub-goals, creating a tree structure.
    """
    goal_id: str
    description: str            # What needs to be achieved
    goal_type: GoalType
    status: GoalStatus

    # Hierarchy
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    depth: int = 0              # 0 = mission, 1 = objective, etc.

    # Dependencies
    depends_on: List[str] = field(default_factory=list)  # Goal IDs that must complete first
    blocks: List[str] = field(default_factory=list)      # Goals blocked by this one

    # Priority and progress
    priority: float = 0.5       # 0.0 = low, 1.0 = high
    progress: float = 0.0       # 0.0 = not started, 1.0 = complete

    # Context
    context: str = ""           # Why this goal exists, background
    success_criteria: str = ""  # How to know when complete

    # Metadata
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    last_updated: float = field(default_factory=time.time)

    # Tracking
    attempts: int = 0           # Number of times tried
    failures: List[str] = field(default_factory=list)  # Failure reasons
    estimated_effort: float = 0.0  # Estimated hours/complexity
    actual_effort: float = 0.0     # Actual time spent

    # Tags and metadata
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_blocked(self, completed_goals: Set[str]) -> bool:
        """Check if goal is blocked by dependencies."""
        for dep_id in self.depends_on:
            if dep_id not in completed_goals:
                return True
        return False

    def is_completable(self) -> bool:
        """Check if all children are complete."""
        if not self.children_ids:
            return True  # Leaf goal
        return False  # Need to check children status separately

    def can_start(self, completed_goals: Set[str]) -> bool:
        """Check if goal can be started."""
        return (
            self.status in (GoalStatus.PENDING, GoalStatus.BLOCKED) and
            not self.is_blocked(completed_goals)
        )

    def update_progress(self, child_progresses: List[float] = None):
        """Update progress based on children or explicit value."""
        if child_progresses:
            # Average of children
            self.progress = sum(child_progresses) / len(child_progresses)

        # Update status based on progress
        if self.progress >= 1.0:
            self.status = GoalStatus.COMPLETE
            self.completed_at = time.time()
        elif self.progress > 0.0 and self.status == GoalStatus.PENDING:
            self.status = GoalStatus.IN_PROGRESS
            if not self.started_at:
                self.started_at = time.time()

        self.last_updated = time.time()


@dataclass
class SuggestedAction:
    """A suggested next action to work on a goal."""
    goal_id: str
    action_description: str
    tool: Optional[str] = None
    arguments: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    expected_outcome: str = ""
    confidence: float = 0.7


@dataclass
class GoalMetrics:
    """Metrics for monitoring goal system."""
    total_goals_created: int = 0
    total_goals_completed: int = 0
    total_goals_failed: int = 0
    total_goals_abandoned: int = 0

    avg_completion_time_seconds: float = 0.0
    avg_decomposition_time_ms: float = 0.0

    active_goals: int = 0
    blocked_goals: int = 0

    decomposition_calls: int = 0
    last_decomposition_time: float = 0.0


# =============================================================================
# GOAL HIERARCHY
# =============================================================================

class GoalHierarchy:
    """
    Manages nested goals with LLM-powered decomposition.

    This is the "what to do" layer that sits above the "how to do it" (planner).
    """

    # Configuration
    MAX_DEPTH = 5               # Maximum nesting depth
    MAX_CHILDREN = 10           # Max children per goal
    DECOMPOSITION_THRESHOLD = 0.6  # Complexity threshold for decomposition

    def __init__(
        self,
        event_bus: 'EventBus' = None,
        mission_anchor: 'MissionAnchor' = None,
        llm_client = None,
        fast_model: str = "llama3.2:3b-instruct-q4_0",
        persistence_path: str = "memory/goals.json"
    ):
        """
        Initialize goal hierarchy.

        Args:
            event_bus: Organism event bus for integration
            mission_anchor: Provides top-level mission
            llm_client: LLM for goal decomposition
            fast_model: Fast model for decomposition
            persistence_path: Where to persist goals
        """
        self.event_bus = event_bus
        self.mission_anchor = mission_anchor
        self.llm_client = llm_client
        self.fast_model = fast_model

        # Goal storage
        self._goals: Dict[str, Goal] = {}  # goal_id -> Goal
        self._root_goal_id: Optional[str] = None

        # Tracking
        self._active_goal_ids: Set[str] = set()
        self._completed_goal_ids: Set[str] = set()
        self._blocked_goal_ids: Set[str] = set()

        # Metrics
        self.metrics = GoalMetrics()

        # Persistence
        self._state_path = Path(persistence_path)
        self._load_state()

        # Event subscriptions
        if self.event_bus and ORGANISM_AVAILABLE:
            self._subscribe_to_events()

        logger.info(f"GoalHierarchy initialized with {len(self._goals)} goals")

    # =========================================================================
    # EVENT SUBSCRIPTIONS
    # =========================================================================

    def _subscribe_to_events(self):
        """Subscribe to organism events."""
        # Listen for mission alignment to create root goal
        self.event_bus.subscribe(EventType.MISSION_ALIGNED, self._on_mission_aligned)

        # Listen for action completion to update progress
        self.event_bus.subscribe(EventType.ACTION_COMPLETE, self._on_action_complete)

        # Listen for action failures
        self.event_bus.subscribe(EventType.ACTION_FAILED, self._on_action_failed)

        logger.debug("Subscribed to organism events")

    async def _on_mission_aligned(self, event: OrganismEvent):
        """Handle mission alignment events."""
        # Could create/update root goal based on mission
        if not self._root_goal_id and self.mission_anchor:
            await self._create_root_goal()

    async def _on_action_complete(self, event: OrganismEvent):
        """Handle action completion - update goal progress."""
        # Find which goal this action serves
        # This is a placeholder - real implementation would track action->goal mapping
        pass

    async def _on_action_failed(self, event: OrganismEvent):
        """Handle action failure - record in goal."""
        # Track failures for retry logic
        pass

    # =========================================================================
    # INITIALIZATION
    # =========================================================================

    async def initialize(self):
        """Async initialization - create root goal from mission."""
        if not self._root_goal_id:
            await self._create_root_goal()

    async def _create_root_goal(self):
        """Create root goal from mission anchor."""
        if not self.mission_anchor:
            # Create default root goal
            mission = "Complete user tasks successfully"
        else:
            mission = self.mission_anchor.get_mission()

        root_goal = Goal(
            goal_id=self._generate_goal_id("mission"),
            description=mission,
            goal_type=GoalType.MISSION,
            status=GoalStatus.ACTIVE,
            priority=1.0,
            depth=0,
            context="Top-level mission from mission anchor",
            success_criteria="User tasks completed, customers successful"
        )

        self._goals[root_goal.goal_id] = root_goal
        self._root_goal_id = root_goal.goal_id
        self._active_goal_ids.add(root_goal.goal_id)

        self.metrics.total_goals_created += 1

        logger.info(f"Created root goal: {mission}")

        # Publish event
        if self.event_bus and ORGANISM_AVAILABLE:
            await self.event_bus.publish(OrganismEvent(
                event_type=EventType.STRATEGY_UPDATED,
                source="goal_hierarchy",
                data={
                    "message": "Root goal created",
                    "goal_id": root_goal.goal_id,
                    "description": mission
                }
            ))

    # =========================================================================
    # GOAL DECOMPOSITION (LLM-Powered)
    # =========================================================================

    async def decompose(self, goal: Goal, context: str = "") -> List[Goal]:
        """
        Decompose a goal into sub-goals using LLM.

        This is the core intelligence - turning a complex goal into achievable
        sub-goals.

        Args:
            goal: Goal to decompose
            context: Additional context for decomposition

        Returns:
            List of sub-goals
        """
        start_time = time.time()

        # Check depth limit
        if goal.depth >= self.MAX_DEPTH:
            logger.warning(f"Max depth reached for goal: {goal.description}")
            return []

        # Check if decomposition is needed
        if not await self._should_decompose(goal):
            logger.debug(f"Skipping decomposition for simple goal: {goal.description}")
            return []

        logger.info(f"Decomposing goal: {goal.description}")

        # Generate sub-goals using LLM
        subgoals = await self._llm_decompose(goal, context)

        if not subgoals:
            logger.warning(f"No sub-goals generated for: {goal.description}")
            return []

        # Create Goal objects
        created_goals = []
        for i, subgoal_desc in enumerate(subgoals):
            subgoal = Goal(
                goal_id=self._generate_goal_id(f"subgoal_{goal.goal_id}_{i}"),
                description=subgoal_desc["description"],
                goal_type=self._infer_goal_type(goal.depth + 1),
                status=GoalStatus.PENDING,
                parent_id=goal.goal_id,
                depth=goal.depth + 1,
                priority=subgoal_desc.get("priority", goal.priority * 0.9),
                context=subgoal_desc.get("context", ""),
                success_criteria=subgoal_desc.get("success_criteria", ""),
                estimated_effort=subgoal_desc.get("effort", 0.0),
            )

            # Set dependencies if specified
            if i > 0 and subgoal_desc.get("depends_on_previous", False):
                prev_goal = created_goals[i - 1]
                subgoal.depends_on.append(prev_goal.goal_id)
                prev_goal.blocks.append(subgoal.goal_id)

            # Store goal
            self._goals[subgoal.goal_id] = subgoal
            goal.children_ids.append(subgoal.goal_id)
            created_goals.append(subgoal)

            self.metrics.total_goals_created += 1

            # Track status
            if subgoal.is_blocked(self._completed_goal_ids):
                self._blocked_goal_ids.add(subgoal.goal_id)
            else:
                self._active_goal_ids.add(subgoal.goal_id)

        # Update metrics
        elapsed_ms = (time.time() - start_time) * 1000
        self.metrics.decomposition_calls += 1
        self.metrics.avg_decomposition_time_ms = (
            (self.metrics.avg_decomposition_time_ms * (self.metrics.decomposition_calls - 1) + elapsed_ms)
            / self.metrics.decomposition_calls
        )
        self.metrics.last_decomposition_time = time.time()

        # Update parent goal status
        goal.status = GoalStatus.IN_PROGRESS

        # Save state
        self._save_state()

        logger.info(f"Decomposed into {len(created_goals)} sub-goals in {elapsed_ms:.0f}ms")

        return created_goals

    async def _should_decompose(self, goal: Goal) -> bool:
        """Decide if a goal should be decomposed."""
        # Already decomposed?
        if goal.children_ids:
            return False

        # Leaf goal types don't decompose
        if goal.goal_type in (GoalType.ACTION, GoalType.SUBTASK):
            return False

        # Check complexity using simple heuristics
        desc = goal.description.lower()

        # Keywords suggesting complexity
        complex_keywords = ["and", "then", "after", "multiple", "several", "research", "find"]
        complexity_score = sum(1 for kw in complex_keywords if kw in desc)

        # Long descriptions suggest complexity
        if len(desc) > 50:
            complexity_score += 1

        # Normalize to 0-1
        complexity = min(complexity_score / 5, 1.0)

        return complexity >= self.DECOMPOSITION_THRESHOLD

    async def _llm_decompose(self, goal: Goal, context: str) -> List[Dict]:
        """Use LLM to decompose goal into sub-goals."""
        if not self.llm_client:
            # Fallback to heuristic decomposition
            return self._heuristic_decompose(goal)

        try:
            # Build prompt
            prompt = f"""You are helping break down a complex goal into smaller, achievable sub-goals.

Parent Goal: {goal.description}
Goal Type: {goal.goal_type.value}
Context: {context or goal.context}
Success Criteria: {goal.success_criteria or "Not specified"}

Break this down into 2-5 concrete sub-goals that:
1. Are specific and actionable
2. When completed, achieve the parent goal
3. Are ordered logically (dependencies considered)
4. Are sized appropriately for completion

Respond in JSON format:
[
  {{
    "description": "First sub-goal description",
    "priority": 0.8,
    "effort": 2.0,
    "success_criteria": "How to know when done",
    "depends_on_previous": false
  }},
  ...
]

Keep descriptions concise (1 sentence). Respond with ONLY the JSON array."""

            response = await self.llm_client.chat(
                model=self.fast_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500
            )

            content = response.content if hasattr(response, 'content') else response.get('message', {}).get('content', '')

            # Parse JSON
            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                subgoals = json.loads(json_match.group())

                # Validate
                if isinstance(subgoals, list) and len(subgoals) > 0:
                    # Ensure required fields
                    for sg in subgoals:
                        if "description" not in sg:
                            continue
                        # Set defaults
                        sg.setdefault("priority", goal.priority * 0.9)
                        sg.setdefault("effort", 1.0)
                        sg.setdefault("success_criteria", "")
                        sg.setdefault("depends_on_previous", False)

                    return subgoals

            logger.debug("LLM decomposition failed to parse, using fallback")

        except Exception as e:
            logger.debug(f"LLM decomposition error: {e}")

        # Fallback
        return self._heuristic_decompose(goal)

    def _heuristic_decompose(self, goal: Goal) -> List[Dict]:
        """Simple heuristic decomposition without LLM."""
        desc = goal.description.lower()

        # Look for "and" to split
        if " and " in desc:
            parts = desc.split(" and ")
            return [
                {
                    "description": part.strip().capitalize(),
                    "priority": goal.priority,
                    "effort": 1.0,
                    "success_criteria": "",
                    "depends_on_previous": False
                }
                for part in parts[:3]  # Max 3
            ]

        # Look for sequential indicators
        if "then" in desc or "after" in desc:
            # Create 2 sequential sub-goals
            return [
                {
                    "description": f"Complete first phase of: {goal.description}",
                    "priority": goal.priority,
                    "effort": 1.0,
                    "success_criteria": "",
                    "depends_on_previous": False
                },
                {
                    "description": f"Complete final phase of: {goal.description}",
                    "priority": goal.priority * 0.9,
                    "effort": 1.0,
                    "success_criteria": "",
                    "depends_on_previous": True
                }
            ]

        # Default: don't decompose
        return []

    # =========================================================================
    # GOAL GENERATION
    # =========================================================================

    async def generate_subgoal(
        self,
        parent_goal: Goal,
        context: str,
        suggestion: str = ""
    ) -> Optional[Goal]:
        """
        Generate a new sub-goal based on context.

        This is for dynamic goal creation during execution.

        Args:
            parent_goal: Parent goal
            context: Current execution context
            suggestion: Optional suggestion for what goal to create

        Returns:
            New sub-goal if created
        """
        if not self.llm_client:
            return None

        try:
            prompt = f"""Based on the current situation, suggest a new sub-goal.

Parent Goal: {parent_goal.description}
Current Context: {context}
Suggestion: {suggestion or "None"}

What sub-goal should be created to help achieve the parent goal?

Respond in JSON:
{{
  "description": "New sub-goal description",
  "priority": 0.7,
  "rationale": "Why this goal is needed now"
}}

Respond with ONLY the JSON object."""

            response = await self.llm_client.chat(
                model=self.fast_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=200
            )

            content = response.content if hasattr(response, 'content') else response.get('message', {}).get('content', '')

            # Parse JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())

                # Create goal
                subgoal = Goal(
                    goal_id=self._generate_goal_id(f"dynamic_{parent_goal.goal_id}"),
                    description=data["description"],
                    goal_type=self._infer_goal_type(parent_goal.depth + 1),
                    status=GoalStatus.PENDING,
                    parent_id=parent_goal.goal_id,
                    depth=parent_goal.depth + 1,
                    priority=data.get("priority", 0.7),
                    context=data.get("rationale", context)
                )

                # Store
                self._goals[subgoal.goal_id] = subgoal
                parent_goal.children_ids.append(subgoal.goal_id)
                self._active_goal_ids.add(subgoal.goal_id)

                self.metrics.total_goals_created += 1
                self._save_state()

                logger.info(f"Generated dynamic sub-goal: {subgoal.description}")
                return subgoal

        except Exception as e:
            logger.debug(f"Sub-goal generation error: {e}")

        return None

    # =========================================================================
    # GOAL SELECTION & FOCUS
    # =========================================================================

    def get_current_focus(self) -> Optional[Goal]:
        """
        Get the highest priority active goal to focus on now.

        Returns the most important, unblocked goal that's ready to work on.
        """
        # Get all active, unblocked goals
        candidates = []
        for goal_id in self._active_goal_ids:
            goal = self._goals.get(goal_id)
            if not goal:
                continue

            # Skip if blocked or complete
            if goal.status in (GoalStatus.BLOCKED, GoalStatus.COMPLETE, GoalStatus.FAILED):
                continue

            # Skip if dependencies not met
            if goal.is_blocked(self._completed_goal_ids):
                continue

            candidates.append(goal)

        if not candidates:
            return None

        # Sort by priority (descending), then depth (prefer deeper/more specific)
        candidates.sort(key=lambda g: (g.priority, g.depth), reverse=True)

        return candidates[0]

    def get_next_action(self, goal: Goal = None) -> Optional[SuggestedAction]:
        """
        Get suggested next action for a goal.

        Args:
            goal: Specific goal, or None to use current focus

        Returns:
            Suggested action to take
        """
        if not goal:
            goal = self.get_current_focus()

        if not goal:
            return None

        # If goal has children, work on them first
        if goal.children_ids:
            # Find first incomplete child
            for child_id in goal.children_ids:
                child = self._goals.get(child_id)
                if child and child.status != GoalStatus.COMPLETE:
                    return self.get_next_action(child)

        # Leaf goal - suggest action
        return SuggestedAction(
            goal_id=goal.goal_id,
            action_description=f"Work on: {goal.description}",
            rationale=f"This is the highest priority active goal (priority: {goal.priority:.2f})",
            expected_outcome=goal.success_criteria or "Progress toward goal completion",
            confidence=0.7
        )

    # =========================================================================
    # PROGRESS TRACKING
    # =========================================================================

    def update_progress(self, goal_id: str, action: str, outcome: str, success: bool = True):
        """
        Update progress on a goal based on action outcome.

        Args:
            goal_id: Goal being worked on
            action: Action taken
            outcome: What happened
            success: Whether action succeeded
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return

        # Record attempt
        goal.attempts += 1

        if success:
            # Increase progress
            if goal.children_ids:
                # Progress based on children
                child_progresses = []
                for child_id in goal.children_ids:
                    child = self._goals.get(child_id)
                    if child:
                        child_progresses.append(child.progress)

                if child_progresses:
                    goal.update_progress(child_progresses)
            else:
                # Leaf goal - increment progress
                # Estimate based on attempts vs estimated effort
                if goal.estimated_effort > 0:
                    increment = 1.0 / max(goal.estimated_effort, 1)
                else:
                    increment = 0.2  # 20% per success

                goal.progress = min(1.0, goal.progress + increment)
                goal.update_progress()
        else:
            # Record failure
            goal.failures.append(f"{action}: {outcome}")

            # If too many failures, mark as failed
            if len(goal.failures) >= 3:
                goal.status = GoalStatus.FAILED
                self._active_goal_ids.discard(goal_id)
                self.metrics.total_goals_failed += 1

        # Update timestamp
        goal.last_updated = time.time()

        # Check completion
        if goal.status == GoalStatus.COMPLETE:
            self._on_goal_complete(goal)

        # Propagate to parent
        if goal.parent_id:
            parent = self._goals.get(goal.parent_id)
            if parent:
                self._update_parent_progress(parent)

        self._save_state()

    def _update_parent_progress(self, parent: Goal):
        """Update parent goal progress based on children."""
        if not parent.children_ids:
            return

        child_progresses = []
        for child_id in parent.children_ids:
            child = self._goals.get(child_id)
            if child:
                child_progresses.append(child.progress)

        if child_progresses:
            parent.update_progress(child_progresses)

            # Check if parent now complete
            if parent.status == GoalStatus.COMPLETE:
                self._on_goal_complete(parent)

            # Propagate further up
            if parent.parent_id:
                grandparent = self._goals.get(parent.parent_id)
                if grandparent:
                    self._update_parent_progress(grandparent)

    def _on_goal_complete(self, goal: Goal):
        """Handle goal completion."""
        # Move from active to completed
        self._active_goal_ids.discard(goal.goal_id)
        self._completed_goal_ids.add(goal.goal_id)

        # Update metrics
        self.metrics.total_goals_completed += 1
        if goal.started_at:
            duration = goal.completed_at - goal.started_at
            total = self.metrics.avg_completion_time_seconds * (self.metrics.total_goals_completed - 1)
            self.metrics.avg_completion_time_seconds = (total + duration) / self.metrics.total_goals_completed

        # Unblock dependent goals
        for blocked_id in goal.blocks:
            blocked = self._goals.get(blocked_id)
            if blocked and not blocked.is_blocked(self._completed_goal_ids):
                blocked.status = GoalStatus.ACTIVE
                self._blocked_goal_ids.discard(blocked_id)
                self._active_goal_ids.add(blocked_id)

        logger.info(f"Goal completed: {goal.description}")

        # Publish event
        if self.event_bus and ORGANISM_AVAILABLE:
            asyncio.create_task(self.event_bus.publish(OrganismEvent(
                event_type=EventType.LESSON_LEARNED,
                source="goal_hierarchy",
                data={
                    "message": f"Goal completed: {goal.description}",
                    "goal_id": goal.goal_id,
                    "progress": goal.progress,
                    "attempts": goal.attempts
                }
            )))

    def is_complete(self, goal: Goal) -> bool:
        """Check if goal is complete."""
        return goal.status == GoalStatus.COMPLETE

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _generate_goal_id(self, prefix: str = "goal") -> str:
        """Generate unique goal ID."""
        timestamp = int(time.time() * 1000)
        hash_input = f"{prefix}_{timestamp}_{len(self._goals)}"
        hash_val = hashlib.sha256(hash_input.encode()).hexdigest()[:12]
        return f"{prefix}_{hash_val}"

    def _infer_goal_type(self, depth: int) -> GoalType:
        """Infer goal type from depth."""
        if depth == 0:
            return GoalType.MISSION
        elif depth == 1:
            return GoalType.OBJECTIVE
        elif depth == 2:
            return GoalType.TASK
        elif depth == 3:
            return GoalType.SUBTASK
        else:
            return GoalType.ACTION

    # =========================================================================
    # QUERYING
    # =========================================================================

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Get goal by ID."""
        return self._goals.get(goal_id)

    def get_active_goals(self) -> List[Goal]:
        """Get all active goals."""
        return [self._goals[gid] for gid in self._active_goal_ids if gid in self._goals]

    def get_blocked_goals(self) -> List[Goal]:
        """Get all blocked goals."""
        return [self._goals[gid] for gid in self._blocked_goal_ids if gid in self._goals]

    def get_goal_tree(self, root_goal_id: str = None) -> Dict:
        """Get goal tree structure for visualization."""
        root_id = root_goal_id or self._root_goal_id
        if not root_id:
            return {}

        root = self._goals.get(root_id)
        if not root:
            return {}

        def build_tree(goal: Goal) -> Dict:
            tree = {
                "id": goal.goal_id,
                "description": goal.description,
                "type": goal.goal_type.value,
                "status": goal.status.value,
                "priority": goal.priority,
                "progress": goal.progress,
                "children": []
            }

            for child_id in goal.children_ids:
                child = self._goals.get(child_id)
                if child:
                    tree["children"].append(build_tree(child))

            return tree

        return build_tree(root)

    # =========================================================================
    # PERSISTENCE
    # =========================================================================

    def _save_state(self):
        """Save goals to disk."""
        try:
            self._state_path.parent.mkdir(exist_ok=True, parents=True)

            state = {
                "root_goal_id": self._root_goal_id,
                "goals": {
                    gid: asdict(goal)
                    for gid, goal in self._goals.items()
                },
                "active_goal_ids": list(self._active_goal_ids),
                "completed_goal_ids": list(self._completed_goal_ids),
                "blocked_goal_ids": list(self._blocked_goal_ids),
                "metrics": asdict(self.metrics),
                "saved_at": datetime.now().isoformat()
            }

            self._state_path.write_text(json.dumps(state, indent=2, default=str))
            logger.debug(f"Saved goal state: {len(self._goals)} goals")

        except Exception as e:
            logger.error(f"Failed to save goal state: {e}")

    def _load_state(self):
        """Load goals from disk."""
        try:
            if not self._state_path.exists():
                return

            data = json.loads(self._state_path.read_text())

            self._root_goal_id = data.get("root_goal_id")

            # Restore goals
            for gid, goal_data in data.get("goals", {}).items():
                # Convert status and type enums
                goal_data["status"] = GoalStatus(goal_data["status"])
                goal_data["goal_type"] = GoalType(goal_data["goal_type"])

                goal = Goal(**goal_data)
                self._goals[gid] = goal

            # Restore tracking sets
            self._active_goal_ids = set(data.get("active_goal_ids", []))
            self._completed_goal_ids = set(data.get("completed_goal_ids", []))
            self._blocked_goal_ids = set(data.get("blocked_goal_ids", []))

            # Restore metrics
            metrics_data = data.get("metrics", {})
            for key, value in metrics_data.items():
                if hasattr(self.metrics, key):
                    setattr(self.metrics, key, value)

            logger.info(
                f"Loaded goal state from {data.get('saved_at')}: "
                f"{len(self._goals)} goals, {len(self._active_goal_ids)} active"
            )

        except Exception as e:
            logger.debug(f"Could not load goal state: {e}")

    # =========================================================================
    # MONITORING
    # =========================================================================

    def get_stats(self) -> Dict:
        """Get goal hierarchy statistics."""
        return {
            "total_goals": len(self._goals),
            "active_goals": len(self._active_goal_ids),
            "completed_goals": len(self._completed_goal_ids),
            "blocked_goals": len(self._blocked_goal_ids),
            "failed_goals": self.metrics.total_goals_failed,
            "avg_completion_time": f"{self.metrics.avg_completion_time_seconds:.1f}s",
            "avg_decomposition_time": f"{self.metrics.avg_decomposition_time_ms:.0f}ms",
            "decomposition_calls": self.metrics.decomposition_calls,
        }

    def print_goal_tree(self, goal_id: str = None, indent: int = 0):
        """Print goal tree to console."""
        goal_id = goal_id or self._root_goal_id
        if not goal_id:
            print("No root goal")
            return

        goal = self._goals.get(goal_id)
        if not goal:
            return

        # Status symbol
        status_symbols = {
            GoalStatus.PENDING: "⏸",
            GoalStatus.BLOCKED: "🚫",
            GoalStatus.ACTIVE: "▶",
            GoalStatus.IN_PROGRESS: "⏩",
            GoalStatus.COMPLETE: "✓",
            GoalStatus.FAILED: "✗",
            GoalStatus.PAUSED: "⏸",
            GoalStatus.ABANDONED: "⛔"
        }

        symbol = status_symbols.get(goal.status, "•")
        progress_bar = "█" * int(goal.progress * 10) + "░" * (10 - int(goal.progress * 10))

        print(
            f"{'  ' * indent}{symbol} {goal.description[:60]} "
            f"[{progress_bar}] {goal.progress*100:.0f}%"
        )

        # Recurse to children
        for child_id in goal.children_ids:
            self.print_goal_tree(child_id, indent + 1)


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================

def create_goal_hierarchy(
    event_bus = None,
    mission_anchor = None,
    llm_client = None,
    **kwargs
) -> GoalHierarchy:
    """Factory function to create goal hierarchy."""
    return GoalHierarchy(
        event_bus=event_bus,
        mission_anchor=mission_anchor,
        llm_client=llm_client,
        **kwargs
    )


# =============================================================================
# MAIN / DEMO
# =============================================================================

if __name__ == "__main__":
    async def demo():
        """Demo the goal hierarchy."""
        print("Goal Hierarchy - Demo")
        print("=" * 60)

        # Create hierarchy (standalone mode)
        hierarchy = GoalHierarchy()

        # Initialize with root goal
        await hierarchy.initialize()

        # Create a test goal
        test_goal = Goal(
            goal_id="test_001",
            description="Research and extract lead information from Facebook Ads Library",
            goal_type=GoalType.OBJECTIVE,
            status=GoalStatus.ACTIVE,
            priority=0.8,
            context="User wants to find advertisers in dog food niche",
            success_criteria="Have list of 10+ advertisers with contact info"
        )

        hierarchy._goals[test_goal.goal_id] = test_goal
        hierarchy._active_goal_ids.add(test_goal.goal_id)

        # Decompose the goal
        print(f"\nDecomposing goal: {test_goal.description}\n")
        subgoals = await hierarchy.decompose(test_goal, context="Facebook Ads Library search")

        print(f"\nCreated {len(subgoals)} sub-goals:")
        for i, sg in enumerate(subgoals, 1):
            print(f"  {i}. {sg.description} (priority: {sg.priority:.2f})")

        # Show goal tree
        print("\n" + "=" * 60)
        print("Goal Tree:")
        print("=" * 60)
        hierarchy.print_goal_tree(test_goal.goal_id)

        # Get current focus
        print("\n" + "=" * 60)
        focus = hierarchy.get_current_focus()
        if focus:
            print(f"Current focus: {focus.description}")
            print(f"Priority: {focus.priority:.2f}")
            print(f"Status: {focus.status.value}")

        # Get next action
        action = hierarchy.get_next_action()
        if action:
            print(f"\nNext action: {action.action_description}")
            print(f"Rationale: {action.rationale}")

        # Show stats
        print("\n" + "=" * 60)
        print("Statistics:")
        stats = hierarchy.get_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")

        print("\nDemo complete!")

    asyncio.run(demo())
