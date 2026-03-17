"""
AGI-like Reasoning Module for Eversale CLI

This module implements advanced reasoning capabilities:
1. Pre-flight Analysis - Think before acting, predict failures
2. Self-Verification - Verify actions succeeded without hardcoded checks
3. Chain-of-Thought - Break complex tasks into reasoning steps
4. Proactive Problem Solving - Detect and fix issues before they escalate
5. Meta-Cognition - Reflect on reasoning quality
6. Adaptive Learning - Learn from mistakes in-session

Uses UI-TARS for unlimited LLM calls to enable true reasoning.
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ReasoningPhase(Enum):
    """Phases of AGI-like reasoning."""
    PRE_FLIGHT = "pre_flight"       # Before action: what could go wrong?
    EXECUTION = "execution"         # During action: monitor progress
    VERIFICATION = "verification"   # After action: did it work?
    CORRECTION = "correction"       # If failed: how to fix?
    META = "meta"                   # Reflect on reasoning quality


@dataclass
class ThoughtChain:
    """A chain of thoughts leading to a decision."""
    thoughts: List[str] = field(default_factory=list)
    conclusion: str = ""
    confidence: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ReasoningContext:
    """Context for reasoning about a task."""
    goal: str = ""
    current_state: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    failures: List[Dict[str, Any]] = field(default_factory=list)
    learned_patterns: Dict[str, str] = field(default_factory=dict)


class AGIReasoning:
    """
    AGI-like reasoning system that uses LLM for intelligent decision-making.

    Key capabilities:
    - Pre-flight analysis before every action
    - Self-verification after actions
    - Proactive failure prevention
    - Learning from mistakes without code changes
    """

    # Prompts for different reasoning phases
    PRE_FLIGHT_PROMPT = """You are analyzing a browser automation task BEFORE execution.

Current Goal: {goal}
Planned Action: {action}
Current Page State: {page_state}
Past Failures in This Session: {failures}

Think step by step:
1. What could go wrong with this action?
2. What preconditions must be true for success?
3. Are there any red flags in the current state?
4. What's an alternative if this fails?

Respond in JSON:
{{
    "risks": ["list of potential failure points"],
    "preconditions": ["what must be true"],
    "red_flags": ["concerns about current state"],
    "alternative_action": "backup plan if this fails",
    "should_proceed": true/false,
    "reasoning": "why you recommend this"
}}"""

    VERIFICATION_PROMPT = """You are verifying if a browser action succeeded.

Goal: {goal}
Action Taken: {action}
Page State BEFORE: {before_state}
Page State AFTER: {after_state}
Expected Outcome: {expected}

Analyze the changes and determine:
1. Did the action succeed?
2. Did we make progress toward the goal?
3. Are there any unexpected side effects?
4. What should we do next?

Respond in JSON:
{{
    "success": true/false,
    "progress_made": true/false,
    "evidence": "what indicates success/failure",
    "side_effects": ["any unexpected changes"],
    "next_action": "recommended next step",
    "confidence": 0.0-1.0
}}"""

    CORRECTION_PROMPT = """An action failed. Think about how to recover.

Goal: {goal}
Failed Action: {action}
Error/Symptom: {error}
Current State: {current_state}
Past Attempts: {past_attempts}

Think creatively:
1. Why did it fail?
2. What's a completely different approach?
3. Can we work around the issue?
4. Should we try a simpler solution?

Respond in JSON:
{{
    "root_cause": "why it failed",
    "alternative_approach": "different way to achieve goal",
    "workaround": "quick fix if available",
    "simpler_solution": "easier approach that might work",
    "should_retry": true/false,
    "new_action": "what to do next"
}}"""

    META_REASONING_PROMPT = """Reflect on the reasoning process so far.

Goal: {goal}
Actions Taken: {actions}
Successes: {successes}
Failures: {failures}

Meta-analysis:
1. Is our approach working?
2. Are we stuck in a loop?
3. Should we completely change strategy?
4. What have we learned?

Respond in JSON:
{{
    "approach_working": true/false,
    "stuck_in_loop": true/false,
    "strategy_change_needed": true/false,
    "learned_patterns": {{"pattern": "lesson"}},
    "recommended_strategy": "what to do differently"
}}"""

    INTENT_UNDERSTANDING_PROMPT = """Deeply understand what the user really wants.

User Request: {user_request}
Available Context: {context}

Think like a human assistant:
1. What is the user's ACTUAL goal (not just literal words)?
2. What do they expect to see as output?
3. What implicit requirements exist?
4. What would make them delighted vs disappointed?

Respond in JSON:
{{
    "literal_request": "what they said",
    "actual_goal": "what they really want",
    "success_criteria": ["how to know we succeeded"],
    "implicit_requirements": ["unspoken expectations"],
    "delight_factors": ["what would exceed expectations"],
    "disappointment_factors": ["what would fail them"]
}}"""

    def __init__(self, llm_client=None):
        """Initialize AGI reasoning with an LLM client."""
        self.llm_client = llm_client
        self.context = ReasoningContext()
        self.thought_history: List[ThoughtChain] = []
        self._reasoning_enabled = True

    async def set_llm_client(self, client):
        """Set the LLM client for reasoning."""
        self.llm_client = client

    def enable_reasoning(self, enabled: bool = True):
        """Enable or disable reasoning (for performance)."""
        self._reasoning_enabled = enabled

    async def _call_kimi(self, prompt: str) -> Dict[str, Any]:
        """
        Call Kimi K2 for complex reasoning tasks.

        Use Kimi for:
        - Intent understanding (most important to get right)
        - Meta-analysis (detecting stuck loops, strategy changes)
        - Complex corrections (creative problem solving)

        Falls back to fast model if Kimi unavailable.
        """
        try:
            from .kimi_k2_client import get_kimi_client

            client = get_kimi_client()
            if client.is_available():
                response = await client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=1500
                )

                content = response.get("content", "") if isinstance(response, dict) else str(response)

                # Try to find JSON in response
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    return json.loads(json_match.group())

        except ImportError:
            logger.debug(" Kimi client not available, using fast model")
        except Exception as e:
            logger.debug(f" Kimi call failed, falling back to fast model: {e}")

        # Fallback to fast model
        return await self._call_llm(prompt)

    async def _call_llm(self, prompt: str) -> Dict[str, Any]:
        """Call LLM for reasoning. Returns parsed JSON or empty dict."""
        if not self.llm_client or not self._reasoning_enabled:
            return {}

        try:
            # Use the fast model for reasoning to keep it cheap
            response = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                model="0000/ui-tars-1.5-7b:latest",
                temperature=0.1,
                max_tokens=1024
            )

            # Extract JSON from response
            content = response.get("content", "")

            # Try to find JSON in response
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                return json.loads(json_match.group())
            return {}

        except Exception as e:
            logger.debug(f"LLM reasoning call failed: {e}")
            return {}

    async def understand_intent(self, user_request: str, context: Dict = None) -> Dict[str, Any]:
        """
        Deeply understand what the user actually wants.

        This is the first step - truly understanding intent beyond literal words.
        Uses Kimi for complex reasoning since this is critical to get right.
        """
        prompt = self.INTENT_UNDERSTANDING_PROMPT.format(
            user_request=user_request,
            context=json.dumps(context or {}, indent=2)
        )

        # Use Kimi for intent understanding - most important to get right
        result = await self._call_kimi(prompt)
        if result:
            self.context.goal = result.get("actual_goal", user_request)
            logger.info(f" Intent understood: {self.context.goal}")
        return result

    async def pre_flight_check(
        self,
        action: str,
        page_state: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Pre-flight analysis before taking an action.

        Returns:
            Tuple of (should_proceed, analysis_result)
        """
        prompt = self.PRE_FLIGHT_PROMPT.format(
            goal=self.context.goal,
            action=action,
            page_state=json.dumps(page_state, indent=2)[:2000],
            failures=json.dumps(self.context.failures[-5:], indent=2)
        )

        result = await self._call_llm(prompt)

        if result:
            should_proceed = result.get("should_proceed", True)
            if not should_proceed:
                logger.warning(f" Pre-flight blocked action: {result.get('reasoning', 'unknown')}")
            return should_proceed, result

        # Default: proceed if LLM unavailable
        return True, {}

    async def verify_action(
        self,
        action: str,
        before_state: Dict[str, Any],
        after_state: Dict[str, Any],
        expected: str = ""
    ) -> Dict[str, Any]:
        """
        Verify if an action succeeded by comparing before/after states.

        Uses LLM reasoning instead of hardcoded checks.
        """
        prompt = self.VERIFICATION_PROMPT.format(
            goal=self.context.goal,
            action=action,
            before_state=json.dumps(before_state, indent=2)[:1500],
            after_state=json.dumps(after_state, indent=2)[:1500],
            expected=expected or "progress toward goal"
        )

        result = await self._call_llm(prompt)

        if result:
            success = result.get("success", True)
            if not success:
                self.context.failures.append({
                    "action": action,
                    "error": result.get("evidence", "unknown"),
                    "timestamp": datetime.now().isoformat()
                })
            logger.info(f" Action verification: success={success}, confidence={result.get('confidence', 0)}")
        return result

    async def get_correction(
        self,
        action: str,
        error: str,
        current_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get intelligent correction for a failed action.

        Returns creative alternatives instead of just retrying.
        Uses Kimi for creative problem-solving.
        """
        prompt = self.CORRECTION_PROMPT.format(
            goal=self.context.goal,
            action=action,
            error=error,
            current_state=json.dumps(current_state, indent=2)[:1500],
            past_attempts=json.dumps(self.context.failures[-3:], indent=2)
        )

        # Use Kimi for creative correction - needs out-of-box thinking
        result = await self._call_kimi(prompt)

        if result:
            logger.info(f" Correction suggested: {result.get('new_action', 'none')}")
            # Learn from this failure
            if result.get("root_cause"):
                pattern = f"{action} -> {error}"
                lesson = result.get("alternative_approach", "try different approach")
                self.context.learned_patterns[pattern] = lesson
        return result

    async def meta_analyze(self) -> Dict[str, Any]:
        """
        Meta-cognitive analysis of the reasoning process.

        Detects stuck loops, ineffective strategies, etc.
        Uses Kimi for meta-cognition since it requires high-level reasoning.
        """
        actions = [h.get("action", "") for h in self.context.history[-10:]]
        successes = [h for h in self.context.history if h.get("success")]
        failures = self.context.failures[-5:]

        prompt = self.META_REASONING_PROMPT.format(
            goal=self.context.goal,
            actions=json.dumps(actions, indent=2),
            successes=json.dumps([s.get("action") for s in successes], indent=2),
            failures=json.dumps([f.get("action") for f in failures], indent=2)
        )

        # Use Kimi for meta-analysis - needs high-level reasoning
        result = await self._call_kimi(prompt)

        if result:
            if result.get("stuck_in_loop"):
                logger.warning(" Meta-analysis detected stuck loop!")
            if result.get("strategy_change_needed"):
                logger.warning(f" Strategy change recommended: {result.get('recommended_strategy')}")
        return result

    async def think_ahead(self, current_state: Dict[str, Any]) -> List[str]:
        """
        Proactively think about what needs to happen next.

        Returns a list of anticipated steps.
        """
        prompt = f"""Given the current state, predict the next 3 steps needed to achieve the goal.

Goal: {self.context.goal}
Current State: {json.dumps(current_state, indent=2)[:1500]}
Progress So Far: {len(self.context.history)} actions taken
Failures Encountered: {len(self.context.failures)}

Respond in JSON:
{{
    "next_steps": ["step1", "step2", "step3"],
    "potential_blockers": ["what might stop us"],
    "optimal_path": "most efficient way forward"
}}"""

        result = await self._call_llm(prompt)
        return result.get("next_steps", [])

    def record_action(self, action: str, result: Any, success: bool):
        """Record an action for learning."""
        self.context.history.append({
            "action": action,
            "result": str(result)[:500],
            "success": success,
            "timestamp": datetime.now().isoformat()
        })

    def get_learned_lesson(self, action: str) -> Optional[str]:
        """Check if we've learned something about this action."""
        for pattern, lesson in self.context.learned_patterns.items():
            if action in pattern:
                return lesson
        return None

    def reset_context(self):
        """Reset context for a new task (but keep learned patterns)."""
        learned = self.context.learned_patterns.copy()
        self.context = ReasoningContext()
        self.context.learned_patterns = learned


class ProactiveGuard:
    """
    Proactive guard that prevents common failures before they happen.

    Uses pattern matching + LLM reasoning to catch issues early.
    """

    # Common failure patterns and their proactive checks
    FAILURE_PATTERNS = {
        "login_required": {
            "indicators": ["sign in", "log in", "please login", "session expired"],
            "check": "Is there a login wall blocking our action?",
            "action": "Handle authentication first"
        },
        "rate_limited": {
            "indicators": ["too many requests", "rate limit", "slow down", "try again later"],
            "check": "Are we being rate limited?",
            "action": "Wait and retry with exponential backoff"
        },
        "captcha": {
            "indicators": ["verify you're human", "captcha", "not a robot", "security check"],
            "check": "Is there a CAPTCHA blocking us?",
            "action": "Solve CAPTCHA or try alternative approach"
        },
        "page_not_loaded": {
            "indicators": ["loading", "please wait", "spinner"],
            "check": "Is the page still loading?",
            "action": "Wait for page to fully load"
        },
        "element_blocked": {
            "indicators": ["modal", "popup", "overlay", "cookie consent"],
            "check": "Is a modal/popup blocking interaction?",
            "action": "Close the blocking element first"
        },
        "wrong_page": {
            "indicators": [],  # Checked by URL/title mismatch
            "check": "Are we on the expected page?",
            "action": "Navigate to correct page"
        }
    }

    def __init__(self, reasoning: AGIReasoning):
        self.reasoning = reasoning

    def detect_blocking_patterns(self, page_text: str) -> List[Dict[str, str]]:
        """Detect potential blocking patterns in page content."""
        detected = []
        page_lower = page_text.lower()

        for pattern_name, pattern_data in self.FAILURE_PATTERNS.items():
            for indicator in pattern_data["indicators"]:
                if indicator in page_lower:
                    detected.append({
                        "pattern": pattern_name,
                        "indicator": indicator,
                        "action": pattern_data["action"]
                    })
                    break
        return detected

    async def preemptive_check(self, action: str, page_state: Dict) -> Dict[str, Any]:
        """
        Run preemptive checks before an action.

        Returns recommendations for handling potential issues.
        """
        page_text = page_state.get("text", "")
        page_url = page_state.get("url", "")

        # Quick pattern detection
        blocking_patterns = self.detect_blocking_patterns(page_text)

        if blocking_patterns:
            return {
                "blocked": True,
                "patterns": blocking_patterns,
                "recommendation": blocking_patterns[0]["action"]
            }

        # Use LLM for deeper analysis if no obvious patterns
        should_proceed, analysis = await self.reasoning.pre_flight_check(action, page_state)

        return {
            "blocked": not should_proceed,
            "analysis": analysis,
            "recommendation": analysis.get("alternative_action") if not should_proceed else None
        }


class SelfHealingLoop:
    """
    Self-healing execution loop that automatically corrects failures.

    Instead of hardcoded error handling, uses LLM to understand and fix issues.
    """

    def __init__(self, reasoning: AGIReasoning, max_corrections: int = 3):
        self.reasoning = reasoning
        self.guard = ProactiveGuard(reasoning)
        self.max_corrections = max_corrections

    async def execute_with_healing(
        self,
        action_fn,
        action_description: str,
        get_state_fn,
        expected_outcome: str = ""
    ) -> Tuple[bool, Any]:
        """
        Execute an action with self-healing capability.

        Args:
            action_fn: Async function to execute the action
            action_description: Description of what we're doing
            get_state_fn: Function to get current page state
            expected_outcome: What success looks like

        Returns:
            Tuple of (success, result)
        """
        corrections = 0
        last_error = None

        while corrections <= self.max_corrections:
            # Get current state before action
            before_state = await get_state_fn()

            # Pre-flight check
            check = await self.guard.preemptive_check(action_description, before_state)
            if check.get("blocked"):
                logger.warning(f" Preemptive block: {check.get('recommendation')}")
                # Could return recommendation for caller to handle
                # Or attempt automatic resolution

            # Check for learned lessons
            lesson = self.reasoning.get_learned_lesson(action_description)
            if lesson:
                logger.info(f" Applying learned lesson: {lesson}")
                # Modify action based on lesson

            try:
                # Execute the action
                result = await action_fn()

                # Get state after action
                after_state = await get_state_fn()

                # Verify success using LLM
                verification = await self.reasoning.verify_action(
                    action_description,
                    before_state,
                    after_state,
                    expected_outcome
                )

                if verification.get("success", True):
                    self.reasoning.record_action(action_description, result, True)
                    return True, result
                else:
                    # Action completed but didn't achieve goal
                    last_error = verification.get("evidence", "verification failed")

            except Exception as e:
                last_error = str(e)

            # Get correction
            correction = await self.reasoning.get_correction(
                action_description,
                last_error,
                await get_state_fn()
            )

            if not correction.get("should_retry", True):
                logger.warning(" Self-healing decided not to retry")
                break

            # Apply correction (caller needs to handle new_action)
            new_action = correction.get("new_action")
            if new_action:
                logger.info(f" Applying correction: {new_action}")
                # This is where the magic happens - the correction becomes the new action
                action_description = new_action

            corrections += 1

            # Brief pause between correction attempts
            await asyncio.sleep(0.5)

        # Record failure
        self.reasoning.record_action(action_description, last_error, False)

        # Meta-analysis after multiple failures
        if corrections >= self.max_corrections:
            meta = await self.reasoning.meta_analyze()
            if meta.get("strategy_change_needed"):
                logger.warning(f" Strategy change needed: {meta.get('recommended_strategy')}")

        return False, last_error


# Global instance for easy access
_agi_reasoning: Optional[AGIReasoning] = None

def get_agi_reasoning() -> AGIReasoning:
    """Get or create the global AGI reasoning instance."""
    global _agi_reasoning
    if _agi_reasoning is None:
        _agi_reasoning = AGIReasoning()
    return _agi_reasoning


async def reason_before_action(action: str, page_state: Dict) -> Tuple[bool, Dict]:
    """Quick helper to do pre-flight reasoning."""
    reasoning = get_agi_reasoning()
    return await reasoning.pre_flight_check(action, page_state)


async def verify_action_success(action: str, before: Dict, after: Dict) -> Dict:
    """Quick helper to verify action success."""
    reasoning = get_agi_reasoning()
    return await reasoning.verify_action(action, before, after)


async def get_smart_correction(action: str, error: str, state: Dict) -> Dict:
    """Quick helper to get intelligent correction."""
    reasoning = get_agi_reasoning()
    return await reasoning.get_correction(action, error, state)
