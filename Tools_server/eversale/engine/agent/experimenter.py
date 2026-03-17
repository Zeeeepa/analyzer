"""
Experimenter: Safe hypothesis testing for strategy improvement.

This component enables controlled experimentation with new approaches
before committing to changes. Uses simulation for safety.
"""

import asyncio
import json
import time
import random
import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Any, Callable
from collections import defaultdict
import statistics

from agent.organism_core import EventBus, EventType, OrganismEvent

logger = logging.getLogger(__name__)


class ExperimentStatus(Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"  # Failed safety check


class ExperimentType(Enum):
    STRATEGY = "strategy"          # Test a new approach
    PARAMETER = "parameter"        # Tune a value
    BEHAVIOR = "behavior"          # Try new behavior
    OPTIMIZATION = "optimization"  # Improve existing


@dataclass
class Hypothesis:
    """A testable hypothesis."""
    id: str
    description: str
    experiment_type: ExperimentType
    control: dict           # Current approach
    treatment: dict         # New approach to test
    expected_improvement: float  # Expected % improvement
    risk_level: str = "low"      # low, medium, high
    created_at: float = field(default_factory=time.time)


@dataclass
class ExperimentResult:
    """Result of an experiment."""
    hypothesis_id: str
    status: ExperimentStatus
    control_score: float
    treatment_score: float
    improvement: float           # Actual improvement %
    confidence: float            # Statistical confidence
    sample_size: int
    p_value: float
    significant: bool            # p < 0.05
    recommendation: str          # "adopt", "reject", "inconclusive"
    duration_seconds: float
    notes: list[str] = field(default_factory=list)


@dataclass
class Experiment:
    """A running or completed experiment."""
    hypothesis: Hypothesis
    status: ExperimentStatus
    control_trials: list[float] = field(default_factory=list)
    treatment_trials: list[float] = field(default_factory=list)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[ExperimentResult] = None


class Experimenter:
    """
    Safe experimentation framework.

    Responsibilities:
    1. Propose and validate experiments
    2. Run experiments in simulation sandbox
    3. Track outcomes with statistical rigor
    4. Guard against unsafe experiments
    5. Recommend adoptions based on evidence
    """

    def __init__(
        self,
        event_bus: EventBus,
        dream_engine: Optional[Any] = None,  # For simulation
        immune_system: Optional[Any] = None,  # For safety checks
        persistence_path: Optional[Path] = None
    ):
        self.event_bus = event_bus
        self.dream_engine = dream_engine
        self.immune_system = immune_system
        self.persistence_path = persistence_path or Path("memory/experimenter.json")

        # Experiment tracking
        self.experiments: dict[str, Experiment] = {}
        self.completed_experiments: list[str] = []
        self.adopted_changes: list[str] = []

        # Configuration
        self.min_sample_size: int = 10
        self.significance_threshold: float = 0.05  # p-value
        self.min_improvement_threshold: float = 0.05  # 5% minimum improvement
        self.max_concurrent_experiments: int = 3

        # Statistics
        self.total_experiments: int = 0
        self.successful_adoptions: int = 0

        # Subscribe to events
        self._setup_subscriptions()

        # Load state
        self._load_state()

    def _setup_subscriptions(self):
        """Subscribe to organism events."""
        self.event_bus.subscribe(EventType.ACTION_COMPLETE, self._on_action_complete)
        self.event_bus.subscribe(EventType.LESSON_LEARNED, self._on_lesson_learned)

    async def _on_action_complete(self, event: OrganismEvent):
        """Track action outcomes for running experiments."""
        # Check if this action is part of an experiment
        exp_id = event.data.get("experiment_id")
        if exp_id and exp_id in self.experiments:
            exp = self.experiments[exp_id]
            score = event.data.get("score", 1.0 if event.data.get("success") else 0.0)
            is_treatment = event.data.get("is_treatment", False)

            if is_treatment:
                exp.treatment_trials.append(score)
            else:
                exp.control_trials.append(score)

            # Check if enough samples
            if (len(exp.control_trials) >= self.min_sample_size and
                len(exp.treatment_trials) >= self.min_sample_size):
                await self._complete_experiment(exp_id)

    async def _on_lesson_learned(self, event: OrganismEvent):
        """Consider if lesson suggests an experiment."""
        # Auto-propose experiments based on lessons
        lesson = event.data.get("lesson", "")
        if "could try" in lesson.lower() or "might work better" in lesson.lower():
            # Potential experiment opportunity
            pass

    # === Core Methods ===

    def generate_hypothesis_id(self, description: str) -> str:
        """Generate unique ID for hypothesis."""
        return hashlib.md5(f"{description}{time.time()}".encode()).hexdigest()[:12]

    async def propose_experiment(
        self,
        description: str,
        experiment_type: ExperimentType,
        control: dict,
        treatment: dict,
        expected_improvement: float = 0.1,
        risk_level: str = "low"
    ) -> Optional[Hypothesis]:
        """
        Propose a new experiment.

        Returns Hypothesis if approved, None if rejected.
        """
        hypothesis = Hypothesis(
            id=self.generate_hypothesis_id(description),
            description=description,
            experiment_type=experiment_type,
            control=control,
            treatment=treatment,
            expected_improvement=expected_improvement,
            risk_level=risk_level
        )

        # Safety check
        if not await self._check_safety(hypothesis):
            await self.event_bus.publish(OrganismEvent(
                event_type=EventType.HEALTH_WARNING,
                source="experimenter",
                data={
                    "message": f"Experiment rejected by safety check: {description}",
                    "hypothesis_id": hypothesis.id
                }
            ))
            return None

        # Check concurrent experiment limit
        running = sum(1 for e in self.experiments.values()
                     if e.status == ExperimentStatus.RUNNING)
        if running >= self.max_concurrent_experiments:
            return None

        # Create experiment
        experiment = Experiment(
            hypothesis=hypothesis,
            status=ExperimentStatus.APPROVED
        )
        self.experiments[hypothesis.id] = experiment
        self.total_experiments += 1

        self._save_state()
        return hypothesis

    async def _check_safety(self, hypothesis: Hypothesis) -> bool:
        """Check if experiment is safe to run."""
        # High risk requires extra scrutiny
        if hypothesis.risk_level == "high":
            # Would need human approval in production
            return False

        # Check with immune system if available
        if self.immune_system:
            # Simulate the treatment to check for threats
            treatment_desc = json.dumps(hypothesis.treatment)
            # In real implementation, would call immune_system.screen()
            pass

        # Check for dangerous keywords
        dangerous = ["delete", "destroy", "bypass", "override", "disable"]
        treatment_str = str(hypothesis.treatment).lower()
        for word in dangerous:
            if word in treatment_str:
                return False

        return True

    async def run_experiment(
        self,
        hypothesis_id: str,
        simulator: Optional[Callable] = None
    ) -> Optional[ExperimentResult]:
        """
        Run an experiment.

        Uses simulator function or DreamEngine for safe execution.
        """
        if hypothesis_id not in self.experiments:
            return None

        exp = self.experiments[hypothesis_id]
        if exp.status != ExperimentStatus.APPROVED:
            return None

        exp.status = ExperimentStatus.RUNNING
        exp.started_at = time.time()

        # Use provided simulator or DreamEngine
        sim = simulator or self._default_simulator

        try:
            # Run control trials
            for _ in range(self.min_sample_size):
                score = await sim(exp.hypothesis.control, is_treatment=False)
                exp.control_trials.append(score)

            # Run treatment trials
            for _ in range(self.min_sample_size):
                score = await sim(exp.hypothesis.treatment, is_treatment=True)
                exp.treatment_trials.append(score)

            # Complete and analyze
            return await self._complete_experiment(hypothesis_id)

        except Exception as e:
            exp.status = ExperimentStatus.FAILED
            exp.result = ExperimentResult(
                hypothesis_id=hypothesis_id,
                status=ExperimentStatus.FAILED,
                control_score=0,
                treatment_score=0,
                improvement=0,
                confidence=0,
                sample_size=0,
                p_value=1.0,
                significant=False,
                recommendation="reject",
                duration_seconds=time.time() - exp.started_at,
                notes=[f"Experiment failed: {e}"]
            )
            self._save_state()
            return exp.result

    async def _default_simulator(self, config: dict, is_treatment: bool) -> float:
        """Default simulator using random with bias toward treatment if it looks better."""
        # Simple simulation - in practice would use DreamEngine
        base_score = 0.6

        # Treatment might be slightly better (simulated)
        if is_treatment:
            base_score += random.gauss(0.05, 0.1)
        else:
            base_score += random.gauss(0, 0.1)

        return max(0, min(1, base_score))

    async def _complete_experiment(self, hypothesis_id: str) -> ExperimentResult:
        """Complete experiment and analyze results."""
        exp = self.experiments[hypothesis_id]
        exp.completed_at = time.time()

        # Calculate statistics
        control_mean = statistics.mean(exp.control_trials) if exp.control_trials else 0
        treatment_mean = statistics.mean(exp.treatment_trials) if exp.treatment_trials else 0

        control_std = statistics.stdev(exp.control_trials) if len(exp.control_trials) > 1 else 0.1
        treatment_std = statistics.stdev(exp.treatment_trials) if len(exp.treatment_trials) > 1 else 0.1

        # Calculate improvement
        if control_mean > 0:
            improvement = (treatment_mean - control_mean) / control_mean
        else:
            improvement = treatment_mean

        # Simple t-test approximation
        n = len(exp.control_trials)
        pooled_std = ((control_std ** 2 + treatment_std ** 2) / 2) ** 0.5
        if pooled_std > 0:
            t_stat = (treatment_mean - control_mean) / (pooled_std * (2/n) ** 0.5)
            # Approximate p-value (simplified)
            p_value = max(0.001, min(1.0, 2 * (1 - min(0.9999, abs(t_stat) / 4))))
        else:
            t_stat = 0
            p_value = 1.0

        significant = p_value < self.significance_threshold
        confidence = 1 - p_value

        # Recommendation
        if significant and improvement > self.min_improvement_threshold:
            recommendation = "adopt"
        elif significant and improvement < -self.min_improvement_threshold:
            recommendation = "reject"
        else:
            recommendation = "inconclusive"

        result = ExperimentResult(
            hypothesis_id=hypothesis_id,
            status=ExperimentStatus.COMPLETED,
            control_score=control_mean,
            treatment_score=treatment_mean,
            improvement=improvement,
            confidence=confidence,
            sample_size=len(exp.control_trials) + len(exp.treatment_trials),
            p_value=p_value,
            significant=significant,
            recommendation=recommendation,
            duration_seconds=exp.completed_at - exp.started_at,
            notes=[]
        )

        exp.status = ExperimentStatus.COMPLETED
        exp.result = result
        self.completed_experiments.append(hypothesis_id)

        # Emit event
        await self.event_bus.publish(OrganismEvent(
            event_type=EventType.LESSON_LEARNED,
            source="experimenter",
            data={
                "experiment_id": hypothesis_id,
                "description": exp.hypothesis.description,
                "recommendation": recommendation,
                "improvement": f"{improvement:.1%}",
                "confidence": f"{confidence:.1%}"
            }
        ))

        self._save_state()
        return result

    async def adopt_change(self, hypothesis_id: str) -> bool:
        """Adopt a successful experiment's treatment as new default."""
        if hypothesis_id not in self.experiments:
            return False

        exp = self.experiments[hypothesis_id]
        if not exp.result or exp.result.recommendation != "adopt":
            return False

        self.adopted_changes.append(hypothesis_id)
        self.successful_adoptions += 1

        await self.event_bus.publish(OrganismEvent(
            event_type=EventType.STRATEGY_UPDATED,
            source="experimenter",
            data={
                "experiment_id": hypothesis_id,
                "adopted_treatment": exp.hypothesis.treatment,
                "improvement": exp.result.improvement
            }
        ))

        self._save_state()
        return True

    def get_experiment_status(self, hypothesis_id: str) -> Optional[dict]:
        """Get status of an experiment."""
        if hypothesis_id not in self.experiments:
            return None

        exp = self.experiments[hypothesis_id]
        return {
            "id": hypothesis_id,
            "description": exp.hypothesis.description,
            "status": exp.status.value,
            "control_trials": len(exp.control_trials),
            "treatment_trials": len(exp.treatment_trials),
            "result": {
                "recommendation": exp.result.recommendation,
                "improvement": f"{exp.result.improvement:.1%}",
                "confidence": f"{exp.result.confidence:.1%}"
            } if exp.result else None
        }

    def get_stats(self) -> dict:
        """Get experimenter statistics."""
        running = [e for e in self.experiments.values()
                  if e.status == ExperimentStatus.RUNNING]
        completed = [e for e in self.experiments.values()
                    if e.status == ExperimentStatus.COMPLETED]

        return {
            "total_experiments": self.total_experiments,
            "running": len(running),
            "completed": len(completed),
            "successful_adoptions": self.successful_adoptions,
            "adoption_rate": f"{self.successful_adoptions / max(1, len(completed)):.0%}",
            "recent_experiments": [
                {
                    "id": e.hypothesis.id,
                    "description": e.hypothesis.description[:50],
                    "status": e.status.value,
                    "recommendation": e.result.recommendation if e.result else None
                }
                for e in list(self.experiments.values())[-5:]
            ]
        }

    # === Persistence ===

    def _save_state(self):
        """Persist experimenter state."""
        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "total_experiments": self.total_experiments,
            "successful_adoptions": self.successful_adoptions,
            "completed_experiments": self.completed_experiments[-100:],
            "adopted_changes": self.adopted_changes[-100:],
            "experiments": {
                id: {
                    "hypothesis": {
                        "id": e.hypothesis.id,
                        "description": e.hypothesis.description,
                        "experiment_type": e.hypothesis.experiment_type.value,
                        "control": e.hypothesis.control,
                        "treatment": e.hypothesis.treatment,
                        "expected_improvement": e.hypothesis.expected_improvement,
                        "risk_level": e.hypothesis.risk_level
                    },
                    "status": e.status.value,
                    "control_trials": e.control_trials,
                    "treatment_trials": e.treatment_trials,
                    "started_at": e.started_at,
                    "completed_at": e.completed_at,
                    "result": {
                        "recommendation": e.result.recommendation,
                        "improvement": e.result.improvement,
                        "confidence": e.result.confidence,
                        "p_value": e.result.p_value,
                        "significant": e.result.significant
                    } if e.result else None
                }
                for id, e in list(self.experiments.items())[-50:]
            }
        }

        with open(self.persistence_path, 'w') as f:
            json.dump(state, f, indent=2)

    def _load_state(self):
        """Load persisted state."""
        if not self.persistence_path.exists():
            return

        try:
            with open(self.persistence_path) as f:
                state = json.load(f)

            self.total_experiments = state.get("total_experiments", 0)
            self.successful_adoptions = state.get("successful_adoptions", 0)
            self.completed_experiments = state.get("completed_experiments", [])
            self.adopted_changes = state.get("adopted_changes", [])

            # Restore experiments (simplified - mainly for stats)
            # Full restoration would rebuild Experiment objects

        except Exception as e:
            logger.debug(f"Failed to load state: {e}")


# === Factory Function ===

def init_experimenter(
    event_bus: EventBus,
    dream_engine: Optional[Any] = None,
    immune_system: Optional[Any] = None,
    persistence_path: Optional[Path] = None
) -> Experimenter:
    """Initialize the experimenter component."""
    return Experimenter(event_bus, dream_engine, immune_system, persistence_path)
