Title: Codex CLI

Purpose

- Run Codex sessions with explicit sandbox/approval and small, focused context.

Profiles (local ~/.codex/config.toml)

- quick (read-only)
- dev-standard (workspace-write, approval on-failure)
- deep-reasoning (like dev-standard, more reasoning time)
- inspector (read-only)
- test-runner (workspace-write)

Notes

- Omit model unless you must override the CLI default.
- Set `sandbox` explicitly per run; prefer `workspace-write` for implementation, `read-only` for analysis.
- Start each non-trivial task with the plan tool and update it as steps complete; Codex enforces one active step at a
  time.
- Before grouped tool calls, send a one-sentence preamble describing the intent to keep logs readable and approvals
  smooth.
- For multi-line scratch scripts, drop a file under `tmp/scripts/` (gitignored) and run
  `uv run python tmp/scripts/<file>.py`
  instead of using heredocs; this keeps the `uv run` sandbox bypass active and makes reruns easy.
- When testing service logins, skip the marketing site by loading `/odoo/web/login` directly. If the quick-login widget
  is still hidden, run `document.querySelector('form.oe_login_form').classList.remove('d-none')` (and set
  `display='block'`) to reveal the desktop form before typing credentials.
