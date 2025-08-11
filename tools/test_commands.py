#!/usr/bin/env python3

import subprocess
import sys
import time
from pathlib import Path

def get_production_db_name():
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        capture_output=True, text=True
    )
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

def get_script_runner_service():
    result = subprocess.run(
        ["docker", "compose", "ps", "--services"],
        capture_output=True, text=True
    )
    services = result.stdout.strip().split('\n') if result.returncode == 0 else []
    for service in services:
        if "script" in service.lower() and "runner" in service.lower():
            return service
    return "script-runner"

def get_our_modules():
    modules = []
    addons_path = Path("addons")
    if addons_path.exists():
        for module_dir in addons_path.iterdir():
            if module_dir.is_dir() and (module_dir / "__manifest__.py").exists():
                modules.append(module_dir.name)
    return modules

def run_unit_tests():
    modules = get_our_modules()
    test_db_name = f"{get_production_db_name()}_test"
    return run_docker_test_command("unit_test", test_db_name, modules)

def run_integration_tests():
    modules = get_our_modules()
    test_db_name = f"{get_production_db_name()}_test"
    return run_docker_test_command("integration_test", test_db_name, modules)

def run_tour_tests():
    modules = get_our_modules()
    test_db_name = f"{get_production_db_name()}_test"
    return run_docker_test_command("tour_test", test_db_name, modules)

def run_all_tests():
    modules = get_our_modules()
    test_db_name = f"{get_production_db_name()}_test"
    return run_docker_test_command("post_install,-at_install", test_db_name, modules)

def run_quick_tests():
    modules = get_our_modules()
    test_db_name = f"{get_production_db_name()}_test"
    return run_docker_test_command("unit_test", test_db_name, modules)

def show_test_stats():
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
                with open(test_file, "r") as f:
                    content = f.read()
                    for category in categories:
                        if f'"{category}"' in content or f"'{category}'" in content:
                            categories[category] += 1
        
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
    
    return 0

def restart_script_runner_with_orphan_cleanup():
    script_runner_service = get_script_runner_service()
    subprocess.run(["docker", "compose", "stop", script_runner_service], capture_output=True)
    subprocess.run(["docker", "compose", "run", "--rm", "--remove-orphans", script_runner_service, "true"], capture_output=True)

def drop_and_create_test_database(db_name):
    script_runner_service = get_script_runner_service()
    
    drop_cmd = [
        "docker", "compose", "run", "--rm", script_runner_service,
        "/odoo/odoo-bin", "--stop-after-init", "--log-level=error",
        "-d", db_name, "--uninstall", "all"
    ]
    subprocess.run(drop_cmd, capture_output=True)

def run_docker_test_command(test_tags, db_name, modules_to_install, timeout=300):
    if modules_to_install is None:
        modules_to_install = get_our_modules()
    
    modules_str = ",".join(modules_to_install)
    script_runner_service = get_script_runner_service()
    
    print(f"🧪 Running tests: {test_tags}")
    print(f"📦 Modules: {modules_str}")
    print(f"📊 Database: {db_name}")
    print("-" * 60)
    
    restart_script_runner_with_orphan_cleanup()
    drop_and_create_test_database(db_name)
    
    cmd = [
        "docker", "compose", "run", "--rm", script_runner_service,
        "/odoo/odoo-bin",
        "-d", db_name,
        "-i", modules_str,
        "--test-tags", test_tags,
        "--test-enable",
        "--stop-after-init",
        "--max-cron-threads=0",
        "--workers=0",
        f"--db-filter=^{db_name}$",
        "--log-level=test",
        "--without-demo=all",
    ]
    
    print(f"🚀 Command: {' '.join(cmd)}")
    print()
    
    start_time = time.time()
    
    try:
        result = subprocess.run(cmd, timeout=timeout)
        elapsed = time.time() - start_time
        
        print(f"\n⏱️  Completed in {elapsed:.2f}s")
        
        drop_and_create_test_database(db_name)
        
        if result.returncode == 0:
            print("✅ Tests passed!")
        else:
            print("❌ Tests failed!")
        
        return result.returncode
        
    except subprocess.TimeoutExpired:
        print(f"\n❌ Tests timed out after {timeout} seconds")
        drop_and_create_test_database(db_name)
        return 1
    
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
        drop_and_create_test_database(db_name)
        return 1
    
    except Exception as e:
        print(f"\n💥 Error running tests: {e}")
        drop_and_create_test_database(db_name)
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
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
    else:
        print("Usage: python test_commands.py [unit|integration|tour|all|quick|stats]")
        sys.exit(1)