#!/usr/bin/env python3
"""
Test script for LLM fallback chain.

Demonstrates:
1. Fallback from Kimi → Llama → Ollama on timeout/failure
2. Cost tracking and savings estimation
3. Minor re-plan optimization (skip Kimi)
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.llm_fallback_chain import (
    LLMFallbackChain,
    FallbackConfig,
    LLMTier,
)
from agent.kimi_k2_client import get_kimi_client
from loguru import logger


async def test_fallback_chain():
    """Test the fallback chain with various scenarios."""

    logger.info("=" * 60)
    logger.info("Testing LLM Fallback Chain")
    logger.info("=" * 60)

    # Initialize Kimi client (optional - works without it too)
    try:
        kimi_client = get_kimi_client()
        logger.info(f"Kimi client available: {kimi_client.is_available()}")
    except Exception as e:
        logger.warning(f"Kimi client not available: {e}")
        kimi_client = None

    # Create fallback chain with Llama as primary
    config = FallbackConfig(
        primary_llm=LLMTier.LLAMA_31_8B,  # Start with free Llama
        kimi_timeout=5.0,
        llama_timeout=8.0,
        ollama_timeout=5.0,
        max_retries_per_tier=2,
        use_llama_for_minor_replans=True,
        llama_model="llama3.1:8b",
        ollama_model="qwen2.5:7b-instruct",
        llama_url="http://localhost:11434",
        ollama_url="http://localhost:11434",
    )

    chain = LLMFallbackChain(config=config, kimi_client=kimi_client)

    # Test 1: Simple planning task (should use Llama)
    logger.info("\n" + "=" * 60)
    logger.info("Test 1: Simple planning task (Llama)")
    logger.info("=" * 60)

    system_prompt = "You are a helpful planning assistant."
    user_prompt = "Create a 3-step plan to research a company online."

    result = await chain.call_with_fallback(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        is_minor_replan=False,
        temperature=0.3,
        max_tokens=1024,
    )

    if result.success:
        logger.info(f"✓ Success! Tier used: {result.tier_used.name}")
        logger.info(f"  Latency: {result.latency_ms}ms")
        logger.info(f"  Response preview: {result.content[:200]}...")
    else:
        logger.error(f"✗ Failed: {result.error}")

    # Test 2: Minor re-plan (should definitely skip Kimi, use Llama)
    logger.info("\n" + "=" * 60)
    logger.info("Test 2: Minor re-plan (should use Llama, skip Kimi)")
    logger.info("=" * 60)

    user_prompt_2 = "Adjust the plan: add a step to verify the company exists."

    result2 = await chain.call_with_fallback(
        system_prompt=system_prompt,
        user_prompt=user_prompt_2,
        is_minor_replan=True,  # This should skip Kimi
        temperature=0.3,
        max_tokens=1024,
    )

    if result2.success:
        logger.info(f"✓ Success! Tier used: {result2.tier_used.name}")
        logger.info(f"  Latency: {result2.latency_ms}ms")
        if result2.tier_used != LLMTier.KIMI_K2:
            logger.info("  ✓ Correctly skipped expensive Kimi for minor re-plan")
    else:
        logger.error(f"✗ Failed: {result2.error}")

    # Show cost report
    logger.info("\n" + "=" * 60)
    logger.info("Cost Report")
    logger.info("=" * 60)

    report = chain.get_cost_report()
    logger.info(f"Calls breakdown:")
    logger.info(f"  Kimi K2: {report['calls']['kimi_k2']}")
    logger.info(f"  Llama 3.1 8B: {report['calls']['llama_3.1_8b']}")
    logger.info(f"  Ollama 7B: {report['calls']['ollama_7b']}")
    logger.info(f"  Total: {report['calls']['total']}")
    logger.info(f"\nCosts:")
    logger.info(f"  Kimi cost: ${report['kimi_cost_usd']:.4f}")
    logger.info(f"  Estimated savings: ${report['estimated_savings_usd']:.4f}")
    logger.info(f"  Free call %: {report['free_call_percentage']:.1f}%")

    # Cleanup
    await chain.close()

    logger.info("\n" + "=" * 60)
    logger.info("Test complete!")
    logger.info("=" * 60)


async def test_strategic_planner_integration():
    """Test the strategic planner with fallback chain."""

    logger.info("\n\n" + "=" * 60)
    logger.info("Testing Strategic Planner Integration")
    logger.info("=" * 60)

    from agent.strategic_planner import get_strategic_planner
    from agent.config_loader import load_config

    # Load config
    config = load_config()

    # Create planner
    planner = get_strategic_planner(config)

    logger.info(f"Planner initialized with fallback: {planner.fallback_chain is not None}")

    # Test planning
    prompt = "Search Google for 'AI automation tools' and extract the top 3 results"
    available_tools = [
        "playwright_navigate",
        "playwright_fill",
        "playwright_click",
        "playwright_extract_entities",
        "playwright_screenshot",
    ]

    logger.info(f"\nPrompt: {prompt}")
    logger.info(f"Available tools: {len(available_tools)}")

    # Check if we should plan
    should_plan = await planner.should_plan(prompt)
    logger.info(f"Should use strategic planning: {should_plan}")

    if should_plan:
        # Create plan
        state = await planner.plan(prompt, available_tools)

        if state:
            logger.info(f"✓ Plan created successfully!")
            logger.info(f"  Summary: {state.plan.summary}")
            logger.info(f"  Steps: {len(state.plan.steps)}")
            for i, step in enumerate(state.plan.steps[:3], 1):
                logger.info(f"    {i}. {step.action} ({step.tool})")
            if len(state.plan.steps) > 3:
                logger.info(f"    ... and {len(state.plan.steps) - 3} more steps")
        else:
            logger.warning("Planning returned None")

    # Show cost report
    logger.info("\n" + "=" * 60)
    logger.info("Strategic Planner Cost Report")
    logger.info("=" * 60)

    cost_report = planner.get_cost_report()
    if cost_report.get("fallback_enabled"):
        logger.info(f"Calls breakdown:")
        logger.info(f"  Kimi K2: {cost_report['calls']['kimi_k2']}")
        logger.info(f"  Llama 3.1 8B: {cost_report['calls']['llama_3.1_8b']}")
        logger.info(f"  Ollama 7B: {cost_report['calls']['ollama_7b']}")
        logger.info(f"\nSavings: ${cost_report['estimated_savings_usd']:.4f}")
        logger.info(f"Free call %: {cost_report['free_call_percentage']:.1f}%")
    else:
        logger.info("Fallback chain not enabled")

    # Cleanup
    await planner.close()


if __name__ == "__main__":
    # Run tests
    asyncio.run(test_fallback_chain())
    asyncio.run(test_strategic_planner_integration())
