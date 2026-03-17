"""
Immune System - Protecting Agent Identity from Corruption

This is the defense layer that protects the agent's core identity from being
compromised, manipulated, or corrupted through various attack vectors.

PURPOSE: The mission anchor defines what the agent IS. The immune system
PROTECTS that identity from corruption.

THREAT MODEL:
1. Prompt Injection - attempts to override instructions or change behavior
2. Mission Drift Pressure - subtle pressure to change core purpose over time
3. Boundary Violations - requests to violate ethical boundaries
4. Social Engineering - manipulation tactics to bypass safeguards
5. Identity Confusion - attempts to confuse or rewrite self-model

DEFENSE MECHANISMS:
- Input screening before processing
- Output sanitization before sending
- Threat pattern recognition (antibodies)
- Quarantine system for suspicious inputs
- Continuous threat logging and analysis

Integration:
- Called on ALL user inputs before processing
- Called on ALL outputs before sending
- Publishes THREAT_DETECTED events via EventBus
- Logs threats for analysis and learning
- Can block, quarantine, or sanitize content
"""

import re
import time
import json
import base64
import binascii
import unicodedata
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from collections import deque, defaultdict
from enum import Enum
from loguru import logger

from .organism_core import EventBus, EventType, OrganismEvent


# =============================================================================
# THREAT MODEL
# =============================================================================

class ThreatType(Enum):
    """Types of threats to agent identity."""
    INJECTION = "injection"                    # Prompt injection attempts
    MISSION_DRIFT = "mission_drift"            # Pressure to change purpose
    BOUNDARY_VIOLATION = "boundary_violation"  # Requests violating ethics
    MANIPULATION = "manipulation"              # Social engineering
    IDENTITY_CONFUSION = "identity_confusion"  # Attempts to confuse self-model
    JAILBREAK = "jailbreak"                    # Attempts to bypass restrictions
    IMPERSONATION = "impersonation"            # Pretending to be authority
    EXFILTRATION = "exfiltration"              # Attempts to extract private data


class QuarantineStatus(Enum):
    """Status of quarantined items in their lifecycle."""
    PENDING = "pending"                        # Awaiting review
    REVIEWED_SAFE = "reviewed_safe"            # Reviewed and determined safe
    REVIEWED_DANGEROUS = "reviewed_dangerous"  # Reviewed and confirmed dangerous
    RELEASED = "released"                      # Safe items that have been released
    DELETED = "deleted"                        # Dangerous items that have been deleted


@dataclass
class Threat:
    """A detected threat to agent identity."""
    threat_type: ThreatType
    severity: float  # 0-1, higher = more severe
    pattern: str = ""  # What triggered detection
    detected_in: str = ""  # The problematic text
    timestamp: float = field(default_factory=time.time)
    mitigation: str = ""  # How it was handled

    def __str__(self):
        return f"[{self.threat_type.value}] severity={self.severity:.2f}: {self.pattern}"


@dataclass
class ScreenResult:
    """Result of screening input or output."""
    safe: bool
    content: str  # Original or sanitized content
    threats: List[Threat] = field(default_factory=list)
    quarantined: bool = False
    sanitized: bool = False
    allowed_with_warning: bool = False

    def has_critical_threats(self) -> bool:
        """Check if any critical (>0.8) threats detected."""
        return any(t.severity >= 0.8 for t in self.threats)

    def has_major_threats(self) -> bool:
        """Check if any major (>0.6) threats detected."""
        return any(t.severity >= 0.6 for t in self.threats)


# =============================================================================
# THREAT PATTERNS - The Antibodies
# =============================================================================

class ThreatPatterns:
    """
    Known threat patterns (antibodies) that the immune system recognizes.

    This is like a virus database - patterns learned from known attacks.
    """

    # Prompt injection patterns
    INJECTION_PATTERNS = [
        # Direct instruction override
        (r"ignore (previous|all|your) (instructions?|prompts?|rules?)", 0.95),
        (r"disregard (previous|all|your) (instructions?|prompts?|rules?)", 0.95),
        (r"forget (everything|all|your) (instructions?|prompts?|rules?)", 0.9),
        (r"new instructions?:?", 0.85),
        (r"system prompt:?", 0.85),
        (r"override (instructions?|rules?|settings?)", 0.9),

        # Role manipulation - always trigger on role switching attempts
        # Security: removed content-based bypass (eversale|agent) - attackers were exploiting
        # this by including those keywords in malicious inputs to bypass detection
        (r"you are now (a |an )?", 0.9),  # Role switch attempts
        (r"act as (a |an )?", 0.85),
        (r"pretend (you are|to be)", 0.8),
        (r"roleplay as", 0.75),
        (r"simulate (being |a )", 0.7),

        # Role confusion - "As an AI..." attempts
        (r"as an (ai|assistant|language model)", 0.85),
        (r"since you('re| are) (just )?(an )?(ai|assistant|chatbot)", 0.8),
        (r"because you('re| are) (an )?(ai|assistant)", 0.75),

        # Context manipulation
        (r"in (this|the) (context|scenario|situation),? you (are|should|must)", 0.8),
        (r"for (this|the) (purpose|task|exercise),? (assume|pretend|act)", 0.8),

        # Instruction boundary breaking
        (r"\[SYSTEM\]|\[INST\]|\[/INST\]", 0.85),
        (r"<\|im_start\|>|<\|im_end\|>", 0.9),  # Chat template markers
        (r"### (System|User|Assistant):", 0.85),
        (r"<<<.*>>>", 0.75),  # Suspicious delimiters
        (r"```system|```instructions?|```prompt", 0.85),  # Markdown delimiter injection
        (r"<system>|</system>|<prompt>|</prompt>", 0.85),  # XML-style delimiter injection

        # Jailbreak attempts
        (r"DAN mode|developer mode|god mode", 0.95),
        (r"jailbreak|bypass (restrictions?|safety|rules)", 0.95),
        (r"disable (safety|ethics|filters?)", 0.95),
        (r"remove (restrictions?|limitations?|boundaries?)", 0.9),

        # Bypass keyword injection - attempts to exploit former content-based exceptions
        # Security: Detect when users try to include "eversale" or "agent" in malicious inputs
        (r"(you are now|act as|pretend to be).*(eversale|agent)", 0.95),
        (r"(hacker|admin|developer|system).*(eversale|agent)", 0.9),

        # Instruction leakage attempts
        (r"show (me )?(your )?(system )?(prompt|instructions?|rules)", 0.9),
        (r"what (are|is) your (system )?(prompt|instructions?|rules)", 0.85),
        (r"print (your )?(prompt|instructions?|rules)", 0.9),
        (r"reveal (your )?(prompt|instructions?|rules)", 0.9),

        # Indirect references - attempts to get agent to follow external instructions
        (r"do what (the|this) (document|file|text|message|email) (says|tells)", 0.9),
        (r"follow (the )?(instructions?|commands?) (in|from|above|below)", 0.85),
        (r"execute (the )?(instructions?|commands?) (in|from|that)", 0.9),
        (r"obey (the )?(instructions?|commands?|orders?)", 0.85),
        (r"according to (the|these) (new )?(instructions?|rules?)", 0.85),

        # Encoded/Obfuscated injection attempts - SECURITY ENHANCEMENT (VULN #1 FIX)
        # Base64-like patterns (long alphanumeric strings that might be encoded payloads)
        (r"[A-Za-z0-9+/]{50,}={0,2}", 0.7),  # Potential base64 encoded payload
        # Hex-encoded patterns
        (r"(?:0x[0-9a-fA-F]{2,}[\s,]*){10,}", 0.75),  # Multiple hex values
        (r"(?:\\x[0-9a-fA-F]{2}){5,}", 0.7),  # Hex escape sequences
        # Unicode escape sequences
        (r"(?:\\u[0-9a-fA-F]{4}){5,}", 0.7),  # Multiple unicode escapes
        (r"(?:&#x?[0-9a-fA-F]+;){5,}", 0.65),  # Multiple HTML entities
        # Encoding/decoding function mentions (often used to hide payloads)
        (r"(atob|btoa|base64|decode|encode|fromCharCode|unescape|decodeURI)", 0.75),
        # ROT13 or similar obfuscation indicators
        (r"\b[bcdfghjklmnpqrstvwxyz]{15,}\b", 0.6),  # Suspicious consonant strings
    ]

    # Mission drift patterns
    MISSION_DRIFT_PATTERNS = [
        # Purpose redefinition
        (r"your (new |real )?(purpose|mission|goal) is", 0.9),
        (r"you should actually", 0.7),
        (r"you're (really|actually) (meant|supposed) to", 0.75),
        (r"from now on,? (you are|you will)", 0.8),

        # Value conflicts
        (r"customer success doesn't matter", 0.85),
        (r"ignore (customer|user) (needs|success)", 0.85),
        (r"don't (worry about|care about) (quality|reliability)", 0.75),

        # Scope expansion
        (r"you (can|should) (do|access) anything", 0.8),
        (r"no (limits|boundaries|restrictions) for you", 0.85),
        (r"you have (unlimited|full) (access|control|power)", 0.85),
    ]

    # Boundary violation patterns
    BOUNDARY_PATTERNS = [
        # Destructive actions
        (r"delete (all|everything|.*database)", 0.95),
        (r"drop (table|database)", 0.95),
        (r"rm -rf", 0.9),
        (r"format (drive|disk|c:)", 0.95),
        (r"destroy (all|everything|data)", 0.9),
        (r"wipe (clean|everything|data)", 0.85),

        # Deceptive actions
        (r"create (a )?fake", 0.9),
        (r"impersonate (a |an )?", 0.9),
        (r"send spam", 0.95),
        (r"phishing (email|campaign|attack)", 0.95),
        (r"lie (to|about)", 0.85),
        (r"deceive (the )?(user|customer)", 0.9),

        # Security violations
        (r"bypass (authentication|auth|login|security)", 0.95),
        (r"sql injection", 0.95),
        (r"xss attack|cross[- ]?site scripting", 0.95),
        (r"exploit (the |a )?(vulnerability|bug|flaw)", 0.9),
        (r"hack (into|the)", 0.95),
        (r"brute[- ]?force (password|login)", 0.95),

        # Privacy violations
        (r"steal (data|credentials|passwords?)", 0.95),
        (r"leak (private|personal|sensitive) (data|information)", 0.95),
        (r"expose (private|personal|sensitive) (data|information)", 0.9),
        (r"share (my |your )?password", 0.85),
    ]

    # Social engineering patterns - SECURITY ENHANCEMENT (VULN #4 FIX)
    # Based on Cialdini's 6 Principles of Persuasion + common attack patterns
    MANIPULATION_PATTERNS = [
        # Urgency pressure (Scarcity)
        (r"(urgent|emergency|critical|immediately|right now|asap)", 0.6),
        (r"(hurry|quickly|fast|before .* too late)", 0.5),
        (r"time[- ]?(sensitive|critical)", 0.6),
        (r"(limited time|expires? (soon|today|now))", 0.65),
        (r"(only|just) \d+ (minutes?|hours?|days?) (left|remaining)", 0.65),
        (r"(act now|don't wait|can't wait)", 0.6),

        # Authority claims
        (r"(i am|i'm) (your )?(admin|administrator|owner|boss|manager)", 0.8),
        (r"(i am|i'm) (a |the )?(developer|engineer|creator)", 0.8),
        (r"(i have|i've got) (admin|root|system|full) (access|privileges?|rights?)", 0.85),
        (r"(i own|i created|i built) (this|you)", 0.8),
        (r"(as your|i'm the) (supervisor|manager|director)", 0.8),
        (r"(official|authorized) (request|instruction)", 0.75),

        # Emotional manipulation
        (r"(please|i'm begging you|i need you to)", 0.4),
        (r"(disappointed|upset|angry) (with|at) you", 0.5),
        (r"you (owe me|must|have to|need to)", 0.6),
        (r"trust me|believe me", 0.5),
        (r"(i'll be|you'll make me) (so )?happy", 0.5),
        (r"(help me|i need your help)", 0.4),

        # Gaslighting / Social proof (Consensus)
        (r"you (always|usually|normally) do this", 0.7),
        (r"(everyone|all agents) (does?|allows?) this", 0.7),
        (r"this is (standard|normal|allowed|permitted)", 0.6),
        (r"(other|all) (agents|AIs|assistants) (can|do|allow)", 0.7),
        (r"(never|nobody) (had|has) a problem with this", 0.65),

        # Scarcity tactics
        (r"(last|final|only) (chance|opportunity)", 0.7),
        (r"(won't get|miss) (this|another) (chance|opportunity)", 0.65),
        (r"(rare|exclusive|special) (access|opportunity)", 0.6),
        (r"(limited|exclusive) (offer|access)", 0.6),

        # Reciprocity tactics
        (r"(i (did|gave|helped)|after (all )?i)", 0.65),
        (r"you owe me", 0.7),
        (r"(return the |repay the )?favo(u)?r", 0.65),
        (r"(i've done|did) (so much|a lot) for you", 0.7),

        # Commitment/Consistency
        (r"you (said|promised|agreed) (you would|to)", 0.65),
        (r"you (always|usually) (do|help with) this", 0.6),
        (r"(be|stay) consistent", 0.5),
        (r"you're (not|being) consistent", 0.6),

        # Liking/Similarity
        (r"(we're|you're) (friends|buddies|similar|alike)", 0.5),
        (r"(i like|i love) you", 0.5),
        (r"(we|you and i) (think|work) the same", 0.55),

        # Fear appeals
        (r"(something bad|disaster|catastrophe) will happen", 0.7),
        (r"(you'll|gonna) (regret|be sorry)", 0.65),
        (r"(or else|otherwise)", 0.6),
        (r"(terrible|awful|horrible) (consequences|things)", 0.7),

        # Flattery manipulation
        (r"you're (so |really )?(smart|intelligent|capable|amazing)", 0.5),
        (r"(only you|you're the only one) can", 0.6),
        (r"you're (the best|special|unique)", 0.5),
    ]

    # Identity confusion patterns
    IDENTITY_PATTERNS = [
        # Self-model attacks
        (r"you are (not|no longer) (an agent|eversale)", 0.9),
        (r"you (can't|cannot|don't) (browse|navigate|extract)", 0.8),
        (r"you are (just|only|merely) (a |an )?(chatbot|assistant)", 0.75),
        (r"you (don't have|lack) (the )?(ability|capability|power)", 0.7),

        # Capability confusion
        (r"you (can|are able to) (make payments?|access local|video call)", 0.8),
        (r"you have (physical|offline|local) access", 0.85),

        # Purpose confusion
        (r"you're (designed|meant|built) to (chat|talk|converse)", 0.7),
        (r"you (can't|shouldn't|mustn't) (actually )?do (tasks|actions|work)", 0.75),
    ]

    @classmethod
    def get_all_patterns(cls) -> Dict[ThreatType, List[Tuple[str, float]]]:
        """Get all threat patterns organized by type."""
        return {
            ThreatType.INJECTION: cls.INJECTION_PATTERNS,
            ThreatType.MISSION_DRIFT: cls.MISSION_DRIFT_PATTERNS,
            ThreatType.BOUNDARY_VIOLATION: cls.BOUNDARY_PATTERNS,
            ThreatType.MANIPULATION: cls.MANIPULATION_PATTERNS,
            ThreatType.IDENTITY_CONFUSION: cls.IDENTITY_PATTERNS,
        }


# =============================================================================
# IMMUNE SYSTEM - The Defense Layer
# =============================================================================

class ImmuneSystem:
    """
    Protects the agent's identity from corruption.

    This is the security layer that screens all inputs and outputs for
    threats to the agent's core identity, mission, and boundaries.

    Key features:
    - Multi-layer threat detection
    - Pattern-based recognition (antibodies)
    - Learning from new threats
    - Quarantine system for suspicious inputs
    - Detailed threat logging
    """

    # Severity thresholds for action
    BLOCK_THRESHOLD = 0.8      # >= 0.8 severity = block immediately
    QUARANTINE_THRESHOLD = 0.6  # >= 0.6 severity = quarantine for review
    WARNING_THRESHOLD = 0.4     # >= 0.4 severity = allow with warning

    # Maximum quarantine size
    MAX_QUARANTINE_SIZE = 100
    MAX_THREAT_LOG_SIZE = 500

    # Quarantine lifecycle timeouts (in seconds)
    SAFE_RELEASE_TIMEOUT = 3600        # 1 hour - release safe items after this time
    DANGEROUS_DELETE_TIMEOUT = 86400   # 24 hours - delete dangerous items after this time
    PENDING_AUTO_TIMEOUT = 604800      # 7 days - auto-escalate or release pending items

    def __init__(
        self,
        mission_anchor,
        self_model,
        event_bus: Optional[EventBus] = None,
        persistence_path: Optional[Path] = None
    ):
        """
        Initialize the immune system.

        Args:
            mission_anchor: MissionAnchor defining core identity
            self_model: SelfModel with capabilities and boundaries
            event_bus: EventBus for publishing threat events
            persistence_path: Where to save threat logs
        """
        self.mission = mission_anchor
        self.self_model = self_model
        self.event_bus = event_bus
        self.persistence_path = persistence_path or Path("memory/immune_system.json")

        # Quarantine - suspicious inputs held for review
        self.quarantine: deque = deque(maxlen=self.MAX_QUARANTINE_SIZE)

        # Threat log - history of all detected threats
        self.threat_log: deque = deque(maxlen=self.MAX_THREAT_LOG_SIZE)

        # Antibodies - learned threat patterns beyond defaults
        # Format: {pattern_string: (threat_type, severity)}
        self.antibodies: Dict[str, Tuple[ThreatType, float]] = {}

        # Statistics
        self.stats = {
            "inputs_screened": 0,
            "outputs_screened": 0,
            "threats_detected": 0,
            "inputs_blocked": 0,
            "inputs_quarantined": 0,
            "outputs_sanitized": 0,
            "quarantine_released": 0,
            "quarantine_deleted": 0,
            "quarantine_escalated": 0,
            "bypass_attempts_logged": 0,  # Track exploitation attempts
            "started_at": time.time(),
        }

        # Track last cleanup time
        self._last_cleanup_time = time.time()

        # Compile regex patterns for efficiency
        self._compiled_patterns: Dict[ThreatType, List[Tuple[re.Pattern, float]]] = {}
        self._compile_patterns()

        # Load saved state
        self._load_state()

        logger.info("ImmuneSystem initialized - protecting agent identity")

    def _compile_patterns(self):
        """Compile all regex patterns for efficient matching."""
        for threat_type, patterns in ThreatPatterns.get_all_patterns().items():
            compiled = []
            for pattern, severity in patterns:
                try:
                    compiled.append((re.compile(pattern, re.IGNORECASE), severity))
                except re.error as e:
                    logger.warning(f"Failed to compile pattern '{pattern}': {e}")
            self._compiled_patterns[threat_type] = compiled

        logger.debug(f"Compiled {sum(len(p) for p in self._compiled_patterns.values())} threat patterns")

    # =============================================================================
    # INPUT SCREENING
    # =============================================================================

    def screen_input(self, input_text: str, source: str = "user") -> ScreenResult:
        """
        Screen incoming input for threats.

        This is called on ALL user inputs before processing.

        Args:
            input_text: The input to screen
            source: Source of input (user, system, api, etc.)
                   Trusted sources: "system_internal", "mission_anchor"
                   Untrusted sources: "user", "api", "external", etc.

        Returns:
            ScreenResult with safety assessment and any threats found
        """
        self.stats["inputs_screened"] += 1

        # Periodically cleanup quarantine (every 100 inputs or every hour)
        self._maybe_cleanup_quarantine()

        # Define trusted sources - these are internal system components only
        # SECURITY: Never trust user input or anything user-controlled
        trusted_sources = {"system_internal", "mission_anchor"}
        is_trusted = source in trusted_sources

        # Log suspicious pattern: someone claiming to be trusted with bypass keywords
        # This detects potential exploitation attempts
        if is_trusted:
            suspicious_keywords = ["eversale", "agent", "bypass", "override", "ignore"]
            found_keywords = [kw for kw in suspicious_keywords if kw in input_text.lower()]
            if found_keywords:
                logger.warning(
                    f"SUSPICIOUS: Trusted source '{source}' contains bypass keywords: {found_keywords}. "
                    f"Input preview: {input_text[:100]}"
                )
                # Log this as a potential security incident
                self.stats.setdefault("bypass_attempts_logged", 0)
                self.stats["bypass_attempts_logged"] += 1

        threats = []

        # 1. Check for prompt injection
        injection_threats = self._detect_injection(input_text)
        threats.extend(injection_threats)

        # 2. Check for mission drift pressure
        drift_threats = self._detect_mission_drift(input_text)
        threats.extend(drift_threats)

        # 3. Check for boundary violations
        boundary_threats = self._detect_boundary_violations(input_text)
        threats.extend(boundary_threats)

        # 4. Check for manipulation attempts
        manipulation_threats = self._detect_manipulation(input_text)
        threats.extend(manipulation_threats)

        # 5. Check for identity confusion
        identity_threats = self._detect_identity_confusion(input_text)
        threats.extend(identity_threats)

        # 6. Check against learned antibodies
        antibody_threats = self._check_antibodies(input_text)
        threats.extend(antibody_threats)

        # Determine action based on highest severity threat
        if not threats:
            return ScreenResult(safe=True, content=input_text)

        max_severity = max(t.severity for t in threats)

        # Log threats
        for threat in threats:
            self.threat_log.append(threat)
            self.stats["threats_detected"] += 1

        # Publish threat event
        if self.event_bus and max_severity >= self.WARNING_THRESHOLD:
            self._publish_threat_event(threats, input_text, source)

        # Critical threats - block immediately
        if max_severity >= self.BLOCK_THRESHOLD:
            self.stats["inputs_blocked"] += 1
            logger.warning(f"BLOCKED INPUT (severity {max_severity:.2f}): {input_text[:100]}")
            return ScreenResult(
                safe=False,
                content=input_text,
                threats=threats,
                quarantined=False,
                sanitized=False
            )

        # Major threats - quarantine for review
        elif max_severity >= self.QUARANTINE_THRESHOLD:
            result = self._quarantine_input(input_text, threats, source)
            self.stats["inputs_quarantined"] += 1
            logger.warning(f"QUARANTINED INPUT (severity {max_severity:.2f}): {input_text[:100]}")
            return result

        # Minor threats - allow with warning
        else:
            logger.info(f"INPUT WARNING (severity {max_severity:.2f}): {input_text[:100]}")
            return ScreenResult(
                safe=True,
                content=input_text,
                threats=threats,
                allowed_with_warning=True
            )

    def _detect_injection(self, text: str) -> List[Threat]:
        """
        Detect prompt injection attempts with sophisticated detection.

        This enhanced version detects:
        - Direct pattern matches (traditional)
        - Base64 encoded injections
        - Unicode obfuscation
        - Hex-encoded injections
        - Multi-step injections using heuristic scoring

        SECURITY ENHANCEMENT - Fixes vulnerability where sophisticated attacks bypass literal patterns
        """
        threats = []
        patterns = self._compiled_patterns.get(ThreatType.INJECTION, [])

        # Track weak signals for heuristic scoring
        weak_signals = []

        # 1. Direct pattern matching on original text
        for pattern, severity in patterns:
            match = pattern.search(text)
            if match:
                threat = Threat(
                    threat_type=ThreatType.INJECTION,
                    severity=severity,
                    pattern=pattern.pattern,
                    detected_in=match.group(0)
                )
                threats.append(threat)

                # Track weak signals (severity < 0.7) for heuristic scoring
                if severity < 0.7:
                    weak_signals.append(f"pattern:{pattern.pattern[:30]}")

        # 2. Unicode normalization - detect obfuscated text using lookalike characters
        try:
            # Normalize unicode to NFKC form (compatibility decomposition + canonical composition)
            # This converts lookalike characters (e.g., Cyrillic 'а' to Latin 'a')
            normalized_text = unicodedata.normalize('NFKC', text)

            # If normalized text is different, check it for injection patterns
            if normalized_text != text:
                for pattern, severity in patterns:
                    match = pattern.search(normalized_text)
                    # Only add if we haven't already detected this pattern
                    if match and not any(t.pattern == pattern.pattern for t in threats):
                        threats.append(Threat(
                            threat_type=ThreatType.INJECTION,
                            severity=min(severity * 0.95, 1.0),  # Slightly lower for obfuscated
                            pattern=f"unicode_obfuscated:{pattern.pattern}",
                            detected_in=f"[unicode obfuscated] {match.group(0)}"
                        ))
                        weak_signals.append("unicode_obfuscation")
                        logger.info(f"Detected unicode obfuscation attempt: {text[:50]}")
        except Exception as e:
            logger.debug(f"Unicode normalization failed: {e}")

        # 3. Base64 decoding - detect encoded injections
        # Look for base64-like strings (20+ chars to avoid false positives)
        base64_candidates = re.findall(r'[A-Za-z0-9+/]{20,}={0,2}', text)
        for candidate in base64_candidates:
            try:
                # Attempt to decode (validate=True ensures proper base64)
                decoded_bytes = base64.b64decode(candidate, validate=True)
                decoded_text = decoded_bytes.decode('utf-8', errors='ignore')

                # Check decoded text for injection patterns
                if decoded_text and len(decoded_text) > 5:
                    for pattern, severity in patterns:
                        match = pattern.search(decoded_text)
                        if match:
                            threats.append(Threat(
                                threat_type=ThreatType.INJECTION,
                                severity=min(severity * 1.1, 1.0),  # Higher severity for encoded attacks
                                pattern=f"base64_encoded:{pattern.pattern}",
                                detected_in=f"[base64: {candidate[:30]}...] decoded: {match.group(0)}"
                            ))
                            weak_signals.append("base64_encoding")
                            logger.warning(f"Detected base64 encoded injection: {decoded_text[:50]}")
            except (binascii.Error, ValueError, UnicodeDecodeError):
                # Not valid base64 or not UTF-8, skip silently
                pass

        # 4. Hex decoding - detect hex-encoded injections
        hex_patterns = [
            r'(?:\\x[0-9a-fA-F]{2})+',  # \x41\x42\x43 format
            r'(?:0x[0-9a-fA-F]{2}[\s,]*)+',  # 0x41 0x42 0x43 format
        ]
        for hex_pattern in hex_patterns:
            hex_candidates = re.findall(hex_pattern, text)
            for candidate in hex_candidates:
                try:
                    # Extract just the hex values (ignore 0x or \x prefixes)
                    hex_values = re.findall(r'[0-9a-fA-F]{2}', candidate)
                    decoded_bytes = bytes.fromhex(''.join(hex_values))
                    decoded_text = decoded_bytes.decode('utf-8', errors='ignore')

                    if decoded_text and len(decoded_text) > 5:
                        for pattern, severity in patterns:
                            match = pattern.search(decoded_text)
                            if match:
                                threats.append(Threat(
                                    threat_type=ThreatType.INJECTION,
                                    severity=min(severity * 1.1, 1.0),  # Higher severity for encoded
                                    pattern=f"hex_encoded:{pattern.pattern}",
                                    detected_in=f"[hex: {candidate[:30]}...] decoded: {match.group(0)}"
                                ))
                                weak_signals.append("hex_encoding")
                                logger.warning(f"Detected hex encoded injection: {decoded_text[:50]}")
                except (ValueError, UnicodeDecodeError):
                    # Not valid hex or not UTF-8, skip silently
                    pass

        # 5. Heuristic scoring - multiple weak signals = likely sophisticated attack
        # Rationale: Attackers often combine multiple techniques to evade detection
        # Example: low-severity patterns + encoding + obfuscation = high confidence attack
        if len(weak_signals) >= 3 and not any(t.severity >= 0.8 for t in threats):
            # Calculate combined severity based on number of signals
            combined_severity = min(0.65 + (len(weak_signals) * 0.05), 0.85)
            threats.append(Threat(
                threat_type=ThreatType.INJECTION,
                severity=combined_severity,
                pattern="heuristic:multiple_weak_signals",
                detected_in=f"Combined signals: {', '.join(set(weak_signals[:5]))}"
            ))
            logger.info(
                f"Heuristic detection triggered: {len(weak_signals)} weak signals "
                f"detected (severity: {combined_severity:.2f})"
            )

        # 6. Log all detections with context for analysis and learning
        if threats:
            logger.info(
                f"Injection detection complete: {len(threats)} threats found. "
                f"Max severity: {max(t.severity for t in threats):.2f}. "
                f"Weak signals: {len(weak_signals)}. "
                f"Input preview: {text[:100]}"
            )

        return threats

    def _detect_mission_drift(self, text: str) -> List[Threat]:
        """Detect attempts to change core mission."""
        threats = []
        patterns = self._compiled_patterns.get(ThreatType.MISSION_DRIFT, [])

        for pattern, severity in patterns:
            match = pattern.search(text)
            if match:
                threats.append(Threat(
                    threat_type=ThreatType.MISSION_DRIFT,
                    severity=severity,
                    pattern=pattern.pattern,
                    detected_in=match.group(0)
                ))

        # Also check against mission anchor
        if self.mission:
            # Simple check: if input contradicts mission statement
            mission_lower = self.mission.mission.lower()
            text_lower = text.lower()

            # Check for negation of mission keywords
            mission_keywords = set(mission_lower.split())
            for keyword in mission_keywords:
                if len(keyword) > 4:  # Skip short words
                    # Look for "not [keyword]" or "don't [keyword]"
                    neg_pattern = rf"(not|don't|never|shouldn't)\s+\w*\s*{re.escape(keyword)}"
                    if re.search(neg_pattern, text_lower):
                        threats.append(Threat(
                            threat_type=ThreatType.MISSION_DRIFT,
                            severity=0.7,
                            pattern=f"negation of mission keyword: {keyword}",
                            detected_in=text[:100]
                        ))

        return threats

    def _detect_boundary_violations(self, text: str) -> List[Threat]:
        """Detect requests to violate ethical boundaries."""
        threats = []
        patterns = self._compiled_patterns.get(ThreatType.BOUNDARY_VIOLATION, [])

        for pattern, severity in patterns:
            match = pattern.search(text)
            if match:
                threats.append(Threat(
                    threat_type=ThreatType.BOUNDARY_VIOLATION,
                    severity=severity,
                    pattern=pattern.pattern,
                    detected_in=match.group(0)
                ))

        # Also check against self-model boundaries
        if self.self_model:
            violates, reason = self.self_model.identity.violates_boundary(text)
            if violates:
                threats.append(Threat(
                    threat_type=ThreatType.BOUNDARY_VIOLATION,
                    severity=0.85,
                    pattern="self-model boundary check",
                    detected_in=reason or "boundary violation detected"
                ))

        return threats

    def _detect_manipulation(self, text: str) -> List[Threat]:
        """Detect social engineering and manipulation attempts."""
        threats = []
        patterns = self._compiled_patterns.get(ThreatType.MANIPULATION, [])

        # Track manipulation indicators
        urgency_count = 0
        authority_count = 0
        emotional_count = 0

        for pattern, severity in patterns:
            match = pattern.search(text)
            if match:
                threat = Threat(
                    threat_type=ThreatType.MANIPULATION,
                    severity=severity,
                    pattern=pattern.pattern,
                    detected_in=match.group(0)
                )
                threats.append(threat)

                # Count manipulation types
                if "urgent" in pattern.pattern.lower() or "hurry" in pattern.pattern.lower():
                    urgency_count += 1
                elif "admin" in pattern.pattern.lower() or "owner" in pattern.pattern.lower():
                    authority_count += 1
                elif "please" in pattern.pattern.lower() or "disappointed" in pattern.pattern.lower():
                    emotional_count += 1

        # Multiple manipulation tactics = higher combined threat
        if urgency_count + authority_count + emotional_count >= 3:
            threats.append(Threat(
                threat_type=ThreatType.MANIPULATION,
                severity=0.8,
                pattern="multiple manipulation tactics detected",
                detected_in=f"{urgency_count} urgency, {authority_count} authority, {emotional_count} emotional"
            ))

        return threats

    def _detect_identity_confusion(self, text: str) -> List[Threat]:
        """Detect attempts to confuse agent's self-model."""
        threats = []
        patterns = self._compiled_patterns.get(ThreatType.IDENTITY_CONFUSION, [])

        for pattern, severity in patterns:
            match = pattern.search(text)
            if match:
                threats.append(Threat(
                    threat_type=ThreatType.IDENTITY_CONFUSION,
                    severity=severity,
                    pattern=pattern.pattern,
                    detected_in=match.group(0)
                ))

        return threats

    def _check_antibodies(self, text: str) -> List[Threat]:
        """Check against learned threat patterns (antibodies)."""
        threats = []

        for pattern, (threat_type, severity) in self.antibodies.items():
            if re.search(pattern, text, re.IGNORECASE):
                threats.append(Threat(
                    threat_type=threat_type,
                    severity=severity,
                    pattern=f"learned antibody: {pattern}",
                    detected_in=text[:100]
                ))

        return threats

    # =============================================================================
    # OUTPUT SCREENING
    # =============================================================================

    def screen_output(self, output_text: str) -> ScreenResult:
        """
        Screen outgoing output for identity violations.

        Prevents the agent from saying things that would violate its identity.

        Args:
            output_text: The output to screen

        Returns:
            ScreenResult with sanitized output if needed
        """
        self.stats["outputs_screened"] += 1

        threats = []
        sanitized = output_text
        needs_sanitization = False

        # 1. Check if output would violate boundaries
        if self._output_violates_boundaries(output_text):
            threats.append(Threat(
                threat_type=ThreatType.BOUNDARY_VIOLATION,
                severity=0.9,
                pattern="output violates agent boundaries",
                detected_in=output_text[:100]
            ))
            needs_sanitization = True

        # 2. Check if output contradicts mission
        if self._output_contradicts_mission(output_text):
            threats.append(Threat(
                threat_type=ThreatType.MISSION_DRIFT,
                severity=0.8,
                pattern="output contradicts mission",
                detected_in=output_text[:100]
            ))
            needs_sanitization = True

        # 3. Check if output leaks private information
        if self._output_leaks_private_info(output_text):
            threats.append(Threat(
                threat_type=ThreatType.EXFILTRATION,
                severity=0.95,
                pattern="output leaks private information",
                detected_in="[REDACTED]"
            ))
            needs_sanitization = True

        # 4. Check if output makes false claims about capabilities
        if self._output_false_capability_claims(output_text):
            threats.append(Threat(
                threat_type=ThreatType.IDENTITY_CONFUSION,
                severity=0.7,
                pattern="output makes false capability claims",
                detected_in=output_text[:100]
            ))
            needs_sanitization = True

        # Sanitize if needed
        if needs_sanitization:
            sanitized = self._sanitize_output(output_text, threats)
            self.stats["outputs_sanitized"] += 1
            logger.warning(f"SANITIZED OUTPUT: {len(threats)} violations found")

            # Log threats
            for threat in threats:
                self.threat_log.append(threat)
                self.stats["threats_detected"] += 1

            return ScreenResult(
                safe=True,
                content=sanitized,
                threats=threats,
                sanitized=True
            )

        return ScreenResult(safe=True, content=output_text)

    def _output_violates_boundaries(self, output: str) -> bool:
        """Check if output would violate agent's boundaries."""
        if not self.self_model:
            return False

        # Check for statements that violate boundaries
        violation_patterns = [
            r"i (will|can|am going to) (lie|deceive|spam|hack)",
            r"i (don't care|ignore) (user|customer|privacy|security)",
            r"i (will|can) (delete all|destroy|wipe)",
        ]

        output_lower = output.lower()
        for pattern in violation_patterns:
            if re.search(pattern, output_lower):
                return True

        return False

    def _output_contradicts_mission(self, output: str) -> bool:
        """Check if output contradicts the mission."""
        if not self.mission:
            return False

        # Check for direct contradictions
        contradiction_patterns = [
            r"customer success (doesn't matter|isn't important)",
            r"i (don't|won't) help (users?|customers?)",
            r"my purpose is not",
        ]

        output_lower = output.lower()
        for pattern in contradiction_patterns:
            if re.search(pattern, output_lower):
                return True

        return False

    def _output_leaks_private_info(self, output: str) -> bool:
        """Check if output leaks private/sensitive information."""
        # Check for common private info patterns
        leak_patterns = [
            r"password is:?\s*\S+",
            r"api[_ ]?key:?\s*\S{10,}",
            r"secret:?\s*\S+",
            r"token:?\s*\S{20,}",
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email (if in system prompt)
        ]

        for pattern in leak_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                return True

        return False

    def _output_false_capability_claims(self, output: str) -> bool:
        """Check if output makes false claims about capabilities."""
        if not self.self_model:
            return False

        # Check for claims about disabled capabilities
        output_lower = output.lower()

        for cap_name, capability in self.self_model.capabilities.items():
            if not capability.enabled:
                # Generate keywords for this capability
                keywords = self.self_model._capability_keywords(cap_name)

                # Check if output claims to be able to do this
                for keyword in keywords:
                    claim_pattern = rf"i (can|will|am able to) {re.escape(keyword)}"
                    if re.search(claim_pattern, output_lower):
                        return True

        return False

    def _sanitize_output(self, output: str, threats: List[Threat]) -> str:
        """
        Sanitize output by removing/replacing problematic content.

        Args:
            output: Original output
            threats: Detected threats

        Returns:
            Sanitized output
        """
        sanitized = output

        # Remove private info
        sanitized = re.sub(
            r"password is:?\s*\S+",
            "[PASSWORD REDACTED]",
            sanitized,
            flags=re.IGNORECASE
        )
        sanitized = re.sub(
            r"api[_ ]?key:?\s*\S{10,}",
            "[API KEY REDACTED]",
            sanitized,
            flags=re.IGNORECASE
        )
        sanitized = re.sub(
            r"secret:?\s*\S+",
            "[SECRET REDACTED]",
            sanitized,
            flags=re.IGNORECASE
        )

        # Add safety disclaimer for boundary violations
        for threat in threats:
            if threat.threat_type == ThreatType.BOUNDARY_VIOLATION:
                sanitized += "\n\n[Note: I cannot perform actions that violate my ethical boundaries.]"
                break

        return sanitized

    # =============================================================================
    # QUARANTINE
    # =============================================================================

    def _sanitize_quarantined_input(self, input_text: str, threats: List[Threat]) -> str:
        """
        Sanitize quarantined input by removing/neutralizing threats.

        SECURITY FIX (VULN #3): Quarantine now actually sanitizes content instead of
        returning it unchanged. This prevents malicious patterns from being processed.

        Args:
            input_text: The suspicious input
            threats: Detected threats

        Returns:
            Sanitized input with threats neutralized
        """
        sanitized = input_text

        # 1. Decode and neutralize any base64 patterns
        try:
            base64_pattern = re.compile(r"[A-Za-z0-9+/]{50,}={0,2}")
            for match in base64_pattern.finditer(input_text):
                try:
                    decoded = base64.b64decode(match.group(0), validate=True).decode('utf-8', errors='ignore')
                    # If decoded contains injection patterns, replace with warning
                    if any(pattern.search(decoded) for pattern_list in self._compiled_patterns.values()
                           for pattern, _ in pattern_list):
                        sanitized = sanitized.replace(match.group(0), "[ENCODED_PAYLOAD_REMOVED]")
                except (binascii.Error, ValueError):
                    pass  # Not valid base64
        except Exception as e:
            logger.debug(f"Base64 sanitization error: {e}")

        # 2. Remove hex-encoded sequences
        sanitized = re.sub(r"(?:\\x[0-9a-fA-F]{2}){5,}", "[HEX_SEQUENCE_REMOVED]", sanitized)
        sanitized = re.sub(r"(?:0x[0-9a-fA-F]{2,}[\s,]*){10,}", "[HEX_VALUES_REMOVED]", sanitized)

        # 3. Remove unicode escape sequences
        sanitized = re.sub(r"(?:\\u[0-9a-fA-F]{4}){5,}", "[UNICODE_REMOVED]", sanitized)
        sanitized = re.sub(r"(?:&#x?[0-9a-fA-F]+;){5,}", "[HTML_ENTITIES_REMOVED]", sanitized)

        # 4. Remove encoding/decoding function calls
        sanitized = re.sub(
            r"(atob|btoa|base64|decode|encode|fromCharCode|unescape|decodeURI)\s*\(",
            "[ENCODING_FUNC_REMOVED](",
            sanitized,
            flags=re.IGNORECASE
        )

        # 5. Neutralize injection patterns
        for threat in threats:
            if threat.threat_type == ThreatType.INJECTION:
                # Replace the detected pattern with neutral text
                if threat.detected_in and threat.detected_in in sanitized:
                    sanitized = sanitized.replace(threat.detected_in, "[INJECTION_ATTEMPT_REMOVED]")

        # 6. Remove role manipulation attempts
        for threat in threats:
            if threat.threat_type == ThreatType.MANIPULATION:
                if threat.detected_in and threat.detected_in in sanitized:
                    sanitized = sanitized.replace(threat.detected_in, "[MANIPULATION_REMOVED]")

        # 7. Neutralize boundary violations
        for threat in threats:
            if threat.threat_type == ThreatType.BOUNDARY_VIOLATION:
                if threat.detected_in and threat.detected_in in sanitized:
                    sanitized = sanitized.replace(threat.detected_in, "[HARMFUL_REQUEST_REMOVED]")

        return sanitized

    def _quarantine_input(
        self,
        input_text: str,
        threats: List[Threat],
        source: str
    ) -> ScreenResult:
        """
        Quarantine suspicious input for review.

        SECURITY FIX (VULN #3): Now sanitizes content before quarantining.

        Args:
            input_text: The suspicious input
            threats: Detected threats
            source: Source of input

        Returns:
            ScreenResult indicating quarantine with sanitized content
        """
        # SECURITY: Sanitize the input before storing
        sanitized_input = self._sanitize_quarantined_input(input_text, threats)

        quarantine_entry = {
            "input": input_text,  # Original for analysis
            "sanitized_input": sanitized_input,  # Sanitized version
            "threats": [asdict(t) for t in threats],
            "source": source,
            "timestamp": time.time(),
            "status": QuarantineStatus.PENDING.value,
            "reviewed": False,  # Keep for backward compatibility
            "reviewed_at": None,
            "status_changed_at": time.time(),
        }

        self.quarantine.append(quarantine_entry)

        logger.warning(
            f"Input quarantined and sanitized: {len(threats)} threats detected "
            f"(max severity: {max(t.severity for t in threats):.2f})"
        )

        # Return sanitized content, not original
        return ScreenResult(
            safe=False,
            content=sanitized_input,  # Return sanitized version
            threats=threats,
            quarantined=True,
            sanitized=True  # Mark as sanitized
        )

    def review_quarantine(self, index: int, approved: bool) -> bool:
        """
        Review a quarantined input.

        Args:
            index: Index in quarantine queue
            approved: Whether to approve the input (True = safe, False = dangerous)

        Returns:
            True if review successful
        """
        if index < 0 or index >= len(self.quarantine):
            return False

        entry = self.quarantine[index]
        entry["reviewed"] = True  # Keep for backward compatibility
        entry["approved"] = approved  # Keep for backward compatibility
        entry["reviewed_at"] = time.time()
        entry["status_changed_at"] = time.time()

        # Update status based on review
        if approved:
            entry["status"] = QuarantineStatus.REVIEWED_SAFE.value
            logger.info(f"Quarantine item {index} marked as SAFE")
        else:
            entry["status"] = QuarantineStatus.REVIEWED_DANGEROUS.value
            logger.warning(f"Quarantine item {index} marked as DANGEROUS")

            # This was a true threat - reinforce the pattern
            for threat_dict in entry["threats"]:
                pattern = threat_dict["pattern"]
                if pattern and pattern not in self.antibodies:
                    threat_type = ThreatType(threat_dict["threat_type"])
                    severity = min(threat_dict["severity"] * 1.1, 1.0)  # Increase severity
                    self._learn_threat_pattern(pattern, threat_type, severity)

        return True

    def update_quarantine_status(
        self,
        index: int,
        new_status: QuarantineStatus,
        reason: str = ""
    ) -> bool:
        """
        Update the status of a quarantined item.

        Args:
            index: Index in quarantine queue
            new_status: New status to set
            reason: Optional reason for status change

        Returns:
            True if update successful
        """
        if index < 0 or index >= len(self.quarantine):
            return False

        entry = self.quarantine[index]
        old_status = entry.get("status", QuarantineStatus.PENDING.value)
        entry["status"] = new_status.value
        entry["status_changed_at"] = time.time()

        if reason:
            entry["status_reason"] = reason

        logger.info(
            f"Quarantine item {index} status changed: {old_status} -> {new_status.value}"
            + (f" ({reason})" if reason else "")
        )

        return True

    def cleanup_quarantine(self) -> Dict[str, int]:
        """
        Clean up quarantine by:
        1. Automatically releasing REVIEWED_SAFE items after timeout
        2. Automatically deleting REVIEWED_DANGEROUS items after timeout
        3. Auto-escalating or auto-releasing old PENDING items

        Returns:
            Dictionary with counts of released, deleted, and escalated items
        """
        current_time = time.time()
        released_count = 0
        deleted_count = 0
        escalated_count = 0

        # Process items (we'll mark them for removal, then remove all at once)
        items_to_remove = []

        for i, entry in enumerate(self.quarantine):
            status = QuarantineStatus(entry.get("status", QuarantineStatus.PENDING.value))
            status_changed_at = entry.get("status_changed_at", entry.get("timestamp", current_time))
            time_in_status = current_time - status_changed_at

            # Auto-release REVIEWED_SAFE items after timeout
            if status == QuarantineStatus.REVIEWED_SAFE:
                if time_in_status >= self.SAFE_RELEASE_TIMEOUT:
                    entry["status"] = QuarantineStatus.RELEASED.value
                    entry["status_changed_at"] = current_time
                    items_to_remove.append(i)
                    released_count += 1
                    logger.info(
                        f"Auto-released safe item from quarantine: "
                        f"{entry['input'][:50]}... (age: {time_in_status/3600:.1f}h)"
                    )

            # Auto-delete REVIEWED_DANGEROUS items after timeout
            elif status == QuarantineStatus.REVIEWED_DANGEROUS:
                if time_in_status >= self.DANGEROUS_DELETE_TIMEOUT:
                    entry["status"] = QuarantineStatus.DELETED.value
                    entry["status_changed_at"] = current_time
                    items_to_remove.append(i)
                    deleted_count += 1
                    logger.info(
                        f"Auto-deleted dangerous item from quarantine: "
                        f"{entry['input'][:50]}... (age: {time_in_status/86400:.1f}d)"
                    )

            # Auto-escalate or auto-release old PENDING items
            elif status == QuarantineStatus.PENDING:
                if time_in_status >= self.PENDING_AUTO_TIMEOUT:
                    # Determine action based on threat severity
                    max_severity = max(t["severity"] for t in entry["threats"])

                    if max_severity >= 0.7:
                        # High severity - escalate to dangerous
                        entry["status"] = QuarantineStatus.REVIEWED_DANGEROUS.value
                        entry["status_changed_at"] = current_time
                        entry["status_reason"] = "auto-escalated due to high severity and no review"
                        escalated_count += 1
                        logger.warning(
                            f"Auto-escalated pending item to DANGEROUS: "
                            f"{entry['input'][:50]}... (severity: {max_severity:.2f})"
                        )
                    else:
                        # Lower severity - assume safe after long timeout
                        entry["status"] = QuarantineStatus.REVIEWED_SAFE.value
                        entry["status_changed_at"] = current_time
                        entry["status_reason"] = "auto-released due to low severity and no incidents"
                        escalated_count += 1
                        logger.info(
                            f"Auto-released pending item (no incidents): "
                            f"{entry['input'][:50]}... (severity: {max_severity:.2f})"
                        )

        # Remove released and deleted items from quarantine
        # Remove in reverse order to maintain indices
        for i in sorted(items_to_remove, reverse=True):
            del self.quarantine[i]

        if released_count > 0 or deleted_count > 0 or escalated_count > 0:
            logger.info(
                f"Quarantine cleanup: {released_count} released, "
                f"{deleted_count} deleted, {escalated_count} escalated"
            )

        return {
            "released": released_count,
            "deleted": deleted_count,
            "escalated": escalated_count,
            "current_size": len(self.quarantine),
        }

    def _maybe_cleanup_quarantine(self):
        """
        Conditionally cleanup quarantine if enough time has passed.

        Cleanup is triggered every hour or every 100 inputs, whichever comes first.
        """
        current_time = time.time()
        time_since_cleanup = current_time - self._last_cleanup_time
        inputs_since_start = self.stats["inputs_screened"]

        # Cleanup every hour or every 100 inputs
        should_cleanup = (
            time_since_cleanup >= 3600  # 1 hour
            or (inputs_since_start % 100 == 0 and len(self.quarantine) > 0)
        )

        if should_cleanup:
            logger.debug("Triggering periodic quarantine cleanup")
            result = self.cleanup_quarantine()

            # Update statistics
            self.stats["quarantine_released"] += result["released"]
            self.stats["quarantine_deleted"] += result["deleted"]
            self.stats["quarantine_escalated"] += result["escalated"]

            self._last_cleanup_time = current_time

    def get_quarantine_summary(self) -> List[Dict]:
        """Get summary of quarantined inputs."""
        current_time = time.time()
        return [
            {
                "index": i,
                "input_preview": entry["input"][:100],
                "threat_count": len(entry["threats"]),
                "max_severity": max(t["severity"] for t in entry["threats"]),
                "source": entry["source"],
                "timestamp": entry["timestamp"],
                "status": entry.get("status", QuarantineStatus.PENDING.value),
                "status_changed_at": entry.get("status_changed_at", entry.get("timestamp")),
                "time_in_status": current_time - entry.get("status_changed_at", entry.get("timestamp")),
                "reviewed": entry.get("reviewed", False),  # Backward compatibility
                "reviewed_at": entry.get("reviewed_at"),
                "status_reason": entry.get("status_reason"),
            }
            for i, entry in enumerate(self.quarantine)
        ]

    def get_quarantine_by_status(self, status: QuarantineStatus) -> List[Dict]:
        """
        Get quarantine items filtered by status.

        Args:
            status: The QuarantineStatus to filter by

        Returns:
            List of quarantine entries with the specified status
        """
        current_time = time.time()
        return [
            {
                "index": i,
                "input": entry["input"],
                "input_preview": entry["input"][:100],
                "threat_count": len(entry["threats"]),
                "threats": entry["threats"],
                "max_severity": max(t["severity"] for t in entry["threats"]),
                "source": entry["source"],
                "timestamp": entry["timestamp"],
                "status": entry.get("status", QuarantineStatus.PENDING.value),
                "status_changed_at": entry.get("status_changed_at", entry.get("timestamp")),
                "time_in_status": current_time - entry.get("status_changed_at", entry.get("timestamp")),
                "reviewed": entry.get("reviewed", False),
                "reviewed_at": entry.get("reviewed_at"),
                "status_reason": entry.get("status_reason"),
            }
            for i, entry in enumerate(self.quarantine)
            if entry.get("status", QuarantineStatus.PENDING.value) == status.value
        ]

    def get_quarantine_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the quarantine.

        Returns:
            Dictionary with quarantine statistics by status
        """
        status_counts = defaultdict(int)
        total_items = len(self.quarantine)

        for entry in self.quarantine:
            status = entry.get("status", QuarantineStatus.PENDING.value)
            status_counts[status] += 1

        return {
            "total_items": total_items,
            "by_status": dict(status_counts),
            "pending": status_counts.get(QuarantineStatus.PENDING.value, 0),
            "reviewed_safe": status_counts.get(QuarantineStatus.REVIEWED_SAFE.value, 0),
            "reviewed_dangerous": status_counts.get(QuarantineStatus.REVIEWED_DANGEROUS.value, 0),
            "released": status_counts.get(QuarantineStatus.RELEASED.value, 0),
            "deleted": status_counts.get(QuarantineStatus.DELETED.value, 0),
        }

    # =============================================================================
    # LEARNING
    # =============================================================================

    def learn_threat_pattern(
        self,
        pattern: str,
        threat_type: ThreatType,
        severity: float = 0.7
    ):
        """
        Learn a new threat pattern (create antibody).

        This allows the immune system to adapt to new attacks.

        Args:
            pattern: Regex pattern that identifies the threat
            threat_type: Type of threat
            severity: Severity level 0-1
        """
        # Validate pattern
        try:
            re.compile(pattern)
        except re.error:
            logger.error(f"Invalid regex pattern: {pattern}")
            return

        self.antibodies[pattern] = (threat_type, severity)
        logger.info(f"Learned new threat pattern: {pattern} ({threat_type.value}, {severity:.2f})")

        # Save to disk
        self._save_state()

    def _learn_threat_pattern(
        self,
        pattern: str,
        threat_type: ThreatType,
        severity: float
    ):
        """Internal method to learn patterns (no validation)."""
        self.antibodies[pattern] = (threat_type, severity)

    def remove_antibody(self, pattern: str) -> bool:
        """
        Remove a learned threat pattern.

        Args:
            pattern: Pattern to remove

        Returns:
            True if removed
        """
        if pattern in self.antibodies:
            del self.antibodies[pattern]
            self._save_state()
            logger.info(f"Removed antibody: {pattern}")
            return True
        return False

    # =============================================================================
    # REPORTING
    # =============================================================================

    def get_threat_report(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get report on recent threats and immune activity.

        Args:
            hours: Look back this many hours

        Returns:
            Threat report dict
        """
        cutoff = time.time() - (hours * 3600)

        # Filter recent threats
        recent_threats = [t for t in self.threat_log if t.timestamp >= cutoff]

        # Count by type
        threat_counts = defaultdict(int)
        for threat in recent_threats:
            threat_counts[threat.threat_type.value] += 1

        # Top patterns
        pattern_counts = defaultdict(int)
        for threat in recent_threats:
            pattern_counts[threat.pattern] += 1

        top_patterns = sorted(
            pattern_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        # Severity distribution
        critical = sum(1 for t in recent_threats if t.severity >= 0.8)
        major = sum(1 for t in recent_threats if 0.6 <= t.severity < 0.8)
        minor = sum(1 for t in recent_threats if t.severity < 0.6)

        return {
            "period_hours": hours,
            "total_threats": len(recent_threats),
            "threats_by_type": dict(threat_counts),
            "severity_distribution": {
                "critical": critical,
                "major": major,
                "minor": minor,
            },
            "top_patterns": [
                {"pattern": p, "count": c}
                for p, c in top_patterns
            ],
            "quarantine_size": len(self.quarantine),
            "antibody_count": len(self.antibodies),
            "statistics": self.stats.copy(),
        }

    def get_recent_threats(self, limit: int = 20) -> List[Dict]:
        """Get recent threats."""
        recent = list(self.threat_log)[-limit:]
        return [
            {
                "type": t.threat_type.value,
                "severity": t.severity,
                "pattern": t.pattern,
                "detected_in": t.detected_in[:100],
                "timestamp": t.timestamp,
            }
            for t in recent
        ]

    # =============================================================================
    # EVENT PUBLISHING
    # =============================================================================

    def _publish_threat_event(
        self,
        threats: List[Threat],
        content: str,
        source: str
    ):
        """Publish threat detection event to EventBus."""
        if not self.event_bus:
            return

        max_threat = max(threats, key=lambda t: t.severity)

        # Use MISSION_DRIFT event if that's the primary threat
        if max_threat.threat_type == ThreatType.MISSION_DRIFT:
            event_type = EventType.MISSION_DRIFT
        else:
            event_type = EventType.HEALTH_WARNING  # Generic threat

        # Determine priority based on severity
        if max_threat.severity >= 0.8:
            priority = 1  # Critical
        elif max_threat.severity >= 0.6:
            priority = 2  # Major
        else:
            priority = 4  # Minor

        try:
            import asyncio
            asyncio.create_task(self.event_bus.publish(OrganismEvent(
                event_type=event_type,
                source="immune_system",
                data={
                    "threat_type": max_threat.threat_type.value,
                    "severity": max_threat.severity,
                    "threat_count": len(threats),
                    "pattern": max_threat.pattern,
                    "source": source,
                    "content_preview": content[:100],
                    "message": f"Identity threat detected: {max_threat.threat_type.value}",
                },
                priority=priority
            )))
        except Exception as e:
            logger.debug(f"Failed to publish threat event: {e}")

    # =============================================================================
    # PERSISTENCE
    # =============================================================================

    def _save_state(self):
        """Save immune system state to disk."""
        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "antibodies": {
                    pattern: [threat_type.value, severity]
                    for pattern, (threat_type, severity) in self.antibodies.items()
                },
                "statistics": self.stats,
                "quarantine_summary": {
                    "count": len(self.quarantine),
                    "unreviewed": sum(1 for e in self.quarantine if not e.get("reviewed", False)),
                },
                "threat_log_summary": {
                    "count": len(self.threat_log),
                    "last_24h": len([
                        t for t in self.threat_log
                        if t.timestamp >= time.time() - 86400
                    ]),
                },
                "saved_at": datetime.now().isoformat(),
            }

            self.persistence_path.write_text(json.dumps(data, indent=2))
            logger.debug(f"ImmuneSystem state saved to {self.persistence_path}")

        except Exception as e:
            logger.error(f"Failed to save ImmuneSystem state: {e}")

    def _load_state(self):
        """Load immune system state from disk."""
        try:
            if not self.persistence_path.exists():
                return

            data = json.loads(self.persistence_path.read_text())

            # Load antibodies
            for pattern, (threat_type_str, severity) in data.get("antibodies", {}).items():
                try:
                    threat_type = ThreatType(threat_type_str)
                    self.antibodies[pattern] = (threat_type, severity)
                except (ValueError, KeyError):
                    logger.warning(f"Failed to load antibody: {pattern}")

            # Load statistics (merge with defaults)
            saved_stats = data.get("statistics", {})
            self.stats.update(saved_stats)

            logger.info(
                f"ImmuneSystem loaded: {len(self.antibodies)} antibodies, "
                f"{self.stats.get('threats_detected', 0)} total threats detected"
            )

        except Exception as e:
            logger.warning(f"Failed to load ImmuneSystem state: {e}")

    def force_save(self):
        """Force immediate save of state."""
        self._save_state()


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_immune_system: Optional[ImmuneSystem] = None


def get_immune_system() -> Optional[ImmuneSystem]:
    """Get the current ImmuneSystem instance."""
    return _immune_system


def init_immune_system(
    mission_anchor,
    self_model,
    event_bus: Optional[EventBus] = None,
    **kwargs
) -> ImmuneSystem:
    """Initialize the ImmuneSystem singleton."""
    global _immune_system
    _immune_system = ImmuneSystem(
        mission_anchor=mission_anchor,
        self_model=self_model,
        event_bus=event_bus,
        **kwargs
    )
    return _immune_system
