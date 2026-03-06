"""
Model Orchestrator - Intelligently combine multiple model outputs.

This orchestrator integrates:
1. Kimi K2 - Strategic planning and reasoning (1T params, long-context)
2. ChatGPT - Verification and quality checks (via OpenAI API)
3. Browser/Web - Real-time information gathering
4. MiniCPM - Visual understanding and screenshot analysis

Capabilities:
- Parallel execution where possible for speed
- Graceful fallbacks when models fail
- Conflict resolution when models disagree
- Confidence scoring based on agreement
- EventBus integration for monitoring
- Timeout handling for each model
"""

import asyncio
import time
import traceback
from datetime import datetime
from typing import Dict, List, Any, Optional, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger

# Import our existing model clients
try:
    from .kimi_k2_client import KimiK2Client, TaskPlan
    KIMI_AVAILABLE = True
except ImportError:
    KIMI_AVAILABLE = False
    logger.debug("Kimi K2 client not available")

# Import EventBus for monitoring
try:
    from .organism_core import EventBus, EventType, OrganismEvent
    EVENTBUS_AVAILABLE = True
except ImportError:
    EVENTBUS_AVAILABLE = False
    logger.debug("EventBus not available - orchestrator will run without event monitoring")

# OpenAI for ChatGPT verification
try:
    from openai import AsyncOpenAI
    import os
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.debug("OpenAI library not available")

# Vision processing
try:
    import ollama
    import base64
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.debug("Ollama not available for vision processing")


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class ModelType(Enum):
    """Types of models that can be orchestrated."""
    KIMI_K2 = "kimi_k2"
    CHATGPT = "chatgpt"
    BROWSER = "browser"
    MINICPM = "minicpm"
    OLLAMA_VISION = "ollama_vision"


@dataclass
class ModelResult:
    """Result from a single model."""
    model_type: ModelType
    success: bool
    content: Any
    error: Optional[str] = None
    latency_ms: float = 0.0
    confidence: float = 1.0  # Self-reported confidence (0-1)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class OrchestratedResult:
    """Final synthesized result from multiple models."""
    task: str
    primary_answer: Any
    model_results: Dict[ModelType, ModelResult] = field(default_factory=dict)
    confidence: float = 0.0  # Overall confidence based on agreement
    conflicts: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    models_used: Set[ModelType] = field(default_factory=set)
    fallback_chain: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "task": self.task,
            "primary_answer": str(self.primary_answer)[:500],  # Truncate for logs
            "confidence": round(self.confidence, 2),
            "execution_time_ms": round(self.execution_time_ms, 1),
            "models_used": [m.value for m in self.models_used],
            "conflicts": self.conflicts,
            "fallback_chain": self.fallback_chain,
            "timestamp": self.timestamp,
            "model_count": len(self.model_results),
        }


# =============================================================================
# MODEL ORCHESTRATOR
# =============================================================================

class ModelOrchestrator:
    """
    Orchestrates multiple AI models to produce high-quality results.

    Strategy:
    1. Run fast models in parallel (vision, browser search)
    2. Feed results to primary reasoning model (Kimi K2)
    3. Optionally verify with secondary model (ChatGPT)
    4. Synthesize results, resolve conflicts, compute confidence
    """

    def __init__(
        self,
        kimi_client: Optional['KimiK2Client'] = None,
        chatgpt_api_key: Optional[str] = None,
        chatgpt_model: str = "gpt-4o-mini",
        vision_model: str = "minicpm-v",
        event_bus: Optional['EventBus'] = None,
        enable_verification: bool = False,
        parallel_timeout: float = 30.0,
        reasoning_timeout: float = 60.0,
        verification_timeout: float = 20.0,
    ):
        """
        Initialize model orchestrator.

        Args:
            kimi_client: Kimi K2 client for strategic reasoning
            chatgpt_api_key: OpenAI API key for verification
            chatgpt_model: ChatGPT model to use (default: gpt-4o-mini for speed)
            vision_model: Ollama vision model for screenshots
            event_bus: EventBus for monitoring and coordination
            enable_verification: Enable ChatGPT verification step
            parallel_timeout: Timeout for parallel model calls (seconds)
            reasoning_timeout: Timeout for main reasoning model (seconds)
            verification_timeout: Timeout for verification step (seconds)
        """
        self.kimi_client = kimi_client
        self.vision_model = vision_model
        self.event_bus = event_bus
        self.enable_verification = enable_verification

        # Timeouts
        self.parallel_timeout = parallel_timeout
        self.reasoning_timeout = reasoning_timeout
        self.verification_timeout = verification_timeout

        # ChatGPT client (lazy init)
        self._chatgpt_client: Optional[AsyncOpenAI] = None
        self._chatgpt_api_key = chatgpt_api_key or os.getenv("OPENAI_API_KEY")
        self._chatgpt_model = chatgpt_model

        # Ollama client (lazy init)
        self._ollama_client = None

        # Statistics
        self.stats = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "avg_confidence": 0.0,
            "avg_execution_time_ms": 0.0,
            "model_usage": {m.value: 0 for m in ModelType},
            "conflicts_detected": 0,
            "fallbacks_triggered": 0,
        }

        logger.debug("ModelOrchestrator initialized")

    @property
    def chatgpt_client(self) -> Optional[AsyncOpenAI]:
        """Get or create ChatGPT client."""
        if not OPENAI_AVAILABLE or not self._chatgpt_api_key:
            return None
        if self._chatgpt_client is None:
            self._chatgpt_client = AsyncOpenAI(api_key=self._chatgpt_api_key)
        return self._chatgpt_client

    @property
    def ollama_client(self):
        """Get or create Ollama client."""
        if not OLLAMA_AVAILABLE:
            return None
        if self._ollama_client is None:
            self._ollama_client = ollama
        return self._ollama_client

    # =========================================================================
    # MAIN ORCHESTRATION
    # =========================================================================

    async def execute(
        self,
        task: str,
        tools: List[str],
        context: Optional[str] = None,
        screenshot: Optional[bytes] = None,
        web_search_query: Optional[str] = None,
        available_tools: Optional[List[str]] = None,
    ) -> OrchestratedResult:
        """
        Execute task using orchestrated multi-model approach.

        Args:
            task: The task to execute
            tools: List of required tools/capabilities
            context: Optional context from previous actions
            screenshot: Optional screenshot for vision analysis
            web_search_query: Optional web search to run
            available_tools: List of available tool names for planning

        Returns:
            OrchestratedResult with synthesized answer and metadata
        """
        start_time = time.time()
        self.stats["total_executions"] += 1

        # Emit event
        if self.event_bus and EVENTBUS_AVAILABLE:
            self.event_bus.emit(OrganismEvent(
                event_type=EventType.ACTION_START,
                source="model_orchestrator",
                data={
                    "task": task,
                    "tools": tools,
                    "timestamp": start_time,
                }
            ))

        result = OrchestratedResult(task=task)

        try:
            # Phase 1: Gather context in parallel (fast models)
            phase1_results = await self._gather_context_parallel(
                task=task,
                screenshot=screenshot,
                web_search_query=web_search_query,
            )
            result.model_results.update(phase1_results)
            result.models_used.update(phase1_results.keys())

            # Phase 2: Primary reasoning (Kimi K2 or fallback)
            reasoning_result = await self._primary_reasoning(
                task=task,
                context=context,
                phase1_results=phase1_results,
                available_tools=available_tools or [],
            )

            if reasoning_result:
                result.model_results[reasoning_result.model_type] = reasoning_result
                result.models_used.add(reasoning_result.model_type)
                result.primary_answer = reasoning_result.content

                # Phase 3: Verification (optional, if enabled)
                if self.enable_verification and reasoning_result.success:
                    verification_result = await self._verify_answer(
                        task=task,
                        proposed_answer=reasoning_result.content,
                        context=phase1_results,
                    )

                    if verification_result:
                        result.model_results[ModelType.CHATGPT] = verification_result
                        result.models_used.add(ModelType.CHATGPT)

            # Phase 4: Synthesize results
            result = self._synthesize(result)

            # Update stats
            result.execution_time_ms = (time.time() - start_time) * 1000
            self.stats["successful_executions"] += 1
            self._update_stats(result)

            # Emit success event
            if self.event_bus and EVENTBUS_AVAILABLE:
                self.event_bus.emit(OrganismEvent(
                    event_type=EventType.ACTION_COMPLETE,
                    source="model_orchestrator",
                    data={
                        "task": task,
                        "confidence": result.confidence,
                        "execution_time_ms": result.execution_time_ms,
                        "models_used": [m.value for m in result.models_used],
                    }
                ))

        except Exception as e:
            logger.error(f"Orchestration failed: {e}")
            logger.debug(traceback.format_exc())
            self.stats["failed_executions"] += 1
            result.conflicts.append(f"Orchestration error: {str(e)}")
            result.execution_time_ms = (time.time() - start_time) * 1000

            # Emit failure event
            if self.event_bus and EVENTBUS_AVAILABLE:
                self.event_bus.emit(OrganismEvent(
                    event_type=EventType.ACTION_FAILED,
                    source="model_orchestrator",
                    data={
                        "task": task,
                        "error": str(e),
                        "execution_time_ms": result.execution_time_ms,
                    }
                ))

        return result

    # =========================================================================
    # PHASE 1: CONTEXT GATHERING (PARALLEL)
    # =========================================================================

    async def _gather_context_parallel(
        self,
        task: str,
        screenshot: Optional[bytes] = None,
        web_search_query: Optional[str] = None,
    ) -> Dict[ModelType, ModelResult]:
        """
        Gather context from fast models in parallel.

        Args:
            task: Task description
            screenshot: Optional screenshot to analyze
            web_search_query: Optional web search query

        Returns:
            Dict mapping ModelType to ModelResult
        """
        tasks = []

        # Vision analysis
        if screenshot and self.ollama_client:
            tasks.append(self._vision_analysis(screenshot))

        # Web search (placeholder - would integrate with browser/search tool)
        if web_search_query:
            tasks.append(self._web_search(web_search_query))

        # Run all in parallel with timeout
        if not tasks:
            return {}

        try:
            completed = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.parallel_timeout
            )

            results = {}
            for result in completed:
                if isinstance(result, ModelResult) and result.success:
                    results[result.model_type] = result
                elif isinstance(result, Exception):
                    logger.warning(f"Parallel task failed: {result}")

            return results

        except asyncio.TimeoutError:
            logger.warning(f"Parallel context gathering timed out after {self.parallel_timeout}s")
            return {}

    async def _vision_analysis(self, screenshot: bytes) -> ModelResult:
        """Analyze screenshot with vision model."""
        start = time.time()

        try:
            if not self.ollama_client:
                return ModelResult(
                    model_type=ModelType.OLLAMA_VISION,
                    success=False,
                    content=None,
                    error="Ollama not available"
                )

            b64 = base64.b64encode(screenshot).decode('utf-8')

            response = await asyncio.to_thread(
                self.ollama_client.chat,
                model=self.vision_model,
                messages=[{
                    'role': 'user',
                    'content': 'Analyze this screenshot. Describe what you see, any errors, and the current state.',
                    'images': [b64]
                }],
                options={'temperature': 0.1}
            )

            content = response.get('message', {}).get('content', '')
            latency = (time.time() - start) * 1000

            return ModelResult(
                model_type=ModelType.OLLAMA_VISION,
                success=True,
                content=content,
                latency_ms=latency,
                metadata={"model": self.vision_model}
            )

        except Exception as e:
            logger.warning(f"Vision analysis failed: {e}")
            return ModelResult(
                model_type=ModelType.OLLAMA_VISION,
                success=False,
                content=None,
                error=str(e),
                latency_ms=(time.time() - start) * 1000
            )

    async def _web_search(self, query: str) -> ModelResult:
        """Placeholder for web search integration."""
        # This would integrate with browser automation or search API
        # For now, return a placeholder
        return ModelResult(
            model_type=ModelType.BROWSER,
            success=False,
            content=None,
            error="Web search not yet implemented",
            metadata={"query": query}
        )

    # =========================================================================
    # PHASE 2: PRIMARY REASONING
    # =========================================================================

    async def _primary_reasoning(
        self,
        task: str,
        context: Optional[str],
        phase1_results: Dict[ModelType, ModelResult],
        available_tools: List[str],
    ) -> Optional[ModelResult]:
        """
        Primary reasoning using Kimi K2 or fallback.

        Args:
            task: Task to reason about
            context: Optional context string
            phase1_results: Results from phase 1 (vision, web)
            available_tools: List of available tool names

        Returns:
            ModelResult from primary reasoning model
        """
        start = time.time()

        # Build enriched context from phase 1 results
        enriched_context = self._build_enriched_context(context, phase1_results)

        # Try Kimi K2 first
        if self.kimi_client and KIMI_AVAILABLE:
            try:
                can_call, reason = await asyncio.wait_for(
                    self.kimi_client.can_call_async(),
                    timeout=5.0
                )

                if can_call:
                    plan = await asyncio.wait_for(
                        self.kimi_client.plan_task(
                            prompt=task,
                            available_tools=available_tools,
                            context=enriched_context,
                        ),
                        timeout=self.reasoning_timeout
                    )

                    if plan:
                        latency = (time.time() - start) * 1000
                        self.stats["model_usage"][ModelType.KIMI_K2.value] += 1

                        return ModelResult(
                            model_type=ModelType.KIMI_K2,
                            success=True,
                            content=plan,
                            latency_ms=latency,
                            confidence=0.9,  # Kimi K2 is high confidence
                            metadata={
                                "steps": len(plan.steps),
                                "estimated_iterations": plan.estimated_iterations,
                            }
                        )
                    else:
                        logger.warning("Kimi K2 planning returned None")
                else:
                    logger.debug(f"Kimi K2 not available: {reason}")
                    self.stats["fallbacks_triggered"] += 1

            except asyncio.TimeoutError:
                logger.warning(f"Kimi K2 timed out after {self.reasoning_timeout}s")
                self.stats["fallbacks_triggered"] += 1
            except Exception as e:
                logger.warning(f"Kimi K2 failed: {e}")
                self.stats["fallbacks_triggered"] += 1

        # Fallback: Use ChatGPT for reasoning if available
        if self.chatgpt_client:
            try:
                fallback_result = await asyncio.wait_for(
                    self._chatgpt_reasoning(task, enriched_context, available_tools),
                    timeout=self.reasoning_timeout
                )
                if fallback_result and fallback_result.success:
                    self.stats["model_usage"][ModelType.CHATGPT.value] += 1
                    return fallback_result
            except asyncio.TimeoutError:
                logger.warning(f"ChatGPT fallback timed out after {self.reasoning_timeout}s")
            except Exception as e:
                logger.warning(f"ChatGPT fallback failed: {e}")

        # Final fallback: Return basic plan structure
        logger.warning("All reasoning models failed, returning basic fallback")
        return ModelResult(
            model_type=ModelType.KIMI_K2,  # Pretend it's from Kimi for compatibility
            success=False,
            content=None,
            error="All reasoning models unavailable",
            latency_ms=(time.time() - start) * 1000,
            confidence=0.0
        )

    def _build_enriched_context(
        self,
        base_context: Optional[str],
        phase1_results: Dict[ModelType, ModelResult]
    ) -> str:
        """Build enriched context from base context + phase 1 results."""
        parts = []

        if base_context:
            parts.append(f"Context: {base_context}")

        # Add vision insights
        if ModelType.OLLAMA_VISION in phase1_results:
            vision = phase1_results[ModelType.OLLAMA_VISION]
            if vision.success:
                parts.append(f"Visual Analysis: {vision.content}")

        # Add web search results
        if ModelType.BROWSER in phase1_results:
            browser = phase1_results[ModelType.BROWSER]
            if browser.success:
                parts.append(f"Web Search: {browser.content}")

        return "\n\n".join(parts) if parts else ""

    async def _chatgpt_reasoning(
        self,
        task: str,
        context: str,
        available_tools: List[str]
    ) -> Optional[ModelResult]:
        """Use ChatGPT for reasoning (fallback)."""
        start = time.time()

        try:
            prompt = f"""Create a step-by-step plan for this task:

TASK: {task}

CONTEXT: {context}

AVAILABLE TOOLS: {', '.join(available_tools[:20])}

Respond with a JSON plan containing:
- summary: Brief task description
- steps: Array of steps with action, tool, arguments
- success_criteria: How to know task is complete"""

            response = await self.chatgpt_client.chat.completions.create(
                model=self._chatgpt_model,
                messages=[
                    {"role": "system", "content": "You are a task planning assistant. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000,
            )

            content = response.choices[0].message.content
            latency = (time.time() - start) * 1000

            # Try to parse as JSON
            import json
            try:
                plan_data = json.loads(content)
            except json.JSONDecodeError:
                # Extract JSON from markdown if needed
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                plan_data = json.loads(content.strip())

            return ModelResult(
                model_type=ModelType.CHATGPT,
                success=True,
                content=plan_data,
                latency_ms=latency,
                confidence=0.7,  # Lower confidence than Kimi K2
                metadata={
                    "model": self._chatgpt_model,
                    "usage": response.usage.total_tokens if response.usage else 0,
                }
            )

        except Exception as e:
            logger.warning(f"ChatGPT reasoning failed: {e}")
            return ModelResult(
                model_type=ModelType.CHATGPT,
                success=False,
                content=None,
                error=str(e),
                latency_ms=(time.time() - start) * 1000
            )

    # =========================================================================
    # PHASE 3: VERIFICATION
    # =========================================================================

    async def _verify_answer(
        self,
        task: str,
        proposed_answer: Any,
        context: Dict[ModelType, ModelResult],
    ) -> Optional[ModelResult]:
        """
        Verify answer using ChatGPT.

        Args:
            task: Original task
            proposed_answer: Answer to verify
            context: Context from other models

        Returns:
            ModelResult with verification result
        """
        if not self.chatgpt_client:
            return None

        start = time.time()

        try:
            # Build verification prompt
            prompt = f"""Verify this proposed solution:

TASK: {task}

PROPOSED SOLUTION:
{str(proposed_answer)[:1000]}

Is this solution:
1. Correct and complete?
2. Aligned with the task?
3. Likely to succeed?

Respond with JSON:
{{
    "verdict": "approve" or "reject",
    "confidence": 0.0-1.0,
    "reasoning": "why",
    "suggestions": ["improvement1", "improvement2"]
}}"""

            response = await asyncio.wait_for(
                self.chatgpt_client.chat.completions.create(
                    model=self._chatgpt_model,
                    messages=[
                        {"role": "system", "content": "You are a quality assurance assistant. Be critical but fair."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2,
                    max_tokens=500,
                ),
                timeout=self.verification_timeout
            )

            content = response.choices[0].message.content
            latency = (time.time() - start) * 1000

            # Parse verification result
            import json
            try:
                verification = json.loads(content)
            except json.JSONDecodeError:
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                verification = json.loads(content.strip())

            return ModelResult(
                model_type=ModelType.CHATGPT,
                success=True,
                content=verification,
                latency_ms=latency,
                confidence=verification.get("confidence", 0.5),
                metadata={
                    "verdict": verification.get("verdict"),
                    "model": self._chatgpt_model,
                }
            )

        except asyncio.TimeoutError:
            logger.warning(f"Verification timed out after {self.verification_timeout}s")
            return None
        except Exception as e:
            logger.warning(f"Verification failed: {e}")
            return None

    # =========================================================================
    # PHASE 4: SYNTHESIS
    # =========================================================================

    def _synthesize(self, result: OrchestratedResult) -> OrchestratedResult:
        """
        Synthesize final result from all model outputs.

        This includes:
        - Conflict detection and resolution
        - Confidence scoring
        - Fallback chain tracking
        """
        # Calculate confidence based on model agreement
        if ModelType.CHATGPT in result.model_results:
            verification = result.model_results[ModelType.CHATGPT]
            if verification.success and isinstance(verification.content, dict):
                verdict = verification.content.get("verdict")

                if verdict == "reject":
                    result.conflicts.append("Verification rejected primary answer")
                    result.confidence = 0.3  # Low confidence

                    # Add suggestions to metadata
                    suggestions = verification.content.get("suggestions", [])
                    if suggestions:
                        result.conflicts.extend([f"Suggestion: {s}" for s in suggestions])
                else:
                    # Verification approved - boost confidence
                    result.confidence = min(0.95, verification.confidence * 1.2)
        else:
            # No verification - use model self-confidence
            confidences = [
                r.confidence for r in result.model_results.values()
                if r.success and r.confidence > 0
            ]
            result.confidence = sum(confidences) / len(confidences) if confidences else 0.5

        # Track which models were used
        for model_type, model_result in result.model_results.items():
            if model_result.success:
                self.stats["model_usage"][model_type.value] += 1

        # Detect conflicts between models
        if len(result.model_results) > 1:
            # Check if vision detected errors but reasoning proceeded anyway
            vision = result.model_results.get(ModelType.OLLAMA_VISION)
            if vision and vision.success and isinstance(vision.content, str):
                if any(word in vision.content.lower() for word in ['error', 'failed', 'wrong']):
                    result.conflicts.append("Vision detected errors on page")
                    result.confidence *= 0.8  # Reduce confidence

        if result.conflicts:
            self.stats["conflicts_detected"] += 1

        return result

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def _update_stats(self, result: OrchestratedResult):
        """Update running statistics."""
        # Update averages
        total = self.stats["successful_executions"]

        # Running average for confidence
        prev_avg_conf = self.stats["avg_confidence"]
        self.stats["avg_confidence"] = (
            (prev_avg_conf * (total - 1) + result.confidence) / total
        )

        # Running average for execution time
        prev_avg_time = self.stats["avg_execution_time_ms"]
        self.stats["avg_execution_time_ms"] = (
            (prev_avg_time * (total - 1) + result.execution_time_ms) / total
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get orchestrator statistics."""
        return {
            **self.stats,
            "success_rate": (
                self.stats["successful_executions"] / self.stats["total_executions"]
                if self.stats["total_executions"] > 0 else 0.0
            ),
            "avg_confidence": round(self.stats["avg_confidence"], 3),
            "avg_execution_time_ms": round(self.stats["avg_execution_time_ms"], 1),
        }

    def reset_stats(self):
        """Reset statistics."""
        self.stats = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "avg_confidence": 0.0,
            "avg_execution_time_ms": 0.0,
            "model_usage": {m.value: 0 for m in ModelType},
            "conflicts_detected": 0,
            "fallbacks_triggered": 0,
        }

    async def close(self):
        """Clean up resources."""
        if self._chatgpt_client:
            await self._chatgpt_client.close()
            self._chatgpt_client = None

        if self.kimi_client:
            await self.kimi_client.close()


# =============================================================================
# GLOBAL SINGLETON
# =============================================================================

_orchestrator: Optional[ModelOrchestrator] = None


def get_orchestrator(
    kimi_client: Optional['KimiK2Client'] = None,
    event_bus: Optional['EventBus'] = None,
    **kwargs
) -> ModelOrchestrator:
    """Get or create global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ModelOrchestrator(
            kimi_client=kimi_client,
            event_bus=event_bus,
            **kwargs
        )
    return _orchestrator
