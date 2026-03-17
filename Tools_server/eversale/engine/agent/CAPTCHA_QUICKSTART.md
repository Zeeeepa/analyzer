# CAPTCHA Dual-LLM Confidence Scoring - Quick Start

## 30-Second Overview

The CAPTCHA solver now uses **two AI models** to decide whether to auto-solve or ask for human help:

1. **Vision Model** (moondream) → Reads the CAPTCHA image → Image confidence
2. **Text Model** (qwen2.5) → Validates the answer → Context confidence
3. **Combined Score** → Smart decision: auto-solve (≥75%) or human fallback (<75%)

**Result**: Fewer failed attempts, faster solving, less human intervention needed.

## Basic Usage

```python
from agent.captcha_solver import LocalCaptchaSolver
import ollama

# Initialize solver
solver = LocalCaptchaSolver(vision_model="moondream")

# Solve with dual-LLM confidence
result = await solver.solve_image_with_vision(
    page=page,
    ollama_client=ollama,
    captcha_type="text"
)

# Check result
if result:
    print(f"Answer: {result['answer']}")
    print(f"Confidence: {result['confidence']:.0%}")
    print(f"Decision: {result['decision']}")

    # Submit if confidence is good
    if result['confidence'] >= 0.75:
        await submit_captcha(result['answer'])
else:
    print("Low confidence - asking human for help")
    await show_browser_popup()
```

## What Changed?

### Before (Old System)
```python
# Single vision model
result = await solver.solve_image_with_vision(page, ollama)

# Simple confidence (0-1)
if result['confidence'] >= 0.5:
    submit(result['answer'])  # Often failed!
```

### After (New System)
```python
# Dual-LLM: vision + text validation
result = await solver.solve_image_with_vision(page, ollama)

# Smart confidence with 4 tiers
if result['confidence'] >= 0.85:
    submit(result['answer'])  # HIGH confidence
elif result['confidence'] >= 0.75:
    submit(result['answer'])  # GOOD confidence (retry if fails)
elif result['confidence'] >= 0.50:
    submit_once_then_fallback()  # MEDIUM (try once)
else:
    show_browser_popup()  # LOW (human help)
```

## Key Improvements

| Feature | Before | After |
|---------|--------|-------|
| **Confidence Calculation** | Vision only | Vision (60%) + Text validation (30%) + Format (10%) |
| **Decision Thresholds** | Binary (>0.5) | 4-tier (85%, 75%, 50%, <50%) |
| **Validation** | None | Text model checks answer quality |
| **Metrics** | None | Tracks success rate by confidence level |
| **False Positives** | High | Low (validated answers only) |

## Confidence Tiers Explained

```
≥85% HIGH    → Auto-solve immediately (trust vision + validation)
75-85% GOOD  → Auto-solve, retry if fails (pretty confident)
50-75% MEDIUM → Try once, then ask human (not sure)
<50% LOW     → Ask human immediately (no point trying)
```

## Real Example

```python
# Vision model sees: "Abc123"
image_confidence = 0.95  # Clear text, good length

# Text model validates: "Valid 6-char alphanumeric"
context_confidence = 0.90  # Makes sense for text CAPTCHA

# Combined: (0.95 × 0.6) + (0.90 × 0.3) + 0.1 = 0.94
combined_confidence = 0.94

# Decision: ≥0.85 = HIGH confidence
# Action: Submit immediately ✓
```

## Common Scenarios

### Scenario 1: Clean CAPTCHA (Auto-Solve)
```
Vision: "Test42" (clear image)
Validation: "Valid text+number combo"
Confidence: 0.94 (HIGH)
→ Auto-submit immediately
```

### Scenario 2: Unclear CAPTCHA (Human Help)
```
Vision: "I cannot read this text clearly" (refusal)
Validation: "Contains error phrase, invalid"
Confidence: 0.15 (LOW)
→ Show browser for human solve
```

### Scenario 3: Borderline (Try Once)
```
Vision: "Xy9" (short but plausible)
Validation: "Unusually short, possibly valid"
Confidence: 0.68 (MEDIUM)
→ Submit once, if fails → human help
```

## Metrics & Analytics

```python
# Track success rates
solver.record_solve_result(success=True)

# Get summary
summary = solver.get_metrics_summary()

print(f"Total attempts: {summary['total_attempts']}")
for level, stats in summary['by_confidence'].items():
    print(f"{level}: {stats['success_rate']:.0%} success")

# Output:
# Total attempts: 50
# high: 90% success    ← Good!
# good: 75% success    ← Acceptable
# medium: 60% success  ← Expected
# low: 0% success      ← Correctly rejected
```

## Advanced: Custom Text Model

```python
# Use different validation model
result = await solver.solve_image_with_vision(
    page=page,
    ollama_client=ollama,
    vision_model="moondream",
    text_model="llama3.1:8b",  # Alternative
    captcha_type="text"
)
```

## Advanced: Threshold Tuning

```python
# After 50+ attempts, check recommendations
summary = solver.get_metrics_summary()

if summary['recommendations']:
    for rec in summary['recommendations']:
        print(f"💡 {rec}")

# Example output:
# 💡 Medium confidence success rate is high (>80%).
#    Consider lowering acceptance threshold.
```

## Integration with Amazon

```python
from agent.captcha_solver import AmazonCaptchaHandler

handler = AmazonCaptchaHandler(page)

# Dual-LLM automatically enabled
success = await handler.solve_amazon_captcha(
    manual_fallback=True,
    vision_model="moondream"
)

# Logs show:
# [AMAZON] Vision result: Abc123
# [AMAZON] Combined confidence: 0.94 (image: 0.95, context: 0.90)
# [AMAZON] Decision: Auto-solve: HIGH confidence (≥85%)
# [AMAZON] CAPTCHA solved via vision (moondream)!
```

## Troubleshooting

### "Context validation failed" errors
```python
# Make sure text model is installed
ollama pull qwen2.5:7b-instruct

# Or use alternative
text_model="llama3.1:8b"
```

### Low confidence scores
```python
# Check image quality
# - Is CAPTCHA too distorted?
# - Is vision model struggling?
# → Try larger model: llava:7b instead of moondream

result = await solver.solve_image_with_vision(
    page=page,
    ollama_client=ollama,
    vision_model="llava:7b",  # More accurate
    captcha_type="text"
)
```

### Too many human fallbacks
```python
# Check metrics
summary = solver.get_metrics_summary()

# If medium confidence has high success (>80%):
# → Lower threshold from 0.75 to 0.70
# Edit: captcha_solver.py → _make_solving_decision()
```

## Files & Documentation

| File | Purpose |
|------|---------|
| `agent/captcha_solver.py` | Main implementation |
| `agent/CAPTCHA_CONFIDENCE_SCORING.md` | Full documentation |
| `agent/CAPTCHA_FLOW_DIAGRAM.md` | Visual flow diagrams |
| `agent/CAPTCHA_QUICKSTART.md` | This guide |
| `test_captcha_confidence.py` | Test script |
| `~/.eversale/captcha_metrics.jsonl` | Metrics log |

## Test It Out

```bash
# Run test to see it in action
python3 test_captcha_confidence.py

# Check metrics
cat ~/.eversale/captcha_metrics.jsonl | tail -5 | python3 -m json.tool
```

## Key Takeaways

✅ **Vision model** (moondream) reads the CAPTCHA image
✅ **Text model** (qwen2.5) validates the answer quality
✅ **Combined confidence** decides: auto-solve or human help
✅ **4 tiers**: HIGH (≥85%), GOOD (75-85%), MEDIUM (50-75%), LOW (<50%)
✅ **Metrics tracking** enables threshold tuning over time

**Bottom line**: Smarter CAPTCHA solving with fewer failures! 🎯
