# Browser Agent Benchmark

Comprehensive benchmark comparing the OLD screenshot-based approach vs NEW snapshot-first approach with token optimization.

## What It Tests

The benchmark measures improvements across 5 real-world tasks:

| Task | Description | Complexity |
|------|-------------|------------|
| **Hacker News links** | Extract article links from HN front page | Simple extraction |
| **Form fill** | Fill form fields on httpbin.org | Multi-step interaction |
| **Reddit post titles** | Extract post titles from Reddit | Text extraction |
| **Google search** | Search and extract results | Multi-step flow |
| **Business contact** | Extract contact info from example site | Complex extraction |

## Metrics Tracked

### Performance Metrics
- **Token usage**: OLD (screenshot) vs NEW (snapshot)
- **Runtime**: Total time to complete task
- **Screenshots**: Number of screenshots taken
- **Success rate**: Task completion percentage

### Improvements Measured
- **Token reduction %**: How much fewer tokens used
- **Runtime speedup**: How much faster (e.g., 3.2x)
- **Screenshot elimination %**: Reduction in screenshots

## Usage

### Basic Run
```bash
# Run all 5 tasks
python benchmark_improvements.py
```

### Quick Test (Fewer Tasks)
```bash
# Run only first 3 tasks
python benchmark_improvements.py --tasks 3
```

### Verbose Output
```bash
# Show detailed per-task metrics
python benchmark_improvements.py --verbose
```

### Custom Output File
```bash
# Save results to custom JSON file
python benchmark_improvements.py --output my_results.json
```

## Example Output

```
================================================================================
BROWSER AGENT BENCHMARK RESULTS
================================================================================

Task                      | Old Tokens | New Tokens | Reduction | Old Time | New Time | Speedup
--------------------------------------------------------------------------------
Hacker News links        |       4500 |       1200 |      73% |   2500ms |    650ms |     3.8x
Form fill                |       7500 |       1800 |      76% |   3200ms |    980ms |     3.3x
Reddit post titles       |       5000 |       1100 |      78% |   2800ms |    720ms |     3.9x
Google search            |       6500 |       1500 |      77% |   3500ms |    920ms |     3.8x
Business contact info    |       5500 |       1300 |      76% |   2700ms |    710ms |     3.8x
--------------------------------------------------------------------------------

SUMMARY
--------------------------------------------------------------------------------
Average token reduction:        76.0%
Average speedup:                3.7x
Screenshots eliminated:         85%
Success rate (OLD):             100%
Success rate (NEW):             100%
Success rate improvement:       +0%

TOTAL SAVINGS
--------------------------------------------------------------------------------
Tokens saved:                   23,100 tokens (29,000 -> 5,900)
Time saved:                     9,530ms (14,700ms -> 5,170ms)
Cost reduction (est.):          ~$0.0693 per benchmark run

================================================================================
```

## How It Works

### OLD Approach (Screenshot-Based)
1. Navigate to page
2. Take screenshot (2500+ tokens)
3. Send screenshot to LLM for analysis
4. Extract elements (slow, expensive)
5. Repeat for every interaction

**Problems:**
- High token usage (images = ~2500 tokens each)
- Slow (screenshot encoding, transfer, LLM analysis)
- Expensive (GPT-4V charges for image tokens)

### NEW Approach (Snapshot-First)
1. Navigate to page
2. Get accessibility snapshot (text-based, ~800 tokens)
3. Compress with token optimizer (~300 tokens)
4. Extract with JavaScript (no LLM, instant)
5. Only screenshot when vision needed (rare)

**Benefits:**
- Low token usage (text snapshots ~300 tokens)
- Fast (no image encoding, direct JS extraction)
- Cheap (text tokens are 1/10th the cost)

## Architecture

```
benchmark_improvements.py
├── OldApproachSimulator       # Simulates screenshot-based approach
│   ├── Uses DirectPlaywright
│   ├── Takes screenshots for every action
│   └── Estimates LLM token usage
│
├── NewApproachBenchmark       # Tests new optimized approach
│   ├── Uses DOMFirstBrowser
│   ├── Uses TokenOptimizer
│   ├── Uses extraction_helpers
│   └── Minimal screenshots
│
└── Metrics Collection
    ├── TaskResult             # Per-task metrics
    ├── BenchmarkComparison    # OLD vs NEW comparison
    └── BenchmarkSummary       # Overall statistics
```

## Requirements

### Python Modules
- `token_optimizer.py` - Token compression and caching
- `dom_first_browser.py` - Snapshot-first browser
- `extraction_helpers.py` - JavaScript extraction utilities
- `playwright_direct.py` - OLD approach (optional, will estimate if missing)

### Dependencies
```bash
pip install playwright loguru
playwright install chromium
```

## Interpreting Results

### Good Results
- Token reduction: 70-80%
- Runtime speedup: 3-4x
- Screenshot reduction: 85-95%
- Success rate: 100%

### Warning Signs
- Token reduction < 50%: Optimizer not working properly
- Runtime speedup < 2x: Extraction may be slow
- Success rate < 80%: Tasks failing, check errors

## Troubleshooting

### "New modules not available"
```bash
# Ensure all modules are in same directory
ls token_optimizer.py dom_first_browser.py extraction_helpers.py
```

### "Old approach not available"
This is OK - benchmark will use estimates for comparison.

### Browser launch fails
```bash
# Install Playwright browsers
playwright install chromium

# Or use headless
python benchmark_improvements.py  # Already uses headless=True
```

### Task failures
```bash
# Run with verbose to see errors
python benchmark_improvements.py --verbose
```

## Output Files

### benchmark_results.json
Complete results in JSON format for analysis:
```json
{
  "timestamp": 1704067200,
  "summary": {
    "total_tasks": 5,
    "avg_token_reduction_pct": 76.0,
    "avg_runtime_speedup": 3.7,
    "comparisons": [...]
  }
}
```

Use this for:
- Tracking performance over time
- Comparing different optimization strategies
- Generating charts/graphs

## Cost Analysis

### Token Cost Estimates
- GPT-4 Turbo: $0.01 / 1K tokens (input)
- GPT-4V: $0.01 / 1K tokens (text), $0.00765 / image

### Example Savings (per 1000 tasks)
```
OLD approach: 29,000 tokens × 1000 tasks = 29M tokens
NEW approach: 5,900 tokens × 1000 tasks = 5.9M tokens

Savings: 23.1M tokens
Cost reduction: ~$231 per 1000 tasks
```

## Next Steps

### After Running Benchmark
1. Review token reduction - should be 70%+
2. Check speedup - should be 3x+
3. Verify success rate - should be 100%
4. Compare with previous runs

### Optimization Tips
If results are below target:
- Increase `max_snapshot_elements` in TokenOptimizer
- Reduce `max_text_length` for more compression
- Use more aggressive caching (`cache_ttl_seconds`)
- Add more extraction helpers for common patterns

### Integration
Once benchmark shows good results:
- Replace screenshot calls with snapshots in production
- Add token optimizer to agent pipeline
- Use extraction helpers for common tasks
- Monitor real-world performance

## Known Limitations

1. **Estimates for OLD approach**: If `playwright_direct.py` not available, uses estimated metrics
2. **Network dependency**: Tasks require internet (uses real sites)
3. **Flaky sites**: Some sites may be slow or unavailable
4. **Vision tasks**: Benchmark doesn't test vision-only tasks (intentionally)

## Support

For issues or questions:
1. Check logs: `python benchmark_improvements.py --verbose`
2. Review error messages in output
3. Verify all modules are present
4. Check Playwright installation

## Version History

- **v1.0** (2024-12-17): Initial benchmark implementation
  - 5 test tasks
  - OLD vs NEW comparison
  - Token, runtime, screenshot metrics
  - JSON export
