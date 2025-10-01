import shlex
from collections.abc import Sequence
from pathlib import Path

from .command import run_process


def build_ssh_target(user: str | None, host: str) -> str:
    if user:
        return f"{user}@{host}"
    return host


def ssh_arguments(user: str | None, host: str, port: int | None) -> list[str]:
    arguments = ["ssh"]
    if port is not None:
        arguments += ["-p", str(port)]
    arguments.append(build_ssh_target(user, host))
    return arguments


def run_remote(host: str, user: str | None, port: int | None, command: Sequence[str], working_directory: Path | None = None) -> None:
    quoted_command = " ".join(shlex.quote(part) for part in command)
    if working_directory is not None:
        quoted_directory = shlex.quote(str(working_directory))
        remote_command = f"cd {quoted_directory} && {quoted_command}"
    else:
        remote_command = quoted_command
    arguments = ssh_arguments(user, host, port)
    arguments.append(remote_command)
    run_process(arguments)


def upload_file(host: str, user: str | None, port: int | None, source: Path, destination: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    arguments = ["scp"]
    if port is not None:
        arguments += ["-P", str(port)]
    arguments += ["-q", str(source), f"{build_ssh_target(user, host)}:{destination}"]
    run_process(arguments)


def ensure_remote_directory(host: str, user: str | None, port: int | None, path: Path) -> None:
    arguments = ["mkdir", "-p", str(path)]
    run_remote(host, user, port, arguments)


def remote_path_exists(host: str, user: str | None, port: int | None, path: Path) -> bool:
    arguments = ssh_arguments(user, host, port)
    arguments.append(f"test -d {shlex.quote(str(path))}")
    result = run_process(arguments, check=False)
    return result.returncode == 0


def sync_remote_repository(host: str, user: str | None, port: int | None, path: Path, repository_url: str, commit: str) -> None:
    ensure_remote_directory(host, user, port, path.parent)
    repo_git = path / ".git"
    if not remote_path_exists(host, user, port, repo_git):
        run_remote(host, user, port, ["rm", "-rf", str(path)])
        run_remote(host, user, port, ["git", "clone", repository_url, str(path)])
    else:
        run_remote(host, user, port, ["git", "-C", str(path), "remote", "set-url", "origin", repository_url])
    run_remote(host, user, port, ["git", "-C", str(path), "fetch", "--prune", "origin"])
    run_remote(host, user, port, ["git", "-C", str(path), "reset", "--hard", commit])
