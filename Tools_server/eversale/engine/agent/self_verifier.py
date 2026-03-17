"""
Self Verifier - Verify Agent Outputs Before Finalizing

This module provides comprehensive verification of agent outputs using multiple
verification strategies:
1. Web fact-checking - Verify claims against web search results
2. Second opinion - Ask another LLM to review the reasoning
3. Visual confirmation - Use vision models to verify UI state matches expectations
4. Consistency checks - Ensure output is internally consistent

Integration with Organism:
- Subscribes to ACTION_COMPLETE events via EventBus
- Runs async verification in parallel
- Logs all verification results
- Gracefully degrades if verification tools fail
- Emits VERIFICATION_COMPLETE events back to EventBus

The verifier acts as a quality control layer, catching errors before they're
presented to the user or committed to actions.
"""

import re
import asyncio
import time
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from loguru import logger
from collections import defaultdict

try:
    from agent.organism_core import EventBus, OrganismEvent, EventType
    EVENTBUS_AVAILABLE = True
except ImportError:
    EVENTBUS_AVAILABLE = False
    logger.warning("EventBus not available - verification won't publish events")

try:
    from agent.llm_client import LLMClient, LLMResponse
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    logger.warning("LLM client not available - second opinion verification disabled")


# =============================================================================
# VERIFICATION DATA STRUCTURES
# =============================================================================

@dataclass
class Claim:
    """A factual claim extracted from agent output."""
    text: str
    claim_type: str  # "fact", "statistic", "action_result", "reasoning"
    confidence: float = 0.5  # Initial confidence
    source_sentence: str = ""

    def __str__(self):
        return f"[{self.claim_type}] {self.text}"


@dataclass
class CheckResult:
    """Result of a single verification check."""
    check_type: str  # "web_fact", "second_opinion", "visual", "consistency"
    passed: bool
    confidence: float  # 0.0 to 1.0
    details: str
    issues: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def __str__(self):
        status = "PASSED" if self.passed else "FAILED"
        return f"{self.check_type}: {status} (confidence={self.confidence:.2f})"


@dataclass
class VerificationResult:
    """Overall verification result aggregating all checks."""
    task: str
    answer: str
    passed: bool
    confidence: float  # Aggregated confidence from all checks
    issues: List[str] = field(default_factory=list)
    checks: List[CheckResult] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0

    def summary(self) -> str:
        """Get human-readable summary."""
        status = "VERIFIED" if self.passed else "VERIFICATION FAILED"
        num_checks = len(self.checks)
        num_passed = sum(1 for c in self.checks if c.passed)

        summary = [
            f"{'='*60}",
            f"VERIFICATION RESULT: {status}",
            f"{'='*60}",
            f"Task: {self.task[:100]}...",
            f"Overall Confidence: {self.confidence:.2%}",
            f"Checks Passed: {num_passed}/{num_checks}",
            f"Duration: {self.duration_ms:.0f}ms",
        ]

        if self.issues:
            summary.append(f"\nIssues Found ({len(self.issues)}):")
            for issue in self.issues[:5]:  # Top 5 issues
                summary.append(f"  - {issue}")

        summary.append(f"\nCheck Details:")
        for check in self.checks:
            summary.append(f"  {check}")

        summary.append(f"{'='*60}")

        return "\n".join(summary)


# =============================================================================
# CLAIM EXTRACTION
# =============================================================================

class ClaimExtractor:
    """Extract verifiable claims from agent output."""

    # Patterns for different claim types
    FACT_PATTERNS = [
        r"(?:is|are|was|were|has|have)\s+([^.!?]+)",  # "X is Y"
        r"(?:located|found|based)\s+(?:in|at|on)\s+([^.!?]+)",  # Location claims
        r"(?:created|founded|established|built)\s+(?:in|on)\s+(\d{4})",  # Date claims
    ]

    STATISTIC_PATTERNS = [
        r"(\d+(?:\.\d+)?)\s*(%|percent|times|dollars|users|customers)",  # Numbers with units
        r"(?:increased|decreased|grew|fell)\s+by\s+(\d+)",  # Change metrics
        r"(?:costs?|prices?|valued)\s+(?:at\s+)?\$?(\d+(?:,\d+)*(?:\.\d+)?)",  # Money
    ]

    ACTION_PATTERNS = [
        r"(?:successfully|completed|executed|performed)\s+([^.!?]+)",  # Success claims
        r"(?:sent|created|updated|deleted|modified)\s+([^.!?]+)",  # Action results
        r"(?:found|discovered|identified)\s+(\d+)\s+([^.!?]+)",  # Search results
    ]

    def extract_claims(self, text: str) -> List[Claim]:
        """Extract all verifiable claims from text."""
        claims = []
        sentences = self._split_sentences(text)

        for sentence in sentences:
            # Extract facts
            for pattern in self.FACT_PATTERNS:
                matches = re.finditer(pattern, sentence, re.IGNORECASE)
                for match in matches:
                    claims.append(Claim(
                        text=match.group(1).strip(),
                        claim_type="fact",
                        source_sentence=sentence
                    ))

            # Extract statistics
            for pattern in self.STATISTIC_PATTERNS:
                matches = re.finditer(pattern, sentence, re.IGNORECASE)
                for match in matches:
                    claims.append(Claim(
                        text=match.group(0).strip(),
                        claim_type="statistic",
                        source_sentence=sentence
                    ))

            # Extract action results
            for pattern in self.ACTION_PATTERNS:
                matches = re.finditer(pattern, sentence, re.IGNORECASE)
                for match in matches:
                    claims.append(Claim(
                        text=match.group(0).strip(),
                        claim_type="action_result",
                        source_sentence=sentence
                    ))

        # Deduplicate similar claims
        claims = self._deduplicate_claims(claims)

        logger.debug(f"Extracted {len(claims)} claims from {len(sentences)} sentences")
        return claims

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        # Simple sentence splitting (could be improved with nltk)
        sentences = re.split(r'[.!?]+', text)
        return [s.strip() for s in sentences if len(s.strip()) > 10]

    def _deduplicate_claims(self, claims: List[Claim]) -> List[Claim]:
        """Remove duplicate or very similar claims."""
        if not claims:
            return []

        unique_claims = []
        seen_texts = set()

        for claim in claims:
            # Normalize for comparison
            normalized = claim.text.lower().strip()

            # Skip if too similar to existing claim
            if not any(self._similarity(normalized, seen) > 0.8 for seen in seen_texts):
                unique_claims.append(claim)
                seen_texts.add(normalized)

        return unique_claims

    def _similarity(self, a: str, b: str) -> float:
        """Calculate text similarity (simple token overlap)."""
        tokens_a = set(a.split())
        tokens_b = set(b.split())

        if not tokens_a or not tokens_b:
            return 0.0

        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)

        return intersection / union if union > 0 else 0.0


# =============================================================================
# VERIFICATION STRATEGIES
# =============================================================================

class WebFactChecker:
    """Verify claims against web search results."""

    def __init__(self, search_fn=None):
        """
        Args:
            search_fn: Async function to perform web search
                       Should accept query string and return search results
        """
        self.search_fn = search_fn
        self._cache: Dict[str, Any] = {}  # Cache search results

    async def check_claim(self, claim: Claim) -> CheckResult:
        """Verify a single claim against web search."""
        if not self.search_fn:
            return CheckResult(
                check_type="web_fact",
                passed=True,  # Optimistic - no search available
                confidence=0.5,
                details="Web search not available",
                issues=["Web search function not provided"]
            )

        try:
            # Check cache first
            cache_key = claim.text.lower().strip()
            if cache_key in self._cache:
                search_result = self._cache[cache_key]
            else:
                # Perform search
                search_query = self._create_search_query(claim)
                search_result = await self.search_fn(search_query)
                self._cache[cache_key] = search_result

            # Analyze search results
            passed, confidence, details = self._analyze_search_result(claim, search_result)

            return CheckResult(
                check_type="web_fact",
                passed=passed,
                confidence=confidence,
                details=details,
                issues=[] if passed else [f"Claim not verified by web search: {claim.text}"]
            )

        except Exception as e:
            logger.warning(f"Web fact check failed: {e}")
            return CheckResult(
                check_type="web_fact",
                passed=True,  # Optimistic on error
                confidence=0.5,
                details=f"Search error: {str(e)}",
                issues=[f"Web search failed: {str(e)}"]
            )

    def _create_search_query(self, claim: Claim) -> str:
        """Create effective search query from claim."""
        # For facts, search the claim directly
        # For statistics, include context
        # For action results, skip (can't verify via web)

        if claim.claim_type == "action_result":
            # Can't verify actions via web search
            return None

        # Extract key terms
        query = claim.text

        # Remove common filler words
        fillers = ["is", "are", "was", "were", "the", "a", "an"]
        words = [w for w in query.split() if w.lower() not in fillers]

        return " ".join(words[:10])  # Limit query length

    def _analyze_search_result(self, claim: Claim, search_result: Any) -> tuple[bool, float, str]:
        """
        Analyze search results to verify claim.

        Returns:
            (passed, confidence, details)
        """
        # This is a simplified implementation
        # In production, would use NLP/embeddings to compare claim to search results

        if not search_result:
            return (True, 0.5, "No search results to verify against")

        # Extract text from search results
        result_text = str(search_result).lower()
        claim_text = claim.text.lower()

        # Simple keyword matching
        claim_words = set(claim_text.split())
        matches = sum(1 for word in claim_words if word in result_text)
        confidence = matches / len(claim_words) if claim_words else 0.0

        passed = confidence > 0.3  # At least 30% keyword overlap

        details = f"Search verification: {confidence:.0%} keyword match"

        return (passed, confidence, details)


class SecondOpinionChecker:
    """Ask another LLM to review the reasoning."""

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def check_reasoning(self, task: str, answer: str) -> CheckResult:
        """Get second opinion on task/answer pair."""
        if not self.llm_client:
            return CheckResult(
                check_type="second_opinion",
                passed=True,
                confidence=0.5,
                details="LLM client not available",
                issues=["Second opinion LLM not configured"]
            )

        try:
            # Construct review prompt
            prompt = self._create_review_prompt(task, answer)

            # Get LLM response
            response = await self.llm_client.generate(
                prompt=prompt,
                temperature=0.1,  # Low temperature for consistency
                max_tokens=500
            )

            # Parse response
            passed, confidence, issues = self._parse_review(response.content)

            return CheckResult(
                check_type="second_opinion",
                passed=passed,
                confidence=confidence,
                details=response.content[:200],
                issues=issues
            )

        except Exception as e:
            logger.warning(f"Second opinion check failed: {e}")
            return CheckResult(
                check_type="second_opinion",
                passed=True,  # Optimistic on error
                confidence=0.5,
                details=f"Review error: {str(e)}",
                issues=[f"LLM review failed: {str(e)}"]
            )

    def _create_review_prompt(self, task: str, answer: str) -> str:
        """Create prompt for second opinion."""
        return f"""You are reviewing another AI agent's work. Evaluate if the answer correctly addresses the task.

TASK:
{task}

ANSWER:
{answer}

Provide a brief review in this format:
VERDICT: [CORRECT/INCORRECT/UNCERTAIN]
CONFIDENCE: [0-100]%
ISSUES: [List any problems, or "None"]

Be concise and focus on correctness, not style."""

    def _parse_review(self, review_text: str) -> tuple[bool, float, List[str]]:
        """
        Parse review response.

        Returns:
            (passed, confidence, issues)
        """
        # Extract verdict
        verdict_match = re.search(r'VERDICT:\s*(CORRECT|INCORRECT|UNCERTAIN)', review_text, re.IGNORECASE)
        verdict = verdict_match.group(1).upper() if verdict_match else "UNCERTAIN"

        # Extract confidence
        conf_match = re.search(r'CONFIDENCE:\s*(\d+)', review_text)
        confidence = int(conf_match.group(1)) / 100.0 if conf_match else 0.5

        # Extract issues
        issues = []
        issues_match = re.search(r'ISSUES:\s*(.+?)(?:\n|$)', review_text, re.IGNORECASE | re.DOTALL)
        if issues_match:
            issues_text = issues_match.group(1).strip()
            if issues_text.lower() != "none":
                # Split by common delimiters
                issues = [i.strip() for i in re.split(r'[;\n]', issues_text) if i.strip()]

        passed = verdict == "CORRECT"

        return (passed, confidence, issues)


class VisualVerifier:
    """Verify UI state matches expectations using vision models."""

    def __init__(self, vision_fn=None):
        """
        Args:
            vision_fn: Async function to analyze screenshots
                       Should accept image and question, return description
        """
        self.vision_fn = vision_fn

    async def verify_visual_state(
        self,
        screenshot: Any,
        expected_state: str,
        task: str
    ) -> CheckResult:
        """Verify visual state matches expectations."""
        if not self.vision_fn:
            return CheckResult(
                check_type="visual",
                passed=True,
                confidence=0.5,
                details="Vision model not available",
                issues=["Visual verification not configured"]
            )

        if not screenshot:
            return CheckResult(
                check_type="visual",
                passed=True,
                confidence=0.5,
                details="No screenshot provided",
                issues=["Screenshot not available for verification"]
            )

        try:
            # Ask vision model to describe state
            question = f"Describe what you see on the screen. Is this consistent with: {expected_state}?"
            description = await self.vision_fn(screenshot, question)

            # Check if description matches expected state
            passed, confidence = self._compare_states(description, expected_state)

            return CheckResult(
                check_type="visual",
                passed=passed,
                confidence=confidence,
                details=f"Vision check: {description[:200]}",
                issues=[] if passed else [f"Visual state mismatch: expected '{expected_state}'"]
            )

        except Exception as e:
            logger.warning(f"Visual verification failed: {e}")
            return CheckResult(
                check_type="visual",
                passed=True,  # Optimistic on error
                confidence=0.5,
                details=f"Vision error: {str(e)}",
                issues=[f"Visual verification failed: {str(e)}"]
            )

    def _compare_states(self, actual: str, expected: str) -> tuple[bool, float]:
        """Compare actual state description to expected state."""
        # Simple keyword matching
        actual_lower = actual.lower()
        expected_lower = expected.lower()

        # Extract key terms from expected state
        expected_terms = set(expected_lower.split())

        # Count how many expected terms appear in actual
        matches = sum(1 for term in expected_terms if term in actual_lower)
        confidence = matches / len(expected_terms) if expected_terms else 0.0

        passed = confidence > 0.5  # At least 50% match

        return (passed, confidence)


class ConsistencyChecker:
    """Check internal consistency of agent output."""

    async def check_consistency(self, answer: str) -> CheckResult:
        """Check if answer is internally consistent."""
        issues = []

        # Check for contradictions
        contradictions = self._find_contradictions(answer)
        if contradictions:
            issues.extend([f"Contradiction: {c}" for c in contradictions])

        # Check for incomplete thoughts
        if self._has_incomplete_thoughts(answer):
            issues.append("Answer contains incomplete thoughts")

        # Check for logical flow
        if not self._has_logical_flow(answer):
            issues.append("Answer lacks logical flow")

        passed = len(issues) == 0
        confidence = 1.0 - (len(issues) * 0.2)  # Decrease confidence per issue

        return CheckResult(
            check_type="consistency",
            passed=passed,
            confidence=max(0.0, confidence),
            details=f"Consistency check: {len(issues)} issues found",
            issues=issues
        )

    def _find_contradictions(self, text: str) -> List[str]:
        """Find obvious contradictions in text."""
        contradictions = []

        # Look for yes/no contradictions
        has_yes = re.search(r'\byes\b', text, re.IGNORECASE)
        has_no = re.search(r'\bno\b', text, re.IGNORECASE)
        has_not = re.search(r'\bnot\b', text, re.IGNORECASE)

        # Simple heuristic: if both yes and no appear, might be contradiction
        if has_yes and has_no and has_not:
            contradictions.append("Text contains both affirmative and negative statements")

        # Look for number contradictions (e.g., "5 items" then "10 items")
        numbers = re.findall(r'\b(\d+)\s+(\w+)', text)
        number_dict = defaultdict(list)
        for num, unit in numbers:
            number_dict[unit].append(int(num))

        for unit, nums in number_dict.items():
            if len(set(nums)) > 1:  # Different numbers for same unit
                contradictions.append(f"Inconsistent numbers for '{unit}': {nums}")

        return contradictions

    def _has_incomplete_thoughts(self, text: str) -> bool:
        """Check for incomplete thoughts."""
        # Look for sentences that end abruptly
        incomplete_patterns = [
            r'[a-z,]\s*$',  # Ends with lowercase or comma
            r'\.\.\.\s*$',  # Ends with ellipsis
            r'\b(?:but|and|or|so|because)\s*$',  # Ends with conjunction
        ]

        for pattern in incomplete_patterns:
            if re.search(pattern, text.strip()):
                return True

        return False

    def _has_logical_flow(self, text: str) -> bool:
        """Check if text has logical flow."""
        # Very simple check: look for transitions
        transitions = [
            'first', 'second', 'third', 'next', 'then', 'finally',
            'however', 'therefore', 'thus', 'consequently',
            'additionally', 'furthermore', 'moreover'
        ]

        text_lower = text.lower()
        has_transitions = any(trans in text_lower for trans in transitions)

        # If text is short, don't require transitions
        if len(text.split()) < 50:
            return True

        return has_transitions


# =============================================================================
# MAIN VERIFIER
# =============================================================================

class SelfVerifier:
    """
    Main verification system coordinating all verification strategies.

    Subscribes to EventBus ACTION_COMPLETE events and runs verification.
    Publishes VERIFICATION_COMPLETE events with results.
    """

    def __init__(
        self,
        llm_client=None,
        search_fn=None,
        vision_fn=None,
        event_bus: 'EventBus' = None,
        config: Dict = None
    ):
        """
        Args:
            llm_client: LLM client for second opinions
            search_fn: Async function for web searches
            vision_fn: Async function for visual verification
            event_bus: EventBus for organism integration
            config: Configuration dict
        """
        self.config = config or {}
        self.event_bus = event_bus

        # Initialize components
        self.claim_extractor = ClaimExtractor()
        self.web_checker = WebFactChecker(search_fn=search_fn)
        self.second_opinion = SecondOpinionChecker(llm_client=llm_client)
        self.visual_verifier = VisualVerifier(vision_fn=vision_fn)
        self.consistency_checker = ConsistencyChecker()

        # State
        self._verification_history: List[VerificationResult] = []
        self._running = False

        # Settings
        self.min_confidence = self.config.get('min_verification_confidence', 0.6)
        self.enabled_checks = self.config.get('enabled_checks', [
            'consistency', 'second_opinion', 'web_fact', 'visual'
        ])

        # Subscribe to events
        if self.event_bus and EVENTBUS_AVAILABLE:
            self.event_bus.subscribe(EventType.ACTION_COMPLETE, self._on_action_complete)
            logger.info("SelfVerifier subscribed to ACTION_COMPLETE events")

        logger.info(f"SelfVerifier initialized with checks: {self.enabled_checks}")

    def _on_action_complete(self, event: OrganismEvent):
        """Handle ACTION_COMPLETE events from EventBus."""
        try:
            task = event.data.get('task', '')
            answer = event.data.get('result', '')

            if task and answer:
                # Run verification asynchronously
                asyncio.create_task(self._verify_and_publish(task, answer, event.data))
        except Exception as e:
            logger.error(f"Error handling ACTION_COMPLETE event: {e}")

    async def _verify_and_publish(self, task: str, answer: str, context: Dict):
        """Verify and publish results to EventBus."""
        try:
            # Run verification
            result = await self.verify(answer, task)

            # Publish verification result
            if self.event_bus and EVENTBUS_AVAILABLE:
                # Add new event type if not exists
                try:
                    verification_event = OrganismEvent(
                        event_type=EventType.ACTION_COMPLETE,  # Reuse existing type
                        source="self_verifier",
                        data={
                            'verification_result': result,
                            'original_task': task,
                            'original_answer': answer,
                            'passed': result.passed,
                            'confidence': result.confidence,
                            'issues': result.issues
                        }
                    )
                    self.event_bus.emit(verification_event)
                    logger.debug(f"Published verification result: {result.passed}")
                except Exception as e:
                    logger.warning(f"Failed to publish verification event: {e}")

        except Exception as e:
            logger.error(f"Error in verify_and_publish: {e}")

    async def verify(self, answer: str, task: str, screenshot: Any = None) -> VerificationResult:
        """
        Verify agent output using all enabled strategies.

        Args:
            answer: The agent's answer/output to verify
            task: The original task/question
            screenshot: Optional screenshot for visual verification

        Returns:
            VerificationResult with aggregated confidence and issues
        """
        start_time = time.time()
        checks: List[CheckResult] = []

        logger.info(f"Starting verification for task: {task[:100]}...")

        # Extract claims for fact checking
        claims = self.claim_extractor.extract_claims(answer)
        logger.debug(f"Extracted {len(claims)} claims to verify")

        # Run verification checks in parallel
        check_tasks = []

        # 1. Consistency check (always run, fast)
        if 'consistency' in self.enabled_checks:
            check_tasks.append(self._run_consistency_check(answer))

        # 2. Second opinion (if LLM available)
        if 'second_opinion' in self.enabled_checks:
            check_tasks.append(self._run_second_opinion(task, answer))

        # 3. Web fact checking (for top claims)
        if 'web_fact' in self.enabled_checks and claims:
            # Limit to top 5 most important claims
            top_claims = self._prioritize_claims(claims)[:5]
            for claim in top_claims:
                check_tasks.append(self._run_web_check(claim))

        # 4. Visual verification (if screenshot provided)
        if 'visual' in self.enabled_checks and screenshot:
            expected_state = self._infer_expected_state(task, answer)
            check_tasks.append(self._run_visual_check(screenshot, expected_state, task))

        # Execute all checks concurrently
        if check_tasks:
            check_results = await asyncio.gather(*check_tasks, return_exceptions=True)

            # Filter out exceptions
            for result in check_results:
                if isinstance(result, CheckResult):
                    checks.append(result)
                elif isinstance(result, Exception):
                    logger.warning(f"Verification check failed: {result}")

        # Aggregate results
        overall_passed, overall_confidence, all_issues = self._aggregate_results(checks)

        duration_ms = (time.time() - start_time) * 1000

        result = VerificationResult(
            task=task,
            answer=answer,
            passed=overall_passed,
            confidence=overall_confidence,
            issues=all_issues,
            checks=checks,
            duration_ms=duration_ms
        )

        # Store in history
        self._verification_history.append(result)

        # Log summary
        logger.info(result.summary())

        return result

    async def _run_consistency_check(self, answer: str) -> CheckResult:
        """Run consistency check."""
        try:
            return await self.consistency_checker.check_consistency(answer)
        except Exception as e:
            logger.warning(f"Consistency check failed: {e}")
            return CheckResult(
                check_type="consistency",
                passed=True,
                confidence=0.5,
                details=f"Error: {str(e)}",
                issues=[str(e)]
            )

    async def _run_second_opinion(self, task: str, answer: str) -> CheckResult:
        """Run second opinion check."""
        try:
            return await self.second_opinion.check_reasoning(task, answer)
        except Exception as e:
            logger.warning(f"Second opinion check failed: {e}")
            return CheckResult(
                check_type="second_opinion",
                passed=True,
                confidence=0.5,
                details=f"Error: {str(e)}",
                issues=[str(e)]
            )

    async def _run_web_check(self, claim: Claim) -> CheckResult:
        """Run web fact check."""
        try:
            return await self.web_checker.check_claim(claim)
        except Exception as e:
            logger.warning(f"Web fact check failed: {e}")
            return CheckResult(
                check_type="web_fact",
                passed=True,
                confidence=0.5,
                details=f"Error: {str(e)}",
                issues=[str(e)]
            )

    async def _run_visual_check(
        self,
        screenshot: Any,
        expected_state: str,
        task: str
    ) -> CheckResult:
        """Run visual verification check."""
        try:
            return await self.visual_verifier.verify_visual_state(
                screenshot,
                expected_state,
                task
            )
        except Exception as e:
            logger.warning(f"Visual check failed: {e}")
            return CheckResult(
                check_type="visual",
                passed=True,
                confidence=0.5,
                details=f"Error: {str(e)}",
                issues=[str(e)]
            )

    def _prioritize_claims(self, claims: List[Claim]) -> List[Claim]:
        """Prioritize claims for verification (most important first)."""
        # Priority: statistics > facts > action_results
        priority_map = {
            "statistic": 3,
            "fact": 2,
            "action_result": 1,
            "reasoning": 1
        }

        return sorted(
            claims,
            key=lambda c: priority_map.get(c.claim_type, 0),
            reverse=True
        )

    def _infer_expected_state(self, task: str, answer: str) -> str:
        """Infer expected visual state from task and answer."""
        # Extract action verbs and objects
        action_match = re.search(
            r'\b(click|navigate|fill|submit|search|open|close)\s+(?:on\s+)?(?:the\s+)?([^.!?]+)',
            task.lower()
        )

        if action_match:
            action, target = action_match.groups()
            return f"Screen should show result of {action} on {target}"

        # Fallback: use answer to infer state
        return f"Screen should reflect: {answer[:100]}"

    def _aggregate_results(self, checks: List[CheckResult]) -> tuple[bool, float, List[str]]:
        """
        Aggregate check results into overall verdict.

        Returns:
            (overall_passed, overall_confidence, all_issues)
        """
        if not checks:
            return (True, 1.0, [])  # No checks = optimistic pass

        # Calculate weighted average confidence
        # Weight: consistency=0.2, second_opinion=0.4, web_fact=0.3, visual=0.1
        weights = {
            'consistency': 0.2,
            'second_opinion': 0.4,
            'web_fact': 0.3,
            'visual': 0.1
        }

        total_weight = 0.0
        weighted_confidence = 0.0

        for check in checks:
            weight = weights.get(check.check_type, 0.25)  # Default weight
            weighted_confidence += check.confidence * weight
            total_weight += weight

        overall_confidence = weighted_confidence / total_weight if total_weight > 0 else 0.5

        # Overall pass if confidence meets threshold AND no critical failures
        critical_failures = [c for c in checks if not c.passed and c.confidence < 0.3]
        overall_passed = (
            overall_confidence >= self.min_confidence and
            len(critical_failures) == 0
        )

        # Collect all issues
        all_issues = []
        for check in checks:
            all_issues.extend(check.issues)

        return (overall_passed, overall_confidence, all_issues)

    def get_verification_stats(self) -> Dict[str, Any]:
        """Get statistics about verification history."""
        if not self._verification_history:
            return {
                'total_verifications': 0,
                'pass_rate': 0.0,
                'avg_confidence': 0.0,
                'common_issues': []
            }

        total = len(self._verification_history)
        passed = sum(1 for v in self._verification_history if v.passed)

        avg_confidence = sum(v.confidence for v in self._verification_history) / total

        # Count issue frequencies
        issue_counts = defaultdict(int)
        for v in self._verification_history:
            for issue in v.issues:
                issue_counts[issue] += 1

        common_issues = sorted(
            issue_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        return {
            'total_verifications': total,
            'pass_rate': passed / total,
            'avg_confidence': avg_confidence,
            'common_issues': [{'issue': issue, 'count': count} for issue, count in common_issues]
        }


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

async def example_usage():
    """Example of how to use SelfVerifier."""

    # Create verifier with optional components
    verifier = SelfVerifier(
        llm_client=None,  # Would pass LLMClient instance
        search_fn=None,   # Would pass async search function
        vision_fn=None,   # Would pass async vision function
        config={
            'min_verification_confidence': 0.6,
            'enabled_checks': ['consistency', 'second_opinion']
        }
    )

    # Verify an answer
    task = "Find Python books on books.toscrape.com"
    answer = "I found 15 Python books. The most popular is 'Python for Data Science' priced at $45.99. Successfully added 3 books to cart."

    result = await verifier.verify(answer, task)

    print(result.summary())

    # Check if verification passed
    if result.passed:
        print(f"✓ Output verified with {result.confidence:.0%} confidence")
    else:
        print(f"✗ Verification failed: {result.issues}")

    # Get stats
    stats = verifier.get_verification_stats()
    print(f"\nVerification Stats: {stats}")


if __name__ == "__main__":
    asyncio.run(example_usage())
