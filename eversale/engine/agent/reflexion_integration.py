#!/usr/bin/env python3
"""
Reflexion Integration Examples for Eversale

Shows how to integrate the Reflexion self-improvement loop with:
1. brain_enhanced_v2.py - Main agent brain
2. self_healing_system.py - Error recovery
3. self_play_engine.py - Training loop
4. context_memory.py - Memory system
"""

import asyncio
from pathlib import Path
from typing import Dict, Any
from loguru import logger

from .reflexion import (
    ReflexionEngine,
    integrate_with_brain,
    integrate_with_self_healing
)


# ============================================================================
# INTEGRATION 1: Enhanced Brain with Reflexion
# ============================================================================

class ReflexiveBrain:
    """
    Wrapper that adds Reflexion capabilities to brain_enhanced_v2.

    Usage:
        brain = ReflexiveBrain(config, mcp)
        success, output = await brain.run_with_reflexion(prompt)
    """

    def __init__(self, original_brain, config: Dict):
        self.brain = original_brain
        self.config = config
        self.reflexion = ReflexionEngine(config)

        logger.info("ReflexiveBrain initialized - self-improvement enabled")

    async def run_with_reflexion(
        self,
        prompt: str,
        category: str = "general",
        domain: str = "general"
    ) -> tuple[bool, str]:
        """
        Run task with reflexion loop.

        Automatically retries with self-reflection on failure.
        """

        # Define executor that wraps original brain
        async def executor(enhanced_prompt: str, context: Dict) -> tuple[str, list]:
            # Run the enhanced prompt (includes reflection guidance)
            output = await self.brain.run(enhanced_prompt)

            # Get tool usage
            tools_used = []
            if hasattr(self.brain, 'tool_history'):
                tools_used = self.brain.tool_history[-10:]  # Last 10 tools

            return output, tools_used

        # Get evaluation context
        eval_context = await self._get_eval_context()

        # Execute with reflexion
        success, output, reflections = await self.reflexion.execute_with_reflexion(
            prompt,
            category,
            domain,
            executor,
            eval_context
        )

        # Periodic consolidation
        if self.reflexion.metrics.total_tasks % 10 == 0:
            await self.reflexion.consolidate_learnings()
            logger.info(self.reflexion.get_improvement_report())

        return success, output

    async def _get_eval_context(self) -> Dict:
        """Get context for evaluation (page state, screenshot, etc.)"""
        context = {}

        if hasattr(self.brain, 'mcp') and self.brain.mcp:
            try:
                # Get page text
                page_text = await self.brain.mcp.call_tool(
                    'playwright_get_text',
                    {'selector': 'body'}
                )
                context['page_content'] = str(page_text) if page_text else ""

                # Get URL
                url_result = await self.brain.mcp.call_tool(
                    'playwright_evaluate',
                    {'script': 'window.location.href'}
                )
                context['page_url'] = str(url_result) if url_result else ""

            except Exception as e:
                logger.debug(f"Could not get eval context: {e}")

        return context

    def get_metrics(self):
        """Get reflexion metrics."""
        return self.reflexion.get_metrics()

    def get_report(self) -> str:
        """Get improvement report."""
        return self.reflexion.get_improvement_report()


# ============================================================================
# INTEGRATION 2: Self-Play Training with Reflexion
# ============================================================================

async def enhance_training_with_reflexion(
    self_play_engine,
    config: Dict
) -> Dict:
    """
    Enhance self-play training with reflexion loop.

    Replaces standard task execution with reflexion-based execution.

    Usage in self_play_engine.py:
        from agent.reflexion_integration import enhance_training_with_reflexion

        # In run_training():
        reflexion_stats = await enhance_training_with_reflexion(self, config)
    """

    reflexion = ReflexionEngine(config)

    logger.info("Enhanced training with Reflexion self-improvement")

    # Monkey-patch the _execute_task method to use reflexion
    original_execute = self_play_engine._execute_task

    async def reflexion_execute_task(brain, task, task_num):
        """Execute task with reflexion loop."""

        # Define executor
        async def executor(prompt: str, context: Dict) -> tuple[str, list]:
            output = await brain.run(prompt)
            tools = brain.get_stats().get('tool_calls', [])
            return output, tools

        # Get eval context
        eval_context = {}
        if hasattr(brain, 'mcp') and brain.mcp:
            try:
                page_text = await brain.mcp.call_tool('playwright_get_text', {'selector': 'body'})
                eval_context['page_content'] = str(page_text) if page_text else ""
            except:
                pass

        # Execute with reflexion
        success, output, reflections = await reflexion.execute_with_reflexion(
            task.prompt,
            task.category,
            task.domain,
            executor,
            eval_context
        )

        # Convert to TaskResult format
        from training.self_play_engine import TaskResult
        import time

        # Calculate total execution time from all attempts
        total_exec_time = 0.0
        if reflections:
            for refl in reflections:
                if refl.failed_approach and 'execution_time' in refl.failed_approach:
                    total_exec_time += refl.failed_approach['execution_time']

        return TaskResult(
            task=task,
            success=success,
            output=output[:500],
            execution_time=total_exec_time,
            iterations=len(reflections),
            tool_calls=brain.get_stats().get('tool_calls', 0),
            errors=[],
            learnings_extracted=len(reflections),
            timestamp=task.timestamp
        )

    # Replace method
    self_play_engine._execute_task = reflexion_execute_task

    return {
        'reflexion_enabled': True,
        'max_attempts': reflexion.max_attempts,
        'engine': reflexion
    }


# ============================================================================
# INTEGRATION 3: Self-Healing with Reflexion Strategies
# ============================================================================

def sync_reflexion_to_self_healing(reflexion_engine: ReflexionEngine):
    """
    Sync learned strategies from Reflexion to self-healing system.

    Call this periodically to share learnings.

    Usage:
        from agent.reflexion_integration import sync_reflexion_to_self_healing

        # After training or periodically:
        sync_reflexion_to_self_healing(reflexion_engine)
    """

    from .self_healing_system import self_healing

    strategies_added = 0

    # Export strategies by category
    for category, strategies in reflexion_engine.memory.strategies.items():
        for strategy in strategies:
            # Convert to self-healing format
            healing_strategy = {
                'action': 'reflexion_strategy',
                'reason': f'Learned from reflexion: {strategy}',
                'source': 'reflexion',
                'confidence': 0.8
            }

            # Add to appropriate self-healing category
            if category in ['navigation', 'interaction', 'extraction']:
                if healing_strategy not in self_healing.success_strategies[category]:
                    self_healing.success_strategies[category].append(healing_strategy)
                    strategies_added += 1

    logger.info(f"Synced {strategies_added} reflexion strategies to self-healing")

    return strategies_added


# ============================================================================
# INTEGRATION 4: Context Memory with Reflexion
# ============================================================================

def sync_reflexion_to_context_memory(
    reflexion_engine: ReflexionEngine,
    context_memory
):
    """
    Add key insights from reflexion to context memory.

    Usage:
        from agent.reflexion_integration import sync_reflexion_to_context_memory

        sync_reflexion_to_context_memory(reflexion_engine, context_memory)
    """

    # Get top strategies
    insights_added = 0

    for category, strategies in reflexion_engine.memory.strategies.items():
        for strategy in strategies[:3]:  # Top 3 per category
            entry = f"[Reflexion] {category}: {strategy}"
            context_memory.add_entry(entry)
            insights_added += 1

    logger.info(f"Added {insights_added} reflexion insights to context memory")

    return insights_added


# ============================================================================
# INTEGRATION 5: Complete Production Setup
# ============================================================================

async def setup_production_reflexion(config: Dict) -> Dict:
    """
    Complete production setup with all integrations.

    Returns dictionary with all reflexion components.

    Usage:
        from agent.reflexion_integration import setup_production_reflexion

        reflexion_components = await setup_production_reflexion(config)

        # Use in brain:
        brain = reflexion_components['reflexive_brain']
        success, output = await brain.run_with_reflexion(prompt)

        # Get metrics:
        print(reflexion_components['engine'].get_improvement_report())
    """

    logger.info("Setting up production reflexion system...")

    # 1. Create main reflexion engine
    reflexion = ReflexionEngine(config)

    # 2. Load existing state if available
    reflexion.load_state()

    # 3. Create wrapper components
    components = {
        'engine': reflexion,
        'evaluator': reflexion.evaluator,
        'reflection_generator': reflexion.reflection_generator,
        'memory': reflexion.memory,
        'experience_replay': reflexion.experience_replay,
        'metrics': reflexion.metrics
    }

    logger.info("Production reflexion system ready")
    logger.info(f"Memory: {reflexion.memory.get_stats()}")
    logger.info(f"Experience: {reflexion.experience_replay.get_stats()}")

    return components


# ============================================================================
# INTEGRATION 6: Monitoring and Reporting
# ============================================================================

class ReflexionMonitor:
    """
    Monitor reflexion performance and generate reports.

    Usage:
        monitor = ReflexionMonitor(reflexion_engine)

        # Periodic check
        await monitor.check_performance()

        # Generate report
        report = monitor.generate_dashboard()
    """

    def __init__(self, reflexion_engine: ReflexionEngine):
        self.engine = reflexion_engine
        self.checkpoints = []

    async def check_performance(self) -> Dict:
        """Check current performance and detect issues."""

        metrics = self.engine.metrics

        # Calculate rates
        success_rate = metrics.final_success_rate
        first_attempt_rate = metrics.first_attempt_success_rate
        improvement = success_rate - first_attempt_rate

        # Check for issues
        issues = []

        if success_rate < 0.7:
            issues.append("Low success rate (<70%) - need more training")

        if improvement < 0.05:
            issues.append("Low improvement rate - reflections may not be helpful")

        if metrics.avg_attempts_to_success > 3.5:
            issues.append("High attempts to success - strategies not effective")

        # Record checkpoint
        checkpoint = {
            'timestamp': metrics.last_update,
            'success_rate': success_rate,
            'improvement': improvement,
            'issues': issues
        }
        self.checkpoints.append(checkpoint)

        if issues:
            logger.warning(f"Reflexion issues detected: {', '.join(issues)}")

        return checkpoint

    def generate_dashboard(self) -> str:
        """Generate monitoring dashboard."""

        metrics = self.engine.metrics
        memory_stats = self.engine.memory.get_stats()
        experience_stats = self.engine.experience_replay.get_stats()

        dashboard = f"""
╔══════════════════════════════════════════════════════════════════╗
║                  REFLEXION MONITORING DASHBOARD                  ║
╠══════════════════════════════════════════════════════════════════╣

🎯 PERFORMANCE METRICS
   Success Rate:           {metrics.final_success_rate*100:.1f}%
   First Attempt Rate:     {metrics.first_attempt_success_rate*100:.1f}%
   Improvement:            +{(metrics.final_success_rate - metrics.first_attempt_success_rate)*100:.1f}%
   Avg Attempts:           {metrics.avg_attempts_to_success:.2f}

📊 TASK STATISTICS
   Total Tasks:            {metrics.total_tasks}
   Successful:             {metrics.successful_tasks}
   Failed:                 {metrics.failed_tasks}
   Total Attempts:         {metrics.total_attempts}

🧠 MEMORY SYSTEM
   Total Reflections:      {memory_stats['total_reflections']}
   Consolidated Strategies: {memory_stats['total_strategies']}
   Short-term Size:        {memory_stats['short_term_size']}

📚 EXPERIENCE REPLAY
   Trajectories:           {experience_stats['total_trajectories']}
   Success Trajectories:   {experience_stats['successful_trajectories']}
   Failure Trajectories:   {experience_stats['failed_trajectories']}
   Success Rate:           {experience_stats['success_rate']*100:.1f}%

📈 CATEGORY PERFORMANCE
"""

        for category, stats in metrics.category_performance.items():
            rate = stats['successful'] / max(stats['total'], 1) * 100
            dashboard += f"   {category:15} {stats['successful']:2}/{stats['total']:2} ({rate:.0f}%) "
            dashboard += f"avg {stats['avg_attempts']:.1f} attempts\n"

        dashboard += "\n╚══════════════════════════════════════════════════════════════════╝"

        return dashboard


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

async def example_complete_integration():
    """
    Complete example showing all integrations.
    """

    # 1. Setup config
    config = {
        'llm': {
            'main_model': '0000/ui-tars-1.5-7b:latest',
            'router_model': '0000/ui-tars-1.5-7b:latest'
        },
        'reflexion': {
            'max_attempts': 5,
            'reflection_threshold': 0.6
        }
    }

    # 2. Setup production reflexion
    components = await setup_production_reflexion(config)
    reflexion_engine = components['engine']

    # 3. Create brain with reflexion
    from agent.brain_enhanced_v2 import create_enhanced_brain
    from agent.mcp_client import MCPClient

    mcp = MCPClient()
    await mcp.connect_all_servers()

    original_brain = create_enhanced_brain(config, mcp)
    reflexive_brain = ReflexiveBrain(original_brain, config)

    # 4. Execute task with reflexion
    success, output = await reflexive_brain.run_with_reflexion(
        prompt="Navigate to example.com and extract contact information",
        category="extraction",
        domain="general"
    )

    print(f"Task result: {'SUCCESS' if success else 'FAILURE'}")
    print(f"Output: {output[:200]}")

    # 5. Sync learnings to self-healing
    sync_reflexion_to_self_healing(reflexion_engine)

    # 6. Check performance
    monitor = ReflexionMonitor(reflexion_engine)
    checkpoint = await monitor.check_performance()
    print(monitor.generate_dashboard())

    # 7. Save state
    reflexion_engine.save_state()

    await mcp.disconnect_all_servers()


if __name__ == "__main__":
    asyncio.run(example_complete_integration())
