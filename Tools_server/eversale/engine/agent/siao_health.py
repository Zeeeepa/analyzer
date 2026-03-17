"""
SIAO Health Checker - Verify all organism components are functioning correctly.

This comprehensive health system tests every component of the SIAO organism:
- EventBus: Message delivery, latency, subscription health
- Heartbeat: Timing precision, metric collection, persistence
- GapDetector: Prediction/comparison cycle, surprise classification
- ValenceSystem: Emotional tracking, decay, mood classification
- UncertaintyTracker: Confidence scoring, calibration accuracy
- Memory: Storage/retrieval, capacity, fragmentation
- ImmuneSystem: Threat detection, pattern matching, screening
- CuriosityEngine: Gap detection, priority scoring, investigation
- SleepCycle: Tiredness tracking, consolidation triggers
- AttentionAllocator: Budget management, allocation efficiency
- SelfModel: Capability tracking, learning from outcomes
- DreamEngine: Simulation quality, prediction accuracy

Usage:
    from agent.siao_health import SIAOHealthChecker

    checker = SIAOHealthChecker()
    checker.attach(organism=organism, siao_core=siao_core)

    report = await checker.check_all()
    checker.print_report(report)
"""

import asyncio
import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from loguru import logger

# Try to import Rich for pretty printing
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# Import organism components
try:
    from agent.organism_core import (
        EventBus, EventType, OrganismEvent,
        HeartbeatLoop, GapDetector, MissionAnchor, Organism
    )
    ORGANISM_AVAILABLE = True
except ImportError:
    ORGANISM_AVAILABLE = False
    logger.warning("organism_core not available - health checks limited")


# =============================================================================
# HEALTH STATUS TYPES
# =============================================================================

class HealthStatus(Enum):
    """Overall health status."""
    GREEN = "green"      # Healthy - all systems operational
    YELLOW = "yellow"    # Degraded - some issues but functional
    RED = "red"          # Failing - critical issues detected
    OFFLINE = "offline"  # Not running or unreachable


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ComponentHealth:
    """Health result for a single component."""
    name: str
    status: HealthStatus
    latency_ms: float = 0.0
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "status": self.status.value,
            "latency_ms": self.latency_ms,
            "message": self.message,
            "details": self.details
        }


@dataclass
class Issue:
    """A detected health issue."""
    component: str
    severity: str  # "critical", "warning", "info"
    message: str
    suggestion: str = ""

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "component": self.component,
            "severity": self.severity,
            "message": self.message,
            "suggestion": self.suggestion
        }


@dataclass
class HealthReport:
    """Complete health report."""
    timestamp: datetime
    overall_status: HealthStatus
    components: List[ComponentHealth]
    issues: List[Issue]
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "overall_status": self.overall_status.value,
            "components": [c.to_dict() for c in self.components],
            "issues": [i.to_dict() for i in self.issues],
            "summary": self.summary
        }

    def save_to_file(self, path: Path):
        """Save report to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Health report saved to {path}")


# =============================================================================
# HEALTH CHECKER
# =============================================================================

class SIAOHealthChecker:
    """Health verification for all SIAO organism components."""

    def __init__(self):
        """Initialize health checker."""
        self._organism: Optional[Organism] = None
        self._siao_core = None

        # Component references (will be populated by attach)
        self._event_bus: Optional[EventBus] = None
        self._heartbeat: Optional[HeartbeatLoop] = None
        self._gap_detector: Optional[GapDetector] = None
        self._mission_anchor: Optional[MissionAnchor] = None

        # Extended SIAO components
        self._valence_system = None
        self._uncertainty_tracker = None
        self._memory_arch = None
        self._immune_system = None
        self._curiosity_engine = None
        self._sleep_cycle = None
        self._attention_allocator = None
        self._self_model = None
        self._dream_engine = None

        # New meta-cognition components
        self._meta_learner = None
        self._experimenter = None
        self._self_modifier = None
        self._world_model = None
        self._episode_compressor = None

        # Health metrics
        self._check_start_time = 0
        self._check_count = 0

    def attach(self, organism=None, siao_core=None):
        """
        Attach to organism instances.

        Args:
            organism: Organism instance (now contains ALL components including extended SIAO)
            siao_core: SIAO core instance (deprecated - organism now has all components)
        """
        self._organism = organism
        self._siao_core = siao_core

        # Extract core organism components
        if organism:
            self._event_bus = getattr(organism, 'event_bus', None)
            self._heartbeat = getattr(organism, 'heartbeat', None)
            self._gap_detector = getattr(organism, 'gap_detector', None)
            self._mission_anchor = getattr(organism, 'mission_anchor', None)

            # Extract extended SIAO components from organism (new unified architecture)
            self._valence_system = getattr(organism, 'valence_system', None)
            self._uncertainty_tracker = getattr(organism, 'uncertainty_tracker', None)
            self._memory_arch = getattr(organism, 'memory', None)  # Uses 'memory' attribute
            self._immune_system = getattr(organism, 'immune_system', None)
            self._curiosity_engine = getattr(organism, 'curiosity_engine', None)
            self._sleep_cycle = getattr(organism, 'sleep_cycle', None)
            self._attention_allocator = getattr(organism, 'attention_allocator', None)
            self._self_model = getattr(organism, 'self_model', None)
            self._dream_engine = getattr(organism, 'dream_engine', None)

            # New components
            self._meta_learner = getattr(organism, 'meta_learner', None)
            self._experimenter = getattr(organism, 'experimenter', None)
            self._self_modifier = getattr(organism, 'self_modifier', None)
            self._world_model = getattr(organism, 'world_model', None)
            self._episode_compressor = getattr(organism, 'episode_compressor', None)

        # Fallback: Extract extended SIAO components from separate siao_core (legacy)
        if siao_core:
            self._valence_system = self._valence_system or getattr(siao_core, 'valence_system', None)
            self._uncertainty_tracker = self._uncertainty_tracker or getattr(siao_core, 'uncertainty_tracker', None)
            self._memory_arch = self._memory_arch or getattr(siao_core, 'memory_arch', None)
            self._immune_system = self._immune_system or getattr(siao_core, 'immune_system', None)
            self._curiosity_engine = self._curiosity_engine or getattr(siao_core, 'curiosity_engine', None)
            self._sleep_cycle = self._sleep_cycle or getattr(siao_core, 'sleep_cycle', None)
            self._attention_allocator = self._attention_allocator or getattr(siao_core, 'attention_allocator', None)
            self._self_model = self._self_model or getattr(siao_core, 'self_model', None)
            self._dream_engine = self._dream_engine or getattr(siao_core, 'dream_engine', None)

        logger.info("SIAO Health Checker attached to organism")

    async def check_all(self) -> HealthReport:
        """
        Run all health checks and return comprehensive report.

        Returns:
            HealthReport with status for all components
        """
        self._check_start_time = time.time()
        self._check_count += 1

        logger.info("Starting comprehensive SIAO health check...")

        components = []
        issues = []

        # Check each component (in parallel for speed)
        checks = [
            self.check_event_bus(),
            self.check_heartbeat(),
            self.check_gap_detector(),
            self.check_mission_anchor(),
            self.check_valence(),
            self.check_uncertainty(),
            self.check_memory(),
            self.check_immune(),
            self.check_curiosity(),
            self.check_sleep(),
            self.check_attention(),
            self.check_self_model(),
            self.check_dream(),
            # New meta-cognition components
            self.check_meta_learner(),
            self.check_experimenter(),
            self.check_world_model(),
            self.check_episode_compressor(),
        ]

        # Run all checks concurrently
        results = await asyncio.gather(*checks, return_exceptions=True)

        # Process results
        for result in results:
            if isinstance(result, Exception):
                # Check failed with exception
                components.append(ComponentHealth(
                    name="unknown",
                    status=HealthStatus.RED,
                    message=f"Check failed: {str(result)}"
                ))
                issues.append(Issue(
                    component="unknown",
                    severity="critical",
                    message=f"Health check exception: {str(result)}",
                    suggestion="Check logs for stack trace"
                ))
            elif result:
                components.append(result)

                # Extract issues from failed checks
                if result.status == HealthStatus.RED:
                    issues.append(Issue(
                        component=result.name,
                        severity="critical",
                        message=result.message,
                        suggestion=self._suggest_fix(result.name, result.details)
                    ))
                elif result.status == HealthStatus.YELLOW:
                    issues.append(Issue(
                        component=result.name,
                        severity="warning",
                        message=result.message,
                        suggestion=self._suggest_fix(result.name, result.details)
                    ))
                elif result.status == HealthStatus.OFFLINE:
                    issues.append(Issue(
                        component=result.name,
                        severity="critical",
                        message=f"{result.name} is offline",
                        suggestion=f"Initialize {result.name} component"
                    ))

        # Calculate overall status
        overall_status = self._calculate_overall_status(components)

        # Create summary
        total_time = time.time() - self._check_start_time
        summary = {
            "total_checks": len(components),
            "healthy": sum(1 for c in components if c.status == HealthStatus.GREEN),
            "degraded": sum(1 for c in components if c.status == HealthStatus.YELLOW),
            "failing": sum(1 for c in components if c.status == HealthStatus.RED),
            "offline": sum(1 for c in components if c.status == HealthStatus.OFFLINE),
            "check_duration_ms": round(total_time * 1000, 2),
            "check_number": self._check_count,
        }

        report = HealthReport(
            timestamp=datetime.now(),
            overall_status=overall_status,
            components=components,
            issues=issues,
            summary=summary
        )

        logger.info(f"Health check complete: {overall_status.value} ({total_time*1000:.1f}ms)")

        return report

    # =========================================================================
    # INDIVIDUAL COMPONENT CHECKS
    # =========================================================================

    async def check_event_bus(self) -> ComponentHealth:
        """Check EventBus: Can publish? Can subscribe? Latency?"""
        if not self._event_bus:
            return ComponentHealth(
                name="EventBus",
                status=HealthStatus.OFFLINE,
                message="EventBus not initialized"
            )

        start = time.time()
        errors = []
        details = {}

        try:
            # Test 1: Can we subscribe?
            test_received = False

            def test_callback(event):
                nonlocal test_received
                test_received = True

            self._event_bus.subscribe(EventType.HEALTH_CHECK, test_callback)

            # Test 2: Can we publish?
            test_event = OrganismEvent(
                event_type=EventType.HEALTH_CHECK,
                source="health_checker",
                data={"test": True}
            )

            await self._event_bus.publish(test_event)

            # Wait briefly for callback
            await asyncio.sleep(0.01)

            if not test_received:
                errors.append("Event not received by subscriber")

            # Test 3: Check event history
            recent = self._event_bus.get_recent_events(limit=10)
            details["recent_event_count"] = len(recent)

            # Test 4: Check event counts
            counts = self._event_bus.get_event_counts(since_seconds=60)
            details["event_counts_last_minute"] = counts
            details["total_events_last_minute"] = sum(counts.values())

            # Cleanup
            self._event_bus.unsubscribe(EventType.HEALTH_CHECK, test_callback)

        except Exception as e:
            errors.append(f"EventBus test failed: {e}")

        latency = (time.time() - start) * 1000

        # Determine status
        if errors:
            status = HealthStatus.RED
            message = "; ".join(errors)
        elif latency > 100:
            status = HealthStatus.YELLOW
            message = f"EventBus slow: {latency:.1f}ms"
        else:
            status = HealthStatus.GREEN
            message = "EventBus healthy"

        details["latency_ms"] = round(latency, 2)

        return ComponentHealth(
            name="EventBus",
            status=status,
            latency_ms=latency,
            message=message,
            details=details
        )

    async def check_heartbeat(self) -> ComponentHealth:
        """Check Heartbeat: Is it beating? Consistent interval?"""
        if not self._heartbeat:
            return ComponentHealth(
                name="Heartbeat",
                status=HealthStatus.OFFLINE,
                message="Heartbeat not initialized"
            )

        start = time.time()
        details = {}
        errors = []

        try:
            # Check if alive
            is_alive = self._heartbeat.alive
            details["alive"] = is_alive

            if not is_alive:
                errors.append("Heartbeat not running")

            # Get metrics
            metrics = self._heartbeat.metrics
            details["beats"] = metrics.beats
            details["uptime_seconds"] = round(metrics.uptime_seconds, 2)
            details["error_rate"] = round(metrics.error_rate, 3)
            details["gap_rate"] = round(metrics.gap_rate, 3)
            details["avg_confidence"] = round(metrics.avg_confidence, 3)
            details["memory_pressure"] = round(metrics.memory_pressure, 3)

            # Check for unhealthy metrics
            if metrics.error_rate > 0.5:
                errors.append(f"High error rate: {metrics.error_rate:.2f}")

            if metrics.memory_pressure > 0.9:
                errors.append(f"High memory pressure: {metrics.memory_pressure:.2f}")

            if metrics.avg_confidence < 0.3:
                errors.append(f"Low confidence: {metrics.avg_confidence:.2f}")

        except Exception as e:
            errors.append(f"Heartbeat check failed: {e}")

        latency = (time.time() - start) * 1000

        # Determine status
        if errors:
            status = HealthStatus.RED if not details.get("alive") else HealthStatus.YELLOW
            message = "; ".join(errors)
        else:
            status = HealthStatus.GREEN
            message = f"Heartbeat healthy: {details.get('beats', 0)} beats"

        return ComponentHealth(
            name="Heartbeat",
            status=status,
            latency_ms=latency,
            message=message,
            details=details
        )

    async def check_gap_detector(self) -> ComponentHealth:
        """Check GapDetector: Can predict? Can compare?"""
        if not self._gap_detector:
            return ComponentHealth(
                name="GapDetector",
                status=HealthStatus.OFFLINE,
                message="GapDetector not initialized"
            )

        start = time.time()
        details = {}
        errors = []

        try:
            # Test prediction
            test_prediction = await self._gap_detector.predict(
                action="test_action",
                tool="test_tool",
                arguments={"test": True},
                context={"health_check": True}
            )

            details["can_predict"] = test_prediction is not None

            if test_prediction:
                # Test comparison
                test_result = await self._gap_detector.compare(
                    prediction=test_prediction,
                    actual_outcome="test completed successfully",
                    actual_success=True
                )

                details["can_compare"] = test_result is not None
                details["gap_score"] = round(test_result.gap_score, 3)
                details["surprise_type"] = test_result.surprise_type

            # Get statistics
            surprise_rate = self._gap_detector.get_surprise_rate()
            patterns = self._gap_detector.get_recurring_patterns()

            details["surprise_rate"] = round(surprise_rate, 3)
            details["recurring_patterns"] = len(patterns)

            # Check for issues
            if surprise_rate > 0.7:
                errors.append(f"High surprise rate: {surprise_rate:.2f}")

        except Exception as e:
            errors.append(f"GapDetector test failed: {e}")

        latency = (time.time() - start) * 1000

        # Determine status
        if errors:
            status = HealthStatus.YELLOW
            message = "; ".join(errors)
        else:
            status = HealthStatus.GREEN
            message = "GapDetector healthy"

        return ComponentHealth(
            name="GapDetector",
            status=status,
            latency_ms=latency,
            message=message,
            details=details
        )

    async def check_mission_anchor(self) -> ComponentHealth:
        """Check MissionAnchor: Mission intact? Alignment tracking?"""
        if not self._mission_anchor:
            return ComponentHealth(
                name="MissionAnchor",
                status=HealthStatus.OFFLINE,
                message="MissionAnchor not initialized"
            )

        start = time.time()
        details = {}
        errors = []

        try:
            # Get mission
            mission = self._mission_anchor.get_mission()
            values = self._mission_anchor.get_values()

            details["mission"] = mission
            details["core_values"] = values

            # Test alignment check
            test_score = await self._mission_anchor.check_alignment(
                action="help customer with research task",
                context={"health_check": True}
            )

            details["test_alignment_score"] = round(test_score, 3)

            # Get trend
            alignment_trend = self._mission_anchor.get_alignment_trend()
            is_drifting = self._mission_anchor.is_drifting()

            details["alignment_trend"] = round(alignment_trend, 3)
            details["is_drifting"] = is_drifting

            # Check for drift
            if is_drifting:
                errors.append(f"Mission drift detected: {alignment_trend:.2f}")

            if alignment_trend < 0.3:
                errors.append(f"Low alignment trend: {alignment_trend:.2f}")

        except Exception as e:
            errors.append(f"MissionAnchor check failed: {e}")

        latency = (time.time() - start) * 1000

        # Determine status
        if errors:
            status = HealthStatus.YELLOW
            message = "; ".join(errors)
        else:
            status = HealthStatus.GREEN
            message = "MissionAnchor healthy"

        return ComponentHealth(
            name="MissionAnchor",
            status=status,
            latency_ms=latency,
            message=message,
            details=details
        )

    async def check_valence(self) -> ComponentHealth:
        """Check ValenceSystem: Is it tracking? Responding to events?"""
        if not self._valence_system:
            return ComponentHealth(
                name="ValenceSystem",
                status=HealthStatus.OFFLINE,
                message="ValenceSystem not initialized"
            )

        start = time.time()
        details = {}
        errors = []

        try:
            # Get current state
            if hasattr(self._valence_system, 'get_emotional_profile'):
                profile = self._valence_system.get_emotional_profile()
                details["current_valence"] = round(profile.current_valence, 3)
                details["mood"] = profile.mood
                details["trend"] = profile.trend
                details["volatility"] = round(profile.volatility, 3)

            # Check if system is responsive
            if hasattr(self._valence_system, 'current_valence'):
                current = self._valence_system.current_valence
                details["current_valence"] = round(current, 3)

                # Check for extreme states
                if current < -0.8:
                    errors.append(f"Extreme negative valence: {current:.2f}")
                elif current > 0.8:
                    details["note"] = "High positive valence (good)"

        except Exception as e:
            errors.append(f"ValenceSystem check failed: {e}")

        latency = (time.time() - start) * 1000

        # Determine status
        if errors:
            status = HealthStatus.YELLOW
            message = "; ".join(errors)
        else:
            status = HealthStatus.GREEN
            message = "ValenceSystem healthy"

        return ComponentHealth(
            name="ValenceSystem",
            status=status,
            latency_ms=latency,
            message=message,
            details=details
        )

    async def check_uncertainty(self) -> ComponentHealth:
        """Check UncertaintyTracker: Is it scoring confidence?"""
        if not self._uncertainty_tracker:
            return ComponentHealth(
                name="UncertaintyTracker",
                status=HealthStatus.OFFLINE,
                message="UncertaintyTracker not initialized"
            )

        start = time.time()
        details = {}
        errors = []

        try:
            # Test confidence assessment
            if hasattr(self._uncertainty_tracker, 'assess_confidence'):
                assessment = await self._uncertainty_tracker.assess_confidence(
                    task_description="test task for health check",
                    context={"health_check": True}
                )

                if assessment:
                    details["test_confidence"] = round(assessment.confidence, 3)
                    details["recommended_action"] = assessment.action.value if hasattr(assessment, 'action') else "unknown"

            # Check calibration
            if hasattr(self._uncertainty_tracker, 'get_calibration_accuracy'):
                calibration = self._uncertainty_tracker.get_calibration_accuracy()
                details["calibration_accuracy"] = round(calibration, 3)

                if calibration < 0.6:
                    errors.append(f"Poor calibration: {calibration:.2f}")

        except Exception as e:
            errors.append(f"UncertaintyTracker check failed: {e}")

        latency = (time.time() - start) * 1000

        # Determine status
        if errors:
            status = HealthStatus.YELLOW
            message = "; ".join(errors)
        else:
            status = HealthStatus.GREEN
            message = "UncertaintyTracker healthy"

        return ComponentHealth(
            name="UncertaintyTracker",
            status=status,
            latency_ms=latency,
            message=message,
            details=details
        )

    async def check_memory(self) -> ComponentHealth:
        """Check Memory: Can store? Can retrieve? Healthy size?"""
        if not self._memory_arch:
            return ComponentHealth(
                name="Memory",
                status=HealthStatus.OFFLINE,
                message="Memory not initialized"
            )

        start = time.time()
        details = {}
        errors = []

        try:
            # Test storage
            test_key = f"health_check_{int(time.time())}"
            test_value = {"test": True, "timestamp": time.time()}

            if hasattr(self._memory_arch, 'store'):
                self._memory_arch.store(test_key, test_value)
                details["can_store"] = True

            # Test retrieval
            if hasattr(self._memory_arch, 'retrieve'):
                retrieved = self._memory_arch.retrieve(test_key)
                details["can_retrieve"] = retrieved is not None

                if retrieved != test_value:
                    errors.append("Retrieved value doesn't match stored value")

            # Get memory stats
            if hasattr(self._memory_arch, 'get_stats'):
                stats = self._memory_arch.get_stats()
                details.update(stats)

                # Check for capacity issues
                if stats.get('utilization', 0) > 0.9:
                    errors.append(f"High memory utilization: {stats['utilization']:.2f}")

        except Exception as e:
            errors.append(f"Memory check failed: {e}")

        latency = (time.time() - start) * 1000

        # Determine status
        if errors:
            status = HealthStatus.YELLOW
            message = "; ".join(errors)
        else:
            status = HealthStatus.GREEN
            message = "Memory healthy"

        return ComponentHealth(
            name="Memory",
            status=status,
            latency_ms=latency,
            message=message,
            details=details
        )

    async def check_immune(self) -> ComponentHealth:
        """Check ImmuneSystem: Can screen? Patterns loaded?"""
        if not self._immune_system:
            return ComponentHealth(
                name="ImmuneSystem",
                status=HealthStatus.OFFLINE,
                message="ImmuneSystem not initialized"
            )

        start = time.time()
        details = {}
        errors = []

        try:
            # Test screening (sync method, not async)
            if hasattr(self._immune_system, 'screen_input'):
                test_input = "Help me with a research task"
                result = self._immune_system.screen_input(test_input)

                details["can_screen"] = result is not None
                details["test_safe"] = result.safe if result else False

                # Check threat patterns loaded
                if hasattr(self._immune_system, 'threat_patterns'):
                    patterns = self._immune_system.threat_patterns
                    details["patterns_loaded"] = len(patterns) if patterns else 0

            # Get statistics
            if hasattr(self._immune_system, 'get_threat_stats'):
                stats = self._immune_system.get_threat_stats()
                details.update(stats)

                # Check for high threat rate
                if stats.get('threat_rate', 0) > 0.3:
                    errors.append(f"High threat rate: {stats['threat_rate']:.2f}")

        except Exception as e:
            errors.append(f"ImmuneSystem check failed: {e}")

        latency = (time.time() - start) * 1000

        # Determine status
        if errors:
            status = HealthStatus.YELLOW
            message = "; ".join(errors)
        else:
            status = HealthStatus.GREEN
            message = "ImmuneSystem healthy"

        return ComponentHealth(
            name="ImmuneSystem",
            status=status,
            latency_ms=latency,
            message=message,
            details=details
        )

    async def check_curiosity(self) -> ComponentHealth:
        """Check CuriosityEngine: Gap detection working?"""
        if not self._curiosity_engine:
            return ComponentHealth(
                name="CuriosityEngine",
                status=HealthStatus.OFFLINE,
                message="CuriosityEngine not initialized"
            )

        start = time.time()
        details = {}
        errors = []

        try:
            # Get gap statistics
            if hasattr(self._curiosity_engine, 'get_gap_stats'):
                stats = self._curiosity_engine.get_gap_stats()
                details.update(stats)

                # Check if gaps are being filled
                if stats.get('open_gaps', 0) > 100:
                    errors.append(f"Many open gaps: {stats['open_gaps']}")

            # Check prioritization
            if hasattr(self._curiosity_engine, 'get_top_gaps'):
                top_gaps = self._curiosity_engine.get_top_gaps(limit=5)
                details["top_gaps_count"] = len(top_gaps) if top_gaps else 0

        except Exception as e:
            errors.append(f"CuriosityEngine check failed: {e}")

        latency = (time.time() - start) * 1000

        # Determine status
        if errors:
            status = HealthStatus.YELLOW
            message = "; ".join(errors)
        else:
            status = HealthStatus.GREEN
            message = "CuriosityEngine healthy"

        return ComponentHealth(
            name="CuriosityEngine",
            status=status,
            latency_ms=latency,
            message=message,
            details=details
        )

    async def check_sleep(self) -> ComponentHealth:
        """Check SleepCycle: Tiredness tracking?"""
        if not self._sleep_cycle:
            return ComponentHealth(
                name="SleepCycle",
                status=HealthStatus.OFFLINE,
                message="SleepCycle not initialized"
            )

        start = time.time()
        details = {}
        errors = []

        try:
            # Get tiredness level
            if hasattr(self._sleep_cycle, 'get_tiredness'):
                tiredness = self._sleep_cycle.get_tiredness()
                details["tiredness"] = round(tiredness, 3)

                # Check for exhaustion
                if tiredness > 0.9:
                    errors.append(f"Extreme tiredness: {tiredness:.2f}")

            # Check sleep state (is_sleeping is an attribute, not method)
            if hasattr(self._sleep_cycle, 'is_sleeping'):
                is_sleeping = self._sleep_cycle.is_sleeping
                details["is_sleeping"] = is_sleeping

            # Get consolidation stats
            if hasattr(self._sleep_cycle, 'get_consolidation_stats'):
                stats = self._sleep_cycle.get_consolidation_stats()
                details.update(stats)

        except Exception as e:
            errors.append(f"SleepCycle check failed: {e}")

        latency = (time.time() - start) * 1000

        # Determine status
        if errors:
            status = HealthStatus.YELLOW
            message = "; ".join(errors)
        else:
            status = HealthStatus.GREEN
            message = "SleepCycle healthy"

        return ComponentHealth(
            name="SleepCycle",
            status=status,
            latency_ms=latency,
            message=message,
            details=details
        )

    async def check_attention(self) -> ComponentHealth:
        """Check AttentionAllocator: Budget being managed?"""
        if not self._attention_allocator:
            return ComponentHealth(
                name="AttentionAllocator",
                status=HealthStatus.OFFLINE,
                message="AttentionAllocator not initialized"
            )

        start = time.time()
        details = {}
        errors = []

        try:
            # Get budget status
            if hasattr(self._attention_allocator, 'get_budget_status'):
                status_info = self._attention_allocator.get_budget_status()
                details.update(status_info)

                # Check for budget exhaustion
                if status_info.get('remaining_budget', 0) < 0.1:
                    errors.append("Attention budget nearly exhausted")

            # Check allocation efficiency
            if hasattr(self._attention_allocator, 'get_efficiency'):
                efficiency = self._attention_allocator.get_efficiency()
                details["efficiency"] = round(efficiency, 3)

                if efficiency < 0.5:
                    errors.append(f"Low allocation efficiency: {efficiency:.2f}")

        except Exception as e:
            errors.append(f"AttentionAllocator check failed: {e}")

        latency = (time.time() - start) * 1000

        # Determine status
        if errors:
            status = HealthStatus.YELLOW
            message = "; ".join(errors)
        else:
            status = HealthStatus.GREEN
            message = "AttentionAllocator healthy"

        return ComponentHealth(
            name="AttentionAllocator",
            status=status,
            latency_ms=latency,
            message=message,
            details=details
        )

    async def check_self_model(self) -> ComponentHealth:
        """Check SelfModel: Identity intact? Capabilities tracked?"""
        if not self._self_model:
            return ComponentHealth(
                name="SelfModel",
                status=HealthStatus.OFFLINE,
                message="SelfModel not initialized"
            )

        start = time.time()
        details = {}
        errors = []

        try:
            # Check identity
            if hasattr(self._self_model, 'get_identity'):
                identity = self._self_model.get_identity()
                details["has_identity"] = identity is not None

            # Get capabilities
            if hasattr(self._self_model, 'get_capabilities'):
                capabilities = self._self_model.get_capabilities()
                details["capability_count"] = len(capabilities) if capabilities else 0

                # Check for learning
                if hasattr(self._self_model, 'get_learning_stats'):
                    stats = self._self_model.get_learning_stats()
                    details.update(stats)

            # Check confidence calibration
            if hasattr(self._self_model, 'get_confidence_accuracy'):
                accuracy = self._self_model.get_confidence_accuracy()
                details["confidence_accuracy"] = round(accuracy, 3)

                if accuracy < 0.6:
                    errors.append(f"Low confidence accuracy: {accuracy:.2f}")

        except Exception as e:
            errors.append(f"SelfModel check failed: {e}")

        latency = (time.time() - start) * 1000

        # Determine status
        if errors:
            status = HealthStatus.YELLOW
            message = "; ".join(errors)
        else:
            status = HealthStatus.GREEN
            message = "SelfModel healthy"

        return ComponentHealth(
            name="SelfModel",
            status=status,
            latency_ms=latency,
            message=message,
            details=details
        )

    async def check_dream(self) -> ComponentHealth:
        """Check DreamEngine: Can simulate?"""
        if not self._dream_engine:
            return ComponentHealth(
                name="DreamEngine",
                status=HealthStatus.OFFLINE,
                message="DreamEngine not initialized"
            )

        start = time.time()
        details = {}
        errors = []

        try:
            # Test simulation
            if hasattr(self._dream_engine, 'simulate'):
                test_sim = await self._dream_engine.simulate(
                    scenario="test scenario",
                    context={"health_check": True}
                )
                details["can_simulate"] = test_sim is not None

            # Get dream statistics
            if hasattr(self._dream_engine, 'get_dream_stats'):
                stats = self._dream_engine.get_dream_stats()
                details.update(stats)

            # Check prediction accuracy
            if hasattr(self._dream_engine, 'get_prediction_accuracy'):
                accuracy = self._dream_engine.get_prediction_accuracy()
                details["prediction_accuracy"] = round(accuracy, 3)

                if accuracy < 0.5:
                    errors.append(f"Low prediction accuracy: {accuracy:.2f}")

        except Exception as e:
            errors.append(f"DreamEngine check failed: {e}")

        latency = (time.time() - start) * 1000

        # Determine status
        if errors:
            status = HealthStatus.YELLOW
            message = "; ".join(errors)
        else:
            status = HealthStatus.GREEN
            message = "DreamEngine healthy"

        return ComponentHealth(
            name="DreamEngine",
            status=status,
            latency_ms=latency,
            message=message,
            details=details
        )

    async def check_meta_learner(self) -> ComponentHealth:
        """Check MetaLearner: Learning about learning?"""
        if not self._meta_learner:
            return ComponentHealth(
                name="MetaLearner",
                status=HealthStatus.OFFLINE,
                message="MetaLearner not initialized"
            )

        start = time.time()
        details = {}
        errors = []

        try:
            # Get meta-learner stats
            if hasattr(self._meta_learner, 'get_stats'):
                stats = self._meta_learner.get_stats()
                details["current_strategy"] = stats.get("current_strategy", "unknown")
                details["total_lessons"] = stats.get("total_lessons", 0)
                details["strategy_switches"] = stats.get("strategy_switches", 0)

            # Check if learning
            if hasattr(self._meta_learner, 'should_explore'):
                details["exploring"] = self._meta_learner.should_explore()

        except Exception as e:
            errors.append(f"MetaLearner check failed: {e}")

        latency = (time.time() - start) * 1000

        if errors:
            status = HealthStatus.YELLOW
            message = "; ".join(errors)
        else:
            status = HealthStatus.GREEN
            message = f"MetaLearner healthy: {details.get('current_strategy', 'unknown')} strategy"

        return ComponentHealth(
            name="MetaLearner",
            status=status,
            latency_ms=latency,
            message=message,
            details=details
        )

    async def check_experimenter(self) -> ComponentHealth:
        """Check Experimenter: Running safe experiments?"""
        if not self._experimenter:
            return ComponentHealth(
                name="Experimenter",
                status=HealthStatus.OFFLINE,
                message="Experimenter not initialized"
            )

        start = time.time()
        details = {}
        errors = []

        try:
            # Get experimenter stats
            if hasattr(self._experimenter, 'get_stats'):
                stats = self._experimenter.get_stats()
                details["total_experiments"] = stats.get("total_experiments", 0)
                details["successful_adoptions"] = stats.get("successful_adoptions", 0)
                details["running"] = stats.get("running", 0)

        except Exception as e:
            errors.append(f"Experimenter check failed: {e}")

        latency = (time.time() - start) * 1000

        if errors:
            status = HealthStatus.YELLOW
            message = "; ".join(errors)
        else:
            status = HealthStatus.GREEN
            message = f"Experimenter healthy: {details.get('total_experiments', 0)} experiments"

        return ComponentHealth(
            name="Experimenter",
            status=status,
            latency_ms=latency,
            message=message,
            details=details
        )

    async def check_world_model(self) -> ComponentHealth:
        """Check WorldModel: Building causal understanding?"""
        if not self._world_model:
            return ComponentHealth(
                name="WorldModel",
                status=HealthStatus.OFFLINE,
                message="WorldModel not initialized"
            )

        start = time.time()
        details = {}
        errors = []

        try:
            # Get entity count
            if hasattr(self._world_model, 'entities'):
                details["entity_count"] = len(self._world_model.entities)

            # Get rule count
            if hasattr(self._world_model, 'causal_rules'):
                details["causal_rules"] = len(self._world_model.causal_rules)

            # Check prediction capability
            if hasattr(self._world_model, 'can_predict'):
                details["can_predict"] = self._world_model.can_predict()

        except Exception as e:
            errors.append(f"WorldModel check failed: {e}")

        latency = (time.time() - start) * 1000

        if errors:
            status = HealthStatus.YELLOW
            message = "; ".join(errors)
        else:
            status = HealthStatus.GREEN
            message = f"WorldModel healthy: {details.get('entity_count', 0)} entities"

        return ComponentHealth(
            name="WorldModel",
            status=status,
            latency_ms=latency,
            message=message,
            details=details
        )

    async def check_episode_compressor(self) -> ComponentHealth:
        """Check EpisodeCompressor: Extracting wisdom?"""
        if not self._episode_compressor:
            return ComponentHealth(
                name="EpisodeCompressor",
                status=HealthStatus.OFFLINE,
                message="EpisodeCompressor not initialized"
            )

        start = time.time()
        details = {}
        errors = []

        try:
            # Get compression stats
            if hasattr(self._episode_compressor, 'get_stats'):
                stats = self._episode_compressor.get_stats()
                details.update(stats)

            # Check wisdom count
            if hasattr(self._episode_compressor, 'wisdom_count'):
                details["wisdom_extracted"] = self._episode_compressor.wisdom_count

        except Exception as e:
            errors.append(f"EpisodeCompressor check failed: {e}")

        latency = (time.time() - start) * 1000

        if errors:
            status = HealthStatus.YELLOW
            message = "; ".join(errors)
        else:
            status = HealthStatus.GREEN
            message = f"EpisodeCompressor healthy"

        return ComponentHealth(
            name="EpisodeCompressor",
            status=status,
            latency_ms=latency,
            message=message,
            details=details
        )

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _calculate_overall_status(self, components: List[ComponentHealth]) -> HealthStatus:
        """Calculate overall health status from component statuses."""
        if not components:
            return HealthStatus.OFFLINE

        # Count statuses
        status_counts = {
            HealthStatus.GREEN: 0,
            HealthStatus.YELLOW: 0,
            HealthStatus.RED: 0,
            HealthStatus.OFFLINE: 0,
        }

        for component in components:
            status_counts[component.status] += 1

        # Determine overall
        if status_counts[HealthStatus.RED] > 0 or status_counts[HealthStatus.OFFLINE] >= len(components) / 2:
            return HealthStatus.RED
        elif status_counts[HealthStatus.YELLOW] > 0 or status_counts[HealthStatus.OFFLINE] > 0:
            return HealthStatus.YELLOW
        else:
            return HealthStatus.GREEN

    def _suggest_fix(self, component_name: str, details: Dict) -> str:
        """Suggest a fix for a component issue."""
        suggestions = {
            "EventBus": "Check event subscribers and ensure event loop is running",
            "Heartbeat": "Restart heartbeat loop or check for blocking operations",
            "GapDetector": "Review prediction accuracy and surprise thresholds",
            "MissionAnchor": "Re-align actions with mission statement",
            "ValenceSystem": "Check for prolonged negative valence triggers",
            "UncertaintyTracker": "Recalibrate confidence estimates",
            "Memory": "Free up memory or increase storage capacity",
            "ImmuneSystem": "Review threat patterns and adjust sensitivity",
            "CuriosityEngine": "Prioritize gap filling or increase investigation resources",
            "SleepCycle": "Trigger sleep cycle to consolidate memories",
            "AttentionAllocator": "Rebalance attention budget or reduce concurrent tasks",
            "SelfModel": "Update capability model based on recent performance",
            "DreamEngine": "Improve simulation accuracy or training data",
            # New meta-cognition components
            "MetaLearner": "Check learning strategy effectiveness and consider strategy switch",
            "Experimenter": "Review pending experiments and adoption rate",
            "WorldModel": "Update causal rules with recent observations",
            "EpisodeCompressor": "Trigger memory compression or check episode queue",
        }

        return suggestions.get(component_name, "Review component logs and configuration")

    def diagnose_issues(self, report: HealthReport) -> List[Issue]:
        """
        Analyze health data and suggest fixes.

        This goes beyond individual component issues to find systemic problems.
        """
        systemic_issues = []

        # Check for correlated failures
        failed_components = [c.name for c in report.components if c.status == HealthStatus.RED]

        if len(failed_components) >= 3:
            systemic_issues.append(Issue(
                component="System",
                severity="critical",
                message=f"Multiple component failures detected: {', '.join(failed_components)}",
                suggestion="Restart organism or check for resource exhaustion"
            ))

        # Check for slow components
        slow_components = [c.name for c in report.components if c.latency_ms > 100]

        if len(slow_components) >= 2:
            systemic_issues.append(Issue(
                component="System",
                severity="warning",
                message=f"Multiple slow components: {', '.join(slow_components)}",
                suggestion="Check for CPU/memory pressure or blocking operations"
            ))

        # Check for offline components
        offline_components = [c.name for c in report.components if c.status == HealthStatus.OFFLINE]

        if offline_components:
            systemic_issues.append(Issue(
                component="System",
                severity="warning",
                message=f"Components not initialized: {', '.join(offline_components)}",
                suggestion="Initialize missing components or check startup sequence"
            ))

        return systemic_issues

    def print_report(self, report: HealthReport, verbose: bool = False):
        """Pretty print health report using Rich (or fallback to plain text)."""
        if RICH_AVAILABLE:
            self._print_report_rich(report, verbose)
        else:
            self._print_report_plain(report, verbose)

    def _print_report_rich(self, report: HealthReport, verbose: bool):
        """Print report using Rich library."""
        console = Console()

        # Overall status banner
        status_color = {
            HealthStatus.GREEN: "green",
            HealthStatus.YELLOW: "yellow",
            HealthStatus.RED: "red",
            HealthStatus.OFFLINE: "dim"
        }[report.overall_status]

        console.print(Panel(
            f"[bold {status_color}]{report.overall_status.value.upper()}[/bold {status_color}]",
            title="SIAO Health Status",
            subtitle=f"{report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            border_style=status_color
        ))

        # Summary table
        summary_table = Table(title="Summary", box=box.SIMPLE)
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="white")

        for key, value in report.summary.items():
            summary_table.add_row(key.replace('_', ' ').title(), str(value))

        console.print(summary_table)
        console.print()

        # Component status table
        component_table = Table(title="Components", box=box.ROUNDED)
        component_table.add_column("Component", style="cyan")
        component_table.add_column("Status", style="white")
        component_table.add_column("Latency", justify="right", style="white")
        component_table.add_column("Message", style="dim")

        for component in sorted(report.components, key=lambda c: c.status.value):
            status_emoji = {
                HealthStatus.GREEN: "✓",
                HealthStatus.YELLOW: "⚠",
                HealthStatus.RED: "✗",
                HealthStatus.OFFLINE: "○"
            }[component.status]

            component_table.add_row(
                component.name,
                f"{status_emoji} {component.status.value}",
                f"{component.latency_ms:.1f}ms",
                component.message[:50] if not verbose else component.message
            )

        console.print(component_table)

        # Issues
        if report.issues:
            console.print()
            issues_table = Table(title="Issues", box=box.ROUNDED)
            issues_table.add_column("Severity", style="white")
            issues_table.add_column("Component", style="cyan")
            issues_table.add_column("Issue", style="yellow")
            issues_table.add_column("Suggestion", style="dim")

            for issue in report.issues:
                severity_emoji = {
                    "critical": "🔴",
                    "warning": "🟡",
                    "info": "🔵"
                }[issue.severity]

                issues_table.add_row(
                    f"{severity_emoji} {issue.severity}",
                    issue.component,
                    issue.message[:40] if not verbose else issue.message,
                    issue.suggestion[:40] if not verbose else issue.suggestion
                )

            console.print(issues_table)

        # Verbose details
        if verbose:
            console.print()
            for component in report.components:
                if component.details:
                    detail_table = Table(title=f"{component.name} Details", box=box.SIMPLE)
                    detail_table.add_column("Key", style="cyan")
                    detail_table.add_column("Value", style="white")

                    for key, value in component.details.items():
                        detail_table.add_row(key, str(value))

                    console.print(detail_table)

    def _print_report_plain(self, report: HealthReport, verbose: bool):
        """Print report using plain text (fallback)."""
        print(f"\n{'='*60}")
        print(f"SIAO Health Status: {report.overall_status.value.upper()}")
        print(f"Timestamp: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        # Summary
        print("SUMMARY:")
        for key, value in report.summary.items():
            print(f"  {key.replace('_', ' ').title()}: {value}")

        # Components
        print(f"\nCOMPONENTS:")
        for component in sorted(report.components, key=lambda c: c.status.value):
            status_symbol = {
                HealthStatus.GREEN: "[OK]",
                HealthStatus.YELLOW: "[WARN]",
                HealthStatus.RED: "[FAIL]",
                HealthStatus.OFFLINE: "[OFF]"
            }[component.status]

            print(f"  {status_symbol} {component.name:20s} {component.latency_ms:6.1f}ms  {component.message}")

            if verbose and component.details:
                for key, value in component.details.items():
                    print(f"      {key}: {value}")

        # Issues
        if report.issues:
            print(f"\nISSUES:")
            for issue in report.issues:
                print(f"  [{issue.severity.upper()}] {issue.component}: {issue.message}")
                if verbose and issue.suggestion:
                    print(f"      Suggestion: {issue.suggestion}")

        print(f"\n{'='*60}\n")


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def quick_health_check(organism=None, siao_core=None, verbose: bool = False) -> HealthReport:
    """
    Quick health check convenience function.

    Args:
        organism: Organism instance
        siao_core: SIAO core instance
        verbose: Print verbose output

    Returns:
        HealthReport
    """
    checker = SIAOHealthChecker()
    checker.attach(organism=organism, siao_core=siao_core)
    report = await checker.check_all()

    if verbose:
        checker.print_report(report, verbose=True)

    return report


def create_health_checker(organism=None, siao_core=None) -> SIAOHealthChecker:
    """
    Create and attach a health checker.

    Args:
        organism: Organism instance
        siao_core: SIAO core instance

    Returns:
        SIAOHealthChecker instance
    """
    checker = SIAOHealthChecker()
    checker.attach(organism=organism, siao_core=siao_core)
    return checker
