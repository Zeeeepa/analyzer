"""
Tool Registry - Centralized tool definition and management system

Based on OpenCode's tool/registry.ts pattern, this module provides:
- ToolDefinition dataclass for type-safe tool definitions
- ToolRegistry class for managing all available tools
- Built-in tool registration for playwright, file ops, bash, search
- Dynamic discovery of custom tools from tool/*.py
- Access control based on agent mode permissions
- Plugin integration support

Architecture:
    ToolRegistry
        |
        +-- Built-in tools (playwright_*, browser_*, read_file, etc.)
        +-- Custom tools (discovered from tool/*.py)
        +-- Plugin tools (from plugin definitions)
        +-- Access control (agent mode based)
        +-- Hot reload (watch tool/*.py for changes)
"""

import importlib
import inspect
import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Set
from loguru import logger

# Agent mode imports are delayed to avoid circular dependencies
# They will be imported in methods that need them
AgentMode = None
get_agent_mode = None
AGENT_MODES = None

def _import_agent_mode():
    """Lazy import of agent mode configuration."""
    global AgentMode, get_agent_mode, AGENT_MODES
    if AgentMode is None:
        try:
            from .brain_config import AgentMode as AM, get_agent_mode as GAM, AGENT_MODES as MODES
            AgentMode = AM
            get_agent_mode = GAM
            AGENT_MODES = MODES
        except ImportError:
            try:
                from brain_config import AgentMode as AM, get_agent_mode as GAM, AGENT_MODES as MODES
                AgentMode = AM
                get_agent_mode = GAM
                AGENT_MODES = MODES
            except ImportError:
                logger.warning("Could not import brain_config - agent mode filtering disabled")
                # Create dummy classes for testing
                from dataclasses import dataclass
                from typing import Dict, Any

                @dataclass
                class DummyAgentMode:
                    name: str = "build"
                    tool_permissions: Dict[str, Any] = None

                    def __post_init__(self):
                        if self.tool_permissions is None:
                            self.tool_permissions = {'write': True, 'edit': True, 'bash': 'allow', 'browser': True}

                AgentMode = DummyAgentMode
                get_agent_mode = lambda name='build': DummyAgentMode(name=name)
                AGENT_MODES = {'build': DummyAgentMode()}

    return AgentMode, get_agent_mode, AGENT_MODES


# ============================================================================
# Tool Definition
# ============================================================================

@dataclass
class ToolDefinition:
    """
    Defines a single tool with all metadata and execution function.

    Attributes:
        id: Unique tool identifier (e.g., 'playwright_navigate')
        name: Display name (e.g., 'Navigate Browser')
        description: Human-readable description of what the tool does
        parameters: JSON Schema defining tool parameters
        execute: Callable that executes the tool (async or sync)
        permissions: List of required permissions (e.g., ['browser', 'edit', 'bash'])
        enabled: Whether the tool is currently enabled
        category: Tool category (e.g., 'browser', 'file', 'search', 'bash')
        aliases: Alternative names for this tool
        metadata: Additional metadata (cost, timeout, etc.)
    """
    id: str
    name: str
    description: str
    parameters: Dict[str, Any]
    execute: Callable
    permissions: List[str] = field(default_factory=list)
    enabled: bool = True
    category: str = "general"
    aliases: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization (excluding execute function)."""
        data = asdict(self)
        data.pop('execute', None)  # Can't serialize functions
        return data

    def to_openai_format(self) -> Dict[str, Any]:
        """
        Convert to OpenAI function calling format.

        Returns:
            Dict in OpenAI function format:
            {
                "type": "function",
                "function": {
                    "name": "tool_id",
                    "description": "...",
                    "parameters": {...}
                }
            }
        """
        return {
            "type": "function",
            "function": {
                "name": self.id,
                "description": self.description,
                "parameters": self.parameters
            }
        }

    def to_anthropic_format(self) -> Dict[str, Any]:
        """
        Convert to Anthropic tool format.

        Returns:
            Dict in Anthropic tool format:
            {
                "name": "tool_id",
                "description": "...",
                "input_schema": {...}
            }
        """
        return {
            "name": self.id,
            "description": self.description,
            "input_schema": self.parameters
        }

    def to_mcp_format(self) -> Dict[str, Any]:
        """
        Convert to MCP tool format.

        Returns:
            Dict in MCP tool format:
            {
                "name": "tool_id",
                "description": "...",
                "inputSchema": {...}
            }
        """
        return {
            "name": self.id,
            "description": self.description,
            "inputSchema": self.parameters
        }

    def check_permissions(self, agent_mode) -> bool:
        """
        Check if tool is allowed in given agent mode.

        Args:
            agent_mode: AgentMode instance to check against

        Returns:
            True if all required permissions are satisfied
        """
        # No permissions required = always allowed
        if not self.permissions:
            return True

        # Check each required permission
        for perm in self.permissions:
            perm_lower = perm.lower()

            # Check permission type
            if perm_lower == 'write':
                if not agent_mode.tool_permissions.get('write', True):
                    return False
            elif perm_lower == 'edit':
                if not agent_mode.tool_permissions.get('edit', True):
                    return False
            elif perm_lower == 'bash':
                bash_perm = agent_mode.tool_permissions.get('bash', 'allow')
                if bash_perm == 'deny':
                    return False
            elif perm_lower == 'browser':
                if not agent_mode.tool_permissions.get('browser', True):
                    return False
            # Add more permission types as needed

        return True

    def requires_user_permission(self, agent_mode) -> bool:
        """
        Check if tool requires user permission before execution.

        Args:
            agent_mode: AgentMode instance to check against

        Returns:
            True if tool requires user permission
        """
        for perm in self.permissions:
            if perm.lower() == 'bash':
                if agent_mode.tool_permissions.get('bash') == 'ask':
                    return True
        return False


# ============================================================================
# Tool Registry
# ============================================================================

class ToolRegistry:
    """
    Central registry for all available tools.

    Features:
    - Register/unregister tools
    - List tools by agent mode, category, etc.
    - Discover custom tools from tool/*.py
    - Hot reload on file changes
    - Access control based on agent mode
    - Plugin integration

    Usage:
        registry = ToolRegistry()
        await registry.initialize()

        # Register a tool
        registry.register(ToolDefinition(...))

        # Get tool by ID
        tool = registry.get('playwright_navigate')

        # List enabled tools for agent mode
        tools = registry.list_enabled('build')
    """

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._aliases: Dict[str, str] = {}  # alias -> canonical tool id
        self._categories: Dict[str, Set[str]] = {}  # category -> set of tool ids
        self._custom_tool_path = Path(__file__).parent / "tool"
        self._initialized = False

    async def initialize(self):
        """
        Initialize the tool registry.

        Steps:
        1. Register built-in tools
        2. Discover and register custom tools from tool/*.py
        3. Set up file watchers for hot reload (optional)
        """
        if self._initialized:
            logger.warning("Tool registry already initialized")
            return

        logger.info("Initializing tool registry...")

        # Register built-in tools
        self._register_builtin_tools()

        # Discover custom tools
        await self.discover_custom()

        self._initialized = True
        logger.info(f"Tool registry initialized with {len(self._tools)} tools")

    def register(self, tool: ToolDefinition) -> bool:
        """
        Register a tool in the registry.

        Args:
            tool: ToolDefinition to register

        Returns:
            True if registered successfully, False if ID already exists
        """
        if tool.id in self._tools:
            logger.warning(f"Tool '{tool.id}' already registered, skipping")
            return False

        # Register main tool
        self._tools[tool.id] = tool

        # Register aliases
        for alias in tool.aliases:
            self._aliases[alias] = tool.id

        # Add to category index
        if tool.category not in self._categories:
            self._categories[tool.category] = set()
        self._categories[tool.category].add(tool.id)

        logger.debug(f"Registered tool: {tool.id} (category: {tool.category})")
        return True

    def unregister(self, tool_id: str) -> bool:
        """
        Unregister a tool from the registry.

        Args:
            tool_id: ID of the tool to unregister

        Returns:
            True if unregistered successfully, False if not found
        """
        if tool_id not in self._tools:
            logger.warning(f"Tool '{tool_id}' not found in registry")
            return False

        tool = self._tools[tool_id]

        # Remove from main registry
        del self._tools[tool_id]

        # Remove aliases
        for alias in tool.aliases:
            self._aliases.pop(alias, None)

        # Remove from category index
        if tool.category in self._categories:
            self._categories[tool.category].discard(tool_id)

        logger.debug(f"Unregistered tool: {tool_id}")
        return True

    def get(self, tool_id: str) -> Optional[ToolDefinition]:
        """
        Get a tool by ID or alias.

        Args:
            tool_id: Tool ID or alias

        Returns:
            ToolDefinition if found, None otherwise
        """
        # Try direct ID lookup
        if tool_id in self._tools:
            return self._tools[tool_id]

        # Try alias lookup
        canonical_id = self._aliases.get(tool_id)
        if canonical_id:
            return self._tools.get(canonical_id)

        return None

    def list_all(self) -> List[ToolDefinition]:
        """
        List all registered tools.

        Returns:
            List of all ToolDefinition objects
        """
        return list(self._tools.values())

    def list_enabled(self, agent_mode: str = None) -> List[ToolDefinition]:
        """
        List all enabled tools for a given agent mode.

        Args:
            agent_mode: Agent mode name ('build', 'plan', etc.).
                        If None, returns all enabled tools.

        Returns:
            List of enabled ToolDefinition objects
        """
        enabled_tools = [t for t in self._tools.values() if t.enabled]

        # Filter by agent mode if specified
        if agent_mode:
            _, get_mode_func, _ = _import_agent_mode()
            mode = get_mode_func(agent_mode)
            enabled_tools = [t for t in enabled_tools if t.check_permissions(mode)]

        return enabled_tools

    def list_by_category(self, category: str) -> List[ToolDefinition]:
        """
        List all tools in a specific category.

        Args:
            category: Category name (e.g., 'browser', 'file', 'bash')

        Returns:
            List of ToolDefinition objects in the category
        """
        tool_ids = self._categories.get(category, set())
        return [self._tools[tid] for tid in tool_ids if tid in self._tools]

    def get_categories(self) -> List[str]:
        """
        Get all available tool categories.

        Returns:
            List of category names
        """
        return list(self._categories.keys())

    async def discover_custom(self) -> int:
        """
        Discover and register custom tools from tool/*.py.

        Scans the tool directory for Python files and imports any
        functions decorated with @tool or ToolDefinition objects.

        Returns:
            Number of custom tools discovered
        """
        if not self._custom_tool_path.exists():
            logger.debug(f"Custom tool directory not found: {self._custom_tool_path}")
            return 0

        discovered = 0

        # Scan all .py files in tool directory
        for tool_file in self._custom_tool_path.glob("*.py"):
            if tool_file.name.startswith("_"):
                continue  # Skip private modules

            try:
                # Import the module
                module_name = f"tool.{tool_file.stem}"
                spec = importlib.util.spec_from_file_location(module_name, tool_file)
                if not spec or not spec.loader:
                    continue

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Look for ToolDefinition objects or decorated functions
                for name, obj in inspect.getmembers(module):
                    if isinstance(obj, ToolDefinition):
                        if self.register(obj):
                            discovered += 1
                    elif hasattr(obj, '__tool_definition__'):
                        # Function decorated with @tool
                        tool_def = obj.__tool_definition__
                        if self.register(tool_def):
                            discovered += 1

                logger.debug(f"Scanned custom tool file: {tool_file.name}")

            except Exception as e:
                logger.warning(f"Failed to import custom tool {tool_file.name}: {e}")

        if discovered > 0:
            logger.info(f"Discovered {discovered} custom tools")

        return discovered

    def from_plugin(self, plugin_def: Dict[str, Any]) -> Optional[ToolDefinition]:
        """
        Create a ToolDefinition from a plugin definition.

        Plugin definition format:
        {
            "id": "plugin_tool_name",
            "name": "Display Name",
            "description": "Tool description",
            "parameters": {...},  # JSON Schema
            "execute": <callable>,
            "permissions": ["browser", "edit"],
            "category": "plugin"
        }

        Args:
            plugin_def: Plugin tool definition dictionary

        Returns:
            ToolDefinition if valid, None otherwise
        """
        try:
            tool = ToolDefinition(
                id=plugin_def['id'],
                name=plugin_def.get('name', plugin_def['id']),
                description=plugin_def.get('description', ''),
                parameters=plugin_def.get('parameters', {}),
                execute=plugin_def['execute'],
                permissions=plugin_def.get('permissions', []),
                enabled=plugin_def.get('enabled', True),
                category=plugin_def.get('category', 'plugin'),
                aliases=plugin_def.get('aliases', []),
                metadata=plugin_def.get('metadata', {})
            )

            if self.register(tool):
                logger.info(f"Registered plugin tool: {tool.id}")
                return tool

            return None

        except (KeyError, TypeError) as e:
            logger.error(f"Invalid plugin definition: {e}")
            return None

    def to_openai_format(self, agent_mode: str = None) -> List[Dict[str, Any]]:
        """
        Export all enabled tools in OpenAI function calling format.

        Args:
            agent_mode: Agent mode name to filter tools (optional)

        Returns:
            List of tools in OpenAI format
        """
        tools = self.list_enabled(agent_mode)
        return [t.to_openai_format() for t in tools]

    def to_anthropic_format(self, agent_mode: str = None) -> List[Dict[str, Any]]:
        """
        Export all enabled tools in Anthropic tool format.

        Args:
            agent_mode: Agent mode name to filter tools (optional)

        Returns:
            List of tools in Anthropic format
        """
        tools = self.list_enabled(agent_mode)
        return [t.to_anthropic_format() for t in tools]

    def to_mcp_format(self, agent_mode: str = None) -> List[Dict[str, Any]]:
        """
        Export all enabled tools in MCP format.

        Args:
            agent_mode: Agent mode name to filter tools (optional)

        Returns:
            List of tools in MCP format
        """
        tools = self.list_enabled(agent_mode)
        return [t.to_mcp_format() for t in tools]

    def get_stats(self) -> Dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Dictionary with registry stats
        """
        total = len(self._tools)
        enabled = len([t for t in self._tools.values() if t.enabled])
        categories = {cat: len(tools) for cat, tools in self._categories.items()}

        return {
            'total_tools': total,
            'enabled_tools': enabled,
            'disabled_tools': total - enabled,
            'categories': categories,
            'aliases': len(self._aliases)
        }

    # ========================================================================
    # Built-in Tool Registration
    # ========================================================================

    def _register_builtin_tools(self):
        """Register all built-in tools."""
        self._register_playwright_tools()
        self._register_browser_tools()
        self._register_file_tools()
        self._register_bash_tools()
        self._register_search_tools()
        self._register_memory_tools()

        logger.info(f"Registered {len(self._tools)} built-in tools")

    def _register_playwright_tools(self):
        """Register Playwright browser automation tools."""

        # playwright_navigate
        self.register(ToolDefinition(
            id="playwright_navigate",
            name="Navigate Browser",
            description="Navigate the browser to a URL",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to navigate to"
                    }
                },
                "required": ["url"]
            },
            execute=lambda url: None,  # Placeholder - real execution via MCP
            permissions=["browser"],
            category="browser",
            aliases=["navigate", "goto", "go_to", "visit", "browse"],
            metadata={"timeout": 30000, "cost": 1.0}
        ))

        # playwright_click
        self.register(ToolDefinition(
            id="playwright_click",
            name="Click Element",
            description="Click an element on the page using CSS selector",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the element to click"
                    }
                },
                "required": ["selector"]
            },
            execute=lambda selector: None,
            permissions=["browser"],
            category="browser",
            aliases=["click"],
            metadata={"timeout": 10000, "cost": 0.5}
        ))

        # playwright_fill
        self.register(ToolDefinition(
            id="playwright_fill",
            name="Fill Input",
            description="Fill a form input field with text",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the input field"
                    },
                    "value": {
                        "type": "string",
                        "description": "Text to fill into the field"
                    }
                },
                "required": ["selector", "value"]
            },
            execute=lambda selector, value: None,
            permissions=["browser"],
            category="browser",
            aliases=["fill", "type", "input"],
            metadata={"timeout": 5000, "cost": 0.5}
        ))

        # playwright_screenshot
        self.register(ToolDefinition(
            id="playwright_screenshot",
            name="Take Screenshot",
            description="Take a screenshot of the current page",
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Optional filename for the screenshot"
                    }
                }
            },
            execute=lambda name=None: None,
            permissions=["browser"],
            category="browser",
            aliases=["screenshot", "capture"],
            metadata={"timeout": 5000, "cost": 0.2}
        ))

        # playwright_snapshot
        self.register(ToolDefinition(
            id="playwright_snapshot",
            name="Get Page Snapshot",
            description="Get accessibility snapshot and page structure",
            parameters={
                "type": "object",
                "properties": {}
            },
            execute=lambda: None,
            permissions=["browser"],
            category="browser",
            aliases=["snapshot", "get_page"],
            metadata={"timeout": 10000, "cost": 1.0}
        ))

        # playwright_get_markdown
        self.register(ToolDefinition(
            id="playwright_get_markdown",
            name="Get Page as Markdown",
            description="Get page content converted to markdown format",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Optional URL to navigate to first"
                    }
                }
            },
            execute=lambda url=None: None,
            permissions=["browser"],
            category="browser",
            aliases=["read_page", "get_content"],
            metadata={"timeout": 15000, "cost": 1.5}
        ))

        # playwright_find_contacts
        self.register(ToolDefinition(
            id="playwright_find_contacts",
            name="Find Contacts",
            description="Extract emails, phone numbers, and contact info from current page",
            parameters={
                "type": "object",
                "properties": {}
            },
            execute=lambda: None,
            permissions=["browser"],
            category="browser",
            aliases=["find_contacts", "extract_contacts"],
            metadata={"timeout": 10000, "cost": 1.0}
        ))

    def _register_browser_tools(self):
        """Register browser_* tools (Claude Code style)."""

        # browser_snapshot (mmid-based)
        self.register(ToolDefinition(
            id="browser_snapshot",
            name="Browser Snapshot (MMID)",
            description="Get page snapshot with mmid element references for reliable clicking",
            parameters={
                "type": "object",
                "properties": {}
            },
            execute=lambda: None,
            permissions=["browser"],
            category="browser",
            aliases=[],
            metadata={"timeout": 10000, "cost": 1.0, "style": "claude_code"}
        ))

        # browser_click (mmid-based)
        self.register(ToolDefinition(
            id="browser_click",
            name="Browser Click (MMID)",
            description="Click element by mmid reference (e.g., 'mm5')",
            parameters={
                "type": "object",
                "properties": {
                    "mmid": {
                        "type": "string",
                        "description": "MMID element reference (e.g., 'mm5')"
                    }
                },
                "required": ["mmid"]
            },
            execute=lambda mmid: None,
            permissions=["browser"],
            category="browser",
            aliases=[],
            metadata={"timeout": 5000, "cost": 0.5, "style": "claude_code"}
        ))

        # browser_type (mmid-based)
        self.register(ToolDefinition(
            id="browser_type",
            name="Browser Type (MMID)",
            description="Type text into element by mmid reference",
            parameters={
                "type": "object",
                "properties": {
                    "mmid": {
                        "type": "string",
                        "description": "MMID element reference"
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to type"
                    },
                    "clear": {
                        "type": "boolean",
                        "description": "Clear existing text first (default: true)"
                    }
                },
                "required": ["mmid", "text"]
            },
            execute=lambda mmid, text, clear=True: None,
            permissions=["browser"],
            category="browser",
            aliases=[],
            metadata={"timeout": 5000, "cost": 0.5, "style": "claude_code"}
        ))

        # browser_navigate
        self.register(ToolDefinition(
            id="browser_navigate",
            name="Browser Navigate",
            description="Navigate to URL (Claude Code style)",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to navigate to"
                    }
                },
                "required": ["url"]
            },
            execute=lambda url: None,
            permissions=["browser"],
            category="browser",
            aliases=[],
            metadata={"timeout": 30000, "cost": 1.0, "style": "claude_code"}
        ))

    def _register_file_tools(self):
        """Register file operation tools."""

        # read_file
        self.register(ToolDefinition(
            id="read_file",
            name="Read File",
            description="Read content from a file",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read"
                    }
                },
                "required": ["path"]
            },
            execute=lambda path: None,
            permissions=[],  # Read doesn't require special permissions
            category="file",
            aliases=[],
            metadata={"timeout": 5000, "cost": 0.1}
        ))

        # write_file
        self.register(ToolDefinition(
            id="write_file",
            name="Write File",
            description="Write content to a file",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to write"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    },
                    "append": {
                        "type": "boolean",
                        "description": "Append to file instead of overwriting (default: false)"
                    }
                },
                "required": ["path", "content"]
            },
            execute=lambda path, content, append=False: None,
            permissions=["write"],
            category="file",
            aliases=["save_file", "create_file"],
            metadata={"timeout": 5000, "cost": 0.2}
        ))

        # edit_file
        self.register(ToolDefinition(
            id="edit_file",
            name="Edit File",
            description="Edit a file by replacing old string with new string",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to edit"
                    },
                    "old_string": {
                        "type": "string",
                        "description": "String to replace"
                    },
                    "new_string": {
                        "type": "string",
                        "description": "Replacement string"
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace all occurrences (default: false)"
                    }
                },
                "required": ["path", "old_string", "new_string"]
            },
            execute=lambda path, old_string, new_string, replace_all=False: None,
            permissions=["edit"],
            category="file",
            aliases=[],
            metadata={"timeout": 5000, "cost": 0.3}
        ))

    def _register_bash_tools(self):
        """Register bash command execution tools."""

        # bash
        self.register(ToolDefinition(
            id="bash",
            name="Execute Bash Command",
            description="Execute a bash command in the shell",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Bash command to execute"
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Timeout in seconds (default: 30)"
                    }
                },
                "required": ["command"]
            },
            execute=lambda command, timeout=30: None,
            permissions=["bash"],
            category="bash",
            aliases=[],
            metadata={"timeout": 30000, "cost": 1.0}
        ))

    def _register_search_tools(self):
        """Register search tools (grep, glob)."""

        # grep
        self.register(ToolDefinition(
            id="grep",
            name="Search Files",
            description="Search for a pattern in files using grep/ripgrep",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regular expression pattern to search for"
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory or file to search in (default: current directory)"
                    },
                    "case_insensitive": {
                        "type": "boolean",
                        "description": "Case-insensitive search (default: false)"
                    }
                },
                "required": ["pattern"]
            },
            execute=lambda pattern, path=None, case_insensitive=False: None,
            permissions=[],  # Read-only operation
            category="search",
            aliases=[],
            metadata={"timeout": 10000, "cost": 0.5}
        ))

        # glob
        self.register(ToolDefinition(
            id="glob",
            name="Find Files by Pattern",
            description="Find files matching a glob pattern",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g., '**/*.py')"
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in (default: current directory)"
                    }
                },
                "required": ["pattern"]
            },
            execute=lambda pattern, path=None: None,
            permissions=[],  # Read-only operation
            category="search",
            aliases=[],
            metadata={"timeout": 5000, "cost": 0.3}
        ))

    def _register_memory_tools(self):
        """Register memory/contact management tools."""

        # save_contact
        self.register(ToolDefinition(
            id="save_contact",
            name="Save Contact",
            description="Save a contact to memory/database",
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Contact name"
                    },
                    "email": {
                        "type": "string",
                        "description": "Email address"
                    },
                    "company": {
                        "type": "string",
                        "description": "Company name"
                    },
                    "title": {
                        "type": "string",
                        "description": "Job title"
                    }
                },
                "required": ["name"]
            },
            execute=lambda name, email=None, company=None, title=None: None,
            permissions=["write"],
            category="memory",
            aliases=[],
            metadata={"timeout": 2000, "cost": 0.2}
        ))


# ============================================================================
# Global Registry Instance
# ============================================================================

_global_registry: Optional[ToolRegistry] = None

def get_tool_registry() -> ToolRegistry:
    """
    Get the global tool registry instance (singleton pattern).

    Returns:
        ToolRegistry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


async def init_tool_registry() -> ToolRegistry:
    """
    Initialize the global tool registry.

    Returns:
        Initialized ToolRegistry instance
    """
    registry = get_tool_registry()
    await registry.initialize()
    return registry


# ============================================================================
# Tool Decorator
# ============================================================================

def tool(
    id: str,
    name: str = None,
    description: str = "",
    parameters: Dict[str, Any] = None,
    permissions: List[str] = None,
    category: str = "custom",
    aliases: List[str] = None,
    metadata: Dict[str, Any] = None
):
    """
    Decorator to mark a function as a tool.

    Usage:
        @tool(
            id="my_custom_tool",
            name="My Custom Tool",
            description="Does something useful",
            parameters={
                "type": "object",
                "properties": {
                    "arg": {"type": "string", "description": "Argument"}
                },
                "required": ["arg"]
            },
            permissions=["browser"],
            category="custom"
        )
        async def my_tool(arg: str):
            # Tool implementation
            return {"result": arg}

    Args:
        id: Unique tool identifier
        name: Display name (defaults to function name)
        description: Tool description
        parameters: JSON Schema for parameters
        permissions: Required permissions
        category: Tool category
        aliases: Alternative names
        metadata: Additional metadata

    Returns:
        Decorated function with attached ToolDefinition
    """
    def decorator(func):
        tool_def = ToolDefinition(
            id=id,
            name=name or func.__name__,
            description=description or func.__doc__ or "",
            parameters=parameters or {},
            execute=func,
            permissions=permissions or [],
            category=category,
            aliases=aliases or [],
            metadata=metadata or {}
        )

        # Attach definition to function
        func.__tool_definition__ = tool_def

        return func

    return decorator


# ============================================================================
# Tests
# ============================================================================

async def test_tool_registry():
    """
    Comprehensive test suite for tool registry.

    Tests:
    1. Tool registration and retrieval
    2. Alias resolution
    3. Category indexing
    4. Agent mode filtering
    5. Format conversion (OpenAI, Anthropic, MCP)
    6. Custom tool discovery
    7. Plugin integration
    """
    print("\n========== Testing Tool Registry ==========\n")

    # Test 1: Basic registration and retrieval
    print("Test 1: Basic Registration")
    registry = ToolRegistry()

    test_tool = ToolDefinition(
        id="test_tool",
        name="Test Tool",
        description="A test tool",
        parameters={"type": "object", "properties": {}},
        execute=lambda: None,
        permissions=[],
        category="test"
    )

    assert registry.register(test_tool), "Tool registration failed"
    assert registry.get("test_tool") == test_tool, "Tool retrieval failed"
    print("  ✓ Basic registration works")

    # Test 2: Alias resolution
    print("\nTest 2: Alias Resolution")
    alias_tool = ToolDefinition(
        id="main_tool",
        name="Main Tool",
        description="Tool with aliases",
        parameters={"type": "object", "properties": {}},
        execute=lambda: None,
        permissions=[],
        category="test",
        aliases=["alias1", "alias2"]
    )

    registry.register(alias_tool)
    assert registry.get("alias1") == alias_tool, "Alias resolution failed"
    assert registry.get("alias2") == alias_tool, "Alias resolution failed"
    print("  ✓ Alias resolution works")

    # Test 3: Category indexing
    print("\nTest 3: Category Indexing")
    browser_tools = registry.list_by_category("browser")
    print(f"  ✓ Found {len(browser_tools)} tools (expected 0 for empty registry)")

    # Test 4: Initialize with built-in tools
    print("\nTest 4: Built-in Tools Initialization")
    await registry.initialize()
    all_tools = registry.list_all()
    print(f"  ✓ Initialized with {len(all_tools)} built-in tools")

    # Verify categories
    categories = registry.get_categories()
    print(f"  ✓ Categories: {', '.join(categories)}")
    assert "browser" in categories, "Browser category missing"
    assert "file" in categories, "File category missing"

    # Test 5: Agent mode filtering
    print("\nTest 5: Agent Mode Filtering")
    build_tools = registry.list_enabled('build')
    plan_tools = registry.list_enabled('plan')
    safe_tools = registry.list_enabled('safe')

    print(f"  ✓ Build mode: {len(build_tools)} tools")
    print(f"  ✓ Plan mode: {len(plan_tools)} tools")
    print(f"  ✓ Safe mode: {len(safe_tools)} tools")

    # Build mode should have more tools than safe mode
    assert len(build_tools) > len(safe_tools), "Build mode should have more tools than safe mode"

    # Test 6: Format conversion
    print("\nTest 6: Format Conversion")
    openai_tools = registry.to_openai_format('build')
    anthropic_tools = registry.to_anthropic_format('build')
    mcp_tools = registry.to_mcp_format('build')

    print(f"  ✓ OpenAI format: {len(openai_tools)} tools")
    print(f"  ✓ Anthropic format: {len(anthropic_tools)} tools")
    print(f"  ✓ MCP format: {len(mcp_tools)} tools")

    # Verify format structure
    if openai_tools:
        assert "type" in openai_tools[0], "OpenAI format missing 'type'"
        assert "function" in openai_tools[0], "OpenAI format missing 'function'"

    if anthropic_tools:
        assert "name" in anthropic_tools[0], "Anthropic format missing 'name'"
        assert "input_schema" in anthropic_tools[0], "Anthropic format missing 'input_schema'"

    # Test 7: Permission checking
    print("\nTest 7: Permission Checking")
    write_tool = registry.get("write_file")
    if write_tool:
        build_mode = get_agent_mode('build')
        safe_mode = get_agent_mode('safe')

        assert write_tool.check_permissions(build_mode), "Write tool should be allowed in build mode"
        assert not write_tool.check_permissions(safe_mode), "Write tool should be blocked in safe mode"
        print("  ✓ Permission checking works")

    # Test 8: Statistics
    print("\nTest 8: Registry Statistics")
    stats = registry.get_stats()
    print(f"  ✓ Total tools: {stats['total_tools']}")
    print(f"  ✓ Enabled tools: {stats['enabled_tools']}")
    print(f"  ✓ Categories: {stats['categories']}")
    print(f"  ✓ Aliases: {stats['aliases']}")

    # Test 9: Tool unregistration
    print("\nTest 9: Tool Unregistration")
    assert registry.unregister("test_tool"), "Tool unregistration failed"
    assert registry.get("test_tool") is None, "Tool still exists after unregistration"
    print("  ✓ Tool unregistration works")

    # Test 10: Custom tool decorator
    print("\nTest 10: Custom Tool Decorator")

    @tool(
        id="decorated_tool",
        name="Decorated Tool",
        description="Tool created with decorator",
        parameters={
            "type": "object",
            "properties": {
                "arg": {"type": "string"}
            }
        },
        category="test"
    )
    async def my_tool(arg: str):
        return {"result": arg}

    assert hasattr(my_tool, '__tool_definition__'), "Decorator didn't attach ToolDefinition"
    registry.register(my_tool.__tool_definition__)
    assert registry.get("decorated_tool") is not None, "Decorated tool not registered"
    print("  ✓ Tool decorator works")

    # Summary
    print("\n========== All Tests Passed ==========\n")
    print(f"Total tools in registry: {len(registry.list_all())}")
    print(f"Tool categories: {', '.join(registry.get_categories())}")
    print(f"Aliases registered: {stats['aliases']}")

    return True


if __name__ == '__main__':
    # Run tests when module is executed directly
    import asyncio
    asyncio.run(test_tool_registry())
