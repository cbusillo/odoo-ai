import os
from pathlib import Path
from collections.abc import Mapping, Sequence

from .settings import StackSettings


def _compose_env_file(settings: StackSettings) -> Path:
    compose_env_file = settings.env_file.with_suffix(".compose.env")
    compose_env_values = settings.environment.copy()
    compose_env_values.pop("DOCKER_IMAGE_REFERENCE", None)
    compose_env_file.write_text(
        "\n".join(f"{key}={value}" for key, value in sorted(compose_env_values.items())) + "\n",
        encoding="utf-8",
    )
    return compose_env_file


def local_compose_command(settings: StackSettings, extra: Sequence[str]) -> list[str]:
    command = settings.compose_arguments(_compose_env_file(settings))
    command += list(extra)
    return command


def local_compose_env(settings: StackSettings) -> Mapping[str, str]:
    env = os.environ.copy()
    env.update(settings.environment)
    env.pop("DOCKER_IMAGE_REFERENCE", None)
    # Disable interactive Docker Compose prompts (e.g. volume mismatch
    # confirmations). Tooling and CI should fail fast instead of blocking on
    # stdin.
    env.setdefault("COMPOSE_INTERACTIVE_NO_CLI", "1")
    return env
