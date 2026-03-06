"""
AGI Core - Cognitive Architecture for Autonomous Browser Agent

This is the seed of AGI-like behavior. A proper cognitive architecture with:

1. PERCEPTION - Understanding the current state deeply
2. REASONING - Multi-step thinking before acting
3. PLANNING - Decomposing goals into executable steps
4. EXECUTION - Taking actions with monitoring
5. LEARNING - Improving from every interaction
6. METACOGNITION - Thinking about its own thinking

Philosophy:
- Think before every action (not just on failure)
- Predict problems before they happen
- Learn from EVERY outcome (success and failure)
- Know what you don't know (uncertainty awareness)
- Explain your reasoning (transparency)

This module works even without LLM by using pattern-based reasoning
as fallback, making it robust and always-on.
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


# =============================================================================
# COGNITIVE STATE - Working Memory
# =============================================================================

class CognitiveState(Enum):
    """Current cognitive state of the agent."""
    IDLE = "idle"
    PERCEIVING = "perceiving"
    REASONING = "reasoning"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    LEARNING = "learning"
    RECOVERING = "recovering"


@dataclass
class WorkingMemory:
    """
    Short-term memory that persists across actions within a session.

    Like human working memory - holds ~7 items, decays over time,
    but critical items are reinforced.
    """
    # Current goal and subgoals
    primary_goal: str = ""
    subgoals: List[str] = field(default_factory=list)
    current_subgoal_idx: int = 0

    # Current state understanding
    page_understanding: Dict[str, Any] = field(default_factory=dict)
    detected_obstacles: List[str] = field(default_factory=list)
    available_actions: List[str] = field(default_factory=list)

    # Action history (last N actions)
    recent_actions: List[Dict] = field(default_factory=list)
    max_recent: int = 10

    # Learned patterns this session
    session_patterns: Dict[str, str] = field(default_factory=dict)

    # Confidence tracking
    confidence: float = 0.8
    uncertainty_reasons: List[str] = field(default_factory=list)

    # Predictions
    predicted_next_obstacle: str = ""
    predicted_success_probability: float = 0.5

    def add_action(self, action: str, result: str, success: bool):
        """Add action to recent history."""
        self.recent_actions.append({
            "action": action,
            "result": result,
            "success": success,
            "timestamp": time.time()
        })
        # Keep only recent
        if len(self.recent_actions) > self.max_recent:
            self.recent_actions.pop(0)

    def get_action_pattern(self) -> str:
        """Get pattern of recent actions for loop detection."""
        return " -> ".join(a["action"][:20] for a in self.recent_actions[-5:])

    def detect_loop(self) -> bool:
        """Detect if we're stuck in a loop."""
        if len(self.recent_actions) < 4:
            return False
        # Check if last 4 actions repeat a pattern
        actions = [a["action"] for a in self.recent_actions[-6:]]
        # Simple loop: A -> B -> A -> B
        if len(actions) >= 4:
            if actions[-1] == actions[-3] and actions[-2] == actions[-4]:
                return True
        # Same action repeated
        if len(set(actions[-3:])) == 1:
            return True
        return False


@dataclass
class EpisodicMemory:
    """
    Long-term episodic memory - stores experiences for future reference.

    Persisted to disk so learning carries across sessions.
    """
    episodes: List[Dict] = field(default_factory=list)
    success_patterns: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    failure_patterns: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    site_knowledge: Dict[str, Dict] = field(default_factory=dict)

    _storage_path: Path = field(default_factory=lambda: Path.home() / ".eversale" / "agi_memory.json")

    def record_episode(self, goal: str, actions: List[Dict], outcome: str, success: bool):
        """Record a complete episode (goal -> actions -> outcome)."""
        episode = {
            "goal": goal,
            "actions": actions,
            "outcome": outcome,
            "success": success,
            "timestamp": datetime.now().isoformat(),
            "action_count": len(actions)
        }
        self.episodes.append(episode)

        # Update patterns
        goal_key = self._normalize_goal(goal)
        if success:
            self.success_patterns[goal_key] += 1
        else:
            self.failure_patterns[goal_key] += 1

        # Trim old episodes (keep last 1000)
        if len(self.episodes) > 1000:
            self.episodes = self.episodes[-1000:]

        # Auto-save
        self._save()

    def get_similar_episodes(self, goal: str, limit: int = 5) -> List[Dict]:
        """Find similar past episodes for learning."""
        goal_key = self._normalize_goal(goal)
        similar = []
        for ep in reversed(self.episodes):
            ep_key = self._normalize_goal(ep["goal"])
            if self._similarity(goal_key, ep_key) > 0.5:
                similar.append(ep)
                if len(similar) >= limit:
                    break
        return similar

    def get_success_rate(self, goal: str) -> float:
        """Get historical success rate for similar goals."""
        goal_key = self._normalize_goal(goal)
        successes = self.success_patterns.get(goal_key, 0)
        failures = self.failure_patterns.get(goal_key, 0)
        total = successes + failures
        if total == 0:
            return 0.5  # Unknown
        return successes / total

    def learn_site_pattern(self, site: str, pattern_type: str, pattern: str):
        """Learn site-specific patterns (e.g., login selectors, rate limits)."""
        if site not in self.site_knowledge:
            self.site_knowledge[site] = {}
        self.site_knowledge[site][pattern_type] = pattern
        self._save()

    def get_site_knowledge(self, site: str) -> Dict:
        """Get learned knowledge about a site."""
        return self.site_knowledge.get(site, {})

    def _normalize_goal(self, goal: str) -> str:
        """Normalize goal for pattern matching."""
        # Remove specific details, keep intent
        goal = goal.lower()
        # Remove numbers
        goal = re.sub(r'\d+', 'N', goal)
        # Remove quoted strings
        goal = re.sub(r'["\'][^"\']+["\']', 'X', goal)
        # Keep only key words
        keywords = ['find', 'search', 'get', 'extract', 'scrape', 'click', 'login',
                    'reddit', 'linkedin', 'facebook', 'google', 'navigate']
        words = goal.split()
        key_words = [w for w in words if any(k in w for k in keywords)]
        return ' '.join(key_words[:5])

    def _similarity(self, a: str, b: str) -> float:
        """Simple similarity score between two normalized goals."""
        a_words = set(a.split())
        b_words = set(b.split())
        if not a_words or not b_words:
            return 0.0
        intersection = len(a_words & b_words)
        union = len(a_words | b_words)
        return intersection / union if union > 0 else 0.0

    def _save(self):
        """Save memory to disk."""
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "episodes": self.episodes[-100:],  # Last 100 episodes
                "success_patterns": dict(self.success_patterns),
                "failure_patterns": dict(self.failure_patterns),
                "site_knowledge": self.site_knowledge
            }
            with open(self._storage_path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.debug(f"Failed to save episodic memory: {e}")

    def load(self):
        """Load memory from disk."""
        try:
            if self._storage_path.exists():
                with open(self._storage_path, 'r') as f:
                    data = json.load(f)
                self.episodes = data.get("episodes", [])
                self.success_patterns = defaultdict(int, data.get("success_patterns", {}))
                self.failure_patterns = defaultdict(int, data.get("failure_patterns", {}))
                self.site_knowledge = data.get("site_knowledge", {})
                logger.info(f"[Core] Loaded {len(self.episodes)} episodes from memory")
        except Exception as e:
            logger.debug(f"Failed to load episodic memory: {e}")


# =============================================================================
# COGNITIVE PROCESSES - The Thinking Engine
# =============================================================================

class CognitiveEngine:
    """
    The core cognitive engine that orchestrates all thinking.

    Implements a proper cognitive loop:
    1. Perceive -> 2. Reason -> 3. Plan -> 4. Execute -> 5. Verify -> 6. Learn

    Works with or without LLM - has built-in pattern-based reasoning as fallback.
    """

    # Built-in reasoning patterns (work without LLM)
    OBSTACLE_PATTERNS = {
        "login": ["sign in", "log in", "login", "create account", "register"],
        "captcha": ["captcha", "verify", "robot", "human", "security check"],
        "rate_limit": ["too many", "slow down", "rate limit", "try again"],
        "blocked": ["blocked", "forbidden", "access denied", "not allowed"],
        "not_found": ["not found", "404", "doesn't exist", "no results"],
        "loading": ["loading", "please wait", "spinner"],
        "popup": ["cookie", "accept", "dismiss", "close", "modal", "overlay"],
    }

    SITE_STRATEGIES = {
        "reddit": {
            "primary": "Use JSON API at reddit.com/r/{sub}.json",
            "fallback": "Search via Google: site:reddit.com {query}",
            "obstacles": ["login wall", "rate limit", "age gate"],
        },
        "linkedin": {
            "primary": "Search profiles directly",
            "fallback": "Search via Google: site:linkedin.com/in {query}",
            "obstacles": ["login required", "rate limit", "captcha"],
        },
        "facebook": {
            "primary": "Use FB Ads Library (no login)",
            "fallback": "Search via Google: site:facebook.com/ads/library",
            "obstacles": ["login wall", "region block"],
        },
    }

    GOAL_DECOMPOSITION = {
        "find_users": ["navigate to site", "perform search", "extract results", "filter quality", "format output"],
        "scrape_data": ["navigate to page", "wait for load", "identify elements", "extract data", "save results"],
        "login": ["navigate to login", "find form", "enter credentials", "submit", "verify success"],
    }

    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self.state = CognitiveState.IDLE
        self.working_memory = WorkingMemory()
        self.episodic_memory = EpisodicMemory()
        self.episodic_memory.load()

        # Callbacks for actions
        self._action_callback: Optional[Callable] = None
        self._perception_callback: Optional[Callable] = None

        # Metrics
        self.reasoning_calls = 0
        self.llm_calls = 0
        self.pattern_calls = 0

    def set_callbacks(self, action_cb: Callable = None, perception_cb: Callable = None):
        """Set callbacks for executing actions and perceiving state."""
        self._action_callback = action_cb
        self._perception_callback = perception_cb

    async def set_llm_client(self, client):
        """Set LLM client for advanced reasoning."""
        self.llm_client = client

    # =========================================================================
    # PERCEPTION - Understanding Current State
    # =========================================================================

    async def perceive(self, page_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deeply perceive and understand the current state.

        Returns structured understanding of:
        - What page we're on
        - What obstacles exist
        - What actions are available
        - What's changed since last perception
        """
        self.state = CognitiveState.PERCEIVING

        url = page_state.get("url", "")
        text = page_state.get("text", "").lower()

        # Detect obstacles using patterns
        obstacles = []
        for obstacle_type, patterns in self.OBSTACLE_PATTERNS.items():
            if any(p in text for p in patterns):
                obstacles.append(obstacle_type)

        # Detect site
        site = "unknown"
        for known_site in self.SITE_STRATEGIES.keys():
            if known_site in url.lower():
                site = known_site
                break

        # Get site-specific knowledge from memory
        site_knowledge = self.episodic_memory.get_site_knowledge(site)

        # Detect available actions (simplified)
        actions = []
        if "search" in text or "input" in text:
            actions.append("search")
        if "login" in text or "sign in" in text:
            actions.append("login")
        if "next" in text or "more" in text:
            actions.append("paginate")
        if any(p in text for p in ["result", "item", "card", "listing"]):
            actions.append("extract")

        understanding = {
            "url": url,
            "site": site,
            "obstacles": obstacles,
            "available_actions": actions,
            "site_knowledge": site_knowledge,
            "has_results": "result" in text or "found" in text,
            "is_blocked": len(obstacles) > 0,
            "primary_obstacle": obstacles[0] if obstacles else None,
        }

        # Update working memory
        self.working_memory.page_understanding = understanding
        self.working_memory.detected_obstacles = obstacles
        self.working_memory.available_actions = actions

        return understanding

    # =========================================================================
    # REASONING - Thinking Before Acting
    # =========================================================================

    async def reason(self, goal: str, perception: Dict) -> Dict[str, Any]:
        """
        Multi-step reasoning about what to do.

        This is the core of AGI-like behavior:
        1. Understand the goal deeply
        2. Consider obstacles
        3. Evaluate strategies
        4. Predict outcomes
        5. Select best action

        Uses LLM if available, falls back to pattern-based reasoning.
        """
        self.state = CognitiveState.REASONING
        self.reasoning_calls += 1

        # Check for loops first
        if self.working_memory.detect_loop():
            logger.warning("[Core] Loop detected! Forcing strategy change.")
            return {
                "action": "change_strategy",
                "reason": "Stuck in loop - need different approach",
                "confidence": 0.3,
                "strategy": self._get_fallback_strategy(perception.get("site", "unknown"))
            }

        # Get historical success rate for this type of goal
        success_rate = self.episodic_memory.get_success_rate(goal)

        # Check for obstacles
        obstacles = perception.get("obstacles", [])
        if obstacles:
            # Handle obstacle first
            obstacle = obstacles[0]
            handler = self._get_obstacle_handler(obstacle, perception)
            if handler:
                return {
                    "action": handler["action"],
                    "reason": f"Handling {obstacle} obstacle",
                    "confidence": handler["confidence"],
                    "obstacle": obstacle
                }

        # Decompose goal if needed
        subgoals = self._decompose_goal(goal)
        if subgoals and len(subgoals) > 1:
            # Find current subgoal
            completed = sum(1 for a in self.working_memory.recent_actions if a["success"])
            current_idx = min(completed, len(subgoals) - 1)
            current_subgoal = subgoals[current_idx]

            self.working_memory.subgoals = subgoals
            self.working_memory.current_subgoal_idx = current_idx

            return {
                "action": "execute_subgoal",
                "subgoal": current_subgoal,
                "progress": f"{current_idx + 1}/{len(subgoals)}",
                "reason": f"Working on step {current_idx + 1}: {current_subgoal}",
                "confidence": 0.7
            }

        # Try LLM reasoning if available
        if self.llm_client:
            llm_result = await self._llm_reason(goal, perception)
            if llm_result:
                self.llm_calls += 1
                return llm_result

        # Pattern-based reasoning fallback
        self.pattern_calls += 1
        return self._pattern_reason(goal, perception)

    def _get_obstacle_handler(self, obstacle: str, perception: Dict) -> Optional[Dict]:
        """Get handler for specific obstacle."""
        handlers = {
            "login": {
                "action": "use_fallback",
                "confidence": 0.6,
                "detail": "Login wall detected - try Google site: search"
            },
            "captcha": {
                "action": "wait_and_retry",
                "confidence": 0.4,
                "detail": "Captcha detected - wait and try again"
            },
            "rate_limit": {
                "action": "slow_down",
                "confidence": 0.7,
                "detail": "Rate limited - increase delays"
            },
            "popup": {
                "action": "dismiss_popup",
                "confidence": 0.8,
                "detail": "Popup detected - dismiss it"
            },
            "loading": {
                "action": "wait",
                "confidence": 0.9,
                "detail": "Page loading - wait for completion"
            },
            "blocked": {
                "action": "use_fallback",
                "confidence": 0.5,
                "detail": "Access blocked - try alternative approach"
            },
        }
        return handlers.get(obstacle)

    def _decompose_goal(self, goal: str) -> List[str]:
        """Decompose a goal into subgoals."""
        goal_lower = goal.lower()

        # Find matching goal type
        for goal_type, steps in self.GOAL_DECOMPOSITION.items():
            if goal_type.replace("_", " ") in goal_lower:
                return steps

        # Default decomposition for search-type goals
        if any(w in goal_lower for w in ["find", "search", "get", "extract"]):
            return ["navigate to site", "perform search", "extract results", "format output"]

        return [goal]  # Single step

    def _get_fallback_strategy(self, site: str) -> str:
        """Get fallback strategy for a site."""
        strategies = self.SITE_STRATEGIES.get(site, {})
        return strategies.get("fallback", "Try Google search as alternative")

    async def _llm_reason(self, goal: str, perception: Dict) -> Optional[Dict]:
        """Use LLM for advanced reasoning."""
        try:
            prompt = f"""You are an AGI reasoning about a browser automation task.

Goal: {goal}
Current Page: {perception.get('url', 'unknown')}
Obstacles: {perception.get('obstacles', [])}
Available Actions: {perception.get('available_actions', [])}
Recent Actions: {self.working_memory.get_action_pattern()}

Think step by step:
1. What is the best next action?
2. What could go wrong?
3. What's my confidence level?

Respond in JSON:
{{"action": "the action to take", "reason": "why", "confidence": 0.0-1.0, "risk": "potential problem"}}"""

            response = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                model="0000/ui-tars-1.5-7b:latest",
                temperature=0.1,
                max_tokens=500
            )

            content = response.get("content", "")
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.debug(f"LLM reasoning failed: {e}")
        return None

    def _pattern_reason(self, goal: str, perception: Dict) -> Dict:
        """Pattern-based reasoning fallback."""
        site = perception.get("site", "unknown")

        # Site-specific strategy
        if site in self.SITE_STRATEGIES:
            strategy = self.SITE_STRATEGIES[site]
            if perception.get("is_blocked"):
                return {
                    "action": "use_fallback",
                    "strategy": strategy["fallback"],
                    "reason": f"Primary approach blocked, using fallback for {site}",
                    "confidence": 0.6
                }
            return {
                "action": "use_primary",
                "strategy": strategy["primary"],
                "reason": f"Using primary strategy for {site}",
                "confidence": 0.7
            }

        # Generic strategy
        if perception.get("has_results"):
            return {
                "action": "extract",
                "reason": "Results available - extract them",
                "confidence": 0.8
            }

        if "search" in perception.get("available_actions", []):
            return {
                "action": "search",
                "reason": "Search available - perform search",
                "confidence": 0.7
            }

        return {
            "action": "explore",
            "reason": "Unknown state - explore page",
            "confidence": 0.4
        }

    # =========================================================================
    # PLANNING - Creating Action Sequences
    # =========================================================================

    async def plan(self, goal: str, perception: Dict) -> List[Dict]:
        """
        Create a plan of actions to achieve the goal.

        Returns a sequence of planned actions with:
        - action: what to do
        - expected_outcome: what should happen
        - fallback: what to do if it fails
        """
        self.state = CognitiveState.PLANNING

        subgoals = self._decompose_goal(goal)

        plan = []
        for i, subgoal in enumerate(subgoals):
            step = {
                "step": i + 1,
                "action": subgoal,
                "expected_outcome": f"Complete: {subgoal}",
                "fallback": self._get_fallback_strategy(perception.get("site", "unknown")) if i == 0 else "retry",
                "timeout": 30,
            }
            plan.append(step)

        # Update working memory
        self.working_memory.subgoals = subgoals

        return plan

    # =========================================================================
    # EXECUTION - Taking Actions with Monitoring
    # =========================================================================

    async def execute(self, action: Dict, execute_fn: Callable) -> Dict:
        """
        Execute an action with monitoring and verification.

        Wraps action execution with:
        - Pre-execution check
        - Timeout handling
        - Post-execution verification
        - Error recovery
        """
        self.state = CognitiveState.EXECUTING

        action_desc = action.get("action", str(action))

        # Pre-execution confidence check
        if action.get("confidence", 1.0) < 0.3:
            logger.warning(f"[Core] Low confidence action: {action_desc}")

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                execute_fn(action),
                timeout=action.get("timeout", 30)
            )

            success = result.get("success", True) if isinstance(result, dict) else True

            # Record in working memory
            self.working_memory.add_action(action_desc, str(result)[:100], success)

            return {
                "success": success,
                "result": result,
                "action": action_desc
            }

        except asyncio.TimeoutError:
            self.working_memory.add_action(action_desc, "timeout", False)
            return {
                "success": False,
                "error": "timeout",
                "action": action_desc
            }
        except Exception as e:
            self.working_memory.add_action(action_desc, str(e)[:100], False)
            return {
                "success": False,
                "error": str(e),
                "action": action_desc
            }

    # =========================================================================
    # VERIFICATION - Checking Outcomes
    # =========================================================================

    async def verify(self, expected: str, actual: Dict) -> Dict[str, Any]:
        """
        Verify if action achieved expected outcome.

        Returns:
        - success: bool
        - confidence: how sure we are
        - discrepancy: what's different from expected
        """
        self.state = CognitiveState.VERIFYING

        if actual.get("error"):
            return {
                "success": False,
                "confidence": 0.9,
                "discrepancy": f"Error occurred: {actual['error']}"
            }

        # Simple verification - check if result looks successful
        result = actual.get("result", {})
        if isinstance(result, dict):
            if result.get("status") == "complete":
                return {"success": True, "confidence": 0.9, "discrepancy": None}
            if result.get("data") or result.get("leads"):
                return {"success": True, "confidence": 0.8, "discrepancy": None}

        # Uncertain
        return {
            "success": None,  # Unknown
            "confidence": 0.5,
            "discrepancy": "Unable to verify outcome"
        }

    # =========================================================================
    # LEARNING - Improving from Experience
    # =========================================================================

    async def learn(self, goal: str, actions: List[Dict], outcome: str, success: bool):
        """
        Learn from the episode.

        Records the episode and extracts patterns for future use.
        """
        self.state = CognitiveState.LEARNING

        # Record in episodic memory
        self.episodic_memory.record_episode(goal, actions, outcome, success)

        # Extract and store patterns
        if success:
            # Learn what worked
            action_pattern = " -> ".join(a.get("action", "")[:20] for a in actions)
            self.working_memory.session_patterns[f"success:{goal[:30]}"] = action_pattern
        else:
            # Learn what to avoid
            if actions:
                last_action = actions[-1].get("action", "")
                self.working_memory.session_patterns[f"avoid:{goal[:30]}"] = last_action

        logger.info(f"[Core] Learned from episode: {goal[:30]}... -> {'success' if success else 'failure'}")

    # =========================================================================
    # METACOGNITION - Thinking About Thinking
    # =========================================================================

    async def metacognize(self) -> Dict[str, Any]:
        """
        Meta-cognitive analysis of own reasoning process.

        Checks:
        - Am I stuck in a loop?
        - Is my strategy working?
        - Should I change approach?
        - What am I uncertain about?
        """
        analysis = {
            "in_loop": self.working_memory.detect_loop(),
            "confidence": self.working_memory.confidence,
            "actions_taken": len(self.working_memory.recent_actions),
            "success_rate": self._calculate_session_success_rate(),
            "should_change_strategy": False,
            "recommendation": None
        }

        # Check if strategy needs changing
        if analysis["in_loop"]:
            analysis["should_change_strategy"] = True
            analysis["recommendation"] = "Stuck in loop - try completely different approach"
        elif analysis["success_rate"] < 0.3 and analysis["actions_taken"] > 3:
            analysis["should_change_strategy"] = True
            analysis["recommendation"] = "Low success rate - consider fallback strategy"
        elif self.working_memory.confidence < 0.4:
            analysis["recommendation"] = "Low confidence - gather more information first"

        return analysis

    def _calculate_session_success_rate(self) -> float:
        """Calculate success rate for current session."""
        if not self.working_memory.recent_actions:
            return 0.5
        successes = sum(1 for a in self.working_memory.recent_actions if a["success"])
        return successes / len(self.working_memory.recent_actions)

    # =========================================================================
    # MAIN COGNITIVE LOOP
    # =========================================================================

    async def think_and_act(
        self,
        goal: str,
        get_state_fn: Callable,
        execute_fn: Callable,
        max_steps: int = 10
    ) -> Dict[str, Any]:
        """
        Main cognitive loop: Perceive -> Reason -> Plan -> Execute -> Verify -> Learn

        This is the entry point for AGI-like behavior.
        """
        self.working_memory.primary_goal = goal
        all_actions = []
        final_result = None

        logger.info(f"[Core] Starting cognitive loop for: {goal[:50]}...")

        for step in range(max_steps):
            # 1. PERCEIVE
            page_state = await get_state_fn()
            perception = await self.perceive(page_state)

            # 2. METACOGNIZE - check if we need to change approach
            meta = await self.metacognize()
            if meta["should_change_strategy"]:
                logger.warning(f"[Core] Meta: {meta['recommendation']}")
                # Force a different approach
                perception["force_fallback"] = True

            # 3. REASON
            reasoning = await self.reason(goal, perception)
            logger.debug(f"[Core] Step {step + 1}: {reasoning.get('action')} ({reasoning.get('confidence', 0):.1%} confidence)")

            # 4. Check for completion
            if reasoning.get("action") == "done" or perception.get("has_results"):
                final_result = {"status": "complete", "step": step + 1}
                break

            # 5. EXECUTE
            execution_result = await self.execute(reasoning, execute_fn)
            all_actions.append({
                "action": reasoning.get("action"),
                "result": str(execution_result.get("result", ""))[:100],
                "success": execution_result.get("success", False)
            })

            # 6. VERIFY
            verification = await self.verify(reasoning.get("expected_outcome", ""), execution_result)

            if not execution_result.get("success"):
                # Action failed - will trigger recovery in next iteration
                self.working_memory.confidence *= 0.8

        # 7. LEARN from this episode
        success = final_result is not None and final_result.get("status") == "complete"
        await self.learn(goal, all_actions, str(final_result), success)

        return {
            "goal": goal,
            "success": success,
            "steps": len(all_actions),
            "final_result": final_result,
            "actions": all_actions,
            "metrics": {
                "reasoning_calls": self.reasoning_calls,
                "llm_calls": self.llm_calls,
                "pattern_calls": self.pattern_calls
            }
        }

    def reset_session(self):
        """Reset working memory for new session (keep episodic memory)."""
        self.working_memory = WorkingMemory()
        self.state = CognitiveState.IDLE
        self.reasoning_calls = 0
        self.llm_calls = 0
        self.pattern_calls = 0


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_cognitive_engine: Optional[CognitiveEngine] = None

def get_cognitive_engine() -> CognitiveEngine:
    """Get or create the global cognitive engine."""
    global _cognitive_engine
    if _cognitive_engine is None:
        _cognitive_engine = CognitiveEngine()
    return _cognitive_engine


async def think_before_act(goal: str, page_state: Dict) -> Dict:
    """Quick helper to get reasoning for a goal."""
    engine = get_cognitive_engine()
    perception = await engine.perceive(page_state)
    return await engine.reason(goal, perception)


def get_historical_success_rate(goal: str) -> float:
    """Get success rate for similar goals from memory."""
    engine = get_cognitive_engine()
    return engine.episodic_memory.get_success_rate(goal)
