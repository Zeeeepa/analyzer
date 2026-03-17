"""
Real-World Integration Example

Shows how to integrate browser backend into existing agent architecture.
Demonstrates both simple and advanced usage patterns.
"""

import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from loguru import logger

from browser_backend import (
    BrowserBackend, create_backend, BackendFactory,
    ElementRef, SnapshotResult, InteractionResult
)


# ============================================================================
# Example 1: Simple Agent with Backend
# ============================================================================

class SimpleAgentWithBackend:
    """
    Simple agent that uses browser backend for automation.

    Can use either Playwright or CDP transparently.
    """

    def __init__(self, backend_type: str = 'auto', headless: bool = False):
        self.backend_type = backend_type
        self.headless = headless
        self.backend: Optional[BrowserBackend] = None

    async def start(self) -> bool:
        """Initialize browser backend."""
        self.backend = await create_backend(
            self.backend_type,
            headless=self.headless
        )

        if not self.backend:
            logger.error("Failed to create browser backend")
            return False

        logger.info(f"Started {self.backend.__class__.__name__}")
        return True

    async def stop(self):
        """Cleanup backend."""
        if self.backend:
            await self.backend.disconnect()
            self.backend = None

    async def execute_task(self, task: str) -> Dict[str, Any]:
        """
        Execute a task using AI to decide actions.

        This is a simplified example - real implementation would use
        LLM to decide actions based on task and page state.
        """
        if not self.backend:
            return {"error": "Backend not initialized"}

        # Example: "Find and click the login button on example.com"
        steps = self._parse_task(task)

        for step in steps:
            if step['action'] == 'navigate':
                result = await self.backend.navigate(step['url'])
                if not result.success:
                    return {"error": f"Navigation failed: {result.error}"}

            elif step['action'] == 'click':
                # Get page state
                snapshot = await self.backend.snapshot()

                # Find element (simplified - real version uses AI)
                element = self._find_element(snapshot, step['target'])
                if not element:
                    return {"error": f"Element not found: {step['target']}"}

                # Click it
                click_result = await self.backend.click(element.mmid)
                if not click_result.success:
                    return {"error": f"Click failed: {click_result.error}"}

        return {"success": True, "message": "Task completed"}

    def _parse_task(self, task: str) -> List[Dict[str, Any]]:
        """Parse natural language task into steps (simplified)."""
        # Real implementation would use LLM for this
        if "example.com" in task.lower():
            return [
                {"action": "navigate", "url": "https://example.com"},
                {"action": "click", "target": "login"}
            ]
        return []

    def _find_element(self, snapshot: SnapshotResult, target: str) -> Optional[ElementRef]:
        """Find element in snapshot (simplified - real version uses AI)."""
        # Real implementation would use LLM to analyze snapshot.elements
        target_lower = target.lower()

        # Find by text match
        for el in snapshot.elements:
            if target_lower in el.text.lower():
                return el

        return None


# ============================================================================
# Example 2: Advanced Agent with Session Reuse
# ============================================================================

class SessionAwareAgent:
    """
    Agent that prefers CDP for session reuse but falls back to Playwright.
    """

    def __init__(self):
        self.backend: Optional[BrowserBackend] = None
        self.using_session = False

    async def start(self) -> bool:
        """Try CDP first, fallback to Playwright."""
        # Try CDP (reuses existing Chrome with logins)
        self.backend = await create_backend('cdp')

        if self.backend:
            logger.info("Connected to existing Chrome session via CDP")
            self.using_session = True
            return True

        # Fallback to Playwright
        logger.info("CDP unavailable, using Playwright (fresh browser)")
        self.backend = await create_backend('playwright')

        if not self.backend:
            logger.error("Failed to create any backend")
            return False

        self.using_session = False
        return True

    async def navigate_with_login_check(self, url: str, requires_login: bool = False):
        """Navigate and handle login if needed."""
        if not self.backend:
            raise RuntimeError("Backend not initialized")

        # Navigate
        nav_result = await self.backend.navigate(url)
        if not nav_result.success:
            raise RuntimeError(f"Navigation failed: {nav_result.error}")

        if requires_login and not self.using_session:
            logger.warning("Site requires login but using fresh browser")
            # Could implement login flow here
            await self._perform_login(url)

    async def _perform_login(self, site_url: str):
        """Perform login flow (implementation depends on site)."""
        snapshot = await self.backend.snapshot()

        # Find login form
        username_fields = [el for el in snapshot.elements if el.role == 'textbox' and 'user' in el.text.lower()]
        password_fields = [el for el in snapshot.elements if el.role == 'textbox' and 'password' in el.text.lower()]

        if username_fields and password_fields:
            # Type credentials (from config/env)
            await self.backend.type(username_fields[0].mmid, "user@example.com")
            await self.backend.type(password_fields[0].mmid, "password123")

            # Click submit
            submit_buttons = [el for el in snapshot.elements if el.role == 'button' and 'submit' in el.text.lower()]
            if submit_buttons:
                await self.backend.click(submit_buttons[0].mmid)


# ============================================================================
# Example 3: Multi-Backend Agent Pool
# ============================================================================

class AgentPool:
    """
    Pool of agents with different backends for parallel execution.
    """

    def __init__(self, size: int = 3, backend_type: str = 'playwright'):
        self.size = size
        self.backend_type = backend_type
        self.agents: List[SimpleAgentWithBackend] = []

    async def initialize(self):
        """Create pool of agents."""
        for i in range(self.size):
            agent = SimpleAgentWithBackend(backend_type=self.backend_type)
            if await agent.start():
                self.agents.append(agent)
                logger.info(f"Agent {i+1}/{self.size} initialized")
            else:
                logger.error(f"Agent {i+1} failed to start")

        logger.info(f"Pool ready with {len(self.agents)} agents")

    async def execute_parallel(self, tasks: List[str]) -> List[Dict[str, Any]]:
        """Execute multiple tasks in parallel."""
        results = await asyncio.gather(*[
            agent.execute_task(task)
            for agent, task in zip(self.agents, tasks)
        ])
        return results

    async def shutdown(self):
        """Cleanup all agents."""
        await asyncio.gather(*[agent.stop() for agent in self.agents])


# ============================================================================
# Example 4: Adaptive Backend Selection
# ============================================================================

class AdaptiveAgent:
    """
    Agent that chooses backend based on task requirements.
    """

    @dataclass
    class TaskProfile:
        needs_login: bool = False
        needs_stealth: bool = False
        high_performance: bool = False

    async def execute(self, task: str, profile: Optional[TaskProfile] = None):
        """Execute task with optimal backend."""
        profile = profile or self.TaskProfile()

        # Choose backend based on requirements
        backend_type = self._choose_backend(profile)
        logger.info(f"Selected {backend_type} backend for task")

        async with await create_backend(backend_type) as backend:
            if not backend:
                logger.error("Failed to create backend")
                return {"error": "Backend creation failed"}

            # Execute task
            # ... (task execution logic)
            pass

    def _choose_backend(self, profile: TaskProfile) -> str:
        """Choose optimal backend based on task profile."""
        if profile.needs_login:
            # CDP preserves login sessions
            return 'cdp'

        if profile.needs_stealth:
            # Playwright has better stealth features
            return 'playwright'

        if profile.high_performance:
            # CDP is lighter weight
            return 'cdp'

        # Default: auto-detect
        return 'auto'


# ============================================================================
# Example 5: Real Automation Workflow
# ============================================================================

async def example_workflow():
    """
    Real-world example: Extract data from authenticated site.
    """
    # Create agent with session reuse
    agent = SessionAwareAgent()
    await agent.start()

    try:
        # Navigate to authenticated site
        await agent.navigate_with_login_check(
            'https://example.com/dashboard',
            requires_login=True
        )

        # Get page state
        snapshot = await agent.backend.snapshot()
        logger.info(f"Page loaded: {snapshot.title}")
        logger.info(f"Found {len(snapshot.elements)} interactive elements")

        # Find data table
        tables = [el for el in snapshot.elements if el.tag == 'table']
        if tables:
            logger.info(f"Found {len(tables)} tables")

        # Click "Export" button
        export_buttons = [
            el for el in snapshot.elements
            if el.role == 'button' and 'export' in el.text.lower()
        ]

        if export_buttons:
            logger.info(f"Clicking export button: {export_buttons[0].text}")
            result = await agent.backend.click(export_buttons[0].mmid)

            if result.success:
                logger.info("Export started successfully")
            else:
                logger.error(f"Export failed: {result.error}")

    finally:
        await agent.backend.disconnect()


# ============================================================================
# Example 6: Testing with Mock Backend
# ============================================================================

from browser_backend import NavigationResult, ObserveResult

class MockBackend(BrowserBackend):
    """Mock backend for testing."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.navigation_history = []
        self.click_history = []

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def navigate(self, url: str, wait_until: str = 'load') -> NavigationResult:
        self.navigation_history.append(url)
        return NavigationResult(success=True, url=url, title='Mock Page')

    async def snapshot(self) -> SnapshotResult:
        return SnapshotResult(
            url='https://mock.com',
            title='Mock Page',
            elements=[
                ElementRef(
                    mmid='mm0',
                    ref='button:Submit',
                    role='button',
                    text='Submit',
                    tag='button',
                    selector='button.submit'
                )
            ]
        )

    async def click(self, ref: str, **kwargs) -> InteractionResult:
        self.click_history.append(ref)
        return InteractionResult(success=True, method='mock')

    async def type(self, ref: str, text: str, clear: bool = True, **kwargs) -> InteractionResult:
        return InteractionResult(success=True)

    async def scroll(self, direction: str = 'down', amount: int = 500) -> InteractionResult:
        return InteractionResult(success=True)

    async def run_code(self, js: str) -> Any:
        return None

    async def observe(self, network: bool = False, console: bool = False) -> ObserveResult:
        return ObserveResult()

    async def screenshot(self, full_page: bool = False) -> bytes:
        return b'mock_screenshot'


async def test_agent_with_mock():
    """Test agent with mock backend (no real browser needed)."""
    agent = SimpleAgentWithBackend()
    agent.backend = MockBackend()
    await agent.backend.connect()

    # Execute task
    result = await agent.execute_task("Navigate to example.com and click login")

    # Verify
    assert result.get('success') or result.get('error')
    assert len(agent.backend.navigation_history) > 0

    logger.info("Test passed!")


# ============================================================================
# Main Examples
# ============================================================================

async def main():
    """Run all examples."""

    print("\n=== Example 1: Simple Agent ===")
    agent = SimpleAgentWithBackend(backend_type='auto')
    if await agent.start():
        result = await agent.execute_task("Navigate to example.com")
        print(f"Result: {result}")
        await agent.stop()

    print("\n=== Example 2: Session Aware Agent ===")
    session_agent = SessionAwareAgent()
    if await session_agent.start():
        print(f"Using existing session: {session_agent.using_session}")
        await session_agent.backend.disconnect()

    print("\n=== Example 3: Agent Pool ===")
    pool = AgentPool(size=2, backend_type='playwright')
    await pool.initialize()
    results = await pool.execute_parallel([
        "Task 1: Navigate to example.com",
        "Task 2: Navigate to github.com"
    ])
    print(f"Parallel results: {results}")
    await pool.shutdown()

    print("\n=== Example 4: Adaptive Agent ===")
    adaptive = AdaptiveAgent()
    profile = AdaptiveAgent.TaskProfile(needs_login=True)
    # await adaptive.execute("Login to dashboard", profile)

    print("\n=== Example 5: Real Workflow ===")
    # await example_workflow()

    print("\n=== Example 6: Testing with Mock ===")
    await test_agent_with_mock()


if __name__ == '__main__':
    asyncio.run(main())
