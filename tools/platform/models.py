from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
    target_type: Literal["compose", "application"] = "compose"
    target_id: str = ""
    target_name: str = ""
    git_branch: str = ""
    source_git_ref: str = "origin/main"
    auto_deploy: bool | None = None
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
