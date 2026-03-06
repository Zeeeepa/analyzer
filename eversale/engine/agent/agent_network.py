"""
Multi-Agent Network - Delegates tasks to helper agents and tracks their state.
"""

import json
import time
from pathlib import Path
from typing import Dict, List
from uuid import uuid4


class AgentNetwork:
    def __init__(self):
        self.storage = Path("memory/agent_network.json")
        self.tasks: List[Dict] = []
        self._load()

    def delegate_task(self, prompt: str, agent_id: str = "agent-alpha") -> Dict:
        task = {
            "id": str(uuid4()),
            "prompt": prompt,
            "agent_id": agent_id,
            "status": "queued",
            "timestamp": time.time()
        }
        self.tasks.append(task)
        self._trim()
        self._save()
        return {
            "status": "delegated",
            "task_id": task["id"],
            "agent_id": agent_id,
            "message": f"Task queued for {agent_id}"
        }

    def update_task(self, task_id: str, status: str, result: str = "") -> Dict:
        for task in self.tasks:
            if task["id"] == task_id:
                task["status"] = status
                task["result"] = result or task.get("result", "")
                task["updated_at"] = time.time()
                self._save()
                return {"status": "updated", "task": task}
        return {"error": "task not found"}

    def get_status(self) -> Dict:
        return {
            "pending": [t for t in self.tasks if t["status"] in ["queued", "in_progress"]],
            "completed": [t for t in self.tasks if t["status"] == "completed"],
            "total": len(self.tasks)
        }

    def _trim(self, max_tasks: int = 50):
        if len(self.tasks) > max_tasks:
            self.tasks = self.tasks[-max_tasks:]

    def _save(self):
        try:
            self.storage.parent.mkdir(parents=True, exist_ok=True)
            self.storage.write_text(json.dumps(self.tasks[-50:], indent=2))
        except Exception:
            pass

    def _load(self):
        if not self.storage.exists():
            return
        try:
            self.tasks = json.loads(self.storage.read_text())
        except Exception:
            self.tasks = []
