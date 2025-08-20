#!/usr/bin/env python3

import os
import secrets
import string
import subprocess
import sys
import time
from pathlib import Path


def get_production_db_name() -> str:
    result = subprocess.run(["docker", "compose", "config", "--format", "json"], capture_output=True, text=True)
    if result.returncode == 0:
        import json

        config = json.loads(result.stdout)
        for service_name, service in config.get("services", {}).items():
            if "web" in service_name.lower():
                env = service.get("environment", {})
                if isinstance(env, dict):
                    return env.get("ODOO_DB", "opw")
                elif isinstance(env, list):
                    for env_var in env:
                        if env_var.startswith("ODOO_DB="):
                            return env_var.split("=", 1)[1]
    return "opw"


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
            if module_dir.is_dir() and (module_dir / "__manifest__.py").exists():
                modules.append(module_dir.name)
    return modules


def run_unit_tests() -> int:
    modules = get_our_modules()
    test_db_name = f"{get_production_db_name()}_test_unit"
    test_tags = ",".join([f"/{module}" for module in modules])
    return run_docker_test_command(test_tags, test_db_name, modules, use_production_clone=False, use_module_prefix=False)


def run_integration_tests() -> int:
    modules = get_our_modules()
    test_db_name = f"{get_production_db_name()}_test_integration"
    test_tags = ",".join([f"/{module}" for module in modules])
    return run_docker_test_command(test_tags, test_db_name, modules, timeout=600, use_production_clone=True, use_module_prefix=False)


def run_tour_tests() -> int:
    print("🧪 Starting tour tests...")
    modules = get_our_modules()
    test_db_name = f"{get_production_db_name()}_test_tour"
    print(f"   Database: {test_db_name}")
    print(f"   Modules: {', '.join(modules)}")
    test_tags = ",".join([f"/{module}" for module in modules])
    return run_docker_test_command(
        test_tags, test_db_name, modules, timeout=1800, use_production_clone=True, is_tour_test=True, use_module_prefix=False
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
    rc |= (rc_unit != 0)

    # 2) Integration tests on cloned DB
    print("\n▶️  Phase 2: Integration tests")
    rc_integration = run_integration_tests() if rc_unit == 0 else rc_unit
    rc |= (rc_integration != 0)

    # 3) Tour tests (browser) on cloned DB
    print("\n▶️  Phase 3: Tour tests")
    rc_tour = run_tour_tests() if rc_integration == 0 else rc_integration
    rc |= (rc_tour != 0)

    if rc == 0:
        print("\n✅ All categories passed")
        return 0
    else:
        print("\n❌ Some categories failed")
        # Return first non-zero code for conventional CI semantics
        return rc_unit or rc_integration or rc_tour or 1


def run_quick_tests() -> int:
    modules = get_our_modules()
    test_db_name = f"{get_production_db_name()}_test_unit"
    return run_docker_test_command("unit_test", test_db_name, modules, use_production_clone=False)


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
        "odoo-opw-database-1",
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
            "odoo-opw-database-1",
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
        drop_cmd = ["docker", "exec", "odoo-opw-database-1", "dropdb", "-U", "odoo", "--if-exists", db]
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
    list_cmd = ["docker", "ps", "-q", "-f", f"name=odoo-opw-{script_runner_service}", "-f", "status=running"]
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
        "odoo-opw-script-runner-1",
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
                "odoo-opw-script-runner-1",
                "sh",
                "-c",
                f"if [ -L '{filestore}' ]; then echo 'symlink'; elif [ -d '{filestore}' ]; then echo 'directory'; else echo 'unknown'; fi",
            ]
            check_result = subprocess.run(check_symlink_cmd, capture_output=True, text=True)
            is_symlink = check_result.stdout.strip() == "symlink"

            if is_symlink:
                rm_cmd = ["docker", "exec", "odoo-opw-script-runner-1", "rm", filestore]
            else:
                rm_cmd = ["docker", "exec", "odoo-opw-script-runner-1", "rm", "-rf", filestore]

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
    subprocess.run(["docker", "exec", f"odoo-opw-{script_runner_service}-1", "pkill", "chrome"], capture_output=True)
    subprocess.run(["docker", "exec", f"odoo-opw-{script_runner_service}-1", "pkill", "chromium"], capture_output=True)
    # Force kill if still running
    subprocess.run(["docker", "exec", f"odoo-opw-{script_runner_service}-1", "pkill", "-9", "chrome"], capture_output=True)
    subprocess.run(["docker", "exec", f"odoo-opw-{script_runner_service}-1", "pkill", "-9", "chromium"], capture_output=True)
    # Clean up zombie processes
    subprocess.run(
        [
            "docker",
            "exec",
            f"odoo-opw-{script_runner_service}-1",
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
        "odoo-opw-database-1",
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
        "odoo-opw-database-1",
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
        "odoo-opw-database-1",
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
        "odoo-opw-database-1",
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
        "odoo-opw-database-1",
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
        "odoo-opw-database-1",
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
        "odoo-opw-database-1",
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
        "odoo-opw-database-1",
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
        "odoo-opw-database-1",
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
        "odoo-opw-database-1",
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

    # Step 3: Terminate connections to production database before cloning
    print(f"   Terminating connections to production database {production_db}...")
    kill_prod_connections_cmd = [
        "docker",
        "exec",
        "odoo-opw-database-1",
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
        "odoo-opw-database-1",
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
        return

    # Step 4: Verify creation succeeded
    verify_create_cmd = [
        "docker",
        "exec",
        "odoo-opw-database-1",
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

            # Mark modules as uninstalled to force test module loading
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
        drop_and_create_test_database(db_name)

    # Build test tags - optionally with module prefix to only run our module tests
    # Format: module_name:test_tag for each module (when use_module_prefix=True)
    if not test_tags:
        # No tags specified, just use module names
        test_tags_final = ",".join(modules_to_install)
    elif not use_module_prefix:
        # Use tags as-is without module prefix (for tour tests)
        test_tags_final = test_tags
    elif "," in test_tags:
        # Complex tags with multiple components - apply module prefix to last tag
        # e.g., "post_install,-at_install,unit_test" -> "module:unit_test"
        tags = test_tags.split(",")
        last_tag = tags[-1].strip()
        test_tags_final = ",".join([f"{module}:{last_tag}" for module in modules_to_install])
    elif test_tags.startswith("-"):
        # Negative tags - use as-is
        test_tags_final = test_tags
    else:
        # Simple tags - use module prefixes
        test_tags_final = ",".join([f"{module}:{test_tags}" for module in modules_to_install])

    print(f"🏷️  Final test tags: {test_tags_final}")

    # For tests, always use -i (install) to force test module loading
    # Even with production clones, we need -i to trigger test discovery
    # Odoo doesn't load test modules during update (-u), only during install
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
            "--workers=0",
            f"--db-filter=^{db_name}$",
            "--log-level=test",
            "--without-demo=all",
        ]
    )

    print(f"🚀 Command: {' '.join(cmd)}")
    print()

    start_time = time.time()

    try:
        # Don't capture output, let it stream to console
        result = subprocess.run(cmd, timeout=timeout, text=True)
        elapsed = time.time() - start_time

        print(f"\n⏱️  Completed in {elapsed:.2f}s")

        # Cleanup after tests (default behavior)
        if cleanup_after:
            print("-" * 60)
            print("🧹 Post-test cleanup...")
            cleanup_test_databases(production_db)
            cleanup_test_filestores(production_db)

        if result.returncode == 0:
            print("✅ Tests passed!")
        else:
            print("❌ Tests failed!")

        return result.returncode

    except subprocess.TimeoutExpired:
        print(f"\n❌ Tests timed out after {timeout} seconds")
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
            sys.exit(run_unit_tests())
        elif command == "integration":
            sys.exit(run_integration_tests())
        elif command == "tour":
            sys.exit(run_tour_tests())
        elif command == "all":
            sys.exit(run_all_tests())
        elif command == "quick":
            sys.exit(run_quick_tests())
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
