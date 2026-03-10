"""Workspace path detection utilities for the Eversale package.

Resolves paths dynamically based on the package installation location.
Works natively on Windows, macOS, and Linux — no WSL paths.
"""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=1)
def get_engine_dir() -> Path:
    """Return the absolute path to the engine directory.

    This is the parent of the agent/ directory (i.e. engine/).
    """
    return Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def get_workspace_root() -> str:
    """
    Return the absolute path to the workspace root.

    Priority:
    1. EVERSALE_WORKSPACE_ROOT environment variable (allows overrides).
    2. EVERSALE_ENGINE_DIR environment variable (set by the CLI entry point).
    3. Parent directories that contain both ``agent/`` and ``config/``.
    4. The engine directory (package root fallback).
    """
    # 1. Explicit env var override
    env_root = os.environ.get("EVERSALE_WORKSPACE_ROOT")
    if env_root:
        return env_root.rstrip("/\\")

    # 2. Engine dir from CLI entry point
    env_engine = os.environ.get("EVERSALE_ENGINE_DIR")
    if env_engine:
        engine_path = Path(env_engine)
        if engine_path.exists():
            return str(engine_path)

    # 3. Walk up from this file to find the engine root
    engine_dir = get_engine_dir()
    if (engine_dir / "agent").exists() and (engine_dir / "config").exists():
        return str(engine_dir)

    # 4. Check parent directories for a workspace marker
    current = Path(__file__).resolve()
    for parent in current.parents:
        # Check for the eversale engine layout
        if (parent / "agent").exists() and (parent / "config").exists():
            return str(parent)
        # Check for a monorepo layout (agent-backend + cli)
        if (parent / "agent-backend").exists() and (parent / "cli").exists():
            return str(parent)

    # 5. Fallback to the engine directory
    return str(engine_dir)


def get_workspace_root_path() -> Path:
    """Return the workspace root as a Path object."""
    return Path(get_workspace_root()).resolve()


@lru_cache(maxsize=1)
def get_eversale_home() -> Path:
    """Return the eversale home directory (~/.eversale).

    This is where runtime data, logs, cache, and outputs are stored.
    """
    home = Path(os.environ.get("EVERSALE_HOME", Path.home() / ".eversale"))
    home.mkdir(parents=True, exist_ok=True)
    return home

