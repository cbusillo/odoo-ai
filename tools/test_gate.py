import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _resolve_latest_dir(default: Path) -> Path:
    if default.exists():
        return default
    pointer = default.parent / "latest.json"
    try:
        data = json.loads(pointer.read_text())
        latest = Path(data.get("latest"))
        if latest.exists():
            return latest
    except Exception:
        pass
    return default


def _read_summary(latest_dir: Path) -> dict | None:
    p = latest_dir / "summary.json"
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return None


def _status(latest_dir: Path) -> int:
    data = _read_summary(latest_dir)
    if data is None:
        return 2  # running/unknown
    try:
        return 0 if bool(data.get("success")) else 1
    except Exception:
        return 3


def _bottomline(latest_dir: Path) -> dict | None:
    s = _read_summary(latest_dir)
    if not s:
        return None
    ct = s.get("counters_total") or {}
    return {
        "success": bool(s.get("success")),
        "tests_run": ct.get("tests_run"),
        "failures": ct.get("failures"),
        "errors": ct.get("errors"),
        "skips": ct.get("skips"),
        "return_codes": s.get("return_codes") or {},
        "session": s.get("session"),
        "summary": str((latest_dir / "summary.json").resolve()),
    }


def _launch_detached() -> int:
    logs = Path("tmp/test-logs")
    logs.mkdir(parents=True, exist_ok=True)
    pid_file = logs / "test-all.pid"
    out = logs / "launcher.out"
    env = os.environ.copy()
    env.setdefault("TEST_DETACHED", "1")
    cmd = ["nohup", "env", "TEST_DETACHED=1", "uv", "run", "test-all"]
    with open(out, "ab", buffering=0) as f:
        proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
    pid_file.write_text(str(proc.pid))
    return proc.pid


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Single-call gate: launch if needed, wait, exit 0/1 on summary")
    parser.add_argument("--latest", default="tmp/test-logs/latest", help="Path to latest dir")
    parser.add_argument("--timeout", type=int, default=7200, help="Max seconds to wait (default 2h)")
    parser.add_argument("--interval", type=int, default=10, help="Poll interval seconds")
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--launch-only", action="store_true", help="Only launch and exit (prints JSON pid)")
    parser.add_argument("--status-only", action="store_true", help="Only report status/bottom line; do not launch")
    args = parser.parse_args(argv)

    latest = _resolve_latest_dir(Path(args.latest))

    # argparse replaces '-' with '_' for attribute names
    if args.launch_only:
        pid = _launch_detached()
        payload = {"status": "running", "pid": pid}
        print(json.dumps(payload) if args.json else f"running pid={pid}")
        return 0

    st = _status(latest)
    if args.status_only:
        if st == 2:
            print(json.dumps({"status": "running"}) if args.json else "running")
            return 2
        bl = _bottomline(latest) or {}
        if args.json:
            print(json.dumps(bl))
        else:
            print(
                f"success={bl.get('success')} tests_run={bl.get('tests_run')} failures={bl.get('failures')} errors={bl.get('errors')} skips={bl.get('skips')} session={bl.get('session')}"
            )
        return 0 if bl.get("success") else 1

    # Default: ensure running, then wait and return bottom line
    if st == 2:
        # already running → just wait
        pass
    elif st in (0, 1):
        # finished; proceed to bottom line
        pass
    else:  # 3 invalid or no summary yet
        _launch_detached()

    start = time.time()
    while True:
        st = _status(latest)
        if st in (0, 1):
            bl = _bottomline(latest) or {}
            if args.json:
                print(json.dumps(bl))
            else:
                print(
                    f"success={bl.get('success')} tests_run={bl.get('tests_run')} failures={bl.get('failures')} errors={bl.get('errors')} skips={bl.get('skips')} session={bl.get('session')}"
                )
            return 0 if bl.get("success") else 1
        if args.timeout and (time.time() - start) > args.timeout:
            if args.json:
                print(json.dumps({"status": "timeout"}))
            else:
                print("timeout")
            return 2
        time.sleep(max(1, args.interval))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
