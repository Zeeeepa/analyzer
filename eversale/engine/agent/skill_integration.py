#!/usr/bin/env python3
"""
Skill Library Integration for Brain Enhanced V2

Hooks the Voyager-style skill library into the main agent brain for:
1. Automatic skill learning from successful executions
2. Skill-based planning (use existing skills when available)
3. Skill composition for complex tasks
4. Performance tracking and improvement

Integration Points:
- Hook into execute_action() to record successful patterns
- Hook into plan_task() to search for applicable skills
- Hook into reflect() to identify skill improvement opportunities
- Expose skill library via agent commands
"""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
from loguru import logger

from .skill_library import (
    SkillLibrary,
    Skill,
    SkillCategory,
    get_skill_library
)


class SkillAwareAgent:
    """
    Mixin class to add skill library capabilities to the agent brain
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.skill_library = get_skill_library()
        self._current_execution_trace: List[Dict[str, Any]] = []
        self._current_task_desc: str = ""

    async def execute_with_skills(
        self,
        task: str,
        use_skills: bool = True,
        learn_skills: bool = True
    ) -> Any:
        """
        Execute a task with skill library support

        Args:
            task: Task description
            use_skills: Whether to search for and use existing skills
            learn_skills: Whether to learn new skills from execution

        Returns:
            Task result
        """
        # Start execution trace
        self._current_execution_trace = []
        self._current_task_desc = task

        result = None
        start_time = datetime.now()

        try:
            # Step 1: Search for existing skills that could help
            if use_skills:
                applicable_skills = self.skill_library.search_skills(
                    query=task,
                    min_success_rate=0.7,
                    limit=3
                )

                if applicable_skills:
                    logger.info(f"Found {len(applicable_skills)} applicable skills for task")

                    # Try to use the best skill
                    best_skill = applicable_skills[0]
                    logger.info(f"Attempting to use skill: {best_skill.name}")

                    try:
                        # Execute the skill
                        context = self._prepare_skill_context(task)
                        result = await self._execute_skill_safely(best_skill, context)

                        # Record success
                        execution_time = (datetime.now() - start_time).total_seconds()
                        self.skill_library.record_skill_usage(
                            skill_id=best_skill.skill_id,
                            success=True,
                            execution_time=execution_time
                        )

                        logger.info(f"Successfully used skill: {best_skill.name}")
                        return result

                    except Exception as e:
                        logger.warning(f"Skill execution failed: {e}")
                        # Record failure
                        execution_time = (datetime.now() - start_time).total_seconds()
                        self.skill_library.record_skill_usage(
                            skill_id=best_skill.skill_id,
                            success=False,
                            execution_time=execution_time,
                            error=str(e)
                        )
                        # Fall through to regular execution

            # Step 2: No applicable skill or skill failed - execute normally
            result = await self._execute_task_normally(task)

            # Step 3: Learn from successful execution
            if learn_skills and result and self._current_execution_trace:
                await self._try_learn_skill(task, result)

            return result

        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            raise

        finally:
            # Clear trace
            self._current_execution_trace = []
            self._current_task_desc = ""

    def _prepare_skill_context(self, task: str) -> Dict[str, Any]:
        """
        Prepare context dictionary for skill execution

        Args:
            task: Task description

        Returns:
            Context dictionary
        """
        # Extract common parameters from task using simple patterns
        context = {
            "task": task,
        }

        # Extract URL if present
        import re
        url_match = re.search(r'https?://[^\s]+', task)
        if url_match:
            context["url"] = url_match.group(0)

        # Extract email if present
        email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', task)
        if email_match:
            context["email"] = email_match.group(0)

        # Add any browser/page context if available
        if hasattr(self, 'browser_context'):
            context["browser"] = self.browser_context

        return context

    async def _execute_skill_safely(self, skill: Skill, context: Dict[str, Any]) -> Any:
        """
        Execute a skill with error handling and timeout

        Args:
            skill: Skill to execute
            context: Execution context

        Returns:
            Skill result
        """
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                skill.execute(context),
                timeout=300.0  # 5 minute timeout
            )
            return result
        except asyncio.TimeoutError:
            raise Exception(f"Skill execution timed out: {skill.name}")
        except Exception as e:
            raise Exception(f"Skill execution error: {e}")

    async def _execute_task_normally(self, task: str) -> Any:
        """
        Execute task using normal agent flow (placeholder)

        This should be implemented by the actual agent brain to execute
        the task using its standard approach (ReAct, planning, etc.)

        Args:
            task: Task to execute

        Returns:
            Task result
        """
        # This is where the normal agent execution would happen
        # For now, just a placeholder that shows the pattern
        logger.info(f"Executing task normally: {task}")

        # The actual brain would do something like:
        # - Plan the task
        # - Execute actions
        # - Record actions in self._current_execution_trace
        # - Return result

        return {"executed": True, "task": task}

    async def _try_learn_skill(self, task: str, result: Any):
        """
        Try to learn a skill from successful execution

        Args:
            task: Task that was executed
            result: Result of the task
        """
        if not self._current_execution_trace:
            return

        # Determine category from task
        category = self._infer_category(task)

        logger.info(f"Attempting to learn skill from task: {task}")

        # Extract skill
        learned_skill = self.skill_library.learn_skill_from_execution(
            task_description=task,
            actions=self._current_execution_trace,
            result=result,
            category=category,
            auto_add=True
        )

        if learned_skill:
            logger.info(f"Learned new skill: {learned_skill.name} ({learned_skill.skill_id})")

            # Try to generalize if the skill seems specific
            if learned_skill.generalization_level == 0:
                from .skill_library import SkillGenerator
                generalized = SkillGenerator.generalize_skill(learned_skill)
                if generalized:
                    self.skill_library.add_skill(generalized, validate=True)
                    logger.info(f"Created generalized version: {generalized.skill_id}")

    def _infer_category(self, task: str) -> SkillCategory:
        """
        Infer skill category from task description

        Args:
            task: Task description

        Returns:
            Most likely skill category
        """
        task_lower = task.lower()

        # Navigation patterns
        if any(word in task_lower for word in ["login", "navigate", "go to", "visit", "browse"]):
            return SkillCategory.NAVIGATION

        # Extraction patterns
        if any(word in task_lower for word in ["extract", "scrape", "get", "find", "collect"]):
            return SkillCategory.EXTRACTION

        # Interaction patterns
        if any(word in task_lower for word in ["fill", "submit", "click", "type", "enter"]):
            return SkillCategory.INTERACTION

        # Default to composite for complex tasks
        return SkillCategory.COMPOSITE

    def record_action(self, tool: str, arguments: Dict[str, Any], result: Any = None):
        """
        Record an action in the execution trace

        Call this from the agent's action execution code to track what's being done

        Args:
            tool: Tool that was used
            arguments: Arguments passed to the tool
            result: Result of the action (optional)
        """
        self._current_execution_trace.append({
            "tool": tool,
            "arguments": arguments,
            "result": result,
            "timestamp": datetime.now().isoformat()
        })

    def record_action_safe(self, tool: str, arguments: Dict[str, Any], result: Any = None) -> bool:
        """
        Safely record an action with error handling.

        This is a convenience wrapper that handles exceptions gracefully.
        Use this when calling from the main brain to avoid disrupting execution.

        Args:
            tool: Tool that was used
            arguments: Arguments passed to the tool
            result: Result of the action (optional)

        Returns:
            True if recording succeeded, False otherwise
        """
        try:
            self.record_action(tool=tool, arguments=arguments, result=result)
            return True
        except Exception as e:
            logger.debug(f"Skill action recording failed: {e}")
            return False

    async def try_learn_skill_safe(self, task: str, result: Any) -> bool:
        """
        Safely try to learn a skill with error handling.

        This is a convenience wrapper that handles exceptions gracefully.
        Use this when calling from the main brain to avoid disrupting execution.

        Args:
            task: Task description that was executed
            result: Result of the task execution

        Returns:
            True if learning succeeded or was attempted, False on error
        """
        try:
            await self._try_learn_skill(task, result)
            return True
        except Exception as e:
            logger.debug(f"Skill learning failed: {e}")
            return False

    def search_applicable_skills(
        self,
        prompt: str,
        min_success_rate: float = 0.7,
        limit: int = 3,
        log_results: bool = True
    ) -> List[Any]:
        """
        Search for skills applicable to a given prompt/task.

        This is a convenience method that wraps skill search with logging
        and error handling for use in the main brain.

        Args:
            prompt: The task or prompt to find skills for
            min_success_rate: Minimum success rate for skills (default 0.7)
            limit: Maximum number of skills to return (default 3)
            log_results: Whether to log found skills (default True)

        Returns:
            List of applicable skills, empty list on error or no matches
        """
        try:
            if not self.skill_library:
                return []

            applicable_skills = self.skill_library.search_skills(
                query=prompt,
                min_success_rate=min_success_rate,
                limit=limit
            )

            if applicable_skills and log_results:
                skill_names = [s.name for s in applicable_skills]
                logger.info(f"Found {len(applicable_skills)} applicable skills: {', '.join(skill_names)}")

            return applicable_skills
        except Exception as e:
            logger.debug(f"Skill search failed: {e}")
            return []

    def has_skill_library(self) -> bool:
        """
        Check if the skill library is available and initialized.

        Returns:
            True if skill library is ready to use
        """
        return hasattr(self, 'skill_library') and self.skill_library is not None

    def get_skill_count(self) -> int:
        """
        Get the number of skills in the library.

        Returns:
            Number of skills, 0 if library not available
        """
        if self.has_skill_library():
            return len(self.skill_library.skills)
        return 0

    async def suggest_skills_for_task(self, task: str) -> List[Dict[str, Any]]:
        """
        Suggest skills that could help with a task

        Args:
            task: Task description

        Returns:
            List of skill suggestions with metadata
        """
        skills = self.skill_library.search_skills(
            query=task,
            limit=5
        )

        suggestions = []
        for skill in skills:
            suggestions.append({
                "skill_id": skill.skill_id,
                "name": skill.name,
                "description": skill.description,
                "category": skill.category.value,
                "success_rate": skill.metrics.success_rate,
                "total_uses": skill.metrics.total_uses,
                "required_tools": skill.required_tools,
            })

        return suggestions

    async def compose_workflow_for_task(
        self,
        task: str,
        max_skills: int = 5
    ) -> Optional[Skill]:
        """
        Try to compose a workflow from existing skills

        Args:
            task: Complex task description
            max_skills: Maximum skills to combine

        Returns:
            Composite skill or None
        """
        # Search for skills that might be relevant
        skills = self.skill_library.search_skills(
            query=task,
            limit=max_skills
        )

        if len(skills) < 2:
            return None

        # Compose them
        skill_ids = [s.skill_id for s in skills]
        workflow = self.skill_library.compose_workflow(
            skill_ids=skill_ids,
            workflow_name=f"Workflow: {task[:50]}",
            workflow_description=task
        )

        return workflow

    def get_skill_statistics(self) -> Dict[str, Any]:
        """Get skill library statistics"""
        return self.skill_library.get_statistics()

    def export_skills(self, output_path: str):
        """Export skills to file"""
        from pathlib import Path
        self.skill_library.export_skills(Path(output_path))

    def import_skills(self, input_path: str):
        """Import skills from file"""
        from pathlib import Path
        self.skill_library.import_skills(Path(input_path))


# Example integration with a hypothetical agent
class ExampleSkillAwareAgent(SkillAwareAgent):
    """
    Example showing how to integrate skill library with an agent
    """

    def __init__(self):
        self.browser_context = None
        super().__init__()

    async def execute_task(self, task: str) -> Any:
        """
        Main task execution entry point

        This shows how to integrate the skill library into the main
        execution flow of an agent.
        """
        logger.info(f"Executing task with skill support: {task}")

        # Use the skill-aware execution
        result = await self.execute_with_skills(
            task=task,
            use_skills=True,  # Try to use existing skills
            learn_skills=True  # Learn from this execution
        )

        return result

    async def _execute_task_normally(self, task: str) -> Any:
        """
        Override to implement actual task execution

        This is where you'd call the normal agent brain logic
        """
        # Example: Execute using ReAct pattern or planning
        logger.info(f"Executing with normal agent brain: {task}")

        # Simulate some actions
        await self._simulate_actions(task)

        return {"success": True, "task": task}

    async def _simulate_actions(self, task: str):
        """Simulate executing some actions (for example purposes)"""
        # Example actions that would be recorded
        self.record_action(
            tool="playwright_navigate",
            arguments={"url": "https://example.com"}
        )

        self.record_action(
            tool="playwright_fill",
            arguments={"selector": "#search", "value": task}
        )

        self.record_action(
            tool="playwright_click",
            arguments={"selector": "button.submit"}
        )


# Interactive skill management commands
async def skill_command_handler(command: str, args: List[str]) -> str:
    """
    Handle skill-related commands from the CLI

    Commands:
    - skill search <query> - Search for skills
    - skill list [category] - List all skills or by category
    - skill show <skill_id> - Show skill details
    - skill stats - Show library statistics
    - skill export <path> - Export skills
    - skill import <path> - Import skills
    - skill compose <skill_ids> - Compose skills into workflow

    Args:
        command: Main command ("skill")
        args: Command arguments

    Returns:
        Response string
    """
    library = get_skill_library()

    if not args:
        return """
Skill Library Commands:
  skill search <query>       - Search for skills
  skill list [category]      - List all skills
  skill show <skill_id>      - Show skill details
  skill stats                - Show statistics
  skill export <path>        - Export skills to file
  skill import <path>        - Import skills from file
"""

    subcommand = args[0]

    if subcommand == "search":
        if len(args) < 2:
            return "Usage: skill search <query>"

        query = " ".join(args[1:])
        skills = library.search_skills(query=query, limit=10)

        if not skills:
            return f"No skills found for: {query}"

        lines = [f"Found {len(skills)} skills:\n"]
        for i, skill in enumerate(skills, 1):
            lines.append(f"{i}. {skill.name} ({skill.skill_id})")
            lines.append(f"   {skill.description}")
            lines.append(f"   Category: {skill.category.value}")
            lines.append(f"   Success Rate: {skill.metrics.success_rate:.1%}")
            lines.append(f"   Uses: {skill.metrics.total_uses}")
            lines.append("")

        return "\n".join(lines)

    elif subcommand == "list":
        category = None
        if len(args) > 1:
            try:
                category = SkillCategory(args[1])
            except ValueError:
                return f"Invalid category: {args[1]}"

        skills = [s for s in library.skills.values()
                 if category is None or s.category == category]

        lines = [f"Skills ({len(skills)} total):\n"]
        for skill in sorted(skills, key=lambda s: s.name):
            lines.append(f"  {skill.skill_id}: {skill.name}")
            lines.append(f"    Category: {skill.category.value}, Status: {skill.status.value}")

        return "\n".join(lines)

    elif subcommand == "show":
        if len(args) < 2:
            return "Usage: skill show <skill_id>"

        skill_id = args[1]
        skill = library.get_skill(skill_id)

        if not skill:
            return f"Skill not found: {skill_id}"

        lines = [
            f"Skill: {skill.name}",
            f"ID: {skill.skill_id}",
            f"Category: {skill.category.value}",
            f"Status: {skill.status.value}",
            f"Version: {skill.version}",
            f"",
            f"Description: {skill.description}",
            f"",
            f"Metrics:",
            f"  Total Uses: {skill.metrics.total_uses}",
            f"  Success Rate: {skill.metrics.success_rate:.1%}",
            f"  Avg Execution Time: {skill.metrics.avg_execution_time:.2f}s",
            f"",
            f"Required Tools: {', '.join(skill.required_tools)}",
            f"Tags: {', '.join(skill.tags)}",
            f"",
            f"Code:",
            f"```python",
            skill.code,
            f"```",
        ]

        return "\n".join(lines)

    elif subcommand == "stats":
        stats = library.get_statistics()

        lines = [
            "Skill Library Statistics:",
            f"  Total Skills: {stats['total_skills']}",
            f"  Active Skills: {stats['by_status'].get('active', 0)}",
            f"  Total Uses: {stats['total_uses']}",
            f"  Average Success Rate: {stats['avg_success_rate']:.1%}",
            f"  Vector Retrieval: {'Enabled' if stats['retrieval_enabled'] else 'Disabled'}",
            "",
            "By Category:",
        ]

        for category, count in stats['by_category'].items():
            lines.append(f"  {category}: {count}")

        return "\n".join(lines)

    elif subcommand == "export":
        if len(args) < 2:
            return "Usage: skill export <path>"

        from pathlib import Path
        output_path = Path(args[1])
        library.export_skills(output_path)
        return f"Exported skills to: {output_path}"

    elif subcommand == "import":
        if len(args) < 2:
            return "Usage: skill import <path>"

        from pathlib import Path
        input_path = Path(args[1])
        library.import_skills(input_path)
        return f"Imported skills from: {input_path}"

    else:
        return f"Unknown subcommand: {subcommand}"


# Example usage
async def example_usage():
    """Example of using the skill-aware agent"""

    # Create agent
    agent = ExampleSkillAwareAgent()

    # Execute a task - will search for applicable skills first
    result1 = await agent.execute_task("Login to example.com and extract contacts")

    # This execution will be recorded and learned from
    result2 = await agent.execute_task("Navigate to pricing page and extract prices")

    # Now the agent has learned skills, try similar task
    result3 = await agent.execute_task("Login to another-site.com and extract contacts")
    # This might reuse the learned login skill!

    # Get suggestions for a new task
    suggestions = await agent.suggest_skills_for_task("Fill out contact form")
    print(f"Skill suggestions: {suggestions}")

    # Get statistics
    stats = agent.get_skill_statistics()
    print(f"Library stats: {stats}")


if __name__ == "__main__":
    asyncio.run(example_usage())
