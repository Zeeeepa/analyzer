"""
Telemetry Hub - Ingests structured JSON+text telemetry logs for mission awareness.
"""

import json
from pathlib import Path
from typing import Dict, List


class TelemetryHub:
    def __init__(self, directory: Path = Path("logs/telemetry")):
        self.directory = directory
        self.state_path = Path("memory/telemetry_state.json")
        self.offsets: Dict[str, int] = {}
        self.events: List[str] = []
        self.directory.mkdir(parents=True, exist_ok=True)
        self._load_state()

    def _load_state(self):
        if not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text())
            self.offsets = data.get("offsets", {})
            self.events = data.get("events", [])[-50:]
        except Exception:
            self.offsets = {}
            self.events = []

    def _save_state(self):
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "offsets": self.offsets,
                "events": self.events[-50:]
            }
            self.state_path.write_text(json.dumps(data))
        except Exception:
            pass

    def read_updates(self) -> List[str]:
        updates: List[str] = []

        if not self.directory.exists():
            return updates

        for file in sorted([p for p in self.directory.iterdir() if p.is_file()]):
            key = str(file)
            offset = self.offsets.get(key, 0)

            try:
                with file.open("r", encoding="utf-8", errors="ignore") as stream:
                    stream.seek(offset)
                    for line in stream:
                        line = line.strip()
                        if not line:
                            continue
                        parsed = self._parse_line(line)
                        updates.append(parsed)
                    self.offsets[key] = stream.tell()
            except Exception:
                continue

        if updates:
            self.events.extend(updates)
            self.events = self.events[-50:]
            self._save_state()

        return updates

    def _parse_line(self, line: str) -> str:
        try:
            payload = json.loads(line)
            if isinstance(payload, dict):
                for key in ("status", "summary", "message", "description"):
                    value = payload.get(key)
                    if value:
                        return f"{key.title()}: {value}"
                return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)[:200]
            if isinstance(payload, list):
                return "; ".join(str(v) for v in payload)[:200]
            return str(payload)
        except json.JSONDecodeError:
            return line[:200]

    def summarize(self) -> str:
        if not self.events:
            return ""
        return "; ".join(self.events[-3:])
