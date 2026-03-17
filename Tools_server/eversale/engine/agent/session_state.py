"""
Session State Management for Eversale Agent

This module contains the SessionState class that manages:
- Memory and learning from successful/failed executions
- Statistics tracking (iterations, tool calls, retries, etc.)
- Action logging and historical execution tracking
- Task duration and goal tracking

Extracted from brain_enhanced_v2.py to improve modularity and reduce file size.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from loguru import logger


# Memory persistence directory
MEMORY_DIR = Path("memory")
MEMORY_DIR.mkdir(exist_ok=True)


@dataclass
class Memory:
    """
    Persistent memory for learning from past executions.

    Stores:
    - domain_strategies: Successful prompts/patterns by domain
    - successful_selectors: Tool executions that worked
    - failed_approaches: Tool executions that failed (to avoid repeating)
    """
    domain_strategies: Dict[str, List[Dict]] = field(default_factory=dict)
    successful_selectors: Dict[str, List[str]] = field(default_factory=dict)
    failed_approaches: Dict[str, List[str]] = field(default_factory=dict)

    def save(self):
        """Persist memory to disk as JSON."""
        path = MEMORY_DIR / "agent_memory.json"
        data = {
            'domain_strategies': self.domain_strategies,
            'successful_selectors': self.successful_selectors,
            'failed_approaches': self.failed_approaches,
        }
        try:
            path.write_text(json.dumps(data, indent=2))
            logger.debug(f"Memory saved to {path}")
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")

    @classmethod
    def load(cls) -> 'Memory':
        """
        Load memory from disk, or return empty memory if none exists.

        Returns:
            Memory instance with loaded or default data
        """
        path = MEMORY_DIR / "agent_memory.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                logger.debug(f"Memory loaded from {path}")
                return cls(
                    domain_strategies=data.get('domain_strategies', {}),
                    successful_selectors=data.get('successful_selectors', {}),
                    failed_approaches=data.get('failed_approaches', {}),
                )
            except Exception as e:
                logger.error(f"Failed to load memory: {e}, using empty memory")
                return cls()
        return cls()


class SessionState:
    """
    Manages session state including memory, statistics, action logging,
    and learning from successful/failed tool executions.

    Extracted from EnhancedBrain to reduce file size and improve modularity.

    Responsibilities:
    - Track execution statistics (iterations, tool calls, retries, etc.)
    - Maintain execution logs and historical actions
    - Learn from successful/failed tool executions
    - Provide memory-based fallbacks for failed tools
    - Integrate with DecisionLogger, AwarenessHub, and SurvivalManager
    """

    def __init__(self, decision_logger=None, awareness=None, survival=None):
        """
        Initialize session state.

        Args:
            decision_logger: Optional DecisionLogger instance for logging decisions
            awareness: Optional AwarenessHub instance for context
            survival: Optional SurvivalManager instance for progress tracking
        """
        # Session identity for persistence/tracking layers
        self.session_id = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Statistics tracking
        self.stats = {
            'iterations': 0,
            'tool_calls': 0,
            'vision_calls': 0,
            'retries': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'health_checks': 0,
            'resource_checks': 0,
            'throttle_count': 0,
            'resource_warnings': 0,
        }

        # Memory persistence
        self.memory = Memory.load()

        # Execution tracking
        self._execution_log: List[Dict[str, Any]] = []
        self._historical_actions: List[Dict[str, Any]] = []
        self._last_issues: List[str] = []

        # Task tracking
        self._task_start_time = datetime.now()
        self._goal_summary = ""
        self._goal_keywords: List[str] = []

        # External dependencies (optional)
        self._decision_logger = decision_logger
        self._awareness = awareness
        self._survival = survival

        logger.debug("SessionState initialized")

    def reset_for_new_task(self):
        """
        Reset state for a new task execution.

        Clears execution log and task-specific state,
        but preserves statistics and memory.
        """
        self._execution_log.clear()
        self._task_start_time = datetime.now()
        self._goal_summary = ""
        self._goal_keywords = []
        self._last_issues = []
        logger.debug("SessionState reset for new task")

    def log_resource_issue(self, issue: str):
        """
        Log a resource-related issue (memory, CPU, etc.).

        Args:
            issue: Description of the resource issue
        """
        logger.warning(f"Resource issue: {issue}")
        self._last_issues.append(issue)
        if self._survival:
            self._survival.record_progress(f"Resource issue: {issue}")

    def log_action(self, name: str, args: Dict[str, Any], success: bool,
                   result: Any = None, error: str = None, attempt: int = 1):
        """
        Log an action execution with its outcome.

        Args:
            name: Tool/action name
            args: Arguments passed to the tool
            success: Whether the execution succeeded
            result: Result if successful
            error: Error message if failed
            attempt: Attempt number (for retries)
        """
        entry = {
            'timestamp': datetime.now().isoformat(),
            'action': name,
            'args': dict(args) if isinstance(args, dict) else args,
            'success': success,
            'attempt': attempt,
            'result': result if success else None,
            'error': error
        }
        self._execution_log.append(entry)
        self._historical_actions.append(entry)

        # Keep bounded history (prevent unbounded growth)
        if len(self._historical_actions) > 500:
            self._historical_actions.pop(0)

        # Log to decision logger if available
        self._log_decision("tool_call", entry)

    def _log_decision(self, kind: str, detail: Dict[str, Any]):
        """
        Log a decision with context from awareness and survival.

        Args:
            kind: Type of decision (e.g., "tool_call", "reasoning")
            detail: Decision details
        """
        record = {
            "kind": kind,
            "detail": detail,
            "awareness": self._awareness.digest() if self._awareness else {},
            "survival": self._survival.digest() if self._survival else {},
            "timestamp": datetime.now().isoformat()
        }
        if self._decision_logger:
            try:
                self._decision_logger.log(record)
            except Exception as e:
                logger.debug(f"Decision logging failed: {e}")

    def record_successful_tool(self, name: str, args: Dict[str, Any]):
        """
        Record a successful tool execution for learning.

        Args:
            name: Tool name
            args: Arguments that worked
        """
        if not isinstance(args, dict):
            return

        entry = {
            'args': dict(args),
            'timestamp': datetime.now().isoformat()
        }

        bucket = self.memory.successful_selectors.setdefault(name, [])

        # Only add if not duplicate of recent entries
        if entry['args'] and all(e['args'] != entry['args'] for e in bucket[-5:]):
            bucket.append(entry)
            logger.debug(f"Recorded successful tool: {name}")

    def record_failed_tool(self, name: str, args: Dict[str, Any]):
        """
        Record a failed tool execution to avoid repeating.

        Args:
            name: Tool name
            args: Arguments that failed
        """
        if not isinstance(args, dict):
            return

        entry = {
            'args': dict(args),
            'timestamp': datetime.now().isoformat()
        }

        bucket = self.memory.failed_approaches.setdefault(name, [])

        # Only add if not duplicate of recent entries
        if entry['args'] and all(e['args'] != entry['args'] for e in bucket[-5:]):
            bucket.append(entry)
            logger.debug(f"Recorded failed tool: {name}")

    def get_memory_fallback(self, tool_name: str, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get a fallback from memory based on previous successful executions.

        Args:
            tool_name: Tool name to find fallback for
            args: Current arguments that failed

        Returns:
            Merged arguments with successful parameters, or None
        """
        bucket = self.memory.successful_selectors.get(tool_name, [])

        # Try last 5 successful executions
        for entry in reversed(bucket[-5:]):
            stored = entry.get('args', {})
            if stored and stored != args:
                logger.debug(f"Found memory fallback for {tool_name}")
                return {**args, **stored}

        return None

    def learn_success(self, domain: str, prompt: str):
        """
        Learn from a successful task execution.

        Args:
            domain: Task domain/category
            prompt: Prompt that led to success
        """
        if domain not in self.memory.domain_strategies:
            self.memory.domain_strategies[domain] = []

        strategy = {
            'prompt_pattern': prompt[:50],  # Store first 50 chars
            'timestamp': datetime.now().isoformat(),
            'tools_used': self.stats['tool_calls'],
        }

        self.memory.domain_strategies[domain].append(strategy)

        # Keep only last 10 strategies per domain
        self.memory.domain_strategies[domain] = self.memory.domain_strategies[domain][-10:]

        logger.info(f"Learned success pattern for domain: {domain}")

    def save_memory(self):
        """Persist memory to disk."""
        self.memory.save()

    def get_successful_actions(self) -> List[Dict[str, Any]]:
        """
        Get list of successful actions from historical actions.

        Returns:
            List of successful action entries
        """
        return [entry for entry in self._historical_actions if entry.get('success')]

    def get_recent_actions(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most recent actions from execution log.

        Args:
            count: Number of recent actions to return

        Returns:
            List of recent action entries
        """
        return self._execution_log[-count:]

    def get_task_duration(self) -> float:
        """
        Get duration of current task in seconds.

        Returns:
            Task duration in seconds
        """
        return (datetime.now() - self._task_start_time).total_seconds()

    def get_stats_summary(self) -> Dict[str, Any]:
        """
        Get a summary of current statistics.

        Returns:
            Dictionary with stats, duration, and log sizes
        """
        return {
            **self.stats,
            'duration_seconds': self.get_task_duration(),
            'execution_log_size': len(self._execution_log),
            'historical_actions_size': len(self._historical_actions),
            'issues_count': len(self._last_issues)
        }

    def increment_stat(self, stat_name: str, amount: int = 1):
        """
        Increment a statistic by the given amount.

        Args:
            stat_name: Name of the stat to increment
            amount: Amount to increment by (default 1)
        """
        if stat_name in self.stats:
            self.stats[stat_name] += amount
        else:
            logger.warning(f"Attempted to increment unknown stat: {stat_name}")

    def set_goal(self, summary: str, keywords: List[str] = None):
        """
        Set the current goal summary and keywords.

        Args:
            summary: Goal summary text
            keywords: List of goal-related keywords
        """
        self._goal_summary = summary
        self._goal_keywords = keywords or []
        logger.debug(f"Goal set: {summary[:50]}...")

    @property
    def goal_summary(self) -> str:
        """Get the current goal summary."""
        return self._goal_summary

    @property
    def goal_keywords(self) -> List[str]:
        """Get the current goal keywords."""
        return self._goal_keywords

    @property
    def last_issues(self) -> List[str]:
        """Get list of recent issues."""
        return self._last_issues

    @property
    def execution_log(self) -> List[Dict[str, Any]]:
        """Get the full execution log for current task."""
        return self._execution_log

    @property
    def historical_actions(self) -> List[Dict[str, Any]]:
        """Get the full historical actions across tasks."""
        return self._historical_actions
