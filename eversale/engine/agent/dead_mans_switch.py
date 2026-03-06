"""
Dead Man's Switch - Triggers emergency action if no activity for X hours.

For space missions, remote deployments, or critical systems where
silence = something is wrong.

Usage:
    switch = DeadMansSwitch(timeout_hours=4)
    switch.ping()  # Call after each successful task

    # If no ping for 4 hours, triggers:
    # 1. Emergency log entry
    # 2. Fallback task execution
    # 3. Alert file creation for external monitoring
"""

import asyncio
import json
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable, List
from loguru import logger

from .atomic_file import atomic_write_json, atomic_write_text


class DeadMansSwitch:
    def __init__(
        self,
        timeout_hours: float = 0.25,  # Default: 15 minutes for interactive mode
        config_path: Path = Path("config/dead_mans_switch.yaml"),
        state_path: Path = Path("memory/dead_mans_switch.json"),
    ):
        self.timeout_seconds = timeout_hours * 3600
        self.config_path = config_path
        self.state_path = state_path
        self.alert_path = Path("logs/DEAD_MAN_ALERT.txt")

        self.last_ping = time.time()
        self.triggered = False
        self.running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._fallback_tasks: List[str] = []
        self._on_trigger_callbacks: List[Callable] = []

        self._load_state()
        self._load_config()

    def _load_state(self):
        """Load last known state."""
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text())
                self.last_ping = data.get("last_ping", time.time())
                self.triggered = data.get("triggered", False)
            except Exception:
                pass

    def _save_state(self):
        """Persist state."""
        data = {
            "last_ping": self.last_ping,
            "triggered": self.triggered,
            "last_updated": datetime.now().isoformat(),
        }
        atomic_write_json(self.state_path, data, indent=2, backup=True)

    def _load_config(self):
        """Load config with fallback tasks."""
        if self.config_path.exists():
            try:
                import yaml
                config = yaml.safe_load(self.config_path.read_text())
                self.timeout_seconds = config.get("timeout_hours", 4.0) * 3600
                self._fallback_tasks = config.get("fallback_tasks", [])
            except Exception:
                pass

    def ping(self):
        """Signal that system is alive. Call after each successful task."""
        self.last_ping = time.time()
        self.triggered = False
        self._save_state()

        # Clear alert if it exists
        if self.alert_path.exists():
            self.alert_path.unlink()

        logger.debug(f"Dead man's switch pinged at {datetime.now()}")

    def time_remaining(self) -> float:
        """Seconds until trigger (negative if overdue)."""
        return self.timeout_seconds - (time.time() - self.last_ping)

    def is_overdue(self) -> bool:
        """Check if switch should trigger."""
        return self.time_remaining() <= 0

    def start_monitoring(self):
        """Start background monitoring thread."""
        if self.running:
            return

        self.running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info(f"Dead man's switch monitoring started (timeout: {self.timeout_seconds/3600:.1f}h)")

    def stop_monitoring(self):
        """Stop monitoring."""
        self.running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)

    def _monitor_loop(self):
        """Background loop checking for timeout."""
        while self.running:
            if self.is_overdue() and not self.triggered:
                self._trigger()
            time.sleep(60)  # Check every minute

    def _trigger(self):
        """Execute dead man's switch actions."""
        self.triggered = True
        self._save_state()

        timestamp = datetime.now().isoformat()
        hours_silent = (time.time() - self.last_ping) / 3600

        logger.error(f"DEAD MAN'S SWITCH TRIGGERED - No activity for {hours_silent:.1f} hours")

        # 1. Create alert file for external monitoring
        alert_content = f"""DEAD MAN'S SWITCH ALERT
========================
Triggered: {timestamp}
Last Activity: {datetime.fromtimestamp(self.last_ping).isoformat()}
Silent For: {hours_silent:.1f} hours
Timeout Setting: {self.timeout_seconds/3600:.1f} hours

This system has not completed any tasks within the expected timeframe.
Possible causes:
- System crash not caught by watchdog
- Network failure preventing task completion
- Infinite loop or hung process
- Resource exhaustion

Recommended actions:
1. Check system logs: logs/eversale.log
2. Check crash logs: logs/crashes.log
3. Restart the system: ./eversale --watchdog
"""
        atomic_write_text(self.alert_path, alert_content, backup=False)

        # 2. Log to dedicated dead man's log
        dead_log = Path("logs/dead_mans_switch.log")
        with open(dead_log, "a") as f:
            f.write(f"[{timestamp}] TRIGGERED after {hours_silent:.1f}h silence\n")

        # 3. Execute callbacks
        for callback in self._on_trigger_callbacks:
            try:
                callback(hours_silent)
            except Exception as e:
                logger.error(f"Dead man's switch callback error: {e}")

        # 4. Execute fallback tasks (if agent available)
        if self._fallback_tasks:
            logger.info(f"Executing {len(self._fallback_tasks)} fallback tasks")
            # Fallback tasks are executed by the main agent loop if it recovers

    def on_trigger(self, callback: Callable):
        """Register callback for when switch triggers."""
        self._on_trigger_callbacks.append(callback)

    def add_fallback_task(self, task: str):
        """Add a fallback task to execute on trigger."""
        self._fallback_tasks.append(task)

    def get_fallback_tasks(self) -> List[str]:
        """Get pending fallback tasks."""
        if self.triggered:
            tasks = self._fallback_tasks.copy()
            self._fallback_tasks.clear()
            return tasks
        return []

    def status(self) -> dict:
        """Get current switch status."""
        remaining = self.time_remaining()
        return {
            "active": self.running,
            "triggered": self.triggered,
            "last_ping": datetime.fromtimestamp(self.last_ping).isoformat(),
            "timeout_hours": self.timeout_seconds / 3600,
            "time_remaining_hours": max(0, remaining / 3600),
            "overdue": self.is_overdue(),
            "overdue_hours": abs(min(0, remaining)) / 3600 if remaining < 0 else 0,
        }


# Default config template
DEFAULT_CONFIG = """# Dead Man's Switch Configuration
# Triggers emergency actions if no successful task for X hours
# Default: 0.25 hours (15 minutes) for interactive mode
# For daemon/production mode, increase to 4.0 or higher

timeout_hours: 0.25

# Tasks to execute when switch triggers (runs when system recovers)
fallback_tasks:
  - "Log system status and send diagnostic report"
  - "Check all scheduled tasks are still configured"

# Future: webhook/email alerts
# alert_webhook: https://hooks.slack.com/...
# alert_email: ops@company.com
"""


def create_default_config():
    """Create default config file."""
    config_path = Path("config/dead_mans_switch.yaml")
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(DEFAULT_CONFIG)
        logger.info(f"Created dead man's switch config: {config_path}")
