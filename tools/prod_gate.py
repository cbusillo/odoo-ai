import json
import os
import subprocess
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import click

from tools.environment_files import discover_repo_root, parse_env_file

VALID_BACKUP_MODES = {"both", "none", "snapshot", "vzdump"}


@lru_cache(maxsize=1)
def _repo_env_defaults() -> dict[str, str]:
    repo_root = discover_repo_root(Path.cwd())
    for candidate_path in (repo_root / ".env", repo_root / "platform" / ".env"):
        if candidate_path.exists():
            return parse_env_file(candidate_path)
    return {}


def _env(prefix: str, key: str, *, required: bool = False, default: str | None = None) -> str | None:
    environment_key = f"{prefix}_{key}"
    value = os.getenv(environment_key)
    if value is not None and not value.strip():
        value = None
    if value is None:
        repo_default = _repo_env_defaults().get(environment_key)
        if repo_default is not None and repo_default.strip():
            value = repo_default
    if value is None:
        value = default
    if required and not value:
        raise click.ClickException(f"Missing required env var: {environment_key}")
    return value


def _split_modes(raw: str | None) -> set[str]:
    if not raw:
        return set()
    tokens = raw.replace(":", ",").split(",")
    modes = {token.strip().lower() for token in tokens if token.strip()}
    invalid_modes = sorted(mode for mode in modes if mode not in VALID_BACKUP_MODES)
    if invalid_modes:
        valid_modes = ", ".join(sorted(VALID_BACKUP_MODES))
        invalid_modes_text = ", ".join(invalid_modes)
        raise click.ClickException(
            f"Invalid PROD_BACKUP_MODE value(s): {invalid_modes_text}. Expected one or more of: {valid_modes}"
        )
    return modes


def _run(cmd: list[str], *, cwd: Path | None = None, dry_run: bool = False) -> None:
    click.echo(f"$ {' '.join(cmd)}")
    if dry_run:
        return
    subprocess.run(cmd, cwd=cwd, check=True)


def _run_capture(cmd: list[str], *, dry_run: bool = False) -> str:
    click.echo(f"$ {' '.join(cmd)}")
    if dry_run:
        return ""
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout or ""


def _parse_snapshot_names(output: str) -> list[str]:
    if not output.strip():
        return []
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        payload = None
    names: list[str] = []
    if isinstance(payload, list):
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name") or entry.get("snapshot")
            if isinstance(name, str) and name:
                names.append(name)
        return names
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stripped = stripped.lstrip("`-|> ")
        token = stripped.split()[0]
        if token.lower() in {"name", "snapshot", "snapshots"}:
            continue
        names.append(token)
    return names


def _prune_snapshots(
    *,
    ssh: str,
    ctid: str,
    prefix: str,
    keep: int,
    dry_run: bool,
) -> None:
    if keep <= 0:
        return
    try:
        output = _run_capture(["ssh", ssh, "pct", "listsnapshot", str(ctid)], dry_run=dry_run)
    except subprocess.CalledProcessError:
        click.echo("Snapshot retention skipped: pct listsnapshot failed")
        return
    snapshot_names = _parse_snapshot_names(output)
    if prefix:
        snapshot_names = [name for name in snapshot_names if name.startswith(prefix)]
    snapshot_names = sorted(snapshot_names)
    if len(snapshot_names) <= keep:
        return
    to_remove = snapshot_names[: len(snapshot_names) - keep]
    for snapshot_name in to_remove:
        _run(["ssh", ssh, "pct", "delsnapshot", str(ctid), snapshot_name], dry_run=dry_run)


def _ssh_target(host: str, user: str | None) -> str:
    if user:
        return f"{user}@{host}"
    return host


def _load_target_env(prefix: str) -> tuple[str, str | None, str]:
    host = _env(prefix, "PROD_PROXMOX_HOST", required=True)
    assert host is not None
    user = _env(prefix, "PROD_PROXMOX_USER", default="root")
    ctid = _env(prefix, "PROD_CT_ID", required=True)
    assert ctid is not None
    return host, user, ctid


def _backup_gate_record_id(*, context_name: str, instance_name: str, created_at: datetime) -> str:
    return f"backup-{context_name}-{instance_name}-{created_at.strftime('%Y%m%dT%H%M%SZ')}"


def _build_backup_gate_record(
    *,
    context_name: str,
    instance_name: str,
    created_at: datetime,
    source: str,
    modes: set[str],
    snapshot_name: str,
    storage_name: str,
    proxmox_host: str,
    ctid: str,
    optional_tag: str | None,
) -> dict[str, object]:
    evidence: dict[str, str] = {
        "backup_modes": ",".join(sorted(modes)),
        "ctid": ctid,
        "proxmox_host": proxmox_host,
    }
    if snapshot_name:
        evidence["snapshot"] = snapshot_name
    if storage_name:
        evidence["storage"] = storage_name
    if optional_tag:
        evidence["tag"] = optional_tag
    return {
        "schema_version": 1,
        "record_id": _backup_gate_record_id(
            context_name=context_name,
            instance_name=instance_name,
            created_at=created_at,
        ),
        "context": context_name,
        "instance": instance_name,
        "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
        "required": True,
        "status": "pass",
        "evidence": evidence,
    }


def _resolve_record_directory(record_directory: Path) -> Path:
    repo_root = discover_repo_root(Path.cwd())
    if record_directory.is_absolute():
        return record_directory
    return repo_root / record_directory


def _write_backup_gate_record(*, record_directory: Path, record_payload: dict[str, object]) -> Path:
    resolved_record_directory = _resolve_record_directory(record_directory)
    resolved_record_directory.mkdir(parents=True, exist_ok=True)
    record_id = str(record_payload["record_id"])
    record_path = resolved_record_directory / f"{record_id}.json"
    record_path.write_text(json.dumps(record_payload, indent=2, sort_keys=True), encoding="utf-8")
    return record_path


@click.group()
def main() -> None:
    """Prod deploy safety gates (backup + rollback)."""


@main.command("backup")
@click.option("--target", default="opw", show_default=True, help="Prefix for PROD_* env vars")
@click.option("--tag", default=None, help="Optional label to append to snapshot name")
@click.option("--run-tests", is_flag=True, help="Run uv test gate before backup")
@click.option(
    "--control-plane-record-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Write a control-plane backup gate record JSON file into this directory after a successful backup.",
)
@click.option(
    "--control-plane-instance",
    default="prod",
    show_default=True,
    help="Destination instance name to record in the emitted control-plane backup gate payload.",
)
@click.option("--dry-run", is_flag=True)
def backup_command(
    target: str,
    tag: str | None,
    run_tests: bool,
    control_plane_record_dir: Path | None,
    control_plane_instance: str,
    dry_run: bool,
) -> None:
    prefix = target.upper()
    storage = _env(prefix, "PROD_BACKUP_STORAGE")
    storage_value = storage or ""
    mode_raw = _env(prefix, "PROD_BACKUP_MODE", default="both")
    snapshot_prefix = _env(prefix, "PROD_SNAPSHOT_PREFIX", default=f"{target}-predeploy")
    snapshot_keep_raw = _env(prefix, "PROD_SNAPSHOT_KEEP")
    snapshot_keep = 0
    if snapshot_keep_raw:
        try:
            snapshot_keep = max(int(snapshot_keep_raw), 0)
        except ValueError as exc:
            raise click.ClickException(f"Invalid {prefix}_PROD_SNAPSHOT_KEEP: {snapshot_keep_raw}") from exc

    modes = _split_modes(mode_raw)
    if "none" in modes:
        modes = set()
    elif not modes or "both" in modes:
        modes = {"snapshot", "vzdump"}

    if "vzdump" in modes and not storage:
        raise click.ClickException(f"{prefix}_PROD_BACKUP_STORAGE is required for vzdump backups")
    if "vzdump" in modes:
        storage_value = storage or ""

    if run_tests:
        _run(["uv", "run", "test", "run", "--json", "--stack", target], dry_run=dry_run)

    if not modes and control_plane_record_dir is not None:
        click.echo("control_plane_record_skipped=no_backup_mode")
        return

    if not modes:
        return

    host, user, ctid = _load_target_env(prefix)
    created_at = datetime.utcnow()
    timestamp = created_at.strftime("%Y%m%d-%H%M%S")
    tag_suffix = f"-{tag}" if tag else ""
    snapshot_name = f"{snapshot_prefix}-{timestamp}{tag_suffix}"

    ssh = _ssh_target(host, user)
    if "snapshot" in modes:
        _run(["ssh", ssh, "pct", "snapshot", str(ctid), snapshot_name], dry_run=dry_run)
        if snapshot_keep:
            _prune_snapshots(
                ssh=ssh,
                ctid=ctid,
                prefix=snapshot_prefix or "",
                keep=snapshot_keep,
                dry_run=dry_run,
            )

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

    if control_plane_record_dir is None:
        return
    if dry_run:
        click.echo("control_plane_record_skipped=dry_run")
        return

    if not control_plane_instance.strip():
        raise click.ClickException("--control-plane-instance requires a non-empty value")
    record_payload = _build_backup_gate_record(
        context_name=target,
        instance_name=control_plane_instance.strip(),
        created_at=created_at,
        source="odoo-ai.prod-gate",
        modes=modes,
        snapshot_name=snapshot_name if "snapshot" in modes else "",
        storage_name=storage_value if "vzdump" in modes else "",
        proxmox_host=host,
        ctid=ctid,
        optional_tag=tag,
    )
    record_path = _write_backup_gate_record(
        record_directory=control_plane_record_dir,
        record_payload=record_payload,
    )
    click.echo(f"control_plane_record={record_path}")


@main.command("rollback")
@click.option("--target", default="opw", show_default=True, help="Prefix for PROD_* env vars")
@click.option("--snapshot", "snapshot_name", required=True, help="Snapshot name to rollback")
@click.option("--start/--no-start", default=True, show_default=True)
@click.option("--dry-run", is_flag=True)
def rollback_command(target: str, snapshot_name: str, start: bool, dry_run: bool) -> None:
    prefix = target.upper()
    host, user, ctid = _load_target_env(prefix)

    ssh = _ssh_target(host, user)
    _run(["ssh", ssh, "pct", "rollback", str(ctid), snapshot_name], dry_run=dry_run)
    if start:
        _run(["ssh", ssh, "pct", "start", str(ctid)], dry_run=dry_run)


@main.command("list")
@click.option("--target", default="opw", show_default=True, help="Prefix for PROD_* env vars")
@click.option("--dry-run", is_flag=True)
def list_command(target: str, dry_run: bool) -> None:
    prefix = target.upper()
    host, user, ctid = _load_target_env(prefix)

    ssh = _ssh_target(host, user)
    _run(["ssh", ssh, "pct", "listsnapshot", str(ctid)], dry_run=dry_run)
