"""
Signal Dispatcher - Emits mission-critical alerts for autonomous monitoring.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


class SignalDispatcher:
    def __init__(self, path: Path = Path("logs/signals.log")):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def broadcast(self, level: str, message: str, detail: Optional[str] = None):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message,
            "detail": detail or ""
        }
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass
