#!/usr/bin/env python3
"""
Test script for auto-restart system.

This script simulates various crash scenarios to test the auto-restart wrapper.

Usage:
    python auto_restart.py test_auto_restart.py <scenario>

Scenarios:
    clean_exit      - Exit cleanly (should NOT restart)
    immediate_crash - Crash immediately (should restart)
    delayed_crash   - Run for 10s then crash (should restart)
    multiple_crash  - Crash 3 times then exit clean
    user_interrupt  - Simulate Ctrl+C (should NOT restart)
"""

import sys
import time
import os

def main():
    if len(sys.argv) < 2:
        print("Usage: python auto_restart.py test_auto_restart.py <scenario>")
        print("Scenarios: clean_exit, immediate_crash, delayed_crash, multiple_crash, user_interrupt")
        sys.exit(1)

    scenario = sys.argv[1]

    print(f"Running test scenario: {scenario}")

    if scenario == "clean_exit":
        print("Running for 5 seconds...")
        time.sleep(5)
        print("Exiting cleanly (exit code 0)")
        sys.exit(0)

    elif scenario == "immediate_crash":
        print("Crashing immediately...")
        sys.exit(1)

    elif scenario == "delayed_crash":
        print("Running for 10 seconds before crashing...")
        time.sleep(10)
        print("Crashing now!")
        sys.exit(1)

    elif scenario == "multiple_crash":
        # Track attempts using a file
        attempt_file = os.path.expanduser("~/.eversale/test_restart_attempts.txt")
        os.makedirs(os.path.dirname(attempt_file), exist_ok=True)

        if os.path.exists(attempt_file):
            with open(attempt_file, 'r') as f:
                attempts = int(f.read().strip() or "0")
        else:
            attempts = 0

        attempts += 1

        with open(attempt_file, 'w') as f:
            f.write(str(attempts))

        print(f"Attempt {attempts}/3")

        if attempts < 3:
            print(f"Crashing (attempt {attempts})...")
            time.sleep(2)
            sys.exit(1)
        else:
            print("Third attempt - exiting cleanly")
            os.remove(attempt_file)
            sys.exit(0)

    elif scenario == "user_interrupt":
        print("Simulating user interrupt (Ctrl+C)...")
        time.sleep(1)
        sys.exit(130)  # Exit code for SIGINT

    else:
        print(f"Unknown scenario: {scenario}")
        sys.exit(1)


if __name__ == "__main__":
    main()
