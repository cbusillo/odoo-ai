#!/usr/bin/env python3

import argparse
import logging
import sys
from collections.abc import Sequence

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

    image_reference = _current_image_reference(settings)
    env_values = build_updated_environment(settings, image_reference)

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
        write_env_file(settings.env_file, env_values)

        if "database" in settings.services:
            _run_local_compose(settings, ["up", "-d", "--remove-orphans", "database"], check=False)

        _run_local_compose(settings, ["up", "-d", "--remove-orphans", settings.script_runner_service], check=False)
        _run_local_compose(settings, ["stop", "web"], check=False)
        run_process(
            local_compose_command(
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
            ),
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
