#!/usr/bin/env python3
"""
Eversale CLI - Your AI Employee

Pure Python entry point for the eversale command.
Installed via: pip install -e .

Usage:
    eversale "Task description"              # Simple task (run_simple.py)
    eversale --ultimate "Complex task"       # Ultimate mode (run_ultimate.py)
    eversale --help                          # Show help
    eversale --version                       # Show version
"""

import sys
import os
import asyncio
from pathlib import Path


# ─── Resolve engine directory ─────────────────────────────────────────
# The engine dir is always relative to this file (eversale_cli.py sits
# next to engine/).  Works for both `pip install -e .` and direct runs.
ENGINE_DIR = str(Path(__file__).resolve().parent / "engine")
AGENT_DIR = str(Path(ENGINE_DIR) / "agent")

# Ensure engine is importable (mimics the old Node.js wrapper behavior)
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)


def _show_help():
    """Print usage help."""
    print("""
Eversale CLI - Your AI Employee
================================

Usage:
    eversale "Task description"              Run a task (accessibility-first agent)
    eversale --ultimate "Complex task"       Run complex task (full orchestration engine)
    eversale                                 Interactive mode

Options:
    --ultimate          Use the full orchestration engine for complex multi-step tasks
    --headless          Run browser in headless mode
    --max-steps N       Maximum steps before giving up (default: 20)
    --debug, -d         Enable debug output
    --version           Show version
    --help, -h          Show this help

Examples:
    eversale "Search Google for AI news"
    eversale "Find 10 marketing agencies in Miami"
    eversale --ultimate "Research Stripe competitors and create a report"
    eversale --headless "Navigate to github.com"

Environment Variables:
    OPENAI_API_KEY      API key for LLM provider (e.g. Z.AI)
    OPENAI_BASE_URL     Base URL for OpenAI-compatible API
    OPENAI_MODEL        Model name (default: glm-5)
    EVERSALE_HOME       Home directory (default: ~/.eversale)
""")


def _show_version():
    """Print version."""
    print("Eversale CLI v2.1.218 (Python)")


def main():
    """Main entry point for the eversale command."""
    # Force unbuffered stdout so users see progress in real-time
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass  # Python < 3.7

    args = sys.argv[1:]

    # Quick flags that don't need engine imports
    if "--help" in args or "-h" in args:
        _show_help()
        return

    if "--version" in args:
        _show_version()
        return

    # Detect mode: --ultimate routes to run_ultimate.py
    use_ultimate = False
    if "--ultimate" in args:
        use_ultimate = True
        args.remove("--ultimate")
        # Reconstruct sys.argv for the downstream script
        sys.argv = [sys.argv[0]] + args

    # Ensure EVERSALE_HOME exists
    eversale_home = Path(os.environ.get("EVERSALE_HOME", Path.home() / ".eversale"))
    eversale_home.mkdir(parents=True, exist_ok=True)
    (eversale_home / "logs").mkdir(parents=True, exist_ok=True)
    (eversale_home / "outputs").mkdir(parents=True, exist_ok=True)

    # Set ENGINE_DIR env var for runtime file resolution
    os.environ["EVERSALE_ENGINE_DIR"] = ENGINE_DIR
    os.environ.setdefault("EVERSALE_HOME", str(eversale_home))

    if use_ultimate:
        _run_ultimate()
    else:
        _run_simple()


def _run_simple():
    """Delegate to run_simple.py (accessibility-first agent)."""
    try:
        # Import and run the simple agent
        import run_simple
        exit_code = asyncio.run(run_simple.main())
        sys.exit(exit_code or 0)
    except KeyboardInterrupt:
        print("\nInterrupted. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        print("Check ~/.eversale/logs/eversale.log for details")
        sys.exit(1)


def _run_ultimate():
    """Delegate to run_ultimate.py (full orchestration engine)."""
    try:
        # Import run_ultimate — it has its own _run_with_clean_shutdown
        import run_ultimate
        run_ultimate._run_with_clean_shutdown()
    except KeyboardInterrupt:
        print("\nInterrupted. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        print("Check ~/.eversale/logs/eversale.log for details")
        sys.exit(1)


if __name__ == "__main__":
    main()
