#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def which(candidates):
    for c in candidates:
        if c and (Path(c).exists() and os.access(c, os.X_OK) or shutil.which(c)):
            return c
    return None


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)
    return p


def run(cmd, cwd=None):
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    return proc.returncode, proc.stdout, proc.stderr


def digest(transcript: Path):
    # Emulate previous digest: permissionMode, subagents used, test commands, inspection calls
    perm = None
    subagents = {}
    tests = []
    writes = 0
    inspection = []

    try:
        lines = transcript.read_text(errors="ignore").splitlines()
    except Exception as e:
        print(f"[warn] could not read transcript: {e}", file=sys.stderr)
        return

    for ln in lines:
        try:
            o = json.loads(ln)
        except Exception:
            continue
        if o.get("type") == "system" and o.get("subtype") == "init":
            perm = o.get("permissionMode")
        m = o.get("message") or {}
        for part in m.get("content") or []:
            if part.get("type") == "tool_use":
                name = part.get("name")
                if name == "Task":
                    st = (part.get("input") or {}).get("subagent_type", "")
                    if st:
                        subagents[st] = subagents.get(st, 0) + 1
                if name == "Bash":
                    cmd = (part.get("input") or {}).get("command", "")
                    if "uv run test-" in cmd:
                        tests.append(cmd)
                    if "addons/" in cmd:
                        writes += 1
                if name and name.startswith("mcp__inspection-pycharm__"):
                    inspection.append(name)

    print("--- Digest (Claude) ---", file=sys.stderr)
    print("permissionMode:", perm, file=sys.stderr)
    print("subagents:", subagents, file=sys.stderr)
    print("writes (bash touching addons/):", writes, file=sys.stderr)
    print("tests (uv run):", tests, file=sys.stderr)
    print("inspection calls:", inspection[-3:], file=sys.stderr)
    print("--- End Digest ---", file=sys.stderr)


def prune_artifacts(art_root: Path, keep: int):
    if not art_root.exists():
        return
    dirs = sorted([p for p in art_root.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
    for d in dirs[keep:]:
        print(f"[info] prune: removing {d}", file=sys.stderr)
        shutil.rmtree(d, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Claude integration test runner (Python)")
    parser.add_argument("--permission-mode", default=os.environ.get("PERMISSION_MODE", "bypassPermissions"))
    parser.add_argument("--suffix", default=os.environ.get("RUN_SUFFIX", "claude"))
    parser.add_argument("--digest", action="store_true")
    parser.add_argument("--prune", type=int)
    parser.add_argument("--claude-bin", dest="claude_bin", default=os.environ.get("CLAUDE_BIN", ""))
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    run_dir = ensure_dir(root / "tmp" / "claude-subagent-test")
    transcript = run_dir / "transcript.jsonl"

    claude_bin = which(
        [
            args.claude_bin,
            "claude",
            str(Path.home() / ".claude/local/claude"),
            "/Users/cbusillo/.claude/local/claude",
            "/opt/homebrew/bin/claude",
            "/usr/local/bin/claude",
        ]
    )
    if not claude_bin:
        print("error: Claude CLI not found. Set CLAUDE_BIN to the absolute path or add it to PATH.", file=sys.stderr)
        sys.exit(1)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        code, so, _ = run(["git", "rev-parse", "--short", "HEAD"], cwd=root)
        sha = so.strip() if code == 0 else "no-git"
    except Exception:
        sha = "no-git"
    run_id = f"{ts}-{sha}"

    module_dir = f"addons/warranty_manager_{args.suffix}"
    prompt = (
        "Execute the task in @docs/llm-cli-tests/tasks/warranty_manager.md using subagents per @CLAUDE.md. "
        f'For this run, name the addon "{module_dir}" (underscore suffix). Place tests under "{module_dir}/tests" '
        f'and run tests with "uv run test-unit {module_dir}". Do NOT write to "addons/warranty_manager" without the suffix. '
        "Apply changes and run tests (uv run). Use a dedicated testing subagent and iterate until tests pass. "
        "Run MCP inspection and fix issues until clean. Save long artifacts under tmp/subagent-runs/."
    )

    env = os.environ.copy()
    env["SUBAGENT_RUN_ID"] = run_id

    cmd = [
        claude_bin,
        "--permission-mode",
        args.permission_mode,
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
    ]

    print(f"[info] Running Claude: writing transcript to {transcript} (permission-mode={args.permission_mode})", file=sys.stderr)
    with transcript.open("w", encoding="utf-8", errors="ignore") as fh:
        proc = subprocess.Popen(cmd, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            fh.write(line)
        rc = proc.wait()

    print(f"[done] Transcript written to {transcript}", file=sys.stderr)

    if args.digest:
        digest(transcript)
    if args.prune and args.prune > 0:
        prune_artifacts(root / "tmp" / "subagent-runs", args.prune)

    sys.exit(rc)


if __name__ == "__main__":
    main()
