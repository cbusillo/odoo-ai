---
title: Testing Style
---


Purpose

- Consolidate testing conventions and pointers to real test sources.

Basics

- Place Python tests under `addons/<module>/tests/` and JS/tours under
  `addons/<module>/static/tests/`.
- Use base classes and factory helpers; avoid ad hoc data creation where
  possible.
- Tag tests appropriately (unit/integration/tour) to keep runs predictable.

Sources of Truth

- `addons/*/tests/` — unit/integration tests in this repo.
- `addons/*/tests/fixtures/` — factories and shared fixtures.
- `addons/*/static/tests/` — JS/Hoot/tour tests.
- `addons/*/static/tests/helpers/` — shared JS helpers (when present).

Hoot and JS Testing

- Keep Hoot patterns aligned with real tests under `addons/*/static/tests/`.
- Prefer existing helpers under `addons/*/static/tests/helpers/`.

Selectors (tours)

- Prefer simple, stable selectors (role/name) and avoid brittle CSS chains.
- Add explicit waits for UI state rather than fixed sleeps.

Tour Sources

- `addons/*/static/tests/tours/` — actual tour implementations.
- `docs/style/browser-automation.md` — browser tooling and selector guidance.
- `docs/workflows/debugging.md` — debugging workflow for flaky tours.

Service Mocking

- JS mocks live with tests under `addons/*/static/tests/`.
- Python fixtures live under `addons/*/tests/fixtures/`.

Advanced Scenarios

- Avoid generic examples; point to real tests and fixtures in the repo.
- Use `docs/TESTING.md` for the fast -> full test flow.

See also

- `docs/TESTING.md` — test workflow and gate rules.
- `docs/tooling/testing-cli.md` — command and flag reference.
