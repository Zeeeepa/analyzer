# Self Verifier - Output Verification System

## Overview

The Self Verifier provides comprehensive verification of agent outputs before finalizing, using multiple verification strategies to ensure accuracy and reliability.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Self Verifier                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐  ┌──────────────────┐                │
│  │ Claim Extractor │  │ Consistency      │                │
│  │ - Facts         │  │ Checker          │                │
│  │ - Statistics    │  │ - Contradictions │                │
│  │ - Actions       │  │ - Completeness   │                │
│  └─────────────────┘  └──────────────────┘                │
│                                                             │
│  ┌─────────────────┐  ┌──────────────────┐                │
│  │ Web Fact        │  │ Second Opinion   │                │
│  │ Checker         │  │ - LLM Review     │                │
│  │ - Search Claims │  │ - Reasoning Check│                │
│  └─────────────────┘  └──────────────────┘                │
│                                                             │
│  ┌─────────────────┐  ┌──────────────────┐                │
│  │ Visual Verifier │  │ EventBus         │                │
│  │ - Screenshot    │  │ Integration      │                │
│  │ - State Check   │  │ - Subscribe      │                │
│  └─────────────────┘  └──────────────────┘                │
└─────────────────────────────────────────────────────────────┘
```

## Features

### 1. Claim Extraction
Automatically extracts verifiable claims from agent output:

- **Facts**: "X is Y", location claims, date claims
- **Statistics**: Numbers with units, percentages, changes
- **Action Results**: "Successfully completed X", "Found N items"
- **Reasoning**: Logical chains and inferences

### 2. Verification Strategies

#### Consistency Check (Always On)
- Detects contradictions in output
- Identifies incomplete thoughts
- Verifies logical flow
- Fast, no external dependencies

#### Web Fact Checking (Optional)
- Verifies claims against web search results
- Caches search results for efficiency
- Prioritizes statistics and key facts
- Graceful degradation if search unavailable

#### Second Opinion (Optional)
- Uses another LLM to review reasoning
- Structured review format (VERDICT/CONFIDENCE/ISSUES)
- Catches logical errors and misunderstandings
- Requires LLM client

#### Visual Verification (Optional)
- Verifies UI state matches expectations
- Uses vision models to analyze screenshots
- Confirms actions were executed correctly
- Requires vision function

### 3. EventBus Integration

The verifier subscribes to `ACTION_COMPLETE` events:

```python
# Automatic verification on action completion
event = OrganismEvent(
    event_type=EventType.ACTION_COMPLETE,
    source="action_engine",
    data={
        'task': 'Find Python books',
        'result': 'Found 15 books...',
        'screenshot': screenshot_data
    }
)

# Verifier automatically processes and publishes results
```

### 4. Graceful Degradation

If verification tools fail:
- Falls back to optimistic passing (confidence 0.5)
- Logs warnings for debugging
- Continues verification with available tools
- Never blocks the agent

## Usage

### Basic Usage

```python
from agent.self_verifier import SelfVerifier

# Initialize verifier
verifier = SelfVerifier()

# Verify an answer
task = "Find Python books on books.toscrape.com"
answer = "I found 15 Python books. The top book costs $45.99."

result = await verifier.verify(answer, task)

# Check results
if result.passed:
    print(f"✓ Verified with {result.confidence:.0%} confidence")
else:
    print(f"✗ Issues: {result.issues}")

# View detailed summary
print(result.summary())
```

### With Full Configuration

```python
from agent.self_verifier import SelfVerifier
from agent.llm_client import LLMClient
from agent.organism_core import EventBus

# Initialize components
llm_client = LLMClient()
event_bus = EventBus()

# Async search function
async def web_search(query):
    # Your search implementation
    return search_results

# Async vision function
async def analyze_screenshot(screenshot, question):
    # Your vision implementation
    return description

# Create fully-configured verifier
verifier = SelfVerifier(
    llm_client=llm_client,
    search_fn=web_search,
    vision_fn=analyze_screenshot,
    event_bus=event_bus,
    config={
        'min_verification_confidence': 0.6,
        'enabled_checks': ['consistency', 'second_opinion', 'web_fact', 'visual']
    }
)

# Verify with all strategies
result = await verifier.verify(
    answer=answer,
    task=task,
    screenshot=screenshot_data
)
```

### EventBus Integration

```python
from agent.organism_core import EventBus, EventType
from agent.self_verifier import SelfVerifier

# Create shared event bus
event_bus = EventBus()

# Create verifier (auto-subscribes to ACTION_COMPLETE)
verifier = SelfVerifier(event_bus=event_bus)

# When actions complete, verification happens automatically
action_engine.complete_action(
    task="Search for items",
    result="Found 10 items"
)
# → EventBus emits ACTION_COMPLETE
# → Verifier receives event
# → Runs verification
# → Publishes verification result
```

### Statistics and Monitoring

```python
# Get verification statistics
stats = verifier.get_verification_stats()

print(f"Total Verifications: {stats['total_verifications']}")
print(f"Pass Rate: {stats['pass_rate']:.0%}")
print(f"Avg Confidence: {stats['avg_confidence']:.0%}")
print(f"Common Issues: {stats['common_issues']}")
```

## Configuration Options

```python
config = {
    # Minimum confidence to pass verification (0.0-1.0)
    'min_verification_confidence': 0.6,

    # Which checks to enable
    'enabled_checks': [
        'consistency',      # Always recommended
        'second_opinion',   # Requires LLM
        'web_fact',        # Requires search_fn
        'visual'           # Requires vision_fn and screenshot
    ]
}
```

## Data Structures

### Claim
```python
@dataclass
class Claim:
    text: str                 # The claim text
    claim_type: str          # "fact", "statistic", "action_result", "reasoning"
    confidence: float        # Initial confidence (0.0-1.0)
    source_sentence: str     # Original sentence containing claim
```

### CheckResult
```python
@dataclass
class CheckResult:
    check_type: str          # "web_fact", "second_opinion", "visual", "consistency"
    passed: bool             # Did check pass?
    confidence: float        # Check confidence (0.0-1.0)
    details: str            # Human-readable details
    issues: List[str]       # Issues found
    timestamp: float        # When check completed
```

### VerificationResult
```python
@dataclass
class VerificationResult:
    task: str                # Original task
    answer: str              # Agent's answer
    passed: bool             # Overall pass/fail
    confidence: float        # Aggregated confidence (0.0-1.0)
    issues: List[str]       # All issues from all checks
    checks: List[CheckResult] # Individual check results
    timestamp: float         # Verification timestamp
    duration_ms: float       # How long verification took

    def summary(self) -> str:
        """Get human-readable summary"""
```

## Confidence Aggregation

Checks are weighted for overall confidence:

| Check Type | Weight | Description |
|------------|--------|-------------|
| consistency | 20% | Internal consistency and logic |
| second_opinion | 40% | LLM review of reasoning |
| web_fact | 30% | External fact verification |
| visual | 10% | UI state confirmation |

Overall pass requires:
1. Aggregated confidence ≥ threshold (default 0.6)
2. No critical failures (confidence < 0.3)

## Example Outputs

### Successful Verification
```
============================================================
VERIFICATION RESULT: VERIFIED
============================================================
Task: Find Python books on books.toscrape.com...
Overall Confidence: 90.00%
Checks Passed: 3/3
Duration: 245ms

Check Details:
  consistency: PASSED (confidence=1.00)
  second_opinion: PASSED (confidence=0.85)
  web_fact: PASSED (confidence=0.88)
============================================================
```

### Failed Verification
```
============================================================
VERIFICATION RESULT: VERIFICATION FAILED
============================================================
Task: Calculate total revenue...
Overall Confidence: 45.00%
Checks Passed: 1/3
Duration: 312ms

Issues Found (2):
  - Contradiction: Inconsistent numbers for 'revenue': [1000, 1500]
  - Second opinion: Calculation appears incorrect

Check Details:
  consistency: FAILED (confidence=0.60)
  second_opinion: FAILED (confidence=0.40)
  web_fact: PASSED (confidence=0.75)
============================================================
```

## Integration with Organism

The Self Verifier is designed to integrate seamlessly with the Organism architecture:

```
Heartbeat Loop (Always Running)
    ↓
Action Engine executes task
    ↓
Emits ACTION_COMPLETE event → EventBus
    ↓
Self Verifier receives event
    ↓
Runs verification strategies (async)
    ↓
Publishes verification result → EventBus
    ↓
Brain uses verification for confidence adjustment
    ↓
Episodic Memory stores verification results
```

## Performance

- **Consistency Check**: <1ms (no external calls)
- **Second Opinion**: 500-2000ms (LLM call)
- **Web Fact Check**: 300-1000ms per claim (cached)
- **Visual Verification**: 1000-3000ms (vision model)

**Total**: Typically 500-3000ms with parallel execution

## Error Handling

The verifier is designed to never fail the agent:

1. **Missing Dependencies**: Gracefully disables that check
2. **Network Errors**: Falls back to optimistic passing
3. **Timeout**: Sets confidence to 0.5 and continues
4. **Exception**: Logs error, returns safe default

## Testing

Run the test suite:

```bash
python3 test_self_verifier.py
```

Tests cover:
- Claim extraction accuracy
- Consistency checking
- Full verification workflow
- Statistics tracking
- Mock LLM integration

## Best Practices

1. **Always enable consistency check** - Fast and has no dependencies
2. **Use second opinion for critical tasks** - Catches reasoning errors
3. **Cache web searches** - Avoid redundant lookups
4. **Set appropriate confidence thresholds** - Lower for exploratory, higher for production
5. **Monitor verification stats** - Identify common failure modes
6. **Log all verification results** - Debugging and quality analysis

## Future Enhancements

Potential improvements:

- **Semantic similarity** for claim verification (embeddings)
- **Multi-model consensus** for second opinions
- **Historical pattern matching** against known-good outputs
- **User feedback loop** to improve verification accuracy
- **Automated correction** of detected issues
- **Real-time verification** during task execution
- **Confidence calibration** based on historical accuracy

## Related Components

- **organism_core.py**: EventBus for event-driven verification
- **llm_client.py**: LLM client for second opinions
- **world_model.py**: World state for expectation generation
- **episodic_memory.py**: Store verification history for learning

## License

Part of the Eversale autonomous AI worker system.
