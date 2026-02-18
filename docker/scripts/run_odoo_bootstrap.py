#!/usr/bin/env python3
"""Bootstrap Odoo databases before launching the long-running web server.

This wrapper keeps first-start behavior deterministic:
- Wait for PostgreSQL connectivity
- Initialize the configured database when required
- Start the standard Odoo HTTP server process

The command is safe to run on every container start because initialization only
executes when the target database is missing required installed modules.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass

import psycopg2


@dataclass(frozen=True)
class BootstrapSettings:
    config_path: str
    database_name: str
    database_host: str
    database_port: int
    database_user: str
    database_password: str
    install_modules: tuple[str, ...]
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


def _load_settings(argument_namespace: argparse.Namespace) -> BootstrapSettings:
    database_name = os.environ.get("ODOO_DB_NAME", "").strip()
    if not database_name:
        raise RuntimeError("ODOO_DB_NAME must be set for bootstrap startup.")

    database_port_raw = os.environ.get("ODOO_DB_PORT", "5432").strip() or "5432"
    database_port = int(database_port_raw)
    install_modules = _split_modules(os.environ.get("ODOO_INSTALL_MODULES", ""))

    return BootstrapSettings(
        config_path=argument_namespace.config_path,
        database_name=database_name,
        database_host=os.environ.get("ODOO_DB_HOST", "database").strip() or "database",
        database_port=database_port,
        database_user=os.environ.get("ODOO_DB_USER", "odoo").strip() or "odoo",
        database_password=os.environ.get("ODOO_DB_PASSWORD", ""),
        install_modules=install_modules,
        ready_timeout_seconds=180,
        poll_interval_seconds=2.0,
    )


def _wait_for_database(settings: BootstrapSettings) -> None:
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


def _database_exists(settings: BootstrapSettings) -> bool:
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


def _installed_module_names(settings: BootstrapSettings) -> set[str]:
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


def _missing_required_modules(settings: BootstrapSettings) -> tuple[str, ...]:
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
    settings: BootstrapSettings,
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


def _run_initialization_if_needed(settings: BootstrapSettings) -> None:
    missing_modules = _missing_required_modules(settings)
    if not missing_modules and _database_exists(settings):
        print("[platform-bootstrap] database already initialized; skipping init", flush=True)
        return

    print(
        "[platform-bootstrap] running database bootstrap for modules: "
        f"{','.join(['base', *missing_modules])}",
        flush=True,
    )
    initialize_command = _build_odoo_command(settings, initialize_modules=missing_modules, stop_after_init=True)
    subprocess.run(initialize_command, check=True)


def main() -> None:
    arguments = _parse_arguments()
    settings = _load_settings(arguments)
    _wait_for_database(settings)
    _run_initialization_if_needed(settings)

    print("[platform-bootstrap] starting Odoo web server", flush=True)
    server_command = _build_odoo_command(settings, initialize_modules=None, stop_after_init=False)
    os.execv(server_command[0], server_command)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # pragma: no cover - startup guard
        print(f"[platform-bootstrap] fatal: {error}", file=sys.stderr, flush=True)
        raise
