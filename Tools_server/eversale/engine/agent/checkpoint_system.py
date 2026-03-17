"""
Checkpoint System for Agent Backend

This system saves and restores mid-task agent state (different from git snapshots).
Captures live session/task state including messages, browser state, tool execution,
and task progress for resuming interrupted tasks.

Features:
- Save checkpoint with session state, browser state, tool execution state, and task progress
- List checkpoints by task or time
- Restore from checkpoint (full or partial)
- Auto-checkpoint every N steps
- Checkpoint metadata (timestamp, description, step number)

Usage:
    from checkpoint_system import get_checkpoint_manager

    manager = get_checkpoint_manager()

    # Save checkpoint
    checkpoint_id = manager.save_checkpoint(
        session_state=session,
        browser_state={"url": "https://example.com", "tabs": [...]},
        description="Before form submission"
    )

    # List checkpoints
    checkpoints = manager.list_checkpoints(task_id="task_123")

    # Restore checkpoint
    restored = manager.restore_checkpoint(checkpoint_id)
"""

import json
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field, asdict
from loguru import logger
import base64


# Checkpoint storage directory
CHECKPOINT_DIR = Path("memory/checkpoints")
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class BrowserState:
    """Browser state snapshot."""
    current_url: Optional[str] = None
    active_tab_index: int = 0
    tabs: List[Dict[str, Any]] = field(default_factory=list)
    cookies: List[Dict[str, Any]] = field(default_factory=list)
    local_storage: Dict[str, Any] = field(default_factory=dict)
    session_storage: Dict[str, Any] = field(default_factory=dict)
    viewport: Dict[str, int] = field(default_factory=dict)
    screenshot_base64: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BrowserState':
        """Create from dictionary."""
        return cls(**data)


@dataclass
class ToolExecutionState:
    """Tool execution state snapshot."""
    pending_tools: List[Dict[str, Any]] = field(default_factory=list)
    completed_tools: List[Dict[str, Any]] = field(default_factory=list)
    failed_tools: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: Dict[str, Any] = field(default_factory=dict)
    execution_queue: List[str] = field(default_factory=list)
    retry_count: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolExecutionState':
        """Create from dictionary."""
        return cls(**data)


@dataclass
class TaskProgress:
    """Task progress snapshot."""
    todos: List[Dict[str, Any]] = field(default_factory=list)
    step_count: int = 0
    current_step: Optional[str] = None
    completed_steps: List[str] = field(default_factory=list)
    blocked_steps: List[Dict[str, Any]] = field(default_factory=list)
    subtasks: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskProgress':
        """Create from dictionary."""
        return cls(**data)


@dataclass
class Checkpoint:
    """Complete checkpoint snapshot."""
    checkpoint_id: str
    task_id: str
    session_id: str
    timestamp: str
    description: str
    step_number: int

    # State components
    session_state: Dict[str, Any]
    browser_state: Dict[str, Any]
    tool_execution_state: Dict[str, Any]
    task_progress: Dict[str, Any]

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    auto_checkpoint: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Checkpoint':
        """Create from dictionary."""
        return cls(**data)


class CheckpointManager:
    """
    Manages checkpoints for agent session state.

    Features:
    - Save and restore checkpoints
    - List and filter checkpoints
    - Auto-checkpoint at intervals
    - Cleanup old checkpoints
    - Partial restore (only specific components)
    """

    def __init__(
        self,
        checkpoint_dir: Optional[Path] = None,
        max_checkpoints_per_task: int = 50,
        auto_checkpoint_interval: int = 10
    ):
        """
        Initialize checkpoint manager.

        Args:
            checkpoint_dir: Directory for checkpoint storage (default: memory/checkpoints)
            max_checkpoints_per_task: Maximum checkpoints to keep per task
            auto_checkpoint_interval: Auto-checkpoint every N steps (0 to disable)
        """
        self.checkpoint_dir = checkpoint_dir or CHECKPOINT_DIR
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        self.max_checkpoints_per_task = max_checkpoints_per_task
        self.auto_checkpoint_interval = auto_checkpoint_interval

        # Index for fast lookups
        self._index: Dict[str, List[str]] = {}  # task_id -> [checkpoint_ids]
        self._build_index()

        # Step counter for auto-checkpoints
        self._step_counters: Dict[str, int] = {}  # task_id -> step_count

        logger.info(f"CheckpointManager initialized: {self.checkpoint_dir}")

    def _build_index(self):
        """Build index of checkpoints by task ID."""
        self._index.clear()

        for checkpoint_file in self.checkpoint_dir.glob("*.json"):
            try:
                data = json.loads(checkpoint_file.read_text())
                task_id = data.get("task_id")
                checkpoint_id = data.get("checkpoint_id")

                if task_id and checkpoint_id:
                    if task_id not in self._index:
                        self._index[task_id] = []
                    self._index[task_id].append(checkpoint_id)
            except Exception as e:
                logger.warning(f"Failed to index checkpoint {checkpoint_file}: {e}")

    def save_checkpoint(
        self,
        session_state: Any,
        task_id: Optional[str] = None,
        browser_state: Optional[Union[Dict[str, Any], BrowserState]] = None,
        tool_execution_state: Optional[Union[Dict[str, Any], ToolExecutionState]] = None,
        task_progress: Optional[Union[Dict[str, Any], TaskProgress]] = None,
        description: str = "",
        tags: Optional[List[str]] = None,
        auto: bool = False,
        include_screenshot: bool = False
    ) -> str:
        """
        Save a checkpoint of current state.

        Args:
            session_state: SessionState instance or dict
            task_id: Task identifier (optional, uses session.session_id if not provided)
            browser_state: BrowserState instance or dict
            tool_execution_state: ToolExecutionState instance or dict
            task_progress: TaskProgress instance or dict
            description: Human-readable description
            tags: List of tags for filtering
            auto: Whether this is an auto-checkpoint
            include_screenshot: Whether to include browser screenshot

        Returns:
            Checkpoint ID
        """
        checkpoint_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        # Extract session state
        if hasattr(session_state, 'export_session'):
            session_data = session_state.export_session()
            session_id = session_state.session_id
            actual_task_id = task_id or session_id
        elif isinstance(session_state, dict):
            session_data = session_state
            session_id = session_data.get('session_id', 'unknown')
            actual_task_id = task_id or session_id
        else:
            raise ValueError("session_state must be SessionState instance or dict")

        # Extract browser state
        if browser_state is None:
            browser_data = BrowserState().to_dict()
        elif isinstance(browser_state, BrowserState):
            browser_data = browser_state.to_dict()
        elif isinstance(browser_state, dict):
            browser_data = BrowserState.from_dict(browser_state).to_dict()
        else:
            browser_data = BrowserState().to_dict()

        # Extract tool execution state
        if tool_execution_state is None:
            tool_data = ToolExecutionState().to_dict()
        elif isinstance(tool_execution_state, ToolExecutionState):
            tool_data = tool_execution_state.to_dict()
        elif isinstance(tool_execution_state, dict):
            tool_data = ToolExecutionState.from_dict(tool_execution_state).to_dict()
        else:
            tool_data = ToolExecutionState().to_dict()

        # Extract task progress
        if task_progress is None:
            progress_data = TaskProgress().to_dict()
        elif isinstance(task_progress, TaskProgress):
            progress_data = task_progress.to_dict()
        elif isinstance(task_progress, dict):
            progress_data = TaskProgress.from_dict(task_progress).to_dict()
        else:
            progress_data = TaskProgress().to_dict()

        # Determine step number
        step_number = self._step_counters.get(actual_task_id, 0)

        # Create checkpoint
        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            task_id=actual_task_id,
            session_id=session_id,
            timestamp=timestamp,
            description=description,
            step_number=step_number,
            session_state=session_data,
            browser_state=browser_data,
            tool_execution_state=tool_data,
            task_progress=progress_data,
            metadata={
                'created_at': timestamp,
                'include_screenshot': include_screenshot,
                'session_duration': session_data.get('timestamps', {}).get('duration_seconds', 0)
            },
            tags=tags or [],
            auto_checkpoint=auto
        )

        # Save to file
        checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.json"
        try:
            checkpoint_file.write_text(json.dumps(checkpoint.to_dict(), indent=2))

            # Update index
            if actual_task_id not in self._index:
                self._index[actual_task_id] = []
            self._index[actual_task_id].append(checkpoint_id)

            # Cleanup old checkpoints if needed
            self._cleanup_old_checkpoints(actual_task_id)

            logger.info(
                f"Checkpoint saved: {checkpoint_id} "
                f"(task: {actual_task_id}, step: {step_number}, auto: {auto})"
            )

            return checkpoint_id

        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            raise

    def restore_checkpoint(
        self,
        checkpoint_id: str,
        components: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Restore checkpoint state.

        Args:
            checkpoint_id: Checkpoint ID to restore
            components: Optional list of components to restore
                       (e.g., ['session_state', 'browser_state'])
                       If None, restores all components

        Returns:
            Dictionary with restored state components
        """
        checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.json"

        if not checkpoint_file.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_id}")

        try:
            data = json.loads(checkpoint_file.read_text())
            checkpoint = Checkpoint.from_dict(data)

            # Determine which components to restore
            if components is None:
                components = ['session_state', 'browser_state', 'tool_execution_state', 'task_progress']

            restored = {
                'checkpoint_id': checkpoint.checkpoint_id,
                'task_id': checkpoint.task_id,
                'session_id': checkpoint.session_id,
                'timestamp': checkpoint.timestamp,
                'description': checkpoint.description,
                'step_number': checkpoint.step_number,
                'metadata': checkpoint.metadata
            }

            # Restore requested components
            if 'session_state' in components:
                restored['session_state'] = checkpoint.session_state

            if 'browser_state' in components:
                restored['browser_state'] = BrowserState.from_dict(checkpoint.browser_state)

            if 'tool_execution_state' in components:
                restored['tool_execution_state'] = ToolExecutionState.from_dict(
                    checkpoint.tool_execution_state
                )

            if 'task_progress' in components:
                restored['task_progress'] = TaskProgress.from_dict(checkpoint.task_progress)

            logger.info(
                f"Checkpoint restored: {checkpoint_id} "
                f"(components: {', '.join(components)})"
            )

            return restored

        except Exception as e:
            logger.error(f"Failed to restore checkpoint: {e}")
            raise

    def list_checkpoints(
        self,
        task_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        auto_only: bool = False,
        manual_only: bool = False,
        limit: Optional[int] = None,
        sort_by: str = 'timestamp',
        ascending: bool = False
    ) -> List[Dict[str, Any]]:
        """
        List checkpoints with optional filtering.

        Args:
            task_id: Filter by task ID
            tags: Filter by tags (any match)
            auto_only: Only auto-checkpoints
            manual_only: Only manual checkpoints
            limit: Maximum number of results
            sort_by: Sort field ('timestamp', 'step_number', 'task_id')
            ascending: Sort order

        Returns:
            List of checkpoint metadata
        """
        checkpoints = []

        # Get checkpoint IDs to scan
        if task_id:
            checkpoint_ids = self._index.get(task_id, [])
        else:
            checkpoint_ids = []
            for ids in self._index.values():
                checkpoint_ids.extend(ids)

        # Load and filter checkpoints
        for checkpoint_id in checkpoint_ids:
            checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.json"

            if not checkpoint_file.exists():
                continue

            try:
                data = json.loads(checkpoint_file.read_text())

                # Apply filters
                if auto_only and not data.get('auto_checkpoint', False):
                    continue

                if manual_only and data.get('auto_checkpoint', False):
                    continue

                if tags and not any(tag in data.get('tags', []) for tag in tags):
                    continue

                # Extract metadata
                metadata = {
                    'checkpoint_id': data['checkpoint_id'],
                    'task_id': data['task_id'],
                    'session_id': data['session_id'],
                    'timestamp': data['timestamp'],
                    'description': data['description'],
                    'step_number': data['step_number'],
                    'tags': data.get('tags', []),
                    'auto_checkpoint': data.get('auto_checkpoint', False),
                    'metadata': data.get('metadata', {})
                }

                checkpoints.append(metadata)

            except Exception as e:
                logger.warning(f"Failed to load checkpoint {checkpoint_id}: {e}")

        # Sort checkpoints
        reverse = not ascending
        if sort_by == 'timestamp':
            checkpoints.sort(key=lambda x: x['timestamp'], reverse=reverse)
        elif sort_by == 'step_number':
            checkpoints.sort(key=lambda x: x['step_number'], reverse=reverse)
        elif sort_by == 'task_id':
            checkpoints.sort(key=lambda x: x['task_id'], reverse=reverse)

        # Apply limit
        if limit:
            checkpoints = checkpoints[:limit]

        return checkpoints

    def delete_checkpoint(self, checkpoint_id: str):
        """
        Delete a checkpoint.

        Args:
            checkpoint_id: Checkpoint ID to delete
        """
        checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.json"

        if not checkpoint_file.exists():
            logger.warning(f"Checkpoint not found: {checkpoint_id}")
            return

        try:
            # Load to get task_id for index update
            data = json.loads(checkpoint_file.read_text())
            task_id = data.get('task_id')

            # Delete file
            checkpoint_file.unlink()

            # Update index
            if task_id and task_id in self._index:
                self._index[task_id] = [
                    cid for cid in self._index[task_id] if cid != checkpoint_id
                ]

            logger.info(f"Checkpoint deleted: {checkpoint_id}")

        except Exception as e:
            logger.error(f"Failed to delete checkpoint: {e}")
            raise

    def _cleanup_old_checkpoints(self, task_id: str):
        """
        Remove old checkpoints if exceeding max limit.

        Args:
            task_id: Task ID to cleanup
        """
        checkpoint_ids = self._index.get(task_id, [])

        if len(checkpoint_ids) <= self.max_checkpoints_per_task:
            return

        # Get all checkpoints for this task with timestamps
        checkpoints_with_time = []
        for checkpoint_id in checkpoint_ids:
            checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.json"
            if checkpoint_file.exists():
                try:
                    data = json.loads(checkpoint_file.read_text())
                    checkpoints_with_time.append({
                        'id': checkpoint_id,
                        'timestamp': data['timestamp'],
                        'auto': data.get('auto_checkpoint', False)
                    })
                except Exception:
                    continue

        # Sort by timestamp (oldest first)
        checkpoints_with_time.sort(key=lambda x: x['timestamp'])

        # Keep manual checkpoints, delete oldest auto-checkpoints
        to_delete = []
        auto_count = sum(1 for c in checkpoints_with_time if c['auto'])

        if auto_count > self.max_checkpoints_per_task // 2:
            # Delete oldest auto-checkpoints
            for checkpoint in checkpoints_with_time:
                if checkpoint['auto']:
                    to_delete.append(checkpoint['id'])
                    if len(checkpoints_with_time) - len(to_delete) <= self.max_checkpoints_per_task:
                        break

        # Delete old checkpoints
        for checkpoint_id in to_delete:
            try:
                self.delete_checkpoint(checkpoint_id)
            except Exception as e:
                logger.warning(f"Failed to delete old checkpoint {checkpoint_id}: {e}")

    def auto_checkpoint_if_needed(
        self,
        session_state: Any,
        task_id: Optional[str] = None,
        browser_state: Optional[Union[Dict[str, Any], BrowserState]] = None,
        tool_execution_state: Optional[Union[Dict[str, Any], ToolExecutionState]] = None,
        task_progress: Optional[Union[Dict[str, Any], TaskProgress]] = None
    ) -> Optional[str]:
        """
        Auto-checkpoint if interval reached.

        Args:
            session_state: SessionState instance or dict
            task_id: Task identifier
            browser_state: BrowserState instance or dict
            tool_execution_state: ToolExecutionState instance or dict
            task_progress: TaskProgress instance or dict

        Returns:
            Checkpoint ID if checkpoint created, None otherwise
        """
        if self.auto_checkpoint_interval == 0:
            return None

        # Get task ID
        if hasattr(session_state, 'session_id'):
            actual_task_id = task_id or session_state.session_id
        elif isinstance(session_state, dict):
            actual_task_id = task_id or session_state.get('session_id', 'unknown')
        else:
            return None

        # Increment step counter
        self._step_counters[actual_task_id] = self._step_counters.get(actual_task_id, 0) + 1
        current_step = self._step_counters[actual_task_id]

        # Check if checkpoint needed
        if current_step % self.auto_checkpoint_interval == 0:
            checkpoint_id = self.save_checkpoint(
                session_state=session_state,
                task_id=actual_task_id,
                browser_state=browser_state,
                tool_execution_state=tool_execution_state,
                task_progress=task_progress,
                description=f"Auto-checkpoint at step {current_step}",
                auto=True
            )
            return checkpoint_id

        return None

    def get_latest_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent checkpoint for a task.

        Args:
            task_id: Task ID

        Returns:
            Checkpoint metadata or None if no checkpoints exist
        """
        checkpoints = self.list_checkpoints(
            task_id=task_id,
            limit=1,
            sort_by='timestamp',
            ascending=False
        )

        return checkpoints[0] if checkpoints else None

    def restore_session_state(self, checkpoint_id: str) -> Any:
        """
        Restore SessionState from checkpoint.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            SessionState instance (requires SessionState class to be imported)
        """
        restored = self.restore_checkpoint(checkpoint_id, components=['session_state'])

        # Try to import and create SessionState
        try:
            from session_state import SessionState

            session = SessionState()
            session.import_session(restored['session_state'])

            logger.info(f"SessionState restored from checkpoint: {checkpoint_id}")
            return session

        except ImportError:
            logger.warning("SessionState class not available, returning raw data")
            return restored['session_state']

    async def save_checkpoint_async(self, *args, **kwargs) -> str:
        """Async version of save_checkpoint."""
        return await asyncio.to_thread(self.save_checkpoint, *args, **kwargs)

    async def restore_checkpoint_async(self, *args, **kwargs) -> Dict[str, Any]:
        """Async version of restore_checkpoint."""
        return await asyncio.to_thread(self.restore_checkpoint, *args, **kwargs)

    async def list_checkpoints_async(self, *args, **kwargs) -> List[Dict[str, Any]]:
        """Async version of list_checkpoints."""
        return await asyncio.to_thread(self.list_checkpoints, *args, **kwargs)


# Singleton instance
_checkpoint_manager: Optional[CheckpointManager] = None


def get_checkpoint_manager(
    checkpoint_dir: Optional[Path] = None,
    max_checkpoints_per_task: int = 50,
    auto_checkpoint_interval: int = 10
) -> CheckpointManager:
    """
    Get or create singleton CheckpointManager instance.

    Args:
        checkpoint_dir: Directory for checkpoint storage
        max_checkpoints_per_task: Maximum checkpoints per task
        auto_checkpoint_interval: Auto-checkpoint interval (steps)

    Returns:
        CheckpointManager instance
    """
    global _checkpoint_manager

    if _checkpoint_manager is None:
        _checkpoint_manager = CheckpointManager(
            checkpoint_dir=checkpoint_dir,
            max_checkpoints_per_task=max_checkpoints_per_task,
            auto_checkpoint_interval=auto_checkpoint_interval
        )

    return _checkpoint_manager


# Basic test
if __name__ == "__main__":
    print("Testing Checkpoint System...")

    # Test 1: Create checkpoint manager
    print("\n1. Creating checkpoint manager...")
    manager = get_checkpoint_manager(auto_checkpoint_interval=5)
    print(f"   Manager created: {manager.checkpoint_dir}")

    # Test 2: Create mock session state
    print("\n2. Creating mock session state...")
    mock_session = {
        'session_id': 'test-session-123',
        'messages': [
            {'role': 'user', 'content': 'Test message 1'},
            {'role': 'assistant', 'content': 'Response 1'}
        ],
        'stats': {'iterations': 5, 'tool_calls': 10},
        'timestamps': {'task_start': datetime.now().isoformat(), 'duration_seconds': 30}
    }
    print(f"   Session ID: {mock_session['session_id']}")

    # Test 3: Save manual checkpoint
    print("\n3. Saving manual checkpoint...")
    checkpoint_id = manager.save_checkpoint(
        session_state=mock_session,
        browser_state=BrowserState(
            current_url="https://example.com",
            tabs=[{'url': 'https://example.com', 'title': 'Example'}]
        ),
        tool_execution_state=ToolExecutionState(
            completed_tools=[{'name': 'navigate', 'result': 'success'}]
        ),
        task_progress=TaskProgress(
            todos=[{'content': 'Test todo', 'status': 'pending'}],
            step_count=3
        ),
        description="Test checkpoint with browser state",
        tags=['test', 'manual']
    )
    print(f"   Checkpoint ID: {checkpoint_id}")

    # Test 4: Auto-checkpoint
    print("\n4. Testing auto-checkpoint...")
    for i in range(10):
        auto_id = manager.auto_checkpoint_if_needed(
            session_state=mock_session,
            browser_state={'current_url': f'https://example.com/page{i}'}
        )
        if auto_id:
            print(f"   Auto-checkpoint created at step {(i+1)}: {auto_id}")

    # Test 5: List checkpoints
    print("\n5. Listing checkpoints...")
    checkpoints = manager.list_checkpoints(task_id='test-session-123')
    print(f"   Found {len(checkpoints)} checkpoints:")
    for cp in checkpoints:
        print(f"     - {cp['checkpoint_id'][:8]}... Step {cp['step_number']}: {cp['description']}")

    # Test 6: List auto-checkpoints only
    print("\n6. Listing auto-checkpoints only...")
    auto_checkpoints = manager.list_checkpoints(
        task_id='test-session-123',
        auto_only=True
    )
    print(f"   Found {len(auto_checkpoints)} auto-checkpoints")

    # Test 7: Restore checkpoint
    print("\n7. Restoring checkpoint...")
    restored = manager.restore_checkpoint(checkpoint_id)
    print(f"   Restored session ID: {restored['session_id']}")
    print(f"   Browser URL: {restored['browser_state'].current_url}")
    print(f"   Completed tools: {len(restored['tool_execution_state'].completed_tools)}")
    print(f"   Todos: {len(restored['task_progress'].todos)}")

    # Test 8: Partial restore
    print("\n8. Partial restore (browser state only)...")
    partial = manager.restore_checkpoint(checkpoint_id, components=['browser_state'])
    print(f"   Restored components: {list(partial.keys())}")
    print(f"   Browser URL: {partial['browser_state'].current_url}")

    # Test 9: Get latest checkpoint
    print("\n9. Getting latest checkpoint...")
    latest = manager.get_latest_checkpoint('test-session-123')
    if latest:
        print(f"   Latest checkpoint: {latest['checkpoint_id'][:8]}...")
        print(f"   Description: {latest['description']}")
        print(f"   Timestamp: {latest['timestamp']}")

    # Test 10: Async operations
    print("\n10. Testing async operations...")
    async def test_async():
        async_id = await manager.save_checkpoint_async(
            session_state=mock_session,
            description="Async checkpoint test"
        )
        print(f"   Async checkpoint ID: {async_id}")

        async_restored = await manager.restore_checkpoint_async(async_id)
        print(f"   Async restored session ID: {async_restored['session_id']}")

        async_list = await manager.list_checkpoints_async(task_id='test-session-123')
        print(f"   Async list found {len(async_list)} checkpoints")

    asyncio.run(test_async())

    # Test 11: Cleanup
    print("\n11. Cleanup test checkpoints...")
    for checkpoint in checkpoints:
        manager.delete_checkpoint(checkpoint['checkpoint_id'])
    remaining = manager.list_checkpoints(task_id='test-session-123')
    print(f"   Remaining checkpoints: {len(remaining)}")

    print("\nAll tests completed successfully!")
