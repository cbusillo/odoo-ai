from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .models import ContextDefinition, InstanceDefinition, JsonObject, RuntimeSelection, StackDefinition


def openupgrade_enabled(source_environment: dict[str, str]) -> bool:
    raw_value = source_environment.get("OPENUPGRADE_ENABLED", "False").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def effective_runtime_addon_repositories(
    *,
    stack_definition: StackDefinition,
    runtime_selection: RuntimeSelection,
    source_environment: dict[str, str],
) -> tuple[str, ...]:
    effective_repositories = list(runtime_selection.effective_addon_repositories)

    if openupgrade_enabled(source_environment):
        openupgrade_repository = f"OCA/OpenUpgrade@{stack_definition.odoo_version}"
        if openupgrade_repository not in effective_repositories:
            effective_repositories.append(openupgrade_repository)

    return tuple(effective_repositories)


def merge_effective_modules(context_definition: ContextDefinition, instance_definition: InstanceDefinition) -> tuple[str, ...]:
    effective_install_modules: list[str] = []
    for module_name in context_definition.install_modules:
        if module_name not in effective_install_modules:
            effective_install_modules.append(module_name)
    for module_name in instance_definition.install_modules_add:
        if module_name not in effective_install_modules:
            effective_install_modules.append(module_name)
    return tuple(effective_install_modules)


def merge_effective_addon_repositories(
    stack_definition: StackDefinition,
    context_definition: ContextDefinition,
    instance_definition: InstanceDefinition,
) -> tuple[str, ...]:
    effective_addon_repositories: list[str] = []
    for repository_name in stack_definition.addon_repositories:
        if repository_name not in effective_addon_repositories:
            effective_addon_repositories.append(repository_name)
    for repository_name in context_definition.addon_repositories_add:
        if repository_name not in effective_addon_repositories:
            effective_addon_repositories.append(repository_name)
    for repository_name in instance_definition.addon_repositories_add:
        if repository_name not in effective_addon_repositories:
            effective_addon_repositories.append(repository_name)
    return tuple(effective_addon_repositories)


def merge_effective_runtime_env(
    stack_definition: StackDefinition,
    context_definition: ContextDefinition,
    instance_definition: InstanceDefinition,
) -> dict[str, str]:
    effective_runtime_env: dict[str, str] = {}
    runtime_sources = (
        stack_definition.runtime_env,
        context_definition.runtime_env,
        instance_definition.runtime_env,
    )
    for runtime_source in runtime_sources:
        for key, raw_value in runtime_source.items():
            effective_runtime_env[key] = str(raw_value)
    return effective_runtime_env


def port_seed_for_context(context_name: str) -> tuple[int, int, int]:
    context_port_map = {
        "opw": (8069, 8072, 15432),
        "cm": (9069, 9072, 25432),
    }
    return context_port_map.get(context_name, (11069, 11072, 45432))


def port_offset_for_instance(instance_name: str) -> int:
    if instance_name == "local":
        return 0
    if instance_name == "dev":
        return 100
    if instance_name == "testing":
        return 200
    if instance_name == "prod":
        return 300
    return 0


def resolve_local_platform_state_root(stack_definition: StackDefinition, discover_repo_root: Callable[[Path], Path]) -> Path:
    configured_root = stack_definition.state_root.strip()
    if configured_root:
        expanded_state_root = Path(configured_root).expanduser()
        if expanded_state_root.is_absolute():
            return expanded_state_root
        return (discover_repo_root(Path.cwd()) / expanded_state_root).resolve()
    return (discover_repo_root(Path.cwd()) / ".platform" / "state").resolve()


def resolve_runtime_selection(
    stack_definition: StackDefinition,
    context_name: str,
    instance_name: str,
    discover_repo_root: Callable[[Path], Path],
) -> RuntimeSelection:
    if context_name not in stack_definition.contexts:
        available_contexts = ", ".join(sorted(stack_definition.contexts))
        raise ValueError(f"Unknown context '{context_name}'. Available: {available_contexts}")

    context_definition = stack_definition.contexts[context_name]
    if instance_name not in context_definition.instances:
        available_instances = ", ".join(sorted(context_definition.instances))
        raise ValueError(
            f"Unknown instance '{instance_name}' for context '{context_name}'. "
            f"Available: {available_instances}"
        )
    instance_definition = context_definition.instances[instance_name]

    effective_install_modules = merge_effective_modules(context_definition, instance_definition)
    effective_addon_repositories = merge_effective_addon_repositories(
        stack_definition,
        context_definition,
        instance_definition,
    )
    effective_runtime_env = merge_effective_runtime_env(
        stack_definition,
        context_definition,
        instance_definition,
    )

    base_web_port, base_longpoll_port, base_db_port = port_seed_for_context(context_name)
    instance_offset = port_offset_for_instance(instance_name)
    web_host_port = base_web_port + instance_offset
    longpoll_host_port = base_longpoll_port + instance_offset
    db_host_port = base_db_port + instance_offset

    database_name = instance_definition.database or context_definition.database or context_name
    state_root_path = resolve_local_platform_state_root(stack_definition, discover_repo_root)
    state_path = state_root_path / f"{context_name}-{instance_name}"
    data_volume_name = f"odoo-{context_name}-{instance_name}-data"
    log_volume_name = f"odoo-{context_name}-{instance_name}-logs"
    db_volume_name = f"odoo-{context_name}-{instance_name}-db"

    return RuntimeSelection(
        context_name=context_name,
        instance_name=instance_name,
        context_definition=context_definition,
        instance_definition=instance_definition,
        database_name=database_name,
        project_name=f"odoo-{context_name}-{instance_name}",
        state_path=state_path,
        data_mount=state_path / "data",
        runtime_conf_host_path=state_path / "data" / "platform.odoo.conf",
        data_volume_name=data_volume_name,
        log_volume_name=log_volume_name,
        db_volume_name=db_volume_name,
        web_host_port=web_host_port,
        longpoll_host_port=longpoll_host_port,
        db_host_port=db_host_port,
        runtime_odoo_conf_path="/tmp/platform.odoo.conf",
        effective_install_modules=effective_install_modules,
        effective_addon_repositories=effective_addon_repositories,
        effective_runtime_env=effective_runtime_env,
    )


def write_runtime_odoo_conf_file(
    runtime_selection: RuntimeSelection,
    stack_definition: StackDefinition,
    source_environment: dict[str, str],
) -> Path:
    runtime_selection.runtime_conf_host_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_conf_file = runtime_selection.runtime_conf_host_path

    lines: list[str] = [
        "[options]",
        f"db_name = {runtime_selection.database_name}",
        f"db_user = {source_environment.get('ODOO_DB_USER', 'odoo')}",
        f"db_password = {source_environment.get('ODOO_DB_PASSWORD', '')}",
        "db_host = database",
        "db_port = 5432",
        "list_db = False",
        f"addons_path = {','.join(stack_definition.addons_path)}",
        "data_dir = /volumes/data",
        "",
        f"; context={runtime_selection.context_name}",
        f"; instance={runtime_selection.instance_name}",
        f"; install_modules={','.join(runtime_selection.effective_install_modules)}",
    ]

    runtime_conf_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return runtime_conf_file


def render_runtime_env(runtime_values: dict[str, str]) -> str:
    return "\n".join(f"{key}={value}" for key, value in runtime_values.items()) + "\n"


def runtime_env_diff(existing_values: dict[str, str], proposed_values: dict[str, str]) -> JsonObject:
    added_keys = sorted(key for key in proposed_values if key not in existing_values)
    removed_keys = sorted(key for key in existing_values if key not in proposed_values)
    changed_keys = sorted(
        key for key in proposed_values if key in existing_values and proposed_values[key] != existing_values[key]
    )
    unchanged_count = len(proposed_values) - len(added_keys) - len(changed_keys)
    return {
        "added_keys": added_keys,
        "removed_keys": removed_keys,
        "changed_keys": changed_keys,
        "unchanged_key_count": unchanged_count,
    }
