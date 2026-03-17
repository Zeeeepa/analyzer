"""
Session Status Tracking System

Based on OpenCode's session/status.ts, this module provides real-time status tracking
for agent sessions with retry management, progress indicators, and event publishing.

Features:
- SessionStatus enum (IDLE, BUSY, RETRY, WAITING, ERROR)
- RetryStatus tracking with attempt counts and timing
- Thread-safe status updates
- Event publishing via event_bus.py
- Progress tracking with percentage and messages
- Automatic idle cleanup (only persist non-idle)
- Timestamp tracking for each status change

Integration:
- Publishes "session.status" events for status changes
- Publishes "session.idle" events for backward compatibility
- Uses AgentEventBus singleton for real-time updates
"""

import time
import threading
from enum import Enum
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from loguru import logger

# Try to import event bus, but don't fail if not available
try:
    from event_bus import get_event_bus
    EVENT_BUS_AVAILABLE = True
except ImportError:
    EVENT_BUS_AVAILABLE = False
    logger.warning("event_bus module not available, status events will not be published")


class SessionStatus(Enum):
    """
    Status states for agent sessions.

    States:
    - IDLE: No activity, waiting for work
    - BUSY: Actively processing a task
    - RETRY: Failed attempt, retrying with backoff
    - WAITING: Waiting for user input or external action
    - ERROR: Error state, requires intervention
    """
    IDLE = "idle"
    BUSY = "busy"
    RETRY = "retry"
    WAITING = "waiting"
    ERROR = "error"

    def __str__(self):
        return self.value


@dataclass
class RetryStatus:
    """
    Retry state for sessions that are retrying after failures.

    Tracks:
    - attempt: Current retry attempt number (1-indexed)
    - message: Reason for retry or error message
    - next_retry_at: Unix timestamp when next retry is scheduled
    """
    attempt: int
    message: str
    next_retry_at: float

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "attempt": self.attempt,
            "message": self.message,
            "next_retry_at": self.next_retry_at,
            "seconds_until_retry": max(0, self.next_retry_at - time.time())
        }


@dataclass
class ProgressInfo:
    """
    Progress information for long-running tasks.

    Tracks:
    - percentage: Progress percentage (0-100)
    - message: Current operation description
    - updated_at: Unix timestamp of last update
    """
    percentage: float
    message: str
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "percentage": self.percentage,
            "message": self.message,
            "updated_at": self.updated_at
        }


@dataclass
class SessionStatusEntry:
    """
    Full status entry for a session.

    Contains:
    - status: Current SessionStatus
    - updated_at: Unix timestamp of last status change
    - retry_info: Optional RetryStatus if status is RETRY
    - progress_info: Optional ProgressInfo for BUSY status
    - metadata: Additional context data
    """
    status: SessionStatus
    updated_at: float = field(default_factory=time.time)
    retry_info: Optional[RetryStatus] = None
    progress_info: Optional[ProgressInfo] = None
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "status": self.status.value,
            "updated_at": self.updated_at,
            "metadata": self.metadata
        }
        if self.retry_info:
            result["retry"] = self.retry_info.to_dict()
        if self.progress_info:
            result["progress"] = self.progress_info.to_dict()
        return result


class StatusTracker:
    """
    Thread-safe status tracker for agent sessions.

    Manages session statuses with:
    - get(session_id) - get current status, default IDLE
    - set(session_id, status) - update status, publish event
    - list_all() - get all session statuses
    - clear_idle() - cleanup idle entries
    - set_retry() - set retry state with attempt tracking
    - set_progress() - update progress for busy sessions
    - get_progress() - get current progress info

    Storage Strategy:
    - Only stores non-IDLE statuses in memory
    - Deletes idle entries to save memory
    - Returns IDLE by default for unknown sessions

    Event Publishing:
    - Emits "session.status" event on status change
    - Emits "session.idle" event when transitioning to IDLE
    - Events include full status entry data
    """

    def __init__(self):
        """Initialize the status tracker."""
        self._statuses: Dict[str, SessionStatusEntry] = {}
        self._lock = threading.RLock()
        self._event_bus = get_event_bus() if EVENT_BUS_AVAILABLE else None
        logger.debug("StatusTracker initialized")

    def get(self, session_id: str) -> SessionStatus:
        """
        Get current status for a session.

        Args:
            session_id: Session identifier

        Returns:
            SessionStatus enum value (defaults to IDLE if not found)
        """
        with self._lock:
            entry = self._statuses.get(session_id)
            if entry:
                return entry.status
            return SessionStatus.IDLE

    def get_entry(self, session_id: str) -> SessionStatusEntry:
        """
        Get full status entry for a session.

        Args:
            session_id: Session identifier

        Returns:
            SessionStatusEntry (creates default IDLE entry if not found)
        """
        with self._lock:
            entry = self._statuses.get(session_id)
            if entry:
                return entry
            return SessionStatusEntry(status=SessionStatus.IDLE)

    def set(self, session_id: str, status: SessionStatus, metadata: Dict = None):
        """
        Set status for a session and publish event.

        Args:
            session_id: Session identifier
            status: New SessionStatus value
            metadata: Optional metadata dictionary

        Side Effects:
            - Publishes "session.status" event
            - Publishes "session.idle" event if status is IDLE
            - Deletes entry from storage if status is IDLE
        """
        with self._lock:
            now = time.time()

            # Create or update entry
            if session_id in self._statuses:
                entry = self._statuses[session_id]
                old_status = entry.status
                entry.status = status
                entry.updated_at = now
                if metadata:
                    entry.metadata.update(metadata)

                # Clear retry/progress info when transitioning away from those states
                if status != SessionStatus.RETRY:
                    entry.retry_info = None
                if status != SessionStatus.BUSY:
                    entry.progress_info = None
            else:
                old_status = SessionStatus.IDLE
                entry = SessionStatusEntry(
                    status=status,
                    updated_at=now,
                    metadata=metadata or {}
                )
                self._statuses[session_id] = entry

            # Delete idle entries from storage (only persist non-idle)
            if status == SessionStatus.IDLE:
                if session_id in self._statuses:
                    del self._statuses[session_id]
                    logger.debug(f"Removed idle session from storage: {session_id}")

            # Log status change
            if old_status != status:
                logger.info(f"Session {session_id}: {old_status.value} -> {status.value}")

            # Publish events (async, non-blocking)
            self._publish_status_event(session_id, entry, old_status)

    def set_retry(
        self,
        session_id: str,
        attempt: int,
        message: str,
        next_retry_at: float,
        metadata: Dict = None
    ):
        """
        Set session to RETRY status with retry information.

        Args:
            session_id: Session identifier
            attempt: Current retry attempt number (1-indexed)
            message: Reason for retry
            next_retry_at: Unix timestamp for next retry
            metadata: Optional metadata dictionary
        """
        with self._lock:
            now = time.time()
            retry_info = RetryStatus(
                attempt=attempt,
                message=message,
                next_retry_at=next_retry_at
            )

            if session_id in self._statuses:
                entry = self._statuses[session_id]
                old_status = entry.status
                entry.status = SessionStatus.RETRY
                entry.updated_at = now
                entry.retry_info = retry_info
                if metadata:
                    entry.metadata.update(metadata)
            else:
                old_status = SessionStatus.IDLE
                entry = SessionStatusEntry(
                    status=SessionStatus.RETRY,
                    updated_at=now,
                    retry_info=retry_info,
                    metadata=metadata or {}
                )
                self._statuses[session_id] = entry

            logger.info(
                f"Session {session_id}: RETRY attempt {attempt}, "
                f"next retry in {max(0, next_retry_at - now):.1f}s"
            )

            # Publish events
            self._publish_status_event(session_id, entry, old_status)

    def set_progress(
        self,
        session_id: str,
        percentage: float,
        message: str,
        metadata: Dict = None
    ):
        """
        Update progress for a session (sets to BUSY if not already).

        Args:
            session_id: Session identifier
            percentage: Progress percentage (0-100)
            message: Current operation description
            metadata: Optional metadata dictionary
        """
        with self._lock:
            now = time.time()
            progress_info = ProgressInfo(
                percentage=max(0, min(100, percentage)),
                message=message,
                updated_at=now
            )

            if session_id in self._statuses:
                entry = self._statuses[session_id]
                old_status = entry.status
                # Only set to BUSY if not in ERROR or WAITING state
                if entry.status not in (SessionStatus.ERROR, SessionStatus.WAITING):
                    entry.status = SessionStatus.BUSY
                entry.updated_at = now
                entry.progress_info = progress_info
                if metadata:
                    entry.metadata.update(metadata)
            else:
                old_status = SessionStatus.IDLE
                entry = SessionStatusEntry(
                    status=SessionStatus.BUSY,
                    updated_at=now,
                    progress_info=progress_info,
                    metadata=metadata or {}
                )
                self._statuses[session_id] = entry

            logger.debug(
                f"Session {session_id}: progress {percentage:.1f}% - {message}"
            )

            # Publish events
            self._publish_status_event(session_id, entry, old_status)

    def get_progress(self, session_id: str) -> Optional[Tuple[float, str]]:
        """
        Get current progress for a session.

        Args:
            session_id: Session identifier

        Returns:
            Tuple of (percentage, message) or None if no progress info
        """
        with self._lock:
            entry = self._statuses.get(session_id)
            if entry and entry.progress_info:
                return (entry.progress_info.percentage, entry.progress_info.message)
            return None

    def list_all(self) -> Dict[str, Dict]:
        """
        Get all session statuses.

        Returns:
            Dictionary mapping session_id to status entry dict
        """
        with self._lock:
            return {
                session_id: entry.to_dict()
                for session_id, entry in self._statuses.items()
            }

    def clear_idle(self) -> int:
        """
        Remove all idle sessions from storage.

        Returns:
            Number of sessions cleared
        """
        with self._lock:
            idle_sessions = [
                session_id
                for session_id, entry in self._statuses.items()
                if entry.status == SessionStatus.IDLE
            ]

            for session_id in idle_sessions:
                del self._statuses[session_id]
                logger.debug(f"Cleared idle session: {session_id}")

            if idle_sessions:
                logger.info(f"Cleared {len(idle_sessions)} idle sessions")

            return len(idle_sessions)

    def clear_session(self, session_id: str):
        """
        Remove a specific session from tracking (sets to IDLE).

        Args:
            session_id: Session identifier
        """
        self.set(session_id, SessionStatus.IDLE)

    def get_all_by_status(self, status: SessionStatus) -> Dict[str, Dict]:
        """
        Get all sessions with a specific status.

        Args:
            status: SessionStatus to filter by

        Returns:
            Dictionary mapping session_id to status entry dict
        """
        with self._lock:
            return {
                session_id: entry.to_dict()
                for session_id, entry in self._statuses.items()
                if entry.status == status
            }

    def get_session_count(self) -> int:
        """
        Get total number of tracked sessions (excludes IDLE).

        Returns:
            Number of non-idle sessions
        """
        with self._lock:
            return len(self._statuses)

    def _publish_status_event(
        self,
        session_id: str,
        entry: SessionStatusEntry,
        old_status: SessionStatus
    ):
        """
        Publish status change events to event bus.

        Args:
            session_id: Session identifier
            entry: New status entry
            old_status: Previous status
        """
        if not self._event_bus:
            return  # Event bus not available, skip publishing

        try:
            # Prepare event data
            event_data = {
                "session_id": session_id,
                "status": entry.status.value,
                "old_status": old_status.value,
                "updated_at": entry.updated_at,
                "metadata": entry.metadata
            }

            # Add retry info if present
            if entry.retry_info:
                event_data["retry"] = entry.retry_info.to_dict()

            # Add progress info if present
            if entry.progress_info:
                event_data["progress"] = entry.progress_info.to_dict()

            # Try sync emit first (for AgentEventBus compatibility)
            if hasattr(self._event_bus, 'emit_sync'):
                self._event_bus.emit_sync("session.status", event_data)

                # Publish backward compatibility event for IDLE transitions
                if entry.status == SessionStatus.IDLE:
                    self._event_bus.emit_sync("session.idle", {
                        "session_id": session_id,
                        "previous_status": old_status.value,
                        "updated_at": entry.updated_at
                    })
            else:
                # Fallback: log the event instead
                logger.debug(
                    f"Event (no bus): session.status - "
                    f"{session_id}: {old_status.value} -> {entry.status.value}"
                )

        except Exception as e:
            logger.error(f"Failed to publish status event for {session_id}: {e}")


# Global singleton instance
_tracker_instance: Optional[StatusTracker] = None
_tracker_lock = threading.Lock()


def get_status_tracker() -> StatusTracker:
    """
    Get the singleton StatusTracker instance.

    This is the recommended way to access the status tracker from anywhere
    in the agent backend.

    Returns:
        StatusTracker singleton instance

    Example:
        tracker = get_status_tracker()
        tracker.set("session-123", SessionStatus.BUSY)
        tracker.set_progress("session-123", 50, "Processing data")
    """
    global _tracker_instance
    with _tracker_lock:
        if _tracker_instance is None:
            _tracker_instance = StatusTracker()
        return _tracker_instance


# Test function
def test_status_tracker():
    """
    Test the StatusTracker functionality.

    Tests:
    - Basic status tracking
    - Retry status with timing
    - Progress tracking
    - Idle cleanup
    - Event publishing
    """
    print("\n" + "=" * 60)
    print("Testing StatusTracker")
    print("=" * 60)

    tracker = get_status_tracker()

    # Test 1: Basic status tracking
    print("\nTest 1: Basic Status Tracking")
    print("-" * 40)
    session_id = "test-session-1"

    status = tracker.get(session_id)
    print(f"Initial status: {status} (should be IDLE)")
    assert status == SessionStatus.IDLE

    tracker.set(session_id, SessionStatus.BUSY)
    status = tracker.get(session_id)
    print(f"After set to BUSY: {status}")
    assert status == SessionStatus.BUSY

    # Test 2: Retry status
    print("\nTest 2: Retry Status")
    print("-" * 40)
    next_retry = time.time() + 30
    tracker.set_retry(session_id, attempt=1, message="Connection timeout", next_retry_at=next_retry)

    entry = tracker.get_entry(session_id)
    print(f"Status: {entry.status}")
    print(f"Retry attempt: {entry.retry_info.attempt}")
    print(f"Retry message: {entry.retry_info.message}")
    print(f"Seconds until retry: {entry.retry_info.to_dict()['seconds_until_retry']:.1f}")
    assert entry.status == SessionStatus.RETRY
    assert entry.retry_info.attempt == 1

    # Test 3: Progress tracking
    print("\nTest 3: Progress Tracking")
    print("-" * 40)
    tracker.set_progress(session_id, 25, "Loading data")
    progress = tracker.get_progress(session_id)
    print(f"Progress: {progress[0]:.1f}% - {progress[1]}")
    assert progress[0] == 25
    assert progress[1] == "Loading data"

    tracker.set_progress(session_id, 75, "Processing results")
    progress = tracker.get_progress(session_id)
    print(f"Updated progress: {progress[0]:.1f}% - {progress[1]}")
    assert progress[0] == 75

    # Test 4: List all sessions
    print("\nTest 4: List All Sessions")
    print("-" * 40)
    tracker.set("session-2", SessionStatus.WAITING)
    tracker.set("session-3", SessionStatus.ERROR, {"error": "Network failure"})

    all_statuses = tracker.list_all()
    print(f"Total tracked sessions: {len(all_statuses)}")
    for sid, entry in all_statuses.items():
        print(f"  {sid}: {entry['status']}")

    # Test 5: Filter by status
    print("\nTest 5: Filter by Status")
    print("-" * 40)
    busy_sessions = tracker.get_all_by_status(SessionStatus.BUSY)
    print(f"BUSY sessions: {len(busy_sessions)}")

    # Test 6: Idle cleanup
    print("\nTest 6: Idle Cleanup")
    print("-" * 40)
    tracker.set(session_id, SessionStatus.IDLE)
    tracker.set("session-2", SessionStatus.IDLE)

    cleared = tracker.clear_idle()
    print(f"Cleared {cleared} idle sessions")

    remaining = tracker.list_all()
    print(f"Remaining tracked sessions: {len(remaining)}")
    for sid, entry in remaining.items():
        print(f"  {sid}: {entry['status']}")

    # Test 7: Event subscription
    print("\nTest 7: Event Publishing")
    print("-" * 40)

    event_count = [0]

    def status_handler(event):
        event_count[0] += 1
        data = event.data
        print(f"Event received: {data['session_id']} -> {data['status']}")

    event_bus = get_event_bus()
    event_bus.subscribe("session.status", status_handler)

    tracker.set("event-test", SessionStatus.BUSY)
    tracker.set_progress("event-test", 50, "Halfway done")
    tracker.set("event-test", SessionStatus.IDLE)

    # Small delay to ensure events are processed
    time.sleep(0.1)

    print(f"Total events received: {event_count[0]}")

    # Test 8: Full entry serialization
    print("\nTest 8: Full Entry Serialization")
    print("-" * 40)
    tracker.set_progress("json-test", 80, "Almost complete", {"user_id": "123"})
    entry = tracker.get_entry("json-test")
    json_data = entry.to_dict()
    print(f"Serialized entry: {json_data}")
    assert "status" in json_data
    assert "progress" in json_data
    assert json_data["metadata"]["user_id"] == "123"

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    # Run tests
    test_status_tracker()
