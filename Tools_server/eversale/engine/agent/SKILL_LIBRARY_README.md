# Voyager-Style Skill Library for Eversale

A self-improving skill acquisition and retrieval system based on the [Voyager research paper](https://arxiv.org/abs/2305.16291), adapted for web automation tasks.

## Overview

The skill library enables Eversale to:

1. **Learn automatically** - Extract reusable skills from successful task executions
2. **Search semantically** - Find relevant skills using natural language queries
3. **Compose workflows** - Combine simple skills into complex multi-step tasks
4. **Track performance** - Monitor success rates and continuously improve
5. **Generalize patterns** - Make specific skills work in broader contexts
6. **Share knowledge** - Export/import skills between agents

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Skill Library                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │ Skill Generator│  │ Skill Retriever│  │ Skill Composer│ │
│  │                │  │                │  │              │  │
│  │ - Extract      │  │ - Vector DB    │  │ - Workflow   │  │
│  │ - Generalize   │  │ - Semantic     │  │   Creation   │  │
│  │ - Parameterize │  │   Search       │  │ - Dependency │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
│                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │ Skill Validator│  │ Skill Metrics  │  │  Pre-built   │  │
│  │                │  │                │  │   Skills     │  │
│  │ - Syntax Check │  │ - Success Rate │  │              │  │
│  │ - Safety Check │  │ - Performance  │  │ - Navigation │  │
│  │ - Self-Verify  │  │ - Usage Track  │  │ - Extraction │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Skill

A reusable automation pattern with:

- **Executable code** - Python function as string
- **Metadata** - Name, description, category, tags
- **Parameters** - Configurable inputs
- **Dependencies** - Required tools and other skills
- **Metrics** - Success rate, usage count, execution time
- **Versioning** - Track skill evolution

```python
skill = Skill(
    skill_id="nav_login_generic",
    name="Generic Login Flow",
    description="Navigate to login page and submit credentials",
    category=SkillCategory.NAVIGATION,
    code="""
async def login_generic(context):
    await playwright_navigate(url=context['login_url'])
    await playwright_fill(selector='input[type="email"]', value=context['username'])
    await playwright_fill(selector='input[type="password"]', value=context['password'])
    await playwright_click(selector='button[type="submit"]')
    result = True
    return result
""",
    parameters={
        "login_url": {"type": "string", "description": "URL of login page"},
        "username": {"type": "string", "description": "Username or email"},
        "password": {"type": "string", "description": "Password"},
    },
    required_tools=["playwright_navigate", "playwright_fill", "playwright_click"],
    tags=["login", "authentication", "navigation"],
)
```

### 2. SkillLibrary

Central manager for all skills:

```python
from agent.skill_library import get_skill_library

library = get_skill_library()

# Search for skills
skills = library.search_skills(
    query="login to website",
    category=SkillCategory.NAVIGATION,
    min_success_rate=0.7,
    limit=5
)

# Learn from execution
learned = library.learn_skill_from_execution(
    task_description="Login to example.com",
    actions=[...],
    result={"success": True},
    category=SkillCategory.NAVIGATION
)

# Compose workflow
workflow = library.compose_workflow(
    skill_ids=["nav_login_generic", "extract_contacts"],
    workflow_name="Login and Extract Contacts",
    workflow_description="Login and extract all contacts from pages"
)

# Track usage
library.record_skill_usage(
    skill_id="nav_login_generic",
    success=True,
    execution_time=2.5
)
```

### 3. SkillRetriever

Vector-based semantic search using ChromaDB:

```python
retriever = SkillRetriever()

# Add skill
retriever.add_skill(skill)

# Search semantically
results = retriever.search(
    query="I need to login to a website",
    category=SkillCategory.NAVIGATION,
    min_success_rate=0.8,
    limit=10
)
# Returns: [(skill_id, relevance_score), ...]
```

### 4. SkillGenerator

Extracts and generalizes skills from executions:

```python
generator = SkillGenerator()

# Extract from successful execution
actions = [
    {"tool": "playwright_navigate", "arguments": {"url": "https://example.com"}},
    {"tool": "playwright_fill", "arguments": {"selector": "#search", "value": "query"}},
    {"tool": "playwright_click", "arguments": {"selector": "button.submit"}},
]

skill = generator.extract_from_execution(
    task_description="Search on example.com",
    actions=actions,
    result={"found": 10},
    category=SkillCategory.INTERACTION
)

# Generalize for broader use
generalized = generator.generalize_skill(skill)
```

### 5. SkillComposer

Combines skills into workflows:

```python
composer = SkillComposer()

composite = composer.compose_skills(
    skills=[skill1, skill2, skill3],
    workflow_name="Multi-step Workflow",
    workflow_description="Complete workflow combining multiple skills"
)
```

### 6. SkillValidator

Validates skills before adding to library:

```python
validator = SkillValidator()

is_valid, errors = validator.validate_skill(skill)
if not is_valid:
    print(f"Validation errors: {errors}")

# Self-verification with test cases
test_contexts = [
    {"url": "https://test1.com", "username": "user1"},
    {"url": "https://test2.com", "username": "user2"},
]

passed = validator.self_verify_skill(skill, test_contexts)
```

## Skill Categories

Skills are organized into categories:

| Category | Description | Examples |
|----------|-------------|----------|
| **Navigation** | Moving around sites | Login, search, pagination, scroll |
| **Extraction** | Getting data from pages | Tables, lists, contacts, prices |
| **Interaction** | Interacting with elements | Forms, clicks, uploads, downloads |
| **Verification** | Checking success/validity | Login check, data validation |
| **Recovery** | Handling errors | Dismiss popups, retry, fallbacks |
| **Composite** | Multi-step workflows | Login+Extract, Search+Scrape |
| **Stealth** | Anti-detection | Header rotation, delays, fingerprinting |
| **Analysis** | Processing data | Comparison, filtering, scoring |
| **Communication** | Sending messages | Email, notifications, alerts |

## Pre-built Skills

The library comes with pre-built skills for common patterns:

### Navigation
- **Generic Login Flow** - Login with username/password
- **Paginate Through Results** - Click through multiple pages
- **Infinite Scroll Loading** - Scroll to load more content

### Extraction
- **Extract Table Data** - Get data from HTML tables
- **Extract Contact Information** - Find emails and phone numbers

### Interaction
- **Fill and Submit Form** - Fill form fields and submit

### Recovery
- **Dismiss Cookie/Modal Popups** - Close common popups

### Verification
- **Verify Login Success** - Check if login succeeded

## Integration with Brain Enhanced V2

The skill library integrates seamlessly with the main agent brain:

```python
from agent.skill_integration import SkillAwareAgent

class MyAgent(SkillAwareAgent):
    """Agent with skill library support"""

    async def execute_task(self, task: str):
        # Automatically searches for and uses existing skills
        # Then learns new skills from successful executions
        result = await self.execute_with_skills(
            task=task,
            use_skills=True,    # Try existing skills first
            learn_skills=True   # Learn from this execution
        )
        return result

    async def _execute_task_normally(self, task: str):
        # Your normal agent execution logic
        # Record actions with self.record_action(tool, args, result)
        pass
```

### Recording Actions

To enable skill learning, record actions during execution:

```python
# During task execution
self.record_action(
    tool="playwright_navigate",
    arguments={"url": "https://example.com"},
    result={"success": True}
)

self.record_action(
    tool="playwright_fill",
    arguments={"selector": "#search", "value": query},
    result={"success": True}
)
```

After successful task completion, a skill will be automatically extracted!

## Usage Examples

### Example 1: Basic Skill Search

```python
library = get_skill_library()

# Search for login skills
skills = library.search_skills("login to website", limit=5)

for skill in skills:
    print(f"{skill.name}: {skill.metrics.success_rate:.1%} success rate")
```

### Example 2: Learning from Execution

```python
# Agent executes a task successfully
actions = [
    {"tool": "playwright_navigate", "arguments": {"url": "https://linkedin.com"}},
    {"tool": "playwright_fill", "arguments": {"selector": "#email", "value": "user@example.com"}},
    {"tool": "playwright_fill", "arguments": {"selector": "#password", "value": "pass123"}},
    {"tool": "playwright_click", "arguments": {"selector": "button[type='submit']"}},
]

# Learn the skill
learned = library.learn_skill_from_execution(
    task_description="Login to LinkedIn",
    actions=actions,
    result={"success": True},
    category=SkillCategory.NAVIGATION
)

print(f"Learned skill: {learned.name}")
```

### Example 3: Composing a Workflow

```python
# Find relevant skills
login = library.search_skills("login", limit=1)[0]
extract = library.search_skills("extract contacts", limit=1)[0]

# Compose them
workflow = library.compose_workflow(
    skill_ids=[login.skill_id, extract.skill_id],
    workflow_name="Login and Extract Workflow",
    workflow_description="Login to site and extract all contact information"
)

# Use the workflow
context = {
    "login_url": "https://example.com/login",
    "username": "user@example.com",
    "password": "password123"
}

result = await workflow.execute(context)
```

### Example 4: Performance Tracking

```python
skill = library.get_skill("nav_login_generic")

# Execute skill
success = await execute_skill(skill, context)

# Record usage
library.record_skill_usage(
    skill_id=skill.skill_id,
    success=success,
    execution_time=2.5,
    error="" if success else "Connection timeout"
)

# Check metrics
print(f"Success rate: {skill.metrics.success_rate:.1%}")
print(f"Avg time: {skill.metrics.avg_execution_time:.2f}s")
print(f"Total uses: {skill.metrics.total_uses}")
```

### Example 5: Export/Import Skills

```python
# Export skills to file
library.export_skills(Path("my_skills.json"))

# Import in another agent
new_library = get_skill_library()
new_library.import_skills(Path("my_skills.json"))
```

## CLI Commands

When integrated with the main CLI, skill commands are available:

```bash
# Search for skills
skill search "login to website"

# List all skills
skill list

# List by category
skill list navigation

# Show skill details
skill show nav_login_generic

# Get statistics
skill stats

# Export skills
skill export skills_backup.json

# Import skills
skill import skills_backup.json
```

## Skill Lifecycle

```
┌──────────┐     ┌─────────┐     ┌────────┐     ┌────────────┐
│  DRAFT   │────>│ ACTIVE  │────>│DEPRECATED────>│  DELETED   │
└──────────┘     └─────────┘     └────────┘     └────────────┘
     │               │
     │               │
     v               v
┌──────────┐     ┌─────────┐
│  FAILED  │     │ UPDATED │
└──────────┘     └─────────┘
```

1. **DRAFT** - Newly created or learned, pending validation
2. **ACTIVE** - Validated and available for use
3. **DEPRECATED** - Replaced by a better version
4. **FAILED** - Failed validation or too many errors

## Performance Metrics

Each skill tracks:

- **Total Uses** - Number of times executed
- **Successes/Failures** - Success count and failure count
- **Success Rate** - Percentage of successful executions
- **Avg Execution Time** - Moving average of execution time
- **Last Used** - Timestamp of last use
- **Failure Reasons** - Recent error messages

These metrics enable:
- Skill ranking by reliability
- Performance regression detection
- Automatic skill improvement
- Confidence scoring for retrieval

## Advanced Features

### Skill Versioning

Skills are versioned, allowing tracking of improvements:

```python
skill_v1 = library.get_skill("login_skill")
skill_v1.version  # 1

# Update skill
skill_v2 = improve_skill(skill_v1)
skill_v2.version  # 2

library.add_skill(skill_v2)
library.deprecate_skill(skill_v1.skill_id)
```

### Skill Dependencies

Skills can be composed into workflows:

```python
# Use SkillComposer to combine multiple skills
composite = library.compose_workflow(
    skill_ids=["skill_1", "skill_2", "skill_3"],
    workflow_name="Complex Multi-step Workflow",
    workflow_description="Execute multiple skills in sequence"
)

# The composite skill contains all the combined code
```

### Skill Generalization Levels

Skills track how general vs. specific they are:

- **Level 0** - Very specific (e.g., "Login to example.com")
- **Level 1** - Somewhat general (e.g., "Login to any site with email/password")
- **Level 2** - General (e.g., "Login to any site with any credential type")
- **Level 3+** - Highly general (e.g., "Authenticate to any service")

Higher levels are more reusable but may need more parameters.

### Skill Tags

Tags enable flexible categorization beyond single category:

```python
skill.tags = ["login", "oauth", "social", "google", "authentication"]

# Search by tag
oauth_skills = [s for s in library.skills.values() if "oauth" in s.tags]
```

## Best Practices

### 1. Record All Actions

For automatic skill learning, record every action during execution:

```python
async def execute_task(self, task):
    # Record each action
    self.record_action("playwright_navigate", {"url": url})
    self.record_action("playwright_fill", {"selector": sel, "value": val})
    self.record_action("playwright_click", {"selector": btn})
```

### 2. Use Descriptive Task Descriptions

Better descriptions lead to better skill names and retrieval:

```python
# Good
"Login to LinkedIn with email and password"

# Bad
"Do login thing"
```

### 3. Validate Before Adding

Always validate skills before adding to prevent errors:

```python
is_valid, errors = validator.validate_skill(skill)
if is_valid:
    library.add_skill(skill)
```

### 4. Generalize Learned Skills

Make specific skills more reusable:

```python
specific = library.learn_skill_from_execution(...)
general = generator.generalize_skill(specific)
library.add_skill(general)
```

### 5. Monitor Performance

Track metrics to identify issues:

```python
stats = library.get_statistics()
if stats['avg_success_rate'] < 0.8:
    print("Warning: Library success rate below 80%")

# Find underperforming skills
bad_skills = [
    s for s in library.skills.values()
    if s.metrics.success_rate < 0.5 and s.metrics.total_uses > 10
]
```

### 6. Export Regularly

Back up learned skills:

```python
# Daily backup
library.export_skills(Path(f"backups/skills_{date.today()}.json"))
```

## Configuration

Environment variables:

```bash
# ChromaDB directory
SKILL_LIBRARY_CHROMA_DIR=memory/skills/chroma

# Maximum skills in memory
SKILL_LIBRARY_MAX_SKILLS=1000

# Auto-learn threshold (min actions to learn)
SKILL_LIBRARY_MIN_ACTIONS=2

# Success rate threshold for retrieval
SKILL_LIBRARY_MIN_SUCCESS_RATE=0.7
```

## Troubleshooting

### Vector Search Not Working

If ChromaDB is not available:

```bash
pip install chromadb
```

The library falls back to basic keyword search if ChromaDB is unavailable.

### Skill Validation Failing

Check for:
- Syntax errors in skill code
- Missing required fields (name, description, code)
- Dangerous operations (imports, eval, exec)
- Unknown tool dependencies

### Skills Not Being Learned

Ensure:
- Actions are being recorded with `record_action()`
- Task completes successfully
- At least 2 actions in execution trace
- `learn_skills=True` in `execute_with_skills()`

### Low Success Rates

Investigate:
- Check failure reasons in metrics
- Review skill code for bugs
- Verify required tools are available
- Test with different contexts

## Performance

Target metrics:

- **Skill Count**: 500+ skills
- **Retrieval Accuracy**: 90%+ relevant results
- **Search Latency**: <100ms for semantic search
- **Learning Rate**: 1 skill per 10 successful tasks
- **Success Rate**: 85%+ average across all skills

## Future Enhancements

Planned improvements:

1. **Skill Refinement** - Automatically improve skills based on failures
2. **Multi-Agent Learning** - Share skills across distributed agents
3. **Skill Templates** - Pre-configured templates for common patterns
4. **A/B Testing** - Test skill variants to find best version
5. **Skill Marketplace** - Community sharing of skills
6. **Active Learning** - Request user feedback on uncertain skills
7. **Transfer Learning** - Adapt skills from one domain to another

## References

- [Voyager: An Open-Ended Embodied Agent with Large Language Models](https://arxiv.org/abs/2305.16291)
- [Skill Library Implementation in MineDojo](https://github.com/MineDojo/Voyager)
- [ChromaDB Documentation](https://docs.trychroma.com/)

## Files

```
agent/
├── skill_library.py           # Main skill library implementation
├── skill_integration.py       # Integration with brain_enhanced_v2
├── test_skill_library.py      # Comprehensive test suite
└── SKILL_LIBRARY_README.md    # This file

examples/
└── skill_library_demo.py      # Interactive demo

memory/
└── skills/
    ├── skills.json            # Persistent skill storage
    ├── metrics.json           # Skill metrics
    ├── chroma/                # Vector database
    └── history/               # Skill version history
```

## License

Same as Eversale main project.

---

**Target: 500+ skills, 90%+ retrieval accuracy**

Built with production-grade Python, async support, and vector embeddings.
