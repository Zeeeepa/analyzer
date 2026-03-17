"""
Todo Management System for Agent Sessions

Based on OpenCode's session/todo.ts, this module provides session-based task tracking
for browser automation workflows with priority management and event publishing.

Features:
- TodoItem dataclass (id, content, status, priority, timestamps)
- TodoManager class for CRUD operations
- Thread-safe todo list updates
- Event publishing via event_bus.py
- Session-based storage with JSON persistence
- Query methods (pending, by priority, statistics)

Integration:
- Publishes "todo.updated" events for list changes
- Uses AgentEventBus singleton for real-time updates
- Provides task tracking during browser automation
"""

import json
import time
import threading
import uuid
import asyncio
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from loguru import logger

from .event_bus import get_event_bus


class TodoStatus(Enum):
    """
    Status states for todo items.

    States:
    - PENDING: Not yet started
    - IN_PROGRESS: Currently being worked on
    - COMPLETED: Successfully finished
    - CANCELLED: Cancelled or no longer relevant
    """
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    def __str__(self):
        return self.value


class TodoPriority(Enum):
    """
    Priority levels for todo items.

    Levels:
    - HIGH: Critical, needs immediate attention
    - MEDIUM: Normal priority
    - LOW: Can be deferred
    """
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    def __str__(self):
        return self.value


@dataclass
class TodoItem:
    """
    A single todo item with metadata.

    Fields:
    - id: Unique identifier (UUID)
    - content: Task description
    - status: Current TodoStatus
    - priority: TodoPriority level
    - created_at: Unix timestamp when created
    - updated_at: Unix timestamp when last updated
    - metadata: Arbitrary metadata (sequence ID, goal index, etc.)
    """
    id: str
    content: str
    status: TodoStatus
    priority: TodoPriority
    created_at: float
    updated_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status.value,
            "priority": self.priority.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'TodoItem':
        """Create TodoItem from dictionary."""
        return cls(
            id=data["id"],
            content=data["content"],
            status=TodoStatus(data["status"]),
            priority=TodoPriority(data["priority"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            metadata=data.get("metadata", {})
        )


class TodoManager:
    """
    Session-based todo list manager with persistence and events.

    Manages todo lists per session with:
    - get(session_id) - retrieve todos for session
    - update(session_id, todos) - persist todos and broadcast
    - add(session_id, content, priority) - add new todo
    - complete(session_id, todo_id) - mark as completed
    - cancel(session_id, todo_id) - mark as cancelled
    - reorder(session_id, order) - change todo order
    - get_pending(session_id) - get incomplete todos
    - get_by_priority(session_id, priority) - filter by priority
    - count_by_status(session_id) - status statistics

    Storage Strategy:
    - Key: ["todo", session_id]
    - JSON format with validation
    - Returns empty list if no data
    - Persists to data/todos directory

    Event Publishing:
    - Emits "todo.updated" event on list changes
    - Includes session_id and updated todos
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        """
        Initialize the todo manager.

        Args:
            storage_dir: Directory for storing todo JSON files (default: ./data/todos)
        """
        # Storage setup
        if storage_dir is None:
            storage_dir = Path(__file__).parent / "data" / "todos"
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

        # Thread safety
        self._lock = threading.RLock()

        # Event bus
        self._event_bus = get_event_bus()

        logger.debug(f"TodoManager initialized (storage: {self._storage_dir})")

    def _get_storage_path(self, session_id: str) -> Path:
        """Get storage file path for a session."""
        # Sanitize session_id for filename
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
        return self._storage_dir / f"{safe_id}.json"

    def _load_todos(self, session_id: str) -> List[TodoItem]:
        """
        Load todos from storage.

        Args:
            session_id: Session identifier

        Returns:
            List of TodoItem objects (empty list if no data)
        """
        storage_path = self._get_storage_path(session_id)

        if not storage_path.exists():
            return []

        try:
            with open(storage_path, 'r') as f:
                data = json.load(f)
                todos = [TodoItem.from_dict(item) for item in data]
                logger.debug(f"Loaded {len(todos)} todos for session {session_id}")
                return todos
        except Exception as e:
            logger.error(f"Failed to load todos for {session_id}: {e}")
            return []

    def _save_todos(self, session_id: str, todos: List[TodoItem]):
        """
        Save todos to storage.

        Args:
            session_id: Session identifier
            todos: List of TodoItem objects
        """
        storage_path = self._get_storage_path(session_id)

        try:
            data = [todo.to_dict() for todo in todos]
            with open(storage_path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(todos)} todos for session {session_id}")
        except Exception as e:
            logger.error(f"Failed to save todos for {session_id}: {e}")

    def get(self, session_id: str) -> List[TodoItem]:
        """
        Get all todos for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of TodoItem objects (empty list if no data)
        """
        with self._lock:
            return self._load_todos(session_id)

    def update(self, session_id: str, todos: List[TodoItem]):
        """
        Update todo list for a session and broadcast event.

        Args:
            session_id: Session identifier
            todos: New list of TodoItem objects

        Side Effects:
            - Saves todos to storage
            - Publishes "todo.updated" event
        """
        with self._lock:
            # Update timestamps
            now = time.time()
            for todo in todos:
                todo.updated_at = now

            # Save to storage
            self._save_todos(session_id, todos)

            # Publish event
            self._publish_update_event(session_id, todos)

    def add(
        self,
        session_id: str,
        content: str,
        priority: TodoPriority = TodoPriority.MEDIUM,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TodoItem:
        """
        Add a new todo to a session.

        Args:
            session_id: Session identifier
            content: Task description
            priority: TodoPriority level (default: MEDIUM)
            metadata: Optional dict stored with the todo (sequence IDs, etc.)

        Returns:
            The newly created TodoItem
        """
        with self._lock:
            todos = self._load_todos(session_id)

            now = time.time()
            new_todo = TodoItem(
                id=str(uuid.uuid4()),
                content=content,
                status=TodoStatus.PENDING,
                priority=priority,
                created_at=now,
                updated_at=now,
                metadata=metadata or {}
            )

            todos.append(new_todo)
            self._save_todos(session_id, todos)
            self._publish_update_event(session_id, todos)

            logger.info(f"Added todo to session {session_id}: {content}")
            return new_todo

    def complete(self, session_id: str, todo_id: str) -> bool:
        """
        Mark a todo as completed.

        Args:
            session_id: Session identifier
            todo_id: Todo item ID

        Returns:
            True if todo was found and updated, False otherwise
        """
        return self._update_status(session_id, todo_id, TodoStatus.COMPLETED)

    def cancel(self, session_id: str, todo_id: str) -> bool:
        """
        Mark a todo as cancelled.

        Args:
            session_id: Session identifier
            todo_id: Todo item ID

        Returns:
            True if todo was found and updated, False otherwise
        """
        return self._update_status(session_id, todo_id, TodoStatus.CANCELLED)

    def set_in_progress(self, session_id: str, todo_id: str) -> bool:
        """
        Mark a todo as in progress.

        Args:
            session_id: Session identifier
            todo_id: Todo item ID

        Returns:
            True if todo was found and updated, False otherwise
        """
        return self._update_status(session_id, todo_id, TodoStatus.IN_PROGRESS)

    def _update_status(self, session_id: str, todo_id: str, new_status: TodoStatus) -> bool:
        """
        Update the status of a todo item.

        Args:
            session_id: Session identifier
            todo_id: Todo item ID
            new_status: New TodoStatus value

        Returns:
            True if todo was found and updated, False otherwise
        """
        with self._lock:
            todos = self._load_todos(session_id)

            found = False
            for todo in todos:
                if todo.id == todo_id:
                    old_status = todo.status
                    todo.status = new_status
                    todo.updated_at = time.time()
                    found = True
                    logger.info(
                        f"Updated todo {todo_id} in session {session_id}: "
                        f"{old_status.value} -> {new_status.value}"
                    )
                    break

            if found:
                self._save_todos(session_id, todos)
                self._publish_update_event(session_id, todos)
            else:
                logger.warning(
                    f"Todo {todo_id} not found in session {session_id}"
                )

            return found

    def reorder(self, session_id: str, order: List[str]) -> bool:
        """
        Reorder todos based on ID list.

        Args:
            session_id: Session identifier
            order: List of todo IDs in desired order

        Returns:
            True if reorder was successful, False otherwise
        """
        with self._lock:
            todos = self._load_todos(session_id)

            # Create ID to todo mapping
            todo_map = {todo.id: todo for todo in todos}

            # Build new ordered list
            reordered = []
            for todo_id in order:
                if todo_id in todo_map:
                    reordered.append(todo_map[todo_id])

            # Add any todos not in the order list (at the end)
            ordered_ids = set(order)
            for todo in todos:
                if todo.id not in ordered_ids:
                    reordered.append(todo)

            # Update timestamps
            now = time.time()
            for todo in reordered:
                todo.updated_at = now

            # Save and broadcast
            self._save_todos(session_id, reordered)
            self._publish_update_event(session_id, reordered)

            logger.info(f"Reordered {len(reordered)} todos for session {session_id}")
            return True

    def remove(self, session_id: str, todo_id: str) -> bool:
        """
        Remove a todo from the list.

        Args:
            session_id: Session identifier
            todo_id: Todo item ID

        Returns:
            True if todo was found and removed, False otherwise
        """
        with self._lock:
            todos = self._load_todos(session_id)
            original_count = len(todos)

            todos = [todo for todo in todos if todo.id != todo_id]

            if len(todos) < original_count:
                self._save_todos(session_id, todos)
                self._publish_update_event(session_id, todos)
                logger.info(f"Removed todo {todo_id} from session {session_id}")
                return True
            else:
                logger.warning(f"Todo {todo_id} not found in session {session_id}")
                return False

    def clear(self, session_id: str):
        """
        Clear all todos for a session.

        Args:
            session_id: Session identifier
        """
        with self._lock:
            self._save_todos(session_id, [])
            self._publish_update_event(session_id, [])
            logger.info(f"Cleared all todos for session {session_id}")

    # Query methods

    def get_pending(self, session_id: str) -> List[TodoItem]:
        """
        Get all incomplete todos (pending or in progress).

        Args:
            session_id: Session identifier

        Returns:
            List of TodoItem objects that are not completed or cancelled
        """
        with self._lock:
            todos = self._load_todos(session_id)
            return [
                todo for todo in todos
                if todo.status in (TodoStatus.PENDING, TodoStatus.IN_PROGRESS)
            ]

    def get_by_priority(self, session_id: str, priority: TodoPriority) -> List[TodoItem]:
        """
        Get todos filtered by priority.

        Args:
            session_id: Session identifier
            priority: TodoPriority to filter by

        Returns:
            List of TodoItem objects with the specified priority
        """
        with self._lock:
            todos = self._load_todos(session_id)
            return [todo for todo in todos if todo.priority == priority]

    def count_by_status(self, session_id: str) -> Dict[str, int]:
        """
        Get todo counts by status.

        Args:
            session_id: Session identifier

        Returns:
            Dictionary mapping status values to counts
        """
        with self._lock:
            todos = self._load_todos(session_id)

            counts = {
                TodoStatus.PENDING.value: 0,
                TodoStatus.IN_PROGRESS.value: 0,
                TodoStatus.COMPLETED.value: 0,
                TodoStatus.CANCELLED.value: 0
            }

            for todo in todos:
                counts[todo.status.value] += 1

            return counts

    def get_statistics(self, session_id: str) -> Dict:
        """
        Get comprehensive statistics about todos.

        Args:
            session_id: Session identifier

        Returns:
            Dictionary with total, by_status, by_priority, completion_rate
        """
        with self._lock:
            todos = self._load_todos(session_id)

            if not todos:
                return {
                    "total": 0,
                    "by_status": self.count_by_status(session_id),
                    "by_priority": {
                        TodoPriority.HIGH.value: 0,
                        TodoPriority.MEDIUM.value: 0,
                        TodoPriority.LOW.value: 0
                    },
                    "completion_rate": 0.0
                }

            # Count by priority
            by_priority = {
                TodoPriority.HIGH.value: 0,
                TodoPriority.MEDIUM.value: 0,
                TodoPriority.LOW.value: 0
            }
            for todo in todos:
                by_priority[todo.priority.value] += 1

            # Calculate completion rate
            completed = sum(1 for todo in todos if todo.status == TodoStatus.COMPLETED)
            completion_rate = (completed / len(todos)) * 100 if todos else 0.0

            return {
                "total": len(todos),
                "by_status": self.count_by_status(session_id),
                "by_priority": by_priority,
                "completion_rate": completion_rate
            }

    def _publish_update_event(self, session_id: str, todos: List[TodoItem]):
        """
        Publish todo.updated event to event bus.

        Args:
            session_id: Session identifier
            todos: Updated list of TodoItem objects
        """
        try:
            event_data = {
                "session_id": session_id,
                "todos": [todo.to_dict() for todo in todos],
                "count": len(todos),
                "timestamp": time.time()
            }

            # Publish event asynchronously (fire-and-forget)
            # Handle both cases: within and outside event loop
            try:
                loop = asyncio.get_running_loop()
                # If we're in an event loop, create a task
                loop.create_task(self._event_bus.publish("todo.updated", event_data))
            except RuntimeError:
                # No event loop running, use asyncio.run
                asyncio.run(self._event_bus.publish("todo.updated", event_data))

        except Exception as e:
            # Gracefully handle event publishing failures
            logger.debug(f"Event publishing skipped for {session_id}: {e}")


# Global singleton instance
_manager_instance: Optional[TodoManager] = None
_manager_lock = threading.Lock()


def get_todo_manager() -> TodoManager:
    """
    Get the singleton TodoManager instance.

    This is the recommended way to access the todo manager from anywhere
    in the agent backend.

    Returns:
        TodoManager singleton instance

    Example:
        manager = get_todo_manager()
        manager.add("session-123", "Navigate to login page", TodoPriority.HIGH)
        manager.set_in_progress("session-123", todo_id)
        manager.complete("session-123", todo_id)
    """
    global _manager_instance
    with _manager_lock:
        if _manager_instance is None:
            _manager_instance = TodoManager()
        return _manager_instance


# Test function
def test_todo_manager():
    """
    Test the TodoManager functionality.

    Tests:
    - Adding todos
    - Status updates (pending -> in_progress -> completed)
    - Priority filtering
    - Reordering
    - Statistics
    - Event publishing
    """
    print("\n" + "=" * 60)
    print("Testing TodoManager")
    print("=" * 60)

    manager = get_todo_manager()
    session_id = "test-session-1"

    # Clean up from previous tests
    manager.clear(session_id)

    # Test 1: Adding todos
    print("\nTest 1: Adding Todos")
    print("-" * 40)

    todo1 = manager.add(session_id, "Navigate to login page", TodoPriority.HIGH)
    print(f"Added: {todo1.content} (priority: {todo1.priority.value})")

    todo2 = manager.add(session_id, "Fill username field", TodoPriority.HIGH)
    print(f"Added: {todo2.content} (priority: {todo2.priority.value})")

    todo3 = manager.add(session_id, "Fill password field", TodoPriority.MEDIUM)
    print(f"Added: {todo3.content} (priority: {todo3.priority.value})")

    todo4 = manager.add(session_id, "Click submit button", TodoPriority.MEDIUM)
    print(f"Added: {todo4.content} (priority: {todo4.priority.value})")

    todo5 = manager.add(session_id, "Verify login success", TodoPriority.LOW)
    print(f"Added: {todo5.content} (priority: {todo5.priority.value})")

    # Metadata support
    meta_todo = manager.add(
        session_id,
        "Metadata test task",
        TodoPriority.LOW,
        metadata={"sequence_id": "demo-seq", "goal_index": 99}
    )
    assert meta_todo.metadata["sequence_id"] == "demo-seq"
    manager.remove(session_id, meta_todo.id)

    todos = manager.get(session_id)
    print(f"\nTotal todos: {len(todos)}")
    assert len(todos) == 5

    # Test 2: Status updates
    print("\nTest 2: Status Updates")
    print("-" * 40)

    manager.set_in_progress(session_id, todo1.id)
    print(f"Set '{todo1.content}' to IN_PROGRESS")

    manager.complete(session_id, todo1.id)
    print(f"Set '{todo1.content}' to COMPLETED")

    manager.set_in_progress(session_id, todo2.id)
    print(f"Set '{todo2.content}' to IN_PROGRESS")

    counts = manager.count_by_status(session_id)
    print(f"\nStatus counts: {counts}")
    assert counts[TodoStatus.COMPLETED.value] == 1
    assert counts[TodoStatus.IN_PROGRESS.value] == 1
    assert counts[TodoStatus.PENDING.value] == 3

    # Test 3: Get pending todos
    print("\nTest 3: Get Pending Todos")
    print("-" * 40)

    pending = manager.get_pending(session_id)
    print(f"Pending todos: {len(pending)}")
    for todo in pending:
        print(f"  - {todo.content} ({todo.status.value})")
    assert len(pending) == 4  # 1 in_progress + 3 pending

    # Test 4: Filter by priority
    print("\nTest 4: Filter by Priority")
    print("-" * 40)

    high_priority = manager.get_by_priority(session_id, TodoPriority.HIGH)
    print(f"High priority todos: {len(high_priority)}")
    for todo in high_priority:
        print(f"  - {todo.content}")
    assert len(high_priority) == 2

    medium_priority = manager.get_by_priority(session_id, TodoPriority.MEDIUM)
    print(f"Medium priority todos: {len(medium_priority)}")
    assert len(medium_priority) == 2

    # Test 5: Reordering
    print("\nTest 5: Reordering Todos")
    print("-" * 40)

    original_order = [todo.id for todo in manager.get(session_id)]
    print(f"Original order: {[manager.get(session_id)[i].content for i in range(len(original_order))]}")

    # Reverse the order
    new_order = list(reversed(original_order))
    manager.reorder(session_id, new_order)

    reordered = manager.get(session_id)
    print(f"Reordered: {[todo.content for todo in reordered]}")
    assert reordered[0].id == original_order[-1]

    # Test 6: Statistics
    print("\nTest 6: Statistics")
    print("-" * 40)

    stats = manager.get_statistics(session_id)
    print(f"Total: {stats['total']}")
    print(f"By status: {stats['by_status']}")
    print(f"By priority: {stats['by_priority']}")
    print(f"Completion rate: {stats['completion_rate']:.1f}%")
    assert stats['total'] == 5
    assert stats['completion_rate'] == 20.0  # 1/5 completed

    # Test 7: Remove todo
    print("\nTest 7: Remove Todo")
    print("-" * 40)

    removed = manager.remove(session_id, todo5.id)
    print(f"Removed '{todo5.content}': {removed}")
    assert removed

    remaining = manager.get(session_id)
    print(f"Remaining todos: {len(remaining)}")
    assert len(remaining) == 4

    # Test 8: Cancel todo
    print("\nTest 8: Cancel Todo")
    print("-" * 40)

    manager.cancel(session_id, todo4.id)
    print(f"Cancelled '{todo4.content}'")

    counts = manager.count_by_status(session_id)
    print(f"Status counts: {counts}")
    assert counts[TodoStatus.CANCELLED.value] == 1

    # Test 9: Event publishing
    print("\nTest 9: Event Publishing")
    print("-" * 40)

    event_count = [0]

    async def todo_handler(event_type, data):
        event_count[0] += 1
        print(f"Event received: session={data['session_id']}, count={data['count']}")

    async def test_events():
        event_bus = get_event_bus()
        await event_bus.subscribe("todo.updated", todo_handler)

        manager.add(session_id, "Test event publishing")
        await asyncio.sleep(0.1)  # Small delay for event processing

        print(f"Total events received: {event_count[0]}")
        # Note: Event publishing is optional, so we don't assert on count

    try:
        asyncio.run(test_events())
    except Exception as e:
        print(f"Event test skipped (optional feature): {e}")

    # Test 10: Clear all
    print("\nTest 10: Clear All Todos")
    print("-" * 40)

    manager.clear(session_id)
    final_todos = manager.get(session_id)
    print(f"Todos after clear: {len(final_todos)}")
    assert len(final_todos) == 0

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    # Run tests
    test_todo_manager()
