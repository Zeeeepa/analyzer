# Memory Architecture Integration Guide

## Overview

The Mem0-style Memory Architecture provides advanced memory management for Eversale, implementing four-layer memory based on cognitive science and Mem0 research.

## Architecture Layers

```
┌──────────────────────────────────────────────────────────────┐
│                    WORKING MEMORY (40-50 steps)              │
│              Current task context in full detail             │
│                   Rolling buffer, recent focus               │
└──────────────────────┬───────────────────────────────────────┘
                       │ Compression & Save
                       ↓
┌──────────────────────────────────────────────────────────────┐
│                   EPISODIC MEMORY (SQLite)                   │
│           Specific task execution experiences                │
│          "On Dec 1st, I extracted 50 leads from FB"          │
└──────────────────────┬───────────────────────────────────────┘
                       │ Pattern Extraction
                       ↓
┌──────────────────────────────────────────────────────────────┐
│                   SEMANTIC MEMORY (SQLite)                   │
│              Generalized knowledge and patterns              │
│      "When extracting leads, use playwright_extract_*"       │
└──────────────────────┬───────────────────────────────────────┘
                       │ Action Sequences
                       ↓
┌──────────────────────────────────────────────────────────────┐
│                    SKILL MEMORY (SQLite)                     │
│              Executable action sequences                     │
│       "extract_fb_leads: [navigate, extract, save]"          │
└──────────────────────────────────────────────────────────────┘
```

## Performance Targets

- **91% latency reduction** vs raw history (Mem0 benchmark)
- **90% token reduction** through compression
- **95%+ retrieval relevance** via semantic search
- **<100ms retrieval time** for all queries

## Quick Start

### Basic Usage

```python
from agent.memory_architecture import MemoryArchitecture

# Create memory system
memory = MemoryArchitecture()

# Add steps during task execution
memory.add_step(
    action="Navigate to example.com",
    observation="Page loaded successfully",
    reasoning="User requested data from this site",
    tool_calls=[{"name": "playwright_navigate", "args": {"url": "example.com"}}],
    success=True
)

memory.add_step(
    action="Extract contacts",
    observation="Found 25 contacts",
    success=True
)

# Get context for LLM (compressed older steps, detailed recent steps)
context = memory.get_context(detailed_steps=10)
# Pass context to LLM...

# When task completes, save as episode
episode = memory.save_episode(
    task_prompt="Extract contacts from example.com",
    outcome="Successfully extracted 25 contacts",
    success=True,
    duration_seconds=12.5,
    tags=["extraction", "contacts"],
    importance=0.8  # High importance
)
```

### Advanced Usage

```python
# Search past experiences
past_experiences = memory.search_episodes(
    query="extract contacts from website",
    limit=5,
    success_only=True
)

# Search generalized knowledge
knowledge = memory.search_semantic(
    query="how to handle login walls",
    limit=3
)

# Search skills
skills = memory.search_skills(
    query="extract data from page",
    limit=5
)

# Get enriched context (includes relevant memories)
enriched = memory.get_enriched_context(
    query="extract leads from LinkedIn",
    detailed_steps=10,
    limit_per_type=3
)
# This includes working memory + relevant episodes + knowledge + skills

# Save a reusable skill
memory.save_skill(
    skill_name="extract_fb_leads",
    description="Extract leads from Facebook Ads Library",
    action_sequence=[
        {"action": "navigate", "url": "facebook.com/ads/library"},
        {"action": "search", "query": "{search_term}"},
        {"action": "extract_ads", "max_results": 50},
        {"action": "extract_contacts", "from": "advertiser_pages"}
    ],
    preconditions=["logged_in_facebook", "ads_library_accessible"],
    postconditions=["leads_extracted", "csv_saved"],
    tags=["facebook", "leads", "extraction"]
)

# Record skill execution (updates statistics)
memory.record_skill_execution(
    skill_name="extract_fb_leads",
    success=True,
    duration=45.3
)

# Get statistics
stats = memory.get_stats()
memory.print_stats()
```

## Integration with Existing Components

### 1. Integration with `brain_enhanced_v2.py`

Replace basic context with enriched memory context:

```python
# In brain_enhanced_v2.py
from agent.memory_architecture import MemoryArchitecture

class EnhancedBrain:
    def __init__(self):
        # Add memory architecture
        self.memory = MemoryArchitecture()
        # ... existing init code ...

    async def run(self, prompt: str):
        # Get enriched context instead of basic history
        context = self.memory.get_enriched_context(
            query=prompt,
            detailed_steps=10,
            limit_per_type=3
        )

        # Add to system prompt
        system_prompt = f"""
        You are Eversale, an AI agent.

        {context}

        User request: {prompt}
        """

        # Execute task...
        for step in task_execution:
            # Record each step
            self.memory.add_step(
                action=step.action,
                observation=step.result,
                reasoning=step.reasoning,
                tool_calls=step.tool_calls,
                success=step.success
            )

        # When done, save episode
        self.memory.save_episode(
            task_prompt=prompt,
            outcome=final_result,
            success=task_success,
            duration_seconds=execution_time
        )
```

### 2. Integration with `reflexion.py`

Link reflexion reflections to episodic memories:

```python
# In reflexion.py
from agent.memory_architecture import MemoryArchitecture

class ReflexionMemory:
    def __init__(self):
        self.memory_arch = MemoryArchitecture()
        # ... existing init ...

    def store_reflection(self, reflection: SelfReflection):
        # Store as episodic memory
        episode = self.memory_arch.save_episode(
            task_prompt=reflection.task_prompt,
            outcome=reflection.what_happened,
            success=reflection.reflection_type != ReflectionType.FAILURE,
            duration_seconds=0.0,  # Reflection doesn't have duration
            tags=["reflection", reflection.reflection_type.value],
            importance=reflection.confidence
        )

        # Link reflection to episode
        reflection.memory_id = episode.memory_id

        # ... existing store code ...

    def retrieve_relevant_reflections(self, task: str, limit: int = 3):
        # Use semantic search
        episodes = self.memory_arch.search_episodes(
            query=task,
            limit=limit,
            success_only=False  # Include failures for learning
        )

        # Convert back to reflections
        # ... conversion code ...
```

### 3. Integration with `planning_agent.py`

Use semantic memory to inform plan generation:

```python
# In planning_agent.py
from agent.memory_architecture import MemoryArchitecture

class PlanningAgent:
    def __init__(self):
        self.memory = MemoryArchitecture()
        # ... existing init ...

    def generate_plan(self, task: str) -> Plan:
        # Search for relevant past experiences
        past_experiences = self.memory.search_episodes(
            query=task,
            limit=5,
            success_only=True
        )

        # Search for relevant knowledge
        knowledge = self.memory.search_semantic(
            query=task,
            limit=3
        )

        # Search for relevant skills
        skills = self.memory.search_skills(
            query=task,
            limit=5
        )

        # Build prompt with context
        planning_prompt = f"""
        Task: {task}

        Relevant past experiences:
        {self._format_episodes(past_experiences)}

        Relevant knowledge:
        {self._format_semantic(knowledge)}

        Available skills:
        {self._format_skills(skills)}

        Generate a plan...
        """

        # Generate plan using LLM with context
        plan = self._generate_plan_with_llm(planning_prompt)

        return plan
```

### 4. Enhance `context_memory.py`

Replace basic context memory with full architecture:

```python
# context_memory_enhanced.py
from agent.memory_architecture import MemoryArchitecture

# Global instance
_memory = None

def get_memory() -> MemoryArchitecture:
    """Get global memory architecture instance."""
    global _memory
    if _memory is None:
        _memory = MemoryArchitecture()
    return _memory

def add_entry(entry: str):
    """Add entry to working memory."""
    memory = get_memory()
    # Parse entry and add as step
    # ... implementation ...

def summary(count: int = 3) -> str:
    """Get memory summary."""
    memory = get_memory()
    return memory.get_context(detailed_steps=count)

# Drop-in replacement for old ContextMemory
class ContextMemory:
    def __init__(self):
        self.memory = get_memory()

    def add_entry(self, entry: str):
        # Convert to step format
        self.memory.add_step(
            action=entry,
            observation="",
            success=True
        )

    def summary(self, count: int = 3) -> str:
        return self.memory.get_context(detailed_steps=count)
```

## Memory Consolidation

The system automatically consolidates memories every 5 minutes:

1. **Merge similar episodes** - Reduces redundancy
2. **Extract patterns** - Creates semantic memories
3. **Decay old memories** - Removes low-utility memories (TODO)

Manual consolidation:

```python
memory.consolidate_now()
```

## Memory Compression

Automatic compression with 10:1 target ratio:

```python
# Before compression (500 tokens):
"""
Step 1: Navigate to example.com -> Success
Step 2: Click login button -> Success
Step 3: Fill email field -> Success
Step 4: Fill password field -> Success
Step 5: Click submit -> Success
Step 6: Wait for dashboard -> Success
Step 7: Navigate to contacts -> Success
Step 8: Extract contacts -> Found 50 contacts
Step 9: Save to CSV -> Saved to contacts.csv
"""

# After compression (50 tokens):
"""
Successful actions: Navigate, login (filled email/password),
extract contacts (found 50), save to CSV.
"""
```

## Semantic Search

Uses vector embeddings for relevance:

```python
# Query: "how to handle login walls"
# Returns memories semantically related to authentication, login, credentials

results = memory.search_all(
    query="how to handle login walls",
    limit_per_type=3
)

# Results include:
# - Episodes about logging into sites
# - Semantic knowledge about authentication
# - Skills for login workflows
```

## Storage

All memories persisted in `/memory/` directory:

```
memory/
├── working_memory.json          # Current session (JSON)
├── episodic_memory.db           # Experiences (SQLite)
├── semantic_memory.db           # Knowledge (SQLite)
├── skill_memory.db              # Skills (SQLite)
├── reflexion/                   # Reflexion reflections
└── plans/                       # Planning agent plans
```

## Performance Monitoring

```python
# Get statistics
stats = memory.get_stats()
print(stats)

# Output:
{
    "working_memory": {
        "current_steps": 15,
        "capacity": 50,
        "session_id": "20251202_143022"
    },
    "episodic_memory": {
        "total_episodes": 127
    },
    "semantic_memory": {
        "total_patterns": 23
    },
    "skill_memory": {
        "total_skills": 8
    },
    "compression": {
        "token_reduction": "89.2%",
        "target": "90.0%"
    },
    "last_consolidation": "2025-12-02T14:25:30"
}

# Pretty print
memory.print_stats()

# Output:
=== Memory Architecture Statistics ===

Working Memory:
  Current steps: 15/50
  Session: 20251202_143022

Long-Term Memory:
  Episodes: 127
  Semantic patterns: 23
  Skills: 8

Compression:
  Token reduction: 89.2% (target: 90.0%)

Consolidation:
  Last run: 2025-12-02T14:25:30
```

## Best Practices

### 1. Record Every Action

```python
# Good - records every step
memory.add_step("Navigate to page", "Success")
memory.add_step("Click button", "Button clicked")
memory.add_step("Extract data", "Found 50 items")

# Bad - only records final result
# Missing intermediate steps loses context
```

### 2. Use Descriptive Action Names

```python
# Good
memory.add_step(
    action="Extract email addresses from .contact-info elements",
    observation="Found 25 email addresses"
)

# Bad - too vague
memory.add_step(
    action="Extract",
    observation="Found 25"
)
```

### 3. Set Importance Appropriately

```python
# High importance - critical task
memory.save_episode(..., importance=0.9)

# Medium importance - routine task
memory.save_episode(..., importance=0.5)

# Low importance - trivial task
memory.save_episode(..., importance=0.2)
```

### 4. Tag Episodes for Easy Retrieval

```python
memory.save_episode(
    ...,
    tags=["extraction", "facebook", "leads", "success"]
)

# Later: easy to find all Facebook extraction tasks
fb_episodes = memory.search_episodes("facebook extraction")
```

### 5. Use Enriched Context for Planning

```python
# Good - includes past experiences
context = memory.get_enriched_context(prompt)
plan = planner.plan(context)

# Bad - only current context
context = memory.get_context()
plan = planner.plan(context)
```

### 6. Save Reusable Skills

```python
# If a sequence works well, save it as a skill
if task_success and complexity > 5:
    memory.save_skill(
        skill_name=f"workflow_{task_type}",
        description=task_description,
        action_sequence=steps_taken
    )
```

## Troubleshooting

### High Memory Usage

```python
# Check stats
stats = memory.get_stats()
print(f"Episodes: {stats['episodic_memory']['total_episodes']}")

# If too many episodes, consolidate
memory.consolidate_now()

# Or manually prune (future feature)
# memory.prune_old_memories(older_than_days=30)
```

### Slow Retrieval

```python
# Check retrieval time
import time
start = time.time()
results = memory.search_episodes("query")
duration = time.time() - start
print(f"Retrieval took {duration*1000:.1f}ms")

# Target: <100ms
# If slower:
# 1. Check database indexes (should be automatic)
# 2. Reduce search limit
# 3. Use more specific queries
```

### Low Relevance in Results

```python
# If results not relevant:
# 1. Use more specific queries
results = memory.search_episodes("extract Facebook Ads Library leads")
# vs generic "extract"

# 2. Use tags
results = memory.search_episodes(
    query="extract leads",
    tags=["facebook", "ads"]
)

# 3. Filter by success
results = memory.search_episodes(
    query="extract leads",
    success_only=True
)
```

## API Reference

### MemoryArchitecture

Main class for memory management.

**Constructor:**
```python
memory = MemoryArchitecture(
    working_capacity=50,      # Working memory capacity
    auto_consolidate=True     # Auto-consolidate every 5 min
)
```

**Working Memory Methods:**
- `add_step(action, observation, reasoning, tool_calls, success, error)` - Add step
- `get_context(detailed_steps)` - Get context for LLM
- `get_recent_steps(n)` - Get N recent steps

**Episodic Memory Methods:**
- `save_episode(task_prompt, outcome, success, duration_seconds, task_id, tags, importance)` - Save episode
- `search_episodes(query, limit, success_only)` - Search episodes

**Semantic Memory Methods:**
- `search_semantic(query, limit)` - Search knowledge
- `extract_patterns(min_episodes)` - Extract patterns

**Skill Memory Methods:**
- `save_skill(skill_name, description, action_sequence, preconditions, postconditions, tags)` - Save skill
- `search_skills(query, limit)` - Search skills
- `get_skill(skill_name)` - Get specific skill
- `record_skill_execution(skill_name, success, duration)` - Update stats

**Unified Methods:**
- `search_all(query, limit_per_type)` - Search all types
- `get_enriched_context(query, detailed_steps, limit_per_type)` - Get enriched context
- `consolidate_now()` - Run consolidation
- `get_stats()` - Get statistics
- `print_stats()` - Print statistics

## Examples

### Example 1: SDR Workflow

```python
from agent.memory_architecture import MemoryArchitecture

memory = MemoryArchitecture()

# Task: Find leads from Facebook Ads
memory.working.current_task_id = "sdr_fb_leads_001"

# Step 1: Navigate
memory.add_step(
    action="Navigate to Facebook Ads Library",
    observation="Loaded ads library page",
    tool_calls=[{"name": "playwright_navigate", "args": {"url": "facebook.com/ads/library"}}],
    success=True
)

# Step 2: Search
memory.add_step(
    action="Search for 'CRM software' ads",
    observation="Found 45 advertisers",
    tool_calls=[{"name": "playwright_fill", "args": {"selector": "input[name=q]", "value": "CRM software"}}],
    success=True
)

# Step 3: Extract
memory.add_step(
    action="Extract advertiser details",
    observation="Extracted 45 advertiser names and pages",
    tool_calls=[{"name": "playwright_extract_fb_ads"}],
    success=True
)

# Step 4: Visit websites
memory.add_step(
    action="Visit advertiser websites and extract contacts",
    observation="Extracted 32 emails, 18 phone numbers",
    tool_calls=[{"name": "playwright_batch_extract", "args": {"urls": ["..."]}}],
    success=True
)

# Step 5: Save
memory.add_step(
    action="Save leads to CSV",
    observation="Saved 45 leads to leads_fb_crm.csv",
    success=True
)

# Save episode
episode = memory.save_episode(
    task_prompt="Find leads from Facebook Ads Library for 'CRM software'",
    outcome="Successfully extracted 45 leads (32 emails, 18 phones)",
    success=True,
    duration_seconds=87.3,
    tags=["sdr", "facebook", "leads", "crm"],
    importance=0.8
)

print(f"Episode saved: {episode.memory_id}")
print(f"Compression: {episode.original_tokens} -> {episode.compressed_tokens} tokens")
```

### Example 2: Learning from Failures

```python
# Failed task
memory.add_step(
    action="Login to LinkedIn",
    observation="Login wall detected",
    success=False,
    error="Anti-bot detection triggered"
)

memory.add_step(
    action="Retry with stealth mode",
    observation="Still blocked",
    success=False,
    error="Captcha appeared"
)

# Save as failed episode
episode = memory.save_episode(
    task_prompt="Extract contacts from LinkedIn",
    outcome="Failed due to anti-bot detection",
    success=False,
    duration_seconds=15.2,
    tags=["linkedin", "extraction", "failed", "anti-bot"],
    importance=0.9  # High importance - need to learn from this
)

# Later, when planning similar task:
context = memory.get_enriched_context(
    query="extract contacts from LinkedIn",
    detailed_steps=5
)

# Context will include the failed episode:
# "Past experience: LinkedIn extraction failed due to anti-bot.
#  Consider: Use logged-in session, avoid rapid requests"
```

### Example 3: Skill Reuse

```python
# First execution - manual steps
# ... execute task ...

# Save as skill
memory.save_skill(
    skill_name="extract_reddit_warm_signals",
    description="Extract Reddit posts with buying intent signals",
    action_sequence=[
        {
            "action": "navigate",
            "tool": "playwright_navigate",
            "args": {"url": "reddit.com/r/{subreddit}"}
        },
        {
            "action": "extract_posts",
            "tool": "playwright_extract_reddit",
            "args": {"filter": "warm_signals"}
        },
        {
            "action": "analyze_sentiment",
            "tool": "llm_analyze",
            "args": {"text": "{posts}", "task": "identify buying intent"}
        },
        {
            "action": "save_results",
            "tool": "save_csv",
            "args": {"filename": "reddit_leads_{date}.csv"}
        }
    ],
    preconditions=["reddit_accessible", "target_subreddit_known"],
    postconditions=["leads_extracted", "csv_saved"],
    tags=["reddit", "leads", "sentiment", "extraction"]
)

# Later, reuse skill
skill = memory.get_skill("extract_reddit_warm_signals")
if skill:
    print(f"Skill: {skill.description}")
    print(f"Success rate: {skill.success_rate:.1%}")
    print(f"Steps: {len(skill.action_sequence)}")

    # Execute skill steps...
    start_time = time.time()
    success = execute_skill_sequence(skill.action_sequence)
    duration = time.time() - start_time

    # Record execution
    memory.record_skill_execution(
        skill_name="extract_reddit_warm_signals",
        success=success,
        duration=duration
    )
```

## Future Enhancements

- [ ] Memory decay/pruning based on utility
- [ ] Cross-session learning (share memories between instances)
- [ ] Memory versioning and rollback
- [ ] Advanced pattern mining (clustering, association rules)
- [ ] Integration with external knowledge bases
- [ ] Memory visualization dashboard
- [ ] A/B testing of memory strategies
- [ ] Federated learning across Eversale instances

## References

- Mem0: The Memory Layer for AI Applications (2024)
- LangGraph Memory Architecture
- Reflexion: Language Agents with Verbal Reinforcement Learning (Shinn et al., 2023)
- Human Memory Systems (Cognitive Science Research)
- Production Agent Memory Patterns (Anthropic, OpenAI, Google DeepMind)
