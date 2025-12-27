# Auto-discovery mechanism for Odoo tests in subdirectories
# This solves Odoo's limitation of only discovering test modules at the top level
import importlib
import pkgutil
import sys
import logging

_logger = logging.getLogger(__name__)


def _expose_subdir_tests():
    """
    Recursively discovers all test modules in subdirectories and exposes them
    as attributes on the tests package so Odoo's test loader can find them.

    Odoo's test discovery only looks for modules starting with 'test_' directly
    in the tests package, not in subdirectories. This function walks all
    subdirectories, imports test modules, and sets them as attributes on this
    package with names starting with 'test_'.
    """
    pkg = sys.modules[__name__]
    prefix = __name__ + "."
    exported = set()

    # Walk all subpackages/modules under tests/
    for _, fullname, is_package in pkgutil.walk_packages(__path__, prefix):
        # Get the last component of the module name (e.g., 'test_minimal')
        base = fullname.rsplit(".", 1)[-1]

        # Only process modules whose names start with 'test_'
        if base.startswith("test_"):
            try:
                # Import the real module (e.g., odoo.addons.product_connect.tests.unit.test_foo)
                mod = importlib.import_module(fullname)

                # Create an alias for the module
                # If there are duplicates, disambiguate them
                alias = base
                if alias in exported:
                    # Create unique name like test_foo__unit, test_foo__integration
                    path_parts = fullname[len(prefix) :].split(".")
                    if len(path_parts) > 1:
                        # Include the subdirectory in the alias
                        alias = f"{base}__{path_parts[0]}"
                    else:
                        # Fallback to full path replacement
                        alias = fullname[len(prefix) :].replace(".", "__")

                # Re-expose the module on the tests package
                setattr(pkg, alias, mod)
                exported.add(alias)
                _logger.debug(f"Exposed test module: {fullname} as {alias}")

            except ImportError as e:
                _logger.warning(f"Failed to import test module {fullname}: {e}")
                continue

    _logger.info(f"Auto-discovered and exposed {len(exported)} test modules from subdirectories")
    return exported


# Run the auto-discovery when the tests package is imported
_exposed_modules = _expose_subdir_tests()

# Manually import JS unit tests (renamed to avoid tour contamination)
try:
    from .js import js_unit_tests

    # Expose it as test_js_units for Odoo's test discovery
    sys.modules[__name__].test_js_units = js_unit_tests
    _logger.info("Manually imported JS unit tests module")
except ImportError as e:
    _logger.warning(f"Failed to import JS unit tests: {e}")
