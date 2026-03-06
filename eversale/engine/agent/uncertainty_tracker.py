#!/usr/bin/env python3
"""
Uncertainty Tracker - Know When to Ask for Help

This is critical to AGI organism safety: confident agents that are wrong cause damage.
Uncertain agents that know they're uncertain ask for help.

Purpose:
- Track confidence levels for every decision
- Calibrate confidence estimates against actual outcomes
- Decide when to proceed vs. when to ask for help
- Explain uncertainty in human-readable terms

Integration:
- Called before executing any significant action
- Works with self_model for capability awareness
- Uses memory_architecture for similarity matching
- Subscribes to EventBus for outcome tracking
- Triggers user prompts when help is needed

Confidence Factors:
1. Memory familiarity (30%) - have we seen this before?
2. Instruction clarity (20%) - is the request clear?
3. Tools available (20%) - do we have what we need?
4. Recent success rate (20%) - how well are similar tasks going?
5. Self-model confidence (10%) - what does our capability model say?
6. Multi-model agreement (bonus) - do multiple models agree?

Multi-Model Confidence:
- When ModelOrchestrator returns results from 2+ models:
  * 2 models agree: +15% confidence boost
  * 3 models agree: +25% confidence boost
  * Models disagree: -10% confidence penalty
- Uses semantic similarity to detect partial agreement (threshold: 0.7)
- Tracks historical agreement rates per model pair
- Integrates with EventBus to automatically track model consensus

Decision Thresholds:
- confidence > 0.7: Proceed confidently
- 0.4 < confidence < 0.7: Proceed with verification
- confidence < 0.4: Ask for help

Calibration:
- Tracks predicted confidence vs. actual success
- Adjusts estimates if consistently over/under-confident
- Maintains calibration curve for transparency
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import deque, defaultdict
from loguru import logger
import sqlite3
import threading

# For text similarity calculations
try:
    import difflib
    DIFFLIB_AVAILABLE = True
except ImportError:
    DIFFLIB_AVAILABLE = False

# For semantic similarity (optional)
try:
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.feature_extraction.text import TfidfVectorizer
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


# ============================================================================
# CONFIGURATION
# ============================================================================

MEMORY_DIR = Path("memory")
MEMORY_DIR.mkdir(exist_ok=True)

UNCERTAINTY_DB = MEMORY_DIR / "uncertainty_tracker.db"
CALIBRATION_JSON = MEMORY_DIR / "confidence_calibration.json"

# Confidence thresholds
CONFIDENCE_HIGH = 0.7  # Proceed confidently
CONFIDENCE_LOW = 0.4   # Ask for help

# Confidence factor weights
FACTOR_WEIGHTS = {
    "seen_similar_before": 0.3,
    "clear_instructions": 0.2,
    "tools_available": 0.2,
    "recent_success_rate": 0.2,
    "self_model_confidence": 0.1
}

# Multi-model confidence boosts
MULTI_MODEL_AGREEMENT_BOOST = {
    2: 0.15,  # 2 models agree: +15%
    3: 0.25,  # 3 models agree: +25%
    4: 0.35,  # 4+ models agree: +35%
}
MULTI_MODEL_DISAGREEMENT_PENALTY = 0.10  # Models disagree: -10%
PARTIAL_AGREEMENT_THRESHOLD = 0.7  # Semantic similarity threshold for partial agreement

# Calibration parameters
CALIBRATION_BINS = 10  # Divide confidence range into 10 bins
CALIBRATION_WINDOW = 100  # Last 100 decisions for calibration


# ============================================================================
# DATA STRUCTURES
# ============================================================================

class ActionType(Enum):
    """Recommended action based on confidence level."""
    PROCEED = "proceed"
    PROCEED_WITH_VERIFICATION = "proceed_with_verification"
    ASK_FOR_HELP = "ask_for_help"
    ASK_FOR_CLARIFICATION = "ask_for_clarification"


@dataclass
class Action:
    """Recommended action with reasoning."""
    action_type: ActionType
    reason: str = ""
    confidence: float = 0.0
    uncertain_aspects: List[str] = field(default_factory=list)
    suggested_questions: List[str] = field(default_factory=list)


@dataclass
class ConfidenceFactors:
    """Individual factors contributing to confidence."""
    seen_similar_before: float = 0.0
    clear_instructions: float = 0.0
    tools_available: float = 0.0
    recent_success_rate: float = 0.0
    self_model_confidence: float = 0.0
    multi_model_agreement: float = 0.0  # NEW: Multi-model agreement factor

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class Decision:
    """A decision to assess for uncertainty."""
    decision_id: str
    task_description: str
    proposed_action: str
    tool: Optional[str] = None
    arguments: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class DecisionOutcome:
    """Outcome of a decision for calibration."""
    decision_id: str
    predicted_confidence: float
    actual_success: bool
    error_message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CalibrationBin:
    """Statistics for a confidence bin."""
    bin_range: Tuple[float, float]
    predicted_confidence_avg: float = 0.0
    actual_success_rate: float = 0.0
    count: int = 0
    calibration_error: float = 0.0  # abs(predicted - actual)


# ============================================================================
# UNCERTAINTY TRACKER
# ============================================================================

class UncertaintyTracker:
    """
    Track confidence levels and decide when to ask for help.

    This is the safety layer that prevents overconfident failures.
    """

    def __init__(
        self,
        memory_arch=None,
        self_model=None,
        event_bus=None,
        confidence_high: float = CONFIDENCE_HIGH,
        confidence_low: float = CONFIDENCE_LOW
    ):
        """
        Initialize uncertainty tracker.

        Args:
            memory_arch: MemoryArchitecture instance for similarity matching
            self_model: SelfModel instance for capability awareness
            event_bus: EventBus instance for outcome tracking
            confidence_high: Threshold for confident proceed (default 0.7)
            confidence_low: Threshold for asking help (default 0.4)
        """
        self.memory = memory_arch
        self.self_model = self_model
        self.event_bus = event_bus

        self.confidence_threshold_high = confidence_high
        self.confidence_threshold_low = confidence_low

        # Decision history
        self._decisions: Dict[str, Decision] = {}
        self._outcomes: deque[DecisionOutcome] = deque(maxlen=CALIBRATION_WINDOW)

        # Recent success tracking
        self._recent_successes: deque[bool] = deque(maxlen=20)

        # Multi-model agreement tracking
        self._model_agreements: Dict[Tuple[str, str], List[bool]] = defaultdict(lambda: deque(maxlen=50))
        self._agreement_rates: Dict[Tuple[str, str], float] = {}

        # Calibration data
        self._calibration_bins: List[CalibrationBin] = self._init_calibration_bins()
        self._calibration_adjustment = 0.0  # Global adjustment factor

        # Thread safety
        self._lock = threading.Lock()

        # Persistence
        self._init_db()
        self._load_calibration()

        # Subscribe to outcome events if event bus available
        if self.event_bus:
            self._subscribe_to_events()

    def _init_calibration_bins(self) -> List[CalibrationBin]:
        """Initialize calibration bins."""
        bins = []
        bin_size = 1.0 / CALIBRATION_BINS
        for i in range(CALIBRATION_BINS):
            bin_start = i * bin_size
            bin_end = (i + 1) * bin_size
            bins.append(CalibrationBin(
                bin_range=(bin_start, bin_end)
            ))
        return bins

    def _init_db(self):
        """Initialize SQLite database for persistence."""
        with sqlite3.connect(str(UNCERTAINTY_DB)) as conn:
            # Create tables separately (SQLite executes one statement at a time)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS decisions (
                    decision_id TEXT PRIMARY KEY,
                    task_description TEXT,
                    proposed_action TEXT,
                    predicted_confidence REAL,
                    actual_success INTEGER,
                    timestamp TEXT,
                    factors TEXT,
                    context TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_decisions_timestamp
                ON decisions(timestamp DESC)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS model_agreements (
                    task_id TEXT,
                    model_a TEXT,
                    model_b TEXT,
                    agreed BOOLEAN,
                    similarity_score REAL,
                    timestamp TEXT,
                    PRIMARY KEY (task_id, model_a, model_b)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_agreements_models
                ON model_agreements(model_a, model_b)
            """)
            conn.commit()

    def _subscribe_to_events(self):
        """Subscribe to event bus for outcome tracking."""
        from .organism_core import EventType

        async def on_action_complete(event):
            """Handle successful action completion."""
            decision_id = event.data.get("decision_id")
            if decision_id and decision_id in self._decisions:
                self.record_outcome(decision_id, success=True)

            # Track multi-model agreement if available
            model_results = event.data.get("model_results")
            if model_results and len(model_results) >= 2:
                task_id = event.data.get("task_id", decision_id)
                models_used = list(model_results.keys())

                # Calculate agreement
                similarity = self.calculate_multi_model_confidence(model_results)
                agreed = similarity >= PARTIAL_AGREEMENT_THRESHOLD

                self.track_model_agreement(
                    task_id=task_id,
                    models=models_used,
                    agreed=agreed,
                    similarity_score=similarity
                )

        async def on_action_failed(event):
            """Handle failed action."""
            decision_id = event.data.get("decision_id")
            error = event.data.get("error", "Unknown error")
            if decision_id and decision_id in self._decisions:
                self.record_outcome(decision_id, success=False, error=error)

        self.event_bus.subscribe(EventType.ACTION_COMPLETE, on_action_complete)
        self.event_bus.subscribe(EventType.ACTION_FAILED, on_action_failed)

    # ========================================================================
    # CORE ASSESSMENT
    # ========================================================================

    def assess(
        self,
        decision: Decision,
        model_results: Optional[Dict[str, Any]] = None
    ) -> Action:
        """
        Assess a decision and return recommended action.

        Args:
            decision: The decision to assess
            model_results: Optional multi-model results for confidence boosting

        Returns:
            Action with recommendation (proceed/verify/ask_for_help)
        """
        # Calculate confidence
        confidence, factors = self.calculate_confidence(decision, model_results)

        # Apply calibration adjustment
        adjusted_confidence = self._apply_calibration(confidence)

        # Store decision for outcome tracking
        with self._lock:
            self._decisions[decision.decision_id] = decision

        # Determine action based on confidence
        if adjusted_confidence >= self.confidence_threshold_high:
            # High confidence - proceed
            return Action(
                action_type=ActionType.PROCEED,
                confidence=adjusted_confidence,
                reason=f"High confidence ({adjusted_confidence:.1%}). Proceeding with action."
            )

        elif adjusted_confidence >= self.confidence_threshold_low:
            # Medium confidence - proceed with verification
            uncertain_aspects = self._identify_uncertain_aspects(factors)
            return Action(
                action_type=ActionType.PROCEED_WITH_VERIFICATION,
                confidence=adjusted_confidence,
                reason=f"Moderate confidence ({adjusted_confidence:.1%}). Will verify outcome.",
                uncertain_aspects=uncertain_aspects
            )

        else:
            # Low confidence - ask for help
            uncertain_aspects = self._identify_uncertain_aspects(factors)
            questions = self._generate_clarifying_questions(decision, factors)

            return Action(
                action_type=ActionType.ASK_FOR_HELP,
                confidence=adjusted_confidence,
                reason=self.explain_uncertainty(decision, factors),
                uncertain_aspects=uncertain_aspects,
                suggested_questions=questions
            )

    def calculate_confidence(
        self,
        decision: Decision,
        model_results: Optional[Dict[str, Any]] = None
    ) -> Tuple[float, ConfidenceFactors]:
        """
        Calculate confidence from multiple factors.

        Args:
            decision: The decision to assess
            model_results: Optional multi-model results for agreement-based boosting

        Returns:
            (confidence_score, individual_factors)
        """
        factors = ConfidenceFactors()

        # 1. Seen similar before (memory similarity)
        factors.seen_similar_before = self._assess_memory_similarity(decision)

        # 2. Clear instructions (parse clarity)
        factors.clear_instructions = self._assess_instruction_clarity(decision)

        # 3. Tools available (capability match)
        factors.tools_available = self._assess_tools_available(decision)

        # 4. Recent success rate
        factors.recent_success_rate = self._assess_recent_success()

        # 5. Self-model confidence
        factors.self_model_confidence = self._assess_self_model(decision)

        # 6. Multi-model agreement (if available)
        if model_results and len(model_results) >= 2:
            factors.multi_model_agreement = self.calculate_multi_model_confidence(model_results)
        else:
            factors.multi_model_agreement = 0.0

        # Weighted combination (base factors only)
        base_confidence = sum(
            getattr(factors, factor) * weight
            for factor, weight in FACTOR_WEIGHTS.items()
        )

        # Apply multi-model boost/penalty if available
        if factors.multi_model_agreement > 0:
            # Multi-model agreement modifies the base confidence
            num_models = len(model_results) if model_results else 0
            avg_similarity = factors.multi_model_agreement

            if avg_similarity >= PARTIAL_AGREEMENT_THRESHOLD:
                # Models agree - boost confidence
                boost = MULTI_MODEL_AGREEMENT_BOOST.get(
                    num_models,
                    MULTI_MODEL_AGREEMENT_BOOST.get(max(MULTI_MODEL_AGREEMENT_BOOST.keys()))
                )
                confidence = base_confidence + boost
            else:
                # Models disagree - penalty
                confidence = base_confidence - MULTI_MODEL_DISAGREEMENT_PENALTY
        else:
            confidence = base_confidence

        # Clamp to [0, 1]
        confidence = max(0.0, min(1.0, confidence))

        return confidence, factors

    def _assess_memory_similarity(self, decision: Decision) -> float:
        """
        Check if we've seen similar tasks before.
        Returns 0.0-1.0 based on similarity to past successful tasks.
        """
        if not self.memory:
            return 0.5  # Neutral if no memory available

        try:
            # Search episodic memory for similar tasks
            episodes = self.memory.search_episodes(
                query=decision.task_description,
                limit=5,
                success_only=True
            )

            if not episodes:
                return 0.3  # Low confidence if no similar experiences

            # Calculate average similarity (using composite scores as proxy)
            avg_score = sum(ep.composite_score for ep in episodes) / len(episodes)

            # Boost if we have multiple similar experiences
            familiarity_boost = min(len(episodes) / 5, 0.2)

            return min(avg_score + familiarity_boost, 1.0)

        except Exception as e:
            logger.debug(f"Memory similarity check failed: {e}")
            return 0.5

    def _assess_instruction_clarity(self, decision: Decision) -> float:
        """
        Assess how clear and specific the instructions are.
        Returns 0.0-1.0 based on clarity indicators.
        """
        text = decision.task_description + " " + decision.proposed_action
        text_lower = text.lower()

        score = 0.5  # Start neutral

        # Positive indicators (specific, clear)
        clarity_keywords = [
            "extract", "navigate", "click", "find", "search",
            "download", "upload", "fill", "submit", "select"
        ]
        for keyword in clarity_keywords:
            if keyword in text_lower:
                score += 0.05

        # Check for specific details (URLs, selectors, numbers)
        if any(pattern in text for pattern in ["http://", "https://", "www."]):
            score += 0.1  # URL specified

        if any(pattern in text for pattern in [".", "#", "[", "{"]):
            score += 0.1  # Selector specified

        if any(char.isdigit() for char in text):
            score += 0.05  # Numbers/specifics mentioned

        # Negative indicators (vague, ambiguous)
        vague_keywords = [
            "maybe", "perhaps", "try", "see if", "figure out",
            "somehow", "whatever", "anything", "something"
        ]
        for keyword in vague_keywords:
            if keyword in text_lower:
                score -= 0.1

        # Check for question marks (indicates uncertainty in request)
        if "?" in text:
            score -= 0.05

        return max(0.0, min(1.0, score))

    def _assess_tools_available(self, decision: Decision) -> float:
        """
        Check if we have the tools needed for this task.
        Returns 0.0-1.0 based on tool availability.
        """
        if not decision.tool:
            # No specific tool mentioned - check if we can infer
            text_lower = decision.task_description.lower()

            # Check for tool-related keywords
            tool_hints = {
                "navigate": ["navigate", "go to", "visit", "open"],
                "click": ["click", "press", "button"],
                "extract": ["extract", "get", "scrape", "find"],
                "fill": ["fill", "enter", "type", "input"],
                "screenshot": ["screenshot", "capture", "image"]
            }

            # If we can infer a likely tool, medium confidence
            for tool, keywords in tool_hints.items():
                if any(kw in text_lower for kw in keywords):
                    return 0.7

            return 0.5  # Neutral if can't determine tool needs

        # Check if the tool is in our known capabilities
        # (In real implementation, would check against available Playwright tools)
        known_tools = [
            "playwright_navigate", "playwright_click", "playwright_fill",
            "playwright_extract_page_fast", "playwright_snapshot",
            "playwright_screenshot", "playwright_extract_fb_ads",
            "playwright_batch_extract"
        ]

        if decision.tool in known_tools:
            return 1.0  # We have this tool
        elif decision.tool.startswith("playwright_"):
            return 0.8  # Playwright tool, probably available
        else:
            return 0.3  # Unknown tool, low confidence

    def _assess_recent_success(self) -> float:
        """
        Calculate success rate of recent actions.
        Returns 0.0-1.0 based on recent performance.
        """
        if not self._recent_successes:
            return 0.6  # Neutral baseline

        success_rate = sum(self._recent_successes) / len(self._recent_successes)
        return success_rate

    def _assess_self_model(self, decision: Decision) -> float:
        """
        Check what the self-model says about our capability.
        Returns 0.0-1.0 based on self-assessed capability.
        """
        if not self.self_model:
            return 0.5  # Neutral if no self-model

        try:
            # Check if self-model has a capability assessment method
            if hasattr(self.self_model, 'assess_capability'):
                capability = self.self_model.assess_capability(
                    decision.task_description
                )
                return capability

            # Fallback: check known capabilities
            if hasattr(self.self_model, 'can_handle'):
                can_handle = self.self_model.can_handle(
                    decision.task_description
                )
                return 1.0 if can_handle else 0.3

            return 0.5  # Neutral if no assessment method

        except Exception as e:
            logger.debug(f"Self-model assessment failed: {e}")
            return 0.5

    # ========================================================================
    # MULTI-MODEL CONFIDENCE TRACKING
    # ========================================================================

    def calculate_multi_model_confidence(self, model_results: Dict[str, Any]) -> float:
        """
        Calculate confidence based on multi-model agreement.

        Args:
            model_results: Dict mapping model names to their outputs
                          e.g., {"kimi_k2": plan_obj, "chatgpt": plan_obj, "browser": text}

        Returns:
            Confidence score 0.0-1.0 based on agreement
            - 2 models agree: base +15%
            - 3 models agree: base +25%
            - Models disagree: base -10%
            - Uses semantic similarity for partial agreement

        Example:
            >>> results = {
            ...     "kimi_k2": "Navigate to example.com and extract data",
            ...     "chatgpt": "Navigate to example.com and scrape content",
            ...     "browser": "Go to example.com"
            ... }
            >>> confidence = tracker.calculate_multi_model_confidence(results)
            >>> # Returns higher confidence due to semantic agreement
        """
        if not model_results or len(model_results) < 2:
            return 0.0  # No multi-model comparison possible

        # Convert all results to comparable strings
        model_texts = {}
        for model_name, result in model_results.items():
            model_texts[model_name] = self._extract_comparable_text(result)

        # Calculate pairwise similarities
        model_names = list(model_texts.keys())
        agreements = []
        similarities = []

        for i, model_a in enumerate(model_names):
            for model_b in model_names[i+1:]:
                text_a = model_texts[model_a]
                text_b = model_texts[model_b]

                similarity = self._calculate_semantic_similarity(text_a, text_b)
                similarities.append(similarity)

                # Check historical agreement rate for this pair
                pair_key = tuple(sorted([model_a, model_b]))
                historical_rate = self._agreement_rates.get(pair_key, 0.7)

                # Weighted agreement: 70% current similarity, 30% historical
                weighted_similarity = similarity * 0.7 + historical_rate * 0.3
                agreements.append(weighted_similarity)

        if not agreements:
            return 0.0

        # Calculate average agreement
        avg_agreement = sum(agreements) / len(agreements)

        # Determine confidence boost/penalty
        num_models = len(model_results)
        base_confidence = avg_agreement

        if avg_agreement >= PARTIAL_AGREEMENT_THRESHOLD:
            # Models agree - apply boost
            boost = MULTI_MODEL_AGREEMENT_BOOST.get(
                num_models,
                MULTI_MODEL_AGREEMENT_BOOST.get(max(MULTI_MODEL_AGREEMENT_BOOST.keys()))
            )
            confidence = min(1.0, base_confidence + boost)

            logger.debug(
                f"Multi-model agreement: {num_models} models, "
                f"avg similarity {avg_agreement:.2f}, boost +{boost:.2f}"
            )
        else:
            # Models disagree - apply penalty
            confidence = max(0.0, base_confidence - MULTI_MODEL_DISAGREEMENT_PENALTY)

            logger.debug(
                f"Multi-model disagreement: {num_models} models, "
                f"avg similarity {avg_agreement:.2f}, penalty -{MULTI_MODEL_DISAGREEMENT_PENALTY:.2f}"
            )

        return confidence

    def track_model_agreement(
        self,
        task_id: str,
        models: List[str],
        agreed: bool,
        similarity_score: Optional[float] = None
    ):
        """
        Track historical agreement rates between model pairs.

        Args:
            task_id: Unique task identifier
            models: List of model names (must be 2+ models)
            agreed: Whether the models agreed on the output
            similarity_score: Optional similarity score (0.0-1.0)

        Example:
            >>> tracker.track_model_agreement(
            ...     task_id="task_123",
            ...     models=["kimi_k2", "chatgpt"],
            ...     agreed=True,
            ...     similarity_score=0.85
            ... )
        """
        if len(models) < 2:
            logger.warning(f"track_model_agreement requires 2+ models, got {len(models)}")
            return

        timestamp = datetime.now().isoformat()

        with self._lock:
            # Track all pairwise combinations
            for i, model_a in enumerate(models):
                for model_b in models[i+1:]:
                    # Standardize pair key (alphabetical order)
                    pair_key = tuple(sorted([model_a, model_b]))

                    # Update in-memory tracking
                    self._model_agreements[pair_key].append(agreed)

                    # Recalculate agreement rate for this pair
                    agreements_list = self._model_agreements[pair_key]
                    if agreements_list:
                        agreement_rate = sum(agreements_list) / len(agreements_list)
                        self._agreement_rates[pair_key] = agreement_rate

                        logger.debug(
                            f"Model pair {model_a} <-> {model_b}: "
                            f"agreement rate {agreement_rate:.1%} "
                            f"(n={len(agreements_list)})"
                        )

                    # Persist to database
                    try:
                        with sqlite3.connect(str(UNCERTAINTY_DB)) as conn:
                            conn.execute("""
                                INSERT OR REPLACE INTO model_agreements
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (
                                task_id,
                                model_a,
                                model_b,
                                int(agreed),
                                similarity_score or (1.0 if agreed else 0.0),
                                timestamp
                            ))
                            conn.commit()
                    except Exception as e:
                        logger.warning(f"Failed to persist model agreement: {e}")

    def _extract_comparable_text(self, result: Any) -> str:
        """
        Extract comparable text from various result types.

        Handles:
        - TaskPlan objects (from Kimi K2)
        - Dict objects (from ChatGPT)
        - String objects
        - Other types (converted to string)
        """
        if result is None:
            return ""

        # String
        if isinstance(result, str):
            return result

        # Dict (likely from ChatGPT)
        if isinstance(result, dict):
            # Extract relevant fields
            parts = []
            if "summary" in result:
                parts.append(result["summary"])
            if "steps" in result:
                steps = result["steps"]
                if isinstance(steps, list):
                    for step in steps[:5]:  # First 5 steps
                        if isinstance(step, dict):
                            parts.append(step.get("action", ""))
                        else:
                            parts.append(str(step))
            if "success_criteria" in result:
                parts.append(result["success_criteria"])

            return " ".join(parts)

        # TaskPlan object (from Kimi K2)
        if hasattr(result, "summary") and hasattr(result, "steps"):
            parts = [result.summary]
            for step in result.steps[:5]:  # First 5 steps
                if hasattr(step, "action"):
                    parts.append(step.action)
            return " ".join(parts)

        # Fallback: convert to string
        return str(result)[:500]  # Truncate for safety

    def _calculate_semantic_similarity(self, text_a: str, text_b: str) -> float:
        """
        Calculate semantic similarity between two texts.

        Uses TF-IDF + cosine similarity if sklearn available,
        otherwise falls back to difflib SequenceMatcher.

        Returns:
            Similarity score 0.0-1.0
        """
        if not text_a or not text_b:
            return 0.0

        # Normalize texts
        text_a = text_a.lower().strip()
        text_b = text_b.lower().strip()

        if text_a == text_b:
            return 1.0

        # Try TF-IDF + cosine similarity (more semantic)
        if SKLEARN_AVAILABLE:
            try:
                vectorizer = TfidfVectorizer(
                    stop_words='english',
                    max_features=100
                )
                vectors = vectorizer.fit_transform([text_a, text_b])
                similarity_matrix = cosine_similarity(vectors)
                return float(similarity_matrix[0, 1])
            except Exception as e:
                logger.debug(f"TF-IDF similarity failed: {e}")
                # Fall through to difflib

        # Fallback: difflib (simpler, more syntactic)
        if DIFFLIB_AVAILABLE:
            return difflib.SequenceMatcher(None, text_a, text_b).ratio()

        # Final fallback: crude word overlap
        words_a = set(text_a.split())
        words_b = set(text_b.split())
        if not words_a or not words_b:
            return 0.0

        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union) if union else 0.0

    def get_model_agreement_stats(self) -> Dict[str, Any]:
        """
        Get statistics on model agreement rates.

        Returns:
            Dict with agreement rates for each model pair
        """
        with self._lock:
            stats = {
                "total_pairs": len(self._agreement_rates),
                "pair_rates": {},
                "overall_agreement": 0.0,
            }

            for pair_key, rate in self._agreement_rates.items():
                model_a, model_b = pair_key
                pair_name = f"{model_a} <-> {model_b}"
                agreements_list = self._model_agreements.get(pair_key, [])

                stats["pair_rates"][pair_name] = {
                    "agreement_rate": round(rate, 3),
                    "sample_size": len(agreements_list),
                    "recent_agreements": sum(list(agreements_list)[-10:]),
                    "recent_total": min(len(agreements_list), 10),
                }

            # Calculate overall agreement across all pairs
            if self._agreement_rates:
                stats["overall_agreement"] = round(
                    sum(self._agreement_rates.values()) / len(self._agreement_rates),
                    3
                )

            return stats

    # ========================================================================
    # UNCERTAINTY EXPLANATION
    # ========================================================================

    def explain_uncertainty(self, decision: Decision, factors: ConfidenceFactors) -> str:
        """
        Generate human-readable explanation of uncertainty sources.

        Args:
            decision: The decision being assessed
            factors: Individual confidence factors

        Returns:
            Human-readable explanation string
        """
        explanations = []

        factors_dict = factors.to_dict()

        # Identify low-scoring factors
        for factor_name, score in factors_dict.items():
            if score < 0.5:
                explanation = self._explain_factor(factor_name, score, decision)
                if explanation:
                    explanations.append(explanation)

        if not explanations:
            return "Low overall confidence despite individual factors being acceptable."

        return " ".join(explanations)

    def _explain_factor(self, factor_name: str, score: float, decision: Decision) -> str:
        """Explain why a specific factor has low confidence."""
        explanations = {
            "seen_similar_before":
                f"I haven't encountered a task like '{decision.task_description[:50]}...' before ({score:.0%} familiarity).",

            "clear_instructions":
                f"The instructions seem unclear or vague ({score:.0%} clarity). I'm not sure exactly what's expected.",

            "tools_available":
                f"I'm uncertain if I have the right tools for this task ({score:.0%} tool confidence).",

            "recent_success_rate":
                f"My recent performance has been inconsistent ({score:.0%} success rate), so I'm less confident.",

            "self_model_confidence":
                f"Based on my self-assessment, this task seems outside my core capabilities ({score:.0%} self-confidence).",

            "multi_model_agreement":
                f"Multiple models produced conflicting results ({score:.0%} agreement), suggesting uncertainty in the approach."
        }

        return explanations.get(factor_name, "")

    def flag_uncertain_regions(self, context: str) -> List[str]:
        """
        Identify specific parts of a task that are uncertain.

        Args:
            context: Task context or description

        Returns:
            List of uncertain aspects
        """
        uncertain = []

        context_lower = context.lower()

        # Check for vague language
        vague_patterns = [
            ("maybe", "Uncertain whether to proceed"),
            ("perhaps", "Ambiguous intention"),
            ("try", "Exploratory action without clear success criteria"),
            ("see if", "Conditional action with unclear outcome"),
            ("figure out", "Problem-solving required without clear method"),
            ("somehow", "Missing crucial implementation details"),
            ("whatever", "Unspecified parameters or targets"),
            ("something", "Non-specific target or action")
        ]

        for pattern, explanation in vague_patterns:
            if pattern in context_lower:
                uncertain.append(f"{explanation} ('{pattern}' detected)")

        # Check for missing specifics
        if not any(char.isdigit() for char in context):
            if any(word in context_lower for word in ["find", "search", "get", "extract"]):
                uncertain.append("No specific count or limit specified for extraction")

        # Check for missing URL/target
        if any(word in context_lower for word in ["navigate", "visit", "go to"]):
            if not any(pattern in context for pattern in ["http://", "https://", "www."]):
                uncertain.append("Navigation target not clearly specified")

        # Check for missing selector
        if any(word in context_lower for word in ["click", "fill", "extract"]):
            if not any(char in context for char in [".", "#", "["]):
                uncertain.append("Element selector not specified")

        return uncertain

    def _identify_uncertain_aspects(self, factors: ConfidenceFactors) -> List[str]:
        """Identify which aspects are causing uncertainty."""
        uncertain_aspects = []

        factors_dict = factors.to_dict()

        # Map factors to user-friendly aspect names
        aspect_names = {
            "seen_similar_before": "Task familiarity",
            "clear_instructions": "Instruction clarity",
            "tools_available": "Tool availability",
            "recent_success_rate": "Recent performance",
            "self_model_confidence": "Capability match",
            "multi_model_agreement": "Model consensus"
        }

        for factor_name, score in factors_dict.items():
            # Skip multi_model_agreement if it's 0 (not applicable)
            if factor_name == "multi_model_agreement" and score == 0.0:
                continue

            if score < 0.5:
                aspect = aspect_names.get(factor_name, factor_name)
                uncertain_aspects.append(f"{aspect} ({score:.0%})")

        return uncertain_aspects

    def _generate_clarifying_questions(
        self,
        decision: Decision,
        factors: ConfidenceFactors
    ) -> List[str]:
        """Generate questions to ask the user for clarification."""
        questions = []

        # If instructions unclear
        if factors.clear_instructions < 0.5:
            questions.append(
                f"Could you provide more specific details about: {decision.task_description}?"
            )

        # If tool uncertain
        if factors.tools_available < 0.5 and decision.tool:
            questions.append(
                f"I'm not familiar with the '{decision.tool}' tool. Could you describe what it should do?"
            )

        # If haven't seen similar before
        if factors.seen_similar_before < 0.4:
            questions.append(
                "Could you provide an example of what a successful outcome would look like?"
            )

        # If self-model says outside capabilities
        if factors.self_model_confidence < 0.4:
            questions.append(
                "This task seems outside my current capabilities. Would you like me to try anyway, or should we break it into smaller steps?"
            )

        return questions

    # ========================================================================
    # OUTCOME TRACKING & CALIBRATION
    # ========================================================================

    def record_outcome(
        self,
        decision_id: str,
        success: bool,
        error: Optional[str] = None
    ):
        """
        Update confidence calibration based on outcome.

        Args:
            decision_id: ID of the decision
            success: Whether the action succeeded
            error: Optional error message if failed
        """
        with self._lock:
            # Get the decision
            decision = self._decisions.get(decision_id)
            if not decision:
                logger.warning(f"No decision found for ID: {decision_id}")
                return

            # Get the predicted confidence (need to recalculate)
            predicted_confidence, factors = self.calculate_confidence(decision)

            # Create outcome record
            outcome = DecisionOutcome(
                decision_id=decision_id,
                predicted_confidence=predicted_confidence,
                actual_success=success,
                error_message=error
            )

            # Store outcome
            self._outcomes.append(outcome)

            # Update recent success tracking
            self._recent_successes.append(success)

            # Update calibration bins
            self._update_calibration(predicted_confidence, success)

            # Persist to database
            self._save_decision_outcome(decision, predicted_confidence, success, factors)

            # Save calibration state
            self._save_calibration()

            logger.debug(
                f"Recorded outcome: {decision_id} | "
                f"Predicted: {predicted_confidence:.1%} | "
                f"Actual: {'success' if success else 'failure'}"
            )

    def _update_calibration(self, predicted_confidence: float, actual_success: bool):
        """Update calibration bins with new outcome."""
        # Find the appropriate bin
        bin_idx = int(predicted_confidence * CALIBRATION_BINS)
        bin_idx = min(bin_idx, CALIBRATION_BINS - 1)

        bin_data = self._calibration_bins[bin_idx]

        # Update bin statistics (incremental average)
        n = bin_data.count

        # Update predicted confidence average
        bin_data.predicted_confidence_avg = (
            (bin_data.predicted_confidence_avg * n + predicted_confidence) / (n + 1)
        )

        # Update actual success rate
        success_value = 1.0 if actual_success else 0.0
        bin_data.actual_success_rate = (
            (bin_data.actual_success_rate * n + success_value) / (n + 1)
        )

        # Update count
        bin_data.count += 1

        # Calculate calibration error
        bin_data.calibration_error = abs(
            bin_data.predicted_confidence_avg - bin_data.actual_success_rate
        )

        # Update global calibration adjustment
        self._recalculate_calibration_adjustment()

    def _recalculate_calibration_adjustment(self):
        """
        Recalculate global calibration adjustment.

        If we're consistently overconfident, this becomes negative.
        If we're consistently underconfident, this becomes positive.
        """
        # Get bins with sufficient data
        valid_bins = [b for b in self._calibration_bins if b.count >= 5]

        if not valid_bins:
            self._calibration_adjustment = 0.0
            return

        # Calculate average calibration error
        # Positive error = overconfident, negative error = underconfident
        errors = []
        for bin_data in valid_bins:
            error = bin_data.predicted_confidence_avg - bin_data.actual_success_rate
            errors.append(error)

        avg_error = sum(errors) / len(errors)

        # Adjustment is negative of the error (to correct)
        # Scale by 0.5 to be conservative
        self._calibration_adjustment = -avg_error * 0.5

        logger.debug(
            f"Calibration adjustment: {self._calibration_adjustment:+.3f} "
            f"(avg error: {avg_error:+.3f})"
        )

    def _apply_calibration(self, raw_confidence: float) -> float:
        """Apply calibration adjustment to raw confidence."""
        adjusted = raw_confidence + self._calibration_adjustment
        return max(0.0, min(1.0, adjusted))

    def get_calibration_stats(self) -> Dict[str, Any]:
        """
        Return calibration statistics showing how well-calibrated we are.

        Returns:
            Dict with calibration metrics and bin data
        """
        # Calculate overall calibration metrics
        total_decisions = sum(b.count for b in self._calibration_bins)

        if total_decisions == 0:
            return {
                "total_decisions": 0,
                "calibration_adjustment": self._calibration_adjustment,
                "status": "No calibration data yet"
            }

        # Calculate weighted calibration error
        weighted_error = sum(
            b.calibration_error * b.count
            for b in self._calibration_bins
        ) / total_decisions

        # Recent accuracy
        recent_outcomes = list(self._outcomes)[-20:]
        recent_accuracy = 0.0
        if recent_outcomes:
            recent_accuracy = sum(
                1 for o in recent_outcomes if o.actual_success
            ) / len(recent_outcomes)

        # Bin statistics
        bins_data = []
        for i, bin_data in enumerate(self._calibration_bins):
            if bin_data.count > 0:
                bins_data.append({
                    "range": f"{bin_data.bin_range[0]:.1f}-{bin_data.bin_range[1]:.1f}",
                    "predicted": bin_data.predicted_confidence_avg,
                    "actual": bin_data.actual_success_rate,
                    "count": bin_data.count,
                    "error": bin_data.calibration_error
                })

        # Determine calibration status
        if weighted_error < 0.05:
            status = "Well-calibrated"
        elif weighted_error < 0.15:
            status = "Moderately calibrated"
        else:
            status = "Needs calibration"

        # Determine bias
        if self._calibration_adjustment > 0.1:
            bias = "Underconfident (calibration correcting upward)"
        elif self._calibration_adjustment < -0.1:
            bias = "Overconfident (calibration correcting downward)"
        else:
            bias = "Well-calibrated"

        return {
            "total_decisions": total_decisions,
            "weighted_calibration_error": weighted_error,
            "calibration_adjustment": self._calibration_adjustment,
            "recent_accuracy": recent_accuracy,
            "status": status,
            "bias": bias,
            "bins": bins_data
        }

    # ========================================================================
    # PERSISTENCE
    # ========================================================================

    def _save_decision_outcome(
        self,
        decision: Decision,
        predicted_confidence: float,
        actual_success: bool,
        factors: ConfidenceFactors
    ):
        """Save decision and outcome to database."""
        try:
            with sqlite3.connect(str(UNCERTAINTY_DB)) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO decisions VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """, (
                    decision.decision_id,
                    decision.task_description,
                    decision.proposed_action,
                    predicted_confidence,
                    int(actual_success),
                    decision.timestamp,
                    json.dumps(factors.to_dict()),
                    json.dumps(decision.context)
                ))
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to save decision outcome: {e}")

    def _save_calibration(self):
        """Save calibration state to JSON."""
        try:
            data = {
                "calibration_adjustment": self._calibration_adjustment,
                "bins": [
                    {
                        "range": list(b.bin_range),
                        "predicted_avg": b.predicted_confidence_avg,
                        "actual_rate": b.actual_success_rate,
                        "count": b.count,
                        "error": b.calibration_error
                    }
                    for b in self._calibration_bins
                ],
                "last_updated": datetime.now().isoformat()
            }

            CALIBRATION_JSON.write_text(json.dumps(data, indent=2))

        except Exception as e:
            logger.warning(f"Failed to save calibration: {e}")

    def _load_calibration(self):
        """Load calibration state from JSON."""
        if not CALIBRATION_JSON.exists():
            return

        try:
            data = json.loads(CALIBRATION_JSON.read_text())

            self._calibration_adjustment = data.get("calibration_adjustment", 0.0)

            bins_data = data.get("bins", [])
            if len(bins_data) == len(self._calibration_bins):
                for i, bin_dict in enumerate(bins_data):
                    self._calibration_bins[i].predicted_confidence_avg = bin_dict["predicted_avg"]
                    self._calibration_bins[i].actual_success_rate = bin_dict["actual_rate"]
                    self._calibration_bins[i].count = bin_dict["count"]
                    self._calibration_bins[i].calibration_error = bin_dict["error"]

            logger.info(f"Loaded calibration: adjustment={self._calibration_adjustment:+.3f}")

        except Exception as e:
            logger.warning(f"Failed to load calibration: {e}")

    # ========================================================================
    # ANALYSIS & REPORTING
    # ========================================================================

    def get_uncertainty_report(self, decision: Decision) -> Dict[str, Any]:
        """
        Get detailed uncertainty report for a decision.

        Args:
            decision: Decision to analyze

        Returns:
            Dict with detailed uncertainty breakdown
        """
        confidence, factors = self.calculate_confidence(decision)
        adjusted_confidence = self._apply_calibration(confidence)
        action = self.assess(decision)

        return {
            "decision_id": decision.decision_id,
            "task": decision.task_description,
            "raw_confidence": confidence,
            "adjusted_confidence": adjusted_confidence,
            "calibration_adjustment": self._calibration_adjustment,
            "recommendation": action.action_type.value,
            "factors": factors.to_dict(),
            "uncertain_aspects": action.uncertain_aspects,
            "suggested_questions": action.suggested_questions,
            "explanation": action.reason
        }

    def print_calibration_stats(self):
        """Print calibration statistics to console."""
        stats = self.get_calibration_stats()

        print("\n=== Uncertainty Tracker Calibration ===")
        print(f"\nTotal Decisions: {stats['total_decisions']}")
        print(f"Status: {stats['status']}")
        print(f"Bias: {stats['bias']}")
        print(f"Calibration Adjustment: {stats['calibration_adjustment']:+.3f}")
        print(f"Recent Accuracy: {stats['recent_accuracy']:.1%}")

        if stats['bins']:
            print("\nCalibration by Confidence Level:")
            print(f"{'Range':<12} {'Predicted':<12} {'Actual':<12} {'Count':<8} {'Error':<8}")
            print("-" * 60)
            for bin_data in stats['bins']:
                print(
                    f"{bin_data['range']:<12} "
                    f"{bin_data['predicted']:<12.1%} "
                    f"{bin_data['actual']:<12.1%} "
                    f"{bin_data['count']:<8} "
                    f"{bin_data['error']:<8.3f}"
                )
        print()


# ============================================================================
# INTEGRATION HELPERS
# ============================================================================

def create_uncertainty_tracker(
    memory_arch=None,
    self_model=None,
    event_bus=None
) -> UncertaintyTracker:
    """Factory function to create uncertainty tracker."""
    return UncertaintyTracker(
        memory_arch=memory_arch,
        self_model=self_model,
        event_bus=event_bus
    )


def integrate_with_brain(tracker: UncertaintyTracker, brain):
    """
    Integrate uncertainty tracker with brain_enhanced_v2.py.

    Call tracker.assess() before every action in the brain's think loop.
    """
    # This would wrap brain's action execution with uncertainty checks
    pass


# ============================================================================
# DEMO / TESTING
# ============================================================================

if __name__ == "__main__":
    print("Uncertainty Tracker - Know When to Ask for Help")
    print("=" * 60)

    # Create tracker
    tracker = create_uncertainty_tracker()

    # Test decision 1: Clear, familiar task
    print("\nTest 1: Clear, familiar web navigation task")
    decision1 = Decision(
        decision_id="test_001",
        task_description="Navigate to https://example.com and extract the main heading",
        proposed_action="Use playwright_navigate then playwright_extract_page_fast",
        tool="playwright_navigate"
    )

    action1 = tracker.assess(decision1)
    print(f"Recommendation: {action1.action_type.value}")
    print(f"Confidence: {action1.confidence:.1%}")
    print(f"Reason: {action1.reason}")

    # Record successful outcome
    tracker.record_outcome("test_001", success=True)

    # Test decision 2: Vague, unclear task
    print("\nTest 2: Vague, unclear task")
    decision2 = Decision(
        decision_id="test_002",
        task_description="Maybe try to find something on the page somehow",
        proposed_action="Figure out what to extract",
        tool=None
    )

    action2 = tracker.assess(decision2)
    print(f"Recommendation: {action2.action_type.value}")
    print(f"Confidence: {action2.confidence:.1%}")
    print(f"Reason: {action2.reason}")
    if action2.uncertain_aspects:
        print(f"Uncertain aspects: {', '.join(action2.uncertain_aspects)}")
    if action2.suggested_questions:
        print("Suggested questions:")
        for q in action2.suggested_questions:
            print(f"  - {q}")

    # Test decision 3: Unknown tool
    print("\nTest 3: Task with unknown tool")
    decision3 = Decision(
        decision_id="test_003",
        task_description="Extract data from API endpoint",
        proposed_action="Call the quantum_api_reader tool",
        tool="quantum_api_reader"
    )

    action3 = tracker.assess(decision3)
    print(f"Recommendation: {action3.action_type.value}")
    print(f"Confidence: {action3.confidence:.1%}")
    print(f"Reason: {action3.reason}")

    # Simulate some outcomes for calibration
    print("\nSimulating outcomes for calibration...")
    for i in range(10):
        decision = Decision(
            decision_id=f"test_{i+10:03d}",
            task_description=f"Test task {i}",
            proposed_action="Test action"
        )
        action = tracker.assess(decision)
        # Simulate 70% success rate
        success = (i % 10) < 7
        tracker.record_outcome(decision.decision_id, success)

    # Test multi-model confidence
    print("\nTest 4: Multi-model confidence with agreement")
    model_results_agree = {
        "kimi_k2": "Navigate to example.com and extract contact information",
        "chatgpt": "Go to example.com and scrape contact details",
        "browser": "Visit example.com to get contacts"
    }
    confidence_agree = tracker.calculate_multi_model_confidence(model_results_agree)
    print(f"Models agree - Confidence: {confidence_agree:.1%}")

    print("\nTest 5: Multi-model confidence with disagreement")
    model_results_disagree = {
        "kimi_k2": "Navigate to example.com and extract contact information",
        "chatgpt": "Search Google for company reviews",
        "browser": "Download the homepage as PDF"
    }
    confidence_disagree = tracker.calculate_multi_model_confidence(model_results_disagree)
    print(f"Models disagree - Confidence: {confidence_disagree:.1%}")

    # Track model agreement
    print("\nTest 6: Tracking model agreement over time")
    tracker.track_model_agreement("task_1", ["kimi_k2", "chatgpt"], agreed=True, similarity_score=0.85)
    tracker.track_model_agreement("task_2", ["kimi_k2", "chatgpt"], agreed=True, similarity_score=0.90)
    tracker.track_model_agreement("task_3", ["kimi_k2", "chatgpt"], agreed=False, similarity_score=0.30)
    tracker.track_model_agreement("task_4", ["chatgpt", "browser"], agreed=True, similarity_score=0.75)

    agreement_stats = tracker.get_model_agreement_stats()
    print(f"\nModel Agreement Statistics:")
    print(f"Total model pairs tracked: {agreement_stats['total_pairs']}")
    print(f"Overall agreement rate: {agreement_stats['overall_agreement']:.1%}")
    for pair_name, stats in agreement_stats['pair_rates'].items():
        print(f"  {pair_name}: {stats['agreement_rate']:.1%} (n={stats['sample_size']})")

    # Test decision with multi-model results
    print("\nTest 7: Decision assessment with multi-model results")
    decision_multi = Decision(
        decision_id="test_multi_001",
        task_description="Extract contact information from company website",
        proposed_action="Use playwright_extract_page_fast",
        tool="playwright_extract_page_fast"
    )
    action_multi = tracker.assess(decision_multi, model_results=model_results_agree)
    print(f"Recommendation: {action_multi.action_type.value}")
    print(f"Confidence (with multi-model boost): {action_multi.confidence:.1%}")

    # Print calibration stats
    tracker.print_calibration_stats()

    print("\nUncertainty tracker with multi-model confidence ready!")
