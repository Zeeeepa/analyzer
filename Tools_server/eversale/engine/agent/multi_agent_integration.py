#!/usr/bin/env python3
"""
Multi-Agent Integration Examples

Demonstrates integration of multi_agent.py with existing Eversale components:
- Planning Agent for hierarchical task decomposition
- Parallel execution across multiple agents
- Multi-tab browser coordination
- Skill library for capability-based routing
- Memory architecture for shared context
"""

import asyncio
from typing import Dict, Any, List, Optional
from loguru import logger

from .multi_agent import (
    AgentOrchestrator,
    AgentWorker,
    AgentRole,
    AgentTask,
    MessageBroker,
    SharedMemory,
    TaskPriority,
    create_agent_swarm,
    execute_task_with_swarm
)


class PlannerAgentWorker(AgentWorker):
    """
    Agent that integrates with planning_agent.py
    Creates hierarchical plans for complex tasks
    """

    def __init__(self, agent_id: str, broker: MessageBroker, shared_memory: SharedMemory):
        super().__init__(agent_id, AgentRole.PLANNER, broker, shared_memory)
        self.capabilities = {"task_decomposition", "plan_creation", "plan_validation"}

    async def execute_task(self, task: AgentTask) -> Any:
        """Execute planning task"""
        logger.info(f"PlannerAgent {self.agent_id} creating plan for: {task.description}")

        try:
            # Import planning agent
            from .planning_agent import planning_agent

            # Create plan
            plan = await planning_agent.plan(
                task=task.description,
                context=task.metadata.get("context", {}),
                max_depth=3
            )

            # Validate plan
            evaluation = await planning_agent.validate_plan(plan)

            return {
                "status": "success",
                "plan_id": plan.plan_id,
                "steps": len(plan.steps),
                "estimated_duration": plan.estimated_total_duration,
                "critic_score": plan.critic_score,
                "evaluation": evaluation
            }

        except Exception as e:
            logger.error(f"Planning failed: {e}")
            raise


class ExecutorAgentWorker(AgentWorker):
    """
    Agent that executes plans created by PlannerAgent
    Integrates with parallel.py for parallel execution
    """

    def __init__(
        self,
        agent_id: str,
        broker: MessageBroker,
        shared_memory: SharedMemory,
        browser=None
    ):
        super().__init__(agent_id, AgentRole.EXECUTOR, broker, shared_memory)
        self.capabilities = {"plan_execution", "parallel_execution", "browser_automation"}
        self.browser = browser

    async def execute_task(self, task: AgentTask) -> Any:
        """Execute a plan or task"""
        logger.info(f"ExecutorAgent {self.agent_id} executing: {task.description}")

        # Check if this is a plan execution
        plan_id = task.metadata.get("plan_id")

        if plan_id:
            return await self._execute_plan(plan_id, task)
        else:
            return await self._execute_simple_task(task)

    async def _execute_plan(self, plan_id: str, task: AgentTask) -> Any:
        """Execute a hierarchical plan"""
        try:
            from .planning_agent import planning_agent, Plan

            # Load plan
            plan = Plan.load(plan_id)
            if not plan:
                raise ValueError(f"Plan {plan_id} not found")

            # Create action handler
            async def action_handler(action: str, arguments: Dict) -> Any:
                # This would call appropriate tools/functions
                logger.info(f"Executing action: {action} with {arguments}")
                await asyncio.sleep(0.5)  # Simulate work
                return {"success": True}

            # Execute plan
            planning_agent.executor.action_handler = action_handler
            result = await planning_agent.execute_plan(plan)

            return {
                "status": "success",
                "plan_id": plan_id,
                "completed_steps": result["completed_steps"],
                "failed_steps": result["failed_steps"],
                "duration": result["duration"]
            }

        except Exception as e:
            logger.error(f"Plan execution failed: {e}")
            raise

    async def _execute_simple_task(self, task: AgentTask) -> Any:
        """Execute a simple task"""
        # Simulate task execution
        await asyncio.sleep(1)
        return {"status": "success", "result": f"Completed: {task.description}"}


class ParallelResearcherAgent(AgentWorker):
    """
    Agent that performs parallel research using multi_tab.py
    Can handle multiple research tasks simultaneously
    """

    def __init__(
        self,
        agent_id: str,
        broker: MessageBroker,
        shared_memory: SharedMemory,
        browser=None
    ):
        super().__init__(agent_id, AgentRole.RESEARCHER, broker, shared_memory)
        self.capabilities = {"parallel_research", "web_scraping", "multi_tab"}
        self.browser = browser
        self.tab_manager = None

    async def execute_task(self, task: AgentTask) -> Any:
        """Execute research task with parallel browsing"""
        logger.info(f"ParallelResearcherAgent {self.agent_id} researching: {task.description}")

        targets = task.metadata.get("targets", [])
        if not targets:
            targets = [task.description]

        try:
            # Initialize tab manager if we have browser
            if self.browser and not self.tab_manager:
                from .multi_tab import TabManager
                self.tab_manager = TabManager(browser=self.browser)
                await self.tab_manager.initialize(pool_size=3)

            if self.tab_manager:
                # Parallel research using multiple tabs
                results = await self._parallel_research(targets)
            else:
                # Sequential research
                results = await self._sequential_research(targets)

            return {
                "status": "success",
                "results": results,
                "targets_researched": len(results)
            }

        except Exception as e:
            logger.error(f"Research failed: {e}")
            raise

    async def _parallel_research(self, targets: List[str]) -> List[Dict]:
        """Research multiple targets in parallel"""
        async def research_one(page):
            """Extract data from a page"""
            title = await page.title()
            url = page.url

            # Extract basic info
            info = await page.evaluate("""
                () => {
                    return {
                        headings: Array.from(document.querySelectorAll('h1, h2'))
                            .map(h => h.textContent).slice(0, 3),
                        links: Array.from(document.querySelectorAll('a'))
                            .map(a => a.href).slice(0, 5)
                    }
                }
            """)

            return {
                "title": title,
                "url": url,
                "info": info
            }

        # Convert targets to URLs if needed
        urls = [
            f"https://www.google.com/search?q={target.replace(' ', '+')}"
            if not target.startswith('http') else target
            for target in targets
        ]

        # Parallel extraction
        results = await self.tab_manager.parallel_extract(
            urls=urls,
            extract_fn=research_one,
            max_concurrent=3
        )

        return [r.get("data", {}) for r in results if r.get("success")]

    async def _sequential_research(self, targets: List[str]) -> List[Dict]:
        """Research targets sequentially"""
        results = []
        for target in targets:
            # Simulate research
            await asyncio.sleep(0.5)
            results.append({
                "target": target,
                "info": f"Research results for {target}"
            })
        return results


class SkillBasedAgent(AgentWorker):
    """
    Agent that uses skill_library.py for capability-based execution
    Retrieves and executes learned skills
    """

    def __init__(self, agent_id: str, broker: MessageBroker, shared_memory: SharedMemory):
        super().__init__(agent_id, AgentRole.EXECUTOR, broker, shared_memory)
        self.capabilities = {"skill_execution", "skill_learning", "adaptive_execution"}
        self.skill_library = None

    async def execute_task(self, task: AgentTask) -> Any:
        """Execute task using skill library"""
        logger.info(f"SkillBasedAgent {self.agent_id} executing: {task.description}")

        try:
            # Initialize skill library
            if not self.skill_library:
                from .skill_library import SkillLibrary
                self.skill_library = SkillLibrary()
                await self.skill_library.initialize()

            # Retrieve relevant skills
            skills = await self.skill_library.retrieve_skills(
                query=task.description,
                top_k=3
            )

            if skills:
                logger.info(f"Found {len(skills)} relevant skills")

                # Try to execute with best matching skill
                best_skill = skills[0]
                context = task.metadata.get("context", {})

                result = best_skill.execute(context)

                # Record skill usage
                best_skill.metrics.record_use(success=True, execution_time=0)
                await self.skill_library.save_skill(best_skill)

                return {
                    "status": "success",
                    "skill_used": best_skill.name,
                    "result": result
                }
            else:
                # No skill found, execute directly
                logger.info("No matching skill found, executing directly")
                await asyncio.sleep(1)
                return {
                    "status": "success",
                    "skill_used": None,
                    "result": f"Completed: {task.description}"
                }

        except Exception as e:
            logger.error(f"Skill-based execution failed: {e}")
            raise


class CoordinatedOrchestrator(AgentOrchestrator):
    """
    Enhanced orchestrator with integration to existing Eversale components
    """

    def __init__(self, *args, browser=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Store browser for browser-dependent agents
        self.browser = browser

        # Register custom agent types
        self.agent_types.update({
            AgentRole.PLANNER: PlannerAgentWorker,
            AgentRole.EXECUTOR: lambda agent_id, broker, memory: ExecutorAgentWorker(
                agent_id, broker, memory, browser=self.browser
            ),
        })

    async def execute_complex_workflow(
        self,
        workflow_description: str,
        use_planning: bool = True
    ) -> Dict[str, Any]:
        """
        Execute a complex workflow using multiple agents

        Pipeline:
        1. PlannerAgent creates hierarchical plan
        2. Plan is decomposed into parallel tasks
        3. Tasks distributed across specialized agents
        4. Results aggregated and returned

        Args:
            workflow_description: Description of workflow
            use_planning: Whether to use planning agent

        Returns:
            Workflow results
        """
        logger.info(f"Executing complex workflow: {workflow_description}")

        results = {}

        try:
            if use_planning:
                # Step 1: Create plan
                plan_task_id = await self.submit_task(
                    description=f"Create plan for: {workflow_description}",
                    priority=TaskPriority.HIGH,
                    required_role=AgentRole.PLANNER
                )

                plan_result = await self.get_task_result(plan_task_id, timeout=60)
                results["plan"] = plan_result

                if not plan_result or plan_result.get("status") != "success":
                    raise Exception("Planning failed")

                # Step 2: Execute plan
                execution_task_id = await self.submit_task(
                    description=f"Execute plan: {plan_result['plan_id']}",
                    priority=TaskPriority.HIGH,
                    required_role=AgentRole.EXECUTOR,
                    metadata={"plan_id": plan_result["plan_id"]}
                )

                execution_result = await self.get_task_result(execution_task_id, timeout=120)
                results["execution"] = execution_result

            else:
                # Direct execution without planning
                task_id = await self.submit_task(
                    description=workflow_description,
                    priority=TaskPriority.NORMAL
                )

                result = await self.get_task_result(task_id, timeout=60)
                results["execution"] = result

            return {
                "status": "success",
                "workflow": workflow_description,
                "results": results
            }

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            return {
                "status": "failed",
                "workflow": workflow_description,
                "error": str(e),
                "partial_results": results
            }

    async def parallel_research_workflow(
        self,
        targets: List[str]
    ) -> Dict[str, Any]:
        """
        Execute parallel research on multiple targets

        Args:
            targets: List of research targets

        Returns:
            Research results
        """
        logger.info(f"Starting parallel research for {len(targets)} targets")

        # Submit research tasks
        task_ids = []
        for target in targets:
            task_id = await self.submit_task(
                description=f"Research: {target}",
                priority=TaskPriority.NORMAL,
                required_role=AgentRole.RESEARCHER,
                metadata={"targets": [target]}
            )
            task_ids.append(task_id)

        # Collect results
        results = []
        for task_id in task_ids:
            try:
                result = await self.get_task_result(task_id, timeout=30)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"Research task {task_id} failed: {e}")
                results.append({"status": "failed", "error": str(e)})

        return {
            "status": "success",
            "targets": targets,
            "results": results,
            "successful": len([r for r in results if r.get("status") == "success"]),
            "failed": len([r for r in results if r.get("status") == "failed"])
        }


# Integration examples
async def example_hierarchical_workflow():
    """
    Example: Use PlannerAgent + ExecutorAgent for complex task
    """
    logger.info("=== Example: Hierarchical Workflow ===")

    orchestrator = CoordinatedOrchestrator(
        orchestrator_id="hierarchical_orchestrator",
        max_agents=5
    )

    await orchestrator.start()

    # Spawn specialized agents
    await orchestrator.spawn_agent(AgentRole.PLANNER)
    await orchestrator.spawn_agent(AgentRole.EXECUTOR)
    await orchestrator.spawn_agent(AgentRole.RESEARCHER)

    try:
        # Execute complex workflow
        result = await orchestrator.execute_complex_workflow(
            workflow_description="Research top 3 CRM companies and extract their contact information",
            use_planning=True
        )

        logger.info(f"Workflow result: {result}")

    finally:
        await orchestrator.stop()


async def example_parallel_research():
    """
    Example: Parallel research across multiple agents
    """
    logger.info("=== Example: Parallel Research ===")

    orchestrator = CoordinatedOrchestrator(
        orchestrator_id="parallel_orchestrator",
        max_agents=5
    )

    await orchestrator.start()

    # Spawn multiple researcher agents
    for i in range(3):
        await orchestrator.spawn_agent(AgentRole.RESEARCHER)

    try:
        # Research multiple targets in parallel
        targets = [
            "Stripe payment processing",
            "Shopify e-commerce platform",
            "HubSpot CRM software"
        ]

        result = await orchestrator.parallel_research_workflow(targets)

        logger.info(f"Research completed: {result['successful']}/{len(targets)} successful")
        logger.info(f"Results: {result}")

    finally:
        await orchestrator.stop()


async def example_skill_based_execution():
    """
    Example: Use SkillBasedAgent with skill library
    """
    logger.info("=== Example: Skill-Based Execution ===")

    orchestrator = AgentOrchestrator(
        orchestrator_id="skill_orchestrator",
        max_agents=3
    )

    # Register skill-based agent
    orchestrator.agent_types[AgentRole.EXECUTOR] = SkillBasedAgent

    await orchestrator.start()

    # Spawn skill-based agents
    await orchestrator.spawn_agent(AgentRole.EXECUTOR)

    try:
        # Submit task that can use learned skills
        task_id = await orchestrator.submit_task(
            description="Navigate to Facebook Ads Library and search for 'CRM software'",
            required_role=AgentRole.EXECUTOR
        )

        result = await orchestrator.get_task_result(task_id, timeout=30)

        logger.info(f"Skill-based execution result: {result}")

    finally:
        await orchestrator.stop()


async def example_distributed_coordination():
    """
    Example: Multiple orchestrators coordinating via shared memory
    """
    logger.info("=== Example: Distributed Coordination ===")

    # Create two orchestrators
    orchestrator1 = AgentOrchestrator(
        orchestrator_id="orchestrator1",
        max_agents=3
    )

    orchestrator2 = AgentOrchestrator(
        orchestrator_id="orchestrator2",
        max_agents=3
    )

    await orchestrator1.start()
    await orchestrator2.start()

    try:
        # Both orchestrators share same memory
        shared_mem = orchestrator1.shared_memory

        # Orchestrator 1 submits task
        task_id1 = await orchestrator1.submit_task("Research Stripe")

        # Store task ID in shared memory
        await shared_mem.set("current_task", task_id1)

        # Orchestrator 2 submits related task
        task_id2 = await orchestrator2.submit_task("Research Shopify")

        # Wait for results
        result1 = await orchestrator1.get_task_result(task_id1, timeout=30)
        result2 = await orchestrator2.get_task_result(task_id2, timeout=30)

        logger.info(f"Distributed results: {result1}, {result2}")

    finally:
        await orchestrator1.stop()
        await orchestrator2.stop()


# Main demo
async def main():
    """Run all examples"""
    logger.info("Starting Multi-Agent Integration Examples")

    # Run examples
    await example_hierarchical_workflow()
    await asyncio.sleep(2)

    await example_parallel_research()
    await asyncio.sleep(2)

    await example_skill_based_execution()
    await asyncio.sleep(2)

    await example_distributed_coordination()

    logger.info("All examples completed")


if __name__ == "__main__":
    asyncio.run(main())
