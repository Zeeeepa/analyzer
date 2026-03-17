"""
Autonomous Learning Engine - Recursive Self-Improvement Protocol

Iterative capability enhancement through:
1. Task execution and outcome analysis
2. Autonomous performance evaluation
3. Strategy extraction and persistence
4. Adaptive difficulty calibration
5. Continuous protocol refinement

Enables extended autonomous learning cycles on GPU infrastructure.

PROTOCOL v2:
- Execution timeout protection
- Checkpoint-based recovery
- Resource management optimization
- Enhanced signal capture
- System health monitoring
"""

import asyncio
import json
import time
import gc
import os
import signal
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict, field
from loguru import logger
import yaml
import ollama

from .task_generator import TaskGenerator, TrainingTask
from .training_enhancements import TrainingEnhancer, create_training_enhancer


@dataclass
class TaskResult:
    """Result of a training task execution."""
    task: TrainingTask
    success: bool
    output: str
    execution_time: float
    iterations: int
    tool_calls: int
    errors: List[str]
    learnings_extracted: int
    timestamp: str
    # NEW: Capture actual tool calls for better learning
    tool_history: List[Dict] = field(default_factory=list)
    selectors_used: List[str] = field(default_factory=list)


@dataclass
class TrainingSession:
    """A complete training session."""
    session_id: str
    start_time: str
    end_time: Optional[str]
    target_duration_hours: float
    tasks_completed: int
    tasks_successful: int
    strategies_learned: int
    strategies_pruned: int
    performance_history: List[Dict]
    # NEW: For crash recovery
    last_checkpoint: Optional[str] = None
    resumed_from: Optional[str] = None


class SelfPlayEngine:
    """
    Autonomous Learning Engine - Extended duration recursive improvement.

    Protocol architecture:
    - Scenario generation (task synthesis)
    - Autonomous execution (task completion)
    - Strategy optimization (playbook refinement)
    - Capability enhancement (iterative improvement)
    """

    # Task timeout (prevent infinite hangs)
    TASK_TIMEOUT_SECONDS = 180  # 3 minutes max per task

    # Memory cleanup frequency
    CLEANUP_EVERY_N_TASKS = 10

    # Checkpoint frequency
    CHECKPOINT_EVERY_N_BATCHES = 2

    # Parallel execution
    PARALLEL_TASKS = 3  # Run 3 tasks simultaneously
    MAX_PARALLEL_TASKS = 4  # Maximum parallel tasks

    def __init__(self, config_path: str = "config/config.yaml"):
        # Load config
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        # Initialize components
        self.task_generator = TaskGenerator()

        # Training state
        self.session: Optional[TrainingSession] = None
        self.results: List[TaskResult] = []

        # Performance tracking
        self.success_window = []  # Recent success rates
        self.window_size = 20

        # Learning tracking
        self.strategies_before = 0
        self.strategies_after = 0

        # Paths
        self.training_dir = Path("training/sessions")
        self.training_dir.mkdir(parents=True, exist_ok=True)

        # Load ACE components
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from ace.playbook import Playbook
        from ace.reflector import Reflector

        self.playbook = Playbook()
        self.reflector = Reflector()

        # Enable training mode for more permissive learning
        self.reflector.training_mode = True

        self.strategies_before = len(self.playbook.strategies)

        # Track for cleanup
        self._task_counter = 0
        self._mcp_client = None

        # Initialize training enhancer (6 major improvements)
        self.enhancer = create_training_enhancer(self.config)
        self._enhancer_initialized = False

    def _cleanup_memory(self):
        """Periodic memory cleanup to prevent GPU/RAM bloat."""
        gc.collect()
        # Clear Ollama cache if needed
        try:
            # Force Python garbage collection
            gc.collect()
            logger.debug("Memory cleanup completed")
        except Exception as e:
            logger.warning(f"Memory cleanup warning: {e}")

    def _check_system_health(self) -> bool:
        """Check if system is healthy enough to continue."""
        try:
            # Test Ollama is responsive
            ollama.list()
            return True
        except Exception as e:
            logger.error(f"System health check failed: {e}")
            return False

    async def _reconnect_mcp(self):
        """Reconnect MCP servers if connection lost."""
        if self._mcp_client:
            try:
                await self._mcp_client.disconnect_all_servers()
            except:
                pass
            try:
                await self._mcp_client.connect_all_servers()
                logger.info("MCP reconnected successfully")
            except Exception as e:
                logger.error(f"MCP reconnection failed: {e}")
                raise

    async def run_training(self,
                           duration_hours: float = 3.0,
                           batch_size: int = 5,
                           curriculum: bool = True,
                           headless: bool = True,
                           resume_from: str = None) -> TrainingSession:
        """
        Run self-play training for specified duration.

        Args:
            duration_hours: How long to train (default 3 hours)
            batch_size: Tasks per batch before analysis
            curriculum: Use progressive difficulty
            headless: Run browser headlessly
            resume_from: Session ID to resume from (crash recovery)
        """
        # Check for crash recovery
        if resume_from:
            loaded = self._load_checkpoint(resume_from)
            if loaded:
                logger.info(f"📂 Resuming from checkpoint: {resume_from}")
                self.session.resumed_from = resume_from
            else:
                logger.warning(f"Could not load checkpoint {resume_from}, starting fresh")
                resume_from = None

        # Initialize session (if not resuming)
        if not resume_from:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.session = TrainingSession(
                session_id=session_id,
                start_time=datetime.now().isoformat(),
                end_time=None,
                target_duration_hours=duration_hours,
                tasks_completed=0,
                tasks_successful=0,
                strategies_learned=0,
                strategies_pruned=0,
                performance_history=[]
            )

        logger.info(f"◈ Initiating {duration_hours}h learning protocol: {self.session.session_id}")

        # Calculate end time
        end_time = datetime.now() + timedelta(hours=duration_hours)

        # Import brain and MCP
        from agent.brain_enhanced_v2 import create_enhanced_brain as create_genius_brain
        from agent.mcp_client import MCPClient

        # Initialize MCP with retry
        mcp = MCPClient()
        self._mcp_client = mcp

        max_retries = 3
        for attempt in range(max_retries):
            try:
                await mcp.connect_all_servers()
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"MCP connection attempt {attempt+1} failed, retrying...")
                    await asyncio.sleep(2)
                else:
                    raise RuntimeError(f"Failed to connect MCP after {max_retries} attempts: {e}")

        # Initialize training enhancer
        if not self._enhancer_initialized:
            await self.enhancer.initialize(headless=headless)
            self._enhancer_initialized = True
            logger.info("◈ Training enhancer initialized (6 improvements active)")

        try:
            batch_num = 0
            total_tasks = int(duration_hours * 60)  # ~1 task per minute estimate

            # Get curriculum settings from enhancer
            task_settings = self.enhancer.get_task_settings()
            logger.info(f"◈ Starting at curriculum level: {task_settings['difficulty']['name']}")
            logger.info(f"◈ Allowed categories: {', '.join(task_settings['allowed_categories'])}")

            if curriculum:
                all_tasks = self.task_generator.generate_progressive_curriculum(total_tasks)
            else:
                all_tasks = self.task_generator.generate_batch(total_tasks, ensure_variety=True)

            task_index = 0

            while datetime.now() < end_time:
                batch_num += 1
                logger.info(f"\n{'='*60}")
                logger.info(f"◈ CYCLE {batch_num} - {(end_time - datetime.now()).seconds // 60} minutes remaining")
                logger.info(f"{'='*60}")

                # Get batch of tasks
                batch_tasks = []
                for _ in range(batch_size):
                    if task_index < len(all_tasks):
                        batch_tasks.append(all_tasks[task_index])
                        task_index += 1
                    else:
                        # Generate more if needed
                        batch_tasks.append(self.task_generator.generate_task())

                # Execute batch IN PARALLEL
                batch_results = await self._execute_batch_parallel(
                    batch_tasks, mcp, create_genius_brain, end_time
                )

                # Batch analysis and learning
                await self._analyze_batch(batch_results)

                # Self-evaluation phase
                if batch_num % 3 == 0:  # Every 3 batches
                    await self._self_evaluation_phase(mcp)

                # Meta-learning phase
                if batch_num % 5 == 0:  # Every 5 batches
                    await self._meta_learning_phase()

                # Prune low-value strategies
                if batch_num % 10 == 0:  # Every 10 batches
                    pruned = self.playbook.prune_low_value_strategies()
                    self.session.strategies_pruned += pruned
                    if pruned > 0:
                        logger.info(f"◈ Pruned {pruned} low-value strategies")

                # Save checkpoint (more frequently for crash recovery)
                if batch_num % self.CHECKPOINT_EVERY_N_BATCHES == 0:
                    self._save_checkpoint()
                    self.session.last_checkpoint = datetime.now().isoformat()

                # Health check every 5 batches
                if batch_num % 5 == 0:
                    if not self._check_system_health():
                        logger.warning("System health check failed, attempting recovery...")
                        await self._reconnect_mcp()

                # Record performance snapshot
                self.session.performance_history.append({
                    'batch': batch_num,
                    'timestamp': datetime.now().isoformat(),
                    'success_rate': sum(self.success_window) / len(self.success_window) if self.success_window else 0,
                    'total_strategies': len(self.playbook.strategies),
                    'tasks_completed': self.session.tasks_completed
                })

                # Brief pause between batches
                await asyncio.sleep(2)

        finally:
            # Cleanup
            await mcp.disconnect_all_servers()

            # Shutdown enhancer
            if self._enhancer_initialized:
                await self.enhancer.shutdown()
                self._enhancer_initialized = False

            # Finalize session
            self.session.end_time = datetime.now().isoformat()
            self.strategies_after = len(self.playbook.strategies)
            self.session.strategies_learned = max(0, self.strategies_after - self.strategies_before)

            # Save final session
            self._save_session()

            # Generate report
            self._generate_report()

        return self.session

    async def _execute_batch_parallel(self, tasks: List[TrainingTask], mcp, brain_factory, end_time) -> List[TaskResult]:
        """
        Execute multiple tasks in parallel for faster training.
        Runs PARALLEL_TASKS tasks simultaneously.
        """
        from rich.console import Console
        console = Console()

        results = []
        task_queue = list(tasks)

        while task_queue and datetime.now() < end_time:
            # Take up to PARALLEL_TASKS from queue
            current_batch = task_queue[:self.PARALLEL_TASKS]
            task_queue = task_queue[self.PARALLEL_TASKS:]

            console.print(f"\n[bold cyan]⚡ Running {len(current_batch)} tasks in parallel...[/bold cyan]")

            # Create tasks for parallel execution
            async_tasks = []
            for i, task in enumerate(current_batch):
                console.print(f"  [{i+1}] {task.category}: {task.prompt[:50]}...")
                brain = brain_factory(self.config, mcp)
                async_tasks.append(self._execute_single_task_safe(brain, task, i+1))

            # Run all tasks in parallel
            parallel_results = await asyncio.gather(*async_tasks, return_exceptions=True)

            # Process results
            for i, result in enumerate(parallel_results):
                if isinstance(result, Exception):
                    # Task raised exception
                    task = current_batch[i]
                    result = TaskResult(
                        task=task,
                        success=False,
                        output=f"Exception: {result}",
                        execution_time=0,
                        iterations=0,
                        tool_calls=0,
                        errors=[str(result)],
                        learnings_extracted=0,
                        timestamp=datetime.now().isoformat()
                    )

                results.append(result)
                self.results.append(result)

                # Update stats
                self.session.tasks_completed += 1
                if result.success:
                    self.session.tasks_successful += 1

                self.success_window.append(1 if result.success else 0)
                if len(self.success_window) > self.window_size:
                    self.success_window.pop(0)

                self._task_counter += 1

            # Show parallel results
            success_count = sum(1 for r in parallel_results if isinstance(r, TaskResult) and r.success)
            success_rate = sum(self.success_window) / len(self.success_window) * 100 if self.success_window else 0
            console.print(f"[green]  ✓ Batch complete: {success_count}/{len(current_batch)} succeeded "
                         f"(Rolling: {success_rate:.1f}%)[/green]")

            # Record failures for curiosity-driven retry
            for i, result in enumerate(parallel_results):
                if isinstance(result, TaskResult) and not result.success:
                    self.task_generator.record_failure(current_batch[i])

            # Memory cleanup
            if self._task_counter % self.CLEANUP_EVERY_N_TASKS == 0:
                self._cleanup_memory()

        return results

    async def _execute_single_task_safe(self, brain, task: TrainingTask, task_num: int) -> TaskResult:
        """Execute a single task with timeout and error handling."""
        from rich.console import Console
        console = Console()

        try:
            result = await asyncio.wait_for(
                self._execute_task(brain, task, task_num),
                timeout=self.TASK_TIMEOUT_SECONDS
            )
            return result
        except asyncio.TimeoutError:
            console.print(f"  [yellow][{task_num}] ⏰ Timed out[/yellow]")
            return TaskResult(
                task=task,
                success=False,
                output="Task timed out",
                execution_time=self.TASK_TIMEOUT_SECONDS,
                iterations=0,
                tool_calls=0,
                errors=["TimeoutError"],
                learnings_extracted=0,
                timestamp=datetime.now().isoformat()
            )
        except Exception as e:
            console.print(f"  [red][{task_num}] Error: {e}[/red]")
            return TaskResult(
                task=task,
                success=False,
                output=f"Error: {e}",
                execution_time=0,
                iterations=0,
                tool_calls=0,
                errors=[str(e)],
                learnings_extracted=0,
                timestamp=datetime.now().isoformat()
            )

    async def _execute_task(self, brain, task: TrainingTask, task_num: int = 0) -> TaskResult:
        """Execute a single training task with enhanced verification."""
        from rich.console import Console
        from agent.bs_detector import get_integrity_validator
        from agent.ground_truth_validator import get_ground_truth_validator
        console = Console()

        start_time = time.time()
        errors = []
        output = ""
        integrity_corrected = False
        page_content = ""
        actual_url = ""
        screenshot_path = ""
        tool_history = []

        # Show task starting
        prefix = f"[{task_num}]" if task_num else ""
        console.print(f"  {prefix} [dim]Starting: {task.prompt[:40]}...[/dim]")

        try:
            output = await brain.run(task.prompt)

            # Try to get page content for ground truth validation
            try:
                if hasattr(brain, 'mcp') and brain.mcp:
                    # Get current page state for validation
                    snapshot_result = await brain.mcp.call_tool('playwright_get_text', {'selector': 'body'})
                    if isinstance(snapshot_result, dict):
                        page_content = snapshot_result.get('content', snapshot_result.get('text', str(snapshot_result)))
                    else:
                        page_content = str(snapshot_result) if snapshot_result else ""

                    # Get current URL via JavaScript
                    url_result = await brain.mcp.call_tool('playwright_evaluate', {
                        'script': 'window.location.href'
                    })
                    if isinstance(url_result, dict):
                        actual_url = url_result.get('result', url_result.get('content', ''))
                    else:
                        actual_url = str(url_result) if url_result else ""

                    # Take screenshot for vision verification
                    try:
                        import uuid
                        screenshot_path = f"/tmp/training_screenshot_{uuid.uuid4().hex[:8]}.png"
                        # Use take_screenshot tool with proper boolean
                        await brain.mcp.call_tool('take_screenshot', {'name': screenshot_path, 'full_page': False})
                    except Exception as ss_err:
                        logger.debug(f"Screenshot capture failed: {ss_err}")
                        # Fallback: try playwright_screenshot directly
                        try:
                            await brain.mcp.call_tool('playwright_screenshot', {'path': screenshot_path})
                        except:
                            screenshot_path = ""

                    # Capture tool history if available
                    if hasattr(brain, 'tool_history'):
                        tool_history = brain.tool_history[-20:]  # Last 20 tool calls
            except Exception as e:
                logger.debug(f"Could not get page state for validation: {e}")

            # GROUND TRUTH VALIDATION - Real verification, not vibes
            gt_validator = get_ground_truth_validator()
            validation_passed = True
            validation_details = []

            # Validate based on task type
            # Include all extraction-like categories
            extraction_categories = ['extraction', 'search', 'sdr_prospecting',
                                     'table_extraction', 'form_filling', 'data_extraction']

            if task.category in extraction_categories or 'extract' in task.category.lower():
                # Extraction tasks: verify data exists in page
                extraction_result = gt_validator.verify_extraction(
                    extracted_data=output,
                    page_content=page_content,
                    task_type=task.category
                )
                validation_passed = extraction_result.is_valid
                validation_details.append(f"extraction:{extraction_result.details}")

                if not validation_passed:
                    console.print(f"  {prefix} [yellow]◈ Ground truth fail: {extraction_result.details}[/yellow]")

            elif task.category in ['navigation', 'exploration']:
                # Navigation tasks: verify URL matches intent
                intended_url = self._extract_url_from_prompt(task.prompt)
                if intended_url and actual_url:
                    nav_result = gt_validator.verify_navigation(intended_url, actual_url)
                    validation_passed = nav_result.is_valid
                    validation_details.append(f"navigation:{nav_result.details}")

                    if not validation_passed:
                        console.print(f"  {prefix} [yellow]◈ URL mismatch: {nav_result.details}[/yellow]")

            # Also run integrity check (catches hallucinated patterns)
            integrity_validator = get_integrity_validator()
            is_valid, issues, hint = integrity_validator.verify_output(
                claimed_output=output,
                task_type=task.category
            )

            if not is_valid:
                console.print(f"  {prefix} [yellow]◈ Integrity issue: {issues}[/yellow]")
                console.print(f"  {prefix} [dim]Initiating correction protocol...[/dim]")

                correction_prompt = integrity_validator.create_correction_prompt(output, issues, hint)
                try:
                    corrected_output = await brain.run(correction_prompt)
                    output = corrected_output
                    integrity_corrected = True
                    console.print(f"  {prefix} [cyan]◈ Corrected[/cyan]")
                except:
                    pass

            # Final success determination: ground truth takes precedence
            success = validation_passed and self._evaluate_success(task, output, brain.get_stats())

            # ENHANCED PROCESSING - Vision verification, quality scoring, LoRA collection
            enhanced_result = None
            quality_score = 0.0
            try:
                elapsed_seconds = time.time() - start_time
                enhanced_result = await self.enhancer.process_task_result(
                    task_prompt=task.prompt,
                    output=output,
                    screenshot_path=screenshot_path,
                    page_url=actual_url,
                    page_content=page_content,
                    elapsed_seconds=elapsed_seconds,
                    tool_calls=brain.get_stats().get('tool_calls', 0),
                    category=task.category,
                    domain=task.domain,
                    error=errors[0] if errors else None
                )

                # Use enhanced success determination if available
                if enhanced_result:
                    success = enhanced_result.get('success', success)
                    quality_score = enhanced_result.get('quality', {}).get('overall', 0.0)

                    # Log curriculum level changes
                    curriculum_change = enhanced_result.get('curriculum', {})
                    if curriculum_change.get('changed'):
                        direction = curriculum_change.get('direction', '')
                        new_level = curriculum_change.get('new_level', 1)
                        console.print(f"  [cyan]◈ Curriculum level {direction}: now at level {new_level}[/cyan]")

            except Exception as e:
                logger.debug(f"Enhanced processing error: {e}")

            # Sample for human review queue (5% of "successes")
            if success and gt_validator.should_sample_for_review():
                gt_validator.queue_for_review(
                    task_prompt=task.prompt,
                    claimed_output=output,
                    page_snapshot=page_content[:1000],
                    validation_result=extraction_result if task.category in ['extraction', 'search'] else None
                )

            # Show result with quality score
            if success:
                status = "[green]✓ Verified[/green]"
                if integrity_corrected:
                    status += " [cyan](corrected)[/cyan]"
                if quality_score > 0:
                    status += f" [dim](Q:{quality_score:.2f})[/dim]"
                console.print(f"  {prefix} {status} ({time.time()-start_time:.1f}s)")
            else:
                console.print(f"  {prefix} [yellow]✗ Failed[/yellow] ({time.time()-start_time:.1f}s)")

        except Exception as e:
            success = False
            errors.append(str(e))
            output = f"Error: {e}"
            console.print(f"  {prefix} [red]✗ Error: {str(e)[:50]}[/red]")
            logger.error(f"Task failed: {e}")

        execution_time = time.time() - start_time
        stats = brain.get_stats()

        # Extract learnings from this task
        learnings = await self._extract_learnings(task, output, success)

        return TaskResult(
            task=task,
            success=success,
            output=output[:500],  # Truncate for storage
            execution_time=execution_time,
            iterations=stats.get('iterations', 0),
            tool_calls=stats.get('tool_calls', 0),
            errors=errors,
            learnings_extracted=len(learnings),
            timestamp=datetime.now().isoformat()
        )

    def _evaluate_success(self, task: TrainingTask, output: str, stats: Dict) -> bool:
        """
        Evaluate if a task was successful.
        Uses heuristics based on task type and output.
        """
        output_lower = output.lower()

        # Failure indicators
        failure_indicators = [
            'error', 'failed', 'could not', 'unable to',
            'timed out', 'not found', 'exception'
        ]

        # Check for explicit failures
        if any(ind in output_lower for ind in failure_indicators):
            # But some tasks are ABOUT error handling
            if task.category == 'error_recovery':
                # Success if handled gracefully
                return 'handled' in output_lower or 'gracefully' in output_lower or 'fallback' in output_lower
            return False

        # Check for task-specific success
        if task.category == 'navigation':
            return 'navigated' in output_lower or 'loaded' in output_lower or 'screenshot' in output_lower

        if task.category == 'extraction':
            # Should have extracted something
            return len(output) > 100 or 'extracted' in output_lower or 'found' in output_lower

        if task.category == 'search':
            return 'search' in output_lower or 'results' in output_lower or 'found' in output_lower

        if task.category == 'interaction':
            return 'clicked' in output_lower or 'filled' in output_lower or 'completed' in output_lower

        if task.category == 'analysis':
            # Should have substantial analysis
            return len(output) > 200

        # Default: assume success if no errors and some output
        return len(output) > 50 and stats.get('tool_calls', 0) > 0

    def _extract_url_from_prompt(self, prompt: str) -> Optional[str]:
        """Extract URL from task prompt for navigation validation."""
        import re
        # Match full URLs
        url_match = re.search(r'https?://[^\s<>"\']+', prompt)
        if url_match:
            return url_match.group(0).rstrip('.,;')

        # Match domain patterns like "example.com" or "go to example.com"
        domain_match = re.search(r'(?:go to|visit|navigate to|open)\s+([a-z0-9\-]+\.[a-z]{2,}(?:/[^\s]*)?)', prompt, re.IGNORECASE)
        if domain_match:
            domain = domain_match.group(1)
            return f"https://{domain}"

        return None

    async def _extract_learnings(self, task: TrainingTask, output: str, success: bool) -> List[Tuple]:
        """Extract learnings from task execution and add to playbook."""
        # Create pseudo-conversation history for reflector
        conversation_history = [
            {'role': 'user', 'content': task.prompt},
            {'role': 'assistant', 'content': output}
        ]

        # Use reflector to extract learnings
        learnings = self.reflector.reflect_on_task(
            conversation_history=conversation_history,
            task_success=success,
            user_prompt=task.prompt
        )

        # Add quality learnings to playbook
        added_count = 0
        for domain, action_type, strategy, marker in learnings:
            # Quality check
            if self.reflector.is_quality_strategy(strategy):
                if self.playbook.add_strategy(domain, action_type, strategy, marker):
                    added_count += 1

        if added_count > 0:
            self.playbook.save()
            self.session.strategies_learned += added_count
            logger.info(f"◈ Added {added_count} new strategies to repository")

        return learnings

    async def _analyze_batch(self, results: List[TaskResult]):
        """Analyze batch results for patterns."""
        # Group by success/failure
        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]

        if failures:
            # Analyze failure patterns
            failure_categories = {}
            for r in failures:
                cat = r.task.category
                failure_categories[cat] = failure_categories.get(cat, 0) + 1

            logger.info(f"📊 Batch analysis: {len(successes)}/{len(results)} successful")
            if failure_categories:
                logger.info(f"   Failures by category: {failure_categories}")

        # Check for consistently failing domains
        domain_failures = {}
        for r in failures:
            dom = r.task.domain
            domain_failures[dom] = domain_failures.get(dom, 0) + 1

        for domain, count in domain_failures.items():
            if count >= 2:
                # This domain needs attention
                logger.warning(f"⚠️ Domain {domain} failing frequently ({count} times)")

    async def _self_evaluation_phase(self, mcp):
        """
        Self-evaluation phase - autonomous performance analysis.
        Extracts patterns from execution outcomes for strategy refinement.
        """
        logger.info("\n◈ SELF-EVALUATION PROTOCOL")

        # Get recent results
        recent = self.results[-10:] if len(self.results) >= 10 else self.results

        # Generate self-evaluation prompt
        eval_prompt = f"""Analyze these recent task executions and identify patterns:

Tasks executed: {len(recent)}
Success rate: {sum(1 for r in recent if r.success) / len(recent) * 100:.1f}%

Successful patterns:
{self._summarize_successes(recent)}

Failure patterns:
{self._summarize_failures(recent)}

Based on this analysis:
1. What strategies are working well?
2. What strategies should be avoided?
3. What new strategies should be tried?

Be specific and actionable."""

        try:
            response = ollama.generate(
                model=self.config['llm']['main_model'],
                prompt=eval_prompt,
                options={'temperature': 0.3}
            )

            evaluation = response['response']
            logger.info(f"Self-evaluation insights:\n{evaluation[:500]}...")

            # Extract and add strategies from evaluation
            await self._process_evaluation(evaluation)

        except Exception as e:
            logger.error(f"Self-evaluation failed: {e}")

    def _summarize_successes(self, results: List[TaskResult]) -> str:
        """Summarize successful task patterns."""
        successes = [r for r in results if r.success]
        if not successes:
            return "No recent successes"

        summary = []
        for r in successes[:5]:
            summary.append(f"- {r.task.category}/{r.task.difficulty}: {r.task.prompt[:50]}...")
        return "\n".join(summary)

    def _summarize_failures(self, results: List[TaskResult]) -> str:
        """Summarize failed task patterns."""
        failures = [r for r in results if not r.success]
        if not failures:
            return "No recent failures"

        summary = []
        for r in failures[:5]:
            summary.append(f"- {r.task.category}/{r.task.difficulty}: {r.task.prompt[:50]}...")
            if r.errors:
                summary.append(f"  Error: {r.errors[0][:100]}")
        return "\n".join(summary)

    async def _process_evaluation(self, evaluation: str):
        """Extract actionable strategies from self-evaluation."""
        # Use LLM to extract specific strategies
        extract_prompt = f"""From this self-evaluation, extract specific strategies as JSON array:

Evaluation:
{evaluation[:1500]}

Return JSON only:
[
  {{"domain": "*", "action_type": "...", "strategy": "...", "marker": "✓"}},
  ...
]

Only include highly specific, actionable strategies."""

        try:
            response = ollama.generate(
                model=self.config['llm']['router_model'],  # Fast model
                prompt=extract_prompt,
                options={'temperature': 0.1}
            )

            # Parse JSON
            import re
            json_match = re.search(r'\[[\s\S]*\]', response['response'])
            if json_match:
                strategies = json.loads(json_match.group(0))
                for s in strategies:
                    if self.reflector.is_quality_strategy(s.get('strategy', '')):
                        self.playbook.add_strategy(
                            s.get('domain', '*'),
                            s.get('action_type', 'general'),
                            s['strategy'],
                            s.get('marker', '✓')
                        )
                self.playbook.save()

        except Exception as e:
            logger.error(f"Strategy extraction failed: {e}")

    async def _meta_learning_phase(self):
        """
        Meta-learning phase - optimize the learning protocol parameters.
        """
        logger.info("\n◈ META-LEARNING PROTOCOL")

        # Analyze playbook health
        stats = self.playbook.get_stats()
        logger.info(f"Playbook stats: {stats}")

        # Check for strategy imbalance
        domains = stats.get('domains', [])
        if '*' in domains and len(domains) < 3:
            logger.info("⚠️ Strategies too generic - need more domain-specific patterns")

        # Adjust task generation based on performance
        recent_success = sum(self.success_window) / len(self.success_window) if self.success_window else 0.5

        if recent_success > 0.8:
            # Doing well - increase difficulty
            self.task_generator.difficulty_distribution = {
                'easy': 0.1,
                'medium': 0.4,
                'hard': 0.5
            }
            logger.info("📈 High success rate - increasing difficulty")

        elif recent_success < 0.4:
            # Struggling - decrease difficulty
            self.task_generator.difficulty_distribution = {
                'easy': 0.5,
                'medium': 0.4,
                'hard': 0.1
            }
            logger.info("📉 Low success rate - decreasing difficulty")

    def _save_checkpoint(self):
        """Save training checkpoint for crash recovery."""
        checkpoint_path = self.training_dir / f"checkpoint_{self.session.session_id}.json"

        checkpoint = {
            'session': asdict(self.session),
            'results_summary': {
                'total': len(self.results),
                'successful': sum(1 for r in self.results if r.success),
                'by_category': self._count_by_category()
            },
            'playbook_stats': self.playbook.get_stats(),
            'task_generator_stats': self.task_generator.get_stats(),
            # For recovery
            'success_window': self.success_window,
            'task_counter': self._task_counter,
            'difficulty_distribution': self.task_generator.difficulty_distribution
        }

        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint, f, indent=2, default=str)

        logger.debug(f"Checkpoint saved: {checkpoint_path}")

    def _load_checkpoint(self, session_id: str) -> bool:
        """Load checkpoint for crash recovery."""
        checkpoint_path = self.training_dir / f"checkpoint_{session_id}.json"

        if not checkpoint_path.exists():
            return False

        try:
            with open(checkpoint_path) as f:
                checkpoint = json.load(f)

            # Restore session
            session_data = checkpoint['session']
            self.session = TrainingSession(
                session_id=session_data['session_id'],
                start_time=session_data['start_time'],
                end_time=None,
                target_duration_hours=session_data['target_duration_hours'],
                tasks_completed=session_data['tasks_completed'],
                tasks_successful=session_data['tasks_successful'],
                strategies_learned=session_data['strategies_learned'],
                strategies_pruned=session_data['strategies_pruned'],
                performance_history=session_data['performance_history']
            )

            # Restore state
            self.success_window = checkpoint.get('success_window', [])
            self._task_counter = checkpoint.get('task_counter', 0)
            if 'difficulty_distribution' in checkpoint:
                self.task_generator.difficulty_distribution = checkpoint['difficulty_distribution']

            logger.info(f"Restored checkpoint: {session_data['tasks_completed']} tasks completed")
            return True

        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return False

    def _count_by_category(self) -> Dict:
        """Count results by category."""
        counts = {}
        for r in self.results:
            cat = r.task.category
            if cat not in counts:
                counts[cat] = {'total': 0, 'success': 0}
            counts[cat]['total'] += 1
            if r.success:
                counts[cat]['success'] += 1
        return counts

    def _save_session(self):
        """Save complete session data."""
        session_path = self.training_dir / f"session_{self.session.session_id}.json"

        session_data = {
            'session': asdict(self.session),
            'results': [
                {
                    'task_prompt': r.task.prompt,
                    'task_category': r.task.category,
                    'task_difficulty': r.task.difficulty,
                    'success': r.success,
                    'execution_time': r.execution_time,
                    'iterations': r.iterations,
                    'tool_calls': r.tool_calls,
                    'errors': r.errors,
                    'learnings': r.learnings_extracted,
                    'timestamp': r.timestamp
                }
                for r in self.results
            ],
            'final_playbook_stats': self.playbook.get_stats()
        }

        with open(session_path, 'w') as f:
            json.dump(session_data, f, indent=2)

        logger.info(f"◈ Session data persisted: {session_path}")

    def _generate_report(self):
        """Generate human-readable training report."""
        from agent.ground_truth_validator import get_ground_truth_validator

        report_path = self.training_dir / f"report_{self.session.session_id}.txt"

        total_time = (datetime.fromisoformat(self.session.end_time) -
                      datetime.fromisoformat(self.session.start_time))

        success_rate = (self.session.tasks_successful / self.session.tasks_completed * 100
                       if self.session.tasks_completed > 0 else 0)

        # Get ground truth validation stats
        gt_validator = get_ground_truth_validator()
        gt_stats = gt_validator.get_stats()

        report = f"""
╔══════════════════════════════════════════════════════════════════╗
║           SDR-1 AUTONOMOUS LEARNING PROTOCOL REPORT              ║
╠══════════════════════════════════════════════════════════════════╣

◈ Session ID: {self.session.session_id}
◈ Duration: {total_time}
◈ Target: {self.session.target_duration_hours} hours

═══════════════════════════════════════════════════════════════════
                          TASK METRICS
═══════════════════════════════════════════════════════════════════

Total Tasks Completed: {self.session.tasks_completed}
Verified Successful:   {self.session.tasks_successful}
Success Rate:          {success_rate:.1f}%

By Category:
{self._format_category_stats()}

═══════════════════════════════════════════════════════════════════
                     GROUND TRUTH VALIDATION
═══════════════════════════════════════════════════════════════════

Total Validations:     {gt_stats['total_validations']}
Passed Verification:   {gt_stats['passed']}
Failed Verification:   {gt_stats['failed']}
Verification Rate:     {gt_stats['pass_rate']*100:.1f}%
Human Review Queue:    {gt_stats['pending_reviews']} items pending

═══════════════════════════════════════════════════════════════════
                        LEARNING METRICS
═══════════════════════════════════════════════════════════════════

Strategies Before:     {self.strategies_before}
Strategies After:      {self.strategies_after}
Net New Strategies:    {self.session.strategies_learned}
Strategies Pruned:     {self.session.strategies_pruned}

Playbook Growth:       {((self.strategies_after / self.strategies_before - 1) * 100) if self.strategies_before > 0 else 0:.1f}%

═══════════════════════════════════════════════════════════════════
                     TRAINING ENHANCEMENTS
═══════════════════════════════════════════════════════════════════

{self._format_enhancer_stats()}

═══════════════════════════════════════════════════════════════════
                     PERFORMANCE TRAJECTORY
═══════════════════════════════════════════════════════════════════

{self._format_performance_trajectory()}

═══════════════════════════════════════════════════════════════════
                          INSIGHTS
═══════════════════════════════════════════════════════════════════

{self._generate_insights()}

╚══════════════════════════════════════════════════════════════════╝
"""

        with open(report_path, 'w') as f:
            f.write(report)

        print(report)
        logger.info(f"◈ Report generated: {report_path}")

    def _format_category_stats(self) -> str:
        """Format category statistics."""
        counts = self._count_by_category()
        lines = []
        for cat, data in sorted(counts.items()):
            rate = data['success'] / data['total'] * 100 if data['total'] > 0 else 0
            lines.append(f"  {cat:15} {data['success']:3}/{data['total']:3} ({rate:.0f}%)")
        return "\n".join(lines) if lines else "  No data"

    def _format_performance_trajectory(self) -> str:
        """Format performance trajectory over time."""
        if not self.session.performance_history:
            return "  No trajectory data"

        lines = []
        for snap in self.session.performance_history[::max(1, len(self.session.performance_history)//10)]:
            lines.append(f"  Batch {snap['batch']:3}: {snap['success_rate']*100:.0f}% success, "
                        f"{snap['total_strategies']} strategies")
        return "\n".join(lines)

    def _format_enhancer_stats(self) -> str:
        """Format training enhancer statistics."""
        try:
            stats = self.enhancer.get_all_stats()
            lines = []

            # Vision verification
            vision = stats.get('vision', {})
            lines.append("Vision Verification:")
            lines.append(f"  Model: {vision.get('vision_model', 'N/A')}")
            lines.append(f"  Verifications: {vision.get('verifications', 0)}")
            lines.append(f"  Pass rate: {vision.get('pass_rate', 0)*100:.1f}%")

            # Quality scoring
            quality = stats.get('quality', {})
            lines.append(f"\nQuality Scoring:")
            lines.append(f"  Tasks scored: {quality.get('total_scored', 0)}")
            lines.append(f"  Avg quality: {quality.get('avg_overall', 0):.3f}")

            # Curriculum
            curriculum = stats.get('curriculum', {})
            lines.append(f"\nCurriculum Learning:")
            lines.append(f"  Final level: {curriculum.get('current_level', 1)} ({curriculum.get('level_name', 'Basic')})")
            lines.append(f"  Level success rate: {curriculum.get('current_success_rate', 0)*100:.1f}%")

            # Active learning
            active = stats.get('active_learning', {})
            lines.append(f"\nActive Learning:")
            lines.append(f"  Failure modes tracked: {active.get('unique_failure_types', 0)}")
            lines.append(f"  Targeted tasks: {active.get('targeted_tasks_generated', 0)}")

            # LoRA training
            lora = stats.get('lora', {})
            lines.append(f"\nLoRA Training Data:")
            lines.append(f"  Examples collected: {lora.get('examples_collected', 0)}")
            lines.append(f"  Ready for training: {'Yes' if lora.get('ready_for_training', False) else 'No'}")

            return "\n".join(lines)

        except Exception as e:
            return f"  Could not load enhancer stats: {e}"

    def _generate_insights(self) -> str:
        """Generate actionable insights from training."""
        insights = []

        # Success rate trend
        if self.session.performance_history:
            first_rate = self.session.performance_history[0].get('success_rate', 0)
            last_rate = self.session.performance_history[-1].get('success_rate', 0)

            if last_rate > first_rate + 0.1:
                insights.append("✅ SUCCESS RATE IMPROVED during training - learning is working!")
            elif last_rate < first_rate - 0.1:
                insights.append("⚠️ Success rate decreased - may need easier tasks or more time")
            else:
                insights.append("➡️ Success rate stable - consider longer training")

        # Strategy growth
        if self.session.strategies_learned > 10:
            insights.append(f"✅ Learned {self.session.strategies_learned} new strategies - good diversity")
        elif self.session.strategies_learned < 3:
            insights.append("⚠️ Few new strategies learned - tasks may be too similar")

        # Category analysis
        counts = self._count_by_category()
        weak_categories = [cat for cat, data in counts.items()
                         if data['total'] >= 3 and data['success'] / data['total'] < 0.5]
        if weak_categories:
            insights.append(f"⚠️ Weak categories need practice: {', '.join(weak_categories)}")

        return "\n".join(insights) if insights else "  No specific insights"


async def quick_test():
    """Quick test of the training system."""
    engine = SelfPlayEngine()
    # Run just 5 minutes for testing
    await engine.run_training(duration_hours=5/60, batch_size=2)


if __name__ == "__main__":
    asyncio.run(quick_test())
