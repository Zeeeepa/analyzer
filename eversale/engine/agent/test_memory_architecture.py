#!/usr/bin/env python3
"""
Test script for Memory Architecture
Demonstrates core functionality and integration patterns.
"""

import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.memory_architecture import (
    MemoryArchitecture,
    WorkingMemoryStep,
    MemoryImportance,
    MemoryType
)


def test_basic_workflow():
    """Test basic memory workflow."""
    print("\n" + "="*60)
    print("TEST 1: Basic Memory Workflow")
    print("="*60)

    # Create memory system
    memory = MemoryArchitecture(auto_consolidate=False)  # Disable auto-consolidate for testing

    print("\n1. Adding steps to working memory...")

    # Simulate task execution
    steps = [
        ("Navigate to Facebook Ads Library", "Page loaded successfully", True),
        ("Search for 'dog food' advertisers", "Found 23 advertisers", True),
        ("Extract advertiser details", "Extracted 23 advertiser pages", True),
        ("Visit advertiser websites", "Visited 23 websites", True),
        ("Extract contact information", "Found 18 emails, 12 phone numbers", True),
        ("Save to CSV", "Saved to leads_dogfood.csv", True)
    ]

    for action, observation, success in steps:
        memory.add_step(
            action=action,
            observation=observation,
            reasoning="Executing SDR workflow",
            success=success
        )
        print(f"  ✓ {action}")

    print(f"\nWorking memory: {len(memory.working.steps)} steps")

    # Get context (should be compressed for older steps)
    print("\n2. Getting context for LLM...")
    context = memory.get_context(detailed_steps=3)
    print(f"Context length: {len(context)} chars")
    print(f"First 300 chars: {context[:300]}...")

    # Save as episode
    print("\n3. Saving episode to long-term memory...")
    episode = memory.save_episode(
        task_prompt="Find leads from Facebook Ads Library for 'dog food'",
        outcome="Successfully extracted 18 emails and 12 phone numbers",
        success=True,
        duration_seconds=45.7,
        tags=["sdr", "facebook", "leads", "pet_industry"],
        importance=0.8
    )

    print(f"  Episode ID: {episode.memory_id}")
    print(f"  Original tokens: {episode.original_tokens}")
    print(f"  Compressed tokens: {episode.compressed_tokens}")
    if episode.original_tokens > 0:
        reduction = (1 - episode.compressed_tokens / episode.original_tokens) * 100
        print(f"  Compression ratio: {reduction:.1f}%")

    print("\n✅ Test 1 passed!")


def test_semantic_search():
    """Test semantic search across memories."""
    print("\n" + "="*60)
    print("TEST 2: Semantic Search")
    print("="*60)

    memory = MemoryArchitecture(auto_consolidate=False)

    # Add multiple episodes
    print("\n1. Creating multiple episodes...")

    episodes_data = [
        ("Extract leads from Facebook Ads", "facebook extraction", ["facebook", "leads"]),
        ("Scrape LinkedIn profiles", "linkedin scraping", ["linkedin", "profiles"]),
        ("Monitor Reddit for warm signals", "reddit monitoring", ["reddit", "sentiment"]),
        ("Extract contacts from company website", "website extraction", ["website", "contacts"]),
    ]

    for prompt, outcome, tags in episodes_data:
        # Add some steps
        memory.add_step(f"Execute {prompt}", f"Completed: {outcome}", success=True)

        # Save episode
        memory.save_episode(
            task_prompt=prompt,
            outcome=outcome,
            success=True,
            duration_seconds=30.0,
            tags=tags
        )
        print(f"  ✓ {prompt}")

    # Search
    print("\n2. Searching for 'extract contact information'...")
    results = memory.search_episodes(
        query="extract contact information",
        limit=3
    )

    print(f"\nFound {len(results)} relevant episodes:")
    for i, ep in enumerate(results, 1):
        print(f"  {i}. {ep.task_prompt}")
        print(f"     Relevance score: {ep.composite_score:.3f}")
        print(f"     Tags: {', '.join(ep.tags)}")

    print("\n✅ Test 2 passed!")


def test_skill_management():
    """Test skill creation and retrieval."""
    print("\n" + "="*60)
    print("TEST 3: Skill Management")
    print("="*60)

    memory = MemoryArchitecture(auto_consolidate=False)

    # Create a skill
    print("\n1. Creating reusable skill...")
    skill = memory.save_skill(
        skill_name="extract_fb_ads_leads",
        description="Extract leads from Facebook Ads Library for a given search term",
        action_sequence=[
            {"step": 1, "action": "navigate", "url": "facebook.com/ads/library"},
            {"step": 2, "action": "search", "query": "{search_term}"},
            {"step": 3, "action": "extract_ads", "max_results": 50},
            {"step": 4, "action": "visit_advertisers"},
            {"step": 5, "action": "extract_contacts"},
            {"step": 6, "action": "save_csv", "filename": "leads_{search_term}.csv"}
        ],
        preconditions=["facebook_accessible", "logged_in"],
        postconditions=["leads_extracted", "csv_saved"],
        tags=["facebook", "leads", "sdr"]
    )

    print(f"  ✓ Skill created: {skill.skill_name}")
    print(f"    Steps: {len(skill.action_sequence)}")

    # Simulate executions
    print("\n2. Simulating skill executions...")
    executions = [
        (True, 42.3),   # Success, 42.3s
        (True, 38.7),   # Success, 38.7s
        (False, 15.2),  # Failure, 15.2s
        (True, 41.1),   # Success, 41.1s
        (True, 39.8),   # Success, 39.8s
    ]

    for i, (success, duration) in enumerate(executions, 1):
        memory.record_skill_execution(
            skill_name="extract_fb_ads_leads",
            success=success,
            duration=duration
        )
        status = "✓" if success else "✗"
        print(f"  {status} Execution {i}: {duration}s")

    # Retrieve and check statistics
    print("\n3. Retrieving skill statistics...")
    skill = memory.get_skill("extract_fb_ads_leads")

    print(f"  Skill: {skill.skill_name}")
    print(f"  Success rate: {skill.success_rate:.1%}")
    print(f"  Times executed: {skill.times_executed}")
    print(f"  Average duration: {skill.average_duration:.1f}s")

    # Search skills
    print("\n4. Searching skills...")
    results = memory.search_skills("extract leads from facebook")
    print(f"  Found {len(results)} matching skills")
    for skill in results:
        print(f"    - {skill.skill_name} (score: {skill.composite_score:.3f})")

    print("\n✅ Test 3 passed!")


def test_enriched_context():
    """Test enriched context with all memory types."""
    print("\n" + "="*60)
    print("TEST 4: Enriched Context")
    print("="*60)

    memory = MemoryArchitecture(auto_consolidate=False)

    # Setup memories
    print("\n1. Setting up test data...")

    # Add working memory steps
    memory.add_step(
        "Navigate to LinkedIn",
        "Page loaded",
        success=True
    )
    memory.add_step(
        "Attempt to extract profiles",
        "Login wall detected",
        success=False
    )

    # Add an episode
    memory.save_episode(
        task_prompt="Extract LinkedIn profiles",
        outcome="Failed due to login wall",
        success=False,
        duration_seconds=12.5,
        tags=["linkedin", "failed"]
    )

    # Add another episode (success)
    memory.add_step("Login to LinkedIn", "Logged in successfully", success=True)
    memory.add_step("Extract profiles", "Extracted 50 profiles", success=True)

    memory.save_episode(
        task_prompt="Extract LinkedIn profiles after login",
        outcome="Successfully extracted 50 profiles",
        success=True,
        duration_seconds=45.2,
        tags=["linkedin", "success"]
    )

    # Add a skill
    memory.save_skill(
        skill_name="linkedin_profile_extraction",
        description="Extract LinkedIn profiles with login",
        action_sequence=[
            {"step": 1, "action": "login"},
            {"step": 2, "action": "search"},
            {"step": 3, "action": "extract"}
        ],
        tags=["linkedin"]
    )

    print("  ✓ Added working memory, episodes, and skill")

    # Get enriched context
    print("\n2. Getting enriched context...")
    context = memory.get_enriched_context(
        query="extract LinkedIn profiles",
        detailed_steps=5,
        limit_per_type=2
    )

    print(f"\nEnriched context ({len(context)} chars):")
    print("-" * 60)
    print(context[:800])
    if len(context) > 800:
        print("...")
    print("-" * 60)

    print("\n✅ Test 4 passed!")


def test_memory_consolidation():
    """Test memory consolidation."""
    print("\n" + "="*60)
    print("TEST 5: Memory Consolidation")
    print("="*60)

    memory = MemoryArchitecture(auto_consolidate=False)

    # Create similar episodes
    print("\n1. Creating similar episodes...")

    for i in range(5):
        # Add steps
        memory.add_step(
            f"Navigate to example{i}.com",
            "Page loaded",
            success=True
        )
        memory.add_step(
            "Extract contact info",
            f"Found {20 + i} contacts",
            success=True
        )

        # Save episode
        memory.save_episode(
            task_prompt=f"Extract contacts from example{i}.com",
            outcome=f"Extracted {20 + i} contacts",
            success=True,
            duration_seconds=30.0 + i,
            tags=["extraction", "contacts", "website"]
        )

    print(f"  ✓ Created 5 similar episodes")

    # Check episode count before
    stats_before = memory.get_stats()
    episode_count_before = stats_before['episodic_memory']['total_episodes']
    print(f"  Episodes before consolidation: {episode_count_before}")

    # Consolidate
    print("\n2. Running consolidation...")
    memory.consolidate_now()

    # Check episode count after
    stats_after = memory.get_stats()
    episode_count_after = stats_after['episodic_memory']['total_episodes']
    semantic_count = stats_after['semantic_memory']['total_patterns']

    print(f"  Episodes after consolidation: {episode_count_after}")
    print(f"  Semantic patterns extracted: {semantic_count}")

    if semantic_count > 0:
        print("\n3. Searching semantic memories...")
        semantics = memory.search_semantic("extract contacts from website", limit=3)
        for sem in semantics:
            print(f"  Pattern: {sem.pattern}")
            print(f"  Confidence: {sem.confidence:.1%}")

    print("\n✅ Test 5 passed!")


def test_statistics():
    """Test statistics and monitoring."""
    print("\n" + "="*60)
    print("TEST 6: Statistics & Monitoring")
    print("="*60)

    memory = MemoryArchitecture(auto_consolidate=False)

    # Add some data
    print("\n1. Adding test data...")

    for i in range(3):
        memory.add_step(f"Action {i}", f"Result {i}", success=True)

    memory.save_episode(
        task_prompt="Test task",
        outcome="Success",
        success=True,
        duration_seconds=10.0
    )

    # Get statistics
    print("\n2. Getting statistics...")
    memory.print_stats()

    # Test get_stats API
    stats = memory.get_stats()
    print("\n3. Statistics object:")
    print(f"  Working memory steps: {stats['working_memory']['current_steps']}")
    print(f"  Total episodes: {stats['episodic_memory']['total_episodes']}")
    print(f"  Token reduction: {stats['compression']['token_reduction']}")

    print("\n✅ Test 6 passed!")


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*60)
    print("MEMORY ARCHITECTURE TEST SUITE")
    print("="*60)

    tests = [
        test_basic_workflow,
        test_semantic_search,
        test_skill_management,
        test_enriched_context,
        test_memory_consolidation,
        test_statistics
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Passed: {passed}/{len(tests)}")
    print(f"Failed: {failed}/{len(tests)}")

    if failed == 0:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {failed} test(s) failed")

    return failed == 0


if __name__ == "__main__":
    # Run tests
    success = run_all_tests()

    # Exit code
    sys.exit(0 if success else 1)
