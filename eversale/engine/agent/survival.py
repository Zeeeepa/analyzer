"""
Survival Manager - Keeps the agent mission-ready for long-running, mission-critical workflows.

Tracks the primary directive, resource buffers, checkpoints, and emergent alerts so the agent
can prioritize mission survival (power, network, retries) while staying on target.
"""

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .atomic_file import atomic_write_json

SURVIVAL_QUESTIONS = [
    "Is my primary directive still valid, or has priority drifted?",
    "Which checkpoints were reached in the last run and are they logged?",
    "Are there any outstanding emergencies flagged by logs or monitors?",
    "What’s the latest disk/free ratio for logs, memory, and workspace?",
    "Are any resources (power, network, compute) dropping below safe bounds?",
    "Have I pruned anything recently to recover storage space?",
    "Are recent logs showing new critical entries that affect survival?",
    "Is the tone of the latest prompt 'urgent', 'positive', or neutral?",
    "Did I capture new long-term goals or priorities from the user?",
    "Could any I/O-heavy tool call push storage past the available space?",
    "Do environment observations suggest upstream services need checking?",
    "Are there external alerts (e.g., Cloudflare, captcha) that threaten the mission?",
    "Is enough history saved so I can recover if interrupted unexpectedly?",
    "Is there a recommendation to conserve or replenish key resources right now?",
    "When was the last time I confirmed mission status with the user or logs?",
    "Do curiosity prompts align with the current survival plan?",
    "Are outputs being saved in watched folders that might overflow soon?",
    "Do I have a contingency plan if future prompts need more resources than available?",
    "Is the most recent summary/checkpoint stored for auditability?",
    "Are there repeated failures or retries that should become new survival policies?"
]


@dataclass
class SurvivalSnapshot:
    timestamp: float
    note: str


class SurvivalManager:
    def __init__(self):
        self.primary_directive: str = ""
        self.progress_log: List[SurvivalSnapshot] = []
        self.resource_levels: Dict[str, float] = {
            'power': 1.0,
            'network': 1.0,
            'compute': 1.0
        }
        self.emergency_flags: List[str] = []
        self.checkpoints: List[str] = []
        self.last_evaluation: float = 0.0
        self.state_path = Path("memory/survival_state.json")
        self._load_state()

    def register_prompt(self, prompt: str):
        if prompt and prompt != self.primary_directive:
            self.primary_directive = prompt.strip()
            self.checkpoints.clear()
            self.record_progress("Started new directive.")

    def record_progress(self, note: str):
        if not note:
            return
        snapshot = SurvivalSnapshot(timestamp=time.time(), note=note[:200])
        self.progress_log.append(snapshot)
        if len(self.progress_log) > 50:
            self.progress_log.pop(0)
        self.save_state()

    def store_checkpoint(self, checkpoint: str):
        if checkpoint and checkpoint not in self.checkpoints:
            self.checkpoints.append(checkpoint)
            self.record_progress(f"Checkpoint: {checkpoint}")
            self.save_state()

    def adjust_resource(self, resource: str, level: float):
        if resource not in self.resource_levels:
            self.resource_levels[resource] = max(0.0, min(level, 1.0))
        else:
            self.resource_levels[resource] = max(0.0, min(level, 1.0))
        self.record_progress(f"Resource {resource} now {self.resource_levels[resource]:.2f}")
        self.save_state()

    def flag_emergency(self, alert: str):
        if alert and alert not in self.emergency_flags:
            self.emergency_flags.append(alert)
            self.record_progress(f"Emergency flagged: {alert}")
            self.save_state()

    def react_to_environment(self, observations: List[str]):
        for note in observations:
            if "alert" in note.lower() or "error" in note.lower() or "urgent" in note.lower():
                self.flag_emergency(note)
            else:
                self.record_progress(f"Environment noticed: {note}")

    def evaluate_survival(self) -> List[str]:
        suggestions: List[str] = []
        now = time.time()
        if now - self.last_evaluation < 60:
            return suggestions
        self.last_evaluation = now

        storage_notes = self.monitor_storage()
        suggestions.extend(storage_notes)

        low_resources = [r for r, v in self.resource_levels.items() if v < 0.45]
        for r in low_resources:
            suggestions.append(f"Resource '{r}' is low ({self.resource_levels[r]:.2f}); conserve usage or replenish.")

        if self.emergency_flags:
            suggestions.append("Emergencies: " + "; ".join(self.emergency_flags[-3:]))

        if self.primary_directive:
            suggestions.append(f"Mission reminder: {self.primary_directive[:120]}")

        if self.checkpoints:
            suggestions.append(f"Recent checkpoint: {self.checkpoints[-1]}")

        return suggestions

    def save_state(self):
        try:
            data = {
                "primary_directive": self.primary_directive,
                "resource_levels": self.resource_levels,
                "emergency_flags": self.emergency_flags[-6:],
                "checkpoints": self.checkpoints[-6:],
            }
            atomic_write_json(self.state_path, data, indent=2, backup=True)
        except Exception:
            pass

    def _load_state(self):
        if not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text())
            self.primary_directive = data.get("primary_directive", "")
            self.resource_levels = data.get("resource_levels", self.resource_levels)
            self.emergency_flags = data.get("emergency_flags", [])[-6:]
            self.checkpoints = data.get("checkpoints", [])[-6:]
        except Exception:
            pass

    def monitor_storage(self, paths: List[Path] = None, threshold: float = 0.08) -> List[str]:
        if paths is None:
            paths = [Path("logs"), Path("memory"), Path("workspace"), Path(".")]
        alerts: List[str] = []

        for path in paths:
            try:
                target = path if path.exists() else path.parent
                usage = shutil.disk_usage(str(target))
                free_ratio = usage.free / usage.total if usage.total else 1.0
                if free_ratio < threshold:
                    note = f"Low disk on {target}: {free_ratio:.0%} free"
                    self.flag_emergency(note)
                    alerts.append(note)
                    self._prune_old_files(path)
            except Exception as e:
                alerts.append(f"Storage check failed for {path}: {e}")

        return alerts

    def _prune_old_files(self, directory: Path, days: int = 7):
        if not directory.exists():
            return

        cutoff = time.time() - max(days * 86400, 3600)
        for file in sorted(directory.glob("**/*"), key=lambda p: p.stat().st_mtime):
            if not file.is_file():
                continue
            try:
                if file.stat().st_mtime < cutoff:
                    os.remove(file)
                    self.record_progress(f"Pruned {file.name} for storage relief.")
                    break
            except Exception:
                continue

    def get_survival_questions(self) -> List[str]:
        return SURVIVAL_QUESTIONS.copy()

    def digest(self) -> str:
        parts = []
        if self.primary_directive:
            parts.append(f"Directive: {self.primary_directive[:80]}")
        if self.checkpoints:
            parts.append(f"Checkpoints: {self.checkpoints[-2:]}")
        if self.emergency_flags:
            parts.append(f"Emergencies: {self.emergency_flags[-2:]}")
        res = ", ".join(f"{k}:{v:.2f}" for k, v in self.resource_levels.items())
        parts.append(f"Resources: {res}")
        return " | ".join(parts)
