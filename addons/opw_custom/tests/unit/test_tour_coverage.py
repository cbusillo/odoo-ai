import re
from pathlib import Path
from ..common_imports import tagged, UNIT_TAGS
from ..fixtures.base import UnitTestCase


@tagged(*UNIT_TAGS)
class TestTourCoverage(UnitTestCase):
    def test_all_tours_have_runners(self) -> None:
        addon_path = Path(__file__).parent.parent
        tours_path = addon_path / "static" / "tests" / "tours"

        if not tours_path.exists():
            self.skipTest("No tours directory found")

        tour_files = {}
        for tour_file in tours_path.glob("*.js"):
            if tour_file.name == "basic_tour.js":
                continue

            with open(tour_file) as f:
                content = f.read()
                match = re.search(r'registry\.category\("web_tour\.tours"\)\.add\("([^"]+)"', content)
                if match:
                    tour_name = match.group(1)
                    tour_files[tour_name] = tour_file.name

        test_runners = set()

        tests_dir = Path(__file__).parent
        for test_file in tests_dir.glob("test_*.py"):
            if test_file.name == "test_tour_coverage.py":
                continue

            with open(test_file) as f:
                content = f.read()
                tour_matches = re.findall(r'self\.start_tour\([^,]+,\s*["\']([^"\']+)["\']', content)
                test_runners.update(tour_matches)

        tours_test_dir = tests_dir / "tours"
        if tours_test_dir.exists():
            for test_file in tours_test_dir.glob("test_*.py"):
                with open(test_file) as f:
                    content = f.read()
                    tour_matches = re.findall(r'self\.start_tour\([^,]+,\s*["\']([^"\']+)["\']', content)
                    test_runners.update(tour_matches)

        missing_runners = []
        for tour_name, tour_file in tour_files.items():
            if tour_name not in test_runners:
                missing_runners.append((tour_name, tour_file))

        if missing_runners:
            message = "The following tours do not have test runners:\n"
            for tour_name, tour_file in missing_runners:
                message += f"  - {tour_file}: tour '{tour_name}' has no test runner\n"
            message += "\nCreate a test class with:\n"
            message += "  self.start_tour('/web', 'tour_name', login=self.test_user.login)\n"
            self.fail(message)

        orphaned_runners = []
        for runner_tour in test_runners:
            if runner_tour not in tour_files:
                orphaned_runners.append(runner_tour)

        if orphaned_runners:
            print(f"WARNING: The following test runners have no corresponding tour files: {orphaned_runners}")

        print(f"✓ Tour coverage check passed: {len(tour_files)} tours, {len(test_runners)} runners")
