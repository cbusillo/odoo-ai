import importlib
import logging
import pkgutil
import sys
from collections.abc import Iterable


def expose_subdirectory_tests(package_name: str, package_path: Iterable[str]) -> set[str]:
    """Expose nested ``test_*`` modules at package level for Odoo discovery."""
    package_logger = logging.getLogger(package_name)
    package_module = sys.modules[package_name]
    package_prefix = f"{package_name}."
    exported_aliases: set[str] = set()

    for _, module_full_name, _ in pkgutil.walk_packages(package_path, package_prefix):
        module_base_name = module_full_name.rsplit(".", 1)[-1]
        if not module_base_name.startswith("test_"):
            continue

        try:
            imported_module = importlib.import_module(module_full_name)
        except ImportError as import_error:
            package_logger.warning("Failed to import test module %s: %s", module_full_name, import_error)
            continue

        alias_name = module_base_name
        if alias_name in exported_aliases:
            relative_module_path = module_full_name[len(package_prefix) :]
            relative_parts = relative_module_path.split(".")
            if len(relative_parts) > 1:
                alias_name = f"{module_base_name}__{relative_parts[0]}"
            else:
                alias_name = relative_module_path.replace(".", "__")

        setattr(package_module, alias_name, imported_module)
        exported_aliases.add(alias_name)
        package_logger.debug("Exposed test module %s as %s", module_full_name, alias_name)

    package_logger.info(
        "Auto-discovered and exposed %s test modules from subdirectories",
        len(exported_aliases),
    )
    return exported_aliases


def expose_module_alias(
    package_name: str,
    module_suffix: str,
    alias_name: str,
    *,
    warn_on_missing: bool = True,
) -> bool:
    """Expose ``<package>.<module_suffix>`` as ``alias_name`` on package module."""
    package_logger = logging.getLogger(package_name)
    package_module = sys.modules[package_name]
    module_full_name = f"{package_name}.{module_suffix}"

    try:
        imported_module = importlib.import_module(module_full_name)
    except ImportError as import_error:
        if warn_on_missing:
            package_logger.warning("Failed to import %s: %s", module_full_name, import_error)
        else:
            package_logger.debug("Skipped optional module %s: %s", module_full_name, import_error)
        return False

    setattr(package_module, alias_name, imported_module)
    package_logger.debug("Exposed module %s as %s", module_full_name, alias_name)
    return True
