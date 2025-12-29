import hashlib
import logging
import os
import unittest
from collections.abc import Iterable

_logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return os.environ.get("OAI_TEST_SLICER", "0") == "1"


def _parse_modules() -> set[str]:
    raw = os.environ.get("TEST_SLICE_MODULES", "").strip()
    if not raw:
        return set()
    return {m.strip() for m in raw.split(",") if m.strip()}


def _bucket_of(name: str, total: int) -> int:
    if total <= 1:
        return 0
    h = hashlib.sha1(name.encode()).hexdigest()
    return int(h[:8], 16) % total


def _matches_target_module(py_module: str, targets: Iterable[str]) -> bool:
    if not targets:
        return True
    # Typical Odoo test module path: odoo.addons.<module>....
    for t in targets:
        needle = f".addons.{t}."
        if needle in py_module or py_module.endswith(f".addons.{t}") or py_module.startswith(f"{t}."):
            return True
    return False


def _install_loader_patch(total: int, index: int, only_modules: set[str]) -> None:
    orig_get = unittest.TestLoader.getTestCaseNames

    def sliced_get(self: unittest.TestLoader, test_case_class: type[unittest.TestCase]):  # type: ignore[override]
        names = orig_get(self, test_case_class)
        py_mod = getattr(test_case_class, "__module__", "")
        if not _matches_target_module(py_mod, only_modules):
            return names

        out: list[str] = []
        cls = getattr(test_case_class, "__name__", "Test")
        for n in names:
            if not n.startswith("test"):
                # don’t slice non-tests
                out.append(n)
                continue
            key = f"{py_mod}.{cls}.{n}"
            if _bucket_of(key, total) == index:
                out.append(n)
        return out

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
