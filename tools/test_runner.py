#!/usr/bin/env python3

import re
import sys
import time
import subprocess
import argparse
import json
import socket
import random
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict


@dataclass
class TestProgress:
    phase: str = "starting"
    current_test: str = ""
    tests_completed: int = 0
    tests_total: int = 0
    last_update: float = 0
    is_stalled: bool = False
    stall_threshold: int = 45


@dataclass
class TestResults:
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    failures: list[str] = None
    errors_list: list[str] = None
    summary: str = ""
    loading_failed: bool = False
    loading_error: str = ""
    elapsed: float = 0
    returncode: int = 0
    browser_errors: list[str] = None
    failed_tour_steps: list[str] = None
    error_details: dict[str, str] = None
    output_files: dict[str, str] = None
    critical_error: dict[str, str] = None

    def __post_init__(self) -> None:
        if self.failures is None:
            self.failures = []
        if self.errors_list is None:
            self.errors_list = []
        if self.browser_errors is None:
            self.browser_errors = []
        if self.failed_tour_steps is None:
            self.failed_tour_steps = []
        if self.error_details is None:
            self.error_details = {}
        if self.output_files is None:
            self.output_files = {}


class CallerDetector:
    @staticmethod
    def detect_caller() -> str:
        import psutil

        current = psutil.Process()
        for proc in current.parents():
            try:
                cmdline = " ".join(proc.cmdline()).lower()
                if any(indicator in cmdline for indicator in ["chatgpt", "gpt", "openai"]):
                    return "gpt"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Check for agent indicators in command line or environment
        cmdline = " ".join(sys.argv).lower()
        if any(indicator in cmdline for indicator in ["agent", "claude", "task"]):
            return "agent"

        # Check if output is being piped (likely agent/script)
        if not sys.stdout.isatty():
            return "agent"

        # Default to human
        return "human"


class OutputManager:
    def __init__(self, output_dir: Path, caller_type: str = "human") -> None:
        self.output_dir = output_dir
        self.caller_type = caller_type
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Output files
        self.streaming_log = output_dir / "streaming.log"
        self.full_log = output_dir / "full.log"
        self.summary_file = output_dir / "summary.json"
        self.progress_file = output_dir / "progress.json"
        self.heartbeat_file = output_dir / "heartbeat.json"

        # File handles
        self.streaming_handle = open(self.streaming_log, "w", buffering=1)
        self.full_handle = open(self.full_log, "w", buffering=1)

        # Progress tracking
        self.progress = TestProgress()
        self.last_heartbeat = time.time()

        # Output patterns for parsing
        self.test_patterns = {
            "test_start": re.compile(r"Running test (.+)"),
            "test_complete": re.compile(r"(PASS|FAIL|ERROR): (.+)"),
            "phase_change": re.compile(r"(Loading|Installing|Testing|Finalizing)"),
            "tour_start": re.compile(r"Starting tour: (.+)"),
            "browser_error": re.compile(r"(Console error:|Browser error:|JavaScript error:|UncaughtPromiseError|OwlError)"),
        }

        # Critical error patterns that should stop execution
        self.critical_error_patterns = {
            "db_constraint": re.compile(r"(violates check constraint|IntegrityError|bad query:|psycopg2\..*Error)"),
            "module_error": re.compile(
                r"(Failed to load registry|Failed to initialize database|TypeError: Model|AttributeError:.*models)"
            ),
            "critical_exception": re.compile(r"(CRITICAL|FATAL|OperationalError:)"),
            "port_conflict": re.compile(r"(Address already in use|Port.*is in use|bind.*failed|Cannot bind)"),
            "access_error": re.compile(r"(odoo\.exceptions\.AccessError|AccessError:|You are not allowed to)"),
            "validation_error": re.compile(r"(odoo\.exceptions\.ValidationError|ValidationError:|UserError:)"),
            "missing_dependency": re.compile(r"(ModuleNotFoundError:|ImportError:.*No module named|unmet dependencies)"),
            "test_discovery": re.compile(r"(No tests? found|0 tests? collected|ImportError.*test_)"),
        }

        # Track critical errors
        self.critical_error_detected = False
        self.critical_error_details = None

    def write_line(self, line: str):
        timestamp = datetime.now().isoformat()
        timestamped_line = f"[{timestamp}] {line}"

        # Write to all log files
        self.full_handle.write(timestamped_line + "\n")
        self.full_handle.flush()

        # Stream to human if applicable
        if self.caller_type == "human":
            self.streaming_handle.write(timestamped_line + "\n")
            self.streaming_handle.flush()
            print(line.rstrip())
            sys.stdout.flush()
        else:
            # For agents/GPT, write to streaming log but don't print
            self.streaming_handle.write(timestamped_line + "\n")
            self.streaming_handle.flush()

        # Update progress tracking
        self._update_progress(line)
        self._update_heartbeat()

        # Check for critical errors
        self._check_critical_errors(line)

    def _update_progress(self, line: str) -> None:
        current_time = time.time()

        # Detect phase changes
        for pattern_name, pattern in self.test_patterns.items():
            match = pattern.search(line)
            if match:
                if pattern_name == "test_start":
                    self.progress.current_test = match.group(1)
                    self.progress.phase = "testing"
                elif pattern_name == "test_complete":
                    self.progress.tests_completed += 1
                elif pattern_name == "phase_change":
                    self.progress.phase = match.group(1).lower()
                elif pattern_name == "tour_start":
                    self.progress.current_test = f"Tour: {match.group(1)}"
                    self.progress.phase = "tour"
                break

        self.progress.last_update = current_time

        # Check for stalls based on phase
        stall_thresholds = {
            "tour": 120,  # Tours can be slow
            "starting": 60,  # Startup can take time
            "loading": 60,  # Module loading
            "testing": 45,  # Regular tests
        }

        threshold = stall_thresholds.get(self.progress.phase, 45)
        self.progress.stall_threshold = threshold
        self.progress.is_stalled = (current_time - self.progress.last_update) > threshold

        # Write progress update
        self._write_progress()

    def _update_heartbeat(self) -> None:
        current_time = time.time()
        heartbeat_data = {
            "timestamp": current_time,
            "last_update": self.progress.last_update,
            "time_since_update": current_time - self.progress.last_update,
            "is_stalled": self.progress.is_stalled,
            "phase": self.progress.phase,
            "stall_threshold": self.progress.stall_threshold,
        }

        with open(self.heartbeat_file, "w") as f:
            json.dump(heartbeat_data, f, indent=2)

    def _write_progress(self) -> None:
        with open(self.progress_file, "w") as f:
            json.dump(asdict(self.progress), f, indent=2)

    def _check_critical_errors(self, line: str) -> None:
        for error_type, pattern in self.critical_error_patterns.items():
            if pattern.search(line):
                self.critical_error_detected = True
                self.critical_error_details = {
                    "type": error_type,
                    "line": line,
                    "timestamp": datetime.now().isoformat(),
                    "current_test": self.progress.current_test,
                    "phase": self.progress.phase,
                }

                # Write critical error to separate file
                critical_error_file = self.output_dir / "critical_error.txt"
                with open(critical_error_file, "w") as f:
                    f.write("🚨 CRITICAL ERROR DETECTED 🚨\n")
                    f.write("=" * 80 + "\n")
                    f.write(f"Type: {error_type}\n")
                    f.write(f"Phase: {self.progress.phase}\n")
                    f.write(f"Current Test: {self.progress.current_test}\n")
                    f.write(f"Timestamp: {self.critical_error_details['timestamp']}\n")
                    f.write(f"Error Line: {line}\n")
                    f.write("=" * 80 + "\n")

                # Print prominent error notification (write directly to avoid recursion)
                error_banner = "\n" + "🚨" * 20 + "\n"
                error_msg = f"{error_banner}CRITICAL ERROR DETECTED - TEST EXECUTION WILL STOP\nError Type: {error_type}\nError: {line}{error_banner}"

                # Write directly to files and console
                timestamp = datetime.now().isoformat()
                for handle in [self.streaming_handle, self.full_handle]:
                    handle.write(f"[{timestamp}] {error_msg}\n")
                    handle.flush()

                if self.caller_type == "human":
                    print(error_msg)
                    sys.stdout.flush()
                break

    def close(self) -> None:
        if hasattr(self, "streaming_handle"):
            self.streaming_handle.close()
        if hasattr(self, "full_handle"):
            self.full_handle.close()


class UnifiedTestRunner:
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
        self.test_tags: str | None = None  # Track specific test requested

        # Detect caller type
        self.caller_type = CallerDetector.detect_caller()

        # Create output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = Path("tmp/tests") / f"odoo-tests-{timestamp}"

        # Initialize output manager
        self.output_manager = None

        # Validate environment
        self._validate_environment()

    def _validate_environment(self) -> None:
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Error: Docker not found or not accessible: {e}")
            sys.exit(1)

        self._ensure_containers_running()

    def _ensure_containers_running(self) -> None:
        containers_to_check = [
            {"name": "odoo-opw-script-runner-1", "service": "script-runner"},
            {"name": "odoo-opw-shell-1", "service": "shell"},
        ]

        for container in containers_to_check:
            check_cmd = ["docker", "ps", "--filter", f"name={container['name']}", "--format", "{{.Names}}"]
            result = subprocess.run(check_cmd, capture_output=True, text=True)

            if container["name"] not in result.stdout:
                if self.verbose:
                    print(f"Container {container['name']} not running, starting it...")

                start_cmd = [
                    "docker",
                    "compose",
                    "run",
                    "-d",
                    "--name",
                    container["name"],
                    container["service"],
                    "tail",
                    "-f",
                    "/dev/null",
                ]

                try:
                    subprocess.run(start_cmd, capture_output=True, check=True, text=True)
                    if self.verbose:
                        print(f"Started container {container['name']}")
                    time.sleep(1)
                except subprocess.CalledProcessError as e:
                    if "already in use" in str(e.stderr):
                        restart_cmd = ["docker", "start", container["name"]]
                        try:
                            subprocess.run(restart_cmd, capture_output=True, check=True)
                            if self.verbose:
                                print(f"Restarted existing container {container['name']}")
                        except subprocess.CalledProcessError:
                            print(f"Error: Could not start container {container['name']}")
                            sys.exit(1)
                    else:
                        print(f"Error starting container {container['name']}: {e.stderr}")
                        sys.exit(1)

    @staticmethod
    def get_available_port(start: int = 20100, end: int = 21000) -> int:
        reserved_ports = {8069, 8070, 8071, 8072}

        # Use random starting point to avoid conflicts
        port_range = list(range(start, end))
        random.shuffle(port_range)

        for port in port_range:
            if port in reserved_ports:
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("", port))
                    return port
            except OSError:
                continue
        raise RuntimeError(f"No available ports found in range {start}-{end}")

    def _run_preflight_checks(self) -> dict[str, bool]:
        """Run pre-execution checks to validate environment."""
        checks = {}

        # Check if database is accessible
        try:
            check_db = [
                "docker",
                "exec",
                self.container_name,
                "python3",
                "-c",
                f"import psycopg2; conn = psycopg2.connect('dbname={self.database} host=database user=odoo'); conn.close(); print('OK')",
            ]
            result = subprocess.run(check_db, capture_output=True, text=True, timeout=5)
            checks["database_accessible"] = result.returncode == 0 and "OK" in result.stdout
        except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError):
            checks["database_accessible"] = False

        # Check if addons paths exist
        try:
            check_paths = [
                "docker",
                "exec",
                self.container_name,
                "python3",
                "-c",
                f"import os; paths = '{self.addons_path}'.split(','); missing = [p for p in paths if not os.path.exists(p)]; print('Missing:' + str(missing) if missing else 'OK')",
            ]
            result = subprocess.run(check_paths, capture_output=True, text=True, timeout=5)
            checks["addons_paths_exist"] = result.returncode == 0 and "OK" in result.stdout
        except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError):
            checks["addons_paths_exist"] = False

        # Check if product_connect module exists
        try:
            check_module = [
                "docker",
                "exec",
                self.container_name,
                "python3",
                "-c",
                "import os; print('OK' if os.path.exists('/volumes/addons/product_connect') else 'Missing')",
            ]
            result = subprocess.run(check_module, capture_output=True, text=True, timeout=5)
            checks["product_connect_exists"] = result.returncode == 0 and "OK" in result.stdout
        except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError):
            checks["product_connect_exists"] = False

        return checks

    def run_tests_with_streaming(self, test_type: str = "all", specific_test: str | None = None, timeout: int = 180) -> TestResults:
        # Initialize output manager
        self.output_manager = OutputManager(self.output_dir, self.caller_type)

        # Run preflight checks
        if self.verbose or self.debug:
            self.output_manager.write_line("Running preflight checks...")
            checks = self._run_preflight_checks()
            for check, passed in checks.items():
                status = "✓" if passed else "✗"
                self.output_manager.write_line(f"  {status} {check}")

            if not all(checks.values()):
                self.output_manager.write_line("⚠️  Warning: Some preflight checks failed")

        # Store specific test for diagnostics
        self.test_tags = specific_test

        # Build command
        port = UnifiedTestRunner.get_available_port()
        cmd = [
            "/odoo/odoo-bin",
            "-d",
            self.database,
            "--addons-path",
            self.addons_path,
            "--http-port",
            str(port),
            "--test-enable",
            "--stop-after-init",
            "--max-cron-threads=0",
            "--workers=0",
            f"--db-filter=^{self.database}$",
            "--log-level=info",
        ]

        # Add test tags based on type
        if specific_test:
            if specific_test.startswith("/"):
                cmd.extend(["--test-tags", specific_test])
            elif ":" in specific_test and "/" in specific_test:
                cmd.extend(["--test-tags", specific_test])
            elif "." in specific_test:
                cmd.extend(["--test-tags", f"/product_connect:{specific_test}"])
            elif specific_test.startswith("Test"):
                cmd.extend(["--test-tags", f"/product_connect:{specific_test}"])
            else:
                cmd.extend(["--test-tags", specific_test])
        elif test_type in ["python", "tour", "all"]:
            # Only run product_connect tests by default to avoid permission issues
            # with other modules' test setup
            cmd.extend(["--test-tags", "product_connect"])
        else:
            cmd.extend(["--test-tags", test_type])

        docker_cmd = ["docker", "exec", "-e", "PYTHONUNBUFFERED=1", self.container_name] + cmd

        if self.debug:
            self.output_manager.write_line(f"Debug: Running command: {' '.join(docker_cmd)}")

        # Print initial info
        test_desc = specific_test or test_type
        self.output_manager.write_line(f"Running {test_desc} tests...")
        self.output_manager.write_line(f"Output directory: {self.output_dir}")
        self.output_manager.write_line(f"Caller type: {self.caller_type}")
        self.output_manager.write_line("-" * 80)

        start_time = time.time()
        output_lines = []

        try:
            # Start process with real-time output
            process = subprocess.Popen(
                docker_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True,
            )
            last_output_time = time.time()

            while True:
                # Check if process is still running
                if process.poll() is not None:
                    break

                # Check for critical errors - stop immediately if detected
                if self.output_manager.critical_error_detected:
                    self.output_manager.write_line("Terminating test process due to critical error...")
                    process.terminate()
                    time.sleep(2)
                    if process.poll() is None:
                        process.kill()
                    break

                # Try to read line with timeout
                try:
                    line = process.stdout.readline()
                    if line:
                        line = line.rstrip()
                        output_lines.append(line)
                        self.output_manager.write_line(line)
                        last_output_time = time.time()
                    else:
                        # No output available, check for timeout
                        current_time = time.time()
                        if current_time - start_time > timeout:
                            self.output_manager.write_line(f"TIMEOUT: Test execution exceeded {timeout} seconds")
                            process.terminate()
                            time.sleep(2)
                            if process.poll() is None:
                                process.kill()
                            break

                        # Check for stall
                        if current_time - last_output_time > self.output_manager.progress.stall_threshold:
                            self.output_manager.write_line(
                                f"WARNING: No output for {current_time - last_output_time:.1f}s (stall threshold: {self.output_manager.progress.stall_threshold}s)"
                            )

                        time.sleep(0.1)  # Brief pause to avoid busy waiting

                except Exception as e:
                    self.output_manager.write_line(f"Error reading process output: {e}")
                    break

            # Get final return code
            return_code = process.wait()
            elapsed = time.time() - start_time

            # Override return code if critical error detected
            if self.output_manager.critical_error_detected:
                error_type = self.output_manager.critical_error_details.get("type", "unknown")
                if error_type == "db_constraint":
                    return_code = -10
                elif error_type == "module_error":
                    return_code = -11
                else:
                    return_code = -12

            # Get any remaining output
            try:
                remaining_output, _ = process.communicate(timeout=5)
                if remaining_output:
                    for line in remaining_output.split("\n"):
                        if line.strip():
                            output_lines.append(line.strip())
                            # Don't check for critical errors in remaining output
                            if not self.output_manager.critical_error_detected:
                                self.output_manager.write_line(line.strip())
            except subprocess.TimeoutExpired:
                pass  # Ignore timeout on final output collection

        except subprocess.TimeoutExpired:
            self.output_manager.write_line(f"Process timed out after {timeout} seconds")
            return_code = -1
            elapsed = timeout
        except Exception as e:
            self.output_manager.write_line(f"Unexpected error during test execution: {e}")
            return_code = -2
            elapsed = time.time() - start_time

        self.output_manager.write_line("-" * 80)
        self.output_manager.write_line(f"Tests completed in {elapsed:.1f} seconds with return code: {return_code}")

        # Parse results
        full_output = "\n".join(output_lines)
        results = self._parse_test_results(full_output)
        results.elapsed = elapsed
        results.returncode = return_code

        # Add critical error info if detected
        if self.output_manager.critical_error_detected:
            results.critical_error = self.output_manager.critical_error_details
            results.summary = f"CRITICAL ERROR: {self.output_manager.critical_error_details.get('type', 'unknown')}"
        # Check for early exit with error
        elif return_code == 1 and elapsed < 5 and results.total == 0:
            # Likely a startup failure
            results.critical_error = {
                "type": "startup_failure",
                "phase": "starting",
                "error": "Process exited immediately - check logs for port conflicts or configuration issues",
            }
            results.summary = "CRITICAL ERROR: startup_failure"
        # Check for test discovery failure
        elif return_code == 0 and results.total == 0 and not self.output_manager.critical_error_detected:
            # Tests completed "successfully" but no tests found
            error_msg = self._analyze_test_discovery_failure(full_output)
            results.critical_error = {
                "type": "test_discovery_failure",
                "phase": "discovery",
                "error": error_msg,
            }
            results.summary = "CRITICAL ERROR: test_discovery_failure"

        # Add output file paths
        results.output_files = {
            "streaming_log": str(self.output_manager.streaming_log),
            "full_log": str(self.output_manager.full_log),
            "summary_json": str(self.output_manager.summary_file),
            "progress_json": str(self.output_manager.progress_file),
            "heartbeat_json": str(self.output_manager.heartbeat_file),
        }

        # Add critical error file if it exists
        critical_error_file = self.output_dir / "critical_error.txt"
        if critical_error_file.exists():
            results.output_files["critical_error"] = str(critical_error_file)

        # Write final summary
        self._write_summary(results)

        # Close output manager
        self.output_manager.close()

        return results

    @staticmethod
    def _parse_test_results(output: str) -> TestResults:
        results = TestResults()

        # Check for module loading failures
        if "Failed to load registry" in output or "Failed to initialize database" in output:
            results.loading_failed = True
            error_match = re.search(r"(TypeError: Model.*|AttributeError:.*|ImportError:.*|.*Error:.*)", output)
            if error_match:
                results.loading_error = error_match.group(1).strip()
            else:
                results.loading_error = "Module loading failed (check logs for details)"
            results.summary = f"Module loading failed: {results.loading_error}"
            return results

        # Extract overall summary
        summary_match = re.search(r"(\d+) failed, (\d+) error\(s\) of (\d+) tests", output)
        if summary_match:
            results.failed = int(summary_match.group(1))
            results.errors = int(summary_match.group(2))
            results.total = int(summary_match.group(3))
            results.passed = results.total - results.failed - results.errors
            results.summary = summary_match.group()
        else:
            # Try alternative format
            ran_match = re.search(r"Ran (\d+) tests? in", output)
            if ran_match:
                results.total = int(ran_match.group(1))
                if "FAILED" in output:
                    fail_match = re.search(r"FAILED \(.*?failures=(\d+)", output)
                    error_match = re.search(r"errors=(\d+)", output)
                    results.failed = int(fail_match.group(1)) if fail_match else 0
                    results.errors = int(error_match.group(1)) if error_match else 0
                else:
                    results.failed = 0
                    results.errors = 0
                results.passed = results.total - results.failed - results.errors
                results.summary = f"{results.failed} failed, {results.errors} error(s) of {results.total} tests"

        # Extract individual failures and errors
        failure_pattern = r"(FAIL|ERROR): (Test\w+\.test_\w+)"
        for match in re.finditer(failure_pattern, output):
            status, test_name = match.groups()
            if status == "FAIL":
                results.failures.append(test_name)
            else:
                results.errors_list.append(test_name)

        # Extract browser errors for tour tests
        if "tour" in output.lower() or "OwlError" in output or "UncaughtPromiseError" in output:
            console_error_pattern = (
                r"(Console error:|Browser error:|JavaScript error:|UncaughtPromiseError|OwlError)(.*?)(?=\n\d{4}-|$)"
            )
            for match in re.finditer(console_error_pattern, output, re.DOTALL):
                error_text = match.group(2).strip()
                if error_text:
                    results.browser_errors.append(f"{match.group(1)}: {error_text}")

            # Extract tour step failures
            tour_step_pattern = r"Tour step failed: (.*?)(?=\n|$)"
            for match in re.finditer(tour_step_pattern, output):
                results.failed_tour_steps.append(match.group(1).strip())

        # Extract detailed error information
        traceback_pattern = r"(FAIL|ERROR): (Test\w+\.test_\w+)(.*?)(?=(?:FAIL|ERROR):|$)"
        for match in re.finditer(traceback_pattern, output, re.DOTALL):
            status, test_name, details = match.groups()
            error_lines = []
            for line in details.split("\n"):
                if any(
                    keyword in line
                    for keyword in ["AssertionError:", "ERROR:", "DETAIL:", "TypeError:", "ReferenceError:", "Error:"]
                ):
                    error_lines.append(line.strip())
            if error_lines:
                results.error_details[test_name] = "\n".join(error_lines)

        return results

    def _analyze_test_discovery_failure(self, output: str) -> str:
        """Analyze why test discovery failed and provide actionable diagnostics."""
        reasons = []

        # Check for common test discovery issues
        if "ImportError" in output:
            import_match = re.search(r"ImportError: (.+)", output)
            if import_match:
                reasons.append(f"Import error: {import_match.group(1)}")

        if "ModuleNotFoundError" in output:
            module_match = re.search(r"ModuleNotFoundError: (.+)", output)
            if module_match:
                reasons.append(f"Missing module: {module_match.group(1)}")

        if "@tagged" not in output:
            reasons.append("No @tagged decorator found - tests must have @tagged('post_install', '-at_install')")

        if "test_" not in output.lower():
            reasons.append("No test methods found - ensure methods start with 'test_'")

        if "odoo.tests" not in output:
            reasons.append("No test imports found - ensure tests import from odoo.tests")

        # Check for test file naming
        test_pattern = getattr(self, "test_tags", "")
        if test_pattern:
            if "." in test_pattern:
                class_name, method_name = test_pattern.split(".", 1)
                reasons.append(f"Specific test method requested: {test_pattern}")
                reasons.append(f"Verify class '{class_name}' exists and has method '{method_name}'")
            elif test_pattern.startswith("Test"):
                reasons.append(f"Specific test class requested: {test_pattern}")
                reasons.append(f"Verify class '{test_pattern}' exists in tests/ directory")

        # Check for common test configuration issues
        if "product_connect" in output and "tests" in output:
            reasons.append("Module found but no tests discovered - check test file imports")
            reasons.append("Ensure tests/__init__.py imports all test files")

        # Default message if no specific reason found
        if not reasons:
            reasons.append("Test discovery failed - check test file naming (test_*.py) and class inheritance")
            reasons.append("Verify tests are in the tests/ directory and properly imported in __init__.py")

        return "; ".join(reasons)

    def _write_summary(self, results: TestResults) -> None:
        summary_data = {
            "timestamp": datetime.now().isoformat(),
            "caller_type": self.caller_type,
            "results": asdict(results),
            "recommendations": self._generate_recommendations(results),
        }

        with open(self.output_manager.summary_file, "w") as f:
            json.dump(summary_data, f, indent=2)

        # For GPT integration, also write a simple text summary
        gpt_summary_file = self.output_dir / "gpt_summary.txt"
        with open(gpt_summary_file, "w") as f:
            f.write(f"Test Results Summary\n")
            f.write(f"===================\n\n")
            f.write(f"Total: {results.total}\n")
            f.write(f"Passed: {results.passed}\n")
            f.write(f"Failed: {results.failed}\n")
            f.write(f"Errors: {results.errors}\n")
            f.write(f"Elapsed: {results.elapsed:.1f}s\n\n")

            if results.loading_failed:
                f.write(f"CRITICAL: Module loading failed\n")
                f.write(f"Error: {results.loading_error}\n\n")

            if results.failures:
                f.write(f"Failed Tests:\n")
                for test in results.failures:
                    f.write(f"  - {test}\n")
                f.write("\n")

            if results.errors_list:
                f.write(f"Error Tests:\n")
                for test in results.errors_list:
                    f.write(f"  - {test}\n")
                f.write("\n")

            if results.browser_errors:
                f.write(f"Browser Errors:\n")
                for error in results.browser_errors:
                    f.write(f"  - {error}\n")
                f.write("\n")

            f.write(f"Output Files:\n")
            for name, path in results.output_files.items():
                f.write(f"  {name}: {path}\n")

        results.output_files["gpt_summary"] = str(gpt_summary_file)

    @staticmethod
    def _generate_recommendations(results: TestResults) -> list[str]:
        recommendations = []

        if results.loading_failed:
            recommendations.append("Fix module loading errors before running tests")
            recommendations.append("Check import statements and model definitions")

        if results.browser_errors:
            recommendations.append("Investigate JavaScript console errors in browser tests")
            recommendations.append("Check Owl component implementations and templates")

        if results.failed > 0:
            recommendations.append("Review failed test assertions and business logic")

        if results.errors > 0:
            recommendations.append("Fix test setup or infrastructure errors")

        if results.total == 0 and not results.loading_failed:
            recommendations.append("Check test discovery - ensure tests are properly tagged")
            recommendations.append("Verify test files exist and inherit from proper base classes")
            recommendations.append("Ensure test methods start with 'test_' and classes have @tagged decorator")
            recommendations.append("Check that test files are imported in tests/__init__.py")

        return recommendations


def get_recommended_timeout(test_type: str, specific_test: str | None = None) -> int:
    if specific_test and "." in specific_test:
        return 60  # Individual test method
    elif specific_test:
        return 300  # Specific test class
    elif test_type == "all":
        return 1800  # Full suite
    elif test_type == "tour":
        return 420  # Browser tests
    elif test_type == "python":
        return 480  # Python tests
    else:
        return 300  # Default


def main() -> None:
    parser = argparse.ArgumentParser(description="Unified Odoo Test Runner")
    parser.add_argument(
        "test_type",
        nargs="?",
        default="summary",
        choices=["all", "python", "tour", "summary", "failing"],
        help="Type of tests to run",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show detailed output")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("-t", "--timeout", type=int, default=None, help="Timeout in seconds")
    parser.add_argument("--test-tags", type=str, help="Run specific test tags")
    parser.add_argument("-j", "--json", action="store_true", help="Output results as JSON")
    parser.add_argument("-c", "--container", type=str, default="odoo-opw-script-runner-1", help="Docker container name")
    parser.add_argument("-d", "--database", type=str, default="opw", help="Database name")
    parser.add_argument(
        "-p", "--addons-path", type=str, default="/volumes/addons,/odoo/addons,/volumes/enterprise", help="Addons path"
    )

    args = parser.parse_args()

    runner = UnifiedTestRunner(
        verbose=args.verbose,
        debug=args.debug,
        container=args.container,
        database=args.database,
        addons_path=args.addons_path,
    )

    # Determine timeout
    timeout = args.timeout
    if timeout is None:
        timeout = get_recommended_timeout(args.test_type, args.test_tags)
        if args.verbose or args.debug:
            print(f"Using recommended timeout: {timeout} seconds ({timeout // 60} minutes)")

    # Run tests
    if args.test_type == "failing":
        # Quick implementation for failing tests
        results = runner.run_tests_with_streaming(timeout=timeout)
        failing = results.failures + results.errors_list
        results_dict = {"failing_tests": failing, "count": len(failing)}
    else:
        test_type = "all" if args.test_type == "summary" else args.test_type
        results = runner.run_tests_with_streaming(test_type, args.test_tags, timeout)
        results_dict = asdict(results)

    # Output results
    if args.json:
        print(json.dumps(results_dict, indent=2))
    else:
        # Human readable output
        if isinstance(results, TestResults):
            if results.critical_error:
                print("\n" + "🚨" * 30)
                print("CRITICAL ERROR DETECTED - TEST EXECUTION STOPPED")
                print("🚨" * 30)
                print(f"\nError Type: {results.critical_error.get('type', 'unknown')}")
                print(f"Phase: {results.critical_error.get('phase', 'unknown')}")
                if results.critical_error.get("current_test"):
                    print(f"Current Test: {results.critical_error.get('current_test')}")
                error_msg = results.critical_error.get("error", results.critical_error.get("line", "unknown"))
                print(f"\nError Details:\n{error_msg}")
                print(f"\nReturn Code: {results.returncode}")
                print("\nAction Required: Fix the critical error before running tests again")
            elif results.loading_failed:
                print(f"\n❌ Module Loading Failed!")
                print(f"Error: {results.loading_error}")
            else:
                print(f"\n=== Test Results ===")
                print(f"Total:  {results.total}")
                print(f"Passed: {results.passed} ✅")
                print(f"Failed: {results.failed} ❌")
                print(f"Errors: {results.errors} 💥")

                if results.failures:
                    print(f"\n=== Failed Tests ===")
                    for test in results.failures[:10]:
                        print(f"  FAIL: {test}")

                if results.errors_list:
                    print(f"\n=== Error Tests ===")
                    for test in results.errors_list[:10]:
                        print(f"  ERROR: {test}")

                if results.browser_errors:
                    print(f"\n=== Browser Console Errors ===")
                    for error in results.browser_errors[:5]:
                        print(f"  ❌ {error}")

            print(f"\n=== Output Files ===")
            for name, path in results.output_files.items():
                print(f"  {name}: {path}")

        else:  # failing tests case
            print(f"\n=== Currently Failing Tests ({results_dict['count']}) ===")
            for test in results_dict["failing_tests"]:
                print(f"  - {test}")

    # Exit with appropriate code
    if isinstance(results, TestResults):
        if results.critical_error:
            # Use specific exit codes for critical errors
            sys.exit(abs(results.returncode) if results.returncode < 0 else 10)
        elif results.failed > 0 or results.errors > 0:
            sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
