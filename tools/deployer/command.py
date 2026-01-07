import logging
import re
import shlex
import subprocess
import sys
import time
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


_DOCKER_TRANSIENT_ERROR_RE = re.compile(
    r"request returned 500 Internal Server Error for API route"
    r"|unable to get image"
    r"|check if the server supports the requested API version",
    re.IGNORECASE,
)


def _looks_like_transient_docker_api_failure(command: Sequence[str], stderr: str | None) -> bool:
    if not stderr:
        return False
    if not command:
        return False
    if command[0] != "docker":
        return False
    # Never auto-retry `docker exec` / `docker compose exec` because callers may
    # be running non-idempotent operations (migrations/upgrades). Even if the
    # error looks like a Docker API hiccup, it's safer to let the operator
    # rerun explicitly.
    if "exec" in command:
        return False
    return bool(_DOCKER_TRANSIENT_ERROR_RE.search(stderr))


def run_process(
    command: Sequence[str],
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    capture_output: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    logger = logging.getLogger("deploy.command")
    logger.debug("$ %s", " ".join(shlex.quote(part) for part in command))

    is_docker = bool(command and command[0] == "docker")
    is_docker_execute_command = is_docker and any(part == "exec" for part in command)
    attempts = 3 if is_docker else 1
    last_result: subprocess.CompletedProcess[str] | None = None
    for attempt_number in range(1, attempts + 1):
        if capture_output:
            result = subprocess.run(
                list(command),
                cwd=str(cwd) if cwd is not None else None,
                env=dict(env) if env is not None else None,
                capture_output=True,
                text=True,
            )
        else:
            # For docker commands, capture stderr so we can detect transient
            # Docker Desktop API failures (HTTP 5xx) without changing stdout
            # streaming behavior. Skip capture for exec so output streams live.
            result = subprocess.run(
                list(command),
                cwd=str(cwd) if cwd is not None else None,
                env=dict(env) if env is not None else None,
                stdout=None,
                stderr=None if is_docker_execute_command else (subprocess.PIPE if is_docker else None),
                text=True,
            )

            # Preserve stderr visibility for docker commands. Docker CLI writes
            # progress and warnings to stderr even on success; capturing it for
            # retry detection must not silence it.
            if is_docker and result.stderr:
                sys.stderr.write(result.stderr)
                sys.stderr.flush()
        last_result = result
        if not (check and result.returncode != 0):
            return result

        stderr = result.stderr
        if attempt_number >= attempts or not _looks_like_transient_docker_api_failure(command, stderr):
            raise CommandError(command, result.returncode, result.stdout if capture_output else None, stderr)

        delay_seconds = 2 ** (attempt_number - 1)
        logger.warning(
            "Transient Docker API failure (attempt %s/%s); retrying in %ss",
            attempt_number,
            attempts,
            delay_seconds,
        )
        time.sleep(delay_seconds)

    raise CommandError(command, last_result.returncode if last_result else 1, None, None)
