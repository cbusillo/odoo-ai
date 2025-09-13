import argparse
import json
import sys
import time
from pathlib import Path


def _resolve_active_dir(fallback: Path) -> Path:
    base = fallback.parent
    # Prefer 'current' if present (in-progress)
    cur = base / "current"
    if cur.exists():
        return cur
    cj = cur.with_suffix(".json")
    try:
        data = json.loads(cj.read_text())
        p = Path(data.get("current"))
        if p.exists():
            return p
    except Exception:
        pass
    # Fall back to 'latest'
    if fallback.exists():
        return fallback
    lj = base / "latest.json"
    try:
        data = json.loads(lj.read_text())
        p = Path(data.get("latest"))
        if p.exists():
            return p
    except Exception:
        pass
    return fallback


def read_summary(latest_dir: Path) -> dict | None:
    summary = latest_dir / "summary.json"
    try:
        if summary.exists() and summary.is_file():
            with open(summary) as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return None


def check_status(latest_dir: Path) -> int:
    """Return code semantics:
    - 0: tests finished and success == True
    - 1: tests finished and success == False
    - 2: tests not finished yet / no summary available
    - 3: invalid state (corrupt summary)
    """
    data = read_summary(latest_dir)
    if data is None:
        return 2
    try:
        success = bool(data.get("success"))
    except Exception:
        return 3
    return 0 if success else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wait for test-all completion and gate on summary.json")
    parser.add_argument("--latest", default="tmp/test-logs/latest", help="Path to latest dir or symlink")
    parser.add_argument("--session", default=None, help="Specific session dir (overrides --latest)")
    parser.add_argument("--wait", action="store_true", help="Block until completion (success or failure)")
    parser.add_argument("--timeout", type=int, default=0, help="Max seconds to wait when --wait is used (0 = no limit)")
    parser.add_argument("--interval", type=int, default=10, help="Poll interval seconds when waiting")
    parser.add_argument("--json", action="store_true", help="Emit JSON status instead of text")
    args = parser.parse_args(argv)

    latest_path = Path(args.session) if args.session else _resolve_active_dir(Path(args.latest))

    if not args.wait:
        rc = check_status(latest_path)
        status = {0: "done:success", 1: "done:failed", 2: "running", 3: "invalid"}[rc]
        if args.json:
            out = {"status": status, "code": rc, "session": latest_path.name, "summary": str(latest_path / "summary.json")}
            print(json.dumps(out))
        else:
            print(f"test_wait status: {status}")
        return rc

    # Wait mode
    start = time.time()
    while True:
        rc = check_status(latest_path)
        if rc in (0, 1, 3):
            if args.json:
                status = {0: "done:success", 1: "done:failed", 3: "invalid"}[rc]
                out = {"status": status, "code": rc, "session": latest_path.name, "summary": str(latest_path / "summary.json")}
                print(json.dumps(out))
            return rc
        if args.timeout and (time.time() - start) > args.timeout:
            if args.json:
                print(json.dumps({"status": "timeout", "code": 2, "session": latest_path.name}))
            else:
                print("test_wait status: timeout")
            return 2
        time.sleep(max(1, args.interval))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
