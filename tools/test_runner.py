import re
import sys
import time
import subprocess
import argparse
import json
import socket
import random
import shutil
import select
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class TestProgress:
    phase: str = "starting"
    current_test: str = ""
    tests_started: int = 0  # Track tests that actually started
    tests_completed: int = 0
    tests_total: int = 0
    last_update: float = 0
    is_stalled: bool = False
    stall_threshold: int = 60
    output_lines_since_test: int = 0  # Track activity


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
                if any(indicator in cmdline for indicator in ["codex", "gpt-codex", "openai"]):
                    return "gpt"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        cmdline = " ".join(sys.argv).lower()
        if any(indicator in cmdline for indicator in ["agent", "claude", "task"]):
            return "agent"

        if not sys.stdout.isatty():
            return "agent"

        return "human"


class OutputManager:
    def __init__(self, output_dir: Path, caller_type: str = "human") -> None:
        self.output_dir = output_dir
        self.caller_type = caller_type
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.streaming_log = output_dir / "streaming.log"
        self.full_log = output_dir / "full.log"
        self.summary_file = output_dir / "summary.json"
        self.progress_file = output_dir / "progress.json"
        self.heartbeat_file = output_dir / "heartbeat.json"

        self.streaming_handle = open(self.streaming_log, "w", buffering=1)
        self.full_handle = open(self.full_log, "w", buffering=1)

        self.progress = TestProgress()
        self.last_heartbeat = time.time()

        self.test_patterns = {
            "test_start": re.compile(r"(Starting|Running test|Testing) (.+)"),
            "test_class_start": re.compile(r"Starting (Test\w+)"),
            "test_method_start": re.compile(r"Starting .*\.(test_\w+)"),
            "test_complete": re.compile(r"(PASS|FAIL|ERROR|OK|FAILED): (.+)"),
            "test_ok": re.compile(r"test_\w+.*\.\.\. ok"),
            "test_failed": re.compile(r"test_\w+.*\.\.\. FAIL"),
            "test_error": re.compile(r"test_\w+.*\.\.\. ERROR"),
            "phase_change": re.compile(r"(Loading|Installing|Testing|Finalizing|Initializing)"),
            "module_loading": re.compile(r"odoo: modules loaded"),
            "registry_ready": re.compile(r"registry loaded in"),
            "tour_start": re.compile(r"Starting tour: (.+)"),
            "browser_error": re.compile(r"(Console error:|Browser error:|JavaScript error:|UncaughtPromiseError|OwlError)"),
            "js_test_start": re.compile(r"Starting (ProductConnectJSTests|.*HttpCase|.*test_hoot)"),
            "hoot_test": re.compile(r"\[HOOT]"),
        }

        self.tests_seen = set()

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

        self.critical_error_detected = False
        self.critical_error_details = None

    def write_line(self, line: str):
        timestamp = datetime.now().isoformat()
        timestamped_line = f"[{timestamp}] {line}"

        self.full_handle.write(timestamped_line + "\n")
        self.full_handle.flush()

        if self.caller_type == "human":
            self.streaming_handle.write(timestamped_line + "\n")
            self.streaming_handle.flush()
            print(line.rstrip())
            sys.stdout.flush()
        else:
            self.streaming_handle.write(timestamped_line + "\n")
            self.streaming_handle.flush()

        self._update_progress(line)
        self._update_heartbeat()

        self._check_critical_errors(line)

    def _update_progress(self, line: str) -> None:
        current_time = time.time()

        self.progress.output_lines_since_test += 1

        if "Starting" in line and ("test_" in line or "Test" in line):
            test_match = re.search(r"Starting ([\w\.]+(?:test_\w+|Test\w+))", line)
            if test_match:
                test_name = test_match.group(1)
                if test_name not in self.tests_seen:
                    self.tests_seen.add(test_name)
                    self.progress.tests_started += 1
                    self.progress.current_test = test_name
                    self.progress.phase = "testing"
                    self.progress.output_lines_since_test = 0
                    if self.progress.tests_started % 10 == 0:
                        self.write_line(f"✅ Progress: {self.progress.tests_started} tests started")

        for pattern_name, pattern in self.test_patterns.items():
            match = pattern.search(line)
            if match:
                if pattern_name in ["test_complete", "test_ok", "test_failed", "test_error"]:
                    self.progress.tests_completed += 1
                elif pattern_name == "phase_change":
                    phase = match.group(1).lower()
                    if phase != self.progress.phase:
                        self.progress.phase = phase
                elif pattern_name == "tour_start":
                    self.progress.current_test = f"Tour: {match.group(1)}"
                    self.progress.phase = "tour"
                    self.progress.tests_started += 1
                elif pattern_name == "js_test_start":
                    self.progress.phase = "javascript_tests"
                    self.progress.current_test = match.group(1)
                    self.progress.tests_started += 1
                    # Log JS test detection
                    self.write_line("")
                    self.write_line("=" * 80)
                    self.write_line("🌐 JavaScript/Hoot tests detected - these may take up to 30 minutes")
                    self.write_line("   Browser tests have extended timeouts, please be patient...")
                    self.write_line("=" * 80)
                    self.write_line("")
                elif pattern_name == "hoot_test":
                    self.progress.phase = "hoot_tests"
                elif pattern_name == "module_loading":
                    self.progress.phase = "modules_loaded"
                elif pattern_name == "registry_ready":
                    self.progress.phase = "ready_for_tests"
                break

        self.progress.last_update = current_time

        if self.progress.output_lines_since_test < 100:
            base_threshold = 180
        else:
            base_threshold = 120

        stall_thresholds = {
            "tour": 300,  # Tours can be very slow
            "starting": 120,  # Startup can take time
            "loading": 120,  # Module loading
            "modules_loaded": 60,  # Should start tests soon
            "ready_for_tests": 60,  # Should start tests soon
            "testing": base_threshold,  # Regular tests - dynamic
            "javascript_tests": 600,  # JS tests can be extremely slow
            "hoot_tests": 600,  # Hoot tests need lots of time
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
        # Skip errors in tests that are testing validation or error conditions
        if self.progress.current_test:
            test_name = self.progress.current_test.lower()
            # Check if this is a test that's expected to cause errors
            if any(keyword in test_name for keyword in ["validation", "error", "constraint", "integrity", "invalid", "fail"]):
                # Skip database constraint errors in these tests
                if any(phrase in line.lower() for phrase in ["bad query", "null value", "constraint", "violates", "integrityerror", "error opw odoo.sql_db"]):
                    return
            # Also skip for integration tests that might be testing error conditions
            if "integration" in test_name:
                if any(phrase in line.lower() for phrase in ["bad query", "null value", "constraint", "violates"]):
                    return

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

                error_banner = "\n" + "🚨" * 20 + "\n"
                error_msg = f"{error_banner}CRITICAL ERROR DETECTED - TEST EXECUTION WILL STOP\nError Type: {error_type}\nError: {line}{error_banner}"

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
        container: str = None,
        database: str = "opw",
        addons_path: str = "/volumes/addons,/odoo/addons,/volumes/enterprise",
        test_mode: str = "mixed",  # mixed, unit, validation, tour, all
    ) -> None:
        import os
        self.verbose = verbose
        self.debug = debug
        
        # Set container name using environment variable
        if container is None:
            container_prefix = os.environ.get("ODOO_CONTAINER_PREFIX", "odoo-opw")
            container = f"{container_prefix}-script-runner-1"
        self.container_name = container
        self.database = database
        self.addons_path = addons_path
        self.test_tags: str | None = None  # Track specific test requested
        self.modules: list[str] = []  # Modules to test
        self.test_mode = test_mode  # Test execution mode

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
        if self.verbose:
            print("DEBUG: Validating environment...")
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Error: Docker not found or not accessible: {e}")
            sys.exit(1)

        self._ensure_containers_running()

    def _ensure_containers_running(self) -> None:
        import os
        container_prefix = os.environ.get("ODOO_CONTAINER_PREFIX", "odoo-opw")
        
        if self.verbose:
            print("DEBUG: Checking containers...")
        
        # Clean up any zombie browser processes first
        self._cleanup_zombie_processes(f"{container_prefix}-script-runner-1")
        
        containers_to_check = [
            {"name": f"{container_prefix}-script-runner-1", "service": "script-runner"},
            {"name": f"{container_prefix}-shell-1", "service": "shell"},
        ]

        for container in containers_to_check:
            check_cmd = ["docker", "ps", "--filter", f"name={container['name']}", "--format", "{{.Names}}"]
            result = subprocess.run(check_cmd, capture_output=True, text=True)

            if container["name"] not in result.stdout:
                if self.verbose:
                    print(f"Container {container['name']} not running, starting it...")

                # First try to restart existing container
                restart_cmd = ["docker", "start", container["name"]]
                restart_result = subprocess.run(restart_cmd, capture_output=True, text=True)
                
                if restart_result.returncode == 0:
                    if self.verbose:
                        print(f"Restarted existing container {container['name']}")
                    continue
                
                # Container doesn't exist, create new one
                start_cmd = [
                    "docker",
                    "compose",
                    "run",
                    "-d",
                    "--rm",  # Auto-remove when stopped to prevent duplicates
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
                    print(f"Error starting container {container['name']}: {e.stderr}")
                    # Try to clean up and restart
                    subprocess.run(["docker", "rm", "-f", container["name"]], capture_output=True)
                    time.sleep(1)
                    try:
                        subprocess.run(start_cmd, capture_output=True, check=True)
                        if self.verbose:
                            print(f"Container {container['name']} restarted after cleanup")
                    except subprocess.CalledProcessError:
                        print(f"Failed to start container {container['name']} after cleanup")
                        sys.exit(1)

    def _cleanup_zombie_processes(self, container_name: str) -> None:
        """Clean up zombie processes in the container to prevent database locks."""
        try:
            if self.verbose:
                print(f"DEBUG: Cleaning up zombie processes in {container_name}...")
            
            # Kill all Odoo test processes first (they hold database locks)
            odoo_cleanup_commands = [
                ["docker", "exec", container_name, "pkill", "-f", "odoo-bin.*test-enable"],
                ["docker", "exec", container_name, "pkill", "-f", "python3.*odoo-bin"],
                ["docker", "exec", container_name, "pkill", "-f", "timeout.*odoo-bin"],
            ]
            
            for cmd in odoo_cleanup_commands:
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    if self.verbose and result.returncode == 0:
                        print(f"DEBUG: Killed processes with: {' '.join(cmd[-2:])}")
                except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                    continue  # Ignore cleanup failures
            
            # Wait for processes to terminate gracefully
            import time
            time.sleep(2)
            
            # Kill zombie chromium/browser processes
            browser_cleanup_commands = [
                ["docker", "exec", container_name, "pkill", "-f", "chromium"],
                ["docker", "exec", container_name, "pkill", "-f", "chrome"],
                ["docker", "exec", container_name, "pkill", "-f", "chrome_crashpad"],
                ["docker", "exec", container_name, "pkill", "-9", "-f", "chromium"],  # Force kill if needed
            ]
            
            for cmd in browser_cleanup_commands:
                try:
                    subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                    continue  # Ignore cleanup failures
            
            # Enhanced cleanup: clear shared memory and orphaned resources  
            enhanced_cleanup_commands = [
                # Clear shared memory segments
                ["docker", "exec", container_name, "sh", "-c", "ipcs -m | awk '/^0x/ {print $2}' | xargs -r ipcrm -m || true"],
                # Clear semaphores
                ["docker", "exec", container_name, "sh", "-c", "ipcs -s | awk '/^0x/ {print $2}' | xargs -r ipcrm -s || true"],
                # Remove socket files
                ["docker", "exec", container_name, "find", "/tmp", "-name", "*.sock", "-type", "s", "-delete"],
                # Clean up temp files
                ["docker", "exec", container_name, "sh", "-c", "find /tmp -name 'odoo-*' -type f -delete || true"],
                ["docker", "exec", container_name, "sh", "-c", "find /tmp -name 'chrome*' -type d -exec rm -rf {} + || true"],
                # Add chromedriver to browser cleanup
                ["docker", "exec", container_name, "pkill", "-f", "chromedriver"],
                ["docker", "exec", container_name, "pkill", "-9", "-f", "chromedriver"],
            ]
            
            for cmd in enhanced_cleanup_commands:
                try:
                    subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                    continue  # Ignore cleanup failures
                    
            if self.verbose:
                print("DEBUG: Enhanced process cleanup completed")
                
        except Exception as e:
            if self.verbose:
                print(f"DEBUG: Process cleanup warning: {e}")

    def discover_local_modules(self) -> list[str]:
        """Discover all modules in the local addons directory."""
        modules = []
        addons_dir = Path("addons")

        if not addons_dir.exists():
            return modules

        for item in addons_dir.iterdir():
            # Skip non-directories and special directories
            if not item.is_dir() or item.name.startswith("__") or item.name.startswith("."):
                continue

            # Check if it's a valid Odoo module (has __manifest__.py or __openerp__.py)
            if (item / "__manifest__.py").exists() or (item / "__openerp__.py").exists():
                modules.append(item.name)

        # Sort for consistent ordering
        modules.sort()

        if self.verbose:
            print(f"Discovered local modules: {', '.join(modules)}")

        return modules

    def _resolve_bare_test_method(self, method_name: str, modules: list[str]) -> dict[str, str] | None:
        """Given a bare method like 'test_foo', find its class and module.

        Returns dict with keys: module, class, tag (formatted as /module:Class.method)
        or None if not found.
        """
        addons_root = Path("addons")
        for module in modules:
            module_dir = addons_root / module / "tests"
            if not module_dir.exists():
                continue
            # Search recursively for test files
            for py in module_dir.rglob("test_*.py"):
                try:
                    content = py.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                # Find the method in the file
                for m in re.finditer(rf"^\s*def\s+{re.escape(method_name)}\s*\(", content, re.MULTILINE):
                    # Walk backwards to find the enclosing class definition
                    upto = content[: m.start()]
                    class_matches = list(re.finditer(r"^\s*class\s+(Test\w+)\s*\(", upto, re.MULTILINE))
                    if not class_matches:
                        continue
                    cls_name = class_matches[-1].group(1)
                    return {
                        "module": module,
                        "class": cls_name,
                        "tag": f"/{module}:{cls_name}.{method_name}",
                    }
        return None

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
        if self.verbose:
            print("DEBUG: Running preflight checks...")
        checks = {}

        # Check if database is accessible
        try:
            if self.verbose:
                print("DEBUG: Checking database connection...")
            # Test database connection using Odoo's configuration
            # Use echo to pipe Python code to Odoo shell via stdin
            check_db = f"echo \"env['res.users'].search_count([]); print('OK')\" | docker exec -i {self.container_name} /odoo/odoo-bin shell -d {self.database} --no-http --stop-after-init"
            result = subprocess.run(check_db, shell=True, capture_output=True, text=True, timeout=15)
            checks["database_accessible"] = result.returncode == 0 and "OK" in result.stdout
            if self.verbose:
                print(f"DEBUG: Database check result: {checks['database_accessible']}")
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

        # Check if modules exist
        if self.modules:
            for module in self.modules:
                try:
                    check_module = [
                        "docker",
                        "exec",
                        self.container_name,
                        "python3",
                        "-c",
                        f"import os; print('OK' if os.path.exists('/volumes/addons/{module}') else 'Missing')",
                    ]
                    result = subprocess.run(check_module, capture_output=True, text=True, timeout=5)
                    checks[f"{module}_exists"] = result.returncode == 0 and "OK" in result.stdout
                except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError):
                    checks[f"{module}_exists"] = False
        else:
            checks["modules_discovered"] = False

        return checks

    def run_tests_with_streaming(
        self, test_type: str = "all", specific_test: str | None = None, timeout: int = 180, modules: list[str] | None = None
    ) -> TestResults:
        """Run tests with streaming output.

        For test_mode='all', runs tests progressively:
        1. Unit tests (fast, clean DB)
        2. Integration tests (slow, production clone)
        3. Tour tests (browser UI)

        Stops at first category failure for fail-fast behavior.
        """
        # Initialize output manager only if not already created (e.g., by run_progressive_tests)
        self._should_close_output_manager = False
        if not self.output_manager:
            self.output_manager = OutputManager(self.output_dir, self.caller_type)
            self._should_close_output_manager = True  # We created it, so we should close it

        # Use provided modules or discover them
        explicit_modules = bool(modules)  # Track if user explicitly provided modules
        if modules:
            self.modules = modules
        elif not self.modules:
            # Auto-discover if no modules specified
            self.modules = self.discover_local_modules()

        if not self.modules:
            self.output_manager.write_line("⚠️  No modules found to test!")
            return TestResults()

        # Run preflight checks
        if self.verbose or self.debug:
            self.output_manager.write_line("Running preflight checks...")
            checks = self._run_preflight_checks()
            for check, passed in checks.items():
                status = "✓" if passed else "✗"
                self.output_manager.write_line(f"  {status} {check}")

            if not all(checks.values()):
                self.output_manager.write_line("⚠️  Warning: Some preflight checks failed")

                # Critical check - database must be accessible
                if not checks.get("database_accessible", False):
                    self.output_manager.write_line("❌ CRITICAL: Database is not accessible!")
                    self.output_manager.write_line("   This usually means:")
                    self.output_manager.write_line("   - Odoo containers are not running properly")
                    self.output_manager.write_line("   - Database connection issues")
                    self.output_manager.write_line("   - Wrong database name or credentials")
                    self.output_manager.write_line("")
                    self.output_manager.write_line("   Try: docker compose restart")
                    return TestResults(
                        critical_error={
                            "type": "database_not_accessible",
                            "phase": "preflight",
                            "error": "Database connection failed during preflight checks",
                        }
                    )

        # Store specific test for diagnostics
        self.test_tags = specific_test

        # Resolve bare test method names like "test_foo" to full test-tags
        # format "/<module>:<TestClass>.test_foo" to avoid discovery failures
        if specific_test and isinstance(specific_test, str):
            try:
                if re.match(r"^test_[A-Za-z0-9_]+$", specific_test):
                    search_modules = modules or (self.modules if self.modules else self.discover_local_modules())
                    resolved = self._resolve_bare_test_method(specific_test, search_modules)
                    if resolved:
                        specific_test = resolved["tag"]
                        # Keep modules context aligned for logs
                        self.modules = [resolved["module"]]
                        if self.verbose or self.debug:
                            self.output_manager.write_line(
                                f"DEBUG: Resolved bare method '{self.test_tags}' → '{specific_test}'"
                            )
            except Exception:
                # Non-fatal; fall back to original behavior
                pass

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
            "--log-level=test",  # Changed from info to test for better visibility
            "--without-demo=all",  # Prevent loading demo data that conflicts with production DB
        ]
        
        # For tour tests, add additional optimizations to prevent hanging
        if (test_type and "tour" in str(test_type).lower()) or (specific_test and any(k in specific_test for k in ["HttpCase", "JSTest", "test_js", "Tour"])):
            cmd.extend([
                "--limit-time-cpu=300",  # 5 minute CPU limit
                "--limit-time-real=600", # 10 minute real time limit
                "--limit-request=8192",  # Increase request limit
                "--limit-memory-hard=2684354560",  # 2.5GB memory limit
            ])

        # Apply module filtering to avoid running core Odoo tests that cause constraint violations
        # This ensures we only run tests from our custom addons
        if self.modules and not specific_test:
            module_tags = [f"/{mod}" for mod in self.modules]
            cmd.extend(["--test-tags", ",".join(module_tags)])
            if self.verbose or self.debug:
                self.output_manager.write_line(f"DEBUG: Running tests for modules: {', '.join(self.modules)}")

        # Add test filtering if specific test requested
        elif specific_test:
            # Detect module prefix if present
            if ":" in specific_test:
                parts = specific_test.split(":", 1)
                if "/" in parts[0]:
                    # Full format like /product_connect:TestClass
                    cmd.extend(["--test-tags", specific_test])
                else:
                    # Module:TestClass format
                    module_prefix = parts[0]
                    test_part = parts[1]
                    cmd.extend(["--test-tags", f"/{module_prefix}:{test_part}"])
            elif "." in specific_test:
                # TestClass.test_method format - need to find which module
                if len(self.modules) == 1:
                    cmd.extend(["--test-tags", f"/{self.modules[0]}:{specific_test}"])
                else:
                    # Multiple modules - try without module prefix
                    cmd.extend(["--test-tags", specific_test])
            elif specific_test.startswith("Test"):
                # TestClass format - for tour tests, ensure we include the module
                if len(self.modules) == 1:
                    # For single module, use module prefix to ensure proper discovery
                    cmd.extend(["--test-tags", f"/{self.modules[0]}:{specific_test}"])
                else:
                    # Multiple modules or no modules specified - try global search
                    cmd.extend(["--test-tags", specific_test])
            elif specific_test.startswith("/"):
                # Already a full tag format
                cmd.extend(["--test-tags", specific_test])
            else:
                # If not resolved above, treat as raw tag expression
                cmd.extend(["--test-tags", specific_test])
        elif test_type == "python-only":
            # Run module tests but exclude JS tests
            if self.modules:
                # Include module tests but exclude JS tests
                tags = [f"/{mod}" for mod in self.modules]
                exclusions = [f"-/{mod}:ProductConnectJSTests" for mod in self.modules]
                all_tags = tags + exclusions
                cmd.extend(["--test-tags", ",".join(all_tags)])

        docker_cmd = [
            "docker",
            "exec",
            "-e",
            "PYTHONUNBUFFERED=1",
            "-e",
            "PYTHONIOENCODING=utf-8",  # Ensure UTF-8 output encoding
            self.container_name,
        ] + cmd
        # Enable Python faulthandler to allow SIGUSR1 stack dumps on stalls
        docker_cmd = docker_cmd[:2] + ["-e", "PYTHONFAULTHANDLER=1"] + docker_cmd[2:]

        # Improve headless browser stability for tour/JS tests
        try:
            if (
                (test_type and "tour" in str(test_type).lower())
                or (specific_test and any(k in specific_test for k in ["HttpCase", "JSTest", "test_js", "Tour"]))
            ):
                # Enhanced browser configuration for tour tests to prevent hanging
                browser_env = [
                    "-e", "HEADLESS_CHROMIUM=1",
                    "-e", "CHROMIUM_BIN=/usr/bin/chromium",
                    "-e", "DISPLAY=:99",  # Set virtual display
                    # Override CHROMIUM_FLAGS with tour-specific optimizations
                    "-e", "CHROMIUM_FLAGS=--headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage --disable-software-rasterizer --window-size=1920,1080 --no-first-run --no-default-browser-check --disable-web-security --disable-features=VizDisplayCompositor,TranslateUI,site-per-process,IsolateOrigins,BlockInsecurePrivateNetworkRequests --virtual-time-budget=30000 --run-all-compositor-stages-before-draw --disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --disable-extensions --disable-plugins --disable-sync --disable-web-bluetooth --disable-web-usb",
                    # Additional environment variables to prevent hanging after tour completion
                    "-e", "ODOO_TEST_BROWSER_TIMEOUT=60",
                    "-e", "ODOO_TEST_TIMEOUT=300", 
                    "-e", "ODOO_TOUR_DISABLE_WEBSOCKET=1",  # Disable websockets that cause hanging
                    "-e", "ODOO_DISABLE_WEBSOCKET=1",  # Global websocket disable for tests
                ]
                docker_cmd = docker_cmd[:2] + browser_env + docker_cmd[2:]
                self.output_manager.write_line("Applied enhanced browser configuration for tour tests")
        except Exception as e:
            # Log error but proceed - don't let browser setup break the test
            if self.output_manager:
                self.output_manager.write_line(f"Warning: Browser setup failed: {e}")
            pass

        if self.debug or self.verbose:
            self.output_manager.write_line(f"Debug: Running command: {' '.join(docker_cmd)}")

        # Print initial info
        test_desc = specific_test or test_type
        modules_desc = f" for modules: {', '.join(self.modules)}" if self.modules else ""
        self.output_manager.write_line(f"Running {test_desc} tests{modules_desc}")
        self.output_manager.write_line(f"Output directory: {self.output_dir}")
        self.output_manager.write_line(f"Caller type: {self.caller_type}")
        self.output_manager.write_line("-" * 80)

        start_time = time.time()
        output_lines = []

        try:
            # Start process with real-time output and improved buffering
            process = subprocess.Popen(
                docker_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True,
            )
            
            last_output_time = time.time()
            stall_warnings = 0
            max_stall_warnings = 20  # Increased to be more tolerant of long operations

            took_stall_diagnostics = False
            tour_completed = False  # Track if tour has completed successfully
            is_tour_test = (test_type and "tour" in str(test_type).lower()) or (specific_test and any(k in specific_test for k in ["HttpCase", "JSTest", "test_js", "Tour"]))
            while True:
                # Check if process is still running
                if process.poll() is not None:
                    break

                # Check for critical errors - stop immediately if detected
                if self.output_manager.critical_error_detected:
                    self.output_manager.write_line("Terminating test process due to critical error...")
                    self._safe_terminate_process(process)
                    break

                # Check for timeout first
                current_time = time.time()
                if current_time - start_time > timeout:
                    self.output_manager.write_line(f"TIMEOUT: Test execution exceeded {timeout} seconds")
                    self._safe_terminate_process(process)
                    break

                # Try to read line with non-blocking select
                try:
                    # Use select to check if data is available (with adaptive timeout)
                    select_timeout = self._get_adaptive_select_timeout()
                    ready, _, _ = select.select([process.stdout], [], [], select_timeout)

                    if ready:
                        # Data is available, read it
                        line = process.stdout.readline()
                        if line:
                            line = line.rstrip()
                            output_lines.append(line)
                            self.output_manager.write_line(line)
                            last_output_time = time.time()
                            stall_warnings = 0  # Reset stall warnings on new output
                            
                            # Check if tour has completed successfully
                            if is_tour_test and not tour_completed:
                                if "Test completed successfully" in line or "test_basic_tour: ok" in line:
                                    tour_completed = True
                                    self.output_manager.write_line("✅ Tour completed successfully - waiting for clean shutdown...")
                                    # Give process 30 seconds to shutdown cleanly after tour completion
                                    tour_completion_timeout = time.time() + 30
                    else:
                        # No data available within select timeout
                        
                        # For tour tests, check if we should force terminate after completion
                        if is_tour_test and tour_completed:
                            if current_time > tour_completion_timeout:
                                self.output_manager.write_line("⚠️  Tour completed but process didn't exit cleanly - forcing termination")
                                self._safe_terminate_process(process)
                                break
                        
                        # Only check for stall if we're past the adaptive threshold
                        stall_threshold = self._get_adaptive_stall_threshold()
                        if current_time - last_output_time > stall_threshold:
                            stall_warnings += 1
                            last_test = getattr(self.output_manager.progress, "current_test", "") or "unknown"
                            phase = getattr(self.output_manager.progress, "phase", "") or "unknown"
                            self.output_manager.write_line(
                                f"WARNING: No output for {current_time - last_output_time:.1f}s "
                                f"(threshold: {stall_threshold}s) [{stall_warnings}/{max_stall_warnings}] "
                                f"(phase={phase}, last_test={last_test})"
                            )
                            # On first significant stall, capture diagnostics and try SIGUSR1 stack dump
                            if not took_stall_diagnostics and stall_warnings >= 3:
                                self._capture_stall_diagnostics()
                                took_stall_diagnostics = True

                            # Terminate if too many stall warnings (increased threshold)
                            if stall_warnings >= max_stall_warnings:
                                self.output_manager.write_line(
                                    f"STALLED: Process appears to be stuck after {stall_warnings} warnings. Terminating..."
                                )
                                self._safe_terminate_process(process)
                                break

                except Exception as e:
                    self.output_manager.write_line(f"Error reading process output: {e}")
                    # Don't break immediately - try to recover
                    time.sleep(0.1)
                    continue

            # Get final return code with timeout to prevent hanging
            try:
                return_code = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.output_manager.write_line("WARNING: Process did not exit cleanly, forcing termination")
                self._safe_terminate_process(process)
                return_code = -1
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

            # Get any remaining output with improved timeout handling
            try:
                # Use non-blocking approach to collect remaining output
                remaining_lines = []
                start_collect = time.time()
                max_collect_time = 10  # Maximum time to spend collecting remaining output
                
                while time.time() - start_collect < max_collect_time and process.poll() is None:
                    try:
                        ready, _, _ = select.select([process.stdout], [], [], 0.1)
                        if ready:
                            line = process.stdout.readline()
                            if line:
                                line = line.rstrip()
                                if line.strip():
                                    remaining_lines.append(line)
                                    output_lines.append(line)
                                    # Don't check for critical errors in remaining output
                                    if not self.output_manager.critical_error_detected:
                                        self.output_manager.write_line(line)
                            else:
                                # No more data available
                                break
                        else:
                            # No data ready, exit collection
                            break
                    except Exception:
                        # Error reading remaining data, exit collection
                        break
                        
                if remaining_lines:
                    self.output_manager.write_line(f"Collected {len(remaining_lines)} remaining output lines")
                    
            except Exception as e:
                self.output_manager.write_line(f"Error collecting remaining output: {e}")
                # Don't let this crash the entire test run

        except subprocess.TimeoutExpired:
            self.output_manager.write_line(f"Process timed out after {timeout} seconds")
            return_code = -1
            elapsed = timeout
        except Exception as e:
            self.output_manager.write_line(f"Unexpected error during test execution: {e}")
            return_code = -2
            elapsed = time.time() - start_time
        finally:
            # Ensure process cleanup to prevent zombies
            try:
                if 'process' in locals() and process is not None:
                    if process.poll() is None:
                        self.output_manager.write_line("Cleaning up running process...")
                        self._safe_terminate_process(process)
            except Exception as e:
                if self.output_manager:
                    self.output_manager.write_line(f"Error during final cleanup: {e}")
                else:
                    print(f"Error during final cleanup: {e}")

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

        # Close output manager only if we created it in this method
        if self._should_close_output_manager:
            self.output_manager.close()

        return results

    def _safe_terminate_process(self, process: subprocess.Popen) -> None:
        """Safely terminate a process with proper cleanup and deadlock prevention."""
        try:
            # First attempt: gentle termination
            if process.poll() is None:
                process.terminate()
                try:
                    # Wait for graceful termination with timeout
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate gracefully
                    if process.poll() is None:
                        process.kill()
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            # Process is truly stuck - log warning and force cleanup
                            self.output_manager.write_line("WARNING: Process failed to terminate cleanly - forcing container cleanup")
                            
            # Additional cleanup: kill any remaining test processes in container
            try:
                self._force_terminate_test_processes()
            except Exception as cleanup_error:
                self.output_manager.write_line(f"Warning during process cleanup: {cleanup_error}")
                
        except Exception as e:
            self.output_manager.write_line(f"Error during process termination: {e}")

    
    def _capture_stall_diagnostics(self) -> None:
        """Capture helpful diagnostics when output stalls to pinpoint the hang."""
        try:
            self.output_manager.write_line("🩺 Capturing stall diagnostics (process list, Python stacks)...")
            # Show process list inside container (first/last lines for brevity)
            ps_cmd = ["docker", "exec", self.container_name, "ps", "-ef"]
            ps = subprocess.run(ps_cmd, capture_output=True, text=True, timeout=10)
            if ps.returncode == 0 and ps.stdout:
                lines = ps.stdout.strip().splitlines()
                show = []
                show.extend(lines[:25])
                if len(lines) > 50:
                    show.append("... (snip) ...")
                    show.extend(lines[-25:])
                for ln in show:
                    self.output_manager.write_line(f"[ps] {ln}")
            else:
                self.output_manager.write_line(f"⚠️  Unable to collect process list: {ps.stderr.strip() if ps.stderr else 'no output'}")
            # Try to dump Python stacks via SIGUSR1 (enabled by PYTHONFAULTHANDLER=1)
            find_pid_cmd = [
                "docker", "exec", self.container_name, "sh", "-c",
                "pgrep -f 'python.*odoo|odoo-bin' || true"
            ]
            pid_res = subprocess.run(find_pid_cmd, capture_output=True, text=True, timeout=5)
            pids = [p for p in pid_res.stdout.strip().split() if p.isdigit()]
            if pids:
                for pid in pids[:3]:
                    self.output_manager.write_line(f"🔎 Sending SIGUSR1 to PID {pid} for Python traceback dump")
                    subprocess.run(["docker", "exec", self.container_name, "kill", "-USR1", pid], capture_output=True, text=True, timeout=5)
            else:
                self.output_manager.write_line("ℹ️  No Odoo Python PID found for SIGUSR1 dump")
        except Exception as e:
            self.output_manager.write_line(f"⚠️  Stall diagnostics error: {e}")

    def _get_adaptive_select_timeout(self) -> float:
        """Get adaptive select timeout based on current test phase."""
        if not hasattr(self, 'output_manager') or not self.output_manager:
            return 3.0  # Default fallback
            
        phase = self.output_manager.progress.phase
        
        # Longer timeouts for phases that legitimately take time
        phase_timeouts = {
            "starting": 5.0,
            "loading": 5.0,
            "modules_loaded": 3.0,
            "testing": 2.0,
            "javascript_tests": 10.0,  # JS tests can have long gaps
            "hoot_tests": 10.0,
            "tour": 8.0,
        }
        
        return phase_timeouts.get(phase, 3.0)

    def _get_adaptive_stall_threshold(self) -> int:
        """Get adaptive stall threshold that considers test phase and recent activity."""
        if not hasattr(self, 'output_manager') or not self.output_manager:
            return 180  # Default fallback
            
        phase = self.output_manager.progress.phase
        output_lines = self.output_manager.progress.output_lines_since_test
        
        # Base thresholds for different phases
        base_thresholds = {
            "starting": 180,      # Startup can be slow
            "loading": 180,       # Module loading
            "modules_loaded": 120, # Should start tests soon
            "ready_for_tests": 120,
            "testing": 240,       # Regular tests - increased from 120
            "javascript_tests": 900, # JS tests need much more time - increased from 600
            "hoot_tests": 900,    # Hoot tests - increased from 600
            "tour": 600,          # Tours - increased from 300
        }
        
        base_threshold = base_thresholds.get(phase, 180)
        
        # Adjust based on recent activity
        if output_lines < 50:
            # Recent activity, allow more time
            return int(base_threshold * 1.5)
        elif output_lines > 200:
            # Lots of output, might be stuck in a loop
            return int(base_threshold * 0.8)
        else:
            return base_threshold

    def run_progressive_tests(self, modules: list[str] | None = None) -> TestResults:
        """Run tests progressively: unit → validation → tour.

        Stops at first category failure for fail-fast behavior.
        """
        all_results = TestResults()

        # Initialize output manager if not already done
        if self.output_manager is None:
            self.output_manager = OutputManager(self.output_dir, self.caller_type)

        try:
            # Phase 1: Unit tests (fast, clean DB)
            self.output_manager.write_line("")
            self.output_manager.write_line("=" * 80)
            self.output_manager.write_line("🏃 Phase 1: Unit Tests (Fast - Clean Database)")
            self.output_manager.write_line("=" * 80)
            self.output_manager.write_line("")

            unit_results = self._run_test_category("unit", modules, None)
            all_results.total += unit_results.total
            all_results.passed += unit_results.passed
            all_results.failed += unit_results.failed
            all_results.errors += unit_results.errors

            # Continue even if unit tests fail to run all tests
            if unit_results.failed > 0 or unit_results.errors > 0:
                if self.output_manager:
                    self.output_manager.write_line("⚠️ Unit tests had failures but continuing with remaining tests...")

            # Comprehensive cleanup between phases
            self._deep_cleanup_between_phases("unit", "integration")

            # Phase 2: Integration tests (slow, production clone)
            self.output_manager.write_line("")
            self.output_manager.write_line("=" * 80)
            self.output_manager.write_line("🔍 Phase 2: Integration Tests (Slow - Production Clone)")
            self.output_manager.write_line("=" * 80)
            self.output_manager.write_line("")

            integration_results = self._run_test_category("integration", modules, None)
            all_results.total += integration_results.total
            all_results.passed += integration_results.passed
            all_results.failed += integration_results.failed
            all_results.errors += integration_results.errors

            # Continue even if integration tests fail to run all tests
            if integration_results.failed > 0 or integration_results.errors > 0:
                if self.output_manager:
                    self.output_manager.write_line("⚠️ Integration tests had failures but continuing with remaining tests...")

            # Comprehensive cleanup between phases
            self._deep_cleanup_between_phases("integration", "tour")

            # Phase 3: Tour tests (browser UI)
            self.output_manager.write_line("")
            self.output_manager.write_line("=" * 80)
            self.output_manager.write_line("🌐 Phase 3: Tour Tests (Browser UI)")
            self.output_manager.write_line("=" * 80)
            self.output_manager.write_line("")

            tour_results = self._run_test_category("tour", modules, None)
            all_results.total += tour_results.total
            all_results.passed += tour_results.passed
            all_results.failed += tour_results.failed
            all_results.errors += tour_results.errors

            # Final summary
            all_results.summary = f"All tests completed: {all_results.passed}/{all_results.total} passed"

        finally:
            # Final comprehensive cleanup
            self._deep_cleanup_between_phases("tour", "final")
            
            # Close output manager
            if self.output_manager:
                self.output_manager.close()

        return all_results

    def _setup_unit_test_database(self) -> None:
        """Set up a clean test database for unit tests.

        Creates a fresh empty database with the '_test' suffix and initializes it
        with only the necessary modules. This provides proper isolation for unit tests.
        """
        import os
        
        test_db = f"{self.database}_test" if not self.database.endswith("_test") else self.database
        db_password = os.environ.get("ODOO_DB_PASSWORD")
        if not db_password:
            raise RuntimeError("ODOO_DB_PASSWORD environment variable not set")
        
        container_prefix = os.environ.get("ODOO_CONTAINER_PREFIX", "odoo-opw")
        db_container = f"{container_prefix}-database-1"

        print(f"Setting up clean test database: {test_db}")

        # Step 1: Terminate any existing connections to the test database
        terminate_cmd = [
            "docker",
            "exec",
            "-e",
            f"PGPASSWORD={db_password}",
            db_container,
            "psql",
            "-U",
            "odoo",
            "-d",
            "postgres",
            "-c",
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{test_db}' AND pid <> pg_backend_pid();",
        ]
        result = subprocess.run(terminate_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Note: No connections to terminate (this is normal for first run)")

        # Step 2: Drop existing test database if it exists
        drop_cmd = [
            "docker",
            "exec",
            "-e", 
            f"PGPASSWORD={db_password}",
            db_container,
            "psql",
            "-U",
            "odoo",
            "-d",
            "postgres",
            "-c",
            f"DROP DATABASE IF EXISTS {test_db};"
        ]

        print(f"Dropping existing test database (if any)...")
        result = subprocess.run(drop_cmd, capture_output=True, text=True)
        if result.returncode != 0 and "does not exist" not in result.stderr:
            print(f"Warning: Could not drop database: {result.stderr}")
            print(f"Return code: {result.returncode}")

        # Step 3: Create new EMPTY database (not from template)
        create_cmd = [
            "docker",
            "exec",
            "-e",
            f"PGPASSWORD={db_password}",
            db_container,
            "psql",
            "-U",
            "odoo",
            "-d",
            "postgres",
            "-c",
            f"CREATE DATABASE {test_db} WITH TEMPLATE template0 ENCODING 'UTF8';",
        ]

        print(f"Creating fresh EMPTY test database...")
        result = subprocess.run(create_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error creating test database: {result.stderr}")
            print("Falling back to using base database")
            return

        # Step 4: Initialize the database with base modules and product_connect
        print(f"Initializing test database with modules...")
        init_cmd = [
            "docker",
            "exec",
            self.container_name,
            "/odoo/odoo-bin",
            "-d",
            test_db,
            "--addons-path",
            self.addons_path,
            "-i",
            "base,product_connect",  # Install base and our module
            "--stop-after-init",
            "--log-level=warn",
            "--without-demo=all",
        ]

        result = subprocess.run(init_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error initializing test database: {result.stderr}")
            print("Test database created but initialization failed")
        else:
            print(f"✅ Test database {test_db} initialized successfully")

        print("-" * 80)

    def _terminate_db_connections(self, db_name: str) -> None:
        import os
        db_password = os.environ.get("ODOO_DB_PASSWORD")
        if not db_password:
            raise RuntimeError("ODOO_DB_PASSWORD environment variable not set")
        
        container_prefix = os.environ.get("ODOO_CONTAINER_PREFIX", "odoo-opw")
        db_container = f"{container_prefix}-database-1"
        
        terminate_cmd = [
            "docker",
            "exec",
            "-e",
            f"PGPASSWORD={db_password}",
            db_container,
            "psql",
            "-U",
            "odoo",
            "-d",
            "postgres",
            "-c",
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();",
        ]
        result = subprocess.run(terminate_cmd, capture_output=True, text=True, timeout=30)
        
        # Also try to cancel any running queries on this database
        cancel_cmd = [
            "docker",
            "exec",
            "-e", 
            f"PGPASSWORD={db_password}",
            db_container,
            "psql",
            "-U",
            "odoo", 
            "-d",
            "postgres",
            "-c",
            f"SELECT pg_cancel_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND state = 'active';",
        ]
        subprocess.run(cancel_cmd, capture_output=True, text=True, timeout=10)

    def _drop_database_safely(self, db_name: str) -> None:
        import os
        if not db_name or db_name == "postgres":
            return
        try:
            self._terminate_db_connections(db_name)
            
            db_password = os.environ.get("ODOO_DB_PASSWORD")
            if not db_password:
                raise RuntimeError("ODOO_DB_PASSWORD environment variable not set")
            
            container_prefix = os.environ.get("ODOO_CONTAINER_PREFIX", "odoo-opw")
            db_container = f"{container_prefix}-database-1"
            
            drop_cmd = [
                "docker",
                "exec",
                "-e",
                f"PGPASSWORD={db_password}",
                db_container,
                "psql",
                "-U",
                "odoo",
                "-d",
                "postgres",
                "-c",
                f"DROP DATABASE IF EXISTS {db_name};",
            ]
            subprocess.run(drop_cmd, capture_output=True, text=True)
        except Exception:
            pass

    def _clone_production_database(self, target_db: str, source_db: str) -> None:
        import os
        
        if self.output_manager:
            self.output_manager.write_line(
                f"🗄️  Cloning database: {source_db} → {target_db}"
            )

        # Ensure target is dropped and source has no active connections
        self._terminate_db_connections(target_db)
        self._drop_database_safely(target_db)
        self._terminate_db_connections(source_db)

        db_password = os.environ.get("ODOO_DB_PASSWORD")
        if not db_password:
            raise RuntimeError("ODOO_DB_PASSWORD environment variable not set")
        
        container_prefix = os.environ.get("ODOO_CONTAINER_PREFIX", "odoo-opw")
        db_container = f"{container_prefix}-database-1"
        
        clone_cmd = [
            "docker",
            "exec",
            "-e",
            f"PGPASSWORD={db_password}",
            db_container,
            "psql",
            "-U",
            "odoo",
            "-d",
            "postgres",
            "-c",
            f"CREATE DATABASE {target_db} WITH TEMPLATE {source_db};",
        ]
        result = subprocess.run(clone_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Failed to clone database")

        if self.output_manager:
            self.output_manager.write_line(f"✅ Database cloned: {target_db}")

    def _create_filestore_symlink(self, test_db: str, production_db: str) -> None:
        test_filestore = f"/volumes/data/filestore/{test_db}"
        prod_filestore = f"/volumes/data/filestore/{production_db}"
        if self.output_manager:
            self.output_manager.write_line(
                f"🔗 Creating filestore link: {test_filestore} → {prod_filestore}"
            )
        cmd = [
            "docker",
            "exec",
            self.container_name,
            "sh",
            "-c",
            f"if [ -e '{test_filestore}' ]; then rm -rf '{test_filestore}'; fi && ln -s '{prod_filestore}' '{test_filestore}'",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Failed to create filestore symlink")
        if self.output_manager:
            self.output_manager.write_line("✅ Filestore symlink ready")

    def _cleanup_test_filestore(self, test_db: str) -> None:
        # Best-effort removal of test filestore path
        path = f"/volumes/data/filestore/{test_db}"
        cmd = ["docker", "exec", self.container_name, "sh", "-c", f"[ -L '{path}' ] && rm '{path}' || true"]
        subprocess.run(cmd, capture_output=True, text=True)

    def _deep_cleanup_between_phases(self, from_phase: str, to_phase: str) -> None:
        """Perform comprehensive cleanup between test phases to prevent hangs."""
        if self.output_manager:
            self.output_manager.write_line("")
            self.output_manager.write_line(f"🧹 Deep cleanup: {from_phase} → {to_phase}")
            self.output_manager.write_line("-" * 40)
        
        try:
            # 1. Force terminate all test-related processes
            self._force_terminate_test_processes()
            
            # 2. Clean up database connections
            self._cleanup_database_connections()
            
            # 3. Reset Docker container state
            self._reset_container_state()
            
            # 4. Clean up temporary files and locks
            self._cleanup_temp_files_and_locks()
            
            # 5. Wait for container to stabilize
            import time
            time.sleep(3)
            
            if self.output_manager:
                self.output_manager.write_line("✅ Deep cleanup completed")
                self.output_manager.write_line("")
                
        except Exception as e:
            if self.output_manager:
                self.output_manager.write_line(f"⚠️ Cleanup warning: {e}")

    def _force_cleanup_category_processes(self, category: str) -> None:
        """Force cleanup of processes specific to a test category."""
        try:
            # Kill any remaining processes for this category
            process_patterns = [
                "odoo-bin.*test-enable",
                "python.*odoo-bin",
                "timeout.*odoo-bin",
            ]
            
            # Add browser processes for tour tests
            if category == "tour":
                process_patterns.extend([
                    "chromium",
                    "chrome",
                    "chrome_crashpad",
                    "chromedriver",
                ])
            
            for pattern in process_patterns:
                cmd = ["docker", "exec", self.container_name, "pkill", "-f", pattern]
                subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                
            # Force kill any stubborn processes
            for pattern in process_patterns:
                cmd = ["docker", "exec", self.container_name, "pkill", "-9", "-f", pattern]
                subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                
        except Exception as e:
            if self.output_manager:
                self.output_manager.write_line(f"⚠️ Process cleanup warning: {e}")

    def _force_terminate_test_processes(self) -> None:
        """Aggressively terminate all test-related processes."""
        try:
            if self.output_manager:
                self.output_manager.write_line("   🔄 Terminating test processes...")
            
            # Get all test-related PIDs
            find_pids_cmd = [
                "docker", "exec", self.container_name, "sh", "-c",
                "pgrep -f 'odoo-bin.*test|python.*odoo|timeout.*odoo|chromium|chrome' || true"
            ]
            
            result = subprocess.run(find_pids_cmd, capture_output=True, text=True, timeout=10)
            pids = [p.strip() for p in result.stdout.split() if p.strip().isdigit()]
            
            if pids:
                if self.output_manager:
                    self.output_manager.write_line(f"     Found {len(pids)} processes to terminate")
                
                # Try graceful termination first
                for pid in pids:
                    cmd = ["docker", "exec", self.container_name, "kill", "-TERM", pid]
                    subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                
                # Wait a moment for graceful shutdown
                import time
                time.sleep(2)
                
                # Force kill any remaining processes
                for pid in pids:
                    cmd = ["docker", "exec", self.container_name, "kill", "-KILL", pid]
                    subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    
        except Exception as e:
            if self.output_manager:
                self.output_manager.write_line(f"     ⚠️ Process termination warning: {e}")

    def _cleanup_database_connections(self) -> None:
        """Clean up database connections and reset connection pool."""
        try:
            if self.output_manager:
                self.output_manager.write_line("   🗄️ Cleaning database connections...")
            
            # Terminate connections to all test databases
            db_patterns = [
                f"{self.database}_test",
                f"{self.database}_test_unit", 
                f"{self.database}_test_integration",
                f"{self.database}_test_tour"
            ]
            
            for db_pattern in db_patterns:
                try:
                    self._terminate_db_connections(db_pattern)
                except Exception:
                    pass  # Ignore errors for non-existent databases
                    
        except Exception as e:
            if self.output_manager:
                self.output_manager.write_line(f"     ⚠️ DB connection cleanup warning: {e}")

    def _reset_container_state(self) -> None:
        """Reset Docker container state without full restart."""
        try:
            if self.output_manager:
                self.output_manager.write_line("   🐳 Resetting container state...")
            
            # Clear shared memory segments
            cmd = ["docker", "exec", self.container_name, "sh", "-c", "ipcs -m | awk '/^0x/ {print $2}' | xargs -r ipcrm -m || true"]
            subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            # Clear semaphores
            cmd = ["docker", "exec", self.container_name, "sh", "-c", "ipcs -s | awk '/^0x/ {print $2}' | xargs -r ipcrm -s || true"]
            subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            # Clear orphaned sockets
            cmd = ["docker", "exec", self.container_name, "sh", "-c", "find /tmp -name '*.sock' -type s -delete || true"]
            subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
        except Exception as e:
            if self.output_manager:
                self.output_manager.write_line(f"     ⚠️ Container reset warning: {e}")

    def _cleanup_temp_files_and_locks(self) -> None:
        """Clean up temporary files and locks that might cause hangs."""
        try:
            if self.output_manager:
                self.output_manager.write_line("   🗂️ Cleaning temporary files and locks...")
            
            # Clean up Odoo temporary files
            cleanup_commands = [
                # Remove Odoo cache and session files
                "find /tmp -name 'openerp-*' -type f -delete || true",
                "find /tmp -name 'odoo-*' -type f -delete || true",
                "find /tmp -name '.odoo_*' -type f -delete || true",
                # Remove browser cache and temp files
                "find /tmp -name 'chrome*' -type d -exec rm -rf {} + || true",
                "find /tmp -name 'chromium*' -type d -exec rm -rf {} + || true",
                # Remove stale lock files
                "find /tmp -name '*.lock' -type f -delete || true",
                "find /tmp -name '*.pid' -type f -delete || true",
                # Clean up core dumps
                "find /tmp -name 'core.*' -type f -delete || true",
            ]
            
            for cleanup_cmd in cleanup_commands:
                cmd = ["docker", "exec", self.container_name, "sh", "-c", cleanup_cmd]
                subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                
        except Exception as e:
            if self.output_manager:
                self.output_manager.write_line(f"     ⚠️ Temp file cleanup warning: {e}")

    def _run_test_category(self, category: str, modules: list[str] | None, specific_test: str | None = None) -> TestResults:
        """Run a specific category of tests.

        Filters tests based on the test categorization tags:
        - unit: Runs tests tagged with 'unit_test' on clean test database
        - integration: Runs tests tagged with 'integration_test' on production database
        - tour: Runs tests tagged with 'tour_test' on production database
        """
        # Map category to test tag
        tag_map = {
            "unit": "unit_test",
            "integration": "integration_test",
            "tour": "tour_test",
        }

        test_tag = tag_map.get(category)
        if not test_tag:
            # Fallback to running all tests if category not recognized
            timeout = get_recommended_timeout(category, test_mode=category)
            return self._run_normal_tests(category, None, timeout, modules)
        
        # Track whether modules were explicitly provided by the user
        explicit_modules = bool(modules)

        # Prepare isolated database per category
        original_db = self.database
        test_db_was_prepared = False

        if category == "unit":
            # Clean empty test DB for unit tests
            try:
                self._setup_unit_test_database()
                self.database = f"{original_db}_test" if not original_db.endswith("_test") else original_db
                test_db_was_prepared = True
            except Exception as e:
                # Fall back to original DB if setup fails
                if self.output_manager:
                    self.output_manager.write_line(f"⚠️  Failed to setup unit test database: {e}. Falling back to {original_db}.")
                self.database = original_db

        elif category in ("integration", "tour"):
            # Clone production DB for isolation
            cloned_db = f"{original_db}_test_{category}"
            try:
                self._clone_production_database(cloned_db, source_db=original_db)
                self.database = cloned_db
                test_db_was_prepared = True
                # For integration and tour tests, ensure filestore access (attachments, images)
                if category in ("integration", "tour"):
                    try:
                        self._create_filestore_symlink(cloned_db, original_db)
                    except Exception as fe:
                        if self.output_manager:
                            self.output_manager.write_line(f"⚠️  Failed to create filestore symlink: {fe}")
            except Exception as e:
                if self.output_manager:
                    self.output_manager.write_line(f"⚠️  Failed to clone database for {category}: {e}. Using {original_db}.")
                self.database = original_db

        # If a specific test was requested, resolve/forward it instead of broad tag filters
        resolved_specific = None
        if specific_test:
            try:
                if re.match(r"^test_[A-Za-z0-9_]+$", specific_test):
                    search_modules = modules or (self.modules if self.modules else self.discover_local_modules())
                    resolved = self._resolve_bare_test_method(specific_test, search_modules)
                    if resolved:
                        resolved_specific = resolved["tag"]  # format: /module:Class.method
                        # Align module context to improve downstream handling/logs
                        self.modules = [resolved["module"]]
                else:
                    # Use as-is (could be TestClass or TestClass.method or already /module:...)
                    resolved_specific = specific_test
            except Exception:
                # Non-fatal; fall back to tag-based selection
                resolved_specific = None

        if resolved_specific:
            test_tags = resolved_specific
        else:
            # Build the tag filter for Odoo test runner
            # Correct format is: tag/module or just /module (NOT /module:tag)
            # To filter by tag in specific modules, use: tag/module1,tag/module2
            if modules:
                # Run tests with specific tag in specific modules
                test_tags = ",".join([f"{test_tag}/{module}" for module in modules])
            else:
                # Discover our custom modules and run tests only for them
                # This prevents running Odoo core tests that may cause conflicts
                discovered_modules = self.discover_local_modules()
                if discovered_modules:
                    test_tags = ",".join([f"{test_tag}/{module}" for module in discovered_modules])
                else:
                    # Fallback if no modules discovered
                    test_tags = test_tag

        # Get appropriate timeout for this category
        timeout = get_recommended_timeout(category, test_mode=category)

        # Run tests with tag filtering
        try:
            return self._run_tests_with_tags(test_tags, timeout, modules, category)
        finally:
            # Cleanup cloned/created test DBs to avoid accumulation
            if test_db_was_prepared:
                try:
                    if category in ("integration", "tour"):
                        # Best-effort cleanup of filestore link
                        self._cleanup_test_filestore(self.database)
                    # Drop the test database
                    self._drop_database_safely(self.database)
                except Exception as ce:
                    if self.output_manager:
                        self.output_manager.write_line(f"⚠️  Cleanup warning for {self.database}: {ce}")
                finally:
                    # Restore original database name for subsequent phases
                    self.database = original_db
                    
                    # Ensure full process cleanup after each category
                    self._force_cleanup_category_processes(category)

    def _run_tests_with_tags(self, test_tags: str, timeout: int, modules: list[str] | None, category: str) -> TestResults:
        """Run tests with specific tag filtering.

        Args:
            test_tags: Comma-separated tag filters (e.g., "/product_connect:unit_test")
            timeout: Maximum time for test execution
            modules: Optional list of modules to test
            category: Category name for display
        """
        # Reuse the existing run_tests_with_streaming method
        # but pass the tag filter as the specific_test parameter
        return self.run_tests_with_streaming(
            test_type=f"{category} (tagged)", specific_test=test_tags, timeout=timeout, modules=modules
        )

    def _run_normal_tests(self, test_type: str, specific_test: str | None, timeout: int, modules: list[str] | None) -> TestResults:
        """Run tests in normal mode (current behavior)."""
        # This is essentially a wrapper for the existing run_tests_with_streaming
        return self.run_tests_with_streaming(test_type=test_type, specific_test=specific_test, timeout=timeout, modules=modules)

    def _parse_test_results(self, output: str) -> TestResults:
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
            else:
                # Fall back to progress tracking if no standard summary found
                if hasattr(self.output_manager, 'progress') and self.output_manager.progress.tests_started > 0:
                    results.total = self.output_manager.progress.tests_started
                    # For tour tests, we need to parse the actual results from output
                    # since TestProgress doesn't track pass/fail status
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

        # Only check for @tagged if we see no tests starting (module-wide runs don't show @tagged)
        if "@tagged" not in output and "Starting Test" not in output and "INFO opw odoo.addons" not in output:
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

    def cleanup_old_test_folders(self, keep_recent: int = 10, days_old: int | None = None) -> dict[str, Any]:
        """Clean up old test folders to save disk space."""
        test_dir = Path("tmp/tests")
        if not test_dir.exists():
            return {"removed": 0, "kept": 0, "space_saved": 0}

        # Get all test folders sorted by modification time (newest first)
        test_folders = []
        for folder in test_dir.iterdir():
            if folder.is_dir() and folder.name.startswith("odoo-tests-"):
                test_folders.append((folder, folder.stat().st_mtime))

        test_folders.sort(key=lambda x: x[1], reverse=True)

        # Determine which folders to remove
        folders_to_remove = []
        folders_to_keep = []
        current_time = time.time()

        for i, (folder, mtime) in enumerate(test_folders):
            # Check age-based removal
            if days_old and (current_time - mtime) > (days_old * 24 * 60 * 60):
                folders_to_remove.append(folder)
            # Check count-based removal
            elif i >= keep_recent:
                folders_to_remove.append(folder)
            else:
                folders_to_keep.append(folder)

        # Calculate space to be saved
        space_saved = 0
        for folder in folders_to_remove:
            try:
                # Calculate folder size
                folder_size = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())
                space_saved += folder_size

                # Remove the folder
                shutil.rmtree(folder)
                if self.verbose:
                    print(f"Removed: {folder.name} ({folder_size / 1024 / 1024:.1f} MB)")
            except Exception as e:
                if self.verbose:
                    print(f"Failed to remove {folder.name}: {e}")

        return {
            "removed": len(folders_to_remove),
            "kept": len(folders_to_keep),
            "space_saved": space_saved,
            "space_saved_mb": round(space_saved / 1024 / 1024, 1),
        }


def get_recommended_timeout(test_type: str, specific_test: str | None = None, test_mode: str = "mixed") -> int:
    # Much longer timeouts for reliability based on mode
    if test_mode == "unit":
        # Unit tests should be fast
        return 300  # 5 minutes max for unit tests
    elif test_mode == "integration":
        # Integration tests on production data need lots of time
        return 3600  # 60 minutes for integration
    elif test_mode == "tour":
        # Tour tests need time for browser
        return 1800  # 30 minutes for tours
    elif test_mode == "all":
        # Progressive execution needs time for everything
        return 5400  # 90 minutes total (unit + integration + tour)

    # Legacy mode-specific timeouts
    if specific_test and ("JSTest" in specific_test or "HttpCase" in specific_test or "test_js" in specific_test):
        return 2100  # 35 minutes for JS tests
    elif specific_test and "." in specific_test:
        return 300  # Individual test method
    elif specific_test:
        return 900  # Specific test class
    elif test_type == "all":
        return 3600  # 60 minutes
    elif test_type == "tour":
        return 1800  # 30 minutes
    elif test_type == "python":
        return 1800  # 30 minutes
    elif test_type == "js":
        return 2100  # 35 minutes
    else:
        return 900  # Default 15 minutes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified Odoo Test Runner - Multi-mode test execution with progressive support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # First-time setup (creates clean test database)
  python tools/setup_test_db.py
  
  # Progressive execution (recommended - fail fast)
  python test_runner.py --all      # Runs unit → integration → tour
  
  # Individual test modes
  python test_runner.py --unit-only       # Fast unit tests (3 min)
  python test_runner.py --integration-only  # Production data tests (30 min)
  python test_runner.py --tour-only       # Browser UI tests (15 min)
  
  # Legacy modes (current behavior)
  python test_runner.py --mixed    # All tests mixed (current default)
  python test_runner.py --python   # Python tests only
  python test_runner.py --tour     # Tour tests only
  
  # Run tests for specific module(s)
  python test_runner.py product_connect
  python test_runner.py TestProductTemplate
  python test_runner.py TestProductTemplate.test_sku_validation
  
  # Cleanup old test folders
  python test_runner.py --cleanup
  python test_runner.py --cleanup --keep-recent 5
  python test_runner.py --cleanup --days-old 7
        """,
    )

    # Positional arguments for modules or specific tests
    parser.add_argument(
        "targets",
        nargs="*",
        help="Module names or specific test (TestClass or TestClass.test_method)",
    )

    # Test type flags
    test_group = parser.add_mutually_exclusive_group()
    # New progressive modes
    test_group.add_argument("--all", action="store_true", help="Progressive execution: unit → integration → tour (fail fast)")
    test_group.add_argument("--unit-only", action="store_true", help="Run only fast unit tests (clean DB, ~3 min)")
    test_group.add_argument("--integration-only", action="store_true", help="Run only integration tests (production clone, ~30 min)")
    test_group.add_argument("--tour-only", action="store_true", help="Run only tour/browser tests (~15 min)")
    # Legacy modes
    test_group.add_argument("--mixed", action="store_true", help="Run all tests mixed (current behavior)")
    test_group.add_argument("--python", action="store_true", help="Run Python tests only (legacy)")
    test_group.add_argument("--tour", action="store_true", help="Run tour tests only (legacy)")
    test_group.add_argument("--summary", action="store_true", help="Show summary of available tests")
    test_group.add_argument("--failing", action="store_true", help="Show currently failing tests")

    # Cleanup options
    parser.add_argument("--cleanup", action="store_true", help="Clean up old test folders")
    parser.add_argument("--keep-recent", type=int, default=10, help="Number of recent test folders to keep (default: 10)")
    parser.add_argument("--days-old", type=int, help="Remove test folders older than N days")

    # Other options
    parser.add_argument("-v", "--verbose", action="store_true", help="Show detailed output")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("-t", "--timeout", type=int, default=None, help="Timeout in seconds")
    parser.add_argument("-j", "--json", action="store_true", help="Output results as JSON")
    parser.add_argument("-c", "--container", type=str, default=None, help="Docker container name (defaults to ODOO_CONTAINER_PREFIX-script-runner-1)")
    parser.add_argument("-d", "--database", type=str, default="opw", help="Database name (unit tests will use {database}_test)")
    parser.add_argument(
        "-p", "--addons-path", type=str, default="/volumes/addons,/odoo/addons,/volumes/enterprise", help="Addons path"
    )

    args = parser.parse_args()

    # Handle shortcut mode names in targets
    # If first target is a mode name, treat it as mode selection
    if args.targets and len(args.targets) > 0:
        first_target = args.targets[0]
        if first_target in ["unit", "integration", "tour", "all", "python", "failing", "summary"]:
            # It's a mode shortcut, not a module name
            if first_target == "unit":
                args.unit_only = True
                args.targets = args.targets[1:]  # Remove mode from targets
            elif first_target == "integration":
                args.integration_only = True
                args.targets = args.targets[1:]
            elif first_target == "tour":
                args.tour_only = True
                args.targets = args.targets[1:]
            elif first_target == "all":
                args.all = True
                args.targets = args.targets[1:]
            elif first_target == "python":
                args.python = True
                args.targets = args.targets[1:]
            elif first_target == "failing":
                args.failing = True
                args.targets = args.targets[1:]
            elif first_target == "summary":
                args.summary = True
                args.targets = args.targets[1:]

    # Determine test mode
    if args.all:
        test_mode = "all"  # Progressive execution
    elif args.unit_only:
        test_mode = "unit"
    elif args.integration_only:
        test_mode = "integration"
    elif args.tour_only:
        test_mode = "tour"
    elif args.mixed:
        test_mode = "mixed"
    else:
        test_mode = "mixed"  # Default to current behavior for compatibility

    runner = UnifiedTestRunner(
        verbose=args.verbose,
        debug=args.debug,
        container=args.container,
        database=args.database,
        addons_path=args.addons_path,
        test_mode=test_mode,
    )

    # Handle cleanup mode
    if args.cleanup:
        print("Cleaning up old test folders...")
        cleanup_results = runner.cleanup_old_test_folders(keep_recent=args.keep_recent, days_old=args.days_old)
        print(f"Removed {cleanup_results['removed']} folders")
        print(f"Kept {cleanup_results['kept']} recent folders")
        print(f"Freed {cleanup_results['space_saved_mb']} MB of disk space")
        sys.exit(0)

    # Determine test type for legacy modes
    if args.python:
        test_type = "python"
    elif args.tour:
        test_type = "tour"
    elif args.summary:
        test_type = "summary"
    elif args.failing:
        test_type = "failing"
    else:
        test_type = "all"  # Default

    # Parse targets - could be modules or specific tests
    modules = []
    specific_test = None

    if args.targets:
        # Check if targets look like test specifications
        first_target = args.targets[0]
        if (
            first_target.startswith("Test")
            or first_target.startswith("test_")
            or "." in first_target
            or ":" in first_target
            or "/" in first_target
        ):
            # It's a specific test (class, method, or tag expression)
            specific_test = first_target
            # If module is specified with test, extract it
            if ":" in specific_test and "/" not in specific_test:
                module, test = specific_test.split(":", 1)
                modules = [module]
        else:
            # They're module names
            modules = args.targets

    # Determine timeout
    timeout = args.timeout
    if timeout is None:
        timeout = get_recommended_timeout(test_type, specific_test, test_mode)
        if args.verbose or args.debug:
            print(f"Using recommended timeout: {timeout} seconds ({timeout // 60} minutes)")

    # Run tests based on mode
    if test_mode == "all":
        # Progressive execution
        results = runner.run_progressive_tests(modules)
        results_dict = asdict(results)
    elif test_mode in ["unit", "integration", "tour"]:
        # Run specific test category with tag filtering (supports specific tests too)
        results = runner._run_test_category(test_mode, modules, specific_test)
        results_dict = asdict(results)
    elif test_mode == "mixed":
        # Mixed mode - run all tests together (legacy behavior)
        results = runner.run_tests_with_streaming(test_type, specific_test, timeout, modules)
        results_dict = asdict(results)
    elif test_type == "python":
        # Python tests should run ALL categories to get 350+ tests
        # Use progressive runner which handles output manager properly
        results = runner.run_progressive_tests(modules)
        results_dict = asdict(results)
    elif test_type == "failing":
        # Quick implementation - just check recent test results
        import glob
        import json
        
        # Find most recent test summary
        test_dirs = sorted(glob.glob("tmp/tests/odoo-tests-*/summary.json"), reverse=True)
        if test_dirs:
            with open(test_dirs[0], 'r') as f:
                recent = json.load(f)
                failing = recent.get("failures", []) + recent.get("errors_list", [])
                print(f"Recent failing tests from {test_dirs[0]}:")
                for test in failing:
                    print(f"  ❌ {test}")
                if not failing:
                    print("  ✅ No failing tests in most recent run")
        else:
            print("No recent test runs found. Run tests first.")
        sys.exit(0)
    elif test_type == "summary":
        # Just show what would be tested
        if not modules:
            modules = runner.discover_local_modules()
        print(f"Would test the following modules: {', '.join(modules)}")
        print(f"Test mode: {test_mode}")
        if test_mode in ["unit", "integration", "tour", "all"]:
            print(f"\nWith new multi-mode runner:")
            print(f"  Unit tests: ~123 tests (3 min)")
            print(f"  Integration tests: ~194 tests (30 min)")
            print(f"  Tour tests: ~14 tests (15 min)")
        sys.exit(0)
    else:
        results = runner.run_tests_with_streaming(test_type, specific_test, timeout, modules)
        results_dict = asdict(results)

    # Output results
    if args.json:
        print(json.dumps(results_dict, indent=2))
    else:
        # Human readable output
        if test_type == "failing":
            # Special handling for failing tests case
            print(f"\n=== Currently Failing Tests ({results_dict['count']}) ===")
            for test in results_dict["failing_tests"]:
                print(f"  - {test}")
        elif isinstance(results, TestResults):
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
