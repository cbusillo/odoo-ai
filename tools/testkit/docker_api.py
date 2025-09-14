from __future__ import annotations

import subprocess
from pathlib import Path


def get_script_runner_service() -> str:
    result = subprocess.run(["docker", "compose", "ps", "--services"], capture_output=True, text=True)
    services = result.stdout.strip().split("\n") if result.returncode == 0 else []
    for service in services:
        if "script" in service.lower() and "runner" in service.lower():
            return service
    return "script-runner"


def get_database_service() -> str:
    return "database"


def compose_exec(service: str, args: list[str], capture_output: bool = True) -> subprocess.CompletedProcess:
    cmd = ["docker", "compose", "exec", "-T", service] + args
    return subprocess.run(cmd, capture_output=capture_output, text=True)


def ensure_services_up(services: list[str]) -> None:
    for s in services:
        subprocess.run(["docker", "compose", "up", "-d", s], capture_output=True)


def project_root() -> Path:
    return Path.cwd()
