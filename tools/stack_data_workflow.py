import logging
import os
import re
import shlex
from collections.abc import Iterable, Sequence
from pathlib import Path

from tools.deployer.command import CommandError, run_process
from tools.deployer.compose_ops import local_compose_command, local_compose_env
from tools.deployer.data_workflow_support import (
    build_updated_environment,
    ensure_local_bind_mounts,
    wait_for_local_service,
    write_env_file,
)
from tools.deployer.settings import StackSettings, load_stack_settings
from tools.platform.dokploy import (
    DEFAULT_DOKPLOY_DEPLOY_TIMEOUT_SECONDS,
    deployment_key,
    deployment_status,
    dokploy_request,
    fetch_dokploy_target_payload,
    find_matching_dokploy_schedule,
    find_dokploy_target_definition,
    latest_deployment_for_compose,
    latest_deployment_for_schedule,
    load_dokploy_source_of_truth_if_present,
    parse_dokploy_env_text,
    resolve_dokploy_user_id,
    schedule_key,
    serialize_dokploy_env_text,
    update_dokploy_target_env,
    upsert_dokploy_schedule,
    wait_for_dokploy_compose_deployment,
    wait_for_dokploy_schedule_deployment,
)
from tools.platform.environment import load_dokploy_source_of_truth, resolve_stack_runtime_scope
from tools.platform.models import DokployTargetDefinition, JsonObject

_logger = logging.getLogger(__name__)

DATA_WORKFLOW_SCRIPT = "/volumes/scripts/run_odoo_data_workflows.py"
DOKPLOY_DATA_WORKFLOW_SCHEDULE_NAME = "platform-data-workflow"
DOKPLOY_MANUAL_ONLY_CRON_EXPRESSION = "0 0 31 2 *"
DOKPLOY_CANCELLED_DEPLOYMENT_STATUSES = {"cancelled", "canceled"}
DOKPLOY_SUCCESS_DEPLOYMENT_STATUSES = {"done", "success", "succeeded", "completed", "finished", "healthy"}
DOKPLOY_RUNNING_DEPLOYMENT_STATUSES = {"pending", "queued", "running", "in_progress", "starting"}

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


def _resolve_required_dokploy_compose_target_definition(
    settings: StackSettings,
    *,
    context_name: str,
    instance_name: str,
) -> DokployTargetDefinition:
    source_of_truth = load_dokploy_source_of_truth_if_present(settings.repo_root, load_dokploy_source_of_truth)
    if source_of_truth is None:
        raise ValueError("Dokploy-managed remote workflows require platform/dokploy.toml with pinned target metadata.")

    target_definition = find_dokploy_target_definition(
        source_of_truth,
        context_name=context_name,
        instance_name=instance_name,
    )
    if target_definition is None:
        raise ValueError(
            "Dokploy-managed remote workflow requires a target definition in platform/dokploy.toml for "
            f"{context_name}/{instance_name}."
        )
    if target_definition.target_type != "compose":
        raise ValueError(
            "Dokploy-managed remote data workflows require compose targets, but "
            f"platform/dokploy.toml configures {context_name}/{instance_name} as '{target_definition.target_type}'."
        )

    compose_id = target_definition.target_id.strip()
    if not compose_id:
        raise ValueError(
            "Dokploy-managed remote workflow requires a pinned target_id in platform/dokploy.toml for "
            f"{context_name}/{instance_name}."
        )
    return target_definition


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


def _build_dokploy_data_workflow_schedule_app_name(*, context_name: str, instance_name: str) -> str:
    return f"platform-{context_name}-{instance_name}-data-workflow"


def _resolve_dokploy_schedule_runtime(
    *,
    dokploy_host: str,
    dokploy_token: str,
    compose_id: str,
    compose_name: str,
) -> tuple[str, str, str, str | None]:
    compose_payload = dokploy_request(
        host=dokploy_host,
        token=dokploy_token,
        path="/api/compose.one",
        query={"composeId": compose_id},
    )
    if not isinstance(compose_payload, dict):
        raise ValueError(f"Dokploy compose.one returned an invalid response for compose {compose_name!r}.")

    compose_app_name = str(compose_payload.get("appName") or "").strip()
    if not compose_app_name:
        raise ValueError(f"Dokploy compose {compose_name!r} ({compose_id}) has no appName in API response.")

    compose_server_id = str(compose_payload.get("serverId") or "").strip()
    if compose_server_id:
        return "server", compose_server_id, compose_app_name, compose_server_id

    user_id = resolve_dokploy_user_id(host=dokploy_host, token=dokploy_token)
    return "dokploy-server", user_id, compose_app_name, None


def _build_dokploy_data_workflow_script(
    *,
    compose_app_name: str,
    bootstrap: bool,
    no_sanitize: bool,
    clear_stale_lock: bool,
    data_workflow_lock_path: str,
) -> str:
    workflow_arguments: list[str] = []
    if bootstrap:
        workflow_arguments.append("--bootstrap")
    if no_sanitize:
        workflow_arguments.append("--no-sanitize")

    quoted_workflow_arguments = " ".join(shlex.quote(argument) for argument in workflow_arguments)
    workflow_argument_line = (
        f"workflow_arguments=({quoted_workflow_arguments})" if quoted_workflow_arguments else "workflow_arguments=()"
    )
    clear_stale_lock_line = f"clear_stale_lock={'1' if clear_stale_lock else '0'}"

    return f"""#!/usr/bin/env bash
set -euo pipefail

compose_project={shlex.quote(compose_app_name)}
{workflow_argument_line}
{clear_stale_lock_line}
data_workflow_lock_path={shlex.quote(data_workflow_lock_path)}

resolve_container_id() {{
    local service_name="$1"
    local container_id
    container_id=$(docker ps -aq \
        --filter "label=com.docker.compose.project=${{compose_project}}" \
        --filter "label=com.docker.compose.service=${{service_name}}" | head -n 1)
    if [ -z "${{container_id}}" ]; then
        echo "Missing container for service '${{service_name}}' in project '${{compose_project}}'." >&2
        exit 1
    fi
    printf '%s' "${{container_id}}"
}}

ensure_running() {{
    local container_id="$1"
    local service_name="$2"
    local current_status
    current_status=$(docker inspect -f '{{{{.State.Status}}}}' "${{container_id}}")
    if [ "${{current_status}}" != "running" ]; then
        echo "Starting ${{service_name}} container ${{container_id}}"
        docker start "${{container_id}}" >/dev/null
    fi
}}

start_web_container() {{
    local current_status
    current_status=$(docker inspect -f '{{{{.State.Status}}}}' "${{web_container_id}}" 2>/dev/null || true)
    if [ "${{current_status}}" != "running" ]; then
        echo "Starting web container ${{web_container_id}}"
        docker start "${{web_container_id}}" >/dev/null || true
    fi
}}

database_container_id=$(resolve_container_id "database")
script_runner_container_id=$(resolve_container_id "script-runner")
web_container_id=$(resolve_container_id "web")

ensure_running "${{database_container_id}}" "database"
ensure_running "${{script_runner_container_id}}" "script-runner"

if [ "${{clear_stale_lock}}" = "1" ]; then
    echo "Clearing stale data workflow lock ${{data_workflow_lock_path}}"
    docker exec -u root "${{script_runner_container_id}}" rm -f "${{data_workflow_lock_path}}"
fi

trap start_web_container EXIT

web_status=$(docker inspect -f '{{{{.State.Status}}}}' "${{web_container_id}}")
if [ "${{web_status}}" = "running" ]; then
    echo "Stopping web container ${{web_container_id}}"
    docker stop "${{web_container_id}}" >/dev/null
fi

echo "Running platform data workflow in container ${{script_runner_container_id}}"
docker exec -u root "${{script_runner_container_id}}" \
    python3 -u {shlex.quote(DATA_WORKFLOW_SCRIPT)} "${{workflow_arguments[@]}}"

start_web_container
trap - EXIT
"""


def _schedule_deployments(schedule: JsonObject | None) -> tuple[JsonObject, ...]:
    if not isinstance(schedule, dict):
        return ()
    raw_deployments = schedule.get("deployments")
    if not isinstance(raw_deployments, list):
        return ()
    deployment_entries: list[JsonObject] = []
    for raw_deployment in raw_deployments:
        if isinstance(raw_deployment, dict):
            deployment_entries.append(raw_deployment)
    return tuple(deployment_entries)


def _deployment_status_value(deployment: JsonObject) -> str:
    return str(deployment.get("status") or "").strip().lower()


def _has_running_schedule_deployment(schedule: JsonObject | None) -> bool:
    return any(
        _deployment_status_value(deployment) in DOKPLOY_RUNNING_DEPLOYMENT_STATUSES
        for deployment in _schedule_deployments(schedule)
    )


def _should_clear_stale_data_workflow_lock(schedule: JsonObject | None) -> bool:
    deployments = _schedule_deployments(schedule)
    if not deployments or _has_running_schedule_deployment(schedule):
        return False
    for deployment in deployments:
        deployment_status_value = _deployment_status_value(deployment)
        if deployment_status_value in DOKPLOY_CANCELLED_DEPLOYMENT_STATUSES:
            return True
        if deployment_status_value in DOKPLOY_SUCCESS_DEPLOYMENT_STATUSES:
            return False
    return False


def _sync_dokploy_target_environment_and_deploy(
    *,
    dokploy_host: str,
    dokploy_token: str,
    target_definition: DokployTargetDefinition,
    env_values: dict[str, str],
    deploy_timeout_seconds: int,
) -> None:
    compose_id = target_definition.target_id.strip()
    compose_name = target_definition.target_name.strip() or f"{target_definition.context}-{target_definition.instance}"
    target_payload = fetch_dokploy_target_payload(
        host=dokploy_host,
        token=dokploy_token,
        target_type="compose",
        target_id=compose_id,
    )
    current_env_map = parse_dokploy_env_text(str(target_payload.get("env") or ""))
    desired_env_map = dict(current_env_map)
    updated_environment_keys: list[str] = []
    for environment_key, environment_value in env_values.items():
        if desired_env_map.get(environment_key) == environment_value:
            continue
        desired_env_map[environment_key] = environment_value
        updated_environment_keys.append(environment_key)

    if updated_environment_keys:
        update_dokploy_target_env(
            host=dokploy_host,
            token=dokploy_token,
            target_type="compose",
            target_id=compose_id,
            target_payload=target_payload,
            env_text=serialize_dokploy_env_text(desired_env_map),
        )
        _logger.info(
            "Updated Dokploy compose env for %s with %s key(s): %s",
            compose_name,
            len(updated_environment_keys),
            ",".join(sorted(updated_environment_keys)),
        )
    else:
        _logger.info("Dokploy compose env already matched generated workflow env for %s", compose_name)

    latest_compose_deployment = latest_deployment_for_compose(dokploy_host, dokploy_token, compose_id)
    previous_deployment_key = deployment_key(latest_compose_deployment or {})
    dokploy_request(
        host=dokploy_host,
        token=dokploy_token,
        path="/api/compose.deploy",
        method="POST",
        payload={"composeId": compose_id},
        timeout_seconds=deploy_timeout_seconds,
    )
    deployment_result = wait_for_dokploy_compose_deployment(
        host=dokploy_host,
        token=dokploy_token,
        compose_id=compose_id,
        before_key=previous_deployment_key,
        timeout_seconds=deploy_timeout_seconds,
    )
    _logger.info("Dokploy compose deployment completed before data workflow: %s", deployment_result)


def _run_dokploy_managed_remote_data_workflow(
    settings: StackSettings,
    env_values: dict[str, str],
    *,
    bootstrap: bool,
    no_sanitize: bool,
) -> int:
    """Run the data workflow on a Dokploy-managed target via Dokploy schedule jobs."""
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
    target_definition = _resolve_required_dokploy_compose_target_definition(
        settings,
        context_name=context_name,
        instance_name=instance_name,
    )

    compose_id = target_definition.target_id.strip()
    compose_name = target_definition.target_name.strip() or f"{context_name}-{instance_name}"
    schedule_type, schedule_lookup_id, compose_app_name, schedule_server_id = _resolve_dokploy_schedule_runtime(
        dokploy_host=dokploy_host,
        dokploy_token=dokploy_token,
        compose_id=compose_id,
        compose_name=compose_name,
    )
    schedule_name = DOKPLOY_DATA_WORKFLOW_SCHEDULE_NAME
    schedule_app_name = _build_dokploy_data_workflow_schedule_app_name(
        context_name=context_name,
        instance_name=instance_name,
    )
    schedule_timeout_seconds = target_definition.deploy_timeout_seconds or DEFAULT_DOKPLOY_DEPLOY_TIMEOUT_SECONDS
    _sync_dokploy_target_environment_and_deploy(
        dokploy_host=dokploy_host,
        dokploy_token=dokploy_token,
        target_definition=target_definition,
        env_values=env_values,
        deploy_timeout_seconds=schedule_timeout_seconds,
    )
    existing_schedule = find_matching_dokploy_schedule(
        host=dokploy_host,
        token=dokploy_token,
        target_id=schedule_lookup_id,
        schedule_type=schedule_type,
        schedule_name=schedule_name,
        app_name=schedule_app_name,
    )
    if _has_running_schedule_deployment(existing_schedule):
        raise ValueError(
            f"Dokploy-managed data workflow already has a running schedule deployment for {context_name}/{instance_name}."
        )
    schedule_script = _build_dokploy_data_workflow_script(
        compose_app_name=compose_app_name,
        bootstrap=bootstrap,
        no_sanitize=no_sanitize,
        clear_stale_lock=_should_clear_stale_data_workflow_lock(existing_schedule),
        data_workflow_lock_path=env_values.get("ODOO_DATA_WORKFLOW_LOCK_FILE", "/volumes/data/.data_workflow_in_progress"),
    )
    schedule_payload = {
        "name": schedule_name,
        "cronExpression": DOKPLOY_MANUAL_ONLY_CRON_EXPRESSION,
        "appName": schedule_app_name,
        "shellType": "bash",
        "scheduleType": schedule_type,
        "command": "platform data workflow",
        "script": schedule_script,
        "serverId": schedule_server_id,
        "userId": schedule_lookup_id if schedule_type == "dokploy-server" else None,
        "enabled": False,
        "timezone": "UTC",
    }
    schedule = upsert_dokploy_schedule(
        host=dokploy_host,
        token=dokploy_token,
        target_id=schedule_lookup_id,
        schedule_type=schedule_type,
        schedule_name=schedule_name,
        app_name=schedule_app_name,
        schedule_payload=schedule_payload,
    )
    schedule_id = schedule_key(schedule)
    if not schedule_id:
        raise ValueError(f"Dokploy schedule {schedule_name!r} for {context_name}/{instance_name} did not expose a schedule id.")

    latest_schedule_deployment = latest_deployment_for_schedule(dokploy_host, dokploy_token, schedule_id)
    previous_deployment_key = deployment_key(latest_schedule_deployment or {})

    _logger.info(
        "Dokploy remote data workflow: stack=%s schedule=%s schedule_type=%s compose_project=%s",
        settings.name,
        schedule_id,
        schedule_type,
        compose_app_name,
    )

    dokploy_request(
        host=dokploy_host,
        token=dokploy_token,
        path="/api/schedule.runManually",
        method="POST",
        payload={"scheduleId": schedule_id},
        timeout_seconds=schedule_timeout_seconds,
    )

    deployment_result = wait_for_dokploy_schedule_deployment(
        host=dokploy_host,
        token=dokploy_token,
        schedule_id=schedule_id,
        before_key=previous_deployment_key,
        timeout_seconds=30,
    )
    _logger.info("Dokploy schedule workflow deployment completed: %s", deployment_result)

    latest_schedule_deployment = latest_deployment_for_schedule(dokploy_host, dokploy_token, schedule_id)
    latest_schedule_status = deployment_status(latest_schedule_deployment or {})
    if latest_schedule_status and latest_schedule_status not in {"success", "succeeded", "done", "completed", "healthy", "finished"}:
        raise ValueError(f"Dokploy schedule {schedule_id!r} completed with non-success status {latest_schedule_status!r}.")
    _logger.info(
        "Dokploy-managed data workflow completed for stack %s via schedule %s",
        settings.name,
        schedule_id,
    )
    return 0


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

    if runtime_scope is not None and runtime_scope[1] in {"dev", "testing", "prod"} and env_values.get("DOKPLOY_HOST", "").strip():
        return _run_dokploy_managed_remote_data_workflow(stack_settings, env_values, bootstrap=bootstrap, no_sanitize=no_sanitize)

    ensure_local_bind_mounts(stack_settings)
    write_env_file(stack_settings.env_file, env_values)
    _run_local_compose(stack_settings, ["build", stack_settings.script_runner_service])

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
