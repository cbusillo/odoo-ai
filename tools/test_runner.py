#!/usr/bin/env python
import re
import sys
import time
import threading
import argparse
import random
import json
import docker
from docker.errors import DockerException


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

        try:
            self.docker_client = docker.from_env()
        except DockerException as e:
            print(f"Error connecting to Docker: {e}")
            sys.exit(1)
            
    def restart_container(self) -> bool:
        """Restart the test container to clean up all zombie processes."""
        try:
            container = self.docker_client.containers.get(self.container_name)
            print(f"Restarting container {self.container_name} to clean up zombie processes...")
            container.restart(timeout=30)
            # Wait for container to be ready
            time.sleep(5)
            print("Container restarted successfully")
            return True
        except Exception as e:
            print(f"Failed to restart container: {e}")
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
            container = self.docker_client.containers.get(self.container_name)

            # Execute command with timeout
            # Note: docker-py doesn't support timeout in exec_run directly,
            # but we can use a thread with a timer for proper timeout handling
            class ResultContainer:
                def __init__(self) -> None:
                    self.result = None
                    self.error = None

            container_result = ResultContainer()

            def run_exec() -> None:
                try:
                    # Set environment for test execution
                    env = {
                        "PYTHONUNBUFFERED": "1",
                        # CHROME_BIN is already set in Dockerfile
                    }
                    # Run with stderr merged to stdout to capture all output
                    container_result.result = container.exec_run(cmd, stderr=True, stdout=True, demux=False, environment=env)
                except Exception as exec_error:
                    container_result.error = exec_error

            thread = threading.Thread(target=run_exec)
            thread.start()
            thread.join(timeout=timeout)

            if thread.is_alive():
                # Timeout occurred
                return -1, f"Command timed out after {timeout} seconds"

            if container_result.error:
                raise container_result.error

            result = container_result.result

            # Get output
            output = result.output.decode("utf-8", errors="replace")

            return result.exit_code, output

        except docker.errors.NotFound:
            return -1, f"Container '{self.container_name}' not found"
        except docker.errors.APIError as e:
            return -1, f"Docker API error: {e}"
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
        }

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

        # Extract specific error details if requested
        if self.verbose:
            # Look for tracebacks
            traceback_pattern = r"(FAIL|ERROR): (Test\w+\.test_\w+)(.*?)(?=(?:FAIL|ERROR):|$)"
            for match in re.finditer(traceback_pattern, output, re.DOTALL):
                status, test_name, details = match.groups()
                # Extract just the key error line
                error_match = re.search(r"(AssertionError:|ERROR:|DETAIL:).*", details)
                if error_match:
                    error_line = error_match.group().strip()
                    if "error_details" not in results:
                        results["error_details"] = {}
                    results["error_details"][test_name] = error_line

        return results

    def list_tests(self) -> dict[str, list[str]]:
        """List all available tests by scanning test files in the container"""
        test_files = {"python": [], "js": [], "tour": []}

        try:
            container = self.docker_client.containers.get(self.container_name)

            # Find Python test files
            find_cmd = ["find", "/volumes/addons/product_connect", "-name", "test_*.py", "-type", "f"]
            result = container.exec_run(find_cmd, stderr=False)

            if result.exit_code == 0:
                output = result.output.decode("utf-8", errors="replace")
                for file_path in output.strip().split("\n"):
                    if file_path:
                        # Extract test methods from file
                        grep_cmd = ["grep", "-E", "^\\s*def test_", file_path]
                        grep_result = container.exec_run(grep_cmd, stderr=False)

                        if grep_result.exit_code == 0:
                            grep_output = grep_result.output.decode("utf-8", errors="replace")
                            for line in grep_output.strip().split("\n"):
                                if line:
                                    method = re.search(r"def (test_\w+)", line)
                                    if method:
                                        test_files["python"].append(f"{file_path.split('/')[-1]}::{method.group(1)}")

        except (docker.errors.NotFound, docker.errors.APIError):
            pass

        return test_files

    def run_tests(
        self, test_type: str = "all", specific_test: str | None = None, timeout: int = 180, show_details: bool = False
    ) -> dict[str, int | str | list[str] | dict[str, str] | float]:
        # CRITICAL: Odoo requires module update to run tests
        args = ["-u", "product_connect", "--test-enable", "--stop-after-init", "--max-cron-threads=0"]

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
            # Run all post_install tests (our Python tests)
            args.append("--test-tags=post_install")
        elif test_type == "js":
            args.append("--test-tags=product_connect_js")
        elif test_type == "tour":
            args.append("--test-tags=product_connect_tour")
        elif test_type == "all":
            # Run all our tests - Odoo doesn't support comma-separated tags well
            # Instead, we use the module tag which should run all tests
            args.append("--test-tags=product_connect,post_install,product_connect_js,product_connect_tour")
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
            lines = output.split('\n')
            results["output_tail"] = '\n'.join(lines[-100:])
        
        # Restart container after browser tests to clean up zombie Chrome processes
        # This leaves a clean environment for the next test run
        if test_type in ["js", "tour", "all"]:
            print("\nCleaning up test environment...")
            self.restart_container()

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
        results = runner.run_tests(test_type="all", specific_test=args.test_tags, timeout=args.timeout)
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
        else:
            print(f"\n=== Test Results ===")
            print(f"Total:  {results.get('total', 0)}")
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
