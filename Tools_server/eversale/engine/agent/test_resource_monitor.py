#!/usr/bin/env python3
"""Tests for resource monitor."""
import pytest
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from .resource_monitor import ResourceMonitor, ResourceError


class TestResourceMonitor:
    """Tests for ResourceMonitor class."""

    def test_initialization(self):
        """Test resource monitor initialization."""
        monitor = ResourceMonitor(
            cpu_threshold=80.0,
            mem_threshold=85.0,
            gpu_threshold=90.0
        )

        assert monitor.cpu_threshold == 80.0
        assert monitor.mem_threshold == 85.0
        assert monitor.gpu_threshold == 90.0
        assert monitor.last_report == ""

    def test_initialization_defaults(self):
        """Test resource monitor with default thresholds."""
        monitor = ResourceMonitor()

        assert monitor.cpu_threshold == 85.0
        assert monitor.mem_threshold == 90.0
        assert monitor.gpu_threshold == 85.0

    def test_has_gpu_with_nvidia_smi(self):
        """Test GPU detection when nvidia-smi is available."""
        monitor = ResourceMonitor()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)

            result = monitor._has_gpu()

            assert result is True
            mock_run.assert_called_once()

    def test_has_gpu_without_nvidia_smi(self):
        """Test GPU detection when nvidia-smi is not available."""
        monitor = ResourceMonitor()

        with patch('subprocess.run', side_effect=Exception("Command not found")):
            result = monitor._has_gpu()

            assert result is False

    def test_check_returns_empty_when_ok(self):
        """Test check returns empty list when resources are ok."""
        monitor = ResourceMonitor(
            cpu_threshold=90.0,
            mem_threshold=90.0,
            gpu_threshold=90.0
        )

        with patch.object(monitor, '_cpu_usage', return_value=50.0):
            with patch.object(monitor, '_mem_usage', return_value=60.0):
                with patch.object(monitor, '_gpu_usage', return_value=40.0):
                    issues = monitor.check()

                    assert issues == []
                    assert monitor.last_report == ""

    def test_check_returns_cpu_issue(self):
        """Test check returns CPU issue when threshold exceeded."""
        monitor = ResourceMonitor(cpu_threshold=70.0)

        with patch.object(monitor, '_cpu_usage', return_value=85.0):
            with patch.object(monitor, '_mem_usage', return_value=50.0):
                with patch.object(monitor, '_gpu_usage', return_value=None):
                    issues = monitor.check()

                    assert len(issues) == 1
                    assert "CPU" in issues[0]
                    assert "85%" in issues[0]

    def test_check_returns_memory_issue(self):
        """Test check returns memory issue when threshold exceeded."""
        monitor = ResourceMonitor(mem_threshold=60.0)

        with patch.object(monitor, '_cpu_usage', return_value=50.0):
            with patch.object(monitor, '_mem_usage', return_value=75.0):
                with patch.object(monitor, '_gpu_usage', return_value=None):
                    issues = monitor.check()

                    assert len(issues) == 1
                    assert "Memory" in issues[0]
                    assert "75%" in issues[0]

    def test_check_returns_gpu_issue(self):
        """Test check returns GPU issue when threshold exceeded."""
        monitor = ResourceMonitor(gpu_threshold=80.0)

        with patch.object(monitor, '_cpu_usage', return_value=50.0):
            with patch.object(monitor, '_mem_usage', return_value=50.0):
                with patch.object(monitor, '_gpu_usage', return_value=95.0):
                    issues = monitor.check()

                    assert len(issues) == 1
                    assert "GPU" in issues[0]
                    assert "95%" in issues[0]

    def test_check_returns_multiple_issues(self):
        """Test check returns multiple issues."""
        monitor = ResourceMonitor(
            cpu_threshold=70.0,
            mem_threshold=70.0,
            gpu_threshold=70.0
        )

        with patch.object(monitor, '_cpu_usage', return_value=85.0):
            with patch.object(monitor, '_mem_usage', return_value=90.0):
                with patch.object(monitor, '_gpu_usage', return_value=95.0):
                    issues = monitor.check()

                    assert len(issues) == 3
                    assert any("CPU" in issue for issue in issues)
                    assert any("Memory" in issue for issue in issues)
                    assert any("GPU" in issue for issue in issues)

    def test_check_updates_last_report(self):
        """Test that check updates last_report."""
        monitor = ResourceMonitor(cpu_threshold=50.0)

        with patch.object(monitor, '_cpu_usage', return_value=80.0):
            with patch.object(monitor, '_mem_usage', return_value=50.0):
                with patch.object(monitor, '_gpu_usage', return_value=None):
                    monitor.check()

                    assert monitor.last_report != ""
                    assert "CPU" in monitor.last_report

    def test_summary_with_issues(self):
        """Test summary when there are issues."""
        monitor = ResourceMonitor(cpu_threshold=50.0)
        monitor.last_report = "CPU at 80%"

        summary = monitor.summary()

        assert "Resource monitor:" in summary
        assert "CPU at 80%" in summary

    def test_summary_without_issues(self):
        """Test summary when there are no issues."""
        monitor = ResourceMonitor()
        monitor.last_report = ""

        summary = monitor.summary()

        assert summary == "Resource monitor: OK"

    def test_cpu_usage_without_psutil(self):
        """Test CPU usage when psutil is not available."""
        monitor = ResourceMonitor()

        with patch('agent.resource_monitor.PSUTIL_AVAILABLE', False):
            cpu = monitor._cpu_usage()

            assert cpu is None

    def test_cpu_usage_with_psutil(self):
        """Test CPU usage with psutil."""
        monitor = ResourceMonitor()

        with patch('agent.resource_monitor.PSUTIL_AVAILABLE', True):
            with patch('agent.resource_monitor.psutil') as mock_psutil:
                mock_psutil.cpu_percent.return_value = 45.5

                cpu = monitor._cpu_usage()

                assert cpu == 45.5
                mock_psutil.cpu_percent.assert_called_once_with(interval=1.0)

    def test_mem_usage_without_psutil(self):
        """Test memory usage when psutil is not available."""
        monitor = ResourceMonitor()

        with patch('agent.resource_monitor.PSUTIL_AVAILABLE', False):
            mem = monitor._mem_usage()

            assert mem is None

    def test_mem_usage_with_psutil(self):
        """Test memory usage with psutil."""
        monitor = ResourceMonitor()

        with patch('agent.resource_monitor.PSUTIL_AVAILABLE', True):
            with patch('agent.resource_monitor.psutil') as mock_psutil:
                mock_vm = Mock()
                mock_vm.percent = 67.8
                mock_psutil.virtual_memory.return_value = mock_vm

                mem = monitor._mem_usage()

                assert mem == 67.8

    def test_gpu_usage_no_gpu(self):
        """Test GPU usage when no GPU available."""
        monitor = ResourceMonitor()

        with patch.object(monitor, '_has_gpu', return_value=False):
            gpu = monitor._gpu_usage()

            assert gpu is None

    def test_gpu_usage_with_gpu(self):
        """Test GPU usage when GPU is available."""
        monitor = ResourceMonitor()

        with patch.object(monitor, '_has_gpu', return_value=True):
            with patch('subprocess.run') as mock_run:
                mock_result = Mock()
                mock_result.stdout = "75\n"
                mock_run.return_value = mock_result

                gpu = monitor._gpu_usage()

                assert gpu == 75.0

    def test_gpu_usage_multiple_gpus(self):
        """Test GPU usage returns max when multiple GPUs."""
        monitor = ResourceMonitor()

        with patch.object(monitor, '_has_gpu', return_value=True):
            with patch('subprocess.run') as mock_run:
                mock_result = Mock()
                mock_result.stdout = "45\n75\n60\n"
                mock_run.return_value = mock_result

                gpu = monitor._gpu_usage()

                assert gpu == 75.0  # Should return max

    def test_gpu_usage_error(self):
        """Test GPU usage handles errors gracefully."""
        monitor = ResourceMonitor()

        with patch.object(monitor, '_has_gpu', return_value=True):
            with patch('subprocess.run', side_effect=Exception("GPU query failed")):
                gpu = monitor._gpu_usage()

                assert gpu is None

    def test_can_run_heavy_true(self):
        """Test can_run_heavy returns True when resources OK."""
        monitor = ResourceMonitor()

        with patch.object(monitor, 'check', return_value=[]):
            result = monitor.can_run_heavy()

            assert result is True

    def test_can_run_heavy_false(self):
        """Test can_run_heavy returns False when resources high."""
        monitor = ResourceMonitor()

        with patch.object(monitor, 'check', return_value=["CPU at 90%"]):
            result = monitor.can_run_heavy()

            assert result is False

    def test_enforce_memory_limit(self):
        """Test enforcing memory limit."""
        monitor = ResourceMonitor()

        with patch('resource.setrlimit') as mock_setrlimit:
            monitor.enforce_memory_limit(max_mb=2048)

            expected_bytes = 2048 * 1024 * 1024
            mock_setrlimit.assert_called_once()
            args = mock_setrlimit.call_args[0]
            assert args[1] == (expected_bytes, expected_bytes)

    def test_enforce_memory_limit_error(self):
        """Test enforce memory limit handles errors."""
        monitor = ResourceMonitor()

        with patch('resource.setrlimit', side_effect=Exception("Permission denied")):
            # Should not raise, just log warning
            monitor.enforce_memory_limit(max_mb=2048)

    def test_throttle_if_needed_no_throttle(self):
        """Test throttle when resources are OK."""
        monitor = ResourceMonitor()

        with patch.object(monitor, '_cpu_usage', return_value=50.0):
            with patch.object(monitor, '_mem_usage', return_value=50.0):
                with patch.object(monitor, '_gpu_usage', return_value=50.0):
                    result = monitor.throttle_if_needed()

                    assert result is False

    def test_throttle_if_needed_cpu_high(self):
        """Test throttle when CPU is high."""
        monitor = ResourceMonitor()

        with patch.object(monitor, '_cpu_usage', return_value=90.0):
            with patch.object(monitor, '_mem_usage', return_value=50.0):
                with patch.object(monitor, '_gpu_usage', return_value=50.0):
                    with patch('time.sleep') as mock_sleep:
                        result = monitor.throttle_if_needed()

                        assert result is True
                        mock_sleep.assert_called_once_with(2)

    def test_throttle_if_needed_memory_high(self):
        """Test throttle when memory is high."""
        monitor = ResourceMonitor()

        with patch.object(monitor, '_cpu_usage', return_value=50.0):
            with patch.object(monitor, '_mem_usage', return_value=90.0):
                with patch.object(monitor, '_gpu_usage', return_value=50.0):
                    with patch('time.sleep') as mock_sleep:
                        result = monitor.throttle_if_needed()

                        assert result is True
                        mock_sleep.assert_called_once()

    def test_throttle_if_needed_gpu_high(self):
        """Test throttle when GPU is high."""
        monitor = ResourceMonitor()

        with patch.object(monitor, '_cpu_usage', return_value=50.0):
            with patch.object(monitor, '_mem_usage', return_value=50.0):
                with patch.object(monitor, '_gpu_usage', return_value=90.0):
                    with patch('time.sleep') as mock_sleep:
                        result = monitor.throttle_if_needed()

                        assert result is True

    def test_kill_if_critical_ok(self):
        """Test kill_if_critical when resources are OK."""
        monitor = ResourceMonitor()

        with patch.object(monitor, '_cpu_usage', return_value=80.0):
            with patch.object(monitor, '_mem_usage', return_value=80.0):
                with patch.object(monitor, '_gpu_usage', return_value=80.0):
                    # Should not raise
                    monitor.kill_if_critical()

    def test_kill_if_critical_cpu(self):
        """Test kill_if_critical raises on critical CPU."""
        monitor = ResourceMonitor()

        with patch.object(monitor, '_cpu_usage', return_value=96.0):
            with patch.object(monitor, '_mem_usage', return_value=50.0):
                with patch.object(monitor, '_gpu_usage', return_value=50.0):
                    with pytest.raises(ResourceError) as exc_info:
                        monitor.kill_if_critical()

                    assert "CPU" in str(exc_info.value)
                    assert "96%" in str(exc_info.value)

    def test_kill_if_critical_memory(self):
        """Test kill_if_critical raises on critical memory."""
        monitor = ResourceMonitor()

        with patch.object(monitor, '_cpu_usage', return_value=50.0):
            with patch.object(monitor, '_mem_usage', return_value=97.0):
                with patch.object(monitor, '_gpu_usage', return_value=50.0):
                    with pytest.raises(ResourceError) as exc_info:
                        monitor.kill_if_critical()

                    assert "MEM" in str(exc_info.value)

    def test_kill_if_critical_gpu(self):
        """Test kill_if_critical raises on critical GPU."""
        monitor = ResourceMonitor()

        with patch.object(monitor, '_cpu_usage', return_value=50.0):
            with patch.object(monitor, '_mem_usage', return_value=50.0):
                with patch.object(monitor, '_gpu_usage', return_value=98.0):
                    with pytest.raises(ResourceError) as exc_info:
                        monitor.kill_if_critical()

                    assert "GPU" in str(exc_info.value)

    def test_check_and_enforce_ok(self):
        """Test check_and_enforce when resources are OK."""
        monitor = ResourceMonitor()

        with patch.object(monitor, '_cpu_usage', return_value=50.0):
            with patch.object(monitor, '_mem_usage', return_value=50.0):
                with patch.object(monitor, '_gpu_usage', return_value=50.0):
                    issues = monitor.check_and_enforce()

                    assert issues == []

    def test_check_and_enforce_warning(self):
        """Test check_and_enforce with warning level."""
        monitor = ResourceMonitor()

        with patch.object(monitor, '_cpu_usage', return_value=75.0):
            with patch.object(monitor, '_mem_usage', return_value=50.0):
                with patch.object(monitor, '_gpu_usage', return_value=50.0):
                    issues = monitor.check_and_enforce()

                    assert len(issues) == 1
                    assert "Warning" in issues[0]
                    assert "CPU=75%" in issues[0]

    def test_check_and_enforce_throttle(self):
        """Test check_and_enforce throttles when needed."""
        monitor = ResourceMonitor()

        with patch.object(monitor, '_cpu_usage', return_value=90.0):
            with patch.object(monitor, '_mem_usage', return_value=50.0):
                with patch.object(monitor, '_gpu_usage', return_value=50.0):
                    with patch('time.sleep') as mock_sleep:
                        issues = monitor.check_and_enforce()

                        assert len(issues) == 1
                        assert "Throttling" in issues[0]
                        mock_sleep.assert_called_once()

    def test_check_and_enforce_critical(self):
        """Test check_and_enforce raises on critical."""
        monitor = ResourceMonitor()

        with patch.object(monitor, '_cpu_usage', return_value=96.0):
            with patch.object(monitor, '_mem_usage', return_value=50.0):
                with patch.object(monitor, '_gpu_usage', return_value=50.0):
                    with pytest.raises(ResourceError):
                        monitor.check_and_enforce()

    def test_check_and_enforce_multiple_levels(self):
        """Test check_and_enforce with multiple threshold levels."""
        monitor = ResourceMonitor()

        with patch.object(monitor, '_cpu_usage', return_value=75.0):  # Warning
            with patch.object(monitor, '_mem_usage', return_value=88.0):  # Throttle
                with patch.object(monitor, '_gpu_usage', return_value=50.0):
                    with patch('time.sleep'):
                        issues = monitor.check_and_enforce()

                        # Should have warning and throttle messages
                        assert len(issues) == 2
                        assert any("Warning" in issue for issue in issues)
                        assert any("Throttling" in issue for issue in issues)

    def test_record_capabilities(self, tmp_path):
        """Test recording resource capabilities."""
        capability_path = tmp_path / "resource_capability.json"

        monitor = ResourceMonitor()
        monitor.capability_path = capability_path

        monitor._record_capabilities()

        assert capability_path.exists()
        import json
        data = json.loads(capability_path.read_text())

        assert "cpu_limit" in data
        assert "mem_limit" in data
        assert "gpu_limit" in data
        assert "has_psutil" in data
        assert "gpu_query" in data


class TestResourceError:
    """Tests for ResourceError exception."""

    def test_resource_error_creation(self):
        """Test creating ResourceError."""
        error = ResourceError("Test error message")

        assert isinstance(error, Exception)
        assert str(error) == "Test error message"

    def test_resource_error_raised(self):
        """Test ResourceError can be raised and caught."""
        with pytest.raises(ResourceError) as exc_info:
            raise ResourceError("Critical resource usage")

        assert "Critical resource usage" in str(exc_info.value)
