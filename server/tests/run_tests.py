#!/usr/bin/env python3
"""
Comprehensive test runner for Deal Desk OS.

This script provides various test execution scenarios:
- Full test suite execution
- Category-specific test runs
- Performance test execution
- CI/CD optimized test runs
- Test result reporting
"""

import argparse
import asyncio
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import pytest


class DealDeskTestRunner:
    """Main test runner for Deal Desk OS."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.test_dir = project_root / "server" / "tests"
        self.reports_dir = project_root / "test_reports"
        self.coverage_dir = self.reports_dir / "coverage"
        self.performance_dir = self.reports_dir / "performance"
        self.security_dir = self.reports_dir / "security"

        # Ensure directories exist
        for directory in [self.reports_dir, self.coverage_dir, self.performance_dir, self.security_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def run_test_suite(
        self,
        test_category: Optional[str] = None,
        markers: Optional[List[str]] = None,
        coverage: bool = False,
        verbose: bool = False,
        parallel: bool = False,
        generate_report: bool = True,
    ) -> int:
        """Run test suite with specified configuration."""
        cmd = ["python", "-m", "pytest"]

        # Add test directory
        cmd.append(str(self.test_dir))

        # Add markers
        if markers:
            for marker in markers:
                cmd.extend(["-m", marker])

        # Add coverage if requested
        if coverage:
            cmd.extend([
                "--cov=app",
                f"--cov-report=html:{self.coverage_dir}",
                "--cov-report=term-missing",
                "--cov-report=xml",
                "--cov-fail-under=80"
            ])

        # Add verbose output
        if verbose:
            cmd.append("-vv")
        else:
            cmd.append("-v")

        # Add parallel execution
        if parallel:
            cmd.extend(["-n", "auto"])

        # Add JUnit XML report for CI
        if generate_report:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            junit_file = self.reports_dir / f"junit_report_{timestamp}.xml"
            cmd.extend(["--junit-xml", str(junit_file)])

        # Add HTML report
        if generate_report:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_file = self.reports_dir / f"report_{timestamp}.html"
            cmd.extend(["--html", str(html_file), "--self-contained-html"])

        # Add timeout for safety
        cmd.extend(["--timeout=600"])

        # Print command
        print(f"Running: {' '.join(cmd)}")

        # Execute tests
        start_time = time.time()
        result = subprocess.run(cmd, cwd=self.project_root)
        duration = time.time() - start_time

        print(f"\nTest execution completed in {duration:.2f} seconds")
        print(f"Return code: {result.returncode}")

        return result.returncode

    def run_unit_tests(self, coverage: bool = True) -> int:
        """Run only unit tests."""
        return self.run_test_suite(
            markers=["unit"],
            coverage=coverage,
            verbose=True,
            generate_report=True
        )

    def run_integration_tests(self, coverage: bool = False) -> int:
        """Run integration tests."""
        return self.run_test_suite(
            markers=["integration"],
            coverage=coverage,
            verbose=True,
            generate_report=True
        )

    def run_end_to_end_tests(self) -> int:
        """Run end-to-end workflow tests."""
        return self.run_test_suite(
            markers=["end_to_end"],
            coverage=False,
            verbose=True,
            generate_report=True
        )

    def run_performance_tests(self, generate_report: bool = True) -> int:
        """Run performance and load tests."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        performance_report = self.performance_dir / f"performance_report_{timestamp}.json"

        cmd = [
            "python", "-m", "pytest",
            str(self.test_dir),
            "-m", "performance",
            "-v",
            "--benchmark-only",
            "--benchmark-json", str(performance_report)
        ]

        print(f"Running performance tests...")
        result = subprocess.run(cmd, cwd=self.project_root)

        if generate_report:
            self.generate_performance_report(performance_report)

        return result.returncode

    def run_security_tests(self) -> int:
        """Run security and compliance tests."""
        return self.run_test_suite(
            markers=["security"],
            coverage=False,
            verbose=True,
            generate_report=True
        )

    def run_sla_tests(self) -> int:
        """Run SLA and KPI validation tests."""
        return self.run_test_suite(
            markers=["sla"],
            coverage=False,
            verbose=True,
            generate_report=True
        )

    def run_smoke_tests(self) -> int:
        """Run quick smoke tests for basic functionality."""
        smoke_markers = ["unit", "not slow", "not expensive"]
        return self.run_test_suite(
            markers=smoke_markers,
            coverage=False,
            verbose=True,
            parallel=True,
            generate_report=False
        )

    def run_ci_tests(self, parallel: bool = True) -> int:
        """Run CI-optimized test suite."""
        ci_markers = ["unit", "integration", "not slow", "not expensive"]
        return self.run_test_suite(
            markers=ci_markers,
            coverage=True,
            verbose=False,
            parallel=parallel,
            generate_report=True
        )

    def generate_performance_report(self, benchmark_file: Path) -> None:
        """Generate HTML performance report from benchmark data."""
        try:
            import json

            with open(benchmark_file, 'r') as f:
                benchmark_data = json.load(f)

            # Generate simple HTML report
            html_template = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Deal Desk OS - Performance Report</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 20px; }
                    table { border-collapse: collapse; width: 100%; }
                    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                    th { background-color: #f2f2f2; }
                    .pass { color: green; }
                    .fail { color: red; }
                </style>
            </head>
            <body>
                <h1>Deal Desk OS - Performance Report</h1>
                <p>Generated: {timestamp}</p>

                <h2>Benchmark Results</h2>
                <table>
                    <tr>
                        <th>Test Name</th>
                        <th>Min (ms)</th>
                        <th>Mean (ms)</th>
                        <th>Max (ms)</th>
                        <th>Status</th>
                    </tr>
                    {benchmark_rows}
                </table>

                <h2>Summary</h2>
                <p>Total tests: {total_tests}</p>
                <p>Passed: {passed_tests}</p>
                <p>Failed: {failed_tests}</p>
            </body>
            </html>
            """

            benchmark_rows = ""
            total_tests = len(benchmark_data.get("benchmarks", []))
            passed_tests = 0
            failed_tests = 0

            for benchmark in benchmark_data.get("benchmarks", []):
                name = benchmark.get("name", "Unknown")
                min_time = benchmark.get("min", 0) * 1000  # Convert to ms
                mean_time = benchmark.get("mean", 0) * 1000
                max_time = benchmark.get("max", 0) * 1000

                # Simple pass/fail criteria
                status = "pass" if mean_time < 1000 else "fail"  # Fail if > 1 second
                status_class = status

                if status == "pass":
                    passed_tests += 1
                else:
                    failed_tests += 1

                benchmark_rows += f"""
                <tr>
                    <td>{name}</td>
                    <td>{min_time:.2f}</td>
                    <td>{mean_time:.2f}</td>
                    <td>{max_time:.2f}</td>
                    <td class="{status_class}">{status.upper()}</td>
                </tr>
                """

            html_content = html_template.format(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                benchmark_rows=benchmark_rows,
                total_tests=total_tests,
                passed_tests=passed_tests,
                failed_tests=failed_tests
            )

            # Write HTML report
            html_file = benchmark_file.with_suffix('.html')
            with open(html_file, 'w') as f:
                f.write(html_content)

            print(f"Performance report generated: {html_file}")

        except Exception as e:
            print(f"Error generating performance report: {e}")

    def run_custom_test_suite(self, test_pattern: str, **kwargs) -> int:
        """Run custom test suite based on file pattern or markers."""
        if test_pattern.startswith("tests/"):
            # File path pattern
            cmd = ["python", "-m", "pytest", str(self.project_root / test_pattern)]
        else:
            # Marker pattern
            return self.run_test_suite(markers=[test_pattern], **kwargs)

        # Add common options
        if kwargs.get("verbose", False):
            cmd.append("-v")

        result = subprocess.run(cmd, cwd=self.project_root)
        return result.returncode

    def check_test_environment(self) -> bool:
        """Check if test environment is properly configured."""
        print("Checking test environment...")

        # Check if test database is accessible
        try:
            result = subprocess.run(
                ["python", "-c", "from app.core.config import get_settings; print(get_settings().database_url)"],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print("✓ Database configuration accessible")
            else:
                print("✗ Database configuration error")
                return False
        except Exception as e:
            print(f"✗ Error checking database: {e}")
            return False

        # Check if Redis is accessible (optional)
        try:
            result = subprocess.run(
                ["python", "-c", "import redis; r = redis.Redis(); r.ping()"],
                cwd=self.project_root,
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                print("✓ Redis connection successful")
            else:
                print("⚠ Redis connection failed (optional for some tests)")
        except Exception:
            print("⚠ Redis not available (optional for some tests)")

        # Check if test files exist
        test_files = list(self.test_dir.glob("**/test_*.py"))
        if test_files:
            print(f"✓ Found {len(test_files)} test files")
        else:
            print("✗ No test files found")
            return False

        print("✓ Test environment ready")
        return True


def main():
    """Main entry point for test runner."""
    parser = argparse.ArgumentParser(description="Deal Desk OS Test Runner")

    parser.add_argument(
        "--category",
        choices=["unit", "integration", "e2e", "performance", "security", "sla", "smoke", "ci"],
        help="Test category to run"
    )
    parser.add_argument(
        "--markers",
        nargs="+",
        help="Custom pytest markers"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Generate coverage report"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run tests in parallel"
    )
    parser.add_argument(
        "--pattern",
        help="Custom test pattern (file path or marker)"
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip test report generation"
    )
    parser.add_argument(
        "--check-env",
        action="store_true",
        help="Check test environment before running tests"
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).parent.parent.parent,
        help="Project root directory"
    )

    args = parser.parse_args()

    # Initialize test runner
    runner = DealDeskTestRunner(args.project_root)

    # Check environment if requested
    if args.check_env:
        if not runner.check_test_environment():
            print("Test environment check failed")
            return 1
        return 0

    # Run appropriate test suite
    try:
        if args.category == "unit":
            exit_code = runner.run_unit_tests(coverage=args.coverage)
        elif args.category == "integration":
            exit_code = runner.run_integration_tests(coverage=args.coverage)
        elif args.category == "e2e":
            exit_code = runner.run_end_to_end_tests()
        elif args.category == "performance":
            exit_code = runner.run_performance_tests(generate_report=not args.no_report)
        elif args.category == "security":
            exit_code = runner.run_security_tests()
        elif args.category == "sla":
            exit_code = runner.run_sla_tests()
        elif args.category == "smoke":
            exit_code = runner.run_smoke_tests()
        elif args.category == "ci":
            exit_code = runner.run_ci_tests(parallel=args.parallel)
        elif args.pattern:
            exit_code = runner.run_custom_test_suite(
                args.pattern,
                verbose=args.verbose,
                coverage=args.coverage,
                parallel=args.parallel,
                generate_report=not args.no_report
            )
        else:
            # Default: run all tests
            exit_code = runner.run_test_suite(
                markers=args.markers,
                coverage=args.coverage,
                verbose=args.verbose,
                parallel=args.parallel,
                generate_report=not args.no_report
            )

        return exit_code

    except KeyboardInterrupt:
        print("\nTest execution interrupted")
        return 1
    except Exception as e:
        print(f"Error running tests: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())