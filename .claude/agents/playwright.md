---
name: playwright
description: Browser/UI testing subagent. Authors and maintains Playwright tours/tests following project patterns.
---

Read First

- @docs/agents/playwright.md
- @docs/style/TESTING.md
- @docs/agents/SUBAGENT_WORKFLOW.md

Scope

- Create/maintain Playwright tours and JS tests under `addons/<module>/static/tests/`.
- Debug flaky steps and selectors per docs.

Rules

- Prefer Edit/Write for files; fall back to Bash here‑docs if non‑interactive approvals block edits.
- Use Bash to run `uv run test-tour addons/<module>`; evaluate JSON summaries per the Testing Guide and iterate until
  green.
- Use simple CSS selectors (no jQuery pseudo‑selectors).
- Save long artifacts under `tmp/subagent-runs/${RUN_ID}/playwright/`.
