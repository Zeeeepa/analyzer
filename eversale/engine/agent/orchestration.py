"""
Workflow Orchestration Engine

Extracted from brain_enhanced_v2.py to handle:
- Main execution entry point (run)
- Streaming execution with timeouts
- Loop modes (timed, counted, infinite, scheduled)
- Task scheduling and one-time scheduled tasks
- Data extraction and result saving

This module provides the OrchestrationMixin class that can be
inherited by the main agent brain class.
"""

import asyncio
import hashlib
import json
import re
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger
from rich.console import Console

# Import goal sequencer for multi-step prompts
try:
    from .goal_sequencer import (
        parse_goals, is_multi_goal, advance_goal, get_next_goal,
        GoalSequence, GoalStatus, GoalType
    )
    GOAL_SEQUENCER_AVAILABLE = True
except ImportError:
    GOAL_SEQUENCER_AVAILABLE = False
    logger.warning("Goal sequencer not available - multi-goal prompts will not be handled")

# Import command parser for deterministic action execution
try:
    from .command_parser import parse_command, can_execute_directly, get_mcp_calls, ActionType
    COMMAND_PARSER_AVAILABLE = True
except ImportError:
    COMMAND_PARSER_AVAILABLE = False
    logger.debug("Command parser not available - using LLM for all commands")

# Import action templates for common patterns
try:
    from .action_templates import find_template, execute_template
    TEMPLATES_AVAILABLE = True
except ImportError:
    TEMPLATES_AVAILABLE = False
    logger.debug("Action templates not available")

# Import intelligent task router for deterministic workflows
try:
    from .intelligent_task_router import (
        route_task, ExecutionPath, RoutingDecision
    )
    from .deterministic_workflows import (
        match_workflow, extract_params, execute_workflow
    )
    INTELLIGENT_ROUTING_AVAILABLE = True
except ImportError:
    INTELLIGENT_ROUTING_AVAILABLE = False
    logger.debug("Intelligent task routing not available")

# Import forever task state for checkpoint support
try:
    from .forever_operations import (
        ForeverTaskState,
        CircuitBreaker,
        cleanup_resources_between_iterations,
        recycle_browser_if_needed
    )
    FOREVER_OPS_AVAILABLE = True
except ImportError:
    ForeverTaskState = None
    CircuitBreaker = None
    cleanup_resources_between_iterations = None
    recycle_browser_if_needed = None
    FOREVER_OPS_AVAILABLE = False

# Import health monitoring
try:
    from .health_check import HealthWriter, start_health_monitoring, stop_health_monitoring
    HEALTH_MONITORING_AVAILABLE = True
except ImportError:
    HealthWriter = None
    start_health_monitoring = None
    stop_health_monitoring = None
    HEALTH_MONITORING_AVAILABLE = False

# Import security guardrails
try:
    from .security_guardrails import check_security, get_refusal_message
except ImportError:
    check_security = None
    get_refusal_message = None

# Import resource limits
try:
    from .resource_limits import ResourceLimitError
except ImportError:
    ResourceLimitError = Exception

# Strategic planner availability
try:
    from .kimi_k2_client import should_use_kimi_planning
    STRATEGIC_PLANNER_AVAILABLE = True
except ImportError:
    STRATEGIC_PLANNER_AVAILABLE = False
    should_use_kimi_planning = lambda p, c: False

# HTN Planning agent for complex multi-step tasks
try:
    from planning_agent import PlanningAgent, quick_plan_and_execute
    from complexity_detector import is_complex_task, get_complexity_score
    HTN_PLANNING_AVAILABLE = True
except ImportError:
    try:
        from .planning_agent import PlanningAgent, quick_plan_and_execute
        from .complexity_detector import is_complex_task, get_complexity_score
        HTN_PLANNING_AVAILABLE = True
    except ImportError as e:
        HTN_PLANNING_AVAILABLE = False
        PlanningAgent = None
        quick_plan_and_execute = None
        is_complex_task = lambda p, c: False
        get_complexity_score = lambda p: 0.0
        logger.debug(f"HTN planning agent not available: {e}")

# Multi-agent system for complex multi-step tasks
try:
    from .multi_agent import (
        AgentOrchestrator, AgentRole, TaskPriority,
        create_agent_swarm, execute_task_with_swarm
    )
    MULTI_AGENT_AVAILABLE = True
except ImportError:
    MULTI_AGENT_AVAILABLE = False
    logger.debug("Multi-agent system not available")

try:
    from .prompt_processor import DIRECT_MODE_PROMPT
except ImportError:
    DIRECT_MODE_PROMPT = ""


try:
    from .todo_manager import get_todo_manager, TodoPriority, TodoStatus
    TODO_MANAGER_AVAILABLE = True
except ImportError:
    TODO_MANAGER_AVAILABLE = False
    get_todo_manager = None
    TodoPriority = None
    TodoStatus = None

# AGI-like reasoning for smarter execution
try:
    from .agi_reasoning import (
        AGIReasoning, get_agi_reasoning, SelfHealingLoop,
        reason_before_action, verify_action_success, get_smart_correction
    )
    AGI_REASONING_AVAILABLE = True
except ImportError:
    AGI_REASONING_AVAILABLE = False
    AGIReasoning = None
    get_agi_reasoning = None
    SelfHealingLoop = None
    logger.debug("AGI reasoning not available")

# === RESILIENCE SYSTEMS (v2.10+) ===
# Self-healing system for adaptive error recovery
try:
    from .self_healing_system import self_healing, SelfHealingSystem
    SELF_HEALING_AVAILABLE = True
except ImportError:
    SELF_HEALING_AVAILABLE = False
    self_healing = None
    SelfHealingSystem = None
    logger.debug("Self-healing system not available")

# Retry system with exponential backoff
try:
    from .retry_system import retry_with_backoff, RetryManager, RetryConfig
    RETRY_SYSTEM_AVAILABLE = True
except ImportError:
    RETRY_SYSTEM_AVAILABLE = False
    retry_with_backoff = None
    RetryManager = None
    RetryConfig = None
    logger.debug("Retry system not available")

# Autonomous challenge resolver for CAPTCHA/Cloudflare
try:
    from .autonomous_challenge_resolver import (
        AutonomousChallengeResolver, get_autonomous_resolver, resolve_any_challenge
    )
    CHALLENGE_RESOLVER_AVAILABLE = True
except ImportError:
    CHALLENGE_RESOLVER_AVAILABLE = False
    AutonomousChallengeResolver = None
    get_autonomous_resolver = None
    resolve_any_challenge = None
    logger.debug("Autonomous challenge resolver not available")

# Site profiles for bot-protected domains (headful mode, extended timeouts)
try:
    from .site_profiles import (
        get_site_profile, is_bot_protected, should_use_headful,
        get_timeout_for_site, get_wait_time, configure_browser_for_site,
        PROTECTED_DOMAINS
    )
    SITE_PROFILES_AVAILABLE = True
except ImportError:
    SITE_PROFILES_AVAILABLE = False
    get_site_profile = None
    is_bot_protected = None
    should_use_headful = None
    get_timeout_for_site = None
    get_wait_time = None
    configure_browser_for_site = None
    PROTECTED_DOMAINS = set()
    logger.debug("Site profiles not available")

console = Console()


# =============================================================================
# PROSPECT COLLECTOR - Cross-goal deduplication and final summary for SDRs
# =============================================================================

class ProspectCollector:
    """
    Collects and deduplicates prospects across multiple goals.

    Designed for SDR use cases - provides:
    - Cross-goal deduplication by URL/ID
    - Smart failure detection (login walls, no results, rate limits)
    - Final summary with all unique prospects
    - Actionable suggestions when failures occur
    """

    def __init__(self):
        self.prospects = {
            'fb_ads': [],      # {'name': str, 'url': str}
            'linkedin': [],    # {'name': str, 'url': str, 'type': 'profile'|'company'}
            'reddit': [],      # {'username': str, 'url': str}
            'google_maps': [], # {'name': str, 'url': str}
            'other': []        # Catch-all for unknown sources
        }
        self.seen_urls = set()  # For deduplication
        self.seen_names = set()  # Secondary dedup by name (case-insensitive)
        self.failures = []  # Track failures with reasons
        self.successes = []  # Track successful extractions
        self.suggestions = []  # Actionable suggestions for user

    def parse_and_collect(self, result: str, goal_description: str) -> int:
        """
        Parse goal result and collect prospects.

        Returns number of NEW prospects added (after deduplication).
        """
        if not result:
            return 0

        result_lower = result.lower()
        goal_lower = goal_description.lower()
        new_count = 0

        # Detect failure patterns and provide actionable suggestions
        failure_info = self._detect_failure(result, goal_description)
        if failure_info:
            self.failures.append(failure_info)
            return 0

        # Parse based on result content
        if 'fb advertiser' in result_lower or 'advertiser url' in result_lower:
            new_count = self._parse_fb_ads(result)
            if new_count > 0:
                self.successes.append({'source': 'FB Ads', 'count': new_count, 'goal': goal_description[:50]})
        elif 'linkedin profile' in result_lower or 'linkedin company' in result_lower:
            new_count = self._parse_linkedin(result)
            if new_count > 0:
                self.successes.append({'source': 'LinkedIn', 'count': new_count, 'goal': goal_description[:50]})
        elif 'reddit user' in result_lower or 'profile url: https://www.reddit.com/user' in result_lower:
            new_count = self._parse_reddit(result)
            if new_count > 0:
                self.successes.append({'source': 'Reddit', 'count': new_count, 'goal': goal_description[:50]})
        elif 'google maps' in result_lower or 'maps url' in result_lower:
            new_count = self._parse_google_maps(result)
            if new_count > 0:
                self.successes.append({'source': 'Google Maps', 'count': new_count, 'goal': goal_description[:50]})

        return new_count

    def _detect_failure(self, result: str, goal: str) -> Optional[Dict]:
        """Detect failure patterns and return actionable info."""
        result_lower = result.lower()
        goal_lower = goal.lower()

        # Login required detection
        login_patterns = [
            'login required', 'sign in', 'log in to', 'please log in',
            'authentication required', 'session expired', 'access denied',
            'you must be logged in', 'create an account'
        ]
        if any(p in result_lower for p in login_patterns):
            site = self._identify_site(goal)
            return {
                'type': 'login_required',
                'goal': goal[:50],
                'site': site,
                'suggestion': f"Log into {site} in your browser first, then retry"
            }

        # No results detection
        no_results_patterns = [
            'no results', 'nothing found', '0 results', 'no matches',
            'no advertisers found', 'no profiles found', 'no users found',
            'could not find', 'no businesses found'
        ]
        if any(p in result_lower for p in no_results_patterns):
            return {
                'type': 'no_results',
                'goal': goal[:50],
                'suggestion': "Try different search terms or broader keywords"
            }

        # Rate limiting detection
        rate_limit_patterns = [
            'rate limit', 'too many requests', 'slow down', 'try again later',
            'temporarily blocked', 'unusual traffic', 'captcha'
        ]
        if any(p in result_lower for p in rate_limit_patterns):
            return {
                'type': 'rate_limited',
                'goal': goal[:50],
                'suggestion': "Wait a few minutes before retrying, or use a different account"
            }

        # Page load failure
        load_failure_patterns = [
            'failed to load', 'timeout', 'page not found', '404', '500',
            'connection refused', 'network error'
        ]
        if any(p in result_lower for p in load_failure_patterns):
            return {
                'type': 'load_failure',
                'goal': goal[:50],
                'suggestion': "Check your internet connection and retry"
            }

        return None

    def _identify_site(self, goal: str) -> str:
        """Identify which site the goal is targeting."""
        goal_lower = goal.lower()
        if 'fb ads' in goal_lower or 'facebook' in goal_lower or 'ads library' in goal_lower:
            return 'Facebook'
        elif 'linkedin' in goal_lower:
            return 'LinkedIn'
        elif 'reddit' in goal_lower:
            return 'Reddit'
        elif 'google maps' in goal_lower or 'maps' in goal_lower:
            return 'Google Maps'
        elif 'gmail' in goal_lower:
            return 'Gmail'
        elif 'zoho' in goal_lower:
            return 'Zoho Mail'
        return 'the site'

    def _parse_fb_ads(self, result: str) -> int:
        """Parse FB Ads advertiser results."""
        import re
        new_count = 0

        # Pattern: "1. Name" followed by "Advertiser URL: https://..."
        lines = result.split('\n')
        current_name = None

        for line in lines:
            line = line.strip()

            # Match numbered name: "1. Company Name"
            name_match = re.match(r'\d+\.\s+(.+)', line)
            if name_match:
                current_name = name_match.group(1).strip()
                continue

            # Match URL line: "Advertiser URL: https://facebook.com/..."
            url_match = re.match(r'Advertiser URL:\s*(https?://[^\s]+)', line, re.I)
            if url_match and current_name:
                url = url_match.group(1).strip()
                if url not in self.seen_urls and current_name.lower() not in self.seen_names:
                    self.seen_urls.add(url)
                    self.seen_names.add(current_name.lower())
                    self.prospects['fb_ads'].append({'name': current_name, 'url': url})
                    new_count += 1
                current_name = None

        return new_count

    def _parse_linkedin(self, result: str) -> int:
        """Parse LinkedIn profile/company results."""
        import re
        new_count = 0
        lines = result.split('\n')
        current_name = None
        is_company = 'company' in result.lower()

        for line in lines:
            line = line.strip()

            name_match = re.match(r'\d+\.\s+(.+)', line)
            if name_match:
                current_name = name_match.group(1).strip()
                continue

            url_match = re.match(r'(?:Profile|Company) URL:\s*(https?://[^\s]+)', line, re.I)
            if url_match and current_name:
                url = url_match.group(1).strip()
                if url not in self.seen_urls and current_name.lower() not in self.seen_names:
                    self.seen_urls.add(url)
                    self.seen_names.add(current_name.lower())
                    self.prospects['linkedin'].append({
                        'name': current_name,
                        'url': url,
                        'type': 'company' if is_company else 'profile'
                    })
                    new_count += 1
                current_name = None

        return new_count

    def _parse_reddit(self, result: str) -> int:
        """Parse Reddit user results."""
        import re
        new_count = 0
        lines = result.split('\n')
        current_username = None

        for line in lines:
            line = line.strip()

            # Match: "1. u/username"
            name_match = re.match(r'\d+\.\s+u/(.+)', line)
            if name_match:
                current_username = name_match.group(1).strip()
                continue

            url_match = re.match(r'Profile URL:\s*(https?://[^\s]+)', line, re.I)
            if url_match and current_username:
                url = url_match.group(1).strip()
                if url not in self.seen_urls and current_username.lower() not in self.seen_names:
                    self.seen_urls.add(url)
                    self.seen_names.add(current_username.lower())
                    self.prospects['reddit'].append({'username': current_username, 'url': url})
                    new_count += 1
                current_username = None

        return new_count

    def _parse_google_maps(self, result: str) -> int:
        """Parse Google Maps business results."""
        import re
        new_count = 0
        lines = result.split('\n')
        current_name = None

        for line in lines:
            line = line.strip()

            name_match = re.match(r'\d+\.\s+(.+)', line)
            if name_match:
                current_name = name_match.group(1).strip()
                continue

            url_match = re.match(r'Maps URL:\s*(https?://[^\s]+)', line, re.I)
            if url_match and current_name:
                url = url_match.group(1).strip()
                if url not in self.seen_urls and current_name.lower() not in self.seen_names:
                    self.seen_urls.add(url)
                    self.seen_names.add(current_name.lower())
                    self.prospects['google_maps'].append({'name': current_name, 'url': url})
                    new_count += 1
                current_name = None

        return new_count

    def get_total_count(self) -> int:
        """Get total unique prospect count."""
        return sum(len(v) for v in self.prospects.values())

    def generate_summary(self) -> str:
        """Generate final summary for SDRs."""
        lines = []
        total = self.get_total_count()

        lines.append("")
        lines.append("=" * 60)
        lines.append("PROSPECTING SUMMARY")
        lines.append("=" * 60)

        # Success stats
        succeeded = len(self.successes)
        failed = len(self.failures)
        lines.append(f"Goals: {succeeded} succeeded, {failed} failed")
        lines.append(f"Total Unique Prospects: {total}")
        lines.append("")

        # FB Ads
        if self.prospects['fb_ads']:
            lines.append(f"FB Ads Advertisers ({len(self.prospects['fb_ads'])}):")
            for p in self.prospects['fb_ads']:
                lines.append(f"  - {p['name']}")
                lines.append(f"    {p['url']}")
            lines.append("")

        # LinkedIn
        if self.prospects['linkedin']:
            profiles = [p for p in self.prospects['linkedin'] if p.get('type') == 'profile']
            companies = [p for p in self.prospects['linkedin'] if p.get('type') == 'company']

            if profiles:
                lines.append(f"LinkedIn Profiles ({len(profiles)}):")
                for p in profiles:
                    lines.append(f"  - {p['name']}")
                    lines.append(f"    {p['url']}")
                lines.append("")

            if companies:
                lines.append(f"LinkedIn Companies ({len(companies)}):")
                for p in companies:
                    lines.append(f"  - {p['name']}")
                    lines.append(f"    {p['url']}")
                lines.append("")

        # Reddit
        if self.prospects['reddit']:
            lines.append(f"Reddit Users ({len(self.prospects['reddit'])}):")
            for p in self.prospects['reddit']:
                lines.append(f"  - u/{p['username']}")
                lines.append(f"    {p['url']}")
            lines.append("")

        # Google Maps
        if self.prospects['google_maps']:
            lines.append(f"Google Maps Businesses ({len(self.prospects['google_maps'])}):")
            for p in self.prospects['google_maps']:
                lines.append(f"  - {p['name']}")
                if p.get('url'):
                    lines.append(f"    {p['url']}")
            lines.append("")

        # Failures and suggestions
        if self.failures:
            lines.append("Issues Encountered:")
            for f in self.failures:
                lines.append(f"  - [{f['type']}] {f['goal']}")
                lines.append(f"    Suggestion: {f['suggestion']}")
            lines.append("")

        lines.append("=" * 60)

        return "\n".join(lines)


class OrchestrationMixin:
    """
    Mixin class providing workflow orchestration capabilities.

    This class should be inherited by the main agent brain class.
    It expects the following attributes to be present on self:
    - crash_recovery: CrashRecovery instance
    - _steering_enabled: bool
    - _steering: SteeringInput instance
    - mcp: MCP client
    - awareness: AwarenessHub instance
    - survival: SurvivalManager instance
    - memory: AgentMemory instance
    - memory_arch: MemoryArchitecture instance (optional)
    - context_memory: ContextMemory instance
    - resource_limiter: ResourceLimiter instance (optional)
    - resource_monitor: ResourceMonitor instance
    - dead_mans_switch: DeadMansSwitch instance (optional)
    - prompt_processor: PromptProcessor instance
    - strategic_planner: StrategicPlanner instance (optional)
    - config: dict
    - iteration: int
    - stats: Dict
    - task_timeout: int
    - _forever_mode: bool
    - _last_checkpoint_time: datetime (optional)
    - _prompt_count: int
    - _review_interval: int
    - _consolidation_task: asyncio.Task (optional)
    - _describe_retry_done: bool
    - _execution_log: List
    - _task_start_time: datetime
    - _next_health_check_time: datetime
    - _last_issues: List
    - _preflight_details: List
    """

    async def cleanup_state(self):
        """
        Reset all state between goal runs to prevent state bleed.

        This ensures each goal starts with a clean slate:
        - Stops steering input listener if running
        - Clears plan caches to prevent reusing old plans
        - Resets execution logs and stats
        - Clears forever mode flags
        - Resets fast mode executor state if available
        """
        # Stop steering if running
        if hasattr(self, '_steering') and self._steering and hasattr(self._steering, 'is_running'):
            try:
                if self._steering.is_running():
                    self._steering.stop()
            except Exception as e:
                logger.debug(f"Failed to stop steering: {e}")

        # Clear plan caches
        for attr in ['_last_plan_prompt', '_cached_plan']:
            if hasattr(self, attr):
                try:
                    delattr(self, attr)
                except Exception as e:
                    logger.debug(f"Failed to delete {attr}: {e}")

        # Clear execution logs
        if hasattr(self, '_execution_log'):
            try:
                self._execution_log.clear()
            except Exception as e:
                logger.debug(f"Failed to clear execution log: {e}")

        # Clear issue tracking
        if hasattr(self, '_last_issues'):
            self._last_issues = []
        if hasattr(self, '_preflight_details'):
            self._preflight_details = []

        # Reset stats
        if hasattr(self, 'stats'):
            self.stats = {}

        # Reset forever mode flags
        if hasattr(self, '_forever_mode'):
            self._forever_mode = False
        if hasattr(self, '_last_checkpoint_time'):
            self._last_checkpoint_time = None

        # Reset fast mode executor state if available
        if hasattr(self, 'fast_mode_executor') and self.fast_mode_executor:
            try:
                if hasattr(self.fast_mode_executor, 'reset'):
                    await self.fast_mode_executor.reset()
            except Exception as e:
                logger.debug(f"Failed to reset fast mode executor: {e}")

        logger.debug("[STATE CLEANUP] All state reset for next goal")
        if hasattr(self, '_goal_todo_map'):
            self._goal_todo_map.clear()

    def _get_todo_session_id(self) -> Optional[str]:
        """Determine session identifier for todo tracking."""
        if hasattr(self, 'session_state') and getattr(self.session_state, 'session_id', None):
            return self.session_state.session_id
        if getattr(self, 'session_id', None):
            return self.session_id
        if getattr(self, 'memory_arch', None) and getattr(self.memory_arch, 'current_session_id', None):
            return self.memory_arch.current_session_id
        return None

    def _map_goal_priority(self, goal) -> 'TodoPriority':
        """Map goal characteristics to todo priority."""
        if not TODO_MANAGER_AVAILABLE:
            return None
        if goal.goal_type == GoalType.CONDITIONAL or not goal.is_blocking:
            return TodoPriority.LOW
        if goal.goal_type == GoalType.EXTRACTION or goal.goal_type == GoalType.ASSERTION:
            return TodoPriority.HIGH
        return TodoPriority.MEDIUM

    def _initialize_goal_todos(self, sequence_id: str, sequence: 'GoalSequence'):
        """Ensure each goal in the sequence has a corresponding todo item."""
        if not (TODO_MANAGER_AVAILABLE and sequence_id and sequence):
            return

        session_id = self._get_todo_session_id()
        if not session_id:
            return

        manager = get_todo_manager()

        if not hasattr(self, '_goal_todo_map'):
            self._goal_todo_map: Dict[str, Dict[int, str]] = {}

        sequence_map = self._goal_todo_map.setdefault(sequence_id, {})

        # Map existing todos that belong to this sequence
        for todo in manager.get(session_id):
            meta = getattr(todo, 'metadata', {}) or {}
            if meta.get('sequence_id') != sequence_id:
                continue
            goal_index = meta.get('goal_index')
            if goal_index is None:
                continue
            sequence_map[goal_index] = todo.id
            # Align status if already completed or executing
            if goal_index < len(sequence.goals):
                goal = sequence.goals[goal_index]
                if goal.status == GoalStatus.COMPLETED:
                    manager.complete(session_id, todo.id)
                elif goal.status == GoalStatus.EXECUTING:
                    manager.set_in_progress(session_id, todo.id)

        # Create todos for missing goals
        for goal in sequence.goals:
            if goal.index in sequence_map:
                continue

            priority = self._map_goal_priority(goal) or TodoPriority.MEDIUM
            todo = manager.add(
                session_id,
                f"Goal {goal.index + 1}: {goal.description}",
                priority=priority,
                metadata={"sequence_id": sequence_id, "goal_index": goal.index}
            )
            sequence_map[goal.index] = todo.id

            if goal.status == GoalStatus.COMPLETED:
                manager.complete(session_id, todo.id)

    def _update_goal_todo_status(self, sequence_id: str, goal, status: 'TodoStatus'):
        """Update todo status for a specific goal."""
        if not (TODO_MANAGER_AVAILABLE and sequence_id and goal and status):
            return

        session_id = self._get_todo_session_id()
        if not session_id:
            return

        if not hasattr(self, '_goal_todo_map'):
            return

        todo_id = self._goal_todo_map.get(sequence_id, {}).get(goal.index)
        if not todo_id:
            return

        manager = get_todo_manager()
        try:
            if status == TodoStatus.IN_PROGRESS:
                manager.set_in_progress(session_id, todo_id)
            elif status == TodoStatus.COMPLETED:
                manager.complete(session_id, todo_id)
            elif status == TodoStatus.CANCELLED:
                manager.cancel(session_id, todo_id)
        except Exception as e:
            logger.debug(f"Todo status update failed: {e}")

    def _finalize_goal_todos(self, sequence_id: Optional[str], sequence: Optional['GoalSequence']):
        """Finalize todos when sequence completes or aborts."""
        if not TODO_MANAGER_AVAILABLE or not sequence_id:
            return
        if not hasattr(self, '_goal_todo_map'):
            return

        if sequence:
            if sequence.is_complete:
                for goal in sequence.goals:
                    if goal.status == GoalStatus.COMPLETED:
                        self._update_goal_todo_status(sequence_id, goal, TodoStatus.COMPLETED)
                    elif goal.status in (GoalStatus.SKIPPED, GoalStatus.FAILED):
                        self._update_goal_todo_status(sequence_id, goal, TodoStatus.CANCELLED)
            else:
                for goal in sequence.goals:
                    if goal.status in (GoalStatus.FAILED, GoalStatus.SKIPPED):
                        self._update_goal_todo_status(sequence_id, goal, TodoStatus.CANCELLED)

        self._goal_todo_map.pop(sequence_id, None)

    def _should_use_multi_agent(self, prompt: str) -> bool:
        """
        Detect if task is suitable for multi-agent execution.

        Multi-agent is ideal for:
        - Multiple URLs to process
        - Multiple extraction types (research + extract + validate + analyze)
        - Long-running workflows with parallel opportunities
        - Tasks with explicit mentions of multiple steps

        Returns:
            True if multi-agent should be used, False otherwise
        """
        if not MULTI_AGENT_AVAILABLE:
            return False

        lower = prompt.lower()

        # Count URLs in prompt
        import re
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, prompt)
        has_multiple_urls = len(urls) >= 3

        # Check for multiple extraction types
        extraction_keywords = ['research', 'extract', 'validate', 'analyze', 'compare', 'summarize']
        extraction_count = sum(1 for kw in extraction_keywords if kw in lower)
        has_multiple_extractions = extraction_count >= 3

        # Check for explicit multi-step mentions
        multi_step_indicators = [
            'multiple sites', 'several websites', 'batch of urls',
            'research and extract', 'extract and validate', 'gather and analyze',
            'for each url', 'process all', 'scrape multiple'
        ]
        has_multi_step = any(ind in lower for ind in multi_step_indicators)

        # Check for long workflow indicators
        long_workflow_indicators = [
            'comprehensive', 'thorough', 'deep dive', 'full analysis',
            'collect everything', 'all data', 'complete extraction'
        ]
        has_long_workflow = any(ind in lower for ind in long_workflow_indicators)

        # Decision logic
        if has_multiple_urls and has_multiple_extractions:
            logger.info("[MULTI-AGENT] Detected: Multiple URLs + Multiple extractions")
            return True

        if has_multiple_urls and has_multi_step:
            logger.info("[MULTI-AGENT] Detected: Multiple URLs + Multi-step workflow")
            return True

        if has_multiple_extractions and has_long_workflow:
            logger.info("[MULTI-AGENT] Detected: Multiple extractions + Long workflow")
            return True

        return False

    async def __aenter__(self):
        """Async context manager entry - allows using OrchestrationMixin with 'async with'."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures cleanup even on errors."""
        await self.cleanup_state()
        return False

    async def _run_direct_mode(self, prompt: str) -> str:
        """
        DIRECT MODE: Execute instructions with strict adherence using Playwright MCP tools.
        
        This mode bypasses the ReAct loop and reasoning engine to provider a 
        literal, mechanical execution path ("Playwright MCP" style).
        
        It relies on:
        1. browser_snapshot (to get mmid refs)
        2. LLM instruction following (DIRECT_MODE_PROMPT)
        3. Direct MCP tool calls (browser_click, browser_type, etc.)
        """
        logger.info(f"⚡ DIRECT MODE ACTIVATED: {prompt}")
        
        # Ensure browser is ready
        if not self.mcp:
            return "Error: MCP client not initialized"
            
        # Initial navigation if requested
        # (Naive check - real logic is handled by LLM in loop, but helpful to start)
        if prompt.startswith("http") or "navigate to" in prompt.lower():
             pass # Let loop handle it
             
        max_steps = 30  # Increased from 20 for complex tasks (v2.10)
        history = []
        
        for i in range(max_steps):
            logger.debug(f"[DirectMode] Step {i+1}/{max_steps}")
            
            # 1. Get Page State (Snapshot)
            # We use browser_snapshot to get accessibility tree + mmids
            try:
                snapshot_result = await self.mcp.call_tool("browser_snapshot", {})
                
                state_desc = ""
                if snapshot_result.get("success"):
                     # Format simplified state for LLM (url + snapshot text)
                     state_desc = f"URL: {snapshot_result.get('url')}\nTitle: {snapshot_result.get('title')}\n\nInteractive Elements:\n{snapshot_result.get('snapshot')}"
                else:
                     state_desc = f"Error getting snapshot: {snapshot_result.get('error')}"
            except Exception as e:
                state_desc = f"Critical Snapshot Error: {e}"

            # 2. Construct Prompt
            # Combine system prompt + user task + current state
            # We don't use message history for the *system* prompt part in this simple mode,
            # but we append the last few actions to avoid loops
            
            full_prompt = DIRECT_MODE_PROMPT.format(state=state_desc, prompt=prompt)
            
            messages = [
                {"role": "user", "content": full_prompt}
            ]
            
            # Add recent history context (last 3 steps)
            if history:
                 messages.append({"role": "user", "content": "Recent History:\n" + "\n".join(history[-3:])})

            # 3. Call LLM
            # Use raw model access if available, or fall back to standard generation
            logger.debug("[DirectMode] Sending to LLM...")
            
            # We need a way to call the model. 
            # Assuming self.llm or self._generate_response is available (from AgentBrain)
            # Since this is a mixin, we rely on the host class having it.
            # Using self.model.generate() or similar.
            # Let's try to find the standard generation method.
            # 'generate_response' is common.
            
            try:
                # We enforce JSON mode via prompt, but nice to have in API too if supported
                response_text = await self._generate_llm_response(messages) # Helper we might need to find/add
            except AttributeError:
                 # Fallback if _generate_llm_response not found (handle different Brain versions)
                 # Reverting to self.model.generate if available
                 if hasattr(self, 'model'):
                      response_text = await self.model.a_generate(messages) # Hypothetical
                 else:
                      return "Error: No LLM available for Direct Mode"

            # 4. Parse Action
            try:
                # Extract first complete JSON object with proper brace matching
                action_data = None
                start_idx = response_text.find('{')
                if start_idx == -1:
                    logger.warning("[DirectMode] No JSON found in response")
                    history.append(f"Output error: {response_text[:100]}")
                    continue

                # Find matching closing brace
                brace_count = 0
                in_string = False
                escape_next = False
                for i, char in enumerate(response_text[start_idx:], start_idx):
                    if escape_next:
                        escape_next = False
                        continue
                    if char == '\\' and in_string:
                        escape_next = True
                        continue
                    if char == '"' and not escape_next:
                        in_string = not in_string
                        continue
                    if in_string:
                        continue
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_str = response_text[start_idx:i+1]
                            try:
                                action_data = json.loads(json_str)
                                break
                            except json.JSONDecodeError:
                                # Continue searching for next potential JSON
                                continue

                if action_data is None:
                    logger.warning("[DirectMode] Could not parse JSON from response")
                    history.append(f"Parse error: {response_text[:100]}")
                    continue
                action_type = action_data.get("action")
                
                logger.info(f"🤖 Action: {action_type} params={json.dumps(action_data)}")
                
                if action_type == "done":
                     return action_data.get("result", "Task completed via Direct Mode")
                     
                # 5. Execute Action with RESILIENCE (v2.10)
                # Use _execute_mcp_call for retry, self-healing, and challenge resolution

                tool_name = action_type
                params = {k:v for k,v in action_data.items() if k != "action"}

                # Special mapping if needed (e.g. "click" -> "browser_click")
                if action_type == "click": tool_name = "browser_click"
                if action_type == "type": tool_name = "browser_type"
                if action_type == "scroll": tool_name = "browser_scroll"
                if action_type == "navigate": tool_name = "playwright_navigate"

                # Use resilient MCP call with retry and self-healing
                result = await self._execute_mcp_call(tool_name, params)

                # Record history
                result_status = result.get('success', 'ok') if isinstance(result, dict) else 'ok'
                history.append(f"Action: {tool_name} -> {result_status}")
                
            except Exception as e:
                logger.error(f"[DirectMode] loop error: {e}")
                history.append(f"Error: {str(e)}")

        return "Task ended (max steps reached)"

    async def _generate_llm_response(self, messages):
        """Helper to call LLM - adapts to available model interface"""
        import asyncio

        # Attempt 1: self.ollama_client (standard in Brain - used by reasoning_engine)
        if hasattr(self, 'ollama_client') and self.ollama_client:
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.ollama_client.chat,
                        model=getattr(self, 'model', '0000/ui-tars-1.5-7b:latest'),
                        messages=messages,
                        options={'temperature': getattr(self, 'temperature', 0.1)}
                    ),
                    timeout=getattr(self, 'llm_timeout', 60)
                )
                msg = response.get('message', {})
                if hasattr(msg, 'model_dump'):
                    msg = msg.model_dump()
                elif not isinstance(msg, dict):
                    msg = dict(msg)
                return msg.get('content', '')
            except Exception as e:
                logger.error(f"[DirectMode] ollama_client call failed: {e}")
                raise

        # Attempt 2: self.gpu_llm_client (remote GPU server)
        if hasattr(self, 'gpu_llm_client') and self.gpu_llm_client:
            try:
                response = await self.gpu_llm_client.chat(messages)
                return response.get('content', '') if isinstance(response, dict) else str(response)
            except Exception as e:
                logger.error(f"[DirectMode] gpu_llm_client call failed: {e}")
                raise

        raise AttributeError("No LLM client found (need ollama_client or gpu_llm_client)")

    async def run(self, prompt: str) -> str:
        """Main entry with streaming output."""
        
        # DIRECT MODE CHECK
        # If direct_mode is enabled (default True for now), bypass routing
        direct_mode = getattr(self, 'direct_mode', True) 
        if direct_mode:
             # Check for legacy/specialized workflows that should BYPASS direct mode
             # (User requested to keep Reddit/FB Ads workflows active)
             bypass_direct = False
             if INTELLIGENT_ROUTING_AVAILABLE:
                 try:
                     decision = route_task(prompt)
                     # If router says DETERMINISTIC (FB Ads, LinkedIn etc) or SPECIALIZED_EXTRACTOR,
                     # we should let the legacy routing handle it (which has specialized tools for these)
                     if decision.path in (ExecutionPath.DETERMINISTIC, ExecutionPath.SPECIALIZED_EXTRACTOR):
                         logger.info(f"[ORCHESTRATION] Specialized workflow detected ({decision.workflow_name}) - bypassing Direct Mode")
                         bypass_direct = True
                 except Exception as e:
                     logger.warning(f"Routing check failed: {e}")

             if not bypass_direct:
                 logger.info("[ORCHESTRATION] Using Direct Mode")
                 try:
                     return await self._run_direct_mode(prompt)
                 except Exception as e:
                     logger.error(f"Direct Mode failed: {e}. Falling back to standard orchestration.")
                     # Fallthrough to standard run if direct mode crashes
        
        start = time.time()
        if self.crash_recovery:
            self.crash_recovery.mark_running(prompt)
        complete_success = False

        # Start steering input listener for real-time user interaction
        if self._steering_enabled:
            self._steering.start()
            self._steering.show_steering_hint(console)

        # Security guardrail check - block black hat/malicious requests
        if check_security:
            security_check = check_security(prompt)
            if not security_check.allowed:
                logger.warning(f"Security guardrail blocked request: {security_check.category}")
                console.print(get_refusal_message(security_check))
                return get_refusal_message(security_check)

        # AGI-like reasoning: Deeply understand user intent before execution
        agi_reasoning = None
        if AGI_REASONING_AVAILABLE and get_agi_reasoning:
            try:
                agi_reasoning = get_agi_reasoning()
                # Initialize with LLM client if available
                if hasattr(self, 'llm_client') and self.llm_client:
                    await agi_reasoning.set_llm_client(self.llm_client)
                # Understand true intent (async call to LLM)
                intent = await agi_reasoning.understand_intent(prompt, {
                    'url': getattr(self, 'current_url', ''),
                    'history_length': len(getattr(self, 'history', [])),
                })
                if intent and intent.get('actual_goal'):
                    logger.info(f"[AGI] True intent: {intent.get('actual_goal')}")
                    # Think ahead - what steps will be needed?
                    anticipated = await agi_reasoning.think_ahead({
                        'goal': intent.get('actual_goal'),
                        'page': getattr(self, 'current_url', 'no page')
                    })
                    if anticipated:
                        logger.debug(f"[AGI] Anticipated steps: {anticipated}")
            except Exception as e:
                logger.debug(f"AGI reasoning init failed (non-critical): {e}")

        # HTN PLANNING: Check for complex multi-step tasks requiring hierarchical planning
        # Complex tasks like multi-platform workflows, multiple URLs, complex coordination
        # benefit from upfront planning with dependency management and fallbacks
        # SKIP HTN for multi-goal prompts - goal sequencer handles those better
        _is_multi_goal = is_multi_goal(prompt) if GOAL_SEQUENCER_AVAILABLE else False
        if HTN_PLANNING_AVAILABLE and is_complex_task(prompt, self.config) and not _is_multi_goal:
            try:
                complexity = get_complexity_score(prompt)
                logger.info(f"[HTN PLANNING] Complex task detected (score: {complexity:.2f})")
                # Silent - planning internally

                # Create action handler that executes via MCP
                async def action_handler(action: str, arguments: dict):
                    """Execute a planned action via MCP tools with smart argument translation."""
                    try:
                        # Get task description for argument translation
                        task_desc = arguments.get('task', '')
                        task_lower = task_desc.lower()

                        # Map planning actions to MCP tool calls
                        tool_mapping = {
                            'navigate': 'playwright_navigate',
                            'search': 'playwright_fill',
                            'extract': 'playwright_extract_entities',
                            'click': 'playwright_click',
                            'save_results': 'playwright_save_csv',
                            'screenshot_fallback': 'playwright_screenshot',
                            'execute_task': 'playwright_navigate',
                            'verify': 'playwright_snapshot',  # Verify by taking snapshot
                        }

                        tool_name = tool_mapping.get(action, action)

                        # Translate arguments based on action type
                        translated_args = dict(arguments)

                        if action == 'navigate' or action == 'execute_task':
                            # Extract URL from task description
                            # Look for explicit URLs
                            url_match = re.search(r'https?://[^\s]+', task_desc)
                            if url_match:
                                translated_args = {'url': url_match.group(0)}
                            else:
                                # Map common site names to URLs
                                site_mapping = {
                                    'fb ads library': 'https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&media_type=all',
                                    'facebook ads library': 'https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&media_type=all',
                                    'reddit': 'https://www.reddit.com',
                                    'linkedin': 'https://www.linkedin.com',
                                    'google maps': 'https://www.google.com/maps',
                                    'gmail': 'https://mail.google.com',
                                    'zoho mail': 'https://mail.zoho.com',
                                    'google': 'https://www.google.com',
                                }
                                for site_name, url in site_mapping.items():
                                    if site_name in task_lower:
                                        translated_args = {'url': url}
                                        break
                                else:
                                    # Can't determine URL - return failure
                                    return {'success': False, 'error': f'Cannot determine URL from task: {task_desc[:50]}'}

                        elif action == 'search':
                            # Extract search query from task
                            query_patterns = [
                                r'search\s+(?:for\s+)?["\']([^"\']+)["\']',
                                r'search\s+(?:for\s+)?(\S+)',
                            ]
                            for pattern in query_patterns:
                                match = re.search(pattern, task_desc, re.I)
                                if match:
                                    translated_args = {'text': match.group(1), 'selector': 'input[type="search"], input[name="q"], input.search'}
                                    break
                            else:
                                # Default to snapshot for verification instead
                                tool_name = 'playwright_snapshot'
                                translated_args = {}

                        elif action == 'extract':
                            # Use entity extraction
                            translated_args = {}

                        elif action == 'verify':
                            # Take snapshot to verify
                            tool_name = 'playwright_snapshot'
                            translated_args = {}

                        elif action == 'save_results':
                            # Use CSV save
                            translated_args = {'filename': 'results.csv'}

                        # Execute via MCP
                        if hasattr(self, 'mcp') and self.mcp:
                            logger.debug(f"[HTN] Executing {tool_name} with args: {translated_args}")
                            result = await self.mcp.call_tool(tool_name, translated_args)
                            return {'success': True, 'result': result}
                        else:
                            logger.warning(f"No MCP client available for action: {action}")
                            return {'success': False, 'error': 'No MCP client available'}

                    except Exception as e:
                        logger.error(f"Action handler failed for {action}: {e}")
                        return {'success': False, 'error': str(e)}

                # Execute via HTN planning
                result = await quick_plan_and_execute(prompt, action_handler)

                if result.get('success'):
                    plan = result.get('plan')
                    execution = result.get('execution', {})
                    completed = execution.get('completed_steps', 0)
                    total = execution.get('total_steps', 0)

                    # Only return if ALL steps completed - otherwise fall through to goal sequencer
                    if completed >= total and total > 0:
                        # Format output
                        output_lines = [
                            f"Completed {completed} tasks",
                            f"Duration: {execution.get('duration', 0):.1f}s"
                        ]

                        if execution.get('failed_steps'):
                            output_lines.append(f"Failed: {len(execution['failed_steps'])}")

                        output = '\n'.join(output_lines)

                        # Apply user format if specified
                        try:
                            from .output_format_handler import format_output
                            output = format_output(prompt, output)
                        except Exception as e:
                            logger.debug(f"Output format handler failed: {e}")

                        return output
                    else:
                        # HTN didn't fully execute - fall through to goal sequencer
                        logger.warning(f"[HTN] Only {completed}/{total} steps in {execution.get('duration', 0):.1f}s - falling through to goal sequencer")
                        # Fall through to standard execution
                else:
                    error_msg = result.get('error', 'Planning validation failed')
                    logger.warning(f"[HTN] {error_msg} - falling through")
                    # Silent fall through to goal sequencer
                    # Fall through to standard execution

            except Exception as e:
                logger.error(f"HTN planning execution failed: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                # Silent fall through to goal sequencer

        # GOAL SEQUENCER: Check for multi-goal prompts - route to sequence handler
        # Multi-goal prompts like "do X then Y then Z" need special handling
        logger.debug(f"GOAL_SEQUENCER_AVAILABLE={GOAL_SEQUENCER_AVAILABLE}, is_multi_goal={_is_multi_goal}")
        if GOAL_SEQUENCER_AVAILABLE and _is_multi_goal:
            try:
                logger.info("[DEBUG] Calling _run_goal_sequence...")
                sequence_result = await self._run_goal_sequence(prompt)

                # Apply user format if specified
                try:
                    from .output_format_handler import format_output
                    sequence_result = format_output(prompt, sequence_result)
                except Exception as e:
                    logger.debug(f"Output format handler failed: {e}")

                return sequence_result
            except Exception as e:
                logger.error(f"Goal sequence execution failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Silent fall through
                # Fall through to standard execution

        # ACTION TEMPLATES: Fast-path for single-goal template matches
        # Templates provide multi-step deterministic execution like Playwright MCP
        if TEMPLATES_AVAILABLE:
            try:
                template = find_template(prompt)
                if template:
                    # Note: Template name is internal - don't expose to users
                    result = await execute_template(template, prompt, self.mcp)
                    if result.get("success"):
                        # Get URL for output (always include it)
                        final_url = result.get("url") or result.get("source_url") or ""

                        # If template produced a multi-item formatted output (URLs-only / many leads), prefer it.
                        formatted = result.get("formatted_output")
                        if formatted:
                            return formatted

                        # MANDATORY: Use extraction_summary if available (shows actual prospects)
                        if result.get("extraction_summary"):
                            output = result["extraction_summary"]
                            if final_url and final_url not in output:
                                output += f"\nFinal URL: {final_url}"

                            # Apply user format if specified
                            try:
                                from .output_format_handler import format_output
                                output = format_output(prompt, output)
                            except Exception as e:
                                logger.debug(f"Output format handler failed: {e}")

                            return output

                        # Fallback: show template info with URL
                        output = f"Template '{template.name}' completed"
                        if final_url:
                            output += f"\nFinal URL: {final_url}"

                        # Include any extracted data count
                        extraction_count = result.get("extraction_count", 0)
                        if extraction_count > 0:
                            output += f"\nExtracted: {extraction_count} item(s)"

                        # Apply user format if specified
                        try:
                            from .output_format_handler import format_output
                            output = format_output(prompt, output)
                        except Exception as e:
                            logger.debug(f"Output format handler failed: {e}")

                        return output
                    else:
                        logger.debug(f"Template execution had failures: {result}")
            except Exception as e:
                logger.debug(f"Template execution failed: {e}, trying other methods")

        # DIRECT PATTERNS: Fast-path for single-goal known patterns (Gmail, Maps, etc.)
        # Only runs for single-goal prompts (multi-goal handled above)
        try:
            if hasattr(self, '_try_direct_patterns'):
                direct_result = await self._try_direct_patterns(prompt)
                if direct_result:
                    # Apply user format if specified
                    try:
                        from .output_format_handler import format_output
                        direct_result = format_output(prompt, direct_result)
                    except Exception as e:
                        logger.debug(f"Output format handler failed: {e}")
                    return direct_result
        except Exception as e:
            logger.debug(f"Direct patterns check failed: {e}")

        # Check if user wants visible browser
        self.mcp.detect_headless_from_prompt(prompt)
        # Check if user wants speed/FAST_TRACK mode (applied safely per-URL)
        try:
            self.mcp.detect_speed_mode_from_prompt(prompt)
        except Exception:
            pass
        self._set_describe_mode(prompt)
        self._describe_retry_done = False  # reset per task
        self.awareness.update_from_prompt(prompt)
        tone = self.awareness.detect_social_cues(prompt)
        if tone == "urgent":
            logger.info("Prompt tone marked as urgent; stay on task.")
        self.survival.register_prompt(prompt)
        self._prompt_count += 1
        if self._prompt_count % self._review_interval == 0:
            self._maybe_run_improvement_review()

        try:
            # Auto preflight
            preflight_ok, preflight_msg = await self._preflight_checks()
            if not preflight_ok:
                logger.error(f"Preflight failed: {preflight_msg}")
                complete_success = True
                return f"Preflight failed: {preflight_msg} | Details: {'; '.join(self._preflight_details)}"

            # Start consolidation on first run
            if self._consolidation_task is None and self.memory_arch:
                await self._start_memory_consolidation()

            # CRITICAL: Detect and set forever mode BEFORE any execution starts
            # This ensures timeout is disabled for all loop/monitor/scheduled tasks
            self._detect_and_set_forever_mode(prompt)

            # Parse duration/loops/schedule
            # Check for scheduled tasks (recurring or one-time)
            schedule = self._parse_schedule(prompt)
            if schedule:
                clean = self._clean_prompt(prompt)
                complete_success = True
                if schedule.get('one_time'):
                    return await self._one_time_scheduled(clean, schedule)
                return await self._scheduled_loop(clean, schedule)

            # Check for indefinite/forever mode
            if self._parse_indefinite(prompt):
                clean = self._clean_prompt(prompt)
                complete_success = True
                return await self._infinite_loop(clean)

            # Check for timed duration (e.g., "for 2 hours")
            duration = self._parse_duration(prompt)
            if duration:
                clean = self._clean_prompt(prompt)
                complete_success = True
                return await self._timed_loop(clean, duration)

            # Check for counted loops (e.g., "5 times")
            loops = self._parse_loops(prompt)
            if loops:
                clean = self._clean_prompt(prompt)
                complete_success = True
                return await self._counted_loop(clean, loops)

            result = await self._execute_with_streaming(prompt)
            elapsed = time.time() - start

            # Apply user-specified output format if present
            try:
                from .output_format_handler import format_output
                result = format_output(prompt, result)
            except Exception as e:
                logger.debug(f"Output format handler failed: {e}")
                # Continue with original result

            # Premium completion display
            if elapsed < 30:
                speed_icon = "⚡"
                speed_msg = "Lightning fast!"
                color = "#10B981"  # green
            elif elapsed < 60:
                speed_icon = "✨"
                speed_msg = "Quick work!"
                color = "#00D4AA"  # teal
            else:
                speed_icon = "📊"
                speed_msg = "Thorough analysis"
                color = "#F59E0B"  # amber

            console.print(f"\n[{color}]{speed_icon}[/{color}] [bold]Completed in {elapsed:.1f}s[/bold] [dim]• {speed_msg}[/dim]")

            # Save memory + context
            self.memory.save()
            self.context_memory.add_entry(f"Prompt: {prompt} -> Result: {result[:200]}")

            # Save episode to memory architecture
            if self.memory_arch:
                try:
                    duration = time.time() - start
                    success = complete_success
                    self.memory_arch.save_episode(
                        task_prompt=prompt,
                        outcome=result[:200] if result else "Completed",
                        success=success,
                        duration_seconds=duration,
                        tags=['agent_task']
                    )
                except Exception as e:
                    logger.debug(f"Episode save failed: {e}")

            complete_success = True
            return result

        except ResourceLimitError as e:
            # Task killed by resource limiter
            logger.error(f"Task killed by resource limiter: {e}")
            console.print(f"[red]⚠ Task stopped due to resource limits: {e}[/red]")
            complete_success = False
            return f"Task stopped due to resource limits: {e}"

        finally:
            # Stop steering input listener
            if self._steering_enabled:
                self._steering.stop()

            if self.crash_recovery:
                self.crash_recovery.mark_complete(complete_success)
            if complete_success and self.dead_mans_switch:
                self.dead_mans_switch.ping()  # Signal we're alive

    async def _try_direct_patterns(self, prompt: str) -> Optional[str]:
        """
        Try to handle prompt via deterministic workflows first.

        This is the intelligent routing layer that avoids LLM calls for known patterns:
        1. Check if prompt matches a deterministic workflow
        2. If yes -> execute workflow directly (no LLM planning)
        3. If no -> return None to fall through to LLM-based execution

        Returns:
            Result string if handled, None if should fall through to LLM
        """
        if not INTELLIGENT_ROUTING_AVAILABLE:
            return None

        try:
            # Route the task
            decision = route_task(prompt)

            logger.info(f"Task routing: {decision.path.value} (confidence: {decision.confidence:.2f})")
            logger.debug(f"Routing reasoning: {decision.reasoning}")

            # Handle deterministic workflows
            if decision.path == ExecutionPath.DETERMINISTIC:
                # Get current URL for URL-based workflow auto-selection
                current_url = None
                try:
                    if hasattr(self.mcp, 'client') and hasattr(self.mcp.client, 'page') and self.mcp.client.page:
                        current_url = self.mcp.client.page.url
                except Exception:
                    pass  # Ignore errors getting URL

                workflow = match_workflow(prompt, current_url=current_url)
                if workflow:
                    params = extract_params(prompt, workflow)
                    logger.info(f"Executing deterministic workflow: {workflow.name}")
                    console.print(f"[cyan]Using optimized workflow: {workflow.name}[/cyan]")

                    try:
                        result = await execute_workflow(workflow, params, self.mcp)
                        if result.get("success"):
                            return f"Workflow '{workflow.name}' completed successfully. {result.get('summary', '')}"
                        else:
                            logger.warning(f"Workflow failed: {result.get('error')}")
                            # Fall through to LLM execution
                            return None
                    except Exception as e:
                        logger.error(f"Workflow execution error: {e}")
                        return None

            # Handle specialized extractors
            elif decision.path == ExecutionPath.SPECIALIZED_EXTRACTOR:
                extractor_name = decision.workflow_name
                params = decision.params

                logger.info(f"Using specialized extractor: {extractor_name}")
                console.print(f"[cyan]Using specialized extractor: {extractor_name}[/cyan]")

                # Route to appropriate extractor
                if extractor_name == "fb_ads_extractor":
                    result = await self.mcp.client.extract_fb_ads_batch(
                        max_ads=params.get("max_ads", 50)
                    )
                elif extractor_name == "reddit_extractor":
                    result = await self.mcp.client.extract_reddit_posts_batch(
                        subreddit=params.get("subreddit"),
                        max_posts=params.get("max_posts", 50)
                    )
                elif extractor_name == "linkedin_extractor":
                    query = params.get("search_query", "")
                    result = await self.mcp.client.linkedin_company_lookup(
                        company=query,
                        max_results=3
                    )
                else:
                    return None

                if result and result.get("success"):
                    return self._format_extractor_result(extractor_name, result)
                else:
                    logger.warning(f"Extractor failed: {result.get('error', 'Unknown error')}")
                    return None

            # Handle simple execution (single actions like navigation, click, etc.)
            elif decision.path == ExecutionPath.SIMPLE_EXECUTION:
                params = decision.params

                # Check if it's a navigation command
                if "url" in params:
                    url = params.get("url", "")

                    # If no URL provided, try to extract service/site name and construct URL
                    if not url:
                        # Extract service name from prompt (e.g., "Go to Zoho Mail" -> "Zoho Mail")
                        import re
                        nav_match = re.search(r"(?:go\s+to|navigate\s+to|open|visit)\s+(.+)", prompt.lower())
                        if nav_match:
                            service = nav_match.group(1).strip()

                            # Common service name to URL mappings
                            service_urls = {
                                "zoho mail": "https://mail.zoho.com",
                                "zoho": "https://mail.zoho.com",
                                "gmail": "https://mail.google.com",
                                "outlook": "https://outlook.live.com",
                                "yahoo mail": "https://mail.yahoo.com",
                                "linkedin": "https://linkedin.com",
                                "facebook": "https://facebook.com",
                                "twitter": "https://twitter.com",
                                "x": "https://x.com",
                                "instagram": "https://instagram.com",
                                "reddit": "https://reddit.com",
                                "youtube": "https://youtube.com",
                                "google": "https://google.com",
                            }

                            # Check for exact match
                            if service in service_urls:
                                url = service_urls[service]
                            # Check for partial match (e.g., "mail.zoho.com" -> add https://)
                            elif "." in service and not service.startswith("http"):
                                url = f"https://{service}"
                            else:
                                # Can't determine URL - let LLM handle it
                                logger.debug(f"Can't determine URL for service: {service}")
                                return None

                    if url:
                        logger.info(f"Simple navigation to: {url}")
                        console.print(f"[cyan]Navigating to: {url}[/cyan]")

                        try:
                            result = await self.mcp.client.navigate(url)
                            if result.get("success"):
                                return f"Successfully navigated to {url}"
                            else:
                                logger.warning(f"Navigation failed: {result.get('error')}")
                                return None
                        except Exception as e:
                            logger.error(f"Navigation error: {e}")
                            return None

                # For other simple actions (clicks, types, etc.), fall through to LLM
                # The LLM can handle these single-action commands
                logger.debug("Simple execution without navigation - falling through to LLM")
                return None

            # LOCAL_LLM and KIMI_K2 paths fall through to normal execution
            return None

        except Exception as e:
            logger.error(f"Direct patterns check failed: {e}")
            return None

    def _format_extractor_result(self, extractor_name: str, result: Dict[str, Any]) -> str:
        """Format extractor results for user display."""
        if extractor_name == "fb_ads_extractor":
            ads_count = result.get("ads_count", 0)
            return f"Extracted {ads_count} Facebook ads successfully."

        elif extractor_name == "reddit_extractor":
            posts_count = result.get("posts_count", 0)
            warm_count = result.get("warm_lead_count", 0)
            return f"Extracted {posts_count} Reddit posts ({warm_count} warm leads)."

        elif extractor_name == "linkedin_extractor":
            results_count = result.get("results_count", 0)
            return f"Found {results_count} LinkedIn company profiles."

        return "Extraction completed successfully."

    async def _try_mcp_simple(self, prompt: str) -> Optional[str]:
        """
        Super-simple Playwright MCP-like execution for known sites.

        This is the "just make it work" approach that bypasses all complex systems:
        1. Match simple site patterns
        2. Navigate to URL with search query
        3. Wait for content to load
        4. Take accessibility snapshot
        5. Extract relevant info from snapshot text

        Returns result string if handled, None to fall through to other methods.
        """
        import re
        import json
        from urllib.parse import quote_plus

        # CRITICAL: Unwrap JSON-wrapped prompts first
        # Some code paths wrap prompts as: {"type":"task","prompt":"actual prompt"}
        try:
            parsed = json.loads(prompt)
            if isinstance(parsed, dict) and 'prompt' in parsed:
                prompt = parsed['prompt']
                logger.debug(f"[MCP-SIMPLE] Unwrapped JSON prompt: {prompt[:60]}...")
        except (json.JSONDecodeError, TypeError):
            pass  # Not JSON, use as-is

        prompt_lower = prompt.lower()

        # Site patterns with URL builders
        # IMPORTANT: Order matters! More specific triggers must come first.
        # LinkedIn before Reddit (so "linkedin" doesn't accidentally match "reddit" first)
        # "zoho mail" before "zoho", "google maps" before "maps", etc.
        # =================================================================
        # SITE CONFIGS - Support for all major browser-based job tasks
        # =================================================================
        # Categories: Sales, Recruiting, Marketing, E-commerce, Real Estate,
        #             Research, Support, Finance, Social Media, General
        # =================================================================
        site_configs = {
            # --- SALES & MARKETING ---
            'fb_ads': {
                'triggers': ['fb ads', 'facebook ads', 'meta ads', 'ads library'],
                'url_builder': lambda q: f'https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&media_type=all&q={quote_plus(q)}&search_type=keyword_unordered' if q else 'https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&media_type=all',
                'wait_time': 2,
                'extractor': self._extract_fb_ads_simple,
                'category': 'sales',
            },
            'linkedin': {
                'triggers': ['linkedin'],
                'url_builder': lambda q: f'https://www.linkedin.com/search/results/all/?keywords={quote_plus(q)}' if q else 'https://www.linkedin.com',
                'wait_time': 1.5,
                'extractor': self._extract_linkedin_simple,
                'category': 'sales',
            },
            'hubspot': {
                'triggers': ['hubspot', 'hubspot crm'],
                'url_builder': lambda q: 'https://app.hubspot.com/contacts',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'sales',
            },
            'salesforce': {
                'triggers': ['salesforce', 'sfdc'],
                'url_builder': lambda q: 'https://login.salesforce.com',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'sales',
            },

            # --- RECRUITING & HR ---
            'indeed': {
                'triggers': ['indeed', 'indeed.com', 'job search indeed'],
                'url_builder': lambda q: f'https://www.indeed.com/jobs?q={quote_plus(q)}' if q else 'https://www.indeed.com',
                'wait_time': 1.5,
                'extractor': self._extract_job_listings,
                'category': 'recruiting',
            },
            'glassdoor': {
                'triggers': ['glassdoor', 'company reviews'],
                'url_builder': lambda q: f'https://www.glassdoor.com/Search/results.htm?keyword={quote_plus(q)}' if q else 'https://www.glassdoor.com',
                'wait_time': 1.5,
                'extractor': self._extract_job_listings,
                'category': 'recruiting',
            },
            'ziprecruiter': {
                'triggers': ['ziprecruiter', 'zip recruiter'],
                'url_builder': lambda q: f'https://www.ziprecruiter.com/jobs-search?search={quote_plus(q)}' if q else 'https://www.ziprecruiter.com',
                'wait_time': 1.5,
                'extractor': self._extract_job_listings,
                'category': 'recruiting',
            },

            # --- SOCIAL MEDIA ---
            'twitter': {
                'triggers': ['twitter', 'x.com', 'tweet'],
                'url_builder': lambda q: f'https://twitter.com/search?q={quote_plus(q)}' if q else 'https://twitter.com',
                'wait_time': 1.5,
                'extractor': self._extract_social_posts,
                'category': 'social',
            },
            'instagram': {
                'triggers': ['instagram', 'ig', 'insta'],
                'url_builder': lambda q: f'https://www.instagram.com/explore/tags/{quote_plus(q.replace(" ", ""))}/' if q else 'https://www.instagram.com',
                'wait_time': 1.5,
                'extractor': self._extract_social_posts,
                'category': 'social',
            },
            'youtube': {
                'triggers': ['youtube', 'yt', 'video search'],
                'url_builder': lambda q: f'https://www.youtube.com/results?search_query={quote_plus(q)}' if q else 'https://www.youtube.com',
                'wait_time': 1.5,
                'extractor': self._extract_youtube_results,
                'category': 'social',
            },
            'tiktok': {
                'triggers': ['tiktok', 'tik tok'],
                'url_builder': lambda q: f'https://www.tiktok.com/search?q={quote_plus(q)}' if q else 'https://www.tiktok.com',
                'wait_time': 1.5,
                'extractor': self._extract_social_posts,
                'category': 'social',
            },

            # --- E-COMMERCE ---
            'amazon': {
                'triggers': ['amazon', 'amazon.com', 'product search amazon'],
                'url_builder': lambda q: f'https://www.amazon.com/s?k={quote_plus(q)}' if q else 'https://www.amazon.com',
                'wait_time': 1.5,
                'extractor': self._extract_ecommerce_products,
                'category': 'ecommerce',
            },
            'ebay': {
                'triggers': ['ebay', 'ebay.com'],
                'url_builder': lambda q: f'https://www.ebay.com/sch/i.html?_nkw={quote_plus(q)}' if q else 'https://www.ebay.com',
                'wait_time': 1.5,
                'extractor': self._extract_ecommerce_products,
                'category': 'ecommerce',
            },
            'etsy': {
                'triggers': ['etsy', 'etsy.com'],
                'url_builder': lambda q: f'https://www.etsy.com/search?q={quote_plus(q)}' if q else 'https://www.etsy.com',
                'wait_time': 1.5,
                'extractor': self._extract_ecommerce_products,
                'category': 'ecommerce',
            },
            'shopify': {
                'triggers': ['shopify', 'shopify admin'],
                'url_builder': lambda q: 'https://admin.shopify.com',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'ecommerce',
            },

            # --- REAL ESTATE ---
            'zillow': {
                'triggers': ['zillow', 'zillow.com', 'home search', 'property search'],
                'url_builder': lambda q: f'https://www.zillow.com/homes/{quote_plus(q)}_rb/' if q else 'https://www.zillow.com',
                'wait_time': 1.5,
                'extractor': self._extract_real_estate_listings,
                'category': 'realestate',
            },
            'realtor': {
                'triggers': ['realtor', 'realtor.com'],
                'url_builder': lambda q: f'https://www.realtor.com/realestateandhomes-search/{quote_plus(q.replace(" ", "-"))}' if q else 'https://www.realtor.com',
                'wait_time': 1.5,
                'extractor': self._extract_real_estate_listings,
                'category': 'realestate',
            },
            'redfin': {
                'triggers': ['redfin', 'redfin.com'],
                'url_builder': lambda q: f'https://www.redfin.com/city/0/CA/{quote_plus(q)}' if q else 'https://www.redfin.com',
                'wait_time': 1.5,
                'extractor': self._extract_real_estate_listings,
                'category': 'realestate',
            },

            # --- LOCAL BUSINESS ---
            'google_maps': {
                'triggers': ['google maps', 'maps'],
                'url_builder': lambda q: f'https://www.google.com/maps/search/{quote_plus(q)}' if q else 'https://www.google.com/maps',
                'wait_time': 1.5,
                'extractor': self._extract_maps_simple,
                'category': 'local',
            },
            'yelp': {
                'triggers': ['yelp', 'yelp.com', 'restaurant search', 'business reviews'],
                'url_builder': lambda q: f'https://www.yelp.com/search?find_desc={quote_plus(q)}' if q else 'https://www.yelp.com',
                'wait_time': 1.5,
                'extractor': self._extract_local_business,
                'category': 'local',
            },
            'tripadvisor': {
                'triggers': ['tripadvisor', 'trip advisor'],
                'url_builder': lambda q: f'https://www.tripadvisor.com/Search?q={quote_plus(q)}' if q else 'https://www.tripadvisor.com',
                'wait_time': 1.5,
                'extractor': self._extract_local_business,
                'category': 'local',
            },

            # --- RESEARCH & GENERAL ---
            'google_search': {
                'triggers': ['google search', 'search google', 'google for'],
                'url_builder': lambda q: f'https://www.google.com/search?q={quote_plus(q)}' if q else 'https://www.google.com',
                'wait_time': 2,
                'extractor': self._extract_search_results,
                'category': 'research',
            },
            'wikipedia': {
                'triggers': ['wikipedia', 'wiki'],
                'url_builder': lambda q: f'https://en.wikipedia.org/wiki/Special:Search?search={quote_plus(q)}' if q else 'https://en.wikipedia.org',
                'wait_time': 2,
                'extractor': self._extract_article_content,
                'category': 'research',
            },
            'scholar': {
                'triggers': ['google scholar', 'scholar', 'academic search'],
                'url_builder': lambda q: f'https://scholar.google.com/scholar?q={quote_plus(q)}' if q else 'https://scholar.google.com',
                'wait_time': 2,
                'extractor': self._extract_search_results,
                'category': 'research',
            },

            # --- COMMUNITY & FORUMS ---
            'reddit': {
                'triggers': ['reddit', 'subreddit', 'r/'],
                'url_builder': lambda q: f'https://www.reddit.com/search/?q={quote_plus(q)}' if q else 'https://www.reddit.com',
                'wait_time': 1.5,
                'extractor': self._extract_reddit_simple,
                'category': 'community',
            },
            'quora': {
                'triggers': ['quora', 'quora.com'],
                'url_builder': lambda q: f'https://www.quora.com/search?q={quote_plus(q)}' if q else 'https://www.quora.com',
                'wait_time': 1.5,
                'extractor': self._extract_qa_content,
                'category': 'community',
            },
            'hackernews': {
                'triggers': ['hacker news', 'hackernews', 'hn', 'ycombinator'],
                'url_builder': lambda q: f'https://hn.algolia.com/?q={quote_plus(q)}' if q else 'https://news.ycombinator.com',
                'wait_time': 2,
                'extractor': self._extract_news_items,
                'category': 'community',
            },
            'producthunt': {
                'triggers': ['product hunt', 'producthunt'],
                'url_builder': lambda q: f'https://www.producthunt.com/search?q={quote_plus(q)}' if q else 'https://www.producthunt.com',
                'wait_time': 1.5,
                'extractor': self._extract_product_listings,
                'category': 'community',
            },

            # --- PROJECT MANAGEMENT ---
            'trello': {
                'triggers': ['trello', 'trello board'],
                'url_builder': lambda q: 'https://trello.com',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'productivity',
            },
            'asana': {
                'triggers': ['asana', 'asana tasks'],
                'url_builder': lambda q: 'https://app.asana.com',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'productivity',
            },
            'notion': {
                'triggers': ['notion', 'notion.so'],
                'url_builder': lambda q: 'https://www.notion.so',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'productivity',
            },

            # --- EMAIL ---
            'gmail': {
                'triggers': ['gmail', 'google mail'],
                'url_builder': lambda q: 'https://mail.google.com/mail/u/0/#inbox',
                'wait_time': 1.5,
                'extractor': self._extract_gmail_simple,
                'category': 'email',
            },
            'zoho_mail': {
                'triggers': ['zoho mail', 'zoho'],
                'url_builder': lambda q: 'https://mail.zoho.com/zm/#mail/folder/inbox',
                'wait_time': 1.5,
                'extractor': self._extract_zoho_simple,
                'category': 'email',
            },
            'outlook': {
                'triggers': ['outlook', 'outlook.com', 'hotmail'],
                'url_builder': lambda q: 'https://outlook.live.com/mail/0/inbox',
                'wait_time': 1.5,
                'extractor': self._extract_email_inbox,
                'category': 'email',
            },

            # --- NEWS & MEDIA ---
            'news': {
                'triggers': ['news search', 'google news'],
                'url_builder': lambda q: f'https://news.google.com/search?q={quote_plus(q)}' if q else 'https://news.google.com',
                'wait_time': 2,
                'extractor': self._extract_news_items,
                'category': 'news',
            },
            'craigslist': {
                'triggers': ['craigslist', 'craigslist.org'],
                'url_builder': lambda q: f'https://www.craigslist.org/search?query={quote_plus(q)}' if q else 'https://www.craigslist.org',
                'wait_time': 1.5,
                'extractor': self._extract_classifieds,
                'category': 'classifieds',
            },

            # --- TRAVEL & HOSPITALITY ---
            'booking': {
                'triggers': ['booking.com', 'booking', 'hotel booking'],
                'url_builder': lambda q: f'https://www.booking.com/searchresults.html?ss={quote_plus(q)}' if q else 'https://www.booking.com',
                'wait_time': 4,
                'extractor': self._extract_travel_listings,
                'category': 'travel',
            },
            'airbnb': {
                'triggers': ['airbnb', 'airbnb.com', 'vacation rental'],
                'url_builder': lambda q: f'https://www.airbnb.com/s/{quote_plus(q)}/homes' if q else 'https://www.airbnb.com',
                'wait_time': 4,
                'extractor': self._extract_travel_listings,
                'category': 'travel',
            },
            'expedia': {
                'triggers': ['expedia', 'expedia.com', 'flight search'],
                'url_builder': lambda q: f'https://www.expedia.com/Hotel-Search?destination={quote_plus(q)}' if q else 'https://www.expedia.com',
                'wait_time': 4,
                'extractor': self._extract_travel_listings,
                'category': 'travel',
            },
            'kayak': {
                'triggers': ['kayak', 'kayak.com', 'flight compare'],
                'url_builder': lambda q: f'https://www.kayak.com/explore/{quote_plus(q)}' if q else 'https://www.kayak.com',
                'wait_time': 4,
                'extractor': self._extract_travel_listings,
                'category': 'travel',
            },

            # --- FINANCE & BANKING ---
            'coinbase': {
                'triggers': ['coinbase', 'crypto exchange', 'buy crypto'],
                'url_builder': lambda q: 'https://www.coinbase.com/price',
                'wait_time': 1.5,
                'extractor': self._extract_finance_data,
                'category': 'finance',
            },
            'robinhood': {
                'triggers': ['robinhood', 'stock trading'],
                'url_builder': lambda q: f'https://robinhood.com/stocks/{quote_plus(q.upper())}' if q else 'https://robinhood.com',
                'wait_time': 1.5,
                'extractor': self._extract_finance_data,
                'category': 'finance',
            },
            'yahoo_finance': {
                'triggers': ['yahoo finance', 'stock quote', 'stock price'],
                'url_builder': lambda q: f'https://finance.yahoo.com/quote/{quote_plus(q.upper())}' if q else 'https://finance.yahoo.com',
                'wait_time': 2,
                'extractor': self._extract_finance_data,
                'category': 'finance',
            },
            'turbotax': {
                'triggers': ['turbotax', 'tax filing', 'file taxes'],
                'url_builder': lambda q: 'https://turbotax.intuit.com',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'finance',
            },

            # --- HEALTHCARE ---
            'zocdoc': {
                'triggers': ['zocdoc', 'doctor appointment', 'find doctor'],
                'url_builder': lambda q: f'https://www.zocdoc.com/search?address={quote_plus(q)}' if q else 'https://www.zocdoc.com',
                'wait_time': 1.5,
                'extractor': self._extract_healthcare_listings,
                'category': 'healthcare',
            },
            'webmd': {
                'triggers': ['webmd', 'health symptoms', 'medical search'],
                'url_builder': lambda q: f'https://www.webmd.com/search/search_results/default.aspx?query={quote_plus(q)}' if q else 'https://www.webmd.com',
                'wait_time': 2,
                'extractor': self._extract_article_content,
                'category': 'healthcare',
            },
            'healthgrades': {
                'triggers': ['healthgrades', 'doctor reviews', 'physician search'],
                'url_builder': lambda q: f'https://www.healthgrades.com/search?what={quote_plus(q)}' if q else 'https://www.healthgrades.com',
                'wait_time': 1.5,
                'extractor': self._extract_healthcare_listings,
                'category': 'healthcare',
            },

            # --- GOVERNMENT & LEGAL ---
            'usps': {
                'triggers': ['usps', 'usps tracking', 'mail tracking'],
                'url_builder': lambda q: f'https://tools.usps.com/go/TrackConfirmAction?tLabels={quote_plus(q)}' if q else 'https://www.usps.com',
                'wait_time': 2,
                'extractor': self._extract_tracking_info,
                'category': 'government',
            },
            'irs': {
                'triggers': ['irs', 'irs.gov', 'tax refund'],
                'url_builder': lambda q: 'https://www.irs.gov',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'government',
            },
            'uscis': {
                'triggers': ['uscis', 'immigration', 'visa status'],
                'url_builder': lambda q: 'https://www.uscis.gov',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'government',
            },

            # --- EDUCATION & LEARNING ---
            'coursera': {
                'triggers': ['coursera', 'online course', 'coursera.org'],
                'url_builder': lambda q: f'https://www.coursera.org/search?query={quote_plus(q)}' if q else 'https://www.coursera.org',
                'wait_time': 1.5,
                'extractor': self._extract_course_listings,
                'category': 'education',
            },
            'udemy': {
                'triggers': ['udemy', 'udemy.com', 'video course'],
                'url_builder': lambda q: f'https://www.udemy.com/courses/search/?q={quote_plus(q)}' if q else 'https://www.udemy.com',
                'wait_time': 1.5,
                'extractor': self._extract_course_listings,
                'category': 'education',
            },
            'linkedin_learning': {
                'triggers': ['linkedin learning', 'lynda', 'professional course'],
                'url_builder': lambda q: f'https://www.linkedin.com/learning/search?keywords={quote_plus(q)}' if q else 'https://www.linkedin.com/learning',
                'wait_time': 1.5,
                'extractor': self._extract_course_listings,
                'category': 'education',
            },
            'khan_academy': {
                'triggers': ['khan academy', 'khanacademy'],
                'url_builder': lambda q: f'https://www.khanacademy.org/search?page_search_query={quote_plus(q)}' if q else 'https://www.khanacademy.org',
                'wait_time': 2,
                'extractor': self._extract_course_listings,
                'category': 'education',
            },

            # --- FOOD & DELIVERY ---
            'doordash': {
                'triggers': ['doordash', 'food delivery', 'order food'],
                'url_builder': lambda q: f'https://www.doordash.com/search/store/{quote_plus(q)}/' if q else 'https://www.doordash.com',
                'wait_time': 1.5,
                'extractor': self._extract_food_listings,
                'category': 'food',
            },
            'ubereats': {
                'triggers': ['uber eats', 'ubereats'],
                'url_builder': lambda q: f'https://www.ubereats.com/search?q={quote_plus(q)}' if q else 'https://www.ubereats.com',
                'wait_time': 1.5,
                'extractor': self._extract_food_listings,
                'category': 'food',
            },
            'grubhub': {
                'triggers': ['grubhub', 'grub hub'],
                'url_builder': lambda q: f'https://www.grubhub.com/search?queryText={quote_plus(q)}' if q else 'https://www.grubhub.com',
                'wait_time': 1.5,
                'extractor': self._extract_food_listings,
                'category': 'food',
            },
            'opentable': {
                'triggers': ['opentable', 'restaurant reservation', 'book table'],
                'url_builder': lambda q: f'https://www.opentable.com/s?term={quote_plus(q)}' if q else 'https://www.opentable.com',
                'wait_time': 1.5,
                'extractor': self._extract_food_listings,
                'category': 'food',
            },

            # --- FREELANCE & GIG WORK ---
            'upwork': {
                'triggers': ['upwork', 'upwork.com', 'freelance job', 'hire freelancer'],
                'url_builder': lambda q: f'https://www.upwork.com/search/jobs/?q={quote_plus(q)}' if q else 'https://www.upwork.com',
                'wait_time': 1.5,
                'extractor': self._extract_gig_listings,
                'category': 'freelance',
            },
            'fiverr': {
                'triggers': ['fiverr', 'fiverr.com', 'gig marketplace'],
                'url_builder': lambda q: f'https://www.fiverr.com/search/gigs?query={quote_plus(q)}' if q else 'https://www.fiverr.com',
                'wait_time': 1.5,
                'extractor': self._extract_gig_listings,
                'category': 'freelance',
            },
            'toptal': {
                'triggers': ['toptal', 'toptal.com', 'elite freelancer'],
                'url_builder': lambda q: 'https://www.toptal.com',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'freelance',
            },
            'freelancer': {
                'triggers': ['freelancer.com', 'freelancer'],
                'url_builder': lambda q: f'https://www.freelancer.com/jobs/{quote_plus(q.replace(" ", "-"))}/' if q else 'https://www.freelancer.com',
                'wait_time': 1.5,
                'extractor': self._extract_gig_listings,
                'category': 'freelance',
            },

            # --- AUTOMOTIVE ---
            'autotrader': {
                'triggers': ['autotrader', 'auto trader', 'car search'],
                'url_builder': lambda q: f'https://www.autotrader.com/cars-for-sale/all-cars?searchRadius=0&makeCodeList={quote_plus(q)}' if q else 'https://www.autotrader.com',
                'wait_time': 1.5,
                'extractor': self._extract_auto_listings,
                'category': 'automotive',
            },
            'cargurus': {
                'triggers': ['cargurus', 'car gurus', 'used cars'],
                'url_builder': lambda q: f'https://www.cargurus.com/Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action?searchCriteria.makeName={quote_plus(q)}' if q else 'https://www.cargurus.com',
                'wait_time': 1.5,
                'extractor': self._extract_auto_listings,
                'category': 'automotive',
            },
            'carmax': {
                'triggers': ['carmax', 'car max'],
                'url_builder': lambda q: f'https://www.carmax.com/cars?search={quote_plus(q)}' if q else 'https://www.carmax.com',
                'wait_time': 1.5,
                'extractor': self._extract_auto_listings,
                'category': 'automotive',
            },

            # --- TICKETS & EVENTS ---
            'ticketmaster': {
                'triggers': ['ticketmaster', 'concert tickets', 'event tickets'],
                'url_builder': lambda q: f'https://www.ticketmaster.com/search?q={quote_plus(q)}' if q else 'https://www.ticketmaster.com',
                'wait_time': 1.5,
                'extractor': self._extract_event_listings,
                'category': 'events',
            },
            'eventbrite': {
                'triggers': ['eventbrite', 'event search', 'local events'],
                'url_builder': lambda q: f'https://www.eventbrite.com/d/online/{quote_plus(q.replace(" ", "-"))}/' if q else 'https://www.eventbrite.com',
                'wait_time': 1.5,
                'extractor': self._extract_event_listings,
                'category': 'events',
            },
            'stubhub': {
                'triggers': ['stubhub', 'stub hub', 'resale tickets'],
                'url_builder': lambda q: f'https://www.stubhub.com/search?q={quote_plus(q)}' if q else 'https://www.stubhub.com',
                'wait_time': 1.5,
                'extractor': self._extract_event_listings,
                'category': 'events',
            },
            'meetup': {
                'triggers': ['meetup', 'meetup.com', 'local meetup'],
                'url_builder': lambda q: f'https://www.meetup.com/find/?keywords={quote_plus(q)}' if q else 'https://www.meetup.com',
                'wait_time': 1.5,
                'extractor': self._extract_event_listings,
                'category': 'events',
            },

            # --- LOGISTICS & SHIPPING ---
            'fedex': {
                'triggers': ['fedex', 'fedex tracking'],
                'url_builder': lambda q: f'https://www.fedex.com/fedextrack/?trknbr={quote_plus(q)}' if q else 'https://www.fedex.com',
                'wait_time': 1.5,
                'extractor': self._extract_tracking_info,
                'category': 'logistics',
            },
            'ups': {
                'triggers': ['ups', 'ups tracking'],
                'url_builder': lambda q: f'https://www.ups.com/track?tracknum={quote_plus(q)}' if q else 'https://www.ups.com',
                'wait_time': 1.5,
                'extractor': self._extract_tracking_info,
                'category': 'logistics',
            },
            'dhl': {
                'triggers': ['dhl', 'dhl tracking'],
                'url_builder': lambda q: f'https://www.dhl.com/us-en/home/tracking.html?tracking-id={quote_plus(q)}' if q else 'https://www.dhl.com',
                'wait_time': 1.5,
                'extractor': self._extract_tracking_info,
                'category': 'logistics',
            },

            # --- CUSTOMER SUPPORT PLATFORMS ---
            'zendesk': {
                'triggers': ['zendesk', 'support ticket', 'help desk'],
                'url_builder': lambda q: 'https://www.zendesk.com/login',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'support',
            },
            'intercom': {
                'triggers': ['intercom', 'customer chat'],
                'url_builder': lambda q: 'https://app.intercom.com',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'support',
            },
            'freshdesk': {
                'triggers': ['freshdesk', 'fresh desk'],
                'url_builder': lambda q: 'https://freshdesk.com/login',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'support',
            },

            # --- ACCOUNTING & FINANCE TOOLS ---
            'quickbooks': {
                'triggers': ['quickbooks', 'quick books', 'qbo'],
                'url_builder': lambda q: 'https://app.qbo.intuit.com',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'accounting',
            },
            'xero': {
                'triggers': ['xero', 'xero.com', 'xero accounting'],
                'url_builder': lambda q: 'https://login.xero.com',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'accounting',
            },
            'freshbooks': {
                'triggers': ['freshbooks', 'fresh books'],
                'url_builder': lambda q: 'https://my.freshbooks.com',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'accounting',
            },
            'wave': {
                'triggers': ['wave accounting', 'waveapps'],
                'url_builder': lambda q: 'https://my.waveapps.com',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'accounting',
            },

            # --- LEGAL & DOCUMENTS ---
            'docusign': {
                'triggers': ['docusign', 'e-sign', 'electronic signature'],
                'url_builder': lambda q: 'https://app.docusign.com',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'legal',
            },
            'pandadoc': {
                'triggers': ['pandadoc', 'panda doc'],
                'url_builder': lambda q: 'https://app.pandadoc.com',
                'wait_time': 1.5,
                'extractor': self._extract_generic_app,
                'category': 'legal',
            },
            'docracy': {
                'triggers': ['docracy', 'legal templates', 'contract templates'],
                'url_builder': lambda q: f'https://www.docracy.com/search?query={quote_plus(q)}' if q else 'https://www.docracy.com',
                'wait_time': 2,
                'extractor': self._extract_search_results,
                'category': 'legal',
            },

            # --- B2B MARKETPLACES ---
            'alibaba': {
                'triggers': ['alibaba', 'alibaba.com', 'wholesale supplier'],
                'url_builder': lambda q: f'https://www.alibaba.com/trade/search?SearchText={quote_plus(q)}' if q else 'https://www.alibaba.com',
                'wait_time': 1.5,
                'extractor': self._extract_b2b_listings,
                'category': 'b2b',
            },
            'thomasnet': {
                'triggers': ['thomasnet', 'thomas net', 'industrial supplier'],
                'url_builder': lambda q: f'https://www.thomasnet.com/search.html?what={quote_plus(q)}' if q else 'https://www.thomasnet.com',
                'wait_time': 1.5,
                'extractor': self._extract_b2b_listings,
                'category': 'b2b',
            },
            'made_in_china': {
                'triggers': ['made-in-china', 'made in china', 'china supplier'],
                'url_builder': lambda q: f'https://www.made-in-china.com/products-search/hot-china-products/{quote_plus(q)}.html' if q else 'https://www.made-in-china.com',
                'wait_time': 1.5,
                'extractor': self._extract_b2b_listings,
                'category': 'b2b',
            },

            # --- GAMING & STREAMING ---
            'twitch': {
                'triggers': ['twitch', 'twitch.tv', 'live stream'],
                'url_builder': lambda q: f'https://www.twitch.tv/search?term={quote_plus(q)}' if q else 'https://www.twitch.tv',
                'wait_time': 1.5,
                'extractor': self._extract_streaming_content,
                'category': 'gaming',
            },
            'steam': {
                'triggers': ['steam', 'steam store', 'pc games'],
                'url_builder': lambda q: f'https://store.steampowered.com/search/?term={quote_plus(q)}' if q else 'https://store.steampowered.com',
                'wait_time': 1.5,
                'extractor': self._extract_gaming_listings,
                'category': 'gaming',
            },

            # --- MISCELLANEOUS ESSENTIAL ---
            'pinterest': {
                'triggers': ['pinterest', 'pinterest.com', 'pin search'],
                'url_builder': lambda q: f'https://www.pinterest.com/search/pins/?q={quote_plus(q)}' if q else 'https://www.pinterest.com',
                'wait_time': 1.5,
                'extractor': self._extract_social_posts,
                'category': 'social',
            },
            'reddit_search': {
                'triggers': ['reddit search'],
                'url_builder': lambda q: f'https://www.reddit.com/search/?q={quote_plus(q)}' if q else 'https://www.reddit.com',
                'wait_time': 1.5,
                'extractor': self._extract_reddit_simple,
                'category': 'community',
            },
            'medium': {
                'triggers': ['medium', 'medium.com', 'blog search'],
                'url_builder': lambda q: f'https://medium.com/search?q={quote_plus(q)}' if q else 'https://medium.com',
                'wait_time': 2,
                'extractor': self._extract_article_content,
                'category': 'research',
            },
            'substack': {
                'triggers': ['substack', 'newsletter search'],
                'url_builder': lambda q: f'https://substack.com/search/{quote_plus(q)}' if q else 'https://substack.com',
                'wait_time': 2,
                'extractor': self._extract_article_content,
                'category': 'research',
            },
        }

        # Find matching site config
        matched_site = None
        for site_name, config in site_configs.items():
            if any(trigger in prompt_lower for trigger in config['triggers']):
                matched_site = (site_name, config)
                break

        if not matched_site:
            logger.debug(f"[MCP-SIMPLE] No site match for prompt: {prompt[:50]}...")
            return None

        site_name, config = matched_site
        logger.info(f"[MCP-SIMPLE] Matched site: {site_name}")
        console.print(f"[bold green]>> MCP-Simple: {site_name.replace('_', ' ').upper()}[/bold green]")

        # Extract search query from prompt
        query = self._extract_search_query(prompt)
        if query:
            console.print(f"[dim cyan]  Search: '{query}'[/dim cyan]")

        # Build URL
        url = config['url_builder'](query)
        logger.info(f"[MCP-SIMPLE] URL: {url}")

        try:
            # Step 1: Navigate
            console.print(f"[cyan]Navigating to {site_name.replace('_', ' ').title()}...[/cyan]")
            nav_result = await self.mcp.call_tool('playwright_navigate', {'url': url})

            # Step 2: Wait for content to load
            wait_time = config['wait_time']
            console.print(f"[dim]Waiting {wait_time}s for content...[/dim]")
            await asyncio.sleep(wait_time)

            # Step 2.5: Scroll down for sites that lazy-load content (FB Ads, Reddit, etc.)
            if site_name in ['fb_ads', 'reddit', 'linkedin', 'google_maps']:
                console.print(f"[dim]Scrolling to load more content...[/dim]")
                try:
                    await self.mcp.call_tool('playwright_scroll', {'direction': 'down', 'amount': 2000})
                    await asyncio.sleep(0.5)
                    await self.mcp.call_tool('playwright_scroll', {'direction': 'down', 'amount': 2000})
                    await asyncio.sleep(0.3)
                except Exception as scroll_err:
                    logger.debug(f"[MCP-SIMPLE] Scroll failed: {scroll_err}")

            # Step 3: Take snapshot
            console.print(f"[dim]Taking snapshot...[/dim]")
            snapshot_result = await self.mcp.call_tool('playwright_snapshot', {})

            if not snapshot_result:
                logger.warning("[MCP-SIMPLE] Empty snapshot")
                return None

            # Step 4: Extract using site-specific extractor
            # Handle different snapshot result formats
            if isinstance(snapshot_result, dict):
                # Get the snapshot text from various possible keys
                snapshot_text = (
                    snapshot_result.get('snapshot') or
                    snapshot_result.get('content') or
                    snapshot_result.get('text') or
                    str(snapshot_result)
                )
                # Also get URL for context
                current_url = snapshot_result.get('url', url)
            else:
                snapshot_text = str(snapshot_result)
                current_url = url

            # Step 4.5: CRITICAL - Extract links with URLs using JavaScript
            # The accessibility snapshot doesn't include URLs, but extractors need them
            # This builds Playwright MCP-style output with actual link URLs
            mcp_style_lines = []
            try:
                # Platform-specific link extraction for better results
                if site_name == 'fb_ads':
                    # FB Ads: Look for advertiser page links
                    # Matches: facebook.com/NUMERIC_ID, ads/library/?id=, ads/library/?page_id=
                    js_code = """() => {
                        const links = [];
                        document.querySelectorAll('a[href*="facebook.com"]').forEach((a, idx) => {
                            const href = a.href || '';
                            const text = (a.innerText || a.textContent || '').trim();
                            // Match advertiser URLs:
                            // 1. facebook.com/NUMERIC_ID (page links)
                            // 2. facebook.com/ads/library/?id=... or ?page_id=... (ads library links)
                            // 3. facebook.com/ads/library/?active_status=all&ad_type=all&... with advertiser_id
                            const isNumericId = href.match(/facebook\\.com\\/\\d{10,}/);
                            const isAdsLibraryId = href.match(/facebook\\.com\\/ads\\/library\\/\\?.*(?:id|page_id|advertiser_id)=/);
                            const isAdvertiserLink = isNumericId || isAdsLibraryId;
                            if (isAdvertiserLink && text && text.length > 2 && text.length < 100) {
                                links.push({ text: text.substring(0, 80), url: href, idx: idx });
                            }
                        });
                        return links.slice(0, 20);
                    }"""
                elif site_name == 'reddit':
                    # Reddit: Look for user profile links
                    js_code = """() => {
                        const links = [];
                        document.querySelectorAll('a[href*="/user/"]').forEach((a, idx) => {
                            const href = a.href || '';
                            const text = (a.innerText || a.textContent || '').trim();
                            if (href.includes('reddit.com/user/') && text && text.length > 1 && text.length < 50) {
                                const username = href.match(/\\/user\\/([^\\/\\?]+)/);
                                if (username && username[1] !== 'me') {
                                    links.push({ text: text.substring(0, 50), url: href, idx: idx });
                                }
                            }
                        });
                        return links.slice(0, 20);
                    }"""
                elif site_name == 'linkedin':
                    # LinkedIn: Look for profile and company links
                    js_code = """() => {
                        const links = [];
                        document.querySelectorAll('a[href*="linkedin.com/in/"], a[href*="linkedin.com/company/"]').forEach((a, idx) => {
                            const href = a.href || '';
                            const text = (a.innerText || a.textContent || '').trim();
                            if (text && text.length > 2 && text.length < 100) {
                                links.push({ text: text.substring(0, 80), url: href, idx: idx });
                            }
                        });
                        return links.slice(0, 20);
                    }"""
                elif site_name == 'google_maps':
                    # Google Maps: Look for place links
                    js_code = """() => {
                        const links = [];
                        document.querySelectorAll('a[href*="google.com/maps/place"]').forEach((a, idx) => {
                            const href = a.href || '';
                            const text = (a.innerText || a.textContent || '').trim();
                            if (text && text.length > 2 && text.length < 100) {
                                links.push({ text: text.substring(0, 80), url: href, idx: idx });
                            }
                        });
                        return links.slice(0, 20);
                    }"""
                else:
                    # Generic: Get all links
                    js_code = """() => {
                        const links = [];
                        const skipWords = ['menu', 'close', 'search', 'filter', 'home', 'login', 'sign', 'help'];
                        document.querySelectorAll('a[href]').forEach((a, idx) => {
                            const text = (a.innerText || a.textContent || '').trim();
                            const href = a.href || '';
                            if (!text || text.length > 100 || !href || href.startsWith('javascript:')) return;
                            if (skipWords.some(w => text.toLowerCase() === w)) return;
                            links.push({ text: text.substring(0, 80), url: href, idx: idx });
                        });
                        return links.slice(0, 50);
                    }"""

                links_result = await self.mcp.call_tool('playwright_evaluate', {'script': js_code})
                logger.info(f"[MCP-SIMPLE] Link extraction result type: {type(links_result)}")

                # Handle evaluate() return format: {"success": True, "result": [...]}
                if isinstance(links_result, dict):
                    if links_result.get('error'):
                        logger.warning(f"[MCP-SIMPLE] Link extraction error: {links_result.get('error')}")
                    elif links_result.get('result'):
                        links_result = links_result.get('result')

                if links_result and isinstance(links_result, list) and len(links_result) > 0:
                    for link in links_result:
                        text = link.get('text', '')
                        href = link.get('url', '')
                        idx = link.get('idx', 0)
                        if text and href:
                            # Format: link "Name" [ref=eXXX] [cursor=pointer]:
                            #           - /url: https://...
                            mcp_style_lines.append(f'link "{text}" [ref=e{idx}] [cursor=pointer]:')
                            mcp_style_lines.append(f'  - /url: {href}')

                    if mcp_style_lines:
                        # Prepend MCP-style links to snapshot for extractors to find
                        snapshot_text = "\n".join(mcp_style_lines) + "\n\n" + snapshot_text
                        logger.info(f"[MCP-SIMPLE] Added {len(links_result)} links in MCP format")
                else:
                    logger.warning(f"[MCP-SIMPLE] No links extracted for {site_name}")
            except Exception as link_err:
                logger.warning(f"[MCP-SIMPLE] Link extraction failed: {link_err}")

            logger.debug(f"[MCP-SIMPLE] Snapshot length: {len(snapshot_text)} chars")
            result = config['extractor'](snapshot_text, query)

            if result:
                return result
            else:
                # Return generic success if no specific extraction
                return f"Opened {site_name.replace('_', ' ').title()}: {url}"

        except Exception as e:
            logger.error(f"[MCP-SIMPLE] Error: {e}")
            return None

    def _extract_search_query(self, prompt: str) -> Optional[str]:
        """Extract search query from prompt - COMPREHENSIVE VERSION.

        Handles all common patterns:
        - Quoted: 'for "booked meetings"' or "for 'cold email'"
        - Parenthetical: '(lead gen/appointment setting)'
        - Prospect pattern: 'SDR/lead-gen agency prospect'
        - From pattern: 'from lead-gen talk'
        - After site name: 'FB Ads Library cold email'
        """
        import re
        import json

        # CRITICAL: Unwrap JSON-wrapped prompts first
        # Some code paths wrap prompts as: {"type":"task","prompt":"actual prompt"}
        try:
            parsed = json.loads(prompt)
            if isinstance(parsed, dict) and 'prompt' in parsed:
                prompt = parsed['prompt']
                logger.debug(f"[SEARCH QUERY] Unwrapped JSON prompt: {prompt[:60]}...")
        except (json.JSONDecodeError, TypeError):
            pass  # Not JSON, use as-is

        # ALL quote characters (NOT raw string so \u works!)
        QUOTES = '"\'"\u201c\u201d\u2018\u2019'

        # Stopwords that should never be returned as search queries
        stopwords = {
            'ads', 'users', 'profiles', 'posts', 'library', 'for', 'the',
            'on', 'in', 'at', 'to', 'a', 'an', 'fb ads', 'facebook', 'reddit',
            'linkedin', 'gmail', 'zoho', 'google maps', 'no login', 'login',
            'output', 'url', 'urls', 'profile', 'advertiser', 'listing',
            'prospect', 'agency', 'blocked', 'result', 'pointing', 'final',
            'reached', 'logged', 'not logged'
        }

        def is_valid_query(q: str) -> bool:
            """Check if extracted query is valid."""
            if not q or len(q) < 3:
                return False
            q_lower = q.lower().strip()
            # Reject URLs
            if '://' in q or q_lower.startswith('www.') or q_lower.startswith('http'):
                return False
            if '.com' in q_lower or '.io' in q_lower or '.net' in q_lower:
                return False
            # Reject if it's just a stopword
            if q_lower in stopwords:
                return False
            return True

        def clean_query(q: str) -> str:
            """Clean extracted query."""
            # Replace slashes/dashes with spaces
            q = re.sub(r'[/\-]', ' ', q)
            # Remove extra whitespace
            q = ' '.join(q.split())
            return q.strip()

        # P1: Quoted text after "for" - highest priority
        # Use f-string to properly include Unicode quotes
        pattern_for_quoted = f'\\bfor\\s+[{QUOTES}]([^{QUOTES}]+)[{QUOTES}]'
        for_quoted = re.search(pattern_for_quoted, prompt, re.I)
        if for_quoted:
            query = for_quoted.group(1).strip()
            if is_valid_query(query):
                return query

        # P2: Any quoted text
        pattern_quoted = f'[{QUOTES}]([^{QUOTES}]+)[{QUOTES}]'
        quoted = re.search(pattern_quoted, prompt)
        if quoted:
            query = quoted.group(1).strip()
            if is_valid_query(query):
                return query

        # P2.5: Unquoted "for X" where X is the search term (no quotes)
        # Matches: "find 1 advertiser for booked meetings"
        # Only extracts text AFTER "for" (not "1 advertiser for X")
        for_unquoted = re.search(r'\bfor\s+([a-zA-Z][a-zA-Z0-9\s\-]+)$', prompt.strip(), re.I)
        if for_unquoted:
            query = clean_query(for_unquoted.group(1))
            if is_valid_query(query):
                return query

        # P3: Parenthetical text - "(lead gen/appointment setting/marketing)"
        paren_match = re.search(r'\(([^)]{5,50})\)', prompt)
        if paren_match:
            query = clean_query(paren_match.group(1))
            # Remove "no login" if present
            query = re.sub(r'\bno\s+login\b', '', query, flags=re.I).strip()
            if is_valid_query(query) and len(query) > 5:
                return query

        # P4: "X prospect" or "X listing" or "X URL" pattern
        # Matches: "SDR/lead-gen agency prospect URL"
        prospect_match = re.search(
            r'(?:output\s+\d+\s+)?([a-zA-Z][a-zA-Z0-9\-/\s]{3,40}?)\s+(?:prospect|listing|profile|agency)\s+(?:URL|link)?',
            prompt, re.I
        )
        if prospect_match:
            query = clean_query(prospect_match.group(1))
            if is_valid_query(query):
                return query

        # P5: "from X talk/discussion" pattern
        from_match = re.search(
            r'\bfrom\s+([a-zA-Z][a-zA-Z0-9\-/\s]+?)(?:\s+talk|\s+discussion|\s+post|\s*[.:)]|$)',
            prompt, re.I
        )
        if from_match:
            query = clean_query(from_match.group(1))
            if is_valid_query(query):
                return query

        # P6: Keywords after site name
        site_match = re.search(
            r'(?:fb\s+ads\s+library|fb\s+ads|facebook\s+ads|reddit|linkedin|gmail|zoho|google\s+maps)\s*[:(]?\s*([a-zA-Z][a-zA-Z0-9\-/\s]+?)(?:\s*[(:.]|\s+output|\s+no\s+login|\s*$)',
            prompt, re.I
        )
        if site_match:
            query = clean_query(site_match.group(1))
            query = re.sub(r'\b(search|for|find|about|looking)\b', '', query, flags=re.I).strip()
            if is_valid_query(query):
                return query

        # P7: Text after "search" or "find"
        search_match = re.search(r'\b(?:search|find)\s+([a-zA-Z][a-zA-Z0-9\-/\s]{3,40}?)(?:\s*[(:.]|$)', prompt, re.I)
        if search_match:
            query = clean_query(search_match.group(1))
            if is_valid_query(query):
                return query

        return None

    def _extract_fb_ads_simple(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract FB Ads advertiser info from snapshot text.

        Handles Playwright MCP snapshot format:
        link "Advertiser Name" [ref=e280] [cursor=pointer]:
          - /url: https://www.facebook.com/61584836816352/

        Also handles simpler formats like:
        link 'Name' ... facebook.com/12345
        """
        import re

        # Look for advertiser patterns in FB Ads Library snapshot
        advertisers = []

        # Skip these common navigation/UI elements (case-insensitive)
        skip_names = {
            'meta ad library', 'ad library', 'facebook', 'home', 'create',
            'settings', 'help', 'log in', 'sign up', 'see ad details',
            'load more', 'show more', 'learn more', 'see all', 'menu',
            'notifications', 'messenger', 'search', 'video', 'marketplace',
            'watch', 'groups', 'gaming', 'all filters', 'clear filters',
            'privacy', 'terms', 'advertising', 'ad choices', 'cookies',
            'active status', 'all ads', 'image', 'video', 'text',
            'more about this ad', 'about', 'careers', 'english', 'meta',
            'active ads', 'inactive ads', 'keyword', 'advertiser', 'filters',
            'date', 'media type', 'language', 'platform', 'country', 'us',
            'all', 'today', 'last 7 days', 'last 30 days', 'last 90 days',
            'start date', 'end date', 'apply', 'reset', 'close', 'cancel'
        }

        # Skip patterns (UI element indicators)
        skip_patterns = ['filter', 'sort', 'menu', 'page', 'close', 'active',
                        'status', 'type', 'select', 'option', 'dropdown',
                        'button', 'input', 'checkbox', 'radio']

        # PATTERN 1: Playwright MCP format - link "Name" followed by /url: facebook.com/ID
        # Format: link "Name" [ref=X] ... /url: https://www.facebook.com/ID/
        # Split snapshot into lines and look for link + url pairs
        lines = snapshot.split('\n')
        current_name = None
        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # Match link "Name" [ref=...] format
            link_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line_stripped, re.I)
            if link_match:
                name = link_match.group(1).strip()
                # Store as potential advertiser
                if name and len(name) > 2 and name.lower() not in skip_names:
                    if not any(p in name.lower() for p in skip_patterns):
                        current_name = name
                continue

            # Match /url: format (comes after link)
            url_match = re.match(r'-?\s*/url:\s*(https?://(?:www\.)?facebook\.com/(\d{10,})/?).*', line_stripped, re.I)
            if url_match and current_name:
                page_url = url_match.group(1)
                page_id = url_match.group(2)
                advertisers.append({
                    'name': current_name,
                    'url': page_url,
                    'page_id': page_id
                })
                current_name = None  # Reset for next pair
                continue

            # Also check for url: without leading slash
            url_match2 = re.match(r'url:\s*(https?://(?:www\.)?facebook\.com/(\d{10,})/?).*', line_stripped, re.I)
            if url_match2 and current_name:
                page_url = url_match2.group(1)
                page_id = url_match2.group(2)
                advertisers.append({
                    'name': current_name,
                    'url': page_url,
                    'page_id': page_id
                })
                current_name = None
                continue

        # PATTERN 2: Links with facebook.com page IDs in same line (fallback)
        if not advertisers:
            fb_page_pattern = r'link\s+["\']([^"\']+)["\']\s*.*?(?:facebook\.com/|fb\.com/)(\d{10,})'
            for match in re.finditer(fb_page_pattern, snapshot, re.I | re.DOTALL):
                name = match.group(1).strip()
                page_id = match.group(2)
                if name and len(name) > 2 and name.lower() not in skip_names:
                    if not any(p in name.lower() for p in skip_patterns):
                        advertisers.append({
                            'name': name,
                            'url': f'https://www.facebook.com/{page_id}/',
                            'page_id': page_id
                        })

        # PATTERN 3: Look for "See ad details" preceded by advertiser name
        if not advertisers:
            ad_detail_pattern = r'link\s+["\']([^"\']{3,60})["\']\s*\[ref.*?(?:See ad details|View ad details)'
            for match in re.finditer(ad_detail_pattern, snapshot, re.I | re.DOTALL):
                name = match.group(1).strip()
                if name and name.lower() not in skip_names and len(name) > 2:
                    if not any(p in name.lower() for p in skip_patterns):
                        advertisers.append({'name': name, 'url': ''})

        # PATTERN 4: Any link that looks like a business/company name (last resort)
        if not advertisers:
            link_pattern = r'link\s+["\']([A-Z][^"\']{2,50})["\']\s*\[ref'
            for match in re.finditer(link_pattern, snapshot):
                name = match.group(1).strip()
                name_lower = name.lower()
                if name_lower not in skip_names and not name.startswith('http'):
                    word_count = len(name.split())
                    if word_count <= 6 and not any(p in name_lower for p in skip_patterns):
                        advertisers.append({'name': name, 'url': ''})

        # Deduplicate by name (case-insensitive)
        seen = set()
        unique_advertisers = []
        for adv in advertisers:
            name_key = adv['name'].lower()
            if name_key not in seen:
                seen.add(name_key)
                unique_advertisers.append(adv)

        if unique_advertisers:
            count = len(unique_advertisers)
            result_lines = [f"Found {count} FB advertiser(s) for '{query or 'all ads'}'"]

            # Show each advertiser with their URL (this is what the user wants)
            for i, adv in enumerate(unique_advertisers[:5]):  # Show up to 5
                result_lines.append(f"  {i+1}. {adv['name']}")
                if adv.get('url'):
                    result_lines.append(f"     Advertiser URL: {adv['url']}")

            if count > 5:
                result_lines.append(f"  ... and {count - 5} more advertisers")

            return "\n".join(result_lines)

        # Fallback: If we can't extract advertisers but page loaded, still report success
        if 'ad library' in snapshot.lower() or 'facebook.com/ads/library' in snapshot.lower():
            return f"FB Ads Library loaded for '{query or 'all ads'}' - page may require scrolling to load ads"

        return None

    def _extract_reddit_simple(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract Reddit user/post info from snapshot text.

        Handles Playwright MCP snapshot format:
        link "Username" [ref=X]:
          - /url: https://www.reddit.com/user/username/
        """
        import re

        users = []
        subreddits = []

        # PATTERN 1: Playwright MCP format - /url: reddit.com/user/X or /r/X
        lines = snapshot.split('\n')
        for line in lines:
            line_stripped = line.strip()

            # Match /url: reddit.com/user/username
            user_url_match = re.match(r'-?\s*/url:\s*https?://(?:www\.)?reddit\.com/user/([^\s/]+)/?', line_stripped, re.I)
            if user_url_match:
                username = user_url_match.group(1)
                if username and username not in users and username.lower() not in ['me', 'deleted', 'undefined']:
                    users.append(username)
                continue

            # Match /url: reddit.com/r/subreddit
            sub_url_match = re.match(r'-?\s*/url:\s*https?://(?:www\.)?reddit\.com/r/([^\s/]+)/?', line_stripped, re.I)
            if sub_url_match:
                sub = sub_url_match.group(1)
                if sub and sub not in subreddits:
                    subreddits.append(sub)

        # PATTERN 2: Direct URL patterns in text (fallback)
        if not users:
            user_pattern = r'reddit\.com/user/([^\s\)/"]+)'
            for match in re.finditer(user_pattern, snapshot):
                username = match.group(1)
                if username not in users and username.lower() not in ['me', 'deleted', 'undefined']:
                    users.append(username)

        if not subreddits:
            sub_pattern = r'reddit\.com/r/([^\s\)/"]+)'
            for match in re.finditer(sub_pattern, snapshot):
                sub = match.group(1)
                if sub not in subreddits:
                    subreddits.append(sub)

        if users:
            result_lines = [f"Found {len(users)} Reddit user(s)"]
            # Show each user with their profile URL (SDR-friendly output)
            for i, username in enumerate(users[:5]):
                result_lines.append(f"  {i+1}. u/{username}")
                result_lines.append(f"     Profile URL: https://www.reddit.com/user/{username}")
            if len(users) > 5:
                result_lines.append(f"  ... and {len(users) - 5} more users")
            return "\n".join(result_lines)
        elif subreddits:
            return f"Found {len(subreddits)} subreddit(s): r/{', r/'.join(subreddits[:5])}"

        return None

    def _extract_linkedin_simple(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract LinkedIn profile info from snapshot text.

        Handles Playwright MCP snapshot format:
        link "Name" [ref=X]:
          - /url: https://www.linkedin.com/in/profile-id/
        """
        import re

        profiles = []
        companies = []

        # PATTERN 1: Playwright MCP format - /url: linkedin.com/in/X or /company/X
        lines = snapshot.split('\n')
        current_name = None
        for line in lines:
            line_stripped = line.strip()

            # Match link "Name" [ref=...] format to get profile/company names
            link_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line_stripped, re.I)
            if link_match:
                current_name = link_match.group(1).strip()
                # Skip UI elements
                if current_name.lower() in ['home', 'my network', 'jobs', 'messaging', 'notifications', 'me', 'for business', 'linkedin']:
                    current_name = None
                continue

            # Match /url: linkedin.com/in/profile-id
            profile_url_match = re.match(r'-?\s*/url:\s*https?://(?:www\.)?linkedin\.com/in/([^\s/?]+)', line_stripped, re.I)
            if profile_url_match:
                profile_id = profile_url_match.group(1)
                if profile_id not in [p['id'] for p in profiles]:
                    profiles.append({
                        'id': profile_id,
                        'name': current_name or profile_id
                    })
                current_name = None
                continue

            # Match /url: linkedin.com/company/company-id
            company_url_match = re.match(r'-?\s*/url:\s*https?://(?:www\.)?linkedin\.com/company/([^\s/?]+)', line_stripped, re.I)
            if company_url_match:
                company_id = company_url_match.group(1)
                if company_id not in [c['id'] for c in companies]:
                    companies.append({
                        'id': company_id,
                        'name': current_name or company_id
                    })
                current_name = None

        # PATTERN 2: Direct URL patterns in text (fallback)
        if not profiles:
            profile_pattern = r'linkedin\.com/in/([^\s\)/"?]+)'
            for match in re.finditer(profile_pattern, snapshot):
                profile_id = match.group(1)
                if profile_id not in [p['id'] for p in profiles]:
                    profiles.append({'id': profile_id, 'name': profile_id})

        if not companies:
            company_pattern = r'linkedin\.com/company/([^\s\)/"?]+)'
            for match in re.finditer(company_pattern, snapshot):
                company_id = match.group(1)
                if company_id not in [c['id'] for c in companies]:
                    companies.append({'id': company_id, 'name': company_id})

        if profiles:
            result_lines = [f"Found {len(profiles)} LinkedIn profile(s)"]
            # Show each profile with their URL (SDR-friendly output)
            for i, profile in enumerate(profiles[:5]):
                result_lines.append(f"  {i+1}. {profile['name']}")
                result_lines.append(f"     Profile URL: https://www.linkedin.com/in/{profile['id']}")
            if len(profiles) > 5:
                result_lines.append(f"  ... and {len(profiles) - 5} more profiles")
            return "\n".join(result_lines)
        elif companies:
            result_lines = [f"Found {len(companies)} LinkedIn company page(s)"]
            # Show each company with their URL (SDR-friendly output)
            for i, company in enumerate(companies[:5]):
                result_lines.append(f"  {i+1}. {company['name']}")
                result_lines.append(f"     Company URL: https://www.linkedin.com/company/{company['id']}")
            if len(companies) > 5:
                result_lines.append(f"  ... and {len(companies) - 5} more companies")
            return "\n".join(result_lines)

        return None

    def _extract_gmail_simple(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract Gmail inbox info from snapshot text."""
        # Just confirm we're on Gmail
        if 'mail.google.com' in snapshot.lower() or 'inbox' in snapshot.lower():
            return "Opened Gmail inbox\n  URL: https://mail.google.com"
        return None

    def _extract_zoho_simple(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract Zoho Mail inbox info from snapshot text."""
        if 'zoho' in snapshot.lower() or 'inbox' in snapshot.lower():
            return "Opened Zoho Mail inbox\n  URL: https://mail.zoho.com"
        return None

    def _extract_maps_simple(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract Google Maps results from snapshot text.

        Handles Playwright MCP snapshot format:
        link "Business Name" [ref=X]:
          - /url: https://www.google.com/maps/place/...
        """
        import re

        businesses = []
        skip_names = {'google', 'maps', 'search', 'settings', 'directions',
                     'explore', 'saved', 'contribute', 'send feedback', 'menu',
                     'your location', 'recents', 'hotels', 'restaurants',
                     'things to do', 'transit', 'pharmacies', 'atms', 'gas'}

        # PATTERN 1: Playwright MCP format - link "Name" followed by /url: maps/place
        lines = snapshot.split('\n')
        current_name = None
        for line in lines:
            line_stripped = line.strip()

            # Match link "Name" [ref=...] format
            link_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line_stripped, re.I)
            if link_match:
                name = link_match.group(1).strip()
                if name and len(name) > 2 and name.lower() not in skip_names:
                    if not name.startswith('http'):
                        current_name = name
                continue

            # Match /url: google.com/maps/place/X
            place_url_match = re.match(r'-?\s*/url:\s*https?://(?:www\.)?google\.com/maps/place/([^\s?]+)', line_stripped, re.I)
            if place_url_match and current_name:
                place_id = place_url_match.group(1)
                businesses.append({
                    'name': current_name,
                    'url': f'https://www.google.com/maps/place/{place_id}'
                })
                current_name = None

        # PATTERN 2: Direct URL patterns (fallback)
        if not businesses:
            link_pattern = r'link\s+["\']([^"\']{3,60})["\']\s*\[ref'
            for match in re.finditer(link_pattern, snapshot, re.I):
                name = match.group(1).strip()
                if name.lower() not in skip_names and not name.startswith('http'):
                    businesses.append({'name': name, 'url': ''})

        if businesses:
            result_lines = [f"Found {len(businesses)} business(es) on Google Maps for '{query or 'search'}'"]
            # Show each business with their URL (SDR-friendly output)
            for i, biz in enumerate(businesses[:5]):
                result_lines.append(f"  {i+1}. {biz['name']}")
                if biz.get('url'):
                    result_lines.append(f"     Maps URL: {biz['url']}")
            if len(businesses) > 5:
                result_lines.append(f"  ... and {len(businesses) - 5} more businesses")
            return "\n".join(result_lines)

        return None

    # =========================================================================
    # GENERIC EXTRACTORS - Work across multiple sites in each category
    # =========================================================================

    def _extract_generic_app(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Generic extractor for web apps (CRM, project management, etc.)."""
        # Just confirm we loaded the app
        if snapshot and len(snapshot) > 100:
            return f"Opened application successfully\n  Page loaded with {len(snapshot)} characters of content"
        return None

    def _extract_job_listings(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract job listings from Indeed, Glassdoor, ZipRecruiter, etc."""
        import re

        jobs = []
        lines = snapshot.split('\n')
        current_title = None

        for line in lines:
            line = line.strip()

            # Match job title links: link "Software Engineer" [ref=...]
            title_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line, re.I)
            if title_match:
                title = title_match.group(1).strip()
                # Filter out UI elements
                if len(title) > 5 and title.lower() not in ['sign in', 'post job', 'search', 'home', 'companies']:
                    current_title = title
                continue

            # Match job URL: /url: https://...
            url_match = re.match(r'-?\s*/url:\s*(https?://[^\s]+)', line, re.I)
            if url_match and current_title:
                url = url_match.group(1)
                if 'job' in url.lower() or 'career' in url.lower() or 'position' in url.lower():
                    jobs.append({'title': current_title, 'url': url})
                current_title = None

        if jobs:
            result_lines = [f"Found {len(jobs)} job listing(s) for '{query or 'search'}'"]
            for i, job in enumerate(jobs[:5]):
                result_lines.append(f"  {i+1}. {job['title']}")
                result_lines.append(f"     Job URL: {job['url']}")
            if len(jobs) > 5:
                result_lines.append(f"  ... and {len(jobs) - 5} more jobs")
            return "\n".join(result_lines)

        return f"Job search page loaded for '{query or 'search'}'"

    def _extract_social_posts(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract social media posts/profiles from Twitter, Instagram, TikTok."""
        import re

        profiles = []
        posts = []
        lines = snapshot.split('\n')

        for line in lines:
            line = line.strip()

            # Match profile URLs
            profile_match = re.search(r'(twitter\.com|x\.com|instagram\.com|tiktok\.com)/@?([^\s/"?]+)', line, re.I)
            if profile_match:
                platform = profile_match.group(1)
                username = profile_match.group(2)
                if username and len(username) > 1 and username.lower() not in ['search', 'explore', 'home']:
                    url = f"https://{profile_match.group(1)}/{username}"
                    if url not in [p['url'] for p in profiles]:
                        profiles.append({'username': username, 'url': url})

        if profiles:
            result_lines = [f"Found {len(profiles)} social profile(s)"]
            for i, p in enumerate(profiles[:5]):
                result_lines.append(f"  {i+1}. @{p['username']}")
                result_lines.append(f"     Profile URL: {p['url']}")
            if len(profiles) > 5:
                result_lines.append(f"  ... and {len(profiles) - 5} more profiles")
            return "\n".join(result_lines)

        return f"Social media page loaded for '{query or 'search'}'"

    def _extract_youtube_results(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract YouTube video results."""
        import re

        videos = []
        lines = snapshot.split('\n')
        current_title = None

        for line in lines:
            line = line.strip()

            # Match video title links
            title_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line, re.I)
            if title_match:
                title = title_match.group(1).strip()
                if len(title) > 10 and title.lower() not in ['home', 'shorts', 'subscriptions', 'library']:
                    current_title = title
                continue

            # Match video URL: /url: youtube.com/watch?v=...
            url_match = re.match(r'-?\s*/url:\s*(https?://(?:www\.)?youtube\.com/watch\?v=[^\s]+)', line, re.I)
            if url_match and current_title:
                videos.append({'title': current_title, 'url': url_match.group(1)})
                current_title = None

        if videos:
            result_lines = [f"Found {len(videos)} video(s) for '{query or 'search'}'"]
            for i, v in enumerate(videos[:5]):
                result_lines.append(f"  {i+1}. {v['title'][:60]}...")
                result_lines.append(f"     Video URL: {v['url']}")
            if len(videos) > 5:
                result_lines.append(f"  ... and {len(videos) - 5} more videos")
            return "\n".join(result_lines)

        return f"YouTube search loaded for '{query or 'search'}'"

    def _extract_ecommerce_products(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract products from Amazon, eBay, Etsy."""
        import re

        products = []
        lines = snapshot.split('\n')
        current_name = None

        for line in lines:
            line = line.strip()

            # Match product name links
            name_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line, re.I)
            if name_match:
                name = name_match.group(1).strip()
                if len(name) > 10 and '$' not in name and name.lower() not in ['cart', 'sign in', 'account']:
                    current_name = name
                continue

            # Match product URL
            url_match = re.match(r'-?\s*/url:\s*(https?://[^\s]+(?:dp|itm|listing)[^\s]*)', line, re.I)
            if url_match and current_name:
                products.append({'name': current_name[:80], 'url': url_match.group(1)})
                current_name = None

        # Also look for prices
        prices = re.findall(r'\$[\d,]+\.?\d*', snapshot)

        if products:
            result_lines = [f"Found {len(products)} product(s) for '{query or 'search'}'"]
            for i, p in enumerate(products[:5]):
                result_lines.append(f"  {i+1}. {p['name']}")
                result_lines.append(f"     Product URL: {p['url']}")
            if len(products) > 5:
                result_lines.append(f"  ... and {len(products) - 5} more products")
            return "\n".join(result_lines)

        return f"E-commerce search loaded for '{query or 'search'}' - {len(prices)} prices found on page"

    def _extract_real_estate_listings(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract real estate listings from Zillow, Realtor, Redfin."""
        import re

        listings = []
        lines = snapshot.split('\n')
        current_address = None

        for line in lines:
            line = line.strip()

            # Match address links (usually contain street numbers and names)
            addr_match = re.match(r'link\s+"(\d+[^"]+)"\s*\[ref=', line, re.I)
            if addr_match:
                addr = addr_match.group(1).strip()
                if len(addr) > 10:
                    current_address = addr
                continue

            # Match listing URL
            url_match = re.match(r'-?\s*/url:\s*(https?://[^\s]+(?:homedetails|property|listing)[^\s]*)', line, re.I)
            if url_match and current_address:
                listings.append({'address': current_address, 'url': url_match.group(1)})
                current_address = None

        # Look for prices
        prices = re.findall(r'\$[\d,]+(?:K|M)?', snapshot)

        if listings:
            result_lines = [f"Found {len(listings)} property listing(s) for '{query or 'search'}'"]
            for i, l in enumerate(listings[:5]):
                result_lines.append(f"  {i+1}. {l['address']}")
                result_lines.append(f"     Listing URL: {l['url']}")
            if len(listings) > 5:
                result_lines.append(f"  ... and {len(listings) - 5} more listings")
            return "\n".join(result_lines)

        return f"Real estate search loaded for '{query or 'search'}' - {len(prices)} prices found on page"

    def _extract_local_business(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract local business info from Yelp, TripAdvisor."""
        import re

        businesses = []
        lines = snapshot.split('\n')
        current_name = None

        for line in lines:
            line = line.strip()

            # Match business name links
            name_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line, re.I)
            if name_match:
                name = name_match.group(1).strip()
                # Filter UI elements
                if len(name) > 3 and name.lower() not in ['home', 'search', 'write a review', 'sign up', 'log in']:
                    current_name = name
                continue

            # Match business URL
            url_match = re.match(r'-?\s*/url:\s*(https?://(?:www\.)?(?:yelp|tripadvisor)[^\s]+biz[^\s]*)', line, re.I)
            if url_match and current_name:
                businesses.append({'name': current_name, 'url': url_match.group(1)})
                current_name = None

        if businesses:
            result_lines = [f"Found {len(businesses)} business(es) for '{query or 'search'}'"]
            for i, b in enumerate(businesses[:5]):
                result_lines.append(f"  {i+1}. {b['name']}")
                result_lines.append(f"     Business URL: {b['url']}")
            if len(businesses) > 5:
                result_lines.append(f"  ... and {len(businesses) - 5} more businesses")
            return "\n".join(result_lines)

        return f"Local business search loaded for '{query or 'search'}'"

    def _extract_search_results(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract search results from Google, Scholar."""
        import re

        results = []
        lines = snapshot.split('\n')
        current_title = None

        for line in lines:
            line = line.strip()

            # Match result title links
            title_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line, re.I)
            if title_match:
                title = title_match.group(1).strip()
                if len(title) > 10 and title.lower() not in ['images', 'news', 'videos', 'maps', 'shopping']:
                    current_title = title
                continue

            # Match result URL (not google.com internal links)
            url_match = re.match(r'-?\s*/url:\s*(https?://(?!www\.google)[^\s]+)', line, re.I)
            if url_match and current_title:
                url = url_match.group(1)
                if 'google.com' not in url:
                    results.append({'title': current_title, 'url': url})
                current_title = None

        if results:
            result_lines = [f"Found {len(results)} search result(s) for '{query or 'search'}'"]
            for i, r in enumerate(results[:5]):
                result_lines.append(f"  {i+1}. {r['title'][:60]}...")
                result_lines.append(f"     URL: {r['url']}")
            if len(results) > 5:
                result_lines.append(f"  ... and {len(results) - 5} more results")
            return "\n".join(result_lines)

        return f"Search results loaded for '{query or 'search'}'"

    def _extract_article_content(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract article/wiki content."""
        # For articles, just confirm we loaded content
        if snapshot and len(snapshot) > 500:
            # Count paragraphs/sections
            paragraphs = len(re.findall(r'paragraph|heading|article', snapshot, re.I))
            return f"Article loaded successfully\n  Content: ~{len(snapshot)} characters, {paragraphs} sections"
        return f"Article page loaded for '{query or 'search'}'"

    def _extract_qa_content(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract Q&A content from Quora, Stack Overflow, etc."""
        import re

        questions = []
        lines = snapshot.split('\n')

        for line in lines:
            line = line.strip()

            # Match question links (usually end with ?)
            q_match = re.match(r'link\s+"([^"]+\??)"\s*\[ref=', line, re.I)
            if q_match:
                q = q_match.group(1).strip()
                if len(q) > 20 and '?' in q:
                    questions.append(q)

        if questions:
            result_lines = [f"Found {len(questions)} question(s) for '{query or 'search'}'"]
            for i, q in enumerate(questions[:5]):
                result_lines.append(f"  {i+1}. {q[:80]}...")
            if len(questions) > 5:
                result_lines.append(f"  ... and {len(questions) - 5} more questions")
            return "\n".join(result_lines)

        return f"Q&A page loaded for '{query or 'search'}'"

    def _extract_news_items(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract news items from Google News, Hacker News, etc."""
        import re

        articles = []
        lines = snapshot.split('\n')
        current_title = None

        for line in lines:
            line = line.strip()

            # Match article title links
            title_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line, re.I)
            if title_match:
                title = title_match.group(1).strip()
                if len(title) > 15:
                    current_title = title
                continue

            # Match article URL
            url_match = re.match(r'-?\s*/url:\s*(https?://(?!news\.google)[^\s]+)', line, re.I)
            if url_match and current_title:
                articles.append({'title': current_title, 'url': url_match.group(1)})
                current_title = None

        if articles:
            result_lines = [f"Found {len(articles)} news article(s) for '{query or 'search'}'"]
            for i, a in enumerate(articles[:5]):
                result_lines.append(f"  {i+1}. {a['title'][:60]}...")
                result_lines.append(f"     Article URL: {a['url']}")
            if len(articles) > 5:
                result_lines.append(f"  ... and {len(articles) - 5} more articles")
            return "\n".join(result_lines)

        return f"News page loaded for '{query or 'search'}'"

    def _extract_product_listings(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract product listings from Product Hunt, etc."""
        import re

        products = []
        lines = snapshot.split('\n')
        current_name = None

        for line in lines:
            line = line.strip()

            # Match product name links
            name_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line, re.I)
            if name_match:
                name = name_match.group(1).strip()
                if len(name) > 3 and name.lower() not in ['home', 'topics', 'collections', 'ship']:
                    current_name = name
                continue

            # Match product URL
            url_match = re.match(r'-?\s*/url:\s*(https?://(?:www\.)?producthunt\.com/posts/[^\s]+)', line, re.I)
            if url_match and current_name:
                products.append({'name': current_name, 'url': url_match.group(1)})
                current_name = None

        if products:
            result_lines = [f"Found {len(products)} product(s) for '{query or 'search'}'"]
            for i, p in enumerate(products[:5]):
                result_lines.append(f"  {i+1}. {p['name']}")
                result_lines.append(f"     Product URL: {p['url']}")
            if len(products) > 5:
                result_lines.append(f"  ... and {len(products) - 5} more products")
            return "\n".join(result_lines)

        return f"Product listing page loaded for '{query or 'search'}'"

    def _extract_email_inbox(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract email inbox info (Outlook, etc.)."""
        if 'inbox' in snapshot.lower() or 'mail' in snapshot.lower():
            return "Opened email inbox\n  Ready for email operations"
        return None

    def _extract_classifieds(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract classified listings from Craigslist, etc."""
        import re

        listings = []
        lines = snapshot.split('\n')
        current_title = None

        for line in lines:
            line = line.strip()

            # Match listing title links
            title_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line, re.I)
            if title_match:
                title = title_match.group(1).strip()
                if len(title) > 5 and '$' not in title:
                    current_title = title
                continue

            # Match listing URL
            url_match = re.match(r'-?\s*/url:\s*(https?://[^\s]+craigslist[^\s]+\.html)', line, re.I)
            if url_match and current_title:
                listings.append({'title': current_title, 'url': url_match.group(1)})
                current_title = None

        # Look for prices
        prices = re.findall(r'\$[\d,]+', snapshot)

        if listings:
            result_lines = [f"Found {len(listings)} listing(s) for '{query or 'search'}'"]
            for i, l in enumerate(listings[:5]):
                result_lines.append(f"  {i+1}. {l['title'][:60]}...")
                result_lines.append(f"     Listing URL: {l['url']}")
            if len(listings) > 5:
                result_lines.append(f"  ... and {len(listings) - 5} more listings")
            return "\n".join(result_lines)

        return f"Classifieds search loaded for '{query or 'search'}' - {len(prices)} prices found"

    def _extract_travel_listings(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract travel/hotel/flight listings from Booking, Airbnb, Expedia, etc."""
        import re

        listings = []
        lines = snapshot.split('\n')
        current_name = None

        for line in lines:
            line = line.strip()

            # Match hotel/property name
            name_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line, re.I)
            if name_match:
                name = name_match.group(1).strip()
                if len(name) > 5 and 'book now' not in name.lower() and 'search' not in name.lower():
                    current_name = name
                continue

            # Match property URL
            url_match = re.match(r'-?\s*/url:\s*(https?://[^\s]+)', line, re.I)
            if url_match and current_name:
                url = url_match.group(1)
                if any(site in url for site in ['booking.com', 'airbnb.com', 'expedia.com', 'kayak.com', 'hotels.com']):
                    listings.append({'name': current_name, 'url': url})
                    current_name = None

        # Extract prices
        prices = re.findall(r'\$[\d,]+(?:\.\d{2})?(?:/night)?', snapshot)

        if listings:
            result_lines = [f"Found {len(listings)} property/travel option(s)"]
            for i, l in enumerate(listings[:8]):
                result_lines.append(f"  {i+1}. {l['name'][:60]}")
                result_lines.append(f"     URL: {l['url']}")
            if prices:
                result_lines.append(f"  Price range: {prices[0]} - {prices[-1] if len(prices) > 1 else prices[0]}")
            return "\n".join(result_lines)

        return f"Travel search loaded for '{query or 'destination'}' - {len(prices)} prices found"

    def _extract_finance_data(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract financial data - stock prices, crypto, etc."""
        import re

        # Look for price data
        prices = re.findall(r'\$[\d,]+(?:\.\d+)?', snapshot)
        percentages = re.findall(r'[+-]?\d+(?:\.\d+)?%', snapshot)

        # Look for stock symbols
        symbols = re.findall(r'\b[A-Z]{2,5}\b', snapshot)

        result_lines = [f"Financial data for '{query or 'query'}'"]
        if prices:
            result_lines.append(f"  Prices found: {', '.join(prices[:5])}")
        if percentages:
            result_lines.append(f"  Changes: {', '.join(percentages[:5])}")

        return "\n".join(result_lines) if len(result_lines) > 1 else f"Finance page loaded for '{query or 'search'}'"

    def _extract_healthcare_listings(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract healthcare provider listings from Zocdoc, Healthgrades, etc."""
        import re

        providers = []
        lines = snapshot.split('\n')
        current_name = None

        for line in lines:
            line = line.strip()

            # Match provider name
            name_match = re.match(r'link\s+"(?:Dr\.\s*)?([^"]+)"\s*\[ref=', line, re.I)
            if name_match:
                name = name_match.group(1).strip()
                if len(name) > 3 and 'book' not in name.lower() and 'view' not in name.lower():
                    current_name = name
                continue

            # Match profile URL
            url_match = re.match(r'-?\s*/url:\s*(https?://[^\s]+)', line, re.I)
            if url_match and current_name:
                url = url_match.group(1)
                if any(site in url for site in ['zocdoc.com', 'healthgrades.com', 'vitals.com', 'webmd.com']):
                    providers.append({'name': current_name, 'url': url})
                    current_name = None

        if providers:
            result_lines = [f"Found {len(providers)} healthcare provider(s)"]
            for i, p in enumerate(providers[:8]):
                result_lines.append(f"  {i+1}. {p['name']}")
                result_lines.append(f"     Profile: {p['url']}")
            return "\n".join(result_lines)

        return f"Healthcare search loaded for '{query or 'provider'}'"

    def _extract_course_listings(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract online course listings from Coursera, Udemy, etc."""
        import re

        courses = []
        lines = snapshot.split('\n')
        current_title = None

        for line in lines:
            line = line.strip()

            # Match course title
            title_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line, re.I)
            if title_match:
                title = title_match.group(1).strip()
                if len(title) > 5 and 'enroll' not in title.lower() and 'cart' not in title.lower():
                    current_title = title
                continue

            # Match course URL
            url_match = re.match(r'-?\s*/url:\s*(https?://[^\s]+)', line, re.I)
            if url_match and current_title:
                url = url_match.group(1)
                if any(site in url for site in ['coursera.org', 'udemy.com', 'linkedin.com/learning', 'khanacademy.org', 'edx.org']):
                    courses.append({'title': current_title, 'url': url})
                    current_title = None

        if courses:
            result_lines = [f"Found {len(courses)} course(s) for '{query or 'search'}'"]
            for i, c in enumerate(courses[:8]):
                result_lines.append(f"  {i+1}. {c['title'][:60]}")
                result_lines.append(f"     Course URL: {c['url']}")
            return "\n".join(result_lines)

        return f"Course search loaded for '{query or 'topic'}'"

    def _extract_food_listings(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract restaurant/food delivery listings from DoorDash, UberEats, etc."""
        import re

        restaurants = []
        lines = snapshot.split('\n')
        current_name = None

        for line in lines:
            line = line.strip()

            # Match restaurant name
            name_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line, re.I)
            if name_match:
                name = name_match.group(1).strip()
                if len(name) > 2 and 'order' not in name.lower() and 'menu' not in name.lower():
                    current_name = name
                continue

            # Match restaurant URL
            url_match = re.match(r'-?\s*/url:\s*(https?://[^\s]+)', line, re.I)
            if url_match and current_name:
                url = url_match.group(1)
                if any(site in url for site in ['doordash.com', 'ubereats.com', 'grubhub.com', 'opentable.com', 'yelp.com']):
                    restaurants.append({'name': current_name, 'url': url})
                    current_name = None

        # Extract ratings
        ratings = re.findall(r'(\d+(?:\.\d)?)\s*(?:stars?|rating)', snapshot, re.I)
        delivery_times = re.findall(r'(\d+[-–]\d+)\s*min', snapshot, re.I)

        if restaurants:
            result_lines = [f"Found {len(restaurants)} restaurant(s)"]
            for i, r in enumerate(restaurants[:8]):
                result_lines.append(f"  {i+1}. {r['name']}")
                result_lines.append(f"     URL: {r['url']}")
            if delivery_times:
                result_lines.append(f"  Delivery times: {', '.join(delivery_times[:3])} min")
            return "\n".join(result_lines)

        return f"Food search loaded for '{query or 'restaurants'}'"

    def _extract_gig_listings(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract freelance/gig listings from Upwork, Fiverr, etc."""
        import re

        gigs = []
        lines = snapshot.split('\n')
        current_title = None

        for line in lines:
            line = line.strip()

            # Match gig/job title
            title_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line, re.I)
            if title_match:
                title = title_match.group(1).strip()
                if len(title) > 5 and 'apply' not in title.lower() and 'post' not in title.lower():
                    current_title = title
                continue

            # Match gig URL
            url_match = re.match(r'-?\s*/url:\s*(https?://[^\s]+)', line, re.I)
            if url_match and current_title:
                url = url_match.group(1)
                if any(site in url for site in ['upwork.com', 'fiverr.com', 'freelancer.com', 'toptal.com', 'guru.com']):
                    gigs.append({'title': current_title, 'url': url})
                    current_title = None

        # Extract price ranges
        prices = re.findall(r'\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?(?:/hr)?', snapshot)

        if gigs:
            result_lines = [f"Found {len(gigs)} gig/job listing(s)"]
            for i, g in enumerate(gigs[:8]):
                result_lines.append(f"  {i+1}. {g['title'][:60]}")
                result_lines.append(f"     URL: {g['url']}")
            if prices:
                result_lines.append(f"  Budget range: {prices[0]}")
            return "\n".join(result_lines)

        return f"Freelance search loaded for '{query or 'jobs'}'"

    def _extract_auto_listings(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract automotive listings from AutoTrader, CarGurus, etc."""
        import re

        vehicles = []
        lines = snapshot.split('\n')
        current_name = None

        for line in lines:
            line = line.strip()

            # Match vehicle name/title (e.g., "2024 Toyota Camry")
            name_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line, re.I)
            if name_match:
                name = name_match.group(1).strip()
                # Look for year patterns in vehicle names
                if re.search(r'20\d{2}|19\d{2}', name) or any(make in name.lower() for make in ['toyota', 'honda', 'ford', 'bmw', 'mercedes', 'audi', 'chevrolet', 'nissan']):
                    current_name = name
                continue

            # Match vehicle URL
            url_match = re.match(r'-?\s*/url:\s*(https?://[^\s]+)', line, re.I)
            if url_match and current_name:
                url = url_match.group(1)
                if any(site in url for site in ['autotrader.com', 'cargurus.com', 'carmax.com', 'cars.com', 'carfax.com']):
                    vehicles.append({'name': current_name, 'url': url})
                    current_name = None

        # Extract prices and mileage
        prices = re.findall(r'\$[\d,]+', snapshot)
        mileage = re.findall(r'([\d,]+)\s*(?:mi|miles)', snapshot, re.I)

        if vehicles:
            result_lines = [f"Found {len(vehicles)} vehicle(s)"]
            for i, v in enumerate(vehicles[:8]):
                result_lines.append(f"  {i+1}. {v['name'][:60]}")
                result_lines.append(f"     URL: {v['url']}")
            if prices:
                result_lines.append(f"  Price range: {prices[0]} - {prices[-1] if len(prices) > 1 else prices[0]}")
            return "\n".join(result_lines)

        return f"Auto search loaded for '{query or 'vehicles'}'"

    def _extract_event_listings(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract event/ticket listings from Ticketmaster, Eventbrite, etc."""
        import re

        events = []
        lines = snapshot.split('\n')
        current_name = None

        for line in lines:
            line = line.strip()

            # Match event name
            name_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line, re.I)
            if name_match:
                name = name_match.group(1).strip()
                if len(name) > 5 and 'buy' not in name.lower() and 'ticket' not in name.lower():
                    current_name = name
                continue

            # Match event URL
            url_match = re.match(r'-?\s*/url:\s*(https?://[^\s]+)', line, re.I)
            if url_match and current_name:
                url = url_match.group(1)
                if any(site in url for site in ['ticketmaster.com', 'eventbrite.com', 'stubhub.com', 'meetup.com', 'seatgeek.com']):
                    events.append({'name': current_name, 'url': url})
                    current_name = None

        # Extract dates
        dates = re.findall(r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}(?:,?\s+\d{4})?', snapshot, re.I)

        if events:
            result_lines = [f"Found {len(events)} event(s)"]
            for i, e in enumerate(events[:8]):
                result_lines.append(f"  {i+1}. {e['name'][:60]}")
                result_lines.append(f"     URL: {e['url']}")
            if dates:
                result_lines.append(f"  Dates: {', '.join(dates[:3])}")
            return "\n".join(result_lines)

        return f"Event search loaded for '{query or 'events'}'"

    def _extract_tracking_info(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract package tracking info from FedEx, UPS, USPS, DHL."""
        import re

        # Look for tracking status keywords
        status_keywords = ['delivered', 'in transit', 'out for delivery', 'shipped', 'processing', 'picked up', 'arrived']
        found_status = None
        for kw in status_keywords:
            if kw in snapshot.lower():
                found_status = kw.title()
                break

        # Look for dates
        dates = re.findall(r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}(?:,?\s+\d{4})?', snapshot, re.I)

        # Look for locations
        locations = re.findall(r'[A-Z][a-z]+(?:,\s*[A-Z]{2})?', snapshot)

        result_lines = [f"Tracking info for: {query or 'package'}"]
        if found_status:
            result_lines.append(f"  Status: {found_status}")
        if dates:
            result_lines.append(f"  Last update: {dates[0]}")
        if locations:
            result_lines.append(f"  Location: {locations[0] if locations else 'Unknown'}")

        return "\n".join(result_lines) if found_status else f"Tracking page loaded - check status for {query or 'tracking number'}"

    def _extract_b2b_listings(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract B2B/wholesale listings from Alibaba, ThomasNet, etc."""
        import re

        suppliers = []
        lines = snapshot.split('\n')
        current_name = None

        for line in lines:
            line = line.strip()

            # Match supplier/product name
            name_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line, re.I)
            if name_match:
                name = name_match.group(1).strip()
                if len(name) > 5 and 'contact' not in name.lower() and 'inquiry' not in name.lower():
                    current_name = name
                continue

            # Match supplier URL
            url_match = re.match(r'-?\s*/url:\s*(https?://[^\s]+)', line, re.I)
            if url_match and current_name:
                url = url_match.group(1)
                if any(site in url for site in ['alibaba.com', 'thomasnet.com', 'made-in-china.com', 'globalsources.com']):
                    suppliers.append({'name': current_name, 'url': url})
                    current_name = None

        # Extract MOQ and prices
        moq = re.findall(r'(?:MOQ|Min[.]?\s*Order)[:\s]*(\d+)', snapshot, re.I)
        prices = re.findall(r'\$[\d.]+(?:\s*[-–]\s*\$[\d.]+)?(?:/piece|/unit)?', snapshot)

        if suppliers:
            result_lines = [f"Found {len(suppliers)} supplier(s)/product(s)"]
            for i, s in enumerate(suppliers[:8]):
                result_lines.append(f"  {i+1}. {s['name'][:60]}")
                result_lines.append(f"     URL: {s['url']}")
            if moq:
                result_lines.append(f"  Min Order: {moq[0]} units")
            if prices:
                result_lines.append(f"  Price: {prices[0]}")
            return "\n".join(result_lines)

        return f"B2B search loaded for '{query or 'products'}'"

    def _extract_streaming_content(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract streaming content from Twitch, etc."""
        import re

        streams = []
        lines = snapshot.split('\n')
        current_name = None

        for line in lines:
            line = line.strip()

            # Match streamer/channel name
            name_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line, re.I)
            if name_match:
                name = name_match.group(1).strip()
                if len(name) > 2 and 'browse' not in name.lower():
                    current_name = name
                continue

            # Match stream URL
            url_match = re.match(r'-?\s*/url:\s*(https?://[^\s]+twitch\.tv[^\s]*)', line, re.I)
            if url_match and current_name:
                streams.append({'name': current_name, 'url': url_match.group(1)})
                current_name = None

        # Extract viewer counts
        viewers = re.findall(r'([\d,]+)\s*(?:viewers?|watching)', snapshot, re.I)

        if streams:
            result_lines = [f"Found {len(streams)} stream(s)"]
            for i, s in enumerate(streams[:8]):
                result_lines.append(f"  {i+1}. {s['name']}")
                result_lines.append(f"     Channel: {s['url']}")
            if viewers:
                result_lines.append(f"  Top viewer count: {viewers[0]}")
            return "\n".join(result_lines)

        return f"Streaming search loaded for '{query or 'streams'}'"

    def _extract_gaming_listings(self, snapshot: str, query: Optional[str]) -> Optional[str]:
        """Extract gaming listings from Steam, Epic, etc."""
        import re

        games = []
        lines = snapshot.split('\n')
        current_name = None

        for line in lines:
            line = line.strip()

            # Match game title
            name_match = re.match(r'link\s+"([^"]+)"\s*\[ref=', line, re.I)
            if name_match:
                name = name_match.group(1).strip()
                if len(name) > 2 and 'install' not in name.lower() and 'play' not in name.lower():
                    current_name = name
                continue

            # Match game URL
            url_match = re.match(r'-?\s*/url:\s*(https?://[^\s]+)', line, re.I)
            if url_match and current_name:
                url = url_match.group(1)
                if any(site in url for site in ['steampowered.com', 'epicgames.com', 'gog.com']):
                    games.append({'name': current_name, 'url': url})
                    current_name = None

        # Extract prices
        prices = re.findall(r'\$[\d.]+', snapshot)

        if games:
            result_lines = [f"Found {len(games)} game(s)"]
            for i, g in enumerate(games[:8]):
                result_lines.append(f"  {i+1}. {g['name'][:60]}")
                result_lines.append(f"     Store: {g['url']}")
            if prices:
                result_lines.append(f"  Price range: {prices[0]} - {prices[-1] if len(prices) > 1 else prices[0]}")
            return "\n".join(result_lines)

        return f"Gaming search loaded for '{query or 'games'}'"

    async def _run_goal_sequence(self, prompt: str) -> str:
        """Execute a sequence of goals from a complex prompt with checkpoint support."""
        try:
            # Import checkpoint class
            from .goal_sequencer import GoalSequenceCheckpoint

            # Generate sequence ID for checkpoint lookup
            sequence_id = GoalSequenceCheckpoint.generate_sequence_id(prompt)

            # Check for existing checkpoint
            checkpoint = GoalSequenceCheckpoint.load(sequence_id)
            resumed = False

            if checkpoint:
                console.print(f"\n[bold yellow]Found checkpoint for this sequence![/bold yellow]")
                console.print(f"[dim]Progress: {checkpoint.current_index}/{checkpoint.total_goals} goals completed[/dim]")
                console.print(f"[dim]Last updated: {checkpoint.updated_at}[/dim]")

                # Auto-resume if more than 5 goals completed (significant progress)
                should_resume = checkpoint.current_index >= 5

                if not should_resume:
                    # Ask user if they want to resume (for smaller sequences)
                    try:
                        console.print(f"[yellow]Resume from goal {checkpoint.current_index + 1}? [Y/n][/yellow]", end=" ")
                        # Note: In CLI mode, auto-resume. In interactive mode, could prompt.
                        # For now, auto-resume all checkpoints
                        should_resume = True
                    except Exception:
                        should_resume = True

                if should_resume:
                    resumed = True
                    console.print(f"[green]Resuming from goal {checkpoint.current_index + 1}...[/green]")
                else:
                    console.print("[yellow]Starting fresh sequence...[/yellow]")
                    checkpoint = None

            # Parse the prompt into goals
            sequence = parse_goals(prompt)

            # Restore checkpoint if resuming
            if checkpoint and resumed:
                checkpoint.restore_to_sequence(sequence)
                console.print(f"[green]Checkpoint restored: {sequence.current_index}/{len(sequence.goals)} goals completed[/green]\n")
            else:
                console.print(f"\n[bold cyan]Multi-goal task detected: {len(sequence.goals)} goals[/bold cyan]")
                for i, goal in enumerate(sequence.goals):
                    type_indicator = ""
                    if goal.goal_type == GoalType.CONDITIONAL:
                        type_indicator = " [IF]"
                    desc = goal.description[:55] + "..." if len(goal.description) > 55 else goal.description
                    status = "[green]DONE[/green]" if goal.status == GoalStatus.COMPLETED else ""
                    console.print(f"  [dim]{i + 1}. {desc}{type_indicator} {status}[/dim]")
                console.print()

            self._initialize_goal_todos(sequence_id, sequence)

            results = []
            start_time = time.time()

            # Initialize prospect collector for cross-goal deduplication
            prospect_collector = ProspectCollector()

            while not sequence.is_complete:
                # CHECKPOINT: Save state before executing each goal
                try:
                    checkpoint_state = GoalSequenceCheckpoint.from_sequence(sequence, prompt)
                    checkpoint_state.save()
                except Exception as e:
                    logger.warning(f"Failed to save checkpoint: {e}")

                # Use get_next_goal to handle conditionals properly
                current = get_next_goal(sequence)
                if not current:
                    break

                current.status = GoalStatus.EXECUTING
                self._update_goal_todo_status(sequence_id, current, TodoStatus.IN_PROGRESS)

                # Display goal with clear visual separator for multi-task visibility
                goal_type_str = ""
                if current.goal_type == GoalType.CONDITIONAL:
                    goal_type_str = " [CONDITIONAL]"
                console.print(f"\n[bold yellow]{'=' * 60}[/bold yellow]")
                console.print(f"[bold yellow]TASK {current.index + 1} of {len(sequence.goals)}{goal_type_str}[/bold yellow]")
                console.print(f"[yellow]{current.description[:80]}[/yellow]")
                console.print(f"[bold yellow]{'=' * 60}[/bold yellow]")

                try:
                    # Get the clean goal description (without context)
                    clean_goal = current.description

                    # CLEAR STATE: Comprehensive reset between goals to prevent state bleed
                    # This ensures each goal starts fresh without contamination from previous goals
                    # Plan caches
                    if hasattr(self, '_last_plan_prompt'):
                        delattr(self, '_last_plan_prompt')
                    if hasattr(self, '_cached_plan'):
                        delattr(self, '_cached_plan')
                    # Execution state
                    if hasattr(self, '_execution_log'):
                        self._execution_log.clear()
                    if hasattr(self, '_last_issues'):
                        self._last_issues = []
                    if hasattr(self, '_preflight_details'):
                        self._preflight_details = []
                    # Forever mode flags
                    if hasattr(self, '_forever_mode'):
                        self._forever_mode = False
                    if hasattr(self, '_last_checkpoint_time'):
                        self._last_checkpoint_time = None

                    # Build full prompt with context for LLM fallback
                    # Only include minimal context to avoid confusion
                    context = sequence.get_context_for_llm()
                    goal_prompt_with_context = f"{clean_goal}\n\n[CONTEXT: {context}]" if context else clean_goal

                    # Execute single goal - pass both clean goal (for templates) and full prompt (for LLM)
                    result = await self._run_single_goal(clean_goal, goal_prompt_with_context)

                    # Check if successful - only fail on explicit error messages
                    # Don't fail on URLs containing 'sign' or common success patterns
                    result_lower = result.lower() if result else ''
                    goal_lower = clean_goal.lower()
                    explicit_errors = ['error:', 'failed:', 'could not complete', 'unable to', 'exception:', 'timeout']
                    success = result and not any(
                        err in result_lower
                        for err in explicit_errors
                    )

                    # RESULT VERIFICATION: Check if result matches goal type
                    # Detect misrouted results (e.g., FB Ads result for Reddit goal)
                    misroute_detected = False
                    if success:
                        # Reddit goal should not have FB/advertiser results
                        if 'reddit' in goal_lower and ('advertiser' in result_lower or 'fb ads' in result_lower):
                            misroute_detected = True
                            logger.warning(f"Misrouted result: Reddit goal got FB Ads result")
                        # LinkedIn goal should not have FB/advertiser results
                        elif 'linkedin' in goal_lower and ('advertiser' in result_lower or 'fb ads' in result_lower):
                            misroute_detected = True
                            logger.warning(f"Misrouted result: LinkedIn goal got FB Ads result")
                        # Gmail goal should have mail.google.com
                        elif 'gmail' in goal_lower and 'mail.google.com' not in result_lower and 'inbox' not in result_lower:
                            if 'advertiser' in result_lower:  # Got wrong result
                                misroute_detected = True
                                logger.warning(f"Misrouted result: Gmail goal got wrong result")

                    if misroute_detected:
                        logger.warning(f"Goal {current.index + 1} result doesn't match goal type - retrying with LLM")
                        # Don't count as success if misrouted
                        success = False
                        result = f"Misrouted: Got wrong result type for '{clean_goal}'"

                    if success:
                        # Extract meaningful summary from result
                        summary = self._extract_goal_summary(result, clean_goal)
                        console.print(f"[green]+ Task {current.index + 1}: {summary}[/green]")
                        results.append(f"Task {current.index + 1}: {summary}")
                        self._update_goal_todo_status(sequence_id, current, TodoStatus.COMPLETED)

                        # Collect prospects for final summary (SDR-friendly output)
                        new_prospects = prospect_collector.parse_and_collect(result, clean_goal)
                        if new_prospects > 0:
                            console.print(f"[dim cyan]   >> Collected {new_prospects} new prospect(s)[/dim cyan]")

                        # Visual separator and progress indicator
                        console.print(f"[dim]{'-' * 60}[/dim]")
                        console.print(f"[dim cyan]Progress: {current.index + 1}/{len(sequence.goals)} tasks completed[/dim cyan]")
                    else:
                        console.print(f"[red]x Task {current.index + 1} failed: {result[:100]}[/red]")
                        self._update_goal_todo_status(sequence_id, current, TodoStatus.CANCELLED)

                        # Track failure in collector for actionable suggestions
                        prospect_collector.parse_and_collect(result, clean_goal)

                        # Visual separator for failed tasks too
                        console.print(f"[dim]{'-' * 60}[/dim]")
                        console.print(f"[dim]Progress: {current.index + 1}/{len(sequence.goals)} attempted[/dim]")

                    # Advance to next goal (also updates page state)
                    has_more = advance_goal(sequence, success, result, result if not success else None)

                    if not has_more and not sequence.is_complete:
                        console.print("[red]Sequence stopped due to blocking goal failure[/red]")
                        break

                except Exception as e:
                    console.print(f"[red]x Goal {current.index + 1} error: {e}[/red]")
                    logger.error(f"Goal {current.index + 1} execution error: {e}", exc_info=True)
                    self._update_goal_todo_status(sequence_id, current, TodoStatus.CANCELLED)
                    advance_goal(sequence, False, error=str(e))
                    if current.is_blocking:
                        break

            # CHECKPOINT: Clean up checkpoint after successful completion
            if sequence.is_complete:
                try:
                    final_checkpoint = GoalSequenceCheckpoint.from_sequence(sequence, prompt)
                    final_checkpoint.delete()
                    logger.info(f"[CHECKPOINT] Deleted checkpoint for completed sequence {sequence_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete checkpoint: {e}")

            # Compile final results
            elapsed = time.time() - start_time
            summary = [
                f"Task: {prompt}",
                f"Status: {sequence.progress_summary}",
                f"Time: {elapsed:.1f}s",
                "",
                "Results:"
            ]
            summary.extend(results)

            # Add page state summary
            if sequence.page_state.url:
                summary.append(f"\nFinal URL: {sequence.page_state.url}")

            if sequence.is_complete:
                successful = len([g for g in sequence.goals if g.status == GoalStatus.COMPLETED])
                console.print(f"\n[bold green]{'=' * 60}[/bold green]")
                console.print(f"[bold green]ALL TASKS COMPLETE[/bold green]")
                console.print(f"[green]Tasks: {successful}/{len(sequence.goals)} completed successfully[/green]")
                console.print(f"[green]Total Time: {elapsed:.1f}s[/green]")
                console.print(f"[bold green]{'=' * 60}[/bold green]")
                if resumed:
                    console.print(f"[dim](Resumed from checkpoint at goal {checkpoint.current_index + 1})[/dim]")
            else:
                failed = [g for g in sequence.goals if g.status == GoalStatus.FAILED]
                if failed:
                    summary.append(f"\nFailed goals: {[g.description for g in failed]}")
                # Save checkpoint for partial completion
                try:
                    partial_checkpoint = GoalSequenceCheckpoint.from_sequence(sequence, prompt)
                    partial_checkpoint.save()
                    console.print(f"\n[yellow]Checkpoint saved. Resume later by running the same prompt.[/yellow]")
                except Exception as e:
                    logger.warning(f"Failed to save partial checkpoint: {e}")

            # FINAL PROSPECT SUMMARY - The key output for SDRs
            # Shows all unique prospects collected across all goals
            total_prospects = prospect_collector.get_total_count()
            if total_prospects > 0 or prospect_collector.failures:
                prospect_summary = prospect_collector.generate_summary()
                console.print(prospect_summary)
                summary.append(prospect_summary)
            else:
                console.print(f"\n[dim]No prospects extracted. Try more specific search terms.[/dim]")

            self._finalize_goal_todos(sequence_id, sequence)
            return "\n".join(summary)

        finally:
            if 'sequence' in locals():
                self._finalize_goal_todos(sequence_id, locals().get('sequence'))
            # CRITICAL: Clean up all state after goal sequence to prevent state bleed
            # This ensures the next goal sequence starts fresh
            await self.cleanup_state()

    async def _run_single_goal(self, goal_prompt: str, full_prompt_with_context: str = None) -> str:
        """Execute a single goal (extracted for reuse in goal sequences).

        Args:
            goal_prompt: Clean goal description (used for template/command matching)
            full_prompt_with_context: Full prompt with context (used for LLM fallback)

        Execution order (deterministic first for Playwright MCP-like precision):
        0. Pre-validation - Check prompt is valid and safe
        1. Action templates - Pre-defined multi-step sequences for common operations
        2. Command parser - Deterministic execution for simple commands (navigate, click, type)
        3. Direct patterns - Fast-path for known services (Gmail, Maps, etc.)
        4. Standard execution - Full LLM-based execution (fallback)
        """
        # Reset stats to prevent accumulation across goals
        self.stats = {}

        # Use full prompt for LLM if provided, otherwise use goal_prompt
        llm_prompt = full_prompt_with_context or goal_prompt

        # 0. PRE-VALIDATION - Validate the goal before execution
        validation_result = self._validate_goal(goal_prompt)
        if not validation_result["valid"]:
            logger.warning(f"Goal validation failed: {validation_result['reason']}")
            return f"Goal validation failed: {validation_result['reason']}"

        # 0.5 MCP-SIMPLE - Super simple Playwright MCP-like execution for known sites
        # This runs FIRST because it's proven to work - just navigate, wait, snapshot, extract
        try:
            logger.info(f"[MCP-SIMPLE] Checking goal: {goal_prompt[:80]}...")
            mcp_simple_result = await self._try_mcp_simple(goal_prompt)
            if mcp_simple_result:
                logger.info(f"[MCP-SIMPLE] Success: {mcp_simple_result[:100]}...")
                return mcp_simple_result
            else:
                logger.info("[MCP-SIMPLE] No match, falling through to templates")
        except Exception as e:
            logger.warning(f"[MCP-SIMPLE] Handler failed: {e}", exc_info=True)

        # 1. ACTION TEMPLATES - Try pre-defined sequences first
        # Templates provide multi-step deterministic execution like Playwright MCP
        # Use CLEAN goal_prompt for template matching (no context bleeding)
        if TEMPLATES_AVAILABLE:
            try:
                template = find_template(goal_prompt)
                if template:
                    # Note: Template name is internal - don't expose to users
                    result = await execute_template(template, goal_prompt, self.mcp)
                    if result.get("success"):
                        formatted = result.get("formatted_output")
                        if formatted:
                            return formatted
                        # MANDATORY: Use extraction_summary if available (shows actual prospects)
                        if result.get("extraction_summary"):
                            return result["extraction_summary"]
                        # Fallback: show completion without internal details
                        return f"Completed {result['steps_executed']} steps successfully"
                    else:
                        logger.debug(f"Template execution had failures: {result}")
                        # Fall through to other methods
            except Exception as e:
                logger.debug(f"Template execution failed: {e}, trying other methods")

        # 2. COMMAND PARSER - Try deterministic execution for simple commands
        # This matches Playwright MCP's precision for single actions
        # Use CLEAN goal_prompt for command parsing
        if COMMAND_PARSER_AVAILABLE and can_execute_directly(goal_prompt):
            try:
                mcp_calls = get_mcp_calls(goal_prompt)
                if mcp_calls:
                    console.print(f"[dim cyan]>> Command parser: executing {len(mcp_calls)} action(s) directly[/dim cyan]")
                    results = []
                    for tool_name, params in mcp_calls:
                        # Execute the parsed command
                        result = await self._execute_mcp_call(tool_name, params)
                        results.append(str(result) if result else "OK")

                    # Take snapshot after command execution to confirm result
                    try:
                        snapshot = await self.mcp.call_tool('playwright_snapshot', {})
                        if snapshot:
                            results.append(f"Page state: {str(snapshot)[:500]}...")
                    except Exception:
                        pass

                    return f"Executed {len(mcp_calls)} action(s): {'; '.join(results[:3])}"
            except Exception as e:
                logger.debug(f"Command parser execution failed: {e}, falling back to other methods")

        # 3. DIRECT PATTERNS - Fast-path for known services (Gmail, Maps, FB Ads, etc.)
        # This catches patterns the command parser and templates might miss
        # Use CLEAN goal_prompt for direct patterns
        if hasattr(self, '_try_direct_patterns'):
            try:
                direct_result = await self._try_direct_patterns(goal_prompt)
                if direct_result:
                    return direct_result
            except Exception as e:
                logger.debug(f"Direct patterns failed: {e}, falling back to standard execution")

        # 4. STANDARD EXECUTION - Full LLM-based execution (fallback)
        # Use llm_prompt which has context for better LLM understanding
        return await self._execute_with_streaming(llm_prompt)

    def _extract_goal_summary(self, result: str, goal: str) -> str:
        """Extract a meaningful summary from a goal result.

        Makes output user-friendly by highlighting what was actually accomplished.
        Shows URLs and actual extracted data instead of vague messages.
        """
        import re
        result_lower = result.lower() if result else ""
        goal_lower = goal.lower()

        # Extract URLs from result text - always show actual URLs found
        url_pattern = r'(https?://[^\s\)\]]+)'
        urls = re.findall(url_pattern, result)
        final_url = urls[-1] if urls else None

        # FB Ads results - show advertiser and URL
        if 'prospect:' in result_lower and ('advertiser' in result_lower or 'fb ads' in goal_lower or 'facebook' in goal_lower):
            # Result format: "Prospect: NAME | URL (Found N total)"
            # Extract the prospect line
            prospect_match = re.search(r'Prospect:\s*([^|]+)\|\s*([^\(]+)', result, re.IGNORECASE)
            if prospect_match:
                name = prospect_match.group(1).strip()
                url = prospect_match.group(2).strip()
                count_match = re.search(r'Found\s+(\d+)\s+total', result)
                count = count_match.group(1) if count_match else "1"
                return f"Found {count} FB advertiser(s): {name}\n  URL: {url}"
            # Fallback: try to extract count at least
            count_match = re.search(r'found\s+(\d+)\s+(?:advertiser|prospect)', result_lower)
            if count_match:
                count = count_match.group(1)
                return f"Found {count} FB advertiser(s) at {final_url or 'FB Ads Library'}"
            return f"Found FB advertiser(s) at {final_url or 'FB Ads Library'}"

        # Reddit results - show user/post URL
        if 'reddit' in goal_lower:
            # Check if we have prospect data
            if 'prospect:' in result_lower or 'user' in result_lower or 'u/' in result_lower:
                # Extract Reddit user profile URL
                reddit_url_match = re.search(r'(https?://(?:www\.)?reddit\.com/user/[^\s\)]+)', result)
                if reddit_url_match:
                    return f"Found Reddit user\n  URL: {reddit_url_match.group(1)}"
                return f"Found Reddit user(s) at {final_url or 'reddit.com'}"
            if 'post' in result_lower or 'r/' in result_lower:
                return f"Found Reddit post(s) at {final_url or 'reddit.com'}"
            return f"Opened Reddit: {final_url or 'reddit.com'}"

        # LinkedIn results - show profile URL
        if 'linkedin' in goal_lower:
            if 'prospect' in result_lower or 'profile' in result_lower or 'linkedin.com/in/' in result_lower:
                linkedin_url_match = re.search(r'(https?://(?:www\.)?linkedin\.com/in/[^\s\)]+)', result)
                if linkedin_url_match:
                    return f"Found LinkedIn prospect\n  URL: {linkedin_url_match.group(1)}"
                return f"Found LinkedIn prospect(s) at {final_url or 'linkedin.com'}"
            return f"Opened LinkedIn: {final_url or 'linkedin.com'}"

        # Gmail results - show final URL
        if 'gmail' in goal_lower:
            if 'mail.google.com' in result_lower or 'inbox' in result_lower:
                return f"Opened Gmail\n  URL: {final_url or 'https://mail.google.com'}"
            return f"Gmail: {final_url or 'mail.google.com'}"

        # Zoho results - show final URL
        if 'zoho' in goal_lower:
            if 'mail.zoho' in result_lower:
                return f"Opened Zoho Mail\n  URL: {final_url or 'https://mail.zoho.com'}"
            return f"Zoho: {final_url or 'mail.zoho.com'}"

        # Google Maps results - show listing URL
        if 'google maps' in goal_lower or 'maps' in goal_lower:
            if 'business' in result_lower or 'listing' in result_lower:
                maps_url_match = re.search(r'(https?://(?:www\.)?google\.com/maps/[^\s\)]+)', result)
                if maps_url_match:
                    return f"Found Google Maps listing\n  URL: {maps_url_match.group(1)}"
                return f"Found Google Maps listing at {final_url or 'google.com/maps'}"
            return f"Opened Google Maps: {final_url or 'google.com/maps'}"

        # Template execution - include URL if available
        if "template '" in result_lower:
            template_match = re.search(r"template '([^']+)'", result_lower)
            template_name = template_match.group(1) if template_match else "template"
            if final_url:
                return f"Ran {template_name}\n  URL: {final_url}"
            return f"Ran {template_name}"

        # Extraction summary format (from action_templates.py)
        if 'prospect:' in result_lower and '|' in result:
            # This is a formatted extraction_summary - return as-is but add URL if missing
            if final_url and final_url not in result:
                return f"{result.strip()}\n  Final URL: {final_url}"
            return result.strip()

        # Generic fallback - show URL if available
        if final_url:
            # Extract first 60 chars of non-URL content
            text_without_urls = re.sub(url_pattern, '', result).strip()
            clean = re.sub(r'\s+', ' ', text_without_urls[:60]).strip()
            summary = (clean + "..." if len(text_without_urls) > 60 else clean) if clean else "Completed"
            return f"{summary}\n  URL: {final_url}"

        # No URL found - just clean text
        clean = re.sub(r'\s+', ' ', result[:60]).strip()
        return clean + "..." if len(result) > 60 else clean

    def _validate_goal(self, goal_prompt: str) -> Dict[str, Any]:
        """Pre-validate a goal before execution.

        Returns:
            Dict with 'valid' (bool) and optionally 'reason' (str) if invalid
        """
        if not goal_prompt or not goal_prompt.strip():
            return {"valid": False, "reason": "Empty goal prompt"}

        # Check for minimum length
        if len(goal_prompt.strip()) < 3:
            return {"valid": False, "reason": "Goal prompt too short"}

        # Check for obviously malformed prompts
        if goal_prompt.strip() in ['...', '???', '!!!', '---']:
            return {"valid": False, "reason": "Invalid goal format"}

        return {"valid": True}

    async def _execute_mcp_call(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """
        Execute a single MCP tool call with resilience systems.

        Includes:
        - Retry with exponential backoff (2s, 4s, 8s, max 30s)
        - Self-healing on failure (alternative selectors, timing adjustments)
        - Challenge resolution for navigation (Cloudflare, CAPTCHA detection)
        """
        # Normalize tool name (remove 'playwright_' or 'browser_' prefix)
        actual_tool = tool_name.replace('playwright_', '').replace('browser_', '')

        # Map to actual MCP tool names (playwright_* format used by agent)
        tool_mapping = {
            'navigate': 'playwright_navigate',
            'click': 'playwright_click',
            'type': 'playwright_type',
            'snapshot': 'playwright_snapshot',
            'screenshot': 'playwright_screenshot',
            'take_screenshot': 'playwright_screenshot',
            'wait': 'playwright_wait',
            'wait_for': 'playwright_wait',
            'press_key': 'playwright_press_key',
            'hover': 'playwright_hover',
            'select_option': 'playwright_select_option',
            'evaluate': 'playwright_evaluate',
        }

        mapped_tool = tool_mapping.get(actual_tool, tool_name)

        # Handle special cases
        if mapped_tool == 'playwright_snapshot':
            return await self.mcp.call_tool('playwright_snapshot', {})

        # === RESILIENT EXECUTION WITH RETRY AND SELF-HEALING ===
        max_retries = 3
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                # Execute the tool call
                result = await self.mcp.call_tool(mapped_tool, params)

                # Check for navigation - trigger Cloudflare/challenge detection
                if mapped_tool == 'playwright_navigate' and CHALLENGE_RESOLVER_AVAILABLE:
                    await self._check_and_resolve_challenges(params.get('url', ''))

                # Record success for self-healing learning
                if SELF_HEALING_AVAILABLE and self_healing:
                    self_healing.record_success(
                        {'function': mapped_tool, 'arguments': params},
                        {'action': 'direct_execution'}
                    )

                return result

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                logger.warning(f"[RESILIENCE] MCP call {mapped_tool} failed (attempt {attempt}/{max_retries}): {e}")

                # Check if error is retryable
                is_retryable = any(kw in error_str for kw in [
                    'timeout', 'network', 'connection', 'rate limit',
                    'element not found', 'selector', 'not visible'
                ])

                if not is_retryable:
                    logger.debug(f"[RESILIENCE] Error not retryable, failing immediately")
                    raise

                # Try self-healing if available
                if SELF_HEALING_AVAILABLE and self_healing and attempt < max_retries:
                    try:
                        context = {
                            'function': mapped_tool,
                            'arguments': params,
                            'error': str(e)
                        }
                        healing_strategy = await self_healing.analyze_failure(e, context, attempt)

                        if healing_strategy:
                            logger.info(f"[RESILIENCE] Applying healing strategy: {healing_strategy.get('action', 'unknown')}")

                            # Apply modifications if suggested
                            if 'modifications' in healing_strategy:
                                params = {**params, **healing_strategy['modifications']}

                            # Execute any healing steps
                            if 'steps' in healing_strategy:
                                await self._execute_healing_steps(healing_strategy['steps'])
                    except Exception as heal_error:
                        logger.debug(f"[RESILIENCE] Self-healing failed: {heal_error}")

                # Exponential backoff before retry
                if attempt < max_retries:
                    delay = min(2.0 * (2 ** (attempt - 1)), 30.0)  # 2s, 4s, 8s... max 30s
                    logger.debug(f"[RESILIENCE] Waiting {delay}s before retry {attempt + 1}")
                    await asyncio.sleep(delay)

        # All retries exhausted - record failure for learning
        if SELF_HEALING_AVAILABLE and self_healing:
            self_healing.record_failure(str(last_error), {'function': mapped_tool, 'arguments': params})

        raise last_error or Exception(f"MCP call {mapped_tool} failed after {max_retries} attempts")

    async def _check_and_resolve_challenges(self, url: str) -> bool:
        """
        Check for and resolve Cloudflare/CAPTCHA challenges after navigation.

        For bot-protected sites (Google, GitHub, Reddit, etc.):
        - Automatically switches to headful mode for user CAPTCHA solving
        - Uses extended timeouts for challenge resolution
        - Waits for user interaction when needed
        """
        # Check if this is a known bot-protected site
        site_profile = None
        if SITE_PROFILES_AVAILABLE and get_site_profile:
            site_profile = get_site_profile(url)
            if site_profile.requires_headful:
                logger.info(f"[RESILIENCE] Bot-protected site detected: {site_profile.domain}")
                # Switch to headful mode if we have browser access
                await self._switch_to_headful_if_needed(url, site_profile)

        if not CHALLENGE_RESOLVER_AVAILABLE or not get_autonomous_resolver:
            return True

        try:
            # Get page content to detect challenges
            snapshot = await self.mcp.call_tool('playwright_snapshot', {})
            page_content = snapshot.get('snapshot', '') if isinstance(snapshot, dict) else str(snapshot)

            # Quick check for common challenge indicators
            challenge_indicators = [
                'just a moment', 'checking your browser', 'cloudflare',
                'cf-browser-verification', 'challenge-running',
                'recaptcha', 'hcaptcha', 'verify you are human'
            ]

            content_lower = page_content.lower() if page_content else ''
            has_challenge = any(indicator in content_lower for indicator in challenge_indicators)

            if has_challenge:
                logger.info(f"[RESILIENCE] Challenge detected on {url}, attempting resolution...")

                # For bot-protected sites, use extended timeout and allow user intervention
                max_time = 120 if (site_profile and site_profile.captcha_likely) else 60

                resolver = get_autonomous_resolver(mcp_client=self.mcp)
                result = await resolver.resolve(
                    page_content=page_content,
                    url=url,
                    max_time_seconds=max_time
                )

                if result.success:
                    logger.info(f"[RESILIENCE] Challenge resolved via: {result.resolution_strategy}")
                    return True
                else:
                    logger.warning(f"[RESILIENCE] Challenge resolution failed, continuing anyway")
                    return result.should_continue

            # Apply extra wait time for bot-protected sites
            if site_profile and site_profile.extra_wait_seconds > 0:
                logger.debug(f"[RESILIENCE] Extra wait {site_profile.extra_wait_seconds}s for {site_profile.domain}")
                await asyncio.sleep(site_profile.extra_wait_seconds)

            return True

        except Exception as e:
            logger.debug(f"[RESILIENCE] Challenge check error: {e}")
            return True  # Continue anyway

    async def _switch_to_headful_if_needed(self, url: str, site_profile) -> None:
        """Switch browser to headful mode for bot-protected sites requiring user CAPTCHA solving."""
        try:
            # Try to access the browser through various possible attributes
            browser = getattr(self, 'browser', None) or getattr(self, '_browser', None)

            if browser and hasattr(browser, 'show_browser'):
                if hasattr(browser, 'headless') and browser.headless:
                    logger.info(f"[RESILIENCE] Switching to HEADFUL mode for {site_profile.domain}")
                    logger.info(f"[RESILIENCE] User may need to solve CAPTCHA manually")
                    console.print(f"[yellow]Switching to visible browser for {site_profile.domain}[/yellow]")
                    console.print(f"[dim]Please solve any CAPTCHA that appears...[/dim]")
                    await browser.show_browser()
            elif hasattr(self, 'mcp') and self.mcp:
                # Try via MCP - some browsers support headful mode switching
                try:
                    await self.mcp.call_tool('browser_show', {})
                except Exception:
                    pass  # Not all MCP clients support this

        except Exception as e:
            logger.debug(f"[RESILIENCE] Could not switch to headful mode: {e}")

    async def _execute_healing_steps(self, steps: list) -> None:
        """Execute healing steps suggested by self-healing system."""
        for step in steps:
            try:
                if step.get('type') == 'wait' or 'wait' in step:
                    duration = step.get('duration', step.get('wait', 1000)) / 1000.0
                    await asyncio.sleep(duration)
                elif step.get('function'):
                    func_name = step['function']
                    args = step.get('arguments', {})
                    await self.mcp.call_tool(func_name, args)
            except Exception as e:
                logger.debug(f"[RESILIENCE] Healing step failed: {e}")

    async def _try_multi_agent_execution(self, prompt: str) -> Optional[str]:
        """
        Execute complex multi-step task using multi-agent system.

        This method creates a swarm of specialized agents to handle complex tasks in parallel:
        - ResearcherAgent: Web research and data gathering
        - ExtractorAgent: Data extraction from multiple sources
        - ValidatorAgent: Data validation and quality checking
        - AnalystAgent: Data analysis and insight generation
        - WriterAgent: Content generation and formatting

        Args:
            prompt: User prompt to execute

        Returns:
            Result string if executed successfully, None if multi-agent not suitable
        """
        if not MULTI_AGENT_AVAILABLE:
            return None

        if not self._should_use_multi_agent(prompt):
            return None

        logger.info("[MULTI-AGENT] Starting multi-agent execution")
        console.print("[cyan]Using multi-agent system for complex task...[/cyan]")

        try:
            # Extract URLs from prompt
            import re
            url_pattern = r'https?://[^\s]+'
            urls = re.findall(url_pattern, prompt)

            # Determine task breakdown based on prompt
            lower = prompt.lower()
            tasks = []

            # Research tasks
            if 'research' in lower or 'find' in lower or 'gather' in lower:
                for i, url in enumerate(urls[:5]):  # Limit to 5 URLs for performance
                    tasks.append({
                        'role': AgentRole.RESEARCHER,
                        'description': f"Research and gather information from {url}",
                        'metadata': {
                            'urls': [url],
                            'query': prompt,
                            'depth': 2
                        }
                    })

            # Extraction tasks
            if 'extract' in lower or 'scrape' in lower or 'get data' in lower:
                extract_type = 'contacts' if 'contact' in lower or 'email' in lower else 'all'
                if urls:
                    # Use batch extraction for efficiency
                    tasks.append({
                        'role': AgentRole.EXTRACTOR,
                        'description': f"Extract data from {len(urls)} URLs",
                        'metadata': {
                            'urls': urls,
                            'extract_type': extract_type,
                            'batch': True
                        }
                    })

            # Validation tasks
            if 'validate' in lower or 'verify' in lower or 'check' in lower:
                tasks.append({
                    'role': AgentRole.VALIDATOR,
                    'description': "Validate and clean extracted data",
                    'metadata': {
                        'validation_type': 'all',
                        'deduplicate': True
                    }
                })

            # Analysis tasks
            if 'analyze' in lower or 'compare' in lower or 'insights' in lower:
                tasks.append({
                    'role': AgentRole.ANALYST,
                    'description': "Analyze data and generate insights",
                    'metadata': {
                        'analysis_type': 'insights',
                        'output_format': 'markdown'
                    }
                })

            # Create orchestrator
            orchestrator = AgentOrchestrator(
                orchestrator_id=f"task_{hashlib.sha256(prompt.encode()).hexdigest()[:8]}",
                max_agents=min(len(tasks) + 2, 10)  # Cap at 10 agents
            )

            await orchestrator.start()

            # Submit tasks with graceful fallback
            task_ids = []
            for task in tasks:
                try:
                    task_id = await orchestrator.submit_task(
                        description=task['description'],
                        priority=TaskPriority.NORMAL,
                        required_role=task['role'],
                        metadata=task['metadata']
                    )
                    task_ids.append(task_id)
                except Exception as e:
                    logger.warning(f"Failed to submit task: {e}")
                    # Continue with other tasks

            if not task_ids:
                logger.warning("[MULTI-AGENT] No tasks were submitted successfully, falling back")
                await orchestrator.stop()
                return None

            console.print(f"[dim cyan]Submitted {len(task_ids)} tasks to agent swarm...[/dim cyan]")

            # Wait for results with timeout and graceful degradation
            results = []
            timeout_per_task = 120.0  # 2 minutes per task

            for i, task_id in enumerate(task_ids):
                try:
                    console.print(f"[dim]Waiting for task {i+1}/{len(task_ids)}...[/dim]")
                    result = await orchestrator.get_task_result(task_id, timeout=timeout_per_task)

                    if result:
                        results.append(result)
                    else:
                        logger.warning(f"Task {task_id} timed out after {timeout_per_task}s")
                        console.print(f"[yellow]Task {i+1} timed out, continuing...[/yellow]")

                except Exception as e:
                    logger.error(f"Error getting task result: {e}")
                    console.print(f"[yellow]Task {i+1} failed: {str(e)[:100]}[/yellow]")

            # Stop orchestrator
            await orchestrator.stop()

            if not results:
                logger.warning("[MULTI-AGENT] No results obtained, falling back to standard execution")
                return None

            # Aggregate results
            summary_parts = [f"Multi-agent execution completed {len(results)}/{len(task_ids)} tasks successfully:\n"]

            for i, result in enumerate(results):
                if isinstance(result, dict):
                    summary = result.get('summary', str(result)[:200])
                    summary_parts.append(f"{i+1}. {summary}")
                else:
                    summary_parts.append(f"{i+1}. {str(result)[:200]}")

            # Get orchestrator final status
            status = orchestrator.get_status()
            summary_parts.append(f"\nAgent Swarm Status:")
            summary_parts.append(f"- Total agents: {status['total_agents']}")
            summary_parts.append(f"- Tasks processed: {status['total_tasks_processed']}")
            summary_parts.append(f"- Tasks failed: {status['total_tasks_failed']}")

            final_summary = "\n".join(summary_parts)
            logger.info("[MULTI-AGENT] Execution completed successfully")

            return final_summary

        except Exception as e:
            logger.error(f"Multi-agent execution failed: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            console.print(f"[yellow]Multi-agent system error: {str(e)[:100]}[/yellow]")
            # Return None to trigger graceful fallback to standard execution
            return None


    async def _execute_with_streaming(self, prompt: str) -> str:
        """Execute with live streaming output."""
        # Generate task ID for resource limiting
        task_id = hashlib.sha256(prompt.encode()).hexdigest()[:16]

        # Register current process PID with resource limiter
        if self.resource_limiter:
            try:
                import os
                current_pid = os.getpid()
                self.resource_limiter.register_task_pid(task_id, current_pid)
            except Exception as e:
                logger.debug(f"Could not register task PID: {e}")

        # Forever mode tasks run indefinitely - NO timeout
        # Regular one-shot tasks have optional timeout
        timeout = None if self._forever_mode else self.task_timeout

        # Wrap execution with global task timeout to prevent infinite loops (only for one-shot tasks)
        try:
            if self.resource_limiter:
                async with self.resource_limiter.async_task_context(task_id) as handle:
                    if timeout:
                        return await asyncio.wait_for(
                            self._execute_with_streaming_impl(prompt, handle),
                            timeout=timeout
                        )
                    else:
                        return await self._execute_with_streaming_impl(prompt, handle)
            else:
                if timeout:
                    return await asyncio.wait_for(
                        self._execute_with_streaming_impl(prompt, None),
                        timeout=timeout
                    )
                else:
                    return await self._execute_with_streaming_impl(prompt, None)
        except asyncio.TimeoutError:
            # Task exceeded global timeout - gracefully handle (only for one-shot tasks)
            timeout_mins = timeout / 60 if timeout else 0
            error_msg = f"Task exceeded global timeout of {timeout_mins:.1f} minutes. Saving state and stopping."
            logger.error(error_msg)
            console.print(f"[red]⏱ {error_msg}[/red]")

            # Save current state
            try:
                self.memory.save()
                if self.memory_arch:
                    self.memory_arch.save_episode(
                        task_prompt=prompt,
                        outcome="Timeout - task exceeded global limit",
                        success=False,
                        duration_seconds=timeout,
                        tags=['timeout', 'error']
                    )
            except Exception as e:
                logger.warning(f"Failed to save state on timeout: {e}")

            return f"Task timed out after {timeout_mins:.1f} minutes. Completed {self.stats.get('tool_calls', 0)} tool calls across {self.stats.get('iterations', 0)} iterations."

    async def _execute_with_streaming_impl(self, prompt: str, resource_handle=None) -> str:
        """Execute with live streaming output (implementation)."""
        # Check resources at start of execution
        if self.iteration % 5 == 0:
            issues = self.resource_monitor.check()
            if issues:
                logger.warning(f"Resource issues at iteration {self.iteration}: {issues}")
                self.stats['resource_warnings'] = self.stats.get('resource_warnings', 0) + 1

        # Describe mode can change per request (e.g., inside loops)
        self._set_describe_mode(prompt)
        self._describe_retry_done = False  # reset per execution
        self._execution_log.clear()
        self._task_start_time = datetime.now()
        self._next_health_check_time = datetime.now()
        self._last_issues = []

        # Initialize checkpoint time for forever mode
        if self._forever_mode and self._last_checkpoint_time is None:
            self._last_checkpoint_time = datetime.now()

        # DIRECT MODE: Follow exact directions like Playwright MCP
        # Skip all routing layers and go straight to ReAct loop for literal execution
        # This is the default behavior - follows the user's exact instructions
        direct_mode = getattr(self, 'direct_mode', True)  # Default to True for Playwright MCP behavior
        if direct_mode:
            logger.info("[DIRECT MODE] Following exact directions - bypassing routing")
            return await self._react_loop(prompt, resource_handle)

        # Legacy routing (only if direct_mode=False)
        # Try file shortcuts first (fast path for simple file operations)
        file_result = await self._try_file_shortcuts(prompt)
        if file_result:
            return file_result

        # 0. MULTI-AGENT SYSTEM - try FIRST for complex multi-step tasks with multiple URLs
        # Handles tasks that benefit from parallel agent execution (research + extract + validate + analyze)
        # This runs before strategic planning to catch tasks better suited for agent swarm
        multi_agent_result = await self._try_multi_agent_execution(prompt)
        if multi_agent_result:
            return multi_agent_result

        # 1. STRATEGIC PLANNING - try FIRST for complex multi-step browser tasks
        # For complex tasks, create a step-by-step plan before execution
        # This MUST run before web shortcuts to catch "research X" type tasks
        if STRATEGIC_PLANNER_AVAILABLE and self.strategic_planner:
            use_planning = should_use_kimi_planning(prompt, self.config)
            logger.debug(f"should_use_kimi_planning('{prompt[:50]}...'): {use_planning}")
            if use_planning:
                plan_result = await self._try_strategic_plan(prompt)
                if plan_result:
                    return plan_result
                # If planning failed, fall through to other methods
                logger.debug("Strategic plan failed or returned None, trying other methods")

        # 2. Simple web shortcuts (quick searches, single page visits)
        # NOTE: This is AFTER strategic planning to ensure complex tasks get planned
        web_result = await self._try_web_shortcuts(prompt)
        if web_result:
            return web_result

        # 3. Try complex multi-step handler (breaks down complex tasks - legacy)
        complex_result = await self._try_complex_workflow(prompt)
        if complex_result:
            return complex_result

        # 4. Try multi-step click handler (specialized for "go to X, click Y" patterns)
        click_result = await self._try_click_through(prompt)
        if click_result:
            return click_result

        # 5. DIRECT PATTERNS: Fast-path for single-goal known patterns (Gmail, Maps, etc.)
        # This must run BEFORE capability routing to prevent mismatches
        # Examples: "Go to Gmail", "Open Google Maps", "Search Facebook Ads"
        try:
            if hasattr(self, '_try_direct_patterns'):
                direct_result = await self._try_direct_patterns(prompt)
                if direct_result:
                    return direct_result
        except Exception as e:
            logger.debug(f"Direct patterns check failed: {e}")

        # 6. Try business capability auto-routing for simpler tasks
        result = await self._try_capability(prompt)
        if result:
            return result

        # 7. Try fast executor path
        result = await self._try_executor(prompt)
        if result:
            return result

        # 8. Full ReAct loop with streaming (fallback)
        return await self._react_loop(prompt, resource_handle)

    # =========================================================================
    # Prompt parsing methods (delegate to PromptProcessor)
    # =========================================================================

    def _parse_duration(self, prompt: str) -> Optional[timedelta]:
        """Parse duration from prompt. Delegates to PromptProcessor."""
        return self.prompt_processor.parse_duration(prompt)

    def _parse_loops(self, prompt: str) -> Optional[int]:
        """Parse loop count from prompt. Delegates to PromptProcessor."""
        return self.prompt_processor.parse_loops(prompt)

    def _parse_indefinite(self, prompt: str) -> bool:
        """Check if user wants indefinite/forever loop. Delegates to PromptProcessor."""
        return self.prompt_processor.parse_indefinite(prompt)

    def _detect_and_set_forever_mode(self, prompt: str) -> None:
        """
        Detect forever mode patterns from natural language and set _forever_mode flag.
        Delegates pattern detection to PromptProcessor.
        """
        if self.prompt_processor.detect_forever_mode(prompt):
            self._forever_mode = True
            logger.info(f"Forever mode detected from prompt: '{prompt[:100]}...'")
        else:
            self._forever_mode = False

    def _parse_schedule(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Parse scheduled recurring task patterns. Delegates to PromptProcessor."""
        return self.prompt_processor.parse_schedule(prompt)

    def _clean_prompt(self, prompt: str) -> str:
        """Remove scheduling/timing directives from prompt. Delegates to PromptProcessor."""
        return self.prompt_processor.clean_prompt(prompt)

    # =========================================================================
    # Loop execution methods
    # =========================================================================

    async def _timed_loop(self, prompt: str, duration: timedelta) -> str:
        """Execute a loop for a specified duration with enterprise features.

        ENTERPRISE FEATURES:
        - Circuit breaker with exponential backoff
        - Per-iteration timeout (prevents hanging)
        - Automatic resource cleanup every N iterations
        - Browser recycling to prevent memory leaks
        - Checkpoint every 5 iterations for crash recovery
        """
        results = deque(maxlen=100)  # Memory-safe: automatically keeps only last 100 results
        collected_data = []
        end = datetime.now() + duration
        i = 0

        # Create/resume task state for checkpointing
        task_id = hashlib.sha256(prompt.encode()).hexdigest()[:16]

        if ForeverTaskState:
            state = ForeverTaskState.load(task_id)
            if state and state.status == "running" and state.task_type == "timed_loop":
                i = state.processed_items
                collected_data = state.results.copy() if state.results else []
                console.print(f"\n[bold green]>>> Resuming from checkpoint (iteration {i})[/bold green]")
            else:
                i = 0
                state = ForeverTaskState.create(task_id, "timed_loop")
        else:
            i = 0
            state = None

        console.print(f"\n[bold yellow]>>> Timed loop ({duration.total_seconds()/60:.1f} min) - Press Ctrl+C to stop[/bold yellow]")
        console.print(f"[dim]Task ID: {task_id} (checkpoints saved automatically)[/dim]")

        # Forever mode already set in run() - timed loops run until duration expires
        self._forever_mode = True
        self._last_checkpoint_time = datetime.now()

        # Start health monitoring
        health_writer = None
        if HEALTH_MONITORING_AVAILABLE and HealthWriter:
            health_writer = HealthWriter()
            health_writer.update_activity(f"Timed loop: {prompt[:50]}")
            health_writer.start()
            logger.info("[HEALTH] Health monitoring started for timed loop")

        # ENTERPRISE: Circuit breaker for resilience
        if CircuitBreaker:
            circuit = CircuitBreaker(
                name=f"timed_{task_id}",
                failure_threshold=5,
                recovery_threshold=3,
                initial_backoff=10.0,
                max_backoff=300.0,
                backoff_multiplier=2.0
            )
        else:
            circuit = None

        # Resource management settings
        resource_check_interval = 10  # Check resources every N iterations
        browser_recycle_interval = 100  # Recycle browser every N iterations
        per_iteration_timeout = 300  # 5 minute timeout per iteration (prevents hanging)

        try:
            while datetime.now() < end:
                i += 1
                if state:
                    state.processed_items = i

                # Periodic resource health check
                if i % resource_check_interval == 0:
                    try:
                        issues = self.resource_monitor.check()
                        if issues:
                            logger.warning(f"Resource issues detected at iteration {i}: {issues}")
                            console.print(f"[yellow]>>> Resource warning (iteration {i}): {', '.join(issues)}[/yellow]")
                            if any(keyword in str(issues).lower() for keyword in ['critical', 'extremely high', 'out of']):
                                console.print(f"[yellow]>>> Critical resources - forcing cleanup[/yellow]")
                                if cleanup_resources_between_iterations:
                                    collected_data = cleanup_resources_between_iterations(i, collected_data, 2000, True)
                    except Exception as e:
                        logger.debug(f"Resource check failed: {e}")

                    # Resource cleanup between iterations
                    if cleanup_resources_between_iterations:
                        collected_data = cleanup_resources_between_iterations(i, collected_data, 5000)

                # Periodic browser recycling to prevent memory leaks
                if i % browser_recycle_interval == 0 and recycle_browser_if_needed:
                    try:
                        # CRITICAL FIX: Add timeout to prevent deadlock (audit fix)
                        await asyncio.wait_for(
                            recycle_browser_if_needed(self.mcp, i, browser_recycle_interval, state),
                            timeout=60.0  # 60 second timeout for browser recycle
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Browser recycle timed out at iteration {i} - continuing without recycle")
                    except Exception as e:
                        logger.warning(f"Browser recycle failed: {e}")

                # Circuit breaker check
                if circuit and not circuit.should_allow():
                    backoff = circuit.get_backoff_seconds()
                    console.print(f"[red]>>> Circuit OPEN - backing off {backoff:.0f}s...[/red]")
                    await asyncio.sleep(backoff)
                    continue

                console.print(f"\n[cyan]━━━ Loop {i} ━━━[/cyan]")

                # Update health monitoring
                if health_writer:
                    health_writer.update_activity(f"Iteration {i}: {prompt[:40]}")
                    health_writer.increment_iterations()

                try:
                    # Per-iteration timeout to prevent hanging
                    try:
                        result = await asyncio.wait_for(
                            self._execute_with_streaming(prompt),
                            timeout=per_iteration_timeout
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Iteration {i} timed out after {per_iteration_timeout}s")
                        if circuit:
                            circuit.record_failure(f"Timeout after {per_iteration_timeout}s")
                        if health_writer:
                            health_writer.increment_errors()
                        console.print(f"[yellow]>>> Iteration timed out, continuing...[/yellow]")
                        continue

                    # Append to deque (automatically maintains 100-item limit)
                    results.append(result)

                    # Extract any structured data
                    data = self._extract_data(result)
                    if data:
                        collected_data.extend(data)
                        # Save overflow to disk before trimming
                        if len(collected_data) > 5000:
                            overflow_path = self._save_results(collected_data[:-2500], f"{prompt}_overflow_{i}")
                            console.print(f"[dim]Saved overflow to {overflow_path}[/dim]")
                            collected_data = collected_data[-2500:]
                        console.print(f"[dim]Collected: {len(collected_data)} items total[/dim]")

                    # Record success in circuit breaker
                    if circuit:
                        circuit.record_success()

                    # Checkpoint every 5 iterations
                    if state and i % 5 == 0:
                        state.results = collected_data[-100:]  # Keep last 100
                        state.checkpoint({"last_result": str(result)[:500], "total_loops": i})
                        console.print(f"[dim green]+ Checkpoint saved (iteration {i})[/dim green]")

                    remaining = (end - datetime.now()).total_seconds() / 60
                    console.print(f"[dim]{remaining:.1f} min left[/dim]")
                    await asyncio.sleep(2)

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(f"Loop error: {e}")

                    # Record failure in circuit breaker
                    if circuit:
                        circuit.record_failure(str(e))

                    # Update health monitoring
                    if health_writer:
                        health_writer.increment_errors()
                        health_writer.set_status("error")

                    if state:
                        state.errors.append({"iteration": i, "error": str(e)[:200], "timestamp": datetime.now().isoformat()})
                        state.errors = state.errors[-50:]

                    # Display error with circuit breaker status
                    if circuit:
                        status = circuit.get_status()
                        console.print(f"[red]Error: {str(e)[:100]}. Circuit: {status['state']} ({status['failures']} failures)[/red]")
                    else:
                        console.print(f"[red]Error: {str(e)[:100]}. Retrying in 5s...[/red]")
                        await asyncio.sleep(5)

        except KeyboardInterrupt:
            console.print(f"\n[yellow]>>> Stopped by user after {i} loops[/yellow]")
            if state:
                state.status = "paused"
                state.results = collected_data[-100:]
                state.checkpoint({"stopped": "user_interrupt"})

        finally:
            # Stop health monitoring
            if health_writer:
                health_writer.stop()
                logger.info("[HEALTH] Health monitoring stopped for timed loop")

            # Reset forever mode
            self._forever_mode = False
            self._last_checkpoint_time = None

        # Save collected data
        saved_path = None
        if collected_data:
            saved_path = self._save_results(collected_data, prompt)

        self.memory.save()

        summary = f"Completed {i} loops."
        if saved_path:
            summary += f"\nSaved {len(collected_data)} items to: {saved_path}"
        summary += f"\n\nLast: {results[-1] if results else 'None'}"
        return summary

    async def _counted_loop(self, prompt: str, count: int) -> str:
        """Execute a loop for a specified number of iterations with enterprise features.

        ENTERPRISE FEATURES:
        - Circuit breaker with exponential backoff
        - Per-iteration timeout (prevents hanging)
        - Automatic resource cleanup every N iterations
        - Browser recycling to prevent memory leaks
        - Checkpoint every 5 iterations for crash recovery
        """
        results = deque(maxlen=100)  # Memory-safe: automatically keeps only last 100 results
        collected_data = []

        # Create/resume task state for checkpointing
        task_id = hashlib.sha256(prompt.encode()).hexdigest()[:16]

        if ForeverTaskState:
            state = ForeverTaskState.load(task_id)
            if state and state.status == "running" and state.task_type == "counted_loop":
                i = state.processed_items
                collected_data = state.results.copy() if state.results else []
                console.print(f"\n[bold green]>>> Resuming from checkpoint (iteration {i})[/bold green]")
            else:
                i = 0
                state = ForeverTaskState.create(task_id, "counted_loop")
        else:
            i = 0
            state = None

        console.print(f"\n[bold yellow]>>> Counted loop ({count} iterations) - Press Ctrl+C to stop[/bold yellow]")
        console.print(f"[dim]Task ID: {task_id} (checkpoints saved automatically)[/dim]")

        # Forever mode already set in run() - counted loops run until count reached
        self._forever_mode = True
        self._last_checkpoint_time = datetime.now()

        # ENTERPRISE: Circuit breaker for resilience
        if CircuitBreaker:
            circuit = CircuitBreaker(
                name=f"counted_{task_id}",
                failure_threshold=5,
                recovery_threshold=3,
                initial_backoff=10.0,
                max_backoff=300.0,
                backoff_multiplier=2.0
            )
        else:
            circuit = None

        # Resource management settings
        resource_check_interval = 10  # Check resources every N iterations
        browser_recycle_interval = 100  # Recycle browser every N iterations
        per_iteration_timeout = 300  # 5 minute timeout per iteration (prevents hanging)

        try:
            while i < count:
                i += 1
                if state:
                    state.processed_items = i

                # Periodic resource health check
                if i % resource_check_interval == 0:
                    try:
                        issues = self.resource_monitor.check()
                        if issues:
                            logger.warning(f"Resource issues detected at iteration {i}: {issues}")
                            console.print(f"[yellow]>>> Resource warning (iteration {i}): {', '.join(issues)}[/yellow]")
                            if any(keyword in str(issues).lower() for keyword in ['critical', 'extremely high', 'out of']):
                                console.print(f"[yellow]>>> Critical resources - forcing cleanup[/yellow]")
                                if cleanup_resources_between_iterations:
                                    collected_data = cleanup_resources_between_iterations(i, collected_data, 2000, True)
                    except Exception as e:
                        logger.debug(f"Resource check failed: {e}")

                    # Resource cleanup between iterations
                    if cleanup_resources_between_iterations:
                        collected_data = cleanup_resources_between_iterations(i, collected_data, 5000)

                # Periodic browser recycling to prevent memory leaks
                if i % browser_recycle_interval == 0 and recycle_browser_if_needed:
                    try:
                        # CRITICAL FIX: Add timeout to prevent deadlock (audit fix)
                        await asyncio.wait_for(
                            recycle_browser_if_needed(self.mcp, i, browser_recycle_interval, state),
                            timeout=60.0  # 60 second timeout for browser recycle
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Browser recycle timed out at iteration {i} - continuing without recycle")
                    except Exception as e:
                        logger.warning(f"Browser recycle failed: {e}")

                # Circuit breaker check
                if circuit and not circuit.should_allow():
                    backoff = circuit.get_backoff_seconds()
                    console.print(f"[red]>>> Circuit OPEN - backing off {backoff:.0f}s...[/red]")
                    await asyncio.sleep(backoff)
                    continue

                console.print(f"\n[cyan]━━━ Loop {i}/{count} ━━━[/cyan]")
                try:
                    # Per-iteration timeout to prevent hanging
                    try:
                        result = await asyncio.wait_for(
                            self._execute_with_streaming(prompt),
                            timeout=per_iteration_timeout
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Iteration {i} timed out after {per_iteration_timeout}s")
                        if circuit:
                            circuit.record_failure(f"Timeout after {per_iteration_timeout}s")
                        console.print(f"[yellow]>>> Iteration timed out, continuing...[/yellow]")
                        continue

                    # Append to deque (automatically maintains 100-item limit)
                    results.append(result)

                    # Extract any structured data
                    data = self._extract_data(result)
                    if data:
                        collected_data.extend(data)
                        # Save overflow to disk before trimming
                        if len(collected_data) > 5000:
                            overflow_path = self._save_results(collected_data[:-2500], f"{prompt}_overflow_{i}")
                            console.print(f"[dim]Saved overflow to {overflow_path}[/dim]")
                            collected_data = collected_data[-2500:]
                        console.print(f"[dim]Collected: {len(collected_data)} items total[/dim]")

                    # Record success in circuit breaker
                    if circuit:
                        circuit.record_success()

                    # Checkpoint every 5 iterations
                    if state and i % 5 == 0:
                        state.results = collected_data[-100:]  # Keep last 100
                        state.checkpoint({"last_result": str(result)[:500], "total_loops": i})
                        console.print(f"[dim green]+ Checkpoint saved (iteration {i})[/dim green]")

                    if i < count:
                        await asyncio.sleep(2)

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(f"Loop error: {e}")

                    # Record failure in circuit breaker
                    if circuit:
                        circuit.record_failure(str(e))

                    if state:
                        state.errors.append({"iteration": i, "error": str(e)[:200], "timestamp": datetime.now().isoformat()})
                        state.errors = state.errors[-50:]

                    # Display error with circuit breaker status
                    if circuit:
                        status = circuit.get_status()
                        console.print(f"[red]Error: {str(e)[:100]}. Circuit: {status['state']} ({status['failures']} failures)[/red]")
                    else:
                        console.print(f"[red]Error: {str(e)[:100]}. Continuing...[/red]")

        except KeyboardInterrupt:
            console.print(f"\n[yellow]>>> Stopped by user after {i} loops[/yellow]")
            if state:
                state.status = "paused"
                state.results = collected_data[-100:]
                state.checkpoint({"stopped": "user_interrupt"})

        finally:
            # Reset forever mode
            self._forever_mode = False
            self._last_checkpoint_time = None

        # Save collected data
        saved_path = None
        if collected_data:
            saved_path = self._save_results(collected_data, prompt)

        self.memory.save()

        summary = f"Completed {i} loops."
        if saved_path:
            summary += f"\nSaved {len(collected_data)} items to: {saved_path}"
        summary += f"\n\nLast: {results[-1] if results else 'None'}"
        return summary

    async def _infinite_loop(self, prompt: str) -> str:
        """Run indefinitely until canceled (Ctrl+C) with checkpoint support.

        TRUE 24/7 OPERATION:
        - No artificial iteration limit
        - Enterprise circuit breaker with exponential backoff
        - Per-iteration timeout (prevents hanging)
        - Automatic resource cleanup every N iterations
        - Browser recycling to prevent memory leaks
        - Checkpoint every 5 iterations for crash recovery
        """
        results = deque(maxlen=100)  # Memory-safe: automatically keeps only last 100 results
        collected_data = []

        # Create/resume task state for checkpointing
        task_id = hashlib.sha256(prompt.encode()).hexdigest()[:16]

        if ForeverTaskState:
            state = ForeverTaskState.load(task_id)
            if state and state.status == "running":
                i = state.processed_items
                collected_data = state.results.copy() if state.results else []
                console.print(f"\n[bold green]>>> Resuming from checkpoint (iteration {i})[/bold green]")
            else:
                i = 0
                state = ForeverTaskState.create(task_id, "infinite_loop")
        else:
            i = 0
            state = None

        console.print(f"\n[bold yellow]>>> Running 24/7 - Press Ctrl+C to stop[/bold yellow]")
        console.print(f"[dim]Task ID: {task_id} (checkpoints saved automatically)[/dim]")

        # Forever mode already set in run() - disables global timeout
        self._forever_mode = True
        self._last_checkpoint_time = datetime.now()

        # Start health monitoring
        health_writer = None
        if HEALTH_MONITORING_AVAILABLE and HealthWriter:
            health_writer = HealthWriter()
            health_writer.update_activity(f"Infinite loop: {prompt[:50]}")
            health_writer.start()
            logger.info("[HEALTH] Health monitoring started for infinite loop")

        # ENTERPRISE: Circuit breaker for resilience (requires consecutive successes to recover)
        if CircuitBreaker:
            circuit = CircuitBreaker(
                name=f"forever_{task_id}",
                failure_threshold=5,
                recovery_threshold=3,  # Need 3 consecutive successes to fully recover
                initial_backoff=10.0,
                max_backoff=300.0,
                backoff_multiplier=2.0
            )
        else:
            circuit = None

        # Resource management settings
        resource_check_interval = 10  # Check resources every N iterations
        browser_recycle_interval = 100  # Recycle browser every N iterations
        per_iteration_timeout = 300  # 5 minute timeout per iteration (prevents hanging)

        try:
            while True:
                i += 1
                if state:
                    state.processed_items = i

                # TRUE 24/7: No artificial iteration limit - runs until stopped

                # Periodic resource health check
                if i % resource_check_interval == 0:
                    try:
                        issues = self.resource_monitor.check()
                        if issues:
                            logger.warning(f"Resource issues detected at iteration {i}: {issues}")
                            console.print(f"[yellow]>>> Resource warning (iteration {i}): {', '.join(issues)}[/yellow]")
                            # If critical resource issues, take action but DON'T stop
                            if any(keyword in str(issues).lower() for keyword in ['critical', 'extremely high', 'out of']):
                                console.print(f"[yellow]>>> Critical resources - forcing cleanup[/yellow]")
                                # Force cleanup instead of stopping
                                if cleanup_resources_between_iterations:
                                    collected_data = cleanup_resources_between_iterations(i, collected_data, 2000, True)
                    except Exception as e:
                        logger.debug(f"Resource check failed: {e}")

                    # Resource cleanup between iterations
                    if cleanup_resources_between_iterations:
                        collected_data = cleanup_resources_between_iterations(i, collected_data, 5000)

                # Periodic browser recycling to prevent memory leaks
                if i % browser_recycle_interval == 0 and recycle_browser_if_needed:
                    try:
                        # CRITICAL FIX: Add timeout to prevent deadlock (audit fix)
                        await asyncio.wait_for(
                            recycle_browser_if_needed(self.mcp, i, browser_recycle_interval, state),
                            timeout=60.0  # 60 second timeout for browser recycle
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Browser recycle timed out at iteration {i} - continuing without recycle")
                    except Exception as e:
                        logger.warning(f"Browser recycle failed: {e}")

                # Circuit breaker check
                if circuit and not circuit.should_allow():
                    backoff = circuit.get_backoff_seconds()
                    console.print(f"[red]>>> Circuit OPEN - backing off {backoff:.0f}s...[/red]")
                    await asyncio.sleep(backoff)
                    continue

                console.print(f"\n[cyan]--- Loop {i} (24/7 mode) ---[/cyan]")

                # Update health monitoring
                if health_writer:
                    health_writer.update_activity(f"Iteration {i}: {prompt[:40]}")
                    health_writer.increment_iterations()

                try:
                    # Per-iteration timeout to prevent hanging
                    try:
                        result = await asyncio.wait_for(
                            self._execute_with_streaming(prompt),
                            timeout=per_iteration_timeout
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Iteration {i} timed out after {per_iteration_timeout}s")
                        if circuit:
                            circuit.record_failure(f"Timeout after {per_iteration_timeout}s")
                        if health_writer:
                            health_writer.increment_errors()
                        console.print(f"[yellow]>>> Iteration timed out, continuing...[/yellow]")
                        continue

                    # Append to deque (automatically maintains 100-item limit)
                    results.append(result)

                    # Extract any structured data
                    data = self._extract_data(result)
                    if data:
                        collected_data.extend(data)
                        # Save overflow to disk before trimming
                        if len(collected_data) > 5000:
                            overflow_path = self._save_results(collected_data[:-2500], f"{prompt}_overflow_{i}")
                            console.print(f"[dim]Saved overflow to {overflow_path}[/dim]")
                            collected_data = collected_data[-2500:]
                        console.print(f"[dim]Collected: {len(collected_data)} items total[/dim]")

                    # Record success in circuit breaker
                    if circuit:
                        circuit.record_success()

                    # Checkpoint every 5 iterations
                    if state and i % 5 == 0:
                        state.results = collected_data[-100:]  # Keep last 100
                        state.checkpoint({"last_result": str(result)[:500], "total_loops": i})
                        console.print(f"[dim green]+ Checkpoint saved (iteration {i})[/dim green]")

                    # Small delay between iterations
                    await asyncio.sleep(2)

                except Exception as e:
                    logger.error(f"Loop error: {e}")

                    # Record failure in circuit breaker
                    if circuit:
                        circuit.record_failure(str(e))

                    # Update health monitoring
                    if health_writer:
                        health_writer.increment_errors()
                        health_writer.set_status("error")

                    if state:
                        state.errors.append({"iteration": i, "error": str(e)[:200], "timestamp": datetime.now().isoformat()})
                        # Keep only last 50 errors
                        state.errors = state.errors[-50:]

                    # Display error with circuit breaker status
                    if circuit:
                        status = circuit.get_status()
                        console.print(f"[red]Error: {str(e)[:100]}. Circuit: {status['state']} ({status['failures']} failures)[/red]")
                    else:
                        console.print(f"[red]Error: {str(e)[:100]}. Retrying in 10s...[/red]")
                        await asyncio.sleep(10)

        except KeyboardInterrupt:
            console.print(f"\n[yellow]>>> Stopped by user after {i} loops[/yellow]")
            if state:
                state.status = "paused"
                state.results = collected_data[-100:]
                state.checkpoint({"stopped": "user_interrupt"})

        except Exception as e:
            # CRITICAL: Catch-all for unexpected exceptions (audit fix)
            logger.error(f"Infinite loop fatal error: {e}")
            console.print(f"[red]Fatal error in infinite loop: {str(e)[:200]}[/red]")
            if state:
                state.status = "error"
                state.errors.append({"iteration": i, "error": f"FATAL: {str(e)[:200]}", "timestamp": datetime.now().isoformat()})
                state.checkpoint({"fatal_error": str(e)[:500]})

        finally:
            # Stop health monitoring (CRITICAL: ensure cleanup on ANY exit)
            if health_writer:
                health_writer.stop()
                logger.info("[HEALTH] Health monitoring stopped for infinite loop")

            # Reset forever mode
            self._forever_mode = False
            self._last_checkpoint_time = None

        # Save collected data
        saved_path = None
        if collected_data:
            saved_path = self._save_results(collected_data, prompt)

        self.memory.save()

        summary = f"Ran {i} loops (24/7 mode, stopped by user)."
        summary += f"\nTask ID: {task_id} (can resume with same prompt)"
        if saved_path:
            summary += f"\nSaved {len(collected_data)} items to: {saved_path}"
        summary += f"\n\nLast: {results[-1] if results else 'None'}"
        return summary

    async def _scheduled_loop(self, prompt: str, schedule: Dict[str, Any]) -> str:
        """Run on a schedule (e.g., every day at 9am, every friday at 3pm) with enterprise features.

        ENTERPRISE FEATURES:
        - Circuit breaker with exponential backoff
        - Per-iteration timeout (prevents hanging)
        - Automatic resource cleanup every N iterations
        - Browser recycling to prevent memory leaks
        - Checkpoint every 5 iterations for crash recovery
        """
        interval = schedule['interval']
        time_of_day = schedule.get('time_of_day')
        duration = schedule.get('duration')
        max_count = schedule.get('count')
        day_of_week = schedule.get('day_of_week')  # 0=Mon, 6=Sun

        results = deque(maxlen=100)  # Memory-safe: automatically keeps only last 100 results
        collected_data = []
        i = 0

        # Calculate end time if duration specified
        end_time = datetime.now() + duration if duration else None

        # Create/resume task state for checkpointing
        task_id = hashlib.sha256(prompt.encode()).hexdigest()[:16]

        if ForeverTaskState:
            state = ForeverTaskState.load(task_id)
            if state and state.status == "running" and state.task_type == "scheduled_loop":
                i = state.processed_items
                collected_data = state.results.copy() if state.results else []
                console.print(f"\n[bold green]>>> Resuming from checkpoint (iteration {i})[/bold green]")
            else:
                i = 0
                state = ForeverTaskState.create(task_id, "scheduled_loop")
        else:
            i = 0
            state = None

        # Forever mode already set in run() - scheduled tasks run indefinitely unless duration/count set
        self._forever_mode = True
        self._last_checkpoint_time = datetime.now()

        # ENTERPRISE: Circuit breaker for resilience
        if CircuitBreaker:
            circuit = CircuitBreaker(
                name=f"scheduled_{task_id}",
                failure_threshold=5,
                recovery_threshold=3,
                initial_backoff=10.0,
                max_backoff=300.0,
                backoff_multiplier=2.0
            )
        else:
            circuit = None

        # Resource management settings
        resource_check_interval = 10  # Check resources every N iterations
        browser_recycle_interval = 100  # Recycle browser every N iterations
        per_iteration_timeout = 300  # 5 minute timeout per iteration (prevents hanging)

        # Start health monitoring (CRITICAL: was missing - audit fix)
        health_writer = None
        if HEALTH_MONITORING_AVAILABLE and HealthWriter:
            health_writer = HealthWriter()
            health_writer.update_activity(f"Scheduled loop: {prompt[:50]}")
            health_writer.start()
            logger.info("[HEALTH] Health monitoring started for scheduled loop")

        # Format schedule info for display
        days_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        if day_of_week is not None:
            day_name = days_names[day_of_week]
            time_str = f"{time_of_day['hour']:02d}:{time_of_day['minute']:02d}" if time_of_day else "09:00"
            console.print(f"\n[bold cyan]Scheduled: every {day_name} at {time_str}[/bold cyan]")
        elif time_of_day:
            time_str = f"{time_of_day['hour']:02d}:{time_of_day['minute']:02d}"
            console.print(f"\n[bold cyan]Scheduled: every {interval} at {time_str}[/bold cyan]")
        else:
            console.print(f"\n[bold cyan]Scheduled: every {interval}[/bold cyan]")

        if end_time:
            console.print(f"[dim]Running until: {end_time.strftime('%Y-%m-%d %H:%M')}[/dim]")
        if max_count:
            console.print(f"[dim]Max runs: {max_count}[/dim]")

        console.print(f"[dim]Task ID: {task_id} (checkpoints saved automatically)[/dim]")
        console.print(f"[yellow]Press Ctrl+C to stop[/yellow]")

        try:
            while True:
                # Check end conditions
                if end_time and datetime.now() >= end_time:
                    console.print(f"\n[green]Duration completed[/green]")
                    break
                if max_count and i >= max_count:
                    console.print(f"\n[green]Completed {max_count} runs[/green]")
                    break

                # Wait for scheduled time
                if i > 0:
                    now = datetime.now()

                    if day_of_week is not None:
                        # Day-of-week scheduling (e.g., every Friday at 3pm)
                        target_hour = time_of_day['hour'] if time_of_day else 9
                        target_minute = time_of_day['minute'] if time_of_day else 0

                        # Calculate days until next occurrence
                        days_ahead = day_of_week - now.weekday()
                        if days_ahead <= 0:  # Target day already passed this week
                            days_ahead += 7

                        target = now + timedelta(days=days_ahead)
                        target = target.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)

                        wait_seconds = (target - now).total_seconds()
                        console.print(f"[dim]Next run: {days_names[day_of_week]} at {target.strftime('%Y-%m-%d %H:%M')} ({wait_seconds/3600:.1f}h)[/dim]")
                        await asyncio.sleep(wait_seconds)

                    elif time_of_day:
                        # Daily at specific time
                        target = now.replace(
                            hour=time_of_day['hour'],
                            minute=time_of_day['minute'],
                            second=0,
                            microsecond=0
                        )
                        # If target time already passed today, schedule for tomorrow
                        if target <= now:
                            target += timedelta(days=1)

                        wait_seconds = (target - now).total_seconds()
                        if wait_seconds > 0:
                            console.print(f"[dim]Next run at {target.strftime('%Y-%m-%d %H:%M')} ({wait_seconds/3600:.1f}h)[/dim]")
                            await asyncio.sleep(wait_seconds)
                    else:
                        # Just wait for interval
                        wait_seconds = interval.total_seconds()
                        next_run = datetime.now() + interval
                        console.print(f"[dim]Next run at {next_run.strftime('%H:%M:%S')} ({wait_seconds/60:.1f}m)[/dim]")
                        await asyncio.sleep(wait_seconds)

                # Execute
                i += 1
                if state:
                    state.processed_items = i

                # Periodic resource health check
                if i % resource_check_interval == 0:
                    try:
                        issues = self.resource_monitor.check()
                        if issues:
                            logger.warning(f"Resource issues detected at iteration {i}: {issues}")
                            console.print(f"[yellow]>>> Resource warning (iteration {i}): {', '.join(issues)}[/yellow]")
                            if any(keyword in str(issues).lower() for keyword in ['critical', 'extremely high', 'out of']):
                                console.print(f"[yellow]>>> Critical resources - forcing cleanup[/yellow]")
                                if cleanup_resources_between_iterations:
                                    collected_data = cleanup_resources_between_iterations(i, collected_data, 2000, True)
                    except Exception as e:
                        logger.debug(f"Resource check failed: {e}")

                    # Resource cleanup between iterations
                    if cleanup_resources_between_iterations:
                        collected_data = cleanup_resources_between_iterations(i, collected_data, 5000)

                # Periodic browser recycling to prevent memory leaks
                if i % browser_recycle_interval == 0 and recycle_browser_if_needed:
                    try:
                        # CRITICAL FIX: Add timeout to prevent deadlock (audit fix)
                        await asyncio.wait_for(
                            recycle_browser_if_needed(self.mcp, i, browser_recycle_interval, state),
                            timeout=60.0  # 60 second timeout for browser recycle
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Browser recycle timed out at iteration {i} - continuing without recycle")
                    except Exception as e:
                        logger.warning(f"Browser recycle failed: {e}")

                # Circuit breaker check
                if circuit and not circuit.should_allow():
                    backoff = circuit.get_backoff_seconds()
                    console.print(f"[red]>>> Circuit OPEN - backing off {backoff:.0f}s...[/red]")
                    await asyncio.sleep(backoff)
                    continue

                console.print(f"\n[cyan]━━━ Scheduled Run {i} ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ━━━[/cyan]")

                try:
                    # Per-iteration timeout to prevent hanging
                    try:
                        result = await asyncio.wait_for(
                            self._execute_with_streaming(prompt),
                            timeout=per_iteration_timeout
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Iteration {i} timed out after {per_iteration_timeout}s")
                        if circuit:
                            circuit.record_failure(f"Timeout after {per_iteration_timeout}s")
                        console.print(f"[yellow]>>> Iteration timed out, continuing to next scheduled run...[/yellow]")
                        continue

                    # Append to deque (automatically maintains 100-item limit)
                    results.append(result)

                    # Extract any structured data
                    data = self._extract_data(result)
                    if data:
                        collected_data.extend(data)
                        # Save overflow to disk before trimming
                        if len(collected_data) > 5000:
                            overflow_path = self._save_results(collected_data[:-2500], f"{prompt}_overflow_{i}")
                            console.print(f"[dim]Saved overflow to {overflow_path}[/dim]")
                            collected_data = collected_data[-2500:]
                        console.print(f"[dim]Collected: {len(collected_data)} items total[/dim]")

                    # Record success in circuit breaker
                    if circuit:
                        circuit.record_success()

                    # Checkpoint every 5 iterations
                    if state and i % 5 == 0:
                        state.results = collected_data[-100:]  # Keep last 100
                        state.checkpoint({"last_result": str(result)[:500], "total_runs": i})
                        console.print(f"[dim green]+ Checkpoint saved (iteration {i})[/dim green]")

                except Exception as e:
                    logger.error(f"Scheduled run error: {e}")

                    # Record failure in circuit breaker
                    if circuit:
                        circuit.record_failure(str(e))

                    if state:
                        state.errors.append({"iteration": i, "error": str(e)[:200], "timestamp": datetime.now().isoformat()})
                        state.errors = state.errors[-50:]

                    # Display error with circuit breaker status
                    if circuit:
                        status = circuit.get_status()
                        console.print(f"[red]Error: {str(e)[:100]}. Circuit: {status['state']} ({status['failures']} failures)[/red]")
                    else:
                        console.print(f"[red]Error: {e}[/red]")

                    # Update health monitoring (CRITICAL: was missing - audit fix)
                    if health_writer:
                        health_writer.increment_errors()
                        health_writer.set_status("error")

        except KeyboardInterrupt:
            console.print(f"\n[yellow]Schedule stopped by user after {i} runs[/yellow]")
            if state:
                state.status = "paused"
                state.results = collected_data[-100:]
                state.checkpoint({"stopped": "user_interrupt"})

        except Exception as e:
            # CRITICAL: Catch-all for unexpected exceptions (audit fix)
            logger.error(f"Scheduled loop fatal error: {e}")
            console.print(f"[red]Fatal error in scheduled loop: {str(e)[:200]}[/red]")
            if state:
                state.status = "error"
                state.errors.append({"iteration": i, "error": f"FATAL: {str(e)[:200]}", "timestamp": datetime.now().isoformat()})
                state.checkpoint({"fatal_error": str(e)[:500]})

        finally:
            # Stop health monitoring (CRITICAL: was missing - audit fix)
            if health_writer:
                health_writer.stop()
                logger.info("[HEALTH] Health monitoring stopped for scheduled loop")

            # Reset forever mode
            self._forever_mode = False
            self._last_checkpoint_time = None

        # Save collected data
        saved_path = None
        if collected_data:
            saved_path = self._save_results(collected_data, prompt)

        self.memory.save()

        summary = f"Completed {i} scheduled runs."
        if saved_path:
            summary += f"\nSaved {len(collected_data)} items to: {saved_path}"
        summary += f"\n\nLast: {results[-1] if results else 'None'}"
        return summary


    async def _one_time_scheduled(self, prompt: str, schedule: Dict[str, Any]) -> str:
        """Run once at a scheduled time (e.g., next friday at 3pm)."""
        target_day = schedule.get('target_day')  # 0=Mon, 6=Sun
        time_of_day = schedule.get('time_of_day', {'hour': 9, 'minute': 0})

        # Calculate target datetime
        now = datetime.now()
        current_weekday = now.weekday()

        # Days until target day
        days_ahead = target_day - current_weekday
        if days_ahead <= 0:  # Target day already passed this week
            days_ahead += 7

        target_date = now + timedelta(days=days_ahead)
        target_datetime = target_date.replace(
            hour=time_of_day['hour'],
            minute=time_of_day['minute'],
            second=0,
            microsecond=0
        )

        # If target time already passed today and it's the target day, schedule for next week
        if target_datetime <= now:
            target_datetime += timedelta(weeks=1)

        wait_seconds = (target_datetime - now).total_seconds()

        days_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        target_day_name = days_names[target_day]

        console.print(f"\n[bold cyan]📅 One-time task scheduled[/bold cyan]")
        console.print(f"[bold]When:[/bold] {target_day_name} at {time_of_day['hour']:02d}:{time_of_day['minute']:02d}")
        console.print(f"[bold]Date:[/bold] {target_datetime.strftime('%Y-%m-%d %H:%M')}")
        console.print(f"[dim]Waiting {wait_seconds/3600:.1f} hours ({wait_seconds/86400:.1f} days)[/dim]")
        console.print(f"[yellow]Press Ctrl+C to cancel[/yellow]\n")

        try:
            # Wait until target time
            await asyncio.sleep(wait_seconds)

            # Execute
            console.print(f"\n[cyan]━━━ Executing scheduled task ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ━━━[/cyan]")
            result = await self._execute_with_streaming(prompt)

            console.print(f"\n[green]✓ One-time task completed[/green]")
            self.memory.save()
            return result

        except KeyboardInterrupt:
            console.print(f"\n[yellow]⏹ Scheduled task cancelled[/yellow]")
            return "Task cancelled by user"

    # =========================================================================
    # Data extraction and saving helpers
    # =========================================================================

    def _extract_data(self, result: str) -> List[Dict]:
        """Extract structured data from result text."""
        extracted = []

        if not result:
            return extracted

        # Try JSON
        try:
            match = re.search(r'\[[\s\S]*?\]', result)
            if match:
                data = json.loads(match.group(0))
                if isinstance(data, list):
                    return data
        except (json.JSONDecodeError, ValueError):
            pass  # Expected for non-JSON results, continue to key-value parsing

        # Try key-value pairs
        lines = result.split('\n')
        current = {}

        for line in lines:
            line = line.strip()
            if not line:
                if current and len(current) > 1:
                    extracted.append(current)
                    current = {}
                continue

            match = re.match(r'^[•\-\*]?\s*([A-Za-z_]+)\s*[:\-]\s*(.+)$', line)
            if match:
                key = match.group(1).lower()
                value = match.group(2).strip()
                current[key] = value

        if current and len(current) > 1:
            extracted.append(current)

        return extracted

    def _save_results(self, data: List[Dict], prompt: str) -> Optional[str]:
        """Save results to user's output folder."""
        if not data:
            return None

        try:
            from .output_path import save_csv

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            clean = re.sub(r'[^a-zA-Z0-9]+', '_', prompt[:20]).strip('_').lower()
            filename = f"results_{clean}_{timestamp}.csv"

            path = save_csv(filename, data)
            console.print(f"[green]Saved to: {path}[/green]")
            return str(path)

        except Exception as e:
            logger.error(f"Save failed: {e}")
            return None
