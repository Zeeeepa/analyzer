"""
Training Enhancements - 6 Major Improvements for SDR-1

1. Isolated Browser Contexts - Each parallel task gets its own browser
2. Vision Verification - Use minicpm-v to verify screenshots
3. LoRA Fine-tuning - Train on verified successes
4. Quality Reward Signals - Not just pass/fail, but quality scores
5. Curriculum Learning - Progressive difficulty
6. Active Learning - Focus on failure modes

This module provides the infrastructure for all 6 improvements.
"""

import asyncio
import json
import re
import random
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from loguru import logger

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False


# =============================================================================
# 1. ISOLATED BROWSER CONTEXTS - Each parallel task gets its own browser
# =============================================================================

class BrowserContextPool:
    """
    Manages a pool of isolated browser contexts for parallel task execution.

    Problem: All parallel tasks were sharing one browser/page, causing URL collision.
    Solution: Each task gets its own isolated browser context.
    """

    def __init__(self, max_contexts: int = 5):
        self.max_contexts = max_contexts
        self.contexts: Dict[str, Any] = {}  # context_id -> context info
        self.playwright = None
        self.browser = None
        self._lock = asyncio.Lock()

    async def initialize(self, headless: bool = True):
        """Initialize the browser for context pooling."""
        from playwright.async_api import async_playwright

        self.playwright = await async_playwright().start()

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ]

        self.browser = await self.playwright.chromium.launch(
            headless=headless,
            args=launch_args
        )

        logger.info(f"[POOL] Browser initialized, max {self.max_contexts} contexts")

    async def acquire_context(self, task_id: str) -> Tuple[Any, Any]:
        """
        Acquire an isolated browser context for a task.

        Returns:
            Tuple of (context, page)
        """
        async with self._lock:
            # Check if we already have a context for this task
            if task_id in self.contexts:
                ctx_info = self.contexts[task_id]
                return ctx_info['context'], ctx_info['page']

            # Check if we're at capacity
            if len(self.contexts) >= self.max_contexts:
                # Release oldest context
                oldest_id = next(iter(self.contexts))
                await self.release_context(oldest_id)

            # Create new isolated context
            context_options = {
                "viewport": {"width": 1920, "height": 1080},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            context = await self.browser.new_context(**context_options)
            page = await context.new_page()

            self.contexts[task_id] = {
                'context': context,
                'page': page,
                'created': datetime.now().isoformat(),
                'url': None
            }

            logger.info(f"[POOL] Created isolated context for task {task_id[:8]}")
            return context, page

    async def release_context(self, task_id: str):
        """Release a browser context back to the pool."""
        async with self._lock:
            if task_id in self.contexts:
                ctx_info = self.contexts[task_id]
                try:
                    await ctx_info['context'].close()
                except:
                    pass
                del self.contexts[task_id]
                logger.debug(f"[POOL] Released context {task_id[:8]}")

    async def release_all(self):
        """Release all contexts."""
        for task_id in list(self.contexts.keys()):
            await self.release_context(task_id)

    async def shutdown(self):
        """Shutdown the browser pool."""
        await self.release_all()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("[POOL] Browser pool shutdown complete")

    def get_stats(self) -> Dict:
        """Get pool statistics."""
        return {
            'active_contexts': len(self.contexts),
            'max_contexts': self.max_contexts,
            'context_ids': list(self.contexts.keys())
        }


class IsolatedTaskExecutor:
    """
    Executes tasks in isolated browser contexts.

    Wraps the existing brain/MCP to use isolated contexts.
    """

    def __init__(self, pool: BrowserContextPool, config: dict):
        self.pool = pool
        self.config = config

    async def execute_task(self, task_id: str, task_prompt: str, brain_factory) -> Dict:
        """
        Execute a task in an isolated browser context.

        Args:
            task_id: Unique identifier for this task
            task_prompt: The task to execute
            brain_factory: Function that creates a brain with a given page

        Returns:
            Dict with result, context info, etc.
        """
        context, page = await self.pool.acquire_context(task_id)

        try:
            # Create MCP client that uses this specific page
            from agent.mcp_client import MCPClient
            mcp = MCPClient()

            # Override the page in the playwright client
            if 'playwright' in mcp.servers:
                mcp.servers['playwright']['client'].page = page
                mcp.servers['playwright']['client'].context = context

            # Create brain with this MCP
            brain = brain_factory(self.config, mcp)

            # Execute task
            start_time = datetime.now()
            result = await brain.run(task_prompt)
            elapsed = (datetime.now() - start_time).total_seconds()

            # Get final URL for verification
            final_url = page.url

            return {
                'success': True,
                'result': result,
                'context_id': task_id,
                'final_url': final_url,
                'elapsed': elapsed,
                'stats': brain.get_stats()
            }

        except Exception as e:
            logger.error(f"[ISOLATED] Task {task_id[:8]} failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'context_id': task_id
            }

        finally:
            # Release context after task completes
            await self.pool.release_context(task_id)


# =============================================================================
# 2. VISION VERIFICATION - Use minicpm-v to verify screenshots
# =============================================================================

class VisionVerifier:
    """
    Uses vision model (minicpm-v) to verify task completion from screenshots.

    Problem: Text-only verification misses visual cues (error modals, wrong pages).
    Solution: Use vision model to analyze screenshots and verify success.
    """

    VISION_MODELS = ['minicpm-v', 'llava:7b', 'llava:13b', 'llava']

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.vision_model = self._detect_vision_model()
        self.has_vision = self.vision_model is not None

        if self.has_vision:
            logger.info(f"[VISION] Using {self.vision_model} for verification")
        else:
            logger.warning("[VISION] No vision model - using text-only verification")

        self.stats = {
            'verifications': 0,
            'passed': 0,
            'failed': 0,
            'vision_used': 0,
            'fallback_used': 0
        }

    def _detect_vision_model(self) -> Optional[str]:
        """Detect available vision model."""
        if not OLLAMA_AVAILABLE:
            return None

        # Check config first
        config_model = self.config.get('llm', {}).get('vision_model')
        if config_model:
            try:
                ollama.show(config_model)
                return config_model
            except:
                pass

        # Auto-detect
        try:
            available = ollama.list()
            models = getattr(available, 'models', []) if hasattr(available, 'models') else available.get('models', [])

            model_names = []
            for m in models:
                name = getattr(m, 'model', None) or (m.get('model', '') if isinstance(m, dict) else '')
                if name:
                    model_names.append(name)

            for vision_model in self.VISION_MODELS:
                for available_name in model_names:
                    if vision_model in available_name.lower():
                        return available_name
        except:
            pass

        return None

    async def verify_task_completion(self,
                                      screenshot_path: str,
                                      task_prompt: str,
                                      claimed_output: str,
                                      page_url: str = None) -> Dict:
        """
        Verify task completion using vision model.

        Args:
            screenshot_path: Path to screenshot of final page state
            task_prompt: Original task description
            claimed_output: What the agent claims to have done
            page_url: Current URL for additional verification

        Returns:
            Dict with verification results
        """
        self.stats['verifications'] += 1

        if self.has_vision and Path(screenshot_path).exists():
            return await self._verify_with_vision(
                screenshot_path, task_prompt, claimed_output, page_url
            )
        else:
            return self._verify_without_vision(
                task_prompt, claimed_output, page_url
            )

    async def _verify_with_vision(self,
                                   screenshot_path: str,
                                   task_prompt: str,
                                   claimed_output: str,
                                   page_url: str) -> Dict:
        """Verify using vision model."""
        self.stats['vision_used'] += 1

        import base64

        try:
            with open(screenshot_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            prompt = f"""Analyze this screenshot to verify if a web automation task was completed successfully.

TASK: {task_prompt}

AGENT'S CLAIM: {claimed_output[:500]}

CURRENT URL: {page_url or 'Unknown'}

Please analyze the screenshot and determine:
1. Does the page show what the task asked for?
2. Are there any error messages, CAPTCHAs, or login walls visible?
3. Does the claimed output match what's visible on screen?

Return JSON:
{{
  "task_completed": true/false,
  "page_matches_task": true/false,
  "errors_visible": true/false,
  "error_description": "description if errors visible",
  "output_matches_screen": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}"""

            response = ollama.generate(
                model=self.vision_model,
                prompt=prompt,
                images=[image_data],
                options={'temperature': 0.1}
            )

            # Parse response
            result = self._parse_verification_response(response['response'])
            result['method'] = 'vision'
            result['model'] = self.vision_model

            if result.get('task_completed', False) and result.get('confidence', 0) > 0.6:
                self.stats['passed'] += 1
            else:
                self.stats['failed'] += 1

            return result

        except Exception as e:
            logger.error(f"[VISION] Verification failed: {e}")
            return self._verify_without_vision(task_prompt, claimed_output, page_url)

    def _verify_without_vision(self,
                                task_prompt: str,
                                claimed_output: str,
                                page_url: str) -> Dict:
        """Fallback verification without vision."""
        self.stats['fallback_used'] += 1

        # Basic heuristics
        is_error = any(ind in claimed_output.lower() for ind in
                       ['error', 'failed', 'could not', 'unable', 'timeout'])

        has_content = len(claimed_output) > 50 and not is_error

        # URL check
        url_matches = True
        if page_url:
            task_lower = task_prompt.lower()
            url_lower = page_url.lower()

            # Extract expected domain from task
            url_match = re.search(r'(?:https?://)?(?:www\.)?([a-z0-9\-]+\.[a-z]{2,})', task_lower)
            if url_match:
                expected_domain = url_match.group(1)
                url_matches = expected_domain in url_lower

        passed = has_content and url_matches and not is_error

        if passed:
            self.stats['passed'] += 1
        else:
            self.stats['failed'] += 1

        return {
            'task_completed': passed,
            'page_matches_task': url_matches,
            'errors_visible': is_error,
            'output_matches_screen': has_content,
            'confidence': 0.5,  # Lower confidence without vision
            'method': 'heuristic',
            'reasoning': f"URL match: {url_matches}, Has content: {has_content}, Is error: {is_error}"
        }

    def _parse_verification_response(self, response: str) -> Dict:
        """Parse JSON from vision model response."""
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group(0))
        except:
            pass

        # Fallback parsing
        response_lower = response.lower()
        return {
            'task_completed': 'complete' in response_lower or 'success' in response_lower,
            'confidence': 0.5,
            'reasoning': response[:200]
        }

    def get_stats(self) -> Dict:
        """Get verification stats."""
        return {
            **self.stats,
            'has_vision': self.has_vision,
            'vision_model': self.vision_model,
            'pass_rate': self.stats['passed'] / max(1, self.stats['verifications'])
        }


# =============================================================================
# 3. LORA FINE-TUNING - Train on verified successes
# =============================================================================

@dataclass
class TrainingExample:
    """A single training example for fine-tuning."""
    task_prompt: str
    successful_output: str
    tool_calls: List[Dict]
    verification_score: float
    category: str
    domain: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_chat_format(self) -> Dict:
        """Convert to chat format for fine-tuning."""
        return {
            "messages": [
                {"role": "system", "content": "You are an expert web automation agent."},
                {"role": "user", "content": self.task_prompt},
                {"role": "assistant", "content": self.successful_output}
            ]
        }

    def to_instruct_format(self) -> str:
        """Convert to instruction format."""
        return f"""### Instruction:
{self.task_prompt}

### Response:
{self.successful_output}"""


class LoRATrainingManager:
    """
    Manages LoRA fine-tuning on verified successful examples.

    Problem: Model doesn't learn from its successes.
    Solution: Collect verified successful examples and fine-tune with LoRA.
    """

    def __init__(self, storage_dir: Path = None):
        self.storage_dir = storage_dir or Path("training/lora_data")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.examples_file = self.storage_dir / "training_examples.json"
        self.examples: List[TrainingExample] = []

        # Thresholds (must be set before _load_examples)
        self.min_verification_score = 0.7  # Only use high-quality examples
        self.min_examples_for_training = 50  # Minimum examples before training
        self.max_examples = 1000  # Cap to prevent memory issues

        self._load_examples()

        self.stats = {
            'examples_collected': len(self.examples),
            'examples_used_for_training': 0,
            'training_runs': 0,
            'last_training': None
        }

    def _load_examples(self):
        """Load existing training examples."""
        if self.examples_file.exists():
            try:
                with open(self.examples_file) as f:
                    data = json.load(f)
                    self.examples = [TrainingExample(**ex) for ex in data[-self.max_examples:]]
            except Exception as e:
                logger.warning(f"Could not load training examples: {e}")

    def _save_examples(self):
        """Save training examples to disk."""
        try:
            data = [asdict(ex) for ex in self.examples[-self.max_examples:]]
            with open(self.examples_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save training examples: {e}")

    def add_example(self,
                    task_prompt: str,
                    output: str,
                    tool_calls: List[Dict],
                    verification_result: Dict,
                    category: str,
                    domain: str):
        """
        Add a verified successful example for training.

        Only adds if verification score is above threshold.
        """
        score = verification_result.get('confidence', 0)

        if score < self.min_verification_score:
            logger.debug(f"[LORA] Skipping example with low score: {score:.2f}")
            return False

        if not verification_result.get('task_completed', False):
            logger.debug("[LORA] Skipping incomplete task")
            return False

        example = TrainingExample(
            task_prompt=task_prompt,
            successful_output=output[:2000],  # Limit size
            tool_calls=tool_calls[:20],  # Limit tool calls
            verification_score=score,
            category=category,
            domain=domain
        )

        self.examples.append(example)
        self._save_examples()
        self.stats['examples_collected'] = len(self.examples)

        logger.info(f"[LORA] Added training example (score: {score:.2f}, total: {len(self.examples)})")
        return True

    def export_training_data(self, format: str = 'chat') -> Path:
        """
        Export training data for fine-tuning.

        Args:
            format: 'chat' for chat format, 'instruct' for instruction format

        Returns:
            Path to exported file
        """
        if format == 'chat':
            output_file = self.storage_dir / "training_chat.jsonl"
            with open(output_file, 'w') as f:
                for ex in self.examples:
                    if ex.verification_score >= self.min_verification_score:
                        f.write(json.dumps(ex.to_chat_format()) + '\n')
        else:
            output_file = self.storage_dir / "training_instruct.txt"
            with open(output_file, 'w') as f:
                for ex in self.examples:
                    if ex.verification_score >= self.min_verification_score:
                        f.write(ex.to_instruct_format() + '\n\n')

        logger.info(f"[LORA] Exported {len(self.examples)} examples to {output_file}")
        return output_file

    def should_trigger_training(self) -> bool:
        """Check if we have enough examples to trigger training."""
        high_quality = sum(1 for ex in self.examples if ex.verification_score >= self.min_verification_score)
        return high_quality >= self.min_examples_for_training

    async def run_lora_training(self, base_model: str = 'llama3.1:8b-instruct-q8_0') -> Dict:
        """
        Run LoRA fine-tuning using Ollama's create API.

        Note: This requires Ollama to support LoRA training.
        For now, we export the data for external training.
        """
        if not self.should_trigger_training():
            return {'status': 'skipped', 'reason': 'not enough examples'}

        # Export training data
        training_file = self.export_training_data(format='chat')

        # Create Modelfile for fine-tuning
        modelfile_content = f"""FROM {base_model}

# Fine-tuned on verified successful web automation examples
PARAMETER temperature 0.1
PARAMETER num_ctx 4096

SYSTEM You are an expert web automation agent trained on verified successful task completions.
"""

        modelfile_path = self.storage_dir / "Modelfile.lora"
        modelfile_path.write_text(modelfile_content)

        self.stats['training_runs'] += 1
        self.stats['last_training'] = datetime.now().isoformat()
        self.stats['examples_used_for_training'] = len(self.examples)

        # Return info for manual training
        return {
            'status': 'ready',
            'training_file': str(training_file),
            'modelfile': str(modelfile_path),
            'examples': len(self.examples),
            'high_quality_examples': sum(1 for ex in self.examples if ex.verification_score >= self.min_verification_score),
            'instructions': f"""
To fine-tune with LoRA:

1. Using Ollama (if supported):
   ollama create sdr1-finetuned -f {modelfile_path}

2. Using external tools (unsloth, axolotl):
   - Training data: {training_file}
   - Base model: {base_model}
   - Format: Chat/JSONL
"""
        }

    def get_stats(self) -> Dict:
        """Get training stats."""
        categories = {}
        domains = {}

        for ex in self.examples:
            categories[ex.category] = categories.get(ex.category, 0) + 1
            domains[ex.domain] = domains.get(ex.domain, 0) + 1

        return {
            **self.stats,
            'categories': categories,
            'domains': dict(list(domains.items())[:10]),
            'avg_verification_score': sum(ex.verification_score for ex in self.examples) / max(1, len(self.examples)),
            'ready_for_training': self.should_trigger_training()
        }


# =============================================================================
# 4. QUALITY REWARD SIGNALS - Not just pass/fail
# =============================================================================

@dataclass
class QualityScore:
    """Multi-dimensional quality score for a task completion."""
    overall: float  # 0.0 to 1.0

    # Dimensions
    task_completion: float  # Did it complete the task?
    data_quality: float  # Quality of extracted data
    efficiency: float  # How efficiently (time, tool calls)?
    correctness: float  # Was the output correct?
    robustness: float  # Did it handle edge cases?

    # Breakdown
    breakdown: Dict = field(default_factory=dict)

    def to_reward(self) -> float:
        """Convert to single reward signal."""
        return self.overall


class QualityScorer:
    """
    Calculates multi-dimensional quality scores for task completions.

    Problem: Pass/fail doesn't capture nuance - a fast correct completion
             should score higher than a slow correct one.
    Solution: Multi-dimensional scoring with weighted components.
    """

    # Scoring weights
    WEIGHTS = {
        'task_completion': 0.35,
        'data_quality': 0.25,
        'efficiency': 0.15,
        'correctness': 0.15,
        'robustness': 0.10
    }

    def __init__(self):
        self.scores: List[QualityScore] = []
        self.stats = {
            'total_scored': 0,
            'avg_overall': 0.0,
            'avg_by_dimension': {}
        }

    def score_completion(self,
                         task_prompt: str,
                         output: str,
                         verification_result: Dict,
                         elapsed_seconds: float,
                         tool_calls: int,
                         page_content: str = None) -> QualityScore:
        """
        Calculate quality score for a task completion.

        Args:
            task_prompt: Original task
            output: Agent's output
            verification_result: From vision/ground truth verification
            elapsed_seconds: Time taken
            tool_calls: Number of tool calls made
            page_content: Page content for data quality check

        Returns:
            QualityScore with multi-dimensional breakdown
        """

        # 1. Task Completion Score (from verification)
        task_completion = 0.0
        if verification_result.get('task_completed', False):
            task_completion = verification_result.get('confidence', 0.5)

        # 2. Data Quality Score
        data_quality = self._score_data_quality(output, page_content, task_prompt)

        # 3. Efficiency Score (time and tool calls)
        efficiency = self._score_efficiency(elapsed_seconds, tool_calls)

        # 4. Correctness Score
        correctness = self._score_correctness(output, verification_result)

        # 5. Robustness Score
        robustness = self._score_robustness(output, verification_result)

        # Calculate weighted overall
        overall = (
            self.WEIGHTS['task_completion'] * task_completion +
            self.WEIGHTS['data_quality'] * data_quality +
            self.WEIGHTS['efficiency'] * efficiency +
            self.WEIGHTS['correctness'] * correctness +
            self.WEIGHTS['robustness'] * robustness
        )

        score = QualityScore(
            overall=overall,
            task_completion=task_completion,
            data_quality=data_quality,
            efficiency=efficiency,
            correctness=correctness,
            robustness=robustness,
            breakdown={
                'task_completed': verification_result.get('task_completed', False),
                'elapsed_seconds': elapsed_seconds,
                'tool_calls': tool_calls,
                'output_length': len(output)
            }
        )

        self.scores.append(score)
        self._update_stats()

        return score

    def _score_data_quality(self, output: str, page_content: str, task_prompt: str) -> float:
        """Score the quality of extracted/generated data."""
        score = 0.5  # Base score

        # Check for empty or error outputs
        if not output or len(output) < 20:
            return 0.1

        error_indicators = ['error', 'failed', 'could not', 'unable']
        if any(ind in output.lower() for ind in error_indicators):
            return 0.2

        # Check for data richness
        if len(output) > 200:
            score += 0.1
        if len(output) > 500:
            score += 0.1

        # Check if output contains structured data
        if any(c in output for c in ['{', '[', '|', '\t']):
            score += 0.1

        # Check if output has email/phone patterns (for extraction tasks)
        if re.search(r'[\w\.-]+@[\w\.-]+', output):
            score += 0.1
        if re.search(r'\+?[\d\-\(\)\s]{10,}', output):
            score += 0.05

        # Verify against page content if available
        if page_content:
            # Sample some words from output and check if they exist in page
            words = re.findall(r'\b\w{5,}\b', output)[:20]
            if words:
                matches = sum(1 for w in words if w.lower() in page_content.lower())
                match_rate = matches / len(words)
                score = score * 0.7 + match_rate * 0.3

        return min(1.0, score)

    def _score_efficiency(self, elapsed_seconds: float, tool_calls: int) -> float:
        """Score efficiency based on time and tool usage."""
        # Time scoring (faster = better, up to a point)
        if elapsed_seconds < 30:
            time_score = 1.0
        elif elapsed_seconds < 60:
            time_score = 0.9
        elif elapsed_seconds < 120:
            time_score = 0.7
        elif elapsed_seconds < 300:
            time_score = 0.5
        else:
            time_score = 0.3

        # Tool call scoring (fewer = better, but some are needed)
        if tool_calls <= 3:
            tool_score = 1.0
        elif tool_calls <= 5:
            tool_score = 0.9
        elif tool_calls <= 10:
            tool_score = 0.7
        elif tool_calls <= 20:
            tool_score = 0.5
        else:
            tool_score = 0.3

        return (time_score + tool_score) / 2

    def _score_correctness(self, output: str, verification_result: Dict) -> float:
        """Score correctness of the output."""
        base_score = 0.5

        if verification_result.get('output_matches_screen', False):
            base_score += 0.3

        if verification_result.get('page_matches_task', False):
            base_score += 0.2

        if not verification_result.get('errors_visible', True):
            base_score += 0.1

        return min(1.0, base_score)

    def _score_robustness(self, output: str, verification_result: Dict) -> float:
        """Score robustness (handling edge cases, retries, etc.)."""
        score = 0.5

        # Completed without errors
        if verification_result.get('task_completed', False):
            score += 0.3

        # No visible errors
        if not verification_result.get('errors_visible', True):
            score += 0.2

        return min(1.0, score)

    def _update_stats(self):
        """Update running statistics."""
        self.stats['total_scored'] = len(self.scores)

        if self.scores:
            self.stats['avg_overall'] = sum(s.overall for s in self.scores) / len(self.scores)
            self.stats['avg_by_dimension'] = {
                'task_completion': sum(s.task_completion for s in self.scores) / len(self.scores),
                'data_quality': sum(s.data_quality for s in self.scores) / len(self.scores),
                'efficiency': sum(s.efficiency for s in self.scores) / len(self.scores),
                'correctness': sum(s.correctness for s in self.scores) / len(self.scores),
                'robustness': sum(s.robustness for s in self.scores) / len(self.scores),
            }

    def get_stats(self) -> Dict:
        """Get scoring statistics."""
        return self.stats


# =============================================================================
# 5. CURRICULUM LEARNING - Progressive difficulty
# =============================================================================

class CurriculumManager:
    """
    Manages progressive difficulty in training tasks.

    Problem: Random tasks don't build skills progressively.
    Solution: Start easy, increase difficulty as model improves.
    """

    # Difficulty levels with corresponding task types
    DIFFICULTY_LEVELS = {
        1: {
            'name': 'Basic',
            'categories': ['navigation', 'screenshot'],
            'max_steps': 2,
            'sites': ['example.com', 'wikipedia.org', 'quotes.toscrape.com']
        },
        2: {
            'name': 'Simple',
            'categories': ['navigation', 'exploration', 'simple_extraction'],
            'max_steps': 3,
            'sites': ['quotes.toscrape.com', 'books.toscrape.com', 'wikipedia.org']
        },
        3: {
            'name': 'Intermediate',
            'categories': ['search', 'table_extraction', 'form_filling'],
            'max_steps': 5,
            'sites': ['github.com', 'news.ycombinator.com', 'reddit.com']
        },
        4: {
            'name': 'Advanced',
            'categories': ['sdr_prospecting', 'linkedin_style', 'multi_step'],
            'max_steps': 8,
            'sites': ['wellfound.com', 'crunchbase.com', 'linkedin.com']
        },
        5: {
            'name': 'Expert',
            'categories': ['complex_extraction', 'multi_site', 'auth_required'],
            'max_steps': 15,
            'sites': ['any']
        }
    }

    def __init__(self, storage_path: Path = None):
        self.storage_path = storage_path or Path("training/curriculum_state.json")
        self.current_level = 1
        self.level_history: List[Dict] = []

        # Performance tracking per level
        self.level_stats = {level: {'attempts': 0, 'successes': 0} for level in range(1, 6)}

        # Thresholds
        self.promotion_threshold = 0.7  # Success rate to move up
        self.demotion_threshold = 0.3  # Success rate to move down
        self.min_attempts_for_change = 10  # Min attempts before level change

        self._load_state()

    def _load_state(self):
        """Load curriculum state from disk."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path) as f:
                    state = json.load(f)
                    self.current_level = state.get('current_level', 1)
                    # Convert string keys back to integers (JSON converts int keys to strings)
                    loaded_stats = state.get('level_stats', {})
                    if loaded_stats:
                        self.level_stats = {
                            int(k): v for k, v in loaded_stats.items()
                        }
                    self.level_history = state.get('level_history', [])
            except:
                pass

    def _save_state(self):
        """Save curriculum state to disk."""
        try:
            state = {
                'current_level': self.current_level,
                'level_stats': self.level_stats,
                'level_history': self.level_history[-100:]  # Keep last 100
            }
            with open(self.storage_path, 'w') as f:
                json.dump(state, f, indent=2)
        except:
            pass

    def get_current_difficulty(self) -> Dict:
        """Get current difficulty settings."""
        return self.DIFFICULTY_LEVELS[self.current_level]

    def get_allowed_categories(self) -> List[str]:
        """Get task categories allowed at current level."""
        return self.DIFFICULTY_LEVELS[self.current_level]['categories']

    def get_allowed_sites(self) -> List[str]:
        """Get sites allowed at current level."""
        return self.DIFFICULTY_LEVELS[self.current_level]['sites']

    def record_attempt(self, success: bool, category: str = None) -> Dict:
        """
        Record a task attempt and potentially adjust difficulty.

        Returns:
            Dict with level change info if any
        """
        level = self.current_level
        self.level_stats[level]['attempts'] += 1
        if success:
            self.level_stats[level]['successes'] += 1

        self.level_history.append({
            'level': level,
            'success': success,
            'category': category,
            'timestamp': datetime.now().isoformat()
        })

        # Check if we should change level
        change_result = self._check_level_change()

        self._save_state()
        return change_result

    def _check_level_change(self) -> Dict:
        """Check if we should promote or demote."""
        level = self.current_level
        stats = self.level_stats[level]

        if stats['attempts'] < self.min_attempts_for_change:
            return {'changed': False, 'reason': 'not enough attempts'}

        success_rate = stats['successes'] / stats['attempts']

        # Check for promotion
        if success_rate >= self.promotion_threshold and level < 5:
            self.current_level = level + 1
            # Reset stats for new level
            self.level_stats[self.current_level] = {'attempts': 0, 'successes': 0}
            logger.info(f"[CURRICULUM] Promoted to level {self.current_level} ({self.DIFFICULTY_LEVELS[self.current_level]['name']})")
            return {
                'changed': True,
                'direction': 'up',
                'new_level': self.current_level,
                'old_success_rate': success_rate
            }

        # Check for demotion
        if success_rate <= self.demotion_threshold and level > 1:
            self.current_level = level - 1
            logger.info(f"[CURRICULUM] Demoted to level {self.current_level} ({self.DIFFICULTY_LEVELS[self.current_level]['name']})")
            return {
                'changed': True,
                'direction': 'down',
                'new_level': self.current_level,
                'old_success_rate': success_rate
            }

        return {'changed': False, 'success_rate': success_rate}

    def get_stats(self) -> Dict:
        """Get curriculum stats."""
        current_stats = self.level_stats[self.current_level]
        success_rate = current_stats['successes'] / max(1, current_stats['attempts'])

        return {
            'current_level': self.current_level,
            'level_name': self.DIFFICULTY_LEVELS[self.current_level]['name'],
            'current_success_rate': success_rate,
            'attempts_at_level': current_stats['attempts'],
            'level_stats': self.level_stats,
            'history_length': len(self.level_history)
        }


# =============================================================================
# 6. ACTIVE LEARNING - Focus on failure modes
# =============================================================================

@dataclass
class FailureMode:
    """Represents a type of failure the model makes."""
    category: str
    domain: str
    failure_type: str  # e.g., 'selector_not_found', 'timeout', 'hallucination'
    example_prompt: str
    frequency: int = 1
    last_seen: str = ""

    def __post_init__(self):
        if not self.last_seen:
            self.last_seen = datetime.now().isoformat()


class ActiveLearningManager:
    """
    Focuses training on areas where the model struggles.

    Problem: Random training doesn't address specific weaknesses.
    Solution: Track failure modes and generate targeted training tasks.
    """

    def __init__(self, storage_path: Path = None):
        self.storage_path = storage_path or Path("training/failure_modes.json")
        self.failure_modes: Dict[str, FailureMode] = {}
        self._load_failures()

        # Priority queue for task generation
        self.priority_queue: List[Tuple[float, str]] = []  # (priority, failure_key)

        self.stats = {
            'total_failures': 0,
            'unique_failure_types': 0,
            'targeted_tasks_generated': 0
        }

    def _failure_key(self, category: str, domain: str, failure_type: str) -> str:
        """Generate unique key for a failure mode."""
        return f"{category}:{domain}:{failure_type}"

    def _load_failures(self):
        """Load failure modes from disk."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path) as f:
                    data = json.load(f)
                    for key, val in data.items():
                        self.failure_modes[key] = FailureMode(**val)
            except:
                pass

    def _save_failures(self):
        """Save failure modes to disk."""
        try:
            data = {k: asdict(v) for k, v in self.failure_modes.items()}
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except:
            pass

    def record_failure(self,
                       task_prompt: str,
                       category: str,
                       domain: str,
                       error: str,
                       verification_result: Dict = None):
        """
        Record a task failure for analysis.

        Args:
            task_prompt: The task that failed
            category: Task category
            domain: Website domain
            error: Error message or description
            verification_result: Verification details
        """
        # Classify failure type
        failure_type = self._classify_failure(error, verification_result)

        key = self._failure_key(category, domain, failure_type)

        if key in self.failure_modes:
            self.failure_modes[key].frequency += 1
            self.failure_modes[key].last_seen = datetime.now().isoformat()
        else:
            self.failure_modes[key] = FailureMode(
                category=category,
                domain=domain,
                failure_type=failure_type,
                example_prompt=task_prompt[:200],
                frequency=1
            )

        self.stats['total_failures'] += 1
        self.stats['unique_failure_types'] = len(self.failure_modes)

        self._update_priority_queue()
        self._save_failures()

        logger.debug(f"[ACTIVE] Recorded failure: {failure_type} on {domain}")

    def _classify_failure(self, error: str, verification_result: Dict = None) -> str:
        """Classify the type of failure."""
        error_lower = error.lower() if error else ""

        # Selector failures
        if any(x in error_lower for x in ['selector', 'element', 'not found', 'no element']):
            return 'selector_not_found'

        # Timeout failures
        if 'timeout' in error_lower:
            return 'timeout'

        # Navigation failures
        if any(x in error_lower for x in ['navigate', 'url', 'page', '404', '403']):
            return 'navigation_failed'

        # CAPTCHA/Bot detection
        if any(x in error_lower for x in ['captcha', 'bot', 'blocked', 'cloudflare']):
            return 'bot_detection'

        # Hallucination (from verification)
        if verification_result:
            if not verification_result.get('output_matches_screen', True):
                return 'hallucination'
            if not verification_result.get('task_completed', True):
                return 'incomplete_task'

        # Generic error
        if any(x in error_lower for x in ['error', 'exception', 'failed']):
            return 'generic_error'

        return 'unknown'

    def _update_priority_queue(self):
        """Update priority queue based on failure frequencies."""
        self.priority_queue = []

        for key, failure in self.failure_modes.items():
            # Priority based on frequency and recency
            priority = failure.frequency

            # Boost recent failures
            try:
                last_seen = datetime.fromisoformat(failure.last_seen)
                hours_ago = (datetime.now() - last_seen).total_seconds() / 3600
                if hours_ago < 24:
                    priority *= 1.5
            except:
                pass

            self.priority_queue.append((priority, key))

        # Sort by priority (highest first)
        self.priority_queue.sort(reverse=True)

    def get_targeted_task_category(self) -> Optional[Tuple[str, str]]:
        """
        Get a task category to target based on failure modes.

        Returns:
            Tuple of (category, domain) or None if no targeting needed
        """
        if not self.priority_queue:
            return None

        # Pick from top failures with some randomization
        top_failures = self.priority_queue[:5]
        if not top_failures:
            return None

        # Weight selection by priority
        total_priority = sum(p for p, _ in top_failures)
        r = random.random() * total_priority

        cumulative = 0
        for priority, key in top_failures:
            cumulative += priority
            if r <= cumulative:
                failure = self.failure_modes[key]
                self.stats['targeted_tasks_generated'] += 1
                return (failure.category, failure.domain)

        return None

    def generate_remedial_prompt(self, category: str, domain: str) -> Optional[str]:
        """
        Generate a remedial task prompt for a failure mode.

        Returns:
            Task prompt targeting the weakness, or None
        """
        key = None
        for k, failure in self.failure_modes.items():
            if failure.category == category and failure.domain == domain:
                key = k
                break

        if not key:
            return None

        failure = self.failure_modes[key]

        # Generate prompt based on failure type
        prompts = {
            'selector_not_found': f"Navigate to {domain} and carefully identify all clickable elements before interacting.",
            'timeout': f"Visit {domain} and wait for the page to fully load before taking any action.",
            'navigation_failed': f"Navigate directly to https://{domain} and verify the page loaded correctly.",
            'bot_detection': f"Visit {domain} using natural browsing patterns - scroll, wait, then extract information.",
            'hallucination': f"Go to {domain} and extract only information that you can directly see on the page.",
            'incomplete_task': f"Visit {domain} and complete the full task step by step, verifying each step.",
        }

        base_prompt = prompts.get(failure.failure_type, f"Visit {domain} and perform a {category} task carefully.")

        return base_prompt

    def get_stats(self) -> Dict:
        """Get active learning stats."""
        # Group by failure type
        by_type = {}
        for failure in self.failure_modes.values():
            by_type[failure.failure_type] = by_type.get(failure.failure_type, 0) + failure.frequency

        return {
            **self.stats,
            'failure_types': by_type,
            'top_failures': [(k, self.failure_modes[k].frequency) for _, k in self.priority_queue[:10]],
            'domains_with_failures': list(set(f.domain for f in self.failure_modes.values()))
        }


# =============================================================================
# INTEGRATED TRAINING ENHANCER - Combines all 6 improvements
# =============================================================================

class TrainingEnhancer:
    """
    Integrates all 6 training improvements into a single interface.

    Use this class in self_play_engine.py to get all enhancements.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}

        # Initialize all components
        self.browser_pool = BrowserContextPool(max_contexts=5)
        self.vision_verifier = VisionVerifier(config)
        self.lora_manager = LoRATrainingManager()
        self.quality_scorer = QualityScorer()
        self.curriculum = CurriculumManager()
        self.active_learning = ActiveLearningManager()

        self.initialized = False
        self.stats = {}

    async def initialize(self, headless: bool = True):
        """Initialize all components."""
        await self.browser_pool.initialize(headless=headless)
        self.initialized = True
        logger.info("[ENHANCER] All training enhancements initialized")

    async def shutdown(self):
        """Shutdown all components."""
        await self.browser_pool.shutdown()
        self.initialized = False

    def get_task_settings(self) -> Dict:
        """
        Get settings for next training task based on curriculum and active learning.

        Returns:
            Dict with categories, difficulty, targeted training info
        """
        settings = {
            'difficulty': self.curriculum.get_current_difficulty(),
            'allowed_categories': self.curriculum.get_allowed_categories(),
            'allowed_sites': self.curriculum.get_allowed_sites(),
            'targeted': None
        }

        # Check if we should do targeted training (30% of time)
        if random.random() < 0.3:
            targeted = self.active_learning.get_targeted_task_category()
            if targeted:
                settings['targeted'] = {
                    'category': targeted[0],
                    'domain': targeted[1],
                    'prompt': self.active_learning.generate_remedial_prompt(*targeted)
                }

        return settings

    async def process_task_result(self,
                                   task_prompt: str,
                                   output: str,
                                   screenshot_path: str,
                                   page_url: str,
                                   page_content: str,
                                   elapsed_seconds: float,
                                   tool_calls: int,
                                   category: str,
                                   domain: str,
                                   error: str = None) -> Dict:
        """
        Process a task result through all enhancement systems.

        Returns:
            Comprehensive result with all scores and decisions
        """
        result = {
            'task_prompt': task_prompt[:100],
            'category': category,
            'domain': domain
        }

        # 1. Vision verification (if screenshot available)
        verification = await self.vision_verifier.verify_task_completion(
            screenshot_path=screenshot_path,
            task_prompt=task_prompt,
            claimed_output=output,
            page_url=page_url
        )
        result['verification'] = verification

        # 2. Quality scoring
        quality = self.quality_scorer.score_completion(
            task_prompt=task_prompt,
            output=output,
            verification_result=verification,
            elapsed_seconds=elapsed_seconds,
            tool_calls=tool_calls,
            page_content=page_content
        )
        result['quality'] = asdict(quality)

        # 3. Success/failure determination
        success = (
            verification.get('task_completed', False) and
            quality.overall >= 0.5
        )
        result['success'] = success

        # 4. Update curriculum
        curriculum_result = self.curriculum.record_attempt(success, category)
        result['curriculum'] = curriculum_result

        # 5. Record for LoRA training (if successful)
        if success:
            added = self.lora_manager.add_example(
                task_prompt=task_prompt,
                output=output,
                tool_calls=[],  # Would need to pass actual tool calls
                verification_result=verification,
                category=category,
                domain=domain
            )
            result['added_to_training'] = added
        else:
            # 6. Record failure for active learning
            self.active_learning.record_failure(
                task_prompt=task_prompt,
                category=category,
                domain=domain,
                error=error or 'task_failed',
                verification_result=verification
            )
            result['recorded_failure'] = True

        return result

    def get_all_stats(self) -> Dict:
        """Get comprehensive stats from all components."""
        return {
            'browser_pool': self.browser_pool.get_stats(),
            'vision': self.vision_verifier.get_stats(),
            'lora': self.lora_manager.get_stats(),
            'quality': self.quality_scorer.get_stats(),
            'curriculum': self.curriculum.get_stats(),
            'active_learning': self.active_learning.get_stats()
        }


# Factory function
def create_training_enhancer(config: dict = None) -> TrainingEnhancer:
    """Create a training enhancer instance."""
    return TrainingEnhancer(config)
