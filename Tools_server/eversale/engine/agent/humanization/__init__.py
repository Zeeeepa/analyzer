"""
Humanization Module - Make browser automation indistinguishable from humans

This module implements research-backed techniques from:
- Emunium: Human-like Playwright automation
- HumanCursor: Bezier curve mouse movements with Bernstein polynomials
- Ghost Cursor: Fitts's Law mouse patterns
- human-keyboard: Typing with errors and fatigue
- Browser-Use: Agent perception patterns + 3-source DOM fusion
- Stagehand: Self-healing selectors
- Multilogin/GoLogin: Antidetect fingerprinting techniques

Key Components:
- BezierCursor: Ultra-realistic mouse movements with tremor and easing
- HumanTyper: Typing with errors, corrections, and fatigue modeling
- HumanScroller: Natural scrolling patterns
- ContinuousPerception: "See" the page like a human (constant visual awareness)
- ProfileManager: Persistent browser profiles with real session data
- SelfHealingSelectors: Selectors that fix themselves when sites change
- AntidetectFingerprint: Multilogin-style browser fingerprint randomization
- PatternRandomizer: Adds entropy to ALL patterns to prevent detection
- DOMFusion: 3-source element detection (DOM + A11y + Snapshot)
- FastTrackSafety: FAST_TRACK mode safety validator (skip humanization for internal tools)

FAST_TRACK Mode:
    For high-volume, non-sensitive tasks on internal tools, you can skip humanization
    to significantly speed up automation. FAST_TRACK mode:
    - Uses direct cursor movement (no bezier curves)
    - Types instantly (no delays or errors)
    - Scrolls instantly (no momentum or pauses)

    CRITICAL: FAST_TRACK is ONLY safe for:
    - Internal dashboards/tools
    - Local development (localhost)
    - Private admin panels
    - Trusted APIs

    NEVER use on public websites - FastTrackSafety enforces this automatically.

Usage:
    from agent.humanization import (
        BezierCursor, HumanTyper, HumanScroller,
        CursorConfig, TypingConfig, ScrollConfig,
        FastTrackSafety, is_fast_track_safe,
        ContinuousPerception, ProfileManager, SelfHealingSelectors,
        AntidetectFingerprint, PatternRandomizer, DOMFusion,
        get_default_profile, get_persistent_context_args
    )

    # Human-like clicking (normal mode)
    cursor = BezierCursor()
    await cursor.click_at(page, selector=".submit-btn")

    # Human-like typing with errors
    typer = HumanTyper()
    await typer.type_text(page, "Hello world", selector="#input")

    # FAST_TRACK mode for high-volume internal tasks
    url = "https://internal-dashboard.company.local"
    if is_fast_track_safe(url):
        # Create configs with FAST_TRACK enabled
        cursor_config = CursorConfig(fast_track=True)
        typer_config = TypingConfig(fast_track=True)
        scroller_config = ScrollConfig(fast_track=True)

        cursor = BezierCursor(config=cursor_config)
        typer = HumanTyper(config=typer_config)
        scroller = HumanScroller(config=scroller_config)

        # Now all actions are instant - perfect for processing 1000+ items
        for item in items:  # Fast processing
            await cursor.click_at(page, selector=f".item-{item}")
            await typer.type_text(page, item.data, selector="#input")
            await page.keyboard.press('Enter')

    # Continuous visual awareness
    perception = ContinuousPerception(page)
    await perception.start()
    state = perception.get_state()

    # Persistent browser profile
    profile = get_default_profile()
    args = get_persistent_context_args()

    # Antidetect fingerprinting
    antidetect = AntidetectFingerprint()
    profile = antidetect.create_profile("session-123")
    js = antidetect.get_injection_script(profile)

    # 3-source DOM fusion
    fusion = DOMFusion()
    elements = await fusion.analyze(page)
    buttons = await fusion.find_by_role(page, "button")
"""

from .bezier_cursor import BezierCursor, move_human, click_human, get_cursor, CursorConfig
from .human_typer import HumanTyper, type_human, get_typer, TypingConfig
from .human_scroller import HumanScroller, scroll_human, get_scroller, ScrollConfig
from .continuous_perception import ContinuousPerception, perceive_page, PerceptionState, PerceptionConfig
from .profile_manager import (
    ProfileManager, BrowserProfile, get_default_profile,
    get_profile_manager, get_profile_path, get_persistent_context_args
)
from .self_healing_selectors import (
    SelfHealingSelectors, SelectorMatch, find_element_healing
)
from .antidetect_fingerprint import (
    AntidetectFingerprint, FingerprintProfile, SeededRandom,
    get_fingerprint_generator, create_fingerprint, get_fingerprint_script
)
from .pattern_randomizer import (
    PatternRandomizer, RandomizerConfig, get_randomizer,
    new_session, randomize_delay, should_pause, get_pause
)
from .dom_fusion import (
    DOMFusion, FusedElement, analyze_page, get_clickable_elements
)
from .fast_track_safety import (
    FastTrackSafety, SafetyConfig, get_safety_checker,
    is_fast_track_safe, enforce_fast_track_safety
)

__all__ = [
    # Cursor
    'BezierCursor',
    'CursorConfig',
    'move_human',
    'click_human',
    'get_cursor',

    # Typing
    'HumanTyper',
    'TypingConfig',
    'type_human',
    'get_typer',

    # Scrolling
    'HumanScroller',
    'ScrollConfig',
    'scroll_human',
    'get_scroller',

    # Perception
    'ContinuousPerception',
    'PerceptionState',
    'PerceptionConfig',
    'perceive_page',

    # Profiles
    'ProfileManager',
    'BrowserProfile',
    'get_default_profile',
    'get_profile_manager',
    'get_profile_path',
    'get_persistent_context_args',

    # Self-healing
    'SelfHealingSelectors',
    'SelectorMatch',
    'find_element_healing',

    # Antidetect Fingerprinting
    'AntidetectFingerprint',
    'FingerprintProfile',
    'SeededRandom',
    'get_fingerprint_generator',
    'create_fingerprint',
    'get_fingerprint_script',

    # Pattern Randomization
    'PatternRandomizer',
    'RandomizerConfig',
    'get_randomizer',
    'new_session',
    'randomize_delay',
    'should_pause',
    'get_pause',

    # DOM Fusion (3-source element detection)
    'DOMFusion',
    'FusedElement',
    'analyze_page',
    'get_clickable_elements',

    # FAST_TRACK Safety
    'FastTrackSafety',
    'SafetyConfig',
    'get_safety_checker',
    'is_fast_track_safe',
    'enforce_fast_track_safety',
]
