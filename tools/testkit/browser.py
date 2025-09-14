from __future__ import annotations

from .docker_api import compose_exec, ensure_services_up, get_script_runner_service


def kill_browsers_and_zombies() -> None:
    service = get_script_runner_service()
    ensure_services_up([service])
    for name in ("chrome", "chromium"):
        compose_exec(service, ["pkill", name])
    for name in ("chrome", "chromium", "geckodriver", "chromedriver"):
        compose_exec(service, ["pkill", "-9", name])
    compose_exec(service, ["sh", "-c", "ps aux | grep defunct | awk '{print $2}' | xargs -r kill -9"])  # noqa: ISC001


def restart_script_runner_with_orphan_cleanup() -> None:
    # We avoid changing docker files; rely on compose up with remove-orphans
    from subprocess import run

    service = get_script_runner_service()
    run(["docker", "compose", "up", "-d", "--remove-orphans", service])
