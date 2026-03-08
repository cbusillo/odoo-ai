import logging
import os
import re
from collections.abc import Iterable, Sequence
from pathlib import Path

from tools.deployer.command import CommandError, run_process
from tools.deployer.compose_ops import local_compose_command, local_compose_env, remote_compose_command
from tools.deployer.helpers import get_git_commit, get_git_remote_url
from tools.deployer.remote import run_remote
from tools.deployer.restore_support import (
    build_updated_environment,
    ensure_local_bind_mounts,
    prepare_remote_stack,
    push_env_to_remote,
    wait_for_local_service,
    write_env_file,
)
from tools.deployer.settings import StackSettings, load_stack_settings

_logger = logging.getLogger(__name__)

RESTORE_SCRIPT = "/volumes/scripts/restore_from_upstream.py"

RESTORE_SCRIPT_ENV_KEYS = {
    "ODOO_DB_HOST",
    "ODOO_DB_PORT",
    "ODOO_DB_USER",
    "ODOO_DB_PASSWORD",
    "ODOO_DB_NAME",
    "ODOO_FILESTORE_PATH",
    "ODOO_FILESTORE_OWNER",
    "RESTORE_SSH_DIR",
    "RESTORE_SSH_KEY",
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
    "ODOO_ADMIN_PASSWORD",
    "ODOO_RESTORE_LOCK_FILE",
    "ODOO_UPSTREAM_HOST",
    "ODOO_UPSTREAM_USER",
    "ODOO_UPSTREAM_DB_NAME",
    "ODOO_UPSTREAM_DB_USER",
    "ODOO_UPSTREAM_FILESTORE_PATH",
    "BOOTSTRAP_ONLY",
    "NO_SANITIZE",
}

RESTORE_SCRIPT_ENV_PREFIXES = (
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


def _restore_script_environment(env_values: dict[str, str]) -> dict[str, str]:
    filtered_values: dict[str, str] = {}
    for env_key, env_value in env_values.items():
        if env_key in RESTORE_SCRIPT_ENV_KEYS:
            filtered_values[env_key] = env_value
            continue
        if any(env_key.startswith(prefix) for prefix in RESTORE_SCRIPT_ENV_PREFIXES):
            filtered_values[env_key] = env_value
    return filtered_values


def _add_exec_env_names(command: list[str], env_names: Iterable[str]) -> None:
    for env_name in sorted(env_names):
        command.extend(["-e", env_name])


def _missing_upstream_restore_keys(env_values: dict[str, str]) -> tuple[str, ...]:
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


def _handle_restore_exit(error: CommandError) -> None:
    if error.returncode == 10:
        _logger.warning("restore_from_upstream exited with code 10; continuing because bootstrap completed successfully")
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


def _add_toggle_env_flags(command: list[str], *, bootstrap_only: bool, no_sanitize: bool) -> None:
    if bootstrap_only:
        command.extend(["-e", "BOOTSTRAP_ONLY=1"])
    if no_sanitize:
        command.extend(["-e", "NO_SANITIZE=1"])


def _add_toggle_args(command: list[str], *, bootstrap_only: bool, no_sanitize: bool) -> None:
    if bootstrap_only:
        command.append("--bootstrap-only")
    if no_sanitize:
        command.append("--no-sanitize")


def _resolve_restore_environment(raw_values: dict[str, str]) -> dict[str, str]:
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


def restore_stack(
    stack_name: str,
    *,
    env_file: Path | None = None,
    bootstrap_only: bool = False,
    no_sanitize: bool = False,
) -> int:
    settings = load_stack_settings(stack_name, env_file)
    _ensure_stack_env(settings, stack_name)
    restore_settings = settings
    image_reference = _current_image_reference(restore_settings)
    env_values_raw = build_updated_environment(restore_settings, image_reference)
    env_values = _resolve_restore_environment(env_values_raw)
    if not bootstrap_only:
        missing_upstream_keys = _missing_upstream_restore_keys(env_values)
        if missing_upstream_keys:
            missing_joined = ", ".join(missing_upstream_keys)
            raise ValueError(
                "Restore requires upstream settings; missing: "
                f"{missing_joined}. Configure these in `.env` or `platform/secrets.toml`, "
                "or pass --bootstrap-only intentionally."
            )

    if restore_settings.remote_host:
        repository_url = get_git_remote_url(restore_settings.repo_root)
        commit = get_git_commit(restore_settings.repo_root)
        prepare_remote_stack(restore_settings, repository_url, commit)
        push_env_to_remote(restore_settings, env_values)

        if "database" in restore_settings.services:
            _run_remote_compose(restore_settings, ["up", "-d", "--remove-orphans", "database"])

        _run_remote_compose(restore_settings, ["up", "-d", "--remove-orphans", restore_settings.script_runner_service])
        _run_remote_compose(restore_settings, ["stop", "web"])

        remote_exec: list[str] = [
            "exec",
            "-T",
            "--user",
            "root",
        ]
        _add_toggle_env_flags(remote_exec, bootstrap_only=bootstrap_only, no_sanitize=no_sanitize)

        remote_exec.extend(
            [
                restore_settings.script_runner_service,
                "python3",
                "-u",
                RESTORE_SCRIPT,
            ]
        )
        _add_toggle_args(remote_exec, bootstrap_only=bootstrap_only, no_sanitize=no_sanitize)

        try:
            _run_remote_compose(restore_settings, remote_exec)
        except CommandError as error:
            _handle_restore_exit(error)
        _run_remote_compose(restore_settings, ["up", "-d", "--remove-orphans", "web"])
    else:
        ensure_local_bind_mounts(restore_settings)
        write_env_file(restore_settings.env_file, env_values)

        stack_started = False

        def _ensure_stack_running() -> None:
            nonlocal stack_started
            if stack_started:
                return
            _run_local_compose(
                restore_settings,
                ["up", "-d", "--remove-orphans", *restore_settings.services],
                check=False,
            )
            stack_started = True

        if "database" in restore_settings.services:
            _run_local_compose(restore_settings, ["up", "-d", "--remove-orphans", "database"], check=False)
            try:
                wait_for_local_service(restore_settings, "database")
            except ValueError:
                _ensure_stack_running()
                wait_for_local_service(restore_settings, "database")

        _run_local_compose(
            restore_settings,
            ["up", "-d", "--remove-orphans", restore_settings.script_runner_service],
            check=False,
        )
        try:
            wait_for_local_service(restore_settings, restore_settings.script_runner_service)
        except ValueError:
            _ensure_stack_running()
            wait_for_local_service(restore_settings, restore_settings.script_runner_service)
        _run_local_compose(restore_settings, ["stop", "web"], check=False)

        restore_env_values = _restore_script_environment(env_values)
        # Pass restore settings via process environment + name-only `-e KEY`
        # flags so secrets do not appear in the docker compose command line.
        exec_environment = dict(local_compose_env(restore_settings))
        exec_environment.update(restore_env_values)

        exec_extra = [
            "exec",
            "-T",
            "--user",
            "root",
        ]
        _add_exec_env_names(exec_extra, restore_env_values.keys())
        _add_toggle_env_flags(exec_extra, bootstrap_only=bootstrap_only, no_sanitize=no_sanitize)
        exec_extra.extend(
            [
                restore_settings.script_runner_service,
                "python3",
                "-u",
                RESTORE_SCRIPT,
            ]
        )
        _add_toggle_args(exec_extra, bootstrap_only=bootstrap_only, no_sanitize=no_sanitize)

        try:
            run_process(
                local_compose_command(restore_settings, exec_extra),
                cwd=restore_settings.repo_root,
                env=exec_environment,
            )
        except CommandError as error:
            _handle_restore_exit(error)
        _run_local_compose(restore_settings, ["up", "-d", "--remove-orphans", "web"], check=False)

    _logger.info("Restore completed for stack %s", stack_name)
    return 0
