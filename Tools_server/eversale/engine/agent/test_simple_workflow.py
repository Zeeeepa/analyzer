"""
Tests for Simple Workflow Executor

Run with: pytest test_simple_workflow.py -v
"""

import pytest
from simple_workflow_executor import (
    SimpleWorkflow,
    WorkflowStep,
    SimpleWorkflowExecutor,
    WorkflowResult,
    StepResult,
    GOOGLE_SEARCH,
    SIMPLE_NAVIGATE,
    get_workflow,
    list_workflows,
)


class MockToolResult:
    """Mock result from MCP tools."""
    def __init__(self, success=True, message="OK", data=None):
        self.success = success
        self.message = message
        self.data = data
        self.screenshot_b64 = "mock_screenshot_data"


class MockMCPTools:
    """Mock MCP tools for testing without browser."""

    def __init__(self):
        self.calls = []

    async def navigate(self, url):
        self.calls.append(("navigate", url))
        return MockToolResult(success=True, message=f"Navigated to {url}")

    async def click(self, selector):
        self.calls.append(("click", selector))
        return MockToolResult(success=True, message=f"Clicked {selector}")

    async def fill(self, selector, text):
        self.calls.append(("fill", selector, text))
        return MockToolResult(success=True, message=f"Filled {selector} with {text}")

    async def press_key(self, key):
        self.calls.append(("press_key", key))
        return MockToolResult(success=True, message=f"Pressed {key}")

    async def screenshot(self):
        self.calls.append(("screenshot",))
        return MockToolResult(success=True, message="Screenshot taken")

    async def extract_content(self):
        self.calls.append(("extract_content",))
        return MockToolResult(
            success=True,
            message="Extracted content",
            data="Sample extracted content"
        )

    async def scroll(self, direction):
        self.calls.append(("scroll", direction))
        return MockToolResult(success=True, message=f"Scrolled {direction}")


@pytest.mark.asyncio
async def test_simple_workflow_success():
    """Test successful workflow execution."""
    tools = MockMCPTools()
    executor = SimpleWorkflowExecutor(tools)

    workflow = SimpleWorkflow(
        name="test_workflow",
        steps=[
            WorkflowStep("navigate", "https://example.com"),
            WorkflowStep("wait", value="0.1"),
            WorkflowStep("extract"),
        ]
    )

    result = await executor.execute(workflow)

    assert result.success is True
    assert result.completed_steps == 3
    assert result.total_steps == 3
    assert result.failed_step is None
    assert len(result.step_results) == 3


@pytest.mark.asyncio
async def test_workflow_with_variables():
    """Test variable substitution."""
    tools = MockMCPTools()
    executor = SimpleWorkflowExecutor(tools)

    workflow = SimpleWorkflow(
        name="test_vars",
        steps=[
            WorkflowStep("navigate", "{url}"),
            WorkflowStep("type", "{selector}", "{text}"),
        ]
    )

    variables = {
        "url": "https://example.com",
        "selector": "input[name='q']",
        "text": "search query",
    }

    result = await executor.execute(workflow, variables)

    assert result.success is True
    assert ("navigate", "https://example.com") in tools.calls
    assert ("fill", "input[name='q']", "search query") in tools.calls


@pytest.mark.asyncio
async def test_workflow_required_step_fails():
    """Test workflow stops when required step fails."""

    class FailingTools(MockMCPTools):
        async def click(self, selector):
            self.calls.append(("click", selector))
            return MockToolResult(success=False, message="Element not found")

    tools = FailingTools()
    executor = SimpleWorkflowExecutor(tools)

    workflow = SimpleWorkflow(
        name="failing_workflow",
        steps=[
            WorkflowStep("navigate", "https://example.com"),
            WorkflowStep("click", "button#missing", required=True),  # Will fail
            WorkflowStep("extract"),  # Should not run
        ]
    )

    result = await executor.execute(workflow)

    assert result.success is False
    assert result.failed_step == 2
    assert result.completed_steps == 1  # Only first step completed
    assert len(result.step_results) == 2  # Two steps executed (second failed)


@pytest.mark.asyncio
async def test_workflow_optional_step_fails():
    """Test workflow continues when optional step fails."""

    class PartiallyFailingTools(MockMCPTools):
        async def click(self, selector):
            self.calls.append(("click", selector))
            return MockToolResult(success=False, message="Element not found")

    tools = PartiallyFailingTools()
    executor = SimpleWorkflowExecutor(tools)

    workflow = SimpleWorkflow(
        name="optional_workflow",
        steps=[
            WorkflowStep("navigate", "https://example.com"),
            WorkflowStep("click", "button#popup-close", required=False),  # Optional, will fail
            WorkflowStep("extract"),  # Should still run
        ]
    )

    result = await executor.execute(workflow)

    assert result.success is True
    assert result.completed_steps == 3  # All steps completed
    assert len(result.step_results) == 3
    assert result.step_results[1].success is False  # Middle step failed
    assert result.step_results[2].success is True  # Last step succeeded


@pytest.mark.asyncio
async def test_prebuilt_google_search():
    """Test pre-built Google search workflow."""
    tools = MockMCPTools()
    executor = SimpleWorkflowExecutor(tools)

    result = await executor.execute(GOOGLE_SEARCH, {"query": "AI agents"})

    assert result.success is True
    assert ("navigate", "https://www.google.com") in tools.calls
    assert ("fill", "textarea[name='q']", "AI agents") in tools.calls


@pytest.mark.asyncio
async def test_prebuilt_simple_navigate():
    """Test pre-built simple navigate workflow."""
    tools = MockMCPTools()
    executor = SimpleWorkflowExecutor(tools)

    result = await executor.execute(SIMPLE_NAVIGATE, {"url": "https://test.com"})

    assert result.success is True
    assert ("navigate", "https://test.com") in tools.calls
    assert ("extract_content",) in tools.calls


def test_workflow_registry():
    """Test workflow registry functions."""
    # List all workflows
    workflows = list_workflows()
    assert len(workflows) > 0
    assert "google_search" in workflows
    assert "simple_navigate" in workflows

    # Get workflow by name
    workflow = get_workflow("google_search")
    assert workflow is not None
    assert workflow.name == "google_search"
    assert len(workflow.steps) > 0

    # Get non-existent workflow
    missing = get_workflow("does_not_exist")
    assert missing is None


@pytest.mark.asyncio
async def test_step_timing():
    """Test that step timing is recorded."""
    tools = MockMCPTools()
    executor = SimpleWorkflowExecutor(tools)

    workflow = SimpleWorkflow(
        name="timing_test",
        steps=[
            WorkflowStep("navigate", "https://example.com"),
            WorkflowStep("extract"),
        ]
    )

    result = await executor.execute(workflow)

    assert result.success is True
    assert result.total_time_ms > 0
    for step_result in result.step_results:
        assert step_result.time_ms >= 0


@pytest.mark.asyncio
async def test_extracted_data():
    """Test that extracted data is captured."""
    tools = MockMCPTools()
    executor = SimpleWorkflowExecutor(tools)

    workflow = SimpleWorkflow(
        name="extract_test",
        steps=[
            WorkflowStep("navigate", "https://example.com"),
            WorkflowStep("extract"),
        ]
    )

    result = await executor.execute(workflow)

    assert result.success is True
    assert result.extracted_data == "Sample extracted content"
    assert result.step_results[-1].extracted_data == "Sample extracted content"


@pytest.mark.asyncio
async def test_unknown_action():
    """Test handling of unknown action type."""
    tools = MockMCPTools()
    executor = SimpleWorkflowExecutor(tools)

    workflow = SimpleWorkflow(
        name="unknown_action_test",
        steps=[
            WorkflowStep("unknown_action", "target"),
        ]
    )

    result = await executor.execute(workflow)

    assert result.success is False
    assert "Unknown action" in result.error


@pytest.mark.asyncio
async def test_workflow_repr():
    """Test workflow and step string representations."""
    workflow = SimpleWorkflow(
        name="test",
        steps=[WorkflowStep("navigate", "https://example.com")]
    )

    assert "test" in str(workflow)
    assert "navigate" in str(workflow.steps[0])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
