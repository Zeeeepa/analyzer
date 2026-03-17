#!/usr/bin/env python3
"""
Reflexion Self-Improvement Loop (Shinn et al., 2023)
Production implementation with enhancements from LangChain and agent research.

Framework Overview:
    Attempt → Observe Outcome → Generate Self-Reflection →
    Store in Memory → Retry with Reflection Context → Repeat until Success

Architecture:
- Actor: Generates actions based on observations + reflection history
- Critic/Evaluator: Scores outputs, determines success/failure
- Self-Reflection Generator: Creates verbal reinforcement cues
- Memory System: Stores and retrieves reflections
- Experience Replay: Learns from past trajectories

Target Performance:
- 91% success on coding tasks (AlfWorld benchmark)
- 97% success on decision-making (HotPotQA benchmark)
- Self-healing through iterative reflection

References:
- Reflexion: Language Agents with Verbal Reinforcement Learning (Shinn et al., 2023)
- LangChain ReAct + Reflexion patterns
- Production agent research from Anthropic, OpenAI, Google DeepMind
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from loguru import logger
import ollama
from collections import defaultdict, deque

# For vector similarity (optional enhancement)
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


# ============================================================================
# DATA STRUCTURES
# ============================================================================

class ReflectionType(Enum):
    """Types of reflections for categorization."""
    SUCCESS = "success"           # What worked well
    FAILURE = "failure"           # What went wrong
    STRATEGY = "strategy"         # General strategy insight
    PATTERN = "pattern"           # Recurring pattern identified
    CORRECTION = "correction"     # Correction applied


@dataclass
class TaskAttempt:
    """A single attempt at completing a task."""
    attempt_number: int
    action: str                   # Action taken (tool call, reasoning step)
    observation: str              # Result observed
    success: bool
    execution_time: float
    timestamp: str
    tool_calls: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    intermediate_steps: List[Dict] = field(default_factory=list)


@dataclass
class SelfReflection:
    """A self-reflection generated from task execution."""
    reflection_id: str
    task_prompt: str
    task_category: str
    attempt_number: int
    reflection_type: ReflectionType

    # The actual reflection content
    what_happened: str            # Factual description
    why_it_happened: str          # Root cause analysis
    what_to_do_next: str          # Specific actionable advice

    # Context
    failed_approach: Optional[Dict] = None
    successful_approach: Optional[Dict] = None

    # Metadata
    confidence: float = 0.0       # How confident in this reflection (0-1)
    usefulness: float = 0.0       # How useful this proved to be (updated later)
    times_referenced: int = 0     # How many times this was retrieved and used

    # Timestamps
    created_at: str = ""
    last_used: str = ""

    # Embedding for similarity search (optional)
    embedding: Optional[List[float]] = None


@dataclass
class TaskTrajectory:
    """Complete trajectory of a task execution (for experience replay)."""
    trajectory_id: str
    task_prompt: str
    task_category: str
    task_domain: str

    attempts: List[TaskAttempt] = field(default_factory=list)
    reflections: List[SelfReflection] = field(default_factory=list)

    final_success: bool = False
    total_attempts: int = 0
    total_execution_time: float = 0.0

    # Learning outcomes
    key_insights: List[str] = field(default_factory=list)
    mistakes_made: List[str] = field(default_factory=list)
    successful_strategies: List[str] = field(default_factory=list)

    timestamp: str = ""


@dataclass
class ReflexionMetrics:
    """Metrics for tracking reflexion performance."""
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0

    total_attempts: int = 0
    avg_attempts_to_success: float = 0.0

    reflections_generated: int = 0
    reflections_used: int = 0

    # Improvement tracking
    first_attempt_success_rate: float = 0.0
    final_success_rate: float = 0.0
    improvement_rate: float = 0.0

    # By category
    category_performance: Dict[str, Dict] = field(default_factory=dict)

    # Time tracking
    start_time: str = ""
    last_update: str = ""


# ============================================================================
# CRITIC / EVALUATOR
# ============================================================================

class TaskEvaluator:
    """
    Critic component: Evaluates task completion and generates scores.
    Uses multiple verification strategies.
    """

    def __init__(self, config: Dict):
        self.config = config
        self.llm_model = config.get('llm', {}).get('main_model', '0000/ui-tars-1.5-7b:latest')

    async def evaluate_attempt(
        self,
        task_prompt: str,
        task_category: str,
        output: str,
        expected_outcome: Optional[str] = None,
        ground_truth: Optional[Any] = None,
        page_content: str = "",
        screenshot_path: str = ""
    ) -> Tuple[bool, float, str]:
        """
        Evaluate whether an attempt was successful.

        Returns:
            (success: bool, confidence: float, reasoning: str)
        """

        # Use multiple verification strategies
        scores = []
        reasonings = []

        # 1. Heuristic verification (fast)
        heuristic_success, heuristic_conf, heuristic_reason = self._heuristic_verify(
            task_category, output
        )
        scores.append((heuristic_success, heuristic_conf))
        reasonings.append(f"Heuristic: {heuristic_reason}")

        # 2. Ground truth verification (if available)
        if ground_truth or page_content:
            gt_success, gt_conf, gt_reason = self._ground_truth_verify(
                output, ground_truth, page_content, task_category
            )
            scores.append((gt_success, gt_conf))
            reasonings.append(f"Ground truth: {gt_reason}")

        # 3. LLM-based verification (most flexible but slower)
        llm_success, llm_conf, llm_reason = await self._llm_verify(
            task_prompt, task_category, output, expected_outcome
        )
        scores.append((llm_success, llm_conf))
        reasonings.append(f"LLM: {llm_reason}")

        # Aggregate scores (weighted voting)
        weights = [0.3, 0.4, 0.3]  # heuristic, ground_truth, llm
        if not (ground_truth or page_content):
            weights = [0.4, 0.0, 0.6]  # Adjust if no ground truth

        total_weight = 0.0
        weighted_success = 0.0
        for i, (success, conf) in enumerate(scores):
            if weights[i] > 0:
                weighted_success += weights[i] * (1.0 if success else 0.0) * conf
                total_weight += weights[i] * conf

        final_success = (weighted_success / total_weight) > 0.5 if total_weight > 0 else False
        final_confidence = total_weight / sum(w for w in weights if w > 0)

        combined_reasoning = " | ".join(reasonings)

        return final_success, final_confidence, combined_reasoning

    def _heuristic_verify(
        self,
        task_category: str,
        output: str
    ) -> Tuple[bool, float, str]:
        """Fast heuristic-based verification."""
        output_lower = output.lower()

        # Check for explicit failure indicators
        failure_indicators = [
            'error', 'failed', 'could not', 'unable to',
            'timed out', 'not found', 'exception', 'crashed'
        ]

        if any(ind in output_lower for ind in failure_indicators):
            # Exception: error handling tasks
            if task_category == 'error_recovery':
                if 'handled' in output_lower or 'recovered' in output_lower:
                    return True, 0.8, "Error handled successfully"
            return False, 0.9, "Failure indicators present"

        # Category-specific checks
        if task_category == 'navigation':
            if 'navigated' in output_lower or 'loaded' in output_lower:
                return True, 0.7, "Navigation success indicators"
            return False, 0.6, "No navigation success indicators"

        if task_category in ['extraction', 'search', 'data_extraction']:
            if len(output) > 100 and ('extracted' in output_lower or 'found' in output_lower):
                return True, 0.7, "Extraction indicators and sufficient output"
            return False, 0.6, "Insufficient extraction evidence"

        if task_category == 'interaction':
            if 'clicked' in output_lower or 'filled' in output_lower or 'submitted' in output_lower:
                return True, 0.7, "Interaction success indicators"
            return False, 0.6, "No interaction success indicators"

        # Default: check for minimal output
        if len(output) > 50:
            return True, 0.5, "Has output (weak signal)"

        return False, 0.5, "Insufficient output"

    def _ground_truth_verify(
        self,
        output: str,
        ground_truth: Any,
        page_content: str,
        task_category: str
    ) -> Tuple[bool, float, str]:
        """Verify against ground truth or page content."""

        # For extraction tasks: check if extracted data exists in page
        if task_category in ['extraction', 'search', 'data_extraction'] and page_content:
            # Extract structured data patterns from output
            import re

            # Look for emails, URLs, numbers, etc.
            emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', output)
            urls = re.findall(r'https?://[^\s<>"\']+', output)
            phones = re.findall(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', output)

            # Check if these exist in page content
            found_count = 0
            total_count = len(emails) + len(urls) + len(phones)

            if total_count > 0:
                for item in emails + urls + phones:
                    if item in page_content:
                        found_count += 1

                match_rate = found_count / total_count
                if match_rate > 0.7:
                    return True, 0.9, f"Ground truth verified: {match_rate*100:.0f}% match"
                else:
                    return False, 0.8, f"Ground truth mismatch: only {match_rate*100:.0f}% match"

            # Fallback: check for general text overlap
            output_words = set(output.lower().split())
            page_words = set(page_content.lower().split())
            overlap = len(output_words & page_words) / max(len(output_words), 1)

            if overlap > 0.3:
                return True, 0.6, f"Moderate text overlap ({overlap*100:.0f}%)"
            else:
                return False, 0.7, f"Low text overlap ({overlap*100:.0f}%)"

        # If ground_truth provided, do direct comparison
        if ground_truth:
            if str(ground_truth).lower() in output.lower():
                return True, 0.95, "Exact ground truth match"
            else:
                return False, 0.95, "Ground truth not found in output"

        return True, 0.5, "No ground truth available (neutral)"

    async def _llm_verify(
        self,
        task_prompt: str,
        task_category: str,
        output: str,
        expected_outcome: Optional[str] = None
    ) -> Tuple[bool, float, str]:
        """Use LLM to verify task completion."""

        verification_prompt = f"""You are a task evaluator. Determine if the following task was completed successfully.

Task: {task_prompt}
Category: {task_category}
{f'Expected outcome: {expected_outcome}' if expected_outcome else ''}

Agent output:
{output[:1000]}

Evaluate whether the task was completed successfully. Consider:
1. Did the agent accomplish the stated goal?
2. Is the output relevant and useful?
3. Are there any clear failures or errors?

Respond in JSON format:
{{
    "success": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation"
}}"""

        try:
            response = ollama.generate(
                model=self.llm_model,
                prompt=verification_prompt,
                options={'temperature': 0.1}
            )

            # Parse JSON response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response['response'])
            if json_match:
                result = json.loads(json_match.group(0))
                return (
                    result.get('success', False),
                    result.get('confidence', 0.5),
                    result.get('reasoning', 'No reasoning provided')
                )
        except Exception as e:
            logger.debug(f"LLM verification failed: {e}")

        # Fallback
        return False, 0.3, "LLM verification unavailable"


# ============================================================================
# SELF-REFLECTION GENERATOR
# ============================================================================

class ReflectionGenerator:
    """
    Generates verbal self-reflections from task execution.
    Creates specific, actionable feedback for future attempts.
    """

    def __init__(self, config: Dict):
        self.config = config
        self.llm_model = config.get('llm', {}).get('main_model', '0000/ui-tars-1.5-7b:latest')

    async def generate_reflection(
        self,
        task_prompt: str,
        task_category: str,
        attempts: List[TaskAttempt],
        success: bool,
        previous_reflections: List[SelfReflection] = None
    ) -> SelfReflection:
        """
        Generate a self-reflection from task execution trajectory.

        This is the core of Reflexion: creating verbal reinforcement cues
        that help the agent learn from experience.
        """

        # Prepare context
        attempts_summary = self._summarize_attempts(attempts)
        previous_lessons = self._summarize_previous_reflections(previous_reflections) if previous_reflections else "No previous reflections."

        reflection_prompt = f"""You are an AI agent that learns from experience through self-reflection.

Task: {task_prompt}
Category: {task_category}
Final outcome: {"SUCCESS" if success else "FAILURE"}

Execution trajectory:
{attempts_summary}

Previous lessons learned:
{previous_lessons}

Generate a detailed self-reflection to improve future performance. Structure your reflection as:

1. WHAT HAPPENED (factual description):
   - What actions were taken?
   - What was the actual outcome?
   - What unexpected things occurred?

2. WHY IT HAPPENED (root cause analysis):
   - What was the underlying reason for success/failure?
   - What assumptions were wrong?
   - What was overlooked or misunderstood?

3. WHAT TO DO NEXT (specific actionable advice):
   - Concrete steps to improve next time
   - Specific techniques or approaches to try
   - Things to avoid or watch out for

Be SPECIFIC and ACTIONABLE. Avoid generic advice like "be more careful" or "try harder".

Respond in JSON format:
{{
    "what_happened": "...",
    "why_it_happened": "...",
    "what_to_do_next": "...",
    "confidence": 0.0-1.0,
    "reflection_type": "success/failure/strategy/pattern"
}}"""

        try:
            response = ollama.generate(
                model=self.llm_model,
                prompt=reflection_prompt,
                options={'temperature': 0.3}  # Some creativity but mostly factual
            )

            # Parse response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response['response'])
            if json_match:
                reflection_data = json.loads(json_match.group(0))

                # Create reflection object
                reflection = SelfReflection(
                    reflection_id=f"refl_{int(time.time()*1000)}_{len(attempts)}",
                    task_prompt=task_prompt,
                    task_category=task_category,
                    attempt_number=len(attempts),
                    reflection_type=ReflectionType(reflection_data.get('reflection_type', 'failure' if not success else 'success')),
                    what_happened=reflection_data.get('what_happened', ''),
                    why_it_happened=reflection_data.get('why_it_happened', ''),
                    what_to_do_next=reflection_data.get('what_to_do_next', ''),
                    confidence=reflection_data.get('confidence', 0.5),
                    created_at=datetime.now().isoformat(),
                    failed_approach=asdict(attempts[-1]) if not success and attempts else None,
                    successful_approach=asdict(attempts[-1]) if success and attempts else None
                )

                return reflection

        except Exception as e:
            logger.error(f"Failed to generate reflection: {e}")

        # Fallback: create basic reflection
        return self._create_fallback_reflection(task_prompt, task_category, attempts, success)

    def _summarize_attempts(self, attempts: List[TaskAttempt]) -> str:
        """Summarize execution attempts for reflection generation."""
        if not attempts:
            return "No attempts recorded."

        summary = []
        for i, attempt in enumerate(attempts, 1):
            summary.append(f"Attempt {i}:")
            summary.append(f"  Action: {attempt.action[:200]}")
            summary.append(f"  Observation: {attempt.observation[:200]}")
            summary.append(f"  Result: {'SUCCESS' if attempt.success else 'FAILURE'}")
            if attempt.errors:
                summary.append(f"  Errors: {', '.join(attempt.errors[:3])}")

        return "\n".join(summary)

    def _summarize_previous_reflections(self, reflections: List[SelfReflection]) -> str:
        """Summarize previous reflections to avoid repetition."""
        if not reflections:
            return "No previous reflections."

        summary = []
        for i, refl in enumerate(reflections[-3:], 1):  # Last 3 reflections
            summary.append(f"{i}. {refl.what_to_do_next[:150]}")

        return "\n".join(summary)

    def _create_fallback_reflection(
        self,
        task_prompt: str,
        task_category: str,
        attempts: List[TaskAttempt],
        success: bool
    ) -> SelfReflection:
        """Create a basic reflection when LLM generation fails."""
        if success:
            what_happened = f"Task completed successfully after {len(attempts)} attempt(s)."
            why_it_happened = "The approach worked as expected."
            what_to_do_next = "Continue using similar strategies for this type of task."
        else:
            what_happened = f"Task failed after {len(attempts)} attempt(s)."
            why_it_happened = "The approach did not work. Need different strategy."
            what_to_do_next = "Try alternative approaches: different tools, different selectors, or different navigation paths."

        return SelfReflection(
            reflection_id=f"refl_fallback_{int(time.time()*1000)}",
            task_prompt=task_prompt,
            task_category=task_category,
            attempt_number=len(attempts),
            reflection_type=ReflectionType.SUCCESS if success else ReflectionType.FAILURE,
            what_happened=what_happened,
            why_it_happened=why_it_happened,
            what_to_do_next=what_to_do_next,
            confidence=0.3,
            created_at=datetime.now().isoformat()
        )


# ============================================================================
# MEMORY SYSTEM
# ============================================================================

class ReflexionMemory:
    """
    Memory system for storing and retrieving reflections.

    Supports:
    - Short-term memory: Current task reflections
    - Long-term memory: All reflections, indexed for retrieval
    - Similarity search: Find relevant past reflections
    - Consolidation: Merge similar reflections into strategies
    """

    def __init__(self, storage_dir: Path = Path("memory/reflexion")):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Short-term memory: Recent reflections (last N per task)
        self.short_term: deque = deque(maxlen=10)

        # Long-term memory: All reflections, indexed by category and type
        self.long_term: Dict[str, List[SelfReflection]] = defaultdict(list)

        # Consolidated strategies: High-value patterns
        self.strategies: Dict[str, List[str]] = defaultdict(list)

        # Load from disk
        self._load()

    def add_reflection(self, reflection: SelfReflection):
        """Add a reflection to memory."""
        # Add to short-term
        self.short_term.append(reflection)

        # Add to long-term (indexed by category)
        self.long_term[reflection.task_category].append(reflection)

        # Save to disk
        self._save_reflection(reflection)

    def get_relevant_reflections(
        self,
        task_category: str,
        task_prompt: str,
        limit: int = 5
    ) -> List[SelfReflection]:
        """
        Retrieve most relevant reflections for a task.

        Uses:
        1. Category matching
        2. Keyword similarity
        3. Usefulness scoring
        4. Recency
        """
        candidates = self.long_term.get(task_category, [])

        if not candidates:
            # Fallback: get from all categories
            candidates = []
            for reflections in self.long_term.values():
                candidates.extend(reflections)

        # Score each reflection
        scored = []
        for refl in candidates:
            score = self._compute_relevance_score(refl, task_category, task_prompt)
            scored.append((score, refl))

        # Sort by score (descending)
        scored.sort(key=lambda x: x[0], reverse=True)

        # Update usage stats
        selected = [refl for _, refl in scored[:limit]]
        for refl in selected:
            refl.times_referenced += 1
            refl.last_used = datetime.now().isoformat()

        return selected

    def _compute_relevance_score(
        self,
        reflection: SelfReflection,
        task_category: str,
        task_prompt: str
    ) -> float:
        """Compute relevance score for a reflection."""
        score = 0.0

        # Category match (high weight)
        if reflection.task_category == task_category:
            score += 10.0

        # Keyword overlap (medium weight)
        prompt_words = set(task_prompt.lower().split())
        refl_words = set(reflection.task_prompt.lower().split())
        overlap = len(prompt_words & refl_words) / max(len(prompt_words), 1)
        score += overlap * 5.0

        # Usefulness (high weight - learned from feedback)
        score += reflection.usefulness * 8.0

        # Confidence (medium weight)
        score += reflection.confidence * 3.0

        # Times referenced (small positive signal)
        score += min(reflection.times_referenced * 0.5, 3.0)

        # Recency (decay over time)
        try:
            age_days = (datetime.now() - datetime.fromisoformat(reflection.created_at)).days
            recency_factor = max(0, 1.0 - age_days / 30)  # Decay over 30 days
            score += recency_factor * 2.0
        except:
            pass

        return score

    def consolidate_reflections(self) -> int:
        """
        Consolidate similar reflections into high-level strategies.
        Returns number of strategies created.
        """
        # Group reflections by category
        strategies_created = 0

        for category, reflections in self.long_term.items():
            # Get successful reflections only
            successful = [r for r in reflections
                         if r.reflection_type == ReflectionType.SUCCESS
                         and r.usefulness > 0.6]

            if len(successful) < 3:
                continue

            # Look for common patterns in "what_to_do_next"
            advice_texts = [r.what_to_do_next for r in successful]

            # Simple clustering: find frequently occurring phrases
            from collections import Counter
            words = []
            for text in advice_texts:
                words.extend(text.lower().split())

            # Get common bigrams/trigrams
            common = Counter(words).most_common(10)

            # Create strategy if enough evidence
            if common and common[0][1] >= 3:
                strategy = f"For {category} tasks: " + ", ".join([word for word, count in common[:3]])
                if strategy not in self.strategies[category]:
                    self.strategies[category].append(strategy)
                    strategies_created += 1
                    logger.info(f"Consolidated strategy: {strategy}")

        return strategies_created

    def get_strategies(self, category: str) -> List[str]:
        """Get consolidated strategies for a category."""
        return self.strategies.get(category, [])

    def update_usefulness(self, reflection_id: str, usefulness: float):
        """Update usefulness score based on feedback."""
        for reflections in self.long_term.values():
            for refl in reflections:
                if refl.reflection_id == reflection_id:
                    refl.usefulness = usefulness
                    return

    def _save_reflection(self, reflection: SelfReflection):
        """Save reflection to disk."""
        file_path = self.storage_dir / f"{reflection.reflection_id}.json"

        with open(file_path, 'w') as f:
            json.dump(asdict(reflection), f, indent=2, default=str)

    def _load(self):
        """Load reflections from disk."""
        if not self.storage_dir.exists():
            return

        for file_path in self.storage_dir.glob("refl_*.json"):
            try:
                with open(file_path) as f:
                    data = json.load(f)

                # Convert back to object
                reflection = SelfReflection(
                    reflection_id=data['reflection_id'],
                    task_prompt=data['task_prompt'],
                    task_category=data['task_category'],
                    attempt_number=data['attempt_number'],
                    reflection_type=ReflectionType(data['reflection_type']),
                    what_happened=data['what_happened'],
                    why_it_happened=data['why_it_happened'],
                    what_to_do_next=data['what_to_do_next'],
                    confidence=data.get('confidence', 0.5),
                    usefulness=data.get('usefulness', 0.0),
                    times_referenced=data.get('times_referenced', 0),
                    created_at=data.get('created_at', ''),
                    last_used=data.get('last_used', ''),
                    failed_approach=data.get('failed_approach'),
                    successful_approach=data.get('successful_approach')
                )

                self.long_term[reflection.task_category].append(reflection)

            except Exception as e:
                logger.warning(f"Failed to load reflection {file_path}: {e}")

    def get_stats(self) -> Dict:
        """Get memory statistics."""
        total_reflections = sum(len(refls) for refls in self.long_term.values())
        total_strategies = sum(len(strats) for strats in self.strategies.values())

        by_type = defaultdict(int)
        by_category = defaultdict(int)

        for reflections in self.long_term.values():
            for refl in reflections:
                by_type[refl.reflection_type.value] += 1
                by_category[refl.task_category] += 1

        return {
            'total_reflections': total_reflections,
            'total_strategies': total_strategies,
            'short_term_size': len(self.short_term),
            'by_type': dict(by_type),
            'by_category': dict(by_category)
        }


# ============================================================================
# EXPERIENCE REPLAY
# ============================================================================

class ExperienceReplay:
    """
    Stores and replays task execution trajectories for learning.

    Enables:
    - Learning from successful trajectories
    - Analyzing failure patterns
    - Building training datasets for future fine-tuning
    """

    def __init__(self, storage_dir: Path = Path("training/experiences")):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.trajectories: List[TaskTrajectory] = []

        # Success/failure indexes for efficient sampling
        self.successes: List[TaskTrajectory] = []
        self.failures: List[TaskTrajectory] = []

        self._load()

    def store_trajectory(self, trajectory: TaskTrajectory):
        """Store a task execution trajectory."""
        self.trajectories.append(trajectory)

        if trajectory.final_success:
            self.successes.append(trajectory)
        else:
            self.failures.append(trajectory)

        # Save to disk
        self._save_trajectory(trajectory)

    def sample_successes(self, n: int = 5, category: str = None) -> List[TaskTrajectory]:
        """Sample successful trajectories for learning."""
        candidates = self.successes

        if category:
            candidates = [t for t in candidates if t.task_category == category]

        # Sample recent and high-performing
        import random
        return random.sample(candidates, min(n, len(candidates)))

    def sample_failures(self, n: int = 5, category: str = None) -> List[TaskTrajectory]:
        """Sample failure trajectories for analysis."""
        candidates = self.failures

        if category:
            candidates = [t for t in candidates if t.task_category == category]

        import random
        return random.sample(candidates, min(n, len(candidates)))

    def analyze_failure_patterns(self) -> Dict[str, List[str]]:
        """Analyze common failure patterns across trajectories."""
        patterns = defaultdict(list)

        for trajectory in self.failures:
            category = trajectory.task_category

            # Extract common error types
            for attempt in trajectory.attempts:
                for error in attempt.errors:
                    if error not in patterns[category]:
                        patterns[category].append(error)

        return dict(patterns)

    def get_training_examples(self, min_quality: float = 0.7) -> List[Dict]:
        """
        Get high-quality examples for training/fine-tuning.

        Format suitable for LoRA training.
        """
        examples = []

        for trajectory in self.successes:
            # Skip low-quality trajectories
            if trajectory.total_attempts > 5:
                continue

            # Create training example
            example = {
                'prompt': trajectory.task_prompt,
                'category': trajectory.task_category,
                'domain': trajectory.task_domain,
                'successful_approach': trajectory.successful_strategies,
                'trajectory': [asdict(attempt) for attempt in trajectory.attempts],
                'reflections': [asdict(refl) for refl in trajectory.reflections],
                'key_insights': trajectory.key_insights
            }

            examples.append(example)

        return examples

    def _save_trajectory(self, trajectory: TaskTrajectory):
        """Save trajectory to disk."""
        file_path = self.storage_dir / f"{trajectory.trajectory_id}.json"

        with open(file_path, 'w') as f:
            json.dump(asdict(trajectory), f, indent=2, default=str)

    def _load(self):
        """Load trajectories from disk."""
        if not self.storage_dir.exists():
            return

        for file_path in self.storage_dir.glob("traj_*.json"):
            try:
                with open(file_path) as f:
                    data = json.load(f)

                # Convert back to object (simplified - would need full deserialization)
                trajectory = TaskTrajectory(
                    trajectory_id=data['trajectory_id'],
                    task_prompt=data['task_prompt'],
                    task_category=data['task_category'],
                    task_domain=data['task_domain'],
                    final_success=data['final_success'],
                    total_attempts=data['total_attempts'],
                    total_execution_time=data['total_execution_time'],
                    timestamp=data['timestamp']
                )

                self.trajectories.append(trajectory)

                if trajectory.final_success:
                    self.successes.append(trajectory)
                else:
                    self.failures.append(trajectory)

            except Exception as e:
                logger.warning(f"Failed to load trajectory {file_path}: {e}")

    def get_stats(self) -> Dict:
        """Get experience replay statistics."""
        return {
            'total_trajectories': len(self.trajectories),
            'successful_trajectories': len(self.successes),
            'failed_trajectories': len(self.failures),
            'success_rate': len(self.successes) / max(len(self.trajectories), 1),
            'avg_attempts': sum(t.total_attempts for t in self.trajectories) / max(len(self.trajectories), 1)
        }


# ============================================================================
# MAIN REFLEXION ENGINE
# ============================================================================

class ReflexionEngine:
    """
    Main Reflexion self-improvement loop.

    Implements: Attempt → Observe → Reflect → Store → Retry with Context

    Target performance:
    - 91%+ success on coding tasks
    - 97%+ success on decision-making tasks
    - Continuous improvement through reflection
    """

    def __init__(self, config: Dict):
        self.config = config

        # Components
        self.evaluator = TaskEvaluator(config)
        self.reflection_generator = ReflectionGenerator(config)
        self.memory = ReflexionMemory()
        self.experience_replay = ExperienceReplay()

        # Metrics
        self.metrics = ReflexionMetrics(
            start_time=datetime.now().isoformat()
        )

        # Configuration
        self.max_attempts = config.get('reflexion', {}).get('max_attempts', 5)
        self.reflection_threshold = config.get('reflexion', {}).get('reflection_threshold', 0.6)

    async def execute_with_reflexion(
        self,
        task_prompt: str,
        task_category: str,
        task_domain: str,
        executor: Callable,  # Function that executes the task
        evaluator_context: Dict = None
    ) -> Tuple[bool, str, List[SelfReflection]]:
        """
        Execute a task with reflexion loop.

        Args:
            task_prompt: The task to accomplish
            task_category: Category (navigation, extraction, etc.)
            task_domain: Domain (e-commerce, real-estate, etc.)
            executor: Async function(prompt, context) -> (output, tools_used)
            evaluator_context: Additional context for evaluation (page_content, etc.)

        Returns:
            (success, final_output, reflections_used)
        """

        trajectory = TaskTrajectory(
            trajectory_id=f"traj_{int(time.time()*1000)}",
            task_prompt=task_prompt,
            task_category=task_category,
            task_domain=task_domain,
            timestamp=datetime.now().isoformat()
        )

        attempts: List[TaskAttempt] = []
        reflections: List[SelfReflection] = []

        # Get relevant past reflections
        relevant_reflections = self.memory.get_relevant_reflections(
            task_category, task_prompt, limit=3
        )

        success = False
        final_output = ""

        for attempt_num in range(1, self.max_attempts + 1):
            logger.info(f"Reflexion attempt {attempt_num}/{self.max_attempts}")

            # Build context with reflections
            context = self._build_execution_context(
                task_prompt,
                relevant_reflections,
                reflections,  # Current trajectory reflections
                attempts
            )

            # Execute
            start_time = time.time()
            try:
                output, tools_used = await executor(context['enhanced_prompt'], context)
                final_output = output
                execution_time = time.time() - start_time

                # Record attempt
                attempt = TaskAttempt(
                    attempt_number=attempt_num,
                    action=f"Executed task with {len(tools_used)} tool calls",
                    observation=output[:500],
                    success=False,  # Will update after evaluation
                    execution_time=execution_time,
                    timestamp=datetime.now().isoformat(),
                    tool_calls=tools_used
                )
                attempts.append(attempt)

            except Exception as e:
                logger.error(f"Execution error: {e}")
                attempt = TaskAttempt(
                    attempt_number=attempt_num,
                    action=f"Execution failed",
                    observation=str(e),
                    success=False,
                    execution_time=time.time() - start_time,
                    timestamp=datetime.now().isoformat(),
                    errors=[str(e)]
                )
                attempts.append(attempt)
                final_output = f"Error: {e}"
                continue

            # Evaluate
            eval_ctx = evaluator_context or {}
            success, confidence, reasoning = await self.evaluator.evaluate_attempt(
                task_prompt,
                task_category,
                output,
                expected_outcome=eval_ctx.get('expected_outcome'),
                ground_truth=eval_ctx.get('ground_truth'),
                page_content=eval_ctx.get('page_content', ''),
                screenshot_path=eval_ctx.get('screenshot_path', '')
            )

            attempt.success = success

            logger.info(f"Evaluation: {'SUCCESS' if success else 'FAILURE'} "
                       f"(confidence: {confidence:.2f}) - {reasoning}")

            # Generate reflection
            reflection = await self.reflection_generator.generate_reflection(
                task_prompt,
                task_category,
                attempts,
                success,
                reflections
            )

            reflections.append(reflection)
            self.memory.add_reflection(reflection)

            # Update metrics
            self.metrics.total_attempts += 1
            self.metrics.reflections_generated += 1

            if success:
                logger.info(f"Task succeeded on attempt {attempt_num}")
                break

            # If last attempt, mark as failure
            if attempt_num == self.max_attempts:
                logger.warning(f"Task failed after {self.max_attempts} attempts")

        # Update trajectory
        trajectory.attempts = attempts
        trajectory.reflections = reflections
        trajectory.final_success = success
        trajectory.total_attempts = len(attempts)
        trajectory.total_execution_time = sum(a.execution_time for a in attempts)

        # Extract learnings
        if success:
            trajectory.successful_strategies = [r.what_to_do_next for r in reflections
                                               if r.reflection_type == ReflectionType.SUCCESS]
        else:
            trajectory.mistakes_made = [r.why_it_happened for r in reflections]

        # Store trajectory
        self.experience_replay.store_trajectory(trajectory)

        # Update metrics
        self.metrics.total_tasks += 1
        if success:
            self.metrics.successful_tasks += 1
        else:
            self.metrics.failed_tasks += 1

        if attempt_num == 1 and success:
            self.metrics.first_attempt_success_rate = (
                (self.metrics.first_attempt_success_rate * (self.metrics.total_tasks - 1) + 1.0)
                / self.metrics.total_tasks
            )

        self.metrics.final_success_rate = self.metrics.successful_tasks / self.metrics.total_tasks
        self.metrics.avg_attempts_to_success = (
            sum(len(t.attempts) for t in self.experience_replay.successes)
            / max(len(self.experience_replay.successes), 1)
        )

        # Update category performance
        if task_category not in self.metrics.category_performance:
            self.metrics.category_performance[task_category] = {
                'total': 0, 'successful': 0, 'avg_attempts': 0.0
            }

        cat_stats = self.metrics.category_performance[task_category]
        cat_stats['total'] += 1
        if success:
            cat_stats['successful'] += 1
        cat_stats['avg_attempts'] = (
            (cat_stats['avg_attempts'] * (cat_stats['total'] - 1) + len(attempts))
            / cat_stats['total']
        )

        self.metrics.last_update = datetime.now().isoformat()

        return success, final_output, reflections

    def _build_execution_context(
        self,
        task_prompt: str,
        relevant_reflections: List[SelfReflection],
        current_reflections: List[SelfReflection],
        previous_attempts: List[TaskAttempt]
    ) -> Dict:
        """
        Build execution context with reflection guidance.

        This is key to Reflexion: injecting verbal feedback into the execution.
        """

        # Start with base prompt
        enhanced_prompt = task_prompt

        # Add lessons from past similar tasks
        if relevant_reflections:
            lessons = "\n\nLessons from similar past tasks:\n"
            for i, refl in enumerate(relevant_reflections, 1):
                lessons += f"{i}. {refl.what_to_do_next}\n"

            enhanced_prompt += lessons

        # Add reflections from current attempts
        if current_reflections:
            feedback = "\n\nSelf-reflections from previous attempts:\n"
            for i, refl in enumerate(current_reflections, 1):
                feedback += f"\nAttempt {i} reflection:\n"
                feedback += f"- What happened: {refl.what_happened}\n"
                feedback += f"- Why: {refl.why_it_happened}\n"
                feedback += f"- What to do: {refl.what_to_do_next}\n"

            enhanced_prompt += feedback

        # Add specific guidance based on previous attempt failures
        if previous_attempts and not previous_attempts[-1].success:
            last_attempt = previous_attempts[-1]
            guidance = "\n\nBased on the last attempt failure:\n"
            guidance += f"- Previous action: {last_attempt.action}\n"
            guidance += f"- What didn't work: {last_attempt.observation[:200]}\n"

            if last_attempt.errors:
                guidance += f"- Errors: {', '.join(last_attempt.errors)}\n"

            guidance += "\nTry a different approach this time. Consider:\n"
            guidance += "- Using different tools or selectors\n"
            guidance += "- Changing the navigation path\n"
            guidance += "- Adding wait times or retries\n"
            guidance += "- Simplifying the approach\n"

            enhanced_prompt += guidance

        return {
            'enhanced_prompt': enhanced_prompt,
            'relevant_reflections': relevant_reflections,
            'current_reflections': current_reflections,
            'attempt_number': len(previous_attempts) + 1
        }

    async def consolidate_learnings(self) -> Dict:
        """
        Periodic consolidation of learnings into high-level strategies.

        Should be called periodically (e.g., after every 10 tasks).
        """
        logger.info("Starting learning consolidation...")

        # Consolidate reflections into strategies
        strategies_created = self.memory.consolidate_reflections()

        # Analyze failure patterns
        failure_patterns = self.experience_replay.analyze_failure_patterns()

        # Update reflection usefulness based on recent success
        # (Simple heuristic: successful tasks → useful reflections)
        recent_successes = self.experience_replay.sample_successes(n=10)
        for trajectory in recent_successes:
            for reflection in trajectory.reflections:
                # Increase usefulness of reflections from successful trajectories
                current_usefulness = reflection.usefulness
                updated = min(1.0, current_usefulness + 0.1)
                self.memory.update_usefulness(reflection.reflection_id, updated)

        logger.info(f"Consolidation complete: {strategies_created} strategies created")

        return {
            'strategies_created': strategies_created,
            'failure_patterns': failure_patterns,
            'reflections_updated': len(recent_successes)
        }

    def get_metrics(self) -> ReflexionMetrics:
        """Get current metrics."""
        return self.metrics

    def get_improvement_report(self) -> str:
        """Generate human-readable improvement report."""
        report = f"""
╔══════════════════════════════════════════════════════════════════╗
║                   REFLEXION IMPROVEMENT REPORT                   ║
╠══════════════════════════════════════════════════════════════════╣

Overall Performance:
- Total tasks: {self.metrics.total_tasks}
- Successful: {self.metrics.successful_tasks} ({self.metrics.final_success_rate*100:.1f}%)
- Failed: {self.metrics.failed_tasks}

Learning Efficiency:
- First attempt success rate: {self.metrics.first_attempt_success_rate*100:.1f}%
- Final success rate: {self.metrics.final_success_rate*100:.1f}%
- Improvement: +{(self.metrics.final_success_rate - self.metrics.first_attempt_success_rate)*100:.1f}%
- Average attempts to success: {self.metrics.avg_attempts_to_success:.1f}

Reflection System:
- Reflections generated: {self.metrics.reflections_generated}
- Reflections used: {self.metrics.reflections_used}
- Memory stats: {self.memory.get_stats()}

Experience Replay:
{json.dumps(self.experience_replay.get_stats(), indent=2)}

Performance by Category:
"""
        for category, stats in self.metrics.category_performance.items():
            success_rate = stats['successful'] / max(stats['total'], 1) * 100
            report += f"  {category:20} {stats['successful']:3}/{stats['total']:3} "
            report += f"({success_rate:.0f}%) avg {stats['avg_attempts']:.1f} attempts\n"

        report += "\n╚══════════════════════════════════════════════════════════════════╝"

        return report

    def save_state(self):
        """Save reflexion state to disk."""
        state_path = Path("memory/reflexion/reflexion_state.json")
        state_path.parent.mkdir(parents=True, exist_ok=True)

        with open(state_path, 'w') as f:
            json.dump(asdict(self.metrics), f, indent=2, default=str)

        logger.info(f"Reflexion state saved to {state_path}")

    def load_state(self):
        """Load reflexion state from disk."""
        state_path = Path("memory/reflexion/reflexion_state.json")

        if not state_path.exists():
            return

        try:
            with open(state_path) as f:
                data = json.load(f)

            # Restore metrics (partial - simplified)
            self.metrics.total_tasks = data.get('total_tasks', 0)
            self.metrics.successful_tasks = data.get('successful_tasks', 0)
            self.metrics.failed_tasks = data.get('failed_tasks', 0)
            self.metrics.total_attempts = data.get('total_attempts', 0)

            logger.info("Reflexion state loaded from disk")

        except Exception as e:
            logger.warning(f"Failed to load reflexion state: {e}")


# ============================================================================
# INTEGRATION WITH EXISTING SYSTEMS
# ============================================================================

async def integrate_with_brain(
    brain_instance,
    task_prompt: str,
    task_category: str = "general",
    task_domain: str = "general"
) -> Tuple[bool, str]:
    """
    Integration helper for brain_enhanced_v2.py

    Usage in brain:
        from agent.reflexion import integrate_with_brain

        success, output = await integrate_with_brain(
            self, task_prompt, task_category, task_domain
        )
    """
    config = brain_instance.config if hasattr(brain_instance, 'config') else {}

    reflexion = ReflexionEngine(config)

    # Define executor that wraps brain's run method
    async def executor(prompt: str, context: Dict) -> Tuple[str, List]:
        output = await brain_instance.run(prompt)
        tools = brain_instance.get_stats().get('tool_calls', [])
        return output, tools

    # Get evaluation context from brain
    eval_context = {}
    if hasattr(brain_instance, 'mcp') and brain_instance.mcp:
        try:
            # Try to get page state for evaluation
            page_text = await brain_instance.mcp.call_tool('playwright_get_text', {'selector': 'body'})
            eval_context['page_content'] = str(page_text) if page_text else ""
        except:
            pass

    # Execute with reflexion
    success, output, reflections = await reflexion.execute_with_reflexion(
        task_prompt,
        task_category,
        task_domain,
        executor,
        eval_context
    )

    # Log improvement report periodically
    if reflexion.metrics.total_tasks % 10 == 0:
        logger.info(reflexion.get_improvement_report())
        reflexion.save_state()

    return success, output


def integrate_with_self_healing(reflexion_engine: ReflexionEngine):
    """
    Integration with self_healing_system.py

    Reflexion can provide learned strategies to self-healing.
    """
    from .self_healing_system import self_healing

    # Export strategies from reflexion to self-healing
    for category, strategies in reflexion_engine.memory.strategies.items():
        for strategy in strategies:
            # Convert to self-healing format
            self_healing.success_strategies[category].append({
                'action': 'reflexion_learned',
                'strategy': strategy,
                'source': 'reflexion_consolidation'
            })

    logger.info("Integrated reflexion strategies with self-healing system")


# ============================================================================
# CLI / TESTING
# ============================================================================

async def test_reflexion():
    """Test the reflexion system."""

    # Mock config
    config = {
        'llm': {
            'main_model': '0000/ui-tars-1.5-7b:latest',
            'router_model': '0000/ui-tars-1.5-7b:latest'
        },
        'reflexion': {
            'max_attempts': 3,
            'reflection_threshold': 0.6
        }
    }

    reflexion = ReflexionEngine(config)

    # Mock executor (simulates task execution)
    async def mock_executor(prompt: str, context: Dict) -> Tuple[str, List]:
        attempt = context.get('attempt_number', 1)

        # Fail first attempt, succeed on retry
        if attempt == 1:
            return "Failed: Could not find element", []
        else:
            return "Success: Navigated to page and extracted data: email@example.com", [
                {'tool': 'playwright_navigate', 'args': {'url': 'https://example.com'}},
                {'tool': 'playwright_extract_page_fast', 'args': {}}
            ]

    # Run test task
    success, output, reflections = await reflexion.execute_with_reflexion(
        task_prompt="Navigate to example.com and extract contact information",
        task_category="extraction",
        task_domain="general",
        executor=mock_executor,
        evaluator_context={'page_content': 'Contact: email@example.com'}
    )

    print("\n" + "="*70)
    print("REFLEXION TEST RESULTS")
    print("="*70)
    print(f"Success: {success}")
    print(f"Output: {output}")
    print(f"Reflections generated: {len(reflections)}")

    for i, refl in enumerate(reflections, 1):
        print(f"\nReflection {i}:")
        print(f"  Type: {refl.reflection_type.value}")
        print(f"  What happened: {refl.what_happened[:100]}")
        print(f"  Why: {refl.why_it_happened[:100]}")
        print(f"  What to do: {refl.what_to_do_next[:100]}")

    print("\n" + reflexion.get_improvement_report())


if __name__ == "__main__":
    asyncio.run(test_reflexion())
