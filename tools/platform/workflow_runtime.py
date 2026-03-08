from __future__ import annotations

import json
import textwrap
from collections.abc import Callable
from pathlib import Path

import click

from tools.deployer.command import CommandError

from .models import ContextDefinition, LoadedStack, RuntimeSelection, StackDefinition


def ordered_instance_names(context_definition: ContextDefinition) -> list[str]:
    preferred_order = ("local", "dev", "testing", "prod")
    ordered_names = [instance_name for instance_name in preferred_order if instance_name in context_definition.instances]
    for instance_name in sorted(context_definition.instances):
        if instance_name not in ordered_names:
            ordered_names.append(instance_name)
    return ordered_names


def _resolve_restore_explicit_env_file(*, repo_root: Path, env_file: Path | None) -> Path | None:
    if env_file is None:
        return None

    resolved_env_file = env_file if env_file.is_absolute() else (repo_root / env_file)
    if not resolved_env_file.exists():
        raise click.ClickException(f"Env file not found: {resolved_env_file}")
    return resolved_env_file


def _ensure_runtime_env_file(repo_root: Path, context_name: str, instance_name: str) -> Path:
    runtime_env_file = repo_root / ".platform" / "env" / f"{context_name}.{instance_name}.env"
    if not runtime_env_file.exists():
        raise click.ClickException(
            f"Runtime env file not found: {runtime_env_file}. Run 'uv run platform up --context {context_name} --instance {instance_name}' first."
        )
    return runtime_env_file


def _openupgrade_exec_command(*, force: bool, reset_versions: bool) -> list[str]:
    command = [
        "python3",
        "/volumes/scripts/run_openupgrade.py",
    ]
    if force:
        command.append("--force")
    if reset_versions:
        command.append("--reset-versions")
    return command


def _compose_exec(
    runtime_env_file: Path,
    container_service: str,
    container_command: list[str],
    *,
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_fn: Callable[[list[str]], None],
) -> None:
    compose_command = compose_base_command_fn(runtime_env_file)
    run_command_fn(compose_command + ["exec", "-T", container_service] + container_command)


def _compose_exec_with_input(
    runtime_env_file: Path,
    container_service: str,
    container_command: list[str],
    input_text: str,
    *,
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_with_input_fn: Callable[[list[str], str], None],
) -> None:
    compose_command = compose_base_command_fn(runtime_env_file)
    run_command_with_input_fn(compose_command + ["exec", "-T", container_service] + container_command, input_text)


def _compose_up_script_runner(
    runtime_env_file: Path,
    *,
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_fn: Callable[[list[str]], None],
) -> None:
    compose_command = compose_base_command_fn(runtime_env_file)
    run_command_fn(compose_command + ["up", "-d", "script-runner"])


def _run_with_web_temporarily_stopped(
    runtime_env_file: Path,
    operation: Callable[[], None],
    *,
    dry_run: bool,
    dry_run_commands: tuple[list[str], ...],
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_best_effort_fn: Callable[[list[str]], int],
    echo_fn: Callable[[str], None],
) -> None:
    compose_command = compose_base_command_fn(runtime_env_file)
    stop_web_command = compose_command + ["stop", "web"]
    up_web_command = compose_command + ["up", "-d", "web"]

    if dry_run:
        echo_fn(f"$ {' '.join(stop_web_command)}")
        for command in dry_run_commands:
            echo_fn(f"$ {' '.join(command)}")
        echo_fn(f"$ {' '.join(up_web_command)}")
        return

    run_command_best_effort_fn(stop_web_command)
    try:
        operation()
    finally:
        run_command_best_effort_fn(up_web_command)


def run_with_web_temporarily_stopped(
    runtime_env_file: Path,
    operation: Callable[[], None],
    *,
    dry_run: bool,
    dry_run_commands: tuple[list[str], ...],
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_best_effort_fn: Callable[[list[str]], int],
    echo_fn: Callable[[str], None],
) -> None:
    _run_with_web_temporarily_stopped(
        runtime_env_file,
        operation,
        dry_run=dry_run,
        dry_run_commands=dry_run_commands,
        compose_base_command_fn=compose_base_command_fn,
        run_command_best_effort_fn=run_command_best_effort_fn,
        echo_fn=echo_fn,
    )


def _apply_admin_password_if_configured(
    runtime_env_file: Path,
    runtime_selection: RuntimeSelection,
    stack_definition: StackDefinition,
    loaded_environment: dict[str, str],
    *,
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_with_input_fn: Callable[[list[str], str], None],
    echo_fn: Callable[[str], None],
) -> None:
    admin_password = loaded_environment.get("ODOO_ADMIN_PASSWORD", "").strip()
    if not admin_password:
        return

    configured_admin_login_raw = loaded_environment.get("ODOO_ADMIN_LOGIN", "")
    configured_admin_login = configured_admin_login_raw.strip() or "admin"
    if not configured_admin_login_raw.strip():
        echo_fn("admin_password_action=defaulted_odoo_admin_login=admin")

    addons_path_argument = ",".join(stack_definition.addons_path)
    odoo_shell_command = [
        "/odoo/odoo-bin",
        "shell",
        "-d",
        runtime_selection.database_name,
        f"--addons-path={addons_path_argument}",
        "--data-dir=/volumes/data",
        "--db_host=database",
        "--db_port=5432",
        f"--db_user={loaded_environment.get('ODOO_DB_USER', 'odoo')}",
        f"--db_password={loaded_environment.get('ODOO_DB_PASSWORD', '')}",
    ]

    script_payload = {
        "password": admin_password,
        "login": configured_admin_login,
    }
    odoo_shell_script = textwrap.dedent("""
import json

payload = json.loads('__PAYLOAD__')
admin_user = env['res.users'].sudo().with_context(active_test=False).search(
    [('login', '=', payload['login'])],
    limit=1,
)
if not admin_user:
    raise ValueError(f"Configured admin user not found: {payload['login']}")
else:
    admin_user.with_context(no_reset_password=True).sudo().password = payload['password']
    print("admin_password_updated=true")
env.cr.commit()
""").replace("__PAYLOAD__", json.dumps(script_payload))

    _compose_exec_with_input(
        runtime_env_file,
        "script-runner",
        odoo_shell_command,
        odoo_shell_script,
        compose_base_command_fn=compose_base_command_fn,
        run_command_with_input_fn=run_command_with_input_fn,
    )


def _assert_active_admin_password_is_not_default(
    runtime_env_file: Path,
    runtime_selection: RuntimeSelection,
    stack_definition: StackDefinition,
    loaded_environment: dict[str, str],
    *,
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_with_input_fn: Callable[[list[str], str], None],
) -> None:
    addons_path_argument = ",".join(stack_definition.addons_path)
    odoo_shell_command = [
        "/odoo/odoo-bin",
        "shell",
        "-d",
        runtime_selection.database_name,
        f"--addons-path={addons_path_argument}",
        "--data-dir=/volumes/data",
        "--db_host=database",
        "--db_port=5432",
        f"--db_user={loaded_environment.get('ODOO_DB_USER', 'odoo')}",
        f"--db_password={loaded_environment.get('ODOO_DB_PASSWORD', '')}",
    ]

    configured_admin_login_raw = loaded_environment.get("ODOO_ADMIN_LOGIN", "")
    configured_admin_login = configured_admin_login_raw.strip() or "admin"
    login_names_to_check = ["admin"]
    if configured_admin_login not in login_names_to_check:
        login_names_to_check.append(configured_admin_login)

    script_payload = {"logins": login_names_to_check}
    odoo_shell_script = textwrap.dedent("""
import json
from odoo.exceptions import AccessDenied

payload = json.loads('__PAYLOAD__')

for login_name in payload['logins']:
    target_user = env['res.users'].sudo().with_context(active_test=False).search(
        [('login', '=', login_name)],
        limit=1,
    )
    if not target_user:
        continue

    authenticated = False
    try:
        auth_info = env['res.users'].sudo().authenticate(
            {'type': 'password', 'login': login_name, 'password': 'admin'},
            {'interactive': False},
        )
        authenticated = bool(auth_info)
    except AccessDenied:
        authenticated = False

    if authenticated:
        raise ValueError(f"Insecure configuration: active password for {login_name} is 'admin'.")

print("admin_default_password_active=false")
""").replace("__PAYLOAD__", json.dumps(script_payload))

    _compose_exec_with_input(
        runtime_env_file,
        "script-runner",
        odoo_shell_command,
        odoo_shell_script,
        compose_base_command_fn=compose_base_command_fn,
        run_command_with_input_fn=run_command_with_input_fn,
    )


def run_restore_workflow(
    *,
    repo_root: Path,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    bootstrap_only: bool,
    no_sanitize: bool,
    dry_run: bool,
    load_stack_fn: Callable[[Path], LoadedStack],
    resolve_runtime_selection_fn: Callable[[StackDefinition, str, str], RuntimeSelection],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    write_runtime_odoo_conf_file_fn: Callable[[RuntimeSelection, StackDefinition, dict[str, str]], Path],
    write_runtime_env_file_fn: Callable[[Path, StackDefinition, RuntimeSelection, dict[str, str]], Path],
    restore_stack_fn: Callable[..., int],
    echo_fn: Callable[[str], None],
) -> None:
    if context_name not in {"cm", "opw"}:
        raise click.ClickException("Restore workflow is currently supported only for cm/opw contexts.")

    restore_stack_name = context_name if instance_name == "local" else f"{context_name}-{instance_name}"
    restore_env_file = _resolve_restore_explicit_env_file(repo_root=repo_root, env_file=env_file)
    if restore_env_file is None:
        stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
        if not stack_file_path.exists():
            raise click.ClickException(f"Stack file not found: {stack_file_path}")
        loaded_stack = load_stack_fn(stack_file_path)
        stack_definition = loaded_stack.stack_definition
        runtime_selection = resolve_runtime_selection_fn(stack_definition, context_name, instance_name)
        _env_file_path, loaded_environment = load_environment_fn(
            repo_root,
            None,
            context_name=context_name,
            instance_name=instance_name,
            collision_mode="error",
        )
        write_runtime_odoo_conf_file_fn(runtime_selection, stack_definition, loaded_environment)
        restore_env_file = write_runtime_env_file_fn(
            repo_root,
            stack_definition,
            runtime_selection,
            loaded_environment,
        )

    if dry_run:
        restore_env_label = str(restore_env_file) if restore_env_file is not None else "<default stack env>"
        echo_fn(f"restore_context={context_name}")
        echo_fn(f"restore_instance={instance_name}")
        echo_fn(f"restore_stack={restore_stack_name}")
        echo_fn(f"restore_env_file={restore_env_label}")
        echo_fn(f"restore_bootstrap_only={str(bootstrap_only).lower()}")
        echo_fn(f"restore_no_sanitize={str(no_sanitize).lower()}")
        return

    try:
        restore_exit_code = restore_stack_fn(
            restore_stack_name,
            env_file=restore_env_file,
            bootstrap_only=bootstrap_only,
            no_sanitize=no_sanitize,
        )
    except (CommandError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    if restore_exit_code != 0:
        raise click.ClickException(f"Restore failed with exit code {restore_exit_code}.")


def _run_openupgrade_workflow(
    *,
    runtime_env_file: Path,
    force: bool,
    reset_versions: bool,
    dry_run: bool,
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_fn: Callable[[list[str]], None],
    run_command_best_effort_fn: Callable[[list[str]], int],
    echo_fn: Callable[[str], None],
) -> None:
    compose_command = compose_base_command_fn(runtime_env_file)
    openupgrade_command = _openupgrade_exec_command(force=force, reset_versions=reset_versions)

    up_script_runner_command = compose_command + ["up", "-d", "script-runner"]
    stop_web_command = compose_command + ["stop", "web"]
    openupgrade_exec_command = compose_command + ["exec", "-T", "script-runner", *openupgrade_command]
    up_web_command = compose_command + ["up", "-d", "web"]

    if dry_run:
        echo_fn(f"$ {' '.join(up_script_runner_command)}")
        echo_fn(f"$ {' '.join(stop_web_command)}")
        echo_fn(f"$ {' '.join(openupgrade_exec_command)}")
        echo_fn(f"$ {' '.join(up_web_command)}")
        return

    run_command_best_effort_fn(stop_web_command)
    try:
        run_command_fn(up_script_runner_command)
        run_command_fn(openupgrade_exec_command)
    finally:
        run_command_best_effort_fn(up_web_command)


def _load_command_runtime_context(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    resolve_runtime_selection_fn: Callable[[StackDefinition, str, str], RuntimeSelection],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
) -> tuple[StackDefinition, RuntimeSelection, dict[str, str], Path]:
    repo_root = discover_repo_root_fn(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    loaded_stack = load_stack_fn(stack_file_path)
    stack_definition = loaded_stack.stack_definition
    runtime_selection = resolve_runtime_selection_fn(stack_definition, context_name, instance_name)
    _env_file_path, loaded_environment = load_environment_fn(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    runtime_env_file = _ensure_runtime_env_file(repo_root, context_name, instance_name)
    return stack_definition, runtime_selection, loaded_environment, runtime_env_file


def run_init_workflow(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    dry_run: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    resolve_runtime_selection_fn: Callable[[StackDefinition, str, str], RuntimeSelection],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_fn: Callable[[list[str]], None],
    run_command_best_effort_fn: Callable[[list[str]], int],
    run_command_with_input_fn: Callable[[list[str], str], None],
    echo_fn: Callable[[str], None],
) -> None:
    stack_definition, runtime_selection, loaded_environment, runtime_env_file = _load_command_runtime_context(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        discover_repo_root_fn=discover_repo_root_fn,
        load_stack_fn=load_stack_fn,
        resolve_runtime_selection_fn=resolve_runtime_selection_fn,
        load_environment_fn=load_environment_fn,
    )

    install_modules = ",".join(runtime_selection.effective_install_modules)
    addons_path_argument = ",".join(stack_definition.addons_path)
    command = [
        "/odoo/odoo-bin",
        "-d",
        runtime_selection.database_name,
        f"--addons-path={addons_path_argument}",
        "--data-dir=/volumes/data",
        "-i",
        install_modules,
        "--db_host=database",
        "--db_port=5432",
        f"--db_user={loaded_environment.get('ODOO_DB_USER', 'odoo')}",
        f"--db_password={loaded_environment.get('ODOO_DB_PASSWORD', '')}",
        "--stop-after-init",
    ]
    if dry_run:
        compose_command = compose_base_command_fn(runtime_env_file)
        _run_with_web_temporarily_stopped(
            runtime_env_file,
            operation=lambda: None,
            dry_run=True,
            dry_run_commands=(
                compose_command + ["up", "-d", "script-runner"],
                compose_command + ["exec", "-T", "script-runner", *command],
            ),
            compose_base_command_fn=compose_base_command_fn,
            run_command_best_effort_fn=run_command_best_effort_fn,
            echo_fn=echo_fn,
        )
        return

    def _run_init_operation() -> None:
        _compose_up_script_runner(
            runtime_env_file,
            compose_base_command_fn=compose_base_command_fn,
            run_command_fn=run_command_fn,
        )
        _compose_exec(
            runtime_env_file,
            "script-runner",
            command,
            compose_base_command_fn=compose_base_command_fn,
            run_command_fn=run_command_fn,
        )
        _apply_admin_password_if_configured(
            runtime_env_file,
            runtime_selection,
            stack_definition,
            loaded_environment,
            compose_base_command_fn=compose_base_command_fn,
            run_command_with_input_fn=run_command_with_input_fn,
            echo_fn=echo_fn,
        )
        _assert_active_admin_password_is_not_default(
            runtime_env_file,
            runtime_selection,
            stack_definition,
            loaded_environment,
            compose_base_command_fn=compose_base_command_fn,
            run_command_with_input_fn=run_command_with_input_fn,
        )

    _run_with_web_temporarily_stopped(
        runtime_env_file,
        operation=_run_init_operation,
        dry_run=False,
        dry_run_commands=(),
        compose_base_command_fn=compose_base_command_fn,
        run_command_best_effort_fn=run_command_best_effort_fn,
        echo_fn=echo_fn,
    )
    echo_fn(f"init={runtime_selection.project_name}")


def run_update_workflow(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    dry_run: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    resolve_runtime_selection_fn: Callable[[StackDefinition, str, str], RuntimeSelection],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_fn: Callable[[list[str]], None],
    run_command_best_effort_fn: Callable[[list[str]], int],
    echo_fn: Callable[[str], None],
) -> None:
    stack_definition, runtime_selection, loaded_environment, runtime_env_file = _load_command_runtime_context(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        discover_repo_root_fn=discover_repo_root_fn,
        load_stack_fn=load_stack_fn,
        resolve_runtime_selection_fn=resolve_runtime_selection_fn,
        load_environment_fn=load_environment_fn,
    )

    update_modules = runtime_selection.context_definition.update_modules
    module_argument = ",".join(runtime_selection.effective_install_modules)
    addons_path_argument = ",".join(stack_definition.addons_path)
    if update_modules.upper() != "AUTO":
        module_argument = update_modules

    command = [
        "/odoo/odoo-bin",
        "-d",
        runtime_selection.database_name,
        f"--addons-path={addons_path_argument}",
        "--data-dir=/volumes/data",
        "-u",
        module_argument,
        "--db_host=database",
        "--db_port=5432",
        f"--db_user={loaded_environment.get('ODOO_DB_USER', 'odoo')}",
        f"--db_password={loaded_environment.get('ODOO_DB_PASSWORD', '')}",
        "--stop-after-init",
    ]
    if dry_run:
        compose_command = compose_base_command_fn(runtime_env_file)
        _run_with_web_temporarily_stopped(
            runtime_env_file,
            operation=lambda: None,
            dry_run=True,
            dry_run_commands=(
                compose_command + ["up", "-d", "script-runner"],
                compose_command + ["exec", "-T", "script-runner", *command],
            ),
            compose_base_command_fn=compose_base_command_fn,
            run_command_best_effort_fn=run_command_best_effort_fn,
            echo_fn=echo_fn,
        )
        return

    def _run_update_operation() -> None:
        _compose_up_script_runner(
            runtime_env_file,
            compose_base_command_fn=compose_base_command_fn,
            run_command_fn=run_command_fn,
        )
        _compose_exec(
            runtime_env_file,
            "script-runner",
            command,
            compose_base_command_fn=compose_base_command_fn,
            run_command_fn=run_command_fn,
        )

    _run_with_web_temporarily_stopped(
        runtime_env_file,
        operation=_run_update_operation,
        dry_run=False,
        dry_run_commands=(),
        compose_base_command_fn=compose_base_command_fn,
        run_command_best_effort_fn=run_command_best_effort_fn,
        echo_fn=echo_fn,
    )
    echo_fn(f"update={runtime_selection.project_name}")


def run_openupgrade_command(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    force: bool,
    reset_versions: bool,
    dry_run: bool,
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    resolve_runtime_selection_fn: Callable[[StackDefinition, str, str], RuntimeSelection],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_fn: Callable[[list[str]], None],
    run_command_best_effort_fn: Callable[[list[str]], int],
    echo_fn: Callable[[str], None],
) -> None:
    repo_root = discover_repo_root_fn(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    loaded_stack = load_stack_fn(stack_file_path)
    stack_definition = loaded_stack.stack_definition
    resolve_runtime_selection_fn(stack_definition, context_name, instance_name)
    load_environment_fn(
        repo_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    runtime_env_file = _ensure_runtime_env_file(repo_root, context_name, instance_name)
    _run_openupgrade_workflow(
        runtime_env_file=runtime_env_file,
        force=force,
        reset_versions=reset_versions,
        dry_run=dry_run,
        compose_base_command_fn=compose_base_command_fn,
        run_command_fn=run_command_fn,
        run_command_best_effort_fn=run_command_best_effort_fn,
        echo_fn=echo_fn,
    )
    if not dry_run:
        echo_fn(f"openupgrade={context_name}-{instance_name}")


def run_workflow(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    workflow: str,
    dry_run: bool,
    no_cache: bool,
    bootstrap_only: bool,
    no_sanitize: bool,
    force: bool,
    reset_versions: bool,
    allow_prod_data_workflow: bool,
    assert_prod_data_workflow_allowed_fn: Callable[..., None],
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    resolve_runtime_selection_fn: Callable[[StackDefinition, str, str], RuntimeSelection],
    load_environment_fn: Callable[..., tuple[Path, dict[str, str]]],
    write_runtime_odoo_conf_file_fn: Callable[[RuntimeSelection, StackDefinition, dict[str, str]], Path],
    write_runtime_env_file_fn: Callable[[Path, StackDefinition, RuntimeSelection, dict[str, str]], Path],
    restore_stack_fn: Callable[..., int],
    compose_base_command_fn: Callable[[Path], list[str]],
    run_command_fn: Callable[[list[str]], None],
    run_command_best_effort_fn: Callable[[list[str]], int],
    run_command_with_input_fn: Callable[[list[str], str], None],
    invoke_platform_command_fn: Callable[..., None],
    echo_fn: Callable[[str], None],
) -> None:
    def run_workflow_phase(phase_name: str) -> None:
        echo_fn(f"workflow_phase_start={phase_name}")
        run_workflow(
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            workflow=phase_name,
            dry_run=dry_run,
            no_cache=no_cache,
            bootstrap_only=bootstrap_only,
            no_sanitize=no_sanitize,
            force=force,
            reset_versions=reset_versions,
            allow_prod_data_workflow=allow_prod_data_workflow,
            assert_prod_data_workflow_allowed_fn=assert_prod_data_workflow_allowed_fn,
            discover_repo_root_fn=discover_repo_root_fn,
            load_stack_fn=load_stack_fn,
            resolve_runtime_selection_fn=resolve_runtime_selection_fn,
            load_environment_fn=load_environment_fn,
            write_runtime_odoo_conf_file_fn=write_runtime_odoo_conf_file_fn,
            write_runtime_env_file_fn=write_runtime_env_file_fn,
            restore_stack_fn=restore_stack_fn,
            compose_base_command_fn=compose_base_command_fn,
            run_command_fn=run_command_fn,
            run_command_best_effort_fn=run_command_best_effort_fn,
            run_command_with_input_fn=run_command_with_input_fn,
            invoke_platform_command_fn=invoke_platform_command_fn,
            echo_fn=echo_fn,
        )
        echo_fn(f"workflow_phase_end={phase_name}")

    assert_prod_data_workflow_allowed_fn(
        instance_name=instance_name,
        workflow=workflow,
        allow_prod_data_workflow=allow_prod_data_workflow,
    )
    normalized_workflow = workflow.strip().lower()
    if normalized_workflow == "restore":
        repo_root = discover_repo_root_fn(Path.cwd())
        run_restore_workflow(
            repo_root=repo_root,
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            bootstrap_only=bootstrap_only,
            no_sanitize=no_sanitize,
            dry_run=dry_run,
            load_stack_fn=load_stack_fn,
            resolve_runtime_selection_fn=resolve_runtime_selection_fn,
            load_environment_fn=load_environment_fn,
            write_runtime_odoo_conf_file_fn=write_runtime_odoo_conf_file_fn,
            write_runtime_env_file_fn=write_runtime_env_file_fn,
            restore_stack_fn=restore_stack_fn,
            echo_fn=echo_fn,
        )
        echo_fn(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "init":
        run_init_workflow(
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            dry_run=dry_run,
            discover_repo_root_fn=discover_repo_root_fn,
            load_stack_fn=load_stack_fn,
            resolve_runtime_selection_fn=resolve_runtime_selection_fn,
            load_environment_fn=load_environment_fn,
            compose_base_command_fn=compose_base_command_fn,
            run_command_fn=run_command_fn,
            run_command_best_effort_fn=run_command_best_effort_fn,
            run_command_with_input_fn=run_command_with_input_fn,
            echo_fn=echo_fn,
        )
        echo_fn(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "update":
        run_update_workflow(
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            dry_run=dry_run,
            discover_repo_root_fn=discover_repo_root_fn,
            load_stack_fn=load_stack_fn,
            resolve_runtime_selection_fn=resolve_runtime_selection_fn,
            load_environment_fn=load_environment_fn,
            compose_base_command_fn=compose_base_command_fn,
            run_command_fn=run_command_fn,
            run_command_best_effort_fn=run_command_best_effort_fn,
            echo_fn=echo_fn,
        )
        echo_fn(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "openupgrade":
        run_openupgrade_command(
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            force=force,
            reset_versions=reset_versions,
            dry_run=dry_run,
            discover_repo_root_fn=discover_repo_root_fn,
            load_stack_fn=load_stack_fn,
            resolve_runtime_selection_fn=resolve_runtime_selection_fn,
            load_environment_fn=load_environment_fn,
            compose_base_command_fn=compose_base_command_fn,
            run_command_fn=run_command_fn,
            run_command_best_effort_fn=run_command_best_effort_fn,
            echo_fn=echo_fn,
        )
        echo_fn(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "restore-init":
        run_workflow_phase("restore")
        run_workflow_phase("init")
        echo_fn(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "restore-update":
        run_workflow_phase("restore")
        run_workflow_phase("update")
        echo_fn(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "restore-init-update":
        run_workflow_phase("restore-init")
        run_workflow_phase("update")
        echo_fn(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "select":
        invoke_platform_command_fn(
            "select",
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            dry_run=False,
        )
        echo_fn(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "info":
        invoke_platform_command_fn(
            "info",
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            json_output=False,
        )
        echo_fn(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "status":
        invoke_platform_command_fn(
            "status",
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            json_output=False,
        )
        echo_fn(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "up":
        invoke_platform_command_fn(
            "up",
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            build_images=True,
            no_cache=no_cache,
        )
        echo_fn(f"workflow={normalized_workflow}")
        return

    if normalized_workflow == "build":
        invoke_platform_command_fn(
            "build",
            stack_file=stack_file,
            context_name=context_name,
            instance_name=instance_name,
            env_file=env_file,
            no_cache=no_cache,
        )
        echo_fn(f"workflow={normalized_workflow}")
        return

    raise click.ClickException(f"Unsupported workflow: {workflow}")
