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

Debug Mode:
    Use --debug flag to enable detailed test discovery information and debug-level logging.
    This helps troubleshoot issues with test detection and execution.

Options:
    -v, --verbose    - Show detailed output
    --debug          - Enable debug mode with verbose test discovery and debug logging
    --test-tags TAG  - Run specific test (e.g., TestOrderImporter or TestOrderImporter.test_import)
    -j, --json       - Output results as JSON
    -t, --timeout N  - Set timeout in seconds (default: 180)
"""

import re
import sys
import time
import subprocess
import argparse
import json
import socket
from pathlib import Path


def check_execution_context() -> None:
    """Check if the script is being run correctly and provide helpful guidance."""
    # Check if we're in a virtual environment
    in_venv = hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)

    # Get the project root (parent of tools directory)
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    expected_venv = project_root / ".venv"

    # Check if running from the correct directory
    cwd = Path.cwd()
    if cwd != project_root:
        print(f"⚠️  Warning: You should run this script from the project root directory.")
        print(f"   Current directory: {cwd}")
        print(f"   Expected directory: {project_root}")
        print()

    # Check if using the project's virtual environment
    if not in_venv:
        print("❌ Error: Not running in a virtual environment!")
        print()
        print("Please run this script using the project's virtual environment:")
        print(f"    {expected_venv}/bin/python {script_path.relative_to(project_root)}")
        print()
        print("Or activate the virtual environment first:")
        print(f"    source {expected_venv}/bin/activate")
        print(f"    python {script_path.relative_to(project_root)}")
        sys.exit(1)

    # Check if using the correct virtual environment
    venv_path = Path(sys.prefix)
    if venv_path != expected_venv and not venv_path.parts[-1].startswith("venv"):
        print(f"⚠️  Warning: You might be using a different virtual environment.")
        print(f"   Current venv: {venv_path}")
        print(f"   Expected venv: {expected_venv}")
        print()


class TestRunner:
    def __init__(
        self,
        verbose: bool = False,
        debug: bool = False,
        container: str = "odoo-opw-script-runner-1",
        database: str = "opw",
        addons_path: str = "/volumes/addons,/odoo/addons,/volumes/enterprise",
    ) -> None:
        self.verbose = verbose
        self.debug = debug
        self.container_name = container
        self.database = database
        self.addons_path = addons_path

        # Check if docker is available
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Error: Docker not found or not accessible: {e}")
            sys.exit(1)

        # Ensure required containers are running
        self._ensure_containers_running()

    def _ensure_containers_running(self) -> None:
        """Ensure required containers are running, start them if not."""
        containers_to_check = [
            {"name": "odoo-opw-script-runner-1", "service": "script-runner", "command": ["tail", "-f", "/dev/null"]},
            {
                "name": "odoo-opw-shell-1",
                "service": "shell",
                "command": None,  # Uses default command from docker-compose.yml
            },
        ]

        for container in containers_to_check:
            # Check if container is running
            check_cmd = ["docker", "ps", "--filter", f"name={container['name']}", "--format", "{{.Names}}"]
            result = subprocess.run(check_cmd, capture_output=True, text=True)

            if container["name"] not in result.stdout:
                if self.verbose:
                    print(f"Container {container['name']} not running, starting it...")

                # Start the container
                start_cmd = ["docker", "compose", "run", "-d", "--name", container["name"], container["service"]]
                if container["command"]:
                    start_cmd.extend(container["command"])

                try:
                    subprocess.run(start_cmd, capture_output=True, check=True, text=True)
                    if self.verbose:
                        print(f"Started container {container['name']}")
                    # Give container a moment to fully start
                    time.sleep(1)
                except subprocess.CalledProcessError as e:
                    # Container might already exist but be stopped
                    if "already in use" in str(e.stderr):
                        # Try to start existing container
                        restart_cmd = ["docker", "start", container["name"]]
                        try:
                            subprocess.run(restart_cmd, capture_output=True, check=True)
                            if self.verbose:
                                print(f"Restarted existing container {container['name']}")
                        except subprocess.CalledProcessError:
                            print(f"Error: Could not start container {container['name']}")
                            print("Please check your Docker setup and try again.")
                            sys.exit(1)
                    else:
                        print(f"Error starting container {container['name']}: {e.stderr}")
                        sys.exit(1)

    def get_available_port(self, start: int = 18080, end: int = 19000) -> int:
        """Find an available port, avoiding known conflicts."""
        # Common ports to avoid
        reserved_ports = {8069, 8070, 8071, 8072}  # Odoo web containers

        for port in range(start, end):
            if port in reserved_ports:
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("", port))
                    if self.verbose:
                        print(f"Selected available port: {port}")
                    return port
            except OSError:
                continue
        raise RuntimeError(f"No available ports found in range {start}-{end}")

    def cleanup_test_processes(self) -> bool:
        """Kill any lingering test processes in the container"""
        try:
            if self.verbose:
                print("Cleaning up any lingering test processes...")

            # Kill any odoo-bin test processes
            kill_cmd = ["docker", "exec", self.container_name, "sh", "-c", "pkill -f 'odoo-bin.*--test-enable' || true"]
            subprocess.run(kill_cmd, timeout=5)

            # Kill any lingering Chrome processes
            chrome_kill_cmd = ["docker", "exec", self.container_name, "sh", "-c", "pkill -f 'chromium|chrome' || true"]
            subprocess.run(chrome_kill_cmd, timeout=5)

            return True
        except Exception as e:
            if self.verbose:
                print(f"Error cleaning up test processes: {e}")
            return False

    @staticmethod
    def cleanup_docker_environment() -> bool:
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
        port = self.get_available_port()

        cmd = [
            "/odoo/odoo-bin",
            "-d",
            self.database,
            "--addons-path",
            self.addons_path,
            "--http-port",
            str(port),
        ] + args

        if self.verbose or self.debug:
            print(f"Running in {self.container_name}: {' '.join(cmd)}")

        if self.debug:
            print(f"Debug: Full docker command: docker exec -e PYTHONUNBUFFERED=1 {self.container_name} {' '.join(cmd)}")
            print(f"Debug: Using port {port} for test execution")
            print(f"Debug: Timeout set to {timeout} seconds")

        try:
            # Simple approach: direct docker exec with timeout
            docker_cmd = ["docker", "exec", "-e", "PYTHONUNBUFFERED=1", self.container_name] + cmd

            # Run with subprocess timeout
            result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout)

            # Combine stdout and stderr for consistent output
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr

            return result.returncode, output

        except subprocess.TimeoutExpired as e:
            # Kill any remaining processes in container matching our command
            kill_cmd = ["docker", "exec", self.container_name, "pkill", "-f", f"http-port.{port}"]
            try:
                subprocess.run(kill_cmd, timeout=5)
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
                pass  # Ignore errors in cleanup

            # Try to get partial output if available
            output = ""
            if hasattr(e, "stdout") and e.stdout:
                output = e.stdout.decode(errors="ignore")

            return -1, f"Command timed out after {timeout} seconds (killed by Python)\n{output}"
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

        if self.debug:
            print(f"Debug: Discovering tests in container {self.container_name}")
            print(f"Debug: Searching for test files in /volumes/addons/product_connect")

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

            if self.debug:
                print(f"Debug: Running test file discovery: {' '.join(find_cmd)}")

            result = subprocess.run(find_cmd, capture_output=True, text=True)

            if result.returncode == 0:
                found_files = [f for f in result.stdout.strip().split("\n") if f]
                if self.debug:
                    print(f"Debug: Found {len(found_files)} test files:")
                    for file_path in found_files:
                        print(f"  - {file_path}")

                for file_path in found_files:
                    if file_path:
                        # Extract test methods from file
                        grep_cmd = ["docker", "exec", self.container_name, "grep", "-E", "^\\s*def test_", file_path]

                        if self.debug:
                            print(f"Debug: Scanning {file_path} for test methods...")

                        grep_result = subprocess.run(grep_cmd, capture_output=True, text=True)

                        if grep_result.returncode == 0:
                            methods_found = []
                            for line in grep_result.stdout.strip().split("\n"):
                                if line:
                                    method = re.search(r"def (test_\w+)", line)
                                    if method:
                                        method_name = method.group(1)
                                        test_files["python"].append(f"{file_path.split('/')[-1]}::{method_name}")
                                        methods_found.append(method_name)

                            if self.debug and methods_found:
                                print(
                                    f"  Found {len(methods_found)} test methods: {', '.join(methods_found[:3])}{'...' if len(methods_found) > 3 else ''}"
                                )
                        else:
                            if self.debug:
                                print(f"  No test methods found in {file_path}")
            else:
                if self.debug:
                    print(f"Debug: Test file discovery failed: {result.stderr}")

        except subprocess.SubprocessError as e:
            if self.debug:
                print(f"Debug: Error during test discovery: {e}")

        if self.debug:
            print(f"Debug: Test discovery complete. Found {len(test_files['python'])} Python tests")

        return test_files

    def run_tests(
        self, test_type: str = "all", specific_test: str | None = None, timeout: int = 180, show_details: bool = False
    ) -> dict[str, int | str | list[str] | dict[str, str] | float]:
        # Clean up any lingering test processes before starting
        if self.debug:
            print(f"Debug: Cleaning up any lingering test processes...")
        self.cleanup_test_processes()

        # Run tests with proper isolation to avoid locks
        # Use --workers=0 and --db-filter to isolate database access
        # Always load product_connect module for test discovery
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
            args = [
                "-i",
                "product_connect",
                "--test-enable",
                "--stop-after-init",
                "--max-cron-threads=0",
                "--workers=0",
                f"--db-filter=^{self.database}$",
            ]

        # Adjust log level based on what we need
        if self.debug:
            args.append("--log-level=debug")
            if self.debug:
                print(f"Debug: Using debug log level for detailed test discovery")
        elif show_details:
            args.append("--log-level=info")
        else:
            # Need at least info level to get test results in Odoo 18
            args.append("--log-level=info")

        if self.verbose or self.debug:
            print(f"Test type: {test_type}, Specific test: {specific_test}")

        if self.debug:
            print(f"Debug: Database filter: ^{self.database}$")
            print(f"Debug: Addons path: {self.addons_path}")
            print(f"Debug: Container: {self.container_name}")

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
            # Run Python tests with Odoo 18 standard tags
            # Our tests use @tagged("post_install", "-at_install") from base classes
            args.append("--test-tags=post_install,-at_install")
        elif test_type == "js":
            # Run JavaScript tests via Python test runner
            args.append("--test-tags=/product_connect:ProductConnectJSTests")
        elif test_type == "tour":
            # Run tour tests - they'll be discovered by location and structure
            args.append("--test-tags=post_install,-at_install")
        elif test_type == "all":
            # Run all tests: Python tests + Tour tests
            # Using standard Odoo 18 tags that our base classes provide
            args.append("--test-tags=post_install,-at_install")
        else:
            args.append(f"--test-tags={test_type}")

        if specific_test:
            print(f"Running specific test: {specific_test}")
        else:
            print(f"Running {test_type} tests...")

        if self.verbose or self.debug:
            print(f"Test command args: {args}")

        if self.debug:
            print(f"Debug: About to execute test command with {len(args)} arguments")
            print(f"Debug: Expected test discovery process:")
            print(f"  1. Odoo will scan addons path for modules")
            print(f"  2. Module 'product_connect' will be loaded")
            print(f"  3. Test files matching pattern will be discovered")
            print(f"  4. Tests matching tags will be executed")
            print(f"Debug: Starting test execution...")

        if self.debug:
            print(f"Debug: Test discovery will search for tests matching the following criteria:")
            if specific_test:
                print(f"  - Specific test pattern: {specific_test}")
            if test_type == "python":
                print(f"  - Python tests with tags: post_install,-at_install")
            elif test_type == "tour":
                print(f"  - Tour tests with tags: post_install,-at_install")
            elif test_type == "all":
                print(f"  - All tests with tags: post_install,-at_install")
            print(f"  - Module path: /volumes/addons/product_connect")
            print(f"  - Test file pattern: test_*.py in tests/ subdirectories")

        start_time = time.time()

        if self.debug:
            print(f"Debug: Test execution started at {time.strftime('%H:%M:%S')}")

        returncode, output = self.run_command(args, timeout)

        elapsed = time.time() - start_time
        print(f"Tests completed in {elapsed:.1f} seconds")

        if self.debug:
            print(f"Debug: Test execution finished at {time.strftime('%H:%M:%S')}")
            print(f"Debug: Return code: {returncode}")
            print(f"Debug: Output length: {len(output)} characters")
            if returncode != 0:
                print(f"Debug: Non-zero return code indicates test failures or errors")

        if returncode == -1:
            return {"error": "timeout", "elapsed": elapsed}

        results = self.parse_test_results(output)
        results["elapsed"] = elapsed
        results["returncode"] = returncode

        # Save raw output if verbose
        if self.verbose or self.debug:
            results["raw_output"] = output
            # Also save last 100 lines for debugging
            lines = output.split("\n")
            results["output_tail"] = "\n".join(lines[-100:])

        if self.debug:
            # Show a sample of the output for debugging
            lines = output.split("\n")
            print(f"Debug: Sample output (first 10 lines):")
            for i, line in enumerate(lines[:10]):
                print(f"  {i + 1:2d}: {line}")
            if len(lines) > 20:
                print(f"  ... ({len(lines) - 20} lines omitted) ...")
                print(f"Debug: Sample output (last 10 lines):")
                for i, line in enumerate(lines[-10:], len(lines) - 9):
                    print(f"  {i:2d}: {line}")

        # Clean up Docker environment after tests
        # This removes any stopped containers and other Docker artifacts
        if test_type in ["js", "tour", "all"]:
            TestRunner.cleanup_docker_environment()

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
        # Use recommended timeout for 'all' tests
        timeout = get_recommended_timeout("all")
        results = self.run_tests(timeout=timeout)
        failures = results.get("failures", [])
        errors_list = results.get("errors_list", [])
        # Ensure we have lists before concatenating
        if isinstance(failures, list) and isinstance(errors_list, list):
            return failures + errors_list
        return []


def get_recommended_timeout(test_type: str, specific_test: str | None = None) -> int:
    """Get recommended timeout based on test scope.

    Based on our test suite analysis:
    - 321 test methods total
    - 42 browser-based tests
    - Estimated runtime: 16-24 minutes for full suite
    """
    # Individual test method (e.g., TestClass.test_method)
    if specific_test and "." in specific_test:
        return 60  # 1 minute for individual test method
    # Specific test class (e.g., TestClass)
    elif specific_test:
        return 300  # 5 minutes for specific test class
    # Test type specific timeouts
    elif test_type == "all":
        return 1800  # 30 minutes for full suite (16-24 min estimate + buffer)
    elif test_type == "tour":
        return 420  # 7 minutes for browser tests
    elif test_type == "python":
        return 480  # 8 minutes for Python-only tests
    elif test_type == "js":
        return 180  # 3 minutes for JS tests
    else:
        return 300  # 5 minutes default for other cases


def main() -> None:
    # Check execution context before doing anything else
    check_execution_context()

    parser = argparse.ArgumentParser(description="Odoo Test Runner")
    parser.add_argument(
        "test_type",
        nargs="?",
        default="summary",
        choices=["all", "python", "js", "tour", "summary", "failing"],
        help="Type of tests to run",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show detailed output")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode with verbose test discovery and debug logging")
    parser.add_argument("-t", "--timeout", type=int, default=None, help="Timeout in seconds (default: varies by test type)")
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

    runner = TestRunner(
        verbose=args.verbose, debug=args.debug, container=args.container, database=args.database, addons_path=args.addons_path
    )

    # Update module if requested
    if args.update:
        if not runner.update_module():
            sys.exit(1)

    # Determine timeout - use user-specified or recommended based on test type
    timeout = args.timeout
    if timeout is None:
        timeout = get_recommended_timeout(args.test_type, args.test_tags)
        if args.verbose or args.debug:
            print(f"Using recommended timeout: {timeout} seconds ({timeout // 60} minutes)")
        if args.debug:
            print(f"Debug: Timeout calculation based on test_type='{args.test_type}', specific_test='{args.test_tags}'")

    # Handle special commands
    if args.debug:
        print(f"Debug: Executing command '{args.test_type}' with test_tags='{args.test_tags}'")

    if args.test_type == "summary":
        # Just run all tests and show summary
        results = runner.run_tests(specific_test=args.test_tags, timeout=timeout)
    elif args.test_type == "failing":
        # Show only failing tests
        failing = runner.get_failing_tests()
        results = {"failing_tests": failing, "count": len(failing)}
    else:
        # Run specified test type
        results = runner.run_tests(
            args.test_type, specific_test=args.test_tags, timeout=timeout, show_details=args.verbose or args.debug
        )

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
                if args.debug:
                    print(f"\nDebug: Test discovery troubleshooting:")
                    print(f"  - Verify product_connect module is installed and loadable")
                    print(f"  - Check that test files exist in addons/product_connect/tests/")
                    print(f"  - Ensure test classes inherit from proper base classes")
                    print(f"  - Verify test methods start with 'test_' and have proper decorators")
                    print(f"  - Check that @tagged decorators match the test tags being used")
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
