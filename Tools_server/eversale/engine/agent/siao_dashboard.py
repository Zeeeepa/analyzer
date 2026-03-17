"""
SIAO Dashboard - Real-time status view of all organism components.

Provides comprehensive monitoring of:
- Heartbeat (organism pulse)
- Valence (emotional state)
- Uncertainty (confidence calibration)
- Memory (episodic storage)
- Self Model (capabilities & proficiency)
- Gap Detection (prediction accuracy)
- Mission Alignment
- Event Bus activity
- Rust acceleration status
- Overall organism health

Usage:
    dashboard = SIAODashboard()
    dashboard.attach(organism=organism_instance, siao_core=siao_core_instance)

    # Terminal display
    dashboard.print_status()

    # JSON export
    json_data = dashboard.to_json()

    # Programmatic access
    status = dashboard.get_status()
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.text import Text
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ComponentHealth:
    """Health status of a single component."""
    name: str
    status: str  # "green", "yellow", "red", "offline"
    message: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)

    def get_emoji(self) -> str:
        """Get status emoji."""
        emoji_map = {
            "green": "✓",
            "yellow": "⚠",
            "red": "✗",
            "offline": "○"
        }
        return emoji_map.get(self.status, "?")


# =============================================================================
# SIAO DASHBOARD
# =============================================================================

class SIAODashboard:
    """Real-time status dashboard for SIAO organism components."""

    def __init__(self):
        """Initialize dashboard."""
        self._organism = None
        self._siao_core = None
        self._console = Console() if RICH_AVAILABLE else None

    def attach(self, organism=None, siao_core=None):
        """
        Attach to organism instances for monitoring.

        Args:
            organism: Organism instance from organism_core.py
            siao_core: SIAO core instance (if using integrated valence/uncertainty)
        """
        self._organism = organism
        self._siao_core = siao_core

    def get_status(self) -> Dict:
        """
        Get complete status of all SIAO components.

        Returns:
            Dict with status of all components
        """
        return {
            "timestamp": datetime.now().isoformat(),
            "organism_alive": self._organism.alive if self._organism else False,
            "heartbeat": self._get_heartbeat_status(),
            "valence": self._get_valence_status(),
            "uncertainty": self._get_uncertainty_status(),
            "self_model": self._get_self_model_status(),
            "gap_detector": self._get_gap_detector_status(),
            "mission": self._get_mission_status(),
            "event_bus": self._get_event_bus_status(),
            "memory": self._get_memory_status(),
            "health": self._get_overall_health(),
            "rust_acceleration": self._get_rust_status(),
            "components": self._get_all_component_status()
        }

    # =========================================================================
    # COMPONENT STATUS GETTERS
    # =========================================================================

    def _get_heartbeat_status(self) -> Dict:
        """Get heartbeat loop status."""
        if not self._organism or not hasattr(self._organism, 'heartbeat'):
            return {"status": "offline", "message": "Heartbeat not initialized"}

        hb = self._organism.heartbeat
        metrics = hb.metrics

        return {
            "alive": hb.alive,
            "beats": metrics.beats,
            "uptime_seconds": metrics.uptime_seconds,
            "interval_ms": hb.interval_ms,
            "metrics": {
                "error_rate": metrics.error_rate,
                "avg_confidence": metrics.avg_confidence,
                "memory_pressure": metrics.memory_pressure,
                "task_latency_ms": metrics.task_latency_ms,
                "queue_depth": metrics.queue_depth,
                "gap_rate": metrics.gap_rate,
                "last_action_success": metrics.last_action_success,
                "last_gap_score": metrics.last_gap_score,
            },
            "rust_accelerated": hb._rust_heartbeat is not None
        }

    def _get_valence_status(self) -> Dict:
        """Get valence system status."""
        valence = None

        # Try to get from SIAO core (property is valence_system)
        if self._siao_core and hasattr(self._siao_core, 'valence_system'):
            valence = self._siao_core.valence_system
        # Try to get from organism
        elif self._organism and hasattr(self._organism, 'valence_system'):
            valence = self._organism.valence_system

        if not valence:
            return {"status": "offline", "message": "Valence system not initialized"}

        profile = valence.get_emotional_profile()
        motivation = valence.get_motivation()
        should_pause, pause_reason = valence.should_pause()

        return {
            "current_valence": valence.current_valence,
            "mood": valence.current_mood,
            "trend": profile.trend,
            "recent_avg": profile.recent_avg,
            "volatility": profile.volatility,
            "time_in_state": profile.time_in_state,
            "dominant_emotion": profile.dominant_emotion,
            "motivation": {
                "strategy": motivation["strategy"],
                "speed_multiplier": motivation["speed_multiplier"],
                "risk_tolerance": motivation["risk_tolerance"],
                "message": motivation["message"]
            },
            "paused": should_pause,
            "pause_reason": pause_reason,
            "history_count": len(valence.valence_history)
        }

    def _get_uncertainty_status(self) -> Dict:
        """Get uncertainty tracker status."""
        uncertainty = None

        # Try to get from SIAO core (property is uncertainty_tracker)
        if self._siao_core and hasattr(self._siao_core, 'uncertainty_tracker'):
            uncertainty = self._siao_core.uncertainty_tracker
        # Try to get from organism
        elif self._organism and hasattr(self._organism, 'uncertainty_tracker'):
            uncertainty = self._organism.uncertainty_tracker

        if not uncertainty:
            return {"status": "offline", "message": "Uncertainty tracker not initialized"}

        # Get calibration stats
        cal_stats = uncertainty.get_calibration_stats()

        # Recent success rate
        recent_success_rate = 0.0
        if uncertainty._recent_successes:
            recent_success_rate = sum(uncertainty._recent_successes) / len(uncertainty._recent_successes)

        return {
            "avg_confidence": recent_success_rate,
            "calibration_adjustment": uncertainty._calibration_adjustment,
            "calibration_status": cal_stats.get("status", "unknown"),
            "calibration_bias": cal_stats.get("bias", "unknown"),
            "total_decisions": cal_stats.get("total_decisions", 0),
            "recent_accuracy": cal_stats.get("recent_accuracy", 0.0),
            "weighted_error": cal_stats.get("weighted_calibration_error", 0.0),
            "pending_decisions": len(uncertainty._decisions),
            "thresholds": {
                "high": uncertainty.confidence_threshold_high,
                "low": uncertainty.confidence_threshold_low
            }
        }

    def _get_self_model_status(self) -> Dict:
        """Get self model status."""
        self_model = None

        # Try to get from SIAO core
        if self._siao_core and hasattr(self._siao_core, 'self_model'):
            self_model = self._siao_core.self_model
        # Try to get from organism
        elif self._organism and hasattr(self._organism, 'self_model'):
            self_model = self._organism.self_model

        if not self_model:
            return {"status": "offline", "message": "Self model not initialized"}

        # Get capabilities summary
        enabled_caps = [n for n, c in self_model.capabilities.items() if c.enabled]
        high_conf_caps = [
            n for n, c in self_model.capabilities.items()
            if c.enabled and c.confidence >= 0.8
        ]

        # Get strengths and weaknesses
        strengths = self_model.get_strengths(min_score=0.7)
        weaknesses = self_model.get_weaknesses(max_score=0.4)

        return {
            "identity": {
                "name": self_model.identity.name,
                "purpose": self_model.identity.purpose,
                "role": self_model.identity.role
            },
            "capabilities": {
                "total": len(self_model.capabilities),
                "enabled": len(enabled_caps),
                "high_confidence": len(high_conf_caps),
                "top_capabilities": high_conf_caps[:5]
            },
            "proficiencies": {
                "total_learned": len(self_model.proficiencies),
                "strengths": strengths,
                "weaknesses": weaknesses
            },
            "operational_state": {
                "fatigue": self_model.state.fatigue,
                "confidence": self_model.state.confidence,
                "context_fullness": self_model.state.context_fullness,
                "mood_valence": self_model.state.mood_valence,
                "consecutive_failures": self_model.state.consecutive_failures,
                "needs_rest": self_model.state.needs_rest(),
                "is_struggling": self_model.state.is_struggling()
            }
        }

    def _get_gap_detector_status(self) -> Dict:
        """Get gap detector status."""
        if not self._organism or not hasattr(self._organism, 'gap_detector'):
            return {"status": "offline", "message": "Gap detector not initialized"}

        gap = self._organism.gap_detector

        return {
            "surprise_rate": gap.get_surprise_rate(window_size=20),
            "recurring_patterns": gap.get_recurring_patterns(min_count=3),
            "pending_predictions": len(gap._pending_predictions),
            "history_count": len(gap._gap_history),
            "pattern_counts": len(gap._pattern_counts),
            "rust_accelerated": gap._rust_gap_detector is not None
        }

    def _get_mission_status(self) -> Dict:
        """Get mission anchor status."""
        if not self._organism or not hasattr(self._organism, 'mission_anchor'):
            return {"status": "offline", "message": "Mission anchor not initialized"}

        mission = self._organism.mission_anchor

        return {
            "mission": mission.mission,
            "values": mission.core_values,
            "alignment_trend": mission.get_alignment_trend(window=20),
            "is_drifting": mission.is_drifting(threshold=0.5),
            "drift_count": mission._drift_count,
            "alignment_history_count": len(mission._alignment_history)
        }

    def _get_event_bus_status(self) -> Dict:
        """Get event bus status."""
        if not self._organism or not hasattr(self._organism, 'event_bus'):
            return {"status": "offline", "message": "Event bus not initialized"}

        bus = self._organism.event_bus

        # Get event counts
        event_counts = bus.get_event_counts(since_seconds=60)

        return {
            "running": bus._running,
            "subscribers_count": sum(len(subs) for subs in bus._subscribers.values()),
            "all_subscribers_count": len(bus._all_subscribers),
            "event_history_count": len(bus._event_history),
            "recent_events_60s": event_counts,
            "total_event_types": len(bus._subscribers),
            "rust_accelerated": bus._rust_bus is not None
        }

    def _get_memory_status(self) -> Dict:
        """Get memory architecture status."""
        memory = None

        # Try to get from organism
        if self._organism and hasattr(self._organism, 'memory'):
            memory = self._organism.memory
        # Try to get from SIAO core
        elif self._siao_core and hasattr(self._siao_core, 'memory'):
            memory = self._siao_core.memory

        if not memory:
            return {"status": "offline", "message": "Memory not initialized"}

        # Get basic memory stats
        stats = {}

        # Try to get episodic memory stats
        if hasattr(memory, 'episodic') and memory.episodic:
            try:
                episodes = memory.episodic.get_all_episodes()
                stats["episodic_count"] = len(episodes)
                stats["episodic_success_rate"] = sum(1 for e in episodes if e.success) / len(episodes) if episodes else 0
            except:
                stats["episodic_count"] = "unknown"

        # Try to get wisdom stats
        if hasattr(memory, 'wisdom') and memory.wisdom:
            try:
                stats["wisdom_count"] = len(memory.wisdom.lessons)
            except:
                stats["wisdom_count"] = "unknown"

        # Try to get working memory stats
        if hasattr(memory, 'working') and memory.working:
            try:
                stats["working_memory_count"] = len(memory.working.current_context)
            except:
                stats["working_memory_count"] = "unknown"

        return {
            "initialized": True,
            "stats": stats
        }

    def _get_overall_health(self) -> Dict:
        """Get aggregate health from all components."""
        if not self._organism:
            return {
                "status": "offline",
                "score": 0.0,
                "issues": ["Organism not initialized"]
            }

        issues = []
        warnings = []

        # Check heartbeat
        hb_status = self._get_heartbeat_status()
        if hb_status.get("status") == "offline":
            issues.append("Heartbeat offline")
        elif hb_status.get("metrics"):
            metrics = hb_status["metrics"]
            if metrics.get("error_rate", 0) > 0.2:
                issues.append(f"High error rate: {metrics['error_rate']:.1%}")
            if metrics.get("gap_rate", 0) > 0.5:
                warnings.append(f"High gap rate: {metrics['gap_rate']:.1%}")

        # Check valence
        val_status = self._get_valence_status()
        if val_status.get("status") != "offline":
            if val_status.get("paused"):
                issues.append(f"Paused: {val_status.get('pause_reason')}")
            elif val_status.get("current_valence", 0) < -0.6:
                warnings.append(f"Negative valence: {val_status['current_valence']:.2f}")

        # Check self model
        sm_status = self._get_self_model_status()
        if sm_status.get("status") != "offline":
            op_state = sm_status.get("operational_state", {})
            if op_state.get("needs_rest"):
                warnings.append("Agent needs rest")
            if op_state.get("is_struggling"):
                warnings.append("Agent struggling")

        # Calculate health score
        score = 1.0
        score -= len(issues) * 0.3  # Critical issues
        score -= len(warnings) * 0.1  # Warnings
        score = max(0.0, min(1.0, score))

        # Determine status
        if score >= 0.8:
            status = "healthy"
        elif score >= 0.6:
            status = "degraded"
        elif score >= 0.4:
            status = "struggling"
        else:
            status = "critical"

        return {
            "status": status,
            "score": score,
            "issues": issues,
            "warnings": warnings
        }

    def _get_rust_status(self) -> Dict:
        """Check which Rust accelerations are active."""
        if not self._organism:
            return {
                "available": False,
                "components": {}
            }

        from agent.organism_core import RUST_AVAILABLE

        components = {}

        # Check event bus
        if hasattr(self._organism, 'event_bus'):
            components["event_bus"] = self._organism.event_bus._rust_bus is not None

        # Check heartbeat
        if hasattr(self._organism, 'heartbeat'):
            components["heartbeat"] = self._organism.heartbeat._rust_heartbeat is not None

        # Check gap detector
        if hasattr(self._organism, 'gap_detector'):
            components["gap_detector"] = self._organism.gap_detector._rust_gap_detector is not None

        return {
            "available": RUST_AVAILABLE,
            "components": components,
            "speedup_potential": {
                "event_bus": "50-100x (lock-free broadcast)",
                "heartbeat": "<1ms jitter (vs 10-50ms)",
                "gap_detector": "50-200x (SIMD similarity)"
            }
        }

    def _get_all_component_status(self) -> List[ComponentHealth]:
        """Status of each of the organism components."""
        components = []

        # 1. Heartbeat
        hb_status = self._get_heartbeat_status()
        if hb_status.get("status") == "offline":
            components.append(ComponentHealth(
                name="Heartbeat",
                status="offline",
                message="Not initialized"
            ))
        elif hb_status.get("alive"):
            components.append(ComponentHealth(
                name="Heartbeat",
                status="green",
                message=f"{hb_status['beats']} beats, {hb_status['uptime_seconds']:.0f}s uptime",
                metrics=hb_status.get("metrics", {})
            ))
        else:
            components.append(ComponentHealth(
                name="Heartbeat",
                status="red",
                message="Not alive"
            ))

        # 2. Event Bus
        eb_status = self._get_event_bus_status()
        if eb_status.get("status") == "offline":
            components.append(ComponentHealth(
                name="EventBus",
                status="offline",
                message="Not initialized"
            ))
        else:
            components.append(ComponentHealth(
                name="EventBus",
                status="green",
                message=f"{eb_status['subscribers_count']} subscribers, {eb_status['event_history_count']} events",
                metrics=eb_status
            ))

        # 3. Gap Detector
        gd_status = self._get_gap_detector_status()
        if gd_status.get("status") == "offline":
            components.append(ComponentHealth(
                name="GapDetector",
                status="offline",
                message="Not initialized"
            ))
        else:
            surprise_rate = gd_status.get("surprise_rate", 0)
            status = "green" if surprise_rate < 0.3 else "yellow" if surprise_rate < 0.6 else "red"
            components.append(ComponentHealth(
                name="GapDetector",
                status=status,
                message=f"{surprise_rate:.0%} surprise rate",
                metrics=gd_status
            ))

        # 4. Mission Anchor
        m_status = self._get_mission_status()
        if m_status.get("status") == "offline":
            components.append(ComponentHealth(
                name="MissionAnchor",
                status="offline",
                message="Not initialized"
            ))
        else:
            trend = m_status.get("alignment_trend", 0)
            is_drifting = m_status.get("is_drifting", False)
            status = "red" if is_drifting else "yellow" if trend < 0.6 else "green"
            components.append(ComponentHealth(
                name="MissionAnchor",
                status=status,
                message=f"{trend:.0%} alignment" + (" (DRIFTING)" if is_drifting else ""),
                metrics=m_status
            ))

        # 5. Valence System
        v_status = self._get_valence_status()
        if v_status.get("status") == "offline":
            components.append(ComponentHealth(
                name="ValenceSystem",
                status="offline",
                message="Not initialized"
            ))
        else:
            valence = v_status.get("current_valence", 0)
            mood = v_status.get("mood", "unknown")
            status = "red" if valence < -0.6 else "yellow" if valence < -0.2 else "green"
            components.append(ComponentHealth(
                name="ValenceSystem",
                status=status,
                message=f"{mood} ({valence:+.2f})",
                metrics=v_status
            ))

        # 6. Uncertainty Tracker
        u_status = self._get_uncertainty_status()
        if u_status.get("status") == "offline":
            components.append(ComponentHealth(
                name="UncertaintyTracker",
                status="offline",
                message="Not initialized"
            ))
        else:
            cal_status = u_status.get("calibration_status", "unknown")
            accuracy = u_status.get("recent_accuracy", 0)
            status = "green" if cal_status == "Well-calibrated" else "yellow"
            components.append(ComponentHealth(
                name="UncertaintyTracker",
                status=status,
                message=f"{cal_status}, {accuracy:.0%} accuracy",
                metrics=u_status
            ))

        # 7. Self Model
        sm_status = self._get_self_model_status()
        if sm_status.get("status") == "offline":
            components.append(ComponentHealth(
                name="SelfModel",
                status="offline",
                message="Not initialized"
            ))
        else:
            op_state = sm_status.get("operational_state", {})
            fatigue = op_state.get("fatigue", 0)
            confidence = op_state.get("confidence", 1)
            status = "red" if op_state.get("needs_rest") else "yellow" if fatigue > 0.5 else "green"
            components.append(ComponentHealth(
                name="SelfModel",
                status=status,
                message=f"{confidence:.0%} confidence, {fatigue:.0%} fatigue",
                metrics=sm_status
            ))

        # 8. Memory
        mem_status = self._get_memory_status()
        if mem_status.get("status") == "offline":
            components.append(ComponentHealth(
                name="Memory",
                status="offline",
                message="Not initialized"
            ))
        else:
            stats = mem_status.get("stats", {})
            ep_count = stats.get("episodic_count", "?")
            components.append(ComponentHealth(
                name="Memory",
                status="green",
                message=f"{ep_count} episodes",
                metrics=mem_status
            ))

        return components

    # =========================================================================
    # OUTPUT METHODS
    # =========================================================================

    def print_status(self):
        """Pretty print status for terminal using Rich."""
        if not RICH_AVAILABLE or not self._console:
            self._print_simple_status()
            return

        # Get status
        status = self.get_status()
        health = status["health"]
        components = status["components"]

        # Create layout
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )

        # Header
        header_text = Text()
        header_text.append("SIAO ORGANISM DASHBOARD", style="bold cyan")
        header_text.append(" | ", style="dim")
        header_text.append(f"Status: {health['status'].upper()}",
                          style=f"bold {'green' if health['status'] == 'healthy' else 'yellow' if health['status'] == 'degraded' else 'red'}")
        header_text.append(" | ", style="dim")
        header_text.append(f"Health: {health['score']:.0%}", style="bold")
        layout["header"].update(Panel(header_text, border_style="cyan"))

        # Body - Component table
        table = Table(title="Component Status", box=box.ROUNDED, expand=True)
        table.add_column("Component", style="cyan", width=20)
        table.add_column("Status", width=10)
        table.add_column("Message", style="dim")

        for comp in components:
            status_color = {
                "green": "green",
                "yellow": "yellow",
                "red": "red",
                "offline": "dim"
            }.get(comp.status, "white")

            table.add_row(
                comp.name,
                f"{comp.get_emoji()} {comp.status}",
                comp.message,
                style=status_color if comp.status == "red" else None
            )

        layout["body"].update(table)

        # Footer - Key metrics
        footer_text = Text()

        # Heartbeat
        hb = status.get("heartbeat", {})
        if hb.get("alive"):
            footer_text.append(f"Beats: {hb.get('beats', 0)} | ", style="dim")

        # Valence
        val = status.get("valence", {})
        if val.get("status") != "offline":
            footer_text.append(f"Mood: {val.get('mood', '?')} ({val.get('current_valence', 0):+.2f}) | ", style="dim")

        # Rust
        rust = status.get("rust_acceleration", {})
        if rust.get("available"):
            active = sum(1 for v in rust.get("components", {}).values() if v)
            footer_text.append(f"Rust: {active}/{len(rust.get('components', {}))} active | ", style="green")

        footer_text.append(f"Time: {status['timestamp']}", style="dim")

        layout["footer"].update(Panel(footer_text, border_style="dim"))

        # Print
        self._console.print(layout)

        # Print issues/warnings if any
        if health.get("issues"):
            self._console.print("\n[bold red]Issues:[/bold red]")
            for issue in health["issues"]:
                self._console.print(f"  [red]✗[/red] {issue}")

        if health.get("warnings"):
            self._console.print("\n[bold yellow]Warnings:[/bold yellow]")
            for warning in health["warnings"]:
                self._console.print(f"  [yellow]⚠[/yellow] {warning}")

    def _print_simple_status(self):
        """Simple text-based status (fallback when Rich not available)."""
        status = self.get_status()
        health = status["health"]
        components = status["components"]

        print("\n" + "=" * 70)
        print(f"SIAO ORGANISM DASHBOARD")
        print(f"Status: {health['status'].upper()} | Health: {health['score']:.0%}")
        print("=" * 70)

        print("\nComponent Status:")
        print("-" * 70)
        for comp in components:
            print(f"  {comp.get_emoji()} {comp.name:<20} {comp.status:<10} {comp.message}")

        if health.get("issues"):
            print("\nIssues:")
            for issue in health["issues"]:
                print(f"  X {issue}")

        if health.get("warnings"):
            print("\nWarnings:")
            for warning in health["warnings"]:
                print(f"  ! {warning}")

        print("\n" + "=" * 70)
        print(f"Time: {status['timestamp']}")
        print("=" * 70 + "\n")

    def to_json(self) -> str:
        """
        Export status as JSON for API/monitoring.

        Returns:
            JSON string with complete status
        """
        status = self.get_status()

        # Convert ComponentHealth objects to dicts
        status["components"] = [
            {
                "name": c.name,
                "status": c.status,
                "message": c.message,
                "metrics": c.metrics
            }
            for c in status["components"]
        ]

        return json.dumps(status, indent=2, default=str)

    def save_to_file(self, filepath: str = None):
        """
        Save current status to JSON file.

        Args:
            filepath: Path to save file (defaults to memory/dashboard_status.json)
        """
        if filepath is None:
            filepath = "memory/dashboard_status.json"

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(self.to_json())
        print(f"Status saved to {filepath}")


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_dashboard(organism=None, siao_core=None) -> SIAODashboard:
    """
    Create and attach a dashboard.

    Args:
        organism: Organism instance
        siao_core: SIAO core instance

    Returns:
        Configured SIAODashboard instance
    """
    dashboard = SIAODashboard()
    dashboard.attach(organism=organism, siao_core=siao_core)
    return dashboard


def quick_status(organism=None, siao_core=None):
    """
    Quick status check - print to terminal.

    Args:
        organism: Organism instance
        siao_core: SIAO core instance
    """
    dashboard = create_dashboard(organism=organism, siao_core=siao_core)
    dashboard.print_status()


# =============================================================================
# MAIN / DEMO
# =============================================================================

if __name__ == "__main__":
    print("SIAO Dashboard")
    print("=" * 70)
    print("\nThis module provides real-time monitoring of the SIAO organism.")
    print("\nUsage:")
    print("  from agent.siao_dashboard import SIAODashboard, create_dashboard")
    print("  dashboard = create_dashboard(organism=my_organism)")
    print("  dashboard.print_status()")
    print("\n" + "=" * 70)
