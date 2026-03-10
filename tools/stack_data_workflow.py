import logging
import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import replace as _dataclass_replace
from pathlib import Path

from tools.deployer.command import CommandError, run_process
from tools.deployer.compose_ops import local_compose_command, local_compose_env, remote_compose_command
from tools.deployer.data_workflow_support import (
    build_updated_environment,
    ensure_local_bind_mounts,
    prepare_remote_stack,
    push_env_to_remote,
    wait_for_local_service,
    write_env_file,
)
from tools.deployer.helpers import get_git_commit, get_git_remote_url
from tools.deployer.remote import run_remote
from tools.deployer.settings import StackSettings, load_stack_settings
from tools.platform.dokploy import (
    collect_dokploy_deploy_servers,
    dokploy_request,
    resolve_dokploy_compose_id,
    resolve_dokploy_compose_name,
    resolve_dokploy_compose_remote_config,
)
from tools.platform.environment import resolve_stack_runtime_scope

_logger = logging.getLogger(__name__)

DATA_WORKFLOW_SCRIPT = "/volumes/scripts/run_odoo_data_workflows.py"

DATA_WORKFLOW_SCRIPT_ENV_KEYS = {
    "ODOO_DB_HOST",
    "ODOO_DB_PORT",
    "ODOO_DB_USER",
    "ODOO_DB_PASSWORD",
    "ODOO_DB_NAME",
    "ODOO_FILESTORE_PATH",
    "ODOO_FILESTORE_OWNER",
    "DATA_WORKFLOW_SSH_DIR",
    "DATA_WORKFLOW_SSH_KEY",
    "ODOO_PROJECT_NAME",
    "ODOO_VERSION",
    "ODOO_ADDONS_PATH",
    "ODOO_ADDON_REPOSITORIES",
    "ODOO_INSTALL_MODULES",
    "ODOO_UPDATE_MODULES",
    "LOCAL_ADDONS_DIRS",
    "OPENUPGRADE_ENABLED",
    "OPENUPGRADE_SCRIPTS_PATH",
    "OPENUPGRADE_TARGET_VERSION",
    "OPENUPGRADE_SKIP_UPDATE_ADDONS",
    "ODOO_KEY",
    "ODOO_ADMIN_LOGIN",
    "ODOO_ADMIN_PASSWORD",
    "ODOO_DATA_WORKFLOW_LOCK_FILE",
    "ODOO_UPSTREAM_HOST",
    "ODOO_UPSTREAM_USER",
    "ODOO_UPSTREAM_DB_NAME",
    "ODOO_UPSTREAM_DB_USER",
    "ODOO_UPSTREAM_FILESTORE_PATH",
    "BOOTSTRAP",
    "NO_SANITIZE",
}

DATA_WORKFLOW_SCRIPT_ENV_PREFIXES = (
    "ENV_OVERRIDE_",
    "OPENUPGRADE_",
)

REQUIRED_UPSTREAM_ENV_KEYS = (
    "ODOO_UPSTREAM_HOST",
    "ODOO_UPSTREAM_USER",
    "ODOO_UPSTREAM_DB_NAME",
    "ODOO_UPSTREAM_DB_USER",
    "ODOO_UPSTREAM_FILESTORE_PATH",
)


def _data_workflow_script_environment(env_values: dict[str, str]) -> dict[str, str]:
    filtered_values: dict[str, str] = {}
    for env_key, env_value in env_values.items():
        if env_key in DATA_WORKFLOW_SCRIPT_ENV_KEYS:
            filtered_values[env_key] = env_value
            continue
        if any(env_key.startswith(prefix) for prefix in DATA_WORKFLOW_SCRIPT_ENV_PREFIXES):
            filtered_values[env_key] = env_value
    return filtered_values


def _add_exec_env_names(command: list[str], env_names: Iterable[str]) -> None:
    for env_name in sorted(env_names):
        command.extend(["-e", env_name])


def _missing_upstream_source_keys(env_values: dict[str, str]) -> tuple[str, ...]:
    missing_keys: list[str] = []
    for environment_key in REQUIRED_UPSTREAM_ENV_KEYS:
        if env_values.get(environment_key, "").strip():
            continue
        missing_keys.append(environment_key)
    return tuple(missing_keys)


def _ensure_stack_env(settings: StackSettings, stack_name: str) -> None:
    env_path = settings.env_file
    if env_path.exists():
        return
    raise FileNotFoundError(f"No environment file found for stack '{stack_name}'. Expected {env_path}.")


def _handle_data_workflow_exit(error: CommandError) -> None:
    if error.returncode == 10:
        _logger.warning("run_odoo_data_workflows exited with code 10; continuing because bootstrap completed successfully")
        return
    raise error


def _run_local_compose(settings: StackSettings, extra: Sequence[str], *, check: bool = True) -> None:
    command = local_compose_command(settings, extra)
    run_process(command, cwd=settings.repo_root, check=check, env=local_compose_env(settings))


def _run_remote_compose(settings: StackSettings, extra: Sequence[str]) -> None:
    if settings.remote_host is None or settings.remote_stack_path is None:
        raise ValueError("remote compose requested without remote host configuration")
    command = remote_compose_command(settings, extra)
    run_remote(settings.remote_host, settings.remote_user, settings.remote_port, command, settings.remote_stack_path)


def _current_image_reference(settings: StackSettings) -> str:
    return settings.environment.get(settings.image_variable_name) or settings.registry_image


def _add_toggle_env_flags(command: list[str], *, bootstrap: bool, no_sanitize: bool) -> None:
    if bootstrap:
        command.extend(["-e", "BOOTSTRAP=1"])
    if no_sanitize:
        command.extend(["-e", "NO_SANITIZE=1"])


def _add_toggle_args(command: list[str], *, bootstrap: bool, no_sanitize: bool) -> None:
    if bootstrap:
        command.append("--bootstrap")
    if no_sanitize:
        command.append("--no-sanitize")


def _resolve_data_workflow_environment(raw_values: dict[str, str]) -> dict[str, str]:
    def _strip_quotes(raw: str) -> str:
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
            return raw[1:-1]
        return raw

    pattern = re.compile(r"\$\{([^}]+)}")
    cache: dict[str, str] = {}

    def _resolve_expr(expr: str, seen: set[str]) -> str:
        name, default = expr, ""
        if ":-" in expr:
            name, default = (part.strip() for part in expr.split(":-", 1))
        cached_value = cache.get(name)
        if cached_value is not None:
            return cached_value
        if name in raw_values:
            return _resolve_value(name, seen)
        return os.environ.get(name, default)

    def _resolve_value(variable_name: str, seen: set[str]) -> str:
        if variable_name in cache:
            return cache[variable_name]
        if variable_name in seen:
            return raw_values.get(variable_name, "")
        seen.add(variable_name)
        raw = raw_values.get(variable_name, "")
        if not isinstance(raw, str):
            raw_str = str(raw)
        else:
            raw_str = _strip_quotes(raw.strip())

        previous = None
        resolved = raw_str
        while previous != resolved:
            previous = resolved
            resolved = pattern.sub(lambda match: _resolve_expr(match.group(1), seen), resolved)

        # Preserve legacy behavior for shell-style and home-path expansion
        # used in existing restore environment files.
        resolved = os.path.expandvars(resolved)
        resolved = os.path.expanduser(resolved)

        cache[variable_name] = resolved
        seen.discard(variable_name)
        return resolved

    return {env_var_name: _resolve_value(env_var_name, set()) for env_var_name in raw_values}


def _run_dokploy_managed_remote_data_workflow(
    settings: StackSettings,
    env_values: dict[str, str],
    *,
    bootstrap: bool,
    no_sanitize: bool,
) -> int:
    """Run the data workflow on a Dokploy-managed compose target via SSH.

    Reuses the existing SSH remote machinery but skips prepare_remote_stack because
    Dokploy has already deployed the compose files to the remote host.

    The remote .env is temporarily overwritten for the duration of the workflow.
    The next Dokploy deploy (platform ship) will restore the Dokploy-managed environment.

    Compose project name and remote stack path are derived from the Dokploy API.
    Override via env vars if Dokploy's appName does not match what is expected:
      DOKPLOY_REMOTE_STACK_PATH_<STACK_NAME_UPPER>  e.g. DOKPLOY_REMOTE_STACK_PATH_CM_DEV
      DOKPLOY_COMPOSE_PROJECT_<STACK_NAME_UPPER>    e.g. DOKPLOY_COMPOSE_PROJECT_CM_DEV
      DOKPLOY_SSH_HOST                              explicit SSH hostname override
      DOKPLOY_SSH_USER                              SSH user (default: root)
      DOKPLOY_SSH_PORT                              SSH port (default: 22)
    """
    dokploy_host = env_values.get("DOKPLOY_HOST", "").strip()
    dokploy_token = env_values.get("DOKPLOY_TOKEN", "").strip()
    if not dokploy_host or not dokploy_token:
        raise ValueError(
            "Dokploy remote data workflow requires DOKPLOY_HOST and DOKPLOY_TOKEN "
            "in the resolved environment. Configure them in .env or platform/secrets.toml."
        )

    runtime_scope = resolve_stack_runtime_scope(settings.name)
    if runtime_scope is None:
        raise ValueError(f"Unable to derive runtime scope from stack name {settings.name!r}.")
    context_name, instance_name = runtime_scope
    compose_name = resolve_dokploy_compose_name(context_name, instance_name, env_values)

    ssh_host, ssh_user, ssh_port, remote_stack_path, compose_project = _resolve_dokploy_remote_runtime(
        dokploy_host=dokploy_host,
        dokploy_token=dokploy_token,
        compose_name=compose_name,
        env_values=env_values,
    )

    _logger.info(
        "Dokploy remote data workflow: stack=%s ssh=%s@%s path=%s compose_project=%s",
        settings.name,
        ssh_user,
        ssh_host,
        remote_stack_path,
        compose_project,
    )

    remote_settings = _dataclass_replace(
        settings,
        remote_host=ssh_host,
        remote_user=ssh_user,
        remote_port=ssh_port,
        remote_stack_path=remote_stack_path,
        remote_env_path=remote_stack_path / ".env",
        compose_project=compose_project,
    )

    # Temporarily write the merged workflow env to the remote .env.
    # This is necessary so docker compose can resolve image references and service config.
    # The next `platform ship` (Dokploy deploy) will restore the Dokploy-managed environment.
    push_env_to_remote(remote_settings, env_values)

    if "database" in remote_settings.services:
        _run_remote_compose(remote_settings, ["up", "-d", "--remove-orphans", "database"])

    _run_remote_compose(
        remote_settings,
        ["up", "-d", "--remove-orphans", remote_settings.script_runner_service],
    )
    _run_remote_compose(remote_settings, ["stop", "web"])

    remote_exec: list[str] = [
        "exec",
        "-T",
        "--user",
        "root",
    ]
    _add_toggle_env_flags(remote_exec, bootstrap=bootstrap, no_sanitize=no_sanitize)
    remote_exec.extend(
        [
            remote_settings.script_runner_service,
            "python3",
            "-u",
            DATA_WORKFLOW_SCRIPT,
        ]
    )
    _add_toggle_args(remote_exec, bootstrap=bootstrap, no_sanitize=no_sanitize)

    try:
        _run_remote_compose(remote_settings, remote_exec)
    except CommandError as error:
        _handle_data_workflow_exit(error)

    _run_remote_compose(remote_settings, ["up", "-d", "--remove-orphans", "web"])
    _logger.info(
        "Dokploy compose data workflow completed for stack %s on %s",
        settings.name,
        ssh_host,
    )
    return 0


def _resolve_dokploy_remote_runtime(
    *,
    dokploy_host: str,
    dokploy_token: str,
    compose_name: str,
    env_values: dict[str, str],
) -> tuple[str, str | None, int | None, Path, str]:
    safe_name = compose_name.upper().replace("-", "_")
    path_override_key = f"DOKPLOY_REMOTE_STACK_PATH_{safe_name}"
    project_override_key = f"DOKPLOY_COMPOSE_PROJECT_{safe_name}"
    path_override = env_values.get(path_override_key, "").strip()
    project_override = env_values.get(project_override_key, "").strip()

    ssh_user_override = env_values.get("DOKPLOY_SSH_USER", "").strip()
    ssh_port_raw = env_values.get("DOKPLOY_SSH_PORT", "").strip()
    ssh_port_override = int(ssh_port_raw) if ssh_port_raw.isdigit() else None

    deploy_servers = collect_dokploy_deploy_servers(host=dokploy_host, token=dokploy_token)
    if not deploy_servers:
        raise ValueError("Dokploy reported no deploy servers for remote data workflow discovery.")

    ssh_host_override = env_values.get("DOKPLOY_SSH_HOST", "").strip()

    if path_override and project_override:
        remote_stack_path = Path(path_override)
        compose_project = project_override
    else:
        remote_stack_path, compose_project = resolve_dokploy_compose_remote_config(
            host=dokploy_host,
            token=dokploy_token,
            compose_name=compose_name,
            environment_values=env_values,
        )

    if ssh_host_override:
        for deploy_server in deploy_servers:
            server_name = str(deploy_server.get("name") or "").strip()
            server_ip = str(deploy_server.get("ipAddress") or "").strip()
            if ssh_host_override not in {server_name, server_ip}:
                continue
            ssh_user = ssh_user_override or str(deploy_server.get("username") or "").strip() or "root"
            raw_server_port = deploy_server.get("port")
            if ssh_port_override is not None:
                ssh_port = ssh_port_override
            elif isinstance(raw_server_port, int):
                ssh_port = raw_server_port
            else:
                ssh_port = 22
            return ssh_host_override, ssh_user, ssh_port, remote_stack_path, compose_project

        ssh_port = ssh_port_override if ssh_port_override is not None else 22
        ssh_user = ssh_user_override or "root"
        return ssh_host_override, ssh_user, ssh_port, remote_stack_path, compose_project

    context_name, instance_name = compose_name.split("-", 1)
    compose_id, _resolved_compose_name = resolve_dokploy_compose_id(
        host=dokploy_host,
        token=dokploy_token,
        context_name=context_name,
        instance_name=instance_name,
        environment_values=env_values,
    )
    compose_payload = dokploy_request(
        host=dokploy_host,
        token=dokploy_token,
        path="/api/compose.one",
        query={"composeId": compose_id},
    )
    if not isinstance(compose_payload, dict):
        raise ValueError(f"Dokploy compose.one returned an invalid response for compose {compose_name!r}.")

    compose_server_id = str(compose_payload.get("serverId") or "").strip()
    if compose_server_id:
        for deploy_server in deploy_servers:
            server_id = str(
                deploy_server.get("serverId")
                or deploy_server.get("id")
                or deploy_server.get("_id")
                or ""
            ).strip()
            if server_id != compose_server_id:
                continue
            ssh_host = str(deploy_server.get("name") or "").strip() or str(deploy_server.get("ipAddress") or "").strip()
            if not ssh_host:
                raise ValueError(
                    f"Dokploy compose {compose_name!r} resolved to server {compose_server_id!r}, "
                    "but that deploy server has no hostname or IP address."
                )
            ssh_user = ssh_user_override or str(deploy_server.get("username") or "").strip() or "root"
            raw_server_port = deploy_server.get("port")
            if ssh_port_override is not None:
                ssh_port = ssh_port_override
            elif isinstance(raw_server_port, int):
                ssh_port = raw_server_port
            else:
                ssh_port = 22
            return ssh_host, ssh_user, ssh_port, remote_stack_path, compose_project
        raise ValueError(
            f"Dokploy compose {compose_name!r} resolved to unknown deploy server id {compose_server_id!r}."
        )

    if len(deploy_servers) == 1:
        deploy_server = deploy_servers[0]
        ssh_host = str(deploy_server.get("name") or "").strip() or str(deploy_server.get("ipAddress") or "").strip()
        if not ssh_host:
            raise ValueError(
                f"Dokploy remote workflow for {compose_name!r} needs a deploy host, but the only deploy server has no hostname or IP address."
            )
        ssh_user = ssh_user_override or str(deploy_server.get("username") or "").strip() or "root"
        raw_server_port = deploy_server.get("port")
        if ssh_port_override is not None:
            ssh_port = ssh_port_override
        elif isinstance(raw_server_port, int):
            ssh_port = raw_server_port
        else:
            ssh_port = 22
        return ssh_host, ssh_user, ssh_port, remote_stack_path, compose_project

    known_hosts = sorted(
        {
            host_name
            for deploy_server in deploy_servers
            for host_name in (
                str(deploy_server.get("name") or "").strip(),
                str(deploy_server.get("ipAddress") or "").strip(),
            )
            if host_name
        }
    )
    raise ValueError(
        f"Dokploy compose {compose_name!r} does not expose deploy server linkage. "
        f"Set DOKPLOY_SSH_HOST explicitly. Known hosts: {known_hosts!r}."
    )


def run_stack_data_workflow(
    stack_name: str,
    *,
    env_file: Path | None = None,
    bootstrap: bool = False,
    no_sanitize: bool = False,
) -> int:
    settings = load_stack_settings(stack_name, env_file)
    _ensure_stack_env(settings, stack_name)
    stack_settings = settings
    runtime_scope = resolve_stack_runtime_scope(stack_name)
    image_reference = _current_image_reference(stack_settings)
    env_values_raw = build_updated_environment(stack_settings, image_reference)
    env_values = _resolve_data_workflow_environment(env_values_raw)
    if not bootstrap:
        missing_upstream_keys = _missing_upstream_source_keys(env_values)
        if missing_upstream_keys:
            missing_joined = ", ".join(missing_upstream_keys)
            raise ValueError(
                "Restore requires upstream settings; missing: "
                f"{missing_joined}. Configure these in `.env` or `platform/secrets.toml`, "
                "or run bootstrap intentionally."
            )

    if stack_settings.remote_host:
        repository_url = get_git_remote_url(stack_settings.repo_root)
        commit = get_git_commit(stack_settings.repo_root)
        prepare_remote_stack(stack_settings, repository_url, commit)
        push_env_to_remote(stack_settings, env_values)

        if "database" in stack_settings.services:
            _run_remote_compose(stack_settings, ["up", "-d", "--remove-orphans", "database"])

        _run_remote_compose(stack_settings, ["up", "-d", "--remove-orphans", stack_settings.script_runner_service])
        _run_remote_compose(stack_settings, ["stop", "web"])

        remote_exec: list[str] = [
            "exec",
            "-T",
            "--user",
            "root",
        ]
        _add_toggle_env_flags(remote_exec, bootstrap=bootstrap, no_sanitize=no_sanitize)

        remote_exec.extend(
            [
                stack_settings.script_runner_service,
                "python3",
                "-u",
                DATA_WORKFLOW_SCRIPT,
            ]
        )
        _add_toggle_args(remote_exec, bootstrap=bootstrap, no_sanitize=no_sanitize)

        try:
            _run_remote_compose(stack_settings, remote_exec)
        except CommandError as error:
            _handle_data_workflow_exit(error)
        _run_remote_compose(stack_settings, ["up", "-d", "--remove-orphans", "web"])
    elif (
        runtime_scope is not None
        and runtime_scope[1] in {"dev", "testing", "prod"}
        and env_values.get("DOKPLOY_HOST", "").strip()
    ):
        # Dokploy-managed remote compose target: SSH to the Dokploy server.
        # The compose files are already deployed by Dokploy; we skip prepare_remote_stack
        # and derive the remote path + compose project from the Dokploy API.
        return _run_dokploy_managed_remote_data_workflow(
            stack_settings, env_values, bootstrap=bootstrap, no_sanitize=no_sanitize
        )
    else:
        ensure_local_bind_mounts(stack_settings)
        write_env_file(stack_settings.env_file, env_values)

        stack_started = False

        def _ensure_stack_running() -> None:
            nonlocal stack_started
            if stack_started:
                return
            _run_local_compose(
                stack_settings,
                ["up", "-d", "--remove-orphans", *stack_settings.services],
                check=False,
            )
            stack_started = True

        if "database" in stack_settings.services:
            _run_local_compose(stack_settings, ["up", "-d", "--remove-orphans", "database"], check=False)
            try:
                wait_for_local_service(stack_settings, "database")
            except ValueError:
                _ensure_stack_running()
                wait_for_local_service(stack_settings, "database")

        _run_local_compose(
            stack_settings,
            ["up", "-d", "--remove-orphans", stack_settings.script_runner_service],
            check=False,
        )
        try:
            wait_for_local_service(stack_settings, stack_settings.script_runner_service)
        except ValueError:
            _ensure_stack_running()
            wait_for_local_service(stack_settings, stack_settings.script_runner_service)
        _run_local_compose(stack_settings, ["stop", "web"], check=False)

        data_workflow_env_values = _data_workflow_script_environment(env_values)
        # Pass data workflow settings via process environment + name-only `-e KEY`
        # flags so secrets do not appear in the docker compose command line.
        exec_environment = dict(local_compose_env(stack_settings))
        exec_environment.update(data_workflow_env_values)

        exec_extra = [
            "exec",
            "-T",
            "--user",
            "root",
        ]
        _add_exec_env_names(exec_extra, data_workflow_env_values.keys())
        _add_toggle_env_flags(exec_extra, bootstrap=bootstrap, no_sanitize=no_sanitize)
        exec_extra.extend(
            [
                stack_settings.script_runner_service,
                "python3",
                "-u",
                DATA_WORKFLOW_SCRIPT,
            ]
        )
        _add_toggle_args(exec_extra, bootstrap=bootstrap, no_sanitize=no_sanitize)

        try:
            run_process(
                local_compose_command(stack_settings, exec_extra),
                cwd=stack_settings.repo_root,
                env=exec_environment,
            )
        except CommandError as error:
            _handle_data_workflow_exit(error)
        _run_local_compose(stack_settings, ["up", "-d", "--remove-orphans", "web"], check=False)

    _logger.info("Data workflow completed for stack %s", stack_name)
    return 0
