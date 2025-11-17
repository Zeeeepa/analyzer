# WrtnLabs Vector Storage & Embeddings Guide

**Complete Guide to Vector Storage, Embeddings, and RAG Integration**

---

## Table of Contents

1. [Overview](#1-overview)
2. [Vector Storage Options](#2-vector-storage-options)
3. [Embeddings Models](#3-embeddings-models)
4. [Integration Architecture](#4-integration-architecture)
5. [Configuration](#5-configuration)
6. [Usage Examples](#6-usage-examples)
7. [Best Practices](#7-best-practices)

---

## 1. Overview

### 1.1 What WrtnLabs Uses

The WrtnLabs ecosystem uses **OpenAI's native Vector Store** as the primary vector storage solution, integrated through the **Agentica framework**.

**Key Repository:**
- 🔗 **[@agentica/openai-vector-store](https://github.com/wrtnlabs/vector-store)** (5 stars)
- Purpose: RAG (Retrieval Augmented Generation) for AI agents
- Integration: Function Calling via Agentica framework

### 1.2 Philosophy

> **"Intelligent Memory System for Agents"**

Traditional AI systems send entire conversation histories sequentially. WrtnLabs' approach:
- ✅ Supply agents with large-scale data in a **single call**
- ✅ Mimics how humans recall **long-term memories**
- ✅ Dynamic file retrieval **on-demand**

---

## 2. Vector Storage Options

### 2.1 Primary: OpenAI Vector Store (Native)

**Status:** ✅ **Officially Supported & Integrated**

```typescript
import OpenAI from 'openai';
import { AgenticaOpenAIVectorStoreSelector } from '@agentica/openai-vector-store';

const openai = new OpenAI({ apiKey: process.env.OPENAI_KEY });

const selector = new AgenticaOpenAIVectorStoreSelector({
  provider: {
    api: openai,
    assistant: { id: assistant_id },
    vectorStore: { id: vector_store_id }
  }
});
```

**Features:**
- ✅ SHA-256 hashing for duplicate prevention
- ✅ Automatic file management
- ✅ Priority-based file retrieval
- ✅ Integrated with OpenAI Assistants API
- ✅ Function Calling support via Agentica

**Storage Backend:**
- Uses OpenAI's managed vector storage
- No local database required
- Files stored in OpenAI's infrastructure

### 2.2 Self-Hosted Options (Community/Future)

While WrtnLabs officially uses OpenAI Vector Store, the architecture is extensible. Here are **potential alternatives** (not officially supported):

| Vector DB | Status | Use Case | Notes |
|-----------|--------|----------|-------|
| **OpenAI Vector Store** | ✅ Official | Production | Fully integrated |
| **Pinecone** | 🟡 Possible | Cloud-native | Would need custom integration |
| **Chroma** | 🟡 Possible | Local/self-hosted | Would need custom integration |
| **Weaviate** | 🟡 Possible | Enterprise | Would need custom integration |
| **Qdrant** | 🟡 Possible | High-performance | Would need custom integration |
| **Milvus** | 🟡 Possible | Large-scale | Would need custom integration |
| **PostgreSQL pgvector** | 🟡 Possible | Existing DB | Already uses PostgreSQL! |

### 2.3 PostgreSQL pgvector Extension (Feasible)

**Why This Makes Sense:**
- AutoBE already uses PostgreSQL for data
- pgvector extension adds vector capabilities
- Self-hosted, no external dependencies

**Potential Implementation:**
```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create embeddings table
CREATE TABLE document_embeddings (
  id SERIAL PRIMARY KEY,
  content TEXT,
  embedding vector(1536),  -- For OpenAI ada-002
  metadata JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Create index for similarity search
CREATE INDEX ON document_embeddings 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

---

## 3. Embeddings Models

### 3.1 Officially Supported: OpenAI Embeddings

**Primary Model:** `text-embedding-3-large`

```typescript
// Configuration
const EMBEDDINGS_CONFIG = {
  endpoint: "https://api.openai.com/v1/embeddings",
  apiKey: process.env.OPENAI_API_KEY,
  model: "text-embedding-3-large",
  dimensions: 1536  // or 3072 for large
};
```

**Available OpenAI Models:**

| Model | Dimensions | Cost per 1M tokens | Use Case |
|-------|------------|-------------------|----------|
| **text-embedding-3-small** | 512 / 1536 | $0.02 | Cost-effective, general |
| **text-embedding-3-large** | 256 / 1024 / 3072 | $0.13 | High accuracy |
| **text-embedding-ada-002** | 1536 | $0.10 | Legacy (still good) |

**Dimension Parameter:**
```typescript
// Shorter embeddings for faster processing
const response = await openai.embeddings.create({
  model: "text-embedding-3-large",
  input: "Your text here",
  dimensions: 1024  // Reduced from 3072
});
```

### 3.2 Alternative Embeddings (Not Officially Supported)

These would require custom integration:

#### **Anthropic**
- ❌ **No embeddings API** (Anthropic doesn't offer embeddings)
- Alternative: Use OpenAI or other providers

#### **Cohere**
```typescript
// Hypothetical integration
import { CohereClient } from 'cohere-ai';

const cohere = new CohereClient({
  token: process.env.COHERE_API_KEY
});

const response = await cohere.embed({
  texts: ["Text to embed"],
  model: "embed-english-v3.0",
  inputType: "search_document"
});
```

**Models:**
- `embed-english-v3.0` (1024 dimensions)
- `embed-multilingual-v3.0` (1024 dimensions)
- `embed-english-light-v3.0` (384 dimensions)

#### **Open-Source Models (Local)**

```python
# Using sentence-transformers
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings = model.encode(["Text to embed"])
```

**Popular Models:**
- `all-MiniLM-L6-v2` (384 dim) - Fast, lightweight
- `all-mpnet-base-v2` (768 dim) - Balanced
- `e5-large-v2` (1024 dim) - High quality

---

## 4. Integration Architecture

### 4.1 Current Architecture (OpenAI Vector Store)

```
┌─────────────────────────────────────────────────────┐
│                  USER QUERY                         │
└────────────────────┬────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────┐
│              AGENTICA AGENT                         │
│  ┌───────────────────────────────────────┐         │
│  │  AgenticaOpenAIVectorStoreSelector    │         │
│  │  - Query processing                    │         │
│  │  - File management                     │         │
│  │  - Duplicate prevention (SHA-256)      │         │
│  └────────────────┬──────────────────────┘         │
└────────────────────┼────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────┐
│           OPENAI VECTOR STORE                       │
│  ┌───────────────────────────────────────┐         │
│  │  • File storage                        │         │
│  │  • Automatic embeddings generation     │         │
│  │  • Semantic search                     │         │
│  │  • Retrieval via Assistants API        │         │
│  └───────────────────────────────────────┘         │
└─────────────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────┐
│                RESPONSE                             │
│  Context-aware answer with citations               │
└─────────────────────────────────────────────────────┘
```

### 4.2 How It Works

**Step 1: File Upload**
```typescript
await selector.attach({
  file: {
    data: fileBuffer,
    name: "document.pdf"
  }
});

// System:
// 1. Calculates SHA-256 hash
// 2. Checks for duplicates
// 3. Uploads to OpenAI Vector Store
// 4. OpenAI automatically generates embeddings
// 5. Indexes for semantic search
```

**Step 2: Query Processing**
```typescript
const result = await selector.query({
  query: "What is the refund policy?"
});

// System:
// 1. Creates new thread
// 2. Agent searches vector store
// 3. Retrieves relevant documents
// 4. Generates response with context
```

**Step 3: File Management**
```typescript
const status = await selector.status();
// Returns:
// {
//   vectorStore: { id, name, fileCounts },
//   assistant: { id, name, model, tools }
// }
```

---

## 5. Configuration

### 5.1 Environment Variables

```bash
# ===== OPENAI CONFIGURATION =====
OPENAI_API_KEY="sk-proj-your-key"
OPENAI_MODEL="gpt-4.1"

# ===== VECTOR STORE CONFIGURATION =====
# These are created via OpenAI API
OPENAI_ASSISTANT_ID="asst_..."
OPENAI_VECTOR_STORE_ID="vs_..."

# ===== EMBEDDINGS CONFIGURATION (Optional) =====
# OpenAI handles embeddings automatically,
# but you can specify preferences

EMBEDDINGS_MODEL="text-embedding-3-large"
EMBEDDINGS_DIMENSIONS=1536
EMBEDDINGS_BATCH_SIZE=100

# ===== OPTIONAL: CUSTOM VECTOR DB =====
# If implementing pgvector or other

# PostgreSQL with pgvector
PGVECTOR_DATABASE_URL="postgresql://user:pass@localhost:5432/vectors"

# Pinecone
PINECONE_API_KEY="your-key"
PINECONE_ENVIRONMENT="us-east-1-aws"
PINECONE_INDEX="autobe-docs"

# Chroma (local)
CHROMA_HOST="localhost"
CHROMA_PORT="8000"
```

### 5.2 Initialization

```typescript
// Complete setup
import OpenAI from 'openai';
import { Agentica } from '@agentica/core';
import { AgenticaOpenAIVectorStoreSelector } from '@agentica/openai-vector-store';
import typia from 'typia';

// 1. Create OpenAI instance
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY
});

// 2. Create assistant (if not exists)
const assistant = await openai.beta.assistants.create({
  name: "Knowledge Base Assistant",
  instructions: "You help users find information from uploaded documents.",
  model: "gpt-4-1106-preview",
  tools: [{ type: "file_search" }]
});

// 3. Create vector store (if not exists)
const vectorStore = await openai.beta.vectorStores.create({
  name: "Company Knowledge Base"
});

// 4. Link assistant to vector store
await openai.beta.assistants.update(assistant.id, {
  tool_resources: {
    file_search: {
      vector_store_ids: [vectorStore.id]
    }
  }
});

// 5. Create selector
const selector = new AgenticaOpenAIVectorStoreSelector({
  provider: {
    api: openai,
    assistant: { id: assistant.id },
    vectorStore: { id: vectorStore.id }
  }
});

// 6. Integrate with Agentica
const agent = new Agentica({
  model: "chatgpt",
  vendor: { api: openai, model: "gpt-4-1106-preview" },
  controllers: [
    {
      protocol: "class",
      name: "vectorStore",
      application: typia.llm.application<typeof selector, "llm">(),
      execute: selector
    }
  ]
});
```

---

## 6. Usage Examples

### 6.1 Basic RAG Implementation

```typescript
// Upload documents
const documents = [
  { name: "policy.pdf", data: policyBuffer },
  { name: "faq.txt", data: faqBuffer },
  { name: "manual.docx", data: manualBuffer }
];

for (const doc of documents) {
  await selector.attach({ file: doc });
  console.log(`✅ Uploaded: ${doc.name}`);
}

// Query the knowledge base
const response = await selector.query({
  query: "What is the return policy for defective items?"
});

console.log(response.response);
// → Returns context-aware answer citing the relevant policy
```

### 6.2 With Agentica Function Calling

```typescript
// Agent can automatically invoke vector store
const userMessage = "Can you find information about shipping times?";

const agentResponse = await agent.chat({
  messages: [
    { role: "user", content: userMessage }
  ]
});

// Behind the scenes:
// 1. Agent recognizes need for external knowledge
// 2. Automatically calls vectorStore.query()
// 3. Retrieves relevant documents
// 4. Synthesizes answer with citations
```

### 6.3 File Management

```typescript
// Check current status
const status = await selector.status();
console.log(`Files in vector store: ${status.vectorStore.fileCounts.total}`);

// List all files
const files = await openai.beta.vectorStores.files.list(vectorStore.id);
for (const file of files.data) {
  console.log(`- ${file.id}: ${file.status}`);
}

// Remove a file
await openai.beta.vectorStores.files.del(vectorStore.id, fileId);
```

### 6.4 Advanced: Priority-Based Retrieval

```typescript
// Using optional store object for granular control
interface IStore {
  priority: (file: IFile) => number;
  shouldInclude: (file: IFile) => boolean;
}

const customStore: IStore = {
  priority: (file) => {
    // Higher priority for recent files
    const age = Date.now() - file.createdAt.getTime();
    return 1 / (age + 1);
  },
  shouldInclude: (file) => {
    // Only include PDFs and docs
    return /\.(pdf|docx?)$/i.test(file.name);
  }
};

const selectorWithStore = new AgenticaOpenAIVectorStoreSelector({
  provider: { api: openai, assistant: { id }, vectorStore: { id } },
  store: customStore
});
```

---

## 7. Best Practices

### 7.1 Document Preparation

**Chunking Strategy:**
```typescript
// Split large documents into chunks
function chunkDocument(text: string, chunkSize: number = 1000): string[] {
  const chunks: string[] = [];
  const words = text.split(' ');
  
  for (let i = 0; i < words.length; i += chunkSize) {
    chunks.push(words.slice(i, i + chunkSize).join(' '));
  }
  
  return chunks;
}

// Upload with metadata
const chunks = chunkDocument(documentText);
for (let i = 0; i < chunks.length; i++) {
  await selector.attach({
    file: {
      data: Buffer.from(chunks[i]),
      name: `document_chunk_${i}.txt`
    }
  });
}
```

### 7.2 Cost Optimization

**Embeddings Cost:**
- text-embedding-3-small: $0.02 per 1M tokens
- text-embedding-3-large: $0.13 per 1M tokens

**Strategies:**
1. Use `text-embedding-3-small` for most use cases
2. Reduce dimensions when possible
3. Batch embeddings requests
4. Cache embeddings for frequently accessed documents

### 7.3 Performance Tuning

```typescript
// Batch processing
async function batchUpload(files: File[], batchSize: number = 10) {
  for (let i = 0; i < files.length; i += batchSize) {
    const batch = files.slice(i, i + batchSize);
    await Promise.all(
      batch.map(file => selector.attach({ file }))
    );
    console.log(`Uploaded batch ${i / batchSize + 1}`);
  }
}

// Parallel queries (if needed)
const queries = [
  "What is the refund policy?",
  "How long is shipping?",
  "What payment methods are accepted?"
];

const results = await Promise.all(
  queries.map(q => selector.query({ query: q }))
);
```

### 7.4 Error Handling

```typescript
try {
  await selector.attach({ file: document });
} catch (error) {
  if (error.message.includes("duplicate")) {
    console.log("File already exists (SHA-256 match)");
  } else if (error.message.includes("size limit")) {
    console.error("File too large, split into chunks");
  } else {
    console.error("Upload failed:", error);
  }
}
```

---

## 8. Alternative Implementations

### 8.1 PostgreSQL pgvector (Self-Hosted)

**Setup:**
```sql
-- Install extension
CREATE EXTENSION vector;

-- Create embeddings table
CREATE TABLE embeddings (
  id SERIAL PRIMARY KEY,
  content TEXT,
  embedding vector(1536),
  metadata JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Create index
CREATE INDEX ON embeddings 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

**TypeScript Integration:**
```typescript
import { Pool } from 'pg';
import OpenAI from 'openai';

const pool = new Pool({
  connectionString: process.env.DATABASE_URL
});

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY
});

// Store embedding
async function storeEmbedding(content: string) {
  const response = await openai.embeddings.create({
    model: "text-embedding-3-small",
    input: content
  });
  
  const embedding = response.data[0].embedding;
  
  await pool.query(
    'INSERT INTO embeddings (content, embedding) VALUES ($1, $2)',
    [content, JSON.stringify(embedding)]
  );
}

// Search similar
async function searchSimilar(query: string, limit: number = 5) {
  const response = await openai.embeddings.create({
    model: "text-embedding-3-small",
    input: query
  });
  
  const queryEmbedding = response.data[0].embedding;
  
  const result = await pool.query(`
    SELECT content, metadata,
      1 - (embedding <=> $1::vector) as similarity
    FROM embeddings
    ORDER BY embedding <=> $1::vector
    LIMIT $2
  `, [JSON.stringify(queryEmbedding), limit]);
  
  return result.rows;
}
```

---

## 9. Comparison Table

### Vector Storage Options

| Feature | OpenAI Vector Store | pgvector | Pinecone | Chroma |
|---------|-------------------|----------|----------|--------|
| **WrtnLabs Support** | ✅ Official | 🟡 Possible | 🟡 Possible | 🟡 Possible |
| **Self-Hosted** | ❌ No | ✅ Yes | ❌ No | ✅ Yes |
| **Cost** | API usage | Free (infra) | $$$ | Free |
| **Setup Complexity** | Low | Medium | Low | Medium |
| **Scalability** | High | Medium | Very High | Medium |
| **Integration** | Native | Custom | Custom | Custom |

### Embeddings Options

| Provider | Model | Dimensions | Cost/1M | Quality |
|----------|-------|------------|---------|---------|
| **OpenAI** | text-embedding-3-large | 3072 | $0.13 | ⭐⭐⭐⭐⭐ |
| **OpenAI** | text-embedding-3-small | 1536 | $0.02 | ⭐⭐⭐⭐ |
| **Cohere** | embed-english-v3.0 | 1024 | $0.10 | ⭐⭐⭐⭐ |
| **Local** | all-mpnet-base-v2 | 768 | Free | ⭐⭐⭐ |

---

## 10. Summary

### What WrtnLabs Uses (Official):

✅ **Vector Storage:** OpenAI Vector Store (native integration)  
✅ **Embeddings:** OpenAI text-embedding-3-large  
✅ **Integration:** Via @agentica/openai-vector-store package  
✅ **Features:** SHA-256 deduplication, automatic file management  

### What's Possible (Custom):

🟡 **pgvector** - Self-hosted, already uses PostgreSQL  
🟡 **Pinecone** - Cloud-native, high-scale  
🟡 **Chroma** - Local vector database  
🟡 **Cohere/Local embeddings** - Alternative providers  

### Recommendation:

For most users: **Stick with OpenAI Vector Store** (official, integrated, maintained)

For self-hosted: **pgvector** (natural fit with existing PostgreSQL)

---

**Document Version:** 1.0  
**Last Updated:** November 14, 2025  
**Maintained By:** Codegen Analysis System  
**Repository:** https://github.com/Zeeeepa/analyzer

