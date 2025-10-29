# Project Documentation

This repository is organized for Codex CLI–driven development with small, focused documents that are easy to load by
handle.

Use path+anchor “handles” when sharing docs between sessions, for example:

- @docs/style/python.md#type-hints
- @docs/odoo/orm.md#batch-writes
- @docs/workflows/codex-workflow.md#working-loop

## Table of Contents

- Roles
    - docs/roles/analyst.md — research and discovery
    - docs/roles/engineer.md — implementation and refactoring
    - docs/roles/tester.md — unit/JS/integration/tour
    - docs/roles/reviewer.md — inspections and zero‑warning policy
    - docs/roles/maintainer.md — release and branch hygiene
- Policies
    - docs/policies/acceptance-gate.md — zero‑warning + full test run
    - docs/policies/doc-style.md — topic page conventions and anchors
    - docs/policies/coding-standards.md — top‑level rules and links
- Workflows
    - docs/workflows/codex-workflow.md — plan → patch → targeted tests/inspection → iterate → full gate
    - docs/workflows/odoo-development.md — minimal change path, batching, security checks
    - docs/workflows/testing-workflow.md — sharding, scoping, JSON summaries
    - docs/workflows/debugging.md — error analysis and triage
    - docs/workflows/refactor-workflows.md — safe refactoring processes
    - docs/workflows/refactor-safety.md — pre‑refactor checks
    - docs/workflows/performance-review.md — performance analysis
    - docs/workflows/migration.md — migration patterns (Odoo 18)
    - docs/workflows/planning.md — planning templates
    - docs/workflows/service-patterns.md — service layer patterns
    - docs/workflows/bulk-operations.md — mass data processing
- Tooling
    - docs/tooling/codex-cli.md — sessions, profiles, sandbox/approval
    - docs/tooling/inspection.md — changed/git/full scopes, result schema
    - docs/tooling/odoo-intelligence.md — model/field queries, module updates
    - docs/tooling/testing-cli.md — uv test phases and flags
    - docs/tooling/docker.md — container operations
    - docs/tooling/docker-mcp.md — Docker MCP usage and JSON param shapes
        - docs/testing.md — testing overview and pointers
- Odoo Canon
    - docs/odoo/orm.md — recordsets, batching, computed fields
    - docs/odoo/security.md — ACLs, access rules, safe defaults
    - docs/odoo/performance.md — ORM perf, N+1, batching
    - docs/odoo/workflow.md — module layout, imports, container paths
- Architecture & Resources
    - docs/architecture.md — system architecture overview
    - docs/resources.md — external documentation links
- Integrations
    - docs/integrations/README.md — integrations index
    - docs/integrations/shopify.md — Shopify integration guide
    - docs/integrations/graphql.md — GraphQL patterns (Shopify)
    - docs/integrations/webhooks.md — Webhook patterns
    - docs/integrations/shopify-sync.md — Shopify sync patterns
- Recipes
    - docs/recipes/cell-mechanic-db.md — run the Cell Mechanic addon against its own database
- Style
    - docs/style/index.md — style index (start here)
    - docs/style/python.md — type hints, f‑strings, line length
    - docs/style/javascript.md — ES modules, Owl patterns
    - docs/style/testing.md — base classes, fixtures, tours
    - docs/style/hoot-testing.md — Hoot testing
    - docs/style/owl-components.md — Owl components
    - docs/style/owl-troubleshooting.md — Owl troubleshooting
    - docs/style/playwright-patterns.md — Playwright patterns
    - docs/style/playwright-selectors.md — Playwright selectors
    - docs/style/tour-debugging.md — Tour debugging
    - docs/style/tour-patterns.md — Tour patterns
    - docs/style/test-scenarios.md — Common test scenarios
    - docs/style/testing-advanced.md — Advanced Odoo testing

Notes

- Keep docs small; prefer linking by handle to larger guides when needed.
- docs/todo/* is intentionally git‑ignored for transient work items.
