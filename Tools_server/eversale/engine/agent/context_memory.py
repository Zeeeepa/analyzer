"""
Context Memory - Stores recent prompts and summaries for Codex-like persistence.
"""

import json
from pathlib import Path
from typing import List


class ContextMemory:
    def __init__(self, path: Path = Path("memory/context_history.json"), limit: int = 30):
        self.path = path
        self.limit = limit
        self.history: List[str] = []
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        try:
            self.history = json.loads(self.path.read_text())[-self.limit:]
        except Exception:
            self.history = []

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.history[-self.limit:], ensure_ascii=False))
        except Exception:
            pass

    def add_entry(self, entry: str):
        text = entry.strip()
        if not text:
            return
        self.history.append(text)
        if len(self.history) > self.limit:
            self.history = self.history[-self.limit:]
        self._save()

    def summary(self, count: int = 3) -> str:
        return " | ".join(self.history[-count:]) if self.history else ""
