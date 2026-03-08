import os
import secrets
import string

from .db import get_db_user
from .docker_api import compose_exec, ensure_services_up, get_database_service, get_script_runner_service


def _last_output_line(result_output: str | None) -> str:
    if not result_output:
        return ""
    lines = [line.strip() for line in result_output.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def setup_test_authentication(db_name: str) -> str:
    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(16))
    service = get_script_runner_service()
    ensure_services_up([service])

    # Hash in-container via passlib. Fail closed if hashing is unavailable.
    hash_res = compose_exec(
        service,
        [
            "env",
            f"TESTKIT_PASS={password}",
            "python",
            "-c",
            (
                "import os; "
                "from passlib.context import CryptContext; "
                "print(CryptContext(schemes=['pbkdf2_sha512']).hash(os.environ['TESTKIT_PASS']))"
            ),
        ],
    )
    if hash_res.returncode != 0:
        detail = _last_output_line(hash_res.stderr) or _last_output_line(hash_res.stdout)
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Unable to hash test admin password with passlib in script-runner container{suffix}")
    hash_output = (hash_res.stdout or "").strip().splitlines()
    if not hash_output:
        raise RuntimeError("Hash command returned no output for test admin password")
    hashed = hash_output[-1]
    sanitized = hashed.replace("'", "''")
    sql = f"UPDATE res_users SET password='{sanitized}' WHERE login='admin';"

    update_result = compose_exec(
        get_database_service(),
        ["psql", "-U", get_db_user(), "-d", db_name, "-c", sql],
    )
    if update_result.returncode != 0:
        detail = _last_output_line(update_result.stderr) or _last_output_line(update_result.stdout)
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Unable to persist hashed test admin password{suffix}")
    os.environ["ODOO_TEST_PASSWORD"] = password
    return password
