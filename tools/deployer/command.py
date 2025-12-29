import logging
import shlex
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path


class CommandError(RuntimeError):
    def __init__(self, command: Sequence[str], returncode: int, stdout: str | None, stderr: str | None):
        joined_command = " ".join(shlex.quote(part) for part in command)
        message = f"command failed ({returncode}): {joined_command}"
        super().__init__(message)
        self.command = tuple(command)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run_process(
    command: Sequence[str],
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    capture_output: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    logging.getLogger("deploy.command").debug("$ %s", " ".join(shlex.quote(part) for part in command))
    result = subprocess.run(
        list(command),
        cwd=str(cwd) if cwd is not None else None,
        env=dict(env) if env is not None else None,
        capture_output=capture_output,
        text=True,
    )
    if check and result.returncode != 0:
        raise CommandError(
            command, result.returncode, result.stdout if capture_output else None, result.stderr if capture_output else None
        )
    return result
