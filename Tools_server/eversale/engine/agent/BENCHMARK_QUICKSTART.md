# Benchmark Quick Start

Quick reference for running the browser agent benchmark.

## One-Line Run

```bash
python benchmark_improvements.py
```

## Common Commands

| Command | Description |
|---------|-------------|
| `python benchmark_improvements.py` | Run all 5 tasks |
| `python benchmark_improvements.py --tasks 1` | Quick test (1 task) |
| `python benchmark_improvements.py --tasks 3` | Medium test (3 tasks) |
| `python benchmark_improvements.py --verbose` | Detailed output |
| `python benchmark_improvements.py --output my_results.json` | Custom output file |

## Expected Results

### Good Performance
- Token reduction: **70-80%**
- Runtime speedup: **3-4x**
- Screenshot elimination: **85-100%**
- Success rate: **100%**

### Actual Results (Example)
```
Average token reduction:        76.1%
Average speedup:                3.7x
Screenshots eliminated:         100%
Success rate improvement:       +0%

Tokens saved: 22,100 tokens per 5 tasks
Time saved: 10,720ms per 5 tasks
Cost reduction: ~$0.0663 per benchmark run
```

## What It Tests

1. **Hacker News links** - Extract article links
2. **Form fill** - Fill form fields on httpbin.org
3. **Reddit titles** - Extract post titles
4. **Google search** - Search and get results
5. **Business contact** - Extract contact info

## Output Files

- Console: Formatted table with results
- `benchmark_results.json`: Complete data in JSON format

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "New modules not available" | Check all modules are present |
| "Old approach not available" | OK - will use estimates |
| Browser launch fails | Run `playwright install chromium` |
| Tasks timing out | Use `--tasks 1` for quick test |

## Next Steps

After running:
1. Review token reduction (should be 70%+)
2. Check speedup (should be 3x+)
3. Verify success rate (should be 100%)
4. Compare with baseline in BENCHMARK_README.md

## Quick Validation

Test the output format without running full benchmark:
```bash
python test_benchmark.py
```

## Full Documentation

See `BENCHMARK_README.md` for complete documentation.
