#!/usr/bin/env python3
"""
Multi-Agent Coordination System for Eversale

Implements advanced multi-agent orchestration based on AgentOrchestra, Devin, and
distributed systems research. Enables multiple agents to work together on complex
tasks with coordination, resource sharing, and fault tolerance.

Architecture:
- AgentOrchestrator: Central coordinator managing agent swarm
- AgentWorker: Specialized worker agents with domain expertise
- MessageBroker: Async communication between agents
- SharedMemory: Coordinated state management
- TaskDistributor: Load balancing and task assignment
- LeaderElection: Distributed leader selection
- ResourceManager: Shared resource allocation
- HealthMonitor: Agent health and failure detection

Key Features:
1. Agent Swarm - Multiple specialized agents working in parallel
2. Task Distribution - Smart load balancing across agents
3. Message Passing - Async inter-agent communication
4. Shared State - Coordinated memory across agents
5. Leader Election - Automatic leader selection
6. Failure Isolation - One agent failure doesn't cascade
7. Resource Pooling - Shared browser sessions, APIs, etc.
8. Auto-Scaling - Dynamic agent spawning based on load
9. Cost Optimization - Route tasks to most efficient agent
10. Performance Monitoring - Track agent performance metrics

Integration:
- Works with planning_agent.py for hierarchical planning
- Uses parallel.py for parallel execution
- Integrates multi_tab.py for browser coordination
- Extends agent_network.py with advanced coordination
- Uses multi_instance.py for distributed deployment
"""

import asyncio
import hashlib
import json
import time
import os
import socket
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple, Callable, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict, deque
from loguru import logger
import threading
from queue import Queue, Empty
from abc import ABC, abstractmethod

# Import circuit breaker
from .circuit_breaker import CircuitBreaker, CircuitState

# Storage directories
COORDINATION_DIR = Path("memory/multi_agent")
COORDINATION_DIR.mkdir(parents=True, exist_ok=True)

AGENTS_DIR = COORDINATION_DIR / "agents"
AGENTS_DIR.mkdir(parents=True, exist_ok=True)

MESSAGES_DIR = COORDINATION_DIR / "messages"
MESSAGES_DIR.mkdir(parents=True, exist_ok=True)

SHARED_STATE_DIR = COORDINATION_DIR / "shared_state"
SHARED_STATE_DIR.mkdir(parents=True, exist_ok=True)

METRICS_FILE = COORDINATION_DIR / "metrics.json"


class AgentRole(Enum):
    """Agent specialization roles"""
    ORCHESTRATOR = "orchestrator"  # Coordinates other agents
    PLANNER = "planner"  # Creates plans and strategies
    RESEARCHER = "researcher"  # Web research and data gathering
    EXTRACTOR = "extractor"  # Data extraction specialist
    VALIDATOR = "validator"  # Data validation and verification
    WRITER = "writer"  # Content generation and formatting
    ANALYST = "analyst"  # Data analysis and insights
    EXECUTOR = "executor"  # Generic task execution
    MONITOR = "monitor"  # System monitoring and health checks
    RECOVERY = "recovery"  # Error recovery and fallbacks


class AgentStatus(Enum):
    """Agent lifecycle status"""
    INITIALIZING = "initializing"
    IDLE = "idle"
    BUSY = "busy"
    WAITING = "waiting"
    ERROR = "error"
    STOPPING = "stopping"
    STOPPED = "stopped"


class MessageType(Enum):
    """Types of inter-agent messages"""
    TASK_ASSIGNMENT = "task_assignment"
    TASK_RESULT = "task_result"
    TASK_PROGRESS = "task_progress"
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    SHUTDOWN = "shutdown"


class TaskPriority(Enum):
    """Task priority levels"""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass
class Message:
    """Inter-agent message"""
    message_id: str
    message_type: MessageType
    from_agent: str
    to_agent: Optional[str] = None  # None = broadcast
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    priority: TaskPriority = TaskPriority.NORMAL
    requires_response: bool = False
    in_response_to: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        data["message_type"] = self.message_type.value
        data["priority"] = self.priority.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Create from dictionary"""
        data = data.copy()
        data["message_type"] = MessageType(data["message_type"])
        data["priority"] = TaskPriority(data["priority"])
        return cls(**data)


@dataclass
class AcknowledgedMessage:
    """Message with acknowledgment tracking"""
    message: Message
    timeout: float = 30.0
    max_retries: int = 3
    acked: bool = False
    retry_count: int = 0
    sent_at: float = field(default_factory=time.time)
    ack_received_at: Optional[float] = None


@dataclass
class AgentTask:
    """Task assigned to an agent"""
    task_id: str
    description: str
    assigned_to: str
    priority: TaskPriority = TaskPriority.NORMAL
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Any = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    timeout: float = 300.0  # 5 minutes
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentMetrics:
    """Performance metrics for an agent"""
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_execution_time: float = 0.0
    avg_execution_time: float = 0.0
    messages_sent: int = 0
    messages_received: int = 0
    errors_encountered: int = 0
    last_active: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        total = self.tasks_completed + self.tasks_failed
        if total == 0:
            return 1.0
        return self.tasks_completed / total

    def record_task(self, success: bool, duration: float):
        """Record task completion"""
        if success:
            self.tasks_completed += 1
        else:
            self.tasks_failed += 1

        self.total_execution_time += duration

        # Update moving average
        total_tasks = self.tasks_completed + self.tasks_failed
        self.avg_execution_time = self.total_execution_time / total_tasks if total_tasks > 0 else 0

        self.last_active = datetime.now().isoformat()


class MessageBroker:
    """
    Async message broker for inter-agent communication
    Supports direct messaging, broadcasting, pub-sub patterns, and message acknowledgment
    """

    def __init__(self):
        self.messages: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))  # Per-agent message queues
        self.broadcast_queue: deque = deque(maxlen=1000)
        self.topics: Dict[str, Set[str]] = defaultdict(set)  # Topic -> subscribers
        self._lock = asyncio.Lock()
        self.message_history: deque = deque(maxlen=10000)

        # Message acknowledgment support
        self._pending_acks: Dict[str, AcknowledgedMessage] = {}
        self._ack_lock = asyncio.Lock()

    async def send(self, message: Message):
        """Send a message to an agent or broadcast"""
        async with self._lock:
            # Store in history
            self.message_history.append(message)

            # Save to disk for persistence
            self._persist_message(message)

            if message.to_agent:
                # Direct message
                self.messages[message.to_agent].append(message)
                logger.debug(f"Message {message.message_id} sent to {message.to_agent}")
            else:
                # Broadcast
                self.broadcast_queue.append(message)
                logger.debug(f"Message {message.message_id} broadcast to all agents")

    async def receive(self, agent_id: str, timeout: float = 0.1) -> Optional[Message]:
        """Receive a message for an agent"""
        start_time = time.time()

        while True:
            async with self._lock:
                # Check direct messages first
                if self.messages[agent_id]:
                    return self.messages[agent_id].popleft()

                # Check broadcast messages
                if self.broadcast_queue:
                    msg = self.broadcast_queue[0]
                    if msg.from_agent != agent_id:  # Don't receive own broadcasts
                        self.broadcast_queue.popleft()
                        return msg

            # Check timeout
            if timeout > 0 and (time.time() - start_time) >= timeout:
                return None

            await asyncio.sleep(0.01)

    async def subscribe(self, agent_id: str, topic: str):
        """Subscribe agent to a topic"""
        async with self._lock:
            self.topics[topic].add(agent_id)
            logger.debug(f"Agent {agent_id} subscribed to topic {topic}")

    async def publish(self, topic: str, message: Message):
        """Publish message to topic subscribers"""
        async with self._lock:
            subscribers = self.topics.get(topic, set())
            for agent_id in subscribers:
                self.messages[agent_id].append(message)
            logger.debug(f"Message published to topic {topic} ({len(subscribers)} subscribers)")

    def _persist_message(self, message: Message):
        """Persist message to disk"""
        try:
            msg_file = MESSAGES_DIR / f"{message.message_id}.json"
            msg_file.write_text(json.dumps(message.to_dict(), indent=2))
        except Exception as e:
            logger.warning(f"Failed to persist message: {e}")

    def get_queue_size(self, agent_id: str) -> int:
        """Get size of agent's message queue"""
        return len(self.messages[agent_id])

    async def send_with_ack(self, message: Message, timeout: float = 30.0) -> bool:
        """Send message and wait for acknowledgment with retries."""
        ack_msg = AcknowledgedMessage(message=message, timeout=timeout)

        async with self._ack_lock:
            self._pending_acks[message.message_id] = ack_msg

        # Send message
        await self.send(message)

        # Wait for ack with retries
        for attempt in range(ack_msg.max_retries):
            try:
                await asyncio.wait_for(
                    self._wait_for_ack(message.message_id),
                    timeout=timeout
                )
                return True
            except asyncio.TimeoutError:
                ack_msg.retry_count += 1
                logger.warning(f"Message {message.message_id} ack timeout (attempt {attempt + 1}/{ack_msg.max_retries})")
                if attempt < ack_msg.max_retries - 1:
                    # Exponential backoff
                    backoff = (2 ** attempt) + random.uniform(0, 1)
                    await asyncio.sleep(backoff)
                    await self.send(message)  # Retry

        # Failed after all retries
        async with self._ack_lock:
            self._pending_acks.pop(message.message_id, None)
        logger.error(f"Message {message.message_id} failed after {ack_msg.max_retries} retries")
        return False

    async def _wait_for_ack(self, message_id: str):
        """Wait for acknowledgment of a message."""
        while True:
            async with self._ack_lock:
                ack_msg = self._pending_acks.get(message_id)
                if ack_msg and ack_msg.acked:
                    self._pending_acks.pop(message_id, None)
                    return
            await asyncio.sleep(0.1)

    async def acknowledge(self, message_id: str):
        """Acknowledge receipt of a message."""
        async with self._ack_lock:
            if message_id in self._pending_acks:
                self._pending_acks[message_id].acked = True
                self._pending_acks[message_id].ack_received_at = time.time()
                logger.debug(f"Message {message_id} acknowledged")


class SharedMemory:
    """
    Shared memory for coordinated state across agents
    Thread-safe with atomic operations and versioning
    """

    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.versions: Dict[str, int] = {}  # Track versions for optimistic locking
        self._lock = asyncio.Lock()
        self.state_file = SHARED_STATE_DIR / "shared_memory.json"
        self._load()

    async def set(self, key: str, value: Any, expected_version: Optional[int] = None) -> bool:
        """
        Set a value with optional optimistic locking

        Args:
            key: Key to set
            value: Value to store
            expected_version: If provided, only set if current version matches

        Returns:
            True if set succeeded, False if version conflict
        """
        async with self._lock:
            # Check version if provided
            if expected_version is not None:
                current_version = self.versions.get(key, 0)
                if current_version != expected_version:
                    logger.warning(f"Version conflict for key {key}: expected {expected_version}, got {current_version}")
                    return False

            # Set value and increment version
            self.data[key] = value
            self.versions[key] = self.versions.get(key, 0) + 1

            # Persist
            self._save()

            return True

    async def get(self, key: str, default: Any = None) -> Tuple[Any, int]:
        """
        Get a value and its version

        Returns:
            (value, version) tuple
        """
        async with self._lock:
            value = self.data.get(key, default)
            version = self.versions.get(key, 0)
            return value, version

    async def delete(self, key: str):
        """Delete a key"""
        async with self._lock:
            if key in self.data:
                del self.data[key]
            if key in self.versions:
                del self.versions[key]
            self._save()

    async def keys(self) -> List[str]:
        """Get all keys"""
        async with self._lock:
            return list(self.data.keys())

    async def clear(self):
        """Clear all data"""
        async with self._lock:
            self.data.clear()
            self.versions.clear()
            self._save()

    def _save(self):
        """Persist to disk"""
        try:
            state = {
                "data": self.data,
                "versions": self.versions,
                "updated_at": datetime.now().isoformat()
            }
            self.state_file.write_text(json.dumps(state, indent=2, default=str))
        except Exception as e:
            logger.warning(f"Failed to save shared memory: {e}")

    def _load(self):
        """Load from disk"""
        try:
            if self.state_file.exists():
                state = json.loads(self.state_file.read_text())
                self.data = state.get("data", {})
                self.versions = state.get("versions", {})
        except Exception as e:
            logger.warning(f"Failed to load shared memory: {e}")


class LeaderElection:
    """
    Distributed leader election using file-based locks.
    Implements a simple leader election protocol:
    1. All candidates try to acquire lock
    2. First to acquire becomes leader
    3. Leader maintains heartbeat
    4. If heartbeat stale, new election triggered
    """

    LEADER_FILE = Path.home() / ".eversale" / "leader.lock"
    HEARTBEAT_INTERVAL = 5  # seconds
    STALE_THRESHOLD = 15  # seconds - leader considered dead if no heartbeat

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.is_leader = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._lock_fd: Optional[int] = None
        self._running = False
        self.leader_id: Optional[str] = None

        # Ensure leader file directory exists
        self.LEADER_FILE.parent.mkdir(parents=True, exist_ok=True)

    async def run_election(self) -> bool:
        """Attempt to become leader. Returns True if elected."""
        try:
            # Try to acquire exclusive lock
            if await self._acquire_lock():
                self.is_leader = True
                self.leader_id = self.agent_id
                self._write_heartbeat()

                # Start async heartbeat loop
                self._running = True
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                logger.info(f"Agent {self.agent_id} elected as leader")
                return True
            else:
                # Check if current leader is stale
                return await self._check_stale_leader()

        except Exception as e:
            logger.error(f"Leader election failed: {e}")
            return False

    async def _acquire_lock(self) -> bool:
        """Try to acquire exclusive lock non-blocking."""
        import fcntl

        try:
            # Try to create lock file exclusively
            try:
                fd = os.open(str(self.LEADER_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                # File exists, check if we can steal stale lock
                return False

            try:
                # Apply OS-level exclusive lock (non-blocking)
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._lock_fd = fd
                return True
            except (BlockingIOError, OSError):
                # Failed to acquire lock
                os.close(fd)
                try:
                    self.LEADER_FILE.unlink()
                except Exception:
                    pass
                return False

        except Exception as e:
            logger.debug(f"Failed to acquire lock: {e}")
            return False

    async def _check_stale_leader(self) -> bool:
        """Check if current leader is stale and take over if so."""
        import fcntl

        try:
            if not self.LEADER_FILE.exists():
                return False

            # Try to read lock data
            try:
                with open(self.LEADER_FILE, 'r') as f:
                    # Try to get shared lock to read
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                        data = json.loads(f.read())
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    except BlockingIOError:
                        # Lock is held, leader is active
                        self.leader_id = None
                        return False

                # Check heartbeat age
                last_heartbeat = datetime.fromisoformat(data['heartbeat'])
                age = (datetime.now() - last_heartbeat).total_seconds()

                if age > self.STALE_THRESHOLD:
                    logger.warning(f"Leader {data['agent_id']} is stale ({age}s), taking over")

                    # Remove stale lock file
                    try:
                        self.LEADER_FILE.unlink()
                    except Exception as e:
                        logger.debug(f"Failed to remove stale lock: {e}")
                        return False

                    # Retry lock acquisition
                    if await self._acquire_lock():
                        self.is_leader = True
                        self.leader_id = self.agent_id
                        self._write_heartbeat()

                        # Start heartbeat loop
                        self._running = True
                        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                        logger.info(f"Agent {self.agent_id} took over leadership from stale leader")
                        return True
                else:
                    # Leader is active, store their ID
                    self.leader_id = data.get('agent_id')
                    logger.info(f"Agent {self.agent_id} is follower, leader is {self.leader_id}")

            except Exception as e:
                logger.debug(f"Error reading leader file: {e}")
                return False

        except Exception as e:
            logger.debug(f"Could not check leader status: {e}")

        return False

    def _write_heartbeat(self):
        """Write heartbeat to leader file."""
        try:
            if self._lock_fd is None:
                return

            data = {
                'agent_id': self.agent_id,
                'heartbeat': datetime.now().isoformat(),
                'pid': os.getpid(),
                'hostname': socket.gethostname(),
                'elected_at': datetime.now().isoformat()
            }

            # Write to file descriptor
            os.ftruncate(self._lock_fd, 0)
            os.lseek(self._lock_fd, 0, os.SEEK_SET)
            os.write(self._lock_fd, json.dumps(data, indent=2).encode())

        except Exception as e:
            logger.error(f"Failed to write heartbeat: {e}")

    async def _heartbeat_loop(self):
        """Maintain heartbeat while leader."""
        while self._running and self.is_leader:
            try:
                self._write_heartbeat()
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)

    def resign(self):
        """Give up leadership."""
        import fcntl

        self._running = False

        # Cancel heartbeat task
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        # Release lock file descriptor
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
            except Exception as e:
                logger.debug(f"Error releasing leader lock: {e}")
            finally:
                self._lock_fd = None

        # Remove leader lock file
        if self.is_leader:
            try:
                self.LEADER_FILE.unlink()
            except Exception as e:
                logger.debug(f"Error removing leader file: {e}")

        self.is_leader = False
        logger.info(f"Agent {self.agent_id} resigned leadership")

    def get_leader(self) -> Optional[str]:
        """Get current leader ID."""
        if self.is_leader:
            return self.agent_id

        try:
            if self.LEADER_FILE.exists():
                data = json.loads(self.LEADER_FILE.read_text())
                return data.get("agent_id")
        except Exception:
            pass

        return self.leader_id

    # Legacy sync method for backward compatibility
    def start_election(self) -> bool:
        """Synchronous election wrapper (deprecated, use run_election)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is already running, create task but don't wait
                asyncio.create_task(self.run_election())
                return self.is_leader
            else:
                # Run election synchronously
                return loop.run_until_complete(self.run_election())
        except Exception as e:
            logger.error(f"Sync election failed: {e}")
            return False

    # Legacy method for backward compatibility
    def step_down(self):
        """Step down as leader (legacy sync wrapper)."""
        self.resign()
class TaskDistributor:
    """
    Intelligent task distribution across agents
    Load balancing, capability-based routing, priority handling, exponential backoff
    """

    def __init__(self, shared_memory: SharedMemory):
        self.shared_memory = shared_memory
        self.task_queue: Dict[TaskPriority, deque] = {
            priority: deque() for priority in TaskPriority
        }
        self.assigned_tasks: Dict[str, AgentTask] = {}  # task_id -> task
        self.agent_workload: Dict[str, int] = defaultdict(int)  # agent_id -> active tasks
        self._lock = asyncio.Lock()

        # Exponential backoff for retries
        self._retry_delays: Dict[str, float] = {}  # task_id -> next retry delay
        self._max_delay = 60.0
        self._base_delay = 1.0

    async def submit_task(
        self,
        task_id: str,
        description: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        required_role: Optional[AgentRole] = None,
        metadata: Dict[str, Any] = None
    ) -> AgentTask:
        """Submit a task for distribution"""
        task = AgentTask(
            task_id=task_id,
            description=description,
            priority=priority,
            assigned_to="",  # Will be assigned later
            metadata=metadata or {}
        )

        if required_role:
            task.metadata["required_role"] = required_role.value

        async with self._lock:
            self.task_queue[priority].append(task)
            logger.debug(f"Task {task_id} submitted with priority {priority.name}")

        return task

    async def assign_tasks(self, available_agents: List["AgentWorker"]) -> List[Tuple[str, AgentTask]]:
        """
        Assign tasks to available agents

        Returns:
            List of (agent_id, task) assignments
        """
        assignments = []

        async with self._lock:
            # Process by priority
            for priority in sorted(TaskPriority, key=lambda p: p.value):
                queue = self.task_queue[priority]

                while queue and available_agents:
                    task = queue.popleft()

                    # Find best agent for this task
                    agent = self._select_agent(task, available_agents)
                    if not agent:
                        # No suitable agent, put back in queue
                        queue.appendleft(task)
                        break

                    # Assign task
                    task.assigned_to = agent.agent_id
                    task.status = "assigned"
                    self.assigned_tasks[task.task_id] = task
                    self.agent_workload[agent.agent_id] += 1

                    assignments.append((agent.agent_id, task))
                    available_agents.remove(agent)

                    logger.info(f"Task {task.task_id} assigned to agent {agent.agent_id}")

        return assignments

    def _select_agent(self, task: AgentTask, available_agents: List["AgentWorker"]) -> Optional["AgentWorker"]:
        """Select best agent for a task"""
        # Filter by required role
        required_role = task.metadata.get("required_role")
        if required_role:
            candidates = [a for a in available_agents if a.role.value == required_role]
        else:
            candidates = available_agents

        if not candidates:
            return None

        # Select agent with lowest workload
        best_agent = min(candidates, key=lambda a: self.agent_workload.get(a.agent_id, 0))
        return best_agent

    async def complete_task(self, task_id: str, result: Any = None, error: Optional[str] = None):
        """Mark task as completed"""
        async with self._lock:
            if task_id in self.assigned_tasks:
                task = self.assigned_tasks[task_id]
                task.status = "completed" if not error else "failed"
                task.completed_at = datetime.now().isoformat()
                task.result = result
                task.error = error

                # Update workload
                if task.assigned_to:
                    self.agent_workload[task.assigned_to] = max(0, self.agent_workload[task.assigned_to] - 1)

    async def get_task_status(self, task_id: str) -> Optional[AgentTask]:
        """Get status of a task"""
        async with self._lock:
            return self.assigned_tasks.get(task_id)

    def get_queue_sizes(self) -> Dict[str, int]:
        """Get queue sizes by priority"""
        return {priority.name: len(queue) for priority, queue in self.task_queue.items()}

    async def retry_task(self, task: AgentTask):
        """Retry a failed task with exponential backoff."""
        task_id = task.task_id

        # Calculate backoff delay
        current_delay = self._retry_delays.get(task_id, self._base_delay)

        # Wait with backoff (add jitter)
        jitter = random.uniform(0, current_delay * 0.1)
        await asyncio.sleep(current_delay + jitter)

        # Increase delay for next retry (exponential)
        next_delay = min(current_delay * 2, self._max_delay)
        self._retry_delays[task_id] = next_delay

        # Re-queue task
        task.retry_count += 1
        task.status = "pending"
        task.assigned_to = ""  # Will be reassigned

        async with self._lock:
            self.task_queue[task.priority].append(task)

        logger.info(f"Task {task_id} retrying (attempt {task.retry_count}/{task.max_retries}) with {current_delay:.1f}s delay")

    def reset_retry_delay(self, task_id: str):
        """Reset retry delay on success."""
        self._retry_delays.pop(task_id, None)


class AgentWorker(ABC):
    """
    Base class for specialized worker agents
    Each worker has a specific role and capabilities
    """

    def __init__(
        self,
        agent_id: str,
        role: AgentRole,
        broker: MessageBroker,
        shared_memory: SharedMemory
    ):
        self.agent_id = agent_id
        self.role = role
        self.status = AgentStatus.INITIALIZING
        self.broker = broker
        self.shared_memory = shared_memory
        self.metrics = AgentMetrics()

        # Current task
        self.current_task: Optional[AgentTask] = None
        self._running = False
        self._task_loop: Optional[asyncio.Task] = None

        # Capabilities
        self.capabilities: Set[str] = set()

    async def start(self):
        """Start the agent"""
        self._running = True
        self.status = AgentStatus.IDLE
        self._task_loop = asyncio.create_task(self._message_loop())
        logger.info(f"Agent {self.agent_id} ({self.role.name}) started")

    async def stop(self):
        """Stop the agent"""
        self._running = False
        self.status = AgentStatus.STOPPING

        if self._task_loop:
            self._task_loop.cancel()
            try:
                await self._task_loop
            except asyncio.CancelledError:
                pass

        self.status = AgentStatus.STOPPED
        logger.info(f"Agent {self.agent_id} stopped")

    async def _message_loop(self):
        """Process incoming messages"""
        while self._running:
            try:
                # Check for messages
                message = await self.broker.receive(self.agent_id, timeout=0.5)

                if message:
                    self.metrics.messages_received += 1
                    await self._handle_message(message)

                # Send heartbeat periodically
                if int(time.time()) % 30 == 0:
                    await self._send_heartbeat()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Agent {self.agent_id} message loop error: {e}")
                self.metrics.errors_encountered += 1

    async def _handle_message(self, message: Message):
        """Handle incoming message with acknowledgment"""
        try:
            # Acknowledge message receipt
            await self.broker.acknowledge(message.message_id)

            if message.message_type == MessageType.TASK_ASSIGNMENT:
                await self._handle_task_assignment(message)
            elif message.message_type == MessageType.REQUEST:
                await self._handle_request(message)
            elif message.message_type == MessageType.SHUTDOWN:
                await self.stop()
            else:
                # Subclass can handle other message types
                await self.handle_custom_message(message)

        except Exception as e:
            logger.error(f"Agent {self.agent_id} failed to handle message: {e}")

    async def _handle_task_assignment(self, message: Message):
        """Handle task assignment"""
        task_data = message.payload.get("task")
        if not task_data:
            return

        # Create task object
        task = AgentTask(**task_data)
        self.current_task = task

        # Execute task
        start_time = time.time()
        self.status = AgentStatus.BUSY
        task.started_at = datetime.now().isoformat()

        try:
            result = await self.execute_task(task)

            # Task succeeded
            duration = time.time() - start_time
            self.metrics.record_task(success=True, duration=duration)
            task.status = "completed"
            task.completed_at = datetime.now().isoformat()
            task.result = result

            # Send result back
            await self._send_task_result(task, success=True)

        except Exception as e:
            # Task failed
            duration = time.time() - start_time
            self.metrics.record_task(success=False, duration=duration)
            task.status = "failed"
            task.error = str(e)
            logger.error(f"Agent {self.agent_id} task failed: {e}")

            # Send error back
            await self._send_task_result(task, success=False, error=str(e))

        finally:
            self.current_task = None
            self.status = AgentStatus.IDLE

    @abstractmethod
    async def execute_task(self, task: AgentTask) -> Any:
        """
        Execute a task (must be implemented by subclasses)

        Returns:
            Task result
        """
        pass

    async def handle_custom_message(self, message: Message):
        """Handle custom message types (can be overridden)"""
        pass

    async def _handle_request(self, message: Message):
        """Handle request from another agent"""
        pass

    async def _send_task_result(self, task: AgentTask, success: bool, error: str = ""):
        """Send task result back to orchestrator"""
        result_msg = Message(
            message_id=f"result_{task.task_id}_{time.time()}",
            message_type=MessageType.TASK_RESULT,
            from_agent=self.agent_id,
            to_agent="orchestrator",
            payload={
                "task_id": task.task_id,
                "success": success,
                "result": task.result,
                "error": error,
                "metrics": {
                    "execution_time": task.metadata.get("execution_time", 0),
                    "started_at": task.started_at,
                    "completed_at": task.completed_at
                }
            }
        )

        await self.broker.send(result_msg)
        self.metrics.messages_sent += 1

    async def _send_heartbeat(self):
        """Send heartbeat message"""
        heartbeat = Message(
            message_id=f"heartbeat_{self.agent_id}_{time.time()}",
            message_type=MessageType.HEARTBEAT,
            from_agent=self.agent_id,
            payload={
                "status": self.status.value,
                "current_task": self.current_task.task_id if self.current_task else None,
                "metrics": asdict(self.metrics)
            }
        )

        await self.broker.send(heartbeat)

    async def send_message(self, to_agent: str, message_type: MessageType, payload: Dict[str, Any]):
        """Send a message to another agent"""
        message = Message(
            message_id=f"{self.agent_id}_{to_agent}_{time.time()}",
            message_type=message_type,
            from_agent=self.agent_id,
            to_agent=to_agent,
            payload=payload
        )

        await self.broker.send(message)
        self.metrics.messages_sent += 1

    def get_status(self) -> Dict[str, Any]:
        """Get agent status"""
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "status": self.status.value,
            "current_task": self.current_task.task_id if self.current_task else None,
            "metrics": asdict(self.metrics),
            "capabilities": list(self.capabilities)
        }


class ResearcherAgent(AgentWorker):
    """Agent specialized in web research and data gathering."""

    def __init__(self, agent_id: str, broker: MessageBroker, shared_memory: SharedMemory):
        super().__init__(agent_id, AgentRole.RESEARCHER, broker, shared_memory)
        self.capabilities = {"web_search", "data_gathering", "page_analysis"}
        self.browser = None
        self.llm_client = None

    async def execute_task(self, task: AgentTask) -> Any:
        """
        Execute research task - actually browse web and gather information.

        Task metadata can include:
        - query: Search query or research topic
        - urls: Specific URLs to research
        - depth: Research depth (1-3, default 2)
        - max_results: Maximum results to gather
        """
        logger.info(f"ResearcherAgent {self.agent_id} executing: {task.description}")

        try:
            # Import required modules
            from .playwright_direct import PlaywrightClient
            from .llm_client import get_llm_client
            from .config_loader import load_config

            # Initialize browser if needed
            if not self.browser:
                config = load_config()
                self.browser = PlaywrightClient(
                    headless=config.get('browser', {}).get('headless', True)
                )
                await self.browser.connect()

            # Initialize LLM client if needed
            if not self.llm_client:
                self.llm_client = get_llm_client()

            # Parse task parameters
            query = task.metadata.get('query', task.description)
            urls = task.metadata.get('urls', [])
            depth = task.metadata.get('depth', 2)
            max_results = task.metadata.get('max_results', 5)

            findings = []
            sources = []

            # If specific URLs provided, research those
            if urls:
                for url in urls[:max_results]:
                    try:
                        logger.info(f"Researching URL: {url}")
                        result = await self.browser.navigate(url)

                        if result.get('status') == 'success':
                            # Extract page content
                            content = result.get('markdown', '')
                            title = result.get('title', url)

                            # Use LLM to summarize findings
                            summary_prompt = f"""Analyze this webpage and extract key information relevant to: {query}

Page Title: {title}
Content (first 2000 chars):
{content[:2000]}

Provide a concise summary of the most relevant information found."""

                            summary_result = await self.llm_client.generate(
                                prompt=summary_prompt,
                                temperature=0.3,
                                max_tokens=500
                            )

                            findings.append({
                                'url': url,
                                'title': title,
                                'summary': summary_result.content
                            })
                            sources.append(url)

                    except Exception as e:
                        logger.warning(f"Error researching {url}: {e}")

            else:
                # No specific URLs - perform web search
                logger.info(f"Performing web search for: {query}")

                # Use browser to search (e.g., via Google)
                search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"

                try:
                    result = await self.browser.navigate(search_url)

                    if result.get('status') == 'success':
                        # Extract search results (simplified - real implementation would parse search results)
                        content = result.get('markdown', '')

                        # Use LLM to extract insights from search results
                        analysis_prompt = f"""Analyze these search results for: {query}

Search Results:
{content[:3000]}

Extract the key findings and provide a structured summary of what was learned."""

                        analysis_result = await self.llm_client.generate(
                            prompt=analysis_prompt,
                            temperature=0.3,
                            max_tokens=800
                        )

                        findings.append({
                            'query': query,
                            'source': 'web_search',
                            'summary': analysis_result.content
                        })
                        sources.append(search_url)

                except Exception as e:
                    logger.warning(f"Web search error: {e}")

            # Store findings in shared memory for other agents
            await self.shared_memory.set(
                f"research_{task.task_id}",
                {
                    'findings': findings,
                    'sources': sources,
                    'query': query,
                    'timestamp': datetime.now().isoformat()
                }
            )

            return {
                "status": "completed",
                "findings": findings,
                "sources": sources,
                "summary": f"Researched {len(findings)} sources for: {query}"
            }

        except Exception as e:
            logger.error(f"ResearcherAgent error: {e}")
            raise


class ExtractorAgent(AgentWorker):
    """Agent specialized in data extraction from web pages."""

    def __init__(self, agent_id: str, broker: MessageBroker, shared_memory: SharedMemory):
        super().__init__(agent_id, AgentRole.EXTRACTOR, broker, shared_memory)
        self.capabilities = {"html_extraction", "contact_extraction", "table_parsing"}
        self.browser = None

    async def execute_task(self, task: AgentTask) -> Any:
        """
        Execute extraction task - navigate to URLs and extract structured data.

        Task metadata can include:
        - urls: List of URLs to extract from (required)
        - extract_type: Type of extraction (contacts, table, all)
        - selectors: Custom CSS selectors to extract
        - batch: Whether to use batch extraction
        """
        logger.info(f"ExtractorAgent {self.agent_id} executing: {task.description}")

        try:
            # Import required modules
            from .playwright_direct import PlaywrightClient
            from .config_loader import load_config

            # Initialize browser if needed
            if not self.browser:
                config = load_config()
                self.browser = PlaywrightClient(
                    headless=config.get('browser', {}).get('headless', True)
                )
                await self.browser.connect()

            # Parse task parameters
            urls = task.metadata.get('urls', [])
            extract_type = task.metadata.get('extract_type', 'contacts')
            selectors = task.metadata.get('selectors', {})
            use_batch = task.metadata.get('batch', False)

            if not urls:
                raise ValueError("ExtractorAgent requires 'urls' in task metadata")

            extracted_data = []
            total_contacts = 0

            # Batch extraction mode
            if use_batch and len(urls) > 1:
                logger.info(f"Using batch extraction for {len(urls)} URLs")

                try:
                    # Call batch extract tool
                    batch_result = await self.browser.call_tool(
                        'playwright_batch_extract',
                        {'urls': urls}
                    )

                    if batch_result.get('status') == 'success':
                        results = batch_result.get('results', [])

                        for result in results:
                            url_data = {
                                'url': result.get('url'),
                                'title': result.get('title', ''),
                                'emails': result.get('emails', []),
                                'phones': result.get('phones', []),
                                'status': result.get('status')
                            }
                            extracted_data.append(url_data)
                            total_contacts += len(result.get('emails', [])) + len(result.get('phones', []))

                except Exception as e:
                    logger.warning(f"Batch extraction failed: {e}, falling back to sequential")
                    use_batch = False

            # Sequential extraction mode
            if not use_batch:
                for url in urls:
                    try:
                        logger.info(f"Extracting from: {url}")

                        # Navigate to URL
                        nav_result = await self.browser.navigate(url)

                        if nav_result.get('status') != 'success':
                            extracted_data.append({
                                'url': url,
                                'status': 'navigation_failed',
                                'error': nav_result.get('error')
                            })
                            continue

                        # Perform extraction based on type
                        if extract_type == 'contacts':
                            # Extract contacts
                            extract_result = await self.browser.call_tool(
                                'playwright_extract_page_fast',
                                {}
                            )

                            if extract_result.get('status') == 'success':
                                emails = extract_result.get('emails', [])
                                phones = extract_result.get('phones', [])

                                url_data = {
                                    'url': url,
                                    'title': nav_result.get('title', ''),
                                    'emails': emails,
                                    'phones': phones,
                                    'status': 'success'
                                }
                                extracted_data.append(url_data)
                                total_contacts += len(emails) + len(phones)

                        elif extract_type == 'table':
                            # Extract tables from page
                            content_result = await self.browser.get_content()
                            markdown = content_result.get('markdown', '')

                            # Simple table extraction from markdown
                            tables = []
                            lines = markdown.split('\n')
                            current_table = []

                            for line in lines:
                                if '|' in line:
                                    current_table.append(line)
                                elif current_table:
                                    tables.append('\n'.join(current_table))
                                    current_table = []

                            if current_table:
                                tables.append('\n'.join(current_table))

                            url_data = {
                                'url': url,
                                'title': nav_result.get('title', ''),
                                'tables': tables,
                                'table_count': len(tables),
                                'status': 'success'
                            }
                            extracted_data.append(url_data)

                        elif extract_type == 'custom' and selectors:
                            # Extract using custom selectors
                            custom_data = {}

                            for key, selector in selectors.items():
                                try:
                                    text_result = await self.browser.get_text(selector)
                                    custom_data[key] = text_result.get('text', '')
                                except Exception as e:
                                    logger.warning(f"Failed to extract {key}: {e}")
                                    custom_data[key] = None

                            url_data = {
                                'url': url,
                                'title': nav_result.get('title', ''),
                                'custom_data': custom_data,
                                'status': 'success'
                            }
                            extracted_data.append(url_data)

                        else:
                            # Extract all available data
                            extract_result = await self.browser.call_tool(
                                'playwright_extract_page_fast',
                                {}
                            )

                            url_data = {
                                'url': url,
                                'title': nav_result.get('title', ''),
                                'markdown': nav_result.get('markdown', '')[:1000],
                                'emails': extract_result.get('emails', []),
                                'phones': extract_result.get('phones', []),
                                'status': 'success'
                            }
                            extracted_data.append(url_data)
                            total_contacts += len(extract_result.get('emails', [])) + len(extract_result.get('phones', []))

                    except Exception as e:
                        logger.warning(f"Error extracting from {url}: {e}")
                        extracted_data.append({
                            'url': url,
                            'status': 'error',
                            'error': str(e)
                        })

            # Store extracted data in shared memory
            await self.shared_memory.set(
                f"extraction_{task.task_id}",
                {
                    'extracted_data': extracted_data,
                    'total_urls': len(urls),
                    'successful_extractions': len([d for d in extracted_data if d.get('status') == 'success']),
                    'total_contacts': total_contacts,
                    'timestamp': datetime.now().isoformat()
                }
            )

            return {
                "status": "completed",
                "extracted_data": extracted_data,
                "total_urls": len(urls),
                "successful": len([d for d in extracted_data if d.get('status') == 'success']),
                "total_contacts": total_contacts,
                "summary": f"Extracted data from {len(extracted_data)}/{len(urls)} URLs, found {total_contacts} contacts"
            }

        except Exception as e:
            logger.error(f"ExtractorAgent error: {e}")
            raise


class ValidatorAgent(AgentWorker):
    """Agent specialized in data validation and quality checking."""

    def __init__(self, agent_id: str, broker: MessageBroker, shared_memory: SharedMemory):
        super().__init__(agent_id, AgentRole.VALIDATOR, broker, shared_memory)
        self.capabilities = {"data_validation", "quality_check", "deduplication"}

    async def execute_task(self, task: AgentTask) -> Any:
        """
        Execute validation task - validate and clean extracted data.

        Task metadata can include:
        - data: Data to validate (required)
        - validation_type: Type of validation (email, phone, url, company)
        - deduplicate: Whether to remove duplicates
        - verify_online: Whether to verify data online (e.g., check if URLs exist)
        """
        logger.info(f"ValidatorAgent {self.agent_id} executing: {task.description}")

        try:
            import re

            # Parse task parameters
            data = task.metadata.get('data', {})
            validation_type = task.metadata.get('validation_type', 'all')
            deduplicate = task.metadata.get('deduplicate', True)
            verify_online = task.metadata.get('verify_online', False)

            if not data:
                raise ValueError("ValidatorAgent requires 'data' in task metadata")

            errors = []
            warnings = []
            validated_data = {}

            # Email validation
            if 'emails' in data or validation_type == 'email':
                emails = data.get('emails', [])
                valid_emails = []
                invalid_emails = []

                # Email regex pattern
                email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

                for email in emails:
                    if isinstance(email, str):
                        email = email.strip().lower()

                        # Basic format validation
                        if email_pattern.match(email):
                            # Additional checks
                            if email.count('@') == 1:
                                domain = email.split('@')[1]

                                # Check for suspicious domains
                                suspicious_domains = ['example.com', 'test.com', 'localhost']
                                if domain not in suspicious_domains:
                                    valid_emails.append(email)
                                else:
                                    warnings.append(f"Suspicious email domain: {email}")
                                    invalid_emails.append(email)
                            else:
                                invalid_emails.append(email)
                        else:
                            invalid_emails.append(email)

                # Deduplicate
                if deduplicate:
                    original_count = len(valid_emails)
                    valid_emails = list(set(valid_emails))
                    if len(valid_emails) < original_count:
                        warnings.append(f"Removed {original_count - len(valid_emails)} duplicate emails")

                validated_data['emails'] = valid_emails
                validated_data['invalid_emails'] = invalid_emails

                if invalid_emails:
                    errors.append(f"Found {len(invalid_emails)} invalid emails")

            # Phone validation
            if 'phones' in data or validation_type == 'phone':
                phones = data.get('phones', [])
                valid_phones = []
                invalid_phones = []

                # Phone pattern (simplified - matches various formats)
                phone_pattern = re.compile(r'[\d\s\-\(\)\+]{10,}')

                for phone in phones:
                    if isinstance(phone, str):
                        phone = phone.strip()

                        # Extract digits
                        digits = re.sub(r'\D', '', phone)

                        # Valid if 10-15 digits
                        if 10 <= len(digits) <= 15:
                            valid_phones.append(phone)
                        else:
                            invalid_phones.append(phone)

                # Deduplicate
                if deduplicate:
                    original_count = len(valid_phones)
                    valid_phones = list(set(valid_phones))
                    if len(valid_phones) < original_count:
                        warnings.append(f"Removed {original_count - len(valid_phones)} duplicate phones")

                validated_data['phones'] = valid_phones
                validated_data['invalid_phones'] = invalid_phones

                if invalid_phones:
                    errors.append(f"Found {len(invalid_phones)} invalid phone numbers")

            # URL validation
            if 'urls' in data or validation_type == 'url':
                urls = data.get('urls', [])
                valid_urls = []
                invalid_urls = []

                # URL pattern
                url_pattern = re.compile(
                    r'^https?://'  # http:// or https://
                    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
                    r'localhost|'  # localhost...
                    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
                    r'(?::\d+)?'  # optional port
                    r'(?:/?|[/?]\S+)$', re.IGNORECASE)

                for url in urls:
                    if isinstance(url, str):
                        url = url.strip()

                        if url_pattern.match(url):
                            valid_urls.append(url)
                        else:
                            invalid_urls.append(url)

                # Deduplicate
                if deduplicate:
                    original_count = len(valid_urls)
                    valid_urls = list(set(valid_urls))
                    if len(valid_urls) < original_count:
                        warnings.append(f"Removed {original_count - len(valid_urls)} duplicate URLs")

                # Online verification
                if verify_online and valid_urls:
                    from .playwright_direct import PlaywrightClient
                    from .config_loader import load_config

                    browser = PlaywrightClient(
                        headless=load_config().get('browser', {}).get('headless', True)
                    )
                    await browser.connect()

                    verified_urls = []
                    for url in valid_urls[:10]:  # Limit to first 10 for performance
                        try:
                            result = await browser.navigate(url)
                            if result.get('status') == 'success':
                                verified_urls.append(url)
                            else:
                                warnings.append(f"URL failed to load: {url}")
                        except Exception as e:
                            warnings.append(f"Error verifying {url}: {e}")

                    await browser.disconnect()
                    validated_data['verified_urls'] = verified_urls

                validated_data['urls'] = valid_urls
                validated_data['invalid_urls'] = invalid_urls

                if invalid_urls:
                    errors.append(f"Found {len(invalid_urls)} invalid URLs")

            # Company name validation (basic)
            if 'companies' in data or validation_type == 'company':
                companies = data.get('companies', [])
                valid_companies = []

                for company in companies:
                    if isinstance(company, str):
                        company = company.strip()

                        # Basic validation - not empty, reasonable length
                        if len(company) > 1 and len(company) < 200:
                            # Remove common noise words
                            if not company.lower() in ['none', 'n/a', 'unknown', 'null']:
                                valid_companies.append(company)

                # Deduplicate
                if deduplicate:
                    original_count = len(valid_companies)
                    valid_companies = list(set(valid_companies))
                    if len(valid_companies) < original_count:
                        warnings.append(f"Removed {original_count - len(valid_companies)} duplicate companies")

                validated_data['companies'] = valid_companies

            # Generic data validation
            if validation_type == 'all':
                # Validate any lists in the data
                for key, value in data.items():
                    if isinstance(value, list) and key not in ['emails', 'phones', 'urls', 'companies']:
                        if deduplicate:
                            original_count = len(value)
                            value = list(set(value))
                            if len(value) < original_count:
                                warnings.append(f"Removed {original_count - len(value)} duplicates from {key}")
                        validated_data[key] = value

            # Calculate quality score
            total_items = sum(len(v) if isinstance(v, list) else 0 for v in data.values())
            valid_items = sum(len(v) if isinstance(v, list) else 0 for k, v in validated_data.items() if not k.startswith('invalid_'))
            quality_score = (valid_items / total_items * 100) if total_items > 0 else 100

            # Store validated data in shared memory
            await self.shared_memory.set(
                f"validation_{task.task_id}",
                {
                    'validated_data': validated_data,
                    'errors': errors,
                    'warnings': warnings,
                    'quality_score': quality_score,
                    'timestamp': datetime.now().isoformat()
                }
            )

            return {
                "status": "completed",
                "valid": len(errors) == 0,
                "validated_data": validated_data,
                "errors": errors,
                "warnings": warnings,
                "quality_score": quality_score,
                "summary": f"Validated data with {quality_score:.1f}% quality score, {len(errors)} errors, {len(warnings)} warnings"
            }

        except Exception as e:
            logger.error(f"ValidatorAgent error: {e}")
            raise


class AnalystAgent(AgentWorker):
    """Agent specialized in analyzing data and generating insights."""

    def __init__(self, agent_id: str, broker: MessageBroker, shared_memory: SharedMemory):
        super().__init__(agent_id, AgentRole.ANALYST, broker, shared_memory)
        self.capabilities = {"data_analysis", "pattern_recognition", "insight_generation"}
        self.llm_client = None

    async def execute_task(self, task: AgentTask) -> Any:
        """
        Execute analysis task - analyze data and generate insights.

        Task metadata can include:
        - data: Data to analyze (required)
        - analysis_type: Type of analysis (summary, comparison, trends, insights)
        - context: Additional context for analysis
        - output_format: Format for output (text, json, markdown)
        """
        logger.info(f"AnalystAgent {self.agent_id} executing: {task.description}")

        try:
            # Import required modules
            from .llm_client import get_llm_client

            # Initialize LLM client if needed
            if not self.llm_client:
                self.llm_client = get_llm_client()

            # Parse task parameters
            data = task.metadata.get('data', {})
            analysis_type = task.metadata.get('analysis_type', 'insights')
            context = task.metadata.get('context', task.description)
            output_format = task.metadata.get('output_format', 'text')

            if not data:
                raise ValueError("AnalystAgent requires 'data' in task metadata")

            insights = []
            statistics = {}

            # Calculate basic statistics
            if isinstance(data, dict):
                for key, value in data.items():
                    if isinstance(value, list):
                        statistics[key] = {
                            'count': len(value),
                            'unique_count': len(set(value)) if all(isinstance(x, (str, int, float)) for x in value) else len(value)
                        }
                    elif isinstance(value, (int, float)):
                        statistics[key] = {'value': value}

            # Perform analysis based on type
            if analysis_type == 'summary':
                # Generate summary of data
                summary_prompt = f"""Analyze this data and provide a concise summary:

Context: {context}

Data:
{json.dumps(data, indent=2, default=str)[:3000]}

Provide a clear, structured summary of the key points."""

                summary_result = await self.llm_client.generate(
                    prompt=summary_prompt,
                    temperature=0.3,
                    max_tokens=800
                )

                insights.append({
                    'type': 'summary',
                    'content': summary_result.content
                })

            elif analysis_type == 'comparison':
                # Compare different data points
                comparison_prompt = f"""Compare and contrast the data provided:

Context: {context}

Data:
{json.dumps(data, indent=2, default=str)[:3000]}

Statistics:
{json.dumps(statistics, indent=2)}

Identify key differences, similarities, and notable patterns."""

                comparison_result = await self.llm_client.generate(
                    prompt=comparison_prompt,
                    temperature=0.3,
                    max_tokens=1000
                )

                insights.append({
                    'type': 'comparison',
                    'content': comparison_result.content
                })

            elif analysis_type == 'trends':
                # Identify trends in data
                trends_prompt = f"""Identify trends and patterns in this data:

Context: {context}

Data:
{json.dumps(data, indent=2, default=str)[:3000]}

Statistics:
{json.dumps(statistics, indent=2)}

Highlight emerging patterns, trends, and anomalies."""

                trends_result = await self.llm_client.generate(
                    prompt=trends_prompt,
                    temperature=0.3,
                    max_tokens=1000
                )

                insights.append({
                    'type': 'trends',
                    'content': trends_result.content
                })

            else:  # 'insights' or default
                # Generate comprehensive insights
                insights_prompt = f"""Analyze this data and generate actionable insights:

Context: {context}

Data:
{json.dumps(data, indent=2, default=str)[:3000]}

Statistics:
{json.dumps(statistics, indent=2)}

Provide:
1. Key findings
2. Notable patterns
3. Actionable recommendations
4. Potential issues or concerns"""

                insights_result = await self.llm_client.generate(
                    prompt=insights_prompt,
                    temperature=0.4,
                    max_tokens=1200
                )

                insights.append({
                    'type': 'insights',
                    'content': insights_result.content
                })

            # Format output
            if output_format == 'json':
                analysis_output = {
                    'statistics': statistics,
                    'insights': insights
                }
            elif output_format == 'markdown':
                md_parts = [f"# Analysis: {context}\n"]
                md_parts.append("\n## Statistics\n")
                for key, stats in statistics.items():
                    md_parts.append(f"- **{key}**: {stats}\n")
                md_parts.append("\n## Insights\n")
                for insight in insights:
                    md_parts.append(f"\n### {insight['type'].title()}\n")
                    md_parts.append(f"{insight['content']}\n")
                analysis_output = ''.join(md_parts)
            else:  # 'text'
                text_parts = [f"Analysis: {context}\n\n"]
                text_parts.append("Statistics:\n")
                for key, stats in statistics.items():
                    text_parts.append(f"  {key}: {stats}\n")
                text_parts.append("\nInsights:\n")
                for insight in insights:
                    text_parts.append(f"\n{insight['type'].title()}:\n{insight['content']}\n")
                analysis_output = ''.join(text_parts)

            # Store analysis in shared memory
            await self.shared_memory.set(
                f"analysis_{task.task_id}",
                {
                    'statistics': statistics,
                    'insights': insights,
                    'output': analysis_output,
                    'timestamp': datetime.now().isoformat()
                }
            )

            return {
                "status": "completed",
                "statistics": statistics,
                "insights": insights,
                "output": analysis_output,
                "summary": f"Generated {len(insights)} insights from data analysis"
            }

        except Exception as e:
            logger.error(f"AnalystAgent error: {e}")
            raise


class WriterAgent(AgentWorker):
    """Agent specialized in content generation and formatting."""

    def __init__(self, agent_id: str, broker: MessageBroker, shared_memory: SharedMemory):
        super().__init__(agent_id, AgentRole.WRITER, broker, shared_memory)
        self.capabilities = {"content_generation", "formatting", "summarization"}
        self.llm_client = None

    async def execute_task(self, task: AgentTask) -> Any:
        """
        Execute writing task - generate and format content.

        Task metadata can include:
        - content_type: Type of content (email, report, summary, description)
        - data: Source data for content generation
        - format: Output format (text, markdown, html)
        - tone: Writing tone (professional, casual, technical)
        - length: Target length (short, medium, long)
        - template: Optional template to use
        """
        logger.info(f"WriterAgent {self.agent_id} executing: {task.description}")

        try:
            # Import required modules
            from .llm_client import get_llm_client

            # Initialize LLM client if needed
            if not self.llm_client:
                self.llm_client = get_llm_client()

            # Parse task parameters
            content_type = task.metadata.get('content_type', 'text')
            data = task.metadata.get('data', {})
            output_format = task.metadata.get('format', 'text')
            tone = task.metadata.get('tone', 'professional')
            length = task.metadata.get('length', 'medium')
            template = task.metadata.get('template', '')
            context = task.metadata.get('context', task.description)

            # Determine target word count based on length
            word_counts = {
                'short': 100,
                'medium': 300,
                'long': 600
            }
            target_words = word_counts.get(length, 300)

            generated_content = ""

            # Generate content based on type
            if content_type == 'email':
                # Generate email
                email_prompt = f"""Write a professional email based on this context:

Context: {context}

Data/Information:
{json.dumps(data, indent=2, default=str)[:2000] if data else 'None'}

Requirements:
- Tone: {tone}
- Length: {length} (~{target_words} words)
- Include subject line

Generate a well-structured email."""

                result = await self.llm_client.generate(
                    prompt=email_prompt,
                    temperature=0.5,
                    max_tokens=target_words * 2
                )

                generated_content = result.content

            elif content_type == 'report':
                # Generate report
                report_prompt = f"""Write a comprehensive report based on this information:

Topic: {context}

Data/Findings:
{json.dumps(data, indent=2, default=str)[:3000] if data else 'None'}

Requirements:
- Tone: {tone}
- Length: {length}
- Include: Executive Summary, Key Findings, Recommendations
- Format: {output_format}

Generate a well-structured report."""

                result = await self.llm_client.generate(
                    prompt=report_prompt,
                    temperature=0.4,
                    max_tokens=target_words * 3
                )

                generated_content = result.content

            elif content_type == 'summary':
                # Generate summary
                summary_prompt = f"""Summarize this information concisely:

Context: {context}

Source Data:
{json.dumps(data, indent=2, default=str)[:3000] if data else 'None'}

Requirements:
- Length: {length} (~{target_words} words)
- Tone: {tone}
- Focus on key points only

Generate a clear, concise summary."""

                result = await self.llm_client.generate(
                    prompt=summary_prompt,
                    temperature=0.3,
                    max_tokens=target_words * 2
                )

                generated_content = result.content

            elif content_type == 'description':
                # Generate description
                desc_prompt = f"""Write a compelling description:

Subject: {context}

Details:
{json.dumps(data, indent=2, default=str)[:2000] if data else 'None'}

Requirements:
- Tone: {tone}
- Length: {length} (~{target_words} words)
- Engaging and informative

Generate a well-crafted description."""

                result = await self.llm_client.generate(
                    prompt=desc_prompt,
                    temperature=0.6,
                    max_tokens=target_words * 2
                )

                generated_content = result.content

            else:
                # Generic content generation
                generic_prompt = f"""Generate content based on these requirements:

Task: {context}

Input Data:
{json.dumps(data, indent=2, default=str)[:2000] if data else 'None'}

Requirements:
- Type: {content_type}
- Tone: {tone}
- Length: {length} (~{target_words} words)
- Format: {output_format}

{f'Template to follow: {template}' if template else ''}

Generate high-quality content."""

                result = await self.llm_client.generate(
                    prompt=generic_prompt,
                    temperature=0.5,
                    max_tokens=target_words * 2
                )

                generated_content = result.content

            # Apply formatting
            if output_format == 'markdown' and not generated_content.startswith('#'):
                # Add markdown structure if not present
                formatted_content = f"# {context}\n\n{generated_content}"
            elif output_format == 'html':
                # Basic HTML wrapping
                formatted_content = f"<html><body><h1>{context}</h1><div>{generated_content.replace(chr(10), '<br>')}</div></body></html>"
            else:
                formatted_content = generated_content

            # Store generated content in shared memory
            await self.shared_memory.set(
                f"content_{task.task_id}",
                {
                    'content': formatted_content,
                    'type': content_type,
                    'format': output_format,
                    'word_count': len(formatted_content.split()),
                    'timestamp': datetime.now().isoformat()
                }
            )

            return {
                "status": "completed",
                "content": formatted_content,
                "content_type": content_type,
                "format": output_format,
                "word_count": len(formatted_content.split()),
                "summary": f"Generated {content_type} content ({len(formatted_content.split())} words)"
            }

        except Exception as e:
            logger.error(f"WriterAgent error: {e}")
            raise


class AgentOrchestrator:
    """
    Central orchestrator managing multi-agent swarm
    Handles coordination, task distribution, and monitoring
    """

    def __init__(
        self,
        orchestrator_id: str = "orchestrator",
        auto_scale: bool = True,
        min_agents: int = 2,
        max_agents: int = 10
    ):
        self.orchestrator_id = orchestrator_id
        self.auto_scale = auto_scale
        self.min_agents = min_agents
        self.max_agents = max_agents

        # Core components
        self.broker = MessageBroker()
        self.shared_memory = SharedMemory()
        self.task_distributor = TaskDistributor(self.shared_memory)
        self.leader_election = LeaderElection(orchestrator_id)

        # Circuit breaker for agent fault isolation
        self._agent_circuits = CircuitBreaker(
            failure_threshold=3,
            success_threshold=2,
            reset_timeout=30.0
        )

        # Agent registry
        self.agents: Dict[str, AgentWorker] = {}
        self.agent_types: Dict[AgentRole, type] = {
            AgentRole.RESEARCHER: ResearcherAgent,
            AgentRole.EXTRACTOR: ExtractorAgent,
            AgentRole.VALIDATOR: ValidatorAgent,
            AgentRole.ANALYST: AnalystAgent,
            AgentRole.WRITER: WriterAgent,
        }

        # State
        self._running = False
        self._coordination_loop: Optional[asyncio.Task] = None
        self._health_monitor_loop: Optional[asyncio.Task] = None

        # Metrics
        self.total_tasks_processed = 0
        self.total_tasks_failed = 0

    async def start(self):
        """Start the orchestrator"""
        logger.info(f"Starting AgentOrchestrator {self.orchestrator_id}")

        # Attempt leader election (async)
        if not await self.leader_election.run_election():
            logger.warning("Not elected as leader, running in follower mode")
            # In follower mode, we might have limited functionality
            return

        # Initialize with minimum agents
        await self._spawn_initial_agents()

        # Start coordination loop
        self._running = True
        self._coordination_loop = asyncio.create_task(self._coordination_loop_task())

        # Start health monitor loop
        self._health_monitor_loop = asyncio.create_task(self._health_monitor_task())

        logger.info("AgentOrchestrator started successfully")

    async def stop(self):
        """Stop the orchestrator"""
        logger.info("Stopping AgentOrchestrator")

        self._running = False

        # Stop coordination loop
        if self._coordination_loop:
            self._coordination_loop.cancel()
            try:
                await self._coordination_loop
            except asyncio.CancelledError:
                pass

        # Stop health monitor loop
        if self._health_monitor_loop:
            self._health_monitor_loop.cancel()
            try:
                await self._health_monitor_loop
            except asyncio.CancelledError:
                pass

        # Stop all agents
        for agent in list(self.agents.values()):
            await agent.stop()

        # Resign as leader
        self.leader_election.resign()

        logger.info("AgentOrchestrator stopped")

    async def _spawn_initial_agents(self):
        """Spawn initial set of agents"""
        for role in [AgentRole.RESEARCHER, AgentRole.EXTRACTOR, AgentRole.VALIDATOR]:
            await self.spawn_agent(role)

    async def spawn_agent(self, role: AgentRole) -> Optional[AgentWorker]:
        """Spawn a new agent of specified role"""
        if len(self.agents) >= self.max_agents:
            logger.warning(f"Cannot spawn agent, at max capacity ({self.max_agents})")
            return None

        agent_class = self.agent_types.get(role)
        if not agent_class:
            logger.error(f"No agent class for role {role}")
            return None

        # Create agent ID
        agent_id = f"{role.value}_{len([a for a in self.agents.values() if a.role == role])}"

        # Instantiate agent
        agent = agent_class(agent_id, self.broker, self.shared_memory)
        self.agents[agent_id] = agent

        # Start agent
        await agent.start()

        logger.info(f"Spawned agent {agent_id} ({role.name})")

        return agent

    async def _coordination_loop_task(self):
        """Main coordination loop"""
        while self._running:
            try:
                # Check agent health
                await self._check_agent_health()

                # Distribute tasks
                await self._distribute_tasks()

                # Auto-scale if enabled
                if self.auto_scale:
                    await self._auto_scale()

                # Collect metrics
                await self._collect_metrics()

                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Coordination loop error: {e}")

    async def _check_agent_health(self):
        """Check health of all agents"""
        for agent_id, agent in list(self.agents.items()):
            if agent.status == AgentStatus.ERROR:
                logger.warning(f"Agent {agent_id} in error state, restarting")
                await agent.stop()
                del self.agents[agent_id]

                # Spawn replacement
                await self.spawn_agent(agent.role)

    async def _distribute_tasks(self):
        """Distribute pending tasks to available agents with circuit breaker protection"""
        # Find idle agents with healthy circuits
        available_agents = [
            agent for agent in self.agents.values()
            if agent.status == AgentStatus.IDLE and self._agent_circuits.can_execute(f"agent:{agent.agent_id}")
        ]

        if not available_agents:
            return

        # Assign tasks
        assignments = await self.task_distributor.assign_tasks(available_agents)

        # Send task assignments with circuit breaker protection
        for agent_id, task in assignments:
            circuit_id = f"agent:{agent_id}"

            # Check circuit state before sending
            if not self._agent_circuits.can_execute(circuit_id):
                logger.warning(f"Circuit open for agent {agent_id}, skipping task assignment")
                # Put task back in queue
                await self.task_distributor.retry_task(task)
                continue

            message = Message(
                message_id=f"assign_{task.task_id}",
                message_type=MessageType.TASK_ASSIGNMENT,
                from_agent=self.orchestrator_id,
                to_agent=agent_id,
                payload={"task": asdict(task)}
            )

            # Send with acknowledgment
            success = await self.broker.send_with_ack(message, timeout=10.0)

            if success:
                self._agent_circuits.record_success(circuit_id)
            else:
                self._agent_circuits.record_failure(circuit_id)
                logger.error(f"Failed to assign task {task.task_id} to agent {agent_id}")
                # Put task back in queue for retry
                await self.task_distributor.retry_task(task)

    async def _auto_scale(self):
        """Auto-scale agent pool based on workload"""
        queue_sizes = self.task_distributor.get_queue_sizes()
        total_queued = sum(queue_sizes.values())

        active_agents = len([a for a in self.agents.values() if a.status == AgentStatus.BUSY])
        idle_agents = len([a for a in self.agents.values() if a.status == AgentStatus.IDLE])

        # Scale up if queue is backing up
        if total_queued > 10 and idle_agents == 0 and len(self.agents) < self.max_agents:
            logger.info(f"Scaling up: {total_queued} tasks queued")
            # Spawn agent of most needed role
            await self.spawn_agent(AgentRole.EXECUTOR)

        # Scale down if too many idle agents
        elif idle_agents > 3 and len(self.agents) > self.min_agents:
            logger.info(f"Scaling down: {idle_agents} idle agents")
            # Remove an idle agent
            for agent in self.agents.values():
                if agent.status == AgentStatus.IDLE:
                    await agent.stop()
                    del self.agents[agent.agent_id]
                    break

    async def _collect_metrics(self):
        """Collect metrics from all agents"""
        # This could be expanded to aggregate metrics and save to disk
        pass

    async def _health_monitor_task(self):
        """Background task to monitor agent health and manage circuit breakers"""
        while self._running:
            try:
                for agent_id, agent in list(self.agents.items()):
                    circuit_id = f"agent:{agent_id}"

                    # Check if agent is responding (has sent heartbeat recently)
                    if not self._is_agent_alive(agent):
                        logger.warning(f"Agent {agent_id} not responding (no recent heartbeat)")
                        self._agent_circuits.record_failure(circuit_id)

                        # If circuit is open, restart agent
                        if self._agent_circuits.get_state(circuit_id) == CircuitState.OPEN:
                            logger.info(f"Restarting unresponsive agent {agent_id}")
                            await self._restart_agent(agent_id)
                    else:
                        # Agent is healthy, record success if circuit was previously failing
                        state = self._agent_circuits.get_state(circuit_id)
                        if state in [CircuitState.HALF_OPEN, CircuitState.OPEN]:
                            self._agent_circuits.record_success(circuit_id)

                await asyncio.sleep(5)  # Check every 5 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")

    def _is_agent_alive(self, agent: AgentWorker) -> bool:
        """Check if agent is alive based on recent activity"""
        # Agent is alive if it's not in ERROR or STOPPED state
        # and has recent activity in metrics
        if agent.status in [AgentStatus.ERROR, AgentStatus.STOPPED]:
            return False

        # Check if agent has recent activity (last 30 seconds)
        try:
            last_active = datetime.fromisoformat(agent.metrics.last_active)
            age = (datetime.now() - last_active).total_seconds()
            return age < 30
        except Exception:
            return True  # Assume alive if we can't parse timestamp

    async def _restart_agent(self, agent_id: str):
        """Restart a failed agent"""
        logger.info(f"Restarting agent {agent_id}")

        old_agent = self.agents.get(agent_id)
        if old_agent:
            role = old_agent.role
            await old_agent.stop()
            del self.agents[agent_id]
        else:
            # If agent not found, use default role
            role = AgentRole.EXECUTOR

        # Spawn new agent with same role
        new_agent = await self.spawn_agent(role)

        # Reset circuit
        circuit_id = f"agent:{agent_id}"
        self._agent_circuits.reset(circuit_id)

        return new_agent

    def get_healthy_agents(self) -> List[str]:
        """Get list of agents with closed circuits"""
        healthy = []
        for agent_id in self.agents:
            if self._agent_circuits.can_execute(f"agent:{agent_id}"):
                healthy.append(agent_id)
        return healthy

    async def submit_task(
        self,
        description: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        required_role: Optional[AgentRole] = None,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Submit a task for execution

        Returns:
            task_id
        """
        task_id = hashlib.md5(f"{description}_{time.time()}".encode()).hexdigest()[:16]

        await self.task_distributor.submit_task(
            task_id=task_id,
            description=description,
            priority=priority,
            required_role=required_role,
            metadata=metadata
        )

        logger.info(f"Task {task_id} submitted: {description}")

        return task_id

    async def get_task_result(self, task_id: str, timeout: float = 60.0) -> Optional[Any]:
        """
        Wait for task result

        Args:
            task_id: Task ID to wait for
            timeout: Max seconds to wait

        Returns:
            Task result or None if timeout
        """
        start_time = time.time()

        while (time.time() - start_time) < timeout:
            task = await self.task_distributor.get_task_status(task_id)

            if task and task.status == "completed":
                return task.result
            elif task and task.status == "failed":
                raise Exception(f"Task failed: {task.error}")

            await asyncio.sleep(0.5)

        return None

    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status including circuit breaker states"""
        return {
            "orchestrator_id": self.orchestrator_id,
            "is_leader": self.leader_election.is_leader,
            "total_agents": len(self.agents),
            "healthy_agents": len(self.get_healthy_agents()),
            "agents_by_status": {
                status.value: len([a for a in self.agents.values() if a.status == status])
                for status in AgentStatus
            },
            "agents_by_role": {
                role.value: len([a for a in self.agents.values() if a.role == role])
                for role in AgentRole
            },
            "queue_sizes": self.task_distributor.get_queue_sizes(),
            "total_tasks_processed": self.total_tasks_processed,
            "total_tasks_failed": self.total_tasks_failed,
            "circuit_breakers": self._agent_circuits.get_all_stats(),
            "agents": [agent.get_status() for agent in self.agents.values()]
        }


# Convenience functions
async def create_agent_swarm(
    num_agents: int = 5,
    roles: Optional[List[AgentRole]] = None
) -> AgentOrchestrator:
    """
    Create and start an agent swarm

    Args:
        num_agents: Number of agents to create
        roles: List of roles (if None, will create balanced mix)

    Returns:
        Running AgentOrchestrator
    """
    orchestrator = AgentOrchestrator(
        orchestrator_id="swarm_orchestrator",
        max_agents=num_agents
    )

    await orchestrator.start()

    # Spawn additional agents if needed
    if roles:
        for role in roles:
            await orchestrator.spawn_agent(role)
    else:
        # Create balanced mix
        default_roles = [
            AgentRole.RESEARCHER,
            AgentRole.EXTRACTOR,
            AgentRole.VALIDATOR,
        ]
        for i in range(num_agents - len(orchestrator.agents)):
            role = default_roles[i % len(default_roles)]
            await orchestrator.spawn_agent(role)

    return orchestrator


async def execute_task_with_swarm(
    task_description: str,
    orchestrator: Optional[AgentOrchestrator] = None
) -> Any:
    """
    Execute a single task using agent swarm

    Args:
        task_description: Task to execute
        orchestrator: Existing orchestrator or None to create new one

    Returns:
        Task result
    """
    # Create orchestrator if needed
    created_new = False
    if not orchestrator:
        orchestrator = await create_agent_swarm(num_agents=3)
        created_new = True

    try:
        # Submit task
        task_id = await orchestrator.submit_task(task_description)

        # Wait for result
        result = await orchestrator.get_task_result(task_id, timeout=120)

        return result

    finally:
        if created_new:
            await orchestrator.stop()


# Example usage
if __name__ == "__main__":
    async def main():
        # Create orchestrator
        orchestrator = AgentOrchestrator(
            orchestrator_id="example_orchestrator",
            max_agents=5
        )

        await orchestrator.start()

        # Submit some tasks
        task1 = await orchestrator.submit_task(
            "Research company Stripe",
            priority=TaskPriority.HIGH,
            required_role=AgentRole.RESEARCHER
        )

        task2 = await orchestrator.submit_task(
            "Extract contacts from website",
            required_role=AgentRole.EXTRACTOR
        )

        task3 = await orchestrator.submit_task(
            "Validate extracted data",
            required_role=AgentRole.VALIDATOR
        )

        # Wait for results
        try:
            result1 = await orchestrator.get_task_result(task1, timeout=30)
            logger.info(f"Task 1 result: {result1}")

            result2 = await orchestrator.get_task_result(task2, timeout=30)
            logger.info(f"Task 2 result: {result2}")

            result3 = await orchestrator.get_task_result(task3, timeout=30)
            logger.info(f"Task 3 result: {result3}")

        except Exception as e:
            logger.error(f"Task execution failed: {e}")

        # Print status
        status = orchestrator.get_status()
        logger.info(f"Orchestrator status: {json.dumps(status, indent=2)}")

        # Cleanup
        await orchestrator.stop()

    asyncio.run(main())
