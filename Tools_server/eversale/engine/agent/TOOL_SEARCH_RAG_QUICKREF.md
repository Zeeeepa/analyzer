# RAG Tool Search - Quick Reference

## Installation

```bash
# Already in requirements.txt
pip install chromadb
```

## Basic Usage

```python
from tool_search import ToolSearchManager

# Initialize
manager = ToolSearchManager()

# Register tool
manager.register_tool(
    name="web_scraper",
    description="Extract data from web pages",
    parameters={"url": {"type": "string"}},
    category="web",
    defer_loading=True
)

# Search
results = manager.search("get data from website", max_results=5)

# Activate
for r in results:
    manager.activate_tool(r.tool.name)

# Get active tools for LLM
tools = manager.get_active_tools()
```

## Configuration

```python
from tool_search import RAGConfig

config = RAGConfig()
config.rag_top_k = 10                    # More results
config.rag_similarity_threshold = 0.6    # Lower threshold
config.weight_semantic = 0.7             # Semantic priority
config.cache_ttl_seconds = 7200          # 2hr cache

manager = ToolSearchManager(config=config)
```

## Common Patterns

### Agent Integration

```python
class Agent:
    def __init__(self):
        self.tool_search = ToolSearchManager()
        # Register all tools
        for tool in available_tools:
            self.tool_search.register_tool(**tool, defer_loading=True)

    def get_tools(self, task):
        results = self.tool_search.search(task, max_results=5)
        for r in results:
            self.tool_search.activate_tool(r.tool.name)
        return self.tool_search.get_active_tools()
```

### With Skill Library

```python
from skill_library import SkillLibrary

skill_lib = SkillLibrary()
manager = ToolSearchManager(skill_library=skill_lib)

results = await manager.search_with_skills(
    query="automate browser task",
    max_results=5
)
```

### Usage Tracking

```python
import time

start = time.time()
try:
    execute_tool(name, params)
    manager.record_tool_result(name, success=True,
                                execution_time=time.time()-start)
except Exception:
    manager.record_tool_result(name, success=False)
```

## Key Methods

| Method | Description | Example |
|--------|-------------|---------|
| `register_tool()` | Add tool to index | `manager.register_tool(name, desc, params)` |
| `search()` | Find relevant tools | `results = manager.search(query, max_results=5)` |
| `search_with_skills()` | Search tools + skills | `await manager.search_with_skills(query)` |
| `activate_tool()` | Load tool into context | `manager.activate_tool("scraper")` |
| `deactivate_tool()` | Remove from context | `manager.deactivate_tool("scraper")` |
| `record_tool_result()` | Track usage/success | `manager.record_tool_result(name, success=True)` |
| `get_active_tools()` | Get loaded tools | `tools = manager.get_active_tools()` |
| `get_token_savings()` | View statistics | `savings = manager.get_token_savings()` |
| `rebuild_index()` | Rebuild embeddings | `manager.rebuild_index()` |

## Relevance Scoring

```
Relevance = (Semantic × 0.5) + (Usage × 0.3) + (Success × 0.2)
```

- **Semantic**: Vector similarity (how conceptually close)
- **Usage**: Frequency of use (how popular)
- **Success**: Success rate (how reliable)

Customize weights:
```python
config.weight_semantic = 0.7
config.weight_usage = 0.2
config.weight_success = 0.1
```

## Token Savings

```
Without RAG: 74 tools × 200 tokens = 14,800 tokens
With RAG:     5 tools × 200 tokens =  1,000 tokens
Savings:                             93%
```

Check savings:
```python
savings = manager.get_token_savings()
print(f"Saved {savings['tokens_saved']} tokens ({savings['savings_percent']:.1f}%)")
```

## Troubleshooting

### ChromaDB Not Loading
```python
# Check status
savings = manager.get_token_savings()
print(f"RAG enabled: {savings['rag_enabled']}")

# Force enable
export EVERSALE_ENABLE_CHROMADB=true

# Falls back to keyword search if unavailable
```

### Poor Results
```python
# Lower threshold
config.rag_similarity_threshold = 0.5

# More candidates
config.rag_top_k = 10

# Rebuild index
manager.rebuild_index()
```

### Slow Queries
```python
# First query downloads model (one-time)
# Subsequent queries use cache

# Check cache
savings = manager.get_token_savings()
print(f"Cache size: {savings['cache_size']}")
```

## Best Practices

1. **Write descriptive tool descriptions**
   ```python
   # Good: "Extract structured data from HTML using CSS selectors"
   # Bad: "Scrapes web"
   ```

2. **Use consistent categories**
   ```python
   categories = ["web", "data", "file", "api", "browser"]
   ```

3. **Always track results**
   ```python
   manager.record_tool_result(name, success=True, execution_time=1.5)
   ```

4. **Deactivate unused tools**
   ```python
   manager.reset_to_critical()  # Keep only critical tools
   ```

5. **Rebuild after bulk changes**
   ```python
   # After updating many tool descriptions
   manager.rebuild_index()
   ```

## Configuration Cheat Sheet

```python
class RAGConfig:
    # Retrieval
    rag_top_k = 5                        # Tools to retrieve
    rag_similarity_threshold = 0.7       # Min similarity (0-1)

    # Model
    embedding_model = "all-MiniLM-L6-v2" # Sentence transformer

    # Cache
    cache_enabled = True
    cache_ttl_seconds = 3600             # 1 hour
    cache_max_size = 100                 # Max queries

    # Scoring weights
    weight_semantic = 0.5                # Semantic similarity
    weight_usage = 0.3                   # Usage frequency
    weight_success = 0.2                 # Success rate

    # Context optimization
    include_full_params = False          # Minimal params
    max_description_length = 200         # Truncate descriptions
```

## Examples

Run examples:
```bash
python tool_search_rag_example.py
```

Read full documentation:
```bash
cat TOOL_SEARCH_RAG_README.md
```

## Migration from Old System

```python
# Old (loads everything)
def get_tools():
    return all_tools

# New (loads relevant only)
def get_tools(task):
    results = manager.search(task, max_results=5)
    for r in results:
        manager.activate_tool(r.tool.name)
    return manager.get_active_tools()
```

## Performance Tips

1. **Pre-warm cache**: Run dummy query at startup
2. **Batch register**: Register all tools at initialization
3. **Use categories**: Filter by category when possible
4. **Monitor cache**: Check cache hit rate
5. **Tune weights**: Adjust based on your use case

## Quick Diagnosis

```python
# Check system status
savings = manager.get_token_savings()
print(f"""
RAG Status:
  - RAG enabled: {savings['rag_enabled']}
  - Total tools: {savings['total_tools']}
  - Active tools: {savings['active_tools']}
  - Token savings: {savings['savings_percent']:.1f}%
  - Cache size: {savings['cache_size']}
""")

# Test search
results = manager.search("test query", max_results=3)
for r in results:
    print(f"{r.tool.name}: {r.relevance_score:.1%}")
```
