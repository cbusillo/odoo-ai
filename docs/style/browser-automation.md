---
title: Browser Automation (Built-in)
---


## Purpose

Use the built-in Code browser tools for UI validation. Avoid Playwright.

## Guardrails

- Prefer stable selectors (role/name/data attributes).
- Wait for UI state, not fixed sleeps.
- Capture screenshots/console output on failures.
- Keep interactions short and deterministic.

## Sources of Truth

- `docs/tooling/codex-cli.md` — Codex CLI usage and browser tool notes.
