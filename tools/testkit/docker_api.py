import os
import subprocess
from pathlib import Path

from tools.deployer.settings import parse_env_file


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _resolve_env_file(env: dict[str, str]) -> Path | None:
    raw_value = _blank_to_none(env.get("TESTKIT_ENV_FILE"))
    if not raw_value:
        return None
    env_path = Path(os.path.expandvars(os.path.expanduser(raw_value))).resolve()
    if not env_path.exists():
        raise FileNotFoundError(f"TESTKIT_ENV_FILE not found: {env_path}")
    return env_path


def compose_env() -> dict[str, str]:
    """Return an env dict suitable for `docker compose`.

    Testkit shells out to `docker compose` directly (instead of going through the
    deployer stack helpers). Compose variable interpolation relies on the
    process environment (and/or `.env`).

    In local setups we often keep `ODOO_STATE_ROOT=~/...` in `.env`, which
    Docker Compose does not expand. We normalize it to absolute paths and
    ensure the bind-mount variables used in `docker-compose.yml` are set.
    """

    env = os.environ.copy()
    env_file_path = _resolve_env_file(env)
    if env_file_path:
        env.update(parse_env_file(env_file_path))
    else:
        dotenv_path = Path.cwd() / ".env"
        if dotenv_path.exists():
            env.update(parse_env_file(dotenv_path))

    project_name = (_blank_to_none(env.get("ODOO_PROJECT_NAME")) or "odoo").strip()
    state_root_raw = _blank_to_none(env.get("ODOO_STATE_ROOT"))
    if state_root_raw is None:
        state_root_raw = str(Path.home() / "odoo-ai" / project_name)
    state_root_path = Path(os.path.expandvars(os.path.expanduser(state_root_raw))).resolve()

    data_dir_host_raw = _blank_to_none(env.get("ODOO_DATA_HOST_DIR"))
    log_dir_host_raw = _blank_to_none(env.get("ODOO_LOG_HOST_DIR"))
    db_dir_host_raw = _blank_to_none(env.get("ODOO_DB_HOST_DIR"))

    data_dir_host = Path(os.path.expandvars(os.path.expanduser(data_dir_host_raw))).resolve() if data_dir_host_raw else (
        state_root_path / "data"
    )
    log_dir_host = Path(os.path.expandvars(os.path.expanduser(log_dir_host_raw))).resolve() if log_dir_host_raw else (
        state_root_path / "logs"
    )
    db_dir_host = Path(os.path.expandvars(os.path.expanduser(db_dir_host_raw))).resolve() if db_dir_host_raw else (
        state_root_path / "postgres"
    )

    env["ODOO_STATE_ROOT"] = str(state_root_path)
    env["ODOO_DATA_HOST_DIR"] = str(data_dir_host)
    env["ODOO_LOG_HOST_DIR"] = str(log_dir_host)
    env["ODOO_DB_HOST_DIR"] = str(db_dir_host)
    env.setdefault("COMPOSE_INTERACTIVE_NO_CLI", "1")
    env.setdefault("COMPOSE_MENU", "false")
    return env


def get_script_runner_service() -> str:
    result = subprocess.run(
        ["docker", "compose", "ps", "--services"],
        capture_output=True,
        text=True,
        env=compose_env(),
    )
    services = result.stdout.strip().split("\n") if result.returncode == 0 else []
    for service in services:
        if "script" in service.lower() and "runner" in service.lower():
            return service
    return "script-runner"


def get_database_service() -> str:
    return "database"


def compose_exec(service: str, args: list[str], capture_output: bool = True) -> subprocess.CompletedProcess:
    command = ["docker", "compose", "exec", "-T", service] + args
    return subprocess.run(command, capture_output=capture_output, text=True, env=compose_env())


def ensure_services_up(services: list[str]) -> None:
    for service_name in services:
        subprocess.run(
            ["docker", "compose", "up", "-d", service_name],
            capture_output=True,
            env=compose_env(),
        )


def project_root() -> Path:
    return Path.cwd()
