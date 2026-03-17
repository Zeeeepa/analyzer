"""
Antidetect Fingerprint System - Multilogin-style profile management

Learned from: Multilogin, GoLogin, Dolphin Anty, Camoufox

Key principles:
1. CONSISTENCY - Same fingerprint throughout session (seeded RNG)
2. REALISM - Values from real device database, not random
3. CORRELATION - GPU matches cores matches memory matches screen
4. SUBTLE NOISE - <0.1% variation for canvas/audio (invisible but changes hash)
5. RANDOMIZATION - Slight variations each session to avoid pattern detection

This module creates complete browser fingerprint profiles that:
- Look like real devices (not random values)
- Stay consistent within a session
- Change between sessions (anti-pattern)
- Have correlated properties (high-end GPU = high cores)
"""

import hashlib
import random
import json
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from loguru import logger


class SeededRandom:
    """
    Deterministic random number generator with seed.
    Same seed = same sequence of "random" numbers.
    Used for session-consistent fingerprints.
    """

    def __init__(self, seed: str):
        # Convert string seed to integer
        self.seed_int = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
        self._state = self.seed_int

    def _next(self) -> int:
        """Linear congruential generator"""
        self._state = (self._state * 1103515245 + 12345) & 0x7FFFFFFF
        return self._state

    def random(self) -> float:
        """Return random float in [0, 1)"""
        return self._next() / 0x7FFFFFFF

    def uniform(self, a: float, b: float) -> float:
        """Return random float in [a, b]"""
        return a + (b - a) * self.random()

    def randint(self, a: int, b: int) -> int:
        """Return random integer in [a, b]"""
        return a + int(self.random() * (b - a + 1))

    def choice(self, seq: list) -> Any:
        """Return random element from sequence"""
        return seq[self.randint(0, len(seq) - 1)]

    def gauss(self, mu: float, sigma: float) -> float:
        """Return Gaussian random with mean mu and std sigma"""
        # Box-Muller transform
        u1 = self.random()
        u2 = self.random()
        import math
        z0 = math.sqrt(-2 * math.log(u1 + 1e-10)) * math.cos(2 * math.pi * u2)
        return mu + z0 * sigma


# Real device fingerprint database (from FingerprintSwitcher-style data)
# These are REAL combinations found on actual devices
DEVICE_PROFILES = {
    "high_end_desktop": {
        "screens": [
            {"width": 2560, "height": 1440, "colorDepth": 24, "pixelRatio": 1},
            {"width": 3840, "height": 2160, "colorDepth": 24, "pixelRatio": 1},
            {"width": 2560, "height": 1080, "colorDepth": 24, "pixelRatio": 1},
        ],
        "hardware": [
            {"cores": 16, "memory": 32},
            {"cores": 12, "memory": 32},
            {"cores": 16, "memory": 64},
            {"cores": 24, "memory": 64},
        ],
        "webgl": [
            {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4090 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4080 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3090 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD, AMD Radeon RX 7900 XTX Direct3D11 vs_5_0 ps_5_0, D3D11)"},
        ],
    },
    "mid_range_desktop": {
        "screens": [
            {"width": 1920, "height": 1080, "colorDepth": 24, "pixelRatio": 1},
            {"width": 2560, "height": 1440, "colorDepth": 24, "pixelRatio": 1},
            {"width": 1920, "height": 1200, "colorDepth": 24, "pixelRatio": 1},
        ],
        "hardware": [
            {"cores": 8, "memory": 16},
            {"cores": 6, "memory": 16},
            {"cores": 8, "memory": 32},
            {"cores": 12, "memory": 16},
        ],
        "webgl": [
            {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD, AMD Radeon RX 6700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 2060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
        ],
    },
    "laptop": {
        "screens": [
            {"width": 1920, "height": 1080, "colorDepth": 24, "pixelRatio": 1},
            {"width": 1366, "height": 768, "colorDepth": 24, "pixelRatio": 1},
            {"width": 1536, "height": 864, "colorDepth": 24, "pixelRatio": 1.25},
            {"width": 1440, "height": 900, "colorDepth": 24, "pixelRatio": 1},
        ],
        "hardware": [
            {"cores": 8, "memory": 16},
            {"cores": 4, "memory": 8},
            {"cores": 6, "memory": 8},
            {"cores": 8, "memory": 8},
        ],
        "webgl": [
            {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce MX450 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"},
        ],
    },
    "budget_desktop": {
        "screens": [
            {"width": 1920, "height": 1080, "colorDepth": 24, "pixelRatio": 1},
            {"width": 1366, "height": 768, "colorDepth": 24, "pixelRatio": 1},
            {"width": 1600, "height": 900, "colorDepth": 24, "pixelRatio": 1},
        ],
        "hardware": [
            {"cores": 4, "memory": 8},
            {"cores": 2, "memory": 4},
            {"cores": 4, "memory": 4},
            {"cores": 6, "memory": 8},
        ],
        "webgl": [
            {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GT 1030 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) HD Graphics 530 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
        ],
    },
}

# Timezone and locale combinations (geographically consistent)
LOCALE_PROFILES = [
    {"timezone": "America/New_York", "languages": ["en-US", "en"], "locale": "en-US"},
    {"timezone": "America/Los_Angeles", "languages": ["en-US", "en"], "locale": "en-US"},
    {"timezone": "America/Chicago", "languages": ["en-US", "en"], "locale": "en-US"},
    {"timezone": "America/Denver", "languages": ["en-US", "en"], "locale": "en-US"},
    {"timezone": "Europe/London", "languages": ["en-GB", "en"], "locale": "en-GB"},
    {"timezone": "Europe/Paris", "languages": ["fr-FR", "fr", "en"], "locale": "fr-FR"},
    {"timezone": "Europe/Berlin", "languages": ["de-DE", "de", "en"], "locale": "de-DE"},
    {"timezone": "Australia/Sydney", "languages": ["en-AU", "en"], "locale": "en-AU"},
    {"timezone": "Asia/Tokyo", "languages": ["ja-JP", "ja", "en"], "locale": "ja-JP"},
    {"timezone": "Asia/Singapore", "languages": ["en-SG", "en", "zh"], "locale": "en-SG"},
]

# Chrome versions (realistic distribution)
CHROME_VERSIONS = [
    {"major": 120, "full": "120.0.6099.130"},
    {"major": 121, "full": "121.0.6167.85"},
    {"major": 122, "full": "122.0.6261.95"},
    {"major": 119, "full": "119.0.6045.160"},
    {"major": 123, "full": "123.0.6312.59"},
]


@dataclass
class FingerprintProfile:
    """Complete browser fingerprint profile"""
    # Identity
    profile_id: str
    session_seed: str

    # Screen
    screen_width: int
    screen_height: int
    screen_color_depth: int
    screen_pixel_ratio: float
    avail_width: int
    avail_height: int

    # Hardware
    hardware_concurrency: int
    device_memory: int
    platform: str = "Win32"
    max_touch_points: int = 0

    # WebGL
    webgl_vendor: str = ""
    webgl_renderer: str = ""

    # Locale
    timezone: str = "America/New_York"
    languages: List[str] = field(default_factory=lambda: ["en-US", "en"])
    locale: str = "en-US"

    # Chrome version
    chrome_major: int = 120
    chrome_full: str = "120.0.6099.130"

    # Noise parameters (session-consistent)
    canvas_noise: float = 0.0003
    audio_noise: float = 0.00003
    webgl_noise: float = 0.0001

    # Timing noise
    performance_noise_ms: float = 50.0

    # Font count (realistic)
    font_count: int = 287

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            "profile_id": self.profile_id,
            "session_seed": self.session_seed,
            "screen": {
                "width": self.screen_width,
                "height": self.screen_height,
                "colorDepth": self.screen_color_depth,
                "pixelRatio": self.screen_pixel_ratio,
                "availWidth": self.avail_width,
                "availHeight": self.avail_height,
            },
            "hardware": {
                "concurrency": self.hardware_concurrency,
                "memory": self.device_memory,
                "platform": self.platform,
                "maxTouchPoints": self.max_touch_points,
            },
            "webgl": {
                "vendor": self.webgl_vendor,
                "renderer": self.webgl_renderer,
            },
            "locale": {
                "timezone": self.timezone,
                "languages": self.languages,
                "locale": self.locale,
            },
            "chrome": {
                "major": self.chrome_major,
                "full": self.chrome_full,
            },
            "noise": {
                "canvas": self.canvas_noise,
                "audio": self.audio_noise,
                "webgl": self.webgl_noise,
                "performance": self.performance_noise_ms,
            },
            "fonts": {
                "count": self.font_count,
            }
        }


class AntidetectFingerprint:
    """
    Antidetect fingerprint generator and manager.

    Creates consistent, realistic fingerprints that:
    - Look like real devices
    - Stay same within session
    - Change between sessions
    - Have correlated properties

    Example:
        gen = AntidetectFingerprint()

        # Create new profile
        profile = gen.create_profile("account_123")

        # Get injection script
        js = gen.get_injection_script(profile)

        # Inject into page
        await page.add_init_script(js)
    """

    def __init__(self, profiles_dir: Optional[str] = None):
        self.profiles_dir = Path(profiles_dir) if profiles_dir else Path.home() / ".eversale" / "fingerprints"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self._profiles: Dict[str, FingerprintProfile] = {}
        self._load_profiles()

    def _load_profiles(self):
        """Load saved profiles from disk"""
        profiles_file = self.profiles_dir / "profiles.json"
        if profiles_file.exists():
            try:
                with open(profiles_file) as f:
                    data = json.load(f)
                    for pid, pdata in data.items():
                        # Reconstruct profile
                        self._profiles[pid] = FingerprintProfile(
                            profile_id=pdata["profile_id"],
                            session_seed=pdata["session_seed"],
                            screen_width=pdata["screen"]["width"],
                            screen_height=pdata["screen"]["height"],
                            screen_color_depth=pdata["screen"]["colorDepth"],
                            screen_pixel_ratio=pdata["screen"]["pixelRatio"],
                            avail_width=pdata["screen"]["availWidth"],
                            avail_height=pdata["screen"]["availHeight"],
                            hardware_concurrency=pdata["hardware"]["concurrency"],
                            device_memory=pdata["hardware"]["memory"],
                            platform=pdata["hardware"]["platform"],
                            max_touch_points=pdata["hardware"]["maxTouchPoints"],
                            webgl_vendor=pdata["webgl"]["vendor"],
                            webgl_renderer=pdata["webgl"]["renderer"],
                            timezone=pdata["locale"]["timezone"],
                            languages=pdata["locale"]["languages"],
                            locale=pdata["locale"]["locale"],
                            chrome_major=pdata["chrome"]["major"],
                            chrome_full=pdata["chrome"]["full"],
                            canvas_noise=pdata["noise"]["canvas"],
                            audio_noise=pdata["noise"]["audio"],
                            webgl_noise=pdata["noise"]["webgl"],
                            performance_noise_ms=pdata["noise"]["performance"],
                            font_count=pdata["fonts"]["count"],
                        )
            except Exception as e:
                logger.debug(f"Failed to load fingerprint profiles: {e}")

    def _save_profiles(self):
        """Save profiles to disk"""
        profiles_file = self.profiles_dir / "profiles.json"
        try:
            data = {pid: p.to_dict() for pid, p in self._profiles.items()}
            with open(profiles_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to save fingerprint profiles: {e}")

    def create_profile(
        self,
        profile_id: str,
        device_class: Optional[str] = None,
        locale_profile: Optional[Dict] = None,
        regenerate: bool = False
    ) -> FingerprintProfile:
        """
        Create a new fingerprint profile.

        Args:
            profile_id: Unique identifier (e.g., "account_123")
            device_class: high_end_desktop, mid_range_desktop, laptop, budget_desktop
            locale_profile: Override timezone/language
            regenerate: Force regenerate even if exists

        Returns:
            FingerprintProfile with all properties
        """
        # Return existing if not regenerating
        if not regenerate and profile_id in self._profiles:
            return self._profiles[profile_id]

        # Create session seed (changes on regenerate for anti-pattern)
        session_seed = f"{profile_id}_{int(time.time())}"
        rng = SeededRandom(session_seed)

        # Pick device class (weighted toward common)
        if device_class is None:
            device_class = rng.choice([
                "mid_range_desktop",  # Most common
                "mid_range_desktop",
                "laptop",
                "laptop",
                "high_end_desktop",
                "budget_desktop",
            ])

        device = DEVICE_PROFILES[device_class]

        # Pick correlated components
        screen = rng.choice(device["screens"])
        hardware = rng.choice(device["hardware"])
        webgl = rng.choice(device["webgl"])

        # Pick locale (or use provided)
        if locale_profile is None:
            locale_profile = rng.choice(LOCALE_PROFILES)

        # Pick Chrome version
        chrome = rng.choice(CHROME_VERSIONS)

        # Generate noise parameters (subtle variations)
        canvas_noise = rng.uniform(0.0001, 0.0005)  # 0.01-0.05% - undetectable
        audio_noise = rng.uniform(0.00001, 0.00005)  # Even smaller for audio
        webgl_noise = rng.uniform(0.00005, 0.0002)
        perf_noise = rng.uniform(30, 80)  # ms variance in timing

        # Font count (realistic range)
        font_count = rng.randint(250, 320)

        # Calculate avail dimensions (minus taskbar)
        taskbar_height = rng.randint(35, 50)
        avail_height = screen["height"] - taskbar_height

        profile = FingerprintProfile(
            profile_id=profile_id,
            session_seed=session_seed,
            screen_width=screen["width"],
            screen_height=screen["height"],
            screen_color_depth=screen["colorDepth"],
            screen_pixel_ratio=screen.get("pixelRatio", 1),
            avail_width=screen["width"],
            avail_height=avail_height,
            hardware_concurrency=hardware["cores"],
            device_memory=hardware["memory"],
            webgl_vendor=webgl["vendor"],
            webgl_renderer=webgl["renderer"],
            timezone=locale_profile["timezone"],
            languages=locale_profile["languages"],
            locale=locale_profile["locale"],
            chrome_major=chrome["major"],
            chrome_full=chrome["full"],
            canvas_noise=canvas_noise,
            audio_noise=audio_noise,
            webgl_noise=webgl_noise,
            performance_noise_ms=perf_noise,
            font_count=font_count,
        )

        self._profiles[profile_id] = profile
        self._save_profiles()

        logger.debug(f"Profile: {profile_id}")
        return profile

    def get_profile(self, profile_id: str) -> Optional[FingerprintProfile]:
        """Get existing profile"""
        return self._profiles.get(profile_id)

    def get_or_create_profile(self, profile_id: str) -> FingerprintProfile:
        """Get existing or create new profile"""
        if profile_id in self._profiles:
            return self._profiles[profile_id]
        return self.create_profile(profile_id)

    def get_injection_script(self, profile: FingerprintProfile) -> str:
        """
        Generate JavaScript to inject fingerprint into page.

        Uses seeded RNG for consistent noise within session.
        """
        return f'''
// ============================================================
// ANTIDETECT FINGERPRINT INJECTION - Profile: {profile.profile_id}
// Session: {profile.session_seed}
// ============================================================

(function() {{
    'use strict';

    // Session-consistent seeded RNG
    const sessionSeed = "{profile.session_seed}";
    let rngState = 0;
    for (let i = 0; i < sessionSeed.length; i++) {{
        rngState = ((rngState << 5) - rngState) + sessionSeed.charCodeAt(i);
        rngState = rngState & rngState;
    }}

    function seededRandom() {{
        rngState = (rngState * 1103515245 + 12345) & 0x7FFFFFFF;
        return rngState / 0x7FFFFFFF;
    }}

    // Noise parameters
    const CANVAS_NOISE = {profile.canvas_noise};
    const AUDIO_NOISE = {profile.audio_noise};
    const PERF_NOISE = {profile.performance_noise_ms};

    // ========== SCREEN PROPERTIES ==========
    Object.defineProperty(screen, 'width', {{ get: () => {profile.screen_width}, configurable: true }});
    Object.defineProperty(screen, 'height', {{ get: () => {profile.screen_height}, configurable: true }});
    Object.defineProperty(screen, 'availWidth', {{ get: () => {profile.avail_width}, configurable: true }});
    Object.defineProperty(screen, 'availHeight', {{ get: () => {profile.avail_height}, configurable: true }});
    Object.defineProperty(screen, 'colorDepth', {{ get: () => {profile.screen_color_depth}, configurable: true }});
    Object.defineProperty(screen, 'pixelDepth', {{ get: () => {profile.screen_color_depth}, configurable: true }});
    Object.defineProperty(window, 'devicePixelRatio', {{ get: () => {profile.screen_pixel_ratio}, configurable: true }});

    // ========== HARDWARE PROPERTIES ==========
    Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {profile.hardware_concurrency}, configurable: true }});
    Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {profile.device_memory}, configurable: true }});
    Object.defineProperty(navigator, 'platform', {{ get: () => '{profile.platform}', configurable: true }});
    Object.defineProperty(navigator, 'maxTouchPoints', {{ get: () => {profile.max_touch_points}, configurable: true }});

    // ========== LOCALE PROPERTIES ==========
    Object.defineProperty(navigator, 'language', {{ get: () => '{profile.languages[0]}', configurable: true }});
    Object.defineProperty(navigator, 'languages', {{ get: () => {json.dumps(profile.languages)}, configurable: true }});

    // ========== WEBDRIVER (CRITICAL) ==========
    Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined, configurable: true }});

    // ========== PLUGINS ==========
    Object.defineProperty(navigator, 'plugins', {{
        get: () => {{
            const plugins = [
                {{ name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
                {{ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' }},
            ];
            plugins.item = (i) => plugins[i] || null;
            plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
            plugins.refresh = () => {{}};
            return plugins;
        }},
        configurable: true
    }});

    // ========== CHROME RUNTIME ==========
    window.chrome = {{
        app: {{ isInstalled: false }},
        runtime: {{
            OnInstalledReason: {{ CHROME_UPDATE: 'chrome_update', INSTALL: 'install' }},
            PlatformOs: {{ ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', WIN: 'win' }}
        }}
    }};

    // ========== CLIENT HINTS ==========
    const brands = [
        {{ brand: "Chromium", version: "{profile.chrome_major}" }},
        {{ brand: "Google Chrome", version: "{profile.chrome_major}" }},
        {{ brand: "Not=A?Brand", version: "24" }}
    ];

    Object.defineProperty(navigator, 'userAgentData', {{
        get: function() {{
            return {{
                brands: brands,
                mobile: false,
                platform: "Windows",
                getHighEntropyValues: async function(hints) {{
                    return {{
                        brands: brands,
                        mobile: false,
                        platform: "Windows",
                        platformVersion: "15.0.0",
                        architecture: "x86",
                        bitness: "64",
                        model: "",
                        uaFullVersion: "{profile.chrome_full}",
                        fullVersionList: brands
                    }};
                }},
                toJSON: function() {{
                    return {{ brands, mobile: false, platform: "Windows" }};
                }}
            }};
        }},
        configurable: true
    }});

    // ========== WEBGL SPOOFING ==========
    const webglVendor = '{profile.webgl_vendor}';
    const webglRenderer = '{profile.webgl_renderer}';

    const getParameterProxy = {{
        apply: function(target, ctx, args) {{
            const param = args[0];
            if (param === 37445) return webglVendor;  // UNMASKED_VENDOR_WEBGL
            if (param === 37446) return webglRenderer; // UNMASKED_RENDERER_WEBGL
            return target.apply(ctx, args);
        }}
    }};

    if (typeof WebGLRenderingContext !== 'undefined') {{
        WebGLRenderingContext.prototype.getParameter = new Proxy(
            WebGLRenderingContext.prototype.getParameter, getParameterProxy
        );
    }}
    if (typeof WebGL2RenderingContext !== 'undefined') {{
        WebGL2RenderingContext.prototype.getParameter = new Proxy(
            WebGL2RenderingContext.prototype.getParameter, getParameterProxy
        );
    }}

    // ========== CANVAS NOISE INJECTION ==========
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(...args) {{
        const context = this.getContext('2d');
        if (context && this.width > 0 && this.height > 0) {{
            try {{
                const imageData = context.getImageData(0, 0, this.width, this.height);
                const pixels = imageData.data;

                // Add subtle noise using seeded RNG (consistent per session)
                for (let i = 0; i < pixels.length; i += 4) {{
                    const noise = (seededRandom() - 0.5) * 2 * CANVAS_NOISE * 255;
                    pixels[i]   = Math.max(0, Math.min(255, pixels[i] + noise));
                    pixels[i+1] = Math.max(0, Math.min(255, pixels[i+1] + noise));
                    pixels[i+2] = Math.max(0, Math.min(255, pixels[i+2] + noise));
                }}
                context.putImageData(imageData, 0, 0);
            }} catch(e) {{}}
        }}
        return originalToDataURL.apply(this, args);
    }};

    // Also patch toBlob
    const originalToBlob = HTMLCanvasElement.prototype.toBlob;
    HTMLCanvasElement.prototype.toBlob = function(callback, ...args) {{
        const context = this.getContext('2d');
        if (context && this.width > 0 && this.height > 0) {{
            try {{
                const imageData = context.getImageData(0, 0, this.width, this.height);
                const pixels = imageData.data;
                for (let i = 0; i < pixels.length; i += 4) {{
                    const noise = (seededRandom() - 0.5) * 2 * CANVAS_NOISE * 255;
                    pixels[i]   = Math.max(0, Math.min(255, pixels[i] + noise));
                    pixels[i+1] = Math.max(0, Math.min(255, pixels[i+1] + noise));
                    pixels[i+2] = Math.max(0, Math.min(255, pixels[i+2] + noise));
                }}
                context.putImageData(imageData, 0, 0);
            }} catch(e) {{}}
        }}
        return originalToBlob.call(this, callback, ...args);
    }};

    // ========== AUDIO CONTEXT NOISE ==========
    if (typeof AudioContext !== 'undefined') {{
        const OriginalAudioContext = AudioContext;
        window.AudioContext = function(...args) {{
            const ctx = new OriginalAudioContext(...args);

            // Patch createOscillator for frequency noise
            const originalCreateOscillator = ctx.createOscillator.bind(ctx);
            ctx.createOscillator = function() {{
                const osc = originalCreateOscillator();
                const originalStart = osc.start.bind(osc);
                osc.start = function(when) {{
                    // Add tiny frequency noise
                    osc.frequency.value *= (1 + (seededRandom() - 0.5) * AUDIO_NOISE);
                    return originalStart(when);
                }};
                return osc;
            }};

            return ctx;
        }};
        window.AudioContext.prototype = OriginalAudioContext.prototype;
    }}

    // ========== WEBRTC LEAK PROTECTION ==========
    const originalRTC = window.RTCPeerConnection || window.webkitRTCPeerConnection;
    if (originalRTC) {{
        window.RTCPeerConnection = function(...args) {{
            const pc = new originalRTC(...args);

            const origCreateOffer = pc.createOffer.bind(pc);
            pc.createOffer = async function(options) {{
                const offer = await origCreateOffer(options);
                if (offer && offer.sdp) {{
                    offer.sdp = offer.sdp.replace(/a=candidate:.+typ host.+\\r\\n/g, '');
                }}
                return offer;
            }};

            const origCreateAnswer = pc.createAnswer.bind(pc);
            pc.createAnswer = async function(options) {{
                const answer = await origCreateAnswer(options);
                if (answer && answer.sdp) {{
                    answer.sdp = answer.sdp.replace(/a=candidate:.+typ host.+\\r\\n/g, '');
                }}
                return answer;
            }};

            return pc;
        }};
        window.RTCPeerConnection.prototype = originalRTC.prototype;
    }}

    // ========== PERFORMANCE TIMING NOISE ==========
    const originalNow = performance.now.bind(performance);
    performance.now = function() {{
        return originalNow() + (seededRandom() - 0.5) * PERF_NOISE;
    }};

    // ========== FONT COUNT ==========
    if (document.fonts) {{
        Object.defineProperty(document.fonts, 'size', {{
            get: () => {profile.font_count},
            configurable: true
        }});
    }}

    // ========== PERMISSIONS ==========
    const originalQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = (params) => {{
        if (params.name === 'notifications') {{
            return Promise.resolve({{ state: 'default', onchange: null }});
        }}
        return originalQuery(params);
    }};

    console.debug('[Antidetect] Fingerprint injected: {profile.profile_id}');
}})();
'''

    def list_profiles(self) -> List[str]:
        """List all profile IDs"""
        return list(self._profiles.keys())

    def delete_profile(self, profile_id: str):
        """Delete a profile"""
        if profile_id in self._profiles:
            del self._profiles[profile_id]
            self._save_profiles()


# Global instance
_fingerprint_gen: Optional[AntidetectFingerprint] = None


def get_fingerprint_generator() -> AntidetectFingerprint:
    """Get or create global fingerprint generator"""
    global _fingerprint_gen
    if _fingerprint_gen is None:
        _fingerprint_gen = AntidetectFingerprint()
    return _fingerprint_gen


def create_fingerprint(profile_id: str, **kwargs) -> FingerprintProfile:
    """Convenience: Create fingerprint profile"""
    return get_fingerprint_generator().create_profile(profile_id, **kwargs)


def get_fingerprint_script(profile_id: str) -> str:
    """Convenience: Get injection script for profile"""
    gen = get_fingerprint_generator()
    profile = gen.get_or_create_profile(profile_id)
    return gen.get_injection_script(profile)
