from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

import click


def _env(prefix: str, key: str, *, required: bool = False, default: str | None = None) -> str | None:
    value = os.getenv(f"{prefix}_{key}", default)
    if required and not value:
        raise click.ClickException(f"Missing required env var: {prefix}_{key}")
    return value


def _split_modes(raw: str | None) -> set[str]:
    if not raw:
        return set()
    tokens = raw.replace(":", ",").split(",")
    return {token.strip().lower() for token in tokens if token.strip()}


def _run(cmd: list[str], *, cwd: Path | None = None, dry_run: bool = False) -> None:
    click.echo(f"$ {' '.join(cmd)}")
    if dry_run:
        return
    subprocess.run(cmd, cwd=cwd, check=True)


def _ssh_target(host: str, user: str | None) -> str:
    if user:
        return f"{user}@{host}"
    return host


@click.group()
def main() -> None:
    """Prod deploy safety gates (backup + rollback)."""


@main.command("backup")
@click.option("--target", default="opw", show_default=True, help="Prefix for PROD_* env vars")
@click.option("--tag", default=None, help="Optional label to append to snapshot name")
@click.option("--run-tests", is_flag=True, help="Run uv test gate before backup")
@click.option("--dry-run", is_flag=True)
def backup_command(target: str, tag: str | None, run_tests: bool, dry_run: bool) -> None:
    prefix = target.upper()
    host = _env(prefix, "PROD_PROXMOX_HOST", required=True)
    if host is None:
        raise click.ClickException(f"{prefix}_PROD_PROXMOX_HOST is required")
    user = _env(prefix, "PROD_PROXMOX_USER", default="root")
    ctid = _env(prefix, "PROD_CT_ID", required=True)
    storage = _env(prefix, "PROD_BACKUP_STORAGE")
    storage_value = storage or ""
    mode_raw = _env(prefix, "PROD_BACKUP_MODE", default="both")
    snapshot_prefix = _env(prefix, "PROD_SNAPSHOT_PREFIX", default=f"{target}-predeploy")

    modes = _split_modes(mode_raw)
    if not modes or "both" in modes:
        modes = {"snapshot", "vzdump"}

    if "vzdump" in modes and not storage:
        raise click.ClickException(f"{prefix}_PROD_BACKUP_STORAGE is required for vzdump backups")
    if "vzdump" in modes:
        storage_value = storage or ""

    if run_tests:
        _run(["uv", "run", "test", "run", "--json"], dry_run=dry_run)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tag_suffix = f"-{tag}" if tag else ""
    snapshot_name = f"{snapshot_prefix}-{timestamp}{tag_suffix}"

    ssh = _ssh_target(host, user)
    if "snapshot" in modes:
        _run(["ssh", ssh, "pct", "snapshot", str(ctid), snapshot_name], dry_run=dry_run)

    if "vzdump" in modes:
        _run(
            [
                "ssh",
                ssh,
                "vzdump",
                str(ctid),
                "--mode",
                "snapshot",
                "--storage",
                storage_value,
            ],
            dry_run=dry_run,
        )


@main.command("rollback")
@click.option("--target", default="opw", show_default=True, help="Prefix for PROD_* env vars")
@click.option("--snapshot", "snapshot_name", required=True, help="Snapshot name to rollback")
@click.option("--start/--no-start", default=True, show_default=True)
@click.option("--dry-run", is_flag=True)
def rollback_command(target: str, snapshot_name: str, start: bool, dry_run: bool) -> None:
    prefix = target.upper()
    host = _env(prefix, "PROD_PROXMOX_HOST", required=True)
    if host is None:
        raise click.ClickException(f"{prefix}_PROD_PROXMOX_HOST is required")
    user = _env(prefix, "PROD_PROXMOX_USER", default="root")
    ctid = _env(prefix, "PROD_CT_ID", required=True)

    ssh = _ssh_target(host, user)
    _run(["ssh", ssh, "pct", "rollback", str(ctid), snapshot_name], dry_run=dry_run)
    if start:
        _run(["ssh", ssh, "pct", "start", str(ctid)], dry_run=dry_run)


@main.command("list")
@click.option("--target", default="opw", show_default=True, help="Prefix for PROD_* env vars")
@click.option("--dry-run", is_flag=True)
def list_command(target: str, dry_run: bool) -> None:
    prefix = target.upper()
    host = _env(prefix, "PROD_PROXMOX_HOST", required=True)
    if host is None:
        raise click.ClickException(f"{prefix}_PROD_PROXMOX_HOST is required")
    user = _env(prefix, "PROD_PROXMOX_USER", default="root")
    ctid = _env(prefix, "PROD_CT_ID", required=True)

    ssh = _ssh_target(host, user)
    _run(["ssh", ssh, "pct", "listsnapshot", str(ctid)], dry_run=dry_run)
