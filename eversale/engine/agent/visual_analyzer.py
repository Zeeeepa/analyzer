"""
Visual Analyzer - Real multimodal page understanding.

Problem: llama3.1 is text-only, so "multimodal" methods were fake.

Solution:
1. Use vision model (llava, bakllava) if available locally
2. Fall back to DOM + accessibility analysis
3. Convert screenshots to structured text descriptions

This module provides REAL visual understanding or honest fallback.
"""

import base64
import re
import json
from pathlib import Path
from typing import Dict, Optional, Any
from loguru import logger

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False


class VisualAnalyzer:
    """
    Analyze page visuals using vision models or fallback methods.

    Supported vision models (checked in order):
    - llava:7b, llava:13b
    - bakllava
    - moondream
    - llama3.2-vision (if available)
    """

    # Vision models to check for (in priority order)
    VISION_MODELS = [
        'llava:7b',
        'llava:13b',
        'llava',
        'bakllava',
        'moondream',
        'llama3.2-vision:11b',
        'llama3.2-vision',
    ]

    def __init__(self, config: dict = None):
        self.config = config or {}

        # Check for vision model
        self.vision_model = self._detect_vision_model()
        self.has_vision = self.vision_model is not None

        if self.has_vision:
            logger.info(f"[VISUAL] Vision model available: {self.vision_model}")
        else:
            logger.warning("[VISUAL] No vision model found - using DOM fallback")

        # Stats
        self.stats = {
            'vision_analyses': 0,
            'fallback_analyses': 0,
            'errors': 0
        }

    def _detect_vision_model(self) -> Optional[str]:
        """Check if any vision model is available locally."""
        if not OLLAMA_AVAILABLE:
            return None

        # Check config override first
        config_model = self.config.get('llm', {}).get('vision_model')
        if config_model:
            try:
                ollama.show(config_model)
                return config_model
            except Exception:
                pass

        # Check for known vision models (auto-detect even without config)
        try:
            available = ollama.list()

            # Handle both old dict format and new object format
            models = available.get('models', []) if isinstance(available, dict) else getattr(available, 'models', [])

            model_names = []
            for m in models:
                # Try object attribute first, then dict key
                name = getattr(m, 'model', None) or m.get('model', '') if isinstance(m, dict) else getattr(m, 'model', '')
                if name:
                    model_names.append(name)

            # Also check for minicpm-v specifically (our recommended model)
            check_models = ['minicpm-v'] + list(self.VISION_MODELS)

            for vision_model in check_models:
                for available_name in model_names:
                    if vision_model in available_name.lower():
                        return available_name
        except Exception as e:
            logger.error(f"[VISUAL] Could not list ollama models: {e}")

        return None

    async def analyze_screenshot(self,
                                  screenshot_path: str,
                                  task_context: str,
                                  dom_fallback: str = None) -> Dict:
        """
        Analyze a screenshot to understand page state.

        If vision model available: Use actual image analysis
        Otherwise: Return DOM-based analysis

        Returns dict with:
        - elements: List of identified elements
        - suggested_action: Next action to take
        - reasoning: Why this action
        - confidence: 0-1 confidence score
        """

        if self.has_vision and Path(screenshot_path).exists():
            return await self._analyze_with_vision(screenshot_path, task_context)
        else:
            return self._analyze_with_dom_fallback(dom_fallback, task_context)

    async def _analyze_with_vision(self, screenshot_path: str, task_context: str) -> Dict:
        """Analyze screenshot using vision model."""
        self.stats['vision_analyses'] += 1

        try:
            # Read and encode image
            with open(screenshot_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            prompt = f"""Analyze this webpage screenshot for the following task:

TASK: {task_context}

Please identify:
1. Key interactive elements (buttons, links, inputs) and their approximate positions
2. The current state of the page (logged in/out, loaded content, etc.)
3. What action should be taken next to accomplish the task

Return your analysis as JSON:
{{
  "page_state": "description of current page",
  "elements": [
    {{"type": "button/link/input", "text": "...", "location": "top/middle/bottom"}},
    ...
  ],
  "suggested_action": "click/type/scroll/navigate",
  "target_description": "description of element to interact with",
  "reasoning": "why this action",
  "confidence": 0.8
}}"""

            response = ollama.generate(
                model=self.vision_model,
                prompt=prompt,
                images=[image_data],
                options={'temperature': 0.1}
            )

            # Parse response
            result = self._parse_vision_response(response['response'])
            result['method'] = 'vision'
            result['model'] = self.vision_model

            return result

        except Exception as e:
            logger.error(f"[VISUAL] Vision analysis failed: {e}")
            self.stats['errors'] += 1
            return {
                'error': str(e),
                'method': 'vision_failed',
                'elements': [],
                'suggested_action': 'extract',
                'reasoning': 'Vision analysis failed, fallback to extraction',
                'confidence': 0.3
            }

    def _analyze_with_dom_fallback(self, dom_info: str, task_context: str) -> Dict:
        """
        Analyze page using DOM information when no vision model.

        This is honest about its limitations - it can't see images,
        styling, or layout. But it CAN see:
        - Text content
        - Element structure
        - Selectors
        """
        self.stats['fallback_analyses'] += 1

        if not dom_info:
            return {
                'method': 'fallback_no_dom',
                'elements': [],
                'suggested_action': 'navigate',
                'reasoning': 'No page info available',
                'confidence': 0.1
            }

        # Parse DOM info to extract elements
        elements = []

        # Look for buttons
        button_matches = re.findall(r'BUTTONS?:?\s*(.*?)(?=LINKS?:|INPUTS?:|DATA|$)', dom_info, re.DOTALL | re.IGNORECASE)
        if button_matches:
            for line in button_matches[0].split('\n'):
                if '→' in line:
                    parts = line.split('→')
                    text = parts[0].replace('•', '').strip()
                    selector = parts[1].strip() if len(parts) > 1 else ''
                    if text:
                        elements.append({'type': 'button', 'text': text[:50], 'selector': selector})

        # Look for links
        link_matches = re.findall(r'LINKS?:?\s*(.*?)(?=BUTTONS?:|INPUTS?:|DATA|$)', dom_info, re.DOTALL | re.IGNORECASE)
        if link_matches:
            for line in link_matches[0].split('\n'):
                if '→' in line:
                    parts = line.split('→')
                    text = parts[0].replace('•', '').strip()
                    selector = parts[1].strip() if len(parts) > 1 else ''
                    if text:
                        elements.append({'type': 'link', 'text': text[:50], 'selector': selector})

        # Look for inputs
        input_matches = re.findall(r'INPUTS?:?\s*(.*?)(?=BUTTONS?:|LINKS?:|DATA|$)', dom_info, re.DOTALL | re.IGNORECASE)
        if input_matches:
            for line in input_matches[0].split('\n'):
                if '→' in line:
                    parts = line.split('→')
                    name = parts[0].replace('•', '').strip()
                    selector = parts[1].strip() if len(parts) > 1 else ''
                    if name:
                        elements.append({'type': 'input', 'name': name[:50], 'selector': selector})

        # Determine suggested action based on task
        task_lower = task_context.lower()
        suggested_action = 'extract'
        target_description = 'page content'
        reasoning = 'Default to extraction'

        if 'search' in task_lower or 'find' in task_lower:
            # Look for search input
            search_inputs = [e for e in elements if e.get('type') == 'input' and
                          any(kw in e.get('name', '').lower() for kw in ['search', 'query', 'q'])]
            if search_inputs:
                suggested_action = 'type'
                target_description = search_inputs[0].get('selector', 'search input')
                reasoning = 'Found search input, should type search query'

        elif 'click' in task_lower or 'go to' in task_lower or 'navigate' in task_lower:
            suggested_action = 'click'
            if elements:
                target_description = elements[0].get('selector', 'first element')
            reasoning = 'Task requires clicking/navigation'

        elif 'fill' in task_lower or 'enter' in task_lower or 'type' in task_lower:
            suggested_action = 'type'
            inputs = [e for e in elements if e.get('type') == 'input']
            if inputs:
                target_description = inputs[0].get('selector', 'input field')
            reasoning = 'Task requires filling form'

        return {
            'method': 'dom_fallback',
            'limitation': 'Cannot see images, styling, or visual layout',
            'elements': elements[:20],  # Limit
            'suggested_action': suggested_action,
            'target_description': target_description,
            'reasoning': reasoning,
            'confidence': 0.5  # Lower confidence for DOM-only
        }

    def _parse_vision_response(self, response: str) -> Dict:
        """Parse JSON from vision model response."""
        try:
            # Try to find JSON in response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

        # Fallback: extract what we can
        return {
            'page_state': response[:200],
            'elements': [],
            'suggested_action': 'extract',
            'reasoning': 'Could not parse vision response',
            'confidence': 0.4
        }

    def describe_page_for_text_model(self,
                                      dom_info: str,
                                      screenshot_exists: bool = False) -> str:
        """
        Create text description of page for text-only model.

        This is called when we need to describe visual state
        to a model that can't see images.
        """
        lines = [
            "PAGE DESCRIPTION (converted from visual state):",
            ""
        ]

        if screenshot_exists and not self.has_vision:
            lines.append("NOTE: Screenshot exists but no vision model available.")
            lines.append("Using DOM structure instead of visual analysis.")
            lines.append("")

        if dom_info:
            lines.append(dom_info)
        else:
            lines.append("No page structure available.")

        return "\n".join(lines)

    def get_stats(self) -> Dict:
        """Get analysis stats."""
        return {
            **self.stats,
            'has_vision': self.has_vision,
            'vision_model': self.vision_model
        }


# Factory
def create_visual_analyzer(config: dict = None) -> VisualAnalyzer:
    """Create a visual analyzer instance."""
    return VisualAnalyzer(config)


# Singleton
_analyzer = None

def get_visual_analyzer(config: dict = None) -> VisualAnalyzer:
    """Get global visual analyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = VisualAnalyzer(config)
    return _analyzer
