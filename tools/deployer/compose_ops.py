from collections.abc import Sequence
from pathlib import PurePosixPath

from .command import run_process
from .settings import StackSettings


def relative_compose_paths(settings: StackSettings) -> tuple[str, ...]:
    relative_paths: list[str] = []
    for file_path in settings.compose_files:
        relative = file_path.relative_to(settings.repo_root)
        relative_paths.append(PurePosixPath(*relative.parts).as_posix())
    return tuple(relative_paths)


def local_compose_command(settings: StackSettings, extra: Sequence[str]) -> list[str]:
    command = settings.compose_arguments()
    command += list(extra)
    return command


def local_compose(settings: StackSettings, extra: Sequence[str]) -> None:
    run_process(local_compose_command(settings, extra), cwd=settings.repo_root)


def remote_compose_command(settings: StackSettings, extra: Sequence[str]) -> list[str]:
    if settings.remote_stack_path is None:
        raise ValueError("remote stack path missing")
    if settings.remote_env_path is None:
        raise ValueError("remote env path missing")
    command = list(settings.compose_command)
    command += ["-p", settings.compose_project, "--env-file", str(settings.remote_env_path)]
    for relative in relative_compose_paths(settings):
        command += ["-f", relative]
    command += list(extra)
    return command
