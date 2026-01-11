from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import click

try:
    from rich.console import Console
    from rich.prompt import Confirm, Prompt
except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
    raise SystemExit("Missing 'rich'. Run: uv sync") from exc
try:
    import questionary
except ImportError:  # pragma: no cover - optional for arrow-key TUI
    questionary = None

from tools.deployer.command import CommandError, run_process
from tools.deployer.compose_ops import local_compose_command, local_compose_env
from tools.deployer.deploy import _wait_for_local_service, deploy_stack, execute_upgrade
from tools.deployer.health import HealthcheckError
from tools.deployer.helpers import get_git_commit
from tools.deployer.settings import (
    AUTO_INSTALLED_SENTINEL,
    StackSettings,
    discover_repo_root,
    load_stack_settings,
    parse_env_file,
    resolve_addon_dirs,
)
from tools.stack_restore import restore_stack

console = Console()

ALL_TARGET = "all"
ENVS = ("local", "dev", "testing", "prod")
LOCAL_ACTIONS = (
    "up",
    "down",
    "init",
    "restore",
    "restart",
    "upgrade",
    "upgrade-restart",
    "openupgrade",
    "doctor",
    "info",
)
POST_SHIP_ACTIONS = ("none", "restore", "init", "upgrade")
SHIP_ACTIONS = ("ship",)
GATE_ACTIONS = ("gate",)
STATUS_ENVS = ("dev", "testing")
HISTORY_LIMIT = 50
FAVORITES_LIMIT = 6
STATUS_INTERVAL_DEFAULT = 10.0
STATUS_TIMEOUT_DEFAULT = 600.0
POST_DEPLOY_INTERVAL_DEFAULT = 15.0
POST_DEPLOY_TIMEOUT_DEFAULT = 7200.0
WEB_READY_INTERVAL_DEFAULT = 15.0
WEB_READY_TIMEOUT_DEFAULT = 900.0
LOCAL_INFO_SCHEMA_VERSION = 1

OPS_CONFIG_PATH = Path("docker/config/ops.toml")


@dataclass(frozen=True)
class OpsState:
    target: str = "opw"
    env: str = "local"
    action: str = "up"
    deploy: bool = True
    build: bool = False
    no_cache: bool = False
    serial: bool = False  # runtime flag; intentionally not persisted


@dataclass(frozen=True)
class OpsConfig:
    repo_root: Path
    state_path: Path
    coolify_host: str
    coolify_auto_deploy: bool
    targets: dict[str, dict[str, object]]


_OPS_CONFIG: OpsConfig | None = None
_COOLIFY_APP_CACHE: dict[str, str] = {}
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")


def _expand_path(repo_root: Path, raw: str) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(raw))
    path = Path(expanded)
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _load_ops_config() -> OpsConfig:
    global _OPS_CONFIG
    if _OPS_CONFIG is not None:
        return _OPS_CONFIG
    repo_root = _repo_root()
    config_path = repo_root / OPS_CONFIG_PATH
    if not config_path.exists():
        raise click.ClickException(f"Missing ops config: {config_path}")
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))

    state_raw = data.get("state", {})
    state_path_raw = state_raw.get("path", "~/odoo-ai/ops.json")
    state_path = _expand_path(repo_root, state_path_raw)

    coolify_raw = data.get("coolify", {})
    coolify_host = coolify_raw.get("host", "https://coolify.shinycomputers.com")
    coolify_auto = bool(coolify_raw.get("auto_deploy", True))

    targets = data.get("targets", {})
    if not targets:
        raise click.ClickException("ops config has no targets configured")

    _OPS_CONFIG = OpsConfig(
        repo_root=repo_root,
        state_path=state_path,
        coolify_host=coolify_host,
        coolify_auto_deploy=coolify_auto,
        targets=targets,
    )
    return _OPS_CONFIG


def _load_state_payload() -> dict[str, object]:
    config = _load_ops_config()
    if not config.state_path.exists():
        return {}
    try:
        return json.loads(config.state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _normalize_history(history: object) -> list[dict[str, object]]:
    valid_targets = set(_target_names()) | {ALL_TARGET}
    valid_actions = set(LOCAL_ACTIONS) | set(SHIP_ACTIONS) | set(GATE_ACTIONS)
    entries: list[dict[str, object]] = []
    if not isinstance(history, list):
        return entries
    for item in history:
        if not isinstance(item, dict):
            continue
        target = item.get("target")
        env = item.get("env")
        action = item.get("action")
        deploy = item.get("deploy", False)
        build = item.get("build", False)
        no_cache = item.get("no_cache", False)
        if target not in valid_targets or env not in ENVS or action not in valid_actions:
            continue
        if env == "local" and action not in LOCAL_ACTIONS:
            continue
        if env in ("dev", "testing") and action not in SHIP_ACTIONS:
            continue
        if env == "prod" and action not in (SHIP_ACTIONS + GATE_ACTIONS):
            continue
        entries.append(
            {
                "target": target,
                "env": env,
                "action": action,
                "deploy": bool(deploy),
                "build": bool(build),
                "no_cache": bool(no_cache),
                "ts": item.get("ts"),
            }
        )
    return entries


def _write_state_payload(payload: dict[str, object]) -> None:
    config = _load_ops_config()
    config.state_path.parent.mkdir(parents=True, exist_ok=True)
    config.state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _update_payload_with_state(payload: dict[str, object], state: OpsState) -> dict[str, object]:
    updated = dict(payload)
    updated.pop("serial", None)
    updated.update(
        {
            "target": state.target,
            "env": state.env,
            "action": state.action,
            "deploy": state.deploy,
            "build": state.build,
            "no_cache": state.no_cache,
        }
    )
    return updated


def _load_state() -> OpsState:
    config = _load_ops_config()
    default_target = sorted(config.targets.keys())[0]
    default_deploy = True
    payload = _load_state_payload()
    valid_targets = set(config.targets.keys()) | {ALL_TARGET}
    target_raw = payload.get("target")
    env_raw = payload.get("env")
    action_raw = payload.get("action")
    target = target_raw if isinstance(target_raw, str) and target_raw in valid_targets else default_target
    env = env_raw if isinstance(env_raw, str) and env_raw in ENVS else OpsState.env
    action = action_raw if isinstance(action_raw, str) and action_raw else OpsState.action
    deploy_raw = payload.get("deploy", default_deploy)
    deploy = bool(deploy_raw)
    build_raw = payload.get("build", OpsState.build)
    build = bool(build_raw)
    no_cache_raw = payload.get("no_cache", OpsState.no_cache)
    no_cache = bool(no_cache_raw)
    return OpsState(target=target, env=env, action=action, deploy=deploy, build=build, no_cache=no_cache)


def _save_state(state: OpsState) -> None:
    payload = _load_state_payload()
    updated = _update_payload_with_state(payload, state)
    _write_state_payload(updated)


def _record_history(state: OpsState) -> None:
    payload = _load_state_payload()
    updated = _update_payload_with_state(payload, state)
    history = _normalize_history(updated.get("history"))
    entry = {
        "target": state.target,
        "env": state.env,
        "action": state.action,
        "deploy": state.deploy,
        "build": state.build,
        "no_cache": state.no_cache,
        "ts": datetime.now(UTC).isoformat(),
    }
    updated["history"] = [entry, *history][:HISTORY_LIMIT]
    _write_state_payload(updated)


def _favorite_states(limit: int = FAVORITES_LIMIT) -> list[OpsState]:
    payload = _load_state_payload()
    history = _normalize_history(payload.get("history"))
    if not history:
        return []
    scores: dict[tuple[str, str, str, bool, bool, bool], float] = {}
    for index, entry in enumerate(history):
        weight = 1.0 / (index + 1)
        key = (
            str(entry["target"]),
            str(entry["env"]),
            str(entry["action"]),
            bool(entry.get("deploy", False)),
            bool(entry.get("build", False)),
            bool(entry.get("no_cache", False)),
        )
        scores[key] = scores.get(key, 0.0) + weight
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    favorites: list[OpsState] = []
    for (target, env, action, deploy, build, no_cache), _score in ranked[:limit]:
        favorites.append(OpsState(target=target, env=env, action=action, deploy=deploy, build=build, no_cache=no_cache))
    return favorites


def _favorite_label(state: OpsState) -> str:
    label = f"{state.target} {state.env} {state.action}"
    if state.action == "ship" and state.env in ("dev", "testing") and state.deploy:
        label = f"{label} +deploy"
    if state.env == "local" and state.action in ("up", "init", "restore"):
        if state.build:
            label = f"{label} +build"
            if state.no_cache:
                label = f"{label} +no-cache"
    return label


def _render_cli_command(
    *,
    target: str,
    env: str,
    action: str,
    deploy: bool,
    wait_deploy: bool,
    serial: bool,
    build: bool,
    no_cache: bool,
    post_action: str | None,
    dry_run: bool,
) -> str:
    command_parts: list[str] = ["uv", "run", "ops"]
    if action in LOCAL_ACTIONS:
        command_parts.extend(["local", action, target])
        if build:
            command_parts.append("--build")
            if no_cache:
                command_parts.append("--no-cache")
        if dry_run:
            command_parts.append("--dry-run")
        return shlex.join(command_parts)

    if action == "ship":
        command_parts.extend(["ship", env, target])
        if not deploy:
            command_parts.append("--no-deploy")
        if not wait_deploy:
            command_parts.append("--no-wait")
        if serial:
            command_parts.append("--serial")
        if post_action and post_action != "none":
            command_parts.extend(["--after", post_action])
        if dry_run:
            command_parts.append("--dry-run")
        return shlex.join(command_parts)

    if action == "gate":
        command_parts.extend(["gate", target])
        if dry_run:
            command_parts.append("--dry-run")
        return shlex.join(command_parts)

    return shlex.join(command_parts)


def _run(cmd: Sequence[str], *, dry_run: bool = False, display: bool = True) -> None:
    if display:
        console.print(f"$ {' '.join(cmd)}")
    if dry_run:
        return
    subprocess.run(list(cmd), check=True)


def _repo_root() -> Path:
    return discover_repo_root(Path.cwd())


def _repo_env(repo_root: Path) -> dict[str, str]:
    env_path = repo_root / ".env"
    if not env_path.exists():
        return {}
    return parse_env_file(env_path)


def _env_value(key: str, *, default: str | None = None) -> str | None:
    if key in os.environ:
        return os.environ[key]
    repo_env = _repo_env(_repo_root())
    return repo_env.get(key, default)


def _target_names() -> list[str]:
    config = _load_ops_config()
    return sorted(config.targets.keys())


def _target_choices() -> list[str]:
    return [*_target_names(), ALL_TARGET]


def _target_config(target: str) -> dict[str, object]:
    config = _load_ops_config()
    try:
        return dict(config.targets[target])
    except KeyError as error:
        raise click.ClickException(f"Unknown target: {target}") from error


def _resolve_local_stack(target: str) -> str:
    target_cfg = _target_config(target)
    local_stack = target_cfg.get("local_stack")
    if isinstance(local_stack, str) and local_stack:
        return local_stack
    return f"{target}-local"


def _resolve_local_env_file(target: str) -> Path:
    target_cfg = _target_config(target)
    env_file = target_cfg.get("local_env_file")
    if isinstance(env_file, str) and env_file:
        return _expand_path(_load_ops_config().repo_root, env_file)
    template = f"docker/config/{target}-local.env"
    return _expand_path(_load_ops_config().repo_root, template)


def _resolve_branch(target: str, env: str) -> str:
    target_cfg = _target_config(target)
    branches = target_cfg.get("branches", {})
    if isinstance(branches, dict):
        value = branches.get(env)
        if isinstance(value, str) and value:
            return value
    return f"{target}-{env}"


def _resolve_coolify_app(target: str, env: str) -> str | None:
    target_cfg = _target_config(target)
    coolify = target_cfg.get("coolify", {})
    if isinstance(coolify, dict):
        value = coolify.get(env)
        if isinstance(value, str) and value:
            return value
    if env in ("dev", "testing", "prod"):
        return f"{target}-{env}"
    return None


def _stack_env_path(stack_name: str) -> Path:
    return _load_ops_config().repo_root / "docker" / "config" / f"{stack_name}.env"


def _stack_env_exists(stack_name: str) -> bool:
    return _stack_env_path(stack_name).exists()


def _targets_for(target: str) -> list[str]:
    if target == ALL_TARGET:
        return _target_names()
    return [target]


def _confirm_dirty() -> bool:
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True)
    if not result.stdout.strip():
        return True
    return Confirm.ask("Working tree is dirty. Continue anyway?", default=False)


def _looks_like_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value))


def _coolify_request(path: str, *, method: str = "GET", body: dict[str, object] | None = None) -> object:
    config = _load_ops_config()
    host = _env_value("COOLIFY_HOST", default=config.coolify_host)
    token = _env_value("COOLIFY_TOKEN")
    if not host or not token:
        raise click.ClickException("COOLIFY_HOST/COOLIFY_TOKEN not set; cannot talk to Coolify.")
    url = f"{host.rstrip('/')}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def _coolify_list_apps() -> list[dict[str, object]]:
    payload = _coolify_request("/api/v1/applications")
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        apps = payload.get("applications")
        if isinstance(apps, list):
            return [item for item in apps if isinstance(item, dict)]
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    raise click.ClickException("Unexpected Coolify applications response.")


def _coolify_update_application(app_ref: str, payload: dict[str, object]) -> None:
    app_uuid = _coolify_find_app_uuid(app_ref)
    _coolify_request(f"/api/v1/applications/{app_uuid}", method="PATCH", body=payload)


def _coolify_find_app_uuid(app_ref: str) -> str:
    if _looks_like_uuid(app_ref):
        return app_ref
    cached = _COOLIFY_APP_CACHE.get(app_ref)
    if cached:
        return cached
    apps = _coolify_list_apps()
    matches = [app for app in apps if str(app.get("name")) == app_ref]
    if not matches:
        raise click.ClickException(f"Coolify app '{app_ref}' not found.")
    if len(matches) > 1:
        choices = ", ".join(str(app.get("uuid") or app.get("id")) for app in matches)
        raise click.ClickException(f"Multiple Coolify apps named '{app_ref}': {choices}")
    match = matches[0]
    uuid = match.get("uuid") or match.get("id")
    if not uuid:
        raise click.ClickException(f"Coolify app '{app_ref}' has no uuid/id in API response.")
    uuid_str = str(uuid)
    _COOLIFY_APP_CACHE[app_ref] = uuid_str
    return uuid_str


def _coolify_deploy(app_ref: str, *, dry_run: bool) -> None:
    config = _load_ops_config()
    host = _env_value("COOLIFY_HOST", default=config.coolify_host)
    token = _env_value("COOLIFY_TOKEN")
    if not host or not token:
        raise click.ClickException("COOLIFY_HOST/COOLIFY_TOKEN not set; cannot trigger deploy.")
    app_uuid = _coolify_find_app_uuid(app_ref)
    url = f"{host.rstrip('/')}/api/v1/applications/{app_uuid}/start"
    if dry_run:
        console.print(f"$ POST {url}")
        return
    req = urllib.request.Request(url, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as response:
        response.read()


def _coolify_latest_deployment(app_ref: str) -> dict[str, object] | None:
    app_uuid = _coolify_find_app_uuid(app_ref)
    payload = _coolify_request(f"/api/v1/deployments/applications/{app_uuid}")
    deployments: list[dict[str, object]] = []
    if isinstance(payload, list):
        deployments = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        for key in ("data", "deployments"):
            data = payload.get(key)
            if isinstance(data, list):
                deployments = [item for item in data if isinstance(item, dict)]
                break
    if not deployments:
        return None

    def _sort_key(dep: dict[str, object]) -> tuple[int, float]:
        dep_id = dep.get("id")
        numeric_id = int(dep_id) if isinstance(dep_id, int) else 0
        created = dep.get("created_at") or dep.get("createdAt")
        created_ts = 0.0
        if isinstance(created, str) and created:
            created_value = created.replace("Z", "+00:00")
            try:
                created_ts = datetime.fromisoformat(created_value).timestamp()
            except ValueError:
                created_ts = 0.0
        return numeric_id, created_ts

    return max(deployments, key=_sort_key)


def _normalize_deployment_logs(raw_logs: object) -> list[str]:
    if isinstance(raw_logs, str):
        try:
            parsed = json.loads(raw_logs)
        except json.JSONDecodeError:
            return [raw_logs]
        raw_logs = parsed
    if not isinstance(raw_logs, list):
        return []
    outputs: list[str] = []
    for entry in raw_logs:
        if not isinstance(entry, dict):
            continue
        output = entry.get("output")
        if isinstance(output, str) and output:
            outputs.append(output)
    return outputs


def _coolify_deployment_logs(app_ref: str) -> list[str]:
    deployment = _coolify_latest_deployment(app_ref)
    if not deployment:
        return []
    candidates = []
    for key in ("deployment_uuid", "uuid", "id"):
        value = deployment.get(key)
        if value:
            candidates.append(str(value))
    for candidate in candidates:
        try:
            payload = _coolify_request(f"/api/v1/deployments/{candidate}")
        except urllib.error.HTTPError:
            continue
        except urllib.error.URLError:
            continue
        if not isinstance(payload, dict):
            continue
        outputs = _normalize_deployment_logs(payload.get("logs"))
        if outputs:
            return outputs
    return []


def _coolify_env_value(app_ref: str, key: str) -> str | None:
    app_uuid = _coolify_find_app_uuid(app_ref)
    try:
        payload = _coolify_request(f"/api/v1/applications/{app_uuid}/envs")
    except urllib.error.HTTPError:
        return None
    except urllib.error.URLError:
        return None
    if not isinstance(payload, list):
        return None
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        if entry.get("key") != key:
            continue
        if entry.get("is_preview"):
            continue
        value = entry.get("real_value") or entry.get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _wait_for_web_ready(entry: str, env: str, app_ref: str) -> None:
    base_url = _coolify_env_value(app_ref, "ODOO_BASE_URL")
    if not base_url:
        console.print(f"{entry} {env}: ODOO_BASE_URL missing; skipping web readiness wait.")
        return
    url = f"{base_url.rstrip('/')}/web/login"
    console.print(f"{entry} {env}: waiting for web login ({url})...")
    start = time.monotonic()
    while True:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        except (OSError, TimeoutError, urllib.error.URLError):
            status = None
        if status == 200:
            console.print(f"{entry} {env}: [green]web login ready[/green]")
            return
        if time.monotonic() - start > WEB_READY_TIMEOUT_DEFAULT:
            raise click.ClickException(f"Timed out waiting for {entry} {env} web login to be ready.")
        time.sleep(WEB_READY_INTERVAL_DEFAULT)


def _post_deploy_success_marker(post_action: str) -> str:
    if post_action == "restore":
        return "Upstream overwrite completed successfully."
    if post_action == "init":
        return "Bootstrap completed successfully."
    if post_action == "upgrade":
        return "Addon update completed successfully."
    return ""


def _wait_for_post_deploy(entry: str, env: str, app_ref: str, post_action: str) -> None:
    marker = _post_deploy_success_marker(post_action)
    if not marker:
        return
    console.print(f"{entry} {env}: waiting for post-deploy {post_action} to finish...")
    start = time.monotonic()
    while True:
        outputs = _coolify_deployment_logs(app_ref)
        if any(marker in output for output in outputs):
            console.print(f"{entry} {env}: [green]{post_action} completed[/green]")
            return
        if time.monotonic() - start > POST_DEPLOY_TIMEOUT_DEFAULT:
            raise click.ClickException(f"Timed out waiting for {entry} {env} post-deploy {post_action} to finish.")
        time.sleep(POST_DEPLOY_INTERVAL_DEFAULT)


def _deployment_key(deployment: dict[str, object] | None) -> str:
    if not deployment:
        return ""
    dep_id = deployment.get("uuid") or deployment.get("id") or deployment.get("deployment_uuid")
    created = deployment.get("created_at") or deployment.get("createdAt") or ""
    return f"{dep_id}:{created}"


def _deployment_color(status: str) -> str:
    success = {"success", "succeeded", "finished", "completed"}
    failed = {"failed", "error", "canceled", "cancelled"}
    running = {"running", "in_progress", "queued", "starting", "deploying", "building", "pending", "processing"}
    if status in success:
        return "green"
    if status in failed:
        return "red"
    if status in running:
        return "yellow"
    return "yellow"


def _render_status(status: str, color: str) -> str:
    label = status or "unknown"
    if color == "green":
        return f"[green]{label}[/green]"
    if color == "red":
        return f"[red]{label}[/red]"
    if color == "yellow":
        return f"[yellow]{label}[/yellow]"
    return label


def _print_status(entry: str, env: str, app_ref: str) -> None:
    deployment = _coolify_latest_deployment(app_ref)
    if not deployment:
        console.print(f"{entry} {env}: [yellow]no deployments found[/yellow]")
        return
    raw_status = str(deployment.get("status") or "unknown").lower()
    color = _deployment_color(raw_status)
    console.print(f"{entry} {env}: {_render_status(raw_status, color)}")


def _wait_for_status(
    entry: str,
    env: str,
    app_ref: str,
    *,
    interval: float,
    timeout: float,
    expected_key: str | None = None,
) -> bool:
    start = time.monotonic()
    last_status: str | None = None
    waiting_notice = False
    while True:
        deployment = _coolify_latest_deployment(app_ref)
        key = _deployment_key(deployment)
        if expected_key and (not key or key == expected_key):
            if not waiting_notice:
                console.print(f"{entry} {env}: [yellow]waiting for deployment to start...[/yellow]")
                waiting_notice = True
            if time.monotonic() - start > timeout:
                raise click.ClickException(f"Timed out waiting for {entry} {env} to start.")
            time.sleep(interval)
            continue
        raw_status = str((deployment or {}).get("status") or "unknown").lower()
        if raw_status != last_status:
            color = _deployment_color(raw_status)
            console.print(f"{entry} {env}: {_render_status(raw_status, color)}")
            last_status = raw_status
        color = _deployment_color(raw_status)
        if color in {"green", "red"}:
            return color == "green"
        if time.monotonic() - start > timeout:
            raise click.ClickException(f"Timed out waiting for {entry} {env} to finish.")
        time.sleep(interval)


def _wait_for_deploy(entry: str, env: str, before_keys: dict[str, str]) -> None:
    app_ref = _resolve_coolify_app(entry, env)
    if not app_ref:
        console.print(f"No Coolify app ref for {entry} {env}; skipping wait.")
        return
    expected = before_keys.get(entry)
    success = _wait_for_status(
        entry,
        env,
        app_ref,
        interval=STATUS_INTERVAL_DEFAULT,
        timeout=STATUS_TIMEOUT_DEFAULT,
        expected_key=expected,
    )
    if success:
        console.print(f"{entry} {env}: [green]deploy succeeded[/green]")
    else:
        raise click.ClickException(f"{entry} {env} deploy failed.")


def _run_local_compose(settings: StackSettings, extra: Sequence[str], *, dry_run: bool) -> None:
    command = local_compose_command(settings, extra)
    if dry_run:
        console.print(f"$ {' '.join(command)}")
        return
    run_process(command, cwd=settings.repo_root, env=local_compose_env(settings))


def _docker_command_prefix(settings: StackSettings) -> list[str]:
    compose_command = list(settings.compose_command)
    if not compose_command:
        return ["docker"]
    if "compose" in compose_command:
        compose_index = compose_command.index("compose")
        if compose_index > 0:
            return compose_command[:compose_index]
    binary_name = Path(compose_command[0]).name
    if binary_name == "podman-compose":
        return ["podman"]
    return ["docker"]


def _docker_command(settings: StackSettings, extra: Sequence[str]) -> list[str]:
    command = _docker_command_prefix(settings)
    command += list(extra)
    return command


def _compose_project_container_ids(settings: StackSettings) -> list[str]:
    try:
        result = run_process(
            local_compose_command(settings, ["ps", "--all", "-q"]),
            cwd=settings.repo_root,
            env=local_compose_env(settings),
            capture_output=True,
            check=False,
        )
    except OSError:
        return []
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def _volume_names_for_container_ids(settings: StackSettings, container_ids: Sequence[str]) -> set[str]:
    if not container_ids:
        return set()
    try:
        inspect_result = run_process(
            _docker_command(settings, ["inspect", *container_ids]),
            env=local_compose_env(settings),
            capture_output=True,
            check=False,
        )
    except OSError:
        return set()
    if inspect_result.returncode != 0 or not inspect_result.stdout:
        return set()
    try:
        container_data = json.loads(inspect_result.stdout)
    except json.JSONDecodeError:
        return set()
    if not isinstance(container_data, list):
        return set()
    volume_names: set[str] = set()
    for container in container_data:
        if not isinstance(container, dict):
            continue
        mounts = container.get("Mounts")
        if not isinstance(mounts, list):
            continue
        for mount in mounts:
            if not isinstance(mount, dict):
                continue
            if mount.get("Type") != "volume":
                continue
            volume_name = mount.get("Name")
            if isinstance(volume_name, str) and volume_name:
                volume_names.add(volume_name)
    return volume_names


def _anonymous_volume_names(settings: StackSettings, volume_names: Iterable[str]) -> list[str]:
    anonymous_volume_names: set[str] = set()
    for volume_name in sorted(set(volume_names)):
        try:
            inspect_result = run_process(
                _docker_command(settings, ["volume", "inspect", volume_name]),
                env=local_compose_env(settings),
                capture_output=True,
                check=False,
            )
        except OSError:
            break
        if inspect_result.returncode != 0 or not inspect_result.stdout:
            continue
        try:
            volume_data = json.loads(inspect_result.stdout)
        except json.JSONDecodeError:
            continue
        if not isinstance(volume_data, list):
            continue
        for volume in volume_data:
            if not isinstance(volume, dict):
                continue
            name = volume.get("Name")
            if not isinstance(name, str) or not name:
                continue
            labels = volume.get("Labels")
            if not isinstance(labels, dict):
                continue
            if "com.docker.volume.anonymous" in labels:
                anonymous_volume_names.add(name)
    return sorted(anonymous_volume_names)


def _project_labeled_anonymous_volumes(settings: StackSettings) -> set[str]:
    try:
        list_result = run_process(
            _docker_command(
                settings,
                [
                    "volume",
                    "ls",
                    "-q",
                    "--filter",
                    f"label=com.docker.compose.project={settings.compose_project}",
                    "--filter",
                    "label=com.docker.volume.anonymous",
                ],
            ),
            env=local_compose_env(settings),
            capture_output=True,
            check=False,
        )
    except OSError:
        return set()
    return {line.strip() for line in (list_result.stdout or "").splitlines() if line.strip()}


def _remove_anonymous_volumes(settings: StackSettings, candidate_volume_names: set[str]) -> None:
    volume_names = set(candidate_volume_names)
    volume_names.update(_project_labeled_anonymous_volumes(settings))
    if not volume_names:
        return
    removable = _anonymous_volume_names(settings, volume_names)
    if removable:
        try:
            run_process(
                _docker_command(settings, ["volume", "rm", *removable]),
                env=local_compose_env(settings),
                check=False,
            )
        except OSError:
            return


def _format_update_modules(modules: tuple[str, ...]) -> str:
    if modules == (AUTO_INSTALLED_SENTINEL,):
        return "AUTO"
    return ",".join(modules) if modules else "none"


def _clean_optional_value(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _local_info_payload(settings: StackSettings) -> dict[str, object]:
    addons_dirs = resolve_addon_dirs(settings.environment, settings.repo_root)
    addons_paths = [str(path) for path in addons_dirs]
    project_name = _clean_optional_value(settings.environment.get("ODOO_PROJECT_NAME"))
    db_name = _clean_optional_value(settings.environment.get("ODOO_DB_NAME"))
    return {
        "schema_version": LOCAL_INFO_SCHEMA_VERSION,
        "repo_root": str(settings.repo_root),
        "stack_name": settings.name,
        "env_file": str(settings.env_file),
        "source_env_file": str(settings.source_env_file),
        "compose_files": [str(path) for path in settings.compose_files],
        "compose_project": settings.compose_project,
        "project_name": project_name,
        "state_root": str(settings.state_root),
        "db_name": db_name,
        "addons_path": addons_paths,
        "compose_command": list(settings.compose_command),
        "docker_context": str(settings.docker_context),
        "services": list(settings.services),
        "script_runner_service": settings.script_runner_service,
        "odoo_bin_path": settings.odoo_bin_path,
        "image_variable_name": settings.image_variable_name,
    }


def _emit_local_info(payloads: list[dict[str, object]], *, json_output: bool) -> None:
    if json_output:
        output: object = payloads[0] if len(payloads) == 1 else payloads
        click.echo(json.dumps(output, indent=2))
        return
    for payload in payloads:
        stack_name = payload.get("stack_name")
        if stack_name:
            console.print(f"Local stack: [bold]{stack_name}[/bold]")
        for key, value in payload.items():
            if key == "stack_name":
                continue
            if isinstance(value, list):
                rendered = ", ".join(str(item) for item in value)
            else:
                rendered = str(value)
            console.print(f"  {key}: {rendered}")


def _run_local_restart(settings: StackSettings, *, dry_run: bool) -> None:
    services = ["web"] if "web" in settings.services else list(settings.services)
    _run_local_compose(settings, ["restart", *services], dry_run=dry_run)


def _ensure_local_service(settings: StackSettings, service: str, *, dry_run: bool) -> None:
    if service not in settings.services:
        return
    _run_local_compose(settings, ["up", "-d", service], dry_run=dry_run)


def _run_local_upgrade(settings: StackSettings, *, dry_run: bool) -> None:
    modules = _format_update_modules(settings.update_modules)
    console.print(f"Upgrading local modules: {modules}")
    if dry_run:
        return
    _ensure_local_service(settings, settings.script_runner_service, dry_run=dry_run)
    execute_upgrade(settings, settings.update_modules, remote=False)


def _run_local_openupgrade(settings: StackSettings, *, dry_run: bool) -> None:
    def _run_compose_with_retry(arguments: list[str], *, attempts: int = 3) -> None:
        last_error: CommandError | None = None
        for attempt_number in range(1, max(1, attempts) + 1):
            try:
                _run_local_compose(settings, arguments, dry_run=False)
                return
            except CommandError as exc:
                last_error = exc
                if attempt_number >= attempts:
                    raise
                delay_seconds = 2 ** (attempt_number - 1)
                console.print(
                    f"Retrying docker compose command (attempt {attempt_number + 1}/{attempts}) after {delay_seconds}s due to transient failure...",
                )
                time.sleep(delay_seconds)
        if last_error is None:
            raise RuntimeError("compose retry exhausted without a captured error")
        raise last_error

    openupgrade_command = [
        "exec",
        "-T",
        settings.script_runner_service,
        "python3",
        "/volumes/scripts/run_openupgrade.py",
        "--force",
        "--reset-versions",
    ]
    if dry_run:
        console.print(f"$ {' '.join(local_compose_command(settings, openupgrade_command))}")
        return
    # Retrying OpenUpgrade execution itself is unsafe (non-idempotent). We only
    # apply a small retry to the surrounding docker compose lifecycle commands
    # because Docker Desktop can occasionally return transient 5xx errors.
    _run_compose_with_retry(["up", "-d", settings.script_runner_service])
    if "web" in settings.services:
        _run_compose_with_retry(["stop", "web"])
        try:
            _run_compose_with_retry(["up", "-d", settings.script_runner_service])
            _wait_for_local_service(settings, settings.script_runner_service)
            _run_local_compose(settings, openupgrade_command, dry_run=False)
        finally:
            _run_compose_with_retry(["up", "-d", "web"])
        return
    _run_compose_with_retry(["up", "-d", settings.script_runner_service])
    _wait_for_local_service(settings, settings.script_runner_service)
    _run_local_compose(settings, openupgrade_command, dry_run=False)


def _run_local_action(
    target: str,
    action: str,
    *,
    dry_run: bool,
    build: bool,
    no_cache: bool,
    json_output: bool,
) -> None:
    if action == "info":
        payloads: list[dict[str, object]] = []
        for entry in _targets_for(target):
            stack = _resolve_local_stack(entry)
            env_file_path = _resolve_local_env_file(entry)
            settings = load_stack_settings(stack, env_file_path)
            payloads.append(_local_info_payload(settings))
        _emit_local_info(payloads, json_output=json_output)
        return
    no_cache_used = False
    for entry in _targets_for(target):
        stack = _resolve_local_stack(entry)
        env_file_path = _resolve_local_env_file(entry)
        if action == "down":
            settings = load_stack_settings(stack, env_file_path)
            if dry_run:
                _run_local_compose(settings, ["down", "--remove-orphans"], dry_run=True)
                console.print(f"[dry-run] {entry} local down cleanup (anonymous volumes)")
                continue
            container_ids = _compose_project_container_ids(settings)
            candidate_volume_names = _volume_names_for_container_ids(settings, container_ids)
            _run_local_compose(settings, ["down", "--remove-orphans"], dry_run=False)
            _remove_anonymous_volumes(settings, candidate_volume_names)
            console.print(f"{entry} local down complete")
            continue
        if action == "doctor":
            settings = load_stack_settings(stack, env_file_path)
            _print_local_doctor(entry, settings)
            continue
        if action == "restart":
            settings = load_stack_settings(stack, env_file_path)
            _run_local_restart(settings, dry_run=dry_run)
            console.print(f"{entry} local restart complete")
            continue
        if action == "upgrade":
            settings = load_stack_settings(stack, env_file_path)
            _run_local_upgrade(settings, dry_run=dry_run)
            console.print(f"{entry} local upgrade complete")
            continue
        if action == "upgrade-restart":
            settings = load_stack_settings(stack, env_file_path)
            _run_local_upgrade(settings, dry_run=dry_run)
            _run_local_restart(settings, dry_run=dry_run)
            console.print(f"{entry} local upgrade + restart complete")
            continue
        if action == "openupgrade":
            settings = load_stack_settings(stack, env_file_path)
            _run_local_openupgrade(settings, dry_run=dry_run)
            console.print(f"{entry} local openupgrade complete")
            continue
        settings = load_stack_settings(stack, env_file_path)
        if dry_run:
            extras: list[str] = []
            if build:
                extras.append("build")
                if no_cache and not no_cache_used:
                    extras.append("no-cache")
                    no_cache_used = True
            if action in ("restore", "init"):
                extras.append(action)
            suffix = f" ({', '.join(extras)})" if extras else ""
            console.print(f"[dry-run] {entry} local {action}{suffix}")
            continue
        if build:
            build_args = ["build"]
            if no_cache and not no_cache_used:
                build_args.append("--no-cache")
            _run_local_compose(settings, build_args, dry_run=False)
            if no_cache and not no_cache_used:
                no_cache_used = True
        if action in ("restore", "init"):
            restore_stack(stack, env_file=env_file_path, bootstrap_only=action == "init")
            console.print(f"{entry} local {action} complete")
            continue
        commit = get_git_commit(settings.repo_root)
        image_reference = f"{settings.registry_image}:{settings.name}-{commit[:7]}"
        try:
            deploy_stack(settings, image_reference, remote=False, commit=commit)
        except HealthcheckError as error:
            raise click.ClickException(str(error)) from error
        console.print(f"{entry} local {action} complete")


def _run_prod_gate(target: str, *, dry_run: bool, skip_tests: bool) -> None:
    cmd = ["uv", "run", "prod-gate", "backup", "--target", target]
    if not skip_tests:
        cmd.append("--run-tests")
    _run(cmd, dry_run=dry_run)


def _run_test_gate(target: str, *, dry_run: bool, skip_tests: bool) -> None:
    if skip_tests:
        return
    cmd = ["uv", "run", "test", "run", "--json", "--stack", target]
    _run(cmd, dry_run=dry_run)


def _run_ship(
    target: str,
    env: str,
    *,
    deploy: bool,
    wait_deploy: bool,
    serial: bool,
    post_action: str | None,
    dry_run: bool,
    skip_tests: bool,
    require_confirm: bool,
) -> None:
    if env not in ("dev", "testing", "prod"):
        raise click.ClickException("Ship is only valid for dev/testing/prod environments.")
    if env == "prod":
        if require_confirm and not Confirm.ask("Ship to prod?", default=False):
            return
        for entry in _targets_for(target):
            _run_prod_gate(entry, dry_run=dry_run, skip_tests=skip_tests)
    elif env == "testing":
        for entry in _targets_for(target):
            _run_test_gate(entry, dry_run=dry_run, skip_tests=skip_tests)
    if not _confirm_dirty():
        return

    auto_deploy = _load_ops_config().coolify_auto_deploy
    wait_enabled = wait_deploy and (deploy or auto_deploy) and env in ("dev", "testing", "prod")
    if post_action:
        if post_action in {"restore", "init"} and env not in ("dev", "testing"):
            raise click.ClickException("Post-deploy restore/init is only supported for dev/testing.")
        if post_action == "upgrade" and env not in ("dev", "testing", "prod"):
            raise click.ClickException("Post-deploy upgrade is only supported for dev/testing/prod.")
        if not wait_enabled:
            raise click.ClickException("Post-deploy actions require --wait.")
        if not (deploy or auto_deploy):
            raise click.ClickException("Post-deploy actions require a deploy (auto-deploy or --deploy).")
    token = _env_value("COOLIFY_TOKEN") if wait_enabled else None
    if wait_enabled and not token:
        console.print("COOLIFY_TOKEN not set; skipping deploy wait.")
        wait_enabled = False

    before_keys: dict[str, str] = {}
    if wait_enabled:
        for entry in _targets_for(target):
            app_ref = _resolve_coolify_app(entry, env)
            if not app_ref:
                continue
            before_keys[entry] = _deployment_key(_coolify_latest_deployment(app_ref))

    post_apps: list[str] = []
    if post_action:
        command = "python3 /volumes/scripts/restore_from_upstream.py"
        if post_action == "init":
            command = f"{command} --bootstrap-only"
        elif post_action == "upgrade":
            command = f"{command} --update-only"
        for entry in _targets_for(target):
            app_ref = _resolve_coolify_app(entry, env)
            if not app_ref:
                console.print(f"No Coolify app ref for {entry} {env}; skipping post-deploy {post_action}.")
                continue
            _coolify_update_application(
                app_ref,
                {
                    "post_deployment_command": command,
                    "post_deployment_command_container": "script-runner",
                },
            )
            post_apps.append(app_ref)

    entries = _targets_for(target)
    try:
        if serial and env in ("dev", "testing", "prod"):
            for entry in entries:
                branch = _resolve_branch(entry, env)
                _run(["git", "push", "origin", f"HEAD:{branch}"], dry_run=dry_run)
                app_ref = None
                if deploy or wait_enabled or post_action:
                    app_ref = _resolve_coolify_app(entry, env)
                if deploy:
                    if not app_ref:
                        console.print(f"No Coolify app ref for {entry} {env}; skipping deploy.")
                    else:
                        _coolify_deploy(app_ref, dry_run=dry_run)
                if wait_enabled:
                    if not app_ref:
                        console.print(f"No Coolify app ref for {entry} {env}; skipping wait.")
                    else:
                        _wait_for_deploy(entry, env, before_keys)
                        if post_action:
                            _wait_for_post_deploy(entry, env, app_ref, post_action)
                            _wait_for_web_ready(entry, env, app_ref)
        else:
            for entry in entries:
                branch = _resolve_branch(entry, env)
                _run(["git", "push", "origin", f"HEAD:{branch}"], dry_run=dry_run)
            if deploy and env in ("dev", "testing", "prod"):
                for entry in entries:
                    app_ref = _resolve_coolify_app(entry, env)
                    if not app_ref:
                        console.print(f"No Coolify app ref for {entry} {env}; skipping deploy.")
                        continue
                    _coolify_deploy(app_ref, dry_run=dry_run)

            if wait_enabled:
                for entry in entries:
                    _wait_for_deploy(entry, env, before_keys)
                    if post_action:
                        app_ref = _resolve_coolify_app(entry, env)
                        if not app_ref:
                            console.print(f"No Coolify app ref for {entry} {env}; skipping post-deploy wait.")
                            continue
                        _wait_for_post_deploy(entry, env, app_ref, post_action)
                        _wait_for_web_ready(entry, env, app_ref)
    finally:
        if post_apps:
            for app_ref in post_apps:
                _coolify_update_application(
                    app_ref,
                    {
                        "post_deployment_command": "true",
                        "post_deployment_command_container": "script-runner",
                    },
                )


def _run_gate(target: str, *, dry_run: bool, skip_tests: bool, require_confirm: bool) -> None:
    if require_confirm and not Confirm.ask("Run prod gate?", default=False):
        return
    for entry in _targets_for(target):
        _run_prod_gate(entry, dry_run=dry_run, skip_tests=skip_tests)


def _run_status(target: str, env: str, *, wait: bool, interval: float, timeout: float) -> None:
    if env not in STATUS_ENVS:
        raise click.ClickException("Status is only available for dev/testing.")
    for entry in _targets_for(target):
        app_ref = _resolve_coolify_app(entry, env)
        if not app_ref:
            console.print(f"No Coolify app ref for {entry} {env}; skipping.")
            continue
        if wait:
            _wait_for_status(entry, env, app_ref, interval=interval, timeout=timeout)
        else:
            _print_status(entry, env, app_ref)


def _print_local_doctor(entry: str, settings: StackSettings) -> None:
    required_env = ("ODOO_DB_NAME", "ODOO_DB_USER")
    visible_env = (
        "ODOO_PROJECT_NAME",
        "ODOO_VERSION",
        "ODOO_STATE_ROOT",
        "ODOO_DATA_HOST_DIR",
        "ODOO_DB_HOST_DIR",
        "ODOO_LOG_HOST_DIR",
        "ODOO_DB_NAME",
        "ODOO_DB_USER",
    )
    console.print(f"Local stack: [bold]{entry}[/bold]")
    console.print(f"  name: {settings.name}")
    console.print(f"  compose command: {' '.join(settings.compose_command)}")
    console.print(f"  env file: {settings.env_file}")
    console.print(f"  source env: {settings.source_env_file}")
    console.print(f"  state root: {settings.state_root}")
    console.print(f"  compose project: {settings.compose_project}")
    console.print(f"  compose files: {', '.join(str(path) for path in settings.compose_files)}")
    console.print(f"  services: {', '.join(settings.services)}")
    console.print(f"  script runner: {settings.script_runner_service}")
    console.print(f"  registry image: {settings.registry_image}")
    try:
        commit = get_git_commit(settings.repo_root)
        console.print(f"  image tag: {settings.registry_image}:{settings.name}-{commit[:7]}")
    except (RuntimeError, OSError) as error:
        console.print(f"  image tag: unavailable ({error})")

    missing_env = [key for key in required_env if not settings.environment.get(key)]
    if missing_env:
        console.print(f"  missing env: {', '.join(missing_env)}")

    missing_files = [path for path in (settings.env_file, settings.source_env_file) if not path.exists()]
    missing_files.extend(path for path in settings.compose_files if not path.exists())
    if missing_files:
        console.print(f"  missing files: {', '.join(str(path) for path in missing_files)}")

    compose_binary = str(settings.compose_command[0]) if settings.compose_command else ""
    if compose_binary:
        compose_path = _resolve_command_path(compose_binary)
        if compose_path is None:
            console.print(f"  compose binary: missing ({compose_binary})")
        else:
            console.print(f"  compose binary: {compose_path}")
            if Path(compose_binary).name == "docker":
                try:
                    result = run_process(
                        _docker_command(settings, ["info"]),
                        env=local_compose_env(settings),
                        capture_output=True,
                        check=False,
                    )
                except OSError:
                    console.print("  docker daemon: unavailable")
                else:
                    if result.returncode == 0:
                        console.print("  docker daemon: ok")
                    else:
                        console.print("  docker daemon: unavailable")

    health_status = _check_healthcheck_url(settings.healthcheck_url)
    if health_status:
        console.print(f"  healthcheck url: {settings.healthcheck_url} ({health_status})")

    if compose_binary:
        _print_compose_health(settings)

    for key in visible_env:
        value = settings.environment.get(key)
        if value:
            console.print(f"  env {key}: {value}")


def _check_healthcheck_url(url: str) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return f"ok {response.status}"
    except urllib.error.HTTPError as error:
        return f"error {error.code}"
    except (OSError, TimeoutError, urllib.error.URLError) as error:
        return f"unreachable {error}"


_WIN_DEFAULT_PATHEXT = ".COM;.EXE;.BAT;.CMD;.VBS;.JS;.WS;.MSC"


def _access_check(path_name: str, mode: int) -> bool:
    return os.path.exists(path_name) and os.access(path_name, mode) and not os.path.isdir(path_name)


def _win_path_needs_curdir(command: str, mode: int) -> bool:
    if not (mode & os.X_OK):
        return True
    try:
        import _winapi  # type: ignore[attr-defined]
    except ImportError:
        return False
    return _winapi.NeedCurrentDirectoryForExePath(os.fsdecode(command))


def _resolve_command_path(command: str) -> str | None:
    if not command:
        return None

    mode = os.F_OK | os.X_OK
    directory_name, command_name = os.path.split(command)
    if directory_name:
        search_paths = [directory_name]
    else:
        path_value = os.environ.get("PATH")
        if path_value is None:
            try:
                path_value = os.confstr("CS_PATH")
            except (AttributeError, ValueError):
                path_value = os.defpath

        if not path_value:
            return None

        path_value = os.fsdecode(path_value)
        search_paths = path_value.split(os.pathsep)

        if sys.platform == "win32" and _win_path_needs_curdir(command_name, mode):
            search_paths.insert(0, os.curdir)

    if sys.platform == "win32":
        pathext_source = os.getenv("PATHEXT") or _WIN_DEFAULT_PATHEXT
        path_extensions = [extension.rstrip(".") for extension in pathext_source.split(os.pathsep) if extension]
        candidates = [f"{command_name}{extension}" for extension in path_extensions]

        normalized_command = command_name.upper()
        if not (mode & os.X_OK) or any(normalized_command.endswith(extension.upper()) for extension in path_extensions):
            candidates.insert(0, command_name)
    else:
        candidates = [command_name]

    seen_directories: set[str] = set()
    for directory in search_paths:
        normalized_directory = os.path.normcase(directory)
        if normalized_directory in seen_directories:
            continue
        seen_directories.add(normalized_directory)
        for candidate_name in candidates:
            candidate_path = os.path.join(directory, candidate_name)
            if _access_check(candidate_path, mode):
                return candidate_path
    return None


def _print_compose_health(settings: StackSettings) -> None:
    services = settings.services
    if not services:
        return
    console.print("  service health:")
    for service in services:
        container_id = _compose_container_id(settings, service)
        if not container_id:
            console.print(f"    - {service}: not running")
            continue
        state = _inspect_container_state(settings, container_id)
        health = _inspect_container_health(settings, container_id)
        if health is None:
            console.print(f"    - {service}: {state}")
            continue
        console.print(f"    - {service}: {state}, health={health}")


def _compose_container_id(settings: StackSettings, service: str) -> str | None:
    try:
        result = run_process(
            local_compose_command(settings, ["ps", "-q", service]),
            cwd=settings.repo_root,
            env=local_compose_env(settings),
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    container_id = (result.stdout or "").strip()
    return container_id or None


def _inspect_container_state(settings: StackSettings, container_id: str) -> str:
    try:
        result = run_process(
            _docker_command(settings, ["inspect", "-f", "{{.State.Status}}", container_id]),
            env=local_compose_env(settings),
            capture_output=True,
            check=False,
        )
    except OSError:
        return "unknown"
    state = (result.stdout or "").strip() if result.returncode == 0 else "unknown"
    return state or "unknown"


def _inspect_container_health(settings: StackSettings, container_id: str) -> str | None:
    try:
        result = run_process(
            _docker_command(settings, ["inspect", "-f", "{{.State.Health.Status}}", container_id]),
            env=local_compose_env(settings),
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    health = (result.stdout or "").strip()
    if not health or health == "<no value>":
        return None
    return health


def _prompt_choice(label: str, choices: Iterable[str], default: str) -> str:
    options = list(choices)
    if questionary and sys.stdin.isatty():
        selection = questionary.select(label, choices=options, default=default).ask()
        if selection is None:
            raise click.Abort()
        return str(selection)
    return Prompt.ask(label, choices=options, default=default)


def _interactive(*, dry_run: bool, remember: bool, wait_deploy: bool) -> None:
    try:
        state = _load_state()
        favorite = None
        favorites = _favorite_states()
        if favorites:
            if questionary and sys.stdin.isatty():
                labels = [_favorite_label(entry) for entry in favorites]
                choices = [*labels, "Custom"]
                selection = questionary.select("Pick favorite", choices=choices, default="Custom").ask()
                if selection in labels:
                    favorite = favorites[labels.index(selection)]
            else:
                console.print("Favorites:")
                for index, entry in enumerate(favorites, start=1):
                    console.print(f"  {index}) {_favorite_label(entry)}")
                choice = Prompt.ask(
                    "Use favorite?",
                    choices=[*map(str, range(1, len(favorites) + 1)), "custom"],
                    default="custom",
                )
                if choice != "custom":
                    favorite = favorites[int(choice) - 1]

        build = False
        no_cache = False
        serial = False
        post_action = "none"
        if favorite:
            target = favorite.target
            env = favorite.env
            action = favorite.action
            deploy = favorite.deploy
            build = favorite.build
            no_cache = favorite.no_cache
            serial = False
        else:
            target = _prompt_choice("Target", _target_choices(), state.target)
            env = _prompt_choice("Env", ENVS, state.env)

            if env == "local":
                action_choices = LOCAL_ACTIONS
            elif env == "prod":
                action_choices = SHIP_ACTIONS + GATE_ACTIONS
            else:
                action_choices = SHIP_ACTIONS

            action_default = state.action if state.action in action_choices else action_choices[0]
            action = _prompt_choice("Action", action_choices, action_default)
            deploy = state.deploy
            if action == "ship" and env in ("dev", "testing"):
                deploy = Confirm.ask("Trigger Coolify deploy after push?", default=True)
                serial = Confirm.ask("Deploy serially?", default=False)
                post_action = _prompt_choice("After deploy", POST_SHIP_ACTIONS, "none")
            if env == "local" and action in ("up", "init", "restore"):
                if questionary and sys.stdin.isatty():
                    build_choice = questionary.select("Build image?", choices=["No", "Yes"], default="No").ask()
                    build = build_choice == "Yes"
                else:
                    build = Confirm.ask("Build image before starting?", default=False)
                if build:
                    if questionary and sys.stdin.isatty():
                        cache_choice = questionary.select(
                            "Use build cache?",
                            choices=["Yes", "No-cache"],
                            default="Yes",
                        ).ask()
                        no_cache = cache_choice == "No-cache"
                    else:
                        no_cache = Confirm.ask("Use --no-cache?", default=False)

        current = OpsState(
            target=target,
            env=env,
            action=action,
            deploy=deploy,
            build=build,
            no_cache=no_cache,
            serial=serial,
        )
        if remember:
            _save_state(current)

        _execute(
            target,
            env,
            action,
            deploy=deploy,
            wait_deploy=wait_deploy,
            serial=serial,
            build=build,
            no_cache=no_cache,
            post_action=post_action,
            dry_run=dry_run,
            skip_tests=False,
            require_confirm=True,
            record_history=True,
        )
        command_line = _render_cli_command(
            target=target,
            env=env,
            action=action,
            deploy=deploy,
            wait_deploy=wait_deploy,
            serial=serial,
            build=build,
            no_cache=no_cache,
            post_action=post_action,
            dry_run=dry_run,
        )
        console.print(f"CLI command: {command_line}")
    except (KeyboardInterrupt, EOFError) as error:
        raise click.Abort() from error


def _execute(
    target: str,
    env: str,
    action: str,
    *,
    deploy: bool,
    wait_deploy: bool,
    serial: bool,
    build: bool,
    no_cache: bool,
    post_action: str | None,
    dry_run: bool,
    skip_tests: bool,
    require_confirm: bool,
    json_output: bool = False,
    record_history: bool = False,
) -> None:
    valid_targets = set(_target_names()) | {ALL_TARGET}
    if target not in valid_targets:
        raise click.ClickException(f"Unknown target: {target}")
    if env not in ENVS:
        raise click.ClickException(f"Unknown env: {env}")

    if action in LOCAL_ACTIONS:
        if env != "local":
            raise click.ClickException("Local actions are only valid for env=local.")
        _run_local_action(
            target,
            action,
            dry_run=dry_run,
            build=build,
            no_cache=no_cache,
            json_output=json_output,
        )
        if record_history:
            _record_history(
                OpsState(
                    target=target,
                    env=env,
                    action=action,
                    deploy=deploy,
                    build=build,
                    no_cache=no_cache,
                    serial=serial,
                )
            )
        return

    if action == "ship":
        _run_ship(
            target,
            env,
            deploy=deploy,
            wait_deploy=wait_deploy,
            serial=serial,
            post_action=post_action,
            dry_run=dry_run,
            skip_tests=skip_tests,
            require_confirm=require_confirm,
        )
        if record_history:
            _record_history(OpsState(target=target, env=env, action=action, deploy=deploy, serial=serial))
        return

    if action == "gate":
        _run_gate(target, dry_run=dry_run, skip_tests=skip_tests, require_confirm=require_confirm)
        if record_history:
            _record_history(OpsState(target=target, env=env, action=action, deploy=deploy, serial=serial))
        return

    raise click.ClickException(f"Unknown action: {action}")


@click.group(invoke_without_command=True)
@click.option("--target", default=None)
@click.option("--env", "env_name", default=None)
@click.option("--action", default=None)
@click.option("--deploy/--no-deploy", default=True, help="Trigger Coolify deploy after ship")
@click.option("--wait/--no-wait", default=True, help="Wait for Coolify deploy to finish")
@click.option("--serial/--parallel", default=False, help="Deploy one target at a time when shipping")
@click.option("--build/--no-build", default=False, help="Build image before local actions")
@click.option("--no-cache", is_flag=True, help="Build without cache for local actions")
@click.option("--skip-tests", is_flag=True, help="Skip ship gate tests")
@click.option("--dry-run", is_flag=True)
@click.option("--remember/--no-remember", default=True)
@click.pass_context
def main(
    ctx: click.Context,
    target: str | None,
    env_name: str | None,
    action: str | None,
    deploy: bool,
    wait: bool,
    serial: bool,
    build: bool,
    no_cache: bool,
    skip_tests: bool,
    dry_run: bool,
    remember: bool,
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    if not target and not env_name and not action:
        _interactive(dry_run=dry_run, remember=remember, wait_deploy=wait)
        return
    if not (target and env_name and action):
        raise click.ClickException("Provide --target, --env, and --action or run without arguments for prompts.")
    _execute(
        target,
        env_name,
        action,
        deploy=deploy,
        wait_deploy=wait,
        serial=serial,
        build=build if env_name == "local" else False,
        no_cache=no_cache if env_name == "local" else False,
        post_action=None,
        dry_run=dry_run,
        skip_tests=skip_tests,
        require_confirm=True,
        record_history=True,
    )


@main.command("local")
@click.argument("action", type=click.Choice(LOCAL_ACTIONS, case_sensitive=False))
@click.argument("target")
@click.option("--build/--no-build", default=False, help="Build image before local actions")
@click.option("--no-cache", is_flag=True, help="Build without cache")
@click.option("--json", "json_output", is_flag=True, help="Output info as JSON (info action only)")
@click.option("--dry-run", is_flag=True)
def local_command(
    action: str,
    target: str,
    build: bool,
    no_cache: bool,
    json_output: bool,
    dry_run: bool,
) -> None:
    if json_output and action != "info":
        raise click.ClickException("--json is only supported with the info action.")
    _execute(
        target,
        "local",
        action,
        deploy=False,
        wait_deploy=False,
        serial=False,
        build=build,
        no_cache=no_cache,
        post_action=None,
        dry_run=dry_run,
        skip_tests=False,
        require_confirm=False,
        json_output=json_output,
        record_history=True,
    )


@main.command("ship")
@click.argument("env", type=click.Choice(("dev", "testing", "prod"), case_sensitive=False))
@click.argument("target")
@click.option("--deploy/--no-deploy", default=True)
@click.option("--wait/--no-wait", default=True, help="Wait for Coolify deploy to finish")
@click.option("--serial/--parallel", default=False, help="Deploy one target at a time")
@click.option("--after", type=click.Choice(POST_SHIP_ACTIONS, case_sensitive=False), default="none")
@click.option("--skip-tests", is_flag=True)
@click.option("--dry-run", is_flag=True)
@click.option("--confirm/--no-confirm", default=False)
def ship_command(
    env: str,
    target: str,
    deploy: bool,
    wait: bool,
    serial: bool,
    after: str,
    skip_tests: bool,
    dry_run: bool,
    confirm: bool,
) -> None:
    if env == "prod" and not confirm and not sys.stdin.isatty():
        raise click.ClickException("Prod ship requires --confirm when non-interactive.")
    require_confirm = env == "prod" and not confirm
    post_action = after if after != "none" else None
    if env == "prod" and post_action is None:
        post_action = "upgrade"
    _execute(
        target,
        env,
        "ship",
        deploy=deploy,
        wait_deploy=wait,
        serial=serial,
        build=False,
        no_cache=False,
        post_action=post_action,
        dry_run=dry_run,
        skip_tests=skip_tests,
        require_confirm=require_confirm,
        record_history=True,
    )


@main.command("gate")
@click.argument("target")
@click.option("--skip-tests", is_flag=True)
@click.option("--dry-run", is_flag=True)
@click.option("--confirm/--no-confirm", default=False)
def gate_command(target: str, skip_tests: bool, dry_run: bool, confirm: bool) -> None:
    if not confirm and not sys.stdin.isatty():
        raise click.ClickException("Prod gate requires --confirm when non-interactive.")
    _execute(
        target,
        "prod",
        "gate",
        deploy=False,
        wait_deploy=False,
        serial=False,
        build=False,
        no_cache=False,
        post_action=None,
        dry_run=dry_run,
        skip_tests=skip_tests,
        require_confirm=not confirm,
        record_history=True,
    )


@main.command("status")
@click.argument("env", type=click.Choice(STATUS_ENVS, case_sensitive=False))
@click.argument("target")
@click.option("--wait/--no-wait", default=True, help="Wait for deployment to finish")
@click.option("--interval", type=float, default=STATUS_INTERVAL_DEFAULT, help="Polling interval in seconds")
@click.option("--timeout", type=float, default=STATUS_TIMEOUT_DEFAULT, help="Timeout in seconds")
def status_command(env: str, target: str, wait: bool, interval: float, timeout: float) -> None:
    _run_status(target, env, wait=wait, interval=interval, timeout=timeout)


if __name__ == "__main__":
    main()
