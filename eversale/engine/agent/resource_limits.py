"""
Resource Limits - Prevent runaway tasks from consuming all system resources.

Monitors and enforces:
- Memory usage limits
- Task duration limits
- CPU throttling (via sleep)
- Concurrent task limits

Usage:
    limiter = ResourceLimiter(max_memory_mb=2048, max_task_minutes=60)

    with limiter.task_context("my_task"):
        # Task runs here
        # Auto-killed if exceeds limits
"""

import asyncio
import os
import signal
import threading
import time
from contextlib import contextmanager, asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import json
import shutil
import urllib.request

from loguru import logger

# Optional psutil import - graceful fallback if not installed
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not installed - resource monitoring will be limited. Install with: pip install psutil")


@dataclass
class ResourceConfig:
    """Resource limit configuration."""
    max_memory_mb: int = 2048          # Max memory per task
    max_task_minutes: float = 120       # Max duration per task (2 hours)
    max_total_memory_mb: int = 4096     # Max total memory for all tasks
    max_concurrent_tasks: int = 3       # Max parallel tasks
    cpu_throttle_percent: int = 80      # Start throttling at this CPU %
    check_interval_seconds: float = 5.0 # How often to check limits
    kill_on_exceed: bool = True         # Kill task if exceeds limits
    warn_threshold_percent: float = 0.8 # Warn at 80% of limit
    min_disk_space_gb: float = 1.0      # Minimum disk space (GB)
    memory_critical_percent: float = 95  # Critical memory threshold
    memory_warning_percent: float = 85   # Warning memory threshold
    network_check_url: str = "https://www.google.com"  # URL for network checks
    network_timeout: int = 5             # Network check timeout (seconds)


class ResourceLimiter:
    def __init__(self, config: Optional[ResourceConfig] = None, config_path: Path = Path("config/resources.yaml")):
        self.config = config or self._load_config(config_path)
        self._active_tasks: Dict[str, dict] = {}
        self._task_pids: Dict[str, int] = {}  # Track PIDs per task
        self._subprocess_pids: Dict[str, List[int]] = {}  # Track child processes
        self._lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._violations_log = Path("logs/resource_violations.log")
        self._last_disk_check = 0
        self._last_network_stats = {}

    def _load_config(self, config_path: Path) -> ResourceConfig:
        """Load config from YAML or use defaults."""
        if config_path.exists():
            try:
                import yaml
                data = yaml.safe_load(config_path.read_text())
                return ResourceConfig(**data)
            except Exception as e:
                logger.warning(f"Failed to load resource config: {e}, using defaults")
        return ResourceConfig()

    def start_monitoring(self):
        """Start background resource monitoring."""
        if self._running:
            return

        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info(f"Resource limiter started (max_mem: {self.config.max_memory_mb}MB, max_time: {self.config.max_task_minutes}min)")

    def stop_monitoring(self):
        """Stop monitoring."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)

    def _monitor_loop(self):
        """Background monitoring loop."""
        while self._running:
            try:
                self._check_limits()

                # Periodic disk space check (every 60 seconds)
                now = time.time()
                if now - self._last_disk_check > 60:
                    disk_ok, free_gb = self.check_disk_space()
                    if not disk_ok:
                        logger.error(f"Low disk space: {free_gb:.2f}GB free")
                        self._emergency_cleanup()
                    self._last_disk_check = now

                time.sleep(self.config.check_interval_seconds)
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")

    def _check_limits(self):
        """Check all active tasks against limits."""
        total_memory_mb = 0
        cpu_percent = 0

        if PSUTIL_AVAILABLE:
            try:
                process = psutil.Process(os.getpid())

                # Check system memory and trigger preemptive actions
                self._check_memory_preemptive()

                # Check total memory
                total_memory_mb = process.memory_info().rss / (1024 * 1024)
                if total_memory_mb > self.config.max_total_memory_mb:
                    self._log_violation("TOTAL_MEMORY", f"Total memory {total_memory_mb:.0f}MB exceeds {self.config.max_total_memory_mb}MB")

                # Check CPU and throttle if needed
                cpu_percent = process.cpu_percent(interval=0.1)
                if cpu_percent > self.config.cpu_throttle_percent:
                    # Throttle by introducing small delays
                    time.sleep(0.1)
            except Exception as e:
                logger.debug(f"Resource check error: {e}")

        # Check each active task (duration limits work without psutil)
        with self._lock:
            now = time.time()
            for task_id, task_info in list(self._active_tasks.items()):
                # Check duration
                duration_minutes = (now - task_info["start_time"]) / 60
                if duration_minutes > self.config.max_task_minutes:
                    self._handle_violation(task_id, "DURATION",
                        f"Task {task_id} exceeded {self.config.max_task_minutes}min (ran {duration_minutes:.1f}min)")

                # Check memory (approximate per-task) - only if psutil available
                if PSUTIL_AVAILABLE and total_memory_mb > 0:
                    task_memory_mb = total_memory_mb / max(1, len(self._active_tasks))
                    if task_memory_mb > self.config.max_memory_mb:
                        warn_threshold = self.config.max_memory_mb * self.config.warn_threshold_percent
                        if task_memory_mb > warn_threshold:
                            logger.warning(f"Task {task_id} memory high: {task_memory_mb:.0f}MB")

    def _handle_violation(self, task_id: str, violation_type: str, message: str):
        """Handle a resource limit violation."""
        self._log_violation(violation_type, message)

        if self.config.kill_on_exceed:
            logger.error(f"KILLING task due to resource violation: {message}")
            with self._lock:
                if task_id in self._active_tasks:
                    self._active_tasks[task_id]["killed"] = True
                    self._active_tasks[task_id]["kill_reason"] = message

    def _log_violation(self, violation_type: str, message: str):
        """Log resource violation."""
        logger.error(f"RESOURCE VIOLATION [{violation_type}]: {message}")

        self._violations_log.parent.mkdir(parents=True, exist_ok=True)
        with open(self._violations_log, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] [{violation_type}] {message}\n")

    def register_task_pid(self, task_id: str, pid: int):
        """Register the PID for a task."""
        with self._lock:
            self._task_pids[task_id] = pid
            if task_id not in self._subprocess_pids:
                self._subprocess_pids[task_id] = []
        logger.debug(f"Registered PID {pid} for task {task_id}")

    def register_subprocess(self, task_id: str, pid: int):
        """Register a subprocess (like Chrome) for a task."""
        with self._lock:
            if task_id in self._subprocess_pids:
                self._subprocess_pids[task_id].append(pid)
        logger.debug(f"Registered subprocess PID {pid} for task {task_id}")

    def kill_task(self, task_id: str, reason: str = "Resource limit exceeded"):
        """Actually kill a task and all its subprocesses."""
        logger.warning(f"Killing task {task_id}: {reason}")

        if not PSUTIL_AVAILABLE:
            logger.error("Cannot kill task - psutil not available")
            return

        # Kill subprocesses first (e.g., Chrome)
        with self._lock:
            subprocess_pids = self._subprocess_pids.get(task_id, []).copy()

        for pid in subprocess_pids:
            try:
                proc = psutil.Process(pid)
                # Kill all children recursively
                for child in proc.children(recursive=True):
                    try:
                        child.kill()
                        logger.debug(f"Killed child process {child.pid}")
                    except psutil.NoSuchProcess:
                        pass
                    except Exception as e:
                        logger.debug(f"Error killing child {child.pid}: {e}")
                proc.kill()
                logger.info(f"Killed subprocess {pid}")
            except psutil.NoSuchProcess:
                pass
            except Exception as e:
                logger.error(f"Error killing subprocess {pid}: {e}")

        # Kill main task process
        with self._lock:
            main_pid = self._task_pids.get(task_id)

        if main_pid:
            try:
                os.kill(main_pid, signal.SIGKILL)
                logger.info(f"Killed main process {main_pid}")
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.error(f"Error killing main process {main_pid}: {e}")

        # Clean up tracking
        with self._lock:
            self._task_pids.pop(task_id, None)
            self._subprocess_pids.pop(task_id, None)
            if task_id in self._active_tasks:
                self._active_tasks[task_id]["killed"] = True
                self._active_tasks[task_id]["kill_reason"] = reason

    def _check_memory_preemptive(self) -> bool:
        """Check if memory is getting dangerously high and take preemptive action."""
        if not PSUTIL_AVAILABLE:
            return False

        try:
            mem = psutil.virtual_memory()

            # If above warning threshold, start garbage collection
            if mem.percent > self.config.memory_warning_percent:
                logger.warning(f"Memory at {mem.percent:.1f}%, triggering garbage collection")
                import gc
                gc.collect()

            # If above critical threshold, start killing tasks
            if mem.percent > self.config.memory_critical_percent:
                logger.error(f"Memory CRITICAL at {mem.percent:.1f}%, killing oldest task")
                with self._lock:
                    if self._active_tasks:
                        # Find oldest task
                        oldest_task = min(
                            self._active_tasks.items(),
                            key=lambda x: x[1].get("start_time", float('inf'))
                        )
                        if oldest_task:
                            task_id = oldest_task[0]
                            logger.error(f"Killing oldest task {task_id} due to critical memory")
                            # Mark for killing (actual kill happens outside lock)
                            self._active_tasks[task_id]["killed"] = True
                            self._active_tasks[task_id]["kill_reason"] = f"Critical memory: {mem.percent:.1f}%"

                        # Actually kill the task
                        if oldest_task:
                            self.kill_task(oldest_task[0], f"Critical memory: {mem.percent:.1f}%")
                return True

            return mem.percent > self.config.memory_warning_percent

        except Exception as e:
            logger.error(f"Memory preemptive check error: {e}")
            return False

    def check_disk_space(self) -> Tuple[bool, float]:
        """Check if disk space is sufficient."""
        try:
            usage = shutil.disk_usage("/")
            free_gb = usage.free / (1024 ** 3)
            return free_gb >= self.config.min_disk_space_gb, free_gb
        except Exception as e:
            logger.error(f"Error checking disk space: {e}")
            return True, 0  # Assume OK if can't check

    def _emergency_cleanup(self):
        """Emergency cleanup when disk is low."""
        logger.warning("Running emergency cleanup due to low disk space")

        # Clear cache files
        cache_dir = Path("cache")
        if cache_dir.exists():
            count = 0
            for f in cache_dir.glob("*"):
                try:
                    if f.is_file():
                        f.unlink()
                        count += 1
                except Exception as e:
                    logger.debug(f"Error deleting cache file {f}: {e}")
            logger.info(f"Cleared {count} cache files")

        # Clear old logs (keep only 3 most recent)
        log_dir = Path("logs")
        if log_dir.exists():
            log_files = sorted(
                [f for f in log_dir.glob("*.log*") if f.is_file()],
                key=lambda x: x.stat().st_mtime
            )
            # Keep only 3 most recent, delete the rest
            for f in log_files[:-3]:
                try:
                    f.unlink()
                    logger.debug(f"Deleted old log: {f}")
                except Exception as e:
                    logger.debug(f"Error deleting log {f}: {e}")

        # Clear temp files
        temp_dir = Path("temp")
        if temp_dir.exists():
            count = 0
            for f in temp_dir.glob("*"):
                try:
                    if f.is_file():
                        f.unlink()
                        count += 1
                except Exception as e:
                    logger.debug(f"Error deleting temp file {f}: {e}")
            logger.info(f"Cleared {count} temp files")

        logger.info("Emergency cleanup completed")

    def check_network(self) -> bool:
        """Check if network is available."""
        try:
            urllib.request.urlopen(self.config.network_check_url, timeout=self.config.network_timeout)
            return True
        except Exception as e:
            logger.debug(f"Network check failed: {e}")
            return False

    def get_network_stats(self) -> dict:
        """Get network usage statistics."""
        if not PSUTIL_AVAILABLE:
            return {}

        try:
            net_io = psutil.net_io_counters()
            stats = {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
            }

            # Calculate delta if we have previous stats
            if self._last_network_stats:
                stats["bytes_sent_delta"] = stats["bytes_sent"] - self._last_network_stats.get("bytes_sent", 0)
                stats["bytes_recv_delta"] = stats["bytes_recv"] - self._last_network_stats.get("bytes_recv", 0)

            self._last_network_stats = stats
            return stats
        except Exception as e:
            logger.debug(f"Error getting network stats: {e}")
            return {}

    def can_start_task(self) -> tuple[bool, str]:
        """Check if a new task can start."""
        with self._lock:
            if len(self._active_tasks) >= self.config.max_concurrent_tasks:
                return False, f"Max concurrent tasks ({self.config.max_concurrent_tasks}) reached"

        # Check total memory (only if psutil available)
        if PSUTIL_AVAILABLE:
            try:
                process = psutil.Process(os.getpid())
                total_memory_mb = process.memory_info().rss / (1024 * 1024)
                if total_memory_mb > self.config.max_total_memory_mb * 0.9:
                    return False, f"Memory too high ({total_memory_mb:.0f}MB)"
            except Exception:
                pass  # Allow task if we can't check memory

        return True, "OK"

    def register_task(self, task_id: str) -> bool:
        """Register a new task. Returns False if limits prevent it."""
        can_start, reason = self.can_start_task()
        if not can_start:
            logger.warning(f"Cannot start task {task_id}: {reason}")
            return False

        with self._lock:
            self._active_tasks[task_id] = {
                "start_time": time.time(),
                "killed": False,
                "kill_reason": None,
            }
        return True

    def unregister_task(self, task_id: str):
        """Unregister a completed task."""
        with self._lock:
            self._active_tasks.pop(task_id, None)

    def is_task_killed(self, task_id: str) -> tuple[bool, Optional[str]]:
        """Check if a task has been marked for killing."""
        with self._lock:
            task = self._active_tasks.get(task_id, {})
            return task.get("killed", False), task.get("kill_reason")

    @contextmanager
    def task_context(self, task_id: str):
        """Context manager for running a task with resource limits."""
        if not self.register_task(task_id):
            raise ResourceLimitError(f"Cannot start task: resource limits exceeded")

        try:
            yield ResourceTaskHandle(self, task_id)
        finally:
            self.unregister_task(task_id)

    @asynccontextmanager
    async def async_task_context(self, task_id: str):
        """Async context manager for running a task with resource limits."""
        if not self.register_task(task_id):
            raise ResourceLimitError(f"Cannot start task: resource limits exceeded")

        try:
            yield ResourceTaskHandle(self, task_id)
        finally:
            self.unregister_task(task_id)

    def status(self) -> dict:
        """Get current resource status."""
        memory_mb = 0
        cpu_percent = 0
        system_memory_percent = 0
        disk_free_gb = 0
        network_available = False

        if PSUTIL_AVAILABLE:
            try:
                process = psutil.Process(os.getpid())
                memory_mb = process.memory_info().rss / (1024 * 1024)
                cpu_percent = process.cpu_percent(interval=0.1)

                # System memory
                mem = psutil.virtual_memory()
                system_memory_percent = mem.percent

            except Exception:
                pass

        # Check disk space
        disk_ok, disk_free_gb = self.check_disk_space()

        # Check network (cached to avoid blocking)
        network_available = self.check_network()

        with self._lock:
            active_count = len(self._active_tasks)
            tracked_pids = len(self._task_pids)
            tracked_subprocesses = sum(len(pids) for pids in self._subprocess_pids.values())

        return {
            "memory_mb": round(memory_mb, 1),
            "memory_limit_mb": self.config.max_total_memory_mb,
            "memory_percent": round(memory_mb / self.config.max_total_memory_mb * 100, 1) if memory_mb > 0 else 0,
            "system_memory_percent": round(system_memory_percent, 1),
            "cpu_percent": round(cpu_percent, 1),
            "disk_free_gb": round(disk_free_gb, 2),
            "disk_ok": disk_ok,
            "network_available": network_available,
            "active_tasks": active_count,
            "tracked_pids": tracked_pids,
            "tracked_subprocesses": tracked_subprocesses,
            "max_concurrent_tasks": self.config.max_concurrent_tasks,
            "monitoring": self._running,
            "psutil_available": PSUTIL_AVAILABLE,
        }


class ResourceTaskHandle:
    """Handle for checking task status during execution."""
    def __init__(self, limiter: ResourceLimiter, task_id: str):
        self.limiter = limiter
        self.task_id = task_id

    def check(self) -> bool:
        """Check if task should continue. Returns False if killed."""
        killed, reason = self.limiter.is_task_killed(self.task_id)
        if killed:
            raise ResourceLimitError(f"Task killed: {reason}")
        return True


class ResourceLimitError(Exception):
    """Raised when resource limits are exceeded."""
    pass


# Default config template
DEFAULT_CONFIG = """# Resource Limits Configuration
# Prevent runaway tasks from consuming all system resources

max_memory_mb: 2048           # Max memory per task (MB)
max_task_minutes: 120         # Max duration per task (minutes)
max_total_memory_mb: 4096     # Max total memory for process (MB)
max_concurrent_tasks: 3       # Max parallel tasks
cpu_throttle_percent: 80      # Start throttling at this CPU %
check_interval_seconds: 5.0   # How often to check limits
kill_on_exceed: true          # Kill task if exceeds limits
warn_threshold_percent: 0.8   # Warn at 80% of limit
min_disk_space_gb: 1.0        # Minimum disk space (GB)
memory_critical_percent: 95   # Critical memory threshold (%)
memory_warning_percent: 85    # Warning memory threshold (%)
network_check_url: "https://www.google.com"  # URL for network checks
network_timeout: 5            # Network check timeout (seconds)
"""


def create_default_config():
    """Create default config file."""
    config_path = Path("config/resources.yaml")
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(DEFAULT_CONFIG)
        logger.info(f"Created resource limits config: {config_path}")
