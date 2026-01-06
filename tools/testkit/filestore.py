from .docker_api import compose_exec, ensure_services_up, get_script_runner_service
from .settings import TestSettings


def filestore_root() -> str:
    settings = TestSettings()
    return (settings.filestore_path or "/volumes/data").rstrip("/")


def snapshot_filestore(test_db_name: str, production_db: str) -> None:
    root = filestore_root()
    production_filestore = f"{root}/filestore/{production_db}"
    test_filestore = f"{root}/filestore/{test_db_name}"
    service = get_script_runner_service()
    ensure_services_up([service])
    exists = compose_exec(service, ["sh", "-c", f"[ -d '{production_filestore}' ] && echo 1 || echo 0"]).stdout.strip()
    if not exists.endswith("1"):
        return
    compose_exec(service, ["sh", "-c", f"rm -rf '{test_filestore}' || true"])
    # try hardlinks then rsync
    res = compose_exec(
        service,
        [
            "sh",
            "-c",
            f"if [ -d '{production_filestore}' ]; then cp -al '{production_filestore}' '{test_filestore}' 2>/dev/null || false; else exit 1; fi",
        ],
    )
    if res.returncode == 0:
        return
    compose_exec(service, ["sh", "-c", f"rsync -a --delete '{production_filestore}/' '{test_filestore}/' 2>/dev/null || false"])


def cleanup_filestores(production_db: str) -> None:
    service = get_script_runner_service()
    ensure_services_up([service])
    root = filestore_root()
    res = compose_exec(service, ["sh", "-c", f"ls -d {root}/filestore/{production_db}_test_* 2>/dev/null || true"])
    for line in filter(None, res.stdout.strip().split("\n")):
        kind = compose_exec(
            service,
            [
                "sh",
                "-c",
                f"if [ -L '{line}' ]; then echo 'symlink'; elif [ -d '{line}' ]; then echo 'directory'; else echo 'unknown'; fi",
            ],
        ).stdout.strip()
        if kind == "symlink":
            compose_exec(service, ["rm", line])
        else:
            compose_exec(service, ["rm", "-rf", line])


def cleanup_single_test_filestore(db_name: str) -> None:
    service = get_script_runner_service()
    ensure_services_up([service])
    root = filestore_root()
    target = f"{root}/filestore/{db_name}"
    compose_exec(service, ["sh", "-c", f"[ -e '{target}' ] && rm -rf '{target}' || true"])


def filestore_exists(db_name: str) -> bool:
    service = get_script_runner_service()
    ensure_services_up([service])
    root = filestore_root()
    target = f"{root}/filestore/{db_name}"
    res = compose_exec(service, ["sh", "-c", f"[ -e '{target}' ] && echo 1 || echo 0"])
    return (res.stdout or "").strip().endswith("1")
