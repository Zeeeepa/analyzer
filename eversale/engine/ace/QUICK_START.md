# ACE Quick Start Guide

## 🚀 Get Started in 30 Seconds

### 1. Initialize Playbook (one-time setup)

```bash
# Copy starter strategies to runtime playbook
cp ace/starter_playbook.yaml ace/playbook.yaml
```

### 2. Use the Agent (ACE enabled by default)

```python
from agent.brain import SDRAgent

agent = SDRAgent()  # ACE enabled by default
await agent.initialize()

# Agent automatically learns from tasks
result = await agent.run("Find LinkedIn contacts for AI startups")
```

That's it! The agent now learns from experience.

---

## 📖 Common Operations

### Inspect Playbook

```python
from ace.playbook import Playbook

playbook = Playbook()
stats = playbook.get_stats()

print(f"Total strategies: {stats['total_strategies']}")
print(f"Avg success: {stats['avg_success_rate']:.1%}")
```

### Query Strategies for Context

```python
strategies = playbook.query_strategies(
    domain="linkedin.com",
    action_type="search",
    limit=5
)

for s in strategies:
    print(f"[{s.marker}] {s.strategy} ({s.success_rate:.0%})")
```

### Add Custom Strategy

```python
playbook.add_strategy(
    domain="linkedin.com",
    action_type="search",
    strategy="Use Boolean operators for advanced search",
    marker="✓"
)
playbook.save()
```

### Disable ACE (for benchmarking)

```python
agent = SDRAgent(enable_ace=False)
```

### Reset to Starter Playbook

```bash
# Backup current learning
cp ace/playbook.yaml ace/playbook.backup.yaml

# Restore defaults
cp ace/starter_playbook.yaml ace/playbook.yaml
```

---

## 🧪 Verify Installation

```bash
# Run test suite (should see all ✅)
python3 test_ace.py

# Run interactive demo
python3 examples/ace_demo.py
```

---

## 📊 What You Get

### 29 Pre-built Strategies

- **LinkedIn** (7): Search optimization, contact extraction, popup handling
- **Facebook Ads** (5): Country selection, filtering, advertiser extraction
- **Apollo** (4): Email verification, export workflows, filtering
- **General** (13): Cookie popups, error recovery, rate limits, validation

### Automatic Learning

After each task, the agent:
1. Analyzes what worked and what didn't
2. Extracts novel strategies
3. Updates playbook with success tracking
4. Prunes low-value patterns

### Minimal Overhead

- **0ms** for simple actions (click, type, scroll)
- **~40ms** for complex actions (search, extract)
- **<10%** token increase
- **<50KB** playbook size

---

## 🎯 Key Concepts

### Strategy Markers

- `✓` **Helpful** - Proven to work, use this approach
- `✗` **Harmful** - Known to fail, avoid this
- `○` **Neutral** - Contextual observation

### Action Classification

**Complex** (ACE strategies applied):
- search, extract_contacts, fill_form, handle_popup, handle_error

**Simple** (ACE skipped for speed):
- click, type, scroll, wait, screenshot

### Success Tracking

Each strategy tracks:
- `success_count`: Number of times it helped
- `failure_count`: Number of times it failed
- `success_rate`: Calculated percentage
- `created_at`, `last_used`: Timestamps

---

## 💡 Best Practices

### DO:
✅ Let ACE run for 10-20 tasks to build domain knowledge
✅ Review playbook periodically: `playbook.get_stats()`
✅ Prune manually if needed: `playbook.prune_low_value_strategies()`
✅ Back up your playbook before major changes

### DON'T:
❌ Disable ACE unless benchmarking (you lose learning benefits)
❌ Manually edit playbook.yaml (use the API instead)
❌ Expect instant expertise (strategies improve over time)
❌ Add duplicate strategies (deduplication is automatic)

---

## 🔍 Monitoring

Watch logs for ACE activity:

```
INFO  | ACE enabled: 29 strategies loaded          # Startup
DEBUG | Injected 5 strategies for linkedin.com     # During task
INFO  | ACE learned 2 new strategies               # After task
INFO  | Pruned 3 low-value strategies              # Every 10 tasks
```

Enable verbose mode:

```python
agent = SDRAgent(verbose=True)
```

---

## 🆘 Troubleshooting

**Q: Agent isn't learning new strategies**
```bash
# Check if reflection is running
grep "ACE learned" logs/agent.log

# Verify ACE is enabled
python3 -c "from agent.brain import SDRAgent; a=SDRAgent(); print(a.enable_ace)"
```

**Q: Playbook file is missing**
```bash
# Recreate from starter
cp ace/starter_playbook.yaml ace/playbook.yaml
```

**Q: Too many strategies, performance degrading**
```python
# Prune aggressively
playbook.prune_low_value_strategies(min_success_rate=0.5, min_usage_count=5)
playbook.save()
```

**Q: Want to see what strategies are being used**
```python
# Enable debug logging
import logging
logging.getLogger('ace').setLevel(logging.DEBUG)
```

---

## 📚 Learn More

- **Full Documentation**: `ace/README.md`
- **Integration Details**: `ACE_INTEGRATION.md`
- **Test Suite**: `test_ace.py`
- **Interactive Demo**: `examples/ace_demo.py`
- **Original ACE**: https://github.com/kayba-ai/agentic-context-engine

---

## 🎓 Example Workflow

```python
from agent.brain import SDRAgent
from ace.playbook import Playbook

# Initialize agent with ACE
agent = SDRAgent(verbose=True)
await agent.initialize()

# Run some tasks (agent learns automatically)
await agent.run("Find 5 AI startup founders on LinkedIn")
await agent.run("Search Facebook Ad Library for competitor ads")
await agent.run("Extract contacts from Apollo for SaaS companies")

# Check what was learned
playbook = Playbook()
stats = playbook.get_stats()
print(f"Agent now knows {stats['total_strategies']} strategies")
print(f"Average success: {stats['avg_success_rate']:.1%}")

# Query learned patterns
linkedin_tips = playbook.query_strategies("linkedin.com", "search")
for tip in linkedin_tips:
    print(f"  • {tip.strategy}")

# Agent is now smarter for future tasks!
```

---

**Ready to go!** Your agent will now learn from every task and continuously improve. 🎉
