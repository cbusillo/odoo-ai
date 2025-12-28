---
title: Project Documentation
---


This repository is organized for Codex CLI–driven development with small,
focused documents that are easy to load by handle.

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
    - docs/workflows/planning.md — planning workflow
    - docs/workflows/service-patterns.md — service layer sources of truth
    - docs/workflows/bulk-operations.md — mass data processing
    - docs/workflows/prod-deploy.md — prod deploy gate + rollback
- Tooling
    - docs/tooling/codex-cli.md — sessions, profiles, sandbox/approval
    - docs/tooling/runtime-baselines.md — where Python/runtime versions live
        - docs/tooling/inspection.md — changed/git/full scopes, result schema
        - docs/tooling/odoo-intelligence.md — model/field queries, module updates
        - docs/tooling/testing-cli.md — uv test phases and flags
        - docs/tooling/docker.md — container operations
        - docs/tooling/coolify.md — Coolify app logs/envs
            - docs/TESTING.md — testing overview and pointers
- Odoo Canon
    - docs/odoo/orm.md — ORM sources of truth
    - docs/odoo/security.md — ACLs, access rules, safe defaults
    - docs/odoo/performance.md — performance sources of truth
    - docs/odoo/workflow.md — Odoo workflow and conventions
- Architecture & Resources
    - docs/ARCHITECTURE.md — system architecture overview
    - docs/resources.md — external documentation links
- Integrations
    - docs/integrations/README.md — integrations index
    - docs/integrations/shopify.md — Shopify integration guide
    - docs/integrations/graphql.md — GraphQL sources of truth (Shopify)
    - docs/integrations/webhooks.md — webhook sources of truth
    - docs/integrations/shopify-sync.md — Shopify sync sources of truth
- Style
    - docs/style/index.md — style index (start here)
    - docs/style/python.md — type hints, f‑strings, line length
    - docs/style/javascript.md — ES modules, Owl patterns
        - docs/style/testing.md — base classes, fixtures, tours
        - docs/style/hoot-testing.md — Hoot testing
        - docs/style/owl-components.md — Owl sources of truth
        - docs/style/owl-troubleshooting.md — Owl troubleshooting sources of truth
        - docs/style/browser-automation.md — built-in browser tooling
        - docs/style/tour-debugging.md — Tour debugging
        - docs/style/tour-patterns.md — tour sources of truth
        - docs/style/test-scenarios.md — test scenario sources of truth
        - docs/style/testing-advanced.md — advanced testing sources of truth

Notes

- Keep docs small; prefer linking by handle to larger guides when needed.
- `docs/todo/` holds tracked, living work-in-progress docs.
  Use `*.local.md` for personal scratch notes (git-ignored).
- Living migration doc (tracked): `docs/todo/NEW_ARCH.md` (active OPW/CM stack
  and addons plan).
