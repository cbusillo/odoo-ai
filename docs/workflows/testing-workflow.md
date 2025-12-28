---
title: Testing Workflow
---


Fast → Full

- Loop: `uv run test unit --modules <touched>`; JS with `--js-modules`; selective integration/tour as needed.
- Gate: `uv run test run --json` all phases; require `success: true`.

Logs & Summaries

- Parse `tmp/test-logs/latest/summary.json` (or per‑phase summaries) for a single result.
