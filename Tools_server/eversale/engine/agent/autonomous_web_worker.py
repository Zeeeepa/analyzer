"""
Autonomous Web Worker - The Ultimate Forever Agent

This is the crown jewel that combines:
- Forever Operations (never stops)
- World Class Agent (natural language + patterns)
- Dream Mode (self-improvement)
- Brain Enhanced (ReAct + vision + tools)

It can understand ANY natural language request and execute it indefinitely.

Examples:
- "Check my competitor's pricing every hour and alert me of changes"
- "Monitor my inbox and respond to customer inquiries"
- "Scrape leads from Facebook Ads continuously"
- "Watch Hacker News for AI mentions and summarize them"
- "Process my task queue forever - each task is a URL to scrape"

This is Claude Code / Codex with steroids + Playwright MCP for true web automation.
"""

import asyncio
import json
import time
import hashlib
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from loguru import logger
import threading

# Import our modules
from .forever_operations import ForeverWorker, ForeverConfig, WorkerState, DreamThought
from .world_class_agent import (
    WorldClassAgent,
    NaturalLanguageInterpreter,
    ParsedTask,
    TaskIntent,
    ProactiveMonitor,
    PatternLibrary,
    ConversationMemory
)
from .long_running_resilience import ResilienceManager


# =============================================================================
# AUTONOMOUS WORKER STATES
# =============================================================================

class AutonomousMode(Enum):
    """Operating modes for the autonomous worker."""
    INTERACTIVE = "interactive"    # Waiting for user input
    EXECUTING = "executing"        # Running a task
    MONITORING = "monitoring"      # Watching for changes
    PROCESSING = "processing"      # Processing a queue
    DREAMING = "dreaming"          # Self-improvement mode
    PAUSED = "paused"              # Temporarily paused
    RECOVERY = "recovery"          # Recovering from error


# =============================================================================
# TASK QUEUE
# =============================================================================

@dataclass
class QueuedTask:
    """A task in the queue."""
    task_id: str
    prompt: str                    # Natural language prompt
    priority: int = 5              # 1-10, 10 is highest
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    status: str = "pending"        # pending, running, completed, failed
    result: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict = field(default_factory=dict)


class TaskQueue:
    """Priority queue for tasks."""

    def __init__(self, storage_path: Path = None):
        self.storage_path = storage_path
        self.tasks: Dict[str, QueuedTask] = {}
        self._load()

    def add(self, prompt: str, priority: int = 5, metadata: Dict = None) -> str:
        """Add a task to the queue."""
        task_id = hashlib.md5(f"{prompt}:{datetime.now().isoformat()}".encode()).hexdigest()[:12]

        task = QueuedTask(
            task_id=task_id,
            prompt=prompt,
            priority=priority,
            created_at=datetime.now().isoformat(),
            metadata=metadata or {}
        )

        self.tasks[task_id] = task
        self._save()

        logger.info(f"[QUEUE] Added task {task_id}: {prompt[:50]}...")
        return task_id

    def get_next(self) -> Optional[QueuedTask]:
        """Get the next task to run (highest priority pending)."""
        pending = [t for t in self.tasks.values() if t.status == "pending"]
        if not pending:
            return None

        pending.sort(key=lambda t: (-t.priority, t.created_at))
        return pending[0]

    def mark_running(self, task_id: str):
        """Mark a task as running."""
        if task_id in self.tasks:
            self.tasks[task_id].status = "running"
            self.tasks[task_id].started_at = datetime.now().isoformat()
            self._save()

    def mark_completed(self, task_id: str, result: str):
        """Mark a task as completed."""
        if task_id in self.tasks:
            self.tasks[task_id].status = "completed"
            self.tasks[task_id].completed_at = datetime.now().isoformat()
            self.tasks[task_id].result = result
            self._save()

    def mark_failed(self, task_id: str, error: str):
        """Mark a task as failed or retry."""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.retry_count += 1
            task.error = error

            if task.retry_count < task.max_retries:
                task.status = "pending"  # Will retry
            else:
                task.status = "failed"

            self._save()

    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        stats = {"pending": 0, "running": 0, "completed": 0, "failed": 0}
        for task in self.tasks.values():
            stats[task.status] = stats.get(task.status, 0) + 1
        return stats

    def _load(self):
        """Load queue from disk."""
        if self.storage_path and self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text())
                for tid, tdata in data.items():
                    self.tasks[tid] = QueuedTask(**tdata)
            except Exception as e:
                logger.warning(f"Failed to load queue: {e}")

    def _save(self):
        """Save queue to disk."""
        if self.storage_path:
            data = {tid: asdict(t) for tid, t in self.tasks.items()}
            self.storage_path.write_text(json.dumps(data, indent=2))


# =============================================================================
# AUTONOMOUS WEB WORKER
# =============================================================================

@dataclass
class WorkerConfig:
    """Configuration for the autonomous worker."""
    # Identity
    name: str = "autonomous_worker"
    user_id: str = "default"

    # Work directory
    work_dir: Path = None

    # Forever mode settings
    forever_enabled: bool = True
    poll_interval_seconds: float = 30.0
    max_runtime_hours: float = 0  # 0 = unlimited

    # Queue processing
    process_queue: bool = True
    max_parallel_tasks: int = 1  # Can be increased for parallel

    # Monitoring
    monitoring_enabled: bool = True
    check_monitors_interval: int = 60

    # Dream mode
    dream_mode_enabled: bool = True
    dream_idle_threshold_minutes: float = 5.0

    # Resilience
    checkpoint_interval: int = 100  # Steps between checkpoints
    max_consecutive_errors: int = 10
    error_backoff_seconds: float = 60.0

    # Browser
    headless: bool = True
    browser_timeout: int = 30000


class AutonomousWebWorker:
    """
    The ultimate autonomous web worker.

    Usage:
        # Simple usage
        worker = AutonomousWebWorker()
        worker.run_forever("Check my inbox every 5 minutes and respond to urgent emails")

        # Or with queue
        worker = AutonomousWebWorker()
        worker.add_task("Scrape amazon.com for product prices")
        worker.add_task("Research competitor XYZ")
        worker.add_task("Fill out form at site.com/contact")
        worker.run_forever()  # Processes queue forever
    """

    def __init__(self, config: WorkerConfig = None):
        self.config = config or WorkerConfig()

        # Set up work directory
        if self.config.work_dir is None:
            self.config.work_dir = Path.home() / '.eversale' / 'autonomous' / self.config.name
        self.config.work_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.agent = WorldClassAgent(
            user_id=self.config.user_id,
            work_dir=self.config.work_dir / 'agent'
        )

        self.queue = TaskQueue(self.config.work_dir / 'queue.json')

        self.resilience = ResilienceManager(
            task_id=f"autonomous_{self.config.name}",
            checkpoint_dir=self.config.work_dir / 'checkpoints'
        )

        # State
        self.mode = AutonomousMode.INTERACTIVE
        self.is_running = False
        self.start_time: Optional[datetime] = None
        self.tasks_completed = 0
        self.errors_count = 0
        self.consecutive_errors = 0
        self.last_activity = ""
        self.current_task: Optional[QueuedTask] = None

        # Dream mode
        self.dreams: List[DreamThought] = []
        self.last_task_time = datetime.now()
        self.idle_cycles = 0

        # Signal handling
        self._stop_requested = False
        self._setup_signal_handlers()

        # Executor callback (set by integrator with Brain)
        self.execute_prompt: Optional[Callable[[str], str]] = None

        logger.info(f"[AUTONOMOUS] Worker '{self.config.name}' initialized at {self.config.work_dir}")

    def add_task(self, prompt: str, priority: int = 5, metadata: Dict = None) -> str:
        """Add a task to the queue."""
        return self.queue.add(prompt, priority, metadata)

    def add_watch(
        self,
        url: str,
        watch_for: str = "change",
        interval_minutes: int = 5,
        alert_action: str = "log"
    ) -> str:
        """Add a monitoring watch."""
        return self.agent.add_watch(url, watch_for, interval_minutes, alert_action)

    def run_forever(self, initial_prompt: str = None):
        """
        Run the worker forever.

        Args:
            initial_prompt: Optional natural language prompt to start with.
                           If provided, this defines the forever task.
                           If not, processes the queue forever.
        """
        logger.info(f"[AUTONOMOUS] Starting forever mode for '{self.config.name}'")
        self.is_running = True
        self.start_time = datetime.now()
        self.mode = AutonomousMode.EXECUTING if initial_prompt else AutonomousMode.PROCESSING

        # Parse initial prompt if provided
        initial_task = None
        if initial_prompt:
            initial_task = self.agent.nlp.parse(initial_prompt)
            logger.info(f"[AUTONOMOUS] Initial task: {initial_task.intent.value}")

            # Add to queue as high priority
            self.queue.add(initial_prompt, priority=10)

        try:
            self._main_loop(initial_task)
        except KeyboardInterrupt:
            logger.info("[AUTONOMOUS] Keyboard interrupt received")
        finally:
            self._shutdown()

    def _main_loop(self, initial_task: ParsedTask = None):
        """Main processing loop."""
        cycle = 0

        while not self._should_stop():
            cycle += 1
            cycle_start = time.time()

            try:
                # Check monitors if enabled
                if self.config.monitoring_enabled and cycle % 10 == 0:
                    self._check_monitors()

                # Process queue
                if self.config.process_queue:
                    task = self.queue.get_next()

                    if task:
                        self.mode = AutonomousMode.EXECUTING
                        self._process_task(task)
                        self.last_task_time = datetime.now()
                        self.idle_cycles = 0
                        self.consecutive_errors = 0
                    else:
                        self.idle_cycles += 1

                        # Enter dream mode if idle too long
                        if self._should_dream():
                            self._enter_dream_mode()

                # Checkpoint periodically
                if cycle % self.config.checkpoint_interval == 0:
                    self._checkpoint(cycle)

                # Calculate sleep time
                elapsed = time.time() - cycle_start
                sleep_time = max(0, self.config.poll_interval_seconds - elapsed)

                if sleep_time > 0:
                    self.mode = AutonomousMode.MONITORING
                    self.last_activity = f"Sleeping for {sleep_time:.1f}s"
                    self._interruptible_sleep(sleep_time)

            except Exception as e:
                self._handle_error(e)

        logger.info(f"[AUTONOMOUS] Exiting main loop after {cycle} cycles")

    def _process_task(self, task: QueuedTask):
        """Process a single task."""
        self.current_task = task
        self.queue.mark_running(task.task_id)

        logger.info(f"[AUTONOMOUS] Processing task {task.task_id}: {task.prompt[:60]}...")
        self.last_activity = f"Processing: {task.prompt[:40]}..."

        try:
            # Parse the prompt
            parsed = self.agent.nlp.parse(task.prompt)
            logger.info(f"[AUTONOMOUS] Intent: {parsed.intent.value}, Target: {parsed.target}")

            # Execute the task
            if self.execute_prompt:
                result = self.execute_prompt(task.prompt)
            else:
                # Fallback: just log what we would do
                result = self._simulate_execution(parsed)

            # Mark completed
            self.queue.mark_completed(task.task_id, result)
            self.tasks_completed += 1

            # Learn from success
            self.agent.memory.remember_request(
                text=task.prompt,
                parsed=parsed,
                result=result,
                success=True
            )

            logger.info(f"[AUTONOMOUS] Task {task.task_id} completed successfully")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[AUTONOMOUS] Task {task.task_id} failed: {error_msg}")
            self.queue.mark_failed(task.task_id, error_msg)
            self.errors_count += 1
            self.consecutive_errors += 1

        finally:
            self.current_task = None

    def _simulate_execution(self, parsed: ParsedTask) -> str:
        """Simulate task execution when no executor is set."""
        # This is a placeholder - in real usage, Brain would be connected
        intent_actions = {
            TaskIntent.SCRAPE: f"Would scrape data from {parsed.target}",
            TaskIntent.RESEARCH: f"Would research {parsed.target}",
            TaskIntent.FIND_LEADS: f"Would find leads for {parsed.target}",
            TaskIntent.MONITOR: f"Would start monitoring {parsed.target}",
            TaskIntent.FILL_FORM: f"Would fill form at {parsed.target}",
            TaskIntent.COMPARE: f"Would compare {parsed.target}",
            TaskIntent.SUMMARIZE: f"Would summarize {parsed.target}",
        }

        action = intent_actions.get(parsed.intent, f"Would process: {parsed.original_text}")

        # Simulate some work
        time.sleep(1)

        return action

    def _check_monitors(self):
        """Check all monitors for changes."""
        def page_fetcher(url: str) -> str:
            # In real usage, this would use Playwright to fetch pages
            return f"<html>Mock content for {url}</html>"

        events = self.agent.monitor.check_all(page_fetcher)

        for event in events:
            logger.warning(f"[AUTONOMOUS] Monitor event: {event.change_type} on {event.url}")

            # Could trigger a task based on the event
            if event.change_type in ['value_decreased', 'below_threshold']:
                self.add_task(
                    f"Price drop detected on {event.url}: {event.old_value} -> {event.new_value}. Take action.",
                    priority=8
                )

    def _should_dream(self) -> bool:
        """Check if we should enter dream mode."""
        if not self.config.dream_mode_enabled:
            return False

        idle_minutes = (datetime.now() - self.last_task_time).total_seconds() / 60
        return idle_minutes >= self.config.dream_idle_threshold_minutes

    def _enter_dream_mode(self):
        """Enter dream mode for self-improvement."""
        self.mode = AutonomousMode.DREAMING
        self.last_activity = "Dreaming - analyzing patterns"

        logger.info(f"[AUTONOMOUS] Entering dream mode after {self.idle_cycles} idle cycles")

        # Analyze patterns
        thoughts = []

        # 1. Analyze task success patterns
        profile = self.agent.memory.get_user_profile()
        if profile['total_requests'] > 0:
            success_rate = profile['success_rate']
            if success_rate < 0.8:
                thoughts.append(DreamThought(
                    timestamp=datetime.now().isoformat(),
                    category="improvement",
                    insight=f"Task success rate is {success_rate:.1%}. Review common failure patterns.",
                    priority=4
                ))

        # 2. Analyze queue health
        queue_stats = self.queue.get_stats()
        if queue_stats['failed'] > 5:
            thoughts.append(DreamThought(
                timestamp=datetime.now().isoformat(),
                category="warning",
                insight=f"{queue_stats['failed']} tasks have failed. Consider reviewing error patterns.",
                priority=5
            ))

        # 3. Suggest optimizations
        uptime_hours = (datetime.now() - self.start_time).total_seconds() / 3600 if self.start_time else 0
        if uptime_hours > 12 and self.consecutive_errors == 0:
            thoughts.append(DreamThought(
                timestamp=datetime.now().isoformat(),
                category="optimization",
                insight=f"Running stably for {uptime_hours:.1f}h. System is healthy.",
                priority=1
            ))

        self.dreams.extend(thoughts)

        # Keep only recent dreams
        if len(self.dreams) > 100:
            self.dreams = self.dreams[-50:]

        logger.info(f"[AUTONOMOUS] Dream mode generated {len(thoughts)} insights")

    def _checkpoint(self, cycle: int):
        """Save checkpoint for recovery."""
        checkpoint = {
            'cycle': cycle,
            'mode': self.mode.value,
            'tasks_completed': self.tasks_completed,
            'errors_count': self.errors_count,
            'queue_stats': self.queue.get_stats(),
            'timestamp': datetime.now().isoformat()
        }

        self.resilience.checkpoint(checkpoint)
        logger.debug(f"[AUTONOMOUS] Checkpoint saved at cycle {cycle}")

    def _handle_error(self, error: Exception):
        """Handle errors in the main loop."""
        self.errors_count += 1
        self.consecutive_errors += 1
        self.mode = AutonomousMode.RECOVERY

        logger.error(f"[AUTONOMOUS] Error in main loop: {error}")

        if self.consecutive_errors >= self.config.max_consecutive_errors:
            logger.warning(f"[AUTONOMOUS] Too many errors ({self.consecutive_errors}), backing off...")
            self._interruptible_sleep(self.config.error_backoff_seconds)
            self.consecutive_errors = 0

    def _should_stop(self) -> bool:
        """Check if we should stop."""
        if self._stop_requested:
            return True

        # Check max runtime
        if self.config.max_runtime_hours > 0 and self.start_time:
            runtime_hours = (datetime.now() - self.start_time).total_seconds() / 3600
            if runtime_hours >= self.config.max_runtime_hours:
                logger.info(f"[AUTONOMOUS] Max runtime reached: {runtime_hours:.1f}h")
                return True

        # Check stop file
        stop_file = self.config.work_dir / 'STOP'
        if stop_file.exists():
            logger.info(f"[AUTONOMOUS] Stop file detected")
            stop_file.unlink()
            return True

        return False

    def _interruptible_sleep(self, seconds: float):
        """Sleep that can be interrupted."""
        end_time = time.time() + seconds
        while time.time() < end_time:
            if self._should_stop():
                break
            time.sleep(min(1.0, end_time - time.time()))

    def _setup_signal_handlers(self):
        """Set up graceful shutdown on signals."""
        def handle_signal(signum, frame):
            logger.info(f"[AUTONOMOUS] Received signal {signum}, requesting stop")
            self._stop_requested = True

        try:
            signal.signal(signal.SIGTERM, handle_signal)
            signal.signal(signal.SIGINT, handle_signal)
        except:
            pass

    def _shutdown(self):
        """Clean shutdown."""
        logger.info(f"[AUTONOMOUS] Shutting down '{self.config.name}'")

        self.is_running = False

        # Save state
        state = {
            'name': self.config.name,
            'mode': self.mode.value,
            'tasks_completed': self.tasks_completed,
            'errors_count': self.errors_count,
            'dreams': [asdict(d) for d in self.dreams[-20:]],
            'shutdown_at': datetime.now().isoformat()
        }

        state_file = self.config.work_dir / 'last_state.json'
        state_file.write_text(json.dumps(state, indent=2))

        logger.info(f"[AUTONOMOUS] Completed {self.tasks_completed} tasks, {self.errors_count} errors")

    def get_status(self) -> Dict[str, Any]:
        """Get current worker status."""
        uptime = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0

        return {
            'name': self.config.name,
            'mode': self.mode.value,
            'is_running': self.is_running,
            'uptime_seconds': uptime,
            'uptime_human': str(timedelta(seconds=int(uptime))),
            'tasks_completed': self.tasks_completed,
            'errors_count': self.errors_count,
            'queue_stats': self.queue.get_stats(),
            'current_task': self.current_task.prompt[:50] if self.current_task else None,
            'last_activity': self.last_activity,
            'dreams_count': len(self.dreams),
            'agent_profile': self.agent.memory.get_user_profile(),
        }

    def request_stop(self):
        """Request graceful stop."""
        self._stop_requested = True


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_autonomous_worker(
    name: str = "default",
    user_id: str = "default"
) -> AutonomousWebWorker:
    """Factory to create an autonomous worker."""
    config = WorkerConfig(name=name, user_id=user_id)
    return AutonomousWebWorker(config)


def run_forever_task(prompt: str, name: str = "forever_task"):
    """Convenience function to run a forever task."""
    worker = create_autonomous_worker(name=name)
    worker.run_forever(prompt)


def process_queue_forever(tasks: List[str], name: str = "queue_processor"):
    """Convenience function to process a queue forever."""
    worker = create_autonomous_worker(name=name)

    for task in tasks:
        worker.add_task(task)

    worker.run_forever()


# =============================================================================
# INTEGRATION WITH BRAIN
# =============================================================================

def integrate_with_brain(worker: AutonomousWebWorker, brain_instance):
    """
    Integrate the autonomous worker with Brain for actual execution.

    Usage:
        from engine.agent.brain_enhanced_v2 import Brain
        from engine.agent.autonomous_web_worker import create_autonomous_worker, integrate_with_brain

        brain = Brain(...)
        worker = create_autonomous_worker("my_worker")
        integrate_with_brain(worker, brain)

        worker.run_forever("Scrape leads from Facebook Ads continuously")
    """
    async def execute_async(prompt: str) -> str:
        result = await brain.run(prompt)
        return result

    def execute_sync(prompt: str) -> str:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(execute_async(prompt))
        finally:
            loop.close()

    worker.execute_prompt = execute_sync
    logger.info("[AUTONOMOUS] Integrated with Brain for task execution")


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    # Demo 1: Simple forever task
    print("\n=== Demo: Natural Language Processing ===")
    worker = create_autonomous_worker("demo")

    test_prompts = [
        "Check my competitor's pricing every hour and alert me of changes",
        "Monitor my inbox and respond to customer inquiries",
        "Scrape leads from Facebook Ads continuously",
        "Watch Hacker News for AI mentions and summarize them",
        "Process my task queue forever",
    ]

    for prompt in test_prompts:
        result = worker.agent.process_request(prompt)
        print(f"\n>>> {prompt}")
        print(f"    Intent: {result['intent']}")
        print(f"    Target: {result['target']}")
        print(f"    Is Forever: {result['is_forever']}")

    # Demo 2: Queue processing
    print("\n=== Demo: Task Queue ===")
    worker.add_task("Scrape product prices from amazon", priority=5)
    worker.add_task("Research competitor XYZ", priority=3)
    worker.add_task("URGENT: Check inventory levels", priority=10)

    print(f"Queue stats: {worker.queue.get_stats()}")

    # Get next task (should be highest priority)
    next_task = worker.queue.get_next()
    print(f"Next task: {next_task.prompt} (priority: {next_task.priority})")

    print("\n=== Worker Status ===")
    print(json.dumps(worker.get_status(), indent=2, default=str))
