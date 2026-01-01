from collections.abc import Iterable
from pathlib import Path

import click

from .command import run_process
from .compose_ops import local_compose_command, local_compose_env, remote_compose_command
from .remote import run_remote, sync_remote_repository
from .settings import StackSettings


def convert_key_values(values: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise click.BadParameter(f"expected KEY=VALUE, received {item}")
        key, value = item.split("=", 1)
        result[key] = value
    return result


def get_git_commit(repo_root: Path) -> str:
    result = run_process(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True)
    output = (result.stdout or "").strip()
    if not output:
        raise RuntimeError("unable to determine git revision")
    return output


def get_git_short_commit(repo_root: Path) -> str:
    result = run_process(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root, capture_output=True)
    output = (result.stdout or "").strip()
    if not output:
        raise RuntimeError("unable to determine git revision")
    return output


def get_git_remote_url(repo_root: Path, remote_name: str = "origin") -> str:
    result = run_process(["git", "remote", "get-url", remote_name], cwd=repo_root, capture_output=True, check=False)
    output = (result.stdout or "").strip()
    if result.returncode != 0 or not output:
        raise RuntimeError(f"remote '{remote_name}' url unavailable")
    return output


def resolve_image_reference(settings: StackSettings, tag: str | None, image: str | None) -> str:
    if image and tag:
        raise click.BadParameter("provide either --tag or --image, not both")
    if image:
        return image
    resolved_tag = tag or f"{settings.name}-{get_git_short_commit(settings.repo_root)}"
    return f"{settings.registry_image}:{resolved_tag}"


def resolve_remote_flag(settings: StackSettings, remote_flag: bool | None) -> bool:
    if remote_flag is not None:
        return remote_flag
    return settings.remote_host is not None


def sync_repository(settings: StackSettings, repository_url: str | None, commit: str, remote: bool) -> None:
    if not remote:
        return
    if repository_url is None:
        raise ValueError("remote repository url required")
    if settings.remote_host is None or settings.remote_stack_path is None:
        raise ValueError("remote repository configuration incomplete")
    sync_remote_repository(
        settings.remote_host,
        settings.remote_user,
        settings.remote_port,
        settings.remote_stack_path,
        repository_url,
        commit,
        settings.github_token,
    )


def run_build(
    settings: StackSettings,
    remote: bool,
    no_cache: bool,
    repository_url: str | None,
    commit: str,
) -> None:
    build_args = ["build"]
    if no_cache:
        build_args.append("--no-cache")

    services = [service for service in ("script-runner", "web") if service in settings.services]
    if services:
        # Avoid buildx export collisions when multiple services share the same image tag.
        build_args.append(services[0])
    else:
        build_args.extend(settings.services)

    if remote:
        sync_repository(settings, repository_url, commit, remote)
        command = remote_compose_command(settings, build_args)
        run_remote(settings.remote_host, settings.remote_user, settings.remote_port, command, settings.remote_stack_path)
    else:
        command = local_compose_command(settings, build_args)
        run_process(command, cwd=settings.repo_root, env=local_compose_env(settings))
