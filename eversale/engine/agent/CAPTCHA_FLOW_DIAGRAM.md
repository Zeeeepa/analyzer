# CAPTCHA Dual-LLM Confidence Scoring Flow

## Visual Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     CAPTCHA DETECTED                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              STEP 1: VISION MODEL ANALYSIS                       │
│                                                                  │
│  Models: moondream (2.8B) → llava:7b → llama3.2-vision         │
│                                                                  │
│  Input:  CAPTCHA screenshot                                     │
│  Output: - Answer: "Abc123"                                     │
│          - Image Confidence: 0.95                               │
│                                                                  │
│  Factors:                                                       │
│  ✓ Answer length (3-10 chars = good)                           │
│  ✓ Clean output (no extra text)                                │
│  ✓ No LLM artifacts ("sorry", "cannot")                        │
│  ✗ Ambiguous chars (O/0, I/l/1) = penalty                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              STEP 2: IMAGE DESCRIPTION                           │
│                                                                  │
│  Same vision model describes the CAPTCHA:                       │
│                                                                  │
│  Prompt: "Describe this CAPTCHA in 1-2 sentences.              │
│           Focus on: clarity, distortion, readability"           │
│                                                                  │
│  Output: "Distorted text with moderate clarity,                │
│           6 alphanumeric characters visible"                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│          STEP 3: TEXT MODEL VALIDATION                          │
│                                                                  │
│  Model: qwen2.5:7b-instruct (or llama3.1:8b)                   │
│                                                                  │
│  Input:  - CAPTCHA type: "text"                                │
│          - Vision answer: "Abc123"                              │
│          - Image description: "Distorted text..."              │
│          - Raw output: "Abc123"                                 │
│                                                                  │
│  Validation Questions:                                          │
│  1. Does format match CAPTCHA type?                            │
│  2. Is answer plausible (not gibberish)?                       │
│  3. Any red flags (too long, errors)?                          │
│                                                                  │
│  Output: {"valid": true,                                        │
│           "confidence": 0.90,                                   │
│           "reason": "Valid 6-char alphanumeric"}               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│          STEP 4: COMBINED CONFIDENCE CALCULATION                │
│                                                                  │
│  Formula:                                                       │
│  combined = (image_conf × 0.6) + (context_conf × 0.3)         │
│           + format_bonus                                        │
│                                                                  │
│  Example:                                                       │
│  combined = (0.95 × 0.6) + (0.90 × 0.3) + 0.1                 │
│           = 0.57 + 0.27 + 0.1                                  │
│           = 0.94                                                │
│                                                                  │
│  Penalties Applied:                                             │
│  ✗ Answer too long (>10 chars): -20%                          │
│  ✗ Contains spaces: -15%                                       │
│  ✗ Context validation failed: -25%                             │
│                                                                  │
│  Final: 0.94 (no penalties)                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│          STEP 5: DECISION MAKING (THRESHOLDS)                   │
│                                                                  │
│  Confidence: 0.94                                               │
│                                                                  │
│  Threshold Evaluation:                                          │
│  ✓ ≥ 85% (HIGH)    → Auto-solve immediately                   │
│    75-85% (GOOD)   → Auto-solve with retry                     │
│    50-75% (MEDIUM) → Try once, then fallback                   │
│    < 50% (LOW)     → Human fallback immediately                │
│                                                                  │
│  Decision: "Auto-solve: HIGH confidence (≥85%)"               │
│  Action:   Submit answer NOW                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              STEP 6: SUBMIT & RECORD RESULT                     │
│                                                                  │
│  Submit answer: "Abc123"                                        │
│                                                                  │
│  Wait for result...                                             │
│                                                                  │
│  Result: SUCCESS ✓                                              │
│                                                                  │
│  Log to metrics:                                                │
│  {                                                              │
│    "timestamp": 1765165584.08,                                 │
│    "captcha_type": "text",                                     │
│    "combined_confidence": 0.94,                                │
│    "image_confidence": 0.95,                                   │
│    "context_confidence": 0.90,                                 │
│    "model": "moondream",                                       │
│    "answer_length": 6,                                         │
│    "accepted": true,                                           │
│    "actual_success": true                                      │
│  }                                                              │
│                                                                  │
│  Update metrics:                                                │
│  HIGH confidence: 1 attempt, 1 success (100% rate)             │
└─────────────────────────────────────────────────────────────────┘
```

## Decision Tree

```
                    ┌─────────────────┐
                    │ CAPTCHA Detected│
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ Vision Analysis │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ Text Validation │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │Combined = 0.XX  │
                    └────────┬────────┘
                             │
                ┌────────────┼────────────┐
                │            │            │
          ≥0.85 │      0.75-0.85    0.50-0.75      <0.50
                │            │            │            │
         ┌──────▼──────┐ ┌──▼──┐   ┌────▼────┐  ┌───▼────┐
         │AUTO-SOLVE   │ │AUTO │   │TRY ONCE │  │HUMAN   │
         │IMMEDIATELY  │ │+RETRY   │THEN HUMAN  │FALLBACK│
         └──────┬──────┘ └──┬──┘   └────┬────┘  └───┬────┘
                │            │           │            │
         ┌──────▼──────┐ ┌──▼──┐   ┌────▼────┐  ┌───▼────┐
         │Submit now   │ │Submit   │Submit   │  │Show    │
         │High conf    │ │Retry│   │Once only│  │browser │
         └──────┬──────┘ └──┬──┘   └────┬────┘  └───┬────┘
                │            │           │            │
                └────────────┴───────────┴────────────┘
                                  │
                         ┌────────▼────────┐
                         │ Record Result   │
                         │ Update Metrics  │
                         └─────────────────┘
```

## Confidence Weight Breakdown

```
COMBINED CONFIDENCE = Weighted Sum + Penalties

┌────────────────────────────────────────────────────────┐
│                    COMPONENTS                          │
├────────────────────────────────────────────────────────┤
│                                                        │
│  Image Confidence (60%)                               │
│  ████████████████████████████████████ 0.60           │
│    - Vision model OCR accuracy                        │
│    - Answer quality assessment                        │
│                                                        │
│  Context Confidence (30%)                             │
│  ████████████████████ 0.30                           │
│    - Text model validation                            │
│    - Format/plausibility check                        │
│                                                        │
│  Format Bonus (10%)                                   │
│  ██████████ 0.10                                     │
│    - Length within expected range                     │
│    - Type matches (text/math/grid)                    │
│                                                        │
├────────────────────────────────────────────────────────┤
│                    PENALTIES                           │
├────────────────────────────────────────────────────────┤
│                                                        │
│  Answer Too Long (>10 chars)        -0.20 (20%)      │
│  Contains Spaces                     -0.15 (15%)      │
│  Context Validation Failed           -0.25 (25%)      │
│                                                        │
└────────────────────────────────────────────────────────┘

Example:
  Image: 0.95 × 0.6 = 0.57
  Context: 0.90 × 0.3 = 0.27
  Format: Valid = +0.10
  Penalties: None = 0.00
  ─────────────────────────
  TOTAL: 0.94 → HIGH CONFIDENCE
```

## Success Rate Tracking

```
┌──────────────────────────────────────────────────────────┐
│            CAPTCHA SOLVING METRICS                       │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  HIGH (≥85%)                                            │
│  Attempts: 10  Successes: 9                             │
│  ████████████████████████████████████████ 90%          │
│                                                          │
│  GOOD (75-85%)                                          │
│  Attempts: 15  Successes: 11                            │
│  ████████████████████████████ 73%                      │
│                                                          │
│  MEDIUM (50-75%)                                        │
│  Attempts: 20  Successes: 12                            │
│  ████████████████████ 60%                              │
│                                                          │
│  LOW (<50%)                                             │
│  Attempts: 5  Successes: 0                              │
│  ████ 0% (all rejected before submission)              │
│                                                          │
├──────────────────────────────────────────────────────────┤
│  RECOMMENDATIONS:                                        │
│  • HIGH confidence performing well (90%)                 │
│  • MEDIUM confidence acceptable (60%)                    │
│  • LOW confidence correctly rejected (0% waste)          │
└──────────────────────────────────────────────────────────┘
```

## Comparison: Before vs After

```
┌─────────────────────────────────────────────────────────┐
│                  BEFORE (Single LLM)                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Vision Model → Answer                                 │
│                   ↓                                     │
│              Basic confidence (0-1)                     │
│                   ↓                                     │
│              Accept if > 0.5                            │
│                   ↓                                     │
│              Submit (many failures)                     │
│                                                         │
│  Issues:                                                │
│  ✗ High false positive rate                           │
│  ✗ No validation of answer quality                    │
│  ✗ Wasted attempts on bad answers                     │
│  ✗ No context awareness                               │
│                                                         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                  AFTER (Dual LLM)                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Vision Model → Answer + Image Confidence              │
│                         ↓                               │
│  Text Model → Validation + Context Confidence          │
│                         ↓                               │
│  Combined Score (weighted + penalties)                 │
│                         ↓                               │
│  Smart Decision (4 tier thresholds)                    │
│                         ↓                               │
│  Submit if confident, fallback if not                  │
│                                                         │
│  Benefits:                                              │
│  ✓ Lower false positive rate                          │
│  ✓ Answer quality validation                          │
│  ✓ Fewer wasted attempts                              │
│  ✓ Context-aware decisions                            │
│  ✓ Adaptive thresholds via metrics                    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Real-World Example Flow

```
┌──────────────────────────────────────────────────────────┐
│ EXAMPLE: Amazon CAPTCHA - "xY9pQm"                      │
└──────────────────────────────────────────────────────────┘

Step 1: Vision Analysis (moondream)
  Input: Screenshot of distorted text
  Output: "xY9pQm"
  Image Confidence: 0.85
  Reasoning: Clean extraction, good length, mixed case

Step 2: Image Description
  Output: "Distorted alphanumeric text, moderate clarity,
           wavy background, 6 characters visible"

Step 3: Context Validation (qwen2.5)
  Input: type=text, answer="xY9pQm", desc="Distorted..."
  Output: {
    "valid": true,
    "confidence": 0.80,
    "reason": "Valid 6-char mixed alphanumeric, plausible"
  }

Step 4: Combined Confidence
  = (0.85 × 0.6) + (0.80 × 0.3) + 0.1
  = 0.51 + 0.24 + 0.1
  = 0.85

Step 5: Decision
  Threshold: 0.85 ≥ 0.85 (HIGH)
  Decision: "Auto-solve: HIGH confidence (≥85%)"
  Action: Submit immediately

Step 6: Result
  Submitted: "xY9pQm"
  Amazon Response: ✓ ACCEPTED
  Metrics: HIGH confidence, 1 attempt, 1 success

OUTCOME: Successfully solved without human intervention!
```

## Threshold Adjustment Example

```
Initial Thresholds:
  HIGH:   ≥0.85
  GOOD:   0.75-0.85
  MEDIUM: 0.50-0.75
  LOW:    <0.50

After 50 Attempts:
  HIGH:   10 attempts, 7 successes (70%)  ← Below target!
  GOOD:   15 attempts, 12 successes (80%)
  MEDIUM: 20 attempts, 15 successes (75%) ← Above expectations!
  LOW:    5 attempts, 0 successes (0%)

Recommendation:
  "High confidence success rate is low (<70%).
   Consider raising high confidence threshold."

Adjusted Thresholds:
  HIGH:   ≥0.90  ← Raised from 0.85
  GOOD:   0.80-0.90  ← Raised from 0.75
  MEDIUM: 0.50-0.80  ← Unchanged
  LOW:    <0.50

After Another 50 Attempts:
  HIGH:   8 attempts, 7 successes (87.5%)  ✓ Improved!
  GOOD:   12 attempts, 10 successes (83%)
  MEDIUM: 25 attempts, 18 successes (72%)
  LOW:    5 attempts, 0 successes (0%)

Result: Better accuracy, fewer false positives!
```

## Integration Points

```
┌─────────────────────────────────────────────────────────┐
│               WHERE IT'S USED                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1. LocalCaptchaSolver.solve_image_with_vision()       │
│     └─> Main entry point for all CAPTCHA solving       │
│                                                         │
│  2. AmazonCaptchaHandler.solve_amazon_captcha()        │
│     └─> Amazon-specific integration                    │
│                                                         │
│  3. PageCaptchaHandler.solve_and_inject()              │
│     └─> Generic page CAPTCHA solving                   │
│                                                         │
│  4. AuthChallengeManager.check_and_handle_challenges() │
│     └─> High-level challenge management                │
│                                                         │
└─────────────────────────────────────────────────────────┘
```
