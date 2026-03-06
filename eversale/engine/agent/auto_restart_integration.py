"""
Auto-Restart Integration with Forever Operations

This module shows how to integrate the auto-restart wrapper with
forever operations and crash recovery for maximum reliability.

Architecture:
    [Auto-Restart Wrapper]
        |
        v
    [run_ultimate.py]
        |
        v
    [Brain with Crash Recovery]
        |
        v
    [Forever Worker Operations]

Protection Layers:
1. Process-level: auto_restart.py monitors and restarts crashed processes
2. Session-level: Brain.crash_recovery resumes interrupted tasks
3. Worker-level: ForeverWorker checkpointing for infinite loops

Example Usage:
    # Start with auto-restart protection
    python engine/auto_restart.py "Monitor inbox forever"

    # Or directly in code
    from agent.auto_restart_integration import start_with_auto_restart
    start_with_auto_restart(task_prompt="Monitor inbox forever")
"""

import sys
import subprocess
from pathlib import Path
from typing import Optional, List


def start_with_auto_restart(
    task_prompt: str,
    debug: bool = False,
    interactive: bool = False
) -> int:
    """
    Start the agent with auto-restart protection.

    Args:
        task_prompt: The task to run
        debug: Enable debug mode
        interactive: Run in interactive mode

    Returns:
        Exit code from auto_restart.py
    """
    engine_dir = Path(__file__).parent.parent
    auto_restart_path = engine_dir / "auto_restart.py"

    # Build arguments
    args = [sys.executable, str(auto_restart_path)]

    if debug:
        args.append("--debug")

    if interactive:
        args.append("--interactive")
    elif task_prompt:
        args.append(task_prompt)

    # Run with auto-restart
    return subprocess.call(args)


def run_forever_worker_with_restart(
    worker_name: str,
    check_fn_module: str,
    check_fn_name: str,
    process_fn_module: str,
    process_fn_name: str
):
    """
    Run a forever worker with full auto-restart protection.

    This creates a Python script that runs your forever worker,
    then wraps it with auto-restart.

    Args:
        worker_name: Name for the worker
        check_fn_module: Module path for check function (e.g., 'my.module')
        check_fn_name: Function name for checking items
        process_fn_module: Module path for process function
        process_fn_name: Function name for processing items

    Example:
        run_forever_worker_with_restart(
            worker_name="email_monitor",
            check_fn_module="my_workers",
            check_fn_name="check_inbox",
            process_fn_module="my_workers",
            process_fn_name="respond_to_email"
        )
    """
    # Create temporary worker script
    worker_script = f"""
import sys
from pathlib import Path

# Add engine to path
engine_path = Path(__file__).parent.parent
sys.path.insert(0, str(engine_path))

from agent.forever_operations import ForeverWorker, ForeverConfig

# Import user functions
from {check_fn_module} import {check_fn_name}
from {process_fn_module} import {process_fn_name}

class CustomWorker(ForeverWorker):
    def check_for_items(self):
        return {check_fn_name}()

    def process_item(self, item):
        return {process_fn_name}(item)

if __name__ == "__main__":
    config = ForeverConfig(
        poll_interval_seconds=30.0,
        heartbeat_interval_seconds=60.0,
        max_runtime_hours=0  # Unlimited
    )
    worker = CustomWorker(config=config, worker_name="{worker_name}")
    worker.run_forever()
"""

    # Save worker script
    worker_dir = Path.home() / ".eversale" / "workers"
    worker_dir.mkdir(parents=True, exist_ok=True)
    worker_file = worker_dir / f"{worker_name}_worker.py"
    worker_file.write_text(worker_script)

    print(f"Created worker script: {worker_file}")
    print(f"Starting with auto-restart protection...")

    # Run with auto-restart
    engine_dir = Path(__file__).parent.parent
    auto_restart_path = engine_dir / "auto_restart.py"

    subprocess.call([
        sys.executable,
        str(auto_restart_path),
        str(worker_file)
    ])


def get_restart_status() -> dict:
    """
    Get status of auto-restart system.

    Returns:
        Dict with crash logs, recent crashes, etc.
    """
    crash_log_dir = Path.home() / ".eversale" / "crash_logs"

    if not crash_log_dir.exists():
        return {
            "crash_log_dir": str(crash_log_dir),
            "total_crashes": 0,
            "recent_crashes": []
        }

    import json
    from datetime import datetime, timedelta

    crash_files = sorted(crash_log_dir.glob("crash_*.json"))
    total_crashes = len(crash_files)

    # Get crashes from last 24 hours
    cutoff = datetime.now() - timedelta(hours=24)
    recent_crashes = []

    for crash_file in reversed(crash_files[-10:]):  # Last 10
        try:
            data = json.loads(crash_file.read_text())
            crash_time = datetime.fromisoformat(data["timestamp"])
            if crash_time > cutoff:
                recent_crashes.append({
                    "timestamp": data["timestamp"],
                    "exit_code": data["exit_code"],
                    "runtime_seconds": data["runtime_seconds"]
                })
        except Exception:
            continue

    return {
        "crash_log_dir": str(crash_log_dir),
        "total_crashes": total_crashes,
        "crashes_last_24h": len(recent_crashes),
        "recent_crashes": recent_crashes[:5]  # Show last 5
    }


def cleanup_old_crash_logs(max_age_days: int = 7) -> int:
    """
    Clean up old crash logs.

    Args:
        max_age_days: Remove logs older than this many days

    Returns:
        Number of files removed
    """
    crash_log_dir = Path.home() / ".eversale" / "crash_logs"

    if not crash_log_dir.exists():
        return 0

    from datetime import datetime, timedelta

    cutoff = datetime.now() - timedelta(days=max_age_days)
    removed = 0

    for crash_file in crash_log_dir.glob("crash_*.json"):
        try:
            mtime = datetime.fromtimestamp(crash_file.stat().st_mtime)
            if mtime < cutoff:
                crash_file.unlink()
                removed += 1
        except Exception:
            continue

    return removed


# =============================================================================
# COMBINED PROTECTION: Auto-Restart + Crash Recovery + Forever Operations
# =============================================================================

class ResilientAgent:
    """
    Combines all protection mechanisms for maximum reliability.

    Features:
    1. Auto-restart at process level
    2. Crash recovery at session level
    3. Forever operations at task level
    4. Checkpointing for state persistence

    Usage:
        agent = ResilientAgent()
        agent.run_forever(task_prompt="Monitor inbox")
    """

    def __init__(self, debug: bool = False):
        self.debug = debug
        self.engine_dir = Path(__file__).parent.parent

    def run_forever(self, task_prompt: str):
        """
        Run a task forever with all protection layers.

        Args:
            task_prompt: The task to run (should be a forever operation)
        """
        auto_restart_path = self.engine_dir / "auto_restart.py"

        args = [sys.executable, str(auto_restart_path)]

        if self.debug:
            args.append("--debug")

        args.append(task_prompt)

        print(f"Starting resilient agent with auto-restart...")
        print(f"Task: {task_prompt}")
        print(f"Protection layers:")
        print(f"  1. Auto-restart wrapper")
        print(f"  2. Brain crash recovery")
        print(f"  3. Forever operations checkpointing")
        print()

        return subprocess.call(args)

    def run_worker(
        self,
        worker_class,
        worker_name: str = "custom_worker",
        config_overrides: dict = None
    ):
        """
        Run a ForeverWorker with auto-restart protection.

        Args:
            worker_class: Subclass of ForeverWorker
            worker_name: Name for the worker
            config_overrides: Dict of config overrides
        """
        from agent.forever_operations import ForeverConfig

        # Create worker script
        worker_script_path = self._create_worker_script(
            worker_class,
            worker_name,
            config_overrides
        )

        # Run with auto-restart
        auto_restart_path = self.engine_dir / "auto_restart.py"

        print(f"Starting worker '{worker_name}' with auto-restart...")
        print(f"Worker script: {worker_script_path}")
        print()

        return subprocess.call([
            sys.executable,
            str(auto_restart_path),
            str(worker_script_path)
        ])

    def _create_worker_script(
        self,
        worker_class,
        worker_name: str,
        config_overrides: dict = None
    ) -> Path:
        """Create a temporary script to run the worker."""
        import inspect

        # Get worker class source
        worker_source = inspect.getsource(worker_class)
        worker_module = inspect.getmodule(worker_class).__name__

        config_overrides = config_overrides or {}

        script_content = f"""
import sys
from pathlib import Path

# Add engine to path
engine_path = Path(__file__).parent.parent
sys.path.insert(0, str(engine_path))

from agent.forever_operations import ForeverConfig

# Worker class
{worker_source}

if __name__ == "__main__":
    config = ForeverConfig(
        **{config_overrides}
    )
    worker = {worker_class.__name__}(config=config, worker_name="{worker_name}")
    worker.run_forever()
"""

        # Save script
        worker_dir = Path.home() / ".eversale" / "workers"
        worker_dir.mkdir(parents=True, exist_ok=True)
        script_path = worker_dir / f"{worker_name}_runner.py"
        script_path.write_text(script_content)

        return script_path

    def get_status(self) -> dict:
        """Get combined status of all protection layers."""
        return {
            "auto_restart": get_restart_status(),
            "crash_recovery": self._get_crash_recovery_status(),
            "forever_workers": self._get_worker_status()
        }

    def _get_crash_recovery_status(self) -> dict:
        """Get crash recovery status."""
        crash_state_file = Path.home() / ".eversale" / "crash_state.json"

        if not crash_state_file.exists():
            return {"has_pending": False}

        import json
        try:
            data = json.loads(crash_state_file.read_text())
            return {
                "has_pending": data.get("has_pending", False),
                "pending_prompt": data.get("pending_prompt", "")[:100]
            }
        except Exception:
            return {"has_pending": False}

    def _get_worker_status(self) -> list:
        """Get status of all forever workers."""
        worker_dir = Path.home() / ".eversale" / "workers"

        if not worker_dir.exists():
            return []

        import json
        workers = []

        for worker_subdir in worker_dir.iterdir():
            if worker_subdir.is_dir():
                heartbeat_file = worker_subdir / "heartbeat.json"
                if heartbeat_file.exists():
                    try:
                        data = json.loads(heartbeat_file.read_text())
                        workers.append({
                            "name": worker_subdir.name,
                            "state": data.get("state"),
                            "uptime_seconds": data.get("uptime_seconds"),
                            "items_processed": data.get("items_processed"),
                            "last_activity": data.get("last_activity")
                        })
                    except Exception:
                        continue

        return workers


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def start_resilient(task_prompt: str, debug: bool = False):
    """
    Quick start with all protection layers.

    Args:
        task_prompt: Task to run
        debug: Enable debug mode
    """
    agent = ResilientAgent(debug=debug)
    return agent.run_forever(task_prompt)


def monitor_crashes(tail: bool = False, count: int = 10):
    """
    Monitor crash logs.

    Args:
        tail: Follow crash logs in real-time
        count: Number of recent crashes to show
    """
    crash_log_dir = Path.home() / ".eversale" / "crash_logs"

    if not crash_log_dir.exists():
        print("No crash logs found")
        return

    import json
    from datetime import datetime

    crash_files = sorted(crash_log_dir.glob("crash_*.json"))

    if not crash_files:
        print("No crash logs found")
        return

    print(f"Total crashes: {len(crash_files)}")
    print(f"\nLast {count} crashes:\n")

    for crash_file in reversed(crash_files[-count:]):
        try:
            data = json.loads(crash_file.read_text())
            timestamp = datetime.fromisoformat(data["timestamp"])
            print(f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} - "
                  f"Exit code {data['exit_code']}, "
                  f"Runtime {data['runtime_seconds']:.1f}s, "
                  f"Retry {data['retry_count']}")

            if data.get("error_output"):
                print(f"  Error: {data['error_output'][:100]}...")

        except Exception as e:
            print(f"Failed to read {crash_file}: {e}")

    if tail:
        print("\nWatching for new crashes (Ctrl+C to stop)...")
        import time
        last_count = len(crash_files)

        try:
            while True:
                time.sleep(2)
                current_files = list(crash_log_dir.glob("crash_*.json"))
                if len(current_files) > last_count:
                    # New crash
                    new_crash = sorted(current_files)[-1]
                    data = json.loads(new_crash.read_text())
                    timestamp = datetime.fromisoformat(data["timestamp"])
                    print(f"\n[NEW CRASH] {timestamp.strftime('%H:%M:%S')} - "
                          f"Exit code {data['exit_code']}, "
                          f"Runtime {data['runtime_seconds']:.1f}s")
                    last_count = len(current_files)
        except KeyboardInterrupt:
            print("\nStopped monitoring")


if __name__ == "__main__":
    # Example usage
    print("Auto-Restart Integration Examples:")
    print()
    print("1. Start with resilient protection:")
    print("   from agent.auto_restart_integration import start_resilient")
    print("   start_resilient('Monitor inbox forever')")
    print()
    print("2. Check status:")
    print("   agent = ResilientAgent()")
    print("   print(agent.get_status())")
    print()
    print("3. Monitor crashes:")
    print("   from agent.auto_restart_integration import monitor_crashes")
    print("   monitor_crashes(tail=True)")
