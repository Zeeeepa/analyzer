#!/usr/bin/env python3
"""
Quick test to verify benchmark structure and output format.
This doesn't run actual browser tests, just validates the reporting logic.
"""

import json
from benchmark_improvements import (
    TaskResult,
    BenchmarkComparison,
    BenchmarkSummary,
    print_benchmark_results,
)


def create_mock_results():
    """Create mock benchmark results to test output formatting."""

    # Simulated OLD vs NEW results for each task
    mock_data = [
        {
            'task': 'Hacker News links',
            'old': {'tokens': 4500, 'time': 2500, 'screenshots': 3, 'success': True},
            'new': {'tokens': 1200, 'time': 650, 'screenshots': 0, 'success': True},
        },
        {
            'task': 'Form fill',
            'old': {'tokens': 7500, 'time': 3200, 'screenshots': 5, 'success': True},
            'new': {'tokens': 1800, 'time': 980, 'screenshots': 0, 'success': True},
        },
        {
            'task': 'Reddit post titles',
            'old': {'tokens': 5000, 'time': 2800, 'screenshots': 3, 'success': True},
            'new': {'tokens': 1100, 'time': 720, 'screenshots': 0, 'success': True},
        },
        {
            'task': 'Google search',
            'old': {'tokens': 6500, 'time': 3500, 'screenshots': 4, 'success': True},
            'new': {'tokens': 1500, 'time': 920, 'screenshots': 0, 'success': True},
        },
        {
            'task': 'Business contact info',
            'old': {'tokens': 5500, 'time': 2700, 'screenshots': 3, 'success': True},
            'new': {'tokens': 1300, 'time': 710, 'screenshots': 0, 'success': True},
        },
    ]

    comparisons = []
    for data in mock_data:
        comp = BenchmarkComparison(
            task_name=data['task'],
            old_tokens=data['old']['tokens'],
            old_runtime_ms=data['old']['time'],
            old_screenshots=data['old']['screenshots'],
            old_success=data['old']['success'],
            new_tokens=data['new']['tokens'],
            new_runtime_ms=data['new']['time'],
            new_screenshots=data['new']['screenshots'],
            new_success=data['new']['success'],
        )
        comparisons.append(comp)

    # Calculate averages
    avg_token_reduction = sum(c.token_reduction_pct for c in comparisons) / len(comparisons)
    avg_speedup = sum(c.runtime_speedup for c in comparisons) / len(comparisons)
    avg_screenshot_reduction = sum(c.screenshot_reduction_pct for c in comparisons) / len(comparisons)

    summary = BenchmarkSummary(
        total_tasks=len(comparisons),
        avg_token_reduction_pct=avg_token_reduction,
        avg_runtime_speedup=avg_speedup,
        avg_screenshot_reduction_pct=avg_screenshot_reduction,
        old_success_rate=100.0,
        new_success_rate=100.0,
        success_rate_improvement=0.0,
        comparisons=comparisons,
    )

    return summary


def main():
    print("Testing Benchmark Output Format")
    print("=" * 80)
    print()

    # Create mock results
    summary = create_mock_results()

    # Print formatted output
    print_benchmark_results(summary)

    # Save to JSON
    output_file = "test_benchmark_results.json"
    data = {
        'test_run': True,
        'summary': summary.to_dict(),
    }

    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Test results saved to {output_file}")
    print()
    print("✓ Output formatting works correctly!")
    print("✓ Ready to run real benchmark")


if __name__ == '__main__':
    main()
