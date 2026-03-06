"""
Startup health checks for Eversale.
Ensures all dependencies are ready before running.
"""

import subprocess
import sys
from pathlib import Path
from typing import Tuple, List
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def check_ollama_running() -> Tuple[bool, str]:
    """Check if Ollama service is running."""
    import os
    # Bypass if using remote GPU LLM
    if os.environ.get('GPU_LLM_URL') or os.environ.get('EVERSALE_LLM_URL'):
        return True, "Using remote GPU LLM (local Ollama check skipped)"
        
    # Check config file too
    try:
        import yaml
        config_path = Path("config/config.yaml")
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
                if config.get('llm', {}).get('base_url'):
                    return True, "Using configured remote LLM (local Ollama check skipped)"
    except Exception:
        pass

    try:
        import ollama
        # Try to list models - this will fail if Ollama isn't running
        models = ollama.list()
        return True, f"{len(models.get('models', []))} models available"
    except Exception as e:
        error = str(e).lower()
        if "connection refused" in error or "connect" in error:
            return False, "Ollama is not running. Start it with: ollama serve"
        return False, f"Ollama error: {e}"


def check_required_models() -> Tuple[bool, str]:
    """Check if required models are installed."""
    import os
    # Bypass if using remote GPU LLM (assume remote has models)
    if os.environ.get('GPU_LLM_URL') or os.environ.get('EVERSALE_LLM_URL'):
        return True, "Remote GPU models assumed ready"
        
    # Check config file too
    try:
        import yaml
        config_path = Path("config/config.yaml")
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
                if config.get('llm', {}).get('base_url'):
                     return True, "configured remote LLM models assumed ready"
    except Exception:
        pass

    try:
        import ollama
        result = ollama.list()

        # Handle both dict and object responses
        if hasattr(result, 'models'):
            models = result.models
            model_names = [getattr(m, 'model', '') for m in models]
        else:
            models = result.get('models', [])
            model_names = [m.get('name', '') if isinstance(m, dict) else getattr(m, 'model', '') for m in models]

        model_str = ' '.join(model_names).lower()

        # We need 0000/ui-tars-1.5-7b:latest as the primary model
        has_uitars = 'ui-tars' in model_str or 'uitars' in model_str

        if not has_uitars:
            return False, "0000/ui-tars-1.5-7b:latest not found. Run: ollama pull 0000/ui-tars-1.5-7b:latest"

        # Check for vision model (required for full functionality)
        has_vision = 'moondream' in model_str

        if has_vision:
            return True, "0000/ui-tars-1.5-7b:latest + moondream ready"
        else:
            return True, "0000/ui-tars-1.5-7b:latest ready (vision optional: ollama pull moondream:latest)"

    except Exception as e:
        return False, f"Cannot check models: {e}"


def check_playwright() -> Tuple[bool, str]:
    """Check if Playwright browsers are installed."""
    try:
        # Just check if playwright module exists
        import playwright
        from pathlib import Path
        import os

        # Check common browser locations
        home = Path.home()
        browser_paths = [
            home / ".cache" / "ms-playwright",  # Linux
            home / "Library" / "Caches" / "ms-playwright",  # macOS
            Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright",  # Windows
        ]

        for path in browser_paths:
            if path.exists() and any(path.iterdir()):
                return True, "Browser automation ready"

        # If we got here, playwright is installed but browsers might not be
        return True, "Playwright ready (run: playwright install chromium)"

    except ImportError:
        return False, "Playwright not installed. Run: pip install playwright"
    except Exception as e:
        return False, f"Playwright check error: {e}"


def check_config() -> Tuple[bool, str]:
    """Check if config file exists and is valid."""
    config_path = Path("config/config.yaml")
    if not config_path.exists():
        return False, "config/config.yaml not found"

    try:
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)

        if not config:
            return False, "Config file is empty"

        return True, "Config loaded"
    except Exception as e:
        return False, f"Config error: {e}"


def check_output_folder() -> Tuple[bool, str]:
    """Check if output folder is accessible."""
    try:
        from .output_path import get_output_folder
        folder = get_output_folder()
        return True, str(folder)
    except Exception as e:
        return False, f"Output folder error: {e}"


def run_health_checks(verbose: bool = True) -> bool:
    """
    Run all health checks.

    Returns True if all critical checks pass.
    """
    checks = [
        ("AI Service", check_ollama_running, True),  # critical
        ("AI Models", check_required_models, True),  # critical
        ("Browser", check_playwright, False),  # not critical for all tasks
        ("Config", check_config, True),  # critical
        ("Output Folder", check_output_folder, False),  # not critical
    ]

    results = []
    all_critical_passed = True

    for name, check_fn, is_critical in checks:
        try:
            passed, message = check_fn()
        except Exception as e:
            passed, message = False, str(e)

        results.append((name, passed, message, is_critical))

        if not passed and is_critical:
            all_critical_passed = False

    if verbose:
        _display_results(results, all_critical_passed)

    return all_critical_passed


def _display_results(results: List, all_passed: bool):
    """Display health check results."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(width=3)
    table.add_column(width=18)
    table.add_column()

    for name, passed, message, is_critical in results:
        if passed:
            icon = "[green]✓[/green]"
            style = "dim"
        elif is_critical:
            icon = "[red]✗[/red]"
            style = "red"
        else:
            icon = "[yellow]![/yellow]"
            style = "yellow"

        table.add_row(icon, name, f"[{style}]{message}[/{style}]")

    if all_passed:
        console.print(table)
    else:
        panel = Panel(
            table,
            title="[red bold]Startup Check Failed[/red bold]",
            border_style="red"
        )
        console.print(panel)
        console.print("\n[yellow]Fix the issues above and try again.[/yellow]\n")


def quick_check() -> Tuple[bool, str]:
    """
    Quick check - just verify Ollama is running.
    Returns (success, error_message)
    """
    import os
    # Bypass if using remote GPU LLM
    if os.environ.get('GPU_LLM_URL') or os.environ.get('EVERSALE_LLM_URL'):
        return True, ""
        
    try:
        import yaml
        config_path = Path("config/config.yaml")
        if config_path.exists():
             with open(config_path) as f:
                config = yaml.safe_load(f) or {}
                if config.get('llm', {}).get('base_url'):
                    return True, ""
    except Exception:
        pass

    try:
        import ollama
        ollama.list()
        return True, ""
    except Exception as e:
        error = str(e).lower()
        if "connection refused" in error or "connect" in error:
            return False, "Ollama is not running.\n\nStart it with: [bold]ollama serve[/bold]"
        return False, f"Ollama error: {e}"


if __name__ == "__main__":
    # Run checks when called directly
    success = run_health_checks(verbose=True)
    sys.exit(0 if success else 1)
