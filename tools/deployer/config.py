from __future__ import annotations

import shlex
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .env_utils import load_env_values

LANES = {"addon", "core"}


def _ensure_sequence(value: str | Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def _normalise_repository(value: str) -> str:
    return value.lower()


def _split_modules(value: str | Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        candidates = (part.strip() for part in value.replace("\n", ",").split(","))
    else:
        candidates = (part.strip() for item in value for part in str(item).split(","))
    return tuple(module for module in candidates if module)


def _resolve_path(
    raw: str | Path | None,
    *,
    base: Path,
    default: str | Path | None = None,
) -> Path:
    target = raw if raw is not None else default
    if target is None:
        msg = "Configuration value is required"
        raise ValueError(msg)

    if isinstance(target, Path):
        path = target
    else:
        path = Path(str(target)).expanduser()

    if not path.is_absolute():
        path = (base / path).resolve()

    return path


def _command_tuple(
    value: Sequence[str] | str | None,
    *,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return tuple(shlex.split(value))
    return tuple(str(item) for item in value)


def _command_optional(value: Sequence[str] | str | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return tuple(shlex.split(value))
    return tuple(str(item) for item in value)


def _default_repo_root(base_dir: Path) -> Path:
    for candidate in (base_dir, *base_dir.parents):
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    return base_dir


def _default_compose_files(name: str, repo_root: Path, stack_root: Path) -> tuple[Path, ...]:
    candidates = [
        repo_root / "docker-compose.yml",
        stack_root / "compose.override.yml",
        stack_root / "docker-compose.override.yml",
    ]
    files = tuple(path for path in candidates if path.exists())
    if not files:
        msg = f"Stack '{name}' must reference at least one compose file"
        raise ValueError(msg)
    return files


def _default_addons_root(name: str, stack_root: Path, repo_root: Path, env_values: Mapping[str, str]) -> Path:
    if env_value := env_values.get("DEPLOY_ADDONS_ROOT"):
        return Path(env_value).expanduser()
    stack_addons = stack_root / "addons"
    if stack_addons.exists():
        return stack_addons
    if name.endswith("dev") or "dev" in name:
        return stack_root
    return repo_root / "addons"


class RouteConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    repositories: tuple[str, ...]
    branches: tuple[str, ...]
    stack: str
    lane: str = "addon"
    modules: tuple[str, ...] | None = None

    @model_validator(mode="before")
    @classmethod
    def _apply_aliases(cls, data: Mapping[str, object]) -> Mapping[str, object]:
        mutable = dict(data)
        if "repositories" not in mutable and "repository" in mutable:
            mutable["repositories"] = mutable.pop("repository")
        if "branches" not in mutable and "branch" in mutable:
            mutable["branches"] = mutable.pop("branch")
        return mutable

    @field_validator("repositories", "branches", mode="before")
    @classmethod
    def _coerce_sequence(cls, value: str | Sequence[str]) -> tuple[str, ...]:
        result = _ensure_sequence(value)
        if not result:
            msg = "Route requires at least one repository/branch"
            raise ValueError(msg)
        return result

    @field_validator("repositories")
    @classmethod
    def _normalise_repositories(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_normalise_repository(item) for item in value)

    @field_validator("lane")
    @classmethod
    def _validate_lane(cls, value: str) -> str:
        if value not in LANES:
            msg = f"Unsupported lane '{value}' (expected one of {sorted(LANES)})"
            raise ValueError(msg)
        return value

    @field_validator("modules", mode="before")
    @classmethod
    def _split_modules_field(cls, value: str | Sequence[str] | None) -> tuple[str, ...] | None:
        modules = _split_modules(value)
        return modules or None


class StackConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    stack_root: str | Path
    repo_root: str | Path | None = None
    env_file: str | Path | None = None
    compose_files: Sequence[str | Path] | str | None = None
    docker_compose: Sequence[str] | str | None = None
    queue_dir: str | Path | None = None
    state_dir: str | Path | None = None
    addons_root: str | Path | None = None
    healthcheck: str | None = None
    healthcheck_url: str | None = None
    project: str | None = None
    modules_default: tuple[str, ...] | str | None = None
    wake_command: Sequence[str] | str | None = None
    debounce_seconds: int | str | None = None

    @field_validator("modules_default", mode="before")
    @classmethod
    def _split_modules_field(cls, value: str | Sequence[str] | None) -> tuple[str, ...] | None:
        modules = _split_modules(value)
        return modules or None

    @field_validator("compose_files", mode="before")
    @classmethod
    def _coerce_compose_files(cls, value: Sequence[str | Path] | str | None) -> tuple[str | Path, ...] | None:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            raw = value.replace("\n", ",").replace(":", ",")
            parts = [item.strip() for item in raw.split(",") if item.strip()]
            return tuple(parts)
        if isinstance(value, Sequence):
            return tuple(value)
        return None

    @field_validator("docker_compose", "wake_command", mode="before")
    @classmethod
    def _coerce_command(cls, value: Sequence[str] | str | None) -> tuple[str, ...] | None:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            return tuple(shlex.split(value))
        return tuple(str(item) for item in value)

    @field_validator("debounce_seconds", mode="before")
    @classmethod
    def _coerce_debounce(cls, value: int | str | None) -> int | None:
        if value in (None, ""):
            return None
        return int(value)


class DeployConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    webhook_secret_file: str | Path
    repo_root: str | Path | None = None
    docker_compose: Sequence[str] | str | None = None
    gitmodules: str | Path | None = None
    stacks: list[StackConfig]
    routes: list[RouteConfig]


@dataclass(slots=True)
class RouteSettings:
    repositories: tuple[str, ...]
    branches: tuple[str, ...]
    stack: str
    lane: str
    modules: tuple[str, ...] | None

    def matches(self, repository: str, branch: str) -> bool:
        repo_key = _normalise_repository(repository)
        repo_match = "*" in self.repositories or repo_key in self.repositories
        branch_match = "*" in self.branches or branch in self.branches
        return repo_match and branch_match


@dataclass(slots=True)
class StackSettings:
    name: str
    stack_root: Path
    repo_root: Path
    env_file: Path
    docker_compose: tuple[str, ...]
    compose_files: tuple[Path, ...]
    project: str
    queue_dir: Path
    state_dir: Path
    addons_root: Path
    modules_default: tuple[str, ...]
    healthcheck_url: str
    debounce_seconds: int | None
    wake_command: tuple[str, ...] | None
    environment: Mapping[str, str]


@dataclass(slots=True)
class DeploySettings:
    webhook_secret_file: Path
    gitmodules_path: Path
    stacks: dict[str, StackSettings]
    routes: tuple[RouteSettings, ...]

    def stack_for(self, name: str) -> StackSettings:
        try:
            return self.stacks[name]
        except KeyError as exc:
            msg = f"Unknown stack '{name}'"
            raise KeyError(msg) from exc

    def find_route(self, repository: str, branch: str) -> RouteSettings | None:
        for route in self.routes:
            if route.matches(repository, branch):
                return route
        return None

    def modules_for_route(self, route: RouteSettings) -> list[str]:
        if route.modules:
            return list(route.modules)
        stack = self.stack_for(route.stack)
        return list(stack.modules_default)


def _load_routes(route_configs: Iterable[RouteConfig]) -> tuple[RouteSettings, ...]:
    routes: list[RouteSettings] = []
    for route in route_configs:
        routes.append(
            RouteSettings(
                repositories=route.repositories,
                branches=route.branches,
                stack=route.stack,
                lane=route.lane,
                modules=route.modules,
            )
        )
    return tuple(routes)


def _load_stack(
    config: StackConfig,
    *,
    base_dir: Path,
    global_repo_root: Path,
    global_compose_cmd: tuple[str, ...],
) -> StackSettings:
    name = config.name
    stack_root = _resolve_path(config.stack_root, base=base_dir)
    repo_root = _resolve_path(config.repo_root, base=base_dir, default=global_repo_root)
    env_file = _resolve_path(config.env_file, base=base_dir, default=stack_root / ".env")

    env_values = load_env_values(env_file, missing_ok=True)

    compose_value = config.compose_files
    if compose_value is None:
        env_compose = env_values.get("DEPLOY_COMPOSE_FILES")
        if env_compose:
            compose_value = tuple(part.strip() for part in env_compose.split(":") if part.strip())

    compose_files: tuple[Path, ...]
    if compose_value:
        compose_files = tuple(
            _resolve_path(path, base=base_dir)
            for path in _ensure_sequence(compose_value)
        )
    else:
        compose_files = ()
    if not compose_files:
        compose_files = _default_compose_files(name, repo_root, stack_root)

    docker_compose_cmd = _command_tuple(config.docker_compose, default=global_compose_cmd)
    if not docker_compose_cmd:
        msg = f"Stack '{name}' requires a docker compose command"
        raise ValueError(msg)

    queue_value = config.queue_dir or env_values.get("DEPLOY_QUEUE_DIR")
    queue_dir = _resolve_path(queue_value, base=stack_root, default=stack_root / ".queue")

    state_value = config.state_dir or env_values.get("DEPLOY_STATE_DIR")
    state_dir = _resolve_path(state_value, base=stack_root, default=stack_root / ".deployed")

    addons_value = config.addons_root or env_values.get("DEPLOY_ADDONS_ROOT")
    addons_root = _resolve_path(
        addons_value,
        base=base_dir,
        default=_default_addons_root(name, stack_root, repo_root, env_values),
    )

    healthcheck = (
        config.healthcheck
        or config.healthcheck_url
        or env_values.get("DEPLOY_HEALTHCHECK_URL")
    )
    if not healthcheck:
        msg = f"Stack '{name}' missing healthcheck URL"
        raise ValueError(msg)

    project = config.project or env_values.get("ODOO_PROJECT_NAME") or name
    if not project:
        msg = f"Stack '{name}' requires 'project' or ODOO_PROJECT_NAME in env"
        raise ValueError(msg)

    modules_default = config.modules_default or _split_modules(env_values.get("ODOO_UPDATE"))
    wake_command = _command_optional(config.wake_command or env_values.get("DEPLOY_WAKE_COMMAND"))

    debounce_seconds: int | None
    if config.debounce_seconds is not None:
        debounce_seconds = int(config.debounce_seconds)
    else:
        debounce_env = env_values.get("DEPLOY_DEBOUNCE_SECONDS")
        debounce_seconds = int(debounce_env) if debounce_env else None

    return StackSettings(
        name=name,
        stack_root=stack_root,
        repo_root=repo_root,
        env_file=env_file,
        docker_compose=docker_compose_cmd,
        compose_files=compose_files,
        project=project,
        queue_dir=queue_dir,
        state_dir=state_dir,
        addons_root=addons_root,
        modules_default=modules_default,
        healthcheck_url=str(healthcheck),
        debounce_seconds=debounce_seconds,
        wake_command=wake_command,
        environment=env_values,
    )


def load_settings(config_path: Path) -> DeploySettings:
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    base_dir = config_path.parent.resolve()

    config_model = DeployConfig.model_validate(data)

    webhook_secret_file = _resolve_path(config_model.webhook_secret_file, base=base_dir)

    global_repo_root = _resolve_path(
        config_model.repo_root,
        base=base_dir,
        default=_default_repo_root(base_dir),
    )

    compose_cmd = _command_tuple(config_model.docker_compose, default=("docker", "compose"))
    if not compose_cmd:
        msg = "A docker compose command must be provided"
        raise ValueError(msg)

    if not config_model.stacks:
        msg = "At least one stack must be configured"
        raise ValueError(msg)

    stacks: dict[str, StackSettings] = {}
    for stack_cfg in config_model.stacks:
        stack = _load_stack(
            stack_cfg,
            base_dir=base_dir,
            global_repo_root=global_repo_root,
            global_compose_cmd=compose_cmd,
        )
        stacks[stack.name] = stack

    if config_model.gitmodules is not None:
        gitmodules = _resolve_path(config_model.gitmodules, base=base_dir)
    else:
        first_stack = next(iter(stacks.values()))
        gitmodules = first_stack.repo_root / ".gitmodules"

    if not config_model.routes:
        msg = "At least one route must be configured"
        raise ValueError(msg)
    routes = _load_routes(config_model.routes)

    return DeploySettings(
        webhook_secret_file=webhook_secret_file,
        gitmodules_path=gitmodules,
        stacks=stacks,
        routes=routes,
    )
