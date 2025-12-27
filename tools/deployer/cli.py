import logging
from collections.abc import Iterable
from pathlib import Path

import click

from .command import run_process
from .compose_ops import local_compose_command, remote_compose_command
from .deploy import deploy_stack, render_settings, show_status
from .docker_ops import build_image, inspect_image_digest, pull_image, push_image
from .health import HealthcheckError
from .remote import run_remote, sync_remote_repository
from .settings import StackSettings, load_stack_settings


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")


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

    services = [service for service in ("web", "script-runner") if service in settings.services]
    build_args.extend(services)

    if remote:
        sync_repository(settings, repository_url, commit, remote)
        command = remote_compose_command(settings, build_args)
        run_remote(settings.remote_host, settings.remote_user, settings.remote_port, command, settings.remote_stack_path)
    else:
        command = local_compose_command(settings, build_args)
        run_process(command, cwd=settings.repo_root)


@click.group()
@click.option("--verbose", is_flag=True, help="Enable debug logging")
def main(verbose: bool) -> None:
    configure_logging(verbose)


@main.command("build")
@click.option("--stack", "stack_name", required=True)
@click.option("--env-file", type=click.Path(path_type=Path))
@click.option("--tag")
@click.option("--image")
@click.option("--dockerfile", type=click.Path(path_type=Path))
@click.option("--build-arg", "build_args", multiple=True)
@click.option("--target")
@click.option("--push/--no-push", default=False)
def build_command(
    stack_name: str,
    env_file: Path | None,
    tag: str | None,
    image: str | None,
    dockerfile: Path | None,
    build_args: tuple[str, ...],
    target: str | None,
    push: bool,
) -> None:
    settings = load_stack_settings(stack_name, env_file)
    image_reference = resolve_image_reference(settings, tag, image)
    mapping = convert_key_values(build_args)
    build_image(image_reference, settings.docker_context, dockerfile, mapping, target)
    if push:
        push_image(image_reference)
    click.echo(image_reference)


@main.command("push")
@click.option("--stack", "stack_name", required=True)
@click.option("--env-file", type=click.Path(path_type=Path))
@click.option("--tag")
@click.option("--image")
def push_command(stack_name: str, env_file: Path | None, tag: str | None, image: str | None) -> None:
    settings = load_stack_settings(stack_name, env_file)
    image_reference = resolve_image_reference(settings, tag, image)
    push_image(image_reference)
    click.echo(image_reference)


@main.command("pull")
@click.option("--stack", "stack_name", required=True)
@click.option("--env-file", type=click.Path(path_type=Path))
@click.option("--tag")
@click.option("--image")
def pull_command(stack_name: str, env_file: Path | None, tag: str | None, image: str | None) -> None:
    settings = load_stack_settings(stack_name, env_file)
    image_reference = resolve_image_reference(settings, tag, image)
    pull_image(image_reference)
    click.echo(image_reference)


@main.command("deploy")
@click.option("--stack", "stack_name", required=True)
@click.option("--env-file", type=click.Path(path_type=Path))
@click.option("--tag")
@click.option("--image")
@click.option("--remote/--local", "remote_flag", default=None)
@click.option("--build/--no-build", "build_flag", default=False, help="Build stack images before deploying")
@click.option("--no-cache", is_flag=True, help="When building, disable Docker build cache")
@click.option("--skip-upgrade", is_flag=True)
@click.option("--skip-health", is_flag=True)
@click.option("--health-timeout", default=60, type=int)
@click.option("--set", "overrides", multiple=True)
def deploy_command(
    stack_name: str,
    env_file: Path | None,
    tag: str | None,
    image: str | None,
    remote_flag: bool | None,
    build_flag: bool,
    no_cache: bool,
    skip_upgrade: bool,
    skip_health: bool,
    health_timeout: int,
    overrides: tuple[str, ...],
) -> None:
    settings = load_stack_settings(stack_name, env_file)
    remote = resolve_remote_flag(settings, remote_flag)
    commit = get_git_commit(settings.repo_root)
    repository_url = get_git_remote_url(settings.repo_root) if remote else None
    image_reference = resolve_image_reference(settings, tag, image)
    extra_variables = convert_key_values(overrides)
    if build_flag:
        run_build(settings, remote, no_cache, repository_url, commit)
    try:
        deploy_stack(
            settings,
            image_reference,
            remote,
            skip_upgrade,
            skip_health,
            health_timeout,
            extra_variables,
            repository_url,
            commit,
        )
    except HealthcheckError as error:
        raise click.ClickException(str(error))
    click.echo(image_reference)


@main.command("status")
@click.option("--stack", "stack_name", required=True)
@click.option("--env-file", type=click.Path(path_type=Path))
@click.option("--remote/--local", "remote_flag", default=None)
def status_command(stack_name: str, env_file: Path | None, remote_flag: bool | None) -> None:
    settings = load_stack_settings(stack_name, env_file)
    remote = resolve_remote_flag(settings, remote_flag)
    show_status(settings, remote)


@main.command("inspect")
@click.option("--stack", "stack_name", required=True)
@click.option("--env-file", type=click.Path(path_type=Path))
@click.option("--tag")
@click.option("--image")
def inspect_command(stack_name: str, env_file: Path | None, tag: str | None, image: str | None) -> None:
    settings = load_stack_settings(stack_name, env_file)
    image_reference = resolve_image_reference(settings, tag, image)
    digest = inspect_image_digest(image_reference)
    click.echo(digest)


@main.command("describe")
@click.option("--stack", "stack_name", required=True)
@click.option("--env-file", type=click.Path(path_type=Path))
@click.option("--tag")
@click.option("--image")
def describe_command(stack_name: str, env_file: Path | None, tag: str | None, image: str | None) -> None:
    settings = load_stack_settings(stack_name, env_file)
    image_reference = resolve_image_reference(settings, tag, image)
    click.echo(render_settings(settings, image_reference))
