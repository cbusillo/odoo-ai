from __future__ import annotations

from pathlib import Path

from .models import RuntimeSelection, StackDefinition


def _resolve_pycharm_addons_paths(repo_root: Path, stack_definition: StackDefinition) -> list[str]:
    """Render PyCharm addons_path values without mirroring Odoo sources into the repo.

    The runtime stack uses container paths. Keep those values as-is, except map the
    project addons mount to the local workspace path so local addons stay editable.
    """

    container_to_host_path = {
        "/opt/project/addons": repo_root / "addons",
    }
    resolved_paths: list[str] = []
    for addons_path in stack_definition.addons_path:
        mapped_path = container_to_host_path.get(addons_path)
        if mapped_path is None:
            resolved_paths.append(addons_path)
            continue
        resolved_paths.append(str(mapped_path))
    return resolved_paths


def write_pycharm_odoo_conf(
    *,
    repo_root: Path,
    runtime_selection: RuntimeSelection,
    stack_definition: StackDefinition,
    source_environment: dict[str, str],
) -> Path:
    """Write an IDE-oriented Odoo config.

    This intentionally avoids copying Odoo core/enterprise sources into the
    repository. PyCharm remote interpreters should resolve those from remote
    sources managed by the IDE itself.
    """

    ide_directory = repo_root / ".platform" / "ide"
    ide_directory.mkdir(parents=True, exist_ok=True)
    ide_config_path = ide_directory / f"{runtime_selection.context_name}.{runtime_selection.instance_name}.odoo.conf"

    addons_paths = _resolve_pycharm_addons_paths(repo_root, stack_definition)
    host_data_directory = runtime_selection.state_path / "data"

    lines = [
        "[options]",
        f"db_name = {runtime_selection.database_name}",
        f"db_user = {source_environment.get('ODOO_DB_USER', 'odoo')}",
        f"db_password = {source_environment.get('ODOO_DB_PASSWORD', '')}",
        "db_host = 127.0.0.1",
        f"db_port = {runtime_selection.db_host_port}",
        "list_db = False",
        f"addons_path = {','.join(addons_paths)}",
        f"data_dir = {host_data_directory}",
        "",
        f"; context={runtime_selection.context_name}",
        f"; instance={runtime_selection.instance_name}",
        "; generated_for=pycharm",
    ]
    ide_config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ide_config_path
