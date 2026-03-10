import os
from collections.abc import Mapping, Sequence

from .settings import StackSettings


def local_compose_command(settings: StackSettings, extra: Sequence[str]) -> list[str]:
    command = settings.compose_arguments()
    command += list(extra)
    return command


def local_compose_env(settings: StackSettings) -> Mapping[str, str]:
    env = os.environ.copy()
    env.update(settings.environment)
    # Disable interactive Docker Compose prompts (e.g. volume mismatch
    # confirmations). Tooling and CI should fail fast instead of blocking on
    # stdin.
    env.setdefault("COMPOSE_INTERACTIVE_NO_CLI", "1")
    return env
