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

