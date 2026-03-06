"""
Awareness Hub - Adds long-term goal tracking, environment monitoring, curiosity, and tone awareness.

This module ensures the brain retains context beyond a single prompt, watches for high-level system updates,
detects tone, and recommends future attention areas without executing random moves.
"""

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .telemetry import TelemetryHub
from .atomic_file import atomic_write_json

POSITIVE_WORDS = {
    "thanks", "thank", "appreciate", "good", "great", "happy", "excited", "awesome", "perfect", "love"
}
NEGATIVE_WORDS = {
    "urgent", "frustrated", "blocked", "problem", "issue", "delay", "fail", "angry", "disappointed"
}


@dataclass
class AwarenessObservation:
    timestamp: float
    description: str


class AwarenessHub:
    def __init__(self):
        self.long_term_goals: List[str] = []
        self.priority_notes: List[str] = []
        self.observations: List[AwarenessObservation] = []
        self.tone_history: List[str] = []
        self.lessons: List[str] = []
        self.last_monitor_time: float = 0.0
        self.state_path = Path("memory/awareness_state.json")
        self.telemetry = TelemetryHub()
        self._load_state()

    def update_from_prompt(self, prompt: str):
        text = prompt.strip()
        if not text:
            return

        sentences = re.split(r'[.!?]+', text)
        for sentence in sentences:
            lower = sentence.lower()
            if "goal" in lower or "objective" in lower or "priority" in lower:
                cleaned = sentence.strip()
                if cleaned and cleaned not in self.long_term_goals:
                    self.long_term_goals.append(cleaned)
                    if len(self.long_term_goals) > 6:
                        self.long_term_goals.pop(0)

        if "priority" in text.lower():
            self.priority_notes.append(text)
            if len(self.priority_notes) > 6:
                self.priority_notes.pop(0)

        self._save_state()

    def detect_social_cues(self, text: str) -> str:
        if not text:
            tone = "neutral"
        else:
            words = re.findall(r"[A-Za-z]+", text.lower())
            pos = sum(1 for w in words if w in POSITIVE_WORDS)
            neg = sum(1 for w in words if w in NEGATIVE_WORDS)
            if pos > neg + 1:
                tone = "positive"
            elif neg > pos + 1:
                tone = "urgent"
            else:
                tone = "neutral"
        self.tone_history.append(tone)
        if len(self.tone_history) > 10:
            self.tone_history.pop(0)
        self._save_state()
        return tone

    def monitor_environment(self) -> List[str]:
        """Scan logs for updates and synthesize quick highlights."""
        notes: List[str] = []
        logs_dir = Path("logs")
        now = time.time()
        if logs_dir.exists() and logs_dir.is_dir():
            for log_file in logs_dir.glob("*.log"):
                try:
                    mtime = log_file.stat().st_mtime
                except OSError:
                    continue
                if mtime > self.last_monitor_time:
                    notes.append(f"{log_file.name} updated at {time.strftime('%H:%M:%S', time.localtime(mtime))}")
        if notes:
            self.last_monitor_time = now
            self.observations.append(AwarenessObservation(timestamp=now, description="; ".join(notes)))
            while len(self.observations) > 6:
                self.observations.pop(0)
        telemetry_updates = self.telemetry.read_updates()
        if telemetry_updates:
            notes.extend(telemetry_updates)
            self.observations.append(AwarenessObservation(timestamp=now, description="; ".join(telemetry_updates)))
            while len(self.observations) > 6:
                self.observations.pop(0)
        if notes:
            self._save_state()
        return notes

    def propose_curiosity_tasks(self) -> List[str]:
        suggestions: List[str] = []
        if self.long_term_goals:
            suggestions.append(f"Review status of goal: '{self.long_term_goals[-1]}'")
        if self.observations:
            suggestions.append("Check recent system logs or alerts for new updates.")
        if len(self.tone_history) >= 3 and self.tone_history[-1] == "urgent":
            suggestions.append("Prioritize urgent mentions from the latest prompts.")
        return suggestions

    def digest(self) -> str:
        parts = []
        if self.long_term_goals:
            parts.append(f"Long-term goals: {self.long_term_goals[-2:]}")
        if self.priority_notes:
            parts.append(f"Recent priorities: {self.priority_notes[-2:]}")
        if self.observations:
            parts.append(f"Environment notes: {[o.description for o in self.observations[-2:]]}")
        if self.tone_history:
            parts.append(f"Tone: {self.tone_history[-1]}")
        if self.lessons:
            parts.append(f"Lessons: {self.lessons[-1]}")
        telemetry_summary = self.telemetry_summary()
        if telemetry_summary:
            parts.append(f"Telemetry: {telemetry_summary}")
        return " | ".join(parts) if parts else "No awareness updates yet."

    def _save_state(self):
        try:
            data = {
                "long_term_goals": self.long_term_goals[-6:],
                "priority_notes": self.priority_notes[-6:],
                "observations": [o.description for o in self.observations[-6:]],
                "tone_history": self.tone_history[-10:],
                "lessons": self.lessons[-5:],
                "last_monitor_time": self.last_monitor_time
            }
            atomic_write_json(self.state_path, data, indent=2, backup=True)
        except Exception:
            pass

    def _load_state(self):
        if not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text())
            self.long_term_goals = data.get("long_term_goals", [])[-6:]
            self.priority_notes = data.get("priority_notes", [])[-6:]
            obs = data.get("observations", [])[-6:]
            self.observations = [AwarenessObservation(timestamp=time.time(), description=o) for o in obs]
            self.tone_history = data.get("tone_history", [])[-10:]
            self.lessons = data.get("lessons", [])[-5:]
            self.last_monitor_time = data.get("last_monitor_time", 0.0)
        except Exception:
            pass

    def add_lesson(self, note: str):
        if not note:
            return
        self.lessons.append(note)
        if len(self.lessons) > 5:
            self.lessons.pop(0)
        self._save_state()

    def telemetry_summary(self) -> str:
        return self.telemetry.summarize()
