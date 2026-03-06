"""
Decision Logger - Records rationale for actions, rescues, and explorations.
"""

import json
from pathlib import Path
from typing import Dict


class DecisionLogger:
    def __init__(self, path: Path = Path("memory/decisions.json"), limit: int = 100):
        self.path = path
        self.limit = limit
        self.entries = []
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        try:
            self.entries = json.loads(self.path.read_text())[-self.limit:]
        except Exception:
            self.entries = []

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.entries[-self.limit:], indent=2))
        except Exception:
            pass

    def log(self, decision: Dict):
        clean = {k: v for k, v in decision.items()}
        self.entries.append(clean)
        if len(self.entries) > self.limit:
            self.entries = self.entries[-self.limit:]
        self._save()
