# Iris Optimization Skill

## Context
This project has the `@foxruv/iris` optimization engine installed. This engine provides a pluggable architecture for hyperparameter and prompt optimization, prioritizing:
1. **Ax (Bayesian Optimization)** - For numeric/structural parameters.
2. **DSPy (MIPROv2)** - For prompt/LLM optimization.
3. **Grid Search** - For simple fallbacks.

## Your Role
When the user mentions "optimization", "tuning", or "improving performance", you must:

1. **Analyze the Target:**
   - Identify the script or function needing optimization.
   - Look for an exported `evaluate(params)` function.

2. **Check Configuration (`iris-config.yaml`):**
   - If no config exists, propose creating one using the template below.
   - Respect the `strategy` order (default: `['ax', 'dspy', 'grid']`).

3. **Select the Strategy:**
   - **Prefer Ax** if the project has a Python environment and numeric parameters.
   - **Prefer DSPy** if optimizing prompts/text.
   - **Use Grid** if the search space is small (<20 combinations) or dependencies are missing.

4. **Execute:**
   - Use the CLI: `npx iris optimize --config <config.yaml> --target <script.ts>`
   - Do NOT write custom optimization loops unless the CLI is insufficient.

## Configuration Template
```yaml
optimization:
  strategy: ['ax', 'grid']
  searchSpace:
    parameters:
      - name: "learning_rate"
        type: "range"
        bounds: [0.0001, 0.1]
        log_scale: true
```

## Dependency Check
Before running Ax or DSPy, verify dependencies:
- Ax: `pip install ax-platform` (Python service must be running).
- DSPy: `pip install dspy-ai`.
