import json
import logging
import re
import subprocess
import time
from pathlib import Path

from .docker_api import compose_exec, ensure_services_up, get_database_service, get_script_runner_service
from .settings import TestSettings

_logger = logging.getLogger(__name__)


def get_db_user() -> str:
    settings = TestSettings()
    return settings.db_user or "odoo"


def _terminate_backends(db_name: str, db_user: str) -> None:
    compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            db_user,
            "-d",
            "postgres",
            "-c",
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();",
        ],
    )


def cleanup_test_databases(production_db: str) -> None:
    ensure_services_up([get_database_service()])
    db_user = get_db_user()
    result = compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            db_user,
            "-d",
            "postgres",
            "-t",
            "-c",
            (
                "SELECT datname FROM pg_database "
                f"WHERE datname LIKE '{production_db}_test_%' "
                f"   OR datname LIKE '{production_db}_ut_%';"
            ),
        ],
    )
    test_dbs = [db.strip() for db in result.stdout.strip().split("\n") if db.strip()] if result.returncode == 0 else []
    for db in test_dbs:
        _terminate_backends(db, db_user)
        force_drop_database(db)


def force_drop_database(db_name: str) -> None:
    db_user = get_db_user()
    compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            db_user,
            "-d",
            "postgres",
            "-c",
            f'DROP DATABASE IF EXISTS "{db_name}";',
        ],
    )


def drop_and_create(db_name: str, template: str | None = None) -> None:
    db_user = get_db_user()
    # terminate and drop
    _terminate_backends(db_name, db_user)
    force_drop_database(db_name)
    # create (optionally from template)
    if template:
        compose_exec(
            get_database_service(),
            [
                "psql",
                "-U",
                db_user,
                "-d",
                "postgres",
                "-c",
                f'CREATE DATABASE "{db_name}" TEMPLATE "{template}";',
            ],
        )
    else:
        compose_exec(
            get_database_service(),
            [
                "psql",
                "-U",
                db_user,
                "-d",
                "postgres",
                "-c",
                f'CREATE DATABASE "{db_name}";',
            ],
        )


def get_production_db_name() -> str:
    return TestSettings().db_name


def get_module_states(db_name: str, module_names: list[str]) -> dict[str, str]:
    if not module_names:
        return {}
    ensure_services_up([get_database_service()])
    db_user = get_db_user()
    safe_names: list[str] = []
    for name in module_names:
        if re.match(r"^[A-Za-z0-9_]+$", name):
            safe_names.append(name)
        else:
            _logger.warning("db: skipping unsafe module name %s", name)
    if not safe_names:
        return {}
    module_names_literal = ",".join(safe_names)
    query = (
        "SELECT name, state FROM ir_module_module "
        f"WHERE name = ANY(string_to_array('{module_names_literal}', ','));"
    )
    result = compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            db_user,
            "-d",
            db_name,
            "-t",
            "-A",
            "-F",
            "|",
            "-c",
            query,
        ],
    )
    if result.returncode != 0:
        _logger.debug("db: failed to read module states for %s", db_name)
        return {}
    states: dict[str, str] = {}
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        name, _, state = line.partition("|")
        if name:
            states[name.strip()] = state.strip()
    return states


def split_modules_for_install(db_name: str, module_names: list[str]) -> tuple[list[str], list[str]]:
    states = get_module_states(db_name, module_names)
    update_states = {"installed", "to upgrade", "to remove"}
    install_modules: list[str] = []
    update_modules: list[str] = []
    for module_name in module_names:
        state = states.get(module_name)
        if state in update_states:
            update_modules.append(module_name)
        else:
            install_modules.append(module_name)
    return install_modules, update_modules


def _db_exists(db_name: str, db_user: str) -> bool:
    res = compose_exec(
        get_database_service(),
        [
            "psql",
            "-U",
            db_user,
            "-d",
            "postgres",
            "-t",
            "-c",
            f"SELECT count(*) FROM pg_database WHERE datname = '{db_name}';",
        ],
    )
    return res.returncode == 0 and res.stdout.strip() == "1"


def _create_database(db_name: str, db_user: str) -> bool:
    res = compose_exec(
        get_database_service(),
        ["createdb", "-U", db_user, db_name],
    )
    return res.returncode == 0


def wait_for_database_ready(retries: int = 30, delay: float = 1.0) -> bool:
    ensure_services_up([get_database_service()])
    db_user = get_db_user()
    for _ in range(max(1, retries)):
        res = compose_exec(get_database_service(), ["psql", "-U", db_user, "-d", "postgres", "-c", "SELECT 1;"])
        if res.returncode == 0:
            return True
        time.sleep(delay)
    return False


def db_capacity() -> tuple[int, int]:
    """Return (max_connections, active_connections). Best-effort."""
    ensure_services_up([get_database_service()])
    db_user = get_db_user()
    max_conn = 100
    active = 0
    try:
        res = compose_exec(
            get_database_service(),
            [
                "psql",
                "-U",
                db_user,
                "-d",
                "postgres",
                "-t",
                "-c",
                "SHOW max_connections;",
            ],
            timeout=10,
        )
    except subprocess.TimeoutExpired as exc:
        _logger.debug("db: timeout reading max_connections (%s)", exc)
        res = None
    if res and res.returncode == 0:
        try:
            max_conn = int(res.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            _logger.debug("db: failed to parse max_connections (%s)", exc)
    try:
        res2 = compose_exec(
            get_database_service(),
            [
                "psql",
                "-U",
                db_user,
                "-d",
                "postgres",
                "-t",
                "-c",
                "SELECT count(*) FROM pg_stat_activity;",
            ],
            timeout=10,
        )
    except subprocess.TimeoutExpired as exc:
        _logger.debug("db: timeout reading pg_stat_activity (%s)", exc)
        res2 = None
    if res2 and res2.returncode == 0:
        try:
            active = int(res2.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            _logger.debug("db: failed to parse active connections (%s)", exc)
    return max_conn, active


def drop_and_create_test_database(db_name: str) -> None:
    db_user = get_db_user()
    wait_for_database_ready()
    force_drop_database(db_name)
    _create_database(db_name, db_user)


def clone_production_database(db_name: str) -> None:
    production_db = get_production_db_name()
    db_user = get_db_user()
    wait_for_database_ready()
    force_drop_database(db_name)
    if not _create_database(db_name, db_user):
        return
    cmd = (
        f"set -o pipefail; pg_dump -Fc -U {db_user} {production_db} | "
        f"pg_restore -U {db_user} -d {db_name} --no-owner --role={db_user}"
    )
    compose_exec(get_database_service(), ["bash", "-lc", cmd])


def create_template_from_production(template_db: str, *, timeout_sec: int | None = None) -> None:
    """Create a template test database from production once per session."""
    db_user = get_db_user()
    wait_for_database_ready()
    force_drop_database(template_db)
    # Create empty target database
    if not _create_database(template_db, db_user):
        return
    # Clone from production
    production_db = get_production_db_name()
    dump_command = (
        f"set -o pipefail; pg_dump -Fc -U {db_user} {production_db} | "
        f"pg_restore -U {db_user} -d {template_db} --no-owner --role={db_user}"
    )
    compose_exec(get_database_service(), ["bash", "-lc", dump_command], timeout=timeout_sec)


def build_module_template(
    template_db: str,
    modules: list[str],
    *,
    timeout_sec: int | None = None,
    log_path: Path | None = None,
) -> None:
    if not modules:
        return
    ensure_services_up([get_database_service(), get_script_runner_service()])
    drop_and_create_test_database(template_db)
    module_list = ",".join(modules)
    command = [
        "/odoo/odoo-bin",
        "-d",
        template_db,
        "--stop-after-init",
        "--max-cron-threads=0",
        "--workers=0",
        f"--db-filter=^{template_db}$",
        "--log-level=test",
        "--without-demo",
        "-i",
        module_list,
    ]
    result = compose_exec(get_script_runner_service(), command, timeout=timeout_sec)
    if log_path:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text((result.stdout or "") + (result.stderr or ""))
        except OSError as exc:
            _logger.debug("db: failed to write template log (%s)", exc)
    if result.returncode != 0:
        raise RuntimeError(f"module template build failed (rc={result.returncode})")


def template_reuse_candidate(_base_db: str, ttl_sec: int) -> str | None:
    """Return an existing reusable template DB name or None.

    We record the last template name and time in tmp/test-logs/template.json.
    If REUSE_TEMPLATE is enabled and TTL not expired, and DB exists, reuse it.
    """
    from time import time

    metadata_path = Path("tmp/test-logs/template.json")
    if not metadata_path.exists():
        return None
    try:
        data = json.loads(metadata_path.read_text())
        name = data.get("name")
        created = float(data.get("created", 0))
        if not name:
            return None
        if ttl_sec and (time() - created) > ttl_sec:
            return None
        if _db_exists(name, get_db_user()):
            return name
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        _logger.debug("db: failed to read template metadata (%s)", exc)
        return None
    return None


def record_template(template_db: str) -> None:
    from time import time

    metadata_path = Path("tmp/test-logs/template.json")
    try:
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps({"name": template_db, "created": time()}))
    except OSError as exc:
        _logger.debug("db: failed to record template metadata (%s)", exc)
