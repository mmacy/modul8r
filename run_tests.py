#!/usr/bin/env python3
"""
Test runner script for modul8r with different test categories.
"""

import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle output."""
    print(f"\n{'=' * 60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print("=" * 60)

    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Run modul8r tests")
    parser.add_argument(
        "test_type",
        choices=["unit", "integration", "e2e", "phase1", "all", "fast", "slow"],
        help="Type of tests to run",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--no-cov", action="store_true", help="Skip coverage reporting")

    args = parser.parse_args()

    # Base pytest command
    base_cmd = ["uv", "run", "pytest"]

    if args.verbose:
        base_cmd.extend(["-v", "-s"])

    success = True

    if args.test_type == "unit":
        # Run unit tests (fast, no external dependencies)
        cmd = base_cmd + ["tests/test_services.py", "tests/test_phase1_components.py", "-m", "not slow"]
        success &= run_command(cmd, "Unit Tests")

    elif args.test_type == "integration":
        # Run integration tests (may use mocked external services)
        cmd = base_cmd + ["tests/test_main.py", "tests/test_playwright.py", "-m", "not slow"]
        success &= run_command(cmd, "Integration Tests")

    elif args.test_type == "e2e":
        # Run end-to-end tests with real services
        print("\n⚠️  E2E tests require OPENAI_API_KEY and will make real API calls!")
        print("⚠️  These tests may take several minutes and cost money!")
        response = input("Continue? (y/N): ")

        if response.lower() != "y":
            print("E2E tests cancelled.")
            return

        cmd = base_cmd + ["tests/test_e2e_real_modules.py", "-m", "slow"]
        success &= run_command(cmd, "End-to-End Tests with Real Modules")

    elif args.test_type == "phase1":
        # Run Phase 1 specific tests
        cmd = base_cmd + ["tests/test_phase1_components.py", "-m", "phase1 or not slow"]
        success &= run_command(cmd, "Phase 1 Foundation Safeguards Tests")

    elif args.test_type == "fast":
        # Run all fast tests (no external API calls)
        cmd = base_cmd + ["-m", "not slow", "tests/"]
        success &= run_command(cmd, "Fast Tests (No External Dependencies)")

    elif args.test_type == "slow":
        # Run only slow tests
        print("\n⚠️  Slow tests require OPENAI_API_KEY and will make real API calls!")
        print("⚠️  These tests may take several minutes and cost money!")
        response = input("Continue? (y/N): ")

        if response.lower() != "y":
            print("Slow tests cancelled.")
            return

        cmd = base_cmd + ["-m", "slow", "tests/"]
        success &= run_command(cmd, "Slow Tests (Real API Calls)")

    elif args.test_type == "all":
        # Run all tests in sequence
        print("\n⚠️  This will run ALL tests including real API calls!")
        print("⚠️  This may take a long time and cost money!")
        response = input("Continue? (y/N): ")

        if response.lower() != "y":
            print("All tests cancelled.")
            return

        # Fast tests first
        cmd = base_cmd + ["-m", "not slow", "tests/"]
        success &= run_command(cmd, "Fast Tests")

        # Then slow tests
        if success:
            cmd = base_cmd + ["-m", "slow", "tests/"]
            success &= run_command(cmd, "Slow Tests")

    # Summary
    print(f"\n{'=' * 60}")
    if success:
        print("✅ All tests completed successfully!")
    else:
        print("❌ Some tests failed. Check output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
