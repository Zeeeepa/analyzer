"""
LSP Client for code intelligence features.

Provides completions, hover info, definitions, references, and diagnostics
by connecting to local language servers via JSON-RPC protocol.
"""

import asyncio
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class Language(Enum):
    """Supported programming languages."""
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    TSX = "tsx"
    JSX = "jsx"


@dataclass
class LSPServerConfig:
    """Configuration for a language server."""
    command: List[str]
    languages: List[Language]
    name: str
    initialization_options: Optional[Dict[str, Any]] = None


# Language server configurations
LSP_SERVERS = {
    "pyright": LSPServerConfig(
        command=["pyright-langserver", "--stdio"],
        languages=[Language.PYTHON],
        name="pyright"
    ),
    "pylsp": LSPServerConfig(
        command=["pylsp"],
        languages=[Language.PYTHON],
        name="pylsp"
    ),
    "typescript-language-server": LSPServerConfig(
        command=["typescript-language-server", "--stdio"],
        languages=[Language.TYPESCRIPT, Language.JAVASCRIPT, Language.TSX, Language.JSX],
        name="typescript-language-server"
    ),
}


class LSPClient:
    """
    Language Server Protocol client for code intelligence.

    Connects to language servers and provides IDE-like features:
    - Code completions
    - Hover documentation
    - Go to definition
    - Find references
    - Diagnostics (errors/warnings)
    """

    def __init__(self, timeout: int = 10):
        """
        Initialize LSP client.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.process: Optional[subprocess.Popen] = None
        self.message_id = 0
        self.initialized = False
        self.server_config: Optional[LSPServerConfig] = None
        self.root_uri: Optional[str] = None
        self.diagnostics_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._response_queue: Dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None

    def _get_next_id(self) -> int:
        """Get next message ID."""
        self.message_id += 1
        return self.message_id

    def _detect_language(self, file_path: str) -> Optional[Language]:
        """
        Detect language from file extension.

        Args:
            file_path: Path to file

        Returns:
            Language enum or None if unknown
        """
        ext = Path(file_path).suffix.lower()

        ext_map = {
            ".py": Language.PYTHON,
            ".ts": Language.TYPESCRIPT,
            ".tsx": Language.TSX,
            ".js": Language.JAVASCRIPT,
            ".jsx": Language.JSX,
        }

        return ext_map.get(ext)

    def _detect_server(self, language: Language) -> Optional[LSPServerConfig]:
        """
        Detect available language server for language.

        Args:
            language: Programming language

        Returns:
            Server config or None if not found
        """
        # Preferred servers per language
        preferences = {
            Language.PYTHON: ["pyright", "pylsp"],
            Language.TYPESCRIPT: ["typescript-language-server"],
            Language.JAVASCRIPT: ["typescript-language-server"],
            Language.TSX: ["typescript-language-server"],
            Language.JSX: ["typescript-language-server"],
        }

        for server_name in preferences.get(language, []):
            config = LSP_SERVERS.get(server_name)
            if config and self._is_server_installed(config):
                return config

        return None

    def _is_server_installed(self, config: LSPServerConfig) -> bool:
        """
        Check if language server is installed.

        Args:
            config: Server configuration

        Returns:
            True if installed
        """
        try:
            subprocess.run(
                [config.command[0], "--version"],
                capture_output=True,
                timeout=2
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _path_to_uri(self, path: str) -> str:
        """
        Convert file path to URI.

        Args:
            path: File path

        Returns:
            File URI
        """
        abs_path = os.path.abspath(path)
        # Handle Windows paths
        if os.name == 'nt':
            abs_path = abs_path.replace('\\', '/')
            if abs_path[1] == ':':
                abs_path = '/' + abs_path
        return f"file://{abs_path}"

    def _uri_to_path(self, uri: str) -> str:
        """
        Convert URI to file path.

        Args:
            uri: File URI

        Returns:
            File path
        """
        if uri.startswith("file://"):
            path = uri[7:]
            # Handle Windows paths
            if os.name == 'nt' and path.startswith('/') and path[2] == ':':
                path = path[1:]
            return path.replace('/', os.sep)
        return uri

    async def _send_message(self, message: Dict[str, Any]) -> None:
        """
        Send JSON-RPC message to server.

        Args:
            message: JSON-RPC message
        """
        if not self.process or not self.process.stdin:
            raise RuntimeError("LSP server not running")

        content = json.dumps(message)
        header = f"Content-Length: {len(content)}\r\n\r\n"

        try:
            self.process.stdin.write((header + content).encode())
            self.process.stdin.flush()
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            raise

    async def _read_message(self) -> Optional[Dict[str, Any]]:
        """
        Read JSON-RPC message from server.

        Returns:
            Parsed message or None on error
        """
        if not self.process or not self.process.stdout:
            return None

        try:
            # Read headers
            headers = {}
            while True:
                line = self.process.stdout.readline().decode().strip()
                if not line:
                    break
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip()] = value.strip()

            # Read content
            content_length = int(headers.get('Content-Length', 0))
            if content_length == 0:
                return None

            content = self.process.stdout.read(content_length).decode()
            return json.loads(content)

        except Exception as e:
            logger.error(f"Failed to read message: {e}")
            return None

    async def _message_reader(self) -> None:
        """Background task to read messages from server."""
        while self.process and self.process.poll() is None:
            try:
                message = await asyncio.wait_for(
                    self._read_message(),
                    timeout=0.1
                )

                if message:
                    await self._handle_message(message)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Message reader error: {e}")
                break

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """
        Handle incoming message from server.

        Args:
            message: JSON-RPC message
        """
        # Handle responses
        if 'id' in message and message['id'] in self._response_queue:
            future = self._response_queue.pop(message['id'])
            if 'error' in message:
                future.set_exception(RuntimeError(message['error']))
            else:
                future.set_result(message.get('result'))

        # Handle notifications
        elif 'method' in message:
            method = message['method']
            params = message.get('params', {})

            if method == 'textDocument/publishDiagnostics':
                uri = params.get('uri')
                diagnostics = params.get('diagnostics', [])
                if uri:
                    self.diagnostics_cache[uri] = diagnostics

    async def _request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Send JSON-RPC request and wait for response.

        Args:
            method: LSP method name
            params: Method parameters

        Returns:
            Response result
        """
        msg_id = self._get_next_id()
        message = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params or {}
        }

        future = asyncio.Future()
        self._response_queue[msg_id] = future

        await self._send_message(message)

        try:
            result = await asyncio.wait_for(future, timeout=self.timeout)
            return result
        except asyncio.TimeoutError:
            self._response_queue.pop(msg_id, None)
            raise TimeoutError(f"Request {method} timed out")

    async def _notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """
        Send JSON-RPC notification (no response expected).

        Args:
            method: LSP method name
            params: Method parameters
        """
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }

        await self._send_message(message)

    async def initialize(
        self,
        root_path: str,
        language: Optional[Language] = None
    ) -> bool:
        """
        Initialize language server for project.

        Args:
            root_path: Project root directory
            language: Programming language (auto-detected if None)

        Returns:
            True if successful
        """
        if self.initialized:
            logger.warning("LSP client already initialized")
            return True

        # Auto-detect language if not specified
        if language is None:
            # Try to detect from common files
            for ext, lang in [(".py", Language.PYTHON), (".ts", Language.TYPESCRIPT)]:
                test_files = list(Path(root_path).rglob(f"*{ext}"))
                if test_files:
                    language = lang
                    break

            if language is None:
                logger.error("Could not auto-detect language")
                return False

        # Detect server
        self.server_config = self._detect_server(language)
        if not self.server_config:
            logger.error(f"No language server found for {language.value}")
            return False

        logger.info(f"Using {self.server_config.name} for {language.value}")

        # Start server process
        try:
            self.process = subprocess.Popen(
                self.server_config.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        except Exception as e:
            logger.error(f"Failed to start language server: {e}")
            return False

        # Start message reader
        self._reader_task = asyncio.create_task(self._message_reader())

        # Send initialize request
        self.root_uri = self._path_to_uri(root_path)

        init_params = {
            "processId": os.getpid(),
            "rootUri": self.root_uri,
            "rootPath": root_path,
            "capabilities": {
                "textDocument": {
                    "completion": {
                        "completionItem": {
                            "snippetSupport": False
                        }
                    },
                    "hover": {
                        "contentFormat": ["plaintext", "markdown"]
                    },
                    "definition": {
                        "linkSupport": False
                    },
                    "references": {},
                    "publishDiagnostics": {}
                }
            }
        }

        if self.server_config.initialization_options:
            init_params["initializationOptions"] = self.server_config.initialization_options

        try:
            result = await self._request("initialize", init_params)
            await self._notify("initialized", {})
            self.initialized = True
            logger.info("LSP server initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize LSP server: {e}")
            await self.shutdown()
            return False

    async def open_document(self, file_path: str) -> bool:
        """
        Notify server that document is open.

        Args:
            file_path: Path to file

        Returns:
            True if successful
        """
        if not self.initialized:
            return False

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            return False

        language = self._detect_language(file_path)
        if not language:
            logger.error(f"Unknown language for {file_path}")
            return False

        uri = self._path_to_uri(file_path)

        await self._notify("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": language.value,
                "version": 1,
                "text": text
            }
        })

        return True

    async def get_completions(
        self,
        file_path: str,
        line: int,
        column: int
    ) -> List[Dict[str, Any]]:
        """
        Get code completions at position.

        Args:
            file_path: Path to file
            line: Line number (0-indexed)
            column: Column number (0-indexed)

        Returns:
            List of completion items
        """
        if not self.initialized:
            return []

        await self.open_document(file_path)

        uri = self._path_to_uri(file_path)

        try:
            result = await self._request("textDocument/completion", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column}
            })

            if isinstance(result, dict) and 'items' in result:
                return result['items']
            elif isinstance(result, list):
                return result

            return []

        except Exception as e:
            logger.error(f"Failed to get completions: {e}")
            return []

    async def get_hover(
        self,
        file_path: str,
        line: int,
        column: int
    ) -> Optional[str]:
        """
        Get hover documentation at position.

        Args:
            file_path: Path to file
            line: Line number (0-indexed)
            column: Column number (0-indexed)

        Returns:
            Documentation string or None
        """
        if not self.initialized:
            return None

        await self.open_document(file_path)

        uri = self._path_to_uri(file_path)

        try:
            result = await self._request("textDocument/hover", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column}
            })

            if not result:
                return None

            contents = result.get('contents')

            if isinstance(contents, str):
                return contents
            elif isinstance(contents, dict):
                return contents.get('value', '')
            elif isinstance(contents, list) and contents:
                if isinstance(contents[0], str):
                    return contents[0]
                elif isinstance(contents[0], dict):
                    return contents[0].get('value', '')

            return None

        except Exception as e:
            logger.error(f"Failed to get hover info: {e}")
            return None

    async def get_definition(
        self,
        file_path: str,
        line: int,
        column: int
    ) -> List[Dict[str, Any]]:
        """
        Get definition location at position.

        Args:
            file_path: Path to file
            line: Line number (0-indexed)
            column: Column number (0-indexed)

        Returns:
            List of definition locations with 'uri', 'range'
        """
        if not self.initialized:
            return []

        await self.open_document(file_path)

        uri = self._path_to_uri(file_path)

        try:
            result = await self._request("textDocument/definition", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column}
            })

            if isinstance(result, dict):
                return [result]
            elif isinstance(result, list):
                return result

            return []

        except Exception as e:
            logger.error(f"Failed to get definition: {e}")
            return []

    async def get_references(
        self,
        file_path: str,
        line: int,
        column: int,
        include_declaration: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Find references at position.

        Args:
            file_path: Path to file
            line: Line number (0-indexed)
            column: Column number (0-indexed)
            include_declaration: Include declaration in results

        Returns:
            List of reference locations with 'uri', 'range'
        """
        if not self.initialized:
            return []

        await self.open_document(file_path)

        uri = self._path_to_uri(file_path)

        try:
            result = await self._request("textDocument/references", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column},
                "context": {
                    "includeDeclaration": include_declaration
                }
            })

            if isinstance(result, list):
                return result

            return []

        except Exception as e:
            logger.error(f"Failed to get references: {e}")
            return []

    async def get_diagnostics(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Get diagnostics (errors/warnings) for file.

        Args:
            file_path: Path to file

        Returns:
            List of diagnostic items with 'severity', 'message', 'range'
        """
        if not self.initialized:
            return []

        await self.open_document(file_path)

        # Wait a bit for diagnostics to arrive
        await asyncio.sleep(0.5)

        uri = self._path_to_uri(file_path)
        return self.diagnostics_cache.get(uri, [])

    async def shutdown(self) -> None:
        """Shutdown language server cleanly."""
        if not self.initialized:
            return

        try:
            # Send shutdown request
            await self._request("shutdown")
            await self._notify("exit")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

        # Stop reader task
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        # Terminate process
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

        self.initialized = False
        self.process = None
        self._response_queue.clear()
        self.diagnostics_cache.clear()

        logger.info("LSP server shutdown complete")


# Test code
async def test_lsp_client():
    """Test LSP client functionality."""
    print("Testing LSP Client")
    print("-" * 50)

    # Create test Python file
    test_dir = Path("/tmp/lsp_test")
    test_dir.mkdir(exist_ok=True)

    test_file = test_dir / "test.py"
    test_file.write_text("""
import os
import sys

def hello_world():
    print("Hello, World!")
    return 42

class MyClass:
    def __init__(self):
        self.value = 10

    def get_value(self):
        return self.value

result = hello_world()
obj = MyClass()
value = obj.get_value()
""")

    client = LSPClient(timeout=5)

    try:
        # Test initialization
        print("\n1. Testing initialization...")
        success = await client.initialize(str(test_dir), Language.PYTHON)
        if success:
            print("   PASSED: Server initialized")
        else:
            print("   SKIPPED: No language server installed")
            print("   Install with: pip install pyright or pip install python-lsp-server")
            return

        # Test completions
        print("\n2. Testing completions...")
        completions = await client.get_completions(str(test_file), 5, 10)
        if completions:
            print(f"   PASSED: Got {len(completions)} completions")
            print(f"   Sample: {completions[0].get('label', 'N/A')}")
        else:
            print("   INFO: No completions (expected for some positions)")

        # Test hover
        print("\n3. Testing hover...")
        hover = await client.get_hover(str(test_file), 4, 5)
        if hover:
            print(f"   PASSED: Got hover info")
            print(f"   Info: {hover[:100]}...")
        else:
            print("   INFO: No hover info (expected for some positions)")

        # Test definition
        print("\n4. Testing go to definition...")
        definitions = await client.get_definition(str(test_file), 15, 10)
        if definitions:
            print(f"   PASSED: Found {len(definitions)} definitions")
            for defn in definitions:
                uri = defn.get('uri', '')
                range_info = defn.get('range', {})
                start = range_info.get('start', {})
                print(f"   Location: {uri}:{start.get('line', 0)}")
        else:
            print("   INFO: No definitions found")

        # Test diagnostics
        print("\n5. Testing diagnostics...")

        # Create file with error
        error_file = test_dir / "error.py"
        error_file.write_text("""
def broken_function():
    x = 1
    y = 2
    return x + z  # Undefined variable
""")

        diagnostics = await client.get_diagnostics(str(error_file))
        if diagnostics:
            print(f"   PASSED: Found {len(diagnostics)} diagnostics")
            for diag in diagnostics:
                severity = diag.get('severity', 0)
                message = diag.get('message', '')
                print(f"   Severity {severity}: {message}")
        else:
            print("   INFO: No diagnostics (may take time to compute)")

        # Test references
        print("\n6. Testing find references...")
        references = await client.get_references(str(test_file), 4, 5)
        if references:
            print(f"   PASSED: Found {len(references)} references")
        else:
            print("   INFO: No references found")

        print("\n" + "=" * 50)
        print("Test completed successfully!")

    finally:
        await client.shutdown()

        # Cleanup
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run test
    asyncio.run(test_lsp_client())
