"""
Model Capabilities Registry

Centralized registry for AI model capabilities, limits, and costs.
Based on OpenCode's provider/models.ts architecture.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum


class TaskType(Enum):
    """Common AI task types for model recommendations"""
    REASONING = "reasoning"
    CODING = "coding"
    VISION = "vision"
    FAST_RESPONSE = "fast_response"
    LONG_CONTEXT = "long_context"
    COST_OPTIMIZED = "cost_optimized"


@dataclass
class ModelCapabilities:
    """Model feature support flags"""
    attachment: bool = False  # File attachments
    reasoning: bool = False  # Chain of thought / extended thinking
    temperature: bool = True  # Supports temperature parameter
    tool_call: bool = False  # Function/tool calling
    interleaved: bool = False  # Mixed content types in messages
    modalities: List[str] = field(default_factory=list)  # text, image, audio, video, pdf


@dataclass
class ModelLimits:
    """Model token limits"""
    context: int  # Context window in tokens
    output: int  # Max output tokens


@dataclass
class ModelCost:
    """Model pricing per 1M tokens (USD)"""
    input: float  # Cost per 1M input tokens
    output: float  # Cost per 1M output tokens
    cache_read: Optional[float] = None  # Cost per 1M cached tokens read
    cache_write: Optional[float] = None  # Cost per 1M cached tokens written


@dataclass
class ModelDefinition:
    """Complete model specification"""
    id: str  # Unique model identifier
    name: str  # Human-readable name
    family: str  # Model family (claude, gpt, gemini, etc)
    capabilities: ModelCapabilities
    limits: ModelLimits
    cost: ModelCost
    status: str = "stable"  # stable, beta, deprecated


class ModelRegistry:
    """
    Central registry for AI model metadata and capabilities.

    Usage:
        registry = ModelRegistry()
        model = registry.get_model("claude-3-opus-20240229")
        if registry.supports_feature(model.id, "tool_call"):
            # Use tool calling
            pass
    """

    def __init__(self):
        self._models: Dict[str, ModelDefinition] = {}
        self._initialize_models()

    def _initialize_models(self):
        """Pre-populate registry with common models"""

        # Claude Models
        self._register(ModelDefinition(
            id="claude-3-opus-20240229",
            name="Claude 3 Opus",
            family="claude",
            capabilities=ModelCapabilities(
                attachment=True,
                reasoning=False,
                temperature=True,
                tool_call=True,
                interleaved=True,
                modalities=["text", "image", "pdf"]
            ),
            limits=ModelLimits(context=200_000, output=4_096),
            cost=ModelCost(input=15.0, output=75.0, cache_read=1.5, cache_write=18.75),
            status="stable"
        ))

        self._register(ModelDefinition(
            id="claude-3-5-sonnet-20241022",
            name="Claude 3.5 Sonnet",
            family="claude",
            capabilities=ModelCapabilities(
                attachment=True,
                reasoning=False,
                temperature=True,
                tool_call=True,
                interleaved=True,
                modalities=["text", "image", "pdf"]
            ),
            limits=ModelLimits(context=200_000, output=8_192),
            cost=ModelCost(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75),
            status="stable"
        ))

        self._register(ModelDefinition(
            id="claude-3-5-haiku-20241022",
            name="Claude 3.5 Haiku",
            family="claude",
            capabilities=ModelCapabilities(
                attachment=True,
                reasoning=False,
                temperature=True,
                tool_call=True,
                interleaved=True,
                modalities=["text", "image", "pdf"]
            ),
            limits=ModelLimits(context=200_000, output=8_192),
            cost=ModelCost(input=1.0, output=5.0, cache_read=0.1, cache_write=1.25),
            status="stable"
        ))

        self._register(ModelDefinition(
            id="claude-3-haiku-20240307",
            name="Claude 3 Haiku",
            family="claude",
            capabilities=ModelCapabilities(
                attachment=True,
                reasoning=False,
                temperature=True,
                tool_call=True,
                interleaved=True,
                modalities=["text", "image", "pdf"]
            ),
            limits=ModelLimits(context=200_000, output=4_096),
            cost=ModelCost(input=0.25, output=1.25, cache_read=0.03, cache_write=0.30),
            status="stable"
        ))

        self._register(ModelDefinition(
            id="claude-opus-4-20250514",
            name="Claude Opus 4.5",
            family="claude",
            capabilities=ModelCapabilities(
                attachment=True,
                reasoning=True,
                temperature=True,
                tool_call=True,
                interleaved=True,
                modalities=["text", "image", "pdf"]
            ),
            limits=ModelLimits(context=200_000, output=16_384),
            cost=ModelCost(input=15.0, output=75.0, cache_read=1.5, cache_write=18.75),
            status="stable"
        ))

        # GPT Models
        self._register(ModelDefinition(
            id="gpt-4o",
            name="GPT-4o",
            family="gpt",
            capabilities=ModelCapabilities(
                attachment=True,
                reasoning=False,
                temperature=True,
                tool_call=True,
                interleaved=True,
                modalities=["text", "image", "audio"]
            ),
            limits=ModelLimits(context=128_000, output=16_384),
            cost=ModelCost(input=2.5, output=10.0),
            status="stable"
        ))

        self._register(ModelDefinition(
            id="gpt-4o-mini",
            name="GPT-4o Mini",
            family="gpt",
            capabilities=ModelCapabilities(
                attachment=True,
                reasoning=False,
                temperature=True,
                tool_call=True,
                interleaved=True,
                modalities=["text", "image", "audio"]
            ),
            limits=ModelLimits(context=128_000, output=16_384),
            cost=ModelCost(input=0.15, output=0.6),
            status="stable"
        ))

        self._register(ModelDefinition(
            id="gpt-4-turbo",
            name="GPT-4 Turbo",
            family="gpt",
            capabilities=ModelCapabilities(
                attachment=True,
                reasoning=False,
                temperature=True,
                tool_call=True,
                interleaved=True,
                modalities=["text", "image"]
            ),
            limits=ModelLimits(context=128_000, output=4_096),
            cost=ModelCost(input=10.0, output=30.0),
            status="stable"
        ))

        self._register(ModelDefinition(
            id="gpt-3.5-turbo",
            name="GPT-3.5 Turbo",
            family="gpt",
            capabilities=ModelCapabilities(
                attachment=False,
                reasoning=False,
                temperature=True,
                tool_call=True,
                interleaved=False,
                modalities=["text"]
            ),
            limits=ModelLimits(context=16_385, output=4_096),
            cost=ModelCost(input=0.5, output=1.5),
            status="stable"
        ))

        self._register(ModelDefinition(
            id="o1",
            name="GPT-o1",
            family="gpt",
            capabilities=ModelCapabilities(
                attachment=True,
                reasoning=True,
                temperature=False,
                tool_call=False,
                interleaved=True,
                modalities=["text", "image"]
            ),
            limits=ModelLimits(context=200_000, output=100_000),
            cost=ModelCost(input=15.0, output=60.0),
            status="stable"
        ))

        self._register(ModelDefinition(
            id="o1-mini",
            name="GPT-o1 Mini",
            family="gpt",
            capabilities=ModelCapabilities(
                attachment=True,
                reasoning=True,
                temperature=False,
                tool_call=False,
                interleaved=True,
                modalities=["text", "image"]
            ),
            limits=ModelLimits(context=128_000, output=65_536),
            cost=ModelCost(input=3.0, output=12.0),
            status="stable"
        ))

        # Gemini Models
        self._register(ModelDefinition(
            id="gemini-2.0-flash-exp",
            name="Gemini 2.0 Flash",
            family="gemini",
            capabilities=ModelCapabilities(
                attachment=True,
                reasoning=False,
                temperature=True,
                tool_call=True,
                interleaved=True,
                modalities=["text", "image", "audio", "video"]
            ),
            limits=ModelLimits(context=1_048_576, output=8_192),
            cost=ModelCost(input=0.0, output=0.0),  # Free during preview
            status="beta"
        ))

        self._register(ModelDefinition(
            id="gemini-1.5-pro",
            name="Gemini 1.5 Pro",
            family="gemini",
            capabilities=ModelCapabilities(
                attachment=True,
                reasoning=False,
                temperature=True,
                tool_call=True,
                interleaved=True,
                modalities=["text", "image", "audio", "video"]
            ),
            limits=ModelLimits(context=2_097_152, output=8_192),
            cost=ModelCost(input=1.25, output=5.0, cache_read=0.3125, cache_write=1.25),
            status="stable"
        ))

        self._register(ModelDefinition(
            id="gemini-1.5-flash",
            name="Gemini 1.5 Flash",
            family="gemini",
            capabilities=ModelCapabilities(
                attachment=True,
                reasoning=False,
                temperature=True,
                tool_call=True,
                interleaved=True,
                modalities=["text", "image", "audio", "video"]
            ),
            limits=ModelLimits(context=1_048_576, output=8_192),
            cost=ModelCost(input=0.075, output=0.3, cache_read=0.01875, cache_write=0.075),
            status="stable"
        ))

        self._register(ModelDefinition(
            id="gemini-exp-1206",
            name="Gemini Experimental 1206",
            family="gemini",
            capabilities=ModelCapabilities(
                attachment=True,
                reasoning=True,
                temperature=True,
                tool_call=True,
                interleaved=True,
                modalities=["text", "image", "audio"]
            ),
            limits=ModelLimits(context=200_000, output=8_192),
            cost=ModelCost(input=0.0, output=0.0),  # Free during preview
            status="beta"
        ))

    def _register(self, model: ModelDefinition):
        """Register a model in the registry"""
        self._models[model.id] = model

    def get_model(self, model_id: str) -> Optional[ModelDefinition]:
        """
        Get model definition by ID

        Args:
            model_id: Model identifier (e.g., "claude-3-opus-20240229")

        Returns:
            ModelDefinition or None if not found
        """
        return self._models.get(model_id)

    def list_models(self, family: Optional[str] = None, status: Optional[str] = None) -> List[ModelDefinition]:
        """
        List available models with optional filtering

        Args:
            family: Filter by model family (claude, gpt, gemini)
            status: Filter by status (stable, beta, deprecated)

        Returns:
            List of ModelDefinition objects
        """
        models = list(self._models.values())

        if family:
            models = [m for m in models if m.family == family]

        if status:
            models = [m for m in models if m.status == status]

        return sorted(models, key=lambda m: (m.family, m.name))

    def get_best_for_task(self, task_type: TaskType) -> Optional[ModelDefinition]:
        """
        Recommend best model for a specific task type

        Args:
            task_type: Type of task (TaskType enum)

        Returns:
            Recommended ModelDefinition or None
        """
        if task_type == TaskType.REASONING:
            # Prefer models with reasoning capabilities
            return self.get_model("claude-opus-4-20250514")

        elif task_type == TaskType.CODING:
            # Balance of capability and cost
            return self.get_model("claude-3-5-sonnet-20241022")

        elif task_type == TaskType.VISION:
            # Best multimodal support
            return self.get_model("gemini-1.5-pro")

        elif task_type == TaskType.FAST_RESPONSE:
            # Fastest, cheapest
            return self.get_model("claude-3-5-haiku-20241022")

        elif task_type == TaskType.LONG_CONTEXT:
            # Largest context window
            return self.get_model("gemini-1.5-pro")

        elif task_type == TaskType.COST_OPTIMIZED:
            # Best price/performance
            return self.get_model("gpt-4o-mini")

        return None

    def supports_feature(self, model_id: str, feature: str) -> bool:
        """
        Check if model supports a specific feature

        Args:
            model_id: Model identifier
            feature: Feature name (attachment, reasoning, tool_call, etc)

        Returns:
            True if feature is supported, False otherwise
        """
        model = self.get_model(model_id)
        if not model:
            return False

        return getattr(model.capabilities, feature, False)

    def supports_modality(self, model_id: str, modality: str) -> bool:
        """
        Check if model supports a specific modality

        Args:
            model_id: Model identifier
            modality: Modality type (text, image, audio, video, pdf)

        Returns:
            True if modality is supported, False otherwise
        """
        model = self.get_model(model_id)
        if not model:
            return False

        return modality in model.capabilities.modalities

    def calculate_cost(self, model_id: str, input_tokens: int, output_tokens: int,
                      cached_tokens: int = 0) -> Optional[float]:
        """
        Calculate total cost for a model interaction

        Args:
            model_id: Model identifier
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cached_tokens: Number of cached tokens read (if applicable)

        Returns:
            Total cost in USD, or None if model not found
        """
        model = self.get_model(model_id)
        if not model:
            return None

        # Convert to per-million pricing
        input_cost = (input_tokens / 1_000_000) * model.cost.input
        output_cost = (output_tokens / 1_000_000) * model.cost.output

        cache_cost = 0.0
        if cached_tokens > 0 and model.cost.cache_read is not None:
            cache_cost = (cached_tokens / 1_000_000) * model.cost.cache_read

        return input_cost + output_cost + cache_cost


# Singleton instance
_registry = None

def get_registry() -> ModelRegistry:
    """Get singleton ModelRegistry instance"""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry


# Tests
if __name__ == "__main__":
    print("Model Registry Tests")
    print("=" * 60)

    registry = get_registry()

    # Test 1: Get specific model
    print("\n1. Get Claude 3.5 Sonnet:")
    sonnet = registry.get_model("claude-3-5-sonnet-20241022")
    if sonnet:
        print(f"   Name: {sonnet.name}")
        print(f"   Family: {sonnet.family}")
        print(f"   Context: {sonnet.limits.context:,} tokens")
        print(f"   Output: {sonnet.limits.output:,} tokens")
        print(f"   Input cost: ${sonnet.cost.input}/1M tokens")
        print(f"   Tool calling: {sonnet.capabilities.tool_call}")

    # Test 2: List models by family
    print("\n2. Claude Models:")
    claude_models = registry.list_models(family="claude")
    for model in claude_models:
        print(f"   - {model.name} ({model.id})")

    print("\n3. GPT Models:")
    gpt_models = registry.list_models(family="gpt")
    for model in gpt_models:
        print(f"   - {model.name} ({model.id})")

    print("\n4. Gemini Models:")
    gemini_models = registry.list_models(family="gemini")
    for model in gemini_models:
        print(f"   - {model.name} ({model.id})")

    # Test 3: Task recommendations
    print("\n5. Task Recommendations:")
    for task in TaskType:
        model = registry.get_best_for_task(task)
        if model:
            print(f"   {task.value}: {model.name}")

    # Test 4: Feature support
    print("\n6. Feature Support Check:")
    test_model = "claude-3-5-sonnet-20241022"
    features = ["tool_call", "reasoning", "attachment", "temperature"]
    for feature in features:
        supported = registry.supports_feature(test_model, feature)
        print(f"   {feature}: {supported}")

    # Test 5: Modality support
    print("\n7. Modality Support (Gemini 1.5 Pro):")
    test_model = "gemini-1.5-pro"
    modalities = ["text", "image", "audio", "video", "pdf"]
    for modality in modalities:
        supported = registry.supports_modality(test_model, modality)
        print(f"   {modality}: {supported}")

    # Test 6: Cost calculation
    print("\n8. Cost Calculation:")
    print(f"   GPT-4o (10K input, 2K output):")
    cost = registry.calculate_cost("gpt-4o", 10_000, 2_000)
    if cost:
        print(f"   Total: ${cost:.4f}")

    print(f"\n   Claude 3.5 Sonnet (10K input, 2K output, 5K cached):")
    cost = registry.calculate_cost("claude-3-5-sonnet-20241022", 10_000, 2_000, 5_000)
    if cost:
        print(f"   Total: ${cost:.4f}")

    # Test 7: Stable models only
    print("\n9. Stable Models Count:")
    stable = registry.list_models(status="stable")
    print(f"   {len(stable)} stable models available")

    # Test 8: Compare reasoning models
    print("\n10. Reasoning-Capable Models:")
    all_models = registry.list_models()
    reasoning_models = [m for m in all_models if m.capabilities.reasoning]
    for model in reasoning_models:
        print(f"   - {model.name} ({model.family})")
        print(f"     Context: {model.limits.context:,}, Output: {model.limits.output:,}")
        print(f"     Cost: ${model.cost.input}/1M in, ${model.cost.output}/1M out")

    print("\n" + "=" * 60)
    print("All tests completed successfully!")
