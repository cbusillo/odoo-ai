from __future__ import annotations

import os
import secrets
import string

from .db import get_db_user
from .docker_api import compose_exec, ensure_services_up, get_database_service, get_script_runner_service


def setup_test_authentication(db_name: str) -> str:
    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(16))
    service = get_script_runner_service()
    ensure_services_up([service])

    # Hash with passlib in the container if available
    hash_res = compose_exec(
        service,
        [
            "python",
            "-c",
            "from passlib.context import CryptContext; print(CryptContext(schemes=['pbkdf2_sha512']).hash('" + password + "'))",
        ],
    )
    if hash_res.returncode == 0:
        hashed = (hash_res.stdout or "").strip().splitlines()[-1]
        sanitized = hashed.replace("'", "''")
        sql = f"UPDATE res_users SET password='{sanitized}' WHERE login='admin';"
    else:
        sql = f"UPDATE res_users SET password='{password}' WHERE login='admin';"

    compose_exec(
        get_database_service(),
        ["psql", "-U", get_db_user(), "-d", db_name, "-c", sql],
    )
    os.environ["ODOO_TEST_PASSWORD"] = password
    return password
