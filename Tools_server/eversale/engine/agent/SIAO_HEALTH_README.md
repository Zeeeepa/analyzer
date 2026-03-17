# SIAO Health Checker

Comprehensive health monitoring system for all SIAO organism components.

## Overview

The SIAO Health Checker verifies that all components of the organism are functioning correctly by testing each component individually and analyzing the overall system health. It's designed to catch issues early and provide actionable diagnostic information.

## Components Monitored

The health checker tests 13 core organism components:

### Core Organism (organism_core.py)
1. **EventBus** - Nervous system message delivery
2. **Heartbeat** - Continuous pulse and metrics collection
3. **GapDetector** - Prediction/comparison cycle for surprises
4. **MissionAnchor** - Identity and alignment tracking

### Extended SIAO Components
5. **ValenceSystem** - Emotional gradient (pain to pleasure)
6. **UncertaintyTracker** - Confidence scoring and calibration
7. **Memory** - Storage and retrieval operations
8. **ImmuneSystem** - Threat detection and input screening
9. **CuriosityEngine** - Knowledge gap detection and filling
10. **SleepCycle** - Tiredness tracking and consolidation
11. **AttentionAllocator** - Budget management and allocation
12. **SelfModel** - Capability tracking and self-awareness
13. **DreamEngine** - Simulation and prediction

## Health Status Levels

Each component receives one of four health statuses:

- **GREEN** ✓ - Healthy, all systems operational
- **YELLOW** ⚠ - Degraded, some issues but functional
- **RED** ✗ - Failing, critical issues detected
- **OFFLINE** ○ - Not running or not initialized

## Quick Start

### Basic Usage

```python
from agent.siao_health import quick_health_check

# Quick check with output
report = await quick_health_check(organism=organism, verbose=True)
```

### Detailed Usage

```python
from agent.siao_health import SIAOHealthChecker

# Create checker
checker = SIAOHealthChecker()
checker.attach(organism=organism, siao_core=siao_core)

# Run full health check
report = await checker.check_all()

# Print formatted report
checker.print_report(report, verbose=True)

# Analyze systemic issues
systemic_issues = checker.diagnose_issues(report)

# Save report to file
report.save_to_file(Path("memory/health_reports/report.json"))
```

### Command Line Testing

```bash
# Basic health check
python3 test_siao_health.py --basic

# Check with running organism
python3 test_siao_health.py --organism

# Full SIAO stack check
python3 test_siao_health.py --full

# Performance benchmarks
python3 test_siao_health.py --benchmark

# Save report to file
python3 test_siao_health.py --organism --save-report

# All tests
python3 test_siao_health.py --all --verbose
```

## What Each Check Tests

### EventBus Check
- Can subscribe to events
- Can publish events
- Event delivery latency
- Event history tracking
- Event counts per minute

**Healthy if**: Latency < 100ms, events delivered successfully

### Heartbeat Check
- Is the heartbeat running
- Beat count and uptime
- Error rate, gap rate, confidence
- Memory pressure
- Metric collection

**Healthy if**: Alive, error rate < 0.5, memory pressure < 0.9

### GapDetector Check
- Can generate predictions
- Can compare predictions to reality
- Gap scoring accuracy
- Surprise rate
- Recurring patterns

**Healthy if**: Surprise rate < 0.7

### MissionAnchor Check
- Mission statement intact
- Core values present
- Alignment scoring works
- Alignment trend tracking
- Drift detection

**Healthy if**: No drift detected, alignment > 0.3

### ValenceSystem Check
- Emotional profile tracking
- Current valence state
- Mood classification
- Volatility measurement

**Healthy if**: Not in extreme negative state (< -0.8)

### UncertaintyTracker Check
- Confidence assessment works
- Calibration accuracy
- Recommended actions

**Healthy if**: Calibration accuracy > 0.6

### Memory Check
- Can store data
- Can retrieve data
- Storage integrity
- Memory utilization

**Healthy if**: Utilization < 0.9, data integrity maintained

### ImmuneSystem Check
- Can screen inputs
- Threat patterns loaded
- Screening accuracy
- Threat detection rate

**Healthy if**: Threat rate reasonable (< 0.3)

### CuriosityEngine Check
- Gap statistics tracking
- Gap prioritization
- Investigation progress

**Healthy if**: Open gaps manageable (< 100)

### SleepCycle Check
- Tiredness tracking
- Sleep state management
- Consolidation statistics

**Healthy if**: Not exhausted (tiredness < 0.9)

### AttentionAllocator Check
- Budget status
- Allocation efficiency
- Resource management

**Healthy if**: Budget not exhausted, efficiency > 0.5

### SelfModel Check
- Identity awareness
- Capability tracking
- Learning statistics
- Confidence calibration

**Healthy if**: Confidence accuracy > 0.6

### DreamEngine Check
- Can simulate scenarios
- Dream statistics
- Prediction accuracy

**Healthy if**: Prediction accuracy > 0.5

## Report Structure

### HealthReport

```python
@dataclass
class HealthReport:
    timestamp: datetime
    overall_status: HealthStatus
    components: List[ComponentHealth]
    issues: List[Issue]
    summary: Dict[str, Any]
```

### ComponentHealth

```python
@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus
    latency_ms: float
    message: str
    details: Dict[str, Any]
```

### Issue

```python
@dataclass
class Issue:
    component: str
    severity: str  # "critical", "warning", "info"
    message: str
    suggestion: str
```

## Interpreting Results

### Overall Status

The overall status is determined by:
- **RED**: Any critical failures or > 50% offline
- **YELLOW**: Any degraded components or some offline
- **GREEN**: All components healthy

### Common Issues and Solutions

| Issue | Likely Cause | Solution |
|-------|--------------|----------|
| EventBus slow (>100ms) | Too many subscribers | Optimize event handlers |
| Heartbeat not running | Not started | Call `await organism.start()` |
| High surprise rate | Poor predictions | Review prediction logic |
| Mission drift | Misaligned actions | Check mission alignment |
| Extreme negative valence | Repeated failures | Investigate failure causes |
| Low calibration | Poor confidence estimates | Recalibrate with more data |
| High memory usage | Memory leak | Trigger consolidation |
| High threat rate | Too sensitive | Adjust threat thresholds |
| Many open gaps | Slow investigation | Increase gap filling resources |
| Extreme tiredness | No sleep cycles | Trigger sleep/consolidation |
| Budget exhausted | Over-allocation | Rebalance attention budget |
| Low confidence accuracy | Miscalibration | Update self-model with outcomes |
| Low prediction accuracy | Poor training data | Improve dream simulation data |

## Performance Benchmarks

Typical performance on modern hardware:

- **Individual component check**: 0.1-12ms
- **Full health check (13 components)**: 10-50ms
- **Checks run in parallel**: Yes (async/await)

## Integration Examples

### Scheduled Health Monitoring

```python
async def health_monitor_loop():
    """Run health checks every 5 minutes."""
    checker = create_health_checker(organism=organism)

    while True:
        report = await checker.check_all()

        if report.overall_status == HealthStatus.RED:
            logger.critical("CRITICAL: Organism health RED")
            # Trigger alerts, emergency protocols

        await asyncio.sleep(300)  # 5 minutes
```

### Pre-Task Health Check

```python
async def safe_execute_task(task):
    """Execute task only if organism is healthy."""
    report = await quick_health_check(organism=organism)

    if report.overall_status == HealthStatus.RED:
        raise Exception("Organism unhealthy, aborting task")

    return await execute_task(task)
```

### Health-Based Circuit Breaker

```python
class HealthCircuitBreaker:
    """Circuit breaker based on organism health."""

    async def check(self):
        report = await quick_health_check(organism=self.organism)

        critical_issues = sum(
            1 for c in report.components
            if c.status == HealthStatus.RED
        )

        if critical_issues >= 3:
            # Trip circuit breaker
            self.state = "OPEN"
            logger.error("Circuit breaker OPEN due to health issues")
```

## Files

- **`agent/siao_health.py`** - Main health checker implementation
- **`test_siao_health.py`** - Test suite and examples
- **`memory/health_reports/`** - Saved health reports (JSON)

## Dependencies

### Required
- `asyncio` - Async health checks
- `dataclasses` - Data structures
- `loguru` - Logging

### Optional
- `rich` - Pretty terminal output (fallback to plain text if not available)

## Future Enhancements

- [ ] Historical health trend analysis
- [ ] Predictive health alerts (detect degradation before failure)
- [ ] Auto-healing triggers (restart components on failure)
- [ ] Health metrics export (Prometheus, Grafana)
- [ ] Real-time health dashboard
- [ ] Health-based load shedding
- [ ] Component dependency graph analysis
- [ ] Health check caching for high-frequency monitoring

## See Also

- `organism_core.py` - Core organism components
- `valence_system.py` - Emotional gradient system
- `self_model.py` - Self-awareness and capability tracking
- `health_monitor.py` - Legacy health monitoring (to be replaced)
