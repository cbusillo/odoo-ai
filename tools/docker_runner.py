#!/usr/bin/env python3
import logging
import os
import shutil
import subprocess
from typing import Sequence


logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)


def run_compose_command(command: Sequence[str], *, must_succeed: bool = True) -> int:
    _logger.debug(f"$ {' '.join(command)}")
    result = subprocess.run(list(command))
    if must_succeed and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result.returncode


def resolve_script_runner_container() -> str:
    project = os.environ.get("ODOO_PROJECT_NAME", "odoo")
    return f"{project}-script-runner-1"


def restore_from_upstream() -> int:
    if shutil.which("docker") is None:
        _logger.error("docker CLI not found on PATH")
        return 127

    run_compose_command(["docker", "compose", "up", "-d", "--remove-orphans", "script-runner"], must_succeed=False)

    run_compose_command(["docker", "compose", "stop", "web"], must_succeed=False)

    container = resolve_script_runner_container()
    return_code = run_compose_command(
        [
            "docker",
            "exec",
            container,
            "python3",
            "/volumes/scripts/restore_from_upstream.py",
        ]
    )

    run_compose_command(["docker", "compose", "up", "-d", "--remove-orphans", "web"], must_succeed=False)

    return return_code
