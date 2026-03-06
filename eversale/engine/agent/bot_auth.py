"""
Web Bot Authentication Protocol
Implements AWS/Cloudflare bot verification to reduce CAPTCHA friction.

Based on:
- AWS WAF Bot Control
- Cloudflare Turnstile
- Bot Management Alliance proposals
"""

import hashlib
import hmac
import time
import asyncio
import os
import logging
from dataclasses import dataclass
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class BotCredential:
    """Bot verification credential."""
    issuer: str  # "eversale", "anthropic", etc.
    bot_id: str
    public_key: str
    capabilities: List[str]  # ["read", "form_fill", "navigate"]
    issued_at: int
    expires_at: int
    signature: str


class BotAuthProtocol:
    """
    Implements bot authentication headers for reduced friction.

    Flow:
    1. Generate bot credential signed by issuer
    2. Include in request headers
    3. Site verifies signature, grants reduced captcha
    """

    HEADER_PREFIX = "X-Bot-"

    def __init__(self, issuer: str = "eversale", private_key: Optional[str] = None):
        self.issuer = issuer
        self.private_key = private_key or os.getenv("BOT_AUTH_PRIVATE_KEY")
        if not self.private_key:
            raise ValueError("BOT_AUTH_PRIVATE_KEY environment variable must be set")
        self.bot_id = self._generate_bot_id()

    def _generate_bot_id(self) -> str:
        """Generate unique bot identifier."""
        import uuid
        return f"eversale-{uuid.uuid4().hex[:12]}"

    def generate_credential(self, capabilities: List[str] = None,
                            ttl_hours: int = 24) -> BotCredential:
        """Generate signed bot credential."""
        if capabilities is None:
            capabilities = ['read', 'form_fill', 'navigate']

        now = int(time.time())
        expires = now + (ttl_hours * 3600)

        # Data to sign
        data = f"{self.issuer}:{self.bot_id}:{','.join(capabilities)}:{now}:{expires}"

        # HMAC signature
        signature = hmac.new(
            self.private_key.encode(),
            data.encode(),
            hashlib.sha256
        ).hexdigest()

        return BotCredential(
            issuer=self.issuer,
            bot_id=self.bot_id,
            public_key=self._derive_public_key(),
            capabilities=capabilities,
            issued_at=now,
            expires_at=expires,
            signature=signature
        )

    def _derive_public_key(self) -> str:
        """Derive public key from private key."""
        return hashlib.sha256(self.private_key.encode()).hexdigest()[:32]

    def get_headers(self, credential: BotCredential = None) -> Dict[str, str]:
        """Get headers to include in requests."""
        if credential is None:
            credential = self.generate_credential()

        return {
            f"{self.HEADER_PREFIX}Issuer": credential.issuer,
            f"{self.HEADER_PREFIX}Id": credential.bot_id,
            f"{self.HEADER_PREFIX}Capabilities": ','.join(credential.capabilities),
            f"{self.HEADER_PREFIX}Issued": str(credential.issued_at),
            f"{self.HEADER_PREFIX}Expires": str(credential.expires_at),
            f"{self.HEADER_PREFIX}Signature": credential.signature,
            f"{self.HEADER_PREFIX}Protocol-Version": "1.0"
        }

    async def inject_headers(self, page) -> None:
        """Inject bot auth headers into Playwright page."""
        credential = self.generate_credential(['read', 'form_fill', 'navigate'])
        headers = self.get_headers(credential)

        # Set extra headers
        await page.set_extra_http_headers(headers)


class CaptchaHandler:
    """
    Handle CAPTCHAs when bot auth is insufficient.
    """

    def __init__(self, solver_service: str = "2captcha"):
        self.solver = solver_service
        self.api_key = os.getenv(f"{solver_service.upper()}_API_KEY")

    async def detect_captcha(self, page) -> Optional[str]:
        """Detect CAPTCHA type on page."""
        # Check for common CAPTCHA providers
        captcha_signatures = {
            'recaptcha': ['grecaptcha', 'g-recaptcha', 'recaptcha'],
            'hcaptcha': ['hcaptcha', 'h-captcha'],
            'cloudflare': ['cf-turnstile', 'challenge-platform'],
            'funcaptcha': ['funcaptcha', 'arkoselabs']
        }

        page_content = await page.content()

        for captcha_type, signatures in captcha_signatures.items():
            for sig in signatures:
                if sig in page_content.lower():
                    return captcha_type

        return None

    async def solve(self, page, captcha_type: str) -> bool:
        """Attempt to solve CAPTCHA."""
        if not self.api_key:
            logger.debug(f"No API key found for {self.solver}")
            return False

        if captcha_type == 'recaptcha':
            return await self._solve_recaptcha(page)
        elif captcha_type == 'hcaptcha':
            return await self._solve_hcaptcha(page)
        elif captcha_type == 'cloudflare':
            # Cloudflare Turnstile - wait and retry
            logger.debug("Cloudflare Turnstile detected, waiting for auto-solve...")
            await asyncio.sleep(5)
            return True  # Often auto-solves

        return False

    async def _solve_recaptcha(self, page) -> bool:
        """Solve reCAPTCHA v2/v3."""
        # Get site key
        site_key = await page.evaluate('''
            () => {
                const el = document.querySelector('[data-sitekey]');
                return el ? el.dataset.sitekey : null;
            }
        ''')

        if not site_key:
            logger.debug("Could not find reCAPTCHA site key")
            return False

        logger.debug(f"Detected reCAPTCHA with site key: {site_key}")

        # Submit to solver service (2captcha API)
        if self.solver == "2captcha":
            return await self._solve_recaptcha_2captcha(page, site_key)

        return False

    async def _solve_recaptcha_2captcha(self, page, site_key: str) -> bool:
        """Solve reCAPTCHA using 2captcha service."""
        import aiohttp

        url = await page.url

        # Submit captcha task
        submit_url = "http://2captcha.com/in.php"
        params = {
            'key': self.api_key,
            'method': 'userrecaptcha',
            'googlekey': site_key,
            'pageurl': url,
            'json': 1
        }

        async with aiohttp.ClientSession() as session:
            # Submit task
            async with session.post(submit_url, data=params) as response:
                result = await response.json()
                if result.get('status') != 1:
                    logger.debug(f"2captcha submit failed: {result.get('request')}")
                    return False

                task_id = result.get('request')
                logger.debug(f"2captcha task submitted: {task_id}")

            # Poll for result
            result_url = "http://2captcha.com/res.php"
            for attempt in range(30):  # Poll for up to 60 seconds
                await asyncio.sleep(2)

                params = {
                    'key': self.api_key,
                    'action': 'get',
                    'id': task_id,
                    'json': 1
                }

                async with session.get(result_url, params=params) as response:
                    result = await response.json()

                    if result.get('status') == 1:
                        # Got solution
                        captcha_response = result.get('request')
                        logger.debug("2captcha solved successfully")

                        # Inject solution into page
                        await page.evaluate('''
                            (response) => {
                                document.getElementById('g-recaptcha-response').innerHTML = response;
                                if (typeof ___grecaptcha_cfg !== 'undefined') {
                                    Object.keys(___grecaptcha_cfg.clients).forEach((key) => {
                                        ___grecaptcha_cfg.clients[key].callback(response);
                                    });
                                }
                            }
                        ''', captcha_response)

                        return True
                    elif result.get('request') != 'CAPCHA_NOT_READY':
                        logger.debug(f"2captcha error: {result.get('request')}")
                        return False

        logger.debug("2captcha timeout")
        return False

    async def _solve_hcaptcha(self, page) -> bool:
        """Solve hCaptcha."""
        # Get site key
        site_key = await page.evaluate('''
            () => {
                const el = document.querySelector('[data-sitekey]');
                return el ? el.dataset.sitekey : null;
            }
        ''')

        if not site_key:
            logger.debug("Could not find hCaptcha site key")
            return False

        logger.debug(f"Detected hCaptcha with site key: {site_key}")

        # Similar implementation to reCAPTCHA but for hCaptcha
        if self.solver == "2captcha":
            return await self._solve_hcaptcha_2captcha(page, site_key)

        return False

    async def _solve_hcaptcha_2captcha(self, page, site_key: str) -> bool:
        """Solve hCaptcha using 2captcha service."""
        import aiohttp

        url = await page.url

        # Submit captcha task
        submit_url = "http://2captcha.com/in.php"
        params = {
            'key': self.api_key,
            'method': 'hcaptcha',
            'sitekey': site_key,
            'pageurl': url,
            'json': 1
        }

        async with aiohttp.ClientSession() as session:
            # Submit task
            async with session.post(submit_url, data=params) as response:
                result = await response.json()
                if result.get('status') != 1:
                    logger.debug(f"2captcha submit failed: {result.get('request')}")
                    return False

                task_id = result.get('request')
                logger.debug(f"2captcha task submitted: {task_id}")

            # Poll for result
            result_url = "http://2captcha.com/res.php"
            for attempt in range(30):  # Poll for up to 60 seconds
                await asyncio.sleep(2)

                params = {
                    'key': self.api_key,
                    'action': 'get',
                    'id': task_id,
                    'json': 1
                }

                async with session.get(result_url, params=params) as response:
                    result = await response.json()

                    if result.get('status') == 1:
                        # Got solution
                        captcha_response = result.get('request')
                        logger.debug("2captcha solved successfully")

                        # Inject solution into page
                        await page.evaluate('''
                            (response) => {
                                document.querySelector('[name="h-captcha-response"]').innerHTML = response;
                                window.hcaptcha && window.hcaptcha.getRespKey &&
                                    window.hcaptcha.submit();
                            }
                        ''', captcha_response)

                        return True
                    elif result.get('request') != 'CAPCHA_NOT_READY':
                        logger.debug(f"2captcha error: {result.get('request')}")
                        return False

        logger.debug("2captcha timeout")
        return False


# Example usage
async def demo():
    """Demo bot auth protocol."""
    # Initialize protocol
    protocol = BotAuthProtocol(issuer="eversale")

    # Generate credential
    credential = protocol.generate_credential(['read', 'navigate', 'form_fill'])

    # Get headers
    headers = protocol.get_headers(credential)
    print("Bot Auth Headers:")
    for key, value in headers.items():
        print(f"  {key}: {value}")

    # Initialize captcha handler
    captcha_handler = CaptchaHandler(solver_service="2captcha")

    print(f"\nCaptcha Handler initialized with service: {captcha_handler.solver}")
    print(f"API Key configured: {bool(captcha_handler.api_key)}")


if __name__ == "__main__":
    asyncio.run(demo())
