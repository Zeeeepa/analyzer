"""
Sensitive Data Guard - Protect credentials and secrets from LLM exposure

Based on browser-use's message manager approach, this module ensures that:
1. LLMs NEVER see actual credentials, API keys, passwords, or tokens
2. All sensitive data is replaced with placeholders before sending to LLM
3. Placeholders are unmask only during execution (never in context/messages)
4. Auto-detection of sensitive patterns in content

Architecture:
- SensitiveDataGuard: Main class managing secret registry and masking/unmasking
- Secret placeholders: <secret>name</secret> format (XML-like for clear visibility)
- Pattern-based detection: Regex patterns for common sensitive data types
- Integration point: Mask before LLM, unmask for execution only

Usage:
    guard = SensitiveDataGuard()

    # Register known secrets
    guard.register_secret("gmail_password", "MyP@ssw0rd123")
    guard.register_secret("api_key", "sk-proj-abc123...")

    # Auto-detect and register secrets in text
    guard.auto_register_detected("Login with password: MyP@ssw0rd123")

    # Mask before sending to LLM
    safe_text = guard.mask_content("Login with password: MyP@ssw0rd123")
    # Returns: "Login with password: <secret>gmail_password</secret>"

    # Unmask for execution only (never in LLM context)
    real_text = guard.unmask_content(safe_text)
    # Returns: "Login with password: MyP@ssw0rd123"
"""

import re
import hashlib
from typing import Dict, List, Optional, Tuple, Set, Any
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class SecretPattern:
    """Pattern definition for detecting sensitive data."""
    name: str
    pattern: re.Pattern
    severity: str  # "critical", "high", "medium"
    description: str
    auto_register: bool = True  # Whether to auto-register matches


@dataclass
class RegisteredSecret:
    """A registered secret with metadata."""
    name: str
    value: str
    source: str  # "manual", "auto_detected", "env_var"
    pattern_type: Optional[str] = None
    severity: str = "high"
    masked_count: int = 0  # How many times this secret was masked

    def get_hash(self) -> str:
        """Get a hash of the secret value for tracking."""
        return hashlib.sha256(self.value.encode()).hexdigest()[:12]


class SensitiveDataGuard:
    """
    Protect sensitive data from LLM exposure using secret placeholders.

    Core principle: LLMs should NEVER see actual credentials, only placeholders.
    """

    def __init__(self):
        """Initialize the sensitive data guard."""
        # Map of placeholder name -> RegisteredSecret
        self.secrets: Dict[str, RegisteredSecret] = {}

        # Pattern definitions for auto-detection
        self.patterns: List[SecretPattern] = self._build_detection_patterns()

        # Cache of value -> placeholder name for fast lookup
        self._value_to_name: Dict[str, str] = {}

        # Set of detected but not registered secrets (for logging)
        self._detected_not_registered: Set[str] = set()

        # Statistics
        self.stats = {
            'total_masked': 0,
            'total_unmasked': 0,
            'secrets_registered': 0,
            'auto_detected': 0,
            'pattern_matches': {}
        }

        logger.info("[SENSITIVE_DATA_GUARD] Initialized with deny-by-default secret protection")

    def _build_detection_patterns(self) -> List[SecretPattern]:
        """
        Build regex patterns for detecting sensitive data.

        Returns comprehensive patterns for:
        - API keys (OpenAI, Anthropic, AWS, etc.)
        - Passwords in various contexts
        - Email addresses in auth contexts
        - Tokens and secrets
        - SSH keys
        - Database connection strings
        """
        return [
            # API Keys - Critical severity
            SecretPattern(
                name="openai_api_key",
                pattern=re.compile(r'\b(sk-[a-zA-Z0-9]{32,})\b'),
                severity="critical",
                description="OpenAI API key",
                auto_register=True
            ),
            SecretPattern(
                name="anthropic_api_key",
                pattern=re.compile(r'\b(sk-ant-[a-zA-Z0-9-_]{90,})\b'),
                severity="critical",
                description="Anthropic Claude API key",
                auto_register=True
            ),
            SecretPattern(
                name="aws_access_key",
                pattern=re.compile(r'\b(AKIA[0-9A-Z]{16})\b'),
                severity="critical",
                description="AWS Access Key ID",
                auto_register=True
            ),
            SecretPattern(
                name="aws_secret_key",
                pattern=re.compile(r'\b([A-Za-z0-9/+=]{40})\b'),
                severity="critical",
                description="AWS Secret Access Key (40 chars)",
                auto_register=False  # Too many false positives
            ),
            SecretPattern(
                name="github_token",
                pattern=re.compile(r'\b(gh[ps]_[a-zA-Z0-9]{36,})\b'),
                severity="critical",
                description="GitHub personal access token",
                auto_register=True
            ),
            SecretPattern(
                name="generic_api_key",
                pattern=re.compile(r'\b(api[_-]?key[_-]?[:\s]*[a-zA-Z0-9_\-]{20,})\b', re.IGNORECASE),
                severity="high",
                description="Generic API key pattern",
                auto_register=True
            ),

            # Passwords - High severity
            SecretPattern(
                name="password_in_url",
                pattern=re.compile(r'://[^:@\s]+:([^@\s]+)@'),
                severity="high",
                description="Password in URL/connection string",
                auto_register=True
            ),
            SecretPattern(
                name="password_field",
                pattern=re.compile(r'(?:password|passwd|pwd)["\s:=]+([^\s"\'}{,;]+)', re.IGNORECASE),
                severity="high",
                description="Password in key-value format",
                auto_register=True
            ),
            SecretPattern(
                name="password_env",
                pattern=re.compile(r'(?:PASSWORD|PASSWD|PWD)=([^\s&]+)', re.IGNORECASE),
                severity="high",
                description="Password in environment variable",
                auto_register=True
            ),

            # Tokens - High severity
            SecretPattern(
                name="bearer_token",
                pattern=re.compile(r'\bBearer\s+([a-zA-Z0-9_\-\.=]+)\b'),
                severity="high",
                description="Bearer token",
                auto_register=True
            ),
            SecretPattern(
                name="jwt_token",
                pattern=re.compile(r'\b(eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*)\b'),
                severity="high",
                description="JWT token",
                auto_register=True
            ),
            SecretPattern(
                name="access_token",
                pattern=re.compile(r'\b(access[_-]?token[:\s]+[a-zA-Z0-9_\-\.=]{20,})\b', re.IGNORECASE),
                severity="high",
                description="Access token",
                auto_register=True
            ),

            # SSH Keys - Critical severity
            SecretPattern(
                name="ssh_private_key",
                pattern=re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
                severity="critical",
                description="SSH private key",
                auto_register=True
            ),

            # Database credentials - High severity
            SecretPattern(
                name="postgres_url",
                pattern=re.compile(r'postgres(?:ql)?://[^:]+:([^@]+)@'),
                severity="high",
                description="PostgreSQL connection string with password",
                auto_register=True
            ),
            SecretPattern(
                name="mysql_url",
                pattern=re.compile(r'mysql://[^:]+:([^@]+)@'),
                severity="high",
                description="MySQL connection string with password",
                auto_register=True
            ),
            SecretPattern(
                name="mongodb_url",
                pattern=re.compile(r'mongodb(?:\+srv)?://[^:]+:([^@]+)@'),
                severity="high",
                description="MongoDB connection string with password",
                auto_register=True
            ),

            # Email addresses in auth contexts - Medium severity
            SecretPattern(
                name="email_with_password",
                pattern=re.compile(r'(?:email|username)[\s:=]+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', re.IGNORECASE),
                severity="medium",
                description="Email in auth context",
                auto_register=False  # Only register if near password
            ),

            # Credit card numbers - Critical severity
            SecretPattern(
                name="credit_card",
                pattern=re.compile(r'\b(?:\d{4}[\s-]?){3}\d{4}\b'),
                severity="critical",
                description="Credit card number",
                auto_register=True
            ),

            # Secrets in common formats - High severity
            SecretPattern(
                name="secret_env",
                pattern=re.compile(r'(?:SECRET|TOKEN|KEY)=([^\s&]+)', re.IGNORECASE),
                severity="high",
                description="Secret in environment variable",
                auto_register=True
            ),
        ]

    def register_secret(self, name: str, value: str, source: str = "manual",
                       pattern_type: Optional[str] = None, severity: str = "high") -> bool:
        """
        Register a secret to protect.

        Args:
            name: Unique name for the secret (e.g., "gmail_password", "api_key")
            value: The actual secret value to protect
            source: How this secret was registered ("manual", "auto_detected", "env_var")
            pattern_type: Which pattern detected this (if auto-detected)
            severity: Severity level ("critical", "high", "medium")

        Returns:
            True if registered successfully, False if already exists
        """
        if not value or not isinstance(value, str):
            logger.warning(f"[SENSITIVE_DATA_GUARD] Cannot register empty or non-string secret: {name}")
            return False

        # Don't register very short values (likely false positives)
        if len(value) < 6:
            logger.debug(f"[SENSITIVE_DATA_GUARD] Skipping short value for {name} (< 6 chars)")
            return False

        # Check if already registered
        if name in self.secrets:
            existing = self.secrets[name]
            if existing.value == value:
                logger.debug(f"[SENSITIVE_DATA_GUARD] Secret '{name}' already registered")
                return False
            else:
                logger.warning(f"[SENSITIVE_DATA_GUARD] Updating secret '{name}' with new value")

        # Register the secret
        secret = RegisteredSecret(
            name=name,
            value=value,
            source=source,
            pattern_type=pattern_type,
            severity=severity
        )

        self.secrets[name] = secret
        self._value_to_name[value] = name
        self.stats['secrets_registered'] += 1

        logger.info(
            f"[SENSITIVE_DATA_GUARD] Registered secret '{name}' "
            f"(source={source}, severity={severity}, hash={secret.get_hash()})"
        )

        return True

    def detect_sensitive(self, text: str) -> List[Tuple[str, str, str, str]]:
        """
        Detect potential secrets in text using patterns.

        Args:
            text: Text to scan for sensitive data

        Returns:
            List of (pattern_name, matched_value, severity, description) tuples
        """
        if not text or not isinstance(text, str):
            return []

        detected = []

        for pattern_def in self.patterns:
            matches = pattern_def.pattern.finditer(text)
            for match in matches:
                # Extract the secret value (first group or full match)
                value = match.group(1) if match.groups() else match.group(0)

                # Skip if already registered
                if value in self._value_to_name:
                    continue

                # Skip very short matches
                if len(value) < 6:
                    continue

                detected.append((
                    pattern_def.name,
                    value,
                    pattern_def.severity,
                    pattern_def.description
                ))

                # Update stats
                pattern_name = pattern_def.name
                self.stats['pattern_matches'][pattern_name] = \
                    self.stats['pattern_matches'].get(pattern_name, 0) + 1

        return detected

    def auto_register_detected(self, text: str, context: str = "unknown") -> int:
        """
        Auto-detect and register secrets found in text.

        Args:
            text: Text to scan and register secrets from
            context: Context description for logging (e.g., "login_prompt", "api_response")

        Returns:
            Number of secrets auto-registered
        """
        if not text or not isinstance(text, str):
            return 0

        detected = self.detect_sensitive(text)
        registered_count = 0

        for pattern_name, value, severity, description in detected:
            # Find the pattern definition
            pattern_def = next((p for p in self.patterns if p.name == pattern_name), None)

            # Only register if pattern allows auto-registration
            if pattern_def and pattern_def.auto_register:
                # Generate a unique name
                base_name = pattern_name
                suffix = 1
                name = base_name

                while name in self.secrets:
                    name = f"{base_name}_{suffix}"
                    suffix += 1

                # Register the secret
                if self.register_secret(
                    name=name,
                    value=value,
                    source="auto_detected",
                    pattern_type=pattern_name,
                    severity=severity
                ):
                    registered_count += 1
                    self.stats['auto_detected'] += 1
                    logger.info(
                        f"[SENSITIVE_DATA_GUARD] Auto-registered '{name}' from {context} "
                        f"(pattern={pattern_name}, severity={severity})"
                    )
            else:
                # Log but don't register
                self._detected_not_registered.add(f"{pattern_name}: {value[:20]}...")
                logger.debug(
                    f"[SENSITIVE_DATA_GUARD] Detected but not auto-registered: "
                    f"{pattern_name} in {context}"
                )

        return registered_count

    def mask_content(self, text: str) -> str:
        """
        Replace actual secret values with placeholders.

        This should be called BEFORE sending any content to the LLM.

        Args:
            text: Text containing potential secrets

        Returns:
            Text with secrets replaced by <secret>name</secret> placeholders
        """
        if not text or not isinstance(text, str):
            return text

        masked_text = text
        masked_count = 0

        # Sort secrets by length (longest first) to avoid partial replacements
        sorted_secrets = sorted(
            self.secrets.items(),
            key=lambda x: len(x[1].value),
            reverse=True
        )

        for name, secret in sorted_secrets:
            # Escape special regex characters in the secret value
            escaped_value = re.escape(secret.value)

            # Count occurrences before masking
            count = len(re.findall(escaped_value, masked_text))

            if count > 0:
                # Replace with placeholder
                placeholder = f"<secret>{name}</secret>"
                masked_text = re.sub(escaped_value, placeholder, masked_text)

                # Update stats
                secret.masked_count += count
                masked_count += count
                self.stats['total_masked'] += count

                logger.debug(
                    f"[SENSITIVE_DATA_GUARD] Masked {count} occurrence(s) of '{name}' "
                    f"(severity={secret.severity})"
                )

        if masked_count > 0:
            logger.info(
                f"[SENSITIVE_DATA_GUARD] Masked {masked_count} secret(s) before LLM exposure"
            )

        return masked_text

    def unmask_content(self, text: str) -> str:
        """
        Replace placeholders with actual secret values.

        This should ONLY be called during execution, NEVER when preparing LLM context.

        Args:
            text: Text containing <secret>name</secret> placeholders

        Returns:
            Text with placeholders replaced by actual secret values
        """
        if not text or not isinstance(text, str):
            return text

        unmasked_text = text
        unmasked_count = 0

        # Find all placeholders in the text
        placeholder_pattern = re.compile(r'<secret>([^<]+)</secret>')
        matches = placeholder_pattern.finditer(text)

        for match in matches:
            name = match.group(1)

            if name in self.secrets:
                secret = self.secrets[name]
                placeholder = match.group(0)

                # Replace placeholder with actual value
                unmasked_text = unmasked_text.replace(placeholder, secret.value)
                unmasked_count += 1
                self.stats['total_unmasked'] += 1

                logger.debug(
                    f"[SENSITIVE_DATA_GUARD] Unmasked placeholder for '{name}' "
                    f"(severity={secret.severity})"
                )
            else:
                logger.warning(
                    f"[SENSITIVE_DATA_GUARD] Unknown secret placeholder: {name}"
                )

        if unmasked_count > 0:
            logger.info(
                f"[SENSITIVE_DATA_GUARD] Unmasked {unmasked_count} secret(s) for execution"
            )

        return unmasked_text

    def has_placeholders(self, text: str) -> bool:
        """
        Check if text contains any secret placeholders.

        Args:
            text: Text to check

        Returns:
            True if text contains <secret>...</secret> placeholders
        """
        if not text or not isinstance(text, str):
            return False

        return bool(re.search(r'<secret>[^<]+</secret>', text))

    def get_placeholder_names(self, text: str) -> List[str]:
        """
        Extract all secret placeholder names from text.

        Args:
            text: Text containing placeholders

        Returns:
            List of secret names found in placeholders
        """
        if not text or not isinstance(text, str):
            return []

        placeholder_pattern = re.compile(r'<secret>([^<]+)</secret>')
        matches = placeholder_pattern.findall(text)

        return list(set(matches))

    def remove_secret(self, name: str) -> bool:
        """
        Remove a registered secret.

        Args:
            name: Name of the secret to remove

        Returns:
            True if removed, False if not found
        """
        if name in self.secrets:
            secret = self.secrets[name]
            del self.secrets[name]

            # Remove from value lookup cache
            if secret.value in self._value_to_name:
                del self._value_to_name[secret.value]

            logger.info(f"[SENSITIVE_DATA_GUARD] Removed secret '{name}'")
            return True

        return False

    def clear_secrets(self):
        """Clear all registered secrets."""
        count = len(self.secrets)
        self.secrets.clear()
        self._value_to_name.clear()
        self._detected_not_registered.clear()

        logger.info(f"[SENSITIVE_DATA_GUARD] Cleared {count} registered secret(s)")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about secret protection.

        Returns:
            Dict with stats including:
            - total_masked: Total number of secret occurrences masked
            - total_unmasked: Total number of placeholders unmasked
            - secrets_registered: Number of secrets currently registered
            - auto_detected: Number of auto-detected secrets
            - pattern_matches: Dict of pattern_name -> match_count
        """
        return {
            **self.stats,
            'secrets_registered': len(self.secrets),
            'secrets_by_severity': {
                'critical': len([s for s in self.secrets.values() if s.severity == 'critical']),
                'high': len([s for s in self.secrets.values() if s.severity == 'high']),
                'medium': len([s for s in self.secrets.values() if s.severity == 'medium']),
            }
        }

    def get_registered_secrets_info(self) -> List[Dict[str, Any]]:
        """
        Get information about registered secrets (without exposing values).

        Returns:
            List of dicts with secret metadata (name, source, severity, etc.)
        """
        return [
            {
                'name': name,
                'source': secret.source,
                'pattern_type': secret.pattern_type,
                'severity': secret.severity,
                'masked_count': secret.masked_count,
                'value_hash': secret.get_hash(),
                'value_length': len(secret.value),
            }
            for name, secret in self.secrets.items()
        ]


# Global instance
_global_guard: Optional[SensitiveDataGuard] = None


def get_sensitive_data_guard() -> SensitiveDataGuard:
    """
    Get or create the global SensitiveDataGuard instance.

    Returns:
        SensitiveDataGuard instance
    """
    global _global_guard
    if _global_guard is None:
        _global_guard = SensitiveDataGuard()
    return _global_guard


def reset_sensitive_data_guard():
    """Reset the global guard instance (useful for testing)."""
    global _global_guard
    _global_guard = None


# Convenience functions for common operations

def register_secret(name: str, value: str, **kwargs) -> bool:
    """Register a secret using the global guard."""
    guard = get_sensitive_data_guard()
    return guard.register_secret(name, value, **kwargs)


def mask_for_llm(text: str) -> str:
    """
    Mask sensitive data before sending to LLM.

    Args:
        text: Text to mask

    Returns:
        Masked text safe for LLM
    """
    guard = get_sensitive_data_guard()
    return guard.mask_content(text)


def unmask_for_execution(text: str) -> str:
    """
    Unmask placeholders for execution only.

    IMPORTANT: Only use when executing actions, never when preparing LLM context.

    Args:
        text: Text with placeholders

    Returns:
        Text with actual secret values
    """
    guard = get_sensitive_data_guard()
    return guard.unmask_content(text)


def auto_detect_and_protect(text: str, context: str = "unknown") -> str:
    """
    Auto-detect secrets, register them, and return masked version.

    Args:
        text: Text to scan and protect
        context: Context description for logging

    Returns:
        Masked text with auto-detected secrets replaced
    """
    guard = get_sensitive_data_guard()
    guard.auto_register_detected(text, context)
    return guard.mask_content(text)
