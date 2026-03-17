"""
Bootstrap - First-run setup and startup checks.

Ensures everything is ready before Eversale starts:
- Creates required directories
- Generates default configs
- Checks dependencies
- Validates browser installation
- Tests network connectivity
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple

# Fix Windows console encoding for Unicode symbols (✓, ✗, etc.)
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, TypeError):
        pass  # Python < 3.7 or already configured

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console(force_terminal=True)

# ============================================================================
# EARLY INITIALIZATION (runs on import)
# Configure environment variables BEFORE any other modules are imported
# ============================================================================

# Configure ChromaDB to avoid ONNX OOM errors
os.environ.setdefault("ONNX_USE_GPU", "0")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("CHROMA_ANONYMIZED_TELEMETRY", "false")

# Required directories
REQUIRED_DIRS = [
    "config",
    "memory",
    "logs",
    "coordination",
    "coordination/instances",
    "coordination/locks",
    "coordination/work",
    "coordination/results",
    "output",
    "data",
]

# Default config files
DEFAULT_CONFIGS = {
    "config/dead_mans_switch.yaml": """# Dead Man's Switch Configuration
timeout_hours: 4.0
fallback_tasks:
  - "Log system status and send diagnostic report"
""",
    "config/resources.yaml": """# Resource Limits Configuration
max_memory_mb: 2048
max_task_minutes: 120
max_total_memory_mb: 4096
max_concurrent_tasks: 3
cpu_throttle_percent: 80
check_interval_seconds: 5.0
kill_on_exceed: true
warn_threshold_percent: 0.8
""",
    "config/schedule.yaml": """# Scheduled Tasks
# Add your recurring tasks here
scheduled_tasks: []
""",
    "config/missions.yaml": """# Persistent Missions
# These tasks auto-reload on startup
missions: []
""",
}


def ensure_directories() -> List[str]:
    """Create all required directories. Returns list of created dirs."""
    created = []
    for dir_path in REQUIRED_DIRS:
        path = Path(dir_path)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(dir_path)
    return created


def ensure_configs() -> List[str]:
    """Create default config files if missing. Returns list of created files."""
    created = []
    for file_path, content in DEFAULT_CONFIGS.items():
        path = Path(file_path)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            created.append(file_path)
    return created


def check_python_version() -> Tuple[bool, str]:
    """Check Python version is 3.10+."""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 10:
        return True, f"Python {version.major}.{version.minor}.{version.micro}"
    return False, f"Python {version.major}.{version.minor} (need 3.10+)"


def ensure_ollama_embedding_model(model: str = "nomic-embed-text") -> bool:
    """
    Ensure the Ollama embedding model is available.
    Auto-pulls if missing. Returns True if model is ready.
    """
    try:
        import ollama
    except ImportError:
        return False

    try:
        # Check if model exists by trying to list it
        models_response = ollama.list()
        # Handle both dict and object response formats
        if hasattr(models_response, 'models'):
            models = models_response.models
        else:
            models = models_response.get('models', [])

        # Extract model names - handle both dict and object formats
        model_names = []
        for m in models:
            if hasattr(m, 'model'):
                model_names.append(m.model)  # Object format
            elif isinstance(m, dict):
                model_names.append(m.get('name', ''))  # Dict format

        # Check if model is already installed (with or without :latest tag)
        for name in model_names:
            if name.startswith(model):
                return True  # Model already installed

        # Model not found, try to pull it
        console.print(f"[dim]Pulling embedding model '{model}'...[/dim]")
        ollama.pull(model)
        console.print(f"[green]✓[/green] Embedding model '{model}' ready")
        return True

    except Exception as e:
        # Silently fail - will use fallback embedding
        return False


def ensure_curl_cffi() -> bool:
    """
    Check if curl_cffi is installed, auto-install if missing.
    Returns True if available.
    """
    try:
        import curl_cffi
        return True
    except ImportError:
        pass

    # Try to auto-install
    try:
        console.print("[dim]Installing curl_cffi for TLS fingerprinting...[/dim]")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "curl_cffi", "-q"],
            capture_output=True,
            timeout=120
        )
        if result.returncode == 0:
            console.print("[green]✓[/green] curl_cffi installed")
            return True
    except Exception:
        pass

    return False


def configure_chromadb_for_low_memory() -> None:
    """
    Configure ChromaDB to avoid ONNX OOM issues.
    Sets environment variables before ChromaDB is imported.
    """
    # Disable ONNX GPU to prevent OOM on systems without proper GPU support
    os.environ.setdefault("ONNX_USE_GPU", "0")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    # Use smaller batch size for embeddings
    os.environ.setdefault("CHROMA_ANONYMIZED_TELEMETRY", "false")


def ensure_rust_core() -> bool:
    """
    Check if Rust core library is available, auto-build if possible.
    Returns True if available.
    """
    # Check if already available
    try:
        import eversale_core
        return True
    except ImportError:
        pass

    # Check if we have cargo
    rust_core_dir = Path(__file__).parent.parent / "rust" / "core"
    if not rust_core_dir.exists():
        return False

    # Check for cargo
    try:
        result = subprocess.run(
            ["cargo", "--version"],
            capture_output=True,
            timeout=10
        )
        if result.returncode != 0:
            return False
    except Exception:
        return False

    # Check/install maturin
    try:
        result = subprocess.run(
            [sys.executable, "-m", "maturin", "--version"],
            capture_output=True,
            timeout=10
        )
        if result.returncode != 0:
            raise ImportError()
    except Exception:
        try:
            console.print("[dim]Installing maturin for Rust build...[/dim]")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "maturin", "-q"],
                capture_output=True,
                timeout=120
            )
            if result.returncode != 0:
                return False
        except Exception:
            return False

    # Build Rust core library using maturin build + pip install
    # This avoids virtualenv requirements of 'maturin develop'
    try:
        console.print("[dim]Building Rust core library (this may take a minute)...[/dim]")

        # Build the wheel
        dist_dir = rust_core_dir / "dist"
        result = subprocess.run(
            [sys.executable, "-m", "maturin", "build", "--release", "-o", str(dist_dir),
             "-m", str(rust_core_dir / "Cargo.toml")],
            capture_output=True,
            timeout=300  # 5 minutes max
        )

        # Check if wheel was created (warnings in stderr are OK)
        wheels = list(dist_dir.glob("eversale_core*.whl")) if dist_dir.exists() else []

        if result.returncode != 0 and not wheels:
            error_msg = result.stderr.decode()[:200] if result.stderr else "Unknown error"
            console.print(f"[dim]Rust build skipped: {error_msg}[/dim]")
            return False

        if not wheels:
            console.print("[dim]Rust build: wheel not found[/dim]")
            return False

        # Install the wheel (use newest one)
        wheel_path = str(sorted(wheels, key=lambda w: w.stat().st_mtime, reverse=True)[0])
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", wheel_path, "--force-reinstall", "-q"],
            capture_output=True,
            timeout=60
        )
        if result.returncode == 0:
            console.print("[green]✓[/green] Rust core library built and installed")
            return True

        console.print("[dim]Rust wheel install failed[/dim]")
        return False

    except subprocess.TimeoutExpired:
        console.print("[dim]Rust build timed out, skipping[/dim]")
        return False
    except Exception as e:
        console.print(f"[dim]Rust build failed: {e}[/dim]")
        return False


def check_required_packages() -> List[Tuple[str, bool, str]]:
    """Check required packages are installed."""
    # (pip_name, import_name, description)
    packages = [
        ("rich", "rich", "Beautiful CLI output"),
        ("loguru", "loguru", "Logging"),
        ("pyyaml", "yaml", "Config files"),
        ("playwright", "playwright", "Browser automation"),
        ("apscheduler", "apscheduler", "Task scheduling"),
    ]

    results = []
    for pip_name, import_name, description in packages:
        try:
            __import__(import_name)
            results.append((pip_name, True, description))
        except ImportError:
            results.append((pip_name, False, description))

    return results


def check_optional_packages() -> List[Tuple[str, bool, str]]:
    """Check optional packages."""
    packages = [
        ("psutil", "Resource monitoring"),
        ("chromadb", "Vector memory"),
        ("ollama", "Local LLM"),
    ]

    results = []
    for package, description in packages:
        try:
            __import__(package)
            results.append((package, True, description))
        except ImportError:
            results.append((package, False, description))

    return results


def check_playwright_browsers() -> Tuple[bool, str]:
    """Check if Playwright browsers are installed."""
    try:
        from playwright.sync_api import sync_playwright
        # Just check if we can import - actual browser check is expensive
        return True, "Playwright ready"
    except ImportError:
        return False, "Playwright not installed"
    except Exception as e:
        return False, f"Playwright error: {e}"


def check_network() -> Tuple[bool, str]:
    """Quick network connectivity check."""
    import socket
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True, "Network OK"
    except OSError:
        return False, "No internet connection"


def is_first_run() -> bool:
    """Check if this is the first run."""
    marker = Path("memory/.initialized")
    return not marker.exists()


def mark_initialized():
    """Mark that first-run setup is complete."""
    marker = Path("memory/.initialized")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("initialized")


def run_bootstrap(verbose: bool = True, skip_browser_check: bool = False) -> bool:
    """
    Run all bootstrap checks and setup.

    Returns True if everything is ready, False if critical issues found.
    """
    issues = []
    warnings = []

    # 1. Create directories
    created_dirs = ensure_directories()
    if created_dirs and verbose:
        console.print(f"[dim]Created directories: {', '.join(created_dirs)}[/dim]")

    # 2. Create default configs
    created_configs = ensure_configs()
    if created_configs and verbose:
        console.print(f"[dim]Created configs: {', '.join(created_configs)}[/dim]")

    # 3. Check Python version
    py_ok, py_msg = check_python_version()
    if not py_ok:
        issues.append(f"Python version: {py_msg}")

    # 4. Check required packages
    required = check_required_packages()
    for pkg, ok, desc in required:
        if not ok:
            issues.append(f"Missing package: {pkg} ({desc}) - pip install {pkg}")

    # 5. Check optional packages
    optional = check_optional_packages()
    for pkg, ok, desc in optional:
        if not ok:
            warnings.append(f"Optional: {pkg} ({desc})")

    # 6. Check Playwright (skip if requested - it's slow)
    if not skip_browser_check:
        pw_ok, pw_msg = check_playwright_browsers()
        if not pw_ok:
            warnings.append(f"Browser: {pw_msg} - run: playwright install chromium")

    # 7. Check network
    net_ok, net_msg = check_network()
    if not net_ok:
        warnings.append(f"Network: {net_msg}")

    # Report issues
    if issues:
        console.print("\n[bold red]Setup Issues:[/bold red]")
        for issue in issues:
            console.print(f"  [red]✗[/red] {issue}")
        return False

    if warnings and verbose:
        console.print("\n[yellow]Warnings (non-critical):[/yellow]")
        for warning in warnings:
            console.print(f"  [yellow]![/yellow] {warning}")

    return True


def show_first_run_welcome():
    """Show minimal welcome message for first-time users."""
    welcome = """[bold cyan]Welcome to Eversale[/bold cyan]

AI agent that automates browser tasks. Uses your logged-in sessions.

[bold]Quick start:[/bold]
  eversale "Research Stripe"
  eversale "Find leads from FB Ads for 'CRM'"

[dim]Type [bold]help[/bold] for commands, [bold]examples[/bold] for more prompts[/dim]

[dim]Press Enter to continue...[/dim]"""
    console.print(Panel(welcome, title="[bold]Setup[/bold]", border_style="cyan"))


def show_example_prompts():
    """Show example prompts to help users get started."""
    examples = [
        # Core workflows
        ("Sales/SDR", "Find leads from Facebook Ads for 'CRM software'", "Extract advertisers & contacts"),
        ("Research", "Research <company name>", "Deep company analysis"),
        ("Operations", "Triage my inbox and draft replies", "Email processing"),
        ("Finance", "Categorize these transactions", "Auto-categorization"),
        ("Support", "Classify tickets and draft responses", "Customer ops"),
        ("HR", "Compare resumes for Python developer", "Candidate scoring"),
        ("Legal", "Extract parties and terms from contract", "Contract analysis"),
        ("Marketing", "Analyze my Google Analytics traffic", "Traffic insights"),
        ("E-commerce", "Research book prices on books.toscrape.com", "Product research"),
        ("Education", "Create quiz about photosynthesis", "Quiz generation"),
        # Scheduling
        ("Forever", "Monitor inbox forever", "Runs until stopped"),
        ("Interval", "Check every 30 minutes", "Repeat on schedule"),
        ("Recurring", "Build leads every Friday at 3pm", "Weekly task"),
        ("Timed", "Research for 2 hours", "Set duration"),
    ]

    table = Table(title="Example Prompts - 31 Industries", show_header=True, header_style="bold cyan")
    table.add_column("Category", style="cyan", width=12)
    table.add_column("Example Prompt", style="white", width=42)
    table.add_column("What It Does", style="dim", width=22)

    for type_, example, desc in examples:
        table.add_row(type_, example, desc)

    console.print(table)
    console.print()


def run_first_time_setup():
    """Complete first-time setup experience."""
    console.clear()

    # Show welcome
    show_first_run_welcome()

    try:
        input()  # Wait for Enter
    except (EOFError, KeyboardInterrupt):
        pass

    console.clear()
    console.print("[bold]Running setup checks...[/bold]\n")

    # Run bootstrap
    success = run_bootstrap(verbose=True, skip_browser_check=False)

    if success:
        console.print("\n[bold green]✓ Setup complete![/bold green]\n")
        show_example_prompts()
        mark_initialized()
    else:
        console.print("\n[bold red]Please fix the issues above and try again.[/bold red]")
        console.print("[dim]Most issues can be fixed with: pip install -r requirements.txt[/dim]\n")

    return success


def quick_startup_check() -> bool:
    """Quick startup check for returning users (no verbose output)."""
    ensure_directories()
    ensure_configs()
    # Note: curl_cffi and ollama embedding model setup runs at import time
    # in run_ultimate.py, before other modules are loaded
    return True
