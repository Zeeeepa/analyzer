# RAG Tool Search - Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      RAG Tool Search System                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌────────────┐         ┌────────────┐        ┌──────────────┐ │
│  │   Agent    │────────▶│   Tool     │───────▶│   ChromaDB   │ │
│  │  (Brain)   │  Query  │  Search    │ Embed  │   (Vector    │ │
│  │            │         │  Manager   │        │    Store)    │ │
│  └────────────┘         └────────────┘        └──────────────┘ │
│       │                       │                                  │
│       │                       │                                  │
│       │                  ┌────┴─────┐                           │
│       │                  │          │                            │
│       │            ┌─────▼────┐ ┌──▼──────┐                    │
│       │            │  Query   │ │  Tool   │                     │
│       │            │  Cache   │ │ Embedder│                     │
│       │            └──────────┘ └─────────┘                     │
│       │                                                          │
│       │                  ┌────────────┐                         │
│       └─────────────────▶│   Skill    │                         │
│         (Optional)        │  Library   │                         │
│                          └────────────┘                         │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Tool Registration Phase

```
┌──────────────┐
│  Register    │
│  Tools       │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────┐
│  ToolSearchManager                   │
│  - Store tool definition             │
│  - Mark as deferred                  │
└──────┬───────────────────────────────┘
       │
       ├─────────────────┬─────────────┐
       ▼                 ▼             ▼
┌─────────────┐   ┌─────────────┐   ┌──────────────┐
│   Vector    │   │  Keyword    │   │   Critical   │
│  Embedding  │   │   Index     │   │     Set      │
│   (RAG)     │   │ (Fallback)  │   │  (Always     │
│             │   │             │   │   Active)    │
└─────────────┘   └─────────────┘   └──────────────┘
```

### 2. Search Query Flow

```
┌──────────────────────────────────────────────────────────────┐
│  Agent Query: "I need to scrape data from a website"        │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ Query Cache  │
                  │  Check       │
                  └──────┬───────┘
                         │
              ┌──────────┴──────────┐
              │                     │
              ▼ Cache Miss          ▼ Cache Hit
    ┌─────────────────┐      ┌─────────────┐
    │  Generate       │      │   Return    │
    │  Query Embed    │      │   Cached    │
    └────────┬────────┘      │   Results   │
             │               └─────────────┘
             ▼
    ┌─────────────────┐
    │  ChromaDB       │
    │  Vector Search  │
    │  (Semantic)     │
    └────────┬────────┘
             │
             ▼
    ┌──────────────────────────┐
    │  Top-K Similar Tools     │
    │  (e.g., K=10)            │
    └────────┬─────────────────┘
             │
             ▼
    ┌──────────────────────────┐
    │  Multi-Signal Scoring:   │
    │  - Semantic (50%)        │
    │  - Usage (30%)           │
    │  - Success (20%)         │
    └────────┬─────────────────┘
             │
             ▼
    ┌──────────────────────────┐
    │  Filter & Rank           │
    │  - Category filter       │
    │  - Already active filter │
    │  - Threshold filter      │
    └────────┬─────────────────┘
             │
             ▼
    ┌──────────────────────────┐
    │  Return Top-N Results    │
    │  (e.g., N=5)             │
    └────────┬─────────────────┘
             │
             ▼
    ┌──────────────────────────┐
    │  Cache Results           │
    └──────────────────────────┘
```

### 3. Tool Activation Flow

```
┌─────────────────────┐
│  Search Results     │
│  1. web_scraper     │
│  2. html_parser     │
│  3. data_extractor  │
└──────────┬──────────┘
           │
           ▼
┌──────────────────────┐
│  Activate Top Tools  │
└──────────┬───────────┘
           │
    ┌──────┴──────┬──────────────┐
    ▼             ▼              ▼
┌────────┐   ┌────────┐   ┌──────────┐
│ Tool 1 │   │ Tool 2 │   │  Tool 3  │
│ Active │   │ Active │   │  Active  │
└────────┘   └────────┘   └──────────┘
           │
           ▼
┌────────────────────────────┐
│  Get Active Tools          │
│  (for LLM context)         │
│                            │
│  Returns only 5 tools      │
│  instead of all 74         │
│                            │
│  Token savings: 93%        │
└────────────────────────────┘
```

## Component Architecture

### ToolSearchManager

```
┌──────────────────────────────────────────────────────────┐
│                   ToolSearchManager                       │
├──────────────────────────────────────────────────────────┤
│  Properties:                                             │
│  - all_tools: Dict[str, ToolDefinition]                 │
│  - active_tools: Set[str]                               │
│  - config: RAGConfig                                     │
│  - embedder: ToolEmbedder                               │
│  - query_cache: QueryCache                              │
│  - search_index: Dict[str, Set[str]]                    │
│  - skill_library: Optional[SkillLibrary]                │
├──────────────────────────────────────────────────────────┤
│  Methods:                                                │
│  + register_tool(name, desc, params, category, defer)   │
│  + search(query, max_results, category) → Results       │
│  + search_with_skills(query, max_results) → Dict        │
│  + activate_tool(name) → bool                           │
│  + deactivate_tool(name) → bool                         │
│  + record_tool_result(name, success, time)              │
│  + get_active_tools() → List[Dict]                      │
│  + get_token_savings() → Dict                           │
│  + rebuild_index()                                       │
│  + reset_to_critical()                                   │
└──────────────────────────────────────────────────────────┘
```

### ToolEmbedder

```
┌──────────────────────────────────────────────────────────┐
│                     ToolEmbedder                          │
├──────────────────────────────────────────────────────────┤
│  Properties:                                             │
│  - collection: ChromaDB Collection                       │
│  - collection_name: str                                  │
│  - _embedding_cache: Dict[str, str]                     │
├──────────────────────────────────────────────────────────┤
│  Methods:                                                │
│  + index_tool(tool: ToolDefinition)                     │
│  + search(query, top_k, min_similarity) → List[Tuple]   │
│  + rebuild_index(tools: List[ToolDefinition])           │
│  - _initialize_collection()                             │
└──────────────────────────────────────────────────────────┘
           │
           │ Uses
           ▼
┌──────────────────────────────────────────────────────────┐
│                      ChromaDB                             │
├──────────────────────────────────────────────────────────┤
│  - PersistentClient                                      │
│  - Collection: "tool_search"                            │
│  - Embedding Model: "all-MiniLM-L6-v2"                  │
│  - Storage: memory/tool_embeddings/                     │
└──────────────────────────────────────────────────────────┘
```

### QueryCache

```
┌──────────────────────────────────────────────────────────┐
│                      QueryCache                           │
├──────────────────────────────────────────────────────────┤
│  Properties:                                             │
│  - _cache: Dict[hash, (results, timestamp)]             │
│  - _access_order: List[str]  # LRU tracking             │
│  - max_size: int = 100                                   │
│  - ttl_seconds: int = 3600                              │
├──────────────────────────────────────────────────────────┤
│  Methods:                                                │
│  + get(query_hash) → Optional[Results]                  │
│  + set(query_hash, results)                             │
│  + invalidate(pattern)                                   │
└──────────────────────────────────────────────────────────┘
```

### RAGConfig

```
┌──────────────────────────────────────────────────────────┐
│                       RAGConfig                           │
├──────────────────────────────────────────────────────────┤
│  Retrieval:                                              │
│  - rag_top_k: int = 5                                   │
│  - rag_similarity_threshold: float = 0.7                │
│                                                          │
│  Embedding:                                              │
│  - embedding_model: str = "all-MiniLM-L6-v2"           │
│                                                          │
│  Caching:                                                │
│  - cache_enabled: bool = True                           │
│  - cache_ttl_seconds: int = 3600                        │
│  - cache_max_size: int = 100                            │
│                                                          │
│  Scoring Weights:                                        │
│  - weight_semantic: float = 0.5                         │
│  - weight_usage: float = 0.3                            │
│  - weight_success: float = 0.2                          │
│                                                          │
│  Context Optimization:                                   │
│  - include_full_params: bool = False                    │
│  - max_description_length: int = 200                    │
└──────────────────────────────────────────────────────────┘
```

## Relevance Scoring Algorithm

```
Input: Query Q, Tool T

Step 1: Semantic Similarity
┌──────────────────────────────────┐
│  embed(Q) · embed(T)             │
│  ────────────────────            │
│  ||embed(Q)|| ||embed(T)||       │
│                                  │
│  → semantic_score (0-1)          │
└──────────────────────────────────┘

Step 2: Usage Score
┌──────────────────────────────────┐
│  log(usage_count + 1)            │
│  ─────────────────────           │
│  log(max_usage + 1)              │
│                                  │
│  → usage_score (0-1)             │
└──────────────────────────────────┘

Step 3: Success Score
┌──────────────────────────────────┐
│  success_count                   │
│  ──────────────────              │
│  success_count + failure_count   │
│                                  │
│  → success_score (0-1)           │
└──────────────────────────────────┘

Step 4: Weighted Combination
┌──────────────────────────────────┐
│  relevance = 0.5 × semantic      │
│            + 0.3 × usage         │
│            + 0.2 × success       │
│                                  │
│  → final_score (0-1)             │
└──────────────────────────────────┘
```

## Integration with Agent Brain

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Brain                           │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Task: "Scrape product prices from Amazon"             │
│                                                          │
│  ┌────────────────────────────────────┐                │
│  │ 1. Task Understanding              │                │
│  │    - Parse task description        │                │
│  │    - Extract key requirements      │                │
│  └───────────┬────────────────────────┘                │
│              │                                           │
│              ▼                                           │
│  ┌────────────────────────────────────┐                │
│  │ 2. Tool Discovery (RAG)            │                │
│  │    - Query: "web scraping prices"  │◄───────┐      │
│  │    - Get top-5 relevant tools      │        │      │
│  └───────────┬────────────────────────┘        │      │
│              │                                  │      │
│              ▼                          ┌───────┴────┐ │
│  ┌────────────────────────────────────┐│ Tool Search│ │
│  │ 3. Tool Activation                 ││  Manager   │ │
│  │    - web_scraper (95% relevant)    │└────────────┘ │
│  │    - html_parser (87% relevant)    │               │
│  │    - price_extractor (82%)         │               │
│  └───────────┬────────────────────────┘               │
│              │                                          │
│              ▼                                          │
│  ┌────────────────────────────────────┐               │
│  │ 4. Context Assembly                │               │
│  │    - Critical tools (always)       │               │
│  │    - Retrieved tools (task-specific)│              │
│  │    - Total: ~1,000 tokens          │               │
│  │    (vs 14,800 without RAG)         │               │
│  └───────────┬────────────────────────┘               │
│              │                                          │
│              ▼                                          │
│  ┌────────────────────────────────────┐               │
│  │ 5. LLM Call                        │               │
│  │    - Send task + active tools      │               │
│  │    - Get plan/actions              │               │
│  └───────────┬────────────────────────┘               │
│              │                                          │
│              ▼                                          │
│  ┌────────────────────────────────────┐               │
│  │ 6. Execution & Tracking            │               │
│  │    - Execute tool calls            │               │
│  │    - Record success/failure        │───────┐      │
│  │    - Update usage stats            │       │      │
│  └────────────────────────────────────┘       │      │
│                                                │      │
│                                         ┌──────▼────┐ │
│                                         │   Tool    │ │
│                                         │  Metrics  │ │
│                                         └───────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Token Flow Comparison

### Without RAG (Traditional)

```
┌─────────────────────────────────────┐
│  Load ALL 74 Tools                  │
│                                     │
│  ┌─────────────────────────────┐   │
│  │ Tool 1:  200 tokens         │   │
│  │ Tool 2:  200 tokens         │   │
│  │ Tool 3:  200 tokens         │   │
│  │ ...                         │   │
│  │ Tool 74: 200 tokens         │   │
│  └─────────────────────────────┘   │
│                                     │
│  Total: 14,800 tokens               │
│  Context Used: 14,800 tokens        │
│  Context Wasted: ~12,000 tokens     │
└─────────────────────────────────────┘
```

### With RAG (Optimized)

```
┌─────────────────────────────────────┐
│  Load Only Relevant Tools           │
│                                     │
│  Critical Tools (Always):           │
│  ┌─────────────────────────────┐   │
│  │ playwright_navigate: 200    │   │
│  │ playwright_click:    200    │   │
│  │ playwright_fill:     200    │   │
│  └─────────────────────────────┘   │
│                                     │
│  Task-Specific (RAG Retrieved):     │
│  ┌─────────────────────────────┐   │
│  │ web_scraper:     200        │   │
│  │ html_parser:     200        │   │
│  └─────────────────────────────┘   │
│                                     │
│  Total: 1,000 tokens                │
│  Context Used: 1,000 tokens         │
│  Context Wasted: ~0 tokens          │
│  Savings: 13,800 tokens (93%)       │
└─────────────────────────────────────┘
```

## Performance Characteristics

### Time Complexity

```
Operation                    Without RAG    With RAG
─────────────────────────    ───────────    ────────
Tool Registration            O(1)           O(E)   [E = embedding time]
Search (cold)                O(N)           O(log N + K)  [K = top-K]
Search (cached)              O(N)           O(1)
Tool Activation              O(1)           O(1)
Get Active Tools             O(A)           O(A)   [A = active tools]

N = total tools (74)
A = active tools (~5)
K = top-K results (5-10)
E = embedding generation (~10ms)
```

### Space Complexity

```
Component           Memory Usage
───────────         ────────────
Tool Registry       O(N × D)     [N tools × D description size]
Vector Embeddings   O(N × V)     [N tools × V vector dimension]
Query Cache         O(C × K)     [C cached queries × K results]
Keyword Index       O(W × N)     [W words × N tools]

Typical:
- N = 74 tools
- D = 200 chars avg
- V = 384 dimensions (all-MiniLM-L6-v2)
- C = 100 cached queries
- K = 5 results
- W = 500 unique words

Total: ~5MB (very lightweight)
```

## Fallback Mechanism

```
┌──────────────────────────────────────┐
│  Search Request                      │
└────────────┬─────────────────────────┘
             │
             ▼
      ┌──────────────┐
      │ ChromaDB     │
      │ Available?   │
      └──────┬───────┘
             │
      ┌──────┴──────┐
      │             │
      ▼ Yes         ▼ No
┌──────────┐   ┌─────────────┐
│   RAG    │   │  Keyword    │
│  Search  │   │   Search    │
│(Semantic)│   │ (Fallback)  │
└──────────┘   └─────────────┘
      │             │
      └──────┬──────┘
             │
             ▼
      ┌──────────────┐
      │   Return     │
      │   Results    │
      └──────────────┘

Graceful degradation:
- RAG preferred (semantic understanding)
- Keyword search fallback (still functional)
- No failure mode
```

## Future Enhancements

```
Current:                     Planned:
────────                     ────────

Single signal               → Multi-modal embeddings
Vector search               → Hybrid search (vector + BM25)
Static embeddings           → Fine-tuned embeddings
Usage stats                 → Collaborative filtering
Manual categories           → Auto-categorization
Tool-level search           → Tool composition search
Simple caching              → Distributed cache (Redis)
Local ChromaDB              → Scalable vector DB
```
