# ERROR_RECOVERY.md — Minimal Playbook

Use this checklist when tools fail or agents get stuck.

Steps
- Re-run with read‑only sandbox to reproduce safely.
- Check approvals and sandbox mode; escalate only if necessary.
- Verify paths (host vs container). Use Odoo/Docker tools for container files.
- Run targeted tests: `uv run test unit` to narrow the blast radius.
- Gate and capture: `uv run test run --json` waits and exits 0/1, writing artifacts under `tmp/test-logs/latest/`.
- If Claude/Codex session is inconsistent, start a fresh session and re-attach minimal context.

Notes
- Do not run Python directly; use Odoo environment commands only.
- Prefer MCP tools with structured outputs; avoid brittle text parsing.
