---
title: Testing Style
---


Purpose

- Consolidate testing conventions and pointers to real test sources.

When

- Any time you add or modify tests, fixtures, or tours.

Sources of Truth

- `addons/*/tests/` — unit/integration tests in this repo.
- `addons/*/tests/fixtures/` — factories and shared fixtures.
- `addons/*/static/tests/` — JS/Hoot/tour tests.
- `addons/*/static/tests/helpers/` — shared JS helpers (when present).

Environment Validation Scenarios

- Use `validation scenario` or `environment-level validation` for
  instance-aware checks that exercise real restored/testing stacks and may rely
  on real credentials, real network calls, or destructive setup such as reset
  plus re-export flows.
- Do not treat these scenarios as normal `uv run test ...` assets unless they
  become deterministic enough for the shared test gate.
- When a one-off validation flow proves reusable, promote it out of
  `tmp/scripts/` into a tracked script under `tools/validate/` instead of
  leaving it as scratch code.
- Keep addon test trees (`addons/*/tests/`) focused on gateable unit,
  integration, JS, and tour coverage. Put environment orchestration and
  instance-aware round-trip checks in tracked validation scripts, not in addon
  test suites.
- Prefer platform-managed entry points for these scenarios so target selection,
  env loading, and logging remain consistent. Until a dedicated
  `uv run platform validate ...` command exists, run promoted local scenarios
  through `uv run platform odoo-shell --context <ctx> --instance local --script
  tools/validate/<scenario>.py` and keep remote variants behind explicit
  managed entry points rather than ad hoc shell snippets.

Recorded Tours

- DB-recorded tours live in `web_tour.tour`/`web_tour.tour.step`
  (recorded via the UI recorder).
- Export recorded tours with the managed local runtime:

  ```bash
  uv run platform odoo-shell --context opw --instance local \
    --script tools/tour_recorder/export_recorded_tours.py
  ```

  Fall back to raw `docker compose exec` only when the managed platform
  contract is unavailable.

- Seed at test time by passing `RECORDED_TOURS_JSON` or
  `RECORDED_TOURS_PATH` (e.g., a temp file).

Basics

- Place Python tests under `addons/<module>/tests/` and JS/tours under
  `addons/<module>/static/tests/`.
- Use base classes and factory helpers; avoid ad hoc data creation where
  possible.
- Tag tests appropriately (unit/integration/tour) to keep runs predictable.

`test_support`

- Treat `addons/test_support/` as the shared test toolkit, not a dumping ground
  for every fixture in the repo.
- `test_support` may have a small baseline dependency set when that supports
  genuinely generic test helpers, but it must not accumulate domain or
  business-module dependencies just to silence IDE resolution issues.
- Keep code in `test_support` only when it is broadly reusable and does not
  encode addon-specific knowledge such as custom models, custom fields, or
  addon-provided helper methods.
- Generic primitives belong in `test_support`: shared base cases, discovery
  helpers, neutral factory building blocks, and broadly applicable fixtures.
- Domain composition belongs with the owning addon's tests: if a helper needs
  addon-specific models, fields, defaults, or wiring, keep the final composer
  in that addon's `tests/fixtures/` module even if it calls shared helpers.
- The same rule applies to browser/tour helpers: addon-specific selectors,
  Discuss/mail navigation, and business-flow helpers stay local to the addon
  test tree even when multiple tours share them.

Direct Imports vs Local Wrappers

- Import directly from `test_support` when the symbol is truly generic and the
  addon does not need to reshape it.
- Addon-local wrappers are optional. Use them when they add clarity, provide
  addon-specific tags or default context, or expose a curated/descriptive test
  API.
- Avoid pass-through wrappers that do nothing but rename an unchanged shared
  import. Prefer the shorter direct import in that case.
- Use local wrappers when they decouple tests from shared implementation churn
  or when they make domain intent clearer at the call site.
- Addon-local fixture bases may expose typed convenience properties for Odoo
  models used heavily in tests (for example `Partner`, `ExternalId`,
  `RepairshoprImporter`) when that materially improves PyCharm inspections.
  Keep those typed properties in the owning addon's `tests/fixtures/base.py`
  rather than pushing addon-specific model knowledge into `test_support`.

`common_imports`

- Prefer exactly one addon-local shim at `tests/common_imports.py` when an
  addon wants a curated test API.
- The default shape is:
  - `from test_support.tests import build_common_imports`
  - `common = build_common_imports(__package__, ...)`
- Keep `tests/common_imports.py` declarative and tiny. In the normal case it
  should only build and export the shared `common` object.
- In test files, prefer `@common.tagged(*common.UNIT_TAGS)` and similar access
  over re-exporting many individual module globals.
- Prefer the shared builder over `import *` wrappers, `globals().update(...)`,
  or addon-local `base_types.py` / `test_helpers.py` pass-through modules.
- Define addon-local `common_imports` wrappers only when the addon needs its
  own tags, default context, or a narrower import surface for readability.
- Import generic fixtures and helpers directly from `test_support` when the
  addon does not add meaningful value on top.
- Do not create addon-local pass-through fixture modules that only re-export
  `test_support.tests.fixtures.*` unchanged.
- Apply the same rule as fixtures: wrappers are a tool for clarity and local
  ownership, not a mandatory layer.

Inspection Priority

- For Odoo test code, JetBrains/PyCharm inspection is the authoritative signal
  for cleanup and shaping decisions.
- Ruff remains required for fast syntax/style feedback, but it does not replace
  inspection-driven cleanup for dynamic Odoo patterns, model aliases, or test
  base ergonomics.
- When Ruff is green and PyCharm still reports actionable addon-test findings,
  keep iterating until the inspection result is clean or a narrow suppression is
  clearly justified.

Addon Test Bases

- Treat `tests/fixtures/base.py` as the primary place for addon-specific test
  composition.
- It is acceptable for addon test bases to do small amounts of inspection-
  friendly shaping on top of `test_support`, such as:
  - declaring `model_aliases` used by the shared unit base,
  - exposing typed model properties backed by `self.env["..."]`,
  - setting addon-local default test context or tags.
- Prefer fixing repeated inspection noise at the shared addon test-base layer
  before editing many individual test methods or adding suppressions.

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
