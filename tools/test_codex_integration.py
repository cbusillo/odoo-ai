#!/usr/bin/env python3
import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def which(candidates):
    for c in candidates:
        if c and shutil.which(c):
            return c
    return None


def run(cmd, cwd=None):
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    return proc.returncode, proc.stdout, proc.stderr


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)
    return p


def digest(transcript: Path, repo_root: Path):
    out = []
    out.append(f"--- Digest ({transcript}) ---")
    try:
        text = transcript.read_text(errors="ignore")
    except Exception as e:
        out.append(f"[warn] could not read transcript: {e}")
        print("\n".join(out), file=sys.stderr)
        return

    # Grep-like summary
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(r"(addons/|uv run test-|inspection-pycharm__)", line):
            out.append(f"{i}: {line}")

    # Git status of addons
    code, so, se = run(["git", "status", "--porcelain=v1", "addons"], cwd=repo_root)
    out.append("\nFiles in addons/:")
    out.append(so.strip())

    # Warranty modules present
    try:
        names = sorted(os.listdir(repo_root / "addons"))
    except FileNotFoundError:
        names = []
    mods = [n for n in names if n.startswith("warranty_manager_")]
    out.append("\nwarranty_manager_* modules present:")
    out.extend(mods or ["(none)"])
    out.append("--- End Digest ---")
    print("\n".join(out), file=sys.stderr)


def prune(run_dir: Path, keep: int):
    files = sorted(run_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files[keep:]:
        print(f"[info] prune: removing {f}", file=sys.stderr)
        try:
            f.unlink()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Codex integration test runner (Python)")
    parser.add_argument("--task", default="@docs/llm-cli-tests/tasks/warranty_manager.md")
    parser.add_argument(
        "--allowed-tools",
        default="Bash Edit Write mcp__inspection-pycharm__inspection_trigger mcp__inspection-pycharm__inspection_get_status mcp__inspection-pycharm__inspection_get_problems",
    )
    parser.add_argument("--sandbox", default="workspace-write")
    parser.add_argument("--suffix", default=os.environ.get("RUN_SUFFIX", "codex"))
    parser.add_argument("--digest", action="store_true")
    parser.add_argument("--verbose", action="store_true", help="Stream Codex output to stdout (default: quiet)")
    parser.add_argument("--prune", type=int)
    parser.add_argument("--codex-bin", dest="codex_bin", default=os.environ.get("CODEX_BIN", ""))
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    run_dir = ensure_dir(root / "tmp" / "codex-runs")

    codex_bin = which([args.codex_bin, "codex", "/opt/homebrew/bin/codex", "/usr/local/bin/codex"])
    if codex_bin is None:
        env_bin = os.environ.get("CODEX_BIN", "")
        codex_bin = which([env_bin, "codex", "/opt/homebrew/bin/codex", "/usr/local/bin/codex"])
    if not codex_bin:
        print("error: codex not found", file=sys.stderr)
        sys.exit(1)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        code, so, _ = run(["git", "rev-parse", "--short", "HEAD"], cwd=root)
        sha = so.strip() if code == 0 else "no-git"
    except Exception:
        sha = "no-git"
    run_id = f"{ts}-{sha}"
    transcript = run_dir / f"{run_id}.txt"

    module_dir = f"addons/warranty_manager_{args.suffix}"
    prompt = (
        f"Execute the task in {args.task}. Follow project rules in AGENTS.md and docs/codex/WORKFLOW.md. "
        f'For this run, name the addon "{module_dir}" (underscore suffix). Place tests under "{module_dir}/tests" '
        f'and run tests with "uv run test-unit {module_dir}". Do NOT write to "addons/warranty_manager" without the suffix. '
        f"Tool scope: use only these tools: {args.allowed_tools}. "
        f"Apply changes and run tests (uv run). Use Inspection MCP if available and converge to zero warnings. Return a concise report (Decision • Diffs/Paths • Test summary • Inspection summary • Risks/next steps)."
    )

    cmd = [codex_bin, "exec", "--sandbox", args.sandbox, prompt]

    print(f"[info] Running Codex: writing transcript to {transcript}", file=sys.stderr)
    with transcript.open("w", encoding="utf-8", errors="ignore") as fh:
        proc = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert proc.stdout is not None
        for line in proc.stdout:
            if args.verbose:
                sys.stdout.write(line)
            fh.write(line)
        rc = proc.wait()

    print(f"[done] Transcript: {transcript}", file=sys.stderr)

    if args.digest:
        digest(transcript, root)
    if args.prune and args.prune > 0:
        prune(run_dir, args.prune)

    sys.exit(rc)


if __name__ == "__main__":
    main()
