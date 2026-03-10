import logging
import os
import shlex
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import click
from pydantic import BaseModel, ConfigDict, Field

from tools.environment_files import discover_repo_root, parse_env_file
from tools.platform import environment as platform_environment

_logger = logging.getLogger(__name__)


def _paths_relative_to_repo(paths: Iterable[Path], repo_root: Path) -> list[str]:
    entries: list[str] = []
    for path in paths:
        try:
            entries.append(str(path.relative_to(repo_root)))
        except ValueError:
            entries.append(str(path))
    return entries


def _validate_base_env_defaults(
    *,
    base_env_values: dict[str, str],
    resolved_environment: dict[str, str],
) -> None:
    conflicting_keys = sorted(
        key for key, base_value in base_env_values.items() if key in resolved_environment and resolved_environment[key] != base_value
    )
    if not conflicting_keys:
        return

    raise click.ClickException(
        "Conflicting keys between canonical stack env and platform/config/base.env: "
        f"{', '.join(conflicting_keys)}. "
        "platform/config/base.env must match canonical runtime defaults for duplicate keys; "
        "remove conflicting keys there or make values identical."
    )


_FALSY_SETTING_VALUES = {"false", "0", "no", "off"}


def _is_false_setting(raw_value: str | None) -> bool:
    if raw_value is None:
        return False
    normalized = raw_value.strip().lower()
    if not normalized:
        return False
    return normalized in _FALSY_SETTING_VALUES


def security_environment_issues(environment: dict[str, str]) -> tuple[str, ...]:
    issues: list[str] = []
    master_password = (environment.get("ODOO_MASTER_PASSWORD") or "").strip()
    if not master_password:
        issues.append("Missing ODOO_MASTER_PASSWORD (set a non-empty value in .env or the deployment environment).")
    list_db_value = environment.get("ODOO_LIST_DB")
    if not _is_false_setting(list_db_value):
        issues.append("ODOO_LIST_DB must be false to disable the database manager (set ODOO_LIST_DB=False).")
    return tuple(issues)


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


AUTO_INSTALLED_SENTINEL = "__AUTO_INSTALLED__"


def resolve_update_modules(config: "StackConfig") -> tuple[str, ...]:
    update_source = config.update_modules_raw
    if update_source and update_source.strip().upper() not in {"AUTO", ""}:
        return split_values(update_source)
    return (AUTO_INSTALLED_SENTINEL,)


def infer_project_slug(stack_name: str) -> str | None:
    lowered = stack_name.lower()
    for prefix in ("opw-", "cm-"):
        if lowered.startswith(prefix):
            return prefix[:-1]
    if "-" in stack_name:
        return stack_name.split("-", 1)[0]
    return None


def _resolve_platform_runtime_scope(stack_name: str) -> tuple[str, str] | None:
    return platform_environment.resolve_stack_runtime_scope(stack_name)


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
    image_variable_raw: str | None = Field(None, alias="DEPLOY_IMAGE_VARIABLE")
    project_name: str | None = Field(None, alias="ODOO_PROJECT_NAME")
    docker_image: str | None = Field(None, alias="DOCKER_IMAGE")
    base_url: str | None = Field(None, alias="ENV_OVERRIDE_CONFIG_PARAM__WEB__BASE__URL")
    update_modules_raw: str | None = Field(None, alias="ODOO_UPDATE_MODULES")
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

    # Normalize and collect any explicitly provided compose files from the environment.
    # We do not auto-discover per-stack local overlays anymore.
    variant_files: list[Path] = []
    if config.compose_files_raw:
        for item in split_values(config.compose_files_raw):  # supports comma or colon
            path = Path(item)
            if not path.is_absolute():
                path = (repo_root / path).resolve()
            variant_files.append(path)

    project_slug = infer_project_slug(name)
    if project_slug is None and config.project_name:
        normalized = config.project_name.strip().lower()
        if normalized:
            project_slug = normalized.split("-", 1)[0]

    config_dir = repo_root / "platform" / "compose"
    layered_files: list[Path] = []
    base_layer = config_dir / "base.yaml"
    project_layer = config_dir / f"{project_slug}.yaml" if project_slug else None

    # Always start with the primary compose file(s)
    ordered_candidates: list[Path] = []
    if base_file.exists():
        ordered_candidates.append(base_file.resolve())
    if base_layer.exists():
        ordered_candidates.append(base_layer.resolve())
    if override_file.exists():
        ordered_candidates.append(override_file.resolve())
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
    runtime_scope = _resolve_platform_runtime_scope(name)
    context_name = runtime_scope[0] if runtime_scope is not None else None
    instance_name = runtime_scope[1] if runtime_scope is not None else None

    loaded_environment = platform_environment.load_environment_with_details(
        repo_root,
        env_path,
        context_name=context_name,
        instance_name=instance_name,
    )
    raw_environment = loaded_environment.merged_values.copy()
    resolved_env_chain: list[Path] = [env_path]

    base_env_path = repo_root / "platform" / "config" / "base.env"
    if base_env_path.exists():
        base_env_values = parse_env_file(base_env_path)
        _validate_base_env_defaults(
            base_env_values=base_env_values,
            resolved_environment=raw_environment,
        )
        # Base config values are fallback defaults for tool-driven runtime
        # generation. Canonical stack resolution always wins over this file.
        for environment_key, environment_value in base_env_values.items():
            raw_environment.setdefault(environment_key, environment_value)
        resolved_env_chain.insert(0, base_env_path.resolve())

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
    update_modules = resolve_update_modules(config)
    services = compute_services(config)
    script_runner_service = compute_script_runner(config)
    odoo_bin_path = compute_odoo_bin(config)
    image_variable_name = compute_image_variable(config)
    github_token = config.github_token
    # Persist bind-mount paths back into the environment so downstream compose calls pick up overrides.
    final_environment = raw_environment.copy()
    final_environment["ODOO_STATE_ROOT"] = str(state_root_path)
    final_environment["ODOO_DATA_HOST_DIR"] = str(data_dir_host)
    final_environment["ODOO_LOG_HOST_DIR"] = str(log_dir_host)
    final_environment["ODOO_DB_HOST_DIR"] = str(db_dir_host)
    final_environment["ODOO_DATA_MOUNT"] = str(data_dir_host)
    final_environment["ODOO_LOG_MOUNT"] = str(log_dir_host)
    final_environment["ODOO_DB_MOUNT"] = str(db_dir_host)
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
        str(merged_env_path.relative_to(repo_root)) if merged_env_path.is_relative_to(repo_root) else str(merged_env_path),
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
        github_token=github_token,
    )


def select_env_file(name: str, repo_root: Path, explicit: Path | None) -> Path:
    return platform_environment.resolve_stack_env_file(
        repo_root=repo_root,
        stack_name=name,
        explicit_env_file=explicit,
        require_runtime_env=explicit is None,
    )
