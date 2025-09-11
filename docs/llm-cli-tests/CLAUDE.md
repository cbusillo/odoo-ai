# Claude Integration Test (Operator Guide)

Purpose

- Non‑interactive smoke test to ensure subagents apply changes, run tests (uv), run MCP inspection, and converge to zero
  warnings.

Run

- Simple (no worktrees):
    - `uv run python tools/test_claude_integration.py`
    - Defaults to `--permission-mode bypassPermissions` so writes/tests proceed. Override with
      `PERMISSION_MODE=acceptEdits` to only auto‑approve edits.
    - Uses addon name `warranty_manager_claude` (suffix for comparison).
    - Optional: `--digest` to print a short summary; `--prune N` to keep only the last N artifact directories under
      `tmp/subagent-runs/`.

Observe

- Transcript: `tmp/claude-subagent-test/transcript.jsonl`
- Optional digest: pass `--digest`; prune with `--prune N`

Notes

- Workflow/policy: See `docs/agents/SUBAGENT_WORKFLOW.md` and `CLAUDE.md`.
