#!/usr/bin/env python3
"""
Auto-Restart Wrapper for Eversale CLI Agent

Monitors the main process and automatically restarts it if it crashes.
Features:
- Exponential backoff to prevent infinite crash loops
- Crash diagnostics saved to file
- Max retry limits with cooldown periods
- Clean shutdown on user interrupt
- Logging of all restart events

Usage:
    python auto_restart.py [args...]

    All arguments are passed through to run_ultimate.py

Example:
    python auto_restart.py "Research Stripe"
    python auto_restart.py --interactive
"""

import sys
import os
import subprocess
import time
import signal
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

# Configure paths
ENGINE_DIR = Path(__file__).parent
RUN_ULTIMATE_PATH = ENGINE_DIR / "run_ultimate.py"
CRASH_LOG_DIR = Path.home() / ".eversale" / "crash_logs"
CRASH_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Restart configuration
INITIAL_BACKOFF = 5.0  # Start with 5 second delay
MAX_BACKOFF = 300.0    # Max 5 minute delay
BACKOFF_MULTIPLIER = 2.0
MAX_RETRIES_BEFORE_COOLDOWN = 5  # After 5 crashes, enter cooldown
COOLDOWN_PERIOD = 600.0  # 10 minute cooldown
RESET_WINDOW = 3600.0  # Reset retry count after 1 hour of stable running

# Color codes for terminal output (only if TTY)
def supports_color():
    """Check if terminal supports color."""
    return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()

if supports_color():
    RED = '\033[91m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    CYAN = '\033[96m'
    DIM = '\033[2m'
    RESET = '\033[0m'
else:
    RED = YELLOW = GREEN = CYAN = DIM = RESET = ''


class RestartManager:
    """Manages process restarts with exponential backoff and crash diagnostics."""

    def __init__(self):
        self.retry_count = 0
        self.total_crashes = 0
        self.current_backoff = INITIAL_BACKOFF
        self.last_start_time: Optional[float] = None
        self.crash_history: List[Dict] = []
        self.should_exit = False

    def record_crash(self, exit_code: int, runtime_seconds: float, error_output: str = ""):
        """Record a crash with diagnostics."""
        self.total_crashes += 1
        self.retry_count += 1

        crash_info = {
            "timestamp": datetime.now().isoformat(),
            "exit_code": exit_code,
            "runtime_seconds": runtime_seconds,
            "retry_count": self.retry_count,
            "backoff_seconds": self.current_backoff,
            "error_output": error_output[-500:] if error_output else ""  # Last 500 chars
        }

        self.crash_history.append(crash_info)

        # Save crash info to file
        crash_file = CRASH_LOG_DIR / f"crash_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(crash_file, 'w') as f:
                json.dump(crash_info, f, indent=2)
            print(f"{DIM}Crash info saved to: {crash_file}{RESET}")
        except Exception as e:
            print(f"{DIM}Warning: Could not save crash info: {e}{RESET}")

        # Update backoff
        self.current_backoff = min(MAX_BACKOFF, self.current_backoff * BACKOFF_MULTIPLIER)

    def record_successful_start(self):
        """Record that the process started successfully."""
        self.last_start_time = time.time()

    def check_stable_runtime(self):
        """Check if process has been running long enough to reset retry count."""
        if self.last_start_time is None:
            return

        runtime = time.time() - self.last_start_time
        if runtime > RESET_WINDOW:
            # Process has been stable for over an hour, reset counters
            print(f"{GREEN}Process stable for {runtime/60:.1f} minutes. Resetting retry counters.{RESET}")
            self.retry_count = 0
            self.current_backoff = INITIAL_BACKOFF

    def should_enter_cooldown(self) -> bool:
        """Check if we should enter cooldown period."""
        return self.retry_count >= MAX_RETRIES_BEFORE_COOLDOWN

    def enter_cooldown(self):
        """Enter cooldown period after too many crashes."""
        print(f"{YELLOW}Too many crashes ({self.retry_count}). Entering {COOLDOWN_PERIOD/60:.1f} minute cooldown.{RESET}")
        print(f"{DIM}Recent crashes:{RESET}")
        for crash in self.crash_history[-5:]:
            print(f"  {crash['timestamp']}: exit_code={crash['exit_code']}, runtime={crash['runtime_seconds']:.1f}s")

        # Wait for cooldown
        self._interruptible_sleep(COOLDOWN_PERIOD)

        # After cooldown, reset to moderate retry level
        self.retry_count = 2  # Don't reset to 0, keep some caution
        self.current_backoff = INITIAL_BACKOFF * 2
        print(f"{GREEN}Cooldown complete. Resuming with caution.{RESET}")

    def get_backoff_seconds(self) -> float:
        """Get current backoff duration."""
        return self.current_backoff

    def _interruptible_sleep(self, seconds: float):
        """Sleep that can be interrupted by Ctrl+C."""
        end_time = time.time() + seconds
        try:
            while time.time() < end_time and not self.should_exit:
                remaining = end_time - time.time()
                if remaining > 0:
                    time.sleep(min(1.0, remaining))
        except KeyboardInterrupt:
            self.should_exit = True
            raise


def setup_signal_handlers(manager: RestartManager):
    """Setup signal handlers for clean shutdown."""
    def handle_signal(signum, frame):
        print(f"\n{YELLOW}Received shutdown signal. Stopping auto-restart...{RESET}")
        manager.should_exit = True
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    # CRITICAL FIX: SIGTERM doesn't exist on Windows - wrap in try/hasattr (audit fix)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, handle_signal)


def run_with_restart(args: List[str]):
    """Main loop that runs the process with auto-restart."""
    manager = RestartManager()
    setup_signal_handlers(manager)

    print(f"{CYAN}Eversale Auto-Restart Wrapper{RESET}")
    print(f"{DIM}Monitoring: {RUN_ULTIMATE_PATH}{RESET}")
    print(f"{DIM}Press Ctrl+C to stop{RESET}\n")

    while not manager.should_exit:
        try:
            # Build command
            cmd = [sys.executable, str(RUN_ULTIMATE_PATH)] + args

            # Set environment variable to mark this as running via auto-restart
            # This prevents infinite wrapper spawning
            env = os.environ.copy()
            env['EVERSALE_AUTO_RESTART'] = '1'

            # Start process
            start_time = time.time()
            print(f"{GREEN}Starting process...{RESET}")
            manager.record_successful_start()

            # Run the process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True,
                env=env  # Pass environment with auto-restart marker
            )

            # Stream output in real-time
            # CRITICAL FIX: Use threading for cross-platform output streaming
            # 'select' doesn't work on Windows pipes, and 'communicate' buffers everything.
            import threading

            stdout_lines = []
            stderr_lines = []

            def stream_reader(stream, line_list, is_stderr=False):
                """Read lines from a stream and print them in real-time."""
                try:
                    for line in iter(stream.readline, ''):
                        if not line: break
                        if is_stderr:
                            print(line, end='', file=sys.stderr)
                        else:
                            print(line, end='')
                        line_list.append(line)
                        
                        # Periodically check for stability in the main loop,
                        # but we can't notify the manager easily from here without locking.
                        # We'll rely on the main thread loop for that.
                except Exception:
                    pass
                finally:
                    stream.close()

            # Start threads for stdout and stderr
            t_out = threading.Thread(target=stream_reader, args=(process.stdout, stdout_lines, False))
            t_err = threading.Thread(target=stream_reader, args=(process.stderr, stderr_lines, True))
            
            t_out.daemon = True
            t_err.daemon = True
            
            t_out.start()
            t_err.start()

            # Wait for process to complete
            while process.poll() is None:
                manager.check_stable_runtime()
                # Sleep briefly to avoid busy loop, allowing threads to run
                time.sleep(0.1)

            # Ensure threads finish
            t_out.join(timeout=1.0)
            t_err.join(timeout=1.0)


            # Process finished
            exit_code = process.returncode
            runtime = time.time() - start_time

            # Check if exit was clean (exit code 0 or user interrupt)
            if exit_code == 0:
                print(f"{GREEN}Process exited cleanly.{RESET}")
                break  # Clean exit, don't restart

            # Check for keyboard interrupt (Ctrl+C)
            if exit_code in (-2, 130):  # SIGINT
                print(f"{YELLOW}Process interrupted by user.{RESET}")
                break  # User interrupt, don't restart

            # Crash detected
            error_output = '\n'.join(stderr_lines[-20:]) if stderr_lines else ""
            print(f"\n{RED}Process crashed with exit code {exit_code} after {runtime:.1f}s{RESET}")

            # Record crash
            manager.record_crash(exit_code, runtime, error_output)

            # Check if we should enter cooldown
            if manager.should_enter_cooldown():
                manager.enter_cooldown()
                if manager.should_exit:
                    break

            # Wait before restart (exponential backoff)
            backoff = manager.get_backoff_seconds()
            print(f"{YELLOW}Waiting {backoff:.1f}s before restart (attempt {manager.retry_count})...{RESET}")

            try:
                manager._interruptible_sleep(backoff)
            except KeyboardInterrupt:
                print(f"\n{YELLOW}Restart cancelled by user.{RESET}")
                break

            if manager.should_exit:
                break

            print(f"\n{CYAN}Restarting...{RESET}\n")

        except KeyboardInterrupt:
            print(f"\n{YELLOW}Shutdown requested.{RESET}")
            break
        except Exception as e:
            print(f"{RED}Auto-restart error: {e}{RESET}")
            import traceback
            traceback.print_exc()
            break

    # Summary
    print(f"\n{CYAN}Auto-restart stopped.{RESET}")
    if manager.total_crashes > 0:
        print(f"{DIM}Total crashes this session: {manager.total_crashes}{RESET}")
        print(f"{DIM}Crash logs: {CRASH_LOG_DIR}{RESET}")


def main():
    """Entry point."""
    # Check if run_ultimate.py exists
    if not RUN_ULTIMATE_PATH.exists():
        print(f"{RED}Error: {RUN_ULTIMATE_PATH} not found{RESET}")
        sys.exit(1)

    # Get arguments to pass through
    args = sys.argv[1:]

    # Run with auto-restart
    run_with_restart(args)


if __name__ == "__main__":
    main()
