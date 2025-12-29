from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

import click

from tools.deployer.command import CommandError, run_process
from tools.deployer.settings import discover_repo_root


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

    for target in targets:
        command = ["git", "push", remote, f"{from_ref}:{target}"]
        click.echo(f"$ {' '.join(command)}")
        if dry_run:
            continue
        try:
            run_process(command, cwd=repo_root)
        except CommandError as exc:
            raise click.ClickException(str(exc)) from exc
