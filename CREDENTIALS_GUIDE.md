# 🔑 Credentials Guide - What's Required vs Optional

## ✅ What You DON'T Need (Common Confusion)

### ❌ Supabase for Iris Telemetry
**You do NOT need Supabase credentials for basic Iris operation.**

**Why?** Iris telemetry works like this:
```
Your Code → AgentDB (local SQLite) → POST webhook → iris-prime-api.vercel.app
                                                      ↓
                                                  Supabase (FoxRuv's hosted instance)
```

The POST webhook is **keyless** - it auto-detects your project context and sends it to FoxRuv's API.

### When DO You Need Supabase?

**ONLY if you want:**
1. **Cross-project federation** - Your trading bot learning from your NFL predictor
2. **Direct Supabase writes** - Writing to YOUR OWN Supabase instance (not FoxRuv's)

If you just want Iris to learn from your code and optimize itself, **you don't need any Supabase credentials**.

---

## 🎯 What's Actually Required

### For Iris Core Features (No API Keys)

**Required:**
- `PROJECT_ID=trading-platform` (in .env)
- `IRIS_AUTO_INVOKE=true` (optional, enables auto-optimization)

**That's it!** Iris will:
- ✅ Track decisions in local AgentDB
- ✅ Learn patterns
- ✅ Run AI Council
- ✅ Optimize experts
- ✅ Send anonymous telemetry to FoxRuv API

### For Optional Federation (Cross-Project Learning)

**Only if you want your projects to learn from each other:**

```bash
# Add to .env
FOXRUV_SUPABASE_URL=your_foxruv_provided_url
FOXRUV_SUPABASE_SERVICE_ROLE_KEY=your_foxruv_provided_key
FOXRUV_PROJECT_ID=trading-platform
```

**Note:** These are FoxRuv-provided credentials for federated learning, not your own Supabase project.

---

## 📦 MCP Skills Credentials

### No API Key Required ✅

- **filesystem-with-morph** - Ready to use immediately
- **mcp-manager** - Meta-skill, no credentials

### API Key Required 🔑

#### Context7
```bash
CONTEXT7_API_KEY=your_key_here
```
Get from: https://context7.com/dashboard

#### VectorCode
```bash
VECTORCODE_API_KEY=your_key_here
```
Get from: https://vectorcode.ai/api-keys

#### Supabase (YOUR project, not FoxRuv's)
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```
Get from: Supabase Dashboard → Settings → API

#### Neo4j
```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
```
Or use Neo4j AuraDB (cloud)

---

## 🚀 Quick Setup (Minimal)

**For just Iris core features (no MCPs):**

```bash
cd /home/iris/code/tradin-platform

# Add to .env
echo "PROJECT_ID=trading-platform" >> .env
echo "IRIS_AUTO_INVOKE=true" >> .env

# That's it! No other credentials needed.
```

**Test it:**
```bash
npx iris config show
npx iris discover --project .
```

---

## 🔐 .env Template (Full)

```bash
# ============================================
# IRIS CORE (Required for basic operation)
# ============================================
PROJECT_ID=trading-platform
IRIS_AUTO_INVOKE=true

# ============================================
# IRIS FEDERATION (Optional - cross-project learning)
# ============================================
# Only add these if FoxRuv provides them for federation
# FOXRUV_SUPABASE_URL=
# FOXRUV_SUPABASE_SERVICE_ROLE_KEY=
# FOXRUV_PROJECT_ID=trading-platform

# ============================================
# MCP SKILLS (Optional - only add what you use)
# ============================================

# Context7 (semantic code search)
# CONTEXT7_API_KEY=

# VectorCode (vector embeddings search)
# VECTORCODE_API_KEY=

# Supabase (YOUR database, not FoxRuv's)
# SUPABASE_URL=
# SUPABASE_SERVICE_ROLE_KEY=

# Neo4j (graph database)
# NEO4J_URI=bolt://localhost:7687
# NEO4J_USERNAME=neo4j
# NEO4J_PASSWORD=

# ============================================
# TRADING PLATFORM (Existing)
# ============================================
JWT_SECRET=your_jwt_secret
ALPACA_API_KEY=your_alpaca_key
ALPACA_API_SECRET=your_alpaca_secret
AGENTDB_PATH=./data/agentdb
```

---

## 🐛 Fixing Common Warnings

### Warning: "Supabase credentials not configured"

**This is OK!** It's just informing you that federation is disabled. Iris still works perfectly.

**To silence it:** This warning shouldn't block anything. If it's annoying, you can ignore it.

**To enable federation:** Get FoxRuv federation credentials and add them.

### Warning: "enable_supabase: false"

**This is correct!** Unless you're using federation, this should be false.

---

## 📊 What Works Without Any Extra Credentials

With just `PROJECT_ID` and `IRIS_AUTO_INVOKE`:

✅ AgentDB tracking (local SQLite)
✅ Pattern discovery
✅ AI Council decisions
✅ Expert rotation
✅ Drift detection
✅ Auto-optimization
✅ Keyless telemetry to FoxRuv API
✅ Iris health checks
✅ Iris evaluation
✅ All CLI commands

---

## 🎯 Summary

**Minimum to get started:**
```bash
PROJECT_ID=trading-platform
IRIS_AUTO_INVOKE=true
```

**Add MCPs only when you need them.**

**Add federation only if you want cross-project learning.**

**Everything else is optional!**
