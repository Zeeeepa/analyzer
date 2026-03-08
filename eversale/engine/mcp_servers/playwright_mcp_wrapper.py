#!/usr/bin/env python3
"""
Playwright MCP Wrapper - Connects to @modelcontextprotocol/server-playwright

This wraps the official Playwright MCP server and provides a Python interface.
The server runs as a subprocess and we communicate via stdio.
"""

import asyncio
import json
import subprocess
from typing import Dict, Any, Optional
from loguru import logger


class PlaywrightMCPClient:
    """
    Client for the official Playwright MCP server

    Starts the server as a subprocess and communicates via JSON-RPC over stdio.
    """

    def __init__(self, headless: bool = False, user_data_dir: Optional[str] = None):
        self.process: Optional[subprocess.Popen] = None
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.request_id = 0
        self.connected = False

    async def connect(self):
        """Start the Playwright MCP server"""

        logger.info("Starting Playwright MCP server...")

        # Build environment
        env = {
            "PLAYWRIGHT_HEADLESS": "true" if self.headless else "false",
        }

        if self.user_data_dir:
            env["PLAYWRIGHT_USER_DATA_DIR"] = self.user_data_dir

        # Start server process
        try:
            self.process = subprocess.Popen(
                ["npx", "@modelcontextprotocol/server-playwright"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                bufsize=0
            )

            # Wait a bit for server to start
            await asyncio.sleep(2)

            # Check if process started successfully
            if self.process.poll() is not None:
                stderr = self.process.stderr.read().decode()
                raise RuntimeError(f"Playwright MCP server failed to start: {stderr}")

            self.connected = True
            logger.info("✓ Playwright MCP server started")

        except FileNotFoundError:
            raise RuntimeError(
                "Playwright MCP server not found. Install with:\n"
                "npm install -g @modelcontextprotocol/server-playwright"
            )

    async def disconnect(self):
        """Stop the Playwright MCP server"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

            self.connected = False
            logger.info("Playwright MCP server stopped")

    async def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """
        Call a tool on the Playwright MCP server

        Args:
            tool_name: Name of the tool (e.g., "playwright_navigate")
            params: Tool parameters

        Returns:
            Tool result
        """

        if not self.connected:
            raise RuntimeError("Not connected to Playwright MCP server")

        self.request_id += 1

        # Build JSON-RPC request
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": params
            }
        }

        logger.debug(f"Playwright MCP request: {tool_name} with {params}")

        try:
            # Send request
            request_json = json.dumps(request) + "\n"
            self.process.stdin.write(request_json.encode())
            self.process.stdin.flush()

            # Read response (with timeout)
            response_line = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    self.process.stdout.readline
                ),
                timeout=30.0
            )

            response = json.loads(response_line)

            if "error" in response:
                error_msg = response["error"].get("message", "Unknown error")
                logger.error(f"Playwright MCP error: {error_msg}")
                return {"error": error_msg}

            result = response.get("result", {})
            logger.debug(f"Playwright MCP result: {str(result)[:200]}")

            return result

        except asyncio.TimeoutError:
            logger.error(f"Timeout calling {tool_name}")
            return {"error": "Timeout waiting for Playwright response"}

        except Exception as e:
            logger.exception(f"Error calling Playwright tool: {e}")
            return {"error": str(e)}

    def get_available_tools(self) -> list:
        """
        Get list of available Playwright tools

        Based on @modelcontextprotocol/server-playwright
        """
        return [
            {
                "name": "playwright_navigate",
                "description": "Navigate browser to a URL",
                "params": {
                    "url": "string (required)"
                }
            },
            {
                "name": "playwright_screenshot",
                "description": "Take a screenshot of the current page",
                "params": {
                    "name": "string (optional) - filename",
                    "fullPage": "boolean (optional) - capture full page"
                }
            },
            {
                "name": "playwright_click",
                "description": "Click an element on the page",
                "params": {
                    "selector": "string (required) - CSS selector"
                }
            },
            {
                "name": "playwright_fill",
                "description": "Fill a form input field",
                "params": {
                    "selector": "string (required) - CSS selector",
                    "value": "string (required) - text to fill"
                }
            },
            {
                "name": "playwright_select",
                "description": "Select an option from a dropdown",
                "params": {
                    "selector": "string (required) - CSS selector",
                    "value": "string (required) - option value"
                }
            },
            {
                "name": "playwright_hover",
                "description": "Hover over an element",
                "params": {
                    "selector": "string (required) - CSS selector"
                }
            },
            {
                "name": "playwright_evaluate",
                "description": "Execute JavaScript in the page",
                "params": {
                    "script": "string (required) - JavaScript code"
                }
            },
            {
                "name": "playwright_type",
                "description": "Type text into an element",
                "params": {
                    "selector": "string (required) - CSS selector",
                    "text": "string (required) - text to type"
                }
            }
        ]


# Standalone test
async def test_playwright_mcp():
    """Test the Playwright MCP connection"""

    client = PlaywrightMCPClient(headless=False)

    try:
        await client.connect()

        # Test navigation
        print("Testing navigation...")
        result = await client.call_tool("playwright_navigate", {"url": "https://example.com"})
        print(f"Navigate result: {result}")

        # Test evaluate (extract text)
        print("\nTesting evaluate...")
        result = await client.call_tool("playwright_evaluate", {
            "script": "document.querySelector('h1').textContent"
        })
        print(f"Evaluate result: {result}")

        # Test screenshot
        print("\nTesting screenshot...")
        result = await client.call_tool("playwright_screenshot", {"name": "test.png"})
        print(f"Screenshot result: {result}")

        print("\n✅ All tests passed!")

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(test_playwright_mcp())
