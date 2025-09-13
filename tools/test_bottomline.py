import argparse
import json
import sys
from pathlib import Path


def read_summary(path: Path) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print bottom-line test result and exit 0/1")
    parser.add_argument("--latest", default="tmp/test-logs/latest", help="Path to latest dir")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    latest = Path(args.latest)
    summary = read_summary(latest / "summary.json")
    if not summary:
        print("no_summary")
        return 2
    ok = bool(summary.get("success"))
    total = summary.get("counters_total") or {}
    rcodes = summary.get("return_codes") or {}
    out = {
        "success": ok,
        "tests_run": total.get("tests_run"),
        "failures": total.get("failures"),
        "errors": total.get("errors"),
        "skips": total.get("skips"),
        "return_codes": rcodes,
        "session": summary.get("session"),
        "summary": str((latest / "summary.json").resolve()),
    }
    if args.json:
        print(json.dumps(out))
    else:
        print(
            f"success={out['success']} tests_run={out['tests_run']} failures={out['failures']} errors={out['errors']} skips={out['skips']} session={out['session']}"
        )
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
