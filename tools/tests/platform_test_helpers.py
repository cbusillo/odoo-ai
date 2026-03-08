from pathlib import Path


def write_compose_stack_files(repo_root: Path, *, include_override: bool = True) -> None:
    compose_directory = repo_root / "platform" / "compose"
    compose_directory.mkdir(parents=True, exist_ok=True)
    (repo_root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (compose_directory / "base.yaml").write_text("services: {}\n", encoding="utf-8")
    if include_override:
        (repo_root / "docker-compose.override.yml").write_text("services: {}\n", encoding="utf-8")


def write_runtime_env_file(
    repo_root: Path,
    *,
    context_name: str = "opw",
    instance_name: str = "local",
    project_name: str = "odoo-opw-local",
) -> Path:
    runtime_env_file = repo_root / ".platform" / "env" / f"{context_name}.{instance_name}.env"
    runtime_env_file.parent.mkdir(parents=True, exist_ok=True)
    runtime_env_file.write_text(f"ODOO_PROJECT_NAME={project_name}\n", encoding="utf-8")
    return runtime_env_file
