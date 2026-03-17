"""
Resource Monitor - Tracks CPU/GPU/memory usage and enforces limits.
"""

import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

# Platform-specific imports
_IS_WINDOWS = sys.platform == 'win32'
if not _IS_WINDOWS:
    import resource
else:
    resource = None  # Not available on Windows

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

logger = logging.getLogger(__name__)


class ResourceError(Exception):
    """Raised when resources exceed critical threshold."""
    pass


class ResourceMonitor:
    # Threshold levels
    WARNING_THRESHOLD = 70
    THROTTLE_THRESHOLD = 85
    CRITICAL_THRESHOLD = 95

    # GPU is expected to be at 100% during LLM inference - don't treat as critical
    GPU_CRITICAL_THRESHOLD = 100  # Effectively disabled - GPU at 100% is normal for LLM

    def __init__(self, cpu_threshold: float = 85.0, mem_threshold: float = 90.0, gpu_threshold: float = 85.0):
        self.cpu_threshold = cpu_threshold
        self.mem_threshold = mem_threshold
        self.gpu_threshold = gpu_threshold
        self.last_report = ""
        self.capability_path = Path("memory/resource_capability.json")
        self._record_capabilities()

    def _record_capabilities(self):
        props = {
            "cpu_limit": self.cpu_threshold,
            "mem_limit": self.mem_threshold,
            "gpu_limit": self.gpu_threshold,
            "has_psutil": PSUTIL_AVAILABLE,
            "gpu_query": self._has_gpu()
        }
        try:
            self.capability_path.parent.mkdir(parents=True, exist_ok=True)
            self.capability_path.write_text(json.dumps(props))
        except Exception:
            pass

    def _has_gpu(self) -> bool:
        try:
            subprocess.run(["nvidia-smi"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return True
        except Exception:
            return False

    def check(self) -> List[str]:
        issues = []
        cpu = self._cpu_usage()
        if cpu and cpu >= self.cpu_threshold:
            issues.append(f"CPU at {cpu:.0f}% (>= {self.cpu_threshold}%)")
        mem = self._mem_usage()
        if mem and mem >= self.mem_threshold:
            issues.append(f"Memory at {mem:.0f}% (>= {self.mem_threshold}%)")
        gpu = self._gpu_usage()
        if gpu and gpu >= self.gpu_threshold:
            issues.append(f"GPU at {gpu:.0f}% (>= {self.gpu_threshold}%)")
        self.last_report = "; ".join(issues)
        return issues

    def summary(self) -> str:
        if self.last_report:
            return f"Resource monitor: {self.last_report}"
        return "Resource monitor: OK"

    def _cpu_usage(self) -> Optional[float]:
        if not PSUTIL_AVAILABLE:
            return None
        return psutil.cpu_percent(interval=1.0)

    def _mem_usage(self) -> Optional[float]:
        if not PSUTIL_AVAILABLE:
            return None
        return psutil.virtual_memory().percent

    def _gpu_usage(self) -> Optional[float]:
        if not self._has_gpu():
            return None
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                check=True
            )
            values = [float(x.strip()) for x in result.stdout.splitlines() if x.strip()]
            return max(values) if values else None
        except Exception:
            return None

    def can_run_heavy(self) -> bool:
        issues = self.check()
        return not issues

    def enforce_memory_limit(self, max_mb: int = 4096):
        """Set hard memory limit using setrlimit.

        Args:
            max_mb: Maximum memory in megabytes (default 4GB)
        """
        max_bytes = max_mb * 1024 * 1024
        if _IS_WINDOWS:
            logger.debug("Memory limits not supported on Windows")
            return
        try:
            resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))
            logger.info(f"Memory limit set to {max_mb}MB")
        except Exception as e:
            logger.warning(f"Could not set memory limit: {e}")

    def throttle_if_needed(self) -> bool:
        """Sleep if resources above throttle threshold.

        Returns:
            True if throttled, False otherwise
        """
        cpu = self._cpu_usage()
        mem = self._mem_usage()
        gpu = self._gpu_usage()

        should_throttle = False
        reasons = []

        if cpu and cpu >= self.THROTTLE_THRESHOLD:
            should_throttle = True
            reasons.append(f"CPU={cpu:.0f}%")

        if mem and mem >= self.THROTTLE_THRESHOLD:
            should_throttle = True
            reasons.append(f"MEM={mem:.0f}%")

        if gpu and gpu >= self.THROTTLE_THRESHOLD:
            should_throttle = True
            reasons.append(f"GPU={gpu:.0f}%")

        if should_throttle:
            logger.warning(f"Throttling due to high resource usage: {', '.join(reasons)}")
            time.sleep(2)  # Back off
            return True

        return False

    def kill_if_critical(self):
        """Terminate process if resources critically high.

        Raises:
            ResourceError: When resources exceed critical threshold
        """
        cpu = self._cpu_usage()
        mem = self._mem_usage()
        gpu = self._gpu_usage()

        critical_issues = []

        if cpu and cpu >= self.CRITICAL_THRESHOLD:
            critical_issues.append(f"CPU={cpu:.0f}%")

        if mem and mem >= self.CRITICAL_THRESHOLD:
            critical_issues.append(f"MEM={mem:.0f}%")

        if gpu and gpu >= self.GPU_CRITICAL_THRESHOLD:
            critical_issues.append(f"GPU={gpu:.0f}%")

        if critical_issues:
            error_msg = f"Critical resource usage: {', '.join(critical_issues)}"
            logger.error(error_msg)
            raise ResourceError(error_msg)

    def check_and_enforce(self) -> List[str]:
        """Check resources and enforce limits.

        Returns:
            List of issues/warnings

        Raises:
            ResourceError: When resources exceed critical threshold
        """
        cpu = self._cpu_usage()
        mem = self._mem_usage()
        gpu = self._gpu_usage()

        issues = []

        # Check for critical levels first
        critical_issues = []
        if cpu and cpu >= self.CRITICAL_THRESHOLD:
            critical_issues.append(f"CPU={cpu:.0f}%")
        if mem and mem >= self.CRITICAL_THRESHOLD:
            critical_issues.append(f"MEM={mem:.0f}%")
        if gpu and gpu >= self.GPU_CRITICAL_THRESHOLD:
            critical_issues.append(f"GPU={gpu:.0f}%")

        if critical_issues:
            error_msg = f"Critical resource usage: {', '.join(critical_issues)}"
            logger.error(error_msg)
            raise ResourceError(error_msg)

        # Check for throttle levels
        throttle_issues = []
        if cpu and cpu >= self.THROTTLE_THRESHOLD:
            throttle_issues.append(f"CPU={cpu:.0f}%")
        if mem and mem >= self.THROTTLE_THRESHOLD:
            throttle_issues.append(f"MEM={mem:.0f}%")
        if gpu and gpu >= self.THROTTLE_THRESHOLD:
            throttle_issues.append(f"GPU={gpu:.0f}%")

        if throttle_issues:
            issue_msg = f"Throttling: {', '.join(throttle_issues)}"
            issues.append(issue_msg)
            logger.warning(issue_msg)
            time.sleep(2)  # Back off

        # Check for warning levels
        warning_issues = []
        if cpu and cpu >= self.WARNING_THRESHOLD and cpu < self.THROTTLE_THRESHOLD:
            warning_issues.append(f"CPU={cpu:.0f}%")
        if mem and mem >= self.WARNING_THRESHOLD and mem < self.THROTTLE_THRESHOLD:
            warning_issues.append(f"MEM={mem:.0f}%")
        if gpu and gpu >= self.WARNING_THRESHOLD and gpu < self.THROTTLE_THRESHOLD:
            warning_issues.append(f"GPU={gpu:.0f}%")

        if warning_issues:
            warning_msg = f"Warning: {', '.join(warning_issues)}"
            issues.append(warning_msg)
            logger.warning(warning_msg)

        return issues
