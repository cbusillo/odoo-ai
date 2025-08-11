#!/usr/bin/env python3
"""
Simple test execution commands that work directly with Docker Compose.
These are UV run scripts that map to straightforward Docker commands.
"""

import subprocess
import sys
import time
from typing import List

def run_unit_tests() -> int:
    """Run unit tests using script-runner container."""
    return _run_docker_test_command(
        test_tags="/product_connect:unit_test",
        db_name="test_unit_db"
    )

def run_integration_tests() -> int:
    """Run integration tests using script-runner container."""
    return _run_docker_test_command(
        test_tags="/product_connect:integration_test",
        db_name="test_integration_db"
    )

def run_tour_tests() -> int:
    """Run tour tests using script-runner container."""
    return _run_docker_test_command(
        test_tags="/product_connect:tour_test",
        db_name="test_tour_db"
    )

def run_all_tests() -> int:
    """Run all post-install tests using script-runner container."""
    return _run_docker_test_command(
        test_tags="/product_connect:post_install,-at_install",
        db_name="test_all_db"
    )

def run_quick_tests() -> int:
    """Run a subset of fast unit tests."""
    return _run_docker_test_command(
        test_tags="/product_connect:unit_test,test_basic,test_simple_unit,test_infrastructure_check",
        db_name="test_quick_db"
    )

def show_test_stats() -> int:
    """Show test count statistics by category."""
    print("Test Statistics for product_connect module:")
    print("=" * 50)
    
    # Count tests by searching for @tagged decorators
    from pathlib import Path
    
    test_root = Path("addons/product_connect/tests")
    if not test_root.exists():
        print("❌ Test directory not found")
        return 1
    
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
    
    print(f"Total test files: {total_files}")
    for category, count in categories.items():
        print(f"{category:20}: {count:3} files")
    
    print("\nTo run tests:")
    print("  uv run test-unit        # Fast unit tests")
    print("  uv run test-integration # Integration tests")
    print("  uv run test-tour        # Browser tours")
    print("  uv run test-all         # All tests")
    print("  uv run test-quick       # Subset of unit tests")
    
    return 0

def _run_docker_test_command(test_tags: str, db_name: str, timeout: int = 300) -> int:
    """Execute a docker compose test command with proper cleanup."""
    
    print(f"🧪 Running tests: {test_tags}")
    print(f"📊 Database: {db_name}")
    print("-" * 60)
    
    # Build the Docker command using script-runner
    cmd = [
        "docker", "compose", "run", "--rm", "script-runner",
        "/odoo/odoo-bin",
        "-d", db_name,
        "-i", "product_connect",
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
        # Run the command
        result = subprocess.run(cmd, timeout=timeout)
        elapsed = time.time() - start_time
        
        print(f"\n⏱️  Completed in {elapsed:.2f}s")
        
        # Clean up database
        _cleanup_database(db_name)
        
        if result.returncode == 0:
            print("✅ Tests passed!")
        else:
            print("❌ Tests failed!")
        
        return result.returncode
        
    except subprocess.TimeoutExpired:
        print(f"\n❌ Tests timed out after {timeout} seconds")
        _cleanup_database(db_name)
        return 1
    
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
        _cleanup_database(db_name)
        return 1
    
    except Exception as e:
        print(f"\n💥 Error running tests: {e}")
        _cleanup_database(db_name)
        return 1

def _cleanup_database(db_name: str) -> None:
    """Clean up test database."""
    print(f"🧹 Cleaning up database: {db_name}")
    
    cleanup_cmd = [
        "docker", "compose", "run", "--rm", "script-runner",
        "/odoo/odoo-bin", "--stop-after-init",
        "-d", db_name, "--uninstall", "all"
    ]
    
    try:
        subprocess.run(cleanup_cmd, capture_output=True, timeout=30)
    except Exception as e:
        print(f"Warning: Could not clean up database: {e}")

if __name__ == "__main__":
    # Allow running this script directly for testing
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