import json
import os
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    # Ensure logs dir
    logs = Path("tmp/test-logs")
    logs.mkdir(parents=True, exist_ok=True)
    pid_file = logs / "test-all.pid"
    launcher_out = logs / "launcher.out"

    # Launch detached; respect existing env overrides but force TEST_DETACHED=1 for long phases
    env = os.environ.copy()
    env.setdefault("TEST_DETACHED", "1")

    # Build command
    cmd = ["nohup", "env"] + [f"{k}={v}" for k, v in env.items() if k in ("TEST_DETACHED", "TEST_TAGS", "TOUR_TIMEOUT")]
    cmd += ["uv", "run", "test-all"]

    with open(launcher_out, "ab", buffering=0) as out:
        # Start process in background
        proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT)
    pid = proc.pid
    pid_file.write_text(str(pid))

    # Prefer the in-progress 'current' pointer to report the active session
    session = None
    cur = Path("tmp/test-logs/current")
    cur_json = cur.with_suffix(".json")
    # Wait briefly for 'current' to appear
    for _ in range(20):  # ~2s total
        if cur.exists():
            try:
                session = Path(os.readlink(cur)).name
            except OSError:
                # If it's a real dir, use its name
                session = cur.name
            break
        if cur_json.exists():
            try:
                data = json.loads(cur_json.read_text())
                session = Path(data.get("current", "")).name or None
                if session:
                    break
            except Exception:
                pass
        try:
            import time as _t

            _t.sleep(0.1)
        except Exception:
            break

    # Fallback to latest pointer only if current is not available yet
    if session is None:
        latest_json = Path("tmp/test-logs/latest.json")
        try:
            if latest_json.exists():
                data = json.loads(latest_json.read_text())
                session = Path(data.get("latest", "")).name or None
        except Exception:
            pass

    payload = {"status": "running", "pid": pid, "pid_file": str(pid_file), "session": session}
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
