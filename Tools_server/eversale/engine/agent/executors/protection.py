"""
Protection Executors - CAPTCHA, Cloudflare, and Stealth Mode

P1: CAPTCHA Solver - Detect and solve CAPTCHAs using vision models
P2: Cloudflare Handler - Bypass Cloudflare challenges or find alternatives
P3: Stealth Mode - Enable enhanced anti-detection browser configuration
"""

from typing import Dict, Any
from loguru import logger
from .base import BaseExecutor, ActionResult, ActionStatus


class P1_CaptchaSolver(BaseExecutor):
    """P1 - Solve CAPTCHA challenges using local vision models."""

    capability = "P1"
    action = "solve_captcha"
    required_params = []
    optional_params = ["page_url", "captcha_type"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        """
        Detect and solve CAPTCHA challenges on the current page.

        Uses local vision models (moondream, llama3.2-vision) to solve CAPTCHAs
        without paid API services.
        """
        try:
            from ..captcha_solver import LocalCaptchaSolver, ChallengeHandler

            logger.info("[P1] Initializing CAPTCHA solver")

            # Initialize solver and handler
            captcha_solver = LocalCaptchaSolver(vision_model="moondream")
            challenge_handler = ChallengeHandler(
                page=self.browser.page if self.browser else None,
                solver=captcha_solver
            )

            # Detect CAPTCHA on current page
            logger.info("[P1] Detecting CAPTCHA on page")
            detection = await challenge_handler.detect_challenge()

            if not detection.detected:
                return ActionResult(
                    status=ActionStatus.SUCCESS,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    message="No CAPTCHA detected on current page",
                    data={"captcha_detected": False}
                )

            logger.info(f"[P1] CAPTCHA detected: {detection.challenge_type.value}")

            # Attempt to solve
            solve_result = await challenge_handler.handle_challenge()

            if solve_result["status"] == "solved":
                return ActionResult(
                    status=ActionStatus.SUCCESS,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    message=f"CAPTCHA solved successfully: {detection.challenge_type.value}",
                    data={
                        "captcha_detected": True,
                        "captcha_type": detection.challenge_type.value,
                        "solved": True,
                        "method": solve_result.get("method", "vision"),
                        "confidence": solve_result.get("confidence", 0.0)
                    }
                )
            else:
                return ActionResult(
                    status=ActionStatus.PARTIAL,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    message=f"CAPTCHA detected but not solved: {solve_result.get('message')}",
                    data={
                        "captcha_detected": True,
                        "captcha_type": detection.challenge_type.value,
                        "solved": False,
                        "reason": solve_result.get("message")
                    }
                )

        except Exception as e:
            logger.error(f"[P1] CAPTCHA solver failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                error=str(e),
                message=f"CAPTCHA solver error: {str(e)}"
            )


class P2_CloudflareHandler(BaseExecutor):
    """P2 - Handle Cloudflare challenges and blocks."""

    capability = "P2"
    action = "handle_cloudflare"
    required_params = []
    optional_params = ["site_url", "find_alternative"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        """
        Handle Cloudflare challenges by:
        1. Waiting for JS challenge auto-completion
        2. Using stealth mode refresh
        3. Finding alternative data sources
        """
        try:
            from ..challenge_handler import CloudflareChallengeHandler
            import asyncio

            logger.info("[P2] Initializing Cloudflare challenge handler")

            if not self.browser or not self.browser.page:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    error="No browser page available",
                    message="Cannot handle Cloudflare without active browser page"
                )

            page = self.browser.page
            handler = CloudflareChallengeHandler(page=page)

            # Check if Cloudflare is actually blocking
            is_blocked = await handler.is_cloudflare_challenge()

            if not is_blocked:
                return ActionResult(
                    status=ActionStatus.SUCCESS,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    message="No Cloudflare challenge detected",
                    data={"cloudflare_detected": False}
                )

            logger.info("[P2] Cloudflare challenge detected, attempting bypass")

            # Try auto-completion first (wait for JS challenge)
            logger.info("[P2] Waiting for Cloudflare JS challenge to auto-complete (15s)")
            await asyncio.sleep(15)

            # Check if resolved
            is_still_blocked = await handler.is_cloudflare_challenge()

            if not is_still_blocked:
                return ActionResult(
                    status=ActionStatus.SUCCESS,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    message="Cloudflare challenge auto-completed successfully",
                    data={
                        "cloudflare_detected": True,
                        "bypassed": True,
                        "method": "auto_completion"
                    }
                )

            # If still blocked, try stealth refresh
            logger.info("[P2] Still blocked, attempting stealth mode refresh")
            result = await handler.handle_challenge()

            if result["bypassed"]:
                return ActionResult(
                    status=ActionStatus.SUCCESS,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    message="Cloudflare challenge bypassed with stealth mode",
                    data={
                        "cloudflare_detected": True,
                        "bypassed": True,
                        "method": result.get("method", "stealth_refresh")
                    }
                )
            else:
                # Suggest alternatives
                alternatives = result.get("alternatives", [])
                return ActionResult(
                    status=ActionStatus.PARTIAL,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    message=f"Cloudflare block persists. {len(alternatives)} alternative sources available.",
                    data={
                        "cloudflare_detected": True,
                        "bypassed": False,
                        "alternatives": alternatives
                    },
                    next_actions=["try_alternative_source"] if alternatives else []
                )

        except Exception as e:
            logger.error(f"[P2] Cloudflare handler failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                error=str(e),
                message=f"Cloudflare handler error: {str(e)}"
            )


class P3_StealthMode(BaseExecutor):
    """P3 - Enable enhanced stealth browser configuration."""

    capability = "P3"
    action = "enable_stealth"
    required_params = []
    optional_params = ["persistent", "fingerprint_randomization"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        """
        Enable stealth mode for anti-bot detection avoidance.

        Applies MCP-compatible launch args, headers, and fingerprint randomization.
        """
        try:
            from ..stealth_browser_config import (
                get_mcp_compatible_launch_args,
                get_stealth_context_options,
                get_undetectable_headers
            )

            logger.info("[P3] Enabling stealth mode configuration")

            if not self.browser:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    error="No browser instance available",
                    message="Cannot enable stealth mode without browser instance"
                )

            # Get stealth configuration
            launch_args = get_mcp_compatible_launch_args()
            headers = get_undetectable_headers()
            context_options = get_stealth_context_options()

            # Apply to current context if available
            if hasattr(self.browser, 'page') and self.browser.page:
                page = self.browser.page

                # Set extra headers
                await page.set_extra_http_headers(headers)
                logger.info("[P3] Applied stealth headers to current page")

                # Note: Launch args and context options require browser restart
                # Store in context for next browser initialization
                if not hasattr(self.browser, '_stealth_enabled'):
                    self.browser._stealth_enabled = True
                    self.browser._stealth_launch_args = launch_args
                    self.browser._stealth_context_options = context_options

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                message="Stealth mode enabled. Headers applied. Full stealth on next browser restart.",
                data={
                    "stealth_enabled": True,
                    "headers_applied": True,
                    "launch_args_count": len(launch_args),
                    "restart_required": True,
                    "features": [
                        "MCP-compatible launch args",
                        "Anti-detection headers",
                        "Fingerprint randomization",
                        "WebGL/Canvas consistency",
                        "TLS fingerprinting"
                    ]
                }
            )

        except Exception as e:
            logger.error(f"[P3] Stealth mode enablement failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                error=str(e),
                message=f"Stealth mode error: {str(e)}"
            )


# Registry of protection executors
PROTECTION_EXECUTORS = {
    "P1": P1_CaptchaSolver,
    "P2": P2_CloudflareHandler,
    "P3": P3_StealthMode,
}


def get_protection_executor(capability: str) -> BaseExecutor:
    """Get a protection executor by capability ID."""
    return PROTECTION_EXECUTORS.get(capability)
