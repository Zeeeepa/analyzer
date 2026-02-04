# Project Context for Gemini

This file provides context and rules for Gemini to interact with this project.



# Gemini Optimization Protocol

## System Capabilities
You are interacting with a project enabled with the `@foxruv/iris` Optimization Engine. This engine allows you to autonomously tune hyperparameters and prompts using:
- **Ax** (Bayesian Optimization)
- **DSPy** (Prompt Optimization)
- **Grid Search** (Fallback)

## Your Optimization Mandate
If the user asks to "optimize", "tune", or "improve" any component:

1.  **Discovery Phase:**
    *   Scan the codebase for the target script.
    *   Verify if it exports an `evaluate(params)` function.
    *   Check for `iris-config.yaml`. If missing, generate one using the standard template.

2.  **Strategy Selection (Strict Priority):**
    *   **Priority 1: Ax.** Check if `ax-platform` is installed and the Python service is running. If yes, configure `iris-config.yaml` to use `['ax', 'grid']`.
    *   **Priority 2: DSPy.** If optimizing text/prompts, check for `dspy-ai`. Use `['dspy', 'grid']`.
    *   **Priority 3: Grid Search.** Use this if dependencies are missing or the search space is small.

3.  **Execution:**
    *   Construct the CLI command: `npx iris optimize --config <config> --target <script>`
    *   Run the command using your shell tool.
    *   Analyze the JSON output (Best Score/Configuration).

4.  **Refinement:**
    *   If the score is unsatisfactory, propose widening the search bounds in `iris-config.yaml` and re-running.

## Config Reference
```yaml
optimization:
  strategy: ['ax', 'dspy', 'grid']
  searchSpace:
    parameters:
      - name: "param_x"
        type: "range"
        bounds: [0, 10]
```
