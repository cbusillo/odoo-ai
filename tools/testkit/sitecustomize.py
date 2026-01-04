import hashlib
import logging
import os
import unittest
from collections.abc import Iterable

_logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return os.environ.get("OAI_TEST_SLICER", "0") == "1"


def _parse_modules() -> set[str]:
    raw_value = os.environ.get("TEST_SLICE_MODULES", "").strip()
    if not raw_value:
        return set()
    return {module_name.strip() for module_name in raw_value.split(",") if module_name.strip()}


def _bucket_of(name: str, total: int) -> int:
    if total <= 1:
        return 0
    hash_value = hashlib.sha1(name.encode()).hexdigest()
    return int(hash_value[:8], 16) % total


def _matches_target_module(py_module: str, targets: Iterable[str]) -> bool:
    if not targets:
        return True
    # Typical Odoo test module path: odoo.addons.<module>....
    for target in targets:
        needle = f".addons.{target}."
        if needle in py_module or py_module.endswith(f".addons.{target}") or py_module.startswith(f"{target}."):
            return True
    return False


def _install_loader_patch(total: int, index: int, only_modules: set[str]) -> None:
    original_getter = unittest.TestLoader.getTestCaseNames

    def sliced_get(self: unittest.TestLoader, test_case_class: type[unittest.TestCase]):  # type: ignore[override]
        names = original_getter(self, test_case_class)
        # Only slice targeted addon modules; otherwise leave untouched
        python_module = getattr(test_case_class, "__module__", "")
        if not _matches_target_module(python_module, only_modules):
            return names

        selected_names: list[str] = []
        class_name = getattr(test_case_class, "__name__", "Test")
        for test_name in names:
            if not test_name.startswith("test"):
                # don’t slice non-tests
                selected_names.append(test_name)
                continue
            bucket_key = f"{python_module}.{class_name}.{test_name}"
            if _bucket_of(bucket_key, total) == index:
                selected_names.append(test_name)
        return selected_names

    unittest.TestLoader.getTestCaseNames = sliced_get  # type: ignore[assignment]


def _main() -> None:
    if not _enabled():
        return
    try:
        total = int(os.environ.get("TEST_SLICE_TOTAL", "0"))
        index = int(os.environ.get("TEST_SLICE_INDEX", "0"))
    except ValueError:
        return
    if total <= 1 or index < 0 or index >= total:
        return
    only_modules = _parse_modules()
    _install_loader_patch(total, index, only_modules)


try:
    _main()
except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
    _logger.debug("slicer: init failed (%s)", exc)
