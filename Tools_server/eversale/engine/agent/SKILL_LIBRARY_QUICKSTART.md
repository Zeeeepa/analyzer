# Skill Library Quick Start

Get up and running with the Voyager-style skill library in 5 minutes.

## Installation

The skill library is already included in Eversale. Just ensure ChromaDB is installed:

```bash
pip install chromadb
```

## Basic Usage

### 1. Get the Library

```python
from agent.skill_library import get_skill_library

library = get_skill_library()
```

That's it! The library initializes with pre-built skills automatically.

### 2. Search for Skills

```python
# Find skills using natural language
skills = library.search_skills(
    query="login to a website",
    limit=5
)

for skill in skills:
    print(f"- {skill.name}: {skill.description}")
```

### 3. Use a Skill

```python
# Get a specific skill
login_skill = library.get_skill("nav_login_generic")

# Prepare context
context = {
    "login_url": "https://example.com/login",
    "username": "user@example.com",
    "password": "mypassword"
}

# Execute
result = await login_skill.execute(context)
```

### 4. Learn New Skills

```python
# After successfully executing a task, record the actions
actions = [
    {"tool": "playwright_navigate", "arguments": {"url": "https://example.com"}},
    {"tool": "playwright_fill", "arguments": {"selector": "#search", "value": "query"}},
    {"tool": "playwright_click", "arguments": {"selector": "button"}},
]

# Learn from it
learned = library.learn_skill_from_execution(
    task_description="Search on example.com",
    actions=actions,
    result={"found": 10},
    category=SkillCategory.INTERACTION
)

print(f"Learned: {learned.name}")
```

### 5. Track Performance

```python
# Record when you use a skill
library.record_skill_usage(
    skill_id=skill.skill_id,
    success=True,
    execution_time=2.5
)

# Check metrics later
print(f"Success rate: {skill.metrics.success_rate:.1%}")
```

## Integration with Your Agent

### Step 1: Make Your Agent Skill-Aware

```python
from agent.skill_integration import SkillAwareAgent

class MyAgent(SkillAwareAgent):
    def __init__(self):
        super().__init__()
        # Your initialization

    async def _execute_task_normally(self, task: str):
        # Your normal task execution
        # Record actions with:
        self.record_action(tool="playwright_navigate", arguments={...})
        return result
```

### Step 2: Use Skills in Execution

```python
agent = MyAgent()

# This will:
# 1. Search for applicable skills
# 2. Try to use existing skills first
# 3. Fall back to normal execution if needed
# 4. Learn new skills from successful executions
result = await agent.execute_with_skills(
    task="Login to example.com",
    use_skills=True,
    learn_skills=True
)
```

## Common Patterns

### Pattern 1: Search and Execute

```python
# Search
skills = library.search_skills("extract contacts from page")

# Use the best one
if skills:
    best_skill = skills[0]
    result = await best_skill.execute(context)
```

### Pattern 2: Compose Workflow

```python
# Get component skills
login = library.search_skills("login", limit=1)[0]
extract = library.search_skills("extract data", limit=1)[0]

# Combine them
workflow = library.compose_workflow(
    skill_ids=[login.skill_id, extract.skill_id],
    workflow_name="Login and Extract",
    workflow_description="Login then extract all data"
)

# Use the workflow
result = await workflow.execute(context)
```

### Pattern 3: Export/Import

```python
# Export your learned skills
library.export_skills(Path("my_skills.json"))

# Import in another agent
library.import_skills(Path("shared_skills.json"))
```

## Pre-built Skills Reference

### Navigation
- `nav_login_generic` - Generic login flow
- `nav_pagination` - Paginate through results
- `nav_infinite_scroll` - Infinite scroll loading

### Extraction
- `extract_table_data` - Extract HTML tables
- `extract_contacts` - Find emails and phones

### Interaction
- `interact_fill_form` - Fill and submit forms

### Recovery
- `recovery_dismiss_popup` - Dismiss popups

### Verification
- `verify_login_success` - Check login succeeded

## CLI Commands

```bash
# Search for skills
skill search "login to website"

# List all skills
skill list

# Show skill details
skill show nav_login_generic

# Get statistics
skill stats

# Export/import
skill export my_skills.json
skill import shared_skills.json
```

## Example: Complete Workflow

```python
from agent.skill_library import get_skill_library, SkillCategory

# Initialize
library = get_skill_library()

# 1. Search for relevant skills
print("Searching for login skills...")
login_skills = library.search_skills("login to website", limit=3)

for skill in login_skills:
    print(f"Found: {skill.name} ({skill.metrics.success_rate:.0%} success)")

# 2. Execute a task (simulated)
actions = [
    {"tool": "playwright_navigate", "arguments": {"url": "https://example.com"}},
    {"tool": "playwright_fill", "arguments": {"selector": "#email", "value": "user@test.com"}},
    {"tool": "playwright_click", "arguments": {"selector": "button.submit"}},
]

# 3. Learn from execution
print("\nLearning new skill...")
learned = library.learn_skill_from_execution(
    task_description="Login to example.com with email",
    actions=actions,
    result={"success": True},
    category=SkillCategory.NAVIGATION
)

if learned:
    print(f"✓ Learned: {learned.name}")

# 4. Use the learned skill
context = {
    "url": "https://example.com",
    "email": "user@test.com",
}

# Execute (in real scenario)
# result = await learned.execute(context)

# 5. Record usage
library.record_skill_usage(
    skill_id=learned.skill_id,
    success=True,
    execution_time=2.0
)

# 6. Check statistics
stats = library.get_statistics()
print(f"\nLibrary Stats:")
print(f"  Total Skills: {stats['total_skills']}")
print(f"  Active Skills: {stats['by_status'].get('active', 0)}")
print(f"  Success Rate: {stats['avg_success_rate']:.1%}")

# 7. Export for backup
library.export_skills(Path("skills_backup.json"))
print("\n✓ Skills backed up to skills_backup.json")
```

## Troubleshooting

### "ChromaDB not available"

Install ChromaDB:
```bash
pip install chromadb
```

The library works without it (using basic search) but semantic search won't be available.

### Skills not being learned

Make sure:
1. Actions are recorded: `self.record_action(tool, args)`
2. Task completes successfully
3. `learn_skills=True` in `execute_with_skills()`

### Low retrieval accuracy

The library learns from your executions. After more tasks:
- More skills are learned
- Retrieval becomes more accurate
- Performance improves

Target: 500+ skills for 90%+ accuracy.

## Next Steps

1. **Run the demo**: `python examples/skill_library_demo.py`
2. **Read the full docs**: `agent/SKILL_LIBRARY_README.md`
3. **Run tests**: `python agent/test_skill_library.py`
4. **Integrate with your agent**: See integration examples above

## Tips

1. **Start simple** - Use pre-built skills first
2. **Record everything** - All actions should be recorded for learning
3. **Descriptive names** - Better task descriptions = better skill names
4. **Monitor metrics** - Check `skill stats` regularly
5. **Export often** - Back up your learned skills
6. **Share skills** - Import/export to collaborate

## Resources

- Main implementation: `agent/skill_library.py`
- Integration helpers: `agent/skill_integration.py`
- Full documentation: `agent/SKILL_LIBRARY_README.md`
- Tests: `agent/test_skill_library.py`
- Demo: `examples/skill_library_demo.py`

---

**Questions?** Check the full README or run the interactive demo.
