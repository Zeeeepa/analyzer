"""
Permission System Module

Inspired by OpenCode's permission implementation with once/always/reject pattern.
Provides user consent mechanism for sensitive agent operations.

Features:
1. Three-state permission model: once, always, reject
2. Wildcard pattern matching for flexible permission grouping
3. Session-based approval caching
4. Integration with UI callbacks for user interaction
5. Granular permission types (bash, file_edit, web_access, etc.)

Usage:
    manager = PermissionManager(ui_callback=my_prompt_function)

    # Request permission
    allowed, response = await manager.ask(
        permission_type='bash',
        tool_name='git push',
        args={'command': 'git push origin main'},
        metadata={'repo': '/path/to/repo'}
    )

    if allowed:
        # Execute operation
        pass
    else:
        # Operation rejected
        raise RejectedError(f"User rejected: {tool_name}")
"""

import asyncio
import fnmatch
import uuid
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable, Tuple, List, Set
from enum import Enum
from loguru import logger


class PermissionType(Enum):
    """Types of permissions that can be requested."""
    BASH = "bash"
    FILE_EDIT = "file_edit"
    FILE_DELETE = "file_delete"
    WEB_ACCESS = "web_access"
    EXTERNAL_DIRECTORY = "external_directory"
    DOOM_LOOP = "doom_loop"
    DESTRUCTIVE = "destructive"  # git push --force, rm -rf, etc.
    SENSITIVE_DATA = "sensitive_data"  # .env, credentials, etc.


# Patterns that should ALWAYS be blocked (security/destructive)
BLOCKED_PATTERNS = [
    # Destructive file operations
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "rm -rf .",
    "> /dev/sda",
    "mkfs.",
    "dd if=",
    ":(){:|:&};:",  # Fork bomb

    # Hacking/security tools
    "nmap ",
    "nikto ",
    "sqlmap ",
    "metasploit",
    "msfconsole",
    "hydra ",
    "john ",
    "hashcat ",
    "aircrack",
    "burpsuite",
    "wireshark",

    # Credential theft
    "cat /etc/shadow",
    "cat /etc/passwd",
    "mimikatz",
    "lazagne",
    "credential",

    # Network attacks
    "arpspoof",
    "ettercap",
    "bettercap",
    "tcpdump -w",

    # Privilege escalation
    "sudo su -",
    "chmod 777 /",
    "chown -R",
]

# File patterns that should never be deleted
PROTECTED_FILES = [
    ".env",
    ".git/",
    "node_modules/",
    "__pycache__/",
    ".ssh/",
    "id_rsa",
    "credentials",
    "secrets",
    ".aws/",
    ".kube/",
]


def is_blocked_command(command: str) -> tuple[bool, str]:
    """
    Check if a command matches blocked patterns.

    Args:
        command: The bash command to check

    Returns:
        (is_blocked, reason) tuple
    """
    command_lower = command.lower()

    for pattern in BLOCKED_PATTERNS:
        if pattern.lower() in command_lower:
            return True, f"Command contains blocked pattern: {pattern}"

    return False, ""


def is_protected_path(path: str) -> tuple[bool, str]:
    """
    Check if a file path is protected from deletion.

    Args:
        path: The file path to check

    Returns:
        (is_protected, reason) tuple
    """
    path_lower = path.lower()

    for protected in PROTECTED_FILES:
        if protected.lower() in path_lower:
            return True, f"Path contains protected pattern: {protected}"

    return False, ""


class PermissionResponse(Enum):
    """User's response to permission request."""
    ONCE = "once"  # Allow this one time
    ALWAYS = "always"  # Allow for entire session
    REJECT = "reject"  # Deny this operation


@dataclass
class PermissionRequest:
    """Represents a pending permission request."""
    request_id: str
    permission_type: PermissionType
    tool_name: str
    args: Dict[str, Any]
    metadata: Dict[str, Any]
    pattern: str  # Computed pattern for matching
    timestamp: float = field(default_factory=lambda: asyncio.get_event_loop().time())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            'request_id': self.request_id,
            'permission_type': self.permission_type.value,
            'tool_name': self.tool_name,
            'args': self.args,
            'metadata': self.metadata,
            'pattern': self.pattern,
            'timestamp': self.timestamp
        }


@dataclass
class ApprovedPermission:
    """Represents an approved permission pattern."""
    permission_type: PermissionType
    pattern: str  # Wildcard pattern (e.g., "bash:git *", "file_edit:/path/to/dir/*")
    granted_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())

    def matches(self, permission_type: PermissionType, check_pattern: str) -> bool:
        """Check if this approval matches a given pattern."""
        if self.permission_type != permission_type:
            return False

        # Exact match
        if self.pattern == check_pattern:
            return True

        # Wildcard match
        return fnmatch.fnmatch(check_pattern, self.pattern)


class RejectedError(Exception):
    """Raised when user rejects a permission request."""

    def __init__(self, message: str, context: Dict[str, Any] = None):
        super().__init__(message)
        self.context = context or {}


class PermissionManager:
    """
    Manages permission requests and approvals with once/always/reject pattern.

    Inspired by OpenCode's permission system:
    - "once" - Allow single operation
    - "always" - Cache approval for session (wildcard pattern)
    - "reject" - Deny operation

    Sources:
    - https://opencode.ai/docs/permissions/
    - https://deepwiki.com/sst/opencode/5.2-permission-system
    """

    def __init__(
        self,
        ui_callback: Optional[Callable] = None,
        auto_approve: bool = False,
        default_mode: str = "ask"
    ):
        """
        Initialize permission manager.

        Args:
            ui_callback: Async function to prompt user for permission
                         Should return PermissionResponse enum value
            auto_approve: If True, auto-approve all requests (DANGEROUS - testing only)
            default_mode: Default permission mode ("ask", "allow", "deny")
        """
        self.ui_callback = ui_callback
        self.auto_approve = auto_approve
        self.default_mode = default_mode

        # Pending permission requests awaiting user response
        self.pending: Dict[str, PermissionRequest] = {}

        # Approved patterns for this session (wildcard support)
        self.approved: List[ApprovedPermission] = []

        # Rejected patterns (to avoid re-asking)
        self.rejected: Set[str] = set()

        # Permission configuration per type
        # PHILOSOPHY: Allow everything by default like Claude Code with --dangerously-skip-permissions
        # ONLY block: deletions and security-sensitive operations (hacking, credentials)
        self.config: Dict[PermissionType, str] = {
            PermissionType.BASH: "allow",           # Allow all bash commands
            PermissionType.FILE_EDIT: "allow",      # Allow all file edits
            PermissionType.FILE_DELETE: "deny",     # BLOCK: Never auto-delete files
            PermissionType.WEB_ACCESS: "allow",     # Allow web access
            PermissionType.EXTERNAL_DIRECTORY: "allow",  # Allow external dirs
            PermissionType.DOOM_LOOP: "allow",      # Allow doom loop override
            PermissionType.DESTRUCTIVE: "deny",     # BLOCK: rm -rf, force push, etc.
            PermissionType.SENSITIVE_DATA: "allow",  # Allow: needed for login automation
        }

        logger.info(f"[PERMISSION] Manager initialized (auto_approve={auto_approve}, default={default_mode})")

    def _compute_pattern(
        self,
        permission_type: PermissionType,
        tool_name: str,
        args: Dict[str, Any]
    ) -> str:
        """
        Compute a pattern string for permission matching.

        Patterns are used for wildcard matching (e.g., "bash:git *" matches "bash:git push").

        Args:
            permission_type: Type of permission
            tool_name: Name of the tool/command
            args: Tool arguments

        Returns:
            Pattern string like "bash:git push" or "file_edit:/path/to/file.txt"
        """
        base = f"{permission_type.value}:{tool_name}"

        # Add specific args to pattern based on permission type
        if permission_type == PermissionType.BASH:
            # For bash commands, include the command itself
            command = args.get('command', '')
            if command:
                base = f"{permission_type.value}:{command}"

        elif permission_type in [PermissionType.FILE_EDIT, PermissionType.FILE_DELETE]:
            # For file operations, include the file path
            file_path = args.get('file_path', args.get('path', ''))
            if file_path:
                base = f"{permission_type.value}:{file_path}"

        elif permission_type == PermissionType.EXTERNAL_DIRECTORY:
            # For directory access, include the directory path
            directory = args.get('directory', args.get('path', ''))
            if directory:
                base = f"{permission_type.value}:{directory}"

        return base

    def _get_wildcard_pattern(self, pattern: str) -> str:
        """
        Generate a wildcard pattern for "always" approvals.

        Examples:
            "bash:git push origin main" -> "bash:git *"
            "file_edit:/path/to/specific/file.txt" -> "file_edit:/path/to/specific/*"
            "file_delete:/home/user/test.txt" -> "file_delete:/home/user/*"

        Args:
            pattern: Specific pattern from request

        Returns:
            Wildcard pattern for broader matching
        """
        parts = pattern.split(':')
        if len(parts) != 2:
            return pattern

        perm_type, target = parts

        # For bash commands, wildcard the subcommand
        if perm_type == "bash":
            # "git push origin main" -> "git *"
            command_parts = target.split()
            if len(command_parts) > 1:
                return f"{perm_type}:{command_parts[0]} *"

        # For file paths, wildcard the filename but keep directory
        elif perm_type in ["file_edit", "file_delete", "external_directory"]:
            # "/path/to/file.txt" -> "/path/to/*"
            if '/' in target:
                dir_path = target.rsplit('/', 1)[0]
                return f"{perm_type}:{dir_path}/*"

        return pattern

    def is_approved(self, permission_type: PermissionType, pattern: str) -> bool:
        """
        Check if a permission pattern is already approved.

        Args:
            permission_type: Type of permission
            pattern: Pattern to check (e.g., "bash:git push")

        Returns:
            True if approved, False otherwise
        """
        for approval in self.approved:
            if approval.matches(permission_type, pattern):
                logger.debug(f"[PERMISSION] Auto-approved via pattern: {approval.pattern}")
                return True
        return False

    def is_rejected(self, pattern: str) -> bool:
        """
        Check if a pattern was previously rejected.

        Args:
            pattern: Pattern to check

        Returns:
            True if rejected, False otherwise
        """
        return pattern in self.rejected

    async def ask(
        self,
        permission_type: str | PermissionType,
        tool_name: str,
        args: Dict[str, Any],
        metadata: Dict[str, Any] = None
    ) -> Tuple[bool, Optional[PermissionResponse]]:
        """
        Request permission from user. Returns immediately if already approved.

        Flow:
        1. Check if permission type is configured to auto-allow/deny
        2. Compute pattern and check cached approvals
        3. Check if previously rejected
        4. If none of above, prompt user via callback
        5. Cache decision based on response (once/always/reject)

        Args:
            permission_type: Type of permission (str or PermissionType enum)
            tool_name: Name of tool requesting permission
            args: Tool arguments
            metadata: Additional context for user display

        Returns:
            Tuple of (allowed: bool, response: PermissionResponse)

        Raises:
            ValueError: If ui_callback is required but not set
        """
        # Convert string to enum if needed
        if isinstance(permission_type, str):
            try:
                permission_type = PermissionType(permission_type)
            except ValueError:
                logger.warning(f"[PERMISSION] Unknown permission type: {permission_type}, using BASH")
                permission_type = PermissionType.BASH

        metadata = metadata or {}

        # Check configuration for this permission type
        mode = self.config.get(permission_type, self.default_mode)

        if mode == "allow":
            logger.debug(f"[PERMISSION] Auto-allowed by config: {permission_type.value}")
            return True, PermissionResponse.ALWAYS

        if mode == "deny":
            logger.warning(f"[PERMISSION] Auto-denied by config: {permission_type.value}")
            return False, PermissionResponse.REJECT

        # Auto-approve mode (testing only)
        if self.auto_approve:
            logger.debug(f"[PERMISSION] Auto-approved (testing mode): {permission_type.value}:{tool_name}")
            return True, PermissionResponse.ALWAYS

        # Compute pattern for matching
        pattern = self._compute_pattern(permission_type, tool_name, args)

        # Check if already approved
        if self.is_approved(permission_type, pattern):
            return True, PermissionResponse.ALWAYS

        # Check if previously rejected
        if self.is_rejected(pattern):
            logger.warning(f"[PERMISSION] Previously rejected: {pattern}")
            return False, PermissionResponse.REJECT

        # Need to ask user
        if not self.ui_callback:
            # No callback set - default to deny for safety
            logger.warning(f"[PERMISSION] No UI callback set, denying: {pattern}")
            return False, PermissionResponse.REJECT

        # Create permission request
        request_id = str(uuid.uuid4())
        request = PermissionRequest(
            request_id=request_id,
            permission_type=permission_type,
            tool_name=tool_name,
            args=args,
            metadata=metadata,
            pattern=pattern
        )

        self.pending[request_id] = request

        try:
            # Call UI callback to prompt user
            logger.info(f"[PERMISSION] Requesting permission: {pattern}")
            response = await self.ui_callback(request)

            # Process response
            return await self.respond(request_id, response)

        except Exception as e:
            logger.error(f"[PERMISSION] Error prompting user: {e}")
            # On error, deny for safety
            self.pending.pop(request_id, None)
            return False, PermissionResponse.REJECT

    async def respond(
        self,
        request_id: str,
        response: str | PermissionResponse
    ) -> Tuple[bool, PermissionResponse]:
        """
        Handle user response to permission request.

        Args:
            request_id: ID of the pending request
            response: User's response (once/always/reject or enum)

        Returns:
            Tuple of (allowed: bool, response: PermissionResponse)

        Raises:
            ValueError: If request_id not found
        """
        # Convert string to enum if needed
        if isinstance(response, str):
            try:
                response = PermissionResponse(response.lower())
            except ValueError:
                logger.warning(f"[PERMISSION] Invalid response: {response}, treating as reject")
                response = PermissionResponse.REJECT

        # Get pending request
        request = self.pending.pop(request_id, None)
        if not request:
            raise ValueError(f"Permission request {request_id} not found")

        logger.info(f"[PERMISSION] User responded '{response.value}' to: {request.pattern}")

        # Process response
        if response == PermissionResponse.REJECT:
            # Add to rejected set
            self.rejected.add(request.pattern)
            return False, response

        elif response == PermissionResponse.ONCE:
            # Allow this one time only (no caching)
            return True, response

        elif response == PermissionResponse.ALWAYS:
            # Cache approval with wildcard pattern
            wildcard_pattern = self._get_wildcard_pattern(request.pattern)
            approval = ApprovedPermission(
                permission_type=request.permission_type,
                pattern=wildcard_pattern
            )
            self.approved.append(approval)
            logger.success(f"[PERMISSION] Cached approval pattern: {wildcard_pattern}")
            return True, response

        else:
            # Unknown response, deny for safety
            logger.warning(f"[PERMISSION] Unknown response: {response}")
            return False, PermissionResponse.REJECT

    def clear_session_approvals(self):
        """Clear all session approvals (for new session)."""
        count = len(self.approved)
        self.approved.clear()
        self.rejected.clear()
        logger.info(f"[PERMISSION] Cleared {count} session approvals")

    def set_config(self, permission_type: PermissionType, mode: str):
        """
        Set configuration for a permission type.

        Args:
            permission_type: Type of permission
            mode: Permission mode ("ask", "allow", "deny")
        """
        if mode not in ["ask", "allow", "deny"]:
            raise ValueError(f"Invalid mode: {mode}. Must be 'ask', 'allow', or 'deny'")

        self.config[permission_type] = mode
        logger.info(f"[PERMISSION] Set {permission_type.value} mode to '{mode}'")

    def get_pending_requests(self) -> List[PermissionRequest]:
        """Get list of pending permission requests."""
        return list(self.pending.values())

    def get_approved_patterns(self) -> List[str]:
        """Get list of approved patterns."""
        return [f"{a.permission_type.value}:{a.pattern}" for a in self.approved]

    def get_rejected_patterns(self) -> List[str]:
        """Get list of rejected patterns."""
        return list(self.rejected)

    def export_state(self) -> Dict[str, Any]:
        """
        Export current state for persistence.

        Returns:
            Dict with pending, approved, rejected, and config
        """
        return {
            'pending': [req.to_dict() for req in self.pending.values()],
            'approved': [
                {
                    'permission_type': a.permission_type.value,
                    'pattern': a.pattern,
                    'granted_at': a.granted_at
                }
                for a in self.approved
            ],
            'rejected': list(self.rejected),
            'config': {k.value: v for k, v in self.config.items()}
        }

    def import_state(self, state: Dict[str, Any]):
        """
        Import state from persistence.

        Args:
            state: Dict from export_state()
        """
        # Import approved patterns
        self.approved = [
            ApprovedPermission(
                permission_type=PermissionType(a['permission_type']),
                pattern=a['pattern'],
                granted_at=a.get('granted_at', 0.0)
            )
            for a in state.get('approved', [])
        ]

        # Import rejected patterns
        self.rejected = set(state.get('rejected', []))

        # Import config
        for perm_type_str, mode in state.get('config', {}).items():
            try:
                perm_type = PermissionType(perm_type_str)
                self.config[perm_type] = mode
            except ValueError:
                logger.warning(f"[PERMISSION] Unknown permission type in config: {perm_type_str}")

        logger.info(f"[PERMISSION] Imported state: {len(self.approved)} approved, {len(self.rejected)} rejected")


# Global instance (singleton pattern)
_permission_manager: Optional[PermissionManager] = None


def get_permission_manager(
    ui_callback: Optional[Callable] = None,
    auto_approve: bool = False
) -> PermissionManager:
    """
    Get or create the global PermissionManager instance.

    Args:
        ui_callback: UI callback for prompting user (only used on first call)
        auto_approve: Auto-approve mode (only used on first call)

    Returns:
        Global PermissionManager instance
    """
    global _permission_manager
    if _permission_manager is None:
        _permission_manager = PermissionManager(
            ui_callback=ui_callback,
            auto_approve=auto_approve
        )
    return _permission_manager


def reset_permission_manager():
    """Reset the global permission manager (for testing)."""
    global _permission_manager
    _permission_manager = None
