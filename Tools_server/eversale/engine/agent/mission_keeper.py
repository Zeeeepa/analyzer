"""
Mission Keeper - Ensures mission prompts stay scheduled and persist across restarts.
"""

import yaml
from pathlib import Path
from typing import Dict, List

from .scheduler import TaskScheduler
from loguru import logger


class MissionKeeper:
    def __init__(self, scheduler: TaskScheduler):
        self.scheduler = scheduler
        self.path = Path("config/missions.yaml")
        self.missions: List[Dict] = []
        self._load_missions()

    def _load_missions(self):
        if not self.path.exists():
            self._write_default()
        try:
            config = yaml.safe_load(self.path.read_text())
            self.missions = config.get("missions", [])
        except Exception:
            self.missions = []

    def _write_default(self):
        default = {
            "missions": [
                {
                    "name": "persistent-mission",
                    "schedule": "0 * * * *",
                    "prompt": "Monitor the mission dashboard, keep solar arrays optimal, and report anomalies."
                }
            ]
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            yaml.dump(default, f)

    def ensure_missions(self):
        added = 0
        for mission in self.missions:
            name = mission.get("name")
            if not name:
                continue
            if name in self.scheduler.tasks:
                continue
            cron = mission.get("schedule", "0 * * * *")
            prompt = mission.get("prompt", "")
            if not prompt:
                continue
            self.scheduler.add_task(name, cron, prompt)
            added += 1
        if added:
            logger.info(f"MissionKeeper added {added} missions")
