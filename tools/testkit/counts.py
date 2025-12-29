import logging
import re
from collections.abc import Iterable
from pathlib import Path


_logger = logging.getLogger(__name__)
_PY_TEST_PATTERN = re.compile(r"^\s*def\s+test_", re.MULTILINE)
_JS_TEST_PATTERN = re.compile(r"\btest\s*\(")


def count_py_tests(paths: Iterable[Path]) -> int:
    total = 0
    for path in paths:
        try:
            text = path.read_text(errors="ignore")
        except OSError as exc:
            _logger.debug("counts: unable to read %s (%s)", path, exc)
            continue
        total += len(_PY_TEST_PATTERN.findall(text))
    return total


def count_js_tests(paths: Iterable[Path]) -> int:
    total = 0
    for path in paths:
        try:
            text = path.read_text(errors="ignore")
        except OSError as exc:
            _logger.debug("counts: unable to read %s (%s)", path, exc)
            continue
        total += len(_JS_TEST_PATTERN.findall(text))
    return total
