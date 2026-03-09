#!/usr/bin/env python3
"""Initialize Odoo state if needed before launching the long-running web server.

This wrapper keeps first-start behavior deterministic:
- Wait for PostgreSQL connectivity
- Initialize the configured database when required
- Start the standard Odoo HTTP server process

The command is safe to run on every container start because initialization only
executes when the target database is missing required installed modules.
"""

from __future__ import annotations

import argparse
import configparser
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass

import psycopg2

RUNTIME_OPTION_MAP: tuple[tuple[str, str], ...] = (
    ("ODOO_DB_MAXCONN", "db_maxconn"),
    ("ODOO_MAX_CRON_THREADS", "max_cron_threads"),
    ("ODOO_WORKERS", "workers"),
    ("ODOO_LIMIT_TIME_CPU", "limit_time_cpu"),
    ("ODOO_LIMIT_TIME_REAL", "limit_time_real"),
    ("ODOO_LIMIT_TIME_REAL_CRON", "limit_time_real_cron"),
    ("ODOO_LIMIT_TIME_WORKER_CRON", "limit_time_worker_cron"),
    ("ODOO_LIMIT_MEMORY_SOFT", "limit_memory_soft"),
    ("ODOO_LIMIT_MEMORY_HARD", "limit_memory_hard"),
)


@dataclass(frozen=True)
class StartupSettings:
    config_path: str
    base_config_path: str
    database_name: str
    database_host: str
    database_port: int
    database_user: str
    database_password: str
    master_password: str
    admin_login: str
    admin_password: str
    addons_path: str
    data_dir: str
    list_db: str
    install_modules: tuple[str, ...]
    data_workflow_lock_file: str
    data_workflow_lock_timeout_seconds: int
    ready_timeout_seconds: int
    poll_interval_seconds: float


def _split_modules(raw_modules: str) -> tuple[str, ...]:
    parsed_modules: list[str] = []
    for module_name in (raw_modules or "").split(","):
        normalized_module_name = module_name.strip()
        if not normalized_module_name:
            continue
        if normalized_module_name in parsed_modules:
            continue
        parsed_modules.append(normalized_module_name)
    return tuple(parsed_modules)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap Odoo database and launch web server")
    parser.add_argument("-c", "--config", dest="config_path", required=True)
    return parser.parse_args()


def _load_settings(argument_namespace: argparse.Namespace) -> StartupSettings:
    database_name = os.environ.get("ODOO_DB_NAME", "").strip()
    if not database_name:
        raise RuntimeError("ODOO_DB_NAME must be set for startup.")

    database_port_raw = os.environ.get("ODOO_DB_PORT", "5432").strip() or "5432"
    database_port = int(database_port_raw)
    install_modules = _split_modules(os.environ.get("ODOO_INSTALL_MODULES", ""))
    master_password = os.environ.get("ODOO_MASTER_PASSWORD", "").strip()
    if not master_password:
        raise RuntimeError("ODOO_MASTER_PASSWORD must be set for startup.")

    return StartupSettings(
        config_path=argument_namespace.config_path,
        base_config_path=os.environ.get("ODOO_CONFIG", "/volumes/config/_generated.conf").strip()
        or "/volumes/config/_generated.conf",
        database_name=database_name,
        database_host=os.environ.get("ODOO_DB_HOST", "database").strip() or "database",
        database_port=database_port,
        database_user=os.environ.get("ODOO_DB_USER", "odoo").strip() or "odoo",
        database_password=os.environ.get("ODOO_DB_PASSWORD", ""),
        master_password=master_password,
        admin_login=os.environ.get("ODOO_ADMIN_LOGIN", "").strip() or "admin",
        admin_password=os.environ.get("ODOO_ADMIN_PASSWORD", "").strip(),
        addons_path=os.environ.get("ODOO_ADDONS_PATH", "").strip(),
        data_dir=os.environ.get("ODOO_DATA_DIR", "/volumes/data").strip() or "/volumes/data",
        list_db=os.environ.get("ODOO_LIST_DB", "False").strip() or "False",
        install_modules=install_modules,
        data_workflow_lock_file=os.environ.get(
            "ODOO_DATA_WORKFLOW_LOCK_FILE",
            "/volumes/data/.data_workflow_in_progress",
        ).strip()
        or "/volumes/data/.data_workflow_in_progress",
        data_workflow_lock_timeout_seconds=int(
            os.environ.get("ODOO_DATA_WORKFLOW_LOCK_TIMEOUT_SECONDS", "7200").strip()
            or "7200"
        ),
        ready_timeout_seconds=180,
        poll_interval_seconds=2.0,
    )


def _write_runtime_config(settings: StartupSettings) -> None:
    config_parser = configparser.ConfigParser(interpolation=None)
    if settings.base_config_path and os.path.exists(settings.base_config_path):
        config_parser.read(settings.base_config_path, encoding="utf-8")
    if not config_parser.has_section("options"):
        config_parser.add_section("options")

    options = config_parser["options"]
    options["admin_passwd"] = settings.master_password
    options["db_name"] = settings.database_name
    options["db_user"] = settings.database_user
    options["db_password"] = settings.database_password
    options["db_host"] = settings.database_host
    options["db_port"] = str(settings.database_port)
    options["list_db"] = settings.list_db
    options["data_dir"] = settings.data_dir
    if settings.addons_path:
        options["addons_path"] = settings.addons_path

    # Keep runtime tuning deterministic by overlaying supported env-driven
    # options onto the generated base config on every container start.
    for env_name, option_name in RUNTIME_OPTION_MAP:
        option_value = os.environ.get(env_name, "").strip()
        if option_value:
            options[option_name] = option_value

    dev_mode_value = os.environ.get("ODOO_DEV_MODE", "").strip()
    if dev_mode_value:
        options["dev_mode"] = dev_mode_value
    elif "dev_mode" in options:
        options.pop("dev_mode", None)

    config_path = settings.config_path
    config_directory = os.path.dirname(config_path)
    if config_directory:
        os.makedirs(config_directory, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as config_file:
        config_parser.write(config_file)


def _wait_for_database(settings: StartupSettings) -> None:
    deadline = time.monotonic() + settings.ready_timeout_seconds
    while time.monotonic() < deadline:
        try:
            with psycopg2.connect(
                host=settings.database_host,
                port=settings.database_port,
                user=settings.database_user,
                password=settings.database_password,
                dbname="postgres",
            ):
                return
        except psycopg2.OperationalError:
            time.sleep(settings.poll_interval_seconds)
    raise RuntimeError(
        "Database did not become reachable within "
        f"{settings.ready_timeout_seconds} seconds ({settings.database_host}:{settings.database_port})."
    )


def _database_exists(settings: StartupSettings) -> bool:
    with psycopg2.connect(
        host=settings.database_host,
        port=settings.database_port,
        user=settings.database_user,
        password=settings.database_password,
        dbname="postgres",
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.database_name,))
            return cursor.fetchone() is not None


def _installed_module_names(settings: StartupSettings) -> set[str]:
    with psycopg2.connect(
        host=settings.database_host,
        port=settings.database_port,
        user=settings.database_user,
        password=settings.database_password,
        dbname=settings.database_name,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM ir_module_module WHERE state = 'installed'")
            return {str(row[0]) for row in cursor.fetchall()}


def _missing_required_modules(settings: StartupSettings) -> tuple[str, ...]:
    if not _database_exists(settings):
        return settings.install_modules

    try:
        installed_modules = _installed_module_names(settings)
    except psycopg2.errors.UndefinedTable:
        return settings.install_modules

    missing_modules: list[str] = []
    for module_name in settings.install_modules:
        if module_name not in installed_modules:
            missing_modules.append(module_name)
    return tuple(missing_modules)


def _build_odoo_command(
    settings: StartupSettings,
    *,
    initialize_modules: tuple[str, ...] | None = None,
    stop_after_init: bool,
) -> list[str]:
    command = [
        "/odoo/odoo-bin",
        "-c",
        settings.config_path,
        "-d",
        settings.database_name,
        f"--db_host={settings.database_host}",
        f"--db_port={settings.database_port}",
        f"--db_user={settings.database_user}",
        f"--db_password={settings.database_password}",
    ]

    if initialize_modules is not None:
        normalized_modules = ["base", *initialize_modules]
        unique_modules: list[str] = []
        for module_name in normalized_modules:
            if module_name in unique_modules:
                continue
            unique_modules.append(module_name)
        command.extend(["-i", ",".join(unique_modules)])

    if stop_after_init:
        command.append("--stop-after-init")
    return command


def _build_odoo_shell_command(settings: StartupSettings) -> list[str]:
    return [
        "/odoo/odoo-bin",
        "shell",
        "-c",
        settings.config_path,
        "-d",
        settings.database_name,
        f"--db_host={settings.database_host}",
        f"--db_port={settings.database_port}",
        f"--db_user={settings.database_user}",
        f"--db_password={settings.database_password}",
        "--no-http",
    ]


def _run_odoo_shell(settings: StartupSettings, script_text: str, *, label: str) -> None:
    print(f"[platform-startup] running {label}", flush=True)
    subprocess.run(_build_odoo_shell_command(settings), input=script_text.encode(), check=True)


def _apply_admin_password_if_configured(settings: StartupSettings) -> None:
    if not settings.admin_password:
        return

    payload = {
        "login": settings.admin_login,
        "password": settings.admin_password,
    }
    script = """
import json

payload = json.loads('__PAYLOAD__')
admin_user = env['res.users'].sudo().with_context(active_test=False).search(
    [('login', '=', payload['login'])],
    limit=1,
)
if not admin_user:
    raise ValueError(f"Configured admin user not found: {payload['login']}")

admin_user.with_context(no_reset_password=True).sudo().write({'password': payload['password']})
env.cr.commit()
print('admin_password_updated=true')
""".replace("__PAYLOAD__", json.dumps(payload))
    _run_odoo_shell(settings, script, label="admin hardening")


def _assert_active_admin_password_is_not_default(settings: StartupSettings) -> None:
    login_names_to_check = ["admin"]
    if settings.admin_login not in login_names_to_check:
        login_names_to_check.append(settings.admin_login)

    payload = {"logins": login_names_to_check}
    script = """
import json
from odoo.exceptions import AccessDenied

payload = json.loads('__PAYLOAD__')

for login_name in payload['logins']:
    target_user = env['res.users'].sudo().with_context(active_test=False).search(
        [('login', '=', login_name)],
        limit=1,
    )
    if not target_user:
        continue

    authenticated = False
    try:
        auth_info = env['res.users'].sudo().authenticate(
            {'type': 'password', 'login': login_name, 'password': 'admin'},
            {'interactive': False},
        )
        authenticated = bool(auth_info)
    except AccessDenied:
        authenticated = False

    if authenticated:
        raise ValueError(f"Insecure configuration: active password for {login_name} is 'admin'.")

print('admin_default_password_active=false')
""".replace("__PAYLOAD__", json.dumps(payload))
    _run_odoo_shell(settings, script, label="admin password policy")


def _run_initialization_if_needed(settings: StartupSettings) -> None:
    missing_modules = _missing_required_modules(settings)
    if not missing_modules and _database_exists(settings):
        print("[platform-startup] database already initialized; skipping init", flush=True)
        return

    print(
        "[platform-startup] running database initialization for modules: "
        f"{','.join(['base', *missing_modules])}",
        flush=True,
    )
    initialize_command = _build_odoo_command(settings, initialize_modules=missing_modules, stop_after_init=True)
    subprocess.run(initialize_command, check=True)


def _wait_for_data_workflow_lock(settings: StartupSettings) -> None:
    if not settings.data_workflow_lock_file:
        return

    lock_path = settings.data_workflow_lock_file
    if not os.path.exists(lock_path):
        return

    deadline = time.monotonic() + settings.data_workflow_lock_timeout_seconds
    wait_seconds = 0
    while os.path.exists(lock_path):
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Data workflow lock {lock_path} still present after {settings.data_workflow_lock_timeout_seconds} seconds."
            )
        if wait_seconds % 10 == 0:
            print(
                f"[platform-startup] waiting for data workflow lock release: {lock_path}",
                flush=True,
            )
        time.sleep(settings.poll_interval_seconds)
        wait_seconds += 1

    print("[platform-startup] data workflow lock cleared; continuing startup", flush=True)


def main() -> None:
    arguments = _parse_arguments()
    settings = _load_settings(arguments)
    _write_runtime_config(settings)
    _wait_for_database(settings)
    _wait_for_data_workflow_lock(settings)
    _run_initialization_if_needed(settings)
    _apply_admin_password_if_configured(settings)
    if settings.admin_password:
        _assert_active_admin_password_is_not_default(settings)

    print("[platform-startup] starting Odoo web server", flush=True)
    server_command = _build_odoo_command(settings, stop_after_init=False)
    os.execv(server_command[0], server_command)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # pragma: no cover - startup guard
        print(f"[platform-startup] fatal: {error}", file=sys.stderr, flush=True)
        raise
