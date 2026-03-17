#!/usr/bin/env python3
"""
Dream Engine - Mental Simulation Without Acting

This is the organism's rehearsal mechanism. Humans mentally simulate scenarios
before acting ("what if..."). Dreams consolidate learning and test edge cases.
An agent that can simulate without consequences learns faster and safer.

Purpose:
- Rehearse scenarios without real-world consequences
- Test learned patterns against edge cases
- Discover failure modes before they occur
- Consolidate learning during sleep
- Build a world model of how things work

Architecture:
    Gap Detector Surprises → Generate Scenarios → Dry Run Simulation →
    Predict Outcome → Learn from Simulation → Store Preemptive Lessons

Dream Types:
1. Failure Rehearsal - What if this failed? How would we handle it?
2. Edge Case Exploration - What weird inputs could we get?
3. Optimization Dreams - Could we have done that better?
4. Threat Simulation - What attacks might we face?
5. Novel Situation Prep - What if something completely new happened?

Integration:
- Called by sleep_cycle during Phase 5
- Uses gap_detector surprises as dream seeds
- Stores lessons in memory_architecture
- Updates world_model from experience
- Publishes LESSON_LEARNED events when insights found

References:
- Cognitive science: sleep consolidation, mental rehearsal
- Active Inference: counterfactual reasoning
- AlphaGo: Monte Carlo Tree Search (mental simulation)
- Human motor learning: mental practice improves performance
"""

import asyncio
import time
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from loguru import logger
from collections import defaultdict, deque
import random

# Optional: LLM for simulation
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("Ollama not available - dreams will use heuristic simulation")


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class DreamType(Enum):
    """Types of dream scenarios."""
    FAILURE_REHEARSAL = "failure_rehearsal"        # What if this failed?
    EDGE_CASE = "edge_case"                        # What weird inputs could we get?
    OPTIMIZATION = "optimization"                  # Could we do better?
    THREAT_SIMULATION = "threat_simulation"        # What attacks might we face?
    NOVEL_SITUATION = "novel_situation"            # What if something new happened?
    RECOVERY_TEST = "recovery_test"                # Can we recover from this?


@dataclass
class Scenario:
    """A 'what-if' scenario to simulate."""
    scenario_id: str
    description: str
    context: Dict[str, Any]
    trigger: str                    # What surprise triggered this scenario
    variation: str                  # How it differs from reality
    edge_case_type: str            # "failure", "timeout", "unexpected_input", etc.
    dream_type: DreamType

    # Simulation inputs
    initial_state: Dict[str, Any] = field(default_factory=dict)
    planned_actions: List[str] = field(default_factory=list)

    # Metadata
    priority: float = 0.5          # How important to simulate this (0-1)
    created_at: str = ""

    def __str__(self):
        return f"[{self.dream_type.value}] {self.description[:60]}..."


@dataclass
class DreamResult:
    """Result of simulating a scenario."""
    scenario: Scenario
    simulated_outcome: str
    would_fail: bool
    failure_reason: str = ""
    lesson: str = ""
    confidence: float = 0.5

    # Simulation trace
    simulated_steps: List[str] = field(default_factory=list)
    predicted_errors: List[str] = field(default_factory=list)
    recovery_strategies: List[str] = field(default_factory=list)

    # Value
    usefulness_score: float = 0.0   # How useful was this dream? (updated later)

    timestamp: str = ""

    def get_summary(self) -> str:
        """Get human-readable summary."""
        outcome = "WOULD FAIL" if self.would_fail else "WOULD SUCCEED"
        return f"{outcome}: {self.lesson[:100]}"


@dataclass
class WorldRule:
    """A rule about how the world works."""
    rule_id: str
    pattern: str                    # "websites can timeout", "users can lie"
    context: str                    # When this applies
    confidence: float = 0.5
    times_validated: int = 0
    times_violated: int = 0
    examples: List[str] = field(default_factory=list)
    created_at: str = ""
    last_updated: str = ""


# =============================================================================
# WORLD MODEL
# =============================================================================

class WorldModel:
    """
    Simplified model of how the world works.

    Tracks rules and patterns learned from experience.
    Used for predicting outcomes during dreams.
    """

    def __init__(self, storage_path: Path = Path("memory/world_model.json")):
        self.storage_path = storage_path

        # Rules about how the world works
        self.rules: Dict[str, WorldRule] = {}

        # Patterns: "action X in context Y usually leads to Z"
        self.patterns: Dict[str, Dict] = defaultdict(lambda: {
            'action': '',
            'context': {},
            'outcomes': defaultdict(int),  # outcome -> count
            'success_rate': 0.5
        })

        # Common failure modes
        self.failure_modes: Dict[str, List[str]] = defaultdict(list)

        # Load from disk
        self._load()

    def add_rule(self, pattern: str, context: str, examples: List[str] = None):
        """Add or update a world rule."""
        rule_id = hashlib.md5(f"{pattern}:{context}".encode()).hexdigest()[:12]

        if rule_id in self.rules:
            # Update existing
            rule = self.rules[rule_id]
            rule.times_validated += 1
            rule.last_updated = datetime.now().isoformat()
            if examples:
                rule.examples.extend(examples)
        else:
            # Create new
            rule = WorldRule(
                rule_id=rule_id,
                pattern=pattern,
                context=context,
                confidence=0.5,
                examples=examples or [],
                created_at=datetime.now().isoformat(),
                last_updated=datetime.now().isoformat()
            )
            self.rules[rule_id] = rule

        self._save()

    def predict(self, action: str, context: Dict[str, Any]) -> str:
        """
        Predict what would happen if we did action in context.

        Uses learned patterns and rules.
        """
        # Look for matching patterns
        pattern_key = f"{action}:{str(sorted(context.items()))[:50]}"

        if pattern_key in self.patterns:
            pattern = self.patterns[pattern_key]

            # Get most common outcome
            if pattern['outcomes']:
                most_common = max(pattern['outcomes'].items(), key=lambda x: x[1])
                return most_common[0]

        # Fallback: use rules
        for rule in self.rules.values():
            if rule.confidence > 0.6:
                # Check if rule applies
                if self._rule_applies(rule, action, context):
                    return f"Based on rule '{rule.pattern}': likely to proceed normally"

        # Default: assume success
        return "Action likely to succeed (no learned patterns available)"

    def update(self, action: str, context: Dict, actual_outcome: str, success: bool):
        """Learn from real outcomes to improve predictions."""
        # Update pattern
        pattern_key = f"{action}:{str(sorted(context.items()))[:50]}"
        pattern = self.patterns[pattern_key]

        pattern['action'] = action
        pattern['context'] = context
        pattern['outcomes'][actual_outcome] += 1

        # Update success rate
        total_outcomes = sum(pattern['outcomes'].values())
        success_count = sum(
            count for outcome, count in pattern['outcomes'].items()
            if 'success' in outcome.lower() or 'completed' in outcome.lower()
        )
        pattern['success_rate'] = success_count / max(total_outcomes, 1)

        # Track failure modes
        if not success:
            tool = action.split('(')[0] if '(' in action else action
            if actual_outcome not in self.failure_modes[tool]:
                self.failure_modes[tool].append(actual_outcome)

        self._save()

    def _rule_applies(self, rule: WorldRule, action: str, context: Dict) -> bool:
        """Check if a rule applies to this action/context."""
        # Simple keyword matching
        action_lower = action.lower()
        context_str = str(context).lower()

        # Check if rule keywords appear
        pattern_words = set(rule.pattern.lower().split())
        action_words = set(action_lower.split())

        overlap = len(pattern_words & action_words)
        return overlap > 0

    def get_failure_modes(self, tool: str) -> List[str]:
        """Get known failure modes for a tool."""
        return self.failure_modes.get(tool, [])

    def get_stats(self) -> Dict:
        """Get world model statistics."""
        return {
            'total_rules': len(self.rules),
            'total_patterns': len(self.patterns),
            'total_failure_modes': sum(len(modes) for modes in self.failure_modes.values()),
            'high_confidence_rules': sum(1 for r in self.rules.values() if r.confidence > 0.7)
        }

    def _save(self):
        """Save world model to disk."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                'rules': {k: asdict(v) for k, v in self.rules.items()},
                'patterns': dict(self.patterns),
                'failure_modes': dict(self.failure_modes),
                'saved_at': datetime.now().isoformat()
            }

            self.storage_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.debug(f"Failed to save world model: {e}")

    def _load(self):
        """Load world model from disk."""
        if not self.storage_path.exists():
            return

        try:
            data = json.loads(self.storage_path.read_text())

            # Load rules
            for rule_id, rule_data in data.get('rules', {}).items():
                self.rules[rule_id] = WorldRule(**rule_data)

            # Load patterns (convert back to defaultdict)
            for key, pattern in data.get('patterns', {}).items():
                self.patterns[key] = pattern

            # Load failure modes
            for tool, modes in data.get('failure_modes', {}).items():
                self.failure_modes[tool] = modes

            logger.debug(f"Loaded world model: {len(self.rules)} rules, {len(self.patterns)} patterns")
        except Exception as e:
            logger.debug(f"Failed to load world model: {e}")


# =============================================================================
# SCENARIO GENERATOR
# =============================================================================

class ScenarioGenerator:
    """
    Generate 'what-if' scenarios from surprises and experiences.

    Creates variations on real events to explore edge cases.
    """

    def __init__(self, world_model: WorldModel):
        self.world_model = world_model

    def generate_from_surprise(
        self,
        surprise_event: Dict[str, Any],
        count: int = 3
    ) -> List[Scenario]:
        """
        Generate scenarios from a gap detector surprise.

        Args:
            surprise_event: Event data from gap detector
            count: Number of scenarios to generate

        Returns:
            List of scenarios to simulate
        """
        scenarios = []

        tool = surprise_event.get('tool', 'unknown')
        expected = surprise_event.get('expected', '')
        actual = surprise_event.get('actual', '')

        # 1. Failure Rehearsal: What if this failed completely?
        scenarios.append(Scenario(
            scenario_id=f"dream_{int(time.time()*1000)}_fail",
            description=f"What if {tool} failed completely?",
            context=surprise_event,
            trigger=f"Surprise on {tool}",
            variation="Complete failure instead of partial success",
            edge_case_type="total_failure",
            dream_type=DreamType.FAILURE_REHEARSAL,
            initial_state={'tool': tool, 'expected': expected},
            planned_actions=[f"Execute {tool}", "Handle complete failure"],
            priority=0.8,
            created_at=datetime.now().isoformat()
        ))

        # 2. Edge Case: What if input was malformed?
        scenarios.append(Scenario(
            scenario_id=f"dream_{int(time.time()*1000)}_edge",
            description=f"What if input to {tool} was malformed?",
            context=surprise_event,
            trigger=f"Surprise on {tool}",
            variation="Malformed input instead of valid input",
            edge_case_type="bad_input",
            dream_type=DreamType.EDGE_CASE,
            initial_state={'tool': tool, 'input': 'malformed'},
            planned_actions=[f"Execute {tool} with bad input", "Validate result"],
            priority=0.6,
            created_at=datetime.now().isoformat()
        ))

        # 3. Timeout: What if this took too long?
        scenarios.append(Scenario(
            scenario_id=f"dream_{int(time.time()*1000)}_timeout",
            description=f"What if {tool} timed out?",
            context=surprise_event,
            trigger=f"Surprise on {tool}",
            variation="Timeout instead of completion",
            edge_case_type="timeout",
            dream_type=DreamType.FAILURE_REHEARSAL,
            initial_state={'tool': tool, 'timeout': True},
            planned_actions=[f"Execute {tool}", "Handle timeout"],
            priority=0.7,
            created_at=datetime.now().isoformat()
        ))

        return scenarios[:count]

    def generate_optimization_scenarios(
        self,
        recent_episodes: List[Any],
        count: int = 2
    ) -> List[Scenario]:
        """
        Generate scenarios for optimization.

        'Could we have done that better?'
        """
        scenarios = []

        for episode in recent_episodes[:count]:
            if hasattr(episode, 'tools_used') and episode.tools_used:
                scenarios.append(Scenario(
                    scenario_id=f"dream_opt_{int(time.time()*1000)}",
                    description=f"Could we optimize {episode.task_prompt[:50]}?",
                    context={'episode': episode.memory_id if hasattr(episode, 'memory_id') else 'unknown'},
                    trigger="Recent task completion",
                    variation="Alternative tool sequence",
                    edge_case_type="optimization",
                    dream_type=DreamType.OPTIMIZATION,
                    initial_state={'tools': episode.tools_used},
                    planned_actions=["Try alternative approach", "Compare efficiency"],
                    priority=0.5,
                    created_at=datetime.now().isoformat()
                ))

        return scenarios

    def generate_novel_scenarios(self, count: int = 2) -> List[Scenario]:
        """
        Generate scenarios for novel situations.

        'What if something completely unexpected happened?'
        """
        scenarios = []

        # Common novel situations
        novel_events = [
            "Server returns 503 for all requests",
            "Page structure completely changed",
            "Rate limiting triggered",
            "Authentication suddenly required",
            "Data format changed unexpectedly"
        ]

        for i, event in enumerate(random.sample(novel_events, min(count, len(novel_events)))):
            scenarios.append(Scenario(
                scenario_id=f"dream_novel_{int(time.time()*1000)}_{i}",
                description=f"What if: {event}?",
                context={'novel_event': event},
                trigger="Proactive exploration",
                variation=event,
                edge_case_type="novel_situation",
                dream_type=DreamType.NOVEL_SITUATION,
                initial_state={},
                planned_actions=["Detect situation", "Adapt strategy"],
                priority=0.4,
                created_at=datetime.now().isoformat()
            ))

        return scenarios


# =============================================================================
# DREAM SIMULATOR
# =============================================================================

class DreamSimulator:
    """
    Simulates scenarios without real execution.

    Uses world model + LLM to predict outcomes.
    """

    def __init__(
        self,
        world_model: WorldModel,
        llm_client=None,
        llm_model: str = "qwen2.5:7b-instruct"
    ):
        self.world_model = world_model
        self.llm_client = llm_client
        self.llm_model = llm_model

    async def dry_run(self, scenario: Scenario) -> DreamResult:
        """
        Simulate a scenario without executing real actions.

        Predicts outcome using:
        1. World model patterns
        2. LLM reasoning
        3. Heuristic rules
        """
        logger.debug(f"Dreaming: {scenario}")

        # Initialize result
        result = DreamResult(
            scenario=scenario,
            simulated_outcome="",
            would_fail=False,
            confidence=0.5,
            timestamp=datetime.now().isoformat()
        )

        # Simulate using LLM if available
        if self.llm_client and OLLAMA_AVAILABLE:
            llm_result = await self._simulate_with_llm(scenario)
            result.simulated_outcome = llm_result['outcome']
            result.would_fail = llm_result['would_fail']
            result.failure_reason = llm_result.get('failure_reason', '')
            result.lesson = llm_result.get('lesson', '')
            result.confidence = llm_result.get('confidence', 0.5)
            result.simulated_steps = llm_result.get('steps', [])
        else:
            # Fallback: heuristic simulation
            heuristic_result = self._simulate_heuristic(scenario)
            result.simulated_outcome = heuristic_result['outcome']
            result.would_fail = heuristic_result['would_fail']
            result.failure_reason = heuristic_result.get('failure_reason', '')
            result.lesson = heuristic_result.get('lesson', '')
            result.confidence = 0.4  # Lower confidence for heuristics

        return result

    async def _simulate_with_llm(self, scenario: Scenario) -> Dict:
        """Use LLM to simulate scenario."""
        prompt = f"""You are simulating a 'what-if' scenario to predict outcomes without real execution.

Scenario: {scenario.description}
Type: {scenario.dream_type.value}
Edge Case: {scenario.edge_case_type}
Context: {json.dumps(scenario.context, default=str)[:500]}

Planned actions:
{chr(10).join(f"- {action}" for action in scenario.planned_actions)}

Predict what would happen if we executed this scenario. Consider:
1. Would this succeed or fail?
2. What specific errors might occur?
3. What lesson can we learn preemptively?

Respond in JSON:
{{
    "would_fail": true/false,
    "outcome": "Brief description of what happens",
    "failure_reason": "Why it would fail (if applicable)",
    "lesson": "Specific actionable lesson to prevent this",
    "steps": ["step1", "step2"],
    "confidence": 0.0-1.0
}}"""

        try:
            response = ollama.generate(
                model=self.llm_model,
                prompt=prompt,
                options={'temperature': 0.3}
            )

            # Parse JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', response['response'])
            if json_match:
                return json.loads(json_match.group(0))
        except Exception as e:
            logger.debug(f"LLM simulation failed: {e}")

        # Fallback
        return self._simulate_heuristic(scenario)

    def _simulate_heuristic(self, scenario: Scenario) -> Dict:
        """Heuristic-based simulation."""
        # Use edge case type to predict outcome
        edge_case = scenario.edge_case_type

        if edge_case == "total_failure":
            return {
                'would_fail': True,
                'outcome': "Action would fail completely",
                'failure_reason': "Simulated total failure",
                'lesson': "Always have fallback/retry logic for critical operations",
                'confidence': 0.7
            }

        if edge_case == "timeout":
            return {
                'would_fail': True,
                'outcome': "Action would timeout",
                'failure_reason': "Operation exceeded time limit",
                'lesson': "Set appropriate timeouts and handle them gracefully",
                'confidence': 0.6
            }

        if edge_case == "bad_input":
            return {
                'would_fail': True,
                'outcome': "Action would fail due to invalid input",
                'failure_reason': "Input validation failed",
                'lesson': "Validate inputs before processing, handle edge cases",
                'confidence': 0.6
            }

        # Default: might succeed
        return {
            'would_fail': False,
            'outcome': "Action would likely succeed with minor issues",
            'failure_reason': "",
            'lesson': "Continue monitoring for unexpected behaviors",
            'confidence': 0.5
        }


# =============================================================================
# DREAM ENGINE
# =============================================================================

class DreamEngine:
    """
    Main dream engine - simulates scenarios without acting.

    Called during sleep to consolidate learning and explore edge cases.
    """

    def __init__(
        self,
        gap_detector=None,
        memory_arch=None,
        llm_client=None,
        event_bus=None,
        llm_model: str = "qwen2.5:7b-instruct"
    ):
        """
        Initialize dream engine.

        Args:
            gap_detector: For accessing surprises
            memory_arch: For accessing episodic memories and storing lessons
            llm_client: For LLM-based simulation
            event_bus: For publishing LESSON_LEARNED events
            llm_model: Model to use for simulation
        """
        self.gap_detector = gap_detector
        self.memory_arch = memory_arch
        self.llm_client = llm_client
        self.event_bus = event_bus

        # Components
        self.world_model = WorldModel()
        self.scenario_generator = ScenarioGenerator(self.world_model)
        self.simulator = DreamSimulator(self.world_model, llm_client, llm_model)

        # Dream history
        self.recent_dreams: deque = deque(maxlen=100)
        self.dream_count = 0

        # Lessons learned
        self.preemptive_lessons: List[Dict] = []

        # Storage
        self.storage_path = Path("memory/dreams")
        self.storage_path.mkdir(parents=True, exist_ok=True)

    async def simulate_scenarios(self, count: int = 5) -> int:
        """
        Main dream loop - simulate several scenarios.

        This is called during sleep cycle Phase 5.

        Args:
            count: Number of scenarios to simulate

        Returns:
            Number of scenarios simulated
        """
        logger.info(f"Dream engine: simulating {count} scenarios...")

        # 1. Pull recent surprises from gap detector
        surprises = self._get_recent_surprises()

        # 2. Generate variant scenarios
        scenarios = self.generate_scenarios(surprises, count)

        if not scenarios:
            logger.debug("No scenarios to simulate")
            return 0

        # 3. Simulate each without acting
        simulated_count = 0
        for scenario in scenarios:
            try:
                result = await self.dry_run(scenario)

                # 4. Learn from simulation
                if result.would_fail:
                    self.store_preemptive_lesson(scenario, result)

                simulated_count += 1
                self.dream_count += 1

            except Exception as e:
                logger.error(f"Dream simulation error: {e}")

        logger.info(f"Dream engine: completed {simulated_count} simulations")
        return simulated_count

    def generate_scenarios(self, surprises: List[Dict], count: int) -> List[Scenario]:
        """
        Generate what-if scenarios from recent surprises.

        Creates variations: different inputs, different states, edge cases.
        """
        scenarios = []

        # 1. Generate from surprises
        for surprise in surprises[:3]:  # Top 3 surprises
            scenarios.extend(
                self.scenario_generator.generate_from_surprise(surprise, count=2)
            )

        # 2. Generate optimization scenarios
        if self.memory_arch:
            try:
                recent_episodes = self.memory_arch.search_episodes(
                    query="", limit=5, success_only=True
                )
                scenarios.extend(
                    self.scenario_generator.generate_optimization_scenarios(
                        recent_episodes, count=1
                    )
                )
            except Exception as e:
                logger.debug(f"Could not generate optimization scenarios: {e}")

        # 3. Generate novel situation scenarios
        scenarios.extend(
            self.scenario_generator.generate_novel_scenarios(count=2)
        )

        # Sort by priority
        scenarios.sort(key=lambda s: s.priority, reverse=True)

        return scenarios[:count]

    async def dry_run(self, scenario: Scenario) -> DreamResult:
        """
        Simulate a scenario without executing real actions.

        Wrapper around DreamSimulator.dry_run().
        """
        result = await self.simulator.dry_run(scenario)

        # Store in dream history
        self.recent_dreams.append({
            'scenario': asdict(scenario),
            'result': asdict(result),
            'timestamp': datetime.now().isoformat()
        })

        # Update world model
        if scenario.planned_actions:
            self.world_model.update(
                action=scenario.planned_actions[0] if scenario.planned_actions else "unknown",
                context=scenario.context,
                actual_outcome=result.simulated_outcome,
                success=not result.would_fail
            )

        return result

    def store_preemptive_lesson(self, scenario: Scenario, result: DreamResult):
        """
        Store lesson learned from simulation.

        Format: "If X happens, avoid Y because Z"
        """
        lesson = {
            'scenario_id': scenario.scenario_id,
            'lesson': result.lesson,
            'condition': f"If {scenario.edge_case_type}",
            'recommendation': f"Avoid {scenario.variation}",
            'reasoning': result.failure_reason,
            'confidence': result.confidence,
            'source': 'dream_simulation',
            'created_at': datetime.now().isoformat()
        }

        self.preemptive_lessons.append(lesson)

        # Publish LESSON_LEARNED event
        if self.event_bus:
            try:
                # Import EventType here to avoid circular dependency
                from .organism_core import OrganismEvent, EventType

                asyncio.create_task(self.event_bus.publish(OrganismEvent(
                    event_type=EventType.LESSON_LEARNED,
                    source="dream_engine",
                    data={
                        'lesson': lesson['lesson'],
                        'condition': lesson['condition'],
                        'confidence': lesson['confidence'],
                        'scenario_type': scenario.dream_type.value
                    },
                    priority=4
                )))
            except Exception as e:
                logger.debug(f"Could not publish lesson event: {e}")

        # Store in memory architecture if available
        if self.memory_arch:
            try:
                # Store as semantic memory
                from .memory_architecture import SemanticMemory, MemoryType

                semantic = SemanticMemory(
                    memory_id=f"lesson_{scenario.scenario_id}",
                    memory_type=MemoryType.SEMANTIC,
                    pattern=lesson['condition'],
                    content=lesson['lesson'],
                    context=lesson['reasoning'],
                    confidence=lesson['confidence'],
                    created_at=datetime.now().isoformat(),
                    last_accessed=datetime.now().isoformat(),
                    tags=['dream_lesson', scenario.edge_case_type, scenario.dream_type.value]
                )

                self.memory_arch.semantic.add_semantic(semantic)

            except Exception as e:
                logger.debug(f"Could not store lesson in semantic memory: {e}")

        logger.info(f"Preemptive lesson learned: {lesson['lesson'][:80]}")

    async def imagine_edge_case(self, context: str) -> List[str]:
        """
        Generate edge cases for a given context.

        'What could go wrong? What's the worst case?'
        """
        edge_cases = []

        # Common edge cases
        templates = [
            f"{context} - but the server times out",
            f"{context} - but the input is malformed",
            f"{context} - but the page structure changed",
            f"{context} - but authentication is required",
            f"{context} - but rate limiting is triggered",
            f"{context} - but the network is unstable"
        ]

        edge_cases.extend(templates)

        return edge_cases

    async def rehearse_response(self, situation: str) -> str:
        """
        Mentally rehearse how to handle a situation.

        Returns recommended response strategy.
        """
        # Use LLM if available
        if self.llm_client and OLLAMA_AVAILABLE:
            prompt = f"""You are rehearsing how to handle a situation mentally (without acting).

Situation: {situation}

What would be the best response strategy? Be specific and actionable.

Respond with a brief strategy (2-3 sentences)."""

            try:
                response = ollama.generate(
                    model=self.simulator.llm_model,
                    prompt=prompt,
                    options={'temperature': 0.2}
                )
                return response['response'].strip()
            except Exception as e:
                logger.debug(f"Rehearsal failed: {e}")

        # Fallback: generic strategy
        return f"For '{situation}': Assess context, try primary approach with fallback, monitor outcome, adjust if needed."

    def get_dream_insights(self) -> List[str]:
        """Return insights from recent dreams."""
        insights = []

        # Extract lessons from recent dreams
        for dream in list(self.recent_dreams)[-10:]:
            result = dream.get('result', {})
            lesson = result.get('lesson', '')
            if lesson and lesson not in insights:
                insights.append(lesson)

        return insights

    def update_world_model(self, observation: str):
        """Update the simplified world model from experience."""
        # Extract patterns from observation
        # This is called by other systems when they learn something

        # Simple pattern extraction
        if 'timeout' in observation.lower():
            self.world_model.add_rule(
                pattern="Operations can timeout",
                context="Network requests",
                examples=[observation]
            )

        if 'not found' in observation.lower():
            self.world_model.add_rule(
                pattern="Elements may not exist",
                context="Page interactions",
                examples=[observation]
            )

        if 'rate limit' in observation.lower():
            self.world_model.add_rule(
                pattern="APIs can rate limit",
                context="API calls",
                examples=[observation]
            )

    def _get_recent_surprises(self) -> List[Dict]:
        """Get recent surprises from gap detector."""
        surprises = []

        if not self.gap_detector:
            return surprises

        try:
            # Get recent gap events
            for gap_result in list(self.gap_detector._gap_history)[-10:]:
                if gap_result.surprise_type in ('major', 'critical'):
                    surprises.append({
                        'tool': gap_result.prediction.tool,
                        'expected': gap_result.prediction.expected_outcome,
                        'actual': gap_result.actual_outcome,
                        'gap_score': gap_result.gap_score,
                        'analysis': gap_result.analysis
                    })
        except Exception as e:
            logger.debug(f"Could not get surprises from gap detector: {e}")

        return surprises

    def get_stats(self) -> Dict:
        """Get dream engine statistics."""
        return {
            'total_dreams': self.dream_count,
            'recent_dreams': len(self.recent_dreams),
            'preemptive_lessons': len(self.preemptive_lessons),
            'world_model': self.world_model.get_stats(),
            'dream_types': self._count_dream_types()
        }

    def _count_dream_types(self) -> Dict[str, int]:
        """Count dreams by type."""
        counts = defaultdict(int)

        for dream in self.recent_dreams:
            scenario = dream.get('scenario', {})
            dream_type = scenario.get('dream_type', 'unknown')
            counts[dream_type] += 1

        return dict(counts)


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================

def create_dream_engine(
    gap_detector=None,
    memory_arch=None,
    llm_client=None,
    event_bus=None,
    **kwargs
) -> DreamEngine:
    """Factory function to create dream engine."""
    return DreamEngine(
        gap_detector=gap_detector,
        memory_arch=memory_arch,
        llm_client=llm_client,
        event_bus=event_bus,
        **kwargs
    )


# =============================================================================
# MAIN / DEMO
# =============================================================================

if __name__ == "__main__":
    async def demo():
        """Demo the dream engine."""
        print("Dream Engine - Demo")
        print("=" * 60)

        # Create dream engine (standalone)
        dream_engine = DreamEngine()

        print(f"\nWorld model stats: {dream_engine.world_model.get_stats()}")

        # Add some observations to world model
        print("\nLearning from observations...")
        dream_engine.update_world_model("Request timed out after 30 seconds")
        dream_engine.update_world_model("Element not found on page")
        dream_engine.update_world_model("Rate limit exceeded: 429 Too Many Requests")

        print(f"Updated world model: {dream_engine.world_model.get_stats()}")

        # Simulate some scenarios
        print("\nSimulating scenarios...")
        count = await dream_engine.simulate_scenarios(count=3)

        print(f"\nSimulated {count} scenarios")

        # Get insights
        insights = dream_engine.get_dream_insights()
        print(f"\nInsights from dreams:")
        for i, insight in enumerate(insights, 1):
            print(f"  {i}. {insight}")

        # Rehearse a response
        print("\nRehearsal:")
        situation = "Page navigation fails with 404 error"
        strategy = await dream_engine.rehearse_response(situation)
        print(f"  Situation: {situation}")
        print(f"  Strategy: {strategy}")

        # Stats
        print("\nDream Engine Statistics:")
        stats = dream_engine.get_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")

        print("\nDemo complete!")

    asyncio.run(demo())
