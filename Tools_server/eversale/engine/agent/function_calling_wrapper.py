#!/usr/bin/env python3
"""
Smart Function Calling Wrapper - Extract and validate tool calls from various formats
Handles: JSON, TOOL:/PARAMS:/END_TOOL, plain text descriptions, and mixed formats
"""

import json
import re
from typing import Dict, List, Optional, Any
from loguru import logger


class FunctionCallWrapper:
    """Intelligent parser for extracting function calls from model outputs"""

    def __init__(self):
        self.valid_functions = [
            # Playwright MCP tools
            "playwright_navigate",
            "playwright_click",
            "playwright_fill",
            "playwright_screenshot",
            "playwright_evaluate",
            "playwright_hover",
            "playwright_select",
            "playwright_type",
            "playwright_press",
            "playwright_wait_for_selector",
            "playwright_get_text",
            "playwright_get_attribute",
            "playwright_scroll",
            "playwright_go_back",
            "playwright_go_forward",
            "playwright_reload",
            "playwright_close",
        ]

    def extract_calls(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract function calls from model output in any format
        Returns list of standardized tool calls
        """
        calls = []

        # Try extraction methods in order of reliability
        # 1. Pure JSON (most reliable)
        json_calls = self._extract_json(text)
        if json_calls:
            calls.extend(json_calls)
            logger.debug(f"Extracted {len(json_calls)} calls via JSON parsing")
            return calls

        # 2. TOOL:/PARAMS: format (legacy)
        tool_calls = self._extract_tool_format(text)
        if tool_calls:
            calls.extend(tool_calls)
            logger.debug(f"Extracted {len(tool_calls)} calls via TOOL format")
            return calls

        # 3. Natural language descriptions (fallback)
        nl_calls = self._extract_natural_language(text)
        if nl_calls:
            calls.extend(nl_calls)
            logger.debug(f"Extracted {len(nl_calls)} calls via NL parsing")
            return calls

        logger.warning(f"No valid function calls found in: {text[:200]}...")
        return calls

    def _extract_json(self, text: str) -> List[Dict[str, Any]]:
        """Extract JSON function calls (most reliable)"""
        calls = []

        # Try to find JSON object or array
        # Handle multiple JSON blocks
        json_pattern = r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}|\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\])'

        matches = re.finditer(json_pattern, text, re.DOTALL)

        for match in matches:
            try:
                parsed = json.loads(match.group())

                # Normalize to list
                if isinstance(parsed, dict):
                    parsed = [parsed]

                for call in parsed:
                    standardized = self._standardize_call(call)
                    if standardized:
                        calls.append(standardized)
            except json.JSONDecodeError:
                continue

        return calls

    def _extract_tool_format(self, text: str) -> List[Dict[str, Any]]:
        """Extract TOOL:/PARAMS:/END_TOOL format"""
        calls = []

        # Pattern: TOOL: function_name\nPARAMS:\n{json}\nEND_TOOL
        pattern = r'TOOL:\s*(\w+)\s*PARAMS:\s*(\{[^}]*\})\s*END_TOOL'

        matches = re.finditer(pattern, text, re.DOTALL | re.IGNORECASE)

        for match in matches:
            function_name = match.group(1).strip()
            params_str = match.group(2).strip()

            try:
                params = json.loads(params_str)
                calls.append({
                    "function": function_name,
                    "arguments": params
                })
            except json.JSONDecodeError:
                logger.warning(f"Invalid params JSON in TOOL format: {params_str}")
                continue

        return calls

    def _extract_natural_language(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract function calls from natural language descriptions
        Last resort - tries to infer intent
        """
        calls = []
        text_lower = text.lower()

        # Navigate patterns
        nav_patterns = [
            (r'(?:navigate|go|visit)\s+(?:to\s+)?(?:https?://)?([^\s,]+)', 'playwright_navigate'),
            (r'open\s+(?:https?://)?([^\s,]+)', 'playwright_navigate'),
        ]

        for pattern, func in nav_patterns:
            match = re.search(pattern, text_lower)
            if match:
                url = match.group(1)
                # Add https if missing
                if not url.startswith('http'):
                    url = f'https://{url}'
                calls.append({
                    "function": func,
                    "arguments": {"url": url}
                })

        # Click patterns
        click_patterns = [
            r'click\s+(?:on\s+)?["\']?([^"\']+)["\']?',
            r'press\s+(?:the\s+)?["\']?([^"\']+)["\']?\s+button',
        ]

        for pattern in click_patterns:
            match = re.search(pattern, text_lower)
            if match:
                selector = match.group(1).strip()
                calls.append({
                    "function": "playwright_click",
                    "arguments": {"selector": selector}
                })
                break

        # Fill patterns
        fill_patterns = [
            r'fill\s+["\']?([^"\']+)["\']?\s+with\s+["\']?([^"\']+)["\']?',
            r'type\s+["\']?([^"\']+)["\']?\s+(?:in|into)\s+["\']?([^"\']+)["\']?',
        ]

        for pattern in fill_patterns:
            match = re.search(pattern, text_lower)
            if match:
                value = match.group(1).strip()
                selector = match.group(2).strip()
                calls.append({
                    "function": "playwright_fill",
                    "arguments": {
                        "selector": selector,
                        "value": value
                    }
                })
                break

        return calls

    def _standardize_call(self, call: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Standardize function call to consistent format
        Handles various naming conventions
        """
        # Extract function name (various keys used by different models)
        func_name = None
        for key in ['function', 'name', 'tool', 'action', 'command']:
            if key in call:
                func_name = call[key]
                break

        if not func_name:
            logger.warning(f"No function name found in call: {call}")
            return None

        # Validate function exists
        if func_name not in self.valid_functions:
            # Try to fix common mistakes
            func_name = self._fix_function_name(func_name)
            if not func_name:
                logger.warning(f"Invalid function name: {call.get('function')}")
                return None

        # Extract arguments
        args = None
        for key in ['arguments', 'args', 'params', 'parameters', 'input']:
            if key in call:
                args = call[key]
                break

        if args is None:
            args = {}

        return {
            "function": func_name,
            "arguments": args
        }

    def _fix_function_name(self, name: str) -> Optional[str]:
        """Fix common function name mistakes"""
        name = name.lower().strip()

        # Remove common prefixes/suffixes
        name = re.sub(r'^(call_|execute_|run_)', '', name)
        name = re.sub(r'(_function|_tool|_action)$', '', name)

        # Add playwright_ prefix if missing
        if not name.startswith('playwright_'):
            test_name = f'playwright_{name}'
            if test_name in self.valid_functions:
                return test_name

        # Direct match
        if name in self.valid_functions:
            return name

        # Fuzzy match (common typos)
        corrections = {
            'navigate': 'playwright_navigate',
            'click': 'playwright_click',
            'fill': 'playwright_fill',
            'type': 'playwright_fill',
            'screenshot': 'playwright_screenshot',
            'eval': 'playwright_evaluate',
            'execute': 'playwright_evaluate',
            'hover': 'playwright_hover',
            'select': 'playwright_select',
            'wait': 'playwright_wait_for_selector',
        }

        return corrections.get(name)

    def validate_arguments(self, function: str, arguments: Dict[str, Any]) -> bool:
        """
        Validate that arguments match function requirements
        Returns True if valid, False otherwise
        """
        required_args = {
            'playwright_navigate': ['url'],
            'playwright_click': ['selector'],
            'playwright_fill': ['selector', 'value'],
            'playwright_screenshot': [],
            'playwright_evaluate': ['script'],
            'playwright_hover': ['selector'],
            'playwright_select': ['selector', 'value'],
            'playwright_type': ['selector', 'text'],
            'playwright_press': ['key'],
            'playwright_wait_for_selector': ['selector'],
            'playwright_get_text': ['selector'],
            'playwright_get_attribute': ['selector', 'attribute'],
            'playwright_scroll': [],
        }

        if function not in required_args:
            logger.warning(f"Unknown function for validation: {function}")
            return False

        required = required_args[function]

        # Check all required arguments present
        for arg in required:
            if arg not in arguments:
                logger.warning(f"Missing required argument '{arg}' for {function}")
                return False

        return True

    def enhance_arguments(self, function: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhance arguments with smart defaults and corrections
        """
        enhanced = arguments.copy()

        # Fix URLs
        if function == 'playwright_navigate' and 'url' in enhanced:
            url = enhanced['url']

            # Add https if missing protocol
            if not url.startswith(('http://', 'https://')):
                enhanced['url'] = f'https://{url}'

            # Remove trailing slash for consistency
            enhanced['url'] = enhanced['url'].rstrip('/')

        # Fix selectors (common mistakes)
        if 'selector' in enhanced:
            selector = enhanced['selector']

            # Remove extra quotes
            selector = selector.strip('"\'')

            # Fix common CSS selector mistakes
            # input[name=search] → input[name="search"]
            selector = re.sub(r'\[(\w+)=([^\]"\s]+)\]', r'[\1="\2"]', selector)

            enhanced['selector'] = selector

        return enhanced


# Singleton instance
function_wrapper = FunctionCallWrapper()


def extract_function_calls(text: str) -> List[Dict[str, Any]]:
    """Convenience function for extracting calls"""
    return function_wrapper.extract_calls(text)


def validate_function_call(function: str, arguments: Dict[str, Any]) -> bool:
    """Convenience function for validation"""
    return function_wrapper.validate_arguments(function, arguments)
