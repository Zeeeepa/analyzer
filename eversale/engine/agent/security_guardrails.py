"""
Security Guardrails - Deny-by-default security policy.

This module implements comprehensive security controls to prevent:
- Unauthorized file system access
- Credential theft and exposure
- Network security violations
- Arbitrary code execution
- System configuration tampering

Default policy: DENY unless explicitly allowed.
"""

import re
import logging
import time
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
from pathlib import Path
from collections import defaultdict, deque

from agent.workspace_paths import get_workspace_root_path

# Configure logging for security events
logger = logging.getLogger(__name__)


@dataclass
class GuardrailResult:
    """Result of security check."""
    allowed: bool
    reason: str = ""
    category: str = ""
    severity: str = "medium"  # low, medium, high, critical


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    max_requests: int
    time_window: int  # seconds
    operation_type: str


class RateLimiter:
    """Rate limiter for sensitive operations."""

    def __init__(self):
        # Track requests per operation type
        # key: operation_type -> deque of timestamps
        self.requests: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))

        # Rate limit configurations
        self.limits = {
            "credential_access": RateLimitConfig(max_requests=5, time_window=3600, operation_type="credential_access"),
            "file_write": RateLimitConfig(max_requests=50, time_window=60, operation_type="file_write"),
            "file_delete": RateLimitConfig(max_requests=20, time_window=60, operation_type="file_delete"),
            "command_execution": RateLimitConfig(max_requests=100, time_window=60, operation_type="command_execution"),
            "network_request": RateLimitConfig(max_requests=200, time_window=60, operation_type="network_request"),
            "sensitive_file_access": RateLimitConfig(max_requests=10, time_window=3600, operation_type="sensitive_file_access"),
        }

    def check_rate_limit(self, operation_type: str) -> Tuple[bool, str]:
        """
        Check if operation exceeds rate limit.

        Args:
            operation_type: Type of operation being performed

        Returns:
            Tuple of (allowed, reason)
        """
        if operation_type not in self.limits:
            # No rate limit configured for this operation
            return True, ""

        config = self.limits[operation_type]
        current_time = time.time()
        request_times = self.requests[operation_type]

        # Remove requests outside the time window
        while request_times and current_time - request_times[0] > config.time_window:
            request_times.popleft()

        # Check if limit exceeded
        if len(request_times) >= config.max_requests:
            return False, (
                f"Rate limit exceeded for {operation_type}: "
                f"{config.max_requests} requests per {config.time_window} seconds"
            )

        # Record this request
        request_times.append(current_time)
        return True, ""

    def reset(self, operation_type: Optional[str] = None):
        """Reset rate limit counters."""
        if operation_type:
            self.requests[operation_type].clear()
        else:
            self.requests.clear()


# Workspace configuration (auto-detected from repo structure)
WORKSPACE_ROOT = str(get_workspace_root_path())


# CRITICAL: Sensitive system files that should NEVER be accessed
SENSITIVE_FILE_PATTERNS = [
    r"/etc/passwd",
    r"/etc/shadow",
    r"/etc/sudoers",
    r"\.ssh/id_[rd]sa",
    r"\.ssh/id_ed25519",
    r"\.ssh/authorized_keys",
    r"\.aws/credentials",
    r"\.aws/config",
    r"\.env",
    r"\.env\..*",
    r"credentials\.json",
    r"service[-_]account.*\.json",
    r"\.npmrc",
    r"\.pypirc",
    r"\.dockercfg",
    r"\.docker/config\.json",
    r"\.netrc",
    r"\.git-credentials",
    r"\.kube/config",
    r"password.*\.(txt|json|yml|yaml)",
    r"secret.*\.(txt|json|yml|yaml)",
    r"token.*\.(txt|json|yml|yaml)",
    r"/proc/",
    r"/sys/",
    r"/dev/",
    r"\.pgpass",
    r"\.mysql_history",
    r"\.psql_history",
]


# CRITICAL: Dangerous shell commands
DANGEROUS_COMMAND_PATTERNS = [
    (r"\brm\s+-rf\s+/", "recursive_delete_root", "critical"),
    (r"\bdd\s+if=.*of=/dev/", "disk_wipe", "critical"),
    (r"\bmkfs\.", "filesystem_format", "critical"),
    (r"\bchmod\s+777", "excessive_permissions", "high"),
    (r"\bchmod\s+\+s\b", "setuid_bit", "high"),
    (r"\bsudo\s+su\b", "privilege_escalation", "high"),
    (r"\bsudo\s+-i\b", "privilege_escalation", "high"),
    (r"\bsudo\s+bash\b", "privilege_escalation", "high"),
    (r"\bcurl\s+.*\|\s*bash", "pipe_to_shell", "critical"),
    (r"\bwget\s+.*\|\s*bash", "pipe_to_shell", "critical"),
    (r"\beval\s*\(", "arbitrary_eval", "high"),
    (r"\bexec\s*\(", "arbitrary_exec", "high"),
    (r"__import__\s*\(\s*['\"]os['\"]", "dangerous_import", "high"),
    (r":\(\)\s*\{\s*:\|:&\s*\}", "fork_bomb", "critical"),
    (r"\bnc\s+-[el].*\s+-e\s+/bin/", "reverse_shell", "critical"),
    (r"/bin/bash\s+-i\s+.*>&\s+/dev/tcp/", "reverse_shell", "critical"),
    (r"\biptables\s+-F", "firewall_flush", "high"),
    (r"\bufw\s+disable", "firewall_disable", "high"),
    (r"\bsetenforce\s+0", "selinux_disable", "high"),
]


# CRITICAL: Dangerous file operations
DANGEROUS_FILE_OPERATIONS = [
    (r"delete.*(?:/etc/|/bin/|/usr/|/lib/|/boot/|/var/log/)", "system_file_deletion", "critical"),
    (r"rm.*(?:/etc/|/bin/|/usr/|/lib/|/boot/|/var/log/)", "system_file_deletion", "critical"),
    (r"unlink.*(?:/etc/|/bin/|/usr/|/lib/|/boot/)", "system_file_deletion", "critical"),
    (r"write.*(?:/etc/|/bin/|/usr/|/lib/|/boot/)", "system_file_modification", "critical"),
    (r"modify.*(?:/etc/|/bin/|/usr/|/lib/|/boot/)", "system_file_modification", "critical"),
    (r"chmod.*(?:/etc/|/bin/|/usr/|/lib/|/boot/)", "system_file_modification", "high"),
    (r"chown.*(?:/etc/|/bin/|/usr/|/lib/|/boot/)", "system_file_modification", "high"),
]


# CRITICAL: Credential and secret access patterns
CREDENTIAL_ACCESS_PATTERNS = [
    (r"read.*(?:password|credential|api[_-]?key|secret|token)", "credential_read", "high"),
    (r"access.*(?:password|credential|api[_-]?key|secret|token)", "credential_access", "high"),
    (r"extract.*(?:password|credential|api[_-]?key|secret|token)", "credential_extraction", "critical"),
    (r"dump.*(?:password|credential|api[_-]?key|memory)", "credential_dump", "critical"),
    (r"steal.*(?:password|credential|api[_-]?key|secret|token)", "credential_theft", "critical"),
    (r"exfiltrate.*(?:password|credential|data|secret)", "data_exfiltration", "critical"),
    (r"os\.environ.*(?:PASSWORD|SECRET|TOKEN|KEY|CREDENTIAL)", "env_var_access", "high"),
    (r"getenv.*(?:PASSWORD|SECRET|TOKEN|KEY|CREDENTIAL)", "env_var_access", "high"),
]


# CRITICAL: Network security patterns
NETWORK_SECURITY_PATTERNS = [
    (r"connect\s+to\s+(?:ftp|ssh|telnet)://(?!localhost|127\.0\.0\.1)", "untrusted_network", "high"),
    (r"(?:nc|netcat)\s+-l.*-e", "backdoor_listener", "critical"),
    (r"(?:upload|send|transmit).*(?:to|->)\s+(?:\d{1,3}\.){3}\d{1,3}", "data_transmission", "high"),
    (r"(?:scp|sftp|rsync).*(?!localhost|127\.0\.0\.1)", "remote_copy", "medium"),
    (r"socket\.connect\(\s*\(\s*['\"](?!127\.0\.0\.1|localhost)", "socket_connection", "medium"),
]


# COMPREHENSIVE THREAT PATTERNS
# NOTE: These patterns are intentionally broad to prevent bypasses
# They do NOT require specific keywords like "without permission" to trigger

# 1. Hacking and unauthorized access patterns
HACKING_PATTERNS = [
    # General hacking attempts (doesn't require "their" or "target")
    (r"\bhack(?:ing)?\s+(?:into|in|to)\b", "hacking", "critical"),
    (r"\bbreak(?:ing)?\s+into\b", "hacking", "critical"),
    (r"\bcrack(?:ing)?\s+(?:password|login|account|system)", "password_cracking", "critical"),
    (r"\b(?:bruteforce|brute[_\s-]?force)\s+(?:attack|password|login)", "bruteforce", "critical"),
    (r"\bsql\s*injection\b", "sql_injection", "critical"),
    (r"\bxss\s+(?:attack|exploit|vulnerability)", "xss", "critical"),
    (r"\bcsrf\s+(?:attack|exploit|vulnerability)", "csrf", "critical"),
    (r"\brce\s+(?:attack|exploit|vulnerability)", "remote_code_execution", "critical"),
    (r"\b(?:privilege|privesc)\s+escalation\b", "privilege_escalation", "critical"),
    (r"\b(?:bypass|circumvent)\s+(?:authentication|security|protection|firewall)", "security_bypass", "critical"),
    (r"\b(?:zero[_\s-]?day|0day)\s+exploit\b", "zero_day", "critical"),
]

# 2. Malware and malicious software patterns
MALWARE_PATTERNS = [
    (r"\b(?:create|write|build|code|develop|make)\s+(?:a\s+)?(?:virus|malware|trojan|worm|spyware)", "malware_creation", "critical"),
    (r"\b(?:ransomware|crypto[_\s-]?locker|file[_\s-]?encryptor)\b", "ransomware", "critical"),
    (r"\b(?:keylogger|keystroke[_\s-]?logger|key[_\s-]?logger)\b", "keylogger", "critical"),
    (r"\b(?:rootkit|bootkit)\b", "rootkit", "critical"),
    (r"\b(?:backdoor|reverse[_\s-]?shell|bind[_\s-]?shell)\b", "backdoor", "critical"),
    (r"\b(?:rat|remote[_\s-]?access[_\s-]?trojan)\b", "rat", "critical"),
    (r"\b(?:botnet|zombie[_\s-]?network)\b", "botnet", "critical"),
    (r"\b(?:cryptominer|cryptojacker|coin[_\s-]?miner)\b", "cryptominer", "high"),
    (r"\b(?:deploy|spread|distribute|install|infect)\s+(?:malware|virus|trojan)", "malware_distribution", "critical"),
]

# 3. Data theft and exfiltration patterns
DATA_THEFT_PATTERNS = [
    (r"\b(?:steal|theft|extract|exfiltrate|grab)\s+(?:password|credential|login|api[_\s-]?key|secret|token|cookie)", "credential_theft", "critical"),
    (r"\b(?:steal|theft|extract|exfiltrate)\s+(?:data|database|information|files)", "data_theft", "critical"),
    (r"\b(?:dump|scrape|harvest|collect)\s+(?:password|credential|email|user[_\s-]?data)", "data_harvesting", "critical"),
    (r"\b(?:credit[_\s-]?card|payment)\s+(?:theft|steal|skimming)", "payment_theft", "critical"),
    (r"\bidentity\s+theft\b", "identity_theft", "critical"),
    (r"\b(?:session|cookie)\s+(?:hijack|theft|steal)", "session_theft", "critical"),
]

# 4. Social engineering and phishing patterns
PHISHING_PATTERNS = [
    (r"\b(?:create|build|make|setup|set[_\s-]?up)\s+(?:a\s+)?phishing\s+(?:page|site|website|email|campaign)", "phishing", "critical"),
    (r"\b(?:spoof|fake|clone)\s+(?:login|website|page|email)", "spoofing", "critical"),
    (r"\bpretexting\b", "pretexting", "high"),
    (r"\bsocial[_\s-]?engineer(?:ing)?\b", "social_engineering", "high"),
    (r"\bcredential[_\s-]?(?:harvest|phish)", "credential_phishing", "critical"),
]

# 5. Denial of Service patterns
DOS_PATTERNS = [
    (r"\b(?:ddos|dos)\s+(?:attack|tool|script)", "ddos", "critical"),
    (r"\b(?:flood|overwhelm|exhaust)\s+(?:server|website|service|network)", "flooding", "critical"),
    (r"\bsyn\s+flood\b", "syn_flood", "critical"),
    (r"\bslowloris\b", "slowloris", "critical"),
    (r"\b(?:crash|take[_\s-]?down|bring[_\s-]?down)\s+(?:server|website|service)", "service_disruption", "critical"),
]

# 6. Account compromise patterns
ACCOUNT_COMPROMISE_PATTERNS = [
    (r"\b(?:hijack|takeover|take[_\s-]?over|compromise)\s+(?:account|email|profile|session)", "account_takeover", "critical"),
    (r"\b(?:unauthorized|illegal)\s+(?:access|entry|login)", "unauthorized_access", "critical"),
    (r"\bimpersonat(?:e|ion)\s+(?:user|admin|victim)", "impersonation", "critical"),
]

# 7. Network attack patterns
NETWORK_ATTACK_PATTERNS = [
    (r"\b(?:man[_\s-]?in[_\s-]?the[_\s-]?middle|mitm)\s+attack\b", "mitm", "critical"),
    (r"\barp\s+(?:spoofing|poison)", "arp_spoofing", "critical"),
    (r"\bdns\s+(?:spoofing|poison)", "dns_spoofing", "critical"),
    (r"\bpacket\s+(?:sniff(?:ing)?|intercept(?:ing)?|capture|capturing)\b", "packet_sniffing", "high"),
    (r"\bport\s+scan(?:ning)?\b", "port_scanning", "medium"),
]

# 8. Unauthorized actions (doesn't require specific victim pronouns)
UNAUTHORIZED_PATTERNS = [
    (r"\b(?:unauthorized|illegal|unlawful|malicious)\s+(?:access|use|modification|deletion)", "unauthorized_action", "critical"),
    (r"\bwithout\s+(?:permission|authorization|consent)", "no_permission", "critical"),
    (r"\b(?:secretly|covertly|stealthily)\s+(?:install|access|monitor|record)", "covert_action", "critical"),
]

# Combine all malicious patterns
BLACKHAT_PATTERNS = (
    HACKING_PATTERNS +
    MALWARE_PATTERNS +
    DATA_THEFT_PATTERNS +
    PHISHING_PATTERNS +
    DOS_PATTERNS +
    ACCOUNT_COMPROMISE_PATTERNS +
    NETWORK_ATTACK_PATTERNS +
    UNAUTHORIZED_PATTERNS
)


# Allowed patterns that override blocks (for legitimate use cases)
# IMPORTANT: These must be very specific to prevent abuse
ALLOWED_OVERRIDE_PATTERNS = [
    (r"(?:ctf|capture[_\s-]?the[_\s-]?flag)\s+(?:competition|challenge|exercise)", "ctf_authorized"),
    (r"authorized\s+penetration\s+test(?:ing)?", "pentest_authorized"),
    (r"bug[_\s-]?bounty\s+program", "bug_bounty_authorized"),
    (r"my\s+own\s+(?:account|system|server|application)", "self_owned"),
    (r"test\s+environment\s+with\s+(?:explicit\s+)?permission", "test_env_authorized"),
]


# DENY-BY-DEFAULT FILE SYSTEM PROTECTION
# Sensitive directories that require explicit whitelisting
SENSITIVE_DIRECTORIES = [
    "/etc",
    "/bin",
    "/sbin",
    "/usr/bin",
    "/usr/sbin",
    "/lib",
    "/lib64",
    "/boot",
    "/sys",
    "/proc",
    "/dev",
    "/root",
    "/var/log",
    "/var/spool",
    "~/.ssh",
    "~/.gnupg",
    "~/.aws",
    "~/.config",
]

# Explicitly allowed file patterns within workspace
ALLOWED_FILE_PATTERNS = [
    r"\.py$",
    r"\.js$",
    r"\.ts$",
    r"\.jsx$",
    r"\.tsx$",
    r"\.json$",
    r"\.yaml$",
    r"\.yml$",
    r"\.md$",
    r"\.txt$",
    r"\.csv$",
    r"\.log$",
    r"\.html$",
    r"\.css$",
    r"\.scss$",
    r"\.sh$",
    r"\.bash$",
    r"\.sql$",
    r"\.xml$",
    r"\.toml$",
    r"\.ini$",
    r"\.cfg$",
    r"\.conf$",
    r"\.gitignore$",
    r"\.dockerignore$",
    r"Dockerfile$",
    r"Makefile$",
    r"README",
    r"LICENSE",
]


class SecurityGuardrails:
    """Security guardrail enforcement with deny-by-default policy."""

    def __init__(self, strict_mode: bool = False):
        """
        Initialize security guardrails.

        Args:
            strict_mode: If True, applies additional restrictions
        """
        self.strict_mode = strict_mode
        self.blocked_actions_log = []
        self.rate_limiter = RateLimiter()

    def check_security(self, prompt: str, context: Optional[dict] = None) -> GuardrailResult:
        """
        Check if a prompt passes security guardrails.

        Default policy: DENY unless explicitly safe.

        Args:
            prompt: The user prompt to check
            context: Optional context with file_path, command, network_target, etc.

        Returns:
            GuardrailResult indicating if action is allowed
        """
        prompt_lower = prompt.lower()
        context = context or {}

        # Check for allowed override patterns (for legitimate security work)
        # NOTE: These are VERY specific to prevent abuse
        for pattern, category in ALLOWED_OVERRIDE_PATTERNS:
            if re.search(pattern, prompt_lower):
                logger.info(f"Security override: {category}")
                return GuardrailResult(
                    allowed=True,
                    reason=f"Allowed for {category}",
                    category=category,
                    severity="low"
                )

        # 1. Check for black hat hacking patterns
        result = self._check_blackhat_patterns(prompt_lower)
        if not result.allowed:
            self._log_blocked_action(prompt, result)
            return result

        # 2. Check file operations (with deny-by-default)
        result = self._check_file_operations(prompt_lower, context)
        if not result.allowed:
            self._log_blocked_action(prompt, result)
            return result

        # 3. Check command execution
        result = self._check_command_execution(prompt_lower, context)
        if not result.allowed:
            self._log_blocked_action(prompt, result)
            return result

        # 4. Check credential access
        result = self._check_credential_access(prompt_lower, context)
        if not result.allowed:
            self._log_blocked_action(prompt, result)
            return result

        # 5. Check network operations
        result = self._check_network_operations(prompt_lower, context)
        if not result.allowed:
            self._log_blocked_action(prompt, result)
            return result

        # 6. Strict mode additional checks
        if self.strict_mode:
            result = self._check_strict_mode(prompt_lower, context)
            if not result.allowed:
                self._log_blocked_action(prompt, result)
                return result

        # If we get here, action is allowed
        logger.info(f"Action allowed: {prompt[:100]}")
        return GuardrailResult(allowed=True, reason="Passed all security checks", category="allowed")

    def _check_blackhat_patterns(self, prompt_lower: str) -> GuardrailResult:
        """Check for malicious hacking patterns."""
        for pattern, category, severity in BLACKHAT_PATTERNS:
            if re.search(pattern, prompt_lower):
                return GuardrailResult(
                    allowed=False,
                    reason=f"Blocked: Malicious hacking attempt ({category})",
                    category=category,
                    severity=severity
                )
        return GuardrailResult(allowed=True)

    def _check_file_operations(self, prompt_lower: str, context: dict) -> GuardrailResult:
        """
        Check file operations for safety with DENY-BY-DEFAULT policy.

        File operations are DENIED unless:
        1. File is within workspace AND
        2. File is not sensitive AND
        3. File extension is allowed AND
        4. Operation passes rate limiting
        """
        file_path = context.get("file_path", "")
        operation = context.get("operation", "access")

        if file_path:
            # DENY: Sensitive file patterns (ALWAYS blocked)
            for pattern in SENSITIVE_FILE_PATTERNS:
                if re.search(pattern, file_path, re.IGNORECASE):
                    return GuardrailResult(
                        allowed=False,
                        reason=f"Blocked: Access to sensitive file: {file_path}",
                        category="sensitive_file_access",
                        severity="critical"
                    )

            # DENY: Sensitive directories (ALWAYS blocked)
            try:
                resolved_path = str(Path(file_path).resolve())
                for sensitive_dir in SENSITIVE_DIRECTORIES:
                    expanded_dir = str(Path(sensitive_dir).expanduser().resolve())
                    if resolved_path.startswith(expanded_dir):
                        return GuardrailResult(
                            allowed=False,
                            reason=f"Blocked: Access to sensitive directory: {sensitive_dir}",
                            category="sensitive_directory_access",
                            severity="critical"
                        )
            except Exception as e:
                # If we can't resolve path, DENY by default
                logger.warning(f"Could not resolve path {file_path}: {e}")
                return GuardrailResult(
                    allowed=False,
                    reason=f"Blocked: Could not verify file path safety: {file_path}",
                    category="path_resolution_failed",
                    severity="high"
                )

            # DENY: Files outside workspace for write/delete/modify/execute
            if not self._is_within_workspace(file_path):
                if operation in ["write", "delete", "modify", "execute"]:
                    return GuardrailResult(
                        allowed=False,
                        reason=f"Blocked: {operation} operation outside workspace: {file_path}",
                        category="out_of_workspace",
                        severity="high"
                    )
                # Read operations outside workspace: allowed but logged
                logger.warning(f"Read operation outside workspace: {file_path}")

            # DENY: Files with disallowed extensions (within workspace)
            if self._is_within_workspace(file_path):
                if not self._is_allowed_file_type(file_path):
                    return GuardrailResult(
                        allowed=False,
                        reason=f"Blocked: File type not allowed: {file_path}",
                        category="disallowed_file_type",
                        severity="medium"
                    )

            # Rate limit file operations
            if operation == "write":
                allowed, reason = self.rate_limiter.check_rate_limit("file_write")
                if not allowed:
                    return GuardrailResult(
                        allowed=False,
                        reason=reason,
                        category="rate_limit_exceeded",
                        severity="high"
                    )
            elif operation == "delete":
                allowed, reason = self.rate_limiter.check_rate_limit("file_delete")
                if not allowed:
                    return GuardrailResult(
                        allowed=False,
                        reason=reason,
                        category="rate_limit_exceeded",
                        severity="high"
                    )

        # Check for dangerous file operations in prompt
        for pattern, category, severity in DANGEROUS_FILE_OPERATIONS:
            if re.search(pattern, prompt_lower):
                return GuardrailResult(
                    allowed=False,
                    reason=f"Blocked: Dangerous file operation ({category})",
                    category=category,
                    severity=severity
                )

        return GuardrailResult(allowed=True)

    def _check_command_execution(self, prompt_lower: str, context: dict) -> GuardrailResult:
        """Check shell command execution for safety with rate limiting."""
        command = context.get("command", prompt_lower)

        for pattern, category, severity in DANGEROUS_COMMAND_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                # Rate limit command execution - only when dangerous command detected
                allowed, reason = self.rate_limiter.check_rate_limit("command_execution")
                if not allowed:
                    return GuardrailResult(
                        allowed=False,
                        reason=reason,
                        category="rate_limit_exceeded",
                        severity="high"
                    )

                return GuardrailResult(
                    allowed=False,
                    reason=f"Blocked: Dangerous shell command ({category})",
                    category=category,
                    severity=severity
                )

        return GuardrailResult(allowed=True)

    def _check_credential_access(self, prompt_lower: str, context: dict) -> GuardrailResult:
        """Check for credential and secret access with strict rate limiting."""
        for pattern, category, severity in CREDENTIAL_ACCESS_PATTERNS:
            if re.search(pattern, prompt_lower):
                # Rate limit credential access attempts (very strict) - only when detected
                allowed, reason = self.rate_limiter.check_rate_limit("credential_access")
                if not allowed:
                    return GuardrailResult(
                        allowed=False,
                        reason=reason,
                        category="rate_limit_exceeded",
                        severity="critical"
                    )

                # REMOVED: Bypass for "config" + "workspace" - too permissive
                # Deny ALL credential access attempts by default
                return GuardrailResult(
                    allowed=False,
                    reason=f"Blocked: Credential access attempt ({category})",
                    category=category,
                    severity=severity
                )

        return GuardrailResult(allowed=True)

    def _check_network_operations(self, prompt_lower: str, context: dict) -> GuardrailResult:
        """Check network operations for safety with rate limiting."""
        network_target = context.get("network_target", "")

        # Block connections to unknown/untrusted domains
        if network_target and not self._is_trusted_domain(network_target):
            # Rate limit network requests - only when untrusted domain detected
            allowed, reason = self.rate_limiter.check_rate_limit("network_request")
            if not allowed:
                return GuardrailResult(
                    allowed=False,
                    reason=reason,
                    category="rate_limit_exceeded",
                    severity="high"
                )

            return GuardrailResult(
                allowed=False,
                reason=f"Blocked: Connection to untrusted domain: {network_target}",
                category="untrusted_network",
                severity="high"
            )

        # Check for network security patterns
        for pattern, category, severity in NETWORK_SECURITY_PATTERNS:
            if re.search(pattern, prompt_lower):
                # Rate limit when suspicious network operation detected
                allowed, reason = self.rate_limiter.check_rate_limit("network_request")
                if not allowed:
                    return GuardrailResult(
                        allowed=False,
                        reason=reason,
                        category="rate_limit_exceeded",
                        severity="high"
                    )

                return GuardrailResult(
                    allowed=False,
                    reason=f"Blocked: Unsafe network operation ({category})",
                    category=category,
                    severity=severity
                )

        return GuardrailResult(allowed=True)

    def _check_strict_mode(self, prompt_lower: str, context: dict) -> GuardrailResult:
        """Additional checks when in strict mode."""
        # In strict mode, block ANY file operations outside workspace
        file_path = context.get("file_path", "")
        if file_path and not self._is_within_workspace(file_path):
            return GuardrailResult(
                allowed=False,
                reason=f"Blocked (strict mode): All operations outside workspace blocked",
                category="strict_mode_violation",
                severity="high"
            )

        # In strict mode, block all network operations
        if any(keyword in prompt_lower for keyword in ["connect", "download", "upload", "request", "fetch", "curl", "wget"]):
            if context.get("network_target") or re.search(r"https?://", prompt_lower):
                return GuardrailResult(
                    allowed=False,
                    reason=f"Blocked (strict mode): Network operations disabled",
                    category="strict_mode_network",
                    severity="high"
                )

        # In strict mode, require explicit approval for any code execution
        if any(keyword in prompt_lower for keyword in ["execute", "run", "eval", "exec", "subprocess"]):
            if not context.get("approved", False):
                return GuardrailResult(
                    allowed=False,
                    reason=f"Blocked (strict mode): Code execution requires explicit approval",
                    category="strict_mode_execution",
                    severity="high"
                )

        return GuardrailResult(allowed=True)

    def _is_within_workspace(self, file_path: str) -> bool:
        """Check if a file path is within the workspace."""
        try:
            path = Path(file_path).resolve()
            workspace = Path(WORKSPACE_ROOT).resolve()
            return str(path).startswith(str(workspace))
        except Exception:
            # If we can't determine, deny by default
            return False

    def _is_allowed_file_type(self, file_path: str) -> bool:
        """
        Check if a file type is allowed (deny-by-default).

        Only explicitly whitelisted file extensions are allowed.
        """
        try:
            file_lower = file_path.lower()
            for pattern in ALLOWED_FILE_PATTERNS:
                if re.search(pattern, file_lower):
                    return True
            return False
        except Exception:
            # If we can't determine, deny by default
            return False

    def _is_trusted_domain(self, domain: str) -> bool:
        """Check if a domain is trusted."""
        trusted_domains = [
            "localhost",
            "127.0.0.1",
            "::1",
            "github.com",
            "gitlab.com",
            "pypi.org",
            "npmjs.com",
            "docker.io",
            "hub.docker.com",
        ]

        domain_lower = domain.lower()
        for trusted in trusted_domains:
            if trusted in domain_lower:
                return True

        return False

    def _log_blocked_action(self, prompt: str, result: GuardrailResult):
        """Log blocked actions for security monitoring."""
        log_entry = {
            "prompt": prompt[:200],  # Truncate for logging
            "category": result.category,
            "reason": result.reason,
            "severity": result.severity,
        }
        self.blocked_actions_log.append(log_entry)

        # Log with appropriate severity level
        if result.severity == "critical":
            logger.critical(f"BLOCKED: {result.reason} | Prompt: {prompt[:100]}")
        elif result.severity == "high":
            logger.error(f"BLOCKED: {result.reason} | Prompt: {prompt[:100]}")
        elif result.severity == "medium":
            logger.warning(f"BLOCKED: {result.reason} | Prompt: {prompt[:100]}")
        else:
            logger.info(f"BLOCKED: {result.reason} | Prompt: {prompt[:100]}")

    def get_blocked_actions_report(self) -> List[dict]:
        """Get a report of all blocked actions."""
        return self.blocked_actions_log.copy()


# Global instance for backward compatibility
_default_guardrails = SecurityGuardrails(strict_mode=False)


def check_security(prompt: str, context: Optional[dict] = None) -> GuardrailResult:
    """
    Check if a prompt passes security guardrails.

    Default policy: DENY unless explicitly safe.

    Args:
        prompt: The user prompt to check
        context: Optional context with file_path, command, network_target, etc.

    Returns:
        GuardrailResult indicating if action is allowed
    """
    return _default_guardrails.check_security(prompt, context)


def get_refusal_message(result: GuardrailResult) -> str:
    """Get a user-friendly refusal message."""
    severity_emoji = {
        "critical": "🚨",
        "high": "⛔",
        "medium": "⚠️",
        "low": "ℹ️"
    }

    emoji = severity_emoji.get(result.severity, "🚫")

    return f"""{emoji} **Security Check Failed**

{result.reason}

Severity: {result.severity.upper()}
Category: {result.category}

For legitimate security research (CTFs, authorized penetration testing, bug bounty programs),
please provide context in your request indicating authorization and scope.

For questions about this security policy, please contact your administrator."""
