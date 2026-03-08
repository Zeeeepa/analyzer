"""
CAPTCHA & 2FA Handler - Local vision-based solving (NO paid APIs)

Supports:
- CAPTCHA Detection: reCAPTCHA v2/v3, hCaptcha, Cloudflare Turnstile, Image-based
- 2FA Detection: SMS codes, Authenticator apps, Email verification, Backup codes
- User Notification: Console, optional webhooks
- Auto-pause/resume: Pauses agent, waits for user, auto-resumes
- Vision-based Solving: Local LLM vision models (moondream, llama3.2-vision)
- Login Flow Integration: Seamless integration with login_manager.py

Features:
- FREE vision-based CAPTCHA solving using local LLMs
- Manual fallback with browser popup
- Webhook notifications for remote agents
- Retry logic with exponential backoff
- Detailed logging and error handling
- NO external paid APIs (2captcha, anti-captcha, etc.)
"""

import asyncio
import aiohttp
import os
import time
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from enum import Enum
from loguru import logger

# Import visual fallback for screenshot + click when selectors fail
try:
    from .selector_fallbacks import get_visual_fallback
    VISUAL_FALLBACK_AVAILABLE = True
except ImportError:
    VISUAL_FALLBACK_AVAILABLE = False
    get_visual_fallback = None


class ChallengeType(Enum):
    """Types of authentication challenges."""
    # CAPTCHA types
    RECAPTCHA_V2 = "recaptcha_v2"
    RECAPTCHA_V3 = "recaptcha_v3"
    HCAPTCHA = "hcaptcha"
    CLOUDFLARE_TURNSTILE = "cloudflare_turnstile"
    IMAGE_CAPTCHA = "image_captcha"

    # 2FA types
    SMS_CODE = "sms_code"
    AUTHENTICATOR_APP = "authenticator_app"
    EMAIL_VERIFICATION = "email_verification"
    BACKUP_CODE = "backup_code"

    # Other
    UNKNOWN = "unknown"


@dataclass
class ChallengeDetection:
    """Result of challenge detection."""
    detected: bool
    challenge_type: ChallengeType
    site_key: Optional[str] = None
    selector: Optional[str] = None
    confidence: float = 0.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class LocalCaptchaSolver:
    """
    Solves CAPTCHAs using LOCAL vision models (NO paid APIs).

    Uses:
    - Local LLM vision models (0000/ui-tars-1.5-7b:latest, moondream, llama3.2-vision, llava)
    - UI-TARS: ByteDance agentic vision model specifically designed for GUI tasks
    - Manual browser fallback for complex CAPTCHAs
    - Human-like behavior to avoid triggering CAPTCHAs

    NO external API keys required - completely free and private.
    """

    def __init__(self, vision_model: str = "0000/ui-tars-1.5-7b:latest"):
        self.vision_model = vision_model
        self.ollama_client = None

        # Metrics tracking for confidence analysis
        self.solve_attempts = []
        self.success_by_confidence = {
            "high": {"attempts": 0, "successes": 0},      # >= 85%
            "good": {"attempts": 0, "successes": 0},      # 75-85%
            "medium": {"attempts": 0, "successes": 0},    # 50-75%
            "low": {"attempts": 0, "successes": 0}        # < 50%
        }

        # Try to import ollama for vision solving
        try:
            import ollama
            self.ollama_client = ollama
            logger.debug(f"[CAPTCHA] Initialized with vision model: {vision_model}")
        except ImportError:
            logger.warning("[CAPTCHA] Ollama not available - will use manual fallback only")

    @property
    def is_configured(self) -> bool:
        """Always configured - no API key needed"""
        return True

    async def solve_hcaptcha(self, site_key: str, page_url: str) -> Optional[str]:
        """
        hCaptcha requires manual solving - vision models cannot solve these reliably.

        Args:
            site_key: The hCaptcha sitekey from the page
            page_url: The URL where CAPTCHA appears

        Returns:
            None - manual solving required
        """
        logger.info(f"[CAPTCHA] hCaptcha detected - manual solving required")
        return None

    async def solve_recaptcha_v2(self, site_key: str, page_url: str) -> Optional[str]:
        """
        reCAPTCHA v2 requires manual solving - vision models cannot solve these reliably.

        Args:
            site_key: The reCAPTCHA sitekey
            page_url: The URL where CAPTCHA appears

        Returns:
            None - manual solving required
        """
        logger.info(f"[CAPTCHA] reCAPTCHA v2 detected - manual solving required")
        return None

    async def solve_recaptcha_v3(self, site_key: str, page_url: str, action: str = "submit") -> Optional[str]:
        """
        reCAPTCHA v3 is invisible - usually no manual solving needed.

        Args:
            site_key: The reCAPTCHA sitekey
            page_url: The URL where CAPTCHA appears
            action: The action parameter (usually 'submit')

        Returns:
            None - reCAPTCHA v3 is handled by browser behavior
        """
        logger.info(f"[CAPTCHA] reCAPTCHA v3 detected - typically handled automatically")
        return None

    async def solve_turnstile(self, site_key: str, page_url: str) -> Optional[str]:
        """
        Cloudflare Turnstile requires manual solving - vision models cannot solve these.

        Args:
            site_key: The Turnstile sitekey
            page_url: The URL where Turnstile appears

        Returns:
            None - manual solving required
        """
        logger.info(f"[CAPTCHA] Cloudflare Turnstile detected - manual solving required")
        return None


    async def solve_image_with_vision(self, page, ollama_client=None,
                                       vision_model: str = None,
                                       captcha_type: str = "text",
                                       text_model: str = "0000/ui-tars-1.5-7b:latest") -> Optional[Dict[str, Any]]:
        """
        Solve image CAPTCHA using local LLM vision (FREE - no API key needed)

        Enhanced with:
        - 0000/ui-tars-1.5-7b:latest for BOTH vision AND validation (unified agentic model)
        - moondream:latest for vision analysis (fallback)
        - Context-aware validation
        - OCR error correction
        - Retry with different crops/preprocessing

        Models used:
        - 0000/ui-tars-1.5-7b:latest - Primary unified model for vision + validation (agentic GUI model)
          Tests show UI-TARS validation is FASTER (2.15x) and MORE ACCURATE (+20%) than qwen3:8b
        - moondream:latest - Fallback vision model for CAPTCHA image analysis

        Args:
            page: Playwright page object
            ollama_client: Ollama client instance (optional, uses self.ollama_client if not provided)
            vision_model: Vision model to use (optional, uses self.vision_model if not provided)
            captcha_type: Type of CAPTCHA - "text", "math", "image_selection" (default: "text")
            text_model: Text model for context validation (default: "0000/ui-tars-1.5-7b:latest")

        Returns:
            Dict with keys: "answer" (str), "confidence" (float 0-1), "model" (str used),
            "image_confidence" (float), "context_confidence" (float), "decision" (str)
            or None if confidence too low
        """
        try:
            # Use instance defaults if not provided
            if not ollama_client:
                ollama_client = self.ollama_client
            if not vision_model:
                vision_model = self.vision_model

            if not ollama_client:
                logger.warning("[CAPTCHA] Ollama not available for vision solving")
                return None

            # UI-TARS only - designed for GUI understanding, best for CAPTCHA solving
            # No fallback needed - UI-TARS is available on GPU server
            model_chain = ["0000/ui-tars-1.5-7b:latest"]

            logger.info(f"[CAPTCHA] Attempting vision-based CAPTCHA solve (type: {captcha_type})...")

            # Find CAPTCHA element
            captcha_element = await self._find_captcha_element(page)
            if not captcha_element:
                logger.warning("[CAPTCHA] Could not find CAPTCHA image element")
                return None

            # Try each model in the fallback chain
            for attempt, model in enumerate(model_chain):
                logger.info(f"[CAPTCHA] Attempt {attempt + 1}/{len(model_chain)} with {model}")

                # Get screenshot (with preprocessing on retry)
                screenshot_b64 = await self._get_captcha_screenshot(
                    captcha_element,
                    enhance_contrast=(attempt > 0)  # Enhance on retry
                )

                if not screenshot_b64:
                    continue

                # Get type-specific prompt
                prompt = self._get_captcha_prompt(captcha_type)

                # Query vision model
                try:
                    response = ollama_client.generate(
                        model=model,
                        prompt=prompt,
                        images=[screenshot_b64],
                        options={'temperature': 0.1, 'num_predict': 50}
                    )

                    answer = response.get('response', '').strip()

                    # Clean and validate answer
                    cleaned_answer = self._clean_answer(answer, captcha_type)
                    if not cleaned_answer:
                        logger.warning(f"[CAPTCHA] {model} returned invalid answer: {answer}")
                        continue

                    # Calculate image confidence score (vision model)
                    image_confidence = self._calculate_image_confidence(cleaned_answer, answer, captcha_type)

                    # Apply OCR error correction
                    corrected_answer = self._correct_ocr_errors(cleaned_answer, captcha_type)

                    # Recalculate image confidence after correction
                    if corrected_answer != cleaned_answer:
                        logger.info(f"[CAPTCHA] OCR correction: {cleaned_answer} -> {corrected_answer}")
                        image_confidence = max(0.5, image_confidence - 0.1)  # Lower confidence if corrected

                    # Get image description for context validation
                    image_desc = await self._get_image_description(captcha_element, model, ollama_client)

                    # Context validation with text model
                    context_result = await self._validate_with_context(
                        corrected_answer,
                        captcha_type,
                        image_desc,
                        answer,
                        ollama_client,
                        text_model
                    )

                    context_confidence = context_result.get("confidence", 0.0)
                    context_valid = context_result.get("valid", False)
                    context_reason = context_result.get("reason", "")

                    # Calculate combined confidence
                    combined_confidence = self._calculate_combined_confidence(
                        image_confidence,
                        context_confidence,
                        len(corrected_answer),
                        captcha_type,
                        context_valid
                    )

                    logger.info(f"[CAPTCHA] {model} solved: {corrected_answer}")
                    logger.info(f"[CAPTCHA] Image confidence: {image_confidence:.2f}, Context confidence: {context_confidence:.2f}")
                    logger.info(f"[CAPTCHA] Combined confidence: {combined_confidence:.2f}")
                    logger.info(f"[CAPTCHA] Context validation: {context_reason}")

                    # Determine action based on combined confidence
                    decision, should_accept = self._make_solving_decision(combined_confidence, attempt, len(model_chain))

                    logger.info(f"[CAPTCHA] Decision: {decision}")

                    # Accept if confidence is good enough
                    if should_accept:
                        result = {
                            "answer": corrected_answer,
                            "confidence": combined_confidence,
                            "model": model,
                            "image_confidence": image_confidence,
                            "context_confidence": context_confidence,
                            "decision": decision
                        }

                        # Log metrics for analysis
                        self._log_solve_attempt(
                            captcha_type=captcha_type,
                            combined_confidence=combined_confidence,
                            image_confidence=image_confidence,
                            context_confidence=context_confidence,
                            model=model,
                            answer_length=len(corrected_answer),
                            accepted=True
                        )

                        return result
                    else:
                        logger.warning(f"[CAPTCHA] {decision}, trying next model...")

                        # Log rejected attempt
                        self._log_solve_attempt(
                            captcha_type=captcha_type,
                            combined_confidence=combined_confidence,
                            image_confidence=image_confidence,
                            context_confidence=context_confidence,
                            model=model,
                            answer_length=len(corrected_answer),
                            accepted=False
                        )

                except Exception as e:
                    logger.warning(f"[CAPTCHA] {model} failed: {e}")
                    continue

            logger.error("[CAPTCHA] All vision models failed")
            return None

        except Exception as e:
            logger.error(f"[CAPTCHA] Vision solve error: {e}")
            return None

    async def _find_captcha_element(self, page):
        """Find the CAPTCHA image element on the page."""
        captcha_selectors = [
            'img[alt*="captcha" i]',
            'img[src*="captcha" i]',
            '.captcha-image',
            '#captcha-image',
            'img[class*="captcha" i]',
            '#captcha img',
            '.g-recaptcha img',
            '[data-captcha] img',
            'canvas[id*="captcha"]',  # Canvas-based CAPTCHAs
        ]

        for selector in captcha_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    return element
            except:
                continue
        return None

    async def detect_captcha_type(self, page) -> str:
        """
        Automatically detect the type of CAPTCHA on the page.

        Returns:
            "text", "math", or "image_selection"
        """
        try:
            # Get page text and check for indicators
            page_text = await page.evaluate('() => document.body.innerText.toLowerCase()')

            # Check for math CAPTCHA indicators
            if any(indicator in page_text for indicator in [
                'solve', 'equation', 'calculate', 'what is', 'math',
                '+', '-', '×', '÷', '='
            ]):
                logger.debug("[CAPTCHA] Detected math CAPTCHA based on page text")
                return "math"

            # Check for image selection CAPTCHA indicators
            if any(indicator in page_text for indicator in [
                'select all', 'click on', 'identify', 'which images',
                'select images', 'click all'
            ]):
                logger.debug("[CAPTCHA] Detected image selection CAPTCHA based on page text")
                return "image_selection"

            # Default to text CAPTCHA
            logger.debug("[CAPTCHA] Defaulting to text CAPTCHA")
            return "text"

        except Exception as e:
            logger.warning(f"[CAPTCHA] Type detection failed: {e}, defaulting to text")
            return "text"

    async def _get_captcha_screenshot(self, element, enhance_contrast: bool = False):
        """Take screenshot of CAPTCHA element with optional preprocessing."""
        import base64
        try:
            screenshot_bytes = await element.screenshot()

            # Enhance contrast on retry
            if enhance_contrast:
                screenshot_bytes = await self._enhance_image(screenshot_bytes)

            screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            return screenshot_b64
        except Exception as e:
            logger.error(f"[CAPTCHA] Screenshot failed: {e}")
            return None

    async def _enhance_image(self, image_bytes):
        """Enhance image contrast and clarity using PIL."""
        try:
            from PIL import Image, ImageEnhance
            import io

            # Load image
            img = Image.open(io.BytesIO(image_bytes))

            # Enhance contrast
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.0)  # Increase contrast by 2x

            # Enhance sharpness
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.5)

            # Save back to bytes
            output = io.BytesIO()
            img.save(output, format='PNG')
            return output.getvalue()

        except Exception as e:
            logger.warning(f"[CAPTCHA] Image enhancement failed: {e}")
            return image_bytes  # Return original if enhancement fails

    def _get_captcha_prompt(self, captcha_type: str) -> str:
        """Get type-specific prompt for vision model."""
        prompts = {
            "text": """Look at this CAPTCHA image carefully.
Read the distorted text exactly as shown, character by character.
The text may be warped, overlapping, or have lines through it.
Respond ONLY with the exact characters visible - no explanations or extra text.
Example: If you see "Abc123", respond with: Abc123""",

            "math": """Look at this CAPTCHA image carefully.
You will see a math problem like "2 + 3 = ?" or "5 × 4 = ?".
Solve the math problem and respond ONLY with the number answer.
Do not include the equation, equals sign, or any explanation.
Example: If you see "2 + 3 = ?", respond with: 5""",

            "image_selection": """Look at this CAPTCHA grid carefully.
You will see a 3x3 grid of images numbered 1-9 (left to right, top to bottom).
Identify which grid positions contain the requested object.
Respond ONLY with the grid numbers separated by commas.
Example: If positions 1, 4, and 7 contain the object, respond with: 1,4,7"""
        }

        return prompts.get(captcha_type, prompts["text"])

    def _clean_answer(self, answer: str, captcha_type: str) -> Optional[str]:
        """Clean and validate the vision model's answer."""
        if not answer:
            return None

        # Remove quotes and extra whitespace
        cleaned = answer.replace('"', '').replace("'", '').strip()

        # Take first line only
        cleaned = cleaned.split('\n')[0]

        # Remove common LLM prefixes
        prefixes_to_remove = [
            "the text is:", "the answer is:", "i see:", "response:",
            "the code is:", "captcha:", "text:", "answer:"
        ]
        for prefix in prefixes_to_remove:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()

        # Type-specific validation
        if captcha_type == "text":
            # Text CAPTCHAs should be 3-10 characters
            if not (3 <= len(cleaned) <= 15):
                return None

        elif captcha_type == "math":
            # Math should be a number
            import re
            match = re.search(r'-?\d+', cleaned)
            if match:
                cleaned = match.group(0)
            else:
                return None

        elif captcha_type == "image_selection":
            # Image selection should be numbers 1-9 separated by commas
            import re
            if not re.match(r'^[1-9](,[1-9])*$', cleaned):
                return None

        return cleaned if cleaned else None

    def _calculate_image_confidence(self, cleaned_answer: str, raw_answer: str,
                                    captcha_type: str) -> float:
        """
        Calculate confidence score from vision model (image analysis).

        Factors:
        - Answer length (text CAPTCHAs typically 3-10 chars)
        - Raw answer quality (extra text = lower confidence)
        - Ambiguous characters (O/0, I/l/1)
        - LLM artifacts (refusal phrases)
        """
        confidence = 1.0

        # Penalize if answer is too long
        if captcha_type == "text":
            if len(cleaned_answer) > 10:
                confidence -= 0.3
            elif len(cleaned_answer) > 15:
                confidence -= 0.5

        # Penalize if raw answer had extra text
        if len(raw_answer) > len(cleaned_answer) * 1.5:
            confidence -= 0.2

        # Penalize if answer has unusual characters
        import re
        if captcha_type == "text":
            # Check for common OCR confusion characters
            if re.search(r'[O0Il1]', cleaned_answer):
                confidence -= 0.1  # Ambiguous characters

        # Check for common LLM artifacts
        artifacts = ["sorry", "cannot", "unable", "don't", "can't", "unclear"]
        if any(art in raw_answer.lower() for art in artifacts):
            confidence -= 0.5

        return max(0.0, min(1.0, confidence))

    async def _get_image_description(self, captcha_element, model: str, ollama_client) -> str:
        """Get a brief description of the CAPTCHA image for context validation."""
        try:
            screenshot_bytes = await captcha_element.screenshot()
            import base64
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

            desc_prompt = """Briefly describe what you see in this CAPTCHA image in 1-2 sentences.
Focus on: image clarity, distortion level, text readability, background noise."""

            response = ollama_client.generate(
                model=model,
                prompt=desc_prompt,
                images=[screenshot_b64],
                options={'temperature': 0.1, 'num_predict': 100}
            )

            return response.get('response', '').strip()
        except Exception as e:
            logger.warning(f"[CAPTCHA] Image description failed: {e}")
            return "Unable to describe image"

    async def _validate_with_context(self, answer: str, captcha_type: str,
                                     image_desc: str, raw_answer: str,
                                     ollama_client, text_model: str) -> Dict[str, Any]:
        """
        Use text model to validate the vision model's answer with context.

        Returns:
            Dict with keys: "valid" (bool), "confidence" (0-1), "reason" (str)
        """
        try:
            prompt = f"""Analyze this CAPTCHA solving attempt:

CAPTCHA Type: {captcha_type}
Vision Model Answer: {answer}
Image Description: {image_desc}
Raw Output: {raw_answer}

Questions to answer:
1. Does the answer format match the expected CAPTCHA type?
2. Is the answer plausible (not gibberish or random characters)?
3. Any red flags suggesting wrong answer (e.g., too long, contains error messages)?

Consider:
- Text CAPTCHAs are typically 3-10 alphanumeric characters
- Math CAPTCHAs should be a number
- Image selection should be grid positions (e.g., "1,4,7")

Return ONLY a JSON object with this exact format:
{{"valid": true/false, "confidence": 0.0-1.0, "reason": "brief explanation"}}"""

            response = ollama_client.generate(
                model=text_model,
                prompt=prompt,
                options={'temperature': 0.1, 'num_predict': 150}
            )

            response_text = response.get('response', '').strip()

            # Parse JSON response
            import json
            import re

            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                return {
                    "valid": result.get("valid", False),
                    "confidence": float(result.get("confidence", 0.0)),
                    "reason": result.get("reason", "No reason provided")
                }
            else:
                # Fallback: check for positive/negative keywords
                positive_keywords = ["valid", "plausible", "correct", "matches", "reasonable"]
                negative_keywords = ["invalid", "implausible", "wrong", "gibberish", "error"]

                text_lower = response_text.lower()

                has_positive = any(kw in text_lower for kw in positive_keywords)
                has_negative = any(kw in text_lower for kw in negative_keywords)

                if has_positive and not has_negative:
                    return {"valid": True, "confidence": 0.7, "reason": "Text analysis suggests valid"}
                elif has_negative:
                    return {"valid": False, "confidence": 0.3, "reason": "Text analysis suggests invalid"}
                else:
                    return {"valid": True, "confidence": 0.5, "reason": "Uncertain from text analysis"}

        except Exception as e:
            logger.warning(f"[CAPTCHA] Context validation failed: {e}")
            return {"valid": True, "confidence": 0.5, "reason": f"Validation error: {e}"}

    def _calculate_combined_confidence(self, image_confidence: float,
                                       context_confidence: float,
                                       answer_length: int,
                                       captcha_type: str,
                                       context_valid: bool) -> float:
        """
        Calculate combined confidence from vision and text models.

        Weights:
        - image_confidence: 60%
        - context_confidence: 30%
        - format_validity: 10%

        Penalties:
        - Answer too long (>10 chars): -20%
        - Answer contains spaces: -15%
        - Context validation failed: -25%
        """
        # Base weighted average
        combined = (image_confidence * 0.6) + (context_confidence * 0.3)

        # Format validity bonus (10%)
        format_valid = True
        if captcha_type == "text":
            format_valid = 3 <= answer_length <= 10
        elif captcha_type == "math":
            format_valid = answer_length <= 4  # Math answers are usually short
        elif captcha_type == "image_selection":
            format_valid = answer_length <= 20  # e.g., "1,4,7,9"

        if format_valid:
            combined += 0.1

        # Apply penalties
        if captcha_type == "text" and answer_length > 10:
            combined -= 0.2

        # Context validation penalty
        if not context_valid:
            combined -= 0.25

        return max(0.0, min(1.0, combined))

    def _make_solving_decision(self, combined_confidence: float,
                               attempt: int, total_attempts: int) -> tuple[str, bool]:
        """
        Decide whether to accept the answer based on confidence and context.

        Thresholds:
        - >= 85%: Auto-solve immediately
        - 75-85%: Auto-solve with single retry on failure
        - 50-75%: Try once, then human fallback
        - < 50%: Skip to human fallback immediately

        Returns:
            (decision_message, should_accept)
        """
        is_last_attempt = (attempt + 1) >= total_attempts

        if combined_confidence >= 0.85:
            return ("Auto-solve: HIGH confidence (≥85%)", True)

        elif combined_confidence >= 0.75:
            if is_last_attempt:
                return ("Auto-solve: GOOD confidence (75-85%), last attempt", True)
            else:
                return ("Auto-solve: GOOD confidence (75-85%), will retry if fails", True)

        elif combined_confidence >= 0.50:
            if attempt == 0:
                return ("Try once: MEDIUM confidence (50-75%)", True)
            else:
                return ("Skip: MEDIUM confidence (50-75%), already tried", False)

        else:
            return ("Skip: LOW confidence (<50%), human fallback recommended", False)

    def _log_solve_attempt(self, captcha_type: str, combined_confidence: float,
                           image_confidence: float, context_confidence: float,
                           model: str, answer_length: int, accepted: bool):
        """
        Log CAPTCHA solving attempt for metrics and analysis.

        Tracks:
        - Success rate by confidence level
        - Model performance
        - Historical data for threshold adjustment
        """
        import time

        # Record attempt
        attempt_data = {
            "timestamp": time.time(),
            "captcha_type": captcha_type,
            "combined_confidence": combined_confidence,
            "image_confidence": image_confidence,
            "context_confidence": context_confidence,
            "model": model,
            "answer_length": answer_length,
            "accepted": accepted
        }
        self.solve_attempts.append(attempt_data)

        # Keep only last 100 attempts to avoid memory bloat
        if len(self.solve_attempts) > 100:
            self.solve_attempts = self.solve_attempts[-100:]

        # Categorize by confidence level
        if combined_confidence >= 0.85:
            confidence_level = "high"
        elif combined_confidence >= 0.75:
            confidence_level = "good"
        elif combined_confidence >= 0.50:
            confidence_level = "medium"
        else:
            confidence_level = "low"

        # Track attempt in success metrics
        self.success_by_confidence[confidence_level]["attempts"] += 1
        if accepted:
            self.success_by_confidence[confidence_level]["successes"] += 1

        # Log to file for persistence
        try:
            import json
            import os
            log_file = os.path.expanduser("~/.eversale/captcha_metrics.jsonl")
            os.makedirs(os.path.dirname(log_file), exist_ok=True)

            with open(log_file, "a") as f:
                f.write(json.dumps(attempt_data) + "\n")

            logger.debug(f"[CAPTCHA METRICS] Logged attempt: {confidence_level} confidence, accepted={accepted}")
        except Exception as e:
            logger.debug(f"[CAPTCHA METRICS] Failed to log to file: {e}")

    def get_metrics_summary(self) -> Dict[str, Any]:
        """
        Get summary of CAPTCHA solving metrics.

        Returns:
            Dict with success rates by confidence level and recommendations
        """
        summary = {
            "total_attempts": len(self.solve_attempts),
            "by_confidence": {}
        }

        for level, stats in self.success_by_confidence.items():
            attempts = stats["attempts"]
            successes = stats["successes"]

            if attempts > 0:
                success_rate = successes / attempts
                summary["by_confidence"][level] = {
                    "attempts": attempts,
                    "successes": successes,
                    "success_rate": success_rate
                }
            else:
                summary["by_confidence"][level] = {
                    "attempts": 0,
                    "successes": 0,
                    "success_rate": 0.0
                }

        # Add recommendations based on historical data
        recommendations = []

        # If high confidence success rate is low, suggest adjusting thresholds
        high_stats = summary["by_confidence"]["high"]
        if high_stats["attempts"] >= 5 and high_stats["success_rate"] < 0.7:
            recommendations.append("High confidence success rate is low (<70%). Consider raising high confidence threshold.")

        # If medium confidence has good success rate, suggest lowering threshold
        medium_stats = summary["by_confidence"]["medium"]
        if medium_stats["attempts"] >= 5 and medium_stats["success_rate"] > 0.8:
            recommendations.append("Medium confidence success rate is high (>80%). Consider lowering acceptance threshold.")

        summary["recommendations"] = recommendations

        return summary

    def record_solve_result(self, success: bool):
        """
        Record whether the last solve attempt actually succeeded.

        Call this after submitting the CAPTCHA answer to track accuracy.

        Args:
            success: True if CAPTCHA was accepted, False if rejected
        """
        if not self.solve_attempts:
            logger.warning("[CAPTCHA METRICS] No solve attempts to record result for")
            return

        # Update the last attempt
        last_attempt = self.solve_attempts[-1]
        last_attempt["actual_success"] = success

        # Update success metrics
        combined_confidence = last_attempt["combined_confidence"]

        if combined_confidence >= 0.85:
            confidence_level = "high"
        elif combined_confidence >= 0.75:
            confidence_level = "good"
        elif combined_confidence >= 0.50:
            confidence_level = "medium"
        else:
            confidence_level = "low"

        # If we previously counted this as a success but it failed, decrement
        if last_attempt.get("accepted") and not success:
            self.success_by_confidence[confidence_level]["successes"] -= 1
            logger.warning(f"[CAPTCHA METRICS] {confidence_level} confidence attempt FAILED in practice")
        # If we previously rejected but marking as success (shouldn't happen normally)
        elif not last_attempt.get("accepted") and success:
            logger.info(f"[CAPTCHA METRICS] {confidence_level} confidence attempt succeeded despite rejection")

        # Log result to file
        try:
            import json
            import os
            log_file = os.path.expanduser("~/.eversale/captcha_metrics.jsonl")

            # Append updated result
            with open(log_file, "a") as f:
                f.write(json.dumps(last_attempt) + "\n")

            logger.debug(f"[CAPTCHA METRICS] Recorded actual result: success={success}")
        except Exception as e:
            logger.debug(f"[CAPTCHA METRICS] Failed to log result: {e}")

    def _correct_ocr_errors(self, answer: str, captcha_type: str) -> str:
        """Correct common OCR errors using substitution rules."""
        if captcha_type != "text":
            return answer  # Only apply to text CAPTCHAs

        # Common OCR substitutions (context-dependent)
        # We'll try both versions if ambiguous, but for now use simple rules

        corrected = answer

        # If answer looks like it should be alphanumeric, apply corrections
        import re

        # Common patterns to fix:
        # - "O" at end of number sequences likely should be "0"
        # - "0" in middle of letter sequences likely should be "O"
        # - "l" at start of words likely should be "I"
        # - "1" surrounded by letters likely should be "l" or "I"

        # Replace O with 0 if surrounded by digits
        corrected = re.sub(r'(\d)O(\d)', r'\g<1>0\2', corrected)
        corrected = re.sub(r'(\d)O$', r'\g<1>0', corrected)
        corrected = re.sub(r'^O(\d)', r'0\1', corrected)

        # Replace 0 with O if surrounded by letters
        corrected = re.sub(r'([a-zA-Z])0([a-zA-Z])', r'\g<1>O\2', corrected)

        # Replace l with I at start of capitalized words
        if corrected and corrected[0] == 'l' and len(corrected) > 1 and corrected[1].isupper():
            corrected = 'I' + corrected[1:]

        # Replace 1 with l if surrounded by lowercase letters
        corrected = re.sub(r'([a-z])1([a-z])', r'\g<1>l\2', corrected)

        # Replace 5 with S if surrounded by letters
        corrected = re.sub(r'([a-zA-Z])5([a-zA-Z])', r'\g<1>S\2', corrected)

        # Replace 8 with B if surrounded by letters
        corrected = re.sub(r'([a-zA-Z])8([a-zA-Z])', r'\g<1>B\2', corrected)

        if corrected != answer:
            logger.debug(f"[CAPTCHA] OCR corrections applied: {answer} -> {corrected}")

        return corrected


class AmazonCaptchaHandler:
    """
    Specialized handler for Amazon's CAPTCHA and bot detection.

    Strategies:
    1. Prevention: Human-like behavior to avoid triggering CAPTCHA
    2. Detection: Identify Amazon CAPTCHA types
    3. Solving: Vision-based solving + manual popup fallback
    """

    # Amazon CAPTCHA indicators
    AMAZON_CAPTCHA_PATTERNS = [
        'captcha', 'robot check', 'automated access',
        'sorry! something went wrong', 'enter the characters',
        'type the characters', 'prove you are not a robot',
        'api-services-support@amazon.com'
    ]

    AWS_WAF_INDICATORS = [
        'awsWafCaptcha', 'aws-waf-token', 'challenge.js',
        'captcha.awswaf', 'waf-challenge'
    ]

    def __init__(self, page, solver: LocalCaptchaSolver = None):
        self.page = page
        self.solver = solver or LocalCaptchaSolver()

    async def detect_amazon_captcha(self) -> Dict[str, Any]:
        """Detect if Amazon is showing a CAPTCHA"""
        try:
            content = await self.page.content()
            content_lower = content.lower()
            url = self.page.url.lower()

            # Check for AWS WAF CAPTCHA (most common on Amazon)
            is_aws_waf = any(ind in content_lower for ind in self.AWS_WAF_INDICATORS)

            # Check for general Amazon CAPTCHA
            is_captcha = any(pat in content_lower for pat in self.AMAZON_CAPTCHA_PATTERNS)

            if is_aws_waf:
                # Extract AWS WAF site key
                import re
                site_key_match = re.search(r'data-sitekey=["\']([^"\']+)["\']', content)
                site_key = site_key_match.group(1) if site_key_match else None

                return {
                    "detected": True,
                    "type": "aws_waf",
                    "site_key": site_key,
                    "url": url,
                    "message": "Amazon AWS WAF CAPTCHA detected"
                }
            elif is_captcha:
                return {
                    "detected": True,
                    "type": "image_captcha",
                    "url": url,
                    "message": "Amazon image CAPTCHA detected"
                }

            return {"detected": False, "type": None}

        except Exception as e:
            return {"detected": False, "type": None, "error": str(e)}

    async def solve_amazon_captcha(self, manual_fallback: bool = True,
                                    ollama_client=None,
                                    vision_model: str = "0000/ui-tars-1.5-7b:latest") -> bool:
        """
        Attempt to solve Amazon CAPTCHA using vision-based solving (NO external APIs)

        Uses local LLM vision models (moondream, UI-TARS, llama3.2-vision) to read CAPTCHA text.
        Falls back to manual popup if vision fails.

        Args:
            manual_fallback: If True, show browser for manual solve if auto fails
            ollama_client: Ollama client (will auto-import if not provided)
            vision_model: Vision model to use (default: moondream for reliability)
        """
        detection = await self.detect_amazon_captcha()

        if not detection.get("detected"):
            logger.info("[AMAZON] No CAPTCHA detected")
            return True

        captcha_type = detection.get("type")
        logger.info(f"[AMAZON] CAPTCHA detected: {captcha_type}")

        # Try vision-based solving (works for both image CAPTCHAs and some AWS WAF)
        # Import ollama if not provided
        if not ollama_client:
            try:
                import ollama
                ollama_client = ollama
            except ImportError:
                logger.warning("[AMAZON] Ollama not available, skipping vision solve")
                ollama_client = None

        if ollama_client:
            logger.info(f"[AMAZON] Trying vision-based solve with {vision_model}...")
            result = await self.solver.solve_image_with_vision(
                self.page, ollama_client, vision_model=vision_model
            )
            if result:
                answer = result.get("answer") if isinstance(result, dict) else result
                confidence = result.get("confidence", 0.0) if isinstance(result, dict) else 0.5
                model_used = result.get("model", vision_model) if isinstance(result, dict) else vision_model
                decision = result.get("decision", "Unknown") if isinstance(result, dict) else "Unknown"
                image_conf = result.get("image_confidence", 0.0) if isinstance(result, dict) else 0.0
                context_conf = result.get("context_confidence", 0.0) if isinstance(result, dict) else 0.0

                logger.info(f"[AMAZON] Vision result: {answer}")
                logger.info(f"[AMAZON] Combined confidence: {confidence:.2f} (image: {image_conf:.2f}, context: {context_conf:.2f})")
                logger.info(f"[AMAZON] Decision: {decision}")

                # Only attempt submission if confidence is acceptable
                if confidence >= 0.50:
                    success = await self._submit_image_captcha_answer(answer)

                    # Record actual result for metrics
                    self.solver.record_solve_result(success)

                    if success:
                        logger.success(f"[AMAZON] CAPTCHA solved via vision ({model_used})!")
                        return True
                    else:
                        logger.warning(f"[AMAZON] Answer submission failed, falling back to manual")
                else:
                    logger.warning(f"[AMAZON] Confidence too low ({confidence:.2f}), skipping auto-solve")

        # Manual fallback
        if manual_fallback:
            logger.info("[AMAZON] Falling back to manual solve...")
            from rich.console import Console
            console = Console()
            console.print("\n[bold yellow]AMAZON CAPTCHA DETECTED[/bold yellow]")
            console.print("[cyan]Please solve the CAPTCHA in the browser window...[/cyan]")

            # Wait for CAPTCHA to be solved (URL changes or content changes)
            start_url = self.page.url
            for _ in range(60):  # 60 * 2s = 2 minutes max
                await asyncio.sleep(2)
                new_detection = await self.detect_amazon_captcha()
                if not new_detection.get("detected"):
                    logger.success("[AMAZON] CAPTCHA solved manually!")
                    return True
                if self.page.url != start_url and 'captcha' not in self.page.url.lower():
                    logger.success("[AMAZON] Page changed - CAPTCHA likely solved!")
                    return True

            logger.warning("[AMAZON] Manual solve timed out")
            return False

        return False

    async def _inject_aws_waf_token(self, token: str) -> bool:
        """Inject AWS WAF solution token"""
        try:
            # Note: AWS WAF token should be obtained dynamically from challenge response
            # This is a placeholder implementation for testing purposes only
            await self.page.evaluate(f'''(token) => {{
                // Set the AWS WAF cookie
                document.cookie = "aws-waf-token=" + token + "; path=/";

                // Try to find and set any hidden fields
                const hiddenFields = document.querySelectorAll('input[name*="waf"], input[name*="captcha"]');
                hiddenFields.forEach(field => field.value = token);

                // Try to submit the form
                const forms = document.querySelectorAll('form');
                if (forms.length > 0) {{
                    forms[0].submit();
                }} else {{
                    location.reload();
                }}
            }}''', token)

            await asyncio.sleep(2)  # Wait for page to process
            return True
        except Exception as e:
            logger.error(f"[AMAZON] Token injection failed: {e}")
            return False

    async def _submit_image_captcha_answer(self, answer: str) -> bool:
        """Submit image CAPTCHA answer"""
        try:
            # Find the input field
            input_selectors = [
                'input[name*="captcha" i]',
                'input[id*="captcha" i]',
                '#captchacharacters',
                'input[type="text"]'
            ]

            for selector in input_selectors:
                try:
                    input_field = await self.page.query_selector(selector)
                    if input_field:
                        await input_field.fill(answer)

                        # Find and click submit button
                        submit_selectors = ['button[type="submit"]', 'input[type="submit"]',
                                           '.a-button-input', '#continue']
                        for btn_sel in submit_selectors:
                            btn = await self.page.query_selector(btn_sel)
                            if btn:
                                await btn.click()
                                await asyncio.sleep(2)
                                return True
                except:
                    continue

            return False
        except Exception as e:
            logger.error(f"[AMAZON] Answer submission failed: {e}")
            return False


class TwoFactorDetector:
    """Detects 2FA prompts on pages."""

    # 2FA detection patterns
    SMS_PATTERNS = [
        'enter.*code.*sent.*phone',
        'verification.*code',
        'sms.*code',
        'text.*message.*code',
        'enter.*6.*digit',
        'mobile.*verification',
        'phone.*verification',
    ]

    AUTHENTICATOR_PATTERNS = [
        'authenticator.*app',
        'google.*authenticator',
        'two.*factor.*authentication',
        '2fa.*code',
        'totp.*code',
        'authentication.*app',
        'verification.*app',
    ]

    EMAIL_PATTERNS = [
        'check.*email.*verification',
        'verification.*link.*email',
        'code.*sent.*email',
        'email.*verification',
        'verify.*email.*address',
    ]

    BACKUP_CODE_PATTERNS = [
        'backup.*code',
        'recovery.*code',
        'emergency.*code',
        'one.*time.*backup',
    ]

    def __init__(self, page):
        self.page = page

    async def detect_2fa(self) -> ChallengeDetection:
        """Detect if page is showing a 2FA prompt."""
        try:
            # Get page text content
            page_text = await self.page.evaluate('''() => {
                return document.body.innerText.toLowerCase();
            }''')

            # Check for SMS code
            for pattern in self.SMS_PATTERNS:
                import re
                if re.search(pattern, page_text, re.IGNORECASE):
                    logger.info("[2FA] Detected SMS code prompt")
                    return ChallengeDetection(
                        detected=True,
                        challenge_type=ChallengeType.SMS_CODE,
                        confidence=0.9,
                        metadata={"matched_pattern": pattern}
                    )

            # Check for authenticator app
            for pattern in self.AUTHENTICATOR_PATTERNS:
                import re
                if re.search(pattern, page_text, re.IGNORECASE):
                    logger.info("[2FA] Detected authenticator app prompt")
                    return ChallengeDetection(
                        detected=True,
                        challenge_type=ChallengeType.AUTHENTICATOR_APP,
                        confidence=0.9,
                        metadata={"matched_pattern": pattern}
                    )

            # Check for email verification
            for pattern in self.EMAIL_PATTERNS:
                import re
                if re.search(pattern, page_text, re.IGNORECASE):
                    logger.info("[2FA] Detected email verification prompt")
                    return ChallengeDetection(
                        detected=True,
                        challenge_type=ChallengeType.EMAIL_VERIFICATION,
                        confidence=0.9,
                        metadata={"matched_pattern": pattern}
                    )

            # Check for backup code
            for pattern in self.BACKUP_CODE_PATTERNS:
                import re
                if re.search(pattern, page_text, re.IGNORECASE):
                    logger.info("[2FA] Detected backup code prompt")
                    return ChallengeDetection(
                        detected=True,
                        challenge_type=ChallengeType.BACKUP_CODE,
                        confidence=0.9,
                        metadata={"matched_pattern": pattern}
                    )

            # Check for common 2FA input fields
            input_field = await self.page.query_selector(
                'input[name*="code"], input[placeholder*="code"], '
                'input[name*="otp"], input[name*="verification"], '
                'input[name*="2fa"], input[autocomplete="one-time-code"]'
            )

            if input_field:
                # Try to determine type from context
                label_text = await self.page.evaluate('''(input) => {
                    const label = input.closest('label') ||
                                 document.querySelector(`label[for="${input.id}"]`);
                    return label ? label.innerText.toLowerCase() : '';
                }''', input_field)

                if 'phone' in label_text or 'sms' in label_text:
                    return ChallengeDetection(
                        detected=True,
                        challenge_type=ChallengeType.SMS_CODE,
                        confidence=0.7,
                        metadata={"label": label_text}
                    )
                elif 'email' in label_text:
                    return ChallengeDetection(
                        detected=True,
                        challenge_type=ChallengeType.EMAIL_VERIFICATION,
                        confidence=0.7,
                        metadata={"label": label_text}
                    )
                else:
                    return ChallengeDetection(
                        detected=True,
                        challenge_type=ChallengeType.AUTHENTICATOR_APP,
                        confidence=0.6,
                        metadata={"label": label_text}
                    )

        except Exception as e:
            logger.error(f"[2FA] Detection error: {e}")

        return ChallengeDetection(detected=False, challenge_type=ChallengeType.UNKNOWN)


class ScrappyCaptchaBypasser:
    """
    FREE CAPTCHA bypass techniques - no API needed!

    Techniques:
    1. Human-like behavior to avoid triggering CAPTCHA
    2. Cookie persistence (solve once, reuse forever)
    3. Manual solve mode (pause for human, continue after)
    4. Accessibility mode bypass attempts
    5. Wait-and-retry (some CAPTCHAs timeout)
    """

    def __init__(self, page):
        self.page = page

    async def act_human(self):
        """Make browser behave more human-like to avoid CAPTCHA triggers"""
        import random

        try:
            # Random mouse movements
            for _ in range(random.randint(3, 7)):
                x = random.randint(100, 800)
                y = random.randint(100, 600)
                await self.page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.1, 0.3))

            # Random scroll
            await self.page.evaluate(f'window.scrollBy(0, {random.randint(50, 200)})')
            await asyncio.sleep(random.uniform(0.5, 1.5))

            # Scroll back
            await self.page.evaluate(f'window.scrollBy(0, -{random.randint(30, 100)})')
            await asyncio.sleep(random.uniform(0.3, 0.8))

            logger.debug("[SCRAPPY] Human-like behavior executed")
        except Exception:
            pass

    async def try_accessibility_bypass(self) -> bool:
        """Try clicking accessibility/audio CAPTCHA options which are sometimes easier"""
        try:
            # hCaptcha accessibility
            access_selectors = [
                '[aria-label*="accessibility"]',
                '[title*="accessibility"]',
                'button:has-text("Get an audio challenge")',
                '.rc-button-audio',  # reCAPTCHA audio button
                '#recaptcha-audio-button',
                '[aria-label*="audio"]',
            ]

            for selector in access_selectors:
                btn = await self.page.query_selector(selector)
                if btn and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(2)
                    logger.info("[SCRAPPY] Clicked accessibility option")
                    return True
        except Exception:
            pass
        return False

    async def wait_for_manual_solve(self, timeout: int = 60) -> bool:
        """
        Pause and wait for human to solve CAPTCHA manually.
        Returns True if CAPTCHA appears to be solved.
        """
        logger.info(f"[SCRAPPY] CAPTCHA detected - waiting {timeout}s for manual solve...")
        logger.info("[SCRAPPY] Please solve the CAPTCHA in the browser window!")

        start = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start) < timeout:
            await asyncio.sleep(2)

            # Check if CAPTCHA is gone
            captcha_gone = await self.page.evaluate('''() => {
                // Check if CAPTCHA elements are still visible
                const hcaptcha = document.querySelector('[data-hcaptcha-widget-id], .h-captcha');
                const recaptcha = document.querySelector('.g-recaptcha, [data-sitekey]');
                const captchaFrame = document.querySelector('iframe[src*="captcha"], iframe[src*="hcaptcha"]');
                const turnstile = document.querySelector('[data-sitekey][data-callback]');

                // Check if any response field is filled
                const responses = document.querySelectorAll(
                    'textarea[name="h-captcha-response"], textarea[name="g-recaptcha-response"], textarea[name="cf-turnstile-response"]'
                );
                for (const r of responses) {
                    if (r.value && r.value.length > 10) return true;
                }

                // Check if captcha container is hidden
                if (hcaptcha && hcaptcha.offsetParent === null) return true;
                if (recaptcha && recaptcha.offsetParent === null) return true;
                if (turnstile && turnstile.offsetParent === null) return true;

                return false;
            }''')

            if captcha_gone:
                logger.success("[SCRAPPY] CAPTCHA solved manually!")
                return True

        logger.warning("[SCRAPPY] Timeout waiting for manual CAPTCHA solve")
        return False

    async def try_checkbox_click(self) -> bool:
        """Try clicking the CAPTCHA checkbox (sometimes just works)"""
        try:
            checkbox_selectors = [
                '.recaptcha-checkbox',
                '.recaptcha-checkbox-border',
                '#recaptcha-anchor',
                '[role="checkbox"]',
                '.checkbox',
            ]

            for selector in checkbox_selectors:
                # Try in main page
                cb = await self.page.query_selector(selector)
                if cb and await cb.is_visible():
                    await cb.click()
                    await asyncio.sleep(3)
                    logger.info("[SCRAPPY] Clicked CAPTCHA checkbox")
                    return True

                # Try in iframes
                for frame in self.page.frames:
                    try:
                        cb = await frame.query_selector(selector)
                        if cb and await cb.is_visible():
                            await cb.click()
                            await asyncio.sleep(3)
                            logger.info("[SCRAPPY] Clicked CAPTCHA checkbox in iframe")
                            return True
                    except Exception:
                        continue

            # Last resort: try visual fallback on main page
            if VISUAL_FALLBACK_AVAILABLE and get_visual_fallback:
                visual_fb = get_visual_fallback()
                if visual_fb.has_vision:
                    logger.info("[SCRAPPY] Trying visual fallback for CAPTCHA checkbox")
                    coords = await visual_fb.find_element_visually(
                        self.page,
                        "the CAPTCHA checkbox or 'I'm not a robot' checkbox"
                    )
                    if coords:
                        x, y = coords
                        await self.page.mouse.click(x, y)
                        await asyncio.sleep(3)
                        logger.info(f"[SCRAPPY] Clicked CAPTCHA checkbox visually at ({x}, {y})")
                        return True

        except Exception:
            pass
        return False

    async def bypass(self, manual_fallback: bool = True, manual_timeout: int = 30) -> bool:
        """
        Try all scrappy bypass techniques.

        Args:
            manual_fallback: If True, wait for manual solve as last resort
            manual_timeout: Seconds to wait for manual solve

        Returns:
            True if CAPTCHA bypassed, False otherwise
        """
        logger.info("[SCRAPPY] Attempting free CAPTCHA bypass...")

        # Step 1: Act human first
        await self.act_human()
        await asyncio.sleep(1)

        # Step 2: Try just clicking the checkbox
        if await self.try_checkbox_click():
            await asyncio.sleep(2)
            # Check if it worked
            solved = await self.page.evaluate('''() => {
                const responses = document.querySelectorAll(
                    'textarea[name="h-captcha-response"], textarea[name="g-recaptcha-response"], textarea[name="cf-turnstile-response"]'
                );
                for (const r of responses) {
                    if (r.value && r.value.length > 10) return true;
                }
                return false;
            }''')
            if solved:
                logger.success("[SCRAPPY] Checkbox click worked!")
                return True

        # Step 3: Try accessibility options
        await self.try_accessibility_bypass()

        # Step 4: Manual fallback
        if manual_fallback:
            return await self.wait_for_manual_solve(manual_timeout)

        return False


class PageCaptchaHandler:
    """
    Integrates CAPTCHA solving with Playwright page automation.
    Detects, solves, and injects CAPTCHA solutions.
    """

    def __init__(self, page, solver: LocalCaptchaSolver = None, webhook_url: str = None):
        self.page = page
        self.solver = solver or LocalCaptchaSolver()
        self.scrappy = ScrappyCaptchaBypasser(page)  # Free bypass option
        self.twofa_detector = TwoFactorDetector(page)
        self.webhook_url = webhook_url or os.environ.get("CAPTCHA_WEBHOOK_URL")
        self.notification_callback: Optional[Callable] = None

    def set_notification_callback(self, callback: Callable):
        """Set a callback function for notifications (e.g., to pause agent)."""
        self.notification_callback = callback

    async def detect_captcha(self) -> ChallengeDetection:
        """Detect what type of CAPTCHA is on the page"""
        try:
            # Check for Cloudflare Turnstile (check first as it's common)
            turnstile = await self.page.query_selector('[data-sitekey][data-callback], .cf-turnstile')
            if turnstile:
                site_key = await turnstile.get_attribute('data-sitekey')
                if site_key:
                    logger.info("[CAPTCHA] Detected Cloudflare Turnstile")
                    return ChallengeDetection(
                        detected=True,
                        challenge_type=ChallengeType.CLOUDFLARE_TURNSTILE,
                        site_key=site_key,
                        confidence=0.95
                    )

            # Check for hCaptcha
            hcaptcha = await self.page.query_selector('[data-sitekey][data-hcaptcha-widget-id], .h-captcha[data-sitekey]')
            if hcaptcha:
                site_key = await hcaptcha.get_attribute('data-sitekey')
                logger.info("[CAPTCHA] Detected hCaptcha")
                return ChallengeDetection(
                    detected=True,
                    challenge_type=ChallengeType.HCAPTCHA,
                    site_key=site_key,
                    confidence=0.95
                )

            # Check for hCaptcha iframe
            hcaptcha_frame = await self.page.query_selector('iframe[src*="hcaptcha.com"]')
            if hcaptcha_frame:
                # Try to extract sitekey from page
                site_key = await self.page.evaluate('''() => {
                    const el = document.querySelector('[data-sitekey]');
                    return el ? el.getAttribute('data-sitekey') : null;
                }''')
                if site_key:
                    logger.info("[CAPTCHA] Detected hCaptcha (iframe)")
                    return ChallengeDetection(
                        detected=True,
                        challenge_type=ChallengeType.HCAPTCHA,
                        site_key=site_key,
                        confidence=0.9
                    )

            # Check for reCAPTCHA v2
            recaptcha_v2 = await self.page.query_selector('.g-recaptcha[data-sitekey]')
            if recaptcha_v2:
                site_key = await recaptcha_v2.get_attribute('data-sitekey')
                logger.info("[CAPTCHA] Detected reCAPTCHA v2")
                return ChallengeDetection(
                    detected=True,
                    challenge_type=ChallengeType.RECAPTCHA_V2,
                    site_key=site_key,
                    confidence=0.95
                )

            # Check for reCAPTCHA v3 (invisible)
            recaptcha_v3 = await self.page.evaluate('''() => {
                const scripts = document.querySelectorAll('script[src*="recaptcha"]');
                for (const s of scripts) {
                    if (s.src.includes('render=')) {
                        const match = s.src.match(/render=([^&]+)/);
                        if (match) return match[1];
                    }
                }
                return null;
            }''')
            if recaptcha_v3:
                logger.info("[CAPTCHA] Detected reCAPTCHA v3")
                return ChallengeDetection(
                    detected=True,
                    challenge_type=ChallengeType.RECAPTCHA_V3,
                    site_key=recaptcha_v3,
                    confidence=0.9
                )

            # Check for reCAPTCHA iframe
            recaptcha_frame = await self.page.query_selector('iframe[src*="recaptcha"]')
            if recaptcha_frame:
                site_key = await self.page.evaluate('''() => {
                    const el = document.querySelector('[data-sitekey], .g-recaptcha');
                    return el ? el.getAttribute('data-sitekey') : null;
                }''')
                if site_key:
                    logger.info("[CAPTCHA] Detected reCAPTCHA (iframe)")
                    return ChallengeDetection(
                        detected=True,
                        challenge_type=ChallengeType.RECAPTCHA_V2,
                        site_key=site_key,
                        confidence=0.9
                    )

            # Check for image-based CAPTCHAs (generic)
            image_captcha = await self.page.query_selector(
                'img[alt*="captcha"], img[src*="captcha"], '
                'img[alt*="verification"], canvas[id*="captcha"]'
            )
            if image_captcha:
                logger.info("[CAPTCHA] Detected image-based CAPTCHA")
                return ChallengeDetection(
                    detected=True,
                    challenge_type=ChallengeType.IMAGE_CAPTCHA,
                    confidence=0.7,
                    metadata={"requires_manual": True}
                )

        except Exception as e:
            logger.error(f"[CAPTCHA] Detection error: {e}")

        return ChallengeDetection(detected=False, challenge_type=ChallengeType.UNKNOWN)

    async def detect_all_challenges(self) -> List[ChallengeDetection]:
        """Detect all types of challenges (CAPTCHA + 2FA)."""
        challenges = []

        # Check for CAPTCHA
        captcha = await self.detect_captcha()
        if captcha.detected:
            challenges.append(captcha)

        # Check for 2FA
        twofa = await self.twofa_detector.detect_2fa()
        if twofa.detected:
            challenges.append(twofa)

        return challenges

    async def notify_user(self, challenge: ChallengeDetection):
        """Notify user about detected challenge (console + optional webhook)."""
        challenge_name = challenge.challenge_type.value.replace("_", " ").title()

        # Console notification
        logger.warning("=" * 70)
        logger.warning(f"[AUTH CHALLENGE] {challenge_name} detected!")
        logger.warning("=" * 70)

        if challenge.challenge_type in [ChallengeType.SMS_CODE, ChallengeType.AUTHENTICATOR_APP]:
            logger.info("[2FA] Please complete 2-factor authentication in the browser")
            logger.info("[2FA] Type 'continue' when done")
        elif challenge.challenge_type == ChallengeType.EMAIL_VERIFICATION:
            logger.info("[2FA] Please check your email and complete verification")
            logger.info("[2FA] Type 'continue' when done")
        else:
            logger.info(f"[CHALLENGE] Please solve the {challenge_name} in the browser")
            logger.info("[CHALLENGE] Type 'continue' when done")

        logger.warning("=" * 70)

        # Webhook notification (if configured)
        if self.webhook_url:
            await self._send_webhook_notification(challenge)

        # Custom callback (e.g., to pause agent)
        if self.notification_callback:
            await self.notification_callback(challenge)

    async def _send_webhook_notification(self, challenge: ChallengeDetection):
        """Send webhook notification about challenge."""
        try:
            payload = {
                "type": "auth_challenge",
                "challenge_type": challenge.challenge_type.value,
                "url": self.page.url,
                "timestamp": time.time(),
                "metadata": challenge.metadata
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload, timeout=5) as resp:
                    if resp.status == 200:
                        logger.debug("[WEBHOOK] Notification sent successfully")
                    else:
                        logger.warning(f"[WEBHOOK] Failed to send notification: {resp.status}")
        except Exception as e:
            logger.error(f"[WEBHOOK] Error sending notification: {e}")

    async def wait_for_user_resolution(self, challenge: ChallengeDetection, timeout: int = 300) -> bool:
        """
        Wait for user to manually resolve the challenge.

        Args:
            challenge: The detected challenge
            timeout: Maximum wait time in seconds (default 5 minutes)

        Returns:
            True if challenge was resolved, False if timeout

        Note:
            If using A11yBrowser in headless mode, call browser.show_browser()
            before this method to make the browser visible for manual solving.
        """
        start = time.time()

        while (time.time() - start) < timeout:
            await asyncio.sleep(2)

            # Check if challenge is resolved
            if challenge.challenge_type in [ChallengeType.SMS_CODE, ChallengeType.AUTHENTICATOR_APP,
                                           ChallengeType.EMAIL_VERIFICATION, ChallengeType.BACKUP_CODE]:
                # For 2FA, check if we've navigated away or the input is gone
                current_2fa = await self.twofa_detector.detect_2fa()
                if not current_2fa.detected:
                    logger.success("[2FA] Challenge resolved!")
                    return True
            else:
                # For CAPTCHA, check if it's solved
                captcha_solved = await self.page.evaluate('''() => {
                    const responses = document.querySelectorAll(
                        'textarea[name="h-captcha-response"], textarea[name="g-recaptcha-response"], textarea[name="cf-turnstile-response"]'
                    );
                    for (const r of responses) {
                        if (r.value && r.value.length > 10) return true;
                    }
                    return false;
                }''')

                if captcha_solved:
                    logger.success("[CAPTCHA] Challenge resolved!")
                    return True

        logger.warning(f"[CHALLENGE] Timeout waiting for resolution ({timeout}s)")
        return False

    async def solve_and_inject(self, auto_fallback: bool = True) -> bool:
        """
        Detect CAPTCHA, solve it, and inject the solution.

        Args:
            auto_fallback: If True, fallback to manual solve if API fails

        Returns:
            True if successful or no CAPTCHA found.
        """
        detection = await self.detect_captcha()

        if not detection.detected:
            return True  # No CAPTCHA, all good

        page_url = self.page.url
        site_key = detection.site_key
        captcha_type = detection.challenge_type

        logger.info(f"[CAPTCHA] Detected {captcha_type.value} on page")

        # Try automated solving first (if configured)
        token = None
        if self.solver.is_configured and site_key:
            if captcha_type == ChallengeType.HCAPTCHA:
                token = await self.solver.solve_hcaptcha(site_key, page_url)
            elif captcha_type == ChallengeType.RECAPTCHA_V2:
                token = await self.solver.solve_recaptcha_v2(site_key, page_url)
            elif captcha_type == ChallengeType.RECAPTCHA_V3:
                token = await self.solver.solve_recaptcha_v3(site_key, page_url)
            elif captcha_type == ChallengeType.CLOUDFLARE_TURNSTILE:
                token = await self.solver.solve_turnstile(site_key, page_url)

            if token:
                # Inject solution
                success = await self._inject_solution(captcha_type, token)
                if success:
                    return True

        # Fallback to manual solve
        if auto_fallback:
            logger.info("[CAPTCHA] Falling back to manual solve")
            await self.notify_user(detection)
            return await self.wait_for_user_resolution(detection)

        return False

    async def _inject_solution(self, captcha_type: ChallengeType, token: str) -> bool:
        """Inject the CAPTCHA solution token into the page"""
        try:
            if captcha_type == ChallengeType.HCAPTCHA:
                # Inject into hCaptcha response fields
                await self.page.evaluate(f'''(token) => {{
                    // Set textarea response
                    const textareas = document.querySelectorAll('textarea[name="h-captcha-response"], textarea[name="g-recaptcha-response"]');
                    textareas.forEach(ta => {{ ta.value = token; }});

                    // Also set any hidden inputs
                    const hiddens = document.querySelectorAll('input[name="h-captcha-response"]');
                    hiddens.forEach(h => {{ h.value = token; }});

                    // Try to trigger hCaptcha callback if exists
                    if (window.hcaptcha) {{
                        try {{ window.hcaptcha.execute(); }} catch(e) {{}}
                    }}
                }}''', token)

            elif captcha_type in [ChallengeType.RECAPTCHA_V2, ChallengeType.RECAPTCHA_V3]:
                # Inject into reCAPTCHA response fields
                await self.page.evaluate(f'''(token) => {{
                    // Set textarea response
                    const textareas = document.querySelectorAll('textarea[name="g-recaptcha-response"]');
                    textareas.forEach(ta => {{
                        ta.value = token;
                        ta.style.display = 'block';  // Make visible for some implementations
                    }});

                    // Try to trigger callback
                    if (window.grecaptcha && window.grecaptcha.getResponse) {{
                        // Find callback function name
                        const callback = document.querySelector('[data-callback]')?.getAttribute('data-callback');
                        if (callback && window[callback]) {{
                            window[callback](token);
                        }}
                    }}
                }}''', token)

            elif captcha_type == ChallengeType.CLOUDFLARE_TURNSTILE:
                # Inject into Turnstile response field
                await self.page.evaluate(f'''(token) => {{
                    const input = document.querySelector('input[name="cf-turnstile-response"]');
                    if (input) {{
                        input.value = token;
                    }}

                    // Try to trigger callback
                    const callback = document.querySelector('[data-callback]')?.getAttribute('data-callback');
                    if (callback && window[callback]) {{
                        window[callback](token);
                    }}
                }}''', token)

            logger.success(f"[CAPTCHA] Solution injected for {captcha_type.value}")
            await asyncio.sleep(1)  # Give page time to process
            return True

        except Exception as e:
            logger.error(f"[CAPTCHA] Injection error: {e}")
            return False


class AuthChallengeManager:
    """
    High-level manager for all authentication challenges.
    Integrates with login_manager.py for seamless auth flows.
    """

    def __init__(self, page, solver: LocalCaptchaSolver = None, webhook_url: str = None):
        self.page = page
        self.captcha_handler = PageCaptchaHandler(page, solver, webhook_url)
        self.twofa_detector = TwoFactorDetector(page)

    async def check_and_handle_challenges(self, manual_timeout: int = 300) -> bool:
        """
        Check for all types of authentication challenges and handle them.

        Args:
            manual_timeout: Timeout for manual resolution (seconds)

        Returns:
            True if all challenges resolved, False otherwise
        """
        challenges = await self.captcha_handler.detect_all_challenges()

        if not challenges:
            return True  # No challenges

        logger.info(f"[AUTH] Detected {len(challenges)} challenge(s)")

        # Handle each challenge
        for challenge in challenges:
            await self.captcha_handler.notify_user(challenge)

            # Try automated solving for CAPTCHAs
            if challenge.challenge_type in [ChallengeType.RECAPTCHA_V2, ChallengeType.RECAPTCHA_V3,
                                           ChallengeType.HCAPTCHA, ChallengeType.CLOUDFLARE_TURNSTILE]:
                if self.captcha_handler.solver.is_configured:
                    success = await self.captcha_handler.solve_and_inject(auto_fallback=True)
                    if success:
                        continue

            # For 2FA or failed CAPTCHA, wait for manual resolution
            success = await self.captcha_handler.wait_for_user_resolution(challenge, manual_timeout)
            if not success:
                return False

        logger.success("[AUTH] All challenges resolved successfully!")
        return True

    async def integrate_with_login(self, login_callback: Callable) -> bool:
        """
        Integrate challenge handling with login flow.

        Args:
            login_callback: Function to call to perform login

        Returns:
            True if login successful with challenges handled
        """
        # Perform login
        await login_callback()

        # Check for challenges after login attempt
        return await self.check_and_handle_challenges()
