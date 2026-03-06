"""
Browser tool schemas for LLM-based browser automation.

This module defines JSON schemas for browser tools that Qwen models can call reliably,
based on research from Reddit LocalLLaMA community on improving tool calling accuracy.

Key design principles:
1. Strict type definitions with explicit enums
2. Clear, concise descriptions
3. Multiple positive examples per tool
4. Required vs optional parameters clearly marked
5. Validation helpers for runtime checking
"""

from typing import Dict, List, Any, Optional
import json


BROWSER_TOOL_SCHEMAS = {
    "click": {
        "name": "click",
        "description": "Click on an element identified by its ID from the compressed DOM representation.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Element ID from compressed DOM (e.g., e1, e2, e3). This is the numeric ID shown in the DOM snapshot.",
                    "pattern": "^e\\d+$"
                }
            },
            "required": ["id"]
        },
        "examples": [
            {
                "description": "Click on a button",
                "tool_call": {"name": "click", "arguments": {"id": "e5"}}
            },
            {
                "description": "Click on a link",
                "tool_call": {"name": "click", "arguments": {"id": "e12"}}
            },
            {
                "description": "Click on a submit button",
                "tool_call": {"name": "click", "arguments": {"id": "e23"}}
            }
        ]
    },

    "type_text": {
        "name": "type_text",
        "description": "Type text into an input field or textarea element.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Element ID from compressed DOM (e.g., e1, e2, e3)",
                    "pattern": "^e\\d+$"
                },
                "text": {
                    "type": "string",
                    "description": "The text to type into the element"
                },
                "clear_first": {
                    "type": "boolean",
                    "description": "Whether to clear existing text before typing",
                    "default": True
                }
            },
            "required": ["id", "text"]
        },
        "examples": [
            {
                "description": "Type into a search box",
                "tool_call": {"name": "type_text", "arguments": {"id": "e3", "text": "machine learning", "clear_first": True}}
            },
            {
                "description": "Type into an email field without clearing",
                "tool_call": {"name": "type_text", "arguments": {"id": "e7", "text": "user@example.com", "clear_first": False}}
            },
            {
                "description": "Type into a textarea",
                "tool_call": {"name": "type_text", "arguments": {"id": "e15", "text": "This is a comment"}}
            }
        ]
    },

    "scroll": {
        "name": "scroll",
        "description": "Scroll the page in a specified direction by a certain amount.",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["up", "down", "left", "right"],
                    "description": "Direction to scroll"
                },
                "amount": {
                    "type": "integer",
                    "description": "Number of pixels to scroll (default: 500)",
                    "default": 500,
                    "minimum": 0
                }
            },
            "required": ["direction"]
        },
        "examples": [
            {
                "description": "Scroll down to see more content",
                "tool_call": {"name": "scroll", "arguments": {"direction": "down", "amount": 500}}
            },
            {
                "description": "Scroll up to top",
                "tool_call": {"name": "scroll", "arguments": {"direction": "up", "amount": 1000}}
            },
            {
                "description": "Scroll right in a horizontal carousel",
                "tool_call": {"name": "scroll", "arguments": {"direction": "right", "amount": 300}}
            }
        ]
    },

    "scroll_to_element": {
        "name": "scroll_to_element",
        "description": "Scroll the page to bring a specific element into view.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Element ID from compressed DOM (e.g., e1, e2, e3)",
                    "pattern": "^e\\d+$"
                }
            },
            "required": ["id"]
        },
        "examples": [
            {
                "description": "Scroll to a section header",
                "tool_call": {"name": "scroll_to_element", "arguments": {"id": "e18"}}
            },
            {
                "description": "Scroll to a footer element",
                "tool_call": {"name": "scroll_to_element", "arguments": {"id": "e45"}}
            },
            {
                "description": "Scroll to bring button into view",
                "tool_call": {"name": "scroll_to_element", "arguments": {"id": "e9"}}
            }
        ]
    },

    "navigate": {
        "name": "navigate",
        "description": "Navigate to a specified URL in the current tab.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to navigate to (must include protocol: http:// or https://)",
                    "pattern": "^https?://.+"
                }
            },
            "required": ["url"]
        },
        "examples": [
            {
                "description": "Navigate to a website",
                "tool_call": {"name": "navigate", "arguments": {"url": "https://www.example.com"}}
            },
            {
                "description": "Navigate to a specific page",
                "tool_call": {"name": "navigate", "arguments": {"url": "https://github.com/anthropics/anthropic-sdk-python"}}
            },
            {
                "description": "Navigate to search results",
                "tool_call": {"name": "navigate", "arguments": {"url": "https://www.google.com/search?q=python+tutorial"}}
            }
        ]
    },

    "go_back": {
        "name": "go_back",
        "description": "Navigate back to the previous page in browser history.",
        "parameters": {
            "type": "object",
            "properties": {}
        },
        "examples": [
            {
                "description": "Go back to previous page",
                "tool_call": {"name": "go_back", "arguments": {}}
            },
            {
                "description": "Return to search results",
                "tool_call": {"name": "go_back", "arguments": {}}
            }
        ]
    },

    "go_forward": {
        "name": "go_forward",
        "description": "Navigate forward to the next page in browser history.",
        "parameters": {
            "type": "object",
            "properties": {}
        },
        "examples": [
            {
                "description": "Go forward in history",
                "tool_call": {"name": "go_forward", "arguments": {}}
            },
            {
                "description": "Redo navigation",
                "tool_call": {"name": "go_forward", "arguments": {}}
            }
        ]
    },

    "refresh": {
        "name": "refresh",
        "description": "Refresh the current page to reload its content.",
        "parameters": {
            "type": "object",
            "properties": {}
        },
        "examples": [
            {
                "description": "Reload the page",
                "tool_call": {"name": "refresh", "arguments": {}}
            },
            {
                "description": "Refresh to see updated content",
                "tool_call": {"name": "refresh", "arguments": {}}
            }
        ]
    },

    "extract_text": {
        "name": "extract_text",
        "description": "Extract text content from one or more elements.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Element ID from compressed DOM (e.g., e1, e2, e3). If multiple is true, this can match multiple elements.",
                    "pattern": "^e\\d+$"
                },
                "multiple": {
                    "type": "boolean",
                    "description": "Whether to extract text from multiple matching elements",
                    "default": False
                }
            },
            "required": ["id"]
        },
        "examples": [
            {
                "description": "Extract text from a heading",
                "tool_call": {"name": "extract_text", "arguments": {"id": "e4", "multiple": False}}
            },
            {
                "description": "Extract text from all list items",
                "tool_call": {"name": "extract_text", "arguments": {"id": "e10", "multiple": True}}
            },
            {
                "description": "Extract paragraph text",
                "tool_call": {"name": "extract_text", "arguments": {"id": "e22"}}
            }
        ]
    },

    "extract_links": {
        "name": "extract_links",
        "description": "Extract href attributes from link elements.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Element ID from compressed DOM (e.g., e1, e2, e3). Extracts links from this element and its children.",
                    "pattern": "^e\\d+$"
                }
            },
            "required": ["id"]
        },
        "examples": [
            {
                "description": "Extract all links from navigation",
                "tool_call": {"name": "extract_links", "arguments": {"id": "e2"}}
            },
            {
                "description": "Extract links from a section",
                "tool_call": {"name": "extract_links", "arguments": {"id": "e15"}}
            },
            {
                "description": "Extract footer links",
                "tool_call": {"name": "extract_links", "arguments": {"id": "e50"}}
            }
        ]
    },

    "wait_for": {
        "name": "wait_for",
        "description": "Wait for an element to reach a specific state before continuing.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Element ID from compressed DOM (e.g., e1, e2, e3)",
                    "pattern": "^e\\d+$"
                },
                "state": {
                    "type": "string",
                    "enum": ["visible", "hidden", "attached"],
                    "description": "The state to wait for: visible (element is visible), hidden (element is hidden), attached (element exists in DOM)",
                    "default": "visible"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Maximum time to wait in milliseconds",
                    "default": 30000,
                    "minimum": 0,
                    "maximum": 60000
                }
            },
            "required": ["id"]
        },
        "examples": [
            {
                "description": "Wait for loading spinner to disappear",
                "tool_call": {"name": "wait_for", "arguments": {"id": "e8", "state": "hidden", "timeout": 5000}}
            },
            {
                "description": "Wait for modal to appear",
                "tool_call": {"name": "wait_for", "arguments": {"id": "e12", "state": "visible", "timeout": 3000}}
            },
            {
                "description": "Wait for element to be attached to DOM",
                "tool_call": {"name": "wait_for", "arguments": {"id": "e20", "state": "attached"}}
            }
        ]
    },

    "screenshot": {
        "name": "screenshot",
        "description": "Take a screenshot of the current page or viewport.",
        "parameters": {
            "type": "object",
            "properties": {
                "full_page": {
                    "type": "boolean",
                    "description": "Whether to capture the entire page (true) or just the current viewport (false)",
                    "default": False
                }
            }
        },
        "examples": [
            {
                "description": "Take viewport screenshot",
                "tool_call": {"name": "screenshot", "arguments": {"full_page": False}}
            },
            {
                "description": "Capture entire page",
                "tool_call": {"name": "screenshot", "arguments": {"full_page": True}}
            },
            {
                "description": "Screenshot visible area",
                "tool_call": {"name": "screenshot", "arguments": {}}
            }
        ]
    },

    "get_page_info": {
        "name": "get_page_info",
        "description": "Get information about the current page including URL and title.",
        "parameters": {
            "type": "object",
            "properties": {}
        },
        "examples": [
            {
                "description": "Get current page details",
                "tool_call": {"name": "get_page_info", "arguments": {}}
            },
            {
                "description": "Check page URL and title",
                "tool_call": {"name": "get_page_info", "arguments": {}}
            }
        ]
    },

    "manage_tabs": {
        "name": "manage_tabs",
        "description": "Manage browser tabs: create new tabs, close tabs, or switch between tabs.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["new", "close", "switch"],
                    "description": "Action to perform: new (create new tab), close (close current/specified tab), switch (switch to specified tab)"
                },
                "tab_id": {
                    "type": "string",
                    "description": "Tab identifier (required for 'close' and 'switch' actions, optional for 'new')"
                }
            },
            "required": ["action"]
        },
        "examples": [
            {
                "description": "Open a new tab",
                "tool_call": {"name": "manage_tabs", "arguments": {"action": "new"}}
            },
            {
                "description": "Switch to a specific tab",
                "tool_call": {"name": "manage_tabs", "arguments": {"action": "switch", "tab_id": "tab-123"}}
            },
            {
                "description": "Close current tab",
                "tool_call": {"name": "manage_tabs", "arguments": {"action": "close"}}
            }
        ]
    }
}


def build_tools_prompt(available_tools: List[str]) -> str:
    """
    Build tools section for executor prompt.

    Args:
        available_tools: List of tool names that are available to the agent

    Returns:
        Formatted string containing tool definitions with examples
    """
    if not available_tools:
        return "No tools available."

    tool_sections = []

    for tool_name in available_tools:
        if tool_name not in BROWSER_TOOL_SCHEMAS:
            continue

        schema = BROWSER_TOOL_SCHEMAS[tool_name]

        # Build tool definition
        section = f"## {schema['name']}\n\n"
        section += f"{schema['description']}\n\n"
        section += "**Parameters:**\n"
        section += f"```json\n{json.dumps(schema['parameters'], indent=2)}\n```\n\n"

        # Add examples
        section += "**Examples:**\n"
        for i, example in enumerate(schema['examples'], 1):
            section += f"{i}. {example.get('description', 'Example ' + str(i))}\n"
            section += f"```json\n{json.dumps(example['tool_call'], indent=2)}\n```\n"

        tool_sections.append(section)

    header = f"# Available Tools ({len(tool_sections)})\n\n"
    header += "You have access to the following browser automation tools. "
    header += "Use them to interact with web pages and accomplish tasks.\n\n"

    return header + "\n\n".join(tool_sections)


def validate_tool_call(tool_name: str, arguments: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate a tool call against its schema.

    Args:
        tool_name: Name of the tool being called
        arguments: Dictionary of arguments passed to the tool

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if the tool call is valid, False otherwise
        - error_message: None if valid, error description if invalid
    """
    if tool_name not in BROWSER_TOOL_SCHEMAS:
        return False, f"Unknown tool: {tool_name}"

    schema = BROWSER_TOOL_SCHEMAS[tool_name]
    params_schema = schema['parameters']
    properties = params_schema.get('properties', {})
    required = params_schema.get('required', [])

    # Check required parameters
    for param in required:
        if param not in arguments:
            return False, f"Missing required parameter: {param}"

    # Validate each argument
    for arg_name, arg_value in arguments.items():
        if arg_name not in properties:
            return False, f"Unknown parameter: {arg_name}"

        prop_schema = properties[arg_name]
        expected_type = prop_schema.get('type')

        # Type validation
        type_map = {
            'string': str,
            'integer': int,
            'boolean': bool,
            'number': (int, float)
        }

        if expected_type in type_map:
            expected_python_type = type_map[expected_type]
            if not isinstance(arg_value, expected_python_type):
                return False, f"Parameter '{arg_name}' must be of type {expected_type}, got {type(arg_value).__name__}"

        # Enum validation
        if 'enum' in prop_schema:
            if arg_value not in prop_schema['enum']:
                return False, f"Parameter '{arg_name}' must be one of {prop_schema['enum']}, got '{arg_value}'"

        # Pattern validation for strings
        if expected_type == 'string' and 'pattern' in prop_schema:
            import re
            pattern = prop_schema['pattern']
            if not re.match(pattern, arg_value):
                return False, f"Parameter '{arg_name}' does not match required pattern: {pattern}"

        # Range validation for numbers
        if expected_type in ['integer', 'number']:
            if 'minimum' in prop_schema and arg_value < prop_schema['minimum']:
                return False, f"Parameter '{arg_name}' must be >= {prop_schema['minimum']}"
            if 'maximum' in prop_schema and arg_value > prop_schema['maximum']:
                return False, f"Parameter '{arg_name}' must be <= {prop_schema['maximum']}"

    return True, None


def get_tool_schema(tool_name: str) -> Optional[Dict[str, Any]]:
    """
    Get the schema for a specific tool.

    Args:
        tool_name: Name of the tool

    Returns:
        Tool schema dictionary or None if tool not found
    """
    return BROWSER_TOOL_SCHEMAS.get(tool_name)


def get_all_tool_names() -> List[str]:
    """
    Get list of all available tool names.

    Returns:
        List of tool name strings
    """
    return list(BROWSER_TOOL_SCHEMAS.keys())


def format_tool_for_openai(tool_name: str) -> Optional[Dict[str, Any]]:
    """
    Format a tool schema for OpenAI's function calling API.

    Args:
        tool_name: Name of the tool to format

    Returns:
        Tool schema in OpenAI format or None if tool not found
    """
    if tool_name not in BROWSER_TOOL_SCHEMAS:
        return None

    schema = BROWSER_TOOL_SCHEMAS[tool_name]

    return {
        "type": "function",
        "function": {
            "name": schema["name"],
            "description": schema["description"],
            "parameters": schema["parameters"]
        }
    }


def format_all_tools_for_openai() -> List[Dict[str, Any]]:
    """
    Format all tool schemas for OpenAI's function calling API.

    Returns:
        List of tool schemas in OpenAI format
    """
    return [
        format_tool_for_openai(tool_name)
        for tool_name in BROWSER_TOOL_SCHEMAS.keys()
    ]
