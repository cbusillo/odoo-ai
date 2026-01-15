import argparse
import logging
import sys
from collections.abc import Sequence
from enum import IntEnum
from pathlib import Path

from pydantic import ValidationError
from restore_from_upstream import LocalServerSettings, OdooRestorerError, OdooUpstreamRestorer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExitCode(IntEnum):
    SUCCESS = 0
    INVALID_ARGS = 30
    OPENUPGRADE_FAILED = 40


def parse_arguments(argument_values: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenUpgrade against the current database")
    parser.add_argument("--env-file", type=Path, default=None, help="Optional env file to load settings from")
    parser.add_argument("--scripts-path", type=Path, default=None, help="Override OPENUPGRADE_SCRIPTS_PATH")
    parser.add_argument("--target-version", type=str, default=None, help="Override OPENUPGRADE_TARGET_VERSION")
    parser.add_argument("--force", action="store_true", help="Run even if OPENUPGRADE_ENABLED is false")
    parser.add_argument(
        "--reset-versions",
        action="store_true",
        help="Reset module versions for OpenUpgrade scripts before running",
    )
    return parser.parse_args(argument_values)


def main(argument_values: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argument_values)

    env_file: Path | None = arguments.env_file
    settings_kwargs: dict[str, object] = {}
    if env_file and env_file.exists():
        settings_kwargs["_env_file"] = env_file
    elif env_file is not None:
        logger.warning("Env file %s not found; falling back to process environment", env_file)
        env_file = None

    try:
        local_settings = LocalServerSettings(**settings_kwargs)
    except ValidationError as validation_error:
        logger.error("Invalid local configuration: %s", validation_error)
        return int(ExitCode.INVALID_ARGS)

    if arguments.scripts_path is not None:
        local_settings.openupgrade_scripts_path = arguments.scripts_path
    if arguments.target_version:
        local_settings.openupgrade_target_version = arguments.target_version

    if arguments.force and not local_settings.openupgrade_enabled:
        local_settings.openupgrade_enabled = True

    if not local_settings.openupgrade_enabled:
        logger.error("OpenUpgrade disabled. Set OPENUPGRADE_ENABLED=1 or pass --force.")
        return int(ExitCode.INVALID_ARGS)

    restorer = OdooUpstreamRestorer(local_settings, None, env_file)
    if arguments.reset_versions:
        try:
            restorer.reset_openupgrade_versions()
        except OdooRestorerError as reset_error:
            logger.error("OpenUpgrade reset failed: %s", reset_error)
            return int(ExitCode.OPENUPGRADE_FAILED)
    try:
        restorer.run_openupgrade()
    except OdooRestorerError as openupgrade_error:
        logger.error("OpenUpgrade failed: %s", openupgrade_error)
        return int(ExitCode.OPENUPGRADE_FAILED)

    logger.info("OpenUpgrade completed successfully.")
    return int(ExitCode.SUCCESS)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
