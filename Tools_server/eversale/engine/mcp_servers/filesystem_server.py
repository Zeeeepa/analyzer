#!/usr/bin/env python3
"""
Filesystem MCP Server - File operations

Provides tools for:
- Reading files
- Writing files
- Listing directories
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any


class FilesystemServer:
    """MCP server for filesystem operations"""

    def __init__(self, workspace: str = "./workspace"):
        self.workspace = Path(workspace)
        self.workspace.mkdir(exist_ok=True, parents=True)

    def read_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read a file"""

        file_path = Path(params.get("path"))

        # Ensure within workspace
        if not str(file_path).startswith(str(self.workspace)):
            file_path = self.workspace / file_path

        if not file_path.exists():
            return {"error": f"File not found: {file_path}"}

        try:
            content = file_path.read_text()
            return {
                "status": "success",
                "path": str(file_path),
                "content": content
            }
        except Exception as e:
            return {"error": str(e)}

    def write_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Write content to a file"""

        file_path = Path(params.get("path"))

        # Ensure within workspace
        if not str(file_path).startswith(str(self.workspace)):
            file_path = self.workspace / file_path

        # Create parent directories
        file_path.parent.mkdir(exist_ok=True, parents=True)

        try:
            file_path.write_text(params.get("content", ""))
            return {
                "status": "success",
                "path": str(file_path),
                "message": f"Written to {file_path}"
            }
        except Exception as e:
            return {"error": str(e)}

    def list_directory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List files in a directory"""

        dir_path = Path(params.get("path", "."))

        # Ensure within workspace
        if not str(dir_path).startswith(str(self.workspace)):
            dir_path = self.workspace / dir_path

        if not dir_path.exists():
            return {"error": f"Directory not found: {dir_path}"}

        try:
            files = [str(f.relative_to(self.workspace)) for f in dir_path.iterdir()]
            return {
                "status": "success",
                "path": str(dir_path),
                "files": files
            }
        except Exception as e:
            return {"error": str(e)}

    def handle_tool_call(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Route tool calls to appropriate methods"""

        handlers = {
            "read_file": self.read_file,
            "write_file": self.write_file,
            "list_directory": self.list_directory,
        }

        if tool_name in handlers:
            return handlers[tool_name](params)
        else:
            return {"error": f"Unknown tool: {tool_name}"}


def main():
    """Run MCP server"""

    server = FilesystemServer()

    # Simple stdio-based MCP protocol
    for line in sys.stdin:
        try:
            request = json.loads(line)
            tool_name = request.get("tool")
            params = request.get("params", {})

            result = server.handle_tool_call(tool_name, params)

            response = {
                "status": "success",
                "result": result
            }

            print(json.dumps(response), flush=True)

        except Exception as e:
            error_response = {
                "status": "error",
                "error": str(e)
            }
            print(json.dumps(error_response), flush=True)


if __name__ == "__main__":
    main()
