#!/usr/bin/env python3
"""
Advanced Causal Reasoning Examples for WorldModel

This demonstrates the new capabilities added to WorldModel:
1. Temporal causality (time-delayed effects)
2. Hidden variable inference
3. Bayesian uncertainty quantification
4. Multi-agent causal reasoning
"""

import asyncio
import time
from world_model import WorldModel


async def demo_temporal_reasoning():
    """Demonstrate temporal causal reasoning."""
    print("\n=== TEMPORAL CAUSAL REASONING ===")

    wm = WorldModel()
    await wm.initialize()

    # Enable temporal reasoning
    wm.add_temporal_reasoning()

    # Add temporal rules: "Send email" → "Customer replies" (delay: 3600s, variance: 600s)
    wm.temporal_graph.add_temporal_rule(
        cause="Send email to customer",
        effect="Customer replies",
        probability=0.7,
        delay_seconds=3600,  # 1 hour
        variance=600  # ±10 minutes
    )

    # Predict WHEN effect will occur
    cause_time = time.time()
    predictions = await wm.predict_temporal("Send email to customer", cause_time)

    for pred in predictions:
        print(f"Effect: {pred['effect']}")
        print(f"Probability: {pred['probability']:.2f}")
        print(f"Expected time: {pred['expected_time'] - cause_time:.0f}s from now")
        print(f"Time window: {pred['time_window'][0] - cause_time:.0f}s to {pred['time_window'][1] - cause_time:.0f}s")

    # Observe actual sequence and learn
    wm.temporal_graph.observe_sequence("Send email to customer", "Customer replies", 3900)  # 65 minutes

    print(f"\nObserved sequences: {len(wm.temporal_graph.observed_sequences)}")


async def demo_hidden_variable_detection():
    """Demonstrate hidden variable inference."""
    print("\n=== HIDDEN VARIABLE DETECTION ===")

    wm = WorldModel()
    await wm.initialize()

    # Enable hidden variable detection
    wm.add_hidden_variable_detection()

    # Record correlations between observable variables
    # Scenario: Sales and website traffic both increase, but neither causes the other
    wm.hidden_detector.record_correlation("sales_increased", "traffic_increased", 0.85)
    wm.hidden_detector.record_correlation("sales_increased", "social_buzz", 0.82)
    wm.hidden_detector.record_correlation("traffic_increased", "social_buzz", 0.88)

    # Detect hidden cause
    effects = ["sales_increased", "traffic_increased", "social_buzz"]
    hidden = await wm.detect_hidden_causes(effects, threshold=0.7)

    if hidden:
        print(f"Hidden variable detected: {hidden.name}")
        print(f"Inferred from: {hidden.inferred_from}")
        print(f"Probability: {hidden.probability:.2f}")
        print(f"Hypothesized effects: {hidden.hypothesized_effects}")

    # Try to explain unexplained effect
    explanation = wm.hidden_detector.explain_unexplained("sudden_spike_in_demand")
    if explanation:
        print(f"\nExplanation: {explanation}")


async def demo_bayesian_reasoning():
    """Demonstrate Bayesian causal network."""
    print("\n=== BAYESIAN CAUSAL REASONING ===")

    wm = WorldModel()
    await wm.initialize()

    # Enable Bayesian network
    wm.add_bayesian_network()

    # Build a simple network: Rain → Sprinkler ← Time
    # Rain → Wet Grass ← Sprinkler

    # Add nodes
    wm.bayesian_network.add_node("rain", prior=0.2)
    wm.bayesian_network.add_node("time_is_morning", prior=0.5)

    # Sprinkler depends on rain and time
    wm.bayesian_network.add_node(
        "sprinkler_on",
        prior=0.3,
        parents=["rain", "time_is_morning"],
        cpt={
            (True, True): 0.01,   # Rain + morning → sprinkler unlikely
            (True, False): 0.01,  # Rain + not morning → sprinkler unlikely
            (False, True): 0.8,   # No rain + morning → sprinkler likely
            (False, False): 0.2   # No rain + not morning → sprinkler less likely
        }
    )

    # Wet grass depends on rain and sprinkler
    wm.bayesian_network.add_node(
        "wet_grass",
        prior=0.4,
        parents=["rain", "sprinkler_on"],
        cpt={
            (True, True): 0.99,   # Both rain and sprinkler → very likely wet
            (True, False): 0.90,  # Rain only → likely wet
            (False, True): 0.85,  # Sprinkler only → likely wet
            (False, False): 0.05  # Neither → unlikely wet
        }
    )

    # Query: What's probability of wet grass?
    prob, conf = await wm.bayesian_query("wet_grass")
    print(f"P(wet_grass) = {prob:.2f} ± {conf:.2f}")

    # Query given evidence: We observe it's morning and grass is wet
    prob, conf = await wm.bayesian_query(
        "rain",
        evidence={"time_is_morning": True, "wet_grass": True}
    )
    print(f"P(rain | morning, wet_grass) = {prob:.2f} ± {conf:.2f}")

    # Intervention: What if we FORCE sprinkler on?
    results = await wm.bayesian_intervention("sprinkler_on", True)
    print(f"\nAfter do(sprinkler_on=True):")
    for node, prob in results.items():
        print(f"  P({node}) = {prob:.2f}")

    # Counterfactual: "If it had rained, would grass be wet?"
    cf_prob = await wm.bayesian_counterfactual(
        observation={"wet_grass": False, "rain": False},
        intervention={"rain": True},
        query_node="wet_grass"
    )
    print(f"\nCounterfactual: If it had rained, P(wet_grass) = {cf_prob:.2f}")


async def demo_multi_agent_reasoning():
    """Demonstrate multi-agent causal reasoning."""
    print("\n=== MULTI-AGENT CAUSAL REASONING ===")

    wm = WorldModel()
    await wm.initialize()

    # Enable multi-agent reasoning
    wm.add_multi_agent_reasoning()

    # Model a competitor agent
    wm.multi_agent.model_agent(
        agent_id="competitor_A",
        beliefs={"market_share": 0.3, "customer_satisfaction": 0.7},
        goals=["increase market share", "reduce costs", "launch new product"],
        capabilities=["price_discount", "marketing_campaign", "product_development"]
    )

    # Predict what competitor will do
    context = {"quarter": "Q4", "market_trend": "growing"}
    predictions = await wm.predict_agent_behavior("competitor_A", context)

    print("Predicted competitor actions:")
    for pred in predictions:
        print(f"  - {pred}")

    # Observe competitor action and explain
    explanation = await wm.explain_agent_behavior(
        "competitor_A",
        "launched aggressive marketing_campaign"
    )
    print(f"\nExplanation: {explanation}")

    # Record interaction
    wm.multi_agent.record_interaction(
        "competitor_A",
        "launched aggressive marketing_campaign",
        "gained 5% market share"
    )

    print(f"\nInteraction history: {len(wm.multi_agent.interaction_history)} events")


async def demo_integrated_reasoning():
    """Demonstrate all capabilities working together."""
    print("\n=== INTEGRATED ADVANCED REASONING ===")

    wm = WorldModel()
    await wm.initialize()

    # Enable all advanced features
    wm.add_temporal_reasoning()
    wm.add_hidden_variable_detection()
    wm.add_bayesian_network()
    wm.add_multi_agent_reasoning()

    print("All advanced causal reasoning capabilities enabled:")
    print("  ✓ Temporal causality")
    print("  ✓ Hidden variable inference")
    print("  ✓ Bayesian uncertainty quantification")
    print("  ✓ Multi-agent reasoning")

    # Example: Customer churn scenario
    print("\nScenario: Predicting customer churn with multiple factors")

    # Build Bayesian network for churn
    wm.bayesian_network.add_node("competitor_launched_product", prior=0.3)
    wm.bayesian_network.add_node("customer_support_slow", prior=0.2)
    wm.bayesian_network.add_node(
        "customer_churn",
        prior=0.15,
        parents=["competitor_launched_product", "customer_support_slow"],
        cpt={
            (True, True): 0.7,   # Both factors → high churn
            (True, False): 0.4,  # Competitor only → medium churn
            (False, True): 0.3,  # Support issue only → medium churn
            (False, False): 0.1  # Neither → low churn
        }
    )

    # Query churn probability
    prob, conf = await wm.bayesian_query("customer_churn")
    print(f"\nBase churn probability: {prob:.2f} ± {conf:.2f}")

    # Model competitor
    wm.multi_agent.model_agent(
        "competitor_B",
        goals=["steal our customers"],
        capabilities=["launch_product", "offer_discount"]
    )

    # Predict competitor action
    comp_actions = await wm.predict_agent_behavior("competitor_B", {})
    print(f"Predicted competitor actions: {comp_actions}")

    # Intervention: What if we improve support speed?
    results = await wm.bayesian_intervention("customer_support_slow", False)
    print(f"\nIf we improve support: P(customer_churn) = {results.get('customer_churn', 0):.2f}")

    # Add temporal prediction: When will churn happen?
    wm.temporal_graph.add_temporal_rule(
        "competitor_launched_product",
        "customer_churn",
        probability=0.4,
        delay_seconds=7 * 24 * 3600,  # 7 days
        variance=2 * 24 * 3600  # ±2 days
    )

    temporal_preds = await wm.predict_temporal("competitor_launched_product")
    if temporal_preds:
        pred = temporal_preds[0]
        print(f"\nTemporal prediction: Churn will occur in {pred['expected_time'] - time.time():.0f}s")


async def main():
    """Run all demonstrations."""
    print("=" * 60)
    print("WORLD MODEL - ADVANCED CAUSAL REASONING DEMONSTRATIONS")
    print("=" * 60)

    await demo_temporal_reasoning()
    await demo_hidden_variable_detection()
    await demo_bayesian_reasoning()
    await demo_multi_agent_reasoning()
    await demo_integrated_reasoning()

    print("\n" + "=" * 60)
    print("All demonstrations complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
