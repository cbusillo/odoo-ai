from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

import click

from tools.deployer.cli import (
    convert_key_values,
    get_git_commit,
    get_git_remote_url,
    resolve_image_reference,
    resolve_remote_flag,
    run_build,
)
from tools.deployer.command import CommandError, run_process
from tools.deployer.compose_ops import local_compose_command, remote_compose_command
from tools.deployer.deploy import deploy_stack
from tools.deployer.remote import run_remote
from tools.deployer.settings import discover_repo_root, load_stack_settings
from tools.stack_restore import restore_stack

ENV_SUFFIXES = ("dev", "testing", "prod")


def _git_output(args: Iterable[str], *, cwd: Path | None = None, check: bool = True) -> str:
    result = run_process(list(args), cwd=cwd, capture_output=True, check=check)
    return (result.stdout or "").strip()


def _list_remote_branches(repo_root: Path, remote: str) -> list[str]:
    output = _git_output(["git", "ls-remote", "--heads", remote], cwd=repo_root, check=False)
    branches: list[str] = []
    for line in output.splitlines():
        _, ref = (line.split(maxsplit=1) + [""])[:2]
        if not ref.startswith("refs/heads/"):
            continue
        branches.append(ref.removeprefix("refs/heads/"))
    return branches


def _group_env_branches(branches: Iterable[str], suffixes: Iterable[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for branch in branches:
        for suffix in suffixes:
            tail = f"-{suffix}"
            if not branch.endswith(tail):
                continue
            prefix = branch[: -len(tail)]
            if not prefix:
                continue
            grouped[prefix].append(branch)
            break
    for key in grouped:
        grouped[key] = sorted(set(grouped[key]))
    grouped["all"] = sorted({branch for branches in grouped.values() for branch in branches})
    return grouped


def _format_groups(groups: dict[str, list[str]]) -> str:
    ordered = sorted(groups.items(), key=lambda item: item[0])
    return "\n".join(f"{name}: {', '.join(values)}" for name, values in ordered if values)


@click.group("stack")
def main() -> None:
    """Stack helper commands."""


@main.command("promote")
@click.option("--from", "from_ref", default="HEAD", show_default=True)
@click.option("--group", "group_name", default="all", show_default=True)
@click.option("--remote", default="origin", show_default=True)
@click.option("--suffix", "suffixes", multiple=True, default=ENV_SUFFIXES, show_default=True)
@click.option("--list-groups", is_flag=True, help="List discovered environment groups and exit")
@click.option("--dry-run", is_flag=True)
def promote_command(
    from_ref: str,
    group_name: str,
    remote: str,
    suffixes: tuple[str, ...],
    list_groups: bool,
    dry_run: bool,
) -> None:
    repo_root = discover_repo_root(Path.cwd())
    branches = _list_remote_branches(repo_root, remote)
    groups = _group_env_branches(branches, suffixes)
    if list_groups:
        click.echo(_format_groups(groups) or "(no env branches found)")
        return

    targets = groups.get(group_name, [])
    if not targets:
        known = ", ".join(sorted(groups)) if groups else "(none)"
        raise click.ClickException(f"unknown group '{group_name}'. Known groups: {known}")

    if not dry_run:
        prod_targets = [target for target in targets if target.endswith("-prod")]
        if prod_targets:
            click.confirm(
                f"Push {from_ref} to prod branch(es): {', '.join(prod_targets)}?",
                abort=True,
            )

    for target in targets:
        command = ["git", "push", remote, f"{from_ref}:{target}"]
        click.echo(f"$ {' '.join(command)}")
        if dry_run:
            continue
        try:
            run_process(command, cwd=repo_root)
        except CommandError as exc:
            raise click.ClickException(str(exc)) from exc


@main.command("up")
@click.option("--stack", "stack_name", required=True)
@click.option("--env-file", type=click.Path(path_type=Path))
@click.option("--tag")
@click.option("--image")
@click.option("--remote/--local", "remote_flag", default=None)
@click.option("--build/--no-build", "build_flag", default=True, show_default=True)
@click.option("--no-cache", is_flag=True)
@click.option("--restore/--no-restore", "restore_flag", default=False, show_default=True)
@click.option(
    "--init",
    "bootstrap_init",
    is_flag=True,
    help="Bootstrap a new stack (implies --restore --bootstrap-only).",
)
@click.option("--bootstrap-only", is_flag=True)
@click.option("--no-sanitize", is_flag=True)
@click.option("--skip-upgrade", is_flag=True)
@click.option("--skip-health", is_flag=True)
@click.option("--health-timeout", default=60, type=int, show_default=True)
@click.option("--set", "overrides", multiple=True)
def up_command(
    stack_name: str,
    env_file: Path | None,
    tag: str | None,
    image: str | None,
    remote_flag: bool | None,
    build_flag: bool,
    no_cache: bool,
    restore_flag: bool,
    bootstrap_init: bool,
    bootstrap_only: bool,
    no_sanitize: bool,
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

    if bootstrap_init:
        restore_flag = True
        bootstrap_only = True

    if build_flag:
        run_build(settings, remote, no_cache, repository_url, commit)

    if restore_flag:
        restore_stack(stack_name, bootstrap_only=bootstrap_only, no_sanitize=no_sanitize)
        return

    deploy_stack(
        settings,
        image_reference,
        remote,
        skip_upgrade=skip_upgrade,
        skip_health_check=skip_health,
        health_timeout_seconds=health_timeout,
        extra_env=extra_variables or None,
        repository_url=repository_url,
        commit=commit,
    )


@main.command("down")
@click.option("--stack", "stack_name", required=True)
@click.option("--env-file", type=click.Path(path_type=Path))
@click.option("--remote/--local", "remote_flag", default=None)
def down_command(stack_name: str, env_file: Path | None, remote_flag: bool | None) -> None:
    settings = load_stack_settings(stack_name, env_file)
    remote = resolve_remote_flag(settings, remote_flag)
    command = remote_compose_command(settings, ["down"]) if remote else local_compose_command(settings, ["down"])
    if remote:
        if settings.remote_host is None or settings.remote_stack_path is None:
            raise click.ClickException("remote stack configuration incomplete")
        run_remote(settings.remote_host, settings.remote_user, settings.remote_port, command, settings.remote_stack_path)
        return
    run_process(command, cwd=settings.repo_root)
