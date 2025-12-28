from __future__ import annotations

from tools.docker_runner import restore_stack


def _restore(stack: str, *, bootstrap_only: bool) -> int:
    return restore_stack(stack, bootstrap_only=bootstrap_only, no_sanitize=False)


def restore_opw_dev() -> int:
    return _restore("opw-dev", bootstrap_only=False)


def restore_opw_testing() -> int:
    return _restore("opw-testing", bootstrap_only=False)


def restore_cm_dev() -> int:
    return _restore("cm-dev", bootstrap_only=False)


def restore_cm_testing() -> int:
    return _restore("cm-testing", bootstrap_only=False)


def restore_opw_local() -> int:
    return _restore("opw-local", bootstrap_only=False)


def restore_cm_local() -> int:
    return _restore("cm-local", bootstrap_only=False)


def init_opw_dev() -> int:
    return _restore("opw-dev", bootstrap_only=True)


def init_opw_testing() -> int:
    return _restore("opw-testing", bootstrap_only=True)


def init_cm_dev() -> int:
    return _restore("cm-dev", bootstrap_only=True)


def init_cm_testing() -> int:
    return _restore("cm-testing", bootstrap_only=True)


def init_opw_local() -> int:
    return _restore("opw-local", bootstrap_only=True)


def init_cm_local() -> int:
    return _restore("cm-local", bootstrap_only=True)
