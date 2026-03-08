"""
Long-Running Agent Resilience Module

Implements bulletproof techniques for 10,000+ step runs based on research from:
- LangGraph checkpointing (https://docs.langchain.com/oss/python/langgraph/persistence)
- Context-Bench memory management (Letta)
- tau-Bench reliability patterns (Sierra)
- AutoGen fault tolerance (Microsoft)
- Google ADK context compaction

Key Features:
1. Sliding Window Context Management - Prevents context overflow
2. Hierarchical Memory with Summarization - Older context gets compressed
3. Disk-Based Checkpointing - Crash recovery at any point
4. Infinite Loop Detection with Early Stop - Prevents spiraling
5. Graceful Degradation - Partial results saved on failure
6. Memory Decay - Removes stale/irrelevant context
"""

import json
import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from loguru import logger


# ============================================================================
# CONTEXT WINDOW MANAGEMENT
# ============================================================================

@dataclass
class ContextWindow:
    """
    Sliding window context management to prevent overflow.

    Based on research:
    - Keep last N messages verbatim (short-term)
    - Summarize older messages into compressed form (medium-term)
    - Store essential facts only for oldest context (long-term)
    """

    # Configuration
    max_messages: int = 50          # Max messages before compression
    verbatim_window: int = 20       # Keep last N messages verbatim
    summary_window: int = 20        # Keep N summarized chunks
    max_tokens_estimate: int = 8000 # Rough token limit

    # State
    messages: List[Dict] = field(default_factory=list)
    summaries: List[str] = field(default_factory=list)
    essential_facts: List[str] = field(default_factory=list)
    total_messages_processed: int = 0
    compression_count: int = 0

    def add_message(self, role: str, content: str, name: str = None) -> Dict:
        """Add a message, triggering compression if needed."""
        msg = {
            'role': role,
            'content': content[:3000],  # Hard limit per message
            'timestamp': datetime.now().isoformat()
        }
        if name:
            msg['name'] = name

        self.messages.append(msg)
        self.total_messages_processed += 1

        # Check if we need to compress
        if len(self.messages) >= self.max_messages:
            self._compress_context()

        return msg

    def _compress_context(self):
        """Compress older messages into summaries."""
        if len(self.messages) <= self.verbatim_window:
            return

        # Messages to summarize (oldest beyond verbatim window)
        to_summarize = self.messages[:-self.verbatim_window]
        to_keep = self.messages[-self.verbatim_window:]

        # Create summary of old messages
        summary_parts = []
        tool_results = []
        for msg in to_summarize:
            role = msg.get('role', '')
            content = msg.get('content', '')[:200]
            name = msg.get('name', '')

            if role == 'tool':
                # Extract key info from tool results
                tool_results.append(f"{name}: {content[:100]}")
            elif role == 'assistant':
                # Keep assistant decisions
                summary_parts.append(f"Action: {content[:150]}")

        # Create compressed summary
        if tool_results:
            summary = f"[Iteration {self.compression_count + 1}] Tools: {'; '.join(tool_results[:5])}"
            if summary_parts:
                summary += f" | Decisions: {'; '.join(summary_parts[:3])}"
        else:
            summary = f"[Iteration {self.compression_count + 1}] {'; '.join(summary_parts[:5])}"

        self.summaries.append(summary[:500])

        # Keep only last N summaries
        if len(self.summaries) > self.summary_window:
            # Convert oldest summaries to essential facts
            old_summaries = self.summaries[:-self.summary_window]
            for s in old_summaries:
                # Extract any data patterns (URLs, counts, errors)
                if 'error' in s.lower():
                    self.essential_facts.append(f"Error encountered: {s[:100]}")
                elif any(x in s.lower() for x in ['found', 'extracted', 'saved']):
                    self.essential_facts.append(f"Progress: {s[:100]}")

            self.summaries = self.summaries[-self.summary_window:]

        # Keep essential facts bounded
        self.essential_facts = self.essential_facts[-20:]

        # Replace messages with compressed version
        self.messages = to_keep
        self.compression_count += 1

        logger.debug(f"[CONTEXT COMPRESS] Iteration {self.compression_count}: "
                    f"{len(to_summarize)} msgs -> summary, kept {len(to_keep)} verbatim")

    def get_context_for_llm(self) -> List[Dict]:
        """Get optimized context for LLM call."""
        context = []

        # Add essential facts as system context
        if self.essential_facts:
            facts_text = "PRIOR PROGRESS:\n" + "\n".join(f"- {f}" for f in self.essential_facts[-10:])
            context.append({'role': 'system', 'content': facts_text})

        # Add compressed summaries
        if self.summaries:
            summaries_text = "RECENT HISTORY:\n" + "\n".join(self.summaries[-5:])
            context.append({'role': 'system', 'content': summaries_text})

        # Add verbatim messages
        context.extend(self.messages)

        return context

    def estimate_tokens(self) -> int:
        """Rough token estimate (4 chars ~ 1 token)."""
        total_chars = sum(len(m.get('content', '')) for m in self.messages)
        total_chars += sum(len(s) for s in self.summaries)
        total_chars += sum(len(f) for f in self.essential_facts)
        return total_chars // 4


# ============================================================================
# INFINITE LOOP DETECTION & EARLY STOP
# ============================================================================

@dataclass
class LoopDetector:
    """
    Detects infinite loops and triggers early stop.

    Based on research from tau-Bench and AutoGen:
    - Track action patterns
    - Detect repeated failures
    - Implement "pass^k" metric for reliability
    - Early stop before resource exhaustion
    """

    # Configuration
    max_identical_actions: int = 3      # Same action repeated
    max_failures_consecutive: int = 5   # Consecutive failures
    max_total_failures: int = 20        # Total failures before stop
    max_iterations: int = 10000         # Hard limit
    loop_pattern_window: int = 10       # Check last N for patterns

    # State
    action_history: List[str] = field(default_factory=list)
    failure_history: List[Dict] = field(default_factory=list)
    consecutive_failures: int = 0
    total_failures: int = 0
    total_iterations: int = 0
    early_stop_reason: str = ""

    def record_action(self, action: str, args: Dict, success: bool, error: str = None):
        """Record an action and check for loops."""
        # Create action signature
        sig = f"{action}:{json.dumps(args, sort_keys=True, default=str)[:100]}"
        self.action_history.append(sig)
        self.total_iterations += 1

        # Track failures
        if not success:
            self.consecutive_failures += 1
            self.total_failures += 1
            self.failure_history.append({
                'action': action,
                'error': error[:200] if error else '',
                'iteration': self.total_iterations,
                'timestamp': datetime.now().isoformat()
            })
        else:
            self.consecutive_failures = 0

        # Keep histories bounded
        self.action_history = self.action_history[-100:]
        self.failure_history = self.failure_history[-50:]

    def should_early_stop(self) -> Tuple[bool, str]:
        """Check if we should stop early."""

        # Check max iterations
        if self.total_iterations >= self.max_iterations:
            return True, f"Max iterations reached ({self.max_iterations})"

        # Check consecutive failures
        if self.consecutive_failures >= self.max_failures_consecutive:
            return True, f"Too many consecutive failures ({self.consecutive_failures})"

        # Check total failures
        if self.total_failures >= self.max_total_failures:
            return True, f"Too many total failures ({self.total_failures})"

        # Check for repeated identical actions
        if len(self.action_history) >= self.max_identical_actions:
            recent = self.action_history[-self.max_identical_actions:]
            if len(set(recent)) == 1:
                return True, f"Identical action repeated {self.max_identical_actions} times"

        # Check for loop patterns (A->B->A->B->A->B)
        if len(self.action_history) >= self.loop_pattern_window:
            recent = self.action_history[-self.loop_pattern_window:]
            # Check for 2-step, 3-step, 4-step patterns
            for pattern_len in [2, 3, 4]:
                if self._detect_pattern(recent, pattern_len):
                    return True, f"Loop pattern detected (length {pattern_len})"

        return False, ""

    def _detect_pattern(self, actions: List[str], pattern_len: int) -> bool:
        """Detect repeating patterns of given length."""
        if len(actions) < pattern_len * 3:  # Need at least 3 repetitions
            return False

        # Get potential pattern
        pattern = actions[-pattern_len:]

        # Check if it repeats in previous actions
        repeats = 0
        for i in range(len(actions) - pattern_len, -1, -pattern_len):
            chunk = actions[i:i + pattern_len]
            if chunk == pattern:
                repeats += 1
            else:
                break

        return repeats >= 2  # Pattern repeated at least twice before current

    def get_health_report(self) -> Dict:
        """Get current health status."""
        should_stop, reason = self.should_early_stop()
        return {
            'total_iterations': self.total_iterations,
            'total_failures': self.total_failures,
            'consecutive_failures': self.consecutive_failures,
            'should_stop': should_stop,
            'stop_reason': reason,
            'recent_actions': self.action_history[-5:],
            'recent_failures': self.failure_history[-3:]
        }


# ============================================================================
# DISK-BASED CHECKPOINT PERSISTENCE
# ============================================================================

@dataclass
class CheckpointManager:
    """
    Disk-based checkpointing for crash recovery.

    Based on LangGraph checkpointer pattern:
    - Save state at each superstep
    - Resume from last successful checkpoint
    - Support time travel (replay from any point)
    """

    checkpoint_dir: Path = field(default_factory=lambda: Path.home() / '.eversale' / 'checkpoints')
    task_id: str = ""
    max_checkpoints: int = 20

    # Current state
    current_checkpoint: int = 0
    checkpoints: List[Dict] = field(default_factory=list)

    def __post_init__(self):
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        if self.task_id:
            self._load_checkpoints()

    def _get_checkpoint_path(self, checkpoint_num: int) -> Path:
        return self.checkpoint_dir / f"{self.task_id}_cp{checkpoint_num:05d}.json"

    def _get_index_path(self) -> Path:
        return self.checkpoint_dir / f"{self.task_id}_index.json"

    def _load_checkpoints(self):
        """Load checkpoint index."""
        index_path = self._get_index_path()
        if index_path.exists():
            try:
                data = json.loads(index_path.read_text())
                self.checkpoints = data.get('checkpoints', [])
                self.current_checkpoint = data.get('current', 0)
            except Exception as e:
                logger.warning(f"Failed to load checkpoint index: {e}")

    def _save_index(self):
        """Save checkpoint index."""
        index_path = self._get_index_path()
        try:
            index_path.write_text(json.dumps({
                'task_id': self.task_id,
                'current': self.current_checkpoint,
                'checkpoints': self.checkpoints[-self.max_checkpoints:],
                'updated': datetime.now().isoformat()
            }, indent=2))
        except Exception as e:
            logger.warning(f"Failed to save checkpoint index: {e}")

    def save_checkpoint(
        self,
        iteration: int,
        messages: List[Dict],
        results: List[Any],
        state: Dict,
        metadata: Dict = None
    ) -> str:
        """Save a checkpoint to disk."""
        self.current_checkpoint += 1

        checkpoint_data = {
            'checkpoint_num': self.current_checkpoint,
            'task_id': self.task_id,
            'iteration': iteration,
            'timestamp': datetime.now().isoformat(),
            'messages_count': len(messages),
            'messages': messages[-30:],  # Keep last 30 messages
            'results_count': len(results),
            'results_sample': results[-10:] if results else [],
            'state': state,
            'metadata': metadata or {}
        }

        # Save to disk
        cp_path = self._get_checkpoint_path(self.current_checkpoint)
        try:
            cp_path.write_text(json.dumps(checkpoint_data, default=str, indent=2))

            # Update index
            self.checkpoints.append({
                'num': self.current_checkpoint,
                'iteration': iteration,
                'path': str(cp_path),
                'timestamp': checkpoint_data['timestamp']
            })

            # Cleanup old checkpoints
            if len(self.checkpoints) > self.max_checkpoints:
                old_checkpoints = self.checkpoints[:-self.max_checkpoints]
                for old in old_checkpoints:
                    try:
                        Path(old['path']).unlink(missing_ok=True)
                    except:
                        pass
                self.checkpoints = self.checkpoints[-self.max_checkpoints:]

            self._save_index()

            logger.info(f"[CHECKPOINT] Saved #{self.current_checkpoint} at iteration {iteration}")
            return str(cp_path)

        except Exception as e:
            logger.error(f"[CHECKPOINT] Failed to save: {e}")
            return ""

    def load_latest_checkpoint(self) -> Optional[Dict]:
        """Load the most recent checkpoint."""
        if not self.checkpoints:
            return None

        latest = self.checkpoints[-1]
        cp_path = Path(latest['path'])

        if not cp_path.exists():
            return None

        try:
            return json.loads(cp_path.read_text())
        except Exception as e:
            logger.error(f"[CHECKPOINT] Failed to load: {e}")
            return None

    def load_checkpoint(self, checkpoint_num: int) -> Optional[Dict]:
        """Load a specific checkpoint (for time travel)."""
        cp_path = self._get_checkpoint_path(checkpoint_num)
        if not cp_path.exists():
            return None

        try:
            return json.loads(cp_path.read_text())
        except Exception as e:
            logger.error(f"[CHECKPOINT] Failed to load #{checkpoint_num}: {e}")
            return None

    @classmethod
    def get_task_id(cls, prompt: str) -> str:
        """Generate consistent task ID from prompt."""
        return hashlib.md5(prompt[:200].encode()).hexdigest()[:12]


# ============================================================================
# GRACEFUL DEGRADATION & PARTIAL RESULTS
# ============================================================================

@dataclass
class GracefulDegradation:
    """
    Handles failures gracefully, preserving partial results.

    Features:
    - Save partial results on failure
    - Generate summary even if incomplete
    - Provide recovery instructions
    """

    output_dir: Path = field(default_factory=lambda: Path.home() / 'Desktop' / 'AI_Agent_Output')
    task_id: str = ""

    # Collected results
    partial_results: List[Dict] = field(default_factory=list)
    errors: List[Dict] = field(default_factory=list)
    progress_log: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def record_progress(self, step: str, data: Any = None):
        """Record progress for potential recovery."""
        entry = f"[{datetime.now().strftime('%H:%M:%S')}] {step}"
        if data:
            entry += f" - {str(data)[:100]}"
        self.progress_log.append(entry)

    def record_partial_result(self, result: Dict):
        """Store a partial result."""
        result['_recorded_at'] = datetime.now().isoformat()
        self.partial_results.append(result)

    def record_error(self, error: str, context: Dict = None):
        """Record an error with context."""
        self.errors.append({
            'error': error[:500],
            'context': context or {},
            'timestamp': datetime.now().isoformat()
        })

    def save_partial_results(self, reason: str = "task_incomplete") -> str:
        """Save whatever results we have on failure."""
        if not self.partial_results and not self.progress_log:
            return ""

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"partial_{self.task_id}_{timestamp}.json"
        filepath = self.output_dir / filename

        try:
            data = {
                'task_id': self.task_id,
                'status': 'partial',
                'reason': reason,
                'timestamp': datetime.now().isoformat(),
                'results_count': len(self.partial_results),
                'results': self.partial_results,
                'errors_count': len(self.errors),
                'errors': self.errors[-10:],
                'progress_log': self.progress_log[-50:],
                'recovery_hint': self._generate_recovery_hint()
            }

            filepath.write_text(json.dumps(data, default=str, indent=2))
            logger.info(f"[GRACEFUL] Saved partial results to {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"[GRACEFUL] Failed to save partial results: {e}")
            return ""

    def _generate_recovery_hint(self) -> str:
        """Generate hint for resuming the task."""
        if not self.progress_log:
            return "No progress recorded. Start from beginning."

        last_step = self.progress_log[-1]
        results_count = len(self.partial_results)

        hint = f"Last completed step: {last_step}\n"
        hint += f"Partial results collected: {results_count}\n"

        if self.errors:
            last_error = self.errors[-1].get('error', '')
            hint += f"Last error: {last_error[:100]}\n"

        return hint

    def generate_emergency_summary(self) -> str:
        """Generate a summary even if task is incomplete."""
        lines = ["**PARTIAL RESULTS (Task Incomplete)**\n"]

        if self.partial_results:
            lines.append(f"Collected {len(self.partial_results)} results before failure:")
            for r in self.partial_results[:5]:
                lines.append(f"  - {str(r)[:100]}")
            if len(self.partial_results) > 5:
                lines.append(f"  ... and {len(self.partial_results) - 5} more")

        if self.errors:
            lines.append(f"\nEncountered {len(self.errors)} errors:")
            for e in self.errors[-3:]:
                lines.append(f"  - {e.get('error', '')[:80]}")

        if self.progress_log:
            lines.append(f"\nProgress log (last 5 steps):")
            for p in self.progress_log[-5:]:
                lines.append(f"  {p}")

        return "\n".join(lines)


# ============================================================================
# MEMORY DECAY (Relevance-Based Forgetting)
# ============================================================================

@dataclass
class MemoryDecay:
    """
    Implements memory decay to prevent bloat.

    Based on Redis TTL patterns and research on relevance-based forgetting:
    - Recent memories have high weight
    - Older memories decay over time
    - Irrelevant memories are removed
    """

    decay_rate: float = 0.9  # Weight multiplier per hour
    min_weight: float = 0.1  # Minimum weight before removal
    max_entries: int = 100

    memories: List[Dict] = field(default_factory=list)

    def add_memory(self, content: str, importance: float = 1.0, tags: List[str] = None):
        """Add a memory with initial importance weight."""
        self.memories.append({
            'content': content[:500],
            'weight': importance,
            'tags': tags or [],
            'created': datetime.now(),
            'last_accessed': datetime.now()
        })

        # Trigger decay and cleanup
        self._decay_and_cleanup()

    def _decay_and_cleanup(self):
        """Apply decay and remove low-weight memories."""
        now = datetime.now()

        for mem in self.memories:
            # Calculate time since last access
            last_accessed = mem.get('last_accessed', mem.get('created', now))
            if isinstance(last_accessed, str):
                last_accessed = datetime.fromisoformat(last_accessed)

            hours_elapsed = (now - last_accessed).total_seconds() / 3600

            # Apply exponential decay
            mem['weight'] *= (self.decay_rate ** hours_elapsed)
            mem['last_accessed'] = now

        # Remove low-weight memories
        self.memories = [m for m in self.memories if m['weight'] >= self.min_weight]

        # Keep only max entries (by weight)
        if len(self.memories) > self.max_entries:
            self.memories.sort(key=lambda x: x['weight'], reverse=True)
            self.memories = self.memories[:self.max_entries]

    def recall(self, query: str, limit: int = 5) -> List[str]:
        """Recall relevant memories, boosting their weight."""
        query_lower = query.lower()

        # Score memories by relevance
        scored = []
        for mem in self.memories:
            content = mem.get('content', '').lower()
            tags = [t.lower() for t in mem.get('tags', [])]

            # Simple relevance scoring
            score = mem.get('weight', 1.0)

            # Boost if query terms appear
            for word in query_lower.split():
                if word in content:
                    score *= 1.5
                if word in tags:
                    score *= 2.0

            scored.append((mem, score))

        # Sort by score and return top results
        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for mem, score in scored[:limit]:
            # Boost weight of recalled memories
            mem['weight'] = min(1.0, mem['weight'] * 1.2)
            mem['last_accessed'] = datetime.now()
            results.append(mem['content'])

        return results


# ============================================================================
# COMBINED RESILIENCE MANAGER
# ============================================================================

class ResilienceManager:
    """
    Combined manager for all long-running resilience features.

    Usage:
        resilience = ResilienceManager(task_id="my_task")

        for iteration in range(10000):
            # Check if we should stop
            should_stop, reason = resilience.should_stop()
            if should_stop:
                break

            # Record action
            resilience.record_action("tool_name", {"arg": "val"}, success=True)

            # Add message to context
            resilience.add_message("assistant", "I will do X")

            # Checkpoint periodically
            if iteration % 10 == 0:
                resilience.checkpoint(iteration, results)

        # Get final summary
        summary = resilience.get_summary()
    """

    def __init__(
        self,
        task_id: str = None,
        prompt: str = "",
        max_iterations: int = 10000,
        checkpoint_interval: int = 10
    ):
        # Generate task ID if not provided
        self.task_id = task_id or CheckpointManager.get_task_id(prompt)
        self.prompt = prompt
        self.checkpoint_interval = checkpoint_interval

        # Initialize components
        self.context = ContextWindow()
        self.loop_detector = LoopDetector(max_iterations=max_iterations)
        self.checkpointer = CheckpointManager(task_id=self.task_id)
        self.degradation = GracefulDegradation(task_id=self.task_id)
        self.memory = MemoryDecay()

        # Start time
        self.start_time = datetime.now()

        logger.info(f"[RESILIENCE] Initialized for task {self.task_id}")

    def record_action(self, action: str, args: Dict, success: bool, error: str = None, result: Any = None):
        """Record an action and update all tracking."""
        # Update loop detector
        self.loop_detector.record_action(action, args, success, error)

        # Update degradation tracker
        if success and result:
            self.degradation.record_partial_result({'action': action, 'result': result})
        elif error:
            self.degradation.record_error(error, {'action': action, 'args': args})

        self.degradation.record_progress(f"{action} -> {'OK' if success else 'FAIL'}")

        # Add to memory
        importance = 1.0 if success else 0.5
        self.memory.add_memory(
            f"{action}: {str(result)[:100] if result else error[:100] if error else 'no result'}",
            importance=importance,
            tags=[action, 'success' if success else 'failure']
        )

    def add_message(self, role: str, content: str, name: str = None):
        """Add a message to context window."""
        return self.context.add_message(role, content, name)

    def get_context(self) -> List[Dict]:
        """Get optimized context for LLM."""
        return self.context.get_context_for_llm()

    def should_stop(self) -> Tuple[bool, str]:
        """Check if we should stop (combines all checks)."""
        return self.loop_detector.should_early_stop()

    def checkpoint(self, iteration: int, results: List[Any], state: Dict = None) -> str:
        """Save a checkpoint."""
        return self.checkpointer.save_checkpoint(
            iteration=iteration,
            messages=self.context.messages,
            results=results,
            state=state or {},
            metadata={
                'loop_health': self.loop_detector.get_health_report(),
                'context_stats': {
                    'messages': len(self.context.messages),
                    'summaries': len(self.context.summaries),
                    'compressions': self.context.compression_count
                }
            }
        )

    def should_checkpoint(self, iteration: int) -> bool:
        """Check if we should save a checkpoint at this iteration."""
        return iteration > 0 and iteration % self.checkpoint_interval == 0

    def resume_from_checkpoint(self) -> Optional[Dict]:
        """Resume from last checkpoint."""
        checkpoint = self.checkpointer.load_latest_checkpoint()
        if checkpoint:
            # Restore context
            self.context.messages = checkpoint.get('messages', [])
            self.loop_detector.total_iterations = checkpoint.get('iteration', 0)
            logger.info(f"[RESILIENCE] Resumed from checkpoint at iteration {checkpoint.get('iteration', 0)}")
        return checkpoint

    def save_on_failure(self, reason: str = "task_failed") -> str:
        """Save partial results on failure."""
        return self.degradation.save_partial_results(reason)

    def get_summary(self) -> str:
        """Get final summary."""
        elapsed = (datetime.now() - self.start_time).total_seconds()

        health = self.loop_detector.get_health_report()

        lines = [
            "**TASK EXECUTION SUMMARY**",
            f"- Task ID: {self.task_id}",
            f"- Duration: {elapsed:.1f}s",
            f"- Total iterations: {health['total_iterations']}",
            f"- Total failures: {health['total_failures']}",
            f"- Context compressions: {self.context.compression_count}",
            f"- Checkpoints saved: {len(self.checkpointer.checkpoints)}",
            f"- Partial results: {len(self.degradation.partial_results)}",
        ]

        if health['should_stop']:
            lines.append(f"- Early stop: {health['stop_reason']}")

        return "\n".join(lines)

    def recall_relevant(self, query: str, limit: int = 5) -> List[str]:
        """Recall relevant memories for the query."""
        return self.memory.recall(query, limit)


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================

def create_resilient_runner(prompt: str, max_iterations: int = 10000) -> ResilienceManager:
    """Create a resilience manager for a long-running task."""
    return ResilienceManager(
        prompt=prompt,
        max_iterations=max_iterations,
        checkpoint_interval=max(10, max_iterations // 100)  # ~100 checkpoints
    )
