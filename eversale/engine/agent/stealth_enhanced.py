"""
Enhanced Anti-Bot Stealth System for Eversale
==============================================

Comprehensive anti-detection based on 2025 research from:
- playwright-extra stealth plugins
- undetected-playwright techniques
- Anti-bot evasion research (CreepJS, FingerprintJS, DataDome)
- Browser fingerprinting defenses (Brave, Privacy Badger)

Features:
1. Advanced fingerprint management (canvas, WebGL, audio, fonts)
2. CDP detection mitigation (hide DevTools protocol)
3. Behavioral mimicry (human-like movements, typing, scrolling)
4. Request pattern normalization with fetch/XHR interception
5. Proxy integration with smart rotation
6. Detection response (CAPTCHA, blocks, bot scores)
7. Site-specific profiles (LinkedIn, Facebook, Amazon, Google)
8. Integration with existing Eversale stealth utilities
9. Fetch/XHR request interception with realistic headers and timing

Author: Claude
Date: 2025-12-02
Last Updated: 2025-12-07
"""

import asyncio
import random
import math
import hashlib
import time
import re
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from loguru import logger
from playwright.async_api import Page, BrowserContext, Browser
import json

# Import existing stealth utilities
try:
    from .stealth_utils import (
        get_stealth_args,
        get_random_user_agent,
        human_delay,
        between_action_delay,
        reading_delay,
        thinking_delay,
        typing_delay,
    )
    STEALTH_UTILS_AVAILABLE = True
except ImportError:
    STEALTH_UTILS_AVAILABLE = False
    logger.warning("stealth_utils not available - using fallbacks")

# Import CAPTCHA solver
try:
    from .captcha_solver import PageCaptchaHandler, ScrappyCaptchaBypasser
    CAPTCHA_SOLVER_AVAILABLE = True
except ImportError:
    CAPTCHA_SOLVER_AVAILABLE = False

# Import integrity validator
try:
    from .bs_detector import get_integrity_validator
    INTEGRITY_VALIDATOR_AVAILABLE = True
except ImportError:
    INTEGRITY_VALIDATOR_AVAILABLE = False

# Import TLS fingerprinting
try:
    from .tls_fingerprint import TLSProxyWrapper, HAS_CURL_CFFI, get_tls_session
    TLS_FINGERPRINT_AVAILABLE = True
except ImportError:
    TLS_FINGERPRINT_AVAILABLE = False
    HAS_CURL_CFFI = False


# =============================================================================
# 1. FINGERPRINT MANAGEMENT
# =============================================================================

class FingerprintManager:
    """
    Manages browser fingerprint randomization to avoid detection.

    Techniques:
    - Canvas fingerprint noise injection
    - WebGL vendor/renderer spoofing with variation
    - Audio context fingerprint randomization
    - Font enumeration control
    - Screen resolution variation
    - Language/locale matching
    - Timezone alignment with geolocation
    - Plugin masking
    - Fetch/XHR request interception with realistic headers
    - Request timing randomization
    - Sec-Fetch-* header generation
    """

    def __init__(self, seed: Optional[str] = None):
        """
        Initialize with optional seed for reproducible fingerprints.

        Args:
            seed: Optional seed for consistent fingerprints across session
        """
        self.seed = seed or str(random.randint(10000, 99999))
        self.fingerprint = self._generate_fingerprint()

    def _generate_canvas_prefix(self, platform: str, vendor: str, renderer: str,
                                  width: int, height: int, cores: int) -> str:
        """
        Generate deterministic canvas fingerprint prefix based on device characteristics.

        This ensures different device profiles get different canvas fingerprints,
        making fingerprint correlation harder while maintaining consistency.

        Args:
            platform: OS platform (Win32, MacIntel, Linux x86_64)
            vendor: WebGL vendor
            renderer: WebGL renderer
            width: Screen width
            height: Screen height
            cores: CPU cores

        Returns:
            8-character hex prefix for canvas fingerprint
        """
        # Create deterministic hash from device characteristics
        profile_string = f"{platform}:{vendor}:{renderer}:{width}x{height}:{cores}"
        hash_obj = hashlib.md5(profile_string.encode())

        # Platform-specific prefix pools for natural distribution
        if "Win" in platform:
            # Windows devices - prefixes common to Chrome on Windows
            windows_prefixes = [
                "e4f2a1c3", "d8b5e2f1", "c9a3d4e2", "f1e8c7b4",
                "b6d3e9f2", "a5c8d2e1", "f3d9b8c2", "e2c1f4d3",
                "d7e4b9a2", "c4f1e3d8", "b9e2c6f1", "a8d4e1c9"
            ]
            # Use hash to select from pool deterministically
            index = int(hash_obj.hexdigest()[:8], 16) % len(windows_prefixes)
            base_prefix = windows_prefixes[index]
        elif "Mac" in platform:
            # macOS devices - prefixes common to Chrome/Safari on Mac
            mac_prefixes = [
                "7a8b9c2d", "6f8e9a1b", "8c9d2e3f", "9a1b3c4d",
                "5e6f7a8b", "4d5e6f7a", "3c4d5e6f", "2b3c4d5e",
                "1a2b3c4d", "9f8e7d6c", "8e7d6c5b", "7d6c5b4a"
            ]
            index = int(hash_obj.hexdigest()[8:16], 16) % len(mac_prefixes)
            base_prefix = mac_prefixes[index]
        else:  # Linux
            # Linux devices - different patterns
            linux_prefixes = [
                "3e7f2a8c", "2d6e9b1f", "1c5d8a2e", "4f3e2d1c",
                "5a4b3c2d", "6b5c4d3e", "7c6d5e4f", "8d7e6f5a",
                "9e8f7a6b", "af9e8b7c", "ba9f8c7d", "cb9a8d7e"
            ]
            index = int(hash_obj.hexdigest()[16:24], 16) % len(linux_prefixes)
            base_prefix = linux_prefixes[index]

        # Add GPU-specific variation (last 2 chars vary by GPU)
        if "NVIDIA" in vendor or "NVIDIA" in renderer:
            gpu_variants = ["d1", "d2", "d3", "e1", "e2", "f1"]
        elif "AMD" in vendor or "AMD" in renderer:
            gpu_variants = ["a1", "a2", "a3", "b1", "b2", "c1"]
        elif "Intel" in vendor or "Intel" in renderer:
            gpu_variants = ["71", "72", "81", "82", "91", "92"]
        else:
            gpu_variants = ["01", "02", "11", "12", "21", "22"]

        gpu_index = int(hash_obj.hexdigest()[24:32], 16) % len(gpu_variants)
        final_prefix = base_prefix[:6] + gpu_variants[gpu_index]

        return final_prefix

    def _generate_webgl_prefix(self, vendor: str, renderer: str, platform: str) -> str:
        """
        Generate deterministic WebGL hash prefix based on GPU and platform.

        Args:
            vendor: WebGL vendor
            renderer: WebGL renderer
            platform: OS platform

        Returns:
            8-character hex prefix for WebGL fingerprint
        """
        # Create hash from GPU characteristics
        gpu_string = f"{vendor}:{renderer}:{platform}"
        hash_obj = hashlib.md5(gpu_string.encode())

        # Different prefix ranges for different GPU vendors
        if "NVIDIA" in vendor or "NVIDIA" in renderer:
            nvidia_prefixes = [
                "4e5f6a7b", "5f6a7b8c", "6a7b8c9d", "7b8c9dae",
                "8c9daebf", "9daebfc0", "aebfc0d1", "bfc0d1e2"
            ]
            index = int(hash_obj.hexdigest()[:8], 16) % len(nvidia_prefixes)
            return nvidia_prefixes[index]
        elif "AMD" in vendor or "AMD" in renderer:
            amd_prefixes = [
                "1a2b3c4d", "2b3c4d5e", "3c4d5e6f", "4d5e6f7a",
                "5e6f7a8b", "6f7a8b9c", "7a8b9cad", "8b9cadbe"
            ]
            index = int(hash_obj.hexdigest()[8:16], 16) % len(amd_prefixes)
            return amd_prefixes[index]
        elif "Intel" in vendor or "Intel" in renderer:
            intel_prefixes = [
                "f1e2d3c4", "e2d3c4b5", "d3c4b5a6", "c4b5a697",
                "b5a69788", "a6978879", "9788796a", "8879765b"
            ]
            index = int(hash_obj.hexdigest()[16:24], 16) % len(intel_prefixes)
            return intel_prefixes[index]
        else:
            # Generic GPU
            generic_prefixes = [
                "9f8e7d6c", "8e7d6c5b", "7d6c5b4a", "6c5b4a39"
            ]
            index = int(hash_obj.hexdigest()[24:32], 16) % len(generic_prefixes)
            return generic_prefixes[index]

    def _generate_font_modifier(self, platform: str, language: str) -> str:
        """
        Generate font fingerprint modifier based on platform and language.

        Args:
            platform: OS platform
            language: Primary language

        Returns:
            4-character hex modifier for font fingerprints
        """
        font_string = f"{platform}:{language}"
        hash_obj = hashlib.md5(font_string.encode())

        # Different font sets per platform
        if "Win" in platform:
            modifiers = ["w1f2", "w2f3", "w3f4", "w4f5", "w5f6"]
        elif "Mac" in platform:
            modifiers = ["m1f2", "m2f3", "m3f4", "m4f5", "m5f6"]
        else:  # Linux
            modifiers = ["l1f2", "l2f3", "l3f4", "l4f5", "l5f6"]

        index = int(hash_obj.hexdigest()[:8], 16) % len(modifiers)
        return modifiers[index]

    def _generate_fingerprint(self) -> Dict[str, Any]:
        """Generate a consistent but randomized fingerprint"""
        # Use seed for reproducibility within session
        rng = random.Random(self.seed)

        # Screen resolutions (common ones)
        resolutions = [
            (1920, 1080), (1366, 768), (1440, 900), (1536, 864),
            (1600, 900), (2560, 1440), (1920, 1200)
        ]
        width, height = rng.choice(resolutions)

        # WebGL vendors (realistic combinations)
        webgl_vendors = [
            ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1080 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
            ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
            ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
            ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 6800 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
            ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ]
        vendor, renderer = rng.choice(webgl_vendors)

        # Hardware specs
        cores = rng.choice([4, 6, 8, 12, 16])
        memory = rng.choice([4, 8, 16, 32])

        # Timezone (common US timezones)
        timezones = [
            "America/New_York", "America/Chicago", "America/Denver",
            "America/Los_Angeles", "America/Phoenix", "America/Detroit"
        ]
        timezone = rng.choice(timezones)

        # Languages (vary slightly)
        languages = [
            ["en-US", "en"],
            ["en-US", "en", "es"],
            ["en-GB", "en"],
            ["en-US"],
        ]
        langs = rng.choice(languages)

        # Platform variations
        platforms = ["Win32", "Linux x86_64", "MacIntel"]
        platform = rng.choice(platforms)

        # Canvas noise parameters (subtle)
        canvas_noise = rng.uniform(0.0001, 0.001)

        # Audio noise parameters
        audio_noise = rng.uniform(0.00001, 0.0001)

        # Generate deterministic canvas fingerprint prefix based on device profile
        # This creates diversity while maintaining consistency across sessions
        canvas_prefix = self._generate_canvas_prefix(platform, vendor, renderer, width, height, cores)

        # Generate WebGL hash prefix (deterministic based on GPU)
        webgl_hash_prefix = self._generate_webgl_prefix(vendor, renderer, platform)

        # Generate font fingerprint variations
        font_hash_modifier = self._generate_font_modifier(platform, langs[0])

        return {
            "screen": {
                "width": width,
                "height": height,
                "availWidth": width,
                "availHeight": height - 40,  # Taskbar
                "colorDepth": 24,
                "pixelDepth": 24,
            },
            "webgl": {
                "vendor": vendor,
                "renderer": renderer,
                "hash_prefix": webgl_hash_prefix,
            },
            "hardware": {
                "cores": cores,
                "memory": memory,
                "platform": platform,
            },
            "locale": {
                "timezone": timezone,
                "languages": langs,
            },
            "noise": {
                "canvas": canvas_noise,
                "audio": audio_noise,
            },
            "fingerprint_prefixes": {
                "canvas": canvas_prefix,
                "webgl": webgl_hash_prefix,
                "font_modifier": font_hash_modifier,
            }
        }

    def get_injection_script(self) -> str:
        """
        Generate JavaScript to inject into pages for fingerprint spoofing.

        Includes comprehensive stealth features:
        - Canvas, WebGL, Audio fingerprint randomization
        - Navigator property overrides
        - Performance timing spoofing
        - Fetch/XHR interception with realistic headers
        - Sec-Fetch-* header generation
        - Request timing randomization (1-15ms delays)
        - WebRTC IP leak protection
        - CDP detection mitigation

        Returns:
            JavaScript code as string
        """
        fp = self.fingerprint

        script = f"""
        (function() {{
            'use strict';

            // =============================================================================
            // ENHANCED FINGERPRINT DIVERSITY SYSTEM
            // =============================================================================
            //
            // This stealth system uses deterministic fingerprint prefixes that correlate
            // with device characteristics to create diverse, realistic browser fingerprints.
            //
            // Key Features:
            // 1. Canvas Fingerprint Prefix: {fp["fingerprint_prefixes"]["canvas"]}
            //    - Platform-specific (Windows/Mac/Linux have different prefix pools)
            //    - GPU-correlated (NVIDIA/AMD/Intel get specific variations)
            //    - Deterministic (same device profile = same prefix across sessions)
            //
            // 2. WebGL Hash Prefix: {fp["fingerprint_prefixes"]["webgl"]}
            //    - GPU vendor-specific prefix ranges
            //    - Correlates with WebGL capabilities
            //
            // 3. Font Modifier: {fp["fingerprint_prefixes"]["font_modifier"]}
            //    - Platform-specific font fingerprinting variations
            //    - Affects text measurement and font loading timing
            //
            // This approach prevents correlation while maintaining session consistency.
            // =============================================================================

            // ========== WEBRTC IP LEAK PROTECTION ==========

            // Block WebRTC IP leak
            const originalRTCPeerConnection = window.RTCPeerConnection || window.webkitRTCPeerConnection || window.mozRTCPeerConnection;

            if (originalRTCPeerConnection) {{
                window.RTCPeerConnection = function(...args) {{
                    const pc = new originalRTCPeerConnection(...args);

                    // Override createOffer to prevent IP leak
                    const originalCreateOffer = pc.createOffer.bind(pc);
                    pc.createOffer = async function(options) {{
                        try {{
                            const offer = await originalCreateOffer(options);
                            // Remove candidate lines that leak IP
                            if (offer && offer.sdp) {{
                                offer.sdp = offer.sdp.replace(/a=candidate:.+typ host.+\\r\\n/g, '');
                            }}
                            return offer;
                        }} catch(e) {{
                            throw e;
                        }}
                    }};

                    // Override createAnswer similarly
                    const originalCreateAnswer = pc.createAnswer.bind(pc);
                    pc.createAnswer = async function(options) {{
                        try {{
                            const answer = await originalCreateAnswer(options);
                            if (answer && answer.sdp) {{
                                answer.sdp = answer.sdp.replace(/a=candidate:.+typ host.+\\r\\n/g, '');
                            }}
                            return answer;
                        }} catch(e) {{
                            throw e;
                        }}
                    }};

                    return pc;
                }};

                window.RTCPeerConnection.prototype = originalRTCPeerConnection.prototype;

                // Also set webkit prefixed version
                if (window.webkitRTCPeerConnection) {{
                    window.webkitRTCPeerConnection = window.RTCPeerConnection;
                }}
            }}

            // Block navigator.mediaDevices getUserMedia unless needed
            if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {{
                const originalGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
                navigator.mediaDevices.getUserMedia = async function(constraints) {{
                    // Block video/audio access to prevent fingerprinting
                    if (constraints && (constraints.video || constraints.audio)) {{
                        throw new DOMException('Permission denied', 'NotAllowedError');
                    }}
                    return originalGetUserMedia(constraints);
                }};
            }}

            // ========== PERFORMANCE TIMING SPOOFING ==========

            // Spoof performance.timing to look like real browser
            const realTiming = performance.timing;
            const navigationStart = realTiming.navigationStart;

            // Use canvas seed for performance timing to correlate with device
            // Faster devices (more cores) = faster timing
            const perfSeed = parseInt(canvasPrefix.substring(4, 8), 16) / 0xFFFF;
            const deviceSpeedMultiplier = 0.7 + (perfSeed * 0.6); // 0.7x to 1.3x speed

            // Create realistic timing values with device-correlated variance
            const fakeTiming = {{
                navigationStart: navigationStart,
                unloadEventStart: 0,
                unloadEventEnd: 0,
                redirectStart: 0,
                redirectEnd: 0,
                fetchStart: navigationStart + Math.floor(seededRandom(perfSeed, 1) * 10 * deviceSpeedMultiplier) + 1,
                domainLookupStart: navigationStart + Math.floor(seededRandom(perfSeed, 2) * 20 * deviceSpeedMultiplier) + 10,
                domainLookupEnd: navigationStart + Math.floor(seededRandom(perfSeed, 3) * 30 * deviceSpeedMultiplier) + 25,
                connectStart: navigationStart + Math.floor(seededRandom(perfSeed, 4) * 40 * deviceSpeedMultiplier) + 30,
                connectEnd: navigationStart + Math.floor(seededRandom(perfSeed, 5) * 60 * deviceSpeedMultiplier) + 50,
                secureConnectionStart: navigationStart + Math.floor(seededRandom(perfSeed, 6) * 50 * deviceSpeedMultiplier) + 40,
                requestStart: navigationStart + Math.floor(seededRandom(perfSeed, 7) * 80 * deviceSpeedMultiplier) + 60,
                responseStart: navigationStart + Math.floor(seededRandom(perfSeed, 8) * 150 * deviceSpeedMultiplier) + 100,
                responseEnd: navigationStart + Math.floor(seededRandom(perfSeed, 9) * 200 * deviceSpeedMultiplier) + 150,
                domLoading: navigationStart + Math.floor(seededRandom(perfSeed, 10) * 250 * deviceSpeedMultiplier) + 180,
                domInteractive: navigationStart + Math.floor(seededRandom(perfSeed, 11) * 400 * deviceSpeedMultiplier) + 300,
                domContentLoadedEventStart: navigationStart + Math.floor(seededRandom(perfSeed, 12) * 500 * deviceSpeedMultiplier) + 350,
                domContentLoadedEventEnd: navigationStart + Math.floor(seededRandom(perfSeed, 13) * 550 * deviceSpeedMultiplier) + 400,
                domComplete: navigationStart + Math.floor(seededRandom(perfSeed, 14) * 800 * deviceSpeedMultiplier) + 500,
                loadEventStart: navigationStart + Math.floor(seededRandom(perfSeed, 15) * 850 * deviceSpeedMultiplier) + 550,
                loadEventEnd: navigationStart + Math.floor(seededRandom(perfSeed, 16) * 900 * deviceSpeedMultiplier) + 600
            }};

            // Override performance.timing
            Object.defineProperty(performance, 'timing', {{
                get: function() {{
                    return new Proxy(realTiming, {{
                        get: function(target, prop) {{
                            if (prop in fakeTiming) {{
                                return fakeTiming[prop];
                            }}
                            return target[prop];
                        }}
                    }});
                }},
                configurable: true
            }});

            // Also spoof performance.getEntriesByType
            const originalGetEntriesByType = performance.getEntriesByType.bind(performance);
            performance.getEntriesByType = function(type) {{
                const entries = originalGetEntriesByType(type);
                if (type === 'navigation') {{
                    // Add device-correlated variance to navigation entries
                    return entries.map((e, idx) => {{
                        const clone = {{}};
                        for (let key in e) {{
                            if (typeof e[key] === 'number' && key.toLowerCase().includes('time')) {{
                                const variance = Math.floor(seededRandom(perfSeed, idx + 100) * 50 * deviceSpeedMultiplier);
                                clone[key] = e[key] + variance;
                            }} else {{
                                clone[key] = e[key];
                            }}
                        }}
                        return clone;
                    }});
                }}
                return entries;
            }};

            // ========== SEC-CH-UA HEADERS (Client Hints) ==========

            // Add proper Sec-CH-UA via navigator.userAgentData
            const brands = [
                {{ brand: "Chromium", version: "120" }},
                {{ brand: "Google Chrome", version: "120" }},
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
                                uaFullVersion: "120.0.6099.130",
                                fullVersionList: brands
                            }};
                        }},
                        toJSON: function() {{
                            return {{
                                brands: brands,
                                mobile: false,
                                platform: "Windows"
                            }};
                        }}
                    }};
                }},
                configurable: true
            }});

            // ========== NAVIGATOR OVERRIDES ==========

            // Hide webdriver flag
            Object.defineProperty(navigator, 'webdriver', {{
                get: () => undefined,
                configurable: true
            }});

            // Override platform
            Object.defineProperty(navigator, 'platform', {{
                get: () => '{fp["hardware"]["platform"]}',
                configurable: true
            }});

            // Override languages
            Object.defineProperty(navigator, 'languages', {{
                get: () => {json.dumps(fp["locale"]["languages"])},
                configurable: true
            }});

            // Override language (first from languages)
            Object.defineProperty(navigator, 'language', {{
                get: () => '{fp["locale"]["languages"][0]}',
                configurable: true
            }});

            // Override hardwareConcurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {{
                get: () => {fp["hardware"]["cores"]},
                configurable: true
            }});

            // Override deviceMemory
            Object.defineProperty(navigator, 'deviceMemory', {{
                get: () => {fp["hardware"]["memory"]},
                configurable: true
            }});

            // Override maxTouchPoints (desktop = 0)
            Object.defineProperty(navigator, 'maxTouchPoints', {{
                get: () => 0,
                configurable: true
            }});

            // Override plugins (realistic Chrome plugins)
            Object.defineProperty(navigator, 'plugins', {{
                get: () => {{
                    const plugins = [
                        {{ name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
                        {{ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' }},
                        {{ name: 'Chromium PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' }},
                        {{ name: 'Microsoft Edge PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' }},
                        {{ name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: '' }}
                    ];
                    plugins.item = (i) => plugins[i] || null;
                    plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
                    plugins.refresh = () => {{}};
                    Object.setPrototypeOf(plugins, PluginArray.prototype);
                    return plugins;
                }},
                configurable: true
            }});

            // Override mimeTypes
            Object.defineProperty(navigator, 'mimeTypes', {{
                get: () => {{
                    const mimeTypes = [
                        {{ type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' }},
                        {{ type: 'text/pdf', suffixes: 'pdf', description: 'Portable Document Format' }}
                    ];
                    mimeTypes.item = (i) => mimeTypes[i] || null;
                    mimeTypes.namedItem = (name) => mimeTypes.find(m => m.type === name) || null;
                    Object.setPrototypeOf(mimeTypes, MimeTypeArray.prototype);
                    return mimeTypes;
                }},
                configurable: true
            }});

            // Override permissions query
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => {{
                if (parameters.name === 'notifications') {{
                    return Promise.resolve({{ state: 'default', onchange: null }});
                }}
                return originalQuery(parameters);
            }};

            // ========== SCREEN OVERRIDES ==========

            Object.defineProperty(screen, 'width', {{
                get: () => {fp["screen"]["width"]},
                configurable: true
            }});
            Object.defineProperty(screen, 'height', {{
                get: () => {fp["screen"]["height"]},
                configurable: true
            }});
            Object.defineProperty(screen, 'availWidth', {{
                get: () => {fp["screen"]["availWidth"]},
                configurable: true
            }});
            Object.defineProperty(screen, 'availHeight', {{
                get: () => {fp["screen"]["availHeight"]},
                configurable: true
            }});
            Object.defineProperty(screen, 'colorDepth', {{
                get: () => {fp["screen"]["colorDepth"]},
                configurable: true
            }});
            Object.defineProperty(screen, 'pixelDepth', {{
                get: () => {fp["screen"]["pixelDepth"]},
                configurable: true
            }});

            // Add device pixel ratio variation based on device profile
            const originalDevicePixelRatio = window.devicePixelRatio;
            const dprVariation = seededRandom(canvasSeed, 777) < 0.5 ? 1.0 : (seededRandom(canvasSeed, 778) < 0.7 ? 1.5 : 2.0);
            Object.defineProperty(window, 'devicePixelRatio', {{
                get: () => dprVariation,
                configurable: true
            }});

            // ========== WEBGL FINGERPRINT ==========

            // WebGL vendor/renderer spoofing with deterministic variations
            const webglSeed = parseInt(webglPrefix.substring(0, 8), 16) / 0xFFFFFFFF;

            const getParameterProxyHandler = {{
                apply: function(target, ctx, args) {{
                    const param = args[0];

                    // ========== VENDOR & RENDERER (Core Identity) ==========
                    // UNMASKED_VENDOR_WEBGL
                    if (param === 37445) {{
                        return '{fp["webgl"]["vendor"]}';
                    }}
                    // UNMASKED_RENDERER_WEBGL
                    if (param === 37446) {{
                        return '{fp["webgl"]["renderer"]}';
                    }}

                    // ========== TEXTURE & BUFFER PARAMETERS ==========
                    // MAX_TEXTURE_SIZE - vary by GPU tier
                    if (param === 0x0D33 || param === 3379) {{
                        const sizes = [8192, 16384, 32768];
                        const sizeIdx = Math.floor(seededRandom(webglSeed, 1) * sizes.length);
                        return sizes[sizeIdx];
                    }}
                    // MAX_CUBE_MAP_TEXTURE_SIZE - correlate with MAX_TEXTURE_SIZE
                    if (param === 0x851C || param === 34076) {{
                        const sizes = [8192, 16384, 32768];
                        const sizeIdx = Math.floor(seededRandom(webglSeed, 1) * sizes.length);
                        return sizes[sizeIdx];
                    }}
                    // MAX_RENDERBUFFER_SIZE - vary by GPU
                    if (param === 0x84E8 || param === 34024) {{
                        const sizes = [8192, 16384, 32768];
                        const sizeIdx = Math.floor(seededRandom(webglSeed, 2) * sizes.length);
                        return sizes[sizeIdx];
                    }}
                    // MAX_TEXTURE_IMAGE_UNITS
                    if (param === 0x8872 || param === 34930) {{
                        return Math.floor(seededRandom(webglSeed, 10) * 4) + 16; // 16-20
                    }}
                    // MAX_VERTEX_TEXTURE_IMAGE_UNITS
                    if (param === 0x8B4C || param === 35660) {{
                        return Math.floor(seededRandom(webglSeed, 11) * 4) + 16; // 16-20
                    }}
                    // MAX_COMBINED_TEXTURE_IMAGE_UNITS
                    if (param === 0x8B4D || param === 35661) {{
                        return Math.floor(seededRandom(webglSeed, 12) * 8) + 32; // 32-40
                    }}

                    // ========== VIEWPORT & DIMENSIONS ==========
                    // MAX_VIEWPORT_DIMS - correlate with screen resolution
                    if (param === 0x0D3A || param === 3386) {{
                        const maxDim = {fp["screen"]["width"]} > 2560 ? 32768 : 16384;
                        return new Int32Array([maxDim, maxDim]);
                    }}

                    // ========== VERTEX & FRAGMENT SHADER LIMITS ==========
                    // MAX_VERTEX_ATTRIBS - important for fingerprinting
                    if (param === 0x8869 || param === 34921) {{
                        return Math.floor(seededRandom(webglSeed, 4) * 2) + 16; // 16-17
                    }}
                    // MAX_VARYING_VECTORS
                    if (param === 0x8DFC || param === 36348) {{
                        return Math.floor(seededRandom(webglSeed, 5) * 4) + 30; // 30-33
                    }}
                    // MAX_VERTEX_UNIFORM_VECTORS
                    if (param === 0x8DFB || param === 36347) {{
                        const values = [1024, 4096];
                        return values[Math.floor(seededRandom(webglSeed, 6) * values.length)];
                    }}
                    // MAX_FRAGMENT_UNIFORM_VECTORS
                    if (param === 0x8DFD || param === 36349) {{
                        const values = [1024, 4096];
                        return values[Math.floor(seededRandom(webglSeed, 7) * values.length)];
                    }}

                    // ========== ALIASING & POINT SIZE ==========
                    // ALIASED_LINE_WIDTH_RANGE - subtle GPU-specific variation
                    if (param === 0x846E || param === 33902) {{
                        const variation = seededRandom(webglSeed, 3) * 0.1;
                        return new Float32Array([1, 7.375 + variation]);
                    }}
                    // ALIASED_POINT_SIZE_RANGE - correlate with line width
                    if (param === 0x846D || param === 33901) {{
                        const variation = seededRandom(webglSeed, 8) * 10;
                        return new Float32Array([1, 255 + variation]);
                    }}

                    // ========== COLOR & STENCIL BUFFERS ==========
                    // RED_BITS, GREEN_BITS, BLUE_BITS, ALPHA_BITS
                    if (param === 0x0D52 || param === 3410) return 8; // RED_BITS
                    if (param === 0x0D53 || param === 3411) return 8; // GREEN_BITS
                    if (param === 0x0D54 || param === 3412) return 8; // BLUE_BITS
                    if (param === 0x0D55 || param === 3413) return 8; // ALPHA_BITS
                    if (param === 0x0D56 || param === 3414) return 24; // DEPTH_BITS
                    if (param === 0x0D57 || param === 3415) return 8; // STENCIL_BITS

                    // ========== ANTIALIASING ==========
                    // SAMPLES - vary antialiasing capability
                    if (param === 0x80A9 || param === 32937) {{
                        const samples = [0, 2, 4, 8];
                        return samples[Math.floor(seededRandom(webglSeed, 9) * samples.length)];
                    }}
                    // MAX_SAMPLES
                    if (param === 0x8D57 || param === 36183) {{
                        const maxSamples = [4, 8, 16];
                        return maxSamples[Math.floor(seededRandom(webglSeed, 13) * maxSamples.length)];
                    }}

                    // ========== SHADER PRECISION ==========
                    // SHADING_LANGUAGE_VERSION - important identifier
                    if (param === 0x8B8C || param === 35724) {{
                        return 'WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)';
                    }}
                    // VERSION
                    if (param === 0x1F02 || param === 7938) {{
                        return 'WebGL 1.0 (OpenGL ES 2.0 Chromium)';
                    }}

                    // ========== WEBGL2 SPECIFIC PARAMETERS ==========
                    // MAX_3D_TEXTURE_SIZE (WebGL2)
                    if (param === 0x8073 || param === 32883) {{
                        const sizes = [2048, 4096];
                        return sizes[Math.floor(seededRandom(webglSeed, 14) * sizes.length)];
                    }}
                    // MAX_ARRAY_TEXTURE_LAYERS (WebGL2)
                    if (param === 0x88FF || param === 35071) {{
                        const layers = [256, 2048];
                        return layers[Math.floor(seededRandom(webglSeed, 15) * layers.length)];
                    }}
                    // MAX_COLOR_ATTACHMENTS (WebGL2)
                    if (param === 0x8CDF || param === 36063) {{
                        return Math.floor(seededRandom(webglSeed, 16) * 4) + 8; // 8-11
                    }}
                    // MAX_DRAW_BUFFERS (WebGL2)
                    if (param === 0x8824 || param === 34852) {{
                        return Math.floor(seededRandom(webglSeed, 17) * 4) + 8; // 8-11
                    }}
                    // MAX_ELEMENT_INDEX (WebGL2)
                    if (param === 0x8D6B || param === 36203) {{
                        return 4294967295; // 2^32 - 1
                    }}
                    // MAX_ELEMENTS_INDICES (WebGL2)
                    if (param === 0x80E9 || param === 33001) {{
                        return Math.floor(seededRandom(webglSeed, 18) * 1000000) + 1000000;
                    }}
                    // MAX_ELEMENTS_VERTICES (WebGL2)
                    if (param === 0x80E8 || param === 33000) {{
                        return Math.floor(seededRandom(webglSeed, 19) * 1000000) + 1000000;
                    }}
                    // MAX_FRAGMENT_INPUT_COMPONENTS (WebGL2)
                    if (param === 0x9125 || param === 37157) {{
                        const values = [60, 128];
                        return values[Math.floor(seededRandom(webglSeed, 20) * values.length)];
                    }}
                    // MAX_UNIFORM_BLOCK_SIZE (WebGL2)
                    if (param === 0x8A30 || param === 35376) {{
                        return 65536;
                    }}
                    // MAX_UNIFORM_BUFFER_BINDINGS (WebGL2)
                    if (param === 0x8A2F || param === 35375) {{
                        return Math.floor(seededRandom(webglSeed, 21) * 12) + 72; // 72-83
                    }}

                    return target.apply(ctx, args);
                }}
            }};

            if (typeof WebGLRenderingContext !== 'undefined') {{
                const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = new Proxy(originalGetParameter, getParameterProxyHandler);
            }}

            if (typeof WebGL2RenderingContext !== 'undefined') {{
                const originalGetParameter2 = WebGL2RenderingContext.prototype.getParameter;
                WebGL2RenderingContext.prototype.getParameter = new Proxy(originalGetParameter2, getParameterProxyHandler);
            }}

            // ========== WEBGL EXTENSION SPOOFING ==========

            // Spoof getSupportedExtensions to return realistic extension list
            // Extensions vary by GPU vendor - correlate with spoofed renderer
            const gpuVendor = '{fp["webgl"]["vendor"]}';
            const isNvidia = gpuVendor.includes('NVIDIA');
            const isAMD = gpuVendor.includes('AMD');
            const isIntel = gpuVendor.includes('Intel');

            // Core extensions common to all GPUs
            const coreExtensions = [
                'ANGLE_instanced_arrays',
                'EXT_blend_minmax',
                'EXT_color_buffer_half_float',
                'EXT_disjoint_timer_query',
                'EXT_float_blend',
                'EXT_frag_depth',
                'EXT_shader_texture_lod',
                'EXT_texture_compression_bptc',
                'EXT_texture_compression_rgtc',
                'EXT_texture_filter_anisotropic',
                'KHR_parallel_shader_compile',
                'OES_element_index_uint',
                'OES_fbo_render_mipmap',
                'OES_standard_derivatives',
                'OES_texture_float',
                'OES_texture_float_linear',
                'OES_texture_half_float',
                'OES_texture_half_float_linear',
                'OES_vertex_array_object',
                'WEBGL_color_buffer_float',
                'WEBGL_compressed_texture_s3tc',
                'WEBGL_compressed_texture_s3tc_srgb',
                'WEBGL_debug_renderer_info',
                'WEBGL_debug_shaders',
                'WEBGL_depth_texture',
                'WEBGL_draw_buffers',
                'WEBGL_lose_context',
                'WEBGL_multi_draw'
            ];

            // High-end GPU extensions (NVIDIA/AMD)
            const highEndExtensions = [
                'EXT_color_buffer_float',
                'EXT_texture_compression_s3tc',
                'WEBGL_compressed_texture_astc',
                'WEBGL_compressed_texture_etc',
                'WEBGL_compressed_texture_etc1',
                'WEBGL_compressed_texture_pvrtc'
            ];

            // Combine based on GPU tier
            let supportedExtensions = [...coreExtensions];
            if (isNvidia || isAMD) {{
                // High-end GPUs get more extensions
                supportedExtensions = supportedExtensions.concat(highEndExtensions);
            }} else if (isIntel) {{
                // Intel gets fewer extensions (integrated GPU)
                supportedExtensions = supportedExtensions.concat(['EXT_texture_compression_s3tc']);
            }}

            // Spoof getSupportedExtensions
            if (typeof WebGLRenderingContext !== 'undefined') {{
                const origGetSupportedExtensions = WebGLRenderingContext.prototype.getSupportedExtensions;
                WebGLRenderingContext.prototype.getSupportedExtensions = function() {{
                    return supportedExtensions;
                }};

                // Also spoof getExtension to return consistent results
                const origGetExtension = WebGLRenderingContext.prototype.getExtension;
                WebGLRenderingContext.prototype.getExtension = function(name) {{
                    // Only return extension if it's in our supported list
                    if (supportedExtensions.includes(name)) {{
                        return origGetExtension.call(this, name);
                    }}
                    return null;
                }};
            }}

            if (typeof WebGL2RenderingContext !== 'undefined') {{
                const origGetSupportedExtensions2 = WebGL2RenderingContext.prototype.getSupportedExtensions;
                WebGL2RenderingContext.prototype.getSupportedExtensions = function() {{
                    return supportedExtensions;
                }};

                const origGetExtension2 = WebGL2RenderingContext.prototype.getExtension;
                WebGL2RenderingContext.prototype.getExtension = function(name) {{
                    if (supportedExtensions.includes(name)) {{
                        return origGetExtension2.call(this, name);
                    }}
                    return null;
                }};
            }}

            // ========== CANVAS FINGERPRINT NOISE ==========

            const canvasNoise = {fp["noise"]["canvas"]};
            const canvasPrefix = '{fp["fingerprint_prefixes"]["canvas"]}';
            const webglPrefix = '{fp["fingerprint_prefixes"]["webgl"]}';
            const fontModifier = '{fp["fingerprint_prefixes"]["font_modifier"]}';

            // Deterministic seeded random based on canvas prefix
            // This ensures the same device profile always generates the same canvas fingerprint
            function seededRandom(seed, index) {{
                const x = Math.sin(seed + index) * 10000;
                return x - Math.floor(x);
            }}

            // Convert hex prefix to numeric seed
            const canvasSeed = parseInt(canvasPrefix.substring(0, 8), 16) / 0xFFFFFFFF;

            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(...args) {{
                const context = this.getContext('2d');
                if (context) {{
                    const imageData = context.getImageData(0, 0, this.width, this.height);
                    const pixels = imageData.data;
                    // Add deterministic noise based on canvas prefix
                    // This makes each device profile unique but consistent
                    for (let i = 0; i < pixels.length; i += 4) {{
                        const noise1 = seededRandom(canvasSeed, i) - 0.5;
                        const noise2 = seededRandom(canvasSeed, i + 1) - 0.5;
                        const noise3 = seededRandom(canvasSeed, i + 2) - 0.5;
                        pixels[i] = pixels[i] + Math.floor(noise1 * canvasNoise * 255);
                        pixels[i+1] = pixels[i+1] + Math.floor(noise2 * canvasNoise * 255);
                        pixels[i+2] = pixels[i+2] + Math.floor(noise3 * canvasNoise * 255);
                    }}
                    context.putImageData(imageData, 0, 0);
                }}
                return originalToDataURL.apply(this, args);
            }};

            const originalToBlobCanvas = HTMLCanvasElement.prototype.toBlob;
            HTMLCanvasElement.prototype.toBlob = function(...args) {{
                const context = this.getContext('2d');
                if (context) {{
                    const imageData = context.getImageData(0, 0, this.width, this.height);
                    const pixels = imageData.data;
                    // Same deterministic noise for consistency
                    for (let i = 0; i < pixels.length; i += 4) {{
                        const noise1 = seededRandom(canvasSeed, i) - 0.5;
                        const noise2 = seededRandom(canvasSeed, i + 1) - 0.5;
                        const noise3 = seededRandom(canvasSeed, i + 2) - 0.5;
                        pixels[i] = pixels[i] + Math.floor(noise1 * canvasNoise * 255);
                        pixels[i+1] = pixels[i+1] + Math.floor(noise2 * canvasNoise * 255);
                        pixels[i+2] = pixels[i+2] + Math.floor(noise3 * canvasNoise * 255);
                    }}
                    context.putImageData(imageData, 0, 0);
                }}
                return originalToBlobCanvas.apply(this, args);
            }};

            // Override getImageData to also include prefix-based variation
            const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
            CanvasRenderingContext2D.prototype.getImageData = function(...args) {{
                const imageData = originalGetImageData.apply(this, args);
                // Store canvas prefix in image data for fingerprinting tools to pick up
                if (imageData.data.length > 16) {{
                    // Encode prefix into first few pixels (very subtle)
                    const prefixBytes = canvasPrefix.match(/.{{1,2}}/g).map(byte => parseInt(byte, 16));
                    for (let i = 0; i < Math.min(prefixBytes.length, 4); i++) {{
                        imageData.data[i * 4 + 3] = imageData.data[i * 4 + 3] ^ (prefixBytes[i] & 0x0F);
                    }}
                }}
                return imageData;
            }};

            // ========== AUDIO CONTEXT FINGERPRINT ==========

            const audioNoise = {fp["noise"]["audio"]};

            // Deterministic audio seed based on WebGL prefix (correlate with GPU)
            const audioSeed = parseInt(webglPrefix.substring(0, 8), 16) / 0xFFFFFFFF;

            if (typeof AudioContext !== 'undefined') {{
                const OriginalAudioContext = AudioContext;
                window.AudioContext = function(...args) {{
                    const ctx = new OriginalAudioContext(...args);

                    // Add deterministic noise to oscillator based on device profile
                    const originalCreateOscillator = ctx.createOscillator.bind(ctx);
                    ctx.createOscillator = function() {{
                        const oscillator = originalCreateOscillator();
                        const originalStart = oscillator.start.bind(oscillator);
                        oscillator.start = function(when) {{
                            // Use seeded random for consistent but unique audio fingerprint
                            const noiseValue = seededRandom(audioSeed, Date.now() % 1000) - 0.5;
                            oscillator.frequency.value = oscillator.frequency.value * (1 + noiseValue * audioNoise);
                            return originalStart(when);
                        }};
                        return oscillator;
                    }};

                    // Also modify the audio context's sample rate representation
                    const originalSampleRate = ctx.sampleRate;
                    Object.defineProperty(ctx, 'sampleRate', {{
                        get: function() {{
                            // Slight variation based on device profile
                            const variation = Math.floor(seededRandom(audioSeed, 42) * 100);
                            return originalSampleRate + (variation % 2 === 0 ? 0 : 0);
                        }}
                    }});

                    return ctx;
                }};
                window.AudioContext.prototype = OriginalAudioContext.prototype;
            }}

            // ========== FONT ENUMERATION CONTROL ==========

            // Block font enumeration via size measurements (common fingerprinting technique)
            // Use font modifier to create platform-specific variations
            const fontSeed = parseInt(fontModifier.substring(1, 3), 16) / 255;

            if (typeof document !== 'undefined' && document.fonts) {{
                const originalCheck = document.fonts.check.bind(document.fonts);
                document.fonts.check = function(...args) {{
                    // Add deterministic timing variation based on platform
                    const delay = seededRandom(fontSeed, args[0] ? args[0].length : 1) * 2;
                    return originalCheck(...args);
                }};

                // Override font loading events with platform-specific timing
                const originalLoad = document.fonts.load.bind(document.fonts);
                document.fonts.load = async function(...args) {{
                    const result = await originalLoad(...args);
                    // Platform-specific delay in font loading
                    const loadDelay = seededRandom(fontSeed, 999) * 5;
                    await new Promise(resolve => setTimeout(resolve, loadDelay));
                    return result;
                }};
            }}

            // Override text measurement for font fingerprinting defense
            const originalMeasureText = CanvasRenderingContext2D.prototype.measureText;
            CanvasRenderingContext2D.prototype.measureText = function(text) {{
                const metrics = originalMeasureText.apply(this, arguments);
                // Add platform-specific micro-variations to font metrics
                const fontVariation = seededRandom(fontSeed, text.length) * 0.01;
                const modifiedWidth = metrics.width * (1 + fontVariation);

                return new Proxy(metrics, {{
                    get(target, prop) {{
                        if (prop === 'width') {{
                            return modifiedWidth;
                        }}
                        return target[prop];
                    }}
                }});
            }};

            // ========== TIMEZONE ==========

            const originalDateToString = Date.prototype.toString;
            Date.prototype.toString = function() {{
                const str = originalDateToString.apply(this);
                // Keep timezone consistent
                return str;
            }};

            // ========== CHROME RUNTIME ==========

            if (!window.chrome) {{
                window.chrome = {{}};
            }}

            window.chrome.runtime = {{
                OnInstalledReason: {{
                    CHROME_UPDATE: 'chrome_update',
                    INSTALL: 'install',
                    SHARED_MODULE_UPDATE: 'shared_module_update',
                    UPDATE: 'update'
                }},
                OnRestartRequiredReason: {{
                    APP_UPDATE: 'app_update',
                    OS_UPDATE: 'os_update',
                    PERIODIC: 'periodic'
                }},
                PlatformArch: {{
                    ARM: 'arm',
                    ARM64: 'arm64',
                    MIPS: 'mips',
                    MIPS64: 'mips64',
                    X86_32: 'x86-32',
                    X86_64: 'x86-64'
                }},
                PlatformNaclArch: {{
                    ARM: 'arm',
                    MIPS: 'mips',
                    MIPS64: 'mips64',
                    X86_32: 'x86-32',
                    X86_64: 'x86-64'
                }},
                PlatformOs: {{
                    ANDROID: 'android',
                    CROS: 'cros',
                    LINUX: 'linux',
                    MAC: 'mac',
                    OPENBSD: 'openbsd',
                    WIN: 'win'
                }},
                RequestUpdateCheckStatus: {{
                    NO_UPDATE: 'no_update',
                    THROTTLED: 'throttled',
                    UPDATE_AVAILABLE: 'update_available'
                }}
            }};

            // ========== NOTIFICATION ==========

            if (typeof Notification !== 'undefined') {{
                Object.defineProperty(Notification, 'permission', {{
                    get: () => 'default',
                    configurable: true
                }});
            }}

            // ========== HIDE CDP MESSAGES (Advanced) ==========

            // Patch WebSocket to hide CDP detection
            const OriginalWebSocket = window.WebSocket;
            window.WebSocket = function(...args) {{
                const ws = new OriginalWebSocket(...args);

                // Block messages containing CDP signatures
                const originalSend = ws.send.bind(ws);
                ws.send = function(data) {{
                    if (typeof data === 'string' && (
                        data.includes('Runtime.enable') ||
                        data.includes('Debugger.enable') ||
                        data.includes('CDP')
                    )) {{
                        // Block CDP-related messages
                        return;
                    }}
                    return originalSend(data);
                }};

                return ws;
            }};
            window.WebSocket.prototype = OriginalWebSocket.prototype;

            // ========== CONSOLE DEBUG SUPPRESSION ==========

            const originalConsoleDebug = console.debug;
            console.debug = function(...args) {{
                // Filter automation-related debug logs
                if (args.length && typeof args[0] === 'string') {{
                    const msg = args[0].toLowerCase();
                    if (msg.includes('automation') || msg.includes('puppeteer') || msg.includes('playwright')) {{
                        return;
                    }}
                }}
                return originalConsoleDebug.apply(this, args);
            }};

            // ========== CHROME APP ==========

            if (!window.chrome.app) {{
                window.chrome.app = {{
                    isInstalled: false,
                    InstallState: {{ DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' }},
                    RunningState: {{ CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }}
                }};
            }}

            // ========== BATTERY STATUS (Desktop = no battery) ==========

            if (navigator.getBattery) {{
                const originalGetBattery = navigator.getBattery.bind(navigator);
                navigator.getBattery = async function() {{
                    const battery = await originalGetBattery();
                    Object.defineProperty(battery, 'charging', {{ get: () => true }});
                    Object.defineProperty(battery, 'chargingTime', {{ get: () => 0 }});
                    Object.defineProperty(battery, 'dischargingTime', {{ get: () => Infinity }});
                    Object.defineProperty(battery, 'level', {{ get: () => 1 }});
                    return battery;
                }};
            }}

            // ========== CONNECTION TYPE ==========

            if (navigator.connection) {{
                Object.defineProperty(navigator.connection, 'rtt', {{ get: () => 50 }});
                Object.defineProperty(navigator.connection, 'downlink', {{ get: () => 10 }});
                Object.defineProperty(navigator.connection, 'effectiveType', {{ get: () => '4g' }});
            }}

            // ========== FETCH/XHR INTERCEPTION ==========

            // Deterministic timing seed for request delays
            const requestSeed = parseInt(canvasPrefix.substring(2, 6), 16) / 0xFFFF;

            // Helper to get current page origin
            function getCurrentOrigin() {{
                return window.location.origin;
            }}

            // Helper to add realistic timing delay to requests
            async function addRequestDelay() {{
                // Add slight random delay (1-15ms) to mimic network overhead
                const delay = Math.floor(seededRandom(requestSeed, Date.now() % 10000) * 15) + 1;
                await new Promise(resolve => setTimeout(resolve, delay));
            }}

            // Helper to generate realistic sec-fetch headers based on request type
            function getSecFetchHeaders(url, method, mode, requestType) {{
                const headers = {{}};
                const targetUrl = new URL(url, window.location.href);
                const isSameOrigin = targetUrl.origin === window.location.origin;

                // Sec-Fetch-Site
                if (isSameOrigin) {{
                    headers['Sec-Fetch-Site'] = 'same-origin';
                }} else if (targetUrl.hostname.endsWith(window.location.hostname.split('.').slice(-2).join('.'))) {{
                    headers['Sec-Fetch-Site'] = 'same-site';
                }} else {{
                    headers['Sec-Fetch-Site'] = 'cross-site';
                }}

                // Sec-Fetch-Mode
                headers['Sec-Fetch-Mode'] = mode || 'cors';

                // Sec-Fetch-Dest
                if (requestType === 'xhr') {{
                    headers['Sec-Fetch-Dest'] = 'empty';
                }} else if (requestType === 'fetch') {{
                    // Determine dest based on accept header or default to empty
                    headers['Sec-Fetch-Dest'] = 'empty';
                }}

                return headers;
            }}

            // Intercept fetch()
            const originalFetch = window.fetch;
            window.fetch = async function(resource, init) {{
                init = init || {{}};
                const url = typeof resource === 'string' ? resource : resource.url;
                const method = (init.method || 'GET').toUpperCase();
                const mode = init.mode || 'cors';

                // Add timing delay to mimic natural request patterns
                await addRequestDelay();

                // Clone headers to avoid modifying original
                const headers = new Headers(init.headers || {{}});

                // Add Accept header if not present (based on common patterns)
                if (!headers.has('Accept')) {{
                    // Realistic Accept header for JSON APIs
                    if (url.includes('/api/') || url.includes('.json')) {{
                        headers.set('Accept', 'application/json, text/plain, */*');
                    }} else {{
                        headers.set('Accept', '*/*');
                    }}
                }}

                // Add Accept-Language if not present
                if (!headers.has('Accept-Language')) {{
                    headers.set('Accept-Language', '{fp["locale"]["languages"][0]},en;q=0.9');
                }}

                // Add Referer if not present and not cross-origin
                if (!headers.has('Referer') && window.location.href !== 'about:blank') {{
                    try {{
                        const targetUrl = new URL(url, window.location.href);
                        const isSameOrigin = targetUrl.origin === window.location.origin;
                        if (isSameOrigin || mode !== 'no-cors') {{
                            headers.set('Referer', window.location.href);
                        }}
                    }} catch (e) {{
                        // Invalid URL, skip referer
                    }}
                }}

                // Add sec-fetch-* headers (critical for modern bot detection)
                const secFetchHeaders = getSecFetchHeaders(url, method, mode, 'fetch');
                for (const [key, value] of Object.entries(secFetchHeaders)) {{
                    if (!headers.has(key)) {{
                        headers.set(key, value);
                    }}
                }}

                // Add Accept-Encoding if not present
                if (!headers.has('Accept-Encoding')) {{
                    headers.set('Accept-Encoding', 'gzip, deflate, br');
                }}

                // Update init with modified headers
                init.headers = headers;

                // Call original fetch
                try {{
                    const response = await originalFetch(resource, init);
                    return response;
                }} catch (error) {{
                    throw error;
                }}
            }};

            // Keep prototype to avoid detection
            window.fetch.toString = function() {{
                return 'function fetch() {{ [native code] }}';
            }};

            // Intercept XMLHttpRequest
            const OriginalXMLHttpRequest = window.XMLHttpRequest;

            function StealthXMLHttpRequest() {{
                const xhr = new OriginalXMLHttpRequest();
                const originalOpen = xhr.open;
                const originalSend = xhr.send;
                const originalSetRequestHeader = xhr.setRequestHeader;

                let method = 'GET';
                let url = '';
                let async = true;
                const customHeaders = {{}};
                let hasAcceptHeader = false;
                let hasRefererHeader = false;
                let hasAcceptLanguageHeader = false;
                let hasAcceptEncodingHeader = false;

                // Track which headers were set
                xhr.setRequestHeader = function(header, value) {{
                    const headerLower = header.toLowerCase();
                    customHeaders[header] = value;

                    if (headerLower === 'accept') hasAcceptHeader = true;
                    if (headerLower === 'referer') hasRefererHeader = true;
                    if (headerLower === 'accept-language') hasAcceptLanguageHeader = true;
                    if (headerLower === 'accept-encoding') hasAcceptEncodingHeader = true;

                    return originalSetRequestHeader.call(this, header, value);
                }};

                xhr.open = function(m, u, a = true) {{
                    method = m;
                    url = u;
                    async = a;
                    return originalOpen.call(this, m, u, a);
                }};

                xhr.send = function(body) {{
                    // Add realistic headers before sending

                    // Add Accept if not present
                    if (!hasAcceptHeader) {{
                        if (url.includes('/api/') || url.includes('.json')) {{
                            originalSetRequestHeader.call(this, 'Accept', 'application/json, text/plain, */*');
                        }} else if (url.includes('.xml')) {{
                            originalSetRequestHeader.call(this, 'Accept', 'text/xml, application/xml, */*');
                        }} else {{
                            originalSetRequestHeader.call(this, 'Accept', '*/*');
                        }}
                    }}

                    // Add Accept-Language if not present
                    if (!hasAcceptLanguageHeader) {{
                        originalSetRequestHeader.call(this, 'Accept-Language', '{fp["locale"]["languages"][0]},en;q=0.9');
                    }}

                    // Add Referer if not present
                    if (!hasRefererHeader && window.location.href !== 'about:blank') {{
                        try {{
                            const targetUrl = new URL(url, window.location.href);
                            const isSameOrigin = targetUrl.origin === window.location.origin;
                            if (isSameOrigin) {{
                                originalSetRequestHeader.call(this, 'Referer', window.location.href);
                            }}
                        }} catch (e) {{
                            // Invalid URL, skip referer
                        }}
                    }}

                    // Add Accept-Encoding if not present
                    if (!hasAcceptEncodingHeader) {{
                        originalSetRequestHeader.call(this, 'Accept-Encoding', 'gzip, deflate, br');
                    }}

                    // Add sec-fetch-* headers
                    const secFetchHeaders = getSecFetchHeaders(url, method, 'cors', 'xhr');
                    for (const [key, value] of Object.entries(secFetchHeaders)) {{
                        originalSetRequestHeader.call(this, key, value);
                    }}

                    // Add small delay before sending (mimic natural timing)
                    const delay = Math.floor(seededRandom(requestSeed, Date.now() % 10000) * 15) + 1;
                    setTimeout(() => {{
                        originalSend.call(xhr, body);
                    }}, delay);
                }};

                return xhr;
            }}

            // Copy prototype and static properties
            StealthXMLHttpRequest.prototype = OriginalXMLHttpRequest.prototype;
            Object.setPrototypeOf(StealthXMLHttpRequest, OriginalXMLHttpRequest);

            // Copy static properties
            for (const key in OriginalXMLHttpRequest) {{
                if (OriginalXMLHttpRequest.hasOwnProperty(key)) {{
                    StealthXMLHttpRequest[key] = OriginalXMLHttpRequest[key];
                }}
            }}

            // Replace global XMLHttpRequest
            window.XMLHttpRequest = StealthXMLHttpRequest;

            // Make toString look native
            window.XMLHttpRequest.toString = function() {{
                return 'function XMLHttpRequest() {{ [native code] }}';
            }};

        }})();
        """

        return script

    def get_context_options(self, proxy: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Get browser context options with fingerprint settings.

        Args:
            proxy: Optional proxy configuration

        Returns:
            Dictionary of context options for Playwright
        """
        fp = self.fingerprint

        # Sec-CH-UA headers for Client Hints
        sec_ch_ua_headers = {
            "Sec-CH-UA": '"Chromium";v="120", "Google Chrome";v="120", "Not=A?Brand";v="24"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-CH-UA-Platform-Version": '"15.0.0"',
            "Sec-CH-UA-Arch": '"x86"',
            "Sec-CH-UA-Bitness": '"64"',
            "Sec-CH-UA-Full-Version-List": '"Chromium";v="120.0.6099.130", "Google Chrome";v="120.0.6099.130", "Not=A?Brand";v="24.0.0.0"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1"
        }

        options = {
            "viewport": {
                "width": fp["screen"]["width"],
                "height": fp["screen"]["height"]
            },
            "locale": fp["locale"]["languages"][0],
            "timezone_id": fp["locale"]["timezone"],
            "color_scheme": "light",
            "device_scale_factor": 1,
            "is_mobile": False,
            "has_touch": False,
            "java_script_enabled": True,
            "accept_downloads": True,
            "ignore_https_errors": True,
            "extra_http_headers": sec_ch_ua_headers,
        }

        # Add proxy if provided
        if proxy:
            options["proxy"] = proxy

        return options


# =============================================================================
# 2. BEHAVIORAL MIMICRY
# =============================================================================

class BehaviorMimicry:
    """
    Human-like behavioral patterns to avoid bot detection.

    Features:
    - Bezier curve mouse movements
    - Natural typing with typos
    - Variable scroll behavior
    - Reading time simulation
    - Random pauses and micro-movements
    """

    @staticmethod
    def bezier_curve(
        start: Tuple[float, float],
        end: Tuple[float, float],
        steps: int = 30
    ) -> List[Tuple[float, float]]:
        """
        Generate smooth Bezier curve path for mouse movement.

        Args:
            start: Starting (x, y) coordinates
            end: Ending (x, y) coordinates
            steps: Number of points in curve

        Returns:
            List of (x, y) coordinates along curve
        """
        # Generate random control points for natural curve
        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2

        # Add randomness to control points
        offset_x1 = random.uniform(-100, 100)
        offset_y1 = random.uniform(-100, 100)
        control1 = (mid_x + offset_x1, mid_y + offset_y1)

        offset_x2 = random.uniform(-50, 50)
        offset_y2 = random.uniform(-50, 50)
        control2 = (mid_x + offset_x2, mid_y + offset_y2)

        points = []
        for i in range(steps + 1):
            t = i / steps
            # Cubic Bezier formula
            x = (
                (1-t)**3 * start[0] +
                3 * (1-t)**2 * t * control1[0] +
                3 * (1-t) * t**2 * control2[0] +
                t**3 * end[0]
            )
            y = (
                (1-t)**3 * start[1] +
                3 * (1-t)**2 * t * control1[1] +
                3 * (1-t) * t**2 * control2[1] +
                t**3 * end[1]
            )

            # Add micro-movements (jitter)
            if 0 < i < steps:
                x += random.uniform(-2, 2)
                y += random.uniform(-2, 2)

            points.append((x, y))

        return points

    @staticmethod
    async def move_mouse_naturally(
        page: Page,
        target_x: float,
        target_y: float,
        current_x: Optional[float] = None,
        current_y: Optional[float] = None
    ):
        """
        Move mouse to target with natural Bezier curve.

        Args:
            page: Playwright page
            target_x: Target X coordinate
            target_y: Target Y coordinate
            current_x: Starting X coordinate (default: center)
            current_y: Starting Y coordinate (default: center)
        """
        if current_x is None or current_y is None:
            viewport = page.viewport_size
            current_x = viewport['width'] / 2 if viewport else 960
            current_y = viewport['height'] / 2 if viewport else 540

        # Generate curve
        steps = random.randint(20, 40)
        points = BehaviorMimicry.bezier_curve((current_x, current_y), (target_x, target_y), steps)

        # Move along curve with variable speed
        for i, (x, y) in enumerate(points):
            await page.mouse.move(x, y)

            # Variable delay (slower at start/end, faster in middle)
            progress = i / len(points)
            if progress < 0.2 or progress > 0.8:
                delay = random.uniform(8, 15)
            else:
                delay = random.uniform(3, 8)

            await asyncio.sleep(delay / 1000)

    @staticmethod
    async def type_naturally(
        page: Page,
        selector: str,
        text: str,
        typo_probability: float = 0.02
    ):
        """
        Type text with human-like patterns including occasional typos.

        Args:
            page: Playwright page
            selector: Input field selector
            text: Text to type
            typo_probability: Chance of typo per character (0.02 = 2%)
        """
        # Click field first
        element = await page.query_selector(selector)
        if not element:
            return False

        await element.click()
        await asyncio.sleep(random.uniform(0.1, 0.3))

        # Clear field
        await page.keyboard.press("Control+a")
        await asyncio.sleep(random.uniform(0.03, 0.08))
        await page.keyboard.press("Backspace")
        await asyncio.sleep(random.uniform(0.08, 0.15))

        # Type each character
        for i, char in enumerate(text):
            # Occasional typo and correction
            if random.random() < typo_probability and len(text) > 10:
                # Type wrong character
                wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
                await page.keyboard.type(wrong_char)
                await asyncio.sleep(random.uniform(0.1, 0.2))

                # Pause (notice typo)
                await asyncio.sleep(random.uniform(0.2, 0.4))

                # Backspace
                await page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.1, 0.2))

            # Type actual character
            await page.keyboard.type(char)

            # Variable delay based on character
            if char in ' .!?,':
                await asyncio.sleep(random.uniform(0.08, 0.2))
            elif char == '\n':
                await asyncio.sleep(random.uniform(0.2, 0.4))
            else:
                # Fast burst occasionally
                if random.random() < 0.2:
                    await asyncio.sleep(random.uniform(0.03, 0.08))
                # Long pause occasionally (thinking)
                elif random.random() < 0.1:
                    await asyncio.sleep(random.uniform(0.3, 0.6))
                # Normal typing
                else:
                    await asyncio.sleep(random.uniform(0.08, 0.18))

        return True

    @staticmethod
    async def scroll_naturally(
        page: Page,
        direction: str = "down",
        amount: Optional[int] = None
    ):
        """
        Scroll with human-like variable speed.

        Args:
            page: Playwright page
            direction: "down" or "up"
            amount: Pixels to scroll (random if None)
        """
        if amount is None:
            amount = random.randint(200, 500)

        if direction == "up":
            amount = -amount

        # Scroll in chunks with variable speed
        chunks = random.randint(3, 6)
        chunk_size = amount / chunks

        for i in range(chunks):
            await page.mouse.wheel(0, chunk_size)
            # Variable delay between chunks
            await asyncio.sleep(random.uniform(0.02, 0.05))

        # Pause after scroll (reading time)
        if STEALTH_UTILS_AVAILABLE:
            await reading_delay()
        else:
            await asyncio.sleep(random.uniform(0.3, 0.8))

    @staticmethod
    async def reading_pause(content_length: int = 1000):
        """
        Pause as if reading content (proportional to length).

        Args:
            content_length: Approximate character count of content
        """
        # Average reading speed: 200-300 words per minute
        # ~5 characters per word = 1000-1500 chars per minute
        # Add some randomness
        base_delay = (content_length / 1250) * random.uniform(0.5, 1.5)
        # Cap at reasonable max
        delay = min(base_delay, 5.0)
        # Minimum delay
        delay = max(delay, 0.3)

        await asyncio.sleep(delay)

    @staticmethod
    async def random_micro_movements(page: Page, count: int = 3):
        """
        Make small random mouse movements (simulating fidgeting).

        Args:
            page: Playwright page
            count: Number of micro-movements
        """
        viewport = page.viewport_size
        if not viewport:
            return

        for _ in range(count):
            # Small random movement
            offset_x = random.uniform(-50, 50)
            offset_y = random.uniform(-50, 50)

            current = await page.evaluate("""() => {
                return {x: window.innerWidth / 2, y: window.innerHeight / 2};
            }""")

            new_x = max(0, min(viewport['width'], current['x'] + offset_x))
            new_y = max(0, min(viewport['height'], current['y'] + offset_y))

            await page.mouse.move(new_x, new_y)
            await asyncio.sleep(random.uniform(0.1, 0.3))


# =============================================================================
# 3. PROXY MANAGER
# =============================================================================

class ProxyManager:
    """
    Smart proxy rotation and management.

    Features:
    - Multiple proxy types (residential, mobile, datacenter)
    - Automatic rotation
    - Sticky sessions for related requests
    - Health checking
    - Geo-targeting
    """

    def __init__(self, proxies: Optional[List[Dict]] = None):
        """
        Initialize proxy manager.

        Args:
            proxies: List of proxy configs, e.g.:
                [
                    {"server": "http://proxy1:8080", "username": "user", "password": "pass", "type": "residential"},
                    {"server": "http://proxy2:8080", "type": "datacenter"},
                ]
        """
        self.proxies = proxies or []
        self.current_index = 0
        self.proxy_health: Dict[str, Dict] = {}
        self.sticky_sessions: Dict[str, Dict] = {}  # domain -> proxy

    def add_proxy(self, server: str, username: Optional[str] = None,
                  password: Optional[str] = None, proxy_type: str = "datacenter"):
        """Add a proxy to the pool"""
        proxy = {
            "server": server,
            "type": proxy_type
        }
        if username:
            proxy["username"] = username
        if password:
            proxy["password"] = password

        self.proxies.append(proxy)
        self.proxy_health[server] = {
            "failures": 0,
            "successes": 0,
            "last_used": 0
        }

    def get_proxy(self, domain: Optional[str] = None, sticky: bool = False) -> Optional[Dict]:
        """
        Get next proxy in rotation.

        Args:
            domain: Domain for sticky session
            sticky: If True, reuse same proxy for domain

        Returns:
            Proxy config dict or None
        """
        if not self.proxies:
            return None

        # Sticky session: return same proxy for domain
        if sticky and domain and domain in self.sticky_sessions:
            return self.sticky_sessions[domain]

        # Filter healthy proxies (< 3 recent failures)
        healthy_proxies = [
            p for p in self.proxies
            if self.proxy_health.get(p["server"], {}).get("failures", 0) < 3
        ]

        if not healthy_proxies:
            # Reset all if none healthy
            for server in self.proxy_health:
                self.proxy_health[server]["failures"] = 0
            healthy_proxies = self.proxies

        # Rotate
        proxy = healthy_proxies[self.current_index % len(healthy_proxies)]
        self.current_index += 1

        # Store for sticky session
        if sticky and domain:
            self.sticky_sessions[domain] = proxy

        # Update last used
        self.proxy_health[proxy["server"]]["last_used"] = time.time()

        return proxy

    def record_success(self, proxy: Dict):
        """Record successful proxy use"""
        server = proxy["server"]
        if server in self.proxy_health:
            self.proxy_health[server]["successes"] += 1
            self.proxy_health[server]["failures"] = max(0, self.proxy_health[server]["failures"] - 1)

    def record_failure(self, proxy: Dict):
        """Record proxy failure"""
        server = proxy["server"]
        if server in self.proxy_health:
            self.proxy_health[server]["failures"] += 1

    def get_stats(self) -> Dict:
        """Get proxy health statistics"""
        return {
            "total_proxies": len(self.proxies),
            "health": self.proxy_health
        }


# =============================================================================
# 4. DETECTION RESPONSE
# =============================================================================

class DetectionResponse:
    """
    Detect and respond to bot detection measures.

    Features:
    - CAPTCHA detection (reCAPTCHA, hCaptcha, Turnstile)
    - Block page detection
    - Bot score monitoring
    - Honeypot link avoidance
    """

    @staticmethod
    async def detect_captcha(page: Page) -> Dict[str, Any]:
        """
        Detect CAPTCHA on page.

        Returns:
            Dict with: has_captcha, captcha_type, site_key
        """
        result = {
            "has_captcha": False,
            "captcha_type": None,
            "site_key": None
        }

        try:
            # Check for hCaptcha
            hcaptcha = await page.query_selector('[data-sitekey][data-hcaptcha-widget-id], .h-captcha[data-sitekey]')
            if hcaptcha:
                site_key = await hcaptcha.get_attribute('data-sitekey')
                result.update({"has_captcha": True, "captcha_type": "hcaptcha", "site_key": site_key})
                return result

            # Check for reCAPTCHA v2
            recaptcha_v2 = await page.query_selector('.g-recaptcha[data-sitekey]')
            if recaptcha_v2:
                site_key = await recaptcha_v2.get_attribute('data-sitekey')
                result.update({"has_captcha": True, "captcha_type": "recaptcha_v2", "site_key": site_key})
                return result

            # Check for reCAPTCHA v3 (invisible)
            recaptcha_v3 = await page.evaluate("""() => {
                const scripts = document.querySelectorAll('script[src*="recaptcha"]');
                for (const s of scripts) {
                    if (s.src.includes('render=')) {
                        const match = s.src.match(/render=([^&]+)/);
                        if (match) return match[1];
                    }
                }
                return null;
            }""")
            if recaptcha_v3:
                result.update({"has_captcha": True, "captcha_type": "recaptcha_v3", "site_key": recaptcha_v3})
                return result

            # Check for Cloudflare Turnstile
            turnstile = await page.query_selector('.cf-turnstile')
            if turnstile:
                site_key = await turnstile.get_attribute('data-sitekey')
                result.update({"has_captcha": True, "captcha_type": "turnstile", "site_key": site_key})
                return result

        except Exception as e:
            logger.debug(f"CAPTCHA detection error: {e}")

        return result

    @staticmethod
    async def detect_block(page: Page) -> bool:
        """
        Detect if page is a block/access denied page.

        Returns:
            True if blocked, False otherwise
        """
        try:
            content = await page.content()
            title = await page.title()

            # Common block indicators
            block_indicators = [
                "access denied",
                "403 forbidden",
                "suspicious activity",
                "blocked",
                "you have been blocked",
                "security challenge",
                "attention required",
                "unusual traffic",
                "automated requests",
                "not authorized",
                "access is denied",
                "this site can't be reached",
            ]

            content_lower = content.lower()
            title_lower = title.lower()

            for indicator in block_indicators:
                if indicator in content_lower or indicator in title_lower:
                    return True

            # Check status code
            return False

        except Exception:
            return False

    @staticmethod
    async def detect_honeypots(page: Page) -> List[str]:
        """
        Detect honeypot links/elements to avoid.

        Returns:
            List of selectors to avoid clicking
        """
        try:
            honeypots = await page.evaluate("""() => {
                const suspicious = [];

                // Find hidden links (common honeypot technique)
                const links = document.querySelectorAll('a');
                links.forEach((link, i) => {
                    const style = window.getComputedStyle(link);

                    // Hidden via CSS
                    if (style.display === 'none' ||
                        style.visibility === 'hidden' ||
                        style.opacity === '0' ||
                        parseFloat(style.fontSize) < 1) {
                        suspicious.push(`a:nth-of-type(${i+1})`);
                    }

                    // Positioned off-screen
                    const rect = link.getBoundingClientRect();
                    if (rect.top < -100 || rect.left < -100) {
                        suspicious.push(`a:nth-of-type(${i+1})`);
                    }
                });

                return suspicious;
            }""")

            return honeypots or []

        except Exception:
            return []


# =============================================================================
# 5. SITE-SPECIFIC PROFILES
# =============================================================================

class SiteProfile:
    """
    Site-specific stealth profiles with custom settings.
    """

    PROFILES = {
        "linkedin": {
            "name": "LinkedIn",
            "proxy_type": "mobile",  # Prefer mobile proxies
            "delays": {
                "navigation": (3, 7),  # Slower, more cautious
                "action": (1, 3),
                "typing": (0.1, 0.3),
            },
            "behavior": {
                "scroll_before_extract": True,
                "random_movements": True,
                "reading_pauses": True,
            },
            "requirements": {
                "logged_in": True,  # Must be logged in
                "session_warmup": True,  # Visit homepage first
            }
        },
        "facebook": {
            "name": "Facebook",
            "proxy_type": "residential",
            "delays": {
                "navigation": (2, 5),
                "action": (0.5, 2),
                "typing": (0.08, 0.2),
            },
            "behavior": {
                "scroll_before_extract": True,
                "random_movements": True,
                "reading_pauses": True,
            },
            "requirements": {
                "logged_in": True,
                "session_warmup": True,
            }
        },
        "amazon": {
            "name": "Amazon",
            "proxy_type": "residential",
            "delays": {
                "navigation": (3, 8),  # Very slow, Amazon is aggressive
                "action": (1, 4),
                "typing": (0.1, 0.3),
            },
            "behavior": {
                "scroll_before_extract": True,
                "random_movements": True,
                "reading_pauses": True,
                "add_to_cart_sometimes": True,  # Mimic shopping behavior
            },
            "requirements": {
                "session_warmup": True,
                "visit_multiple_pages": True,
            }
        },
        "google": {
            "name": "Google",
            "proxy_type": "datacenter",  # Can use datacenter but rotate often
            "delays": {
                "navigation": (1, 3),
                "action": (0.3, 1),
                "typing": (0.08, 0.15),
            },
            "behavior": {
                "scroll_before_extract": False,
                "random_movements": False,
                "reading_pauses": False,
            },
            "requirements": {
                "rotate_frequently": True,
            }
        },
        "default": {
            "name": "Default",
            "proxy_type": "datacenter",
            "delays": {
                "navigation": (2, 4),
                "action": (0.5, 1.5),
                "typing": (0.08, 0.18),
            },
            "behavior": {
                "scroll_before_extract": False,
                "random_movements": False,
                "reading_pauses": True,
            },
            "requirements": {}
        }
    }

    @classmethod
    def get_profile(cls, url: str) -> Dict:
        """
        Get site profile based on URL.

        Args:
            url: Page URL

        Returns:
            Profile configuration dict
        """
        url_lower = url.lower()

        if "linkedin.com" in url_lower:
            return cls.PROFILES["linkedin"]
        elif "facebook.com" in url_lower or "fb.com" in url_lower:
            return cls.PROFILES["facebook"]
        elif "amazon.com" in url_lower:
            return cls.PROFILES["amazon"]
        elif "google.com" in url_lower:
            return cls.PROFILES["google"]
        else:
            return cls.PROFILES["default"]


# =============================================================================
# 6. ENHANCED STEALTH SESSION
# =============================================================================

class EnhancedStealthSession:
    """
    Complete stealth session manager integrating all components.

    Usage:
        async with EnhancedStealthSession(page) as session:
            await session.navigate("https://example.com")
            await session.click(".button")
            await session.type("#input", "text")
    """

    def __init__(
        self,
        page: Page,
        fingerprint_seed: Optional[str] = None,
        proxy_manager: Optional[ProxyManager] = None,
        enable_captcha_solver: bool = True,
        enable_tls_fingerprinting: bool = True
    ):
        """
        Initialize enhanced stealth session.

        Args:
            page: Playwright page
            fingerprint_seed: Optional seed for consistent fingerprints
            proxy_manager: Optional proxy manager
            enable_captcha_solver: Enable CAPTCHA solving
            enable_tls_fingerprinting: Enable TLS fingerprinting for pre-flight requests
        """
        self.page = page
        self.fingerprint_manager = FingerprintManager(fingerprint_seed)
        self.proxy_manager = proxy_manager
        self.enable_captcha_solver = enable_captcha_solver
        self.enable_tls_fingerprinting = enable_tls_fingerprinting

        # State tracking
        self.current_url = ""
        self.current_profile = SiteProfile.PROFILES["default"]
        self.mouse_x = 960
        self.mouse_y = 540
        self.actions_count = 0

        # CAPTCHA handler
        self.captcha_handler = None
        if enable_captcha_solver and CAPTCHA_SOLVER_AVAILABLE:
            self.captcha_handler = PageCaptchaHandler(page)

        # TLS fingerprinting wrapper
        self.tls_wrapper = None
        if enable_tls_fingerprinting and TLS_FINGERPRINT_AVAILABLE:
            self.tls_wrapper = TLSProxyWrapper("chrome120")
            logger.debug("TLS fingerprinting enabled")

    async def __aenter__(self):
        """Context manager entry"""
        await self.inject_fingerprint()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        pass

    async def inject_fingerprint(self):
        """Inject fingerprint spoofing scripts"""
        try:
            script = self.fingerprint_manager.get_injection_script()
            await self.page.add_init_script(script)
            logger.debug("[STEALTH] Fingerprint scripts injected")
        except Exception as e:
            logger.warning(f"[STEALTH] Failed to inject fingerprint: {e}")

    async def preflight_request(self, url: str) -> bool:
        """
        Make a pre-flight request with Chrome TLS fingerprint.

        This warms up the connection with a proper Chrome TLS handshake
        before Playwright navigates, making the subsequent Playwright
        request less suspicious to anti-bot systems.

        Args:
            url: URL to pre-warm

        Returns:
            True if successful, False otherwise
        """
        if not self.enable_tls_fingerprinting or not self.tls_wrapper:
            return True  # Skip if TLS fingerprinting disabled

        if not HAS_CURL_CFFI:
            logger.debug("[STEALTH] Skipping preflight (curl_cffi unavailable)")
            return True

        try:
            logger.debug(f"[STEALTH] Pre-flight TLS request to {url}")
            success = await self.tls_wrapper.head_with_tls(url)
            if success:
                logger.debug("[STEALTH] Pre-flight request successful")
            else:
                logger.debug("[STEALTH] Pre-flight request failed (continuing anyway)")
            return success
        except Exception as e:
            logger.warning(f"[STEALTH] Pre-flight request error: {e}")
            return True  # Continue anyway

    async def navigate(self, url: str):
        """
        Navigate to URL with stealth profile and TLS fingerprinting.

        Args:
            url: Target URL
        """
        self.current_url = url
        self.current_profile = SiteProfile.get_profile(url)

        logger.debug(f"[STEALTH] Using profile: {self.current_profile['name']}")

        # Pre-warm with TLS fingerprinted request (if enabled)
        await self.preflight_request(url)

        # Check for honeypots to avoid
        honeypots = await DetectionResponse.detect_honeypots(self.page)
        if honeypots:
            logger.debug(f"[STEALTH] Detected {len(honeypots)} honeypot elements")

        # Navigate with delays
        nav_delay = random.uniform(*self.current_profile["delays"]["navigation"])
        await asyncio.sleep(nav_delay)

        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            logger.warning(f"[STEALTH] Navigation error: {e}")
            return

        # Post-navigation checks
        await asyncio.sleep(random.uniform(1, 2))

        # Check for blocks
        if await DetectionResponse.detect_block(self.page):
            logger.warning("[STEALTH] Block page detected!")
            return

        # Check for CAPTCHA
        captcha_info = await DetectionResponse.detect_captcha(self.page)
        if captcha_info["has_captcha"]:
            logger.warning(f"[STEALTH] CAPTCHA detected: {captcha_info['captcha_type']}")

            if self.captcha_handler and CAPTCHA_SOLVER_AVAILABLE:
                # Try scrappy (free) bypass first
                bypasser = ScrappyCaptchaBypasser(self.page)
                success = await bypasser.bypass(manual_fallback=True, manual_timeout=30)
                if not success:
                    logger.error("[STEALTH] CAPTCHA bypass failed")

        # Behavior based on profile
        if self.current_profile["behavior"].get("scroll_before_extract"):
            await BehaviorMimicry.scroll_naturally(self.page, "down", random.randint(300, 600))
            await asyncio.sleep(random.uniform(0.5, 1.5))

        if self.current_profile["behavior"].get("random_movements"):
            await BehaviorMimicry.random_micro_movements(self.page, count=2)

    async def click(self, selector: str):
        """
        Click element with stealth behavior.

        Args:
            selector: Element selector
        """
        self.actions_count += 1

        # Pre-action delay
        action_delay = random.uniform(*self.current_profile["delays"]["action"])
        await asyncio.sleep(action_delay)

        # Get element
        element = await self.page.query_selector(selector)
        if not element:
            logger.warning(f"[STEALTH] Element not found: {selector}")
            return False

        # Get element position
        box = await element.bounding_box()
        if not box:
            logger.warning(f"[STEALTH] Element not visible: {selector}")
            return False

        # Target with slight offset (humans don't click dead center)
        target_x = box['x'] + box['width'] / 2 + random.uniform(-10, 10)
        target_y = box['y'] + box['height'] / 2 + random.uniform(-10, 10)

        # Move mouse naturally
        await BehaviorMimicry.move_mouse_naturally(
            self.page, target_x, target_y, self.mouse_x, self.mouse_y
        )

        self.mouse_x = target_x
        self.mouse_y = target_y

        # Click with human timing
        await asyncio.sleep(random.uniform(0.03, 0.08))
        await self.page.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.12))
        await self.page.mouse.up()

        return True

    async def type(self, selector: str, text: str):
        """
        Type text with stealth behavior.

        Args:
            selector: Input selector
            text: Text to type
        """
        self.actions_count += 1

        # Pre-action delay
        action_delay = random.uniform(*self.current_profile["delays"]["action"])
        await asyncio.sleep(action_delay)

        # Type naturally
        success = await BehaviorMimicry.type_naturally(
            self.page, selector, text, typo_probability=0.02
        )

        return success

    async def scroll(self, direction: str = "down", amount: Optional[int] = None):
        """
        Scroll with stealth behavior.

        Args:
            direction: "down" or "up"
            amount: Pixels to scroll
        """
        await BehaviorMimicry.scroll_naturally(self.page, direction, amount)

    async def wait_and_read(self, content_length: int = 1000):
        """
        Pause as if reading content.

        Args:
            content_length: Approximate character count
        """
        await BehaviorMimicry.reading_pause(content_length)


# =============================================================================
# 7. CONVENIENCE FUNCTIONS
# =============================================================================

async def create_stealth_context(
    playwright,
    headless: bool = False,
    proxy: Optional[Dict] = None,
    fingerprint_seed: Optional[str] = None
) -> Tuple[BrowserContext, FingerprintManager]:
    """
    Create browser context with full stealth configuration.

    Args:
        playwright: Playwright instance
        headless: Run headless
        proxy: Optional proxy config
        fingerprint_seed: Optional fingerprint seed

    Returns:
        (BrowserContext, FingerprintManager) tuple
    """
    # Generate fingerprint
    fp_manager = FingerprintManager(fingerprint_seed)

    # Get context options
    context_options = fp_manager.get_context_options(proxy)

    # Get stealth launch args
    if STEALTH_UTILS_AVAILABLE:
        launch_args = get_stealth_args()
        user_agent = get_random_user_agent()
    else:
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-automation",
            "--no-sandbox",
        ]
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    context_options["user_agent"] = user_agent

    # Launch browser
    browser = await playwright.chromium.launch(headless=headless, args=launch_args)
    context = await browser.new_context(**context_options)

    # Inject fingerprint scripts
    await context.add_init_script(fp_manager.get_injection_script())

    logger.debug("Enhanced context created")

    return context, fp_manager


def get_stealth_session(
    page: Page,
    fingerprint_seed: Optional[str] = None,
    proxy_manager: Optional[ProxyManager] = None
) -> EnhancedStealthSession:
    """
    Get enhanced stealth session for a page.

    Args:
        page: Playwright page
        fingerprint_seed: Optional fingerprint seed
        proxy_manager: Optional proxy manager

    Returns:
        EnhancedStealthSession instance
    """
    return EnhancedStealthSession(page, fingerprint_seed, proxy_manager)


# =============================================================================
# 8. INTEGRATION HELPERS
# =============================================================================

async def enhance_existing_page(page: Page, fingerprint_seed: Optional[str] = None):
    """
    Enhance an existing page with stealth features.

    Args:
        page: Playwright page to enhance
        fingerprint_seed: Optional fingerprint seed
    """
    fp_manager = FingerprintManager(fingerprint_seed)
    script = fp_manager.get_injection_script()

    try:
        # Inject into current page
        await page.evaluate(script)
        logger.debug("Page enhanced")
    except Exception as e:
        logger.warning(f"[STEALTH] Failed to enhance page: {e}")


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "FingerprintManager",
    "BehaviorMimicry",
    "ProxyManager",
    "DetectionResponse",
    "SiteProfile",
    "EnhancedStealthSession",
    "create_stealth_context",
    "get_stealth_session",
    "enhance_existing_page",
]
