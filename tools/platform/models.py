from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | dict[str, "JsonValue"] | list["JsonValue"]
type JsonObject = dict[str, JsonValue]


class ContextDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database: str | None = None
    install_modules: tuple[str, ...] = ()
    addon_repositories_add: tuple[str, ...] = ()
    runtime_env: dict[str, str | int | float | bool] = Field(default_factory=dict)
    update_modules: str = "AUTO"
    instances: dict[str, "InstanceDefinition"] = Field(default_factory=dict)


class InstanceDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database: str | None = None
    addon_repositories_add: tuple[str, ...] = ()
    install_modules_add: tuple[str, ...] = ()
    runtime_env: dict[str, str | int | float | bool] = Field(default_factory=dict)


class DokployTargetDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: str
    instance: str
    project_name: str = ""
    target_type: Literal["compose", "application"] = "compose"
    target_id: str = ""
    target_name: str = ""
    git_branch: str = ""
    source_git_ref: str = "origin/main"
    require_test_gate: bool = False
    require_prod_gate: bool = False
    deploy_timeout_seconds: int | None = Field(default=None, ge=1)
    healthcheck_enabled: bool = True
    healthcheck_path: str = "/web/health"
    healthcheck_timeout_seconds: int | None = Field(default=None, ge=1)
    env: dict[str, str] = Field(default_factory=dict)
    domains: tuple[str, ...] = ()


class DokploySourceOfTruth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    targets: tuple[DokployTargetDefinition, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _normalize_inherited_targets(cls, raw_value: object) -> object:
        return _normalize_dokploy_source_payload(raw_value)


def _normalize_dokploy_source_payload(raw_value: object) -> object:
    if not isinstance(raw_value, Mapping):
        return raw_value

    normalized_payload = dict(raw_value)
    allowed_top_level_keys = {"defaults", "profiles", "projects", "schema_version", "targets"}
    unknown_keys = sorted(key for key in normalized_payload if key not in allowed_top_level_keys)
    if unknown_keys:
        unknown_key_list = ", ".join(unknown_keys)
        raise ValueError(f"Unknown top-level dokploy keys: {unknown_key_list}")

    raw_targets = normalized_payload.get("targets")
    if not isinstance(raw_targets, list):
        return raw_value

    defaults = _expect_mapping(normalized_payload.get("defaults"), label="defaults")
    raw_profiles = _expect_mapping(normalized_payload.get("profiles"), label="profiles")
    raw_projects = _expect_mapping(normalized_payload.get("projects"), label="projects")

    resolved_profiles: dict[str, dict[str, object]] = {}
    targets: list[object] = []
    for target_index, raw_target in enumerate(raw_targets, start=1):
        if not isinstance(raw_target, Mapping):
            targets.append(raw_target)
            continue

        target_payload = dict(raw_target)
        profile_name = str(target_payload.pop("profile", "") or "").strip()
        merged_target = dict(defaults)
        if profile_name:
            merged_target = _merge_dokploy_settings(
                merged_target,
                _resolve_dokploy_profile(
                    profile_name,
                    raw_profiles=raw_profiles,
                    raw_projects=raw_projects,
                    resolved_profiles=resolved_profiles,
                    active_profiles=(),
                ),
            )
        merged_target = _merge_dokploy_settings(merged_target, target_payload)
        targets.append(
            _resolve_dokploy_project_reference(
                merged_target,
                raw_projects=raw_projects,
                label=f"targets[{target_index}]",
            )
        )

    return {
        "schema_version": normalized_payload.get("schema_version"),
        "targets": targets,
    }


def _resolve_dokploy_profile(
    profile_name: str,
    *,
    raw_profiles: Mapping[str, object],
    raw_projects: Mapping[str, object],
    resolved_profiles: dict[str, dict[str, object]],
    active_profiles: tuple[str, ...],
) -> dict[str, object]:
    if profile_name in resolved_profiles:
        return dict(resolved_profiles[profile_name])
    if profile_name in active_profiles:
        profile_chain = " -> ".join((*active_profiles, profile_name))
        raise ValueError(f"Dokploy profile inheritance cycle detected: {profile_chain}")

    raw_profile = raw_profiles.get(profile_name)
    if raw_profile is None:
        raise ValueError(f"Unknown dokploy profile: {profile_name}")
    if not isinstance(raw_profile, Mapping):
        raise ValueError(f"Dokploy profile '{profile_name}' must be a table/object")

    profile_payload = dict(raw_profile)
    parent_profile_name = str(profile_payload.pop("extends", "") or "").strip()
    merged_profile: dict[str, object] = {}
    if parent_profile_name:
        merged_profile = _resolve_dokploy_profile(
            parent_profile_name,
            raw_profiles=raw_profiles,
            raw_projects=raw_projects,
            resolved_profiles=resolved_profiles,
            active_profiles=(*active_profiles, profile_name),
        )
    merged_profile = _merge_dokploy_settings(merged_profile, profile_payload)
    merged_profile = _resolve_dokploy_project_reference(
        merged_profile,
        raw_projects=raw_projects,
        label=f"profiles.{profile_name}",
    )
    resolved_profiles[profile_name] = dict(merged_profile)
    return merged_profile


def _resolve_dokploy_project_reference(
    payload: dict[str, object],
    *,
    raw_projects: Mapping[str, object],
    label: str,
) -> dict[str, object]:
    resolved_payload = dict(payload)
    raw_project_alias = resolved_payload.pop("project", None)
    if raw_project_alias in (None, ""):
        return resolved_payload

    project_alias = str(raw_project_alias).strip()
    if not project_alias:
        return resolved_payload
    if str(resolved_payload.get("project_name") or "").strip():
        raise ValueError(f"{label} cannot define both project and project_name")

    raw_project_value = raw_projects.get(project_alias)
    if raw_project_value is None:
        raise ValueError(f"Unknown dokploy project alias '{project_alias}' in {label}")
    if isinstance(raw_project_value, str):
        project_name = raw_project_value.strip()
    elif isinstance(raw_project_value, Mapping):
        project_name = str(raw_project_value.get("project_name") or "").strip()
    else:
        raise ValueError(f"Dokploy project alias '{project_alias}' in {label} must be a string or table")
    if not project_name:
        raise ValueError(f"Dokploy project alias '{project_alias}' in {label} is missing project_name")

    resolved_payload["project_name"] = project_name
    return resolved_payload


def _expect_mapping(raw_value: object, *, label: str) -> dict[str, object]:
    if raw_value in (None, ""):
        return {}
    if not isinstance(raw_value, Mapping):
        raise ValueError(f"Dokploy {label} must be a table/object")
    if not all(isinstance(key, str) for key in raw_value):
        raise ValueError(f"Dokploy {label} keys must be strings")
    return dict(raw_value)


def _merge_dokploy_settings(base: Mapping[str, object], overlay: Mapping[str, object]) -> dict[str, object]:
    merged_settings = dict(base)
    for key_name, key_value in overlay.items():
        base_env = merged_settings.get("env")
        if key_name == "env" and isinstance(base_env, Mapping) and isinstance(key_value, Mapping):
            merged_env: dict[str, object] = {}
            for env_key, env_value in base_env.items():
                if isinstance(env_key, str):
                    merged_env[env_key] = env_value
            for env_key, env_value in key_value.items():
                if isinstance(env_key, str):
                    merged_env[env_key] = env_value
            merged_settings["env"] = merged_env
            continue
        merged_settings[key_name] = key_value
    return merged_settings


class StackDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    odoo_version: str
    state_root: str = ""
    addons_path: tuple[str, ...]
    addon_repositories: tuple[str, ...] = ()
    runtime_env: dict[str, str | int | float | bool] = Field(default_factory=dict)
    required_env_keys: tuple[str, ...] = ()
    contexts: dict[str, ContextDefinition]


@dataclass(frozen=True)
class ShipBranchSyncPlan:
    source_git_ref: str
    source_commit: str
    target_branch: str
    remote_branch_commit_before: str
    branch_update_required: bool


class PlatformSecretsInstanceDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    env: dict[str, str | int | float | bool] = Field(default_factory=dict)


class PlatformSecretsContextDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shared: dict[str, str | int | float | bool] = Field(default_factory=dict)
    instances: dict[str, PlatformSecretsInstanceDefinition] = Field(default_factory=dict)


class PlatformSecretsDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    shared: dict[str, str | int | float | bool] = Field(default_factory=dict)
    contexts: dict[str, PlatformSecretsContextDefinition] = Field(default_factory=dict)


@dataclass(frozen=True)
class EnvironmentLayer:
    name: str
    values: dict[str, str]


@dataclass(frozen=True)
class EnvironmentCollision:
    key: str
    previous_layer: str
    incoming_layer: str


@dataclass(frozen=True)
class LoadedEnvironment:
    env_file_path: Path
    merged_values: dict[str, str]
    source_by_key: dict[str, str]
    collisions: tuple[EnvironmentCollision, ...]


@dataclass(frozen=True)
class LoadedStack:
    stack_file_path: Path
    stack_definition: StackDefinition


@dataclass(frozen=True)
class RuntimeSelection:
    context_name: str
    instance_name: str
    context_definition: ContextDefinition
    instance_definition: InstanceDefinition
    database_name: str
    project_name: str
    state_path: Path
    data_mount: Path
    runtime_conf_host_path: Path
    data_volume_name: str
    log_volume_name: str
    db_volume_name: str
    web_host_port: int
    longpoll_host_port: int
    db_host_port: int
    runtime_odoo_conf_path: str
    effective_install_modules: tuple[str, ...]
    effective_addon_repositories: tuple[str, ...]
    effective_runtime_env: dict[str, str]
