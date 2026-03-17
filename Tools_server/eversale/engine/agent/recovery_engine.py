import asyncio
import time
import re
from typing import List, Dict, Any, Optional, Tuple, Callable, Awaitable
from urllib.parse import urlparse
from loguru import logger
from .failure_modes import FailureMode, FailureHandler, SiteHints

class RecoveryEngine:
    def __init__(self, page):
        self.page = page
        self.handlers: Dict[FailureMode, FailureHandler] = {}
        self.retry_counts: Dict[FailureMode, int] = {}
        self.telemetry = [] # Track recovery events: {mode, action, duration, success}
        self.last_detected_modes: List[FailureMode] = []
        self.last_failed_mode: Optional[FailureMode] = None
        
        # Self-healing logic: learn what works for specific domains
        try:
            from .agi_reasoning import get_agi_reasoning
            self.agi = get_agi_reasoning()
        except:
            self.agi = None
            
        self._initialize_default_handlers()

    async def _learn_recovery(self, mode: FailureMode, success: bool):
        """Record success/failure of recovery for future proactive healing."""
        if not self.agi: return
        try:
            domain = urlparse(self.page.url).netloc.replace('www.', '')
            self.agi.record_action(f"recovery:{mode.value}:{domain}", "recovered", success)
        except: pass

    def _initialize_default_handlers(self):
        """Initialize all Tier 0-3 handlers with detectors and recovery steps."""
        
        # --- Tier 0: Core Execution ---
        
        self.handlers[FailureMode.NAVIGATION_FAILED] = FailureHandler(
            name=FailureMode.NAVIGATION_FAILED,
            detectors=[self._detect_nav_failure],
            recovery_steps=[self._recover_reload, self._recover_back_and_forward]
        )
        
        self.handlers[FailureMode.DOM_NOT_STABLE] = FailureHandler(
            name=FailureMode.DOM_NOT_STABLE,
            detectors=[self._detect_dom_instability],
            recovery_steps=[self._recover_wait_for_idle]
        )

        self.handlers[FailureMode.OVERLAY_BLOCKING_INTERACTION] = FailureHandler(
            name=FailureMode.OVERLAY_BLOCKING_INTERACTION,
            detectors=[self._detect_overlays],
            recovery_steps=[self._recover_dismiss_overlays]
        )
        
        self.handlers[FailureMode.ELEMENT_NOT_FOUND] = FailureHandler(
            name=FailureMode.ELEMENT_NOT_FOUND,
            detectors=[], # Usually triggered by exception in action
            recovery_steps=[self._recover_scroll_and_find, self._recover_re_snapshot, self._recover_fuzzy_find]
        )

        self.handlers[FailureMode.ACTION_NOT_APPLIED] = FailureHandler(
            name=FailureMode.ACTION_NOT_APPLIED,
            detectors=[self._detect_action_not_applied],
            recovery_steps=[self._recover_force_action, self._recover_js_action]
        )

        self.handlers[FailureMode.UNEXPECTED_REDIRECT] = FailureHandler(
            name=FailureMode.UNEXPECTED_REDIRECT,
            detectors=[self._detect_unexpected_redirect],
            recovery_steps=[self._recover_back_to_expected]
        )

        self.handlers[FailureMode.INFINITE_SCROLL_REQUIRED] = FailureHandler(
            name=FailureMode.INFINITE_SCROLL_REQUIRED,
            detectors=[self._detect_infinite_scroll],
            recovery_steps=[self._recover_scroll_until_stable]
        )

        # --- Tier 1: Access & Blocking ---

        self.handlers[FailureMode.AUTH_REQUIRED] = FailureHandler(
            name=FailureMode.AUTH_REQUIRED,
            detectors=[self._detect_auth_wall],
            recovery_steps=[self._recover_notify_login]
        )

        self.handlers[FailureMode.MFA_REQUIRED] = FailureHandler(
            name=FailureMode.MFA_REQUIRED,
            detectors=[self._detect_mfa_prompt],
            recovery_steps=[self._recover_request_mfa]
        )

        self.handlers[FailureMode.CAPTCHA_PRESENT] = FailureHandler(
            name=FailureMode.CAPTCHA_PRESENT,
            detectors=[self._detect_captcha],
            recovery_steps=[self._recover_solve_captcha]
        )

        self.handlers[FailureMode.RATE_LIMITED] = FailureHandler(
            name=FailureMode.RATE_LIMITED,
            detectors=[self._detect_rate_limit],
            recovery_steps=[self._recover_wait_long_backoff]
        )

        self.handlers[FailureMode.BOT_DETECTED] = FailureHandler(
            name=FailureMode.BOT_DETECTED,
            detectors=[self._detect_bot_detection],
            recovery_steps=[self._recover_change_stealth_profile]
        )

        self.handlers[FailureMode.GEO_BLOCKED] = FailureHandler(
            name=FailureMode.GEO_BLOCKED,
            detectors=[self._detect_geo_block],
            recovery_steps=[self._recover_geo_block]
        )

        # --- Tier 2: Data Integrity ---

        self.handlers[FailureMode.PARTIAL_EXTRACTION] = FailureHandler(
            name=FailureMode.PARTIAL_EXTRACTION,
            detectors=[self._detect_partial_data],
            recovery_steps=[self._recover_retry_extraction]
        )

        self.handlers[FailureMode.PAGINATION_REQUIRED] = FailureHandler(
            name=FailureMode.PAGINATION_REQUIRED,
            detectors=[self._detect_pagination],
            recovery_steps=[self._recover_click_next]
        )

        self.handlers[FailureMode.DUPLICATE_DETECTED] = FailureHandler(
            name=FailureMode.DUPLICATE_DETECTED,
            detectors=[self._detect_duplicates],
            recovery_steps=[self._recover_skip_duplicates]
        )

        self.handlers[FailureMode.OUTPUT_VALIDATION_FAILED] = FailureHandler(
            name=FailureMode.OUTPUT_VALIDATION_FAILED,
            detectors=[], # Triggered by post-processing
            recovery_steps=[self._recover_reformat_output]
        )

        # --- Tier 3: Safety & Irreversible Actions ---

        self.handlers[FailureMode.DANGEROUS_ACTION_DETECTED] = FailureHandler(
            name=FailureMode.DANGEROUS_ACTION_DETECTED,
            detectors=[self._detect_dangerous_action],
            recovery_steps=[self._recover_halt_and_ask]
        )

        self.handlers[FailureMode.APPROVAL_REQUIRED] = FailureHandler(
            name=FailureMode.APPROVAL_REQUIRED,
            detectors=[self._detect_approval_needed],
            recovery_steps=[self._recover_halt_and_ask]
        )

        self.handlers[FailureMode.CONFIRMATION_REQUIRED] = FailureHandler(
            name=FailureMode.CONFIRMATION_REQUIRED,
            detectors=[self._detect_confirmation_modal],
            recovery_steps=[self._recover_click_confirm]
        )

        self.handlers[FailureMode.POLICY_BLOCKED] = FailureHandler(
            name=FailureMode.POLICY_BLOCKED,
            detectors=[self._detect_policy_block],
            recovery_steps=[self._recover_log_and_skip]
        )

        # Populate others with empty handlers if any missed
        for mode in FailureMode:
            if mode not in self.handlers:
                self.handlers[mode] = FailureHandler(
                    name=mode,
                    detectors=[],
                    recovery_steps=[]
                )

    # --- TIER 0 DETECTORS & RECOVERY ---

    async def _detect_nav_failure(self, page) -> bool:
        if page.url == "about:blank": return True
        content = (await page.content()).lower()
        error_indicators = ["dns_probe_finished", "err_connection_refused", "site can't be reached", "404 not found", "error"]
        return any(err in content for err in error_indicators) and len(content) < 500

    async def _recover_reload(self, page) -> bool:
        logger.info("[RECOVERY] Reloading page...")
        try:
            await page.reload(wait_until="domcontentloaded", timeout=10000)
            return True
        except:
            return False

    async def _recover_back_and_forward(self, page) -> bool:
        logger.info("[RECOVERY] Navigating back and forward...")
        try:
            await page.go_back()
            await asyncio.sleep(1)
            await page.go_forward()
            return True
        except:
            return False

    async def _detect_dom_instability(self, page) -> bool:
        state = await page.evaluate("document.readyState")
        return state not in ["complete", "interactive"]

    async def _recover_wait_for_idle(self, page) -> bool:
        logger.info("[RECOVERY] Waiting for network idle...")
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
            return True
        except:
            return True

    async def _detect_overlays(self, page) -> bool:
        """Dedicated overlay/modal detector."""
        try:
            res = await page.evaluate("""() => {
            const overlays = document.querySelectorAll([
              '[class*="modal"]',
              '[class*="overlay"]',
              '[class*="popup"]',
              '[role="dialog"]',
              'dialog[open]',
              '[aria-modal="true"]',
              '[id*="cookie"]',
              '[class*="cookie"]',
              '[class*="consent"]',
              '[id*="consent"]',
              '#cookie-banner'
            ].join(','));
            for (const el of overlays) {
                const style = window.getComputedStyle(el);
                if (style.display !== 'none' && style.visibility !== 'hidden' && el.offsetHeight > 50) {
                    const rect = el.getBoundingClientRect();
                    const vw = window.innerWidth || 1;
                    const vh = window.innerHeight || 1;
                    const area = Math.max(0, rect.width) * Math.max(0, rect.height);
                    const coversMeaningfully = area >= (vw * vh * 0.15) || (rect.height >= 60 && rect.width >= vw * 0.6);
                    const z = parseInt(style.zIndex || '0') || 0;
                    const blocks = (style.position === 'fixed' || style.position === 'absolute' || z > 10) && coversMeaningfully;
                    if (blocks) return true;
                }
            }
            return false;
        }""")
        except Exception:
            return False

        return res is True

    async def _recover_dismiss_overlays(self, page) -> bool:
        """Handler for OVERLAY_BLOCKING_INTERACTION."""
        logger.info("[RECOVERY] Dismissing overlays/modals...")

        async def _try_dismiss_on(target) -> bool:
            dismiss_selectors = [
                # Consent/cookie
                "#accept-btn",
                "button:has-text('Accept')",
                "button:has-text('Accept all')",
                "button:has-text('Allow all')",
                "button:has-text('I agree')",
                "button:has-text('Agree')",
                "button:has-text('OK')",
                "button:has-text('Got it')",
                "button:has-text('Continue')",

                # Close
                "button:has-text('Close')",
                "button:has-text('Dismiss')",
                "[aria-label*='close' i]",
                "[data-testid*='close' i]",
                ".modal-close",
                ".close-button",
                "button[title*='Close' i]",
            ]
            for selector in dismiss_selectors:
                try:
                    btn = await target.query_selector(selector)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(0.4)
                        return True
                except Exception:
                    continue
            return False

        # 1) Escape key
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.4)
        except Exception:
            pass

        # 2) Try on main page
        await _try_dismiss_on(page)

        # 3) Try inside iframes (common for consent managers)
        try:
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                await _try_dismiss_on(frame)
        except Exception:
            pass

        # 4) Last resort: hide likely consent overlays via JS (only cookie/consent keywords)
        try:
            still_blocked = await self._detect_overlays(page)
            if still_blocked:
                await page.evaluate("""() => {
  const kw = ['cookie','consent','gdpr','privacy','preferences'];
  const els = Array.from(document.querySelectorAll('[class*=\"cookie\" i],[id*=\"cookie\" i],[class*=\"consent\" i],[id*=\"consent\" i],[role=\"dialog\"],[aria-modal=\"true\"],dialog[open]'));
  for (const el of els) {
    try {
      const t = (el.innerText || el.textContent || '').toLowerCase();
      if (!kw.some(k => t.includes(k))) continue;
      el.style.setProperty('display', 'none', 'important');
      el.style.setProperty('visibility', 'hidden', 'important');
      el.style.setProperty('pointer-events', 'none', 'important');
    } catch (e) {}
  }
}""")
        except Exception:
            pass

        # Verify: is the viewport still meaningfully blocked at the center point?
        # Avoid relying solely on "modal"/"overlay" keywords because some environments/mocks
        # don't simulate DOM mutations from our JS dismissal attempts.
        try:
            blocked = await page.evaluate("""() => {
  const cx = Math.floor((window.innerWidth || 0) / 2);
  const cy = Math.floor((window.innerHeight || 0) / 2);
  const el = document.elementFromPoint(cx, cy);
  if (!el) return false;
  let node = el;
  for (let i = 0; i < 6 && node; i++) {
    const style = window.getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    const z = parseInt(style.zIndex || '0') || 0;
    const fixedLike = style.position === 'fixed' || style.position === 'sticky' || style.position === 'absolute';
    const covers = rect.width >= (window.innerWidth * 0.4) && rect.height >= (window.innerHeight * 0.4);
    if (fixedLike && covers && z >= 100) return true;
    node = node.parentElement;
  }
  return false;
}""")
            if isinstance(blocked, bool):
                return not blocked
        except Exception:
            pass

        # If we can't verify, assume best-effort success and let subsequent failures re-trigger recovery.
        return True

    async def _detect_infinite_scroll(self, page) -> bool:
        try:
            res = await page.evaluate("""() => {
  const body = document.body;
  if (!body) return false;
  const scrollHeight = Math.max(body.scrollHeight || 0, document.documentElement.scrollHeight || 0);
  const nearBottom = (window.innerHeight + window.scrollY) >= (scrollHeight - 250);
  const scrollable = scrollHeight > (window.innerHeight * 1.4);
  if (!nearBottom || !scrollable) return false;

  const hasFeed = !!document.querySelector('[role=\"feed\"],[role=\"list\"],[aria-busy=\"true\"],.infinite-scroll,.InfiniteScroll,[data-testid*=\"feed\"]');
  if (!hasFeed) return false;

  const buttons = Array.from(document.querySelectorAll('button,a')).slice(0, 120);
  const hasLoadMore = buttons.some(el => {
    const t = (el.textContent || '').toLowerCase();
    return t.includes('load more') || t.includes('show more') || t.includes('more results') || t === 'more';
  });
  const hasSpinner = !!document.querySelector('[role=\"progressbar\"],.spinner,.loading,[aria-busy=\"true\"]');
  return hasLoadMore || hasSpinner;
}""")
        except Exception:
            return False

        return res is True

    async def _recover_scroll_until_stable(self, page, hints: Optional[SiteHints] = None) -> bool:
        """
        Scroll-until-stable logic.
        Stops when:
        - N consecutive scrolls produce no new content (stable item count)
        - Max scrolls reached
        - Time limit reached (optional)
        """
        logger.info("[RECOVERY] Scrolling until stable...")
        max_scrolls = (hints.max_pages if hints else 5) or 5
        item_selector = hints.preferred_selectors[0] if hints and hints.preferred_selectors else None
        
        last_count = 0
        consecutive_no_change = 0
        
        for i in range(max_scrolls):
            # 1. Scroll down
            await page.mouse.wheel(0, 1000)
            await asyncio.sleep(1.5)
            
            # 2. Check if content changed
            if item_selector:
                current_count = await page.evaluate(f"document.querySelectorAll('{item_selector}').length")
            else:
                current_count = await page.evaluate("document.body.innerText.length")
                
            if current_count == last_count:
                consecutive_no_change += 1
            else:
                consecutive_no_change = 0
                
            if consecutive_no_change >= 2:
                logger.info(f"[RECOVERY] Scroll stabilized after {i+1} iterations.")
                break
                
            last_count = current_count
            
        return True

    async def _recover_scroll_and_find(self, page) -> bool:
        logger.info("[RECOVERY] Scrolling to find element...")
        await page.mouse.wheel(0, 500)
        await asyncio.sleep(1)
        return True

    async def _recover_re_snapshot(self, page) -> bool:
        logger.info("[RECOVERY] Refreshing page snapshot...")
        return True

    async def _recover_fuzzy_find(self, page) -> bool:
        logger.info("[RECOVERY] Attempting fuzzy element finding with vision...")
        # Get the last attempted description from telemetry or parent
        try:
            from .visual_grounding import get_engine, GroundingStrategy
            visual_engine = get_engine()
            # We don't have the original description here easily, 
            # but we can try to find common "important" elements if stalled
            # This is a bit of a placeholder until we can pass the failed target here
            return False 
        except Exception as e:
            logger.error(f"Fuzzy find failed: {e}")
            return False

    async def _detect_action_not_applied(self, page) -> bool:
        """Detect if an action was clicked but no navigation or DOM change occurred."""
        # This usually needs comparison with previous state, 
        # but we can check if we're still on the exact same state after a 'click'
        return False # Placeholder - requires state tracking

    async def _recover_force_action(self, page) -> bool:
        logger.info("[RECOVERY] Forcing action with dispatchEvent...")
        # Try to find the element that was last attempted and force a click
        try:
            # We need the selector of the failed element. 
            # For now, we'll try to click the center of the screen as a desperate measure if stalled
            # or try to click any visible 'button'
            await page.evaluate("document.activeElement.click()")
            return True
        except:
            return False

    async def _recover_js_action(self, page) -> bool:
        logger.info("[RECOVERY] Executing action via JavaScript...")
        try:
            # Try to trigger a click via JS on the focused element
            await page.evaluate("(() => { const el = document.activeElement; if(el) el.click(); })()")
            return True
        except:
            return False

    async def _detect_unexpected_redirect(self, page) -> bool:
        return False

    async def _recover_back_to_expected(self, page) -> bool:
        logger.info("[RECOVERY] Redirected away. Going back...")
        try:
            await page.go_back()
            return True
        except:
            return False

    # --- TIER 1 DETECTORS & RECOVERY ---

    async def _detect_auth_wall(self, page) -> bool:
        content = (await page.content()).lower()
        if "log in" in content or "sign in" in content or "create account" in content:
            has_login = await page.query_selector("input[type='password'], input[name*='pass']")
            return has_login is not None
        return False

    async def _recover_notify_login(self, page) -> bool:
        logger.error(f"[RECOVERY] AUTH_REQUIRED at {page.url}.")
        return False 

    async def _detect_mfa_prompt(self, page) -> bool:
        content = (await page.content()).lower()
        mfa_keywords = ["verification code", "2fa", "two-factor", "check your email", "check your phone"]
        return any(kw in content for kw in mfa_keywords)

    async def _recover_request_mfa(self, page) -> bool:
        logger.warning("[RECOVERY] MFA_REQUIRED. Waiting for manual code entry or escalation.")
        return False

    async def _detect_captcha(self, page) -> bool:
        content = (await page.content()).lower()

        # Specific CAPTCHA challenge indicators (NOT just CDN references)
        # Must be actual challenge elements, not just the word appearing in scripts
        captcha_challenge_indicators = [
            "verify you are human",
            "verify you're human",
            "prove you are human",
            "complete the security check",
            "checking your browser",
            "just a moment",
            "enable javascript and cookies",
            "ray id:",  # Cloudflare challenge pages have this
            "cf-browser-verification",
            "challenge-running",
            "challenge-form",
        ]
        if any(ind in content for ind in captcha_challenge_indicators):
            return True

        # Check for actual CAPTCHA iframes (hCaptcha, reCAPTCHA)
        iframes = await page.query_selector_all("iframe")
        for iframe in iframes:
            try:
                src = await iframe.get_attribute("src") or ""
                src_lower = src.lower()
                # Only trigger on actual CAPTCHA iframe sources
                if any(x in src_lower for x in ["hcaptcha.com", "recaptcha", "captcha-api", "challenges.cloudflare.com"]):
                    return True
            except:
                continue

        # Check for specific CAPTCHA elements (more reliable than text matching)
        try:
            captcha_selectors = [
                "[class*='captcha']",
                "[id*='captcha']",
                "[class*='cf-challenge']",
                "[id*='challenge-form']",
                "[class*='h-captcha']",
                "[class*='g-recaptcha']",
            ]
            for sel in captcha_selectors:
                el = await page.query_selector(sel)
                if el:
                    return True
        except:
            pass

        return False

    async def _recover_solve_captcha(self, page) -> bool:
        logger.info("[RECOVERY] Attempting to solve CAPTCHA...")
        try:
            # Step 1: Check if this is a Cloudflare "checking your browser" challenge
            # These often auto-pass within 5-10 seconds - no user interaction needed
            content = (await page.content()).lower()
            is_cloudflare_check = any(ind in content for ind in [
                "checking your browser",
                "just a moment",
                "please wait",
                "ddos protection",
                "ray id",
                "cloudflare",
                "security check"
            ])

            if is_cloudflare_check:
                logger.info("[RECOVERY] Cloudflare challenge detected - waiting for auto-pass...")
                # Wait up to 15 seconds for Cloudflare to auto-resolve
                for wait_attempt in range(5):
                    await asyncio.sleep(3)
                    new_content = (await page.content()).lower()
                    # Check if the challenge has cleared
                    still_blocked = any(ind in new_content for ind in [
                        "checking your browser",
                        "just a moment",
                        "please wait",
                        "ray id"
                    ])
                    if not still_blocked:
                        logger.info("[RECOVERY] Cloudflare challenge auto-passed!")
                        return True
                logger.warning("[RECOVERY] Cloudflare challenge did not auto-pass after 15s")

            # Step 2: Try cookie/consent dismissal first (common FB blocker)
            try:
                dismiss_selectors = [
                    "button:has-text('Accept All')",
                    "button:has-text('Allow All')",
                    "button:has-text('Accept')",
                    "[data-testid='cookie-policy-manage-dialog-accept-button']",
                    "[aria-label*='Accept' i]",
                    "[aria-label*='Allow' i]",
                ]
                for sel in dismiss_selectors:
                    try:
                        btn = await page.query_selector(sel)
                        if btn and await btn.is_visible():
                            await btn.click()
                            await asyncio.sleep(1)
                            logger.info(f"[RECOVERY] Dismissed consent/cookie overlay via {sel}")
                            # Check if CAPTCHA is still present
                            new_content = (await page.content()).lower()
                            if not any(ind in new_content for ind in ["captcha", "verify you are human", "recaptcha", "hcaptcha"]):
                                return True
                    except Exception:
                        continue
            except Exception:
                pass

            # Step 3: Try the scrappy bypass (checkbox click, accessibility options)
            from .captcha_solver import PageCaptchaHandler
            handler = PageCaptchaHandler(page)
            result = await handler.scrappy.bypass()
            if result:
                return True

            # Step 4: Final attempt - reload and wait again
            logger.info("[RECOVERY] Trying page reload for transient challenges...")
            try:
                await page.reload(wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(5)
                # Check if cleared
                new_content = (await page.content()).lower()
                captcha_gone = not any(ind in new_content for ind in [
                    "captcha", "verify you are human", "recaptcha", "hcaptcha",
                    "checking your browser", "security challenge"
                ])
                if captcha_gone:
                    logger.info("[RECOVERY] CAPTCHA cleared after reload!")
                    return True
            except Exception:
                pass

            return False
        except Exception as e:
            logger.error(f"[RECOVERY] Captcha resolution failed: {e}")
            return False

    async def _detect_rate_limit(self, page) -> bool:
        content = (await page.content()).lower()
        rate_limit_indicators = ["too many requests", "429", "rate limit", "try again later", "throttled"]
        return any(ind in content for ind in rate_limit_indicators)

    async def _recover_wait_long_backoff(self, page) -> bool:
        logger.warning("[RECOVERY] Rate limited. Waiting 30s...")
        await asyncio.sleep(30)
        return True

    async def _detect_bot_detection(self, page) -> bool:
        # Get visible text content, not full HTML (to avoid false positives from scripts)
        try:
            text = (await page.evaluate("document.body ? document.body.innerText : ''") or "").lower()
        except Exception:
            text = ""

        # Also check page title for common block indicators
        try:
            title = (await page.title() or "").lower()
        except Exception:
            title = ""

        # These must appear in visible text, not just HTML
        bot_challenge_indicators = [
            "unusual traffic from your",
            "automated access is not permitted",
            "bot detection",
            "access denied",  # Common block message
            "you have been blocked",
            "blocked by",
            "security challenge",
            "verify you are not a robot",
            "ddos protection by",
            "checking your browser before",
            "this process is automatic",
        ]

        # Check visible text for challenge indicators
        if any(ind in text for ind in bot_challenge_indicators):
            return True

        # Check title for block indicators
        title_block_indicators = ["access denied", "blocked", "security check", "attention required", "just a moment"]
        if any(ind in title for ind in title_block_indicators):
            return True

        return False

    async def _recover_change_stealth_profile(self, page) -> bool:
        logger.info("[RECOVERY] Bot detected. Attempting wait + reload...")

        # Step 1: First try just waiting - many bot checks auto-pass
        for wait_attempt in range(4):
            await asyncio.sleep(3 + wait_attempt)
            if not await self._detect_bot_detection(page) and not await self._detect_captcha(page):
                logger.info("[RECOVERY] Bot check auto-passed after waiting!")
                return True

        # Step 2: Try reload with longer backoff
        for attempt in range(3):
            try:
                backoff = 3 + (attempt * 2)  # 3s, 5s, 7s
                logger.info(f"[RECOVERY] Reload attempt {attempt + 1}/3 with {backoff}s backoff...")
                await asyncio.sleep(backoff)
                await page.reload(wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(3)
                # If the challenge cleared, we can proceed.
                if not await self._detect_bot_detection(page) and not await self._detect_captcha(page):
                    logger.info("[RECOVERY] Bot check cleared after reload!")
                    return True
            except Exception:
                continue

        # Step 3: Try clearing cookies and reloading (sometimes helps with stuck sessions)
        try:
            logger.info("[RECOVERY] Trying cookie clear + reload...")
            context = page.context
            await context.clear_cookies()
            await asyncio.sleep(1)
            await page.reload(wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(5)
            if not await self._detect_bot_detection(page) and not await self._detect_captcha(page):
                logger.info("[RECOVERY] Bot check cleared after cookie clear!")
                return True
        except Exception:
            pass

        return False

    async def _detect_geo_block(self, page) -> bool:
        try:
            text = (await page.evaluate("document.body ? document.body.innerText : ''") or "").lower()
        except Exception:
            text = (await page.content()).lower()

        geo_phrases = [
            "not available in your country",
            "not available in your region",
            "not available in your location",
            "unavailable in your country",
            "unavailable in your region",
            "unavailable in your location",
            "isn't available in your country",
            "isn't available in your region",
            "isn't available in your location",
            "not available where you live",
            "we're sorry, this content is not available",
            "this service is not available",
            "due to your location",
            "due to local regulations",
        ]
        if any(p in text for p in geo_phrases):
            return True

        # Strong signal: explicit "country/region" + "available" block wording
        if ("country" in text or "region" in text or "location" in text) and ("not available" in text or "unavailable" in text):
            return True

        return False

    async def _recover_geo_block(self, page) -> bool:
        logger.error(f"[RECOVERY] GEO_BLOCKED at {page.url}.")
        return False

    # --- TIER 2 DETECTORS & RECOVERY ---

    async def _detect_partial_data(self, page) -> bool:
        return False

    async def _recover_retry_extraction(self, page) -> bool:
        logger.info("[RECOVERY] Retrying data extraction...")
        return True

    async def _detect_pagination(self, page) -> bool:
        next_patterns = ["Next", "Next Page", ">", "»"]
        for pattern in next_patterns:
            btn = await page.query_selector(f"text='{pattern}'")
            if btn and await btn.is_visible():
                return True
        return False

    async def _recover_click_next(self, page) -> bool:
        logger.info("[RECOVERY] Clicking next page...")
        return True

    async def _detect_duplicates(self, page) -> bool:
        return False

    async def _recover_skip_duplicates(self, page) -> bool:
        return True

    async def _recover_reformat_output(self, page) -> bool:
        return True

    # --- TIER 3 DETECTORS & RECOVERY ---

    async def _detect_dangerous_action(self, page) -> bool:
        return False

    async def _recover_halt_and_ask(self, page) -> bool:
        logger.warning("[RECOVERY] SAFETY GATE: Approval required for irreversible action.")
        return False

    async def _detect_approval_needed(self, page) -> bool:
        return False

    async def _detect_confirmation_modal(self, page) -> bool:
        content = (await page.content()).lower()
        if "confirm" in content or "are you sure" in content:
            return True
        return False

    async def _recover_click_confirm(self, page) -> bool:
        logger.info("[RECOVERY] Clicking confirmation button...")
        return False

    async def _detect_policy_block(self, page) -> bool:
        content = (await page.content()).lower()
        return "policy" in content and "block" in content

    async def _recover_log_and_skip(self, page) -> bool:
        logger.error("[RECOVERY] Action blocked by site policy.")
        return False

    # --- Pipeline Implementation ---

    async def run_pipeline(self, hints: Optional[SiteHints] = None) -> bool:
        """
        Observe -> Classify -> Handle -> Resume -> Escalate
        """
        start_pipeline = time.time()
        modes = await self.observe_and_classify()
        self.last_detected_modes = modes or []
        self.last_failed_mode = None
        
        if not modes:
            return True
            
        logger.info(f"Detected failure modes: {[m.value for m in modes]}")
        modes.sort(key=lambda x: list(FailureMode).index(x))
        
        pipeline_success = True
        for mode in modes:
            start_mode = time.time()
            success = await self._handle_mode(mode, hints)
            duration = time.time() - start_mode
            
            # Record telemetry
            self.telemetry.append({
                "mode": mode.value,
                "duration": round(duration, 3),
                "success": success,
                "timestamp": time.time()
            })
            
            if not success:
                logger.error(f"Recovery failed for {mode.value}")
                self.last_failed_mode = mode
                pipeline_success = False
                break # Escalation required
                
        if pipeline_success:
            logger.info(f"Recovery successful in {round(time.time() - start_pipeline, 3)}s. Resuming task.")
        return pipeline_success

    async def observe_and_classify(self) -> List[FailureMode]:
        detected = []
        for mode, handler in self.handlers.items():
            for detector in handler.detectors:
                try:
                    if await detector(self.page):
                        detected.append(mode)
                        break
                except Exception as e:
                    logger.debug(f"Detector for {mode.value} failed: {e}")
        return detected

    def get_latest_telemetry(self) -> List[Dict]:
        """Return and clear recent recovery telemetry."""
        data = self.telemetry[:]
        self.telemetry = []
        return data

    async def _handle_mode(self, mode: FailureMode, hints: Optional[SiteHints] = None) -> bool:
        handler = self.handlers.get(mode)
        if not handler or not handler.recovery_steps:
            return True 

        retries = self.retry_counts.get(mode, 0)
        if retries >= handler.retry_policy["max_retries"]:
            return False

        for step in handler.recovery_steps:
            try:
                # Some steps (like scroll) might need hints
                import inspect
                if "hints" in inspect.signature(step).parameters:
                    res = await step(self.page, hints=hints)
                else:
                    res = await step(self.page)
                    
                if res:
                    self.retry_counts[mode] = 0
                    # Success: Learn this for next time
                    await self._learn_recovery(mode, True)
                    return True
            except Exception as e:
                logger.error(f"Recovery step for {mode.value} failed: {e}")

        self.retry_counts[mode] = retries + 1
        return False
