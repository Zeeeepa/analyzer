#!/usr/bin/env python3
"""Tests for code generator."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from .code_generator import (
    PlaywrightCodeGenerator,
    CodeGenerationConfig,
    CodeFormat,
    GeneratedCode,
    export_workflow,
    export_skill
)


class TestCodeFormat:
    """Tests for CodeFormat enum."""

    def test_code_formats_exist(self):
        """Test that all code formats are defined."""
        assert CodeFormat.PYTHON_ASYNC.value == "python_async"
        assert CodeFormat.PYTHON_SYNC.value == "python_sync"
        assert CodeFormat.PYTEST.value == "pytest"
        assert CodeFormat.TYPESCRIPT.value == "typescript"
        assert CodeFormat.JAVASCRIPT.value == "javascript"


class TestCodeGenerationConfig:
    """Tests for CodeGenerationConfig dataclass."""

    def test_default_config(self):
        """Test default configuration."""
        config = CodeGenerationConfig()

        assert config.format == CodeFormat.PYTHON_ASYNC
        assert config.add_comments is True
        assert config.add_error_handling is True
        assert config.add_retries is True
        assert config.add_logging is True
        assert config.max_retries == 3
        assert config.timeout == 30000
        assert config.headless is False

    def test_custom_config(self):
        """Test custom configuration."""
        config = CodeGenerationConfig(
            format=CodeFormat.PYTEST,
            add_comments=False,
            max_retries=5,
            timeout=60000,
            headless=True
        )

        assert config.format == CodeFormat.PYTEST
        assert config.add_comments is False
        assert config.max_retries == 5
        assert config.timeout == 60000
        assert config.headless is True


class TestGeneratedCode:
    """Tests for GeneratedCode dataclass."""

    def test_generated_code_creation(self):
        """Test creating GeneratedCode."""
        code = GeneratedCode(
            code="import asyncio\nprint('hello')",
            format=CodeFormat.PYTHON_ASYNC,
            parameters={"url": {"value": "https://example.com", "type": "str"}},
            dependencies=["playwright"],
            description="Test workflow"
        )

        assert "import asyncio" in code.code
        assert code.format == CodeFormat.PYTHON_ASYNC
        assert "url" in code.parameters
        assert "playwright" in code.dependencies
        assert code.description == "Test workflow"
        assert code.generated_at is not None


class TestPlaywrightCodeGenerator:
    """Tests for PlaywrightCodeGenerator class."""

    def test_initialization(self):
        """Test generator initialization."""
        generator = PlaywrightCodeGenerator()

        assert generator.config is not None
        assert isinstance(generator.config, CodeGenerationConfig)

    def test_initialization_with_config(self):
        """Test generator initialization with custom config."""
        config = CodeGenerationConfig(max_retries=5)
        generator = PlaywrightCodeGenerator(config=config)

        assert generator.config.max_retries == 5

    def test_generate_param_name(self):
        """Test parameter name generation."""
        generator = PlaywrightCodeGenerator()

        # Test URL
        name = generator._generate_param_name("https://example.com", "url")
        assert name == "url_https_example_com"

        # Test query
        name = generator._generate_param_name("search query", "query")
        assert name == "query_search_query"

        # Test cleaning
        name = generator._generate_param_name("test!!!value###", "param")
        assert name == "param_test_value"

        # Test truncation
        long_value = "x" * 100
        name = generator._generate_param_name(long_value, "test")
        assert len(name) <= 35  # prefix + underscore + 30 chars

    def test_extract_parameters(self):
        """Test parameter extraction from actions."""
        generator = PlaywrightCodeGenerator()

        actions = [
            {
                "tool": "playwright_navigate",
                "arguments": {"url": "https://example.com"}
            },
            {
                "tool": "playwright_fill",
                "arguments": {"selector": "input", "value": "test query"}
            }
        ]

        params = generator._extract_parameters(actions)

        assert len(params) > 0
        # Should extract URL
        assert any("url" in key for key in params.keys())
        # Should extract query value
        assert any("query" in key.lower() for key in params.keys())

    def test_extract_parameters_skips_complex_selectors(self):
        """Test that complex selectors are not parameterized."""
        generator = PlaywrightCodeGenerator()

        actions = [
            {
                "tool": "playwright_click",
                "arguments": {"selector": "div.container > ul > li:nth-child(2) > button.submit"}
            }
        ]

        params = generator._extract_parameters(actions)

        # Complex selector should not be parameterized
        assert not any("selector" in key for key in params.keys())

    def test_extract_dependencies(self):
        """Test dependency extraction."""
        generator = PlaywrightCodeGenerator()

        actions = [
            {"tool": "playwright_navigate", "arguments": {}},
            {"tool": "playwright_extract_page_fast", "arguments": {}},
        ]

        deps = generator._extract_dependencies(actions)

        assert "playwright" in deps
        assert "re" in deps  # Required for extraction

    def test_generate_action_comment(self):
        """Test action comment generation."""
        generator = PlaywrightCodeGenerator()

        # Navigate
        comment = generator._generate_action_comment(
            "playwright_navigate",
            {"url": "https://example.com"}
        )
        assert "Navigate" in comment
        assert "example.com" in comment

        # Click
        comment = generator._generate_action_comment(
            "playwright_click",
            {"selector": "button.submit"}
        )
        assert "Click" in comment
        assert "button.submit" in comment

        # Fill
        comment = generator._generate_action_comment(
            "playwright_fill",
            {"selector": "input", "value": "test"}
        )
        assert "Fill" in comment
        assert "test" in comment

    def test_should_retry(self):
        """Test determining which tools should have retry logic."""
        generator = PlaywrightCodeGenerator()

        # Should retry
        assert generator._should_retry("playwright_navigate") is True
        assert generator._should_retry("playwright_click") is True
        assert generator._should_retry("playwright_fill") is True
        assert generator._should_retry("playwright_get_text") is True

        # Should not retry
        assert generator._should_retry("playwright_screenshot") is False
        assert generator._should_retry("playwright_snapshot") is False

    def test_generate_python_async(self):
        """Test Python async code generation."""
        generator = PlaywrightCodeGenerator()

        actions = [
            {
                "tool": "playwright_navigate",
                "arguments": {"url": "https://example.com"}
            },
            {
                "tool": "playwright_click",
                "arguments": {"selector": "button"}
            }
        ]

        result = generator.generate_from_trace(
            actions=actions,
            description="Test workflow",
            format="python_async"
        )

        assert "async def" in result.code
        assert "await" in result.code
        assert "async_playwright" in result.code
        assert "playwright_navigate" not in result.code  # Should convert to Playwright API
        assert "page.goto" in result.code
        assert "page.click" in result.code

    def test_generate_python_async_with_parameters(self):
        """Test Python async generation with parameterization."""
        generator = PlaywrightCodeGenerator()

        actions = [
            {
                "tool": "playwright_navigate",
                "arguments": {"url": "https://books.toscrape.com"}
            }
        ]

        result = generator.generate_from_trace(
            actions=actions,
            format="python_async",
            parameterize=True
        )

        # Should have URL as parameter
        assert "url_" in result.code
        assert len(result.parameters) > 0

    def test_generate_python_async_with_comments(self):
        """Test Python async generation includes comments."""
        generator = PlaywrightCodeGenerator(
            config=CodeGenerationConfig(add_comments=True)
        )

        actions = [
            {
                "tool": "playwright_navigate",
                "arguments": {"url": "https://example.com"}
            }
        ]

        result = generator.generate_from_trace(actions, description="Test")

        assert '"""' in result.code
        assert "Generated by Eversale" in result.code
        assert "#" in result.code  # Action comments

    def test_generate_python_async_with_retries(self):
        """Test Python async generation includes retry logic."""
        generator = PlaywrightCodeGenerator(
            config=CodeGenerationConfig(add_retries=True, max_retries=3)
        )

        actions = [
            {
                "tool": "playwright_click",
                "arguments": {"selector": "button"}
            }
        ]

        result = generator.generate_from_trace(actions)

        assert "for attempt in range(3)" in result.code
        assert "try:" in result.code
        assert "except" in result.code
        assert "break" in result.code

    def test_generate_python_async_without_retries(self):
        """Test Python async generation without retry logic."""
        generator = PlaywrightCodeGenerator(
            config=CodeGenerationConfig(add_retries=False)
        )

        actions = [
            {
                "tool": "playwright_click",
                "arguments": {"selector": "button"}
            }
        ]

        result = generator.generate_from_trace(actions)

        assert "for attempt in range" not in result.code

    def test_generate_python_sync(self):
        """Test Python sync code generation."""
        generator = PlaywrightCodeGenerator()

        actions = [
            {
                "tool": "playwright_navigate",
                "arguments": {"url": "https://example.com"}
            }
        ]

        result = generator.generate_from_trace(
            actions=actions,
            format="python_sync"
        )

        assert "async def" not in result.code
        assert "await" not in result.code
        assert "sync_playwright" in result.code
        assert "def main(" in result.code
        assert "page.goto" in result.code

    def test_generate_pytest(self):
        """Test pytest test file generation."""
        generator = PlaywrightCodeGenerator()

        actions = [
            {
                "tool": "playwright_navigate",
                "arguments": {"url": "https://example.com"}
            },
            {
                "tool": "playwright_get_text",
                "arguments": {"selector": "h1"}
            }
        ]

        result = generator.generate_from_trace(
            actions=actions,
            description="Test navigation",
            format="pytest"
        )

        assert "import pytest" in result.code
        assert "@pytest.fixture" in result.code
        assert "def test_" in result.code
        assert "assert" in result.code
        assert "page: Page" in result.code

    def test_tool_to_playwright_async_navigate(self):
        """Test converting navigate tool to async Playwright."""
        generator = PlaywrightCodeGenerator()

        code, result_var = generator._tool_to_playwright_async(
            tool="playwright_navigate",
            args={"url": "https://example.com"},
            parameters={},
            config=CodeGenerationConfig(),
            indent="    ",
            index=0
        )

        assert "await page.goto" in code
        assert "https://example.com" in code
        assert "timeout=" in code
        assert result_var is None

    def test_tool_to_playwright_async_click(self):
        """Test converting click tool to async Playwright."""
        generator = PlaywrightCodeGenerator()

        code, result_var = generator._tool_to_playwright_async(
            tool="playwright_click",
            args={"selector": "button.submit"},
            parameters={},
            config=CodeGenerationConfig(),
            indent="    ",
            index=0
        )

        assert "await page.click" in code
        assert "button.submit" in code
        assert result_var is None

    def test_tool_to_playwright_async_fill(self):
        """Test converting fill tool to async Playwright."""
        generator = PlaywrightCodeGenerator()

        code, result_var = generator._tool_to_playwright_async(
            tool="playwright_fill",
            args={"selector": "input#search", "value": "test query"},
            parameters={},
            config=CodeGenerationConfig(),
            indent="    ",
            index=0
        )

        assert "await page.fill" in code
        assert "input#search" in code
        assert "test query" in code
        assert result_var is None

    def test_tool_to_playwright_async_get_text(self):
        """Test converting get_text tool to async Playwright."""
        generator = PlaywrightCodeGenerator()

        code, result_var = generator._tool_to_playwright_async(
            tool="playwright_get_text",
            args={"selector": "h1"},
            parameters={},
            config=CodeGenerationConfig(),
            indent="    ",
            index=0
        )

        assert "await page.text_content" in code
        assert "h1" in code
        assert result_var == "text_0"

    def test_tool_to_playwright_async_screenshot(self):
        """Test converting screenshot tool to async Playwright."""
        generator = PlaywrightCodeGenerator()

        code, result_var = generator._tool_to_playwright_async(
            tool="playwright_screenshot",
            args={"path": "screenshot.png"},
            parameters={},
            config=CodeGenerationConfig(),
            indent="    ",
            index=0
        )

        assert "await page.screenshot" in code
        assert "screenshot.png" in code

    def test_tool_to_playwright_async_evaluate(self):
        """Test converting evaluate tool to async Playwright."""
        generator = PlaywrightCodeGenerator()

        code, result_var = generator._tool_to_playwright_async(
            tool="playwright_evaluate",
            args={"script": "return document.title"},
            parameters={},
            config=CodeGenerationConfig(),
            indent="    ",
            index=0
        )

        assert "await page.evaluate" in code
        assert "document.title" in code
        assert result_var == "eval_result_0"

    def test_tool_to_playwright_async_custom_tools(self):
        """Test converting custom Eversale tools."""
        generator = PlaywrightCodeGenerator()

        # Extract page fast
        code, _ = generator._tool_to_playwright_async(
            tool="playwright_extract_page_fast",
            args={},
            parameters={},
            config=CodeGenerationConfig(),
            indent="    ",
            index=0
        )

        assert "Custom extraction tool" in code

    def test_tool_to_playwright_sync(self):
        """Test converting tools to sync Playwright."""
        generator = PlaywrightCodeGenerator()

        code, result_var = generator._tool_to_playwright_sync(
            tool="playwright_navigate",
            args={"url": "https://example.com"},
            parameters={},
            config=CodeGenerationConfig(),
            indent="    ",
            index=0
        )

        assert "page.goto" in code
        assert "await" not in code
        assert "https://example.com" in code

    def test_generate_from_skill(self):
        """Test generating code from skill."""
        generator = PlaywrightCodeGenerator()

        # Mock skill object
        mock_skill = Mock()
        mock_skill.required_tools = ["playwright_navigate", "playwright_click"]
        mock_skill.description = "Test skill"

        result = generator.generate_from_skill(
            skill=mock_skill,
            format="python_async"
        )

        assert result.code is not None
        assert result.description == "Test skill"

    def test_save_to_file(self, tmp_path):
        """Test saving generated code to file."""
        generator = PlaywrightCodeGenerator()

        generated = GeneratedCode(
            code="print('hello')",
            format=CodeFormat.PYTHON_ASYNC,
            parameters={"url": {"value": "https://example.com", "type": "str"}},
            dependencies=["playwright"],
            description="Test"
        )

        output_path = tmp_path / "test_workflow.py"

        generator.save_to_file(generated, output_path)

        # Check code file
        assert output_path.exists()
        assert output_path.read_text() == "print('hello')"

        # Check metadata file
        metadata_path = output_path.with_suffix('.json')
        assert metadata_path.exists()

        import json
        metadata = json.loads(metadata_path.read_text())
        assert metadata["format"] == "python_async"
        assert "url" in metadata["parameters"]
        assert "playwright" in metadata["dependencies"]

    def test_apply_overrides(self):
        """Test applying configuration overrides."""
        config = CodeGenerationConfig(max_retries=3)
        generator = PlaywrightCodeGenerator(config=config)

        overrides = {"max_retries": 5, "timeout": 60000}
        new_config = generator._apply_overrides(None, overrides)

        assert new_config.max_retries == 5
        assert new_config.timeout == 60000

    def test_apply_overrides_format(self):
        """Test applying format override."""
        generator = PlaywrightCodeGenerator()

        new_config = generator._apply_overrides("pytest", {})

        assert new_config.format == CodeFormat.PYTEST


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_export_workflow(self, tmp_path):
        """Test export_workflow function."""
        actions = [
            {
                "tool": "playwright_navigate",
                "arguments": {"url": "https://example.com"}
            }
        ]

        output_path = tmp_path / "workflow.py"

        result = export_workflow(
            actions=actions,
            output_path=output_path,
            format="python_async",
            description="Test workflow"
        )

        assert output_path.exists()
        assert result.code is not None
        assert result.description == "Test workflow"

    def test_export_skill(self, tmp_path):
        """Test export_skill function."""
        mock_skill = Mock()
        mock_skill.required_tools = ["playwright_navigate"]
        mock_skill.description = "Test skill"

        output_path = tmp_path / "skill.py"

        result = export_skill(
            skill=mock_skill,
            output_path=output_path,
            format="python_async"
        )

        assert output_path.exists()
        assert result.description == "Test skill"


class TestCodeGenerationIntegration:
    """Integration tests for code generation."""

    def test_generate_complete_workflow(self):
        """Test generating a complete workflow."""
        generator = PlaywrightCodeGenerator()

        actions = [
            {
                "tool": "playwright_navigate",
                "arguments": {"url": "https://books.toscrape.com"}
            },
            {
                "tool": "playwright_fill",
                "arguments": {"selector": "input#search", "value": "python"}
            },
            {
                "tool": "playwright_click",
                "arguments": {"selector": "button[type='submit']"}
            },
            {
                "tool": "playwright_get_text",
                "arguments": {"selector": "h1"}
            }
        ]

        result = generator.generate_from_trace(
            actions=actions,
            description="Search for Python books",
            format="python_async"
        )

        # Verify structure
        assert "import asyncio" in result.code
        assert "from playwright.async_api import" in result.code
        assert "async def main(" in result.code
        assert "async with async_playwright()" in result.code
        assert "await page.goto" in result.code
        assert "await page.fill" in result.code
        assert "await page.click" in result.code
        assert "await page.text_content" in result.code
        assert 'if __name__ == "__main__"' in result.code

        # Verify it's valid Python (basic check)
        import ast
        ast.parse(result.code)

    def test_generate_pytest_test(self):
        """Test generating a pytest test."""
        generator = PlaywrightCodeGenerator()

        actions = [
            {
                "tool": "playwright_navigate",
                "arguments": {"url": "https://example.com"}
            },
            {
                "tool": "playwright_get_text",
                "arguments": {"selector": "h1"}
            }
        ]

        result = generator.generate_from_trace(
            actions=actions,
            description="Test homepage",
            format="pytest"
        )

        # Verify pytest structure
        assert "import pytest" in result.code
        assert "@pytest.fixture" in result.code
        assert "def test_workflow(page: Page)" in result.code
        assert "assert page.url" in result.code

        # Should be valid Python
        import ast
        ast.parse(result.code)
