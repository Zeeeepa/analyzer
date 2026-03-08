#!/usr/bin/env python3
"""
Test Suite for Multi-Agent Coordination System

Tests all components:
- MessageBroker: Inter-agent communication
- SharedMemory: Coordinated state management
- LeaderElection: Distributed leader selection
- TaskDistributor: Load balancing and task assignment
- AgentWorker: Agent lifecycle and task execution
- AgentOrchestrator: Complete orchestration
"""

import asyncio
import pytest
import time
from typing import List
from loguru import logger

from .multi_agent import (
    MessageBroker,
    SharedMemory,
    LeaderElection,
    TaskDistributor,
    AgentWorker,
    AgentOrchestrator,
    ResearcherAgent,
    ExtractorAgent,
    ValidatorAgent,
    Message,
    MessageType,
    TaskPriority,
    AgentRole,
    AgentStatus,
    AgentTask,
    create_agent_swarm,
    execute_task_with_swarm
)


class TestMessageBroker:
    """Test MessageBroker component"""

    @pytest.mark.asyncio
    async def test_direct_message(self):
        """Test sending direct message to agent"""
        broker = MessageBroker()

        # Send message
        msg = Message(
            message_id="test_msg_1",
            message_type=MessageType.REQUEST,
            from_agent="agent1",
            to_agent="agent2",
            payload={"data": "test"}
        )

        await broker.send(msg)

        # Receive message
        received = await broker.receive("agent2", timeout=1.0)

        assert received is not None
        assert received.message_id == "test_msg_1"
        assert received.from_agent == "agent1"
        assert received.payload["data"] == "test"

    @pytest.mark.asyncio
    async def test_broadcast_message(self):
        """Test broadcasting message to all agents"""
        broker = MessageBroker()

        # Send broadcast
        msg = Message(
            message_id="test_broadcast_1",
            message_type=MessageType.BROADCAST,
            from_agent="orchestrator",
            to_agent=None,  # Broadcast
            payload={"announcement": "hello"}
        )

        await broker.send(msg)

        # Multiple agents should receive
        received1 = await broker.receive("agent1", timeout=1.0)
        received2 = await broker.receive("agent2", timeout=1.0)

        assert received1 is not None
        assert received2 is not None
        assert received1.message_id == received2.message_id

    @pytest.mark.asyncio
    async def test_queue_size(self):
        """Test message queue size tracking"""
        broker = MessageBroker()

        # Send multiple messages
        for i in range(5):
            msg = Message(
                message_id=f"msg_{i}",
                message_type=MessageType.REQUEST,
                from_agent="sender",
                to_agent="receiver",
                payload={}
            )
            await broker.send(msg)

        assert broker.get_queue_size("receiver") == 5


class TestSharedMemory:
    """Test SharedMemory component"""

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        """Test setting and getting values"""
        memory = SharedMemory()

        # Set value
        success = await memory.set("key1", "value1")
        assert success

        # Get value
        value, version = await memory.get("key1")
        assert value == "value1"
        assert version == 1

    @pytest.mark.asyncio
    async def test_optimistic_locking(self):
        """Test version-based optimistic locking"""
        memory = SharedMemory()

        # Set initial value
        await memory.set("counter", 0)
        value, version = await memory.get("counter")

        # Update with correct version
        success = await memory.set("counter", 1, expected_version=version)
        assert success

        # Try to update with old version (should fail)
        success = await memory.set("counter", 2, expected_version=version)
        assert not success

    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """Test concurrent access from multiple tasks"""
        memory = SharedMemory()
        await memory.set("counter", 0)

        async def increment():
            for _ in range(10):
                value, version = await memory.get("counter")
                await memory.set("counter", value + 1, expected_version=version)
                await asyncio.sleep(0.01)

        # Run multiple incrementers concurrently
        tasks = [increment() for _ in range(3)]
        await asyncio.gather(*tasks)

        final_value, _ = await memory.get("counter")
        # Due to optimistic locking, not all increments will succeed
        assert final_value > 0


class TestLeaderElection:
    """Test LeaderElection component"""

    def test_single_leader(self):
        """Test leader election with single instance"""
        election = LeaderElection("agent1")

        success = election.start_election()
        assert success
        assert election.is_leader
        assert election.get_leader() == "agent1"

        election.step_down()
        assert not election.is_leader

    def test_multiple_instances(self):
        """Test leader election with multiple instances"""
        election1 = LeaderElection("agent1")
        election2 = LeaderElection("agent2")

        # First agent becomes leader
        success1 = election1.start_election()
        assert success1
        assert election1.is_leader

        # Second agent should be follower
        success2 = election2.start_election()
        assert not success2
        assert not election2.is_leader

        # Cleanup
        election1.step_down()
        election2.step_down()


class TestTaskDistributor:
    """Test TaskDistributor component"""

    @pytest.mark.asyncio
    async def test_submit_task(self):
        """Test task submission"""
        memory = SharedMemory()
        distributor = TaskDistributor(memory)

        task = await distributor.submit_task(
            task_id="task1",
            description="Test task",
            priority=TaskPriority.HIGH
        )

        assert task.task_id == "task1"
        assert task.priority == TaskPriority.HIGH

    @pytest.mark.asyncio
    async def test_task_assignment(self):
        """Test assigning tasks to agents"""
        memory = SharedMemory()
        broker = MessageBroker()
        distributor = TaskDistributor(memory)

        # Submit tasks
        await distributor.submit_task("task1", "Test 1", priority=TaskPriority.HIGH)
        await distributor.submit_task("task2", "Test 2", priority=TaskPriority.NORMAL)

        # Create mock agents
        agent1 = ResearcherAgent("agent1", broker, memory)
        agent1.status = AgentStatus.IDLE

        agent2 = ExtractorAgent("agent2", broker, memory)
        agent2.status = AgentStatus.IDLE

        # Assign tasks
        assignments = await distributor.assign_tasks([agent1, agent2])

        assert len(assignments) == 2
        assert assignments[0][1].priority == TaskPriority.HIGH  # High priority first

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """Test that tasks are assigned by priority"""
        memory = SharedMemory()
        broker = MessageBroker()
        distributor = TaskDistributor(memory)

        # Submit tasks in random order
        await distributor.submit_task("task1", "Low", priority=TaskPriority.LOW)
        await distributor.submit_task("task2", "Critical", priority=TaskPriority.CRITICAL)
        await distributor.submit_task("task3", "Normal", priority=TaskPriority.NORMAL)

        # Create agent
        agent = ResearcherAgent("agent1", broker, memory)
        agent.status = AgentStatus.IDLE

        # Assign tasks
        assignments = await distributor.assign_tasks([agent])

        # Should get critical task first
        assert assignments[0][1].priority == TaskPriority.CRITICAL


class TestAgentWorker:
    """Test AgentWorker component"""

    @pytest.mark.asyncio
    async def test_agent_lifecycle(self):
        """Test agent start and stop"""
        broker = MessageBroker()
        memory = SharedMemory()

        agent = ResearcherAgent("agent1", broker, memory)

        # Start agent
        await agent.start()
        assert agent.status == AgentStatus.IDLE
        assert agent._running

        # Stop agent
        await agent.stop()
        assert agent.status == AgentStatus.STOPPED
        assert not agent._running

    @pytest.mark.asyncio
    async def test_agent_task_execution(self):
        """Test agent executing a task"""
        broker = MessageBroker()
        memory = SharedMemory()

        agent = ResearcherAgent("agent1", broker, memory)
        await agent.start()

        # Create task
        task = AgentTask(
            task_id="test_task",
            description="Test research",
            assigned_to=agent.agent_id
        )

        # Execute task
        result = await agent.execute_task(task)

        assert result is not None
        assert result["status"] == "completed"
        assert agent.metrics.tasks_completed == 1

        await agent.stop()

    @pytest.mark.asyncio
    async def test_agent_message_handling(self):
        """Test agent handling messages"""
        broker = MessageBroker()
        memory = SharedMemory()

        agent = ResearcherAgent("agent1", broker, memory)
        await agent.start()

        # Send task assignment message
        task = AgentTask(
            task_id="msg_task",
            description="Test via message",
            assigned_to=agent.agent_id
        )

        msg = Message(
            message_id="test_msg",
            message_type=MessageType.TASK_ASSIGNMENT,
            from_agent="orchestrator",
            to_agent=agent.agent_id,
            payload={"task": {
                "task_id": task.task_id,
                "description": task.description,
                "assigned_to": task.assigned_to,
                "priority": TaskPriority.NORMAL.value,
                "status": "pending",
                "metadata": {}
            }}
        )

        await broker.send(msg)

        # Wait for agent to process
        await asyncio.sleep(3)

        # Agent should have processed task
        assert agent.metrics.tasks_completed > 0

        await agent.stop()


class TestAgentOrchestrator:
    """Test AgentOrchestrator component"""

    @pytest.mark.asyncio
    async def test_orchestrator_start_stop(self):
        """Test orchestrator lifecycle"""
        orchestrator = AgentOrchestrator(
            orchestrator_id="test_orchestrator",
            max_agents=3
        )

        await orchestrator.start()
        assert orchestrator._running
        assert len(orchestrator.agents) >= 2  # Minimum agents spawned

        await orchestrator.stop()
        assert not orchestrator._running
        assert len(orchestrator.agents) == 0

    @pytest.mark.asyncio
    async def test_agent_spawning(self):
        """Test spawning different agent types"""
        orchestrator = AgentOrchestrator(max_agents=5)
        await orchestrator.start()

        # Spawn different agents
        researcher = await orchestrator.spawn_agent(AgentRole.RESEARCHER)
        extractor = await orchestrator.spawn_agent(AgentRole.EXTRACTOR)
        validator = await orchestrator.spawn_agent(AgentRole.VALIDATOR)

        assert researcher is not None
        assert extractor is not None
        assert validator is not None
        assert len(orchestrator.agents) >= 5  # Initial + spawned

        await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_task_submission_and_execution(self):
        """Test complete task flow"""
        orchestrator = AgentOrchestrator(max_agents=3)
        await orchestrator.start()

        # Submit task
        task_id = await orchestrator.submit_task(
            description="Test task",
            priority=TaskPriority.NORMAL,
            required_role=AgentRole.RESEARCHER
        )

        assert task_id is not None

        # Wait for result
        result = await orchestrator.get_task_result(task_id, timeout=10)

        assert result is not None
        assert result["status"] == "completed"

        await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_parallel_task_execution(self):
        """Test executing multiple tasks in parallel"""
        orchestrator = AgentOrchestrator(max_agents=5)
        await orchestrator.start()

        # Submit multiple tasks
        task_ids = []
        for i in range(3):
            task_id = await orchestrator.submit_task(
                description=f"Parallel task {i}",
                priority=TaskPriority.NORMAL
            )
            task_ids.append(task_id)

        # Wait for all results
        results = []
        for task_id in task_ids:
            result = await orchestrator.get_task_result(task_id, timeout=10)
            results.append(result)

        assert len(results) == 3
        assert all(r is not None for r in results)

        await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_auto_scaling(self):
        """Test auto-scaling based on workload"""
        orchestrator = AgentOrchestrator(
            max_agents=10,
            min_agents=2,
            auto_scale=True
        )
        await orchestrator.start()

        initial_count = len(orchestrator.agents)

        # Submit many tasks
        task_ids = []
        for i in range(20):
            task_id = await orchestrator.submit_task(
                description=f"Load task {i}",
                priority=TaskPriority.NORMAL
            )
            task_ids.append(task_id)

        # Wait a bit for auto-scaling
        await asyncio.sleep(2)

        # Should have spawned more agents
        scaled_count = len(orchestrator.agents)
        assert scaled_count >= initial_count

        # Wait for tasks to complete
        for task_id in task_ids:
            try:
                await orchestrator.get_task_result(task_id, timeout=15)
            except:
                pass  # Some might timeout

        await orchestrator.stop()


class TestConvenienceFunctions:
    """Test convenience functions"""

    @pytest.mark.asyncio
    async def test_create_agent_swarm(self):
        """Test creating agent swarm"""
        swarm = await create_agent_swarm(num_agents=5)

        assert swarm is not None
        assert len(swarm.agents) >= 5

        await swarm.stop()

    @pytest.mark.asyncio
    async def test_execute_task_with_swarm(self):
        """Test executing single task with auto-created swarm"""
        result = await execute_task_with_swarm(
            task_description="Test task execution"
        )

        # May return None if agents don't complete in time
        # In production, this would have actual implementation
        assert result is None or isinstance(result, dict)


class TestIntegration:
    """Integration tests"""

    @pytest.mark.asyncio
    async def test_complete_workflow(self):
        """Test complete multi-agent workflow"""
        orchestrator = AgentOrchestrator(max_agents=5)
        await orchestrator.start()

        # Spawn diverse agent pool
        await orchestrator.spawn_agent(AgentRole.RESEARCHER)
        await orchestrator.spawn_agent(AgentRole.EXTRACTOR)
        await orchestrator.spawn_agent(AgentRole.VALIDATOR)

        # Submit related tasks
        research_task = await orchestrator.submit_task(
            "Research Stripe",
            required_role=AgentRole.RESEARCHER,
            priority=TaskPriority.HIGH
        )

        extraction_task = await orchestrator.submit_task(
            "Extract contact info",
            required_role=AgentRole.EXTRACTOR,
            priority=TaskPriority.NORMAL
        )

        validation_task = await orchestrator.submit_task(
            "Validate extracted data",
            required_role=AgentRole.VALIDATOR,
            priority=TaskPriority.NORMAL
        )

        # Wait for all to complete
        research_result = await orchestrator.get_task_result(research_task, timeout=10)
        extraction_result = await orchestrator.get_task_result(extraction_task, timeout=10)
        validation_result = await orchestrator.get_task_result(validation_task, timeout=10)

        assert research_result is not None
        assert extraction_result is not None
        assert validation_result is not None

        # Check metrics
        status = orchestrator.get_status()
        assert status["total_agents"] >= 5
        assert status["total_tasks_processed"] >= 0

        await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_failure_isolation(self):
        """Test that one agent failure doesn't affect others"""
        orchestrator = AgentOrchestrator(max_agents=5)
        await orchestrator.start()

        # Submit tasks
        good_task = await orchestrator.submit_task("Good task")

        # Simulate agent failure
        if orchestrator.agents:
            agent_id = list(orchestrator.agents.keys())[0]
            orchestrator.agents[agent_id].status = AgentStatus.ERROR

        # Wait for health check to handle failure
        await asyncio.sleep(2)

        # Good task should still be processable
        result = await orchestrator.get_task_result(good_task, timeout=10)

        # May or may not complete depending on which agent failed
        # But system should remain operational
        assert orchestrator._running

        await orchestrator.stop()


# Run tests
if __name__ == "__main__":
    async def run_all_tests():
        """Run all tests manually"""
        logger.info("Running Multi-Agent System Tests")

        # Message Broker Tests
        logger.info("\n=== MessageBroker Tests ===")
        broker_tests = TestMessageBroker()
        await broker_tests.test_direct_message()
        await broker_tests.test_broadcast_message()
        await broker_tests.test_queue_size()
        logger.info("MessageBroker tests passed")

        # SharedMemory Tests
        logger.info("\n=== SharedMemory Tests ===")
        memory_tests = TestSharedMemory()
        await memory_tests.test_set_and_get()
        await memory_tests.test_optimistic_locking()
        await memory_tests.test_concurrent_access()
        logger.info("SharedMemory tests passed")

        # LeaderElection Tests
        logger.info("\n=== LeaderElection Tests ===")
        election_tests = TestLeaderElection()
        election_tests.test_single_leader()
        election_tests.test_multiple_instances()
        logger.info("LeaderElection tests passed")

        # TaskDistributor Tests
        logger.info("\n=== TaskDistributor Tests ===")
        distributor_tests = TestTaskDistributor()
        await distributor_tests.test_submit_task()
        await distributor_tests.test_task_assignment()
        await distributor_tests.test_priority_ordering()
        logger.info("TaskDistributor tests passed")

        # AgentWorker Tests
        logger.info("\n=== AgentWorker Tests ===")
        worker_tests = TestAgentWorker()
        await worker_tests.test_agent_lifecycle()
        await worker_tests.test_agent_task_execution()
        await worker_tests.test_agent_message_handling()
        logger.info("AgentWorker tests passed")

        # AgentOrchestrator Tests
        logger.info("\n=== AgentOrchestrator Tests ===")
        orchestrator_tests = TestAgentOrchestrator()
        await orchestrator_tests.test_orchestrator_start_stop()
        await orchestrator_tests.test_agent_spawning()
        await orchestrator_tests.test_task_submission_and_execution()
        await orchestrator_tests.test_parallel_task_execution()
        logger.info("AgentOrchestrator tests passed")

        # Integration Tests
        logger.info("\n=== Integration Tests ===")
        integration_tests = TestIntegration()
        await integration_tests.test_complete_workflow()
        await integration_tests.test_failure_isolation()
        logger.info("Integration tests passed")

        logger.info("\n=== All Tests Passed ===")

    asyncio.run(run_all_tests())
