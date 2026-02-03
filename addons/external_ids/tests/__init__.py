"""External ID tests."""

# Auto-discovery mechanism for Odoo tests in subdirectories.
# This solves Odoo's limitation of only discovering test modules at the top level.
import importlib
import logging
import pkgutil
import sys

_logger = logging.getLogger(__name__)


def _expose_subdirectory_tests() -> set[str]:
    """
    Recursively discover test modules in subdirectories and expose them on the
    tests package so Odoo's test loader can find them.

    Odoo's test discovery only looks for modules starting with 'test_' directly
    in the tests package, not in subdirectories. This function walks all
    subdirectories, imports test modules, and sets them as attributes on this
    package with names starting with 'test_'.
    """
    package = sys.modules[__name__]
    package_prefix = __name__ + "."
    exported = set()

    for module_finder, full_name, is_package in pkgutil.walk_packages(__path__, package_prefix):
        module_base = full_name.rsplit(".", 1)[-1]
        if not module_base.startswith("test_"):
            continue
        try:
            module = importlib.import_module(full_name)
        except ImportError as import_error:
            _logger.warning(f"Failed to import test module {full_name}: {import_error}")
            continue

        alias = module_base
        if alias in exported:
            path_parts = full_name[len(package_prefix) :].split(".")
            if len(path_parts) > 1:
                alias = f"{module_base}__{path_parts[0]}"
            else:
                alias = full_name[len(package_prefix) :].replace(".", "__")

        setattr(package, alias, module)
        exported.add(alias)
        _logger.debug(f"Exposed test module: {full_name} as {alias}")

    _logger.info(f"Auto-discovered and exposed {len(exported)} test modules from subdirectories")
    return exported


_exposed_modules = _expose_subdirectory_tests()
