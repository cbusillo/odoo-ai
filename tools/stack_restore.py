#!/usr/bin/env python3

import argparse
import logging
import os
import re
import sys
from dataclasses import replace
from pathlib import Path
from collections.abc import Sequence

from tools.deployer.helpers import get_git_commit, get_git_remote_url
from tools.deployer.command import CommandError, run_process
from tools.deployer.compose_ops import local_compose_command, local_compose_env, remote_compose_command
from tools.deployer.deploy import (
    build_updated_environment,
    ensure_local_bind_mounts,
    prepare_remote_stack,
    push_env_to_remote,
    write_env_file,
)
from tools.deployer.remote import run_remote
from tools.deployer.settings import StackSettings, load_stack_settings

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)

RESTORE_SCRIPT = "/volumes/scripts/restore_from_upstream.py"
RESTORE_SSH_OVERLAY = Path("docker/config/_restore_ssh_volume.yaml")


def _ensure_stack_env(settings: StackSettings, stack_name: str) -> None:
    env_path = settings.env_file
    if env_path.exists():
        return
    raise FileNotFoundError(f"No environment file found for stack '{stack_name}'. Expected {env_path}.")


def _handle_restore_exit(error: CommandError) -> None:
    if error.returncode == 10:
        _logger.warning(
            "restore_from_upstream exited with code 10; continuing because bootstrap completed successfully"
        )
        return
    raise error


def _run_local_compose(settings: StackSettings, extra: Sequence[str], *, check: bool = True) -> None:
    command = local_compose_command(settings, extra)
    run_process(command, cwd=settings.repo_root, check=check, env=local_compose_env(settings))


def _run_remote_compose(settings: StackSettings, extra: Sequence[str]) -> None:
    if settings.remote_host is None or settings.remote_stack_path is None:
        raise ValueError("remote compose requested without remote host configuration")
    command = remote_compose_command(settings, extra)
    run_remote(settings.remote_host, settings.remote_user, settings.remote_port, command, settings.remote_stack_path)


def _current_image_reference(settings: StackSettings) -> str:
    return settings.environment.get(settings.image_variable_name) or settings.registry_image


def _settings_for_restore(settings: StackSettings) -> StackSettings:
    restore_dir = (settings.environment.get("RESTORE_SSH_DIR") or "").strip()
    if not restore_dir:
        return settings
    overlay = settings.repo_root / RESTORE_SSH_OVERLAY
    if overlay in settings.compose_files:
        return settings
    return replace(settings, compose_files=(*settings.compose_files, overlay))


def _add_toggle_env_flags(command: list[str], *, bootstrap_only: bool, no_sanitize: bool) -> None:
    if bootstrap_only:
        command.extend(["-e", "BOOTSTRAP_ONLY=1"])
    if no_sanitize:
        command.extend(["-e", "NO_SANITIZE=1"])


def _add_toggle_args(command: list[str], *, bootstrap_only: bool, no_sanitize: bool) -> None:
    if bootstrap_only:
        command.append("--bootstrap-only")
    if no_sanitize:
        command.append("--no-sanitize")


def restore_stack(
    stack_name: str,
    *,
    env_file: Path | None = None,
    bootstrap_only: bool = False,
    no_sanitize: bool = False,
) -> int:
    settings = load_stack_settings(stack_name, env_file)
    _ensure_stack_env(settings, stack_name)
    restore_settings = _settings_for_restore(settings)
    image_reference = _current_image_reference(restore_settings)
    env_values_raw = build_updated_environment(restore_settings, image_reference)

    def _strip_quotes(raw: str) -> str:
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
            return raw[1:-1]
        return raw

    pattern = re.compile(r"\$\{([^}]+)\}")
    cache: dict[str, str] = {}

    def _resolve_expr(expr: str, seen: set[str]) -> str:
        name, default = expr, ""
        if ":-" in expr:
            name, default = (part.strip() for part in expr.split(":-", 1))
        cached_value = cache.get(name)
        if cached_value is not None:
            return cached_value
        if name in env_values_raw:
            return _resolve_value(name, seen)
        return os.environ.get(name, default)

    def _resolve_value(variable_name: str, seen: set[str]) -> str:
        if variable_name in cache:
            return cache[variable_name]
        if variable_name in seen:
            return env_values_raw.get(variable_name, "")
        seen.add(variable_name)
        raw = env_values_raw.get(variable_name, "")
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
        cache[variable_name] = resolved
        seen.discard(variable_name)
        return resolved

    env_values: dict[str, str] = {}
    for env_var_name in env_values_raw:
        env_values[env_var_name] = _resolve_value(env_var_name, set())

    if restore_settings.remote_host:
        repository_url = get_git_remote_url(restore_settings.repo_root)
        commit = get_git_commit(restore_settings.repo_root)
        prepare_remote_stack(restore_settings, repository_url, commit)
        push_env_to_remote(restore_settings, env_values)

        if "database" in restore_settings.services:
            _run_remote_compose(restore_settings, ["up", "-d", "--remove-orphans", "database"])

        _run_remote_compose(restore_settings, ["up", "-d", "--remove-orphans", restore_settings.script_runner_service])
        _run_remote_compose(restore_settings, ["stop", "web"])

        remote_exec: list[str] = [
            "exec",
            "-T",
            "--user",
            "root",
        ]
        _add_toggle_env_flags(remote_exec, bootstrap_only=bootstrap_only, no_sanitize=no_sanitize)

        remote_exec.extend(
            [
                restore_settings.script_runner_service,
                "python3",
                RESTORE_SCRIPT,
            ]
        )
        _add_toggle_args(remote_exec, bootstrap_only=bootstrap_only, no_sanitize=no_sanitize)

        try:
            _run_remote_compose(restore_settings, remote_exec)
        except CommandError as error:
            _handle_restore_exit(error)
        _run_remote_compose(restore_settings, ["up", "-d", "--remove-orphans", "web"])
    else:
        ensure_local_bind_mounts(restore_settings)
        write_env_file(restore_settings.env_file, env_values)

        if "database" in restore_settings.services:
            _run_local_compose(restore_settings, ["up", "-d", "--remove-orphans", "database"], check=False)

        _run_local_compose(
            restore_settings,
            ["up", "-d", "--remove-orphans", restore_settings.script_runner_service],
            check=False,
        )
        _run_local_compose(restore_settings, ["stop", "web"], check=False)
        exec_extra = [
            "exec",
            "-T",
            "--user",
            "root",
        ]
        for env_key, env_value in env_values.items():
            exec_extra.extend(["-e", f"{env_key}={env_value}"])
        _add_toggle_env_flags(exec_extra, bootstrap_only=bootstrap_only, no_sanitize=no_sanitize)
        exec_extra.extend(
            [
                restore_settings.script_runner_service,
                "python3",
                RESTORE_SCRIPT,
            ]
        )
        _add_toggle_args(exec_extra, bootstrap_only=bootstrap_only, no_sanitize=no_sanitize)

        try:
            run_process(
                local_compose_command(restore_settings, exec_extra),
                cwd=restore_settings.repo_root,
                env=local_compose_env(restore_settings),
            )
        except CommandError as error:
            _handle_restore_exit(error)
        _run_local_compose(restore_settings, ["up", "-d", "--remove-orphans", "web"], check=False)

    _logger.info("Restore completed for stack %s", stack_name)
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore database and filestore from upstream backups")
    parser.add_argument(
        "--stack",
        default="local",
        help="Stack name to restore (default: local)",
    )
    parser.add_argument(
        "--bootstrap-only",
        action="store_true",
        help="Only bootstrap the stack (skip full upstream restore)",
    )
    parser.add_argument(
        "--no-sanitize",
        action="store_true",
        help="Skip sanitize steps during restore",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return restore_stack(args.stack, bootstrap_only=args.bootstrap_only, no_sanitize=args.no_sanitize)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
