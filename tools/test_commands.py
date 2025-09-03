#!/usr/bin/env python3

import json
import os
import re
import secrets
import select
import string
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def normalize_line_for_pattern_detection(line: str) -> str:
    """Normalize a log line for pattern detection by removing timestamps and variable parts."""

    # Remove timestamps like "2025-08-26 02:10:28,708"
    line = re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}", "[TIMESTAMP]", line)

    # Remove IP addresses like "127.0.0.1"
    line = re.sub(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "[IP]", line)

    # Remove process IDs and other numbers that might vary
    line = re.sub(r"\b\d+\b", "[NUM]", line)

    # Remove version strings like "18.0-5"
    line = re.sub(r"\d+\.\d+(-\d+)?", "[VERSION]", line)

    # Normalize whitespace
    line = " ".join(line.split())

    return line.strip()


def detect_repetitive_pattern(recent_lines: list, pattern_occurrences: dict, min_occurrences: int = 5) -> tuple[bool, str]:
    """
    Detect if we're seeing repetitive patterns in the log output.
    Returns (is_repetitive, pattern_description).
    """
    if len(recent_lines) < min_occurrences:
        return False, ""

    # Update pattern occurrences count for all recent lines
    for line in recent_lines:
        normalized = normalize_line_for_pattern_detection(line)
        if normalized and len(normalized) > 20:  # Ignore very short lines
            pattern_occurrences[normalized] = pattern_occurrences.get(normalized, 0) + 1

    # Find the most common pattern
    if pattern_occurrences:
        most_common_pattern = max(pattern_occurrences.items(), key=lambda x: x[1])
        pattern, count = most_common_pattern

        if count >= min_occurrences:
            # Check if this pattern dominates recent output (>70% of recent lines)
            recent_normalized = [normalize_line_for_pattern_detection(line) for line in recent_lines]
            matching_lines = [norm for norm in recent_normalized if norm == pattern]
            pattern_ratio = len(matching_lines) / len(recent_normalized) if recent_normalized else 0

            if pattern_ratio > 0.7:  # More than 70% of recent lines are the same pattern
                # Extract a readable part of the original pattern
                original_sample = ""
                for line in recent_lines:
                    if normalize_line_for_pattern_detection(line) == pattern:
                        original_sample = line[:100] + "..." if len(line) > 100 else line
                        break

                return True, f"Repetitive pattern detected ({count} times, {pattern_ratio:.1%} of recent output): {original_sample}"

    return False, ""


def kill_browser_processes(container_prefix: str = None) -> None:
    """Aggressively kill browser processes to prevent websocket cleanup hangs."""
    if container_prefix is None:
        container_prefix = get_container_prefix()

    browser_patterns = ["chromium.*headless", "chrome.*headless", "chromium", "chrome", "WebDriver", "geckodriver", "chromedriver"]

    for pattern in browser_patterns:
        try:
            # Use SIGKILL (-9) for immediate termination
            subprocess.run(
                ["docker", "exec", f"{container_prefix}-script-runner-1", "pkill", "-9", "-f", pattern],
                capture_output=True,
                timeout=5,
            )
        except:
            pass  # Ignore errors - process might not exist


def safe_terminate_process(process: subprocess.Popen, container_prefix: str = None) -> None:
    """Safely terminate a process with proper cleanup."""
    if container_prefix is None:
        container_prefix = get_container_prefix()

    try:
        # First attempt: gentle termination
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't terminate gracefully
                if process.poll() is None:
                    process.kill()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        print("WARNING: Process failed to terminate cleanly")

        # Kill any test processes in container
        patterns = [
            "odoo-bin.*test-enable",
            "python.*odoo-bin",
            "timeout.*odoo-bin",
            "chromium",
            "chrome",
        ]

        for pattern in patterns:
            try:
                subprocess.run(
                    ["docker", "exec", f"{container_prefix}-script-runner-1", "pkill", "-f", pattern], capture_output=True, timeout=5
                )
            except:
                pass  # Ignore cleanup failures

    except Exception as e:
        print(f"Error during process termination: {e}")


def get_container_prefix() -> str:
    """Get the container prefix from environment or use default."""
    return os.environ.get("ODOO_PROJECT_NAME", "odoo")


def get_production_db_name() -> str:
    result = subprocess.run(["docker", "compose", "config", "--format", "json"], capture_output=True, text=True)
    if result.returncode == 0:
        import json

        config = json.loads(result.stdout)
        for service_name, service in config.get("services", {}).items():
            if "web" in service_name.lower():
                env = service.get("environment", {})
                if isinstance(env, dict):
                    return env.get("ODOO_DB_NAME", "odoo")
                elif isinstance(env, list):
                    for env_var in env:
                        if env_var.startswith("ODOO_DB_NAME="):
                            return env_var.split("=", 1)[1]
    return "odoo"


def get_script_runner_service() -> str:
    result = subprocess.run(["docker", "compose", "ps", "--services"], capture_output=True, text=True)
    services = result.stdout.strip().split("\n") if result.returncode == 0 else []
    for service in services:
        if "script" in service.lower() and "runner" in service.lower():
            return service
    return "script-runner"


def get_our_modules() -> list[str]:
    modules = []
    addons_path = Path("addons")
    if addons_path.exists():
        for module_dir in addons_path.iterdir():
            if not module_dir.is_dir():
                continue
            if (module_dir / "__manifest__.py").exists():
                name = module_dir.name
                # Skip backup/temp/experimental folders
                lowered = name.lower()
                if any(term in lowered for term in ("backup", "codex", "_bak", "~")):
                    continue
                modules.append(name)
    return modules


def run_unit_tests(modules: list[str] | None = None) -> int:
    """Run unit tests.

    If ``modules`` is provided, restrict installation and test tags to that
    subset. This enables focused runs like:

        python -m tools.test_commands unit user_name_extended

    Default behavior (``modules is None``) runs against all custom addons.
    """
    if modules:
        # Keep only valid modules present in our addons directory
        available = set(get_our_modules())
        modules = [m for m in modules if m in available]
        if not modules:
            print("❌ No matching modules found under ./addons for requested unit test run")
            return 1
    else:
        modules = get_our_modules()

    test_db_name = f"{get_production_db_name()}_test_unit"
    # When scoping to specific modules, prefix test tags so only their tests run
    use_prefix = True if modules else False
    return run_docker_test_command("unit_test", test_db_name, modules, timeout=600, use_module_prefix=use_prefix)


def run_integration_tests() -> int:
    modules = get_our_modules()
    test_db_name = f"{get_production_db_name()}_test_integration"
    return run_docker_test_command(
        "integration_test", test_db_name, modules, timeout=600, use_production_clone=True, use_module_prefix=False
    )


def run_tour_tests() -> int:
    print("🧪 Starting tour tests...")
    modules = get_our_modules()
    test_db_name = f"{get_production_db_name()}_test_tour"
    print(f"   Database: {test_db_name}")
    print(f"   Modules: {', '.join(modules)}")
    return run_docker_test_command(
        "tour_test", test_db_name, modules, timeout=1800, use_production_clone=True, is_tour_test=True, use_module_prefix=False
    )


def run_all_tests() -> int:
    """Run all test categories without hanging.

    Runs unit → integration → tour in separate test sessions to avoid
    cross-category interference and long single-run initialization that
    can hang. Each category uses its tuned timeout and cleanup.
    """
    print("🧪 Running ALL tests (unit → integration → tour)")
    print("=" * 60)

    rc = 0

    # 1) Unit tests on clean DB
    print("\n▶️  Phase 1: Unit tests")
    rc_unit = run_unit_tests()
    rc |= rc_unit != 0

    # 2) Integration tests on cloned DB
    print("\n▶️  Phase 2: Integration tests")
    rc_integration = run_integration_tests() if rc_unit == 0 else rc_unit
    rc |= rc_integration != 0

    # 3) Tour tests (browser) on cloned DB
    print("\n▶️  Phase 3: Tour tests")
    rc_tour = run_tour_tests() if rc_integration == 0 else rc_integration
    rc |= rc_tour != 0

    if rc == 0:
        print("\n✅ All categories passed")
        return 0
    else:
        print("\n❌ Some categories failed")
        # Return first non-zero code for conventional CI semantics
        return rc_unit or rc_integration or rc_tour or 1


def show_test_stats() -> int:
    modules = get_our_modules()

    print("Test Statistics for all modules:")
    print("=" * 50)

    grand_total_files = 0
    grand_categories = {
        "unit_test": 0,
        "integration_test": 0,
        "tour_test": 0,
        "validation_test": 0,
    }

    for module in modules:
        print(f"\nModule: {module}")
        print("-" * 30)

        test_root = Path(f"addons/{module}/tests")
        if not test_root.exists():
            print("  ❌ No tests directory")
            continue

        categories = {
            "unit_test": 0,
            "integration_test": 0,
            "tour_test": 0,
            "validation_test": 0,
        }

        total_files = 0
        for test_file in test_root.rglob("test_*.py"):
            if test_file.name.startswith("test_"):
                total_files += 1
                with open(test_file) as f:
                    content = f.read()
                    if "@tagged(*UNIT_TAGS)" in content or '"unit_test"' in content or "'unit_test'" in content:
                        categories["unit_test"] += 1
                    elif (
                        "@tagged(*INTEGRATION_TAGS)" in content or '"integration_test"' in content or "'integration_test'" in content
                    ):
                        categories["integration_test"] += 1
                    elif "@tagged(*TOUR_TAGS)" in content or '"tour_test"' in content or "'tour_test'" in content:
                        categories["tour_test"] += 1
                    elif "validation" in test_file.name.lower() or '"validation_test"' in content or "'validation_test'" in content:
                        categories["validation_test"] += 1

        print(f"  Total test files: {total_files}")
        for category, count in categories.items():
            print(f"  {category:20}: {count:3} files")
            grand_categories[category] += count

        grand_total_files += total_files

    print("\n" + "=" * 50)
    print("GRAND TOTALS:")
    print(f"Total test files: {grand_total_files}")
    for category, count in grand_categories.items():
        print(f"{category:20}: {count:3} files")

    print("\nTo run tests:")
    print("  uv run test-unit        # Fast unit tests")
    print("  uv run test-integration # Integration tests")
    print("  uv run test-tour        # Browser tours")
    print("  uv run test-all         # All tests")
    print("  uv run test-quick       # Subset of unit tests")
    print("  uv run test-clean       # Clean up test artifacts")

    # Show recent test logs for agents to easily find
    print("\n" + "=" * 50)
    print("RECENT TEST LOGS:")
    log_dir = Path("tmp/test-logs")
    if log_dir.exists():
        # Get last 5 test runs
        test_dirs = sorted([d for d in log_dir.iterdir() if d.is_dir()], reverse=True)[:5]
        if test_dirs:
            for test_dir in test_dirs:
                summary_file = test_dir / "summary.json"
                if summary_file.exists():
                    try:
                        with open(summary_file) as f:
                            summary = json.load(f)
                            status = "✅ PASSED" if summary.get("success") else "❌ FAILED"
                            if summary.get("timeout"):
                                status = "⏱️ TIMEOUT"
                            test_type = summary.get("test_type", "unknown")
                            elapsed = summary.get("elapsed_seconds", 0)
                            print(f"  {test_dir.name}: {status} ({test_type}, {elapsed:.1f}s)")
                            print(f"    📁 Logs: {test_dir}")
                    except:
                        print(f"  {test_dir.name}: [Could not read summary]")
        else:
            print("  No recent test runs found")
    else:
        print("  No test logs directory found yet")

    return 0


def cleanup_test_databases(production_db: str = None) -> None:
    """Drop all test databases matching pattern ${PRODUCTION_DB}_test_*"""
    if production_db is None:
        production_db = get_production_db_name()

    print(f"🧹 Cleaning up test databases for {production_db}...")

    # Get list of test databases
    list_cmd = [
        "docker",
        "exec",
        f"{get_container_prefix()}-database-1",
        "psql",
        "-U",
        "odoo",
        "-d",
        "postgres",
        "-t",
        "-c",
        f"SELECT datname FROM pg_database WHERE datname LIKE '{production_db}_test_%';",
    ]

    result = subprocess.run(list_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"   ⚠️  Could not list databases: {result.stderr}")
        return

    test_dbs = [db.strip() for db in result.stdout.strip().split("\n") if db.strip()]

    if not test_dbs:
        print(f"   No test databases found")
        return

    print(f"   Found {len(test_dbs)} test database(s): {', '.join(test_dbs)}")

    for db in test_dbs:
        # Terminate connections
        kill_cmd = [
            "docker",
            "exec",
            f"{get_container_prefix()}-database-1",
            "psql",
            "-U",
            "odoo",
            "-d",
            "postgres",
            "-c",
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db}' AND pid <> pg_backend_pid();",
        ]
        subprocess.run(kill_cmd, capture_output=True)

        # Drop database
        drop_cmd = ["docker", "exec", f"{get_container_prefix()}-database-1", "dropdb", "-U", "odoo", "--if-exists", db]
        result = subprocess.run(drop_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"   ✅ Dropped {db}")
        else:
            print(f"   ⚠️  Failed to drop {db}: {result.stderr}")


def create_filestore_symlink(test_db_name: str, production_db: str) -> None:
    production_filestore = f"/volumes/data/filestore/{production_db}"
    test_filestore = f"/volumes/data/filestore/{test_db_name}"

    # Find the running script-runner container
    script_runner_service = get_script_runner_service()

    # First try to use any running script-runner container
    list_cmd = ["docker", "ps", "-q", "-f", f"name={get_container_prefix()}-{script_runner_service}", "-f", "status=running"]
    result = subprocess.run(list_cmd, capture_output=True, text=True)

    if result.returncode == 0 and result.stdout.strip():
        # Use the first running container
        container_id = result.stdout.strip().split()[0]
        container_name = container_id[:12]  # Use short ID
    else:
        # Fallback to creating the symlink on the host via docker compose run
        print(f"   Creating filestore symlink via docker compose run...")
        symlink_cmd = [
            "docker",
            "compose",
            "run",
            "--rm",
            script_runner_service,
            "sh",
            "-c",
            f"if [ -e '{test_filestore}' ]; then rm -rf '{test_filestore}'; fi && ln -s '{production_filestore}' '{test_filestore}'",
        ]
        result = subprocess.run(symlink_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"   ✅ Created filestore symlink: {test_filestore} → {production_filestore}")
        else:
            print(f"   ❌ Failed to create filestore symlink: {result.stderr}")
        return

    cleanup_cmd = [
        "docker",
        "exec",
        container_name,
        "sh",
        "-c",
        f"if [ -e '{test_filestore}' ]; then rm -rf '{test_filestore}'; fi",
    ]
    result = subprocess.run(cleanup_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"   ⚠️  Warning: Could not clean existing filestore: {result.stderr}")

    symlink_cmd = [
        "docker",
        "exec",
        container_name,
        "ln",
        "-s",
        production_filestore,
        test_filestore,
    ]
    result = subprocess.run(symlink_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"   ✅ Created filestore symlink: {test_filestore} → {production_filestore}")
    else:
        print(f"   ❌ Failed to create filestore symlink: {result.stderr}")


def cleanup_test_filestores(production_db: str = None) -> None:
    if production_db is None:
        production_db = get_production_db_name()

    print(f"🧹 Cleaning up test filestores for {production_db}...")

    list_cmd = [
        "docker",
        "exec",
        f"{get_container_prefix()}-script-runner-1",
        "sh",
        "-c",
        f"ls -d /volumes/data/filestore/{production_db}_test_* 2>/dev/null || true",
    ]

    result = subprocess.run(list_cmd, capture_output=True, text=True)
    if not result.stdout.strip():
        print(f"   No test filestores found")
        return

    test_filestores = result.stdout.strip().split("\n")
    print(f"   Found {len(test_filestores)} test filestore(s)")

    for filestore in test_filestores:
        if filestore:
            check_symlink_cmd = [
                "docker",
                "exec",
                f"{get_container_prefix()}-script-runner-1",
                "sh",
                "-c",
                f"if [ -L '{filestore}' ]; then echo 'symlink'; elif [ -d '{filestore}' ]; then echo 'directory'; else echo 'unknown'; fi",
            ]
            check_result = subprocess.run(check_symlink_cmd, capture_output=True, text=True)
            is_symlink = check_result.stdout.strip() == "symlink"

            if is_symlink:
                rm_cmd = ["docker", "exec", f"{get_container_prefix()}-script-runner-1", "rm", filestore]
            else:
                rm_cmd = ["docker", "exec", f"{get_container_prefix()}-script-runner-1", "rm", "-rf", filestore]

            result = subprocess.run(rm_cmd, capture_output=True, text=True)
            if result.returncode == 0:
                filestore_name = filestore.split("/")[-1]
                type_str = "symlink" if is_symlink else "directory"
                print(f"   ✅ Removed {type_str}: {filestore_name}")
            else:
                print(f"   ⚠️  Failed to remove {filestore}: {result.stderr}")


def cleanup_all_test_artifacts() -> None:
    """Complete cleanup of all test artifacts"""
    production_db = get_production_db_name()
    print(f"🧹 Complete test cleanup for production database: {production_db}")
    print("=" * 60)

    cleanup_test_databases(production_db)
    cleanup_test_filestores(production_db)

    print("=" * 60)
    print("✅ Test cleanup completed")


def cleanup_chrome_processes() -> None:
    """Kill any lingering Chrome/Chromium processes in script runner container"""
    script_runner_service = get_script_runner_service()
    # Try to kill Chrome processes gracefully first
    subprocess.run(["docker", "exec", f"{get_container_prefix()}-{script_runner_service}-1", "pkill", "chrome"], capture_output=True)
    subprocess.run(
        ["docker", "exec", f"{get_container_prefix()}-{script_runner_service}-1", "pkill", "chromium"], capture_output=True
    )
    # Force kill if still running
    subprocess.run(
        ["docker", "exec", f"{get_container_prefix()}-{script_runner_service}-1", "pkill", "-9", "chrome"], capture_output=True
    )
    subprocess.run(
        ["docker", "exec", f"{get_container_prefix()}-{script_runner_service}-1", "pkill", "-9", "chromium"], capture_output=True
    )
    # Clean up zombie processes
    subprocess.run(
        [
            "docker",
            "exec",
            f"{get_container_prefix()}-{script_runner_service}-1",
            "sh",
            "-c",
            "ps aux | grep defunct | awk '{print $2}' | xargs -r kill -9",
        ],
        capture_output=True,
    )


def restart_script_runner_with_orphan_cleanup() -> None:
    script_runner_service = get_script_runner_service()
    subprocess.run(["docker", "compose", "stop", script_runner_service], capture_output=True)
    subprocess.run(["docker", "compose", "run", "--rm", "--remove-orphans", script_runner_service, "true"], capture_output=True)


def drop_and_create_test_database(db_name: str) -> None:
    print(f"🗄️  Cleaning up test database: {db_name}")

    # Step 1: Kill active connections to test database
    print(f"   Terminating connections to {db_name}...")

    # First, get the connection count
    check_connections_cmd = [
        "docker",
        "exec",
        f"{get_container_prefix()}-database-1",
        "psql",
        "-U",
        "odoo",
        "-d",
        "postgres",
        "-t",
        "-c",
        f"SELECT count(*) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();",
    ]
    result = subprocess.run(check_connections_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        connection_count = result.stdout.strip()
        print(f"   Found {connection_count} active connections to {db_name}")

    # Kill the connections
    kill_connections_cmd = [
        "docker",
        "exec",
        f"{get_container_prefix()}-database-1",
        "psql",
        "-U",
        "odoo",
        "-d",
        "postgres",
        "-c",
        f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();",
    ]
    result = subprocess.run(kill_connections_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"   ⚠️  Warning: Could not kill connections: {result.stderr}")
    else:
        print(f"   Connection termination command executed")

    # Wait a moment for connections to close
    import time

    time.sleep(2)

    # Check again
    result = subprocess.run(check_connections_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        remaining_count = result.stdout.strip()
        print(f"   {remaining_count} connections remaining after termination")

    # Step 2: Drop database
    print(f"   Dropping database {db_name}...")
    drop_cmd = [
        "docker",
        "exec",
        f"{get_container_prefix()}-database-1",
        "psql",
        "-U",
        "odoo",
        "-d",
        "postgres",
        "-c",
        f"DROP DATABASE IF EXISTS {db_name};",
    ]
    result = subprocess.run(drop_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"   ❌ Failed to drop database: {result.stderr}")
        return

    # Step 3: Verify drop succeeded
    verify_drop_cmd = [
        "docker",
        "exec",
        f"{get_container_prefix()}-database-1",
        "psql",
        "-U",
        "odoo",
        "-d",
        "postgres",
        "-t",
        "-c",
        f"SELECT count(*) FROM pg_database WHERE datname = '{db_name}';",
    ]
    result = subprocess.run(verify_drop_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        count = result.stdout.strip()
        if count == "0":
            print(f"   ✅ Database {db_name} successfully dropped")
        else:
            print(f"   ⚠️  Warning: Database {db_name} may still exist (count: {count})")

    # Step 4: Create fresh database
    print(f"   Creating fresh database {db_name}...")
    create_cmd = [
        "docker",
        "exec",
        f"{get_container_prefix()}-database-1",
        "psql",
        "-U",
        "odoo",
        "-d",
        "postgres",
        "-c",
        f"CREATE DATABASE {db_name};",
    ]
    result = subprocess.run(create_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"   ❌ Failed to create database: {result.stderr}")
        return

    # Step 5: Verify creation succeeded
    verify_create_cmd = [
        "docker",
        "exec",
        f"{get_container_prefix()}-database-1",
        "psql",
        "-U",
        "odoo",
        "-d",
        "postgres",
        "-t",
        "-c",
        f"SELECT count(*) FROM pg_database WHERE datname = '{db_name}';",
    ]
    result = subprocess.run(verify_create_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        count = result.stdout.strip()
        if count == "1":
            print(f"   ✅ Database {db_name} successfully created")
        else:
            print(f"   ⚠️  Warning: Database creation may have failed (count: {count})")

    print(f"🗄️  Database cleanup completed")


def setup_test_authentication(db_name: str) -> str:
    """Set up test authentication in the cloned database.

    Generates a secure random password and updates the admin user's password
    in the test database. Returns the generated password.
    """
    # Generate a secure random password
    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(16))

    print(f"   Setting up test authentication...")

    # Hash the password using Odoo's password hashing
    # We'll use a simple approach - set the password directly via SQL
    # Odoo will hash it on first authentication

    # Update the admin user's password in the database
    # Note: We're setting a plain password that Odoo will hash on first use
    # This is simpler than trying to generate the correct hash format
    update_password_cmd = [
        "docker",
        "exec",
        f"{get_container_prefix()}-database-1",
        "psql",
        "-U",
        "odoo",
        "-d",
        db_name,
        "-c",
        f"UPDATE res_users SET password = '{password}' WHERE login = 'admin';",
    ]

    result = subprocess.run(update_password_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"   ⚠️  Warning: Failed to update admin password: {result.stderr}")
        # Don't fail completely, tests might still work
    else:
        print(f"   ✅ Test authentication configured (admin user)")

    # Set environment variable for this session
    os.environ["ODOO_TEST_PASSWORD"] = password

    return password


def clone_production_database(db_name: str) -> str:
    production_db = get_production_db_name()
    print(f"🗄️  Cloning production database: {production_db} → {db_name}")

    # Step 1: Kill active connections to test database
    print(f"   Terminating connections to {db_name}...")

    # First, get the connection count
    check_connections_cmd = [
        "docker",
        "exec",
        f"{get_container_prefix()}-database-1",
        "psql",
        "-U",
        "odoo",
        "-d",
        "postgres",
        "-t",
        "-c",
        f"SELECT count(*) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();",
    ]
    result = subprocess.run(check_connections_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        connection_count = result.stdout.strip()
        print(f"   Found {connection_count} active connections to {db_name}")

    # Kill the connections
    kill_connections_cmd = [
        "docker",
        "exec",
        f"{get_container_prefix()}-database-1",
        "psql",
        "-U",
        "odoo",
        "-d",
        "postgres",
        "-c",
        f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();",
    ]
    result = subprocess.run(kill_connections_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"   ⚠️  Warning: Could not kill connections: {result.stderr}")
    else:
        print(f"   Connection termination command executed")

    # Wait a moment for connections to close
    import time

    time.sleep(2)

    # Check again
    result = subprocess.run(check_connections_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        remaining_count = result.stdout.strip()
        print(f"   {remaining_count} connections remaining after termination")

    # Step 2: Drop existing test database
    print(f"   Dropping existing database {db_name}...")
    drop_cmd = [
        "docker",
        "exec",
        f"{get_container_prefix()}-database-1",
        "psql",
        "-U",
        "odoo",
        "-d",
        "postgres",
        "-c",
        f"DROP DATABASE IF EXISTS {db_name};",
    ]
    result = subprocess.run(drop_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"   ❌ Failed to drop database: {result.stderr}")
        return ""

    # Step 3: Terminate connections to production database before cloning
    print(f"   Terminating connections to production database {production_db}...")
    kill_prod_connections_cmd = [
        "docker",
        "exec",
        f"{get_container_prefix()}-database-1",
        "psql",
        "-U",
        "odoo",
        "-d",
        "postgres",
        "-c",
        f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{production_db}' AND pid <> pg_backend_pid();",
    ]
    result = subprocess.run(kill_prod_connections_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"   ⚠️  Warning: Could not kill production connections: {result.stderr}")
    else:
        print(f"   Production connection termination executed")

    # Wait for connections to close
    time.sleep(2)

    # Step 4: Clone from production database
    print(f"   Cloning from production database {production_db}...")
    clone_cmd = [
        "docker",
        "exec",
        f"{get_container_prefix()}-database-1",
        "psql",
        "-U",
        "odoo",
        "-d",
        "postgres",
        "-c",
        f"CREATE DATABASE {db_name} WITH TEMPLATE {production_db};",
    ]
    result = subprocess.run(clone_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"   ❌ Failed to clone database: {result.stderr}")
        return ""

    # Step 4: Verify creation succeeded
    verify_create_cmd = [
        "docker",
        "exec",
        f"{get_container_prefix()}-database-1",
        "psql",
        "-U",
        "odoo",
        "-d",
        "postgres",
        "-t",
        "-c",
        f"SELECT count(*) FROM pg_database WHERE datname = '{db_name}';",
    ]
    result = subprocess.run(verify_create_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        count = result.stdout.strip()
        if count == "1":
            print(f"   ✅ Database {db_name} successfully cloned from {production_db}")
        else:
            print(f"   ⚠️  Warning: Database creation may have failed (count: {count})")

    print(f"🗄️  Database clone completed")

    # Set up test authentication for tour tests
    return setup_test_authentication(db_name)


def run_docker_test_command(
    test_tags: str,
    db_name: str,
    modules_to_install: list[str],
    timeout: int = 300,
    use_production_clone: bool = False,
    cleanup_before: bool = True,
    cleanup_after: bool = True,
    is_tour_test: bool = False,
    use_module_prefix: bool = True,
) -> int:
    if modules_to_install is None:
        modules_to_install = get_our_modules()

    modules_str = ",".join(modules_to_install)
    script_runner_service = get_script_runner_service()
    production_db = get_production_db_name()

    if is_tour_test:
        print(f"🧪 Running TOUR tests (HttpCase-based tests)")
    else:
        print(f"🧪 Running tests: {test_tags}")
    print(f"📦 Modules: {modules_str}")
    print(f"📊 Database: {db_name}")
    print("-" * 60)

    # Cleanup before tests (default behavior)
    if cleanup_before:
        print("🧹 Pre-test cleanup...")
        cleanup_test_databases(production_db)
        cleanup_test_filestores(production_db)
        print("-" * 60)

    restart_script_runner_with_orphan_cleanup()

    test_password = None
    if use_production_clone:
        test_password = clone_production_database(db_name)
        # Create symlink after container restart for tour tests
        if is_tour_test or "tour" in test_tags:
            print(f"   Creating filestore symlink for tour tests...")
            create_filestore_symlink(db_name, production_db)
            print(f"   Cleaning up Chrome processes...")
            cleanup_chrome_processes()

            # DO NOT mark modules as uninstalled for tour tests!
            # This would cause -i to reinstall them and wipe production data
            # Tours need the actual production data to navigate
            if not is_tour_test:
                # Only for unit/integration tests, mark modules for reinstall
                print(f"   Marking modules as uninstalled to force test discovery...")
                for module in modules_to_install:
                    cmd_uninstall = [
                        "docker",
                        "compose",
                        "exec",
                        "-T",
                        "database",
                        "psql",
                        "-U",
                        "odoo",
                        "-d",
                        db_name,
                        "-c",
                        f"UPDATE ir_module_module SET state = 'uninstalled' WHERE name = '{module}';",
                    ]
                    subprocess.run(cmd_uninstall, capture_output=True)
                print(f"   ✅ Modules marked for reinstallation")
            else:
                print(f"   ✅ Keeping modules installed to preserve production data for tours")
    else:
        drop_and_create_test_database(db_name)

    # Build test tags - optionally scope tags to specific modules using proper Odoo syntax
    # Syntax: [-][tag][/module][:class][.method]
    # For example, restricting tag 'unit_test' to module 'user_name_extended' -> 'unit_test/user_name_extended'
    if not test_tags:
        # No tags specified, just limit by modules
        # Use '/module' form so only those modules' tests run
        test_tags_final = ",".join([f"/{module}" for module in modules_to_install])
    elif not use_module_prefix:
        # Use tags as-is without scoping to module(s)
        test_tags_final = test_tags
    else:
        # Scope provided tag expression to modules.
        # We only support the common case where the expression is a single positive tag
        # or a simple comma-separated list where the last item is the primary tag to scope.
        parts = [p.strip() for p in test_tags.split(",") if p.strip()]
        if len(parts) == 1 and not parts[0].startswith("-"):
            tag = parts[0]
            test_tags_final = ",".join([f"{tag}/{module}" for module in modules_to_install])
        else:
            # Fallback: attach module scoping to the last positive tag
            primary = next((p for p in reversed(parts) if not p.startswith("-")), parts[-1])
            scoped = [f"{primary}/{module}" for module in modules_to_install]
            # Keep the other parts (excluding the primary we scoped) and add scoped specs
            keep = [p for p in parts if p != primary]
            test_tags_final = ",".join(keep + scoped)

    print(f"🏷️  Final test tags: {test_tags_final}")

    # Use different module flags based on test type
    if is_tour_test:
        # For tour tests, don't reinstall modules to avoid database locks
        # Modules are already installed in the cloned production database
        module_flag = "-u"  # Update instead of install
    else:
        # For unit/integration tests, use install to ensure clean test loading
        module_flag = "-i"

    cmd = [
        "docker",
        "compose",
        "run",
        "--rm",
    ]

    # Add environment variable for test password if we have one
    if test_password:
        cmd.extend(["-e", f"ODOO_TEST_PASSWORD={test_password}"])

    # Tour tests need workers for websocket support, others can use single-threaded mode
    if is_tour_test:
        cmd.extend(
            [
                script_runner_service,
                "/odoo/odoo-bin",
                "-d",
                db_name,
                module_flag,
                modules_str,
                "--test-tags",
                test_tags_final,
                "--test-enable",
                "--stop-after-init",
                "--max-cron-threads=0",
                "--workers=0",  # Use single worker until multi-worker issue is resolved
                f"--db-filter=^{db_name}$",
                "--log-level=test",
                "--without-demo=all",
            ]
        )
    else:
        cmd.extend(
            [
                script_runner_service,
                "/odoo/odoo-bin",
                "-d",
                db_name,
                module_flag,
                modules_str,
                "--test-tags",
                test_tags_final,
                "--test-enable",
                "--stop-after-init",
                "--max-cron-threads=0",
                "--workers=0",  # Single-threaded for unit/integration tests
                f"--db-filter=^{db_name}$",
                "--log-level=test",
                "--without-demo=all",
            ]
        )

    # Create log directory for this test run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = Path("tmp/test-logs") / f"test-{timestamp}"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "output.log"
    summary_file = log_dir / "summary.json"

    print(f"🚀 Command: {' '.join(cmd)}")
    print(f"📁 Logs: {log_dir}")
    print()

    start_time = time.time()

    # Prepare summary data
    summary = {
        "timestamp": timestamp,
        "command": cmd,
        "test_type": "tour" if is_tour_test else "unit/integration",
        "database": db_name,
        "modules": modules_to_install,
        "test_tags": test_tags_final,
        "timeout": timeout,
        "start_time": start_time,
    }

    try:
        # Run command with output going to both console and log file
        with open(log_file, "w") as f:
            # Write command info to log
            f.write(f"Command: {' '.join(cmd)}\n")
            f.write(f"Started: {datetime.now()}\n")
            f.write("=" * 80 + "\n\n")
            f.flush()

            # Use Popen to stream output to both console and file
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

            # Track timing for timeout and stall detection
            last_output_time = time.time()
            stall_warnings = 0
            max_stall_warnings = 10
            stall_threshold = 60  # seconds

            # Enhanced stall detection - track repetitive patterns
            recent_lines = []  # Store last 20 lines for pattern detection
            pattern_occurrences = {}  # Count occurrences of similar lines
            last_pattern_check = time.time()
            pattern_check_interval = 60  # Check for patterns every 1 minute

            # Simple progress tracking
            test_count = 0
            current_test = ""
            last_test = ""

            # Adaptive thresholds based on test type (derive from test_tags)
            test_type_lower = test_tags.lower()
            if "tour" in test_type_lower or is_tour_test:
                stall_threshold = 120  # Tours can take longer
                max_stall_warnings = 15
            elif "integration" in test_type_lower:
                stall_threshold = 90
                max_stall_warnings = 12

            result_code = 0

            # Stream output with timeout and stall detection
            while True:
                current_time = time.time()

                # Check for overall timeout
                if current_time - start_time > timeout:
                    print(f"\n⏱️ TIMEOUT: Test execution exceeded {timeout} seconds")
                    f.write(f"\n⏱️ TIMEOUT: Test execution exceeded {timeout} seconds\n")
                    safe_terminate_process(process)
                    result_code = -1
                    break

                # Use select to check if data is available (non-blocking)
                try:
                    ready, _, _ = select.select([process.stdout], [], [], 3.0)

                    if ready:
                        line = process.stdout.readline()
                        if not line:  # EOF - process ended
                            break
                        print(line, end="")  # To console
                        f.write(line)  # To file
                        f.flush()
                        last_output_time = current_time
                        stall_warnings = 0  # Reset on new output

                        # Add line to pattern detection buffer
                        recent_lines.append(line.strip())
                        if len(recent_lines) > 20:  # Keep only last 20 lines
                            recent_lines.pop(0)

                        # Check for repetitive patterns periodically
                        if current_time - last_pattern_check > pattern_check_interval:
                            is_repetitive, pattern_desc = detect_repetitive_pattern(recent_lines, pattern_occurrences)
                            if is_repetitive:
                                print(f"\n🔄 REPETITIVE PATTERN DETECTED: {pattern_desc}")
                                print(f"❌ STALLED: Process stuck in repetitive output. Terminating...")
                                f.write(f"\n🔄 REPETITIVE PATTERN DETECTED: {pattern_desc}\n")
                                f.write(f"❌ STALLED: Process stuck in repetitive output. Terminating...\n")
                                safe_terminate_process(process)
                                result_code = -3  # New code for pattern-based stall
                                break
                            last_pattern_check = current_time

                        # Enhanced test completion detection
                        test_completion_indicators = [
                            "Test completed successfully",
                            "tests started in",
                            "post-tests in",
                            "failed, 0 error(s) of",
                            "Initiating shutdown",
                        ]

                        if any(indicator in line for indicator in test_completion_indicators):
                            # Test framework signaled completion - start cleanup timer
                            if not hasattr(locals(), "cleanup_start_time"):
                                cleanup_start_time = current_time
                                print(f"\n🧹 Test completion detected. Starting cleanup timer...")
                                f.write(f"\n🧹 Test completion detected. Starting cleanup timer...\n")

                                # For tour tests, immediately kill browsers to prevent websocket hang
                                if is_tour_test:
                                    print(f"🔫 Preemptively killing browser processes...")
                                    f.write(f"🔫 Preemptively killing browser processes...\n")
                                    kill_browser_processes()

                        # Check cleanup timeout (much shorter than overall timeout)
                        if hasattr(locals(), "cleanup_start_time"):
                            cleanup_elapsed = current_time - cleanup_start_time
                            if cleanup_elapsed > 30:  # 30 seconds max for cleanup
                                print(f"\n❌ CLEANUP HUNG: Process stuck in cleanup for {cleanup_elapsed:.1f}s. Terminating...")
                                f.write(f"\n❌ CLEANUP HUNG: Process stuck in cleanup for {cleanup_elapsed:.1f}s. Terminating...\n")
                                safe_terminate_process(process)
                                result_code = -4  # New code for cleanup hang
                                break

                        # Simple test progress tracking
                        if "test_" in line and ("(" in line or ":" in line):
                            # Looks like a test name
                            parts = line.split()
                            for part in parts:
                                if part.startswith("test_") and part != last_test:
                                    test_count += 1
                                    last_test = part
                                    current_test = part.strip("():")
                                    if test_count % 10 == 0:
                                        print(f"\nℹ️  Progress: {test_count} tests started...\n")
                                        f.write(f"\nℹ️  Progress: {test_count} tests started...\n")
                                    break
                    else:
                        # No output available - check for stall
                        if current_time - last_output_time > stall_threshold:
                            stall_warnings += 1
                            test_info = f" (last test: {current_test})" if current_test else ""
                            print(
                                f"\n⚠️  WARNING: No output for {current_time - last_output_time:.1f}s [{stall_warnings}/{max_stall_warnings}]{test_info}"
                            )
                            f.write(
                                f"\n⚠️  WARNING: No output for {current_time - last_output_time:.1f}s [{stall_warnings}/{max_stall_warnings}]{test_info}\n"
                            )

                            if stall_warnings >= max_stall_warnings:
                                print(f"\n❌ STALLED: Process appears stuck. Terminating...")
                                f.write(f"\n❌ STALLED: Process appears stuck. Terminating...\n")
                                safe_terminate_process(process)
                                result_code = -2
                                break

                    # Check if process ended
                    poll_result = process.poll()
                    if poll_result is not None:
                        result_code = poll_result
                        break

                except Exception as e:
                    print(f"\n⚠️  Error reading output: {e}")
                    f.write(f"\n⚠️  Error reading output: {e}\n")
                    time.sleep(0.1)
                    continue

            # Get any remaining output
            try:
                for _ in range(100):  # Limit iterations
                    line = process.stdout.readline()
                    if not line:
                        break
                    print(line, end="")
                    f.write(line)
                    f.flush()
            except:
                pass

            # Ensure process is terminated
            if process.poll() is None:
                try:
                    result_code = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print("\n⚠️  Process didn't exit cleanly, forcing termination")
                    f.write("\n⚠️  Process didn't exit cleanly, forcing termination\n")
                    safe_terminate_process(process)
                    result_code = -1

        elapsed = time.time() - start_time

        print(f"\n⏱️  Completed in {elapsed:.2f}s")

        # Update summary
        summary.update(
            {
                "end_time": time.time(),
                "elapsed_seconds": elapsed,
                "returncode": result_code,
                "success": result_code == 0,
                "timeout": result_code == -1,
                "stalled": result_code == -2,
                "repetitive_pattern": result_code == -3,
                "cleanup_hang": result_code == -4,
                "tests_started": test_count,
                "last_test": current_test if current_test else None,
                "error": None,
            }
        )

        # Cleanup after tests (default behavior)
        if cleanup_after:
            print("-" * 60)
            print("🧹 Post-test cleanup...")
            cleanup_test_databases(production_db)
            cleanup_test_filestores(production_db)

        if result_code == 0:
            print("✅ Tests passed!")
            print(f"📄 Logs saved to: {log_file}")
        else:
            print("❌ Tests failed!")
            print(f"📄 Check logs at: {log_file}")

        # Save summary for AI agents to parse
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2, default=str)

        return result_code

    except subprocess.TimeoutExpired:
        # This should rarely happen now as we handle timeout inline
        elapsed = time.time() - start_time
        print(f"\n❌ Tests timed out after {timeout} seconds")

        # Update summary for timeout
        summary.update(
            {
                "end_time": time.time(),
                "elapsed_seconds": elapsed,
                "returncode": -1,
                "success": False,
                "timeout": True,
                "stalled": False,
                "error": f"Timeout after {timeout} seconds",
            }
        )

        # Save summary even on timeout
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2, default=str)

        print(f"📄 Partial logs saved to: {log_file}")

        # Cleanup on timeout if enabled
        if cleanup_after:
            print("🧹 Cleanup after timeout...")
            cleanup_test_databases(production_db)
            cleanup_test_filestores(production_db)
        return 1

    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
        # Cleanup on interrupt if enabled
        if cleanup_after:
            print("🧹 Cleanup after interrupt...")
            cleanup_test_databases(production_db)
            cleanup_test_filestores(production_db)
        return 1

    except Exception as e:
        print(f"\n💥 Error running tests: {e}")
        # Cleanup on error if enabled
        if cleanup_after:
            print("🧹 Cleanup after error...")
            cleanup_test_databases(production_db)
            cleanup_test_filestores(production_db)
        return 1


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "unit":
            # Allow optional module list after "unit" to restrict scope
            modules = sys.argv[2:] if len(sys.argv) > 2 else None
            sys.exit(run_unit_tests(modules))
        elif command == "integration":
            sys.exit(run_integration_tests())
        elif command == "tour":
            sys.exit(run_tour_tests())
        elif command == "all":
            sys.exit(run_all_tests())
        elif command == "stats":
            sys.exit(show_test_stats())
        elif command == "clean" or command == "cleanup":
            cleanup_all_test_artifacts()
            sys.exit(0)
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
    else:
        print("Usage: python test_commands.py [unit|integration|tour|all|quick|stats|clean]")
        sys.exit(1)
