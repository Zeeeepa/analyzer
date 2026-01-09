# 🎯 Iris - AI-Guided LLM Optimization

**Talk naturally to Claude or Gemini. They handle everything.**

## What is Iris?

Iris makes Claude or Gemini your personal optimization guide. You just talk - they handle DSPy, Ax, local LLMs, configs, and all the technical stuff behind the scenes.

```
You: "Help me optimize my prompts"
Iris: "I scanned your project. Found 3 AI components. 
       The summarizer could improve 20%. Ready to start?"
```

**No ML expertise needed. No CLI commands to learn. Just conversation.**

---

## ⚡ Quick Start (30 seconds)

### Step 1: Install

```bash
npm install @foxruv/iris
```

This automatically creates agent + skill files in `.claude/`

### Step 2: Talk to Claude

```
Read .claude/agents/iris.md and help me optimize my AI
```

**That's it.** Claude becomes Iris and walks you through everything.

---

## 🎯 What You Can Say

| You Say | What Happens |
|---------|--------------|
| "Help me optimize my prompts" | Iris scans, recommends, optimizes |
| "Make my AI responses better" | DSPy prompt optimization |
| "Find the best temperature setting" | Ax Bayesian hyperparameter tuning |
| "Set up local LLM" | Configures Ollama with cloud fallback |
| "Learn from my usage patterns" | Enables federated learning |
| "What should I optimize first?" | Scans codebase, prioritizes targets |

**You never run commands.** Iris does everything silently.

---

## 🔧 What Iris Does (Behind the Scenes)

You don't need to know this, but here's what Iris handles for you:

| Feature | What It Means |
|---------|---------------|
| **DSPy Optimization** | Automatically improves your prompts with few-shot learning |
| **Ax Bayesian Tuning** | Finds optimal temperature, top_p, max_tokens (352x faster than grid search) |
| **Local LLM Support** | Works with Ollama, llama.cpp, vLLM |
| **Cloud Fallback** | Uses Claude/GPT/Gemini when local isn't available |
| **Federated Learning** | Learns from patterns across projects (anonymized) |
| **AgentDB Tracking** | Remembers what works, improves over time |

---

## 📁 What Gets Installed

After `npm install`, you have:

```
.claude/
├── agents/iris.md    ← Claude reads this to become Iris
└── skills/iris.md    ← Detailed commands & workflows (for Claude, not you)
```

**First optimization creates:**

```
.iris/
├── config.yaml       ← Your settings
├── learning/         ← Patterns & history
├── agentdb/          ← Decision tracking
└── telemetry/        ← Local metrics
```

---

## 💬 Example Conversation

```
You: Read .claude/agents/iris.md and help me optimize

Iris: Welcome! Let me scan your project...

      📁 Project Type: TypeScript/React
      🎯 Found 3 AI components
      📊 Best candidate: src/summarize.ts (most used)
      
      Ready to start?

You: Yes

Iris: Setting up optimization... ✅ Done
      
      I need 5-10 examples to learn from:
      - Input: What you send to the AI
      - Output: What you want back

You: [provides examples]

Iris: 🎉 Optimization complete!
      
      - Accuracy: 72% → 89% (+17%)
      - Speed: 450ms → 380ms (16% faster)
      
      Want me to apply these changes?
```

---

## 🌐 Federated Learning (Optional)

Say "enable federated learning" and Iris will:

- Share anonymized patterns with the community
- Learn from what works across projects
- Make your AI smarter over time

**Your code and data are never shared** - only optimization patterns.

---

## 🔌 Optional: MCP Integration

For advanced users who want tool-based integration:

```bash
# Add to Claude Desktop or Cursor
claude mcp add iris npx @foxruv/iris@latest mcp start
```

But most users just talk to Claude directly - it's simpler.

---

## 📚 More Resources

- **claude-flow:** <https://github.com/ruvnet/claude-flow>
- **agentic-flow:** <https://github.com/ruvnet/agentic-flow>  
- **agentdb:** <https://github.com/ruvnet/agentdb>

---

## 🆘 Need Help?

Just ask Claude:

```
Read .claude/agents/iris.md - I'm stuck on [your issue]
```

Iris will help you troubleshoot.

---

**Ready to optimize?** Install and start talking! 🚀
