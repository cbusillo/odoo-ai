from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import click
from pydantic import BaseModel, Field, ValidationError

from tools.deployer.command import run_process
from tools.deployer.settings import discover_repo_root, load_stack_settings


class AddonPin(BaseModel):
    path: str
    ref: str | None = None
    branch: str | None = None


class AddonManifest(BaseModel):
    schema_version: str = Field(default="1.0")
    addons: dict[str, AddonPin] = Field(default_factory=dict)


@dataclass(frozen=True)
class SubmoduleInfo:
    name: str
    path: Path
    head: str | None
    branch: str | None
    dirty: bool
    initialized: bool


def _git_output(args: Iterable[str], *, cwd: Path | None = None, check: bool = True) -> str:
    result = run_process(list(args), cwd=cwd, capture_output=True, check=check)
    return (result.stdout or "").strip()


def _submodule_paths(repo_root: Path) -> list[Path]:
    gitmodules = repo_root / ".gitmodules"
    if not gitmodules.exists():
        return []
    result = run_process(
        ["git", "config", "-f", str(gitmodules), "--get-regexp", "path"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    paths: list[Path] = []
    for line in (result.stdout or "").splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        path = parts[1].strip()
        if not path:
            continue
        paths.append(repo_root / path)
    return paths


def _submodule_info(repo_root: Path, path: Path) -> SubmoduleInfo:
    name = path.name
    if not path.exists():
        return SubmoduleInfo(name=name, path=path, head=None, branch=None, dirty=False, initialized=False)
    toplevel_raw = _git_output(["git", "-C", str(path), "rev-parse", "--show-toplevel"], check=False)
    if not toplevel_raw:
        return SubmoduleInfo(name=name, path=path, head=None, branch=None, dirty=False, initialized=False)
    try:
        toplevel = Path(toplevel_raw).resolve()
    except OSError:
        return SubmoduleInfo(name=name, path=path, head=None, branch=None, dirty=False, initialized=False)
    if toplevel != path.resolve():
        return SubmoduleInfo(name=name, path=path, head=None, branch=None, dirty=False, initialized=False)
    head: str | None = _git_output(["git", "-C", str(path), "rev-parse", "HEAD"], check=False)
    if not head:
        head = None
    branch: str | None = _git_output(["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"], check=False)
    if not branch or branch == "HEAD":
        branch = None
    dirty = bool(_git_output(["git", "-C", str(path), "status", "--porcelain"], check=False))
    return SubmoduleInfo(name=name, path=path, head=head, branch=branch, dirty=dirty, initialized=True)


def _default_manifest_path(repo_root: Path, stack_name: str) -> Path:
    return repo_root / "docker" / "config" / f"{stack_name}.addons.json"


def _load_manifest(path: Path) -> AddonManifest | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return AddonManifest.model_validate(payload)


def _manifest_by_path(repo_root: Path, manifest: AddonManifest) -> dict[Path, tuple[str, AddonPin]]:
    mapping: dict[Path, tuple[str, AddonPin]] = {}
    for name, pin in manifest.addons.items():
        resolved = (repo_root / pin.path).resolve()
        mapping[resolved] = (name, pin)
    return mapping


def _write_manifest(path: Path, manifest: AddonManifest) -> None:
    payload = manifest.model_dump()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require_manifest(path: Path) -> AddonManifest:
    if not path.exists():
        raise click.ClickException(f"manifest not found: {path}")
    try:
        manifest = _load_manifest(path)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise click.ClickException(f"invalid manifest: {exc}") from exc
    if manifest is None:
        raise click.ClickException(f"manifest not found: {path}")
    return manifest


def _submodule_info_map(repo_root: Path) -> dict[Path, SubmoduleInfo]:
    return {path.resolve(): _submodule_info(repo_root, path) for path in _submodule_paths(repo_root)}


def _format_head(head: str | None) -> str:
    if not head:
        return "(none)"
    return head[:12]


def _format_branch(branch: str | None) -> str:
    return branch or "(detached)"


def _echo_kv(label: str, value: str) -> None:
    click.echo(f"{label}: {value}")


@click.group("stack")
def main() -> None:
    """Stack helper commands."""


@main.command("status")
@click.option("--stack", "stack_name", required=True)
@click.option("--manifest", "manifest_path", type=click.Path(path_type=Path))
def status_command(stack_name: str, manifest_path: Path | None) -> None:
    repo_root = discover_repo_root(Path.cwd())
    settings = load_stack_settings(stack_name)
    manifest_file = manifest_path or _default_manifest_path(repo_root, stack_name)
    manifest: AddonManifest | None = None
    manifest_error: str | None = None
    if manifest_file.exists():
        try:
            manifest = _load_manifest(manifest_file)
        except (json.JSONDecodeError, ValidationError) as exc:
            manifest_error = str(exc)
    _echo_kv("stack", stack_name)
    _echo_kv("env source", str(settings.source_env_file))
    _echo_kv("env merged", str(settings.env_file))
    _echo_kv("compose project", settings.compose_project)
    _echo_kv("compose files", ", ".join(str(path) for path in settings.compose_files))
    if manifest_error:
        _echo_kv("manifest", f"invalid ({manifest_file})")
        _echo_kv("manifest error", manifest_error)
    else:
        _echo_kv("manifest", str(manifest_file if manifest_file.exists() else "(missing)"))
    click.echo("\nSubmodules:")
    submodules = [_submodule_info(repo_root, path) for path in _submodule_paths(repo_root)]
    manifest_paths = _manifest_by_path(repo_root, manifest) if manifest else {}
    for info in submodules:
        manifest_entry = manifest_paths.get(info.path.resolve())
        initialized = "true" if info.initialized else "false"
        click.echo(
            f"- {info.name}: head={_format_head(info.head)} branch={_format_branch(info.branch)}"
            f" dirty={str(info.dirty).lower()} initialized={initialized}"
        )
        if manifest_entry:
            _, pin = manifest_entry
            if pin.ref and info.head and pin.ref != info.head:
                click.echo(f"  ! ref mismatch manifest={_format_head(pin.ref)} actual={_format_head(info.head)}")
            if pin.branch and info.branch and pin.branch != info.branch:
                click.echo(f"  ! branch mismatch manifest={pin.branch} actual={info.branch}")
    if manifest:
        click.echo("\nManifest entries:")
        known_paths = {info.path.resolve() for info in submodules}
        for name, pin in manifest.addons.items():
            pin_path = (repo_root / pin.path).resolve()
            status = "ok" if pin_path in known_paths else "missing"
            click.echo(f"- {name}: {pin.path} ({status})")


@main.command("pin")
@click.option("--stack", "stack_name", required=True)
@click.option("--manifest", "manifest_path", type=click.Path(path_type=Path))
def pin_command(stack_name: str, manifest_path: Path | None) -> None:
    repo_root = discover_repo_root(Path.cwd())
    manifest_file = manifest_path or _default_manifest_path(repo_root, stack_name)
    addons: dict[str, AddonPin] = {}
    errors: list[str] = []
    for path in _submodule_paths(repo_root):
        info = _submodule_info(repo_root, path)
        if not info.initialized:
            errors.append(f"{info.name} is not initialized")
            continue
        rel_path = str(path.relative_to(repo_root))
        addons[info.name] = AddonPin(path=rel_path, ref=info.head, branch=info.branch)
    if errors:
        for message in errors:
            click.echo(f"- {message}")
        raise click.ClickException("cannot pin stack manifest; initialize submodules")
    manifest = AddonManifest(addons=addons)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    _write_manifest(manifest_file, manifest)
    click.echo(f"Pinned {len(addons)} addons to {manifest_file}")


@main.command("verify")
@click.option("--stack", "stack_name", required=True)
@click.option("--manifest", "manifest_path", type=click.Path(path_type=Path))
def verify_command(stack_name: str, manifest_path: Path | None) -> None:
    repo_root = discover_repo_root(Path.cwd())
    manifest_file = manifest_path or _default_manifest_path(repo_root, stack_name)
    if not manifest_file.exists():
        raise click.ClickException(f"manifest not found: {manifest_file}")
    try:
        manifest = _load_manifest(manifest_file)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise click.ClickException(f"invalid manifest: {exc}") from exc
    if manifest is None:
        raise click.ClickException(f"manifest not found: {manifest_file}")
    manifest_paths = _manifest_by_path(repo_root, manifest)
    errors: list[str] = []
    submodule_paths = _submodule_paths(repo_root)
    if not submodule_paths:
        errors.append("no submodules discovered; cannot verify manifest")
    known_paths = {path.resolve() for path in submodule_paths}
    unknown_manifest = [name for path, (name, _) in manifest_paths.items() if path not in known_paths]
    for name in unknown_manifest:
        errors.append(f"manifest entry {name} not found in .gitmodules")
    for path in submodule_paths:
        info = _submodule_info(repo_root, path)
        entry = manifest_paths.get(info.path.resolve())
        if entry is None:
            errors.append(f"missing manifest entry for {info.name}")
            continue
        if not info.initialized:
            errors.append(f"{info.name} is not initialized")
            continue
        _, pin = entry
        if pin.ref and info.head and pin.ref != info.head:
            errors.append(f"{info.name} ref mismatch manifest={_format_head(pin.ref)} actual={_format_head(info.head)}")
        if pin.branch and info.branch and pin.branch != info.branch:
            errors.append(f"{info.name} branch mismatch manifest={pin.branch} actual={info.branch}")
    if errors:
        for message in errors:
            click.echo(f"- {message}")
        raise click.ClickException("stack verification failed")
    click.echo("stack verification passed")


@main.command("sync")
@click.option("--stack", "stack_name", required=True)
@click.option("--manifest", "manifest_path", type=click.Path(path_type=Path))
def sync_command(stack_name: str, manifest_path: Path | None) -> None:
    repo_root = discover_repo_root(Path.cwd())
    manifest_file = manifest_path or _default_manifest_path(repo_root, stack_name)
    manifest = _require_manifest(manifest_file)
    submodules = _submodule_info_map(repo_root)
    errors: list[str] = []
    for name, pin in manifest.addons.items():
        pin_path = (repo_root / pin.path).resolve()
        info = submodules.get(pin_path)
        if info is None:
            errors.append(f"{name} not found in submodules")
            continue
        if not info.initialized:
            errors.append(f"{name} is not initialized")
    if errors:
        for message in errors:
            click.echo(f"- {message}")
        raise click.ClickException("stack sync failed")
    updated = 0
    for name, pin in manifest.addons.items():
        pin_path = (repo_root / pin.path).resolve()
        info = submodules[pin_path]
        if info.head and pin.ref != info.head:
            pin.ref = info.head
            updated += 1
        if info.branch:
            if pin.branch != info.branch:
                pin.branch = info.branch
                updated += 1
        elif pin.branch is not None:
            pin.branch = None
            updated += 1
    _write_manifest(manifest_file, manifest)
    click.echo(f"Synced {len(manifest.addons)} addons ({updated} updates) to {manifest_file}")


@main.command("promote")
@click.option("--from", "from_stack", required=True)
@click.option("--to", "to_stack", required=True)
@click.option("--from-manifest", "from_manifest", type=click.Path(path_type=Path))
@click.option("--to-manifest", "to_manifest", type=click.Path(path_type=Path))
def promote_command(from_stack: str, to_stack: str, from_manifest: Path | None, to_manifest: Path | None) -> None:
    repo_root = discover_repo_root(Path.cwd())
    source = from_manifest or _default_manifest_path(repo_root, from_stack)
    target = to_manifest or _default_manifest_path(repo_root, to_stack)
    manifest = _require_manifest(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_manifest(target, manifest)
    click.echo(f"Promoted manifest from {source} to {target}")
