from __future__ import annotations

from .cli import test


def _run(args: list[str]) -> int:
    try:
        # Click returns None on success when standalone_mode=False
        rv = test.main(args=args, standalone_mode=False)
        return int(rv or 0)
    except SystemExit as e:  # pragma: no cover - click may call sys.exit
        return int(e.code or 0)


def test_plan() -> int:
    return _run(["plan", "--phase", "all", "--json"])


def test_unit() -> int:
    return _run(["unit", "--json"])


def test_js() -> int:
    return _run(["js", "--json"])


def test_integration() -> int:
    return _run(["integration", "--json"])


def test_tour() -> int:
    return _run(["tour", "--json"])


def test_clean() -> int:
    return _run(["clean"])


def test_status() -> int:
    return _run(["status", "--json"])


def test_wait() -> int:
    return _run(["wait", "--json"])


def test_rerun_failures() -> int:
    return _run(["rerun-failures", "--json"])


def test_doctor() -> int:
    return _run(["doctor", "--json"])
