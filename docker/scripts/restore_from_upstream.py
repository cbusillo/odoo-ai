#!/usr/bin/env python3
import argparse
import json
import time
import logging
import os
import re
import sys
import shlex
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from enum import Enum, IntEnum
from pathlib import Path
from typing import Annotated, Optional, Sequence

import psycopg2
from passlib.context import CryptContext
from psycopg2 import sql
from psycopg2.extensions import connection
from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)


class OdooRestorerError(Exception):
    pass


class OdooDatabaseUpdateError(OdooRestorerError):
    pass


class SqlCallType(Enum):
    UPDATE = "UPDATE"
    INSERT = "INSERT"
    DELETE = "DELETE"
    SELECT = "SELECT"


class ExitCode(IntEnum):
    SUCCESS = 0
    RESTORE_FAILED_BOOTSTRAP_SUCCESS = 10
    BOOTSTRAP_FAILED = 20
    INVALID_ARGS = 30


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore or bootstrap an Odoo database/filestore")
    parser.add_argument("--env-file", type=Path, default=None, help="Optional env file to load settings from")
    parser.add_argument(
        "--bootstrap-only",
        action="store_true",
        help="Force bootstrap mode (skip upstream restore)",
    )
    parser.add_argument(
        "--no-sanitize",
        action="store_true",
        help="Skip sanitization steps (mail/cron/base URL adjustments)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    env_file: Optional[Path] = args.env_file
    if env_file is None:
        candidate = Path(".env")
        if candidate.exists():
            env_file = candidate

    settings_kwargs: dict[str, object] = {}
    if env_file and env_file.exists():
        settings_kwargs["_env_file"] = env_file
    elif env_file is not None:
        _logger.warning("Env file %s not found; falling back to process environment", env_file)
        env_file = None

    try:
        local_settings = LocalServerSettings(**settings_kwargs)
    except ValidationError as exc:
        _logger.error("Invalid local configuration: %s", exc)
        return ExitCode.INVALID_ARGS

    bootstrap_only = args.bootstrap_only or local_settings.bootstrap_only
    no_sanitize = args.no_sanitize or local_settings.no_sanitize

    try:
        upstream_settings = UpstreamServerSettings(**settings_kwargs)
    except ValidationError as exc:
        upstream_settings = None
        _logger.info("Upstream settings incomplete: %s", exc)

    restorer = OdooUpstreamRestorer(local_settings, upstream_settings, env_file)

    try:
        if bootstrap_only:
            restorer.bootstrap_database(do_sanitize=not no_sanitize)
            return ExitCode.SUCCESS

        if upstream_settings is None:
            _logger.warning("Upstream settings unavailable; running bootstrap instead.")
            restorer.bootstrap_database(do_sanitize=not no_sanitize)
            return ExitCode.SUCCESS

        try:
            restorer.restore_from_upstream(do_sanitize=not no_sanitize)
            return ExitCode.SUCCESS
        except (OdooRestorerError, OdooDatabaseUpdateError) as restore_error:
            _logger.warning("Upstream restore failed (%s). Falling back to bootstrap.", restore_error)
            restorer.bootstrap_database(do_sanitize=not no_sanitize)
            return ExitCode.RESTORE_FAILED_BOOTSTRAP_SUCCESS
    except (OdooRestorerError, OdooDatabaseUpdateError) as bootstrap_error:
        _logger.error("Bootstrap failed: %s", bootstrap_error)
        return ExitCode.BOOTSTRAP_FAILED


def restore_from_upstream() -> int:  # Entry point for pyproject scripts
    return main()


@dataclass(frozen=True)
class ServiceUserConfig:
    login: str
    name: str
    api_key_name: str
    group_xmlids: tuple[str, ...]
    password_template: str
    api_key_template: str
    inherit_superuser_groups: bool = False
    inherit_superuser_exclude_xmlids: tuple[str, ...] = ()
    inherit_superuser_category_exclude_keywords: tuple[str, ...] = ()


class OdooConfig:
    GPT_USER_LOGIN = "gpt"
    GPT_API_KEY_NAME = "GPT Integration Key"
    GPT_USER_NAME = "GPT Service User"
    GPT_ADMIN_LOGIN = "gpt-admin"
    GPT_ADMIN_API_KEY_NAME = "GPT Admin Key"
    GPT_ADMIN_USER_NAME = "GPT Admin User"
    GROUP_INTERNAL = "base.group_user"
    GROUP_SYSTEM = "base.group_system"
    API_SCOPE = "rpc"
    GPT_SERVICE_USERS: tuple[ServiceUserConfig, ...] = (
        ServiceUserConfig(
            login=GPT_USER_LOGIN,
            name=GPT_USER_NAME,
            api_key_name=GPT_API_KEY_NAME,
            group_xmlids=(GROUP_INTERNAL,),
            password_template="{base}",
            api_key_template="{base}",
            inherit_superuser_groups=True,
            inherit_superuser_exclude_xmlids=(
                GROUP_SYSTEM,
                "base.group_erp_manager",
            ),
            inherit_superuser_category_exclude_keywords=(
                "administration",
                "settings",
                "technical",
            ),
        ),
        ServiceUserConfig(
            login=GPT_ADMIN_LOGIN,
            name=GPT_ADMIN_USER_NAME,
            api_key_name=GPT_ADMIN_API_KEY_NAME,
            group_xmlids=(GROUP_INTERNAL, GROUP_SYSTEM),
            password_template="{base}",
            api_key_template="admin-{base}",
            inherit_superuser_groups=True,
            inherit_superuser_exclude_xmlids=(),
        ),
    )


API_KEY_INDEX_LENGTH = 8
API_KEY_CRYPT_CONTEXT = CryptContext(
    ["pbkdf2_sha512"],
    pbkdf2_sha512__rounds=6000,
)
@dataclass
class KeyValuePair:
    key: str
    value: str | int | float | bool | None = None


@dataclass
class SqlCall:
    model: str
    data: KeyValuePair | None = None
    where: KeyValuePair | None = None


def _blank_to_none(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        return stripped
    return value


class LocalServerSettings(BaseSettings):
    # noinspection Pydantic
    model_config = SettingsConfigDict(case_sensitive=False)
    host: str = Field(..., alias="ODOO_DB_HOST")
    port: int = Field(5432, alias="ODOO_DB_PORT")
    db_user: str = Field(..., alias="ODOO_DB_USER")
    db_password: SecretStr = Field(..., alias="ODOO_DB_PASSWORD")
    db_name: str = Field(..., alias="ODOO_DB_NAME")
    db_conn: connection | None = None
    filestore_path: Path = Field(..., alias="ODOO_FILESTORE_PATH")
    filestore_owner: str | None = Field(None, alias="ODOO_FILESTORE_OWNER")
    restore_ssh_dir: Path | None = Field(None, alias="RESTORE_SSH_DIR")
    restore_ssh_key: Path | None = Field(None, alias="RESTORE_SSH_KEY")
    base_url: str | None = Field(None, alias="ODOO_BASE_URL")
    # Script/runtime toggles
    disable_cron: bool = Field(True, alias="SANITIZE_DISABLE_CRON")
    project_name: str = Field("odoo", alias="ODOO_PROJECT_NAME")
    addons_path: str | None = Field(None, alias="ODOO_ADDONS_PATH")
    update_modules: str | None = Field(None, alias="ODOO_UPDATE")
    local_addons_dirs: str | None = Field(None, alias="LOCAL_ADDONS_DIRS")
    auto_modules_raw: str | None = Field(None, alias="ODOO_AUTO_MODULES")
    odoo_key: SecretStr | None = Field(None, alias="ODOO_KEY")
    bootstrap_only: bool = Field(False, alias="BOOTSTRAP_ONLY")
    no_sanitize: bool = Field(False, alias="NO_SANITIZE")
    admin_password: SecretStr | None = Field(None, alias="ODOO_ADMIN_PASSWORD")

    @field_validator(
        "filestore_owner",
        "base_url",
        "addons_path",
        "update_modules",
        "local_addons_dirs",
        "auto_modules_raw",
        mode="before",
    )
    @classmethod
    def _optional_str(cls, value: object) -> object:
        return _blank_to_none(value)

    @field_validator("restore_ssh_dir", "restore_ssh_key", mode="before")
    @classmethod
    def _normalize_restore_paths(cls, value: object) -> object:
        value = _blank_to_none(value)
        if value is None:
            return None
        raw = str(value).strip()
        if raw.startswith(("'", '"')) and raw.endswith(("'", '"')) and len(raw) >= 2:
            raw = raw[1:-1]
        expanded = os.path.expanduser(os.path.expandvars(raw))
        return Path(expanded)

    @field_validator("filestore_path", mode="before")
    @classmethod
    def _normalize_filestore_path(cls, value: object) -> object:
        if value is None:
            return value
        raw = str(value).strip()
        if raw.startswith(("'", '"')) and raw.endswith(("'", '"')) and len(raw) >= 2:
            raw = raw[1:-1]
        expanded = os.path.expanduser(os.path.expandvars(raw))
        return Path(expanded)

    @field_validator("admin_password", mode="before")
    @classmethod
    def _optional_secret(cls, value: object) -> object:
        value = _blank_to_none(value)
        if value is None:
            return None
        return value


class UpstreamServerSettings(BaseSettings):
    # noinspection Pydantic
    model_config = SettingsConfigDict(case_sensitive=False)
    host: str = Field(..., alias="ODOO_UPSTREAM_HOST")
    user: str = Field(..., alias="ODOO_UPSTREAM_USER")
    db_name: str = Field(..., alias="ODOO_UPSTREAM_DB_NAME")
    db_user: str = Field(..., alias="ODOO_UPSTREAM_DB_USER")
    filestore_path: Path = Field(..., alias="ODOO_UPSTREAM_FILESTORE_PATH")


class ShopifySettings(BaseSettings):
    # noinspection Pydantic
    model_config = SettingsConfigDict(case_sensitive=False)
    shop_url_key: str = Field(..., alias="SHOPIFY_STORE_URL_KEY")
    api_token: SecretStr = Field(..., alias="SHOPIFY_API_TOKEN")
    api_version: str = Field(..., alias="SHOPIFY_API_VERSION")
    webhook_key: str = Field(..., alias="SHOPIFY_WEBHOOK_KEY")
    production_indicators: Annotated[list[str], NoDecode, Field(alias="PRODUCTION_INDICATORS")] = ["production", "live", "prod-"]

    @field_validator("production_indicators", mode="before")
    @classmethod
    def parse_production_indicators(cls, value: object) -> list[str]:
        if value is None:
            return ["production", "live", "prod-"]
        if isinstance(value, str):
            cleaned = [item.strip() for item in value.split(",") if item.strip()]
            return cleaned or ["production", "live", "prod-"]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return ["production", "live", "prod-"]

    def validate_safe_environment(self) -> None:
        shop_url_lower = self.shop_url_key.lower()
        for indicator in self.production_indicators:
            if indicator in shop_url_lower:
                raise OdooDatabaseUpdateError(
                    f"SAFETY CHECK FAILED: shop_url_key '{self.shop_url_key}' appears to be production. "
                    f"This script should only run on development/test environments. "
                    f"Found production indicator: '{indicator}'. Database will be dropped for safety."
                )
        _logger.info(f"SAFETY CHECK PASSED: {self.production_indicators} not in shop_url_key.")


class OdooUpstreamRestorer:
    def __init__(
        self,
        local: LocalServerSettings,
        upstream: Optional[UpstreamServerSettings],
        env_file: Path | None,
    ) -> None:
        self.local = local
        self.upstream = upstream
        self.env_file = env_file
        self.os_env = os.environ.copy()
        self.os_env["PGPASSWORD"] = self.local.db_password.get_secret_value()
        if self.local.restore_ssh_dir:
            self.os_env["RESTORE_SSH_DIR"] = str(self.local.restore_ssh_dir)
        self._ssh_identity: Optional[Path] = None
        if self.upstream:
            resolved_key = self._resolve_restore_ssh_key()
            self._ssh_identity = resolved_key
            if resolved_key is not None:
                self.os_env["RESTORE_SSH_KEY"] = str(resolved_key)
                _logger.info("Using SSH identity %s", resolved_key)
            elif self.local.restore_ssh_key:
                _logger.info(
                    "SSH identity %s not found inside container; relying on default ssh-agent/keys.",
                    self.local.restore_ssh_key,
                )
        self._auto_addon_dirs: list[Path] = []

    def run_command(self, command: str) -> None:
        _logger.info(f"Running command: {command}")
        try:
            subprocess.run(command, shell=True, env=self.os_env, check=True)
        except subprocess.CalledProcessError as command_error:
            raise OdooRestorerError(f"Command failed: {command}\nError: {command_error}") from command_error

    def _resolve_filestore_owner(self) -> str | None:
        owner = _blank_to_none(self.local.filestore_owner)
        if isinstance(owner, str) and owner.strip():
            return owner.strip()
        return None

    def _resolve_restore_ssh_key(self) -> Path | None:
        key = self.local.restore_ssh_key
        if not key:
            return None

        base_path = Path(str(key))
        candidates: list[Path] = [base_path]

        env_dir = self.local.restore_ssh_dir
        if env_dir:
            candidates.append(Path(env_dir) / base_path.name)

        candidates.extend([Path("/root/.ssh") / base_path.name, Path("/home/ubuntu/.ssh") / base_path.name])

        for candidate in candidates:
            expanded = Path(os.path.expanduser(os.path.expandvars(str(candidate))))
            if expanded.exists():
                return expanded

        fallback = Path(os.path.expanduser(os.path.expandvars(str(base_path))))
        if fallback.exists():
            return fallback

        return None

    def _require_upstream(self) -> UpstreamServerSettings:
        if not self.upstream:
            raise OdooRestorerError("Upstream settings are not configured; cannot perform restore.")
        return self.upstream

    def _build_ssh_command(self) -> list[str]:
        parts = ["ssh", "-o", "StrictHostKeyChecking=yes"]
        if self._ssh_identity:
            parts.extend(["-i", str(self._ssh_identity)])
        elif self.local.restore_ssh_key:
            _logger.warning(
                "RESTORE_SSH_KEY=%s not found inside container; continuing without explicit identity file.",
                self.local.restore_ssh_key,
            )
        return parts

    def overwrite_filestore(self, target_owner: str | None) -> subprocess.Popen:
        upstream = self._require_upstream()
        _logger.info("Overwriting filestore...")
        self.local.filestore_path.mkdir(parents=True, exist_ok=True)
        remote_path = shlex.quote(f"{upstream.user}@{upstream.host}:{upstream.filestore_path}")
        local_path = shlex.quote(str(self.local.filestore_path))
        chown_option = f"--chown={target_owner}" if target_owner else ""
        ssh_parts = self._build_ssh_command()
        ssh_command = shlex.join(ssh_parts)
        rsync_parts = ["rsync", "-az", "--delete"]
        if chown_option:
            rsync_parts.append(chown_option)
        rsync_parts.extend(["-e", shlex.quote(ssh_command), remote_path, local_path])
        rsync_command = " ".join(rsync_parts)
        return subprocess.Popen(rsync_command, shell=True, env=self.os_env)

    def normalize_filestore_permissions(self, target_owner: str | None) -> None:
        if not target_owner:
            return
        _logger.info("Normalizing filestore ownership to %s", target_owner)
        chown_command = f"chown -R {target_owner} {shlex.quote(str(self.local.filestore_path))}"
        self.run_command(chown_command)

    def overwrite_database(self) -> None:
        upstream = self._require_upstream()
        backup_path = "/tmp/upstream_db_backup.sql.gz"
        ssh_parts = self._build_ssh_command()
        ssh_command = shlex.join(ssh_parts)
        dump_cmd = (
            f"{ssh_command} {upstream.user}@{upstream.host} \"cd /tmp && sudo -u '{upstream.db_user}' "
            f"pg_dump -Fc '{upstream.db_name}'\" | gzip > {backup_path}"
        )
        self.run_command(dump_cmd)
        self.terminate_all_db_connections()
        self.run_command(f"dropdb --if-exists -h {self.local.host} -U {self.local.db_user} {self.local.db_name}")
        self.run_command(f"createdb -h {self.local.host} -U {self.local.db_user} {self.local.db_name}")
        restore_cmd = (
            f"gunzip < {backup_path} | pg_restore -d {self.local.db_name} -h {self.local.host} "
            f"-U {self.local.db_user} --no-owner --role={self.local.db_user}"
        )
        self.run_command(restore_cmd)
        self.run_command(f"rm {backup_path}")

    def connect_to_db(self) -> connection:
        if not self.local.db_conn:
            self.local.db_conn = self._connect_with_retry(self.local.db_name)
        return self.local.db_conn

    def _connect_with_retry(self, dbname: str, attempts: int = 10, delay: float = 1.0) -> connection:
        last_error: psycopg2.Error | None = None
        for attempt in range(1, attempts + 1):
            try:
                return psycopg2.connect(
                    dbname=dbname,
                    user=self.local.db_user,
                    password=self.local.db_password.get_secret_value(),
                    host=self.local.host,
                    port=self.local.port,
                )
            except psycopg2.Error as error:
                last_error = error
                if attempt < attempts:
                    time.sleep(delay)
                else:
                    raise
        raise last_error  # defensive: should never reach here

    def terminate_all_db_connections(self) -> None:
        with self._connect_with_retry("postgres") as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='{self.local.db_name}' "
                    f"AND pid <> pg_backend_pid();"
                )
                conn.commit()
        _logger.info("All database connections terminated.")

    def _reset_db_connection(self) -> None:
        if self.local.db_conn:
            try:
                self.local.db_conn.close()
            except Exception:
                pass
            self.local.db_conn = None

    def database_exists(self) -> bool:
        try:
            with self._connect_with_retry("postgres") as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (self.local.db_name,))
                    return cursor.fetchone() is not None
        except psycopg2.Error as error:
            raise OdooRestorerError(f"Failed to check database existence: {error}") from error

    def create_database(self) -> None:
        self.run_command(f"createdb -h {self.local.host} -U {self.local.db_user} {self.local.db_name}")

    def needs_base_install(self) -> bool:
        try:
            conn = self.connect_to_db()
        except psycopg2.Error:
            return True
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'ir_module_module' LIMIT 1"
            )
            table_present = cursor.fetchone() is not None
            if not table_present:
                return True
            cursor.execute("SELECT COUNT(*) FROM ir_module_module")
            count = cursor.fetchone()[0]
            return count == 0

    def install_base_schema(self) -> None:
        odoo_bin = "/odoo/odoo-bin"
        if not Path(odoo_bin).exists():
            odoo_bin = f"{Path('/opt/odoo/venv/bin/python')} /odoo/odoo-bin"

        cmd_parts = [
            odoo_bin,
            "--stop-after-init",
            "-d",
            self.local.db_name,
            "--no-http",
            "--without-demo=all",
            "-i",
            "base",
        ]
        generated_config_path = "/volumes/config/_generated.conf"
        if Path(generated_config_path).exists():
            cmd_parts += ["--config", generated_config_path]
        command = " ".join(cmd_parts)
        _logger.info("Initializing base schema...")
        self.run_command(command)
        self._reset_db_connection()

    def _clean_filestore(self) -> None:
        filestore = self.local.filestore_path
        if filestore.exists():
            _logger.info("Clearing filestore at %s", filestore)
            shutil.rmtree(filestore, ignore_errors=True)
        filestore.mkdir(parents=True, exist_ok=True)

    def call_odoo_sql(self, sql_call: SqlCall, call_type: SqlCallType) -> list[tuple] | None:
        self.connect_to_db()

        table = sql_call.model.replace(".", "_")
        if call_type == SqlCallType.UPDATE or call_type == SqlCallType.INSERT:
            if sql_call.data is None:
                raise ValueError("Data must be provided for UPDATE SQL call.")

            if sql_call.where:
                if sql_call.where.value is None:
                    raise ValueError("Value must be provided for WHERE clause.")

                query = sql.SQL(
                    "INSERT INTO {table} ({where_col}, {data_col}) "
                    "VALUES ({where_val}, {data_val}) "
                    "ON CONFLICT ({where_col}) DO UPDATE "
                    "SET {data_col} = EXCLUDED.{data_col}"
                ).format(
                    table=sql.Identifier(table),
                    where_col=sql.Identifier(sql_call.where.key),
                    data_col=sql.Identifier(sql_call.data.key),
                    where_val=sql.Literal(sql_call.where.value),
                    data_val=sql.Literal(sql_call.data.value),
                )
            else:
                query = sql.SQL("UPDATE {table} SET {key} = {value}").format(
                    table=sql.Identifier(table),
                    key=sql.Identifier(sql_call.data.key),
                    value=sql.Literal(sql_call.data.value),
                )
        elif call_type == SqlCallType.SELECT:
            if sql_call.data and sql_call.data.key:
                query = sql.SQL("SELECT {key} FROM {table}").format(
                    table=sql.Identifier(table),
                    key=sql.Identifier(sql_call.data.key),
                )
            else:
                query = sql.SQL("SELECT * FROM {table}").format(table=sql.Identifier(table))
        else:
            raise ValueError(f"Unsupported SQL call type: {call_type}")

        if call_type == SqlCallType.SELECT and sql_call.where:
            if sql_call.where.value is None:
                raise ValueError("Value must be provided for WHERE clause.")

            query += sql.SQL(" WHERE {key} = {value}").format(
                key=sql.Identifier(sql_call.where.key),
                value=sql.Literal(sql_call.where.value),
            )

        with self.local.db_conn.cursor() as cursor:
            cursor.execute(query)
            if call_type == SqlCallType.SELECT:
                return cursor.fetchall()
            else:
                return []

    def sanitize_database(self) -> None:
        disable_cron = self.local.disable_cron

        sql_calls: list[SqlCall] = [
            SqlCall("ir.mail_server", KeyValuePair("active", False)),
            SqlCall("ir.config_parameter", KeyValuePair("value", "False"), KeyValuePair("key", "mail.catchall.domain")),
            SqlCall("ir.config_parameter", KeyValuePair("value", "False"), KeyValuePair("key", "mail.catchall.alias")),
            SqlCall("ir.config_parameter", KeyValuePair("value", "False"), KeyValuePair("key", "mail.bounce.alias")),
        ]
        if disable_cron:
            sql_calls.append(SqlCall("ir.cron", KeyValuePair("active", False)))
        if self.local.base_url:
            sql_calls.append(
                SqlCall(
                    "ir.config_parameter",
                    KeyValuePair("value", self.local.base_url),
                    KeyValuePair("key", "web.base.url"),
                )
            )
            sql_calls.append(
                SqlCall(
                    "ir.config_parameter",
                    KeyValuePair("value", "True"),
                    KeyValuePair("key", "web.base.url.freeze"),
                )
            )

        _logger.info("Sanitizing database...")
        for sql_call in sql_calls:
            _logger.debug(f"Executing SQL call: {sql_call}")
            self.call_odoo_sql(sql_call, SqlCallType.UPDATE)

        # If we asked to disable crons, verify no active cron remains
        if disable_cron:
            active_crons = self.call_odoo_sql(SqlCall("ir.cron", where=KeyValuePair("active", True)), SqlCallType.SELECT)
            if active_crons:
                errors = "\n".join(f"- {cron[7]} (id: {cron[0]})" for cron in active_crons)
                raise OdooDatabaseUpdateError(f"Error: The following cron jobs are still active after sanitization:\n{errors}")

    def update_shopify_config(self) -> None:
        if self.env_file and self.env_file.exists():
            # noinspection PyArgumentList
            settings = ShopifySettings(_env_file=self.env_file)
        else:
            # noinspection PyArgumentList
            settings = ShopifySettings()

        shop_url_key = (settings.shop_url_key or "").strip()
        api_token = settings.api_token.get_secret_value().strip()
        webhook_key = (settings.webhook_key or "").strip()
        api_version = (settings.api_version or "").strip()

        # Safety check: prevent setting production values, allow replacing production with development
        settings.shop_url_key = shop_url_key
        settings.validate_safe_environment()
        production_indicators = settings.production_indicators

        # Log what we're doing for transparency
        current_shop_url_key = self.call_odoo_sql(
            SqlCall("ir.config_parameter", KeyValuePair("value"), KeyValuePair("key", "shopify.shop_url_key")),
            SqlCallType.SELECT,
        )

        if current_shop_url_key and current_shop_url_key[0]:
            current_value = current_shop_url_key[0][0]
            _logger.info(f"Replacing shop_url_key: '{current_value}' → '{shop_url_key}'")
        else:
            _logger.info(f"Setting shop_url_key to: '{shop_url_key}'")

        sql_calls: list[SqlCall] = [
            SqlCall(
                "ir.config_parameter",
                KeyValuePair("value", shop_url_key),
                KeyValuePair("key", "shopify.shop_url_key"),
            ),
            SqlCall(
                "ir.config_parameter",
                KeyValuePair("value", api_token),
                KeyValuePair("key", "shopify.api_token"),
            ),
            SqlCall(
                "ir.config_parameter",
                KeyValuePair("value", webhook_key),
                KeyValuePair("key", "shopify.webhook_key"),
            ),
            SqlCall(
                "ir.config_parameter",
                KeyValuePair("value", api_version),
                KeyValuePair("key", "shopify.api_version"),
            ),
            SqlCall(
                "ir.config_parameter",
                KeyValuePair("value", "True"),
                KeyValuePair("key", "shopify.test_store"),
            ),
        ]
        _logger.info("Updating Shopify configuration...")
        for sql_call in sql_calls:
            _logger.debug(f"Executing SQL call: {sql_call}")
            try:
                self.call_odoo_sql(sql_call, SqlCallType.UPDATE)
            except psycopg2.Error as error:
                raise OdooDatabaseUpdateError(f"Failed to update Shopify configuration: {error}") from error

        legacy_keys = ("shopify.shop_url", "shopify.store_url")
        for key in legacy_keys:
            result = self.call_odoo_sql(
                SqlCall("ir.config_parameter", KeyValuePair("value"), KeyValuePair("key", key)),
                SqlCallType.SELECT,
            )
            if result and result[0]:
                value = (result[0][0] or "").strip().lower()
                for indicator in production_indicators:
                    if indicator and indicator in value:
                        raise OdooDatabaseUpdateError(
                            f"Safety check failed: {key} still contains production indicator '{indicator}'."
                        )
                with self.local.db_conn.cursor() as cursor:
                    cursor.execute("DELETE FROM ir_config_parameter WHERE key = %s", (key,))
                _logger.info("Removed legacy Shopify config key %s", key)

        sanitized_keys = ["shopify.shop_url_key"]
        for key in sanitized_keys:
            result = self.call_odoo_sql(
                SqlCall("ir.config_parameter", KeyValuePair("value"), KeyValuePair("key", key)),
                SqlCallType.SELECT,
            )
            value = (result[0][0].strip() if result and result[0] else "").lower()
            for indicator in production_indicators:
                if indicator and indicator in value:
                    raise OdooDatabaseUpdateError(
                        f"Safety check failed: {key} still contains production indicator '{indicator}'."
                    )

    def clear_shopify_ids(self) -> None:
        with self.local.db_conn.cursor() as cursor:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'product_product' AND column_name LIKE 'shopify%'"
            )
            existing_fields = [row[0] for row in cursor.fetchall()]

        fields_to_clear = [
            "shopify_created_at",
            "shopify_last_exported",
            "shopify_last_exported_at",
            "shopify_condition_id",
            "shopify_variant_id",
            "shopify_product_id",
            "shopify_ebay_category_id",
        ]

        for field in fields_to_clear:
            if field in existing_fields:
                sql_call = SqlCall("product.product", KeyValuePair(field))
                try:
                    self.call_odoo_sql(sql_call, SqlCallType.UPDATE)
                except psycopg2.Error as error:
                    raise OdooDatabaseUpdateError(f"Failed to clear Shopify ID {field}: {error}") from error
            else:
                _logger.info(f"Skipping field {field} - does not exist in database")

    def drop_database(self) -> None:
        _logger.info("Rolling back database update: dropping database")
        self.terminate_all_db_connections()
        drop_cmd = f"dropdb --if-exists -h {self.local.host} -U {self.local.db_user} {self.local.db_name}"
        self.run_command(drop_cmd)

    # --- Sanity checks ---
    def assert_core_schema_healthy(self) -> None:
        self.connect_to_db()
        with self.local.db_conn.cursor() as cursor:
            # ir_module_module must exist and have rows
            try:
                cursor.execute("SELECT COUNT(*) FROM ir_module_module")
                mod_count = cursor.fetchone()[0]
            except psycopg2.Error as e:
                raise OdooDatabaseUpdateError(f"Schema check failed: ir_module_module missing ({e})") from e
            if mod_count == 0:
                raise OdooDatabaseUpdateError("Schema check failed: ir_module_module is empty")

            # Languages must exist
            try:
                cursor.execute("SELECT COUNT(*) FROM res_lang")
                lang_count = cursor.fetchone()[0]
            except psycopg2.Error as e:
                raise OdooDatabaseUpdateError(f"Schema check failed: res_lang missing ({e})") from e
            if lang_count == 0:
                raise OdooDatabaseUpdateError("Schema check failed: no languages in res_lang")

            # base.public_user should resolve
            cursor.execute("SELECT 1 FROM ir_model_data WHERE module='base' AND name='public_user' LIMIT 1")
            if cursor.fetchone() is None:
                raise OdooDatabaseUpdateError("Schema check failed: base.public_user xmlid not found")

    def _odoo_shell_command(self) -> list[str]:
        base_bin = Path("/odoo/odoo-bin")
        if base_bin.exists():
            command = [str(base_bin), "shell"]
        else:
            alt_python = Path("/opt/odoo/venv/bin/python")
            if not alt_python.exists():
                raise OdooRestorerError("Unable to locate odoo-bin executable for shell operations.")
            command = [str(alt_python), "/odoo/odoo-bin", "shell"]

        command += ["-d", self.local.db_name, "--no-http"]
        generated_config_path = Path("/volumes/config/_generated.conf")
        if generated_config_path.exists():
            command += ["--config", str(generated_config_path)]
        return command

    def _run_odoo_shell(self, script: str) -> None:
        command = self._odoo_shell_command()
        _logger.info("Executing odoo shell for GPT user provisioning: %s", " ".join(command))
        try:
            subprocess.run(
                command,
                input=script.encode("utf-8"),
                env=self.os_env,
                check=True,
            )
        except subprocess.CalledProcessError as error:
            raise OdooRestorerError("Failed to execute Odoo shell for GPT provisioning.") from error

    def ensure_gpt_users(self) -> None:
        secret = self.local.odoo_key
        if secret is None:
            _logger.info("ODOO_KEY not provided; skipping GPT service user provisioning.")
            return

        raw_key = secret.get_secret_value().strip()
        if not raw_key:
            _logger.info("ODOO_KEY empty; skipping GPT service user provisioning.")
            return
        if len(raw_key) < API_KEY_INDEX_LENGTH:
            raise OdooDatabaseUpdateError(f"ODOO_KEY must be at least {API_KEY_INDEX_LENGTH} characters to derive an API key index.")

        payload = {
            "db": self.local.db_name,
            "api_scope": OdooConfig.API_SCOPE,
            "users": [],
        }

        for config in OdooConfig.GPT_SERVICE_USERS:
            password_plain = config.password_template.format(base=raw_key)
            api_key_plain = config.api_key_template.format(base=raw_key)

            if len(api_key_plain) < API_KEY_INDEX_LENGTH:
                raise OdooDatabaseUpdateError(
                    f"Derived API key for {config.login} must be at least {API_KEY_INDEX_LENGTH} characters to derive an index."
                )

            payload["users"].append(
                {
                    "login": config.login,
                    "name": config.name,
                    "password": password_plain,
                    "groups": list(config.group_xmlids),
                    "inherit_superuser_groups": config.inherit_superuser_groups,
                    "inherit_superuser_exclude_xmlids": list(config.inherit_superuser_exclude_xmlids),
                    "inherit_superuser_category_exclude_keywords": list(
                        config.inherit_superuser_category_exclude_keywords
                    ),
                    "api_key_name": config.api_key_name,
                    "api_key_index": api_key_plain[:API_KEY_INDEX_LENGTH],
                    "api_key_hash": API_KEY_CRYPT_CONTEXT.hash(api_key_plain),
                }
            )

        script = textwrap.dedent("""
import json
from odoo import api, SUPERUSER_ID, Command
from odoo.modules.registry import Registry

payload = json.loads('__PAYLOAD__')

registry = Registry(payload["db"])
with registry.cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})
    company = env['res.company'].search([], order='id', limit=1)
    if not company:
        raise ValueError("Unable to locate a company record for GPT user provisioning.")

    partner_defaults = {
        "autopost_bills": "ask",
        "type": "contact",
        "active": True,
    }

    for user_data in payload["users"]:
        partner_vals = dict(partner_defaults, name=user_data["name"], company_id=company.id)
        partner = env["res.partner"].sudo().search([
            ("name", "=", user_data["name"]),
            ("company_id", "=", company.id),
        ], limit=1)
        if partner:
            partner.write(partner_vals)
        else:
            partner = env["res.partner"].sudo().create(partner_vals)

        group_ids: list[int]
        group_ids: list[int] = []

        def add_group(group_id: int) -> None:
            if group_id not in group_ids:
                group_ids.append(group_id)

        if user_data.get("inherit_superuser_groups"):
            superuser = env['res.users'].browse(SUPERUSER_ID)
            exclude_xmlids = set(user_data.get("inherit_superuser_exclude_xmlids", []))
            category_keywords = {
                keyword.lower()
                for keyword in user_data.get("inherit_superuser_category_exclude_keywords", [])
                if keyword
            }
            for group in superuser.groups_id:
                xmlid = group.get_external_id().get(group.id)
                if xmlid and xmlid in exclude_xmlids:
                    continue
                if category_keywords and group.category_id:
                    category_name = (group.category_id.display_name or group.category_id.name or "").lower()
                    if any(keyword in category_name for keyword in category_keywords):
                        continue
                add_group(group.id)

        for xmlid in user_data.get("groups", []):
            try:
                add_group(env.ref(xmlid).id)
            except ValueError as exc:
                raise ValueError(f"Unable to locate group xmlid '{xmlid}' for GPT user provisioning.") from exc

        ctx = dict(env.context, no_reset_password=True)
        user_model = env["res.users"].with_context(ctx).sudo()
        user = user_model.search([("login", "=", user_data["login"] )], limit=1)

        common_vals = {
            "name": user_data["name"],
            "partner_id": partner.id,
            "company_id": company.id,
            "company_ids": [Command.set([company.id])],
            "notification_type": "email",
            "share": False,
            "active": True,
            "groups_id": [Command.set(group_ids)],
        }

        if user:
            user.write(common_vals)
            action = "updated"
        else:
            create_vals = dict(common_vals, login=user_data["login"])
            user = user_model.create(create_vals)
            action = "created"

        user.with_context(no_reset_password=True).sudo().write({'password': user_data['password']})

        env.cr.execute(
            "SELECT id FROM res_users_apikeys WHERE user_id = %s AND name = %s",
            (user.id, user_data["api_key_name"]),
        )
        row = env.cr.fetchone()
        if row:
            env.cr.execute(
                "UPDATE res_users_apikeys SET key=%s, scope=%s, index=%s, expiration_date=NULL WHERE id=%s",
                (user_data["api_key_hash"], payload["api_scope"], user_data["api_key_index"], row[0]),
            )
        else:
            env.cr.execute(
                "INSERT INTO res_users_apikeys (name, user_id, scope, expiration_date, key, index) VALUES (%s, %s, %s, NULL, %s, %s)",
                (user_data["api_key_name"], user.id, payload["api_scope"], user_data["api_key_hash"], user_data["api_key_index"]),
            )

        print(f"GPT provisioning: {action} user {user.login} (id={user.id})")

    cr.commit()
""")
        script = script.replace("__PAYLOAD__", json.dumps(payload))
        self._run_odoo_shell(script)
        self._reset_db_connection()

    def ensure_admin_user(self, *, do_sanitize: bool) -> None:
        """Ensure the admin user has safe credentials."""
        self.connect_to_db()
        with self.local.db_conn.cursor() as cursor:
            cursor.execute("SELECT id, partner_id FROM res_users WHERE login=%s LIMIT 1", ("admin",))
            row = cursor.fetchone()
        if not row:
            _logger.warning("Admin user not found; skipping admin hardening.")
            return
        _, partner_id = row

        set_password = False
        password_plain: Optional[str] = None
        if self.local.admin_password:
            candidate = self.local.admin_password.get_secret_value().strip()
            if candidate:
                set_password = True
                password_plain = candidate

        set_email = False
        target_email = "admin@localhost"
        if partner_id:
            with self.local.db_conn.cursor() as cursor:
                cursor.execute("SELECT email FROM res_partner WHERE id=%s", (partner_id,))
                email_row = cursor.fetchone()
            current_email = (email_row[0] or "").strip() if email_row else ""
            if current_email:
                email_lower = current_email.lower()
                allowed_suffixes = (".local", ".test", ".example", ".invalid")
                domain = email_lower.split("@", 1)[-1]
                if "@" not in email_lower or (
                    not domain.endswith(allowed_suffixes)
                    and domain != "localhost"
                ):
                    set_email = True
            else:
                set_email = True
        else:
            _logger.warning("Admin user has no linked partner; skipping email normalization.")

        if not set_password and not set_email:
            _logger.info("Admin credentials already satisfy safety requirements; no changes needed.")
            return

        payload = {
            "db": self.local.db_name,
            "set_password": set_password,
            "password": password_plain or "",
            "set_email": bool(partner_id and set_email),
            "email": target_email,
        }

        script = textwrap.dedent("""
import json
from odoo import api, SUPERUSER_ID
from odoo.modules.registry import Registry

payload = json.loads('__PAYLOAD__')
registry = Registry(payload['db'])
with registry.cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})
    admin = env['res.users'].sudo().search([('login', '=', 'admin')], limit=1)
    if admin:
        if payload['set_password']:
            admin.with_context(no_reset_password=True).sudo().password = payload['password']
        if payload['set_email'] and admin.partner_id:
            admin.partner_id.sudo().write({'email': payload['email']})
    cr.commit()
""").replace("__PAYLOAD__", json.dumps(payload))

        _logger.info("Hardening admin credentials (password=%s, email=%s)", set_password, set_email)
        self._run_odoo_shell(script)
        self._reset_db_connection()

    def bootstrap_database(self, *, do_sanitize: bool) -> None:
        _logger.info("Starting bootstrap for database '%s'", self.local.db_name)
        target_owner = self._resolve_filestore_owner()
        if target_owner:
            _logger.info("Resolved filestore owner: %s", target_owner)
        try:
            if self.database_exists():
                _logger.info("Existing database detected; dropping before bootstrap.")
                self._reset_db_connection()
                self.drop_database()
        except OdooRestorerError as error:
            _logger.warning("Unable to verify database existence (%s); forcing drop.", error)
            self._reset_db_connection()
            self.drop_database()

        self._clean_filestore()
        self.normalize_filestore_permissions(target_owner)
        self.create_database()
        self._reset_db_connection()
        self.connect_to_db()

        if self.needs_base_install():
            self.install_base_schema()
            self.connect_to_db()
        else:
            _logger.info("Base schema already present; skipping base install step.")

        self.update_addons()
        self._reset_db_connection()
        self.connect_to_db()

        if do_sanitize:
            self.sanitize_database()
            self.local.db_conn.commit()
        else:
            _logger.info("Skipping sanitization per --no-sanitize flag.")

        self.ensure_admin_user(do_sanitize=do_sanitize)
        self.connect_to_db()
        self.assert_core_schema_healthy()
        self.ensure_gpt_users()
        _logger.info("Bootstrap completed successfully.")

    def compute_update_module_list(self) -> list[str]:
        """Return sorted addon names discovered from local addon directories."""

        def _extend_from_raw(raw: str | None) -> None:
            if not raw:
                return
            separator = "," if "," in raw else ":"
            for token in raw.split(separator):
                stripped = token.strip()
                if stripped:
                    candidate_dirs.append(stripped)

        candidate_dirs: list[str] = []
        _extend_from_raw(self.local.local_addons_dirs)
        _extend_from_raw(self.local.addons_path)

        if not candidate_dirs:
            generated_conf = Path("/volumes/config/_generated.conf")
            if generated_conf.exists():
                try:
                    conf_text = generated_conf.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    conf_text = ""
                match = re.search(r"^\s*addons_path\s*=\s*(.+)$", conf_text, re.MULTILINE)
                if match:
                    _extend_from_raw(match.group(1).strip())

        if not candidate_dirs:
            candidate_dirs = [
                "/volumes/addons",
                "/opt/project/addons",
            ]

        discovered: set[str] = set()
        resolved_dirs: list[Path] = []
        for raw_dir in candidate_dirs:
            try:
                base = Path(raw_dir).expanduser()
                base = base.resolve(strict=False)
            except OSError:
                base = Path(raw_dir)

            normalized = str(base)
            if "/odoo/addons" in normalized or "/odoo/odoo/addons" in normalized:
                continue
            if "/enterprise" in normalized:
                continue
            if not base.is_dir():
                continue
            if base not in resolved_dirs:
                resolved_dirs.append(base)

            for child in base.iterdir():
                if not child.is_dir():
                    continue
                if (child / "__manifest__.py").exists() or (child / "__openerp__.py").exists():
                    discovered.add(child.name)

        self._auto_addon_dirs = resolved_dirs
        return sorted(discovered)

    def _default_modules_for_project(self) -> list[str]:
        raw = (self.local.auto_modules_raw or "").strip()
        if not raw:
            return []
        separator = "," if "," in raw else ":"
        modules = [item.strip() for item in raw.split(separator) if item.strip()]
        return modules

    def update_addons(self) -> None:
        mods_env = (self.local.update_modules or "").strip()
        desired: list[str]
        if not mods_env or mods_env.upper() == "AUTO":
            project_defaults = self._default_modules_for_project()
            if project_defaults:
                desired = project_defaults
                _logger.info(
                    "ODOO_UPDATE=%s; using project defaults: %s",
                    mods_env.upper() if mods_env else "AUTO",
                    ", ".join(desired),
                )
            else:
                desired = self.compute_update_module_list()
                if not desired:
                    _logger.info("ODOO_UPDATE unset/AUTO and no modules detected; skipping addon update.")
                    return
                mode_label = mods_env.upper() if mods_env else "AUTO"
                _logger.info(
                    "ODOO_UPDATE=%s; auto-detected modules: %s",
                    mode_label,
                    ", ".join(desired),
                )
        else:
            desired = [m.strip() for m in mods_env.split(",") if m.strip()]
            if not desired:
                _logger.info("ODOO_UPDATE is empty after parsing; skipping.")
                return

        addons_env = (self.local.addons_path or "").strip()
        addons_paths: list[Path] = []
        if addons_env:
            sep = "," if "," in addons_env else ":"
            for raw in [p.strip() for p in addons_env.split(sep) if p.strip()]:
                addons_paths.append(Path(raw))
        if not addons_paths:
            addons_paths = [
                Path("/volumes/addons"),
                Path("/opt/project/addons"),
                Path("/odoo/addons"),
                Path("/volumes/enterprise"),
            ]
        if getattr(self, "_auto_addon_dirs", None):
            for auto_dir in self._auto_addon_dirs:
                if auto_dir not in addons_paths:
                    addons_paths.append(auto_dir)
        _logger.info(
            "Using addons search paths: %s",
            ", ".join(str(p) for p in addons_paths),
        )
        found: set[str] = set()
        missing_fs: list[str] = []
        for name in desired:
            present = False
            for base in addons_paths:
                if (base / name).is_dir():
                    found.add(name)
                    present = True
                    break
            if not present:
                missing_fs.append(name)

        if missing_fs:
            _logger.warning(f"Modules listed in ODOO_UPDATE not found on disk and will be skipped: {', '.join(missing_fs)}")

        if not found:
            _logger.info("No valid modules from ODOO_UPDATE found on disk; skipping.")
            return

        self.connect_to_db()
        rows: dict[str, str] = {}
        with self.local.db_conn.cursor() as cur:
            cur.execute(
                "SELECT name, state FROM ir_module_module WHERE name = ANY(%s)",
                (list(found),),
            )
            for name, state in cur.fetchall():
                rows[name] = state

        to_install = [name for name in found if name not in rows or rows.get(name) in ("uninstalled", "to remove")]
        to_update = list(found)

        odoo_bin = "/odoo/odoo-bin"
        if not Path(odoo_bin).exists():
            odoo_bin = f"{Path('/opt/odoo/venv/bin/python')} /odoo/odoo-bin"

        cmd_parts = [
            odoo_bin,
            "--stop-after-init",
            "-d",
            self.local.db_name,
            "--no-http",
        ]
        if to_install:
            cmd_parts += ["-i", ",".join(to_install)]
        if to_update:
            cmd_parts += ["-u", ",".join(to_update)]

        generated_config_path = "/volumes/config/_generated.conf"
        if Path(generated_config_path).exists():
            cmd_parts += ["--config", generated_config_path]

        command = " ".join(cmd_parts)
        _logger.info(f"Installing: {to_install if to_install else 'none'}; Updating: {to_update if to_update else 'none'}")
        try:
            self.run_command(command)
        except subprocess.CalledProcessError as update_error:
            raise OdooRestorerError(f"Failed to install/update addons: {update_error}") from update_error
        finally:
            self._reset_db_connection()

    def restore_from_upstream(self, do_sanitize: bool = True) -> None:
        upstream = self._require_upstream()
        target_owner = self._resolve_filestore_owner()
        _logger.info("Resolved filestore owner: %s", target_owner or "<default>")
        filestore_proc = self.overwrite_filestore(target_owner)
        self.overwrite_database()
        filestore_proc.wait()
        if filestore_proc.returncode != 0:
            raise OdooRestorerError("Filestore rsync failed.")
        _logger.info("Filestore overwrite completed.")
        self.normalize_filestore_permissions(target_owner)
        if do_sanitize:
            try:
                self.sanitize_database()
                self.local.db_conn.commit()
            except OdooDatabaseUpdateError:
                self.drop_database()
                raise

        self.update_addons()
        self.connect_to_db()

        if do_sanitize:
            try:
                self.update_shopify_config()
                self.clear_shopify_ids()
                self.local.db_conn.commit()
            except OdooDatabaseUpdateError:
                self.drop_database()
                raise

        self.assert_core_schema_healthy()
        self.ensure_gpt_users()

        _logger.info("Upstream overwrite completed successfully.")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(int(main()))
