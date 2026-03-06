"""
Rescue Policy - Logs resource warnings without slowing down the agent.

NOTE: This was simplified to NOT call browser tools for diagnostics.
The previous version called playwright_snapshot and playwright_get_text
on every "emergency" (like low disk space), which:
1. Slowed down the agent significantly
2. Didn't help with actual task completion
3. Wasted resources on non-essential diagnostics
"""

from datetime import datetime, timedelta
from typing import List

from .signal_dispatcher import SignalDispatcher


class RescuePolicy:
    def __init__(self, brain):
        self.brain = brain
        self.last_attempt = datetime.min
        self.cooldown = timedelta(seconds=300)  # Increased to 5 minutes
        self.dispatcher = SignalDispatcher()

    async def attempt_recovery(self, survival, awareness):
        """Log resource warnings without calling browser tools."""
        now = datetime.utcnow()
        if now - self.last_attempt < self.cooldown:
            return []

        emergencies = survival.emergency_flags
        low_resources = [r for r, v in survival.resource_levels.items() if v < 0.4]

        # Skip low disk warnings - they're constant and not actionable
        emergencies = [e for e in emergencies if 'disk' not in e.lower()]
        low_resources = [r for r in low_resources if 'disk' not in r.lower()]

        if not emergencies and not low_resources:
            return []

        self.last_attempt = now
        actions: List[str] = []

        if emergencies:
            actions.append("Warning: " + "; ".join(emergencies[-2:]))
        if low_resources:
            actions.append("Low resources: " + ", ".join(f"{r}:{survival.resource_levels[r]:.2f}" for r in low_resources))

        # Just log - don't call browser tools for diagnostics
        if actions:
            self.dispatcher.broadcast("WARNING", "Resource warning", "; ".join(actions))

        return actions
