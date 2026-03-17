# Dual-LLM CAPTCHA Confidence Scoring System

## Overview

The CAPTCHA solver now uses a **dual-LLM confidence scoring system** to intelligently decide when to auto-solve vs. fallback to human intervention. This dramatically improves success rates and reduces wasted attempts on low-quality answers.

## How It Works

### 1. Vision Model Analysis (Image Confidence)

**Models**: moondream (2.8B), llava:7b, llama3.2-vision

The vision model analyzes the CAPTCHA image and returns:
- Answer (extracted text/result)
- Image confidence (0.0-1.0)

**Factors affecting image confidence**:
- Answer length (text CAPTCHAs typically 3-10 chars)
- Raw answer quality (extra text = lower confidence)
- Ambiguous characters (O/0, I/l/1)
- LLM artifacts (refusal phrases like "sorry", "cannot")

**Example**:
```
Image: Distorted text "Abc123"
Vision answer: "Abc123"
Image confidence: 0.9 (clean answer, good length)
```

### 2. Text Model Validation (Context Confidence)

**Models**: qwen2.5:7b-instruct (default), llama3.1:8b

The text model validates the vision model's answer by analyzing:
- Does the answer format match the CAPTCHA type?
- Is the answer plausible (not gibberish)?
- Any red flags (too long, contains errors)?

**Example prompt**:
```
CAPTCHA Type: text
Vision Model Answer: Abc123
Image Description: Distorted text with moderate clarity
Raw Output: Abc123

Questions:
1. Does the answer format match the expected CAPTCHA type?
2. Is the answer plausible (not gibberish)?
3. Any red flags?

Return JSON: {"valid": true, "confidence": 0.85, "reason": "Valid 6-char alphanumeric"}
```

**Context validation returns**:
- valid: bool (does it pass validation?)
- confidence: 0.0-1.0 (how confident in this assessment?)
- reason: str (explanation)

### 3. Combined Confidence Score

**Formula**:
```
combined = (image_confidence × 0.6) + (context_confidence × 0.3) + format_bonus

Penalties:
- Answer too long (>10 chars): -20%
- Context validation failed: -25%

Bounds: 0.0 ≤ combined ≤ 1.0
```

**Weights**:
- Image confidence: 60% (primary signal)
- Context confidence: 30% (validation)
- Format validity: 10% (bonus for correct format)

**Example**:
```
Image confidence: 0.90
Context confidence: 0.85
Answer length: 6 chars (valid)
Context valid: true

Combined = (0.90 × 0.6) + (0.85 × 0.3) + 0.1 = 0.94
```

### 4. Decision Thresholds

| Confidence | Action | Behavior |
|------------|--------|----------|
| **≥85%** | Auto-solve immediately | High confidence, submit now |
| **75-85%** | Auto-solve with retry | Good confidence, retry if fails |
| **50-75%** | Try once, then fallback | Medium confidence, single attempt |
| **<50%** | Human fallback | Low confidence, skip auto-solve |

**Decision logic**:
```python
if confidence >= 0.85:
    return "Auto-solve: HIGH confidence"
elif confidence >= 0.75:
    return "Auto-solve: GOOD confidence, will retry if fails"
elif confidence >= 0.50:
    return "Try once: MEDIUM confidence"
else:
    return "Skip: LOW confidence, human fallback recommended"
```

## Usage

### Basic Usage

```python
from agent.captcha_solver import LocalCaptchaSolver
import ollama

solver = LocalCaptchaSolver(vision_model="moondream")
ollama_client = ollama

# Solve with dual-LLM confidence scoring
result = await solver.solve_image_with_vision(
    page=page,
    ollama_client=ollama_client,
    vision_model="moondream",
    text_model="qwen2.5:7b-instruct",  # NEW: context validation model
    captcha_type="text"
)

if result:
    print(f"Answer: {result['answer']}")
    print(f"Combined confidence: {result['confidence']:.2f}")
    print(f"Image confidence: {result['image_confidence']:.2f}")
    print(f"Context confidence: {result['context_confidence']:.2f}")
    print(f"Decision: {result['decision']}")
else:
    print("Confidence too low, falling back to human")
```

### With Amazon CAPTCHA Handler

```python
from agent.captcha_solver import AmazonCaptchaHandler

handler = AmazonCaptchaHandler(page)

# Automatically uses dual-LLM scoring
success = await handler.solve_amazon_captcha(
    manual_fallback=True,
    vision_model="moondream"
)

if success:
    print("CAPTCHA solved (auto or manual)")
```

### Tracking Metrics

```python
# Record actual result after submission
solver.record_solve_result(success=True)  # or False if failed

# Get metrics summary
summary = solver.get_metrics_summary()

print(f"Total attempts: {summary['total_attempts']}")
print("\nBy confidence level:")
for level, stats in summary['by_confidence'].items():
    print(f"  {level}: {stats['success_rate']:.1%} success rate")

# Check recommendations
if summary['recommendations']:
    print("\nRecommendations:")
    for rec in summary['recommendations']:
        print(f"  - {rec}")
```

## Metrics & Logging

### What Gets Logged

Every CAPTCHA solve attempt logs:
- Timestamp
- CAPTCHA type (text/math/image_selection)
- Combined confidence (0.0-1.0)
- Image confidence (0.0-1.0)
- Context confidence (0.0-1.0)
- Model used (moondream/llava/etc)
- Answer length
- Accepted (bool - whether attempt was accepted)
- Actual success (bool - whether CAPTCHA was actually solved)

### Log Location

**File**: `~/.eversale/captcha_metrics.jsonl`

**Format**: JSON Lines (one JSON object per line)

**Example**:
```json
{
  "timestamp": 1765165584.08,
  "captcha_type": "text",
  "combined_confidence": 0.94,
  "image_confidence": 0.95,
  "context_confidence": 0.90,
  "model": "moondream",
  "answer_length": 6,
  "accepted": true,
  "actual_success": true
}
```

### Metrics Summary

```python
summary = solver.get_metrics_summary()
```

**Output**:
```python
{
    "total_attempts": 10,
    "by_confidence": {
        "high": {"attempts": 3, "successes": 3, "success_rate": 1.0},
        "good": {"attempts": 4, "successes": 3, "success_rate": 0.75},
        "medium": {"attempts": 2, "successes": 1, "success_rate": 0.5},
        "low": {"attempts": 1, "successes": 0, "success_rate": 0.0}
    },
    "recommendations": [
        "Medium confidence success rate is high (>80%). Consider lowering acceptance threshold."
    ]
}
```

## Model Recommendations

### Vision Models (Primary Analysis)

| Model | Size | Speed | Accuracy | Use Case |
|-------|------|-------|----------|----------|
| **moondream** | 2.8B | Fast | Good | Default, best balance |
| **llava:7b** | 7B | Slow | Better | Complex CAPTCHAs |
| **llama3.2-vision** | 1B | Fastest | Decent | Fallback option |

**Recommendation**: Start with `moondream`, fallback to `llava:7b` if needed.

### Text Models (Context Validation)

| Model | Size | Speed | Accuracy | Use Case |
|-------|------|-------|----------|----------|
| **qwen2.5:7b-instruct** | 7B | Fast | Excellent | Default, best for validation |
| **llama3.1:8b** | 8B | Medium | Good | Alternative option |

**Recommendation**: Use `qwen2.5:7b-instruct` for best results.

## Threshold Tuning

### When to Adjust Thresholds

Based on metrics summary recommendations:

**If high confidence success rate < 70%**:
- Current threshold (≥85%) is too low
- Consider raising to 90% or higher
- More false positives slipping through

**If medium confidence success rate > 80%**:
- Current threshold (50-75%) is too strict
- Consider lowering to 45% or accepting more medium attempts
- Missing good opportunities

### Custom Thresholds

Modify `_make_solving_decision()` in `captcha_solver.py`:

```python
# Before (defaults)
if combined_confidence >= 0.85:
    return ("Auto-solve: HIGH confidence", True)
elif combined_confidence >= 0.75:
    return ("Auto-solve: GOOD confidence", True)
elif combined_confidence >= 0.50:
    return ("Try once: MEDIUM confidence", True)

# After (custom tuning)
if combined_confidence >= 0.90:  # Stricter
    return ("Auto-solve: HIGH confidence", True)
elif combined_confidence >= 0.80:  # Stricter
    return ("Auto-solve: GOOD confidence", True)
elif combined_confidence >= 0.45:  # More lenient
    return ("Try once: MEDIUM confidence", True)
```

## Example Scenarios

### Scenario 1: High Confidence (Auto-Solve)

```
Vision: "Abc123" (image_conf=0.95)
Context: valid=true, conf=0.90, reason="Valid 6-char alphanumeric"
Combined: 0.94

Decision: "Auto-solve: HIGH confidence (≥85%)"
Action: Submit immediately
```

### Scenario 2: Good Confidence (Retry on Fail)

```
Vision: "Test42" (image_conf=0.80)
Context: valid=true, conf=0.75, reason="Plausible text+number mix"
Combined: 0.80

Decision: "Auto-solve: GOOD confidence (75-85%), will retry if fails"
Action: Submit, retry with different model if fails
```

### Scenario 3: Medium Confidence (Single Attempt)

```
Vision: "Xy9z" (image_conf=0.70)
Context: valid=true, conf=0.60, reason="Short but plausible"
Combined: 0.70

Decision: "Try once: MEDIUM confidence (50-75%)"
Action: Submit once, then human fallback
```

### Scenario 4: Low Confidence (Human Fallback)

```
Vision: "Sor1y I cannot read this unclear text" (image_conf=0.40)
Context: valid=false, conf=0.35, reason="Contains refusal phrase"
Combined: 0.00

Decision: "Skip: LOW confidence (<50%), human fallback recommended"
Action: Show browser popup for human solve
```

### Scenario 5: Penalty Example (Too Long)

```
Vision: "ThisIsWayTooLongForACaptcha" (image_conf=0.90)
Context: valid=true, conf=0.85, reason="Valid format but unusual length"
Answer length: 28 chars
Combined: 0.90×0.6 + 0.85×0.3 + 0.1 - 0.2 (length penalty) = 0.59

Decision: "Try once: MEDIUM confidence (50-75%)"
Action: Submit once, likely to fail due to length
```

## Testing

Run the test script to verify the system:

```bash
python3 test_captcha_confidence.py
```

**Expected output**:
- 6 test scenarios demonstrating different confidence levels
- Metrics summary showing attempts by confidence level
- Recommendations based on historical data
- Log file created at `~/.eversale/captcha_metrics.jsonl`

## Benefits

1. **Higher Success Rate**: Only auto-solve when confidence is high
2. **Fewer Wasted Attempts**: Skip low-confidence answers
3. **Faster Fallback**: Immediately go to human when needed
4. **Data-Driven**: Metrics inform threshold tuning
5. **Transparent**: See exact confidence scores and decision reasoning
6. **Self-Improving**: Track success rates to adjust thresholds over time

## Implementation Details

### Key Methods

**`solve_image_with_vision()`** - Main solver with dual-LLM scoring
- Takes screenshot
- Vision model extracts answer
- Text model validates answer
- Calculates combined confidence
- Makes decision based on thresholds

**`_calculate_image_confidence()`** - Vision model confidence
- Analyzes answer quality
- Checks for artifacts
- Returns 0.0-1.0

**`_validate_with_context()`** - Text model validation
- Sends context prompt to text model
- Parses JSON response
- Returns valid/confidence/reason

**`_calculate_combined_confidence()`** - Combines scores
- Weighted average (60/30/10)
- Applies penalties
- Returns 0.0-1.0

**`_make_solving_decision()`** - Threshold-based decision
- Maps confidence to action
- Returns (decision_message, should_accept)

**`_log_solve_attempt()`** - Metrics tracking
- Logs to memory and file
- Tracks by confidence level
- Enables threshold tuning

**`record_solve_result()`** - Post-submission tracking
- Updates success metrics
- Corrects false positives
- Improves accuracy over time

**`get_metrics_summary()`** - Analytics
- Success rates by confidence level
- Recommendations for threshold tuning
- Historical trend analysis

## Future Improvements

1. **Adaptive Thresholds**: Automatically adjust based on success rates
2. **Per-Site Calibration**: Different thresholds for Amazon vs LinkedIn
3. **Model Ensemble**: Average predictions from multiple vision models
4. **Answer Validation**: Check against expected pattern (e.g., 6 digits)
5. **Feedback Loop**: Use actual solve success to retrain confidence weights
6. **A/B Testing**: Experiment with different threshold configurations

## FAQ

**Q: Why two models instead of one?**
A: Vision models are good at OCR but not validation. Text models excel at reasoning and validation. Combining both gives best results.

**Q: Does this slow down solving?**
A: Slightly (adds ~1-2s for text model validation), but dramatically improves accuracy and reduces wasted manual solves.

**Q: What if I don't have qwen2.5 installed?**
A: System will fallback to vision-only confidence (still works, just less accurate).

**Q: Can I use different text models?**
A: Yes, pass `text_model="llama3.1:8b"` to `solve_image_with_vision()`.

**Q: How do I view historical metrics?**
A: Check `~/.eversale/captcha_metrics.jsonl` or call `solver.get_metrics_summary()`.

**Q: Should I adjust thresholds?**
A: Wait until you have 10+ attempts, then check recommendations in metrics summary.

## Related Files

- `/mnt/c/ev29/agent/captcha_solver.py` - Main implementation
- `/mnt/c/ev29/test_captcha_confidence.py` - Test script
- `~/.eversale/captcha_metrics.jsonl` - Metrics log
- `/mnt/c/ev29/agent/CAPTCHA_CONFIDENCE_SCORING.md` - This documentation

