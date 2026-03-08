"""
Session Summarization System - Generate summaries of agent sessions

Based on OpenCode's session/summary.ts, this module provides comprehensive
session summarization including:
- Message title and body generation
- Statistics tracking (files modified, lines changed, tool calls, etc.)
- Snapshot diffing to compute file changes
- Incremental summary updates
- Parent session linking for forked sessions

Features:
- summarize_session() - Generate full session summary with statistics
- summarize_message() - Create title and body for a message
- generate_title() - Brief headline from user message (max 20 words)
- generate_body() - Conversational context summary (max 100 tokens)
- compute_diffs() - Calculate file changes between snapshots
- save_summary() - Persist summary to disk (memory/summaries/)

Integration:
- Works with SessionState for session management
- Uses SnapshotManager for computing diffs
- Stores summaries in JSON format

Usage:
    from session_summary import SessionSummarizer
    from session_state import SessionState
    from snapshot_system import SnapshotManager

    session = SessionState()
    snapshot_mgr = SnapshotManager()
    summarizer = SessionSummarizer(session, snapshot_mgr)

    # Generate summary after session completes
    summary = summarizer.summarize_session()

    # Save summary to disk
    summarizer.save_summary(summary)
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from loguru import logger

from session_state import SessionState
from snapshot_system import SnapshotManager, DiffStat


# Memory directory for summaries
SUMMARY_DIR = Path("memory/summaries")
SUMMARY_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class FileChangeStat:
    """Statistics for a single file's changes."""
    file_path: str
    lines_added: int
    lines_removed: int
    net_change: int = 0

    def __post_init__(self):
        """Calculate net change automatically."""
        self.net_change = self.lines_added - self.lines_removed


@dataclass
class SessionStatistics:
    """Comprehensive session statistics."""
    # Timing
    duration_seconds: float
    started_at: str
    ended_at: str

    # Actions and tools
    total_iterations: int
    total_tool_calls: int
    vision_calls: int
    retries: int
    successful_actions: int
    failed_actions: int
    success_rate: float

    # Cache and performance
    cache_hits: int
    cache_misses: int
    cache_hit_rate: float

    # File changes
    total_files_modified: int
    total_lines_added: int
    total_lines_removed: int
    net_lines_changed: int
    file_changes: List[FileChangeStat] = field(default_factory=list)

    # Resource metrics
    health_checks: int = 0
    resource_checks: int = 0
    throttle_count: int = 0
    resource_warnings: int = 0
    issues_count: int = 0


@dataclass
class MessageSummary:
    """Summary of a single message in the session."""
    role: str
    timestamp: str
    title: str
    body: str
    tool_name: Optional[str] = None
    success: Optional[bool] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionSummary:
    """Complete session summary."""
    # Identity
    session_id: str
    parent_session_id: Optional[str] = None
    child_session_ids: List[str] = field(default_factory=list)

    # Core summary
    title: str = ""
    description: str = ""
    goal_summary: str = ""
    goal_keywords: List[str] = field(default_factory=list)

    # Statistics
    statistics: Optional[SessionStatistics] = None

    # Messages
    messages: List[MessageSummary] = field(default_factory=list)

    # File changes
    files_modified: List[str] = field(default_factory=list)
    file_change_details: List[FileChangeStat] = field(default_factory=list)

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        # Convert nested dataclasses
        if self.statistics:
            result['statistics'] = asdict(self.statistics)
        result['messages'] = [asdict(msg) for msg in self.messages]
        result['file_change_details'] = [asdict(fc) for fc in self.file_change_details]
        return result


class SessionSummarizer:
    """
    Session summarization system for agent executions.

    Generates comprehensive summaries including:
    - Session statistics and metrics
    - File changes with line counts
    - Message summaries with titles/bodies
    - Snapshot-based diffing
    """

    def __init__(
        self,
        session: SessionState,
        snapshot_mgr: Optional[SnapshotManager] = None,
        max_title_words: int = 20,
        max_body_tokens: int = 100
    ):
        """
        Initialize session summarizer.

        Args:
            session: SessionState instance to summarize
            snapshot_mgr: Optional SnapshotManager for computing diffs
            max_title_words: Maximum words in generated titles (default 20)
            max_body_tokens: Maximum tokens in body summaries (default 100)
        """
        self.session = session
        self.snapshot_mgr = snapshot_mgr
        self.max_title_words = max_title_words
        self.max_body_tokens = max_body_tokens

        logger.debug(f"SessionSummarizer initialized for session {session.session_id}")

    def summarize_session(
        self,
        start_snapshot: Optional[str] = None,
        end_snapshot: Optional[str] = None
    ) -> SessionSummary:
        """
        Generate comprehensive session summary.

        Args:
            start_snapshot: Optional starting snapshot hash for diff computation
            end_snapshot: Optional ending snapshot hash for diff computation

        Returns:
            SessionSummary with complete statistics and summaries
        """
        logger.info(f"Generating summary for session {self.session.session_id}")

        # Generate statistics
        stats = self._generate_statistics(start_snapshot, end_snapshot)

        # Generate message summaries
        message_summaries = self._generate_message_summaries()

        # Get first user message for title
        first_user_msg = next(
            (entry for entry in self.session.execution_log if entry.get('action') == 'user'),
            None
        )
        title = self.generate_title(first_user_msg) if first_user_msg else "Agent Session"

        # Create summary
        summary = SessionSummary(
            session_id=self.session.session_id,
            parent_session_id=self.session.parent_session_id,
            child_session_ids=list(self.session.child_session_ids),
            title=title,
            description=self._generate_description(),
            goal_summary=self.session.goal_summary,
            goal_keywords=list(self.session.goal_keywords),
            statistics=stats,
            messages=message_summaries,
            files_modified=[fc.file_path for fc in stats.file_changes] if stats else [],
            file_change_details=stats.file_changes if stats else []
        )

        logger.info(f"Session summary generated: {len(message_summaries)} messages, "
                   f"{stats.total_files_modified if stats else 0} files modified")

        return summary

    def _generate_statistics(
        self,
        start_snapshot: Optional[str] = None,
        end_snapshot: Optional[str] = None
    ) -> SessionStatistics:
        """
        Generate comprehensive session statistics.

        Args:
            start_snapshot: Starting snapshot hash
            end_snapshot: Ending snapshot hash

        Returns:
            SessionStatistics with all metrics
        """
        # Get basic stats from session
        stats = self.session.stats
        duration = self.session.get_task_duration()

        # Calculate action success rate
        successful_actions = len([
            a for a in self.session.execution_log if a.get('success')
        ])
        failed_actions = len([
            a for a in self.session.execution_log if not a.get('success')
        ])
        total_actions = len(self.session.execution_log)
        success_rate = (successful_actions / total_actions * 100) if total_actions > 0 else 0.0

        # Calculate cache hit rate
        total_cache_ops = stats.get('cache_hits', 0) + stats.get('cache_misses', 0)
        cache_hit_rate = (stats.get('cache_hits', 0) / total_cache_ops * 100) if total_cache_ops > 0 else 0.0

        # Compute file changes from snapshots
        file_changes = []
        total_lines_added = 0
        total_lines_removed = 0
        total_files_modified = 0

        if self.snapshot_mgr and start_snapshot and end_snapshot:
            try:
                diffs = self.snapshot_mgr.diff_full(start_snapshot, end_snapshot)
                for diff in diffs:
                    file_change = FileChangeStat(
                        file_path=diff.file_path,
                        lines_added=diff.lines_added,
                        lines_removed=diff.lines_removed
                    )
                    file_changes.append(file_change)
                    total_lines_added += diff.lines_added
                    total_lines_removed += diff.lines_removed

                total_files_modified = len(file_changes)
                logger.debug(f"Computed diffs: {total_files_modified} files, "
                           f"+{total_lines_added}/-{total_lines_removed} lines")
            except Exception as e:
                logger.warning(f"Failed to compute snapshot diffs: {e}")

        return SessionStatistics(
            duration_seconds=duration,
            started_at=self.session._task_start_time.isoformat(),
            ended_at=datetime.now().isoformat(),
            total_iterations=stats.get('iterations', 0),
            total_tool_calls=stats.get('tool_calls', 0),
            vision_calls=stats.get('vision_calls', 0),
            retries=stats.get('retries', 0),
            successful_actions=successful_actions,
            failed_actions=failed_actions,
            success_rate=success_rate,
            cache_hits=stats.get('cache_hits', 0),
            cache_misses=stats.get('cache_misses', 0),
            cache_hit_rate=cache_hit_rate,
            total_files_modified=total_files_modified,
            total_lines_added=total_lines_added,
            total_lines_removed=total_lines_removed,
            net_lines_changed=total_lines_added - total_lines_removed,
            file_changes=file_changes,
            health_checks=stats.get('health_checks', 0),
            resource_checks=stats.get('resource_checks', 0),
            throttle_count=stats.get('throttle_count', 0),
            resource_warnings=stats.get('resource_warnings', 0),
            issues_count=len(self.session.last_issues)
        )

    def _generate_message_summaries(self) -> List[MessageSummary]:
        """
        Generate summaries for all messages in the session.

        Returns:
            List of MessageSummary objects
        """
        summaries = []

        for entry in self.session.execution_log:
            # Generate title and body
            title = self._generate_message_title(entry)
            body = self._generate_message_body(entry)

            summary = MessageSummary(
                role=entry.get('action', 'unknown'),
                timestamp=entry.get('timestamp', datetime.now().isoformat()),
                title=title,
                body=body,
                tool_name=entry.get('action'),
                success=entry.get('success'),
                metadata={
                    'attempt': entry.get('attempt', 1),
                    'has_error': 'error' in entry
                }
            )
            summaries.append(summary)

        return summaries

    def _generate_message_title(self, message: Dict[str, Any]) -> str:
        """
        Generate a brief title for a message.

        Args:
            message: Message/action entry

        Returns:
            Brief title (max 20 words)
        """
        action = message.get('action', 'unknown')
        success = message.get('success', False)
        status = "SUCCESS" if success else "FAILED"

        # Format based on action type
        if action == 'user':
            # User message - extract first part
            content = str(message.get('args', {}).get('message', ''))
            words = content.split()[:self.max_title_words]
            return ' '.join(words) + ('...' if len(content.split()) > self.max_title_words else '')
        else:
            # Tool call
            return f"{action} - {status}"

    def _generate_message_body(self, message: Dict[str, Any]) -> str:
        """
        Generate a body summary for a message.

        Args:
            message: Message/action entry

        Returns:
            Body summary (max 100 tokens ~ 400 chars)
        """
        max_chars = self.max_body_tokens * 4  # Rough approximation

        # Get content from different sources
        content = ""
        if 'result' in message and message.get('success'):
            content = str(message['result'])
        elif 'error' in message:
            content = f"Error: {message['error']}"
        elif 'args' in message:
            content = json.dumps(message['args'], indent=2)

        # Truncate if too long
        if len(content) > max_chars:
            content = content[:max_chars] + "..."

        return content

    def _generate_description(self) -> str:
        """
        Generate overall session description.

        Returns:
            Description string
        """
        stats = self.session.stats
        tool_calls = stats.get('tool_calls', 0)
        iterations = stats.get('iterations', 0)
        duration = self.session.get_task_duration()

        # Format duration
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        duration_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

        return (f"Agent session with {iterations} iterations, "
                f"{tool_calls} tool calls over {duration_str}")

    def generate_title(self, first_message: Optional[Dict[str, Any]]) -> str:
        """
        Generate session title from first user message.

        Args:
            first_message: First message in the session

        Returns:
            Brief headline (max 20 words)
        """
        if not first_message:
            return "Agent Session"

        # Extract user message content
        content = ""
        if 'args' in first_message:
            content = str(first_message['args'].get('message', ''))
        elif 'content' in first_message:
            content = str(first_message['content'])

        if not content:
            return "Agent Session"

        # Clean and truncate
        content = re.sub(r'\s+', ' ', content.strip())
        words = content.split()[:self.max_title_words]
        title = ' '.join(words)

        if len(content.split()) > self.max_title_words:
            title += '...'

        return title or "Agent Session"

    def generate_body(self, messages: List[Dict[str, Any]]) -> str:
        """
        Generate conversational context summary from messages.

        Args:
            messages: List of message entries

        Returns:
            Context summary (max 100 tokens ~ 400 chars)
        """
        max_chars = self.max_body_tokens * 4

        # Collect key information
        user_messages = [
            m for m in messages
            if m.get('action') == 'user' or m.get('role') == 'user'
        ]

        if not user_messages:
            return "Agent session with automated tasks"

        # Get first and last user messages
        first_msg = user_messages[0]
        last_msg = user_messages[-1] if len(user_messages) > 1 else None

        # Build summary
        summary_parts = []

        # First message
        first_content = str(first_msg.get('args', {}).get('message', first_msg.get('content', '')))
        summary_parts.append(first_content[:200])

        # Last message if different
        if last_msg and last_msg != first_msg:
            last_content = str(last_msg.get('args', {}).get('message', last_msg.get('content', '')))
            summary_parts.append(f"... {last_content[:200]}")

        summary = ' '.join(summary_parts)

        # Truncate to max chars
        if len(summary) > max_chars:
            summary = summary[:max_chars] + "..."

        return summary

    def compute_diffs(
        self,
        start_snapshot: str,
        end_snapshot: str
    ) -> Tuple[List[FileChangeStat], int, int]:
        """
        Compute file changes between two snapshots.

        Args:
            start_snapshot: Starting snapshot hash
            end_snapshot: Ending snapshot hash

        Returns:
            Tuple of (file_changes, total_added, total_removed)
        """
        if not self.snapshot_mgr:
            logger.warning("No SnapshotManager provided, cannot compute diffs")
            return [], 0, 0

        try:
            diffs = self.snapshot_mgr.diff_full(start_snapshot, end_snapshot)

            file_changes = []
            total_added = 0
            total_removed = 0

            for diff in diffs:
                file_change = FileChangeStat(
                    file_path=diff.file_path,
                    lines_added=diff.lines_added,
                    lines_removed=diff.lines_removed
                )
                file_changes.append(file_change)
                total_added += diff.lines_added
                total_removed += diff.lines_removed

            logger.info(f"Computed diffs: {len(file_changes)} files, "
                       f"+{total_added}/-{total_removed} lines")

            return file_changes, total_added, total_removed

        except Exception as e:
            logger.error(f"Failed to compute diffs: {e}")
            return [], 0, 0

    def save_summary(
        self,
        summary: SessionSummary,
        directory: Optional[Path] = None
    ) -> Path:
        """
        Save summary to disk as JSON.

        Args:
            summary: SessionSummary to save
            directory: Optional directory (defaults to memory/summaries/)

        Returns:
            Path to saved file
        """
        save_dir = directory or SUMMARY_DIR
        save_dir.mkdir(parents=True, exist_ok=True)

        # Use session ID as filename
        filename = f"{summary.session_id}.json"
        filepath = save_dir / filename

        try:
            # Update timestamp
            summary.updated_at = datetime.now().isoformat()

            # Save to file
            filepath.write_text(json.dumps(summary.to_dict(), indent=2))

            logger.info(f"Session summary saved to {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Failed to save summary: {e}")
            raise

    def load_summary(
        self,
        session_id: str,
        directory: Optional[Path] = None
    ) -> Optional[SessionSummary]:
        """
        Load summary from disk.

        Args:
            session_id: Session ID to load
            directory: Optional directory (defaults to memory/summaries/)

        Returns:
            SessionSummary if found, None otherwise
        """
        load_dir = directory or SUMMARY_DIR
        filepath = load_dir / f"{session_id}.json"

        if not filepath.exists():
            logger.warning(f"Summary not found for session {session_id}")
            return None

        try:
            data = json.loads(filepath.read_text())

            # Reconstruct SessionSummary
            # Convert statistics
            stats_data = data.get('statistics')
            if stats_data:
                # Convert file_changes
                file_changes = [
                    FileChangeStat(**fc) for fc in stats_data.get('file_changes', [])
                ]
                stats_data['file_changes'] = file_changes
                statistics = SessionStatistics(**stats_data)
            else:
                statistics = None

            # Convert messages
            messages = [
                MessageSummary(**msg) for msg in data.get('messages', [])
            ]

            # Convert file_change_details
            file_change_details = [
                FileChangeStat(**fc) for fc in data.get('file_change_details', [])
            ]

            summary = SessionSummary(
                session_id=data['session_id'],
                parent_session_id=data.get('parent_session_id'),
                child_session_ids=data.get('child_session_ids', []),
                title=data.get('title', ''),
                description=data.get('description', ''),
                goal_summary=data.get('goal_summary', ''),
                goal_keywords=data.get('goal_keywords', []),
                statistics=statistics,
                messages=messages,
                files_modified=data.get('files_modified', []),
                file_change_details=file_change_details,
                created_at=data.get('created_at', ''),
                updated_at=data.get('updated_at', ''),
                version=data.get('version', '1.0')
            )

            logger.info(f"Summary loaded for session {session_id}")
            return summary

        except Exception as e:
            logger.error(f"Failed to load summary: {e}")
            return None

    def update_summary_incremental(
        self,
        summary: SessionSummary,
        new_messages: Optional[List[Dict[str, Any]]] = None,
        new_snapshot: Optional[str] = None
    ) -> SessionSummary:
        """
        Update summary incrementally as session progresses.

        Args:
            summary: Existing SessionSummary to update
            new_messages: New messages to add
            new_snapshot: New snapshot hash for updated diffs

        Returns:
            Updated SessionSummary
        """
        logger.debug(f"Updating summary incrementally for session {summary.session_id}")

        # Add new message summaries
        if new_messages:
            for msg in new_messages:
                title = self._generate_message_title(msg)
                body = self._generate_message_body(msg)

                msg_summary = MessageSummary(
                    role=msg.get('action', 'unknown'),
                    timestamp=msg.get('timestamp', datetime.now().isoformat()),
                    title=title,
                    body=body,
                    tool_name=msg.get('action'),
                    success=msg.get('success'),
                    metadata={
                        'attempt': msg.get('attempt', 1),
                        'has_error': 'error' in msg
                    }
                )
                summary.messages.append(msg_summary)

        # Update statistics
        summary.statistics = self._generate_statistics(
            start_snapshot=None,  # Would need to track initial snapshot
            end_snapshot=new_snapshot
        )

        # Update timestamp
        summary.updated_at = datetime.now().isoformat()

        return summary


# Test functions
def test_session_summarizer():
    """Test session summarization functionality."""
    print("=" * 60)
    print("SESSION SUMMARIZER TEST")
    print("=" * 60)

    # Create test session
    from session_state import SessionState

    session = SessionState()
    session.set_goal(
        "Test automation for login flow",
        keywords=["login", "automation", "test"]
    )

    # Simulate some actions
    session.log_action(
        name="navigate",
        args={"url": "https://example.com/login"},
        success=True,
        result="Navigated successfully"
    )
    session.increment_stat('tool_calls')

    session.log_action(
        name="fill_field",
        args={"selector": "#username", "value": "testuser"},
        success=True,
        result="Field filled"
    )
    session.increment_stat('tool_calls')

    session.log_action(
        name="click",
        args={"selector": "#login-button"},
        success=True,
        result="Clicked successfully"
    )
    session.increment_stat('tool_calls')

    session.log_action(
        name="wait_for_selector",
        args={"selector": "#dashboard"},
        success=False,
        error="Timeout waiting for element",
        attempt=1
    )
    session.increment_stat('tool_calls')
    session.increment_stat('retries')

    # Create summarizer
    summarizer = SessionSummarizer(session)

    # Generate summary
    print("\nGenerating session summary...")
    summary = summarizer.summarize_session()

    print(f"\nSession ID: {summary.session_id}")
    print(f"Title: {summary.title}")
    print(f"Description: {summary.description}")
    print(f"Goal: {summary.goal_summary}")
    print(f"Keywords: {', '.join(summary.goal_keywords)}")

    if summary.statistics:
        print(f"\nStatistics:")
        print(f"  Duration: {summary.statistics.duration_seconds:.2f}s")
        print(f"  Tool Calls: {summary.statistics.total_tool_calls}")
        print(f"  Successful Actions: {summary.statistics.successful_actions}")
        print(f"  Failed Actions: {summary.statistics.failed_actions}")
        print(f"  Success Rate: {summary.statistics.success_rate:.1f}%")
        print(f"  Retries: {summary.statistics.retries}")

    print(f"\nMessages: {len(summary.messages)}")
    for i, msg in enumerate(summary.messages, 1):
        status = "SUCCESS" if msg.success else "FAILED" if msg.success is False else "N/A"
        print(f"  {i}. [{msg.tool_name}] {status} - {msg.title}")

    # Save summary
    print("\nSaving summary...")
    filepath = summarizer.save_summary(summary)
    print(f"Saved to: {filepath}")

    # Load summary back
    print("\nLoading summary...")
    loaded_summary = summarizer.load_summary(summary.session_id)
    if loaded_summary:
        print(f"Loaded successfully: {loaded_summary.title}")
        print(f"  Messages: {len(loaded_summary.messages)}")
        print(f"  Files modified: {loaded_summary.statistics.total_files_modified if loaded_summary.statistics else 0}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


def test_with_snapshots():
    """Test summarizer with snapshot diffing."""
    print("\n" + "=" * 60)
    print("SNAPSHOT DIFF TEST")
    print("=" * 60)

    from session_state import SessionState
    from snapshot_system import SnapshotManager
    import tempfile

    # Create temporary directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create some test files
        (tmppath / "file1.txt").write_text("Line 1\nLine 2\nLine 3\n")
        (tmppath / "file2.py").write_text("def hello():\n    print('hello')\n")

        # Initialize snapshot manager
        snapshot_mgr = SnapshotManager(working_dir=str(tmppath))
        snapshot_mgr.track()

        # Create initial snapshot
        snapshot1 = snapshot_mgr.snapshot("Initial state")
        print(f"Initial snapshot: {snapshot1[:8]}")

        # Modify files
        (tmppath / "file1.txt").write_text("Line 1\nLine 2 modified\nLine 3\nLine 4 added\n")
        (tmppath / "file2.py").write_text("def hello():\n    print('hello world')\n\ndef goodbye():\n    print('bye')\n")
        (tmppath / "file3.txt").write_text("New file\n")

        # Create final snapshot
        snapshot2 = snapshot_mgr.snapshot("After changes")
        print(f"Final snapshot: {snapshot2[:8]}")

        # Create session and summarizer
        session = SessionState()
        session.set_goal("Test file modifications")
        session.increment_stat('tool_calls', 5)
        session.increment_stat('iterations', 2)

        summarizer = SessionSummarizer(session, snapshot_mgr)

        # Generate summary with diffs
        print("\nGenerating summary with snapshot diffs...")
        summary = summarizer.summarize_session(
            start_snapshot=snapshot1,
            end_snapshot=snapshot2
        )

        if summary.statistics:
            print(f"\nFile Changes:")
            print(f"  Total files modified: {summary.statistics.total_files_modified}")
            print(f"  Total lines added: {summary.statistics.total_lines_added}")
            print(f"  Total lines removed: {summary.statistics.total_lines_removed}")
            print(f"  Net change: {summary.statistics.net_lines_changed}")

            print(f"\nFile Details:")
            for fc in summary.statistics.file_changes:
                print(f"  {fc.file_path}:")
                print(f"    +{fc.lines_added} -{fc.lines_removed} (net: {fc.net_change:+d})")

        # Save summary
        filepath = summarizer.save_summary(summary)
        print(f"\nSaved to: {filepath}")

    print("\n" + "=" * 60)
    print("SNAPSHOT TEST COMPLETE")
    print("=" * 60)


def test_incremental_updates():
    """Test incremental summary updates."""
    print("\n" + "=" * 60)
    print("INCREMENTAL UPDATE TEST")
    print("=" * 60)

    from session_state import SessionState

    # Create session
    session = SessionState()
    session.set_goal("Progressive task execution")

    # Initial actions
    session.log_action("step1", {"arg": "value"}, success=True)
    session.increment_stat('tool_calls')

    # Create initial summary
    summarizer = SessionSummarizer(session)
    summary = summarizer.summarize_session()

    print(f"Initial summary:")
    print(f"  Messages: {len(summary.messages)}")
    print(f"  Tool calls: {summary.statistics.total_tool_calls if summary.statistics else 0}")

    # Add more actions
    new_messages = []
    for i in range(3):
        msg = {
            'action': f'step{i+2}',
            'args': {'arg': f'value{i}'},
            'success': True,
            'timestamp': datetime.now().isoformat()
        }
        session.log_action(msg['action'], msg['args'], success=True)
        session.increment_stat('tool_calls')
        new_messages.append(msg)

    # Update summary incrementally
    print("\nUpdating summary incrementally...")
    summary = summarizer.update_summary_incremental(summary, new_messages=new_messages)

    print(f"\nUpdated summary:")
    print(f"  Messages: {len(summary.messages)}")
    print(f"  Tool calls: {summary.statistics.total_tool_calls if summary.statistics else 0}")

    # Save updated summary
    filepath = summarizer.save_summary(summary)
    print(f"\nSaved to: {filepath}")

    print("\n" + "=" * 60)
    print("INCREMENTAL TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    # Run all tests
    test_session_summarizer()
    test_with_snapshots()
    test_incremental_updates()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETE")
    print("=" * 60)
