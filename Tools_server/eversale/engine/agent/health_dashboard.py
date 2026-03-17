"""
Health Dashboard - Real-time metrics and health monitoring

Features:
- Track success/failure rates per domain
- Memory and CPU usage monitoring
- Browser health status
- LLM latency tracking
- Export metrics to JSON/Prometheus format

Integration:
- Hooks into react_loop to record metrics
- Background thread for resource monitoring
- Export endpoint for external monitoring
"""

import asyncio
import json
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Deque
from urllib.parse import urlparse

from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich import box
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

# Optional psutil import - graceful fallback if not installed
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not installed - resource monitoring will be limited")


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class DomainMetrics:
    """Metrics for a specific domain."""
    domain: str
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_response_time: float = 0.0  # Sum of all response times in seconds
    captcha_encounters: int = 0
    login_attempts: int = 0
    login_successes: int = 0
    last_accessed: Optional[datetime] = None
    error_types: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.request_count == 0:
            return 0.0
        return (self.success_count / self.request_count) * 100

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate as percentage."""
        if self.request_count == 0:
            return 0.0
        return (self.failure_count / self.request_count) * 100

    @property
    def avg_response_time(self) -> float:
        """Calculate average response time in seconds."""
        if self.request_count == 0:
            return 0.0
        return self.total_response_time / self.request_count

    @property
    def captcha_rate(self) -> float:
        """Calculate CAPTCHA encounter rate as percentage."""
        if self.request_count == 0:
            return 0.0
        return (self.captcha_encounters / self.request_count) * 100

    @property
    def login_success_rate(self) -> float:
        """Calculate login success rate as percentage."""
        if self.login_attempts == 0:
            return 0.0
        return (self.login_successes / self.login_attempts) * 100


@dataclass
class ResourceMetrics:
    """System resource usage metrics."""
    timestamp: datetime = field(default_factory=datetime.now)
    memory_mb: float = 0.0
    memory_percent: float = 0.0
    cpu_percent: float = 0.0
    disk_usage_gb: float = 0.0
    disk_percent: float = 0.0
    open_file_handles: int = 0
    thread_count: int = 0


@dataclass
class ComponentHealth:
    """Health status of a component."""
    name: str
    status: str  # 'healthy', 'degraded', 'down'
    last_check: datetime = field(default_factory=datetime.now)
    latency_ms: Optional[float] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthSnapshot:
    """Complete health snapshot at a point in time."""
    timestamp: datetime = field(default_factory=datetime.now)
    overall_status: str = 'healthy'  # 'healthy', 'warning', 'critical'
    domain_metrics: Dict[str, DomainMetrics] = field(default_factory=dict)
    resource_metrics: ResourceMetrics = field(default_factory=ResourceMetrics)
    component_health: Dict[str, ComponentHealth] = field(default_factory=dict)
    alerts: List[str] = field(default_factory=list)


# =============================================================================
# Health Dashboard
# =============================================================================

class HealthDashboard:
    """
    Real-time health monitoring dashboard for Eversale agent.

    Tracks:
    - Domain-specific success/failure rates
    - Resource usage (memory, CPU, disk)
    - Component health (browser, LLM, MCP)
    - Historical trends and anomaly detection
    """

    # Alert thresholds
    MEMORY_WARNING_THRESHOLD = 80  # Percent
    MEMORY_CRITICAL_THRESHOLD = 95  # Percent
    CPU_WARNING_THRESHOLD = 80  # Percent
    FAILURE_RATE_ALERT_THRESHOLD = 50  # Percent
    SLOW_RESPONSE_THRESHOLD = 30  # Seconds

    def __init__(
        self,
        history_duration_minutes: int = 60,
        monitoring_interval_seconds: float = 5.0,
        outputs_dir: Path = Path("outputs")
    ):
        """
        Initialize health dashboard.

        Args:
            history_duration_minutes: How long to keep historical metrics
            monitoring_interval_seconds: How often to collect resource metrics
            outputs_dir: Directory to monitor for disk usage
        """
        self.history_duration = timedelta(minutes=history_duration_minutes)
        self.monitoring_interval = monitoring_interval_seconds
        self.outputs_dir = outputs_dir

        # Domain metrics tracking
        self.domain_metrics: Dict[str, DomainMetrics] = {}
        self._domain_lock = threading.Lock()

        # Resource metrics history (circular buffer)
        self.resource_history: Deque[ResourceMetrics] = deque(maxlen=int(
            history_duration_minutes * 60 / monitoring_interval_seconds
        ))
        self._resource_lock = threading.Lock()

        # Component health tracking
        self.component_health: Dict[str, ComponentHealth] = {}
        self._component_lock = threading.Lock()

        # Historical snapshots for trend analysis
        self.snapshot_history: Deque[HealthSnapshot] = deque(maxlen=60)  # Last 60 snapshots
        self._snapshot_lock = threading.Lock()

        # Background monitoring
        self._monitoring_thread: Optional[threading.Thread] = None
        self._running = False
        self._process = psutil.Process() if PSUTIL_AVAILABLE else None

        # Anomaly tracking
        self._baseline_cpu = 0.0
        self._baseline_memory = 0.0
        self._baseline_calculated = False

        # Rich console for pretty output
        self.console = Console()

        logger.info("HealthDashboard initialized")

    # =========================================================================
    # Lifecycle Management
    # =========================================================================

    def start_monitoring(self):
        """Start background resource monitoring."""
        if self._running:
            logger.warning("Monitoring already running")
            return

        self._running = True
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="HealthDashboard-Monitor"
        )
        self._monitoring_thread.start()
        logger.info(f"Background monitoring started (interval: {self.monitoring_interval}s)")

    def stop_monitoring(self):
        """Stop background monitoring."""
        if not self._running:
            return

        self._running = False
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=2)
        logger.info("Background monitoring stopped")

    def _monitoring_loop(self):
        """Background loop to collect resource metrics."""
        while self._running:
            try:
                metrics = self._collect_resource_metrics()
                with self._resource_lock:
                    self.resource_history.append(metrics)

                # Calculate baseline after 10 samples
                if not self._baseline_calculated and len(self.resource_history) >= 10:
                    self._calculate_baseline()

                # Clean up old snapshots
                self._cleanup_old_snapshots()

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")

            time.sleep(self.monitoring_interval)

    def _collect_resource_metrics(self) -> ResourceMetrics:
        """Collect current resource usage metrics."""
        metrics = ResourceMetrics()

        if not PSUTIL_AVAILABLE:
            return metrics

        try:
            # Memory usage
            mem_info = self._process.memory_info()
            metrics.memory_mb = mem_info.rss / (1024 * 1024)  # Convert to MB
            metrics.memory_percent = self._process.memory_percent()

            # CPU usage
            metrics.cpu_percent = self._process.cpu_percent(interval=0.1)

            # Disk usage for outputs directory
            if self.outputs_dir.exists():
                disk_usage = psutil.disk_usage(str(self.outputs_dir))
                metrics.disk_usage_gb = disk_usage.used / (1024 ** 3)
                metrics.disk_percent = disk_usage.percent

            # File handles and threads
            metrics.open_file_handles = len(self._process.open_files())
            metrics.thread_count = self._process.num_threads()

        except Exception as e:
            logger.error(f"Error collecting resource metrics: {e}")

        return metrics

    def _calculate_baseline(self):
        """Calculate baseline resource usage for anomaly detection."""
        with self._resource_lock:
            if len(self.resource_history) < 10:
                return

            cpu_values = [m.cpu_percent for m in self.resource_history]
            memory_values = [m.memory_percent for m in self.resource_history]

            self._baseline_cpu = sum(cpu_values) / len(cpu_values)
            self._baseline_memory = sum(memory_values) / len(memory_values)
            self._baseline_calculated = True

            logger.info(f"Baseline calculated - CPU: {self._baseline_cpu:.1f}%, Memory: {self._baseline_memory:.1f}%")

    def _cleanup_old_snapshots(self):
        """Remove snapshots older than history_duration."""
        cutoff_time = datetime.now() - self.history_duration
        with self._snapshot_lock:
            # Deque already handles max size, but clean based on time too
            while self.snapshot_history and self.snapshot_history[0].timestamp < cutoff_time:
                self.snapshot_history.popleft()

    # =========================================================================
    # Domain Metrics Recording
    # =========================================================================

    def record_request(
        self,
        url: str,
        success: bool,
        response_time: float,
        error_type: Optional[str] = None,
        is_captcha: bool = False
    ):
        """
        Record a request to a domain.

        Args:
            url: Full URL of the request
            success: Whether the request succeeded
            response_time: Response time in seconds
            error_type: Type of error if failed (e.g., 'timeout', 'connection_error')
            is_captcha: Whether a CAPTCHA was encountered
        """
        domain = self._extract_domain(url)

        with self._domain_lock:
            if domain not in self.domain_metrics:
                self.domain_metrics[domain] = DomainMetrics(domain=domain)

            metrics = self.domain_metrics[domain]
            metrics.request_count += 1
            metrics.total_response_time += response_time
            metrics.last_accessed = datetime.now()

            if success:
                metrics.success_count += 1
            else:
                metrics.failure_count += 1
                if error_type:
                    metrics.error_types[error_type] += 1

            if is_captcha:
                metrics.captcha_encounters += 1

    def record_login_attempt(self, url: str, success: bool):
        """
        Record a login attempt for a domain.

        Args:
            url: URL of the login page
            success: Whether login succeeded
        """
        domain = self._extract_domain(url)

        with self._domain_lock:
            if domain not in self.domain_metrics:
                self.domain_metrics[domain] = DomainMetrics(domain=domain)

            metrics = self.domain_metrics[domain]
            metrics.login_attempts += 1
            if success:
                metrics.login_successes += 1

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc or parsed.path.split('/')[0] or 'unknown'
        except Exception:
            return 'unknown'

    # =========================================================================
    # Component Health Tracking
    # =========================================================================

    def update_component_health(
        self,
        component_name: str,
        status: str,
        latency_ms: Optional[float] = None,
        error_message: Optional[str] = None,
        **metadata
    ):
        """
        Update health status of a component.

        Args:
            component_name: Name of the component (e.g., 'browser', 'ollama', 'mcp')
            status: Status string ('healthy', 'degraded', 'down')
            latency_ms: Optional latency in milliseconds
            error_message: Optional error message if degraded/down
            **metadata: Additional metadata about the component
        """
        with self._component_lock:
            self.component_health[component_name] = ComponentHealth(
                name=component_name,
                status=status,
                latency_ms=latency_ms,
                error_message=error_message,
                metadata=metadata
            )

    def check_browser_health(self, browser) -> str:
        """
        Check browser health status.

        Args:
            browser: Browser instance to check

        Returns:
            Status string ('healthy', 'degraded', 'down')
        """
        try:
            if browser is None:
                return 'down'

            # Try to get browser context
            if hasattr(browser, 'contexts'):
                contexts = browser.contexts
                status = 'healthy' if contexts else 'degraded'
                self.update_component_health(
                    'browser',
                    status,
                    metadata={'context_count': len(contexts) if contexts else 0}
                )
                return status
            else:
                return 'healthy'

        except Exception as e:
            self.update_component_health('browser', 'down', error_message=str(e))
            return 'down'

    async def check_ollama_health(self, ollama_client, model: str) -> str:
        """
        Check Ollama LLM health and latency.

        Args:
            ollama_client: Ollama client instance
            model: Model name to test

        Returns:
            Status string ('healthy', 'degraded', 'down')
        """
        if ollama_client is None:
            self.update_component_health('ollama', 'down', error_message='Client not initialized')
            return 'down'

        try:
            start_time = time.time()

            # Simple test request
            response = await asyncio.to_thread(
                ollama_client.generate,
                model=model,
                prompt="test",
                options={'num_predict': 1}
            )

            latency_ms = (time.time() - start_time) * 1000

            # Determine status based on latency
            if latency_ms < 1000:
                status = 'healthy'
            elif latency_ms < 5000:
                status = 'degraded'
            else:
                status = 'degraded'

            self.update_component_health(
                'ollama',
                status,
                latency_ms=latency_ms,
                metadata={'model': model}
            )
            return status

        except Exception as e:
            self.update_component_health('ollama', 'down', error_message=str(e))
            return 'down'

    def check_mcp_health(self, mcp_client) -> str:
        """
        Check MCP server health.

        Args:
            mcp_client: MCP client instance

        Returns:
            Status string ('healthy', 'degraded', 'down')
        """
        if mcp_client is None:
            self.update_component_health('mcp', 'down', error_message='Client not initialized')
            return 'down'

        try:
            # Check if client has required attributes
            has_tools = hasattr(mcp_client, 'list_tools')
            has_call = hasattr(mcp_client, 'call_tool')

            if has_tools and has_call:
                status = 'healthy'
            else:
                status = 'degraded'

            self.update_component_health(
                'mcp',
                status,
                metadata={'has_tools': has_tools, 'has_call': has_call}
            )
            return status

        except Exception as e:
            self.update_component_health('mcp', 'down', error_message=str(e))
            return 'down'

    # =========================================================================
    # Health Summary & Alerts
    # =========================================================================

    def get_health_summary(self) -> Dict[str, Any]:
        """
        Get current health summary with all metrics.

        Returns:
            Dictionary with complete health status
        """
        snapshot = self._create_snapshot()

        return {
            'timestamp': snapshot.timestamp.isoformat(),
            'overall_status': snapshot.overall_status,
            'alerts': snapshot.alerts,
            'domain_metrics': {
                domain: {
                    'request_count': m.request_count,
                    'success_rate': round(m.success_rate, 2),
                    'failure_rate': round(m.failure_rate, 2),
                    'avg_response_time': round(m.avg_response_time, 2),
                    'captcha_rate': round(m.captcha_rate, 2),
                    'login_success_rate': round(m.login_success_rate, 2),
                    'last_accessed': m.last_accessed.isoformat() if m.last_accessed else None
                }
                for domain, m in snapshot.domain_metrics.items()
            },
            'resources': {
                'memory_mb': round(snapshot.resource_metrics.memory_mb, 2),
                'memory_percent': round(snapshot.resource_metrics.memory_percent, 2),
                'cpu_percent': round(snapshot.resource_metrics.cpu_percent, 2),
                'disk_usage_gb': round(snapshot.resource_metrics.disk_usage_gb, 2),
                'disk_percent': round(snapshot.resource_metrics.disk_percent, 2),
                'open_files': snapshot.resource_metrics.open_file_handles,
                'threads': snapshot.resource_metrics.thread_count
            },
            'components': {
                name: {
                    'status': comp.status,
                    'latency_ms': round(comp.latency_ms, 2) if comp.latency_ms else None,
                    'error': comp.error_message,
                    'metadata': comp.metadata
                }
                for name, comp in snapshot.component_health.items()
            }
        }

    def _create_snapshot(self) -> HealthSnapshot:
        """Create a complete health snapshot."""
        snapshot = HealthSnapshot()

        # Copy current domain metrics
        with self._domain_lock:
            snapshot.domain_metrics = dict(self.domain_metrics)

        # Get latest resource metrics
        with self._resource_lock:
            if self.resource_history:
                snapshot.resource_metrics = self.resource_history[-1]

        # Copy component health
        with self._component_lock:
            snapshot.component_health = dict(self.component_health)

        # Determine overall status and collect alerts
        snapshot.overall_status, snapshot.alerts = self._determine_status_and_alerts(snapshot)

        # Store snapshot
        with self._snapshot_lock:
            self.snapshot_history.append(snapshot)

        return snapshot

    def _determine_status_and_alerts(self, snapshot: HealthSnapshot) -> tuple[str, List[str]]:
        """
        Determine overall status and generate alerts.

        Returns:
            Tuple of (status, alerts_list)
        """
        alerts = []
        status = 'healthy'

        # Check resource usage
        mem_pct = snapshot.resource_metrics.memory_percent
        cpu_pct = snapshot.resource_metrics.cpu_percent

        if mem_pct >= self.MEMORY_CRITICAL_THRESHOLD:
            alerts.append(f"CRITICAL: Memory usage at {mem_pct:.1f}%")
            status = 'critical'
        elif mem_pct >= self.MEMORY_WARNING_THRESHOLD:
            alerts.append(f"WARNING: Memory usage at {mem_pct:.1f}%")
            if status == 'healthy':
                status = 'warning'

        if cpu_pct >= self.CPU_WARNING_THRESHOLD:
            alerts.append(f"WARNING: CPU usage at {cpu_pct:.1f}%")
            if status == 'healthy':
                status = 'warning'

        # Check domain failure rates
        for domain, metrics in snapshot.domain_metrics.items():
            if metrics.failure_rate >= self.FAILURE_RATE_ALERT_THRESHOLD:
                alerts.append(f"ALERT: {domain} failure rate at {metrics.failure_rate:.1f}%")
                if status == 'healthy':
                    status = 'warning'

            if metrics.avg_response_time >= self.SLOW_RESPONSE_THRESHOLD:
                alerts.append(f"SLOW: {domain} avg response time {metrics.avg_response_time:.1f}s")
                if status == 'healthy':
                    status = 'warning'

        # Check component health
        for name, comp in snapshot.component_health.items():
            if comp.status == 'down':
                alerts.append(f"DOWN: {name} is down - {comp.error_message}")
                status = 'critical'
            elif comp.status == 'degraded':
                alerts.append(f"DEGRADED: {name} is degraded")
                if status == 'healthy':
                    status = 'warning'

        return status, alerts

    # =========================================================================
    # Trend Analysis & Anomaly Detection
    # =========================================================================

    def detect_anomalies(self) -> List[str]:
        """
        Detect anomalies in resource usage based on baseline.

        Returns:
            List of anomaly descriptions
        """
        if not self._baseline_calculated:
            return []

        anomalies = []

        with self._resource_lock:
            if not self.resource_history:
                return anomalies

            current = self.resource_history[-1]

            # CPU spike detection (>50% above baseline)
            if current.cpu_percent > self._baseline_cpu * 1.5:
                anomalies.append(
                    f"CPU spike: {current.cpu_percent:.1f}% (baseline: {self._baseline_cpu:.1f}%)"
                )

            # Memory spike detection (>30% above baseline)
            if current.memory_percent > self._baseline_memory * 1.3:
                anomalies.append(
                    f"Memory spike: {current.memory_percent:.1f}% (baseline: {self._baseline_memory:.1f}%)"
                )

        return anomalies

    def get_trend(self, metric: str, window_minutes: int = 10) -> str:
        """
        Determine trend for a metric over time window.

        Args:
            metric: Metric name ('cpu', 'memory', etc.)
            window_minutes: Time window in minutes

        Returns:
            Trend string ('improving', 'stable', 'degrading', 'unknown')
        """
        with self._resource_lock:
            if len(self.resource_history) < 2:
                return 'unknown'

            # Get samples within window
            cutoff_time = datetime.now() - timedelta(minutes=window_minutes)
            samples = [
                m for m in self.resource_history
                if m.timestamp >= cutoff_time
            ]

            if len(samples) < 2:
                return 'unknown'

            # Extract values
            if metric == 'cpu':
                values = [s.cpu_percent for s in samples]
            elif metric == 'memory':
                values = [s.memory_percent for s in samples]
            else:
                return 'unknown'

            # Simple linear trend
            first_half = sum(values[:len(values)//2]) / (len(values)//2)
            second_half = sum(values[len(values)//2:]) / (len(values) - len(values)//2)

            diff_percent = ((second_half - first_half) / first_half * 100) if first_half > 0 else 0

            if diff_percent < -5:
                return 'improving'
            elif diff_percent > 5:
                return 'degrading'
            else:
                return 'stable'

    # =========================================================================
    # Export Formats
    # =========================================================================

    def get_metrics_json(self) -> str:
        """
        Export full metrics as JSON.

        Returns:
            JSON string with all metrics
        """
        summary = self.get_health_summary()
        summary['anomalies'] = self.detect_anomalies()
        summary['trends'] = {
            'cpu': self.get_trend('cpu'),
            'memory': self.get_trend('memory')
        }
        return json.dumps(summary, indent=2)

    def get_prometheus_format(self) -> str:
        """
        Export metrics in Prometheus format.

        Returns:
            Prometheus-formatted metrics string
        """
        lines = []
        timestamp = int(datetime.now().timestamp() * 1000)

        # Domain metrics
        with self._domain_lock:
            for domain, metrics in self.domain_metrics.items():
                domain_label = domain.replace('.', '_').replace('-', '_')
                lines.append(
                    f'eversale_domain_requests_total{{domain="{domain}"}} {metrics.request_count} {timestamp}'
                )
                lines.append(
                    f'eversale_domain_success_rate{{domain="{domain}"}} {metrics.success_rate:.2f} {timestamp}'
                )
                lines.append(
                    f'eversale_domain_avg_response_time{{domain="{domain}"}} {metrics.avg_response_time:.2f} {timestamp}'
                )
                lines.append(
                    f'eversale_domain_captcha_rate{{domain="{domain}"}} {metrics.captcha_rate:.2f} {timestamp}'
                )

        # Resource metrics
        with self._resource_lock:
            if self.resource_history:
                current = self.resource_history[-1]
                lines.append(f'eversale_memory_mb {current.memory_mb:.2f} {timestamp}')
                lines.append(f'eversale_memory_percent {current.memory_percent:.2f} {timestamp}')
                lines.append(f'eversale_cpu_percent {current.cpu_percent:.2f} {timestamp}')
                lines.append(f'eversale_disk_usage_gb {current.disk_usage_gb:.2f} {timestamp}')
                lines.append(f'eversale_open_files {current.open_file_handles} {timestamp}')
                lines.append(f'eversale_threads {current.thread_count} {timestamp}')

        # Component health (0=down, 1=degraded, 2=healthy)
        with self._component_lock:
            status_map = {'down': 0, 'degraded': 1, 'healthy': 2}
            for name, comp in self.component_health.items():
                status_value = status_map.get(comp.status, 0)
                lines.append(f'eversale_component_health{{component="{name}"}} {status_value} {timestamp}')
                if comp.latency_ms is not None:
                    lines.append(f'eversale_component_latency_ms{{component="{name}"}} {comp.latency_ms:.2f} {timestamp}')

        return '\n'.join(lines)

    def save_metrics(self, output_path: Path):
        """
        Save metrics to file.

        Args:
            output_path: Path to save metrics JSON
        """
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(self.get_metrics_json())
            logger.info(f"Metrics saved to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")

    # =========================================================================
    # Pretty CLI Display
    # =========================================================================

    def print_dashboard(self):
        """Print pretty CLI dashboard using Rich."""
        snapshot = self._create_snapshot()

        # Create layout
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )

        # Split body into sections
        layout["body"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )

        layout["left"].split_column(
            Layout(name="resources"),
            Layout(name="components")
        )

        layout["right"].split_column(
            Layout(name="domains"),
            Layout(name="alerts")
        )

        # Header
        status_color = {
            'healthy': 'green',
            'warning': 'yellow',
            'critical': 'red'
        }.get(snapshot.overall_status, 'white')

        header_text = Text()
        header_text.append("Eversale Health Dashboard", style="bold")
        header_text.append(f" | Status: ", style="white")
        header_text.append(snapshot.overall_status.upper(), style=f"bold {status_color}")
        header_text.append(f" | {snapshot.timestamp.strftime('%Y-%m-%d %H:%M:%S')}", style="dim")

        layout["header"].update(Panel(header_text, border_style=status_color))

        # Resources panel
        resource_table = Table(title="System Resources", box=box.ROUNDED, show_header=False)
        resource_table.add_column("Metric", style="cyan")
        resource_table.add_column("Value", style="white")

        res = snapshot.resource_metrics
        memory_color = self._get_threshold_color(res.memory_percent, 80, 95)
        cpu_color = self._get_threshold_color(res.cpu_percent, 80, 90)

        resource_table.add_row("Memory", f"{res.memory_mb:.1f} MB ({res.memory_percent:.1f}%)", style=memory_color)
        resource_table.add_row("CPU", f"{res.cpu_percent:.1f}%", style=cpu_color)
        resource_table.add_row("Disk", f"{res.disk_usage_gb:.2f} GB ({res.disk_percent:.1f}%)")
        resource_table.add_row("Open Files", str(res.open_file_handles))
        resource_table.add_row("Threads", str(res.thread_count))

        layout["resources"].update(Panel(resource_table, title="Resources", border_style="blue"))

        # Components panel
        component_table = Table(title="Components", box=box.ROUNDED)
        component_table.add_column("Component", style="cyan")
        component_table.add_column("Status", style="white")
        component_table.add_column("Latency", style="white")

        for name, comp in snapshot.component_health.items():
            status_color = {
                'healthy': 'green',
                'degraded': 'yellow',
                'down': 'red'
            }.get(comp.status, 'white')

            latency_str = f"{comp.latency_ms:.0f}ms" if comp.latency_ms else "N/A"

            component_table.add_row(
                name.capitalize(),
                Text(comp.status.upper(), style=status_color),
                latency_str
            )

        layout["components"].update(Panel(component_table, title="Components", border_style="blue"))

        # Domains panel
        domain_table = Table(title="Domain Metrics", box=box.ROUNDED)
        domain_table.add_column("Domain", style="cyan")
        domain_table.add_column("Requests", justify="right")
        domain_table.add_column("Success", justify="right")
        domain_table.add_column("Avg Time", justify="right")

        for domain, metrics in sorted(
            snapshot.domain_metrics.items(),
            key=lambda x: x[1].request_count,
            reverse=True
        )[:10]:  # Top 10 domains
            success_color = self._get_threshold_color(metrics.failure_rate, 20, 50, inverse=True)

            domain_table.add_row(
                domain[:30],  # Truncate long domains
                str(metrics.request_count),
                Text(f"{metrics.success_rate:.1f}%", style=success_color),
                f"{metrics.avg_response_time:.1f}s"
            )

        layout["domains"].update(Panel(domain_table, title="Top Domains", border_style="blue"))

        # Alerts panel
        alerts_text = Text()
        if snapshot.alerts:
            for alert in snapshot.alerts:
                if "CRITICAL" in alert:
                    alerts_text.append(f"• {alert}\n", style="bold red")
                elif "WARNING" in alert or "ALERT" in alert:
                    alerts_text.append(f"• {alert}\n", style="bold yellow")
                else:
                    alerts_text.append(f"• {alert}\n", style="white")
        else:
            alerts_text.append("No alerts", style="green")

        # Add anomalies
        anomalies = self.detect_anomalies()
        if anomalies:
            alerts_text.append("\nAnomalies:\n", style="bold yellow")
            for anomaly in anomalies:
                alerts_text.append(f"• {anomaly}\n", style="yellow")

        layout["alerts"].update(Panel(alerts_text, title="Alerts & Anomalies", border_style="yellow"))

        # Footer with trends
        trends = {
            'cpu': self.get_trend('cpu'),
            'memory': self.get_trend('memory')
        }

        footer_text = Text()
        footer_text.append("Trends: ", style="bold")
        footer_text.append(f"CPU: {trends['cpu']} ", style=self._get_trend_color(trends['cpu']))
        footer_text.append(f"| Memory: {trends['memory']}", style=self._get_trend_color(trends['memory']))

        layout["footer"].update(Panel(footer_text, border_style="dim"))

        # Print layout
        self.console.print(layout)

    def _get_threshold_color(self, value: float, warning: float, critical: float, inverse: bool = False) -> str:
        """Get color based on threshold (red/yellow/green)."""
        if inverse:
            # For success rates (higher is better)
            if value >= critical:
                return "red"
            elif value >= warning:
                return "yellow"
            else:
                return "green"
        else:
            # For usage metrics (lower is better)
            if value >= critical:
                return "red"
            elif value >= warning:
                return "yellow"
            else:
                return "green"

    def _get_trend_color(self, trend: str) -> str:
        """Get color for trend."""
        return {
            'improving': 'green',
            'stable': 'white',
            'degrading': 'red',
            'unknown': 'dim'
        }.get(trend, 'white')

    def print_simple_summary(self):
        """Print a simple text summary without fancy formatting."""
        summary = self.get_health_summary()

        print(f"\n{'='*60}")
        print(f"EVERSALE HEALTH SUMMARY - {summary['timestamp']}")
        print(f"{'='*60}")
        print(f"Overall Status: {summary['overall_status'].upper()}")

        if summary['alerts']:
            print(f"\nALERTS ({len(summary['alerts'])}):")
            for alert in summary['alerts']:
                print(f"  • {alert}")

        print(f"\nRESOURCES:")
        res = summary['resources']
        print(f"  Memory: {res['memory_mb']:.1f} MB ({res['memory_percent']:.1f}%)")
        print(f"  CPU: {res['cpu_percent']:.1f}%")
        print(f"  Disk: {res['disk_usage_gb']:.2f} GB ({res['disk_percent']:.1f}%)")

        print(f"\nCOMPONENTS:")
        for name, comp in summary['components'].items():
            latency = f" ({comp['latency_ms']:.0f}ms)" if comp['latency_ms'] else ""
            print(f"  {name.capitalize()}: {comp['status'].upper()}{latency}")

        if summary['domain_metrics']:
            print(f"\nDOMAINS (Top 5):")
            sorted_domains = sorted(
                summary['domain_metrics'].items(),
                key=lambda x: x[1]['request_count'],
                reverse=True
            )[:5]
            for domain, metrics in sorted_domains:
                print(f"  {domain}:")
                print(f"    Requests: {metrics['request_count']}, "
                      f"Success: {metrics['success_rate']:.1f}%, "
                      f"Avg: {metrics['avg_response_time']:.1f}s")

        print(f"{'='*60}\n")


# =============================================================================
# Global Instance
# =============================================================================

_global_dashboard: Optional[HealthDashboard] = None


def get_dashboard() -> HealthDashboard:
    """Get or create global health dashboard instance."""
    global _global_dashboard
    if _global_dashboard is None:
        _global_dashboard = HealthDashboard()
        _global_dashboard.start_monitoring()
    return _global_dashboard


def stop_global_dashboard():
    """Stop global dashboard monitoring."""
    global _global_dashboard
    if _global_dashboard:
        _global_dashboard.stop_monitoring()
        _global_dashboard = None


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Example: Create dashboard and record some metrics
    dashboard = HealthDashboard()
    dashboard.start_monitoring()

    # Simulate some requests
    dashboard.record_request("https://example.com/page1", success=True, response_time=1.5)
    dashboard.record_request("https://example.com/page2", success=True, response_time=2.1)
    dashboard.record_request("https://test.com/api", success=False, response_time=5.0, error_type="timeout")
    dashboard.record_request("https://example.com/page3", success=True, response_time=1.8, is_captcha=True)

    # Simulate login attempts
    dashboard.record_login_attempt("https://example.com/login", success=True)
    dashboard.record_login_attempt("https://test.com/signin", success=False)

    # Update component health
    dashboard.update_component_health("browser", "healthy", metadata={'contexts': 1})
    dashboard.update_component_health("mcp", "healthy")
    dashboard.update_component_health("ollama", "degraded", latency_ms=2500)

    # Wait a bit for resource metrics to collect
    time.sleep(6)

    # Print dashboard
    print("\n" + "="*70)
    print("RICH DASHBOARD OUTPUT:")
    print("="*70)
    dashboard.print_dashboard()

    print("\n" + "="*70)
    print("SIMPLE SUMMARY OUTPUT:")
    print("="*70)
    dashboard.print_simple_summary()

    print("\n" + "="*70)
    print("JSON METRICS:")
    print("="*70)
    print(dashboard.get_metrics_json())

    print("\n" + "="*70)
    print("PROMETHEUS FORMAT:")
    print("="*70)
    print(dashboard.get_prometheus_format())

    # Save metrics
    dashboard.save_metrics(Path("outputs/health_metrics.json"))

    # Stop monitoring
    dashboard.stop_monitoring()
