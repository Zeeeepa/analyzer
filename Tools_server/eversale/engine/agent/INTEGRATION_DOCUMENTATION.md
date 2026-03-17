# Hallucination Guard + Pre-Execution Validator Integration

## Overview

This integration combines two critical safety systems to provide comprehensive validation for agent actions:

1. **Pre-Execution Validator**: Validates actions BEFORE they execute (safety, correctness, appropriateness)
2. **Hallucination Guard**: Validates data outputs AFTER extraction (detects fake/hallucinated data)

Together, they provide a complete ALLOW/DENY/MODIFY decision framework for the orchestrator.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR                              │
│                                                              │
│  1. Plan Action                                             │
│  2. Pre-Execution Validation ──────────────┐                │
│  3. Execute if ALLOW/MODIFY                │                │
│  4. Post-Execution Validation              │                │
│  5. Use ALLOW/MODIFY/DENY result           │                │
└────────────────────────────────────────────┼────────────────┘
                                             │
                    ┌────────────────────────┼────────────────────┐
                    │                        ▼                    │
                    │    PRE-EXECUTION VALIDATOR                  │
                    │                                             │
                    │  • Dangerous patterns (rm -rf, etc.)       │
                    │  • Parameter validation                     │
                    │  • Common mistakes                          │
                    │  • URL correction                           │
                    │                                             │
                    │  Result: ALLOW/DENY/REQUIRES_APPROVAL      │
                    └─────────────────────────────────────────────┘
                                             │
                                             ▼
                    ┌────────────────────────────────────────────┐
                    │         HALLUCINATION GUARD                │
                    │         (Post-Execution)                   │
                    │                                            │
                    │  • Fake pattern detection                 │
                    │    - Emails (fake@placeholder.com)        │
                    │    - Phones (555-1234)                    │
                    │    - Companies (Acme Corp)                │
                    │    - Disposable emails (guerrillamail)    │
                    │  • LLM instruction leakage                │
                    │  • Data provenance tracking               │
                    │  • Confidence scoring                     │
                    │                                            │
                    │  Result: ALLOW/DENY/MODIFY                │
                    │  + Cleaned data if applicable              │
                    └────────────────────────────────────────────┘
```

## Key Features

### 1. Two-Phase Validation

#### Phase 1: Pre-Execution (validate)
- Checks action safety before execution
- Validates parameters
- Suggests modifications
- Prevents dangerous operations

#### Phase 2: Post-Execution (validate_action_output)
- Validates produced data for hallucinations
- Checks data quality and confidence
- Tracks data provenance
- Returns cleaned data when possible

### 2. Unified Decision Framework

All validation results use the same enum:
- **ALLOW**: Safe to proceed
- **DENY**: Reject completely
- **MODIFY**: Use cleaned/corrected version
- **REQUIRES_APPROVAL**: Manual review needed

### 3. Combined Confidence Scoring

The system combines multiple confidence signals:
- Extraction confidence (from the tool)
- Hallucination detection (pattern matching)
- Data provenance (source verification)
- LLM response validation

Formula:
```python
combined_confidence = (extraction_confidence + source_confidence) / 2
- (critical_issues × 0.2) - (regular_issues × 0.1)
```

### 4. Configuration

```yaml
# config/config.yaml
validator:
  enabled: true
  use_llm_validation: false

  hallucination_guard:
    enabled: true                      # Enable hallucination detection
    strict_mode: true                  # Fail on any hallucination
    validate_llm_outputs: true         # Validate LLM-generated content
    validate_extracted_data: true      # Validate extracted web data
    min_confidence_threshold: 0.5      # Minimum acceptable confidence
```

## Usage Examples

### Example 1: Basic Pre-Execution Validation

```python
from agent.pre_execution_validator import PreExecutionValidator, ValidationResult

validator = PreExecutionValidator()

# Check action before execution
action = {
    "name": "playwright_navigate",
    "parameters": {"url": "example.com"}  # Missing protocol
}

result = validator.validate(action)

if result.result == ValidationResult.ALLOW:
    execute(action)
elif result.result == ValidationResult.MODIFY:
    execute(result.modified_action)  # Use corrected version
elif result.result == ValidationResult.DENY:
    log_error(result.reason)
```

### Example 2: Post-Execution Data Validation

```python
# After extracting data from a webpage
action = {
    "name": "playwright_extract_entities",
    "parameters": {"url": "https://company.com"}
}

output_data = {
    "email": "contact@company.com",
    "phone": "+1-555-0100",
    "company": "Real Company Inc"
}

context = {
    "url": "https://company.com",
    "extraction_method": "css",
    "confidence_score": 0.9
}

# Validate the extracted data
result = validator.validate_action_output(action, output_data, context)

if result.result == ValidationResult.ALLOW:
    store_data(output_data)
    print(f"Data confidence: {result.data_confidence}")
elif result.result == ValidationResult.DENY:
    print(f"Hallucination detected: {result.hallucination_issues}")
    discard_data()
elif result.result == ValidationResult.MODIFY:
    store_data(result.cleaned_data)  # Use sanitized version
    print("Using cleaned data")
```

### Example 3: Full Orchestrator Workflow

```python
def orchestrator_execute_action(action, context=None):
    """Complete validation workflow for orchestrator."""
    validator = PreExecutionValidator()

    # Step 1: Pre-execution validation
    pre_result = validator.validate(action, context)

    if pre_result.result == ValidationResult.DENY:
        return None, f"Action denied: {pre_result.reason}"

    if pre_result.result == ValidationResult.REQUIRES_APPROVAL:
        if not ask_user_approval(pre_result.reason):
            return None, "User denied approval"

    # Use modified action if provided
    action_to_execute = pre_result.modified_action or action

    # Step 2: Execute action
    try:
        output = execute_tool(action_to_execute)
    except Exception as e:
        return None, f"Execution failed: {e}"

    # Step 3: Post-execution validation
    post_result = validator.validate_action_output(
        action_to_execute,
        output,
        context
    )

    if post_result.result == ValidationResult.DENY:
        return None, f"Data validation failed: {post_result.reason}"

    if post_result.result == ValidationResult.MODIFY:
        output = post_result.cleaned_data

    if post_result.result == ValidationResult.REQUIRES_APPROVAL:
        if not ask_user_data_approval(post_result):
            return None, "User rejected data"

    return output, "Success"
```

## Detection Capabilities

### Hallucination Patterns Detected

1. **Fake Emails**
   - `fake@placeholder.com`
   - `test@example.com`
   - `john.doe@*`

2. **Disposable Emails** (93+ domains)
   - `guerrillamail.com`
   - `tempmail.com`
   - `mailinator.com`
   - etc.

3. **Fake Phone Numbers**
   - `555-xxxx` patterns
   - `123-456-7890`
   - `000-000-0000`

4. **Fake Companies**
   - `Acme Corp`
   - `Example Inc`
   - `Contoso` (Microsoft placeholder)

5. **LLM Instruction Leakage** (38+ patterns)
   - "As an AI assistant..."
   - "According to my instructions..."
   - System prompt fragments

6. **Missing Provenance**
   - No source tool specified
   - No URL for browser-based extraction
   - Low confidence scores

## Data Provenance Tracking

Every validated data output includes provenance information:

```python
{
    "tool_name": "playwright_extract_entities",
    "timestamp": "2024-12-07T19:00:00",
    "url": "https://company.com",
    "page_title": "Contact Us - Company",
    "extraction_method": "css",
    "confidence_score": 0.9,
    "verification_attempts": 1,
    "fallback_used": false,
    "metadata": {
        "selector": ".contact-info",
        "element_count": 1
    }
}
```

## Statistics & Monitoring

### Validation Summary

```python
summary = validator.get_validation_summary()
# {
#     "total": 50,
#     "allowed": 40,
#     "denied": 5,
#     "modified": 3,
#     "approval_needed": 2,
#     "allow_rate": 0.8,
#     "hallucination_detected": 5,
#     "average_confidence": 0.75
# }
```

### Hallucination Statistics

```python
hal_stats = validator.get_hallucination_stats()
# {
#     "enabled": true,
#     "strict_mode": true,
#     "total_data_validations": 25,
#     "hallucinations_detected": 5,
#     "provenance_summary": {
#         "total_validations": 25,
#         "sources_by_tool": {"playwright_extract": 20, "llm_generate": 5},
#         "missing_provenance_count": 2,
#         "low_confidence_count": 3
#     },
#     "recent_issues": [...]
# }
```

## Integration Benefits

1. **Defense in Depth**: Two layers of validation (pre + post)
2. **Automatic Data Cleaning**: MODIFY result provides sanitized data
3. **Confidence Scoring**: Quantified trust in extracted data
4. **Provenance Tracking**: Full audit trail for all data
5. **Flexible Configuration**: Enable/disable features as needed
6. **Production Ready**: Comprehensive error handling and logging

## Testing

Run the integration tests:

```bash
cd /mnt/c/ev29
python3 test_integration_direct.py
```

Tests cover:
- Pre-execution validation (safe/dangerous actions)
- URL auto-correction
- Hallucination detection (fake data, disposable emails)
- LLM instruction leakage
- Data cleaning (MODIFY results)
- Confidence scoring
- Statistics tracking
- Full orchestrator workflow

## Error Handling

The system gracefully handles:
- Missing hallucination guard module (falls back to basic validation)
- Missing configuration (uses sensible defaults)
- Invalid data types (logs and continues)
- Validation failures (returns appropriate DENY/REQUIRES_APPROVAL)

```python
try:
    result = validator.validate_action_output(action, output, context)
except Exception as e:
    # Logged automatically, returns REQUIRES_APPROVAL
    logger.error(f"Validation error: {e}")
```

## Best Practices

1. **Always validate both pre and post execution**
   - Pre: Catch dangerous actions before they run
   - Post: Verify data quality after extraction

2. **Use confidence thresholds**
   - Set `min_confidence_threshold` based on use case
   - Critical operations: 0.8+
   - General extraction: 0.5+

3. **Handle MODIFY results**
   - Always use `cleaned_data` when result is MODIFY
   - Log what was removed/changed

4. **Track provenance**
   - Include URL, extraction method, and confidence in context
   - Store provenance with final data

5. **Monitor statistics**
   - Regular check hallucination detection rates
   - Alert on high failure rates

## Future Enhancements

Potential improvements:
- LLM-based validation (more intelligent detection)
- Learning from user corrections
- Domain-specific validation rules
- Real-time email/phone verification APIs
- Blockchain-based provenance immutability

