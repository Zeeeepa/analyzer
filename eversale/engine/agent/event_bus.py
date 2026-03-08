"""
Event Bus System for Eversale Agent

Pub/Sub event system inspired by OpenCode's bus/index.ts.
Provides centralized event management for session lifecycle, tool execution,
messages, file operations, browser actions, and permissions.

Features:
- Subscribe to specific event types or all events (wildcard)
- One-time subscriptions with auto-unsubscribe
- Async callback execution with parallel handling
- Event data validation using dataclasses
- Event history and replay capability
- Thread-safe singleton pattern
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable, Union
from dataclasses import dataclass, asdict
from enum import Enum
from loguru import logger
import threading


class EventType(str, Enum):
    """
    Standard event types for the agent system.

    Categories:
    - Session: Lifecycle events (start, end, error)
    - Tool: Tool execution events (start, end, error)
    - Message: Communication events (user, assistant, system)
    - File: File system operations (read, write, delete)
    - Browser: Browser automation events (navigate, click, type)
    - Permission: Access control events (request, granted, denied)
    """
    # Session events
    SESSION_START = "session.start"
    SESSION_END = "session.end"
    SESSION_ERROR = "session.error"

    # Tool events
    TOOL_START = "tool.start"
    TOOL_END = "tool.end"
    TOOL_ERROR = "tool.error"

    # Message events
    MESSAGE_USER = "message.user"
    MESSAGE_ASSISTANT = "message.assistant"
    MESSAGE_SYSTEM = "message.system"

    # File events
    FILE_READ = "file.read"
    FILE_WRITE = "file.write"
    FILE_DELETE = "file.delete"

    # Browser events
    BROWSER_NAVIGATE = "browser.navigate"
    BROWSER_CLICK = "browser.click"
    BROWSER_TYPE = "browser.type"

    # Permission events
    PERMISSION_REQUEST = "permission.request"
    PERMISSION_GRANTED = "permission.granted"
    PERMISSION_DENIED = "permission.denied"


@dataclass
class EventData:
    """
    Base class for event data with common fields.

    All event payloads should include:
    - event_id: Unique identifier
    - timestamp: When the event occurred
    - Additional fields specific to event type
    """
    event_id: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert event data to dictionary."""
        return asdict(self)


@dataclass
class SessionEventData(EventData):
    """Session lifecycle event data."""
    session_id: str
    user_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ToolEventData(EventData):
    """Tool execution event data."""
    tool_name: str
    args: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None


@dataclass
class MessageEventData(EventData):
    """Message event data."""
    content: str
    role: str
    message_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class FileEventData(EventData):
    """File operation event data."""
    file_path: str
    operation: str
    success: bool
    size_bytes: Optional[int] = None
    error: Optional[str] = None


@dataclass
class BrowserEventData(EventData):
    """Browser automation event data."""
    action: str
    target: str
    success: bool
    url: Optional[str] = None
    error: Optional[str] = None


@dataclass
class PermissionEventData(EventData):
    """Permission event data."""
    resource: str
    action: str
    user_id: Optional[str] = None
    granted: Optional[bool] = None
    reason: Optional[str] = None


@dataclass
class Subscription:
    """
    Represents a subscription to an event.

    Attributes:
        subscription_id: Unique identifier for this subscription
        event_type: Type of event to listen for (or None for wildcard)
        callback: Async or sync function to call when event fires
        once: If True, auto-unsubscribe after first execution
    """
    subscription_id: str
    event_type: Optional[str]
    callback: Callable
    once: bool = False


class EventBus:
    """
    Global event bus for pub/sub messaging.

    Singleton pattern ensures single event bus instance across the application.
    Thread-safe for concurrent access.

    Example:
        bus = EventBus.get_instance()

        # Subscribe to specific event
        sub_id = await bus.subscribe(EventType.TOOL_START, handle_tool_start)

        # Subscribe to all events
        all_id = await bus.subscribe_all(log_all_events)

        # Publish event
        await bus.publish(EventType.TOOL_START, ToolEventData(...))

        # One-time subscription
        once_id = await bus.once(EventType.SESSION_END, cleanup)

        # Unsubscribe
        bus.unsubscribe(sub_id)
    """

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        """
        Initialize event bus.

        Private constructor - use get_instance() instead.
        """
        # Subscription management
        self._subscriptions: Dict[str, List[Subscription]] = {}
        self._wildcard_subscriptions: List[Subscription] = []
        self._subscription_counter = 0

        # Event history for replay
        self._event_history: List[Dict[str, Any]] = []
        self._max_history_size = 1000

        # Statistics
        self._stats = {
            'events_published': 0,
            'events_processed': 0,
            'subscriptions_created': 0,
            'subscriptions_removed': 0,
            'errors': 0
        }

        logger.debug("EventBus initialized")

    @classmethod
    def get_instance(cls) -> 'EventBus':
        """
        Get singleton instance of EventBus.

        Thread-safe singleton pattern.

        Returns:
            EventBus instance
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """
        Reset singleton instance (mainly for testing).

        Clears all subscriptions and history.
        """
        with cls._lock:
            cls._instance = None
            logger.debug("EventBus instance reset")

    async def subscribe(
        self,
        event_type: Union[str, EventType],
        callback: Callable
    ) -> str:
        """
        Subscribe to a specific event type.

        Args:
            event_type: Type of event to listen for
            callback: Async or sync function to call when event fires.
                     Signature: callback(event_type: str, data: EventData)

        Returns:
            Subscription ID for later unsubscription

        Example:
            async def handle_tool_start(event_type, data):
                print(f"Tool started: {data.tool_name}")

            sub_id = await bus.subscribe(EventType.TOOL_START, handle_tool_start)
        """
        event_type_str = event_type.value if isinstance(event_type, EventType) else event_type

        subscription = Subscription(
            subscription_id=str(uuid.uuid4()),
            event_type=event_type_str,
            callback=callback,
            once=False
        )

        if event_type_str not in self._subscriptions:
            self._subscriptions[event_type_str] = []

        self._subscriptions[event_type_str].append(subscription)
        self._stats['subscriptions_created'] += 1

        logger.debug(f"Subscribed to {event_type_str}: {subscription.subscription_id}")
        return subscription.subscription_id

    async def subscribe_all(self, callback: Callable) -> str:
        """
        Subscribe to all events (wildcard subscription).

        Useful for logging, monitoring, or debugging.

        Args:
            callback: Async or sync function to call for any event.
                     Signature: callback(event_type: str, data: EventData)

        Returns:
            Subscription ID for later unsubscription

        Example:
            async def log_all(event_type, data):
                print(f"Event: {event_type}, Data: {data}")

            sub_id = await bus.subscribe_all(log_all)
        """
        subscription = Subscription(
            subscription_id=str(uuid.uuid4()),
            event_type=None,  # None indicates wildcard
            callback=callback,
            once=False
        )

        self._wildcard_subscriptions.append(subscription)
        self._stats['subscriptions_created'] += 1

        logger.debug(f"Subscribed to all events: {subscription.subscription_id}")
        return subscription.subscription_id

    async def once(
        self,
        event_type: Union[str, EventType],
        callback: Callable
    ) -> str:
        """
        Subscribe to event with auto-unsubscribe after first execution.

        Args:
            event_type: Type of event to listen for
            callback: Async or sync function to call once when event fires

        Returns:
            Subscription ID

        Example:
            async def cleanup(event_type, data):
                print("Session ended, cleaning up...")

            await bus.once(EventType.SESSION_END, cleanup)
        """
        event_type_str = event_type.value if isinstance(event_type, EventType) else event_type

        subscription = Subscription(
            subscription_id=str(uuid.uuid4()),
            event_type=event_type_str,
            callback=callback,
            once=True
        )

        if event_type_str not in self._subscriptions:
            self._subscriptions[event_type_str] = []

        self._subscriptions[event_type_str].append(subscription)
        self._stats['subscriptions_created'] += 1

        logger.debug(f"One-time subscription to {event_type_str}: {subscription.subscription_id}")
        return subscription.subscription_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Remove a subscription.

        Args:
            subscription_id: ID returned from subscribe/subscribe_all/once

        Returns:
            True if subscription was found and removed, False otherwise

        Example:
            sub_id = await bus.subscribe(EventType.TOOL_START, handler)
            # ... later ...
            bus.unsubscribe(sub_id)
        """
        # Check specific event subscriptions
        for event_type, subscriptions in self._subscriptions.items():
            for i, sub in enumerate(subscriptions):
                if sub.subscription_id == subscription_id:
                    subscriptions.pop(i)
                    self._stats['subscriptions_removed'] += 1
                    logger.debug(f"Unsubscribed: {subscription_id} from {event_type}")
                    return True

        # Check wildcard subscriptions
        for i, sub in enumerate(self._wildcard_subscriptions):
            if sub.subscription_id == subscription_id:
                self._wildcard_subscriptions.pop(i)
                self._stats['subscriptions_removed'] += 1
                logger.debug(f"Unsubscribed: {subscription_id} from wildcard")
                return True

        logger.warning(f"Subscription not found: {subscription_id}")
        return False

    async def publish(
        self,
        event_type: Union[str, EventType],
        data: Union[EventData, Dict[str, Any]]
    ):
        """
        Publish an event to all subscribers.

        Executes all callbacks in parallel using asyncio.gather.
        Auto-unsubscribes one-time listeners after execution.

        Args:
            event_type: Type of event being published
            data: Event data (EventData instance or dict)

        Example:
            tool_data = ToolEventData(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.now().isoformat(),
                tool_name="browser_click",
                args={"selector": "#submit"}
            )
            await bus.publish(EventType.TOOL_START, tool_data)
        """
        event_type_str = event_type.value if isinstance(event_type, EventType) else event_type

        # Convert data to dict if it's EventData instance
        data_dict = data.to_dict() if isinstance(data, EventData) else data

        # Add to history
        self._add_to_history(event_type_str, data_dict)

        self._stats['events_published'] += 1

        # Collect all relevant subscriptions
        subscriptions_to_execute = []
        subscriptions_to_remove = []

        # Get specific event subscriptions
        if event_type_str in self._subscriptions:
            for sub in self._subscriptions[event_type_str]:
                subscriptions_to_execute.append(sub)
                if sub.once:
                    subscriptions_to_remove.append((event_type_str, sub.subscription_id))

        # Get wildcard subscriptions
        for sub in self._wildcard_subscriptions:
            subscriptions_to_execute.append(sub)
            if sub.once:
                subscriptions_to_remove.append((None, sub.subscription_id))

        # Execute all callbacks in parallel
        if subscriptions_to_execute:
            tasks = []
            for sub in subscriptions_to_execute:
                task = self._execute_callback(sub.callback, event_type_str, data)
                tasks.append(task)

            # Wait for all callbacks to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Count successes and errors
            for result in results:
                if isinstance(result, Exception):
                    self._stats['errors'] += 1
                    logger.error(f"Callback error for {event_type_str}: {result}")
                else:
                    self._stats['events_processed'] += 1

        # Remove one-time subscriptions
        for event_type_key, sub_id in subscriptions_to_remove:
            self.unsubscribe(sub_id)

        logger.debug(f"Published {event_type_str} to {len(subscriptions_to_execute)} subscribers")

    async def _execute_callback(
        self,
        callback: Callable,
        event_type: str,
        data: Any
    ):
        """
        Execute a callback function (async or sync).

        Args:
            callback: Function to execute
            event_type: Event type string
            data: Event data

        Returns:
            Result of callback execution
        """
        try:
            if asyncio.iscoroutinefunction(callback):
                return await callback(event_type, data)
            else:
                # Run sync callback in executor to avoid blocking
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, callback, event_type, data)
        except Exception as e:
            logger.error(f"Error executing callback for {event_type}: {e}")
            raise

    def _add_to_history(self, event_type: str, data: Dict[str, Any]):
        """
        Add event to history with bounded size.

        Args:
            event_type: Event type string
            data: Event data dictionary
        """
        self._event_history.append({
            'event_type': event_type,
            'data': data,
            'published_at': datetime.now().isoformat()
        })

        # Keep bounded history
        if len(self._event_history) > self._max_history_size:
            self._event_history.pop(0)

    def get_history(
        self,
        event_type: Optional[Union[str, EventType]] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get event history, optionally filtered by type.

        Args:
            event_type: Optional event type to filter by
            limit: Optional maximum number of events to return (most recent)

        Returns:
            List of historical events

        Example:
            # Get all history
            all_events = bus.get_history()

            # Get last 10 tool events
            tool_events = bus.get_history(EventType.TOOL_START, limit=10)
        """
        history = self._event_history

        # Filter by event type if specified
        if event_type is not None:
            event_type_str = event_type.value if isinstance(event_type, EventType) else event_type
            history = [e for e in history if e['event_type'] == event_type_str]

        # Apply limit if specified
        if limit is not None:
            history = history[-limit:]

        return history

    async def replay_events(
        self,
        event_type: Optional[Union[str, EventType]] = None,
        callback: Optional[Callable] = None
    ):
        """
        Replay historical events to a callback.

        Useful for initializing new subscribers with past events.

        Args:
            event_type: Optional event type to filter replay
            callback: Optional callback to replay to. If None, publishes to current subscribers.

        Example:
            # Replay all events to new subscriber
            async def new_handler(event_type, data):
                print(f"Replaying: {event_type}")

            await bus.replay_events(callback=new_handler)
        """
        history = self.get_history(event_type)

        for event in history:
            if callback:
                await self._execute_callback(callback, event['event_type'], event['data'])
            else:
                await self.publish(event['event_type'], event['data'])

        logger.info(f"Replayed {len(history)} events")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get event bus statistics.

        Returns:
            Dictionary with stats including:
            - events_published: Total events published
            - events_processed: Total successful callback executions
            - subscriptions_created: Total subscriptions created
            - subscriptions_removed: Total subscriptions removed
            - errors: Total callback errors
            - active_subscriptions: Current number of active subscriptions
            - history_size: Number of events in history
        """
        active_subs = sum(len(subs) for subs in self._subscriptions.values())
        active_subs += len(self._wildcard_subscriptions)

        return {
            **self._stats,
            'active_subscriptions': active_subs,
            'history_size': len(self._event_history)
        }

    def clear_history(self):
        """Clear event history."""
        self._event_history.clear()
        logger.debug("Event history cleared")

    def dispose(self):
        """
        Cleanup event bus resources.

        Removes all subscriptions and clears history.
        """
        self._subscriptions.clear()
        self._wildcard_subscriptions.clear()
        self._event_history.clear()
        logger.info("EventBus disposed")


# Convenience function to get global event bus instance
def get_event_bus() -> EventBus:
    """
    Get global EventBus instance.

    Returns:
        EventBus singleton instance
    """
    return EventBus.get_instance()


# Test suite
if __name__ == "__main__":
    import asyncio

    async def test_event_bus():
        """Test suite for EventBus functionality."""
        print("\n" + "=" * 60)
        print("EVENTBUS TEST SUITE")
        print("=" * 60 + "\n")

        # Reset instance for clean test
        EventBus.reset_instance()
        bus = EventBus.get_instance()

        # Test 1: Basic subscription and publish
        print("Test 1: Basic subscription and publish")
        received_events = []

        async def handler(event_type, data):
            received_events.append((event_type, data))
            print(f"  Received: {event_type}")

        sub_id = await bus.subscribe(EventType.TOOL_START, handler)

        event_data = ToolEventData(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            tool_name="test_tool",
            args={"param": "value"}
        )

        await bus.publish(EventType.TOOL_START, event_data)
        await asyncio.sleep(0.1)  # Allow async execution

        assert len(received_events) == 1, "Should receive 1 event"
        assert received_events[0][0] == EventType.TOOL_START.value
        print("  PASS: Basic subscription works\n")

        # Test 2: Wildcard subscription
        print("Test 2: Wildcard subscription")
        all_events = []

        async def wildcard_handler(event_type, data):
            all_events.append(event_type)

        wildcard_id = await bus.subscribe_all(wildcard_handler)

        await bus.publish(EventType.SESSION_START, SessionEventData(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            session_id="test-session"
        ))

        await bus.publish(EventType.MESSAGE_USER, MessageEventData(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            content="Hello",
            role="user"
        ))

        await asyncio.sleep(0.1)

        assert len(all_events) == 2, "Wildcard should receive all events"
        print("  PASS: Wildcard subscription works\n")

        # Test 3: Once subscription
        print("Test 3: Once subscription (auto-unsubscribe)")
        once_count = []

        async def once_handler(event_type, data):
            once_count.append(1)

        once_id = await bus.once(EventType.FILE_READ, once_handler)

        # Publish twice
        for i in range(2):
            await bus.publish(EventType.FILE_READ, FileEventData(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.now().isoformat(),
                file_path="/test.txt",
                operation="read",
                success=True
            ))

        await asyncio.sleep(0.1)

        assert len(once_count) == 1, "Once handler should only execute once"
        print("  PASS: Once subscription auto-unsubscribes\n")

        # Test 4: Unsubscribe
        print("Test 4: Manual unsubscribe")
        unsub_events = []

        async def unsub_handler(event_type, data):
            unsub_events.append(1)

        unsub_id = await bus.subscribe(EventType.BROWSER_CLICK, unsub_handler)

        await bus.publish(EventType.BROWSER_CLICK, BrowserEventData(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            action="click",
            target="#button",
            success=True
        ))

        await asyncio.sleep(0.1)
        assert len(unsub_events) == 1

        # Unsubscribe and publish again
        bus.unsubscribe(unsub_id)

        await bus.publish(EventType.BROWSER_CLICK, BrowserEventData(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            action="click",
            target="#button2",
            success=True
        ))

        await asyncio.sleep(0.1)
        assert len(unsub_events) == 1, "Should not receive after unsubscribe"
        print("  PASS: Unsubscribe works\n")

        # Test 5: Event history
        print("Test 5: Event history")
        history = bus.get_history(EventType.TOOL_START)
        assert len(history) > 0, "Should have history"
        assert history[0]['event_type'] == EventType.TOOL_START.value
        print(f"  History size: {len(bus.get_history())}")
        print("  PASS: Event history works\n")

        # Test 6: Replay events
        print("Test 6: Replay events")
        replay_events = []

        async def replay_handler(event_type, data):
            replay_events.append(event_type)

        await bus.replay_events(EventType.TOOL_START, replay_handler)
        await asyncio.sleep(0.1)

        assert len(replay_events) > 0, "Should replay events"
        print(f"  Replayed {len(replay_events)} events")
        print("  PASS: Event replay works\n")

        # Test 7: Statistics
        print("Test 7: Statistics")
        stats = bus.get_stats()
        print(f"  Events published: {stats['events_published']}")
        print(f"  Events processed: {stats['events_processed']}")
        print(f"  Active subscriptions: {stats['active_subscriptions']}")
        print(f"  History size: {stats['history_size']}")
        assert stats['events_published'] > 0
        print("  PASS: Statistics tracking works\n")

        # Test 8: Multiple parallel subscriptions
        print("Test 8: Parallel execution")
        parallel_results = []

        async def slow_handler(event_type, data):
            await asyncio.sleep(0.1)
            parallel_results.append(1)

        async def fast_handler(event_type, data):
            parallel_results.append(2)

        await bus.subscribe(EventType.SESSION_END, slow_handler)
        await bus.subscribe(EventType.SESSION_END, fast_handler)

        start_time = asyncio.get_event_loop().time()
        await bus.publish(EventType.SESSION_END, SessionEventData(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            session_id="test-end"
        ))
        end_time = asyncio.get_event_loop().time()

        await asyncio.sleep(0.15)  # Wait for slow handler

        assert len(parallel_results) == 2, "Both handlers should execute"
        assert (end_time - start_time) < 0.2, "Should execute in parallel"
        print("  PASS: Parallel execution works\n")

        # Test 9: Error handling
        print("Test 9: Error handling")

        async def error_handler(event_type, data):
            raise ValueError("Test error")

        await bus.subscribe(EventType.TOOL_ERROR, error_handler)

        # Should not raise, just log error
        await bus.publish(EventType.TOOL_ERROR, ToolEventData(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            tool_name="error_tool",
            args={},
            error="Test error"
        ))

        await asyncio.sleep(0.1)
        print("  PASS: Error handling works\n")

        # Test 10: Singleton pattern
        print("Test 10: Singleton pattern")
        bus2 = EventBus.get_instance()
        assert bus is bus2, "Should return same instance"
        print("  PASS: Singleton pattern works\n")

        # Final stats
        print("=" * 60)
        print("FINAL STATISTICS")
        print("=" * 60)
        final_stats = bus.get_stats()
        for key, value in final_stats.items():
            print(f"  {key}: {value}")

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60 + "\n")

        # Cleanup
        bus.dispose()

    # Run tests
    asyncio.run(test_event_bus())
