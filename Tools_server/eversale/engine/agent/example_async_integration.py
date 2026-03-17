#!/usr/bin/env python3
"""
Example: Integrating Async Memory with Parallel Agents

This demonstrates how to use the async memory architecture with
multiple parallel agents working on different tasks simultaneously.

Scenario: 3 parallel agents, each processing different tasks and
sharing a common memory pool safely.
"""

import asyncio
import hashlib
from datetime import datetime
from typing import List

try:
    from memory_architecture_async import (
        AsyncEpisodicMemoryStore,
        AsyncSemanticMemoryStore,
        AsyncSkillMemoryStore,
    )
    from memory_architecture import (
        EpisodicMemory,
        SemanticMemory,
        SkillMemory,
        MemoryType,
    )
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure all memory architecture files are in the same directory")
    exit(1)


# ============================================================================
# AGENT IMPLEMENTATION
# ============================================================================

class ParallelAgent:
    """
    A parallel agent that can work independently while sharing memory.
    """

    def __init__(
        self,
        agent_id: int,
        episodic_store: AsyncEpisodicMemoryStore,
        semantic_store: AsyncSemanticMemoryStore,
        skill_store: AsyncSkillMemoryStore
    ):
        self.agent_id = agent_id
        self.episodic = episodic_store
        self.semantic = semantic_store
        self.skills = skill_store
        self.session_id = f"agent_{agent_id}_session"

    async def execute_task(self, task_description: str) -> EpisodicMemory:
        """
        Execute a task and store it in memory.

        Steps:
        1. Search for relevant past experiences
        2. Search for relevant knowledge
        3. Search for relevant skills
        4. Execute the task (simulated)
        5. Store the experience in episodic memory
        """
        print(f"[Agent {self.agent_id}] Starting task: {task_description}")

        # Step 1: Search past experiences (parallel read)
        print(f"[Agent {self.agent_id}] Searching past experiences...")
        past_episodes = await self.episodic.search_episodes_async(
            query=task_description,
            limit=3
        )
        print(f"[Agent {self.agent_id}] Found {len(past_episodes)} relevant experiences")

        # Step 2: Search knowledge (parallel read)
        print(f"[Agent {self.agent_id}] Searching knowledge base...")
        relevant_knowledge = await self.semantic.search_semantic_async(
            query=task_description,
            limit=2
        )
        print(f"[Agent {self.agent_id}] Found {len(relevant_knowledge)} relevant patterns")

        # Step 3: Search skills (parallel read)
        print(f"[Agent {self.agent_id}] Searching skill library...")
        relevant_skills = await self.skills.search_skills_async(
            query=task_description,
            limit=2
        )
        print(f"[Agent {self.agent_id}] Found {len(relevant_skills)} relevant skills")

        # Step 4: Execute task (simulated)
        print(f"[Agent {self.agent_id}] Executing task...")
        await asyncio.sleep(0.1)  # Simulate work

        # Step 5: Store experience (exclusive write)
        print(f"[Agent {self.agent_id}] Storing experience in memory...")
        memory_id = hashlib.sha256(
            f"agent_{self.agent_id}_{task_description}_{datetime.now()}".encode()
        ).hexdigest()[:16]

        episode = EpisodicMemory(
            memory_id=memory_id,
            memory_type=MemoryType.EPISODIC,
            task_prompt=task_description,
            content=f"Agent {self.agent_id} completed: {task_description}",
            compressed_content=f"Completed {task_description}",
            outcome="success",
            success=True,
            duration_seconds=0.1,
            tools_used=["search", "execute"],
            created_at=datetime.now().isoformat(),
            last_accessed=datetime.now().isoformat(),
            access_count=0,
            importance=0.7,
            composite_score=0.8,
            task_id=f"task_{self.agent_id}_{memory_id}",
            session_id=self.session_id,
            tags=["completed", f"agent_{self.agent_id}"],
            embedding=[0.1 * i for i in range(10)],
            reflection_ids=[]
        )

        await self.episodic.add_episode_async(episode)
        print(f"[Agent {self.agent_id}] Task completed and stored!")

        return episode

    async def learn_from_experiences(self):
        """
        Extract patterns from experiences and add to semantic memory.
        """
        print(f"[Agent {self.agent_id}] Learning from experiences...")

        # Get agent's own experiences
        my_episodes = await self.episodic.search_episodes_async(
            session_id=self.session_id,
            success_only=True,
            limit=10
        )

        if len(my_episodes) < 2:
            print(f"[Agent {self.agent_id}] Not enough experiences to learn from yet")
            return

        # Extract a pattern (simplified)
        pattern_id = hashlib.sha256(
            f"pattern_agent_{self.agent_id}_{datetime.now()}".encode()
        ).hexdigest()[:16]

        pattern = SemanticMemory(
            memory_id=pattern_id,
            memory_type=MemoryType.SEMANTIC,
            pattern=f"Agent {self.agent_id} task execution pattern",
            context="Learned from successful task completions",
            content=f"Pattern: {len(my_episodes)} successful tasks completed",
            confidence=0.8,
            times_validated=len(my_episodes),
            times_invalidated=0,
            created_at=datetime.now().isoformat(),
            last_accessed=datetime.now().isoformat(),
            access_count=0,
            importance=0.7,
            composite_score=0.75,
            tags=["learned", f"agent_{self.agent_id}"],
            embedding=[0.2 * i for i in range(10)],
            source_episodes=[ep.memory_id for ep in my_episodes]
        )

        await self.semantic.add_semantic_async(pattern)
        print(f"[Agent {self.agent_id}] Learned new pattern from {len(my_episodes)} experiences")

    async def share_skill(self, skill_name: str, description: str):
        """
        Share a skill with other agents via skill memory.
        """
        print(f"[Agent {self.agent_id}] Sharing skill: {skill_name}")

        skill_id = hashlib.sha256(
            f"skill_{skill_name}_{self.agent_id}".encode()
        ).hexdigest()[:16]

        skill = SkillMemory(
            memory_id=skill_id,
            memory_type=MemoryType.SKILL,
            skill_name=skill_name,
            description=description,
            content=f"Skill shared by Agent {self.agent_id}",
            action_sequence=[
                {"step": 1, "action": "prepare"},
                {"step": 2, "action": "execute"},
                {"step": 3, "action": "verify"}
            ],
            preconditions=["task_ready"],
            postconditions=["task_complete"],
            success_rate=0.85,
            times_executed=10,
            average_duration=0.5,
            created_at=datetime.now().isoformat(),
            last_accessed=datetime.now().isoformat(),
            access_count=0,
            importance=0.8,
            composite_score=0.85,
            tags=["shared", f"agent_{self.agent_id}"],
            embedding=[0.3 * i for i in range(10)],
            error_handling=[],
            decision_logic=[]
        )

        await self.skills.add_skill_async(skill)
        print(f"[Agent {self.agent_id}] Skill '{skill_name}' shared successfully")


# ============================================================================
# EXAMPLE SCENARIOS
# ============================================================================

async def scenario_1_parallel_task_execution():
    """
    Scenario 1: Multiple agents executing different tasks in parallel.

    Demonstrates:
    - Safe concurrent reads (agents search memory simultaneously)
    - Safe concurrent writes (agents store experiences without conflicts)
    """
    print("\n" + "=" * 70)
    print("SCENARIO 1: Parallel Task Execution")
    print("=" * 70)
    print("\n3 agents working on different tasks simultaneously")
    print("Each agent: searches memory → executes task → stores result\n")

    # Shared memory stores
    episodic = AsyncEpisodicMemoryStore()
    semantic = AsyncSemanticMemoryStore()
    skills = AsyncSkillMemoryStore()

    # Create 3 agents
    agents = [
        ParallelAgent(1, episodic, semantic, skills),
        ParallelAgent(2, episodic, semantic, skills),
        ParallelAgent(3, episodic, semantic, skills),
    ]

    # Each agent works on different tasks in parallel
    tasks = [
        "Process customer orders",
        "Analyze sales data",
        "Generate reports"
    ]

    print("[Coordinator] Starting parallel task execution...\n")

    # Execute all tasks in parallel (safe due to RW locks)
    results = await asyncio.gather(*[
        agent.execute_task(task)
        for agent, task in zip(agents, tasks)
    ])

    print(f"\n[Coordinator] All {len(results)} tasks completed successfully!")
    print("[Coordinator] Memory safely updated by all agents concurrently")


async def scenario_2_collaborative_learning():
    """
    Scenario 2: Agents learning from shared experiences.

    Demonstrates:
    - Agents reading shared memory pool
    - Extracting patterns from collective experiences
    - Contributing learned knowledge back to shared memory
    """
    print("\n" + "=" * 70)
    print("SCENARIO 2: Collaborative Learning")
    print("=" * 70)
    print("\n3 agents learning from shared experience pool\n")

    # Shared memory stores
    episodic = AsyncEpisodicMemoryStore()
    semantic = AsyncSemanticMemoryStore()
    skills = AsyncSkillMemoryStore()

    # Create agents
    agents = [
        ParallelAgent(1, episodic, semantic, skills),
        ParallelAgent(2, episodic, semantic, skills),
        ParallelAgent(3, episodic, semantic, skills),
    ]

    # First, each agent executes some tasks to build experience
    print("[Coordinator] Phase 1: Building shared experience pool\n")

    initial_tasks = [
        ["Task A1", "Task A2", "Task A3"],
        ["Task B1", "Task B2", "Task B3"],
        ["Task C1", "Task C2", "Task C3"],
    ]

    for agent, task_list in zip(agents, initial_tasks):
        for task in task_list:
            await agent.execute_task(task)

    # Now each agent learns from all experiences
    print("\n[Coordinator] Phase 2: Agents learning from shared experiences\n")

    await asyncio.gather(*[
        agent.learn_from_experiences()
        for agent in agents
    ])

    # Verify shared knowledge
    print("\n[Coordinator] Checking shared knowledge base...")
    all_patterns = await semantic.search_semantic_async("pattern", limit=10)
    print(f"[Coordinator] {len(all_patterns)} patterns learned and shared")


async def scenario_3_skill_sharing():
    """
    Scenario 3: Agents discovering and sharing skills.

    Demonstrates:
    - Agents contributing skills to shared library
    - Other agents discovering and using shared skills
    - No conflicts even when multiple agents share simultaneously
    """
    print("\n" + "=" * 70)
    print("SCENARIO 3: Skill Sharing")
    print("=" * 70)
    print("\n3 agents sharing skills in parallel\n")

    # Shared memory stores
    episodic = AsyncEpisodicMemoryStore()
    semantic = AsyncSemanticMemoryStore()
    skills = AsyncSkillMemoryStore()

    # Create agents
    agents = [
        ParallelAgent(1, episodic, semantic, skills),
        ParallelAgent(2, episodic, semantic, skills),
        ParallelAgent(3, episodic, semantic, skills),
    ]

    # Each agent shares a different skill
    skill_definitions = [
        ("data_processing", "Efficiently process large datasets"),
        ("error_handling", "Robust error recovery patterns"),
        ("optimization", "Performance optimization techniques"),
    ]

    print("[Coordinator] Agents sharing skills in parallel...\n")

    await asyncio.gather(*[
        agent.share_skill(name, desc)
        for agent, (name, desc) in zip(agents, skill_definitions)
    ])

    # All agents can now discover shared skills
    print("\n[Coordinator] Agents discovering shared skills...\n")

    async def discover_skills(agent):
        available_skills = await agent.skills.search_skills_async("skill", limit=5)
        print(f"[Agent {agent.agent_id}] Discovered {len(available_skills)} shared skills:")
        for skill in available_skills:
            print(f"  - {skill.skill_name}: {skill.description}")

    await asyncio.gather(*[discover_skills(agent) for agent in agents])


async def scenario_4_streaming_analysis():
    """
    Scenario 4: Agent analyzing large memory pool using streaming.

    Demonstrates:
    - Streaming large result sets to avoid memory issues
    - Processing data in batches
    - Memory-efficient operations
    """
    print("\n" + "=" * 70)
    print("SCENARIO 4: Streaming Large Memory Pool")
    print("=" * 70)
    print("\nAnalyzing 100 episodes using streaming\n")

    episodic = AsyncEpisodicMemoryStore()
    semantic = AsyncSemanticMemoryStore()
    skills = AsyncSkillMemoryStore()

    agent = ParallelAgent(1, episodic, semantic, skills)

    # Create 100 test episodes
    print("[Agent 1] Creating 100 test episodes...")
    for i in range(100):
        await agent.execute_task(f"Test task {i}")

    # Stream and analyze
    print("\n[Agent 1] Streaming and analyzing episodes in batches...\n")

    total_analyzed = 0
    batch_count = 0

    async for batch in episodic.stream_episodes_async(batch_size=10):
        batch_count += 1
        total_analyzed += len(batch)
        print(f"  Batch {batch_count}: Analyzed {len(batch)} episodes "
              f"(Total: {total_analyzed})")

        # Simulate analysis
        await asyncio.sleep(0.01)

    print(f"\n[Agent 1] Analysis complete: {total_analyzed} episodes in {batch_count} batches")
    print("[Agent 1] Memory usage kept low through streaming")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

async def main():
    """Run all example scenarios."""
    print("\n" + "=" * 70)
    print("ASYNC MEMORY ARCHITECTURE - INTEGRATION EXAMPLES")
    print("=" * 70)
    print("\nDemonstrating safe concurrent access from parallel agents\n")

    scenarios = [
        scenario_1_parallel_task_execution,
        scenario_2_collaborative_learning,
        scenario_3_skill_sharing,
        scenario_4_streaming_analysis,
    ]

    for i, scenario in enumerate(scenarios, 1):
        await scenario()
        if i < len(scenarios):
            print("\n" + "-" * 70)
            await asyncio.sleep(0.5)  # Brief pause between scenarios

    print("\n" + "=" * 70)
    print("ALL SCENARIOS COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    print("\nKey achievements:")
    print("✓ Multiple agents working in parallel without conflicts")
    print("✓ Safe concurrent reads (no blocking)")
    print("✓ Exclusive writes (no race conditions)")
    print("✓ Shared memory pool with collaborative learning")
    print("✓ Efficient streaming for large datasets")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nExecution interrupted by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
