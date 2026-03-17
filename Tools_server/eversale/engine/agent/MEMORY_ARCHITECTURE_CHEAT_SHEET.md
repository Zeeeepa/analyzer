# Memory Architecture Quick Reference

## Setup

```python
from agent.memory_architecture import MemoryArchitecture

memory = MemoryArchitecture()
```

## Add Steps (During Task Execution)

```python
memory.add_step(
    action="Navigate to example.com",
    observation="Page loaded successfully",
    reasoning="User requested data",  # optional
    tool_calls=[{"name": "playwright_navigate", "args": {...}}],  # optional
    success=True,
    error=None  # optional
)
```

## Get Context for LLM

```python
# Simple context (recent steps detailed, older compressed)
context = memory.get_context(detailed_steps=10)

# Enriched context (includes relevant memories)
context = memory.get_enriched_context(
    query="current task description",
    detailed_steps=10,
    limit_per_type=3
)
```

## Save Episode (When Task Completes)

```python
episode = memory.save_episode(
    task_prompt="User's request",
    outcome="What happened",
    success=True,
    duration_seconds=45.3,
    tags=["category", "type"],  # optional
    importance=0.8  # 0.0-1.0, optional
)
```

## Search Memories

```python
# Search episodes
episodes = memory.search_episodes(
    query="extract contacts",
    limit=5,
    success_only=True  # optional
)

# Search semantic knowledge
knowledge = memory.search_semantic(
    query="how to handle login walls",
    limit=3
)

# Search skills
skills = memory.search_skills(
    query="extract data",
    limit=5
)

# Search all types
results = memory.search_all(
    query="extract LinkedIn data",
    limit_per_type=3
)
# Returns: {"episodic": [...], "semantic": [...], "skills": [...]}
```

## Skills

```python
# Save skill
memory.save_skill(
    skill_name="extract_fb_leads",
    description="Extract leads from Facebook Ads Library",
    action_sequence=[
        {"step": 1, "action": "navigate", "url": "..."},
        {"step": 2, "action": "extract", "selector": "..."}
    ],
    preconditions=["logged_in"],  # optional
    postconditions=["csv_saved"],  # optional
    tags=["facebook", "leads"]  # optional
)

# Get skill
skill = memory.get_skill("extract_fb_leads")

# Record execution
memory.record_skill_execution(
    skill_name="extract_fb_leads",
    success=True,
    duration=42.5
)
```

## Consolidation

```python
# Auto-consolidates every 5 minutes
# Or manually:
memory.consolidate_now()
```

## Statistics

```python
# Get stats dict
stats = memory.get_stats()

# Print pretty stats
memory.print_stats()
```

## Common Patterns

### Pattern 1: Basic Task Execution

```python
# Start task
memory.working.current_task_id = "task_123"

# Execute and record steps
for step in task_steps:
    result = execute_step(step)
    memory.add_step(step.action, result.observation, success=result.success)

# Save when done
memory.save_episode(
    task_prompt=user_request,
    outcome=final_result,
    success=task_succeeded,
    duration_seconds=execution_time
)
```

### Pattern 2: LLM with Context

```python
# Get enriched context
context = memory.get_enriched_context(
    query=user_prompt,
    detailed_steps=10
)

# Build prompt
system_prompt = f"""
You are Eversale AI agent.

{context}

User: {user_prompt}
"""

# Call LLM
response = llm.generate(system_prompt)
```

### Pattern 3: Learning from Past

```python
# Before planning new task, search for similar past tasks
past_tasks = memory.search_episodes(
    query=current_task_description,
    limit=3,
    success_only=True
)

# Use insights in planning
if past_tasks:
    print("Similar past tasks:")
    for task in past_tasks:
        print(f"- {task.task_prompt}: {task.outcome}")
```

### Pattern 4: Skill-Based Execution

```python
# Check if we have a skill for this
skills = memory.search_skills(user_request, limit=1)

if skills and skills[0].success_rate > 0.7:
    # Use proven skill
    skill = skills[0]
    execute_skill_sequence(skill.action_sequence)
else:
    # Execute manually and learn
    steps = execute_task_manually(user_request)

    # Save as new skill if successful
    if task_success:
        memory.save_skill(
            skill_name=f"skill_{task_type}",
            description=user_request,
            action_sequence=steps
        )
```

## Integration Snippets

### With brain_enhanced_v2.py

```python
class EnhancedBrain:
    def __init__(self):
        self.memory = MemoryArchitecture()

    async def run(self, prompt: str):
        context = self.memory.get_enriched_context(prompt)
        # Use context in LLM call...

        for step in execution:
            self.memory.add_step(step.action, step.result, success=step.success)

        self.memory.save_episode(prompt, outcome, success, duration)
```

### With reflexion.py

```python
def store_reflection(reflection):
    # Store as episodic memory
    memory.save_episode(
        task_prompt=reflection.task_prompt,
        outcome=reflection.what_happened,
        success=reflection.reflection_type != ReflectionType.FAILURE,
        duration_seconds=0.0,
        tags=["reflection", reflection.reflection_type.value]
    )
```

### With planning_agent.py

```python
def generate_plan(task: str):
    # Get relevant past experiences
    past = memory.search_episodes(task, limit=5, success_only=True)
    knowledge = memory.search_semantic(task, limit=3)
    skills = memory.search_skills(task, limit=5)

    # Use in planning prompt...
```

## Performance Targets

- **Token Reduction**: 90% (10:1 compression)
- **Latency Reduction**: 91% vs raw history
- **Retrieval Time**: <100ms
- **Retrieval Relevance**: 95%+

## Storage Locations

```
memory/
├── working_memory.json          # Current session
├── episodic_memory.db           # Past experiences
├── semantic_memory.db           # Patterns & knowledge
└── skill_memory.db              # Action sequences
```

## Key Concepts

**Working Memory** (40-50 steps)
- Current task context
- Full detail for recent steps
- Auto-compresses older steps

**Episodic Memory** (SQLite)
- Specific task executions
- "On date X, I did Y and got Z"
- Searchable by query, tags, success

**Semantic Memory** (SQLite)
- Generalized knowledge
- Patterns extracted from episodes
- "When doing X, use Y approach"

**Skill Memory** (SQLite)
- Reusable action sequences
- Statistics (success rate, avg duration)
- "To do X: steps [1,2,3]"

## Troubleshooting

**"Retrieval too slow"**
- Reduce search limit
- Use more specific queries
- Check database size (consolidate if >1000 episodes)

**"Results not relevant"**
- Use more specific queries
- Add tags when saving episodes
- Filter by success_only=True

**"High memory usage"**
- Run consolidation: `memory.consolidate_now()`
- Check stats: `memory.print_stats()`
- Reduce working_capacity if needed

**"Token reduction not meeting target"**
- Check compression settings
- Ensure steps have meaningful content
- May need more steps for compression to be effective
