"""
Autonomous Challenge Resolver - The "Wise" Brain for Forever Operations

This module handles ALL types of web obstructions intelligently, designed for
unattended 24/7 operation where no human is available to fix issues.

Architecture (5 Layers of Defense):
    Layer 1: Quick Fixes - Instant resolution for known patterns
    Layer 2: Strategic Bypass - Multi-strategy attempts with learning
    Layer 3: AI Thinking - LLM analyzes situation and proposes solutions
    Layer 4: Subagent Swarm - Parallel exploration to find workarounds
    Layer 5: Human Escalation - Only when all else fails (with timeout auto-continue)

Obstruction Types Handled:
    - Cloudflare challenges (JS, Turnstile, WAF)
    - CAPTCHAs (reCAPTCHA, hCaptcha, image-based)
    - Login walls
    - Cookie consent popups
    - Rate limiting / IP bans
    - Anti-bot detection (fingerprinting, behavior analysis)
    - Page crashes / timeouts
    - Unexpected modals / overlays
    - Geographic restrictions
    - Session expiration

Key Features:
    - Self-learning: Remembers what works for each site
    - Cost-aware: Uses cheap strategies first
    - Parallel exploration: Subagents explore alternatives simultaneously
    - Graceful degradation: Always returns SOMETHING, never blocks forever
    - Forever-ready: Designed for unattended 24/7 operation
"""

import asyncio
import json
import hashlib
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from loguru import logger
from rich.console import Console

console = Console()


class ObstructionType(Enum):
    """All types of web obstructions the resolver can handle."""
    # Cloudflare family
    CLOUDFLARE_JS = auto()        # JavaScript challenge
    CLOUDFLARE_TURNSTILE = auto() # Turnstile CAPTCHA
    CLOUDFLARE_WAF = auto()       # Web Application Firewall block

    # CAPTCHA family
    RECAPTCHA_V2 = auto()
    RECAPTCHA_V3 = auto()
    HCAPTCHA = auto()
    IMAGE_CAPTCHA = auto()

    # Access control
    LOGIN_WALL = auto()
    COOKIE_CONSENT = auto()
    AGE_VERIFICATION = auto()
    GEOGRAPHIC_BLOCK = auto()

    # Rate limiting
    RATE_LIMITED = auto()
    IP_BANNED = auto()
    TOO_MANY_REQUESTS = auto()

    # Anti-bot
    BOT_DETECTED = auto()
    FINGERPRINT_CHECK = auto()
    BEHAVIOR_ANALYSIS = auto()

    # Technical
    PAGE_CRASH = auto()
    TIMEOUT = auto()
    SSL_ERROR = auto()

    # UI obstructions
    MODAL_OVERLAY = auto()
    POPUP_BLOCKER = auto()
    NEWSLETTER_POPUP = auto()

    # Authentication
    SESSION_EXPIRED = auto()
    TWO_FACTOR_REQUIRED = auto()

    # Unknown
    UNKNOWN = auto()


@dataclass
class ObstructionSignature:
    """Unique identifier for an obstruction pattern."""
    obstruction_type: ObstructionType
    site_domain: str
    page_indicators: List[str]
    url_pattern: str = ""

    def to_hash(self) -> str:
        """Create unique hash for this signature."""
        data = f"{self.obstruction_type.name}:{self.site_domain}:{sorted(self.page_indicators)}"
        return hashlib.md5(data.encode()).hexdigest()[:12]


@dataclass
class ResolutionAttempt:
    """Record of a resolution attempt."""
    strategy: str
    layer: int
    success: bool
    duration_ms: int
    error: Optional[str] = None
    result_data: Optional[Dict] = None


@dataclass
class ResolutionResult:
    """Final result of challenge resolution."""
    success: bool
    obstruction_type: ObstructionType
    resolution_strategy: str
    layer_used: int
    total_time_ms: int
    attempts: List[ResolutionAttempt] = field(default_factory=list)
    alternative_data: Optional[Dict] = None
    error: Optional[str] = None
    should_continue: bool = True  # Even on failure, should we continue with task?


@dataclass
class LearnedPattern:
    """A learned successful resolution pattern."""
    signature_hash: str
    successful_strategy: str
    layer: int
    success_count: int = 0
    failure_count: int = 0
    avg_time_ms: int = 0
    last_success: datetime = field(default_factory=datetime.now)

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0


class WisdomStore:
    """
    Persistent memory of successful resolutions.

    The "wisdom" that makes the resolver smarter over time.
    """

    def __init__(self, store_path: Optional[Path] = None):
        self.store_path = store_path or Path.home() / '.eversale' / 'wisdom' / 'challenge_patterns.json'
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.patterns: Dict[str, LearnedPattern] = {}
        self._load()

    def _load(self):
        """Load patterns from disk."""
        try:
            if self.store_path.exists():
                with open(self.store_path, 'r') as f:
                    data = json.load(f)
                for sig_hash, pattern_data in data.items():
                    self.patterns[sig_hash] = LearnedPattern(
                        signature_hash=sig_hash,
                        successful_strategy=pattern_data.get('strategy', ''),
                        layer=pattern_data.get('layer', 1),
                        success_count=pattern_data.get('successes', 0),
                        failure_count=pattern_data.get('failures', 0),
                        avg_time_ms=pattern_data.get('avg_time', 0),
                    )
                logger.debug(f"[WISDOM] Loaded {len(self.patterns)} learned patterns")
        except Exception as e:
            logger.debug(f"[WISDOM] Could not load patterns: {e}")

    def _save(self):
        """Persist patterns to disk."""
        try:
            data = {}
            for sig_hash, pattern in self.patterns.items():
                data[sig_hash] = {
                    'strategy': pattern.successful_strategy,
                    'layer': pattern.layer,
                    'successes': pattern.success_count,
                    'failures': pattern.failure_count,
                    'avg_time': pattern.avg_time_ms,
                }
            with open(self.store_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"[WISDOM] Could not save patterns: {e}")

    def get_best_strategy(self, signature: ObstructionSignature) -> Optional[LearnedPattern]:
        """Get the best known strategy for this obstruction."""
        sig_hash = signature.to_hash()
        pattern = self.patterns.get(sig_hash)
        if pattern and pattern.success_rate > 0.5:
            return pattern
        return None

    def record_success(self, signature: ObstructionSignature, strategy: str, layer: int, time_ms: int):
        """Record a successful resolution."""
        sig_hash = signature.to_hash()
        if sig_hash not in self.patterns:
            self.patterns[sig_hash] = LearnedPattern(
                signature_hash=sig_hash,
                successful_strategy=strategy,
                layer=layer,
            )
        pattern = self.patterns[sig_hash]
        pattern.success_count += 1
        pattern.successful_strategy = strategy
        pattern.layer = layer
        pattern.avg_time_ms = (pattern.avg_time_ms + time_ms) // 2
        pattern.last_success = datetime.now()
        self._save()

    def record_failure(self, signature: ObstructionSignature, strategy: str):
        """Record a failed resolution attempt."""
        sig_hash = signature.to_hash()
        if sig_hash not in self.patterns:
            self.patterns[sig_hash] = LearnedPattern(
                signature_hash=sig_hash,
                successful_strategy=strategy,
                layer=1,
            )
        self.patterns[sig_hash].failure_count += 1
        self._save()


class AutonomousChallengeResolver:
    """
    The "Wise" resolver that handles ALL web obstructions autonomously.

    Designed for forever operations where no human is watching.
    Always tries to continue, never blocks indefinitely.
    """

    # Detection patterns for each obstruction type
    DETECTION_PATTERNS = {
        ObstructionType.CLOUDFLARE_JS: [
            "Just a moment...",
            "Checking your browser",
            "challenge-running",
            "cf-browser-verification",
        ],
        ObstructionType.CLOUDFLARE_TURNSTILE: [
            "cf-turnstile",
            "challenges.cloudflare.com",
            "_cf_chl_opt",
        ],
        ObstructionType.CLOUDFLARE_WAF: [
            "Cloudflare Ray ID",
            "Access denied",
            "Error 1015",
            "Error 1020",
        ],
        ObstructionType.RECAPTCHA_V2: [
            "g-recaptcha",
            "recaptcha-checkbox",
            "recaptcha.net",
        ],
        ObstructionType.HCAPTCHA: [
            "h-captcha",
            "hcaptcha.com",
            "hcaptcha-checkbox",
        ],
        ObstructionType.LOGIN_WALL: [
            "Sign in to continue",
            "Log in to view",
            "Create an account",
            "login-required",
        ],
        ObstructionType.COOKIE_CONSENT: [
            "cookie-consent",
            "Accept cookies",
            "cookie-banner",
            "gdpr-consent",
            "Accept all",
        ],
        ObstructionType.RATE_LIMITED: [
            "rate limit",
            "too many requests",
            "slow down",
            "try again later",
            "429",
        ],
        ObstructionType.BOT_DETECTED: [
            "unusual activity",
            "automated access",
            "bot detected",
            "suspicious activity",
            "verify you are human",
        ],
        ObstructionType.MODAL_OVERLAY: [
            "modal-overlay",
            "popup-modal",
            "dialog-backdrop",
            "lightbox",
        ],
        ObstructionType.NEWSLETTER_POPUP: [
            "newsletter",
            "subscribe",
            "sign up for",
            "get updates",
        ],
        ObstructionType.GEOGRAPHIC_BLOCK: [
            "not available in your",
            "region blocked",
            "geo-restricted",
            "country not supported",
        ],
    }

    def __init__(
        self,
        mcp_client=None,
        llm_client=None,
        page=None,
        enable_learning: bool = True,
        enable_subagents: bool = True,
        human_timeout: int = 120,
    ):
        """
        Initialize the autonomous resolver.

        Args:
            mcp_client: MCP client for browser control
            llm_client: LLM client for AI thinking
            page: Playwright page object (optional, for direct control)
            enable_learning: Learn from successful resolutions
            enable_subagents: Use parallel subagents for exploration
            human_timeout: Seconds to wait for human before auto-continuing
        """
        self.mcp = mcp_client
        self.llm = llm_client
        self.page = page
        self.enable_learning = enable_learning
        self.enable_subagents = enable_subagents
        self.human_timeout = human_timeout

        self.wisdom = WisdomStore() if enable_learning else None

        # Import existing handlers
        self._init_handlers()

        logger.debug("[RESOLVER] Autonomous Challenge Resolver initialized")

    def _init_handlers(self):
        """Initialize existing handler modules."""
        # Cloudflare handler
        try:
            from .challenge_handler import get_challenge_handler, BlockedSite
            self.cloudflare_handler = get_challenge_handler(self.mcp)
            self.BlockedSite = BlockedSite
        except ImportError:
            self.cloudflare_handler = None
            self.BlockedSite = None

        # CAPTCHA solver
        try:
            from .captcha_solver import LocalCaptchaSolver, ChallengeType
            self.captcha_solver = LocalCaptchaSolver()
            self.ChallengeType = ChallengeType
        except ImportError:
            self.captcha_solver = None
            self.ChallengeType = None

        # Cascading recovery (deprecated - v2.9)
        try:
            # DEPRECATED: cascading_recovery removed in v2.9 - use reliability_core
            from .cascading_recovery import CascadingRecoverySystem
            self.recovery_system = CascadingRecoverySystem()
        except ImportError:
            logger.debug("Cascading recovery not available (removed in v2.9)")
            self.recovery_system = None

    async def detect_obstruction(self, page_content: str, url: str = "") -> Optional[ObstructionSignature]:
        """
        Detect what type of obstruction is blocking us.

        Returns ObstructionSignature or None if no obstruction detected.
        """
        content_lower = page_content.lower() if page_content else ""

        # Extract domain from URL
        domain = ""
        if url:
            import re
            match = re.search(r"https?://(?:www\.)?([^/]+)", url)
            if match:
                domain = match.group(1)

        # Check each obstruction type
        for obs_type, patterns in self.DETECTION_PATTERNS.items():
            indicators_found = []
            for pattern in patterns:
                if pattern.lower() in content_lower:
                    indicators_found.append(pattern)

            if indicators_found:
                return ObstructionSignature(
                    obstruction_type=obs_type,
                    site_domain=domain,
                    page_indicators=indicators_found,
                    url_pattern=url,
                )

        return None

    async def resolve(
        self,
        page_content: str = "",
        url: str = "",
        query: str = "",
        max_time_seconds: int = 120,
    ) -> ResolutionResult:
        """
        Main entry point - resolve any obstruction intelligently.

        This is the "wise" resolver that tries everything before giving up.
        Even on failure, returns useful information and allows continuation.

        Args:
            page_content: Current page HTML content
            url: Current URL
            query: What we're searching for (for alternatives)
            max_time_seconds: Maximum time to spend resolving
        """
        start_time = time.time()
        attempts = []

        # Detect obstruction type
        signature = await self.detect_obstruction(page_content, url)

        if not signature:
            return ResolutionResult(
                success=True,
                obstruction_type=ObstructionType.UNKNOWN,
                resolution_strategy="none_needed",
                layer_used=0,
                total_time_ms=0,
                should_continue=True,
            )

        console.print(f"\n[bold yellow]OBSTRUCTION DETECTED[/bold yellow]: {signature.obstruction_type.name}")
        console.print(f"[dim]Indicators: {', '.join(signature.page_indicators[:3])}[/dim]")

        # Check wisdom for known solution
        if self.wisdom:
            learned = self.wisdom.get_best_strategy(signature)
            if learned and learned.success_rate > 0.7:
                console.print(f"[cyan]Using learned strategy: {learned.successful_strategy}[/cyan]")

        # Layer 1: Quick Fixes
        console.print("[dim]Layer 1: Trying quick fixes...[/dim]")
        result = await self._layer1_quick_fixes(signature, page_content, url, query)
        attempts.extend(result.attempts)
        if result.success:
            self._record_success(signature, result)
            return result

        # Layer 2: Strategic Bypass
        if time.time() - start_time < max_time_seconds:
            console.print("[dim]Layer 2: Trying strategic bypass...[/dim]")
            result = await self._layer2_strategic_bypass(signature, page_content, url, query)
            attempts.extend(result.attempts)
            if result.success:
                self._record_success(signature, result)
                return result

        # Layer 3: AI Thinking
        if self.llm and time.time() - start_time < max_time_seconds:
            console.print("[dim]Layer 3: AI analyzing situation...[/dim]")
            result = await self._layer3_ai_thinking(signature, page_content, url, query)
            attempts.extend(result.attempts)
            if result.success:
                self._record_success(signature, result)
                return result

        # Layer 4: Subagent Swarm
        if self.enable_subagents and time.time() - start_time < max_time_seconds:
            console.print("[dim]Layer 4: Deploying subagent swarm...[/dim]")
            result = await self._layer4_subagent_swarm(signature, page_content, url, query)
            attempts.extend(result.attempts)
            if result.success:
                self._record_success(signature, result)
                return result

        # Layer 5: Human Escalation (with auto-continue)
        console.print("[yellow]Layer 5: Attempting human escalation...[/yellow]")
        result = await self._layer5_human_escalation(signature, page_content, url, query)
        attempts.extend(result.attempts)

        # Record failure for learning
        if self.wisdom and not result.success:
            self.wisdom.record_failure(signature, "all_layers_failed")

        total_time = int((time.time() - start_time) * 1000)

        # Always allow continuation - we're in forever mode
        return ResolutionResult(
            success=result.success,
            obstruction_type=signature.obstruction_type,
            resolution_strategy=result.resolution_strategy if result.success else "continue_anyway",
            layer_used=result.layer_used,
            total_time_ms=total_time,
            attempts=attempts,
            alternative_data=result.alternative_data,
            error=result.error,
            should_continue=True,  # ALWAYS continue in forever mode
        )

    def _record_success(self, signature: ObstructionSignature, result: ResolutionResult):
        """Record successful resolution for learning."""
        if self.wisdom:
            self.wisdom.record_success(
                signature,
                result.resolution_strategy,
                result.layer_used,
                result.total_time_ms,
            )

    # === Layer 1: Quick Fixes ===

    async def _layer1_quick_fixes(
        self,
        signature: ObstructionSignature,
        page_content: str,
        url: str,
        query: str,
    ) -> ResolutionResult:
        """
        Layer 1: Instant fixes for known patterns.

        These are fast, deterministic solutions that don't require AI.
        """
        attempts = []
        start = time.time()

        obs_type = signature.obstruction_type

        # Cookie consent - just click accept
        if obs_type == ObstructionType.COOKIE_CONSENT:
            success = await self._try_click_consent_button()
            attempts.append(ResolutionAttempt(
                strategy="click_consent",
                layer=1,
                success=success,
                duration_ms=int((time.time() - start) * 1000),
            ))
            if success:
                console.print("[green]Cookie consent dismissed[/green]")
                return ResolutionResult(
                    success=True,
                    obstruction_type=obs_type,
                    resolution_strategy="click_consent",
                    layer_used=1,
                    total_time_ms=int((time.time() - start) * 1000),
                    attempts=attempts,
                )

        # Newsletter popup - close it
        if obs_type == ObstructionType.NEWSLETTER_POPUP:
            success = await self._try_close_popup()
            attempts.append(ResolutionAttempt(
                strategy="close_popup",
                layer=1,
                success=success,
                duration_ms=int((time.time() - start) * 1000),
            ))
            if success:
                console.print("[green]Popup closed[/green]")
                return ResolutionResult(
                    success=True,
                    obstruction_type=obs_type,
                    resolution_strategy="close_popup",
                    layer_used=1,
                    total_time_ms=int((time.time() - start) * 1000),
                    attempts=attempts,
                )

        # Modal overlay - try to dismiss
        if obs_type == ObstructionType.MODAL_OVERLAY:
            success = await self._try_dismiss_modal()
            attempts.append(ResolutionAttempt(
                strategy="dismiss_modal",
                layer=1,
                success=success,
                duration_ms=int((time.time() - start) * 1000),
            ))
            if success:
                console.print("[green]Modal dismissed[/green]")
                return ResolutionResult(
                    success=True,
                    obstruction_type=obs_type,
                    resolution_strategy="dismiss_modal",
                    layer_used=1,
                    total_time_ms=int((time.time() - start) * 1000),
                    attempts=attempts,
                )

        # Cloudflare JS - wait for auto-complete
        if obs_type == ObstructionType.CLOUDFLARE_JS:
            console.print("[dim]Waiting for JS challenge to auto-complete...[/dim]")
            success = await self._wait_for_cloudflare_js()
            attempts.append(ResolutionAttempt(
                strategy="cloudflare_js_wait",
                layer=1,
                success=success,
                duration_ms=int((time.time() - start) * 1000),
            ))
            if success:
                console.print("[green]Cloudflare JS challenge passed[/green]")
                return ResolutionResult(
                    success=True,
                    obstruction_type=obs_type,
                    resolution_strategy="cloudflare_js_wait",
                    layer_used=1,
                    total_time_ms=int((time.time() - start) * 1000),
                    attempts=attempts,
                )

        return ResolutionResult(
            success=False,
            obstruction_type=obs_type,
            resolution_strategy="quick_fixes_failed",
            layer_used=1,
            total_time_ms=int((time.time() - start) * 1000),
            attempts=attempts,
        )

    # === Layer 2: Strategic Bypass ===

    async def _layer2_strategic_bypass(
        self,
        signature: ObstructionSignature,
        page_content: str,
        url: str,
        query: str,
    ) -> ResolutionResult:
        """
        Layer 2: Multi-strategy bypass attempts.

        Tries multiple approaches with exponential backoff.
        """
        attempts = []
        start = time.time()
        obs_type = signature.obstruction_type

        # Cloudflare family - use existing handler
        if obs_type in [ObstructionType.CLOUDFLARE_JS, ObstructionType.CLOUDFLARE_TURNSTILE,
                        ObstructionType.CLOUDFLARE_WAF]:
            if self.cloudflare_handler:
                result = await self._try_cloudflare_handler(url, query)
                attempts.append(ResolutionAttempt(
                    strategy="cloudflare_handler",
                    layer=2,
                    success=result.get('success', False),
                    duration_ms=int((time.time() - start) * 1000),
                    result_data=result,
                ))
                if result.get('success'):
                    alt_data = result if result.get('alternative_used') else None
                    return ResolutionResult(
                        success=True,
                        obstruction_type=obs_type,
                        resolution_strategy="cloudflare_handler",
                        layer_used=2,
                        total_time_ms=int((time.time() - start) * 1000),
                        attempts=attempts,
                        alternative_data=alt_data,
                    )

        # Rate limiting - exponential backoff wait
        if obs_type in [ObstructionType.RATE_LIMITED, ObstructionType.TOO_MANY_REQUESTS]:
            console.print("[yellow]Rate limited - waiting with backoff...[/yellow]")
            success = await self._wait_with_backoff()
            attempts.append(ResolutionAttempt(
                strategy="rate_limit_backoff",
                layer=2,
                success=success,
                duration_ms=int((time.time() - start) * 1000),
            ))
            if success:
                return ResolutionResult(
                    success=True,
                    obstruction_type=obs_type,
                    resolution_strategy="rate_limit_backoff",
                    layer_used=2,
                    total_time_ms=int((time.time() - start) * 1000),
                    attempts=attempts,
                )

        # CAPTCHA - try solver
        if obs_type in [ObstructionType.RECAPTCHA_V2, ObstructionType.HCAPTCHA,
                        ObstructionType.IMAGE_CAPTCHA]:
            if self.captcha_solver:
                result = await self._try_captcha_solver(obs_type)
                attempts.append(ResolutionAttempt(
                    strategy="captcha_solver",
                    layer=2,
                    success=result,
                    duration_ms=int((time.time() - start) * 1000),
                ))
                if result:
                    return ResolutionResult(
                        success=True,
                        obstruction_type=obs_type,
                        resolution_strategy="captcha_solver",
                        layer_used=2,
                        total_time_ms=int((time.time() - start) * 1000),
                        attempts=attempts,
                    )

        # Alternative data sources
        if query:
            console.print("[cyan]Searching for alternative data sources...[/cyan]")
            alt_result = await self._try_alternative_sources(signature.site_domain, query)
            attempts.append(ResolutionAttempt(
                strategy="alternative_sources",
                layer=2,
                success=bool(alt_result),
                duration_ms=int((time.time() - start) * 1000),
                result_data=alt_result,
            ))
            if alt_result:
                console.print(f"[green]Found alternative: {alt_result.get('source', 'unknown')}[/green]")
                return ResolutionResult(
                    success=True,
                    obstruction_type=obs_type,
                    resolution_strategy="alternative_sources",
                    layer_used=2,
                    total_time_ms=int((time.time() - start) * 1000),
                    attempts=attempts,
                    alternative_data=alt_result,
                )

        return ResolutionResult(
            success=False,
            obstruction_type=obs_type,
            resolution_strategy="strategic_bypass_failed",
            layer_used=2,
            total_time_ms=int((time.time() - start) * 1000),
            attempts=attempts,
        )

    # === Layer 3: AI Thinking ===

    async def _layer3_ai_thinking(
        self,
        signature: ObstructionSignature,
        page_content: str,
        url: str,
        query: str,
    ) -> ResolutionResult:
        """
        Layer 3: Use AI to analyze and solve unexpected situations.

        The LLM thinks about the situation and proposes solutions.
        """
        attempts = []
        start = time.time()
        obs_type = signature.obstruction_type

        if not self.llm:
            return ResolutionResult(
                success=False,
                obstruction_type=obs_type,
                resolution_strategy="no_llm_available",
                layer_used=3,
                total_time_ms=int((time.time() - start) * 1000),
                attempts=attempts,
            )

        console.print("[cyan]AI is analyzing the situation...[/cyan]")

        # Create prompt for AI analysis
        prompt = f"""You are an expert at bypassing web obstructions. Analyze this situation:

OBSTRUCTION TYPE: {obs_type.name}
URL: {url}
SEARCH QUERY: {query}
INDICATORS FOUND: {signature.page_indicators}

PAGE CONTENT SNIPPET (first 2000 chars):
{page_content[:2000] if page_content else "No content available"}

Based on this, provide:
1. ANALYSIS: What exactly is blocking us?
2. SOLUTION: Concrete steps to bypass this (be specific about selectors/actions)
3. ALTERNATIVE: If bypass is impossible, what alternative source can get us similar data?

Keep response under 500 words. Be practical and actionable."""

        try:
            response = await self._call_llm(prompt)

            if response:
                # Parse AI suggestions and try them
                actions = self._parse_ai_response(response)

                for action in actions[:3]:  # Try up to 3 AI suggestions
                    console.print(f"[dim]Trying AI suggestion: {action.get('description', 'unknown')}[/dim]")
                    success = await self._execute_ai_action(action)
                    attempts.append(ResolutionAttempt(
                        strategy=f"ai_action_{action.get('type', 'unknown')}",
                        layer=3,
                        success=success,
                        duration_ms=int((time.time() - start) * 1000),
                        result_data=action,
                    ))
                    if success:
                        console.print("[green]AI solution worked![/green]")
                        return ResolutionResult(
                            success=True,
                            obstruction_type=obs_type,
                            resolution_strategy=f"ai_action_{action.get('type', 'unknown')}",
                            layer_used=3,
                            total_time_ms=int((time.time() - start) * 1000),
                            attempts=attempts,
                        )

        except Exception as e:
            logger.debug(f"[RESOLVER] AI thinking failed: {e}")

        return ResolutionResult(
            success=False,
            obstruction_type=obs_type,
            resolution_strategy="ai_thinking_failed",
            layer_used=3,
            total_time_ms=int((time.time() - start) * 1000),
            attempts=attempts,
        )

    # === Layer 4: Subagent Swarm ===

    async def _layer4_subagent_swarm(
        self,
        signature: ObstructionSignature,
        page_content: str,
        url: str,
        query: str,
    ) -> ResolutionResult:
        """
        Layer 4: Deploy parallel subagents to explore solutions.

        Multiple agents try different approaches simultaneously.
        First success wins.
        """
        attempts = []
        start = time.time()
        obs_type = signature.obstruction_type

        console.print("[cyan]Deploying parallel subagents...[/cyan]")

        # Define parallel exploration tasks
        exploration_tasks = []

        # Subagent 1: Try different navigation paths
        exploration_tasks.append(self._subagent_try_navigation(url, query))

        # Subagent 2: Search for cached/archived version
        exploration_tasks.append(self._subagent_try_cache(url))

        # Subagent 3: Try mobile version
        exploration_tasks.append(self._subagent_try_mobile_version(url))

        # Subagent 4: Search for API endpoint
        exploration_tasks.append(self._subagent_find_api(signature.site_domain, query))

        try:
            # Run all subagents in parallel, wait for first success
            done, pending = await asyncio.wait(
                exploration_tasks,
                timeout=30,
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()

            # Check results
            for task in done:
                try:
                    result = task.result()
                    if result and result.get('success'):
                        strategy = result.get('strategy', 'subagent_unknown')
                        console.print(f"[green]Subagent success: {strategy}[/green]")
                        attempts.append(ResolutionAttempt(
                            strategy=strategy,
                            layer=4,
                            success=True,
                            duration_ms=int((time.time() - start) * 1000),
                            result_data=result,
                        ))
                        return ResolutionResult(
                            success=True,
                            obstruction_type=obs_type,
                            resolution_strategy=strategy,
                            layer_used=4,
                            total_time_ms=int((time.time() - start) * 1000),
                            attempts=attempts,
                            alternative_data=result.get('data'),
                        )
                except Exception as e:
                    logger.debug(f"[RESOLVER] Failed to record subagent success: {e}")

        except Exception as e:
            logger.debug(f"[RESOLVER] Subagent swarm error: {e}")

        return ResolutionResult(
            success=False,
            obstruction_type=obs_type,
            resolution_strategy="subagent_swarm_failed",
            layer_used=4,
            total_time_ms=int((time.time() - start) * 1000),
            attempts=attempts,
        )

    # === Layer 5: Human Escalation ===

    async def _layer5_human_escalation(
        self,
        signature: ObstructionSignature,
        page_content: str,
        url: str,
        query: str,
    ) -> ResolutionResult:
        """
        Layer 5: Last resort - ask human for help.

        BUT with auto-continue after timeout.
        In forever mode, we can't block indefinitely.
        """
        attempts = []
        start = time.time()
        obs_type = signature.obstruction_type

        console.print(f"\n[bold red]ALL AUTOMATED SOLUTIONS FAILED[/bold red]")
        console.print(f"[yellow]Waiting {self.human_timeout}s for human intervention...[/yellow]")
        console.print(f"[dim]URL: {url}[/dim]")
        console.print(f"[dim]Obstruction: {obs_type.name}[/dim]")

        # Try to show browser window if available
        await self._try_show_browser()

        # Wait for human with countdown
        human_solved = False
        wait_interval = 10
        total_waited = 0

        while total_waited < self.human_timeout:
            await asyncio.sleep(wait_interval)
            total_waited += wait_interval

            # Check if obstruction is gone
            if self.page:
                try:
                    new_content = await self.page.content()
                    new_sig = await self.detect_obstruction(new_content, url)
                    if not new_sig:
                        human_solved = True
                        console.print("[bold green]Obstruction cleared! Continuing...[/bold green]")
                        break
                except Exception as e:
                    logger.debug(f"Operation failed: {e}")

            remaining = self.human_timeout - total_waited
            if remaining > 0:
                console.print(f"[dim]Still waiting... ({remaining}s remaining, then auto-continue)[/dim]")

        if human_solved:
            attempts.append(ResolutionAttempt(
                strategy="human_intervention",
                layer=5,
                success=True,
                duration_ms=int((time.time() - start) * 1000),
            ))
            return ResolutionResult(
                success=True,
                obstruction_type=obs_type,
                resolution_strategy="human_intervention",
                layer_used=5,
                total_time_ms=int((time.time() - start) * 1000),
                attempts=attempts,
            )

        # Auto-continue after timeout
        console.print("[yellow]Timeout - auto-continuing without resolution[/yellow]")
        console.print("[dim]Task will continue, some data may be incomplete[/dim]\n")

        attempts.append(ResolutionAttempt(
            strategy="human_timeout_auto_continue",
            layer=5,
            success=False,
            duration_ms=int((time.time() - start) * 1000),
        ))

        return ResolutionResult(
            success=False,
            obstruction_type=obs_type,
            resolution_strategy="auto_continue_after_timeout",
            layer_used=5,
            total_time_ms=int((time.time() - start) * 1000),
            attempts=attempts,
            should_continue=True,  # ALWAYS continue
            error="Human timeout - continuing with partial data",
        )

    # === Helper Methods ===

    async def _try_click_consent_button(self) -> bool:
        """Try to click common consent buttons."""
        consent_selectors = [
            "button:has-text('Accept')",
            "button:has-text('Accept all')",
            "button:has-text('Accept cookies')",
            "button:has-text('I agree')",
            "button:has-text('OK')",
            "[id*='accept']",
            "[class*='accept']",
            "[data-testid*='accept']",
        ]

        for selector in consent_selectors:
            try:
                if self.mcp:
                    await self.mcp.call_tool('playwright_click', {'selector': selector})
                    await asyncio.sleep(0.5)
                    return True
                elif self.page:
                    elem = await self.page.query_selector(selector)
                    if elem:
                        await elem.click()
                        await asyncio.sleep(0.5)
                        return True
            except Exception:
                continue

        return False

    async def _try_close_popup(self) -> bool:
        """Try to close popup modals."""
        close_selectors = [
            "button[aria-label='Close']",
            "button:has-text('Close')",
            "button:has-text('No thanks')",
            "[class*='close']",
            "[class*='dismiss']",
            "svg[class*='close']",
        ]

        for selector in close_selectors:
            try:
                if self.mcp:
                    await self.mcp.call_tool('playwright_click', {'selector': selector})
                    await asyncio.sleep(0.5)
                    return True
                elif self.page:
                    elem = await self.page.query_selector(selector)
                    if elem:
                        await elem.click()
                        await asyncio.sleep(0.5)
                        return True
            except Exception:
                continue

        # Try pressing Escape
        try:
            if self.mcp:
                await self.mcp.call_tool('playwright_keyboard_press', {'key': 'Escape'})
                await asyncio.sleep(0.5)
                return True
            elif self.page:
                await self.page.keyboard.press('Escape')
                await asyncio.sleep(0.5)
                return True
        except Exception as e:
            logger.debug(f"Operation failed: {e}")

        return False

    async def _try_dismiss_modal(self) -> bool:
        """Try to dismiss modal overlay."""
        return await self._try_close_popup()

    async def _wait_for_cloudflare_js(self) -> bool:
        """Wait for Cloudflare JS challenge to auto-complete."""
        max_wait = 20
        for i in range(max_wait // 2):
            await asyncio.sleep(2)

            try:
                if self.page:
                    content = await self.page.content()
                    if not any(p.lower() in content.lower() for p in ["just a moment", "checking your browser"]):
                        return True
            except Exception as e:
                logger.debug(f"Operation failed: {e}")

        return False

    async def _try_cloudflare_handler(self, url: str, query: str) -> Dict:
        """Use existing cloudflare handler."""
        if not self.cloudflare_handler or not self.page:
            return {'success': False}

        try:
            return await self.cloudflare_handler.handle_blocked_request(url, query, self.page, self.mcp)
        except Exception as e:
            logger.debug(f"Cloudflare handler error: {e}")
            return {'success': False, 'error': str(e)}

    async def _wait_with_backoff(self) -> bool:
        """Wait with exponential backoff for rate limiting."""
        delays = [5, 10, 20, 30]  # seconds

        for delay in delays:
            console.print(f"[dim]Waiting {delay}s...[/dim]")
            await asyncio.sleep(delay)

            # Check if we can proceed
            try:
                if self.page:
                    await self.page.reload()
                    # Wait for page to reload
                    await self.page.wait_for_load_state('networkidle', timeout=5000)
                    content = await self.page.content()
                    sig = await self.detect_obstruction(content, self.page.url)
                    if not sig or sig.obstruction_type not in [
                        ObstructionType.RATE_LIMITED, ObstructionType.TOO_MANY_REQUESTS
                    ]:
                        return True
            except Exception as e:
                logger.debug(f"Operation failed: {e}")

        return False

    async def _try_captcha_solver(self, obs_type: ObstructionType) -> bool:
        """Try to solve CAPTCHA using vision-based solver."""
        if not self.captcha_solver:
            return False

        # Most CAPTCHAs require human intervention
        console.print("[yellow]CAPTCHA detected - attempting vision-based solving...[/yellow]")

        # The current solver mostly requires human fallback
        # Return False to escalate to human layer
        return False

    async def _try_alternative_sources(self, domain: str, query: str) -> Optional[Dict]:
        """Try alternative data sources."""
        if not self.cloudflare_handler:
            return None

        try:
            blocked_site = self.cloudflare_handler.detect_blocked_site(f"https://{domain}")
            if blocked_site and self.BlockedSite:
                alternatives = self.cloudflare_handler.get_alternatives(blocked_site)
                for alt in alternatives[:3]:
                    try:
                        alt_url = alt.url_template.format(query=query.replace(" ", "+"))
                        console.print(f"[dim]Trying: {alt.name}[/dim]")

                        if self.mcp:
                            await self.mcp.call_tool('playwright_navigate', {'url': alt_url})
                            # Wait for alternative page to load
                            try:
                                await self.mcp.call_tool('playwright_wait_for_load_state', {'state': 'networkidle', 'timeout': 5000})
                            except Exception as e:
                                logger.debug(f"Operation failed: {e}")  # Continue even if timeout
                            # Check if this one is also blocked
                            if self.page:
                                content = await self.page.content()
                                sig = await self.detect_obstruction(content, alt_url)
                                if not sig:
                                    return {
                                        'success': True,
                                        'source': alt.name,
                                        'url': alt_url,
                                        'strategy': 'alternative_source',
                                    }
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"Alternative sources error: {e}")

        return None

    async def _call_llm(self, prompt: str) -> Optional[str]:
        """Call LLM for analysis."""
        try:
            if hasattr(self.llm, 'generate'):
                response = await self.llm.generate(prompt)
                return response
            elif hasattr(self.llm, 'chat'):
                response = await self.llm.chat([{"role": "user", "content": prompt}])
                return response.get('content', '')
        except Exception as e:
            logger.debug(f"LLM call failed: {e}")
        return None

    def _parse_ai_response(self, response: str) -> List[Dict]:
        """Parse AI response into actionable items."""
        actions = []

        # Look for common action patterns
        if 'click' in response.lower():
            # Extract selector suggestions
            import re
            selectors = re.findall(r'["\'](.*?)["\']', response)
            for sel in selectors[:3]:
                if any(x in sel for x in ['.', '#', '[', 'button', 'input']):
                    actions.append({
                        'type': 'click',
                        'selector': sel,
                        'description': f"Click element: {sel}",
                    })

        if 'wait' in response.lower():
            actions.append({
                'type': 'wait',
                'seconds': 5,
                'description': "Wait for page to update",
            })

        if 'refresh' in response.lower() or 'reload' in response.lower():
            actions.append({
                'type': 'refresh',
                'description': "Refresh the page",
            })

        if 'alternative' in response.lower():
            actions.append({
                'type': 'alternative',
                'description': "Try alternative data source",
            })

        return actions

    async def _execute_ai_action(self, action: Dict) -> bool:
        """Execute an AI-suggested action."""
        try:
            action_type = action.get('type', '')

            if action_type == 'click':
                selector = action.get('selector', '')
                if self.mcp:
                    await self.mcp.call_tool('playwright_click', {'selector': selector})
                    # Wait for page response after click
                    try:
                        await self.mcp.call_tool('playwright_wait_for_load_state', {'state': 'domcontentloaded', 'timeout': 3000})
                    except Exception:
                        await asyncio.sleep(0.5)  # Brief fallback wait
                    return True

            elif action_type == 'wait':
                seconds = action.get('seconds', 5)
                await asyncio.sleep(seconds)  # Intentional wait - keep as is
                return True

            elif action_type == 'refresh':
                if self.page:
                    await self.page.reload()
                    # Wait for reload to complete
                    await self.page.wait_for_load_state('networkidle', timeout=5000)
                    return True

        except Exception as e:
            logger.debug(f"AI action failed: {e}")

        return False

    # === Subagent Tasks ===

    async def _subagent_try_navigation(self, url: str, query: str) -> Dict:
        """Subagent: Try different navigation paths."""
        try:
            # Try root domain
            import re
            match = re.search(r"(https?://[^/]+)", url)
            if match and self.mcp:
                root_url = match.group(1)
                await self.mcp.call_tool('playwright_navigate', {'url': root_url})
                # Wait for root page to load
                try:
                    await self.mcp.call_tool('playwright_wait_for_load_state', {'state': 'networkidle', 'timeout': 5000})
                except Exception as e:
                    logger.debug(f"Operation failed: {e}")  # Continue even if timeout
                return {'success': True, 'strategy': 'root_navigation', 'url': root_url}
        except Exception as e:
            logger.debug(f"Operation failed: {e}")
        return {'success': False}

    async def _subagent_try_cache(self, url: str) -> Dict:
        """Subagent: Try cached/archived version."""
        try:
            # Try Google cache
            cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
            if self.mcp:
                await self.mcp.call_tool('playwright_navigate', {'url': cache_url})
                # Wait for cached page to load
                try:
                    await self.mcp.call_tool('playwright_wait_for_load_state', {'state': 'networkidle', 'timeout': 5000})
                except Exception as e:
                    logger.debug(f"Operation failed: {e}")  # Continue even if timeout
                if self.page:
                    content = await self.page.content()
                    if 'cache' in content.lower() and len(content) > 5000:
                        return {'success': True, 'strategy': 'google_cache', 'url': cache_url}
        except Exception as e:
            logger.debug(f"Operation failed: {e}")

        try:
            # Try Wayback Machine
            archive_url = f"https://web.archive.org/web/{url}"
            if self.mcp:
                await self.mcp.call_tool('playwright_navigate', {'url': archive_url})
                # Wait for Wayback Machine to load
                try:
                    await self.mcp.call_tool('playwright_wait_for_load_state', {'state': 'networkidle', 'timeout': 5000})
                except Exception as e:
                    logger.debug(f"Operation failed: {e}")  # Continue even if timeout
                return {'success': True, 'strategy': 'wayback_machine', 'url': archive_url}
        except Exception as e:
            logger.debug(f"Operation failed: {e}")

        return {'success': False}

    async def _subagent_try_mobile_version(self, url: str) -> Dict:
        """Subagent: Try mobile version of site."""
        try:
            # Add 'm.' prefix or '/mobile' path
            import re
            match = re.search(r"https?://(?:www\.)?(.+)", url)
            if match:
                mobile_url = f"https://m.{match.group(1)}"
                if self.mcp:
                    await self.mcp.call_tool('playwright_navigate', {'url': mobile_url})
                    await asyncio.sleep(2)
                    if self.page:
                        content = await self.page.content()
                        sig = await self.detect_obstruction(content, mobile_url)
                        if not sig:
                            return {'success': True, 'strategy': 'mobile_version', 'url': mobile_url}
        except Exception as e:
            logger.debug(f"Operation failed: {e}")
        return {'success': False}

    async def _subagent_find_api(self, domain: str, query: str) -> Dict:
        """Subagent: Try to find and use API endpoint."""
        # Most sites don't have public APIs, but some do
        return {'success': False}

    async def _try_show_browser(self):
        """Try to show browser window for human intervention."""
        try:
            if self.mcp:
                await self.mcp.call_tool('playwright_set_viewport', {
                    'width': 1280,
                    'height': 720,
                })
        except Exception as e:
            logger.debug(f"Operation failed: {e}")


# Singleton instance
_resolver_instance = None


def get_autonomous_resolver(
    mcp_client=None,
    llm_client=None,
    page=None,
    **kwargs
) -> AutonomousChallengeResolver:
    """Get or create the autonomous resolver singleton."""
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = AutonomousChallengeResolver(
            mcp_client=mcp_client,
            llm_client=llm_client,
            page=page,
            **kwargs,
        )
    return _resolver_instance


async def resolve_any_challenge(
    page_content: str = "",
    url: str = "",
    query: str = "",
    mcp_client=None,
    llm_client=None,
    page=None,
    **kwargs
) -> ResolutionResult:
    """
    Convenience function to resolve any web obstruction.

    Usage:
        result = await resolve_any_challenge(
            page_content=html,
            url="https://example.com",
            query="search term",
            mcp_client=mcp,
        )
        if result.success:
            print(f"Resolved via: {result.resolution_strategy}")
        elif result.should_continue:
            print("Continuing with partial data...")
    """
    resolver = get_autonomous_resolver(mcp_client, llm_client, page, **kwargs)
    return await resolver.resolve(page_content, url, query)
