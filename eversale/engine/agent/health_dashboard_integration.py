"""
Health Dashboard Integration Examples

This file demonstrates how to integrate the HealthDashboard into:
1. ReAct loop for automatic metrics collection
2. Tool executor for domain-specific tracking
3. Browser manager for component health monitoring
4. Standalone monitoring scripts

Usage:
    # In brain_enhanced_v2.py or react_loop.py:
    from agent.health_dashboard import get_dashboard

    dashboard = get_dashboard()  # Auto-starts monitoring

    # Record tool execution
    dashboard.record_request(url, success=True, response_time=2.5)

    # Update component health
    dashboard.update_component_health('browser', 'healthy')

    # Get health summary
    summary = dashboard.get_health_summary()

    # Print dashboard
    dashboard.print_dashboard()
"""

import asyncio
import time
from typing import Optional
from loguru import logger


# =============================================================================
# Integration with ToolExecutor
# =============================================================================

class HealthAwareToolExecutor:
    """
    Example wrapper for ToolExecutor that records metrics to HealthDashboard.

    This shows how to track tool execution success/failure per domain.
    """

    def __init__(self, tool_executor, health_dashboard):
        """
        Wrap a ToolExecutor with health tracking.

        Args:
            tool_executor: Original ToolExecutor instance
            health_dashboard: HealthDashboard instance
        """
        self.tool_executor = tool_executor
        self.dashboard = health_dashboard

    async def execute_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        Execute a tool and record metrics.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        start_time = time.time()
        success = False
        error_type = None
        url = arguments.get('url', 'unknown')

        try:
            # Execute the tool
            result = await self.tool_executor.execute_tool(tool_name, arguments)
            success = result.get('success', True)

            # Check for CAPTCHA
            is_captcha = 'captcha' in str(result).lower()

            # Record the request
            response_time = time.time() - start_time
            self.dashboard.record_request(
                url=url,
                success=success,
                response_time=response_time,
                is_captcha=is_captcha
            )

            return result

        except TimeoutError:
            error_type = 'timeout'
            raise
        except ConnectionError:
            error_type = 'connection_error'
            raise
        except Exception as e:
            error_type = type(e).__name__
            raise
        finally:
            # Always record the request, even on failure
            if not success or error_type:
                response_time = time.time() - start_time
                self.dashboard.record_request(
                    url=url,
                    success=False,
                    response_time=response_time,
                    error_type=error_type
                )


# =============================================================================
# Integration with BrowserManager
# =============================================================================

class HealthAwareBrowserManager:
    """
    Example wrapper for BrowserManager that monitors browser health.

    This shows how to track browser component status.
    """

    def __init__(self, browser_manager, health_dashboard):
        """
        Wrap a BrowserManager with health tracking.

        Args:
            browser_manager: Original BrowserManager instance
            health_dashboard: HealthDashboard instance
        """
        self.browser_manager = browser_manager
        self.dashboard = health_dashboard

    async def ensure_browser_healthy(self) -> bool:
        """
        Check browser health and update dashboard.

        Returns:
            True if browser is healthy
        """
        try:
            browser = await self.browser_manager.get_browser()
            status = self.dashboard.check_browser_health(browser)
            return status == 'healthy'
        except Exception as e:
            self.dashboard.update_component_health(
                'browser',
                'down',
                error_message=str(e)
            )
            return False

    async def check_all_components(self, ollama_client, mcp_client, model: str):
        """
        Check health of all components.

        Args:
            ollama_client: Ollama client instance
            mcp_client: MCP client instance
            model: LLM model name
        """
        # Check browser
        await self.ensure_browser_healthy()

        # Check Ollama
        await self.dashboard.check_ollama_health(ollama_client, model)

        # Check MCP
        self.dashboard.check_mcp_health(mcp_client)


# =============================================================================
# Integration with ReAct Loop
# =============================================================================

async def react_loop_with_health_monitoring(
    brain,
    task_description: str,
    max_iterations: int = 10
):
    """
    Example ReAct loop with integrated health monitoring.

    This shows how to:
    1. Track metrics during execution
    2. Check component health before critical operations
    3. Generate health reports after task completion

    Args:
        brain: Brain instance with all components
        task_description: Task to execute
        max_iterations: Maximum iterations
    """
    from agent.health_dashboard import get_dashboard

    # Get global dashboard
    dashboard = get_dashboard()

    logger.info("Starting task with health monitoring")

    # Check component health before starting
    browser_status = dashboard.check_browser_health(brain.browser)
    mcp_status = dashboard.check_mcp_health(brain.mcp)

    if browser_status == 'down':
        logger.error("Browser is down, cannot proceed")
        return

    if mcp_status == 'down':
        logger.warning("MCP server is down, some tools may not work")

    # Execute task with monitoring
    for iteration in range(max_iterations):
        logger.info(f"Iteration {iteration + 1}/{max_iterations}")

        # Check resource health every 5 iterations
        if iteration % 5 == 0:
            summary = dashboard.get_health_summary()

            # Alert on high memory usage
            if summary['resources']['memory_percent'] > 80:
                logger.warning(f"High memory usage: {summary['resources']['memory_percent']:.1f}%")

            # Alert on component degradation
            for comp_name, comp in summary['components'].items():
                if comp['status'] != 'healthy':
                    logger.warning(f"Component {comp_name} is {comp['status']}")

        # Your normal ReAct loop logic here
        # ...

        # Simulate tool execution with tracking
        # dashboard.record_request(url, success, response_time)

        await asyncio.sleep(0.1)  # Simulated work

    # Print final health report
    logger.info("Task completed, generating health report")
    dashboard.print_simple_summary()

    # Save metrics to file
    from pathlib import Path
    dashboard.save_metrics(Path(f"outputs/health_{int(time.time())}.json"))


# =============================================================================
# Standalone Monitoring Script
# =============================================================================

async def standalone_health_monitor(check_interval: int = 30):
    """
    Standalone health monitoring script.

    Runs continuously and prints health dashboard every check_interval seconds.
    Useful for monitoring long-running agent processes.

    Args:
        check_interval: How often to print dashboard (seconds)
    """
    from agent.health_dashboard import get_dashboard

    dashboard = get_dashboard()

    logger.info(f"Starting standalone health monitor (interval: {check_interval}s)")
    logger.info("Press Ctrl+C to stop")

    try:
        while True:
            # Clear screen and print dashboard
            print("\033[2J\033[H")  # Clear screen
            dashboard.print_dashboard()

            # Check for anomalies
            anomalies = dashboard.detect_anomalies()
            if anomalies:
                logger.warning(f"Detected {len(anomalies)} anomalies:")
                for anomaly in anomalies:
                    logger.warning(f"  - {anomaly}")

            # Wait for next check
            await asyncio.sleep(check_interval)

    except KeyboardInterrupt:
        logger.info("Stopping health monitor")
        dashboard.stop_monitoring()


# =============================================================================
# Integration Helper Functions
# =============================================================================

def add_health_tracking_to_brain(brain):
    """
    Add health dashboard to an existing brain instance.

    This monkey-patches the brain to record metrics automatically.

    Args:
        brain: Brain instance to augment

    Returns:
        Brain instance with health tracking
    """
    from agent.health_dashboard import get_dashboard

    dashboard = get_dashboard()

    # Store original methods
    original_execute = brain.tool_executor.execute_tool if hasattr(brain.tool_executor, 'execute_tool') else None

    # Create wrapper for tool execution
    async def execute_with_tracking(tool_name: str, arguments: dict):
        start_time = time.time()
        url = arguments.get('url', 'unknown')

        try:
            result = await original_execute(tool_name, arguments)
            success = result.get('success', True)
            response_time = time.time() - start_time

            dashboard.record_request(url, success, response_time)
            return result

        except Exception as e:
            response_time = time.time() - start_time
            dashboard.record_request(
                url,
                success=False,
                response_time=response_time,
                error_type=type(e).__name__
            )
            raise

    # Monkey-patch if original exists
    if original_execute:
        brain.tool_executor.execute_tool = execute_with_tracking

    # Add dashboard reference to brain
    brain.health_dashboard = dashboard

    logger.info("Health tracking added to brain")
    return brain


def create_health_report(brain, output_path: Optional[str] = None) -> dict:
    """
    Create a comprehensive health report for a brain instance.

    Args:
        brain: Brain instance
        output_path: Optional path to save report

    Returns:
        Health report dict
    """
    from agent.health_dashboard import get_dashboard
    from pathlib import Path

    dashboard = get_dashboard()

    # Update component health
    dashboard.check_browser_health(brain.browser)
    dashboard.check_mcp_health(brain.mcp)

    # Get summary
    summary = dashboard.get_health_summary()

    # Add brain-specific stats
    summary['brain_stats'] = {
        'iterations': brain.stats.get('iterations', 0),
        'tool_calls': brain.stats.get('tool_calls', 0),
        'vision_calls': brain.stats.get('vision_calls', 0),
        'retries': brain.stats.get('retries', 0),
        'cache_hits': brain.stats.get('cache_hits', 0),
        'cache_misses': brain.stats.get('cache_misses', 0)
    }

    # Save if path provided
    if output_path:
        dashboard.save_metrics(Path(output_path))

    return summary


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Example 1: Standalone health monitor
    print("Example 1: Running standalone health monitor for 10 seconds...")

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    # Import directly to avoid agent.__init__ issues
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "health_dashboard",
        Path(__file__).parent / "health_dashboard.py"
    )
    health_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(health_module)
    get_dashboard = health_module.get_dashboard

    dashboard = get_dashboard()

    # Simulate some activity
    for i in range(5):
        dashboard.record_request(
            f"https://example.com/page{i}",
            success=i % 2 == 0,
            response_time=1.5 + i * 0.3
        )
        time.sleep(0.5)

    dashboard.update_component_health('browser', 'healthy')
    dashboard.update_component_health('ollama', 'healthy', latency_ms=850)
    dashboard.update_component_health('mcp', 'healthy')

    # Print dashboard
    dashboard.print_dashboard()

    # Print metrics
    print("\nJSON Metrics Preview:")
    print(dashboard.get_metrics_json()[:500] + "...")

    # Clean up
    dashboard.stop_monitoring()

    print("\nIntegration examples completed!")
