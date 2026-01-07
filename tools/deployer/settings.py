import logging
import os
import shlex
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

_logger = logging.getLogger(__name__)


def _paths_relative_to_repo(paths: Iterable[Path], repo_root: Path) -> list[str]:
    entries: list[str] = []
    for path in paths:
        try:
            entries.append(str(path.relative_to(repo_root)))
        except ValueError:
            entries.append(str(path))
    return entries


def discover_repo_root(start_directory: Path) -> Path:
    current = start_directory.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    return current


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def split_values(raw_value: str | None) -> tuple[str, ...]:
    if not raw_value:
        return ()
    tokens = raw_value.replace("\n", ",").replace(":", ",").split(",")
    cleaned: list[str] = []
    for token in tokens:
        item = token.strip()
        if item:
            cleaned.append(item)
    return tuple(cleaned)


def split_modules(raw_value: str | None) -> tuple[str, ...]:
    modules: list[str] = []
    for item in split_values(raw_value):
        modules.append(item)
    return tuple(modules)


def _map_addon_path(raw: str, repo_root: Path) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(raw))
    path = Path(expanded)
    if not path.is_absolute():
        return (repo_root / path).resolve()
    normalized = path.as_posix()
    if normalized == "/volumes/addons":
        return (repo_root / "addons").resolve()
    if normalized.startswith("/volumes/addons/"):
        suffix = normalized.removeprefix("/volumes/addons/")
        return (repo_root / "addons" / suffix).resolve()
    if normalized == "/opt/project/addons":
        return (repo_root / "addons").resolve()
    if normalized.startswith("/opt/project/addons/"):
        suffix = normalized.removeprefix("/opt/project/addons/")
        return (repo_root / "addons" / suffix).resolve()
    if normalized == "/volumes/extra_addons":
        return (repo_root / "extra_addons").resolve()
    if normalized.startswith("/volumes/extra_addons/"):
        suffix = normalized.removeprefix("/volumes/extra_addons/")
        return (repo_root / "extra_addons" / suffix).resolve()
    if normalized == "/opt/extra_addons":
        return (repo_root / "extra_addons").resolve()
    if normalized.startswith("/opt/extra_addons/"):
        suffix = normalized.removeprefix("/opt/extra_addons/")
        return (repo_root / "extra_addons" / suffix).resolve()
    return path


def _resolve_addon_dirs(environment: dict[str, str], repo_root: Path) -> list[Path]:
    raw_dirs = environment.get("LOCAL_ADDONS_DIRS") or environment.get("ODOO_ADDONS_PATH") or ""
    candidates = [_map_addon_path(item, repo_root) for item in split_values(raw_dirs)]
    resolved: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if not path.exists() or not path.is_dir():
            continue
        if path in seen:
            continue
        resolved.append(path)
        seen.add(path)
    if not resolved:
        fallback = repo_root / "addons"
        if fallback.exists() and fallback.is_dir():
            resolved.append(fallback.resolve())
    return resolved


def resolve_addon_dirs(environment: dict[str, str], repo_root: Path) -> tuple[Path, ...]:
    return tuple(_resolve_addon_dirs(environment, repo_root))


def _discover_modules_from_dirs(addon_dirs: Iterable[Path]) -> tuple[str, ...]:
    discovered: set[str] = set()
    for base in addon_dirs:
        if not base.exists() or not base.is_dir():
            continue
        for child in base.iterdir():
            if not child.is_dir():
                continue
            if (child / "__manifest__.py").exists() or (child / "__openerp__.py").exists():
                discovered.add(child.name)
    return tuple(sorted(discovered))


def discover_local_modules(environment: dict[str, str], repo_root: Path) -> tuple[str, ...]:
    addon_dirs = _resolve_addon_dirs(environment, repo_root)
    return _discover_modules_from_dirs(addon_dirs)


AUTO_INSTALLED_SENTINEL = "__AUTO_INSTALLED__"


def resolve_update_modules(config: "StackConfig", environment: dict[str, str]) -> tuple[str, ...]:
    update_source = config.update_modules_raw or config.update_modules_legacy
    if update_source and update_source.strip().upper() not in {"AUTO", ""}:
        return split_modules(update_source)
    auto_modules = (environment.get("ODOO_AUTO_MODULES") or "").strip()
    if auto_modules and auto_modules.upper() != "AUTO":
        return split_modules(auto_modules)
    return (AUTO_INSTALLED_SENTINEL,)


def infer_project_slug(stack_name: str) -> str | None:
    lowered = stack_name.lower()
    for prefix in ("opw-", "cm-"):
        if lowered.startswith(prefix):
            return prefix[:-1]
    if "-" in stack_name:
        return stack_name.split("-", 1)[0]
    return None


class StackConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    compose_files_raw: str | None = Field(None, alias="DEPLOY_COMPOSE_FILES")
    compose_command_raw: str | None = Field(None, alias="DEPLOY_COMPOSE_COMMAND")
    compose_project_raw: str | None = Field(None, alias="DEPLOY_COMPOSE_PROJECT")
    registry_image: str | None = Field(None, alias="DEPLOY_REGISTRY_IMAGE")
    healthcheck_url_raw: str | None = Field(None, alias="DEPLOY_HEALTHCHECK_URL")
    services_raw: str | None = Field(None, alias="DEPLOY_SERVICES")
    script_runner_raw: str | None = Field(None, alias="DEPLOY_SCRIPT_RUNNER_SERVICE")
    odoo_bin_raw: str | None = Field(None, alias="DEPLOY_ODOO_BIN")
    docker_context_raw: str | None = Field(None, alias="DEPLOY_DOCKER_CONTEXT")
    remote_host_raw: str | None = Field(None, alias="DEPLOY_REMOTE_HOST")
    remote_user_raw: str | None = Field(None, alias="DEPLOY_REMOTE_USER")
    remote_port: int | None = Field(None, alias="DEPLOY_REMOTE_PORT")
    remote_stack_path_raw: str | None = Field(None, alias="DEPLOY_REMOTE_STACK_PATH")
    remote_env_path_raw: str | None = Field(None, alias="DEPLOY_REMOTE_ENV_PATH")
    image_variable_raw: str | None = Field(None, alias="DEPLOY_IMAGE_VARIABLE")
    project_name: str | None = Field(None, alias="ODOO_PROJECT_NAME")
    docker_image: str | None = Field(None, alias="DOCKER_IMAGE")
    base_url: str | None = Field(None, alias="ODOO_BASE_URL")
    update_modules_raw: str | None = Field(None, alias="ODOO_UPDATE_MODULES")
    update_modules_legacy: str | None = Field(None, alias="ODOO_UPDATE")
    github_token: str | None = Field(None, alias="GITHUB_TOKEN")
    odoo_data_dir: str | None = Field(None, alias="ODOO_DATA_DIR")
    odoo_db_dir: str | None = Field(None, alias="ODOO_DB_DIR")
    odoo_log_dir: str | None = Field(None, alias="ODOO_LOG_DIR")
    odoo_state_root: str | None = Field(None, alias="ODOO_STATE_ROOT")
    odoo_data_host_dir: str | None = Field(None, alias="ODOO_DATA_HOST_DIR")
    odoo_log_host_dir: str | None = Field(None, alias="ODOO_LOG_HOST_DIR")
    odoo_db_host_dir: str | None = Field(None, alias="ODOO_DB_HOST_DIR")


def compute_compose_files(name: str, repo_root: Path, config: StackConfig) -> tuple[Path, ...]:
    """Resolve compose files with layering and delimiter normalization."""

    base_file = repo_root / "docker-compose.yml"
    override_file = repo_root / "docker-compose.override.yml"

    # Normalize and collect any explicitly provided compose files from the environment
    variant_files: list[Path] = []
    if config.compose_files_raw:
        for item in split_values(config.compose_files_raw):  # supports comma or colon
            path = Path(item)
            if not path.is_absolute():
                path = (repo_root / path).resolve()
            variant_files.append(path)
    else:
        # Fallback to a stack-specific config if it exists
        candidate = repo_root / "docker" / "config" / f"{name}.yaml"
        if candidate.exists():
            variant_files.append(candidate.resolve())

    project_slug = infer_project_slug(name)
    if project_slug is None and config.project_name:
        normalized = config.project_name.strip().lower()
        if normalized:
            project_slug = normalized.split("-", 1)[0]

    config_dir = repo_root / "docker" / "config"
    layered_files: list[Path] = []
    base_layer = config_dir / "base.yaml"
    project_layer = config_dir / f"{project_slug}.yaml" if project_slug else None

    # Always start with the primary compose file(s)
    ordered_candidates: list[Path] = []
    if base_file.exists():
        ordered_candidates.append(base_file.resolve())
    if override_file.exists():
        ordered_candidates.append(override_file.resolve())
    if base_layer.exists():
        ordered_candidates.append(base_layer.resolve())
    if project_layer and project_layer.exists():
        ordered_candidates.append(project_layer.resolve())
    ordered_candidates.extend(variant_files)

    # De-duplicate while preserving order
    seen: set[Path] = set()
    for path in ordered_candidates:
        resolved_path = path.resolve()
        if resolved_path not in seen:
            layered_files.append(resolved_path)
            seen.add(resolved_path)

    if not layered_files:
        raise ValueError(f"no compose files resolved for {name}")

    # Log the resolved compose files relative to repo root for readability
    pretty = _paths_relative_to_repo(layered_files, repo_root)
    _logger.debug("Compose files resolved: %s", ", ".join(pretty))

    return tuple(layered_files)


def compute_compose_command(config: StackConfig) -> tuple[str, ...]:
    if config.compose_command_raw:
        return tuple(shlex.split(config.compose_command_raw))
    return "docker", "compose"


def compute_compose_project(name: str, config: StackConfig) -> str:
    if config.compose_project_raw:
        return config.compose_project_raw
    if config.project_name:
        return config.project_name
    return name.replace("/", "-").replace(" ", "-")


def compute_registry_image(config: StackConfig) -> str:
    if config.registry_image:
        return config.registry_image
    if config.docker_image:
        return config.docker_image
    raise ValueError("DEPLOY_REGISTRY_IMAGE missing in env")


def compute_healthcheck_url(config: StackConfig) -> str:
    if config.healthcheck_url_raw:
        return config.healthcheck_url_raw
    if config.base_url:
        return config.base_url.rstrip("/") + "/web/health"
    raise ValueError("DEPLOY_HEALTHCHECK_URL missing in env")


def compute_services(config: StackConfig) -> tuple[str, ...]:
    values = split_values(config.services_raw)
    if values:
        return values
    return "database", "web", "script-runner"


def compute_script_runner(config: StackConfig) -> str:
    if config.script_runner_raw:
        return config.script_runner_raw
    return "script-runner"


def compute_odoo_bin(config: StackConfig) -> str:
    if config.odoo_bin_raw:
        return config.odoo_bin_raw
    return "/odoo/odoo-bin"


def compute_docker_context(repo_root: Path, config: StackConfig) -> Path:
    if config.docker_context_raw:
        context = Path(config.docker_context_raw)
        if not context.is_absolute():
            return (repo_root / context).resolve()
        return context
    return repo_root


def compute_remote_host(config: StackConfig) -> str | None:
    if config.remote_host_raw:
        if config.remote_host_raw.lower() == "local":
            return None
        return config.remote_host_raw
    return None


def compute_remote_user(config: StackConfig, remote_host: str | None) -> str | None:
    if config.remote_user_raw:
        return config.remote_user_raw
    if remote_host:
        return "root"
    return None


def compute_remote_stack_path(_stack_name: str, config: StackConfig, _remote_host: str | None) -> Path | None:
    if config.remote_stack_path_raw:
        return Path(config.remote_stack_path_raw)
    return None


def compute_remote_env_path(config: StackConfig, remote_stack_path: Path | None) -> Path | None:
    if config.remote_env_path_raw:
        return Path(config.remote_env_path_raw)
    if remote_stack_path is not None:
        return remote_stack_path / ".env"
    return None


def compute_image_variable(config: StackConfig) -> str:
    if config.image_variable_raw:
        return config.image_variable_raw
    return "ODOO_IMAGE"


def _write_env_file(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in sorted(values.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class StackSettings:
    name: str
    repo_root: Path
    env_file: Path  # merged environment file used for compose operations
    source_env_file: Path  # stack-specific override file selected by the operator
    environment: dict[str, str]
    state_root: Path
    data_dir: Path
    db_dir: Path
    log_dir: Path
    compose_command: tuple[str, ...]
    compose_project: str
    compose_files: tuple[Path, ...]
    docker_context: Path
    registry_image: str
    healthcheck_url: str
    update_modules: tuple[str, ...]
    services: tuple[str, ...]
    script_runner_service: str
    odoo_bin_path: str
    image_variable_name: str
    remote_host: str | None
    remote_user: str | None
    remote_port: int | None
    remote_stack_path: Path | None
    remote_env_path: Path | None
    github_token: str | None

    def compose_arguments(self) -> list[str]:
        arguments = list(self.compose_command)
        arguments += ["-p", self.compose_project, "--env-file", str(self.env_file)]
        for file_path in self.compose_files:
            arguments += ["-f", str(file_path)]
        return arguments


def load_stack_settings(name: str, env_file: Path | None = None, base_directory: Path | None = None) -> StackSettings:
    base = base_directory if base_directory is not None else Path.cwd()
    repo_root = discover_repo_root(base)
    env_path = select_env_file(name, repo_root, env_file).resolve()
    stack_env_preview = parse_env_file(env_path)

    project_slug = infer_project_slug(name)
    if project_slug is None:
        project_candidate = stack_env_preview.get("ODOO_PROJECT_NAME")
        if project_candidate:
            normalized = project_candidate.strip().lower()
            if normalized:
                project_slug = normalized.split("-", 1)[0]

    env_files_in_order: list[Path] = []
    seen_env_paths: set[Path] = set()

    def _register_env(path: Path) -> None:
        if not path.exists():
            return
        resolved = path.resolve()
        if resolved in seen_env_paths:
            return
        env_files_in_order.append(resolved)
        seen_env_paths.add(resolved)

    _register_env(repo_root / ".env")
    _register_env(repo_root / "docker" / "config" / "base.env")
    if project_slug:
        _register_env(repo_root / "docker" / "config" / f"{project_slug}.env")
    _register_env(env_path)

    raw_environment: dict[str, str] = {}
    resolved_env_chain: list[Path] = []
    for env_file_path in env_files_in_order:
        raw_environment.update(parse_env_file(env_file_path))
        resolved_env_chain.append(env_file_path)

    config = StackConfig.model_validate(raw_environment)

    def _expand_path(raw: str | Path) -> Path:
        text = str(raw)
        expanded = os.path.expandvars(os.path.expanduser(text))
        return Path(expanded).resolve()

    default_state_root = Path.home() / "odoo-ai" / (config.project_name or name)
    state_root_path = _expand_path(config.odoo_state_root or default_state_root)
    data_dir_host = _expand_path(config.odoo_data_host_dir or state_root_path / "data")
    db_dir_host = _expand_path(config.odoo_db_host_dir or state_root_path / "postgres")
    log_dir_host = _expand_path(config.odoo_log_host_dir or state_root_path / "logs")
    compose_env_path = state_root_path / ".compose.env"
    try:
        compose_env_path.parent.mkdir(parents=True, exist_ok=True)
        merged_env_path = compose_env_path
    except OSError:
        fallback_dir = Path.home() / "odoo-ai" / "stack-env"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        merged_env_path = fallback_dir / f"{name}.env"
    compose_command = compute_compose_command(config)
    compose_files = compute_compose_files(name, repo_root, config)
    compose_project = compute_compose_project(name, config)
    docker_context = compute_docker_context(repo_root, config)
    registry_image = compute_registry_image(config)
    healthcheck_url = compute_healthcheck_url(config)
    update_modules = resolve_update_modules(config, raw_environment)
    services = compute_services(config)
    script_runner_service = compute_script_runner(config)
    odoo_bin_path = compute_odoo_bin(config)
    image_variable_name = compute_image_variable(config)
    remote_host = compute_remote_host(config)
    remote_user = compute_remote_user(config, remote_host)
    remote_port = config.remote_port
    remote_stack_path = compute_remote_stack_path(name, config, remote_host)
    remote_env_path = compute_remote_env_path(config, remote_stack_path)
    github_token = config.github_token
    # Persist bind-mount paths back into the environment so downstream compose calls pick up overrides.
    final_environment = raw_environment.copy()
    final_environment["ODOO_STATE_ROOT"] = str(state_root_path)
    final_environment["ODOO_DATA_HOST_DIR"] = str(data_dir_host)
    final_environment["ODOO_LOG_HOST_DIR"] = str(log_dir_host)
    final_environment["ODOO_DB_HOST_DIR"] = str(db_dir_host)
    final_environment["ODOO_DATA_DIR"] = "/volumes/data"
    final_environment["ODOO_LOG_DIR"] = "/volumes/logs"
    final_environment["ODOO_DB_DIR"] = "/var/lib/postgresql/data"
    final_environment["ODOO_SESSION_DIR"] = "/volumes/logs/sessions"
    _write_env_file(merged_env_path, final_environment)

    # Log the resolved environment layering and important derived values
    chain_pretty = _paths_relative_to_repo(resolved_env_chain, repo_root)
    _logger.debug(
        "Env layering: %s -> merged at %s",
        " -> ".join(chain_pretty) if chain_pretty else "<none>",
        str(merged_env_path.relative_to(repo_root)) if merged_env_path.is_relative_to(repo_root) else str(
            merged_env_path),
    )
    return StackSettings(
        name=name,
        repo_root=repo_root,
        env_file=merged_env_path,
        source_env_file=env_path,
        environment=final_environment,
        state_root=state_root_path,
        data_dir=data_dir_host,
        db_dir=db_dir_host,
        log_dir=log_dir_host,
        compose_command=compose_command,
        compose_project=compose_project,
        compose_files=compose_files,
        docker_context=docker_context,
        registry_image=registry_image,
        healthcheck_url=healthcheck_url,
        update_modules=update_modules,
        services=services,
        script_runner_service=script_runner_service,
        odoo_bin_path=odoo_bin_path,
        image_variable_name=image_variable_name,
        remote_host=remote_host,
        remote_user=remote_user,
        remote_port=remote_port,
        remote_stack_path=remote_stack_path,
        remote_env_path=remote_env_path,
        github_token=github_token,
    )


def select_env_file(name: str, repo_root: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    project_slug = infer_project_slug(name)
    candidates = [
        repo_root / "docker" / "config" / f"{name}.env",
        repo_root / "docker" / "config" / ".env.{name}",
        repo_root / "docker" / "config" / f"{project_slug}.env" if project_slug else None,
        repo_root / ".env",
    ]
    for candidate in [path for path in candidates if path is not None]:
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(f"no env file found for {name}")
