"""
Vision Analyzer - Analyze images using local vision model.

Uses Ollama's vision models (minicpm-v, llava, etc.) to describe and analyze images.
"""

import base64
import os
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
from loguru import logger

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False


@dataclass
class VisionResult:
    """Result from vision analysis."""
    success: bool
    description: str = ""
    details: Dict[str, Any] = None
    error: str = ""


class VisionAnalyzer:
    """
    Analyze images using local vision model.
    """

    def __init__(self, model: str = "minicpm-v"):
        self.model = model
        fallback_env = os.environ.get("EVERSALE_VISION_FALLBACK", "1").lower()
        self.fallback_enabled = fallback_env in {"1", "true", "yes"}
        self.available = OLLAMA_AVAILABLE or self.fallback_enabled

    def _encode_image(self, image_path: str) -> Optional[str]:
        """Encode image to base64."""
        try:
            path = Path(image_path)
            if not path.exists():
                logger.error(f"Image not found: {image_path}")
                return None

            with open(path, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to encode image: {e}")
            return None

    def analyze(self, image_path: str, prompt: str = None) -> VisionResult:
        """
        Analyze an image with optional custom prompt.

        Args:
            image_path: Path to image file
            prompt: Custom prompt (default: general description)
        """
        if not OLLAMA_AVAILABLE:
            if self.fallback_enabled:
                logger.warning("Vision fallback active - returning heuristic description.")
                return VisionResult(
                    success=True,
                    description=self._fallback_description(image_path, prompt)
                )
            return VisionResult(
                success=False,
                error="Ollama not available for vision analysis"
            )

        b64 = self._encode_image(image_path)
        if not b64:
            return VisionResult(
                success=False,
                error=f"Could not read image: {image_path}"
            )

        if not prompt:
            prompt = "Describe this image in detail. What do you see?"

        try:
            response = ollama.chat(
                model=self.model,
                messages=[{
                    'role': 'user',
                    'content': prompt,
                    'images': [b64]
                }],
                options={'temperature': 0.3}
            )

            content = response.get('message', {}).get('content', '')

            return VisionResult(
                success=True,
                description=content.strip()
            )

        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            return VisionResult(success=False, error=str(e))

    def analyze_product(self, image_path: str) -> VisionResult:
        """
        Analyze a product image for e-commerce.

        Returns detailed product information suitable for listings.
        """
        prompt = """Analyze this product image for an e-commerce listing.

Describe:
1. What is the product?
2. Color, size, material if visible
3. Key features visible in the image
4. Condition (new, used, etc.)
5. Any brand/logo visible
6. Suggested target audience

Be specific and detailed for product listing purposes."""

        result = self.analyze(image_path, prompt)

        if result.success:
            # Try to extract structured details
            result.details = self._extract_product_details(result.description)

        return result

    def _extract_product_details(self, description: str) -> Dict[str, Any]:
        """Extract structured details from product description."""
        details = {
            'raw_description': description,
            'keywords': [],
            'features': []
        }

        # Extract potential keywords
        import re
        words = re.findall(r'\b[A-Za-z]{4,}\b', description)
        # Filter to unique, lowercase
        seen = set()
        for w in words:
            wl = w.lower()
            if wl not in seen and wl not in ['this', 'that', 'with', 'from', 'have', 'been', 'would', 'could', 'should']:
                seen.add(wl)
                details['keywords'].append(wl)
                if len(details['keywords']) >= 10:
                    break

        # Extract features (lines starting with numbers or bullets)
        lines = description.split('\n')
        for line in lines:
            line = line.strip()
            if line and (line[0].isdigit() or line[0] in '-•*'):
                # Clean up the line
                clean = re.sub(r'^[\d\.\-•\*\s]+', '', line).strip()
                if clean and len(clean) > 5:
                    details['features'].append(clean)

        return details

    def compare_images(self, image_paths: list, prompt: str = None) -> VisionResult:
        """
        Compare multiple images.

        Args:
            image_paths: List of image paths
            prompt: Custom comparison prompt
        """
        if not self.available:
            if not self.fallback_enabled:
                return VisionResult(
                    success=False,
                    error="Ollama not available for vision analysis"
                )
            return VisionResult(
                success=True,
                description=self._fallback_description(", ".join(Path(p).name for p in image_paths), prompt)
            )

        # Encode all images
        images = []
        for path in image_paths:
            b64 = self._encode_image(path)
            if b64:
                images.append(b64)

        if not images:
            return VisionResult(
                success=False,
                error="No valid images to compare"
            )

        if not prompt:
            prompt = f"Compare these {len(images)} images. What are the similarities and differences?"

        try:
            response = ollama.chat(
                model=self.model,
                messages=[{
                    'role': 'user',
                    'content': prompt,
                    'images': images
                }],
                options={'temperature': 0.3}
            )

            content = response.get('message', {}).get('content', '')

            return VisionResult(
                success=True,
                description=content.strip()
            )

        except Exception as e:
            logger.error(f"Image comparison failed: {e}")
            return VisionResult(success=False, error=str(e))

    def extract_text(self, image_path: str) -> VisionResult:
        """
        Extract text from an image (OCR-like).
        """
        prompt = """Extract all visible text from this image.
List each piece of text on a separate line.
Include: labels, titles, prices, descriptions, any writing.
Be thorough - don't miss any text."""

        return self.analyze(image_path, prompt)

    def identify_objects(self, image_path: str) -> VisionResult:
        """
        Identify and list objects in an image.
        """
        prompt = """List all objects you can identify in this image.
Format: one object per line with a brief description.
Example:
- Red chair (wooden, vintage style)
- White coffee mug (ceramic, with handle)"""

        return self.analyze(image_path, prompt)

    def _fallback_description(self, image_path: str, prompt: Optional[str]) -> str:
        """Return a simple descriptive placeholder when no vision backend is available."""
        target = image_path or "image"
        desc = f"(minicpm-v fallback) Vision model unavailable; cannot analyze {target} pixels directly."
        if prompt:
            desc += f" Prompt requested: {prompt}"
        return desc


# Singleton instance
vision = VisionAnalyzer()


def analyze_image(image_path: str, prompt: str = None) -> str:
    """Quick function to analyze an image."""
    result = vision.analyze(image_path, prompt)
    return result.description if result.success else f"Error: {result.error}"


def analyze_product_image(image_path: str) -> Dict:
    """Quick function to analyze a product image."""
    result = vision.analyze_product(image_path)
    if result.success:
        return {
            'description': result.description,
            'details': result.details
        }
    return {'error': result.error}
