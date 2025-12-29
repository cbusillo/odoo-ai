import json
import logging
import time
from pathlib import Path

from .docker_api import compose_exec, ensure_services_up, get_database_service
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
    )
    if res.returncode == 0:
        try:
            max_conn = int(res.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            _logger.debug("db: failed to parse max_connections (%s)", exc)
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
    )
    if res2.returncode == 0:
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


def create_template_from_production(template_db: str) -> None:
    """Create a template test database from production once per session."""
    db_user = get_db_user()
    wait_for_database_ready()
    force_drop_database(template_db)
    # Create empty target database
    if not _create_database(template_db, db_user):
        return
    # Clone from production
    production_db = get_production_db_name()
    cmd = (
        f"set -o pipefail; pg_dump -Fc -U {db_user} {production_db} | "
        f"pg_restore -U {db_user} -d {template_db} --no-owner --role={db_user}"
    )
    compose_exec(get_database_service(), ["bash", "-lc", cmd])


def template_reuse_candidate(_base_db: str, ttl_sec: int) -> str | None:
    """Return an existing reusable template DB name or None.

    We record the last template name and time in tmp/test-logs/template.json.
    If REUSE_TEMPLATE is enabled and TTL not expired, and DB exists, reuse it.
    """
    from time import time

    meta = Path("tmp/test-logs/template.json")
    if not meta.exists():
        return None
    try:
        data = json.loads(meta.read_text())
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

    p = Path("tmp/test-logs/template.json")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"name": template_db, "created": time()}))
    except OSError as exc:
        _logger.debug("db: failed to record template metadata (%s)", exc)
