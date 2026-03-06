# Health Monitoring System

A continuous health monitoring system for the Eversale agent that writes periodic health reports for external monitoring.

## Overview

The health monitoring system runs in a background thread and writes a JSON health file (`~/.eversale/health.json`) every 30 seconds. External monitoring systems can check this file to verify the agent is alive and healthy.

## Features

- **Automatic health reporting** every 30 seconds
- **Health file location**: `~/.eversale/health.json`
- **Metrics tracked**:
  - Timestamp (ISO format)
  - Status (running, idle, error, stopped)
  - Last activity description
  - Iterations completed
  - Errors count
  - Memory usage (MB)
  - Uptime (seconds)
  - Process ID
- **CLI command** to check health: `eversale health-check`
- **Liveness detection**: Agent considered dead if health file is older than 2 minutes

## Usage

### In Python Code

```python
from health_check import HealthWriter

# Create and start health monitoring
health = HealthWriter()
health.start()

# Update activity throughout execution
health.update_activity("Processing task...")
health.increment_iterations()

# Record errors
health.increment_errors()
health.set_status("error")

# Stop when done
health.stop()
```

### CLI Command

Check agent health status:

```bash
eversale health-check
```

Exit codes:
- `0` = Agent is alive and healthy
- `1` = Agent is dead (health file too old or missing)
- `2` = Agent has errors

### Programmatic Health Check

```python
from health_check import is_agent_alive, read_health

# Check if agent is alive
if is_agent_alive():
    print("Agent is running")
else:
    print("Agent is dead")

# Read full health data
health = read_health()
if health:
    print(f"Status: {health['status']}")
    print(f"Iterations: {health['iterations_completed']}")
    print(f"Errors: {health['errors_count']}")
```

## Integration with Orchestration

The health monitoring system is automatically integrated into the orchestration loop methods:

- `_timed_loop()` - Timed duration loops
- `_infinite_loop()` - Forever/24-7 loops
- `_counted_loop()` - Counted iteration loops
- `_scheduled_loop()` - Scheduled recurring tasks

Health monitoring starts automatically when these loop modes are activated and stops when they complete.

### Example Integration

When you run:
```bash
eversale "Monitor inbox forever"
```

The system:
1. Detects forever mode
2. Starts health monitoring automatically
3. Updates health status every iteration:
   - Activity: "Iteration 123: Monitor inbox"
   - Increments iteration counter
   - Records errors if any occur
4. Writes health.json every 30 seconds
5. Stops health monitoring on exit

## Health File Format

```json
{
  "timestamp": "2025-12-11T20:30:45.123456",
  "status": "running",
  "last_activity": "Iteration 42: Monitor inbox forever",
  "iterations_completed": 42,
  "errors_count": 0,
  "memory_mb": 256.5,
  "uptime_seconds": 1234.56,
  "last_heartbeat": "2025-12-11T20:30:45.123456",
  "process_id": 12345,
  "version": "2.0"
}
```

## External Monitoring

External monitoring systems can check agent health by:

1. **Reading the health file**:
   ```bash
   cat ~/.eversale/health.json
   ```

2. **Checking timestamp freshness**:
   ```bash
   # Linux/Mac
   python3 -c "
   import json
   from datetime import datetime
   from pathlib import Path

   health_file = Path.home() / '.eversale' / 'health.json'
   if not health_file.exists():
       print('Agent not running')
       exit(1)

   health = json.loads(health_file.read_text())
   timestamp = datetime.fromisoformat(health['timestamp'])
   age = (datetime.now() - timestamp).total_seconds()

   if age > 120:
       print(f'Agent is DEAD (last seen {age:.0f}s ago)')
       exit(1)
   else:
       print(f'Agent is ALIVE ({age:.0f}s ago)')
       exit(0)
   "
   ```

3. **Using the CLI command**:
   ```bash
   eversale health-check
   ```

## Monitoring Dashboard Integration

The health file can be integrated with monitoring dashboards:

### Grafana

Use the JSON API datasource to read the health file periodically:

```json
{
  "targets": [
    {
      "target": "file://~/.eversale/health.json",
      "type": "timeseries"
    }
  ]
}
```

### Custom Monitoring Script

```python
#!/usr/bin/env python3
"""
Custom monitoring script - alerts if agent is dead.
Run this as a cron job every minute.
"""
import json
import smtplib
from datetime import datetime
from pathlib import Path

def check_and_alert():
    health_file = Path.home() / '.eversale' / 'health.json'

    if not health_file.exists():
        send_alert("Agent health file not found")
        return

    try:
        health = json.loads(health_file.read_text())
        timestamp = datetime.fromisoformat(health['timestamp'])
        age = (datetime.now() - timestamp).total_seconds()

        if age > 120:
            send_alert(f"Agent is DEAD (last seen {age:.0f}s ago)")
        elif health.get('errors_count', 0) > 10:
            send_alert(f"Agent has {health['errors_count']} errors")
    except Exception as e:
        send_alert(f"Failed to read health file: {e}")

def send_alert(message):
    # Send email, Slack, PagerDuty, etc.
    print(f"ALERT: {message}")

if __name__ == "__main__":
    check_and_alert()
```

## Configuration

Health monitoring can be configured by modifying the constants in `health_check.py`:

```python
HEALTH_INTERVAL = 30  # Write health file every N seconds
HEALTH_TIMEOUT = 120  # Agent considered dead after N seconds
```

## Troubleshooting

### Health file not found

The agent has never run with health monitoring enabled, or the health monitoring system failed to start.

**Solution**: Ensure you're running a loop mode (timed, infinite, counted, or scheduled) that enables health monitoring.

### Health file too old

The agent stopped unexpectedly or is hung.

**Solution**:
1. Check if the process is still running: `ps aux | grep run_ultimate`
2. Check logs: `tail -f logs/eversale.log`
3. Restart the agent

### High error count

The agent is encountering repeated errors.

**Solution**:
1. Check the health file for error count: `eversale health-check`
2. Review logs for error details
3. Check if circuit breaker is open (backing off)

## Related Modules

- **forever_operations.py** - Base infrastructure for 24/7 operations
- **orchestration.py** - Loop execution with health monitoring integration
- **HeartbeatReport** - Similar concept in forever_operations.py (but different implementation)

## Differences from HeartbeatReport

The `HeartbeatReport` class in `forever_operations.py` is part of the ForeverWorker system and writes heartbeat data to worker-specific directories. The new `health_check.py` module:

- **Simpler**: Single global health file for the entire agent
- **Standardized location**: Always `~/.eversale/health.json`
- **CLI-friendly**: Direct command `eversale health-check`
- **External monitoring**: Designed for monitoring dashboards
- **Automatic integration**: Works with orchestration loop modes

Both systems can coexist. Use `health_check.py` for simple external monitoring and `HeartbeatReport` for complex multi-worker scenarios.

## License

Part of the Eversale agent system.
