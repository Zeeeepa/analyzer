# RAG-Enhanced Tool Search

Efficient tool discovery using Retrieval-Augmented Generation (RAG) with vector embeddings and semantic search.

## Problem Statement

Traditional tool search loads all tool documentation into context, resulting in:
- **High token usage**: 74+ tools × 200 tokens = ~15,000 tokens
- **Context pollution**: Irrelevant tools waste context window
- **Slow retrieval**: Linear search through all tools
- **No semantic understanding**: Keyword matching misses conceptually similar tools

## Solution: RAG-Based Tool Search

Our RAG implementation provides:
1. **Vector embeddings** for semantic understanding
2. **Smart retrieval** - only load top-K relevant tools
3. **Multi-signal ranking** - semantic + usage + success rate
4. **Query caching** - instant results for repeated queries
5. **Skill integration** - unified search across tools and skills

### Token Savings

```
Without RAG: 74 tools × 200 tokens = 14,800 tokens
With RAG:     5 tools × 200 tokens =  1,000 tokens
Savings:                            13,800 tokens (93%)
```

## Quick Start

### Basic Usage

```python
from tool_search import ToolSearchManager, RAGConfig

# Create manager
manager = ToolSearchManager()

# Register tools
manager.register_tool(
    name="web_scraper",
    description="Extract structured data from web pages",
    parameters={"url": {"type": "string"}},
    category="web",
    defer_loading=True
)

# Search semantically
results = manager.search("I need to get data from a website", max_results=5)

for result in results:
    print(f"{result.tool.name}: {result.relevance_score:.1%}")
    manager.activate_tool(result.tool.name)
```

### Custom Configuration

```python
config = RAGConfig()
config.rag_top_k = 10                      # Return more results
config.rag_similarity_threshold = 0.6      # Lower threshold
config.weight_semantic = 0.7               # Prioritize semantic match
config.cache_ttl_seconds = 7200            # 2 hour cache

manager = ToolSearchManager(config=config)
```

### Integration with Skill Library

```python
from skill_library import SkillLibrary

skill_lib = SkillLibrary()
manager = ToolSearchManager(skill_library=skill_lib)

# Search both tools and skills
results = await manager.search_with_skills(
    query="navigate and click button",
    max_results=5
)

print(f"Found {len(results['tools'])} tools")
print(f"Found {len(results['skills'])} skills")
```

## Architecture

### Components

1. **ToolSearchManager**: Main orchestrator
   - Manages tool registry
   - Routes queries to RAG or keyword search
   - Handles activation/deactivation
   - Tracks usage and success metrics

2. **ToolEmbedder**: Vector embedding engine
   - Uses ChromaDB for vector storage
   - Creates embeddings from tool descriptions
   - Performs semantic similarity search
   - Caches embeddings for efficiency

3. **QueryCache**: LRU cache for queries
   - Caches recent query results
   - TTL-based expiration
   - Pattern-based invalidation

4. **RAGConfig**: Configuration manager
   - Top-K retrieval settings
   - Similarity thresholds
   - Relevance scoring weights
   - Cache settings

### Data Flow

```
Query: "extract data from website"
    ↓
[QueryCache] → Cache hit? Return cached results
    ↓ (miss)
[ToolEmbedder] → Generate query embedding
    ↓
[ChromaDB] → Find top-K similar tool embeddings
    ↓
[RelevanceScorer] → Combine semantic + usage + success signals
    ↓
[ToolSearchManager] → Rank and filter results
    ↓
[QueryCache] → Cache results for future queries
    ↓
Return top-N tools
```

## Configuration Reference

### RAGConfig Options

```python
class RAGConfig:
    # Retrieval
    rag_top_k: int = 5                      # Number of tools to retrieve
    rag_similarity_threshold: float = 0.7   # Min similarity (0-1)

    # Embedding
    embedding_model: str = "all-MiniLM-L6-v2"  # Sentence transformer model

    # Caching
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600           # 1 hour
    cache_max_size: int = 100               # Max cached queries

    # Relevance scoring weights (must sum to 1.0)
    weight_semantic: float = 0.5            # Semantic similarity
    weight_usage: float = 0.3               # Historical usage
    weight_success: float = 0.2             # Success rate

    # Context optimization
    include_full_params: bool = False       # Include full param schemas
    max_description_length: int = 200       # Truncate long descriptions
```

### Environment Variables

```bash
# Optional: Force ChromaDB on/off
export EVERSALE_ENABLE_CHROMADB=true

# ChromaDB will auto-disable if:
# - Not enough memory (< 800MB available)
# - WSL with < 1500MB available
# - Import fails
```

## API Reference

### ToolSearchManager

#### `register_tool(name, description, parameters, category, defer_loading)`
Register a new tool for search.

```python
manager.register_tool(
    name="csv_exporter",
    description="Export data to CSV format",
    parameters={"data": {"type": "array"}},
    category="data",
    defer_loading=True
)
```

#### `search(query, max_results, category) -> List[ToolSearchResult]`
Search for tools using RAG or keyword search.

```python
results = manager.search(
    query="parse JSON data",
    max_results=5,
    category="data"  # Optional filter
)
```

#### `async search_with_skills(query, max_results) -> Dict`
Search both tools and skills (requires skill library).

```python
results = await manager.search_with_skills(
    query="automate web browsing",
    max_results=5
)
```

#### `activate_tool(name) -> bool`
Activate a deferred tool for use.

```python
manager.activate_tool("web_scraper")
```

#### `record_tool_result(name, success, execution_time)`
Record tool execution for relevance scoring.

```python
manager.record_tool_result(
    name="web_scraper",
    success=True,
    execution_time=1.5
)
```

#### `get_token_savings() -> Dict`
Get token usage statistics.

```python
savings = manager.get_token_savings()
print(f"Saved {savings['tokens_saved']} tokens")
print(f"RAG enabled: {savings['rag_enabled']}")
```

#### `rebuild_index()`
Rebuild the entire RAG index.

```python
manager.rebuild_index()
```

### ToolSearchResult

```python
@dataclass
class ToolSearchResult:
    tool: ToolDefinition           # The tool
    relevance_score: float         # Overall score (0-1)
    semantic_score: float          # Semantic similarity (0-1)
    usage_score: float             # Usage frequency (0-1)
    success_score: float           # Success rate (0-1)
    match_reason: str              # Explanation
```

## Relevance Scoring

Tools are ranked using a weighted combination of signals:

### 1. Semantic Similarity (50% weight)
- Vector distance between query and tool embeddings
- Captures conceptual similarity
- Works across different phrasings

### 2. Usage Frequency (30% weight)
- How often the tool has been used
- Log-normalized to handle wide ranges
- Favors proven, frequently-used tools

### 3. Success Rate (20% weight)
- Percentage of successful executions
- Tracks reliability
- New tools default to 50%

### Combined Score

```python
relevance = (
    semantic_similarity * 0.5 +
    usage_frequency * 0.3 +
    success_rate * 0.2
)
```

Customize weights via `RAGConfig`:

```python
config = RAGConfig()
config.weight_semantic = 0.7  # Prioritize semantic match
config.weight_usage = 0.2
config.weight_success = 0.1
```

## Performance Optimization

### 1. Embedding Cache

Tool embeddings are cached to avoid recomputation:

```python
# Embeddings cached by content hash
# Only recomputed if tool description changes
self._embedding_cache[tool.name] = content_hash
```

### 2. Query Cache

Recent queries cached with TTL:

```python
# First query: ~50ms (compute embeddings)
# Cached query: ~1ms (instant retrieval)
query_cache.get(query_hash)
```

### 3. Lazy ChromaDB Loading

ChromaDB only loaded when needed:

```python
# Check memory availability
# Only load if > 800MB free
# Falls back to keyword search if unavailable
```

### 4. Context Optimization

Minimize tokens sent to LLM:

```python
config = RAGConfig()
config.include_full_params = False      # Only param names
config.max_description_length = 200     # Truncate long descriptions
```

## Integration Examples

### With Brain/Agent

```python
from tool_search import get_tool_search, RAGConfig

class Agent:
    def __init__(self):
        config = RAGConfig()
        self.tool_search = get_tool_search(config)

        # Register all available tools
        for tool in self.available_tools:
            self.tool_search.register_tool(**tool, defer_loading=True)

    def get_tools_for_task(self, task_description):
        # Get relevant tools for task
        results = self.tool_search.search(
            query=task_description,
            max_results=5
        )

        # Activate found tools
        for result in results:
            self.tool_search.activate_tool(result.tool.name)

        # Return active tools for LLM context
        return self.tool_search.get_active_tools()
```

### With Skill Library

```python
from skill_library import SkillLibrary
from tool_search import ToolSearchManager

skill_lib = SkillLibrary()
tool_search = ToolSearchManager(skill_library=skill_lib)

async def find_resources(query):
    # Search both tools and skills
    results = await tool_search.search_with_skills(query)

    # Use tools for primitive operations
    for tool in results['tools']:
        tool_search.activate_tool(tool['name'])

    # Use skills for complex workflows
    for skill in results['skills']:
        await skill_lib.execute_skill_async(skill['name'])
```

## Troubleshooting

### ChromaDB Not Loading

**Symptom**: Falls back to keyword search even though ChromaDB is installed.

**Causes**:
1. Insufficient memory (< 800MB available)
2. WSL with < 1500MB available
3. Import error

**Solutions**:
```bash
# Check available memory
free -m

# Force enable (if you have enough memory)
export EVERSALE_ENABLE_CHROMADB=true

# Check import
python -c "import chromadb; print('OK')"
```

### Poor Search Results

**Symptom**: Search returns irrelevant tools.

**Solutions**:

1. **Lower similarity threshold**:
```python
config = RAGConfig()
config.rag_similarity_threshold = 0.5  # More lenient
```

2. **Increase top-K**:
```python
config.rag_top_k = 10  # More candidates
```

3. **Rebuild index**:
```python
manager.rebuild_index()
```

4. **Check tool descriptions**:
```python
# Make descriptions more detailed
manager.register_tool(
    name="scraper",
    description="Extract structured data from HTML web pages using CSS selectors, XPath, or regex patterns",  # More detailed
    ...
)
```

### Slow First Query

**Symptom**: First query takes several seconds.

**Cause**: ChromaDB downloads embedding model on first use.

**Solution**: Pre-warm the cache:

```python
# Trigger model download
manager.search("test query", max_results=1)
```

### Cache Not Working

**Symptom**: Repeated queries still slow.

**Check**:
```python
config = RAGConfig()
config.cache_enabled = True  # Ensure enabled

manager = ToolSearchManager(config)

# After queries, check cache
savings = manager.get_token_savings()
print(f"Cache size: {savings['cache_size']}")
```

## Best Practices

### 1. Tool Descriptions

Write clear, searchable descriptions:

```python
# ❌ Bad
description="Scrapes web"

# ✅ Good
description="Extract structured data from HTML web pages using CSS selectors or XPath queries"
```

### 2. Categories

Use consistent categories for filtering:

```python
categories = ["web", "data", "file", "api", "browser", "ml"]

manager.register_tool(..., category="web")
manager.search(query, category="web")  # Filter by category
```

### 3. Usage Tracking

Always record results for better ranking:

```python
start_time = time.time()
try:
    result = execute_tool(tool_name, params)
    execution_time = time.time() - start_time
    manager.record_tool_result(tool_name, success=True, execution_time)
except Exception:
    manager.record_tool_result(tool_name, success=False)
```

### 4. Context Management

Deactivate unused tools to free context:

```python
# After task completion
for tool in used_tools:
    if tool not in critical_tools:
        manager.deactivate_tool(tool)

# Or reset to critical only
manager.reset_to_critical()
```

### 5. Index Maintenance

Rebuild index when tools change significantly:

```python
# After bulk tool updates
manager.rebuild_index()

# After changing descriptions
manager.rebuild_index()
```

## Migration Guide

### From Keyword Search

```python
# Old approach
def search_tools(query):
    matches = []
    for tool in all_tools:
        if any(word in tool.description for word in query.split()):
            matches.append(tool)
    return matches[:5]

# New approach
manager = ToolSearchManager()
results = manager.search(query, max_results=5)
```

### From Loading All Tools

```python
# Old approach (loads everything)
def get_tools_for_llm():
    return [tool.to_dict() for tool in all_tools]

# New approach (loads only relevant)
def get_tools_for_llm(task):
    results = manager.search(task, max_results=5)
    for r in results:
        manager.activate_tool(r.tool.name)
    return manager.get_active_tools()
```

## Metrics and Monitoring

Track RAG performance:

```python
# Token savings
savings = manager.get_token_savings()
logger.info(f"Token savings: {savings['savings_percent']:.1f}%")

# Cache performance
cache_hits = savings['cache_size']
logger.info(f"Query cache: {cache_hits} entries")

# Search quality
for result in results:
    logger.info(f"{result.tool.name}: {result.relevance_score:.1%}")
    logger.info(f"  Breakdown: {result.match_reason}")
```

## Future Enhancements

Planned improvements:

1. **Fine-tuned embeddings**: Train on tool usage patterns
2. **Collaborative filtering**: "Tools used together" recommendations
3. **Query expansion**: Expand queries with synonyms
4. **Negative sampling**: Learn from failed tool selections
5. **Multi-modal search**: Include code examples in embeddings
6. **Tool composition**: Suggest tool combinations for complex tasks

## References

- ChromaDB: https://docs.trychroma.com/
- Sentence Transformers: https://www.sbert.net/
- RAG Paper: https://arxiv.org/abs/2005.11401
- Voyager (Skill Library): https://arxiv.org/abs/2305.16291

## Support

Issues or questions:
1. Check troubleshooting section above
2. Run example: `python tool_search_rag_example.py`
3. Check logs for `[RAG]` and `[TOOL-SEARCH]` tags
4. Verify ChromaDB: `python -c "import chromadb; print('OK')"`
