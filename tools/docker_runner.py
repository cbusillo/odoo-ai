#!/usr/bin/env python3

import argparse
import logging
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path

# Reuse the Git helpers defined for the deploy CLI
from tools.deployer.cli import get_git_commit, get_git_remote_url
from tools.deployer.command import run_process
from tools.deployer.compose_ops import local_compose_command, remote_compose_command
from tools.deployer.deploy import (
    build_updated_environment,
    prepare_remote_stack,
    push_env_to_remote,
    write_env_file,
)
from tools.deployer.remote import run_remote
from tools.deployer.settings import load_stack_settings

STACK_ENV_TMP_DIR = Path("tmp") / "stack-env"


def _ensure_stack_env(settings, stack_name: str) -> Path:
    env_path = settings.env_file
    if env_path.exists():
        return env_path

    stack_env_path = STACK_ENV_TMP_DIR / f"{stack_name}.env"
    if stack_env_path.exists():
        return stack_env_path

    raise FileNotFoundError(
        f"No environment file found for stack '{stack_name}'. Expected {env_path} or {stack_env_path}."
    )

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)

RESTORE_SCRIPT = "/volumes/scripts/restore_from_upstream.py"


def _run_local_compose(settings, extra: Sequence[str], *, check: bool = True) -> None:
    command = local_compose_command(settings, extra)
    run_process(command, cwd=settings.repo_root, check=check)


def _run_remote_compose(settings, extra: Sequence[str]) -> None:
    if settings.remote_host is None or settings.remote_stack_path is None:
        raise ValueError("remote compose requested without remote host configuration")
    command = remote_compose_command(settings, extra)
    run_remote(settings.remote_host, settings.remote_user, settings.remote_port, command, settings.remote_stack_path)


def _current_image_reference(settings) -> str:
    return settings.environment.get(settings.image_variable_name) or settings.registry_image


def restore_stack(stack_name: str) -> int:
    settings = load_stack_settings(stack_name)
    env_file_path = _ensure_stack_env(settings, stack_name)
    image_reference = _current_image_reference(settings)
    env_values_raw = build_updated_environment(settings, image_reference)

    def _strip_quotes(raw: str) -> str:
        if len(raw) >= 2 and ((raw[0] == raw[-1]) and raw[0] in {'"', "'"}):
            return raw[1:-1]
        return raw

    pattern = re.compile(r"\$\{([^}]+)\}")
    cache: dict[str, str] = {}

    def _resolve_expr(expr: str, seen: set[str]) -> str:
        name, default = expr, ""
        if ":-" in expr:
            name, default = (part.strip() for part in expr.split(":-", 1))
        value = cache.get(name)
        if value is not None:
            return value
        if name in env_values_raw:
            return _resolve_value(name, seen)
        return os.environ.get(name, default)

    def _resolve_value(key: str, seen: set[str]) -> str:
        if key in cache:
            return cache[key]
        if key in seen:
            return env_values_raw.get(key, "")
        seen.add(key)
        raw = env_values_raw.get(key, "")
        if not isinstance(raw, str):
            raw_str = str(raw)
        else:
            raw_str = _strip_quotes(raw.strip())

        previous = None
        resolved = raw_str
        while previous != resolved:
            previous = resolved
            resolved = pattern.sub(lambda match: _resolve_expr(match.group(1), seen), resolved)

        resolved = os.path.expandvars(resolved)
        resolved = os.path.expanduser(resolved)
        cache[key] = resolved
        seen.discard(key)
        return resolved

    env_values: dict[str, str] = {}
    for key in env_values_raw:
        env_values[key] = _resolve_value(key, set())

    if settings.remote_host:
        repository_url = get_git_remote_url(settings.repo_root)
        commit = get_git_commit(settings.repo_root)
        prepare_remote_stack(settings, repository_url, commit)
        push_env_to_remote(settings, env_values)

        if "database" in settings.services:
            _run_remote_compose(settings, ["up", "-d", "--remove-orphans", "database"])

        _run_remote_compose(settings, ["up", "-d", "--remove-orphans", settings.script_runner_service])
        _run_remote_compose(settings, ["stop", "web"])
        _run_remote_compose(
            settings,
            [
                "exec",
                "-T",
                "--user",
                "root",
                settings.script_runner_service,
                "python3",
                RESTORE_SCRIPT,
            ],
        )
        _run_remote_compose(settings, ["up", "-d", "--remove-orphans", "web"])
    else:
        write_env_file(env_file_path, env_values)

        if "database" in settings.services:
            _run_local_compose(settings, ["up", "-d", "--remove-orphans", "database"], check=False)

        _run_local_compose(settings, ["up", "-d", "--remove-orphans", settings.script_runner_service], check=False)
        _run_local_compose(settings, ["stop", "web"], check=False)
        exec_extra = [
            "exec",
            "-T",
            "--user",
            "root",
        ]
        for key, value in env_values.items():
            exec_extra.extend(["-e", f"{key}={value}"])
        exec_extra.extend(
            [
                settings.script_runner_service,
                "python3",
                RESTORE_SCRIPT,
            ]
        )

        run_process(
            local_compose_command(settings, exec_extra),
            cwd=settings.repo_root,
        )
        _run_local_compose(settings, ["up", "-d", "--remove-orphans", "web"], check=False)

    _logger.info("Restore completed for stack %s", stack_name)
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore database and filestore from upstream backups")
    parser.add_argument(
        "--stack",
        default="local",
        help="Stack name to restore (default: local)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return restore_stack(args.stack)


def restore_from_upstream() -> int:  # Entry point for pyproject scripts
    return main()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
