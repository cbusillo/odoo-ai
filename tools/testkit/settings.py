from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Summary schema version for all JSON outputs produced by test runner
SUMMARY_SCHEMA_VERSION = "1.0"


class TestSettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        extra="ignore",
    )

    # Core project/env
    project_name: str = Field("odoo", alias="ODOO_PROJECT_NAME")
    db_user: str | None = Field(None, alias="ODOO_DB_USER")
    filestore_path: str | None = Field(None, alias="ODOO_FILESTORE_PATH")
    db_name: str = Field("odoo", alias="ODOO_DB_NAME")

    # Runner toggles and parameters
    test_unit_split: bool = Field(True, alias="TEST_UNIT_SPLIT")
    test_keep_going: bool = Field(True, alias="TEST_KEEP_GOING")
    test_log_keep: int = Field(12, alias="TEST_LOG_KEEP")
    test_scoped_cleanup: bool = Field(True, alias="TEST_SCOPED_CLEANUP")

    tour_warmup: int = Field(1, alias="TOUR_WARMUP")
    js_workers: int = Field(0, alias="JS_WORKERS")
    tour_workers: int = Field(0, alias="TOUR_WORKERS")
    test_detached: bool = Field(False, alias="TEST_DETACHED")

    test_tags_override: str | None = Field(None, alias="TEST_TAGS")
    test_log_session: str | None = Field(None, alias="TEST_LOG_SESSION")

    # Sharding and parallelism
    unit_shards: int = Field(0, alias="UNIT_SHARDS")  # 0 -> auto
    js_shards: int = Field(0, alias="JS_SHARDS")
    integration_shards: int = Field(0, alias="INTEGRATION_SHARDS")
    tour_shards: int = Field(0, alias="TOUR_SHARDS")
    max_procs: int = Field(0, alias="TEST_MAX_PROCS")  # 0 -> auto
    # Within-module sharding (split heavy modules by class/file)
    unit_within_shards: int = Field(0, alias="UNIT_WITHIN_SHARDS")
    integration_within_shards: int = Field(0, alias="INTEGRATION_WITHIN_SHARDS")
    tour_within_shards: int = Field(0, alias="TOUR_WITHIN_SHARDS")
    # Phase overlap (run unit+js in parallel; integration+tour in parallel)
    phases_overlap: bool = Field(False, alias="PHASES_OVERLAP")

    # Filestore snapshot control for prod-clone phases
    skip_filestore_integration: bool = Field(False, alias="SKIP_FILESTORE_INTEGRATION")
    skip_filestore_tour: bool = Field(False, alias="SKIP_FILESTORE_TOUR")

    # Connection guardrails (soft caps)
    db_max_connections: int = Field(100, alias="DB_MAX_CONNECTIONS")
    conn_per_shard: int = Field(4, alias="DB_CONN_PER_SHARD")
    conn_reserve: int = Field(10, alias="DB_CONN_RESERVE")

    # Events
    events_stdout: bool = Field(False, alias="EVENTS_STDOUT")

    # Template reuse (between sessions)
    reuse_template: bool = Field(False, alias="REUSE_TEMPLATE")
    template_ttl_sec: int = Field(0, alias="TEMPLATE_TTL_SEC")

    # Coverage toggles (pass-through / future use)
    coverage_py: bool = Field(False, alias="COVERAGE_PY")
    coverage_modules: str | None = Field(None, alias="COVERAGE_MODULES")
