"""
Intelligent Model Router - Routes tasks to optimal models based on role and complexity.

BASED ON REDDIT RESEARCH (r/LocalLLaMA):
- Role specialization: planner vs executor vs critic
- xLAM-2-8b beats GPT-4o on BFCL v3 tool calling benchmark
- UI-TARS-1.5-7B for visual web interactions
- 0000/ui-tars-1.5-7b:latest excellent for agentic tasks with 250k context

MODEL STRATEGY (3 models + 2 specialists):
1. 0000/ui-tars-1.5-7b:latest - Primary executor for tool calling
2. moondream:latest - Vision for UI element detection
3. Kimi K2 - Strategic planner for complex tasks

SPECIALIST MODELS (optional, for better performance):
- xLAM-2-8b: Salesforce model, #1 on BFCL v3 tool calling benchmark
- UI-TARS-1.5-7B: ByteDance model for visual web page interactions

ROLE-BASED ROUTING:
- PLANNER: High-level strategy -> 0000/ui-tars-1.5-7b:latest or Kimi K2 for complex
- EXECUTOR: Tool calling -> 0000/ui-tars-1.5-7b:latest (or xLAM-2-8b if available)
- CRITIC: Safety review -> 0000/ui-tars-1.5-7b:latest
- HEALER: Error recovery -> 0000/ui-tars-1.5-7b:latest

Reddit insight: "The graph/tools do the real work, model just chooses edges and tools"
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from loguru import logger


class TaskComplexity(Enum):
    """Task complexity levels."""
    TRIVIAL = 1    # Single action
    SIMPLE = 2     # 2-3 well-defined steps
    MODERATE = 3   # 4-6 steps with some ambiguity
    COMPLEX = 4    # Multi-step extraction/reasoning
    EXPERT = 5     # Novel problems, recovery


class ModelTier(Enum):
    """Model capability tiers - core models + optional specialists."""
    # Core models (always available)
    QWEN3_8B = "qwen3_8b"      # Primary for all tasks - excellent tool calling
    VISION = "vision"          # moondream:latest for vision tasks
    KIMI_K2 = "kimi_k2"        # Strategic planner, complex reasoning

    # Specialist models (optional, for better performance)
    XLAM_8B = "xlam_8b"        # Salesforce xLAM-2-8b - #1 on BFCL v3 tool calling
    UI_TARS = "ui_tars"        # ByteDance UI-TARS-1.5-7B - visual web interactions


@dataclass
class RoutingDecision:
    """Result of model routing decision."""
    model_tier: ModelTier
    recommended_model: str
    complexity: TaskComplexity
    reasoning: str
    confidence: float  # 0.0-1.0
    fallback_tier: Optional[ModelTier] = None
    max_local_attempts: int = 2


class TaskComplexityAnalyzer:
    """
    Analyzes task prompts to determine complexity level.

    Uses pattern matching and heuristics - no LLM call needed.
    This runs BEFORE we pick a model, so it must be fast.
    """

    # Patterns that indicate TRIVIAL tasks (single action)
    TRIVIAL_PATTERNS = [
        r"^click\s+(?:the\s+)?(?:on\s+)?",
        r"^type\s+['\"]",
        r"^scroll\s+(?:down|up|to)",
        r"^press\s+(?:enter|tab|escape)",
        r"^hover\s+(?:over\s+)?",
        r"^select\s+['\"]",
        r"^wait\s+(?:for\s+)?\d+",
        r"^go\s+back$",
        r"^refresh$",
        r"^close\s+(?:the\s+)?(?:tab|window|popup)",
    ]

    # Patterns that indicate SIMPLE tasks (well-known flows)
    SIMPLE_PATTERNS = [
        r"^(?:go\s+to|open|navigate\s+to)\s+\S+$",  # Just navigation
        r"^search\s+(?:for\s+)?['\"]?[\w\s]+['\"]?\s+on\s+(?:google|bing|duckduckgo)",
        r"^login\s+(?:to\s+)?\w+\s+(?:with|as)\s+",
        r"^(?:get|tell\s+me)\s+(?:the\s+)?(?:page\s+)?title",
        r"^take\s+(?:a\s+)?screenshot",
        r"^what\s+(?:is|are)\s+(?:on\s+)?(?:this\s+)?page",
    ]

    # Patterns that indicate COMPLEX tasks (need smart model)
    COMPLEX_PATTERNS = [
        # Multi-item extraction
        r"(?:find|get|extract|tell\s+me|give\s+me)\s+(?:\d+|multiple|several|all|many)",
        r"\d+\s+(?:url|link|result|item|compan|business|advertiser|lead|contact)",
        r"(?:url|link|result)s?\s+(?:from|on)\s+",
        # Research/analysis tasks
        r"(?:research|analyze|investigate|compare|summarize)",
        r"(?:find\s+)?(?:all|every)\s+(?:the\s+)?",
        # Data extraction with criteria
        r"extract\s+(?:all\s+)?(?:the\s+)?(?:contact|email|phone|address)",
        r"scrape\s+",
        r"(?:build|create|compile)\s+(?:a\s+)?(?:list|spreadsheet|csv)",
        # Complex site interactions
        r"(?:fb|facebook)\s+ads\s+library",
        r"linkedin\s+(?:search|sales\s+navigator)",
        r"(?:find|search)\s+(?:leads?|prospects?|companies)",
    ]

    # Patterns that indicate EXPERT tasks (need best model)
    EXPERT_PATTERNS = [
        r"(?:figure\s+out|work\s+around|bypass|solve)",
        r"(?:captcha|recaptcha|cloudflare)",
        r"(?:if\s+.+\s+then|depending\s+on|based\s+on\s+what)",
        r"(?:adapt|adjust|change\s+strategy)",
        r"(?:keep\s+trying|don't\s+give\s+up|find\s+another\s+way)",
        r"(?:debug|troubleshoot|diagnose)",
    ]

    # Keywords that add complexity
    COMPLEXITY_BOOSTERS = {
        # Multi-step indicators
        "then": 1,
        "after that": 1,
        "next": 1,
        "finally": 1,
        "and then": 1,
        # Quantity indicators
        "all": 2,
        "every": 2,
        "multiple": 1,
        "several": 1,
        "many": 2,
        # Ambiguity indicators
        "best": 1,
        "top": 1,
        "most": 1,
        "similar": 1,
        "like": 1,
        "relevant": 1,
        # Quality requirements
        "accurate": 1,
        "correct": 1,
        "exact": 1,
        "specific": 1,
    }

    # Sites known to be complex (dynamic, auth-required, etc.)
    COMPLEX_SITES = [
        "facebook.com/ads/library",
        "linkedin.com",
        "sales navigator",
        "crunchbase.com",
        "zoominfo",
        "apollo.io",
        "hunter.io",
        "clearbit",
    ]

    def analyze(self, task: str) -> Tuple[TaskComplexity, float, str]:
        """
        Analyze task complexity.

        Returns:
            (complexity_level, confidence, reasoning)
        """
        task_lower = task.lower().strip()

        # Check for EXPERT patterns first (highest priority)
        for pattern in self.EXPERT_PATTERNS:
            if re.search(pattern, task_lower):
                return TaskComplexity.EXPERT, 0.9, f"Expert pattern detected: {pattern[:30]}"

        # Check for COMPLEX patterns
        for pattern in self.COMPLEX_PATTERNS:
            if re.search(pattern, task_lower):
                return TaskComplexity.COMPLEX, 0.85, f"Complex pattern detected: {pattern[:30]}"

        # Check for complex sites
        for site in self.COMPLEX_SITES:
            if site in task_lower:
                return TaskComplexity.COMPLEX, 0.9, f"Complex site detected: {site}"

        # Check for TRIVIAL patterns
        for pattern in self.TRIVIAL_PATTERNS:
            if re.search(pattern, task_lower):
                return TaskComplexity.TRIVIAL, 0.95, f"Trivial action: {pattern[:30]}"

        # Check for SIMPLE patterns
        for pattern in self.SIMPLE_PATTERNS:
            if re.search(pattern, task_lower):
                return TaskComplexity.SIMPLE, 0.85, f"Simple pattern: {pattern[:30]}"

        # Calculate complexity score from keywords
        complexity_score = 0
        found_boosters = []
        for keyword, boost in self.COMPLEXITY_BOOSTERS.items():
            if keyword in task_lower:
                complexity_score += boost
                found_boosters.append(keyword)

        # Count steps (rough heuristic based on conjunctions)
        step_indicators = len(re.findall(r'\b(?:then|and|after|next|finally|also)\b', task_lower))
        complexity_score += step_indicators

        # Determine level based on score
        if complexity_score >= 5:
            return TaskComplexity.COMPLEX, 0.7, f"High complexity score ({complexity_score}): {found_boosters[:3]}"
        elif complexity_score >= 3:
            return TaskComplexity.MODERATE, 0.7, f"Moderate complexity score ({complexity_score})"
        elif complexity_score >= 1:
            return TaskComplexity.SIMPLE, 0.7, f"Low complexity score ({complexity_score})"
        else:
            # Default to SIMPLE for unknown patterns (safer than TRIVIAL)
            return TaskComplexity.SIMPLE, 0.5, "No specific patterns matched, defaulting to SIMPLE"

    def extract_quantity(self, task: str) -> Optional[int]:
        """Extract requested quantity from task (e.g., 'find 10 URLs' -> 10)."""
        match = re.search(r'(?:find|get|extract|tell\s+me|give\s+me)\s+(\d+)', task.lower())
        if match:
            return int(match.group(1))
        return None


class ModelRouter:
    """
    Routes tasks to the optimal model based on complexity analysis.

    ROUTING STRATEGY:
    - TRIVIAL/SIMPLE: Always use local models (fast, cheap)
    - MODERATE: Start local, escalate to cloud on failure
    - COMPLEX/EXPERT: Go directly to cloud (Kimi K2)

    This prevents wasting time on local model failures for complex tasks.
    """

    # Model configurations - core models + optional specialists
    # Reddit insight: xLAM-2-8b beats GPT-4o on BFCL v3 tool calling benchmark
    MODELS = {
        # Core models (always available)
        ModelTier.QWEN3_8B: {
            "primary": "0000/ui-tars-1.5-7b:latest",  # Primary for tool calling
            "huggingface": None,    # Native Ollama model
            "fallbacks": [],
            "timeout_seconds": 30,
            "max_tokens": 4096,
            "role": "executor",     # Best for: tool calling, action execution
        },
        ModelTier.VISION: {
            "primary": "moondream:latest",  # Vision tasks
            "huggingface": None,
            "fallbacks": [],
            "timeout_seconds": 15,
            "max_tokens": 1000,
            "role": "vision",
        },
        ModelTier.KIMI_K2: {
            "primary": "kimi-k2",  # Complex reasoning
            "huggingface": None,   # API-based
            "fallbacks": [],
            "timeout_seconds": 60,
            "max_tokens": 4000,
            "role": "planner",     # Best for: strategic planning, complex reasoning
        },
        # Specialist models (optional - install for better performance)
        # User has: robbiemu/Salesforce_Llama-xLAM-2:8b-fc-r-q8_0
        ModelTier.XLAM_8B: {
            "primary": "robbiemu/Salesforce_Llama-xLAM-2:8b-fc-r-q8_0",
            "aliases": ["xlam", "salesforce_llama-xlam", "llama-xlam"],
            "fallbacks": ["0000/ui-tars-1.5-7b:latest"],
            "timeout_seconds": 30,
            "max_tokens": 4096,
            "role": "executor",    # #1 on BFCL v3 tool calling benchmark
        },
        # User has: 0000/ui-tars-1.5-7b:latest
        ModelTier.UI_TARS: {
            "primary": "0000/ui-tars-1.5-7b:latest",
            "aliases": ["ui-tars", "uitars"],
            "fallbacks": ["moondream:latest"],
            "timeout_seconds": 25,
            "max_tokens": 2000,
            "role": "vision",      # Specialized for web page interactions
        },
    }

    # Mapping from complexity to model tier
    # ALL tasks use 0000/ui-tars-1.5-7b:latest - it's the best tool caller
    COMPLEXITY_TO_TIER = {
        TaskComplexity.TRIVIAL: ModelTier.QWEN3_8B,
        TaskComplexity.SIMPLE: ModelTier.QWEN3_8B,
        TaskComplexity.MODERATE: ModelTier.QWEN3_8B,
        TaskComplexity.COMPLEX: ModelTier.QWEN3_8B,  # Start with qwen, escalate to Kimi on failure
        TaskComplexity.EXPERT: ModelTier.QWEN3_8B,   # Start with qwen, escalate to Kimi on failure
    }

    def __init__(self, kimi_available: bool = False, ollama_client=None):
        """
        Initialize router.

        Args:
            kimi_available: Whether Kimi K2 API is configured and available
            ollama_client: Ollama client to check available models
        """
        self.analyzer = TaskComplexityAnalyzer()
        self.kimi_available = kimi_available
        self.ollama_client = ollama_client
        self._failure_counts: Dict[str, int] = {}  # task_hash -> failure count

        # Cache of available specialist models
        self._available_specialists: Dict[ModelTier, bool] = {}
        self._check_specialist_models()

    def route(self, task: str, context: Optional[Dict] = None) -> RoutingDecision:
        """
        Route a task to the optimal model.

        Args:
            task: The task prompt
            context: Optional context (previous failures, current page, etc.)

        Returns:
            RoutingDecision with recommended model and reasoning
        """
        # Analyze task complexity
        complexity, confidence, reasoning = self.analyzer.analyze(task)

        # Get base tier for this complexity
        base_tier = self.COMPLEXITY_TO_TIER[complexity]

        # Check if we need to escalate based on context
        if context:
            # Escalate if we've failed multiple times
            failure_count = context.get("failure_count", 0)
            if failure_count >= 3 and self.kimi_available:
                base_tier = ModelTier.KIMI_K2
                reasoning += f" | Escalated to Kimi K2 due to {failure_count} failures"
                confidence = min(confidence, 0.7)  # Lower confidence after failures

        # If Kimi tier selected but not available, stay with 0000/ui-tars-1.5-7b:latest
        if base_tier == ModelTier.KIMI_K2 and not self.kimi_available:
            base_tier = ModelTier.QWEN3_8B
            reasoning += " | Kimi unavailable, using 0000/ui-tars-1.5-7b:latest"
            confidence *= 0.8  # Lower confidence without smart model

        # Get model config
        model_config = self.MODELS[base_tier]

        # Determine fallback tier - 0000/ui-tars-1.5-7b:latest always falls back to Kimi K2
        fallback_tier = None
        if base_tier == ModelTier.QWEN3_8B and self.kimi_available:
            fallback_tier = ModelTier.KIMI_K2

        # Calculate max attempts before escalating to Kimi
        max_attempts = 3  # Try 0000/ui-tars-1.5-7b:latest 3 times before escalating

        return RoutingDecision(
            model_tier=base_tier,
            recommended_model=model_config["primary"],
            complexity=complexity,
            reasoning=reasoning,
            confidence=confidence,
            fallback_tier=fallback_tier,
            max_local_attempts=max_attempts,
        )

    def should_escalate(self, task: str, attempt: int, last_error: Optional[str] = None) -> Tuple[bool, ModelTier]:
        """
        Determine if we should escalate to Kimi K2 after 0000/ui-tars-1.5-7b:latest failures.

        Simple strategy: After 3 0000/ui-tars-1.5-7b:latest failures, escalate to Kimi K2.

        Returns:
            (should_escalate, new_tier)
        """
        # After 3 failures, escalate to Kimi K2 if available
        if attempt >= 3 and self.kimi_available:
            return True, ModelTier.KIMI_K2

        return False, ModelTier.QWEN3_8B

    def _check_specialist_models(self):
        """
        Check which specialist models are available.

        Reddit insight: xLAM-2-8b and UI-TARS are optional but provide better performance.
        """
        if not self.ollama_client:
            # Can't check, assume not available
            self._available_specialists = {
                ModelTier.XLAM_8B: False,
                ModelTier.UI_TARS: False,
            }
            return

        try:
            # Get list of installed models
            result = self.ollama_client.list()
            if hasattr(result, 'models'):
                models = result.models
                model_names = [m.model.lower() if hasattr(m, 'model') else str(m).lower() for m in models]
            else:
                models = result.get('models', [])
                model_names = [m.get('name', '').lower() for m in models]

            model_str = ' '.join(model_names)

            # Check for xLAM (Salesforce tool calling model)
            # Matches: robbiemu/Salesforce_Llama-xLAM-2:8b-fc-r-q8_0, xlam, etc.
            xlam_patterns = ['xlam', 'salesforce_llama-xlam', 'robbiemu/salesforce']
            self._available_specialists[ModelTier.XLAM_8B] = any(p in model_str for p in xlam_patterns)

            # Check for UI-TARS (ByteDance web interaction model)
            # Matches: 0000/ui-tars-1.5-7b:latest, ui-tars, uitars
            uitars_patterns = ['ui-tars', 'uitars', '0000/ui-tars']
            self._available_specialists[ModelTier.UI_TARS] = any(p in model_str for p in uitars_patterns)

            if self._available_specialists[ModelTier.XLAM_8B]:
                logger.info("[ROUTER] xLAM-2-8b DETECTED - will use for tool calling (BFCL #1 benchmark winner)")
            if self._available_specialists[ModelTier.UI_TARS]:
                logger.info("[ROUTER] UI-TARS DETECTED - will use for visual web interactions")

        except Exception as e:
            logger.warning(f"[ROUTER] Could not check specialist models: {e}")
            self._available_specialists = {
                ModelTier.XLAM_8B: False,
                ModelTier.UI_TARS: False,
            }

    def is_specialist_available(self, tier: ModelTier) -> bool:
        """Check if a specialist model is available."""
        return self._available_specialists.get(tier, False)

    def get_best_executor_model(self) -> str:
        """
        Get the best available model for tool execution.

        Reddit insight: xLAM-2-8b beats GPT-4o on BFCL v3 tool calling benchmark.
        Use it if available, otherwise fall back to 0000/ui-tars-1.5-7b:latest.
        """
        if self._available_specialists.get(ModelTier.XLAM_8B, False):
            return self.MODELS[ModelTier.XLAM_8B]["primary"]
        return self.MODELS[ModelTier.QWEN3_8B]["primary"]

    def get_best_vision_model(self, for_web_interaction: bool = False) -> str:
        """
        Get the best available vision model.

        Args:
            for_web_interaction: If True, prefer UI-TARS for web page interactions

        Reddit insight: UI-TARS-1.5-7B is specialized for web page interactions.
        """
        if for_web_interaction and self._available_specialists.get(ModelTier.UI_TARS, False):
            return self.MODELS[ModelTier.UI_TARS]["primary"]
        return self.MODELS[ModelTier.VISION]["primary"]

    def get_model_for_tier(self, tier: ModelTier) -> str:
        """Get the primary model name for a tier, with specialist substitution."""
        # Check if we should use a specialist instead
        if tier == ModelTier.QWEN3_8B and self._available_specialists.get(ModelTier.XLAM_8B, False):
            # Use xLAM for executor tasks
            return self.MODELS[ModelTier.XLAM_8B]["primary"]

        return self.MODELS[tier]["primary"]

    def get_timeout_for_tier(self, tier: ModelTier) -> int:
        """Get timeout in seconds for a tier."""
        return self.MODELS[tier]["timeout_seconds"]

    def get_install_instructions(self) -> str:
        """Get instructions for installing optional specialist models."""
        instructions = """
OPTIONAL SPECIALIST MODELS (for better performance):

1. xLAM-2-8b (Salesforce) - #1 on BFCL v3 tool calling benchmark
   Beats GPT-4o on function calling! Great for browser automation.
   Install: ollama pull hf.co/Salesforce/Llama-xLAM-2-8b-fc-r-gguf:Q4_K_M

2. UI-TARS-1.5-7B (ByteDance) - Specialized for web page interactions
   Trained on web UI navigation, form filling, element clicking.
   Install: ollama pull hf.co/ByteDance-Seed/UI-TARS-1.5-7B-GGUF:Q4_K_M

Current status:
- xLAM-2-8b: {"INSTALLED" if self._available_specialists.get(ModelTier.XLAM_8B) else "Not installed"}
- UI-TARS: {"INSTALLED" if self._available_specialists.get(ModelTier.UI_TARS) else "Not installed"}
"""
        return instructions


# Singleton instance
_router_instance: Optional[ModelRouter] = None


def get_model_router(kimi_available: bool = None) -> ModelRouter:
    """
    Get or create the singleton ModelRouter instance.

    Args:
        kimi_available: Whether Kimi K2 is available (auto-detected if None)
    """
    global _router_instance

    if _router_instance is None:
        # Auto-detect Kimi availability if not specified
        if kimi_available is None:
            try:
                from .kimi_k2_client import get_kimi_client
                kimi = get_kimi_client()
                kimi_available = kimi.is_available()
            except Exception:
                kimi_available = False

        _router_instance = ModelRouter(kimi_available=kimi_available)
        logger.info(f"[MODEL_ROUTER] Initialized with kimi_available={kimi_available}")

    return _router_instance


def route_task(task: str, context: Optional[Dict] = None) -> RoutingDecision:
    """Convenience function to route a task."""
    router = get_model_router()
    return router.route(task, context)


# Quick test
if __name__ == "__main__":
    router = ModelRouter(kimi_available=True)

    test_tasks = [
        "click the login button",
        "search for AI news on Google",
        "login to saucedemo with standard_user and add backpack to cart",
        "go to fb ads library and search booked meetings tell me 10 advertiser urls",
        "find all companies in NYC that raised Series A in 2024",
        "figure out how to bypass this CAPTCHA",
        "get the page title",
        "extract all email addresses from this page",
    ]

    print("\n" + "="*80)
    print("MODEL ROUTING TEST")
    print("="*80)

    for task in test_tasks:
        decision = router.route(task)
        print(f"\nTask: {task[:60]}...")
        print(f"  Complexity: {decision.complexity.name}")
        print(f"  Model: {decision.model_tier.value} -> {decision.recommended_model}")
        print(f"  Confidence: {decision.confidence:.0%}")
        print(f"  Reasoning: {decision.reasoning}")
        print(f"  Max local attempts: {decision.max_local_attempts}")
