"""
Stealth Utilities - Make browser automation undetectable

Comprehensive anti-bot detection measures:
- Human-like delays and timing
- Proper browser fingerprinting
- Mouse movement simulation with Bernstein polynomial Bezier curves
- Typing patterns with errors, corrections, and fatigue
- WebGL/Canvas fingerprint spoofing
- Persistent browser profiles with session data

ARCHITECTURE (2025):
This module now integrates with the humanization module for advanced features:
- agent.humanization.bezier_cursor: Bernstein polynomial Bezier curves
- agent.humanization.human_typer: QWERTY error typing with fatigue
- agent.humanization.human_scroller: Natural scroll patterns
- agent.humanization.continuous_perception: Visual awareness loop
- agent.humanization.profile_manager: Persistent browser sessions
- agent.humanization.self_healing_selectors: Auto-fixing selectors

The basic functions here are preserved for backward compatibility.
For new code, prefer importing directly from agent.humanization.
"""

import asyncio
import random
import math
from typing import Optional, Tuple, List
from loguru import logger

# Import advanced humanization module
HUMANIZATION_AVAILABLE = False
ANTIDETECT_AVAILABLE = False
PATTERN_RANDOMIZER_AVAILABLE = False
DOM_FUSION_AVAILABLE = False

try:
    from .humanization import (
        BezierCursor, get_cursor,
        HumanTyper, get_typer,
        HumanScroller, get_scroller,
        SelfHealingSelectors, find_element_healing,
        get_persistent_context_args, get_default_profile
    )
    HUMANIZATION_AVAILABLE = True
except ImportError as e:
    logger.debug(f"Advanced humanization module not available: {e}")

# Import antidetect fingerprinting (Multilogin-style)
try:
    from .humanization import (
        AntidetectFingerprint, get_fingerprint_generator, create_fingerprint, get_fingerprint_script
    )
    ANTIDETECT_AVAILABLE = True
except ImportError as e:
    logger.debug(f"Antidetect fingerprint module not available: {e}")

# Import pattern randomizer (prevents behavioral fingerprinting)
try:
    from .humanization import (
        PatternRandomizer, get_randomizer, randomize_delay, new_session
    )
    PATTERN_RANDOMIZER_AVAILABLE = True
except ImportError as e:
    logger.debug(f"Pattern randomizer module not available: {e}")

# Import DOM fusion (3-source element detection)
try:
    from .humanization import (
        DOMFusion, FusedElement, analyze_page, get_clickable_elements
    )
    DOM_FUSION_AVAILABLE = True
except ImportError as e:
    logger.debug(f"DOM fusion module not available: {e}")

# Import visual fallback for screenshot + click when selectors fail
try:
    from .selector_fallbacks import get_visual_fallback
    VISUAL_FALLBACK_AVAILABLE = True
except ImportError:
    VISUAL_FALLBACK_AVAILABLE = False
    get_visual_fallback = None


# ============================================================================
# STEALTH BROWSER LAUNCH ARGUMENTS
# ============================================================================

# Import enhanced stealth config (Playwright MCP compatible)
ENHANCED_STEALTH_AVAILABLE = False
try:
    from .stealth_browser_config import (
        get_mcp_compatible_launch_args,
        get_chrome_context_options
    )
    ENHANCED_STEALTH_AVAILABLE = True
except ImportError:
    logger.debug("Enhanced stealth config not available, using built-in args")


def get_stealth_args() -> List[str]:
    """
    Get Chrome launch arguments that bypass bot detection.

    Uses enhanced MCP-compatible config when available (proven to bypass
    Cloudflare and other anti-bot systems). Falls back to built-in args
    if enhanced config not available.
    """
    # Use enhanced MCP-compatible config when available
    if ENHANCED_STEALTH_AVAILABLE:
        return get_mcp_compatible_launch_args()

    # Fallback to basic stealth args
    return [
        # Core stealth flags
        "--disable-blink-features=AutomationControlled",
        "--disable-automation",
        "--disable-infobars",

        # Remove "Chrome is being controlled by automated test software" bar
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-breakpad",
        "--disable-component-extensions-with-background-pages",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--disable-features=TranslateUI",
        "--disable-hang-monitor",
        "--disable-ipc-flooding-protection",
        "--disable-popup-blocking",
        "--disable-prompt-on-repost",
        "--disable-renderer-backgrounding",
        "--disable-sync",
        "--enable-features=NetworkService,NetworkServiceInProcess",
        "--force-color-profile=srgb",
        "--metrics-recording-only",
        "--no-first-run",
        "--password-store=basic",
        "--use-mock-keychain",

        # Disable all Chrome popups and warnings
        "--disable-session-crashed-bubble",  # No "restore pages" popup
        "--disable-save-password-bubble",    # No password save prompts
        "--disable-translate",               # No translate bar
        "--disable-features=InfiniteSessionRestore",  # No session restore
        "--disable-features=TranslateUI,BlinkGenPropertyTrees",
        "--noerrdialogs",                    # No error dialogs
        "--disable-crash-reporter",          # No crash reporter
        "--hide-crash-restore-bubble",       # Hide restore bubble
        "--suppress-message-center-popups",  # Suppress all popups

        # Disable Google API key warning and unsupported flag warnings
        "--disable-client-side-phishing-detection",
        "--disable-component-cloud-policy",
        "--disable-datasaver-prompt",
        "--disable-domain-reliability",
        "--disable-features=AudioServiceOutOfProcess",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-notifications",
        "--log-level=3",  # Suppress console warnings

        # GPU and rendering (look like real browser)
        "--enable-webgl",
        "--enable-accelerated-2d-canvas",
        "--ignore-gpu-blocklist",

        # Make it look like regular Chrome
        "--no-sandbox",
        "--disable-setuid-sandbox",
        # Compact window size - professional, doesn't dominate screen
        "--window-size=1280,800",
        # Start minimized so it doesn't pop up on top
        "--start-minimized",
        "--window-position=50,50",  # Bottom-right when visible

        # Disable automation detection features
        "--disable-web-security",
        "--allow-running-insecure-content",
    ]


def get_realistic_user_agents() -> List[str]:
    """
    Get realistic user agent strings that match real browser distributions.
    Updated for late 2024/early 2025.
    """
    return [
        # Chrome on Windows (most common)
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",

        # Chrome on Mac
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",

        # Edge on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    ]


def get_random_user_agent() -> str:
    """Get a random realistic user agent, weighted toward Chrome on Windows"""
    agents = get_realistic_user_agents()
    # Weight toward first few (Chrome/Windows) since that's most common
    weights = [0.3, 0.25, 0.15, 0.1, 0.1, 0.05, 0.05]
    return random.choices(agents, weights=weights)[0]


# ============================================================================
# ANTI-FINGERPRINTING JAVASCRIPT
# ============================================================================

def get_stealth_js() -> str:
    """
    JavaScript to inject into pages to bypass fingerprinting detection.
    This runs before any page scripts to hide automation indicators.
    """
    return """
    // ========== WEBRTC IP LEAK PROTECTION ==========

    // Block WebRTC IP leak
    (function() {
        const originalRTCPeerConnection = window.RTCPeerConnection || window.webkitRTCPeerConnection || window.mozRTCPeerConnection;

        if (originalRTCPeerConnection) {
            window.RTCPeerConnection = function(...args) {
                const pc = new originalRTCPeerConnection(...args);

                // Override createOffer to prevent IP leak
                const originalCreateOffer = pc.createOffer.bind(pc);
                pc.createOffer = async function(options) {
                    try {
                        const offer = await originalCreateOffer(options);
                        // Remove candidate lines that leak IP
                        if (offer && offer.sdp) {
                            offer.sdp = offer.sdp.replace(/a=candidate:.+typ host.+\\r\\n/g, '');
                        }
                        return offer;
                    } catch(e) {
                        throw e;
                    }
                };

                // Override createAnswer similarly
                const originalCreateAnswer = pc.createAnswer.bind(pc);
                pc.createAnswer = async function(options) {
                    try {
                        const answer = await originalCreateAnswer(options);
                        if (answer && answer.sdp) {
                            answer.sdp = answer.sdp.replace(/a=candidate:.+typ host.+\\r\\n/g, '');
                        }
                        return answer;
                    } catch(e) {
                        throw e;
                    }
                };

                return pc;
            };

            window.RTCPeerConnection.prototype = originalRTCPeerConnection.prototype;

            // Also set webkit prefixed version
            if (window.webkitRTCPeerConnection) {
                window.webkitRTCPeerConnection = window.RTCPeerConnection;
            }
        }

        // Block navigator.mediaDevices getUserMedia unless needed
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            const originalGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
            navigator.mediaDevices.getUserMedia = async function(constraints) {
                // Block video/audio access to prevent fingerprinting
                if (constraints && (constraints.video || constraints.audio)) {
                    throw new DOMException('Permission denied', 'NotAllowedError');
                }
                return originalGetUserMedia(constraints);
            };
        }
    })();

    // ========== PERFORMANCE TIMING SPOOFING ==========

    (function() {
        // Spoof performance.timing to look like real browser
        const realTiming = performance.timing;
        const navigationStart = realTiming.navigationStart;

        // Create realistic timing values with natural variance
        const fakeTiming = {
            navigationStart: navigationStart,
            unloadEventStart: 0,
            unloadEventEnd: 0,
            redirectStart: 0,
            redirectEnd: 0,
            fetchStart: navigationStart + Math.floor(Math.random() * 10) + 1,
            domainLookupStart: navigationStart + Math.floor(Math.random() * 20) + 10,
            domainLookupEnd: navigationStart + Math.floor(Math.random() * 30) + 25,
            connectStart: navigationStart + Math.floor(Math.random() * 40) + 30,
            connectEnd: navigationStart + Math.floor(Math.random() * 60) + 50,
            secureConnectionStart: navigationStart + Math.floor(Math.random() * 50) + 40,
            requestStart: navigationStart + Math.floor(Math.random() * 80) + 60,
            responseStart: navigationStart + Math.floor(Math.random() * 150) + 100,
            responseEnd: navigationStart + Math.floor(Math.random() * 200) + 150,
            domLoading: navigationStart + Math.floor(Math.random() * 250) + 180,
            domInteractive: navigationStart + Math.floor(Math.random() * 400) + 300,
            domContentLoadedEventStart: navigationStart + Math.floor(Math.random() * 500) + 350,
            domContentLoadedEventEnd: navigationStart + Math.floor(Math.random() * 550) + 400,
            domComplete: navigationStart + Math.floor(Math.random() * 800) + 500,
            loadEventStart: navigationStart + Math.floor(Math.random() * 850) + 550,
            loadEventEnd: navigationStart + Math.floor(Math.random() * 900) + 600
        };

        // Override performance.timing
        Object.defineProperty(performance, 'timing', {
            get: function() {
                return new Proxy(realTiming, {
                    get: function(target, prop) {
                        if (prop in fakeTiming) {
                            return fakeTiming[prop];
                        }
                        return target[prop];
                    }
                });
            },
            configurable: true
        });

        // Also spoof performance.getEntriesByType
        const originalGetEntriesByType = performance.getEntriesByType.bind(performance);
        performance.getEntriesByType = function(type) {
            const entries = originalGetEntriesByType(type);
            if (type === 'navigation') {
                // Add realistic variance to navigation entries
                return entries.map(e => {
                    const clone = {};
                    for (let key in e) {
                        if (typeof e[key] === 'number' && key.toLowerCase().includes('time')) {
                            clone[key] = e[key] + Math.floor(Math.random() * 50);
                        } else {
                            clone[key] = e[key];
                        }
                    }
                    return clone;
                });
            }
            return entries;
        };
    })();

    // ========== SEC-CH-UA HEADERS (Client Hints) ==========

    (function() {
        // Add proper Sec-CH-UA via navigator.userAgentData
        const brands = [
            { brand: "Chromium", version: "120" },
            { brand: "Google Chrome", version: "120" },
            { brand: "Not=A?Brand", version: "24" }
        ];

        Object.defineProperty(navigator, 'userAgentData', {
            get: function() {
                return {
                    brands: brands,
                    mobile: false,
                    platform: "Windows",
                    getHighEntropyValues: async function(hints) {
                        return {
                            brands: brands,
                            mobile: false,
                            platform: "Windows",
                            platformVersion: "15.0.0",
                            architecture: "x86",
                            bitness: "64",
                            model: "",
                            uaFullVersion: "120.0.6099.130",
                            fullVersionList: brands
                        };
                    },
                    toJSON: function() {
                        return {
                            brands: brands,
                            mobile: false,
                            platform: "Windows"
                        };
                    }
                };
            },
            configurable: true
        });
    })();

    // Override navigator.webdriver to return undefined
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });

    // Override navigator.plugins to look like real browser
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const plugins = [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
            ];
            plugins.item = (i) => plugins[i];
            plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
            plugins.refresh = () => {};
            return plugins;
        },
        configurable: true
    });

    // Override navigator.languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
        configurable: true
    });

    // Override navigator.platform
    Object.defineProperty(navigator, 'platform', {
        get: () => 'Win32',
        configurable: true
    });

    // Override navigator.hardwareConcurrency (CPU cores)
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => 8,
        configurable: true
    });

    // Override navigator.deviceMemory
    Object.defineProperty(navigator, 'deviceMemory', {
        get: () => 8,
        configurable: true
    });

    // Fix Chrome runtime check
    window.chrome = {
        app: { isInstalled: false, InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' }, RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' } },
        runtime: { OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' }, OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' }, PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' }, PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' }, PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' }, RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' } }
    };

    // Override permissions query
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );

    // WebGL vendor/renderer spoofing
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        // UNMASKED_VENDOR_WEBGL
        if (parameter === 37445) {
            return 'Google Inc. (NVIDIA)';
        }
        // UNMASKED_RENDERER_WEBGL
        if (parameter === 37446) {
            return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1080 Direct3D11 vs_5_0 ps_5_0, D3D11)';
        }
        return getParameter.apply(this, arguments);
    };

    // WebGL2 vendor/renderer spoofing
    if (typeof WebGL2RenderingContext !== 'undefined') {
        const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) {
                return 'Google Inc. (NVIDIA)';
            }
            if (parameter === 37446) {
                return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1080 Direct3D11 vs_5_0 ps_5_0, D3D11)';
            }
            return getParameter2.apply(this, arguments);
        };
    }

    // Override console.debug to prevent detection logging
    const originalDebug = console.debug;
    console.debug = function(...args) {
        if (args.length && typeof args[0] === 'string' && args[0].includes('automation')) {
            return;
        }
        return originalDebug.apply(this, args);
    };

    // Spoof screen resolution
    Object.defineProperty(screen, 'width', { get: () => 1920, configurable: true });
    Object.defineProperty(screen, 'height', { get: () => 1080, configurable: true });
    Object.defineProperty(screen, 'availWidth', { get: () => 1920, configurable: true });
    Object.defineProperty(screen, 'availHeight', { get: () => 1040, configurable: true });
    Object.defineProperty(screen, 'colorDepth', { get: () => 24, configurable: true });
    Object.defineProperty(screen, 'pixelDepth', { get: () => 24, configurable: true });

    // ========== FIX HEADLESS DETECTION: window.outerWidth/outerHeight ==========
    // In headless Chrome, window.outerWidth and window.outerHeight are 0, which is a dead giveaway
    // Override them to realistic values based on window.innerWidth/innerHeight + browser chrome
    (function() {
        // Calculate realistic outer dimensions based on inner dimensions + browser chrome
        // Typical browser chrome: ~100px for toolbars/address bar (top), ~0px (bottom)
        const chromeHeight = 100;  // Browser UI height (address bar, tabs, etc.)
        const chromeWidth = 0;     // Browser UI width (usually 0 on sides)

        // Get current inner dimensions
        const getOuterWidth = () => window.innerWidth + chromeWidth;
        const getOuterHeight = () => window.innerHeight + chromeHeight;

        // Override outerWidth
        Object.defineProperty(window, 'outerWidth', {
            get: () => getOuterWidth(),
            configurable: true
        });

        // Override outerHeight
        Object.defineProperty(window, 'outerHeight', {
            get: () => getOuterHeight(),
            configurable: true
        });

        // Also fix screenX and screenY (should not be 0 in normal browser)
        // Realistic values: window positioned slightly offset from top-left
        Object.defineProperty(window, 'screenX', {
            get: () => 0,
            configurable: true
        });

        Object.defineProperty(window, 'screenY', {
            get: () => 0,
            configurable: true
        });

        // screenLeft and screenTop are aliases for screenX and screenY
        Object.defineProperty(window, 'screenLeft', {
            get: () => 0,
            configurable: true
        });

        Object.defineProperty(window, 'screenTop', {
            get: () => 0,
            configurable: true
        });
    })();

    // Override Notification to always allow
    Object.defineProperty(Notification, 'permission', {
        get: () => 'default',
        configurable: true
    });
    """


# ============================================================================
# HUMAN-LIKE TIMING
# ============================================================================

# FAST MODE: Set to True to minimize delays (for training/speed)
FAST_MODE = False  # Reduced delays (still stealthy minimums)
TURBO_MODE = False  # Even faster (still enforces stealth minimums)
SPEED_MULTIPLIER = 0.05 if TURBO_MODE else (0.2 if FAST_MODE else 1.0)  # 20x/5x/1x

# Requested-by-user speed mode (applied per-URL using FastTrackSafety)
_SPEED_MODE_REQUESTED: str = "off"  # "off" | "fast" | "turbo"
_speed_warning_domains = set()


def _recompute_speed_multiplier() -> None:
    global SPEED_MULTIPLIER
    SPEED_MULTIPLIER = 0.05 if TURBO_MODE else (0.2 if FAST_MODE else 1.0)


def request_speed_mode(mode: str) -> None:
    """
    Request speed mode from natural language. Mode is applied per-URL via apply_speed_mode_for_url().

    Args:
        mode: "off" | "fast" | "turbo"
    """
    global _SPEED_MODE_REQUESTED
    mode_norm = (mode or "").strip().lower()
    if mode_norm not in ("off", "fast", "turbo"):
        mode_norm = "off"
    _SPEED_MODE_REQUESTED = mode_norm


def apply_speed_mode_for_url(url: str) -> None:
    """
    Apply requested speed mode for a specific URL, enforcing FastTrackSafety.

    This is called at navigation time so we can decide based on destination.
    """
    global FAST_MODE, TURBO_MODE

    requested = _SPEED_MODE_REQUESTED
    if requested == "off":
        if FAST_MODE or TURBO_MODE:
            FAST_MODE = False
            TURBO_MODE = False
            _recompute_speed_multiplier()
        return

    def _is_safe_url(u: str) -> bool:
        """
        Minimal FAST_TRACK safety check (works even when full humanization package
        is unavailable on some platforms).
        """
        try:
            from urllib.parse import urlparse
            import ipaddress

            parsed = urlparse(u)
            host = (parsed.hostname or "").lower()
            if not host:
                return False

            if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
                return True

            # Local-ish dev suffixes
            if host.endswith((".local", ".test", ".dev")):
                return True

            try:
                ip = ipaddress.ip_address(host)
                return bool(ip.is_private or ip.is_loopback or ip.is_reserved)
            except ValueError:
                # Not an IP; keep strict unless it's a known dev suffix above
                return False
        except Exception:
            return False

    is_safe = _is_safe_url(url)

    if not is_safe:
        if FAST_MODE or TURBO_MODE:
            FAST_MODE = False
            TURBO_MODE = False
            _recompute_speed_multiplier()
        return

    # Safe: apply requested mode
    TURBO_MODE = requested == "turbo"
    FAST_MODE = requested == "fast" or TURBO_MODE
    _recompute_speed_multiplier()

async def human_delay(min_ms: int = 50, max_ms: int = 200, variance: float = 0.3):
    """
    Wait a human-like random amount of time.
    Includes variance to make timing less predictable.
    In FAST_MODE, delays are reduced by SPEED_MULTIPLIER.
    """
    base_delay = random.randint(min_ms, max_ms)

    # Add variance (sometimes faster, sometimes slower)
    variance_amount = base_delay * variance
    actual_delay = base_delay + random.uniform(-variance_amount, variance_amount)

    # Apply speed multiplier
    actual_delay = actual_delay * SPEED_MULTIPLIER

    # Ensure minimum delay for stealth (50ms minimum required to avoid bot detection)
    # Even in TURBO_MODE, delays below 50ms cause instant bot detection by timing analysis
    min_delay = 50 if TURBO_MODE else (50 if FAST_MODE else 20)
    actual_delay = max(min_delay, actual_delay)

    await asyncio.sleep(actual_delay / 1000)


async def between_action_delay():
    """Delay between major actions (clicking, typing, etc.)"""
    if TURBO_MODE:
        await human_delay(50, 100)  # Minimum 50ms for stealth
    elif FAST_MODE:
        await human_delay(50, 100)  # Minimum 50ms for stealth
    else:
        await human_delay(150, 400)


async def reading_delay():
    """Delay as if user is reading/looking at page"""
    if TURBO_MODE:
        await human_delay(50, 150)  # Minimum 50ms for stealth
    elif FAST_MODE:
        await human_delay(100, 300)  # Faster but still stealthy
    else:
        await human_delay(500, 1500)


async def thinking_delay():
    """Delay as if user is thinking/deciding"""
    if TURBO_MODE:
        await human_delay(50, 200)  # Minimum 50ms for stealth
    elif FAST_MODE:
        await human_delay(150, 400)  # Faster but still stealthy
    else:
        await human_delay(800, 2500)


async def typing_delay():
    """Delay between keystrokes when typing"""
    # Human typing is ~200-400ms between keys on average
    # But varies wildly - sometimes fast bursts, sometimes pauses
    if random.random() < 0.1:  # 10% chance of longer pause (thinking)
        await human_delay(300, 600)
    elif random.random() < 0.2:  # 20% chance of fast burst
        await human_delay(30, 80)
    else:  # Normal typing
        await human_delay(80, 180)


# ============================================================================
# MOUSE MOVEMENT SIMULATION
# ============================================================================

def bezier_curve(start: Tuple[float, float], end: Tuple[float, float],
                 control1: Optional[Tuple[float, float]] = None,
                 control2: Optional[Tuple[float, float]] = None,
                 steps: int = 50) -> List[Tuple[float, float]]:
    """
    Generate points along a bezier curve for natural mouse movement.
    Uses cubic bezier curve for smooth, human-like paths.
    """
    if control1 is None:
        # Generate random control point
        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2
        offset_x = random.uniform(-100, 100)
        offset_y = random.uniform(-100, 100)
        control1 = (mid_x + offset_x, mid_y + offset_y)

    if control2 is None:
        # Generate second control point
        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2
        offset_x = random.uniform(-50, 50)
        offset_y = random.uniform(-50, 50)
        control2 = (mid_x + offset_x, mid_y + offset_y)

    points = []
    for i in range(steps + 1):
        t = i / steps
        # Cubic bezier formula
        x = (1-t)**3 * start[0] + 3*(1-t)**2*t * control1[0] + 3*(1-t)*t**2 * control2[0] + t**3 * end[0]
        y = (1-t)**3 * start[1] + 3*(1-t)**2*t * control1[1] + 3*(1-t)*t**2 * control2[1] + t**3 * end[1]

        # Add slight noise for more human feel
        if 0 < i < steps:  # Don't add noise to start/end
            x += random.uniform(-2, 2)
            y += random.uniform(-2, 2)

        points.append((x, y))

    return points


async def move_mouse_human(page, target_x: float, target_y: float,
                           current_x: float = None, current_y: float = None):
    """
    Move mouse to target position with human-like curve.

    Args:
        page: Playwright page
        target_x, target_y: Target coordinates
        current_x, current_y: Current position (defaults to center of viewport)
    """
    if current_x is None or current_y is None:
        # Start from center of viewport or last known position
        viewport = page.viewport_size
        current_x = viewport['width'] / 2 if viewport else 960
        current_y = viewport['height'] / 2 if viewport else 540

    # Generate bezier curve path
    num_steps = random.randint(20, 40)  # Variable step count
    points = bezier_curve((current_x, current_y), (target_x, target_y), steps=num_steps)

    # Move through points with variable speed
    for i, (x, y) in enumerate(points):
        await page.mouse.move(x, y)

        # Variable delay - faster in middle, slower at start/end
        progress = i / len(points)
        if progress < 0.2 or progress > 0.8:
            delay = random.uniform(8, 15)
        else:
            delay = random.uniform(3, 8)

        await asyncio.sleep(delay / 1000)


async def human_click(
    page,
    selector: str = None,
    x: float = None,
    y: float = None,
    visual_description: str = None
):
    """
    Perform a human-like click with mouse movement and timing.

    Uses advanced Bernstein polynomial Bezier curves when humanization module available.
    Falls back to visual detection (screenshot + AI) if selector fails.

    Either selector OR (x, y) coordinates must be provided.

    Args:
        page: Playwright page
        selector: CSS selector (optional)
        x, y: Direct coordinates (optional)
        visual_description: Description for visual fallback (e.g., "the Submit button")
    """
    # Use advanced humanization if available
    if HUMANIZATION_AVAILABLE and selector:
        cursor = get_cursor()
        success = await cursor.click_at(page, selector=selector)
        if success:
            return True
        # Fall through to legacy method if advanced fails

    target_x, target_y = None, None

    try:
        if selector:
            # Try self-healing selectors first
            if HUMANIZATION_AVAILABLE:
                result = await find_element_healing(page, selector, visual_description)
                if result:
                    box = await result.bounding_box()
                    if box:
                        offset_x = random.uniform(-box['width'] * 0.2, box['width'] * 0.2)
                        offset_y = random.uniform(-box['height'] * 0.2, box['height'] * 0.2)
                        target_x = box['x'] + box['width'] / 2 + offset_x
                        target_y = box['y'] + box['height'] / 2 + offset_y

            # Standard selector lookup
            if target_x is None:
                element = await page.query_selector(selector)

                if element:
                    box = await element.bounding_box()
                    if box:
                        # Click slightly off-center (humans don't click dead center)
                        offset_x = random.uniform(-box['width'] * 0.2, box['width'] * 0.2)
                        offset_y = random.uniform(-box['height'] * 0.2, box['height'] * 0.2)
                        target_x = box['x'] + box['width'] / 2 + offset_x
                        target_y = box['y'] + box['height'] / 2 + offset_y

            # If selector failed, try visual fallback
            if target_x is None and VISUAL_FALLBACK_AVAILABLE and get_visual_fallback:
                visual_fb = get_visual_fallback()
                if visual_fb.has_vision:
                    # Build description if not provided
                    description = visual_description
                    if not description:
                        description = _selector_to_description(selector)

                    logger.info(f"[VISUAL] human_click fallback for: {description}")
                    coords = await visual_fb.find_element_visually(page, description)
                    if coords:
                        target_x, target_y = coords
                        # Add small offset for human-like behavior
                        target_x += random.uniform(-3, 3)
                        target_y += random.uniform(-3, 3)

            if target_x is None:
                return False

        elif x is not None and y is not None:
            target_x, target_y = x, y
        else:
            return False

        # Move mouse to target (use advanced Bezier if available)
        if HUMANIZATION_AVAILABLE:
            cursor = get_cursor()
            await cursor.move_with_overshoot(page, target_x, target_y)
        else:
            await move_mouse_human(page, target_x, target_y)

        # Small delay before click
        await human_delay(30, 80)

        # Click (with slight variation in hold time)
        await page.mouse.down()
        await human_delay(50, 120)  # Mouse button hold time
        await page.mouse.up()

        return True
    except Exception as e:
        logger.debug(f"Human click failed: {e}")
        return False


def _selector_to_description(selector: str) -> str:
    """Convert selector to visual description."""
    sel_lower = selector.lower()
    if 'submit' in sel_lower:
        return "the Submit button"
    if 'search' in sel_lower:
        return "the search box"
    if 'login' in sel_lower or 'sign' in sel_lower:
        return "the Login button"
    if 'compose' in sel_lower:
        return "the Compose button"
    if 'button' in sel_lower:
        return "a button"
    if 'input' in sel_lower:
        return "an input field"
    return f"the element: {selector[:40]}"


# ============================================================================
# HUMAN-LIKE TYPING
# ============================================================================

async def human_type(
    page,
    selector: str,
    text: str,
    clear_first: bool = True,
    visual_description: str = None
):
    """
    Type text with human-like timing and occasional mistakes.

    Uses advanced QWERTY-neighbor error typing when humanization module available.
    Falls back to visual detection if selector fails.

    Args:
        page: Playwright page
        selector: Input field selector
        text: Text to type
        clear_first: Whether to clear the field first
        visual_description: Description for visual fallback (e.g., "the email input")
    """
    # Use advanced humanization if available
    if HUMANIZATION_AVAILABLE:
        typer = get_typer()
        success = await typer.type_text(page, text, selector=selector, clear_first=clear_first)
        if success:
            return True
        # Fall through to legacy method if advanced fails

    try:
        # Click to focus (human-like) - uses visual fallback if selector fails
        desc = visual_description or _selector_to_description(selector)
        clicked = await human_click(page, selector, visual_description=desc)
        if not clicked:
            return False

        await human_delay(100, 200)

        # Clear if needed
        if clear_first:
            await page.keyboard.press("Control+a")
            await human_delay(30, 80)
            await page.keyboard.press("Backspace")
            await human_delay(80, 150)

        # Type each character with variable timing
        for i, char in enumerate(text):
            # Occasional typo and correction (2% chance)
            if random.random() < 0.02 and len(text) > 10:
                # Type wrong char
                wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
                await page.keyboard.type(wrong_char)
                await human_delay(100, 200)
                # Pause and "notice"
                await human_delay(200, 400)
                # Backspace
                await page.keyboard.press("Backspace")
                await human_delay(100, 200)

            # Type the actual character
            await page.keyboard.type(char)

            # Variable delay between characters
            if char in ' .!?':
                # Longer pause after punctuation/space
                await human_delay(80, 200)
            elif char == '\n':
                await human_delay(200, 400)
            else:
                await typing_delay()

        return True
    except Exception as e:
        logger.debug(f"Human type failed: {e}")
        return False


# ============================================================================
# SCROLL SIMULATION
# ============================================================================

async def human_scroll(page, direction: str = "down", amount: int = None):
    """
    Scroll page with human-like behavior.

    Uses advanced scrolling with momentum when humanization module available.

    Args:
        page: Playwright page
        direction: "up" or "down"
        amount: Pixel amount (random if not specified)
    """
    # Use advanced humanization if available
    if HUMANIZATION_AVAILABLE:
        scroller = get_scroller()
        if direction.lower() == "up":
            await scroller.scroll_up(page, amount)
        else:
            await scroller.scroll_down(page, amount)
        return

    # Legacy implementation
    if amount is None:
        amount = random.randint(200, 500)

    if direction == "up":
        amount = -amount

    # Scroll in chunks with variable speed
    chunks = random.randint(3, 6)
    chunk_size = amount / chunks

    for i in range(chunks):
        await page.mouse.wheel(0, chunk_size)
        await human_delay(20, 50)

    # Pause after scrolling (reading time)
    await reading_delay()


# ============================================================================
# PAGE INTERACTION HELPERS
# ============================================================================

async def wait_for_page_ready(page, timeout: int = 10000):
    """Wait for page to be fully loaded and interactive."""
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=timeout)
        # Additional wait for JS to settle
        await human_delay(300, 700)
        return True
    except Exception:
        return False


async def random_mouse_movement(page):
    """
    Make random mouse movements to simulate user activity.
    Call this occasionally between actions.
    """
    viewport = page.viewport_size
    if not viewport:
        return

    # Move to random position
    x = random.uniform(100, viewport['width'] - 100)
    y = random.uniform(100, viewport['height'] - 100)

    await move_mouse_human(page, x, y)


class StealthSession:
    """
    Context manager for maintaining stealth state throughout a session.
    Tracks mouse position, handles periodic "idle" movements, etc.
    """

    def __init__(self, page):
        self.page = page
        self.mouse_x = 960
        self.mouse_y = 540
        self.last_action_time = 0
        self.actions_count = 0

    async def inject_stealth_scripts(self, session_id: str = None):
        """
        Inject anti-detection scripts into the page.

        Includes:
        - Base stealth JS (WebRTC, navigator props, etc.)
        - Antidetect fingerprint (Canvas, WebGL, Audio noise injection)
        """
        try:
            # Base stealth scripts
            await self.page.add_init_script(get_stealth_js())
            logger.debug("Injected base stealth scripts")

            # Antidetect fingerprint injection (Multilogin-style)
            if ANTIDETECT_AVAILABLE:
                fingerprint_js = get_fingerprint_script(session_id or "default")
                await self.page.add_init_script(fingerprint_js)
                logger.debug("Injected antidetect fingerprint")

        except Exception as e:
            logger.debug(f"Failed to inject stealth scripts: {e}")

    async def before_action(self):
        """Call before each action to add natural delays with pattern randomization."""
        self.actions_count += 1

        # Use pattern randomizer if available for unpredictable delays
        if PATTERN_RANDOMIZER_AVAILABLE:
            randomizer = get_randomizer()
            randomizer.increment_action()

            # Check for random pause (human distraction)
            if randomizer.should_pause():
                pause_duration = randomizer.get_pause_duration()
                await asyncio.sleep(pause_duration)
            else:
                # Randomized delay between actions
                delay_ms = randomizer.randomize_delay(200, 500)
                await asyncio.sleep(delay_ms / 1000)
        else:
            # Fallback to simple delays
            if self.actions_count % random.randint(5, 10) == 0:
                await thinking_delay()
            else:
                await between_action_delay()

    async def click(self, selector: str):
        """Human-like click on element."""
        await self.before_action()
        return await human_click(self.page, selector)

    async def type(self, selector: str, text: str):
        """Human-like typing into element."""
        await self.before_action()
        return await human_type(self.page, selector, text)

    async def scroll(self, direction: str = "down"):
        """Human-like scrolling."""
        await self.before_action()
        await human_scroll(self.page, direction)


# ============================================================================
# RATE LIMITING
# ============================================================================

class RateLimiter:
    """
    Rate limiter to prevent hitting sites too fast.
    Tracks requests per domain and enforces delays.
    """

    def __init__(self, requests_per_minute: int = 10):
        self.rpm = requests_per_minute
        self.domain_timestamps = {}
        self.min_delay = 60 / requests_per_minute  # seconds between requests

    async def wait_for_slot(self, domain: str):
        """Wait until we can make another request to this domain."""
        import time

        if domain not in self.domain_timestamps:
            self.domain_timestamps[domain] = []

        now = time.time()

        # Clean old timestamps (older than 1 minute)
        self.domain_timestamps[domain] = [
            ts for ts in self.domain_timestamps[domain]
            if now - ts < 60
        ]

        # If we've made too many requests, wait
        if len(self.domain_timestamps[domain]) >= self.rpm:
            oldest = min(self.domain_timestamps[domain])
            wait_time = 60 - (now - oldest)
            if wait_time > 0:
                logger.debug(f"Rate limiting: waiting {wait_time:.1f}s for {domain}")
                await asyncio.sleep(wait_time)

        # Also add random delay between requests to same domain
        if self.domain_timestamps[domain]:
            last_request = max(self.domain_timestamps[domain])
            time_since_last = now - last_request
            if time_since_last < self.min_delay:
                extra_wait = self.min_delay - time_since_last + random.uniform(1, 3)
                await asyncio.sleep(extra_wait)

        # Record this request
        self.domain_timestamps[domain].append(time.time())


# Global rate limiter instance
rate_limiter = RateLimiter(requests_per_minute=15)


async def respectful_navigate(page, url: str):
    """
    Navigate to URL with rate limiting and stealth.
    """
    from urllib.parse import urlparse

    domain = urlparse(url).netloc
    await rate_limiter.wait_for_slot(domain)

    # Add random delay before navigation
    await human_delay(500, 1500)

    return await page.goto(url, wait_until="domcontentloaded")


# ============================================================================
# AUTOMATIC STEALTH SETUP (ALL-IN-ONE)
# ============================================================================

async def setup_stealth_page(page, session_id: str = None) -> StealthSession:
    """
    Set up a page with ALL stealth and humanization features.

    This is the recommended way to initialize a page for automation.
    Automatically enables:
    - Base stealth scripts (WebRTC, navigator, etc.)
    - Antidetect fingerprinting (Canvas, WebGL, Audio noise)
    - Pattern randomization for delays
    - Human-like interactions

    Args:
        page: Playwright page object
        session_id: Optional session ID for consistent fingerprints

    Returns:
        StealthSession for human-like interactions

    Example:
        page = await browser.new_page()
        stealth = await setup_stealth_page(page, session_id="user-123")
        await stealth.click("#login-btn")
        await stealth.type("#email", "test@example.com")
    """
    # Create stealth context
    ctx = StealthSession(page)

    # Inject all stealth scripts (base + antidetect)
    await ctx.inject_stealth_scripts(session_id=session_id)

    # Start new pattern randomization session if available
    if PATTERN_RANDOMIZER_AVAILABLE:
        new_session()
        logger.debug("Started new pattern randomization session")

    return ctx


async def analyze_page_elements(page) -> list:
    """
    Analyze page using 3-source DOM fusion for robust element detection.

    Combines DOM Tree + Accessibility Tree + DOM Snapshot for 30-40%
    better element detection accuracy.

    Args:
        page: Playwright page object

    Returns:
        List of FusedElement objects with combined information

    Example:
        elements = await analyze_page_elements(page)
        buttons = [e for e in elements if e.a11y_role == 'button']
        for btn in buttons:
            print(f"Button: {btn.get_description()}")
    """
    if not DOM_FUSION_AVAILABLE:
        logger.warning("DOM fusion not available, returning empty list")
        return []

    return await analyze_page(page)


async def find_interactive_elements(page) -> list:
    """
    Find all clickable/interactive elements on the page.

    Uses DOM fusion to accurately identify buttons, links, inputs, etc.

    Args:
        page: Playwright page object

    Returns:
        List of interactive FusedElement objects
    """
    if not DOM_FUSION_AVAILABLE:
        logger.warning("DOM fusion not available")
        return []

    return await get_clickable_elements(page)


def get_stealth_status() -> dict:
    """
    Get status of all stealth/humanization modules.

    Returns:
        Dict with availability status of each module
    """
    return {
        "humanization": HUMANIZATION_AVAILABLE,
        "antidetect_fingerprint": ANTIDETECT_AVAILABLE,
        "pattern_randomizer": PATTERN_RANDOMIZER_AVAILABLE,
        "dom_fusion": DOM_FUSION_AVAILABLE,
        "visual_fallback": VISUAL_FALLBACK_AVAILABLE,
    }
