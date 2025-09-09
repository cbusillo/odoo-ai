# Subagent Test Scenario (Claude Code)

Purpose

- Validate subagent delegation keeps the main Claude context clean while building a small Odoo addon.

Prereqs

- Claude Code CLI installed (`claude --version`).
- MCP servers configured if you want Odoo/Docker tools (optional for this test): `claude mcp list`.

Run

- Operator-run script (simple, no worktrees):
    - `CLAUDE_BIN=/Users/cbusillo/.claude/local/claude tools/claude_subagent_quick.sh`
    - The runner defaults to `--permission-mode bypassPermissions` so writes/tests proceed non‑interactively. Override
      with `PERMISSION_MODE=acceptEdits` if desired.

What to observe

- Subagent creation/use in the transcript (archer, scout, odoo-engineer, inspector).
- Changes applied under `addons/warranty_manager/` (not just proposed diffs).
- Tests invoked by the testing subagent (uv run), with iterative fixes until green.
- Artifacts saved under `tmp/subagent-runs/<RUN_ID>/...` (logs, long listings).

Optional model routing

- Set a lightweight default for subagents (adjust to your environment):
    - Use Claude’s model selector for subagents, or set an environment override if supported.
- Escalate only when acceptance criteria require deeper reasoning.

Next steps

- Review the changes and run full test suites as needed.
- If issues persist, re-run Inspector subagent or request targeted fixes.
