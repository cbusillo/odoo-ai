#!/usr/bin/env python
"""
Odoo Test Runner - Enhanced test execution for product_connect module

This tool runs Odoo tests in a Docker container using CLI commands (no Docker SDK required).
It provides better output formatting, test filtering, and error reporting than raw Odoo commands.

Usage:
    .venv/bin/python tools/test_runner.py [command] [options]

Commands:
    summary - Run all tests and show summary (default)
    all     - Run all tests with details
    python  - Run Python tests only
    failing - List currently failing tests

Options:
    -v, --verbose    - Show detailed output
    --test-tags TAG  - Run specific test (e.g., TestOrderImporter or TestOrderImporter.test_import)
    -j, --json       - Output results as JSON
    -t, --timeout N  - Set timeout in seconds (default: 180)
"""

import re
import sys
import time
import subprocess
import argparse
import random
import json


class TestRunner:
    def __init__(
        self,
        verbose: bool = False,
        container: str = "odoo-opw-script-runner-1",
        database: str = "opw",
        addons_path: str = "/volumes/addons,/odoo/addons,/volumes/enterprise",
    ) -> None:
        self.verbose = verbose
        self.container_name = container
        self.database = database
        self.addons_path = addons_path

        # Check if docker is available
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Error: Docker not found or not accessible: {e}")
            sys.exit(1)

    def cleanup_docker_environment(self) -> bool:
        """Clean up Docker environment after tests."""
        try:
            print("Cleaning up Docker environment...")
            # Run docker system prune to clean up:
            # - all stopped containers
            # - all networks not used by at least one container
            # - all dangling images
            # - all dangling build cache
            # Note: Named volumes are NOT removed by default
            prune_cmd = ["docker", "system", "prune", "-f", "--filter", "label!=com.docker.compose.version"]
            result = subprocess.run(prune_cmd, capture_output=True, text=True)

            if result.stdout:
                print(f"Docker cleanup: {result.stdout.strip()}")

            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to clean up Docker: {e}")
            return False

    def run_command(self, args: list[str], timeout: int = 180) -> tuple[int, str]:
        port = random.randint(8080, 18079)

        cmd = [
            "/odoo/odoo-bin",
            "-d",
            self.database,
            "--addons-path",
            self.addons_path,
            "--http-port",
            str(port),
        ] + args

        if self.verbose:
            print(f"Running in {self.container_name}: {' '.join(cmd)}")

        try:
            # Build docker exec command to use existing container
            docker_cmd = ["docker", "exec", "-e", "PYTHONUNBUFFERED=1", self.container_name] + cmd

            # Run with timeout
            result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout)

            # Combine stdout and stderr for consistent output
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr

            return result.returncode, output

        except subprocess.TimeoutExpired:
            return -1, f"Command timed out after {timeout} seconds"
        except FileNotFoundError:
            return -1, f"Docker command not found"
        except Exception as e:
            return -1, f"Unexpected error: {e}"

    def parse_test_results(self, output: str) -> dict[str, int | str | list[str] | dict[str, str] | float]:
        results: dict[str, int | str | list[str] | dict[str, str] | float] = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "failures": [],
            "errors_list": [],
            "summary": "",
            "loading_failed": False,
            "loading_error": "",
        }

        # Check for module loading failures first
        if "Failed to load registry" in output or "Failed to initialize database" in output:
            results["loading_failed"] = True
            # Extract the specific error
            error_match = re.search(r"(TypeError: Model.*|AttributeError:.*|ImportError:.*|.*Error:.*)", output)
            if error_match:
                results["loading_error"] = error_match.group(1).strip()
            else:
                results["loading_error"] = "Module loading failed (check logs for details)"
            results["summary"] = f"❌ Module loading failed: {results['loading_error']}"
            return results

        # Extract overall summary - handle different Odoo output formats
        # First try Odoo's test result line (match both with and without "when loading database")
        summary_match = re.search(r"(\d+) failed, (\d+) error\(s\) of (\d+) tests", output)
        if summary_match:
            results["failed"] = int(summary_match.group(1))
            results["errors"] = int(summary_match.group(2))
            results["total"] = int(summary_match.group(3))
            results["passed"] = results["total"] - results["failed"] - results["errors"]
            results["summary"] = summary_match.group()
        else:
            # Try alternative format: "Ran X tests in Y.Z seconds"
            ran_match = re.search(r"Ran (\d+) tests? in", output)
            if ran_match:
                results["total"] = int(ran_match.group(1))
                # Look for failure/error counts
                if "FAILED" in output:
                    fail_match = re.search(r"FAILED \(.*?failures=(\d+)", output)
                    error_match = re.search(r"errors=(\d+)", output)
                    results["failed"] = int(fail_match.group(1)) if fail_match else 0
                    results["errors"] = int(error_match.group(1)) if error_match else 0
                else:
                    results["failed"] = 0
                    results["errors"] = 0
                results["passed"] = results["total"] - results["failed"] - results["errors"]
                results["summary"] = f"{results['failed']} failed, {results['errors']} error(s) of {results['total']} tests"

        # Extract individual failures/errors
        failure_pattern = r"(FAIL|ERROR): (Test\w+\.test_\w+)"
        for match in re.finditer(failure_pattern, output):
            status, test_name = match.groups()
            if status == "FAIL":
                results["failures"].append(test_name)
            else:
                results["errors_list"].append(test_name)

        # Extract specific error details - always extract for tour tests
        if self.verbose or "tour" in output.lower():
            # Look for tour-specific errors
            tour_error_pattern = r'The test code "odoo\.startTour\([^)]+\)" failed'
            if re.search(tour_error_pattern, output) or "OwlError" in output or "UncaughtPromiseError" in output:
                # Extract browser console errors
                console_error_pattern = (
                    r"(Console error:|Browser error:|JavaScript error:|UncaughtPromiseError|OwlError)(.*?)(?=\n\d{4}-|$)"
                )
                console_errors = []
                for match in re.finditer(console_error_pattern, output, re.DOTALL):
                    error_text = match.group(2).strip()
                    if error_text:
                        console_errors.append(f"{match.group(1)}: {error_text}")
                if console_errors:
                    results["browser_errors"] = console_errors

                # Extract tour step failures
                tour_step_pattern = r"Tour step failed: (.*?)(?=\n|$)"
                tour_steps = []
                for match in re.finditer(tour_step_pattern, output):
                    tour_steps.append(match.group(1).strip())
                if tour_steps:
                    results["failed_tour_steps"] = tour_steps

                # Look for specific error messages in tour output
                error_patterns = [
                    r"(UncaughtPromiseError.*?OwlError.*?)(?=\n|$)",
                    r"(Uncaught Promise.*?)(?=\n|$)",
                    r"(OwlError:.*?)(?=\n|$)",
                    r"(TypeError:.*?)(?=\n|$)",
                    r"(ReferenceError:.*?)(?=\n|$)",
                    r"Cannot read properties of.*?(?=\n|$)",
                    r"Invalid props for component.*?(?=\n|$)",
                ]

                for pattern in error_patterns:
                    for match in re.finditer(pattern, output, re.MULTILINE):
                        error_msg = match.group().strip()
                        if error_msg and error_msg not in console_errors:
                            console_errors.append(error_msg)

                if console_errors:
                    results["browser_errors"] = console_errors

            # Look for tracebacks
            traceback_pattern = r"(FAIL|ERROR): (Test\w+\.test_\w+)(.*?)(?=(?:FAIL|ERROR):|$)"
            for match in re.finditer(traceback_pattern, output, re.DOTALL):
                status, test_name, details = match.groups()
                # Extract more detailed error info
                error_lines = []
                for line in details.split("\n"):
                    if any(
                        keyword in line
                        for keyword in ["AssertionError:", "ERROR:", "DETAIL:", "TypeError:", "ReferenceError:", "Error:"]
                    ):
                        error_lines.append(line.strip())
                if error_lines:
                    if "error_details" not in results:
                        results["error_details"] = {}
                    results["error_details"][test_name] = "\n".join(error_lines)

        return results

    def list_tests(self) -> dict[str, list[str]]:
        """List all available tests by scanning test files in the container"""
        test_files = {"python": [], "js": [], "tour": []}

        try:
            # Find Python test files
            find_cmd = [
                "docker",
                "exec",
                self.container_name,
                "find",
                "/volumes/addons/product_connect",
                "-name",
                "test_*.py",
                "-type",
                "f",
            ]
            result = subprocess.run(find_cmd, capture_output=True, text=True)

            if result.returncode == 0:
                for file_path in result.stdout.strip().split("\n"):
                    if file_path:
                        # Extract test methods from file
                        grep_cmd = ["docker", "exec", self.container_name, "grep", "-E", "^\\s*def test_", file_path]
                        grep_result = subprocess.run(grep_cmd, capture_output=True, text=True)

                        if grep_result.returncode == 0:
                            for line in grep_result.stdout.strip().split("\n"):
                                if line:
                                    method = re.search(r"def (test_\w+)", line)
                                    if method:
                                        test_files["python"].append(f"{file_path.split('/')[-1]}::{method.group(1)}")

        except subprocess.SubprocessError:
            pass

        return test_files

    def run_tests(
        self, test_type: str = "all", specific_test: str | None = None, timeout: int = 180, show_details: bool = False
    ) -> dict[str, int | str | list[str] | dict[str, str] | float]:
        # Run tests with proper isolation to avoid locks
        # Use --workers=0 and --db-filter to isolate database access
        # Only update module if explicitly requested to avoid timeouts
        if hasattr(self, "_force_update") and self._force_update:
            args = [
                "-u",
                "product_connect",
                "--test-enable",
                "--stop-after-init",
                "--max-cron-threads=0",
                "--workers=0",
                f"--db-filter=^{self.database}$",
            ]
        else:
            args = ["--test-enable", "--stop-after-init", "--max-cron-threads=0", "--workers=0", f"--db-filter=^{self.database}$"]

        # Adjust log level based on what we need
        if show_details:
            args.append("--log-level=info")
        else:
            # Need at least info level to get test results in Odoo 18
            args.append("--log-level=info")

        if self.verbose:
            print(f"Test type: {test_type}, Specific test: {specific_test}")

        # Determine test tags based on our actual test structure
        if specific_test:
            # Handle specific test class or method
            # Odoo format is: [-][tag][/module][:class][.method]
            if specific_test.startswith("/"):
                # Already has module prefix: /module:class.method
                args.append(f"--test-tags={specific_test}")
            elif ":" in specific_test and "/" in specific_test:
                # Full format provided: tag/module:class.method
                args.append(f"--test-tags={specific_test}")
            elif "." in specific_test:
                # Class.method format - add module prefix
                args.append(f"--test-tags=/product_connect:{specific_test}")
            elif specific_test.startswith("Test"):
                # Just a test class name
                args.append(f"--test-tags=/product_connect:{specific_test}")
            else:
                # Assume it's a test tag
                args.append(f"--test-tags={specific_test}")
        elif test_type == "python":
            # Run all tests in our modules using module path
            args.append("--test-tags=/product_connect,/disable_odoo_online")
        elif test_type == "js":
            # Run JavaScript tests by file pattern
            args.append("--test-tags=/product_connect:*.test.js")
        elif test_type == "tour":
            # Run tour tests by file pattern
            args.append("--test-tags=/product_connect:*tour*")
        elif test_type == "all":
            # Run all tests in our modules - module path runs ALL tests in that module
            args.append("--test-tags=/product_connect,/disable_odoo_online")
        else:
            args.append(f"--test-tags={test_type}")

        if specific_test:
            print(f"Running specific test: {specific_test}")
        else:
            print(f"Running {test_type} tests...")

        if self.verbose:
            print(f"Test command args: {args}")

        start_time = time.time()

        returncode, output = self.run_command(args, timeout)

        elapsed = time.time() - start_time
        print(f"Tests completed in {elapsed:.1f} seconds")

        if returncode == -1:
            return {"error": "timeout", "elapsed": elapsed}

        results = self.parse_test_results(output)
        results["elapsed"] = elapsed
        results["returncode"] = returncode

        # Save raw output if verbose
        if self.verbose:
            results["raw_output"] = output
            # Also save last 100 lines for debugging
            lines = output.split("\n")
            results["output_tail"] = "\n".join(lines[-100:])

        # Clean up Docker environment after tests
        # This removes any stopped containers and other Docker artifacts
        if test_type in ["js", "tour", "all"]:
            self.cleanup_docker_environment()

        return results

    def update_module(self) -> bool:
        print("Updating product_connect module...")
        args = ["-u", "product_connect", "--stop-after-init"]
        returncode, output = self.run_command(args, timeout=60)

        if returncode == 0:
            print("Module updated successfully")
            return True
        else:
            print(f"Module update failed: {output[-500:]}")
            return False

    def get_failing_tests(self) -> list[str]:
        results = self.run_tests(timeout=240)
        failures = results.get("failures", [])
        errors_list = results.get("errors_list", [])
        # Ensure we have lists before concatenating
        if isinstance(failures, list) and isinstance(errors_list, list):
            return failures + errors_list
        return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Odoo Test Runner")
    parser.add_argument(
        "test_type",
        nargs="?",
        default="summary",
        choices=["all", "python", "js", "tour", "summary", "failing"],
        help="Type of tests to run",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show detailed output")
    parser.add_argument("-t", "--timeout", type=int, default=180, help="Timeout in seconds (default: 180)")
    parser.add_argument(
        "--test-tags", type=str, help="Run specific test tags (e.g., TestOrderImporter or TestOrderImporter.test_import)"
    )
    parser.add_argument("-u", "--update", action="store_true", help="Update module before running tests")
    parser.add_argument("-j", "--json", action="store_true", help="Output results as JSON")
    parser.add_argument(
        "-c",
        "--container",
        type=str,
        default="odoo-opw-script-runner-1",
        help="Docker container name (default: odoo-opw-script-runner-1)",
    )
    parser.add_argument("-d", "--database", type=str, default="opw", help="Database name (default: opw)")
    parser.add_argument(
        "-p",
        "--addons-path",
        type=str,
        default="/volumes/addons,/odoo/addons,/volumes/enterprise",
        help="Addons path (default: /volumes/addons,/odoo/addons,/volumes/enterprise)",
    )

    args = parser.parse_args()

    runner = TestRunner(verbose=args.verbose, container=args.container, database=args.database, addons_path=args.addons_path)

    # Update module if requested
    if args.update:
        if not runner.update_module():
            sys.exit(1)

    # Handle special commands
    if args.test_type == "summary":
        # Just run all tests and show summary
        results = runner.run_tests(specific_test=args.test_tags, timeout=args.timeout)
    elif args.test_type == "failing":
        # Show only failing tests
        failing = runner.get_failing_tests()
        results = {"failing_tests": failing, "count": len(failing)}
    else:
        # Run specified test type
        results = runner.run_tests(args.test_type, specific_test=args.test_tags, timeout=args.timeout, show_details=args.verbose)

    # Output results
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        # Human readable output
        if "error" in results:
            print(f"\n❌ Error: {results['error']}")
        elif results.get("loading_failed"):
            print(f"\n=== Test Results ===")
            print(f"❌ Module Loading Failed!")
            print(f"Error: {results.get('loading_error', 'Unknown loading error')}")
            print(f"\nThis means 0 tests were found due to module loading failure, not because there are no tests.")
            print(f"Check the error above and fix the module before running tests.")
        else:
            print(f"\n=== Test Results ===")
            total = results.get("total", 0)
            if total == 0:
                print(f"⚠️  No tests found - this may indicate a configuration issue")
                print(f"   Check that test tags are correct and module is properly loaded")
            print(f"Total:  {total}")
            print(f"Passed: {results.get('passed', 0)} ✅")
            print(f"Failed: {results.get('failed', 0)} ❌")
            print(f"Errors: {results.get('errors', 0)} 💥")

            if results.get("failures"):
                print(f"\n=== Failed Tests ===")
                for test in results["failures"][:10]:
                    print(f"  FAIL: {test}")
                if len(results["failures"]) > 10:
                    print(f"  ... and {len(results['failures']) - 10} more")

            if results.get("errors_list"):
                print(f"\n=== Error Tests ===")
                for test in results["errors_list"][:10]:
                    print(f"  ERROR: {test}")
                if len(results["errors_list"]) > 10:
                    print(f"  ... and {len(results['errors_list']) - 10} more")

            if args.verbose and results.get("error_details"):
                print(f"\n=== Error Details ===")
                error_details = results.get("error_details", {})
                if isinstance(error_details, dict):
                    for test, error in list(error_details.items())[:5]:
                        print(f"\n{test}:")
                        print(f"  {error}")

            # Always show browser errors for tour tests
            if results.get("browser_errors"):
                print(f"\n=== Browser Console Errors ===")
                for error in results["browser_errors"][:10]:
                    print(f"  ❌ {error}")
                if len(results["browser_errors"]) > 10:
                    print(f"  ... and {len(results['browser_errors']) - 10} more")

            if results.get("failed_tour_steps"):
                print(f"\n=== Failed Tour Steps ===")
                for step in results["failed_tour_steps"][:5]:
                    print(f"  ❌ {step}")
                if len(results["failed_tour_steps"]) > 5:
                    print(f"  ... and {len(results['failed_tour_steps']) - 5} more")

            if "failing_tests" in results:
                print(f"\n=== Currently Failing Tests ({results['count']}) ===")
                for test in results["failing_tests"]:
                    print(f"  - {test}")

    # Exit with appropriate code
    if results.get("failed", 0) > 0 or results.get("errors", 0) > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
