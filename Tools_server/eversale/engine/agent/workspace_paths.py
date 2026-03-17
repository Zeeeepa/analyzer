"""Workspace path detection utilities for the Eversale monorepo."""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=1)
def get_workspace_root() -> str:
    """
    Return the absolute path to the ev29 workspace root.

    Priority:
    1. EVERSALE_WORKSPACE_ROOT environment variable (allows overrides).
    2. Parent directories that contain both `agent-backend/` and `cli/`.
    3. Known defaults (/mnt/c/ev29 or C:/ev29).
    4. The highest parent of this file (repository root fallback).
    """

    env_root = os.environ.get("EVERSALE_WORKSPACE_ROOT")
    if env_root:
        return env_root.rstrip("/\\")

    current = Path(__file__).resolve()
    parents = [p for p in current.parents]

    for parent in parents:
        if (parent / "agent-backend").exists() and (parent / "cli").exists():
            return str(parent)

    default_candidates = [Path("/mnt/c/ev29"), Path("C:/ev29")]
    for candidate in default_candidates:
        try:
            if candidate.exists():
                return str(candidate)
        except OSError:
            continue

    # Fallback to the repository root (highest parent)
    if parents:
        return str(parents[-1])

    return str(current)


def get_workspace_root_path() -> Path:
    """Return the workspace root as a Path object."""
    return Path(get_workspace_root()).resolve()
