"""
Health Check Module - Continuous Agent Health Monitoring

Writes periodic health reports to ~/.eversale/health.json for external monitoring.
External systems can check if the agent is alive by verifying the timestamp freshness.

Features:
- Writes JSON health file every 30 seconds
- Includes: timestamp, status, last_activity, iterations, errors, memory, uptime
- Simple CLI command to check health: `eversale --health`
- Agent considered dead if health file is older than 2 minutes

Usage:
    # In orchestration loop
    from health_check import HealthWriter

    health = HealthWriter()
    health.start()  # Starts background thread

    # Update status throughout execution
    health.update_activity("Processing task...")
    health.increment_iterations()
    health.increment_errors()

    # Stop when done
    health.stop()

    # CLI check
    from health_check import check_health_cli
    check_health_cli()  # Prints status and returns exit code
"""

import json
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from loguru import logger


# Health file location
HEALTH_DIR = Path.home() / '.eversale'
HEALTH_FILE = HEALTH_DIR / 'health.json'
HEALTH_INTERVAL = 30  # seconds
HEALTH_TIMEOUT = 120  # seconds (2 minutes)


@dataclass
class HealthReport:
    """Health status report."""
    timestamp: str
    status: str  # "running", "idle", "error", "stopped"
    last_activity: str
    iterations_completed: int
    errors_count: int
    memory_mb: float
    uptime_seconds: float

    # Additional metrics
    last_heartbeat: str
    process_id: int
    version: str = "2.0"


class HealthWriter:
    """
    Continuous health monitoring writer.

    Runs in background thread, updates health.json every 30 seconds.
    External monitoring can verify agent is alive by checking timestamp freshness.
    """

    def __init__(self, interval: int = HEALTH_INTERVAL):
        self.interval = interval
        self.start_time = datetime.now()

        # State
        self.status = "starting"
        self.last_activity = "Initializing"
        self.iterations = 0
        self.errors = 0
        self.running = False

        # Threading
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Ensure directory exists
        HEALTH_DIR.mkdir(parents=True, exist_ok=True)

        logger.info(f"[HEALTH] HealthWriter initialized (interval={interval}s)")

    def start(self):
        """Start background health monitoring thread."""
        if self.running:
            logger.warning("[HEALTH] HealthWriter already running")
            return

        self.running = True
        self.status = "running"
        self._stop_event.clear()

        self._thread = threading.Thread(target=self._health_loop, daemon=True)
        self._thread.start()

        logger.info("[HEALTH] Background health monitoring started")

    def stop(self):
        """Stop background health monitoring thread."""
        if not self.running:
            return

        self.running = False
        self.status = "stopped"
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=2)

        # Write final health status
        self._write_health()

        logger.info("[HEALTH] Background health monitoring stopped")

    def update_activity(self, activity: str):
        """Update last activity description."""
        self.last_activity = activity

    def increment_iterations(self):
        """Increment iteration counter."""
        self.iterations += 1

    def increment_errors(self):
        """Increment error counter."""
        self.errors += 1

    def set_status(self, status: str):
        """Set current status (running, idle, error, stopped)."""
        self.status = status

    def _health_loop(self):
        """Background loop that writes health status periodically."""
        while not self._stop_event.is_set():
            try:
                self._write_health()
            except Exception as e:
                logger.warning(f"[HEALTH] Failed to write health: {e}")

            # Sleep in small increments to allow quick shutdown
            for _ in range(self.interval):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

    def _write_health(self):
        """Write health status to JSON file."""
        uptime = (datetime.now() - self.start_time).total_seconds()

        # Get memory usage
        memory_mb = 0.0
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
        except (ImportError, Exception) as e:
            logger.debug(f"[HEALTH] Failed to get memory usage: {e}")

        # Get process ID
        process_id = 0
        try:
            import os
            process_id = os.getpid()
        except Exception as e:
            logger.debug(f"[HEALTH] Failed to get PID: {e}")

        # Create health report
        report = HealthReport(
            timestamp=datetime.now().isoformat(),
            status=self.status,
            last_activity=self.last_activity,
            iterations_completed=self.iterations,
            errors_count=self.errors,
            memory_mb=memory_mb,
            uptime_seconds=uptime,
            last_heartbeat=datetime.now().isoformat(),
            process_id=process_id
        )

        # Write to file
        try:
            HEALTH_FILE.write_text(json.dumps(asdict(report), indent=2))
            logger.debug(f"[HEALTH] Wrote health status: {self.status}, iterations={self.iterations}, errors={self.errors}")
        except Exception as e:
            logger.warning(f"[HEALTH] Failed to write health file: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get current health status as dict."""
        uptime = (datetime.now() - self.start_time).total_seconds()

        return {
            "status": self.status,
            "last_activity": self.last_activity,
            "iterations_completed": self.iterations,
            "errors_count": self.errors,
            "uptime_seconds": uptime,
            "running": self.running
        }


def read_health() -> Optional[Dict[str, Any]]:
    """
    Read health status from file.

    Returns:
        Health dict or None if file doesn't exist
    """
    if not HEALTH_FILE.exists():
        return None

    try:
        data = json.loads(HEALTH_FILE.read_text())
        return data
    except Exception as e:
        logger.warning(f"[HEALTH] Failed to read health file: {e}")
        return None


def is_agent_alive(timeout: int = HEALTH_TIMEOUT) -> bool:
    """
    Check if agent is alive based on health file timestamp.

    Args:
        timeout: Max age in seconds for health file to be considered alive

    Returns:
        True if agent is alive, False otherwise
    """
    health = read_health()
    if not health:
        return False

    try:
        timestamp = datetime.fromisoformat(health['timestamp'])
        age = (datetime.now() - timestamp).total_seconds()
        return age < timeout
    except (KeyError, ValueError) as e:
        logger.warning(f"[HEALTH] Invalid health timestamp: {e}")
        return False


def check_health_cli():
    """
    CLI command to check agent health and print status.

    Exit codes:
        0 = Agent is alive and healthy
        1 = Agent is dead (health file too old or missing)
        2 = Agent has errors
    """
    from rich.console import Console
    from rich.table import Table

    console = Console()

    if not HEALTH_FILE.exists():
        console.print("[red]Agent health file not found[/red]")
        console.print(f"[dim]Expected location: {HEALTH_FILE}[/dim]")
        console.print("\n[yellow]Agent has never run or health monitoring is not enabled[/yellow]")
        return 1

    health = read_health()
    if not health:
        console.print("[red]Failed to read health file[/red]")
        return 1

    # Check if alive
    alive = is_agent_alive()

    # Parse timestamp
    try:
        timestamp = datetime.fromisoformat(health['timestamp'])
        age = (datetime.now() - timestamp).total_seconds()
    except (KeyError, ValueError) as e:
        console.print(f"[red]Invalid health data: {e}[/red]")
        return 1

    # Build status table
    table = Table(title="Agent Health Status", show_header=True)
    table.add_column("Metric", style="cyan", width=25)
    table.add_column("Value", style="white")

    # Status indicator
    if alive:
        if health.get('status') == 'error':
            status_str = "[yellow]RUNNING (with errors)[/yellow]"
            exit_code = 2
        else:
            status_str = "[green]ALIVE[/green]"
            exit_code = 0
    else:
        status_str = f"[red]DEAD (last seen {age:.0f}s ago)[/red]"
        exit_code = 1

    table.add_row("Status", status_str)
    table.add_row("Last Activity", health.get('last_activity', 'Unknown'))
    table.add_row("Iterations Completed", str(health.get('iterations_completed', 0)))
    table.add_row("Errors Count", str(health.get('errors_count', 0)))
    table.add_row("Memory Usage", f"{health.get('memory_mb', 0):.1f} MB")

    # Uptime
    uptime_seconds = health.get('uptime_seconds', 0)
    uptime_str = str(timedelta(seconds=int(uptime_seconds)))
    table.add_row("Uptime", uptime_str)

    # Last heartbeat
    table.add_row("Last Heartbeat", timestamp.strftime('%Y-%m-%d %H:%M:%S'))
    table.add_row("Heartbeat Age", f"{age:.0f} seconds ago")

    # Process ID
    if health.get('process_id'):
        table.add_row("Process ID", str(health['process_id']))

    console.print(table)

    # Health warnings
    if age > HEALTH_TIMEOUT:
        console.print(f"\n[red]WARNING: Health file is {age:.0f}s old (threshold: {HEALTH_TIMEOUT}s)[/red]")
        console.print("[red]Agent is considered DEAD[/red]")
    elif age > HEALTH_TIMEOUT / 2:
        console.print(f"\n[yellow]WARNING: Health file is {age:.0f}s old (getting stale)[/yellow]")

    if health.get('errors_count', 0) > 0:
        console.print(f"\n[yellow]WARNING: {health['errors_count']} errors recorded[/yellow]")

    # File location
    console.print(f"\n[dim]Health file: {HEALTH_FILE}[/dim]")

    return exit_code


def get_health_summary() -> str:
    """
    Get one-line health summary for display.

    Returns:
        Human-readable health summary string
    """
    if not is_agent_alive():
        return "DEAD (health check failed)"

    health = read_health()
    if not health:
        return "Unknown (no health data)"

    status = health.get('status', 'unknown')
    iterations = health.get('iterations_completed', 0)
    errors = health.get('errors_count', 0)
    uptime = health.get('uptime_seconds', 0)

    uptime_str = str(timedelta(seconds=int(uptime)))

    if errors > 0:
        return f"{status.upper()} - {iterations} iterations, {errors} errors, uptime {uptime_str}"
    else:
        return f"{status.upper()} - {iterations} iterations, uptime {uptime_str}"


# Convenience singleton instance
_global_health_writer: Optional[HealthWriter] = None


def get_health_writer() -> HealthWriter:
    """Get or create global health writer instance."""
    global _global_health_writer
    if _global_health_writer is None:
        _global_health_writer = HealthWriter()
    return _global_health_writer


def start_health_monitoring():
    """Start global health monitoring (convenience function)."""
    writer = get_health_writer()
    writer.start()
    return writer


def stop_health_monitoring():
    """Stop global health monitoring (convenience function)."""
    if _global_health_writer:
        _global_health_writer.stop()


# CLI entry point
if __name__ == "__main__":
    import sys
    exit_code = check_health_cli()
    sys.exit(exit_code)
