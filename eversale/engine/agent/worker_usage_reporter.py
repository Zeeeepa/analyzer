"""
Worker usage reporter.

Reports billable worker minutes (wall-clock while run is active) to the Eversale API.

Endpoint:
  POST https://eversale.io/api/desktop/worker-usage

Auth:
  Authorization: Bearer <license_key>
"""

from __future__ import annotations

import os
import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    httpx = None  # type: ignore
    HTTPX_AVAILABLE = False


@dataclass
class WorkerUsageDelta:
    run_id: str
    worker_minutes: int = 0
    runs_started: int = 0
    llm_calls: int = 0
    browser_actions: int = 0


class WorkerUsageReporter:
    EVERSALE_API_URL = "https://eversale.io/api/desktop"

    def __init__(self, license_key: Optional[str] = None):
        self.license_key = license_key or self._load_license_key()

    def _load_license_key(self) -> Optional[str]:
        key = os.getenv("EVERSALE_LICENSE_KEY")
        if key:
            return key.strip()
        key_path = Path.home() / ".eversale" / "license.key"
        if key_path.exists():
            try:
                return key_path.read_text().strip()
            except Exception:
                return None
        return None

    async def report(self, delta: WorkerUsageDelta) -> bool:
        if not self.license_key or not HTTPX_AVAILABLE:
            return False

        run_id = (delta.run_id or "").strip()
        if not run_id:
            return False

        worker_minutes = max(0, int(delta.worker_minutes or 0))
        runs_started = max(0, int(delta.runs_started or 0))
        llm_calls = max(0, int(delta.llm_calls or 0))
        browser_actions = max(0, int(delta.browser_actions or 0))

        if worker_minutes <= 0 and runs_started <= 0:
            return False

        payload = {
            "runId": run_id,
            "workerMinutes": worker_minutes,
            "runsStarted": runs_started,
            "llmCalls": llm_calls,
            "browserActions": browser_actions,
            "timestamp": datetime.now().isoformat()
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:  # type: ignore[attr-defined]
                resp = await client.post(
                    f"{self.EVERSALE_API_URL}/worker-usage",
                    headers={"Authorization": f"Bearer {self.license_key}"},
                    json=payload
                )
                if resp.status_code == 200:
                    return True
                if resp.status_code == 429:
                    try:
                        data = resp.json()
                        logger.warning(f"[USAGE] Worker limit reached: {data.get('error') or data.get('reason')}")
                    except Exception:
                        logger.warning("[USAGE] Worker limit reached (429)")
                    return False
                return False
        except Exception as e:
            logger.debug(f"[USAGE] Failed to report worker usage: {e}")
            return False


_reporter_singleton: Optional[WorkerUsageReporter] = None


def get_worker_usage_reporter() -> WorkerUsageReporter:
    global _reporter_singleton
    if _reporter_singleton is None:
        _reporter_singleton = WorkerUsageReporter()
    return _reporter_singleton


def report_worker_usage_fire_and_forget(delta: WorkerUsageDelta) -> None:
    """
    Best-effort reporting without blocking the run loop.
    Safe to call even when httpx isn't installed.
    """
    if not HTTPX_AVAILABLE:
        return
    try:
        reporter = get_worker_usage_reporter()
        asyncio.create_task(reporter.report(delta))
    except Exception:
        return

