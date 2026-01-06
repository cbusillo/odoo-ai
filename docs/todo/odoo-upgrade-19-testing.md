You are Code in repo odoo-ai. Start from branch 19.0 and create a new work branch (e.g., 19.0-test-fixes). This session
is
ONLY for tests/fixtures/bug fixes — no feature work.

Scope and guardrails:

- Use uv run … for all commands.
- Prefer Odoo Intelligence MCP for discovery before ad‑hoc shell commands. This is only for addons and tools it lists
  do not use it for docs of fixtures in the root of this repo outside the addons folder. The addons folder is mapped
  into docker so odoo-intelligence will work on it.
- Fix only clear bugs/tests/fixtures. If behavior is ambiguous, DO NOT guess — document it and move on.
- Never edit generated GraphQL artifacts: addons/product_connect/services/shopify/gql/* and
  addons/product_connect/graphql/
  schema/*.
- Follow Odoo 19 view rules (<list>, no attrs/states), and repo standards in AGENTS.md.
- Auto-review tool is failing due to provider stream errors — rely on manual inspection (see
  docs/tooling/inspection.md).

Required documentation updates:

- Update docs/todo/odoo-upgrade-19.md with date-stamped progress notes and decisions.
- Create a new doc for confusing failures: docs/todo/confusing-test-failures.md. For each ambiguous failure, log
  command,
  failure snippet, why unclear, suspected root cause, and next questions.

Workflow (repeat per failure):

1) Baseline failures: uv run test run --json (use detached mode if needed).
2) Triage each failure: clear vs ambiguous.
3) Fix clear ones with minimal diffs and rerun scoped tests (uv run test unit --modules <touched> and/or uv run test js
   --modules <touched>).
4) Log ambiguous ones in docs/todo/confusing-test-failures.md and stop there.
5) Manual inspection (changed → git), then full gate: uv run test run --json.

End state: green gate OR a clean set of fixes plus a complete docs/todo/confusing-test-failures.md list, with docs/todo/
odoo-upgrade-19.md updated accordingly.

Any questions before we start the auto drive session? Please read appropriate docs and code before you answer