"""
MCP Client - Manages connections to MCP servers and tool execution
"""

import asyncio
import json
import csv
import os
import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional
import yaml
from loguru import logger

from .agent_network import AgentNetwork
from .agentic_guards import get_directory_guard


# Canonical tool name mappings - single source of truth
TOOL_ALIASES = {
    # Navigation aliases
    'navigate': 'playwright_navigate',
    'goto': 'playwright_navigate',
    'go_to': 'playwright_navigate',
    'open': 'playwright_navigate',
    'visit': 'playwright_navigate',
    'browse': 'playwright_navigate',
    'load': 'playwright_navigate',

    # Click aliases
    'click': 'playwright_click',
    'press': 'playwright_click',
    'tap': 'playwright_click',

    # Fill aliases
    'fill': 'playwright_fill',
    'type': 'playwright_fill',
    'input': 'playwright_fill',
    'enter': 'playwright_fill',
    'write': 'playwright_fill',

    # Snapshot aliases
    'snapshot': 'playwright_snapshot',
    'get_page': 'playwright_snapshot',
    'page_content': 'playwright_snapshot',
    'get_content': 'playwright_get_markdown',

    # Get markdown/text content aliases
    'read_page': 'playwright_get_markdown',
    'get_text': 'playwright_get_markdown',
    'page_text': 'playwright_get_markdown',
    'read_content': 'playwright_get_markdown',

    # Fast non-browser URL fetching
    'fetch': 'playwright_fetch_url',
    'fetch_url': 'playwright_fetch_url',
    'web_fetch': 'playwright_fetch_url',

    # Screenshot aliases
    'screenshot': 'playwright_screenshot',
    'capture': 'playwright_screenshot',
    'take_screenshot': 'playwright_screenshot',

    # Text extraction aliases
    'extract_text': 'playwright_get_text',
    'read_text': 'playwright_get_text',

    # Contact extraction
    'find_contacts': 'playwright_find_contacts',
    'extract_contacts': 'playwright_find_contacts',
    'get_contacts': 'playwright_find_contacts',

    # File operations
    'save': 'write_file',
    'save_file': 'write_file',
    'create_file': 'write_file',
}


def resolve_tool_name(name: str) -> str:
    """Resolve tool alias to canonical name. Single source of truth."""
    name_lower = name.lower().strip()

    # FIX: Handle combined tool names from bad LLM output like "playwright_fill + playwright_click"
    if ' + ' in name_lower or ' and ' in name_lower:
        # Take the first tool only
        first_tool = name_lower.split(' + ')[0].split(' and ')[0].strip()
        from loguru import logger
        logger.warning(f"[AUTO-FIX] Split combined tool name: '{name}' -> '{first_tool}'")
        name_lower = first_tool

    return TOOL_ALIASES.get(name_lower, name_lower if name_lower in TOOL_ALIASES.values() else name)


class MCPClient:
    """
    Eversale MCP Client - ALWAYS runs internal MCP server with all 74+ tools.

    ARCHITECTURE:
    When eversale starts, it launches an internal MCP server that provides:
    - All Playwright browser tools with stealth mode
    - Claude Code style tools (browser_snapshot, mmid-based clicking)
    - Proof-of-action validation
    - All 74+ extraction/automation tools
    - Memory, filesystem, agent network tools

    The MCP server is the backbone - all tool calls go through it.
    This ensures consistent, reliable browser automation with all tricks enabled.

    Flow:
        User -> eversale CLI -> MCPClient -> [Internal MCP Server] -> PlaywrightClient
                                                     |
                                             All 74+ tools with:
                                             - Firefox stealth
                                             - MMID element refs
                                             - Action verification
                                             - Session memory
                                             - Circuit breaker
                                             - Strategic planning
    """

    def __init__(self, working_dir: str = None):
        self.servers = {}
        self.tools = {}
        self.config = self._load_config()
        self._headless_override = None  # None = use config, True/False = override
        self.agent_network = AgentNetwork()
        self._mcp_server = None  # Internal MCP server instance

        # Initialize directory boundary guard
        if working_dir is None:
            working_dir = os.getcwd()
        self.directory_guard = get_directory_guard(working_dir)

    def set_headless(self, headless: bool):
        """Set headless mode for browser. Call before connect or will reconnect."""
        self._headless_override = headless
        logger.info(f"Headless mode set to: {headless}")

    def enable_fast_track(self):
        """
        Enable FAST_TRACK mode - skips all humanization delays.

        This disables:
        - Bezier curve mouse movements
        - Human-like typing delays
        - Scroll humanization
        - Random pauses between actions

        Use for: "fast track", "turbo", "quickly", "rapid" prompts
        """
        self._fast_track = True
        # Wire to the actual timing system used by playwright_direct (stealth_utils.human_delay)
        try:
            from .stealth_utils import request_speed_mode
            request_speed_mode("fast")
        except Exception:
            pass
        # Import and configure humanization modules if available
        try:
            from humanization import BezierCursor, HumanTyper, HumanScroller
            # These will check _fast_track flag and skip delays
            logger.info("[FAST_TRACK] Humanization disabled for maximum speed")
        except ImportError:
            pass

    def disable_fast_track(self):
        """Disable FAST_TRACK mode - resume normal humanization."""
        self._fast_track = False
        try:
            from .stealth_utils import request_speed_mode
            request_speed_mode("off")
        except Exception:
            pass
        logger.info("[FAST_TRACK] Humanization re-enabled")

    @property
    def fast_track_enabled(self) -> bool:
        """Check if FAST_TRACK mode is enabled."""
        return getattr(self, '_fast_track', False)

    def detect_speed_mode_from_prompt(self, prompt: str) -> str:
        """
        Detect speed mode intent from natural language and request it.

        Returns: "off" | "fast" | "turbo"
        """
        prompt_lower = (prompt or "").lower()

        disable = [
            "disable fast", "disable speed", "no fast", "no turbo", "no speed mode",
            "be careful", "slow down", "human-like", "stealth", "avoid detection",
        ]
        if any(k in prompt_lower for k in disable):
            self.disable_fast_track()
            try:
                from .stealth_utils import request_speed_mode
                request_speed_mode("off")
            except Exception:
                pass
            return "off"

        turbo = ["turbo", "speed mode", "instant", "rush", "asap", "go fast"]
        fast = ["fast track", "quickly", "rapid", "fast"]

        if any(k in prompt_lower for k in turbo):
            self.enable_fast_track()
            try:
                from .stealth_utils import request_speed_mode
                request_speed_mode("turbo")
            except Exception:
                pass
            return "turbo"

        if any(k in prompt_lower for k in fast):
            self.enable_fast_track()
            return "fast"

        # Default: do not carry speed mode across unrelated tasks
        self.disable_fast_track()
        return "off"

    def add_temporary_file_permission(self, path: str):
        """
        Grant temporary file access permission outside working directory.

        Args:
            path: Path to grant temporary access to
        """
        self.directory_guard.add_temporary_permission(path)

    def remove_temporary_file_permission(self, path: str):
        """
        Remove temporary file access permission.

        Args:
            path: Path to revoke access from
        """
        self.directory_guard.remove_temporary_permission(path)

    def clear_temporary_file_permissions(self):
        """Clear all temporary file permissions."""
        self.directory_guard.clear_temporary_permissions()

    def detect_headless_from_prompt(self, prompt: str) -> bool:
        """Detect if user wants visible browser from their prompt."""
        prompt_lower = prompt.lower()
        # Keywords that mean "show the browser"
        show_browser_keywords = [
            'not headless', 'non headless', 'no headless',
            'show browser', 'visible browser', 'see browser',
            'watch browser', 'show chrome', 'visible chrome',
            'show the browser', 'open browser', 'display browser'
        ]
        for keyword in show_browser_keywords:
            if keyword in prompt_lower:
                self.set_headless(False)
                return False  # Not headless = visible
        # Use config default if no keywords found
        browser_config = self.config.get("browser", {})
        return browser_config.get("headless_default", True)  # Default headless for speed

    def _load_config(self) -> dict:
        """Load MCP server configuration"""
        config_path = Path("config/config.yaml")

        if config_path.exists():
            with open(config_path) as f:
                return yaml.safe_load(f)
        else:
            logger.warning("No config file found, using defaults")
            return self._default_config()

    def _default_config(self) -> dict:
        """Default MCP configuration"""
        return {
            "mcp": {
                "servers": {
                    "playwright": {
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-playwright"],
                    },
                    "memory": {
                        "command": "python",
                        "args": ["mcp_servers/memory_server.py"],
                    },
                    "filesystem": {
                        "command": "python",
                        "args": ["mcp_servers/filesystem_server.py"],
                    }
                }
            }
        }

    async def connect_all_servers(self):
        """
        Launch internal MCP server and connect all tools.

        This is the main entry point - it starts the MCP server backbone
        that powers all of Eversale's browser automation.
        """
        from .mcp_server import EversaleMCPServer

        # Determine headless mode - env var takes priority
        if os.environ.get("EVERSALE_HEADLESS", "").lower() in ("false", "0", "no"):
            headless = False
        elif self._headless_override is not None:
            headless = self._headless_override
        else:
            browser_config = self.config.get("browser", {})
            headless = browser_config.get("headless_default", True)  # Default to headless

        # Launch internal MCP server with all 74+ tools
        logger.info("Launching Eversale MCP Server (internal backbone)...")
        self._mcp_server = EversaleMCPServer(headless=headless)
        await self._mcp_server.initialize()

        # Store reference for tool calls
        self.servers["mcp"] = {
            "name": "eversale-mcp",
            "server": self._mcp_server,
            "connected": True
        }

        # Get all tools from MCP server
        mcp_tools = self._mcp_server.get_tools_list()
        for tool in mcp_tools:
            self.tools[tool["name"]] = {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "params": tool.get("inputSchema", {}).get("properties", {})
            }

        # Also connect memory, filesystem, agent network (non-browser tools)
        server_configs = self.config.get("mcp", {}).get("servers", {})
        for server_name, server_config in server_configs.items():
            if server_name != "playwright":  # Skip - MCP server handles this
                try:
                    await self._connect_server(server_name, server_config)
                except Exception as e:
                    logger.warning(f"Non-critical server {server_name} not available: {e}")

        # Register additional tools (memory, filesystem, agent network)
        await self._register_tools()

        logger.info(f"✓ MCP Server ready with {len(self.tools)} tools")

    async def close(self):
        """Gracefully shutdown MCP server and disconnect all."""
        # Shutdown internal MCP server
        if self._mcp_server:
            try:
                await self._mcp_server.shutdown()
            except Exception as exc:
                logger.warning(f"Error shutting down MCP server: {exc}")
            self._mcp_server = None

        # Close any other servers
        for name, server in list(self.servers.items()):
            try:
                if name == "playwright" and "client" in server:
                    await server["client"].disconnect()
            except Exception as exc:
                logger.warning(f"Error closing server {name}: {exc}")

        self.servers.clear()
        self.tools.clear()

    async def _connect_server(self, name: str, config: dict):
        """Connect to a single MCP server"""

        # Connect to Playwright (direct implementation)
        if name == "playwright":
            from .playwright_direct import PlaywrightClient
            from .web_automation_tools import WebAutomationTools

            # Check for override first, then config
            if self._headless_override is not None:
                headless = self._headless_override
            else:
                # Read from browser config section, not env
                browser_config = self.config.get("browser", {})
                headless = browser_config.get("headless_default", True)  # Default headless for speed
            user_data_dir = config.get("env", {}).get("USER_DATA_DIR")
            storage_state = config.get("env", {}).get("STORAGE_STATE")
            browser_type = os.environ.get("EVERSALE_PLAYWRIGHT_BROWSER") or config.get("env", {}).get("BROWSER_TYPE") or "chromium"

            client = PlaywrightClient(
                headless=headless,
                user_data_dir=user_data_dir,
                storage_state=storage_state,
                browser_type=browser_type
            )
            await client.connect()

            # Add advanced automation tools
            automation_tools = WebAutomationTools(client)

            self.servers[name] = {
                "name": name,
                "client": client,
                "automation": automation_tools,
                "connected": True
            }

        else:
            # For other servers (memory, filesystem), use placeholder for now
            # In production, would spawn subprocess here
            self.servers[name] = {
                "name": name,
                "config": config,
                "connected": True
            }

    async def _register_tools(self):
        """Register tools from all connected servers"""

        # Playwright tools - get from direct client
        if "playwright" in self.servers:
            playwright_server = self.servers["playwright"]

            if "client" in playwright_server:
                # Get tools from Playwright client
                playwright_tools = playwright_server["client"].get_tools()

                for tool_name, tool_def in playwright_tools.items():
                    self.tools[tool_name] = tool_def

                # Add advanced automation tools
                if "automation" in playwright_server:
                    automation_tools = playwright_server["automation"].get_tools_definition()
                    for tool_def in automation_tools:
                        self.tools[tool_def["name"]] = tool_def
            else:
                # Fallback tools (shouldn't happen if connection works)
                self.tools.update({
                    "playwright_navigate": {
                        "name": "playwright_navigate",
                        "description": "Navigate browser to a URL",
                        "params": {"url": "string"}
                    },
                    "playwright_click": {
                        "name": "playwright_click",
                        "description": "Click an element on the page",
                        "params": {"selector": "string (CSS selector)"}
                    },
                    "playwright_fill": {
                        "name": "playwright_fill",
                        "description": "Fill a form input field",
                        "params": {"selector": "string", "value": "string"}
                    },
                    "playwright_screenshot": {
                        "name": "playwright_screenshot",
                        "description": "Take a screenshot of current page",
                        "params": {"name": "string (optional)"}
                    },
                    "playwright_evaluate": {
                        "name": "playwright_evaluate",
                        "description": "Execute JavaScript in the page",
                        "params": {"script": "string"}
                    },
                    "playwright_snapshot": {
                        "name": "playwright_snapshot",
                        "description": "Capture accessibility snapshot and summary of the current page",
                        "params": {}
                    },
                    "playwright_get_outline": {
                        "name": "playwright_get_outline",
                        "description": "Alias for playwright_snapshot (accessibility outline + summary)",
                        "params": {}
                    },
                    "playwright_find_contacts": {
                        "name": "playwright_find_contacts",
                        "description": "Extract emails/phones/contact links from current page",
                        "params": {}
                    },
                    "playwright_extract": {
                        "name": "playwright_extract",
                        "description": "Alias for playwright_get_content (page HTML)",
                        "params": {}
                    },
                    # CLAUDE CODE STYLE TOOLS (mmid-based, verification)
                    "browser_snapshot": {
                        "name": "browser_snapshot",
                        "description": "CLAUDE CODE STYLE: Get page snapshot with mmid element refs for reliable clicking",
                        "params": {}
                    },
                    "browser_click": {
                        "name": "browser_click",
                        "description": "CLAUDE CODE STYLE: Click element by mmid (e.g., 'mm5')",
                        "params": {"mmid": "string (required)"}
                    },
                    "browser_type": {
                        "name": "browser_type",
                        "description": "CLAUDE CODE STYLE: Type into element by mmid",
                        "params": {"mmid": "string", "text": "string", "clear": "boolean (default true)"}
                    },
                    "browser_navigate": {
                        "name": "browser_navigate",
                        "description": "CLAUDE CODE STYLE: Navigate to URL",
                        "params": {"url": "string (required)"}
                    },
                    "browser_scroll": {
                        "name": "browser_scroll",
                        "description": "CLAUDE CODE STYLE: Scroll page up/down",
                        "params": {"direction": "up or down", "amount": "integer (pixels)"}
                    },
                    "browser_fingerprint": {
                        "name": "browser_fingerprint",
                        "description": "Get DOM fingerprint for proof-of-action validation",
                        "params": {}
                    },
                    "browser_click_verified": {
                        "name": "browser_click_verified",
                        "description": "Click with automatic verification that action worked",
                        "params": {"selector": "string (CSS or mmid)"}
                    }
                })

        # Memory/Contact tools
        if "memory" in self.servers:
            self.tools.update({
                "save_contact": {
                    "name": "save_contact",
                    "description": "Save a new contact to database",
                    "params": {
                        "name": "string",
                        "company": "string",
                        "email": "string (optional)",
                        "linkedin": "string (optional)",
                        "title": "string (optional)",
                        "context": "string (optional)"
                    }
                },
                "get_contact": {
                    "name": "get_contact",
                    "description": "Retrieve a contact by name or email",
                    "params": {"query": "string"}
                },
                "search_contacts": {
                    "name": "search_contacts",
                    "description": "Search contacts by criteria",
                    "params": {"company": "string (optional)", "status": "string (optional)"}
                },
                "log_interaction": {
                    "name": "log_interaction",
                    "description": "Log an interaction with a contact",
                    "params": {
                        "contact_id": "number",
                        "type": "string (email_sent, reply_received, call, meeting)",
                        "content": "string"
                    }
                },
                "get_history": {
                    "name": "get_history",
                    "description": "Get interaction history for a contact",
                    "params": {"contact_id": "number"}
                }
            })

        # Filesystem tools
        if "filesystem" in self.servers:
            self.tools.update({
                "read_file": {
                    "name": "read_file",
                    "description": "Read a file",
                    "params": {"path": "string"}
                },
                "write_file": {
                    "name": "write_file",
                    "description": "Write content to a file",
                    "params": {"path": "string", "content": "string"}
                },
                "write_validated_csv": {
                    "name": "write_validated_csv",
                    "description": "Write a CSV with validation/deduplication. Params: path, rows (list of objects), required_fields (list), dedupe_keys (list).",
                    "params": {
                        "path": "string",
                        "rows": "list",
                        "required_fields": "list (optional)",
                        "dedupe_keys": "list (optional)"
                    }
                }
            })

        # Agent network tools
        self.tools.update({
            "delegate_task": {
                "name": "delegate_task",
                "description": "Send a subtask to another agent instance.",
                "params": {
                    "prompt": "string (task prompt)",
                    "agent_id": "string (optional, defaults to agent-alpha)"
                }
            },
            "agent_status": {
                "name": "agent_status",
                "description": "Get status of delegated agent tasks.",
                "params": {}
            }
        })

        logger.info(f"Registered {len(self.tools)} tools")
        self.servers.setdefault("agent_network", {"name": "agent_network", "connected": True})

    async def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """
        Execute a tool call via MCP server backbone.

        ALL browser/playwright/browser_* tools go through the internal MCP server.
        This ensures consistent behavior with all tricks enabled.

        Args:
            tool_name: Name of the tool to call
            params: Parameters for the tool

        Returns:
            Tool execution result
        """
        params = params or {}

        # Resolve tool aliases to canonical names
        tool_name = resolve_tool_name(tool_name)

        logger.debug(f"Calling tool: {tool_name} with params: {params}")

        # Automation tools that don't have playwright_ prefix but should go to MCP
        automation_tools = {
            "smart_type", "smart_wait", "extract_data", "extract_table", "save_to_csv",
            "take_screenshot", "scroll_page", "press_key", "hover", "select_dropdown",
            "check_checkbox", "wait_and_click", "get_element_text", "get_cookies", "set_cookies",
            "detect_contact_form", "detect_captcha", "fill_contact_form", "submit_contact_forms"
        }

        # ROUTE 1: Browser tools -> Internal MCP Server (the backbone)
        if tool_name.startswith("playwright_") or tool_name.startswith("browser_") or tool_name in automation_tools:
            if self._mcp_server:
                result = await self._mcp_server.call_tool(tool_name, params)
                return result
            else:
                return {"error": "MCP server not initialized"}

        # ROUTE 2: Filesystem tools -> Direct simulation (faster)
        if tool_name in ["read_file", "write_file", "write_validated_csv"]:
            return await self._simulate_tool_call(tool_name, params)

        # ROUTE 3: Memory/Agent tools -> Simulation
        if tool_name in ["save_contact", "get_contact", "search_contacts",
                         "log_interaction", "get_history", "delegate_task", "agent_status"]:
            return await self._simulate_tool_call(tool_name, params)

        # ROUTE 4: Unknown tool - try MCP server as fallback
        if self._mcp_server:
            try:
                result = await self._mcp_server.call_tool(tool_name, params)
                return result
            except Exception as e:
                logger.warning(f"MCP server doesn't have tool {tool_name}: {e}")

        # Check if tool is registered at all
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")

        # Final fallback to simulation
        result = await self._simulate_tool_call(tool_name, params)
        return result

    def _get_server_for_tool(self, tool_name: str) -> Optional[str]:
        """Determine which MCP server handles a tool"""

        # Playwright tools (both basic and automation)
        playwright_tools = [
            "playwright_navigate", "playwright_click", "playwright_fill", "playwright_screenshot",
            "playwright_evaluate", "playwright_snapshot", "playwright_get_outline",
            "playwright_find_contacts", "playwright_extract", "playwright_get_content", "playwright_get_text",
            "playwright_get_markdown", "playwright_fetch_url", "playwright_llm_extract", "playwright_extract_entities",
            "playwright_extract_fb_ads", "playwright_extract_tiktok_ads", "playwright_extract_reddit", "playwright_extract_page_fast",
            "playwright_batch_extract",
            # Automation tools
            "smart_type", "smart_wait", "extract_data", "extract_table", "save_to_csv",
            "take_screenshot", "scroll_page", "press_key", "hover", "select_dropdown",
            "check_checkbox", "wait_and_click", "get_element_text", "get_cookies", "set_cookies",
            # Contact form tools
            "detect_contact_form", "detect_captcha", "fill_contact_form", "submit_contact_forms"
        ]

        if tool_name.startswith("playwright_") or tool_name.startswith("browser_") or tool_name in playwright_tools:
            return "playwright"
        elif tool_name in ["save_contact", "get_contact", "search_contacts", "log_interaction", "get_history"]:
            return "memory"
        elif tool_name in ["read_file", "write_file", "write_validated_csv"]:
            return "filesystem"
        elif tool_name in ["delegate_task", "agent_status"]:
            return "agent_network"
        return None

    async def _simulate_tool_call(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """
        Fallback tool execution for tools not handled by real MCP servers.
        Playwright tools should NEVER reach this - they go to real browser.
        """

        # Playwright/browser tools should use real browser - error if we reach simulation
        if tool_name.startswith("playwright_") or tool_name.startswith("browser_"):
            logger.error(f"CRITICAL: Browser tool {tool_name} reached simulation - should use real browser!")
            return {"error": f"Tool {tool_name} not available - browser not connected"}

        # Memory operations (in-memory storage - no persistent DB)
        elif tool_name == "save_contact":
            # Store contact in session memory
            contact_id = str(uuid.uuid4())[:12]
            if not hasattr(self, '_memory_contacts'):
                self._memory_contacts = {}
            self._memory_contacts[contact_id] = params
            return {"status": "saved", "contact_id": contact_id}

        elif tool_name == "get_contact":
            # Retrieve from session memory
            if not hasattr(self, '_memory_contacts'):
                self._memory_contacts = {}
            contact_id = params.get("contact_id")
            if contact_id in self._memory_contacts:
                return self._memory_contacts[contact_id]
            return {"error": f"Contact {contact_id} not found"}

        # Filesystem simulations / direct operations
        elif tool_name == "read_file":
            path_str = params.get("path", "")
            if not path_str:
                return {"error": "No path provided"}

            # Check directory boundary guard
            allowed, reason = self.directory_guard.check_access(path_str)
            if not allowed:
                logger.warning(f"[DIRECTORY_GUARD] Blocked read_file: {reason}")
                return {"error": f"Access denied: {reason}"}

            path = Path(path_str)
            if not path.exists():
                return {"error": f"File not found: {path}"}
            try:
                content = path.read_text(encoding="utf-8")
                return {"status": "success", "path": str(path), "content": content, "bytes": len(content.encode("utf-8"))}
            except Exception as e:
                return {"error": str(e)}

        elif tool_name == "write_file":
            path_str = params.get("path", "output.txt")

            # Check directory boundary guard
            allowed, reason = self.directory_guard.check_access(path_str)
            if not allowed:
                logger.warning(f"[DIRECTORY_GUARD] Blocked write_file: {reason}")
                return {"error": f"Access denied: {reason}"}

            path = Path(path_str)
            content = params.get("content", "")
            append_mode = params.get("append", False)
            path.parent.mkdir(parents=True, exist_ok=True)

            if append_mode:
                # Append to file for monitoring/forever mode
                with open(path, "a", encoding="utf-8") as f:
                    f.write(str(content))
                mode_str = "appended"
            else:
                path.write_text(str(content), encoding="utf-8")
                mode_str = "written"

            return {"status": "success", "path": str(path), "bytes": len(str(content).encode("utf-8")), "mode": mode_str}

        elif tool_name == "write_validated_csv":
            path_str = params.get("path", "output.csv")

            # Check directory boundary guard
            allowed, reason = self.directory_guard.check_access(path_str)
            if not allowed:
                logger.warning(f"[DIRECTORY_GUARD] Blocked write_validated_csv: {reason}")
                return {"error": f"Access denied: {reason}"}

            path = Path(path_str)
            rows = params.get("rows", [])
            if isinstance(rows, str):
                try:
                    rows = json.loads(rows)
                except Exception:
                    rows = []
            if not isinstance(rows, list):
                rows = []

            required_fields = params.get("required_fields", []) or []
            dedupe_keys = params.get("dedupe_keys", []) or []

            def has_required(r):
                for f in required_fields:
                    if not str(r.get(f, "")).strip():
                        return False
                return True

            filtered = [r for r in rows if isinstance(r, dict) and has_required(r)]

            seen = set()
            deduped = []
            for r in filtered:
                key = tuple((r.get(k, "") or "").strip().lower() for k in dedupe_keys) if dedupe_keys else tuple(sorted(r.items()))
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(r)

            if not deduped:
                return {"error": "no valid rows to write", "path": str(path)}

            # Determine headers
            headers = []
            for r in deduped:
                for k in r.keys():
                    if k not in headers:
                        headers.append(k)
            if not headers:
                headers = required_fields

            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                for r in deduped:
                    writer.writerow({k: r.get(k, "") for k in headers})

            return {
                "status": "success",
                "path": str(path),
                "rows_written": len(deduped),
                "headers": headers
            }

        if tool_name == "delegate_task":
            prompt = params.get("prompt", "")
            agent_id = params.get("agent_id", "agent-alpha")
            return self.agent_network.delegate_task(prompt, agent_id=agent_id)

        if tool_name == "agent_status":
            return self.agent_network.get_status()

        # Default
        return {"status": "success", "message": f"Executed {tool_name}"}

    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of all available tools"""
        return [
            {
                "name": name,
                "description": tool["description"],
                "params": tool.get("params", tool.get("parameters", {}))
            }
            for name, tool in self.tools.items()
        ]

    async def disconnect_all_servers(self):
        """Disconnect from all MCP servers (alias for close)"""
        await self.close()
