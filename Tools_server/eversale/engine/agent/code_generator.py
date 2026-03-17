#!/usr/bin/env python3
"""
Playwright Code Generator - Export workflows as reusable Playwright scripts

Converts agent execution traces into clean, production-ready Playwright code.
Supports multiple output formats:
- Python async scripts
- Python sync scripts
- Pytest test files
- TypeScript scripts
- JavaScript scripts

Key Features:
1. Clean, idiomatic Playwright code
2. Proper error handling and retries
3. Human-readable comments
4. Parameterization of URLs and selectors
5. Integration with skill library
6. Export from execution history or skills

Example Usage:
    # From execution trace
    generator = PlaywrightCodeGenerator()
    code = generator.generate_from_trace(
        actions=[
            {"tool": "playwright_navigate", "arguments": {"url": "https://example.com"}},
            {"tool": "playwright_click", "arguments": {"selector": "button.submit"}}
        ],
        format="python_async"
    )

    # From skill
    code = generator.generate_from_skill(skill, format="pytest")

    # From agent's last workflow
    code = await agent.export_last_workflow(format="python_sync")
"""

import ast
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger


class CodeFormat(Enum):
    """Supported output formats"""
    PYTHON_ASYNC = "python_async"  # Async Python script
    PYTHON_SYNC = "python_sync"    # Sync Python script
    PYTEST = "pytest"               # Pytest test file
    TYPESCRIPT = "typescript"       # TypeScript (future)
    JAVASCRIPT = "javascript"       # JavaScript (future)


@dataclass
class CodeGenerationConfig:
    """Configuration for code generation"""
    format: CodeFormat = CodeFormat.PYTHON_ASYNC
    add_comments: bool = True
    add_error_handling: bool = True
    add_retries: bool = True
    add_logging: bool = True
    add_screenshots: bool = False
    parameterize: bool = True
    max_retries: int = 3
    timeout: int = 30000  # 30 seconds default
    headless: bool = False
    include_imports: bool = True
    include_setup: bool = True
    function_name: str = "main"
    test_name: str = "test_workflow"


@dataclass
class GeneratedCode:
    """Generated code with metadata"""
    code: str
    format: CodeFormat
    parameters: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    description: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class PlaywrightCodeGenerator:
    """
    Generates clean Playwright code from execution traces or skills
    """

    def __init__(self, config: Optional[CodeGenerationConfig] = None):
        self.config = config or CodeGenerationConfig()

    def generate_from_trace(
        self,
        actions: List[Dict[str, Any]],
        description: str = "",
        format: Optional[str] = None,
        **kwargs
    ) -> GeneratedCode:
        """
        Generate code from an execution trace (list of tool calls)

        Args:
            actions: List of tool call dictionaries with 'tool' and 'arguments'
            description: What the workflow does
            format: Output format override
            **kwargs: Additional config overrides

        Returns:
            GeneratedCode object with code and metadata
        """
        # Apply overrides
        config = self._apply_overrides(format, kwargs)

        # Extract parameters from actions
        parameters = self._extract_parameters(actions) if config.parameterize else {}

        # Generate code based on format
        if config.format == CodeFormat.PYTHON_ASYNC:
            code = self._generate_python_async(actions, description, parameters, config)
        elif config.format == CodeFormat.PYTHON_SYNC:
            code = self._generate_python_sync(actions, description, parameters, config)
        elif config.format == CodeFormat.PYTEST:
            code = self._generate_pytest(actions, description, parameters, config)
        elif config.format == CodeFormat.TYPESCRIPT:
            code = self._generate_typescript(actions, description, parameters, config)
        elif config.format == CodeFormat.JAVASCRIPT:
            code = self._generate_javascript(actions, description, parameters, config)
        else:
            raise ValueError(f"Unsupported format: {config.format}")

        # Extract dependencies
        dependencies = self._extract_dependencies(actions)

        return GeneratedCode(
            code=code,
            format=config.format,
            parameters=parameters,
            dependencies=dependencies,
            description=description
        )

    def generate_from_skill(
        self,
        skill: Any,
        format: Optional[str] = None,
        **kwargs
    ) -> GeneratedCode:
        """
        Generate code from a Skill object

        Args:
            skill: Skill instance from skill_library
            format: Output format override
            **kwargs: Additional config overrides

        Returns:
            GeneratedCode object
        """
        # Extract actions from skill's required_tools and code
        actions = self._skill_to_actions(skill)

        return self.generate_from_trace(
            actions=actions,
            description=skill.description,
            format=format,
            **kwargs
        )

    def _apply_overrides(self, format: Optional[str], kwargs: Dict) -> CodeGenerationConfig:
        """Apply configuration overrides"""
        config = CodeGenerationConfig(**{**self.config.__dict__, **kwargs})

        if format:
            if isinstance(format, str):
                config.format = CodeFormat(format)
            else:
                config.format = format

        return config

    def _extract_parameters(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract parameterizable values from actions"""
        parameters = {}

        for i, action in enumerate(actions):
            args = action.get('arguments', {})

            # URLs should be parameters
            if 'url' in args:
                url = args['url']
                if url and isinstance(url, str):
                    param_name = self._generate_param_name(url, 'url')
                    parameters[param_name] = {
                        'value': url,
                        'type': 'str',
                        'description': f'Target URL for navigation'
                    }

            # Selectors can be parameters (but often should stay hardcoded)
            if 'selector' in args and args['selector']:
                selector = args['selector']
                # Only parameterize simple selectors, not complex ones
                if len(selector) < 50 and ' ' not in selector:
                    param_name = f"selector_{i}"
                    parameters[param_name] = {
                        'value': selector,
                        'type': 'str',
                        'description': f'CSS selector for element'
                    }

            # Search queries, text inputs
            for key in ['query', 'text', 'value']:
                if key in args and args[key]:
                    value = args[key]
                    if isinstance(value, str) and len(value) > 0:
                        param_name = self._generate_param_name(value, key)
                        parameters[param_name] = {
                            'value': value,
                            'type': 'str',
                            'description': f'{key.capitalize()} to use'
                        }

        return parameters

    def _generate_param_name(self, value: str, prefix: str = '') -> str:
        """Generate a clean parameter name from a value"""
        # Clean the value
        clean = re.sub(r'[^a-zA-Z0-9_]', '_', value.lower())
        clean = re.sub(r'_+', '_', clean)
        clean = clean.strip('_')[:30]  # Max 30 chars

        if prefix:
            return f"{prefix}_{clean}" if clean else prefix
        return clean or "param"

    def _extract_dependencies(self, actions: List[Dict[str, Any]]) -> List[str]:
        """Extract Python package dependencies"""
        deps = {'playwright'}  # Always need playwright

        for action in actions:
            tool = action.get('tool', '')

            # Check if any actions require additional packages
            if 'extract' in tool or 'find_contacts' in tool:
                deps.add('re')  # Regex for extraction

            if 'csv' in tool or any('csv' in str(v) for v in action.get('arguments', {}).values()):
                deps.add('csv')

        return sorted(list(deps))

    def _generate_python_async(
        self,
        actions: List[Dict[str, Any]],
        description: str,
        parameters: Dict[str, Any],
        config: CodeGenerationConfig
    ) -> str:
        """Generate async Python script"""
        lines = []

        # Header comment
        if config.add_comments and description:
            lines.extend([
                '"""',
                description,
                '',
                f'Generated by Eversale at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                '"""',
                ''
            ])

        # Imports
        if config.include_imports:
            lines.extend([
                'import asyncio',
                'from playwright.async_api import async_playwright, Page, Browser',
            ])
            if config.add_logging:
                lines.append('import logging')
            if parameters:
                lines.append('from typing import Dict, Any')
            lines.append('')

        # Logging setup
        if config.add_logging:
            lines.extend([
                'logging.basicConfig(level=logging.INFO)',
                'logger = logging.getLogger(__name__)',
                ''
            ])

        # Main function signature
        if parameters:
            lines.append(f'async def {config.function_name}(')
            for param_name, param_info in parameters.items():
                default_val = repr(param_info['value'])
                lines.append(f'    {param_name}: str = {default_val},')
            lines.append(') -> Dict[str, Any]:')
        else:
            lines.append(f'async def {config.function_name}() -> Dict[str, Any]:')

        # Function docstring
        if config.add_comments:
            lines.append('    """')
            lines.append(f'    {description or "Automated workflow"}')
            if parameters:
                lines.append('')
                lines.append('    Args:')
                for param_name, param_info in parameters.items():
                    lines.append(f'        {param_name}: {param_info["description"]}')
            lines.append('    """')

        # Browser setup
        if config.include_setup:
            lines.extend([
                '    async with async_playwright() as p:',
                f'        browser = await p.chromium.launch(headless={config.headless})',
                '        context = await browser.new_context(',
                '            viewport={"width": 1920, "height": 1080},',
                '            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"',
                '        )',
                '        page = await context.new_page()',
                '',
                '        try:',
            ])
            indent = '            '
        else:
            indent = '    '

        # Generate action code
        action_code = self._generate_action_code(actions, parameters, config, indent)
        lines.extend(action_code)

        # Results and cleanup
        if config.include_setup:
            lines.extend([
                '',
                f'{indent}return {{"success": True, "message": "Workflow completed successfully"}}',
                '',
                '        except Exception as e:',
            ])
            if config.add_logging:
                lines.append('            logger.error(f"Workflow failed: {e}")')
            lines.extend([
                '            return {"success": False, "error": str(e)}',
                '',
                '        finally:',
                '            await browser.close()',
            ])

        # Entry point
        lines.extend([
            '',
            '',
            'if __name__ == "__main__":',
            f'    result = asyncio.run({config.function_name}())',
            '    print(f"Result: {result}")',
        ])

        return '\n'.join(lines)

    def _generate_python_sync(
        self,
        actions: List[Dict[str, Any]],
        description: str,
        parameters: Dict[str, Any],
        config: CodeGenerationConfig
    ) -> str:
        """Generate sync Python script using playwright.sync_api"""
        lines = []

        # Header comment
        if config.add_comments and description:
            lines.extend([
                '"""',
                description,
                '',
                f'Generated by Eversale at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                '"""',
                ''
            ])

        # Imports
        if config.include_imports:
            lines.extend([
                'from playwright.sync_api import sync_playwright, Page, Browser',
            ])
            if config.add_logging:
                lines.append('import logging')
            if parameters:
                lines.append('from typing import Dict, Any')
            lines.append('')

        # Logging setup
        if config.add_logging:
            lines.extend([
                'logging.basicConfig(level=logging.INFO)',
                'logger = logging.getLogger(__name__)',
                ''
            ])

        # Main function signature
        if parameters:
            lines.append(f'def {config.function_name}(')
            for param_name, param_info in parameters.items():
                default_val = repr(param_info['value'])
                lines.append(f'    {param_name}: str = {default_val},')
            lines.append(') -> Dict[str, Any]:')
        else:
            lines.append(f'def {config.function_name}() -> Dict[str, Any]:')

        # Function docstring
        if config.add_comments:
            lines.append('    """')
            lines.append(f'    {description or "Automated workflow"}')
            if parameters:
                lines.append('')
                lines.append('    Args:')
                for param_name, param_info in parameters.items():
                    lines.append(f'        {param_name}: {param_info["description"]}')
            lines.append('    """')

        # Browser setup
        if config.include_setup:
            lines.extend([
                '    with sync_playwright() as p:',
                f'        browser = p.chromium.launch(headless={config.headless})',
                '        context = browser.new_context(',
                '            viewport={"width": 1920, "height": 1080},',
                '            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"',
                '        )',
                '        page = context.new_page()',
                '',
                '        try:',
            ])
            indent = '            '
        else:
            indent = '    '

        # Generate action code (sync version)
        action_code = self._generate_action_code_sync(actions, parameters, config, indent)
        lines.extend(action_code)

        # Results and cleanup
        if config.include_setup:
            lines.extend([
                '',
                f'{indent}return {{"success": True, "message": "Workflow completed successfully"}}',
                '',
                '        except Exception as e:',
            ])
            if config.add_logging:
                lines.append('            logger.error(f"Workflow failed: {e}")')
            lines.extend([
                '            return {"success": False, "error": str(e)}',
                '',
                '        finally:',
                '            browser.close()',
            ])

        # Entry point
        lines.extend([
            '',
            '',
            'if __name__ == "__main__":',
            f'    result = {config.function_name}()',
            '    print(f"Result: {result}")',
        ])

        return '\n'.join(lines)

    def _generate_pytest(
        self,
        actions: List[Dict[str, Any]],
        description: str,
        parameters: Dict[str, Any],
        config: CodeGenerationConfig
    ) -> str:
        """Generate pytest test file"""
        lines = []

        # Header comment
        if config.add_comments and description:
            lines.extend([
                '"""',
                f'Test: {description}',
                '',
                f'Generated by Eversale at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                '"""',
                ''
            ])

        # Imports
        if config.include_imports:
            lines.extend([
                'import pytest',
                'from playwright.sync_api import Page, Browser, expect',
                ''
            ])

        # Fixtures
        lines.extend([
            '@pytest.fixture(scope="function")',
            'def browser_context(browser):',
            '    context = browser.new_context(',
            '        viewport={"width": 1920, "height": 1080},',
            '        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"',
            '    )',
            '    yield context',
            '    context.close()',
            '',
            '@pytest.fixture(scope="function")',
            'def page(browser_context):',
            '    page = browser_context.new_page()',
            '    yield page',
            '    page.close()',
            ''
        ])

        # Test function
        lines.append(f'def {config.test_name}(page: Page):')

        # Docstring
        if config.add_comments:
            lines.append('    """')
            lines.append(f'    {description or "Test automated workflow"}')
            lines.append('    """')

        # Generate action code
        indent = '    '
        action_code = self._generate_action_code_sync(actions, parameters, config, indent)
        lines.extend(action_code)

        # Add assertion at the end
        lines.extend([
            '',
            '    # Verify workflow completed',
            f'    assert page.url, "Page should have loaded"',
        ])

        return '\n'.join(lines)

    def _generate_typescript(
        self,
        actions: List[Dict[str, Any]],
        description: str,
        parameters: Dict[str, Any],
        config: CodeGenerationConfig
    ) -> str:
        """Generate TypeScript Playwright code"""
        lines = []

        # Header comment
        if config.add_comments and description:
            lines.extend([
                '/**',
                f' * {description}',
                ' *',
                f' * Generated by Eversale at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                ' */',
                ''
            ])

        # Imports
        lines.extend([
            "import { chromium, Browser, Page } from 'playwright';",
            ''
        ])

        # Interface definitions
        lines.extend([
            'interface WorkflowResult {',
            '    success: boolean;',
            '    data?: any;',
            '    error?: string;',
            '}',
            ''
        ])

        # Parameters interface if needed
        if parameters:
            lines.extend([
                'interface WorkflowParams {',
            ])
            for param_name, param_info in parameters.items():
                lines.append(f'    {param_name}?: string;')
            lines.extend([
                '}',
                ''
            ])

        # Function signature
        if parameters:
            lines.append(f'async function {config.function_name}(params: WorkflowParams = {{}}): Promise<WorkflowResult> {{')
            # Destructure parameters with defaults
            lines.append('    const {')
            for param_name, param_info in parameters.items():
                default_val = param_info['value']
                # Escape single quotes in default values
                default_val = default_val.replace("'", "\\'")
                lines.append(f"        {param_name} = '{default_val}',")
            lines.append('    } = params;')
            lines.append('')
        else:
            lines.append(f'async function {config.function_name}(): Promise<WorkflowResult> {{')

        # Browser setup
        lines.extend([
            f'    const browser: Browser = await chromium.launch({{ headless: {str(config.headless).lower()} }});',
            '    const page: Page = await browser.newPage({',
            '        viewport: { width: 1920, height: 1080 },',
            "        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'",
            '    });',
            '',
            '    try {',
        ])

        # Generate action code
        action_code = self._generate_action_code_typescript(actions, parameters, config, '        ')
        lines.extend(action_code)

        # Return and error handling
        lines.extend([
            '',
            "        return { success: true, data: { message: 'Workflow completed successfully' } };",
            '',
            '    } catch (error) {',
        ])
        if config.add_logging:
            lines.append("        console.error('Workflow failed:', error);")
        lines.extend([
            '        return { success: false, error: String(error) };',
            '',
            '    } finally {',
            '        await browser.close();',
            '    }',
            '}',
            ''
        ])

        # Entry point
        lines.extend([
            '// Execute workflow',
            f'{config.function_name}().then(result => {{',
            "    console.log('Result:', result);",
            '});',
        ])

        return '\n'.join(lines)

    def _generate_javascript(
        self,
        actions: List[Dict[str, Any]],
        description: str,
        parameters: Dict[str, Any],
        config: CodeGenerationConfig
    ) -> str:
        """Generate JavaScript Playwright code"""
        lines = []

        # Header comment
        if config.add_comments and description:
            lines.extend([
                '/**',
                f' * {description}',
                ' *',
                f' * Generated by Eversale at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                ' */',
                ''
            ])

        # Imports
        lines.extend([
            "const { chromium } = require('playwright');",
            ''
        ])

        # Function signature
        if parameters:
            lines.append(f'async function {config.function_name}({{')
            # Destructure parameters with defaults
            for param_name, param_info in parameters.items():
                default_val = param_info['value']
                # Escape single quotes in default values
                default_val = default_val.replace("'", "\\'")
                lines.append(f"    {param_name} = '{default_val}',")
            lines.append('} = {}) {')
        else:
            lines.append(f'async function {config.function_name}() {{')

        # Browser setup
        lines.extend([
            f'    const browser = await chromium.launch({{ headless: {str(config.headless).lower()} }});',
            '    const page = await browser.newPage({',
            '        viewport: { width: 1920, height: 1080 },',
            "        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'",
            '    });',
            '',
            '    try {',
        ])

        # Generate action code (same as TypeScript but without types)
        action_code = self._generate_action_code_javascript(actions, parameters, config, '        ')
        lines.extend(action_code)

        # Return and error handling
        lines.extend([
            '',
            "        return { success: true, data: { message: 'Workflow completed successfully' } };",
            '',
            '    } catch (error) {',
        ])
        if config.add_logging:
            lines.append("        console.error('Workflow failed:', error);")
        lines.extend([
            '        return { success: false, error: String(error) };',
            '',
            '    } finally {',
            '        await browser.close();',
            '    }',
            '}',
            ''
        ])

        # Entry point
        lines.extend([
            '// Execute workflow',
            f'{config.function_name}().then(result => {{',
            "    console.log('Result:', result);",
            '});',
        ])

        return '\n'.join(lines)

    def _generate_action_code_typescript(
        self,
        actions: List[Dict[str, Any]],
        parameters: Dict[str, Any],
        config: CodeGenerationConfig,
        indent: str = '    '
    ) -> List[str]:
        """Generate TypeScript action code"""
        lines = []

        for i, action in enumerate(actions):
            tool = action.get('tool', '')
            args = action.get('arguments', {})

            # Add comment before action
            if config.add_comments:
                comment = self._generate_action_comment(tool, args)
                lines.append(f'{indent}// {comment}')

            # Generate the Playwright call
            code_line, result_var = self._tool_to_playwright_typescript(tool, args, parameters, config, indent, i)

            if code_line:
                # Add retry wrapper if enabled
                if config.add_retries and self._should_retry(tool):
                    lines.append(f'{indent}for (let attempt = 0; attempt < {config.max_retries}; attempt++) {{')
                    lines.append(f'{indent}    try {{')
                    lines.append(f'{indent}        {code_line}')
                    if config.add_logging:
                        lines.append(f'{indent}        console.log("Action {i+1} succeeded");')
                    lines.append(f'{indent}        break;')
                    lines.append(f'{indent}    }} catch (error) {{')
                    lines.append(f'{indent}        if (attempt === {config.max_retries - 1}) {{')
                    lines.append(f'{indent}            throw error;')
                    lines.append(f'{indent}        }}')
                    if config.add_logging:
                        lines.append(f'{indent}        console.warn(`Retry ${{attempt + 1}}/{config.max_retries}: ${{error}}`);')
                    lines.append(f'{indent}        await new Promise(resolve => setTimeout(resolve, 1000));')
                    lines.append(f'{indent}    }}')
                    lines.append(f'{indent}}}')
                else:
                    lines.append(f'{indent}{code_line}')

                # Add screenshot if enabled
                if config.add_screenshots:
                    lines.append(f'{indent}await page.screenshot({{ path: `screenshot_{i+1}.png` }});')

                lines.append('')

        return lines

    def _generate_action_code_javascript(
        self,
        actions: List[Dict[str, Any]],
        parameters: Dict[str, Any],
        config: CodeGenerationConfig,
        indent: str = '    '
    ) -> List[str]:
        """Generate JavaScript action code"""
        # JavaScript action code is identical to TypeScript, just without type annotations
        return self._generate_action_code_typescript(actions, parameters, config, indent)

    def _tool_to_playwright_typescript(
        self,
        tool: str,
        args: Dict[str, Any],
        parameters: Dict[str, Any],
        config: CodeGenerationConfig,
        indent: str,
        index: int
    ) -> Tuple[str, Optional[str]]:
        """Convert tool call to TypeScript Playwright code"""

        # Get parameterized values or use originals
        def get_value(key, default=None):
            value = args.get(key, default)
            # Check if this value was parameterized
            for param_name, param_info in parameters.items():
                if param_info['value'] == value:
                    return param_name  # Use parameter variable
            # Escape single quotes for TypeScript strings
            if isinstance(value, str):
                value = value.replace("'", "\\'")
                return f"'{value}'"
            return repr(value)

        if tool == 'playwright_navigate':
            url_val = get_value('url')
            return f"await page.goto({url_val}, {{ waitUntil: 'domcontentloaded', timeout: {config.timeout} }});", None

        elif tool == 'playwright_click':
            selector_val = get_value('selector')
            return f"await page.click({selector_val}, {{ timeout: {config.timeout} }});", None

        elif tool == 'playwright_fill':
            selector_val = get_value('selector')
            value_val = get_value('value')
            return f"await page.fill({selector_val}, {value_val}, {{ timeout: {config.timeout} }});", None

        elif tool == 'playwright_get_text':
            selector_val = get_value('selector')
            result_var = f"text{index}"
            return f"const {result_var} = await page.textContent({selector_val}, {{ timeout: {config.timeout} }});", result_var

        elif tool == 'playwright_snapshot':
            result_var = f"snapshot{index}"
            return f"const {result_var} = await page.content();", result_var

        elif tool == 'playwright_screenshot':
            path = args.get('path', f'screenshot_{index}.png')
            path = path.replace("'", "\\'")
            return f"await page.screenshot({{ path: '{path}' }});", None

        elif tool == 'playwright_evaluate':
            script = args.get('script', '')
            script = script.replace("'", "\\'")
            result_var = f"evalResult{index}"
            return f"const {result_var} = await page.evaluate('{script}');", result_var

        elif tool in ['playwright_extract_page_fast', 'playwright_find_contacts']:
            return f"// Custom extraction tool: {tool} - implement using page.content() and regex", None

        elif tool == 'playwright_extract_fb_ads':
            return "// Facebook Ads extraction - implement custom scraping logic", None

        elif tool == 'playwright_extract_reddit':
            return "// Reddit extraction - implement custom scraping logic", None

        else:
            return f"// Unsupported tool: {tool}", None

    def _generate_action_code(
        self,
        actions: List[Dict[str, Any]],
        parameters: Dict[str, Any],
        config: CodeGenerationConfig,
        indent: str = '    '
    ) -> List[str]:
        """Generate async action code"""
        lines = []
        result_vars = []

        for i, action in enumerate(actions):
            tool = action.get('tool', '')
            args = action.get('arguments', {})

            # Add comment before action
            if config.add_comments:
                comment = self._generate_action_comment(tool, args)
                lines.append(f'{indent}# {comment}')

            # Generate the Playwright call
            code_line, result_var = self._tool_to_playwright_async(tool, args, parameters, config, indent, i)

            if code_line:
                # Add retry wrapper if enabled
                if config.add_retries and self._should_retry(tool):
                    lines.append(f'{indent}for attempt in range({config.max_retries}):')
                    lines.append(f'{indent}    try:')
                    lines.append(f'{indent}        {code_line}')
                    if config.add_logging:
                        lines.append(f'{indent}        logger.info("Action {i+1} succeeded")')
                    lines.append(f'{indent}        break')
                    lines.append(f'{indent}    except Exception as e:')
                    lines.append(f'{indent}        if attempt == {config.max_retries - 1}:')
                    lines.append(f'{indent}            raise')
                    if config.add_logging:
                        lines.append(f'{indent}        logger.warning(f"Retry {{attempt + 1}}/{{config.max_retries}}: {{e}}")')
                    lines.append(f'{indent}        await asyncio.sleep(1)')
                else:
                    lines.append(f'{indent}{code_line}')

                if result_var:
                    result_vars.append(result_var)

                # Add screenshot if enabled
                if config.add_screenshots:
                    lines.append(f'{indent}await page.screenshot(path=f"screenshot_{i+1}.png")')

                lines.append('')

        return lines

    def _generate_action_code_sync(
        self,
        actions: List[Dict[str, Any]],
        parameters: Dict[str, Any],
        config: CodeGenerationConfig,
        indent: str = '    '
    ) -> List[str]:
        """Generate sync action code"""
        lines = []
        result_vars = []

        for i, action in enumerate(actions):
            tool = action.get('tool', '')
            args = action.get('arguments', {})

            # Add comment before action
            if config.add_comments:
                comment = self._generate_action_comment(tool, args)
                lines.append(f'{indent}# {comment}')

            # Generate the Playwright call
            code_line, result_var = self._tool_to_playwright_sync(tool, args, parameters, config, indent, i)

            if code_line:
                # Add retry wrapper if enabled
                if config.add_retries and self._should_retry(tool):
                    lines.append(f'{indent}for attempt in range({config.max_retries}):')
                    lines.append(f'{indent}    try:')
                    lines.append(f'{indent}        {code_line}')
                    if config.add_logging:
                        lines.append(f'{indent}        logger.info("Action {i+1} succeeded")')
                    lines.append(f'{indent}        break')
                    lines.append(f'{indent}    except Exception as e:')
                    lines.append(f'{indent}        if attempt == {config.max_retries - 1}:')
                    lines.append(f'{indent}            raise')
                    if config.add_logging:
                        lines.append(f'{indent}        logger.warning(f"Retry {{attempt + 1}}/{{config.max_retries}}: {{e}}")')
                    lines.append(f'{indent}        import time; time.sleep(1)')
                else:
                    lines.append(f'{indent}{code_line}')

                if result_var:
                    result_vars.append(result_var)

                # Add screenshot if enabled
                if config.add_screenshots:
                    lines.append(f'{indent}page.screenshot(path=f"screenshot_{i+1}.png")')

                lines.append('')

        return lines

    def _generate_action_comment(self, tool: str, args: Dict[str, Any]) -> str:
        """Generate human-readable comment for action"""
        if tool == 'playwright_navigate':
            url = args.get('url', 'URL')
            return f"Navigate to {url}"
        elif tool == 'playwright_click':
            selector = args.get('selector', 'element')
            return f"Click {selector}"
        elif tool == 'playwright_fill':
            selector = args.get('selector', 'input')
            value = args.get('value', 'value')
            return f"Fill {selector} with '{value}'"
        elif tool == 'playwright_get_text':
            selector = args.get('selector', 'element')
            return f"Get text from {selector}"
        elif tool == 'playwright_snapshot':
            return "Take page snapshot"
        elif tool == 'playwright_screenshot':
            return "Take screenshot"
        elif tool == 'playwright_extract_page_fast':
            return "Extract contacts from page"
        elif tool == 'playwright_extract_fb_ads':
            return "Extract Facebook Ads Library data"
        elif tool == 'playwright_extract_reddit':
            return "Extract Reddit posts"
        elif tool == 'playwright_find_contacts':
            return "Find email/phone contacts"
        elif tool == 'playwright_batch_extract':
            urls = args.get('urls', [])
            return f"Batch extract from {len(urls)} URLs"
        else:
            return f"Execute {tool}"

    def _tool_to_playwright_async(
        self,
        tool: str,
        args: Dict[str, Any],
        parameters: Dict[str, Any],
        config: CodeGenerationConfig,
        indent: str,
        index: int
    ) -> Tuple[str, Optional[str]]:
        """Convert tool call to async Playwright code"""

        # Get parameterized values or use originals
        def get_value(key, default=None):
            value = args.get(key, default)
            # Check if this value was parameterized
            for param_name, param_info in parameters.items():
                if param_info['value'] == value:
                    return param_name  # Use parameter variable
            return repr(value)  # Use literal value

        if tool == 'playwright_navigate':
            url_val = get_value('url')
            return f"await page.goto({url_val}, wait_until='domcontentloaded', timeout={config.timeout})", None

        elif tool == 'playwright_click':
            selector_val = get_value('selector')
            return f"await page.click({selector_val}, timeout={config.timeout})", None

        elif tool == 'playwright_fill':
            selector_val = get_value('selector')
            value_val = get_value('value')
            return f"await page.fill({selector_val}, {value_val}, timeout={config.timeout})", None

        elif tool == 'playwright_get_text':
            selector_val = get_value('selector')
            result_var = f"text_{index}"
            return f"{result_var} = await page.text_content({selector_val}, timeout={config.timeout})", result_var

        elif tool == 'playwright_snapshot':
            result_var = f"snapshot_{index}"
            return f"{result_var} = await page.content()", result_var

        elif tool == 'playwright_screenshot':
            path = args.get('path', f'screenshot_{index}.png')
            return f"await page.screenshot(path={repr(path)})", None

        elif tool == 'playwright_evaluate':
            script = args.get('script', '')
            result_var = f"eval_result_{index}"
            return f"{result_var} = await page.evaluate({repr(script)})", result_var

        elif tool in ['playwright_extract_page_fast', 'playwright_find_contacts']:
            # These are custom Eversale tools - add a comment
            return f"# Custom extraction tool: {tool} - implement using page.content() and regex", None

        elif tool == 'playwright_extract_fb_ads':
            return "# Facebook Ads extraction - implement custom scraping logic", None

        elif tool == 'playwright_extract_reddit':
            return "# Reddit extraction - implement custom scraping logic", None

        else:
            return f"# Unsupported tool: {tool}", None

    def _tool_to_playwright_sync(
        self,
        tool: str,
        args: Dict[str, Any],
        parameters: Dict[str, Any],
        config: CodeGenerationConfig,
        indent: str,
        index: int
    ) -> Tuple[str, Optional[str]]:
        """Convert tool call to sync Playwright code"""

        # Get parameterized values or use originals
        def get_value(key, default=None):
            value = args.get(key, default)
            # Check if this value was parameterized
            for param_name, param_info in parameters.items():
                if param_info['value'] == value:
                    return param_name  # Use parameter variable
            return repr(value)  # Use literal value

        if tool == 'playwright_navigate':
            url_val = get_value('url')
            return f"page.goto({url_val}, wait_until='domcontentloaded', timeout={config.timeout})", None

        elif tool == 'playwright_click':
            selector_val = get_value('selector')
            return f"page.click({selector_val}, timeout={config.timeout})", None

        elif tool == 'playwright_fill':
            selector_val = get_value('selector')
            value_val = get_value('value')
            return f"page.fill({selector_val}, {value_val}, timeout={config.timeout})", None

        elif tool == 'playwright_get_text':
            selector_val = get_value('selector')
            result_var = f"text_{index}"
            return f"{result_var} = page.text_content({selector_val}, timeout={config.timeout})", result_var

        elif tool == 'playwright_snapshot':
            result_var = f"snapshot_{index}"
            return f"{result_var} = page.content()", result_var

        elif tool == 'playwright_screenshot':
            path = args.get('path', f'screenshot_{index}.png')
            return f"page.screenshot(path={repr(path)})", None

        elif tool == 'playwright_evaluate':
            script = args.get('script', '')
            result_var = f"eval_result_{index}"
            return f"{result_var} = page.evaluate({repr(script)})", result_var

        elif tool in ['playwright_extract_page_fast', 'playwright_find_contacts']:
            return f"# Custom extraction tool: {tool} - implement using page.content() and regex", None

        elif tool == 'playwright_extract_fb_ads':
            return "# Facebook Ads extraction - implement custom scraping logic", None

        elif tool == 'playwright_extract_reddit':
            return "# Reddit extraction - implement custom scraping logic", None

        else:
            return f"# Unsupported tool: {tool}", None

    def _should_retry(self, tool: str) -> bool:
        """Determine if a tool should have retry logic"""
        # Navigation, clicks, and fills should retry
        retry_tools = {
            'playwright_navigate',
            'playwright_click',
            'playwright_fill',
            'playwright_get_text'
        }
        return tool in retry_tools

    def _skill_to_actions(self, skill: Any) -> List[Dict[str, Any]]:
        """Convert a Skill object to actions list"""
        actions = []

        # Extract tool calls from skill's required_tools
        for tool in skill.required_tools:
            # Create a basic action structure
            # In a real implementation, we'd parse the skill's code to get actual arguments
            actions.append({
                'tool': tool,
                'arguments': {}
            })

        return actions

    def save_to_file(self, generated: GeneratedCode, output_path: Path):
        """Save generated code to a file"""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(generated.code)

            # Also save metadata
            metadata_path = output_path.with_suffix('.json')
            metadata = {
                'format': generated.format.value,
                'parameters': generated.parameters,
                'dependencies': generated.dependencies,
                'description': generated.description,
                'generated_at': generated.generated_at
            }
            metadata_path.write_text(json.dumps(metadata, indent=2))

            logger.info(f"Saved generated code to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save code: {e}")
            raise


# Convenience functions

def export_workflow(
    actions: List[Dict[str, Any]],
    output_path: Path,
    format: str = "python_async",
    description: str = "",
    **kwargs
) -> GeneratedCode:
    """
    Export workflow to a file

    Args:
        actions: List of tool calls
        output_path: Where to save the code
        format: Output format (python_async, python_sync, pytest)
        description: Workflow description
        **kwargs: Additional config options

    Returns:
        GeneratedCode object
    """
    generator = PlaywrightCodeGenerator()
    generated = generator.generate_from_trace(
        actions=actions,
        description=description,
        format=format,
        **kwargs
    )
    generator.save_to_file(generated, output_path)
    return generated


def export_skill(
    skill: Any,
    output_path: Path,
    format: str = "python_async",
    **kwargs
) -> GeneratedCode:
    """
    Export skill to a file

    Args:
        skill: Skill object
        output_path: Where to save the code
        format: Output format
        **kwargs: Additional config options

    Returns:
        GeneratedCode object
    """
    generator = PlaywrightCodeGenerator()
    generated = generator.generate_from_skill(
        skill=skill,
        format=format,
        **kwargs
    )
    generator.save_to_file(generated, output_path)
    return generated


# Example usage
if __name__ == "__main__":
    # Example: Generate from trace
    sample_actions = [
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

    generator = PlaywrightCodeGenerator()

    # Generate async Python
    result = generator.generate_from_trace(
        actions=sample_actions,
        description="Search for Python books on books.toscrape.com",
        format="python_async"
    )

    print("=" * 80)
    print("GENERATED ASYNC PYTHON CODE:")
    print("=" * 80)
    print(result.code)
    print()

    # Generate pytest
    result_pytest = generator.generate_from_trace(
        actions=sample_actions,
        description="Search for Python books on books.toscrape.com",
        format="pytest"
    )

    print("=" * 80)
    print("GENERATED PYTEST CODE:")
    print("=" * 80)
    print(result_pytest.code)
    print()

    # Generate TypeScript
    result_typescript = generator.generate_from_trace(
        actions=sample_actions,
        description="Search for Python books on books.toscrape.com",
        format="typescript"
    )

    print("=" * 80)
    print("GENERATED TYPESCRIPT CODE:")
    print("=" * 80)
    print(result_typescript.code)
    print()

    # Generate JavaScript
    result_javascript = generator.generate_from_trace(
        actions=sample_actions,
        description="Search for Python books on books.toscrape.com",
        format="javascript"
    )

    print("=" * 80)
    print("GENERATED JAVASCRIPT CODE:")
    print("=" * 80)
    print(result_javascript.code)
