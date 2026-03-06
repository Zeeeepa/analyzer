"""
Forever Operations Module - Autonomous Worker Agent Support

Enables agents to run indefinitely as background workers:
- Email inbox monitors
- Telemetry watchers
- Lead scrapers
- Customer support bots
- Data pipeline monitors
- Any "watch and respond" pattern

Key Features:
1. State persistence - survives restarts
2. Deduplication - never process same item twice
3. Heartbeat reporting - prove agent is alive
4. Smart polling - adaptive sleep cycles
5. External stop signal - clean shutdown
6. Activity journaling - full audit trail
7. Checkpoint support for resumable infinite loops

Scalability: Optimized for true 24/7 operation:
- ForeverTaskState class for checkpointing
- Automatic resource cleanup
- Exponential backoff circuit breaker
- No artificial iteration limits
"""

import json
import time
import signal
import hashlib
import gc
import tempfile
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from loguru import logger
import threading

# Import log rotation utilities
try:
    from log_rotation import JSONLRotator, LogRotator, periodic_cleanup
except ImportError:
    # Fallback if log_rotation not available
    JSONLRotator = None
    LogRotator = None
    periodic_cleanup = None
    logger.warning("[FOREVER] log_rotation module not available, rotation disabled")


# === CHECKPOINT STORAGE DIRECTORY ===
CHECKPOINT_DIR = Path.home() / '.eversale' / 'checkpoints'
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


def _check_disk_space(path: Path, min_free_mb: int = 100) -> bool:
    """
    HIGH FIX: Check if there's enough disk space before writing (audit fix).

    Args:
        path: Path where file will be written
        min_free_mb: Minimum free space required in MB (default 100MB)

    Returns:
        True if sufficient space, False otherwise
    """
    try:
        import shutil
        stat = shutil.disk_usage(path.parent if path.parent.exists() else path)
        free_mb = stat.free / (1024 * 1024)
        if free_mb < min_free_mb:
            logger.warning(f"[DISK] Low disk space: {free_mb:.1f}MB free (need {min_free_mb}MB)")
            return False
        return True
    except Exception as e:
        logger.debug(f"[DISK] Failed to check disk space: {e}")
        return True  # Allow write on check failure (don't block on monitoring issues)


def _atomic_write(path: Path, content: str) -> None:
    """
    CRITICAL FIX: Atomic file write to prevent corruption during crashes (audit fix).

    Writes to a temp file first, then atomically renames to target path.
    This ensures the file is never in a partially-written state.
    Includes disk space check to prevent partial writes on full disk.
    """
    # HIGH FIX: Check disk space before attempting write
    if not _check_disk_space(path, min_free_mb=50):
        raise IOError(f"Insufficient disk space to write {path}")

    try:
        # Write to temp file in same directory (for same-filesystem rename)
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk
        except Exception:
            os.close(fd)
            raise

        # Atomic rename (on POSIX systems)
        shutil.move(tmp_path, path)

    except Exception as e:
        # Clean up temp file on failure
        try:
            if 'tmp_path' in locals() and Path(tmp_path).exists():
                Path(tmp_path).unlink()
        except Exception:
            pass
        raise e


# =============================================================================
# FOREVER TASK STATE - For checkpointing infinite loops
# =============================================================================

@dataclass
class ForeverTaskState:
    """
    Checkpoint state for forever/infinite loop operations.

    Thread-safe: Uses RLock for all state mutations (audit fix).

    Enables:
    - Resume from where you left off after restart/crash
    - Track progress across iterations
    - Store partial results
    - Error tracking

    Usage:
        state = ForeverTaskState.load('my_task_id')
        if not state:
            state = ForeverTaskState.create('my_task_id', 'infinite_loop')

        state.processed_items = 100
        state.checkpoint({'last_result': 'some_data'})

        # On restart:
        state = ForeverTaskState.load('my_task_id')
        if state and state.status == 'running':
            resume_from = state.processed_items
    """
    task_id: str
    task_type: str  # 'infinite_loop', 'scheduled', 'timed', etc.
    status: str = 'created'  # 'created', 'running', 'paused', 'completed', 'failed'
    processed_items: int = 0
    results: List[Any] = field(default_factory=list)
    errors: List[Dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    checkpoint_count: int = 0

    # Resource tracking for cleanup
    _memory_at_start_mb: float = 0.0
    _browser_recycled_count: int = 0

    # CRITICAL FIX: Thread lock for concurrent access (audit fix)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    def __post_init__(self):
        """Ensure lock is initialized after dataclass creation."""
        if not hasattr(self, '_lock') or self._lock is None:
            object.__setattr__(self, '_lock', threading.RLock())

    @classmethod
    def load(cls, task_id: str) -> Optional['ForeverTaskState']:
        """Load checkpoint from disk."""
        checkpoint_file = CHECKPOINT_DIR / f'{task_id}.json'
        if not checkpoint_file.exists():
            return None

        try:
            data = json.loads(checkpoint_file.read_text())
            state = cls(
                task_id=data['task_id'],
                task_type=data.get('task_type', 'infinite_loop'),
                status=data.get('status', 'created'),
                processed_items=data.get('processed_items', 0),
                results=data.get('results', [])[-100:],  # Only keep last 100
                errors=data.get('errors', [])[-50:],  # Only keep last 50
                metadata=data.get('metadata', {}),
                created_at=data.get('created_at', datetime.now().isoformat()),
                updated_at=data.get('updated_at', datetime.now().isoformat()),
                checkpoint_count=data.get('checkpoint_count', 0)
            )
            logger.info(f"[CHECKPOINT] Loaded state for task {task_id}: {state.processed_items} items, status={state.status}")
            return state
        except Exception as e:
            logger.warning(f"[CHECKPOINT] Failed to load checkpoint for {task_id}: {e}")
            return None

    @classmethod
    def create(cls, task_id: str, task_type: str = 'infinite_loop') -> 'ForeverTaskState':
        """Create a new task state."""
        state = cls(
            task_id=task_id,
            task_type=task_type,
            status='running'
        )
        # Record initial memory
        try:
            import psutil
            state._memory_at_start_mb = psutil.Process().memory_info().rss / 1024 / 1024
        except ImportError:
            pass
        state._save()
        logger.info(f"[CHECKPOINT] Created new state for task {task_id}")
        return state

    def checkpoint(self, extra_data: Dict = None):
        """Save checkpoint to disk with optional extra data. Thread-safe."""
        with self._lock:
            self.updated_at = datetime.now().isoformat()
            self.checkpoint_count += 1

            if extra_data:
                self.metadata.update(extra_data)

            # Trim results and errors to prevent unbounded growth
            self.results = self.results[-100:]  # Keep last 100
            self.errors = self.errors[-50:]  # Keep last 50

            self._save()
            logger.debug(f"[CHECKPOINT] Saved checkpoint #{self.checkpoint_count} for {self.task_id}")

    def mark_complete(self, final_result: Any = None):
        """Mark task as completed. Thread-safe."""
        with self._lock:
            self.status = 'completed'
            self.updated_at = datetime.now().isoformat()
            if final_result:
                self.metadata['final_result'] = str(final_result)[:500]
            self._save()
            logger.info(f"[CHECKPOINT] Task {self.task_id} marked complete")

    def mark_failed(self, error: str):
        """Mark task as failed. Thread-safe."""
        with self._lock:
            self.status = 'failed'
            self.updated_at = datetime.now().isoformat()
            self.errors.append({
                'timestamp': datetime.now().isoformat(),
                'error': error[:500],
                'type': 'fatal'
            })
            self._save()
            logger.info(f"[CHECKPOINT] Task {self.task_id} marked failed: {error[:100]}")

    def _save(self):
        """Persist to disk using atomic write to prevent corruption."""
        checkpoint_file = CHECKPOINT_DIR / f'{self.task_id}.json'
        try:
            data = {
                'task_id': self.task_id,
                'task_type': self.task_type,
                'status': self.status,
                'processed_items': self.processed_items,
                'results': self.results[-100:],  # Bound at save time
                'errors': self.errors[-50:],
                'metadata': self.metadata,
                'created_at': self.created_at,
                'updated_at': self.updated_at,
                'checkpoint_count': self.checkpoint_count
            }
            # CRITICAL FIX: Use atomic write to prevent corruption (audit fix)
            _atomic_write(checkpoint_file, json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger.warning(f"[CHECKPOINT] Failed to save checkpoint: {e}")

    @staticmethod
    def cleanup_old_checkpoints(max_age_days: int = 7):
        """Remove old checkpoint files."""
        cutoff = datetime.now() - timedelta(days=max_age_days)
        removed = 0
        for checkpoint_file in CHECKPOINT_DIR.glob('*.json'):
            try:
                mtime = datetime.fromtimestamp(checkpoint_file.stat().st_mtime)
                if mtime < cutoff:
                    checkpoint_file.unlink()
                    removed += 1
            except Exception:
                pass
        if removed:
            logger.info(f"[CHECKPOINT] Cleaned up {removed} old checkpoint files")


# =============================================================================
# ENTERPRISE-GRADE CIRCUIT BREAKER
# =============================================================================

@dataclass
class CircuitBreaker:
    """
    Enterprise circuit breaker with exponential backoff.

    Features:
    - Doesn't reset on single success (requires consecutive successes)
    - Exponential backoff up to max_backoff
    - Tracks failure patterns for diagnostics
    - Half-open state for gradual recovery
    """
    name: str = 'default'
    failure_threshold: int = 5
    recovery_threshold: int = 3  # Consecutive successes needed to close
    initial_backoff: float = 10.0
    max_backoff: float = 300.0  # 5 minutes max
    backoff_multiplier: float = 2.0

    # State
    failures: int = 0
    successes_since_failure: int = 0
    current_backoff: float = 10.0
    state: str = 'closed'  # 'closed', 'open', 'half-open'
    last_failure_time: Optional[datetime] = None
    failure_history: List[Dict] = field(default_factory=list)

    def record_success(self):
        """Record a successful operation."""
        if self.state == 'half-open':
            self.successes_since_failure += 1
            if self.successes_since_failure >= self.recovery_threshold:
                # Fully recover
                self.state = 'closed'
                self.failures = 0
                self.successes_since_failure = 0
                self.current_backoff = self.initial_backoff
                logger.info(f"[CIRCUIT:{self.name}] Circuit CLOSED - recovered after {self.recovery_threshold} successes")
        elif self.state == 'closed':
            # Gradual backoff reduction on success
            self.current_backoff = max(self.initial_backoff, self.current_backoff * 0.9)

    def record_failure(self, error: str = ''):
        """Record a failed operation."""
        self.failures += 1
        self.successes_since_failure = 0
        self.last_failure_time = datetime.now()

        # Track failure history (keep last 20)
        self.failure_history.append({
            'timestamp': datetime.now().isoformat(),
            'error': error[:200]
        })
        self.failure_history = self.failure_history[-20:]

        if self.failures >= self.failure_threshold:
            if self.state != 'open':
                self.state = 'open'
                logger.warning(f"[CIRCUIT:{self.name}] Circuit OPEN - {self.failures} failures")

            # Exponential backoff
            self.current_backoff = min(self.max_backoff, self.current_backoff * self.backoff_multiplier)

    def should_allow(self) -> bool:
        """Check if operation should be allowed."""
        if self.state == 'closed':
            return True

        if self.state == 'open':
            # Check if backoff period has passed
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                if elapsed >= self.current_backoff:
                    self.state = 'half-open'
                    logger.info(f"[CIRCUIT:{self.name}] Circuit HALF-OPEN - testing recovery")
                    return True
            return False

        # half-open: allow limited requests
        return True

    def get_backoff_seconds(self) -> float:
        """Get current backoff duration."""
        if self.state == 'open':
            return self.current_backoff
        return 0

    def get_status(self) -> Dict:
        """Get circuit breaker status for diagnostics."""
        return {
            'name': self.name,
            'state': self.state,
            'failures': self.failures,
            'successes_since_failure': self.successes_since_failure,
            'current_backoff': self.current_backoff,
            'last_failure': self.last_failure_time.isoformat() if self.last_failure_time else None,
            'recent_errors': [e['error'][:50] for e in self.failure_history[-5:]]
        }


# =============================================================================
# RESOURCE CLEANUP UTILITIES
# =============================================================================

def cleanup_resources_between_iterations(
    iteration: int,
    collected_data: List,
    max_collected: int = 5000,
    force_gc: bool = True
) -> List:
    """
    Clean up resources between loop iterations to prevent memory leaks.

    Args:
        iteration: Current iteration number
        collected_data: List of collected items
        max_collected: Maximum items to keep in memory
        force_gc: Whether to force garbage collection

    Returns:
        Trimmed collected_data list
    """
    # Trim collected data
    if len(collected_data) > max_collected:
        # Keep only recent items
        trimmed = collected_data[-max_collected:]
        logger.debug(f"[CLEANUP] Trimmed collected_data from {len(collected_data)} to {len(trimmed)}")
        collected_data = trimmed

    # Force garbage collection every 10 iterations
    if force_gc and iteration % 10 == 0:
        gc.collect()
        logger.debug(f"[CLEANUP] Garbage collection triggered at iteration {iteration}")

    return collected_data


async def recycle_browser_if_needed(
    mcp_client,
    iteration: int,
    recycle_every: int = 100,
    state: ForeverTaskState = None
) -> bool:
    """
    Recycle browser instance periodically to prevent memory leaks.

    Args:
        mcp_client: The MCP client with browser connection
        iteration: Current iteration
        recycle_every: Recycle browser every N iterations
        state: Optional state to track recycle count

    Returns:
        True if browser was recycled
    """
    if iteration % recycle_every != 0:
        return False

    try:
        # Close and reconnect browser
        await mcp_client.disconnect_all_servers()
        await mcp_client.connect_all_servers()

        if state:
            state._browser_recycled_count += 1

        logger.info(f"[CLEANUP] Browser recycled at iteration {iteration}")
        return True
    except Exception as e:
        logger.warning(f"[CLEANUP] Browser recycle failed: {e}")
        return False


class WorkerState(Enum):
    """Worker lifecycle states."""
    STARTING = "starting"
    RUNNING = "running"
    SLEEPING = "sleeping"
    PROCESSING = "processing"
    DREAMING = "dreaming"      # NEW: Self-improvement mode during idle time
    PLANNING = "planning"      # NEW: Strategy planning mode
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ProcessedItem:
    """Track processed items to avoid duplicates."""
    item_id: str
    item_hash: str
    processed_at: str
    action_taken: str
    result: str


@dataclass
class HeartbeatReport:
    """Periodic health report."""
    timestamp: str
    state: str
    uptime_seconds: float
    items_processed: int
    errors_count: int
    last_activity: str
    memory_usage_mb: float = 0.0


@dataclass
class DreamThought:
    """A thought/insight from dream mode."""
    timestamp: str
    category: str  # optimization, pattern, improvement, warning
    insight: str
    priority: int  # 1-5, 5 being most important
    acted_upon: bool = False


@dataclass
class ForeverConfig:
    """Configuration for forever operations."""

    # Polling intervals
    poll_interval_seconds: float = 30.0          # How often to check for new items
    min_poll_interval: float = 5.0               # Minimum poll interval
    max_poll_interval: float = 300.0             # Maximum poll interval (5 min)
    adaptive_polling: bool = True                # Slow down when idle, speed up when busy

    # Heartbeat
    heartbeat_interval_seconds: float = 60.0     # How often to report health
    heartbeat_file: str = "heartbeat.json"       # Where to write heartbeat

    # State persistence
    state_file: str = "worker_state.json"        # Persistent state file
    processed_items_file: str = "processed.json" # Track processed items
    max_processed_history: int = 10000           # Max items to remember

    # Deduplication
    dedup_window_hours: int = 24                 # How long to remember processed items

    # Activity journal
    journal_file: str = "activity_journal.jsonl" # Activity log (JSON lines)
    max_journal_entries: int = 50000             # Max journal entries

    # Stop signal
    stop_signal_file: str = "STOP"               # Create this file to stop

    # Error handling
    max_consecutive_errors: int = 10             # Pause after this many errors
    error_backoff_seconds: float = 60.0          # Wait after errors
    auto_recover: bool = True                    # Try to recover from errors

    # Resource limits
    max_items_per_cycle: int = 100               # Process max N items per poll
    max_runtime_hours: float = 0                 # 0 = unlimited

    # DREAM MODE - Self-improvement during idle time
    dream_mode_enabled: bool = True              # Enable dream/planning mode
    idle_threshold_minutes: float = 5.0          # Enter dream mode after N minutes idle
    dream_duration_seconds: float = 30.0         # How long to "dream" each cycle
    dreams_file: str = "dreams.json"             # Store insights/plans
    max_dreams: int = 100                        # Max dreams to remember

    # Dream activities
    dream_analyze_errors: bool = True            # Analyze past errors for patterns
    dream_optimize_strategy: bool = True         # Think about better approaches
    dream_predict_patterns: bool = True          # Predict busy/quiet periods
    dream_self_improve: bool = True              # Generate improvement ideas

    # LOG ROTATION - Prevent unbounded growth
    log_rotation_enabled: bool = True            # Enable automatic log rotation
    journal_max_size_mb: float = 10.0            # Rotate journal when it exceeds this size
    journal_max_rotations: int = 5               # Keep only last N rotated journals
    cleanup_interval_hours: float = 6.0          # Run cleanup every N hours
    checkpoint_max_age_days: int = 7             # Remove checkpoints older than N days
    rotated_logs_max_age_days: int = 30          # Remove rotated logs older than N days


class ForeverWorker:
    """
    Base class for forever-running worker agents.

    Usage:
        class EmailMonitor(ForeverWorker):
            def check_for_items(self) -> List[Dict]:
                # Return list of new emails
                return get_unread_emails()

            def process_item(self, item: Dict) -> str:
                # Process one email, return result
                return respond_to_email(item)

            def get_item_id(self, item: Dict) -> str:
                return item['email_id']

        monitor = EmailMonitor(config)
        monitor.run_forever()
    """

    def __init__(
        self,
        config: ForeverConfig = None,
        work_dir: Path = None,
        worker_name: str = "worker"
    ):
        self.config = config or ForeverConfig()
        self.work_dir = work_dir or Path.home() / '.eversale' / 'workers' / worker_name
        self.worker_name = worker_name

        # Create work directory
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # State
        self.state = WorkerState.STARTING
        self.start_time = datetime.now()
        self.items_processed = 0
        self.errors_count = 0
        self.consecutive_errors = 0
        self.last_activity = "Starting up"
        self.current_poll_interval = self.config.poll_interval_seconds

        # Processed items tracking (deduplication)
        self.processed_items: Dict[str, ProcessedItem] = {}
        self._load_processed_items()

        # Stop signal handling
        self._stop_requested = False
        self._setup_signal_handlers()

        # Heartbeat thread
        self._heartbeat_thread: Optional[threading.Thread] = None

        # DREAM MODE state
        self.dreams: List[DreamThought] = []
        self.last_item_time = datetime.now()  # Track when we last processed something
        self.idle_cycles = 0                  # How many cycles with no work
        self.activity_history: List[Dict] = []  # Track activity patterns
        self._load_dreams()

        # LOG ROTATION state
        self.journal_rotator = None
        self.last_cleanup_time = datetime.now()
        if self.config.log_rotation_enabled and JSONLRotator:
            self.journal_rotator = JSONLRotator(
                max_size_mb=self.config.journal_max_size_mb,
                max_rotations=self.config.journal_max_rotations
            )
            logger.info(f"[FOREVER] Log rotation enabled: max {self.config.journal_max_size_mb}MB, {self.config.journal_max_rotations} rotations")

        logger.info(f"[FOREVER] Worker '{worker_name}' initialized at {self.work_dir}")

    # =========================================================================
    # ABSTRACT METHODS - Override these in your worker
    # =========================================================================

    def check_for_items(self) -> List[Dict]:
        """
        Check for new items to process.
        Override this in your worker.

        Returns:
            List of items to process (emails, alerts, leads, etc.)
        """
        raise NotImplementedError("Override check_for_items() in your worker")

    def process_item(self, item: Dict) -> str:
        """
        Process a single item.
        Override this in your worker.

        Args:
            item: The item to process

        Returns:
            Result description string
        """
        raise NotImplementedError("Override process_item() in your worker")

    def get_item_id(self, item: Dict) -> str:
        """
        Get unique ID for an item (for deduplication).
        Override this in your worker.

        Args:
            item: The item

        Returns:
            Unique identifier string
        """
        # Default: hash the item
        return hashlib.md5(json.dumps(item, sort_keys=True, default=str).encode()).hexdigest()

    # =========================================================================
    # MAIN LOOP
    # =========================================================================

    def run_forever(self):
        """Main forever loop."""
        logger.info(f"[FOREVER] Starting forever loop for '{self.worker_name}'")
        self.state = WorkerState.RUNNING
        self._start_heartbeat_thread()

        try:
            while not self._should_stop():
                try:
                    # Check for items
                    self.state = WorkerState.PROCESSING
                    self.last_activity = "Checking for new items"
                    self._journal("check_start", {})

                    items = self.check_for_items()

                    if items:
                        # Filter out already processed
                        new_items = self._filter_processed(items)

                        if new_items:
                            logger.info(f"[FOREVER] Found {len(new_items)} new items to process")
                            self._process_items(new_items)

                            # Speed up polling when busy
                            if self.config.adaptive_polling:
                                self.current_poll_interval = max(
                                    self.config.min_poll_interval,
                                    self.current_poll_interval * 0.8
                                )
                        else:
                            logger.debug(f"[FOREVER] {len(items)} items found but all already processed")
                    else:
                        # Track idle cycles
                        self.idle_cycles += 1

                        # Slow down polling when idle
                        if self.config.adaptive_polling:
                            self.current_poll_interval = min(
                                self.config.max_poll_interval,
                                self.current_poll_interval * 1.2
                            )

                        # DREAM MODE: Enter dream state if idle long enough
                        if self._should_dream():
                            self._enter_dream_mode()

                    # Reset error counter on success
                    self.consecutive_errors = 0

                    # Track activity for pattern analysis
                    self._record_activity(len(items) if items else 0)

                    # Periodic cleanup
                    self._run_periodic_cleanup()

                    # Sleep
                    self.state = WorkerState.SLEEPING
                    self.last_activity = f"Sleeping for {self.current_poll_interval:.1f}s"
                    self._sleep_interruptible(self.current_poll_interval)

                except Exception as e:
                    self._handle_error(e)

            # Clean shutdown
            self.state = WorkerState.STOPPING
            self._journal("shutdown", {"reason": "stop_requested"})
            logger.info(f"[FOREVER] Worker '{self.worker_name}' shutting down gracefully")

        finally:
            self.state = WorkerState.STOPPED
            self._save_state()
            self._stop_heartbeat_thread()

    def _process_items(self, items: List[Dict]):
        """Process a batch of items."""
        for i, item in enumerate(items[:self.config.max_items_per_cycle]):
            if self._should_stop():
                break

            item_id = self.get_item_id(item)
            self.last_activity = f"Processing item {i+1}/{len(items)}: {item_id[:20]}"

            try:
                # Process the item
                result = self.process_item(item)

                # Mark as processed
                self._mark_processed(item_id, item, "processed", result)
                self.items_processed += 1

                self._journal("item_processed", {
                    "item_id": item_id,
                    "result": result[:200] if result else ""
                })

                logger.info(f"[FOREVER] Processed {item_id}: {result[:100] if result else 'OK'}")

            except Exception as e:
                self._mark_processed(item_id, item, "error", str(e))
                self._journal("item_error", {"item_id": item_id, "error": str(e)[:200]})
                logger.error(f"[FOREVER] Error processing {item_id}: {e}")
                self.errors_count += 1

    # =========================================================================
    # DEDUPLICATION
    # =========================================================================

    def _filter_processed(self, items: List[Dict]) -> List[Dict]:
        """Filter out already processed items."""
        new_items = []
        cutoff = datetime.now() - timedelta(hours=self.config.dedup_window_hours)

        for item in items:
            item_id = self.get_item_id(item)

            if item_id in self.processed_items:
                processed = self.processed_items[item_id]
                processed_time = datetime.fromisoformat(processed.processed_at)

                # Skip if processed within dedup window
                if processed_time > cutoff:
                    continue

            new_items.append(item)

        return new_items

    def _mark_processed(self, item_id: str, item: Dict, action: str, result: str):
        """Mark an item as processed."""
        self.processed_items[item_id] = ProcessedItem(
            item_id=item_id,
            item_hash=hashlib.md5(json.dumps(item, default=str).encode()).hexdigest()[:16],
            processed_at=datetime.now().isoformat(),
            action_taken=action,
            result=result[:500] if result else ""
        )

        # Cleanup old entries
        if len(self.processed_items) > self.config.max_processed_history:
            self._cleanup_processed_items()

        # Persist
        self._save_processed_items()

    def _cleanup_processed_items(self):
        """Remove old processed items."""
        cutoff = datetime.now() - timedelta(hours=self.config.dedup_window_hours * 2)

        to_remove = []
        for item_id, processed in self.processed_items.items():
            try:
                processed_time = datetime.fromisoformat(processed.processed_at)
                if processed_time < cutoff:
                    to_remove.append(item_id)
            except (ValueError, AttributeError) as e:
                logger.debug(f"[FOREVER] Failed to parse processed_at for {item_id}: {e}")
                pass

        for item_id in to_remove:
            del self.processed_items[item_id]

        logger.debug(f"[FOREVER] Cleaned up {len(to_remove)} old processed items")

    def _load_processed_items(self):
        """Load processed items from disk."""
        path = self.work_dir / self.config.processed_items_file
        if path.exists():
            try:
                data = json.loads(path.read_text())
                for item_id, item_data in data.items():
                    self.processed_items[item_id] = ProcessedItem(**item_data)
                logger.info(f"[FOREVER] Loaded {len(self.processed_items)} processed items")
            except Exception as e:
                logger.warning(f"[FOREVER] Failed to load processed items: {e}")

    def _save_processed_items(self):
        """Save processed items to disk."""
        path = self.work_dir / self.config.processed_items_file
        try:
            data = {k: asdict(v) for k, v in self.processed_items.items()}
            path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning(f"[FOREVER] Failed to save processed items: {e}")

    # =========================================================================
    # HEARTBEAT
    # =========================================================================

    def _start_heartbeat_thread(self):
        """Start heartbeat reporting thread."""
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def _stop_heartbeat_thread(self):
        """Stop heartbeat thread."""
        # Thread is daemon, will stop automatically
        pass

    def _heartbeat_loop(self):
        """Heartbeat reporting loop."""
        while not self._stop_requested:
            try:
                self._write_heartbeat()
            except Exception as e:
                logger.warning(f"[FOREVER] Heartbeat error: {e}")

            time.sleep(self.config.heartbeat_interval_seconds)

    def _write_heartbeat(self):
        """Write heartbeat file."""
        uptime = (datetime.now() - self.start_time).total_seconds()

        # Try to get memory usage
        memory_mb = 0.0
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
        except (ImportError, Exception) as e:
            logger.debug(f"[FOREVER] Failed to get memory usage: {e}")
            pass

        report = HeartbeatReport(
            timestamp=datetime.now().isoformat(),
            state=self.state.value,
            uptime_seconds=uptime,
            items_processed=self.items_processed,
            errors_count=self.errors_count,
            last_activity=self.last_activity,
            memory_usage_mb=memory_mb
        )

        path = self.work_dir / self.config.heartbeat_file
        path.write_text(json.dumps(asdict(report), indent=2))

    # =========================================================================
    # ACTIVITY JOURNAL
    # =========================================================================

    def _journal(self, event: str, data: Dict):
        """Write to activity journal with automatic rotation."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "worker": self.worker_name,
            **data
        }

        path = self.work_dir / self.config.journal_file
        try:
            # Rotate journal if needed
            if self.journal_rotator:
                self.journal_rotator.rotate_if_needed(path)

            # Write entry
            with open(path, 'a') as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"[FOREVER] Journal write failed: {e}")

    # =========================================================================
    # LOG ROTATION & CLEANUP
    # =========================================================================

    def _run_periodic_cleanup(self):
        """Run periodic cleanup of logs, checkpoints, and old files."""
        if not self.config.log_rotation_enabled or not periodic_cleanup:
            return

        # Check if it's time for cleanup
        hours_since_cleanup = (datetime.now() - self.last_cleanup_time).total_seconds() / 3600
        if hours_since_cleanup < self.config.cleanup_interval_hours:
            return

        try:
            logger.info("[FOREVER] Running periodic cleanup...")

            # Cleanup old checkpoints and rotated logs
            stats = periodic_cleanup(
                work_dir=self.work_dir,
                checkpoint_dir=CHECKPOINT_DIR,
                checkpoint_age_days=self.config.checkpoint_max_age_days,
                rotated_logs_age_days=self.config.rotated_logs_max_age_days
            )

            # Trim in-memory lists
            self._trim_in_memory_data()

            # Rotate dreams and processed_items files if they're too large
            self._rotate_supplemental_files()

            self.last_cleanup_time = datetime.now()
            self._journal("periodic_cleanup", stats)

        except Exception as e:
            logger.warning(f"[FOREVER] Periodic cleanup failed: {e}")

    def _trim_in_memory_data(self):
        """Trim in-memory data structures to prevent unbounded growth."""
        if not self.journal_rotator:
            return

        # Trim activity history
        if len(self.activity_history) > 1000:
            self.activity_history = self.journal_rotator.trim_in_memory_list(
                self.activity_history,
                max_size=500,
                keep_recent=True
            )

        # Trim dreams
        if len(self.dreams) > self.config.max_dreams:
            self.dreams = self.journal_rotator.trim_in_memory_list(
                self.dreams,
                max_size=self.config.max_dreams,
                keep_recent=True
            )

        # Trim processed items
        if len(self.processed_items) > self.config.max_processed_history:
            self._cleanup_processed_items()

    def _rotate_supplemental_files(self):
        """Rotate dreams and processed_items files if they're too large."""
        if not self.journal_rotator:
            return

        # Rotate dreams file
        dreams_path = self.work_dir / self.config.dreams_file
        if dreams_path.exists():
            self.journal_rotator.rotate_if_needed(dreams_path)

        # Rotate processed items file
        processed_path = self.work_dir / self.config.processed_items_file
        if processed_path.exists():
            self.journal_rotator.rotate_if_needed(processed_path)

    # =========================================================================
    # ERROR HANDLING
    # =========================================================================

    def _handle_error(self, error: Exception):
        """Handle errors in the main loop."""
        self.errors_count += 1
        self.consecutive_errors += 1
        self.state = WorkerState.ERROR

        logger.error(f"[FOREVER] Error in main loop: {error}")
        self._journal("error", {"error": str(error)[:500]})

        if self.consecutive_errors >= self.config.max_consecutive_errors:
            if self.config.auto_recover:
                logger.warning(f"[FOREVER] Too many errors ({self.consecutive_errors}), backing off...")
                self._sleep_interruptible(self.config.error_backoff_seconds)
                self.consecutive_errors = 0  # Reset and try again
            else:
                logger.error(f"[FOREVER] Too many errors, stopping")
                self._stop_requested = True

    # =========================================================================
    # STOP SIGNAL
    # =========================================================================

    def _should_stop(self) -> bool:
        """Check if we should stop."""
        if self._stop_requested:
            return True

        # Check stop signal file
        stop_file = self.work_dir / self.config.stop_signal_file
        if stop_file.exists():
            logger.info(f"[FOREVER] Stop signal file detected: {stop_file}")
            stop_file.unlink()  # Remove the file
            return True

        # Check max runtime
        if self.config.max_runtime_hours > 0:
            uptime_hours = (datetime.now() - self.start_time).total_seconds() / 3600
            if uptime_hours >= self.config.max_runtime_hours:
                logger.info(f"[FOREVER] Max runtime reached: {uptime_hours:.1f}h")
                return True

        return False

    def _setup_signal_handlers(self):
        """Setup graceful shutdown on signals."""
        def handle_signal(signum, frame):
            logger.info(f"[FOREVER] Received signal {signum}, requesting stop")
            self._stop_requested = True

        try:
            signal.signal(signal.SIGTERM, handle_signal)
            signal.signal(signal.SIGINT, handle_signal)
        except (ValueError, OSError) as e:
            logger.debug(f"[FOREVER] Failed to setup signal handlers: {e}")
            pass  # May fail on some platforms

    def request_stop(self):
        """Request graceful stop."""
        self._stop_requested = True

    # =========================================================================
    # STATE PERSISTENCE
    # =========================================================================

    def _save_state(self):
        """Save worker state."""
        state = {
            "worker_name": self.worker_name,
            "state": self.state.value,
            "start_time": self.start_time.isoformat(),
            "items_processed": self.items_processed,
            "errors_count": self.errors_count,
            "last_activity": self.last_activity,
            "saved_at": datetime.now().isoformat()
        }

        path = self.work_dir / self.config.state_file
        path.write_text(json.dumps(state, indent=2))

    def _load_state(self) -> Optional[Dict]:
        """Load worker state."""
        path = self.work_dir / self.config.state_file
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, IOError, OSError) as e:
                logger.warning(f"[FOREVER] Failed to load state: {e}")
                pass
        return None

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _sleep_interruptible(self, seconds: float):
        """Sleep that can be interrupted by stop signal."""
        end_time = time.time() + seconds
        while time.time() < end_time:
            if self._should_stop():
                break
            time.sleep(min(1.0, end_time - time.time()))

    def get_status(self) -> Dict:
        """Get current worker status."""
        uptime = (datetime.now() - self.start_time).total_seconds()
        status = {
            "worker_name": self.worker_name,
            "state": self.state.value,
            "uptime_seconds": uptime,
            "uptime_human": str(timedelta(seconds=int(uptime))),
            "items_processed": self.items_processed,
            "errors_count": self.errors_count,
            "consecutive_errors": self.consecutive_errors,
            "last_activity": self.last_activity,
            "poll_interval": self.current_poll_interval,
            "processed_items_tracked": len(self.processed_items),
            "dreams_count": len(self.dreams),
            "activity_history_size": len(self.activity_history)
        }

        # Add log rotation stats if enabled
        if self.journal_rotator:
            journal_path = self.work_dir / self.config.journal_file
            hours_since_cleanup = (datetime.now() - self.last_cleanup_time).total_seconds() / 3600
            status["log_rotation"] = {
                "enabled": True,
                "journal_total_size_mb": self.journal_rotator.get_total_size_mb(journal_path),
                "hours_since_cleanup": round(hours_since_cleanup, 1),
                "next_cleanup_in_hours": round(max(0, self.config.cleanup_interval_hours - hours_since_cleanup), 1)
            }

        return status


# =============================================================================
# EXAMPLE WORKERS
# =============================================================================

class EmailInboxMonitor(ForeverWorker):
    """
    Example: Monitor email inbox and respond to new emails.

    Usage:
        monitor = EmailInboxMonitor(
            check_inbox_fn=my_check_inbox,
            respond_fn=my_respond_to_email
        )
        monitor.run_forever()
    """

    def __init__(
        self,
        check_inbox_fn: Callable[[], List[Dict]],
        respond_fn: Callable[[Dict], str],
        **kwargs
    ):
        super().__init__(worker_name="email_monitor", **kwargs)
        self._check_inbox = check_inbox_fn
        self._respond = respond_fn

    def check_for_items(self) -> List[Dict]:
        return self._check_inbox()

    def process_item(self, item: Dict) -> str:
        return self._respond(item)

    def get_item_id(self, item: Dict) -> str:
        return item.get('email_id') or item.get('message_id') or super().get_item_id(item)


class TelemetryWatcher(ForeverWorker):
    """
    Example: Watch telemetry/metrics and respond to alerts.

    Usage:
        watcher = TelemetryWatcher(
            check_alerts_fn=my_check_alerts,
            handle_alert_fn=my_handle_alert
        )
        watcher.run_forever()
    """

    def __init__(
        self,
        check_alerts_fn: Callable[[], List[Dict]],
        handle_alert_fn: Callable[[Dict], str],
        **kwargs
    ):
        super().__init__(worker_name="telemetry_watcher", **kwargs)
        self._check_alerts = check_alerts_fn
        self._handle_alert = handle_alert_fn

    def check_for_items(self) -> List[Dict]:
        return self._check_alerts()

    def process_item(self, item: Dict) -> str:
        return self._handle_alert(item)

    def get_item_id(self, item: Dict) -> str:
        return item.get('alert_id') or item.get('metric_key') or super().get_item_id(item)


class LeadScraper(ForeverWorker):
    """
    Example: Continuously scrape leads from sources.

    Usage:
        scraper = LeadScraper(
            find_leads_fn=my_find_leads,
            process_lead_fn=my_process_lead
        )
        scraper.run_forever()
    """

    def __init__(
        self,
        find_leads_fn: Callable[[], List[Dict]],
        process_lead_fn: Callable[[Dict], str],
        **kwargs
    ):
        super().__init__(worker_name="lead_scraper", **kwargs)
        self._find_leads = find_leads_fn
        self._process_lead = process_lead_fn

    def check_for_items(self) -> List[Dict]:
        return self._find_leads()

    def process_item(self, item: Dict) -> str:
        return self._process_lead(item)

    def get_item_id(self, item: Dict) -> str:
        # Dedupe by website + name combo
        return f"{item.get('website', '')}:{item.get('name', '')}"


# =============================================================================
# INTEGRATION WITH BRAIN
# =============================================================================

def create_forever_task_prompt(task_type: str, task_config: Dict) -> str:
    """
    Generate a prompt that tells the agent to run forever.

    Args:
        task_type: Type of forever task (email_monitor, telemetry_watcher, etc.)
        task_config: Configuration for the task

    Returns:
        Prompt string for the agent
    """
    base_prompt = f"""You are running as a FOREVER WORKER in '{task_type}' mode.

CRITICAL INSTRUCTIONS:
1. This is a FOREVER operation - do NOT stop until explicitly told to
2. Run in a continuous loop: CHECK -> PROCESS -> SLEEP -> REPEAT
3. Never say "task complete" - the task is NEVER complete
4. Save all results incrementally - don't wait to batch
5. Track what you've already processed to avoid duplicates
6. Report progress every 10 items processed
7. If you encounter errors, log them and continue - don't stop

TASK CONFIGURATION:
{json.dumps(task_config, indent=2)}

LOOP STRUCTURE:
1. Check for new items (emails, alerts, leads, etc.)
2. For each NEW item (not already processed):
   - Process it according to task rules
   - Save result to output file
   - Mark as processed
3. Sleep for configured interval
4. Go back to step 1

NEVER STOPPING RULES:
- If no new items: sleep longer, then check again
- If error occurs: log error, skip item, continue
- If rate limited: back off, wait, retry
- If browser crashes: recover browser, continue

BEGIN FOREVER OPERATION NOW. Check for items and start processing.
"""
    return base_prompt


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def run_forever_worker(
    worker_type: str,
    check_fn: Callable,
    process_fn: Callable,
    config: ForeverConfig = None,
    worker_name: str = None
):
    """
    Convenience function to run a forever worker.

    Args:
        worker_type: "email", "telemetry", "lead", or "custom"
        check_fn: Function to check for new items
        process_fn: Function to process an item
        config: Optional ForeverConfig
        worker_name: Optional worker name
    """
    config = config or ForeverConfig()
    worker_name = worker_name or f"{worker_type}_worker"

    if worker_type == "email":
        worker = EmailInboxMonitor(check_fn, process_fn, config=config, worker_name=worker_name)
    elif worker_type == "telemetry":
        worker = TelemetryWatcher(check_fn, process_fn, config=config, worker_name=worker_name)
    elif worker_type == "lead":
        worker = LeadScraper(check_fn, process_fn, config=config, worker_name=worker_name)
    else:
        # Custom worker
        class CustomWorker(ForeverWorker):
            def check_for_items(self): return check_fn()
            def process_item(self, item): return process_fn(item)

        worker = CustomWorker(config=config, worker_name=worker_name)

    worker.run_forever()


# =============================================================================
# DREAM MODE METHODS - Add to ForeverWorker class
# =============================================================================

# Monkey-patch dream mode methods into ForeverWorker
def _should_dream(self) -> bool:
    """Check if we should enter dream mode (idle long enough)."""
    if not self.config.dream_mode_enabled:
        return False

    # Don't dream if we're not in a dreamable state
    if self.state not in [WorkerState.SLEEPING, WorkerState.RUNNING]:
        return False

    # Check if idle long enough
    idle_minutes = (datetime.now() - self.last_item_time).total_seconds() / 60
    return idle_minutes >= self.config.idle_threshold_minutes


def _enter_dream_mode(self):
    """Enter dream mode - self-improvement during idle time."""
    previous_state = self.state
    self.state = WorkerState.DREAMING
    self.last_activity = "Entering dream mode - self-improvement"

    logger.info(f"[FOREVER] Entering dream mode after {self.idle_cycles} idle cycles")
    self._journal("dream_start", {"idle_cycles": self.idle_cycles})

    dream_start = time.time()
    thoughts_generated = 0

    try:
        # Analyze past errors for patterns
        if self.config.dream_analyze_errors and self.errors_count > 0:
            thought = self._dream_analyze_errors()
            if thought:
                self.dreams.append(thought)
                thoughts_generated += 1

        # Think about optimizing strategy
        if self.config.dream_optimize_strategy:
            thought = self._dream_optimize_strategy()
            if thought:
                self.dreams.append(thought)
                thoughts_generated += 1

        # Predict busy/quiet patterns
        if self.config.dream_predict_patterns and len(self.activity_history) >= 10:
            thought = self._dream_predict_patterns()
            if thought:
                self.dreams.append(thought)
                thoughts_generated += 1

        # Generate self-improvement ideas
        if self.config.dream_self_improve:
            thought = self._dream_self_improve()
            if thought:
                self.dreams.append(thought)
                thoughts_generated += 1

        # Trim dreams if too many
        if len(self.dreams) > self.config.max_dreams:
            # Keep most important dreams (highest priority first)
            self.dreams.sort(key=lambda d: -d.priority)
            self.dreams = self.dreams[:self.config.max_dreams]

        # Persist dreams
        self._save_dreams()

        dream_duration = time.time() - dream_start
        logger.info(f"[FOREVER] Dream mode complete: {thoughts_generated} thoughts in {dream_duration:.1f}s")
        self._journal("dream_end", {
            "thoughts_generated": thoughts_generated,
            "duration_seconds": dream_duration
        })

    except Exception as e:
        logger.warning(f"[FOREVER] Dream mode error: {e}")
        self._journal("dream_error", {"error": str(e)[:200]})

    finally:
        self.state = previous_state


def _dream_analyze_errors(self) -> Optional[DreamThought]:
    """Analyze past errors for patterns and generate insights."""
    # Read recent journal entries for errors
    journal_path = self.work_dir / self.config.journal_file
    if not journal_path.exists():
        return None

    error_entries = []
    try:
        with open(journal_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get('event') in ['error', 'item_error']:
                        error_entries.append(entry)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.debug(f"[FOREVER] Failed to parse journal line: {e}")
                    continue
    except (IOError, OSError) as e:
        logger.warning(f"[FOREVER] Failed to read journal file: {e}")
        return None

    if not error_entries:
        return None

    # Analyze error patterns
    error_messages = [e.get('error', '')[:100] for e in error_entries[-20:]]  # Last 20 errors

    # Simple pattern detection: find common words
    word_freq = {}
    for msg in error_messages:
        for word in msg.lower().split():
            if len(word) > 3:  # Skip short words
                word_freq[word] = word_freq.get(word, 0) + 1

    # Find most common error-related words
    common_words = sorted(word_freq.items(), key=lambda x: -x[1])[:5]

    if not common_words:
        return None

    insight = f"Error pattern detected: Most common terms in last {len(error_entries)} errors: "
    insight += ", ".join([f"'{w}' ({c}x)" for w, c in common_words])
    insight += ". Consider adding specific handling for these cases."

    return DreamThought(
        timestamp=datetime.now().isoformat(),
        category="pattern",
        insight=insight,
        priority=4 if self.errors_count > 10 else 2
    )


def _dream_optimize_strategy(self) -> Optional[DreamThought]:
    """Think about optimizing the worker strategy."""
    insights = []

    # Check poll interval efficiency
    if self.idle_cycles > 20:
        if self.current_poll_interval < self.config.max_poll_interval:
            insights.append(
                f"High idle rate ({self.idle_cycles} cycles). "
                f"Consider increasing max_poll_interval above {self.config.max_poll_interval}s."
            )

    # Check error rate
    if self.items_processed > 0:
        error_rate = self.errors_count / self.items_processed
        if error_rate > 0.1:  # More than 10% errors
            insights.append(
                f"High error rate ({error_rate:.1%}). "
                f"Review item processing logic for common failure cases."
            )

    # Check processing efficiency
    uptime_hours = (datetime.now() - self.start_time).total_seconds() / 3600
    if uptime_hours > 1 and self.items_processed > 0:
        items_per_hour = self.items_processed / uptime_hours
        if items_per_hour < 1:
            insights.append(
                f"Low throughput ({items_per_hour:.1f} items/hour). "
                f"Consider reducing poll_interval or checking data source availability."
            )

    if not insights:
        return None

    return DreamThought(
        timestamp=datetime.now().isoformat(),
        category="optimization",
        insight=" | ".join(insights),
        priority=3
    )


def _dream_predict_patterns(self) -> Optional[DreamThought]:
    """Predict busy/quiet periods from activity history."""
    if len(self.activity_history) < 10:
        return None

    # Group activity by hour of day
    hourly_activity = {}
    for activity in self.activity_history[-100:]:  # Last 100 entries
        try:
            ts = datetime.fromisoformat(activity['timestamp'])
            hour = ts.hour
            count = activity.get('item_count', 0)
            if hour not in hourly_activity:
                hourly_activity[hour] = []
            hourly_activity[hour].append(count)
        except (ValueError, KeyError, AttributeError) as e:
            logger.debug(f"[FOREVER] Failed to parse activity timestamp: {e}")
            continue

    if not hourly_activity:
        return None

    # Calculate average activity per hour
    avg_by_hour = {h: sum(counts) / len(counts) for h, counts in hourly_activity.items()}

    # Find busiest and quietest hours
    if avg_by_hour:
        busiest = max(avg_by_hour.items(), key=lambda x: x[1])
        quietest = min(avg_by_hour.items(), key=lambda x: x[1])

        insight = (
            f"Activity pattern detected: Busiest hour is {busiest[0]:02d}:00 "
            f"(avg {busiest[1]:.1f} items), quietest is {quietest[0]:02d}:00 "
            f"(avg {quietest[1]:.1f} items). "
            f"Consider scheduling maintenance during quiet periods."
        )

        return DreamThought(
            timestamp=datetime.now().isoformat(),
            category="pattern",
            insight=insight,
            priority=2
        )

    return None


def _dream_self_improve(self) -> Optional[DreamThought]:
    """Generate self-improvement ideas."""
    ideas = []

    # Check if we should suggest batch processing
    if self.items_processed > 100 and self.config.max_items_per_cycle < 50:
        ideas.append(
            "Consider increasing max_items_per_cycle for better efficiency during busy periods."
        )

    # Check if dedup window could be adjusted
    processed_count = len(self.processed_items)
    if processed_count > self.config.max_processed_history * 0.8:
        ideas.append(
            f"Processed items cache is {processed_count}/{self.config.max_processed_history} full. "
            f"May need to increase max_processed_history or reduce dedup_window_hours."
        )

    # Suggest heartbeat interval adjustment
    uptime_hours = (datetime.now() - self.start_time).total_seconds() / 3600
    if uptime_hours > 24 and self.config.heartbeat_interval_seconds < 300:
        ideas.append(
            "Running for 24+ hours stably. Consider increasing heartbeat_interval for less overhead."
        )

    # Check memory growth (if we tracked it)
    if not ideas:
        # Generic improvement idea based on runtime
        if uptime_hours > 12:
            ideas.append(
                f"Running smoothly for {uptime_hours:.1f} hours. "
                f"System is stable - consider extending max_runtime_hours if currently limited."
            )

    if not ideas:
        return None

    return DreamThought(
        timestamp=datetime.now().isoformat(),
        category="improvement",
        insight=" | ".join(ideas),
        priority=2
    )


def _record_activity(self, item_count: int):
    """Record activity for pattern analysis."""
    self.activity_history.append({
        "timestamp": datetime.now().isoformat(),
        "item_count": item_count,
        "poll_interval": self.current_poll_interval,
        "state": self.state.value
    })

    # Keep only recent history
    if len(self.activity_history) > 1000:
        self.activity_history = self.activity_history[-500:]

    # Update last item time if we processed something
    if item_count > 0:
        self.last_item_time = datetime.now()
        self.idle_cycles = 0


def _load_dreams(self):
    """Load dreams from disk."""
    path = self.work_dir / self.config.dreams_file
    if path.exists():
        try:
            data = json.loads(path.read_text())
            self.dreams = [DreamThought(**d) for d in data]
            logger.info(f"[FOREVER] Loaded {len(self.dreams)} dreams")
        except Exception as e:
            logger.warning(f"[FOREVER] Failed to load dreams: {e}")
            self.dreams = []


def _save_dreams(self):
    """Save dreams to disk."""
    path = self.work_dir / self.config.dreams_file
    try:
        data = [asdict(d) for d in self.dreams]
        path.write_text(json.dumps(data, indent=2))
    except Exception as e:
        logger.warning(f"[FOREVER] Failed to save dreams: {e}")


def get_dreams_summary(self) -> Dict:
    """Get a summary of all dreams/insights."""
    if not self.dreams:
        return {"total": 0, "by_category": {}, "top_insights": []}

    by_category = {}
    for dream in self.dreams:
        cat = dream.category
        by_category[cat] = by_category.get(cat, 0) + 1

    # Get top 5 highest priority insights
    top_insights = sorted(self.dreams, key=lambda d: -d.priority)[:5]

    return {
        "total": len(self.dreams),
        "by_category": by_category,
        "top_insights": [
            {"category": d.category, "insight": d.insight, "priority": d.priority}
            for d in top_insights
        ],
        "unacted": len([d for d in self.dreams if not d.acted_upon])
    }


# Attach dream methods to ForeverWorker class
ForeverWorker._should_dream = _should_dream
ForeverWorker._enter_dream_mode = _enter_dream_mode
ForeverWorker._dream_analyze_errors = _dream_analyze_errors
ForeverWorker._dream_optimize_strategy = _dream_optimize_strategy
ForeverWorker._dream_predict_patterns = _dream_predict_patterns
ForeverWorker._dream_self_improve = _dream_self_improve
ForeverWorker._record_activity = _record_activity
ForeverWorker._load_dreams = _load_dreams
ForeverWorker._save_dreams = _save_dreams
ForeverWorker.get_dreams_summary = get_dreams_summary
