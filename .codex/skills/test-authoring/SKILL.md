---
name: test-authoring
description: Use when writing or updating tests (Python, JS/Hoot, integration, or tours).
---

# Test Authoring

## Scope

- This skill covers choosing test types and writing tests for Python,
  JS/Hoot, integration, and tours.
- For running and gating tests, use $testing-gate-run.

## Decision guide

- Server logic, ORM, or business rules: Python tests under
  `addons/<module>/tests/`.
- UI or Owl behavior: JS/Hoot tests under `addons/<module>/static/tests/`.
- Click-through user flows: tours under `addons/<module>/static/tests/`.
- Multi-service paths or external integrations: integration tests.

## Authoring guardrails

- Reuse base classes and factory helpers; avoid ad-hoc data creation.
- Tag tests appropriately to keep runs predictable.
- Tours: use simple, stable selectors and explicit waits for UI state.

## References

- @docs/style/testing.md
- @docs/style/testing-advanced.md
- @docs/style/hoot-testing.md
- @docs/style/tour-patterns.md
- @docs/style/tour-debugging.md
- @docs/workflows/testing-workflow.md
