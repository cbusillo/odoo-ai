# Codex Integration Test (Operator Guide)

Purpose

- Non‑interactive smoke test to ensure Codex can apply changes, run tests (uv), run MCP inspection (if available), and
  converge to zero warnings.

Run

- Shared task (default):
    - `uv run python tools/test_codex_integration.py` (quiet by default)
    - Add `--verbose` to stream full output; otherwise only the transcript is written and the digest is printed.
    - Uses addon name `warranty_manager_codex` (suffix for comparison).
    - Optional: `--digest` to print a short summary; `--prune N` to keep only the last N transcripts under
      `tmp/codex-runs/`.

Observe

- Transcript files under `tmp/codex-runs/`
- Optional digest: pass `--digest`; prune old transcripts with `--prune N`

Notes

- Workflow/policy: See `docs/codex/WORKFLOW.md` and AGENTS.md.
- Odoo canon & examples: `docs/odoo18/*`, `addons/product_connect`, `addons/external_ids`.
