#!/usr/bin/env python3
"""
Eversale - Your AI Employee

Desktop agent that runs research, sales, admin, customer ops,
spreadsheets, logistics, and more. Runs forever until you cancel.

Usage:
  eversale "Research Stripe"
  eversale  # Interactive mode
  eversale help
"""

import sys
import os
import subprocess

# =============================================================================
# AUTO-INSTALL MISSING DEPENDENCIES
# =============================================================================
def _auto_install_deps():
    """Auto-install missing dependencies before any imports."""
    required = {
        'loguru': 'loguru',
        'rich': 'rich',
        'httpx': 'httpx',
        'pydantic': 'pydantic',
        'yaml': 'pyyaml',
        'dotenv': 'python-dotenv',
    }
    missing = []
    for module, package in required.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if missing:
        print(f"Installing missing dependencies: {', '.join(missing)}...")
        try:
            # Try user install first (no sudo needed)
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--user', '--quiet'] + missing,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                # Fallback without --user
                result = subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', '--quiet'] + missing,
                    capture_output=True,
                    text=True
                )
            if result.returncode != 0:
                print(f"Warning: Could not auto-install. Run manually:")
                print(f"  pip install {' '.join(missing)}")
                sys.exit(1)
            print("Done. Starting Eversale...")
        except Exception as e:
            print(f"Warning: Auto-install failed ({e}). Run manually:")
            print(f"  pip install {' '.join(missing)}")
            sys.exit(1)

_auto_install_deps()
# =============================================================================

import asyncio
import functools
import json
import warnings
from datetime import datetime
from pathlib import Path
from typing import Optional

# Load .env file if it exists (for API keys like MOONSHOT_API_KEY)
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # dotenv not installed, rely on system env vars

# Suppress noisy warnings in production
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*pthread_create.*")
warnings.filterwarnings("ignore", message=".*ONNX.*")
warnings.filterwarnings("ignore", message=".*onnxruntime.*")

# Configure ChromaDB BEFORE any imports that might use it
# This prevents ONNX OOM errors and suppresses noisy output
os.environ.setdefault("ONNX_USE_GPU", "0")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("CHROMA_ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("ONNXRUNTIME_DISABLE_WARNING", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")  # Suppress TensorFlow logs
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")  # Suppress tokenizer warnings

sys.path.insert(0, str(Path(__file__).parent))

# Check debug mode early
_DEBUG_MODE = '--debug' in sys.argv or '-d' in sys.argv or os.environ.get('EVERSALE_DEBUG', '').lower() in ('1', 'true')

# Configure loguru BEFORE any agent imports
from loguru import logger
logger.remove()  # Remove default handler
Path("logs").mkdir(exist_ok=True)
logger.add("logs/eversale.log", rotation="10 MB", level="DEBUG")
if _DEBUG_MODE:
    logger.add(sys.stderr, level="DEBUG", format="<dim>{time:HH:mm:ss}</dim> | {message}")
# In production, no stderr logging - keep it clean for users
os.environ['EVERSALE_LOGGING_CONFIGURED'] = '1'  # Signal to submodules not to add handlers

# Suppress stderr noise during imports (only in production)
class _SuppressStderr:
    def __enter__(self):
        if not _DEBUG_MODE:
            self._stderr = sys.stderr
            sys.stderr = open(os.devnull, 'w')
        return self
    def __exit__(self, *args):
        if not _DEBUG_MODE:
            sys.stderr.close()
            sys.stderr = self._stderr

# IMPORTANT: Import bootstrap FIRST to run early initialization
# This auto-installs dependencies and builds Rust before other imports
from agent.bootstrap import (
    run_bootstrap, is_first_run, run_first_time_setup,
    quick_startup_check, show_example_prompts,
    ensure_curl_cffi, ensure_ollama_embedding_model, ensure_rust_core
)

# Run auto-setup for optional dependencies BEFORE importing modules that use them
with _SuppressStderr():
    ensure_curl_cffi()
    ensure_ollama_embedding_model()
    ensure_rust_core()  # Auto-build Rust if cargo is available

import yaml
from rich.panel import Panel
from rich.table import Table

from agent.brain_enhanced_v2 import create_enhanced_brain
from agent.mcp_client import MCPClient
from agent.ui import EversaleUI, ui, BRAND_PRIMARY, BRAND_SUCCESS, BRAND_DIM
from agent.startup_health_check import run_health_checks, quick_check
from agent.scheduler import TaskScheduler
from agent.mission_keeper import MissionKeeper
from agent.global_browser_pool import warmup_global_pool, shutdown_global_pool

# Use the early-checked debug mode
DEBUG_MODE = _DEBUG_MODE
if DEBUG_MODE:
    sys.argv = [a for a in sys.argv if a not in ('--debug', '-d')]

# Create brain factory
create_brain = create_enhanced_brain

CONFIG_PATH = Path("config/config.yaml")
TRAINING_LOG_PATH = Path("logs/training.log")
_training_logger_configured = False
BEST_METRICS_PATH = Path("training/best_metrics.json")

# Auto-restart marker - set when running via auto_restart.py
_RUNNING_VIA_AUTO_RESTART = os.environ.get('EVERSALE_AUTO_RESTART', '').lower() in ('1', 'true')

# Forever mode patterns for auto-restart detection
_FOREVER_PATTERNS = [
    r'\b(?:forever|indefinitely|infinitely)\b',
    r'\buntil\s+(?:i\s+)?(?:cancel|stop|quit)\b',
    r'\b(?:keep|run)\s+(?:going|running|checking)\b',
    r'\bnon[\-\s]?stop\b',
    r'\bcontinuously\b',
    r'\bevery\s+\d+\s*(?:minutes?|mins?|hours?|hrs?|days?)\b',
    r'\bevery\s+(?:day|hour|minute)\b',
    r'\b(?:daily|hourly)\b',
    r'\bfor\s+\d+(?:\.\d+)?\s*(?:hours?|h|days?|d)\b',
    r'\bmonitor\b.*\b(?:forever|continuously)\b',
    r'\b24/7\b',
]

def _should_auto_restart(prompt: str) -> bool:
    """Check if prompt requires forever mode and should use auto-restart."""
    if _RUNNING_VIA_AUTO_RESTART or os.environ.get('EVERSALE_NO_AUTO_RESTART', '').lower() == 'true':
        return False  # Already wrapped or disabled
    text = prompt.lower()
    import re
    return any(re.search(p, text) for p in _FOREVER_PATTERNS)


def _spawn_with_auto_restart(prompt: str) -> None:
    """Re-execute with auto_restart.py wrapper for crash resilience."""
    import subprocess
    auto_restart_path = Path(__file__).parent / "auto_restart.py"

    if not auto_restart_path.exists():
        logger.warning("auto_restart.py not found, running without restart wrapper")
        return None  # Continue without wrapper

    # Set marker so child process knows it's wrapped
    env = os.environ.copy()
    env['EVERSALE_AUTO_RESTART'] = '1'

    # Build command
    cmd = [sys.executable, str(auto_restart_path), prompt]

    logger.info(f"Spawning with auto-restart wrapper for forever mode task")
    print(f"\n[bold cyan]>>> 24/7 Mode: Auto-restart enabled for crash resilience[/bold cyan]")
    print(f"[dim]If the agent crashes, it will automatically restart[/dim]\n")

    # Replace current process with wrapped version
    try:
        result = subprocess.run(cmd, env=env)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n[yellow]>>> Stopped by user[/yellow]")
        sys.exit(0)


@functools.lru_cache(maxsize=1)
def _load_config() -> dict:
    """Load and cache configuration.

    Uses config_loader which handles:
    - Remote vs local LLM mode detection
    - Proper base_url for CLI users (eversale.io/api/llm)
    - Environment variable overrides
    """
    try:
        from agent.config_loader import load_config as loader_load_config
        return loader_load_config()
    except ImportError:
        # Fallback to direct YAML load if config_loader not available
        try:
            with open(CONFIG_PATH) as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {}


def _ensure_training_logger():
    """Add a dedicated file logger for training sessions."""
    global _training_logger_configured
    if _training_logger_configured:
        return

    TRAINING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(TRAINING_LOG_PATH),
        rotation="50 MB",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    )
    _training_logger_configured = True


def _load_best_metrics() -> dict:
    """Return the saved best training performance metrics."""
    try:
        with open(BEST_METRICS_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_best_metrics(data: dict):
    """Persist training metrics for future comparisons."""
    BEST_METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BEST_METRICS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def startup_checks() -> bool:
    """Run startup health checks. Returns True if OK to proceed."""
    # Quick check first (fast)
    ok, error = quick_check()
    if not ok:
        ui.show_error(error)
        return False
    return True


async def one_shot(prompt: str):
    """Execute single command with beautiful streaming output."""
    import time
    start_time = time.time()

    if not startup_checks():
        return

    config = _load_config()
    mcp = MCPClient()

    try:
        ui.show_startup_badge()

        with ui.thinking_sync("Initializing") as init_progress:
            # NEW: Start browser warmup in background FIRST (parallel with other init)
            init_progress.step("Warming up browser")
            warmup_task = asyncio.create_task(warmup_global_pool(
                size=1,
                headless=mcp._headless_override if mcp._headless_override is not None else True,
                enable_stealth=True,
                background=True  # Don't block - let it warmup in background
            ))

            init_progress.step("Connecting to browser")
            await mcp.connect_all_servers()
            init_progress.step("Loading AI model")
            brain = create_brain(config, mcp)
            # Start organism (the nervous system)
            if brain.organism:
                init_progress.step("Activating organism")
                await brain.organism.start()
                # Initialize SIAO core (9 cognitive components)
                await brain.init_siao_core()

            # Ensure browser is still healthy after organism init (can take minutes)
            # Browser might have gone stale during the long organism startup
            init_progress.step("Warming up browser")
            if brain.browser:
                try:
                    if not await brain.browser.is_healthy():
                        logger.info("Browser stale after organism init, reconnecting...")
                        await brain.browser.ensure_connected()
                except Exception as e:
                    logger.warning(f"Browser warmup failed: {e}, will reconnect on first use")

        ui.show_ready()

        # Main task execution with streaming progress
        with ui.thinking_sync("Working") as progress:
            brain.set_progress_callback(progress.get_callback())
            result = await brain.run(prompt)

        # Calculate elapsed time
        elapsed = time.time() - start_time

        # Show result with celebration
        ui.show_result(result)

        # Show stats if meaningful work was done
        stats = brain.get_stats()
        if stats.get('tool_calls', 0) > 0:
            ui.show_stats(stats)

        # Celebrate completion
        await ui.celebrate_completion(elapsed)

    except KeyboardInterrupt:
        ui.show_status("Interrupted", "warning")

    except Exception as e:
        ui.show_error(str(e))
        logger.exception("Task failed")

    finally:
        # Mark clean shutdown for one-shot mode
        try:
            if hasattr(brain, 'crash_recovery') and brain.crash_recovery:
                brain.crash_recovery.mark_clean_shutdown(reason="user_exit")
        except Exception:
            pass
        await mcp.disconnect_all_servers()
        # NEW: Shutdown global browser pool
        await shutdown_global_pool()


async def interactive():
    """Interactive mode with beautiful streaming UI."""
    import time
    import select

    # Check if stdin has piped input
    def has_piped_input():
        """Detect if stdin is a pipe or has data waiting."""
        if not sys.stdin.isatty():
            return True
        # Check if there's data waiting on stdin (Unix)
        try:
            return select.select([sys.stdin], [], [], 0.0)[0]
        except:
            return False

    # Detect piped input mode early
    is_piped = has_piped_input()

    # Show welcome only for interactive TTY sessions
    if not is_piped:
        await ui.show_welcome()

    # Then run health checks
    if not startup_checks():
        return

    config = _load_config()
    mcp = MCPClient()

    try:
        ui.show_startup_badge()

        with ui.thinking_sync("Initializing") as init_progress:
            # NEW: Start browser warmup in background FIRST
            init_progress.step("Warming up browser")
            warmup_task = asyncio.create_task(warmup_global_pool(
                size=1,
                headless=mcp._headless_override if mcp._headless_override is not None else True,
                enable_stealth=True,
                background=True
            ))

            init_progress.step("Connecting to browser")
            await mcp.connect_all_servers()
            init_progress.step("Loading AI model")
            brain = create_brain(config, mcp)
            # Start organism (the nervous system)
            if brain.organism:
                init_progress.step("Activating organism")
                await brain.organism.start()
                # Initialize SIAO core (9 cognitive components)
                await brain.init_siao_core()

            # Ensure browser is still healthy after organism init (can take minutes)
            # Browser might have gone stale during the long organism startup
            init_progress.step("Checking browser health")
            if brain.browser:
                try:
                    if not await brain.browser.is_healthy():
                        logger.info("Browser stale after organism init, reconnecting...")
                        await brain.browser.ensure_connected()
                except Exception as e:
                    logger.warning(f"Browser warmup failed: {e}, will reconnect on first use")

        ui.show_ready()

        # Show output folder location (only for TTY)
        if not is_piped:
            try:
                from agent.output_path import get_output_folder
                output_folder = get_output_folder()
                ui.console.print(f"[dim]Output folder:[/dim] [bold]{output_folder}[/bold]")
            except:
                pass

        scheduler = TaskScheduler(brain)
        keeper = MissionKeeper(scheduler)
        keeper.ensure_missions()

        # Only auto-resume if there was a CRASH, not a clean exit
        if brain.crash_recovery and brain.crash_recovery.was_crash():
            pending = brain.crash_recovery.pending_prompt()
            if pending:
                # Auto-resume crashed task without asking
                ui.show_status("Recovering from unexpected shutdown...", "warning")
                logger.info(f"Auto-resuming crashed task: {pending[:80]}")
                with ui.thinking_sync("Recovering mission") as thinking:
                    brain.set_progress_callback(thinking.get_callback())
                    recovery_result = await brain.run(pending)
                ui.show_result(recovery_result)
                ui.show_status("Crash recovery complete", "success")
        elif brain.crash_recovery:
            # Clean start - clear any stale state
            brain.crash_recovery.mark_session_start()

        print()

        while True:
            try:
                # Use piped input mode if stdin is not a TTY
                if is_piped:
                    prompt = ui.prompt_piped()
                else:
                    prompt = ui.prompt()
            except EOFError:
                # End of input (piped input finished or Ctrl+D)
                break
            except KeyboardInterrupt:
                break

            try:
                if not prompt.strip():
                    continue

                # Commands
                cmd = prompt.lower().strip()
                parts = cmd.split(maxsplit=1)
                command_name = parts[0] if parts else ""

                if cmd in ['exit', 'quit', 'q']:
                    break

                if cmd in ['help', '?', 'h']:
                    ui.show_help()
                    continue

                if cmd == 'about':
                    ui.show_about()
                    continue

                if cmd == 'check':
                    run_health_checks(verbose=True)
                    continue

                if cmd == 'stats':
                    ui.show_stats(brain.get_stats())
                    continue

                if cmd in ['system', 'sys']:
                    # Show system status
                    status = brain.get_system_status()
                    ui.console.print(f"\n[bold cyan]System Status[/bold cyan]")

                    # Dead Man's Switch
                    dms = status['dead_mans_switch']
                    dms_status = "[red]TRIGGERED[/red]" if dms['triggered'] else "[green]OK[/green]"
                    ui.console.print(f"\n  [bold]Dead Man's Switch:[/bold] {dms_status}")
                    ui.console.print(f"    Timeout: {dms['timeout_hours']:.1f}h")
                    ui.console.print(f"    Time remaining: {dms['time_remaining_hours']:.1f}h")
                    ui.console.print(f"    Last ping: {dms['last_ping']}")

                    # Resource Limits
                    res = status['resource_limits']
                    ui.console.print(f"\n  [bold]Resource Limits:[/bold]")
                    ui.console.print(f"    Memory: {res['memory_mb']:.0f}MB / {res['memory_limit_mb']}MB ({res['memory_percent']:.0f}%)")
                    ui.console.print(f"    CPU: {res['cpu_percent']:.0f}%")
                    ui.console.print(f"    Active tasks: {res['active_tasks']} / {res['max_concurrent_tasks']}")

                    # Multi-Instance
                    mi = status['multi_instance']
                    leader_str = "[yellow]LEADER[/yellow]" if mi['is_leader'] else "follower"
                    ui.console.print(f"\n  [bold]Multi-Instance:[/bold] {leader_str}")
                    ui.console.print(f"    Instance: {mi['instance_id']}")
                    ui.console.print(f"    Position: {mi['instance_index']+1} of {mi['total_instances']}")
                    ui.console.print(f"    Active instances: {', '.join(mi['active_instances'])}")

                    ui.console.print()
                    continue

                if cmd == 'status':
                    # Show SIAO organism dashboard
                    try:
                        from agent.siao_dashboard import create_dashboard
                        dashboard = create_dashboard(
                            organism=brain.organism if hasattr(brain, 'organism') else None,
                            siao_core=brain.siao_core if hasattr(brain, 'siao_core') else None
                        )
                        dashboard.print_status()
                    except ImportError:
                        ui.console.print("[dim]SIAO dashboard not available[/dim]")
                    except Exception as e:
                        ui.console.print(f"[dim]Dashboard error: {e}[/dim]")
                    continue

                if cmd == 'health':
                    # Run SIAO health checks
                    try:
                        from agent.siao_health import quick_health_check
                        report = await quick_health_check(
                            organism=brain.organism if hasattr(brain, 'organism') else None,
                            siao_core=brain.siao_core if hasattr(brain, 'siao_core') else None,
                            verbose=True
                        )
                    except ImportError:
                        ui.console.print("[dim]SIAO health checker not available[/dim]")
                    except Exception as e:
                        ui.console.print(f"[dim]Health check error: {e}[/dim]")
                    continue

                if cmd == 'components':
                    # List all SIAO components and their status
                    try:
                        from agent.siao_dashboard import create_dashboard
                        dashboard = create_dashboard(
                            organism=brain.organism if hasattr(brain, 'organism') else None,
                            siao_core=brain.siao_core if hasattr(brain, 'siao_core') else None
                        )
                        status = dashboard.get_status()
                        components = status.get("components", [])
                        ui.console.print(f"\n[bold cyan]SIAO Components[/bold cyan]\n")
                        for comp in components:
                            emoji = comp.get_emoji() if hasattr(comp, 'get_emoji') else "•"
                            name = comp.name if hasattr(comp, 'name') else str(comp.get('name', ''))
                            comp_status = comp.status if hasattr(comp, 'status') else comp.get('status', '')
                            message = comp.message if hasattr(comp, 'message') else comp.get('message', '')
                            ui.console.print(f"  {emoji} {name:<20} {comp_status:<10} {message}")
                        ui.console.print()
                    except ImportError:
                        ui.console.print("[dim]SIAO dashboard not available[/dim]")
                    except Exception as e:
                        ui.console.print(f"[dim]Components error: {e}[/dim]")
                    continue

                if cmd == 'valence':
                    # Show current valence
                    try:
                        if hasattr(brain, 'organism') and brain.organism:
                            if hasattr(brain.organism, 'valence'):
                                val = brain.organism.valence
                                ui.console.print(f"\n[bold cyan]Valence System[/bold cyan]")
                                ui.console.print(f"  Current valence: {val.get_valence():.2f}")
                                ui.console.print(f"  Mood: {val.get_mood()}")
                                motivation = val.get_motivation()
                                ui.console.print(f"  Strategy: {motivation.get('strategy', 'unknown')}")
                                ui.console.print()
                            else:
                                ui.console.print("[dim]Valence system not initialized[/dim]")
                        else:
                            ui.console.print("[dim]Organism not available[/dim]")
                    except Exception as e:
                        ui.console.print(f"[dim]Valence error: {e}[/dim]")
                    continue

                if cmd == 'sleep':
                    # Trigger manual sleep cycle
                    try:
                        if hasattr(brain, 'siao_core') and brain.siao_core:
                            ui.console.print("[cyan]Triggering sleep cycle...[/cyan]")
                            await brain.siao_core.force_sleep()
                            ui.console.print("[green]Sleep cycle complete[/green]\n")
                        elif hasattr(brain, 'organism') and brain.organism:
                            ui.console.print("[dim]Sleep cycle not available on base organism[/dim]")
                        else:
                            ui.console.print("[dim]Organism not available[/dim]")
                    except Exception as e:
                        ui.console.print(f"[dim]Sleep error: {e}[/dim]")
                    continue

                if cmd == 'diagnose':
                    # Full diagnostic report
                    try:
                        from agent.siao_health import SIAOHealthChecker
                        checker = SIAOHealthChecker()
                        checker.attach(
                            organism=brain.organism if hasattr(brain, 'organism') else None,
                            siao_core=brain.siao_core if hasattr(brain, 'siao_core') else None
                        )
                        report = await checker.check_all()
                        checker.print_report(report, verbose=True)

                        # Also run systemic diagnosis
                        systemic_issues = checker.diagnose_issues(report)
                        if systemic_issues:
                            ui.console.print("\n[bold yellow]Systemic Issues Detected:[/bold yellow]")
                            for issue in systemic_issues:
                                ui.console.print(f"  [{issue.severity}] {issue.component}: {issue.message}")
                                if issue.suggestion:
                                    ui.console.print(f"      Suggestion: {issue.suggestion}")
                            ui.console.print()
                    except ImportError:
                        ui.console.print("[dim]SIAO health checker not available[/dim]")
                    except Exception as e:
                        ui.console.print(f"[dim]Diagnose error: {e}[/dim]")
                    continue

                if cmd == 'memory':
                    from agent.brain_enhanced_v2 import Memory
                    mem = Memory.load()

                    if mem.domain_strategies:
                        ui.console.print(f"\n[bold cyan]Learned Strategies[/bold cyan]")
                        for domain, strategies in mem.domain_strategies.items():
                            ui.console.print(f"  [yellow]{domain}[/yellow]: {len(strategies)} strategies")
                    else:
                        ui.console.print("[dim]No strategies learned yet[/dim]")
                    ui.console.print()
                    continue

                if cmd in ['clear', 'cls']:
                    ui.console.clear()
                    await ui.show_logo(animate=False)
                    continue

                if cmd == 'logo':
                    await ui.show_logo(animate=True)
                    continue

                if cmd == 'examples':
                    show_example_prompts()
                    continue

                if command_name == 'train':
                    hours = _parse_training_duration(parts[1] if len(parts) > 1 else None)
                    await _run_training_session(hours, config=config)
                    continue

                # Model/AI questions - keep it proprietary
                model_questions = ['what model', 'what ai', 'what llm', 'which model',
                                   'which ai', 'which llm', 'powered by', 'what powers',
                                   'what are you', 'who are you', 'what is this']
                if any(q in cmd for q in model_questions):
                    ui.show_about()
                    continue

                # Schedule commands
                if cmd.startswith('schedule'):
                    await handle_schedule(prompt, brain)
                    continue

                # Login commands
                if cmd == 'login' or cmd.startswith('login '):
                    parts = cmd.split(maxsplit=1)
                    service = parts[1] if len(parts) > 1 else None
                    await handle_login(service, mcp, brain)
                    continue

                if cmd in ['ready', 'done', 'logged in', 'continue', 'save login']:
                    await handle_login_done(mcp)
                    continue

                # Capability commands
                if cmd.startswith('cap'):
                    await handle_capability(prompt)
                    continue

                if cmd == 'capabilities':
                    await handle_capability('cap list')
                    continue

                # Execute task with streaming progress
                task_start = time.time()

                with ui.thinking_sync("Working") as progress:
                    brain.set_progress_callback(progress.get_callback())
                    result = await brain.run(prompt)

                task_elapsed = time.time() - task_start

                # Show result
                ui.show_result(result)

                # Check if result mentions saved files
                if result and ('saved' in result.lower() or 'output' in result.lower()):
                    import re
                    paths = re.findall(r'[/\\][\w/\\._-]+\.\w{2,4}', result)
                    if paths:
                        for path in paths[:3]:
                            ui.show_saved(path)

                # Quick stats for complex tasks
                stats = brain.get_stats()
                if stats.get('iterations', 0) > 1 or stats.get('tool_calls', 0) > 3:
                    ui.console.print(f"[dim]⚙ {stats.get('tool_calls', 0)} actions  •  {task_elapsed:.1f}s[/dim]\n")

            except KeyboardInterrupt:
                print()  # Clean newline
                break

            except Exception as e:
                from agent.errors import friendly_error
                title, message = friendly_error(e)
                ui.show_error(f"{title}\n\n{message}")
                logger.exception("Task failed")

    finally:
        # Clean shutdown - mark as clean exit so we don't resume next time
        try:
            logger.info("Shutting down brain components...")
            # Mark clean shutdown BEFORE brain.shutdown()
            if hasattr(brain, 'crash_recovery') and brain.crash_recovery:
                brain.crash_recovery.mark_clean_shutdown(reason="user_exit")
            brain.shutdown()
        except Exception:
            pass

        try:
            await mcp.disconnect_all_servers()
        except Exception:
            pass

        # NEW: Shutdown global browser pool
        await shutdown_global_pool()

        ui.console.print(f"\n[cyan]✦[/cyan] [dim]Goodbye![/dim]\n")


async def handle_schedule(prompt: str, brain):
    """Handle schedule commands."""
    from agent.scheduler import TaskScheduler

    scheduler = TaskScheduler(brain)
    parts = prompt.split(maxsplit=2)
    cmd = parts[1].lower() if len(parts) > 1 else "list"

    if cmd == "list":
        scheduler.list_tasks()

    elif cmd == "add" and len(parts) > 2:
        import shlex
        try:
            args = shlex.split(parts[2])
            if len(args) >= 2:
                schedule_str = args[0]
                task_prompt = args[1]
                name = task_prompt[:20].replace(" ", "_").lower()
                cron = scheduler.parse_schedule(schedule_str)
                scheduler.add_task(name, cron, task_prompt)
                ui.show_status(f"Added: {name} ({schedule_str})", "success")
            else:
                ui.show_error('Usage: schedule add "daily at 9am" "your task"')
        except Exception as e:
            ui.show_error(f"Parse error: {e}")

    elif cmd == "remove" and len(parts) > 2:
        name = parts[2]
        scheduler.remove_task(name)
        ui.show_status(f"Removed: {name}", "success")

    elif cmd == "start":
        ui.show_status("Starting scheduler daemon...", "info")
        print("[dim]Tasks will run on schedule. Press Ctrl+C to stop.[/dim]\n")
        await scheduler.start()

        try:
            while True:
                await asyncio.sleep(60)
        except KeyboardInterrupt:
            await scheduler.stop()
            ui.show_status("Scheduler stopped", "warning")

    elif cmd == "status":
        scheduler.show_status()

    else:
        print("[dim]Commands: schedule list | add | remove | start | status[/dim]")


async def handle_capability(prompt: str):
    """Handle direct capability commands."""
    from rich.table import Table
    from rich.panel import Panel
    from agent.capabilities import Capabilities

    caps = Capabilities()

    # Map of capability names to functions
    cap_map = {
        'a': ('Admin - Inbox Triage', caps.admin_triage_inbox, 'emails'),
        'b': ('Back-office - Spreadsheet Clean', caps.backoffice_clean_spreadsheet, 'file_path'),
        'c': ('CustOps - Ticket Classification', caps.custops_classify_tickets, 'tickets'),
        'd': ('Sales - Company Research', caps.sales_research_company, 'company_name'),
        'e': ('E-commerce - Product Description', caps.ecommerce_product_description, 'product_name'),
        'f': ('Real Estate - Report Summary', caps.realestate_summarize_report, 'report_path'),
        'g': ('Legal - Contract Extract', caps.legal_extract_contract, 'contract_path'),
        'h': ('Logistics - Shipping Summary', caps.logistics_shipping_summary, 'updates'),
        'i': ('Industrial - Maintenance Analysis', caps.industrial_maintenance_analysis, 'log_path'),
        'j': ('Finance - Transaction Categorize', caps.finance_categorize_transactions, 'file_path'),
        'k': ('Marketing - Analytics Insights', caps.marketing_analytics_insights, 'data'),
        'l': ('HR - Resume Comparison', caps.hr_compare_resumes, 'resume_paths'),
        'm': ('Education - Quiz Generator', caps.education_create_quiz, 'content_path'),
        'n': ('Government - Form Extract', caps.government_extract_form, 'form_path'),
        'o': ('IT - Log Summary', caps.it_summarize_logs, 'log_path'),
    }

    parts = prompt.split(maxsplit=2)
    cmd = parts[1].lower() if len(parts) > 1 else ""
    arg = parts[2] if len(parts) > 2 else ""

    if not cmd or cmd == 'list':
        # Show available capabilities
        table = Table(title="Business Capabilities", show_header=True)
        table.add_column("ID", style="bold cyan", width=3)
        table.add_column("Capability", style="white")
        table.add_column("Input", style="dim")

        for key, (name, _, input_type) in cap_map.items():
            table.add_row(key.upper(), name, f"<{input_type}>")

        ui.console.print(Panel(table, border_style="cyan"))
        ui.console.print("[dim]Usage: cap <id> <input>  (e.g., cap d Stripe)[/dim]\n")
        return

    if cmd in cap_map:
        name, func, input_type = cap_map[cmd]

        if not arg:
            ui.show_error(f"Missing argument: {input_type}")
            ui.console.print(f"[dim]Usage: cap {cmd} <{input_type}>[/dim]\n")
            return

        ui.show_status(f"Running: {name}", "info")

        try:
            with ui.thinking_sync("Processing"):
                # Handle special cases
                if cmd == 'l':  # Resume comparison needs list of paths
                    paths = arg.split(',')
                    result = func([p.strip() for p in paths])
                else:
                    result = func(arg)

            if result.success:
                ui.show_result(result.output)
                if result.files_created:
                    for f in result.files_created:
                        ui.show_saved(f)
            else:
                ui.show_error(result.error)

        except Exception as e:
            ui.show_error(f"Failed: {str(e)}")
    else:
        ui.show_error(f"Unknown capability: {cmd}")
        ui.console.print(f"[dim]Use 'cap list' to see available capabilities[/dim]\n")


async def handle_login(service: str, mcp, brain):
    """Handle login command - open browser for user to login."""
    from rich.table import Table
    from rich.panel import Panel

    # Service URLs
    services = {
        'gmail': ('https://mail.google.com', 'Gmail'),
        'google': ('https://accounts.google.com', 'Google'),
        'linkedin': ('https://www.linkedin.com/login', 'LinkedIn'),
        'twitter': ('https://twitter.com/login', 'Twitter/X'),
        'facebook': ('https://www.facebook.com/login', 'Facebook'),
        'outlook': ('https://outlook.live.com', 'Outlook'),
        'calendar': ('https://calendar.google.com', 'Google Calendar'),
    }

    if not service:
        # Show available services
        table = Table(title="Available Services", show_header=False, box=None)
        table.add_column(style="bold cyan", width=12)
        table.add_column(style="dim")

        for key, (url, name) in services.items():
            table.add_row(key, name)

        # Also show saved sessions
        try:
            browser = mcp._mcp_server.client if mcp._mcp_server else None
            if browser:
                saved = browser.get_saved_sessions()
                if saved:
                    table.add_row("", "")
                    table.add_row("[green]Saved:[/green]", ", ".join(saved))
        except Exception:
            pass

        ui.console.print(Panel(table, title="[bold]Login[/bold]", border_style="cyan"))
        ui.console.print("[dim]Usage: login <service>  (e.g., login gmail)[/dim]\n")
        return

    service = service.lower().strip()

    if service not in services:
        ui.show_error(f"Unknown service: {service}")
        ui.console.print(f"[dim]Available: {', '.join(services.keys())}[/dim]\n")
        return

    url, name = services[service]

    ui.show_status(f"Opening {name} for login...", "info")
    ui.console.print(f"[dim]Browser will open in visible mode. Log in, then type 'done' to save.[/dim]\n")

    # Store service for session saving
    mcp._pending_login_service = service

    # Force visible browser for login
    mcp.set_headless(False)

    try:
        # Get or reconnect browser with visible mode
        if mcp._mcp_server:
            await mcp._mcp_server.enter_login_mode(service)
        else:
            await mcp.disconnect_all_servers()
            await mcp.connect_all_servers()

        browser = mcp._mcp_server.client if mcp._mcp_server else None

        if browser:
            await browser.navigate(url)
            ui.show_status(f"Opened {name} - please log in", "success")
            ui.console.print(f"\n[bold]When done, type:[/bold] done\n")
            ui.console.print(f"[dim]Your login will be saved for future headless sessions.[/dim]\n")
        else:
            ui.show_error("Browser not available")

    except Exception as e:
        ui.show_error(f"Failed to open browser: {e}")


async def handle_login_done(mcp):
    """Save login session and return to headless mode."""
    try:
        service = getattr(mcp, '_pending_login_service', None)

        if mcp._mcp_server:
            result = await mcp._mcp_server.finish_login_mode(service)
            if result.get("status") == "success":
                ui.show_status(f"Login saved! Browser now running in headless mode.", "success")
                domain = result.get("domain", "session")
                ui.console.print(f"[dim]Session saved for: {domain}[/dim]\n")
            else:
                ui.show_error(result.get("message", "Failed to save login"))
        else:
            ui.show_status("Login confirmed!", "success")

        mcp._pending_login_service = None

    except Exception as e:
        ui.show_error(f"Failed to save login: {e}")


async def run_daemon():
    """Daemon mode - run scheduler forever."""
    await ui.show_logo(animate=False)
    ui.show_status("Daemon Mode", "info")

    config_path = Path("config/config.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    mcp = MCPClient()

    try:
        with ui.thinking_sync("Starting daemon") as init_progress:
            # NEW: Start browser warmup in background FIRST
            init_progress.step("Warming up browser")
            warmup_task = asyncio.create_task(warmup_global_pool(
                size=1,
                headless=True,
                background=True
            ))

            init_progress.step("Connecting to browser")
            await mcp.connect_all_servers()
            init_progress.step("Loading AI model")
            brain = create_brain(config, mcp)
            # Start organism (the nervous system)
            if brain.organism:
                init_progress.step("Activating organism")
                await brain.organism.start()
                # Initialize SIAO core (9 cognitive components)
                await brain.init_siao_core()

            # Ensure browser is still healthy after organism init (can take minutes)
            # Browser might have gone stale during the long organism startup
            init_progress.step("Checking browser health")
            if brain.browser:
                try:
                    if not await brain.browser.is_healthy():
                        logger.info("Browser stale after organism init, reconnecting...")
                        await brain.browser.ensure_connected()
                except Exception as e:
                    logger.warning(f"Browser warmup failed: {e}, will reconnect on first use")

        from agent.scheduler import TaskScheduler
        scheduler = TaskScheduler(brain)
        from agent.mission_keeper import MissionKeeper
        keeper = MissionKeeper(scheduler)
        keeper.ensure_missions()

        pending = brain.crash_recovery.pending_prompt()
        if pending:
            logger.info("Resuming crash prompt in daemon mode")
            with ui.thinking_sync("Recovering mission") as thinking:
                brain.set_progress_callback(thinking.get_callback())
                await brain.run(pending)

        scheduler.list_tasks()

        if not scheduler.tasks:
            ui.show_error("No scheduled tasks. Add some first:")
            print('[dim]  eversale schedule add "daily at 9am" "Build leads"[/dim]\n')
            return

        await scheduler.start()
        ui.show_status("Daemon running. Waiting for scheduled times...", "success")

        while True:
            await asyncio.sleep(60)
            from datetime import datetime
            if datetime.now().minute == 0:
                print(f"[dim]♥ Alive at {datetime.now().strftime('%H:%M')}[/dim]")

    except KeyboardInterrupt:
        ui.show_status("Stopping daemon...", "warning")
        await scheduler.stop()

    finally:
        # Clean shutdown - mark so we don't resume on next start
        if hasattr(brain, 'crash_recovery') and brain.crash_recovery:
            brain.crash_recovery.mark_clean_shutdown(reason="user_exit")

        # Shutdown organism
        if brain.organism:
            try:
                await brain.organism.stop()
            except Exception:
                pass
        await mcp.disconnect_all_servers()
        # NEW: Shutdown global browser pool
        await shutdown_global_pool()
        ui.show_status("Daemon stopped", "info")


async def run_diagnostic_command(cmd: str):
    """Run SIAO diagnostic commands from CLI (health, status, components, diagnose)."""
    config = _load_config()
    mcp = MCPClient()

    try:
        ui.show_startup_badge()

        with ui.thinking_sync("Initializing") as init_progress:
            # NEW: Start browser warmup in background FIRST
            init_progress.step("Warming up browser")
            warmup_task = asyncio.create_task(warmup_global_pool(
                size=1,
                headless=True,
                background=True
            ))

            init_progress.step("Connecting to browser")
            await mcp.connect_all_servers()
            init_progress.step("Loading AI model")
            brain = create_brain(config, mcp)
            if brain.organism:
                init_progress.step("Activating organism")
                await brain.organism.start()
                # Initialize SIAO core (9 cognitive components)
                await brain.init_siao_core()

            # Ensure browser is still healthy after organism init (can take minutes)
            # Browser might have gone stale during the long organism startup
            init_progress.step("Checking browser health")
            if brain.browser:
                try:
                    if not await brain.browser.is_healthy():
                        logger.info("Browser stale after organism init, reconnecting...")
                        await brain.browser.ensure_connected()
                except Exception as e:
                    logger.warning(f"Browser warmup failed: {e}, will reconnect on first use")

        ui.show_ready()

        if cmd == 'status':
            # Show SIAO organism dashboard
            try:
                from agent.siao_dashboard import create_dashboard
                dashboard = create_dashboard(
                    organism=brain.organism if hasattr(brain, 'organism') else None,
                    siao_core=brain.siao_core if hasattr(brain, 'siao_core') else None
                )
                dashboard.print_status()
            except ImportError:
                ui.console.print("[dim]SIAO dashboard not available[/dim]")
            except Exception as e:
                ui.console.print(f"[dim]Dashboard error: {e}[/dim]")

        elif cmd == 'health':
            # Run SIAO health checks
            try:
                from agent.siao_health import quick_health_check
                report = await quick_health_check(
                    organism=brain.organism if hasattr(brain, 'organism') else None,
                    siao_core=brain.siao_core if hasattr(brain, 'siao_core') else None,
                    verbose=True
                )
            except ImportError:
                ui.console.print("[dim]SIAO health checker not available[/dim]")
            except Exception as e:
                ui.console.print(f"[dim]Health check error: {e}[/dim]")

        elif cmd == 'components':
            # List all SIAO components and their status
            try:
                from agent.siao_dashboard import create_dashboard
                dashboard = create_dashboard(
                    organism=brain.organism if hasattr(brain, 'organism') else None,
                    siao_core=brain.siao_core if hasattr(brain, 'siao_core') else None
                )
                status = dashboard.get_status()
                components = status.get("components", [])
                ui.console.print(f"\n[bold cyan]SIAO Components[/bold cyan]\n")
                for comp in components:
                    emoji = comp.get_emoji() if hasattr(comp, 'get_emoji') else "•"
                    name = comp.name if hasattr(comp, 'name') else str(comp.get('name', ''))
                    comp_status = comp.status if hasattr(comp, 'status') else comp.get('status', '')
                    message = comp.message if hasattr(comp, 'message') else comp.get('message', '')
                    ui.console.print(f"  {emoji} {name:<20} {comp_status:<10} {message}")
                ui.console.print()
            except ImportError:
                ui.console.print("[dim]SIAO dashboard not available[/dim]")
            except Exception as e:
                ui.console.print(f"[dim]Components error: {e}[/dim]")

        elif cmd == 'diagnose':
            # Full diagnostic report
            try:
                from agent.siao_health import SIAOHealthChecker
                checker = SIAOHealthChecker()
                checker.attach(
                    organism=brain.organism if hasattr(brain, 'organism') else None,
                    siao_core=brain.siao_core if hasattr(brain, 'siao_core') else None
                )
                report = await checker.check_all()
                checker.print_report(report, verbose=True)

                # Also run systemic diagnosis
                systemic_issues = checker.diagnose_issues(report)
                if systemic_issues:
                    ui.console.print("\n[bold yellow]Systemic Issues Detected:[/bold yellow]")
                    for issue in systemic_issues:
                        ui.console.print(f"  [{issue.severity}] {issue.component}: {issue.message}")
                        if issue.suggestion:
                            ui.console.print(f"      Suggestion: {issue.suggestion}")
                    ui.console.print()
            except ImportError:
                ui.console.print("[dim]SIAO health checker not available[/dim]")
            except Exception as e:
                ui.console.print(f"[dim]Diagnose error: {e}[/dim]")

    except KeyboardInterrupt:
        ui.show_status("Interrupted", "warning")

    except Exception as e:
        ui.show_error(str(e))
        logger.exception("Diagnostic command failed")

    finally:
        try:
            if hasattr(brain, 'crash_recovery') and brain.crash_recovery:
                brain.crash_recovery.mark_clean_shutdown(reason="diagnostic")
        except Exception:
            pass
        await mcp.disconnect_all_servers()
        # NEW: Shutdown global browser pool
        await shutdown_global_pool()


async def _run_training_session(hours: float, config: Optional[dict] = None):
    """Start a self-play training session for the given duration."""
    config = config or _load_config()
    training_conf = config.get("training", {})
    batch_size = training_conf.get("batch_size", 5)
    curriculum = training_conf.get("curriculum_learning", True)
    headless = training_conf.get("headless", True)

    _ensure_training_logger()

    ui.console.print(Panel(
        f"[bold cyan]Training protocol[/bold cyan]\n"
        f"Duration: [bold green]{hours}h[/bold green]\n"
        f"Batch size: [bold]{batch_size}[/bold]\n"
        f"Curriculum: [bold]{'✔️' if curriculum else '✗'}[/bold]\n"
        f"Headless browser: [bold]{'Yes' if headless else 'No'}[/bold]",
        title="◈ TRAINING",
        border_style="cyan"
    ))

    from training.self_play_engine import SelfPlayEngine

    engine = SelfPlayEngine()
    session = None

    try:
        with ui.thinking_sync("Training in progress"):
            session = await engine.run_training(
                duration_hours=hours,
                batch_size=batch_size,
                curriculum=curriculum,
                headless=headless
            )

    except KeyboardInterrupt:
        ui.show_status("Training interrupted; progress saved", "warning")
        return

    except Exception as exc:
        ui.show_error(f"Training failed: {exc}")
        logger.exception("Training session failed")
        return

    if not session:
        ui.show_status("Training session completed with no report", "warning")
        return

    success_rate = (session.tasks_successful / session.tasks_completed * 100) if session.tasks_completed else 0.0

    summary = Table(title="Training Summary", border_style="green")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", style="green")
    summary.add_row("Duration", f"{session.target_duration_hours} hours")
    summary.add_row("Tasks Completed", str(session.tasks_completed))
    summary.add_row("Success Rate", f"{success_rate:.1f}%")
    summary.add_row("New Strategies", str(session.strategies_learned))
    summary.add_row("Playbook Size", str(len(engine.playbook.strategies)))
    summary.add_row("Session ID", session.session_id)

    ui.console.print(summary)
    ui.console.print(f"[dim]Training log: {TRAINING_LOG_PATH}[/dim]")
    best_metrics = _load_best_metrics()
    prev_best = best_metrics.get("success_rate", 0.0)
    timestamp = datetime.now().isoformat()

    if success_rate > prev_best:
        new_best = {
            "success_rate": success_rate,
            "duration_hours": hours,
            "tasks_completed": session.tasks_completed,
            "strategies_learned": session.strategies_learned,
            "session_id": session.session_id,
            "updated_at": timestamp
        }
        _save_best_metrics(new_best)
        ui.console.print(f"[bold green]New best training run: {success_rate:.1f}% success_rate (prev {prev_best:.1f}%). Auto-updated playbook with the strongest strategies.[/bold green]")
        ui.show_status("Playbook auto-updated with best training run", "success")
    else:
        ui.console.print(f"[dim]Best success rate remains {prev_best:.1f}% (this run: {success_rate:.1f}%).[/dim]")
        ui.show_status("Training finished (playbook unchanged)", "info")


def _parse_training_duration(arg: Optional[str]) -> float:
    """Convert a duration string like '3h' or '180m' into hours."""
    hours = 3.0
    if not arg:
        return hours

    try:
        time_str = arg.lower()
        if 'h' in time_str:
            hours = float(time_str.replace('h', ''))
        elif 'm' in time_str:
            hours = float(time_str.replace('m', '')) / 60
        else:
            hours = float(time_str)
    except Exception:
        pass

    return hours


async def main():
    # Bootstrap: First-run setup or quick check
    if is_first_run():
        if not run_first_time_setup():
            return  # Setup failed
    else:
        quick_startup_check()  # Just ensure dirs/configs exist

    # Check for --interactive or -i flag (can work with piped input)
    if '--interactive' in sys.argv or '-i' in sys.argv:
        # Remove the flag from argv
        sys.argv = [a for a in sys.argv if a not in ('--interactive', '-i')]
        # Force interactive mode even with piped input
        await interactive()
        return

    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()

        if arg in ['help', '-h', '--help', '?']:
            ui.show_help()
            return

        if arg == 'setup':
            # Force re-run setup
            run_bootstrap(verbose=True)
            return

        if arg == 'examples':
            show_example_prompts()
            return

        if arg == 'train':
            hours = _parse_training_duration(sys.argv[2] if len(sys.argv) > 2 else None)
            await _run_training_session(hours)
            return

        if arg == 'schedule':
            if len(sys.argv) > 2 and sys.argv[2].lower() in ['start', 'daemon']:
                await run_daemon()
            else:
                # Show schedule help
                print("\n[bold]Schedule Commands:[/bold]")
                print('  eversale schedule list')
                print('  eversale schedule add "daily at 9am" "Build leads"')
                print('  eversale schedule remove <name>')
                print('  eversale schedule start  (daemon mode)\n')
            return

        if arg == 'version':
            print("Eversale v2.1")
            return

        if arg == 'check':
            run_health_checks(verbose=True)
            return

        # Health monitoring check (continuous monitoring status)
        if arg in ['health-check', '--health-check']:
            # Check agent health monitoring status
            from agent.health_check import check_health_cli
            exit_code = check_health_cli()
            sys.exit(exit_code)
            return

        # SIAO diagnostic commands (health, status, components, diagnose)
        if arg in ['health', 'status', 'components', 'diagnose']:
            await run_diagnostic_command(arg)
            return

        if arg == 'mcp-test':
            # Test MCP server tools locally
            from agent.mcp_server import test_server
            await test_server()
            return

        if arg in ['mcp', 'mcp-server', 'server']:
            # Run as EXTERNAL MCP server (for Claude Desktop integration)
            # Note: Internal MCP server is ALWAYS running when eversale starts
            from agent.mcp_server import EversaleMCPServer
            print("Starting Eversale as external MCP Server (stdio mode)...", file=sys.stderr)
            print("For Claude Desktop, add to claude_desktop_config.json:", file=sys.stderr)
            print('  "eversale": {"command": "python", "args": ["run_ultimate.py", "mcp"]}', file=sys.stderr)
            server = EversaleMCPServer(headless="--headless" in sys.argv)
            await server.run_stdio()
            return

        if arg == 'activate':
            # License activation command
            from agent.license_validator import activate_license
            if len(sys.argv) < 3:
                ui.console.print("[red]Usage: eversale activate <license_key>[/red]")
                return
            key = sys.argv[2]
            success, message = activate_license(key)
            if success:
                ui.console.print(f"[green]✓ {message}[/green]")
            else:
                ui.console.print(f"[red]✗ {message}[/red]")
            return

        if arg == 'deactivate':
            # License deactivation command
            from agent.license_validator import deactivate_license
            deactivate_license()
            ui.console.print("[yellow]License deactivated[/yellow]")
            return

        # One-shot mode
        prompt = " ".join(sys.argv[1:])

        # AUTO-RESTART: Detect forever mode and wrap with restart handler
        # This makes 24/7 operation transparent - no manual wrapper needed
        if _should_auto_restart(prompt):
            _spawn_with_auto_restart(prompt)
            return  # Never reached - subprocess.run exits

        await one_shot(prompt)
        sys.exit(0)

    else:
        # Interactive mode
        await interactive()


def _run_with_clean_shutdown():
    """Run main with clean shutdown handling for asyncio subprocess cleanup."""
    import warnings
    import signal
    import logging

    # Suppress asyncio cleanup warnings
    warnings.filterwarnings("ignore", message=".*Event loop is closed.*")
    warnings.filterwarnings("ignore", category=ResourceWarning)
    warnings.filterwarnings("ignore", message=".*BrokenPipeError.*")
    warnings.filterwarnings("ignore", message=".*Broken pipe.*")

    # Suppress asyncio Future exception messages during shutdown
    logging.getLogger('asyncio').setLevel(logging.CRITICAL)

    # Track if we're shutting down
    shutting_down = False

    # Custom exception handler to suppress shutdown noise
    def quiet_exception_handler(loop, context):
        # Ignore BrokenPipeError and ConnectionResetError during shutdown
        exception = context.get('exception')
        if shutting_down:
            return  # Suppress all errors during shutdown
        if exception:
            if isinstance(exception, (BrokenPipeError, ConnectionResetError, OSError)):
                return  # Suppress pipe errors silently
        # Log other unexpected errors
        logger.debug(f"Async exception: {context.get('message', 'Unknown')}")

    def handle_sigint(sig, frame):
        nonlocal shutting_down
        if shutting_down:
            # Second Ctrl+C - force exit
            print("\n")
            os._exit(0)
        shutting_down = True
        raise KeyboardInterrupt()

    # Set up clean signal handler
    signal.signal(signal.SIGINT, handle_sigint)

    loop = None
    try:
        # Get or create event loop and set custom exception handler
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_exception_handler(quiet_exception_handler)
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        # Clean exit - message already shown in interactive()
        shutting_down = True
    except SystemExit:
        pass
    except Exception as e:
        if not shutting_down:
            logger.exception("Fatal error")
            print(f"\n[red]Error: {e}[/red]")
            print("[dim]Check logs/eversale.log for details[/dim]\n")
            sys.exit(1)
    finally:
        # Clean up the loop quietly
        shutting_down = True
        if loop:
            try:
                # Cancel all pending tasks
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                # Give tasks a moment to cancel
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass


if __name__ == "__main__":
    _run_with_clean_shutdown()
