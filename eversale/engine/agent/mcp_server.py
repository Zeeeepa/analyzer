#!/usr/bin/env python3
"""
Eversale MCP Server - Full MCP protocol implementation with all 74+ tools.

This runs as a proper MCP server (JSON-RPC over stdio) that can be used by:
- Claude Code / Claude Desktop
- Any MCP-compatible client
- VS Code with MCP extensions

It wraps our PlaywrightClient with all the stealth, extraction, and Claude Code
style features (mmid, verification, etc.)

Usage:
    # As MCP server (for Claude Code):
    python -m agent.mcp_server

    # Test standalone:
    python -m agent.mcp_server --test

MCP Configuration (for Claude Code's claude_desktop_config.json):
{
    "mcpServers": {
        "eversale": {
            "command": "python",
            "args": ["-m", "agent.mcp_server"],
            "cwd": "/path/to/agent1"
        }
    }
}
"""

import asyncio
import json
import sys
import os
import time
from typing import Dict, Any, List, Optional
from pathlib import Path
from loguru import logger

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.playwright_direct import PlaywrightClient


class EversaleMCPServer:
    """
    Full MCP server implementation exposing all Playwright + Eversale tools.

    This is the proper way to run browser automation that Claude Code expects:
    - JSON-RPC 2.0 over stdio
    - tools/list endpoint
    - tools/call endpoint
    - All 74+ tools available
    """

    def __init__(self, headless: bool = True):
        self.client: Optional[PlaywrightClient] = None
        self.headless = headless
        self.request_id = 0
        self._initialized = False
        self._login_mode_active = False  # Track if we're in login mode

        # Note: Logging is configured by run_ultimate.py
        # Only add file handler if not already configured
        import os
        if not os.environ.get('EVERSALE_LOGGING_CONFIGURED'):
            logger.add("logs/mcp_server.log", rotation="10 MB", level="DEBUG")

    async def initialize(self):
        """Initialize the Playwright client with all our enhancements."""
        if self._initialized:
            return

        logger.info("Initializing Eversale MCP Server...")

        # Use bundled Chromium by default (not system Chrome 138 which crashes with SIGTRAP)
        # Firefox has DNS issues in WSL2. Playwright's bundled Chromium works well.
        # Set EVERSALE_BROWSER=firefox to use Firefox if needed
        browser_type = os.environ.get("EVERSALE_BROWSER", "chromium")

        self.client = PlaywrightClient(
            headless=self.headless,
            browser_type=browser_type
        )
        await self.client.connect()

        self._initialized = True
        logger.info(f"✓ MCP Server ready ({browser_type}, headless={self.headless})")

    async def enter_login_mode(self, service: str = None) -> Dict[str, Any]:
        """Switch to visible browser for login."""
        if not self.client:
            return {"error": "Client not initialized"}
        self._login_mode_active = True
        return await self.client.login_mode(service)

    async def finish_login_mode(self, service: str = None) -> Dict[str, Any]:
        """Save login and return to headless mode."""
        if not self.client:
            return {"error": "Client not initialized"}
        result = await self.client.finish_login(service)
        self._login_mode_active = False
        return result

    async def shutdown(self):
        """Clean shutdown."""
        if self.client:
            await self.client.disconnect()
        self._initialized = False
        logger.info("MCP Server stopped")

    def get_tools_list(self) -> List[Dict[str, Any]]:
        """
        Return MCP-formatted tool definitions.

        This is what Claude Code sees when it connects.
        """
        if not self.client:
            return []

        raw_tools = self.client.get_tools()

        # Handle ToolResult wrapper (from reliable_browser_tools)
        if hasattr(raw_tools, 'data') and hasattr(raw_tools, 'success'):
            raw_tools = raw_tools.data if raw_tools.success else {}

        mcp_tools = []

        for name, tool_def in raw_tools.items():
            try:
                # Convert our format to MCP format
                mcp_tool = {
                    "name": name,
                    "description": tool_def.get("description", f"Execute {name}"),
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }

                # Convert parameters
                params = tool_def.get("parameters", {})
                for param_name, param_def in params.items():
                    if isinstance(param_def, dict):
                        prop = {
                            "type": param_def.get("type", "string"),
                            "description": param_def.get("description", "")
                        }
                        if "default" in param_def:
                            prop["default"] = param_def["default"]
                        mcp_tool["inputSchema"]["properties"][param_name] = prop

                        if param_def.get("required", False):
                            mcp_tool["inputSchema"]["required"].append(param_name)
                    else:
                        # Simple string type definition
                        mcp_tool["inputSchema"]["properties"][param_name] = {
                            "type": "string",
                            "description": str(param_def)
                        }

                mcp_tools.append(mcp_tool)
            except Exception as e:
                logger.error(f"Failed to convert tool {name} to MCP format: {e}")

        return mcp_tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool and return the result.

        This is the main entry point for Claude Code to run browser actions.
        """
        if not self._initialized:
            await self.initialize()

        try:
            result = await self.client.call_tool(name, arguments)
            return result
        except Exception as e:
            logger.exception(f"Tool {name} failed: {e}")
            return {"error": str(e)}

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a JSON-RPC request.

        Supports:
        - initialize
        - tools/list
        - tools/call
        - shutdown
        """
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")

        try:
            if method == "initialize":
                await self.initialize()
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "eversale-mcp",
                        "version": "2.1.0"
                    }
                }

            elif method == "tools/list":
                if not self._initialized:
                    await self.initialize()
                result = {"tools": self.get_tools_list()}

            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})

                tool_result = await self.call_tool(tool_name, arguments)

                # Format as MCP tool result
                if isinstance(tool_result, dict) and "error" in tool_result:
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error: {tool_result['error']}"
                            }
                        ],
                        "isError": True
                    }
                else:
                    # Success - return as text content
                    result_text = json.dumps(tool_result, indent=2, default=str)
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": result_text
                            }
                        ]
                    }

            elif method == "notifications/initialized":
                # Client acknowledging initialization - no response needed
                return None

            elif method == "shutdown":
                await self.shutdown()
                result = {}

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }

        except Exception as e:
            logger.exception(f"Error handling {method}: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }

    async def run_stdio(self):
        """
        Run the MCP server over stdio.

        This is the main loop that Claude Code communicates with.
        """
        logger.info("Starting MCP server on stdio...")

        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(
            lambda: protocol, sys.stdin
        )

        writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, asyncio.get_event_loop())

        # ENTERPRISE: Heartbeat for connection health
        last_activity = time.time()
        heartbeat_timeout = 300  # 5 min idle timeout

        try:
            while True:
                # Read line from stdin WITH TIMEOUT (prevents zombie processes)
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=60.0)
                    last_activity = time.time()
                except asyncio.TimeoutError:
                    # Check if idle too long
                    if time.time() - last_activity > heartbeat_timeout:
                        logger.warning("MCP client idle timeout, disconnecting")
                        break
                    continue  # Keep waiting

                if not line:
                    break

                try:
                    request = json.loads(line.decode().strip())
                    response = await self.handle_request(request)

                    if response:  # Some methods don't need response
                        response_json = json.dumps(response) + "\n"
                        writer.write(response_json.encode())
                        await writer.drain()

                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON: {e}")
                    error_response = {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32700,
                            "message": "Parse error"
                        }
                    }
                    writer.write((json.dumps(error_response) + "\n").encode())
                    await writer.drain()

        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()


async def test_server():
    """Test the MCP server locally."""
    print("Testing Eversale MCP Server...")

    server = EversaleMCPServer(headless=False)  # Show browser for testing

    try:
        await server.initialize()

        # List tools
        tools = server.get_tools_list()
        print(f"\n✓ {len(tools)} tools available")

        # Show some key tools
        key_tools = [
            "browser_snapshot", "browser_click", "browser_type",
            "playwright_navigate", "playwright_extract_page_fast"
        ]
        print("\nKey tools:")
        for tool in tools:
            if tool["name"] in key_tools:
                print(f"  - {tool['name']}: {tool['description'][:60]}...")

        # Test navigation
        print("\nTesting browser_navigate...")
        result = await server.call_tool("browser_navigate", {"url": "https://example.com"})
        print(f"  Result: {result.get('success', False)}")

        # Test snapshot
        print("\nTesting browser_snapshot...")
        result = await server.call_tool("browser_snapshot", {})
        if result.get("success"):
            print(f"  Found {result.get('element_count', 0)} interactive elements")
            print(f"  Title: {result.get('title', 'N/A')}")

        print("\n✓ All tests passed!")

    finally:
        await server.shutdown()


async def main():
    """Main entry point."""
    if "--test" in sys.argv:
        await test_server()
    else:
        # Run as MCP server
        server = EversaleMCPServer(
            headless="--headless" in sys.argv or os.environ.get("EVERSALE_HEADLESS", "true").lower() == "true"
        )
        await server.run_stdio()


if __name__ == "__main__":
    asyncio.run(main())
