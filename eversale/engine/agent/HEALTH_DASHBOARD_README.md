# Health Dashboard - Real-time Monitoring for Eversale

The Health Dashboard provides comprehensive real-time monitoring for the Eversale agent, tracking success rates, resource usage, component health, and performance metrics across all operations.

## Features

### 1. **Domain Metrics Tracking**
- Request count per domain
- Success/failure rates
- Average response times
- CAPTCHA encounter rates
- Login success rates
- Error type distribution

### 2. **Resource Monitoring**
- Memory usage (current, peak, percentage)
- CPU usage percentage
- Disk space for outputs directory
- Open file handles
- Thread count

### 3. **Component Health**
- Browser status (running, crashed, idle)
- Ollama/LLM status (connected, latency)
- MCP server status
- Automatic health checks with latency tracking

### 4. **Alerting & Anomaly Detection**
- Memory > 80% = warning
- Memory > 95% = critical
- Failure rate > 50% = alert
- Response time > 30s = slow
- Anomaly detection based on baseline metrics

### 5. **Trend Analysis**
- Track CPU and memory trends over time
- Detect improving/stable/degrading patterns
- Historical data for last 60 minutes

### 6. **Export Formats**
- JSON (full metrics export)
- Prometheus (for external monitoring)
- Rich CLI dashboard (pretty terminal output)
- Simple text summary

## Quick Start

### Basic Usage

```python
from agent.health_dashboard import get_dashboard

# Get global dashboard instance (auto-starts monitoring)
dashboard = get_dashboard()

# Record a web request
dashboard.record_request(
    url="https://example.com/page",
    success=True,
    response_time=2.5,  # seconds
    is_captcha=False
)

# Record a login attempt
dashboard.record_login_attempt(
    url="https://example.com/login",
    success=True
)

# Update component health
dashboard.update_component_health(
    'browser',
    status='healthy',  # 'healthy', 'degraded', 'down'
    metadata={'contexts': 1}
)

# Get health summary
summary = dashboard.get_health_summary()
print(summary['overall_status'])  # 'healthy', 'warning', 'critical'

# Print pretty dashboard
dashboard.print_dashboard()

# Print simple summary
dashboard.print_simple_summary()

# Export metrics
json_metrics = dashboard.get_metrics_json()
prometheus_metrics = dashboard.get_prometheus_format()

# Save to file
from pathlib import Path
dashboard.save_metrics(Path("outputs/health_metrics.json"))
```

### Integration with Brain

```python
from agent.health_dashboard_integration import add_health_tracking_to_brain

# Add health tracking to existing brain
brain = create_enhanced_brain(config, mcp_client)
brain = add_health_tracking_to_brain(brain)

# Now all tool executions are automatically tracked
# Access dashboard via brain.health_dashboard
```

### Component Health Checks

```python
# Check browser health
status = dashboard.check_browser_health(browser)
# Returns: 'healthy', 'degraded', or 'down'

# Check Ollama health (async)
status = await dashboard.check_ollama_health(ollama_client, model="qwen2.5:7b-instruct")
# Also measures latency in milliseconds

# Check MCP health
status = dashboard.check_mcp_health(mcp_client)
```

### Anomaly Detection

```python
# Detect anomalies based on baseline metrics
anomalies = dashboard.detect_anomalies()
# Returns list like:
# ["CPU spike: 85.2% (baseline: 45.1%)",
#  "Memory spike: 78.5% (baseline: 52.3%)"]

# Get trend for a metric
trend = dashboard.get_trend('cpu', window_minutes=10)
# Returns: 'improving', 'stable', 'degrading', or 'unknown'

trend = dashboard.get_trend('memory', window_minutes=10)
```

## Alert Thresholds

The dashboard uses the following default thresholds:

| Metric | Warning | Critical |
|--------|---------|----------|
| Memory | 80% | 95% |
| CPU | 80% | - |
| Failure Rate | 50% | - |
| Response Time | 30s | - |

These generate automatic alerts in the health summary.

## Output Examples

### 1. Rich Dashboard (Terminal)

```
╭──────────────────────────────────────────────────────────────────╮
│ Eversale Health Dashboard | Status: HEALTHY | 2025-12-07 19:28  │
╰──────────────────────────────────────────────────────────────────╯
╭─────── Resources ───────╮╭────── Top Domains ──────╮
│   System Resources      ││   Domain Metrics        │
│ Memory    28.4 MB (0.2%)││ example.com             │
│ CPU       9.9%          ││   Requests: 10          │
│ Disk      0.00 GB       ││   Success: 95.0%        │
│ Open Files 1            ││   Avg: 1.8s             │
│ Threads   2             ││                         │
╰─────────────────────────╯╰─────────────────────────╯
╭────── Components ───────╮╭── Alerts & Anomalies ───╮
│ Browser   HEALTHY       ││ No alerts               │
│ Ollama    HEALTHY       ││                         │
│ MCP       HEALTHY       ││                         │
╰─────────────────────────╯╰─────────────────────────╯
```

### 2. JSON Export

```json
{
  "timestamp": "2025-12-07T19:28:15.374592",
  "overall_status": "healthy",
  "alerts": [],
  "domain_metrics": {
    "example.com": {
      "request_count": 10,
      "success_rate": 95.0,
      "failure_rate": 5.0,
      "avg_response_time": 1.8,
      "captcha_rate": 10.0,
      "login_success_rate": 100.0
    }
  },
  "resources": {
    "memory_mb": 28.42,
    "memory_percent": 0.18,
    "cpu_percent": 9.9,
    "disk_usage_gb": 0.0
  },
  "components": {
    "browser": {"status": "healthy", "latency_ms": null},
    "ollama": {"status": "healthy", "latency_ms": 850}
  }
}
```

### 3. Prometheus Format

```
eversale_domain_requests_total{domain="example.com"} 10 1765164435374
eversale_domain_success_rate{domain="example.com"} 95.00 1765164435374
eversale_domain_avg_response_time{domain="example.com"} 1.80 1765164435374
eversale_memory_mb 28.42 1765164435374
eversale_memory_percent 0.18 1765164435374
eversale_cpu_percent 9.90 1765164435374
eversale_component_health{component="browser"} 2 1765164435374
eversale_component_health{component="ollama"} 2 1765164435374
```

## Integration Patterns

### Pattern 1: ReAct Loop Integration

```python
from agent.health_dashboard import get_dashboard

async def react_loop_iteration(brain, task):
    dashboard = get_dashboard()

    # Check health before iteration
    if iteration % 5 == 0:
        summary = dashboard.get_health_summary()
        if summary['resources']['memory_percent'] > 80:
            logger.warning("High memory usage!")

    # Execute tools (automatically tracked if using wrapper)
    result = await brain.tool_executor.execute_tool(tool_name, args)

    # Manual tracking (if not using wrapper)
    dashboard.record_request(
        url=args.get('url'),
        success=result.success,
        response_time=result.duration
    )
```

### Pattern 2: Standalone Monitoring

```python
from agent.health_dashboard import get_dashboard
import asyncio

async def monitor_forever():
    dashboard = get_dashboard()

    while True:
        # Print dashboard every 30 seconds
        dashboard.print_dashboard()

        # Check for anomalies
        anomalies = dashboard.detect_anomalies()
        if anomalies:
            for anomaly in anomalies:
                logger.warning(anomaly)

        await asyncio.sleep(30)

# Run in background
asyncio.create_task(monitor_forever())
```

### Pattern 3: Health-Aware Tool Execution

```python
from agent.health_dashboard_integration import HealthAwareToolExecutor

# Wrap existing tool executor
health_aware_executor = HealthAwareToolExecutor(
    tool_executor=brain.tool_executor,
    health_dashboard=dashboard
)

# All executions now tracked automatically
result = await health_aware_executor.execute_tool('playwright_navigate', {
    'url': 'https://example.com'
})
```

## Advanced Features

### Custom Alert Thresholds

```python
dashboard = HealthDashboard()

# Customize thresholds
dashboard.MEMORY_WARNING_THRESHOLD = 70  # Percent
dashboard.MEMORY_CRITICAL_THRESHOLD = 90
dashboard.CPU_WARNING_THRESHOLD = 85
dashboard.FAILURE_RATE_ALERT_THRESHOLD = 30
dashboard.SLOW_RESPONSE_THRESHOLD = 20  # Seconds

dashboard.start_monitoring()
```

### Historical Analysis

```python
# Access historical snapshots
for snapshot in dashboard.snapshot_history:
    print(f"{snapshot.timestamp}: {snapshot.overall_status}")
    for domain, metrics in snapshot.domain_metrics.items():
        print(f"  {domain}: {metrics.success_rate:.1f}% success")

# Analyze trends over time
cpu_trend = dashboard.get_trend('cpu', window_minutes=30)
memory_trend = dashboard.get_trend('memory', window_minutes=30)
```

### Periodic Health Reports

```python
from pathlib import Path
import time

# Save health report every 5 minutes
while True:
    timestamp = int(time.time())
    dashboard.save_metrics(Path(f"reports/health_{timestamp}.json"))
    time.sleep(300)  # 5 minutes
```

## Performance Impact

The health dashboard is designed to be lightweight:

- **Background monitoring**: ~0.1% CPU overhead
- **Memory footprint**: ~5-10 MB (includes 60 minutes of history)
- **Metric recording**: <1ms per call
- **Dashboard rendering**: ~50ms

For production use with minimal overhead:
- Use `print_simple_summary()` instead of `print_dashboard()` (no Rich formatting)
- Reduce `history_duration_minutes` (default: 60)
- Increase `monitoring_interval_seconds` (default: 5.0)

## Troubleshooting

### High Memory Usage Alerts

```python
# Check which domains are consuming resources
summary = dashboard.get_health_summary()
for domain, metrics in summary['domain_metrics'].items():
    if metrics['avg_response_time'] > 10:
        logger.warning(f"{domain} is slow: {metrics['avg_response_time']:.1f}s")
```

### Component Health Issues

```python
# Detailed component check
summary = dashboard.get_health_summary()
for comp_name, comp in summary['components'].items():
    if comp['status'] != 'healthy':
        logger.error(f"{comp_name} is {comp['status']}: {comp['error']}")

        # Re-initialize component
        if comp_name == 'browser':
            await brain.browser_manager.reconnect()
```

### Missing psutil

If `psutil` is not installed, resource monitoring will be limited. Install with:

```bash
pip install psutil
```

The dashboard will still work without `psutil`, but won't collect:
- Memory usage
- CPU usage
- Disk usage
- Open file handles
- Thread count

## Files

| File | Purpose |
|------|---------|
| `health_dashboard.py` | Main dashboard implementation |
| `health_dashboard_integration.py` | Integration examples and wrappers |
| `HEALTH_DASHBOARD_README.md` | This documentation |

## Example Commands

```bash
# Test dashboard directly
python3 agent/health_dashboard.py

# Run integration examples
python3 agent/health_dashboard_integration.py

# Monitor agent process
python3 -c "from agent.health_dashboard import get_dashboard; import time; d = get_dashboard(); [time.sleep(5) or d.print_simple_summary() for _ in range(10)]"
```

## Future Enhancements

Potential additions (not yet implemented):

- [ ] Webhook alerts for critical conditions
- [ ] Email/Slack notifications
- [ ] Grafana dashboard integration
- [ ] Historical metric persistence to database
- [ ] Per-tool execution time tracking
- [ ] Network bandwidth monitoring
- [ ] Correlation analysis (e.g., high CPU → slow responses)
- [ ] Auto-scaling recommendations based on metrics

## Contributing

To add new metrics:

1. Add metric to appropriate dataclass (`DomainMetrics`, `ResourceMetrics`, etc.)
2. Update `_collect_resource_metrics()` or add recording method
3. Update `get_health_summary()` to include in export
4. Update `print_dashboard()` to display in UI
5. Update `get_prometheus_format()` for Prometheus export

## License

Part of Eversale - Autonomous AI Worker
