"""
MetricsRecorderMixin - Metrics, logging, and progress tracking functionality.

Extracted from brain_enhanced_v2.py to improve code organization.
This mixin handles:
- Resource issue logging
- Action logging (successes/failures)
- Decision tracking
- Tool execution recording
- Memory fallback retrieval
- Goal reminders
- Progress notifications
- Context compaction
- Explainable summaries with hallucination checking
"""

import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from loguru import logger


class MetricsRecorderMixin:
    """
    Mixin for metrics recording, logging, and progress tracking.

    Required parent class attributes:
    - self.session_state: SessionState instance for delegated logging
    - self.messages: List of message dicts for conversation history
    - self._goal_summary: String summary of the current goal
    - self._progress_callback: Optional callback for UI progress updates
    - self._compact_threshold: Int threshold for context compaction
    - self._task_start_time: datetime when task started
    - self._execution_log: List of execution actions
    - self.awareness: AwarenessHub instance
    - self.survival: SurvivalManager instance
    - self.stats: Dict with 'tool_calls' and other counters
    - self.hallucination_guard: Optional HallucinationGuard instance
    """

    # ==================== DELEGATION TO SESSION STATE ====================

    def _log_resource_issue(self, issue: str):
        """Delegate to session_state."""
        self.session_state.log_resource_issue(issue)

    def _log_action(self, name: str, args: Dict[str, Any], success: bool, result: Any = None, error: str = None, attempt: int = 1):
        """Delegate to session_state."""
        self.session_state.log_action(name, args, success, result, error, attempt)

    def _log_decision(self, kind: str, detail: Dict[str, Any]):
        """Delegate to session_state."""
        self.session_state._log_decision(kind, detail)

    def _record_successful_tool(self, name: str, args: Dict[str, Any]):
        """Delegate to session_state."""
        self.session_state.record_successful_tool(name, args)

    def _record_failed_tool(self, name: str, args: Dict[str, Any]):
        """Delegate to session_state."""
        self.session_state.record_failed_tool(name, args)

    def _get_memory_fallback(self, tool_name: str, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Delegate to session_state."""
        return self.session_state.get_memory_fallback(tool_name, args)

    # ==================== GOAL REMINDERS ====================

    def _add_goal_reminder(self):
        """Add a goal reminder as a user message (not system - that breaks Ollama tool calling)."""
        if not self._goal_summary:
            return
        # Use 'user' role instead of 'system' - Ollama only expects system at start
        self.messages.append({
            'role': 'user',
            'content': f"[Reminder: Your goal is to {self._goal_summary[:150]}. Continue working toward this goal.]"
        })

    # ==================== PROGRESS NOTIFICATIONS ====================

    def _notify_progress(self, message: str, step: str = None):
        """Notify UI of progress update."""
        if self._progress_callback:
            try:
                self._progress_callback(message, step)
            except Exception as e:
                logger.debug(f"Progress callback error: {e}")

    # ==================== CONTEXT COMPACTION ====================

    def _compact_context(self):
        """Compact context when messages exceed threshold.

        Like Claude Code's context compaction - summarizes older messages
        to fit within context window limits.
        """
        if len(self.messages) < self._compact_threshold:
            return

        logger.info(f"Compacting context: {len(self.messages)} messages")
        self._notify_progress("Compacting context")

        # Keep system message and first user message
        system_msgs = [m for m in self.messages if m.get('role') == 'system']
        first_user = None
        for m in self.messages:
            if m.get('role') == 'user':
                first_user = m
                break

        # Keep last N messages for recency
        keep_recent = 10
        recent_msgs = self.messages[-keep_recent:]

        # Summarize middle section (tool calls and results)
        middle_start = len(system_msgs) + (1 if first_user else 0)
        middle_end = len(self.messages) - keep_recent
        middle_msgs = self.messages[middle_start:middle_end]

        if middle_msgs:
            # Create summary of what happened
            tool_calls = []
            for m in middle_msgs:
                if m.get('role') == 'assistant':
                    content = m.get('content', '')
                    if 'playwright_' in content or 'tool_call' in str(m):
                        # Extract tool name from content
                        for tool in ['navigate', 'click', 'fill', 'extract', 'screenshot']:
                            if tool in content.lower():
                                tool_calls.append(tool)
                                break

            summary = f"[Previous actions: {', '.join(tool_calls[:10]) or 'exploration'}]"

            summary_msg = {
                'role': 'assistant',
                'content': summary
            }

            # Rebuild messages: system + first_user + summary + recent
            self.messages = system_msgs
            if first_user and first_user not in system_msgs:
                self.messages.append(first_user)
            self.messages.append(summary_msg)
            self.messages.extend(recent_msgs)

            logger.info(f"Context compacted to {len(self.messages)} messages")

    # ==================== EXPLAINABLE SUMMARIES ====================

    def _emit_explainable_summary(self, summary: str, issues: List[str]):
        """Emit explainable summary with hallucination checking and full audit trail."""
        # FINAL HALLUCINATION CHECK: Validate summary before emitting
        final_validation = None
        if self.hallucination_guard:
            final_validation = self.hallucination_guard.validate_output(summary)
            if not final_validation.is_valid:
                logger.warning(f"HALLUCINATION in final summary: {final_validation.issues}")
                issues.extend([f"[HALLUCINATION WARNING] {i}" for i in final_validation.issues])
                # Clean the summary if possible
                if final_validation.cleaned_data:
                    summary = str(final_validation.cleaned_data)

        issue_text = "; ".join(issues) if issues else "none"
        duration = (datetime.now() - self._task_start_time).total_seconds()
        self.survival.store_checkpoint("Summary emitted")
        entry = {
            'goal': self._goal_summary,
            'summary': summary,
            'issues': issues,
            'duration_sec': round(duration, 1),
            'actions': self._execution_log[-10:],
            'awareness': self.awareness.digest(),
            'survival': self.survival.digest(),
            'hallucination_check': 'passed' if (final_validation and final_validation.is_valid) else 'warnings'
        }
        logger.info(f"Explainable summary: {json.dumps(entry, indent=2)}")
        self.messages.append({
            'role': 'system',
            'content': f"Execution complete. Summary: {summary}\nIssues encountered: {issue_text}"
        })
        try:
            self.awareness.save_state()
        except Exception:
            pass
        try:
            self.survival.save_state()
        except Exception:
            pass
